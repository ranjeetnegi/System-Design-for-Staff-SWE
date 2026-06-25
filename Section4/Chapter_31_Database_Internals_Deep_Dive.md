# Chapter 29 — Part A: Database Internals Deep Dive
## B-Tree and LSM-Tree Storage Engines

> "An L5 engineer knows which database to pick. An L6 engineer knows why it behaves the way it does when everything is on fire."

---

## Table of Contents

1. Why Internals Matter at Staff Level
2. The Hard Drive Problem — Why Storage Structures Exist
3. B-Tree Internals: How PostgreSQL Finds Rows
   - What a B-Tree Actually Is
   - Page Structure
   - Point Lookup: Finding One Row
   - Range Scan: Finding a Range of Rows
   - Insert: Where Pages Split
   - Why Secondary Indexes Slow Writes
4. LSM-Tree Internals: How Cassandra Makes Writes Fast
   - The Write Problem B-Trees Have
   - LSM-Tree: Turning Random Writes into Sequential Writes
   - SSTable Structure
   - Bloom Filters Explained
   - Read Path in LSM-Trees
   - Compaction Strategies
5. B-Tree vs LSM-Tree: The Full Comparison
6. Real Incident: Write Amplification Took Down the Database

---

## 1. Why Internals Matter at Staff Level

You finished Chapter 28. You now know that PostgreSQL is great for relational data with complex queries, Cassandra handles write-heavy workloads at scale, Redis serves as an in-memory cache, and Bigtable sits behind analytics pipelines. You can walk through sharding strategies, replication factors, and caching tiers in a system design interview without breaking a sweat.

That is L5 knowledge. It is solid, and it will get you through most interviews.

But L6 interviews are different. An L6 interview is not testing whether you know what tool to pick. It is testing whether you understand **why** the tool behaves the way it does — and specifically, whether you can predict behavior under stress that the interviewer already knows about.

Here is the shift in concrete terms. Consider three questions that come up in real L6 interviews and real production incidents:

---

**Question 1: "Why did adding a secondary index make our writes 5x slower?"**

An L5 answer: "Secondary indexes add overhead."

An L6 answer: "Every INSERT into your table now performs one write to the heap file and one write to each secondary index's B-Tree. If you have 5 secondary indexes and your key space is 1 billion rows, each index tree is 4-5 levels deep. Each INSERT triggers 5-6 random page writes — and if write volume doubled, that is 10-12 random writes per row instead of 2. On a spinning disk that handles 200 random IOPS, you have saturated your disk well before the row count suggests you should have."

That answer requires you to know what a B-Tree page is, how index maintenance works, and what random I/O costs on different hardware.

---

**Question 2: "Why is our PostgreSQL table 200GB when we only have 50GB of actual data?"**

An L5 answer: "There might be bloat."

An L6 answer: "PostgreSQL uses MVCC — Multi-Version Concurrency Control. When you UPDATE a row, it does not overwrite the old version. It marks the old row as deleted and writes the new row as a fresh tuple in the heap file. Dead tuples accumulate. If autovacuum is not running aggressively enough, dead tuples pile up. At 50GB of live data with a high UPDATE rate, 150GB of dead tuples is completely believable. The fix involves tuning autovacuum cost parameters and possibly running VACUUM FULL for a one-time reclaim — but VACUUM FULL takes an exclusive lock, so you need a maintenance window."

That answer requires you to understand how PostgreSQL physically stores rows.

---

**Question 3: "Why does Cassandra read slower than writes even though reads seem simpler?"**

An L5 answer: "Cassandra is optimized for writes."

An L6 answer: "Cassandra uses an LSM-Tree (Log-Structured Merge-Tree). Writes go into an in-memory structure called a MemTable, which is fast because it never touches the disk until it flushes. But reads have to check the MemTable AND every SSTable (Sorted String Table) on disk that might contain the key — potentially dozens of files across multiple compaction levels. Even with bloom filters eliminating most SSTable checks, a read might still touch 3-5 files on disk. The read amplification problem gets worse the longer the system has been running without compaction."

That answer requires you to know how LSM-Trees work end to end.

---

This chapter gives you the internals knowledge behind all three of those answers. Here is a map of what we will cover and how the pieces connect:

```
THE INTERNALS LANDSCAPE
=======================

HARDWARE REALITY
  Spinning disk: 100MB/s sequential, 0.1MB/s random (1000x gap)
  SSD:           3000MB/s sequential, 100MB/s random (30x gap)
         |
         | (forces two different design choices)
         |
    +---------+                    +-----------+
    | B-TREE  |                    | LSM-TREE  |
    | (PostgreSQL, MySQL)          | (Cassandra, RocksDB)
    +---------+                    +-----------+
         |                               |
    Minimizes                       Eliminates
    random READS                    random WRITES
         |                               |
    Pages (8KB)                    MemTable + Commit Log
    Fan-out ~300                   SSTables (sorted, immutable)
    Height = 4-5 for 1B rows       Compaction (background merge)
         |                               |
    Fast reads                     Fast writes
    Slower writes (index           Slower reads (check
    maintenance = random I/O)      multiple SSTables)
         |                               |
    Write amplification            Read amplification
    = 1 + num_indexes              = num_SSTables_to_check

                    BOTH NEED
                  Bloom Filters
               (skip SSTable reads)
              MVCC / Concurrency Control
               (covered in Part B)
```

---

## 2. The Hard Drive Problem — Why Storage Structures Exist

Before you can understand why B-Trees and LSM-Trees look the way they do, you need to feel the hardware constraint that forced them into existence.

### The Physics of Storage

A **spinning hard disk** (HDD) stores data on a circular magnetic platter that rotates. To read data, a physical read head must swing to the correct track and wait for the disk to spin the right sector under it. That movement takes time — typically 5-10 milliseconds.

Ten milliseconds does not sound bad until you do the math.

```
DISK SPEED COMPARISON
=====================

Sequential read (reading 1MB of data stored consecutively):
  HDD:  100 MB/s  -->  1MB takes  ~0.01 seconds  (10ms)
  SSD: 3000 MB/s  -->  1MB takes  ~0.0003 seconds (0.3ms)
  RAM: 50000 MB/s -->  1MB takes  ~0.00002 seconds (0.02ms)

Random read (reading 4KB from a random location on disk):
  HDD:  0.1 MB/s  -->  4KB takes  ~5ms   (head must physically move)
  SSD: 100  MB/s  -->  4KB takes  ~0.04ms (no physical movement)
  RAM: 50000 MB/s -->  4KB takes  trivial

THE GAP:
  HDD sequential vs random: 1000x difference
  SSD sequential vs random:   30x difference
```

The spinning disk analogy: imagine you are in a library where the books are stored on a conveyor belt. If you want books that are physically next to each other on the belt, you can grab them one after another as they scroll by (sequential — fast). But if you want three books from random positions on the belt, you have to wait for the belt to bring each one around to you (random — slow).

SSDs eliminate the spinning mechanism, so there is no physical seek time. But even SSDs have a random vs sequential gap because of how flash memory pages are erased and written — random writes cause **write amplification** inside the SSD's own firmware. The 30x gap on SSDs is much better than the 1000x gap on HDDs, but it still matters at database scale.

### How Databases Exploit This

Every clever thing a storage engine does is an attempt to turn expensive random I/O into cheaper sequential I/O.

**B-Trees exploit the read pattern.** Instead of scattering your data all over disk and doing one random seek per key comparison, a B-Tree packs many keys into a single 8KB page. One random seek retrieves 8KB — which might contain 300 keys. The tree is short (4-5 levels for a billion rows), so the total number of random seeks is tiny: 4-5 reads to find any row.

**LSM-Trees exploit the write pattern.** Instead of updating a row in place (which requires a random write to wherever the page happens to live on disk), an LSM-Tree buffers all writes in memory and periodically flushes them to disk as one large sequential write. The flush writes a multi-megabyte file from beginning to end — exactly the workload where disks are fast.

Both approaches are engineering responses to the same physical reality: random I/O is expensive, so we must minimize it.

```
SEEK TIME ON A SPINNING DISK
=============================

                    [Read Head]
                         |
  Platter:  ...====[SECTOR A]====...====...=[SECTOR B]=====...
                   ^                         ^
              data here                  data here
                   |                         |
                   |<--- physical arm  ----->|
                       movement required

  Reading SECTOR A then SECTOR B (far apart):
  1. Head seeks to SECTOR A: ~5ms
  2. Read SECTOR A: ~0.1ms (fast once there)
  3. Head seeks to SECTOR B: ~8ms
  4. Read SECTOR B: ~0.1ms
  Total: ~13.2ms for 2 reads

  Reading SECTOR A then SECTOR C (right next to A):
  1. Head seeks to SECTOR A: ~5ms
  2. Read SECTOR A: ~0.1ms
  3. Disk rotates slightly, SECTOR C arrives: ~0.05ms
  4. Read SECTOR C: ~0.1ms
  Total: ~5.25ms for 2 reads (2.5x faster!)

  KEY INSIGHT: if you can arrange data so reads are sequential,
  you eliminate the seek overhead for every read after the first.
```

---

## 3. B-Tree Internals: How PostgreSQL Finds Rows

### What a B-Tree Actually Is

A **B-Tree** (Balanced Tree) is the data structure that backs almost every index you have ever used in a relational database. PostgreSQL, MySQL (InnoDB), Oracle, SQL Server — all of them use B-Trees as their primary index structure.

Here is the intuition. Imagine you have a million customer records sorted by customer ID. You could store them in a sorted array and use binary search to find any customer in about 20 comparisons. That works great in memory. But on disk, each comparison in a binary search might be a random I/O. 20 random I/Os at 5ms each = 100ms per lookup. That is too slow.

The B-Tree solves this by making each "step" in the search retrieve many keys at once. Instead of comparing one key at a time, you retrieve a whole **page** — 8,192 bytes in PostgreSQL — and compare potentially hundreds of keys from that single disk read.

```
B-TREE STRUCTURE (3 levels shown, integer key index)
=====================================================

                        [ROOT PAGE]
                   +-----------------+
                   | 250 | 500 | 750 |
                   +--+--+--+--+--+-+
                      |     |     |
           +----------+     |     +----------+
           |                |                |
     [INTERNAL PAGE]  [INTERNAL PAGE]  [INTERNAL PAGE]
     | 100 | 175 |    | 300 | 400 |    | 600 | 680 |
     +-+---+--+--+    +-+---+--+--+    +-+---+--+--+
       |   |   |        |   |   |        |   |   |
      ...  |  ...      ...  |  ...      ...  |  ...
           |                |                |
     [LEAF PAGE]      [LEAF PAGE]      [LEAF PAGE]
     | 175 --> H1 |   | 400 --> H4 |   | 680 --> H7 |
     | 176 --> H2 |   | 401 --> H5 |   | 681 --> H8 |
     | 177 --> H3 |   | 402 --> H6 |   | 682 --> H9 |
     | --> next leaf|  | --> next  |   | --> next   |
     +--------------+  +-----------+   +-----------+

     H1, H2... = pointer to heap page (actual row data)
     Each leaf page links to the next leaf (doubly linked list)
```

Key properties to memorize:

- Every node in the tree (root, internal, leaf) is exactly one **page** — 8KB in PostgreSQL.
- Each page can hold roughly 300 integer keys (or fewer for larger key types like UUIDs).
- This "300 keys per page" is called the **fan-out**. Higher fan-out = shorter tree.
- The tree height is `log₃₀₀(N)` where N is the number of rows.
  - 1,000 rows: height 2
  - 1,000,000 rows: height 3
  - 1,000,000,000 rows (1 billion): height ~5

This is the magic of B-Trees. Even with a billion rows, you need to read at most 5 pages to find any key. Five random disk reads. Compare that to a full table scan of 1 billion rows that would require reading millions of pages.

### Page Structure

Let us look inside a single B-Tree page, since everything in a B-Tree is a page.

```
INSIDE A SINGLE B-TREE LEAF PAGE (8192 bytes)
==============================================

+----------------------------------------------------------+
| PAGE HEADER (24 bytes)                                   |
|  - LSN: Log Sequence Number (for crash recovery)         |
|  - Flags: is leaf? is root?                              |
|  - Lower: where free space starts                        |
|  - Upper: where item data ends                           |
|  - Special: pointer to page-type-specific area           |
+----------------------------------------------------------+
| ITEM ID ARRAY (grows downward from header)               |
|  [ItemID 1][ItemID 2][ItemID 3]...[ItemID N]            |
|  Each ItemID: offset + length of item within this page   |
+----------------------------------------------------------+
|                                                          |
|              FREE SPACE                                  |
|                                                          |
+----------------------------------------------------------+
| ITEM DATA (grows upward from the bottom)                 |
|  Each item = key value + pointer to heap tuple           |
|  [key=175, heapptr=(page 42, offset 88)]                 |
|  [key=176, heapptr=(page 42, offset 200)]                |
|  [key=177, heapptr=(page 43, offset 16)]                 |
|  ...                                                     |
+----------------------------------------------------------+
| SPECIAL AREA (for leaf pages: left/right sibling ptrs)  |
|  left_sibling_page = 17                                  |
|  right_sibling_page = 19                                 |
+----------------------------------------------------------+

Note: "Lower" and "Upper" pointers track where free space is.
When a page fills up, Lower and Upper meet -- page is full.
```

Why is the page size 8KB? Because most operating systems use a memory page size of 4KB or 8KB. When the database reads one B-Tree page from disk, the OS fetches it as whole memory pages. Aligning the database page size to the OS page size avoids reading partial OS pages, which would waste I/O.

A **heap tuple** (what "heapptr" points to above) is the actual row data — the real columns of your table. The B-Tree index stores only the indexed column's value plus a pointer. The pointer contains a block number (which 8KB block in the heap file) and an offset (which byte within that block).

### Point Lookup: Finding One Row

Suppose you run: `SELECT * FROM users WHERE user_id = 42;`

PostgreSQL executes this using the primary key index (a B-Tree). Here is exactly what happens:

```
POINT LOOKUP: user_id = 42
===========================

Step 1: Read ROOT page
  Root page contains: [250 | 500 | 750]
  42 < 250 --> follow leftmost pointer
  DISK READ #1

Step 2: Read INTERNAL page (leftmost child of root)
  Internal page contains: [30 | 60 | 90 | 120]
  30 <= 42 < 60 --> follow second pointer
  DISK READ #2

Step 3: Read LEAF page
  Leaf page contains items sorted by key:
  [40 --> heap(p88, off=16)]
  [41 --> heap(p88, off=200)]
  [42 --> heap(p89, off=44)]   <--- FOUND!
  [43 --> heap(p89, off=188)]
  DISK READ #3

Step 4: Read HEAP page p89
  Fetch the actual row at offset 44 in page 89
  user_id=42, name="Alice", email="alice@example.com", ...
  DISK READ #4

TOTAL: 4 disk reads for a 1-million-row table
       5-6 disk reads for a 1-billion-row table
```

Compare this to a **full table scan**. If you run the same query without an index, PostgreSQL reads every single page in the heap file from beginning to end. For a 1-million-row table where each page holds ~100 rows, that is 10,000 page reads — 2,500x more I/O than the indexed lookup.

This is why indexes exist. The B-Tree trades a small amount of write overhead (maintaining the index on INSERT/UPDATE/DELETE) for massively faster reads.

### Range Scan: Finding a Range of Rows

Now suppose you run: `SELECT * FROM orders WHERE order_date BETWEEN '2024-01-01' AND '2024-01-31';`

The point lookup gets you to the first matching leaf page. But a range scan needs everything between January 1 and January 31. How does the B-Tree handle that without going back to the root for each next key?

The answer is the **doubly-linked list of leaf pages** (shown in the special area of the page structure above). Every leaf page stores a pointer to its left sibling and its right sibling. Once you reach the first matching leaf, you just follow the right-sibling pointer to the next leaf, then the next, until you pass the end of your range.

```
RANGE SCAN: order_date BETWEEN 2024-01-01 AND 2024-01-31
==========================================================

Step 1: Point lookup to find first leaf containing 2024-01-01
  (same as point lookup: root --> internal --> leaf)
  Land on Leaf Page 44

Step 2: Scan within Leaf Page 44
  [2024-01-01 --> heap(p100, off=8)]   <-- start here
  [2024-01-01 --> heap(p100, off=80)]
  [2024-01-02 --> heap(p101, off=16)]
  ...
  [2024-01-05 --> heap(p102, off=44)]
  (page full, all keys in range)

Step 3: Follow right-sibling pointer to Leaf Page 45
  [2024-01-06 --> heap(p103, off=20)]
  ...
  [2024-01-12 --> heap(p106, off=55)]
  (page full, all keys in range)

Step 4: Follow right-sibling pointer to Leaf Page 46
  ...continue until...
  [2024-01-31 --> heap(p140, off=90)]  <-- last match
  [2024-02-01 --> heap(p141, off=10)]  <-- outside range, STOP

Leaf pages traversed: 44 --> 45 --> 46 --> ... (sequential!)
No need to go back to root for each page!

Leaf Page 44 --> [right ptr] --> Leaf Page 45 --> [right ptr] --> Leaf Page 46 --> ...
```

This is efficient because the leaf pages are read in order — sequential I/O from page 44 to page 45 to page 46. The disk head barely has to move. This is why B-Trees are excellent for range queries and why databases sort the leaf pages sequentially on disk when possible.

### Insert: Where Pages Split

Inserts are where B-Trees get complicated. When you INSERT a new row:

1. PostgreSQL finds the correct leaf page via a point lookup (same as reading).
2. PostgreSQL inserts the new key+pointer into that leaf page at the correct sorted position.
3. If the page has space, done. Easy.
4. If the page is full (Lower and Upper pointers have met), PostgreSQL must **split the page**.

```
PAGE SPLIT: inserting key=178 into a full leaf page
====================================================

BEFORE (Leaf Page 18, completely full):
+-----------------------------------------------+
| [171,H1] [172,H2] [173,H3] [174,H4] [175,H5] |
| [176,H6] [177,H7]  <-- FULL, no room for 178  |
+-----------------------------------------------+

Step 1: Allocate a new leaf page (Leaf Page 19)
Step 2: Find the median key (175 in this case)
Step 3: Move keys > median to the new page

AFTER:
Leaf Page 18 (left half):          Leaf Page 19 (right half):
+---------------------------+       +---------------------------+
| [171] [172] [173] [174]   |       | [175] [176] [177] [178]   |
| right_sibling = Page 19   |       | left_sibling  = Page 18   |
+---------------------------+       +---------------------------+

Step 4: Push median key (175) UP to the parent internal page
  Parent must now store: [...| 174 | 175 | 200 |...]
                                     ^
                              new entry pointing to Page 19

If PARENT is also full:
  --> Parent page also splits
  --> Pushes ITS median up to grandparent
  --> Can cascade all the way to root

Root split (very rare):
  Root splits into two pages
  New root page is created
  Tree grows one level taller
```

The cascade split is rare in practice because internal pages can hold ~300 keys before splitting, and the root can hold ~300 entries pointing to ~300 internal pages, each of which holds ~300 leaf pages. You need a very deep, very full tree before a root split occurs.

### Why Secondary Indexes Slow Writes

Now you can understand the write slowdown that opens this chapter.

Every index on a table is a separate B-Tree. Every INSERT into the table must update every B-Tree. This is called **write amplification** — one logical write (insert one row) causes multiple physical writes.

```
WRITE AMPLIFICATION WITH 5 SECONDARY INDEXES
=============================================

Table: trades
Indexes:
  (1) Primary key index on trade_id     --> B-Tree #1
  (2) Secondary index on ticker         --> B-Tree #2
  (3) Secondary index on trader_id      --> B-Tree #3
  (4) Secondary index on trade_date     --> B-Tree #4
  (5) Secondary index on exchange       --> B-Tree #5
  (6) Secondary index on status         --> B-Tree #6

One INSERT (INSERT INTO trades VALUES ...):
  --> Write to heap file                (1 write)
  --> Update B-Tree #1 (primary key)    (1 write, possibly page split)
  --> Update B-Tree #2 (ticker)         (1 write, possibly page split)
  --> Update B-Tree #3 (trader_id)      (1 write, possibly page split)
  --> Update B-Tree #4 (trade_date)     (1 write, possibly page split)
  --> Update B-Tree #5 (exchange)       (1 write, possibly page split)
  --> Update B-Tree #6 (status)         (1 write, possibly page split)
  TOTAL: 7 writes minimum per INSERT (more if page splits cascade)

One UPDATE on ticker (changes the ticker value):
  --> Update heap tuple                          (1 write)
  --> Delete old ticker from B-Tree #2           (1 write)
  --> Insert new ticker into B-Tree #2           (1 write)
  --> All other indexes still current (no change needed)
  TOTAL: 3 writes for this one UPDATE
```

The write amplification formula is:

```
Write Amplification = (1 + num_indexes) × writes_per_second

Example:
  5 secondary indexes, 10,000 inserts/second
  = (1 + 5) × 10,000
  = 60,000 B-Tree page writes per second

  Spinning disk: 200 random IOPS max
  60,000 writes >> 200 IOPS --> DISK SATURATED
```

This is why experienced engineers carefully audit their indexes before launching a write-heavy workload. Every index is a performance tax on every write.

The rule of thumb: add an index when you can measure that it makes an existing query fast enough to justify the write overhead. Never add speculative indexes "just in case."

---

## 4. LSM-Tree Internals: How Cassandra Makes Writes Fast

### The Write Problem B-Trees Have

Recall the write amplification formula. Even with zero secondary indexes, a B-Tree INSERT requires finding the correct leaf page (random read) and then writing to that page (random write). On a spinning disk doing 200 random IOPS, you hit the ceiling at 200 rows inserted per second — before any secondary indexes.

High-throughput systems need to handle hundreds of thousands of writes per second. B-Trees simply cannot scale to this write rate on spinning disks. Something fundamentally different is needed.

The insight behind LSM-Trees: **stop trying to maintain sorted order on disk immediately. Instead, accept writes into memory and batch them into sorted disk writes later.**

### LSM-Tree: Turning Random Writes into Sequential Writes

**LSM** stands for **Log-Structured Merge-Tree**. The name describes what it does: it uses a log (append-only) structure and periodically merges things together.

The write path has four stages:

```
LSM-TREE WRITE PATH
====================

Stage 1: WRITE ARRIVES
  INSERT (key="user:alice", value={name:"Alice", age:30})
                 |
                 v
  +-------------+    +------------------+
  |  MEMTABLE   |    |   COMMIT LOG     |
  | (in memory) |    | (disk, append)   |
  +-------------+    +------------------+
  Sorted Red-Black    Sequential write to
  Tree in RAM.        append-only log file.
  Fast! (~1 microsec) Durable! (survives crash)

Stage 2: MEMTABLE FILLS UP (~64MB threshold)
                 |
                 v
  Flush MemTable to disk as an SSTABLE
  (Sorted String Table)

  [SSTable L0-001.db]
  key=user:alice  --> {name:Alice, age:30}
  key=user:bob    --> {name:Bob, age:25}
  key=user:charlie--> {name:Charlie, age:40}
  ... (sorted, immutable, written sequentially)

  One large sequential write = FAST!
  Old MemTable discarded. New MemTable starts empty.

Stage 3: SSTABLES ACCUMULATE
  L0-001.db  (old)
  L0-002.db  (older)
  L0-003.db  (newest flush)

Stage 4: COMPACTION (background process)
  Merge SSTables like merge-sort:
  Read L0-001 + L0-002 simultaneously
  Write merged result as one new SSTable
  Delete L0-001 and L0-002
  Result: fewer, larger SSTables with no duplicate keys
```

Let us go through each stage carefully.

**Stage 1 — The MemTable.** Every incoming write goes into an in-memory data structure called the MemTable. Think of it as a sorted dictionary in RAM. Cassandra implements it as a sorted tree (typically a Red-Black Tree or Skip List) so that keys stay sorted for efficient reads. Writing to RAM takes microseconds — no disk involved.

But RAM is volatile. If the process crashes, everything in the MemTable disappears. That is why every write also goes to the **commit log** (called the "write-ahead log" in PostgreSQL).

**The Commit Log.** The commit log is a file on disk. But critically, writes to the commit log are **sequential** — each new write is appended to the end of the file. Sequential disk writes are fast: you achieve near-sequential disk throughput (100MB/s on HDD, 3GB/s on SSD). If the process crashes, the commit log is replayed to reconstruct the MemTable.

**Stage 2 — SSTable Flush.** When the MemTable reaches its size threshold (64MB in Cassandra by default), the database freezes that MemTable and writes it entirely to disk as a new file. This file is called an **SSTable** (Sorted String Table). Writing an entire SSTable is one large sequential write — fast. After the flush, the commit log entries for that MemTable are no longer needed and can be discarded.

**Stage 3 — SSTable Accumulation.** As the system keeps running, more SSTables accumulate on disk. Each SSTable is a snapshot of what the MemTable looked like at a point in time. The newest SSTable has the most recent writes; older SSTables have older data.

**Stage 4 — Compaction.** Over time, many small SSTables slow down reads (you have to check many files for each key). A background **compaction** process runs periodically. It picks several SSTables and merges them together into one larger SSTable, like running merge-sort on sorted lists. During merging, if two SSTables have entries for the same key, the newer one wins. Tombstones (deletion markers) are resolved. Old SSTables are deleted after the new merged SSTable is fully written.

### SSTable Structure

An SSTable is not just a flat sorted file. It has internal structure to make lookups efficient:

```
SSTABLE FILE STRUCTURE
=======================

+--------------------------------------------+
| FILE HEADER                                |
|   Magic number, version, metadata          |
+--------------------------------------------+
| BLOOM FILTER                               |
|   Compact bit array: "is key K in this     |
|   file?" -- answers in microseconds        |
|   (explained in detail below)              |
+--------------------------------------------+
| INDEX BLOCK                                |
|   Sparse index: stores the FIRST key of   |
|   each data block.                         |
|   [block1_start: "alice"]                  |
|   [block2_start: "charlie"]                |
|   [block3_start: "mike"]                   |
|   Use binary search to find which block    |
|   might contain your key.                  |
+--------------------------------------------+
| DATA BLOCK 1                               |
|   alice  --> {name:Alice, age:30}          |
|   bob    --> {name:Bob, age:25}            |
|   carol  --> {name:Carol, age:22}          |
+--------------------------------------------+
| DATA BLOCK 2                               |
|   charlie --> {name:Charlie, age:40}       |
|   dave    --> {name:Dave, age:35}          |
|   emily   --> {name:Emily, age:28}         |
+--------------------------------------------+
| DATA BLOCK 3                               |
|   mike  --> {name:Mike, age:45}            |
|   nancy --> {name:Nancy, age:31}           |
|   oscar --> {name:Oscar, age:27}           |
+--------------------------------------------+

To look up key "dave":
  1. Check bloom filter: "is dave in this SSTable?" -> MAYBE
  2. Binary search index block: "charlie" <= "dave" < "mike" -> Data Block 2
  3. Read Data Block 2, scan for "dave" -> FOUND
  Total: 2 reads (index + data block), both sequential reads within the file
```

The **index block** is a sparse index — it does not index every key, just the first key of each data block. This keeps the index small enough to load into memory. To look up a key, you binary-search the index to find which data block to read, then read that single block.

### Bloom Filter Explained

The **bloom filter** is perhaps the most elegant data structure in storage engines. Before doing any disk reads, you ask the bloom filter: "Could this key possibly be in this SSTable?"

If the bloom filter says **NO**: the key is **definitely not** in this SSTable. Skip it entirely. Zero disk reads.

If the bloom filter says **YES**: the key **might** be in this SSTable. Read the index and data block to confirm.

The bloom filter can produce false positives (says YES when the key is not actually there) but never false negatives (if the key is there, it always says YES). This makes it safe to use as a filter — you might waste a read on a false positive, but you will never miss a key.

How does it work?

```
BLOOM FILTER: HOW IT WORKS
============================

Setup: a bit array of M bits, all initially 0.
       K independent hash functions.

Example: M=20 bits, K=3 hash functions (h1, h2, h3)

INITIAL STATE:
Position: 0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18 19
Bits:      0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0

ADD key "alice":
  h1("alice") = 2  --> set bit 2
  h2("alice") = 7  --> set bit 7
  h3("alice") = 14 --> set bit 14

Position: 0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18 19
Bits:      0  0  1  0  0  0  0  1  0  0  0  0  0  0  1  0  0  0  0  0
                 ^              ^                    ^
                 |              |                    |
              bit 2          bit 7               bit 14

ADD key "bob":
  h1("bob") = 4   --> set bit 4
  h2("bob") = 7   --> set bit 7 (already set, no change)
  h3("bob") = 11  --> set bit 11

Position: 0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18 19
Bits:      0  0  1  0  1  0  0  1  0  0  0  1  0  0  1  0  0  0  0  0

LOOKUP key "carol" (NOT in SSTable):
  h1("carol") = 3   --> bit 3 = 0 --> STOP. Bit is 0!
  Answer: carol is DEFINITELY NOT in this SSTable.
  (No disk read needed!)

LOOKUP key "alice" (IS in SSTable):
  h1("alice") = 2  --> bit 2 = 1 (continue)
  h2("alice") = 7  --> bit 7 = 1 (continue)
  h3("alice") = 14 --> bit 14 = 1 (continue)
  Answer: alice MIGHT be in this SSTable. (Read to confirm.)

FALSE POSITIVE example:
  Suppose h1("dave")=2, h2("dave")=4, h3("dave")=11
  --> bit 2 = 1 (set by alice)
  --> bit 4 = 1 (set by bob)
  --> bit 11 = 1 (set by bob)
  Answer: MIGHT be in SSTable -- but dave was never inserted!
  This is a false positive. We do a disk read and find dave is absent.

FALSE NEGATIVE: IMPOSSIBLE.
  If a key was inserted, all its bits were set to 1.
  Those bits can never go back to 0 (no deletions in bloom filter).
  So a key that was inserted will always be found.
```

In practice, Cassandra tunes bloom filters to have a false positive rate of about 1%. With 100 SSTables and a 1% false positive rate, a "key not found" lookup triggers on average one false positive read (instead of zero) while correctly skipping the other 99 SSTables. Without bloom filters, you would have to read all 100 SSTables.

### Read Path in LSM-Trees (Where It Is Slower Than B-Tree)

Now you understand why Cassandra reads can be slower than writes.

```
LSM-TREE READ PATH: key="user:alice"
=====================================

Step 1: Check MemTable (in memory)
  Is "user:alice" in the current MemTable?
  --> YES: return immediately (fastest possible case)
  --> NO: continue

Step 2: Check L0 SSTables (newest, in order from newest to oldest)
  For each L0 SSTable (there may be 4-10 of them):
    a. Check bloom filter: "might alice be here?"
       --> NO (definite): skip this SSTable
       --> YES (maybe): continue to b
    b. Load index block (may already be in memory/cache)
    c. Binary search index --> find data block
    d. Read data block from disk
    e. Search for "user:alice"
       --> FOUND: return value (done)
       --> NOT FOUND: continue to next SSTable

Step 3: Check L1 SSTables (older)
  Similar process, but L1 SSTables have non-overlapping key ranges.
  Binary search the L1 SSTable list to find which one could have alice.
  Check bloom filter --> maybe --> read index + data block.

Step 4: Check L2, L3... (progressively older)
  Same pattern.

WORST CASE: key does not exist anywhere.
  Must check bloom filter of every SSTable at every level.
  Most checks return "definitely no" (good).
  ~1% return "maybe" (false positives) --> wasted disk reads.

Read amplification = number of SSTable checks for one read
  MemTable: 1
  L0: up to 10 SSTables (overlapping key ranges)
  L1: 1 SSTable (non-overlapping)
  L2: 1 SSTable
  ...
  Total: typically 4-10 disk reads for one key

Compare to B-Tree: 4-6 reads for 1 billion rows.
B-Tree has lower read amplification. This is the fundamental tradeoff.
```

The read amplification gets worse as data ages and compaction falls behind. A system that is write-heavy and hasn't compacted recently might have 50+ SSTables across levels, making reads slow until compaction catches up.

### Compaction Strategies

Compaction is the process that keeps SSTables from multiplying forever. There are two main strategies, and they have very different tradeoffs.

**Strategy 1: Size-Tiered Compaction (STCS)**

In size-tiered compaction, SSTables are grouped by size. When enough same-size SSTables accumulate (typically 4), they are merged into one larger SSTable.

```
SIZE-TIERED COMPACTION
========================

Small SSTables (each ~10MB):
  [A: 10MB] [B: 10MB] [C: 10MB] [D: 10MB]
  --> 4 small SSTables accumulated
  --> COMPACT: merge into one medium SSTable

Medium SSTables (each ~40MB):
  [AB+CD: 40MB] [EF+GH: 40MB] [IJ+KL: 40MB] [MN+OP: 40MB]
  --> 4 medium SSTables accumulated
  --> COMPACT: merge into one large SSTable

Large SSTables (each ~160MB):
  [160MB] [160MB] [160MB] [160MB]
  --> COMPACT: one 640MB SSTable

PROBLEM: During compaction, key ranges OVERLAP across levels.
  L0 might have "alice" in 3 different SSTables (latest write wins).
  A read for "alice" must check all 3 to find the newest version.
```

Size-tiered compaction is write-friendly (compaction runs less often) but read-unfriendly (many overlapping SSTables to check) and temporarily doubles space usage during compaction.

**Strategy 2: Leveled Compaction (LCS)**

In leveled compaction, SSTables are organized into levels (L0, L1, L2...). Each level is about 10x larger than the previous level. Critically, within each level (except L0), no two SSTables have overlapping key ranges.

```
LEVELED COMPACTION
==================

L0 (newest, ~4 SSTables, overlapping key ranges allowed):
  [SST-A: keys a-z] [SST-B: keys a-z] [SST-C: keys a-z]
  (All cover the full key space -- newest 3 MemTable flushes)

L1 (10MB total, NO overlapping ranges):
  [SST-1: a-d] [SST-2: e-h] [SST-3: i-l] [SST-4: m-p] [SST-5: q-z]
  Each SSTable covers a distinct key range. NEVER overlaps.

L2 (100MB total, NO overlapping ranges):
  [SST-1: a-b] [SST-2: c-d] ... [SST-50: y-z]

L3 (1GB total, NO overlapping ranges):
  [SST-1: a] [SST-2: a-aa] ... many SSTables

HOW COMPACTION WORKS (L0 -> L1):
  When L0 has 4 SSTables:
  Pick one L0 SSTable (covers keys a-z)
  Find all L1 SSTables with overlapping key range (all of them: a-z)
  Merge: L0 SSTable + all overlapping L1 SSTables --> new L1 SSTables
  Result: L1 still has no overlapping ranges, but includes newest data.

READ BENEFIT:
  For key "alice" (in range a-d):
  L0: check all 4 SSTables (overlapping, must check all)
  L1: check ONLY [SST-1: a-d] (guaranteed, no other L1 SSTable has alice)
  L2: check ONLY one SSTable
  Total: much fewer SSTables than size-tiered

WRITE PENALTY:
  Every compaction moves data through multiple levels.
  A key inserted might move: L0 -> L1 -> L2 -> L3 -> L4
  Write amplification ~10x per level. High compaction overhead.
```

```
SIZE-TIERED vs LEVELED: SIDE BY SIDE
======================================

                    Size-Tiered          Leveled
                    -----------          -------
Write amplification Low (less compaction) High (more compaction)
Read amplification  High (overlapping)   Low (no overlap in L1+)
Space overhead      High (temp 2x)       Low (~10% extra)
Best for            Write-heavy          Read-heavy or mixed

Cassandra default: Size-tiered (matches write-heavy use case)
RocksDB default:   Leveled (matches read-heavy applications like MyRocks)
```

---

## 5. B-Tree vs LSM-Tree: The Full Comparison

This is the core comparison you need to internalize. At L6, you do not just pick one — you explain the exact tradeoff dimensions and how they interact with your specific workload.

| Dimension | B-Tree (PostgreSQL, MySQL) | LSM-Tree (Cassandra, RocksDB) |
|---|---|---|
| **Write path** | Random write to existing page | Sequential: MemTable + commit log |
| **Write amplification** | (1 + num_indexes) per write | Depends on compaction: 10-30x |
| **Read amplification** | Height of tree (4-6 reads) | Levels to check (4-10 reads) |
| **Read performance** | Excellent; single sorted structure | Good with bloom filters; worse under high write pressure |
| **Range scans** | Excellent; leaf linked list | Good; each SSTable is sorted, but multiple files to merge |
| **Write throughput ceiling** | ~200 rows/s on HDD (random IOPS limit) | ~100,000+ rows/s (sequential writes) |
| **Space amplification** | MVCC dead tuples accumulate without VACUUM | Compaction manages tombstones; less bloat |
| **Deletes** | Mark tuple as dead (MVCC); VACUUM reclaims space | Write a tombstone record; resolved at compaction |
| **Crash recovery** | WAL (Write-Ahead Log) replayed | Commit log replayed to rebuild MemTable |
| **Compaction cost** | N/A (in-place update) | Background compaction uses CPU and I/O |
| **Best workload** | Read-heavy, OLTP mixed, complex queries | Write-heavy, append-only, time-series |
| **Worst workload** | 100k+ writes/sec without SSD | Sporadic reads on rarely-compacted data |

**The SSD caveat.** Modern NVMe SSDs have changed the tradeoffs meaningfully. Random write penalty on NVMe is only 30x vs sequential (not 1000x). This means B-Trees can sustain much higher write throughput on NVMe than on HDDs. The gap between B-Trees and LSM-Trees narrows significantly on modern SSD-equipped servers. However:

- LSM-Trees still win on write throughput at extreme scale (millions of writes/second).
- B-Trees still win on read latency consistency (no compaction pauses, no SSTable proliferation).
- At L6, you always qualify your answer with the hardware assumption.

**The write-to-read ratio rule:**

```
Decision Framework:
  If writes >> reads  -->  LSM-Tree (Cassandra, RocksDB)
  If reads >> writes  -->  B-Tree (PostgreSQL, MySQL)
  If mixed (OLTP)     -->  B-Tree on SSD, tune indexes carefully
  If time-series/IoT  -->  LSM-Tree (append-heavy, rarely update old data)
```

---

## 6. Real Incident: Write Amplification Took Down the Database

This incident follows a pattern that appears repeatedly in real production systems. The details are fictionalized, but the failure mode is real.

**Company:** A high-frequency trading platform. The system recorded every trade, order, and market data tick in a PostgreSQL database to support real-time risk dashboards and end-of-day reconciliation.

**Setup:**
- Single PostgreSQL 14 primary with one read replica
- The `trades` table had 12 secondary indexes:
  - ticker symbol, trader_id, desk_id, exchange, strategy_id, trade_date, settlement_date, instrument_type, counterparty_id, book_id, portfolio_id, and status
- Normal write volume: 15,000 inserts per second during market hours

**The trigger:** Market volatility spiked. Trade volume doubled — 30,000 inserts per second instead of 15,000.

**What happened:**

```
WRITE AMPLIFICATION MATH:
  Indexes: 12
  Write amplification: 1 heap + 12 indexes = 13 writes per insert
  Normal: 15,000 inserts/s × 13 = 195,000 random page writes/s
  Spike:  30,000 inserts/s × 13 = 390,000 random page writes/s

  Their disk: NVMe SSD rated for 200,000 IOPS random write
  Normal: 195,000 IOPS  --> 97.5% of disk limit (dangerous!)
  Spike:  390,000 IOPS  --> 195% of disk limit (SATURATED)
```

At disk saturation, PostgreSQL's write queue backed up. Transactions that normally committed in 5ms began taking 500ms, then 5 seconds, then timing out entirely. The application connection pool filled up with waiting connections. Within 3 minutes of the spike, the application returned errors for every write. The risk dashboard showed stale data. Trading systems began failing health checks.

**Investigation:**

After the spike subsided and the database recovered, the engineering team ran:

```sql
-- Find indexes that are never used for reads:
SELECT
  schemaname,
  tablename,
  indexname,
  idx_scan AS times_used_for_reads,
  idx_tup_read,
  idx_tup_fetch
FROM pg_stat_user_indexes
WHERE tablename = 'trades'
ORDER BY idx_scan ASC;

-- Result showed 7 of 12 indexes had idx_scan = 0
-- These indexes had NEVER been used in a query
-- but were being maintained on every single INSERT
```

They also ran EXPLAIN ANALYZE on an INSERT to confirm:

```sql
EXPLAIN (ANALYZE, BUFFERS) INSERT INTO trades VALUES (...);

-- Output showed:
-- Insert on trades  (actual time=0.045..15.234 rows=1 loops=1)
--   Buffers: shared hit=3 read=2 written=13
-- The "written=13" meant 13 buffer pages written per insert
-- This confirmed all 12 indexes were being updated
```

**The fix:**

The team identified which 7 indexes had zero reads (`idx_scan = 0` in `pg_stat_user_indexes`). These were indexes created "just in case" over several years. They dropped them:

```sql
DROP INDEX CONCURRENTLY idx_trades_settlement_date;
DROP INDEX CONCURRENTLY idx_trades_instrument_type;
DROP INDEX CONCURRENTLY idx_trades_counterparty_id;
-- (4 more drops)
```

`CONCURRENTLY` is critical here — it drops the index without locking the table, so writes can continue during the drop.

After dropping 7 indexes:

```
WRITE AMPLIFICATION AFTER FIX:
  Indexes: 5 (12 - 7 dropped)
  Write amplification: 1 heap + 5 indexes = 6 writes per insert
  At 30,000 inserts/s: 180,000 IOPS  --> 90% of disk limit (manageable)
  Write latency: back to <10ms even at peak volume
```

The same hardware, the same query volume, the same peak write rate — but with 7 fewer unused indexes, the system handled the doubled load without saturation.

**The lesson:**

Index count × write rate = your actual disk I/O. Not row count. Not query complexity. The number of indexes on your highest-write table is the single most important factor in your write throughput ceiling.

Practical rules derived from this incident:
1. Run `pg_stat_user_indexes` monthly. Drop any index where `idx_scan` has not grown in 30 days and the table is write-heavy.
2. Never add an index without first checking write amplification math.
3. Monitor disk IOPS utilization, not just CPU and memory. Disk saturation looks like high query latency at normal write rates — it is easy to misdiagnose as a slow query when it is actually a disk I/O problem.
4. When a write spike is expected (sales events, market volatility), verify your index count is minimal beforehand.

---

## Chapter Summary: What to Say in an L6 Interview

When an interviewer asks about database performance under load, here is the framework to use:

**For B-Tree questions (PostgreSQL, MySQL):**
- State the page size (8KB) and fan-out (~300 for integers)
- State the tree height formula: `log₃₀₀(N)` — 4-5 reads for 1 billion rows
- State write amplification: `(1 + num_indexes)` writes per insert
- Mention the leaf page linked list for range scans
- Know that updates in MVCC write a new tuple, causing table bloat without VACUUM

**For LSM-Tree questions (Cassandra, RocksDB):**
- State the four stages: MemTable, commit log, SSTable flush, compaction
- State that writes are sequential (fast) and reads are read-amplified (multiple SSTables)
- Explain bloom filters: definite NO, probable YES, 1% false positive rate
- Know the two compaction strategies: size-tiered (write-friendly) vs leveled (read-friendly)
- Know that read amplification = number of SSTables to check

**For the comparison:**
- Lead with the hardware constraint: random I/O is expensive
- B-Tree minimizes random reads; LSM-Tree eliminates random writes
- Write-heavy → LSM; Read-heavy → B-Tree; on NVMe the gap narrows
- For hybrid workloads, consider tuning (index count for B-Tree, compaction tuning for LSM)

Part B of this chapter covers MVCC and transaction internals — how databases isolate concurrent transactions, what "read committed" vs "serializable" actually means at the page level, and why phantom reads happen even with row-level locks.

---

*End of Chapter 29, Part A.*
# Chapter 29: Database Internals Deep Dive
## Part B: Write-Ahead Log (WAL) and Crash Recovery Internals

---

## Table of Contents

1. The Crash Recovery Problem
2. What WAL Is: The Core Idea
3. The Write Path: How Every Write Flows
4. Crash Recovery: Replaying the WAL
5. Checkpoints: The "You Can Stop Here" Marker
6. WAL and Replication: The Same Log, Different Use
7. WAL Durability Modes: The fsync Tradeoff
8. WAL Segment Management
9. Point-in-Time Recovery (PITR)
10. Real Incident: WAL Directory Filled Disk, Database Halted
11. WAL in Other Databases

---

## 1. The Crash Recovery Problem

### What Actually Happens When You "Save" Data

Let's start from the very beginning. When you write data to a database, the database eventually needs to write that data to a disk — a hard drive or SSD. That's what makes data survive after you turn the computer off. Easy enough.

But here is the uncomfortable truth: writing to disk is not instant, and it is not atomic. "Atomic" means "either it happens completely or it doesn't happen at all." When you write a 16KB data page to disk, the operating system and disk controller break that into smaller writes. Your machine could lose power after the first 4KB made it to disk but before the remaining 12KB got there. Now you have a partial write — half of a page sitting on disk in a broken, inconsistent state.

This is not a theoretical problem. Power outages happen. OS kernels crash. Hardware fails. If your database doesn't have a mechanism to deal with partial writes, users will come back the next morning to find their data corrupted, and there is no way to know which writes completed and which didn't.

### The Two Naive Approaches and Why They Both Fail

Before we get to the solution, let's look at what you might naively try.

**Naive Approach 1: Write Synchronously to Disk Every Time**

Every time a user's transaction commits, you immediately write the changed data pages to disk and wait — completely blocked — until the disk confirms the write is done. Then you tell the user "success."

- Correctness: perfect. If the machine crashes, the committed data is on disk.
- Performance: terrible. A hard disk takes ~5 milliseconds to complete a write (seek time + rotation). That's 5ms per transaction. At 200 transactions per second, you are spending the entire disk's time just writing. Modern applications need tens of thousands of transactions per second. This approach doesn't scale.

**Naive Approach 2: Write Only to Memory, Flush Later**

Keep all changes in memory. Periodically (say, every second), flush dirty pages to disk in the background. Tell the user "success" immediately after writing to memory.

- Performance: excellent. Memory writes are nanoseconds. Users get responses instantly.
- Correctness: catastrophic. If the machine crashes in that one-second window, every transaction from the last second is gone. Users think their data was saved. It wasn't. They'll never trust your system again.

Neither approach is acceptable. We need something that is both fast AND durable. That's what the Write-Ahead Log solves.

### The Surgeon's Checklist Analogy

Surgeons use checklists. Before making any incision, the surgical team runs through a checklist: patient identity confirmed, correct site marked, allergies reviewed, equipment count done. They write down every step before doing it.

Why? Because if something goes wrong mid-surgery, you need to know exactly where you were. The checklist tells you: "We confirmed the patient, we marked the site, but we haven't done the equipment count yet." You can recover from that known state.

The Write-Ahead Log works exactly the same way. Before the database makes any change to its actual data files, it writes a record of the intended change to a log. "I am about to update row 47 in the orders table from status='pending' to status='shipped'." If the machine crashes mid-update, the database reads the log on restart and knows exactly what happened and what didn't. It can recover.

The WAL is the surgical checklist. The data files are the patient. The rule: **always write in the log first, then do the surgery**.

---

## 2. What WAL Is: The Core Idea

### The Fundamental Rule

**Write-Ahead Log (WAL)** is a file (or series of files) that records every intended change to the database, in order, before applying those changes to the actual data files.

The rule is simple but must never be violated:

> Never modify the actual data file until the WAL record for that modification is safely written to disk.

"Safely" means the OS has confirmed the data is on physical storage, not just in some memory buffer. This is what `fsync()` is for — we'll cover it later.

If you follow this rule, you always have a log that describes what the database "meant" to do, even if the actual data files never got updated. Recovery becomes: read the log, figure out what committed, apply it.

### Why Sequential Writes Are the Secret Weapon

Random writes to disk are slow. A hard disk's read/write head has to physically move to the right location on the platter (seek time, ~3-9ms). If you're updating rows scattered across many pages, each update needs the head to jump around. Painful.

**Sequential writes are fast** because the head doesn't move — it just keeps writing forward. Appending to a log is the most sequential write pattern possible. Every new WAL record goes at the end. No seeking. Just forward progress.

On a spinning disk, sequential writes can be 10-100x faster than random writes. Even on SSDs, sequential writes reduce write amplification and wear. This is why writing to the WAL first is not just correct — it's also often faster than writing directly to data files.

### WAL Record Structure

Every entry in the WAL is called a **WAL record**. Each record contains:

| Field | Description | Example |
|-------|-------------|---------|
| LSN | Log Sequence Number — unique, monotonically increasing position in the WAL | `0/1A2B3C40` |
| Transaction ID | Which transaction made this change | `txid 7842` |
| Record Type | What kind of change this is | `INSERT`, `UPDATE`, `DELETE`, `COMMIT`, `ABORT`, `CHECKPOINT` |
| Relation | Which table/index was modified | `orders (oid 16384)` |
| Block Number | Which page within the table file | `page 42` |
| Old Value | The before-image of the row (for undo) | `{status: 'pending'}` |
| New Value | The after-image of the row (for redo) | `{status: 'shipped'}` |
| Length | How many bytes this record occupies | `128 bytes` |

The **LSN (Log Sequence Number)** is especially important. It is a 64-bit integer that represents a byte offset into the WAL. LSN `0/1A2B3C40` means "byte position 0x1A2B3C40 in the WAL stream." It always increases. You can compare two LSNs to know which came first. Every page in the database also stores the LSN of the most recent WAL record that modified it — this lets recovery know whether a page is up to date.

### ASCII Diagram: WAL File Structure

```
WAL File (sequential, append-only)
+--------------------------------------------------+
| Segment 000000010000000000000001 (16 MB)          |
|  +----------+----------+----------+----------+    |
|  | Record 1 | Record 2 | Record 3 | Record 4 |    |
|  | LSN:001  | LSN:002  | LSN:003  | LSN:004  |    |
|  | txid:100 | txid:100 | txid:101 | txid:100 |    |
|  | INSERT   | INSERT   | UPDATE   | COMMIT   |    |
|  | orders   | orders   | users    |          |    |
|  +----------+----------+----------+----------+    |
|  | Record 5 | Record 6 |  ....                    |
|  | LSN:005  | LSN:006  |                          |
|  | txid:101 | txid:102 |                          |
|  | ABORT    | CHECKPOINT                          |
|  +----------+----------+                          |
+--------------------------------------------------+
| Segment 000000010000000000000002 (16 MB)          |
|  +----------+----------+  ...                     |
|  | Record 7 | Record 8 |                          |
|  | LSN:007  | LSN:008  |                          |
|  +----------+----------+                          |
+--------------------------------------------------+

                     [records grow this way --->]
```

Notice: WAL records are appended in order. You never go back and change an earlier record. This is why recovery works — the log is an immutable historical record.

---

## 3. The Write Path: How Every Write Flows

### The Architecture Before WAL

To understand the write path, you need to know two key memory structures in PostgreSQL:

1. **Shared Buffer Pool**: a large chunk of shared memory (often 25% of RAM) where PostgreSQL caches database pages. When you read or write a row, the page containing that row is loaded here. Modifying a page in the buffer pool makes it "dirty" (different from what's on disk).

2. **WAL Buffer**: a smaller chunk of memory where WAL records are assembled before being flushed to the WAL files on disk. Typically 4-64MB.

Both of these are in RAM. RAM is fast. Disk is slow. The whole trick of WAL is knowing exactly when each piece must reach disk.

### The Six Steps of a Write

Let's trace exactly what happens when a client sends `INSERT INTO orders (id, status) VALUES (999, 'pending')`:

**Step 1: Client sends the INSERT**

The client sends the SQL to PostgreSQL over a TCP connection. The PostgreSQL backend process receives it and parses it.

**Step 2: Database writes a WAL record to the WAL buffer**

PostgreSQL generates a WAL record describing the INSERT: "At LSN X, transaction 7842, insert this row into the orders table at page 42." This record is placed in the WAL buffer — still in memory. Nothing has hit disk yet.

**Step 3: Database modifies the page in the shared buffer pool**

PostgreSQL finds the correct page in the shared buffer pool (or loads it from disk if it's not cached). It applies the INSERT to that in-memory page. The page is now "dirty" — it's been modified in RAM but the disk still has the old version.

**Step 4: At COMMIT — WAL buffer is flushed to disk**

This is the critical moment. When the transaction commits, PostgreSQL calls `fsync()` on the WAL buffer. This forces the operating system to actually write those WAL records to the physical disk and confirm it. The database blocks — it waits for the disk to confirm — until this is done.

**This is the durability moment.** Once the WAL record of COMMIT is on disk, the transaction is durable. The data is safe. Even if the machine crashes one millisecond later, the WAL on disk can recreate the committed state.

**Step 5: Client receives success**

Only after the WAL is confirmed on disk does PostgreSQL send "INSERT 0 1" back to the client. The client sees success. From the client's perspective, the data is saved.

**Step 6: Later (async) — background writer flushes dirty pages**

Sometime later — could be milliseconds, could be seconds — a background process called the **bgwriter** wakes up and writes dirty pages from the shared buffer pool to the actual data files on disk. This is asynchronous. The client doesn't wait for this.

The key insight: **the data files on disk can be behind**. The data files might not have the committed data yet. That's totally fine because the WAL is already on disk and the WAL is the authoritative record. If the machine crashes between steps 5 and 6, recovery will replay the WAL and bring the data files up to date.

### ASCII Diagram: Memory vs Disk After a Commit

```
AFTER STEP 5 (client received success, bgwriter hasn't run yet):

MEMORY (RAM):                         DISK:
+---------------------------+         +---------------------------+
| Shared Buffer Pool        |         | WAL Files                 |
|  +---------+              |         |  +---------+---------+    |
|  | Page 42 | <-- DIRTY   |         |  | LSN 001 | LSN 002 |    |
|  | (has    |              |   ====> |  | INSERT  | COMMIT  |    |
|  | new row)|              |         |  | txid100 | txid100 |    |
|  +---------+              |         |  +---------+---------+    |
|                           |         |  [WAL on disk - SAFE]     |
+---------------------------+         +---------------------------+
                                      +---------------------------+
| WAL Buffer (empty after flush)      | Data Files                |
+---------------------------+         |  +---------+              |
|   [flushed to disk]       |         |  | Page 42 | <-- OLD!    |
+---------------------------+         |  | (missing|              |
                                      |  | new row)|              |
                                      |  +---------+              |
                                      |  [data file stale - OK!]  |
                                      +---------------------------+

If machine crashes here:
  - WAL is on disk (COMMIT is recorded)
  - Data file is stale (missing the new row)
  - On restart: PostgreSQL replays WAL -> re-applies INSERT to data file
  - Result: consistent, no data loss
```

This diagram is the heart of WAL. The data file being stale is intentional and safe. The WAL is the source of truth.

---

## 4. Crash Recovery: Replaying the WAL

### What "Crash" Actually Means

A crash can be many things: power outage, kernel panic, process killed with SIGKILL, hardware failure. What they all have in common: PostgreSQL stops without going through its normal shutdown sequence. The in-memory state (shared buffer pool, WAL buffer, anything in RAM) is gone instantly. Only what was on disk survives.

### The Recovery Algorithm

When PostgreSQL starts after a crash, it runs its crash recovery algorithm before accepting any connections. Here's what it does:

**Phase 1: Find the last checkpoint**

PostgreSQL reads its **control file** (`pg_global/pg_control`), which records the location of the last checkpoint. A checkpoint is a known-good point where all dirty pages were flushed to disk (more on this in section 5). Recovery starts from there.

**Phase 2: Redo — replay all WAL from the checkpoint forward**

PostgreSQL reads WAL records starting at the checkpoint LSN and applies them to the data files, in order:

- For each WAL record, it looks at the LSN on the affected page
- If the page's LSN is less than the WAL record's LSN, the change was not yet written to the data file — apply it (redo)
- If the page's LSN is already >= the WAL record's LSN, the change was already written — skip it (idempotent)

This replay continues until PostgreSQL reaches the end of the WAL.

**Phase 3: Undo — rollback uncommitted transactions**

After replaying all WAL, PostgreSQL checks which transactions were in-progress at the time of the crash (transactions that have a BEGIN but no COMMIT or ABORT in the WAL). For those transactions, it uses the "old value" fields in the WAL records to reverse their changes. This is the **undo** phase.

Result: the database is in a state that reflects exactly all committed transactions and none of the uncommitted ones. Clean.

### Redo vs Undo: A Concrete Example

Imagine two transactions were running when the machine crashed:

```
Transaction A:
  LSN 001: BEGIN       txid 100
  LSN 002: INSERT row  txid 100  (orders, row 999)
  LSN 003: COMMIT      txid 100   <-- committed!

Transaction B:
  LSN 004: BEGIN       txid 101
  LSN 005: UPDATE row  txid 101  (users, row 42, balance: 500 -> 450)
  [CRASH -- no COMMIT record for txid 101]
```

Recovery finds the checkpoint was before LSN 001. It replays LSN 001-005:

- LSN 002 (INSERT for txid 100): data file page didn't have this — REDO it. Apply the insert.
- LSN 003 (COMMIT for txid 100): mark txid 100 as committed.
- LSN 005 (UPDATE for txid 101): data file page didn't have this — REDO it. Apply the update temporarily.

Then undo phase: txid 101 has no COMMIT. Use LSN 005's "old value" (balance: 500) to reverse the change. Users row 42 goes back to balance: 500.

Final state: orders has row 999 (committed). Users row 42 has balance 500 (rolled back). Perfectly consistent.

### ASCII Diagram: Crash Recovery Timeline

```
Timeline:

  [Checkpoint]          [Crash]              [Restart complete]
       |                   |                         |
       v                   v                         v
-------+-------------------+-----     --------------+---------->
       |                   |                         |
       |<--- WAL on disk --|                         |
       |    LSN 001-005    |                         |
       |                   |                         |
       |    Data files:    |    Recovery reads WAL:  |
       |    stale after    |    REDO 001,002,003,005 |
       |    checkpoint     |    UNDO 005 (no commit) |
                                                     |
                                              Database open,
                                              accepting connections

Checkpoint LSN: "start replaying from here"
End of WAL:    "stop replaying here"
Undo:          "rollback these in-progress transactions"
```

The recovery is completely automatic. You don't write any recovery scripts. PostgreSQL handles it every time it starts after a non-clean shutdown. This is why databases can advertise "crash-safe" durability guarantees.

---

## 5. Checkpoints: The "You Can Stop Here" Marker

### The WAL Growth Problem

If PostgreSQL keeps appending WAL records forever and never deletes old ones, the WAL directory will grow without bound. A busy database producing 1GB/hour of WAL would fill a disk in days. We need a way to say "everything before this point is safely on disk — we don't need that old WAL for recovery anymore."

That mechanism is the **checkpoint**.

### What a Checkpoint Is

A **checkpoint** is a moment in time at which PostgreSQL guarantees that all dirty pages in the shared buffer pool have been written to the data files on disk. After a checkpoint, if the machine crashes, recovery only needs to replay WAL from that checkpoint forward — everything before it is already reflected in the data files.

Think of a checkpoint like saving your game. You can die after the save point and just restart from there — you don't have to replay the entire game from the beginning.

### The Checkpoint Process, Step by Step

**Step 1:** PostgreSQL writes a CHECKPOINT record to the WAL. This record says "a checkpoint is starting, and the WAL position is X."

**Step 2:** PostgreSQL flushes all dirty pages from the shared buffer pool to the data files. This means writing every modified page that hasn't been written yet to disk. This is **the expensive part** — potentially gigabytes of I/O happening at once.

**Step 3:** PostgreSQL calls `fsync()` to make sure those data file writes are physically on disk, not just in OS cache.

**Step 4:** PostgreSQL updates the **control file** (`pg_global/pg_control`) with the LSN of this checkpoint. The control file is what tells crash recovery "start replaying from here."

**Step 5:** WAL segments before the checkpoint are now safe to delete or recycle (unless needed for replication or archiving — more on that later).

### Why Checkpoints Cause Latency Spikes

This is a classic mystery that trips up many engineers running PostgreSQL in production. Suddenly, at regular intervals, query latency spikes — p99 goes from 10ms to 200ms. No obvious cause. Then it drops back down. Repeat every 5 minutes.

The cause: **checkpoint I/O spike**.

PostgreSQL has two relevant settings:

```
checkpoint_timeout = 5min          # how often to force a checkpoint
checkpoint_completion_target = 0.9 # try to spread I/O over 90% of the interval
```

If `checkpoint_timeout` is 5 minutes and `checkpoint_completion_target` is 0.9, PostgreSQL tries to spread the checkpoint's dirty-page writes over 4.5 minutes (90% of 5). This smooths out the I/O.

But there's another setting:

```
max_wal_size = 1GB  # trigger a checkpoint if WAL grows beyond this
```

If WAL grows faster than expected (big batch job, high write volume), an **emergency checkpoint** fires before the timeout. Emergency checkpoints don't spread their I/O — they flush everything at once. Your disk is suddenly hammered. Latency spikes. Mystery solved.

**The background writer's role**: The **bgwriter** background process continuously writes dirty pages to disk between checkpoints, trying to "pre-flush" pages so the checkpoint has less work to do. If bgwriter is configured too conservatively and can't keep up, checkpoints have to flush more pages. The relevant setting:

```
bgwriter_lru_maxpages = 100      # max pages bgwriter writes per round
bgwriter_delay = 200ms           # how often bgwriter wakes up
```

### ASCII Diagram: Dirty Pages Between Checkpoints

```
Time -->
|
|  [Checkpoint A]                            [Checkpoint B]
|       |                                         |
|       |  Dirty pages build up in buffer pool    |
|       |  as writes come in:                     |
|       |                                         |
|       |  Page 1 dirtied  ~~                     |
|       |  Page 2 dirtied    ~~                   |
|       |  Page 3 dirtied      ~~                 |
|       |                        ~~               |
|       |  bgwriter flushes some  ~~              |
|       |  pages early (pre-flush)  ~~            |
|       |                             ~~          |
|       |  Pages not yet flushed:       [FLUSH!]--+
|       |                               all dirty |
|       |                               pages to  |
|       |                               data files|
|       |                                         |
|       |<-------- checkpoint_timeout (5min) ---->|
|       |<-- checkpoint_completion_target=0.9 --->|
|       |    (spread I/O over 4.5 minutes)        |
|
| With bad config (or emergency checkpoint):
|       |                              [!!SPIKE!!]|
|       |                              (all I/O   |
|       |                              at once)   |
```

**Tuning advice for L6 interviews**: If you see regular latency spikes in PostgreSQL, first check if checkpoints are the cause using `log_checkpoints = on`. The log will show "checkpoint starting" and "checkpoint complete" with I/O statistics. If checkpoints are the culprit, increase `checkpoint_completion_target` toward 1.0, increase `checkpoint_timeout`, or tune bgwriter to flush more aggressively between checkpoints.

---

## 6. WAL and Replication: The Same Log, Different Use

### Replication Is Not a Separate System

Here is something that surprises many people: PostgreSQL replication is not a separate system built on top of the database. It literally reuses the WAL. The same WAL records that provide crash recovery are streamed to replicas. There is no separate "replication protocol" inventing a new way to describe changes.

This is elegant. The WAL is already a complete, ordered description of every change. Replicas just need to receive those records and apply them.

### How Streaming Replication Works

**On the primary:**
- Normal writes produce WAL records into the WAL buffer
- WAL buffer is flushed to WAL files on disk (for durability)
- Additionally, a **walsender** process on the primary reads the WAL and streams it over TCP to replicas

**On the replica:**
- A **walreceiver** process receives the WAL stream from the primary
- It writes the received WAL to the replica's own WAL files
- A **startup process** (or **wal_apply** process in newer versions) reads those WAL files and applies the records to the replica's data files

The replica is always "playing catch-up" with the primary. It's doing exactly what crash recovery does — replaying WAL records — but continuously, while the primary is still running.

### Replication Lag

**Replication lag** is how far behind the replica is from the primary. It's measured in bytes (how many bytes of WAL the replica hasn't applied yet) or time (how old is the most recently applied transaction on the replica).

You can see replication state from the primary:

```sql
SELECT
    application_name,
    sent_lsn,      -- how far primary has SENT to the replica
    write_lsn,     -- how far replica has WRITTEN to its WAL files
    flush_lsn,     -- how far replica has FLUSHED to disk
    replay_lsn,    -- how far replica has APPLIED to its data files
    write_lag,     -- time lag for write_lsn
    flush_lag,     -- time lag for flush_lsn
    replay_lag     -- time lag for replay_lsn (most important!)
FROM pg_stat_replication;
```

The four LSN values tell you where in the pipeline the replica is:
- `sent_lsn`: primary has sent this WAL to the replica over TCP
- `write_lsn`: replica's walreceiver has written it to replica's WAL files
- `flush_lsn`: replica's walreceiver has fsynced it to disk
- `replay_lsn`: replica's apply process has actually applied it to data files

**Why lag matters for your application**: If `replay_lag` is 5 seconds, a read from the replica might return data that's 5 seconds old. If your application reads its own writes from a replica immediately after writing to the primary, it might see stale data. This is a fundamental property of asynchronous replication.

### ASCII Diagram: WAL Streaming Replication

```
PRIMARY:                                      REPLICA:
                                              
+----------------+                           +----------------+
| Client writes  |                           |                |
|   INSERT/UPDATE|                           |                |
+-------+--------+                           +----------------+
        |                                              ^
        v                                              | (applies WAL)
+----------------+                           +----------------+
| WAL Buffer     |                           | Startup/Apply  |
| (in memory)    |                           | Process        |
+-------+--------+                           +------+---------+
        |                                           ^
        | fsync (durability)                        | (reads replica WAL)
        v                                           |
+----------------+    walsender     walreceiver +--+-------------+
| WAL Files      | ------TCP------> WAL Files  |                |
| on disk        |   (streaming)   on disk     | Replica WAL    |
|                |                             | Files on disk  |
+----------------+                             +----------------+
        |
        | (bgwriter, async)
        v
+----------------+
| Data Files     |
| on disk        |
+----------------+

Lag = primary's current LSN - replica's replay_lsn
```

### Synchronous vs Asynchronous Replication

By default, replication is **asynchronous**: the primary commits and returns to the client without waiting for the replica to receive or apply the WAL. If the primary crashes, the replica may be missing the last few transactions.

**Synchronous replication** (`synchronous_standby_names` setting): the primary waits for one or more replicas to confirm they have written (and optionally fsynced) the WAL before returning success to the client. This eliminates the data loss window but adds network latency to every commit. A write from New York to a synchronous replica in California adds ~70ms of round-trip time to every transaction.

---

## 7. WAL Durability Modes: The fsync Tradeoff

### The Role of fsync

When PostgreSQL calls `fsync()` on the WAL buffer, it asks the operating system: "Please make sure this data is actually on the physical storage device, not just in your OS page cache." The OS then flushes its cache to disk and waits for the disk controller to confirm the write.

The `fsync` call is what costs time. It's the "waiting for the disk" part. Without it, PostgreSQL would be trusting the OS to eventually write the data — which it will, unless the machine crashes before it gets around to it.

### Durability Mode Comparison

| Setting | Where WAL lives after commit | Survives power failure? | Performance cost |
|---------|------------------------------|------------------------|-----------------|
| `fsync=on` (default) | Physical disk | Yes | High (disk latency per commit) |
| `fsync=off` | OS page cache (maybe disk) | No | Low (no fsync penalty) |
| `synchronous_commit=off` | OS page cache | No (last ~200ms lost) | Low (async WAL flush) |
| `synchronous_commit=local` | Local disk only | Yes (local) | Medium |
| `synchronous_commit=remote_write` | Primary + replica disk | Yes | High + network RTT |

### fsync=on (Default, Safe)

With `fsync=on`, PostgreSQL calls `fsync()` after flushing the WAL buffer on every commit. The commit blocks until the disk confirms. If the machine loses power, the WAL is guaranteed to be on the physical disk. Nothing is lost.

The cost: every HDD write involves a seek (move the head) and rotation (wait for the right sector). That's ~5ms per fsync. SSDs are faster but still have a flush penalty. At high transaction rates, this adds up.

```
postgresql.conf:
  fsync = on     # default, recommended for production
```

### fsync=off (Dangerous)

With `fsync=off`, PostgreSQL does not call `fsync()`. WAL writes go to the OS page cache. They'll eventually reach disk, but if the machine crashes before that, the WAL records are lost.

Worse: if WAL records are lost but some data file pages were already written (by bgwriter), the data files will be in an inconsistent state with no way to recover. This can cause database corruption.

```
postgresql.conf:
  fsync = off    # NEVER in production. Only for throwaways (CI, temp dev environments)
```

### synchronous_commit=off (Useful Middle Ground)

This is a per-transaction setting (can be set per session). When `synchronous_commit=off`, the database returns success to the client before the WAL buffer has been fsynced. The WAL flush happens asynchronously in the background, typically within 200ms (controlled by `wal_writer_delay = 200ms`).

Risk: if the machine crashes in that 200ms window, the last batch of transactions is lost. But — critically — **the database remains consistent**. There's no corruption. The loss is clean: you lose some committed transactions, but what's on disk is a valid consistent state.

Use case: high-frequency inserts where you can tolerate losing the last few events. Think: metrics ingestion, clickstream logging, audit logs for low-sensitivity events. Losing 100 log entries is acceptable; losing user financial data is not.

```sql
-- Per-transaction:
SET synchronous_commit = off;
INSERT INTO clickstream_events (user_id, page, ts) VALUES (42, '/home', now());
COMMIT;  -- returns immediately, WAL may not be on disk yet
```

### commit_delay and Group Commit

One more optimization: `commit_delay` (default: 0). If set to N microseconds, PostgreSQL waits N microseconds after writing WAL before calling `fsync()`. During that wait, other transactions completing their writes can "join" the same fsync. One fsync serves multiple transactions — **group commit**. This dramatically improves throughput when many transactions commit at nearly the same time.

---

## 8. WAL Segment Management

### Segments: How WAL Is Organized on Disk

The WAL is not one giant file. It's divided into **segments**, each 16MB by default (configurable at `initdb` time with `--wal-segsize`). Each segment is a separate file in the `pg_wal/` directory.

Segment filenames look like:

```
000000010000000000000001
000000010000000000000002
000000010000000000000003
...
```

The filename is a 24-character hex string divided into three parts:
- `00000001`: **Timeline ID** (increases after PITR recovery — more on this later)
- `000000000000000`: **High 32 bits** of the segment number
- `00000001`: **Low 32 bits** of the segment number

So `000000010000000000000001` is timeline 1, WAL segment 1. The next is `000000010000000000000002`, and so on. At 16MB per segment, a database writing 1GB/hour produces about 64 segments per hour.

### Segment Lifecycle

```
WAL directory (pg_wal/):

  [New segments]                 [Old segments]
  000000010000000000000099   <-- current write position
  000000010000000000000098   <-- recently written
  000000010000000000000097
  ...
  000000010000000000000050   <-- last checkpoint was here
  ...
  000000010000000000000001   <-- old, can be recycled

After checkpoint at segment 50:
  Segments 1-49 are no longer needed for crash recovery.
  PostgreSQL either:
    (a) Deletes them  (if wal_keep_size allows)
    (b) Renames/recycles them as future segment names (saves disk alloc time)
    (c) Archives them first if archive_mode = on (PITR)
```

### WAL Explosion: Three Ways Your Disk Fills Up

**Cause 1: Replication Slot Holding WAL**

A **replication slot** is a mechanism that tells the primary: "Keep all WAL that this replica needs, even if the replica is offline." This prevents data loss when a replica reconnects after a pause.

The problem: if the replica stays offline for a long time, the primary accumulates WAL indefinitely. There's no limit by default.

```sql
-- See what's holding WAL:
SELECT slot_name, restart_lsn, pg_current_wal_lsn() - restart_lsn AS lag_bytes
FROM pg_replication_slots;
```

Fix: set a limit.

```
postgresql.conf:
  max_slot_wal_keep_size = 10GB  # drop the slot if it falls behind by more than 10GB
```

**Cause 2: Long-Running Transaction**

If a transaction has been open for 3 hours, PostgreSQL must keep all WAL from the start of that transaction (it might need it for undo). A transaction that runs `BEGIN` and then just sits there will cause WAL accumulation.

```sql
-- Find long-running transactions:
SELECT pid, now() - xact_start AS duration, query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY duration DESC;
```

**Cause 3: Archive Mode Backpressure**

If `archive_mode = on` and the archive command is failing or slow, PostgreSQL won't delete WAL segments that haven't been archived. WAL piles up.

```
postgresql.conf:
  archive_mode = on
  archive_command = 'cp %p /mnt/archive/%f'  # if /mnt/archive is full, this fails
```

Monitor `pg_stat_archiver` for `last_failed_time` and `last_failed_wal`.

### Monitoring WAL Health

```sql
-- WAL generation rate:
SELECT pg_walfile_name(pg_current_wal_lsn()), pg_wal_lsn_diff(pg_current_wal_lsn(), '0/0'::pg_lsn) / 1024 / 1024 AS wal_mb;

-- Replication slot lag:
SELECT slot_name, active, restart_lsn,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS lag
FROM pg_replication_slots;

-- Archive status:
SELECT * FROM pg_stat_archiver;
```

---

## 9. Point-in-Time Recovery (PITR)

### The Problem PITR Solves

Imagine a junior developer runs this at 14:37 on a Friday:

```sql
DELETE FROM orders;  -- forgot the WHERE clause
COMMIT;
```

Your database is now empty. The deletion is committed — crash recovery won't undo it. Your nightly backup from last night restores to yesterday's state, losing 14 hours of orders. You need to restore to exactly 14:36 — one minute before the deletion.

**Point-in-Time Recovery (PITR)** lets you restore a database to any specific moment in time, provided you have:
1. A base backup taken before that moment
2. All WAL segments from that base backup to the target time

### How PITR Works

**Step 1: Take a base backup**

A base backup is a consistent snapshot of all data files. PostgreSQL provides `pg_basebackup` for this:

```bash
pg_basebackup \
  --host=primary-db \
  --username=replication_user \
  --pgdata=/backup/base/ \
  --wal-method=stream \
  --progress \
  --verbose
```

This creates a snapshot of all data files at a point in time. It also includes the WAL generated during the backup itself (so the backup is self-consistent).

You should take base backups regularly — daily is common for moderate databases. The base backup defines how far back you can go in time. If your oldest base backup is from 30 days ago, you can restore to any point in the last 30 days (as long as you have the WAL).

**Step 2: Archive WAL continuously**

While the database runs, every completed WAL segment must be archived to a safe location (separate from the primary):

```
postgresql.conf:
  archive_mode = on
  archive_command = 'aws s3 cp %p s3://my-db-wal-archive/%f'
```

`%p` is the path to the WAL segment file. `%f` is the filename. Every time a WAL segment completes, PostgreSQL runs this command to copy it to S3 (or wherever). The archive is the running history of all changes.

**Step 3: To recover — restore base backup and replay WAL**

When disaster strikes, on a new server:

```bash
# 1. Restore the base backup:
aws s3 sync s3://my-db-base-backup/ /var/lib/postgresql/data/

# 2. Create a recovery configuration:
cat > /var/lib/postgresql/data/postgresql.conf << EOF
restore_command = 'aws s3 cp s3://my-db-wal-archive/%f %p'
recovery_target_time = '2026-06-13 14:36:00'
recovery_target_action = 'promote'
EOF

# 3. Create recovery signal file:
touch /var/lib/postgresql/data/recovery.signal

# 4. Start PostgreSQL
pg_ctl start
```

PostgreSQL starts in recovery mode. It restores WAL segments from S3 one by one using `restore_command`. It applies each WAL record until it reaches a commit with a timestamp >= `14:36:00`. Then it stops applying WAL and promotes itself to a normal running database. The orders table has all its data from 14:36 — before the delete.

### ASCII Diagram: PITR Process

```
TIMELINE:
  [Base Backup]   [Time passes]        [Disaster]   [Target]
       |                                   |             |
  Jun 12         Jun 13 00:00         Jun 13        Jun 13
  23:00          (continuous             14:37         14:36
                  WAL archived          DELETE *      (restore here)
                  to S3)

RECOVERY PROCESS:

  S3:
  +------------------+  +--------+--------+--------+--------+
  | Base Backup      |  | WAL    | WAL    | WAL    | WAL    |
  | (Jun 12 23:00)   |  | seg 01 | seg 02 | ...    | seg 99 |
  +------------------+  +--------+--------+--------+--------+
           |                 |                         |
           v                 v                         |
  +------------------+                                 |
  | Restore to       |  restore_command fetches        |
  | new server       |  segments from S3               |
  +------------------+                                 |
           |                                           |
           v                                           |
  +------------------+  Apply WAL until ----------->  STOP
  | PostgreSQL in    |  recovery_target_time           |
  | recovery mode    |  '2026-06-13 14:36:00'          v
  +------------------+                         PROMOTE to primary
                                               (open for connections)
                                               Orders table intact!
```

### Timelines: What Happens After PITR

After a PITR recovery, PostgreSQL creates a new **timeline** (timeline ID increments from 1 to 2). This prevents the recovered database from accidentally applying WAL from the original timeline after the divergence point. Timeline 1 is the original history; timeline 2 is the recovered history starting from 14:36.

If you later take a new base backup of the recovered database, that backup is on timeline 2 and will use timeline 2's WAL for future PITR.

---

## 10. Real Incident: WAL Directory Filled Disk, Database Halted

### The Setup

Production PostgreSQL cluster. Primary with two replicas. One replica is used for analytics queries — runs heavy `SELECT` jobs that take 20-30 minutes each. On a Tuesday at 2pm, someone reboots the analytics replica to apply OS patches. The patch takes longer than expected. The team moves on. The analytics replica sits offline.

Nobody notices for three days.

### What Happened During Those Three Days

The analytics replica had a **replication slot** on the primary. Replication slots tell the primary: "Keep all WAL that this replica might need, even if it goes offline." This is meant to prevent the replica from missing WAL when it reconnects.

Without `max_slot_wal_keep_size` set, there was no limit. The primary dutifully kept every WAL segment from the moment the replica went offline.

The primary was a busy e-commerce database. It generated about 50GB of WAL per day.

Three days later: 150GB of WAL in `pg_wal/`. The disk was 200GB total. Other files (data, logs) took 40GB. Now WAL takes 150GB. Only 10GB free.

On Friday at 11am, the last 10GB filled up.

**PostgreSQL cannot write new WAL.** Every write to the database — every INSERT, UPDATE, DELETE, even `pg_stat_activity` updates — requires writing WAL. With no disk space, WAL writes fail. PostgreSQL returns an error to every client:

```
ERROR: could not write to file "pg_wal/000000010000000000000221":
       No space left on device
```

The entire database halted. Read-only queries continued working (they don't write WAL). But any write — including the heartbeat check that the health monitor used — failed. The load balancer detected the primary as unhealthy and started routing traffic to a read replica, which also couldn't handle writes.

Complete write outage. 45 minutes of downtime.

### Discovery

The on-call engineer SSHed into the primary. `df -h` showed:

```
Filesystem      Size  Used Avail Use% Mounted on
/dev/nvme0n1    200G  199G  100M 100% /
```

`du -sh /var/lib/postgresql/data/pg_wal/` showed 150GB.

```sql
-- From a session on the replica (read-only, still worked):
SELECT slot_name, active, restart_lsn,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS lag
FROM pg_replication_slots;
```

Output:
```
 slot_name          | active | restart_lsn | lag
--------------------+--------+-------------+---------
 analytics_replica  | f      | 0/4A000000  | 148 GB
 reporting_replica  | t      | 0/FE200000  | 256 MB
```

The `analytics_replica` slot was inactive (not connected) and holding 148GB of WAL.

### The Fix

```sql
-- Drop the stale slot. WAL cleanup happens automatically afterward.
SELECT pg_drop_replication_slot('analytics_replica');
```

PostgreSQL immediately began cleaning up WAL segments no longer needed. Within 30 seconds, `pg_wal/` shrank from 150GB to 2GB. Disk space freed up. WAL writes resumed. Write traffic came back online. Total time from discovery to fix: 8 minutes. Total downtime: 45 minutes.

### Prevention

```
postgresql.conf:
  max_slot_wal_keep_size = 20GB  # drop slot if it falls more than 20GB behind
```

And monitoring:

```sql
-- Alert if any slot has > 10GB of retained WAL:
SELECT slot_name, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS lag
FROM pg_replication_slots
WHERE pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) > 10 * 1024^3;
```

Add a disk space alert: alert at 70% full, page at 85% full. Never let it hit 95%.

### Lessons for L6 Interviews

If an interviewer asks "tell me about a database incident you've dealt with" or "how do you think about disk capacity for PostgreSQL," this incident framework is perfect:

1. **Replication slots are a disk bomb** — they have no limit by default
2. **Always set `max_slot_wal_keep_size`** — makes them self-limiting
3. **Monitor slot lag as a separate metric** from replication lag — lag in bytes, not just time
4. **Disk alerts must fire early** — 70% is not paranoid, it's responsible
5. **Read queries survived; writes didn't** — this is the correct failure mode (WAL is only for writes)

---

## 11. WAL in Other Databases

### The Pattern Is Universal

Every database that claims durability uses some form of a Write-Ahead Log. The implementation details vary, but the core principle — "write the log first, then apply to data files, recover by replaying the log" — is the same everywhere. Understanding PostgreSQL WAL deeply means you can reason about any database's durability story.

### MySQL InnoDB: Redo Log + Undo Log

MySQL InnoDB uses two separate logs where PostgreSQL WAL does the work of both:

**Redo log**: equivalent to PostgreSQL WAL for crash recovery. After a crash, InnoDB replays the redo log to bring data files up to date.

Key difference from PostgreSQL WAL: **the InnoDB redo log is circular**. It has a fixed size (configured with `innodb_log_file_size`). When it fills up, it wraps around. This means:
- Recovery only needs to scan the circular log (bounded size)
- But: if writes are faster than checkpoints, the log fills up and **InnoDB must stall all writes** until a checkpoint clears space. This is a serious bottleneck in write-heavy workloads.

MySQL 8.0 changed this: the redo log is now dynamic and can resize, partly addressing this issue.

**Undo log**: separate from the redo log. Used for rollback AND for MVCC (Multi-Version Concurrency Control). In PostgreSQL, old row versions live in the heap (that's what VACUUM cleans up). In MySQL InnoDB, old row versions live in the undo log. When you do a dirty read or snapshot read, InnoDB reconstructs the old version from the undo log.

| Feature | PostgreSQL WAL | MySQL InnoDB Redo Log |
|---------|---------------|----------------------|
| Structure | Append-forever segments | Circular fixed-size |
| Old versions | In heap (MVCC via heap) | In undo log |
| Replication | WAL streaming | Binary log (separate!) |
| Archiving | Built-in archive_mode | Binary log |

Note: MySQL replication uses the **binary log** (binlog), a separate log from the redo log. The binlog is a logical log (SQL statements or row changes). The redo log is a physical log (page changes). This two-log design is a source of complexity — they must be kept in sync (XA transaction between them).

### Cassandra: Commit Log

Cassandra's equivalent of WAL is the **commit log**. Before writing to a MemTable (in-memory sorted structure), Cassandra appends a record to the commit log.

If a node crashes, Cassandra replays the commit log to recover any MemTable data that wasn't yet flushed to an SSTable (the on-disk structure). The commit log is append-only, sequential, fast — same core properties as PostgreSQL WAL.

One difference: Cassandra's commit log is per-node. There's no concept of primary/replica using the same log — Cassandra uses gossip protocol and quorum writes for replication, not log shipping.

### RocksDB: WAL Before MemTable

RocksDB (used by TiKV, MyRocks, CockroachDB, and many key-value stores) follows the same pattern:

1. Write to WAL (append-only file)
2. Write to MemTable (in-memory sorted structure)
3. Client gets acknowledgment
4. Background: MemTable flushes to L0 SSTable
5. Background: Compaction merges SSTables

On crash: replay WAL to reconstruct MemTable. Same idea, same protection.

The WAL in RocksDB is per-column-family and can be disabled per column family for temporary/reconstructable data (e.g., block cache metadata that can be rebuilt).

### MongoDB: Oplog + Journal

MongoDB has two WAL-like mechanisms:

**Journal (WiredTiger WAL)**: WiredTiger is MongoDB's storage engine. It has its own WAL (called the journal) for crash recovery of the local node. It works exactly like PostgreSQL WAL — write journal record first, then apply to data files.

**Oplog**: The oplog (operations log) is MongoDB's replication log. It's a capped collection in the `local` database that stores every write operation in a logical format (which document was changed, how). Secondaries tail the oplog from the primary and apply operations.

The oplog is separate from the journal. The journal is for crash recovery. The oplog is for replication. This is analogous to MySQL's split between redo log (crash recovery) and binlog (replication).

MongoDB also uses the oplog for Change Streams (CDC/event streaming) — external consumers can tail the oplog to get a stream of all changes, similar to how Debezium reads PostgreSQL's WAL for CDC.

### Summary Comparison

| Database | Crash Recovery Log | Replication Log | Structure |
|----------|--------------------|----------------|-----------|
| PostgreSQL | WAL | WAL (same) | Append-forever segments |
| MySQL InnoDB | Redo log | Binary log (separate) | Circular (redo) + separate (binlog) |
| Cassandra | Commit log | Gossip + quorum (no log stream) | Append-forever per node |
| RocksDB | WAL | Depends on layer above (e.g., Raft) | Append-forever |
| MongoDB | WiredTiger journal | Oplog | Journal: internal; Oplog: capped collection |

### The Universal Insight for L6 Interviews

When a system design interviewer asks "how do you make writes durable?" or "how does your database survive a crash?", the answer is always some form of:

> "We use a write-ahead log. Before modifying data files, we append the intended change to a sequential log and flush it to disk. If we crash, we replay the log on restart. This gives us durability with sequential (fast) writes instead of random (slow) writes to data files."

Then you can go deeper based on the context:
- "Replication is log shipping — replicas replay the same log"
- "Checkpoints bound how much log we must replay on recovery"
- "Archiving the log enables point-in-time recovery"
- "Replication slots let replicas reconnect without missing changes, but require disk monitoring"

That's the framework. WAL is not a PostgreSQL-specific detail — it's the foundation of durable storage in distributed systems.

---

## Key Concepts Reference

| Term | Definition |
|------|-----------|
| WAL | Write-Ahead Log — sequential log of changes written before applying to data files |
| LSN | Log Sequence Number — monotonically increasing byte offset in the WAL |
| fsync | System call that forces OS to flush data from page cache to physical disk |
| Checkpoint | Point where all dirty pages are flushed to data files; WAL before this is reclaimable |
| Shared Buffer Pool | In-memory cache of database pages; modified pages are "dirty" |
| bgwriter | Background process that pre-flushes dirty pages to reduce checkpoint I/O spikes |
| Replication slot | Bookmark that tells primary to retain WAL for an offline replica |
| PITR | Point-in-Time Recovery — restoring to any past moment using base backup + WAL archive |
| Redo | Replaying committed WAL records during recovery to bring data files up to date |
| Undo | Reversing uncommitted changes during recovery using old-value fields in WAL |
| Replication lag | How far behind a replica's applied LSN is from primary's current LSN |
| WAL segment | 16MB file containing WAL records; numbered sequentially in pg_wal/ directory |
| Timeline | Version of history after a PITR; prevents applying wrong WAL to recovered database |
| synchronous_commit | Setting that controls when client is acknowledged relative to WAL flush |
| Commit log | Cassandra's term for WAL |
| Oplog | MongoDB's replication log (separate from journal/WAL) |

---

*Part B complete. Part C covers B-Trees, index internals, and MVCC vacuum.*
# Chapter 29: Database Internals Deep Dive
## Part C: MVCC and Concurrency Control Internals

---

## 1. The Concurrency Problem

Imagine you have a bank account with $1,000 in it. Now imagine two people — let's call them Alice and Bob — both log into the banking app at exactly the same time. Both want to withdraw $800.

Here is what happens without any concurrency control:

```
Time 1:  Alice reads account balance  →  sees $1,000
Time 2:  Bob reads account balance    →  sees $1,000
Time 3:  Alice checks: $1,000 >= $800? YES → proceeds with withdrawal
Time 4:  Bob checks:   $1,000 >= $800? YES → proceeds with withdrawal
Time 5:  Alice writes new balance: $1,000 - $800 = $200
Time 6:  Bob writes new balance:   $1,000 - $800 = $200
```

Final account balance: **$200**. But $800 + $800 = $1,600 was withdrawn. The bank just lost $600. Both withdrawals said "success." The account should be at -$600 in reality — or one of the withdrawals should have been rejected.

This is called a **race condition**: two operations that each individually look safe, but when they run at the same time they produce a wrong result. It happens because each person read a stale value before the other person's write landed.

Databases deal with millions of reads and writes per second. Race conditions like this are not hypothetical — they are the default behavior unless the database does something to prevent them. Every serious database system has a concurrency control mechanism to solve this.

There are two main approaches databases use:

### Approach 1: Locks (Pessimistic Concurrency Control)

The simplest idea: when one transaction is reading or writing a piece of data, make everyone else **wait**.

```
Time 1:  Alice reads account balance  →  ACQUIRES LOCK on the row
Time 2:  Bob tries to read balance    →  BLOCKED (waiting for Alice's lock)
Time 3:  Alice checks: $1,000 >= $800? YES → withdraws → writes $200 → RELEASES LOCK
Time 4:  Bob is unblocked, reads balance  →  sees $200
Time 5:  Bob checks: $200 >= $800? NO → withdrawal rejected
```

This is correct. But it is slow. Reads block other reads. Reads block writes. Writes block reads. On a busy system with thousands of concurrent queries, everyone is constantly waiting for everyone else. It works, but throughput suffers badly.

### Approach 2: MVCC (Optimistic — Give Everyone Their Own Snapshot)

The smarter idea: instead of making readers wait, give each transaction its own **frozen picture** of the database at the moment their transaction started. Reads never have to wait because they are reading a snapshot, not fighting over the live data.

```
Time 1:  Alice starts transaction → gets snapshot: "database as of Time 1"
Time 2:  Bob starts transaction   → gets snapshot: "database as of Time 2"
Time 3:  Both read their own snapshot → both see $1,000 (from their own snapshot)
Time 4:  Alice writes $200 → the actual row is updated
Time 5:  Bob tries to write → sees Alice already modified this row → CONFLICT DETECTED
          → Bob's transaction is rolled back (or retried)
```

The key insight: **reads never block writes, and writes never block reads.** Only write-write conflicts cause waits or aborts. Since most workloads are read-heavy (often 90%+ reads), this is a massive improvement in throughput.

This approach is called **Multi-Version Concurrency Control (MVCC)**, and it is used by PostgreSQL, MySQL InnoDB, Oracle, CockroachDB, and most modern databases.

The tradeoff: you now have to store multiple versions of the same row simultaneously (one for each active snapshot that might need to see the old version). This takes more storage and requires a garbage collection process to clean up old versions that nobody needs anymore. We will dig into all of that.

---

## 2. MVCC Fundamentals: Every Row Has a Version History

In a locking system, a row is a single thing: you update it, the old value is gone. In MVCC, a row is actually a **chain of versions**. Every time you update a row, the old version stays, and a new version is created alongside it. Readers who started before your update see the old version; readers who start after see the new version.

PostgreSQL implements this by storing hidden metadata on every row in the heap (the heap is just PostgreSQL's word for the physical table storage file). There are two critical hidden columns:

- **xmin**: The transaction ID (xid) of the transaction that *created* this row version. A row version becomes "alive" when the transaction with ID xmin commits.
- **xmax**: The transaction ID of the transaction that *deleted or updated* this row version. If xmax is 0 (or NULL), this row version is still "current" — nobody has deleted it yet.

You can actually see these hidden columns in PostgreSQL:

```sql
SELECT xmin, xmax, * FROM orders WHERE id = 42;
```

### What Happens on INSERT

When you insert a new row, PostgreSQL writes it with xmin set to your transaction ID and xmax set to 0:

```
INSERT INTO accounts (id, balance) VALUES (1, 1000);
-- Executed by transaction 100

Heap storage:
┌─────────────────────────────────────────────┐
│  xmin=100  │  xmax=0  │  id=1  │  balance=1000  │
└─────────────────────────────────────────────┘
```

This row version was born in transaction 100, and nobody has touched it since (xmax=0).

### What Happens on UPDATE

Now transaction 200 updates the balance to $200:

```sql
UPDATE accounts SET balance = 200 WHERE id = 1;
-- Executed by transaction 200
```

PostgreSQL does NOT overwrite the old row. Instead it does two things:
1. Sets xmax = 200 on the old version (marking it as "deleted by transaction 200")
2. Creates a brand new row version with xmin = 200 and xmax = 0

```
Heap storage after UPDATE:
┌─────────────────────────────────────────────┐
│  xmin=100  │  xmax=200  │  id=1  │  balance=1000  │  ← OLD version (dead once tx 200 commits)
├─────────────────────────────────────────────┤
│  xmin=200  │  xmax=0    │  id=1  │  balance=200   │  ← NEW version (current)
└─────────────────────────────────────────────┘
```

Any transaction that started before transaction 200 committed will see the first row (balance=1000). Any transaction that started after transaction 200 committed will see the second row (balance=200). Both are physically present in the table file at the same time.

### Three Updates in a Row — The Full Version Chain

Let's trace a row that gets updated three times:

```
Transaction 100: INSERT  balance=1000  →  xmin=100, xmax=0
Transaction 200: UPDATE  balance=200   →  xmin=100, xmax=200  (old)
                                          xmin=200, xmax=0    (new)
Transaction 350: UPDATE  balance=750   →  xmin=100, xmax=200  (old)
                                          xmin=200, xmax=350  (old)
                                          xmin=350, xmax=0    (new, current)

Heap file layout:
┌──────────────────────────────────────────────────────┐
│  VERSION 1: xmin=100  xmax=200  │  id=1  balance=1000 │
├──────────────────────────────────────────────────────┤
│  VERSION 2: xmin=200  xmax=350  │  id=1  balance=200  │
├──────────────────────────────────────────────────────┤
│  VERSION 3: xmin=350  xmax=0    │  id=1  balance=750  │
└──────────────────────────────────────────────────────┘

A transaction that started between tx100 and tx200 sees: VERSION 1 (balance=1000)
A transaction that started between tx200 and tx350 sees: VERSION 2 (balance=200)
A transaction that started after tx350                sees: VERSION 3 (balance=750)
```

This is the core of MVCC: the table file is a **multi-version store**. Each row identity (id=1) can have multiple physical versions coexisting. The correct version for any given reader is determined by comparing the reader's snapshot to the xmin/xmax values.

---

## 3. Snapshots: What Each Transaction Sees

Now that we know rows carry version metadata, we need to understand how a transaction decides *which* version to read. This decision is controlled by the transaction's **snapshot**.

When a transaction starts (or, in READ COMMITTED mode, when each statement starts), PostgreSQL takes a snapshot of the current state of all active transactions. A snapshot contains three things:

- **snapshot_xmin**: The lowest transaction ID that is still in-progress (not yet committed) at snapshot time. Everything with xmin *less than* snapshot_xmin is either committed or rolled back — no ambiguity.
- **snapshot_xmax**: One more than the highest transaction ID that exists at snapshot time. Any transaction ID >= snapshot_xmax started after the snapshot was taken, so we cannot see its work.
- **xip list**: The list of transaction IDs that are currently in-progress (active) at snapshot time. These are transactions that have IDs *between* snapshot_xmin and snapshot_xmax, but have not committed yet. We cannot see their work either.

Think of taking a photograph of a busy street. The photograph is your snapshot. People who walked past before the shutter clicked are in the picture (committed). People who had not arrived yet are not in the picture (future transactions). People who were mid-stride right when you clicked — partially in frame — are the xip list: physically present but in an ambiguous state, so MVCC ignores them.

### The Visibility Rule

For a row version to be **visible** to a transaction with a given snapshot, it must pass both parts of this test:

```
VISIBLE if:
  (1) xmin committed AND xmin < snapshot_xmax AND xmin NOT in xip
      ← "This row was created by a committed transaction that the snapshot can see"
  AND
  (2) xmax = 0
      OR xmax >= snapshot_xmax
      OR xmax is in xip
      OR xmax rolled back (transaction aborted, so deletion never happened)
      ← "This row has not been deleted by any committed transaction the snapshot can see"
```

If both conditions are true: the row version is visible to this transaction.

### Concrete Example Walk-Through

Let's trace four transactions and figure out what each snapshot sees:

```
Timeline of events:
  Tx 100: INSERT row (id=1, balance=1000) → COMMITS at T=1
  Tx 200: UPDATE row to balance=200       → COMMITS at T=3
  Tx 230: long-running read transaction   → STARTS at T=2, still active at T=5
  Tx 250: new transaction                 → STARTS at T=5, takes snapshot
```

At T=5 when Tx 250 takes its snapshot:
- Tx 100: committed long ago
- Tx 200: committed (at T=3)
- Tx 230: still running (started T=2, not yet committed)

Tx 250's snapshot:
```
snapshot_xmin = 230    (lowest active tx)
snapshot_xmax = 251    (next tx id to be assigned)
xip = [230]            (transactions in-progress)
```

Now the heap looks like this:

```
VERSION A: xmin=100  xmax=200  │  id=1  balance=1000   ← old, deleted by tx200
VERSION B: xmin=200  xmax=0    │  id=1  balance=200    ← current
```

Does Tx 250 see VERSION A (balance=1000)?
- Condition 1: xmin=100. Is 100 committed? Yes. Is 100 < 251? Yes. Is 100 in xip=[230]? No. → PASS
- Condition 2: xmax=200. Is 200 = 0? No. Is 200 >= 251? No. Is 200 in xip=[230]? No. Is 200 rolled back? No (it committed). → FAIL

VERSION A is **not visible** to Tx 250. Good — that's the old value.

Does Tx 250 see VERSION B (balance=200)?
- Condition 1: xmin=200. Is 200 committed? Yes. Is 200 < 251? Yes. Is 200 in xip=[230]? No. → PASS
- Condition 2: xmax=0. → PASS immediately

VERSION B is **visible** to Tx 250. It reads balance=200.

What does Tx 230 (started at T=2, before Tx 200 committed) see?

Tx 230's snapshot (taken at T=2):
```
snapshot_xmin = 200    (tx 200 was active when tx 230 started)
snapshot_xmax = 231
xip = [200]            (tx 200 was in-progress at T=2)
```

Does Tx 230 see VERSION A (balance=1000)?
- Condition 1: xmin=100. Committed, < 231, not in xip=[200]. → PASS
- Condition 2: xmax=200. Is 200 in xip=[200]? YES → PASS (tx 200 was in-progress at snapshot time, so this deletion hasn't "happened yet" from Tx 230's point of view)

VERSION A is **visible** to Tx 230. It reads balance=1000 — the value before Tx 200 committed.

### Timeline Diagram

```
         T=1        T=2        T=3        T=4        T=5
          |          |          |          |          |
Tx 100:  [INSERT]--[COMMIT]
                    |
Tx 230:            [START]----------------------------[still running]
                              |
Tx 200:          [UPDATE]---[COMMIT]
                                                       |
Tx 250:                                               [START/SNAPSHOT]

What Tx 230 sees:  balance=1000  (snapshot taken before Tx 200 committed)
What Tx 250 sees:  balance=200   (snapshot taken after Tx 200 committed)

Both readers are running SIMULTANEOUSLY at T=5, seeing DIFFERENT values.
This is MVCC — no locks needed, each transaction sees a consistent snapshot.
```

---

## 4. Why Updates = Delete + Insert in MVCC

In a simple locking system, an UPDATE just overwrites the row in place. The old value is gone. In MVCC, this is impossible — old values must remain for any transaction whose snapshot predates the update.

So MVCC implements UPDATE as a logical **delete + insert**:

1. The old row version gets xmax set (logical delete)
2. A new row version gets written with xmin set (logical insert)

This design choice has important consequences:

### Consequence 1: Storage Bloat

Every update temporarily doubles the number of physical row versions. On a table where rows are updated frequently, dead versions pile up fast. A table with 10 million rows that gets fully updated once has 20 million physical rows temporarily.

This is called **table bloat** — the table file grows even though the logical row count has not changed. PostgreSQL needs a garbage collector (VACUUM, discussed in section 5) to reclaim this space.

### Consequence 2: Write Amplification on Indexes

Indexes in PostgreSQL point to specific physical row versions (by their page number and slot within the page — called a **TID**, or Tuple ID). When a row is updated:
- The old physical location is invalidated
- The new version lands at a different physical location
- Every index that covers this table now has a stale pointer to the old version and needs a new entry for the new version

If your table has 5 indexes and you update a row, you are writing: 1 heap page (for the new version) + 5 index pages (to add the new TID). This is write amplification.

### Consequence 3: HOT — Heap Only Tuple Optimization

PostgreSQL engineers recognized that many updates only change non-indexed columns. For example, updating a `last_login` timestamp when the table's only index is on `user_id`. Why pay the full index update cost when no indexed column changed?

**HOT (Heap Only Tuple)** is PostgreSQL's optimization for this case:

- If the updated columns are NOT covered by any index AND the new row version fits on the same heap page as the old version:
  - PostgreSQL creates a "HOT chain" — a pointer from the old version to the new version, entirely within the heap page
  - No index entry is created for the new version
  - Index scans follow the HOT chain to find the current version
  - Cost: 1 heap page write only, zero index page writes

```
REGULAR UPDATE (indexed column changed, or no space on same page):

  Index (btree):
  ┌────────────────┐
  │  user_id=42    │──────────────────────────┐
  │  → page 7, slot 3  (old TID)              │
  ├────────────────┤                           ▼
  │  user_id=42    │──────────┐       Heap Page 7:
  │  → page 9, slot 1  (new) │       ┌──────────────────────────────┐
  └────────────────┘          │       │ Slot 3: xmin=200 xmax=350    │
                              │       │         user_id=42 score=88  │
                              │       └──────────────────────────────┘
                              │
                              └──►    Heap Page 9:
                                      ┌──────────────────────────────┐
                                      │ Slot 1: xmin=350 xmax=0      │
                                      │         user_id=42 score=95  │
                                      └──────────────────────────────┘
  Two index entries. Two separate heap pages touched.

HOT UPDATE (non-indexed column changed, new version fits on same page):

  Index (btree):
  ┌────────────────────────┐
  │  user_id=42            │──────────────────┐
  │  → page 7, slot 3      │                  │
  └────────────────────────┘                  ▼
  One index entry.              Heap Page 7:
                                ┌──────────────────────────────────────┐
                                │ Slot 3: xmin=200 xmax=350            │
                                │         user_id=42 last_login=T1     │
                                │         [HOT link → Slot 5]          │
                                ├──────────────────────────────────────┤
                                │ Slot 5: xmin=350 xmax=0              │
                                │         user_id=42 last_login=T2     │
                                │         [HOT tuple, no index entry]  │
                                └──────────────────────────────────────┘
  One index entry. One heap page. Zero index pages written.
```

HOT is a significant optimization for workloads that update non-indexed columns frequently. But it only kicks in when both conditions are met: no indexed column changed, AND the page has room. If the page is full, PostgreSQL must place the new version elsewhere and lose the HOT benefit.

---

## 5. VACUUM: The Garbage Collector

MVCC creates a problem: dead row versions accumulate continuously. Every committed UPDATE leaves a dead old version behind. Every committed DELETE leaves a dead old version behind. If these are never cleaned up, the table file grows forever, and sequential scans waste I/O reading dead versions that are invisible to everyone.

**VACUUM** is PostgreSQL's garbage collection mechanism. Understanding it is essential for anyone running PostgreSQL in production.

### Why Dead Tuples Accumulate

```
At T=0: orders table has 1M rows. Average row size 200 bytes. Table = ~200MB.

At T=1: e-commerce sale. 500K orders get their status updated (e.g., "shipped").
        Each update = 1 dead version + 1 new version.
        Dead tuples: 500K × 200 bytes = ~100MB of dead data now in the file.
        Table size jumps to ~300MB. Only ~200MB is readable data.

At T=2: another batch update. 500K more rows updated.
        Dead tuples: now ~200MB of dead data.
        Table size: ~400MB. Half of every sequential scan is wasted I/O.

Without VACUUM, this continues until the disk is full.
```

Dead tuples are physically present in the heap pages. A sequential scan reads every page, including ones full of dead tuples. It just skips the dead ones after reading them. But the I/O cost has already been paid. This is why a bloated table is slow even if the live row count is small.

### What VACUUM Does (Step by Step)

VACUUM is not a simple "delete old rows" command. It does a precise, careful job:

**Step 1: Scan each page of each table**

VACUUM reads every page of the table's heap file. This is sequential I/O — fast, does not interfere much with concurrent queries.

**Step 2: Identify dead tuples**

For each row version on each page, VACUUM checks: is this row version dead? A row version is dead if:
- xmax is set (it was deleted or updated)
- The transaction that set xmax has committed
- No active transaction has a snapshot that predates xmax's commit (no one can see this row anymore)

That last condition is critical: VACUUM cannot clean a row if any running transaction might still need to see it. This is why long-running transactions prevent VACUUM from cleaning old versions (more on this in Section 9).

**Step 3: Mark dead tuples as free space**

VACUUM does NOT zero out or overwrite dead tuples immediately. It simply marks their slots as "reusable" in the page header. The bytes are still there on disk, but the next INSERT or UPDATE can write over them.

**Step 4: Update the Free Space Map (FSM)**

The **Free Space Map** is a small auxiliary data structure that tracks how much free space is available on each heap page. When you insert a new row, PostgreSQL consults the FSM to find a page with enough space, rather than scanning the whole file. VACUUM updates the FSM after marking dead tuples free.

**Step 5: Update the Visibility Map (VM)**

The **Visibility Map** is a 1-bit-per-page structure that marks pages where every single row version is visible to all current and future transactions (i.e., the page has zero dead tuples and no in-progress versions). Pages marked in the VM can be skipped by index-only scans — if all data on the page is guaranteed visible, no heap fetch is needed.

### Regular VACUUM vs VACUUM FULL

These two operations have very different costs and should never be confused:

**Regular VACUUM:**
- Marks dead tuple space as reusable within the table file
- Table file size does NOT shrink on disk (the file stays the same size, but the freed space can be reused by future inserts)
- Runs concurrently — readers and writers continue unimpeded
- Low impact: runs during normal business hours safely
- This is what autovacuum runs automatically

**VACUUM FULL:**
- Rewrites the entire table from scratch into a new file, skipping all dead tuples
- Table file size SHRINKS — space is returned to the operating system
- Requires an **ACCESS EXCLUSIVE lock** on the table — no reads, no writes, no anything for the entire duration
- On a large table (say, 500GB), this can run for hours, during which the table is completely inaccessible
- Use only when: table bloat is so severe it is causing serious performance problems AND you have a maintenance window with zero user traffic
- Alternative: `pg_repack` (a third-party extension) can do an online repack without an exclusive lock

```
Regular VACUUM result:
  Table file: [LIVE][LIVE][FREE][LIVE][FREE][FREE][LIVE]
  File size: unchanged. OS sees same file size.
  New inserts: can use the [FREE] slots.

VACUUM FULL result:
  New file:   [LIVE][LIVE][LIVE][LIVE]
  File size: shrunk. OS can use the freed disk blocks for other files.
  Cost: table was locked for the entire rewrite duration.
```

### Autovacuum: The Automatic Janitor

PostgreSQL does not make you run VACUUM manually (though you can). The **autovacuum daemon** is a background process that monitors tables and triggers VACUUM automatically.

Autovacuum fires on a table when:

```
n_dead_tup > autovacuum_vacuum_threshold + autovacuum_vacuum_scale_factor × n_live_tup
```

With default settings:
- `autovacuum_vacuum_threshold` = 50 (minimum 50 dead tuples before considering a run)
- `autovacuum_vacuum_scale_factor` = 0.2 (20% of live tuples)

So for a table with 1 million live rows: autovacuum triggers when dead tuples exceed 50 + (0.2 × 1,000,000) = 200,050 dead tuples. This is fine for most workloads.

But autovacuum can fall behind. Here is when that happens:

**Problem 1: Write rate exceeds cleaning rate.**

If a table is being updated faster than autovacuum can clean it, dead tuples accumulate. Solution: increase `autovacuum_vacuum_cost_delay` (make each pass faster) or add more autovacuum workers.

**Problem 2: Long-running transactions hold back the cleanup.**

If a transaction started at T=1 and is still running at T=100, autovacuum cannot clean any dead tuples created after T=1 — because that long-running transaction might still need to see them (its snapshot includes them). This is the single most common cause of autovacuum falling behind.

**Problem 3: Not enough autovacuum workers.**

Default is 3 autovacuum workers total. If you have 100 tables all being hammered with updates, 3 workers cannot keep up. Increase `autovacuum_max_workers`.

```
Dead tuple accumulation vs autovacuum cleaning:

Dead tuples
(millions)
     │
  4M ┤                           ╭───── ALERT ZONE
     │                       ╭───╯
  3M ┤                   ╭───╯
     │               ╭───╯
  2M ┤           ╭───╯
     │        ╭──╯       ← Accumulation rate (write-heavy workload)
  1M ┤    ╭───╯  ╲_____ Autovacuum running (cleaning)
     │╭───╯              ╰──── Falls behind if cleaning rate < accumulation rate
   0 ┼──────────────────────────────────────────────────────── Time
     T0   T1   T2   T3   T4   T5   T6   T7   T8   T9
```

Monitor dead tuple counts with:
```sql
SELECT relname, n_dead_tup, n_live_tup, last_autovacuum
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;
```

---

## 6. Transaction ID Wraparound: The Silent Time Bomb

This is one of the most dangerous failure modes in PostgreSQL. If you run PostgreSQL in production, you must understand this.

### The Problem

PostgreSQL uses **32-bit unsigned integers** for transaction IDs (xids). That gives a maximum of about **4.29 billion** unique transaction IDs. But PostgreSQL treats the xid space as a circle, not a line — it uses modular arithmetic and compares xids in a 2-billion-wide window. In practice, this means you get about **2 billion** transactions before the ID counter "wraps around" and old IDs become ambiguous.

Here is why this is catastrophic: imagine a row with xmin = 500. The transaction ID counter has been running for years. It passes 2 billion... 3 billion... 4 billion... and wraps back around to 0, then to 500.

Now there is a newly inserted row with xmin = 500 (the new Tx 500 after wraparound). And there is your old row also with xmin = 500 (from years ago, the original Tx 500). PostgreSQL cannot tell which is the past and which is the present. Visibility checks break down completely.

PostgreSQL's response to this: **it refuses to start**. Literally. If the database detects that wraparound is imminent, it logs:

```
FATAL: database is not accepting commands to avoid wraparound data loss
HINT: Stop the postmaster and vacuum that database in single-user mode.
```

Your database is down. Every user gets errors. Nothing works until you run emergency vacuum.

### The Fix: Freezing

PostgreSQL prevents wraparound by **freezing** old rows. When VACUUM processes a row with a very old xmin (old enough that no active transaction could have started before it), it replaces xmin with a special marker called `FrozenTransactionId` (internally, xid = 2).

A frozen row is **always visible to all transactions**, with no xid-based comparison needed. It is effectively "timeless" — it predates any possible transaction snapshot.

```
Transaction ID number line (wraps at ~4.2 billion):

   0           1B          2B          3B          4B         ~4.3B
   ├───────────┼───────────┼───────────┼───────────┼────────────┤
   │           │           │DANGER ZONE│           │            │
   │◄──────────── ~2 billion visible window ───────────────────►│
   │                                                            │
   │  Rows older than 2 billion txids "fall off the back"      │
   │  UNLESS they are frozen first.                            │

After freezing:
   Rows with xmin that is "too old" → xmin replaced with FrozenXid (=2)
   These rows are permanently visible. No more age problem.
```

### The autovacuum_freeze_max_age Parameter

PostgreSQL freezes rows when their xmin age exceeds `autovacuum_freeze_max_age` (default: 200 million transactions). This is a safety trigger: autovacuum will run on a table purely to freeze old rows, even if the dead tuple count is low, once any row exceeds this age.

You can monitor how close each database is to wraparound:

```sql
SELECT datname,
       age(datfrozenxid) AS xid_age,
       2000000000 - age(datfrozenxid) AS txids_remaining
FROM pg_database
ORDER BY xid_age DESC;
```

**Alert threshold**: When `age(datfrozenxid)` exceeds 1 billion (half of the 2-billion window), you should be actively investigating. At 1.5 billion, you should be taking action. At 2 billion, PostgreSQL will shut down.

```
XID age gauge:

  0           500M        1B         1.5B        2B
  ├───────────┬───────────┬───────────┬───────────┤
  │  SAFE     │  MONITOR  │   ALERT   │ SHUTDOWN  │
  │           │           │           │           │
  └─────────────────────────────────────────────►
              ▲ Normal    ▲ PagerDuty ▲ Emergency ▲ Database refuses connections
              autovacuum   starts      vacuum all    until fixed
              handles it   watching    tables now
```

**Real Incident: Mailchimp, 2019**

Mailchimp's PostgreSQL cluster approached transaction ID wraparound on several high-traffic tables. Their autovacuum had fallen behind due to long-running reporting queries holding old snapshots. They had to:
1. Identify all tables with high xid age
2. Schedule emergency maintenance windows
3. Run manual VACUUM FREEZE on each table
4. Temporarily block write traffic to let vacuum complete

The lesson: monitor `age(datfrozenxid)` like you monitor disk space. A surprise at 2 billion means a database outage.

---

## 7. Isolation Levels: The Consistency Dial

MVCC is not a binary on/off. PostgreSQL exposes a **dial** of how strictly you want consistency enforced, with increasing protection at increasing cost. This dial is called the **isolation level**.

The SQL standard defines four isolation levels. PostgreSQL implements all four, but with some PostgreSQL-specific differences worth knowing.

### The Four Anomalies Isolation Levels Guard Against

Before looking at the levels, understand what they protect against:

**Dirty Read**: You read data that another transaction has written but not yet committed. If that transaction rolls back, you read data that never officially existed.

**Non-Repeatable Read**: Within a single transaction, you read the same row twice. Between your two reads, another transaction commits a change to that row. Your second read returns a different value. The row is not "repeatable" within your transaction.

**Phantom Read**: Within a single transaction, you run the same query twice (e.g., `SELECT COUNT(*) WHERE status='active'`). Between your two queries, another transaction inserts a new row that matches the WHERE clause. Your second query returns a different count. A "phantom" row appeared.

**Write Skew**: Two transactions each read an overlapping set of rows, make decisions based on what they read, and write updates that violate a constraint that was satisfied when each individually read the data. Neither transaction sees a conflict, but together they violate invariants.

### READ UNCOMMITTED

The loosest level. Allows dirty reads: you can read another transaction's uncommitted work.

**PostgreSQL's implementation**: PostgreSQL does not actually implement dirty reads. Treating READ UNCOMMITTED as READ COMMITTED is allowed by the SQL standard, and that is what PostgreSQL does. If you set your transaction to READ UNCOMMITTED in PostgreSQL, it behaves exactly like READ COMMITTED.

### READ COMMITTED (PostgreSQL Default)

The most commonly used level. Each SQL statement within the transaction gets a **fresh snapshot** of the committed data at the moment that statement starts.

- **Dirty reads**: impossible — you can only see committed data
- **Non-repeatable reads**: possible — two `SELECT` statements in the same transaction may see different committed values (each statement gets a new snapshot)
- **Phantom reads**: possible — a `SELECT COUNT(*)` run twice in the same transaction may return different counts

Example of a non-repeatable read under READ COMMITTED:

```sql
-- Transaction A (READ COMMITTED):
BEGIN;
SELECT balance FROM accounts WHERE id = 1;  -- Returns 1000

-- (Meanwhile, Transaction B commits: UPDATE accounts SET balance = 500 WHERE id = 1)

SELECT balance FROM accounts WHERE id = 1;  -- Returns 500 !!
-- Same query, same transaction, different result.
COMMIT;
```

This is by design: READ COMMITTED always shows you the latest committed state, even within a transaction. Most OLTP applications accept this trade-off because it gives better concurrency (each statement gets a fresh snapshot, so long transactions do not hold stale views).

### REPEATABLE READ

The transaction takes one snapshot at the start of the first statement, and uses that same snapshot for all subsequent statements in the transaction.

- **Dirty reads**: impossible
- **Non-repeatable reads**: impossible — your snapshot is frozen at transaction start
- **Phantom reads**: in the SQL standard, possible. In PostgreSQL specifically, IMPOSSIBLE — the snapshot includes row counts, so no phantom rows can appear
- **Write skew**: possible

PostgreSQL's REPEATABLE READ is actually stronger than the SQL standard requires. The standard says phantom reads are possible at REPEATABLE READ, but PostgreSQL's snapshot-based implementation prevents them automatically.

Write skew is still possible. See the concrete example below.

### SERIALIZABLE

The strongest level. PostgreSQL implements this via **Serializable Snapshot Isolation (SSI)**, introduced in PostgreSQL 9.1. This is a sophisticated algorithm that goes beyond just snapshot isolation:

SSI tracks **read-write dependencies** between concurrent transactions. If it detects a pattern of dependencies that would be impossible in a truly serial execution (one transaction at a time), it aborts one of the conflicting transactions with:

```
ERROR: could not serialize access due to read/write dependencies among transactions
DETAIL: Reason code: Canceled on identification as a pivot, during write.
HINT: The transaction might succeed if retried.
```

Note the hint: "might succeed if retried." SSI sometimes produces **false positive aborts** — it can abort transactions that would have been serializable, due to conservative dependency tracking. Applications using SERIALIZABLE must be prepared to retry aborted transactions.

- **Dirty reads**: impossible
- **Non-repeatable reads**: impossible
- **Phantom reads**: impossible
- **Write skew**: impossible (SSI detects and aborts)
- **Cost**: dependency tracking overhead (~10-30% performance overhead on write-heavy workloads)

### Isolation Level Anomaly Matrix

| Isolation Level    | Dirty Read | Non-Repeatable Read | Phantom Read | Write Skew |
|--------------------|:----------:|:-------------------:|:------------:|:----------:|
| READ UNCOMMITTED   |  Possible  |      Possible       |   Possible   |  Possible  |
| READ COMMITTED     | Impossible |      Possible       |   Possible   |  Possible  |
| REPEATABLE READ    | Impossible |     Impossible      | Impossible*  |  Possible  |
| SERIALIZABLE       | Impossible |     Impossible      |  Impossible  | Impossible |

*PostgreSQL-specific: standard allows phantoms at REPEATABLE READ, PostgreSQL prevents them.

Note: PostgreSQL's READ UNCOMMITTED behaves like READ COMMITTED.

### Concrete Write Skew Example

Write skew is subtle. Here is the classic doctor on-call example:

A hospital rule: at least one doctor must be on-call at all times. The `on_call` table has two doctors: Alice and Bob, both on-call.

```sql
-- Transaction A: Alice wants to go home
BEGIN;
SELECT COUNT(*) FROM on_call WHERE is_on_call = TRUE;
-- Returns 2 (Alice and Bob are both on call)
-- "There's someone else on call, I can leave safely"
UPDATE on_call SET is_on_call = FALSE WHERE name = 'Alice';
COMMIT;

-- Transaction B: Bob wants to go home (runs CONCURRENTLY with Transaction A)
BEGIN;
SELECT COUNT(*) FROM on_call WHERE is_on_call = TRUE;
-- Returns 2 (snapshot taken before Alice's update committed)
-- "There's someone else on call, I can leave safely"
UPDATE on_call SET is_on_call = FALSE WHERE name = 'Bob';
COMMIT;

-- Result: NOBODY is on call. Hospital constraint violated.
-- Each transaction individually looked safe. Together: catastrophe.
```

Under REPEATABLE READ, both transactions used consistent snapshots and both read "2 doctors on call." Neither saw a conflict. But their combined writes violated the invariant.

Under SERIALIZABLE, SSI would have detected the read-write dependency cycle and aborted one of the transactions.

Under REPEATABLE READ or READ COMMITTED, the fix is to use `SELECT FOR UPDATE`:

```sql
BEGIN;
SELECT COUNT(*) FROM on_call WHERE is_on_call = TRUE FOR UPDATE;
-- This locks the rows that the COUNT is based on.
-- Transaction B must now WAIT until Transaction A commits.
-- After A commits, B re-reads: COUNT = 1, cannot leave safely.
ROLLBACK;
```

---

## 8. Locking: When MVCC Isn't Enough

MVCC elegantly handles read-write concurrency — readers see a consistent snapshot and never block writers, writers never block readers. But MVCC alone cannot handle **write-write concurrency**. When two transactions want to modify the same row, one of them must wait (or abort). This is where locks come in.

Locks in PostgreSQL are not the blunt, single-level locks of early databases. There is a rich hierarchy.

### Row-Level Locks

When you write a row (INSERT, UPDATE, DELETE), PostgreSQL acquires a row-level lock on it. This prevents two transactions from modifying the same row simultaneously.

You can also acquire row-level locks explicitly in a SELECT:

**FOR UPDATE**: Exclusive lock. No other transaction can modify or lock this row until you commit. Blocks: `FOR UPDATE`, `FOR NO KEY UPDATE`, `FOR SHARE`, `FOR KEY SHARE`.

```sql
SELECT * FROM accounts WHERE id = 1 FOR UPDATE;
-- Now you own this row. Nobody else can touch it.
-- Run your checks and updates safely, then COMMIT.
```

**FOR SHARE**: Shared lock. Other transactions can also lock FOR SHARE, but nobody can update the row. Blocks: `FOR UPDATE`, `FOR NO KEY UPDATE`.

**FOR NO KEY UPDATE**: Like FOR UPDATE, but allows other transactions to acquire FOR KEY SHARE. Used internally by foreign key checks.

**FOR KEY SHARE**: Weakest explicit lock. Allows concurrent FOR NO KEY UPDATE and FOR SHARE. Blocks only FOR UPDATE. Used internally by foreign key enforcement on the referenced side.

### Table-Level Locks

PostgreSQL also has table-level locks, acquired automatically by DML operations:

| Lock Mode         | Acquired By                        | Blocks                          |
|-------------------|------------------------------------|---------------------------------|
| ACCESS SHARE      | SELECT                             | ACCESS EXCLUSIVE only           |
| ROW SHARE         | SELECT FOR UPDATE / FOR SHARE      | EXCLUSIVE, ACCESS EXCLUSIVE     |
| ROW EXCLUSIVE     | INSERT, UPDATE, DELETE             | SHARE, SHARE ROW EXCLUSIVE, EXCLUSIVE, ACCESS EXCLUSIVE |
| SHARE UPDATE EXCLUSIVE | VACUUM, ANALYZE, CREATE INDEX CONCURRENTLY | SHARE UPDATE EXCLUSIVE and above |
| SHARE             | CREATE INDEX (non-concurrent)      | ROW EXCLUSIVE and above         |
| SHARE ROW EXCLUSIVE | CREATE TRIGGER, ALTER TABLE (some) | ROW EXCLUSIVE and above        |
| EXCLUSIVE         | Rarely used explicitly             | All except ACCESS SHARE         |
| ACCESS EXCLUSIVE  | ALTER TABLE, DROP TABLE, TRUNCATE, VACUUM FULL | ALL other locks      |

The critical one: **ACCESS EXCLUSIVE** blocks everything, including plain `SELECT`. This is why `ALTER TABLE` on a busy production table can cause an outage — it waits for all existing queries to finish, then blocks all new queries while it runs.

The safe alternative for adding indexes: `CREATE INDEX CONCURRENTLY` uses SHARE UPDATE EXCLUSIVE, which allows reads and writes to continue.

### Advisory Locks

**Advisory locks** are application-defined named locks that PostgreSQL manages but does not automatically acquire or release. Your application code explicitly acquires and releases them. They are useful for distributed coordination.

```sql
-- Only one process should run the billing job at a time:
SELECT pg_try_advisory_lock(12345);  -- 12345 is your application-defined lock id
-- Returns TRUE if you got the lock, FALSE if someone else holds it
-- If TRUE: run the billing job
-- When done:
SELECT pg_advisory_unlock(12345);
```

Use cases:
- Distributed mutex (only one cron job runs across multiple app servers)
- Rate limiting (acquire a lock to check/update a rate counter atomically)
- Optimistic caching (lock a cache key while regenerating it)

### Deadlock: The Lock Cycle

A **deadlock** happens when Transaction A holds a lock that Transaction B needs, and Transaction B holds a lock that Transaction A needs. Both are waiting for the other. Neither can proceed. They are stuck forever — unless someone intervenes.

```
DEADLOCK DIAGRAM:

  Transaction A                  Transaction B
  ─────────────                  ─────────────
  LOCK row 1  ←─ holds ─┐   ┌─ holds ─→  LOCK row 2
  WAIT for row 2 ────────┼───┤            WAIT for row 1
                         │   │
                         └───┘
              Circular dependency — neither can proceed.

Timeline:
  T=1: Tx A locks row 1
  T=2: Tx B locks row 2
  T=3: Tx A tries to lock row 2 → WAITS
  T=4: Tx B tries to lock row 1 → WAITS
  T=5: PostgreSQL's deadlock detector wakes up
  T=6: PostgreSQL chooses Tx B (the "younger" or less costly transaction)
  T=7: Tx B is aborted with: "ERROR: deadlock detected"
  T=8: Tx A's wait is released. Tx A continues.
```

PostgreSQL detects deadlocks by periodically checking for lock wait cycles (every `deadlock_timeout`, default 1 second). When detected, it kills one transaction (typically the one that has done less work) to break the cycle.

**Prevention**: The only reliable way to prevent deadlocks is to always acquire locks in the same order across all transactions. If Tx A always locks row 1 before row 2, and Tx B also always locks row 1 before row 2, a deadlock is impossible — the second transaction will wait for the first at row 1, and the first will eventually release it.

```sql
-- BAD: Different lock order in different code paths
-- Code path 1: UPDATE accounts WHERE id=1, then UPDATE accounts WHERE id=2
-- Code path 2: UPDATE accounts WHERE id=2, then UPDATE accounts WHERE id=1
-- → Deadlock possible

-- GOOD: Always lock in the same order (e.g., ascending id)
-- Code path 1: UPDATE accounts WHERE id IN (1,2) ORDER BY id
-- Code path 2: UPDATE accounts WHERE id IN (1,2) ORDER BY id
-- → Both will lock id=1 first, id=2 second → no deadlock possible
```

---

## 9. Real Incident: Long-Running Report Blocked Autovacuum

This is a real pattern seen at dozens of companies running PostgreSQL at scale. Understanding it in detail will save you from a painful production incident.

### The Setup

A mid-size e-commerce company runs their analytics on the primary PostgreSQL database (not a read replica — a common early-stage shortcut). Every morning at 6 AM, a data analyst runs a report:

```sql
-- Daily orders report (READ COMMITTED isolation level, runs for ~4 hours)
BEGIN;
SELECT
    DATE_TRUNC('day', created_at) AS day,
    SUM(total_amount) AS revenue,
    COUNT(*) AS order_count,
    AVG(total_amount) AS avg_order_value
FROM orders
GROUP BY 1
ORDER BY 1;
COMMIT;
```

This query takes 4 hours because the `orders` table has 200 million rows and the report does a full sequential scan.

Simultaneously, the production application is processing orders normally: 500 orders per second, each order going through status updates (created → paid → fulfilled → shipped → delivered). That is 5 status UPDATE operations per order. So roughly 2,500 UPDATEs per second on the orders table.

### What Happens

**6:00 AM**: Report transaction starts. PostgreSQL records the snapshot: at this moment, let us say the active transaction watermark is at xid=5,000,000.

**6:00 AM to 10:00 AM**: The application processes 4 hours × 3,600 seconds × 2,500 UPDATEs = **36,000,000 row version updates** on the orders table.

Each UPDATE creates one dead version. So after 4 hours: **36 million dead tuples**.

**6:00 AM to 10:00 AM (autovacuum's perspective)**: Autovacuum sees the growing dead tuple count and triggers on the orders table. It starts cleaning. But here is the problem:

The report transaction is still running with its snapshot from 6:00 AM (xid=5,000,000). Autovacuum cannot clean any dead tuple created before that snapshot's horizon. Since ALL of the 36 million dead tuples were created by transactions with xid > 5,000,000 (they happened after the report started), autovacuum cannot touch ANY of them.

Autovacuum is essentially locked out of the table.

```
Dead tuple count on orders table:

  36M ┤                                              ╭──── 10AM: report ends
      │                                         ╭────╯     VACUUM runs, cleans all
      │                                    ╭────╯
  24M ┤                               ╭────╯
      │                          ╭────╯
      │                     ╭────╯     ← Dead tuples accumulating (2500/sec)
  12M ┤                ╭────╯
      │           ╭────╯
      │      ╭────╯          ×── Autovacuum: BLOCKED. Can't clean anything.
   0  ┼──────╯                                               ╰──────────────
      6AM   7AM   8AM   9AM   10AM
```

**Physical impact**: The orders table was originally 20GB. Each dead row version is approximately 200 bytes. 36 million dead versions = 36M × 200 bytes = ~7.2GB of dead data. Combined with the ongoing live writes, the table file grows from 20GB toward 28GB+.

But it is worse than raw size: **query performance degrades**. Sequential scans now read the dead versions too (they read every page, including dead-tuple-heavy pages). A scan that used to read 20GB of pages now reads 28GB. That is 40% more I/O for the same logical result.

Index scans also degrade: each index lookup finds the correct xmin/xmax version after following a longer chain, and many lookups require a heap fetch that finds a dead tuple first and must follow the HOT chain to find the live version.

**By 10:00 AM**: The report finishes and commits. The report's old snapshot is released. Now the autovacuum horizon advances to the present. Autovacuum can now see all 36 million dead tuples as cleanable.

But autovacuum still has to catch up — it must scan and process all those pages, which takes another 30-60 minutes. During that cleanup time, table performance is still degraded.

The DBAs notice the degradation in their monitoring dashboards, see the dead tuple count spike, and manually run:

```sql
VACUUM ANALYZE orders;
```

This finishes faster than autovacuum because it runs without intentional throttling (autovacuum intentionally throttles itself to avoid impacting production queries). Within 20 minutes, the dead tuples are cleaned, space is reclaimed, and query performance returns to normal.

### The Root Cause Analysis

The fundamental problem is: **a long-running transaction on the primary database holds a snapshot, and that snapshot prevents autovacuum from cleaning dead tuples**.

This is not a PostgreSQL bug. It is a consequence of MVCC's correctness guarantee: autovacuum cannot clean something that a live transaction might still need to see.

The combination of a long-running read + a high-write table is the perfect storm.

### The Fix

**Short term**: Run manual VACUUM after the report ends. Alert if `pg_stat_user_tables.n_dead_tup` exceeds 10% of `n_live_tup` on high-traffic tables.

**Long term**: Move the analytics query to a **read replica**.

```
BEFORE (problematic):

  Application writes ──► Primary DB ◄── Analytics report query (4 hours)
                            │
                            │  Autovacuum BLOCKED by report's snapshot
                            │
                         Table bloat grows

AFTER (fixed):

  Application writes ──► Primary DB ──► streaming replication ──► Read Replica
                            │                                         │
                            │  Autovacuum runs freely                 │
                            │  (no long snapshot holding it back)     │
                         No bloat                          Analytics report runs here
                                                           (replica has its own
                                                            snapshot, does not
                                                            affect primary's vacuum)
```

On the read replica:
- The report's snapshot is isolated to the replica
- The replica can have its own autovacuum running, but even if it falls behind, it does not affect the primary's performance
- The primary is free to vacuum aggressively

**Additional monitoring to add**:

```sql
-- Find transactions holding back vacuum (ordered by age of snapshot)
SELECT pid, usename, application_name,
       now() - xact_start AS txn_age,
       state, query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY txn_age DESC
LIMIT 10;

-- Check vacuum's "oldest transaction" horizon
SELECT age(backend_xmin), pid, query
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY age(backend_xmin) DESC;
```

Alert when any transaction has been running for more than 30 minutes on the primary, especially during known high-write periods. Automatically terminate queries running longer than 2 hours on the primary with `idle_in_transaction_session_timeout` and `statement_timeout`.

### The Broader Lesson

**Rule**: Long-running transactions on primary = autovacuum killer. Use read replicas for analytics.

This rule has a corollary: any workload that holds a snapshot for an extended period — analytics queries, long ETL processes, slow report generation, even a BEGIN that a developer left open while debugging — will cause table bloat if the table has concurrent writes.

The MVCC design that makes read-write concurrency efficient (no locks!) has this cost: the longer you hold a snapshot, the more old row versions must be preserved for you. In a high-write environment, those old versions accumulate fast.

Design accordingly:
- Analytics on read replicas
- Set `statement_timeout` and `idle_in_transaction_session_timeout` on the primary
- Monitor `pg_stat_activity` for long-running transactions
- Monitor `n_dead_tup` and autovacuum lag
- Alert on transaction ID age approaching 1 billion

---

## Summary: Key Concepts in MVCC and Concurrency Control

Here is a condensed reference for interview recall:

| Concept | One-Line Explanation |
|---------|----------------------|
| MVCC | Multiple row versions coexist; each transaction sees a consistent snapshot |
| xmin / xmax | Hidden per-row metadata: which transaction created/deleted this version |
| Snapshot | Frozen view of committed transactions at a point in time |
| UPDATE = delete + insert | Old version stays (xmax set); new version written (xmin set) |
| HOT update | No index update needed if non-indexed column changes AND new version fits same page |
| Dead tuple | Row version with committed xmax that no active snapshot needs |
| VACUUM | Marks dead tuples reusable; updates FSM and VM |
| VACUUM FULL | Rewrites table; shrinks file; requires exclusive lock |
| Autovacuum | Daemon that runs VACUUM automatically when dead tuple threshold is reached |
| XID wraparound | 32-bit counter wraps at ~4B; frozen rows prevent visibility corruption |
| Freezing | Replace old xmin with FrozenXid; permanently visible to all |
| READ COMMITTED | Each statement gets fresh snapshot (PostgreSQL default) |
| REPEATABLE READ | Snapshot fixed at transaction start; no non-repeatable reads |
| SERIALIZABLE | Full isolation via SSI; detects read-write dependency cycles |
| Write skew | Two transactions read overlapping data, write updates that violate constraints |
| FOR UPDATE | Row-level exclusive lock; blocks other writers |
| Advisory lock | Application-defined named mutex managed by PostgreSQL |
| Deadlock | Circular lock dependency; PostgreSQL detects and kills one transaction |
| Long tx bloat | Long-running primary transaction holds snapshot; autovacuum cannot clean |

---

*End of Chapter 29, Part C: MVCC and Concurrency Control Internals*
# Chapter 29: Database Internals Deep Dive
## Part D: Connection Pooling Internals and Query Execution Internals

---

## 1. The Connection Problem at Scale

Before we can understand why connection pooling exists, we need to understand what
actually happens when your application connects to a database — and why doing that
thousands of times per second is a problem.

### 1.1 PostgreSQL's Process-Per-Connection Model

PostgreSQL has a design philosophy that is unusual compared to most modern software:
**every single database connection gets its own operating system process**. Not a
thread — a full, independent process.

Think about what that means. When your web server opens a connection to PostgreSQL,
the database server literally calls `fork()` to create a brand new OS process just
to handle that one connection. That process exists for the entire lifetime of your
connection. When you disconnect, the process dies.

Why would PostgreSQL do this? The answer is **isolation**. If one connection runs a
buggy query that causes a memory corruption or a segfault, it crashes its own
process — and only its own process. The rest of your connections keep running
normally. With threads, a single crash in one thread can corrupt shared memory and
bring down the entire database server. PostgreSQL's designers decided that the safety
of process isolation was worth the cost in memory and overhead.

Compare this to **MySQL**, which uses **threads** instead of processes. Threads are
cheaper — they share memory with the parent process, so each thread needs maybe
1-2MB of overhead rather than 5-10MB. But threads share memory, which means one
badly behaved thread can corrupt the heap that other threads are using. MySQL bets
that this won't happen in practice; PostgreSQL bets that it might.

Now let's talk about the cost. Each PostgreSQL backend process consumes:

- **5 to 10 MB of RAM** just for existence (stack memory, connection metadata,
  statement cache, prepared statement storage, local working memory)
- A slot in the OS process table
- An entry in PostgreSQL's shared memory structures (lock tables, buffer pool
  tracking, etc.)

Do the math for a heavily loaded database:

```
100 connections  ×  10 MB each  =   1 GB RAM (just for connection overhead)
1000 connections × 10 MB each  =  10 GB RAM
5000 connections × 10 MB each  =  50 GB RAM
```

This is RAM that hasn't fetched a single row of data yet. It's pure overhead just
from connections existing.

And memory is only half the problem. The **OS scheduler** also has to deal with
all these processes. Modern Linux uses a scheduler (CFS — Completely Fair Scheduler)
that gives each runnable process a fair slice of CPU time. With 1000 processes all
wanting CPU, the scheduler has to constantly context-switch between them. Each
context switch costs time and cache pollution. Your processes end up waiting in line
more than they're actually running.

```
    Low connection count:          High connection count:
    
    Process A: [===RUN===][wait]   Process A: [=R=][wait...][=R=]
    Process B: [wait][===RUN===]   Process B: [wait...][=R=][wait]
    Process C: [wait]   [==RUN=]   Process C: [wait........][=R=]
                                   Process D: [wait..........]
                                   Process E: [wait..........]
    
    Fewer processes = more CPU     Many processes = everyone waits
    time per process
```

### 1.2 The Connection Lifecycle: What Actually Happens

Every time your application opens a fresh connection to PostgreSQL, this sequence
of events occurs:

**Step 1 — TCP Handshake (3-way)**

Your application sends a SYN packet to PostgreSQL's port (default: 5432).
PostgreSQL sends back SYN-ACK. Your application sends ACK. The TCP connection is
now open. This costs at least one round-trip across the network — if your app server
and database are in the same data center, maybe 0.1ms. Across regions, 50ms or more.

**Step 2 — SSL/TLS Negotiation (optional but common in production)**

If SSL is configured, the client and server now negotiate a TLS session. This
involves:
- Protocol version negotiation
- Certificate exchange and validation
- Key exchange (Diffie-Hellman or similar)
- Session key derivation

This adds 1-10ms of CPU and network time. TLS 1.3 is faster than TLS 1.2 here
because it reduces the number of round-trips needed.

**Step 3 — Authentication**

PostgreSQL checks `pg_hba.conf` to determine the allowed authentication method for
this client (IP address + database + username combination). Then the client proves
its identity — sending a password (MD5 or SCRAM-SHA-256 hashed), a certificate,
or using trust if configured. Another round-trip or two.

**Step 4 — Backend Process Fork (the expensive part)**

The PostgreSQL **postmaster** (the main coordinator process) calls `fork()` to create
a new backend process for this connection. `fork()` duplicates the postmaster's
memory space — the OS uses copy-on-write, so it's not as expensive as copying all
memory immediately, but it still has cost in setting up page tables, file descriptors,
and signal handlers.

**Step 5 — Session Initialization**

The new backend process sets up the session environment:
- Loads `search_path` (which schemas to look in by default)
- Sets timezone, locale, and encoding
- Initializes the statement cache (for caching query plans)
- Sets up memory contexts (PostgreSQL's internal memory allocator hierarchy)
- Registers the session in shared memory structures

**Step 6 — Client Queries**

Now, finally, the client can send SQL queries. The backend executes them and returns
results. This is the useful work.

**Step 7 — Disconnect**

Client sends a termination message. Backend process exits. OS reclaims all memory
and file descriptors. The connection is gone.

The total cost of steps 1-5 is typically **5 to 50 milliseconds** depending on
network latency, SSL, and server load. Let's see why this is catastrophic at scale:

```
1000 requests/second, each opening a fresh connection:

  1000 requests/sec × 20ms connection setup = 20,000 ms of connection setup per second
                                            = 20 CPU-seconds per second
                                            = 20× a single CPU core just for setup
```

You would need 20 CPU cores doing nothing but establishing connections — before a
single query is executed. This is obviously unsustainable.

### 1.3 Why `max_connections=10000` Destroys PostgreSQL

A common mistake made by engineers who are "solving" the connection problem is
simply raising `max_connections` in `postgresql.conf`. If you're running out of
connections, allow more connections, right?

Wrong. Here is what happens:

**Memory destruction:** PostgreSQL pre-allocates shared memory structures sized for
`max_connections` at startup. Setting `max_connections=10000` means PostgreSQL
allocates:
- Lock tables sized for 10,000 concurrent lock holders
- Procarray (the array tracking all backend processes) sized for 10,000 entries
- Plus the per-connection RAM when those connections actually connect

At 10,000 active connections × 10MB = **100GB RAM just for connection overhead**,
before a single byte of actual data is cached.

**Context switching catastrophe:** The OS scheduler now has to juggle 10,000
processes. Modern servers have 32-64 CPU cores. Dividing CPU time among 10,000
processes means each process gets a tiny time slice, spends most of its time
waiting, and the scheduler itself becomes a bottleneck.

**Shared memory contention:** Many operations require access to shared data
structures — the lock manager, the buffer pool (shared_buffers), the WAL write
lock. With 10,000 processes all trying to take and release locks, the lock
contention becomes severe. Processes spend more time waiting for locks than doing
actual work.

**The trap:** When someone says "just increase max_connections," they are confusing
the symptom (connection limit reached) with the solution (stop creating so many
connections). The real solution is a connection pool.

---

## 2. Connection Pooling: The Fix

### 2.1 What a Connection Pool Is

A **connection pool** is a piece of software that sits between your application and
your database. Its job is simple: maintain a fixed number of pre-established
database connections, and lend them to application threads as needed, then take them
back when done.

The best analogy is a **taxi dispatch service**:

Without a pool, every person who needs a ride has to hail a new cab — the cab has
to drive to them (TCP connection), the driver has to verify their identity
(authentication), the cab company has to register the trip (session initialization),
and then finally you ride (execute your query). When you arrive, the cab is
destroyed.

With a pool, the dispatch center keeps 20 taxis running and warmed up at the taxi
stand. You call the dispatch center (ask the pool for a connection), they hand you a
cab from the stand instantly (no setup cost), you take your ride (run your query),
and the cab returns to the stand (connection returned to pool) for the next customer.

```
WITHOUT CONNECTION POOL:
=====================================================================

 App Server                                    PostgreSQL
 
 Thread 1 ----[TCP+TLS+Auth+Fork = 20ms]-----> Backend Proc 1
 Thread 2 ----[TCP+TLS+Auth+Fork = 20ms]-----> Backend Proc 2
 Thread 3 ----[TCP+TLS+Auth+Fork = 20ms]-----> Backend Proc 3
 Thread 4 ----[TCP+TLS+Auth+Fork = 20ms]-----> Backend Proc 4
 ...
 Thread 1000 -[TCP+TLS+Auth+Fork = 20ms]-----> Backend Proc 1000
 
 1000 backend processes = ~10GB RAM overhead

WITH CONNECTION POOL (PgBouncer):
=====================================================================

 App Server                 PgBouncer Pool           PostgreSQL
 
 Thread 1    --[instant]--> |          |             Backend Proc 1
 Thread 2    --[instant]--> |  Pool of |             Backend Proc 2
 Thread 3    --[instant]--> |  20 pre- |-----------> Backend Proc 3
 Thread 4    --[instant]--> |  warmed  |             Backend Proc 4
 Thread 5    --[instant]--> |  conns   |             ...
 ...                        |          |             Backend Proc 20
 Thread 1000 --[instant]--> |__________|
 
 Only 20 backend processes = ~200MB RAM overhead
 Threads 21-1000 wait in queue for <1ms until a connection frees up
```

The pool handles the 5-50ms connection setup once, at startup. Application threads
never pay that cost again.

### 2.2 PgBouncer: The Most Common PostgreSQL Pooler

**PgBouncer** is a lightweight, battle-tested connection pooler specifically for
PostgreSQL. It's written in C and is single-threaded, using `libevent` for
non-blocking I/O — this means it can handle thousands of client connections with
almost no CPU overhead (it's not doing query execution, just routing bytes).

PgBouncer offers three pooling modes, each with different behavior and trade-offs.
Understanding these modes is critical for L6 interviews because choosing the wrong
mode causes subtle bugs.

#### 2.2.1 Session Pooling Mode

In **session pooling mode**, each client connection is assigned one PostgreSQL
backend process for the entire duration of the client's session. The backend is
returned to the pool only when the client disconnects.

```
CLIENT SESSION POOLING:

Client A connects  --> PgBouncer assigns Backend #1 to Client A
                        [Client A uses Backend #1 for entire session]
Client A disconnects -> Backend #1 returned to pool

Client B connects  --> PgBouncer assigns Backend #2 to Client B
                        [Client B uses Backend #2 for entire session]
```

**What works:** Everything. Prepared statements, temporary tables, SET commands that
affect the session, advisory locks, LISTEN/NOTIFY — all work exactly as if you had
connected directly to PostgreSQL.

**What it solves:** It avoids the per-connection setup cost (TCP, TLS, auth, fork)
by keeping connections alive in the pool between client sessions.

**What it doesn't solve:** If your application maintains 500 long-lived connections,
you still have 500 PostgreSQL backend processes. Session pooling only helps if your
application frequently disconnects and reconnects (each reconnect gets a pre-warmed
connection instead of paying setup cost).

**Best for:** Traditional web applications with moderate concurrency, where clients
hold connections for seconds to minutes and the total number of concurrent clients
is manageable (say, under 200).

#### 2.2.2 Transaction Pooling Mode (Most Common in Production)

This is where PgBouncer gets truly powerful. In **transaction pooling mode**,
a PostgreSQL backend is assigned to a client only for the duration of a single
transaction. The moment the client sends `COMMIT` or `ROLLBACK`, the backend goes
back to the pool — even if the client is still connected.

```
TRANSACTION POOLING: 3 backends serving 6 clients

Time --> 

Backend #1: [Client A Txn][Client D Txn][Client A Txn][Client F Txn]...
Backend #2: [Client B Txn][Client B Txn][Client E Txn][Client B Txn]...
Backend #3: [Client C Txn][Client F Txn][Client C Txn][Client E Txn]...

All 6 clients are "connected" to PgBouncer continuously.
They just take turns using the 3 real PostgreSQL backends.
```

The key insight: most applications spend the vast majority of their time in
application code, not inside database transactions. A web request might take 100ms
total, but only 5ms of that is an active database transaction. During the other
95ms, a direct-connection backend would be sitting idle. Transaction pooling
reclaims that idle time.

In practice, **3 to 10 PostgreSQL connections can serve hundreds or even thousands
of application clients** if transactions are short.

**What breaks in transaction pooling mode:**

This is the list you need to memorize for interviews. These features are
**session-scoped** — they're tied to a specific PostgreSQL backend process. Since
transaction pooling can route different transactions to different backends, anything
session-scoped breaks:

| Feature | Why It Breaks | Workaround |
|---|---|---|
| Named prepared statements | Prepared statements stored in backend session; next transaction may go to different backend | Use protocol-level unnamed prepared statements, or DEALLOCATE after each txn |
| `SET search_path = myschema` | SET affects the session; next transaction gets a different backend with default search_path | Set in connection string or use schema-qualified names |
| Advisory locks | `pg_advisory_lock()` tied to session; lock disappears when backend is reassigned | Use advisory locks only in session pooling mode |
| `LISTEN`/`NOTIFY` | LISTEN subscription lives on the session | Use a dedicated direct connection for pub/sub |
| Temporary tables | Temp table lives in backend session | Use regular tables with a session UUID column |
| `WITH HOLD` cursors | Cursor open across transactions lives in session | Don't use WITH HOLD cursors |

**The prepared statements problem explained in depth:**

When you use prepared statements with transaction pooling, here is what goes wrong:

```sql
-- Client A sends to PgBouncer:
PREPARE my_stmt AS SELECT * FROM users WHERE id = $1;

-- PgBouncer routes this to Backend #1.
-- Backend #1 now has "my_stmt" prepared.

-- Client A's transaction commits. Backend #1 returned to pool.

-- Client A starts a new transaction. PgBouncer assigns... Backend #3.
-- (Backend #1 is busy with Client B's transaction)

-- Client A sends:
EXECUTE my_stmt(42);

-- Backend #3 has never seen "my_stmt". Error:
-- ERROR: prepared statement "my_stmt" does not exist
```

The fix most production systems use: **JDBC, psycopg, and other drivers have
a "simple query" mode** where they don't use named prepared statements and instead
re-send the full SQL each time. This is less efficient than true prepared statements
but works correctly with transaction pooling.

#### 2.2.3 Statement Pooling Mode

In **statement pooling mode**, the backend is returned to the pool after each
individual SQL statement — not after each transaction. This means you cannot have
multi-statement transactions at all, because each statement goes to potentially a
different backend.

```sql
-- This breaks completely in statement pooling:
BEGIN;
  UPDATE accounts SET balance = balance - 100 WHERE id = 1;  -- Goes to Backend #1
  UPDATE accounts SET balance = balance + 100 WHERE id = 2;  -- Goes to Backend #2 !!!
COMMIT;                                                        -- Goes to Backend #3 ???

-- The two UPDATEs are now in different transactions on different backends.
-- This is NOT atomic. This is data corruption.
```

Statement pooling only works for workloads where every query is auto-committed
(no explicit transactions needed). This is rare in real applications. You might use
it for simple read-only analytics queries but almost never for OLTP.

### 2.3 Pool Sizing: The Science Behind the Magic Number

How many connections should your pool maintain? This is a question with a
non-obvious answer. Most engineers' instinct is "more connections = more throughput."
The research and practice says the opposite: **too many connections hurts throughput**.

The most famous formulation comes from database performance research:

```
optimal_connections = num_cpu_cores × 2 + effective_spindle_count
```

Where:
- `num_cpu_cores` = physical CPU cores on the database server
- `effective_spindle_count` = number of independent disk spindles (1 for SSD, N for N spinning disks in a RAID that can seek in parallel)

**Example: 16-core PostgreSQL server with NVMe SSD storage:**

```
optimal_connections = 16 × 2 + 1 = 33
```

Thirty-three connections. That's it. For a powerful 16-core server, you want about
33 active connections.

**Why so few?**

PostgreSQL's bottleneck is not "waiting for a connection to be available." It's
**CPU execution** (query processing, hashing, sorting) and **I/O** (reading pages
from disk into the buffer cache). More connections than you have cores means those
connections are waiting for CPU — they're in the scheduler's run queue, not doing
useful work. They just add context switching overhead.

Think of it like a highway with 4 lanes. If you put 4 cars on it, they all drive
at full speed. If you put 400 cars on it, they're all stuck in traffic — the number
of cars doesn't increase the road's throughput, it decreases it.

```
THROUGHPUT VS CONNECTIONS (for a 4-core server):

Queries/sec
    ^
300 |          **** (peak around 8-10 connections)
    |       ***    ***
200 |     **          **
    |   **              ***
100 |  *                   ****
    | *                        ****
  0 +----+----+----+----+----+----+----> Connections
    0    5   10   20   50  100  500

More connections past the peak = more context switching = lower throughput
```

**PgBouncer's own pool should be sized to match this optimal PostgreSQL connection
count**, not the number of application threads. If your PostgreSQL server needs 33
connections, configure PgBouncer with a pool of 33 connections to PostgreSQL —
regardless of how many client applications are connecting to PgBouncer.

**What happens when all pool connections are busy?** PgBouncer queues the client
request. The client waits (milliseconds to seconds) until a connection is available.
This is vastly better than the alternative (creating more connections and slowing
everyone down). You tune `pool_mode`, `pool_size`, `query_wait_timeout` to control
queuing behavior.

---

## 3. Query Execution: From SQL String to Results

Now we go inside the database. You have a connection. You send a SQL string.
What does PostgreSQL actually do with it?

### 3.1 The Four Stages of Query Execution

Every SQL query travels through four distinct stages before you see a result:

```
SQL Text (string)
        |
        v
  +----------+
  |  PARSING |   "Is this valid SQL? What does it mean?"
  +----------+
        |
        v Abstract Syntax Tree (AST)
  +----------+
  | PLANNING |   "What data do I need and how can I get it?"
  +----------+
        |
        v
  +------------+
  |OPTIMIZATION|   "Of all the ways to get that data, which is cheapest?"
  +------------+
        |
        v Query Plan (execution tree)
  +----------+
  |EXECUTION |   "Actually read the data, run the computation, return rows"
  +----------+
        |
        v Result rows
```

### 3.2 Stage 1 — Parsing

The input to the parser is a raw SQL string. The parser's job is to turn that
string into a structured data representation that the rest of the system can work
with.

**The lexer** (lexical analyzer) runs first. It reads the SQL text character by
character and groups characters into **tokens** — meaningful units. For example:

```sql
SELECT * FROM users WHERE id = 42
```

Becomes the token stream:

```
[SELECT] [*] [FROM] [users] [WHERE] [id] [=] [42]
  ^kw    ^op   ^kw    ^ident   ^kw   ^ident ^op ^int
```

Each token has a type (keyword, identifier, operator, literal) and a value.

**The parser** then takes the token stream and checks it against PostgreSQL's
grammar rules. SQL has a formal grammar — a set of rules that say things like
"a SELECT statement consists of SELECT, then a target list, then FROM, then a
table reference, then optionally WHERE, then optionally GROUP BY..." and so on.

The parser checks that the token stream matches the grammar, and if it does, it
builds an **Abstract Syntax Tree (AST)** — a tree where each node represents a
grammatical construct.

```
For: SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id WHERE u.age > 18

                        SelectStmt
                       /          \
              TargetList          FromClause
             /        \           /       \
        FieldRef    FieldRef   JoinExpr   WhereClause
        u.name      o.total   /   |   \      |
                           users  ON  orders  >
                              u  u.id=  o   age 18
                                  o.user_id
```

If your SQL has a syntax error, the error happens here and you see a message like:
`ERROR: syntax error at or near "FORM"` — the parser couldn't match the tokens
to the grammar.

What the parser does NOT check: whether the table `users` actually exists, whether
column `id` is in that table, or whether you have permission to read it. Those
checks come later.

### 3.3 Stage 2 — Analysis and Rewriting

After parsing, PostgreSQL's **analyzer** (sometimes called the semantic analysis
phase) resolves names:

- It looks up `users` in `pg_class` to verify the table exists and get its OID
  (Object Identifier — PostgreSQL's internal ID for everything)
- It resolves column names to their actual column positions in the table
- It checks data types and inserts implicit casts where needed
- It checks permissions

Then the **rewriter** applies rules. PostgreSQL has a rule system (primarily used
to implement views). When you query a view, the rewriter replaces the view reference
with the view's definition — so the planner sees the underlying tables directly.

### 3.4 Stage 3 — Planning and Optimization (The Deep Part)

The planner receives the analyzed query tree. Its job is to figure out the best way
to execute the query. For any non-trivial query, there are many possible execution
strategies — different orderings of joins, different methods for each join, different
index choices. The planner's job is to estimate the cost of each option and pick
the cheapest.

#### 3.4.1 Statistics: What the Planner Knows About Your Data

The planner doesn't execute the query to decide how to execute it — that would be
circular. Instead, it relies on **statistics** that PostgreSQL has collected about
your tables and columns.

These statistics live in the system catalog table `pg_statistic` (and its
human-readable view `pg_stats`). They are gathered by the `ANALYZE` command (which
you can run manually) and by **autovacuum** (a background process that runs
automatically).

For each column in each table, PostgreSQL stores:

**`n_distinct`:** The estimated number of distinct values in the column.
- Positive value: exact count (e.g., 50 distinct countries)
- Negative value: fraction of rows that are distinct (e.g., -0.99 means 99% of
  values are unique — like a primary key or UUID column)

**`histogram_bounds`:** An array of values that divide the column's data into
equal-frequency buckets (quantiles). For example, if the histogram for an `age`
column is `[18, 25, 32, 41, 55, 90]`, that tells you roughly 20% of values fall
in each bucket between those bounds. The planner uses this to estimate how many
rows `WHERE age BETWEEN 25 AND 32` would return.

**`most_common_vals` and `most_common_freqs`:** The top-N most frequent values and
their frequency (fraction of all rows). If `country = 'US'` has `most_common_freqs`
of 0.45, the planner knows 45% of rows have country='US'.

**`null_frac`:** Fraction of rows where this column is NULL.

**`avg_width`:** Average size in bytes of a value in this column (used to estimate
memory usage for sorting and hashing).

Using these statistics, the planner can make an **estimate** of the number of rows
that any given filter predicate will return. This estimate is called the
**cardinality estimate**, and it's the single most important input to the query
optimizer. A bad cardinality estimate leads to a bad plan choice, which leads to
slow queries.

**Stale statistics = bad plans.** If you bulk-load 10 million new rows and
then immediately run a complex query before autovacuum has had a chance to re-analyze
the table, the planner is working with outdated statistics. It might think the table
has 100,000 rows when it actually has 10,100,000 rows — and make completely wrong
decisions as a result.

#### 3.4.2 Scan Types: How Rows Are Actually Fetched

For each table in the query, the planner has to decide how to read the rows it
needs. There are four scan strategies:

**Sequential Scan (Seq Scan)**

The simplest method: read every single page of the table, from first to last, in
physical order. Return the rows that match the WHERE clause, discard the rest.

```
Table pages on disk:  [Page 1][Page 2][Page 3]...[Page N]
Seq Scan:             Read --> Read --> Read --> ... --> Read (all N pages)
Return: rows where condition is true
```

- Cost: proportional to table size (number of pages)
- Excellent I/O efficiency: reads pages sequentially, which is fast on both
  spinning disks (no seeking) and SSDs (predictable access pattern, prefetching)
- Best when: returning more than 5-10% of the table's rows, or when the table
  is small enough to fit in `shared_buffers`

**Index Scan**

Uses a B-tree (or other) index to find the exact locations of matching rows, then
fetches each row from the heap (the main table data).

```
Index (B-tree on user_id):
          [50]
         /    \
      [25]    [75]
      / \      / \
  [10][20] [60][80]  <-- leaf nodes have: key + heap pointer (page, offset)

Index Scan for user_id = 42:
  1. Walk B-tree to find 42 --> heap pointer: (page 17, slot 3)
  2. Fetch page 17 from heap, extract slot 3
  3. Return that one row
```

- Cost: O(log N) to traverse the index + one random heap page read per matching row
- Excellent for high-selectivity queries (returning <1-5% of rows)
- Bad for low-selectivity queries: 100,000 matching rows = 100,000 random page reads,
  which is slower than a sequential scan of the whole table

**Index Only Scan**

If the query's SELECT list and WHERE clause can be answered entirely from the index
(no need to look at the heap), PostgreSQL can skip the heap reads entirely.

```sql
-- Index on (email, name) columns:
SELECT name FROM users WHERE email = 'alice@example.com';

-- The index has both email (for filtering) and name (for returning).
-- PostgreSQL never needs to touch the heap table at all.
```

This is extremely fast — it avoids all heap I/O. The catch: PostgreSQL needs to
check the **visibility map** to confirm that all relevant heap pages have no dead
tuples (rows deleted but not yet vacuumed). If the visibility map says a page might
have dead tuples, PostgreSQL falls back to checking the heap for that page anyway
(to ensure MVCC correctness).

Keep tables well-vacuumed and your index-only scans stay fast.

**Bitmap Scan**

The bitmap scan is a clever two-phase approach that bridges the gap between index
scans (great for very few rows) and sequential scans (great for many rows):

```
Phase 1 - Bitmap Index Scan:
  Walk the index for all matching entries.
  Instead of fetching heap rows immediately, build an in-memory BITMAP
  where each bit represents one heap page.
  Set the bit for each page that contains at least one matching row.

  Bitmap (256 pages total):
  Page: 1  2  3  4  5  6  ...  89  ...  134 ...  256
  Bit:  0  0  1  0  1  0  ...   1  ...    0 ...    1

Phase 2 - Bitmap Heap Scan:
  Iterate through set bits in page-number order.
  Fetch those pages from the heap (in sequential order!).
  For each page, check which rows actually match the condition.
  Return matching rows.
```

Why is this better than a plain index scan for medium selectivity?

Plain index scan returns rows in index order (e.g., sorted by id), which may
require jumping all over the heap in random page order. If 10% of a 10GB table
matches, that's 100,000 random I/Os.

Bitmap scan collects all the page numbers, sorts them, and reads them in ascending
page order. This converts random I/O into nearly sequential I/O. On a spinning disk,
this is 10-100x faster. Even on SSDs, it's significantly better.

The trade-off: building the bitmap takes memory. If the bitmap gets too large for
`work_mem`, PostgreSQL degrades to a "lossy" bitmap (where a set bit means "this
page probably has matching rows" rather than "definitely has matching rows") — the
Bitmap Heap Scan then has to re-check every row on those pages.

```
SCAN TYPE COMPARISON:

                    Selectivity (fraction of rows returned)
                    0.001%    0.1%     1%      10%     100%
                      |        |        |        |        |
Index Only Scan:  [BEST][---GREAT---][GOOD]
Index Scan:       [GREAT][--GOOD--][OK][BAD]
Bitmap Scan:               [GOOD][--GREAT--][GOOD][OK]
Sequential Scan:                          [OK][GOOD][BEST]

Rule of thumb:
  <1% rows   --> Index Scan or Index Only Scan
  1-10% rows --> Bitmap Scan  
  >10% rows  --> Sequential Scan (usually)
```

#### 3.4.3 Join Algorithms

When a query involves multiple tables (a JOIN), the planner must decide:
1. Which table to process first (join order)
2. How to combine each pair of tables (join algorithm)

There are three join algorithms in PostgreSQL:

**Nested Loop Join**

The most intuitive algorithm. For every row in the **outer table**, scan the
**inner table** to find matching rows.

```
Nested Loop Join: orders JOIN users ON orders.user_id = users.id

OUTER: orders (10,000 rows)
INNER: users (1,000 rows)

FOR each order in orders (10,000 iterations):
    FOR each user in users (1,000 iterations):
        IF order.user_id == user.id:
            output (order, user)

Total iterations: 10,000 × 1,000 = 10,000,000 comparisons
```

This looks terrible for large tables, and it is — unless the inner loop uses an
index. With an index on `users.id`:

```
FOR each order in orders (10,000 iterations):
    INDEX SCAN on users where id = order.user_id  (O(log 1000) ≈ 10 comparisons)

Total: 10,000 × 10 = 100,000 comparisons -- much better!
```

Nested loop with index lookup is often the fastest join for small result sets or
when one side of the join is small.

**Hash Join**

The workhorse for joining two large tables with an equality condition:

```
Hash Join: orders JOIN users ON orders.user_id = users.id

Phase 1 - Build:
  Read all rows from the SMALLER table (users, 1,000 rows).
  Build a hash table in memory:
  hash_table[hash(user.id)] = user_row
  
  Hash table: { 1: {id:1, name:"Alice"}, 2: {id:2, name:"Bob"}, ... }

Phase 2 - Probe:
  Read each row from the LARGER table (orders, 10,000 rows).
  For each order: look up hash_table[hash(order.user_id)]
  If found: output (order, user)
  
Total work: O(N + M) where N=1000, M=10000 = 11,000 operations
```

Hash join is fast because it's linear in the total number of rows. The critical
requirement: **the hash table (built from the smaller side) must fit in `work_mem`**.

If the hash table is too large:
- PostgreSQL splits both sides into multiple **batches** based on a hash function
- Each batch is written to disk temporarily
- Batches are processed one at a time (read from disk, process in memory)
- This is called a "hash batch spill" and is far slower — you're now doing disk I/O

You can see this in EXPLAIN ANALYZE output:

```
Hash  (cost=...) (actual time=... rows=...)
  Buckets: 1024  Batches: 8  Memory Usage: 4096kB
                 ^^^^^^^
  Batches: 8 means it spilled to disk (Batches: 1 means fully in memory)
```

If you see many batches, increase `work_mem` for that session.

**Merge Join**

Merge join works like the merge phase of merge sort. Both input sides must be
**sorted** on the join key. Then you merge them in a single linear pass:

```
Merge Join: orders JOIN users ON orders.user_id = users.id
(Both sides sorted by the join key)

orders sorted by user_id: [(1,Ord-A), (1,Ord-B), (2,Ord-C), (3,Ord-D), ...]
users sorted by id:        [(1,Alice),            (2,Bob),   (3,Carol), ...]

Merge step:
  Both pointers start at beginning.
  Compare current order.user_id vs current user.id:
  - If equal: output combined row, advance order pointer
  - If order.user_id < user.id: advance order pointer (no match for this order)
  - If order.user_id > user.id: advance user pointer (no match for this user)
  
Total work: O(N + M) for the merge step.
Plus sorting cost if not already sorted: O(N log N + M log M)
```

Merge join is ideal when the join columns already have an index (data is pre-sorted
in index order). In that case, both sides can be read from their indexes in sorted
order — no sort step needed — and the merge is essentially free.

If neither side is pre-sorted, the planner has to sort both sides first, which
costs `O(N log N + M log M)`. In that case, hash join is usually cheaper for
large tables.

```
JOIN ALGORITHM SELECTION GUIDE:

Condition                        Best Algorithm
------------------------------------------------------------
One table is very small          Nested Loop Join
  (fits in a few pages)

Both tables large, equality      Hash Join (if fits in work_mem)
  join, no pre-existing sort

Both tables sorted on join key   Merge Join
  (index exists on join column)

Inner table has index on         Nested Loop + Index Lookup
  join column, outer is small

Hash table spills to disk        Consider increasing work_mem
                                 or rewriting to reduce rows
                                 before joining
```

### 3.5 Reading EXPLAIN ANALYZE Output

`EXPLAIN ANALYZE` is your most important diagnostic tool. It shows you the exact
execution plan PostgreSQL chose AND the actual execution statistics. You must be
able to read it.

```sql
EXPLAIN ANALYZE
SELECT u.name, COUNT(o.id) as order_count
FROM users u
JOIN orders o ON u.id = o.user_id
WHERE u.country = 'US'
GROUP BY u.name;
```

Example output (simplified):

```
Finalize GroupAggregate  (cost=8000..9000 rows=500 width=40)
                         (actual time=95.2..102.3 rows=487 loops=1)
  Group Key: u.name
  ->  Gather Merge  (cost=7000..8500 rows=1000 width=40)
                    (actual time=88.1..96.4 rows=1462 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        ->  Sort  (cost=6000..6500 rows=500 width=40)
                  (actual time=71.2..72.1 rows=487 loops=3)
              Sort Key: u.name
              Sort Method: quicksort  Memory: 68kB
              ->  Partial HashAggregate  (cost=5000..5500 rows=500 width=40)
                                        (actual time=60.1..65.3 rows=487 loops=3)
                    ->  Hash Join  (cost=2000..4000 rows=50000 width=24)
                                  (actual time=12.3..55.1 rows=51200 loops=3)
                          Hash Cond: (o.user_id = u.id)
                          Buffers: shared hit=8420 read=312
                          ->  Seq Scan on orders  (cost=0..3000 rows=300000)
                                                  (actual time=0.1..20.4 rows=300000 loops=3)
                          ->  Hash  (cost=1800..1800 rows=16000 width=16)
                                   (actual time=11.8..11.8 rows=15940 loops=3)
                                Buckets: 16384  Batches: 1  Memory Usage: 890kB
                                ->  Seq Scan on users  (cost=0..1800 rows=16000 width=16)
                                                       (actual time=0.1..8.3 rows=15940 loops=3)
                                      Filter: (country = 'US'::text)
                                      Rows Removed by Filter: 44060
```

Let's decode each piece:

**`(cost=8000..9000 rows=500 width=40)`:** The planner's estimate.
- `cost=8000..9000`: arbitrary cost units (startup cost .. total cost). Higher is more expensive. These are relative, not milliseconds.
- `rows=500`: planner estimates this node will return 500 rows
- `width=40`: average row size in bytes

**`(actual time=95.2..102.3 rows=487 loops=1)`:** What actually happened.
- `actual time=95.2..102.3`: milliseconds from query start to first row .. to last row
- `rows=487`: actually returned 487 rows (vs estimate of 500 — pretty close, good plan!)
- `loops=1`: this node executed 1 time

**`loops=3` on inner nodes:** The parallel workers. With 2 workers + 1 leader = 3
total, each does 1/3 of the work. The `rows` and `time` shown are per-loop, so
multiply by `loops` for total. `rows=487 loops=3` means 1,461 total rows processed.

**`Buffers: shared hit=8420 read=312`:** Cache statistics.
- `shared hit=8420`: 8,420 pages found in `shared_buffers` (fast, no disk I/O)
- `read=312`: 312 pages had to be read from disk (slow)
- A high `read` count relative to `hit` count indicates the working set doesn't
  fit in `shared_buffers` — consider increasing it or adding indexes.

**`Rows Removed by Filter: 44060`:** On the users Seq Scan, 44,060 rows were read
and discarded (didn't match `country = 'US'`). Only 15,940 matched. If this filter
is very selective, an index on `users.country` might help — but at 26% selectivity
(15,940 / 60,000), a seq scan is probably still correct.

**Spotting a bad plan:** Look for large discrepancies between `rows=X` (estimate)
and `actual rows=Y` (reality). If the planner estimates 100 rows but 50,000 come
out, it probably made wrong choices downstream — it might have chosen a nested loop
(good for 100 rows) that is terrible for 50,000 rows. This is the signature of
stale statistics or a data skew problem.

### 3.6 Parallel Query Execution

For large analytical queries, PostgreSQL can use multiple CPU cores simultaneously
to scan a table or execute a hash join.

```
Sequential Execution:          Parallel Execution:
                               
 [Table: 10M rows]              [Table: 10M rows]
        |                       /       |       \
 [Worker: 1 process]    [W1]  [W2]  [W3]  [W4]
   reads all 10M rows   reads  reads  reads  reads
   in ~10 seconds       2.5M   2.5M   2.5M   2.5M
                           \     |     |    /
                            [Gather Node]
                             merges results
                             ~2.5 seconds total
```

The **Gather** node (or **Gather Merge** for sorted output) is the coordinator.
It launches N parallel worker processes, assigns each a portion of the work, and
collects their results.

Key configuration parameters:

```
max_parallel_workers_per_gather = 4  -- max workers for one query node
max_parallel_workers = 8             -- total parallel workers across all queries
min_parallel_table_scan_size = 8MB   -- table must be this big to use parallelism
parallel_tuple_cost = 0.1            -- cost to pass one tuple between workers
```

**When parallel query helps:**
- Large sequential table scans
- Hash joins where both sides are large
- Aggregations (COUNT, SUM, AVG) over large tables

**When parallel query does NOT help:**
- Index scans: the index is accessed serially (too much coordination overhead
  to parallelize random index lookups effectively)
- Small tables: the overhead of launching workers exceeds the savings
- Write operations: INSERT, UPDATE, DELETE are not parallelized by workers
- Queries inside functions marked `PARALLEL UNSAFE`

---

## 4. Prepared Statements: Parse Once, Execute Many

Every time you send an unparameterized SQL string to PostgreSQL, it goes through
all four stages — parse, analyze, plan, execute — even if you've run that exact
query structure a thousand times before. For simple OLTP queries (insert a row,
look up a row by primary key) that you're running at 10,000 per second, this
overhead adds up.

**Prepared statements** allow you to separate the parse/plan phase from the
execute phase:

```sql
-- Step 1: Prepare (parse + plan, done once)
PREPARE lookup_user (integer) AS
  SELECT id, name, email FROM users WHERE id = $1;

-- Step 2: Execute (just execution, done many times)
EXECUTE lookup_user(42);
EXECUTE lookup_user(7);
EXECUTE lookup_user(1001);
```

After `PREPARE`, PostgreSQL stores the query plan in the backend session's memory
under the name `lookup_user`. Each `EXECUTE` just runs that cached plan with the
given parameter values — no parsing, no planning.

The performance benefit is most significant for:
- **High-frequency simple queries:** If you're doing 10,000 single-row lookups per
  second, eliminating the planning step (say, 0.1ms per query) saves 1 full CPU
  second per second of throughput.
- **Complex queries:** Planning a join over 5 tables with multiple indexes can take
  10-50ms. If you run that query repeatedly with different parameters, preparing it
  once is a significant win.

**The lifecycle:**

```
Application                              PostgreSQL Backend
                                         
PREPARE lookup_user AS SELECT...   -->   Parse SQL
                                         Plan query
                                         Store plan as "lookup_user" in session
                                   <--   OK, ready
                                   
EXECUTE lookup_user(42)            -->   Look up "lookup_user" plan
                                         Bind parameter: $1 = 42
                                         Execute plan
                                   <--   Result rows
```

**The Connection Pool Problem with Prepared Statements:**

In transaction pooling mode, the prepared statement is stored in a specific backend
session. When the transaction ends and the connection is returned to the pool, that
backend might be reassigned to a different client. The next time your client tries
to EXECUTE the same prepared statement, it might be on a backend that has never seen
the PREPARE command.

```
Session (transaction pooling):

Transaction 1:
  Client connects to PgBouncer.
  PgBouncer assigns Backend #7.
  Client: PREPARE stmt1 AS SELECT ...  --> Stored in Backend #7
  Client: EXECUTE stmt1(42)            --> Works fine (same session)
  Client: COMMIT
  Backend #7 returned to pool.

Transaction 2:
  Client asks PgBouncer for connection.
  Backend #7 is busy. PgBouncer assigns Backend #3.
  Client: EXECUTE stmt1(42)  --> ERROR: prepared statement "stmt1" does not exist
  (Backend #3 never saw the PREPARE command)
```

**Solutions in production:**

1. **Use protocol-level unnamed prepared statements:** Most database drivers
   (JDBC, psycopg3, libpq) support a "simple query" or "unnamed prepared statement"
   mode where the driver sends the PREPARE without a name, PostgreSQL plans it, uses
   it for that one EXECUTE, then discards it. This gets the planning benefit within
   a transaction without leaving named prepared statements in the session.

2. **Use PREPARE + DEALLOCATE in the same transaction:**
   ```sql
   BEGIN;
   PREPARE my_stmt AS SELECT ...;
   EXECUTE my_stmt(42);
   DEALLOCATE my_stmt;
   COMMIT;
   ```
   Tedious but compatible with transaction pooling.

3. **Use session pooling instead of transaction pooling** for applications that
   rely heavily on prepared statements. Accept the trade-off in scalability.

4. **Configure PgBouncer's `max_prepared_statements`** (added in PgBouncer 1.21):
   PgBouncer can now intercept and track prepared statements itself, re-preparing
   them on whatever backend is assigned. This removes the trade-off in modern
   PgBouncer versions — transaction pooling and prepared statements can coexist.

---

## 5. Real Incident: Query Plan Regression After Data Skew

This is a real category of production incident that happens more frequently than
you'd expect, and understanding it in depth will serve you well in interviews.

### 5.1 Setup

A social platform has a `users` table with 100 million rows. They have a query
that runs constantly — finding users by their country code for regional targeting:

```sql
SELECT id, name, email, created_at
FROM users
WHERE country = $1
ORDER BY created_at DESC
LIMIT 100;
```

There is an index on `(country, created_at DESC)` — a composite index designed
specifically to answer this query efficiently.

**Initial state (6 months ago when the index was created):**

The platform was new. Users from many countries signed up, but no country dominated.
The distribution was roughly:
- 'US': 15% of users (15 million rows)
- 'IN': 12% of users (12 million rows)
- 'BR': 8% of users (8 million rows)
- ... 200 other countries split the remaining 65%

Statistics showed `country = 'US'` would return about 15% of rows.

**Planner's decision at that time:**

For `country = 'US'`, 15% of 100M = 15M rows. The query has a LIMIT 100, so
PostgreSQL only needs the 100 most recent of those 15M rows. The index on
`(country, created_at DESC)` is perfect: scan the index range for country='US',
return the first 100 rows (which are already sorted by created_at DESC). Extremely
efficient. Query time: **8ms**.

### 5.2 The Data Change

Six months of aggressive US marketing and user growth later:
- 'US': 85% of users (now 85 million rows out of 100M)
- 'IN': 5% (still 12M rows — total grew)
- Everyone else: 10%

A large data migration was done over a weekend: 70M new US users were imported
from an acquisition. The migration completed successfully... but no one ran
`ANALYZE users` afterward. The autovacuum daemon was set to run every 24 hours
with default settings.

**PostgreSQL's statistics still say:** `country = 'US'` appears in 15% of rows.

### 5.3 The Plan Regression

On Monday morning, traffic resumed. The query `WHERE country = 'US'` is now
being planned against stale statistics.

**Planner's (incorrect) reasoning:**

"country = 'US' returns 15% of 100M rows = 15M rows. With the LIMIT 100, I should
use the composite index on (country, created_at DESC) to directly get the 100 most
recent rows. Cost estimate: ~50ms (my model says index scan for 100 rows from 15M
takes about this long based on I/O costs)."

**What actually happens at execution:**

The index is scanned. The index is correct — it points to the actual heap rows
matching `country = 'US'`. There are now 85 million such rows. But the planner
didn't know that when it chose the plan.

Wait — if the planner chose an index scan with LIMIT 100, why is it slow? The
LIMIT 100 means PostgreSQL can stop after finding 100 rows in the index. This
should still be fast, right?

**The killer detail:** The LIMIT interacts with plan choice in a subtle way. In
this case, let's say the query also involves a join or a filter that the index
cannot fully satisfy. Or perhaps the index was not the actual issue — let's look
at a slightly different scenario that's even more common:

**Alternative incident pattern (same statistics problem, different manifestation):**

```sql
-- A different query, no LIMIT:
SELECT country, COUNT(*) as cnt
FROM users
GROUP BY country;
```

Statistics say `country` has 200 distinct values (n_distinct = 200). Planner
plans a HashAggregate: reads all rows, builds a hash table keyed by country.

After migration, there are now only 3 practically significant countries, but the
hash table approach is still fine. The real problem: the planner's row estimates
for downstream operations are way off.

**The original incident (back to it):**

```sql
SELECT * FROM users WHERE country = 'US' AND is_premium = true;
```

Planner estimates:
- `country = 'US'`: 15% of 100M = 15M rows
- `is_premium = true`: 5% of users are premium = 5M rows
- Combined (assuming independence): 15% × 5% = 0.75% of 100M = 750,000 rows

Planner chooses: **nested loop** using index on `is_premium` (since 5% selectivity
is good for an index), then filter by country.

**Reality:**
- `country = 'US'`: 85% of rows = 85M rows
- Combined: 85% × 5% = 4.25% = 4.25M rows

The planner expected 750,000 rows from the inner side of the nested loop. It got
4.25M. Instead of 750,000 index look-ups into the heap, there are 4.25M. Each is
a random page read. The query that ran in **200ms** now takes **45 seconds**.

### 5.4 The Fix and Prevention

**Immediate fix:**

```sql
ANALYZE users;
-- This command collects fresh statistics from the table (takes a few minutes for
-- a 100M row table but dramatically speeds up subsequent queries)
```

After ANALYZE, the planner sees:
- `country = 'US'`: 85% of rows = 85M rows
- Combined: 4.25M rows
- Nested loop with an index is terrible for 4.25M rows

Planner re-evaluates: **Hash Join** or **Seq Scan** with filter is now chosen.
Query time returns to **200ms**.

**Longer-term fix: Tune autovacuum thresholds for high-churn tables:**

```sql
ALTER TABLE users SET (
  autovacuum_analyze_scale_factor = 0.01,  -- Trigger ANALYZE after 1% of rows change
                                            -- (default is 20%, way too high for this table)
  autovacuum_analyze_threshold = 1000      -- Plus at least 1000 rows must change
);
```

Default autovacuum triggers ANALYZE after 20% of the table's rows are modified.
For a 100M-row table, that means 20M row changes before statistics refresh — far
too coarse for high-growth tables.

**Monitoring to catch this before it hurts:**

```sql
-- Check when each table was last analyzed:
SELECT
  schemaname,
  tablename,
  last_analyze,
  last_autoanalyze,
  n_live_tup,
  n_dead_tup,
  (n_dead_tup::float / NULLIF(n_live_tup + n_dead_tup, 0) * 100)::int AS dead_pct
FROM pg_stat_user_tables
WHERE last_autoanalyze < NOW() - INTERVAL '24 hours'
   OR last_autoanalyze IS NULL
ORDER BY n_live_tup DESC;
```

Add this to your monitoring dashboards. A table with millions of rows and
`last_autoanalyze` from three days ago after a large data load is a ticking
time bomb for plan regressions.

**Schema of the full incident lifecycle:**

```
Day 0: Table has 30M rows. Statistics collected. Plans are good.
       Query time: 200ms.

Day 1: 70M rows inserted (data migration). No ANALYZE run.
       Statistics still reflect 30M row world.
       
       [Danger Zone: stale statistics in effect]

Day 2: High traffic. Planner uses stale estimates.
       Planner chooses wrong plan (optimized for 30M rows, not 100M).
       Query time: 45 seconds. Alerts fire. Engineers paged at 3am.
       
       Engineer runs: ANALYZE users;
       Query time returns to 200ms. Incident resolved.

Prevention:
  - Run ANALYZE after all bulk data loads
  - Set autovacuum_analyze_scale_factor = 0.01 for large tables
  - Monitor pg_stat_user_tables.last_autoanalyze
  - Use pg_stat_statements to track query performance over time
    (sudden increase in mean_exec_time is a signal of plan regression)
```

---

## 6. Summary and Connections

This section covered two sides of the database systems coin: how connections get
managed at scale, and what happens inside the database when a query runs.

**Connection pooling** is necessary because PostgreSQL's process-per-connection
model doesn't scale to thousands of concurrent clients. PgBouncer solves this by
multiplexing many client connections over a small pool of real PostgreSQL connections.
Transaction pooling mode is the most efficient but requires giving up session-level
features. Pool size should be set based on the database server's CPU core count,
not the application's concurrency.

**Query execution** is a pipeline: SQL text becomes an AST, which becomes a query
plan (via statistics-driven cost estimation), which is then executed by reading
data using the cheapest combination of scan types (sequential, index, bitmap,
index-only) and join algorithms (nested loop, hash join, merge join).

The planner's quality depends entirely on the freshness and accuracy of its
statistics. Stale statistics — especially after bulk data loads — cause the planner
to make wrong choices, which can turn a 200ms query into a 45-second query. The fix
is simple (ANALYZE), but the prevention requires tuning autovacuum and monitoring.

These two topics connect to each other: a connection pool doesn't help if the
queries themselves are slow. And fast queries don't help if you can't connect to the
database. In a real production system, you need both: a well-sized connection pool
(usually PgBouncer in transaction mode with 20-50 connections to PostgreSQL) and
a query layer where statistics are fresh, indexes are chosen correctly, and plans
are verified with EXPLAIN ANALYZE before going to production.
# Chapter 29: Database Internals Deep Dive — Part E
## Storage Engines, Capacity, Troubleshooting, Calibration, and Quick Reference

> This is the final section of Chapter 29. It covers storage engine trade-offs, capacity math,
> operational troubleshooting, L5 vs L6 interview calibration, 20 meaty brainstorming questions,
> 5 homework exercises, and a quick reference card. Read it, then practice out loud.

---

## 1. Storage Engine Comparison: InnoDB vs RocksDB vs MyRocks

Most engineers treat the storage engine as a black box. Staff engineers know what is actually
happening inside it, because that knowledge directly drives schema decisions, tuning choices,
and system design.

### InnoDB (MySQL's Default Engine)

InnoDB is a B-Tree-based storage engine. It is the right choice for most OLTP workloads: banking,
e-commerce, user accounts, order tracking. It supports full ACID transactions.

**How writes work in InnoDB:**

1. The write hits the buffer pool (in memory).
2. The redo log (a WAL) records the change immediately and durably.
3. The buffer pool page is marked dirty.
4. The background checkpointer eventually flushes dirty pages to the data file.

There are two logs that matter:

- **Redo log** — records what changed. Used for crash recovery (replay forward after crash).
- **Undo log** — records what the old value was. Used for rollback and for MVCC (so other
  transactions can read the old version while a write is in progress).

**The clustered index — InnoDB's most important structural decision:**

In InnoDB, the primary key IS the B-Tree. The actual row data is stored at the leaf nodes of the
primary key index. This is called a clustered index.

```
Primary Key B-Tree (clustered)
        [root node]
       /     |      \
  [pk=1..100] [pk=101..200] [pk=201..300]
       |
  [leaf: pk=1, name="Alice", age=30]   <-- actual row data here
  [leaf: pk=2, name="Bob",   age=25]
  [leaf: pk=3, name="Carol", age=28]
```

Consequence for secondary indexes:

```
Secondary Index on (age)
  [age=25] --> stores pk=2   (NOT a heap pointer)
  [age=28] --> stores pk=3
  [age=30] --> stores pk=1

To fetch the full row: look up age index → get pk → look up clustered index again.
This is called a "double read" or "index merge back."
```

For a range scan on the primary key, all data is already in order in the leaf nodes — sequential
I/O, very fast. For a range scan on a secondary index, each row requires a second lookup into
the clustered index — random I/O, potentially expensive at scale.

---

### RocksDB (LSM-Tree Engine)

Facebook grew frustrated with InnoDB's write amplification and storage overhead. They built
RocksDB, an LSM-Tree-based engine, and then modified MySQL to use it instead of InnoDB.
That modified version of MySQL is called **MyRocks**.

**Where RocksDB is used at Facebook:**

- UDB (User Database) — stores friendship data, profile data, hundreds of billions of rows
- TiKV (TiDB's underlying key-value store) uses RocksDB
- Cassandra 4.x can use RocksDB as its storage engine

**RocksDB's key advantages vs InnoDB:**

- **2x better write throughput** — because writes are sequential appends to an in-memory
  MemTable, then flushed as SSTables. No random I/O on write.
- **2x better storage compression** — SSTables are sorted and compressed block-by-block.
  InnoDB's B-Tree pages are harder to compress (partially full pages, fragmentation).

**RocksDB's trade-off:**

- **Read amplification** — to read a key, you may need to check the MemTable, then multiple
  levels of SSTables (L0, L1, L2, ...). Bloom filters help, but they are not free.
- **Write amplification from compaction** — data gets rewritten multiple times as it moves
  down levels (typically 10-30x write amplification for the storage medium).

---

### Comparison Table: InnoDB vs RocksDB

| Dimension              | InnoDB (B-Tree)            | RocksDB (LSM-Tree)              |
|------------------------|----------------------------|---------------------------------|
| Data structure         | B-Tree                     | LSM-Tree (MemTable + SSTables)  |
| Write pattern          | Random writes to pages     | Sequential writes to log        |
| Read amplification     | Low (index directly)       | Higher (check multiple levels)  |
| Write amplification    | Moderate (page splits)     | High (compaction rewrites data) |
| Storage efficiency     | ~50-60% page utilization   | ~2x better compression          |
| MVCC implementation    | Undo log in tablespace     | Sequence numbers per key        |
| Best for               | Mixed OLTP, read-heavy     | Write-heavy, large datasets     |
| Worst for              | Extreme random write load  | Read-heavy, latency-sensitive   |
| Example deployments    | MySQL everywhere           | Facebook UDB, TiKV, MyRocks     |
| Transaction support    | Full ACID                  | Full ACID (RocksDB Transactions)|
| Space reclamation      | VACUUM-equivalent in InnoDB| Compaction                      |
| Range scans on PK      | Excellent (clustered)      | Good (sorted SSTables)          |

---

## 2. Clustered vs Heap Tables

The question "where are the actual rows stored?" has a bigger performance impact than most
engineers realize.

### Heap Table (PostgreSQL Default)

In PostgreSQL, rows are stored in an unordered heap — basically, pages on disk, filled in
whatever order rows were inserted. Indexes are separate structures that point to heap locations
using a tuple ID (ctid = page number + row offset).

```
Heap (rows in arrival order)
Page 0: [row: id=7, name="Dave"] [row: id=2, name="Bob"] [row: id=99, name="Zara"]
Page 1: [row: id=1, name="Alice"] [row: id=45, name="Mike"] ...

Primary Key Index (B-Tree, separate)
  id=1  --> (page=1, offset=0)   -- random heap read
  id=2  --> (page=0, offset=1)   -- random heap read
  id=7  --> (page=0, offset=0)   -- random heap read
  id=45 --> (page=1, offset=1)   -- random heap read
```

A range scan on the primary key in PostgreSQL:
1. Walk the B-Tree index to find relevant ctids (sorted by id).
2. For each ctid, fetch the heap page — pages may be all over the disk.
3. If the range returns many rows, this becomes many random I/Os.

PostgreSQL partially mitigates this with the "Bitmap Heap Scan" — it collects all ctids first,
sorts them by physical page location, then fetches pages in order. But it is still not as
efficient as a clustered table for large range scans.

---

### Clustered Table (InnoDB, SQL Server)

In a clustered table, the row data lives at the leaf nodes of the primary key index. There is
no separate heap — the index IS the table.

```
Clustered Primary Key B-Tree
Leaf nodes (rows stored in PK order):
  [id=1, name="Alice"] --> [id=2, name="Bob"] --> [id=7, name="Dave"] --> [id=45, name="Mike"]
                                           sequential on disk
```

A range scan on the primary key in InnoDB:
1. Walk the B-Tree to find the starting leaf node.
2. Scan leaf nodes sequentially — rows are in order, sequential I/O.
3. No extra heap lookup needed.

**The UUID problem with clustered indexes:**

If you use random UUIDs as primary keys in InnoDB, every insert lands at a random position
in the B-Tree. This causes:

1. The target page must be loaded into the buffer pool.
2. If the page is full, it must be split — half the rows move to a new page.
3. Both pages are written back to disk.
4. Every insert triggers this: buffer pool churn + random I/O + page splits.

At scale (thousands of inserts/second), this destroys write performance. The buffer pool
fills with random pages, cache hit rate drops, and page split I/O saturates the disk.

**The fix:** Use sequential primary keys (AUTO_INCREMENT) or time-ordered UUIDs (UUIDv7,
which has a timestamp prefix making them monotonically increasing). UUIDv7 inserts always
append to the rightmost leaf node — no random position, no page splits except at the very
end of the tree.

```
UUID v4 inserts (random):           UUIDv7 inserts (time-ordered):
  Insert --> random page lookup       Insert --> append to rightmost leaf
  --> page split 30% of the time      --> no splits (usually)
  --> random I/O everywhere           --> sequential I/O
  --> buffer pool thrash              --> efficient
```

---

## 3. Buffer Pool / Shared Buffers: The Database's Memory Manager

Both PostgreSQL and MySQL maintain an in-memory cache of disk pages. This cache is the most
important performance lever in the database. If your working set fits in the buffer pool,
queries run fast. If it does not, every query is a disk read.

### What the buffer pool does

1. **Reads:** When the database needs a page, it checks the buffer pool first. Cache hit = fast.
   Cache miss = read from disk, load page into pool.
2. **Writes:** The database writes to the buffer pool page (dirty page). The change is also
   written to WAL for durability. The dirty page sits in memory and is flushed to disk later
   by the checkpointer/bgwriter.
3. **Eviction:** When the pool is full and a new page is needed, the pool evicts the least
   recently used page. If it is dirty, it must be flushed to disk first.

### Eviction algorithms

- **InnoDB:** Uses a modified LRU with a "midpoint insertion" strategy. New pages enter at
  the midpoint of the LRU list, not the head. This prevents a full table scan from evicting
  all hot pages (the scan pages are young, they age out quickly).
- **PostgreSQL:** Uses "Clock Sweep" — a cheap approximation of LRU. Each page has a usage
  count. The clock hand sweeps through pages; if usage > 0, decrement and skip; if usage = 0,
  evict. Cheaper than a full LRU list but slightly less precise.

### Sizing the buffer pool

```
PostgreSQL:
  shared_buffers = 25% of total RAM
  (OS page cache handles the remaining working set as a second-level cache)

InnoDB:
  innodb_buffer_pool_size = 70-80% of total RAM
  (InnoDB bypasses OS page cache for data files, so it needs a bigger pool)

Example: 64GB RAM server
  PostgreSQL: shared_buffers = 16GB
  InnoDB:     innodb_buffer_pool_size = 48GB
```

### Measuring buffer pool effectiveness

In PostgreSQL, query `pg_statio_user_tables`:

```sql
SELECT
  relname,
  heap_blks_hit,
  heap_blks_read,
  round(heap_blks_hit::numeric /
    nullif(heap_blks_hit + heap_blks_read, 0) * 100, 2) AS hit_rate_pct
FROM pg_statio_user_tables
ORDER BY heap_blks_read DESC;
```

Target: hit rate > 99% for OLTP. If hit rate is 90%, that means 1 in 10 page reads goes to
disk — on a busy system, that is thousands of disk reads per second.

In InnoDB:

```sql
SHOW STATUS LIKE 'Innodb_buffer_pool_read%';
-- Innodb_buffer_pool_reads      = pages read from disk (misses)
-- Innodb_buffer_pool_read_requests = total page requests
-- Hit rate = 1 - (reads / read_requests)
```

---

## 4. Capacity Estimation: Back-of-Envelope Numbers Every Staff Engineer Knows

When the interviewer asks "how do you scale this?" you need numbers in your head, not
approximations. These are the numbers that matter.

### Single PostgreSQL Node Practical Limits

| Resource          | Comfortable range        | Hard ceiling (pain starts) |
|-------------------|--------------------------|----------------------------|
| Storage           | 1-4 TB                   | 10 TB+ (backups take days) |
| Connections       | 100-300                  | 500+ (use pool)            |
| Read QPS          | 10,000-50,000 (simple)   | 100,000+ (need replicas)   |
| Write QPS         | 1,000-10,000             | 20,000+ (need sharding)    |
| Table rows        | Up to ~500M              | 1B+ (VACUUM becomes painful)|
| Table size        | Up to ~500 GB            | 1 TB+ (index rebuild slow) |

### Storage Sizing Formula

```
Given:
  R = number of rows
  S = average row size in bytes
  I = number of secondary indexes

Table data size = R x S x 1.2          (20% overhead for page headers, fill factor)
Each index size = 0.3 x table_size     (B-Tree indexes are ~30% of table data)
WAL per day     = 0.1 to 0.5 x daily_write_volume

Total footprint = table_size x (1 + 0.3 x I) x 2 (replica) x 1.5 (WAL + temp + backups)

Example:
  R = 500M rows, S = 200 bytes, I = 3 indexes
  Table = 500M x 200 x 1.2 = 120 GB
  Indexes = 3 x 0.3 x 120 GB = 108 GB
  Subtotal = 228 GB
  With replica and WAL overhead = 228 x 2 x 1.5 = 684 GB
  --> plan for ~700 GB total disk
```

### Connection Pool Sizing

```
Rule of thumb: num_db_connections = num_cpu_cores x 2

  8-core PostgreSQL server --> 16 database connections handle most OLTP load
  PgBouncer can multiplex 5,000 app connections over those 16 db connections

Why so few connections?
  Each PostgreSQL connection is a separate process (~10 MB memory).
  At 300 connections = 3 GB just for connection overhead.
  Beyond ~4x num_cores, connections queue behind each other and performance drops.
```

### Scaling Decision Table

| Write QPS | Read QPS | Data Size | Strategy                                    |
|-----------|----------|-----------|---------------------------------------------|
| < 1K      | < 10K    | < 100 GB  | Single node, primary only                   |
| < 5K      | < 50K    | < 500 GB  | Primary + 1-2 read replicas                 |
| < 10K     | < 100K   | < 2 TB    | Primary + multiple replicas + PgBouncer     |
| < 20K     | < 500K   | < 4 TB    | Vertical scale + replicas + caching layer   |
| > 20K     | any      | > 4 TB    | Horizontal sharding required                |

### When to pull each lever

```
Read replicas: when read QPS > 80% of single-node read capacity
Caching (Redis): when same data is read >10x/sec and changes infrequently
Vertical scaling: when CPU or RAM is the bottleneck (not locks, not I/O pattern)
Sharding: when write QPS > 10K sustained OR data > 4 TB OR VACUUM can't keep up
```

---

## 5. Operational Troubleshooting Decision Tree

Real on-call scenarios. For each symptom, know the investigation order.

### Symptom A: High Query Latency (p99 suddenly 10x worse)

```
p99 latency suddenly 10x worse
          |
          v
    EXPLAIN ANALYZE the slow query
          |
    +-----+------+
    |            |
  Plan OK    Plan changed
    |            |
    |        Bad statistics?
    |        --> ANALYZE tablename
    |        --> check pg_stat_user_tables.last_analyze
    |
    v
  pg_stat_activity
  --> any blocking queries?
  --> look for lock_type='relation' or 'tuple'
          |
    +-----+------+
    |            |
  No blocks   Blocking txn found
    |            |
    |        Kill blocking transaction:
    |        SELECT pg_terminate_backend(pid)
    |        WHERE state='idle in transaction'
    |        AND query_start < NOW() - interval '5 min'
    |
    v
  pg_stat_bgwriter
  --> checkpoint_write_time very high?
  --> checkpoint I/O spike (lots of dirty pages flushed at once)
  --> reduce checkpoint_completion_target
  --> increase shared_buffers / max_wal_size
          |
    +-----+------+
    |            |
  Normal      I/O spike
  bgwriter        |
    |        Schedule checkpoints more spread out
    |
    v
  Check replication lag
  --> is this a replica? Is primary overloaded?
  --> pg_stat_replication on primary
          |
    v
  pg_stat_user_tables.n_dead_tup
  --> high dead tuples? Table bloat causing longer scans
  --> run VACUUM ANALYZE tablename
```

### Symptom B: Connection Exhaustion ("sorry, too many clients")

```
"FATAL: sorry, too many clients already"
          |
          v
  SELECT count(*), state FROM pg_stat_activity GROUP BY state;
          |
    +-----+-------+----------+
    |             |          |
  Many idle   Many active   Many idle
  connections  connections  in transaction
    |             |          |
  App not     Real load:   Long-running txns
  returning   scale up     holding connections
  connections pool         --> kill them
    |
  Check application:
  - connection not closed in finally block
  - connection leak in error path
  - ORM not returning to pool
          |
    Fix: add PgBouncer in front,
         set pool_mode=transaction,
         set idle connection timeout
```

### Symptom C: Table Bloat (table far larger than data should require)

```
Table is 400 GB but data should be 100 GB
          |
          v
  SELECT n_live_tup, n_dead_tup, last_autovacuum
  FROM pg_stat_user_tables WHERE relname='orders';
          |
  n_dead_tup very high (tens of millions)?
          |
          v
  Check if autovacuum is running:
  SELECT pid, query FROM pg_stat_activity WHERE query LIKE '%autovacuum%';
          |
    +-----+------+
    |            |
  Running     Not running
    |            |
  Can't keep  Check autovacuum settings:
  up with     autovacuum_vacuum_cost_delay
  write load  autovacuum_vacuum_scale_factor
    |            |
    v            v
  Is a long txn blocking autovacuum?
  SELECT * FROM pg_stat_activity
  WHERE state != 'idle'
  ORDER BY xact_start;
          |
  Kill the old transaction, then:
  VACUUM ANALYZE orders;  -- manual trigger
```

### Symptom D: Replication Lag Growing

```
Replica falling behind primary
          |
          v
  On primary:
  SELECT client_addr, replay_lag, write_lag
  FROM pg_stat_replication;
          |
    +-----+---------+----------+
    |               |          |
  replay_lag     write_lag   Both high
  high only      high only
    |               |          |
  Replica slow   Network     Primary
  applying WAL   issue       write rate
    |                        too high
    v
  Check replica CPU/I/O:
  --> Is replica saturated?
  --> Are analytics queries running on replica?
  --> Are there long-running queries on replica blocking WAL apply?
          |
    +-----+------+
    |            |
  Saturated   Blocking txn
    |            |
  Move        Kill it:
  analytics   SELECT pg_terminate_backend(pid)
  off replica WHERE state != 'idle'
              AND query_start < NOW() - '30min'
          |
    v
  If lag keeps growing despite fixes:
  --> Check max_standby_streaming_delay
  --> Consider adding another replica (distribute read load)
  --> Check if wal_level and wal_compression are tuned
```

### Master Decision Tree (All Symptoms)

```
                    DB Problem Reported
                           |
            +--------------+--------------+
            |                             |
     Latency spike                  Connection error
            |                             |
     EXPLAIN ANALYZE              Count pg_stat_activity
            |                             |
     +------+------+            +---------+---------+
     |             |            |                   |
  Plan OK    Plan changed    Too many idle    Long txns
     |             |            |                   |
  Check locks  ANALYZE     PgBouncer         Kill them
     |
  Check bgwriter/I/O
     |
  Check replication lag
     |
  Check VACUUM / bloat

            Table bloat                Replication lag
                 |                           |
          n_dead_tup high              replay_lag high
                 |                           |
          Long txn blocking?         Replica saturated?
                 |                           |
          Kill it + VACUUM          Move load off replica
```

---

## 6. L5 vs L6 Calibration Table

The difference between L5 and L6 is not knowing more facts — it is reasoning about root causes
instead of jumping to surface fixes.

| # | Scenario               | L5 Response (surface fix)                   | L6 Response (root cause)                                                              |
|---|------------------------|---------------------------------------------|---------------------------------------------------------------------------------------|
| 1 | Slow writes            | "Add an index to help the write"            | Check write amplification; count existing indexes; profile which indexes are actually used |
| 2 | High latency           | "The database is slow, scale it up"         | Check each layer: connections queuing? Lock waits? Stale stats? Checkpoint I/O spike? |
| 3 | Table bloat            | "Run VACUUM to clean it up"                 | Find what is blocking VACUUM (long-running transaction); kill it first, then VACUUM    |
| 4 | Connection exhaustion  | "Increase max_connections to 1000"          | Add PgBouncer; more connections hurt performance beyond 4x core count                 |
| 5 | Index selection        | "Add an index to the slow column"           | Measure cardinality; check pg_stat_user_indexes for unused indexes first              |
| 6 | WAL directory growing  | "Delete the old WAL files to free space"    | Find what is holding WAL: stale replication slot? Long transaction? Then fix the cause|
| 7 | Bad query plan         | "Trust the planner, it will fix itself"     | Check statistics freshness; manually ANALYZE; consider pg_hint_plan if stats are fine |
| 8 | Replication lag        | "Add another replica"                       | Identify root cause: write volume, replica bottleneck, analytics queries on replica   |
| 9 | LSM vs B-Tree choice   | "Cassandra is write-optimized, use it"      | Analyze read:write ratio; check compaction overhead; measure actual write amplification|
|10 | MVCC overhead          | "PostgreSQL wastes storage on old versions" | Tune autovacuum aggressiveness; avoid long transactions; set statement_timeout         |
|11 | Transaction isolation  | "Use SERIALIZABLE everywhere for safety"    | Understand SSI retry cost; use READ COMMITTED for most OLTP, REPEATABLE READ for reports|
|12 | PgBouncer pool mode    | "Transaction pooling is always better"      | Check for prepared statements, advisory locks, session state — these break in transaction mode |

---

## 7. Brainstorming Questions

Practice these out loud. Time yourself. A good answer is 5-7 minutes.

---

### Theme A: B-Tree and Storage

**Question 1:**
You have a table with 15 secondary indexes and writes are 8x slower than expected.
Walk me through your diagnosis.

> Hint: Each index is a separate B-Tree write. 15 indexes means a single row insert writes to
> 15 separate B-Tree locations. Check pg_stat_user_indexes — how many are actually being used?
> Drop the unused ones. Measure write amplification before and after.

---

**Question 2:**
A range query on a non-indexed timestamp column takes 30 seconds on 500 million rows.
What are your options?

> Hint: Sequential scan of 500M rows will always be slow. Options in rough order of cost:
> (1) Add a B-Tree index on timestamp — fast reads, extra write cost.
> (2) Partition the table by time range — prune irrelevant partitions entirely.
> (3) Move to a columnar store (e.g., Parquet on S3 + Athena) for purely analytical queries.
> Discuss the trade-offs of each.

---

**Question 3:**
Your UUID primary key table in InnoDB has terrible insert performance. The team says
"we need UUIDs for security." What's happening internally and how do you fix it?

> Hint: Random UUIDs cause random insertions into the clustered B-Tree. Each insert must find
> the right leaf page (random I/O), which is likely not in buffer pool, then may cause a page
> split. Fix: switch to UUIDv7 (timestamp prefix = monotonically increasing = append-only
> insertions). Alternatively, use AUTO_INCREMENT as primary key and store the UUID in a
> separate unique column (non-clustered, so splits don't hurt as much).

---

**Question 4:**
You need to add full-text search to a product catalog with 50 million rows. Walk me through
when you would use a PostgreSQL GIN index versus Elasticsearch.

> Hint: GIN index in PostgreSQL handles full-text search for moderate workloads. It is simpler
> operationally (no extra system to maintain). Elasticsearch is justified when: (1) search is
> the primary feature, not an add-on; (2) you need relevance ranking beyond tsvector/tsrank;
> (3) faceted search / aggregations are complex; (4) the search index needs to be updated in
> near-real-time from multiple sources. Discuss operational cost of Elasticsearch (cluster
> management, shard sizing, replication).

---

**Question 5:**
A B-Tree index has 5 levels. Approximately how many rows does the table have? Show your reasoning.

> Answer:
> Each internal node in a B-Tree can hold roughly 400 pointers (8-byte keys + 8-byte child
> pointers in a 4 KB page, accounting for headers).
>
> Level 0 (root):     1 node    x 400 = 400 children
> Level 1:          400 nodes   x 400 = 160,000 children
> Level 2:       160,000 nodes  x 400 = 64,000,000 children
> Level 3:    64,000,000 nodes  x 400 = 25,600,000,000 leaf pointers
>
> A 5-level B-Tree can address roughly 25 billion rows.
> So the table likely has tens of billions of rows if the index is 5 levels deep.
> A 4-level index covers ~64 million rows. If the interviewer says 500M rows, the answer
> is 4-5 levels depending on key size and fill factor.

---

### Theme B: WAL and Durability

**Question 6:**
The pg_wal directory is consuming 500 GB and growing. Walk me through your investigation.

> Check in order:
> (1) pg_replication_slots: is there a stale slot no consumer is reading?
>     A slot holds WAL until the consumer acknowledges it. Dead slot = WAL accumulates forever.
>     Fix: DROP REPLICATION SLOT 'slot_name' or set max_slot_wal_keep_size.
> (2) pg_stat_activity: is there a very long-running transaction?
>     WAL cannot be recycled past the oldest active transaction's start point.
>     Fix: kill the long transaction.
> (3) wal_keep_size / wal_keep_segments set too high: reduce to 1-2 GB unless you need more.
> (4) Logical replication slot lagging: consumer (e.g., Debezium) not keeping up.
>     Fix: tune consumer throughput or increase replication slot's max_replication_slots.

---

**Question 7:**
You need to recover data accidentally deleted at 14:37 today. How does point-in-time recovery
work in PostgreSQL and what do you need?

> PITR works by:
> (1) Start from a base backup (a full snapshot of the data directory).
> (2) Replay WAL files from the backup point up to the target time (14:36 in this case).
> (3) Because WAL contains every change, replaying it brings the database to any past state.
>
> What you need:
> - A base backup taken before the deletion (e.g., last night's backup).
> - All WAL segments from that backup to 14:36 today (usually stored in S3 via pgBackRest
>   or WAL-G).
> - A restore server to replay into (do not overwrite production).
>
> PostgreSQL recovery.conf (or postgresql.conf in PG12+):
>   recovery_target_time = '2026-06-13 14:36:00'
>   restore_command = 'aws s3 cp s3://wal-archive/%f %p'

---

**Question 8:**
A replica is 5 minutes behind the primary. A user writes data on the primary, then immediately
reads from the replica. What do they see?

> They see stale data — their own write is not visible yet on the replica.
> This is a "read-your-own-writes" consistency problem.
>
> Solutions:
> (1) Route that user's reads to the primary for 5-10 seconds after a write (sticky routing).
> (2) Use a version cookie: write returns a WAL LSN; the read request includes the LSN;
>     the replica checks if it has replayed past that LSN before responding.
> (3) Synchronous replication: primary does not commit until at least one replica confirms.
>     This guarantees the replica is current but adds latency to every write.
> (4) Accept the inconsistency and design around it (eventual consistency is fine for many
>     social features, e.g., "like count" on a post).

---

**Question 9:**
Your team proposes setting synchronous_commit = off to improve write throughput. What are the
exact risks and under what conditions is it acceptable?

> With synchronous_commit = off:
> - PostgreSQL returns "commit successful" to the client BEFORE the WAL record is written to disk.
> - WAL is buffered in memory and flushed within wal_writer_delay (default 200ms).
> - Risk: if the server crashes in that 200ms window, up to 200ms of committed transactions
>   are lost. The database does NOT become corrupt — it just loses those transactions silently.
>
> This is different from a disk failure (which could corrupt data even with synchronous_commit=on
> if you have no RAID or battery-backed write cache).
>
> Acceptable when:
> - The data is ephemeral (session logs, analytics events where small gaps are tolerable).
> - You have application-level replay (the client will retry anyway on connection error).
> - The write performance gain (often 2-5x) outweighs the small data loss window.
>
> NOT acceptable when:
> - Financial transactions, inventory deductions, anything where "committed = guaranteed."

---

**Question 10:**
After a crash, PostgreSQL takes 10 minutes to restart. Why? What could you do to reduce this?

> PostgreSQL restart requires replaying WAL from the last checkpoint to the crash point.
> The more WAL since the last checkpoint, the longer recovery takes.
>
> Why the checkpoint was far away:
> - max_wal_size set very large (e.g., 32 GB) allows many checkpoints to spread out,
>   which means recovery must replay up to 32 GB of WAL.
> - checkpoint_completion_target=0.9 spreads checkpoint I/O over a long period,
>   which is good for performance but means checkpoints happen less frequently.
>
> To reduce recovery time:
> (1) Reduce max_wal_size (trade: more frequent checkpoint I/O during normal operation).
> (2) Reduce checkpoint_timeout from 5 minutes to 2 minutes.
> (3) Accept the trade-off: faster recovery = more checkpoint I/O during normal operation.
>     For most systems, 1-3 minutes of recovery time is acceptable.

---

### Theme C: MVCC and Concurrency

**Question 11:**
Transaction A starts and reads row X (value = 100). Transaction B updates row X to 200 and
commits. Transaction A reads row X again.

What does Transaction A see under READ COMMITTED vs REPEATABLE READ?

> READ COMMITTED:
> - Each statement in Transaction A gets a fresh snapshot.
> - Transaction A's second read sees 200 (the committed value from B).
> - This is correct behavior for READ COMMITTED — non-repeatable reads are allowed.
>
> REPEATABLE READ (PostgreSQL):
> - Transaction A gets a snapshot at the START of the transaction.
> - Transaction A's second read still sees 100 (the old value, from its snapshot).
> - This is correct behavior — the snapshot is consistent for the life of the transaction.
> - PostgreSQL implements this via MVCC: the old row version (100) is still in the heap,
>   visible to A's snapshot. B's new version (200) has a higher xmin than A's snapshot.

---

**Question 12:**
Two transactions both execute "SELECT COUNT(*) FROM doctors WHERE on_call = true"
and both get count = 1. Both then decide to set on_call = false for that doctor.
Both commit. Now no doctor is on call. What anomaly is this? How do you prevent it?

> This is a **write skew** anomaly. Each transaction read a consistent (but stale) view of
> the world, made a decision based on it, and wrote a change that would not have been made
> if they had seen each other's writes.
>
> REPEATABLE READ does NOT prevent write skew (it prevents non-repeatable reads and phantom
> reads, but not write skew where the conflict is between two writes based on reads).
>
> SERIALIZABLE isolation (SSI in PostgreSQL) DOES prevent this — it detects the dependency
> cycle and aborts one of the transactions.
>
> Alternative application-level solutions:
> - SELECT ... FOR UPDATE: lock the row being read so the second transaction waits.
> - Application-level check-and-set with an optimistic lock version column.
> - Use a single transaction that atomically checks and updates:
>   UPDATE doctors SET on_call = false WHERE on_call = true AND id = X
>   and check the row count returned.

---

**Question 13:**
Your autovacuum cannot keep up with dead tuples. What are the three most likely causes
and how do you diagnose each?

> Cause 1: Very high write rate producing more dead tuples than autovacuum can process.
>   Diagnose: pg_stat_user_tables.n_dead_tup growing faster than last_autovacuum timestamp
>   can keep up. Fix: increase autovacuum_vacuum_cost_limit, decrease autovacuum_vacuum_cost_delay,
>   increase autovacuum_max_workers.
>
> Cause 2: Long-running transactions preventing VACUUM from cleaning old versions.
>   Diagnose: pg_stat_activity — look for transactions older than 1 hour.
>   SELECT min(xact_start) FROM pg_stat_activity WHERE state != 'idle';
>   VACUUM cannot remove row versions newer than the oldest active transaction's snapshot.
>   Fix: set idle_in_transaction_session_timeout; kill old transactions.
>
> Cause 3: Replication slot holding back the xmin horizon.
>   Diagnose: SELECT slot_name, xmin, catalog_xmin FROM pg_replication_slots;
>   A lagging slot's xmin prevents VACUUM from removing dead tuples that the slot might need.
>   Fix: drop the stale slot, or tune the consumer to keep up.

---

**Question 14:**
A table with 1 billion rows is 400 GB but you calculated it should be 100 GB based on row size.
What likely happened and how do you recover?

> The table has 300 GB of dead tuple bloat (old row versions not yet vacuumed).
>
> Why it happened:
> - A long-running transaction (analytics query, stuck migration) held a snapshot open for
>   hours or days, preventing autovacuum from removing dead tuples.
> - High UPDATE rate on the table generating many dead versions.
>
> How to diagnose:
>   SELECT n_live_tup, n_dead_tup, last_autovacuum FROM pg_stat_user_tables WHERE relname='...';
>   SELECT * FROM pg_stat_activity ORDER BY xact_start LIMIT 5;
>
> Recovery:
> 1. Kill the long-running transaction that was blocking VACUUM.
> 2. Run VACUUM ANALYZE tablename (reclaims space in the FSM, allows reuse).
> 3. If you need the actual disk space back (VACUUM does not shrink the file):
>    Run VACUUM FULL tablename — this rewrites the entire table. Causes an ACCESS EXCLUSIVE
>    lock (table is unavailable during this). Use pg_repack as a zero-downtime alternative.

---

**Question 15:**
You need a distributed advisory lock so that only one server among a fleet of 50 application
servers runs a cron job at a time. How do you implement this with PostgreSQL?

> PostgreSQL advisory locks are session-level locks stored in shared memory, visible across
> all connections to the same database. They are the right tool for this.
>
> Implementation:
>
> ```sql
> -- Returns true if the lock was acquired, false if another process holds it
> SELECT pg_try_advisory_lock(12345);  -- 12345 is the job's unique integer ID
> ```
>
> Pattern:
> ```python
> with db.transaction():
>     got_lock = db.execute("SELECT pg_try_advisory_lock(12345)").scalar()
>     if not got_lock:
>         return  # another server has the lock
>     run_the_cron_job()
>     # Lock released automatically when session ends or explicitly:
>     # db.execute("SELECT pg_advisory_unlock(12345)")
> ```
>
> Key points:
> - pg_try_advisory_lock is non-blocking (returns false immediately if lock is held).
> - Lock is released when the connection closes — so if the server crashes mid-job, the
>   lock is automatically released (no stuck lock).
> - Use pg_advisory_lock (blocking) only if you want jobs to queue up, not skip.
> - Limitation: requires all app servers to connect to the SAME PostgreSQL instance (or primary).

---

### Theme D: Query Execution and Connections

**Question 16:**
A query was running in 50ms last week and now takes 8 seconds. EXPLAIN ANALYZE shows a
completely different execution plan. What changed and how do you fix it?

> Most likely cause: statistics are stale. The planner uses pg_statistic (histogram data
> collected by ANALYZE) to estimate how many rows each plan node will return. If statistics
> are old, the planner makes wrong estimates and picks a wrong plan.
>
> Investigation:
> (1) EXPLAIN ANALYZE shows estimated rows vs actual rows. If they are wildly different
>     (e.g., planner estimated 100 rows, actual was 1,000,000), statistics are stale.
> (2) SELECT last_analyze, last_autoanalyze FROM pg_stat_user_tables WHERE relname='...';
>     If last_analyze is weeks ago and the table has millions of writes since then, statistics
>     are stale.
>
> Fix:
> - ANALYZE tablename; (runs in seconds to minutes, no lock)
> - Check autovacuum is running and keeping statistics fresh
>
> Other causes: planner cost constants wrong for your hardware (random_page_cost too high
> causing planner to prefer seq scans), or a new data distribution that genuinely makes the
> old index bad (e.g., column that was high-cardinality is now low-cardinality after a bulk
> update — index scan less efficient than seq scan).

---

**Question 17:**
You are debugging a "connection timeout" error. The database has 200 max_connections.
Walk through your complete investigation.

> Step 1: Are connections exhausted?
>   SELECT count(*), state FROM pg_stat_activity GROUP BY state;
>   If total >= max_connections, connections are exhausted. This is "too many clients."
>
> Step 2: What state are they in?
>   - Many "idle in transaction": application is opening transactions and not closing them
>     (exception in code path, forgot to commit/rollback). Fix: idle_in_transaction_session_timeout.
>   - Many "active" with same query: query is slow/blocking; find the bottleneck.
>   - Many "idle": connection pool is too large, releasing unused connections.
>
> Step 3: Is the application or the pool the culprit?
>   - If using PgBouncer: check pgbouncer's SHOW POOLS; what is the queue wait time?
>   - If direct connections: application is opening too many connections.
>
> Step 4: What is the right fix?
>   - Short term: kill idle connections
>     SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state='idle' AND ...;
>   - Medium term: add PgBouncer with transaction pooling
>   - Long term: application connection management audit

---

**Question 18:**
A Hash Join is using disk (batched hash) instead of memory. What is the fix? What are the
trade-offs?

> A Hash Join builds a hash table from the smaller relation in memory (work_mem), then
> probes it with the larger relation. If the hash table is larger than work_mem, PostgreSQL
> spills it to disk in batches (batch hash join), which is significantly slower due to I/O.
>
> EXPLAIN ANALYZE will show: "Batches: 8" (means 8 disk batches, instead of "Batches: 1").
>
> Fix option 1: Increase work_mem for this session:
>   SET work_mem = '256MB';  -- applies only to this session
>   (or increase globally if this query is common)
>
> Trade-offs of increasing work_mem:
> - work_mem is per sort/hash operation per query, and a query can have many.
> - 100 concurrent queries x 4 operations each x 256MB = 100GB RAM needed.
> - Increase too much and you cause OOM kills.
>
> Fix option 2: Reduce the join input size earlier in the plan:
> - Push down filters so the hash table is built on fewer rows.
> - Ensure the smaller side of the join is actually smaller (swap sides with hints if needed).
>
> Fix option 3: Accept the batched join — for large batch analytics, disk-based hash join
> is expected and acceptable.

---

**Question 19:**
An application uses prepared statements extensively. After switching to PgBouncer in transaction
pooling mode, the application breaks with "prepared statement does not exist" errors. Why?
How do you fix it?

> Root cause: PgBouncer in transaction pooling mode does not guarantee that the same backend
> PostgreSQL connection is reused across transactions from the same client. Prepared statements
> are stored per backend connection. If a client prepares a statement on connection A, but
> their next query is routed to connection B, the prepared statement does not exist on B.
>
> In session pooling mode, each client maps 1:1 to a backend, so prepared statements work.
> But session pooling defeats most of the benefit of PgBouncer (you can only pool idle sessions).
>
> Solutions:
> (1) Switch PgBouncer to session pooling for this application (accept lower multiplexing).
> (2) Disable prepared statements in the application (use simple protocol).
>     In Python psycopg2: use `prepared=False` or disable server-side prepared statements.
>     In Java JDBC: `prepareThreshold=0`
> (3) Use pgBouncer's prepared statement tracking feature (PgBouncer 1.21+) which rewrites
>     prepared statements per connection transparently (experimental as of 2024).
> (4) Use PgPool-II which has proper prepared statement handling but is more complex.

---

**Question 20:**
Parallel query is enabled but a large analytical query runs single-threaded. What conditions
prevent parallelism in PostgreSQL?

> PostgreSQL parallelism requires all of the following to be true:
>
> (1) max_parallel_workers_per_gather > 0 (default 2). If 0, no parallel.
>
> (2) The table must be large enough. If the planner estimates fewer than
>     min_parallel_table_scan_size pages, it does not parallelize.
>
> (3) The query cannot have functions marked NOT PARALLEL SAFE.
>     Check: \df+ function_name and look at "Parallel" column. Custom PL/pgSQL functions
>     default to PARALLEL UNSAFE.
>
> (4) The session is not in a transaction that started with ISOLATION LEVEL SERIALIZABLE
>     (serializable transactions cannot use parallel workers).
>
> (5) The query is not inside a function (function context prevents parallel plans).
>
> (6) max_parallel_workers (global) is not already fully consumed by other queries.
>
> Diagnosis:
>   EXPLAIN (ANALYZE, VERBOSE) query; -- look for "Workers Planned" vs "Workers Launched"
>   If Workers Planned > 0 but Workers Launched = 0: ran out of worker slots.
>   If Workers Planned = 0: planner decided not to parallelize (check conditions above).

---

## 8. Homework Exercises

Do these in writing, as if you are presenting to a senior engineer on your team.

---

### Exercise 1: Design a High-Write Audit Log System

**Requirements:**
- 100,000 writes per second
- Records are immutable (append-only)
- Queryable by user_id and time range
- 90-day retention, then delete

**Design the storage engine, schema, indexing, and retention strategy.**

**Starting points to consider:**

Storage engine choice:
- PostgreSQL: can handle this with partitioning, but at 100K writes/sec you are pushing
  the limit. Use time-range partitioning (one partition per day). Each partition can be
  dropped (not deleted row by row) when it expires — very fast.
- Cassandra / ScyllaDB: native time-series with LSM-tree, designed for this write rate.
  Partition key = (user_id, day), clustering key = timestamp. Range queries are efficient.
  Compaction handles TTL naturally.
- ClickHouse: columnar store, can handle 100K writes/sec with async inserts, excellent for
  analytical queries over time ranges.

Schema (PostgreSQL partitioned):
```sql
CREATE TABLE audit_log (
  id          BIGSERIAL,
  user_id     BIGINT NOT NULL,
  action      TEXT NOT NULL,
  metadata    JSONB,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (created_at);

CREATE INDEX ON audit_log (user_id, created_at);

-- Create partitions for each day:
CREATE TABLE audit_log_2026_06_13
  PARTITION OF audit_log
  FOR VALUES FROM ('2026-06-13') TO ('2026-06-14');
```

Retention: DROP TABLE audit_log_2026_03_15; -- for a 90-day-old partition.
Dropping a partition takes milliseconds vs. DELETE which takes hours on billions of rows.

L6 consideration: At 100K/sec, PostgreSQL write path must not be a bottleneck.
Use UNLOGGED tables or batched inserts. Consider Kafka as a buffer in front, with a consumer
batch-writing to PostgreSQL. This decouples write spike from the database.

---

### Exercise 2: Diagnose and Fix PostgreSQL Performance

**Given:**
- pg_stat_user_tables shows n_dead_tup = 50,000,000 on the orders table
- pg_stat_activity shows a transaction that started 6 hours ago (state: idle in transaction)

**Task:** Explain exactly what is happening, what the risk is, and how to fix it safely.

**Answer:**

What is happening:
The 6-hour-old transaction holds a transaction snapshot from 6 hours ago. PostgreSQL's MVCC
requires that row versions visible to any active transaction must not be cleaned up. Autovacuum
cannot remove the 50M dead tuples on the orders table because those dead tuples might be needed
by the 6-hour-old snapshot.

Risk:
- Table bloat: orders table is wasting disk space and causing slower sequential scans.
- Transaction ID wraparound: if this continues for weeks and autovacuum falls further behind,
  the database approaches the XID wraparound danger zone (autovacuum freeze is also blocked).
- Replica lag: dead tuples slow down writes, which slow down WAL generation patterns.

Fix:
1. Identify the old transaction:
   SELECT pid, usename, xact_start, query, state FROM pg_stat_activity
   ORDER BY xact_start LIMIT 5;

2. Kill it:
   SELECT pg_terminate_backend(pid) WHERE pid = <pid>;
   -- pg_cancel_backend sends SIGINT (graceful), pg_terminate_backend sends SIGTERM (immediate)

3. After killing it, autovacuum will detect the freed xmin horizon and begin cleaning.
   You can also trigger manually for speed:
   VACUUM ANALYZE orders;

4. Verify:
   SELECT n_dead_tup, last_autovacuum FROM pg_stat_user_tables WHERE relname='orders';
   (n_dead_tup should drop over the next few minutes)

5. Prevent recurrence:
   SET idle_in_transaction_session_timeout = '10min';
   -- Kills any session that has been idle in a transaction for more than 10 minutes.

---

### Exercise 3: Connection Pool Architecture for 50K RPS

**Application:** 50,000 requests per second, each needs exactly one database query,
average query time is 5ms.

**Design: how many app servers, how many PgBouncer instances, how many PostgreSQL connections?**

**Using Little's Law:**

```
Little's Law: N = λ × W
  N = average number of requests in the system (concurrency)
  λ = arrival rate (requests/second)
  W = average time in system (seconds)

N = 50,000 req/sec × 0.005 sec = 250 concurrent database connections needed at any moment
```

PostgreSQL connections:
- A 32-core PostgreSQL server handles ~64 connections efficiently (2x cores).
- But we need 250 concurrent → need at least 4 PostgreSQL primaries, OR
- Use PgBouncer to multiplex: 250 concurrent app requests → 64 actual DB connections.
  PgBouncer in transaction mode: connection is held only during the 5ms query.
  Idle time between requests: connection returned to pool.
  PgBouncer multiplexing ratio: (time between requests) / (query time).
  If average think time is 200ms: 200/5 = 40x multiplexing → 250 app connections → 6 DB connections.

Reality check: add overhead for slow queries (p99 might be 50ms), connection overhead, etc.

Architecture:
```
50,000 RPS
    |
[App servers: ~50 servers x 1000 RPS each]
    |
[PgBouncer: 2-3 instances for HA, each handling 25K connections]
    |
[PostgreSQL primary: 32 cores, innodb_buffer_pool 48GB, 100-200 actual connections]
    |
[2 Read replicas for read-heavy queries]
```

PgBouncer sizing: one PgBouncer process handles ~10K client connections on modern hardware.
For 50K RPS, use 3 PgBouncer instances behind a load balancer (HAProxy or similar).

---

### Exercise 4: Explain a Query Plan

**Given EXPLAIN ANALYZE output:**

```
Nested Loop  (cost=0.00..982000.00 rows=10000 width=50)
             (actual time=0.05..48200.00 rows=10000 loops=1)
  ->  Seq Scan on orders  (cost=0.00..18000.00 rows=500 width=20)
                          (actual rows=500 loops=1)
  ->  Seq Scan on order_items  (cost=0.00..200.00 rows=20 width=30)
      Filter: (order_id = orders.id)
      actual rows=20 loops=500
      Rows Removed by Filter: 9980
```

**Task: identify what is wrong and what to fix.**

**Analysis:**

Problem 1: The inner Seq Scan on order_items runs 500 times (once per row from orders).
Each time, it scans the entire order_items table and filters. This is 500 full scans.

Rows Removed by Filter: 9980 means each inner scan reads ~10,000 rows but keeps only 20.
Total inner table reads: 500 × 10,000 = 5,000,000 row reads. This is the performance killer.

Root cause: Missing index on order_items.order_id.

Fix:
```sql
CREATE INDEX ON order_items (order_id);
```

After adding the index, the inner side becomes an Index Scan instead of a Seq Scan.
Each inner lookup reads ~20 rows directly instead of scanning 10,000.
Total reads drop from 5,000,000 to ~10,000.

Problem 2: The Seq Scan on orders returns 500 rows. If orders is a large table (millions of rows)
and only 500 match, there may also be a missing index on the orders filter column. Check the full
query for WHERE conditions on orders.

L6 follow-up: after adding the index, run EXPLAIN ANALYZE again to verify the plan changed.
If the planner still does a Seq Scan after adding the index, the statistics may be stale:
run ANALYZE order_items; to refresh.

---

### Exercise 5: Design WAL-Based Replication for Zero Data Loss

**Requirements:** Zero data loss on primary failure; RTO (recovery time objective) < 30 seconds.

**Design: synchronous vs asynchronous, quorum commit, automated failover.**

**Design:**

Replication topology:
```
Primary (us-east-1a)
    |  synchronous WAL streaming
    +---> Standby 1 (us-east-1b)
    |
    +---> Standby 2 (us-east-1c)  (quorum: any 1 of 2)

Patroni (cluster manager) on all 3 nodes
Etcd (distributed consensus) for leader election
HAProxy in front for client routing
```

PostgreSQL configuration on primary:
```
synchronous_standby_names = 'ANY 1 (standby1, standby2)'
synchronous_commit = on
```

Explanation:
- "ANY 1 of 2" means the primary waits for at least one standby to confirm WAL receipt
  before returning commit to the application.
- If standby1 is down, standby2 alone satisfies quorum — no availability loss.
- The committed data is on at least 2 nodes at all times — zero data loss on single failure.

Automated failover with Patroni:
- Patroni monitors primary health via Etcd (distributed lock).
- If primary fails, Patroni detects it within ~5 seconds (configurable).
- Patroni promotes the standby with the most recent WAL position.
- HAProxy health check detects new primary within ~5 seconds.
- Total RTO: ~10-15 seconds (well within 30-second target).

Trade-off:
- Synchronous commit adds latency to every write (round-trip to standby + disk write there).
- Typical added latency: 1-5ms on same-region replication.
- Acceptable for most OLTP. Unacceptable for <1ms latency requirements.

Alternative for lower latency:
- synchronous_commit = remote_write (standby writes to its OS buffer, not fsync'd to disk).
  Slightly lower durability guarantee but lower latency. Data loss possible if both primary
  and standby fail simultaneously, which is very rare.

---

## 9. Quick Reference Card

Study this until you can reconstruct it from memory.

---

### Database Internals One-Liners

```
B-Tree height:     4 levels at fan-out 400 --> ~25 billion rows
                   3 levels at fan-out 400 --> ~64 million rows

Secondary indexes: each index = +1 write per INSERT/UPDATE (that column)
                   15 indexes = up to 15x write amplification on inserts

WAL:               sequential disk writes (fast)
                   replayed forward on crash recovery
                   streamed to replicas in real time

MVCC:              old row versions kept in heap after UPDATE/DELETE
                   VACUUM removes versions no longer visible to any transaction
                   long transactions prevent VACUUM from cleaning up

Transaction IDs:   32-bit counter, wraps at ~2 billion
                   VACUUM FREEZE rewrites old XID to FrozenXID to prevent wraparound
                   XID wraparound = data corruption (PostgreSQL shuts down to protect)

PgBouncer:         transaction pooling = 20 real connections serving 5000 clients
                   session pooling = 1:1 mapping (breaks the multiplexing benefit)
                   transaction pooling breaks: prepared statements, advisory locks,
                   SET LOCAL, LISTEN/NOTIFY, session-level temporary tables

Buffer pool:       set shared_buffers to 25% of RAM (PostgreSQL)
                   set innodb_buffer_pool_size to 70-80% of RAM (MySQL)
                   target buffer hit rate: >99% for OLTP

Query plan:        EXPLAIN ANALYZE = actual rows vs estimated rows
                   estimated << actual --> stale statistics --> ANALYZE table
                   Nested Loop with many loops --> missing index on inner table

Clustered index:   rows stored in PK order (InnoDB) = fast PK range scan
                   random UUID PKs --> page splits --> slow inserts --> use UUIDv7

LSM vs B-Tree:     LSM: fast writes, slower reads, needs compaction
                   B-Tree: fast reads, moderate writes, no compaction needed
```

---

### When to Use What (Internals Perspective)

| Symptom                      | Root Cause                              | Fix                                               |
|------------------------------|-----------------------------------------|---------------------------------------------------|
| Slow INSERT/UPDATE           | Too many secondary indexes              | Drop unused indexes (check pg_stat_user_indexes)  |
| Table too large (bloat)      | Long txn blocking VACUUM                | Kill old transaction, then VACUUM ANALYZE         |
| "Too many clients" error     | No connection pool                      | Add PgBouncer in transaction mode                 |
| Bad query plan (wrong index) | Stale statistics                        | ANALYZE tablename                                 |
| pg_wal growing unboundedly   | Stale replication slot or long txn      | Drop slot or set max_slot_wal_keep_size           |
| XID wraparound warning       | Autovacuum falling behind               | VACUUM FREEZE; tune autovacuum aggressiveness     |
| Slow range scan on large tbl | Missing index or wrong index type       | EXPLAIN ANALYZE; add B-Tree or GIN index          |
| Read-your-own-write failures | Using read replicas with async lag      | Sticky routing to primary after writes            |
| Write throughput ceiling     | Single primary, too many indexes        | Shard writes; drop unused indexes; use LSM engine |
| OOM on database server       | work_mem too high x many connections    | Reduce work_mem, add PgBouncer to reduce conns    |
| Replica lag growing          | Replica saturated by analytics queries  | Move analytics off replica, add dedicated replica |
| Prepared stmt error (pgb)    | PgBouncer transaction mode              | Switch to session mode or disable server-side prep|

---

### Key Numbers to Memorize

```
Capacity
  Single PG node:  50K read QPS, 10K write QPS, 4TB before sharding is considered
  Connections:     100-300 comfortable, pool at anything higher
  Buffer pool:     25% of RAM (PG), 75% of RAM (MySQL)
  Table size OK:   up to 500M rows, 500GB before maintenance pain

Formula
  Concurrent connections needed = QPS x query_time_seconds (Little's Law)
  Total storage = rows x row_size x 1.2 x (1 + 0.3 x num_indexes) x 2 x 1.5

Replication
  Synchronous commit: adds 1-5ms per write (same region)
  Async replication lag: typically 0-100ms under normal load
  PITR needs: base backup + all WAL from that point to recovery target

MVCC
  Dead tuples created: 1 per UPDATE (old version kept), 1 per DELETE
  Cleanup: autovacuum runs every autovacuum_vacuum_scale_factor x live_tuples changes
  Default scale factor: 20% (for a 1M row table, VACUUM triggers at 200K changes)
  Long transaction impact: VACUUM cannot clean anything newer than oldest txn start
```

---

*End of Chapter 29: Database Internals Deep Dive — Part E*
*This is the final part of the chapter. Parts A through D cover B-Tree mechanics,*
*WAL and durability, MVCC and transactions, and query execution internals.*
## Supplemental Brainstorming: Chapter 29 -- Database Internals

*Questions 24-43: Advanced mechanics and cross-chapter integration.*

Practice these out loud. Aim for 5-7 minutes per question. Push past the first
correct-sounding answer -- interviewers at L6 expect you to explore trade-offs, name
numbers, and connect internals to operational reality.

---

### Section A: Deep Internals (Q24-Q33)

---

**Question 24 -- Size-tiered vs leveled compaction**

Your team is running Cassandra for a time-series sensor dataset. Writes are constant
at 80K/sec. Reads are infrequent batch exports that run nightly. A colleague proposes
switching from the default STCS (size-tiered compaction) to LCS (leveled compaction).

- Explain how STCS merges SSTables: same-size tiers collapse into the next tier. Why
  does this produce large, infrequent compaction events instead of steady background work?
- Explain how LCS maintains fixed-size levels (typically 160 MB each) and how it bounds
  read amplification to roughly O(number of levels) -- usually 5 or fewer SSTable reads.
- For this write-heavy, read-rare workload, which strategy is better? STCS tolerates
  higher write amplification on reads in exchange for lower compaction overhead during
  ingestion. LCS is better when reads dominate.
- Follow-up: the nightly batch reads are slow even with STCS. You cannot switch to LCS
  (write throughput would drop). What else can you do? (Hint: partition key design,
  pre-sorted exports, bloom filter tuning.)

---

**Question 25 -- Bloom filter sizing and false positive rate**

RocksDB is configured with bloom_bits_per_key = 10. Your LSM-Tree has 50 SSTables on
disk. A point lookup for a key that does not exist in the database runs a bloom filter
check on each SSTable before deciding to skip the disk read.

- Derive the false positive rate for a bloom filter with 10 bits per key. The formula
  is approximately (1 - e^(-kn/m))^k where k = number of hash functions, n = items,
  m = bits. At 10 bits/key with k = 7 hash functions the false positive rate is
  approximately 0.8%. Confirm this is low enough for your read SLA.
- With 50 SSTables and 0.8% false positive rate, approximately how many SSTables will
  you read unnecessarily on a missing-key lookup? (50 * 0.008 = 0.4, so nearly all
  missing lookups will correctly skip all 50 SSTables.)
- What happens to memory usage as you increase bloom_bits_per_key from 10 to 20?
  False positive rate drops to near 0%, but the bloom filter for a 100M-key SSTable
  now requires 100M * 20 bits = 250 MB of RAM per SSTable. With 50 SSTables that is
  12.5 GB just for bloom filters. How do you decide the right trade-off?
- Follow-up: block-level vs full-SSTable bloom filters -- when does a block-level bloom
  filter help more than a file-level one?

---

**Question 26 -- WAL shipping vs logical replication**

Your PostgreSQL primary is in us-east-1. You need a read replica in us-west-2 for
disaster recovery and read scaling. Your DBA proposes WAL shipping (archive_command +
restore_command). A developer proposes logical replication (pg_logical or built-in
logical slots).

- WAL shipping sends raw binary WAL files. The replica must be on the same PostgreSQL
  major version. You cannot replicate individual tables; it is all-or-nothing. What
  operational risk does a major-version upgrade create?
- Logical replication decodes WAL into row-level changes (INSERT/UPDATE/DELETE) and
  streams them as logical messages. You can replicate a subset of tables and even
  replicate into a different PostgreSQL major version. What is the overhead of logical
  decoding -- and why does it add CPU load on the primary?
- WAL shipping has no per-row filtering overhead but adds recovery lag equal to the
  WAL segment interval (default 16 MB). Logical replication can stream continuously but
  has a replication slot on the primary that holds WAL until the subscriber confirms.
  What happens if the subscriber disconnects for 48 hours?
- Follow-up: you want zero data loss failover (RPO = 0). Can WAL shipping achieve it?
  Can logical replication? Which PostgreSQL feature makes synchronous standby possible?

---

**Question 27 -- ARIES: UNDO vs REDO phases**

After a sudden power loss, PostgreSQL restarts and enters crash recovery. Walk through
the three phases of ARIES (Analysis, REDO, UNDO) and explain what happens to each of
the following transactions in the WAL:
- Transaction A: committed before the crash, all changes flushed to disk.
- Transaction B: committed before the crash, but some dirty pages had not been flushed.
- Transaction C: was active at the time of the crash, never committed.

- Analysis phase: scan the WAL from the last checkpoint to the crash point. Build the
  dirty page table (which pages were modified but not flushed) and the active
  transaction table (which transactions were in-flight).
- REDO phase: replay all WAL records from the oldest dirty page forward, including
  records from uncommitted transactions like C. Why? Because we do not yet know which
  pages made it to disk. REDO brings the database to the exact state at crash time.
- UNDO phase: roll back uncommitted transactions like C by applying their compensation
  log records (CLRs) in reverse. Transaction A and B require no undo -- they committed.
- Follow-up: why does ARIES write CLRs during UNDO rather than just deleting the
  original log records? What happens if the system crashes again during the UNDO phase?

---

**Question 28 -- Page cache and OS buffer pool interaction**

PostgreSQL has its own shared_buffers pool (let us say 8 GB on a 32 GB machine). The
OS also has a page cache. When PostgreSQL reads a page, it may be in shared_buffers,
in the OS page cache, or only on disk.

- Explain the double-buffering problem: a page evicted from shared_buffers but still in
  the OS page cache does not cause a disk read -- it is served from OS cache. But the
  page occupies RAM in two places simultaneously. What is the typical recommendation for
  shared_buffers sizing to avoid wasting OS page cache? (25-30% of total RAM.)
- O_DIRECT: some databases (InnoDB, RocksDB) use O_DIRECT to bypass the OS page cache
  entirely and manage their own buffer pool. PostgreSQL does not use O_DIRECT. What are
  the trade-offs? O_DIRECT eliminates double-buffering but loses the OS cache as a
  safety net, and requires aligned I/O which complicates writes.
- effective_cache_size in PostgreSQL is NOT a memory allocation -- it is a hint to the
  query planner about how much total cache (shared_buffers + OS cache) is available.
  Setting it too low causes the planner to underestimate index scan benefits and prefer
  sequential scans. How do you set it correctly?
- Follow-up: on a machine with 128 GB RAM running only PostgreSQL, what values would
  you set for shared_buffers, effective_cache_size, and work_mem for a system doing
  complex analytical queries with 50 concurrent users?

---

**Question 29 -- Index bloat and REINDEX in production**

A PostgreSQL B-Tree index on a high-churn column (order_status updated millions of
times per day) has grown to 40 GB but the underlying column data is only 2 GB. Your
on-call engineer says the index has 95% bloat.

- Explain how B-Tree index bloat accumulates: every UPDATE to a row creates a new heap
  tuple (MVCC) and must also mark the old index entry as dead and insert a new one.
  VACUUM can mark old index entries as reusable but cannot compact the index pages.
  Over time, pages fill with dead entries and the tree grows taller than necessary.
- REINDEX TABLE orders; reclaims all dead space but takes an exclusive lock, blocking
  all reads and writes for the duration. On a 40 GB index that could mean minutes of
  downtime. What is the alternative?
- REINDEX CONCURRENTLY builds a new index in the background without blocking writes.
  It is available from PostgreSQL 12+. What are the risks? (It can fail partway through,
  leaving a INVALID index that must be dropped and retried. It also temporarily uses
  double the disk space.)
- pg_repack is an extension that can repack tables and indexes without exclusive locks.
  How does it differ from REINDEX CONCURRENTLY in its approach?
- Follow-up: how do you detect index bloat before it causes query slowdowns? Which
  system view and query would you use?

---

**Question 30 -- Write stalls in LSM-Tree during compaction**

Your RocksDB-backed service (using TiKV or a custom store) handles 100K writes/second
under normal conditions. During a compaction event, write latency spikes from 2ms to
200ms and the p999 goes to 2 seconds. On-call gets paged.

- Explain why compaction causes write stalls: the memtable fills up faster than
  compaction can flush it to L0 SSTables. When the number of L0 SSTables exceeds
  level0_slowdown_writes_trigger (default 20 in RocksDB), the engine begins throttling
  writes. When it exceeds level0_stop_writes_trigger (default 36), writes are fully
  stalled until compaction catches up.
- What are your tuning levers? Increase compaction thread pool (max_background_compactions).
  Increase the memtable size so it fills less frequently (write_buffer_size). Increase
  the max number of memtables allowed before stalling (max_write_buffer_number).
- The root cause is often a burst of writes (e.g., a batch import) that exceeds the
  sustained compaction throughput. How do you distinguish a tuning problem from a
  provisioning problem?
- Follow-up: write stalls are predictable with the right metrics. What Prometheus
  metrics or RocksDB statistics would you alert on to detect compaction pressure before
  it becomes a stall?

---

**Question 31 -- MVCC and long-running transactions in high-churn tables**

A PostgreSQL table receives 50K updates/second. An OLAP query starts a REPEATABLE READ
transaction and runs for 45 minutes scanning the entire table for a report.

- While that transaction is active, can VACUUM reclaim any dead tuples created after
  the transaction started? No -- VACUUM checks the oldest active transaction's xmin
  (the transaction snapshot horizon) and skips any row version newer than it. Dead
  tuples accumulate for 45 minutes at 50K updates/second = 135 million dead tuples.
- Calculate the approximate heap bloat: if each dead tuple is 200 bytes, that is
  135M * 200 = 27 GB of bloat accumulated during one analytics run. If this query
  runs nightly, bloat compounds unless VACUUM can clean up between runs.
- Mitigation options: (1) Run the analytics query against a read replica where vacuum
  runs independently. (2) Use PostgreSQL logical replication to maintain a read replica
  and route all long queries there. (3) Export data to a data warehouse for analytics.
  (4) If you must run on primary, set statement_timeout or lock_timeout to cap query
  duration.
- Follow-up: what is transaction ID wraparound and why does it make long-running
  transactions a safety risk beyond just bloat?

---

**Question 32 -- Covering indexes and index-only scans**

Your e-commerce orders table has 500 million rows. A query fetches order_id, status,
and created_at for all orders by user_id in the last 30 days. The existing index is
on (user_id). The query is slow despite using the index.

- Explain what happens with a non-covering index: PostgreSQL uses the index to find
  the heap tuple pointers for matching user_id rows, then must do a heap fetch for
  every row to retrieve status and created_at. At 500M rows with many orders per user,
  this means thousands of random heap reads per query.
- A covering index on (user_id, created_at, status) can satisfy the query entirely
  from the index -- an index-only scan. The heap is not touched at all. What is the
  prerequisite for an index-only scan to work? (The visibility map must show the pages
  as all-visible -- VACUUM must have run on the heap pages.)
- If the visibility map is not up to date, PostgreSQL must still check the heap for
  every row to verify visibility. How do you force the visibility map to be updated
  without a full table vacuum? (VACUUM ANALYZE target_table; -- or rely on autovacuum
  running more aggressively.)
- Follow-up: covering indexes increase write amplification. If this table receives
  200K updates/second to the status column, what is the write cost of the covering
  index and how do you decide if the read benefit justifies it?

---

**Question 33 -- Write amplification: measuring and minimizing**

A distributed database team is reviewing storage costs. The system does 100K logical
writes/second at 1 KB each = 100 MB/s of logical write throughput. The storage
monitoring shows 800 MB/s of actual disk write I/O.

- The write amplification factor is 800 / 100 = 8x. Name each contributor to this
  amplification: (1) WAL write (1x overhead -- every logical write is also written
  to WAL before the heap). (2) B-Tree page writes: a single row insert may cause a
  full 8 KB page write even if only 100 bytes changed. (3) Secondary indexes: 5
  indexes = 5 additional B-Tree writes per row. (4) Checkpointing: dirty pages are
  written again during checkpoint. (5) Replication: WAL is shipped to replicas.
- For an LSM-Tree system, write amplification comes primarily from compaction.
  A key written to L0 may be rewritten during L0-to-L1 compaction, L1-to-L2
  compaction, and so on. With 7 levels, a write may be physically written 7-10 times.
- How do you reduce write amplification in a B-Tree system? Fewer secondary indexes,
  larger pages, delayed checkpointing, partial page writes disabled (with UPS/NVRAM).
- How do you reduce write amplification in an LSM-Tree system? Use leveled compaction
  with a lower level multiplier, increase L0 size so early compactions are rarer, use
  compression to reduce the bytes written per compaction pass.
- Follow-up: SSD endurance is rated in drive writes per day (DWPD). A 2 TB NVMe SSD
  at 1 DWPD tolerates 2 TB of writes per day. At 800 MB/s write I/O, how many TB per
  day is the system writing? Does this exceed the drive's endurance rating?

---

### Section B: Cross-Chapter Integration (Q34-Q43)

---

**Question 34 -- Ch29 + Ch28: RocksDB read latency spike at 3x scale**

A team chose RocksDB (an LSM-Tree engine, used internally by CockroachDB, TiKV, and
many custom stores) for their user profile store expecting fast writes. At 3x their
original scale they notice p99 read latency climbing from 5ms to 150ms. Writes are
still fast. Nothing else changed.

- Diagnose using LSM-Tree internals: at 3x scale, the dataset is 3x larger. More
  SSTables exist across more levels. A point lookup now touches bloom filters on more
  files per level and, when bloom filter false positives occur, reads more SSTable
  blocks. Read amplification grows with the number of levels and files per level.
- Compaction may be falling behind: if the compaction thread pool is not sized for
  3x write volume, L0 SSTable count grows, and read amplification increases further
  because L0 files are not sorted relative to each other (every L0 file must be
  checked on a point lookup).
- Fixes: (1) Increase compaction threads. (2) Increase bloom_bits_per_key to reduce
  false positives. (3) Use leveled compaction if not already -- it bounds the number
  of SSTables a read must check. (4) Add a row cache (RocksDB's block cache) sized to
  hold the hot working set.
- From Ch28: if the access pattern is Zipfian (20% of user profiles get 80% of reads),
  a cache hit rate of 80%+ would eliminate most disk reads. Evaluate whether a Redis
  layer in front of RocksDB (look-aside cache) would be more cost-effective than
  re-tuning the storage engine.
- Follow-up: at 10x scale, read amplification becomes structural. At what point do
  you migrate to a different storage engine (e.g., a B-Tree-based store for read-heavy
  user profiles) rather than continuing to tune RocksDB?

---

**Question 35 -- Ch29 + Ch33/Ch34: Kafka log segments vs LSM-Tree SSTables**

Kafka's storage model uses append-only log segments on disk. LSM-Trees also use
append-only structures (the WAL and SSTables). A systems design interviewer asks you
to compare the two.

- Kafka segments: Kafka appends messages sequentially to the active segment file.
  When the segment reaches max.bytes (default 1 GB) it is rolled. Old segments are
  retained for a configured retention period then deleted. There is no in-place update;
  consumers read sequentially by offset.
- LSM-Tree SSTables: also immutable, append-only files. But SSTables are sorted by key
  and support point lookups and range scans. Kafka segments are ordered by arrival time
  (offset), not by key, so a point lookup by message key requires scanning all segments
  or using an offset index file.
- Compaction in Kafka: Kafka log compaction retains only the latest value per key,
  discarding older values. This is analogous to LSM merging: when two SSTables contain
  the same key, the newer value wins. But Kafka compaction is triggered by log.cleaner
  threads and targets a compaction ratio, not size tiers or levels.
- Compaction in Cassandra (LSM): size-tiered or leveled, focused on reducing read
  amplification and reclaiming space from tombstones and superseded versions. The goal
  is query performance, not retention policy.
- Fast appends in Kafka: sequential disk writes, batch acknowledgment, page cache
  exploitation with sendfile(). Kafka never rewrites existing data, so there is no
  compaction-induced write stall for producers.
- Follow-up: Kafka uses an offset index (sparse index mapping offset to byte position)
  to enable O(log n) seeks. How is this similar to and different from a B-Tree index?

---

**Question 36 -- Ch29 + Ch35: Scanning 500M rows in PostgreSQL for a batch job**

Your batch job must scan 500 million rows in a PostgreSQL orders table to compute
weekly revenue by region. The job takes 4 hours and is blocking the nightly ETL window.

- Sequential scan vs index scan: for a full-table scan, a sequential scan is almost
  always faster than a B-Tree index scan because sequential I/O is 10-100x faster than
  random I/O. The query planner should choose a sequential scan for a predicate that
  matches more than ~5% of the table. If it is not, check statistics and force with
  enable_indexscan = off.
- Index-only scans and covering indexes: if you only need a few columns (order_id,
  region, amount, created_at), a covering index on those columns lets PostgreSQL read
  entirely from the index, which is smaller than the heap and can be scanned
  sequentially. For a 500M row table with 50 columns, the covering index may be 5-10x
  smaller than the heap scan.
- Parallel sequential scans: PostgreSQL supports parallel seq scans (max_parallel_workers_per_gather).
  With 8 workers, the 4-hour job could drop to ~30 minutes. Tune max_parallel_workers
  and max_parallel_maintenance_workers. Be aware that this consumes additional I/O and
  CPU -- size the parallel workers to not starve OLTP queries.
- Parquet on S3 vs PostgreSQL: for this purely analytical workload, exporting data to
  Parquet (columnar, compressed) and querying with Athena or Spark is often 10-100x
  faster and cheaper. Parquet stores each column separately -- a scan of amount and
  region reads only those columns' bytes, not the entire row. PostgreSQL is row-oriented
  and must read full pages even if you need two columns.
- Decision framework: if the batch job runs daily and the table is append-mostly, use
  an incremental export pipeline (Debezium -> S3 -> Parquet) rather than full-table
  PostgreSQL scans. Reserve PostgreSQL for OLTP; use the data lake for analytics.
- Follow-up: the team wants to stay on PostgreSQL. Would partitioning the table by
  week on created_at help? How does partition pruning reduce the scan? What is the
  operational cost of maintaining a partitioned table?

---

**Question 37 -- Ch29 + Ch38: Write amplification and cloud storage cost**

Your LSM-Tree system (RocksDB-backed) has a write amplification factor of 10x. Logical
write throughput is 100K writes/second at 1 KB each.

- Calculate physical disk I/O: 100K * 1 KB * 10 = 1,000,000 KB/s = ~1 GB/s of disk
  writes. Confirm your storage I/O provisioned IOPS and throughput can sustain this.
  On AWS EBS (gp3), max throughput is 1 GB/s and max IOPS is 16,000 for a single
  volume. You will need io2 Block Express or multiple striped volumes.
- Calculate monthly cloud storage write cost: 1 GB/s * 86,400 s/day * 30 days =
  2,592 TB of data written per month. At AWS EBS io2 pricing (~$0.125/GB-month for
  storage + $0.065/IOPS-hour for provisioned IOPS), this is a significant line item.
  EBS charges for storage provisioned, not bytes written, but IOPS and throughput
  add up. Estimate the cost of provisioned IOPS needed for 1 GB/s throughput.
- How does compaction strategy affect cost? With size-tiered compaction, compaction
  events are bursty (high IOPS spikes during compaction). Provisioned IOPS must cover
  the peak. With leveled compaction, compaction is steady and smaller, so you can
  provision for average rather than peak IOPS.
- Reducing write amplification by 2x (from 10x to 5x) cuts physical I/O in half,
  halving IOPS provisioning cost. Strategies: larger memtable, fewer levels, key
  prefix compression, value separation (WiscKey approach where large values are stored
  in a separate value log, not in the LSM-Tree itself).
- Follow-up: at 100K writes/second, what is the monthly data ingestion and how long
  until you hit a 100 TB storage cap? How does SSTable compression (Snappy, Zstd)
  change the storage footprint? Zstd at 3x compression ratio cuts the cap extension
  factor by 3x.

---

**Question 38 -- Ch29 + Ch36: WAL shipping replication lag across regions**

You are replicating a PostgreSQL primary in us-east-1 to an EU replica in eu-west-1
using WAL shipping. The primary generates 500 MB WAL files. A major write burst just
generated 2 GB of WAL in 60 seconds.

- Calculate replication lag: a transatlantic TCP connection sustains roughly 50-100
  MB/s depending on congestion and MTU. Transferring 2 GB at 50 MB/s takes 40 seconds.
  During that 40 seconds, the EU replica is 40 seconds behind -- plus the time for
  the replica to apply the WAL. Application is another 5-20 seconds for heavy WAL.
  Total lag: 45-60 seconds.
- WAL shipping sends complete segment files (default 16 MB each). The EU replica
  only starts applying a segment after the entire file has arrived. If the primary
  is idle and the current segment never fills, the replica can be minutes behind
  even with no network lag. Tune wal_sender_timeout and archive_timeout to force
  segment rotation.
- RTO if the primary dies: you need to promote the replica. Promotion requires
  replaying any received but unapplied WAL. If 500 MB of WAL arrived but was not
  applied, applying it at 50 MB/s application rate takes ~10 seconds. Total RTO
  from detection to promotion: 30-120 seconds in a well-tuned setup.
- RPO: any WAL that was not shipped before the crash is lost. With WAL shipping,
  RPO = last_shipped_segment_time to crash_time. This can be up to 16 MB of writes
  (one segment) or more if shipping is lagging. For RPO = 0, you need synchronous
  streaming replication, not WAL shipping.
- Follow-up: how does streaming replication differ from WAL shipping in terms of
  latency and RPO? What is the operational complexity of running synchronous streaming
  replication across two AWS regions? What effect does it have on primary write latency?

---

**Question 39 -- Ch29 + Ch28: Choosing between PostgreSQL and Cassandra for a write-heavy IoT workload**

An IoT platform ingests 500K sensor readings/second. Each reading is a small key-value
pair (device_id, timestamp, value). Queries are: (1) latest reading per device, (2)
all readings for a device in the last hour. No transactions, no joins.

- PostgreSQL with B-Tree: 500K writes/second will overwhelm a single PostgreSQL
  instance (practical ceiling is ~50-100K writes/second on high-end hardware). Even
  with sharding, each write touches the B-Tree (random I/O for random device_ids),
  WAL, and secondary indexes. The random I/O pattern for a wide device_id space will
  cause constant page splits and high I/O amplification.
- Cassandra with LSM-Tree: append-only writes go to the memtable first (in-memory,
  very fast). Flushes are sequential. Cassandra is designed for this exact pattern:
  wide partitions keyed by (device_id, timestamp) support both latest-reading queries
  (read last row of partition) and time-range queries (efficient slice reads).
- From Ch28: the key question is whether the partition key design avoids hot partitions.
  If 1% of devices generate 99% of writes, those partitions become hot spots even in
  Cassandra. Solution: add a bucket to the partition key to spread load.
- Trade-offs of Cassandra: eventual consistency, no transactions, no joins, complex
  schema design upfront (denormalization required). Trade-offs of PostgreSQL: requires
  significant sharding/partitioning work to reach 500K writes/sec, but you get ACID
  and simpler querying.
- Follow-up: at what write volume does PostgreSQL become impractical without specialized
  solutions like Citus or TimescaleDB? When you hit that wall, what are the migration
  risks of moving 5 TB of historical data from PostgreSQL to Cassandra?

---

**Question 40 -- Ch29 + Ch33: CDC with Debezium and WAL logical decoding**

Your team is implementing change data capture (CDC) from PostgreSQL to Kafka using
Debezium. Debezium uses PostgreSQL logical replication to stream row-level changes.

- Explain what happens in PostgreSQL: a logical replication slot is created. As
  transactions commit, PostgreSQL logical decoding reads the WAL and produces
  row-level change events (INSERT/UPDATE/DELETE with before/after values) using
  the pgoutput or wal2json plugin.
- The replication slot holds WAL until Debezium confirms it has read and processed
  it. If Debezium goes down for 6 hours, how much WAL accumulates? At 100 MB/s of
  WAL generation, 6 hours = 2.16 TB. Your pg_wal directory must have space for this.
  If it fills, PostgreSQL panics and shuts down.
- Debezium publishes changes to Kafka topics. The Kafka topic is partitioned by
  primary key, ensuring that changes to the same row always go to the same partition
  and are processed in order. Why is ordering-by-key important for downstream consumers?
- Schema changes (DDL) are a challenge: if you ALTER TABLE to add a column, Debezium
  must handle the schema change gracefully. Debezium uses a schema registry (Confluent
  Schema Registry or AWS Glue) to track schema versions.
- Follow-up: you want exactly-once delivery from PostgreSQL to your data warehouse.
  Debezium + Kafka guarantees at-least-once by default. How do you achieve exactly-once
  semantics end-to-end? (Hint: idempotent consumers, deduplication by LSN.)

---

**Question 41 -- Ch29 + Ch35: Building an incremental data pipeline on top of WAL**

Your data engineering team wants to move from nightly full exports of a 10 TB
PostgreSQL database to an incremental pipeline that keeps the data warehouse current
within 5 minutes.

- Full export approach: every night, pg_dump --format=custom produces a 10 TB dump.
  Restoring it to the warehouse takes 6 hours. You are always at least 6 hours behind.
- Incremental approach using WAL: Debezium (logical replication) streams changes to
  Kafka within seconds of commit. A Flink or Spark Streaming job reads Kafka and
  applies upserts to the warehouse. The warehouse is now within 5 minutes of the source.
- Challenges of incremental pipelines: (1) Handling deletes: a logical delete in
  PostgreSQL becomes a tombstone event in Kafka -- the warehouse must support deletes
  or soft-delete patterns. (2) Schema evolution: an ALTER TABLE on the source must
  be propagated to the warehouse schema. (3) Bootstrapping: the initial snapshot of
  10 TB must be loaded consistently (without blocking the source) before the streaming
  pipeline takes over.
- The snapshot-then-stream problem: Debezium solves this with a consistent snapshot
  mode -- it takes a snapshot while holding an ACCESS SHARE lock, records the LSN at
  snapshot time, then switches to streaming from that LSN. But holding a lock on a
  10 TB table for hours blocks DDL.
- Follow-up: if the warehouse is BigQuery or Snowflake, how do you efficiently apply
  upserts? Both support MERGE statements but they are expensive at high frequency.
  What is the pattern of micro-batching upserts every 5 minutes vs. streaming every
  second?

---

**Question 42 -- Ch29 + Ch36: Split-brain during multi-region failover and the WAL**

You are running PostgreSQL with streaming replication between us-east-1 (primary) and
eu-west-1 (standby). The network between regions partitions for 3 minutes. During the
partition, your automatic failover system promotes the EU standby to primary.

- The original primary in us-east-1 is still running and accepting writes (it did not
  crash -- it just cannot reach EU). For those 3 minutes, both regions are accepting
  writes. This is split-brain.
- When the network partition heals, the us-east-1 node connects to the new EU primary
  and discovers it is behind. The WAL timelines have diverged. PostgreSQL uses timeline
  IDs to detect this: after promotion, the new primary increments the timeline ID.
  The old primary's WAL after the split point is on a different timeline and cannot
  be automatically merged.
- Data written to us-east-1 during the split must be manually recovered or discarded.
  How much data is at risk? 3 minutes of writes at whatever the application's write
  rate is. At 10K writes/second, up to 1.8 million transactions are unrecoverable.
- Preventing split-brain: (1) Require a quorum of replicas to acknowledge before
  promoting (Patroni with etcd quorum). (2) Use a fencing token / STONITH to shoot
  the old primary before promoting. (3) Use synchronous replication so the primary
  cannot commit without EU replica ACK -- but this means any network partition also
  stalls writes on the primary.
- Follow-up: what is the correct RTO vs RPO trade-off here? A strict RPO = 0 requires
  synchronous replication and accepting write stalls during any inter-region network
  hiccup. A looser RPO = 3 minutes allows async replication and faster failover.
  How do you present this trade-off to a product team?

---

**Question 43 -- Ch29 + Ch38: Cost of dead tuple bloat and vacuum at scale**

Your PostgreSQL cluster stores 20 TB of live data but the actual disk footprint is
60 TB. The extra 40 TB is dead tuple bloat. You are paying for 60 TB of EBS storage.

- Calculate the monthly cost difference: on AWS, gp3 EBS is $0.08/GB-month.
  40 TB * 1024 GB/TB * $0.08 = $3,277/month wasted on bloat storage.
  At io2 pricing ($0.125/GB-month), that is $5,120/month wasted.
- Why did bloat reach this level? Most likely: (1) autovacuum is too conservative
  (default autovacuum_vacuum_scale_factor = 0.2 means vacuum triggers when 20% of
  the table is dead -- on a 1 TB table that is 200 GB of dead tuples before vacuum
  even starts). (2) Long-running transactions (analytics jobs) blocking vacuum's
  ability to reclaim space.
- Fix autovacuum thresholds: set autovacuum_vacuum_scale_factor = 0.01 (trigger at
  1% dead tuples) and autovacuum_vacuum_threshold = 1000 for high-churn tables.
  Override at the table level with ALTER TABLE ... SET (autovacuum_vacuum_scale_factor = 0.01).
- Immediate reclamation: VACUUM FULL compacts the table but requires an exclusive lock.
  pg_repack reclaims space online without locking. At 60 TB, pg_repack will take
  many hours -- plan this during low-traffic windows and monitor replication lag
  (pg_repack generates significant WAL).
- Structural fix: move long-running analytical queries to a read replica. The primary
  vacuum is no longer blocked. Use idle_in_transaction_session_timeout = 5min to
  kill stuck transactions automatically.
- Follow-up: after reclaiming the 40 TB, autovacuum must prevent the bloat from
  returning. What monitoring would you set up to alert before bloat exceeds 10% of
  live data size? Which pg_stat_user_tables columns are the key signals?

---

*End of Supplemental Brainstorming: Chapter 29.*

---

## Exercises

**Exercise 1 — B-tree vs LSM comparison.** For each workload, choose B-tree or LSM-tree and justify: (a) write-heavy time-series (1M writes/second, rarely read), (b) transactional OLTP (50K reads/second, 5K writes/second), (c) append-only log store, (d) point lookup with occasional range scans. What's the key differentiator for each choice?

**Exercise 2 — WAL and recovery.** A PostgreSQL instance crashes mid-transaction. Walk through: what's in the WAL, how crash recovery works (redo phase, undo phase), what the final committed state is, and what happens to in-flight transactions. What's the difference between checkpoint frequency and WAL segment size?

**Exercise 3 — Index effectiveness analysis.** Given a query: `SELECT * FROM orders WHERE customer_id = ? AND status = 'pending' AND created_at > ?`. You have three indexes: (a) (customer_id), (b) (customer_id, status), (c) (customer_id, status, created_at). Which index does Postgres use? What's the selectivity order and how does it affect the choice?

**Exercise 4 — MVCC visibility.** Two transactions run concurrently in PostgreSQL with READ COMMITTED isolation. Transaction A updates row X. Transaction B reads row X. Walk through: what version of row X does B see at different points (before A commits, during A's commit, after A commits)?

**Exercise 5 — Vacuum and bloat.** A PostgreSQL table has 10M rows with 100 updates/second. After 30 days, what's the dead tuple count? What's the impact on query performance? When does autovacuum run, and what happens if it can't keep up?

**Exercise 6 — Write amplification calculation.** A 10MB SSTable in RocksDB is compacted. Compaction reads the old SSTable and writes the result back. If there are 5 compaction levels and average write amplification is 10x per level, what's the total write amplification for data written to L0?

---

## Homework

**Assignment 1 — EXPLAIN ANALYZE deep dive.** Take your three slowest production queries. Run EXPLAIN ANALYZE. Identify: sequential scans that should be index scans, nested loops that should be hash joins, and missing statistics. Propose one fix per query.

**Assignment 2 — Storage engine comparison.** Choose any two storage engines (InnoDB vs MyISAM, RocksDB vs LevelDB, WiredTiger vs MMAPv1). Write a 2-page comparison: data structures used, write path, read path, crash recovery approach, and the workload each is optimized for.

**Assignment 3 — Interview practice: database internals.** Practice explaining how B-tree indexes work, including: how data is stored, how a range scan works, why B-tree beats binary search tree, and what happens during an index rebuild on a live table.

**Assignment 4 — Read "Designing Data-Intensive Applications" (Kleppmann), Chapter 3.** Focus on storage engines and data structures. Write a one-paragraph summary: what is the fundamental trade-off between B-tree and LSM-tree, and when does each win?
