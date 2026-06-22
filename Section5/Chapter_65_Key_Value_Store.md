# Chapter 61e: Key-Value Store — Build Your Own Redis / DynamoDB

> Every engineer uses a key-value store. Few can design one. This chapter
> is the design interview that separates engineers who know how to use
> a database from engineers who understand how one works.

---

```
+------------------------------------------------------------------+
|  INTERVIEW OVERVIEW — Key-Value Store                            |
|  Time: 45 minutes                                                |
|                                                                  |
|  Min 0-2:   Clarify scope (single-node vs. distributed?)        |
|  Min 2-8:   Users and use cases                                 |
|  Min 8-14:  Functional + Non-functional requirements            |
|  Min 14-19: Scale math                                           |
|  Min 19-23: Assumptions                                          |
|  Min 23-42: Architecture + deep dives                           |
|  Min 42-45: Failure modes, extensions                            |
|                                                                  |
|  Interview tactic: Start single-node (storage engine),          |
|  then organically add distribution. Do NOT jump straight         |
|  to consistent hashing without explaining WHY it is needed.     |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
|  L5 vs L6 AT A GLANCE                                           |
|                                                                  |
|  L5 (Senior SWE):                                               |
|  - LSM tree: MemTable -> WAL -> SSTable -> Bloom filter         |
|  - Consistent hashing with virtual nodes                         |
|  - Quorum reads/writes (W + R > N for strong consistency)       |
|  - Gossip protocol for failure detection                         |
|                                                                  |
|  L6 (Staff):                                                     |
|  - Vector clocks for conflict resolution                         |
|  - Merkle tree anti-entropy for replica sync                    |
|  - Sloppy quorum + hinted handoff for availability              |
|  - Compaction strategy choice (leveled vs. tiered) with         |
|    quantified write amplification trade-off                     |
|  - Hot key detection and mitigation (key splitting)             |
+------------------------------------------------------------------+
```

---

## Why This Chapter Is a Pure Depth Probe

"Design a key-value store" is different from every other system design question. There is no product UI to sketch. There are no users to describe. The interviewer is asking one specific thing: do you know how storage engines work, and do you know how distributed systems maintain consistency?

Real-world equivalents:
- Redis: single-node (mostly), in-memory, data structures, persistence as an option
- Memcached: single-node, in-memory, pure cache, multi-threaded
- DynamoDB: distributed, managed, Dynamo-style eventual/quorum consistency
- Cassandra: distributed, wide-column, Dynamo-style + BigTable SSTable storage
- RocksDB: single-node, disk-persistent, LSM tree engine (embedded, not a server)
- etcd: distributed, Raft consensus, strongly consistent, small scale (metadata only)

At L5, you need to design a DynamoDB-lite: distributed, eventually consistent, LSM-backed storage engine.

---

## Phase 1: Users and Use Cases (Minutes 2-8)

### Clarify the scope first

Before drawing anything, ask: "Is this a single-node in-memory store like Redis, or a distributed persistent store like DynamoDB?"

The interviewer usually wants distributed + persistent. If they say in-memory only, that simplifies dramatically (no LSM tree, just a hash map).

**Assume for this chapter:** distributed, persistent, eventually consistent by default, configurable to strong consistency.

### Who uses a key-value store?

**Internal users (engineers building services):**
- Session management: store user session data with TTL (key = session_id, value = user JSON)
- Rate limiting: store request counters per user per window
- Feature flags: store feature flag configurations
- Shopping cart: store cart contents (key = user_id, value = serialized cart)
- Leaderboard backend: store scores (though Redis ZSET is better for sorted sets)
- Configuration store: key = config_key, value = config_value, distributed access

**The API surface:**

```
Core operations (must have):
  get(key) -> value | null
  put(key, value) -> success | error
  delete(key) -> success | error

Optional operations (P1):
  get_with_ttl(key) -> value with remaining TTL
  put_with_ttl(key, value, ttl_seconds) -> success
  atomic_compare_and_swap(key, expected_value, new_value) -> success | conflict

NOT in scope:
  Range queries (that is a database, not a KV store)
  Transactions across multiple keys (that is a database)
  Secondary indexes (that is a database)
  Sorted sets or lists as values (that is Redis — more complex data structures)
```

### The five constraints that drive every design choice

```
+----------------------+-----------------------------------+-------------------------+
| Constraint           | Impact on design                  | If relaxed...           |
+----------------------+-----------------------------------+-------------------------+
| Value size 10KB max  | Use LSM tree (sequential writes)  | Larger values: object   |
|                      | Not B-tree (random writes)        | storage (S3), not KV   |
+----------------------+-----------------------------------+-------------------------+
| Low write latency    | In-memory MemTable absorbs writes | No MemTable needed if  |
| (<5ms p99)           | before disk flush                 | writes can be slow      |
+----------------------+-----------------------------------+-------------------------+
| Survive node crash   | WAL must be written before        | In-memory is fine       |
|                      | acknowledging write               |                         |
+----------------------+-----------------------------------+-------------------------+
| Scale beyond 1 node  | Consistent hashing for partitioning| Single-node hashmap    |
| (>1TB data)          | Replication for fault tolerance   |                         |
+----------------------+-----------------------------------+-------------------------+
| Read most keys in   | Bloom filter per SSTable:          | No Bloom filter needed  |
| <10ms including      | skip SSTables that can't have key  |                         |
| disk reads           |                                   |                         |
+----------------------+-----------------------------------+-------------------------+
```

---

## Phase 2: Functional Requirements (Minutes 8-14)

### Core operations

- **F1:** `put(key, value)` — write or overwrite a key-value pair. Durably stored.
- **F2:** `get(key) -> value | null` — retrieve value for a key. Null if key does not exist or is deleted.
- **F3:** `delete(key)` — remove a key. Does not immediately remove from disk (tombstone written instead).
- **F4:** `put_with_ttl(key, value, ttl)` — write with automatic expiry. Common for session storage.

### Configuration knobs (the depth-probe question)

- **C1:** Consistency level: `strong` (W=2, R=2, N=3) or `eventual` (W=1, R=1, N=3)
- **C2:** Durability: `sync_every_write` (WAL fsync on every put) or `async` (WAL batched fsync, lower durability)
- **C3:** Replication factor N (default: 3)

### What does NOT belong in a KV store

- Range scans (get all keys between k1 and k2): Use a database with range indexes.
- Joins across keys: Use a database.
- Secondary indexes (find key by value): Use search index or database.
- Multi-key atomic transactions: Use a transactional database (Postgres, Spanner).

---

## Phase 3: Scale and Capacity (Minutes 14-19)

### Scale targets

```
Data volume:          10 TB total data
Read throughput:      100,000 reads/sec
Write throughput:     10,000 writes/sec
Value size:           up to 10 KB (average 1 KB for session/config data)
Key size:             up to 256 bytes
Replication factor:   N = 3 (3 copies of each key-value pair)
Consistency:          Eventual by default, strong on request (configurable)
```

### Storage math

```
Total data: 10 TB
With N=3 replication: 10 TB * 3 = 30 TB raw storage needed

Per node sizing:
  Use 10 nodes (each with 3 TB storage)
  10 nodes * 3 TB = 30 TB total
  Each node holds ~3 TB of data

SSTable file sizes (typical):
  MemTable size: 64 MB (flushed when full)
  SSTable file: 64 MB each (one flush = one SSTable)
  SSTables per node: 3 TB / 64 MB = 48,000 SSTables
  Bloom filter per SSTable: 64 MB * 10 bits / 8 = 80 MB per SSTable -> too large
  
  Wait -- recalculate. Bloom filter size is based on NUMBER of keys, not data size:
  Average key-value pair: 1.256 KB (1024 bytes value + 256 bytes key)
  Keys per SSTable: 64 MB / 1.256 KB = 51,075 keys per SSTable
  Bloom filter at 1% FP rate: 51,075 keys * 10 bits = 510,750 bits = 62.5 KB per filter
  Total Bloom filter memory (48,000 SSTables): 48,000 * 62.5 KB = 3 GB per node -> manageable

Keys per node:
  10 TB total / 10 nodes / 1.256 KB per key = 798 million keys per node

Write throughput math:
  10,000 writes/sec total
  Per node: 10,000 / 10 = 1,000 writes/sec per node
  1,000 writes/sec * 1.256 KB = 1.256 MB/sec write rate
  WAL sequential write at 200 MB/sec: well within SSD/NVMe capability
  MemTable flush: every 64 MB / 1.256 MB/sec = 51 seconds between flushes
  -> 1 SSTable flush per 51 seconds per node. Low.

Read throughput math:
  100,000 reads/sec / 10 nodes = 10,000 reads/sec per node
  With Bloom filter (eliminates 99% of SSTables for missing keys): most reads = MemTable + 1-2 SSTables
  With well-tuned cache (OS page cache): most SSTable reads served from memory
  Effective disk I/O per read: minimal for hot keys (cached), 1-3 I/Os for cold keys
```

### What breaks first at 10x

```
At 100K writes/sec (10x) and 1M reads/sec:

1. MemTable flush rate:
   100K writes/sec * 1.256 KB = 125 MB/sec per shard
   MemTable (64 MB) fills every 0.5 seconds
   SSTable flush: 2 flushes per second per shard -> high I/O
   Fix: increase MemTable size to 512 MB (longer flush interval)
   Trade-off: larger MemTable = more data lost on crash before WAL replay

2. Compaction backlog:
   2 SSTables/second being created, compaction worker cannot keep up
   SSTable count grows: read amplification increases
   Fix: increase compaction workers, or switch from leveled to size-tiered compaction for write-heavy workloads

3. Hot key contention:
   A single popular key (e.g., "homepage_feature_flags") receives 50K reads/sec
   All requests route to the same node (consistent hashing)
   That node becomes the bottleneck
   Fix: read replicas, key replication beyond standard N (3), or application-level caching
```

---

## Architecture Design — HLD

### Opening analogy: the library

Think of the key-value store as a library:
- When you donate a new book (write), the librarian first writes it in the logbook (WAL), then puts it on the "recent acquisitions" shelf (MemTable), and eventually files it in the permanent stacks (SSTable).
- When you request a book (read), the librarian first checks the recent acquisitions shelf (MemTable — fast, in-memory), then the new arrivals (newer SSTables), then the main stacks (older SSTables — slower, on disk).
- To speed up "does this book exist?" the librarian has a card catalog (Bloom filter) for each section — checking the catalog tells you which sections to search without physically looking through shelves.
- The library has 10 branches (10 nodes). Popular books are kept at 3 branches (replication). A head librarian (coordinator node) knows which 3 branches have which books (consistent hashing ring).

### Full HLD diagram

```
[Client Application]
        |
        | get(key) / put(key, value) / delete(key)
        v
+---------------------+
|   COORDINATOR NODE  |
|  (any node in ring) |
|                     |
|  1. Hash key        |
|  2. Find N replicas |
|  3. Fan out request |
|  4. Quorum wait     |
|  5. Return result   |
+---------------------+
     |        |        |
     |        |        |
     v        v        v
+--------+  +--------+  +--------+
| Node 1 |  | Node 2 |  | Node 3 |
| (repli |  | (repli |  | (repli |
|  ca 1) |  |  ca 2) |  |  ca 3) |
|        |  |        |  |        |
|MemTable|  |MemTable|  |MemTable|
|   +    |  |   +    |  |   +    |
|  WAL   |  |  WAL   |  |  WAL   |
|   +    |  |   +    |  |   +    |
|SSTable |  |SSTable |  |SSTable |
| files  |  | files  |  | files  |
+--------+  +--------+  +--------+

Gossip Protocol: each node shares heartbeats with
random neighbors every second. Failure detection
propagates in O(log N) rounds.

Consistent Hashing Ring: coordinator hashes key to
position on ring, finds 3 nearest nodes clockwise.
```

### Component table

```
+-------------------+-------------------------------------+-----------+-------------------+
| Component         | Responsibility                      | Stateful? | Scale target      |
+-------------------+-------------------------------------+-----------+-------------------+
| Coordinator       | Route requests to correct replicas; | NO (role) | Any node can be   |
|                   | any node can be coordinator for a   |           | coordinator for   |
|                   | given request (Dynamo-style)         |           | any request       |
+-------------------+-------------------------------------+-----------+-------------------+
| MemTable          | In-memory sorted BST absorbing      | YES       | 64-512 MB RAM     |
|                   | recent writes; all reads check here |           | per node          |
|                   | first before going to disk          |           |                   |
+-------------------+-------------------------------------+-----------+-------------------+
| WAL               | Write-ahead log for crash recovery; | YES       | Sequential disk   |
|                   | every put/delete appended here      |           | writes at SSD     |
|                   | before MemTable update              |           | speed             |
+-------------------+-------------------------------------+-----------+-------------------+
| SSTable           | Sorted String Table: immutable,     | YES       | 64 MB per file    |
|                   | sorted key-value file flushed from  |           | thousands per     |
|                   | MemTable; never modified            |           | node              |
+-------------------+-------------------------------------+-----------+-------------------+
| Bloom Filter      | Per-SSTable probabilistic filter;   | YES (in   | 62.5 KB per       |
|                   | answers "might this key be in this  | memory)   | SSTable           |
|                   | SSTable?" with 1% false positive    |           |                   |
+-------------------+-------------------------------------+-----------+-------------------+
| Compaction Worker | Background merge of SSTables;       | NO (job)  | 1-4 workers       |
|                   | removes deleted keys (tombstones);  |           | per node          |
|                   | merges small SSTables into large    |           |                   |
+-------------------+-------------------------------------+-----------+-------------------+
| Gossip Service    | Failure detection; each node shares | NO (proto)| Every node        |
|                   | its membership view with random     |           | participates      |
|                   | neighbors every second              |           |                   |
+-------------------+-------------------------------------+-----------+-------------------+
| Anti-Entropy Svc  | Background Merkle tree comparison   | NO (job)  | Periodic: every   |
|                   | between replicas; repairs divergence|           | 10 minutes        |
+-------------------+-------------------------------------+-----------+-------------------+
```

---

## Component 1: LSM Tree — The Single Most Important Thing to Know

**This section alone determines whether you pass or fail the interview.** Walk the LSM tree write path and read path in detail. Every step matters.

### Why not just a B-tree?

**B-tree (used by MySQL, PostgreSQL):**

```
Structure: balanced tree of fixed-size pages (typically 4KB or 16KB)
Write: update the page in place on disk
For a single key update:
  1. Find the leaf page containing the key (tree traversal: O(log n) I/Os)
  2. Read the page into memory
  3. Modify the value in memory
  4. Write the entire page back to disk
  
Problem: RANDOM DISK WRITE
  The page containing "user:12345" is at byte offset 8,437,200 on disk
  Writing to this random offset: SSD ~30-100 microseconds, HDD ~5-10 ms
  At 10,000 writes/sec: 10,000 random disk writes/sec

B-tree write throughput on HDD: ~100-200 I/Os/sec = 100-200 writes/sec max
B-tree write throughput on SSD: ~10,000-50,000 I/Os/sec = feasible but expensive

Compare: LSM tree sequential write throughput on SSD: ~500 MB/sec
  Each write is an append to the WAL (sequential)
  WAL writes at 10K writes/sec * 1 KB = 10 MB/sec -> trivial on any SSD
  MemTable writes: in memory, effectively free
  SSTable flush: sequential write at 200 MB/sec -> 1 SSTable flushed every 0.3 seconds
  
The gap: LSM writes are 10-50x faster than B-tree writes on spinning disk,
and 2-5x faster on SSD for high write workloads.

Trade-off: LSM tree reads are slower than B-tree reads for cold keys.
  B-tree: O(log n) disk I/Os to reach any key
  LSM tree: check MemTable + potentially many SSTables until key is found
  Bloom filter + compaction limit this in practice to 2-4 I/Os for cold reads
```

### LSM Tree write path

**Step-by-step with ASCII diagram:**

```
CLIENT writes: put("user:12345", "name=Alice,age=30")

+----------------------------------------------+
|  STEP 1: Write to WAL (Write-Ahead Log)      |
|                                              |
|  WAL (append-only file on disk):             |
|  ...                                         |
|  [seq=10001] PUT user:12345 name=Alice,age=30|
|  [seq=10002] ...                             |
|                                              |
|  WAL write is sequential (fast):             |
|  seek is needed only when file is created    |
|  every write appends to end                  |
|  fsync: flush to disk (ensures durability)  |
|  Duration: 1-5ms (fsync) or 0.1ms (async)   |
+----------------------------------------------+

+----------------------------------------------+
|  STEP 2: Insert into MemTable (in-memory)    |
|                                              |
|  MemTable: Red-Black Tree (sorted by key)    |
|                                              |
|        user:99999                            |
|        /           \                         |
|  user:12345     user:55555                   |
|  (just inserted)                             |
|                                              |
|  MemTable is SORTED: O(log n) insert         |
|  All keys always sorted by key               |
|  Duration: <1 microsecond (pure RAM)         |
+----------------------------------------------+

Return SUCCESS to client. (WAL is the durability guarantee)

+----------------------------------------------+
|  STEP 3: When MemTable is full (64MB):       |
|          Flush to SSTable on disk            |
|                                              |
|  SSTable file format:                        |
|  +------------------------------------+      |
|  | Data Block 1 (4KB):               |      |
|  |   user:00001 -> val1 (sorted)     |      |
|  |   user:00002 -> val2              |      |
|  |   user:00003 -> val3              |      |
|  +------------------------------------+      |
|  | Data Block 2 (4KB):               |      |
|  |   user:00004 -> val4              |      |
|  |   ...                             |      |
|  +------------------------------------+      |
|  | Index Block (sparse):             |      |
|  |   user:00001 -> offset 0          |      |
|  |   user:00004 -> offset 4096       |      |
|  |   user:00008 -> offset 8192       |      |
|  +------------------------------------+      |
|  | Bloom Filter (62.5 KB for 51K    |      |
|  |   keys at 1% FP rate)            |      |
|  +------------------------------------+      |
|  | Footer: magic number, checksum   |      |
|  +------------------------------------+      |
|                                              |
|  SSTable is immutable: once written, never  |
|  modified. New writes go to a new SSTable.  |
|                                              |
|  Duration: 300ms to flush 64MB sequentially |
|  (during this flush, writes continue to a   |
|  new MemTable in parallel)                   |
+----------------------------------------------+
```

### LSM Tree read path

```
CLIENT reads: get("user:12345")

STEP 1: Check MemTable
  Binary search in the Red-Black Tree
  Found -> return value immediately (sub-millisecond)
  Not found -> continue to step 2

STEP 2: Check SSTables newest to oldest
  For each SSTable (from most recently flushed to oldest):
  
  2a. Check Bloom filter
      If Bloom filter says "DEFINITELY NOT HERE": skip this SSTable (0 disk I/Os)
      If Bloom filter says "MAYBE HERE": check the SSTable (continue to 2b)
      
      Bloom filter false positive rate: 1%
      For N=100 SSTables on disk: only 1% * 100 = 1 SSTable will be a false positive
      Other 99 are correctly skipped
      
  2b. Binary search the index block
      Index block is in memory (loaded once, never changes)
      Find the offset range where the key would be
      
  2c. Read the data block from disk
      1 disk I/O for the data block (4KB)
      Binary search within the data block for the key
      Found -> return value
      Not found -> this is the 1% false positive, continue to next SSTable
      
  2d. If found a tombstone (DELETE marker): return null (key was deleted)

STEP 3: If not found in any SSTable
  Return null (key does not exist)

Performance:
  Cache hit (key in MemTable or recently read SSTable in OS page cache):
    p50: <1ms, p99: 2ms
  Cache miss (cold key, must read from disk):
    p50: 5ms (1-3 disk I/Os), p99: 20ms (compaction pauses)

Why Bloom filter is critical:
  Without Bloom filter (100 SSTables, key not present):
    Must check all 100 SSTables -> 100 disk I/Os
    At 10,000 reads/sec * 100 I/Os = 1,000,000 disk I/Os/sec -> impossible
  With Bloom filter:
    Only 1% are checked (1 false positive) + 0 true positives = 1 disk I/O
    10,000 reads/sec * 1 I/O = 10,000 disk I/Os/sec -> easily handled
```

### Compaction — background garbage collection

**The problem without compaction:**

```
After 1 hour of writes: 200 SSTable files (1 per minute)
A key updated every minute: 200 copies across 200 SSTables (only latest is valid)
Storage wasted: 199 outdated copies
Read path: must check all 200 SSTables (slowing reads over time)

Deleted keys (tombstones): can never be cleaned up (SSTable is immutable)
Eventually: entire disk filled with old versions and tombstones
```

**Leveled compaction (what LevelDB/RocksDB uses):**

```
Level 0 (L0): New SSTables from MemTable flushes
  Each SSTable in L0 may overlap in key space with others (no ordering guarantee)
  When L0 has 4+ SSTables: trigger compaction to L1

Level 1 (L1): 10 MB total size
  SSTables in L1 do NOT overlap (sorted, non-overlapping key ranges)
  L1 = "the sorted layer"

Level 2 (L2): 100 MB total size (10x L1)
Level 3 (L3): 1 GB total size
Level 4 (L4): 10 GB total size
...

Compaction process L0 -> L1:
  1. Pick one SSTable from L0
  2. Find all L1 SSTables that overlap in key space with that L0 file
  3. Merge all: sort by key, keep only the latest version of each key
  4. Write merged output as new L1 SSTables (non-overlapping)
  5. Delete the input L0 SSTable and the old L1 SSTables

After compaction: reading a key in L1 requires at most 1 SSTable I/O
(key ranges don't overlap, so the index tells you exactly which file to check)

Read amplification with leveled compaction:
  Worst case: check MemTable + 1 L0 file + 1 per level = 1 + 4 + 7 = 12 files max
  In practice with Bloom filters: 1-3 disk I/Os for most reads

Write amplification:
  Each byte written to MemTable gets written to:
  WAL (1x) + L0 SSTable (1x) + merge to L1 (10x) + merge to L2 (10x) + ... = 30-50x
  
  Write amplification: 10-30x for leveled compaction
  This is the fundamental trade-off: better reads at the cost of more disk writes.
```

**Size-tiered compaction (what Cassandra uses by default):**

```
Strategy: group SSTables of similar size together and merge

When N (e.g., 4) SSTables of similar size exist: merge them into one larger SSTable
The result is larger -> eventually grouped with other large SSTables -> merged again

Properties:
  Write amplification: lower than leveled (each byte merged fewer times)
  Space amplification: higher (old versions not cleaned up as aggressively)
  Read amplification: higher (overlapping key ranges, more files to check)
  
Best for: write-heavy workloads where read performance is less critical.
          Cassandra write-heavy use cases (IoT sensor data, time-series).

Compare:
  Leveled: better reads, higher write amplification (good for mixed workloads)
  Size-tiered: better writes, worse reads (good for write-heavy workloads)
```

---

## Component 2: Consistent Hashing — Distributing Keys Across Nodes

### Why simple modulo fails

```
Simple modulo: shard_id = hash(key) % N

5 nodes (N=5). A key hashes to 47:
  47 % 5 = 2 -> Node 2

Adding a 6th node (N=6):
  47 % 6 = 5 -> Node 5

Every key that was on Node 2 now maps to different nodes.
Adding 1 node to a 5-node cluster causes 83% of keys to move.

1 billion keys * 83% = 830 million keys moving
At 10 MB/sec data transfer: 830 million keys * 1 KB = 830 GB / 10 MB/sec = 83,000 seconds

This is catastrophically bad. The system is unavailable for data transfer.
```

### Consistent hashing ring

```
Hash space: 0 to 2^32 (4 billion positions, arranged in a ring)
  2^32 - 1 connects back to 0 (the ring is circular)

Physical nodes placed on the ring:
  hash("node-A") = 100 -> Node A at position 100
  hash("node-B") = 250 -> Node B at position 250
  hash("node-C") = 400 -> Node C at position 400
  hash("node-D") = 600 -> Node D at position 600
  hash("node-E") = 900 -> Node E at position 900

Key placement: walk CLOCKWISE from hash(key) to next node

  hash("user:12345") = 180 -> walk clockwise from 180 -> first node is B (at 250)
  Key "user:12345" lives on Node B.
  
  hash("session:abc") = 350 -> walk clockwise from 350 -> first node is C (at 400)
  Key "session:abc" lives on Node C.

Ring diagram:
  0 ...... 100(A) ...... 250(B) ...... 400(C) ...... 600(D) ...... 900(E) ...... 2^32
  Keys between A and B: stored on B
  Keys between B and C: stored on C
  Keys between E and (ring wrap) A: stored on A

Adding Node F at position 700:
  Only keys between D (600) and F (700) need to move
  They were previously on E (700->900 = next node)
  Now they are on F (700 = new node)
  
  Keys that move: positions 600 to 700 (only 1/(number of nodes) fraction)
  With 6 nodes: only 1/6 = 16.7% of D's keys move to F
  Total data moved: 16.7% of 1 node's data (not all data)
  
  Compare to modulo: 83% of ALL keys moved
```

### Virtual nodes (vnodes) — fixing uneven load

```
Problem with single positions:
  Node A at position 100
  Node B at position 250
  ...
  
  If hash function is not perfectly uniform, some nodes get more keys.
  When Node B goes down, ALL of B's keys go to Node C.
  Large data transfer, C's load doubles.

Solution: virtual nodes (each physical node has 150 positions on the ring)

  Physical Node A -> Virtual nodes at: 50, 120, 310, 450, 680, 820, ...  (150 positions)
  Physical Node B -> Virtual nodes at: 80, 200, 370, 490, 710, 890, ...  (150 positions)
  Physical Node C -> Virtual nodes at: 30, 150, 290, 560, 730, 950, ...  (150 positions)

  Total ring positions: 3 nodes * 150 vnodes = 450 positions on the ring
  
  Key placement: walk clockwise from hash(key) to nearest virtual node
  The physical node that owns that virtual node serves the request.

When Node B goes down:
  Node B's 150 virtual nodes are distributed across the ring.
  The keys from each of B's vnodes go to the NEXT vnode (clockwise).
  Each surviving node absorbs ~1/2 of B's load (150 vnodes / 2 survivors = 75 each)
  No single node doubles in load.

When Node F is added with 150 vnodes:
  F's 150 vnodes are inserted at 150 positions across the ring
  Each neighboring vnode loses some keys to F
  Keys transfer is spread across ALL existing nodes
  Each existing node transfers roughly 1/(N+1) fraction of its keys to F
  
  With 10 nodes, adding node 11:
  Each existing node transfers 1/11 of its keys = 9% each
  vs modulo: 91% of keys move

Why 150 virtual nodes?
  Empirically determined: 150 vnodes gives <5% standard deviation in key distribution
  More vnodes: more uniform distribution but more memory for the ring table
  Fewer vnodes: less memory but more uneven load distribution
```

### The ring table (membership information)

```
Each node stores the full ring: {vnode_position -> physical_node} for all 1500 vnodes (10 nodes * 150)
Size of ring table: 1500 entries * (8 bytes position + 16 bytes node ID) = 36 KB per node

How nodes learn about new/removed members: GOSSIP PROTOCOL (see Component 4)
```

---

## Component 3: Replication and Quorum

### The replication factor

For N=3 (3 replicas of each key-value pair):
- The coordinator finds the 3 nodes responsible for the key (3 successive nodes clockwise on the ring)
- Writes the key-value to all 3 nodes
- Reads from any subset of 3 nodes based on consistency requirement

**Why 3 replicas?**

```
N=1: No fault tolerance. 1 node failure = data loss.
N=2: Survives 1 failure. But: quorum (W=2, R=2) => W+R=4 > N=2? -> NO.
     W=2, R=2, N=2: W+R>N but W+R=4 != strong (all nodes must agree, fragile)
N=3: Survives 1 failure. W=2, R=2: W+R=4 > N=3 -> strong consistency possible.
     Also: majority quorum (2 of 3) is clear-cut.
N=5: Survives 2 failures. More expensive. Used for critical metadata (etcd, Raft).
```

### The quorum rule: W + R > N

**The core insight:**

If you write to W nodes and read from R nodes, and W + R > N, then at least one node in the read set MUST overlap with the write set. This overlapping node has the latest value. So quorum reads always return the latest write.

```
N=3, W=2, R=2:
  Write set: nodes {A, B}  (2 out of 3)
  Read set: nodes {A, C}  or {B, C}  or {A, B}  (any 2 out of 3)
  Overlap: at least 1 node is always in both sets
  -> Read always finds the latest write. STRONG CONSISTENCY.

N=3, W=1, R=1:
  Write set: node {A}  (just 1)
  Read set: node {C}  (just 1)
  No guaranteed overlap (C might not have the latest write from A)
  -> Read might return stale value. EVENTUAL CONSISTENCY.
  Trade-off: faster writes (only wait for 1 node) and reads (only wait for 1 node)

N=3, W=3, R=1:
  Write set: all 3 nodes
  Read set: any 1 node
  Every node has the latest write, so any read is correct.
  -> STRONG CONSISTENCY.
  Trade-off: writes are slowest possible (wait for ALL 3 nodes)
  Used for: read-heavy workloads where read latency matters more than write latency

N=3, W=1, R=3:
  Write set: 1 node (fast)
  Read set: all 3 nodes
  Read must get response from all 3 -> strong consistency
  -> STRONG CONSISTENCY but slow reads.
  Rare: usually you want fast reads.
```

**Configurable consistency (Dynamo-style):**

```
Client request parameter: consistency_level
  consistency_level = EVENTUAL:
    W=1, R=1, N=3
    Coordinator sends to 3 nodes, returns after 1 acknowledges
    Read: ask 3 nodes, return on first response
    If nodes disagree: undefined (application resolves or last-write-wins)
    
  consistency_level = STRONG:
    W=2, R=2, N=3
    Coordinator waits for 2 acknowledgements before returning write success
    Read: ask all 3, wait for 2, return the latest version
    If one node is slow (200ms instead of 10ms): wait 200ms
    "Read repair": if stale value found, update the lagging node in background
```

### Read repair: fixing staleness on the read path

```
Client reads key K with W=2, R=2, N=3.
Coordinator asks all 3 replicas: A, B, C.
Responses:
  Node A: value="v2", timestamp=T2
  Node B: value="v1", timestamp=T1  (stale! B missed a write)
  Node C: value="v2", timestamp=T2

Coordinator returns "v2" to client (latest based on timestamp).

Background (read repair):
  Coordinator sends update to Node B: put(key=K, value="v2", timestamp=T2)
  Node B updates its local storage.
  Next read: all 3 nodes return "v2". Consistency restored.

Why read repair works:
  Even with eventual consistency (W=1), frequently read keys are quickly repaired.
  Infrequently read keys may stay stale for longer (repaired only when read).
  Anti-entropy (Merkle trees) covers the cold keys that are never read.
```

---

## Component 4: Gossip Protocol — Failure Detection Without a Central Coordinator

### The problem: how do nodes know if another node is down?

**Option 1: Centralized heartbeat service (ZooKeeper)**

```
All nodes send heartbeats to ZooKeeper every second.
ZooKeeper declares a node dead if no heartbeat in 5 seconds.

Problem: ZooKeeper is a single point of failure for failure detection.
If ZooKeeper is down, no one knows who is alive.
For a metadata service this is fine (etcd/Chubby). For a data store, it's fragile.
```

**Option 2: Each node monitors all others (O(N^2))**

```
10 nodes: each sends heartbeat to 9 others every second.
10 * 9 = 90 heartbeat messages per second. Manageable.

100 nodes: each sends to 99 others. 100 * 99 = 9,900 messages/second.
1,000 nodes: 999,000 messages/second. Not scalable.

Problem: O(N^2) message complexity doesn't scale.
```

**Option 3: Gossip Protocol (O(N log N) convergence)**

```
Each node maintains a membership list:
  {node_id -> {last_heartbeat_time, version_number}}

Every 1 second, each node:
  1. Increments its own heartbeat counter
  2. Picks 2 random neighbors from the membership list
  3. Sends its full membership list to both neighbors
  4. Receives their membership lists
  5. Merges: for each node, keep the entry with the HIGHER version number

After each round: information spreads to 2^t nodes in t rounds.
  Round 1: 1 node knows, tells 2 others -> 3 nodes know
  Round 2: 3 nodes each tell 2 others -> 9 nodes know
  Round 3: 9 * 3 = 27 nodes know
  Round k: approximately min(3^k, N) nodes know

For N=100 nodes: information reaches all nodes in log_3(100) = 4-5 rounds
  4 rounds * 1 second/round = ~4 seconds to propagate across the cluster

Messages per second:
  Each node sends 2 gossip messages/second
  100 nodes: 200 messages/second (vs. 9,900 for all-pairs heartbeat)
  O(N) vs O(N^2)

Failure detection:
  If Node B stops incrementing its heartbeat counter:
    Other nodes see B's version number stagnant while others grow
    After timeout_threshold = 10 seconds (10 rounds without increment):
    Mark Node B as SUSPECTED_DEAD
  After 20 seconds without heartbeat increment:
    Mark Node B as DEAD. Remove from ring. Reroute its keys.
```

**Gossip example:**

```
Round 1 (T=1s):
  Node A gossips to B and C: {A: v=10, B: v=8, C: v=9, D: v=7}
  Node B gossips to E and F: {A: v=9, B: v=8, C: v=8, D: v=7}

After round 1:
  Node A saw B's view: now knows A=max(10,9)=10, B=max(8,8)=8, C=max(9,8)=9, D=max(7,7)=7
  Node B now has A's latest view: A=10 (updated from 9)

After 4-5 rounds: all nodes have the global maximum heartbeat for every peer.
If Node D's heartbeat stays at v=7 for 10 rounds while all others increment:
  All nodes independently conclude: D is down.
  No coordinator needed. Decentralized failure detection.
```

---

## Component 5: Bloom Filter — The False Positive Filter

**This is a crucial deep-dive topic. Know the internals.**

### The problem it solves

```
N=100 SSTables on disk for a cold key.
Without Bloom filter: check all 100 SSTables (1 disk I/O each = 100 disk I/Os)
At 10K reads/sec: 1,000,000 disk I/Os/sec -> impossible

With Bloom filter: most SSTables can be checked in memory (no disk I/O)
  "Is this key in SSTable_42?" -> check Bloom filter (in memory) -> "definitely not" -> skip
  Only check disk for the ~1% false positives
```

### How a Bloom filter works

**Setup:**

```
M = bit array of size m (all zeros initially)
K = k different hash functions (h1, h2, ..., hk)
  Each hash function maps a key to a position in [0, m-1]

Bloom filter for an SSTable with 51,000 keys:
  Target false positive rate: 1%
  m = n * bits_per_element = 51,000 * 10 = 510,000 bits = 62.5 KB
  k = (m/n) * ln(2) = 10 * 0.693 = 6.93 -> use k=7 hash functions
```

**Adding a key (during SSTable construction):**

```
key = "user:12345"
  h1("user:12345") = 42    -> set bit 42 = 1
  h2("user:12345") = 1337  -> set bit 1337 = 1
  h3("user:12345") = 8920  -> set bit 8920 = 1
  h4("user:12345") = 247   -> set bit 247 = 1
  h5("user:12345") = 3904  -> set bit 3904 = 1
  h6("user:12345") = 11204 -> set bit 11204 = 1
  h7("user:12345") = 6661  -> set bit 6661 = 1

Repeat for all 51,000 keys in the SSTable.
```

**Checking a key (during read):**

```
Query: is "user:99999" in this SSTable?
  h1("user:99999") = 42    -> bit 42 = 1 (but this was set by "user:12345")
  h2("user:99999") = 1598  -> bit 1598 = 0 -> STOP. "user:99999" is DEFINITELY NOT in this SSTable.

  Because: if "user:99999" were in the SSTable, ALL 7 of its hash positions would be 1.
  Bit 1598 is 0, so at least one hash position is 0, so the key was never inserted.
  -> Return "definitely not here" with 100% certainty. (NO FALSE NEGATIVES)

Another query: is "user:88888" in this SSTable?
  h1("user:88888") = 42    -> bit 42 = 1
  h2("user:88888") = 1337  -> bit 1337 = 1
  ...all 7 positions happen to be 1 (set by other keys that share these hash values)
  -> Bloom filter says "MAYBE HERE"
  -> Check the SSTable on disk -> key not found. This was a FALSE POSITIVE.
  False positive rate: 1% with our settings.
```

**Key properties:**

```
NO FALSE NEGATIVES:
  If a key IS in the SSTable, all its hash positions are 1.
  Bloom filter always returns "maybe here" for true members.
  We NEVER skip an SSTable that actually contains our key.

FALSE POSITIVES (1%):
  A key NOT in the SSTable might have all its hash positions accidentally set to 1.
  Bloom filter returns "maybe here" when the key is not actually there.
  Cost: 1 extra disk I/O per false positive.
  Acceptable: 100 SSTables * 1% = ~1 extra disk I/O per read.

CANNOT DELETE from a Bloom filter:
  Clearing a bit might affect other keys that also hash to that position.
  Solutions: counting Bloom filter (each bit is a counter), or XOR filter.
  LSM tree sidesteps this: SSTables are immutable. Bloom filter is built once and never modified.

Bloom filter cannot be updated:
  When compaction merges SSTables: build a new Bloom filter for the merged SSTable.
  The old Bloom filter is discarded along with the old SSTables.
```

**Memory calculation:**

```
Per-SSTable Bloom filter:
  51,000 keys * 10 bits = 510,000 bits = 62.5 KB

All SSTables in memory (ideally keep all Bloom filters in RAM):
  3 TB data / 64 MB per SSTable = 48,000 SSTables
  48,000 * 62.5 KB = 3 GB of Bloom filters per node

3 GB fits comfortably in a node with 64 GB RAM.
If RAM is tight: keep only L0 and L1 Bloom filters in memory (most recent = most likely to be read).
```

---

## Component 6: Vector Clocks and Conflict Resolution

**L6 depth. Know the intuition and when they are needed.**

### Why timestamps fail for conflict resolution

```
Scenario:
  T=0: Client A writes key K = "value1" (timestamp: T=0)
  T=1: Replica X receives the write, stores K="value1", clock=T=0
  T=1: Replica Y receives the write (late), stores K="value1", clock=T=0

  T=2: Network partition between X and Y
  T=2: Client A writes K = "value2" to Replica X (timestamp: T=2)
  T=2: Client B writes K = "value3" to Replica Y (timestamp: T=2)

  T=3: Network partition heals.
  Replica X: K = "value2", timestamp = T=2
  Replica Y: K = "value3", timestamp = T=2

  SAME TIMESTAMP. DIFFERENT VALUES. CONFLICT.
  Last-Write-Wins (LWW) cannot resolve this: timestamps are equal.
  
  Even worse: if clocks are not perfectly synchronized (they never are):
  "value3" might have timestamp T=2.001 and "value2" might have T=2.000.
  LWW picks "value3". Was "value3" actually written last? Not necessarily.
  Clock drift: servers can be seconds off. LWW is unreliable with clock drift.
```

### Vector clocks

**Concept:**

```
Each key-value pair carries a vector clock: a list of {node_id: version} pairs.
The vector clock captures the "causal history" of each write.

Notation: [A:1, B:0, C:0] means "node A has written this value once; B and C haven't"

Initial state: K = "value1", clock = [A:1, B:0, C:0]
  (Client wrote to node A, A incremented its counter)

Client A writes again to Replica X (node A):
  New clock: [A:2, B:0, C:0]
  Meaning: "this value has been written by A twice; built on top of the previous A:1 version"

Client B writes to Replica Y (node B):
  But Y's current clock for K is [A:1, B:0, C:0] (partition: hasn't seen A:2)
  New clock after B's write: [A:1, B:1, C:0]
  Meaning: "this value was written by B on top of A's first version"

After partition heals:
  Replica X has: K="value2", clock=[A:2, B:0, C:0]
  Replica Y has: K="value3", clock=[A:1, B:1, C:0]

Conflict detection:
  Compare [A:2, B:0, C:0] and [A:1, B:1, C:0]
  [A:2, B:0]: A incremented from 1 to 2, B stayed at 0
  [A:1, B:1]: A stayed at 1, B incremented from 0 to 1
  Neither vector clock is a prefix of the other.
  -> These are CONCURRENT writes (happened independently, can't determine order)
  -> CONFLICT: must be resolved by application or user
```

**Conflict resolution strategies:**

```
Strategy 1: Last-Write-Wins (LWW) with timestamp as tiebreaker
  Return the value with the highest timestamp.
  Problem: loses data (one write is silently discarded).
  Used by: Cassandra (by default), DynamoDB (with conditional writes)

Strategy 2: Return both values, let application resolve
  Return both "value2" and "value3" to the client.
  Application (or user) merges them.
  Example: Amazon shopping cart — merge both carts (union of items).
  Problem: application complexity.

Strategy 3: Application-specific merge
  For counters: last-write-wins semantics but keep both values and SUM them.
  For sets: union.
  For text: CRDTs (Conflict-free Replicated Data Types) — beyond L5 scope.

For L5: mention that conflicts exist, explain LWW is the common default,
note that vector clocks provide better causality tracking but are more complex.
For L6: explain the full vector clock mechanics and CRDT implications.
```

---

## Component 7: Merkle Tree Anti-Entropy — Background Replica Repair

**Analogy:** Two libraries want to verify they have the same books. They could compare every book one by one (slow). Or: each library computes a fingerprint (hash) of all books. If the fingerprints match, libraries are identical. If not: split the collection in half, compare fingerprints of each half. Recurse until you find the specific section that differs. Then compare and sync only that section.

This is Merkle tree anti-entropy.

### The problem without anti-entropy

```
Scenario:
  Node B crashes for 30 minutes.
  During those 30 minutes: 50,000 writes arrive.
  Hinted handoff stores these writes temporarily on other nodes.
  
  Node B comes back online.
  Hinted handoff: node A forwards the 50,000 writes to B.
  
  Problem: what if hinted handoff failed (too many writes, buffer exceeded)?
  Or: what if Node B was down for a week (longer than hinted handoff retention)?
  
  Without anti-entropy: Node B is permanently stale for those 50,000 keys.
  Quorum reads will still work (W=2, R=2: reads from 2 nodes that have the data).
  But: over time, divergence grows. Eventually the stale replica is useless.
```

### Merkle tree structure

```
For a node managing key range [0, 2^32):

Build a Merkle tree where:
  Leaves: hash(key + value) for each key stored on this node
    hash("user:00001" + "Alice") = 0xABCD1234
    hash("user:00002" + "Bob")   = 0x5678EFAB
    ...
  Internal nodes: hash(left_child_hash + right_child_hash)
  Root: single hash representing all data on this node

The tree is partitioned by key space:
  Root covers all keys [0, 2^32)
  Left child: [0, 2^31)
  Right child: [2^31, 2^32)
  And so on...

Depth = 32 (for 32-bit hash space)
But: only build leaves for non-empty key ranges (sparse Merkle tree)
```

**The comparison process:**

```
Node A (primary) wants to sync with Node B (replica):

Step 1: Exchange root hashes
  A sends: root_hash_A = 0x1234ABCD
  B sends: root_hash_B = 0x1234ABCD  (same -> DONE. Trees are identical.)
  
  OR: root_hash_A = 0x1234ABCD, root_hash_B = 0x5678EFAB (different -> diverged)

Step 2: If root hashes differ, recurse on children
  A sends: left_child_hash = 0xAAAA, right_child_hash = 0xBBBB
  B sends: left_child_hash = 0xAAAA, right_child_hash = 0xCCCC
  -> Left halves match. Right halves differ.
  -> Only recurse into right half: [2^31, 2^32)

Step 3: Continue recursing until leaf-level difference found
  After 32 levels: identify the exact key ranges that differ
  Send only the differing key-value pairs from A to B
  
  Key insight: compare hashes (cheap), transfer only differing data (minimal)
  With 1 million keys and 1,000 differing keys: transfer only 1,000 keys
  Without Merkle tree: transfer all 1 million keys to find the 1,000 different ones

Bandwidth savings:
  Without Merkle tree: 1M keys * 1 KB = 1 GB transfer to find differences
  With Merkle tree:
    1,000 differing keys * 1 KB = 1 MB transfer (actual data)
    + 32 levels * 2 hashes per level * 32 bytes = 2 KB (tree traversal messages)
    Total: 1 MB instead of 1 GB = 1000x savings
```

---

## Component 8: Sloppy Quorum and Hinted Handoff

**Analogy:** You text your friend Bob, who is offline. Your mutual friend Alice says "I'll forward this to Bob when he comes back online." That's hinted handoff. Alice is not Bob's server — she is just storing the message temporarily, with a hint that it should go to Bob.

### The availability dilemma

```
With strict quorum (W=2, N=3):
  All 3 nodes for key K are: A, B, C
  Node B is temporarily down (network glitch)
  
  Client writes key K.
  Coordinator can reach A and C (2 nodes). W=2 is satisfied.
  
  Strict quorum: B must be one of the N=3 designated replicas.
  B is down. N=3 can only be satisfied if B is available.
  -> Return WRITE FAILURE. Client gets an error.
  
  This maximizes consistency but sacrifices availability.
  Amazon's finding (Dynamo paper): the most common failure mode is a single node being
  briefly unavailable. Strict quorum causes many spurious write failures.
```

### Sloppy quorum

```
Sloppy quorum: instead of requiring the write to reach the DESIGNATED N replicas,
allow it to reach ANY W available nodes.

Node B is down. Client writes key K.
Designated replicas: A, B, C.
A and C are available. W=2.

With sloppy quorum:
  Write to A (success) and C (success): W=2 satisfied.
  
  But wait: the key should also be on B.
  -> Hinted handoff: C stores the write with a hint: "this belongs to B"
     C's local store now has: key K (normal) + key K (hinted, for B)
  
  When B comes back online:
  C detects B is alive again (via gossip).
  C forwards the hinted write to B.
  B stores key K.
  C deletes its hinted copy.
  
  Result: write succeeded despite B being down.
  Consistency: B is temporarily stale (eventual consistency).
  Availability: write succeeded (sloppy quorum enables this).
```

**Implementation details:**

```
Hinted handoff storage:
  Local KV store on each node with a separate namespace:
    hinted_writes: {target_node: B, key: K, value: v, timestamp: T}
  
  Hinted handoff buffer size: bounded (e.g., 1 GB)
  If buffer fills: stop accepting hinted writes. Write failure.
  (Rare: only if a node is down for a very long time)

Recovery process (when B comes back):
  C sends hinted write to B: put(K, v, timestamp=T)
  B receives: if B's current version is older than T, accept the write
  B acknowledges to C.
  C deletes its hinted copy.

Anti-entropy is the backstop:
  If hinted handoff fails (C goes down before forwarding to B):
  Anti-entropy (Merkle tree comparison) will detect B's staleness and repair it.
  Typical anti-entropy frequency: every 10 minutes.
```

---

## Deep Dive: WAL — Write-Ahead Log Internals

**Why "write-ahead"?**

```
The invariant: the WAL must be written to disk BEFORE the MemTable is updated.

Crash recovery scenario:
  Write arrives: put("user:12345", "Alice")
  
  Without WAL:
    Update MemTable in memory.
    Node crashes. MemTable (in RAM) is lost. Write is gone.
    
  With WAL (write-ahead):
    1. Append to WAL file: [seq=10001] PUT user:12345 Alice\n
    2. fsync WAL file to disk (flush OS buffers -> durable on disk)
    3. Update MemTable in memory.
    4. Return success to client.
    
    Node crashes after step 2 but before step 3:
    Restart: replay WAL from last SSTable flush point.
    WAL entry [seq=10001]: apply to MemTable.
    MemTable is reconstructed. No data lost.
```

**WAL format:**

```
Each WAL entry:
  +--------+----------+----------+-------------+----------+
  | seq_no | type     | key_size | value_size   | checksum |
  | (8B)   | (PUT=1   | (4B)     | (4B)         | (4B)     |
  |        |  DEL=2)  |          |              |          |
  +--------+----------+----------+-------------+----------+
  | key (variable)         | value (variable)             |
  +------------------------+------------------------------+

seq_no: monotonically increasing. Used to detect partial writes.
type: PUT or DELETE.
checksum: CRC32 of the entry. If checksum fails on replay: truncate WAL at this point.

WAL file rotation:
  When MemTable is full and flushed to SSTable:
  The WAL entries up to the flush are no longer needed (data is in SSTable).
  WAL file is truncated (or a new WAL file is started).
  Only the WAL entries AFTER the last SSTable flush are kept.
```

**The durability trade-off:**

```
fsync on every write:
  Guarantees: no data loss on crash (up to the last acknowledged write)
  Cost: 1-5ms latency per write (SSD fsync latency)
  At 10,000 writes/sec: 10,000 fsyncs/sec -> exceeds most SSDs' fsync throughput
  
  SSD fsync throughput: ~5,000-10,000 IOPS (for 4KB fsyncs)
  At 10,000 fsyncs/sec: SSD is at 100% fsync capacity -> bottleneck

Group commit (solution):
  Buffer writes in memory for T=1ms or until B=100 writes accumulate.
  Issue one fsync for the group.
  
  At 10,000 writes/sec: in 1ms, we accumulate 10 writes.
  10 writes -> 1 fsync -> 10 confirmations returned simultaneously.
  fsync rate: 1,000/sec (10x reduction). SSD easily handles this.
  
  Latency cost: writes now wait up to 1ms extra.
  At 10,000 writes/sec: p50 latency increases from 1ms to 2ms. Acceptable.

Async WAL (maximum throughput, reduced durability):
  fsync every T=100ms (batching up to 1,000,000 writes).
  If crash occurs: lose last 100ms of writes.
  Used by: Kafka (configurable), some Redis persistence modes.
  Not appropriate for a KV store that advertises durability.
```

---

## Failure Scenarios

### Failure 1: One replica node crashes

```
Setup: N=3, W=2, R=2. Nodes A, B, C own key K.
Node B crashes.

Write path:
  Coordinator sends write to A, B, C.
  A: success.
  B: no response (crash).
  C: success.
  W=2 satisfied (A and C). Return success.
  Hinted handoff: A or C stores write for B with hint "forward to B on recovery".

Read path:
  Coordinator sends read to A, B, C.
  A: returns v=5.
  B: no response.
  C: returns v=5.
  R=2 satisfied (A and C agree: v=5). Return v=5.

Recovery (B comes back):
  A forwards hinted write to B.
  Gossip: all nodes know B is alive again.
  Anti-entropy: in background, compare Merkle trees A/C vs B. Repair any differences.
  After recovery: all 3 replicas have the same data.
  
Blast radius: none for clients. Reads and writes succeed normally (W=2, R=2 with 3 nodes, 1 down).
```

### Failure 2: Two replica nodes crash (N=3, W=2)

```
Nodes B and C crash. Only node A is alive.

Write path:
  Coordinator sends write to A, B, C.
  A: success.
  B, C: no response.
  W=2 NOT satisfied (only 1 node acknowledged).
  Return WRITE FAILURE to client.

With sloppy quorum:
  Coordinator writes to A, D, E (next available nodes on the ring)
  A: success, D: success (D stores hinted for B), E: success (E stores hinted for C)
  W=2 satisfied.
  Return success.
  When B and C recover: D and E forward hinted writes.
  
  Availability: writes succeed despite 2 replicas down.
  Consistency: reads may return stale data if they hit only A, D, E.

Read path (without sloppy quorum):
  Coordinator sends read to A, B, C.
  Only A responds. R=2 not satisfied.
  Return READ FAILURE to client.
  
  With DEGRADED mode (R=1 during partial failures): return A's value.
  Application must handle potentially stale data.

Blast radius: writes fail (or use sloppy quorum). Reads may return stale data.
```

### Failure 3: Compaction causes write stall

```
Background compaction merges SSTables.
Compaction requires reading and writing to disk.
Simultaneously: incoming writes want to flush MemTable to a new SSTable.

Write stall: if too many L0 SSTables pile up (because compaction can't keep up):
  Compaction worker is slower than flush rate.
  L0 SSTables accumulate (4, 8, 16...).
  When L0 count exceeds threshold (e.g., 20): WRITE STALL.
  All incoming writes are blocked until compaction catches up.

Symptoms: p99 write latency spikes from 5ms to 500ms+.
  Monitoring: track L0 SSTable count. Alert at L0 > 10.

Fix:
  Increase compaction workers from 2 to 4.
  Temporarily reduce flush threshold (flush MemTable at 32 MB instead of 64 MB).
  Add more nodes (reduce write rate per node).
  
  Permanent fix: tune compaction rate to match write rate:
  compaction_rate > flush_rate always.
  If flush_rate > compaction_rate: add compaction resources or reduce write rate.
```

### Failure 4: Hot key overloads one node

```
Key "global_config" is read 50,000 times/second by all services.
All reads route to node A (consistent hashing: A owns this key range).

Node A: 50,000 reads/sec for one key, plus its normal load.
CPU on Node A: 95% utilization. p99 latency: 200ms.

Fix 1: Application-level caching
  Each application server caches "global_config" for 1 second.
  50,000 reads/sec -> 10 servers * 1 read/sec = 10 reads/sec to Node A.
  Cost: config changes take up to 1 second to propagate.

Fix 2: Key replication (replication beyond N=3)
  Replicate "global_config" to all 10 nodes.
  Reads can be served by any node.
  50,000 reads/sec / 10 nodes = 5,000 reads/sec per node.
  Cost: every write to "global_config" must propagate to all 10 nodes.

Fix 3: Key splitting (for keys with natural sub-keys)
  If "global_config" has multiple independent sub-keys:
  "global_config:feature_flags" -> Node A
  "global_config:rate_limits" -> Node C (different hash)
  "global_config:ab_tests" -> Node E (different hash)
  50,000 reads now split 3 ways: ~16,666 reads/sec per node.

Detection: monitor read rate per key. Alert if any key > 1,000 reads/sec.
```

### Blast radius table

```
Failure                | User impact                    | Recovery
-----------------------|--------------------------------|---------------------------
1 of 3 replicas down   | None (W=2, R=2 still works)    | Automatic on recovery
2 of 3 replicas down   | Writes fail (or sloppy quorum) | Manual node recovery
Compaction stall       | Write latency spikes           | Tune compaction resources
Hot key overload       | Latency on affected node       | App caching or key splitting
Network partition      | Consistency vs availability    | Sloppy quorum + anti-entropy
WAL corruption         | Data loss (partial)            | Replay from checksum point
Bloom filter incorrect | Extra disk I/Os (reads slow)   | Rebuild Bloom filter on start
```

---

## SSE-Level Brainstorming Questions (Concept-Focused)

### LSM Tree concepts

1. Walk me through what happens to a single put(key="user:99", value="Alice") request from the moment it arrives at a storage node to the moment "success" is returned to the client.
2. Why does the MemTable use a Red-Black Tree (or AVL tree) instead of a hash map? (Answer: a sorted tree preserves key order for sequential SSTable flush; a hash map does not.)
3. An SSTable is described as "immutable." Why is immutability valuable for a storage engine? What operations would break if SSTables were mutable?
4. Explain the difference between "read amplification," "write amplification," and "space amplification." For leveled compaction, give an approximate value for each.
5. A database has 1,000 SSTables on disk. A read for a key that does not exist (e.g., the key was never inserted) must check every SSTable in the worst case. How does the Bloom filter reduce the average case? What is the expected number of SSTables checked with a 1% FP rate?
6. A tombstone is written for a deleted key. Why can't the key be immediately removed from the SSTable? When is it actually removed?
7. Compaction is a background process. What happens to incoming reads and writes while compaction is running? (Answer: reads and writes continue normally; compaction uses separate I/O threads; write stall only occurs when L0 SSTable count gets too high.)
8. What is the difference between leveled compaction and size-tiered compaction? Which produces lower read amplification? Which produces lower write amplification?
9. If a node crashes and restarts, the MemTable is lost. Explain step by step how the WAL is used to reconstruct the MemTable.
10. How does the WAL's seq_no help detect and handle a partial write (e.g., node crashed mid-write, leaving a corrupt WAL entry)?

### Consistent hashing concepts

11. Explain why consistent hashing causes only 1/(N+1) fraction of keys to be remapped when a node is added, compared to N/(N+1) for simple modulo hashing.
12. With virtual nodes, adding node F with 150 vnodes to a 10-node cluster: which nodes lose keys to F, and how many keys does each lose?
13. What is the role of the ring table? How large is it? How is it kept consistent across all nodes? (Answer: gossip protocol propagates ring membership changes.)
14. When a node is removed (graceful shutdown, not crash): how are its keys migrated to other nodes? Describe the specific mechanism.
15. Consistent hashing assigns keys to the nearest node clockwise. Why clockwise and not counterclockwise? (Trick: the direction is arbitrary — the important property is consistency, not the direction.)
16. With 10 nodes and N=3 replication: how many nodes are responsible for a given key? Describe exactly which nodes they are in terms of the ring.

### Quorum concepts

17. If N=5, W=3, R=3: does this guarantee strong consistency? (Yes: W+R=6 > N=5.)
18. If N=5, W=1, R=5: does this guarantee strong consistency? (Yes: W+R=6 > N=5.) Is this practical? (No: requiring all 5 nodes to respond for every read is very slow and fragile.)
19. What is the difference between "strict quorum" and "sloppy quorum"? When does sloppy quorum sacrifice consistency?
20. Explain "read repair" step by step. When is it triggered? What happens if the stale replica is down when read repair is attempted?
21. With W=1, R=1, N=3: is it possible for a client to read a value that was never written? (Answer: yes — if a replica hasn't received a write yet, a read hitting that replica returns null or an old value.)
22. What is "quorum lease"? (When the coordinator holds a lease, it can serve reads locally for a bounded time without contacting other replicas, reducing latency for hot keys.)

### Gossip protocol concepts

23. Gossip converges to all-nodes-informed in O(log N) rounds. Prove this with the "each round, the information reaches 2x as many nodes" argument.
24. What is the difference between "push gossip" (A sends to B) and "push-pull gossip" (A sends to B, B replies with its own state)? Which is more efficient?
25. A node is falsely marked as dead (network blip). What happens to keys that were assigned to it? How does the system recover when the node comes back? (Hinted handoff + anti-entropy.)
26. Gossip messages grow as O(N) per message (each message contains the full membership list). At N=1,000 nodes, how large is each gossip message? Is this a problem? (Fix: delta gossip — only send changes, not the full state.)

### Bloom filter concepts

27. A Bloom filter has no false negatives. Prove this from the construction: if key K was inserted, all K's hash positions are set to 1. Any lookup for K finds all positions are 1, so it returns "maybe here."
28. You increase the number of hash functions k from 3 to 10. What happens to the false positive rate? (Decreases up to the optimal k, then increases as too many bits are set.)
29. The optimal k is m/n * ln(2). For m/n = 10 (10 bits per element): k = 10 * 0.693 = 6.93 ≈ 7. Verify that at k=7 and m/n=10, the FP rate is approximately 0.8%.
30. After compaction, old SSTables are deleted and new (merged) SSTables are created. What happens to the Bloom filters for the old SSTables?
31. A Bloom filter cannot support deletions. If we want to support deletions, what alternative data structure can be used? (Counting Bloom filter: each bit is a counter; decrement on delete. Risk: counter overflow. XOR filter: alternative approach, simpler and more space-efficient.)

### Storage engine concepts

32. Compare B-tree and LSM tree on: write throughput, read throughput for hot keys, read throughput for cold keys, space amplification, and crash recovery complexity.
33. Why is sequential disk write so much faster than random disk write? Explain in terms of HDD mechanics (seek time + rotational latency) and SSD NAND flash behavior (erase blocks).
34. What is "write stall" in an LSM tree? At what point does it trigger, and why?
35. If a MemTable is 64 MB and the average key-value pair is 1 KB: how many writes can the MemTable absorb before flushing? (64 MB / 1 KB = 65,536 writes.)
36. The WAL is an append-only file. Over time it grows without bound. How is WAL size managed? (Segment rotation: when MemTable is flushed to SSTable, WAL entries up to that point are no longer needed. The WAL segment is deleted or reused.)

### Distributed systems concepts

37. What is the difference between "linearizability" and "sequential consistency"? Which does quorum (W=2, R=2, N=3) provide?
38. Hinted handoff stores writes for a down node on another node. If the "hint carrier" also goes down before forwarding: what is the fallback? (Anti-entropy via Merkle tree comparison on recovery.)
39. Compare Merkle tree anti-entropy to full-table comparison for repairing divergent replicas. Quantify the bandwidth savings for 1 million keys with 1,000 differing.
40. Vector clocks grow indefinitely as more writes occur. How does Amazon's Dynamo address vector clock growth? (Truncate old {node: version} entries that exceed a threshold, accepting slight reduction in conflict detection precision.)

---

## Intern to Staff Progression

### Same question: "How do you prevent data loss when a node crashes mid-write?"

### Intern level

```
"We save the data to a file every few minutes."

Problem: data written between saves is lost.
No awareness of WAL or crash recovery mechanisms.
```

### L4 level

```
"We use write-ahead logging. Before we update anything in memory, we write to a log file.
On crash: replay the log to reconstruct state."

Correct direction. Missing: what exactly is in the log, what format, how fsync works,
how WAL and SSTable interact (WAL truncation after SSTable flush).
```

### L5 level

```
"Write path:
 1. Append to WAL: serialize the operation as [seq, PUT, key, value, checksum]
 2. fsync the WAL to ensure it's durable on disk
 3. Insert the key-value into the MemTable (in-memory Red-Black Tree)
 4. Return success to client

Crash recovery:
 1. Find the last SSTable flush point (recorded in a manifest file)
 2. Replay all WAL entries after that point
 3. Re-insert them into the MemTable
 4. MemTable is now in the state it was before the crash

The WAL is truncated after each MemTable flush (those entries are now safe in the SSTable).

For performance: use group commit — batch 100 writes, issue one fsync,
return success to all 100. Reduces fsync rate from 10,000/sec to 100/sec."
```

### L6 level

```
L6 adds:
- "WAL segment rotation: WAL is split into fixed-size segments (e.g., 128 MB). 
  When a segment is fully committed to SSTable: delete the segment.
  On recovery: only replay WAL segments that weren't committed. 
  This bounds recovery time even if WAL is large."

- "WAL corruption handling: each entry has a checksum. If replay hits a corrupt entry
  (e.g., partial write at crash boundary), stop replay at that point.
  The partial write at the boundary is discarded. 
  Only acknowledged writes (which made it through step 4 of the write path) survive.
  An acknowledged write that's in the WAL but not in the MemTable:
  Not possible — step 3 (MemTable insert) never fails, and step 4 (return success)
  comes after step 3. So any acknowledged write is either in WAL or in SSTable."

- "For multi-key atomicity (batched writes): use a WAL entry that includes all keys.
  On replay: apply all or none. This gives atomic multi-key writes without transactions."

- "The WAL should be on a separate disk (or separate SSD namespace) from the SSTables.
  SSTables: read-heavy I/O (compaction + reads).
  WAL: write-heavy I/O (appends only).
  Separating them avoids I/O contention and maximizes throughput for both."
```

---

## KV Store Variants at a Glance

```
+------------+----------+----------+----------+-------+--------+-----------+
| System     | Storage  | Dist?    | Consist. | Scale | Lang   | Use case  |
+------------+----------+----------+----------+-------+--------+-----------+
| Redis      | Memory   | Optional | Strong   | 1 TB  | C      | Cache,    |
|            | +persist | (Cluster)| (single) | (GBs  |        | session,  |
|            |          |          |          | RAM)  |        | leaderbd  |
+------------+----------+----------+----------+-------+--------+-----------+
| Memcached  | Memory   | Client-  | None     | GBs   | C      | Pure      |
|            | only     | side     | (no sync)| RAM   |        | cache     |
+------------+----------+----------+----------+-------+--------+-----------+
| RocksDB    | LSM tree | No       | Strong   | TBs   | C++    | Embedded  |
|            | (disk)   | (single) | (local)  | disk  |        | storage   |
+------------+----------+----------+----------+-------+--------+-----------+
| LevelDB    | LSM tree | No       | Strong   | GBs   | C++    | Embedded  |
|            | (disk)   | (single) | (local)  | disk  |        | storage   |
+------------+----------+----------+----------+-------+--------+-----------+
| DynamoDB   | Dynamo   | Yes      | Tunable  | 100s  | Prop.  | AWS       |
|            | (B-tree  | (managed)| (W+R>N)  | TB    | (AWS)  | serverless|
|            | leaf)    |          |          |       |        | workloads |
+------------+----------+----------+----------+-------+--------+-----------+
| Cassandra  | LSM tree | Yes      | Tunable  | PBs   | Java   | Write-    |
|            | (disk)   | (Dynamo) | (W+R>N)  |       |        | heavy,    |
|            |          |          |          |       |        | time-seri |
+------------+----------+----------+----------+-------+--------+-----------+
| etcd       | B-tree   | Yes      | Strong   | GBs   | Go     | Config,   |
|            | (disk)   | (Raft)   | (Raft)   | only  |        | coord.    |
+------------+----------+----------+----------+-------+--------+-----------+

Key differentiators at interview:
  Redis vs. Memcached: Redis has data structures, persistence, pub/sub. Memcached is pure multi-threaded cache.
  DynamoDB vs. Cassandra: DynamoDB is managed (AWS pays for ops). Cassandra is open-source, self-managed.
  LSM-backed vs. B-tree: LSM wins for writes (sequential). B-tree wins for reads (O(log n) always).
  Cassandra vs. etcd: Cassandra is high-scale eventual. etcd is small-scale strong (Raft).
```

---

## L5 vs L6 Calibration Table

```
+---------------------+---------------------------+--------------------------------+
| Dimension           | L5 (Senior SWE)            | L6 (Staff)                     |
+---------------------+---------------------------+--------------------------------+
| Storage engine      | LSM tree: MemTable, WAL,   | Adds: compaction strategy      |
|                     | SSTable, Bloom filter      | comparison (leveled vs tiered),|
|                     | explained correctly        | write amplification quantified |
+---------------------+---------------------------+--------------------------------+
| WAL durability      | fsync on write, WAL replay | Group commit optimization,     |
|                     | on crash recovery          | WAL segment rotation, corrupt  |
|                     |                            | entry handling with checksums  |
+---------------------+---------------------------+--------------------------------+
| Consistent hashing  | Virtual nodes, ring, why   | Proactively quantifies vnode   |
|                     | simple modulo fails        | overhead (36 KB ring table),   |
|                     |                            | discusses rebalancing protocol |
+---------------------+---------------------------+--------------------------------+
| Quorum              | W+R>N rule, 3 preset modes | Knows that quorum does not      |
|                     | (W=1/R=1, W=2/R=2,        | imply linearizability without  |
|                     | W=1/R=3), read repair      | additional protocol (Paxos).   |
|                     |                            | Explains quorum leases.        |
+---------------------+---------------------------+--------------------------------+
| Conflict resolution | Mentions LWW as default,   | Vector clocks: walks through   |
|                     | knows it can lose data     | causality tracking, explains   |
|                     |                            | why causally concurrent writes |
|                     |                            | cannot be resolved by LWW.     |
|                     |                            | Names CRDTs as a solution.     |
+---------------------+---------------------------+--------------------------------+
| Gossip protocol     | O(log N) convergence,      | Quantifies message size at     |
|                     | failure detection          | N=1,000 nodes, explains delta  |
|                     | via heartbeat staleness    | gossip optimization.           |
+---------------------+---------------------------+--------------------------------+
| Anti-entropy        | Mentions Merkle tree       | Walks through the tree         |
|                     | comparison for replica     | comparison at every level,     |
|                     | repair                     | quantifies bandwidth savings   |
|                     |                            | vs full scan (1000x savings).  |
+---------------------+---------------------------+--------------------------------+
| Hinted handoff      | "Store writes for down      | Explains buffer limits, what   |
|                     | replicas and forward later" | happens when buffer is full    |
|                     |                            | (write failure), and how       |
|                     |                            | anti-entropy handles handoff   |
|                     |                            | failure.                       |
+---------------------+---------------------------+--------------------------------+
| Hot key problem     | Not addressed (L5 bar)     | Detects via monitoring,        |
|                     |                            | explains key splitting,        |
|                     |                            | selective replication, and     |
|                     |                            | application-layer caching      |
|                     |                            | trade-offs.                    |
+---------------------+---------------------------+--------------------------------+
| Bloom filter        | Explains no false negatives,| Walks through optimal k        |
|                     | probabilistic false positive| derivation (k = m/n * ln2),   |
|                     | rate, per-SSTable          | explains why deletions are not |
|                     |                            | supported, offers counting     |
|                     |                            | Bloom filter as alternative.  |
+---------------------+---------------------------+--------------------------------+
| Monitoring          | Error rate, latency        | L0 SSTable count (compaction  |
|                     | percentiles               | health), read amplification    |
|                     |                            | ratio, write stall frequency,  |
|                     |                            | hinted handoff queue depth.   |
+---------------------+---------------------------+--------------------------------+
```

---

## Production Incidents

### Incident 1: Cassandra Compaction Falling Behind at Netflix (2013)

**Company:** Netflix  
**What happened:** Netflix ran Cassandra clusters for their recommendation data. During a traffic spike (Super Bowl Sunday streaming), the write rate increased 8x. The L0 SSTable count climbed from 4 to 60 within 20 minutes. Cassandra entered a write stall. The recommendation service timed out while waiting for writes to complete. Users saw "We couldn't find recommendations for you" for 45 minutes.

**Root cause:** Compaction throughput was tuned for average-day traffic (100 MB/sec write rate). The spike pushed it to 800 MB/sec. Compaction workers (2 per node) could flush SSTables but could not compact L0 fast enough. L0 count grew until the write stall threshold (50 SSTables) was hit.

**Fix:**
- Increased compaction workers from 2 to 6 per node
- Increased MemTable size from 64 MB to 256 MB (fewer flushes per second at same write rate)
- Set L0 compaction priority: when L0 count exceeds 10, temporarily pause all other compaction and focus exclusively on L0 -> L1 merges
- Added monitoring alert: alert when L0 count > 8 (well before the write stall threshold)

**Staff lesson:** Compaction must be sized for peak, not average. Compaction backlog during peaks is the most common cause of LSM-tree write stalls. Monitoring L0 SSTable count is as critical as monitoring write latency — it predicts write stalls before they happen.

---

### Incident 2: Amazon DynamoDB Gossip Cascade During AWS US-EAST-1 Outage (2011)

**Company:** Amazon (AWS)  
**What happened:** During the US-EAST-1 network disruption, DynamoDB nodes lost contact with their neighbors. The gossip protocol marked many nodes as "SUSPECTED_DEAD" simultaneously. Because gossip convergence was slow (50 nodes each gossiping to 2 random others per second), the "mark dead" information arrived at different nodes at different times. Some nodes began re-routing requests for keys that were on "dead" (actually alive) nodes to other replicas. The alive nodes received the same requests twice (from coordinator and from the re-routed path), causing duplicate writes. Write amplification during the 4-hour period: 3-4x normal.

**Root cause:** Gossip convergence was too slow relative to the failure detection timeout. Nodes made irreversible routing decisions based on incomplete (non-converged) gossip state. When the "dead" nodes were reachable again, the duplicate writes had already been acknowledged.

**Fix:**
- Increased gossip fanout from 2 to 4 neighbors per round (faster convergence: log_4 instead of log_2)
- Added "SUSPECTED" state with a hold period before acting on "DEAD" state (must be SUSPECTED for 2 rounds before routing changes happen)
- Hinted handoff: write the duplicate to a "hints" namespace so it can be reconciled, not applied as a separate write

**Staff lesson:** Gossip convergence speed determines how quickly failure detection information propagates. Faster gossip (higher fanout) reduces the window of routing inconsistency. The SUSPECTED state adds a grace period that avoids false positives causing premature rerouting.

---

### Incident 3: LevelDB Bloom Filter Memory Bug at LinkedIn (2014)

**Company:** LinkedIn  
**What happened:** LinkedIn used LevelDB-backed storage for their InMail messaging system. A memory optimization change accidentally loaded Bloom filters from disk on every SSTable open instead of keeping them in memory. For a node with 8,000 SSTables, every "key not found" read caused 8,000 disk reads (no Bloom filter in memory to skip SSTables). p99 read latency went from 8ms to 8 seconds. The InMail service timed out for all users for 2 hours while the root cause was identified.

**Root cause:** The memory optimization change freed up RAM by unloading Bloom filters after each SSTable read. The assumption was "Bloom filters are cheap to reload from disk." Reality: 8,000 * 62.5 KB = 500 MB of Bloom filters, reloaded on every read for cold keys = massive I/O.

**Fix:**
- Bloom filters are always kept in memory (reverted the optimization)
- Added explicit tracking of Bloom filter memory usage (now a monitored metric)
- Added per-read monitoring: if a single read triggers more than 5 SSTable file opens, alert

**Staff lesson:** Bloom filter memory usage is small relative to the I/O cost of not having them in memory. The Bloom filter is not optional for an LSM tree — it is the mechanism that makes LSM reads practical. Never unload Bloom filters from memory as an optimization.

---

### Incident 4: Redis Hot Key at Twitter (2020)

**Company:** Twitter  
**What happened:** Twitter used Redis for timeline caching. A single tweet went viral (a celebrity account with 100M followers tweeted something that trended globally). The tweet's timeline key was fetched 500,000 times per second. The Redis instance storing that key hit 100% CPU. p99 latency for all timeline reads on that shard: 2 seconds (from <1ms). The Twitter timeline was slow for millions of users for 40 minutes.

**Root cause:** Single Redis key ("timeline:celebrity_123") could not be distributed across multiple Redis instances. All 500K reads/sec hit the same Redis node. Redis is single-threaded — 500K operations/sec overwhelmed a single CPU.

**Fix:**
- Application-level caching in each web server: cache the hot timeline locally for 5 seconds
- Read replica sharding: replicate the hot key to 5 additional Redis instances; route reads round-robin
- Monitoring: alert when any single Redis key is accessed more than 1,000 times/second

**Staff lesson:** In Redis, every key is owned by exactly one slot (node). A hot key cannot be load-balanced within Redis itself. The fix must be at the application layer (local cache) or at the Redis layer (read replicas). Hot key monitoring is critical for any Redis-backed system that serves public-facing content.

---

### Incident 5: Cassandra Tombstone Cascade at Discord (2017)

**Company:** Discord  
**What happened:** Discord uses Cassandra to store message history (key = channel_id, value = sorted messages). Users can delete individual messages. Each deletion writes a tombstone. For very active channels (gaming communities with thousands of messages deleted per hour), tombstones accumulated faster than compaction could clean them up. Reading a channel's messages required scanning through millions of tombstones before finding live messages. Read latency for busy channels: 15 seconds. Some channels became completely unreadable.

**Root cause:** Tombstones are written with a TTL (gc_grace_seconds = 10 days in Cassandra). Until the TTL expires, tombstones must be kept (they signal "this data was deleted"). Compaction removes tombstones only after the TTL expires. For channels with millions of deletes: tombstones pile up for 10 days before cleanup.

**Fix:**
- Reduce gc_grace_seconds from 10 days to 2 hours for message channels (acceptable because: if a deleted message came back from a lag-behind replica after 2 hours, it would just appear briefly then be re-deleted on the next read repair)
- Partition channels by time bucket: instead of one key per channel, use "channel:{id}:{day}" so older time buckets get their tombstones compacted sooner
- Add monitoring: alert when a read query touches more than 10,000 tombstones before returning live data

**Staff lesson:** Tombstones are the LSM tree's Achilles heel for write-heavy workloads with many deletes. In Cassandra specifically, tombstone accumulation is a known operational risk. If your data model involves frequent deletes, test with realistic delete rates and monitor tombstone scan depth. TTL-based data (messages, sessions) should use Cassandra's built-in TTL feature on the data itself, not explicit delete operations.

---

## Exercises

### Exercise 1: LSM Tree Read Path Trace

**Problem:** A node has: MemTable (5,000 keys), SSTable_A (newest, 51,000 keys), SSTable_B (51,000 keys), SSTable_C (oldest, 51,000 keys). Each SSTable has a Bloom filter. The client reads key "user:99999". Trace the complete read path. How many disk I/Os occur in the best case and worst case?

**Solution:**

```
Step 1: Check MemTable
  Binary search in Red-Black Tree: O(log 5000) = ~12 comparisons
  "user:99999" not found in MemTable.
  Duration: <1 microsecond. Disk I/Os: 0.

Step 2: Check SSTable_A (newest)
  2a: Check SSTable_A's Bloom filter (in memory)
      h1("user:99999") -> bit = 1
      h2("user:99999") -> bit = 0 -> DEFINITELY NOT IN SSTable_A
      Disk I/Os: 0. Skip SSTable_A.
  Duration: <1 microsecond.

Step 3: Check SSTable_B
  3a: Check SSTable_B's Bloom filter (in memory)
      All 7 hash positions are 1 (1% false positive: this is the one false positive)
      -> "MAYBE IN SSTable_B"
  3b: Binary search SSTable_B's index block (in memory)
      Index says: "user:99999" would be in data block at offset 450,000
  3c: Read data block from disk (1 disk I/O)
      Binary search within 4KB data block: "user:99999" not found.
      (False positive confirmed: key is not actually here.)
  Disk I/Os: 1.

Step 4: Check SSTable_C (oldest)
  4a: Check SSTable_C's Bloom filter (in memory)
      h3("user:99999") -> bit = 0 -> DEFINITELY NOT IN SSTable_C
      Disk I/Os: 0. Skip SSTable_C.
  Duration: <1 microsecond.

Step 5: No more SSTables. Key not found. Return null.

Best case (key not in any SSTable, 0 false positives): 0 disk I/Os
Worst case (N SSTables, each is a false positive): N disk I/Os
Expected case (1% FP rate, 3 SSTables): 0.03 false positives -> ~1 disk I/O on average

If key IS found in SSTable_A:
  Step 2 Bloom filter says "maybe here" -> 1 disk I/O to find it.
  Total: 1 disk I/O. Fast.
```

---

### Exercise 2: Quorum Calculation

**Problem:** Design the optimal quorum settings for the following three use cases. Justify your choice of W and R given N=3.

Case A: Session data — millions of writes per second, stale reads for 1-2 seconds are acceptable.  
Case B: Financial ledger — every write must be durable and reads must always see the latest value.  
Case C: Configuration store — rarely written, very frequently read, correctness required.

**Solution:**

```
Case A: Session data
  W=1, R=1, N=3 (eventual consistency)
  Reasoning:
    Write: 1 node acknowledgement -> fast write. Millions of writes/sec feasible.
    Read: 1 node -> fast read. 1-2s stale is acceptable (session data is refreshed often).
    The 1-2 second staleness comes from: async replication propagation delay.
    Loss of a session on node failure: user is asked to log in again. Acceptable UX.

Case B: Financial ledger
  W=2, R=2, N=3 (strong consistency: W+R=4 > N=3)
  Reasoning:
    Write: 2 nodes must acknowledge -> write is durable even if 1 node crashes immediately after.
    Read: 2 nodes queried -> at least 1 overlaps with the write set -> always latest value.
    Trade-off: 1.5x slower than W=1/R=1 (must wait for 2nd acknowledgement).
    Acceptable: financial ledger writes are lower volume, latency matters less than correctness.

Case C: Configuration store
  W=3, R=1, N=3 (strong consistency: W+R=4 > N=3)
  Reasoning:
    Write: must reach all 3 nodes before acknowledging.
      Reason: config is rarely written, so the extra latency per write is acceptable.
    Read: only 1 node -> fastest possible read. 100K config reads/sec per service.
      Any node has the latest config (because writes go to all 3 first).
    Trade-off: writes are slowest possible (require all 3). Reads are fastest possible.
    This is the right trade-off for rarely-written, frequently-read configuration.

Alternative for Case C:
  W=2, R=2, N=3 is also correct (strong consistency, balanced).
  W=3/R=1 is the extreme optimization: sacrifices write availability (all 3 must be up)
  for maximum read performance (any 1 node suffices).
  If 1 node is down, W=3 cannot be satisfied -> write fails.
  For critical config: "no writes during partial failure" might be acceptable (rare writes).
```

---

### Exercise 3: Bloom Filter Math

**Problem:** You are building an SSTable with 100,000 keys. Design a Bloom filter targeting a 0.5% false positive rate.

a) How many bits (m) do you need?  
b) How many hash functions (k) do you need?  
c) What is the total memory usage in KB?  
d) A node has 10,000 SSTables. All Bloom filters are kept in memory. What is the total Bloom filter memory?

**Solution:**

```
Given:
  n = 100,000 keys
  p = 0.5% = 0.005 false positive rate

a) m = -n * ln(p) / (ln(2))^2
  ln(0.005) = -5.298
  ln(2)^2 = 0.4805
  m = -100,000 * (-5.298) / 0.4805 = 529,800 / 0.4805 = 1,102,810 bits
  Round up: m = 1,102,816 bits (nearest multiple of 8)
  In bytes: 1,102,816 / 8 = 137,852 bytes = 134.6 KB

  Alternatively: use the approximation bits_per_element for p=0.5%:
  At 1% FP rate: ~10 bits per element
  At 0.5% FP rate: each halving of FP rate costs ~1 additional bit per element
  0.5% = 1%/2 -> approximately 11 bits per element
  100,000 * 11 = 1,100,000 bits = 134.5 KB (close to exact calculation)

b) k = (m / n) * ln(2)
  m/n = 1,102,816 / 100,000 = 11.03 bits per element
  k = 11.03 * 0.693 = 7.64 -> round to k = 8 hash functions

c) Memory usage per SSTable:
  134.6 KB (from calculation above)

d) Total Bloom filter memory for 10,000 SSTables:
  10,000 * 134.6 KB = 1,346,000 KB = 1,346 MB = 1.31 GB
  
  Is this acceptable?
  A node with 64 GB RAM: Bloom filters use 1.31 GB = 2% of RAM. Acceptable.
  MemTable: up to 512 MB.
  OS page cache (SSTable data blocks): 62 GB remaining.
  The Bloom filter memory is well worth it: it eliminates 99.5% of disk I/Os for missing keys.
```

---

### Exercise 4: Consistent Hashing Node Addition

**Problem:** A cluster has 5 nodes on the consistent hashing ring with the following positions:
- Node A: 100
- Node B: 300
- Node C: 500
- Node D: 700
- Node E: 900

With N=3 replicas, identify the 3 replica nodes for each of these keys:
- Key "session:abc" hashes to 250
- Key "user:xyz" hashes to 650

Then, a new Node F is added at position 600. Which keys (from which nodes) must be migrated to Node F?

**Solution:**

```
Ring layout (clockwise):
  100(A) -> 300(B) -> 500(C) -> 700(D) -> 900(E) -> [wrap] -> 100(A)

Key "session:abc" at position 250:
  Walk clockwise from 250: first node is B (300).
  Replica 1: B (300)
  Replica 2: C (500) - next clockwise
  Replica 3: D (700) - next clockwise
  Replicas: B, C, D

Key "user:xyz" at position 650:
  Walk clockwise from 650: first node is D (700).
  Replica 1: D (700)
  Replica 2: E (900) - next clockwise
  Replica 3: A (100) - next clockwise (wrap around ring)
  Replicas: D, E, A

Adding Node F at position 600:
  New ring: 100(A) -> 300(B) -> 500(C) -> 600(F) -> 700(D) -> 900(E) -> [wrap] -> 100(A)

  Keys that move to F:
    Keys between C (500) and F (600) — these were previously on D (first node after 500).
    Now they are on F (new first node after 500+).
    
  For key "user:xyz" at position 650:
    Before F: clockwise from 650 = D. Replicas: D, E, A.
    After F: F is at 600, which is BEFORE 650.
    Clockwise from 650 = still D (600 < 650 < 700). F is BEHIND 650 on the ring.
    Wait: F is at 600, key is at 650. Clockwise from 650: next position >= 650 is D at 700.
    So "user:xyz" still goes to D, E, A. No migration needed.
    
  What actually moves to F:
    Keys that hashed to 501-600 (positions between C and F).
    Before: these went to D (first node after 500).
    After F added: these go to F (first node after 500+, since F=600 < D=700).
    
  Who loses these keys?
    D was responsible for positions 501-700. Now D is responsible for 601-700.
    F takes 501-600 from D.
    
  Migration:
    D sends all keys in range [501, 600] to F.
    F also needs replicas:
    - F's own range keys: Replica 1 = F, Replica 2 = D (next), Replica 3 = E (next)
    - D should already have these keys as Replica 2 (it was Replica 1 before)
    - D keeps them (now as Replica 2 for F's range)
    - E needs to receive these keys as Replica 3 (if it doesn't already have them)
    
  In practice with virtual nodes: 150 vnodes per node.
  Adding F's 150 vnodes: ~150 small key migrations from different nodes on the ring.
  Each existing node loses ~30 key ranges to F (150 / 5 existing nodes).
  No large single migration.
```

---

### Exercise 5: Gossip Convergence Time

**Problem:** A cluster has N=1,000 nodes. Each node gossips to 3 random nodes per second (fanout = 3). A node fails at T=0. How many seconds until at least 95% of nodes know about the failure?

**Solution:**

```
Gossip spread model:
  At T=0: 1 node has seen the failure (the coordinator that detected it)
  Each gossip round: each informed node tells 3 new nodes
  But: some of the 3 randomly chosen nodes may already know (redundancy grows)

Simple lower bound (ignoring redundancy):
  Round 0: 1 node knows
  Round 1: 1 + 3 = 4 nodes know
  Round 2: 4 + 4*3 = 16 nodes know (if no overlap)
  Round k: approximately min(3^k, 1000) nodes know

  To reach 950 nodes (95% of 1000):
  3^k >= 950
  k >= log_3(950) = ln(950) / ln(3) = 6.856 / 1.099 = 6.24
  k = 7 rounds = 7 seconds (one round per second)

More accurate (with redundancy, epidemic model):
  The Kermack-McKendrick epidemic model:
  After k rounds, the number of informed nodes S(k) satisfies:
  S(k) = N * (1 - e^(-3k/N * S(k-1)))
  This is hard to solve exactly, but empirically:
  For fanout=3, N=1000: 95% informed after ~8-10 seconds.

Answer: approximately 7-10 seconds.

To reduce convergence time (L6 extension):
  Increase fanout from 3 to 6: 95% after ~5 seconds.
  Trade-off: more gossip messages (6x instead of 3x per node per second).
  1000 nodes * 6 messages/sec = 6,000 messages/sec for failure detection.
  At 1 KB per message: 6 MB/sec network overhead for gossip. Acceptable.

Real systems (Cassandra, etcd):
  Cassandra gossip fanout: 3, interval: 1 second.
  Failure detection timeout: 10 seconds (5 heartbeat intervals without update).
  In practice: failures detected within 20-30 seconds cluster-wide.
```

---

## Homework

### Short homework

**Short 1:** Install RocksDB (or use an online demo). Write 1,000 key-value pairs. Then issue 1,000 reads — 500 for keys that exist, 500 for keys that don't. Use the performance counters to observe:
- Number of Bloom filter queries and false positives
- Number of disk reads for missing keys vs. present keys
- MemTable vs. SSTable hit rate

**Short 2:** Implement a simple Bloom filter in Python or Go:
- 10,000-bit array, 7 hash functions (use sha256 with different seeds)
- Insert 1,000 words from /usr/share/dict/words
- Query 1,000 words not in the insert set
- Measure: how many false positives occur? Is it close to the theoretical 1%?

**Short 3:** Read the original Amazon Dynamo paper (search: "Dynamo Amazon's Highly Available Key-value Store 2007"). Identify: which specific sections map to consistent hashing (Section 4.2), quorum (Section 4.5), gossip (Section 4.8), and Merkle tree anti-entropy (Section 4.7)? Write a one-paragraph summary of each.

### Deep homework

**Deep 1:** Build a single-node LSM tree in Python:
- MemTable: use Python's sorted dict (SortedDict from sortedcontainers)
- WAL: write each put/delete to a file in append-only mode
- SSTable: when MemTable exceeds 1 MB, serialize to a file (JSON lines, sorted by key)
- Bloom filter: use the pybloom library for each SSTable
- Read path: check MemTable, then SSTables newest to oldest, using Bloom filter to skip
- Test: 100,000 writes + crash simulation (kill process) + restart + verify reads are correct

**Deep 2:** Simulate a consistent hashing ring:
- 10 nodes, each with 150 virtual nodes
- Hash function: MD5 (or SHA1) of node name + vnode index
- Add 10,000 keys to the ring. For each key, find the 3 replica nodes (N=3).
- Measure key distribution across physical nodes (should be approximately 1,000 keys per node ± 20%)
- Remove one node. Measure: what fraction of keys had to move? Compare to the theoretical 1/(N+1) = 9.1%.
- Add one node. Measure: what fraction of keys moved?

**Deep 3:** Read the Bigtable paper (Google, 2006) and the LevelDB codebase README. LevelDB is Google's open-source implementation of Bigtable's tablet storage engine. Compare:
- How does LevelDB's compaction strategy differ from Bigtable's?
- What did Google learn from Bigtable that they changed in LevelDB?
- How does RocksDB (Meta's fork of LevelDB) differ from LevelDB?

---

## Glossary

**MemTable:** An in-memory sorted data structure (Red-Black Tree or skip list) that absorbs writes before they are flushed to disk. All reads check the MemTable first (it has the most recent writes). When the MemTable exceeds a size threshold (e.g., 64 MB), it is frozen and flushed to a new SSTable.

**WAL (Write-Ahead Log):** An append-only file on disk to which every write is durably committed before the MemTable is updated. On crash recovery, the WAL is replayed to reconstruct the MemTable. Ensures no data loss for acknowledged writes.

**SSTable (Sorted String Table):** An immutable, sorted file on disk containing key-value pairs. Each key appears at most once. SSTables are created by flushing the MemTable. Multiple SSTables can coexist; they are merged and compacted over time.

**Bloom filter:** A probabilistic data structure that answers "might this key be in this set?" with no false negatives and a configurable false positive rate (typically 1%). Used per SSTable to avoid unnecessary disk reads for keys not in the SSTable.

**Compaction:** A background process that merges multiple SSTables into fewer, larger SSTables. Compaction removes deleted keys (tombstones) and old versions of updated keys, reclaiming space and reducing read amplification.

**Read amplification:** The number of disk I/Os required to serve a single read. In LSM trees: 1 (MemTable hit) to N (must check all N SSTables). Compaction and Bloom filters reduce read amplification. B-trees have O(log n) read amplification always.

**Write amplification:** How many times each byte of user data is written to disk throughout its lifetime. For leveled compaction: 10-30x. Caused by data being rewritten during each compaction level merge.

**Space amplification:** The ratio of disk space used to the size of live data. Old versions and tombstones increase space amplification until compaction cleans them up.

**Consistent hashing:** A hash ring where each node is assigned a range of the key space. Adding/removing a node only migrates O(1/N) fraction of keys, unlike modulo hashing which migrates O((N-1)/N) keys.

**Virtual nodes (vnodes):** Each physical node is assigned multiple positions (150 by default) on the consistent hashing ring. Vnodes distribute load more evenly and allow gradual key migration when nodes are added or removed.

**Quorum:** In a cluster of N replicas, a quorum of W nodes for writes and R nodes for reads satisfies W + R > N -> strong consistency. If W + R ≤ N: eventual consistency.

**Gossip protocol:** A decentralized failure detection mechanism where each node periodically shares its view of the cluster with random neighbors. Information propagates in O(log N) rounds. No central coordinator needed.

**Hinted handoff:** When a replica is temporarily down, another node stores the write with a "hint" indicating the intended destination. When the destination node recovers, the hint is forwarded and applied.

**Anti-entropy:** A background process that compares Merkle tree hashes between replicas and transfers differing key-value pairs to bring all replicas into sync. The backstop for hinted handoff failure.

**Merkle tree:** A tree where leaf nodes contain hashes of key-value pairs, and internal nodes contain hashes of their children. Comparing root hashes between two nodes quickly identifies whether they differ; recursing into the tree locates the specific differing key ranges.

**Tombstone:** A deletion marker written in place of a key's value. Since SSTables are immutable, a deleted key cannot be removed immediately. The tombstone propagates to all replicas and is removed during compaction after the TTL expires.

**Sloppy quorum:** An availability optimization that allows writes to proceed even if some designated replicas are down, by temporarily writing to other available nodes and using hinted handoff to forward the writes when the designated replicas recover.

**Vector clock:** A list of {node: version} pairs that tracks the causal history of a key's writes. Two writes are causally related if one's vector clock is a strict prefix of the other's. Otherwise, they are concurrent and constitute a conflict that requires resolution.

**LWW (Last-Write-Wins):** A conflict resolution strategy that keeps only the write with the highest timestamp, discarding concurrent writes. Simple to implement but loses data. Used by Cassandra (by default) and DynamoDB (by default).

---

## The One-Sentence Summary

> "Key-value store = LSM tree (every write appends to WAL for durability, then enters in-memory MemTable, and when MemTable is full, flushes to sorted immutable SSTable on disk; Bloom filter per SSTable eliminates 99% of disk reads for missing keys; compaction background-merges SSTables to reclaim space and reduce read amplification) + consistent hashing with virtual nodes for distributing keys across nodes (adding/removing a node migrates only 1/N fraction of keys) + quorum reads/writes (W + R > N guarantees that the read set and write set overlap, ensuring strong consistency) + gossip protocol for failure detection + Merkle tree anti-entropy for replica repair — the core insight is that write-optimized storage (append-only, sequential disk writes) enables high write throughput at the cost of read amplification, which is then recovered by Bloom filters and compaction."

---

## Interview Q&A — Most Common Cross-Questions

These are the follow-up questions interviewers ask immediately after your design. Each answer is meant to be said out loud in under 60 seconds.

---

**Q1: Walk me through the write path — what happens to a single put("user:99", "Alice") from the moment it arrives at the node?**

Step 1: Append to the WAL (Write-Ahead Log). The entry is serialized as `[seq_no | PUT | key | value | checksum]` and written to an append-only file on disk. Then `fsync` — this guarantees the write survives a crash.

Step 2: Insert into the MemTable. The MemTable is a Red-Black Tree (sorted in-memory). Insert "user:99" → "Alice" at the correct sorted position. O(log n) in-memory operation, sub-microsecond.

Step 3: Return success to the client. The write is durable (WAL on disk) and visible (MemTable in memory).

Background: when the MemTable exceeds 64 MB, it is frozen and flushed to a new SSTable file on disk — a sorted, immutable file. The corresponding WAL segment is then discarded (data is safe in the SSTable). A new MemTable and WAL segment start for incoming writes.

---

**Q2: Walk me through the read path for get("user:99").**

Step 1: Check the MemTable. Binary search in the Red-Black Tree. If found, return immediately — sub-millisecond, 0 disk I/Os.

Step 2: Not in MemTable — check SSTables from newest to oldest. For each SSTable:

  a) Check its Bloom filter (in memory). If the Bloom filter says "definitely not here," skip — 0 disk I/Os.
  
  b) If the Bloom filter says "maybe here," binary search the SSTable's index block (in memory) to find the offset, then read that data block from disk — 1 disk I/O.
  
  c) If the key is found, return the value. If a tombstone is found, return null (key was deleted).

Step 3: If not found in any SSTable, return null.

Expected disk I/Os with Bloom filter (1% false positive rate, 100 SSTables): ~1 disk I/O for a missing key. Without Bloom filter: 100 disk I/Os. The Bloom filter is what makes LSM reads practical.

---

**Q3: What is an LSM tree? Why not just use a B-tree?**

LSM (Log-Structured Merge) tree is a storage engine designed to maximize write throughput by converting random disk writes into sequential disk writes.

Every write in an LSM tree is: (1) an append to the WAL (sequential), and (2) an in-memory insert into the MemTable. Sequential disk writes on SSDs are 5-10× faster than random writes. This is why write-heavy systems (Cassandra, RocksDB, HBase) use LSM trees.

B-trees (used by MySQL, PostgreSQL) store data in fixed-size pages. Every write must find the correct page on disk and update it in place — a random disk write. At 10,000 writes/sec on an HDD: 10,000 random writes/sec exceeds the HDD's random I/O capacity (~200 IOPS). Even on SSDs, random writes wear out NAND cells faster.

Trade-off: LSM writes are fast but reads for cold keys are slower (must check multiple SSTables). B-tree reads are always O(log n). Bloom filters and compaction reduce the LSM read overhead to 2-4 disk I/Os in practice.

---

**Q4: What is a WAL? Why must you write to it before updating the MemTable?**

WAL = Write-Ahead Log. An append-only file on disk. Every put/delete is recorded here before anything else is changed.

The invariant: the WAL must be durable (fsynced to disk) before the MemTable is updated. If the node crashes after the WAL write but before the MemTable insert, on restart you replay the WAL and re-insert the entry into the MemTable — no data loss.

If you updated the MemTable first and then crashed before writing the WAL: the MemTable is in RAM and is gone on crash. The write was never durably recorded anywhere. Data loss for a write you already acknowledged to the client — unacceptable.

The fsync is the expensive operation (1-5ms per call). Group commit optimization: batch 100 writes and issue one fsync. This reduces fsync rate from 10,000/sec to 100/sec, bringing write latency back down.

---

**Q5: What is an SSTable? Why is it immutable?**

SSTable (Sorted String Table) is a sorted, immutable file on disk. When the MemTable is full it is flushed to disk as a new SSTable. Keys are stored in sorted order inside the file. Once written, an SSTable is never modified.

Immutability is the key design choice: it allows the file to be safely read by multiple threads without locking. It enables the Bloom filter (built once on creation, never changes). It makes crash recovery simple (a partially written SSTable is discarded; the WAL covers the gap).

Updates to existing keys do not modify the old SSTable. A new MemTable entry is written, which eventually becomes a new SSTable. The old SSTable's version of that key becomes stale. Compaction merges SSTables and keeps only the latest version, removing the stale entry.

---

**Q6: What is a Bloom filter? How does it work?**

A Bloom filter is a probabilistic data structure that answers "might this key be in this SSTable?" It has no false negatives (if the key is in the SSTable, the Bloom filter always says "maybe") but has a configurable false positive rate (default 1% — says "maybe" for 1% of keys that are NOT in the SSTable).

Construction: a bit array of m bits (all zeros initially) and k hash functions. When adding a key, compute h1(key), h2(key), ..., hk(key), and set those bit positions to 1.

Query: compute the same k hash positions for the lookup key. If ALL bits are 1 → "maybe here" (check the SSTable on disk). If ANY bit is 0 → "definitely not here" (skip the SSTable entirely, no disk I/O).

Why no false negatives: if the key was inserted, all its bits were set to 1. They remain 1 (Bloom filters cannot unset bits). So a lookup for a truly present key always finds all bits = 1.

For 100 SSTables with 1% FP rate: only 1 extra disk I/O per read on average (1 false positive × 1 disk I/O). Without Bloom filters: 100 disk I/Os for a missing key — system would not be usable.

---

**Q7: What is compaction? Why is it needed?**

Compaction is a background process that merges multiple SSTables into fewer, larger SSTables. It removes deleted keys (tombstones) and old versions of updated keys.

Without compaction: every update creates a new SSTable entry. A key updated 1,000 times has 1,000 stale copies across 1,000 SSTables. Disk fills with obsolete data. Reads become slower because they must scan more SSTables. Tombstones for deleted keys accumulate forever.

With compaction: old SSTables are merged. Only the latest version of each key survives. Tombstones are removed (after the gc_grace_seconds TTL — needed to ensure all replicas have seen the deletion before the tombstone is removed). Disk space is reclaimed. Fewer SSTables = faster reads.

Trade-off: compaction consumes disk I/O and CPU in the background. If compaction cannot keep up with the write rate, L0 SSTables accumulate. When L0 count hits the threshold, a write stall occurs — all incoming writes are paused until compaction catches up.

---

**Q8: What is write amplification? What is the write amplification for leveled compaction?**

Write amplification is the ratio of actual bytes written to disk vs bytes written by the user. It accounts for all the times data is rewritten during compaction.

For leveled compaction: each byte of user data is written to:
- WAL: 1×
- L0 SSTable (MemTable flush): 1×
- Merge from L0 to L1: 10× (L1 is 10× larger than L0, so merging into L1 rewrites the data proportionally)
- Merge from L1 to L2: 10×
- ... each level is 10× the previous

Total for 4 levels: 1 (WAL) + 1 (L0) + 10 (L0→L1) + 10 (L1→L2) + 10 (L2→L3) ≈ 30×

This means storing 1 GB of user data causes ~30 GB of actual disk writes over its lifetime. This is the cost of better read performance (sorted, non-overlapping key ranges at each level).

Size-tiered compaction has lower write amplification (~10×) but worse read amplification — SSTables at the same level can overlap in key range, requiring more files to check per read.

---

**Q9: What is consistent hashing? Why not just use `shard_id = hash(key) % N`?**

With modulo hashing, adding or removing a node causes almost all keys to be remapped. Adding 1 node to a 5-node cluster: `hash(key) % 5` vs `hash(key) % 6` gives different results for 83% of keys. Migrating 83% of 10 TB = 8.3 TB of data. The system is unusable during this transfer.

Consistent hashing places nodes on a hash ring (0 to 2^32). Each key maps to the nearest node clockwise. Adding a new node F: only the keys between F's predecessor and F must move to F. With N nodes, that is 1/(N+1) of all keys — about 9% for a 10-node cluster. Migrating 9% of 10 TB = 0.9 TB. Vastly better.

Adding or removing a node only affects the adjacent key range, not the entire dataset.

---

**Q10: What are virtual nodes? Why are they needed?**

With one position per physical node, the key distribution is uneven — some nodes get more keys than others depending on where their hash falls on the ring. Also, if a node goes down, ALL of its keys move to one neighbor (that neighbor doubles in load).

Virtual nodes: each physical node is assigned 150 positions on the ring. A physical node "owns" 150 non-contiguous ranges spread across the ring.

Benefits: (1) Even distribution — 150 positions average out to uniform load. (2) When a node goes down, its 150 ranges are each picked up by different neighboring nodes. Load is spread across all surviving nodes, not doubled on one. (3) Adding a node: its 150 new positions take keys from many different existing nodes, spreading the migration cost.

Ring table size: 10 nodes × 150 vnodes = 1,500 entries × 24 bytes each = 36 KB. Kept in memory on every node, propagated via gossip.

---

**Q11: What is a quorum? Explain the W + R > N rule.**

Quorum is the minimum number of nodes that must acknowledge a write (W) or respond to a read (R) before the operation is considered complete.

The rule: if W + R > N (where N is the replication factor), then the write set and the read set must overlap by at least one node. That overlapping node has the latest write. So the read always sees the latest write → strong consistency.

Example with N=3: W=2, R=2. Write quorum: 2 of 3 nodes. Read quorum: 2 of 3 nodes. By pigeonhole principle, at least 1 node is in both sets. That node has the latest value.

If W + R ≤ N: the write set and read set might not overlap. A read might hit only nodes that missed the latest write → stale value → eventual consistency.

Common configurations:
- W=2, R=2, N=3 → strong consistency, balanced latency
- W=1, R=1, N=3 → eventual consistency, minimum latency
- W=3, R=1, N=3 → strong consistency, fastest reads (any node suffices), slowest writes

---

**Q12: What is read repair? When does it trigger?**

When a coordinator reads with quorum (e.g., R=2, N=3), it asks all 3 replicas. It waits for 2 responses, returns the latest value to the client. But it also compares all responses received.

If one replica returns a stale value (old version number), the coordinator sends an async write to that replica: "Your value for key K is outdated, here is the latest version." The lagging replica updates itself. Next read: all replicas agree.

Read repair is triggered on every quorum read where any responding replica is behind the latest version. It does not require a special process — it piggybacks on normal read traffic.

What it does NOT fix: keys that are never read. A key deleted 6 months ago might still exist on one replica if it was never read since then. Anti-entropy (Merkle tree) covers those cold keys by periodically comparing replicas.

---

**Q13: What is gossip protocol? How quickly does information propagate across the cluster?**

Gossip is a decentralized failure detection mechanism. Every second, each node picks 2-3 random neighbors and exchanges its membership view — the list of all nodes it knows about, with each node's last-seen heartbeat counter.

Each node increments its own heartbeat counter every second. When a node stops incrementing (crashed), other nodes notice the counter is stagnant. After a timeout (e.g., 10 seconds without increment), the node is marked as suspected dead.

Convergence speed: in each gossip round, the number of nodes that know about a new event roughly triples (each informed node tells 3 new nodes). Starting from 1 node: after k rounds, ~3^k nodes know. To reach 1,000 nodes: 3^k ≥ 1,000 → k = log_3(1000) = 6.3 → ~7 seconds.

Message complexity: O(N) per round (each of N nodes sends 2-3 small messages). Compare to all-pairs heartbeat: O(N^2). For N=1,000: gossip = 3,000 messages/sec, all-pairs = 1,000,000 messages/sec. Gossip scales; all-pairs does not.

---

**Q14: What is hinted handoff?**

When a replica is temporarily down and a write arrives, the coordinator cannot deliver the write to that replica. Instead of failing the write, the coordinator stores the write locally with a "hint": "this key-value belongs to node B, forward when B is back."

When node B recovers, the gossip protocol detects it is alive. The hint carrier (node A or C) sees B is up and forwards all hinted writes to B. B applies them and acknowledges. The hint carrier deletes its local copy.

Hinted handoff allows writes to succeed (with sloppy quorum) even when a designated replica is temporarily unavailable — improving availability during partial failures.

Limits: the hinted handoff buffer has a maximum size (e.g., 1 GB). If node B is down for too long and too many writes accumulate, the buffer fills and future writes to B's key range fail. That is why anti-entropy (Merkle tree) exists as a backstop for longer outages.

---

**Q15: What is anti-entropy? What is a Merkle tree and why is it used?**

Anti-entropy is a background process that periodically compares replicas and repairs divergence. It catches the cases that hinted handoff misses: node was down for a long time, hinted handoff buffer overflowed, or network partition lasted longer than the handoff retention.

Merkle tree is a tree where each leaf node contains `hash(key + value)` for a range of keys, and each internal node contains the hash of its children's hashes. The root hash represents the entire dataset.

To compare two replicas: exchange root hashes. If they match, replicas are identical — done. If they differ, recurse into left and right child hashes. The mismatch narrows down to the specific key range that differs. Transfer only the differing key-value pairs.

Bandwidth savings: without Merkle tree, comparing 1M keys requires transferring all 1M key-value pairs = 1 GB. With Merkle tree: 32 levels × 2 hash comparisons × 32 bytes = 2 KB of hashes, then transfer only the ~1,000 differing keys = 1 MB. 1000× bandwidth reduction.

---

**Q16: What is a tombstone? When is it actually deleted from disk?**

When a user calls `delete(key)`, the LSM tree does NOT remove the key from existing SSTables (they are immutable). Instead, it writes a new entry called a tombstone — a special marker meaning "this key was deleted."

On reads: if a tombstone is the most recent entry found for a key, return null (key is deleted). The tombstone "shadows" any older value for that key in older SSTables.

When is it removed: during compaction, after a configurable TTL called `gc_grace_seconds` (e.g., 10 days). The delay is necessary: if a replica was down during the deletion and comes back up, it needs to see the tombstone to know the key was deleted. If the tombstone was removed immediately and that replica came back, it would "resurrect" the deleted key.

Tombstone accumulation problem: if a workload deletes keys frequently (e.g., Discord messages), tombstones pile up faster than compaction can clean them. Reads must scan through millions of tombstones to find live data. Fix: reduce `gc_grace_seconds`, partition data by time bucket so old tombstones compact away sooner, or use TTL-based data expiry instead of explicit deletes.

---

**Q17: What is the difference between leveled compaction and size-tiered compaction?**

**Leveled compaction** (LevelDB, RocksDB): SSTables are organized into levels. L0 files can overlap. L1 and above: non-overlapping key ranges at each level. Each level is 10× the size of the previous. When a level is full, it merges with the next. Result: to find a key at level N, only 1 SSTable needs to be checked (non-overlapping). Better reads, higher write amplification (30×).

**Size-tiered compaction** (Cassandra default): SSTables are grouped by size. When N (e.g., 4) SSTables of similar size exist, they merge into one larger SSTable. No sorting across files — overlapping key ranges allowed. Result: fewer compaction cycles, lower write amplification (~10×). But reads must check more SSTables (overlapping ranges). Worse read performance.

**When to choose:**
- Mixed read/write workload: leveled (better reads)
- Write-heavy (IoT, time-series, log ingestion): size-tiered (lower write amplification, SSD longevity)
- Cassandra default is size-tiered; RocksDB default is leveled.

---

**Q18: What happens when a node crashes and restarts?**

**Step 1 — WAL replay:** On restart, the node reads its WAL from the last SSTable flush checkpoint. It replays all WAL entries after that checkpoint into a new MemTable. Any write that was in the WAL but not yet flushed to an SSTable is recovered. The node is now in the state it was in just before the crash.

**Step 2 — Gossip detection:** The gossip protocol detects the node is alive again within a few gossip rounds (~7 seconds for N=1,000 nodes). The node re-announces itself with its current heartbeat counter.

**Step 3 — Hinted handoff:** Nodes that stored hinted writes for this node forward them. The node applies any writes it missed while it was down.

**Step 4 — Anti-entropy:** In background, the node compares its Merkle tree with its replica peers. Any key ranges that diverged during the outage (due to hinted handoff buffer overflow or other gaps) are identified and the missing key-value pairs are transferred.

**Step 5 — Normal operation:** The node joins the consistent hashing ring and starts serving reads and writes for its key ranges.

---

**Q19: What is the difference between Redis and Cassandra? When would you use each?**

**Redis:** Single-threaded, in-memory primary store (with optional persistence). Sub-millisecond reads and writes. Supports rich data structures (sorted sets, hashes, lists, pub/sub). Not designed for data that exceeds RAM. Single-node or Redis Cluster (sharded, each shard is one master + replicas).

Use Redis for: session storage, rate limiting, leaderboards (ZSET), real-time queues, pub/sub, application-level cache.

**Cassandra:** Disk-persistent, distributed, LSM tree-backed. Designed for petabyte-scale data across many nodes. Eventual consistency by default (tunable to strong). Multi-datacenter replication built in. No single point of failure (any node can be coordinator).

Use Cassandra for: time-series data (IoT, metrics), write-heavy workloads, data that exceeds RAM, multi-region deployments, wide-column access patterns (row key + column families).

**The key distinction:** Redis is a data structure server living in RAM. Cassandra is a distributed persistent database living on disk, optimized for massive scale and write throughput. Do not use Redis when data exceeds available RAM. Do not use Cassandra when you need sub-millisecond latency or rich data structures.

---

**Q20: What is the difference between strong consistency and eventual consistency in a KV store?**

**Strong consistency:** After a write is acknowledged, any subsequent read (on any node) returns that write's value or a later one. No stale reads possible. Requires W + R > N (quorum). Cost: every write must wait for W replicas to acknowledge, every read must contact R replicas and wait for responses.

**Eventual consistency:** After a write is acknowledged, subsequent reads may return stale data temporarily. Eventually (after replication propagates), all replicas converge to the same value. Requires only W=1, R=1. Cost: stale reads possible for a window of time (typically milliseconds to seconds).

**When to choose strong consistency:** financial ledger, inventory count, distributed lock, any scenario where stale reads cause correctness bugs.

**When to choose eventual consistency:** session data, user profile cache, social media counters, any scenario where brief staleness is acceptable for the benefit of lower latency and higher availability.

Practical nuance: most systems need BOTH. Use strong consistency (W=2, R=2) for critical writes, eventual (W=1, R=1) for high-volume reads where staleness is acceptable. Make it configurable per operation (Dynamo-style consistency level).

---

**Q21: What is the hot key problem and how do you fix it?**

A hot key is a single key (e.g., "global_config", "homepage_banner") that is read or written far more frequently than average. In consistent hashing, every key maps to exactly one primary node. A hot key means one node absorbs a disproportionate fraction of all traffic.

At 500,000 reads/sec for a single key, that one node hits 100% CPU. Latency spikes for all keys on that node, not just the hot key.

**Fix 1 — Application-level caching:** Cache the hot key in each application server's local memory for 1-5 seconds. 100 app servers × 1 read every 5 seconds = 20 reads/sec to the KV node. Dramatic reduction with minimal staleness.

**Fix 2 — Key replication beyond N:** Replicate the hot key to all nodes (not just N=3). Route reads to any node round-robin. 500K reads/sec / 10 nodes = 50K reads/sec per node. Manageable. Cost: every write to this key must propagate to all 10 nodes.

**Fix 3 — Key splitting:** If the hot key has independent sub-fields, split it: "config:feature_flags", "config:rate_limits", "config:ab_tests" → each hashes to a different node.

Detection: monitor reads/sec per key. Alert at > 1,000 reads/sec for any single key. The hot key problem is usually sudden — a new feature causes massive reads to one key.

---

**Q22: You mentioned gossip for failure detection. What happens if gossip itself is slow and a node is wrongly marked as dead?**

A "false positive" dead declaration: node B is briefly unreachable (network blip, high CPU causing heartbeat delay). Gossip marks B as dead after 10 seconds without a heartbeat increment.

Consequences: B's key ranges are rerouted to other nodes. Hinted handoff accumulates writes for B. B's virtual nodes are removed from the ring table across the cluster (after gossip converges on the failure).

When B comes back (the blip passes): gossip detects B is alive again within ~7 seconds. B's vnodes are re-added to the ring. Hinted writes are forwarded to B. Anti-entropy reconciles any missed writes.

Short-term inconsistency: during the false-positive window, some reads might return stale data (B was bypassed, reads went to replica C which had an older version). Quorum reads (R=2) reduce this risk — they contact multiple replicas and return the latest version.

Fix to reduce false positives: use a two-stage failure detection. "Suspected" state (10s without heartbeat) vs "Dead" state (30s without heartbeat). Only reroute traffic when a node is "Dead." "Suspected" state triggers alerting but not rerouting. This reduces false routing changes at the cost of 20 extra seconds before traffic rerouting on true failures.

---

*Section 5 — L5 / Senior SWE. Highest-frequency pure depth probe at Google, Meta, and Amazon.*  
*Full chapter. Pairs with Ch31 (Database Internals) for the B-tree side of the storage engine comparison.*
