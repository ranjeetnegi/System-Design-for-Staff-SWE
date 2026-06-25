# Chapter 28 — Part A: The Database Decision Framework

> "The most expensive database decision you will ever make is the one you made before you understood the problem."

---

## Table of Contents

1. The Fatal Mistake (and How to Avoid It)
2. The 4-Step Selection Framework
   - Step 1: Understand Your Data
   - Step 2: Understand Your Access Patterns
   - Step 3: Understand Your Constraints
   - Step 4: Plan Your Evolution Path
3. Database Internals: B-Tree vs LSM-Tree
4. ACID Deep Dive with Concrete Examples
5. L5 vs L6 Decision Table

---

## 1. The Fatal Mistake

Here is a conversation that plays out dozens of times per week in system design interviews — and in real engineering organizations:

> **Interviewer:** "Design a ride-sharing app like Uber."
>
> **Candidate:** "Sure. I'll use PostgreSQL for user data, Redis for caching, and Kafka for event streaming."

That candidate just made the fatal mistake. They named technologies within fifteen seconds of hearing the problem. They haven't asked: What does the data look like? How is it read back? How fast does it need to come back? What happens if two riders book the same driver simultaneously?

This is the **L5 trap**: defaulting to familiar tools before understanding what problem those tools need to solve.

**Staff Engineers — the L6 level — think in a completely different order:**

```
  WRONG order (L5):          RIGHT order (L6):
  
  Hear problem               Hear problem
       |                          |
       v                          v
  Name a database           What shape is the data?
                                  |
                                  v
                            How is it accessed?
                                  |
                                  v
                            What are the constraints?
                                  |
                                  v
                            NOW name a database
```

The right order feels slower. In an interview, the instinct is to jump to technology because technology sounds confident. But the interviewer — especially at L6 — is watching to see if you ask questions first. A candidate who spends three minutes clarifying before touching architecture is demonstrating exactly the skill that separates senior from staff.

### Why This Mistake Is So Expensive

When you choose a database before understanding access patterns, one of two things happens:

1. **You get lucky** — the database you picked happens to fit, usually because the problem was simple enough that almost anything would have worked.
2. **You get burned** — six months later you discover that your relational database can't do the geospatial queries your product actually needs, or your document store can't enforce the transaction semantics your finance team requires. Migration at that point costs weeks of engineering, carries real data-loss risk, and almost certainly causes downtime.

Database migrations are among the most painful operations in software engineering. You can refactor code in a day. You cannot migrate a 10 TB production database in a day.

### The Chapter Map

Here is the full territory this chapter covers. Keep this picture in mind as you read:

```
  ┌─────────────────────────────────────────────────────────────────────┐
  │              DATABASE DECISION FRAMEWORK (Ch 28 Part A)             │
  │                                                                     │
  │  ┌─────────────┐   ┌──────────────┐   ┌────────────┐   ┌────────┐ │
  │  │  STEP 1     │   │   STEP 2     │   │  STEP 3    │   │ STEP 4 │ │
  │  │  Your Data  │──>│ Your Access  │──>│  Your      │──>│ Evolve │ │
  │  │             │   │  Patterns    │   │ Constraints│   │  Path  │ │
  │  └─────────────┘   └──────────────┘   └────────────┘   └────────┘ │
  │        │                  │                  │               │     │
  │   shape, size,       read:write,       ACID vs BASE,    migration │
  │   relations,         latency SLA,      scale, budget,   strategy  │
  │   lifecycle          hot keys,         team skill                  │
  │                      query flex                                    │
  │                                                                    │
  │  ┌──────────────────────────────────────────────────────────────┐  │
  │  │               INTERNALS (Part A, Section 3)                  │  │
  │  │   B-Tree storage     vs     LSM-Tree storage                 │  │
  │  │   (PostgreSQL/MySQL)         (Cassandra/RocksDB)             │  │
  │  └──────────────────────────────────────────────────────────────┘  │
  │                                                                    │
  │  ┌──────────────────────────────────────────────────────────────┐  │
  │  │               ACID DEEP DIVE (Part A, Section 4)             │  │
  │  │  Atomicity | Consistency | Isolation Levels | Durability/WAL │  │
  │  └──────────────────────────────────────────────────────────────┘  │
  └─────────────────────────────────────────────────────────────────────┘
```

---

## 2. The 4-Step Selection Framework

### Step 1: Understand Your Data

Before you can pick a database, you need to understand what you are storing. This sounds obvious, but most engineers skip it entirely. There are three fundamental data shapes, and each has a natural home.

#### Structured vs Semi-Structured vs Unstructured

**Structured data** has a fixed schema. Every record has the same fields, the same types, the same constraints. Think of a spreadsheet where every row must have the same columns. Examples: user accounts (id, email, created\_at, plan\_tier), financial transactions (amount, currency, from\_account, to\_account, timestamp), product inventory (sku, name, price, stock\_count).

Structured data is the natural home of **relational databases** (PostgreSQL, MySQL). The database can enforce that every row obeys the schema, which prevents an enormous class of bugs.

**Semi-structured data** has a shape, but the shape varies from record to record. Think of a product catalog where a laptop has "processor\_speed" and "ram\_gb" but a t-shirt has "size" and "color" — they're both products, but their attributes are completely different. Examples: user profiles where different users have filled in different optional fields, IoT sensor readings where different sensor models emit different fields, configuration documents.

Semi-structured data fits naturally in **document databases** (MongoDB, DynamoDB) or as JSONB columns in PostgreSQL.

**Unstructured data** has no schema at all. Images, videos, audio files, PDFs, raw text logs. These do not belong in any of the databases covered in this chapter — they belong in **object storage** (S3, GCS), with only their metadata (filename, size, owner, created\_at) stored in a database.

```
  DATA SHAPE DECISION:

  ┌─────────────────────────────────────────────────┐
  │  Q: Does every record have the same fields?     │
  └───────────────┬─────────────────────────────────┘
                  │
       ┌──────────┴──────────┐
      YES                    NO
       │                     │
       v                     v
  Structured           Does it have ANY
  (Relational DB)      consistent structure?
                            │
                 ┌──────────┴──────────┐
                YES                    NO
                 │                     │
                 v                     v
          Semi-Structured          Unstructured
          (Document DB or          (Object Storage,
           JSONB column)            NOT a DB)
  └─────────────────────────────────────────────────┘
```

#### Data Relationships: Flat, Hierarchical, Graph

The second dimension of your data is how records relate to each other.

**Flat data** has no relationships. Every record stands alone. A log line knows nothing about other log lines. An event in a clickstream is independent of other events. This is where **key-value stores** (Redis, DynamoDB) shine — they are optimized for finding one thing by its key, and they don't need to join anything to anything else.

**Hierarchical data** has parent-child trees. A comment thread has a top-level post, replies to that post, and replies to replies. An organization chart has a CEO, who has VPs, who have directors, who have managers. Hierarchical data can live in a relational database (using a self-referential foreign key), but deeply nested queries become expensive. **Document databases** are often a better fit because the whole subtree can be stored as a single document and retrieved in one read.

**Graph data** has arbitrary many-to-many relationships with semantic edges. "Alice knows Bob, Bob works for Carol, Carol invested in Dave's company, Dave is Alice's brother." There is no clean hierarchy. Traversing these relationships in a relational database requires expensive recursive JOINs. **Graph databases** (Neo4j, Amazon Neptune) store edges as first-class objects alongside nodes, making relationship traversals fast regardless of depth.

```
  RELATIONSHIP SHAPE:

  FLAT (key-value)         HIERARCHICAL (document)    GRAPH (graph DB)
  
  [rec1]  [rec2]               [root]                 [A]---[B]
  [rec3]  [rec4]              /      \                 |   X   |
  [rec5]  [rec6]          [child1] [child2]           [C]---[D]
                           /    \      \               |       |
  No edges              [gc1] [gc2] [gc3]             [E]-----[F]
  
  Fast by key           Fetch whole tree              Traverse any path
  No traversal          in one read                   with equal cost
```

#### Data Lifecycle: New vs Old

One dimension that is almost never discussed in textbooks but matters enormously in practice is **data lifecycle** — how old data is accessed compared to new data.

For most applications, new data is accessed far more frequently than old data. A social media feed shows posts from the last 48 hours. A ride-sharing app queries active trips. An e-commerce site shows orders from the last 90 days.

This pattern — **recency bias in reads** — has a huge implication: your database needs to be fast for new data, and it can tolerate being slower for old data. This is why **tiered storage** exists. Hot data (last 30 days) lives on fast SSDs in your primary database. Warm data (30 days to 1 year) lives in compressed columnar storage. Cold data (1+ year) lives in cheap object storage like S3 Glacier.

Designing your database without thinking about lifecycle means you will pay SSD prices for data that nobody reads. At scale, this is the difference between a $50,000/month database bill and a $5,000/month one.

---

### Step 2: Understand Your Access Patterns

This is the most important step. Access patterns are the specific questions your application needs to ask of your data. Two applications with identical data shapes can require completely different databases if they ask different questions of that data.

#### The Read:Write Ratio

Every database is a trade-off between making reads faster and making writes faster. Understanding your read:write ratio tells you which side of that trade-off to optimize for.

**Write-heavy workloads** (10:1 writes to reads or higher): Examples include IoT telemetry ingestion, real-time event logging, metrics collection. These workloads need databases with fast write paths — typically **LSM-tree-based stores** like Cassandra or InfluxDB (covered in detail in Section 3).

**Read-heavy workloads** (10:1 reads to writes or higher): Examples include product catalog lookups, user profile fetches, content serving. These workloads benefit from **B-tree-based databases** (PostgreSQL, MySQL) whose read path is optimized, plus **caching layers** (Redis).

**Balanced workloads**: Most OLTP (Online Transaction Processing) applications — the kind that power typical web apps — have read:write ratios around 5:1 to 10:1 in favor of reads. PostgreSQL handles this extremely well.

**OLAP workloads** (Online Analytical Processing): These are analytical queries — aggregations over millions of rows, GROUP BY, complex JOINs. The read:write ratio is extreme (10,000:1 or more) but reads are full-table scans, not point lookups. These belong in **columnar data warehouses** (Snowflake, BigQuery, Redshift), not in OLTP databases.

```
  READ:WRITE RATIO DECISION MAP:

  Writes/sec >> Reads/sec?
  ┌────────────────────────────────────────────────────┐
  │  YES: Write-Heavy                                  │
  │  --> LSM-tree: Cassandra, ScyllaDB, InfluxDB       │
  └────────────────────────────────────────────────────┘

  Reads/sec >> Writes/sec, reads are point lookups?
  ┌────────────────────────────────────────────────────┐
  │  YES: Read-Heavy OLTP                              │
  │  --> B-tree: PostgreSQL/MySQL + Redis cache        │
  └────────────────────────────────────────────────────┘

  Reads/sec >> Writes/sec, reads are full-table aggregations?
  ┌────────────────────────────────────────────────────┐
  │  YES: OLAP / Analytics                             │
  │  --> Columnar: Snowflake, BigQuery, Redshift       │
  └────────────────────────────────────────────────────┘
```

#### Point Lookups vs Range Scans vs Aggregations

These are the three fundamental access pattern shapes. Every query your application runs is one of these (or a combination).

**A point lookup** fetches exactly one record by its primary key. "Give me the user with id = 42." This is the fastest possible query type — it takes O(log N) time in a B-tree index or O(1) amortized in a hash index. Redis, DynamoDB, and any well-indexed relational database handle this excellently.

```
  POINT LOOKUP:
  
  Query: user_id = 42
  
  Index:
  ┌──────┬────────────┐
  │ id=1 │ page 0x1A  │
  │ id=7 │ page 0x2C  │
  │ id=42│ page 0x9F  │  <-- found! go to this page
  │ id=99│ page 0xB1  │
  └──────┴────────────┘
            |
            v
  ┌──────────────────────┐
  │  page 0x9F           │
  │  {id:42, name:"Ana"} │  <-- return this row
  └──────────────────────┘
  
  Cost: O(log N) — extremely fast
```

**A range scan** fetches all records where a key falls within a range. "Give me all orders placed between Jan 1 and Jan 31." This requires the database to walk through a sorted index and return every matching entry. B-trees handle this well because pages are sorted and physically adjacent (leaf pages are linked). Hash indexes cannot do this at all — they have no concept of ordering.

```
  RANGE SCAN:
  
  Query: order_date BETWEEN '2024-01-01' AND '2024-01-31'
  
  Sorted leaf pages (B-tree):
  
  [Dec 28] --> [Dec 31] --> [Jan 01] --> [Jan 05] --> [Jan 12]
                               ^                          ^
                            start here                scan to here
                            
  Walk the linked list of leaf pages.
  Return every row where date is in range.
  
  Cost: O(log N + K) where K = number of matching rows
```

**Aggregations** compute summary statistics over many rows. "What is the total revenue per country this quarter?" These queries scan huge numbers of rows but return very few. In a **row-oriented** database (PostgreSQL), this means reading entire rows just to extract one or two columns — wasteful. **Columnar databases** store all values for a single column together, so an aggregation query only reads the column it needs, not the whole row.

```
  ROW vs COLUMN STORAGE FOR AGGREGATION:
  
  Row-oriented (PostgreSQL):
  ┌────────────────────────────────────────────┐
  │ [id:1, name:"Ana",  country:"US", amt:100] │  must read entire row
  │ [id:2, name:"Bob",  country:"UK", amt:200] │  just to get "amt"
  │ [id:3, name:"Carl", country:"US", amt:150] │
  └────────────────────────────────────────────┘
  
  Column-oriented (Snowflake, Parquet):
  ┌─────────────┐  ┌──────────────────┐  ┌──────────────┐
  │ id: 1,2,3   │  │ country:US,UK,US │  │ amt: 100,200,│
  └─────────────┘  └──────────────────┘  │       150    │
                                          └──────────────┘
  
  Query "SUM(amt) WHERE country='US'" only touches
  the "country" column and "amt" column.
  Skip "id" and "name" entirely.
  
  For 1 billion rows, this is ~10x-100x faster.
```

#### Hot Keys: What They Are and Why They Are Dangerous

A **hot key** is a single key (or small set of keys) that receives a disproportionate fraction of all requests. In a distributed database, data is split across many machines (called **shards** or **partitions**) by key. If all requests go to one key, all traffic goes to one shard. That one machine melts. The others sit idle.

Real examples of hot key problems:
- A celebrity posts on a social media platform — every follower's feed load generates a read for that post's key
- The product page for a flash sale item — millions of requests per second, all for one product ID
- A shared counter (like "total page views") — every page load increments the same key

```
  HOT KEY PROBLEM:
  
  4 shards, "balanced" distribution:
  
  Shard A: [key1, key2, key3, key4]      5 req/s each
  Shard B: [key5, key6, key7, key8]      5 req/s each
  Shard C: [key9, key10, key11, key12]   5 req/s each
  Shard D: [celebrity_post_id]           500,000 req/s   <-- ON FIRE
  
  Shard A, B, C: comfortable
  Shard D:       overloaded, dropped requests, timeouts
  
  FIX 1: Key spreading — append a random suffix (0-99),
          so celebrity_post_id_47 reads from 100 shards.
          
  FIX 2: Read replicas — many copies of the hot shard.
  
  FIX 3: Cache layer (Redis) absorbs reads before DB.
```

Hot keys are invisible during development (your test traffic is uniform) and catastrophic in production (real traffic is never uniform). An L6 engineer asks "what are my hottest keys?" before choosing a database.

#### Latency SLAs: p50, p95, p99 — Why Averages Lie

When someone says "our database query takes 10ms on average," that number is nearly useless for capacity planning. The **average** (or mean) hides the most important information: how bad are the worst cases?

**Percentiles** give you the full picture:

- **p50** (median): 50% of requests are faster than this. This is what a "typical" user experiences.
- **p95**: 95% of requests are faster than this. 1 in 20 users is slower.
- **p99**: 99% of requests are faster than this. 1 in 100 users is slower.
- **p999**: 99.9% of requests are faster than this. 1 in 1000 users is slower — but at 10,000 requests/second, that's 10 users per second having a terrible experience.

```
  LATENCY DISTRIBUTION EXAMPLE:

  Request latency histogram (each * = 1000 requests):
  
  0-5ms    | ****************************  (28,000 requests)
  5-10ms   | ********************          (20,000 requests)
  10-20ms  | *******                       (7,000 requests)
  20-50ms  | **                            (2,000 requests)
  50-100ms | *                             (1,000 requests)
  100ms+   |                               (500 requests... but users FEEL these)
  
  Average: ~8ms   (looks fine!)
  p50:     ~6ms   (typical user is fine)
  p95:     ~35ms  (borderline)
  p99:     ~80ms  (sluggish)
  p999:    ~200ms (terrible for those users)
  
  The AVERAGE told you nothing about the 500 users
  experiencing >100ms. In a database, these outliers
  are almost always caused by:
    - Lock contention (another transaction holds a lock)
    - Garbage collection pause (JVM-based databases)
    - Cache misses forcing a cold disk read
    - Compaction I/O (LSM-tree databases)
```

**Why averages lie in service chains:** In a microservices architecture, a single user request typically calls 5-10 downstream services. If each service has a p99 latency of 50ms and they are called sequentially, the probability that the *overall* request hits at least one slow response is: `1 - (0.99)^10 = 9.6%`. Nearly 1 in 10 users experiences a slow request even though each service individually has a 99% success rate. This is called **tail latency amplification**.

#### Query Flexibility: Will Access Patterns Change?

This is the question most architects forget. Access patterns are not static. A product that starts with "find users by email" might later need "find all users who signed up in the last 7 days" or "find users whose profiles mention a specific city."

**Relational databases are flexible.** You can add an index on any column. You can write arbitrary SQL queries without changing the schema. If your access patterns will evolve — and they almost always do — PostgreSQL gives you enormous flexibility.

**NoSQL databases are inflexible by design.** DynamoDB requires you to define your primary key structure up front. Adding a new query pattern often requires creating a **Global Secondary Index** (GSI) — which doubles your storage costs and write costs — or maintaining a separate table that mirrors the data in a different key order. If you get the key structure wrong, you may need to migrate the entire table.

The rule: **the more uncertain your future access patterns, the more you should lean toward a relational database.** Flexibility has a performance cost, but that cost is usually worth paying early in a product's life.

---

### Step 3: Understand Your Constraints

Once you understand your data and access patterns, you need to understand the non-negotiable constraints that will rule out certain options entirely.

#### Consistency Requirements: ACID vs Eventual

**ACID** stands for Atomicity, Consistency, Isolation, Durability. It is the set of guarantees that relational databases provide for transactions. ACID means: if you write something and immediately read it back, you will get what you wrote. Multiple operations either all succeed or all fail together. Your data will never be in a logically impossible state. (ACID is covered in exhaustive detail in Section 4 of this chapter.)

**Eventual consistency** means: after a write, you will *eventually* see the new value — but for some period of time (usually milliseconds to seconds, occasionally longer), different clients may see different values. Eventual consistency is the natural behavior of distributed systems where data is replicated across multiple machines and those replicas need time to synchronize.

The critical question is: **what does your business actually need?**

```
  CONSISTENCY REQUIREMENT EXAMPLES:

  NEEDS STRONG CONSISTENCY (ACID):
  ┌─────────────────────────────────────────────────────────┐
  │  Bank transfer: debit one account, credit another.      │
  │  These MUST be atomic. A failure mid-transfer cannot    │
  │  leave money in limbo.                                  │
  │                                                         │
  │  Inventory reservation: two users cannot both buy       │
  │  the last item. One transaction must win; the other     │
  │  must see the item as gone.                             │
  │                                                         │
  │  Authentication: a user who just changed their          │
  │  password must not be able to log in with the old one.  │
  └─────────────────────────────────────────────────────────┘

  CAN TOLERATE EVENTUAL CONSISTENCY:
  ┌─────────────────────────────────────────────────────────┐
  │  Social media like counts: if a post shows 1,203        │
  │  likes for 200ms before updating to 1,204, nobody       │
  │  is harmed.                                             │
  │                                                         │
  │  Shopping cart: if a cart shows slightly stale          │
  │  product availability, the checkout step will           │
  │  catch the conflict.                                    │
  │                                                         │
  │  DNS records: propagation takes minutes globally.       │
  │  The internet accepts this.                             │
  └─────────────────────────────────────────────────────────┘
```

The mistake most engineers make is defaulting to "eventual consistency is fine" without actually checking whether their business logic requires strong consistency. Transferring money requires atomicity. Reserving seats at a concert requires strong consistency. Posting a tweet does not.

#### Availability Requirements: Can You Tolerate Downtime?

**Availability** is the percentage of time a system is accepting requests. "Five nines" (99.999%) availability means less than 5.26 minutes of downtime per year.

Higher availability typically requires more replicas, which introduces **replication lag** and weakens consistency guarantees (CAP theorem — covered in depth in Chapter 29). The trade-off is fundamental.

For your database choice: a single-node PostgreSQL instance offers roughly 99.9% availability (about 8 hours of downtime per year, mostly for maintenance). PostgreSQL with streaming replication and automatic failover (using Patroni) can reach 99.99%. Globally distributed databases like CockroachDB or Spanner are designed for 99.999% but at significant cost and complexity.

Before demanding five-nines for your database, ask: does your entire application stack actually achieve five-nines? If your application servers are 99.9% available, there is no point making your database 99.999% available — the bottleneck is elsewhere.

#### Scale Requirements: The 10x Problem

Every system starts small. The question is: what does the system look like at 10x your current scale?

This matters because some databases scale vertically easily (bigger machine) while others scale horizontally naturally (more machines). Adding a bigger machine (**vertical scaling** or "scaling up") is always easier operationally — no data re-partitioning, no distributed coordination, no eventual consistency. But it has a hard ceiling: the largest available EC2 instance has a finite amount of RAM and CPU.

Horizontal scaling (**sharding** or "scaling out") removes the ceiling but adds enormous complexity. Distributed transactions, resharding, hotspot detection, cross-shard queries — these are hard engineering problems.

```
  SCALE DECISION TREE:
  
  Current load: 10,000 requests/sec
  
  3-year projection: 100,000 req/sec (10x)
  
  ┌──────────────────────────────────────────────────────┐
  │  Can a single large machine handle 100k req/sec?     │
  │  (rule of thumb: PostgreSQL on a 96-core, 768GB RAM  │
  │   machine can handle ~50k-100k simple queries/sec)   │
  └──────────────────────────────┬───────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                   YES                        NO
                    │                          │
                    v                          v
           Stay single-node.         Consider sharding or
           Much simpler.             a distributed DB.
           Vertical scale first.     CockroachDB, Vitess,
                                     Cassandra, DynamoDB.
```

The L6 insight here is: **prefer the simplest architecture that plausibly handles 3-year projections.** Do not shard preemptively. Every premature shard is complexity you are paying for today that you might not need for years.

#### Team Expertise and Operational Cost

A perfect database that your team does not know how to operate is not a perfect database. It is a time bomb.

Cassandra is an excellent database for high-write-throughput use cases. It is also notoriously difficult to operate. Tombstone management, compaction tuning, token range management, anti-entropy repair — these require deep operational expertise. If your team has two backend engineers and zero Cassandra experience, choosing Cassandra means one of those engineers will spend months learning Cassandra operations instead of building product.

**Managed databases** (AWS RDS, Cloud Spanner, Atlas MongoDB) shift operational burden to the cloud provider. You pay a premium (typically 2-3x the cost of self-managed), but you get automatic backups, automatic failover, automatic version upgrades, and automatic scaling. For most companies, this premium is absolutely worth it.

**Self-hosted databases** give you maximum control and minimum cost per unit. They are appropriate when: (a) your scale is large enough that cloud premiums cost millions of dollars per year, (b) regulatory requirements demand on-premises hosting, or (c) you have a dedicated DBA team.

#### Budget: Managed vs Self-Hosted

```
  ROUGH COST COMPARISON (2024 estimates):

  Workload: 10k req/sec, 500GB data, single region
  
  ┌──────────────────┬──────────────────┬──────────────────┐
  │  Option          │  Monthly Cost    │  Operational Load│
  ├──────────────────┼──────────────────┼──────────────────┤
  │  AWS RDS         │  ~$800-2,000     │  Very low        │
  │  (managed PG)    │                  │  (AWS manages it)│
  ├──────────────────┼──────────────────┼──────────────────┤
  │  Self-hosted PG  │  ~$300-600       │  High (you manage│
  │  on EC2          │  (EC2 costs only)│   backups, HA,   │
  │                  │                  │   upgrades)      │
  ├──────────────────┼──────────────────┼──────────────────┤
  │  Aurora          │  ~$1,500-3,000   │  Very low;       │
  │  (managed, HA)   │                  │  auto-scale,     │
  │                  │                  │  built-in HA     │
  ├──────────────────┼──────────────────┼──────────────────┤
  │  DynamoDB        │  ~$500-1,500     │  Low; serverless;│
  │  (on-demand)     │  (highly workload│  but key design  │
  │                  │   dependent)     │  is on you       │
  └──────────────────┴──────────────────┴──────────────────┘
  
  Key insight: engineer time costs $150-250/hour at L5+.
  If self-hosting requires 10 hours/month of ops work,
  that's $1,500-2,500/month in hidden cost that doesn't
  appear on the AWS bill.
```

---

### Step 4: Plan Your Evolution Path

Databases are not permanent. The database that is right for your product in Year 1 may be completely wrong in Year 3. Understanding this upfront changes how you design your system.

#### Databases That Are Right Now May Be Wrong Later

Here is a common trajectory:

- **Year 1**: You have 10,000 users. PostgreSQL handles everything. Simple, reliable, easy to query.
- **Year 2**: You have 1 million users. You add a read replica to handle read traffic. PostgreSQL still works.
- **Year 3**: You have 50 million users and your database has 2 TB of data. Range queries are slow. You add indexes. Indexes slow down writes. Write latency climbs. You realize you need to shard — but PostgreSQL doesn't shard natively.

At Year 3, you face a painful migration. The question is: could you have designed Year 1 in a way that makes Year 3 easier?

**The answer is often yes, with one key principle: separate your data by access pattern early, even if everything lives in the same database initially.**

If your user profiles (read-heavy, point lookups) and your activity feed (write-heavy, time-series range scans) are in the same PostgreSQL instance, migrating them later requires untangling two things at once. If they are in separate tables with a clear interface boundary, you can migrate the activity feed to a time-series database independently without touching user profiles.

#### Design for Migration, Not Just Selection

The practical application of this principle is to **wrap your database access in a repository layer** — a module that owns all queries to a particular data type. Your business logic never calls the database directly. It calls `UserRepository.findById(42)`, not `SELECT * FROM users WHERE id = 42`.

Why does this matter for database evolution? Because when you decide to move users from PostgreSQL to DynamoDB, you change one file — the UserRepository implementation — not 200 files scattered across your codebase that all contained raw SQL.

```
  WITHOUT REPOSITORY PATTERN:
  
  UserService.java       --> SELECT * FROM users WHERE id = ?
  AuthService.java       --> SELECT * FROM users WHERE email = ?
  BillingService.java    --> SELECT plan FROM users WHERE id = ?
  NotifService.java      --> SELECT email FROM users WHERE id = ?
  
  To migrate DB: touch all 4 files (and many more in reality)
  
  
  WITH REPOSITORY PATTERN:
  
  UserService.java       --> UserRepository.findById(id)
  AuthService.java       --> UserRepository.findByEmail(email)
  BillingService.java    --> UserRepository.getPlan(id)
  NotifService.java      --> UserRepository.getEmail(id)
        |
        v
  UserRepository.java    --> [all SQL in one place]
  
  To migrate DB: touch UserRepository.java only
```

#### The Cost of Database Lock-In

**Database lock-in** means your application has accumulated so many database-specific features — stored procedures, triggers, proprietary SQL extensions, vendor-specific data types — that migrating to a different database is effectively impossible without a full rewrite.

Lock-in is not always bad. PostgreSQL's JSONB, its full-text search, its PostGIS geographic extension — these are genuinely superior to vendor-neutral alternatives. Using them makes your application better. The cost is that switching away from PostgreSQL becomes very expensive.

The L6 framing: **consciously accept lock-in for features that provide genuine value; refuse it for features that don't.** Using PostgreSQL's JSONB because it eliminates a whole service tier is a good trade. Using a stored procedure for something you could handle in application code just because it's convenient is buying lock-in cheaply.

---

## 3. Database Internals: B-Tree vs LSM-Tree

Most engineers use databases as black boxes. They send queries in; results come out. But understanding what is happening inside the database allows you to predict performance, diagnose anomalies, and make better architectural decisions. The two dominant storage engine designs are **B-Trees** and **Log-Structured Merge Trees (LSM-Trees)**.

### B-Tree: The Read-Optimized Classic

A **B-Tree** (the B stands for "balanced," not "binary") is a self-balancing tree data structure that keeps data sorted and allows searches, insertions, and deletions in O(log N) time. PostgreSQL, MySQL/InnoDB, SQLite, and most traditional relational databases use B-Trees for their primary indexes.

#### How B-Trees Work

Think of a B-Tree as an index in a book. The index has multiple levels. The top level contains a small number of high-level entries ("A-F", "G-M", "N-Z"). Each of those points to a mid-level section. Each of those points to a page containing the actual content.

In a database B-Tree, the structure is:

- **Root node**: A single page that is always in memory. Contains pointers to child nodes.
- **Internal nodes**: Pages that contain only keys and pointers — no actual row data. Used purely for navigation.
- **Leaf nodes**: Pages that contain the actual row data (or pointers to row data on the heap).
- **Leaf pages are linked**: Every leaf page has a pointer to the next leaf page. This is what makes range scans efficient — you find the start of the range and walk the linked list.

```
  B-TREE STRUCTURE (simplified, order 3):

                      ┌───────────┐
                      │  ROOT     │
                      │  [50|80]  │
                      └─────┬─────┘
              ┌─────────────┼─────────────┐
              v             v             v
         ┌────────┐    ┌────────┐    ┌────────┐
         │[10|30] │    │[60|70] │    │[85|95] │
         └──┬─┬─┬─┘    └──┬─┬─┬─┘    └──┬─┬─┬─┘
           ...            ...            ...
            
  Leaf level (actual data, linked list left-to-right):
  
  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
  │ 1  Ana  │-->│ 30 Bob  │-->│ 60 Carl │-->│ 85 Dana │
  │ 5  Ed   │   │ 42 Faye │   │ 71 Greg │   │ 90 Hana │
  │ 10 Ivan │   │ 50 Jane │   │ 80 Kim  │   │ 95 Lena │
  └─────────┘   └─────────┘   └─────────┘   └─────────┘
  
  Each box = one page on disk (~8KB or ~16KB)
  
  Read path for id=42:
  1. Root: 42 < 50, go left child
  2. [10|30]: 42 > 30, go right child
  3. Leaf: scan page, find id=42, return row
  
  Total: 3 page reads = 3 disk I/Os
```

#### Why Reads Are Fast in B-Trees

B-Trees store data in sorted order on disk, which means:
- Point lookups walk the tree in O(log N) time — typically 3-5 page reads even for tables with millions of rows
- Range scans find the start of the range and walk the linked leaf pages — no random I/O within the range
- The root and upper levels fit in the OS buffer cache (they are read extremely frequently), so in practice only leaf-level pages require disk I/O

#### The Write Amplification Problem in B-Trees

Every write to a B-Tree must update a leaf page in place. If that page is full, the database must **split** the page (create two pages and update the parent's pointer), which may cause the parent to split, cascading all the way to the root. This process is called a **page split** and requires multiple disk writes for a single logical write.

**Write amplification** is the ratio of bytes written to disk per byte of logical data written. A B-Tree typically has a write amplification factor of 3-10x — meaning writing 1KB of user data causes 3-10KB of actual disk writes.

For write-heavy workloads, this is expensive. Each write must also update the **Write-Ahead Log** (WAL, explained in Section 4), adding further write overhead.

```
  B-TREE WRITE PATH:

  Application writes: INSERT INTO users VALUES (55, 'Mia')
  
  1. Database writes to WAL (for durability)           [1 write]
  2. Locate correct leaf page in B-tree                [read]
  3. If page has space: update page in-place           [1 write]
  4. If page is FULL: split page, update parent        [2-3 writes]
  5. If parent is full: cascade up...                  [more writes]
  
  For random key inserts into a large B-tree,
  almost every insert hits a different leaf page.
  This causes RANDOM writes scattered across the disk.
  HDDs handle random writes poorly. Even SSDs degrade
  with sustained random writes (write amplification
  wears flash cells faster).
```

---

### LSM-Tree: The Write-Optimized Alternative

**Log-Structured Merge Trees (LSM-Trees)** were invented to solve exactly the random-write problem of B-Trees. They are used in Cassandra, RocksDB (which powers dozens of databases including MyRocks, TiKV, and Flink state backends), LevelDB, InfluxDB, and Apache HBase.

The core insight of an LSM-Tree is: **never update data in place. Only append. Writes are always sequential, which is dramatically faster on both HDDs and SSDs.**

#### How LSM-Trees Work

An LSM-Tree has three main components:

**MemTable**: An in-memory write buffer. Every write goes here first. The MemTable is usually a sorted data structure (like a red-black tree or skip list) so that data inside it is ordered by key.

**SSTables** (Sorted String Tables): Immutable files on disk. When the MemTable fills up (typically when it reaches a few MB), it is flushed to disk as an SSTable. Once written, an SSTable is never modified — only read or deleted.

**Compaction**: Because writes only append, deleted or updated data accumulates as "old versions" across SSTables. Compaction merges SSTables together, discarding obsolete versions and maintaining key ordering.

```
  LSM-TREE WRITE PATH:

  Step 1: Write goes to MemTable (in-memory, sorted)
  
  MemTable:
  ┌─────────────────────────────┐
  │ key=5  val="Bob"  ts=1001   │
  │ key=12 val="Ana"  ts=1002   │  (sorted by key)
  │ key=30 val="Carl" ts=1003   │
  └─────────────────────────────┘
  
  Step 2: MemTable is FULL → flush to L0 SSTable
  
  L0 SSTables (one per flush):
  ┌────────────┐  ┌────────────┐  ┌────────────┐
  │ SST-001    │  │ SST-002    │  │ SST-003    │
  │ k5,k12,k30 │  │ k2,k8,k25  │  │ k5,k15,k30 │
  │ (immutable)│  │ (immutable)│  │(newer vals)│
  └────────────┘  └────────────┘  └────────────┘
  NOTE: k5 and k30 appear in both SST-001 and SST-003.
  SST-003 has the newer version.
  
  Step 3: COMPACTION — merge and deduplicate
  
  L1 SSTable (after compaction):
  ┌─────────────────────────────────────────┐
  │ k2,k5(new),k8,k12,k15,k25,k30(new)     │
  │ (sorted, deduplicated, older vals gone) │
  └─────────────────────────────────────────┘
  
  All writes are SEQUENTIAL (appends). No random I/O.
```

#### Compaction Strategies

There are two main compaction strategies, and choosing between them is a real operational decision.

**Size-Tiered Compaction** (default in Cassandra): When N SSTables of similar size accumulate, merge them into one larger SSTable. This produces fewer write amplification during compaction but results in multiple large SSTables that all need to be checked during reads.

**Leveled Compaction** (default in RocksDB/LevelDB): SSTables are organized into levels (L0, L1, L2...). Each level is 10x larger than the previous. An SSTable is only promoted to the next level when it contains enough data. Within each level (except L0), key ranges do not overlap — each key exists in exactly one SSTable per level. This makes reads faster (you know exactly which SSTable to check) but increases write amplification during compaction.

```
  LEVELED COMPACTION:
  
  L0: [0-100] [50-150] [80-200]   (may overlap, newly flushed)
       |
       | compaction: merge L0 SSTables into L1
       v
  L1: [0-33] [34-67] [68-100] [101-133]...  (no overlap, sorted)
       |                                     (~10MB total)
       | compaction: merge L1 into L2
       v
  L2: (no overlap, sorted)                  (~100MB total)
  L3: (no overlap, sorted)                  (~1GB total)
  
  Reading key=75:
  - Check L0 (may need to check all 3 SSTables)
  - Check exactly 1 SSTable in L1
  - Check exactly 1 SSTable in L2
  - Much more predictable than size-tiered
```

#### The Read Path: MemTable → Bloom Filter → SSTables

Reading from an LSM-Tree is more complex than reading from a B-Tree because the data you want might be in the MemTable, in L0, in L1, or in L2 — and you don't know which.

The read path:

1. **Check the MemTable** (in-memory — fast)
2. **Check Bloom filters** for each SSTable (see below)
3. **Check SSTables** from newest to oldest, stopping when you find the key

Without an optimization, step 3 would require reading every SSTable on disk — catastrophically slow. **Bloom filters** are the solution.

#### Bloom Filters: The Key to LSM-Tree Read Performance

A **Bloom filter** is a probabilistic data structure that answers the question: "Is this key definitely NOT in this SSTable?" with 100% accuracy, but answers "Is this key in this SSTable?" with a small probability of false positives.

Think of it this way: each SSTable has a Bloom filter — a small bit array in memory. When an SSTable is created, every key in it is hashed multiple times, and the corresponding bits in the array are set to 1. To check whether a key is in the SSTable, you hash the key multiple times and check whether all the corresponding bits are 1. If any bit is 0, the key is definitely not in this SSTable. If all bits are 1, the key is probably in the SSTable (with a small false positive rate, typically 1%).

```
  BLOOM FILTER EXAMPLE (simplified):
  
  SSTable contains keys: {5, 12, 30}
  Bit array (10 bits): [0,0,0,0,0,0,0,0,0,0]
  
  Hash key=5:  hash1(5)=2, hash2(5)=7
    Set bits 2 and 7: [0,0,1,0,0,0,0,1,0,0]
  
  Hash key=12: hash1(12)=1, hash2(12)=5
    Set bits 1 and 5: [0,1,1,0,0,1,0,1,0,0]
  
  Hash key=30: hash1(30)=3, hash2(30)=7
    Set bits 3 and 7: [0,1,1,1,0,1,0,1,0,0]
  
  Final filter:        [0,1,1,1,0,1,0,1,0,0]
  
  Query: Is key=99 in this SSTable?
    hash1(99)=4 → bit 4 = 0 → DEFINITELY NOT HERE, skip!
    (Saved a disk read!)
  
  Query: Is key=12 in this SSTable?
    hash1(12)=1 → bit 1 = 1
    hash2(12)=5 → bit 5 = 1
    ALL bits set → probably yes, go read the SSTable
    (May occasionally be a false positive, but that's OK —
     we just do one unnecessary disk read, not a wrong answer)
```

Bloom filters are stored entirely in memory and are tiny (10-20 bits per key). For an SSTable with 1 million keys, the Bloom filter is only ~2.5MB — vastly smaller than the SSTable itself (potentially hundreds of MB). The result: LSM-Trees can skip 99%+ of SSTable reads for keys that don't exist in a given file.

---

### B-Tree vs LSM-Tree: Analytical Comparison

```
  B-TREE vs LSM-TREE — HEAD TO HEAD:

  ┌─────────────────────┬──────────────────────┬──────────────────────┐
  │  Dimension          │  B-Tree              │  LSM-Tree            │
  ├─────────────────────┼──────────────────────┼──────────────────────┤
  │  Write performance  │  Moderate            │  Excellent           │
  │                     │  Random in-place     │  Sequential append   │
  │                     │  writes              │  always              │
  ├─────────────────────┼──────────────────────┼──────────────────────┤
  │  Read performance   │  Excellent for       │  Good with Bloom     │
  │                     │  point lookups       │  filters; worse for  │
  │                     │  and range scans     │  range scans         │
  ├─────────────────────┼──────────────────────┼──────────────────────┤
  │  Write amplification│  3-10x               │  10-30x (compaction) │
  ├─────────────────────┼──────────────────────┼──────────────────────┤
  │  Read amplification │  Low (tree height    │  Higher (check       │
  │                     │  + 1 heap fetch)     │  multiple levels)    │
  ├─────────────────────┼──────────────────────┼──────────────────────┤
  │  Space overhead     │  ~1.5-2x data size   │  ~2-4x during        │
  │                     │  (page fragmentation)│  compaction          │
  ├─────────────────────┼──────────────────────┼──────────────────────┤
  │  Compaction pauses  │  None                │  Yes: compaction     │
  │                     │                      │  competes for I/O    │
  │                     │                      │  with reads/writes   │
  ├─────────────────────┼──────────────────────┼──────────────────────┤
  │  Best for           │  OLTP, mixed reads   │  Write-heavy, time-  │
  │                     │  and writes, range   │  series, event logs, │
  │                     │  scans, low latency  │  wide-column stores  │
  ├─────────────────────┼──────────────────────┼──────────────────────┤
  │  Examples           │  PostgreSQL, MySQL,  │  Cassandra, RocksDB, │
  │                     │  SQLite, Oracle      │  HBase, InfluxDB,    │
  │                     │                      │  LevelDB             │
  └─────────────────────┴──────────────────────┴──────────────────────┘
```

---

## 4. ACID Deep Dive

ACID is one of the most misunderstood sets of acronyms in computer science. Engineers casually say "we need ACID" or "ACID is too slow" without understanding what they are actually asking for or giving up. Let us go through each property with real examples.

### Atomicity: All or Nothing

**Atomicity** means that a transaction is treated as a single, indivisible unit. Either all of its operations succeed, or none of them do. There is no partial success.

The canonical example is a bank transfer:

```sql
BEGIN TRANSACTION;
  UPDATE accounts SET balance = balance - 100 WHERE id = 'Alice';
  UPDATE accounts SET balance = balance + 100 WHERE id = 'Bob';
COMMIT;
```

Imagine the database crashes after the first UPDATE but before the second. Without atomicity, Alice has $100 less but Bob never received it. The money has vanished from the universe. This is a catastrophic data integrity failure.

With atomicity, the database uses a **Write-Ahead Log** (WAL, covered below) to track which transactions are in progress. On recovery after a crash, the database replays the WAL and either completes (rolls forward) or undoes (rolls back) any transaction that was mid-flight at crash time.

```
  ATOMIC TRANSACTION — CRASH RECOVERY:
  
  Timeline:
  t=0:  BEGIN TRANSACTION
  t=1:  UPDATE Alice: -$100  (written to WAL, not yet committed)
  t=2:  UPDATE Bob:   +$100  (written to WAL, not yet committed)
  t=3:  ** DATABASE CRASHES **
  
  On restart:
  WAL shows: transaction T1 started at t=0
             T1 operations written at t=1, t=2
             T1 never committed (no COMMIT record in WAL)
  
  Database rolls back T1:
  → Alice's balance is restored
  → Bob's balance is unchanged
  
  User sees: transaction failed. They retry.
  Money is never lost.
```

### Consistency: Not What You Think

**Consistency** in ACID is commonly misunderstood because the word "consistency" also appears in the CAP theorem (and means something entirely different there).

In ACID, consistency means: **the database moves from one valid state to another valid state.** Valid means satisfying all constraints, rules, and invariants you have defined in the schema.

Examples of consistency constraints:
- A bank account balance cannot go negative (enforced by a CHECK constraint)
- An order cannot reference a non-existent product (enforced by a FOREIGN KEY constraint)
- A username must be unique (enforced by a UNIQUE constraint)

**Important**: ACID consistency is largely the application's responsibility to define. The database enforces whatever constraints you told it to enforce. If you forget to add a FOREIGN KEY constraint, the database will happily let you create orphaned records — and you will say "but I'm using PostgreSQL, it's ACID!" The A, I, and D are the database's job. The C is partly yours.

This is why C is sometimes considered the "weakest" of the ACID properties — it is conditional on the programmer having correctly defined their invariants.

### Isolation: The Hardest One to Get Right

**Isolation** means that concurrently executing transactions should appear to run serially — as if one happened before the other, not simultaneously. In practice, true serial execution is too slow (it would mean one transaction at a time on the entire database), so databases provide different **isolation levels** that trade off between correctness and performance.

There are four standard isolation levels, each protecting against a different class of concurrency anomaly.

#### Concurrency Anomalies

To understand isolation levels, you first need to understand the anomalies they prevent.

**Dirty read**: Transaction A reads data that Transaction B has written but not yet committed. If B later rolls back, A has read data that never officially existed.

```
  DIRTY READ:
  
  Time  Transaction A               Transaction B
  ─────────────────────────────────────────────────
  t=1                               BEGIN
  t=2                               UPDATE balance = 200  (was 100)
  t=3   BEGIN
  t=4   SELECT balance              (reads 200 -- the uncommitted value)
  t=5                               ROLLBACK  (balance reverts to 100)
  t=6   A acts on balance=200...    (A has a dirty read -- 200 never existed officially)
```

**Non-repeatable read**: Transaction A reads a row. Transaction B modifies and commits that row. Transaction A reads the row again and gets a different value. Within a single transaction, the same query returns different results.

```
  NON-REPEATABLE READ:
  
  Time  Transaction A               Transaction B
  ─────────────────────────────────────────────────
  t=1   BEGIN
  t=2   SELECT price WHERE id=1     (gets 10.00)
  t=3                               UPDATE price = 12.00 WHERE id=1; COMMIT
  t=4   SELECT price WHERE id=1     (gets 12.00 -- different from t=2!)
  t=5   COMMIT
  
  A expected to see a consistent price within its transaction.
  It didn't.
```

**Phantom read**: Transaction A queries for rows matching a condition. Transaction B inserts a new row matching that condition. Transaction A re-runs the query and gets a new row that wasn't there before.

```
  PHANTOM READ:
  
  Time  Transaction A               Transaction B
  ─────────────────────────────────────────────────
  t=1   BEGIN
  t=2   SELECT COUNT(*) WHERE       (gets 5)
        dept='Engineering'
  t=3                               INSERT new engineer; COMMIT
  t=4   SELECT COUNT(*) WHERE       (gets 6 -- phantom row!)
        dept='Engineering'
  t=5   COMMIT
  
  A is seeing a "phantom" row that wasn't there
  at the start of its transaction.
```

#### The Four Isolation Levels

```
  ISOLATION LEVELS AND ANOMALY PROTECTION:

  ┌──────────────────────┬────────────┬──────────────────┬────────────────┐
  │  Isolation Level     │ Dirty Read │ Non-Repeatable   │ Phantom Read   │
  │                      │            │ Read             │                │
  ├──────────────────────┼────────────┼──────────────────┼────────────────┤
  │  READ UNCOMMITTED    │  Possible  │  Possible        │  Possible      │
  │  (weakest)           │            │                  │                │
  ├──────────────────────┼────────────┼──────────────────┼────────────────┤
  │  READ COMMITTED      │  Prevented │  Possible        │  Possible      │
  │  (default in PG,     │            │                  │                │
  │   Oracle, SQL Server)│            │                  │                │
  ├──────────────────────┼────────────┼──────────────────┼────────────────┤
  │  REPEATABLE READ     │  Prevented │  Prevented       │  Possible      │
  │  (default in MySQL)  │            │                  │                │
  ├──────────────────────┼────────────┼──────────────────┼────────────────┤
  │  SERIALIZABLE        │  Prevented │  Prevented       │  Prevented     │
  │  (strongest)         │            │                  │  (all anomalies│
  │                      │            │                  │   prevented)   │
  └──────────────────────┴────────────┴──────────────────┴────────────────┘
  
  Trade-off: stronger isolation = more locking = lower throughput.
  
  PostgreSQL's default (READ COMMITTED) prevents dirty reads.
  For financial transactions, you typically want SERIALIZABLE.
  For a social media feed, READ COMMITTED is perfectly fine.
```

**How isolation is implemented:**

- **Lock-based concurrency control**: Transactions hold locks on rows or pages they have read or written. Other transactions must wait. Simple but can deadlock.
- **Multi-Version Concurrency Control (MVCC)**: Used by PostgreSQL and MySQL (InnoDB). When a row is updated, the database keeps the old version alongside the new version. Readers see the snapshot of the database as it was at their transaction's start time. This allows readers and writers to proceed simultaneously without blocking each other. MVCC is why PostgreSQL's READ COMMITTED is fast — reads never wait for writes.

### Durability: Write-Ahead Logging

**Durability** means: once a transaction is committed, it stays committed — even if the database crashes immediately after. The data is on durable storage.

The mechanism that makes this possible is the **Write-Ahead Log (WAL)**.

The rule is simple but profound: **before any change is made to a data page on disk, that change must first be recorded in the WAL.** Hence "write-ahead" — you write to the log ahead of modifying the actual data.

```
  WRITE-AHEAD LOG (WAL) STRUCTURE:

  WAL (append-only log on disk):
  ┌─────────────────────────────────────────────────────────┐
  │ LSN 1001: BEGIN  TXN-42                                 │
  │ LSN 1002: UPDATE accounts SET balance=900 WHERE id=1   │
  │           (old value: 1000, new value: 900)             │
  │ LSN 1003: UPDATE accounts SET balance=600 WHERE id=2   │
  │           (old value: 500, new value: 600)              │
  │ LSN 1004: COMMIT TXN-42                                 │
  └─────────────────────────────────────────────────────────┘
  LSN = Log Sequence Number (monotonically increasing)
  
  On COMMIT:
  1. WAL record (LSN 1004) is flushed to disk (fsync)
  2. "OK" is returned to the client
  3. Data pages are updated in the background
     (buffered in memory, written to disk asynchronously)
  
  If crash happens BEFORE LSN 1004 is written:
  → On recovery: no COMMIT found for TXN-42 → roll back
  
  If crash happens AFTER LSN 1004 is written:
  → On recovery: COMMIT found → re-apply changes from WAL
    (because data pages may not have been written yet)
  
  Result: committed data is NEVER lost.
```

WAL has a secondary benefit: **replication**. PostgreSQL streaming replication works by shipping WAL records from the primary to replicas. Replicas replay the WAL records to stay in sync. This means any database that supports WAL-based replication is getting both durability and high availability from the same mechanism.

---

## 5. L5 vs L6 Decision Table

This table shows eight realistic interview scenarios and contrasts how an L5 engineer (senior) and an L6 engineer (staff) approach the database decision. The difference is almost never about knowing more technology. It is about asking better questions.

```
  L5 vs L6 THINKING — 8 SCENARIOS:

  ┌────┬─────────────────────────┬──────────────────────────┬─────────────────────────────┐
  │ #  │  Scenario               │  L5 Answer               │  L6 Answer                  │
  ├────┼─────────────────────────┼──────────────────────────┼─────────────────────────────┤
  │ 1  │  "Build a social        │  "PostgreSQL for users,  │  "What's the read:write     │
  │    │   network — store       │   Redis for sessions"    │  ratio on post lookups?     │
  │    │   users and posts."     │                          │  Are we doing feed          │
  │    │                         │                          │  generation or point        │
  │    │                         │                          │  lookups? Fan-out-on-write  │
  │    │                         │                          │  vs fan-out-on-read changes │
  │    │                         │                          │  the entire data model."    │
  ├────┼─────────────────────────┼──────────────────────────┼─────────────────────────────┤
  │ 2  │  "Store 10 billion      │  "Cassandra — it handles │  "What queries will you     │
  │    │   IoT sensor readings." │   writes well."          │  run? Time-range per device?│
  │    │                         │                          │  Aggregates across devices? │
  │    │                         │                          │  If time-range per device,  │
  │    │                         │                          │  Cassandra with device_id   │
  │    │                         │                          │  partition key. If cross-   │
  │    │                         │                          │  device aggregates,         │
  │    │                         │                          │  InfluxDB or Druid."        │
  ├────┼─────────────────────────┼──────────────────────────┼─────────────────────────────┤
  │ 3  │  "Build a real-time     │  "Redis Sorted Sets for  │  "How many leaderboard      │
  │    │   game leaderboard."    │   rankings."             │  users? 10k vs 100M changes │
  │    │                         │                          │  everything. At 100M,       │
  │    │                         │                          │  approximate top-K with     │
  │    │                         │                          │  probabilistic counting.    │
  │    │                         │                          │  Do you need exact rank     │
  │    │                         │                          │  for all users or just      │
  │    │                         │                          │  top-1000?"                 │
  ├────┼─────────────────────────┼──────────────────────────┼─────────────────────────────┤
  │ 4  │  "Store product         │  "MongoDB — flexible     │  "How many distinct         │
  │    │   catalog with varied   │   schema is perfect."    │  attribute types?           │
  │    │   attributes."          │                          │  PostgreSQL JSONB handles   │
  │    │                         │                          │  semi-structured data well  │
  │    │                         │                          │  and you keep ACID. MongoDB │
  │    │                         │                          │  only makes sense if you    │
  │    │                         │                          │  need document-level        │
  │    │                         │                          │  atomicity across deeply    │
  │    │                         │                          │  nested structures."        │
  ├────┼─────────────────────────┼──────────────────────────┼─────────────────────────────┤
  │ 5  │  "Design payment        │  "PostgreSQL with         │  "Same, but let's talk      │
  │    │   processing."          │   transactions."          │  isolation level. You need  │
  │    │                         │                          │  SERIALIZABLE for balance   │
  │    │                         │                          │  checks and REPEATABLE READ │
  │    │                         │                          │  is not enough — phantom    │
  │    │                         │                          │  reads can cause double-    │
  │    │                         │                          │  spend bugs. Also: idempot- │
  │    │                         │                          │  ency keys at the app layer │
  │    │                         │                          │  to handle retries."        │
  ├────┼─────────────────────────┼──────────────────────────┼─────────────────────────────┤
  │ 6  │  "Multi-region system   │  "Use DynamoDB —          │  "First: does the product   │
  │    │   for a global app."    │   it's globally           │  actually need multi-region │
  │    │                         │   distributed."          │  WRITES or just read        │
  │    │                         │                          │  replicas? Read replicas    │
  │    │                         │                          │  + one write region handles │
  │    │                         │                          │  95% of cases with far less │
  │    │                         │                          │  complexity. Multi-region   │
  │    │                         │                          │  writes means conflict      │
  │    │                         │                          │  resolution — what's your   │
  │    │                         │                          │  business rule when two     │
  │    │                         │                          │  regions conflict?"         │
  ├────┼─────────────────────────┼──────────────────────────┼─────────────────────────────┤
  │ 7  │  "We're migrating from  │  "Add indexes to slow     │  "Before adding indexes:    │
  │    │   MySQL, queries are    │   queries."               │  what are the actual        │
  │    │   slow."                │                          │  queries? EXPLAIN ANALYZE   │
  │    │                         │                          │  each one. Often the issue  │
  │    │                         │                          │  is N+1 query patterns or   │
  │    │                         │                          │  missing JOIN conditions,   │
  │    │                         │                          │  not missing indexes.       │
  │    │                         │                          │  Indexes on the wrong       │
  │    │                         │                          │  columns can slow writes    │
  │    │                         │                          │  without helping reads."    │
  ├────┼─────────────────────────┼──────────────────────────┼─────────────────────────────┤
  │ 8  │  "We need to store      │  "Use a graph database   │  "How many hops deep are    │
  │    │   social connections    │   like Neo4j."            │  your traversals? 1-2 hops  │
  │    │   (follower/following)."│                          │  (friend-of-friend) works   │
  │    │                         │                          │  fine in PostgreSQL with a  │
  │    │                         │                          │  self-join and the right    │
  │    │                         │                          │  indexes. Neo4j adds        │
  │    │                         │                          │  operational complexity.    │
  │    │                         │                          │  Graph DB is right at 5+    │
  │    │                         │                          │  hops or arbitrary depth    │
  │    │                         │                          │  traversals — e.g., fraud   │
  │    │                         │                          │  ring detection."           │
  └────┴─────────────────────────┴──────────────────────────┴─────────────────────────────┘
```

The pattern across all eight scenarios is the same. The L5 engineer hears the noun ("social network," "IoT," "payments") and maps it to a technology from experience. The L6 engineer treats the noun as a prompt to ask clarifying questions. L6 knows that two "social networks" can require entirely different databases depending on whether they are Twitter-style (fan-out-on-write, denormalized) or LinkedIn-style (connection traversal, graph queries).

**The L6 heuristic**: name a technology only after you can finish the sentence "I chose X specifically because this workload has [property Y], which X is optimized for, and because [alternative Z] would fail at [specific constraint W]."

---

## Key Terms Reference

| Term | Definition |
|---|---|
| **ACID** | Atomicity, Consistency, Isolation, Durability — relational DB transaction guarantees |
| **B-Tree** | Balanced tree storage structure; sorted data; fast reads and range scans |
| **Bloom filter** | Probabilistic data structure; tells you when a key is definitely NOT in a file |
| **Compaction** | LSM-Tree process that merges SSTables and discards obsolete versions |
| **Hot key** | A single key receiving disproportionate traffic; causes shard imbalance |
| **LSM-Tree** | Log-Structured Merge Tree; write-optimized; used in Cassandra, RocksDB |
| **MVCC** | Multi-Version Concurrency Control; readers don't block writers |
| **OLAP** | Online Analytical Processing; aggregate queries over large datasets |
| **OLTP** | Online Transaction Processing; point lookups and small writes; typical web app |
| **p99 latency** | 99th-percentile latency; 1 in 100 requests is slower than this |
| **SSTable** | Sorted String Table; immutable on-disk file used in LSM-Tree engines |
| **Tail latency** | The worst-case latency (p99, p999); amplifies in service chains |
| **WAL** | Write-Ahead Log; record of changes before they are applied; enables durability |
| **Write amplification** | Ratio of bytes written to disk per byte of user data; measures write efficiency |

---

*Part B continues with: Database Taxonomy Deep Dive (Relational, Document, Wide-Column, Time-Series, Graph, Vector) — when to use each, with real architecture examples.*
# Chapter 28 — Part B: Relational Databases (SQL) Deep Dive

> This is Part B of the "Databases — Choosing, Using, and Evolving Data Stores" chapter.
> Part A covered the taxonomy of databases and when to reach for which category.
> Part B goes deep on relational databases — internals, indexing, scaling, and real incidents.

---

## 1. Why Relational Databases Win (More Often Than You Think)

### The Myth That NoSQL Is "More Scalable"

This myth is one of the most persistent in software engineering, and it trips up a surprising number of engineers in L6 interviews. The story goes something like: "SQL doesn't scale, NoSQL does." The reality is more nuanced and, frankly, almost the opposite in most situations.

The confusion comes from a real historical event. In the mid-2000s, companies like Amazon, Google, and Facebook were dealing with write volumes and dataset sizes that genuinely pushed past what a single relational database could handle. Their engineers wrote papers (Dynamo, Bigtable, BigTable) describing the new systems they built. The tech press simplified these papers into "SQL is dead, NoSQL is the future."

What actually happened: those companies built NoSQL systems because they hit genuine limits — billions of users, petabytes of data, millions of writes per second. They did not abandon SQL because SQL was architecturally inferior. They built new things because they needed different tradeoffs.

Here is the uncomfortable truth: **the tradeoffs you give up with NoSQL are enormous**, and most applications never need the scale that would justify accepting those tradeoffs.

When you use a NoSQL database like DynamoDB or Cassandra, you give up:
- **Ad hoc queries** — you must design your data access patterns upfront and create tables for each query pattern
- **ACID transactions** — atomically updating two related pieces of data becomes your problem to solve in application code
- **Joins** — related data must either be denormalized (duplicated) or fetched in multiple round trips
- **Schema enforcement** — nothing stops a bug from writing malformed data into the database

None of these are free. Each one shifts complexity from the database into your application code, where it is harder to maintain, harder to test, and easier to get wrong.

### What SQL Actually Gives You That Is Hard to Replace

Think of a relational database as a **contract with the computer**. You describe your data's structure and constraints once, and the database enforces them forever, for every write, from every service, in every language.

**Foreign keys** are a perfect example. In a relational database, if you say "every order must belong to a valid user," the database will refuse to insert an order with a non-existent user_id. It does not matter which service is writing the data, which engineer wrote the code, or whether a bug slipped through code review. The database says no.

In a NoSQL system, that constraint lives in your application code. If you have five services that write orders, all five must implement that check correctly. When a new engineer joins and writes a sixth service and forgets the check, you will have orphaned orders in your database. You will discover this six months later when a query returns null for a join that should never return null.

**ACID transactions** give you another set of guarantees that are genuinely difficult to replicate:

- **Atomicity**: Either all of a transaction's changes happen, or none do. Transferring $100 from account A to account B either completes fully or rolls back — you never end up with the money deducted from A but not added to B.
- **Consistency**: The database moves from one valid state to another. Constraints are checked at commit time.
- **Isolation**: Concurrent transactions do not see each other's intermediate states.
- **Durability**: Once a transaction commits, it is on disk. A crash does not lose it.

These guarantees matter for anything involving money, inventory, or any state that must be correct. Yes, you can implement compensating transactions and saga patterns in a NoSQL system, but you are rebuilding a subset of what the relational database already gives you — and you will probably do it less reliably.

### Netflix, GitHub, Shopify: PostgreSQL at Massive Scale

The companies that interviewers love to cite as justification for NoSQL are often themselves running PostgreSQL for large portions of their stack.

**GitHub** stores the core of its relational data — repositories, pull requests, issues, users, comments — in MySQL. At the time of the Microsoft acquisition, GitHub had tens of millions of repositories and hundreds of millions of pull requests. MySQL, with proper sharding and read replicas, handled it.

**Shopify** runs PostgreSQL. At 600,000+ merchants, each with their own products, orders, and customers, Shopify's data volume is enormous. Their solution was not to switch to NoSQL — it was to shard PostgreSQL into "pods," where each pod is a set of merchants running on a dedicated PostgreSQL cluster.

**Netflix** uses Cassandra for its viewing history and recommendations — areas where it genuinely needs NoSQL's write throughput and geographic distribution. But Netflix also uses MySQL and PostgreSQL for the relational parts of its system: billing, account management, content metadata.

The lesson: sophisticated engineering organizations use the right tool for the right job. And for most jobs — the ones involving structured data with relationships — the right tool is still a relational database.

### The 80% Rule

Here is a useful mental model for interviews: **80% of applications, even at significant scale, will perform well on a properly tuned PostgreSQL instance or small cluster**. The remaining 20% have genuine requirements — write volumes above 100K/s, truly schemaless data, multi-region active-active writes — that justify a different choice.

A "properly tuned PostgreSQL" means:
- Right hardware (adequate RAM to keep the working set in memory, fast NVMe SSDs)
- Correct indexing (indexes on the columns you filter and join on)
- Connection pooling (PgBouncer in front)
- Read replicas for read-heavy workloads
- Partitioning for very large tables

With these in place, a single PostgreSQL primary can handle thousands of queries per second, hundreds of gigabytes of data, and millions of concurrent users (via connection pooling). Before you suggest NoSQL in an interview, you should be able to explain why your scale exceeds this and what specific limit you are hitting.

---

## 2. PostgreSQL Internals

### MVCC — Multi-Version Concurrency Control

Imagine a library with one copy of a book. Two people want to read it at the same time. The naive solution — only one person can read it at a time — creates a bottleneck. A clever solution: the library makes copies. Reader A gets today's edition. Reader B also gets today's edition. If someone changes the book, they make a new copy. Readers who already have a copy keep their old version until they are done.

This is **MVCC** (Multi-Version Concurrency Control). PostgreSQL never modifies a row in place when it is updated. Instead, it writes a new version of the row and marks the old version as superseded. Readers that started their transaction before the update see the old version. Readers that start after see the new version. Nobody blocks anybody.

#### How PostgreSQL Tracks Versions: xmin and xmax

Every row in PostgreSQL has two hidden system columns:

- **xmin**: The transaction ID of the transaction that created this row version
- **xmax**: The transaction ID of the transaction that deleted or updated this row (0 if the row is still current)

When you run `INSERT INTO users VALUES (...)`, PostgreSQL creates a row with `xmin = your_transaction_id` and `xmax = 0`.

When you `UPDATE` a row, PostgreSQL does two things:
1. Sets `xmax` on the old row to your transaction ID (marking it as deleted/superseded)
2. Creates a new row with `xmin = your_transaction_id` and `xmax = 0`

When you `DELETE` a row, PostgreSQL only sets `xmax` on the existing row. The row is not physically removed.

```
Row in heap:
+------------------------------------------+
|  xmin  |  xmax  |  t_data (actual cols)  |
|--------|--------|------------------------|
|  1500  |   0    |  name="Alice", age=30  |
+------------------------------------------+

After UPDATE SET age=31 by txn 1601:
Old version:                          New version:
+---------------------------+         +---------------------------+
|  xmin  |  xmax  | data   |         |  xmin  |  xmax  | data   |
|--------|--------|--------|         |--------|--------|--------|
|  1500  |  1601  | age=30 |  --->   |  1601  |   0    | age=31 |
+---------------------------+         +---------------------------+
```

#### The Visibility Problem: Which Version Do I See?

When transaction T reads a row, PostgreSQL applies a **visibility check**:

- The row's `xmin` must be committed and must be <= T's snapshot
- The row's `xmax` must be either 0 (not deleted) or a transaction that started after T's snapshot

In plain English: you see a row if it was created before you started, and you do not see deletions that happened after you started.

```
Timeline:

  Txn 100 starts (snapshot: sees txn < 100)
  |
  |   Txn 101 starts, updates row (age: 30 -> 31), commits
  |   |
  |   |    Txn 100 reads row
  |   |    --> Sees age=30 (the version with xmin<100)
  |   |    --> Txn 101's version has xmin=101, which is > 100's snapshot
  |   |
  Txn 100 commits
                  Txn 102 starts
                  Txn 102 reads row
                  --> Sees age=31 (txn 101 committed before txn 102 started)
```

This means **reads never block writes and writes never block reads** in PostgreSQL. Two transactions can read and write the same row simultaneously without either one waiting for the other. This is a massive concurrency advantage over older databases that used read-write locks.

#### Vacuum: Why It Is Necessary and What Happens Without It

MVCC creates a problem: dead row versions accumulate. Every UPDATE leaves behind an old version. Every DELETE leaves behind a row with `xmax` set but the data still physically on disk. Over time, your table fills up with dead rows that no live transaction can see.

**VACUUM** is PostgreSQL's garbage collector. It scans tables, identifies dead row versions (rows where `xmax` is a committed transaction and no running transaction has a snapshot old enough to need that version), and marks that space as reusable.

Without VACUUM, two bad things happen:

**Table bloat**: The table file on disk grows indefinitely. A table that logically contains 10 million rows might occupy the disk space of 50 million rows because of accumulated dead versions. Queries slow down because they must scan more physical pages to find live rows.

**Transaction ID wraparound**: PostgreSQL uses 32-bit transaction IDs. After 2 billion transactions, the IDs wrap around. PostgreSQL handles this by periodically "freezing" old rows — marking them as visible to all transactions — but this requires VACUUM to run. If VACUUM has not run for a very long time, PostgreSQL will actually start refusing new transactions to prevent data corruption. This is rare but has caused production outages at companies that disabled autovacuum.

**Autovacuum** runs automatically in the background and handles routine cleanup. For most applications you do not need to think about it. But for tables with very high UPDATE/DELETE rates, you may need to tune autovacuum to run more aggressively.

---

### WAL — Write-Ahead Log

Imagine you are editing a document and the power goes out halfway through saving. When power comes back, is your document corrupted? If the application wrote part of the new content before the crash, you might have a half-written file.

Databases face the same problem. Writing data to disk is not instantaneous, and a crash mid-write can corrupt the database. **WAL** (Write-Ahead Log) is the solution.

The rule is simple: **before writing any change to the actual data files, write a description of that change to the WAL**. The WAL is a sequential append-only log. Sequential writes are fast (no seeking). If a crash happens:
- If the change made it to the WAL but not the data files, replay the WAL to reconstruct the change
- If the change did not even make it to the WAL, it is as if the transaction never happened

This is safe because a transaction is only considered committed once its WAL record is durably on disk. PostgreSQL calls `fsync()` to force the WAL to disk before returning "commit successful" to the client.

#### WAL and Replication

WAL is not just for crash recovery. It is also the mechanism PostgreSQL uses to replicate data to standby servers.

The primary server continuously writes WAL records as transactions commit. Replica servers connect to the primary and stream those WAL records in real time. Each replica applies the WAL records to its own copy of the data, staying in sync with the primary.

```
PRIMARY SERVER                    REPLICA SERVER
+-------------------+             +-------------------+
|                   |  WAL stream |                   |
|  User writes  --> |  ---------> |  Apply WAL        |
|  data pages       |             |  --> data pages   |
|       |           |             |                   |
|       v           |             +-------------------+
|  WAL file         |
|  (append-only)    |             +-------------------+
|       |           |  WAL stream |                   |
|       +-----------|  ---------> |  REPLICA 2        |
|                   |             |                   |
+-------------------+             +-------------------+

WAL records look like:
  [txn 1601] UPDATE users SET age=31 WHERE id=42
  [txn 1601] COMMIT
  [txn 1602] INSERT INTO orders (user_id, total) VALUES (42, 99.99)
  [txn 1602] COMMIT
```

The replica is always slightly behind the primary — this is called **replication lag**. Under normal conditions, lag is milliseconds. Under heavy write load or if the replica is slow, lag can grow to seconds or minutes, and reads from the replica may return stale data.

---

### Query Planner: How PostgreSQL Decides How to Execute Your Query

When you send a SQL query, PostgreSQL does not immediately go execute it. First, it runs the query through the **query planner** (also called the query optimizer), which figures out the fastest way to retrieve the requested data.

The planner considers many execution strategies and picks the one with the lowest estimated cost. To make good estimates, it relies on **statistics** — data about the distribution of values in each column, maintained by the `ANALYZE` command (run automatically by autovacuum).

#### EXPLAIN ANALYZE: Reading the Query Plan

`EXPLAIN ANALYZE` is your window into the planner's decisions. It shows you exactly what strategy PostgreSQL chose, how many rows it estimated, how many rows it actually found, and how long each step took.

```sql
EXPLAIN ANALYZE
SELECT u.name, COUNT(o.id) AS order_count
FROM users u
JOIN orders o ON o.user_id = u.id
WHERE u.created_at > '2024-01-01'
GROUP BY u.id, u.name;
```

A simplified output:
```
HashAggregate  (cost=1234.00..1240.00 rows=500 width=40)
              (actual time=45.2..46.1 rows=487 loops=1)
  ->  Hash Join  (cost=500.00..1200.00 rows=6800 width=20)
                 (actual time=10.5..40.8 rows=6931 loops=1)
        Hash Cond: (o.user_id = u.id)
        ->  Seq Scan on orders  (cost=0.00..400.00 rows=20000)
                                (actual time=0.1..15.2 rows=20000 loops=1)
        ->  Hash  (cost=480.00..480.00 rows=500)
                  (actual time=9.8..9.8 rows=487 loops=1)
              ->  Index Scan on users  (cost=0.43..480.00 rows=500)
                                       (actual time=0.1..9.1 rows=487 loops=1)
                    Index Cond: (created_at > '2024-01-01')
```

Key things to look for:
- **Estimated rows vs actual rows**: If the planner estimated 500 rows but got 50,000, its statistics are stale and it may have chosen a suboptimal strategy. Run `ANALYZE` on the table.
- **Seq Scan on a large table**: A sequential scan reads every page of the table. Fine for small tables or when you need >10% of rows. A problem when you need a tiny fraction of a large table.
- **Cost**: The numbers in `cost=X..Y` are arbitrary units (roughly disk page reads). The first number is startup cost, the second is total cost.

#### Scan Strategies

**Sequential Scan (Seq Scan)**: Read every row in the table from start to finish. Simple and efficient when you need a large fraction of the table. PostgreSQL uses the OS page cache and can do read-ahead.

**Index Scan**: Navigate the B-tree index to find matching row pointers, then fetch each row from the heap (table data). Each heap fetch may require a random disk read. Good when you need a small number of rows.

**Index Only Scan**: Like Index Scan, but all the columns you need are in the index itself — no heap fetch needed. The fastest possible scan for queries that can be served entirely from the index.

The planner chooses between these based on the estimated fraction of rows needed:
- Need >10-20% of rows → Seq Scan (random I/O cost of index scan exceeds sequential scan)
- Need <1-5% of rows → Index Scan
- All needed columns in index → Index Only Scan

#### Join Strategies

When joining two tables, PostgreSQL chooses one of three strategies:

| Strategy | How It Works | Best For |
|---|---|---|
| **Nested Loop** | For each row in the outer table, search the inner table | Small outer table + indexed inner table |
| **Hash Join** | Build a hash table from the smaller table, probe it with larger table | Medium tables, no useful index |
| **Merge Join** | Sort both tables on the join key, merge-scan them together | Both inputs already sorted (e.g., via index) |

In practice: if you see a Hash Join on a large table in your EXPLAIN output, adding an index on the join key might let the planner switch to a Nested Loop or Merge Join, which can be significantly faster.

---

## 3. Indexing Deep Dive

An index is a separate data structure that the database maintains alongside your table, trading write overhead and disk space for faster reads. Understanding when and how to use indexes is one of the highest-leverage skills in database performance tuning.

### B-Tree Index: The Default

The **B-Tree** (Balanced Tree) index is what PostgreSQL creates when you run `CREATE INDEX` with no type specified. It is a sorted tree structure where each node contains index keys and pointers. Lookups, range scans, and sorted retrievals are all efficient.

```
B-Tree index on users.last_name:

                    [M]
                   /   \
              [D-H]     [R-Z]
             /  |  \    /   \
         [A-C][D-F][G-H][R-T][U-Z]
           |    |    |    |    |
         rows  rows rows rows rows
```

A B-Tree index supports:
- Equality: `WHERE last_name = 'Smith'`
- Range: `WHERE last_name BETWEEN 'Smith' AND 'Williams'`
- Prefix: `WHERE last_name LIKE 'Smi%'` (but NOT `LIKE '%ith'` — that cannot use the sorted prefix structure)
- Sorting: `ORDER BY last_name` (the index is already sorted)
- NULL checks: `WHERE last_name IS NULL` (NULLs are stored in the index)

#### Composite Indexes and the Leftmost Prefix Rule

A composite index covers multiple columns: `CREATE INDEX ON orders (user_id, created_at)`.

The **leftmost prefix rule** says: a composite index can only be used if the query filters on the leading columns of the index, in order.

Given index `(user_id, created_at)`:

```sql
-- Uses the index fully:
WHERE user_id = 42 AND created_at > '2024-01-01'

-- Uses the index partially (only user_id part):
WHERE user_id = 42

-- CANNOT use the index:
WHERE created_at > '2024-01-01'   -- skips user_id, the leading column
```

Why? Because the index is sorted first by `user_id`, then by `created_at` within each `user_id`. To find rows with a specific `created_at`, you would need to scan every `user_id` group — no better than a sequential scan.

```
Composite index (user_id, created_at):

user_id=1, created_at=2024-01-01
user_id=1, created_at=2024-03-15    <--- sorted within user_id=1
user_id=1, created_at=2024-07-20
user_id=2, created_at=2024-02-10
user_id=2, created_at=2024-05-05    <--- sorted within user_id=2
user_id=3, created_at=2024-01-20
...

Query: WHERE user_id=2 AND created_at > '2024-04-01'
--> Jump to user_id=2 section, scan forward from created_at=2024-04-01
--> Efficient: touches only a small slice of the index

Query: WHERE created_at > '2024-04-01'
--> Cannot jump anywhere; must scan the whole index to find all such dates
--> Planner will probably choose a Seq Scan instead
```

**Implication for interview design**: When someone asks "how would you index this table?", think about which columns appear together in WHERE clauses and what order makes the leftmost prefix most useful. Put the equality-filtered column first, then the range-filtered column.

#### Covering Indexes

A **covering index** (or **index with included columns**) lets PostgreSQL answer a query entirely from the index, without ever touching the table.

```sql
-- Regular index: PostgreSQL finds matching row pointers, then fetches rows from heap
CREATE INDEX ON orders (user_id);

-- Covering index: PostgreSQL can answer this query without touching the heap
CREATE INDEX ON orders (user_id) INCLUDE (total, created_at);

-- This query now uses Index Only Scan (no heap fetch):
SELECT total, created_at FROM orders WHERE user_id = 42;
```

Covering indexes are extremely valuable for frequently-run queries on large tables. The tradeoff: the index is larger (includes extra columns) and write operations must update more data.

#### Partial Indexes

A **partial index** only indexes rows that match a WHERE condition. The index is smaller, faster to build, and faster to scan.

```sql
-- Index only active users (assume 95% of users are inactive after 1 year)
CREATE INDEX ON users (email) WHERE status = 'active';

-- This query uses the partial index:
SELECT * FROM users WHERE email = 'alice@example.com' AND status = 'active';

-- This query cannot use it (condition doesn't match):
SELECT * FROM users WHERE email = 'alice@example.com';
```

Real-world use case: if you have a `jobs` table with millions of rows and only a few hundred in `status = 'pending'`, an index on `(status)` where `status = 'pending'` is tiny and extremely fast for the worker process that polls for pending jobs.

---

### Hash Index

A **hash index** maps each indexed value to a hash bucket and stores the row pointer there. It only supports equality lookups — no ranges, no sorting. But for pure equality lookups, it can be slightly faster than a B-Tree because there are fewer levels to traverse.

```sql
CREATE INDEX ON users USING HASH (session_token);

-- Uses hash index:
WHERE session_token = 'abc123def456'

-- Cannot use hash index:
WHERE session_token > 'abc'  -- no ordering in a hash table
```

In practice, most PostgreSQL DBAs use B-Trees even for equality lookups because the performance difference is small and B-Trees are more flexible. Hash indexes are worth considering for very high-volume equality lookups on large values (like UUIDs or session tokens).

---

### GIN Index: For Full-Text Search, JSON, and Arrays

**GIN** (Generalized Inverted Index) is fundamentally different from B-Tree. It is designed for composite values — things like documents, arrays, and JSON objects — where a single row contains multiple searchable items.

Think of the index in the back of a textbook: it maps each keyword to a list of page numbers where that keyword appears. GIN does the same thing for database rows.

```sql
-- Full-text search: find all articles mentioning "postgres" and "performance"
CREATE INDEX ON articles USING GIN (to_tsvector('english', body));

SELECT * FROM articles
WHERE to_tsvector('english', body) @@ to_tsquery('postgres & performance');

-- JSON search: find all users with a specific preference
CREATE INDEX ON users USING GIN (preferences);

SELECT * FROM users WHERE preferences @> '{"theme": "dark"}';

-- Array search: find all posts tagged with "database"
CREATE INDEX ON posts USING GIN (tags);

SELECT * FROM posts WHERE tags @> ARRAY['database'];
```

GIN indexes are large and slow to build/update (because adding one new word to a document requires updating many index entries). They are the right choice when your query patterns involve containment, overlap, or full-text matching.

---

### BRIN Index: For Naturally Ordered Data

**BRIN** (Block Range INdex) is the most compact index type. Instead of indexing individual values, it stores summary information (min and max) for each range of physical blocks.

It only works well when the data is naturally ordered on disk — meaning rows were inserted in the same order as the indexed column. This is true for auto-incrementing IDs and timestamps (assuming rows are rarely deleted and re-inserted).

```
BRIN index on orders.created_at:

Physical blocks:    1-100      | 101-200   | 201-300   | 301-400
Min created_at:     2024-01-01 | 2024-03-15| 2024-06-01| 2024-09-10
Max created_at:     2024-03-14 | 2024-05-31| 2024-09-09| 2024-12-31

Query: WHERE created_at BETWEEN '2024-06-01' AND '2024-07-31'
--> Only blocks 201-300 can contain relevant rows (min/max overlap the range)
--> Skip blocks 1-200 and 301-400
```

A BRIN index on a 100GB table might be just 128KB — orders of magnitude smaller than a B-Tree. The tradeoff: it is much less precise than a B-Tree, so PostgreSQL may still read some blocks that contain no matching rows.

---

### Bad Indexing Patterns

**Over-indexing**: Every index adds overhead to INSERT, UPDATE, and DELETE operations. If you have 10 indexes on a table, every write must update 10 index structures. A table with hundreds of thousands of writes per second and 10 indexes will spend more time maintaining indexes than storing data.

Rule of thumb: index the columns you filter by, join on, and sort by in real queries. Remove indexes that have not been used in months (PostgreSQL tracks index usage in `pg_stat_user_indexes`).

**Indexing low-cardinality columns**: A column with only 2-3 distinct values (like `status` with values 'active'/'inactive') is a poor candidate for a standard B-Tree index. If half the rows have `status = 'active'`, the index points to half the table — the planner will just do a Seq Scan. Use a partial index instead, or accept that filtering by status alone will always be a Seq Scan.

---

## 4. Scaling Patterns

### Connection Pooling

PostgreSQL uses a **process-per-connection** model. When a client connects, PostgreSQL forks a new operating system process to handle that connection. Each process consumes:
- 5-10 MB of RAM for its own memory (shared buffers are separate)
- OS resources: file descriptors, scheduling overhead, etc.

This is fine for 100 connections. It becomes a serious problem at 10,000 connections:
- 10,000 connections × 8 MB = 80 GB of RAM just for connection overhead
- The OS scheduler thrashes handling 10,000 processes
- PostgreSQL's shared memory structures have contention at high connection counts

The solution is a **connection pooler**, and the standard choice is **PgBouncer**.

#### How PgBouncer Works

PgBouncer sits between your application servers and PostgreSQL. Application servers connect to PgBouncer (which can handle many thousands of connections cheaply, since it is a single event-driven process). PgBouncer maintains a small pool of actual PostgreSQL connections and assigns them to application requests as needed.

```
10,000 app threads          PgBouncer              PostgreSQL
+------------------+       +-----------+          +----------+
| App server 1     |       |           |          |          |
|  thread 1  ----> |-----> |           |          |          |
|  thread 2  ----> |-----> |  Pool:    | -------> | 100      |
|  ...       ----> |-----> |  100      | -------> | actual   |
| App server 2     |       |  real     | -------> | worker   |
|  thread 1  ----> |-----> |  PG       |          | processes|
|  thread 2  ----> |-----> |  connections          |          |
|  ...       ----> |-----> |           |          +----------+
| App server 3     |       +-----------+
|  ...       ----> |
+------------------+
                    ^
         10,000 lightweight
         PgBouncer connections
         (single process, no fork)
```

PgBouncer has two main pooling modes:

- **Session pooling**: A PostgreSQL connection is assigned to a client for the entire session. Good for applications that use session-level state. Only saves connections when clients disconnect.
- **Transaction pooling**: A PostgreSQL connection is assigned for a single transaction, then returned to the pool. This is the high-efficiency mode — 10,000 clients can share 100 PostgreSQL connections, as long as no single transaction takes a long time. Most web applications work fine with this.

---

### Read Replicas

When your read load outgrows a single PostgreSQL instance, you add **read replicas** — additional servers that receive a copy of all writes via WAL streaming and serve read queries.

```
Application Servers
+------------------+
|  Write queries   |----> PRIMARY (read-write)
|  Read queries    |          |
|  (routed)        |          | WAL stream
+------------------+          |
                               v
                    +--------------------+
                    | REPLICA 1 (r/o)   |
                    +--------------------+
                    | REPLICA 2 (r/o)   |
                    +--------------------+
```

#### Replication Lag

Because replicas apply WAL asynchronously, there is always a small delay between a write committing on the primary and that write being visible on replicas. Under normal conditions this is milliseconds. Under high write load or if a replica is doing heavy work, lag can be seconds.

**This matters**: a user who just posted a comment and immediately refreshes the page might have their request routed to a replica that has not yet applied that insert. They see a page without their own comment. This is confusing and feels like a bug.

#### The Read-Your-Writes Problem

This is a classic distributed systems problem. The user writes data, then reads it back — but the read goes to a stale replica.

**Solution 1 — Sticky routing after writes**: After any write, route all subsequent reads from that user to the primary for a short window (say, 5 seconds, or until the replica has caught up).

**Solution 2 — Read-after-write tokens**: When the primary commits a write, it returns the WAL position (LSN — Log Sequence Number). Store this in the user's session. When routing a read, send the LSN to the replica; the replica only serves the query if its applied WAL position is >= that LSN, otherwise it redirects to the primary.

**Solution 3 — Always read from primary for anything the user just wrote**: Less elegant but simple and correct.

---

### Partitioning

When a single table grows to hundreds of millions or billions of rows, queries and maintenance operations become slow even with good indexes. **Partitioning** splits the table into multiple physical subtables, each storing a subset of the rows, while appearing as a single table to queries.

#### Range Partitioning by Date

The most common pattern. Each partition covers a time range.

```sql
CREATE TABLE orders (
    id BIGINT,
    user_id BIGINT,
    total NUMERIC,
    created_at TIMESTAMP
) PARTITION BY RANGE (created_at);

CREATE TABLE orders_2024_q1 PARTITION OF orders
    FOR VALUES FROM ('2024-01-01') TO ('2024-04-01');

CREATE TABLE orders_2024_q2 PARTITION OF orders
    FOR VALUES FROM ('2024-04-01') TO ('2024-07-01');
-- ... and so on
```

```
orders (parent, logical table)
+--------------------------------------------+
|  orders_2024_q1   | orders_2024_q2   | ... |
|  Jan-Mar 2024     | Apr-Jun 2024     | ... |
+--------------------------------------------+

Query: WHERE created_at BETWEEN '2024-05-01' AND '2024-06-30'
--> Partition pruning: only scans orders_2024_q2
--> Completely skips orders_2024_q1 and all other partitions
```

The killer benefit: when you want to delete old data, instead of running `DELETE FROM orders WHERE created_at < '2023-01-01'` (which generates enormous write amplification and WAL), you run `DROP TABLE orders_2022_q4` — instant, no transaction log overhead.

#### Hash Partitioning

Distributes rows evenly based on the hash of a column. Use when you want to spread write load evenly and do not have a natural range key.

```sql
CREATE TABLE users (
    id BIGINT,
    email TEXT,
    ...
) PARTITION BY HASH (id);

CREATE TABLE users_p0 PARTITION OF users FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE users_p1 PARTITION OF users FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE users_p2 PARTITION OF users FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE users_p3 PARTITION OF users FOR VALUES WITH (MODULUS 4, REMAINDER 3);
```

#### List Partitioning

Partitions rows based on a discrete set of values. Useful for partitioning by region, status, or category.

```sql
CREATE TABLE events (
    id BIGINT,
    region TEXT,
    ...
) PARTITION BY LIST (region);

CREATE TABLE events_us PARTITION OF events FOR VALUES IN ('us-east', 'us-west');
CREATE TABLE events_eu PARTITION OF events FOR VALUES IN ('eu-west', 'eu-central');
CREATE TABLE events_apac PARTITION OF events FOR VALUES IN ('ap-southeast', 'ap-northeast');
```

---

## 5. The N+1 Query Problem

This is one of the most common performance bugs in applications that use relational databases, and it appears in interviews more often than you might expect — partly because NoSQL does not obviously fix it.

### What It Is

Imagine you are building a page that shows 100 users and each user's profile picture URL. The naive code does this:

```python
# Step 1: one query to get the users
users = db.query("SELECT id, name FROM users LIMIT 100")  # 1 query

# Step 2: for each user, one query to get their profile
for user in users:
    profile = db.query(
        "SELECT avatar_url FROM profiles WHERE user_id = ?",
        user.id
    )  # 100 queries
    user.avatar_url = profile.avatar_url
```

Total: 1 + 100 = **101 queries** to load one page. This is the **N+1 problem**: one query to get N items, then N more queries to get related data.

At 100 users with 1ms per query, this is 101ms of sequential database round trips. At 1,000 users, it is 1,001ms — more than a second just in database calls. This kills page load times.

### Fix 1: JOIN

The simplest fix — get all the data in one query using a SQL JOIN.

```sql
SELECT u.id, u.name, p.avatar_url
FROM users u
JOIN profiles p ON p.user_id = u.id
LIMIT 100;
```

One query, one round trip, same data. The database engine executes the join far more efficiently than 100 separate round trips.

### Fix 2: Eager Loading with IN Clause

When the data is in separate services or you cannot always use a JOIN, fetch in bulk.

```python
users = db.query("SELECT id, name FROM users LIMIT 100")
user_ids = [u.id for u in users]

# One query to get ALL profiles at once
profiles = db.query(
    "SELECT user_id, avatar_url FROM profiles WHERE user_id = ANY(?)",
    user_ids
)

# Build a map for O(1) lookup
profile_map = {p.user_id: p for p in profiles}

for user in users:
    user.avatar_url = profile_map.get(user.id)
```

Total: 2 queries, regardless of how many users. The `IN (id1, id2, id3, ...)` clause lets the database batch-fetch all needed profiles in one scan.

### Fix 3: DataLoader Pattern

The DataLoader pattern (popularized by Facebook's GraphQL implementation) is a general solution for batching and deduplicating requests. Instead of immediately fetching data when requested, DataLoader collects all requests made within a single "tick" of the event loop, then issues one batched request for all of them.

```
Without DataLoader (in a GraphQL resolver):
  resolve user 1 --> fetch profile_id=1 --> 1 query
  resolve user 2 --> fetch profile_id=2 --> 1 query
  ... 
  resolve user 100 --> fetch profile_id=100 --> 1 query
  Total: 100 queries

With DataLoader:
  resolve user 1   --> enqueue profile_id=1
  resolve user 2   --> enqueue profile_id=2
  ...
  resolve user 100 --> enqueue profile_id=100
  --- end of tick ---
  DataLoader: SELECT * FROM profiles WHERE id IN (1,2,3,...,100)
  Total: 1 query
```

DataLoader implementations exist for Node.js, Python, Go, and most other languages.

### Why This Is an Interview Gotcha

The N+1 problem is not a SQL problem — it is an **application design problem**. NoSQL databases do not solve it; they just move it. With MongoDB, you still need to fetch related documents. With DynamoDB, if you denormalized all your data to avoid joins, you traded the N+1 query problem for data duplication and consistency headaches.

When an interviewer asks "how would you handle large amounts of relational data?", mentioning N+1 detection and JOIN-based or batch-loading fixes shows you understand real-world performance engineering, not just theoretical database knowledge.

---

## 6. Real Incident: Shopify's PostgreSQL Scaling Journey

This case study is worth knowing well. It illustrates that the path from "small startup" to "massive scale" does not require abandoning relational databases.

### The Problem

Shopify launched in 2006 with a straightforward Rails application backed by a single PostgreSQL database. By 2014, they had grown from a handful of merchants to hundreds of thousands. The single database was struggling under:

- **Connection limits**: With thousands of Rails application processes each maintaining database connections, they were hitting PostgreSQL's connection limit. Each new merchant brought more traffic, more connections.
- **Hot tables**: The `orders` and `products` tables were enormous and heavily written. The same table was being written by thousands of merchants simultaneously.
- **Slow queries**: As tables grew to hundreds of millions of rows, queries that were instant at 1 million rows were now taking seconds. VACUUM was taking hours.
- **Replication lag**: Their read replicas were falling behind the primary. Shopify's admin panels were reading stale data — merchants would update a product and refresh the page to see the old data.

### What They Did

**Step 1 — PgBouncer**: They added PgBouncer in front of PostgreSQL. This immediately relieved the connection limit problem, allowing thousands of application processes to share a small pool of actual PostgreSQL connections.

**Step 2 — Read replicas**: They split read traffic (product catalog browsing, admin page loads) to read replicas, reducing load on the primary. They implemented read-after-write routing to avoid the stale data problem on admin panels.

**Step 3 — The "Pods" Architecture**: The biggest architectural change. Instead of one giant database for all merchants, they split merchants across many small PostgreSQL clusters, each serving a subset of merchants. They called these **pods**.

Each pod contains:
- One primary PostgreSQL server
- Two or three replicas
- A set of merchants whose data lives entirely on that pod

```
Merchants 1-5,000          Pod A
+--------------+     +-------------------+
|  Shop 42     |---->|  Primary          |
|  Shop 1337   |---->|  Replica 1        |
|  Shop 2048   |---->|  Replica 2        |
+--------------+     +-------------------+

Merchants 5,001-10,000     Pod B
+--------------+     +-------------------+
|  Shop 5001   |---->|  Primary          |
|  Shop 7777   |---->|  Replica 1        |
|  Shop 9999   |---->|  Replica 2        |
+--------------+     +-------------------+
```

A routing layer (backed by a small metadata database) maps each merchant's shop ID to their pod. Every database query is prefixed with a lookup to find the right pod.

### Key Insight: They Kept PostgreSQL

This is the most important part. Shopify did not migrate to Cassandra, MongoDB, or DynamoDB. Their response to every scaling challenge was to add infrastructure around PostgreSQL: pooling, replicas, and eventually sharding.

Why? Because Shopify's data is inherently relational. An order belongs to a customer. A line item belongs to an order. A product has variants. An inventory record belongs to a variant. These relationships are enforced at the database level, and switching to NoSQL would have required Shopify to rebuild all of that enforcement in application code — a massive undertaking with a high risk of bugs that cause merchant data corruption.

### Lesson for Interviews

When someone asks "how would you scale this database?", the answer should follow this progression:

```
Stage 1: Single primary
         --> Add connection pooling (PgBouncer)
         --> Tune indexes and queries

Stage 2: Read bottleneck
         --> Add read replicas
         --> Route read traffic to replicas

Stage 3: Write bottleneck on specific tables
         --> Partition large tables (date, hash)
         --> Vertical scaling (larger instance)

Stage 4: Total write volume exceeds single primary
         --> Shard: split data across multiple independent PostgreSQL clusters

Each step before considering a database engine change.
```

Suggesting a switch to NoSQL in stage 1 or 2 is a red flag in an interview. It shows you are reaching for a hammer when you need a screwdriver.

---

## 7. When NOT to Use Relational (Honest Limits)

Having made the case for relational databases, it is equally important to know where they genuinely struggle. An L6 engineer is not religious about tools — they understand tradeoffs.

### Write Volume Above ~100,000/s on a Single Node

A well-tuned PostgreSQL primary on high-end hardware (many CPU cores, NVMe SSDs) can sustain roughly 50,000–100,000 simple INSERT/UPDATE transactions per second. Beyond that, you are hitting fundamental limits:

- WAL writes become a bottleneck (even NVMe has throughput limits)
- Lock contention on shared buffers
- Autovacuum cannot keep up with dead tuple accumulation

If your application genuinely requires 500,000 writes per second to a single logical dataset, a distributed NoSQL system like Cassandra (designed for exactly this use case) is the right choice.

Note: most applications that think they need this do not actually need it. Check your actual numbers.

### Data That Does Not Have Relationships

A time-series sensor database recording temperature readings every millisecond from 100,000 sensors does not have relationships. There are no foreign keys, no joins, no need for ACID across multiple tables. Using PostgreSQL for this works, but a purpose-built time-series database (InfluxDB, TimescaleDB — though TimescaleDB is actually PostgreSQL-based) will store this data more efficiently and query it faster.

Similarly, a raw event log (a stream of "things that happened") where you never need to join events to other events is better served by a columnar store (ClickHouse, BigQuery) or an append-only log (Kafka) than a row-oriented relational database.

### Schema That Changes Every Week

Relational databases enforce schemas strictly, which is a strength (correctness) but also a constraint (migrations). Adding a column to a table with 500 million rows requires a migration that either:
- Takes hours (the old way: table rewrite)
- Uses tricks like adding nullable columns first, backfilling asynchronously, then making them not-null (the modern approach, used by tools like `pg_repack` and `gh-ost`)

If you are building a product in its earliest stages where the data model is changing every sprint, schema migrations become friction. A document database (MongoDB) or a schema-on-read approach lets you iterate faster by accepting any shape of data.

This is a valid tradeoff — but note that you are trading short-term development velocity for long-term data quality. Most mature engineering organizations eventually impose schema discipline on their document stores anyway, often with heavy regret about the years of unstructured data.

### Multi-Region Active-Active Writes

PostgreSQL's replication is primary-replica (primary-standby). Only the primary accepts writes. If you have users in the US and Europe, both wanting low-latency writes, you have a problem:
- US primary: European users have 100-150ms write latency (cross-ocean round trip)
- Multi-primary PostgreSQL: not natively supported (Citus and BDR extend it, with tradeoffs)

True multi-region active-active writes with strong consistency are fundamentally hard — you hit the CAP theorem. If two regions can both write the same record simultaneously, you need a way to resolve conflicts. Databases like Google Spanner (using TrueTime and Paxos) and CockroachDB (distributed PostgreSQL-compatible) solve this but at significant cost and complexity.

If your application needs users in multiple regions to write with low latency and you need strong consistency, this is a genuine limit of standard PostgreSQL and worth acknowledging in an interview.

---

## Summary: The Relational Database Mental Model

A relational database is not an old, slow technology waiting to be replaced. It is a sophisticated system built over decades of research, with a carefully designed set of guarantees that are genuinely valuable:

- **MVCC** gives you high concurrency without locking hell
- **WAL** gives you durability and replication
- **The query planner** gives you flexibility — write the query that expresses what you want, not how to find it
- **ACID transactions** give you correctness without building distributed transaction logic yourself
- **Schema enforcement** gives you data integrity without trusting every application layer

The key scaling moves — connection pooling, read replicas, partitioning, sharding — let PostgreSQL grow with your application through many orders of magnitude. Most applications will never hit the genuine limits where a different database engine becomes necessary.

In an interview, defaulting to PostgreSQL with a clear understanding of how to scale it is almost always the right starting point. The burden of proof is on the alternative.

---

*Next: Part C — NoSQL Databases: Document, Key-Value, Wide-Column, and Graph*
# Chapter 28, Part C — NoSQL Databases: Document, Key-Value, and Wide-Column Stores

> Part A covered relational databases and ACID. Part B covered the CAP theorem and why NoSQL
> exists. Part C goes deep on the internals of specific NoSQL systems you will be asked about.

---

## Why This Section Matters

"I'd use DynamoDB for this" is table stakes — everyone says that. The L6 follow-up is: *How does
DynamoDB decide which node stores your data? What happens when your partition key is skewed? What
would you do if reads started timing out at 3am?*

This section covers five NoSQL categories at the level of failure modes, not just happy paths.

---

## Section 1: Key-Value Stores — Redis Deep Dive

### What Redis Actually Is

Redis (**Remote Dictionary Server**) is a giant dictionary living entirely in RAM. Give it a key,
get a value back in under a millisecond — no disk involved.

```
Your App                Redis Server (in RAM)
   |                          |
   |  SET user:42 "Alice"     |
   |------------------------->|   ┌─────────────────────────┐
   |                          |   │  Key         Value       │
   |  GET user:42             │   │  ─────────────────────── │
   |------------------------->|   │  user:42     "Alice"     │
   |  "Alice"                 │   │  counter:99  "1024"      │
   |<-------------------------|   │  session:abc "{json...}" │
                                  └─────────────────────────┘
                                  Everything lives in RAM.
                                  Lookup is O(1).
```

Redis is not just a dumb cache — it is a **data structure server**. Values can be lists, hashes,
sorted sets, streams. Each type has its own commands, enabling patterns impossible with plain strings.

---

### Redis Data Structures: The Six You Need to Know

#### 1. String (the simplest one)

A byte sequence — text, JSON, binary. Max 512 MB per key.

**Use cases:**
- **Session tokens**: `SET session:abc123 "{...}" EX 3600` — `EX` sets TTL; key auto-deletes on expiry.
- **Counters**: `INCR page:views:homepage` — atomic increment, no race condition.
- **Simple caches**: `SET product:99:json "{...}" EX 300` — cache query result for 5 minutes.

#### 2. List (a doubly-linked list under the hood)

An ordered collection of strings with O(1) push/pop from either end.

```
LPUSH jobs "email:welcome:user5"    ←  push to LEFT (head)
LPUSH jobs "email:promo:user3"
RPOP  jobs                          ←  pop from RIGHT (tail)

State after LPUSHes:
  HEAD                              TAIL
   |                                 |
  [email:promo:user3] ← [email:welcome:user5]
                                     |
                              RPOP removes this
```

**Use cases:** task queues (LPUSH jobs, RPOP to consume); activity logs (`LPUSH` + `LTRIM`
to keep last 100 actions); timeline feeds (Twitter stored home timelines as pre-computed ID lists).
For large workloads needing consumer groups, use Streams instead.

#### 3. Hash (a dictionary inside a dictionary)

A flat key-value map under a single Redis key — like a database row in memory.

```
HSET user:42 name "Alice" age "30" city "NYC" plan "pro"

Stored as:
  user:42 → {
    name: "Alice"
    age:  "30"
    city: "NYC"
    plan: "pro"
  }
```

**Use cases:** user profiles (update one field with `HSET user:42 plan "enterprise"` without
fetching the whole object); shopping carts (product-id → quantity, `HINCRBY` to increment).

#### 4. Set (unordered, unique membership)

Unique strings, no order. Add/remove/membership are O(1). Union, intersection, and difference
operations across sets are also supported.

**Use cases:** unique visitor counts (`SADD` deduplicates automatically); tagging with
intersection queries (`SINTER tags:sale tags:featured` = products in both); mutual friends
(`SINTER friends:userA friends:userB`).

#### 5. Sorted Set (the leaderboard engine)

A **Sorted Set** is a Set where every member has a floating-point **score**. Members are kept sorted
by score at all times. Internally: a **skip list** (sorted linked list with express lanes) + hash map
for O(log N) insert and O(log N + K) range queries.

```
ZADD leaderboard 9800 "alice"
ZADD leaderboard 7500 "bob"
ZADD leaderboard 9900 "carol"
ZADD leaderboard 6200 "dan"

Sorted Set state (sorted by score, ascending):
  Score   Member
  ─────   ──────
  6200    dan
  7500    bob
  9800    alice
  9900    carol

ZREVRANGE leaderboard 0 2 WITHSCORES
→ carol 9900, alice 9800, bob 7500   (top 3, descending)

ZRANGEBYSCORE leaderboard 7000 9999
→ bob, alice, carol   (everyone between 7000 and 9999)
```

**Use case — sliding window rate limiter:**

```
Key: ratelimit:user:42   (members = request timestamps, score = timestamp)

Per request:
  ZADD ratelimit:user:42 <now_ms> <now_ms>         (record this request)
  ZREMRANGEBYSCORE ratelimit:user:42 0 <now_ms-60000>  (drop entries >60s old)
  count = ZCARD ratelimit:user:42
  if count > 100: reject   else: allow

The set always holds exactly the timestamps from the last 60 seconds — it slides forward.
```

#### 6. Stream (append-only event log)

Redis Streams (Redis 5.0+) are append-only logs where each entry gets an auto-generated
millisecond-precision ID. **Consumer groups** let multiple workers share a stream — each message
goes to exactly one consumer in the group, with re-delivery if that consumer crashes. Think Kafka,
but in-memory and simpler. Use for event sourcing, at-least-once message queues, and async
activity feeds.

---

### Redis Persistence: The Three Modes

Redis is **in-memory by default** — restart and everything is gone. Three modes:

**Mode 1 — No persistence (pure cache)**: source of truth is elsewhere; losing the cache just
means a cold-start warmup period.

**Mode 2 — RDB Snapshots**: forks the process and writes the full dataset to a `.rdb` file.
Linux copy-on-write keeps Redis serving during the snapshot.

```
save 900 1      # snapshot if 1 key changed in last 900 seconds
save 60 10000   # snapshot if 10000 keys changed in last 60 seconds
```

Data loss window = time since last snapshot. Fine for short-TTL caches, not for billing.

**Mode 3 — AOF**: logs every write command as text; replayed on restart. Fsync policy:

| Setting                | Durability              | Speed   |
|------------------------|-------------------------|---------|
| `appendfsync always`   | Every write fsynced     | Slowest |
| `appendfsync everysec` | 1 second max data loss  | Fast (recommended) |
| `appendfsync no`       | OS decides              | Fastest, risky |

**AOF rewrite** periodically compacts the file to the minimal command set needed to reproduce current state.

**Production: RDB + AOF together**

```
┌─────────────────────────────────────────────────────┐
│  Redis Production Configuration                      │
│                                                      │
│  appendonly yes          ← enables AOF               │
│  appendfsync everysec    ← 1 second max data loss    │
│  save 900 1              ← RDB as backup             │
│  save 300 10                                         │
│                                                      │
│  On crash:                                           │
│  - Redis uses AOF to recover (more complete)         │
│  - RDB used if AOF is corrupt                        │
└─────────────────────────────────────────────────────┘
```

**The "Redis lost all my data" incident**: Team uses Redis for sessions with default config
(`save 3600 1`). At 2am, the OOM killer kills Redis. It restarts from the snapshot — 2 hours
stale. All sessions from the last 2 hours are gone; every logged-in user is logged out.
Fix: AOF with `appendfsync everysec`. Never make Redis the sole source of truth for
unrecoverable data.

---

### Eviction Policies: What Happens When Memory Fills Up

When RAM fills up, Redis evicts keys based on `maxmemory-policy`:

| Policy              | Behavior                                              | Best For           |
|---------------------|-------------------------------------------------------|--------------------|
| `noeviction`        | Return errors on write. Nothing evicted.              | When data must not be lost |
| `allkeys-lru`       | Evict the least recently used key, any key            | General cache      |
| `allkeys-lfu`       | Evict the least frequently used key, any key          | Skewed access patterns |
| `volatile-lru`      | Evict LRU key, but only keys with a TTL set           | Mixed cache + persistent |
| `volatile-ttl`      | Evict key with the shortest TTL first                 | TTL-managed caches |
| `allkeys-random`    | Evict a random key                                    | Rarely used        |

**LRU** evicts whatever was accessed longest ago — good default for most caches. **LFU** evicts
the least-frequently-accessed key — better when access patterns are skewed (a few keys are
accessed millions of times; LRU would keep recently-accessed-once keys over frequent ones).
`allkeys-lru` is the right default for most caching use cases.

---

### Redis Cluster: Sharding Across Multiple Nodes

For datasets beyond one machine's RAM, **Redis Cluster** spreads keys across nodes using
**16,384 hash slots**: `slot = CRC16(key) % 16384`. Each master node owns a slot range.

```
3-Node Redis Cluster:

  Node A (master): slots 0 – 5460
  Node B (master): slots 5461 – 10922
  Node C (master): slots 10923 – 16383

  Each master has 1-2 replicas for failover.

  Key "user:42":
    CRC16("user:42") % 16384 = 7832
    → goes to Node B

  Key "counter:99":
    CRC16("counter:99") % 16384 = 1105
    → goes to Node A
```

**The multi-key problem**: `MGET key1 key2` fails if the keys live on different nodes.
**Hash tags** fix this: `{user:42}:profile`, `{user:42}:settings`, `{user:42}:preferences`
— Redis hashes only the `{user:42}` part, so all three land on the same node. This is why
production Redis code uses `{}` in key names.

---

## Section 2: DynamoDB — Serverless Key-Value at Scale

### The Mental Model

DynamoDB is Amazon's fully managed key-value and document store. "Fully managed" means no servers
to provision, no replication to configure — Amazon handles operations entirely. The trade-off: you
give up control over internals. The control you must keep is **access pattern design** — DynamoDB
forces you to think about queries before writing the first byte.

### Data Model

```
Table: Orders

  ┌────────────────────────────────────────────────────────┐
  │ PK (Partition Key)   SK (Sort Key)    Other Attributes  │
  │ ──────────────────   ─────────────   ─────────────────  │
  │ USER#42              ORDER#2024-001  total: 99.99       │
  │ USER#42              ORDER#2024-002  total: 15.50       │
  │ USER#42              PROFILE#        name: "Alice"      │
  │ USER#55              ORDER#2024-003  total: 200.00      │
  └────────────────────────────────────────────────────────┘

  PK determines which partition (physical storage node) holds the item.
  SK determines sort order within that partition.
  Items with the same PK but different SK are stored together, sorted by SK.
```

**PK** determines the physical node (hashed). Items with the same PK are co-located.
**SK** (optional) makes (PK, SK) the unique ID; same-PK items are sorted by SK — range scans are a
single contiguous read. **Attributes** beyond the key are schemaless.

### Access Pattern Design First — This Cannot Be Overstated

In SQL, you design a schema and add indexes later. DynamoDB does not work this way. You must
**know your access patterns before you design the table**. Arbitrary filtering requires a full
table scan — reading every item, which is slow and expensive.

The DynamoDB design process:

```
Step 1: List every query your application needs.
  - Get user profile by user ID
  - List all orders for a user, sorted by date
  - Get a specific order by order ID
  - List all open orders across all users (for admin dashboard)

Step 2: For each query, identify what values you will filter on.

Step 3: Design PK + SK so that the most critical queries are
        answered by reading a single partition.

Step 4: For secondary access patterns, design a GSI.
```

Retrofitting access patterns after the fact means rewriting the table design — a painful live migration.

### GSI (Global Secondary Index): Power with a Price

A **GSI** lets you query by attributes that are not the primary key. You define a new (PK, SK) pair
from existing attributes, and DynamoDB maintains a separate projection of the table sorted by those
attributes.

```
Main Table (PK = USER#id, SK = ORDER#date):
  Can answer: "all orders for user X"

GSI: "OrdersByStatus" (PK = status, SK = createdAt):
  Can answer: "all PENDING orders sorted by creation time"
```

**The GSI cost trap**: Every GSI is essentially a separate copy of the data. If you have 3 GSIs:
- Storage cost is 4x (original + 3 indexes)
- Every write to the main table triggers 3 additional writes (one per GSI)
- Your write capacity is consumed 4x for every item write

**Hot GSI partition problem**: If your GSI uses `status` as PK and 90% of items are DELIVERED,
every DELIVERED write hits the same GSI partition — a hot partition that throttles. Fix: use a
more selective GSI key, or shard it (`DELIVERED#1`, `DELIVERED#2`, ...) and query all shards.

### Capacity Modes

| Mode          | How it works                                         | Best For                        |
|---------------|------------------------------------------------------|---------------------------------|
| On-demand     | Pay per request. No capacity planning.               | Unpredictable, spiky traffic    |
| Provisioned   | Specify read/write units per second. Cheaper if steady. | Predictable, steady traffic |

**On-demand** absorbs any spike instantly at ~6-7x the per-request cost of provisioned. Start here
for new applications with unknown traffic. **Provisioned** with auto-scaling is cheaper for steady
workloads, but auto-scaling has a 1-2 minute lag — keep capacity at ~150% of average, not 100%, to
absorb sudden spikes before auto-scaling kicks in.

### DynamoDB Throttling Incident

Flash sale: traffic spikes 10x in 30 seconds. Provisioned capacity handles 3x. Auto-scaling
cooldown is 60 seconds. For those 60-90 seconds, writes get `ProvisionedThroughputExceededException`.
Retries build queue depth. Responses balloon to 5-10 seconds. Users double-click. Duplicate orders.

**Mitigations:** SDK retries with exponential backoff (on by default); buffer writes behind SQS;
use on-demand mode for unpredictable tables; monitor `ThrottledRequests`.

### DynamoDB Partition Distribution: Even vs Skewed

```
Good partition key: userId (millions of users, writes spread evenly)

  Partition 1 ██████████  (user IDs 0000-2499)
  Partition 2 ██████████  (user IDs 2500-4999)
  Partition 3 ██████████  (user IDs 5000-7499)
  Partition 4 ██████████  (user IDs 7500-9999)

  All partitions roughly equal load. Good.

Bad partition key: country (only ~200 values, unevenly populated)

  Partition "US"  ████████████████████████████████  (40% of data)
  Partition "IN"  ██████████████  (20% of data)
  Partition "GB"  ██████  (10% of data)
  Partition "DE"  ████
  Partition "FR"  ████
  ... (196 more with tiny data)

  "US" partition is throttled. All US users slow. Hot partition.
```

The rule: a good partition key has **high cardinality** (many distinct values) and **even
distribution** (no value accounts for a large percentage of writes).

### DynamoDB Streams

**DynamoDB Streams** is a time-ordered log of every table change (insert, update, delete). Attach
a Lambda function to process changes within seconds. Common uses: sync to Elasticsearch, invalidate
Redis cache, trigger welcome emails on new user inserts, write to an audit table.

---

## Section 3: Document Stores — MongoDB Deep Dive

### What a Document Is

A **document** is a JSON-like record stored internally as **BSON** (Binary JSON — adds Date,
ObjectId, binary). The user record below — including nested address — lives in one document.
One read fetches everything. No join required.

```json
{
  "_id": ObjectId("64f2a3b1c9e4d5f6a7b8c9d0"),
  "userId": 42, "name": "Alice", "email": "alice@example.com",
  "address": { "street": "123 Main St", "city": "New York", "zip": "10001" },
  "tags": ["premium", "early-adopter"],
  "createdAt": ISODate("2024-01-15T09:30:00Z")
}
```

### When Documents Make Sense

**Good fit**: Hierarchical data fetched together, where nested parts are not independently queried.

```
RELATIONAL:                            DOCUMENT:
  posts: id | title                      { "_id": 1, "title": "Redis",
  comments: id | postId | text             "comments": [
                                             {"text":"Great!"},{"text":"Nice"}] }

  SELECT * FROM posts                    db.posts.findOne({_id: 1})
  JOIN comments ON posts.id = postId     → 1 read. No join.
  WHERE posts.id = 1
  → 2 table reads + join
```

**Bad fit**: Data that changes independently. An e-commerce order that embeds the product and
customer means: product price changes → update every order document. Customer name changes →
same. Denormalization works until the embedded data mutates frequently.

### The Aggregation Pipeline

MongoDB's **aggregation pipeline** is the equivalent of complex SQL queries — chained stages,
each transforming the document stream.

```javascript
// SQL equivalent: SELECT country, COUNT(*) as userCount,
//                 AVG(age) as avgAge
//                 FROM users
//                 WHERE age > 18
//                 GROUP BY country
//                 ORDER BY userCount DESC
//                 LIMIT 10

db.users.aggregate([
  { $match: { age: { $gt: 18 } } },          // WHERE age > 18
  { $group: {
      _id: "$country",                         // GROUP BY country
      userCount: { $sum: 1 },                 // COUNT(*)
      avgAge: { $avg: "$age" }                // AVG(age)
  }},
  { $sort: { userCount: -1 } },               // ORDER BY userCount DESC
  { $limit: 10 }                              // LIMIT 10
])
```

Stages execute server-side; each receives documents from the previous stage. Key stages:
`$match` (WHERE), `$group` (GROUP BY), `$project` (SELECT columns), `$lookup` (left join),
`$unwind` (flatten array), `$sort` / `$limit` / `$skip` (ordering, pagination).

### MongoDB Indexes

Without an index, every query does a **collection scan** — reads every document (catastrophic at
100M docs). MongoDB indexes are B-trees, same concept as SQL.

**Compound index**: index on multiple fields. Order matters.

```javascript
db.orders.createIndex({ userId: 1, createdAt: -1 })
// 1 = ascending, -1 = descending

// This index efficiently answers:
db.orders.find({ userId: 42 }).sort({ createdAt: -1 })
// "all orders for user 42, newest first"

// But NOT efficiently:
db.orders.find({ createdAt: { $gt: yesterday } })
// createdAt alone cannot use this index — userId must come first
```

**Partial index**: index only a subset of documents.

```javascript
db.orders.createIndex(
  { status: 1 },
  { partialFilterExpression: { status: "PENDING" } }
)
// Only index PENDING orders. Much smaller index.
// Most orders are DELIVERED — no point indexing them here.
```

**Text index**: full-text search within string fields.

```javascript
db.articles.createIndex({ title: "text", body: "text" })
db.articles.find({ $text: { $search: "redis cluster" } })
```

### The Schema Flexibility Trap

"Flexible schema" means **the application must enforce schema**. After two years of development,
your users collection might look like:

```
Document 1 (2022): { name, email, age, plan }
Document 2 (2023): { name, email, subscription_tier, country }
Document 3 (2024): { name, email, tier, country, phone }
```

Three field names for the same concept. Query `{ tier: "pro" }` and you miss documents 1-2.
Analytics are silently wrong. Fix: use **JSON Schema Validation** (MongoDB 3.6+):

```javascript
db.createCollection("users", {
  validator: {
    $jsonSchema: {
      required: ["name", "email", "tier"],
      properties: { tier: { enum: ["free", "pro", "enterprise"] } }
    }
  }
})
```

Without this, data entropy compounds over time until it becomes an engineering crisis.

### Transactions in MongoDB (Since 4.0)

Before 4.0, MongoDB had no multi-document transactions. The workaround was embedding related data
in one document. Since 4.0, **multi-document ACID transactions** work like SQL:

```javascript
const session = client.startSession();
session.startTransaction();
try {
  await accounts.updateOne({ _id: "alice" }, { $inc: { balance: -100 } }, { session });
  await accounts.updateOne({ _id: "bob" },   { $inc: { balance: +100 } }, { session });
  await session.commitTransaction();
} catch (error) {
  await session.abortTransaction();
}
```

The cost: 2-5x slower than single-document operations (WiredTiger snapshot isolation + locks).
Design documents so most operations touch one document — transactions are the exception.

### Replication in MongoDB: Replica Sets

MongoDB uses **replica sets** — 3+ instances where one is the **primary** (accepts writes) and
the rest are **secondaries** replicating changes via the **oplog** (a capped collection of every
write operation, recorded as idempotent ops).

```
Replica Set (3 members):

  ┌──────────┐     oplog stream      ┌──────────┐
  │ Primary  │──────────────────────>│Secondary │
  │ (writes) │                       │ (reads)  │
  └──────────┘                       └──────────┘
       │              oplog stream
       └──────────────────────────> ┌──────────┐
                                    │Secondary │
                                    └──────────┘

  If primary fails: election takes 10-30 seconds. No writes during that window.
```

Reads can go to secondaries (`readPreference: secondary`) for read scaling, with the trade-off
of potentially stale data.

### Sharding in MongoDB

When a replica set cannot handle throughput or data volume, MongoDB supports **sharding** —
splitting a collection across multiple shards (each shard is a replica set). The **shard key**
determines which shard holds each document. The same hotspot rules apply as DynamoDB:

```
Good shard key: userId (high cardinality, even distribution)
Bad shard key: status (low cardinality — "active" dominates one shard)
Bad shard key: createdAt (monotonically increasing — all new writes hit one shard)
```

---

## Section 4: Wide-Column Stores — Cassandra Deep Dive

### The Mental Model

Cassandra is a **distributed sorted map of sorted maps**:
- Outer map: partition key → partition (a set of rows stored on the same node)
- Inner map: clustering key → column values (rows within a partition, physically sorted)

Imagine a filing cabinet spread across hundreds of servers. Each drawer is a partition (identified
by partition key). Inside each drawer, papers are sorted by the clustering key.

### Data Model

```
Keyspace: social_app  (like a database/schema)
  Table: user_timeline

  CREATE TABLE user_timeline (
    user_id    UUID,         ← partition key
    created_at TIMESTAMP,    ← clustering key (sort order)
    post_id    UUID,
    content    TEXT,
    PRIMARY KEY (user_id, created_at)
  ) WITH CLUSTERING ORDER BY (created_at DESC);

Physical storage:

  Partition user:42:
    2024-06-12 15:00  | post:abc | "Redis article"
    2024-06-12 14:30  | post:def | "Cassandra tip"
    2024-06-11 09:00  | post:ghi | "New project!"
    (sorted by created_at DESC within this partition)

  Partition user:55:
    2024-06-12 16:00  | post:jkl | "Hello world"
    ...
```

`SELECT * FROM user_timeline WHERE user_id = 42 AND created_at > ?` reads contiguous bytes on disk.

### The LSM Tree: How Cassandra Actually Stores Data

Cassandra uses the **LSM Tree** (Log-Structured Merge-Tree), not B-trees. This drives every
performance characteristic — when Cassandra is fast, slow, and why tombstones are dangerous.

```
Write Path:

  Client write
      |
      v
  Commit Log (append-only, on disk) ← crash durability (like WAL)
      |
      v
  MemTable (in-memory write buffer, sorted by key)
      |
      v  (when MemTable is full, ~128MB)
  SSTable (immutable, sorted, on disk)


  Multiple SSTables accumulate on disk:
  ┌─────────┐  ┌─────────┐  ┌─────────┐
  │SSTable1 │  │SSTable2 │  │SSTable3 │
  │(older)  │  │(newer)  │  │(newest) │
  └─────────┘  └─────────┘  └─────────┘
       ↑
  Compaction merges these, removes deleted data, produces new SSTable.
```

**Writes are fast**: Commit log is a sequential append (fastest disk operation). MemTable is memory.
No random seeks.

**Reads are potentially slow**: Must check MemTable + multiple SSTables. Cassandra uses **Bloom
filters** to skip SSTables ("this key is definitely NOT in this file") without reading them.

**Compaction**: Background process that merges SSTables into one, keeps the latest version of each
row, discards old tombstones, deletes old SSTables. After compaction: fewer SSTables = faster reads.

### Consistency Levels: The W + R > N Formula

Cassandra is **multi-master** — every node accepts writes. Data is replicated to N nodes
(typically N=3). Per-operation, you choose a **consistency level**: how many replicas must
respond. The formula for strong consistency:

```
W + R > N

Where:
  N = number of replicas (replication factor)
  W = number of replicas that must acknowledge a write
  R = number of replicas that must respond to a read

If W + R > N, then at least one node in the read must have
the latest write. Strong consistency guaranteed.

Common settings with N=3:

  QUORUM: W=2, R=2 → 2+2 > 3 ✓ Strong consistency.
  ONE:    W=1, R=1 → 1+1 = 2, not > 3 ✗ Eventually consistent.
  ALL:    W=3, R=3 → 3+3 > 3 ✓ Strongest, but one node failure = failure.
```

**QUORUM read path with 3-node ring:**

```
  ┌──────────┐   ┌──────────┐   ┌──────────┐
  │  Node A  │   │  Node B  │   │  Node C  │
  │replica 1 │   │replica 2 │   │replica 3 │
  └────┬─────┘   └────┬─────┘   └────┬─────┘
       │              │              │
       │  Read request for key X     │
       │◄─────────────┤              │
       │              │              │
       │  Coordinator sends read to A and B (or any 2)
       │              │
       │  A: returns version 5       │
       │  B: returns version 5       │
       │  Both agree → return version 5 to client
       │
       │  (C is not consulted for QUORUM read)

  If A returns v5 and B returns v4:
  → Coordinator returns v5 (latest wins via timestamp)
  → Triggers read repair: B is sent v5 to update it
```

**LOCAL_QUORUM**: `QUORUM` in a multi-DC setup would wait for remote DCs (high latency).
`LOCAL_QUORUM` requires quorum only within the local DC — strong consistency without cross-DC round trip.

### Tombstones: The Silent Performance Killer

SSTables are immutable — you cannot erase bytes. A delete writes a **tombstone** marker ("this key
deleted at time T"). During reads, tombstone beats live value if it is newer. Tombstones are only
discarded during compaction after `gc_grace_seconds` (default 10 days) — this window ensures a
previously-down node does not resurrect deleted data when it rejoins.

**Why tombstones are dangerous**:

```
Scenario: A chat application stores messages per conversation.
  Messages are deleted by users frequently.

  Table: messages (PK=conversation_id, SK=message_id)

  Users delete messages constantly.
  → Tombstones accumulate in SSTables.

  Read: "Get last 50 messages in conversation:abc"
  → Cassandra must scan and skip thousands of tombstones
    to find 50 live messages.
  → Read latency spikes from 2ms to 2000ms.
  → Cassandra throws TombstoneOverwhelmingException.
  → Application returns 500 errors.
```

**Real incident**: A time-series table runs `DELETE ... WHERE ts < now() - 30days` daily.
Each run creates millions of tombstones. A week later, reads start timing out — Cassandra must
scan the tombstone graveyard to find 50 live records.

**Mitigations**: Use `INSERT ... USING TTL 2592000` instead of explicit deletes — Cassandra writes
tombstones at TTL expiry more predictably. Design tables with time-bucketed partition keys
(`sensor:abc:2024-06`) so you can DROP entire old partitions, bypassing tombstones entirely.
Tune `gc_grace_seconds` downward if your nodes never stay down for 10 days.

### Cassandra Anti-Patterns

**Anti-pattern 1: Large Partitions** — recommended max is 100 MB per partition. Using `user_id`
as partition key for all-time event history lets active users accumulate millions of rows in one
partition (slow reads, minutes-long compaction, unbalanced nodes). Fix: bucket by time:
`PK = (user_id, year_month)` → one small, bounded partition per user per month.

**Anti-pattern 2: Unbounded Wide Rows** — same root cause as large partitions: unlimited
clustering column values per partition key grow forever.

**Anti-pattern 3: ALLOW FILTERING**

```cql
-- Never in production:
SELECT * FROM users WHERE age > 25 ALLOW FILTERING;
-- Full table scan: reads every partition on every node, filters in memory.
-- 100M rows → reads all 100M to return maybe 1000. Times out or OOMs.
```

Rule: every query must be a primary key lookup or clustering-column range scan.
`ALLOW FILTERING` means you need a new table or a secondary index.

---

## Section 5: Graph Databases — When Relationships Are the Data

### What Graphs Are

A **graph** database stores data as **nodes** (entities) and **edges** (relationships) — and both
can carry properties.

```
Nodes: people, products, pages
Edges: FOLLOWS, PURCHASED, LIKED

  (Alice) --FOLLOWS--> (Bob)
  (Alice) --FOLLOWS--> (Carol)
  (Bob)   --FOLLOWS--> (Carol)
  (Carol) --FOLLOWS--> (Dan)

  Properties:
    Alice.age = 30
    FOLLOWS.since = "2023-01-15"
```

In a relational database, relationships are foreign keys — traversal requires joins. In a graph
database, edges are **first-class objects** stored as direct pointers between nodes. Traversal
is pointer-following, not join computation.

### When Graph Databases Win: Social Networks and Fraud

```
"Find everyone Alice follows, who also follows Carol"

RELATIONAL approach (3 tables: users, follows):

  SELECT DISTINCT f2.followed_id
  FROM follows f1
  JOIN follows f2 ON f1.followed_id = f2.follower_id
  WHERE f1.follower_id = alice_id
    AND f2.followed_id = carol_id;

  Cost at depth 2: OK-ish with indexes.
  At depth 3 (friends of friends of friends):
    3 self-joins. Result set explodes.
  At depth 6 (Six Degrees of Separation):
    6 self-joins. Query runs for hours or times out.

GRAPH DB approach (Neo4j, Cypher query):

  MATCH (alice:Person {name:"Alice"})-[:FOLLOWS*1..3]->(target)
  RETURN DISTINCT target

  Cost: constant per traversal step (pointer following).
  Depth 3 = 3 pointer hops per path explored.
  Depth 6 = 6 pointer hops. Still fast.

  ┌───────┐   FOLLOWS   ┌─────┐   FOLLOWS   ┌───────┐
  │ Alice │────────────>│ Bob │────────────>│ Carol │
  └───────┘             └─────┘             └───────┘
                                                │
                                           FOLLOWS
                                                │
                                                v
                                            ┌─────┐
                                            │ Dan │
                                            └─────┘
  Graph traversal: follow the arrows. Each hop is O(degree of node).
  Relational join: recompute the entire intermediate set each time.
```

**Fraud detection**: Find accounts linked by shared device IDs, IPs, or payment methods within
2 hops — a simple graph traversal vs. multiple complex multi-table joins in SQL.

**Recommendation engines**: "Users who bought X also bought Y" is a BOUGHT-edge traversal.

### Cypher Query Example

**Neo4j** uses **Cypher** — you draw the pattern you want, the engine finds it.

```cypher
// Find 2nd-degree connections of Alice who share interests with her

MATCH (alice:Person {name: "Alice"})-[:FOLLOWS]->(friend:Person)
-[:FOLLOWS]->(foaf:Person)           // foaf = "friend of a friend"
WHERE NOT (alice)-[:FOLLOWS]->(foaf) // exclude people Alice already follows
  AND foaf.name <> "Alice"           // exclude Alice herself
WITH foaf, COUNT(DISTINCT friend) as mutualCount
ORDER BY mutualCount DESC
LIMIT 10
RETURN foaf.name, mutualCount

// "Show me 10 people I don't follow, who are followed by the most
//  people I do follow — ranked by mutual connection count"
```

Cypher syntax: parentheses are nodes, arrows are edges. You describe the pattern; the engine finds it.

### When NOT to Use Graph Databases

Graph databases are operationally expensive and shard poorly — highly connected graphs create
cross-node traversals that kill the performance advantage. Do not reach for a graph database
because data "kind of looks like a graph." Use one when:

- Traversal depth is the core query (depth 3+)
- Relationship properties matter (weighted edges, timestamps on edges)
- The query is "find patterns across the graph" (fraud rings, influence paths)

For parent-child or many-to-many relationships at fixed depth, a relational database is simpler.

---

## Putting It Together: Choosing Your NoSQL Store

| If you need...                                | Use...           |
|-----------------------------------------------|------------------|
| Sub-millisecond cache, counters, leaderboards | Redis            |
| Simple K-V at infinite scale, AWS ecosystem   | DynamoDB         |
| Hierarchical documents, flexible schema       | MongoDB          |
| Write-heavy time-series, always-on (no SPOF)  | Cassandra        |
| Deep relationship traversal, fraud detection  | Neo4j / graph DB |

The L6 answer is not just picking a store — it is reasoning about access patterns, consistency
requirements, write/read ratio, and operational cost. Then naming the specific failure mode:
"DynamoDB on-demand fits, but this partition key will cause hot-partition throttling at scale —
here is how I would shard it." That last sentence is what separates principal-level thinking.

---

*End of Part C. Part D covers database internals: B-trees vs LSM trees, WAL, MVCC, and query
planning in depth. Part E covers replication and consensus protocols.*
# Chapter 28, Part D: NewSQL and Distributed SQL Systems

> Part of the "Databases — Choosing, Using, and Evolving Data Stores" series.
> This part covers the systems that tried to kill the SQL-vs-NoSQL debate by doing both.

---

## Why This Part Exists

Parts A through C covered the classical split: relational databases on one side,
NoSQL on the other. Around 2012, engineers started asking the obvious question: why
pick? SQL databases could not scale writes horizontally. NoSQL gave up transactions
to scale. Could someone build a system that did not make you choose?

This part answers that question. We walk through the systems that tried — what they
built, how they solved the hard problems, and where they still fall short. The goal:
explain not just "use Spanner for global transactions" but *why* Spanner can make
that promise and what it costs.

---

## 1. What Problem NewSQL Solves

### The False Dichotomy

Before 2010, the advice was roughly: "If you need scale, use NoSQL. If you need
transactions, use a relational database." This felt like being told you can have
a fast car or a safe car, but not both. The trade-off was real, but it was not
a law of physics. It was an artifact of *how relational databases were built*.

Traditional relational databases like MySQL and PostgreSQL were designed to run on
a single machine. Everything that makes SQL nice — ACID transactions, joins, foreign
keys, consistent reads — was built assuming one clock, one disk, one process
coordinating everything. When you tried to split that across ten machines, the
assumptions broke.

NoSQL systems (Cassandra, DynamoDB, MongoDB) were designed from scratch to run on
many machines. They got horizontal scale by throwing away the parts that were hard
to distribute: strong consistency, multi-row transactions, and joins. The CAP theorem
(covered in Chapter 26) gave this trade-off a theoretical foundation, but engineers
sometimes misread it as "you cannot have both consistency and availability, ever."
That is not quite what CAP says. What CAP says is that you cannot have both *during
a network partition*. Most of the time, there is no partition, and you can have both.

**NewSQL** is the name for a class of systems that took a fresh look and said: given
modern hardware (SSDs, cheap RAM, fast networks), modern consensus algorithms
(Paxos, Raft), and a willingness to pay some latency cost, you actually can build a
system with SQL semantics, horizontal scale, and strong consistency. It is harder.
It requires real engineering. But it is possible.

### The NewSQL Promise

A NewSQL system promises all of the following simultaneously:
- **SQL interface**: standard relational queries, schemas, joins, transactions
- **Horizontal write scale**: add nodes to handle more writes (unlike PostgreSQL)
- **Strong consistency**: ACID transactions, serializable isolation
- **High availability**: survive node and even region failures automatically

This sounds too good to be true, so let us be honest about what you give up:
- **Latency**: distributed consensus takes time. A single-node PostgreSQL commit
  might take 1ms. A cross-region CockroachDB commit might take 150ms.
- **Complexity**: these systems are harder to operate than a single-node database.
- **Cost**: more machines means more money. And the software licenses for Spanner
  are not free.

The right mental model: NewSQL is the right tool when you have genuinely outgrown
a single-node (or primary + replicas) database and *still* need transactional SQL.
It is not a replacement for PostgreSQL when PostgreSQL is working fine.

### Three Approaches to NewSQL

Engineers have taken three different roads to the same destination:

**Approach 1: Distributed Middleware**

Keep MySQL or PostgreSQL as-is; add a sharding layer on top that splits data across
many instances and routes queries. The database itself does not know it is distributed.

Examples: **Vitess** (shards MySQL, used by YouTube), **Citus** (shards PostgreSQL,
used by Cloudflare).

Pros: battle-tested engine underneath, sharding logic is separate.
Cons: cross-shard queries are expensive; cross-shard transactions are limited.

**Approach 2: Purpose-Built Distributed SQL**

The bolder approach. Build a new database from scratch, designed from day one to
run on many machines. The storage layer, the query layer, and the transaction layer
all know they are distributed.

Examples: **Google Spanner**, **CockroachDB**, **TiDB**. These systems are much harder
to build but can offer stronger guarantees — including cross-shard transactions as
a first-class feature.

Pros: True distributed transactions, strong consistency everywhere, survive node
failures transparently.
Cons: Higher latency than single-node databases (consensus takes time), harder to
operate, higher cost.

**Approach 3: Shared-Nothing MPP (for Analytics)**

The same "scale SQL" idea applied to analytical workloads. **Snowflake**, **Amazon
Redshift**, and **Google BigQuery** run SQL at massive scale but are optimized for
columnar scans over large datasets (OLAP), not for small transactional writes (OLTP).
In interview contexts, "NewSQL" almost always refers to OLTP systems like Spanner
and CockroachDB, not Snowflake.

---

## 2. Google Spanner: The Gold Standard

### The Problem Spanner Was Built to Solve

Google runs its own internal payment and advertising systems. Imagine you are charging
an advertiser in Germany for ad clicks that are being recorded in servers in Singapore.
The advertiser's account balance lives in a European data center. The click events
live in an Asian data center. You need a transaction that debits the account and
marks the clicks as billed — atomically, so you never charge twice or miss a charge.

Before Spanner, Google's engineers had to manually shard their data, manually handle
cross-shard transactions (complicated and error-prone), and live with inconsistent
reads (a replica in Singapore might be seconds behind the primary in Europe). They
had a distributed database (Bigtable) but it had no transactions. They had transactional
databases (MySQL-based internal systems) but they did not scale globally.

Spanner, published in 2012, was Google's solution: a globally distributed, strongly
consistent, SQL-queryable database. It is still the benchmark everything else gets
compared to.

### Sharding: Paxos Groups

Spanner divides data into **shards** called "splits." Each split is a contiguous
range of rows, sorted by primary key. For example, a Users table might be split so
that rows with user IDs 0–1,000,000 are in one split, 1,000,001–2,000,000 in the
next, and so on.

Each split is managed by a **Paxos group** — a set of replica servers (usually 5)
that use the Paxos consensus algorithm to agree on every write. Paxos is similar in
spirit to Raft (which we cover when we discuss CockroachDB): one server is the leader
and processes writes; the others are followers. A write is committed only when a
majority of the group (3 out of 5) acknowledges it.

This design means:
- Each split can survive up to 2 replica failures (3 of 5 still forms a majority).
- Reads that need to be consistent go to the Paxos leader. Reads that can tolerate
  slight staleness ("stale reads") can go to any replica, which is much faster.
- Spanner can span continents: one replica in Europe, one in Asia, one in the US.
  The Paxos protocol handles keeping them in sync.

### The Key Innovation: TrueTime

Here is the deepest and most interesting part of Spanner. To understand why TrueTime
matters, you first need to understand why clocks are a problem in distributed systems.

**The clock drift problem:**

Every computer has a hardware clock. Over time, these clocks drift — they run
slightly fast or slow. Network Time Protocol (NTP) is the standard way to correct
this drift: your server periodically asks a time server "what time is it?" and
adjusts its own clock accordingly. NTP is remarkably accurate, but not perfect.
Under normal conditions, NTP gives you accuracy to about ±100ms. In bad network
conditions, the error can be much worse.

Why does ±100ms matter? Imagine two transactions happening in different data centers
at nearly the same time:
- Transaction T1 commits at 12:00:00.050 (as recorded by data center A's clock).
- Transaction T2 commits at 12:00:00.010 (as recorded by data center B's clock).

If data center B's clock is running 100ms slow, what actually happened is that T2
committed at roughly 12:00:00.110 real time — *after* T1. But B's clock says T2
happened first. Now, if someone reads the database and expects to see "T1 before T2,"
they might see the opposite. This is called a **clock skew** problem and it destroys
the guarantees you are trying to make.

**How TrueTime works:**

Google's insight: instead of trying to eliminate clock uncertainty, *quantify it
precisely and work around it*.

Every Spanner data center has two types of hardware:
1. **GPS receivers** synchronized to atomic GPS time (accurate to within tens of
   nanoseconds of true UTC)
2. **Atomic clocks** that drift very slowly even without GPS signal (accurate to
   within microseconds over several hours)

The **TrueTime API** does not return a single timestamp. Instead, it returns an
**interval** `[earliest, latest]` — a range that is *guaranteed* to contain the true
current time. The difference between `earliest` and `latest` is called the
uncertainty interval. Thanks to GPS + atomic clocks, this interval is typically
only about 4–7 milliseconds (much smaller than NTP's ±100ms).

```
TrueTime API:
  TT.now() → Interval{earliest: T - ε, latest: T + ε}
  where ε ≈ 4ms (typical) based on GPS/atomic clock calibration

  Example:
  TT.now() might return {earliest: 1718188800.003, latest: 1718188800.011}
  True time is guaranteed to be somewhere in that 8ms window.
```

**The Commit Wait mechanism:**

TrueTime is the hardware. The algorithm that uses it is called **commit wait**.

When Spanner is about to commit a transaction, it:
1. Calls `TT.now()` to get the current interval `[t_earliest, t_latest]`.
2. Assigns the transaction a commit timestamp equal to `t_latest`.
3. **Waits** until `TT.now().earliest > t_latest` — that is, waits until it is
   *certain* that the commit timestamp is in the past.
4. Only then releases the commit to clients.

The diagram below shows why this wait matters:

```
Timeline (not to scale):

   [T_commit assigned = t_latest]
   |
   |<--- uncertainty window --->|
   |                            |
t_earliest                   t_latest
   |                            |
   |         WAIT               |
   |--------------------------->|
                                |
                         [t_now.earliest > t_latest]
                          NOW SAFE TO COMMIT
                          (true time is definitely past t_latest)

Effect: Any transaction T2 that starts AFTER Spanner releases T1's commit
        will call TT.now() and get t_earliest > t_latest of T1.
        This guarantees T2's timestamp > T1's timestamp.
        This is called EXTERNAL CONSISTENCY.
```

**External consistency** is the property that says: if transaction T2 starts after
T1 commits in real life (i.e., a human sees T1 is done, then triggers T2), then T2's
timestamp is guaranteed to be greater than T1's timestamp. This sounds obvious but is
very hard to achieve without something like TrueTime. External consistency implies
**linearizability** — the strongest form of consistency you can achieve.

The cost of commit wait is 4–14ms of added latency per commit, just from the wait.
Then add network latency for cross-region Paxos, and you see why Spanner commits can
take 50–200ms when your replicas are spread across continents. That is the speed-of-
light problem: light (and therefore network packets) takes about 67ms to travel from
one side of the US to the other. You cannot make a round-trip faster than physics
allows.

### Read Performance: Strong vs. Stale Reads

Not every read needs to be perfectly up-to-date. Spanner gives you a choice:

**Strong reads** go to the Paxos leader for the relevant shard. The leader is always
up-to-date. This is safe for anything that needs to see the latest data — like
checking an account balance before debiting it.

**Stale reads** (also called "bounded staleness" reads) can go to *any* replica.
Spanner guarantees the data is at most N seconds old (you specify N). This is much
faster — you avoid the leader, you can serve from a geographically nearby replica,
and you do not need to go through consensus. For read-heavy workloads where slightly
old data is fine (dashboards, analytics, recommendations), stale reads provide a
huge performance win.

### Spanner at Scale

Spanner serves Google's internal systems at enormous scale. Public figures from
Google's 2017 paper: over 2,000 databases, across 10+ geographic regions. Serving
Google F1 (the ads database) at hundreds of thousands of queries per second with
strong consistency. The overall Google infrastructure runs well over a billion QPS
across all Spanner instances combined.

These numbers matter for your interview: Spanner is not a toy. It is a production
system handling some of the most demanding workloads on the planet. When you recommend
it, you are recommending something battle-tested.

---

## 3. CockroachDB: Open-Source Spanner

Google built Spanner for internal use. CockroachDB (founded 2015 by ex-Google
engineers) set out to build the open-source equivalent — something anyone could
run on commodity hardware without GPS receivers or atomic clocks.

The name comes from a property the founders wanted: cockroaches survive nearly
anything. If nodes die, regions fail, or the network splits, CockroachDB should
keep serving traffic.

### Architecture: Ranges and Raft

CockroachDB divides data into **ranges** — contiguous slices of the key space,
similar to Spanner's splits. The default range size is 512MB. Each range is
replicated across three nodes (configurable to 5 for higher durability).

Instead of Paxos (which Spanner uses), CockroachDB uses **Raft** for consensus.
Raft and Paxos are functionally equivalent — both elect a leader that processes
writes, both require a majority acknowledgment before committing — but Raft is
considered easier to understand and implement correctly. (The original Raft paper
was literally titled "In Search of an Understandable Consensus Algorithm.")

```
CockroachDB 3-Region Deployment:

Region: US-East          Region: EU-West        Region: AP-Southeast
+------------------+     +------------------+   +------------------+
|  Node 1 (Leader) |     |  Node 2 (Follower)|   |  Node 3 (Follower)|
|  Range A         |<--->|  Range A          |<->|  Range A          |
|  Range B (Fol.)  |     |  Range B (Leader) |   |  Range B (Fol.)   |
|  Range C (Fol.)  |     |  Range C (Fol.)   |   |  Range C (Leader) |
+------------------+     +------------------+   +------------------+

Each range has exactly one leader at a time (Raft).
Writes go to the leader, then replicate to followers.
If leader dies, Raft elects a new one from the followers (no human needed).

Raft Commit Flow for Range A (leader in US-East):
  1. Client sends write to US-East (leader)
  2. Leader proposes log entry to followers
  3. EU-West and AP-Southeast receive the proposal
  4. Both acknowledge
  5. Leader marks entry committed (majority = 2 of 3 followers agreed)
  6. Applies to local state, sends ack to client
  
Cross-region commit latency = round-trip US-East <-> EU-West = ~80-120ms
```

### Hybrid Logical Clocks (HLC)

CockroachDB cannot use TrueTime because it does not assume GPS/atomic clocks are
available. Instead it uses **Hybrid Logical Clocks (HLC)**, a clever algorithm first
described by Sandeep Kulkarni and Murat Demirbas in 2014.

An HLC timestamp is a pair: `(physical_time, logical_counter)`.

**Physical time** is just the wall clock (NTP-synchronized). It drifts, can go
backward, and has uncertainty. CockroachDB uses `max_offset` (default 500ms) as the
maximum assumed clock skew between any two nodes.

**Logical counter** is a monotonically increasing integer. It is incremented
whenever the physical time would otherwise be ambiguous — for example, if two events
happen within the same millisecond, or if a node receives a message with a timestamp
in the future (which means the sender's clock is ahead).

The rules:
1. When a node creates an event: `HLC = max(local_physical_time, last_HLC + 1)`.
2. When a node receives a message: `HLC = max(local_HLC, message_HLC + 1)`.
3. This ensures that if event A causally precedes event B (A happened, a message was
   sent, B happened after receiving that message), then `HLC(A) < HLC(B)`.

```
HLC Example:

Node 1 clock: 10:00:00.100
Node 2 clock: 10:00:00.050  (50ms behind — clock drift)

Without HLC:
  T1 on Node1: timestamp = .100
  T2 on Node2: timestamp = .050
  → T2 looks earlier than T1 even if T2 happened after T1!

With HLC:
  Node1 sends message at HLC = (.100, 0)
  Node2 receives it, sees .100 > its own .050
  Node2 sets HLC = (.100, 1)
  → T2's HLC is now (.100, 1) which is > (.100, 0)
  → Causal ordering preserved!

Remaining problem:
  If no messages are exchanged, two concurrent events on different nodes
  can still have ambiguous ordering if their physical clocks are within
  max_offset (500ms) of each other. CockroachDB handles this with
  "uncertainty intervals" — a transaction that reads a value with a
  timestamp within 500ms of its own timestamp will retry to ensure it
  sees the latest version.
```

**The key difference between HLC and TrueTime:**

TrueTime gives you **wall-clock ordering** with a known, tiny uncertainty (4–14ms).
You wait out the uncertainty, and then you have true external consistency.

HLC gives you **causal ordering** — if event A caused event B, B's timestamp is
definitely higher. But for concurrent events with no causal relationship, HLC cannot
give you a total ordering with the same strength as TrueTime.

In practice, this means: CockroachDB offers **serializable isolation** (which is
extremely strong — it is the strictest SQL isolation level), but it does not offer
the same *external consistency* as Spanner. If T1 commits, and then you trigger T2
from a different process that had no communication with the first process, T2's
timestamp *might* be lower than T1's if the clock skew was large. (The transaction
will still be serializable — it will not violate correctness — but the timestamp
ordering might not match wall-clock ordering.)

For almost all applications, this distinction does not matter. For a global financial
system where Google needs to issue legally auditable timestamps tied to real-world
time, it matters.

### CockroachDB Transaction Flow

Let us walk through exactly what happens when your application runs:

```sql
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 'alice';
UPDATE accounts SET balance = balance + 100 WHERE id = 'bob';
COMMIT;
```

Assume alice's account row is in Range A (leader on Node 1) and bob's account row
is in Range B (leader on Node 2).

```
Step 1: Application sends BEGIN to gateway node (could be any node).
        Gateway creates a Transaction Coordinator.

Step 2: UPDATE alice's row (Range A, Node 1):
  - Coordinator sends write to Node 1 (Range A leader).
  - Node 1 does NOT immediately commit. Instead, it writes a
    "WRITE INTENT" — a provisional write record that says:
    "Alice's balance is now X, but this is part of uncommitted
    transaction TXN-42."
  - The original value is preserved alongside the intent.

Step 3: UPDATE bob's row (Range B, Node 2):
  - Same thing. Node 2 writes a WRITE INTENT for TXN-42.

Step 4: COMMIT:
  - Coordinator writes a "TRANSACTION RECORD" to one of the ranges
    (let's say Range A), marking TXN-42 as COMMITTED with a commit
    timestamp assigned by the HLC.
  - Once the transaction record is committed via Raft, the transaction
    is durable — even if the coordinator crashes now, the commit happened.

Step 5: Intent Resolution (asynchronous):
  - Coordinator (or background goroutines) goes back to Range A and Range B
    and replaces the write intents with committed values.
  - This is asynchronous — the client already got a success response.

What if the coordinator crashes after Step 3 but before Step 4?
  - The write intents are left dangling.
  - When the NEXT transaction tries to read alice's or bob's row, it will
    find the intent. It will look up TXN-42's transaction record.
  - If no record exists (coordinator crashed before writing it), the reader
    will ABORT TXN-42 and clean up the intents.
  - Effectively, readers help complete or abort orphaned transactions.
  - This is called "intent resolution" and it means there is no single
    point of failure for transaction cleanup.
```

This design is elegant: the "transaction record" is the single atomic commit point.
Everything before it is provisional; everything after it is cleanup. If the system
crashes at any point, the next reader can determine the correct outcome.

### Survivability Levels

CockroachDB lets you configure how much failure it can survive:

```
CONFIGURE ZONE USING num_replicas = 3,
  constraints = '{+region=us-east1: 1, +region=eu-west1: 1, +region=ap-southeast1: 1}',
  lease_preferences = '[[+region=us-east1]]';
```

| Configuration         | Survives                         | Commit latency       |
|-----------------------|----------------------------------|----------------------|
| 3 replicas, 1 zone    | 1 node failure                   | ~1-5ms               |
| 3 replicas, 3 zones   | 1 zone (AZ) failure              | ~5-20ms              |
| 5 replicas, 3 regions | 1 full region failure            | ~80-150ms            |

The lease preference setting tells CockroachDB which region should hold the Raft
leader (and thus serve writes with low latency) by default. This is a critical
tuning knob for geo-distributed deployments: if 80% of your writes come from
US-East, you want the lease there.

---

## 4. Vitess: Scaling MySQL (YouTube's Solution)

### The Problem

In 2010, YouTube's MySQL database was a single server. Video view counts, user
metadata, comments — all on one machine. As YouTube grew (it was serving hundreds
of millions of views per day by this point), the write load overwhelmed that single
MySQL server. Simply adding read replicas does not help with writes; all writes still
go to one primary server.

YouTube engineers could have migrated to a NoSQL database, but they had years of
SQL logic, MySQL-specific tooling, and operational expertise. They chose instead to
build **Vitess**: a sharding middleware layer that makes many MySQL instances look
like one big database to the application.

Vitess is now an open-source CNCF project and powers not just YouTube but also
PlanetScale (a hosted MySQL service), Slack, GitHub, and many others.

### Components

**VTGate** is the query router. Your application connects to VTGate as if it were
connecting to a single MySQL server. VTGate parses incoming SQL queries, determines
which shard(s) hold the relevant data based on the sharding key, rewrites the query
if necessary (removing sharding-key filters that MySQL does not understand), and
routes the query to the right VTTablet.

**VTTablet** is a sidecar process that runs alongside each MySQL instance. It
manages the connection pool to MySQL, enforces query timeouts, collects metrics, and
handles replication topology changes. Your application never talks to MySQL directly —
only through VTTablet.

**Topology service** (backed by etcd or ZooKeeper) stores the authoritative map of
which shards exist, which VTTablet is primary for each shard, and where each VTTablet
lives. VTGate reads this map to know where to route queries.

```
Vitess Routing Architecture:

  Application
      |
      | (MySQL protocol)
      v
  +--------+
  | VTGate |  <-- Query Router
  +--------+
      |
      | Reads shard map from topology service (etcd)
      |
      +---------------+---------------+
      |               |               |
      v               v               v
  +----------+   +----------+   +----------+
  | VTTablet |   | VTTablet |   | VTTablet |
  | Shard 0  |   | Shard 1  |   | Shard 2  |
  +----------+   +----------+   +----------+
      |               |               |
      v               v               v
  +--------+      +--------+      +--------+
  | MySQL  |      | MySQL  |      | MySQL  |
  | Shard 0|      | Shard 1|      | Shard 2|
  +--------+      +--------+      +--------+

Sharding key: user_id % 3

Query: SELECT * FROM videos WHERE user_id = 12345
  → user_id 12345 % 3 = 0
  → VTGate routes to Shard 0's VTTablet
  → Returns result

Query: SELECT COUNT(*) FROM videos  (no sharding key)
  → VTGate must query ALL shards (scatter)
  → Shard 0 returns 1.2M, Shard 1 returns 1.1M, Shard 2 returns 1.3M
  → VTGate aggregates: returns 3.6M
  → This is expensive — avoid scatter queries in production
```

### The Resharding Challenge

One of Vitess's most impressive features is **online resharding** — splitting a
shard into two without taking the database offline.

Imagine Shard 0 is getting too large. You want to split it: rows with user_id % 6 = 0
stay in Shard 0; rows with user_id % 6 = 3 go to a new Shard 3.

Without Vitess, this would require taking the shard offline, copying data, and
switching over with downtime. With Vitess:

```
Resharding Flow:

Phase 1 - Copy:
  Old Shard 0 (user_id % 3 = 0)
      |
      | Vitess copies rows where user_id % 6 = 3 to new Shard 3
      | Simultaneously, new writes still go to old Shard 0
      v
  New Shard 3 (being populated, not yet serving traffic)

Phase 2 - Catch up:
  Vitess tails the MySQL binlog from old Shard 0.
  Every new write is replicated to new Shard 3.
  Eventually, new Shard 3 is only milliseconds behind old Shard 0.

Phase 3 - Switchover (near-zero downtime):
  VTGate atomically updates its routing rule:
    Before: user_id % 3 = 0 → Shard 0
    After:  user_id % 6 = 0 → Shard 0, user_id % 6 = 3 → Shard 3
  Inflight transactions may get a "please retry" response.
  New transactions route correctly immediately.

Phase 4 - Cleanup:
  Old Shard 0 has the stale rows for Shard 3 deleted.
```

This is not magic — there are edge cases and careful coordination needed — but it
works in production. PlanetScale (the company founded by the Vitess creators) does
this routinely for customers.

### Cross-Shard JOIN Example

A **scatter-gather query** is any query that cannot be satisfied by a single shard.
JOINs are the most common culprit:

```sql
-- Imagine: videos table is sharded by user_id
-- But you want: all videos that user's friends have watched

SELECT v.title, v.view_count
FROM videos v
JOIN watch_history w ON v.video_id = w.video_id
WHERE w.watcher_id IN (
  SELECT friend_id FROM friendships WHERE user_id = 12345
);
```

This query is a nightmare for Vitess because friendships, watch_history, and videos
might all be on different shards. VTGate would have to:
1. Fan out the friendship query to find all friend IDs.
2. Fan out the watch_history query across all shards for those friends.
3. Fan out the video lookup across all shards.
4. Join the results in memory at the VTGate level.

This is called a **scatter-gather** and it is slow. The lesson: when designing a
sharded database schema, you need to think carefully about your sharding key so that
your most common queries stay within a single shard. This is one of the hardest parts
of sharded database design.

---

## 5. Distributed Transactions Deep Dive

### The Fundamental Problem

Imagine you are building a hotel booking system. When a user books a room, you need
to:
1. Deduct the payment from the user's account (in the Payments database).
2. Mark the room as reserved (in the Bookings database).

Both steps must succeed, or neither should. If payment succeeds but booking fails,
the user loses money without a reservation. If booking succeeds but payment fails,
the hotel gives away a free room.

This is the **distributed transaction problem**: how do you achieve atomicity across
multiple independent databases or services?

### Two-Phase Commit (2PC)

**Two-Phase Commit** (2PC) is the classical protocol. It involves two roles:
a **coordinator** (usually the application or a middleware layer) and **participants**
(the individual databases).

```
2PC Flow:

PHASE 1 — PREPARE ("Can you commit?")

Coordinator → Payments DB: "Prepare to debit $200 from user 123"
Payments DB: Locks the row, writes to a "prepared" log, responds "YES"

Coordinator → Bookings DB: "Prepare to reserve room 45 for 2024-07-01"
Bookings DB: Locks the row, writes to a "prepared" log, responds "YES"

PHASE 2 — COMMIT ("Please commit")

Coordinator: Both said YES. Decision: COMMIT.
Coordinator writes COMMIT decision to its own log (DURABLE)

Coordinator → Payments DB: "Commit"
Payments DB: Applies the debit, releases lock, responds "Done"

Coordinator → Bookings DB: "Commit"
Bookings DB: Applies the reservation, releases lock, responds "Done"

--- FAILURE SCENARIO ---

What if the Coordinator crashes AFTER Phase 1, BEFORE Phase 2?

Payments DB: Holds a lock, waiting. Cannot commit on its own.
Bookings DB: Holds a lock, waiting. Cannot commit on its own.

Both databases are BLOCKED until the coordinator recovers.
This is the "2PC blocking problem" — it is a fundamental limitation.
If the coordinator is dead for an hour, the locks are held for an hour.

Mitigation: Coordinators write their decision to durable storage before
Phase 2, so on recovery they can resume. But the window between crash
and recovery is a real outage.
```

2PC is widely used inside single distributed databases (Spanner and CockroachDB both
use a form of 2PC for multi-shard transactions internally). But it is dangerous to
use across services maintained by different teams, because you are coupling their
availability — if one service is slow to respond, everyone blocks.

### Saga Pattern

The **Saga pattern** is an alternative to 2PC for long-running business transactions,
especially when the participating services are owned by different teams and you cannot
count on them all supporting prepare/commit semantics.

The core idea: instead of one atomic transaction, break the business operation into
a series of steps. Each step has a **compensating action** that undoes it if something
later fails.

```
Saga Example: Book a Trip

Forward steps:
  Step 1: Book flight (Flight Service)       → Compensating action: Cancel flight
  Step 2: Reserve hotel (Hotel Service)      → Compensating action: Cancel hotel
  Step 3: Charge credit card (Payment Svc)   → Compensating action: Issue refund

Happy path:
  Step 1 → Success
  Step 2 → Success
  Step 3 → Success
  Done. Trip is booked.

Failure at Step 3 (payment declined):
  Step 3 fails
  → Execute compensation for Step 2: Cancel hotel reservation
  → Execute compensation for Step 1: Cancel flight booking
  System is back to original state (eventually)

Timeline:
  +--------+    +--------+    +--------+
  | Book   | -> | Reserve| -> | Charge |
  | Flight |    | Hotel  |    | Card   |
  +--------+    +--------+    +--------+
       |              |             |
       v              v             v
  [Cancel  ]    [Cancel  ]    [Refund  ]  ← Compensating actions
  [Flight  ]    [Hotel   ]    [Card    ]    (run in reverse on failure)
```

There are two ways to coordinate a Saga:

**Choreography-based Saga**: Each service publishes an event when it completes its
step, and the next service listens for that event and performs its step. No central
coordinator. Services are decoupled — each service only knows about its own events.
Downside: it is hard to track the overall state of a Saga; you have to trace events
across many services to understand what happened.

**Orchestration-based Saga**: A central orchestrator service drives the workflow
explicitly, calling each service and handling failures. Easier to understand and
debug. Downside: the orchestrator is a dependency — if it goes down, in-flight sagas
stall.

For L6 interviews: know when to recommend Saga vs 2PC. The rule of thumb:
- **2PC**: the services are within the same database system (or tightly controlled
  infrastructure), the transaction is short-lived (milliseconds), and blocking on
  coordinator failure is acceptable.
- **Saga**: services are independent, owned by different teams, or span multiple
  databases. The transaction might take seconds or minutes (e.g., "book a trip").
  You can tolerate eventual consistency between steps, as long as the final outcome
  is atomic.

---

## 6. When to Choose What: The Decision Matrix

Do not memorize this table — internalize the reasoning behind each row.

```
+---------------------------+------------------------------------------+----------------------------------+
| Scenario                  | Recommendation                           | Reasoning                        |
+---------------------------+------------------------------------------+----------------------------------+
| Starting a new product,   | PostgreSQL (single primary + read        | Operational simplicity wins.     |
| <10M rows, team of 5      | replicas)                                | Don't over-engineer early.       |
+---------------------------+------------------------------------------+----------------------------------+
| Global financial txns,    | Google Spanner or CockroachDB            | Need external/serializable       |
| correctness paramount     | (multi-region)                           | consistency. Accept 50-200ms     |
|                           |                                          | commit latency.                  |
+---------------------------+------------------------------------------+----------------------------------+
| High write throughput,    | Vitess (MySQL) or Citus (PostgreSQL)     | Keep SQL semantics, add          |
| SQL required, single      |                                          | horizontal write scale via       |
| region                    |                                          | sharding middleware.             |
+---------------------------+------------------------------------------+----------------------------------+
| Mostly reads, SQL,        | PostgreSQL with read replicas + PgBouncer| Read replicas handle 90%+ of     |
| occasional write spikes   | connection pooler                        | load. Much simpler than          |
|                           |                                          | distributed SQL.                 |
+---------------------------+------------------------------------------+----------------------------------+
| Truly multi-region,       | Cassandra or DynamoDB (accept eventual   | If you MUST have <5ms writes     |
| write latency <5ms,       | consistency with LWW or CRDTs)          | globally, you cannot wait for    |
| consistency flexible      |                                          | cross-region consensus.          |
+---------------------------+------------------------------------------+----------------------------------+
| Analytics / OLAP,         | Snowflake, BigQuery, or Redshift         | MPP engines are optimized for    |
| huge scans, not OLTP      |                                          | columnar scans, not OLTP txns.   |
+---------------------------+------------------------------------------+----------------------------------+
| Financial ledger,         | PostgreSQL or Spanner.                   | Never eventual consistency for   |
| money movement            | Never Cassandra/DynamoDB for money.     | money. You need serializable.    |
+---------------------------+------------------------------------------+----------------------------------+
| Long-running business     | Saga pattern across services.            | 2PC across service boundaries    |
| transactions (minutes)    |                                          | is a reliability nightmare.      |
+---------------------------+------------------------------------------+----------------------------------+
```

### The Upgrade Path

Database migrations are gradual. Nobody jumps straight from a startup to Spanner.
The realistic sequence: PostgreSQL primary → add read replicas → add Citus or Vitess
for sharding → migrate to CockroachDB or Spanner only when cross-shard transactions
are genuinely needed. In an interview, if you jump straight to "use Spanner," the
interviewer will ask "why not just PostgreSQL with read replicas?" Be ready to justify
each step up the ladder. A practical rule: if your PostgreSQL primary is below 80%
CPU on writes, you almost certainly do not need distributed SQL yet.

---

## 7. Real Incident: CockroachDB Clock Skew

This incident is valuable because it is concrete, understandable, and illustrates
exactly the theoretical weakness of HLC that we discussed earlier.

### What Happened

A team running a 9-node CockroachDB cluster (3 nodes in each of 3 availability zones)
noticed that one of their nodes began exhibiting strange behavior: it stopped accepting
writes. Client connections were being redirected to other nodes. The team looked at
the CockroachDB logs and found:

```
W210415 14:23:11.500 1 server/node.go:800 clock offset of 623ms is more than
  allowed maximum of 500ms (max_offset); suspected node failure
```

The node had declared itself "suspect" — essentially taken itself out of service.

### Root Cause

That node's NTP synchronization had silently failed. The node's hardware clock had
drifted 623ms ahead of the cluster's agreed-upon time. This exceeded CockroachDB's
`max_offset` of 500ms.

Recall from the HLC discussion: HLC's causal ordering guarantee is only valid if
nodes' physical clocks are within `max_offset` of each other. If a node's clock is
off by more than `max_offset`, the HLC might generate timestamps that violate
consistency. Rather than let this happen, CockroachDB has a safety circuit breaker:
when a node detects that its clock is too far from other nodes' clocks, it refuses
to participate in consensus and marks itself as suspect.

### Impact

The cluster effectively lost one node. With replication factor 3 (one per AZ), the
affected Raft groups dropped to 2 replicas — still a majority, so the cluster stayed
up. A second concurrent failure would have caused some ranges to lose majority and
go offline. The team observed elevated write latency and transient routing errors
while Raft groups elected new leaseholders.

### Resolution

1. The NTP daemon on the offending node was restarted (`sudo systemctl restart ntpd`).
2. Within 2 minutes, the node's clock was back within 500ms of cluster time.
3. CockroachDB detected the recovery and reintegrated the node automatically.
4. No data loss. No manual repair needed.

### Lessons

**Lesson 1: Monitor NTP, always.**
NTP failure is silent. The node looks up, it responds to pings, it passes health
checks — but its clock is drifting. Add NTP sync monitoring to your alerting stack
(check that `ntpq -p` or `chronyc tracking` shows offset < 100ms).

**Lesson 2: Understand your system's Achilles heel.**
CockroachDB's safety mechanism (refusing to serve when clock is too far off) is the
*right behavior*. The alternative — serving with a skewed clock — could silently
violate consistency and corrupt your data in ways that are almost impossible to detect
or fix. A brief outage on one node is far better than silent data corruption.

**Lesson 3: The difference between Spanner and CockroachDB shows up here.**
Spanner's GPS/atomic clock infrastructure means its `ε` (uncertainty interval) stays
at 4–14ms. Clock drift is bounded at the hardware level. CockroachDB's HLC is a
software approximation that depends on OS-level NTP. This is not a reason to never
use CockroachDB — it is excellent software and this incident was mitigated by its
safety circuit breakers — but it is the real cost of not having specialized hardware.

---

## Summary: The Distributed SQL Landscape

| Property                    | PostgreSQL    | Vitess/Citus  | CockroachDB   | Spanner       |
|-----------------------------|---------------|---------------|---------------|---------------|
| SQL interface               | Full          | Full          | Full          | Full          |
| Horizontal writes           | No            | Yes (sharded) | Yes           | Yes           |
| Cross-shard transactions    | N/A           | Limited       | Yes (native)  | Yes (native)  |
| Consistency model           | Serializable  | Per-shard     | Serializable  | Linearizable  |
| Multi-region active-active  | No            | No            | Yes           | Yes           |
| Clock dependency            | None          | None          | NTP (HLC)     | GPS + Atomic  |
| Typical commit latency      | 1-5ms         | 2-20ms        | 5-150ms       | 10-200ms      |
| Operational complexity      | Low           | Medium        | High          | Very high     |
| Open source                 | Yes           | Yes           | Yes           | No (managed)  |

There is no free lunch. Every cell where CockroachDB or Spanner wins over PostgreSQL
comes with a cost in operational complexity or latency. The L6 skill is not knowing
which system is "best" in the abstract — it is knowing *why* you would accept those
costs for a specific workload, and *when* you would not.

---

*Next: Part E covers time-series and specialized data stores — when InfluxDB beats
PostgreSQL, what makes TimescaleDB different from both, and how graph databases like
Neo4j handle queries that would require 12-way JOINs in SQL.*
# Chapter 28 — Part E: Data Modeling and Schema Design Patterns

Schema design is upstream of everything: it determines what queries are fast, what changes are painful, and whether your system holds up under load. This part covers six areas in depth — each a real production problem with multiple patterns and explicit trade-offs.

---

## 1. Normalization vs Denormalization

### What Normalization Actually Is

Imagine you are keeping a paper notebook of customer orders. The naive approach is to write everything on one line:

```
Order #1001 | Jane Smith | jane@email.com | 123 Oak St | Product: Widget A | $10.00
Order #1002 | Jane Smith | jane@email.com | 123 Oak St | Product: Gadget B | $25.00
Order #1003 | Bob Jones  | bob@email.com  | 456 Elm St | Product: Widget A | $10.00
```

Jane's address appears twice. Widget A's price appears twice. This is **redundancy**. Redundancy causes two problems: wasted storage, and inconsistency risk (if Jane moves, you have to find every line and update it, and if you miss one, your data is wrong).

**Normalization** is the systematic process of eliminating this redundancy by splitting data into separate tables, connected by keys. Each fact lives in exactly one place.

### The Three Normal Forms You Need to Know

**First Normal Form (1NF): No Repeating Groups**

A table is in 1NF when every cell contains exactly one value — no lists, no comma-separated values, no JSON arrays crammed into a column.

Wrong (violates 1NF):
```
order_id | customer_name | products
1001     | Jane Smith    | "Widget A, Gadget B, Widget C"
```

Right (1NF):
```
order_id | customer_name | product
1001     | Jane Smith    | Widget A
1001     | Jane Smith    | Gadget B
1001     | Jane Smith    | Widget C
```

The rule of thumb: if you ever find yourself writing `WHERE products LIKE '%Widget%'`, your schema is violating 1NF. You cannot index into the middle of a string efficiently.

**Second Normal Form (2NF): Depend on the Whole Key**

2NF applies when your primary key is composite. Every non-key column must depend on the *entire* primary key, not just part of it.

Consider `order_items` with primary key `(order_id, product_id)`:

```
order_id | product_id | quantity | product_name | product_price
1001     | P001       | 2        | Widget A     | $10.00
1001     | P002       | 1        | Gadget B     | $25.00
```

`product_name` and `product_price` depend only on `product_id` — a **partial dependency**, which violates 2NF. If Widget A's price changes, you update every `order_items` row containing it. Fix: move them to a `products` table.

**Third Normal Form (3NF): No Transitive Dependencies**

3NF requires that non-key columns not depend on *other* non-key columns.

```
employee_id | department_id | department_name | department_floor
E001        | D001          | Engineering     | 3rd Floor
E002        | D001          | Engineering     | 3rd Floor
```

`department_name` and `department_floor` depend on `department_id` (itself non-key) — a **transitive dependency**. Fix: extract a `departments` table.

### The Practical Rule: Normalize Until It Hurts, Denormalize Until It Works

Start with a fully normalized schema. This is your source of truth. Then look at your actual read queries. If they require 5-way JOINs across hot tables and your read:write ratio is 100:1, you have found a place to **denormalize**.

**Denormalization** deliberately reintroduces redundancy to make reads faster. You copy data from one table into another so a query can be served from a single table with no JOINs.

### The Read vs Write Trade-off

This is the core tension. Pick one to optimize:

```
NORMALIZED SCHEMA
  Writes: fast — one row in one table, no duplication
  Reads:  slow — must JOIN multiple tables, database does extra work
  Consistency: high — data lives in one place, can't be inconsistent

DENORMALIZED SCHEMA
  Writes: slow — must update data in multiple tables, keep them in sync
  Reads:  fast — all data in one row, no JOINs
  Consistency: risk — if a write partially fails, tables diverge
```

The design principle: **design around your read:write ratio**. An analytics dashboard that reads 1,000 times per second and writes once per hour should be aggressively denormalized. A banking system that writes constantly and reads rarely should stay normalized.

### ASCII Diagram: Normalized vs Denormalized Orders

**Normalized (3 tables, needs JOINs):**

```
 customers                orders                order_items
+-------------+          +-------------+        +------------------+
| customer_id |<-+       | order_id    |<-+     | order_item_id    |
| name        |  |       | customer_id |--+     | order_id         |--+
| email       |  +-------| created_at  |        | product_id       |--+
| address     |          | total       |        | quantity         |
+-------------+          +-------------+        | unit_price       |
                                                +------------------+
 products                                              |
+-------------+                                        |
| product_id  |<---------------------------------------+
| name        |
| price       |
+-------------+

Query: "Show order with customer name and products"
SELECT c.name, p.name, oi.quantity, oi.unit_price
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
WHERE o.order_id = 1001;
-- 4 table JOIN, but data is consistent
```

**Denormalized (1 table, no JOINs needed):**

```
 order_details (everything in one table)
+------------+--------------+-------------------+-------------+------------+-----------+
| order_id   | customer_id  | customer_name     | customer_email | product_name | quantity |
+------------+--------------+-------------------+-------------+------------+-----------+
| 1001       | C001         | Jane Smith        | jane@...    | Widget A   | 2        |
| 1001       | C001         | Jane Smith        | jane@...    | Gadget B   | 1        |
| 1002       | C001         | Jane Smith        | jane@...    | Widget A   | 1        |
+------------+--------------+-------------------+-------------+------------+-----------+
-- Jane's name and email duplicated on every order row
-- If Jane changes email, UPDATE hits every row she has

Query: SELECT * FROM order_details WHERE order_id = 1001;
-- Single table scan, no JOINs, very fast
-- But: inconsistency risk on writes
```

**Staff insight:** When asked "normalize or denormalize?", the answer is always "it depends on the access pattern." OLTP systems (orders, accounts): normalize. Read-heavy or analytics paths: denormalize or use a read replica with a purpose-built schema.

---

## 2. Access-Pattern-First Design (The NoSQL Approach)

### The Core Mantra: Your Schema IS Your Query

In relational databases, you design a normalized schema first, then write SQL queries that JOIN across tables. Schema and queries are decoupled — SQL is flexible enough to handle most combinations.

In NoSQL (Cassandra, DynamoDB), there is no JOIN. **You design the schema around the queries you need to answer, not around the shape of your domain objects.** Every query must be answerable by scanning a single partition — a unit of data co-located on one node. Multi-partition queries require multiple network hops and are slow.

### The Step-by-Step Design Process

**Step 1: List every query exhaustively.** Before writing any table definition, list every query the application will make. "Find user's timeline" is different from "find all posts by user X" and different from "find post by post_id." In NoSQL, these three queries may require three separate tables.

**Step 2: For each query, design a data structure that answers it in O(1).** O(1) means the query hits exactly one partition, and within that partition, data is pre-sorted in the order needed. "Latest 100 posts by user" → partition keyed by `user_id`, sorted by timestamp descending.

**Step 3: Accept data duplication.** If two queries need the same data in different shapes, store it twice. Write cost is known and bounded. Read cost is O(1) instead of O(N).

### Worked Example: Social Feed Schema in Cassandra

**The queries:**

```
Query 1: Get a user's timeline — latest 100 posts from people they follow
Query 2: Get a specific post by post_id
Query 3: Get all posts by user X (for profile page)
```

**Cassandra schema building blocks:** Every table has a `PARTITION KEY` (determines which node holds the data — all rows with the same key live together) and a `CLUSTERING KEY` (sort order within a partition, ASC or DESC).

**Table for Query 1 (user timeline):**

```sql
CREATE TABLE user_timeline (
    follower_user_id  UUID,         -- partition key: one partition per user
    post_timestamp    TIMESTAMP,    -- clustering key: sorted newest first
    post_id           UUID,
    author_user_id    UUID,
    author_username   TEXT,
    post_text         TEXT,
    PRIMARY KEY (follower_user_id, post_timestamp, post_id)
) WITH CLUSTERING ORDER BY (post_timestamp DESC);
```

Query: `SELECT * FROM user_timeline WHERE follower_user_id = ? LIMIT 100;`

This hits exactly one partition. The LIMIT 100 stops after reading 100 rows off the top of the sorted clustering key. O(1) for the partition lookup, then a sequential read of 100 rows.

**How data gets here:** Every time user A posts, the application inserts a row into the `user_timeline` partition for every follower of A — "fan-out on write." 1 million followers = 1 million writes per post. Expensive writes, cheap reads.

**Table for Query 2 (post by post_id):**

```sql
CREATE TABLE posts_by_id (
    post_id           UUID,         -- partition key: each post is its own partition
    post_timestamp    TIMESTAMP,
    author_user_id    UUID,
    author_username   TEXT,
    post_text         TEXT,
    like_count        COUNTER,
    PRIMARY KEY (post_id)
);
```

Query: `SELECT * FROM posts_by_id WHERE post_id = ?;`

One partition key, one row lookup. Absolutely O(1).

**Table for Query 3 (all posts by user X):**

```sql
CREATE TABLE posts_by_author (
    author_user_id    UUID,         -- partition key: one partition per author
    post_timestamp    TIMESTAMP,    -- clustering key: newest first
    post_id           UUID,
    post_text         TEXT,
    PRIMARY KEY (author_user_id, post_timestamp, post_id)
) WITH CLUSTERING ORDER BY (post_timestamp DESC);
```

Query: `SELECT * FROM posts_by_author WHERE author_user_id = ? LIMIT 50;`

Notice: `user_timeline` and `posts_by_author` hold overlapping data. This is intentional — two tables for two queries.

**Why the timeline schema cannot answer Query 3:** In `user_timeline`, the partition key is `follower_user_id`. Finding all posts by author X requires scanning every user's timeline partition — millions of partitions, effectively a full table scan. You need `posts_by_author` with `author_user_id` as the partition key.

**The write cost is explicit and bounded:**

```
When user A posts:
  - Insert into posts_by_id: 1 write
  - Insert into posts_by_author: 1 write
  - Insert into user_timeline for each follower: N writes (where N = follower count)

Read cost for any query: 1 partition lookup (O(1))
```

In interviews, saying "I'll write to multiple tables to support multiple read patterns" is the correct and expected answer for NoSQL systems — this is the trade-off made visible.

---

## 3. Schema Evolution Strategies

### The Core Problem

Your schema will change, but old data does not auto-migrate. During a deployment, old code and new code run simultaneously — old code reading an old schema, new code expecting a new one. Get this wrong and you get data corruption or downtime.

### Strategy 1: Add-Only Migrations (The Safest Approach)

**Never remove or rename, only add.** Adding a nullable column is safe — old code ignores it, new code uses it. Dropping a column while old code runs can cause constraint violations. Renaming is a drop + add: old code writing to `user_email` breaks the moment you rename it to `email`.

**The four-phase safe migration:**

```
TIMELINE OF SAFE COLUMN ADDITION / MIGRATION

Phase 1: Add nullable column, deploy nothing yet
  DB state: [old_columns] + [new_column nullable]
  Code: old code running, ignores new_column (NULLs everywhere)

  Week 1         Week 2         Week 3         Week 4
  |              |              |              |
  v              v              v              v
+-----------+  +-----------+  +-----------+  +-----------+
| DB: add   |  | Code:     |  | Backfill: |  | DB: make  |
| nullable  |->| deploy    |->| run job   |->| NOT NULL  |
| column    |  | new code  |  | to fill   |  | (optional)|
|           |  | reads &   |  | old rows  |  |           |
|           |  | writes it |  |           |  |           |
+-----------+  +-----------+  +-----------+  +-----------+
                                   |
                    (backfill: UPDATE table SET new_col = derived_value
                               WHERE new_col IS NULL)
```

This approach guarantees: at no point in time is there a mismatch between the schema the database has and what any running version of the code expects.

**What NOT to do:**
```sql
-- Never do this while old code is still running:
ALTER TABLE users RENAME COLUMN user_email TO email;
-- Old code: INSERT INTO users (user_email, ...) → ERROR: column "user_email" does not exist
-- New code: SELECT email FROM users → Works
-- Result: old pods crash, mixed fleet = partial outage
```

### Strategy 2: Expand-Contract Pattern (For Renaming and Restructuring)

Use the **Expand-Contract** pattern (also called **parallel-write migration**) for renaming or restructuring. It runs in four phases across multiple deployments:

```
EXPAND-CONTRACT FOR RENAMING "user_email" TO "email"

Phase 1 — EXPAND (add new column alongside old):
  DB: [user_email, email (nullable)]
  Code v1: reads/writes user_email only
  Deploy: ALTER TABLE ADD COLUMN email TEXT;

  [user_email]  [email]
  "a@x.com"     NULL
  "b@x.com"     NULL

Phase 2 — DUAL WRITE (write to both, read from old):
  Code v2: writes to BOTH user_email AND email
  reads from user_email (still authoritative)
  Deploy: new version of application

  [user_email]  [email]
  "a@x.com"     "a@x.com"    <- new rows have both
  "b@x.com"     NULL         <- old rows backfilled separately

Phase 3 — READ FROM NEW (verify data, switch reads):
  Run backfill to fill email for all rows where email IS NULL
  Code v3: reads from email (now authoritative), still writes both
  Deploy: verify data integrity, flip read source

Phase 4 — CONTRACT (remove old column):
  Code v4: writes to email only, user_email no longer referenced in any code
  Deploy: ALTER TABLE DROP COLUMN user_email;
  DB: [email]

MINIMUM 4 SEPARATE DEPLOYMENTS — cannot skip phases
```

**Why this matters in multi-service environments:** Service A and Service B both read from the users table. Rename a column in one deployment and Service B (not yet updated) breaks instantly. Expand-Contract lets both services continue working throughout all four phases.

### Strategy 3: Versioned Schemas for NoSQL

Relational databases have ALTER TABLE to change schema across all rows. MongoDB and DynamoDB have no such operation — documents can have different shapes in the same collection.

The solution is **schema versioning**: add a `schema_version` field to every document.

```json
// Old document (schema_version: 1)
{
  "_id": "user_123",
  "schema_version": 1,
  "name": "Jane Smith",
  "address": "123 Oak Street, Springfield, IL 60601"
}

// New document (schema_version: 2)
{
  "_id": "user_456",
  "schema_version": 2,
  "name": "Bob Jones",
  "address": {
    "street": "456 Elm St",
    "city": "Springfield",
    "state": "IL",
    "zip": "60601"
  }
}
```

Your application code handles both versions:

```python
def get_user_city(doc):
    if doc["schema_version"] == 1:
        # Parse city from "123 Oak Street, Springfield, IL 60601"
        parts = doc["address"].split(", ")
        return parts[1] if len(parts) >= 2 else None
    elif doc["schema_version"] == 2:
        return doc["address"]["city"]
    else:
        raise ValueError(f"Unknown schema version: {doc['schema_version']}")
```

**Lazy migration on read:** When a v1 document is read, the application upgrades it to v2 and writes it back. Over time, all documents migrate without a single large batch job:

```python
def read_user(user_id):
    doc = db.users.find_one({"_id": user_id})
    if doc["schema_version"] < CURRENT_VERSION:
        doc = migrate_document(doc)
        db.users.replace_one({"_id": user_id}, doc)
    return doc
```

**Trade-off:** Your application code accumulates migration logic over time. By schema_version 15, you have 14 migration paths to maintain. The code complexity grows. But you avoid risky large-scale migrations on live data.

### Strategy 4: Event Sourcing for Ultimate Flexibility

In a normal system you store **current state**: one row per user, overwritten on update. History is lost. **Event sourcing** stores every event that changed the state, in order. Current state = replay of all events.

```
events table:
+----------+------------------+-----------------------------+------------+
| event_id | aggregate_id     | event_type                  | payload    |
+----------+------------------+-----------------------------+------------+
| 1        | user_123         | UserCreated                 | {name: "Jane", email: "old@..."} |
| 2        | user_123         | EmailChanged                | {email: "new@..."} |
| 3        | user_123         | AddressUpdated              | {address: {...}} |
+----------+------------------+-----------------------------+------------+

Current state of user_123:
  name: "Jane"     (from event 1, never overwritten)
  email: "new@..."  (from event 2, supersedes event 1)
  address: {...}    (from event 3)
```

**Schema evolution is easy with event sourcing**: new event types are additive. Old events represent things that happened in the past and are always valid. Adding a field to `EmailChanged` simply means old `EmailChanged` events lack that field — your code handles the absence gracefully.

**Trade-offs of event sourcing:**
- Replay time grows with history. 10,000 events per entity is slow to reconstruct. Solution: **snapshots** — periodically serialize current state, replay only from the last snapshot forward.
- Querying is harder: "find all users in California" requires a projection (derived read model) or a full event scan.
- Best suited for domains where audit history is essential (finance, healthcare) or business logic is complex enough to justify the overhead.

---

## 4. Time-Series Data Modeling

### The Problem: Scale and Query Shape

1,000 sensors × 1 reading/sec × 86,400 sec/day = **86.4 million rows per day**. A year: 31.5 billion rows. Standard modeling (one row per reading, index on `(sensor_id, timestamp)`) works at small scale. At 31.5 billion rows, index leaf pages for historical data fall out of cache and every query requires disk I/O — slow.

### Cassandra Time-Series Model

Cassandra is a natural fit for time-series because its partition-clustering model maps exactly to the time-series access pattern.

**Basic schema:**

```sql
CREATE TABLE sensor_readings (
    sensor_id    TEXT,
    timestamp    TIMESTAMP,
    value        DOUBLE,
    unit         TEXT,
    PRIMARY KEY (sensor_id, timestamp)
) WITH CLUSTERING ORDER BY (timestamp DESC)
  AND default_time_to_live = 2592000;  -- 30 days TTL, auto-expire
```

Query: `SELECT * FROM sensor_readings WHERE sensor_id = 'sensor_42' LIMIT 3600;`

One partition per sensor, sorted by timestamp. The latest hour of data is at the "top" of the partition. No table scan. Pure sequential read after a single partition lookup.

**The hot partition problem with time bucketing:**

As time goes on, one sensor's partition grows without bound. Cassandra has a practical limit on partition size (a few hundred MB to a few GB). A sensor writing once per second will generate a massive partition over years.

Solution: **bucket the partition key by time**.

```sql
CREATE TABLE sensor_readings_bucketed (
    sensor_id    TEXT,
    bucket_day   DATE,           -- e.g., '2024-01-15'
    timestamp    TIMESTAMP,
    value        DOUBLE,
    PRIMARY KEY ((sensor_id, bucket_day), timestamp)
) WITH CLUSTERING ORDER BY (timestamp DESC);
```

Now each partition covers one sensor on one day. A year of data = 365 partitions per sensor. Each partition is bounded in size.

**Trade-off:** Queries that span multiple days must query multiple partitions and merge results in the application. For most time-series dashboards (show last 24 hours), you only cross a single day boundary at midnight — manageable.

```
PARTITION KEY DISTRIBUTION WITH BUCKETING

Without bucketing:                With bucketing:
  sensor_42 partition               sensor_42 | 2024-01-01  partition (24h of data)
  [ALL readings ever]               sensor_42 | 2024-01-02  partition (24h of data)
  size: grows forever               sensor_42 | 2024-01-03  partition (24h of data)
  eventually hits limits            size: bounded, predictable

  sensor_43 partition               sensor_43 | 2024-01-01  partition
  [ALL readings ever]               sensor_43 | 2024-01-02  partition
                                    ...
```

**TTL (Time To Live):** Cassandra allows setting a TTL on individual rows. When TTL expires, Cassandra marks the row as a tombstone and eventually deletes it. You never run a DELETE job — expiration is automatic. For IoT or metrics where raw data beyond 30 days is not needed, this is a major operational win.

### TimescaleDB: PostgreSQL for Time-Series

**TimescaleDB** is a PostgreSQL extension that turns a regular table into a **hypertable** — a table that automatically partitions itself by time behind the scenes.

```sql
-- Create a normal table
CREATE TABLE sensor_readings (
    sensor_id  TEXT        NOT NULL,
    timestamp  TIMESTAMPTZ NOT NULL,
    value      DOUBLE PRECISION,
    unit       TEXT
);

-- Convert to hypertable, partition by timestamp in 1-day chunks
SELECT create_hypertable('sensor_readings', 'timestamp', chunk_time_interval => INTERVAL '1 day');
```

After this, TimescaleDB creates a new chunk (sub-table) for each day. Queries with a time predicate hit only the relevant chunks — not the entire table. This is called **chunk pruning**.

**Continuous aggregates** (a killer feature):

```sql
-- Pre-compute hourly averages, kept up-to-date automatically
CREATE MATERIALIZED VIEW sensor_hourly_avg
WITH (timescaledb.continuous) AS
SELECT
    sensor_id,
    time_bucket('1 hour', timestamp) AS hour,
    AVG(value)  AS avg_value,
    MAX(value)  AS max_value,
    MIN(value)  AS min_value,
    COUNT(*)    AS reading_count
FROM sensor_readings
GROUP BY sensor_id, time_bucket('1 hour', timestamp);

-- TimescaleDB refreshes this view incrementally as new data arrives
-- Dashboard queries hit the pre-aggregated view, not raw data
```

**Retention policies and compression:**

```sql
-- Drop data older than 1 year automatically
SELECT add_retention_policy('sensor_readings', INTERVAL '1 year');

-- Compress chunks older than 7 days (90%+ size reduction)
SELECT add_compression_policy('sensor_readings', INTERVAL '7 days');
```

TimescaleDB's compression uses columnar storage for old chunks — delta-of-delta encoding for timestamps and run-length encoding for repeated IDs. Real-world compression ratios of 90–95% are common.

### InfluxDB Data Model

**InfluxDB** uses a completely different model than SQL. Data is organized around **measurements** (analogous to a table name), **tags** (indexed metadata), **fields** (numeric values), and a **timestamp**.

```
measurement: cpu_usage
tags:         host=web-01, region=us-east-1, env=prod
fields:       user=45.2, system=12.1, idle=42.7
timestamp:    2024-01-15T12:00:00Z
```

Tags are indexed (low-cardinality metadata: region, host). Fields are not indexed (raw numeric values). Never put a high-cardinality value like `user_id` in a tag — the index explodes. InfluxDB is excellent for Prometheus-style metrics with its Flux query language for rolling averages, derivatives, and rate calculations.

### When to Choose Each System

| Use Case | Best Choice | Reason |
|---|---|---|
| Write-heavy IoT, simple queries | Cassandra | Linear scale, tunable TTL, no SQL overhead |
| Complex SQL + time | TimescaleDB | Full PostgreSQL, JOINs, continuous aggregates |
| Infrastructure metrics, Prometheus | InfluxDB | Purpose-built, Grafana integration |
| Already on PostgreSQL | TimescaleDB | No new infra, extension install |
| Massive distributed scale (global) | Cassandra | Multi-datacenter replication built-in |
| Need ad-hoc SQL aggregations | TimescaleDB | Familiar SQL, continuous aggregates |

---

## 5. Multi-Tenant Data Isolation Patterns

### The Problem

In a SaaS product, all customers share the same application but their data must never mix — not just in the UI, but at the database level. There are four patterns with different isolation/cost trade-offs.

### Pattern 1: Shared Schema (Shared Tables with tenant_id)

Every table has a `tenant_id` column. All tenants' data lives together in the same tables.

```sql
CREATE TABLE users (
    user_id    UUID PRIMARY KEY,
    tenant_id  UUID NOT NULL,
    email      TEXT NOT NULL,
    name       TEXT
);

CREATE INDEX idx_users_tenant ON users (tenant_id, user_id);
```

Every query includes `WHERE tenant_id = current_tenant_id`. In PostgreSQL, you can enforce this automatically with **Row-Level Security (RLS)**:

```sql
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON users
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
-- Now no query can return rows from another tenant, even if a bug forgets WHERE
```

**Trade-offs:** Cheapest — no per-tenant overhead. Weakest isolation — a missing WHERE clause exposes cross-tenant data (RLS helps). All indexes need `tenant_id` as the leading column. A noisy tenant degrades performance for all others.

### Pattern 2: Separate Schema per Tenant (Same Database, Different Namespace)

Each tenant gets their own PostgreSQL **schema** (a namespace within the database):

```
Database: saas_db
  Schema: tenant_00001
    users, orders, products, ...
  Schema: tenant_00002
    users, orders, products, ...
  Schema: tenant_00003
    users, orders, products, ...
```

PostgreSQL `search_path` is set per connection to route to the right schema:

```sql
SET search_path TO tenant_00001;
SELECT * FROM users;  -- hits tenant_00001.users, not tenant_00002.users
```

**Schema migrations** must run against every tenant schema. With 5,000 tenants, a migration that fails on tenant 2,347 leaves 2,346 tenants migrated and the rest on the old schema — a split-brain state. Better isolation than shared schema, but still one DB server. Migration complexity grows with tenant count.

### Pattern 3: Separate Database per Tenant

Each tenant gets their own database server (or at least their own database instance). A separate connection pool routes each request to the right database.

**Trade-offs:** Full isolation — a crash affects only one tenant. But 10,000 tenants × AWS RDS = $4.3M/month. Not viable alone.

**Solution: database pooling with a routing layer.** A tenant router maps `tenant_id → db connection string`. Multiple tenants share a physical server, but the routing layer makes it *look* like each has its own database.

```
Tenant Router
+---------------------------+
| tenant_id → db_server_id  |
| tenant_001 → db_server_A  |
| tenant_002 → db_server_A  |
| tenant_big → db_server_B  |  (large tenant, dedicated)
| tenant_003 → db_server_A  |
+---------------------------+
     |              |
  db_server_A    db_server_B
  (shared)       (dedicated)
```

**When to choose:** Regulated industries (healthcare under HIPAA, finance under SOX) where contractual or legal SLAs require physical isolation between customers' data. Enterprise contracts that specify "your data is on a dedicated server."

### Pattern 4: Shard by Tenant

Large tenants get their own shard. Small tenants share shards. A **shard assignment service** maps each tenant to a shard, and tenants migrate between shards as their usage grows. This is what Salesforce does: largest customers get dedicated database pods, free-tier customers share pods with thousands of others.

### ASCII Diagram: Four Patterns Side-by-Side

```
PATTERN 1: Shared Schema           PATTERN 2: Separate Schema
+-----------------------------+    +-----------------------------+
|          Database           |    |          Database           |
|  Table: users               |    |  Schema: tenant_001         |
|  +--------+---------+       |    |    Table: users             |
|  |user_id |tenant_id|       |    |  Schema: tenant_002         |
|  |u1      | t001    |       |    |    Table: users             |
|  |u2      | t001    |       |    |  Schema: tenant_003         |
|  |u3      | t002    |       |    |    Table: users             |
|  |u4      | t002    |       |    +-----------------------------+
|  +--------+---------+       |    Isolation: MEDIUM
|  All tenants mixed          |    Migrations: complex (N schemas)
+-----------------------------+
Isolation: LOW (RLS helps)

PATTERN 3: Database per Tenant     PATTERN 4: Shard by Tenant
+----------+ +----------+          +--Shard A--+ +--Shard B--+
| DB: t001 | | DB: t002 |          | t001      | | t_big     |
|  users   | |  users   |          | t002      | |           |
|  orders  | |  orders  |          | t003      | |  (large   |
+----------+ +----------+          +--Shard A--+  tenant,   |
 ...                               Small tenants  dedicated) |
Isolation: FULL                    share shards. +--Shard B--+
Cost: HIGH ($$$)                   Isolation: MEDIUM-HIGH
```

---

## 6. Hierarchical Data in Relational Databases

### The Problem

Hierarchical data appears everywhere: nested comment threads, org charts, category trees. In a relational database, parent-child relationships of unknown depth are non-trivial. There are three patterns, each optimizing for a different operation.

### The Example Tree

We will use a 5-node comment tree for all examples:

```
      [1: "Great post!"]
       /               \
[2: "Thanks!"]    [3: "Agree!"]
      |
[4: "You're welcome"]
      |
[5: "Anytime"]
```

### Pattern 1: Adjacency List (parent_id Column)

The simplest approach: each row stores the `parent_id` of its immediate parent.

```sql
CREATE TABLE comments (
    comment_id  INTEGER PRIMARY KEY,
    parent_id   INTEGER REFERENCES comments(comment_id),  -- NULL for root
    text        TEXT,
    author_id   INTEGER
);

INSERT INTO comments VALUES
(1, NULL, 'Great post!',        user_1),
(2, 1,    'Thanks!',            user_2),
(3, 1,    'Agree!',             user_3),
(4, 2,    'You''re welcome',    user_2),
(5, 4,    'Anytime',            user_2);
```

Getting immediate children is O(1): `SELECT * FROM comments WHERE parent_id = 1`.

**Getting all descendants requires a recursive query:**

```sql
WITH RECURSIVE comment_tree AS (
    -- Base case: start from root
    SELECT comment_id, parent_id, text, 0 AS depth
    FROM comments
    WHERE comment_id = 1

    UNION ALL

    -- Recursive step: find children of current level
    SELECT c.comment_id, c.parent_id, c.text, ct.depth + 1
    FROM comments c
    JOIN comment_tree ct ON c.parent_id = ct.comment_id
)
SELECT * FROM comment_tree ORDER BY depth;
```

**Problem:** Recursive CTEs execute as iterative scans — one pass per tree level. Performance degrades with depth. Most comment threads stay under 5–10 levels, so this is acceptable in practice. Best when: tree is shallow, insertions are frequent, structure changes often.

### Pattern 2: Nested Sets (Left/Right Numbering)

**Nested Sets** assigns two numbers to each node (`lft` and `rgt`) via a depth-first traversal, incrementing a counter each time you enter or leave a node.

```
Traversal assigns numbers:
      [1: lft=1, rgt=10]
       /                 \
[2: lft=2, rgt=7]    [3: lft=8, rgt=9]
      |
[4: lft=3, rgt=6]
      |
[5: lft=4, rgt=5]

Table:
comment_id | lft | rgt | text
1          | 1   | 10  | Great post!
2          | 2   | 7   | Thanks!
3          | 8   | 9   | Agree!
4          | 3   | 6   | You're welcome
5          | 4   | 5   | Anytime
```

**The insight:** all descendants of node X have `lft` between X's `lft` and X's `rgt`. To find all descendants of node 1 (lft=1, rgt=10):

```sql
SELECT * FROM comments WHERE lft > 1 AND rgt < 10;
-- Returns all 4 children and grandchildren in one scan
```

This is a single range scan — no recursion. For read-heavy hierarchies, this is very fast.

**The write problem:** Inserting a new node requires renumbering all lft/rgt values after the insertion point. Adding a child to node 3 (lft=8, rgt=9) means updating every node with lft or rgt >= 9. In a 100,000-node tree, that is potentially 50,000 UPDATE statements — a table lock on every insert.

```sql
-- Adding a child to node 3 (lft=8, rgt=9):
-- 1. Shift all lft/rgt values >= 9 by 2
UPDATE comments SET rgt = rgt + 2 WHERE rgt >= 9;
UPDATE comments SET lft = lft + 2 WHERE lft >= 9;
-- 2. Insert new node with lft=9, rgt=10
INSERT INTO comments (comment_id, lft, rgt, text) VALUES (6, 9, 10, 'New reply');
-- This locks the table and requires updating many rows
```

**Nested sets are best when:** the tree is read far more than written (product category trees, static org charts), you need fast subtree retrieval, and the tree changes infrequently.

### Pattern 3: Closure Table (All Ancestor-Descendant Pairs)

The **Closure Table** approach keeps a separate table that stores every ancestor-descendant pair, at every depth.

```sql
CREATE TABLE comment_closure (
    ancestor_id    INTEGER REFERENCES comments(comment_id),
    descendant_id  INTEGER REFERENCES comments(comment_id),
    depth          INTEGER,
    PRIMARY KEY (ancestor_id, descendant_id)
);
```

For our 5-node tree:

```
ancestor_id | descendant_id | depth
1           | 1             | 0      (self-reference)
1           | 2             | 1
1           | 3             | 1
1           | 4             | 2
1           | 5             | 3
2           | 2             | 0
2           | 4             | 1
2           | 5             | 2
3           | 3             | 0
4           | 4             | 0
4           | 5             | 1
5           | 5             | 0
```

**Getting all descendants of node 1:**

```sql
SELECT c.*
FROM comments c
JOIN comment_closure cc ON c.comment_id = cc.descendant_id
WHERE cc.ancestor_id = 1 AND cc.depth > 0;
-- Single JOIN, uses index on ancestor_id, extremely fast
```

**Getting all ancestors of node 5 (breadcrumb trail):**

```sql
SELECT c.* FROM comments c
JOIN comment_closure cc ON c.comment_id = cc.ancestor_id
WHERE cc.descendant_id = 5 AND cc.depth > 0
ORDER BY cc.depth DESC;
-- Returns: node 4, node 2, node 1
```

**Inserting** a node at depth D requires D+1 inserts into the closure table — one self-reference plus one per ancestor. Predictable and bounded.

```sql
-- Insert new comment (id=6) as child of comment 4
-- Step 1: copy all ancestor rows of parent (id=4), incrementing depth by 1
INSERT INTO comment_closure (ancestor_id, descendant_id, depth)
SELECT ancestor_id, 6, depth + 1
FROM comment_closure
WHERE descendant_id = 4;

-- Step 2: add self-reference
INSERT INTO comment_closure VALUES (6, 6, 0);
```

**Deleting a subtree:** `DELETE FROM comment_closure WHERE descendant_id IN (SELECT descendant_id FROM comment_closure WHERE ancestor_id = 4);` then delete from the comments table.

**Trade-off:** Storage grows at O(N * average_depth). Depth 1 = 2N rows. Depth 50 = 50N rows. Real storage cost, usually acceptable given read performance.

### Comparison of All Three Patterns

```
SAME 5-NODE TREE — THREE REPRESENTATIONS

Adjacency List:               Nested Sets:              Closure Table:
+--------+--------+           +--------+-----+-----+    +----------+-------------+-------+
|comment | parent |           |comment | lft | rgt |    | ancestor | descendant  | depth |
+--------+--------+           +--------+-----+-----+    +----------+-------------+-------+
| 1      | NULL   |           | 1      | 1   | 10  |    | 1        | 1           | 0     |
| 2      | 1      |           | 2      | 2   | 7   |    | 1        | 2           | 1     |
| 3      | 1      |           | 3      | 8   | 9   |    | 1        | 3           | 1     |
| 4      | 2      |           | 4      | 3   | 6   |    | 1        | 4           | 2     |
| 5      | 4      |           | 5      | 4   | 5   |    | 1        | 5           | 3     |
+--------+--------+           +--------+-----+-----+    | 2        | 2           | 0     |
                                                        | 2        | 4           | 1     |
Get subtree:                  Get subtree:              | 2        | 5           | 2     |
  WITH RECURSIVE               WHERE lft > 2            | 3        | 3           | 0     |
  (recursive CTE)              AND rgt < 7              | 4        | 4           | 0     |
  O(depth) queries             O(1) range scan          | 4        | 5           | 1     |
                                                        | 5        | 5           | 0     |
Insert node:                  Insert node:              +----------+-------------+-------+
  SET parent_id               UPDATE N rows             Get subtree:
  1 write                     O(N) update storm           JOIN on ancestor_id
  Fast                        Slow for large trees        O(1) index lookup
```

| Operation | Adjacency List | Nested Sets | Closure Table |
|---|---|---|---|
| Get immediate children | O(1) | O(1) | O(1) |
| Get all descendants | O(depth), recursive CTE | O(1) range scan | O(1) index join |
| Get all ancestors | O(depth), recursive CTE | O(1) range scan | O(1) index join |
| Insert a node | O(1) | O(N) renumber | O(depth) inserts |
| Delete subtree | O(depth), recursive | O(N) renumber | O(subtree size) |
| Storage overhead | None | None | O(N * avg_depth) |
| **Best for** | Frequent inserts, shallow trees | Read-heavy, static trees | Read-heavy, any depth |

**Recommendation for interviews:** Comment systems (write-heavy, shallow) → Adjacency List. Product categories or org charts (read-heavy, rarely change) → Nested Sets. Large-scale threads needing efficient ancestor/descendant queries at any depth → Closure Table. PostgreSQL's `WITH RECURSIVE` makes Adjacency List viable for most real applications — start there unless you have evidence of a depth-scaling problem.

---

## Summary

At an L6 interview, knowing these patterns exist is table stakes. What earns the hire is reasoning about *when to apply each one and why*:

- **Normalization vs Denormalization**: write cost vs read cost. Design around your read:write ratio.
- **Access-Pattern-First Design**: mandatory in NoSQL. The schema is the query. Duplicate data to serve different read patterns.
- **Schema Evolution**: must be zero-downtime. Add-only migrations and Expand-Contract. Never rename a column in a single deployment.
- **Time-Series Modeling**: bucket partition keys to bound partition growth. Use TTL for expiry. Cassandra for write-heavy/simple, TimescaleDB for complex SQL + time, InfluxDB for pure metrics.
- **Multi-Tenant Isolation**: a spectrum from shared tables (cheap, weak) to database-per-tenant (expensive, full). Match to regulatory requirements and tenant count.
- **Hierarchical Data**: Adjacency List (simple, shallow trees), Nested Sets (fast reads, expensive writes), Closure Table (fast reads at any depth, extra storage). Start with Adjacency List and `WITH RECURSIVE` unless you have a measured depth problem.
# Chapter 28, Part F: Database Scaling and Sharding Patterns

---

## Why This Part Exists

You picked the right database. You modeled your schema carefully. You wrote clean queries. And then your system grew, and now the database is the bottleneck. Every interview at Staff Engineer level will eventually ask: *"Okay, but how does this scale?"*

This part answers that question in full. We will walk through every step on the scaling ladder — from buying a bigger server all the way to splitting your data across dozens of machines — and explain why each step is harder than the last, and why you should delay the hard steps as long as possible.

---

## Part F.1 — The Scaling Ladder: Do These In Order

Think of database scaling like trying to move a growing library. At first you buy taller shelves. Then you get better librarians. Then you open a second reading room. Eventually you open a second branch. Each step makes sense — but each step also costs more to manage. You don't open a second branch the day you overflow your first bookshelf.

The same logic applies to databases. There is a **scaling ladder** — a sequence of steps in roughly increasing order of operational complexity. The trap that kills teams is skipping rungs. Engineers who jump straight to sharding because it sounds impressive end up with a distributed system that is vastly harder to operate, debug, and evolve than a well-tuned single-node database would have been.

Here is the ladder. Follow it in order.

```
┌──────────────────────────────────────────────────────────────────────┐
│                 THE DATABASE SCALING LADDER                          │
│                                                                      │
│   COMPLEXITY ▲                                                       │
│              │                                                       │
│   HIGH       │  Step 5: Sharding ◄── last resort, big commitment    │
│              │                                                       │
│              │  Step 4: Read Replicas ◄── good for read-heavy load  │
│              │                                                       │
│              │  Step 3: Caching ◄── often eliminates 80% of reads   │
│              │                                                       │
│              │  Step 2: Query Optimization ◄── frequently 100x gain │
│              │                                                       │
│   LOW        │  Step 1: Vertical Scaling ◄── start here, always     │
│              └─────────────────────────────────────────────────────► │
│                                                    SCALE REACHED     │
└──────────────────────────────────────────────────────────────────────┘
```

### Step 1: Vertical Scaling (Bigger Box)

**Vertical scaling** means upgrading the machine your database runs on — more CPU cores, more RAM, faster SSDs. It is unglamorous. It is also frequently the correct answer.

Let's be concrete about how far vertical scaling can take you.

**CPU**: Modern cloud instances offer up to 128 vCPUs. PostgreSQL uses parallel query execution — a single complex analytical query can fan out across dozens of cores. For OLTP workloads (short transactional queries), more cores means more concurrent connections can be served simultaneously. A 32-core server handles roughly 4x the concurrent connections of an 8-core server before CPU becomes the bottleneck.

**RAM**: AWS offers instances with up to 24 TB of RAM (u-24tb1.metal). Most production databases are far smaller than that. The reason RAM matters so much for databases is the **buffer pool** — the portion of RAM the database uses to cache disk pages. When your working set (the pages you access frequently) fits in RAM, reads become memory operations at nanosecond speeds rather than disk operations at millisecond speeds. This is a 100,000x difference. A PostgreSQL database serving 100 GB of frequently-accessed data on a 128 GB RAM instance will perform dramatically better than the same database on a 16 GB RAM instance — even though all the data is "on disk" in both cases.

**Storage**: NVMe SSDs deliver sequential reads at 7 GB/s and random reads at hundreds of thousands of IOPS. This is orders of magnitude faster than the spinning disks that dominated data centers until recently. Many "scaling problems" are actually storage I/O problems that disappear entirely when moving from HDD to SSD.

**The cost curve**: Vertical scaling costs money linearly — a server with 4x the RAM costs roughly 4x as much. This is predictable and manageable. Compare that to the engineering time required to shard a database, which typically runs to months and introduces an entirely new class of operational risk. The break-even point where vertical scaling becomes more expensive than the engineering cost of alternatives is much higher than most teams think.

**When to stop vertical scaling**: When the next tier of instance costs more per unit of performance than the benefit you receive, or when you hit the ceiling of available instances in your cloud provider. In practice, most teams should exhaust vertical scaling before considering alternatives. A well-tuned PostgreSQL database on a 64-core, 512 GB RAM server can handle enormous workloads.

---

### Step 2: Query Optimization — Often 100x Before Any Hardware Change

Before spending money on hardware or engineering time on architecture, look at your queries. Slow queries are often not a capacity problem — they are a correctness problem. A query that scans the entire table instead of using an index is not slow because the database is small; it is slow because it is doing unnecessary work.

**Missing indexes**: The most common cause of slow queries by a wide margin. A **database index** is a separate data structure (usually a B-tree) that stores a sorted copy of one or more columns, allowing the database to find rows without scanning the entire table. Without an index, finding a user by email requires reading every row — an **O(n) full table scan**. With an index, the same query is **O(log n)** — finding one user in a table of 100 million takes roughly 27 comparisons instead of 100 million.

The tool for diagnosing this in PostgreSQL is `EXPLAIN ANALYZE`:

```sql
-- This shows the query plan and actual execution time
EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'alice@example.com';

-- Without index: you'll see "Seq Scan on users" — bad
-- Seq Scan on users  (cost=0.00..2831.00 rows=1 width=234)
--                    (actual time=15.234..15.234 rows=1 loops=1)

-- After creating index: you'll see "Index Scan" — good
CREATE INDEX idx_users_email ON users(email);
-- Index Scan using idx_users_email on users  (cost=0.42..8.44 rows=1 width=234)
--                                            (actual time=0.032..0.032 rows=1 loops=1)
```

The speedup from 15ms to 0.032ms — a 500x improvement — required zero hardware changes.

**N+1 queries**: This is a bug that hides in application code and looks like a database problem. Imagine you are rendering a page that shows 20 blog posts, each with its author's name. An N+1 pattern does this:

```
1. Query: SELECT * FROM posts LIMIT 20     ← 1 query
2. For each post:
   Query: SELECT name FROM users WHERE id = ?  ← 20 more queries
Total: 21 queries per page load
```

The fix is a JOIN or a batch fetch:

```sql
-- One query instead of 21
SELECT posts.*, users.name
FROM posts
JOIN users ON posts.author_id = users.id
LIMIT 20;
```

At low traffic, N+1 queries are merely wasteful. At 1,000 requests/second, each triggering 21 queries, you have 21,000 queries per second where 1,000 would suffice. The database appears overloaded. It is — but the fix is the application, not the database.

**Inefficient query patterns**: `SELECT *` fetches every column even when you need two. On a wide table (many columns, especially with large text or JSON fields), this dramatically increases the amount of data transferred and the size of working set needed in memory. Always select only the columns you need.

Unbounded queries — `SELECT * FROM events WHERE user_id = 123` without a `LIMIT` — can return millions of rows if a user has been active for years. Always paginate. Always use `LIMIT`.

**Connection leaks**: Databases support a limited number of concurrent connections (PostgreSQL defaults to 100). Each connection consumes memory (~5-10 MB in PostgreSQL). Applications that open connections without reliably closing them will exhaust the connection pool and cause all queries to queue or fail. Use a **connection pooler** like **PgBouncer** — it sits between your application and PostgreSQL and multiplexes thousands of application connections onto a smaller pool of actual database connections.

```
WITHOUT PgBouncer:
  App Server 1: 50 connections ──────────────────► PostgreSQL (max 100)
  App Server 2: 50 connections ──────────────────► PostgreSQL
  App Server 3: 50 connections ──► REFUSED — connection limit hit

WITH PgBouncer:
  App Server 1: 500 connections ──► PgBouncer ──► 10 connections ──► PostgreSQL
  App Server 2: 500 connections ──► PgBouncer ──┘ (pooled)
  App Server 3: 500 connections ──► PgBouncer ──┘
```

PgBouncer operates in three modes: **session pooling** (a server connection is assigned to a client connection for its entire duration — minimal benefit), **transaction pooling** (a server connection is reused after each transaction — large benefit, most commonly used), and **statement pooling** (even finer-grained — rare and incompatible with multi-statement transactions). Transaction pooling is the standard recommendation: it allows thousands of app connections to share dozens of database connections because most of the time a connection is idle between transactions.

The symptom of a connection exhaustion problem: query latency spikes to seconds, the database log shows "remaining connection slots are reserved for non-replication superuser connections", and restarting application servers temporarily relieves pressure. The fix is PgBouncer, not more database connections — adding more connections increases PostgreSQL's memory pressure and context-switching overhead.

---

### Step 3: Caching

**Read caching** is placing a fast in-memory store in front of your database to absorb repeated reads. **Redis** is the dominant tool for this. The idea is simple: the first time you read a user's profile, fetch it from the database and store a copy in Redis with an expiry time (**TTL, time-to-live**). Subsequent reads for the same profile return from Redis in under a millisecond, without touching the database at all.

```
WITHOUT CACHE:
  Request → Database → Response
  (every request hits the DB)

WITH CACHE:
  Request → Redis ─── HIT ──► Response   (sub-millisecond)
               └── MISS ──► Database → Cache → Response
```

**What to cache**: Data that is read frequently, changes infrequently, and whose slight staleness is acceptable. User profiles, product descriptions, configuration settings. Do NOT cache financial balances, inventory counts, or anything where reading a stale value would cause correctness problems.

**TTL strategy**: Setting TTL too short means frequent cache misses and high database load. Setting TTL too long means serving stale data. A reasonable default is 5–60 minutes for data that changes occasionally, seconds for data that changes often. Some data (like a user's authentication session) can be cached for hours.

**Cache invalidation**: When the underlying data changes, the cached copy must be invalidated (deleted or updated). This is notoriously difficult. The two strategies are:

- **Write-through**: When you write to the database, also update the cache. Data is always fresh but writes are slower.
- **Cache-aside (lazy loading)**: Only populate the cache on a read miss. Simpler, but briefly stale after a write. Use `DEL cache_key` on writes to force a fresh load on next read.

**Cache stampede**: Imagine 10,000 users are on your site and all of them have the same cached item expire at exactly the same time (because all of them loaded it when a batch process refreshed it). Suddenly, all 10,000 requests go to the database simultaneously. This is the **thundering herd** or **cache stampede** problem.

Fix 1: **Probabilistic early expiration (PER)** — when a cache item is near expiry, a small random fraction of requests fetch a fresh copy even before expiry, staggering the refreshes over time. The formula: a request recomputes early with probability `exp(-delta * beta * log(rand()))` where `delta` is the time remaining and `beta` is a tuning parameter. You do not need to memorize the formula for interviews — just knowing the concept and naming it impresses interviewers.

Fix 2: **Request coalescing** — when multiple concurrent requests all miss the same cache key, only one is allowed to fetch from the database. The others wait. When the first returns, all receive the same result and it is written to cache. The database sees one request, not a thousand. Implementation: use a distributed lock (Redis `SET NX` with a short TTL) on the cache key during population. Requests that fail to acquire the lock briefly wait and then retry the cache read.

Fix 3: **Staggered TTLs** — instead of setting all cache entries to expire at `now + 300s`, set them to expire at `now + 300s + random(0, 30s)`. Entries that were all loaded at the same moment will now expire spread over 30 seconds rather than simultaneously. Simple and effective.

A useful mental model: cache stampedes are a **thundering herd** problem — many processes simultaneously trying to do the same expensive work. The general solution class is always: either stagger when they decide to do the work (PER, jittered TTLs) or ensure only one does the work while others wait (coalescing, locks).

---

### Step 4: Read Replicas

A **read replica** is a copy of your primary database that receives a continuous stream of changes from the primary and applies them in order. The replica is kept approximately up to date — usually within milliseconds — but cannot accept writes.

**How streaming replication works** (PostgreSQL model): Every write to PostgreSQL is first written to the **Write-Ahead Log (WAL)** — a sequential log of all changes. This log is the single source of truth for all data in the database. Replicas connect to the primary and receive a stream of WAL records. They apply these records to their own copy of the data. The replica is in a constant state of "catching up" — when write traffic is low, it may be only milliseconds behind; under heavy write load, it may fall further behind.

```
PRIMARY DATABASE:
  Writes → WAL ──► data files (the primary's copy)
               └──► streams to Replica 1
               └──► streams to Replica 2
               └──► streams to Replica 3

REPLICAS:
  Receive WAL stream → apply changes → serve read queries
```

**Replication lag monitoring**: The gap between what the primary has written and what the replica has applied is called **replication lag**. You must monitor this. A replica that is 30 seconds behind is useless for anything where users expect to see their own recent writes. Query: `SELECT now() - pg_last_xact_replay_timestamp() AS replication_lag;` on the replica.

Replication lag can spike for several reasons: a large write (bulk import, batch update) generates a burst of WAL records faster than the replica can apply them; a slow query on the replica holds a lock and blocks WAL application; or network bandwidth between primary and replica is saturated. Alert when lag exceeds your SLA threshold — for most user-facing services, anything above 5 seconds warrants investigation.

A subtlety: **synchronous replication** forces the primary to wait for at least one replica to confirm receipt before acknowledging the write to the client. This eliminates replication lag for that replica but adds write latency. PostgreSQL supports synchronous replication with `synchronous_commit = on`. Use it for data you cannot afford to lose even in the event the primary crashes immediately after acknowledging a write. Most teams use asynchronous replication (the default) for throughput and accept the small window of potential data loss.

**What to route to replicas**:
- Analytics and reporting queries (long-running, read-only)
- Background jobs that read data
- Dashboard queries
- "Popular posts this week" type aggregations

**What NOT to route to replicas**:
- The "read your own writes" pattern: after a user submits a form, the page that says "success" often reads back the data you just wrote. If this read goes to a replica that is even 100ms behind, the user sees their old data, or worse, sees nothing. Route these reads to the primary.
- Any read where the result affects a subsequent write decision (balance checks, inventory checks before purchase).

A simple rule: **if correctness depends on reading the latest write, use the primary**.

---

### Step 5: Sharding (When All Else Fails)

**Sharding** means partitioning your data across multiple independent database nodes so that each node holds only a fraction of the total data. This is the step that most teams should spend months trying to avoid. When you do need it, everything gets harder: queries that span multiple shards require network round trips, transactions that touch multiple shards require distributed coordination, and operational complexity multiplies with the number of shards.

We will cover sharding in depth in the sections that follow.

A common question: "when exactly should I add a shard?" There is no universal threshold, but useful heuristics:

- Write latency on the primary exceeds your SLA at your peak traffic level, even after query optimization.
- The working set (actively accessed data) no longer fits in available RAM, causing frequent disk reads even with indexes.
- The primary's CPU sits above 80% consistently during business hours, not just during batch jobs.
- A single table has grown beyond roughly 100–500 GB and index builds are impractically slow.

If none of these apply, you do not need sharding yet.

---

## Part F.2 — Sharding Deep Dive

### What Sharding Actually Is

Imagine your `users` table has grown to 2 billion rows. A single database server, even with fast SSDs and indexes, struggles to process 50,000 writes per second while also serving millions of reads — the data is just too large and the I/O bandwidth of a single machine has limits.

Sharding splits this table across, say, 8 database servers. Server 1 holds users 1–250 million. Server 2 holds users 250M–500M. And so on. Each server now manages only 1/8 of the data and handles only 1/8 of the traffic. Both storage and throughput scale horizontally.

The cost: **every query must now know which shard to go to**. And any operation that touches data on multiple shards requires coordinating across a network.

### Why Sharding Is Hard

- **Joins across shards are network calls.** A SQL JOIN that takes microseconds on a single database now requires fetching data from two different servers across a network, reassembling it in application memory, and doing the join manually. This is 10–100x slower and far more complex to implement.
- **Transactions across shards require distributed coordination.** Ensuring that a debit on Shard 1 and a credit on Shard 2 either both commit or both roll back requires a protocol like two-phase commit, which is slow and can block if a participant crashes.
- **Schema changes become a rolling migration.** Altering a table across 16 shards without downtime requires careful orchestration.
- **Operational tooling multiplies.** Backup, restore, monitoring, and debugging now apply to N machines instead of one.
- **Auto-increment IDs break.** If Shard 1 and Shard 2 both generate IDs starting at 1, you get conflicts when you try to merge or query across shards. You must switch to globally unique IDs — UUIDs, Twitter Snowflake-style IDs (timestamp + machine ID + sequence), or a dedicated ID generation service.
- **Global uniqueness constraints become impossible.** A `UNIQUE` constraint on `email` in PostgreSQL ensures no two users have the same email. In a sharded system, each shard enforces uniqueness only within itself. Two shards can independently accept the same email for different users. You must enforce global uniqueness in application code, using a separate deduplicated lookup table on a non-sharded store.

None of this is insurmountable, but you must enter sharding with clear eyes about what you are signing up for.

### Choosing the Shard Key: The Most Important Decision

The shard key is the column (or combination of columns) used to determine which shard a given row lives on. Choosing poorly forces you to reshard later — one of the most painful operations in distributed systems. Criteria for a good shard key:

**High cardinality**: The key should have many distinct values. Sharding by `country` (200 distinct values, very unequal in size) means some shards receive vastly more traffic than others. Sharding by `user_id` (billions of distinct values) distributes traffic evenly.

**Even distribution**: The key's values should be roughly uniformly distributed. Numeric IDs with hash-based sharding satisfy this. Alphabetical names with range-based sharding often do not (many more names start with common letters).

**Query locality**: Queries should hit as few shards as possible. If 90% of queries are "get all data for user X", sharding by user ID ensures those queries hit exactly one shard. If queries are "get all orders in region Y" and you shard by user ID, every region query is a scatter-gather.

**Immutability**: The shard key for a given row should not change. If it does, you must delete the row from its current shard and re-insert it in the new shard — complex and dangerous to do atomically. Use identifiers that never change (user ID, order ID) rather than mutable attributes (username, status).

---

### Sharding Strategy 1: Range-Based Sharding

**Range-based sharding** divides the key space (the values of the shard key) into contiguous ranges and assigns each range to a shard.

Example: A user database sharded on the first letter of the username.

```
┌──────────────────────────────────────────────────────────────────┐
│                  RANGE-BASED SHARDING EXAMPLE                    │
│                                                                  │
│   User names starting with:                                      │
│                                                                  │
│   A – F  ──────────────────► Shard 1  [alice, bob, carol, ...]   │
│   G – M  ──────────────────► Shard 2  [george, henry, ivan, ...]  │
│   N – Z  ──────────────────► Shard 3  [nancy, omar, pete, ...]    │
│                                                                  │
│   RANGE QUERY: "Users starting with A–C"                        │
│   ─────────────────────────────────────                         │
│   Goes entirely to Shard 1. Efficient!                          │
└──────────────────────────────────────────────────────────────────┘
```

**Advantage**: Range queries that align with the shard key stay on a single shard. "Give me all orders from January" on a time-sharded database touches only the January shard. This is efficient.

**Problem — hotspots**: In practice, data is not uniformly distributed. If you shard a time-series event log by date, today's shard receives all writes while historical shards receive no writes. This is a **write hotspot** — one shard is overloaded while others are idle.

```
HOTSPOT PROBLEM:
─────────────────
  Shard Jan  [cold - no new writes]   ████ (full of old data)
  Shard Feb  [cold - no new writes]   ████
  Shard Mar  [cold - no new writes]   ████
  Shard Apr  [HOT - all writes go here!]  ████████████████ OVERLOADED

  At any given moment, 75% of shards are idle. One shard is on fire.
```

For user databases sharded by first letter, all new user signups (in a growing system) go to Shard 3 (N–Z) if new users disproportionately have names in that range, while Shard 1 (A–F) may have mostly deleted or dormant accounts. This imbalance compounds over time.

---

### Sharding Strategy 2: Hash-Based Sharding

**Hash-based sharding** applies a hash function to the shard key and uses the result to determine the shard. The most basic form is:

```
shard_number = hash(user_id) % num_shards
```

A hash function maps arbitrary inputs to a fixed-size output that appears random. User ID 12345 might hash to shard 3. User ID 12346 might hash to shard 0. There is no pattern that a client can exploit to overload any single shard — writes are distributed uniformly.

```
┌──────────────────────────────────────────────────────────────────┐
│                  HASH-BASED SHARDING                             │
│                                                                  │
│   user_id: 1001  →  hash(1001) % 4 = 1  → Shard 1              │
│   user_id: 1002  →  hash(1002) % 4 = 3  → Shard 3              │
│   user_id: 1003  →  hash(1003) % 4 = 0  → Shard 0              │
│   user_id: 1004  →  hash(1004) % 4 = 2  → Shard 2              │
│                                                                  │
│   Even distribution: each shard gets ~25% of traffic            │
└──────────────────────────────────────────────────────────────────┘
```

**Advantage**: Uniform write distribution. No hotspots from write traffic.

**Problem 1 — range queries are impossible**: You cannot ask "give me all users with IDs between 1000 and 2000" efficiently. You have no idea which shards those IDs live on. You must send the query to ALL shards and merge the results — this is called **scatter-gather**. Scatter-gather is expensive: it takes as long as the slowest shard to respond, and it multiplies database load by the number of shards.

**Problem 2 — resharding requires moving half your data**: Suppose you start with 4 shards and the system grows. You add a 5th shard. Now `hash(user_id) % 5` gives different answers than `hash(user_id) % 4` for most keys. Almost all data is now assigned to the wrong shard. You must move roughly 80% of all data — during live traffic — to the correct shards. This is extremely dangerous.

Consistent hashing (next section) solves Problem 2. The scatter-gather problem on range queries is an inherent trade-off of hash-based sharding.

---

### Sharding Strategy 3: Directory-Based Sharding

**Directory-based sharding** maintains an explicit lookup table that maps each key (or key range, or tenant) to a shard. A central **metadata service** answers the question: "which shard holds data for tenant X?"

```
┌────────────────────────────────────────────────────────────────────┐
│              DIRECTORY-BASED SHARDING                              │
│                                                                    │
│   Client Request: "Get data for tenant Acme Corp"                 │
│          │                                                         │
│          ▼                                                         │
│   ┌─────────────────┐                                             │
│   │  Metadata Svc   │  Lookup: "Acme Corp" → Shard 7             │
│   │  (lookup table) │                                             │
│   └────────┬────────┘                                             │
│            │                                                       │
│            ▼                                                       │
│   ┌─────────────────┐                                             │
│   │    Shard 7      │  Return Acme Corp's data                    │
│   └─────────────────┘                                             │
│                                                                    │
│   Directory entries:                                               │
│     Acme Corp      → Shard 7                                      │
│     BetaCo         → Shard 2                                      │
│     Gamma Inc      → Shard 2  (multiple tenants per shard is OK)  │
│     Delta LLC      → Shard 9  (moved from Shard 5 last Tuesday)   │
└────────────────────────────────────────────────────────────────────┘
```

**Advantage**: Maximum flexibility. You can move a single tenant from one shard to another without affecting any other tenant. When a large customer's data grows, you can migrate them to a dedicated shard. This is how multi-tenant SaaS systems typically work in practice.

**Problem 1 — single point of failure**: If the metadata service is unavailable, no queries can be routed to the correct shard. All requests fail. You must make the metadata service highly available (replication, multi-region, etc.).

**Problem 2 — extra latency hop**: Every request adds one network round trip to the metadata service before it can reach the actual database. Caching the directory on each application server mitigates this — but then you have the familiar cache invalidation problem when a tenant moves.

---

## Part F.3 — Consistent Hashing

### Why Naive Mod-N Hashing Breaks on Resharding

Go back to simple hash sharding. You have 4 shards. The rule is `shard = hash(key) % 4`. Key "user:1001" hashes to, say, 7654321, and `7654321 % 4 = 1`, so it lives on Shard 1.

Now you add a 5th shard. The new rule is `hash(key) % 5`. Key "user:1001" hashes to `7654321 % 5 = 1`... actually the same shard. But most keys won't be so lucky. Consider any key where `hash(key) % 4 = k` — when you change to `% 5`, most of them will map to different shards. Specifically, when you go from N to N+1 shards, on average **(N/(N+1))** of all keys map to a different shard. Going from 4 to 5 shards, that's 80% of all data potentially moving. This is catastrophic.

### How Consistent Hashing Works

**Consistent hashing** maps both keys and nodes to positions on a circular ring that spans values from 0 to 2^32 (about 4 billion positions). Think of the ring as a clock face, except instead of 12 positions it has 4 billion.

- Each node (database shard) is hashed to one or more positions on the ring.
- Each key is hashed to a position on the ring.
- A key is assigned to the **first node clockwise from its position** on the ring.

```
┌──────────────────────────────────────────────────────────────────────┐
│                    CONSISTENT HASH RING                              │
│                                                                      │
│                         0                                            │
│                    ┌────┴────┐                                       │
│              Node A│         │                                       │
│         (pos: 50)  *         * Node B (pos: 170)                    │
│                   /           \                                      │
│                  /     RING    \                                     │
│   key "u:9"     /  (0 → 2^32)  \                                    │
│   (pos: 130) ──►*               *◄── key "u:2" (pos: 210)           │
│   → goes to B   \               /    → goes to C                   │
│                  \             /                                     │
│         Node C    *           *                                      │
│         (pos: 300) └─────────┘                                      │
│                                                                      │
│   Rules:                                                             │
│     key at pos 130 → first node clockwise → Node B (pos 170) ✓     │
│     key at pos 210 → first node clockwise → Node C (pos 300) ✓     │
│     key at pos 350 → wraps around → Node A (pos 50) ✓              │
└──────────────────────────────────────────────────────────────────────┘
```

**Adding a node — only O(1/n) of keys move**: When you add Node D at position 250, only the keys between position 170 (Node B's position) and 250 need to move from Node C to Node D. All other keys are unaffected.

```
BEFORE adding Node D:
  Keys 171–300 → Node C

AFTER adding Node D at position 250:
  Keys 171–250 → Node D  (moved here)
  Keys 251–300 → Node C  (unchanged)
  All other keys: unchanged
```

When you had 3 nodes and add a 4th, only 1/4 of the keys need to move — exactly as many as the new node will own. This is a huge improvement over mod-N hashing.

**Virtual nodes** solve the balance problem. With only one position per physical node, the ring segments are unequal by chance — one node might end up responsible for 40% of the key space while another handles 5%. **Virtual nodes** assign each physical node K positions on the ring (e.g., K=150). The positions are spread around the ring pseudo-randomly. With enough virtual nodes, each physical node ends up owning approximately 1/n of the key space regardless of where the actual positions fall.

```
PHYSICAL vs VIRTUAL NODES:

  Physical: 3 nodes, 1 position each → unequal segments
    Node A: pos 50
    Node B: pos 170
    Node C: pos 300
    Segment sizes: A=50, B=120, C=130+50=180  ← unequal!

  With 3 virtual nodes per physical node (K=3):
    Node A: pos 50, 200, 350
    Node B: pos 80, 160, 280
    Node C: pos 30, 220, 310
    → More evenly interleaved around the ring
```

Real-world usage: **Cassandra**, **Redis Cluster**, and **Memcached** all use variants of consistent hashing. Cassandra uses virtual nodes (vnodes) extensively, defaulting to 256 virtual nodes per physical node.

**The hotspot problem that consistent hashing does NOT solve**: Consistent hashing distributes *different* keys evenly. It says nothing about how often each key is accessed. If one key — say, a celebrity's profile — receives 10,000 requests per second while all other keys receive 1 request per second, that key's node is still overloaded no matter how perfectly the ring is balanced.

The fix is **key splitting**: instead of one cache or shard entry for `user:123`, you create N entries: `user:123:shard:0`, `user:123:shard:1`, ..., `user:123:shard:N-1`. Writes go to all N copies. Reads go to a randomly chosen copy. This distributes the hot key's load across N nodes. The cost: N copies of the data, and writes are N times as expensive. Use sparingly for confirmed hotspots.

---

## Part F.4 — The Resharding Problem

### Scenario

You built your system on 4 shards, each handling 25% of the data. Two years later, your user base grew 20x. Each shard now holds more data than it can comfortably index in RAM, write latency is climbing, and you need to double your shard count from 4 to 8.

This is one of the most dangerous operations in all of systems engineering: splitting live shards while the system is running, handling user traffic, and producing no data loss or inconsistency.

### The Naive Approach and Why It Fails

The simplest approach: take Shard 1 offline, copy half its data to a new Shard 5, bring both back up. Problems:

1. **Downtime**: You took a shard offline. For however long the copy took, all users on that shard received errors.
2. **Data written during the copy**: Any writes that arrived while you were copying are missing from the new shard.
3. **Multiply by 4**: You have to do this for all 4 shards.

For a system serving users, this is completely unacceptable.

### The Vitess Online Schema Change Approach

**Vitess** is a database clustering system originally built by YouTube for MySQL and now open-source. It pioneered the technique of online shard splits — splitting a shard into two without downtime. The pattern generalizes to any sharded system.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    VITESS ONLINE SHARD SPLIT                            │
│                                                                         │
│  STEP 1: Create new shard, begin copying data                          │
│  ──────────────────────────────────────────────────────────────────    │
│   Old Shard 1 ────────────────────────────────► Old Shard 1            │
│   (users 1-250M)  [all reads/writes go here]   (still active)          │
│                                │                                        │
│                                │ copy (bulk, background)                │
│                                ▼                                        │
│                         New Shard 5 (building up)                      │
│                                                                         │
│  STEP 2: Enable double-write                                           │
│  ─────────────────────────────                                         │
│   Writes ──► Old Shard 1 (primary)                                     │
│          └──► New Shard 5 (replica of new data)                        │
│   (New shard is catching up via bulk copy + new writes)                │
│                                                                         │
│  STEP 3: New shard catches up to within seconds of old shard           │
│                                                                         │
│  STEP 4: Shadow read mode                                              │
│  ────────────────────────                                              │
│   Reads ──► Old Shard 1 (authoritative result shown to user)           │
│         └──► New Shard 5 (result logged and compared, not shown)       │
│   Differences are logged and investigated. Build confidence.           │
│                                                                         │
│  STEP 5: Traffic flip                                                  │
│  ─────────────────────                                                 │
│   Reads/writes for "users 1-125M" ──► New Shard 5 (now primary)       │
│   Reads/writes for "users 126M-250M" ──► Old Shard 1 (rekeyed)        │
│   Monitor for errors. Old shard kept in sync for quick rollback.       │
│                                                                         │
│  STEP 6: Stop double-write to old shard, decommission                 │
└─────────────────────────────────────────────────────────────────────────┘
```

The key insight: you never move data offline. You first copy everything to the new shard while the old shard continues to serve traffic. Then you start writing to both simultaneously, so no writes are lost. Then you quietly verify the new shard is correct. Only then do you flip traffic.

The riskiest moment is Step 5 — the traffic flip. This should be done with a feature flag that can be instantly reverted. Monitor error rates in real time. If errors spike, flip back.

---

## Part F.5 — Cross-Shard Operations: The Hard Part

### Cross-Shard Joins

On a single database, a JOIN between `users` and `orders` is a local operation — the database engine can compare rows directly in memory. On a sharded system, `users` might be on Shard 1 and `orders` might be on Shard 3. A JOIN requires:

1. Query Shard 1 for the user data
2. Query Shard 3 for the order data
3. Pull both result sets into the application layer
4. Perform the join in application code

This is the **scatter-gather** pattern. Its cost is:
- **Latency**: At least two network round trips (often more if multiple shards hold relevant data)
- **Load**: The application server now does work that the database engine once did
- **Complexity**: The application code must implement join logic

For a two-table join that was 5 lines of SQL, you may now write 50 lines of application code.

**The avoidance strategy — denormalization**: If you know at design time that you always query users with their most recent order, you can store the most recent order's data directly in the users table. This duplicates data but eliminates the cross-shard join entirely. This is a deliberate trade-off: you accept storage cost and update complexity to preserve query efficiency.

### Cross-Shard Transactions

Suppose a money transfer moves $100 from User A (Shard 1) to User B (Shard 3). You must either both debit A and credit B, or do neither. How?

**Two-Phase Commit (2PC)**: A coordinator node manages the transaction.

```
Phase 1 (Prepare):
  Coordinator → Shard 1: "Can you commit: debit $100 from A?"
  Coordinator → Shard 3: "Can you commit: credit $100 to B?"
  Shard 1 → Coordinator: "YES, I'm ready" (locks the row)
  Shard 3 → Coordinator: "YES, I'm ready" (locks the row)

Phase 2 (Commit):
  Both said yes → Coordinator → Shard 1: "COMMIT"
                              → Shard 3: "COMMIT"

  If either said NO → Coordinator → both: "ROLLBACK"
```

The problem: if the coordinator crashes after both shards say "YES" but before sending COMMIT, both shards sit with locked rows indefinitely. This is the 2PC **blocking problem** — it can leave the system in an uncertain state waiting for a coordinator that never comes back. This is why most sharded systems avoid 2PC for cross-shard transactions.

**Saga pattern**: Break the transaction into a sequence of single-shard operations, each with a **compensation** — an undo action to reverse the effect if something later fails.

```
Saga for $100 transfer:
  Step 1: Debit $100 from User A (Shard 1)
          Compensation: Credit $100 back to User A

  Step 2: Credit $100 to User B (Shard 3)
          Compensation: Debit $100 from User B

  If Step 2 fails: run Step 1's compensation (give A back the $100)
```

Sagas avoid distributed locking. Each step commits immediately. Compensations are also committed immediately. The trade-off: there is a window where Step 1 has committed but Step 2 has not — the system is briefly inconsistent. Other processes that read during this window see an incomplete state. Sagas require careful design to ensure compensations are idempotent and that partial states do not cause problems.

**The practical answer**: Most teams design their shard key such that related data lives on the same shard. A social network where each user's data — profile, posts, follow graph — is sharded by user ID means "show all posts by user X" touches only one shard. The expensive scatter-gather is reserved for "show posts from all people user X follows" — a feed query that inherently spans many users. These are handled by pre-computing feeds (fan-out on write) rather than scatter-gathering at read time.

**Fan-out on write** means: when user A makes a post, immediately write that post into the cached feed of every follower. If A has 1,000 followers, you write 1,000 feed entries. When any follower loads their feed, it is a single-shard read of their pre-computed feed list. The scatter-gather happened at write time, distributed across 1,000 small operations, rather than at read time in one large operation.

Fan-out on write breaks down for celebrities (users with millions of followers): writing one post to 10 million feeds takes too long and produces too much write amplification. Twitter's actual architecture handles this with a hybrid: regular users get fan-out on write; celebrities (above a follower threshold) are handled differently — their posts are looked up at read time and merged into the reader's pre-computed feed. This is why your Twitter feed can have a slight delay for celebrity tweets. The system is deliberately choosing eventual consistency and complexity over the simpler but unscalable pure fan-out approach.

This pattern — where the "right" architecture depends on the data distribution (most users vs. celebrity users) — is a classic example of the kind of nuance that Staff Engineer interviews test. The interviewer is not looking for you to state the rule; they are looking for you to identify when the rule breaks and what you would do about it.

---

## Part F.6 — Database Evolution Timeline: Instagram Case Study

Instagram is one of the best-documented examples of a system that evolved from a simple PostgreSQL setup to a globally distributed polyglot architecture as it grew from 0 to over a billion users. Each phase was triggered by a specific bottleneck — not by premature optimization.

### Phase 1: Single PostgreSQL Server (0 → ~500K users, 2010)

Instagram launched on a single PostgreSQL server running on Amazon EC2. The application was Django (Python web framework). The entire database — users, photos, follows, likes, comments — lived on one machine. This was entirely correct for the scale. A single well-tuned PostgreSQL instance handles millions of rows across all tables without difficulty.

**Key decisions**: Careful indexing from day one. No premature optimization. Django's ORM made database access easy. Complexity was kept minimal.

### Phase 2: Read Replicas Added (~500K → 5M users, 2011)

Photo queries — "show all photos by user X" — grew to dominate read traffic. Rather than sharding, Instagram added PostgreSQL read replicas. Photo feed queries were routed to replicas. Writes and user-facing reads that required freshness went to the primary.

**The bottleneck**: Read throughput on the primary, not write throughput or storage.
**The fix**: Read replicas. Weeks of work, not months.

### Phase 3: Introducing Cassandra for Photos (~5M → 50M users, 2011–2012)

The photos table — specifically the "which photos does a user follow in their feed?" access pattern — did not fit the relational model well. The query was: "give me the N most recent photos from the 500 people this user follows, sorted by time." This required scatter-gather across many users' photo streams and was inefficient in PostgreSQL.

Instagram moved photo timelines to **Apache Cassandra**, a wide-column store optimized for exactly this access pattern: "get N most recent items in list X." User data and core relational data stayed in PostgreSQL.

**The bottleneck**: Specific access pattern unsuited to relational model.
**The fix**: Introduce a specialized store for that access pattern. Not a wholesale replacement — a targeted addition.

### Phase 4: Sharded PostgreSQL for User Data (~50M → 300M users, 2013–2015)

User data in PostgreSQL eventually outgrew even a vertically scaled primary with read replicas. Instagram implemented a sharded PostgreSQL architecture. The shard key was user ID. All data for a given user — their profile, settings, relationships — lived on the same shard, ensuring that common per-user queries never required cross-shard joins.

**The bottleneck**: Write throughput and storage on the primary PostgreSQL server.
**The fix**: Shard by user ID. Took months of engineering.

### Phase 5: Multi-Region Deployment (300M → 1B+ users, 2015–present)

Users in Europe were experiencing high latency because all database writes went to servers in the United States. Instagram built multi-region infrastructure, replicating data across AWS regions globally. This introduced the next tier of complexity: **geographic data locality**, **cross-region replication lag**, and **consistency trade-offs** for global writes.

### The Lesson

Each phase of Instagram's evolution was triggered by a measurable bottleneck hitting a threshold. No phase was executed speculatively. When they were at Phase 1, they did not implement Phase 4 "just in case." This is the difference between engineering and over-engineering.

```
┌────────────────────────────────────────────────────────────────────────┐
│              INSTAGRAM EVOLUTION TIMELINE                              │
│                                                                        │
│   USERS    0      500K      5M      50M     300M    1B+               │
│            │        │        │        │       │       │               │
│   PHASE:   ├── 1 ──►├─── 2 ─►├─── 3 ─►├── 4 ─►├── 5 ─►             │
│                                                                        │
│   DB:    Single  +Read    +Cassandra  Sharded  Multi-                 │
│          PG      Replicas  for feeds  PG       Region                 │
│                                                                        │
│   Trigger: N/A   Read     Feed       Write    Latency                 │
│                  overload query      overload for non-US              │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Part F.7 — Polyglot Persistence Patterns

### What Polyglot Persistence Means

**Polyglot persistence** is the practice of using multiple different database technologies within a single system, each chosen for what it does best.

The insight is that different types of queries have radically different optimal data structures:
- **Transactional writes with strong consistency** → PostgreSQL (relational, ACID)
- **Full-text search** → Elasticsearch (inverted index)
- **Sub-millisecond read cache** → Redis (in-memory hash table / sorted set)
- **Event streaming and durability** → Kafka (sequential log)
- **Analytical queries over historical data** → Snowflake or BigQuery (columnar OLAP)

No single database is optimal for all of these. Polyglot persistence accepts this and uses the right tool for each job.

### A Concrete Architecture

A typical e-commerce or social platform architecture:

```
┌─────────────────────────────────────────────────────────────────────┐
│              POLYGLOT PERSISTENCE ARCHITECTURE                      │
│                                                                     │
│   User Action                                                       │
│      │                                                              │
│      ▼                                                              │
│   ┌──────────┐    Writes    ┌─────────────────┐                    │
│   │   App    │─────────────►│   PostgreSQL     │  Source of truth  │
│   │ Server   │              │  (transactional) │  ACID guarantees  │
│   └──────────┘              └────────┬────────┘                    │
│         │                            │                             │
│         │ Cache reads                │ WAL (change stream)         │
│         ▼                            ▼                             │
│   ┌──────────┐              ┌─────────────────┐                    │
│   │  Redis   │              │     Kafka        │  Event bus        │
│   │  Cache   │              │  (event stream)  │                   │
│   └──────────┘              └────────┬────────┘                    │
│                                      │                             │
│                     ┌────────────────┼────────────────┐           │
│                     ▼                ▼                ▼           │
│              ┌────────────┐  ┌─────────────┐  ┌──────────────┐   │
│              │Elasticsearch│  │  Snowflake  │  │ Other svc    │   │
│              │  (search)   │  │ (analytics) │  │ (real-time   │   │
│              └────────────┘  └─────────────┘  │  processing) │   │
│                                               └──────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Synchronization Between Stores: The #1 Problem

Using multiple stores solves the query problem. It creates a synchronization problem: **how do you keep all the stores consistent when data changes?**

**Option 1: Dual write (risky)**

The application writes to two stores on every write:

```python
def create_product(product):
    db.execute("INSERT INTO products ...", product)  # Step 1
    elasticsearch.index("products", product)         # Step 2
```

Problem: What if Step 1 succeeds but Step 2 fails? The product exists in PostgreSQL but not in Elasticsearch. The stores are now inconsistent. Users can create the product but cannot find it via search. The only fix is a reconciliation job that periodically compares the stores and corrects discrepancies — complex and error-prone.

Dual write also violates the transactional guarantee: you cannot atomically commit to two different systems without distributed coordination.

**Option 2: Change Data Capture (CDC) — the right approach**

**Change Data Capture** means listening to the database's own internal change log and replicating changes downstream. In PostgreSQL, every change is recorded in the **Write-Ahead Log (WAL)** before it is applied to the data files. The WAL is the source of truth. Tools like **Debezium** read the WAL and publish every row-level change as an event to Kafka.

```
┌──────────────────────────────────────────────────────────────────────┐
│                  CDC PIPELINE: PostgreSQL → Kafka → Stores           │
│                                                                      │
│  PostgreSQL                                                          │
│  ┌─────────┐                                                         │
│  │  Write  │─── committed ──► WAL (Write-Ahead Log)                 │
│  │  (ACID) │                   │                                     │
│  └─────────┘                   │                                     │
│                                │ Debezium reads WAL                  │
│                                ▼                                     │
│                         ┌─────────────┐                             │
│                         │    Kafka     │  "products" topic           │
│                         │  (durable    │  msg: {op:INSERT, data:...} │
│                         │   event log) │                             │
│                         └──────┬──────┘                             │
│                                │                                     │
│              ┌─────────────────┼─────────────────┐                 │
│              ▼                 ▼                 ▼                 │
│   ┌──────────────────┐ ┌─────────────┐ ┌────────────────────┐     │
│   │  Elasticsearch   │ │  Snowflake  │ │  Redis Cache        │     │
│   │  Consumer:       │ │  Consumer:  │ │  Consumer:          │     │
│   │  INSERT → index  │ │  INSERT →   │ │  DELETE cache key   │     │
│   │  UPDATE → reindex│ │  append row │ │  (force fresh read) │     │
│   │  DELETE → remove │ │             │ │                     │     │
│   └──────────────────┘ └─────────────┘ └────────────────────┘     │
│                                                                      │
│  Key property: PostgreSQL commit is the ONLY write.                 │
│  Downstream propagation is async — no dual-write race condition.    │
└──────────────────────────────────────────────────────────────────────┘
```

The critical property: **PostgreSQL is the single source of truth**. The application writes to PostgreSQL only. Debezium asynchronously propagates those changes to Kafka. Consumers (Elasticsearch, Snowflake, Redis) consume from Kafka. If Elasticsearch is down, Kafka retains the events and Elasticsearch catches up when it recovers — no data is lost.

The trade-off: **eventual consistency**. After a product is created in PostgreSQL, it may take milliseconds to seconds before it appears in Elasticsearch search results. For most applications, this is fine. The user who just created a product is not usually immediately searching for it.

**Option 3: Event sourcing**

In **event sourcing**, you never store the current state of an object. Instead, you store only the sequence of events that produced that state. The current state is derived by replaying events.

Example: Instead of `users` table with current profile data, you have an `events` table: `{user_id: 123, event: "email_changed", from: "old@ex.com", to: "new@ex.com", at: "2024-01-01T12:00:00Z"}`. The current email address is `new@ex.com` because that was the most recent `email_changed` event.

This approach naturally produces a Kafka-ready event stream (every state change is an event by definition) and makes it trivial to project state into any read model or secondary store. The complexity cost: reading current state requires replaying history (usually mitigated by snapshotting), and the programming model is unfamiliar to many engineers. Event sourcing is powerful for systems where audit trails and replayability are valuable, and complex for everything else.

---

## Part F Summary: The Mental Model

Database scaling is not a single decision — it is a progression of decisions made in response to real bottlenecks. The right time to take each step is when you have hit the capacity of the previous step and measured the bottleneck clearly.

The order matters:

1. **Vertical scaling** first — often solves the problem for years.
2. **Query optimization** second — frequently produces 10–100x improvement at zero infrastructure cost.
3. **Caching** third — dramatically reduces database read load.
4. **Read replicas** fourth — scale read throughput beyond a single machine.
5. **Sharding** last — only when write throughput or storage exhausts the above options.

When you do shard, choose your strategy based on your access patterns:

| Strategy | Good For | Bad For |
|----------|----------|---------|
| Range | Range queries on the key, time-series | Write hotspots, uneven key distribution |
| Hash | Uniform write distribution | Range queries, resharding cost |
| Directory | Multi-tenant SaaS, irregular tenant sizes | Lookup service availability, added latency |

Consistent hashing solves the resharding problem for hash-based systems but does not solve hotspot keys. Vitess-style online splits solve the operational problem of live resharding without downtime.

Cross-shard operations — joins and transactions — are the fundamental tax of sharding. Design your shard key to minimize the need for them. When you cannot avoid them, use scatter-gather for reads and Saga patterns for writes.

For polyglot persistence, CDC from PostgreSQL's WAL to Kafka is the standard architecture for keeping secondary stores in sync without dual-write risks.

The Instagram case study illustrates the core lesson: each phase of evolution was forced by a specific measured bottleneck. No phase was speculation. Build systems that can evolve gracefully, and you will never need to pay the cost of a phase before its time.

### Interview Signals: What L6 Candidates Say

In a Staff Engineer interview, the examiner is listening for signals that you understand trade-offs, not just definitions. Here are examples of weak vs. strong answers on scaling topics:

| Topic | Weak (L4/L5) Answer | Strong (L6) Answer |
|-------|--------------------|--------------------|
| "How do you scale the database?" | "Add read replicas and then shard it." | "First measure: is it reads, writes, or storage? Reads → replica + cache. Writes → vertical scale first, then shard if still insufficient. I'd avoid sharding unless I've exhausted cheaper options." |
| "Which sharding strategy?" | "Hash-based for even distribution." | "Depends on access patterns. If range queries dominate, hash sharding forces scatter-gather on every range query — I'd use range-based with careful monitoring for hotspots, or consistent hashing if resharding is a near-term concern." |
| "How do you keep Elasticsearch in sync?" | "Dual write on every update." | "CDC from the WAL via Debezium into Kafka. Elasticsearch consumers read from Kafka. Avoids dual-write race conditions and handles Elasticsearch downtime gracefully — events buffer in Kafka and replay on recovery." |
| "Cache invalidation strategy?" | "Use a 5-minute TTL." | "Write-through for data where staleness is expensive. Cache-aside with aggressive key deletion on write for most data. Monitor hit rates — if hit rate drops below 90%, TTL is too short or cardinality is too high for effective caching." |

These answers do not require memorized facts. They require understanding the trade-offs well enough to reason about novel situations. That is what this chapter is building toward.

---

*Continues in Part G: Distributed SQL, NewSQL, and Global Databases*
# Chapter 28 — Part G: Real-World Incidents, Failure Modes, Migration Strategies, and Operational Realities

---

## Why This Part Exists

Every chapter up to this point has told you how databases work when everything goes right. This part tells you what happens when things go wrong — because at L6, interviewers are not testing whether you know what a B-tree is. They are testing whether you have the scar tissue to avoid blowing up production.

The incidents in this chapter are real. The failure modes are common. The migrations are ones engineers at companies like GitHub, Amazon, and Facebook have actually performed. By the time you finish this chapter, you should be able to walk into an interview and say "here is exactly how I would handle the cache stampede problem" or "here is the four-phase process I would use to migrate this table without downtime," and then back it up with the kind of depth that only comes from understanding the root causes, not just the solutions.

Let's start with one of the most common and most preventable database failures in production.

---

## Section 1: The Thundering Herd — When Your Cache Becomes the Problem

### What Is the Thundering Herd Problem?

Imagine a library that closes for five minutes every hour to re-shelve books. During that five minutes, nobody can check anything out. Now imagine a thousand people show up at the exact same moment the library closes — all of them lined up, all of them waiting, all of them pounding on the door. When the library opens, all thousand rush in at once, overwhelm the librarians, and the system collapses.

That is the **thundering herd problem**, and it is exactly what happens with caches.

Here is the specific scenario: you have a Redis cache that stores database query results. You set a TTL (time-to-live) of 5 minutes on every cache entry. Your application is handling 10,000 requests per second. For 5 minutes, Redis serves all those requests beautifully — the database is barely touched. Then minute 5 arrives. Every cache entry expires at the same time. Every one of those 10,000 requests per second suddenly misses the cache. Every single one of them goes directly to the database.

Your database, which was comfortably handling a few hundred queries per second, suddenly receives 10,000 queries in the same second. It cannot handle this. Connection pool exhausts. Query queue backs up. Latency spikes to seconds. The database crashes or enters a degraded state. Your entire application is now down.

```
THE THUNDERING HERD — WHAT GOES WRONG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Time 0:00 — Cache populated, all 10,000 requests/sec served by Redis
           ┌─────────────────────────────┐
           │           REDIS             │
           │   key: user_feed  [TTL=300] │
           │   key: trending   [TTL=300] │◄── 10,000 req/sec (all HIT)
           │   key: home_page  [TTL=300] │
           └─────────────────────────────┘
                         │
                   tiny trickle
                         │
                         ▼
           ┌─────────────────────────────┐
           │        POSTGRESQL           │
           │   ~50 queries/sec (easy)    │
           └─────────────────────────────┘

Time 5:00 — All TTLs expire simultaneously
           ┌─────────────────────────────┐
           │           REDIS             │
           │   key: user_feed  [EXPIRED] │
           │   key: trending   [EXPIRED] │◄── 10,000 req/sec (all MISS)
           │   key: home_page  [EXPIRED] │
           └─────────────────────────────┘
                         │
              FULL FLOOD — 10,000 req/sec
                         │
                         ▼
           ┌─────────────────────────────┐
           │        POSTGRESQL           │
           │   10,000 queries/sec        │
           │   CONNECTION POOL MAXED     │◄── DATABASE CRASHES
           │   QUEUE OVERFLOWS           │
           └─────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Why Do All Caches Expire at the Same Time?

Because you set the same TTL for all of them. If your caching code looks like this:

```python
redis.set("user_feed:user123", data, ex=300)  # 300 seconds = 5 minutes
redis.set("user_feed:user456", data, ex=300)
redis.set("user_feed:user789", data, ex=300)
```

And you receive a traffic spike at minute 0 that causes 50,000 cache entries to be populated, all of them get TTL=300. At minute 5, all 50,000 expire in the same second.

This is especially dangerous after a deployment that restarts all application servers and warms up the cache from scratch — every entry is born at the same moment, so they all die at the same moment.

### Solution 1: TTL Jitter

**TTL jitter** means adding a random amount of time to the TTL so that different cache entries expire at different times, spreading the database load over a window instead of concentrating it into a spike.

```python
import random

BASE_TTL = 300  # 5 minutes
JITTER = 30     # up to 30 seconds extra

def cache_set(key, value):
    ttl = BASE_TTL + random.randint(0, JITTER)
    redis.set(key, value, ex=ttl)
```

With this change, cache entries now expire somewhere between 300 and 330 seconds. If you have 50,000 entries all created at the same moment, they now expire spread across a 30-second window. Instead of 50,000 database queries hitting in one second, you get about 1,666 per second — still a spike, but a manageable one that the database can absorb.

The jitter window should be sized based on how long it takes your database to recompute and repopulate cache entries. If a cache entry takes 50ms to recompute, and you have 10,000 entries expiring per second, you need enough jitter to spread load to under whatever your database can handle.

### Solution 2: Probabilistic Early Expiration (PER)

**Probabilistic early expiration** (also called XFetch) takes a completely different approach. Instead of letting the cache entry run to zero and then experiencing a miss, you proactively recompute the cache entry *before* it expires — but you do this with a probability that increases as the TTL approaches zero.

Think of it like a gambler: when the cache entry has 5 minutes left, the probability of recomputing early is very low. When it has 30 seconds left, the probability is high. This way, one worker voluntarily recomputes the cache entry just before it expires, and the stampede never happens.

The XFetch algorithm works like this:

```python
import math
import random
import time

def fetch_with_per(key, recompute_fn, ttl, beta=1.0):
    """
    beta: controls how aggressively to early-recompute.
    Higher beta = more aggressive (recompute earlier).
    """
    cached = redis.get(key)
    expiry = redis.ttl(key)  # seconds remaining

    if cached is not None:
        # Decide whether to recompute early
        # The closer to expiry, the more likely we recompute
        delta = time.time()  # time of last recompute (stored with value)
        gap = -beta * math.log(random.random())
        
        if gap < expiry:
            return cached  # cache is fresh enough, use it
    
    # Cache miss OR decided to recompute early
    value = recompute_fn()
    redis.set(key, value, ex=ttl)
    return value
```

The key insight: with PER, multiple workers might all decide to recompute "early" for the same key, but this is still far better than the stampede scenario. You are trading a little extra work (a few premature recomputes) for the elimination of the stampede.

### Solution 3: Request Coalescing (Promise Cache)

**Request coalescing** means that when multiple requests arrive for the same cache key that is currently being recomputed, only one request actually does the recomputation. All the others wait for that first request to finish and then share the result.

Think of it as a "promise": the first request to notice a cache miss makes a promise that it will compute the value. Every subsequent request checks whether a promise already exists. If it does, they wait for the promise to resolve rather than each independently hitting the database.

```
WITHOUT COALESCING:
   Request 1 → cache MISS → database query 1 ─────┐
   Request 2 → cache MISS → database query 2 ──────┤→ 10,000 DB queries
   Request 3 → cache MISS → database query 3 ─────┘

WITH COALESCING:
   Request 1 → cache MISS → database query ─────────┐
   Request 2 → cache MISS → "query in progress, wait"│→ 1 DB query
   Request 3 → cache MISS → "query in progress, wait"│  others wait
                               ▼ result arrives ───────┘
                  All waiting requests served from single result
```

In practice, this is implemented using a distributed lock in Redis:

```python
def get_with_coalescing(key, recompute_fn, ttl):
    value = redis.get(key)
    if value is not None:
        return value
    
    # Try to acquire lock to be the one who recomputes
    lock_key = f"lock:{key}"
    lock_acquired = redis.set(lock_key, "1", nx=True, ex=10)  # 10s lock
    
    if lock_acquired:
        # I won the lock — I do the recompute
        value = recompute_fn()
        redis.set(key, value, ex=ttl)
        redis.delete(lock_key)
        return value
    else:
        # Someone else is recomputing — wait and poll
        for _ in range(20):  # wait up to 2 seconds
            time.sleep(0.1)
            value = redis.get(key)
            if value is not None:
                return value
        # If still missing after waiting, fall back to direct DB query
        return recompute_fn()
```

### Solution 4: Background Refresh

**Background refresh** is the most conservative solution. A background job continuously monitors cache entries and refreshes them *before* they expire. Users never see a cache miss because the cache is always warm.

```
BACKGROUND REFRESH ARCHITECTURE:
                                                           
   ┌─────────────────────────────────────────────────────┐
   │                 BACKGROUND REFRESH JOB              │
   │                                                     │
   │  Every 30 seconds:                                  │
   │  1. Scan all keys where TTL < 60 seconds            │
   │  2. Recompute those values from database            │
   │  3. Reset TTL to 300 seconds                        │
   └────────────────────┬────────────────────────────────┘
                        │ refreshes before expiry
                        ▼
   ┌─────────────────────────────────────────────────────┐
   │                      REDIS                          │
   │   key: user_feed  [TTL=295] ← freshly refreshed    │
   │   key: trending   [TTL=280] ← freshly refreshed    │
   └────────────────────┬────────────────────────────────┘
                        │ always a cache HIT
                        ▼
   ┌─────────────────────────────────────────────────────┐
   │                  USER REQUESTS                      │
   │   10,000 req/sec — all served from Redis            │
   └─────────────────────────────────────────────────────┘
```

The tradeoff: background refresh adds complexity (a new background service), uses more database resources (constant background queries), and means you always serve data that is at most 30 seconds stale. For some use cases (stock prices, sports scores) that is acceptable. For others (bank balances) it is not.

### When to Use Which Solution

| Scenario | Best Solution |
|---|---|
| Simple caching, small TTL variance acceptable | TTL jitter |
| High-value keys where stampede risk is extreme | PER or coalescing |
| Real-time leaderboards, frequently accessed aggregates | Background refresh |
| High-concurrency microservice with shared cache | Request coalescing |

---

## Section 2: Real Incident — GitHub's MySQL Failover Gone Wrong (2012)

### The Setup

In 2012, GitHub ran their primary data on MySQL with a leader-follower replication setup. The **leader** (also called the primary) handled all writes. The **follower** (also called the replica) received a stream of write operations from the leader and applied them, staying a copy of the leader's data. This is standard practice — the replica exists so that if the leader fails, you can promote the replica to become the new leader and continue serving traffic.

This is a fundamentally sound architecture. The failure was not in the architecture. The failure was in the details of how the failover was executed.

### What Went Wrong

GitHub's primary MySQL server began exhibiting performance degradation. Engineers made a decision to initiate a **planned failover** — they would switch traffic over to the replica, which they assumed was a complete, up-to-date copy of the primary.

The fatal assumption: they had not checked **replication lag**.

**Replication lag** is the delay between when a write is committed on the primary and when that write is applied on the replica. In a healthy system, this lag is measured in milliseconds. Under heavy write load or network issues, it can grow to seconds, minutes, or even hours.

At the moment of the failover, GitHub's replica was **45 seconds behind the primary**. This means 45 seconds of user writes — signups, repository pushes, issue comments, pull request reviews — existed only on the primary server and had not yet been replicated to the replica.

The failover completed. The replica became the new primary. Traffic was routed to it.

But those 45 seconds of writes were gone.

```
GITHUB FAILOVER INCIDENT — WHAT HAPPENED

Time 0:          PRIMARY (healthy)              REPLICA
                 ┌──────────────┐              ┌──────────────┐
                 │ All writes   │─replication─►│ 45 seconds   │
                 │ landing here │              │ behind       │
                 └──────────────┘              └──────────────┘

Time 0+5min:     PRIMARY (degraded)
                 ┌──────────────┐              ┌──────────────┐
                 │ Performance  │─replication─►│ Still 45s    │
                 │ degrading    │              │ behind       │
                 └──────────────┘              └──────────────┘

Time 0+10min:    FAILOVER INITIATED
                 ┌──────────────┐              ┌──────────────┐
                 │ PRIMARY      │  TRAFFIC     │  REPLICA     │
                 │ taken offline│─────────────►│  becomes NEW │
                 │              │  switched    │  PRIMARY     │
                 └──────────────┘              └──────────────┘
                       │
                 45 SECONDS OF                Those 45 seconds of
                 WRITES LOST                  writes never arrived
                 (only on old primary,
                  now unreachable)

RESULT: Users' data silently disappeared.
        No error shown — data simply no longer existed.
```

### The Root Cause Chain

Breaking down the chain of failures that led to this incident:

**1. Replication lag was not monitored adequately.** GitHub's monitoring alerted on many things, but replication lag was not being tracked in a way that would block a failover decision. Engineers could not see at a glance that the replica was 45 seconds behind.

**2. The failover procedure did not include a lag check.** The runbook for failover did not have a step that said "check replication lag, abort if lag > X seconds." The engineer performing the failover had no automated gate preventing them from proceeding with a lagged replica.

**3. Semi-synchronous replication was not enabled.** With **semi-synchronous replication**, the primary does not consider a write committed until at least one replica has acknowledged receiving it. This adds a small amount of write latency (the time for the replica to acknowledge) but guarantees that the replica is never more than one write behind. If GitHub had used semi-synchronous replication, the maximum data loss window would have been a single in-flight transaction, not 45 seconds.

**4. Binlogs on the failed primary were inaccessible.** MySQL's **binary log** (binlog) is a log of every write operation. If they could have accessed the binlog on the old primary, they could have replayed the missing 45 seconds of writes onto the new primary. But the old primary was degraded and not fully accessible.

### Incident Summary Table

| Field | Details |
|---|---|
| **Trigger** | Primary MySQL server performance degradation; engineers initiate planned failover |
| **Impact** | 45 seconds of user writes lost silently; users see data disappear |
| **Discovery** | User reports and application inconsistencies after failover |
| **Duration** | Data loss was permanent; manual recovery took days |
| **Resolution** | Partial recovery from application logs and user reports; some data unrecoverable |
| **Prevention** | Added replication lag monitoring; updated failover runbook with lag gates |

### Lessons and Preventive Designs

**Lesson 1: Monitor replication lag continuously.**

Every replica should emit a metric: `replication_lag_seconds`. Alert at >5 seconds (warning), page at >30 seconds (critical). This metric should be on your primary database dashboard, visible to any on-call engineer at all times.

```sql
-- Check replication lag in MySQL
SHOW SLAVE STATUS\G
-- Look at: Seconds_Behind_Master

-- In PostgreSQL (on replica):
SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))
       AS replication_lag_seconds;
```

**Lesson 2: Automated failover tools must refuse to proceed if lag is too high.**

Tools like Orchestrator (for MySQL) and Patroni (for PostgreSQL) can be configured with a `max_lag_on_failover` threshold. If the best available replica is lagged beyond this threshold, the automated failover aborts and pages a human instead of silently promoting a stale replica.

```yaml
# Patroni configuration example
postgresql:
  parameters:
    max_standby_streaming_delay: 30s  # replica stops if it falls >30s behind
    
# Orchestrator configuration
"ReasonableReplicationLagSeconds": 10,
"FailMasterPromotionOnLagMinutes": 0.5  # refuse failover if lag > 30s
```

**Lesson 3: Enable semi-synchronous replication for any data you cannot afford to lose.**

Semi-sync replication adds latency (typically 1-5ms) to every write, because the primary waits for a replica acknowledgement. For most applications this is an acceptable trade for the guarantee that data loss on failover is bounded to zero or near-zero.

```sql
-- MySQL: enable semi-synchronous replication
INSTALL PLUGIN rpl_semi_sync_master SONAME 'semisync_master.so';
SET GLOBAL rpl_semi_sync_master_enabled = 1;
SET GLOBAL rpl_semi_sync_master_timeout = 1000;  -- 1 second timeout before falling back to async
```

**Lesson 4: Store binlogs on separate, durable storage.**

Even if the primary crashes or becomes inaccessible, binlogs should survive. Configure MySQL to ship binlogs to S3 or GCS in near-real-time. If a failover happens and the replica is lagged, you can use the binlog archive to replay the missing writes.

```bash
# mysqlbinlog shipped to S3 via cron every minute
mysqlbinlog --read-from-remote-server \
  --host=primary.internal \
  --raw \
  mysql-bin.000123 | aws s3 cp - s3://db-binlogs/mysql-bin.000123
```

---

## Section 3: Real Incident — Amazon DynamoDB Availability Event (2015)

### The Architecture Before the Incident

DynamoDB is a distributed key-value and document database. One of its internal components is a **metadata service** — a system that tracks where each piece of data lives across the many thousands of storage nodes in DynamoDB. When your application calls `GetItem`, the DynamoDB router first asks the metadata service "which storage node holds this partition key?" and then sends the request to that node.

This metadata service is consulted on **every single DynamoDB request**. Every read, every write, every conditional check — all of them hit the metadata service first.

### What Happened

In September 2015, the DynamoDB metadata service in the US-East-1 region began experiencing elevated latency. Requests to the metadata service started taking longer than normal.

Here is where the cascade began: DynamoDB clients — the code running in millions of AWS Lambda functions, EC2 instances, and other services — are configured to retry failed or slow requests. This is standard good practice in distributed systems. If a request times out, you retry it.

But when the metadata service slowed down, the retries made things worse. Here is why:

```
THE RETRY STORM CASCADE

Step 1: Metadata service gets slightly slower (latency: 50ms instead of 5ms)

Step 2: DynamoDB clients start timing out, they retry
        Each retry = another request to the already-slow metadata service

Step 3: Metadata service now receives 3x the normal request volume
        (original requests + first retries + second retries)
        Latency increases further: 200ms

Step 4: More timeouts, more retries
        5x normal request volume hitting metadata service
        Latency: 1000ms

Step 5: Metadata service completely overwhelmed
        All DynamoDB requests fail (cannot route without metadata)
        
Step 6: ALL of US-East-1 DynamoDB is degraded
        EC2, Lambda, and other services depending on DynamoDB also degrade
```

This is called a **retry storm**. It is a positive feedback loop: more failures lead to more retries, which create more load, which create more failures.

### Impact

For several hours, DynamoDB in US-East-1 was degraded or unavailable. Because so many AWS services (EC2, ELB, RDS multi-AZ) internally use DynamoDB for metadata and coordination, the blast radius extended well beyond just DynamoDB customers. This made the 2015 event one of the largest AWS outages of that period.

### Lessons and Preventive Designs

**Lesson 1: Exponential backoff with jitter is not optional.**

**Exponential backoff** means that after each failed request, you wait longer before retrying: 100ms, 200ms, 400ms, 800ms, 1600ms... The wait time doubles each time. This limits the rate at which a single client hammers a struggling service.

But exponential backoff alone is not enough. If 10,000 clients all start retrying at the same moment, they will all hit their first backoff at the same time, their second backoff at the same time, and so on — synchronized retries that still create spikes.

**Jitter** (randomness) is the fix. Add a random component to the backoff so that clients desynchronize:

```python
import random
import time

def retry_with_exponential_backoff(operation, max_retries=5):
    for attempt in range(max_retries):
        try:
            return operation()
        except TransientError as e:
            if attempt == max_retries - 1:
                raise
            base_delay = (2 ** attempt) * 0.1  # 0.1, 0.2, 0.4, 0.8, 1.6 seconds
            jitter = random.uniform(0, base_delay)
            sleep_time = base_delay + jitter
            time.sleep(sleep_time)
```

AWS's own SDKs use this pattern, and the 2015 incident was a major factor in AWS formalizing this guidance for all SDK clients.

**Lesson 2: Metadata and coordination services are blast-radius multipliers — protect them specially.**

Any service that is consulted on every request is a single point of catastrophic failure. The architecture should:

- **Rate-limit incoming requests** to the metadata service so that even a retry storm cannot exceed the service's capacity
- **Prioritize requests** — background tasks and retries are lower priority than user-facing reads
- **Isolate the metadata service** from general DynamoDB traffic using separate network paths and resource pools

**Lesson 3: Client-side circuit breakers.**

A **circuit breaker** is a pattern borrowed from electrical engineering. When a circuit breaker trips (opens), it stops all current flow, protecting downstream components from further damage.

In software, a circuit breaker monitors failure rates. If failures exceed a threshold (say, 50% of requests failing in the last 10 seconds), the circuit breaker "opens" and immediately rejects new requests without even trying to contact the struggling service. This gives the downstream service time to recover.

```
CIRCUIT BREAKER STATES:

   CLOSED                    OPEN                    HALF-OPEN
   (normal)                  (protecting)            (testing recovery)
   
   All requests ──────►      All requests ──────►    One test request ──────►
   pass through              rejected immediately    allowed through
        │                                                    │
   if failure rate                                    if succeeds:
   exceeds threshold                                  return to CLOSED
        │                                            if fails:
        ▼                                            stay OPEN
   OPEN circuit
```

**Lesson 4: Cache metadata client-side.**

If every DynamoDB request requires consulting the metadata service, then the metadata service must be available for *every* DynamoDB request to succeed. The fix is to **cache metadata in the client**.

When the DynamoDB client discovers that partition key `user:12345` lives on storage node `shard-47`, it caches this mapping locally (in the application's memory) for a few minutes. Subsequent requests to the same key skip the metadata service entirely and go directly to the storage node.

This reduces metadata service load dramatically (typically by 90%+), and means that even if the metadata service is temporarily slow, most requests succeed using cached routing information.

---

## Section 4: Schema Migration Disaster — The NOT NULL Column

### The Problem Setup

You are an engineer at a company that stores user data in PostgreSQL. The `users` table has grown to 500 million rows over five years. Your product team needs to add a `country` column to store the user's country. Straightforward requirement.

You write this migration:

```sql
ALTER TABLE users ADD COLUMN country VARCHAR(50) NOT NULL DEFAULT 'US';
```

You test it in your staging environment. It runs in 2 seconds on the staging table (which has 10,000 rows). You feel confident. You run it in production.

Your application goes down for 3 hours.

### What PostgreSQL Actually Does (Pre-Version 11)

In PostgreSQL versions before 11, when you run `ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT ...`, the database engine:

1. Acquires an **exclusive lock** on the entire `users` table
2. Rewrites **every single row** to include the new column with the default value
3. Holds the lock until the rewrite is complete
4. Then releases the lock

With 500 million rows, step 2 takes hours. During those hours, the exclusive lock means:

- No reads from the `users` table
- No writes to the `users` table
- All queries that touch `users` are blocked, queued, waiting

Every API endpoint that needs user data returns an error or hangs. Your entire application is effectively down.

```
DANGEROUS MIGRATION — TIMELINE

T+0:00  ALTER TABLE users ADD COLUMN country VARCHAR(50) NOT NULL DEFAULT 'US';
        │
        ├─► PostgreSQL acquires EXCLUSIVE LOCK on users table
        │   ┌─────────────────────────────────────────────────┐
        │   │  EXCLUSIVE LOCK HELD — ALL OTHER QUERIES BLOCKED │
        │   └─────────────────────────────────────────────────┘
        │
T+0:01  └─► Rewriting row 1 of 500,000,000...
T+0:30         Rewriting row 50,000,000...
T+1:00         Rewriting row 100,000,000...
        │   ┌────────────────────────────────────┐
        │   │  QUERY QUEUE: 50,000 waiting        │
        │   │  P99 LATENCY: TIMEOUT               │
        │   │  ORDERS PLACED: 0                   │
        │   │  SIGNUPS: 0                          │
        │   └────────────────────────────────────┘
T+3:00  └─► Rewrite complete. Lock released.
            Application resumes. 3 hours of downtime.
```

### The L6 Safe Migration Approach

The correct approach breaks the migration into small steps, each of which is safe to run with zero downtime. Here is the full sequence:

**Step 1: Add the column as nullable (no default, no NOT NULL)**

```sql
-- This is instant in all PostgreSQL versions
-- Just updates table metadata, no row rewriting
ALTER TABLE users ADD COLUMN country VARCHAR(50);
```

This operation is fast because PostgreSQL does not need to touch any existing rows. The column is nullable, so existing rows simply have NULL for this column.

**Step 2: Deploy code that writes the new column**

Before you backfill old data, deploy application code that sets `country` on new writes. This ensures that all new rows being created will have a value, and you have tested the code path in production at small scale before you touch 500 million old rows.

```python
# Application code now writes country on user creation
def create_user(email, country='US'):
    db.execute(
        "INSERT INTO users (email, country) VALUES (%s, %s)",
        (email, country)
    )
```

**Step 3: Backfill old rows in small batches**

Instead of one massive UPDATE that holds locks for hours, backfill in small batches of 1,000–10,000 rows at a time, with a brief sleep between batches.

```python
# Backfill script — run as a background job over several days
import time

batch_size = 5000
sleep_between_batches = 0.1  # 100ms

cursor = 0
max_id = db.query_one("SELECT MAX(id) FROM users")

while cursor < max_id:
    db.execute("""
        UPDATE users
        SET country = 'US'
        WHERE id BETWEEN %s AND %s
          AND country IS NULL
    """, (cursor, cursor + batch_size))
    
    cursor += batch_size
    time.sleep(sleep_between_batches)
    
    # Log progress
    print(f"Backfilled up to id={cursor}")
```

Why small batches with sleep? Each UPDATE acquires row-level locks only on the rows it touches. A batch of 5,000 rows takes maybe 50ms and releases its locks immediately. The 100ms sleep gives the database breathing room. Your application continues serving traffic normally the entire time. The backfill runs over hours or days without impacting production.

**Step 4: Verify the backfill is complete**

```sql
-- Should return 0 after backfill is complete
SELECT COUNT(*) FROM users WHERE country IS NULL;
```

**Step 5: Apply NOT NULL constraint (PostgreSQL 12+ style — no table rewrite)**

In PostgreSQL 12 and later, you can add a NOT NULL constraint without rewriting the table if a valid CHECK constraint or default already covers the column:

```sql
-- PostgreSQL 12+: this does NOT rewrite the table
-- It scans to verify no NULLs exist, then stores the constraint in metadata
ALTER TABLE users ALTER COLUMN country SET NOT NULL;

-- If on an older version, do this instead:
-- First add a CHECK constraint (which PostgreSQL can validate without full lock)
ALTER TABLE users ADD CONSTRAINT country_not_null CHECK (country IS NOT NULL) NOT VALID;
-- Then validate it (validates in background, without exclusive lock)
ALTER TABLE users VALIDATE CONSTRAINT country_not_null;
```

```
SAFE MIGRATION — TIMELINE COMPARISON

DANGEROUS APPROACH:                    SAFE APPROACH:
                                       
T+0:00  ALTER TABLE (with NOT NULL) ── T+0:00  ALTER TABLE (nullable)   ← instant
           EXCLUSIVE LOCK ▼                    no lock
T+1:00     [app down, 0 traffic]        T+0:01  Deploy new code           ← no downtime
T+2:00     [app down, 0 traffic]               traffic continues normally
T+3:00  Lock released, app resumes      T+0:05  Start backfill job        ← runs in background
        3 hours of downtime!            T+0:05  [app continues normally]
                                        T+8:00  Backfill completes
                                               (500M rows over 8 hours)
                                        T+8:01  Verify no NULLs
                                        T+8:02  ALTER TABLE SET NOT NULL   ← fast scan
                                        
                                        TOTAL DOWNTIME: 0 seconds
```

---

## Section 5: Data Corruption at Scale — Detection and Recovery

### Why Data Corruption Happens

Data corruption sounds like a rare, exotic disaster. It is not. At scale, it is a regular occurrence that mature engineering teams plan for systematically.

The causes are everywhere:

- **Disk bit flips**: cosmic rays, electrical interference, and aging hardware can cause a single bit in a stored data page to flip from 0 to 1 or vice versa. This is called a **silent data error** because the disk does not know the bit flipped — it returns the corrupted data as if it were valid.
- **Software bugs**: an application bug writes malformed data. A race condition corrupts a record. A migration script has an off-by-one error and overwrites the wrong rows.
- **Hardware failures during writes**: a server loses power mid-write. The write was partially committed — some bytes landed on disk, others did not. The record is now internally inconsistent.
- **Replication bugs**: in very rare cases, a replication bug can cause a replica to apply writes in the wrong order, or apply a write multiple times, silently diverging from the primary.

### Detection Strategy 1: Checksums at Write Time

A **checksum** is a fingerprint of a block of data. When you write a page of data to disk, you compute a checksum of that data and store it alongside the data. When you read the page back, you recompute the checksum and compare. If they differ, the data was corrupted on disk.

PostgreSQL has done this by default since version 9.3 (when you initialize with `--data-checksums`). Every 8KB data page gets a 16-bit checksum. On every read, PostgreSQL verifies the checksum and raises an error if it does not match:

```
ERROR: invalid page in block 8192 of relation base/16384/2619
DETAIL: Page verification failed, calculated checksum 47291 but expected 12847
```

This error is *better* than returning silently corrupted data. At least you know something is wrong.

### Detection Strategy 2: Periodic Reconciliation Jobs

**Reconciliation** means comparing two systems to find discrepancies. At a minimum, you should run jobs that:

- Count records in primary database vs replica: `SELECT COUNT(*) FROM orders` should match on both
- Spot-check random samples: pick 1,000 random user IDs and verify the data matches between PostgreSQL and Elasticsearch (if you are syncing data there)
- Verify referential integrity: every `order` should have a matching `user_id` in the `users` table

```python
# Example reconciliation job
def reconcile_users_and_orders():
    # Every order should have a valid user
    orphaned_orders = db.query("""
        SELECT o.id 
        FROM orders o
        LEFT JOIN users u ON o.user_id = u.id
        WHERE u.id IS NULL
    """)
    
    if orphaned_orders:
        alert(f"DATA CORRUPTION: {len(orphaned_orders)} orders have no matching user")
```

### Detection Strategy 3: Application-Level Consistency Checks

Business logic often implies consistency rules. If a user has 50 orders but no user record, that is corruption. If a payment record exists but the corresponding order does not, that is corruption. Build automated jobs that check these invariants regularly.

### Detection Strategy 4: Cross-Database Consistency

If you sync data between databases — for example, writing user records to both PostgreSQL and Elasticsearch for full-text search — you need to periodically verify both copies agree.

```python
def verify_search_index_freshness():
    # Sample 500 random user IDs
    sample_ids = db.query("SELECT id FROM users ORDER BY RANDOM() LIMIT 500")
    
    mismatches = 0
    for user_id in sample_ids:
        pg_name = db.query_one("SELECT name FROM users WHERE id = %s", user_id)
        es_name = elasticsearch.get_source(index="users", id=user_id).get("name")
        
        if pg_name != es_name:
            mismatches += 1
    
    if mismatches > 0:
        alert(f"INDEX DRIFT: {mismatches}/500 sampled users differ between PG and ES")
```

### Recovery Strategy 1: Point-in-Time Recovery (PITR)

**Point-in-time recovery** means restoring the database to an exact timestamp before the corruption occurred. PostgreSQL achieves this through a combination of base backups and **Write-Ahead Log (WAL)** archiving.

The WAL is a log of every change made to the database. If you have a base backup from last night and all WAL files since then, you can restore the database to any point in time between the backup and the present:

```bash
# Restore PostgreSQL to 2026-06-12 14:30:00 UTC
# (before the corruption at 14:45:00)

# 1. Restore base backup
cp -r /backup/base_20260612 /var/lib/postgresql/data

# 2. Configure recovery target
cat >> /var/lib/postgresql/data/recovery.conf << EOF
restore_command = 'cp /archive/wal/%f %p'
recovery_target_time = '2026-06-12 14:30:00 UTC'
EOF

# 3. Start PostgreSQL — it will replay WAL up to 14:30:00 and stop
pg_ctl start
```

### Recovery Strategy 2: Replica Promotion

If corruption happens on the primary but has not yet been replicated to replicas (for example, due to replication lag — the replica has not applied the corrupt writes yet), you can promote the replica to primary and use it as your clean copy.

This is why replication lag, while usually a problem, can occasionally be your friend during corruption recovery: a lagged replica might still have uncorrupted data that the primary no longer has.

### Recovery Strategy 3: Selective Row Restore

Sometimes you do not need to restore the entire database — only specific rows were corrupted. In this case, you can extract those rows from a backup and merge them into the live database:

```bash
# Extract specific rows from yesterday's backup
pg_restore --table=orders \
  --where="created_at > '2026-06-11' AND created_at < '2026-06-12'" \
  /backup/orders_20260611.dump \
  | psql -h production-db -d myapp
```

### The Real Story: Facebook Photo Metadata Corruption

In 2012, Facebook experienced an incident where a software bug corrupted the metadata of a large number of photos. The actual photo binary data (stored in their Haystack object store) was intact, but the metadata database that tracked which user owned which photo, what albums they belonged to, and what permissions applied had corrupted entries.

The impact: photos became inaccessible for affected users. From the user's perspective, their photos had disappeared. The actual data was there — the pointer to find it was broken.

Recovery required Facebook engineers to reconstruct metadata by cross-referencing multiple backup copies, CDN access logs (which contained photo IDs that had been recently accessed), and application-level audit logs. It took several days to recover data for all affected users.

**The lesson Facebook formalized:** backups are worthless unless tested. Facebook now runs quarterly **restore drills** — they take a copy of production data, restore it to an isolated environment, and verify that the restored data matches what they expect. They measure the time to restore and track it as a metric.

The rule for your team: if you have not tested restoring from your backups in the last 90 days, you do not have backups. You have backup-shaped objects of unknown utility.

---

## Section 6: The Strangler Fig Migration — A Full Worked Example

### The Pattern

The **Strangler Fig pattern** is named after a tree that grows around its host, gradually taking over until the host tree dies and only the new tree remains. In software, it describes migrating from one system to another by slowly routing traffic to the new system while keeping the old one running, until the old system handles zero traffic and can be decommissioned.

The key insight: you never do a "big bang" cutover where you turn off the old system and turn on the new one simultaneously. That approach is high-risk, hard to roll back, and often means all-or-nothing failure. The Strangler Fig gives you incremental migration with rollback at every step.

### The Scenario: Migrating the Users Table from PostgreSQL to DynamoDB

Your company started on PostgreSQL. Your `users` table has grown to 200 million rows. The access pattern has evolved: 95% of queries are pure key lookups by `user_id` or `email`. Joins are rare. Reporting queries go through a separate analytics database. The relational features of PostgreSQL are unused overhead.

You want to migrate to DynamoDB for this table because: DynamoDB's key-value access pattern matches your actual usage, it scales horizontally without sharding complexity, and its managed operations eliminate DBA overhead.

Here is the full four-phase migration.

### Phase 1: Dual Write

In this phase, every write goes to **both** PostgreSQL and DynamoDB. Reads still go only to PostgreSQL, which remains the source of truth.

```
PHASE 1: DUAL WRITE

   Write Request
        │
        ▼
   ┌────────────┐
   │  App Layer │
   └─────┬──────┘
         │ writes to BOTH
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐  ┌──────────┐
│  PG   │  │ DynamoDB │
│(write)│  │  (write) │
└───────┘  └──────────┘

   Read Request
        │
        ▼
   ┌────────────┐
   │  App Layer │
   └─────┬──────┘
         │ reads from PostgreSQL ONLY
         ▼
      ┌───────┐
      │  PG   │
      │(read) │   ← single source of truth
      └───────┘
```

**What happens when DynamoDB write fails?**

This is the critical question. If you write to PostgreSQL successfully but the DynamoDB write fails, your two stores are now out of sync. The standard approach: write to PostgreSQL (primary), then attempt DynamoDB write. If DynamoDB write fails, log the failure to an async retry queue. A background worker retries failed DynamoDB writes with exponential backoff. You accept eventual consistency between the stores during the dual-write phase — PostgreSQL is still the source of truth, so the inconsistency does not affect users.

**Rollback**: turn off DynamoDB writes. Zero impact to users. Zero risk.

### Phase 2: Shadow Reads

In this phase, you start reading from DynamoDB in the background ("shadow reads") and comparing results to PostgreSQL. You serve users data from PostgreSQL still. This validates that DynamoDB has correct data without risking user-facing errors.

```
PHASE 2: SHADOW READS

   Read Request
        │
        ▼
   ┌────────────────────────────────────┐
   │  App Layer                         │
   │                                    │
   │  1. Read from PostgreSQL (primary) │
   │  2. Async: also read from DynamoDB │
   │  3. Compare the two results         │
   │  4. Log any discrepancy             │
   │  5. Return PostgreSQL result to user│
   └─────┬──────────────────────────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐  ┌──────────┐
│  PG   │  │ DynamoDB │
│(read) │  │(shadow)  │
│serves │  │compare   │
│user   │  │& log     │
└───────┘  └──────────┘
                │
                ▼
         ┌─────────────┐
         │ Discrepancy │
         │    Log      │ ← track mismatch rate
         └─────────────┘
```

Your goal: get the discrepancy rate below 0.01% before advancing. Common discrepancies you will find:
- Rows that were created before dual-write was deployed (missing from DynamoDB entirely) — fix with a one-time backfill job
- Async retry failures that left some rows stale — fix your retry logic
- Type mismatches (PostgreSQL stores a date as a `DATE`, DynamoDB stores it as a string) — fix your serialization

### Phase 3: Canary Reads — Traffic Shifting

Now you flip actual reads to DynamoDB, starting with a small percentage of traffic:

```
PHASE 3: CANARY READS (gradual traffic shift)

   Read Request
        │
        ▼
   ┌─────────────────────────────────────────────┐
   │  Traffic Router / Feature Flag              │
   │                                             │
   │  user_id % 100 < 1  → DynamoDB (1% canary) │
   │  user_id % 100 >= 1 → PostgreSQL (99%)      │
   └────────────────┬────────────────────────────┘
                    │
           ┌────────┴────────┐
           │                 │
           ▼                 ▼
       ┌───────┐         ┌──────────┐
       │  PG   │         │ DynamoDB │
       │ (99%) │         │  (1%)    │
       └───────┘         └──────────┘
       
Ramp schedule:
  Week 1:  1% → DynamoDB    (monitor errors, latency, data accuracy)
  Week 2:  5% → DynamoDB
  Week 3:  20% → DynamoDB
  Week 4:  50% → DynamoDB
  Week 5:  100% → DynamoDB  ← reads fully switched
```

At each step, monitor:
- **Error rate**: DynamoDB returning errors or wrong data?
- **Latency**: p50, p95, p99 latency vs. PostgreSQL baseline
- **Data accuracy**: are the results correct? (spot-check against PostgreSQL for the canary cohort)

**Rollback at any point**: change the traffic split back to 0% DynamoDB. Users on the canary see no impact because you roll back before they notice anything wrong.

### Phase 4: Stop Writing to PostgreSQL and Decommission

After reads are fully on DynamoDB for a period with zero issues:

1. **Stop all writes to PostgreSQL** — DynamoDB is now the sole writer
2. **Keep PostgreSQL in read-only mode for 30 days** — emergency rollback window. If a serious bug surfaces, you can flip reads back to PostgreSQL during this window
3. **After 30 days with no incidents**, put PostgreSQL in maintenance mode
4. **After 60 days**, take a final backup and decommission the PostgreSQL instance

```
FULL MIGRATION TIMELINE:

Week  1-4:  Dual write (PG + Dynamo writes, PG reads)
Week  5-8:  Shadow reads (compare results, fix discrepancies)
Week  9-12: Canary reads (1% → 5% → 20% → 50% → 100% on Dynamo)
Week 13:    Stop PostgreSQL writes
Week 13-17: PostgreSQL read-only (emergency rollback window)
Week 18:    PostgreSQL decommission

TOTAL MIGRATION TIME: ~4-5 months
PRODUCTION DOWNTIME: 0 seconds
DATA LOSS RISK: near zero (dual write throughout)
ROLLBACK CAPABILITY: at every phase
```

---

## Section 7: Operational Realities Staff Engineers Must Know

The topics below do not come up in most system design interview questions. But they are the difference between a system design that looks good on a whiteboard and one that survives contact with production.

### Reality 1: Connection Pool Exhaustion — The Most Common Database Outage

The most frequent database-related outage at growing companies is not the database itself failing. It is the application running out of database connections.

Here is how it happens: your PostgreSQL instance supports 200 connections. Your application has 20 servers, each running 20 application processes, each holding a pool of 10 connections. That is 20 × 20 × 10 = 4,000 connections attempted — but PostgreSQL only allows 200. Most of those connections are rejected.

**Connection pool exhaustion** occurs when every available connection is in use and new requests must wait (or fail) for a connection to become available. Symptoms: all database queries hang, p99 latency spikes to 30+ seconds, timeouts cascade through the entire application.

The fix requires both sides:
- **On the database side**: set `max_connections` appropriately, use a connection pooler like PgBouncer between application and database (PgBouncer maintains a small pool of real connections to PostgreSQL and multiplexes thousands of application "connections" through them)
- **On the application side**: size your connection pool based on actual concurrency needs, not conservatively large — idle connections still occupy a slot

```
WITHOUT PGBOUNCER:
   20 app servers × 20 processes × 10 pool size = 4,000 connections
   PostgreSQL max: 200
   Result: 3,800 connection attempts rejected

WITH PGBOUNCER:
   4,000 app connections → PgBouncer → 50 real PG connections
   PostgreSQL max: 200
   Result: comfortable, all traffic served
```

### Reality 2: Long-Running Transactions Block Everything

In PostgreSQL, a transaction that has been open for a long time causes several serious problems:

- **Blocks VACUUM**: PostgreSQL's autovacuum process reclaims space from deleted and updated rows. A long-running transaction prevents vacuum from reclaiming any row that was visible when the transaction started. Over time, this causes **table bloat** — the table file grows without bound even as you delete data.
- **Blocks DDL**: an `ALTER TABLE` statement acquires an exclusive lock, but it waits in the lock queue behind all active transactions. A transaction open for 5 minutes will cause your DDL to wait 5 minutes before even starting.
- **Blocks other long-running queries**: if a slow transaction holds a lock on rows that other queries need, those queries queue up behind it.

Monitor for long-running transactions in production:

```sql
-- Find all transactions running longer than 5 minutes
SELECT pid, 
       now() - xact_start AS duration,
       query,
       state
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
  AND now() - xact_start > interval '5 minutes'
ORDER BY duration DESC;
```

Set `idle_in_transaction_session_timeout = '5min'` in PostgreSQL to automatically kill transactions that have been idle (not executing a query) for too long. Set `statement_timeout = '30s'` to kill individual queries that run too long.

### Reality 3: Maintenance Windows — Some Changes Require Downtime

Not every database operation can be done online. Know which operations require planned downtime:

| Operation | Online? | Notes |
|---|---|---|
| `ALTER TABLE ADD COLUMN` (nullable) | Yes | Instant metadata update |
| `ALTER TABLE ADD COLUMN NOT NULL` | No (pre-PG12) | Full table rewrite |
| `CREATE INDEX CONCURRENTLY` | Yes | Slow but non-blocking |
| `CREATE INDEX` (without CONCURRENTLY) | No | Exclusive lock |
| `VACUUM FULL` | No | Rewrites entire table, exclusive lock |
| `REINDEX` | No | Exclusive lock (use `REINDEX CONCURRENTLY` in PG12+) |
| `pg_upgrade` (major version) | No | Requires brief downtime |

### Reality 4: Backup Verification Is Not Optional

"We have backups" is not the same as "we can restore from backups." The list of things that can prevent a backup from being restorable:

- The backup process silently fails partway through (partial backup)
- The backup file is corrupted during storage
- The backup is complete but requires a specific PostgreSQL version to restore
- The backup restore process takes 18 hours, but your RTO (recovery time objective) is 4 hours

The only way to know your backups work is to test them. Run a **full restore drill** quarterly:

1. Take a copy of production backup to an isolated environment
2. Restore it to a fresh PostgreSQL instance
3. Verify that specific, known records exist and have the correct values
4. Measure how long the restore takes
5. Document the actual RTO (if it took 12 hours, your RTO is 12 hours)

### Reality 5: The Slow Query Log Is Your Best Friend

Every database has a slow query log. This log records queries that take longer than a threshold to execute. It is your primary tool for identifying performance problems.

```sql
-- PostgreSQL: enable slow query logging in postgresql.conf
log_min_duration_statement = 1000  -- log queries taking > 1000ms
log_statement = 'none'             -- don't log all statements
```

Check the slow query log weekly. The top 5 queries by total time (frequency × average duration) account for the majority of your database's CPU usage. Optimizing those 5 queries often reduces database load by 50-80%.

Tools like `pg_stat_statements` in PostgreSQL aggregate query performance automatically:

```sql
-- Top 10 queries by total time
SELECT query,
       calls,
       total_exec_time / 1000 AS total_seconds,
       mean_exec_time AS avg_ms
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
```

### Reality 6: The "It Worked in Staging" Problem

Your staging environment has 1,000 rows in the `orders` table. Production has 1 billion rows. This difference is not just a matter of scale — it fundamentally changes how the database behaves.

**Query planner differences**: PostgreSQL's query planner uses statistics to choose between query execution strategies. With 1,000 rows, a sequential scan is often faster than using an index. With 1 billion rows, the same query needs an index or it will timeout. The planner makes different choices in staging and production, so a query that takes 5ms in staging can take 45 seconds in production.

**Index selectivity**: an index on `status` where 99% of rows have `status='active'` is useless — it is not selective enough. With 1,000 rows this does not matter. With 1 billion rows, the database scans 990 million rows to find your 10 million `status='inactive'` records.

**Lock contention**: with 10 developers using staging, lock contention is invisible. With 10,000 concurrent users in production hitting the same rows, lock contention becomes catastrophic.

The mitigation: use realistic data volumes in staging for load testing. Use `EXPLAIN ANALYZE` (not just `EXPLAIN`) to see the actual execution plan the database chooses:

```sql
-- EXPLAIN shows the planned execution path
-- EXPLAIN ANALYZE actually runs the query and shows real metrics
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM orders 
WHERE user_id = 12345 AND status = 'pending';
```

### Reality 7: Read Replica Drift — Monitor Bytes, Not Just Seconds

When you add read replicas to offload read traffic from your primary, you create a new operational concern: replica lag. But measuring lag in seconds is misleading.

A replica that is "5 seconds behind" could mean:
- It processed all writes up to 5 seconds ago and is currently idle (fine — it will catch up immediately when new writes arrive)
- It is continuously 5 seconds behind because writes are arriving faster than it can apply them (a growing problem — it will fall further and further behind)

The better metric is **replication lag in bytes** (`pg_replication_slots.confirmed_flush_lsn` or `pg_stat_replication.write_lag`):

```sql
-- Check replication lag more precisely
SELECT client_addr,
       state,
       sent_lsn,
       write_lsn,
       flush_lsn,
       replay_lsn,
       write_lag,
       flush_lag,
       replay_lag
FROM pg_stat_replication;
```

If the byte-lag is growing over time, your replica cannot keep up with your write throughput. Solutions: use a more powerful replica instance, reduce write amplification on the primary, or switch from logical replication to physical streaming replication (faster).

Alert when replica lag exceeds 60 seconds of real-world time OR when byte lag is growing monotonically for more than 5 minutes. The monotonic growth pattern is the more dangerous signal because it indicates the replica will never catch up on its own.

---

## Chapter Summary

The failures described in this chapter share common themes:

**Monitoring gaps are the root cause of most disasters.** GitHub's failover disaster was caused by not monitoring replication lag. Amazon's DynamoDB event was caused by not anticipating retry amplification. Every incident has a monitoring gap that, if closed, would have prevented or significantly limited the damage.

**Safe operations require multi-step incremental approaches.** The NOT NULL column migration shows the cost of a single-step approach. The Strangler Fig migration shows the value of incremental steps with rollback at each stage. Every risky operation should be broken into smaller, reversible steps.

**The database is rarely the weakest link — the access patterns around it are.** The thundering herd problem was not a Redis or PostgreSQL bug. It was a consequence of how TTLs were set. Connection pool exhaustion is not a PostgreSQL bug. It is a consequence of how connection pools are sized and how a pooler is (not) used.

**Operational complexity does not appear on whiteboards.** Slow query logs, VACUUM, backup drills, replication byte-lag, long-running transaction monitoring — none of these appear in most system design interviews. But they are the difference between a system that survives its first year in production and one that collapses under the weight of its own data.

At L6, you are expected to hold both the high-level architecture and these operational realities in your head simultaneously. When you propose a database design, you should also be proposing how you will monitor it, migrate it safely, detect corruption, and recover from failure.

---

*End of Chapter 28 — Part G*

*Continue to Part H for exercises, discussion questions, and failure scenario walkthroughs.*
# Chapter 28 — Part I: OLAP vs OLTP and Analytical Databases

> You just learned how PostgreSQL stores rows, how Cassandra distributes across nodes, and how DynamoDB serves millisecond lookups. All of that knowledge applies to one class of problem: **transactional workloads** — many users doing small reads and writes right now. This section is about the other class: **analytical workloads** — a smaller number of queries that tear through hundreds of millions of rows at once.

---

## 1. Why Your OLTP Database Will Die on Analytics Queries

### The Setup

You are three months into your job. The product manager wants to know: "How many orders did we get per country, broken down by month, for the last two years?"

You know SQL. You write this:

```sql
SELECT
    country,
    DATE_TRUNC('month', created_at) AS month,
    COUNT(*)                        AS order_count
FROM orders
GROUP BY country, DATE_TRUNC('month', created_at)
ORDER BY month DESC;
```

You run it on your production PostgreSQL database. The `orders` table has 500 million rows.

What happens next is the most common analytics-related production incident in the industry.

### What Actually Happens

1. PostgreSQL starts a **full table scan** — it reads every single row in the `orders` table from disk. All 500 million of them.
2. The table is maybe 200 GB. Disk reads spike. The storage I/O bandwidth is saturated.
3. PostgreSQL is single-threaded for this scan (or limited to a handful of parallel workers). The CPU on the one node handling this query pegs at 100%.
4. All the other queries — the ones your users are running right now, the ones powering your checkout page — are waiting in line behind this monster query for CPU and disk.
5. Response times for normal user requests climb from 20ms to 3 seconds. Then they start timing out. Your on-call pager goes off.
6. Three minutes later, your analytics query finishes. The PM has their numbers. Your users had a terrible experience for three minutes, some abandoned their carts, and the SRE team is furious.

This scenario happens at almost every company that starts mixing analytics queries with production OLTP databases. The root cause is not that PostgreSQL is slow — it is that PostgreSQL is optimized for a completely different access pattern.

### OLTP vs OLAP — From First Principles

**OLTP (Online Transaction Processing)** is the workload of a live application. Think of it as the database doing a lot of small, precise operations all day long:
- A user loads their profile: `SELECT * FROM users WHERE id = 12345`
- Someone places an order: `INSERT INTO orders (user_id, amount, ...) VALUES (...)`
- A driver's location updates: `UPDATE drivers SET lat = 37.4, lon = -122.1 WHERE id = 9988`

The defining characteristics:
- **Many concurrent users** — hundreds or thousands of simultaneous connections
- **Small data per query** — reading or writing a handful of rows at most
- **Low latency required** — users are waiting; they want results in under 50ms
- **High write rate** — new rows arriving constantly

**OLAP (Online Analytical Processing)** is the workload of business intelligence and data science. Think of it as the database doing a few large, sweeping operations:
- "What is our revenue by product category for Q3?"
- "How many users who signed up in January are still active in June?"
- "What is the average order value for users in Germany, broken down by age group?"

The defining characteristics:
- **Few concurrent queries** — often just a handful of analysts
- **Huge data per query** — scanning millions or billions of rows
- **Higher latency tolerated** — a dashboard can take 5-10 seconds; analysts can wait
- **Low write rate** — data is typically loaded in batches, not written row-by-row

| Property | OLTP | OLAP |
|---|---|---|
| Access pattern | Point lookups, small writes | Full scans, aggregations |
| Data per query | Rows to KB | GB to TB |
| Concurrency | Thousands of users | Handful of analysts |
| Latency target | < 50ms | Seconds to minutes is acceptable |
| Optimize for | Insert/update throughput | Scan throughput, compression |
| Examples | PostgreSQL, MySQL, DynamoDB | BigQuery, Snowflake, Redshift |

### Root Cause: Row Storage vs Column Storage

To understand why PostgreSQL is bad at analytics, you have to understand how it stores data on disk.

**Row-oriented storage** (PostgreSQL, MySQL, DynamoDB): every field of a single row is stored together on disk, back to back. When you write a row, all its columns land on the same disk page.

**Column-oriented storage** (BigQuery, Snowflake, Parquet files): all values of a single column are stored together. Every `price` in the entire table is packed into one column file. Every `country` in the entire table is in another file.

Here is the same three-column table stored both ways:

```
TABLE: orders
+----+-------+---------+
| id | price | country |
+----+-------+---------+
|  1 | 120   | US      |
|  2 | 450   | UK      |
|  3 | 80    | US      |
+----+-------+---------+

ROW-ORIENTED STORAGE (PostgreSQL):
Disk block 1: [1, 120, US] [2, 450, UK] [3, 80, US]
              ^--- all fields of row 1 ---|^--- row 2---|^--- row 3

COLUMN-ORIENTED STORAGE (BigQuery / Parquet):
id file:      [1] [2] [3]
price file:   [120] [450] [80]
country file: [US] [UK] [US]
```

Now watch what happens when you run `SELECT AVG(price) FROM orders`:

```
ROW-ORIENTED READS:
Disk block 1: [1, 120, US] [2, 450, UK] [3, 80, US]
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
               Read ALL fields for ALL rows just to get price.
               For 500M rows: read every id, every country — data you don't need.

COLUMN-ORIENTED READS:
price file:   [120] [450] [80]
               ^^^^^^^^^^^^^^^^
               Read ONLY the price column. id and country files not touched.
               For 500M rows: read only 1/3 of the data (just the price column).
```

This is the core insight. In PostgreSQL, reading one column requires reading every column because they are all packed together on disk. In BigQuery, reading one column requires reading only that column's file.

For a table with 100 columns and a query that touches 3 of them, columnar storage reads 3% of the data that row storage reads. That is where the 45x speedup comes from — not magic, just physics.

**Real numbers**: the same aggregation query on 500M rows:
- PostgreSQL (row storage): ~3 minutes
- BigQuery (columnar storage): ~4 seconds

This is not because BigQuery's hardware is faster. It is because the storage model matches the access pattern.

---

## 2. Columnar Storage Internals

Now let's go one level deeper and understand what makes columnar storage so effective — beyond just "reads less data."

### Column Files on Disk

In a columnar system, when you load a table with 1 billion rows and 50 columns, you end up with 50 separate column files on disk. Each file contains all the values for that column, in row order, packed tightly together.

Because all values in a column file have the same data type (all integers, or all strings, or all timestamps), the storage engine can apply type-specific optimizations. This is what enables extreme compression.

### Compression — Why Same-Type Data Compresses Beautifully

When you pack values of the same type together, patterns emerge that compression algorithms can exploit. Three encodings matter most in practice:

**Run-Length Encoding (RLE)**

If the same value repeats many times in sequence, store it once with a count:

```
RAW:       [US, US, US, US, US, UK, UK, US, US, US]
RLE:       [(US, 5), (UK, 2), (US, 3)]
Savings:   10 values → 3 pairs. 70% compression.
```

This is huge for columns like `status` (where most orders are `COMPLETED`), `country` (where most users are in a handful of countries), or `is_active` (mostly `true`). These are called **low-cardinality columns** — few distinct values. RLE compresses them into a tiny fraction of their original size.

**Dictionary Encoding**

For string columns with repeating values, store each unique string once in a dictionary, then store integer codes in the column:

```
RAW:       [United States, United States, United Kingdom, United States, United Kingdom]
           These strings are 13-14 bytes each. 5 values = ~70 bytes.

Dictionary: {0: "United States", 1: "United Kingdom"}
Encoded:    [0, 0, 1, 0, 1]
            5 integers instead of 5 long strings. ~95% compression.
```

Dictionary encoding also makes comparisons faster. Instead of comparing strings byte by byte, the query engine compares small integers. `WHERE country = 'United States'` becomes "look up the code for 'United States' (answer: 0), then scan the integer array for values equal to 0."

**Delta Encoding**

For sorted or nearly-sorted numeric columns — especially timestamps — store the first value followed by differences between consecutive values:

```
RAW timestamps (Unix seconds):
[1700000000, 1700000005, 1700000012, 1700000009, 1700000020]

Delta encoded:
[1700000000, +5, +7, -3, +11]
```

The deltas are small integers, which compress far better than large absolute values. A timestamp column that takes 8 bytes per value raw might compress to 1-2 bytes per value with delta encoding.

**The combined effect**: a 1 TB table in row-oriented storage often compresses to 100-200 GB in columnar storage — a 5-10x reduction. In BigQuery's cost model ($5/TB scanned), that compression directly cuts your bill.

### Vectorized Execution

Modern CPUs have **SIMD (Single Instruction, Multiple Data)** instructions that can perform the same operation on 8 or 16 values simultaneously. Instead of adding two numbers, a SIMD instruction adds eight pairs of numbers in one clock cycle.

Row-oriented databases process one row at a time through the query engine:
```
for each row:
    check WHERE clause
    add value to running sum
    increment count
```

Columnar databases use **vectorized execution** — they process a batch of 1024 values at once:
```
load 1024 price values into CPU registers
apply WHERE mask to all 1024 simultaneously  (SIMD)
add matching values to running sum            (SIMD)
add count of matches                          (SIMD)
repeat for next 1024 values
```

The result is dramatically better CPU utilization. The processor spends its time doing arithmetic, not jumping around chasing pointers to individual rows.

### Zone Maps — Skipping Data Without Reading It

Even with columnar storage, you want to avoid reading data you don't need at all. **Zone maps** (also called **min-max indexes**) make this possible.

Each column file (or each chunk of a column file — typically 64MB to 1GB) stores metadata:
- The minimum value in this chunk
- The maximum value in this chunk
- Optionally, a Bloom filter for membership tests

When a query runs with a filter like `WHERE amount > 1000`, the query engine checks each chunk's zone map before reading any data:

```
QUERY: SELECT SUM(amount) FROM orders WHERE amount > 1000

Column file: amount (chunked into 4 blocks)

+-------------+-------+-------+----------+----------+
| Block       | Min   | Max   | Rows     | Read?    |
+-------------+-------+-------+----------+----------+
| Block 1     | 5     | 800   | 250,000  | SKIP     |
|             |       |       |          | max < 1000|
+-------------+-------+-------+----------+----------+
| Block 2     | 200   | 1500  | 250,000  | READ     |
|             |       |       |          | may match|
+-------------+-------+-------+----------+----------+
| Block 3     | 1100  | 9000  | 250,000  | READ     |
|             |       |       |          | all match|
+-------------+-------+-------+----------+----------+
| Block 4     | 10    | 400   | 250,000  | SKIP     |
|             |       |       |          | max < 1000|
+-------------+-------+-------+----------+----------+

Result: Only 500,000 rows read instead of 1,000,000.
        50% of I/O eliminated without reading a single data byte.
```

Zone maps work best when data is sorted or clustered — then low and high value ranges end up in separate blocks. This is why BigQuery's **clustering** feature and Redshift's **sort keys** matter: they arrange data so that zone maps can skip large chunks.

---

## 3. The Three Main Analytical Databases

### BigQuery — Google's Serverless Data Warehouse

**BigQuery** is Google's fully managed analytical database. You do not provision any servers, choose any cluster sizes, or manage any infrastructure. You upload data (or connect to existing Google Cloud data sources), and you run SQL queries against it.

**Architecture — Dremel Under the Hood**

BigQuery is powered by **Dremel**, a distributed query execution engine Google built internally around 2006. The way Dremel executes a query resembles a tree:

```
           ROOT NODE
           (coordinates query)
               |
    +----------+----------+
    |          |          |
INTERMEDIATE  INT.       INT.
   NODE       NODE       NODE
    |          |          |
  +--+       +--+       +--+
  L  L       L  L       L  L
  E  E       E  E       E  E
  A  A       A  A       A  A
  F  F       F  F       F  F

LEAF NODES: Read column data directly from Colossus
            (Google's distributed filesystem, like HDFS but faster)

Thousands of leaf nodes read in parallel.
Intermediate nodes aggregate partial results.
Root node produces the final answer.
```

When you run a query in BigQuery, it may be reading data from thousands of nodes simultaneously. This is why a query on a 1 TB table takes 4 seconds instead of 4 minutes — thousands of machines are doing the work in parallel.

**Partitioning and Clustering**

BigQuery stores table data in partitions. You partition on a date or timestamp column, which creates separate storage files per day (or month, or hour). When a query includes a date filter, BigQuery reads only the relevant partitions:

```sql
-- Without partitioning: scans 3 years = 1095 partitions
SELECT COUNT(*) FROM orders WHERE country = 'US';

-- With DATE(created_at) partitioning:
SELECT COUNT(*) FROM orders
WHERE DATE(created_at) BETWEEN '2024-01-01' AND '2024-03-31';
-- Scans only 90 partitions instead of 1095. 92% cost reduction.
```

**Clustering** works within a partition: rows within each partition are sorted by the clustering columns. If you cluster on `country`, then all rows for `country = 'US'` are adjacent on disk within each partition. Combined with zone maps, a filter on `country` can skip the vast majority of blocks.

**BigQuery Cost Model**

BigQuery charges $5 per terabyte of data scanned. This forces you to think about data layout:
- Partitioning reduces scans by restricting which partitions are read
- Clustering reduces scans via zone map skipping within partitions
- Selecting specific columns (not `SELECT *`) reduces scans to only needed column files

**When to use BigQuery**: ad-hoc analytics on large, irregular datasets; teams without infrastructure expertise; workloads with unpredictable volume (you pay only for what you scan, not for idle compute).

**When not to use BigQuery**: row-level updates or deletes at high frequency (BigQuery is optimized for append-heavy workloads, updates are expensive); sub-second query latency requirements (BigQuery has a startup overhead of 1-3 seconds even for small queries).

---

### Snowflake — The Separated Architecture

**Snowflake** built its business on one core architectural decision: separate storage from compute completely. This sounds simple but has profound operational consequences.

**Architecture — Two Independent Layers**

```
+--------------------------------------------------+
|              SNOWFLAKE ARCHITECTURE              |
+--------------------------------------------------+
|                                                  |
|   COMPUTE LAYER                                  |
|   +---------------+  +---------------+           |
|   | Virtual       |  | Virtual       |           |
|   | Warehouse A   |  | Warehouse B   |           |
|   | (Engineering) |  | (Marketing)   |           |
|   +-------+-------+  +-------+-------+           |
|           |                  |                   |
|           +--------+---------+                   |
|                    |                             |
|   STORAGE LAYER    v                             |
|   +--------------------------------------+       |
|   | Columnar data files in S3/GCS/Azure  |       |
|   | Compressed, micro-partitioned        |       |
|   +--------------------------------------+       |
|                                                  |
+--------------------------------------------------+
```

The **storage layer** is columnar data sitting in cloud object storage (S3 on AWS, GCS on Google Cloud, Azure Blob). You pay for storage at cloud storage rates — cheap, durable, effectively infinite.

The **compute layer** is "virtual warehouses" — clusters of CPU/RAM that you spin up to run queries. You pay only while the warehouse is running. You can pause a warehouse when nobody is using it, and pay zero compute cost during nights and weekends.

**Why This Matters**

In traditional data warehouses (like on-premise Teradata, or early Redshift), storage and compute are coupled. If you need more processing power, you add nodes — but each node also adds storage. If you run out of storage, you add nodes — but now you have more compute than you need. You pay for both at all times.

Snowflake decouples them. Your storage grows based on data volume. Your compute scales based on query complexity. They evolve independently.

**Multi-Cluster Concurrency**

Because compute is separate from storage, you can run multiple virtual warehouses against the same data simultaneously:
- Engineering team's warehouse: running complex ML feature queries
- Marketing team's warehouse: running campaign performance dashboards
- Finance team's warehouse: running month-end close calculations

All three access the same storage layer, with no resource contention between them. In a traditional warehouse, these three workloads would compete for the same CPU pool.

**Time Travel**

Snowflake retains the history of every change to your data. You can query your table as it was at any point in the last 90 days:

```sql
-- What did the orders table look like 24 hours ago?
SELECT COUNT(*) FROM orders
AT (OFFSET => -86400);  -- 86400 seconds = 24 hours

-- What did it look like before a specific timestamp?
SELECT * FROM orders
AT (TIMESTAMP => '2024-11-01 09:00:00'::TIMESTAMP_TZ);
```

This is implemented using **copy-on-write at the micro-partition level**: when you update or delete data, Snowflake writes new micro-partitions and marks the old ones as "retired but retained." They are not deleted until the retention window expires.

**Zero-Copy Cloning**

You can create a full clone of a 10 TB dataset instantly:

```sql
CREATE TABLE orders_dev CLONE orders;
```

This does not copy any data. It creates a new table object pointing to the same underlying micro-partitions. When you write to `orders_dev`, Snowflake uses copy-on-write to diverge — only modified partitions are duplicated. If you never write to the clone, you pay zero extra storage.

This makes it practical to give every engineer their own copy of production data for development and testing.

**When to use Snowflake**: multiple teams querying the same data with different query patterns; variable or spiky workload (pause compute when idle); need for dev/staging copies of large datasets; want Time Travel for audit and recovery.

---

### Redshift — Amazon's Provisioned Data Warehouse

**Amazon Redshift** is AWS's data warehouse product. Unlike BigQuery (serverless) and Snowflake (separated layers), Redshift is a **provisioned cluster**: you choose how many nodes you want, what type they are, and you pay for those nodes continuously whether or not you are running queries.

**MPP Architecture**

Redshift uses **Massively Parallel Processing (MPP)**. Your data is divided across all the nodes in your cluster. When a query runs, every node processes its slice of the data in parallel, then the results are merged:

```
+-----------------------------------------------------+
|                  REDSHIFT CLUSTER                   |
|                                                     |
|  Leader Node                                        |
|  (parses SQL, creates execution plan, coordinates)  |
|         |                                           |
|    +----+----+----+----+                            |
|    |    |    |    |    |                            |
|  Node1 N2  N3  N4  N5  ... (up to 128 nodes)       |
|  slice slice slice ...                              |
|  of   of    of                                      |
|  data data  data                                    |
|                                                     |
|  Each node has local SSD, processes its own slice.  |
|  Results merged by leader node.                     |
+-----------------------------------------------------+
```

**Distribution Styles — A Critical Choice**

When you create a table in Redshift, you choose how rows are distributed across nodes. This choice has a large impact on JOIN performance.

**KEY distribution**: rows with the same value in the distribution key go to the same node.

```sql
CREATE TABLE orders (
    order_id    BIGINT,
    user_id     BIGINT,
    amount      DECIMAL
) DISTKEY(user_id);

CREATE TABLE users (
    user_id     BIGINT,
    country     VARCHAR
) DISTKEY(user_id);
```

Now when you run `SELECT ... FROM orders JOIN users ON orders.user_id = users.user_id`, each node can do the JOIN locally — all `orders` rows and `users` rows for `user_id = 12345` are on the same node. No data needs to move across the network.

**EVEN distribution**: rows are distributed round-robin across nodes. Balanced storage, but JOINs require shuffling data across the network (slow).

**ALL distribution**: the entire table is copied to every node. Makes sense only for small, frequently joined dimension tables (a few million rows). JOINs are always local, but you pay for N copies of the data.

**Sort Keys**

Redshift sorts data within each node's slice according to a sort key you define:

```sql
CREATE TABLE orders (
    order_id   BIGINT,
    created_at TIMESTAMP,
    amount     DECIMAL
) SORTKEY(created_at);
```

Because rows are sorted by `created_at` on disk, zone map skipping is highly effective for date-range queries. A query like `WHERE created_at > '2024-11-01'` can skip all blocks whose max `created_at` is before November.

**The Vacuum Problem**

Like PostgreSQL, Redshift marks deleted rows as "dead" but does not immediately reclaim their space. Over time, your tables accumulate dead rows that waste disk space and slow down scans. You must run `VACUUM` periodically to reclaim space and re-sort any rows that were inserted out of order.

This is an operational overhead that BigQuery and Snowflake abstract away.

**When to use Redshift**: deep AWS integration (S3, Glue, Lambda, SageMaker); workloads with complex SQL and many multi-table JOINs (where careful distribution key selection pays off); need for consistent, provisioned capacity (no cold-start latency).

---

## 4. Analytical Data Modeling — Star Schema and Snowflake Schema

Even with a columnar database, badly modeled data causes slow queries and confusing logic. The standard approach to analytical data modeling is the **star schema**, invented by Ralph Kimball in the 1990s and still dominant today.

### Why Denormalize for Analytics

In operational databases, you normalize aggressively — each fact lives in exactly one place, foreign keys link tables together. This is great for updates (change one row, done) and for write performance. But for analytical queries, normalization is painful.

A query like "total revenue by user country and product category" requires joining `orders` → `users` → `addresses` → `products` → `product_categories`. Six tables, hundreds of millions of rows being joined together. Each join is expensive.

The analytical solution is to **denormalize** — pre-compute joins, accept some redundancy, optimize for read speed.

### Star Schema Structure

```
                        +------------------+
                        |  dim_date        |
                        |------------------|
                        | date_key  (PK)   |
                        | date              |
                        | month             |
                        | quarter           |
                        | year              |
                        +--------+---------+
                                 |
+------------------+    +--------+---------+    +------------------+
|  dim_user        |    |  fact_orders     |    |  dim_product     |
|------------------|    |------------------|    |------------------|
| user_key  (PK)   +----+ user_key   (FK)  +----+ product_key (PK) |
| user_name        |    | product_key (FK) |    | product_name     |
| country          |    | date_key    (FK) |    | category         |
| age_group        |    | store_key   (FK) |    | brand            |
| signup_date      |    | order_id         |    | unit_cost        |
+------------------+    | quantity         |    +------------------+
                        | amount           |
                        | discount         |    +------------------+
                        +--------+---------+    |  dim_store       |
                                 |              |------------------|
                                 +--------------+ store_key   (PK) |
                                                | store_name       |
                                                | city             |
                                                | country          |
                                                +------------------+
```

The **fact table** (`fact_orders`) sits in the center. It contains:
- Foreign keys to every dimension table
- The numeric **measures** that you aggregate (quantity, amount, discount)
- Potentially billions of rows
- Few columns relative to the number of rows

The **dimension tables** (`dim_user`, `dim_product`, `dim_date`, `dim_store`) sit around the edges. They contain:
- The descriptive attributes you filter and group by (country, category, month)
- Relatively few rows (millions, not billions)
- Many columns — the "context" around each fact

A typical analytical query looks like:

```sql
-- Total revenue by country and product category for Q4 2024
SELECT
    u.country,
    p.category,
    SUM(f.amount)   AS total_revenue
FROM
    fact_orders     f
    JOIN dim_user   u ON f.user_key   = u.user_key
    JOIN dim_product p ON f.product_key = p.product_key
    JOIN dim_date   d ON f.date_key   = d.date_key
WHERE
    d.quarter = 4
    AND d.year = 2024
GROUP BY
    u.country,
    p.category
ORDER BY
    total_revenue DESC;
```

The JOIN is between the large fact table and small dimension tables. Columnar storage + MPP handles this efficiently: each dimension table fits in memory, and the fact table is scanned in parallel across many nodes.

### Slowly Changing Dimensions (SCD)

Here is a real problem: a user signs up from the US, then moves to the UK. Their `country` field in `dim_user` needs to change. But you have historical orders linked to this user. Should those historical orders now show the user's current country (UK) or their country at the time of purchase (US)?

For most analytical use cases, you want historical accuracy — orders placed when the user was in the US should count toward US revenue. This is the **slowly changing dimension** problem.

**SCD Type 1 — Overwrite**: update the row in `dim_user` with the new country. Simple, but you lose history. Historical orders now look like they were placed in the UK. Wrong.

**SCD Type 2 — Add a New Row**: when the user moves, instead of updating, insert a new row with a date range:

```
dim_user:
+----------+-----------+---------+---------------------+---------------------+
| user_key | user_id   | country | valid_from          | valid_to            |
+----------+-----------+---------+---------------------+---------------------+
| 1001     | user_999  | US      | 2022-01-15 00:00:00 | 2024-06-30 23:59:59 |
| 1002     | user_999  | UK      | 2024-07-01 00:00:00 | 9999-12-31 23:59:59 |
+----------+-----------+---------+---------------------+---------------------+
```

Each order's `user_key` foreign key points to the row that was valid at the time of purchase. Historical accuracy is preserved. The downside: queries become more complex (you must join on both the key and the valid date range), and the dimension table grows over time.

**SCD Type 3 — Previous Value Column**: add a `previous_country` column to the row. Simple queries, but you can only track one level of history. If the user moves three times, you only know the last two countries.

In practice, **SCD Type 2 is the standard** for anything that matters — revenue attribution, cohort analysis, regulatory compliance. Type 1 is used for corrections (fixing a typo). Type 3 is rarely used.

### Snowflake Schema (Not the Product)

A **snowflake schema** is a star schema where the dimension tables are themselves normalized. For example, instead of having `category` as a column in `dim_product`, you create a separate `dim_category` table and join to it:

```
dim_product → dim_category → dim_department
```

This saves some storage (category names are stored once, not repeated for every product). But it requires an additional JOIN in every query. For most analytical systems, the storage savings are not worth the query complexity. Star schema is generally preferred.

---

## 5. Lambda Architecture and Kappa Architecture

You have an analytical database full of historical data. But your product manager also wants to know "how many orders in the last 5 minutes?" History alone is not enough — you also need real-time data. This is the problem that Lambda and Kappa architectures solve.

### The Core Tension

Two conflicting requirements:
1. **Accuracy**: "Compare this month's revenue to the same month last year." This requires reliable, complete historical data — typically computed by a batch job that runs on all historical data.
2. **Freshness**: "How many users are on the site right now?" This requires data that is seconds or minutes old — not data that was computed last night.

Neither a pure batch system nor a pure streaming system can satisfy both requirements simultaneously.

### Lambda Architecture — Two Codepaths

**Lambda Architecture** (named by Nathan Marz around 2011) solves this with two parallel pipelines:

```
                              +-------------------+
                              |   DATA SOURCES     |
                              |  (PostgreSQL, app) |
                              +--------+----------+
                                       |
                              +--------v----------+
                              |      KAFKA         |
                              |  (message queue,   |
                              |   event log)       |
                              +---+----------+----+
                                  |          |
              +-------------------+          +-------------------+
              |                                                  |
    +---------v----------+                        +--------------v-----+
    |    SPEED LAYER      |                        |   BATCH LAYER      |
    |  Flink / Spark      |                        |   Spark / Hadoop   |
    |  Streaming          |                        |   Runs every 1h    |
    |  (last few minutes) |                        |   on ALL history   |
    +---------+----------+                        +-----------+--------+
              |                                               |
    +---------v----------+                        +----------v---------+
    |  Redis / Druid      |                        |  BigQuery /        |
    |  (fast, recent)     |                        |  Snowflake         |
    |                     |                        |  (complete, slow)  |
    +----------+---------+                        +-----------+--------+
               |                                              |
               +--------------------+--------------------------+
                                    |
                          +---------v--------+
                          |  SERVING LAYER   |
                          |  Query engine    |
                          |  merges results  |
                          +------------------+
```

A query like "orders in the last 5 minutes" hits the speed layer (Redis, Druid). A query like "revenue by month for the last 2 years" hits the batch layer (BigQuery). A query that spans both — "year-to-date revenue through this very minute" — merges results from both layers.

**The Problem with Lambda**

You now have the same business logic implemented twice: once in the streaming job (Flink) and once in the batch job (Spark). They need to produce exactly the same answers for the same time periods or your dashboards will show inconsistent numbers. Keeping two implementations in sync as business logic evolves is painful.

When a bug is found in the batch logic, you fix the Spark job, reprocess historical data, and re-serve. Then you find the same bug in the Flink job. Every change is double the work.

### Kappa Architecture — One Codepath

**Kappa Architecture** (proposed by Jay Kreps, creator of Kafka, in 2014) eliminates the batch layer. There is only one pipeline: streaming.

```
DATA SOURCES → KAFKA (retain ALL history) → FLINK → DATA STORE
```

Kafka is configured to retain all historical data indefinitely (or for years). When you need to reprocess history — say, after fixing a bug in your Flink job — you start a new streaming job from the beginning of the Kafka log. It replays all historical events as if they were new, producing a corrected output.

**The Problem with Kappa**

Keeping years of data in Kafka is expensive. Kafka stores data on disk, and the cost scales with data volume and retention period. At large scale (trillions of events per year), this becomes significant.

Reprocessing years of history through a streaming job also takes a long time — potentially hours or days for very large datasets, during which you serve stale results.

### The Modern Approach

As of 2024, the distinction between Lambda and Kappa has blurred considerably. Streaming systems like **Apache Flink** and **Spark Structured Streaming** are now fast enough and reliable enough that many companies build a single streaming pipeline that handles both real-time and historical use cases.

Storage systems like Apache Iceberg, Delta Lake, and Apache Hudi allow streaming writes directly into the analytical data store, with support for exactly-once semantics, time travel, and schema evolution.

The practical answer for most L6 system design interviews: keep a streaming pipeline for real-time data (Kafka → Flink → analytical store with 5-30 second latency), and use the same analytical store for historical queries. The "separate batch layer" is usually not worth the operational complexity unless you have specific accuracy requirements that streaming cannot meet.

---

## 6. HTAP — Having Both in One System (and Why It's Hard)

**HTAP (Hybrid Transactional/Analytical Processing)** is the idea of running both OLTP and OLAP workloads on a single system. The appeal is obvious: no data pipeline, no replication lag, no operational complexity of two separate systems.

Systems that attempt HTAP: **TiDB** (open-source), **SingleStore** (formerly MemSQL), **Google AlloyDB**, **SAP HANA**, **Oracle In-Memory**.

### Why It's Genuinely Hard

The fundamental conflict: analytical queries are long-running and resource-intensive. A query scanning 500M rows takes 100% of available disk I/O for several seconds. During those seconds, the short-lived transactional queries — the ones your users are waiting on — are competing for the same I/O bandwidth and same CPU.

This is not a software problem that can be engineered away. It is a physics problem: disk I/O bandwidth is finite. When an analytical query consumes it, transactional queries suffer higher latency.

Systems try to mitigate this in several ways:

**Read replicas for analytics**: run a replica of the OLTP database that receives replication from the primary, and direct analytical queries there. Users still hit the primary. The replica absorbs the analytical load.

The problem: replication lag. Changes committed to the primary take some time (milliseconds to seconds) to appear on the replica. For analytics that require real-time accuracy, this is acceptable. For anything requiring immediate consistency, it is not.

**TiDB's approach**: TiDB runs two storage engines internally — **TiKV** (row-oriented, for OLTP) and **TiFlash** (columnar, for OLAP). Data is synchronously replicated to both. The query optimizer decides which engine to use based on the query pattern.

This works reasonably well for moderate workloads. At very high analytical query volume, even TiFlash's resource consumption can affect TiKV's latency.

### The Staff Engineer's Perspective

Most systems at scale that need both OLTP and OLAP workloads keep them **separate and synced via CDC** (Change Data Capture):

```
PostgreSQL (OLTP, users writing)
    → Debezium (CDC, reads WAL)
    → Kafka (buffers, distributes)
    → BigQuery or Snowflake (OLAP, analysts reading)
```

The tradeoff is 5-15 minutes of latency between a transaction happening and it being visible in the analytical store. For most analytical use cases (dashboards, reports, ML features), this latency is acceptable. The benefit is complete workload isolation — your analytical queries cannot affect your production OLTP latency.

---

## 7. The Complete Data Pipeline Architecture

Let's assemble everything into a concrete end-to-end picture. This is the architecture you will describe in a system design interview when the requirements include both operational and analytical data.

### The Full Pipeline

```
+----------------+     +------------+     +----------+     +-----------+     +------------+
|  PostgreSQL    |     |  Debezium  |     |  Kafka   |     |   dbt     |     | BigQuery / |
|  (OLTP)       +---->+  (CDC)     +---->+ (queue)  +---->+ (transform+---->+ Snowflake  |
|                |     |            |     |          |     |  + model) |     | (OLAP)     |
|  users write   |     | reads WAL  |     | buffers  |     | raw→star  |     | analysts   |
|  orders here   |     | publishes  |     | & fans   |     | schema    |     | query here |
|                |     | row changes|     | out      |     |           |     |            |
+----------------+     +------------+     +----------+     +-----------+     +------------+
       |                                       |
       |                              +--------v----------+     +------------+
       |                              |  Flink            |     |  Redis /   |
       |                              |  (streaming       +---->+ Druid      |
       |                              |   aggregation)    |     | (real-time |
       |                              +-------------------+     |  queries)  |
       |                                                        +------------+
       |
  LATENCY AT EACH HOP:
  PostgreSQL → Debezium:  < 1 second (WAL is near-real-time)
  Debezium → Kafka:       < 1 second
  Kafka → dbt:            5-10 minutes (dbt runs on schedule, not continuous)
  dbt → BigQuery:         1-2 minutes (load job)
  Total: ~5-15 minutes

  REAL-TIME PATH (Kafka → Flink):
  Kafka → Flink → Redis:  2-5 seconds end-to-end
```

### Each Component's Role

**Debezium** is an open-source CDC tool that connects to PostgreSQL (or MySQL, MongoDB, etc.) and reads the **Write-Ahead Log (WAL)** — the same log PostgreSQL uses for crash recovery. Every INSERT, UPDATE, and DELETE that PostgreSQL commits is recorded in the WAL. Debezium reads it and publishes each change as a message to Kafka. This happens within about 100ms of the transaction committing. Importantly, this does not add any load to PostgreSQL itself — reading the WAL is a background operation.

**Kafka** buffers and distributes the event stream. Multiple downstream consumers can independently read from the same Kafka topic at their own pace — Flink reads it at stream speed, dbt reads it on a schedule, an ML feature pipeline might read it at yet another pace. Kafka retains messages for a configurable retention period (days to weeks), so if a downstream consumer falls behind, it can catch up.

**dbt (data build tool)** is a SQL-based transformation framework. You write SQL `SELECT` statements that define how raw event data gets transformed into the star schema tables your analysts query. dbt handles dependency ordering (run `dim_user` before `fact_orders` that references it), incremental updates (only process new data since the last run), and documentation. It runs on a schedule — every 5 minutes, every hour, or daily — depending on your freshness requirements.

**BigQuery or Snowflake** is the end destination. Analysts, dashboards, and ML pipelines query here. The data is 5-15 minutes old — acceptable for all but the most latency-sensitive use cases.

**Flink** handles the real-time path. It reads from Kafka in a continuous stream, computes rolling aggregations (orders per minute, revenue per country in the last hour), and writes results to a fast serving layer (Redis, Druid, or directly to BigQuery's streaming insert API). This path has 2-5 seconds of end-to-end latency.

### Putting It in a System Design Interview

When an interviewer says "we have a PostgreSQL database and we need to support analytics dashboards for our business team," the answer is not "add indexes" or "run queries on a read replica." The answer is this pipeline:

1. **CDC with Debezium** to capture changes without affecting the OLTP database
2. **Kafka** as the event backbone, decoupling producers from consumers
3. **dbt** to transform raw events into clean, star-schema analytical tables
4. **BigQuery or Snowflake** as the analytical store
5. **Flink** for any real-time metrics that require sub-minute freshness

The tradeoff to acknowledge: 5-15 minutes of latency. The justification: complete workload isolation — your analytics queries cannot affect your production latency, and you can evolve the analytical schema independently of the OLTP schema.

---

## Summary

| Concept | Key Insight |
|---|---|
| Row vs column storage | Row storage reads entire rows; columnar storage reads only needed columns — 3-100x less I/O for analytics |
| Columnar compression | Same-type data compresses 5-10x better than mixed-type rows |
| Zone maps | Skip entire column file blocks without reading data by checking min/max metadata |
| BigQuery | Serverless, pay-per-scan, Dremel distributed execution, partition+cluster to cut costs |
| Snowflake | Separate storage and compute; pause compute to pay near-zero; Time Travel; zero-copy cloning |
| Redshift | Provisioned MPP cluster; distribution keys determine JOIN efficiency; requires VACUUM |
| Star schema | Fact table (billions of rows, foreign keys, measures) + dimension tables (millions of rows, descriptive attributes) |
| SCD Type 2 | Add new rows with date ranges to track history of slowly changing attributes |
| Lambda architecture | Batch layer for accuracy + speed layer for freshness, but two codepaths for same logic |
| Kappa architecture | One streaming pipeline, replay Kafka for reprocessing — simpler but requires retaining all history |
| HTAP | Analyticals and transactionals on one system — theoretically appealing, practically difficult at scale |
| CDC pipeline | PostgreSQL → Debezium → Kafka → dbt → BigQuery: 5-15 min latency, full workload isolation |

The fundamental lesson is that OLTP and OLAP are not different points on a performance slider — they are fundamentally different workloads that benefit from fundamentally different storage and execution models. Trying to use one system for both is fighting physics. The mature engineering answer is separate systems, synced via a well-designed data pipeline.

---

## Vocabulary Reference

These terms appear frequently in interviews and engineering discussions. Know them precisely:

**Columnar storage**: A file format where each column's values are stored contiguously on disk, rather than storing complete rows together. Enables reading only the columns a query needs.

**Parquet**: The most common open columnar file format, used by Spark, BigQuery, Snowflake (internally), and nearly every modern analytical tool. Stores column data in compressed, chunked row groups.

**Fact table**: The central table in a star schema. Contains foreign keys to dimensions and numeric measures. Has many rows (billions), few columns.

**Dimension table**: A lookup table in a star schema. Contains descriptive attributes (names, categories, geographies). Has few rows (millions), many columns.

**SCD**: Slowly Changing Dimension — a dimension table attribute that changes over time (user's address, product's price). Type 2 (add a new row with date range) preserves full history.

**CDC (Change Data Capture)**: The practice of capturing every row-level change (insert, update, delete) from a database's transaction log and publishing those changes as a stream. Debezium is the most common CDC tool.

**WAL (Write-Ahead Log)**: PostgreSQL's durability mechanism — every change is written to the WAL before being applied to the actual table. Debezium reads the WAL to detect changes without polling the table.

**dbt (data build tool)**: A SQL transformation framework. You write SELECT statements; dbt handles orchestration, dependency resolution, incremental loading, and documentation generation.

**Dremel**: Google's internal distributed query engine that powers BigQuery. Uses a tree of workers to parallelize query execution across thousands of nodes.

**Micro-partition**: Snowflake's internal storage unit. Each micro-partition holds 50-500MB of compressed columnar data. Snowflake uses micro-partition metadata (min/max per column) for zone-map-style pruning.

**Virtual warehouse**: Snowflake's term for a compute cluster. You can have multiple virtual warehouses of different sizes running simultaneously against the same storage layer.

**MPP (Massively Parallel Processing)**: Architecture where data is partitioned across many nodes and each node processes its local partition independently. Redshift uses MPP. Results from each node are merged by a coordinator.

**Distribution key**: In Redshift, the column used to assign rows to nodes. Rows with the same distribution key value land on the same node, enabling local (network-free) JOINs on that key.

**Vectorized execution**: Query processing that operates on batches of values (typically 512-4096) at once, exploiting CPU SIMD instructions, rather than processing one row at a time through a generalized interpreter.

**Run-length encoding**: A compression scheme where consecutive repeated values are stored as (value, count) pairs. Effective for low-cardinality columns in sorted columnar data.

**Zone map**: Per-block metadata storing the min and max values of a column within that block. Allows the query engine to skip blocks that cannot possibly contain values matching a filter predicate.

**Time Travel**: Snowflake's (and Iceberg's) capability to query a table as it existed at a past point in time, implemented via copy-on-write versioning of micro-partitions.

**Zero-copy clone**: Snowflake's ability to create an instant logical copy of a large table that shares the same physical data as the original. Divergence only occurs when either copy is modified (copy-on-write).
# Chapter 28 — Part J: Caching as a System Design Pattern

> "There are only two hard things in Computer Science: cache invalidation and naming things."
> — Phil Karlton

---

## Table of Contents

1. What a Cache Actually Is (And What It Isn't)
2. The Four Caching Strategies
   - Cache-Aside (Lazy Loading)
   - Read-Through
   - Write-Through
   - Write-Behind (Write-Back)
3. Cache Invalidation: The Hardest Problem in Computer Science
4. Cache Stampede and the Thundering Herd Problem
5. Multi-Level Caching
6. What NOT to Cache (Anti-Patterns)
7. Cache Sizing and Eviction Policies
8. Distributed Cache Failure Scenarios

---

## 1. What a Cache Actually Is (And What It Isn't)

Before writing a single line of Redis configuration, you need to understand what a cache actually is — because most engineers who reach for it have only a surface-level model.

A **cache** is a faster, smaller, temporary copy of data from a slower, larger, authoritative store. That is the complete definition. Every word matters.

- **Faster**: this is the entire reason caches exist. If the cache weren't faster, there would be no point.
- **Smaller**: caches can only hold a fraction of the data in the backing store. You have to choose what to keep.
- **Temporary**: cache entries are not the source of truth. They can disappear at any moment. The database is always the real record.

### The Desk Analogy

Imagine you work in an office. Down the hall, behind two locked doors, is a filing cabinet full of documents — every contract, every invoice, every client record your company has ever created. That filing cabinet is your **database**. It holds everything. It is authoritative. But walking down the hall, finding the cabinet, unlocking it, and pulling out a folder takes two minutes every time.

Now imagine your desk. On your desk you keep copies of the ten documents you use every day. You grabbed them last Tuesday. They are right there — you can read them in two seconds without leaving your chair. That desk is your **cache**.

The problem? Someone updated the client record in the filing cabinet on Thursday. Your desk copy still has the old address. Your desk and the filing cabinet are **out of sync**.

That is the central problem of caching. The performance gain is obvious. The danger of stale data is less obvious but far more consequential.

### Three Cache Metrics That Actually Matter

Before deploying a cache, you need to know how to measure whether it is working. There are three numbers that matter:

| Metric | Definition | Target |
|---|---|---|
| **Hit rate** | % of requests served from cache | 90%+ (aim for 95%) |
| **Miss rate** | % of requests that fall through to the DB | 10% or less (= 1 - hit rate) |
| **Latency difference** | How much faster the cache is | Typically 100x |

To make the latency difference concrete: a Redis read in the same data center completes in roughly **0.1 to 0.5 milliseconds**. A PostgreSQL query that hits disk takes **10 to 50 milliseconds**. That is a 100x to 200x difference in response time.

If your hit rate is 95%, only 5% of requests hit the database. Your database is now doing one-twentieth of its former work. That is the leverage caching provides.

If your hit rate is 50%, half your requests still hit the database. You have paid the cost of operating a cache — the infrastructure, the code complexity, the failure modes — and received only marginal benefit. A 50% hit rate is usually a sign that you are caching the wrong things.

---

## 2. The Four Caching Strategies

There are four fundamental ways to integrate a cache with a database. Each makes different tradeoffs between read speed, write speed, consistency, and code complexity. Knowing all four — and being able to explain when to use each — is an L6-level expectation.

---

### Strategy 1: Cache-Aside (Lazy Loading) — The Most Common Pattern

**Cache-aside** means the application code is responsible for managing the cache. The cache does not know anything about the database. The database does not know anything about the cache. The application code glues them together manually.

#### The Read Path

```
Request arrives for user_id = 123

Step 1: Check cache
        Key: "user:123"

        ┌─────────────────────────────────────┐
        │           CACHE HIT PATH            │
        │                                     │
        │  App ──────► Cache                  │
        │              "user:123" found        │
        │              ◄──── return data       │
        │  App returns data to client         │
        │  (total time: ~0.3ms)               │
        └─────────────────────────────────────┘

        ┌─────────────────────────────────────┐
        │           CACHE MISS PATH           │
        │                                     │
        │  App ──────► Cache                  │
        │              "user:123" NOT found   │
        │                                     │
        │  App ──────────────────► Database   │
        │              query: SELECT * FROM   │
        │              users WHERE id=123     │
        │  App ◄──────────────────── result   │
        │                                     │
        │  App ──────► Cache                  │
        │              SET "user:123" = result │
        │              TTL = 300 seconds       │
        │                                     │
        │  App returns data to client         │
        │  (total time: ~15ms for first req)  │
        └─────────────────────────────────────┘
```

#### The Write Path

On a write (user updates their profile), the cache-aside pattern has two sub-approaches:

1. **Invalidate the cache entry**: delete the key from cache. Next read will miss and reload fresh data from DB.
2. **Update the cache entry**: write new data to both DB and cache simultaneously.

Invalidation is simpler and safer. Update is faster but introduces a race condition (more on this in Section 3).

#### Real Code: Cache-Aside in Python

```python
import redis
import json

r = redis.Redis(host='localhost', port=6379)

def get_user(user_id: int) -> dict:
    cache_key = f"user:{user_id}"

    # Step 1: Try cache first
    cached = r.get(cache_key)
    if cached is not None:
        return json.loads(cached)          # Cache HIT — fast path

    # Step 2: Cache miss — query database
    user = db.query("SELECT * FROM users WHERE id = %s", user_id)

    if user is None:
        return None

    # Step 3: Populate cache for next time
    r.setex(
        name=cache_key,
        time=300,              # TTL: 5 minutes
        value=json.dumps(user)
    )

    return user                            # Slower first time, fast after


def update_user(user_id: int, new_data: dict):
    # Write to database (authoritative store)
    db.execute(
        "UPDATE users SET name=%s, email=%s WHERE id=%s",
        new_data['name'], new_data['email'], user_id
    )

    # Invalidate cache so next read gets fresh data
    r.delete(f"user:{user_id}")
```

#### Pros and Cons of Cache-Aside

**Pros:**
- You only cache what is actually requested — no wasted memory on data nobody reads.
- If the cache fails completely (Redis goes down), the application still works — it just falls through to the database on every request. This is called **graceful degradation**.
- Works with any database, any language, any framework.

**Cons:**
- The first request for any key is always slow (the **cold start problem**). After a deploy or cache flush, every user experiences a slow first load.
- **Stale data window**: if user updates their profile, the cache still holds the old version until the TTL expires. If TTL is 5 minutes, users can see 5-minute-old data.
- The application code is more complex because it has to manage cache reads and writes explicitly.

---

### Strategy 2: Read-Through — Cache as Middleware

In **read-through** caching, the cache sits between the application and the database. The application talks only to the cache. When the cache has the data, it returns it. When the cache misses, the cache itself queries the database, stores the result, and then returns it to the application. The application never directly touches the database for reads.

```
         Application
              │
              │ read("user:123")
              ▼
    ┌─────────────────────┐
    │      Cache Layer     │
    │  (Redis, Memcached) │
    │                     │
    │  HIT: return data   │
    │                     │
    │  MISS:              │
    │    ┌──────────────┐ │
    │    │   Database   │ │
    │    │  (Postgres)  │ │
    │    └──────────────┘ │
    │    store + return   │
    └─────────────────────┘
```

The key difference from cache-aside: **the application does not write to the cache on a miss**. The cache layer handles that internally. The application just calls `cache.get(key)` and always gets an answer — either fast from memory or slow from the database.

**Where this pattern appears in practice:**
- Hibernate's second-level cache (Java ORM — the ORM manages cache reads transparently)
- Some CDN configurations where the CDN fetches from origin on miss
- Database connection proxies like ProxySQL

**Pros:**
- Simpler application code — no cache management logic scattered across your codebase.
- Consistent miss-handling logic in one place.

**Cons:**
- The first read for any key is always slow (same cold start problem as cache-aside).
- The cache layer must understand your data model well enough to fetch from the database on miss — this tightly couples the cache to your storage layer.
- Harder to implement correctly for complex queries.

---

### Strategy 3: Write-Through — Always Write to Cache AND Database

In **write-through** caching, every write goes to both the cache and the database **synchronously** and in the same operation. The write is not considered complete until both stores confirm.

```
Application writes: update user 123's name

Application
    │
    │  write("user:123", new_data)
    ▼
┌──────────────────────────────────────────┐
│              Cache Layer                  │
│                                           │
│  1. Write to cache: SET user:123 = data  │
│  2. Write to database: UPDATE users...   │
│  3. Both confirmed ──► return success    │
└──────────────────────────────────────────┘

Result: cache and database are always in sync
        reads after this write always hit cache
        cache never contains stale data for written keys
```

Because every write goes to the cache, reads almost always hit. You essentially never have a cold start for written data — the data lands in cache at write time.

**Pros:**
- Cache always contains the latest version of written data.
- Read latency is always low for any key that has been written — no misses.
- Simple consistency model — cache and database agree immediately.

**Cons:**
- **Write latency increases**. You are now doing two writes (cache + database) synchronously per user write. If the database is slow, the write is slow.
- **Wasted cache space**: you cache every piece of data you write, even data that is never read again. Imagine a batch import of 10 million historical records — they fill your cache, evicting hot data that was actually being read.
- Not suitable when write volume is very high and most written data is not re-read.

**When to use:** systems with moderate write volume where the same records are both frequently written and frequently read — for example, a small social network where user profiles are updated and then immediately re-read by that user's friends.

---

### Strategy 4: Write-Behind (Write-Back) — Async Database Write

**Write-behind** is the most aggressive caching strategy. On a write, the application writes to the cache immediately and returns success to the caller. The cache then writes to the database **asynchronously** in the background, potentially after batching several writes together.

```
Application writes: update user 123's name

Application
    │
    │  write("user:123", new_data)
    ▼
┌─────────────────────────────────────────┐
│             Cache Layer                  │
│                                          │
│  1. Write to cache: SET user:123 = data │
│  2. Return success immediately           │
│     (total write time: ~0.3ms)          │
│                                          │
│  [Background, asynchronously:]          │
│  3. Flush dirty keys to database        │
│     (every 5 seconds, or every 100 ops) │
└─────────────────────────────────────────┘
                    │
                    │ async, batched writes
                    ▼
              ┌──────────┐
              │ Database │
              └──────────┘
```

**Pros:**
- Write latency is cache speed — sub-millisecond. The user perceives the write as instant.
- **Batching**: instead of one database write per user action, you can flush 100 writes in a single batched SQL statement. This dramatically reduces database load on write-heavy systems.
- Great for scenarios like incrementing counters (page views, likes) where you do not need each increment to hit the database immediately.

**Cons:**
- **Data loss risk**: if the cache node crashes before flushing, you lose all unflushed writes. There is a window — however small — where data exists only in the cache and not in the database.
- Complex failure handling: what if the async database write fails? You need retry logic, dead-letter queues, and monitoring.
- Harder to reason about consistency — the database is always slightly behind the cache.

**A real incident pattern:** A team runs a write-behind cache for a gaming leaderboard. A Redis node crashes due to a hardware failure. The node had 30 minutes of score updates buffered that had not yet been flushed to MySQL. Those updates are gone. Players who earned points in the last 30 minutes see their scores rolled back. Support tickets flood in.

**When to use:** Analytics counters (page views, event counts), rate limiters, systems where a small data loss window is acceptable. **Never use for financial data, user account changes, or anything where losing even one write has serious consequences.**

---

### Strategy Comparison Table

| Strategy | Read latency | Write latency | Consistency | Code complexity | Data loss risk |
|---|---|---|---|---|---|
| Cache-aside | Fast (after warmup) | Fast (DB only) | Eventual | Medium | None |
| Read-through | Fast (after warmup) | Fast (DB only) | Eventual | Low | None |
| Write-through | Always fast | Slower (both) | Strong | Low | None |
| Write-behind | Always fast | Very fast | Eventual | High | Yes |

---

## 3. Cache Invalidation: The Hardest Problem in Computer Science

Phil Karlton's quote is not hyperbole. Cache invalidation is genuinely hard. Here is why.

You have a user record. It is cached on six different servers — each server has an in-process memory cache. It is also cached in your Redis cluster. It might be cached in your CDN if you returned it in an HTTP response with a cache-control header. Now the user updates their email address.

How do you make sure every copy of that stale record gets removed or updated? You have **seven places** that might hold the old version. Miss even one and you have an inconsistency.

There are three main approaches to solving this, each with different tradeoffs.

---

### Invalidation Strategy 1: TTL-Based Expiry

The simplest approach: every cache entry expires after a fixed amount of time (its **Time To Live**, or TTL). When the entry expires, the next read fetches fresh data from the database.

```
User record cached at T=0 with TTL=300s

T=0    ─── cache SET, data is fresh ───────────────────────────────┐
                                                                   │
T=60   ─── user updates their email in database                   │
                                                                   │
T=60   ─── cache still holds OLD email                            │
to     ─── all reads served stale                                  │
T=300                                                              │
                                                                   │
T=300  ─── cache EXPIRES ──────────────────────────────────────────┘
                                                                    │
T=300+ ─── next read MISSES, fetches fresh data from DB ───────────►
           cache stores new email
           all subsequent reads are correct
```

**The stale data window is exactly equal to the TTL.** If TTL is 5 minutes, users can see 5-minute-old data. If TTL is 1 hour, users can see 1-hour-old data.

**Choosing the right TTL** is a product decision disguised as a technical decision:
- How long can users tolerate seeing stale data?
- For a user's own profile: probably 0 seconds (they expect to see changes immediately)
- For a public leaderboard: probably 60 seconds is fine
- For a rarely-changing product catalog: probably 1 hour is fine
- For aggregate analytics: probably 24 hours is fine

TTL-based invalidation is the right default when:
- The data changes infrequently
- A short window of staleness is acceptable
- You want the simplest possible implementation

---

### Invalidation Strategy 2: Event-Based Invalidation

Instead of waiting for the TTL to expire, you **proactively invalidate** the cache entry the moment the data changes in the database.

```
User updates their email

    Application
         │
         │  UPDATE users SET email=... WHERE id=123
         ▼
    ┌──────────┐
    │ Database │ ──── write succeeds
    └──────────┘
         │
         │  publish event: { type: "user.updated", user_id: 123 }
         ▼
    ┌──────────────────┐
    │  Message Queue   │
    │  (Kafka/SQS/etc) │
    └──────────────────┘
         │
         │  event delivered to all subscribers
         ▼
    ┌──────────────────┐
    │  Cache Service   │
    │  (or all app     │
    │   servers)       │
    │                  │
    │  DEL user:123    │  ◄─── cache entry gone immediately
    └──────────────────┘

Next read: cache miss → fresh data from DB → cache re-populated
Stale window: milliseconds (time for event to propagate)
```

**Pros:** The stale data window collapses from minutes to milliseconds. Users see fresh data almost immediately after a write.

**Cons:**
- More moving parts. You now need a message queue or event bus.
- **What if event delivery fails?** If the cache invalidation event is dropped, the cache holds stale data indefinitely. You need the cache to still have a TTL as a safety net.
- Ordering matters: if events arrive out of order, you might invalidate a cache entry that was just re-populated with fresh data.

The practical recommendation: **combine event-based invalidation with a long TTL**. The event handles the common case (instant invalidation). The TTL handles the failure case (eventual consistency even if events are lost).

---

### Invalidation Strategy 3: Version-Based Cache Keys

Instead of trying to invalidate an existing key, you **change the key itself** when the data changes.

```
User 123 has version 3 in the database
Cache key: "user:123:v3"

User updates email → database version becomes 4

New cache key: "user:123:v4"

Next read:
  Application looks up "user:123:v4"  ← uses current version
  Cache MISS (new key has never been set)
  DB query → fresh data
  Cache SET "user:123:v4" = fresh data

Old key:
  "user:123:v3" still exists in cache
  Nobody reads it anymore
  Expires naturally via TTL
  Cleaned up by cache eviction
```

This approach means you never have to explicitly delete an old entry. You simply stop reading it. The old entry ages out naturally.

**Pros:**
- No race conditions. You are never in a state where you deleted the old key but the new data is not yet cached.
- Simple to reason about — each version is a completely independent cache entry.

**Cons:**
- The database must store and increment a version number for each record.
- Old cache keys accumulate. If you update a record 50 times, you have 50 stale keys in the cache (all with TTLs, all eventually cleaned up, but still using memory in the meantime).
- You need to know the current version number when constructing cache keys, which requires either fetching the version from the database (defeating part of the purpose) or maintaining a separate version store.

---

## 4. Cache Stampede and the Thundering Herd Problem

Cache stampede is one of the most dramatic failure modes in distributed systems. It is the kind of problem that takes down production systems at 2am.

### The Scenario

Your system has a popular cached value — let's say the front page of a news site showing top stories. This key is cached with a 5-minute TTL. At peak traffic, 10,000 requests per second are hitting this key. All 10,000 are served from cache. The database is barely touched.

Then the TTL expires.

In the next millisecond, all 10,000 requests per second simultaneously find a cache miss. Every single one of them independently queries the database. The database, which was handling 50 queries per second, is suddenly handed 10,000 simultaneous queries. It falls over.

```
Normal operation (cache warm)
─────────────────────────────────────────────────────────────
10,000 req/s ──► Cache HIT ──► 10,000 responses
                               0 DB queries

Cache TTL expires at T=300
─────────────────────────────────────────────────────────────
T=300.000  10,000 req/s ──► Cache MISS ──► 10,000 DB queries
T=300.001                                   DATABASE FALLS OVER
T=300.050  Cache refilled by ONE query (others crashed DB)
T=300.100  Cache warm again, but DB is in failure state
T=310.000  DB recovers
           Normal operation resumes

                 ▲ DB load
                 │
    10,000/s ────│          ████
                 │          ████
                 │          ████
       50/s  ────│──────────     ───────────────
                 │
                 └────────────────────────────► time
                          T=300
                          (TTL expiry)
```

The problem is a **thundering herd** — a massive number of processes all simultaneously discover a resource is unavailable and all simultaneously try to rebuild it.

There are three solutions, in increasing order of sophistication.

---

### Solution 1: TTL Jitter

The simplest fix: add randomness to the TTL so that not all copies of a key expire at exactly the same moment.

```python
import random

BASE_TTL = 300  # 5 minutes

def cache_set_with_jitter(key: str, value: str, base_ttl: int = BASE_TTL):
    # Add random jitter: 0 to 20% of base TTL
    jitter = random.randint(0, base_ttl // 5)   # 0 to 60 seconds
    actual_ttl = base_ttl + jitter

    r.setex(key, actual_ttl, value)

# Result: cache entries expire between 300 and 360 seconds
# Instead of 10,000 simultaneous expiries, you get:
#   ~1,666 expiries at each 10-second interval from T=300 to T=360
# Each mini-wave of 1,666 requests is manageable for the database
```

This is effective for the most common case and requires almost no code. The downside: you still get mini-stampedes at each jitter window. For extremely high traffic, you need stronger medicine.

---

### Solution 2: Probabilistic Early Expiration (XFetch Algorithm)

This approach prevents stampedes by having some requests **proactively refresh the cache before it expires**.

The core idea: as a cache entry gets closer to its expiration time, the probability that any given request will decide to refresh it early increases. When the TTL finally hits zero, the cache has already been refreshed and the stampede never happens.

The algorithm uses this formula to decide whether to early-recompute:

```
recompute = (current_time - ttl * beta * log(random())) > expiry_time
```

In plain English: generate a random number between 0 and 1. Take its log (which is always negative). Multiply by TTL and beta (a tuning constant, typically 1.0). If the result pushes the current time past the expiry time, recompute now.

```python
import math
import random
import time

def get_with_xfetch(key: str, ttl: int, fetch_fn, beta: float = 1.0):
    """
    fetch_fn: function that retrieves fresh data from the database
    beta: higher value = more aggressive early recomputation
    """
    cached = r.get(key)
    expiry = r.expiretime(key)  # Unix timestamp when key expires

    if cached is not None:
        # Decide whether to early-recompute
        now = time.time()
        # As (expiry - now) approaches 0, this check triggers more often
        should_recompute = (now - ttl * beta * math.log(random.random())) > expiry

        if not should_recompute:
            return cached  # Use cached value, no recomputation needed

    # Either cache miss or probabilistic early recompute
    fresh_data = fetch_fn()
    r.setex(key, ttl, fresh_data)
    return fresh_data
```

**Why this works:** With standard TTL, zero requests refresh the cache until it expires, then all of them do simultaneously. With XFetch, some small percentage of requests near the expiry time start refreshing early. By the time the TTL hits zero, the cache has already been refreshed, and the stampede never materializes.

---

### Solution 3: Request Coalescing (Promise Cache / Mutex Locking)

This is the most robust solution for very high-traffic keys. The idea: **only one request per cache miss is allowed to query the database**. All other requests that arrive during the same miss wait for the first request to finish.

```
10,000 concurrent requests for "top-stories" key
TTL has just expired

Request 1:   Cache MISS
             ┌─── acquire distributed lock on "top-stories:lock" ──► SUCCESS
             │    query database
             └─── write result to cache
                  release lock
                  return result to caller

Requests 2-10,000:
             Cache MISS
             ┌─── acquire distributed lock on "top-stories:lock" ──► LOCKED
             │    wait (poll or sleep)
             │    ...
             │    lock released
             └─── re-check cache ──► HIT (Request 1 populated it)
                  return cached result

Database sees: 1 query (not 10,000)
```

```python
import time

LOCK_TTL = 5       # seconds to hold the lock
WAIT_INTERVAL = 0.05   # 50ms polling interval

def get_with_coalescing(key: str, fetch_fn, ttl: int = 300):
    # Try fast path first
    cached = r.get(key)
    if cached is not None:
        return cached

    lock_key = f"{key}:lock"

    # Try to acquire the lock (NX = only set if not exists)
    acquired = r.set(lock_key, "1", nx=True, ex=LOCK_TTL)

    if acquired:
        # We are the designated loader
        try:
            fresh_data = fetch_fn()     # One DB query
            r.setex(key, ttl, fresh_data)
            return fresh_data
        finally:
            r.delete(lock_key)          # Always release the lock
    else:
        # We are a waiter — poll until lock is gone or cache is populated
        deadline = time.time() + LOCK_TTL
        while time.time() < deadline:
            time.sleep(WAIT_INTERVAL)
            cached = r.get(key)
            if cached is not None:
                return cached           # Cache populated by loader
        # Lock expired and still no data — fallback to direct DB query
        return fetch_fn()
```

**Result:** No matter how many concurrent requests hit a cache miss, exactly one database query fires. All other requests wait and are served from cache once the first query completes.

---

## 5. Multi-Level Caching

In large-scale systems, a single cache layer is often not enough. Real systems use **multiple caching layers**, each optimized for a different tradeoff between speed, consistency, and geographic proximity to the user.

```
User request arrives

    User's Browser
         │
         │  (first: check browser cache)
         ▼
    ┌──────────┐
    │   CDN    │  Layer 3 — closest to user geographically
    │(Cloudflare│  Caches static assets, public read-heavy data
    │ Fastly)  │  Latency: ~10ms  Capacity: petabytes
    └──────────┘
         │ miss
         ▼
    ┌──────────────────┐
    │  Application     │  Layer 1 — in-process memory
    │  Server          │  Caches: config, feature flags, hot reference data
    │                  │  Latency: ~0.01ms  Capacity: MBs per server
    │  [in-memory dict]│  Risk: different servers have different values
    └──────────────────┘
         │ miss
         ▼
    ┌──────────────────┐
    │  Redis Cluster   │  Layer 2 — shared distributed cache
    │                  │  Caches: user sessions, API responses, computed data
    │                  │  Latency: ~0.3ms  Capacity: GBs
    │                  │  Consistent across all app servers
    └──────────────────┘
         │ miss
         ▼
    ┌──────────────────┐
    │   PostgreSQL     │  Source of truth
    │   (or any DB)    │  Latency: ~10-50ms  Capacity: TBs
    └──────────────────┘
```

### Layer 1: In-Process Memory Cache

This is a simple dictionary or hashmap living inside the application's own process. Reading it requires zero network I/O — it is just a pointer dereference. Latency is essentially zero (microseconds).

**The critical risk:** if you have 20 application servers, each has its own in-process cache. Server A might have a cached value that server B does not have. Or worse, server A has a stale version that server B has already invalidated. Users routed to different servers can see different data.

**Use in-process caches only for:**
- Immutable or rarely-changing data: product catalog, configuration values, feature flags
- Data where eventual consistency across servers is acceptable

**Never use in-process caches for:**
- User-specific data that changes (you cannot guarantee which server handles the next request)
- Data where all servers must agree on the same value (like a rate limit count)

### Layer 2: Distributed Cache (Redis)

Redis is shared across all application servers. A write from server A is visible to a read from server B. This gives you consistency at the cost of a network round-trip (typically 0.2-0.5ms in the same data center).

### Layer 3: CDN

CDNs (Content Delivery Networks like Cloudflare, Fastly, or AWS CloudFront) are geographically distributed caches. They cache content at points of presence (PoPs) around the world, so a user in Tokyo gets served from a PoP in Tokyo rather than your data center in Virginia.

CDNs are primarily used for:
- Static assets: images, CSS, JavaScript files
- Public, read-heavy API responses (e.g., trending content, public leaderboards)

### The Invalidation Complexity Grows With Levels

With one cache layer, invalidation is: delete the key. With three layers, invalidation requires:
1. Delete from Redis
2. Purge from CDN (most CDNs have an API for this)
3. Wait for in-process caches to expire (you usually cannot actively flush them)

Bugs in multi-level invalidation are notoriously hard to reproduce because they depend on which layer a particular server hit at a particular moment.

---

## 6. What NOT to Cache (Anti-Patterns)

Knowing what to cache is half the skill. The other half is knowing what to leave alone. The following patterns waste memory, increase complexity, and produce bugs without meaningfully improving performance.

---

### Anti-Pattern 1: Rapidly Changing Data

Do not cache data that changes faster than any TTL you would set. A user's current GPS location (in a ride-sharing app) changes every second. If you cache it for even 10 seconds, every read during those 10 seconds returns the wrong location. You have added complexity and still have wrong data.

**Rule:** If the update frequency of the data exceeds the usefulness of any caching window, do not cache it.

---

### Anti-Pattern 2: Financial Data Requiring Strong Consistency

A user's bank balance must never be stale. If a user has $100, transfers $100 to a friend, and your system serves a cached $100 balance to a merchant authorization request in the next 500 milliseconds, you have allowed an overdraft.

Stale financial data is not a performance inconvenience — it is a correctness failure with legal and financial consequences.

**Rule:** Never cache data where reading a stale value could result in financial loss, security vulnerability, or compliance violation. Always read this data from the primary database with strong consistency guarantees.

---

### Anti-Pattern 3: Personalized Data at High Cardinality

"User X's personalized recommendations" might seem like a great caching candidate — computing recommendations is expensive. But if you have 100 million users and each user has a different recommendation set, caching all of them requires 100 million cache entries.

At, say, 1KB per entry, that is 100GB of cache just for recommendations. Your hit rate collapses: you cache every user's recommendations, but each user only reads their own recommendations a few times per session.

**Rule:** Before caching anything per-user, calculate: (number of users) × (bytes per entry) = total cache memory required. If that exceeds your budget or your expected hit rate is low (because users do not re-request the same data repeatedly), do not cache it.

---

### Anti-Pattern 4: Small, Fast Database Queries

Some queries are already fast. A primary key lookup in PostgreSQL with proper indexing might return in 1-2ms. Caching this adds complexity (cache management code, invalidation logic, failure modes) in exchange for saving 1ms. That trade is usually not worth it.

**Rule:** Measure first. If the uncached path takes fewer than 5ms and is not a bottleneck in your request path, caching is probably not the right tool.

---

### Anti-Pattern 5: Caching Without Measurement

The most common caching mistake: deciding what to cache based on intuition rather than data.

Engineers routinely assume the database is the bottleneck. Sometimes the database is fine and the bottleneck is a downstream API call, a slow template render, or network latency. Caching the database does nothing for those bottlenecks.

**Rule:** Use profiling tools and metrics before adding caching. Add caching only where you have measured that (a) the database is the bottleneck and (b) the data being cached is accessed repeatedly in a pattern that would produce a useful hit rate.

---

## 7. Cache Sizing and Eviction Policies

Getting the right cache size is more important than most engineers realize. Too small and your hit rate collapses. Too large and you are paying for memory that provides no additional benefit.

### How to Size a Cache

Start with the **hot data set** — the data that is actually being read frequently.

Most systems follow a **power law distribution**: 80% of requests touch 20% of the data. That 20% is your hot set. Cache the hot set and let the long tail miss.

```
Request frequency by data item (power law)

    Frequency
    │
    │████
    │████████
    │████████████
    │████████████████████
    │████████████████████████████████
    │████████████████████████████████████████
    └─────────────────────────────────────────► Data items

    ◄──── 20% of items ────►◄─── 80% of items ──────────────────────►
    These 20% of items account          These items are rarely read.
    for 80% of your traffic.            Let them miss. Do not cache them.
    Cache these.
```

**Sizing procedure:**
1. Identify your hot set size (query your access logs for the top N% of keys)
2. Start by allocating **20% of your hot data set size** as cache capacity
3. Deploy and monitor your hit rate
4. If hit rate is below 80%, either add capacity or investigate whether you are caching the right keys
5. Keep adding capacity until hit rate improvements become marginal (diminishing returns)

For most systems, caching 20-30% of the total data size achieves 90%+ hit rates because of the power law distribution.

### Eviction Policies

When a cache is full and a new entry needs to be written, the cache must evict (delete) an existing entry to make room. The eviction policy determines which entry gets deleted.

| Policy | How it works | Best for |
|---|---|---|
| **LRU** (Least Recently Used) | Evict the entry that has not been accessed for the longest time | General purpose — most workloads |
| **LFU** (Least Frequently Used) | Evict the entry accessed the fewest total times | When access patterns are stable and long-lived |
| **Random** | Evict any random entry | Surprisingly effective, very low overhead |
| **No eviction** | Reject new writes when full, return error | Rate limiters and counters where you cannot afford to lose any entry |
| **Volatile-LRU** | Apply LRU only to entries that have a TTL set | When you want to protect entries with no TTL from eviction |

**LRU is the right default for most use cases.** The intuition is simple: if you have not accessed something recently, you probably will not access it soon. Evict it first.

**LFU beats LRU** when your hot set is stable over long periods — the same small set of keys are accessed millions of times while the long tail is accessed once and never again. LFU learns this and aggressively protects the hot keys.

**Random eviction** sounds wrong but often performs within 10-15% of LRU with much simpler implementation. Redis uses a variant of random eviction (random sample of entries, evict the LRU within that sample) which is nearly as good as true LRU at a fraction of the memory overhead.

---

## 8. Distributed Cache Failure Scenarios

Caches fail. The question is not whether your cache will fail — it is whether your system degrades gracefully when it does.

---

### Failure Mode 1: Single Cache Node Failure

If your Redis is a single node (not a cluster) and that node fails, every cache read misses immediately. All traffic falls through to the database.

```
Normal: 10,000 req/s, 95% cache hit rate
         50 queries/s reach the database

Cache node fails:
         10,000 queries/s reach the database
         Database handles ~500 queries/s before degrading
         System fails
```

**Fix 1: Circuit breaker on the database.** When the database detects that it is receiving more requests than it can handle, it fast-fails new incoming requests rather than queuing them. This prevents cascading failure — a slow overloaded database makes everything worse than a fast-failing one.

**Fix 2: Graceful degradation.** Design your application to return a degraded response (e.g., showing cached-for-longer data, simplified results, or a "try again in a moment" response) rather than hard-failing. Users tolerate degraded responses far better than error pages.

**Fix 3: Use Redis Sentinel or Redis Cluster.** Sentinel provides automatic failover for a primary-replica Redis setup. Cluster provides sharding and automatic failover. Neither prevents the initial failure, but they minimize downtime from seconds to milliseconds.

---

### Failure Mode 2: Cache Cluster Split-Brain

In a distributed Redis cluster, a network partition can cause two nodes to both believe they are the primary responsible for the same key. Both accept writes. When the partition heals, they disagree on the correct value.

```
Network partition at T=100

Before partition:       Node A (primary) ──── Node B (replica)

After partition:        Node A (primary)      Node B (now also acts as primary)

App server 1 writes: user:123 = "Alice" to Node A
App server 2 writes: user:123 = "Bob"   to Node B

Partition heals at T=200:
         Node A has "Alice"
         Node B has "Bob"
         Which is correct?
```

This scenario requires the **Redlock algorithm** — a distributed locking protocol using multiple independent Redis nodes to achieve a consensus lock. Redlock is controversial because it does not provide perfect safety guarantees under all network conditions (Martin Kleppmann's critique of Redlock is worth reading). For most applications, the simplest fix is: **do not use caches for data where split-brain would be catastrophic**. Use the database (with proper transaction isolation) for that data.

---

### Failure Mode 3: Cache Poisoning

Cache poisoning happens when an attacker — or a bug — causes incorrect data to be stored in the cache, which then gets served to legitimate users.

**Example:** An attacker sends a request with a crafted URL parameter that causes your cache key to collide with another user's cached data. Now user A's cached data is served to user B.

**Example:** A bug in your serialization code writes a corrupted object to the cache. Every subsequent read returns the corrupted object without hitting the database.

**Fix:**
- Never trust cache data for **security decisions**. Always re-validate permissions and authentication from the authoritative source, not the cache.
- Validate data structure on deserialization. If the cached object does not match the expected schema, treat it as a miss and re-fetch from the database.
- Use namespaced, unguessable cache keys. Never construct cache keys from user-supplied input without sanitization.

---

### Failure Mode 4: The Empty Cache Cold Start

After a cache flush, a deployment, or a fresh environment setup, the cache is empty. Every request misses. All traffic hits the database simultaneously. This is a stampede caused by a known event rather than TTL expiry — and it is often more severe because the entire cache is cold, not just one key.

**Fix 1: Cache warming.** Before switching traffic to a new deployment, pre-populate the cache with the most popular keys:

```python
def warm_cache():
    """
    Run before switching traffic to new deployment.
    Fetch the top-N most accessed keys from DB and populate cache.
    """
    top_user_ids = db.query("""
        SELECT user_id, COUNT(*) as access_count
        FROM access_logs
        WHERE ts > NOW() - INTERVAL '1 hour'
        GROUP BY user_id
        ORDER BY access_count DESC
        LIMIT 10000
    """)

    for user_id in top_user_ids:
        user = db.query("SELECT * FROM users WHERE id = %s", user_id)
        cache.set(f"user:{user_id}", user, ttl=300)

    print(f"Warmed {len(top_user_ids)} cache entries")
```

**Fix 2: Gradual traffic ramp.** Instead of switching all traffic at once to the new deployment, increase traffic slowly — 1%, 5%, 10%, 25%, 50%, 100%. The cache warms up incrementally and the database never sees a full cold-start spike.

**Fix 3: Persistent cache.** Redis supports optional persistence (RDB snapshots and AOF logs). A cache that survives restarts is pre-warmed on startup rather than cold.

---

## Summary: Caching Decision Framework

When evaluating whether and how to cache something, work through these questions in order:

```
1. Is the data access pattern repeated?
   (same data read multiple times)
   NO  ──► Don't cache. No hit rate benefit.
   YES ──► continue

2. Can the data tolerate being stale?
   NO  ──► Don't cache, or use very short TTL with event invalidation.
   YES ──► continue

3. What is the read/write ratio?
   Mostly reads  ──► Cache-aside or read-through
   Mixed         ──► Write-through if consistency matters
   Mostly writes ──► Write-behind (accept data loss risk) or don't cache

4. How many distinct keys are there?
   Small set (millions)    ──► Cache directly, good hit rate
   Huge set (billions)     ──► Only cache hottest subset, expect high miss rate

5. What happens when the cache fails?
   System survives  ──► Cache is safe to use
   System crashes   ──► Fix the architecture. Never make cache load-bearing.
```

The last point deserves emphasis: **your system must be able to function — slowly, under degraded performance, but correctly — without the cache.** The moment your system cannot survive a cache failure, you have made the cache a single point of failure as critical as your database, but with far weaker durability guarantees.

---

*This section is Part J of Chapter 28. Continue to Part K for Indexing Strategies and Query Optimization.*
# Chapter 28 — Part K: Databases — Choosing, Using, and Evolving Data Stores

---

## Overview

Chapter 27 gave you a deep toolkit: distributed consistency models, Hybrid Logical Clocks, CRDTs, and Chaos Engineering. That toolkit is useless if you cannot connect it to the actual databases you will use on the job and discuss in interviews. This chapter makes that connection explicit. It then extends your knowledge to three data stores that come up constantly in L6 interviews: Elasticsearch for search, Kafka as a durable log in the data store landscape, and vector databases for the AI era. Read every section carefully. The goal is that after this chapter, hearing the words "Cassandra" or "Elasticsearch" in an interview instantly triggers the right mental model, the right trade-offs, and the right failure modes.

---

## 1. Bridging Chapter 27 to Real Database Choices

If Chapter 27 was theory, this section is translation. Every concept you learned maps to a real system making a real engineering decision. Most candidates can define "eventual consistency." Very few can say, "Cassandra at CL=ONE is eventually consistent, which means a like counter can show stale values, which is acceptable for a social feed but would be a disaster for a bank balance." That specificity is what L6 looks like.

### 1.1 The Translation Table

The table below is your cheat sheet. Study every row. The "What breaks" column is what your interviewer is actually testing when they ask about consistency.

| Chapter 27 Concept | Real Database(s) | How It Is Used | What Breaks If You Get It Wrong |
|---|---|---|---|
| Linearizability | Spanner, CockroachDB (SERIALIZABLE) | Global transactions across regions | User sees account balance before their transfer commits; double-spend becomes possible |
| Sequential consistency | ZooKeeper, etcd | Leader election, distributed locks, config storage | Two services elect themselves as leader simultaneously; split-brain |
| Causal consistency | MongoDB causal sessions, DynamoDB (within a transaction) | Read-your-writes for user-facing writes | User edits profile, refreshes page, sees old profile; support ticket filed |
| Eventual consistency | Cassandra (CL=ONE), DynamoDB (default reads) | Social feeds, analytics counters, caches | Like count shows 999 on one replica, 1000 on another; acceptable lag for feeds |
| HLC (Hybrid Logical Clocks) | CockroachDB, TiDB | Transaction ordering across nodes | Two concurrent writes get wrong timestamp order; MVCC returns the wrong version |
| LWW (Last-Write-Wins) | Cassandra conflict resolution, DynamoDB | Concurrent writes to the same key resolved by timestamp | "Edit profile" from two browsers; one silently overwrites the other |
| G-Counter CRDT | Redis INCRBY (approximated), Riak counters | Distributed like/view counts | Traditional counter loses increments when two nodes accept concurrent writes |
| OR-Set CRDT | Shopping cart in Dynamo-style systems | Concurrent add/remove from multiple devices | "Add to cart" on two devices simultaneously; one addition silently lost |
| Read-your-writes | PostgreSQL (primary reads), session stickiness | User-facing write followed by immediate read | User creates post, page refresh shows empty feed; user thinks post failed |
| Monotonic reads | Sticky session routing in Cassandra | Sequential reads from the same client | User refreshes page, sees older version of their own post than they saw a second ago |

---

### 1.2 Deep Dive: HLC (Hybrid Logical Clocks) in CockroachDB and TiDB

Before getting to LWW in Cassandra, it is worth pausing on the HLC row in the table because it explains why Cassandra's LWW is fundamentally unsafe with physical clocks, and why CockroachDB is not.

A **Hybrid Logical Clock (HLC)** is a timestamp that combines a physical clock reading (wall clock milliseconds) with a logical counter. The physical component keeps the HLC close to real time. The logical component breaks ties when two events happen at the same physical millisecond, and it advances monotonically even if the physical clock stalls or moves slightly backward.

**Why CockroachDB uses HLC instead of physical clocks.** CockroachDB implements multi-version concurrency control (MVCC): every write creates a new version of a row tagged with the transaction's timestamp. Reads look at all versions up to a certain timestamp and return the correct one. This is the same idea as a Git commit history — you can check out any version.

For MVCC to work correctly, the timestamp assigned to a write must reflect its true causal order. If write A causally precedes write B (A happened before B), then A must have a lower timestamp. With pure physical clocks, this is not guaranteed: two nodes whose clocks drift by even 10ms can assign timestamps in the wrong order.

```
Node 1 clock: 10:00:00.000  -> assigns timestamp 1000ms to write A
Node 2 clock: 09:59:59.995  -> assigns timestamp  995ms to write B

B happened after A in real time, but B got a lower timestamp.
MVCC thinks B is older. Reads that should see B now see A instead.
Wrong data returned.
```

HLC prevents this. When Node 2 receives a message from Node 1 (which contains Node 1's HLC timestamp of 1000ms), Node 2 advances its own HLC to max(its own clock, received timestamp) + 1. Node 2 can never assign a timestamp lower than something it has already seen. The causal order is preserved.

CockroachDB goes further with "uncertainty intervals." When a transaction reads a value, if that value's timestamp falls within a small window of uncertainty (bounded by the maximum possible clock skew, typically 500ms), CockroachDB re-reads at a higher timestamp to be safe. This is the "clock uncertainty restart" you see in CockroachDB transaction traces. It adds a small latency penalty but guarantees linearizability.

**What breaks without HLC.** Two concurrent writes to the same key land on different nodes with physical timestamps in the wrong order. MVCC returns the wrong version to a reader. A user who transferred money and then checked their balance could see the pre-transfer balance, even though both operations committed successfully. This is a linearizability violation — the exact failure mode described in the table.

---

### 1.3 Deep Dive: OR-Set CRDT in Shopping Carts (Bonus Row)

The **OR-Set (Observed-Remove Set)** is the CRDT that powers one of the most famous examples in distributed systems: the Amazon/Dynamo shopping cart. Understanding it concretely shows why CRDTs exist — and what the alternative (losing data silently) looks like.

**The problem with a naive set under network partition.** A user has a shopping cart. They add "headphones" on their laptop, then their phone goes offline. On the phone, they add "keyboard." When the phone reconnects, the two replicas need to merge. A naive approach: take the union of both sets. That gives {headphones, keyboard}. Fine so far.

Now the user removes "headphones" on the laptop while the phone is still offline. The laptop's state is {keyboard} (headphones removed). The phone's state is still {headphones, keyboard}. When the phone reconnects:

```
Laptop state: {keyboard}              (headphones was added and then removed)
Phone state:  {headphones, keyboard}  (phone was offline; never saw the remove)

Naive merge (union): {headphones, keyboard}   <- headphones is back!
Remove-wins merge:   {keyboard}               <- correct, but loses phone's keyboard if phone had removed it
```

Neither naive rule works cleanly.

**How OR-Set solves it.** OR-Set tags every add operation with a unique identifier (a "dot" — typically a node ID + logical counter). When you remove an element, you specifically remove all the dots you have observed for that element. If new adds arrive that you have not yet seen (from a concurrent, offline device), those dots survive the remove.

```
Laptop adds "headphones":    {(headphones, dot=A1)}
Phone adds "keyboard":       {(keyboard, dot=B1)}      <- offline

Laptop removes "headphones": removes dot A1 specifically
Laptop state now: {}

Phone reconnects. Its state: {(headphones, dot=A1), (keyboard, dot=B1)}

Merge: laptop says "remove A1". Phone still has A1 and B1.
       A1 is explicitly removed. B1 is not. B1 survives.

Result: {(keyboard, dot=B1)}  -> display: {keyboard}
```

The keyboard survives because its dot (B1) was never explicitly removed by anyone. The headphones are gone because their dot (A1) was explicitly removed by the laptop. This is the "observed-remove" in OR-Set: you only remove what you have observed, not what might be arriving from a concurrent operation.

**The trade-off.** OR-Set favors add-wins semantics for concurrent add/remove. If the laptop removes "headphones" at the exact same moment the phone adds "headphones" (from a different session, a new dot), the add wins. This is the correct behavior for a shopping cart — losing an item the user added is worse than having an extra item they need to manually remove. But for a "banned users" list or an access control list, add-wins semantics could be dangerous: a concurrent add and remove of a banned user leaves the user unbanned. Choose your CRDT semantics carefully based on what failure mode is more acceptable.

---

### 1.4 Deep Dive: LWW (Last-Write-Wins) in Cassandra

**Last-Write-Wins (LWW)** is Cassandra's default conflict resolution strategy. When two writes reach different replicas for the same row and the cluster needs to decide which value to keep, it picks the write with the higher timestamp. Simple, cheap, and fast — but it has a sharp edge.

**The concrete scenario.** Imagine you are building a shared travel planning document. Alice and Bob are both editing the destination city at the same time. Alice is in the US data center, Bob is in the EU data center.

```
T=1000ms  Alice writes: destination = "Paris"   → reaches US replica
T=1001ms  Bob writes:   destination = "Tokyo"   → reaches EU replica
```

Now the two replicas need to reconcile during the next read repair or hinted handoff. Cassandra compares the timestamps. Bob's write has a higher timestamp (1001 > 1000), so "Tokyo" wins. Alice's "Paris" is silently discarded. Alice refreshes the page and sees "Tokyo." She is confused. She edits it back to "Paris." This goes on forever.

Why is this the right trade-off for social feeds? For a social feed, the data is append-only (new posts), and concurrent edits to the same post are rare. If two like counts race, losing one increment is acceptable — the count is 999 instead of 1000. No one files a support ticket. LWW is fine.

Why is LWW wrong for financial data? If Alice and Bob both read a bank balance of $500 and each tries to transfer $400, LWW might keep Bob's transfer (the later timestamp) and silently discard Alice's. Neither transfer was rejected; one was simply lost. That is a correctness bug, not a performance trade-off. Financial systems require linearizable transactions, which is why they use PostgreSQL or Spanner, not Cassandra.

**The clock skew danger.** LWW assumes node clocks are synchronized. In practice, NTP keeps clocks within a few milliseconds. But if a node's clock drifts forward by 500ms, all its writes win every conflict for that window, even if they are actually older. CockroachDB addresses this with HLC (bounded uncertainty); Cassandra does not. This is a known limitation you must call out in interviews.

---

### 1.5 Deep Dive: G-Counter CRDT in Distributed Counters

Start with the problem. You have a popular YouTube video with 10 million views. You want to count views in real time. You spin up three Redis nodes behind a load balancer. Each node runs a simple `INCR video:123:views`.

**What breaks under network partition:**

```
Node A holds: 3,000,000 views
Node B holds: 4,000,000 views
Node C holds: 3,000,001 views   <- network partition; missed sync

User reads from Node A: 3,000,000
User reads from Node B: 4,000,000   <- inconsistent reads
```

When the partition heals, you need to merge these three numbers. What do you do? If you add them, you triple-count. If you take the max, you lose the increments from the other nodes. There is no clean answer with a simple integer counter.

**How G-Counter solves it.** A **G-Counter (Grow-only Counter)** gives each node its own slot in a vector. Node A only increments slot A; Node B only increments slot B. No node ever touches another node's slot.

```
State on Node A:  [A=1000, B=0,    C=0   ]
State on Node B:  [A=0,    B=2000, C=0   ]
State on Node C:  [A=0,    B=0,    C=500 ]
```

The total is always: sum all slots = 1000 + 2000 + 500 = 3500.

When two nodes merge their state, the rule is: for each slot, take the maximum value.

```
Merge(Node A, Node B):  [A=1000, B=2000, C=0]
Merge(above, Node C):   [A=1000, B=2000, C=500]  -> total: 3500
```

This is a **CRDT merge** — commutative, associative, and idempotent. No matter what order the merges happen in, you always get the same answer. No increments are lost.

**Where Redis INCRBY approximates this.** Redis does not natively implement G-Counter. But you can build it: maintain one Redis key per node (`views:video123:nodeA`, `views:video123:nodeB`), increment only your own key, and sum all keys at read time. This is the G-Counter pattern under a different name. Redis Cluster's lack of cross-slot transactions means this pattern is manual — you have to build it yourself.

---

### 1.6 Deep Dive: Read-Your-Writes Violation

This is the most common consistency bug in production web applications. It happens when an application writes to a primary database but reads from a replica.

**The exact failure sequence:**

```
Step 1: User submits "Update Profile" form
Step 2: Application writes new profile to PostgreSQL PRIMARY
        -> Write succeeds, 200 OK returned to user
Step 3: User's browser follows redirect to /profile
Step 4: Application reads profile from REPLICA
        (replica is 45 seconds behind due to replication lag)
Step 5: Replica does not yet have the new profile
Step 6: User sees their OLD profile
        -> User thinks the save failed
        -> User submits the form again
        -> Now you have duplicate writes
```

This is a **read-your-writes** violation: the user cannot read the value they just wrote. It feels like a bug even though the database did exactly what it was configured to do.

**Fix 1: Route the user's reads to the primary for a short window.**

After a write, set a cookie or session flag: `recently_wrote = true, expires_at = now + 30s`. Any read request that sees this flag goes to the primary, not the replica. After 30 seconds, the replica has caught up, and normal replica reads resume. This is the most common fix in large-scale web applications.

**Fix 2: Read from primary always for user-facing profile pages.**

Simpler but wastes primary capacity. Acceptable for low-traffic applications. Not acceptable at Google scale where the primary is already near capacity.

**Fix 3: Use a read-after-write token.**

After a write, the primary returns the WAL position (LSN in PostgreSQL). The application passes this LSN to the replica. The replica waits until it has replicated up to that LSN before answering. PostgreSQL 14+ supports `pg_wait_lsn()`. This is the cleanest fix but adds latency to reads.

---

### 1.7 Quick Reference: Monotonic Reads and Sequential Consistency

Two concepts in the table deserve a brief concrete treatment because they appear in interviews frequently and candidates conflate them.

**Monotonic reads** means: once you have seen version N of a value, you will never be shown a version older than N. You can move forward in time, never backward.

The failure mode is jarring in practice. A user edits their bio. They see the updated bio (version 2). They refresh the page. The load balancer routes them to a different replica that is behind — they see the old bio (version 1). From the user's perspective, their edit "disappeared." Cassandra with no sticky session routing can produce this. The fix is session affinity: route all requests from the same user session to the same replica. This is imperfect (the replica can still be behind when first assigned), but it prevents the time-traveling-backward phenomenon.

**Sequential consistency** (used by ZooKeeper and etcd) is stronger. Every operation appears to execute in some global order, and all clients see the same global order. This is not full linearizability (which additionally requires the global order to match real time), but it is strong enough for leader election.

Why does ZooKeeper use sequential consistency for leader election? Because the guarantee "all clients agree on the same order of events" is sufficient to implement a distributed lock. If Client A's lock-acquire write appears before Client B's in the global order, then A has the lock. All observers agree. No split-brain. The exact wall-clock moment of each write does not matter — only the agreed order matters.

If you downgraded ZooKeeper to eventual consistency, two clients could both believe they acquired the lock, because they observe the write history in different orders. Two services would act as leader simultaneously, potentially corrupting shared state.

---

## 2. Elasticsearch: Search as a Database (and Why It Is Not a Database)

### 2.1 What Elasticsearch Is

**Elasticsearch** is a distributed search and analytics engine built on top of Apache Lucene. You throw documents at it (in JSON), and it lets you search those documents in milliseconds using full-text queries, filters, aggregations, and geospatial queries. It is excellent at one thing: finding documents that match a query, ranked by relevance.

It is not a general-purpose database. This distinction is crucial. If you say "I'll use Elasticsearch as my main database" in an L6 interview, the interviewer will know you do not understand it.

---

### 2.2 The Inverted Index: How Search Works

A **forward index** is what a regular database table looks like: each document has a list of its words.

```
Forward Index
+----------+-----------------------------------+
| Doc ID   | Words                             |
+----------+-----------------------------------+
| doc_1    | hello, world, today               |
| doc_2    | world, news, today                |
| doc_3    | hello, darkness, my, old, friend  |
| doc_4    | news, flash, breaking             |
+----------+-----------------------------------+
```

If you want to find all documents containing "hello", you scan every row. For 100 million documents, that is 100 million comparisons. Too slow.

An **inverted index** flips the structure: each word maps to a list of documents containing it.

```
Inverted Index
+-----------+---------------------------+
| Word      | Posting List (Doc IDs)    |
+-----------+---------------------------+
| hello     | [doc_1, doc_3]            |
| world     | [doc_1, doc_2]            |
| today     | [doc_1, doc_2]            |
| news      | [doc_2, doc_4]            |
| darkness  | [doc_3]                   |
| breaking  | [doc_4]                   |
+-----------+---------------------------+
```

Now query: "hello world"

1. Look up "hello" → [doc_1, doc_3]
2. Look up "world" → [doc_1, doc_2]
3. Intersect: [doc_1]
4. Return doc_1 in ~1 millisecond regardless of how many total documents exist

The posting lists are sorted, so intersection is a simple two-pointer merge — O(result size), not O(total documents). This is why Elasticsearch can search 100 million documents in under 100ms.

**Relevance scoring.** Not all matches are equal. Elasticsearch uses **BM25** (Best Match 25), a probabilistic ranking algorithm. A document where "hello" appears 10 times ranks higher than one where it appears once. A rare word like "quasar" gives a stronger signal than a common word like "the." BM25 computes a score per document, and results are returned sorted by score descending.

---

### 2.3 What Elasticsearch Can Do

- **Full-text search with relevance ranking.** Search a product catalog, return results sorted by how well they match the query.
- **Fuzzy search.** "serch" finds "search" by computing edit distance (Levenshtein distance). Elasticsearch checks if the misspelled word is within 1-2 character edits of a real word in the index.
- **Aggregations.** "How many products are in each price range?" returns a histogram. "What are the top 10 categories by product count?" is a terms aggregation. These are computed in-memory across shards.
- **Geospatial queries.** "Find all restaurants within 5km of this GPS coordinate." Elasticsearch stores latitude/longitude fields and uses geo-point data types.
- **Highlighting.** Return the sentence containing the match, with the matched term bolded — used for search result snippets.

---

### 2.4 Why Elasticsearch Is Not Your Source of Truth

**No transactions.** You cannot write two documents atomically. If you update a user's profile and their search index document in the same Elasticsearch "transaction," there is no transaction. One can succeed and one can fail, leaving them inconsistent.

**Eventual consistency by default.** After you index a document, it is not immediately searchable. Elasticsearch refreshes its in-memory index to disk on a one-second interval by default. During that second, the document exists in Elasticsearch but cannot be found by search. For a social feed this is fine. For a system where a user posts something and immediately clicks "view post," they will not find it.

**Data loss risk.** Elasticsearch does not have a Write-Ahead Log with the same durability guarantees as PostgreSQL. Data lives in-memory segments until flushed. A hard crash between refresh and flush can lose documents. Elasticsearch has `fsync` (called a "flush"), but it happens less frequently than PostgreSQL's WAL write.

**Designed for search, not updates.** Updating a document in Elasticsearch actually deletes the old version and writes a new one. The old version is marked as deleted but still takes up space until a segment merge reclaims it. Heavy update workloads cause write amplification that degrades search performance.

**The bottom line:** Elasticsearch is a read-optimized index over data that lives somewhere else. That "somewhere else" is your real database.

---

### 2.5 The Sync Problem: Keeping Elasticsearch in Sync with PostgreSQL

The most common real-world architecture is: PostgreSQL as the source of truth, Elasticsearch as the search layer. The hardest part is keeping them synchronized.

**Wrong approach: Dual write from application code.**

```
Application code:
  1. INSERT INTO products VALUES (...)   -> PostgreSQL
  2. PUT /products/_doc/123 { ... }      -> Elasticsearch
```

This looks simple but has a fatal flaw. What if step 1 succeeds and step 2 fails? PostgreSQL has the product. Elasticsearch does not. Search returns zero results for a product that exists. You have no automatic way to detect or repair this. The systems drift apart permanently until someone runs a manual reconciliation job.

**Right approach: Change Data Capture (CDC) via Kafka.**

**Change Data Capture (CDC)** reads the database's own transaction log (WAL in PostgreSQL) and converts every insert, update, and delete into an event stream. The application never writes to Elasticsearch directly.

```
+-------------+     WAL      +----------+     topic     +---------+
| PostgreSQL  |  ----------> | Debezium |  -----------> |  Kafka  |
| (source of  |              | (CDC     |               | (durable|
|   truth)    |              |  agent)  |               |  log)   |
+-------------+              +----------+               +---------+
                                                             |
                                              Kafka Sink Connector
                                                             |
                                                             v
                                                    +---------------+
                                                    | Elasticsearch |
                                                    | (search index)|
                                                    +---------------+
```

**Debezium** is an open-source CDC tool that tails the PostgreSQL WAL. Every committed transaction becomes a Kafka message in the correct order. The Elasticsearch Kafka Connector reads those messages and applies them to Elasticsearch. If the connector fails, it simply re-reads from its last committed Kafka offset when it restarts — no data is lost.

Latency: new data is searchable in Elasticsearch 2–10 seconds after committing to PostgreSQL. This is acceptable for most use cases. It is not acceptable for cases where you need to immediately search something you just created.

**Re-indexing: The planned pain.** When you need to change how data is indexed in Elasticsearch (e.g., you want to add a new field, change the tokenizer, or change the mapping), you must rebuild the entire index. You cannot alter a mapping in place the way you alter a PostgreSQL table schema.

The zero-downtime strategy uses **index aliases**:

```
Step 1: Current state
        Alias "products" -> Index "products_v1"

Step 2: Build new index in background
        Create "products_v2", reindex all data from products_v1 to products_v2

Step 3: Atomic alias swap
        Alias "products" -> Index "products_v2"
        (happens in milliseconds, zero downtime)

Step 4: Delete old index
        Delete "products_v1"
```

**Real incident: Twitter's search index rebuild.** Twitter's search index held approximately 500TB of tweet data. When they needed to rebuild the index (changed tokenization strategy), the rebuild took 3 days. During those 3 days, new tweets were being indexed, but re-indexing of older tweets was ongoing. The operational complexity of keeping the old and new indexes synchronized during rebuild, then cutting over, required a dedicated team and a carefully rehearsed runbook. The lesson: test your re-indexing process every quarter. The worst time to figure out your re-index procedure is when you need it urgently in production.

---

### 2.6 Elasticsearch at Scale: Shards, Replicas, and the Sizing Problem

Elasticsearch splits an index into **shards**. Each shard is a complete, standalone Lucene index. When you query an index, Elasticsearch queries all shards in parallel and merges the results. More shards = more parallelism = faster large queries, up to a point.

```
Index: "products" (3 shards, 2 replicas each)

Node 1: [Shard 0 PRIMARY] [Shard 1 REPLICA ] [Shard 2 REPLICA ]
Node 2: [Shard 0 REPLICA ] [Shard 1 PRIMARY] [Shard 2 REPLICA ]
Node 3: [Shard 0 REPLICA ] [Shard 1 REPLICA ] [Shard 2 PRIMARY]
```

Every write goes to the primary shard, which replicates to its replica shards. Reads can be served by any shard copy.

**The shard count problem.** You set the number of primary shards when you create the index. You cannot change it later (without re-indexing). If you set 5 shards and your data grows to need 50 shards, you must re-index. Plan shard count based on expected data volume. A common rule of thumb: keep each shard between 10GB and 50GB. An index with 500GB of data should have 10–50 primary shards.

**Heap sizing: The 32GB wall.** Elasticsearch runs on the JVM. It needs heap memory to hold the in-memory portions of the inverted index (called the "field data cache" and "filter cache"). The rule is: set heap to 50% of available RAM, leaving the other 50% for the OS filesystem cache (which Lucene also uses). But never set heap above 32GB. Above 32GB, the JVM can no longer use "compressed ordinary object pointers" (compressed OOPs), which causes memory overhead to jump dramatically and performance to degrade. A node with 64GB RAM should have a 31GB heap and ~33GB for OS cache.

---

## 3. Kafka: The Write-Ahead Log You Can Query (Not a Database, But Confused for One)

### 3.1 What Kafka Actually Is

**Apache Kafka** is a distributed, durable, ordered log of messages. Think of it as a WAL — the same concept that makes PostgreSQL crash-safe — but one that is accessible as a service over the network, retained for days or weeks, and readable by many consumers simultaneously.

Every message in Kafka has an **offset**: a sequential integer that identifies its position within a partition. Offset 0 is the first message ever written. Offset 4,732,891 is the 4,732,892nd message. Consumers track which offset they have read up to. When a consumer restarts after a crash, it reads from its last committed offset. No messages are lost.

```
Kafka Partition (one continuous log):
+------+------+------+------+------+------+------+
| OFF0 | OFF1 | OFF2 | OFF3 | OFF4 | OFF5 | OFF6 | ...
+------+------+------+------+------+------+------+
  ^                              ^
  |                              |
Consumer A read up to OFF1    Consumer B read up to OFF5

Both consumers are independent. Consumer A being slow does not
affect Consumer B. Neither affects how Kafka stores messages.
```

This independence is the most important property of Kafka. Each consumer group maintains its own offset. Adding a new consumer group to read all messages from the beginning costs nothing. No messages are re-processed by existing consumers.

---

### 3.2 Kafka's Internal Model: Partitions, Consumer Groups, and Ordering

Before understanding where Kafka fits in the data store landscape, you need a precise mental model of how it works.

A **topic** is a named stream of messages. A topic is split into **partitions**. Partitions are the unit of parallelism. Within a partition, messages are strictly ordered. Across partitions, there is no ordering guarantee.

```
Topic: "user-events" (3 partitions)

Partition 0:  [msg0] -> [msg3] -> [msg6] -> [msg9]  (user_id % 3 == 0)
Partition 1:  [msg1] -> [msg4] -> [msg7] -> [msg10] (user_id % 3 == 1)
Partition 2:  [msg2] -> [msg5] -> [msg8] -> [msg11] (user_id % 3 == 2)
```

When you write a message, you specify a key. Kafka hashes the key to pick a partition. All messages with the same key always go to the same partition — this guarantees ordering for a given key. In the user-events example, all events for user 42 (42 % 3 = 0) land on Partition 0, in order. This means a consumer reading Partition 0 sees user 42's events in the exact order they happened.

A **consumer group** is a set of consumers that cooperate to read a topic. Kafka assigns each partition to exactly one consumer in the group at a time. If you have 3 partitions and 3 consumers in a group, each consumer reads one partition. If you have 3 partitions and 6 consumers, 3 consumers sit idle — you can never have more active consumers than partitions.

```
Consumer Group "analytics-service" reading "user-events":

Partition 0 -> Consumer Instance A  (reads user_id % 3 == 0 events)
Partition 1 -> Consumer Instance B  (reads user_id % 3 == 1 events)
Partition 2 -> Consumer Instance C  (reads user_id % 3 == 2 events)
```

If Consumer Instance B crashes, Kafka triggers a **rebalance**: Partition 1 is reassigned to A or C within 30 seconds (default session timeout). During the rebalance window, Partition 1 is not being consumed. This is a latency gap, not data loss — messages wait safely on disk.

**Backpressure by design.** Kafka does not push messages to consumers. Consumers pull at their own rate. A slow consumer simply falls further behind — it never drops messages, it just accumulates lag. You can monitor consumer lag to detect if a consumer is falling dangerously behind. This pull model is why Kafka handles bursty traffic gracefully: a spike in writes shows up as consumer lag, not dropped messages or backpressure errors.

---

### 3.3 Why People Confuse Kafka with a Database (And Why They Are Wrong)

Kafka has three properties that look database-like:

1. **Durable.** Messages are written to disk and replicated across brokers. They do not disappear when a broker crashes.
2. **Ordered.** Within a partition, messages have a guaranteed order. Offset 5 always comes after offset 4.
3. **Queryable.** Via **Kafka Streams** and **ksqlDB**, you can run SQL-like queries on Kafka topics: aggregations, joins, windowed computations.

Given these properties, you might think: "Can I use Kafka as my database?" The answer is no, for three reasons:

- **No random reads.** You cannot say "give me message at offset 4,732,891" efficiently. You can seek to an offset and read forward, but you cannot look up a specific key the way you look up a row by primary key in PostgreSQL.
- **No updates.** Kafka is append-only. You cannot modify a message after it is written.
- **No deletes (by default).** Messages expire based on time or size retention policies, not on business logic. You cannot delete a specific message (except via log compaction, which keeps only the latest value per key — useful but limited).

---

### 3.4 Where Kafka Fits in the Data Store Landscape

| Question | Answer | Reason |
|---|---|---|
| Primary source of truth for OLTP? | No | No random reads, no updates |
| Cache for low-latency key lookup? | No | No O(1) key access |
| Event bus for async communication? | Yes | The canonical use case |
| Data pipeline between systems? | Yes | Backpressure, replay, multiple consumers |
| Audit log for compliance? | Yes | Immutable, ordered, retained |
| Bootstrap a new data store? | Yes | Replay events from offset 0 |

---

### 3.5 The Kafka + Database Pattern: Standard at Google/Netflix/Uber

The most powerful pattern is: write to Kafka once, fan out to many data stores.

```
+-------------+
| Application |
+------+------+
       |
       | write (fast, ordered, durable)
       v
+-------------+
|    Kafka    |
| (durable    |
|    log)     |
+------+------+
       |
       +------------------+------------------+------------------+
       |                  |                  |                  |
       v                  v                  v                  v
+------------+   +---------------+   +----------+   +----------+
| PostgreSQL |   | Elasticsearch |   | BigQuery |   |  Redis   |
| (OLTP      |   | (search       |   | (analytics|  | (cache   |
|  source of |   |  index)       |   |  warehouse|  |  warm-up)|
|  truth)    |   |               |   |           |  |          |
+------------+   +---------------+   +----------+   +----------+
Consumer Grp 1   Consumer Grp 2      Consumer Grp 3  Consumer Grp 4
```

Each arrow is an independent consumer group. Each consumer group reads the same Kafka topic at its own pace. If the BigQuery consumer is slow, it does not slow down the PostgreSQL consumer. If the Redis consumer crashes, it restarts and replays from its last committed offset — no data is lost.

**The critical benefit:** Adding a new data store requires zero changes to the application. You add a new consumer group that reads from the existing Kafka topic. The application never knows. This is how Netflix adds new analytics systems without touching their billing or streaming services.

---

### 3.6 Log Compaction: Kafka's Closest Approximation to a Database

Kafka has one feature that makes it behave slightly more like a key-value store: **log compaction**. When you enable log compaction on a topic, Kafka guarantees that for every key, it will retain at least the most recent message. Older messages with the same key are garbage-collected.

```
Before compaction (key=user_42 has 4 messages):
[user_42: v1] -> [user_42: v2] -> [user_33: v1] -> [user_42: v3]

After compaction:
[user_33: v1] -> [user_42: v3]    <- only latest value per key retained
```

This is how Kafka implements a **changelog topic**: a stream that, when replayed from the beginning, reproduces the latest state of every key. Kafka Streams uses compacted changelog topics to rebuild in-memory state stores when a consumer restarts — instead of replaying the full uncompacted history, it replays only the latest value per key, which is much faster.

Log compaction is not the same as database updates. You still cannot look up a key in O(1) — you have to scan the partition. But it makes Kafka viable as the source of truth for systems like Kafka Streams that maintain derived state in local RocksDB instances (materialized views). Understanding this distinction separates candidates who have read Kafka's documentation from those who have operated it in production.

---

### 3.7 Kafka as a Database Migration Escape Hatch

Imagine you are at a company that built everything on PostgreSQL. The data grew to 10TB. Queries are slow. You decide to migrate to Cassandra for certain workloads. How do you bootstrap Cassandra with 10TB of existing data?

If you have been writing all events to Kafka with a long retention policy (say, 30 days), you simply spin up a new Kafka consumer group, set its offset to the beginning, and replay every event into Cassandra. Cassandra bootstraps itself from the event log. The migration window is determined by your Kafka retention period.

If you have not been writing to Kafka, you have to build a migration ETL job from scratch, handle inconsistencies between the running PostgreSQL and the Cassandra being populated, and figure out the cutover moment — much harder. This is why teams that instrument Kafka from the start have far more flexibility later.

---

## 4. Vector Databases: The AI-Era Data Store

### 4.1 Why Vector Databases Suddenly Matter

For decades, databases answered exact questions: "Find the user whose email is alice@example.com." This maps perfectly to a B-tree index. But the AI era asks a different question: "Find products similar to this image" or "Find documents that mean the same thing as this sentence even if they use different words."

Traditional databases cannot answer these questions. A B-tree on a product description column cannot find semantically similar descriptions — it can only match exact substrings. You need a new kind of data structure.

**The key insight:** Machine learning models (especially large language models and vision models) can convert any piece of data — text, images, audio, video — into a list of numbers called an **embedding**. This list of numbers encodes the semantic meaning of the data. Semantically similar items produce numerically similar embeddings.

```
Text: "cat"     -> embedding: [0.82, -0.14, 0.56, 0.03, ... 1536 numbers]
Text: "kitten"  -> embedding: [0.79, -0.11, 0.54, 0.06, ... 1536 numbers]
                   ^ very close! (small distance between vectors)

Text: "car"     -> embedding: [0.12,  0.88, -0.34, 0.67, ... 1536 numbers]
                   ^ far from cat/kitten (large distance between vectors)
```

Finding "similar" items becomes finding vectors with small distance — **nearest neighbor search**. A vector database is a system optimized to perform nearest neighbor search on millions or billions of vectors.

---

### 4.2 The Nearest Neighbor Problem

You have 100 million product embeddings. A user uploads a photo of a couch. Your vision model converts the photo into a 1536-dimension embedding. You want the 10 most similar products.

**Brute force:** Compute the distance from the query vector to all 100 million stored vectors. Pick the 10 smallest distances. This is O(N * D) where N = 100M and D = 1536. At modern hardware speeds, this takes 10-30 seconds. Too slow for a real-time product page.

**Approximate Nearest Neighbor (ANN):** Trade a tiny accuracy loss for a massive speed gain. Instead of finding the exact 10 nearest neighbors, find 10 vectors that are very likely to be the nearest neighbors. In practice, ANN algorithms achieve 95-99% recall (they find 9.5 out of the true 10 nearest neighbors) in milliseconds instead of seconds.

**HNSW (Hierarchical Navigable Small World)** is the most widely used ANN algorithm. It builds a multi-layer graph where each node is a vector. Higher layers have fewer nodes and allow fast long-distance jumps. Lower layers have all nodes for local precision.

```
HNSW Graph (simplified, 3 layers):

Layer 2 (few nodes, coarse navigation):
  A --------- E

Layer 1 (more nodes):
  A --- B --- C --- D --- E

Layer 0 (all nodes, fine search):
  A - A1 - B - B1 - C - C1 - D - D1 - E - E1

Search: Start at top layer. Jump greedily toward query. Drop to
lower layer. Repeat until Layer 0. Explore neighborhood. Return
top-K results.
```

Query time: O(log N) for the top layers + O(1) for the local neighborhood. For 100M vectors, this is typically 1-10ms.

**IVF (Inverted File Index)** clusters vectors into buckets using k-means clustering. Each bucket contains a centroid vector. At query time: find the closest bucket centroid, then only search within that bucket. Faster to build than HNSW, less accurate at the same budget.

---

### 4.3 Distance Metrics: How "Similar" Is Defined

Vector databases compute distance between vectors using one of three metrics. Choosing the wrong metric gives you wrong results, even if everything else is correct.

**L2 (Euclidean) distance.** The straight-line distance between two points in high-dimensional space. Use this when the magnitude of the vector matters — for example, when comparing image embeddings where brightness is encoded in the vector magnitude.

```
vector_a = [1.0, 2.0, 3.0]
vector_b = [1.5, 2.5, 3.5]

L2(a, b) = sqrt((1.5-1.0)^2 + (2.5-2.0)^2 + (3.5-3.0)^2)
          = sqrt(0.25 + 0.25 + 0.25)
          = sqrt(0.75) ≈ 0.866
```

**Cosine similarity.** Measures the angle between two vectors, ignoring magnitude. Use this for text embeddings: a document about "cats" is similar whether it uses the word "cat" twice or twenty times. Cosine similarity is the most common metric for LLM-generated embeddings.

```
cosine_similarity(a, b) = dot(a, b) / (|a| * |b|)
                        = 1.0 if perfectly aligned
                        = 0.0 if perpendicular (unrelated)
                        = -1.0 if opposite
```

**Dot product.** Used when both direction and magnitude matter. Commonly used in recommendation systems where the magnitude of the embedding encodes the user's "strength" of preference for a category.

The pgvector extension supports all three: `<->` for L2, `<=>` for cosine, `<#>` for dot product (negative, so `ORDER BY ... ASC` gives highest similarity).

---

### 4.4 Vector Database Systems: When to Use What



| System | Type | Best For | Weakness |
|---|---|---|---|
| pgvector | PostgreSQL extension | <10M vectors, SQL joins alongside search | Slower ANN than purpose-built systems |
| Pinecone | Managed cloud service | Production at scale, no ops | Vendor lock-in, cost |
| Weaviate | Open-source, full DB | Combining vector + keyword search | Operationally complex |
| Qdrant | Open-source, purpose-built | Pure vector workload, self-hosted | No SQL |
| Chroma | Open-source, lightweight | Prototyping, local development | Not production-ready at scale |
| Faiss | Library (Meta) | Building block inside other systems | Not a full database |

**When to choose pgvector:**
- You already run PostgreSQL and your team knows it well
- You have fewer than 10 million vectors (pgvector handles this comfortably)
- You need SQL joins: "find similar products AND filter by category = 'electronics' AND price < 500" — this is trivial in pgvector because it is just SQL
- You want to avoid running a second data store

**When to choose a dedicated vector database:**
- You have more than 10 million vectors and need sub-10ms query times
- Your workload is almost entirely vector search with few SQL joins
- You need features like real-time index updates at high write throughput

---

### 4.5 Real Use Case: Similar Product Recommendations

Suppose you are building the "customers also viewed" feature for an e-commerce site. When a user views a product page, you want to show 10 similar products.

**Step 1: Generate embeddings offline.**

```
Pipeline (runs nightly or on product update):

+-------------+     product     +------------------+
|  PostgreSQL |  ------------>  | Embedding Model  |
|  products   |  name, desc,    | (OpenAI, Cohere, |
|   table     |  category, etc  |  or in-house)    |
+-------------+                 +--------+---------+
                                         |
                                 1536-dim vector
                                         |
                                         v
                                +----------------+
                                | pgvector or    |
                                | Pinecone index |
                                +----------------+
```

**Step 2: Query at request time.**

With pgvector, the SQL is:

```sql
SELECT
    id,
    name,
    price,
    category
FROM products
WHERE category = 'furniture'
  AND price BETWEEN 200 AND 2000
ORDER BY embedding <-> $1   -- <-> is the L2 distance operator
LIMIT 10;
```

The `<-> $1` operator computes the L2 (Euclidean) distance between each product's stored embedding and the query embedding `$1`. The `ORDER BY` + `LIMIT 10` combined with an IVFFlat or HNSW index on the embedding column makes this sub-10ms for up to ~5M rows.

**The combined filter problem.** Applying traditional filters (category, price) alongside vector search is called **filtered ANN**. It is harder than it looks. If only 1% of products are in the right category and price range, a naive approach — run ANN on all products, then filter — returns very few results (most of the top-10 ANN results get filtered out). Purpose-built vector databases like Qdrant solve this with payload indexing: they integrate filters into the graph traversal so only eligible candidates are ever considered. pgvector handles this less efficiently for very selective filters.

**Step 3: Full pipeline diagram.**

```
User views product page
         |
         v
  +-------------+
  | Web Server  |
  +------+------+
         |
         | 1. Fetch product embedding from pgvector
         | 2. Run similarity query with filters
         v
  +-------------+      ANN query      +------------------+
  |  pgvector   | <-----------------> | Embedding stored |
  | (products   |                     | for each product |
  |  table +    |  returns top-10     |                  |
  |  index)     | ------------------> |                  |
  +-------------+                     +------------------+
         |
         | top-10 similar products
         v
  +-------------+
  | Web Server  |  assembles "You might also like" section
  +-------------+
         |
         v
      Browser
```

---

### 4.6 Embedding Model Choice and Dimensionality

The size of the embedding (number of dimensions) is a trade-off between accuracy and storage/speed.

| Model | Dimensions | Storage per vector | Use case |
|---|---|---|---|
| OpenAI text-embedding-3-small | 1536 | 6KB | General text search |
| OpenAI text-embedding-3-large | 3072 | 12KB | High accuracy text |
| CLIP (images + text) | 512 | 2KB | Multi-modal product search |
| Sentence-BERT (local) | 768 | 3KB | On-premise, no API cost |

For 10 million products with 1536-dimension embeddings at 4 bytes per float: 10M * 1536 * 4 = ~61GB. This fits on a single large machine's RAM, which is why pgvector is viable at this scale. At 100M products, you are at 610GB — now you need a distributed vector store.

---

## Putting It Together: Which Database for Which Problem

The table below summarizes when to use each database discussed in this chapter. In an L6 system design interview, you are expected to name the right tool and justify it in terms of consistency, performance, and operational trade-offs.

| Need | Database | Consistency | Key Trade-off |
|---|---|---|---|
| Financial transactions, global | Spanner / CockroachDB | Linearizable | High latency (2-phase commit across regions) |
| Social feed writes | Cassandra | Eventual (CL=ONE) | Stale reads acceptable; LWW risk on concurrent edits |
| Config / leader election | ZooKeeper / etcd | Sequential | Not for high-throughput data; small data only |
| User profile read-your-writes | PostgreSQL + primary reads | Causal | Primary capacity pressure; use replica routing carefully |
| Full-text product search | Elasticsearch | Eventual (1s lag) | Not a source of truth; needs CDC sync from real DB |
| Event streaming / data pipeline | Kafka | Ordered per partition | Not queryable by key; no random access |
| Semantic / similarity search | pgvector / Pinecone | Depends on backing DB | Approximate results; embedding quality matters |
| Distributed counters | Redis (G-Counter pattern) | Eventual | Manual CRDT implementation; not automatic |

---

## Summary

This chapter translated Chapter 27's theoretical concepts into concrete database choices. The key lessons are:

- **Consistency models are not abstract.** Choosing Cassandra at CL=ONE means choosing eventual consistency, LWW conflict resolution, and the possibility of stale reads. These are real consequences with real failure modes.
- **Elasticsearch is a read-optimized index**, not a database. It needs a CDC pipeline from a real database to stay synchronized. It cannot be your source of truth.
- **Kafka is a durable log**, not a database. Its superpower is that multiple consumers can read the same stream independently, making it the backbone of fan-out architectures. It is also your migration safety net.
- **Vector databases are for semantic similarity**, not exact match. pgvector is the right starting point for most teams. Purpose-built vector databases become necessary at hundreds of millions of vectors or with complex filtered ANN requirements.

Every choice in this chapter is a trade-off. The L6 skill is naming the trade-off, explaining why it is acceptable for the specific use case, and knowing what to do when it breaks.
# Chapter 28 — Part H: Calibration, Brainstorming, Exercises, and Quick Reference

This is the final section of Chapter 28. Everything before this built up the concepts — how
databases work, how to pick them, how to scale them, how to migrate them. This section is about
converting that knowledge into interview performance. You will calibrate against what L6 actually
looks like, practice the hard open-ended questions, and leave with a reference card you can pull
up before any interview.

**How to use this section:**

- Read the calibration table once carefully, then come back to it the morning of your interview
  to reset your mental bar.
- Work through the brainstorming questions in 3-5 question sessions, one theme per day. Always
  answer out loud before reading the discussion.
- Pick 2 homework exercises per week. Sketch the schema and write path before consulting hints.
- Keep the Quick Reference Card accessible for the first 10 minutes of any interview prep session.

The goal is not to memorize answers. The goal is to build the instincts that produce good answers
to questions you have never seen before.

---

## 1. L5 vs L6 Calibration Table

The gap between L5 and L6 is not about knowing more facts. It is about depth of reasoning, the
ability to see second-order effects, and the instinct to surface tradeoffs before the interviewer
has to prompt you.

An L5 answer is technically correct. An L6 answer is technically correct and also anticipates
the next two questions the interviewer would have asked. It names the failure modes. It compares
two or three approaches. It commits to a recommendation and explains what would make it change
that recommendation. Read each row and ask yourself honestly which column sounds more like you
right now.

| Dimension | L5 Answer | L6 Answer |
|---|---|---|
| **1. Database selection** | Picks based on data type: relational gets PostgreSQL, flexible gets MongoDB, key-value gets Redis. One-sentence justification. | Starts with access patterns, not data shape. Asks what queries run 95% of the time, what the write patterns are, what consistency is needed, and what scale looks like in 2 years. Eliminates candidates with specific reasons, then commits. Flags where the choice might need revisiting. |
| **2. Indexing strategy** | Adds an index on the WHERE-clause column. Knows too many indexes slow writes. | Considers cardinality, selectivity, and whether the index can cover the query entirely. Knows composite index column order (equality filters before range filters). Uses partial indexes for hot subsets. Reads EXPLAIN ANALYZE output. Factors in index maintenance cost during bulk writes. |
| **3. Caching strategy** | Adds Redis for reads, uses cache-aside, sets a TTL. | Distinguishes what can be cached from what cannot (financial balances, inventory counts). Designs invalidation explicitly — not just TTL. Handles cache stampede on cold start. Evaluates write-through vs write-behind vs read-through based on consistency needs. Sizes the cache and explains eviction behavior. |
| **4. Consistency tradeoffs** | Knows ACID vs BASE. Says "strong for money, eventual for everything else." | Articulates the specific consistency model per operation. Defines "eventual" with a lag number (5ms vs 30s). Knows linearizability vs causal consistency. Designs compensating transactions where distributed transactions are impractical. Identifies the user-facing impact of stale reads. |
| **5. Sharding decision** | Proposes sharding when the database gets big. Picks user_id because it distributes evenly. | Evaluates whether sharding is needed — vertical scaling, replicas, partitioning, and caching come first. When sharding is warranted, reasons about hot spots, cross-shard queries, and resharding cost. Considers the impact on transactions. Plans for resharding from day one. |
| **6. Schema migration** | Writes the ALTER TABLE and runs it in a maintenance window. | Plans migrations in steps: add nullable column, backfill in batches, add application support for both schemas, add NOT NULL, drop old column. Knows gh-ost and pt-online-schema-change. Understands lock behavior on large tables. Builds rollback into the plan. |
| **7. Multi-region design** | Puts a replica in each region for reads. Knows writes go to the primary. | Designs for data residency (GDPR, HIPAA) as a hard constraint. Distinguishes active-passive vs active-active and explains the consistency cost of each. Handles primary region failure. Designs conflict resolution for multi-master setups. |
| **8. Failure mode thinking** | Mentions backups and replicas. Knows the primary can fail over to a replica. | Thinks through the full cascade. If this database goes down, which services break, how do they degrade, what is the blast radius? Designs bulkheads. Separates RPO (data loss window) from RTO (recovery time). Knows how to test failover before it matters. |
| **9. Cross-team decisions** | Treats database choice as a team-internal technical decision. | Understands that database choices create long-term commitments affecting multiple teams. Raises visibility before a choice is locked in. Designs data access contracts so downstream teams are not coupled to storage internals. Pushes back on choices made for the wrong reasons. |
| **10. Performance debugging** | Finds the slow query. Adds an index on the slow column. Checks the result. | Starts by measuring — slow query logs, EXPLAIN ANALYZE, pg_stat_statements. Builds a hypothesis before changing anything. Understands that query plans change as table statistics drift. Considers connection pool exhaustion and lock contention separately from query plan issues. Knows how to reproduce the problem in staging. |
| **11. NoSQL data modeling** | Models documents to look similar to the relational schema. Normalizes to avoid duplication. | Knows NoSQL modeling is query-driven — you design documents around how they are read. Embraces denormalization intentionally. Understands duplication is often correct. Knows DynamoDB single-table design. Models for expected access patterns, not data relationships. |
| **12. Data integrity** | Relies on ACID guarantees. Trusts that a successful write means correct data. | Adds application-level checksums for critical records. Designs idempotent writes to prevent duplicates from retries. Audits with periodic reconciliation jobs. Knows ACID cannot catch semantically wrong data from application bugs. Plans PITR and verifies restore integrity before declaring recovery complete. |

---

## 2. Cross-Topic Brainstorming Questions

These questions are open-ended by design. There is no single correct answer. For each one, try to
answer for 3-5 minutes out loud before reading the discussion. The goal is to practice structuring
your thinking, surfacing tradeoffs, and communicating clearly under pressure.

A common trap in interviews is answering too quickly — you hear the question, recognize the
pattern, and jump to the answer you memorized. Interviewers at L6 can tell the difference between
someone who has thought about a problem and someone who has memorized an answer. Slow down.
Start with the problem constraints. Ask a clarifying question. Name the options before you pick
one. Then commit and defend your choice.

The 25 questions below are grouped by theme. Work through one theme per study session. Do not do
all 25 at once — spaced repetition is more effective than a cram session.

### Theme A: Database Selection

**Question 1.** You are designing a ride-sharing system. The team suggests MongoDB for
"flexibility." Walk me through how you would evaluate this suggestion.

Start by asking what "flexibility" actually means. Is it variable schema because the data
structure might change? Or do they want to embed related documents together? Then enumerate the
actual access patterns: fetch a single ride by ID, query all rides for a driver in a date range,
match drivers to nearby riders via geo queries, billing aggregations. Ask whether the data is
relational — riders, drivers, and rides form a graph. If so, ask what queries require joins and
whether MongoDB's lack of server-side joins pushes join complexity into the application layer.
MongoDB is excellent for document-centric, read-heavy data with variable schemas, but ride-sharing
has strong transactional requirements (you cannot double-assign a driver) and relational structure.
An L6 answer evaluates rather than accepts or rejects cold, then recommends PostgreSQL for core
data and a document store only for genuinely variable metadata.

**Question 2.** A startup has PostgreSQL running fine at 100K users. They are planning for 10M
users. What would you change, and when?

Do not jump to sharding or switching databases. Ask what is actually slow today — query latency,
write throughput, storage, or connection count? At 10x growth, the first interventions are: add
read replicas to offload analytics queries, add a connection pooler like PgBouncer to handle
connection overhead, add proper indexing, partition large tables by time or user range, and tune
vacuum settings. Only after those levers are exhausted does sharding make sense.

The "when" matters as much as the "what." You want to make changes before the database becomes a
bottleneck, not during a 3 AM incident. An L6 answer adds that each change should be validated in
staging at simulated load before production, and that the path from 100K to 10M users is a series
of incremental improvements — not one big rewrite that happens all at once.

**Question 3.** You are asked to store both relational user data and time-series telemetry from
IoT devices. How do you structure the database layer?

These are two fundamentally different workloads. Relational user data — accounts, preferences,
relationships — is low volume, needs strong consistency, benefits from transactions, and has
complex query patterns with joins. Time-series IoT telemetry is extremely high write volume,
append-only, queried by time range, and benefits from time-based compression and retention
policies. Using one database forces you to accept the worst tradeoffs of each world. The clean
answer is a purpose-built time-series database (TimescaleDB, InfluxDB, or a PostgreSQL hypertable)
for telemetry alongside standard PostgreSQL for user data. Cross-database joins are rarely needed
because the IoT data links back to the user via a foreign key in the time-series store, and you
almost never need to join the two datasets in a single query.

**Question 4.** Your team wants to add a search feature. Should you use Elasticsearch or extend
PostgreSQL with full-text search? What factors decide?

PostgreSQL full-text search handles basic to moderate search well — stemming, ranking, and boolean
operators are built in; typo tolerance requires the pg_trgm extension. The case for PostgreSQL:
no new system to operate, search index updates within the same transaction as the write. The case
for Elasticsearch: richer relevance tuning (BM25, custom scoring), faceting and aggregations
designed for search, better performance on hundreds of millions of documents. Deciding factors:
corpus size, ranking complexity, whether faceted search is needed, team capacity to operate
Elasticsearch, and acceptable consistency (Elasticsearch is eventually consistent — a write takes
time to appear in search results). An L6 answer does not treat Elasticsearch as the obvious
default — it earns its complexity.

**Question 5.** The payments team uses MySQL. The recommendations team uses Cassandra. You need
data from both for a new feature. How do you design the data access layer?

Do not query both databases in real time and join in application code — that creates a fragile
critical path with a partial-failure problem. If either database is slow or unavailable, the
entire feature is slow or broken.

Three better options: (1) Build a dedicated read store for this feature, kept in sync via CDC or
event streaming — your feature queries one place that already has the data it needs. (2) Have each
team expose an API that encapsulates their data; your feature calls both APIs and merges results,
but each team owns their storage contract. (3) Write a scheduled sync job that builds a
feature-specific denormalized table refreshed on a defined cadence. An L6 answer also raises the
organizational question: who owns the combined data, and what happens when either team changes
their schema? Whichever option you choose must account for that long-term coupling cost.

---

### Theme B: Consistency and Transactions

**Question 6.** A user transfers $500 from savings to checking. You are using a microservices
architecture with one service per account type. How do you ensure atomicity?

Three main options. Two-phase commit (2PC): a coordinator prepares both services then commits or
rolls back. Strong consistency but blocking — if the coordinator crashes after prepare, both
services wait indefinitely. Saga pattern: a sequence of local transactions each with a
compensating transaction. If the checking credit fails, the savings debit is reversed. There is a
window where the money appears to be in flight. Outbox pattern: write the savings debit and a
pending transfer event in the same local transaction; a separate process picks up the event and
credits checking. Idempotent retry logic handles repeated credit attempts. An L6 answer picks one
approach, explains why it fits the consistency and availability requirements, and explicitly
handles the failure case — including what happens when the compensation itself fails.

**Question 7.** Your e-commerce site allows "add to cart." With eventual consistency, two users
could claim the last item. How do you handle this at the database level?

The key insight is that "add to cart" and "purchase" are different operations. Adding to cart does
not need to reserve inventory — it records intent. Reservation happens at checkout. At checkout,
use optimistic locking: read inventory count and version number, then do a conditional update —
UPDATE inventory SET count = count - 1, version = version + 1 WHERE item_id = ? AND version = ?
AND count > 0. If 0 rows are affected, the item is gone — surface "sold out" to the user. This
avoids holding locks during browsing. A more robust version adds a reservation with a TTL at cart
add — reserve on add, confirm on purchase, release on expiry — which improves conversion but adds
background job complexity for expiration cleanup.

**Question 8.** You are building a distributed counter for likes on a post. Which approaches can
handle 10,000 concurrent increments per second without conflicts?

A naive PostgreSQL row-level lock at 10K/sec causes heavy contention and latency spikes. Better
options: (1) Redis INCR is atomic and single-threaded — easily handles 10K/sec at sub-millisecond
latency. (2) Approximate counting with batch flushes — buffer increments in Redis, flush to the
database in bulk every N seconds; slightly stale but the database is not hammered. (3) Counter
shards — maintain N sub-counters per item, increment a randomly chosen one on each write, read by
summing all shards. (4) Kafka-based counting — emit every like event to a stream and aggregate
downstream for analytics-grade accuracy where strict real-time is not required. The right choice
depends on how accurate the count must be in real time.

**Question 9.** A financial report needs consistent data across 5 tables as of yesterday at
11:59 PM. How do you ensure consistency without locking those tables?

Do not lock tables. Use snapshot isolation instead. In PostgreSQL, BEGIN TRANSACTION ISOLATION
LEVEL REPEATABLE READ gives all reads in the transaction the same snapshot from the transaction
start — no locks held against other writers. For a specific past time, you need either a
point-in-time replica or an append-only audit log that lets you reconstruct past state. The most
practical answer for periodic reports: pre-compute and store the snapshot — at 11:59 PM, run the
aggregation and write results to a report_snapshots table. The report reads from there, which is
immutable once written. An L6 answer also asks whether the 5 tables are written within the same
transaction or across multiple services — if the latter, "consistent as of 11:59 PM" requires
application-level coordination, not just database isolation.

**Question 10.** Your system uses Cassandra with QUORUM consistency. You add a new data center
and the team proposes LOCAL_QUORUM. What are the consistency tradeoffs?

QUORUM requires a majority of all replicas across all data centers. With two DCs and replication
factor 3 each, QUORUM needs 4 of 6 nodes — meaning every write must reach at least one node in
the remote DC. This ensures cross-DC consistency but adds remote network latency to every write.
LOCAL_QUORUM requires a majority only within the local DC. This removes the cross-DC latency
penalty and improves availability — a remote DC outage does not block local writes. The tradeoff:
concurrent writes to the same key in two DCs can produce conflicts resolved by last-write-wins.
For a read-heavy system where writes happen in one DC only, LOCAL_QUORUM is the right call. For
true multi-master active-active where any DC can write any row, QUORUM or careful conflict
handling is required.

---

### Theme C: Scaling and Sharding

**Question 11.** You have sharded user data by user_id across 10 shards. A new feature requires
"show me all users who signed up this month." How do you handle this query?

With hash sharding on user_id, users who signed up this month are scattered across all 10 shards
randomly. Options: (1) Scatter-gather — query all 10 shards in parallel and merge. Works but adds
latency and load on every shard. (2) Build a separate index — a secondary database indexed by
signup_date, kept in sync via CDC. Queries hit the index, not the shards. (3) For internal
reporting only — ETL to a data warehouse where range queries by date are trivial and do not touch
production shards. This illustrates why shard key choice is so consequential: the access patterns
you optimized for at sharding time determine which queries are expensive years later.

**Question 12.** Your DynamoDB table has a hot partition — 90% of reads go to user_id =
"celebrity123". What are your options?

A single DynamoDB partition handles 3,000 RCU and 1,000 WCU per second. If one item is 90% of
traffic and exceeds partition limits, you need to spread it across multiple physical partitions.
Options: (1) Write sharding — store "celebrity123#0" through "celebrity123#9", spread writes
randomly, read all 10 and merge. (2) Cache aggressively — if this is read-heavy profile data,
ElastiCache absorbs the reads; the database should not see 90% of traffic for a cacheable item.
(3) DynamoDB Accelerator (DAX) — an in-memory cache that intercepts reads transparently. (4) For
write hotspots specifically — bucket writes by time window and aggregate downstream. An L6 answer
asks the viral case question during the original design review, not during an incident.

**Question 13.** You are planning to double your shard count from 8 to 16. Walk me through the
resharding process with zero downtime.

A naive rehash requires every key to move while the system is live — too risky to do all at once.
The safe approach using consistent hashing: (1) Spin up 8 new empty shards. (2) Each new shard
takes over half the key range of an existing shard. (3) Copy data for that range from the old
shard to the new one. (4) During copy, dual-write new writes to both shards so the new shard
stays fresh. (5) Once the new shard has caught up, flip the routing layer — reads go to the new
shard. (6) After validation, remove the migrated range from the old shard. Each range migrates
independently, limiting the blast radius of any single failure to one slice. The most important
rule: run the entire procedure in staging with production-level traffic before touching production.

**Question 14.** The team is debating whether to shard by tenant_id or user_id for a multi-tenant
SaaS. What factors determine the choice?

Tenant_id sharding co-locates all tenant data on one shard — tenant-scoped queries are fast, and
you can move noisy tenants to dedicated shards. The risk is hot tenants: an enterprise customer
with 100x the traffic of a small account overloads a single shard. You can partially mitigate
this by allocating multiple shard slots to large tenants, but this adds operational complexity.

User_id sharding distributes load more evenly but scatters a tenant's data across all shards,
making any "all users for this tenant" query a scatter-gather operation across every shard in
the cluster.

Deciding factors: (1) Tenant size variance — uniformly small tenants favor tenant_id; a mix of
enterprise and free-tier accounts favors user_id to avoid hot shards. (2) Query scope — if 95%
of queries are scoped to a single tenant, tenant_id eliminates scatter-gather for the common case
and is usually the right call. (3) Compliance — tenants requiring data isolation for regulatory
reasons favor tenant_id sharding or dedicated schemas. An L6 answer designs for the enterprise
tenant edge case from day one and has a plan to migrate hot tenants to isolated shards before
they cause a production incident.

**Question 15.** Your read replica is 30 seconds behind. Which user-facing features can tolerate
this lag, and which cannot?

Features that can tolerate 30-second lag: search results, content feeds, analytics dashboards,
product catalog pages. Features that cannot: anything the user just changed (you update your
profile photo and immediately navigate to your profile — you must see the new photo), inventory
counts during active checkout (stale inventory means overselling), payment status (a completed
payment must appear immediately), post-password-change login (the new password must work at once).
Design pattern for intolerable cases: read-your-own-writes consistency — route a user's reads to
the primary for a short window after any write. An L6 answer also treats the 30-second lag as a
problem to investigate and fix, not just to route around.

---

### Theme D: Schema Evolution and Migrations

**Question 16.** You need to add a NOT NULL column to a 500M row table. Your system runs 24/7.
Walk me through your approach.

Step 1: Add the column as nullable with no default. On PostgreSQL 11+, this is instant — no rows
are rewritten. Step 2: Backfill in batches of 10,000-50,000 rows with a sleep between batches to
avoid lock buildup and replication lag. On a 500M row table this takes hours — run during
low-traffic periods or let it run across multiple days. Step 3: Add a NOT NULL constraint with NOT
VALID — this enforces the constraint on new rows immediately without scanning existing rows.
Step 4: Run VALIDATE CONSTRAINT. This does a full scan but takes only a share lock, not an
exclusive lock — reads and writes continue normally. Step 5: Once validated, the constraint is
enforced for all rows. The entire process is non-blocking and can run while the system serves
normal traffic.

**Question 17.** You are migrating from MongoDB to PostgreSQL for a social network. Users have
inconsistent document structures. What is your strategy?

First, audit the actual data — sample the MongoDB collection to understand which fields exist, how
common each is, and where types are inconsistent. Measure first, design second. Define a target
PostgreSQL schema for the most common structure, mapping rare fields to NULL. For genuinely
flexible per-user metadata, add a JSONB column for the irregular parts alongside structured
columns for the predictable ones. Migration sequence: (1) Build schema and transformation logic,
test on a 1% sample. (2) Bulk load and validate record counts. (3) Run both databases in parallel
with dual writes or CDC sync. (4) Switch reads to PostgreSQL one feature at a time, validating
each. (5) Once all reads are migrated, stop writing to MongoDB, drain the sync, keep it read-only
for a two-week rollback window, then decommission. Never do a big-bang cutover.

**Question 18.** Two services share a database table. You need to rename a column. How do you do
this without breaking the other service?

You cannot rename directly — one service breaks on its next deploy. The safe approach is the
expand/contract pattern. Step 1: Add a new column with the new name alongside the old one.
Step 2: Add a trigger or application-level dual-write that keeps both columns in sync.
Step 3: Update Service A to read and write the new column name; deploy and verify.
Step 4: Backfill the new column for rows written before the trigger was installed.
Step 5: Update Service B to read and write the new column name; deploy and verify.
Step 6: Remove the trigger.
Step 7: Drop the old column. This spans multiple deployment cycles and can take days. The takeaway
is that shared databases between services make any schema change expensive — a strong argument for
service-owned databases with API contracts instead.

**Question 19.** You are deprecating a feature that adds 3 columns to every insert. How do you
safely remove these columns from a live system?

Step 1: Search the codebase exhaustively for every reference — SELECT, INSERT, UPDATE, ORM model
definitions, migration files, raw SQL strings, stored procedures, scheduled jobs. Do not trust
memory. Search. Step 2: Stop writing to the columns. Deploy. Verify via pg_stat_statements and
application metrics that no write traffic touches them. Step 3: Stop reading from them. Deploy.
Confirm no reads. Step 4: The columns are now orphaned — stable and safe. Leave them for one or
two deployment cycles to monitor for missed references. Step 5: Drop the columns, plan the DROP
COLUMN for a low-traffic window, and monitor replication lag during the operation. An L6 answer
also asks whether the data has audit or compliance value before dropping — archive it first if
there is any doubt.

**Question 20.** A new requirement means you need to store user events differently. Old events are
archived, new events have a different structure. How do you handle versioning?

Four approaches: (1) Version field — add an event_schema_version column; application code
branches on the version when reading. Clean at first, messy as versions accumulate over years.
(2) Separate tables — events_v1 and events_v2; operationally clear but queries span two tables.
(3) Schema registry (Avro or Protobuf) — each event carries a schema version ID; deserialization
uses the registered schema. Very clean for Kafka-based systems with backward/forward compatibility
rules. (4) JSONB with a version field — maximum flexibility, but nested fields lose query
performance unless specifically indexed. For archived events specifically: if they are cold storage
rarely queried after 90 days, move them to S3 in Parquet format and query via Athena or BigQuery.
Keep only recent events in the hot-path database.

---

### Theme E: Incidents and Failure Modes

**Question 21.** Redis goes down for 30 seconds. Walk through the cascade and how your system
should respond.

The cascade depends entirely on Redis's role. If Redis is a cache: database query volume spikes
immediately. If the database is not sized for direct traffic, it becomes the next victim —
connection pool exhaustion, latency increases, timeouts cascade to the API layer. If Redis is a
session store: users cannot log in or existing sessions fail — requests fail entirely, not just
slowly. If Redis is a rate limiter: traffic either all gets through (fail-open) or all gets blocked
(fail-closed) depending on implementation. If Redis is Pub/Sub: event delivery stops until Redis
is back and the publisher replays. Each use case needs a pre-defined fallback: circuit breakers
for the cache path, explicit fail-open/fail-closed policy for rate limiting, session fallback
strategy. The L6 insight: "Redis goes down" tests your fallback design, not your ability to
restart Redis.

**Question 22.** Your on-call engineer accidentally deleted 50,000 orders without a date filter.
What do you do?

First: stop the bleeding — if the engineer is still running commands, have them stop. If a script
is running, kill it. Every additional second of deletes makes recovery harder. Second: do not
panic-write to "fix" it manually — additional writes complicate recovery. Third: check your WAL
archive. With continuous archiving in PostgreSQL, point-in-time recovery (PITR) lets you restore
to a specific timestamp just before the incident. Spin up a recovery instance, restore to one
minute before the delete, extract the 50,000 deleted orders as INSERT statements, and replay them
into production. Fourth: communicate — open an incident channel, notify leadership, start a
written timeline. Fifth: validate the recovery. Sixth: post-mortem — why did the engineer have
direct production write access with no gate? Add a dry-run requirement for DELETE statements on
large tables and restrict direct production access to break-glass procedures.

**Question 23.** PostgreSQL primary goes down. Your replica is 45 seconds behind. Do you failover?
What data do you risk losing?

45 seconds of lag means up to 45 seconds of transactions are in the primary's WAL but not in the
replica. Promoting the replica loses those transactions. The question is whether 45 seconds of
data loss is within your RPO — this is a business decision, not a technical one alone. For most
user-facing systems (sessions, content, analytics), 45 seconds is within acceptable RPO. Fail over
immediately, promote the replica, update DNS, and let users retry the lost actions. For financial
systems, losing committed orders or payments is unacceptable — attempt primary recovery first,
accept the loss only if the primary is truly unrecoverable, and replay from an upstream source
(payment gateway, message queue). Also cover split-brain: if the primary comes back up after you
have promoted the replica, you must fence the old primary before it resumes accepting writes.

**Question 24.** PostgreSQL says a user has 500 orders, but Elasticsearch shows 495. How do you
investigate and fix this?

Start with investigation, not fixes. Step 1: Identify the 5 missing orders by diffing the order
ID sets from both systems. Step 2: Check their timestamps — if they are from the last 10 minutes,
this may be indexing lag; check the indexer's consumer offset. Step 3: If they are older, check
the Elasticsearch indexing pipeline logs for errors on those specific IDs — a schema mismatch or
malformed field could cause silent indexing failures. Step 4: Check whether the 5 orders have
anything in common (same status, same creation path) suggesting a systematic bug. Step 5: Fix
the pipeline issue first, then reindex the missing orders. Step 6: Build a durable reconciliation
job that periodically diffs PostgreSQL and Elasticsearch order counts, alerts on discrepancy, and
auto-reindexes the diff. Treat this as a symptom of a systematic gap, not a one-time accident.

**Question 25.** A schema migration is running and causing lock contention — writes are backing
up. Do you let it finish or kill it?

Killing it: PostgreSQL rolls back the DDL transaction, the table returns to its pre-migration
state, the lock is released, and writes resume immediately. You have time to redesign the
migration using a non-locking approach (gh-ost, pt-online-schema-change, or expand/contract). The
cost is that the work still needs to happen later. Letting it finish: if the migration is 90%
complete and will finish in 2 minutes, finishing may be faster than killing and re-running. But if
it is early in a 2-hour operation and writes are queuing up fast, you are heading toward a
cascading outage. Decision tree: How far along is it? How fast are writes queuing? Is there
immediate user-facing impact — failed payments, failed logins? Can this be re-done with a
non-locking approach after killing it? In practice: kill it if the blast radius is growing and
you have a safer re-run path. Never let sunk-cost thinking cause an outage. The migration can
always be re-run.

---

## 3. Homework Exercises

These are design problems to work through before your next interview. Do not just read them —
sketch the schema on paper, walk through the write path out loud, and identify the tradeoffs
before reading the L6 hints. Time yourself: a good L6 answer for a homework exercise should be
articulable in 10-12 minutes in an interview setting. If you cannot speak through it in under 15,
keep practicing until you can.

### Exercise 1: Design a URL Shortener Database Layer

**Problem statement:** Build the database layer for a URL shortener. Store 100M shortened URLs,
handle 10B click events per day, and provide analytics — clicks by hour, by country, by referrer.

**What to design:** Schema for URL mappings and click events, indexing strategy, caching layer
design, and a scaling plan for 10B clicks per day.

**Hints:** The read/write ratio is roughly 1,000:1. What does this mean for caching aggressiveness?
10B clicks per day is ~115,000 per second — can you afford to store every raw event? When and
where do you aggregate? The short code lookup is the hottest path in the system — what is your
p99 latency target and how do you hit it end to end?

**What an L6 answer includes:** A URL mapping table with short_code as primary key, cached in
Redis — the top 1% of URLs represent 90% of traffic (power law), so cache hit rate should be
near 100% for that slice. A click event table that is append-only and partitioned by day or hour
for efficient purges and range queries. Raw events are not queried directly at scale — a
pre-aggregated stats table (clicks by short_code by hour by country), populated by a stream
processor, serves analytics queries instead. Clear statement of what is strongly consistent (the
URL lookup must never return a 404 for a valid URL) and what is eventually consistent (analytics
counts allowed to lag by minutes).

### Exercise 2: Migrate a Monolith Database to Microservices

**Problem statement:** A single PostgreSQL database with 50 tables needs to be split among three
services — User Service, Order Service, Product Service. The system runs 5,000 requests/sec and
cannot have more than 5 minutes of total downtime across the whole migration.

**What to design:** A phased migration plan, a strategy for the shared user table referenced by
orders and products, the data synchronization approach during transition, and a rollback plan.

**Hints:** The strangler fig pattern — migrate one service at a time, not everything at once. CDC
can sync from the monolith to new service databases in real time, enabling a dual-read validation
phase. Which service owns the user table? How do others get user data without a direct DB query?
What does the dual-write phase look like and when does it end?

**What an L6 answer includes:** A phased approach where every phase is independently deployable
and reversible: identify ownership, stand up service databases, enable CDC sync, validate data
parity, switch reads service by service, switch writes, decommission old tables. User Service
owns the user identity table and exposes an API — other services call the API, never the database
directly. Rollback at any phase means reverting routing configuration, not restoring backups —
this is only possible if dual-write is still active, which defines when you can safely end it.

### Exercise 3: Design a Real-Time Leaderboard

**Problem statement:** 1M concurrent users, scores updating continuously (one update per active
user per second), rank visible to each user within 100ms.

**What to design:** A Redis Sorted Set approach (key structure, rank query, rolling windows), a
PostgreSQL approach (schema, index, rank query), and a comparison of when each is appropriate.

**Hints:** Redis ZRANK is O(log N) — at 1M members, how much memory? Approximate rank (ranking
within a band of ±1,000) may be good enough for users — what techniques enable this? Partitioned
leaderboards (regional, by cohort) reduce N dramatically. Rolling windows (today, last 7 days, all
time) need separate keys with TTLs — how do you expire them cleanly?

**What an L6 answer includes:** Redis Sorted Set: ZADD for updates, ZRANK for rank, ZRANGE for
top-N. At 1M members (~100 bytes each), the sorted set is about 100MB — trivial for Redis.
Rolling windows: leaderboard:daily:YYYY-MM-DD with TTL expiring 48h after day end; score updates
write to all active window keys. PostgreSQL alternative: B-tree index on score, rank via
SELECT COUNT(*) WHERE score > :user_score runs in O(log N) — adequate for lower update rates but
will struggle at 1M updates/sec. The explicit comparison: Redis for real-time at this scale,
PostgreSQL for batch-computed daily rankings.

### Exercise 4: E-Commerce Inventory System at Scale

**Problem statement:** 10M products, 10K orders/second peak. Must prevent overselling while
maintaining low-latency product pages and checkout.

**What to design:** Schema for inventory and reservations, the write path from cart add through
order confirmed, a comparison of optimistic locking vs pessimistic locking vs reservation model,
and how eventual consistency applies to display pages vs checkout.

**Hints:** Optimistic locking works when conflicts are rare — is that true during a flash sale
with 10K users competing for 100 units? A reservation model needs a TTL and an expiry background
job. Product display pages showing "only 3 left!" can be stale. The checkout page cannot.

**What an L6 answer includes:** Schema: inventory (product_id, available_quantity,
reserved_quantity), reservations (reservation_id, user_id, product_id, quantity, expires_at,
status), orders linked to reservation_ids. Reservation flow: atomically increment reserved_quantity
WHERE available_quantity - reserved_quantity >= requested_quantity; if 0 rows updated, out of
stock. Confirm the reservation at checkout in one transaction. A background job releases expired
reservations every 30 seconds. For flash sales: a queue-based approach so only N reservations
are atomically accepted, and everyone else sees "sold out" immediately — this prevents 9,900 users
from doing expensive conditional updates that all fail. Display pages read from Redis cache;
checkout reads from the primary with a row lock.

### Exercise 5: Multi-Region Database Design for a Banking App

**Problem statement:** Users in EU, US, and APAC. GDPR requires EU user data stays in EU. US
regulations require US financial records stay in the US. Need global low-latency reads and strong
consistency for financial transactions.

**What to design:** Per-region database architecture, how a US-to-EU cross-region transfer works
at the database level, what data can be globally replicated vs what must stay local, and recovery
if one region loses its primary database.

**Hints:** Geo-partitioned Spanner handles row-level data placement natively. Per-region
PostgreSQL gives more control but requires you to enforce data residency yourself. Which data
must stay local — user PII, transaction history, account balances? What about authentication
tokens and fraud rules? A cross-region transfer must be atomic across two databases in two legal
jurisdictions. If the EU database goes down, can EU users log in? Check their balance? Transact?

**What an L6 answer includes:** Per-region PostgreSQL (or regional Spanner) with data residency
enforced at both the data model level (user records carry a home_region field) and the network
level (VPC rules blocking cross-region database traffic for regulated tables). Global tables in a
separate low-latency store: exchange rates, fraud rules, feature flags — read-only, replicated
everywhere. Cross-region transfer as a two-phase saga: debit US account (local ACID transaction),
write pending event to outbox, coordinator credits EU account (local ACID transaction), mark
complete on success; compensating transaction reverses debit on failure. Authentication via a
global identity service storing only tokens and session metadata — no PII — so login works even
when the regional database is degraded. Users can see cached balances but cannot transact while
the region is down.

### Exercise 6: Debug a Slow Database Query

**Problem statement:** A social network's feed query takes 8 seconds. It fetches posts from
followed users and joins in author info, like counts, and comment counts.

```sql
SELECT p.id, p.content, p.created_at,
       u.username, u.avatar_url,
       COUNT(DISTINCT l.id) AS like_count,
       COUNT(DISTINCT c.id) AS comment_count
FROM posts p
JOIN users u ON u.id = p.user_id
JOIN follows f ON f.followed_id = p.user_id
LEFT JOIN likes l ON l.post_id = p.id
LEFT JOIN comments c ON c.post_id = p.id
WHERE f.follower_id = :current_user_id
  AND p.created_at > NOW() - INTERVAL '7 days'
GROUP BY p.id, u.username, u.avatar_url
ORDER BY p.created_at DESC
LIMIT 50;
```

Simulated EXPLAIN ANALYZE (key nodes):

```
Limit  (rows=50)
  Sort  (rows=250,000, cost=very_high)
    HashAggregate  (rows=250,000)
      Hash Left Join  (likes)
        Hash Left Join  (comments)
          Hash Join  (follows + posts)
            Seq Scan on posts  <-- 50M rows scanned
              Filter: created_at > NOW() - INTERVAL '7 days'
            Index Scan on follows
          Seq Scan on comments  <-- 200M rows scanned
```

**What to identify:** Why there is a Seq Scan on posts despite the date filter. Why comments is a
Seq Scan over 200M rows. Whether the query structure is causing unnecessary work. How the fix
changes the query plan.

**Hints:** Why is posts a Seq Scan even with a created_at filter? What composite index would help?
The COUNT(DISTINCT) aggregations join all likes and all comments for 250K matching posts — is
there a better architectural approach? Should like and comment counts be computed at query time,
or stored pre-aggregated?

**What an L6 answer includes:** The primary problem is the Seq Scan on posts. There is no index
that includes both user_id (from the follows join) and created_at (from the WHERE clause). A
composite index on posts (user_id, created_at DESC) allows an Index Scan, dramatically reducing
rows examined. The secondary problem is the COUNT(DISTINCT) aggregations — joining all 200M
comments and all likes for 250K posts is a disguised full-table scan. The architectural fix:
maintain a post_stats table (post_id, like_count, comment_count) updated via triggers or an
event-driven worker. Replace both Left Joins with a single JOIN on post_stats. The aggregation
disappears from the query entirely. Result: 8 seconds to under 100ms. The plan goes from Seq
Scans and HashAggregate to Index Scans and a single small join. Secondary improvement: a partial
index on posts WHERE created_at > NOW() - INTERVAL '30 days' keeps the index compact and
highly selective as the table grows.

---

## 4. Quick Reference Card

Use this before any system design interview to refresh your memory on database choices. The two
most common mistakes in interviews are (1) picking PostgreSQL for everything out of habit, and
(2) picking a specialized database like Cassandra or DynamoDB to sound impressive without being
able to justify why. This table exists to prevent both. Know the "When NOT to Use" column as well
as you know the "When to Use" column — interviewers test the limits more than the capabilities.

| Database | When to Use | When NOT to Use | Real-World Examples |
|---|---|---|---|
| **PostgreSQL** | Complex queries with joins. Strong consistency and ACID transactions. Moderate write load under 50K writes/sec. Clear relational schema. | Ultra-high write throughput at millions of rows/sec. When horizontal sharding is the starting requirement. When schema-free flexibility is genuinely needed. | Shopify (orders), GitHub (repositories), Uber (core data, historically) |
| **MySQL** | Same use cases as PostgreSQL. Common in LAMP stacks. Strong replication ecosystem and wide hosting support. | Same limitations as PostgreSQL. Weaker JSON and full-text search versus PostgreSQL. | Facebook (social graph, historically), WordPress, Twitter (core data, historically) |
| **MongoDB** | Document-centric data with significantly variable schema. Nested hierarchical data accessed together. Rapid prototyping. Content management. | Frequent multi-document ACID transactions. Highly relational data. Analytical aggregations spanning many fields. | Craigslist (listings), Forbes (CMS), product catalogs with variable attributes |
| **DynamoDB** | Key-value and simple access patterns at massive scale. Serverless and auto-scaling. Single-digit millisecond latency. Access patterns known at design time. | Complex queries and ad-hoc analytics. Unknown access patterns. Many secondary indexes needed. | Amazon shopping cart, Lyft ride tracking, Duolingo (streaks) |
| **Cassandra** | Very high write throughput — millions of writes/sec. Wide-column data by partition key. Multi-region active-active writes. Append-heavy time-series patterns. | Strong consistency requirements. Complex queries with arbitrary filters. Frequent updates to the same rows. | Netflix (viewing history), Discord (messages, historically), Instagram (activity feeds) |
| **Redis** | Caching, session storage, rate limiting, real-time leaderboards, Pub/Sub, distributed locks, counters. | Primary storage for large datasets (memory is expensive). Complex relational queries. Data too large to fit in memory affordably. | Twitter (timeline cache), GitHub (sessions), Stack Overflow (query caching) |
| **Elasticsearch** | Full-text search. Log analytics. Faceted search with complex filters. Aggregation on text fields. Search-as-you-type. | Primary operational data store. Strong consistency reads. Simple key-value lookups (overkill). High-frequency per-record updates. | GitHub (code search), Netflix (content search), Wikipedia (article search) |
| **Cloud Spanner** | Globally distributed relational data needing horizontal scale AND strong consistency. Multi-region ACID transactions. When manual sharding is too complex to operate. | Single-region workloads (cost is high). When eventual consistency is acceptable. | Google Ads, Snap, Goldman Sachs (financial data at global scale) |
| **CockroachDB** | PostgreSQL-compatible syntax with horizontal scaling. Multi-region strong consistency without GCP lock-in. When you need Spanner-like guarantees on any cloud. | Single-node workloads (distributed overhead not justified). When eventual consistency is acceptable. Very latency-sensitive single-row operations. | Bose, Comcast, DoorDash (regional data compliance) |

---

## 5. Chapter Summary: Key Takeaways

The ten rules below are the most important ideas from this chapter. These are not shortcuts or
formulas to memorize. They are principles — once you internalize them, you can derive the right
answer to a question you have never seen before. That is what L6 actually looks like: principled
reasoning under uncertainty, not pattern-matching to memorized solutions.

**1. Access patterns, not data shape, determine your database choice.**
Ask how data will be read and written before asking what it looks like. The shape of the data
tells you almost nothing. The query patterns tell you everything.

**2. Indexes are not free.**
Every index speeds up reads and slows down writes. Add an index for a known, frequent query, never
speculatively. Know when a covering index eliminates heap access entirely, and when composite
index column order changes the query plan from good to terrible.

**3. Eventual consistency has a number attached to it.**
"Eventually consistent" means nothing until you define the acceptable lag. 10 milliseconds and
30 seconds are both "eventual" but they produce completely different designs. Always put a number
on it and ask whether the user experience is acceptable at that lag.

**4. Sharding is a last resort, not a first instinct.**
Vertical scaling, read replicas, connection pooling, caching, and table partitioning solve most
scaling problems without the complexity of sharding. Shard only after exhausting simpler options,
and plan for resharding from the day you shard.

**5. Schema migrations are multi-step, multi-day processes.**
Any migration on a large live table must follow the expand/contract pattern: add new, backfill,
transition application code, remove old. A one-step ALTER TABLE on a 500M row table causes an
outage. Tools like gh-ost exist because this is hard. Use them.

**6. Your cache invalidation strategy is more important than your caching strategy.**
Anyone can put Redis in front of a database. The hard part is deciding what to invalidate, when,
and how to handle the gap between invalidation and re-population. Design this explicitly, not as
an afterthought.

**7. Design for failure before it happens.**
Define RPO and RTO for each database before you need them. Build the failover procedure. Test it.
A failover that has never been tested will fail at the worst possible moment. This is not paranoia
— it is professionalism.

**8. Shared databases between services are a long-term tax.**
Every schema change in a shared database requires coordinating all owning services. Service-owned
databases with API contracts are harder to build initially but dramatically cheaper to evolve.
Every time you accept a shared database, you take on a debt that compounds with team size.

**9. Pre-aggregation beats real-time aggregation for read-heavy analytics.**
Computing COUNT, SUM, or RANK across hundreds of millions of rows at query time is expensive and
fragile. Write aggregated results to a summary table. Accept that the counts are slightly stale —
they almost always are in production, and no user can distinguish a like count updated in real
time from one updated every 30 seconds.

**10. Data integrity requires both database guarantees and application vigilance.**
ACID ensures writes are atomic and durable. It cannot prevent application code from writing
logically wrong data that looks valid to the database. Add checksums for critical records. Build
reconciliation jobs to catch drift between systems. Use idempotent write patterns to prevent
duplicates from retries. Trust but verify — especially after a database restore.

---

### A Final Note

Database questions in L6 interviews are ultimately engineering judgment questions. The interviewer
is not testing whether you know that DynamoDB has 3,000 RCU per partition or that PostgreSQL 11
added instant column defaults. They are testing whether you make good decisions under constraints
— whether you ask the right clarifying questions, whether you surface the tradeoffs without
prompting, and whether you communicate your reasoning in a way that makes other engineers want
to build with you.

The facts matter. You need to know them. But the facts are table stakes. The judgment is what
gets you the offer. Go build something and make mistakes. Then come back to this chapter and the
mistakes will mean more.

---

*End of Chapter 28 — Databases: Choosing, Using, and Evolving Data Stores*
## Supplemental Brainstorming: Chapter 28 — Databases

*Questions 26-50: Complete topic coverage and cross-chapter connections.*

---

### How to Use This Supplement

Chapter 28 introduced the foundational database selection framework and covered basic relational vs NoSQL tradeoffs, ACID properties, indexing strategy, and sharding. These 25 additional questions go deeper into mechanics and connect databases to the surrounding architecture.

Section A (Q26-Q35) stays inside the database engine itself: concurrency control, storage internals, query planning, connection management, schema evolution, and contention patterns. These are the questions that separate candidates who "know databases" from candidates who understand why databases behave the way they do under load.

Section B (Q36-Q50) zooms out to cross-system design: how your database choice interacts with your caching layer (Ch31/32), your event-driven architecture (Ch33), your batch pipeline (Ch35), your multi-region topology (Ch36), your compliance posture (Ch37), and your cost model (Ch38). A staff engineer is expected to reason about these connections without prompting.

For each question, the bullet points are the things you need to cover in an interview answer. The Follow-up is the harder variant that probes whether you understand the limits of the approach — interviewers at the staff level almost always push on the follow-up.

---

### Section A: Advanced DB Mechanics (Q26-Q35)

**Question 26 — MVCC and Long-Running Transactions**

You are running PostgreSQL for a SaaS app with 500 concurrent users. A developer left a transaction open for 45 minutes during a debug session. Other users start reporting slow queries and table bloat. Your DBA says "MVCC is leaking." Explain what is happening and how you fix it.

- Explain how MVCC works: each row version is stamped with a transaction ID (xmin for creation, xmax for deletion); readers see a consistent snapshot corresponding to their transaction start time without blocking writers; writers create new row versions rather than overwriting in place; the old version stays on disk until it is no longer visible to any active transaction.
- Explain the bloat problem: PostgreSQL's autovacuum process normally reclaims dead tuple space; but autovacuum cannot remove a dead tuple if any active transaction predates it (because that old transaction might still need to read the old version); a transaction open for 45 minutes holds back the "oldest transaction horizon" for the entire cluster — autovacuum is blocked from cleaning any table, not just the one being queried.
- Explain the symptoms: table file sizes grow even though row counts stay flat; EXPLAIN shows sequential scans running across bloated pages that are mostly dead tuples; query times increase because the I/O cost of reading a bloated page is the same as reading a full one.
- Describe the fix: detect long-running transactions with SELECT * FROM pg_stat_activity WHERE state = 'idle in transaction' AND query_start < NOW() - INTERVAL '5 minutes'; set idle_in_transaction_session_timeout = '5min' at the cluster level to auto-terminate abandoned sessions; set statement_timeout for normal workloads; tune autovacuum_vacuum_cost_delay and autovacuum_naptime to be more aggressive on high-write tables.
- Follow-up: A product manager says "we need to support BI queries that run for 2 hours on production." How does that requirement change your autovacuum and bloat management strategy? (Answer: use a read replica or logical replication target for long BI queries; never run hour-long analytics on the OLTP primary. If the replica runs the long query, it bloats only its own tables, not the primary's.)

---

**Question 27 — MVCC Snapshot Isolation vs Serializable**

Your fintech app needs to prevent a double-booking race condition on a shared resource. A junior engineer says "we're already using PostgreSQL with MVCC, so we're safe from dirty reads." Explain why MVCC snapshot isolation alone does not prevent all anomalies and how you would get true safety.

- Explain the anomaly MVCC does NOT prevent under READ COMMITTED or REPEATABLE READ: write skew — two transactions each read a value, neither sees the other's write, both commit a change that together violate a business rule (e.g., two surgeons both see "1 surgeon on call" and both go off-call, leaving 0).
- Explain the two remedies: use SERIALIZABLE isolation level (PostgreSQL's SSI uses optimistic concurrency and aborts conflicting transactions), or use explicit row-level locking with SELECT FOR UPDATE to convert the pattern to pessimistic locking.
- Explain the cost tradeoff: SERIALIZABLE adds CPU overhead and raises the abort/retry rate; SELECT FOR UPDATE serializes access but creates a bottleneck on hot rows.
- Follow-up: Your P99 latency spikes 3x after switching to SERIALIZABLE. Profile the abort rate. How do you tune the retry logic so that application-level retries do not cause a thundering herd?

---

**Question 28 — WAL and Crash Recovery**

Your PostgreSQL primary crashes mid-transaction during a bulk insert of 500,000 rows. Operations tells you the instance is back up. A junior engineer asks: "Do we need to re-run the insert? Was data lost?" Walk through exactly what WAL guarantees and what happens at startup.

- Explain WAL structure: every database change — INSERT, UPDATE, DELETE, even internal catalog changes — is written to the write-ahead log as a sequential, append-only record before the change is applied to data pages in the shared buffer cache; this sequence is the reason PostgreSQL can survive a crash without corrupting the database; if the crash happens after the WAL record is written but before the data page is flushed to disk, the WAL record is the authoritative source of truth.
- Explain checkpoints: periodically (controlled by checkpoint_timeout and max_wal_size), PostgreSQL forces all dirty buffer cache pages to disk and writes a checkpoint record to the WAL; at startup after a crash, PostgreSQL only needs to replay WAL from the most recent checkpoint, not from the beginning of time; shorter checkpoint intervals mean less WAL to replay but more I/O during normal operation.
- Explain crash recovery step by step: PostgreSQL reads the control file to find the last checkpoint location; it replays WAL records forward from that point; committed transactions that had not yet been flushed to data pages are re-applied (redo); uncommitted transactions (those without a COMMIT record in the WAL) are rolled back (undo, via the abort records); the database ends in a consistent state at the point of the last committed transaction before the crash.
- Explain what was lost in this case: the bulk insert had not committed (no COMMIT record in WAL), so it is rolled back entirely; those 500,000 rows do not exist; re-run the insert.
- Explain WAL in replication: read replicas stream WAL from the primary and apply it continuously; at any given moment, the replica is N bytes of WAL behind the primary; this is the source of replica lag discussed in Question 33.
- Follow-up: The operations team wants faster crash recovery. They propose increasing checkpoint_completion_target and checkpoint_timeout to reduce checkpoint I/O. Explain the direct tradeoff: longer checkpoint intervals mean more WAL to replay on crash, so recovery takes longer; the correct tuning depends on your RTO requirement (how long can you be down after a crash) versus your tolerance for checkpoint I/O overhead during normal operation.

---

**Question 29 — B-Tree vs LSM-Tree for Your Workload**

You are designing the storage engine selection for a new IoT telemetry system. The system will ingest 100,000 sensor readings per second and serves time-series queries where users ask "show me readings from device X over the last 24 hours." Design the storage engine selection. Justify B-Tree or LSM-Tree.

- Explain the B-Tree write problem:
  each insert into a B-Tree may require a random I/O to locate the correct leaf page, then a page rewrite;
  at 100K writes/second, random I/O exhausts disk bandwidth on spinning disks and creates write amplification even on SSDs;
  B-Trees are optimized for reads (balanced tree, O(log N) lookup), not for insert-heavy workloads.
- Explain LSM-Tree write advantage:
  writes go into an in-memory buffer (memtable), then flush sequentially to disk as sorted string tables (SSTables);
  sequential I/O is 10-100x faster than random I/O on both HDDs and SSDs;
  this is why LevelDB, RocksDB, and Cassandra use LSM-Trees for write-heavy workloads;
  compaction merges SSTables in the background and reclaims space from old versions.
- Explain the LSM-Tree read cost:
  range reads require merging multiple SSTable levels (potentially many files);
  point reads may require checking multiple SSTable levels before finding the correct version;
  Bloom filters let the engine skip SSTables that definitely do not contain the key, significantly reducing unnecessary I/O;
  but for highly selective reads across many files, the overhead is still higher than a B-Tree index.
- Explain the recommendation:
  for this workload (high write throughput + time-range reads organized by device + time), use an LSM-Tree engine;
  options include RocksDB (embedded), ScyllaDB (distributed), or a purpose-built TSDB like InfluxDB, TimescaleDB, or Prometheus for metrics;
  avoid a plain B-Tree relational DB as the primary telemetry store at 100K writes/second.
- Follow-up:
  The product adds a feature: "show me the current value (latest reading) for each device" — this is a high-cardinality point read pattern.
  How does that requirement change the LSM-Tree read cost calculation?
  (Answer: if there are 1 million devices and users frequently query the latest value for random devices, Bloom filters help but read amplification on LSM-Tree becomes noticeable; consider maintaining a separate "current state" table in a B-Tree store like PostgreSQL, updated via streaming from the LSM-Tree ingestion path — two stores for two access patterns.)

---

**Question 30 — Query Planner Behavior and Index Selection**

A query that used to run in 20ms now takes 8 seconds after your team ran a large data backfill that added 50 million rows to a table. The query has an index on user_id. The DBA runs EXPLAIN ANALYZE and sees the planner chose a sequential scan. Explain what happened and how you fix it.

- Explain how the query planner works:
  PostgreSQL uses table statistics (row count, data distribution histograms, column correlation with physical order) maintained by ANALYZE to estimate the cost of each possible execution plan;
  it models I/O cost, CPU cost, and estimated rows returned for each plan, then chooses the lowest-cost option;
  the statistics are stored in pg_statistic and summarized in pg_stats; they go stale when large amounts of data are inserted without a subsequent ANALYZE.
- Explain why the planner chose sequential scan after the backfill:
  two possibilities: (1) statistics are stale — the planner still thinks the table has 5 million rows (not 55 million) so it underestimates the cost of a sequential scan and compares it incorrectly to an index scan;
  (2) statistics are correct — the WHERE user_id = 1 clause matches 30% of the table (because user_id = 1 is a superuser with data in every partition), and for a 30% row fraction a sequential scan genuinely IS faster than an index scan due to random I/O overhead.
- Explain the fix path:
  step 1: run ANALYZE tablename to update statistics immediately; re-run EXPLAIN ANALYZE and see if the plan changes;
  step 2: if the plan does not change, use EXPLAIN (ANALYZE, BUFFERS) to see the actual vs estimated row counts; if they are wildly different, the statistics need improvement (increase default_statistics_target for that column);
  step 3: if the row fraction is legitimately high, the sequential scan is correct; rethink the query (partition pruning, partial index on a more selective condition, or query rewrite).
- Follow-up:
  A developer says "I'll just add pg_hint_plan to force the index."
  When is forcing a plan a good idea vs a dangerous workaround?
  (Answer: forcing an index is useful for short-term diagnosis and as a temporary fix when you know the planner is wrong due to a specific statistics bug; it is dangerous as a permanent measure because query hints do not adapt to changing data distributions — a hint that is correct today may cause a 100x slowdown when the data changes next month; fix the statistics instead.)

---

**Question 31 — Connection Pooling Limits and Failure Modes**

Your Node.js API service has 200 pods. Each pod opens up to 10 database connections. Your PostgreSQL instance has max_connections = 500. During a traffic spike, the 201st pod starts and connections are refused. Describe the problem and design a solution.

- Explain why PostgreSQL has connection limits: each connection is a forked OS process (in PostgreSQL's default process-per-connection model); each process requires memory for its own stack, shared memory structures, and query working memory; a rule of thumb is 5-10MB per connection; at 2,000 connections the DB server is spending 10-20GB on connection overhead before serving a single query; this causes memory pressure, increased context switching, and throughput collapse.
- Explain why the app-level pool does not solve it: each pod maintains its own pool; the pool is not shared across pods; with 200 pods x 10 connections, the total server-side connection count is 2,000 regardless of how few are active at any moment; Kubernetes autoscaling makes this worse — every new pod immediately opens its full pool.
- Explain PgBouncer in transaction pooling mode: PgBouncer sits between the application and PostgreSQL; applications connect to PgBouncer (which accepts thousands of connections cheaply, as it is a single process with lightweight sockets); PgBouncer maintains a small pool of real PostgreSQL server connections (e.g., 100); each time an application executes a transaction, PgBouncer borrows a server connection, runs the transaction, and immediately returns it to the pool; at any moment, the PostgreSQL server sees only 100 connections regardless of how many application pods are running.
- Explain the tradeoff: transaction pooling breaks session-level PostgreSQL features because the session is not persistent — SET LOCAL, advisory locks, prepared statements, and LISTEN/NOTIFY all assume a stable session; frameworks that rely on these (some ORMs, some queue libraries) need modification or must use statement pooling mode instead (which is less efficient but preserves sessions).
- Explain the failure mode without PgBouncer: under a sudden traffic spike, all pods try to open their full pool simultaneously; PostgreSQL hits max_connections; new connections are refused with "FATAL: sorry, too many clients already"; the application throws 500 errors; this is a connection storm and it can cascade into a full outage even when the database itself is healthy.
- Follow-up: Your team deploys PgBouncer but now you see "prepared statement does not exist" errors. What specifically breaks and how do you configure PgBouncer to avoid it? (Answer: prepared statements are created in a server session and referenced by name; in transaction pooling mode, the server session changes between transactions so the prepared statement is gone; fix by disabling server-side prepared statements in your ORM or by switching to statement pooling mode for those specific connections.)

---

**Question 32 — Zero-Downtime Schema Migrations**

Your team needs to add a NOT NULL column with no default to a 500-million-row PostgreSQL table. A junior engineer opens a migration in their ORM that runs ALTER TABLE ADD COLUMN with a DEFAULT. The staging run takes 8 minutes and locks the table. Explain what is happening and design the production-safe migration.

- Explain the lock behavior: in older PostgreSQL versions, adding a column with a DEFAULT required rewriting the entire table, which holds an exclusive lock for the duration; on a 500-million-row table this means 8+ minutes of write (and sometimes read) lock, causing downtime.
- Explain the modern behavior: PostgreSQL 11+ handles ADD COLUMN with a non-volatile DEFAULT without a table rewrite (it stores the default in the catalog); but NOT NULL + no default still requires constraints; and backfills on existing rows are still expensive.
- Explain the zero-downtime migration pattern: (1) add the column as nullable with no default — this is instant; (2) backfill in small batches (UPDATE ... WHERE id BETWEEN x AND y LIMIT 1000) with sleep between batches to avoid lock contention; (3) add the NOT NULL constraint using NOT VALID (validates only new rows immediately); (4) validate the constraint in a separate transaction (VALIDATE CONSTRAINT) which holds a weaker lock; (5) drop the old default if needed.
- Follow-up: Your ORM (e.g., Rails, Django) does not support this multi-step migration natively. How do you enforce this pattern across a team of 20 engineers who run auto-generated migrations?

---

**Question 33 — Read Replica Lag and Stale Reads**

Your e-commerce checkout page reads a user's wallet balance from a PostgreSQL read replica. After a purchase, the balance sometimes shows the old (pre-purchase) value for a few seconds. Customer support is getting complaints. Design the fix without adding a cache.

- Explain the source of lag:
  read replicas receive the WAL stream from the primary and apply it asynchronously;
  in the interval between the primary committing the purchase transaction and the replica applying the corresponding WAL records,
  any read from the replica returns the pre-purchase balance;
  typical lag on an idle replica is under 100ms, but under load or during a long-running replica vacuum, lag can reach seconds or minutes.
- Explain Option A — read-after-write routing from primary:
  identify the specific page loads that immediately follow a user-initiated write (purchase confirmation page, balance display after transfer);
  route those specific reads to the primary instead of a replica;
  all other reads (browse history, product listings) continue to use replicas;
  implement via session tagging: after a write, mark the session with recently_wrote = true and a timestamp; read routing logic checks this flag.
- Explain Option B — synchronous replication:
  configure synchronous_standby_names in PostgreSQL to require at least one replica to acknowledge WAL receipt before the primary commits;
  this eliminates replication lag for the designated synchronous replica;
  the tradeoff: write latency increases by the replica round-trip time (typically 1-5ms on the same data center network);
  availability risk: if the synchronous replica goes offline, writes block until the replica returns or is removed from the standby list.
- Explain Option C — monotonic read tokens (causal consistency):
  when a write commits, return a log sequence number (LSN) to the client;
  on subsequent reads, the client sends the LSN; the replica checks its own applied LSN;
  if the replica is behind the client's LSN, the application retries the read from the primary;
  this is the basis for "read your writes" consistency without forcing all reads to the primary.
- Follow-up:
  At what point does stale read handling become a distributed systems problem rather than a PostgreSQL configuration problem?
  (Answer: when replication spans multiple data centers with 50-150ms inter-region latency — at that point synchronous replication doubles write latency; you need to reason in terms of the CAP theorem and decide explicitly between consistency and availability; this is the transition from "database tuning" to "distributed systems design.")

---

**Question 34 — Hot Row and Hot Partition Problems**

Your social platform has a "like" counter on viral posts. The posts table has a likes column that 50,000 users are incrementing simultaneously. The DB CPU is at 95% and P99 latency is 2 seconds. Diagnose and redesign.

- Explain the hot row problem: UPDATE posts SET likes = likes + 1 WHERE id = X requires an exclusive row lock; every concurrent UPDATE must wait for the previous one to release; even though the lock is brief, 50,000 concurrent waiters create a queue that serializes what should be parallel work.
- Explain Solution A — write-side fan-out with aggregation: instead of updating the post row directly, append like events to a separate likes_events table (INSERT is append-only, no locks); a background job aggregates the count periodically and writes back to the post; the post's like count is "approximately current" but never causes lock contention.
- Explain Solution B — counter sharding: maintain N counter shards (e.g., 16 rows in a post_like_shards table, each with a partial count); each write randomly picks a shard; reads SUM all shards; this reduces hot row contention by 16x while keeping data consistent.
- Explain Solution C — move to a counter-native store: use Redis INCR for real-time counts (atomic, no locking needed at the DB level) and periodically sync back to the relational DB for persistence and reporting.
- Follow-up: The product team says the like count must be exactly correct for financial/legal reasons. How does that constraint eliminate Solution A (eventual aggregation) and force you to pick between B and C?

---

**Question 35 — Optimistic vs Pessimistic Locking Selection**

Your project management tool has a document editor where two users occasionally edit the same task description simultaneously. You need to prevent lost updates. A senior engineer proposes optimistic locking; a team lead proposes pessimistic locking. Walk through when each is correct and design the implementation for this specific case.

- Explain the lost update problem: User A reads the task description at 10:00:00; User B reads the same description at 10:00:01; User A saves their edits at 10:00:30 (the row now has their changes); User B saves their edits at 10:00:45, overwriting User A's changes completely; User A's edits are silently lost; neither user knows this happened.
- Explain pessimistic locking — implementation: the first user to open the editor runs SELECT id, description FROM tasks WHERE id = X FOR UPDATE; the FOR UPDATE clause acquires an exclusive row lock that is held until the transaction commits; the second user's SELECT FOR UPDATE blocks until the first user saves (commits) or their session ends; the second user then sees the updated row; this guarantees no lost updates.
- Explain pessimistic locking — the problem: web application sessions are not database transactions; users hold browser tabs open for minutes or hours; you cannot hold a database transaction open that long (connection pooling, idle timeouts, MVCC bloat); you must simulate locking at the application layer with a "currently_editing_by" column and a heartbeat mechanism; this is complex and still fails when users abandon tabs.
- Explain optimistic locking — implementation: add a version INTEGER column to the tasks table; when User A reads the task, they also read version = 5; when User A saves, the UPDATE is: UPDATE tasks SET description = 'A''s edit', version = version + 1 WHERE id = X AND version = 5; if the version has changed (User B saved first, version is now 6), the UPDATE affects 0 rows; the application checks rows affected and returns a 409 Conflict to User A, asking them to reload and re-apply their edits.
- Explain when optimistic is right: when conflicts are rare (low-contention workloads — most web apps); when sessions are stateless (HTTP); when the cost of a retry is low; when you cannot hold DB transactions open for the duration of user "think time."
- Explain when pessimistic is right: when conflicts are frequent and retries are expensive (e.g., seat booking where retrying means re-running complex pricing, availability, and payment logic); when the business rule is "exactly one winner with no user-visible conflict" (the second user must be told immediately that the seat is taken, before they enter payment details).
- Follow-up: Your API is now a mobile app that can lose connectivity mid-edit for 10 minutes. How does that change the locking strategy? (Answer: optimistic locking with a three-way merge strategy becomes necessary — store the base version the user started editing, the user's edits, and the current server version; attempt a textual merge; optimistic locking with a hard conflict rejection is too aggressive when the user spent 10 minutes offline editing.)

---

---

### Section B: Cross-Chapter Integration (Q36-Q50)

The questions in this section require you to connect your database knowledge to adjacent architectural concerns. In a real staff engineering interview, these scenarios are more common than pure database questions. The interviewer is not testing whether you know PostgreSQL internals — they are testing whether you know when to reach past the database for a different tool, and whether you understand the failure modes that emerge at the boundaries between systems.

For each cross-chapter question, the chapter reference is not decoration — it identifies the specific concept from that chapter that is essential to a correct answer. If you have not read the referenced chapter yet, make a note and return to this question after you have.


**Question 36 — Database Anti-Pattern: DB as a Queue (Ch28 + Ch33)**

A team uses a PostgreSQL jobs table as a task queue. Workers poll with SELECT ... WHERE status = 'pending' FOR UPDATE SKIP LOCKED. At 10 workers and 1,000 jobs/minute, it works. At 100 workers and 50,000 jobs/minute, the table has 20 million rows and performance collapses. Diagnose and redesign. Reference Chapter 33 (event-driven architecture) in your answer.

- Diagnose the failure modes: polling creates constant read load even when the queue is empty; the jobs table grows to millions of rows and index scans degrade; SKIP LOCKED helps contention but does not eliminate it at scale; running DELETE or UPDATE on completed jobs creates table bloat.
- Explain why PostgreSQL is the wrong tool: relational databases optimize for durability and query flexibility, not for the high-throughput, low-latency, ordered delivery semantics of a message queue; you are fighting the tool.
- Explain the migration path to Kafka (Ch33): replace the jobs table with a Kafka topic; producers publish job messages; consumers read from partitions; Kafka handles backpressure, replay, consumer group coordination, and retention automatically; the relational DB is freed for its actual purpose.
- Explain what to keep in the DB: job metadata for human inspection, audit trails, and status dashboards — write these after processing, not as the coordination mechanism.
- Follow-up: The team says "Kafka is operationally complex, we don't have the expertise." What is the correct intermediate step? (Answer: use a purpose-built job queue like Sidekiq+Redis or a managed service like SQS — both are simpler than Kafka and still correct for this workload.)

---

**Question 37 — Polyglot Persistence Design (Ch28 + Ch33)**

You are redesigning a monolith e-commerce app that currently uses a single PostgreSQL database. The new architecture will use PostgreSQL for orders, Elasticsearch for product search, Redis for sessions and cart, and S3 for product images. A stakeholder asks: "How do you keep all of these in sync?" Design the synchronization architecture. Reference Chapter 33 (event-driven architecture).

- Explain why polyglot persistence requires an explicit synchronization strategy: each store has its own consistency model; a write to PostgreSQL does not automatically propagate to Elasticsearch; naive dual-writes (write to both in application code) create partial-failure scenarios where one store updates and the other does not.
- Explain the event-driven synchronization pattern (Ch33): write to PostgreSQL as the system of record; use change data capture (CDC via Debezium or logical replication) to emit change events to Kafka; downstream consumers update Elasticsearch, Redis, and other stores from the Kafka stream; this makes PostgreSQL authoritative and other stores eventually consistent.
- Explain failure handling: if the Elasticsearch consumer falls behind or crashes, it replays from the Kafka offset; the system is eventually consistent, not immediately consistent; design the product search page to tolerate a brief delay between a product update and its appearance in search results.
- Explain what NOT to sync: session data in Redis is ephemeral — do not sync it back to PostgreSQL; images in S3 are immutable blobs — reference them by URL from PostgreSQL, do not duplicate.
- Follow-up: A product manager says "we need real-time search index updates — products must appear in search within 500ms of being published." How does that SLA change your CDC pipeline design? (Answer: prioritize the CDC consumer, reduce Kafka batch intervals, and add monitoring on consumer lag with an alert threshold.)

---

**Question 38 — Read Replicas vs Caching Tradeoffs (Ch28 + Ch31/Ch32)**

Your PostgreSQL-backed API serves 80% reads and 20% writes. You are at 80% read capacity. Your team debates: add two read replicas vs add a Redis cache layer. Walk through the complete decision tree. Reference Chapters 31 and 32 (caching). When does caching NOT solve the problem?

- Explain what read replicas do: each replica receives a copy of the WAL stream and applies it asynchronously; read queries are routed to replicas, distributing the I/O and CPU load; the primary handles all writes plus any reads that require fresh data; replicas are bounded by the same query patterns as the primary — a slow query on the primary is also slow on a replica; adding replicas scales read throughput linearly but does not make individual queries faster.
- Explain what Redis caching does (Ch31/32): serve repeat reads from memory without touching the DB at all; for highly cacheable data (product catalog, user profiles, reference data that changes rarely), cache hit rates of 90%+ can reduce DB read load by 10x; a single Redis node can serve 100K+ operations per second from memory; it is orders of magnitude cheaper per QPS than an additional PostgreSQL replica (no SQL parsing, no disk I/O, no query planning).
- Explain when caching does NOT solve the problem: (1) low cache hit rate — if every user reads unique data (e.g., personalized activity feeds, per-user financial statements, live sensor data), the cache miss rate is near 100% and caching adds latency without reducing DB load; (2) writes are the bottleneck — you are at 80% read capacity; if the write load is also high and causing primary CPU saturation, caching reads helps but does not touch the write path; (3) data freshness requirements are strict — caches introduce staleness controlled by TTL; for financial balances, inventory counts, or medical records, a stale cache read can cause real harm; (4) cache invalidation complexity — if the same piece of data is written from many places, keeping the cache consistent with the DB requires invalidation logic in every write path; missed invalidations cause stale reads silently.
- Explain the diagnostic first step: measure your actual cache hit rate potential before adding Redis; look at your query log and count how many distinct cache keys would be generated; a query for a product detail page by product_id has one key per product — highly cacheable; a query that filters by 12 user-specific parameters generates a unique key per user-request combination — not cacheable.
- Explain the decision framework: if cache hit rate projection is above 70%, add Redis first — it is faster to provision, cheaper, and can absorb the majority of the read load before you need replicas; if cache hit rate is below 50%, add read replicas first because replicas work for all reads regardless of data shape.
- Follow-up: You add Redis and achieve 85% cache hit rate, but P99 latency is still 800ms. The bottleneck has shifted to the 15% of uncached queries. Diagnose the next step. (Answer: that 15% is your most expensive queries — run EXPLAIN ANALYZE on the slowest ones; they likely lack indexes or do large joins; optimize indexes first; add a read replica specifically for those queries if needed; consider whether those queries belong in the OLTP path at all or should be pre-computed.)

---

**Question 39 — Denormalization for Performance**

Your user profile page makes 7 SQL joins to render: user, address, subscription, last_login, feature_flags, payment_method, and notification_preferences. The page loads in 450ms. The product team wants 200ms. Explain when denormalization is the right answer and design the approach.

- Explain the cost of joins: each join in a relational DB requires the query planner to evaluate multiple access paths; with 7 joins, even with good indexes, the planner must coordinate 7 table accesses; on a table with millions of users and foreign key relationships across multiple schemas, join costs compound.
- Explain denormalization options: (A) create a user_profile_view materialized view that pre-computes the join; refresh it on a schedule or on write events; reads become a single-table scan; (B) maintain a user_profile document in a document store (MongoDB, DynamoDB) as a read-optimized projection, updated whenever any of the 7 source tables change; (C) use PostgreSQL JSONB to store a snapshot of the full profile alongside the user row and update it via triggers or CDC.
- Explain the tradeoff: denormalization trades write complexity for read speed; now every write to any of the 7 source tables must update the denormalized store; you must handle the case where the update fails (partial consistency); this is acceptable for display data but dangerous for financial or legal records.
- Follow-up: The notification_preferences table changes 200 times per second (users toggling settings). How does that write frequency affect the viability of the materialized view approach? (Answer: high-frequency writes to source tables make synchronous materialized view refresh expensive; you need async refresh with an acceptable staleness window, or move to a document store with write-through updates.)

---

**Question 40 — DB Internals: Page Splits and Write Performance (Ch28 + Ch29)**

Your PostgreSQL is slow on writes. The DB internals team says it is B-Tree page splits. Design the fix. How does switching to an LSM-Tree engine (e.g., RocksDB) change the trade-off? Reference Chapter 29 (database internals).

- Explain B-Tree page splits (Ch29): B-Tree leaf pages have a fixed size (typically 8KB in PostgreSQL); when a page is full and a new entry must be inserted in the middle, the page splits into two half-full pages; the parent must be updated; in worst case, splits cascade up the tree; each split is a random I/O write — expensive at high write throughput.
- Explain when page splits are worst: monotonically increasing keys (e.g., auto-increment IDs) cause splits only at the rightmost leaf, which is actually the best case; UUIDs or random keys cause splits throughout the tree, creating fragmentation and write amplification.
- Explain the B-Tree fix options: use sequential IDs instead of random UUIDs to minimize mid-tree splits; run CLUSTER periodically to rebuild the index in physical order; increase fill factor (FILLFACTOR = 70) so pages have headroom for inserts before splitting; use BRIN indexes instead of B-Tree for append-only time-series data.
- Explain the LSM-Tree alternative (Ch29): RocksDB writes go to a memtable first (in-memory, no random I/O); flushes to disk are sequential; compaction handles merging; there are no page splits; write amplification shifts from random I/O to sequential compaction I/O, which is dramatically cheaper on modern SSDs; the tradeoff is higher read amplification for point reads.
- Follow-up: Your workload is 70% writes, 30% random point reads. At what write rate does the LSM-Tree advantage outweigh its read cost disadvantage? How do you benchmark this for your specific hardware?

---

**Question 41 — GDPR Deletion Across Relational Tables (Ch28 + Ch37)**

GDPR requires you to delete EU user data within 30 days of a deletion request. Your schema has EU user data in 12 tables with foreign key relationships. Referential integrity constraints cascade deletes but the cascade takes 45 seconds and locks rows. Reference Chapter 37 (data locality and compliance) in your design.

- Explain the cascade lock problem: DELETE FROM users WHERE id = X triggers cascading deletes across all FK-linked tables; each cascade holds row locks; if any child table is large (e.g., 500M events), the cascade runs a full table scan and holds locks for 45+ seconds, degrading production.
- Explain the soft-delete + async purge pattern: instead of hard-deleting immediately, mark the user as deleted_at = NOW() (soft delete); the user is immediately invisible to the application; a background job then runs the actual deletions in batches during off-peak hours with rate limiting (e.g., 1,000 rows per second per table); this satisfies GDPR's 30-day window while avoiding production lock contention.
- Explain the data-at-rest anonymization alternative (Ch37): instead of deleting rows, overwrite PII columns with nulls or random values (cryptographic erasure); the row remains for relational integrity and audit purposes but contains no personal data; this is legally valid under GDPR's "right to erasure" if no PII remains and is much faster than cascading deletes.
- Explain what Chapter 37 adds: data locality and compliance chapter covers jurisdiction-specific retention requirements; some EU regulations require audit logs of deletions themselves — design a deletion_audit table that records who was deleted, when, and which tables were affected, without containing the PII that was deleted.
- Follow-up: Legal says you also need to handle "right to portability" — export a user's data before deletion. The same 12 tables apply. Design the export pipeline that runs before the deletion job.

---

**Question 42 — Cost Model: RDS vs DynamoDB Migration (Ch28 + Ch38)**

Your RDS (PostgreSQL) bill is $15K/month. A DynamoDB migration would cost $8K/month at current load but $50K/month at 10x scale. Model the decision. When do you migrate? Reference Chapter 38 (cost efficiency).

- Explain the cost model structure (Ch38): RDS costs are fixed per instance class regardless of load (you pay for the instance whether it is at 10% or 90% utilization); DynamoDB costs are usage-based (you pay per read/write capacity unit consumed); this creates a crossover point that depends on your growth trajectory.
- Model the crossover: at current load, DynamoDB saves $7K/month; but if you reach 10x scale in 18 months, DynamoDB costs $50K vs RDS (which you might scale to, say, $30K with read replicas) — DynamoDB becomes more expensive; the break-even depends on how fast you grow.
- Explain the migration risk cost: DynamoDB requires a different data model (key-value/document, no joins, limited query patterns); migrating a relational schema to DynamoDB may require denormalization, application rewrites, and months of engineering time; account for migration cost (engineering weeks * salary) in the total cost of ownership.
- Explain the decision framework (Ch38): if you are unlikely to reach 10x scale in 2 years, DynamoDB migration saves money; if 10x scale is likely, RDS with read replicas may be cheaper at scale and avoids migration risk; the correct answer is rarely obvious without a growth model.
- Follow-up: A DynamoDB access pattern requires a Global Secondary Index (GSI) that would cost an additional $12K/month at current load. How does that change the break-even calculation? (Answer: GSIs in DynamoDB are separate throughput — they are a common cost trap; model them explicitly before committing to DynamoDB.)

---

**Question 43 — Transactions Across Event-Driven Services (Ch28 + Ch33)**

You are moving from a monolith PostgreSQL database to an event-driven architecture with Kafka. The monolith had a single transaction that (1) debits a user account, (2) credits a vendor, and (3) sends a confirmation email trigger. How do you handle transactions that span services? What happens to ACID guarantees? Reference Chapter 33.

- Explain what is lost: the single-DB ACID transaction is gone; you now have three independent services (payment service, vendor ledger service, notification service) each with their own databases; there is no distributed transaction coordinator that can atomically commit or roll back all three simultaneously; two-phase commit (2PC) across microservices exists in theory but requires all services to support the protocol, holds locks across the network during the prepare phase, and fails ungracefully when any participant is unavailable — most teams correctly reject 2PC for microservices.
- Explain the Saga pattern (Ch33): replace the ACID transaction with a Saga — a sequence of local transactions, each of which publishes an event to Kafka that triggers the next step; the choreography-based Saga has no central coordinator (each service listens to events and reacts); the orchestration-based Saga has a central Saga orchestrator that calls each service step and handles failures; for this payment flow, orchestration is safer because the orchestrator knows the full state of the transaction.
- Explain compensating transactions: if step 2 (vendor credit) fails after step 1 (account debit) has succeeded, you cannot roll back step 1 in the relational sense — it is already committed; instead, you run a compensating transaction — a separate, explicit reversal (credit the user account back); compensating transactions must be idempotent and must be retried until they succeed; design them to be safe to run multiple times.
- Explain the exactly-once problem: Kafka guarantees at-least-once delivery by default; your consumer may process the "debit account" event twice if the consumer crashes after processing but before committing its Kafka offset; design idempotent consumers — each service stores the event ID it has processed and ignores duplicates; use Kafka's transactional producer API to produce the next event and commit the offset atomically.
- Explain what ACID property you give up: Atomicity (the transaction can be in a partial state — debit done, credit pending) and Isolation (other services see the intermediate state where the user's balance is reduced but the vendor has not been credited); you retain Consistency and Durability within each local transaction; the system is eventually consistent.
- Follow-up: The confirmation email is sent by the notification service before the vendor credit fails 30 seconds later. The user received a "payment successful" email. Do you send a correction email? Design the user-facing compensation flow. (This is an explicit business decision: for small amounts, send a correction email and re-attempt; for large amounts, hold the email until the full Saga completes; the architecture must allow delaying the notification step until all prior steps have committed.)

---

**Question 44 — Separation of Analytics Batch Jobs from OLTP (Ch28 + Ch35)**

Your analytics team runs nightly batch jobs on the production PostgreSQL. The jobs run 3-hour aggregate queries that lock rows and degrade production performance. Reference Chapter 35 (batch processing) in your redesign.

- Diagnose the problem: OLAP (online analytical processing) queries — long-running aggregations over millions of rows — and OLTP (online transactional processing) queries — short, indexed lookups — have opposite access patterns; sharing one database forces them to compete for I/O, CPU, and buffer cache.
- Explain Solution A — dedicated read replica for analytics: create a PostgreSQL read replica whose only purpose is analytics queries; direct the nightly batch jobs there; the primary is not impacted; this is the lowest-cost first step.
- Explain Solution B — dedicated OLAP warehouse (Ch35): export data nightly via ETL to a columnar store (Snowflake, BigQuery, Redshift); batch jobs run there; the OLAP warehouse is optimized for aggregate queries (columnar storage, vectorized execution) and is orders of magnitude faster for analytics; the OLTP PostgreSQL is untouched.
- Explain Solution C — real-time with CDC (Ch35): instead of nightly exports, use CDC (Debezium) to stream changes continuously to the data warehouse; analytics queries are now "near real-time" (minutes of lag) rather than one day old; this is more complex but necessary if the analytics team needs intraday data.
- Explain the long-term architecture principle (Ch35): OLTP and OLAP are different problems solved by different tools; the only reason to run both on the same DB is early-stage simplicity; any system at scale should separate them.
- Follow-up: The analytics team says "we also need to write results back to PostgreSQL — the batch job computes user credit scores that the API reads." Design the write-back path without creating a circular dependency.

---

**Question 45 — Multi-Region PostgreSQL Architecture (Ch28 + Ch36)**

You need to run your PostgreSQL database across 3 regions (US, EU, APAC) to serve global users with low latency. Design the architecture. What consistency model do you choose and why? Reference Chapter 36 (multi-region systems).

- Explain the fundamental problem: PostgreSQL is a single-master system; you can have one primary and many read replicas; you cannot write to two primaries simultaneously without additional tooling; cross-region replication adds 60-150ms of latency between regions.
- Explain Option A — single primary with global read replicas (Ch36): keep the primary in US-East; replicate to EU and APAC read replicas; reads are local and fast; writes always go to US-East (high latency for EU/APAC users doing writes); this is correct when 90%+ of operations are reads.
- Explain Option B — multi-primary with conflict resolution: use Citus, YugabyteDB, or CockroachDB (all distributed SQL); writes are accepted in any region; the system replicates synchronously or asynchronously; synchronous cross-region writes add 150ms+ to every write; asynchronous risks write-write conflicts.
- Explain the consistency model choice (Ch36): for global user-facing writes, choose availability over consistency (AP in CAP terms) and design the application to handle eventual consistency; for financial data, choose consistency and accept that users writing from EU will experience higher write latency; there is no free lunch.
- Explain the practical recommendation: for most SaaS companies, keep a single primary and use regional routing to send writes to the nearest replica that is the primary; or use a sharding strategy where each user is "owned" by a region's primary (no cross-region writes for a given user).
- Follow-up: EU regulators require that EU user data never leave EU data centers. How does that compliance requirement (Ch36/Ch37) further constrain your multi-region architecture? (Answer: you may need separate EU and US database clusters with no cross-region replication of PII — operationally more complex but legally required.)

---

**Question 46 — Handling Schema Evolution with Backward Compatibility**

Your team deploys a new version of the app with a renamed column (user_email to email). The old app version (still running during rolling deploy) reads user_email. The new version reads email. During the 10-minute rolling deploy window, both versions are live simultaneously. Design the zero-downtime migration.

- Explain the risk: if you rename the column before deploying the new code, the old app breaks; if you rename the column after deploying new code, the new app breaks; you cannot do it atomically with a standard rename.
- Explain the expand-contract pattern: (1) ADD COLUMN email (copy of user_email) — both columns now exist; (2) update application code to write to both columns and read from email; deploy this version; (3) backfill email from user_email for all existing rows; (4) make email NOT NULL; (5) deploy a version that writes only to email; (6) DROP COLUMN user_email; this is a 6-step migration spread over multiple deploys.
- Explain the tooling: use a schema migration framework (Flyway, Liquibase, Alembic) that tracks migration state per-environment; enforce the expand-contract pattern in code review; never allow a deploy that drops a column that is still read by the running application version.
- Follow-up: A team member says "this is too slow — it takes 3 deploys to rename one column." When is this caution justified (systems with zero-tolerance for downtime) vs over-engineered (internal tools with maintenance windows)?

---

**Question 47 — Materialized Views and Refresh Strategies**

Your reporting dashboard shows aggregate metrics (total revenue per region per day, cohort retention rates) that require 30-second queries on a 2-billion-row events table. Users expect the dashboard to load in under 2 seconds. Design the pre-computation strategy.

- Explain materialized views: a materialized view stores the query result set physically on disk; reads hit the cached result (fast); the result is only as fresh as the last refresh; PostgreSQL supports REFRESH MATERIALIZED VIEW (full re-computation) or CONCURRENTLY (no lock, but requires a unique index).
- Explain refresh strategies: (A) scheduled refresh — run REFRESH every 5 minutes via a cron job; data is up to 5 minutes stale; acceptable for dashboards; (B) event-triggered refresh — refresh when an upstream write occurs; for 2 billion rows, this is too expensive; (C) incremental refresh — compute only the delta since the last refresh; not natively supported in PostgreSQL but achievable with careful query design (WHERE event_time > last_refresh_timestamp).
- Explain the alternative — pre-aggregate in a separate table: instead of a materialized view, maintain a daily_revenue_by_region table with a background worker that appends new rows as events arrive; reads are always fast; the worker handles the aggregation complexity.
- Follow-up: The business wants hourly granularity instead of daily. The pre-aggregation table now has 24x more rows. How does that change the refresh strategy? At what granularity does in-database pre-aggregation break down and you need a dedicated OLAP engine?

---

**Question 48 — Database-Level Encryption and Key Rotation**

Security requires encryption at rest for your PostgreSQL instance. You enable transparent data encryption (TDE). Six months later, security requires key rotation — the encryption key must be replaced without taking the database offline. Design the key rotation process.

- Explain TDE: the database engine encrypts all data files using a master encryption key stored in a key management system (AWS KMS, HashiCorp Vault); the key is never exposed to application code; encryption/decryption is transparent to queries.
- Explain key rotation challenge: rotating the master key requires re-encrypting all data files; on a 5TB database, this takes hours and historically required downtime.
- Explain envelope encryption: the master key does not encrypt data directly — it encrypts a data encryption key (DEK) that encrypts the data; to rotate the master key, you re-encrypt only the DEK (a tiny operation, milliseconds); the data files are unchanged; this is how AWS KMS key rotation works.
- Explain application-level key rotation (when envelope encryption is not enough): if you need to rotate the DEK itself (e.g., after a breach), you must decrypt and re-encrypt all data; do this in batches on a read replica, then swap replicas; plan for hours of background re-encryption with monitoring on replication lag.
- Follow-up: A junior engineer suggests encrypting at the column level instead of TDE — encrypt the SSN column using AES-256 in application code before inserting. What do you gain (column-level granularity, no DB vendor dependency) and what do you lose (you cannot query encrypted columns in SQL without decrypting first; index-based filtering on SSN becomes impossible)?

---

**Question 49 — Backup and Recovery RTO/RPO Design**

Your startup's PostgreSQL database has no backup strategy. You are asked to design one. The business says "we can tolerate losing up to 1 hour of data" (RPO = 1 hour) and "we need to be back online within 4 hours of a disaster" (RTO = 4 hours). Design the backup system.

- Explain RPO (Recovery Point Objective): the maximum amount of data you can lose; RPO = 1 hour means your backup must be no older than 1 hour at any point; this requires continuous WAL archiving (WAL-E, pgBackRest, Barman), not just nightly backups.
- Explain RTO (Recovery Time Objective): the maximum time to restore; RTO = 4 hours means you must be able to take a base backup, apply WAL, and have a running database in under 4 hours; test this — many teams discover their restore procedure takes 8 hours when they try it.
- Design the backup architecture: (1) nightly full base backup to S3; (2) continuous WAL archiving to S3 with a maximum 5-minute flush interval (WAL segments are ~16MB; at low write rates you may need archive_timeout to force a flush even when the segment is not full); (3) a read replica as a warm standby that can be promoted in minutes rather than hours; (4) automated restore tests in a staging environment weekly.
- Follow-up: The CTO asks: "What is the cost of achieving RPO = 0 (zero data loss)?" Explain synchronous replication to a standby (every commit waits for the standby to acknowledge) and its write latency impact vs the business value of zero data loss.

---

**Question 50 — Putting It Together: The Database Architecture Review**

You join a 200-person company as a staff engineer. The system has: one PostgreSQL primary (db.r6g.8xlarge, $4K/month), no read replicas, no caching, no job queue, a monolith app, analytics queries running on production, and a schema that has never been migrated safely. The system works but is at 70% capacity. In 12 months the business plans to 5x traffic. Design the 12-month database evolution roadmap.

- Month 1-2 (immediate wins): add PgBouncer connection pooling (free, immediate throughput improvement); add one read replica (cut read load in half); move analytics queries to the replica; add Redis for the top 5 cacheable endpoints (measure cache hit rate first).
- Month 3-4 (schema hygiene): audit and fix the top 10 missing indexes (measure slow query log); establish the expand-contract migration pattern as a team standard; add autovacuum tuning and connection timeout settings.
- Month 5-8 (architectural separation): extract the job queue to Redis/SQS; establish CDC pipeline for syncing to an analytics warehouse (offload the analytics team entirely from production); introduce read-your-writes routing for freshness-sensitive endpoints.
- Month 9-12 (scale preparation): evaluate whether 5x traffic fits on the current primary with additional replicas, or whether sharding/partitioning is required; if table partitioning is needed, design and execute the partitioning migration before the traffic event, not during; run disaster recovery drills to validate RTO.
- Follow-up: The CEO announces a surprise 10x traffic event in 6 weeks (a Super Bowl ad). You are at month 2 of the roadmap. What is the minimum viable set of changes to survive 10x load in 6 weeks? (Answer: add 3 read replicas, Redis caching at the API layer, kill all analytics queries from production, and pre-warm connection pools — this is the emergency path, not the clean path.)

---

---

### Quick-Reference: Topic to Question Map

Use this index to locate a specific topic without reading the full list.

MVCC internals and bloat ........................... Q26
MVCC snapshot isolation and write skew ............. Q27
WAL structure and crash recovery ................... Q28
B-Tree vs LSM-Tree for write-heavy workloads ....... Q29
Query planner statistics and index selection ....... Q30
Connection pooling limits and PgBouncer ............ Q31
Zero-downtime schema migrations .................... Q32
Read replica lag and stale read handling ........... Q33
Hot row / hot partition contention ................. Q34
Optimistic vs pessimistic locking .................. Q35
Database-as-queue anti-pattern (Ch28+Ch33) ......... Q36
Polyglot persistence synchronization (Ch28+Ch33) ... Q37
Read replicas vs Redis caching (Ch28+Ch31/32) ...... Q38
Denormalization for join-heavy reads ............... Q39
B-Tree page splits and LSM-Tree (Ch28+Ch29) ........ Q40
GDPR deletion across FK tables (Ch28+Ch37) ......... Q41
RDS vs DynamoDB cost model (Ch28+Ch38) ............. Q42
Distributed transactions with Saga (Ch28+Ch33) ..... Q43
Analytics batch jobs on OLTP (Ch28+Ch35) ........... Q44
Multi-region PostgreSQL architecture (Ch28+Ch36) ... Q45
Schema evolution with expand-contract .............. Q46
Materialized views and refresh strategies .......... Q47
Database encryption and key rotation ............... Q48
Backup strategy, RPO, and RTO ...................... Q49
Full database architecture review .................. Q50

---

*End of Supplemental Questions 26-50 for Chapter 28.*

---

### Cross-chapter: PostgreSQL write idempotency under client retry (from Ch23)

**Question 41 -- PostgreSQL write idempotency under client retry (Ch23 + Ch28)**

Your e-commerce API creates orders in PostgreSQL.
A client submits an order. The INSERT takes 1,100ms. The client timeout is 1,000ms.
The client gets a timeout error and retries. The original INSERT already succeeded.

- Describe the failure mode: the database has the order; the client does not know.
  A naive retry creates a second order row with a new auto-generated UUID.
  What is the user-facing symptom?
- Add idempotency at the database layer: the client generates idempotency_key before the first
  attempt and includes it on every retry.
  The API does: INSERT INTO orders (..., idempotency_key) VALUES (..., 'abc-123')
  ON CONFLICT (idempotency_key) DO NOTHING.
  After a conflict, the API must return the ORIGINAL row.
  Write the SQL to fetch it. What HTTP status code does the API return: 200 or 201?
  Argue for a specific choice.
- Race condition: two retries arrive simultaneously (parallel network glitch).
  Both check "does key abc-123 exist?" -- neither finds it (first attempt still in flight).
  Both try to INSERT. PostgreSQL serializes: one succeeds, one hits DO NOTHING.
  Both threads fetch the existing row. Is there any scenario where DO NOTHING
  still causes a double charge?
- Follow-up: The client sends the same idempotency key but with a DIFFERENT amount
  (a bug changes the amount from 100 to 200 on retry).
  Should the server silently return the original response (amount=100),
  or return HTTP 422 (key reuse with different payload)?
  What does Stripe do? What data must the server store alongside the key to detect this case?

---

---

### Cross-chapter from Ch20: Per-Data-Type Consistency in Fintech

**Question 40 — Ch20 + Ch28: Per-Data-Type Consistency in Fintech**

You are designing the data layer for a fintech application. Three data types: (1) account balance — the current available balance, updated on every transaction; (2) transaction history — an append-only log of all debits and credits; (3) user preferences — display currency, notification settings, dark mode. Three database options on the table: PostgreSQL with serializable isolation, DynamoDB with tunable reads (eventual or strongly consistent, chosen per read request), Cassandra with tunable consistency levels (ONE, QUORUM, ALL, per operation).

- For each data type, select the appropriate consistency model and the appropriate database option. You may not give the same answer for all three. Justify each choice in two sentences: what the model provides and what specific harm occurs if you choose a weaker model.
- Transaction history is append-only — nothing is ever modified or deleted. A developer argues: "Eventual consistency is fine for append-only data — there are no conflicts to resolve." Construct the counter-argument. What specific scenario causes a user-visible problem when a user views their transaction history under eventual consistency, even if no writes conflict? (Hint: think about what happens when a user views their history immediately after initiating a transfer.)
- You chose DynamoDB for transaction history with eventually consistent reads. A compliance auditor asks: "Can a user's transaction history ever show a transaction that never happened?" Address this question precisely. Does eventual consistency in DynamoDB create phantom transactions? What does eventual consistency actually mean for read correctness vs. read freshness?
- Follow-up: A new regulatory requirement states that users disputing a transaction must see a consistent snapshot of their history for the duration of the dispute — meaning the history cannot appear to change between two reads taken 5 minutes apart during the same dispute session. Map this requirement to a consistency model. Which of the three database options can provide it? At what cost in terms of latency and throughput?

> *Discussion notes:*
> - *Account balance = PostgreSQL with serializable isolation (or DynamoDB strongly consistent reads). Stale balance reads cause either false overdraft or false rejection — both financial harm.*
> - *Transaction history = DynamoDB with eventually consistent reads. Records are immutable once committed. The only staleness: a very recent transaction may not appear immediately. User sees it on next refresh. Cosmetically suboptimal, not financially harmful.*
> - *User preferences = eventual consistency from any store — Redis would work. Stale display currency or dark mode causes zero harm.*
> - *Append-only data counter-argument: a user initiates a $500 transfer at T=0. They view transaction history at T+800ms. The replica is 1.5s behind. Their history shows nothing. They assume the transfer failed and initiate it again. This is the "my payment didn't go through" support ticket — a read-your-writes failure masquerading as a transaction failure.*
> - *Eventual consistency in DynamoDB does NOT create phantom transactions. Eventual means reads may be stale (missing recent writes), not incorrect (containing writes that never happened). A transaction that never committed will never appear.*
> - *Dispute requirement maps to snapshot isolation: the history must be consistent at a fixed point in time, not changing between reads. PostgreSQL MVCC provides this natively. DynamoDB can approximate it with version-stamped conditional reads but requires application-level session management.*

---


### Cross-chapter from Ch20+Ch21: Choosing the Right Database per Consistency

**Question 44 — Ch20 + Ch21 + Ch28: Choosing the Right Database per Consistency Requirement**

You are architecting a new payments platform. Four data types: (1) pending transaction state — a transaction is in one of {initiated, processing, settled, failed} at any moment; (2) ledger entries — an append-only record of all balance changes; (3) user payment method preferences — saved cards, default card, billing address; (4) fraud signals — a lightweight score (0.0-1.0) computed per transaction and stored for audit review.

Database options: PostgreSQL (serializable isolation, B-tree storage), DynamoDB (tunable per-request consistency, key-value), Cassandra (tunable per-operation with ONE/QUORUM/ALL, LSM-tree), Redis (in-memory, eventual across cluster nodes).

- For each data type, select one database and one consistency level. State the database, the consistency setting, and one sentence explaining what breaks if you chose a weaker model.
- Pending transaction state is the hardest. Two separate services (payment gateway and fraud detection) can both attempt to move a transaction from "processing" to "settled." Both read the current state, both see "processing," both attempt a write. Which database from the list above prevents this double-settlement at the database level? Which one requires the application to implement its own optimistic locking? Show the mechanism in each case — what SQL or API operation enforces mutual exclusion?
- Ledger entries are append-only. A common reasoning is "eventual consistency is fine for immutable data." Construct the failure mode that proves this wrong. Specifically: a user initiates a $500 transfer at 3:00:00 PM. The ledger entry is written to the primary at 3:00:00. The user checks their transaction history (a ledger read) at 3:00:00.800, 800ms later. The replica used for this read is 1.5 seconds behind. What does the user see? What action might they take based on what they see? What is the downstream consequence?
- Follow-up: Your Cassandra cluster for ledger entries is configured at QUORUM consistency with N=5 nodes, Replication Factor=3. QUORUM requires ceil((RF+1)/2) = 2 acknowledgments per write and per read. Two nodes fail simultaneously. Can you still write? Can you still read? Show the quorum math. What does Cassandra return to the client when quorum is not achievable — an error with a specific error code, a timeout, or does it return stale data silently?

> *Discussion notes:*
> - *Pending transaction state = PostgreSQL with serializable isolation + SELECT FOR UPDATE. This row-level lock prevents concurrent services from both reading "processing" and both writing "settled."*
> - *DynamoDB alternative for pending state: use a conditional write (attribute_not_exists(status) OR status = "processing"). Prevents double-settlement at the application level without row locking. The application must implement the check — the database does not enforce it natively.*
> - *Cassandra LWT (lightweight transactions, Paxos-backed conditional writes): can do conditional writes but costs 4× normal write latency and cannot span multiple rows. Not suitable for pending transaction state without careful design.*
> - *Ledger entries = DynamoDB with strongly consistent reads for the most recent 24 hours, eventually consistent for historical queries. Failure mode for eventual: user initiates a $500 transfer, checks history immediately, sees nothing, initiates the transfer again. This is the "my payment didn't go through" support ticket — a read-your-writes failure.*
> - *Quorum math: N=5, RF=3. QUORUM = ceil((RF+1)/2) = ceil(4/2) = 2 acknowledgments required. With 2 nodes failed: 3 nodes remain. Both writes (need 2 acks) and reads (need 2 acks) succeed. With 3 nodes failed: 2 nodes remain. Writes succeed (2 >= 2), but reads may fail if the 2 remaining nodes have divergent data. Cassandra returns WriteTimeout or ReadTimeout — never silently returns stale data when quorum cannot be achieved.*

---


### Cross-chapter from Ch21: Sharding vs. LSM-Tree Database Migration

**Question 43 — Ch21 + Ch28: Sharding vs. LSM-Tree Database Migration**

Your PostgreSQL primary processes 12,000 writes per second and is at 82% CPU. Engineers propose two options: (A) shard the users table across 4 PostgreSQL instances using user_id mod 4; (B) migrate to Apache Cassandra (LSM-tree storage engine) which can handle far higher write throughput on equivalent hardware.

- For option A — sharding PostgreSQL — list four queries that work correctly against the sharded setup and three queries that break or require application-level workarounds. For each broken query, explain what the correct workaround is and its complexity cost.
- For option B — migrating to Cassandra — explain at the storage engine level why an LSM-tree handles high write throughput better than a B-tree (PostgreSQL's storage). Be specific about what each engine does on a write: what I/O operations occur, what locking occurs, and what the throughput ceiling is determined by.
- Option B requires giving up ACID guarantees that PostgreSQL provides. List three specific guarantees that PostgreSQL provides natively which must be re-implemented at the application layer after migrating to Cassandra. For each, describe the implementation cost and the risk of getting the re-implementation wrong.
- Follow-up: Your team cannot decide. The CTO is risk-averse about Cassandra (irreversible migration cost) but the lead engineer is risk-averse about sharding (operational complexity compounds over time). You have 10 weeks to make the decision. Design a time-boxed experiment that produces the data needed to choose between the two options without fully committing to either. What do you build, what do you measure, and what specific data point constitutes a definitive recommendation for one option over the other?

> *Discussion notes:*
> - *Queries that work with user_id hash sharding: read user by user_id (single shard); update user profile by user_id (single shard); insert new user (route by hash); delete user by user_id (single shard).*
> - *Queries that break: SELECT * FROM users ORDER BY created_at LIMIT 100 — must query all 4 shards, merge results, re-sort (scatter-gather). SELECT COUNT(*) WHERE country='US' — scatter-gather, sum. SELECT u.*, o.total FROM users JOIN orders — cross-shard join requires application-level assembly if orders are on different shards.*
> - *LSM-tree write advantage at the mechanism level: PostgreSQL writes must find the correct page in the B-tree (random I/O), update it in-place, and write to the WAL. B-tree page splits cause write amplification. Cassandra writes go to a sequential in-memory MemTable and a sequential WAL only — no random I/O at write time. Compaction (reorganizing on-disk data) happens asynchronously in the background. This makes Cassandra's write path 5-10× faster on equivalent hardware for write-heavy workloads.*
> - *Three ACID guarantees to re-implement for Cassandra: (1) Foreign key enforcement — Cassandra has no concept of foreign keys; the application must validate parent existence before inserting a child row. (2) Uniqueness constraints beyond the partition key — Cassandra only guarantees uniqueness within a partition key. For global uniqueness (e.g., unique email addresses), the application must use LWT (4× write latency) or accept the risk of duplicates. (3) Multi-row atomic transactions — use the saga pattern with compensating transactions; no equivalent to PostgreSQL's BEGIN/COMMIT spanning multiple tables.*
> - *The 10-week experiment: shadow-write 10% of new writes to a Cassandra instance in parallel with PostgreSQL. Measure: write latency difference, read latency at QUORUM vs PostgreSQL primary, operational overhead of managing compaction. If Cassandra write P99 is 3× better and operational burden is manageable, migrate. If PostgreSQL sharding achieves sufficient throughput at the projected scale, stay.*

---


### Cross-chapter from Ch21: Read Replicas for Analytics vs. Operational Queries

**Question 47 — Ch21 + Ch28: Read Replicas for Analytics vs. Operational Queries**

Your team routes two types of traffic to the same pool of 4 read replicas: operational reads (user-facing, P99 latency SLO of 50ms) and analytics reads (internal dashboards, batch jobs, P99 latency tolerance of 60 seconds). The load balancer distributes these round-robin with no differentiation.

- Describe the hidden contention in specific database terms. A 45-minute analytics query (full table scan, reading 800 million rows) lands on Replica 2. At minute 3, an operational read for a user profile (expected: 2ms) also routes to Replica 2. What database resource is contended? What is the operational read's actual latency? Name the PostgreSQL mechanism that causes this.
- Design the isolation strategy with one additional replica. You now have 5 replicas total. What routing policy uses all 5? How do you prevent analytics queries from routing to the operational replicas — is this enforced at the load balancer, the database connection string level, or the application code level? What is the weakest link in your enforcement?
- The analytics team accesses the analytics replica directly using their own PostgreSQL credentials. Design the database-level guardrails that protect the replica's replication health from long-running analytics queries. Specifically: which session settings do you configure on the analytics role, what are the values, and why is each necessary?
- Follow-up: The analytics team's queries cause replication lag to increase from 500ms to 18 minutes on the analytics replica. The queries are the cause: they hold old snapshots that prevent autovacuum from removing dead tuples, which creates table bloat, which makes sequential scans progressively slower, which makes the queries run longer, which holds snapshots longer. This is a feedback loop. Identify each link in the feedback loop and design the intervention that breaks it. Your intervention must not require the analytics team to change their query patterns.

> *Discussion notes:*
> - *Contention mechanism: a long-running analytics query holds a PostgreSQL snapshot from the moment it started. This snapshot prevents autovacuum from removing dead tuple versions from tables being scanned. Operational reads on the same table must skip dead tuples — as dead tuples accumulate, effective table size grows, sequential reads degrade from 2ms to 200ms.*
> - *Isolation strategy with 5 replicas: Replicas 1-3 serve operational reads. Replica 4 serves analytics reads. Replica 5 is a hot standby for the operational pool. Enforcement at the network layer: analytics replica IP is only reachable from the analytics team's subnet, not from the application tier — this is auditable via firewall rules.*
> - *Session guardrails via ALTER ROLE: statement_timeout = '30min' (cancel queries exceeding 30 minutes), idle_in_transaction_session_timeout = '5min' (disconnect sessions holding idle transactions), lock_timeout = '10s' (cancel analytics queries that block on table locks), work_mem = '2GB' (in-memory sorts reduce disk spill). These are role-level defaults — the analytics user cannot override them.*
> - *Feedback loop breakdown: analytics query holds snapshot → autovacuum blocked → dead tuples accumulate → sequential scans slow → query runs longer → snapshot held longer → more dead tuples. Each link amplifies the next.*
> - *Intervention: set old_snapshot_threshold = '10min' on the analytics replica. PostgreSQL treats snapshots older than 10 minutes as non-blocking for autovacuum purposes. Autovacuum runs regardless of the analytics query's snapshot age. Bloat accumulation stops. Trade-off: analytics queries older than 10 minutes may receive a "snapshot too old" error — acceptable for analytics batch jobs, unacceptable for OLTP.*

---


---

### Cross-chapter from Ch26: DynamoDB strongly consistent reads and cost

**Question 35 -- Ch26 + Ch28: DynamoDB strongly consistent reads and cost**

DynamoDB is AP by default (eventually consistent reads). You can request strongly consistent reads (CP behavior) at the cost of 2x read capacity unit consumption. This makes the CP vs AP choice a literal dollar cost decision, not just a theoretical one.

- For a user profile service with three read patterns: (a) email lookup during login (must be fresh), (b) profile display on feed (can be slightly stale), (c) preference reads for ML recommendation (staleness of 5-10s is fine). For each: eventually consistent or strongly consistent? Calculate the RCU cost difference.
- At 100K reads/second with all reads strongly consistent vs all eventually consistent: what is the annual AWS cost difference? (Assume $0.25 per million RCU, 1 RCU per 4KB item, average item 1KB.) Show the calculation.
- Follow-up: A product manager says "make all DynamoDB reads strongly consistent to avoid any stale data." You pull up the cost calculation. At what read volume does the cost of strong consistency become a budget-level conversation? What is your recommendation for which reads genuinely need strong consistency?


### Cross-chapter from Ch27: CRDTs vs optimistic locking for high-concurrency counters

**Question 41 -- Ch27 + Ch28: CRDTs vs optimistic locking for high-concurrency counters**

Chapter 28 covers database internals, including optimistic locking (read-modify-write with version check). Both CRDTs and optimistic locking solve the concurrent increment problem, but with different approaches. Optimistic locking retries on conflict (eventually consistent from the operation's perspective but requires retries). CRDTs never conflict (no retries, but higher metadata overhead).

- At 1M like operations/second across 3 regions: compare the retry rate for optimistic locking (PostgreSQL counter with version check) vs the merge overhead for G-Counter CRDT. For optimistic locking: at 30% collision rate, 30% of operations require a retry. At 1M/second: 300K retries/second. For G-Counter: each operation is local, no retries, but every read requires summing 3 replica values.
- Calculate the database load for each approach at 1M/second: (a) PostgreSQL optimistic locking: 1M primary writes + 300K retries = 1.3M write operations/second. (b) G-Counter: 1M writes spread across 3 replicas = 333K writes/replica, but 3x merge operations per read. Which scales better?
- Follow-up: The business rule says "the like count displayed to users can be 5 seconds stale, but likes must never be lost." Which approach satisfies this requirement? Optimistic locking: retries can fail under extreme load, potentially dropping some like operations. G-Counter: never drops a like, but the count is eventually consistent (up to 5-second staleness during replication lag). G-Counter is the correct choice. Explain why to a non-technical stakeholder.

---

## Exercises

**Exercise 1 — Database selection matrix.** Choose a database for each system and justify: (a) user profiles (100M users, read-heavy, structured), (b) real-time leaderboard (10M concurrent, sorted by score), (c) CMS documents (variable schema, full-text search), (d) time-series metrics (50K writes/second, 30-day retention). For each: one alternative considered and why it was rejected.

**Exercise 2 — Schema evolution.** You have a PostgreSQL table with 100M rows and need to add a NOT NULL column. Walk through: direct ALTER TABLE locking behavior, the online migration approach (add nullable → backfill → add constraint), and how to validate without downtime.

**Exercise 3 — Read/write pattern analysis.** For a system you own: what's the read:write ratio per major table, what indexes exist (used vs. unused), and which queries are slowest? Propose three optimizations (indexes, denormalization, caching).

**Exercise 4 — Consistency model selection.** For each social media operation (post tweet, increment likes, follow user, view profile, view feed), pick the right consistency model and justify. What's the user experience cost of getting it wrong?

**Exercise 5 — Database migration planning.** Migrate from MySQL to PostgreSQL: 500M rows, 10K RPS, 99.9% availability SLA. Write the migration plan: phases, risk mitigation, rollback procedure, and data integrity validation.

**Exercise 6 — Connection pool sizing.** 20ms average query duration, 10 app servers, 200 max DB connections. Calculate: connections per server, max concurrent queries, queue depth at 500 RPS, and behavior when pool is exhausted.

---

## Homework

**Assignment 1 — Database audit.** For every database your team owns: document access patterns, current indexes (used vs. unused), and the biggest performance bottleneck. Identify one optimization per database to implement this sprint.

**Assignment 2 — Read "Use the Index, Luke."** For your three slowest production queries, run EXPLAIN ANALYZE. Write a one-page analysis identifying whether each query uses the right index.

**Assignment 3 — Interview practice: database design.** Practice "design the data model for a Twitter-like feed" in 20 minutes. Cover: table structure, indexes, write path (fan-out), sharding strategy, consistency model per operation.

**Assignment 4 — Chaos test on a replica.** Simulate a read replica failure. Observe how your application handles it. Measure impact on primary load. Document: detection time, degraded behavior, and fix.

