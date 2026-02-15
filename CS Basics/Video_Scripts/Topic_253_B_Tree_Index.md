# B-Tree Index: Why Databases Use It

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A phone book. Ten million names. You need to find "Negi." Do you start at page one? Flip through every page? Of course not. You open to the middle. "M"—too early. Open to three-quarters. "P"—too far. Back a bit. "N"—close. A few more flips. Found it.

That's binary search. And the B-tree is the data structure that makes this possible in databases. It keeps data sorted and lets you jump to the right place in three or four steps—even with billions of rows. Here's how.

---

## The Story

Imagine a phone book. Sorted by last name. A to Z. Ten million entries. One name per page? No. Hundreds of names per page. The book has an index at the front: "A–D: pages 1–100. E–H: 101–200." You use that to jump to the right section.

Inside each section, maybe another level. "E: 101–110. F: 111–120." You narrow it down. Finally, you're in the right range. A few page flips. You find "Negi."

That's a B-tree. Multiple levels. Each level helps you jump closer. At the leaves, you find the actual data—or a pointer to it.

The magic: you only need a few steps. Not millions. With a branching factor of 500—each node has up to 500 children—a tree with 1 billion rows might have only 4 levels. Four disk reads. Four. To find any row in a billion.

---

## Another Way to See It

Think of a filing cabinet with drawers. Each drawer has folders. Each folder has sections. Each section has papers. You don't search every paper. You open the right drawer. The right folder. The right section. Three or four moves, and you're there.

A B-tree is that hierarchy. But optimized for disk. Each node fits in one disk page—4 KB or 16 KB. Reading one page is one disk read. Expensive. So you want WIDE nodes. Many children. Fewer levels. Fewer disk reads.

---

## Connecting to Software

A B-tree is a balanced tree. Not binary—each node can have many children. Hundreds. Each node = one disk page. Root at the top. Internal nodes in the middle. Leaf nodes at the bottom, holding data or pointers.

**Why B-tree, not binary tree?** Disk reads are expensive. A binary tree is tall. A billion rows = 30 levels. Thirty disk reads for one lookup. Slow. A B-tree with branching factor 500: four levels. Four disk reads. Same data. Ten times fewer reads.

**Operations:** Search = find the path from root to leaf. O(log N). Insert = find position, add (may split node if full). Delete = find, remove (may merge nodes if too empty). The tree stays balanced. Range queries are efficient: find the start leaf, scan forward. "All rows where id between 1000 and 2000"—perfect for B-trees. The leaves are linked. Sequential scan. Fast.

Why B+ tree (common variant): leaf nodes hold all the data; internal nodes only hold keys for routing. More keys per internal node = even fewer levels. Leaves form a linked list—range scans are trivial. Industry standard.

---

## Let's Walk Through the Diagram

```
                    [Root: 50, 100, 150]           <- 1 disk read
                     /      |      \
                    /       |       \
        [10,20,30] [60,70,80] [110,120,130]        <- 2nd disk read
           |           |            |
           v           v            v
        [leaf]      [leaf]       [leaf]            <- 3rd disk read
        data...     data...      data...

Each [ ] = one disk page (4-16 KB)
Branching factor ~100-500 = shallow tree
1 billion rows ≈ 4 levels = 4 disk reads
```

Wide and shallow. That's the B-tree advantage.

---

## Real-World Examples (2-3)

**PostgreSQL:** Uses B-trees for most indexes. CREATE INDEX builds a B-tree. Every lookup uses it. Default and battle-tested.

**MySQL (InnoDB):** Clustered B-tree for the primary key. Secondary indexes are B-trees that point to the primary key. Same idea, different layout.

**SQLite:** B-tree for tables and indexes. Even tiny databases use it. The structure scales from kilobytes to terabytes. Your phone's apps, your browser's stored data—B-trees everywhere.

**MongoDB:** B-tree (WiredTiger storage engine) for indexes. Default _id index. Secondary indexes. Same O(log N) lookups. NoSQL, but the fundamentals are the same. When you need to find things fast, B-tree is the answer.

---

## Let's Think Together

**Question:** A table has 100 million rows. The B-tree has a branching factor of 500. How many levels? How many disk reads for a lookup?

**Answer:** Level 1: 1 node (root). Level 2: up to 500 nodes. Level 3: up to 500² = 250,000 nodes. Level 4: up to 500³ = 125 million nodes. So 100 million rows fit in 4 levels. A lookup: 4 disk reads. From root to leaf. Done.

---

## What Could Go Wrong? (Mini Disaster Story)

A table grows. Index gets fragmented. Inserts and deletes leave holes. The B-tree stays correct, but pages are half-empty. More levels than needed. Lookups slow down. Queries that used to take 10 ms now take 100 ms.

The fix: REINDEX. Rebuild the tree. Consolidate. Expensive—locks the table or takes a long time. But sometimes necessary. Maintenance matters. In PostgreSQL, VACUUM can reclaim space from dead tuples, but index bloat often needs REINDEX. Schedule it during low-traffic windows. Some databases support online reindex—rebuild without blocking reads. Check your DB's capabilities.

---

## Surprising Truth / Fun Fact

The "B" in B-tree doesn't stand for "binary." It stands for "balanced." Or possibly "Boeing"—Rudolf Bayer and Ed McCreight invented it at Boeing in 1972. The name's origin is fuzzy. But the impact is not: almost every serious database uses B-trees or variants (B+ trees) for indexing. LSM-trees (Log-Structured Merge) are an alternative—used in Cassandra, RocksDB—optimized for write-heavy workloads. But for read-heavy, point lookups, and range scans, B-trees remain dominant. Forty-plus years. Still the default. That's staying power. Learn the B-tree—it's the foundation of nearly every database index you'll ever use.

---

## Quick Recap (5 bullets)

- **B-tree** = balanced tree with many children per node; each node = one disk page
- **Why not binary?** = disk reads are expensive; wide tree = fewer levels = fewer reads
- **Scale** = 1 billion rows, branching factor 500 ≈ 4 levels ≈ 4 disk reads
- **Operations** = search O(log N); insert/delete may split or merge nodes
- **Ubiquity** = PostgreSQL, MySQL, SQLite—all use B-trees for indexes

---

## One-Liner to Remember

**A B-tree is wide and shallow: many children per node, few levels, so finding one row among millions takes just a handful of disk reads.**

---

## Next Video

Up next: Secondary indexes. Why having too many can kill your writes. The cost of that extra catalog.
