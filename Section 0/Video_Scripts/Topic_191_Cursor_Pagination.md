# Cursor-Based Pagination vs Offset

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A long train. You want to see all carriages. Method 1, offset: "Show me carriages 101 to 110." The conductor counts from carriage 1 to 100, then shows 101 to 110. Slow for high offsets. Method 2, cursor: "Show me the 10 carriages AFTER this specific one—carriage-100-token." The conductor goes directly to carriage 100, shows the next 10. No counting from the beginning. Fast at any depth. That's cursor-based pagination.

---

## The Story

Offset pagination: "Give me page 10." Or "skip 90, take 10." Database does: `SELECT * FROM items ORDER BY id LIMIT 10 OFFSET 90`. Sounds fine. But OFFSET 90 means: scan 90 rows, throw them away, return 10. OFFSET 9,000,000 means: scan 9 million rows, discard, return 10. Absurd. The deeper you go, the slower it gets. Linear degradation. At scale, unacceptably slow.

Cursor-based pagination: "Give me 10 items AFTER this cursor." Cursor = a pointer to a specific row. Often the ID or (timestamp, id) of the last item you received. Query: `SELECT * FROM items WHERE id > last_seen_id ORDER BY id LIMIT 10`. Database uses the index. Jumps directly to that position. Returns next 10. Constant time. Whether you're at "page" 1 or "page" 100,000, same speed. O(1) instead of O(offset).

Trade-off: cursor pagination doesn't have "page numbers." You can't jump to "page 50" directly. You can only go "next" from where you are. For feeds, activity logs, infinite scroll—that's fine. For "go to page 50 of search results"—offset or a different approach (e.g., search engine cursor) might be needed.

---

## Another Way to See It

Think of a book. Offset: "Go to page 500." You count pages from 1. Turn, turn, turn. Slow. Cursor: "Continue from where you left off—page 234, line 5." You open directly to that spot. Flip a few pages. Fast. The bookmark (cursor) lets you resume. No counting.

Or a queue at DMV. Offset: "I want person 5,000." Guard counts from the front. Nightmare. Cursor: "I'm serving the person after this one." Guard hands you the next. Efficient.

---

## Connecting to Software

In practice: API returns `{ items: [...], next_cursor: "eyJpZCI6MTAwfQ==" }`. Client stores next_cursor. Next request: `GET /items?cursor=eyJpZCI6MTAwfQ==&limit=10`. Server decodes cursor (e.g., base64 of last ID), queries `WHERE id > decoded_id`, returns next 10, new cursor. Cursor is opaque to client—don't expose internals. Encode last_seen_id, maybe with a checksum to prevent tampering.

For ordered lists: cursor must encode the sort key. Sort by `created_at, id`? Cursor = (last_created_at, last_id). Query: `WHERE (created_at, id) > (?, ?)`. Preserves order. Handles ties (same created_at).

**Opaque cursors:** Don't expose raw IDs to clients. Encode them. Base64 of (id, checksum). Prevents tampering. Client can't invent "cursor = 999999" to skip ahead. Server decodes, validates, queries. Opaque = better security and flexibility. You can change internal format without breaking clients.

**Composite sort:** Sorting by multiple columns? Cursor encodes all. "created_at DESC, id DESC" → cursor has (last_created_at, last_id). Query uses tuple comparison. Correct order. Handles ties. Essential for "newest first" feeds with consistent pagination. Design the cursor to match your sort.

---

## Let's Walk Through the Diagram

```
    OFFSET PAGINATION                    CURSOR PAGINATION

    Request: page 10 (OFFSET 90)         Request: cursor=id_100, limit=10

    DB: Scan 1...90 (discard)            DB: Index seek to id > 100
         │                                    │
         │    Return 91-100                   │    Return 101-110
         ▼                                    ▼

    Page 100 (OFFSET 990)?               cursor=id_110, limit=10?
    DB: Scan 1...990 (discard) 💀        DB: Index seek to id > 110 ✓
    SLOW. Gets worse.                    Constant time. Fast.
```

---

## Real-World Examples (2-3)

**Example 1: Twitter timeline.** "Load more" uses cursor. Not "page 50." Cursor = ID of the last tweet you saw. "Give me 20 tweets after this ID." Fast. Infinite scroll. No offset explosion.

**Example 2: Stripe API.** List charges, customers, etc. Uses `starting_after` (cursor). "Give me charges after charge_xyz." Pagination that works at scale. They document it. Offset would break for accounts with millions of records.

**Example 3: Slack.** Message history. Cursor-based. "Messages before this timestamp." Scroll up in a channel. Millions of messages. Cursor = last message ID or timestamp. No OFFSET 500000. Works.

---

## Let's Think Together

**What if the list changes while you're paginating? Items inserted or deleted?**

Offset: items can shift. You might skip or duplicate. Page 2 might have different items than when you started. Cursor: more stable. "After ID 100" is a point in the list. New items before that cursor don't affect "next page." Items after—you'll get them. Deletion: cursor might point to deleted item. Handle: if cursor not found, fall back to "start from beginning" or return error. Edge case. Offset has worse: whole pages shift.

**Can you have "previous page" with cursor?**

Yes. Store "previous_cursor" too. Or: for "back," use the first item of current page as cursor and query "items BEFORE this." Reverse the sort. `WHERE id < first_id ORDER BY id DESC LIMIT 10`. Same idea. Cursor works both directions.

---

## What Could Go Wrong? (Mini Disaster Story)

An e-commerce site uses offset pagination for product search. "Page 50 of 10,000 results." OFFSET 490. Database: scan 490 rows, return 10. Works. They grow. "Page 5,000." OFFSET 49990. Database dies. Timeout. They switch to cursor. "After product ID X." Index seek. Fast. Lesson: offset doesn't scale. Cursor does. Design for scale from the start for large lists.

---

## Surprising Truth / Fun Fact

Relational databases have had OFFSET for decades. It's intuitive. "Page 5." But it's a scalability trap. No amount of indexing fixes OFFSET at large values. The database must physically skip those rows. Cursor is the antidote. Twitter, Facebook, Stripe—all use cursor-style pagination for feeds and lists. It's the industry default for high-scale APIs.

---

## Quick Recap (5 bullets)

- **Offset pagination** = skip N, take M. Simple but slow at depth—DB must scan and discard rows. O(offset).
- **Cursor pagination** = "give me M items AFTER this cursor." Cursor = pointer (e.g., last ID). Index seek. O(1).
- Cursor doesn't support "jump to page 50." Only "next" from current position. Fine for feeds, infinite scroll.
- Cursor encodes sort key. For `ORDER BY created_at, id`, cursor = (last_created_at, last_id). Preserves order.
- Use cursor for large, ordered lists. Use offset only for small datasets or when random access is required.

---

## One-Liner to Remember

Offset = count from the beginning every time. Cursor = jump directly to "after this one." Fast at any depth.

---

## Next Video

Next up: **Why Offset Pagination Breaks at Scale**—the phone book with 10 million entries. "Show me the last 10." The database cries.
