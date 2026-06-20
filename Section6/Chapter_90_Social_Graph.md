# Chapter 93: Social Graph — Instagram / Twitter / LinkedIn at Scale

> The social graph is the nervous system of every social product. Follow/unfollow
> is a write. "Who should I show this post to?" is a graph traversal touching
> billions of edges. "Mutual friends" is a set intersection on 500M-node graphs.
> None of this is simple at scale.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

Distinct from newsfeed (Ch57) — that chapter covers fan-out delivery. This chapter
covers the graph itself: storage, traversal, and real-time queries. Comes up at
Meta, Twitter/X, LinkedIn, Snap, TikTok, and Pinterest. The core question:
"How do you store and query a graph with 1 billion nodes and 500 billion edges?"

---

## Planned Content

### Part 1: The Problem Space — What Is a Social Graph?
- Directed graph: A follows B (doesn't mean B follows A) — Twitter, Instagram
- Undirected graph: A and B are friends — Facebook, LinkedIn connections
- Scale: Meta social graph — 3B users, ~100B friendships
- Queries: followers of X, following of X, mutual connections, 2nd-degree connections,
  "people you may know", feed fan-out list
- The core tension: graph queries are notoriously hard to shard

### Part 2: Storage Models
- Adjacency list in a relational DB: (user_id, followed_user_id) table
  - Simple but: 100B rows, follower count queries need COUNT(*) on full partition
  - Index: (user_id) for "following list", (followed_user_id) for "followers list"
  - Sharding: shard by user_id — but cross-shard joins for mutual friends
- TAO (Facebook): custom graph storage built on MySQL + Memcache
  - Objects (nodes) + Associations (edges) as first-class types
  - Edges stored as adjacency lists, cached in Memcache
  - Strong consistency for writes; eventual consistency for reads from replicas
- Graph databases: Neo4j, Amazon Neptune — great for traversal, poor for web scale
- Custom: Twitter Flock — dedicated social graph service separate from main DB

### Part 3: Follow / Unfollow — Write Path
- Write: INSERT INTO follows (follower_id, followee_id, created_at)
- Invalidate follower/following count cache
- Trigger feed fan-out: when A follows B, should A see B's past posts? (usually no)
- Celebrity problem: when Lady Gaga (80M followers) posts, 80M fanout records created
  — this is the write amplification problem (covered in Ch57, but the graph is the input)
- Soft delete vs. hard delete: unfollow is tombstone or hard delete?

### Part 4: Follower / Following List Queries
- "Who does user A follow?" → follower list, paginated
- "Who follows user A?" → following list, paginated (harder — inverted index)
- Count: follower count ≠ COUNT(*) in prod; maintained as a separate counter
- Consistency: follow count can be slightly stale (eventual consistency acceptable)
- Pagination: cursor-based on (follower_id, created_at DESC) — not offset

### Part 5: Mutual Connections (Set Intersection at Scale)
- "Mutual friends between A and B" = intersection of A's friends and B's friends
- Naive: load A's 1000 friends, load B's 1000 friends, intersect in memory → O(N)
- At scale: intersection of two 10M+ sets (popular users)
  - Bloom filter pre-filter: "is any of A's friends in B's friend set?"
  - Sorted adjacency list + merge join: O(N + M) if both lists are sorted
- "People You May Know" (PYMK): 2nd-degree connections not already connected
  - For each friend F of A, find F's friends not in A's friend set
  - Expensive: requires 2-hop traversal of the graph
  - Solution: precompute offline (Spark GraphX job nightly) + serve from cache

### Part 6: Graph Traversal Algorithms at Scale
- BFS for degree-of-connection: "how many hops between A and B?"
  - Bidirectional BFS: start from both A and B, meet in middle — cuts search space
  - At Facebook scale: 3.57 average degrees of separation (2016 study)
- PageRank on social graphs: used for ranking in feeds, search, PYMK
- Graph partitioning: minimize cross-partition edges to reduce network traffic
  - METIS algorithm for balanced partitioning
  - In practice: most social graphs are scale-free (Zipf degree distribution)
    making perfect partitioning impossible

### Part 7: Graph Serving Infrastructure
- TAO (Facebook's approach): two-tier cache (leader + follower Memcache)
  - Writes go to MySQL (durable) + invalidate cache
  - Reads: Memcache L1 → Memcache L2 → MySQL
- Separate follower service: Twitter maintains follower graphs entirely in RAM
  (FlockDB, later replaced by a Cassandra-based service)
- Sharding strategy: shard by user_id, accept that cross-shard traversal is expensive
- Real incident: Twitter 2022 — after Musk acquisition, laid off team maintaining
  social graph service; follower counts went stale for weeks

### Part 8: Interview Framework
- Clarify: directed (Twitter-style) or undirected (Facebook-style)?
- Core tables: users, follows/friendships
- Start simple: relational DB with indexes
- Evolve: dedicated graph service + cache for follower lists
- Advanced: PYMK via offline graph computation + online cache
- L5 vs. L6: L5 draws the follows table; L6 discusses TAO's object/association model,
  why Memcache is two-tier, and how to handle the celebrity fan-out problem at graph level

---

## The One-Sentence Summary

> "Social graph = adjacency list storage (sharded by user_id, cached in Memcache/Redis) + write path (follow → insert + counter update + cache invalidate) + read path (follower list paginated + mutual friends via set intersection) + offline traversal (PYMK, PageRank via Spark) — the graph is simple to model but the scale makes every query a distributed systems problem."

---

*Full chapter: ~2,500 lines. Pairs with Ch57 (News Feed) — graph provides the fan-out list.*
