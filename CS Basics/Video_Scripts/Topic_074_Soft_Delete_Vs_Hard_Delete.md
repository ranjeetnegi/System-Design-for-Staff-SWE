# Soft Delete vs Hard Delete

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You make a mistake in your notebook. Rip out the page—gone forever. Or draw a line through it. The text is still there. You can read it if you need to. Later, you can erase it for real.

In software, that choice changes everything. Recovery. Compliance. Disaster. Let's see why.

---

## The Story

Lucas is writing notes. He writes something wrong. Two options.

**Hard delete:** Tear out the page. Crumple it. Throw it away. Gone. Can't get it back. No undo. That's `DELETE FROM users WHERE id = 123`. The row vanishes from the database. Forever.

**Soft delete:** Draw a line through the mistake. The text is still visible. Mark it "deleted." You can still read it if you need to. Later, you might erase it. That's `UPDATE users SET deleted_at = NOW() WHERE id = 123`. The row stays. It's just marked.

Most apps show users a "deleted" state. Behind the scenes, the data might still exist. Soft delete gives you a safety net. Undo. Audit trail. Recovery. But it's not always the right choice.

The cliffhanger: soft delete sounds perfect until your database is 80% "deleted" rows and queries crawl. You need a plan. A lifecycle. Soft delete is the beginning, not the end.

---

## Another Way to See It

Think of a Trash folder on your computer. You "delete" a file—it moves to Trash. Still there. You can restore it. That's soft delete. When you "Empty Trash," that's hard delete. Gone for real.

Gmail does this. "Delete" moves to Trash. Thirty days later, it's really deleted. You've been using soft delete every day.

---

## Connecting to Software

**Soft delete implementation:** Add a `deleted_at` or `is_deleted` column. When a user "deletes," you run `UPDATE ... SET deleted_at = NOW()`. Every normal query adds `WHERE deleted_at IS NULL`. Deleted rows are invisible to the app but still in the database.

**Hard delete:** `DELETE FROM table WHERE id = X`. Row is gone. Unrecoverable unless you have backups—and restoring from backup is painful.

**Why soft delete?** Undo. User changes mind. Accident. Audit trail—who deleted what, when? Legal compliance—some laws require keeping records. Analytics on "deleted" data—why did users leave? Recovery after bugs.

**Why hard delete?** GDPR right to erasure—users can demand their data be GONE. Storage savings—millions of "deleted" rows waste space. Simpler queries—no need to filter deleted_at everywhere. No phantom data confusing reports.

**The lifecycle:** Soft delete first. Grace period (30 days, 90 days). Then a scheduled job does hard delete. Like Trash. Best of both.

The ironic twist: GDPR gives users the right to erasure—"delete my data for real." Soft delete alone doesn't satisfy that. You need a path to hard delete. But GDPR also allows keeping data for legal obligations. So often the answer is: soft delete for most things, hard delete after retention period, with special handling for erasure requests.

---

## Let's Walk Through the Diagram

```
    USER CLICKS "DELETE"
            │
            ▼
    ┌───────────────────┐
    │  Soft Delete?      │
    └───────────────────┘
        │           │
       YES         NO
        │           │
        ▼           ▼
  UPDATE users    DELETE FROM users
  SET deleted_at  WHERE id = X
  = NOW()         
        │           │
        ▼           ▼
  Row stays,     Row GONE
  marked.        Forever.
        │
        ▼
  Grace period
  (30 days)
        │
        ▼
  Scheduled job:
  Hard delete
  old soft-deleted
  rows
```

Soft delete = mark first. Hard delete later (or immediately if you choose).

---

## Real-World Examples (2-3)

**Example 1 — Gmail:** Delete moves to Trash. Trash auto-empties after 30 days. Soft delete with time-based hard delete.

**Example 2 — Slack:** Delete a message. It shows "message deleted." The content might still exist for admins or compliance. Soft delete. Retention policies determine when it's really gone.

**Example 3 — E-commerce:** Customer "cancels" order. Order status = CANCELLED. Row stays. Finance needs it. Refunds. Reports. Soft delete. After 7 years, maybe you archive or hard delete for compliance.

The relief: a user accidentally deletes an important document. "Can I get it back?" With soft delete: yes. Restore from the marked row. With hard delete: only from backup, if you have one. Soft delete is insurance.

---

## Let's Think Together

User deletes their account. GDPR says you must erase their data. But your finance team needs old invoices for auditing. Soft or hard delete?

Pause and think.

Tricky. GDPR allows keeping data for legal obligations—tax, invoices. So: soft delete the account (user can't log in). Anonymize or segregate personal data where possible. Keep invoices in a form that satisfies finance but minimizes PII.

Full hard delete might conflict with legal retention. Consult legal. The answer is often "it depends on jurisdiction and use case." Many companies: soft delete immediately, hard delete after 30 days for most PII, but retain financial records for 7 years in anonymized form.

---

## What Could Go Wrong? (Mini Disaster Story)

A company soft-deleted everything. Users, orders, posts. "We want undo!" Years later, the users table had 50 million rows. Only 5 million were "active." Forty-five million had `deleted_at` set. Every query scanned them. Indexes bloated. "SELECT * FROM users WHERE deleted_at IS NULL"—still had to touch the index. Backup size tripled. They needed a cleanup strategy: archive old soft-deleted rows, or hard delete after 2 years. Soft delete is powerful. But plan the cleanup. Add a cron job on day one. "Hard delete rows where deleted_at is older than 2 years." Never let it accumulate. The relief when they finally ran the purge: database size dropped 40%. Queries sped up. Lesson learned.

---

## Surprising Truth / Fun Fact

Gmail uses soft delete. "Deleted" emails go to Trash for 30 days. After 30 days, hard deleted. You've been using soft delete every single day without thinking about it.

---

## Quick Recap (5 bullets)

- **Soft delete:** Add deleted_at, mark row. Queries filter it out. Data stays.
- **Hard delete:** DELETE row. Gone. Unrecoverable.
- **Why soft:** Undo, audit, compliance, analytics, recovery.
- **Why hard:** GDPR erasure, storage, simpler queries.
- **Lifecycle:** Soft delete → grace period → hard delete. Like Trash.

---

## One-Liner to Remember

Soft delete = line through the page. Hard delete = rip it out. One lets you undo. One doesn't. Most apps need both. Soft delete for the grace period. Hard delete for the finale. Plan the lifecycle.

---

## Next Video

How long do you keep data? Hot, warm, cold storage. Retention policies. Archival. Next: Data retention and archival.
