# Chapter 90: Social Graph — Instagram / Twitter / LinkedIn at Scale

> The social graph is the nervous system of every social product. Follow/unfollow is a write. "Who should I show this post to?" is a graph traversal touching billions of edges.

---

## CHAPTER OVERVIEW

This chapter covers how social platforms store, query, and compute on massive graphs of human relationships. We zoom in on three core systems:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    THREE SYSTEMS THIS CHAPTER COVERS                │
├─────────────────┬───────────────────────────┬───────────────────────┤
│   STORAGE       │       QUERYING            │  OFFLINE COMPUTATION  │
├─────────────────┼───────────────────────────┼───────────────────────┤
│ Adjacency lists │ Follower/following lists  │ PYMK (who to follow)  │
│ TAO (Facebook)  │ Mutual connections        │ Graph partitioning    │
│ FlockDB (Twitter│ Cursor-based pagination   │ PageRank for ranking  │
│ Graph DBs (Neo4j│ Degree-of-separation BFS  │ Spark GraphX jobs     │
│                 │ Counter caching (Redis)   │ Node embeddings       │
└─────────────────┴───────────────────────────┴───────────────────────┘

Scale we are designing for:
  Users:       3 billion (Meta), 400M (Twitter), 1B (Instagram)
  Edges:       100 billion+ friendships / follows
  Writes:      Millions of follows/unfollows per hour
  Reads:       Billions of feed, profile, PYMK queries per day
```

Each Part builds on the previous. By the end you will be able to whiteboard the entire social graph stack from first principles.

---

## Part 1: The Social Graph Problem

### What Is a Social Graph?

Imagine every person on the internet as a dot on a giant whiteboard. Every time person A follows or friends person B, you draw an arrow between those two dots. The full picture — all the dots and all the arrows — is the **social graph**.

The word "graph" here is borrowed from mathematics. In math, a graph is just a set of **nodes** (the dots, representing users) and **edges** (the arrows, representing relationships). Social networks are graphs because human relationships are exactly this structure: people connected to other people.

There are two fundamentally different flavors of social graph:

**Directed graph** — used by Twitter and Instagram. When A follows B, there is an arrow pointing FROM A TO B. B does not automatically follow A back. Lady Gaga has 80 million followers but she follows only a few hundred accounts. The arrows are one-way. Technically: edge (A→B) does not imply edge (B→A).

**Undirected graph** — used by Facebook and LinkedIn. When A and B become friends, the relationship is mutual. There is a single edge between them that means "these two are connected." Technically: edge (A,B) is the same as edge (B,A). There is no direction.

This distinction matters enormously for system design because it changes what queries look like and how the data is stored.

### Scale: Why This Is Hard

Let us think about Meta (Facebook + Instagram combined). As of 2024:

- ~3 billion monthly active users (the nodes)
- ~100 billion friendship/follow edges
- Each user has on average ~200 connections
- Some users (celebrities, brands) have tens of millions of followers

If you stored every edge as a row in a MySQL table, that table would have **100 billion rows**. A simple `SELECT * FROM follows WHERE followee_id = 123` on that table — to find all followers of user 123 — could potentially touch billions of rows depending on how popular user 123 is.

Now multiply that query by the number of times per second users ask "show me who follows this person" or "should I show this post to these people." You are looking at millions of such queries per second across the entire platform. Standard database approaches break immediately.

### Core Queries the System Must Answer

These are the queries that every social platform runs constantly. Every one of them touches the social graph:

1. **Followers of X** — "Who follows this user?" (needed for feed fan-out: who gets to see X's new post)
2. **Following of X** — "Who does this user follow?" (shown on profile page)
3. **Follower count of X** — A single number shown on every profile
4. **Is A following B?** — Edge existence check (does the Follow button show "Following" or "Follow"?)
5. **Mutual connections between A and B** — "3 mutual friends" shown on Facebook profile cards
6. **2nd-degree connections** — Friends of friends, used for People You May Know (PYMK)
7. **Degree of separation** — How many hops between any two users (Facebook found average is 3.57)
8. **Feed recipients** — When X posts, which of X's followers should receive this post in their feed?

### Why Sharding Is Hard

Sharding means splitting your data across multiple database machines so no single machine holds everything. The natural approach for a user table is to shard by `user_id`: users 1–10M go to shard 1, users 10M–20M go to shard 2, and so on. This works great for user profile data because queries are always "give me user 12345" which goes to exactly one shard.

The social graph breaks this model. Consider the follows table with columns `(follower_id, followee_id)`. If you shard by `follower_id`, then all edges starting from user A are on one shard — great for "who does A follow?" but terrible for "who follows A?" because A's followers are scattered across every shard. If you shard by `followee_id`, you flip the problem.

The fundamental issue is that an edge connects TWO nodes, and those two nodes live on different shards. There is no sharding key that makes ALL queries local. This forces you into one of several imperfect solutions: dual-write (store each edge twice, once keyed by follower and once by followee), graph partitioning (group densely connected users on the same shard), or a specialized graph serving layer that understands this multi-shard reality.

### 5-Level Progression: How Would You Design This?

**Intern:** "I'd store follows in a MySQL table with columns `(follower_id, followee_id, created_at)`. Add an index on `follower_id` to find who someone follows, and another index on `followee_id` to find their followers. For 100M users this works fine."

This is the correct starting point and shows solid basics. The problem is that 100M users is not 3B users, and a table with 100 billion rows with two separate index traversals will be catastrophically slow.

**Junior Engineer:** "I'd shard the MySQL table. Shard by `follower_id` so that 'who does A follow?' is always a single-shard query. For 'who follows A?' I'd add a second table keyed by `followee_id` and dual-write. I'd also add Redis caching in front — store the follower list as a Redis sorted set keyed by `followee_id`, sorted by follow timestamp, so follower lookups hit cache 99% of the time."

This is a real improvement. Dual-write handles the two-direction query problem. Redis sorted sets are an excellent data structure for paginated follower lists. The weak spot: dual-writes need transactions or at-least-once delivery semantics to stay consistent, and cache invalidation on unfollow is tricky.

**Mid-level Engineer:** "For reads at this scale, Redis sorted sets are the right cache layer. I'd store `followers:{user_id}` as a sorted set with the follower's user_id as the member and the follow timestamp as the score — this gives me time-ordered pagination for free. For writes, I'd use a message queue (Kafka) between the write path and the dual-write: the HTTP handler inserts into the primary MySQL shard synchronously, then publishes a 'follow event' to Kafka. A consumer reads from Kafka and updates the reverse-shard MySQL table and the Redis cache. This decouples the write path from fan-out work. Counts (follower count, following count) are separate counters in Redis — I increment/decrement atomically on every follow/unfollow event rather than counting rows."

This is solid production-grade thinking. The Kafka decoupling prevents one slow downstream update from blocking the user's HTTP request. Separate counters avoid full-table-scans for counts.

**Senior Engineer:** "At 100B edges and billions of reads per day, even Redis per-user sorted sets have limits. The key insight is that most social graph reads are hot: the top 1% of users (celebrities, news accounts) get 99% of the follower-list reads. I'd tier the storage: hot celebrity follower lists stay in Redis (or better, a distributed in-memory store like a specialized graph serving layer), while long-tail user follower lists are served from MySQL on cache miss. For the graph itself, I'd look at Facebook's TAO model: a two-tier cache sitting in front of MySQL, purpose-built for object-and-association (node-and-edge) access patterns. TAO handles both the 'give me node X's data' and 'give me all edges of type Y from node X' queries with a unified API. For sharding, I'd use consistent hashing on `user_id` so that the primary copy of 'who does user X follow' is always on one shard. The reverse direction is served from a replicated read replica or a cache tier that is populated asynchronously."

**Staff Engineer:** "The social graph problem at Meta/Twitter/Instagram scale requires separating three concerns that junior engineers conflate: storage (where does the ground truth live?), serving (how do reads get answered fast?), and computation (what offline processing generates derived data?). For storage, the ground truth is a sharded MySQL-backed system — reliable, ACID for individual row writes, and at 100B rows it is manageable with proper partitioning and hardware. For serving, you build a specialized in-memory caching tier — Facebook's TAO uses two tiers of Memcache in front of MySQL with a carefully designed consistency protocol. Twitter went further and loaded the entire social graph into RAM on dedicated graph servers (350M users × ~200 edges × 8 bytes ≈ about 560GB, which fits on a few servers with high-memory instances). For computation, graph algorithms like PYMK, degree-of-separation, and PageRank cannot run on the live serving layer — they run as offline Spark GraphX jobs on a snapshot of the graph. The serving layer answers 'give me the edge list for user X'; the offline layer answers 'compute PYMK scores for all users.' The staff-level insight is that no single system solves all three — you compose specialized systems for each concern, and the system design challenge is managing consistency and freshness boundaries between them."

### Brainstorming Q&A

**Q1: Why can't you just use a graph database like Neo4j for the social graph at Meta scale?**

Graph databases like Neo4j are purpose-built for graph traversal — they store edges as explicit pointers between nodes, so a query like "find all friends of friends of user X" follows in-memory pointers rather than doing index lookups. For small and medium graphs (say, tens of millions of nodes), Neo4j is genuinely excellent. The problem is that Neo4j and most graph databases are designed to run on a single machine or a small cluster, and they do not shard well. The entire power of a graph database comes from pointer traversal — following a chain of edges is fast because the database engine walks physical pointers in memory or on disk. The moment you distribute the graph across many machines, those "pointers" become network calls, and the traversal latency explodes. Facebook's graph has 3 billion nodes and 100 billion edges. No single machine holds that. You must distribute. But once you distribute, the graph-database traversal advantage disappears — you are doing network hops anyway. Meta, Twitter, and LinkedIn all concluded that a combination of sharded MySQL (for ground truth) plus a custom in-memory cache layer (for serving) outperforms graph databases at their scale. Graph databases are a great fit for analytics use cases on graph subsets, but not for serving billions of real-time social graph queries per day.

**Q2: A new engineer on your team says "let's just add an index on followee_id and we can answer follower queries from the same table without dual-writing." What is wrong with this plan?**

The suggestion is reasonable and actually works — up to a point. A MySQL table with `(follower_id, followee_id)` and indexes on both columns can answer "who follows user X" by scanning the `followee_id` index. The problem is sharding. Once you horizontally shard the table by `follower_id` (which you must do at 100B rows), the data for "all followers of user X" is scattered across potentially thousands of shards. Finding all followers of Lady Gaga means sending a query to every shard, collecting results, and merging them — this is called a scatter-gather query, and it is catastrophically inefficient. If you have 1,000 shards and every follower-lookup fans out to all 1,000, your database tier takes 1,000x the load for that query type. Additionally, index scans on a single shard for a celebrity with 80M followers would still be slow — you are scanning 80M index entries, which requires significant I/O. Dual-writing, where you maintain a second physical table or shard keyed by `followee_id`, eliminates the scatter-gather: "who follows user X" goes to exactly the shard that holds X's follower list. The tradeoff is write amplification (every follow/unfollow touches two storage locations) and consistency (if one write succeeds and the other fails, you have a split-brain). These tradeoffs are manageable with a message queue ensuring at-least-once delivery; the scatter-gather problem at 100B rows and 1000 shards is not manageable.

---

## Part 2: Storage Models

### The Adjacency List in RDBMS

The most natural way to store a social graph in a relational database is the **adjacency list** model. You create a table where each row represents one directed edge:

```sql
CREATE TABLE follows (
    follower_id   BIGINT NOT NULL,
    followee_id   BIGINT NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY   (follower_id, followee_id),
    INDEX         idx_followee (followee_id, follower_id)
);
```

The composite primary key `(follower_id, followee_id)` ensures uniqueness (you can't follow someone twice) and creates a clustered index that makes "who does user A follow?" extremely fast — all of A's followees are stored physically adjacent on disk. The secondary index `(followee_id, follower_id)` makes "who follows user A?" fast from the other direction.

At 100 billion rows, this table is roughly 100B × (8 + 8 + 8) bytes = 2.4 terabytes of raw data, plus index overhead. This fits on a single large server but query performance degrades as the table grows. The solution is **horizontal sharding**.

**Sharding the follows table:**

The standard approach is to maintain TWO physical copies of the follows data, in two separate sharded table clusters:

```
Cluster 1: Sharded by follower_id
  Shard 1: follower_ids 0 - 999,999
  Shard 2: follower_ids 1,000,000 - 1,999,999
  ...
  → Fast query: "who does user X follow?"

Cluster 2: Sharded by followee_id
  Shard 1: followee_ids 0 - 999,999
  Shard 2: followee_ids 1,000,000 - 1,999,999
  ...
  → Fast query: "who follows user X?"
```

Every follow/unfollow writes to BOTH clusters. This is called dual-write. Consistency is maintained by treating the write to Cluster 1 as the source of truth (write it synchronously in the HTTP handler) and propagating to Cluster 2 asynchronously via a message queue.

### TAO: Facebook's Graph Storage System

Facebook built TAO (The Associations and Objects) specifically because generic MySQL + Memcache setups were not ergonomic for social graph access patterns. TAO introduces a clean abstraction layer:

- **Objects** — nodes in the graph (users, posts, pages, events). Each has a type and an ID.
- **Associations** — directed, typed edges between objects. An "association type" might be FRIEND, LIKES, FOLLOWS, COMMENTED_ON. Each association has a timestamp and optional metadata.

TAO's API is deliberately narrow:
- `assoc_get(id1, type, id2)` — does this specific edge exist?
- `assoc_range(id1, type, offset, limit)` — get paginated list of edges from node id1
- `assoc_count(id1, type)` — how many edges of this type does node id1 have?
- `obj_get(id)` — get a node's data

This narrow API is a feature, not a limitation. Because TAO knows that social graph accesses always look like one of these patterns, it can optimize aggressively.

```
TAO Architecture:

┌─────────────────────────────────────────────────────────────┐
│                    WEB / APP SERVERS                        │
│  (call TAO client library — never touch MySQL directly)     │
└──────────────────────────┬──────────────────────────────────┘
                           │ TAO API calls
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              TAO LEADER TIER (per data center)              │
│   Memcache cluster — holds hot objects and associations     │
│   One leader per shard handles writes + cache coherence     │
└──────────────────────────┬──────────────────────────────────┘
                           │ cache miss → fill from DB
                           │ writes → pass through to DB
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              TAO FOLLOWER TIER (multiple per DC)            │
│   More Memcache — serve read-heavy traffic locally          │
│   On miss, asks Leader tier (not DB directly)               │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              MySQL STORAGE LAYER (sharded)                  │
│   Objects table + Associations table                        │
│   Sharded by (id1 % num_shards) for associations            │
│   Ground truth — written to on every follow/unfollow        │
└─────────────────────────────────────────────────────────────┘
```

The two-tier cache structure is critical. The **leader tier** (one Memcache cluster per logical shard) is the authoritative cache — all writes go through it so it can maintain strong consistency for that shard. The **follower tier** (multiple Memcache clusters, closer to web servers) serves read traffic. On a cache miss in the follower tier, it asks the leader, not MySQL — this prevents thundering herds from hitting the database.

TAO handles cross-data-center replication separately: there is a TAO leader in each data center, and they sync via asynchronous MySQL replication with TAO's consistency protocol on top.

### Twitter's FlockDB: The In-Memory Approach

Twitter took a different approach: load the entire social graph into RAM on dedicated graph servers. FlockDB (open-sourced by Twitter around 2010) is a distributed graph database that stores edges primarily in memory with disk persistence.

The scale math works: Twitter had roughly 350 million users, each following on average 200 accounts. That's 350M × 200 = 70 billion edges. Each edge (follower_id, followee_id) is two 64-bit integers = 16 bytes. Total: 70B × 16 bytes = ~1.1 terabytes. With modern high-memory servers (machines with 1–4TB RAM are commercially available), you can hold the entire Twitter social graph in RAM on a small cluster of machines. Memory access is microseconds; this is orders of magnitude faster than even the best disk-based database.

Twitter later evolved this into Cassandra-backed storage with in-memory caching, but the core insight — the social graph for a service like Twitter fits in RAM and you should exploit that — remains valid.

### Why Graph Databases Fail at Web Scale

Neo4j, JanusGraph, Amazon Neptune, and similar graph databases store edges as physical pointers (or pointer-like index entries) between nodes. This makes single-machine graph traversal very fast. The problems at scale:

1. **No horizontal sharding** — Neo4j's architecture assumes the graph fits on one machine (or a small HA cluster). When it doesn't, you must partition the graph across machines, but graph traversals frequently cross partition boundaries, turning each hop into a network call.

2. **Pointer traversal across machines = network calls** — The entire advantage of a graph database is in-process pointer following. Distributed pointer following is just scatter-gather with extra steps.

3. **Write throughput** — Social graph writes (follows/unfollows) happen at millions per hour. Graph databases optimized for traversal typically sacrifice write throughput.

4. **Operational complexity** — MySQL has 30 years of operational tooling (backups, point-in-time recovery, replicas, slow-query analysis). Graph databases have much younger tooling ecosystems.

The result: every large-scale social network that has published their architecture uses MySQL (or Cassandra) for storage with a custom serving/caching layer, not a graph database.

### 5-Level Progression: Designing the Storage Layer

**Intern:** "I'd use a follows table in PostgreSQL with `(follower_id, followee_id)` and indexes on both columns. For a startup with a million users, this is totally fine."

**Junior Engineer:** "At 10M users I'd add sharding to the MySQL table. Shard by `follower_id` for one direction, add a second cluster sharded by `followee_id` for the other direction. Write to both via a message queue for the secondary. Add Redis to cache hot follower lists."

**Mid-level Engineer:** "I'd adopt the TAO object/association model conceptually even if not literally. Store follows in a sharded MySQL table, add a two-level cache (local cache on app servers + a shared Memcache tier). Make sure counts (follower_count, following_count) live in Redis as separate counters, not computed by SELECT COUNT(*). Track follow timestamps in the edge so I can do time-ordered pagination without expensive ORDER BY queries."

**Senior Engineer:** "At 100B edges, storage design must account for two separate concerns: write path and read path. For the write path, sharded MySQL is ground truth. Writes go to the shard synchronously, then fan out asynchronously via Kafka to update the reverse-direction shard and any cache tiers. For the read path, the follower list for any given user must be served from an in-memory structure — either Redis sorted sets for moderate-follower users or a dedicated graph serving tier for celebrities. I'd implement tiered storage: celebrities (>1M followers) get their follower lists eagerly loaded into the graph serving tier; everyone else is served from Redis on cache hit or MySQL on cache miss. This way the 0.01% of celebrity accounts that cause 90% of the read load get special treatment without complicating the general case."

**Staff Engineer:** "Storage is not one system — it is a stack of three layers with explicit contracts between them. Layer 1 is the ground truth: sharded MySQL with dual-write clusters, each holding the adjacency list in one direction. This gives ACID guarantees for individual edge writes and lets you reconstruct any cache from scratch. Layer 2 is the serving cache: TAO-style Memcache tiers or Redis, holding hot edge lists and counts. This layer absorbs 99%+ of read traffic. The contract between layers 1 and 2 is eventual consistency — caches may be a few seconds stale. Layer 3 is the offline derived store: a snapshot of the full graph stored in HDFS or S3, used as input to Spark jobs that compute PYMK scores, PageRank, and other graph analytics. The contract between layers 1 and 3 is batch freshness — the graph snapshot is rebuilt nightly or hourly. The staff-level design decision is choosing where the consistency boundary sits. For 'is A following B?' (shown on the Follow button), you need near-real-time consistency — a one-second lag is acceptable, a one-hour lag is not. For 'suggested friends for user A' (PYMK), a one-day lag is fine. Map each query type to the right layer."

### Brainstorming Q&A

**Q1: You're designing storage for a new social platform that is launching in six months and expects to grow to 50 million users in year one and 500 million in year three. How do you choose your storage architecture so you don't have to rewrite it at 500M?**

The key principle here is "build for where you're going, not where you are, but don't over-engineer for where you might be." At 50 million users with an average of 200 connections each, you have 10 billion edges — manageable in a well-indexed MySQL cluster without heroic engineering. The right year-one architecture is: sharded MySQL (8–16 shards) with dual-write clusters (one sharded by follower_id, one by followee_id), Redis sorted sets for hot follower lists, and separate Redis counters for follower/following counts. This is a well-understood stack that any experienced engineer can operate. The critical thing to do in year one is to put a service abstraction layer (a "graph service") in front of the storage, so that all application code talks to the graph service API rather than directly to MySQL or Redis. When you reach 500M users and need to migrate the storage implementation (to something like TAO or an in-memory graph server), you change what the graph service does internally without changing any application code. The graph service is the investment that makes the system evolvable. Without it, every service that touches the social graph becomes a migration project.

**Q2: What happens to TAO's consistency guarantees when a data center goes down? How does TAO handle this?**

This is a real problem TAO was designed around. TAO stores data across multiple data centers (Facebook has data centers on several continents). The MySQL replication between data centers is asynchronous — writes go to the primary data center's MySQL first, then replicate to secondary data centers with a few-seconds lag. TAO's leader caches sit in front of this MySQL. When a data center goes down, two things happen: (1) reads that were being served by that DC's TAO leader/follower tiers now must route to another DC, accepting higher latency but still returning data. (2) writes that were going to that DC's MySQL must fail over to another DC's MySQL. Facebook's approach is to have one "primary" data center per logical shard that handles writes, and all other data centers are read replicas. If the primary DC for a shard goes down, they run a failover process to promote a replica to primary — this takes seconds to minutes during which writes to that shard may fail or be held. The tradeoff is that TAO accepts eventual consistency on reads: a follower in data center B might briefly show a stale follower list if a follow event was written to data center A's MySQL and hasn't replicated yet. For social graphs this is acceptable — seeing a follow appear with a 2-second delay is invisible to users. For critical counts (like "has this user been banned?"), Facebook routes those reads through the primary TAO tier even from distant data centers, accepting higher latency for stronger consistency.

---

## Part 3: Follow/Unfollow Write Path

### The Full Write Path for a Follow Action

When Alice taps "Follow" on Bob's profile in the Instagram app, a surprisingly complex chain of events occurs. Let's trace it step by step:

```
Alice's phone
     │
     │  POST /follow  {follower_id: alice, followee_id: bob}
     ▼
Load Balancer
     │
     ▼
Follow Service (stateless HTTP handler)
     │
     ├──① Check: does this follow already exist?
     │         (Redis cache lookup: is alice in bob's follower set?)
     │
     ├──② Idempotency check passed → write to MySQL (ground truth)
     │         INSERT INTO follows (follower_id, followee_id, created_at)
     │         VALUES (alice_id, bob_id, NOW())
     │         ON DUPLICATE KEY IGNORE;
     │
     ├──③ Publish follow event to Kafka
     │         topic: "follow-events"
     │         payload: {follower: alice, followee: bob, ts: now}
     │
     └──④ Return 200 OK to Alice's phone
            (fast — only steps ①②③ are synchronous)

Kafka consumers (async, after response sent):
     │
     ├── Consumer A: Update reverse-direction MySQL shard
     │     INSERT INTO follows_by_followee (followee_id, follower_id, ...)
     │
     ├── Consumer B: Update Redis follower list
     │     ZADD followers:{bob_id} {timestamp} {alice_id}
     │     INCR follower_count:{bob_id}
     │     INCR following_count:{alice_id}
     │
     ├── Consumer C: Trigger feed fan-out
     │     (if bob has recent posts, add them to alice's feed)
     │
     └── Consumer D: Update TAO cache
           assoc_put(alice_id, FOLLOWS, bob_id, timestamp)
```

The synchronous path (steps 1–4) should complete in under 100ms. All the heavy downstream work is async.

### The Celebrity Problem: Write Amplification

The follow write for most users is cheap. But consider Lady Gaga with 80 million followers on Twitter. When Lady Gaga posts a new tweet, the feed service needs to notify all 80 million followers. This is called **fan-out on write** — you push new content to each follower's inbox at write time so that reads are fast (each user's feed is precomputed and stored).

Fan-out for Lady Gaga = 80 million write operations per post. If Lady Gaga tweets 10 times a day, that's 800 million writes per day from one user. A single celebrity can generate more write load than all "normal" users combined.

Twitter's solution: **hybrid fan-out strategy**.

```
Normal users (< ~1M followers): fan-out on WRITE
  → When user posts, push to all followers' feed caches immediately
  → Read path is trivial: just read your precomputed feed

Celebrity users (> ~1M followers): fan-out on READ
  → When celebrity posts, DON'T push to followers' caches
  → When a follower's feed is fetched, MERGE their precomputed feed
    with a real-time lookup of celebrities they follow
  → Slightly more expensive reads, but eliminates write amplification

Mixed feeds: each user's feed = precomputed_feed MERGE celebrity_posts
```

This hybrid approach caps write amplification at roughly 1 million writes per post (the threshold for "celebrity" treatment) while keeping read latency acceptable.

### Soft Delete vs. Hard Delete on Unfollow

When Alice unfollows Bob, you have two options:

**Hard delete** — `DELETE FROM follows WHERE follower_id=alice AND followee_id=bob`. The row is gone. Simple. The problem: at 100B rows, MySQL deletes are expensive — they update the clustered index and the secondary index, write to the undo log, and can cause page splits. Mass unfollow events (when a celebrity account is suspended, all N million follows get deleted) can cause a write storm.

**Soft delete** — Add a `deleted_at TIMESTAMP NULL` column. Unfollow sets `deleted_at = NOW()` rather than deleting the row. Queries add `WHERE deleted_at IS NULL`. The row sticks around until a periodic background job purges old deleted rows in off-peak hours.

Soft delete has operational advantages: you can audit follows/unfollows (useful for spam detection and abuse analysis). You can recover from accidental unfollows. You can rate-limit the actual deletion to avoid I/O spikes. The downside is that your "live" table is bloated with deleted rows — index scans touch dead rows before filtering, which hurts performance over time.

Most large social platforms use soft delete with a background purge job that runs nightly. The purge job processes deletions in small batches with rate limiting to avoid impacting live traffic.

### Eventual Consistency for Counts

The follower count shown on a profile page (e.g., "10,432,891 followers") is NEVER read by doing `SELECT COUNT(*) FROM follows WHERE followee_id=?`. At 80M followers, that count query would take seconds. Instead, the count is stored as a separate counter:

```
Redis:
  follower_count:{bob_id}  →  80,000,000
  following_count:{alice_id}  →  342

MySQL (separate counters table):
  INSERT INTO user_counters (user_id, follower_count, following_count)
  VALUES (bob_id, 0, 0)
  ON DUPLICATE KEY UPDATE
    follower_count = follower_count + 1;  -- on follow
    follower_count = follower_count - 1;  -- on unfollow
```

These counters are updated asynchronously via Kafka consumers after the follow write completes. This means there is a brief period (usually under a second) where the follow has been written to MySQL but the Redis counter hasn't been incremented yet. The profile page might briefly show the old count. This is **eventual consistency** — the system will converge to the correct count, just not instantly.

For social networks, this is perfectly acceptable. Users do not notice a 1-second delay in counter updates. The tradeoff — simpler writes, much faster count reads — is clearly worth it.

### 5-Level Progression: Follow/Unfollow Write Path

**Intern:** "I'd insert a row into the follows table, increment the follower_count in the users table, and return 200 OK. Simple and correct."

**Junior Engineer:** "I'd separate the counter update from the edge insert. Insert the edge, publish a Kafka event, return 200 immediately. A Kafka consumer handles counter updates and cache invalidation. This way a slow counter update doesn't block the user's request. I'd also add an idempotency check — if Alice tries to follow Bob twice (maybe she double-tapped), the second request should be a no-op."

**Mid-level Engineer:** "I'd add the celebrity detection logic. When the follow event is published to Kafka, the fan-out consumer checks the followee's follower count. If it's under the celebrity threshold (say 1M), do fan-out on write — push Bob's recent posts to Alice's feed inbox. If it's over the threshold, skip fan-out — Alice's feed will merge celebrity posts at read time. I'd also add rate limiting on follows per user per hour to prevent spam following."

**Senior Engineer:** "The write path has three distinct failure modes that need different handling. First, the MySQL write can fail (database overload, shard offline) — this should return an error to the user; nothing else has happened. Second, the Kafka publish can fail after MySQL write succeeds — the Kafka event is the trigger for counter updates and feed fan-out. If it's lost, the counts drift and the feed is stale. I'd handle this with a CDC (Change Data Capture) approach: read MySQL's binlog (using Debezium or similar) to generate the Kafka events, rather than having the application publish directly. CDC guarantees that every MySQL write generates exactly one Kafka event, even if the application crashes mid-request. Third, a Kafka consumer can fail mid-processing — this is handled by Kafka's consumer offset mechanism: if the consumer crashes, it replays from the last committed offset, reprocessing events at-least-once. Consumer logic must be idempotent — re-processing the same follow event twice should not double-increment the counter."

**Staff Engineer:** "The write path at web scale is really about managing causality and ordering. When Alice follows Bob, several derived states need to update: (1) edge in primary MySQL shard, (2) edge in reverse MySQL shard, (3) Redis follower list for Bob, (4) Redis following list for Alice, (5) counter for Bob's follower count, (6) counter for Alice's following count, (7) Alice's feed (Bob's recent posts should appear), (8) Bob's notifications (Alice just followed him). Each of these has a different latency budget and failure tolerance. The staff engineer's job is to define the causality DAG: which updates must happen before the 200 OK (the primary MySQL write), which must happen before the UI is consistent (Redis updates, < 1 second), and which can happen lazily (notifications, full feed rebuild, PYMK score refresh, < 1 minute). The write amplification problem is the most interesting: a single follow event for a celebrity fan-out triggers O(recent_posts) feed writes across potentially millions of follower shards. The mitigation is the hybrid fan-out model, but implementing it requires a clean abstraction layer that knows which accounts are 'celebrities.' This classification changes dynamically (an account goes viral overnight) so the celebrity threshold must be rechecked on every follow or managed by a separate account-tier service that pushes updates when thresholds are crossed."

### Brainstorming Q&A

**Q1: How do you handle the case where a very popular account gets suspended and 80 million follow edges need to be deleted? What's the system impact and how do you mitigate it?**

When a celebrity account with 80 million followers gets suspended, the naive approach of immediately deleting all follow edges would be catastrophic. Deleting 80 million rows from sharded MySQL involves 80 million index updates across potentially hundreds of shards, all happening simultaneously. This would cause massive I/O spikes on the database tier, competing with live traffic and degrading performance for all users on those shards. The correct approach has three parts. First, the suspension action is immediate and cheap: a single flag on the user record (`is_suspended = true`) prevents the account from posting and hides it from search. No follow edges are deleted yet. Second, the follow edge cleanup is a background process that runs in small batches over hours or days — something like "delete 1,000 rows per second from the follows table, spread across shards, with a rate limiter." This is invisible to users because the suspended account is already inaccessible. Third, counters are updated lazily — the follower count for the suspended account doesn't matter (users can't see it), and the following_count for each of the 80 million followers can be decremented as part of the background cleanup. The key insight is that "account suspended" and "follow edges deleted" are two separate events with very different urgency. The user-visible effect (account gone) must happen immediately; the storage cleanup can happen over days. This pattern — separate the user-visible state change from the expensive storage cleanup — is widely applicable in distributed systems.

**Q2: How do you make the follow/unfollow operation idempotent, and why does this matter?**

Idempotency means that performing the same operation multiple times produces the same result as performing it once. For follow/unfollow, idempotency matters because networks are unreliable. When Alice taps "Follow" on Bob's profile, her phone sends an HTTP request. If the request times out (maybe a spotty network connection), Alice's phone doesn't know if the server received it. The app will retry the request. Without idempotency, two follow events could be processed, resulting in a duplicate entry, an over-incremented counter, and two fan-out events being triggered. Making follow idempotent has two parts. At the database level, use `INSERT ... ON DUPLICATE KEY IGNORE` so that inserting the same (follower_id, followee_id) pair twice results in exactly one row. At the counter level, use a distributed deduplication system: each follow request carries a client-generated idempotency key (UUID). The server stores this key in a Redis set with a 24-hour TTL. Before processing any follow event, check if the idempotency key has been seen before — if yes, return a cached 200 OK without doing any work. This prevents double-counting even in the Kafka consumer pipeline, where at-least-once delivery guarantees mean events can be replayed. The combination of database-level deduplication (ON DUPLICATE KEY) and application-level deduplication (idempotency key cache) makes the entire write path safely retryable.

---

## Part 4: Follower/Following List Queries

### The Pagination Problem

When a user opens the "Followers" list on someone's Instagram profile, they see a list of accounts. There might be 100 accounts, or 80 million. The UI loads them in pages — you see the first 50, then scroll to load the next 50, and so on. This is **pagination**, and getting it right at scale requires understanding why the obvious approach is broken.

**The wrong approach: offset-based pagination**

```sql
-- Page 1: get first 50 followers
SELECT follower_id FROM follows
WHERE followee_id = :bob_id
ORDER BY created_at DESC
LIMIT 50 OFFSET 0;

-- Page 2: skip first 50, get next 50
SELECT follower_id FROM follows
WHERE followee_id = :bob_id
ORDER BY created_at DESC
LIMIT 50 OFFSET 50;

-- Page 1001: skip first 50,000 followers
SELECT follower_id FROM follows
WHERE followee_id = :bob_id
ORDER BY created_at DESC
LIMIT 50 OFFSET 50000;
```

The problem with OFFSET: MySQL (and every SQL database) implements `OFFSET N` by fetching N+limit rows and then discarding the first N. To get page 1001 (offset 50,000), the database fetches 50,050 rows and throws away 50,000 of them. This is wasted work that grows linearly with the page number. For Lady Gaga's 80 million followers, fetching page 1,000,000 would require reading 50,000,000+ rows and discarding almost all of them. This is completely unusable.

**The right approach: cursor-based pagination**

Instead of "skip N rows," you use "start after this specific row" — a **cursor**. The cursor is the key value of the last item you returned:

```sql
-- Page 1: no cursor, start from the beginning
SELECT follower_id, created_at FROM follows
WHERE followee_id = :bob_id
ORDER BY created_at DESC
LIMIT 50;
-- Returns rows with created_at values ending at, say, '2024-01-15 10:30:00'
-- The last row becomes the cursor

-- Page 2: "give me followers whose created_at is BEFORE the cursor"
SELECT follower_id, created_at FROM follows
WHERE followee_id = :bob_id
  AND created_at < '2024-01-15 10:30:00'
ORDER BY created_at DESC
LIMIT 50;
-- MySQL uses the index to jump directly to created_at = '2024-01-15 10:30:00'
-- No rows are scanned and discarded
```

With cursor pagination, every page fetch is equally fast because you're always reading from a known point in the index — no skipping, no wasted scans. The cursor is typically encoded as a Base64 string in the API response so the client doesn't have to know it's a timestamp:

```
API response:
{
  "followers": [...50 items...],
  "next_cursor": "eyJjcmVhdGVkX2F0IjogIjIwMjQtMDEtMTUgMTA6MzA6MDAifQ==",
  "has_more": true
}

Next API call:
GET /followers?user_id=bob&cursor=eyJjcmVhdGVkX2F0IjogIjIwMjQtMDEtMTUgMTA6MzA6MDAifQ==&limit=50
```

```
CURSOR PAGINATION vs OFFSET PAGINATION:

Offset pagination:
  Page 1:   [##########] read 50, skip 0,      return 50  -- fast
  Page 2:   [##################] read 100, skip 50, return 50  -- ok
  Page 100: read 5050, skip 5000, return 50  -- slow
  Page 1M:  read 50,000,050 rows, skip 50,000,000, return 50  -- BROKEN

Cursor pagination:
  Page 1:   seek to start -> [##########] read 50  -- fast
  Page 2:   seek to cursor -> [##########] read 50  -- fast
  Page 100: seek to cursor -> [##########] read 50  -- fast
  Page 1M:  seek to cursor -> [##########] read 50  -- still fast
```

### Follower Count as a Separate Counter

Never compute the follower count with `SELECT COUNT(*)`. Keep a separate counter in Redis:

```
Redis key: follower_count:{user_id}   → integer
Redis key: following_count:{user_id}  → integer

Operations:
  On follow:   INCR follower_count:{bob_id}
               INCR following_count:{alice_id}
  On unfollow: DECR follower_count:{bob_id}
               DECR following_count:{alice_id}
  On read:     GET follower_count:{bob_id}  → O(1), microseconds
```

The MySQL counters table serves as durable backup for Redis counters. On Redis restart or cache eviction, the counter is read from MySQL and loaded back into Redis. Because counter updates are async (via Kafka), there can be brief inconsistency — the Redis counter might differ from a fresh `COUNT(*)` by 1 or 2 during high write periods. This is acceptable: displaying "80,000,001" when the true count is "80,000,000" is invisible to users.

### Redis Sorted Set for Follower Lists

For users with moderate follower counts (say, under 10 million), store the entire follower list in a Redis sorted set:

```
Key:    followers:{bob_id}
Type:   Sorted Set (ZSET)
Member: follower_id (as string or integer)
Score:  follow_timestamp (Unix epoch, enables time-ordered retrieval)

Commands:
  ZADD followers:{bob_id} {timestamp} {alice_id}  -- on follow
  ZREM followers:{bob_id} {alice_id}               -- on unfollow
  ZREVRANGEBYSCORE followers:{bob_id} {cursor} -inf LIMIT 0 50  -- paginate
  ZCARD followers:{bob_id}                         -- count (O(1))
```

Redis sorted sets are implemented as skip lists. Every operation is O(log N) for inserts/deletes and O(log N + M) for range queries (where M is the number of results). For 10 million followers, that's O(log 10M) = O(~23 operations) for a lookup — extremely fast.

The memory cost: each Redis sorted set entry uses roughly 64–128 bytes (overhead for skip list node + the member + the score). For a user with 10 million followers: 10M × 100 bytes = 1GB. This is expensive for a single user. For Lady Gaga with 80M followers: 80M × 100 bytes = 8GB for just one user's follower list.

This is why celebrities need special handling. You cannot afford to store 8GB of Redis memory for one user's follower list. The solution: for high-follower accounts, serve the follower list directly from MySQL on demand (with a cursor-paginated query using the covering index), skipping the Redis cache. Alternatively, shard the large sorted set across multiple Redis keys (`followers:{bob_id}:shard_0`, `followers:{bob_id}:shard_1`, etc.) and merge at query time.

### 5-Level Progression: Follower/Following List Queries

**Intern:** "I'd do `SELECT follower_id FROM follows WHERE followee_id = bob_id LIMIT 50 OFFSET ?` with pagination. Simple SQL, easy to implement."

**Junior Engineer:** "Offset pagination breaks at scale — I'd switch to cursor-based pagination using the follow timestamp as the cursor. The SQL becomes `WHERE followee_id = bob_id AND created_at < {cursor} ORDER BY created_at DESC LIMIT 50`. I'd also add a covering index on `(followee_id, created_at DESC, follower_id)` so the query is an index-only scan — no need to touch the actual row data."

**Mid-level Engineer:** "For most users, I'd front the MySQL query with a Redis sorted set cache. The follower list for user X is `followers:{user_id}` — a Redis ZSET sorted by follow timestamp. On a follower-list request: check Redis first. If the full list is in Redis, serve it directly (O(log N) lookup). If not, query MySQL, populate Redis, return. For active users, the Redis cache hit rate will be near 100%. Set a TTL of 24 hours for inactive user lists to prevent Redis filling with cold data."

**Senior Engineer:** "At this scale, follower-list serving is a tiered problem. I'd classify users into three tiers: (1) Normal users with under 100K followers — serve from Redis ZSET, full list fits in a few MB. (2) Power users with 100K–1M followers — serve the first few pages from Redis, fall back to MySQL cursor queries for deep pages that are rarely accessed. (3) Celebrities with over 1M followers — don't cache the follower list in Redis at all (too expensive). Instead, always serve directly from a sharded MySQL covering-index scan with cursor pagination. For these users, even a covering index scan touching 80M rows is too slow — so I'd maintain a dedicated read replica with the followers table sorted by `(followee_id, created_at DESC)` as the clustered index, giving O(1) range access. The celebrity follower list is never shown in full anyway — the UI shows a count and a few sample followers, not all 80M."

**Staff Engineer:** "The follower-list serving problem is really a data locality and access-pattern problem in disguise. The key observation is that follower-list accesses follow a heavy-tailed distribution: 0.1% of users (celebrities) generate 50% of follower-list read requests. The 99.9% of normal users generate the other 50%. A uniform storage strategy fails both: too expensive for normal users (per-user Redis ZSET for 3 billion users = terabytes of memory), too slow for celebrities (Redis can't hold 8GB per celebrity follower list). The staff-level design separates these explicitly. For the normal-user case, follower lists live in the sharded MySQL cluster; a lightweight application-level cache (not Redis — just a local in-process LRU cache in each graph service pod) handles repeat requests for the same user. For celebrities, the serving path is entirely different: a pre-identified set of 'celebrity' user IDs (maintained by an account classification service) have their follower lists stored in a specialized column-store (like a Cassandra table sorted by followee_id + timestamp) optimized for time-ordered range scans. The column store is purpose-built for the read pattern: 'give me followers of user X, sorted by follow time, starting from cursor C.' The celebrity set is small enough that this specialized store is operationally manageable."

### Brainstorming Q&A

**Q1: A product manager asks you to add a feature: "Show followers in alphabetical order by username." How does this change your storage and serving design, and what are the tradeoffs?**

This request seems simple but has significant implications for the storage design. Currently, follower lists are stored sorted by follow timestamp — this is baked into the Redis ZSET score and the MySQL index order. Adding alphabetical ordering means sorting by username, which is a different field. Usernames can also change (users can update their username on most platforms), which makes them a bad sort key in a precomputed structure. There are three approaches with very different tradeoffs. First, sort at query time: fetch the full follower ID list, look up usernames for each follower, sort by username, then paginate. This is simple but requires a join between the follower list and the user table, which can be expensive for large follower counts. For a user with 10,000 followers, this might mean 10,000 user table lookups per sort operation — not great. Second, precompute the sorted order: maintain a separate data structure — another Redis ZSET with username as the score (encoded as a numeric rank) or a separate sorted table in MySQL. This doubles storage but makes alphabetical queries fast. The catch is that username changes require updating this structure. Third, limit the feature: show alphabetical order only for the first N followers (say, 1000) and fall back to time-ordered for the rest. This is what most products actually do. The product manager should understand that "show in alphabetical order" for a user with 80 million followers means either very expensive per-query sorting or significant storage overhead for precomputed order. In practice, this feature is almost always limited to accounts with smaller follower counts, or the sort is done client-side on a limited subset.

**Q2: How do you handle the case where a user's Redis follower set is evicted (because Redis ran out of memory) and a request comes in for their follower list? What's the cache warming strategy?**

Cache eviction is a guaranteed event at scale — Redis memory is finite, and LRU eviction will eventually remove cold data. The question is how gracefully the system handles a cache miss. The naive approach (query MySQL on every cache miss, populate Redis, return result) has a failure mode called the "thundering herd": if a celebrity's follower set is evicted, thousands of concurrent requests all miss the cache simultaneously, each triggering a MySQL query. This can overwhelm the database. The correct approach has three parts. First, the cache-aside pattern with distributed locking: when a cache miss is detected, only ONE request should trigger the MySQL rebuild. Use a Redis distributed lock (`SET cache_rebuild:{user_id} 1 NX EX 30`) — only the thread that acquires the lock does the MySQL query. All other threads either wait briefly and retry (for small datasets where rebuild is fast) or serve a stale response (for large datasets where rebuild takes seconds). Second, for large follower sets, don't load the entire set from MySQL — load only the first few pages (say, the 10,000 most recent followers). Subsequent pages are served from MySQL with cursor pagination. This limits the rebuild cost while keeping the common case (first page of followers) fast. Third, implement proactive cache warming for high-value accounts: a background job monitors which celebrity accounts are trending (about to get a surge of profile views) and pre-populates their cache tiers before traffic spikes. This turns reactive cache warming into proactive warming, eliminating the thundering herd at the cost of some background compute.

---

## Part 5: Mutual Connections (Set Intersection)

### What Is the Mutual Connections Query?

When you visit someone's LinkedIn or Facebook profile, you often see "3 mutual connections" along with small avatars of those shared connections. This seemingly simple feature requires computing the **intersection** of two potentially large sets:

- Set A: the set of people that YOU are connected to
- Set B: the set of people that THEY are connected to
- Intersection A ∩ B: people you are BOTH connected to

For Facebook friends, these sets are typically 200–2000 people each. For LinkedIn, a "power user" might have 30,000 connections. The intersection size is usually small (a handful of mutuals). The challenge is computing it efficiently, especially when called millions of times per second.

### Naive Approach: Load and Intersect

The simplest approach: load both connection lists into application memory and compute the intersection in code.

```python
# Pseudocode for naive set intersection
def mutual_connections(user_a_id, user_b_id):
    # Load from Redis or MySQL
    connections_a = get_following_set(user_a_id)  # e.g., {3, 7, 12, 99, ...}
    connections_b = get_following_set(user_b_id)  # e.g., {7, 42, 99, ...}
    
    # Python set intersection — O(min(|A|, |B|))
    mutual = connections_a & connections_b
    return mutual
```

For typical users with 200–500 connections each, this works fine. Loading 500 user IDs from Redis is fast (a few milliseconds), and in-memory set intersection of two 500-element sets is instantaneous.

The problem: what about LinkedIn power users with 30,000 connections? Loading 30,000 user IDs from Redis takes meaningful time. More importantly, this query might be called on every profile-view page load for the viewer AND the subject. If the subject has 30,000 connections and is getting 100 concurrent profile views, that's 100 concurrent 30,000-element set loads.

### Bloom Filter Pre-Filter

A **Bloom filter** is a probabilistic data structure that answers the question "is element X in this set?" with very little memory. It can have false positives (it might say "yes" when the answer is "no") but never false negatives (if it says "no," the answer is definitely "no").

For mutual connections, use a Bloom filter as a pre-filter:

```
For each user, maintain a Bloom filter of their connections.
  Size: roughly 10 bits per element for ~1% false positive rate.
  For 1000 connections: 1000 x 10 bits = 1.25 KB (tiny!)
  For 30,000 connections: 30,000 x 10 bits = 37.5 KB (still tiny!)

Mutual connection check:
  1. Load bloom_filter_B (Bloom filter for user B's connections) -- small, fast
  2. For each connection C of user A:
       if bloom_filter_B.might_contain(C):
           // C is PROBABLY a mutual -- verify with exact lookup
           if exact_check(C in connections_B):  // Redis O(1) SISMEMBER
               add C to mutual_connections
  
  This pre-filter means the expensive "exact lookup" only happens for
  likely mutuals, not all of A's connections.
```

In practice, if user A has 1000 connections and has 5 mutuals with user B, the Bloom filter with 1% false positive rate will produce about 10 "possible mutuals" that need exact verification — 5 true mutuals + ~5 false positives. Instead of 1000 exact lookups, you do 10. This is a 100x reduction.

### Sorted Merge Join: O(N + M)

If both connection lists are sorted (which they can be, if stored in sorted order by user_id), you can compute the intersection in a single O(N + M) pass — faster than loading both into hash sets:

```
User A's connections (sorted): [3, 7, 12, 42, 99, 200, ...]
User B's connections (sorted): [7, 15, 42, 99, 400, ...]

Two pointers:
  ptr_a -> 3,  ptr_b -> 7:   3 < 7,  advance ptr_a
  ptr_a -> 7,  ptr_b -> 7:   7 == 7, MUTUAL! Record 7, advance both
  ptr_a -> 12, ptr_b -> 15:  12 < 15, advance ptr_a
  ptr_a -> 42, ptr_b -> 15:  42 > 15, advance ptr_b
  ptr_a -> 42, ptr_b -> 42:  42 == 42, MUTUAL! Record 42, advance both
  ptr_a -> 99, ptr_b -> 99:  99 == 99, MUTUAL! Record 99, advance both
  ...

Result: mutuals = {7, 42, 99}
Time: O(N + M) where N = |A's connections|, M = |B's connections|
Space: O(1) extra memory (just two pointers)
```

This is the classic merge join algorithm from database internals. If you store connection lists in Redis sorted sets (sorted by user_id as the score), you can do this comparison without loading data into application memory — Redis's `ZINTERSTORE` command computes sorted set intersections natively. For large sets, this is the most memory-efficient approach.

### Scale Problem with High-Degree Nodes

Even O(N + M) breaks down when N or M is very large. If user A is a LinkedIn power user with 30,000 connections, every mutual-connection query involving A requires reading all 30,000 of A's connections. This is unavoidable with exact mutual-connection computation.

The practical solution used by most social platforms:

1. **Cap the computation** — Only compute mutuals for the first K connections of each user (e.g., K = 1000 most recent). This covers 99% of real users and gives approximate results for power users.

2. **Approximate mutual counts** — For display purposes ("3 mutual friends"), you don't need exact count — you just need a small sample and a roughly correct count. Approximate using a random sample of each user's connections.

3. **Offline precomputation** — For pairs of users that are likely to view each other's profiles (e.g., users in the same geographic region, users with many shared connections), precompute mutual connections offline in Spark. Cache the result. When the profile view happens, the mutuals are already computed.

4. **Limit depth** — Show only the first 3–5 mutual connections (not all mutuals) in the UI. Stop the intersection once you find 5 mutuals and report "N+ mutual connections" instead of an exact count.

### 5-Level Progression: Mutual Connections

**Intern:** "I'd load both users' friend lists, compute the intersection in Python using set operations, and return the result. For 200 friends each, this is fast enough."

**Junior Engineer:** "I'd use Redis SINTER or ZINTERSTORE to compute the intersection server-side rather than loading both lists into application memory. Redis can compute the intersection of two sorted sets natively, and the result is returned in one round trip. I'd also cache the result (mutual_connections:{user_a}:{user_b}) with a 5-minute TTL since mutual connections don't change that often."

**Mid-level Engineer:** "For the majority of users, Redis ZINTERSTORE works great. For power users with very large connection sets, I'd add the Bloom filter pre-filter: maintain a Bloom filter per user (stored as a Redis string or BitField), check it first to identify candidate mutuals, then verify with exact lookups. I'd also implement the cap: only compute mutuals over the most-recently-added 2000 connections per user to bound the worst case. Set the cap high enough that it covers all real mutual connections (in practice, if you have 2000 common connections, the UI is only showing 5 of them anyway)."

**Senior Engineer:** "At LinkedIn scale (1B users, some with 30K connections), mutual connections must be partially precomputed offline. I'd run a nightly Spark job that identifies 'likely profile view pairs' — pairs (A, B) where A and B have overlapping social circles, work at the same company, or attended the same school. For each such pair, precompute and cache mutual connections. When a profile view happens, the cached result is served instantly for the common case. For uncommon profile views (where no precomputation exists), fall back to the online computation with a strict time budget: compute for up to 100ms, return whatever mutuals are found, and start an async job to compute the full result for caching."

**Staff Engineer:** "Mutual connections is a classic example of a feature that looks trivial but has O(N x M) worst-case behavior that will destroy your infrastructure if you're not careful. The right framing is: what user behavior makes this expensive, and can you eliminate that behavior? Users with extremely high connection counts (30,000+) generate catastrophically expensive mutual-connection queries. LinkedIn solved this partly by design: they enforce a 30,000 connection limit per user. This is not a technical limitation — it's a deliberate product decision to bound the worst-case query cost. Beyond that, the staff-level insight is that 'mutual connections' is really two separate features: (1) the count shown on a profile card ('N mutual connections'), and (2) the detailed list shown when you click. These have different latency budgets and accuracy requirements. The count can be approximate and can be precomputed offline with a Spark job that runs nightly. The detailed list needs to be accurate but is loaded lazily (only when the user clicks). Precompute the count for every probable pair, serve it instantly, and only run the expensive exact intersection when the user explicitly asks to see the list."

### Brainstorming Q&A

**Q1: LinkedIn shows "500+ connections" rather than an exact count for users with very high connection counts. Is this a product shortcut or a deliberate engineering decision?**

It is both — a deliberate product and engineering decision that conveniently solves a real technical problem. From the product perspective, "500+ connections" signals "this person is well-networked" as effectively as "8,342 connections" while being simpler to display and less creepy (displaying someone's exact connection count down to the unit feels oddly precise). From the engineering perspective, computing an exact count for 30,000+ connection users requires a full scan of their connection list every time a profile is viewed, which is expensive. More importantly, the mutual-connections computation becomes O(30,000) in the worst case, which is slow. By capping the displayed count at 500+ and only computing mutuals over a bounded set, LinkedIn bounds their worst-case query cost. This is a general principle in systems design: adding a "cap" or "approximate" label to a display value is often the correct engineering choice, not a compromise. Users do not need exact precision in social signals. The engineering team saves significant resources by serving approximate values, and the product is not meaningfully worse. When you see these caps in social products (Twitter's follower count rounds to nearest thousand for large counts, Instagram shows "1.2M" not "1,234,567"), they are almost always deliberate engineering decisions dressed up as product decisions.

**Q2: How would you implement the mutual connections feature for a graph that changes constantly — people are adding and removing connections at high rates — so that the cached mutual-connection results stay fresh?**

This is a cache invalidation problem with a graph-shaped dependency structure. When user A and user C establish a connection, every cached mutual-connection result that involves either A or C might be stale. If A has 1000 connections, there are 1000 potentially stale cached mutual-connection entries (one for each of A's existing connections with user C). Invalidating all of them on every connection change is O(N) cache invalidations per write, which is prohibitively expensive at scale. The practical approach is TTL-based invalidation rather than event-driven invalidation. Set the mutual-connections cache TTL to something short enough to be "fresh enough" without requiring explicit invalidation — 5 to 30 minutes is typical. This means cached mutual-connection results can be up to 30 minutes stale, which users almost never notice. The edge cases (you and someone share a new connection and it doesn't show up as mutual for 30 minutes) are rare and low-impact. For the offline precomputed results (the daily Spark job), staleness is inherent — the batch result is up to 24 hours old. Again, this is acceptable because mutual connections rarely change dramatically overnight. The key engineering insight is: "fresh enough" is not the same as "always fresh." Identify the acceptable staleness for each feature, and design the cache strategy to meet that SLA — not to be maximally fresh.

---

## Part 6: People You May Know (PYMK)

### The PYMK Problem

"People You May Know" (also called "Friend Suggestions" or "Who to Follow") is the feature that suggests new connections to users. It appears prominently on LinkedIn, Facebook, Instagram, and Twitter. It is one of the most impactful growth features in social products — a good PYMK recommendation can dramatically increase connection density and user engagement.

The core algorithmic problem: for each user X, find the set of people who are NOT currently connected to X but have a high probability of being someone X would connect with. The primary signal used by every social network is **2-hop connections** — people you might know because you have mutual connections with them.

```
2-hop connection example:
  Alice -> Bob (Alice follows Bob)
  Bob -> Charlie (Bob follows Charlie)
  
  Charlie is a 2-hop connection from Alice.
  "You might know Charlie because you both follow Bob."
  -> Charlie is a PYMK candidate for Alice.
```

The math: if Alice follows 200 people, and each of those 200 people follows 200 people, there are potentially 200 × 200 = 40,000 two-hop candidates. After deduplicating (some people appear as 2-hop candidates through multiple paths) and removing people Alice already follows, you might have 10,000 unique PYMK candidates. Ranking these 10,000 candidates to show the best 10–20 is the PYMK problem.

### Why You Cannot Compute PYMK Live

Consider computing PYMK for a single user in real time:

1. Load Alice's following list: 200 users
2. For each of those 200 users, load their following lists: 200 × 200 = 40,000 requests
3. Deduplicate and remove already-followed users: O(40,000) work
4. Score each candidate: requires additional data (profile completeness, common interests, geographic proximity)
5. Return top 10

That's 40,000 network round trips to the social graph serving layer, just for one user. Now multiply by millions of users requesting PYMK simultaneously. This would generate billions of social graph queries per second — completely impossible.

The solution: **compute PYMK offline** as a batch job, cache the results, and serve from cache.

### Offline PYMK with Spark GraphX

Apache Spark GraphX is a distributed graph processing framework built on top of Spark. It can process graphs with billions of nodes and edges across a cluster of machines. The PYMK computation runs as a nightly (or hourly) Spark job:

```
PYMK Spark Job (pseudocode):

Input: graph snapshot stored in HDFS
  edges.parquet: (source_user_id, dest_user_id, edge_timestamp)

Step 1: For each user X, compute 2-hop neighbors
  graph.aggregateMessages(
    sendMsg = edge => edge.dstAttr.followers,  // propagate follower sets
    mergeMsg = (a, b) => a.union(b)
  )
  // After this, each node has a set of 2-hop candidates

Step 2: Remove already-connected users from candidate sets
  candidates = twohop_candidates - direct_connections

Step 3: Score candidates
  For each (user X, candidate Y):
    score = mutual_connection_count(X, Y) * weight_mutual
           + same_workplace(X, Y) * weight_workplace
           + same_school(X, Y) * weight_school
           + profile_completeness(Y) * weight_completeness
           + ...

Step 4: Take top K candidates per user
  results = candidates.groupBy(user_id).top(50, by=score)

Step 5: Write results to serving store
  results.write.format("cassandra").save("pymk_recommendations")
```

The job runs on a snapshot of the entire social graph (exported from MySQL to HDFS as Parquet files). For a graph with 3 billion nodes and 100 billion edges, this job might run for several hours on a large Spark cluster. The result (top-50 PYMK candidates per user) is written to a Cassandra table that the online serving layer reads from in milliseconds.

```
PYMK Computation Pipeline:

  MySQL (ground truth)
       | nightly export
       v
  HDFS (graph snapshot as Parquet)
       | Spark GraphX job (2-3 hours)
       v
  PYMK results (top 50 per user)
       | write
       v
  Cassandra (serving store)
       | millisecond reads
       v
  PYMK API (serves recommendations to the app)
```

### Ranking PYMK Candidates

Having 50 candidates is not enough — you need to rank them. The ranking signals used by real social networks:

1. **Mutual connection count** — The more mutual connections you share with a candidate, the higher the rank. This is the strongest signal.
2. **Recency of mutual connections** — If you and the candidate JUST mutually connected to the same person, that's a stronger signal than if the connection is 5 years old.
3. **Workplace and school** — LinkedIn uses this heavily. Same employer or same university dramatically boosts the score.
4. **Geographic proximity** — Nearby users are more likely to know each other.
5. **Profile similarity** — Similar job titles, industries, or interests.
6. **Reciprocal candidate interest** — If the candidate has shown interest in your content (liked your posts, viewed your profile), they score higher.
7. **Account quality** — Spam accounts and low-quality accounts are filtered or downranked.

These signals are combined using a ranking model — typically a logistic regression or gradient boosted tree trained on historical data (when user X was shown candidate Y, did X connect with Y?). The model outputs a probability score for each candidate, and candidates are sorted by this score.

### Cold Start: New User with 0 Connections

A new user who just signed up has no connections. The 2-hop algorithm produces zero candidates. This is the **cold start problem**.

Solutions for cold start PYMK:

1. **Phone book import** — Ask the user to sync their phone contacts. Match phone numbers against the user database. Suggest everyone in their contacts who is already on the platform.

2. **Email import** — Similar to phone book: import contacts from Gmail or Outlook and suggest matches.

3. **Onboarding interests** — During signup, ask "what topics are you interested in?" (tech, sports, music, etc.). Suggest popular accounts in those topics.

4. **Geographic suggestions** — Suggest popular local accounts in the user's city.

5. **Interest-based embedding** — If the user has a profile with employer and school, use that to suggest former colleagues and classmates even before they've made any connections.

6. **Trending accounts** — Show globally popular accounts (not personalized, but better than nothing).

After the user makes their first few connections, the 2-hop algorithm starts generating personalized candidates, and the cold-start suggestions phase out.

### 5-Level Progression: PYMK

**Intern:** "I'd do a 2-hop query: find who Alice follows, then find who each of those people follows, deduplicate, filter out Alice's existing connections, and show the results. Sort by how many mutual connections each candidate has."

**Junior Engineer:** "Computing 2-hop in real time is too expensive for large users. I'd precompute PYMK results nightly using a SQL query or a MapReduce job and store results in a lookup table. When the PYMK API is called, it reads from the precomputed table in milliseconds. I'd also add basic scoring: sort by mutual connection count descending."

**Mid-level Engineer:** "I'd use Spark GraphX for the offline computation since it's designed for exactly this graph processing pattern. The job runs nightly, computes top-50 candidates per user, and writes to Cassandra. I'd add the full scoring model: mutual connections, workplace, school, geography, profile quality. I'd also handle the cold-start case by adding the phone-book and interest-based fallbacks during the onboarding flow."

**Senior Engineer:** "The nightly batch introduces up to 24 hours of staleness — if I follow a new person today, my PYMK results won't reflect their connections until tomorrow. For a better user experience, I'd add a real-time layer on top of the batch layer. When Alice follows Bob, I trigger a lightweight real-time PYMK update: compute the 2-hop expansion from Bob in real time (Bob's followees are PYMK candidates for Alice), score them quickly, and merge the real-time results with the batch results. This is the Lambda architecture pattern: offline batch for coverage, online real-time for freshness. I'd also add feedback loops: if Alice dismisses a PYMK candidate, record that and exclude them from future suggestions. The ML model should be trained on both positive signals (connected) and negative signals (dismissed)."

**Staff Engineer:** "PYMK at scale is a multi-stage ML pipeline with feedback loops that need careful engineering. Stage 1 is candidate generation (the graph problem): produce a set of O(50–100) candidates per user using the 2-hop heuristic, computed offline in Spark. This is a recall problem — cast a wide net. Stage 2 is scoring (the ranking problem): score each candidate using a feature-rich ML model. Features include graph features (mutual count, mutual weight) plus content features (similar bios, interests, geographic features, activity signals). The ranking model is trained offline on historical data but must be served online (the app calls the PYMK ranking service which scores each candidate in a few milliseconds). Stage 3 is filtering: remove dismissed candidates, suspended accounts, blocked users, and privacy-restricted profiles. Stage 4 is personalized reranking: adjust scores based on recent activity (user just viewed a candidate's profile → boost that candidate). The staff-level challenge is managing the feedback loop: PYMK recommendations affect who users connect with, which changes the graph, which changes future PYMK recommendations. If the model has a bias (e.g., overweights users from certain demographics), it can create a feedback loop that reinforces that bias. The ML team must monitor for feedback-loop amplification and regularly retrain the model on balanced datasets."

### Brainstorming Q&A

**Q1: The Spark GraphX PYMK job runs nightly and takes 3 hours. The data team wants to run it hourly for fresher recommendations, but the cluster can't handle 6 concurrent jobs. How do you make the job faster?**

Making a large Spark job faster is a multi-dimensional problem involving both algorithmic optimization and infrastructure tuning. The most impactful algorithmic change is to run incremental PYMK rather than recomputing from scratch. A full recomputation processes the entire 100-billion-edge graph even though only a small fraction of edges change each hour. Incremental processing works by tracking which users had their follow graph change in the last hour (from the Kafka follow-event stream), and only recomputing PYMK candidates for those users and their affected 2-hop neighborhoods. If 1 million users had follow events in the last hour, and each has ~200 connections, you need to recompute PYMK for at most 200 million affected nodes — a fraction of the full graph. The tricky part is correctly identifying the full affected set (a change to user X's connections affects PYMK candidates for all of X's followers, and potentially their followers), but with careful boundary conditions, you can limit recomputation to the truly affected subset. On the infrastructure side, you can optimize by storing the graph in a more efficient columnar format (ORC or Parquet with predicate pushdown), using graph-partition-aware Spark scheduling to reduce cross-partition shuffles, and caching the frequently-accessed parts of the graph in Spark's memory tier. Together, incremental processing plus infrastructure tuning can reduce a 3-hour job to under 30 minutes, enabling hourly runs without expanding the cluster.

**Q2: How would you evaluate whether your PYMK system is actually good? What metrics would you track?**

Measuring PYMK quality requires both offline and online metrics that measure different aspects of the system. Offline metrics (computed without showing recommendations to users) include precision (of the candidates generated, what fraction does the user eventually connect with?), recall (of all connections the user makes in the next week, what fraction were in our PYMK suggestions?), and coverage (what percentage of users get at least one PYMK suggestion?). These are computed on historical data and give a quick way to compare algorithm versions. Online metrics (measured via A/B experiments with real users) are more important because they measure actual user behavior. The primary metric is connection rate: of users shown PYMK, what fraction make at least one connection from the suggestions? Secondary metrics include the specific connection rate per PYMK card (which positions in the list get the most connections), the dismissal rate (how often do users actively dismiss suggestions — high dismissal means suggestions are bad), and downstream engagement (do users who connect via PYMK engage with their new connection's content?). There is also an important long-term metric: are connections made via PYMK "good" connections? A recommendation system that maximizes short-term connection rates but produces weak connections (users stop engaging with each other after a week) is optimizing the wrong thing. Long-term relationship health — measured by the ongoing interaction rate between PYMK-connected users over 90 days — is the truest measure of recommendation quality and is often at odds with short-term click-through metrics.

---

## Part 7: Graph Traversal at Scale

### Breadth-First Search and Its Problem at Web Scale

The simplest graph traversal is **BFS (Breadth-First Search)**. Starting from a source node, BFS explores all neighbors first, then neighbors of neighbors, and so on. This is how "degree of separation" is computed — how many hops does it take to get from user A to user B?

```
BFS from Alice to find Bob:

Level 0: {Alice}
Level 1: {everyone Alice follows}               ~200 nodes
Level 2: {everyone Alice's connections follow}  ~200x200 = 40,000 nodes
Level 3: {two-hop neighbors' connections}       ~200x200x200 = 8,000,000 nodes
...

At Level 3-4, you've potentially covered all 3 billion users
(because the Facebook average separation is ~3.57 degrees).
```

Single-direction BFS from Alice reaches 8 million nodes after 3 hops. The social graph is so densely connected that BFS expands explosively. For a degree-of-separation query between Alice and a random other user, single-direction BFS would explore millions of nodes before finding the path.

### Bidirectional BFS: The Key Optimization

**Bidirectional BFS** runs two simultaneous BFS searches: one forward from the source (Alice) and one backward from the destination (Bob). When the two frontiers meet (a node appears in both searches), the path is found.

```
Standard BFS (one direction):
  From Alice, Level 3: 200^3 = 8,000,000 nodes explored

Bidirectional BFS (both directions simultaneously):
  From Alice, Level 1: 200 nodes
  From Bob,   Level 1: 200 nodes
  From Alice, Level 2: 200^2 = 40,000 nodes
  From Bob,   Level 2: 200^2 = 40,000 nodes
  Total explored: ~80,400 nodes
  Meet at Level 2 (each side did 2 hops = path length 4 hops)

Savings: 8,000,000 vs 80,400 = ~100x fewer nodes explored!
```

The math: if the graph has branching factor b (average ~200 for social graphs) and the shortest path has length d, standard BFS explores O(b^d) nodes. Bidirectional BFS explores O(2 x b^(d/2)) = O(b^(d/2)) nodes — exponentially fewer.

```
BIDIRECTIONAL BFS ILLUSTRATION:

Alice ---> [frontier A]
             [frontier A expands]
                [frontier A expands]
                    #### <- MEET POINT
                 [frontier B expands]
             [frontier B expands]
Bob  ---> [frontier B]

Each side only searches to the midpoint.
Total search space is roughly the square root of single-direction search.
```

Facebook used bidirectional BFS to compute the famous "3.57 degrees of separation" result — the average shortest path between any two Facebook users is 3.57 hops. This was computed in 2016 on a graph of 1.6 billion users.

### PageRank for Feed Ranking

**PageRank** is the algorithm Google invented to rank web pages by importance. The idea: a page is important if many other important pages link to it. This is recursive — "important" is defined in terms of other "important" pages.

Applied to social graphs: a user is influential if many influential users follow them. This gives you a measure of social authority that is more nuanced than raw follower count (having 1 million bot followers is different from having 1 million real, engaged followers who are themselves influential).

The PageRank formula:
```
PR(u) = (1 - d) + d x SUM [PR(v) / out_degree(v)]
                       for all v that follow u

where:
  PR(u) = PageRank score of user u
  d     = damping factor (~0.85)
  v->u  = all users v who follow u
  out_degree(v) = number of people v follows
```

Intuitively: your PageRank score is the sum of a fraction of each of your followers' PageRank scores. Following someone "transfers" some of your social authority to them.

PageRank in social networks is used for:
- **Feed ranking** — Posts from high-PageRank accounts get boosted in feeds
- **Search ranking** — When you search for a person, accounts with higher PageRank appear first
- **PYMK ranking** — Candidate accounts with higher PageRank are suggested more prominently
- **Spam detection** — Spam accounts have very low PageRank (real users don't follow spam); this is a useful anti-spam signal

PageRank is computed iteratively in Spark — start with all users having equal score, then apply the formula repeatedly until scores converge. Convergence typically takes 20–50 iterations. Each iteration is a full graph pass, so this is an offline batch computation.

### Graph Partitioning

**Graph partitioning** is the problem of splitting a graph across multiple machines in a way that minimizes cross-machine edges (network traffic) while keeping each partition roughly the same size. Good partitioning is critical for the performance of distributed graph algorithms.

The challenge with social graphs: they follow a **power-law distribution** (also called a "scale-free" graph). A few nodes (celebrities) have millions of edges; most nodes have only a few hundred. This makes balanced partitioning nearly impossible with simple strategies like "assign user X to shard X mod 1000."

```
Power-law degree distribution:

  Many users    |###################
  (low degree)  |############
                |#######
                |####
                |###
                |##
  Very few      |#
  (celebrities) |#
                +-----------------------------------
                 0    100K    1M    100M
                              Follower count

Most users have ~200 connections.
A handful have 80 million.
```

**METIS** is a graph partitioning algorithm designed for exactly this problem. It recursively bisects the graph, at each step finding the cut that minimizes cross-partition edges while balancing partition sizes. METIS produces high-quality partitions but requires the full graph to be in memory, which limits its use to smaller graphs or it must be run on the graph cluster itself.

For social graphs at scale, **streaming graph partitioning** is used: as new edges are added (people follow each other), the partitioning algorithm makes a real-time decision about which shard to place the new edge on, based on where the endpoint nodes currently live. This is less optimal than METIS but scales to trillion-edge graphs.

### 5-Level Progression: Graph Traversal

**Intern:** "I'd implement BFS using a queue. Start from the source, explore neighbors level by level, stop when I find the destination."

**Junior Engineer:** "Standard BFS is too slow for finding degrees of separation in a graph of billions of users. I'd implement bidirectional BFS — expand from both the source and destination simultaneously, stop when the frontiers meet. This reduces explored nodes from O(b^d) to O(b^(d/2)), which is exponentially better."

**Mid-level Engineer:** "For degree of separation queries, I'd implement bidirectional BFS with optimizations. Keep a hash set of visited nodes for each frontier — checking if a node is in the opposite frontier is O(1). Process the smaller frontier first at each step (if one side has 200 nodes and the other has 40,000, expand the 200-node side — this is the 'meet in the middle' optimization). For PageRank, run it as an offline Spark job using the Pregel computation model built into GraphX — it's designed for iterative graph algorithms."

**Senior Engineer:** "For large-scale graph traversal, the bottleneck is not computation but data locality. When BFS expands a node, it needs to load that node's edge list. If that edge list lives on a remote machine (different shard), you have a network call. The BFS frontier is essentially a set of random-access requests scattered across all shards — terrible for cache locality. The mitigation: (1) Graph partitioning that co-locates densely connected nodes on the same shard (friends of friends on the same machine = BFS expansion stays local). (2) For degree-of-separation queries, batch multiple user-pair queries together so that the same edge lists are read from cache for multiple concurrent queries. (3) For PageRank and other iterative algorithms, use Spark's graph partitioning (EdgePartition2D in GraphX) which balances both vertex loads and communication."

**Staff Engineer:** "Graph traversal at the scale of 3 billion nodes and 100 billion edges cannot be done on a traditional compute cluster with standard BFS. The state of the art is specialized graph processing systems. Facebook's Giraph (and its successor) uses the Pregel programming model: each vertex runs a user-defined compute function, sends messages to neighbors, and receives messages. This vertex-centric model maps naturally to distributed execution — each worker handles a partition of vertices and processes them in parallel. The communication pattern (vertex A sends message to vertex B's partition) maps to network I/O between workers. The critical optimization is combiner functions: instead of sending one message per edge, aggregate all messages to the same destination vertex into a single message (for PageRank, this means summing all incoming scores before sending). This reduces network traffic by the average in-degree (~200x reduction). For the specific case of bidirectional BFS on the social graph, Facebook built a custom system (not general-purpose GraphX) that holds the entire social graph in RAM across a large cluster, achieving BFS traversal rates of hundreds of millions of edges per second. The key is that degree-of-separation is a latency-sensitive, user-facing query — a user is waiting for the result. Everything else (PageRank, PYMK) is offline batch. Optimize the latency-sensitive path with specialized in-memory infrastructure, and run the batch computation with standard Spark on cheaper hardware."

### Brainstorming Q&A

**Q1: Facebook announced that the average degree of separation between Facebook users dropped from 6 (Milgram's original finding in 1967) to 3.57. How was this computed, and what makes it methodologically interesting?**

The 2016 Facebook computation was done by running a BFS from every user on the Facebook graph and computing the average shortest path length. At 1.6 billion users, running a full all-pairs BFS is computationally infeasible — the number of pairs is 1.6B squared / 2, far too many to compute directly. Instead, Facebook used a statistical sampling approach: run exact BFS from a large random sample of users (millions of source users, not all 1.6 billion), compute the average path length from those samples to all reachable users, and use that as an estimate of the global average. The result, 3.57 degrees, is an estimate with a confidence interval, not an exact figure — but the confidence interval is tight enough that 3.57 is a very good approximation. The methodologically interesting part is what "3.57 degrees" actually means. It is the average over ALL pairs of users — including pairs who are in the same city, in the same company, in the same family. These pairs are likely to be very close (1–2 hops). Random pairs of users from different countries and different social circles contribute longer paths (5–6 hops). The average masks a bimodal distribution: most pairs are close (because Facebook users tend to be densely connected within their immediate social circle) with a long tail of pairs that require 5–6 hops. The "world is small" phenomenon is real, but 3.57 is in some ways misleadingly low — it includes all the pairs that are trivially close.

**Q2: Why does graph partitioning matter for distributed graph computation, and why is it hard for social graphs specifically?**

Graph partitioning matters because distributed graph algorithms like BFS, PageRank, and PYMK need to traverse edges. When an algorithm on machine A needs to follow an edge to a node that lives on machine B, that requires a network call — typically 1,000x slower than accessing local memory. If the graph is badly partitioned (many edges cross machine boundaries), the algorithm spends most of its time waiting on network I/O rather than doing computation. A good partition minimizes the number of cross-partition edges, keeping most edge traversals local. The reason this is hard for social graphs specifically is the power-law degree distribution. High-degree nodes (celebrities with millions of followers) are connected to nodes scattered across every shard, regardless of how you partition. There is no way to co-locate a celebrity with all their followers — the celebrity would need to be on every shard simultaneously. Algorithms like METIS can minimize cross-partition edges for the average case, but celebrities always generate cross-partition traffic. One mitigation is to replicate celebrity nodes — put a copy of Lady Gaga's node (and her edge list) on every shard, so every shard can access her edges locally. This trades storage for network traffic. Another is to treat celebrities specially in the algorithm: partition the graph for normal users and process celebrity edges as broadcast operations (send to all workers at once), which is efficient for the all-to-one pattern that celebrity follower-list traversal resembles. The fundamental tension — power-law graphs have irreducibly "difficult" high-degree nodes — is why social graph computation has been a rich research area for the last 15 years.

---

## Part 8: Graph Serving Infrastructure

### TAO Two-Tier Memcache: Deep Dive

We introduced TAO in Part 2. Here we go deeper into why the two-tier cache architecture works and how consistency is maintained.

**Why two tiers?**

A single Memcache cluster in front of MySQL would work, but at Facebook's scale it creates problems. Facebook has many thousands of web and app servers, all sending requests to a single Memcache cluster. A single large cluster becomes a bottleneck — the cluster's network bandwidth limits how many requests per second it can handle.

The two-tier architecture solves this by adding regional follower caches:

```
TAO TWO-TIER ARCHITECTURE (per data center):

+------------------------------------------------------------------+
|                 THOUSANDS OF WEB/APP SERVERS                     |
|  (each runs a local TAO client library)                          |
+---------------------------+--------------------------------------+
                            | All read/write requests
                            v
+------------------------------------------------------------------+
|              TAO FOLLOWER TIER                                   |
|   Multiple independent Memcache clusters (called "pools")        |
|   Each pool serves a subset of web servers                       |
|   Pool 1: web servers 0-999                                      |
|   Pool 2: web servers 1000-1999                                  |
|   Pool 3: web servers 2000-2999                                  |
|   ...                                                            |
|   On cache miss: asks TAO Leader (NOT MySQL directly)            |
+---------------------------+--------------------------------------+
                            | cache miss OR write request
                            v
+------------------------------------------------------------------+
|              TAO LEADER TIER                                     |
|   One Memcache cluster per database shard                        |
|   ALL writes go through the leader (serialization point)         |
|   Leader coordinates cache invalidation across follower pools    |
|   On cache miss: reads from MySQL, populates its cache           |
+---------------------------+--------------------------------------+
                            | write-through / cache miss fill
                            v
+------------------------------------------------------------------+
|              MySQL STORAGE                                       |
|   Sharded by object/association ID                               |
|   Ground truth, always consistent                                |
+------------------------------------------------------------------+
```

**How writes work in TAO:**

When Alice follows Bob (a new FOLLOWS association from Alice's node to Bob's node):

1. The TAO client sends the write to the TAO Leader for the shard containing Alice's node.
2. The Leader writes the association to MySQL (synchronous — waits for MySQL confirmation).
3. The Leader updates its own Memcache entry for the relevant association list.
4. The Leader sends invalidation messages to all TAO Follower pools that might have cached Alice's association list.
5. The Follower pools delete (invalidate) their stale cached copies.
6. Future reads for Alice's association list will miss the Follower cache, go to the Leader, and get the fresh data.

Step 4 (invalidation) is the key to consistency. The Leader knows exactly which Follower pools might have the stale data (because the Follower pools register which data they have cached). Invalidation messages are sent to each Follower pool via a dedicated invalidation channel.

**Cache hit rates and efficiency:**

The two-tier architecture gives excellent cache hit rates:
- Most reads (profile views, feed loads) read the same popular associations repeatedly (celebrity follower lists, popular page association counts)
- Follower tier caches these per-region: all web servers in the same pool share the same cache → high hit rate within the pool
- Leader tier acts as a second-level cache: even if all Follower pools evict an entry, the Leader likely still has it → very few actual MySQL reads

Typical TAO hit rate at Facebook: >99% of reads are served from cache (Follower or Leader tier). MySQL only handles <1% of read traffic.

### Twitter's Full In-Memory Graph

Twitter's approach is more radical than TAO: load the entire social graph into RAM on dedicated graph serving machines.

**The math:**

```
Twitter scale (approximate, c. 2019):
  Active users:          ~350 million
  Average follows/user:  ~200
  Total edges:           350M x 200 = 70 billion

Memory per edge:
  follower_id:  8 bytes (64-bit integer)
  followee_id:  8 bytes
  Per edge:    16 bytes

Total edge memory:  70B x 16 bytes = 1.12 terabytes
Plus index overhead (~2x): ~2.24 terabytes

Modern high-memory servers: 1-4 TB RAM each
A cluster of 3-4 such servers holds the entire Twitter social graph in RAM.
```

This is the beautiful insight: with modern hardware, the social graph of a 350M-user network fits entirely in RAM. Memory access is ~100 nanoseconds; disk access is ~100 microseconds; a MySQL query is ~10 milliseconds. In-memory graph serving is 100,000x faster than MySQL for graph queries.

**Structure of the in-memory graph:**

```
Follower graph (for feed fan-out, PYMK):
  array indexed by user_id -> pointer to follower list
  follower list = array of {follower_id, follow_timestamp}
  
  user_id_index: [ptr_0, ptr_1, ..., ptr_350M]    // 350M x 8 bytes = 2.8 GB
  edge_data:     [{7, ts1}, {42, ts2}, ...]         // 70B x 16 bytes = 1.12 TB

Following graph (mirror -- for profile page "who does X follow?"):
  Same structure, indexed by follower_id instead
```

**Sharding the in-memory graph:**

Even at 2.24 TB, you don't want it all on one machine (single point of failure, too much pressure on one box). Shard by `user_id % num_shards`:

```
Shard 0: users 0, 4, 8, 12, ...     (every 4th user)
Shard 1: users 1, 5, 9, 13, ...
Shard 2: users 2, 6, 10, 14, ...
Shard 3: users 3, 7, 11, 15, ...
```

A follower-list query for user X goes to exactly one shard: `shard = X % 4`. Fan-out (all followers of X) is served by that same shard. A following-list query for user X also goes to the same shard. This is shard-local — no cross-shard coordination for basic queries.

**Replica lag:**

The in-memory graph is not the source of truth — MySQL is. The in-memory graph is built by loading a snapshot from MySQL and then applying a stream of follow/unfollow events (from Kafka) as they happen. There is a brief lag (typically under a second) between a follow event hitting MySQL and propagating to the in-memory graph. This is acceptable for all social graph use cases: seeing a new follower appear with a 500ms delay is invisible to users.

If a graph serving machine crashes and restarts, it must rebuild its portion of the in-memory graph by replaying the Kafka event stream from the beginning (or from a recent checkpoint). This can take minutes. During rebuilding, that shard is temporarily unavailable, and reads for those users fall back to MySQL (slow but correct). Once rebuilt, the machine rejoins the serving pool.

```
IN-MEMORY GRAPH SERVING -- SHARDED:

  HTTP request: "who follows user 12345?"
        |
        v
  Graph Router: user_id 12345 -> shard 12345 % 4 = shard 1
        |
        v
  Graph Shard 1 (in-memory):
    user_index[12345] -> pointer to follower_list_for_12345
    follower_list = [{alice, ts1}, {bob, ts2}, ..., {N_followers}]
        |
        v (microseconds)
  Return follower list to router
        |
        v
  HTTP response

  -----------------------------------------------------------------------
  Kafka follow-events stream:
    consumer on each shard applies updates to in-memory structure
    lag: typically < 500ms from follow event to in-memory update
```

### Sharding by User ID: Detailed Design

Choosing the right sharding key and shard count requires balancing several concerns:

**Shard count:** too few shards → each shard is too large (more memory per machine, more rebuild time on restart). Too many shards → too many machines to manage, network fan-out for broadcast operations is expensive. For Twitter's graph, 256–512 shards is typical for a balanced tradeoff.

**Consistent hashing vs. modulo sharding:**

Simple modulo (`user_id % num_shards`) is simple but inflexible — adding a new shard requires rehashing all data. Consistent hashing uses a hash ring where each shard "owns" a range of the hash space, and adding a shard only moves a fraction of the data.

```
Consistent hashing ring (simplified):

         Shard A
        /       \
   Shard D     Shard B
        \       /
         Shard C

  Each shard owns an arc of the ring.
  user_id is hashed to a point on the ring.
  The nearest shard clockwise owns that user_id.
  Adding Shard E: only moves the data it "cuts off" from existing shards.
  Adding a shard with modulo hashing: rehashes ~50% of all data.
```

For the social graph serving layer, consistent hashing is preferred because it allows online resizing (adding capacity as the service grows without a full reshard downtime).

**Hot shards:**

Even with consistent hashing, celebrity users are a problem. If Lady Gaga is on Shard 3, Shard 3 gets dramatically more follower-list read traffic than other shards (because every fan viewing Lady Gaga's profile hits Shard 3). This is called a **hot shard**.

Mitigation: replicate celebrity data to all shards. The "celebrity threshold" is a configurable number of followers (say, 10M). Users above this threshold have their follower list replicated to ALL shards, so any shard can serve the request without routing to a specific shard.

### 5-Level Progression: Graph Serving Infrastructure

**Intern:** "I'd serve follower lists from a MySQL table with an index. Add Redis caching in front for popular users. That should handle most traffic."

**Junior Engineer:** "MySQL is too slow for billions of reads per day. I'd use Redis as the primary serving layer — store follower lists as Redis sorted sets, serve from Redis with Redis as the source, and only fall back to MySQL for cache misses. Set TTLs on Redis keys to prevent stale data from accumulating."

**Mid-level Engineer:** "Redis sorted sets work but have memory limits. I'd implement a tiered cache: hot users (celebrities) have their follower lists in Redis; cold users are served from MySQL on demand. I'd also replicate the Redis tier — one primary Redis (handles writes) and multiple read replicas (handle reads). For very large follower lists that don't fit comfortably in Redis, I'd use a cursor-paginated MySQL query with a covering index."

**Senior Engineer:** "The TAO architecture is the right model for this scale. Two tiers of cache (Follower pools + Leader) with writes flowing through the Leader for consistency. The two-tier structure decouples the number of cache servers from the number of web servers — you can add Follower pool capacity without touching the Leader tier. The Leader is the consistency chokepoint: all writes for a shard go through one Leader, which serializes writes and manages cache invalidation. This prevents the cache stampede problem where two concurrent writes to the same follower list produce an inconsistent cached state."

**Staff Engineer:** "Graph serving infrastructure is a specialization of the general distributed caching problem, but with three distinctive features that require custom solutions. First, the data model is graph-shaped (objects and typed associations) rather than key-value, which means the cache must understand graph queries — not just 'get key X' but 'get all type-Y edges from node X, paginated.' TAO's API is designed around this model. Second, the access pattern is heavily skewed — the top 0.01% of nodes (celebrities) receive the majority of read traffic. A uniform caching strategy wastes resources on the cold 99.99% and can't handle the hot 0.01%. TAO handles this through the Follower pool sharding: each pool independently caches what ITS web servers ask for, so a celebrity's data naturally gets cached in all pools without any celebrity-specific logic. Third, write consistency is critical for graph data in a way it isn't for, say, product catalog data. If a follow event is not reflected quickly in the serving layer, the 'is A following B?' check fails — the Follow button shows 'Follow' when it should show 'Following.' TAO achieves near-real-time consistency (< 1 second) by synchronously propagating invalidations from the Leader to all Follower pools after every write. This is more expensive than eventual consistency but is necessary for the user experience."

### Brainstorming Q&A

**Q1: Twitter loads the entire social graph into RAM. What happens if one of the graph serving machines crashes? How do you recover without dropping the service?**

Crashing a graph serving machine is a real operational event that happens regularly in a large fleet. The recovery strategy has multiple layers. The first layer is redundancy: each shard of the graph is stored on not one but three machines — one primary and two replicas — using a leader-election protocol (like Raft or ZooKeeper-based election). When the primary crashes, one of the replicas is elected as the new primary in under a second. During this brief election, reads for that shard either wait (blocking) or are served from the remaining replica with slightly stale data. Since the social graph for any given shard is a few hundred GB, each machine holds several shards' replicas, and the replicas are spread across machines so no single machine crash takes down more than 1/N of the data where N is the replication factor. The second layer is fallback: if a shard is temporarily unavailable (during leader election, or during a longer outage), the graph router falls back to MySQL for reads in that shard. MySQL is slow (10–50ms per query vs. microseconds for in-memory) but is always available and always correct. The third layer is rebuild speed: after a machine recovers (or a replacement is provisioned), it must rebuild its in-memory data. This is done by loading the most recent checkpoint (a serialized snapshot of the graph, stored on distributed storage like S3, taken every hour) and then replaying the Kafka event stream from the checkpoint timestamp. A hourly checkpoint plus a stream replay that processes millions of events per second means rebuild time is typically 5–15 minutes. The operational SLA is: a machine crash causes no data loss, under 1 second of service degradation for affected shards (handled by replica election), and full capacity restoration in under 15 minutes (rebuild time).

**Q2: As Twitter grows from 350M to 1B users, when does the "fit in RAM" approach break, and what's the next architectural step?**

At 350M users and 70B edges, the in-memory graph requires about 2.24 TB of RAM across a small cluster. At 1B users with similar average connection density (200 follows per user), that's 200B edges requiring about 6.4 TB of RAM — still within reach with 4–8 high-memory servers per shard. At 3B users (Meta scale), it's 600B edges requiring ~19 TB — manageable with a larger cluster but getting expensive. The "fits in RAM" approach doesn't break suddenly; it becomes progressively more expensive. The breaking point is when the cost of RAM far exceeds the value of having sub-millisecond graph queries. The next architectural step when RAM-based serving becomes too expensive is a tiered memory architecture: keep only the hottest portion of the graph in DRAM (the edges that are actually accessed frequently), and move the cold portion to NVMe SSDs. Modern NVMe SSDs have ~100 microsecond latency (versus ~100 nanoseconds for DRAM), which is still 100x faster than a MySQL query. A system like Apache Arrow or a custom memory-mapped file structure can manage this DRAM/NVMe tier automatically, keeping hot pages in DRAM and spilling cold pages to NVMe. An alternative is to be smarter about what you put in the in-memory graph — only load the edges that are relevant to active users (users who have been active in the last 30 days, say 30% of the total user base). Inactive users' edges can be served from MySQL on demand without impacting latency SLAs, since inactive users don't generate real-time traffic anyway. This selective loading approach can reduce the in-memory graph size by 2–3x without significantly impacting the performance seen by active users.

---

## CHAPTER SUMMARY

We covered the social graph from first principles through production-grade infrastructure design:

```
SOCIAL GRAPH SYSTEM -- COMPLETE ARCHITECTURE

                        USER REQUEST
                             |
              +--------------v--------------+
              |         GRAPH SERVICE       |
              |    (API: follow, unfollow,  |
              |  followers, following, PYMK)|
              +--+---------------------------+
                 |
     +-----------v------------+
     |    SERVING LAYER       |
     |  +------------------+  |
     |  | In-Memory Graph  |  |  Part 8
     |  | (sharded by      |  |
     |  |  user_id)        |  |
     |  +--------+---------+  |
     |           | miss       |
     |  +--------v---------+  |
     |  | TAO Follower     |  |  Part 8
     |  | Cache Pools      |  |
     |  +--------+---------+  |
     |           | miss       |
     |  +--------v---------+  |
     |  | TAO Leader Cache |  |  Part 8
     |  | (1 per shard)    |  |
     |  +--------+---------+  |
     +-----------|------------+
                 | miss (< 1% of reads)
     +-----------v------------+
     |    STORAGE LAYER       |
     |  +------------------+  |
     |  | MySQL sharded    |  |  Part 2
     |  | by follower_id   |  |
     |  +------------------+  |
     |  +------------------+  |
     |  | MySQL sharded    |  |  Part 2 (dual-write)
     |  | by followee_id   |  |
     |  +------------------+  |
     +------------------------+
                 |
          nightly export
                 |
     +-----------v------------+
     |  OFFLINE COMPUTE LAYER |
     |  +------------------+  |
     |  | HDFS Snapshot    |  |  Part 6
     |  | (graph parquet)  |  |
     |  +--------+---------+  |
     |  +--------v---------+  |
     |  | Spark GraphX     |  |  Parts 6, 7
     |  | - PYMK           |  |
     |  | - PageRank       |  |
     |  | - Partitioning   |  |
     |  +--------+---------+  |
     |  +--------v---------+  |
     |  | Cassandra        |  |  Part 6
     |  | (PYMK results)   |  |
     +------------------------+

WRITE PATH: Follow/Unfollow (Part 3)
  HTTP -> Follow Service -> MySQL (sync) -> Kafka -> consumers (async):
    -> Reverse MySQL shard
    -> Redis counters
    -> In-memory graph update
    -> Fan-out to follower feeds (with celebrity hybrid fan-out)

KEY TRADEOFFS:
  - Directed vs. undirected graph     -> different storage and query patterns
  - Cursor pagination vs. offset      -> O(1) vs. O(n) deep pages
  - Fan-out on write vs. read         -> write amplification vs. read latency
  - In-memory graph vs. TAO           -> RAM cost vs. complexity
  - Offline batch vs. real-time PYMK  -> staleness vs. compute cost
```

The social graph is the infrastructure that everything else in a social product depends on: feed, notifications, recommendations, and privacy controls all query the graph constantly. Getting this layer right — fast, consistent, and scalable — is what separates a product that survives hyper-growth from one that falls over at 100M users.
