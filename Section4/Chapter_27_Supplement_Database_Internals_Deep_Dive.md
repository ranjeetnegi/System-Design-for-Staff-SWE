# Chapter 27 Supplement: Database Internals Deep Dive — B-Trees, WAL, MVCC, Connection Pooling, and NewSQL

---

# Introduction

Chapter 21 provides the Staff-level framework for database selection—access patterns, consistency trade-offs, evolution paths. But when the interview dives deeper, you need to understand *how* databases actually work. Video topics 253–258 assume familiarity with B-tree internals, write-ahead logging, multi-version concurrency control, connection pooling, and the NewSQL landscape. This supplement fills that gap.

These are not academic topics. At Staff level, you're asked to explain *why* a database behaves a certain way under load, *why* adding indexes slows writes, *why* VACUUM exists and when it fails, and *when* to reach for Spanner or CockroachDB instead of sharding PostgreSQL. This supplement gives you the internals needed to answer those questions with depth and precision.

**The Staff Engineer's Database Internals Principle**: You don't need to implement a B-tree from scratch. You do need to understand why B-trees exist, how they interact with disk I/O, and what happens when you add the fifth secondary index to a write-heavy table. The same applies to WAL, MVCC, connection pooling, and NewSQL—understand the mechanics, the trade-offs, and the operational implications.

**How to use this supplement**: Read it alongside Chapter 21. When the main chapter mentions B-trees, WAL, or MVCC, this supplement provides the "how" and "why." For interview prep, focus on the L5 vs L6 table, the operational scenarios (Part 8), the troubleshooting decision tree, and the Appendix Q&A. For deep dives, work through the ASCII diagrams and the capacity estimation sections. The goal is not to memorize formulas but to build intuition—so you can reason about database internals when the interviewer asks "why" or "what happens when."

---

## Quick Visual: Database Internals at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│     DATABASE INTERNALS: THE LAYERS THAT MATTER AT STAFF LEVEL              │
│                                                                             │
│   L5 Framing: "Databases store data and use indexes to find it faster"     │
│   L6 Framing: "Databases are layered systems where each layer solves        │
│                a specific problem—retrieval (B-trees), durability (WAL),   │
│                concurrency (MVCC), connection overhead (pooling), and      │
│                horizontal scale (NewSQL)—and each layer has trade-offs    │
│                that manifest in production"                                │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  RETRIEVAL (B-Tree):                                                 │   │
│   │  • Find 1 row in 1 billion without scanning all of them              │   │
│   │  • Wide trees → few disk reads                                       │   │
│   │  • Secondary indexes = write amplification                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  DURABILITY (WAL):                                                    │   │
│   │  • Sequential writes before random writes                            │   │
│   │  • Crash recovery by replaying the log                               │   │
│   │  • Replication = streaming the WAL                                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  CONCURRENCY (MVCC):                                                  │   │
│   │  • Readers never block writers; writers never block readers          │   │
│   │  • Multiple versions of each row                                    │   │
│   │  • VACUUM cleans up; if it lags → table bloat                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  CONNECTIONS (Pooling):                                               │   │
│   │  • Each connection = process/thread on DB server                     │   │
│   │  • 1000 connections → memory exhaustion, context switching          │   │
│   │  • Pool of 20 connections serves 500 request threads                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  SCALE (NewSQL):                                                      │   │
│   │  • SQL + horizontal scaling + ACID                                  │   │
│   │  • Consensus adds latency                                            │   │
│   │  • Use when single PostgreSQL cannot fit the data                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Database Internals Thinking

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Slow writes** | "Add more indexes" or "Upgrade the server" | "How many secondary indexes do we have? Each INSERT updates every index. 5 indexes = 6 disk writes per row. Write amplification is the bottleneck, not CPU." |
| **Table bloat** | "Run VACUUM more often" | "VACUUM is falling behind because we have long-running transactions holding snapshot visibility. Check pg_stat_activity for transactions older than our autovacuum_freeze_max_age. We may need to increase shared_buffers or run VACUUM during low traffic." |
| **Connection exhaustion** | "Increase max_connections" | "PostgreSQL forks a process per connection. 500 connections = 500 × ~10MB = 5GB just for connection overhead. The fix is connection pooling—PgBouncer or application-side pool—not higher max_connections." |
| **Choosing NewSQL** | "We need to scale, so CockroachDB" | "Does our data fit on one PostgreSQL? If yes, PostgreSQL. If no, have we considered sharding? NewSQL adds consensus latency (5–50ms) and operational complexity. Only worth it when sharding is too painful and we need strong consistency across shards." |
| **WAL growth** | "The WAL directory is full" | "WAL grows when checkpoint can't keep up. Checkpoints write dirty pages to data files. If I/O is saturated, checkpoint lags, WAL accumulates. Fix: increase checkpoint_completion_target, spread I/O across devices, or reduce write load." |

**Key Difference**: L6 engineers connect internal mechanisms to observable symptoms. They know which knob to turn—and which knob turning will cause a new problem elsewhere.

---

# Part 1: B-Tree Index — Why Databases Use It (Topic 253)

## The Problem: Finding One Row in a Billion

Consider a table with 1 billion rows. Without an index, finding a row by a specific key requires a **full table scan**: reading every row until you find the match. On disk, that's billions of random I/O operations. At ~100 random I/O per second per disk, a full scan could take weeks.

The fundamental question: **How do we find a row in O(log N) steps instead of O(N)?**

## The Evolution: Binary Search Tree → Balanced BST → B-Tree

### Binary Search Tree (BST)

A binary search tree organizes data so that for each node:
- Left child: smaller keys
- Right child: larger keys

Search: start at root, compare key, go left or right. O(log N) comparisons in a balanced tree.

**The problem for databases**: A binary tree has **branching factor 2**—each node has at most 2 children. For 1 billion rows, we need log₂(10⁹) ≈ **30 levels**. Thirty disk reads per lookup. Each disk read has ~5–10ms latency. That's 150–300ms per query—before we've even touched the actual data.

### Balanced BST (AVL, Red-Black)

Balanced trees maintain O(log N) height by constraining tree shape. They don't change the branching factor—still 2. Still ~30 disk reads for 1 billion rows.

### B-Tree: The Breakthrough

A **B-tree** (Bayer tree, or "broad tree") has a **high branching factor**. Each node can have **hundreds** of children, not 2.

```
B-Tree vs Binary Tree for 1 Billion Rows:

Binary tree (branching factor 2):
  log₂(10⁹) ≈ 30 levels → 30 disk reads

B-tree (branching factor 500):
  log₅₀₀(10⁹) ≈ 4 levels → 4 disk reads
```

**Why this matters**: Disk reads are expensive. SSDs: ~100µs random read. HDDs: ~10ms. The dominant cost is **number of disk I/Os**, not CPU. B-trees minimize disk I/O by being **WIDE** (many keys per node) instead of **TALL** (many levels).

## B-Tree Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    B-TREE STRUCTURE (Conceptual)                             │
│                                                                             │
│   Each NODE = one disk page (typically 4KB–16KB)                            │
│   Each node contains multiple keys and pointers                             │
│                                                                             │
│                    ┌─────────────────────────────┐                          │
│                    │         ROOT NODE           │                          │
│                    │  [K1] [K2] [K3] ... [Kn]   │  ← Hundreds of keys       │
│                    └───────┬───┬───┬───────┬─────┘                          │
│                            │   │   │       │                                 │
│              ┌─────────────┼───┼───┼───────┼─────────────┐                  │
│              ▼             ▼   ▼   ▼       ▼             ▼                  │
│        ┌──────────┐  ┌──────────┐  ...  ┌──────────┐                        │
│        │ INTERNAL │  │ INTERNAL │       │ INTERNAL │   ← Internal nodes      │
│        │  NODE 1  │  │  NODE 2  │       │  NODE N  │     (same structure)    │
│        └────┬─────┘  └────┬─────┘       └────┬─────┘                        │
│             │              │                  │                             │
│             ▼              ▼                  ▼                             │
│        ┌──────────┐  ┌──────────┐       ┌──────────┐                        │
│        │   LEAF   │  │   LEAF   │       │   LEAF   │   ← Leaf nodes         │
│        │   NODE   │◄─┤   NODE   │◄──────┤   NODE   │     contain actual data │
│        │  (data)  │  │  (data)  │  ...  │  (data)  │     or row pointers    │
│        └──────────┘  └──────────┘       └──────────┘     linked in order     │
│             │              │                  │                             │
│             └──────────────┼──────────────────┘                             │
│                            │                                                 │
│                    Leaf nodes form a LINKED LIST for range scans             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Properties

1. **Root node**: Single entry point. One disk read to start.

2. **Internal nodes**: Store only keys and pointers to child nodes. No actual row data. Many keys fit in one 4KB–16KB page.

3. **Leaf nodes**: Store either the actual row data (clustered index) or pointers to rows (non-clustered index). Leaf nodes are **linked** in key order—enabling efficient range scans.

4. **Branching factor**: With 4KB pages and 8-byte keys + 8-byte pointers, a node might hold ~200–500 entries. Branching factor of 500 → 4 levels for 1 billion rows.

## B+ Tree: The Variant Databases Actually Use

Most relational databases use **B+ trees**, not plain B-trees. The distinction:

| Feature | B-Tree | B+ Tree |
|---------|--------|---------|
| Data location | Internal nodes and leaves | **Leaf nodes only** |
| Leaf structure | Not linked | **Linked list** (prev/next pointers) |
| Range scans | Must traverse tree | **Scan leaf linked list** |

**Why B+ tree**: 
- **Range queries** ("SELECT * FROM orders WHERE date BETWEEN X AND Y") are common. With leaves linked, the database finds the first matching leaf, then scans forward—no tree traversal for each row.
- **All data in leaves** keeps internal nodes small—more keys per node, higher branching factor, fewer levels.

## Disk Page Alignment

A critical design choice: **each B-tree node = one disk page**.

- **4KB**: Traditional default (matches many filesystem block sizes)
- **8KB**: PostgreSQL default
- **16KB**: MySQL InnoDB option for large instances

**Why**: Disks read/write in page-sized units. Reading "one key" means reading the entire page containing that key. If a node fits in one page, one disk read retrieves the entire node—all keys and all child pointers.

## Operations: Search, Insert, Delete

### Search: O(log_B N)

1. Start at root. (1 disk read)
2. Binary search within the node for the key range containing our target.
3. Follow pointer to child. (1 disk read)
4. Repeat until leaf.
5. Search leaf for key. (1 disk read)
6. Return row or row pointer.

Total: **height of tree** disk reads. With branching factor 500 and 1 billion rows: 4 reads.

### Insert: Find + Insert + Possible Split

1. Search to find correct leaf. (Same as search)
2. Insert key into leaf.
3. **If leaf overflows** (too many keys for one page): **split** the leaf into two. Promote middle key to parent.
4. If parent overflows: split parent. May cascade to root.
5. If root splits: new root with 2 children. Tree grows taller.

**Cost**: Typically O(log_B N) reads for search + 1–2 writes. Worst case: split cascade = O(log_B N) writes.

### Delete: Find + Remove + Possible Merge

1. Search to find the leaf containing the key.
2. Remove the key.
3. **If leaf underflows** (too few keys): may **merge** with sibling or **redistribute** keys. Some databases (e.g., PostgreSQL) use lazy deletion—mark as deleted, merge later—to avoid expensive merge operations on hot paths.

## Clustered vs Non-Clustered Index

### Clustered Index

**Data is physically sorted** by the index key. The table's row order *is* the index order.

- **One per table**: Only one clustered index—the table can only be sorted one way.
- **No separate storage**: The index *is* the table structure.
- **Range scans are sequential**: Reading "next 100 rows" means reading the next 100 pages—excellent disk locality.

**Example**: `orders` table clustered on `order_id`. Rows are stored in order_id order on disk. Range query `WHERE order_id BETWEEN 1000 AND 2000` reads sequential pages.

### Non-Clustered Index (Secondary Index)

A **separate** B-tree structure. Leaf nodes contain **pointers** (row IDs, primary key values) to the actual rows.

- **Multiple per table**: You can have many secondary indexes.
- **Indirection**: Index lookup returns pointer; then fetch row (possibly another disk read).
- **Random I/O for row fetch**: If rows are scattered (different clustering), each secondary index lookup may trigger a random disk read.

**Example**: Index on `orders(customer_id)`. Leaf stores (customer_id → order_id). To get full row, database uses order_id to fetch from clustered table. Two lookups: index + table.

## ASCII Diagram: B-Tree with Branching and Leaf Linked List

```
                    ┌────────────────────────────────────────┐
                    │              ROOT (1 page)             │
                    │  Ptr │ 5 │ Ptr │ 15 │ Ptr │ 25 │ Ptr  │
                    └──────┬─────────┬─────────┬──────────────┘
                           │         │         │
        ┌──────────────────┘         │         └──────────────────┐
        ▼                            ▼                            ▼
┌───────────────┐           ┌───────────────┐           ┌───────────────┐
│  INTERNAL     │           │  INTERNAL     │           │  INTERNAL     │
│  [2][4]       │           │  [10][12][14] │           │  [20][22][24] │
└───────┬───────┘           └───────┬───────┘           └───────┬───────┘
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────┐     ┌───────────┐     ┌───────────┐     ┌───────────┐
│ LEAF 1    │◄───►│ LEAF 2    │◄───►│ LEAF 3    │◄───►│ LEAF 4    │ ...
│ 1→row     │     │ 5,6,7→row │     │ 10,11→row │     │ 15,16→row │
└───────────┘     └───────────┘     └───────────┘     └───────────┘
       ▲                                     ▲
       │         Range scan: follow ─────────┘
       │         next pointers, no tree traversal
       └── Point lookup: traverse root→internal→leaf
```

## Staff-Level Insight: Why B-Tree Dominates

**LSM (Log-Structured Merge) trees**—used by Cassandra, RocksDB, LevelDB—are write-optimized. They buffer writes in memory, flush to disk sequentially. Great for write-heavy workloads. But **range scans** in LSM trees can touch many segments (each segment is sorted, but segments must be merged). B-trees offer more **predictable** read latency for point lookups and range scans.

**When to think B-tree**: OLTP, point lookups, range queries, strong consistency, mixed read/write. Most relational databases.
**When to think LSM**: Append-heavy, write throughput priority, eventually consistent, key-value or wide-column. Cassandra, ScyllaDB, storage engines like RocksDB.

### B-Tree in Practice: PostgreSQL vs MySQL

**PostgreSQL**: Default index type is B-tree. Tables are heaps (unordered); primary key creates a unique B-tree. Secondary indexes store (index_key → ctid), where ctid is the physical row location. UPDATEs create new row versions; indexes point to new ctid. No clustered index by default—`CLUSTER` command can physically reorder by an index, but it's one-time.

**MySQL InnoDB**: Primary key is clustered. Secondary indexes store (index_key → primary_key). Row fetch by secondary index requires **index lookup + primary key lookup**—two B-tree traversals. This is the "index intersection" cost: non-clustered indexes are always indirect.

### Real-World Numbers: Branching Factor and Height

| Rows | Binary Tree (B=2) | B-Tree (B=200) | B-Tree (B=500) |
|------|------------------|----------------|----------------|
| 1,000 | 10 levels | 2 levels | 2 levels |
| 1,000,000 | 20 levels | 3 levels | 3 levels |
| 1,000,000,000 | 30 levels | 4 levels | 4 levels |
| 1,000,000,000,000 | 40 levels | 5 levels | 4 levels |

At 4KB per page and 100µs per random read (SSD): 4 reads = 400µs for a point lookup on 1B rows. The B-tree is doing its job.

### Index Bloat and Maintenance

B-trees can become inefficient over time: dead space from deletes, unbalanced splits, page fragmentation. **REINDEX** (PostgreSQL) or **OPTIMIZE TABLE** (MySQL) rebuilds the index. Online reindexing (PostgreSQL 12+) allows concurrent access during rebuild—critical for production. Schedule during low-traffic windows; large indexes can take hours.

### B-Tree vs Hash Index

**Hash index**: Maps key → value via hash function. O(1) average lookup. **But**: No range scans (hash destroys order), no sorted iteration, sensitive to collisions. Good for exact-match-only: `WHERE id = 123`. PostgreSQL has hash indexes; InnoDB has adaptive hash index for hot rows. For most workloads, B-tree wins because range queries (`BETWEEN`, `>`, `<`, `ORDER BY`) are common. Hash is a niche optimization for pure key-value lookups.

### Why Not Just Use Memory (Skip Disk)?

Some databases (Redis, Memcached) keep everything in memory. Fast, but data doesn't survive restarts without persistence (RDB, AOF). For durable storage, data must reach disk. B-trees are designed for disk: nodes = pages, minimize I/O. In-memory B-trees exist (e.g., for caching) but the main value of B-tree is its disk-oriented design. When data fits in memory, the database still uses B-trees on disk for durability; the buffer pool keeps hot pages in memory.

### B-Tree Split Mechanics and Hot Spots

When a leaf overflows, it **splits**: create new leaf, move half the keys, promote middle key to parent. Root split grows tree height. **Fill factor** < 100% (e.g., 90%) leaves space for inserts—reduces splits. **Insert order matters**: Sequential inserts (auto-increment) hit the rightmost leaf—constant contention. Random inserts (UUID v4) spread across leaves. For append-heavy tables, consider hash-based or random keys to avoid hot spots.

### Capacity Estimation: B-Tree Size

**Index size ≈ (rows) × (key size + pointer size)**. Example: 100M rows, index (user_id BIGINT, created_at TIMESTAMP): 16 + 8 ≈ 24 bytes/entry. 100M × 24 = 2.4 GB. Add overhead → ~3 GB. For 1B rows, 5 indexes: ~150 GB index storage. Indexes can dominate; plan accordingly.

### Worked Example: Point Lookup Latency

Query: `SELECT * FROM users WHERE id = 12345` on 1B rows. Path: root → internal → internal → leaf → heap = 5 I/Os. SSD 100µs/read → 500µs. With buffer cache (hot): 1–2 reads → 100–200µs. B-tree delivers logarithmic lookup; primary key is the fastest path.

---

# Part 2: Secondary Indexes — Cost and Use (Topic 254)

## Primary Index vs Secondary Index

### Primary Index

- **Defines physical order** of the table (for clustered) or is the unique identifier (for non-clustered).
- **One per table.**
- Often automatically created for primary key.
- In PostgreSQL: Tables are heaps (no clustered index by default). Primary key creates a unique B-tree index; rows are not reordered.
- In MySQL InnoDB: Primary key is the clustered index. Table is stored in primary key order.

### Secondary Index

- **Additional** B-tree that maps a column (or columns) → row identifiers.
- **Multiple per table.**
- Purpose: Speed up queries that filter or sort by the indexed column(s).

## The Hidden Cost: Write Amplification

**Every INSERT, UPDATE, or DELETE must update every index on the table.**

```
Example: orders table with 5 secondary indexes

INSERT INTO orders (...) VALUES (...);

Actual disk writes:
  1. Insert row into table (or clustered index)
  2. Update index on order_id (primary)
  3. Update index on customer_id
  4. Update index on created_at
  5. Update index on (status, created_at)
  6. Update index on (customer_id, status)

Total: 6 writes for 1 logical row insert
```

**Write amplification** = ratio of physical writes to logical writes. Here: 6x.

- More indexes → more writes per row change
- Slower INSERTs, UPDATEs, DELETEs
- More I/O pressure
- More WAL generated (each index update is logged)

## When Indexes Are Worth It

An index pays off when:

1. **Queries filter by the indexed column**: `WHERE customer_id = 123` with index on customer_id → O(log N) vs O(N) full scan.
2. **Queries sort by the indexed column**: `ORDER BY created_at` with index on created_at → read in order, no sort.
3. **Selectivity is high**: Index on a column with few distinct values (e.g., boolean) may not help—optimizer might prefer full scan.

**Rule of thumb**: Index if the query pattern justifies it. Each index is a trade-off: faster reads, slower writes, more storage.

## Covering Indexes: Index-Only Scans

A **covering index** includes all columns needed for the query. The database can satisfy the query **without reading the table**.

```
Query: SELECT customer_id, status FROM orders WHERE customer_id = 123;

Without covering index:
  - Use index on customer_id to find matching rows
  - For each match, fetch full row from table to get status
  - 1 index read + N table reads (N = number of matching rows)

With covering index on (customer_id, status):
  - Index contains both customer_id and status
  - Read only the index—no table access
  - 1 index read, or sequential leaf reads for range
```

**Index-only scan**: The fastest possible query path when the index covers all needed columns.

**Design implication**: When adding an index for a hot query, consider including frequently selected columns: `CREATE INDEX idx ON orders(customer_id) INCLUDE (status, total)` (PostgreSQL syntax). The index is larger, but the query never touches the table.

## Composite Indexes: Column Order Matters

A **composite index** on (col_A, col_B) stores keys in lexicographic order: first by col_A, then by col_B within each col_A value.

```
Index on (customer_id, created_at):

Stored order: (cust1, t1), (cust1, t2), (cust1, t3), (cust2, t1), (cust2, t2), ...

Useful for:
  WHERE customer_id = X                          ✓ Uses index (leftmost prefix)
  WHERE customer_id = X ORDER BY created_at      ✓ Uses index, no sort
  WHERE customer_id = X AND created_at > Y       ✓ Uses index
  WHERE created_at > Y                            ✗ Cannot use index (col_B only)
  WHERE customer_id = X AND status = 'pending'    △ Uses index for customer_id,
                                                    then filters status in memory
```

**Leftmost prefix rule**: A composite index can be used for queries that filter on a leftmost prefix of columns. (A, B, C) helps (A), (A, B), and (A, B, C). It does *not* help (B), (C), or (B, C).

**Staff insight**: Design composite indexes for the most selective column first, then add columns for filtering/sorting. Measure with EXPLAIN ANALYZE—don't guess.

## When NOT to Index

1. **Low-cardinality columns**: Boolean, status with 3 values. Index may return many rows; optimizer may choose full scan.
2. **Rarely queried columns**: Index costs writes on every insert/update. If the column is almost never in WHERE/JOIN/ORDER BY, skip it.
3. **Very small tables**: Full scan is cheap. Index overhead isn't justified.
4. **Write-heavy tables with many indexes**: Each index multiplies write cost. For append-heavy logs, minimal indexing.

## The "Index Everything" Antipattern

```
"Let's add indexes on every column—queries will be fast!"

Reality:
  - 15 columns → 15 indexes
  - Each INSERT = 1 table write + 15 index writes = 16 writes
  - Write throughput collapses
  - WAL volume explodes
  - Checkpoint and replication lag
  - Disk fills faster
```

**Correct approach**: Index based on **observed** and **anticipated** query patterns. Use query analysis (pg_stat_statements, slow query log) to identify missing indexes. Remove indexes that are never used (query `pg_stat_user_indexes` in PostgreSQL).

### Partial Indexes: Index a Subset of Rows

**Partial index** (PostgreSQL): Index only rows matching a predicate. Smaller index, faster writes for the indexed subset.

```
CREATE INDEX idx_pending_orders ON orders(customer_id) WHERE status = 'pending';
```

Useful when queries filter by a condition (e.g., status = 'pending'). The index only contains pending orders. Inserts of completed orders don't touch this index. Downsides: Query must match the predicate for the index to be used; optimizer must know to use it.

### Expression Indexes and Functional Indexes

Index on a **computed expression** rather than raw column:

```
CREATE INDEX idx_lower_email ON users(LOWER(email));
-- Enables: WHERE LOWER(email) = 'alice@example.com'
```

Without this, `WHERE LOWER(email) = ...` cannot use an index on `email`—the function breaks index usability. Expression indexes store the computed value. Useful for case-insensitive search, truncated dates, JSON path extraction. Trade-off: Index maintenance computes the expression on every insert/update.

### Index Selectivity: When the Optimizer Prefers Full Scan

**Selectivity** = fraction of rows that match a predicate. Low selectivity (e.g., `WHERE status = 'active'` when 90% of rows are active) may lead the optimizer to choose a full table scan—reading the index plus fetching many rows can be slower than sequential scan. High selectivity (e.g., `WHERE user_id = 123` with millions of users) favors index use. Use `EXPLAIN ANALYZE` to verify; don't assume indexes are always used.

### Monitoring Index Usage

PostgreSQL: `pg_stat_user_indexes` — `idx_scan` (how often index was used), `idx_tup_read`, `idx_tup_fetch`. Compare to `pg_stat_user_tables`.`seq_scan` to see scan vs index balance. Unused indexes (`idx_scan` = 0) are candidates for removal—they only add write cost.

### Query Planner and Index Selection

The planner estimates cost of each access path. **Index scan cost** = (pages_read × seq_page_cost) + (rows × cpu_tuple_cost). **Seq scan cost** = (table_pages × seq_page_cost) + (rows × cpu_tuple_cost). For small tables, seq scan often wins—reading the whole table is cheaper than index + random fetches. For large tables with selective predicates, index wins. The planner uses statistics (`pg_statistic`, `ANALYZE`) to estimate selectivity. Stale statistics cause bad plans: run `ANALYZE` regularly. **EXPLAIN (ANALYZE, BUFFERS)** shows actual rows, actual time, and buffer hits—essential for tuning.

### Index Merge and Bitmap Scans

When a query has multiple predicates (e.g., `WHERE a = 1 AND b = 2`), the planner may: (1) Use one composite index (a, b) if it exists. (2) **Index merge**: Use index on (a) and index on (b), intersect row IDs. (3) **Bitmap index scan**: Scan index on (a), build bitmap of matching rows; scan index on (b), build bitmap; AND the bitmaps; fetch rows. Bitmap scans avoid repeated random I/O—good when many rows match. For few rows, index scan with heap fetch is simpler. The planner chooses based on estimated row counts.

## Practical Example: Orders Table

```
Table: orders (1B rows, 100K inserts/sec)

Index 1: PRIMARY KEY (order_id)           — Required
Index 2: (customer_id)                     — Query: orders by customer
Index 3: (created_at)                      — Query: recent orders, analytics
Index 4: (customer_id, status)             — Query: customer's pending orders
Index 5: (warehouse_id, status)            — Query: warehouse fulfillment

Each insert: 5 index updates. 100K inserts/sec × 5 = 500K index writes/sec.
At 8KB pages, random write ~1ms: 500K writes would need 500 seconds of I/O per second.
Reality: Batched, sequential where possible, but still heavy.

Consider: Do we need all 5? Index 4 covers queries that Index 2 + filter could handle,
but (customer_id, status) is more specific. Maybe drop Index 2 if Index 4 suffices?
```

---

# Part 3: Write-Ahead Log (WAL) — What and Why (Topic 255)

## The Problem: Crash During Write

Database writes involve:
1. Modifying data pages in memory (buffer pool)
2. Eventually flushing those pages to disk (data files)

If the process crashes **after** modifying memory but **before** flushing to disk:
- In-memory changes are lost
- Data files may be **inconsistent** (some pages updated, others not)
- **Partial writes**: Half-updated row, broken index, corrupted B-tree

Recovery requires knowing **what** was intended. Without a log, we cannot reconstruct.

## The WAL Solution

**Write-Ahead Logging**: Before modifying any data file, write the intended change to a **sequential, append-only log**. The log is the source of truth for "what happened."

**Rule**: No data page is written to disk until the log records for that page have been written to disk.

```
Write flow:

1. Transaction modifies row in memory (buffer pool)
2. Write log record: "Page X, offset Y: change from A to B" → append to WAL
3. Flush WAL to disk (fsync)
4. Mark page as dirty in buffer pool
5. Eventually: checkpoint flushes dirty pages to data files

Order is critical: WAL MUST be on disk before data page.
```

## Why Sequential Writes

| Storage Type | Sequential Write | Random Write |
|-------------|------------------|--------------|
| HDD | ~100–200 MB/s | ~1–2 MB/s |
| SSD | ~3 GB/s | ~500 MB/s |
| NVMe | ~5–7 GB/s | ~1–2 GB/s |

**Sequential writes are 10–100× faster than random writes.** WAL is append-only—always sequential. Data file updates are random (different pages, different locations). By logging first, we batch many logical changes into one sequential stream. Data file updates can be deferred and batched (checkpoint).

## Crash Recovery

On restart after a crash:

1. **Find last checkpoint** in WAL (periodically recorded).
2. **Load** data file state as of that checkpoint (or replay from a previous checkpoint if needed).
3. **Replay WAL** from checkpoint forward: reapply all logged changes.
4. **Redo**: Replay committed transactions—bring data files to committed state.
5. **Undo**: Roll back uncommitted transactions—restore consistency.

Result: Database returns to a **consistent** state as of the last committed transaction. No corrupted pages, no torn writes.

## Checkpoints

**Checkpoint** = flush all dirty buffer pool pages to data files and record checkpoint position in WAL.

- **Purpose**: Establish a recovery point. WAL before checkpoint is no longer needed for recovery (changes are in data files).
- **WAL truncation**: Old WAL segments can be deleted or archived.
- **Prevents unbounded WAL growth**: Without checkpoints, WAL would grow forever.

**Checkpoint triggers**:
- **Time-based**: Every N seconds (checkpoint_timeout in PostgreSQL)
- **WAL volume-based**: When WAL size exceeds threshold
- **Manual**: CHECKPOINT command

**Trade-off**: Frequent checkpoints = less WAL, faster recovery, but more random I/O to data files. Infrequent checkpoints = less data file I/O, but more WAL, slower recovery.

## WAL in PostgreSQL

- **Directory**: `pg_wal` (formerly `pg_xlog`)
- **Segments**: Typically 16MB each. Named by segment number.
- **Archiving**: `archive_mode` and `archive_command` copy finished segments to backup storage—enables point-in-time recovery (PITR) and replication setup.

**Replication**: Streaming replication sends WAL from primary to replicas. Replicas replay WAL to stay in sync. WAL is the **replication stream**.

## WAL in MySQL (InnoDB)

- **Redo log**: InnoDB's WAL. Records changes to data pages. Circular buffer (ib_logfile0, ib_logfile1).
- **Binary log (binlog)**: Server-level log of SQL statements or row changes. Used for replication and PITR. Separate from redo log.

**Two logs**: Redo for crash recovery; binlog for replication and backup.

## Full-Page Writes

**Problem**: Partial page write. If a 8KB page is half-written when crash occurs, the page is corrupted. WAL typically logs *changes* (deltas), not full pages. Replaying a delta onto a corrupted base yields a corrupted result.

**Solution (PostgreSQL)**: **Full-page writes**. After a checkpoint, the *first* modification of each page writes the **entire page** to WAL, not just the delta. Recovery can reconstruct the page from that full image, then apply subsequent deltas.

Cost: Larger WAL for the first change to each page after checkpoint. Usually acceptable.

### WAL and Replication: Physical vs Logical

**Physical replication** (PostgreSQL, MySQL): Replica receives raw WAL/redo bytes and applies them to its data files. Byte-for-byte consistency with primary. Fast, but replica must run same major version and extension set. **Logical replication** (PostgreSQL logical decoding, MySQL binlog row format): Replica receives logical changes (insert row X, update row Y). Can filter, transform, replicate to different schemas or databases. Used for cross-version upgrades, selective replication, change data capture (CDC) to Kafka or data warehouses. Trade-off: Logical has more overhead and latency than physical.

### WAL Tuning Parameters (PostgreSQL)

- **wal_buffers**: Memory for WAL before flushing. Default 64KB–several MB. Larger can reduce write syscalls.
- **checkpoint_completion_target**: Spread checkpoint I/O over this fraction of checkpoint_timeout. 0.9 = checkpoint finishes by 90% of interval, smoothing I/O.
- **max_wal_size**: WAL can grow to this before forcing checkpoint. Larger = fewer checkpoints, more recovery time after crash.
- **min_wal_size**: Minimum WAL to retain for reuse. Avoids creating/destroying segment files frequently.
- **full_page_writes**: On by default. Disable only for temp tables (not needed) or with battery-backed write cache (risky).

### Key Configuration Parameters: Quick Reference

| Parameter | Purpose | Typical Values |
|-----------|---------|----------------|
| shared_buffers | Buffer pool size | 25% of RAM, max ~32GB |
| work_mem | Memory for sorts, hashes per operation | 4–64 MB |
| maintenance_work_mem | For VACUUM, CREATE INDEX | 256 MB – 2 GB |
| max_connections | Connection limit | 100–300 |
| checkpoint_completion_target | Spread checkpoint I/O | 0.9 |
| wal_buffers | WAL buffer | 64 KB – 16 MB |
| autovacuum_vacuum_scale_factor | Trigger vacuum when n_dead_tup exceeds this fraction of n_live_tup | 0.2 (20%) |
| autovacuum_vacuum_cost_delay | Delay between autovacuum work | 2ms (lower = more aggressive) |

### When WAL Becomes a Bottleneck

**Symptoms**: High WAL volume, `pg_wal` directory growing, replication lag, checkpoint taking too long. **Causes**: (1) Many small transactions (each commit flushes WAL); batch when possible. (2) High write throughput; consider read replicas to spread read load. (3) Full-page writes on systems with many small random updates; each page's first touch writes 8KB to WAL. (4) Slow disk; WAL is sequential but still limited by device. **Mitigation**: Faster storage for WAL (separate SSD for pg_wal), tune checkpoint parameters, reduce full-page write frequency (not recommended unless you understand the risk).

### WAL in Distributed and Replicated Systems

In a primary-replica setup, the primary's WAL is the **replication stream**. Replicas connect and request WAL from the last applied position. **Synchronous replication** (PostgreSQL `synchronous_commit = on`): Primary waits for replica to confirm WAL receipt before committing. Guarantees no data loss if replica has the commit; adds latency (typically 1–5ms for same-datacenter replica). **Asynchronous replication**: Primary commits immediately; replica applies WAL in background. Lower latency, but replica can lag—failover may lose recent commits. **Quorum commit**: Wait for N of M replicas. Balances latency and durability. WAL is the foundation for all of these.

### Point-in-Time Recovery (PITR)

With WAL archiving, you can restore to any point in time. Process: (1) Restore base backup (full copy taken at checkpoint). (2) Apply archived WAL segments from backup time to target time. (3) Apply any in-progress WAL. Result: Database as it was at the target timestamp. Essential for "we need to undo that bad migration" or "restore before the ransomware encrypted the data." Requires continuous WAL archiving and tested restore procedures.

### Crash Recovery Mechanics: Redo and Undo

**Redo phase**: Replay all WAL records. Reapply changes that were in WAL but not yet in data files. Brings data files forward to the point of crash. **Undo phase**: Roll back uncommitted transactions. Transactions that had not committed at crash time must be reversed—use undo information (in WAL or undo log) to revert their changes. Order: Redo first (restore all changes), then undo (roll back uncommitted). **Consistency**: After recovery, database is in a consistent state—no partial transactions, no torn pages. Recovery time depends on WAL volume since last checkpoint; can be minutes for large databases after unexpected shutdown.

## ASCII Diagram: Write Flow and Checkpoint

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WAL WRITE FLOW                                            │
│                                                                             │
│   Transaction commits:                                                       │
│                                                                             │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                 │
│   │  Buffer Pool │     │     WAL      │     │  Data Files │                 │
│   │  (memory)    │     │  (disk, seq) │     │  (disk)     │                 │
│   └──────┬───────┘     └──────┬───────┘     └──────┬───────┘                 │
│          │                    │                    │                         │
│          │ 1. Modify          │                    │                         │
│          │    pages           │                    │                         │
│          │                    │                    │                         │
│          │ 2. Write log ─────►│  append            │                         │
│          │    records         │                    │                         │
│          │                    │ 3. fsync WAL       │                         │
│          │                    │                    │                         │
│          │ 4. Return          │                    │                         │
│          │    success         │                    │                         │
│          │                    │                    │                         │
│          │                    │     CHECKPOINT     │                         │
│          │ 5. Flush dirty ────┼───────────────────►│  write pages             │
│          │    pages           │                    │                         │
│          │                    │ 6. Advance        │                         │
│          │                    │    checkpoint     │                         │
│          │                    │ 7. Truncate       │                         │
│          │                    │    old WAL        │                         │
│                                                                             │
│   CRASH? Replay WAL from checkpoint → consistent state                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 4: MVCC — Multi-Version Concurrency Control (Topic 256)

## The Problem: Reader-Writer Contention

Without MVCC:
- **Reader locks row** → writer must wait. Read-heavy workload blocks writes.
- **Writer locks row** → readers wait. Write blocks reads.
- **Lock contention** limits throughput.

Goal: **Readers never block writers. Writers never block readers.** (They can proceed concurrently on different versions.)

## The MVCC Idea

**Each write creates a new version** of the row. Old versions remain until no longer needed. A **reader** sees a **snapshot**—a consistent view of the database at a point in time. It reads the version that was visible when its transaction started. Writers create new versions; they don't overwrite in place (from readers' perspective) until the reader's snapshot is done.

- **No read locks**: Readers don't take locks. They read from their snapshot.
- **Writer-writer conflict**: Two transactions writing the same row still conflict. One wins; the other may get a serialization error or retry.

## How It Works: Snapshots and Visibility

Each transaction gets a **snapshot** at start: "I see the database as of now." The snapshot includes:
- **Snapshot visibility**: Rows committed before my snapshot start are visible. Rows committed after are invisible. Rows from in-progress transactions: visible only if committed by the transaction that created them, and only if that commit was before my snapshot.

**Implementation**: Each row has metadata: which transaction created it (xmin), which transaction deleted it (xmax, or NULL if not deleted). Visibility rules compare these to the transaction ID of the viewer and the set of active/in-progress transactions.

## PostgreSQL Implementation

- **xmin**: Transaction ID that inserted the row. Row is visible to transactions with snapshot that includes this commit.
- **xmax**: Transaction ID that deleted (or updated—update = delete + insert) the row. NULL if not deleted.
- **Visibility**: A row is visible if: xmin is committed and before snapshot, and (xmax is NULL or xmax is not yet committed or was committed after snapshot).

**Update** = DELETE (set xmax) + INSERT (new row with new xmin). Old row remains; new row exists. Different transactions see different versions based on their snapshot.

## VACUUM: Cleaning Up Old Versions

Old row versions accumulate. A row updated 1000 times has 1000 versions (or 999 dead, 1 visible). They consume space and slow scans.

**VACUUM**:
- Marks dead tuples (no longer visible to any active transaction) as reusable
- Reclaims space for reuse by the same table (doesn't return to OS by default; VACUUM FULL does, but takes exclusive lock)
- Updates visibility statistics for the query planner

**Autovacuum**: PostgreSQL runs VACUUM automatically based on table activity. When it falls behind:
- **Table bloat**: Table grows, scans slow down
- **Transaction ID wraparound risk**: PostgreSQL uses 32-bit transaction IDs. If old rows with very old xmin exist, wraparound can cause data loss. VACUUM "freezes" old rows to prevent this.

**Causes of VACUUM lag**:
- Long-running transactions: Hold snapshot; their snapshot keeps old rows visible
- High write rate: Many dead tuples; VACUUM can't keep up
- Insufficient autovacuum workers or I/O

**Check**: `pg_stat_user_tables` — `n_dead_tup`, `n_live_tup`, `last_vacuum`, `last_autovacuum`. Long-running transactions: `pg_stat_activity` — look at `state`, `xact_start`.

## Snapshot Isolation

**Snapshot isolation**: Each transaction sees a consistent snapshot. No dirty reads, no non-repeatable reads. But **write skew** and **phantom reads** can occur—different from serializability.

**Conflict**: Two transactions read the same row, both update it. One commits first. The second: depending on DB and settings, may get serialization failure (e.g., PostgreSQL's SERIALIZABLE) or may overwrite (e.g., last-writer-wins in some systems).

PostgreSQL default is READ COMMITTED—each statement sees latest committed state. REPEATABLE READ gives snapshot isolation. SERIALIZABLE adds conflict detection for full serializability.

## MVCC in MySQL (InnoDB)

- **Undo log**: Stores old row versions. Rollback and consistent reads use it.
- **Purge thread**: Removes old versions from undo when no transaction needs them.
- **Read view**: Similar to snapshot—determines which versions are visible.

### Isolation Levels and MVCC

**Read Uncommitted**: See uncommitted changes. Rarely used; no snapshot. **Read Committed** (PostgreSQL default): Each statement sees latest committed state. No dirty reads; non-repeatable reads possible. **Repeatable Read** (MySQL default): Transaction sees snapshot at first read. No dirty reads, no non-repeatable reads; phantoms possible. **Serializable**: Strictest; transactions behave as if serial. PostgreSQL implements with SSI (Serializable Snapshot Isolation)—detects write conflicts and aborts. MVCC enables Read Committed and Repeatable Read without locking; Serializable adds conflict detection.

### Locking vs MVCC

**Locking** (two-phase locking, 2PL): Readers and writers take locks. Readers block writers; writers block readers. Throughput limited by lock contention. **MVCC**: No read locks. Writers create new versions; readers see old versions. Higher concurrency for read-heavy workloads. Writers still need row-level or page-level locks for concurrent writes to same row—only one writer wins. MVCC + optimistic concurrency (detect conflict at commit) is common in modern databases. PostgreSQL uses a hybrid: SI for reads, locks for writes.

### Long-Running Transactions: The VACUUM Killer

A transaction that runs for hours holds a snapshot. That snapshot determines visibility: rows deleted by transactions that committed *after* the snapshot started must remain visible. VACUUM cannot remove such rows—they're not "dead" yet. One long transaction blocks VACUUM for the entire database (it affects visibility of all tables). **Operational rule**: Keep transactions short. For batch jobs, commit in chunks. For reporting, use read replicas with their own snapshots. Monitor `max(oldest xact start)` in pg_stat_activity.

## MVCC Trade-offs

| Benefit | Cost |
|---------|------|
| Readers don't block writers | More storage (multiple versions) |
| Writers don't block readers | VACUUM / purge overhead |
| High read throughput | Potential table bloat if cleanup lags |
| Snapshot consistency | Write amplification (update = delete + insert) |
| | Complexity in visibility logic |

## ASCII Diagram: Row Versions and Visibility

```
Row with key K, updated 3 times:

  Tx 100: INSERT  →  Version 1 (xmin=100, xmax=NULL)  "Alice, $100"
  Tx 200: UPDATE  →  Version 1 (xmax=200), Version 2 (xmin=200, xmax=NULL) "Alice, $150"
  Tx 300: UPDATE  →  Version 2 (xmax=300), Version 3 (xmin=300, xmax=NULL) "Alice, $200"

  Tx 250 starts, snapshot = {committed up to 250}
    → Sees Version 2 (xmin=200 committed before 250, xmax=300 not committed or after)
    → Reads "Alice, $150"

  Tx 350 starts, snapshot = {committed up to 350}
    → Sees Version 3
    → Reads "Alice, $200"

  VACUUM: Version 1, 2 are dead (no active snapshot needs them)
    → Mark space reusable
    → Table may still have "holes" until new inserts reuse
```

---

# Part 5: Database Connection Pooling in Practice (Topic 257)

## The Problem: Each Connection Is Expensive

In PostgreSQL, **each connection is a separate OS process**. Not a thread—a full process.

- **Memory per connection**: ~5–10 MB (session state, buffers, etc.)
- **1000 connections**: 5–10 GB just for connections
- **Context switching**: Kernel switches between 1000 processes
- **Connection setup**: TCP handshake, SSL, authentication—takes time

**PostgreSQL recommendation**: `max_connections` = 100–300. Beyond that, consider connection pooling.

## Connection Pool: Share a Few, Serve Many

**Idea**: Application has 500 request-handling threads, but only **20** actual DB connections. A thread that needs the DB **borrows** a connection from the pool, runs its query, returns the connection.

```
Without pooling:
  500 app threads → 500 DB connections → 500 processes on DB server

With pooling (pool size 20):
  500 app threads → share 20 connections → 20 processes on DB server
  When a thread needs DB: get connection from pool → query → return to pool
  Other threads wait for available connection (or get new work)
```

## Sizing the Pool: Little's Law

**Little's Law**: L = λ × W
- L = average number of requests in system (concurrent queries)
- λ = arrival rate (queries per second)
- W = average time in system (query duration)

**Concurrent queries** = QPS × average query duration

Example:
- QPS = 1000
- Average query = 5 ms = 0.005 s
- Concurrent queries = 1000 × 0.005 = **5**

A pool of 10–20 is plenty. Oversizing (e.g., 200) wastes DB resources and can hurt performance (too many concurrent queries → contention, lock waits).

**Rule of thumb**: Pool size ≈ (QPS × p99 query time) + buffer. Don't set pool size = number of app threads.

## PgBouncer: External Connection Pooler

**PgBouncer** sits between application and PostgreSQL. Application connects to PgBouncer; PgBouncer maintains a small pool of real connections to PostgreSQL.

**Pooling modes**:
- **Session pooling**: Connection returned to pool when client disconnects. Preserves session state (prepared statements, temp tables, session variables). Simpler for app, but holds connection for entire session.
- **Transaction pooling**: Connection returned after each transaction. Highest efficiency—short transactions release connections quickly. **Limitation**: No session-level state (no prepared statements across transactions, no temp tables, no SET LOCAL).

**When to use PgBouncer**:
- Multiple app servers, each with its own pool
- Total connections would exceed PostgreSQL max_connections
- Need centralized pooling and connection limits

## HikariCP (Java) and In-App Pooling

**HikariCP**: In-application pool. Connections created by the app process and pooled there. No extra hop (unlike PgBouncer).

**Pros**: No extra network hop, supports all PostgreSQL features (prepared statements, session vars).  
**Cons**: Each app instance has its own pool. 10 app servers × 20 connections = 200 connections to DB.

**Configuration**: `maximumPoolSize`, `minimumIdle`, `connectionTimeout`, `idleTimeout`. HikariCP defaults are often good.

## Multiple App Servers: The Connection Multiplication Problem

```
10 app servers
Each runs 20 DB connections in pool
Total: 200 connections to PostgreSQL

PostgreSQL max_connections = 100
→ 100 connections refused, or must raise limit (bad for DB)
```

**Solution**: Centralized pooler (PgBouncer, pgpool-II, or cloud-managed pooler like RDS Proxy).

```
App Server 1 ─┐
App Server 2 ─┤
App Server 3 ─┼─► PgBouncer ─► PostgreSQL (50 connections)
...           │   (pool: 50)
App Server 10 ┘
```

## Connection Pool Monitoring

Metrics to track:
- **Active connections**: In use
- **Idle connections**: In pool, waiting
- **Wait time**: Time to acquire connection (should be low; high = pool too small or queries too slow)
- **Timeouts**: Failed to get connection within timeout
- **Pool size vs utilization**: If utilization is low, pool may be oversized

**Alert**: Connection wait time > 100ms or timeout rate > 0.1%.

### Prepared Statements and Connection Pooling

**Prepared statements** are parsed and planned once, executed many times. They live in the connection's session state. With **transaction pooling** (PgBouncer), the connection is returned after each transaction—prepared statements are lost. Options: (1) Use **session pooling** so connections persist; (2) Use **statement caching** in the application (re-parse per transaction but cache plans); (3) Use `DEALLOCATE ALL` or avoid prepared statements when using transaction pooling. This is a common source of "prepared statement does not exist" errors with PgBouncer in transaction mode.

### Connection Pool in Kubernetes / Serverless

With many pods or serverless instances, each may open its own pool. 100 pods × 10 connections = 1000 connections. Use a **sidecar pooler** (e.g., PgBouncer per node) or a **centralized pooler** (e.g., RDS Proxy, PgBouncer as a service) to aggregate. Serverless is tricky: cold starts may spike connections; connections may idle and get closed by the database. Connection poolers that support **connection reuse** across invocations (e.g., RDS Proxy's multiplexing) help.

### Failover and Connection Pool Behavior

When the primary fails and a replica promotes, existing connections break. Application must: (1) Detect failure (connection error, health check); (2) Reconnect (new connections go to new primary); (3) Retry in-flight transactions. Connection pool should **validate** connections before use (test query or keepalive) and **evict** broken ones. PgBouncer can be configured to check server liveness. Without validation, the pool may hand out dead connections, causing repeated failures until the pool is refreshed.

### Connection Pool Sizing: The Math

**Little's Law**: L = λ × W. For a pool: L = concurrent queries using DB, λ = QPS, W = average query duration. Example: 500 QPS, 10ms average query → L = 5. Pool of 10 gives headroom. **But**: p99 query might be 500ms. 500 QPS × 0.5s = 250 concurrent at p99. Pool of 300 would be oversized for normal load; during a spike, you'd want capacity. **Practical approach**: Size for p95 or p99, not average. Monitor wait time; if connections wait > 50ms frequently, increase pool or optimize queries. Oversized pools cause too many connections to DB—defeats pooling purpose.

### Connection Limits: The Full Picture

**PostgreSQL**: `max_connections` limits total. `shared_buffers`, `work_mem` are per-connection or per-operation. 500 connections × 4MB work_mem = 2GB for sorts/hashes alone. Size `max_connections` so that (connections × typical memory) fits in RAM. **MySQL**: Similar. `max_connections`, per-connection buffers. Connection pool reduces effective connections. With PgBouncer pool_size=50, only 50 connections hit PostgreSQL regardless of client count. The pooler becomes the choke point—size it for your throughput.

## ASCII Diagram: Connection Pool Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONNECTION POOLING TOPOLOGY                              │
│                                                                             │
│   WITHOUT POOLER (problem at scale):                                         │
│                                                                             │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐                                   │
│   │ App 1    │ │ App 2    │ │ App 3    │  ... 10 app servers                │
│   │ 20 conn  │ │ 20 conn  │ │ 20 conn  │                                   │
│   └────┬─────┘ └────┬─────┘ └────┬─────┘                                   │
│        │            │            │                                          │
│        └────────────┼────────────┘                                          │
│                     │  200 total connections                                 │
│                     ▼                                                       │
│            ┌───────────────┐                                               │
│            │ PostgreSQL    │  max_connections=100 → OVERFLOW               │
│            │ 100 conn max  │                                               │
│            └───────────────┘                                               │
│                                                                             │
│   WITH PgBounCER:                                                           │
│                                                                             │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐                                   │
│   │ App 1    │ │ App 2    │ │ App 3    │  ... 10 app servers                │
│   │ many     │ │ many     │ │ many     │  (each can open many to pooler)   │
│   │ clients  │ │ clients  │ │ clients  │                                   │
│   └────┬─────┘ └────┬─────┘ └────┬─────┘                                   │
│        │            │            │                                          │
│        └────────────┼────────────┘                                          │
│                     │  Thousands of client connections OK                    │
│                     ▼                                                       │
│            ┌───────────────┐                                               │
│            │  PgBouncer    │  pool_size=50                                 │
│            │  (pooler)     │                                               │
│            └───────┬───────┘                                               │
│                    │  50 actual connections                                 │
│                    ▼                                                       │
│            ┌───────────────┐                                               │
│            │ PostgreSQL   │  max_connections=100, uses 50                 │
│            └───────────────┘                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 6: When to Use NewSQL — Spanner, CockroachDB, TiDB (Topic 258)

## The Traditional Dilemma

- **SQL (relational)**: ACID, joins, queries, consistency. Scales vertically. Single node (or primary-replica) limit.
- **NoSQL**: Horizontal scaling, partition tolerance. Often weak consistency, limited query model.

**NewSQL** aims for: **SQL + horizontal scaling + ACID**. Distributed databases that look like relational databases but scale across many nodes.

## Representative NewSQL Systems

### Google Spanner

- **Globally distributed**, strongly consistent
- **TrueTime**: GPS + atomic clocks for timestamps with bounded uncertainty. Enables **external consistency** (strongest form of serializability across regions)
- **Paxos** for replication within a shard
- Not open source; available as Cloud Spanner

### CockroachDB

- **Spanner-inspired**, open source
- **Raft** for consensus
- **PostgreSQL-compatible** SQL (with some differences)
- **Automatic sharding**, range-based partitioning
- Multi-region, active-active capable

### TiDB

- **MySQL-compatible** SQL
- **Separates compute (TiDB)** from **storage (TiKV)**
- TiKV: distributed key-value store (RocksDB-based), Raft consensus
- Good for MySQL workloads needing horizontal scale

### YugabyteDB

- **PostgreSQL-compatible** (YSQL) and **Cassandra-compatible** (YCQL) APIs
- Raft-based replication
- Single binary, multi-API

## When to Use NewSQL

| Use NewSQL when… | Avoid when… |
|------------------|-------------|
| Need SQL + horizontal scaling + strong consistency | Single PostgreSQL can fit the data |
| Global app, multi-region, strong consistency | Eventual consistency is acceptable |
| Financial, inventory, or other ACID-critical domains | Simple key-value (Redis, DynamoDB) suffices |
| Sharding PostgreSQL is too complex or painful | Latency budget is tight (consensus adds 5–50ms) |
| Team has operational capacity for distributed DB | Team is small; ops burden is high |
| | Cost is primary concern (NewSQL is expensive) |

## When NOT to Use NewSQL

- **Simple key-value access**: Redis or DynamoDB is simpler and cheaper.
- **Eventual consistency is fine**: Read replicas, caching, async replication may be enough.
- **Small scale**: Single PostgreSQL is simpler, cheaper, and faster.
- **Tight latency requirements**: Consensus (Raft, Paxos) adds round-trips. Cross-region adds network latency.
- **Limited ops capacity**: NewSQL is complex—consensus, rebalancing, failure handling. Managed services help but are costly.

## Cost and Operational Complexity

- **Self-managed** (CockroachDB, TiDB on your own cluster): Requires deep expertise. Nodes, replication, backup, upgrades.
- **Managed** (Spanner, CockroachDB Cloud, TiDB Cloud): Less ops, but **expensive**. Spanner pricing is significant at scale.
- **Trade-off**: PostgreSQL + read replicas + careful schema is often 10× cheaper and simpler than NewSQL at modest scale.

## Decision Framework

```
1. Does the data fit on one PostgreSQL node? (< 1–2 TB, < 100K QPS)
   YES → Use PostgreSQL. Done.
   NO → Continue

2. Can we shard PostgreSQL? (Clear shard key, no cross-shard transactions?)
   YES → Shard. Add Vitess or custom routing if needed.
   NO → Continue

3. Do we need strong consistency across shards? (ACID across regions?)
   YES → Consider NewSQL (CockroachDB, Spanner, TiDB)
   NO → Consider NoSQL (DynamoDB, Cassandra) or eventual consistency

4. Can we accept consensus latency? (5–50ms per write)
   YES → NewSQL is viable
   NO → Revisit sharding or accept consistency trade-offs
```

## Comparison Table: PostgreSQL vs NewSQL vs NoSQL

| Dimension | PostgreSQL | CockroachDB / Spanner | DynamoDB | Cassandra |
|-----------|------------|------------------------|----------|-----------|
| **Consistency** | Strong (single node) | Strong (distributed) | Configurable | Eventual |
| **Horizontal scale** | Limited (replicas) | Yes | Yes (managed) | Yes |
| **SQL** | Full | Full (mostly) | No | CQL (limited) |
| **Typical latency** | 1–10ms | 5–50ms (consensus) | 1–15ms | 5–20ms |
| **Ops complexity** | Medium | High | Low (managed) | High |
| **Cost (at scale)** | Low–medium | High | High (throughput-based) | Medium |
| **Best for** | OLTP, single region | Global OLTP, strong consistency | Key-value, serverless | Write-heavy, wide-column |

### NewSQL Deep Dive: Consistency Models

**External consistency** (Spanner): If T1 commits before T2 starts, T2 sees T1's writes. Achieved via TrueTime and two-phase commit with precise timestamps. **Serializable snapshot isolation** (CockroachDB): Transactions see a consistent snapshot; writes are ordered. Weaker than Spanner's external consistency but sufficient for most apps. **Causal consistency**: If A happens before B, any observer sees A before B. NewSQL typically offers serializable or strong consistency; the difference is in how they achieve it (clocks, consensus, conflicts).

### Migration Path: PostgreSQL to CockroachDB

**Schema**: Mostly compatible. Differences in types, functions, and extensions. **Application**: Connection string change; some SQL may need adjustment. **Data migration**: pg_dump/pg_restore, or CDC (Debezium, etc.) for zero-downtime. **Testing**: Run both in parallel; compare results. **Rollback plan**: NewSQL is a significant commitment; ensure you can revert or have a fallback.

### When Sharding PostgreSQL Is Preferable to NewSQL

Sharding makes sense when: (1) Clear shard key (e.g., tenant_id, user_id); (2) No cross-shard transactions; (3) Team has sharding experience; (4) Cost sensitivity—sharded PostgreSQL can be much cheaper than managed NewSQL. Use Vitess, Citus, or custom routing. NewSQL makes sense when: Cross-shard transactions are required, global consistency is critical, or sharding complexity is prohibitive. The decision is organizational as much as technical.

### Spanner's TrueTime: Why Clocks Matter

Distributed systems need ordering. Physical clocks drift. **TrueTime**: GPS + atomic clocks give timestamps with explicit uncertainty (e.g., ±7ms). Spanner waits out the uncertainty before committing—ensures no conflicting orderings. Expensive (hardware) but enables external consistency. CockroachDB and others use Hybrid Logical Clocks (HLC) or NTP—weaker guarantees but no special hardware. For most applications, HLC is sufficient; Spanner's guarantees matter for global financial systems, ad auction systems, and similar high-stakes use cases.

### NewSQL Failure Modes and Trade-offs

**Node failure**: Raft re-elects leader; unavailable for 1–2 election timeouts (seconds). **Network partition**: Minority partition cannot commit; availability vs consistency. **Rebalance**: Adding/removing nodes triggers data movement; increased latency and load during rebalance. **Schema changes**: Distributed DDL is complex; some NewSQL systems serialize schema changes. **Backup/restore**: Cross-node consistency adds complexity; typically use distributed snapshots or export/import. Staff engineers anticipate these: run chaos tests, have runbooks, understand failover RTO/RPO.

### Vitess: Sharded MySQL Without Full NewSQL

**Vitess** sits between "single MySQL" and "full NewSQL." It's a sharding layer for MySQL: application talks to Vitess; Vitess routes to sharded MySQL instances. Supports cross-shard reads (with limitations) and resharding. Lower latency than NewSQL (no consensus per write) but requires application awareness of sharding (or Vitess handles it via vindexes). Good middle ground when MySQL compatibility matters and you can accept sharding constraints. Used at YouTube, Slack, and others.

### Citus: Sharded PostgreSQL

**Citus** extends PostgreSQL with built-in sharding. Tables are distributed across worker nodes by a distribution column. Queries that filter by the distribution column are routed to a single shard; cross-shard queries are parallelized. Compatible with PostgreSQL extensions and tooling. Simpler than full NewSQL—no consensus layer—but no distributed transactions across shards. Good for multi-tenant SaaS, time-series, and analytics workloads where the shard key is natural (tenant_id, time bucket).

## ASCII Diagram: NewSQL Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NewSQL ARCHITECTURE (CockroachDB / TiDB style)           │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐    │
│   │  SQL LAYER (Stateless)                                              │    │
│   │  • Parse, plan, execute                                             │    │
│   │  • Talks to storage layer via RPC                                   │    │
│   └───────────────────────────────┬─────────────────────────────────────┘    │
│                                    │                                         │
│   ┌────────────────────────────────┼────────────────────────────────────┐  │
│   │  DISTRIBUTED CONSENSUS (Raft)  │                                     │  │
│   │  • Each range: leader + followers                                    │  │
│   │  • Writes: quorum acknowledgment                                     │  │
│   │  • Reads: leader or follower (depending on consistency)              │  │
│   └────────────────────────────────┬────────────────────────────────────┘  │
│                                    │                                         │
│   ┌────────────────────────────────┼────────────────────────────────────┐  │
│   │  SHARDED STORAGE                │                                     │  │
│   │  Range 1: [a–m)  Range 2: [m–z)  Range 3: ...                         │  │
│   │  Each range replicated across 3+ nodes                               │  │
│   │  Automatic rebalancing when nodes added/removed                     │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   WRITE PATH: Client → SQL → Leader for range → Raft quorum → Commit        │
│   READ PATH:  Client → SQL → Leader (or follower for stale read) → Return  │
│                                                                             │
│   LATENCY: Network RTT + Raft round-trip + disk (if applicable)             │
│   CROSS-REGION: + inter-region RTT (50–200ms)                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 7: Capacity Estimation and Sizing

## Back-of-Envelope: When Does Single PostgreSQL Break?

**Typical single-node limits** (varies by hardware and workload):
- **Storage**: 1–4 TB per instance (beyond that, backups, restores, replication become painful)
- **Connections**: 100–300 (each = process; more = context switch and memory overhead)
- **QPS**: 10K–50K simple reads; 1K–10K writes (depending on transaction complexity)
- **Data size**: 100M–1B rows per table before maintenance (VACUUM, REINDEX) becomes expensive

**Red flags**: Connection exhaustion, VACUUM cannot keep up, checkpoint takes minutes, replication lag > 10s, index scans exceed 100ms p99. These indicate you're approaching limits.

## Storage Sizing: Data + Indexes + WAL

| Component | Formula | Example (1B rows, 100 bytes/row) |
|-----------|---------|----------------------------------|
| Table data | rows × avg row size | 1B × 100 = 100 GB |
| Indexes | ~30% of data per index | 5 indexes × 30 GB = 150 GB |
| WAL | 10–50% of data per day (write rate dependent) | 50 GB |
| Temp/sort | work_mem × concurrent sorts | 4MB × 100 = 400 MB |
| **Total** | | ~300–400 GB |

Add 50–100% for growth, replicas, and backups. Plan for 2–3× raw data for production footprint.

## Connection Pool Sizing Worksheet

```
Given:
  - App instances: 10
  - QPS per instance: 500 (total 5000)
  - Avg query duration: 8ms
  - p99 query duration: 100ms

Concurrent queries (Little's Law):
  Average: 5000 × 0.008 = 40
  p99: 5000 × 0.1 = 500 (spike scenario)

Pool size per instance:
  Average case: 40 / 10 = 4 per instance → pool 8–10
  p99 case: 500 / 10 = 50 per instance → pool 60 (or accept queuing during spikes)

Total connections to DB: 10 × 60 = 600 → exceeds PostgreSQL default (100)
→ Need PgBouncer: pool_size = 60–80 total
```

---

# Part 8: Operational Scenarios — Putting It Together

## Scenario 1: Slow Writes After Adding Indexes

**Symptom**: INSERT latency increased from 2ms to 50ms after adding 4 indexes. **Diagnosis**: Write amplification. Each INSERT updates the table plus 5 indexes (1 primary + 4 secondary) = 6 writes. At 10K inserts/sec, that's 60K index updates/sec. **Resolution**: (1) Audit indexes—remove unused ones (pg_stat_user_indexes). (2) Consider partial indexes for frequently filtered subsets. (3) Batch inserts where possible. (4) Consider covering indexes to avoid some table lookups, but that increases index size. (5) If workload is append-only, consider partitioning and index only recent partitions.

## Scenario 2: Table Bloat and VACUUM Lag

**Symptom**: Table is 500GB but `pg_total_relation_size` shows 200GB of dead tuples. Queries slowing. **Diagnosis**: VACUUM cannot keep up. Check: long-running transactions (pg_stat_activity), autovacuum settings, I/O saturation. **Resolution**: (1) Kill or reduce long-running transactions. (2) Increase autovacuum workers, lower autovacuum_vacuum_cost_delay. (3) Run manual VACUUM during low traffic. (4) If desperate: VACUUM FULL (exclusive lock, rewrites table)—schedule maintenance window. (5) For future: avoid long-running transactions, design for shorter transactions.

## Scenario 3: Connection Exhaustion Under Load

**Symptom**: "too many connections" errors during traffic spike. **Diagnosis**: Application opened 500 connections; PostgreSQL max_connections = 100. **Resolution**: (1) Immediate: Increase max_connections (buys time but doesn't scale—each connection = process). (2) Proper fix: Connection pooling. Deploy PgBouncer or use RDS Proxy. Size pool with Little's Law. (3) Verify application isn't leaking connections (connection per request anti-pattern). (4) For serverless: Use RDS Proxy or similar to multiplex connections.

## Scenario 4: Replication Lag After High WAL Volume

**Symptom**: Replica is 30 seconds behind. **Diagnosis**: Replica cannot apply WAL fast enough. Causes: (1) Replica has fewer resources (CPU, I/O). (2) Heavy write load on primary. (3) Replica doing too much (analytics queries). **Resolution**: (1) Offload read queries from replica or add more replicas. (2) Increase replica resources. (3) Reduce primary write load (batch transactions, remove unnecessary indexes). (4) Check for replication slots holding old WAL—drop unused slots.

## Scenario 5: NewSQL or Sharded PostgreSQL?

**Question**: 10TB dataset, 50K writes/sec, need strong consistency. **Analysis**: Single PostgreSQL cannot hold 10TB and 50K writes/sec comfortably. Options: (1) Shard PostgreSQL: partition by tenant_id or user_id. Requires application changes, no cross-shard transactions. (2) NewSQL (CockroachDB, TiDB): Automatic sharding, cross-shard transactions. Higher latency, higher cost. **Decision**: If cross-shard transactions are rare, sharding wins. If frequent (e.g., financial transfers between accounts on different shards), NewSQL may be necessary. Prototype both; measure latency and cost.

## Common Misconceptions

| Misconception | Reality |
|--------------|---------|
| "More indexes = faster database" | More indexes = slower writes. Index only for real query patterns. |
| "VACUUM reclaims disk space to the OS" | VACUUM marks space reusable within the table. VACUUM FULL returns to OS but locks table. |
| "Connection pool size = number of app threads" | Pool size = concurrent DB queries. Use Little's Law: QPS × avg duration. |
| "NewSQL is always better than sharding" | NewSQL adds latency and cost. Sharding is simpler when cross-shard transactions aren't needed. |
| "B-tree lookup is O(1)" | O(log_B N). With high B, it's few steps, but not constant. |
| "WAL and data files can be on the same slow disk" | WAL on faster disk (or separate volume) improves write throughput and checkpoint speed. |
| "MVCC means no locks" | Writers still take row-level locks. Only readers avoid locks. |
| "Primary key index is free" | It's still a B-tree; still updated on insert. But it's required for uniqueness; cost is unavoidable. |

## Recommended Monitoring Queries (PostgreSQL)

```sql
-- Unused indexes (candidates for removal)
SELECT schemaname, relname, indexrelname, idx_scan
FROM pg_stat_user_indexes
WHERE idx_scan = 0 AND indexrelname NOT LIKE '%_pkey';

-- Table bloat and VACUUM status
SELECT relname, n_live_tup, n_dead_tup,
       round(100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 2) AS dead_pct,
       last_vacuum, last_autovacuum
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000
ORDER BY n_dead_tup DESC;

-- Long-running transactions (VACUUM blockers)
SELECT pid, now() - xact_start AS duration, state, query
FROM pg_stat_activity
WHERE state != 'idle' AND xact_start IS NOT NULL
ORDER BY xact_start;

-- Connection count by state
SELECT state, count(*) FROM pg_stat_activity GROUP BY state;
```

**Operational tip**: Run these periodically (e.g., via cron or monitoring agent). Alert on: `n_dead_tup` / `n_live_tup` > 0.2 for large tables, transactions older than 10 minutes, connection count approaching `max_connections`. These signals often precede incidents.

## Troubleshooting Decision Tree

```
Symptom: Slow queries
├── Sequential scan on large table?
│   └── Add index on filter/sort columns (verify with EXPLAIN)
├── Index scan but high "rows fetched"?
│   └── Stale statistics → ANALYZE; or wrong index (selectivity)
├── High "actual time" in sort/hash?
│   └── work_mem too low; or query returns too many rows
└── Lock wait?
    └── Check pg_locks, pg_stat_activity; find blocking transaction

Symptom: Slow writes
├── Many indexes?
│   └── Remove unused; consider partial indexes
├── VACUUM running?
│   └── Normal; consider tuning autovacuum
├── WAL/checkpoint saturation?
│   └── Faster disk for WAL; tune checkpoint_completion_target
└── Lock contention?
    └── Shorter transactions; reduce hot-spot updates

Symptom: Connection errors
├── "too many connections"?
│   └── Connection pooling (PgBouncer); or raise max_connections (temporary)
├── Connections timing out?
│   └── Pool too small; or slow queries holding connections
└── "connection reset"?
    └── Failover; or DB restart; pool must reconnect
```

---

# Summary: Key Takeaways

1. **B-Tree**: Wide trees minimize disk reads. 4 levels for 1B rows with branching factor 500. B+ tree: data in leaves, leaves linked for range scans. Clustered vs non-clustered affects layout and access patterns. Each node = one disk page; branching factor drives height.

2. **Secondary indexes**: Every index multiplies write cost. Write amplification. Covering indexes enable index-only scans. Composite index column order matters (leftmost prefix). Avoid "index everything." Partial and expression indexes optimize specific patterns. Monitor usage; remove unused.

3. **WAL**: Log before data. Sequential, append-only. Crash recovery by replay. Checkpoints bound WAL growth. Replication streams WAL. Full-page writes protect against torn pages. Physical vs logical replication; PITR for point-in-time restore.

4. **MVCC**: Multiple row versions. Readers use snapshots; no read locks. Writers create new versions. VACUUM reclaims dead tuples. Lagging VACUUM causes bloat and wraparound risk. Long-running transactions block VACUUM. Isolation levels (RC, RR, Serializable) build on snapshots.

5. **Connection pooling**: Each PostgreSQL connection is a process. Pool to limit connections. Size pool with Little's Law (QPS × avg duration). Use PgBouncer when many app servers would exceed max_connections. Transaction vs session pooling; prepared statements with transaction pooling require care.

6. **NewSQL**: SQL + horizontal scaling + ACID. Use when single PostgreSQL or sharding isn't enough and strong consistency is required. Consensus (Raft) adds latency. Spanner, CockroachDB, TiDB, YugabyteDB. Expect higher latency, cost, and ops complexity. Prefer PostgreSQL when it fits.

## Cross-Topic Integration: How the Pieces Fit

A single write flows through multiple systems: **Application** sends INSERT → **Connection pool** assigns a connection → **PostgreSQL** receives it. Internally: (1) **MVCC** allocates new row version (xmin set). (2) **B-tree** indexes are updated—each secondary index gets a new entry. (3) **WAL** records all changes; fsync ensures durability. (4) **Buffer pool** holds dirty pages until checkpoint. (5) **Checkpoint** flushes pages to data files; **VACUUM** (eventually) reclaims space from deleted rows. Each layer has limits: too many indexes → B-tree write amplification; too many connections → pool exhaustion; long transactions → VACUUM blocked; slow disk → WAL and checkpoint lag. Staff engineers understand these interactions and tune the whole system, not just one knob.

**When single-node PostgreSQL hits its ceiling**—storage, connections, or write throughput—the next step is either **sharding** (partition data across multiple PostgreSQL instances, application routes by shard key) or **NewSQL** (distributed database with built-in sharding and consensus). Sharding is simpler and cheaper but sacrifices cross-shard transactions and global consistency. NewSQL provides both at the cost of latency (consensus), operational complexity, and price. The internals you've learned here—B-tree structure, WAL semantics, MVCC behavior, connection economics—apply to both. NewSQL layers distribution and consensus on top; the core ideas of indexes, durability, and concurrency remain.

---

# Appendix: Interview-Oriented One-Liners

- **"Why B-tree?"** — Minimizes disk I/O by being wide (high branching factor), not tall. 4 disk reads for 1B rows with branching factor 500.
- **"Cost of secondary indexes?"** — Every index multiplies write cost. 5 indexes = 6 writes per row. Write amplification.
- **"What is WAL?"** — Sequential log of changes, written before data files. Enables crash recovery and replication. Append-only.
- **"Why does VACUUM exist?"** — MVCC creates multiple row versions. VACUUM removes dead versions. Lag causes bloat and wraparound risk.
- **"Why connection pooling?"** — Each PostgreSQL connection is a process. Pool shares few connections among many app threads.
- **"NewSQL vs sharding?"** — NewSQL: automatic sharding, cross-shard transactions, higher latency. Sharding: simpler, cheaper, no cross-shard transactions.

## Extended Interview Q&A

**Q: "A query is slow. How do you debug it?"**  
A: (1) EXPLAIN ANALYZE to see plan and actual rows. (2) Check for sequential scans on large tables—missing index? (3) Check for high row estimates vs actual—stale statistics? Run ANALYZE. (4) Check buffer hit ratio—disk I/O bound? (5) Check for lock waits in pg_stat_activity. (6) Consider query structure—N+1, unnecessary joins, heavy aggregations.

**Q: "Writes got slow after we added replicas. Why?"**  
A: Synchronous replication waits for replica acknowledgment before commit. Adds latency (typically 1–5ms per write). If replica is slow or far away, latency increases. Solutions: async replication (accept possible data loss on failover), or optimize replica—faster disk, more CPU, reduce replica-side read load.

**Q: "When would you choose LSM over B-tree?"**  
A: Write-heavy, append-mostly workloads (logs, events, metrics). LSM batches writes in memory, flushes sequentially. Better write throughput. Trade-off: range scans can touch many segments; read latency less predictable. Cassandra, RocksDB, LevelDB use LSM. B-tree for OLTP, mixed read/write, predictable latency.

**Q: "How do you size a connection pool for a new service?"**  
A: Little's Law: concurrent = QPS × avg query duration. For 1000 QPS, 5ms avg → 5 concurrent. Pool of 10–20 with buffer. Plan for p99: if p99 is 200ms, 1000 × 0.2 = 200. Don't size pool = app threads; size for actual DB concurrency. Monitor wait time; increase if connections frequently wait.

**Q: "Explain the trade-off between more indexes and write performance."**  
A: Each index adds a B-tree updated on INSERT/UPDATE/DELETE. Write amplification. Benefit: faster reads. Trade-off: index only when read benefit outweighs write cost. Remove unused indexes (pg_stat_user_indexes.idx_scan = 0).

**Q: "What happens if VACUUM falls behind?"**  
A: Table bloat, transaction ID wraparound risk, database may refuse writes. Fix: kill long-running transactions, increase autovacuum workers, manual VACUUM. Prevention: short transactions.

**Q: "How does NewSQL achieve strong consistency across regions?"**  
A: Consensus (Raft, Paxos) ensures replicas agree on write order. Quorum acknowledgment before commit. Cross-region adds latency. Spanner uses TrueTime for external consistency.

## Staff Interview Walkthrough: "Design a High-Throughput Order System"

**Interviewer**: "We need to support 100K orders per second. Discuss database internals."

**Strong Answer Structure**:

1. **Storage and indexing**: "At 100K writes/sec, each insert touches the table and every index. If we have 5 indexes, that's 600K logical writes/sec. B-trees handle this, but we need to minimize indexes—only index columns that drive hot queries. Covering indexes can avoid heap fetches for common queries. We should benchmark insert latency with 0, 2, 5 indexes to quantify write amplification."

2. **WAL and durability**: "WAL will be under heavy load. Sequential writes help, but 100K commits/sec means 100K fsyncs unless we batch. We might use group commit—multiple transactions share one fsync. Checkpoint needs to keep up; we'll tune checkpoint_completion_target and put WAL on faster storage. Replication will stream WAL; we need enough replica capacity to apply it."

3. **MVCC and VACUUM**: "100K inserts/sec creates many row versions. Autovacuum must keep up. Long-running transactions would block VACUUM and cause bloat. We'll keep transactions short, monitor n_dead_tup, and consider partitioning—VACUUM per partition is more manageable."

4. **Connections**: "100K QPS with 5ms average query = 500 concurrent queries. If we have 20 app servers, that's 25 concurrent each. Pool of 30–40 per server = 600–800 total connections. PostgreSQL max_connections is typically 100–300. We need PgBouncer or similar—centralized pool of 100–200 connections serving all app servers."

5. **Scale beyond single node**: "If 100K writes/sec stresses a single PostgreSQL, we shard by merchant_id or use NewSQL. Sharding gives lower latency but no cross-shard transactions. NewSQL gives ACID across shards but adds consensus latency. The choice depends on whether we need cross-merchant transactions."

**Key Staff Signal**: The candidate connects each internal (B-tree, WAL, MVCC, pooling) to the concrete numbers and operational implications. They don't just name mechanisms—they quantify impact and propose mitigations.
