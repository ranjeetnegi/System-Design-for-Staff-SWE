# Denormalization: When and Why?

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A library catalog. Normalized. Book table: book_id, title, author_id. Author table: author_id, name, country. Clean. No duplication. To find "all books by Indian authors" you JOIN. Fine for 1,000 books. But 100 million? That JOIN crawls. Minutes. So you cheat. You COPY the author's name and country directly into the Book table. Now you don't need a JOIN. One table. One scan. Fast. But wait — you duplicated data. Author changes their name? Update it in TWO places. That's denormalization. Trading correctness for speed. When does it make sense? Let me show you.

---

## The Story

You have a library. Proper design. Books. Authors. Separate tables. Book references author by ID. Normalized. No duplicate data. Relationships via foreign keys. To get "book title + author name" you JOIN. Book JOIN Author. Clean. Correct.

Scale to 100 million books. The JOIN runs. And runs. Tables huge. Indexes help. But still. Seconds. Maybe minutes. Users wait. Timeout. The database groans. JOINs at scale are expensive. Really expensive.

So you denormalize. You add author_name and author_country columns to the Book table. Duplicate. Redundant. Now each book row has everything. Title. Author name. Country. No JOIN. Query: "books by Indian authors." Scan Book table. Filter author_country = 'India'. One table. One pass. Fast. The trade-off: author changes their name. You must update millions of book rows. Or you don't. Stale data. Inconsistency. That's the cost.

**When to denormalize:** Read-heavy. Queries always need joined data. Performance critical. Scale demands it. One read = one table. No JOINs. Fast.

**When NOT to:** Data changes frequently. Updates expensive. Consistency critical. Financial data. Medical records. Duplicate = risk. Normalize. Pay the JOIN cost. Correctness over speed.

---

## Another Way to See It

Resume vs LinkedIn. Resume: everything on one page. Name. Education. Experience. Skills. Denormalized. Fast to read. One document. LinkedIn: separate sections. Profile. Experience. Education. Skills. Linked. Normalized. Flexible. Add new section without changing others. But "full profile" = multiple fetches. Or one denormalized view. Different use cases. Resume for printing. LinkedIn for flexibility. Same idea.

---

## Connecting to Software

**Normalization:** No duplicate data. Tables linked by foreign keys. JOIN to combine. Clean. Correct. Slower at scale. Third normal form. Fifth normal form. Theory. Practice: JOINs cost.

**Denormalization:** Intentional duplication. Copy frequently needed data into the row. Avoid JOINs. Fast reads. One table. One query. Trade-off: duplicate data. Update anomaly. Author changes name → update N places. Or: eventual consistency. Async update. Accept temporary staleness.

**When to denormalize:**
- Read-heavy workload. Writes rare. Reads million per second.
- Query pattern always needs "X + Y". Store X and Y together.
- JOIN too slow. Scale. Partitioning. Cross-shard JOINs nearly impossible.
- Acceptable staleness. Profile photo. Author name. Not bank balance.

**When NOT:** Writes frequent. Consistency critical. Financial. Medical. Legal. Correctness first.

---

## Let's Walk Through the Diagram

```
NORMALIZED vs DENORMALIZED

NORMALIZED:
[Books]              [Authors]
id | title | author_id    id | name    | country
1  | XYZ   | 5        →   5  | Sharma  | India
JOIN required. Two tables. Correct. Slow at scale.

DENORMALIZED:
[Books]
id | title | author_name | author_country
1  | XYZ   | Sharma      | India
No JOIN. One table. Duplicate. Fast.

Trade: Storage + Consistency ↔ Speed
```

Normalized: separate. JOIN. Denormalized: together. Duplicate. Choose based on read pattern and consistency needs.

---

## Real-World Examples (2-3)

**1. Facebook news feed:** Heavily denormalized. Each feed item has: post content, author name, author avatar, like count, comment count. All in one. No JOIN for display. At their scale, JOINs are impossible. They trade storage. Accept eventual consistency. "Author changed photo? Backfill async." Millions of posts. Hours. Users might see old avatar. Acceptable. Speed wins.

**2. E-commerce product page:** Product. Category name. Brand name. Seller name. Often denormalized in product document. "Product page" = one fetch. No JOIN across product, category, brand, seller. Duplicate category name in millions of products. Category renamed? Batch update. Rare. Worth it.

**3. Twitter tweet display:** Tweet. Author name. Author handle. Author avatar. Denormalized in tweet. Display = one read. Author updates profile? Tweets keep old. Eventually consistent. Or: backfill. Trade-off made. Scale requires it.

---

## Let's Think Together

News feed. Each post shows author name and avatar. 1 billion posts. Normalized: JOIN user table every time. Denormalized: store author name and avatar URL in each post row. Which for 1 billion posts?

*Let that sink in.*

**Denormalized.** At 1 billion, JOINs are death. Every feed load = JOIN posts + users. Millions of JOINs per second. Impossible. Store author name and avatar in post. Display = read post. Done. Author changes? Async job. Update posts. Might take hours. Staleness. Acceptable for social. Not acceptable for "account balance." Context matters. Scale demands denormalization for feeds. Design for it. From the start.

---

## What Could Go Wrong? (Mini Disaster Story)

Author changes profile photo. Denormalized system. Photo URL stored in millions of posts. Update? Need to update every post by that author. 10 million posts. Batch job. Runs for hours. During that time: some posts show new photo. Some old. Inconsistent. User sees their own post with old photo. "I changed it! Why doesn't it update?!" Consistency nightmare. Fix: accept eventual consistency. Or: store author_id. One fetch for author. But then: two reads per post. Slower. Or: cache author. Complex. Denormalization. Simple reads. Complex updates. Know the cost.

---

## Surprising Truth / Fun Fact

Facebook's news feed is heavily denormalized. They trade storage and consistency for speed. At their scale — billions of posts, millions of feed loads per second — JOINs are practically impossible. They pre-compute. Denormalize. Store what's needed. Update async. The architecture isn't "clean." It's practical. Scale forces trade-offs. The best systems embrace them.

---

## Quick Recap (5 bullets)

- **Normalization:** No duplicate data. JOIN to combine. Clean. Slow at scale.
- **Denormalization:** Intentional duplication. Avoid JOINs. Fast reads. Update cost. Staleness risk.
- **When to denormalize:** Read-heavy, query needs combined data, scale, acceptable staleness.
- **When NOT:** Frequent updates, consistency critical, financial/medical data.
- Facebook, Twitter, e-commerce: all denormalize for feeds and product pages. Scale demands it.

---

## One-Liner to Remember

> Copy the author into the book. No JOIN. Fast. But author changes? Update everywhere. That's the trade-off.

---

## Next Video

One more pattern. Multiple customers. One system. Salesforce. Shopify. Slack. Each customer sees only their data. How do you isolate? Separate databases? Shared tables? The apartment building analogy. Multi-tenant data. Next.
