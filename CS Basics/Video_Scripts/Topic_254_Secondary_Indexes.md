# Secondary Indexes: Cost and Use

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A library catalog. Sorted by title. You want "Harry Potter"—easy. But what if you want "all books by J.K. Rowling"? The catalog is by title, not author. You'd have to scan every entry. Thousands of them.

You need a second catalog. Sorted by author. Same books, different order. You look up "Rowling, J.K." and get a list of titles. That's a secondary index. Powerful. But expensive. Here's why.

---

## The Story

In a library, the main catalog might be by call number—how books are physically arranged on shelves. That's the primary index. One way to find things.

But patrons search by title. By author. By subject. One catalog isn't enough. You add a second. By author. A third. By subject. Each catalog points to the same books. Different order. Different purpose.

In a database, the primary index orders data by the primary key. Often, that's how rows are physically stored. Clustered. One index per table.

But queries filter by other columns. "Find all orders by user 123." "Find all products in category 'Electronics'." The primary key doesn't help. You need a secondary index—a separate B-tree (or similar) that maps "user_id = 123" to a list of row pointers. Or "category = Electronics" to rows.

---

## Another Way to See It

Think of a spreadsheet. One column is the "main" sort—maybe ID. But you often filter by status, by date, by customer. Excel lets you sort by any column. But that's in memory. In a database, sorting by another column means building and maintaining a separate structure. That structure is the secondary index.

---

## Connecting to Software

**Primary index:** Data physically ordered by primary key. Clustered. One per table. Lookup by primary key = one B-tree walk. Fast.

**Secondary index:** Separate structure. B-tree on "user_id" or "created_at" or "category." Each leaf points to rows—either direct pointers or primary key values. Multiple secondary indexes per table.

**The cost:** Every INSERT, UPDATE, or DELETE must update EVERY index. Add a row? Update primary index + all secondary indexes. Five indexes = six writes per row (one primary + five secondary). Writes multiply. Disk fills. Performance drops.

**When worth it:** When reads on that column vastly exceed writes. Heavy filtering or sorting by "user_id"? Index it. Rarely queried? Skip it. Composite indexes: index on (user_id, created_at) lets you efficiently query "user 123's orders by date" with one index. Order matters—(a, b) helps "where a = X order by b" but not "where b = Y."

Monitoring: track slow queries. Add index for them. Track write latency. Too many indexes? Writes suffer. Remove unused indexes. `pg_stat_user_indexes` in PostgreSQL shows index usage. Zero scans? Consider dropping.

---

## Let's Walk Through the Diagram

```
PRIMARY INDEX (by id)          SECONDARY INDEX (by user_id)
+------------------+           +----------------------+
| id=1 -> row 1    |           | user_id=100 -> [1,5,9]|
| id=2 -> row 2    |           | user_id=101 -> [2,7]  |
| id=3 -> row 3    |           | user_id=102 -> [3,4,8]|
+------------------+           +----------------------+

INSERT new row (id=10, user_id=101)
     |
     v
Must update BOTH structures
- Add to primary: id=10
- Add to secondary: user_id=101 -> append 10

More indexes = more work per write
```

---

## Real-World Examples (2-3)

**E-commerce:** Products table. Primary key = product_id. Secondary indexes on category_id (filter by category), price (sort by price), created_at (new arrivals). Each index speeds up certain queries. Each slows down writes.

**Social app:** Posts table. Primary key = post_id. Secondary indexes on user_id (my posts), created_at (feed), thread_id (comments). A viral post gets millions of reads—indexes pay off. But a busy feed means many writes—index cost is real.

**Analytics:** Events table. Primary key = event_id. Secondary index on user_id. Huge table. Writes are append-only. Index on user_id = fast "all events for user X." Worth it. Append-only means every write goes to the end of the index—minimal fragmentation. Time-series + secondary index on user = powerful combo.

**Support ticket system:** Tickets by ticket_id (primary). Secondary on status, assignee_id, created_at. "Show me open tickets assigned to support agent 7" = index on (assignee_id, status). Fast. Without it = full table scan on millions of rows.

---

## Let's Think Together

**Question:** A table has 10 columns. Someone adds an index on EVERY column. Why is this a terrible idea?

**Answer:** Every INSERT updates 11 structures (1 primary + 10 secondary). Writes become 11 times more expensive. Disk usage explodes. Indexes that are never used still get updated. The rule: index only what you query. Measure. Don't guess. One well-chosen index beats ten random ones.

---

## What Could Go Wrong? (Mini Disaster Story)

A new developer adds indexes to "make queries faster." They add one on status, one on priority, one on assignee, one on created_at, one on updated_at. The table had 3 indexes. Now it has 8. Writes slow down. Bulk import that took 10 minutes now takes an hour. Deployments timeout. The database groans.

The lesson: indexes are a trade-off. Every index costs writes and space. Add with care. Remove unused ones. Use EXPLAIN ANALYZE to verify an index is actually used. Sometimes the query planner chooses a full scan—maybe the table is small, or the index selectivity is poor. Don't assume more indexes = better. Measure. Profile. Optimize based on data.

---

## Surprising Truth / Fun Fact

Some databases support "covering" indexes—indexes that include extra columns beyond the key. A query can be satisfied entirely from the index, without touching the table. "Index-only scan." Fewer disk reads. Faster. But the index grows. Trade-offs everywhere. PostgreSQL's INCLUDE clause lets you add columns to an index for covering. MySQL has similar. Use when a query only needs indexed + included columns. Eliminates table lookups. Significant speedup for the right query pattern. The rule of thumb: index columns you filter on, include columns you select. Simple but effective.

---

## Quick Recap (5 bullets)

- **Primary index** = one per table; data ordered by primary key; clustered
- **Secondary index** = separate structure mapping another column to row pointers
- **Cost** = every write updates ALL indexes; more indexes = slower inserts/updates/deletes
- **Worth it when** = reads on that column >> writes; filtering/sorting benefits
- **Avoid** = indexing every column; unused indexes still cost writes

---

## One-Liner to Remember

**Secondary indexes speed up reads by column—but every index you add multiplies write cost; index only what you query.**

---

## Next Video

Up next: Write-ahead log. The accountant's journal that saves your database when the server crashes.
