# Why Do We Need Indexes? Trade-offs

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A city phone book. 5 million names. You need "Priya Sharma." Without alphabetical order, you check every page. One by one. Days of work. With alphabetical order? Flip to S. Then Sh. Then Sha. Thirty seconds. Beautiful. But here's the catch. Every time someone NEW moves to the city, the phone company must RE-SORT the book. Insert the new name in the right place. And there are copies — sorted by name, by address, by phone number. Three books. Every new person. Three updates. Indexes are amazing for reading. But costly for writing. Let's talk about why we need them — and when they hurt.

---

## The Story

Why do we need indexes? Speed. A SELECT with a WHERE clause. Without an index, the database does a full table scan. Read every row. Check the condition. Return matches. 100 million rows? 100 million reads. That could take minutes. Or hours. With an index, the database uses a B-tree. Sorted structure. Binary search. Log of 100 million is about 27. Twenty-seven lookups. Milliseconds. That's the difference between a dead app and a snappy one. Indexes turn O(n) into O(log n). That's not a small win. It's existential.

But. There's always a but. Every INSERT adds a row. The index must add an entry. Sorted. The B-tree must find the right position. Insert. Maybe rebalance. Same for UPDATE — if you change an indexed column. Same for DELETE — remove from index. One write. One index update. Five indexes? Five updates. The write gets five times heavier. You're trading write speed for read speed. That's the trade-off. Not free. Not automatic. A choice.

---

## Another Way to See It

Imagine a filing cabinet. Papers in random order. Finding something? Check every paper. Add an index — a separate sorted list of "Subject → Drawer, Folder." Finding? Instant. But every time you add a new paper, you must update the index. Insert in the right place. Multiple indexes? Multiple updates. The indexing clerk works harder. Filing gets slower. You can't have maximum find speed AND maximum add speed. You balance.

---

## Connecting to Software

**Types of indexes:** B-tree (default, great for range queries like WHERE age > 20), Hash (exact match only, faster for equality), Composite (multiple columns, e.g., email + created_at), Full-text (for search — "containing these words"). Choose based on your queries. A covering index contains all columns the query needs — the database never touches the table. Super fast. But bigger. More to maintain.

**Space:** Indexes take disk space. A table with 5 indexes might have indexes LARGER than the data. You're storing the data plus 5 sorted copies. Storage costs. Backup size. All of it grows.

---

## Let's Walk Through the Diagram

```
THE INDEX TRADE-OFF

READS (SELECT)                    WRITES (INSERT/UPDATE/DELETE)

No Index:                          No Index:
  Scan 100M rows                     Insert 1 row → 1 write
  SLOW ❌                            FAST ✓

With 1 Index:                      With 1 Index:
  ~27 lookups                        Insert 1 row → 1 table write
  FAST ✓                             + 1 index update
                                     MEDIUM

With 5 Indexes:                    With 5 Indexes:
  ~27 lookups                        Insert 1 row → 1 table write
  FAST ✓                             + 5 index updates
                                     SLOW ❌
```

Same read speed with 1 or 5 indexes. But write cost scales with index count. That's the curve. Understand it.

---

## Real-World Examples (2-3)

**1. E-commerce product search:** Index on name, category_id, price. Searches fly. But adding a new product? Three index updates. Bulk import of 10,000 products? 30,000 index operations. Bulk loads often DROP indexes first, load data, REBUILD indexes. Faster than updating incrementally.

**2. Analytics dashboard:** Read-heavy. Hundreds of queries per second. Few writes. Index everything you query. Five indexes? Ten? Fine. Writes are rare. Favor reads. Obvious choice.

**3. Audit log:** Write-heavy. Every action gets logged. Millions of inserts per day. Reads? Rare. Maybe "show last 100 entries." Index on timestamp for that. Nothing else. Too many indexes would kill insert speed. The log would fall behind. Choose writes.

---

## Let's Think Together

A table has 100 million rows, 10 columns, and 8 indexes. A bulk import runs — 1 million new rows. Why is it slow? Pause. Think.

Every row inserted triggers 8 index updates. 1 million rows × 8 indexes = 8 million index operations. Each one: find position in B-tree, insert, maybe rebalance. That's the cost. The fix? Drop indexes before bulk load. Run the import. Rebuild indexes after. One big index build is often faster than a million small ones. Production databases do this. Nightly loads. Index maintenance windows. It's a known pattern.

---

## What Could Go Wrong? (Mini Disaster Story)

A developer thinks: "Indexes are fast. Let me add one on every column. Just in case." User table. 15 columns. 15 indexes. Reads? Lightning. But signups slow to a crawl. Every new user = 15 index updates. Registration takes 3 seconds. Users bounce. "Your site is slow!" Support tickets flood. The team profiles. Finds the database. "Why are inserts so slow?!" The indexes. They drop 10 of them. Keep email (login), user_id (primary key), maybe created_at. Inserts normalize. Lesson: index what you QUERY. Not everything. Each index is a cost. Pay it only where it pays back.

---

## Surprising Truth / Fun Fact

Amazon's DynamoDB lets you create secondary indexes. Global Secondary Index (GSI). It's essentially a COPY of your table, sorted differently. Your main table: keyed by user_id. Your GSI: keyed by created_at. Same data. Different view. You pay for storage and write capacity on EACH index. Every put to the main table triggers a put to every GSI. The trade-off isn't hidden. It's in the bill. Cloud databases make the cost visible. Learn it there. Apply it everywhere.

---

## Quick Recap (5 bullets)

- **Why index:** SELECT with WHERE goes from O(n) to O(log n). Reads get fast. Sometimes 1000x faster
- **Trade-off:** Every INSERT/UPDATE/DELETE must update ALL indexes. More indexes = slower writes
- **Types:** B-tree (range), Hash (exact), Composite (multi-column), Full-text (search)
- **Covering index:** Index contains all columns the query needs — no table lookup. Fast but large
- **Rule:** Index what you QUERY. Not every column. Each index has a cost. Pay where it matters

---

## One-Liner to Remember

> Indexes are a read-write trade. You're buying speed for reads. You're paying with speed for writes. Spend wisely.

---

## Next Video

We've covered networks. Databases. SQL. Indexes. The foundations are in place. What's next? Scaling. Caching. Replication. When one server isn't enough. When your data needs to survive disasters. The journey from "it works" to "it works for millions." Stay tuned.
