# What is a Primary Key and an Index?

## Video Length: ~4-5 minutes | Level: Beginner

---

## The Hook (20-30 seconds)

A library. 10,000 books. No catalog. No numbering. You want "Harry Potter." Where do you start? Shelf 1. Check every book. One by one. 10,000 checks. Maybe you get lucky at 3,000. Maybe you finish at 10,000. That's a full table scan. Exhausting. Now imagine each book has a unique catalog number. And there's a card catalog — sorted alphabetically by title. You want Harry Potter? Flip to "H." Found: Shelf 7, position 42. You walk straight there. Two lookups. Not 10,000. That's the power of a primary key and an index. Same data. Different speed.

---

## The Story

Every table needs a way to identify each row. Uniquely. No two rows can be identical in that column. That's the **primary key**. Like your Aadhaar number. Or a passport number. One per person. The database uses it to say: "This row. Exactly this one. Not any other." When you create a table, you define it: `id INT PRIMARY KEY`. Every row gets a unique id. 1, 2, 3, 4. No duplicates. The database guarantees it.

But finding a row by id is one thing. What if you search by email? "Find the user with email priya@example.com." Without help, the database scans every row. 50 million rows? 50 million checks. That could take minutes. Enter the **index**.

An index is a separate structure. A sorted lookup table. It doesn't hold the full row. It holds the column you're searching — and a pointer to where the actual data lives. Like the index at the back of a textbook. "Photosynthesis: pages 47, 82, 156." You don't read the whole book. You check the index. Jump to the page. Same idea. The database maintains an index on the email column. Sorted. When you query `WHERE email = 'priya@example.com'`, it looks up the index. Finds the pointer. Jumps to the row. O(log n) instead of O(n). From millions of checks to dozens. That's the index.

**Primary key** = unique ID. Required. Usually auto-increment. **Index** = sorted lookup. Optional. But when you search by a column often, you add an index. Search becomes lightning fast.

---

## Another Way to See It

Phone book. Sorted alphabetically by name. That's an index. Want "Sharma"? Don't scan every page. Jump to "S." Then "Sh." Then "Sha." Found. The actual data — the phone numbers and addresses — lives elsewhere. The phone book is just the index. Pointing you to the right place. Database indexes work the same way. Sorted. Pointers. Fast lookup.

---

## Connecting to Software

When you create a table, you always have a primary key. `id SERIAL PRIMARY KEY` or `user_id UUID PRIMARY KEY`. The database uses it internally. For joins. For uniqueness. For speed. When you add `CREATE INDEX idx_users_email ON users(email)`, you're saying: "I'll search by email a lot. Make it fast." The database builds a B-tree — a sorted structure. Future queries on email? Instant. That's how production databases handle millions of rows. Keys and indexes. The secret sauce.

---

## Let's Walk Through the Diagram

```
WITHOUT INDEX: Full Table Scan
Query: WHERE email = 'priya@example.com'

[Row 1] [Row 2] [Row 3] ... [Row 50,000,000]
   |       |       |              |
   X       X       X    ...      ✓ FOUND
   
50 million checks. Slow.


WITH INDEX: Direct Lookup
Query: WHERE email = 'priya@example.com'

INDEX (email → row pointer)     ACTUAL TABLE
  anuj@x.com    → row 4521
  priya@x.com   → row 389402     [Row 389402] ✓
  ravi@x.com    → row 1029
  ...

~30 lookups (log of 50 million). Fast.
```

The index is a shortcut. A map. The database consults it first. Then goes straight to the target.

---

## Real-World Examples (2-3)

**1. Login:** User types email and password. Query: `SELECT * FROM users WHERE email = ?` Without index: scan 100 million rows. With index on email: 30 comparisons. Login in milliseconds. Index makes it possible.

**2. E-commerce search:** "Show products in category Electronics." Index on category_id. Database jumps to all Electronics products. No full scan. Fast category pages.

**3. Social feed:** "Show posts by user 12345." Index on user_id. Database finds all rows with that user_id. Instant. No index? Scan every post ever. Disaster.

---

## Let's Think Together

Your users table has 50 million rows. Users log in with email. Should you add an index on the email column? Pause. Think.

**Yes.** Absolutely. Login is one of the most frequent operations. Every login runs a WHERE email = ? query. Without an index, that's 50 million row checks. Per login. With an index, it's ~26 comparisons (log2 of 50 million). Milliseconds vs seconds. Or worse. Index the columns you search. Email for login? Index it. No hesitation.

---

## What Could Go Wrong? (Mini Disaster Story)

Here's the catch. Indexes speed up READS. But they slow down WRITES. Every time you INSERT a new user, the database must update the email index. Insert the new email in the right sorted position. Every UPDATE on an indexed column? Update the index. Every DELETE? Remove from the index. One table. Ten indexes. One INSERT. Ten index updates. Writes get expensive. Trade-off: read fast, write slow. Or write fast, read slow. You choose. More indexes isn't always better. Index what you QUERY. Not everything.

---

## Surprising Truth / Fun Fact

A B-tree index — used by MySQL, PostgreSQL, most databases — can search 1 billion rows in about 30 comparisons. Thirty. Log base 2 of 1 billion is roughly 30. That's the power of logarithms. Divide and conquer. The index cuts the search space in half. Again. And again. Thirty times. You're done. One billion rows. Thirty steps. Think about that.

---

## Quick Recap (5 bullets)

- **Primary Key** = unique ID for every row. No duplicates. Required. Like Aadhaar for data
- **Index** = sorted lookup structure. Speeds up WHERE, JOIN, ORDER BY on that column
- **Without index** = full table scan. O(n). **With index** = B-tree lookup. O(log n)
- You can have multiple indexes on one table — one per column you search
- **Trade-off:** indexes speed up reads but slow down writes (every INSERT/UPDATE must update indexes)

---

## One-Liner to Remember

> Primary key: who are you? Index: where do I find you? One identifies. The other finds.

---

## Next Video

So indexes make reads fast. But we said they slow down writes. How much? And why would you ever have TOO many indexes? The trade-offs get real. Read fast, write slow. Choose wrong, and your database crawls. When to index. When NOT to. That's next.
