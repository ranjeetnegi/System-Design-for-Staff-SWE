# Why Offset Pagination Breaks at Scale

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A phone book with 10 million entries. You ask: "Show me entries 9,999,991 to 10,000,000." The last 10. The database has to SKIP 9,999,990 entries first. Even though it's only returning 10 entries, it processed nearly 10 million. Absurd. Offset forces the database to count from the beginning every time. At large offsets, it breaks.

---

## The Story

Offset pagination seems innocent. "Page 1": `LIMIT 10 OFFSET 0`. Fine. "Page 10": `OFFSET 90`. Still okay. "Page 100,000": `OFFSET 999,990`. Disaster. The database executes: fetch rows 1 through 999,990, discard them, return the next 10. It doesn't magically jump. It scans. Or, with optimizations, it might use an index to skip—but that's still work. The cost grows with offset. Linearly. O(n) where n = offset.

Why? SQL semantics. OFFSET says "ignore the first N rows." To do that, the database must identify those N rows. That means reading them. Or scanning an index. Either way, work scales with offset. There's no "go directly to row 999,991" in standard SQL with arbitrary ORDER BY. The index helps for ORDER BY indexed_column—but you still traverse. Large offset = large traverse.

Real impact: API with "page 5000" of search results. 50,000 users hit it. Database does 50,000 × (scan 49,990 rows) = billions of row operations. Database dies. Timeout. Cascading failure. Offset pagination is a scalability bomb.

---

## Another Way to See It

Think of a line at a theme park. "I want the 10th person from the front." Easy. Guard counts 10, hands you that group. "I want the 9,999,990th through 9,999,999th person." Guard must count nearly 10 million people. Or walk past them. Either way, impossible in practice. Offset is asking the guard to do that. The further back, the worse.

Or reading a 10,000-page book. "Read page 1." Fine. "Read page 9,999." You have to flip through 9,998 pages to get there. Or have a very good index (like a book index)—but even then, "page number" isn't how books work for random access. Offset is the "flip through" approach. Doesn't scale.

---

## Connecting to Software

The fix: cursor-based pagination. "Give me 10 items after ID 999,990." Query: `WHERE id > 999990 ORDER BY id LIMIT 10`. Index on id. Database seeks to id 999990, reads next 10. Constant time. O(1) regardless of "depth." No offset. No scanning.

If you must use offset (legacy API, specific UX need): limit the max offset. "We only support 1000 results. Use cursor for more." Or: cache early pages. Page 1–10 are hot. Page 5000 is rare. Cache the rare ones? Maybe. But cursor is the real solution. Don't rely on offset for large datasets.

**Keyset pagination:** Another name for cursor pagination. "Keyset" = the set of columns you use as the cursor (e.g., id, or created_at+id). Same idea. Industry term. Search for "keyset pagination" to find more resources. It's the scalable alternative to offset.

**Monitoring:** Add query time metrics for pagination. If "page 10" starts taking 2 seconds, you'll see it. Alert. Before users complain. Offset pagination degrades silently until it's critical. Instrument. Know when to migrate to cursor.

---

## Let's Walk Through the Diagram

```
    OFFSET 90 (Page 10)                  OFFSET 9,999,990 (Page 1,000,000)

    ┌─ 1 ─┐                               ┌─ 1 ─┐
    │  2  │                               │  2  │
    │ ... │  scan & discard               │ ... │  scan & discard
    │ 90  │                               │ 9,999,990 │
    └─────┘                               └──────────┘
         │                                        │
         ▼                                        ▼
    Return 91-100 ✓                         Return 9,999,991 - 10,000,000
    Reasonable                                  💀 Timeout. Database overloaded.
```

---

## Real-World Examples (2-3)

**Example 1: E-commerce product search.** "10,000 results for 'laptop'." User goes to page 500. Offset 4,990. Query time: 5 seconds. Database CPU spikes. Other queries slow down. They implement cursor. "After product X." Query: 10ms. Problem solved.

**Example 2: Analytics dashboard.** "Show transactions, page 200." OFFSET 1990. Table has 50 million rows. Query never returns. They add "export" with cursor-based streaming. Or limit: "browse first 1000, export rest." Offset confined to small range.

**Example 3: Social feed (old design).** "Page 100 of my timeline." Offset 990. Timeline is dynamically sorted. By the time you load page 100, items shifted. Duplicates. Skips. Mess. Cursor ("after this post") fixes order and performance. Industry moved to cursor for feeds.

---

## Let's Think Together

**Does adding an index fix offset pagination?**

Partially. With `ORDER BY indexed_column`, the database can use the index to avoid full table scan. But it still must "skip" offset rows along the index. For B-tree: traverse offset nodes. Cost is proportional to offset. Index helps versus full scan, but offset cost remains. Cursor (WHERE id > X) uses the index to jump directly. No skip. Better.

**When is offset acceptable?**

Small datasets. "Show 100 products. Page 2." Offset 10. Fine. Or when you cap: "max 1000 results. Use filters." Offset 0–990. Tolerable. For unbounded, user-driven "page N" on large data—offset will bite you. Design for cursor early.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup launches a job board. Millions of listings. "Browse jobs, page by page." Offset pagination. Works. They get featured on a popular site. Traffic spike. Users explore. "Page 500" requests flood in. OFFSET 4990. Database: 5-second queries. Connection pool exhausted. Site goes down. 4 hours to recover. They implement cursor the next week. "Load more" instead of "page 500." Never again. Lesson: offset is a time bomb. Traffic + depth = explosion.

---

## Surprising Truth / Fun Fact

MySQL's `OFFSET` is so notorious that there are "tricks" like `WHERE id > last_id LIMIT 10` (cursor) that people discover when offset fails. PostgreSQL has similar behavior. It's a fundamental limitation of the offset model—not a bug. The database is doing what you asked. The ask is wrong for scale. Cursor is the right ask.

---

## Quick Recap (5 bullets)

- **Offset pagination** forces the database to skip N rows before returning. Cost grows linearly with offset.
- At offset 1M, the DB effectively processes 1M rows to return 10. Unacceptable at scale.
- The fix: **cursor-based pagination**. "After this ID." Index seek. Constant time.
- Offset can be acceptable for small datasets or when max offset is capped (e.g., first 1000 results).
- For feeds, search results, large lists—use cursor. Offset will break under load and depth.

---

## One-Liner to Remember

Offset = "skip the first N." The database must touch those N rows. At scale, that touch kills you. Cursor = "start after this one." Jump. Don't skip.

---

## Next Video

Next up: **Event Sourcing**—when the history IS the source of truth. Not "balance: $50,000." But "deposited, withdrew, deposited." Replay to get balance. Like a bank ledger.
