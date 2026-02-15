# What Is Backfill and When Do You Need It?

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You add a "loyalty points" feature. New users get points automatically. But what about the 5 million users who already exist? They have order history. No points.

You have to go back. Calculate. For everyone. That's backfill.

---

## The Story

Emma launches a loyalty program. Buy something, earn points. The code is ready. New orders? Points calculated. Done.

But the database has 5 million users. Years of order history. They have no points. The new logic runs for new data. Old data is empty. Emma needs to run a job. Go back in time. For every user, look at their past orders, calculate points, write them in. That's backfill. Retroactively populating data that didn't exist when the feature launched.

It sounds simple. It's not. Five million users. Maybe 50 million orders. You can't run it all at once. The database would melt. You need batches. Throttling. Progress tracking. Idempotency. Backfill is a discipline.

---

## Another Way to See It

A library gets a new catalog system. All NEW books get cataloged automatically. But the shelves are full of old books. No catalog entries. Someone has to go shelf by shelf. Scan each book. Enter it. That's backfill. Going backward to fix what the new system didn't see.

The frustration: you launch a feature. It works for new users. Old users see nothing. "Why doesn't my account have loyalty points?" Because you haven't backfilled yet. The backfill job runs. A few hours later. Everyone has points. Crisis averted. Plan for it.

---

## Connecting to Software

**Backfill** = filling in data for existing records after a schema or feature change.

**Common scenarios:**
- New column added. Backfill with default or computed values.
- New derived field. Calculate from existing data (e.g., full_name from first_name + last_name).
- Data migration. Copy from old format to new.
- New search index. Re-index all documents in Elasticsearch.

**Challenges:** Millions of rows take time. You can't blast the database. One big `UPDATE` locks tables, kills performance, angers users.

**Best practices:**
- **Batch:** 1000 rows at a time. Maybe 10,000. Depends on row size and DB.
- **Throttle:** Sleep between batches. Let the database breathe.
- **Off-peak:** Run at 2 AM. Less traffic.
- **Track progress:** "Processed 2.3M of 20M." Resume from checkpoint if it fails.
- **Idempotent:** Running twice shouldn't create duplicates or wrong data.

The surprise: backfill is everywhere. Every feature launch with existing data needs it. New column? Backfill. New search index? Backfill. Migrating to a new system? Backfill. It's not an edge case. It's standard operations. The aha: doing it wrong once teaches you forever. Batch. Always batch.

---

## Let's Walk Through the Diagram

```
    BACKFILL FLOW

    ┌─────────────────────────────────────────────────────┐
    │  SELECT * FROM users WHERE full_name IS NULL         │
    │  LIMIT 1000 ORDER BY id                              │
    └─────────────────────────────────────────────────────┘
                            │
                            ▼
    ┌─────────────────────────────────────────────────────┐
    │  For each row:                                       │
    │    full_name = first_name || ' ' || last_name        │
    │    UPDATE users SET full_name = ? WHERE id = ?       │
    └─────────────────────────────────────────────────────┘
                            │
                            ▼
    ┌─────────────────────────────────────────────────────┐
    │  sleep(100ms)  ← throttle                             │
    │  Track: processed 1000, remaining 19,999,000        │
    └─────────────────────────────────────────────────────┘
                            │
                            ▼
                    Repeat until done
```

Batch. Update. Sleep. Track. Repeat. If the job fails, you have a checkpoint. Resume from the last batch. Never start over. Idempotency means running it again produces the same result. Safe. Predictable.

---

## Real-World Examples (2-3)

**Example 1 — full_name backfill:** New column. 20M users. Batches of 1000. Run overnight. Takes 6 hours. Done. No user impact. No database strain. The next morning, every user has full_name populated.

**Example 2 — Search re-index:** New Elasticsearch mapping. All products need re-indexing. Stream from DB, batch of 500, index. Millions of products. Runs for days. Non-blocking.

**Example 3 — Stripe:** Backfilled billions of payment records for a new reporting feature. Weeks of careful batches. Could not impact live payments.

The discipline: backfill is not a one-off script. It's a production job. Monitor it. Alert if it stalls. Have a rollback plan. Document the process. The next feature will need it too.

---

## Let's Think Together

You add a `full_name` column combining `first_name` and `last_name`. 20 million users need backfill. How do you do it without killing the database?

Pause and think.

Batch of 1000–5000. `SELECT id, first_name, last_name WHERE full_name IS NULL LIMIT 5000`. Compute full_name. Batch UPDATE. Sleep 50–200ms. Log progress. Run during low traffic. Use a cursor or max(id) to resume.

Consider doing it in read replicas and then syncing, or use a queue (worker picks batches). Never `UPDATE users SET full_name = first_name || ' ' || last_name` in one shot on 20M rows. The progress bar matters. "2.3M of 20M done" gives you confidence. If it fails at 15M, you restart from 15M. Idempotent.

---

## What Could Go Wrong? (Mini Disaster Story)

A developer ran a backfill. All 20 million rows. One query. `UPDATE users SET full_name = ... WHERE full_name IS NULL`. No batching. No throttle. The database CPU hit 100%. Replicas lagged. Live queries timed out. Users saw errors for 45 minutes. The backfill eventually finished. The incident report was long. Post-mortem: "We should have batched." Obvious in hindsight. Batch. Always batch. Write it in the runbook. New engineers read it. Avoid the mistake. The relief: they fixed the backfill script. Re-ran it properly. Took 8 hours. No user impact.

---

## Surprising Truth / Fun Fact

Stripe once backfilled billions of payment records to support a new reporting feature. It took weeks. Careful batches. They could not afford to slow down live payments. Backfill at scale is an engineering art.

---

## Quick Recap (5 bullets)

- **Backfill** = retroactively populating data for existing records after a change.
- **When:** New column, derived field, data migration, new search index.
- **How:** Batch (1000s), throttle (sleep), off-peak, track progress, idempotent.
- **Why batch:** One massive UPDATE locks the table, kills performance.
- **Resume:** Track last processed ID. Restart from there if job fails.

---

## One-Liner to Remember

New feature for new data. Backfill for old data. Batch it. Never blast. Batch it. Throttle it. Track it. Run it during off-peak. Make it idempotent. Backfill is operations 101. Master it.

---

## Next Video

Your data is huge. Storage is expensive. What if you could shrink it without losing anything? Data compression—next.
