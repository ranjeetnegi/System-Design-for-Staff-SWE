# Schema Migration: Adding a Column Safely

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A restaurant prints 500 paper menus. They're everywhere. Now you want to add "calorie count" to every dish. You can't recall all 500 menus. You can't force everyone to use the new menu tonight. Old and new must work at the same time.

That's schema migration. Changing the database without breaking the app.

---

## The Story

The chef wants calorie counts on the menu. Simple change. But the menus are printed. Distributed. In customers' hands. In the waiters' pads. You can't stop the restaurant, reprint everything, and reopen.

You need a smooth transition. Week one: print new menus with calorie counts. Some tables still have old menus. Some have new. Both work. Week two: everyone has the new menu. Week three: you stop printing the old version. Expand first. Migrate. Then contract.

Database schema migrations are the same. Your app runs 24/7. Hundreds of servers. You can't stop the world, run `ALTER TABLE`, and hope nothing breaks. You need a strategy. Add the new. Migrate. Remove the old. The expand-and-contract pattern.

The surprise: the "simple" change—adding a column—can take days when you do it right. Multiple deploys. Coordination. Backfill. But that's the professional way. No downtime. No data loss. No broken users.

---

## Another Way to See It

Adding a lane to a highway. You can't close the highway. You build the new lane alongside. Traffic uses both. When the new lane is ready, you shift traffic. Then you remove the old lane. Same idea: expand, migrate, contract.

The relief: once you've done it correctly, the pattern repeats. Add column, backfill, switch. Rename column, add new, migrate, drop old. Every migration follows the same rhythm. Master it once.

---

## Connecting to Software

**Schema migration** = changing database structure. Add column. Remove column. Change type. Rename. It sounds simple. It's dangerous. Production is live. One wrong `ALTER TABLE` and you lock the entire table. Or break every application reading it.

**Safe approach for adding a column:**
1. Add column with `DEFAULT NULL` (or a safe default). No downtime. Existing rows get NULL.
2. Deploy new code that WRITES to the new column.
3. Backfill old rows (background job, batches).
4. Deploy code that READS from the new column.
5. Optional: add `NOT NULL` constraint after backfill is done.

**Unsafe moves:** Rename a column—old code breaks. Drop a column—old code breaks. Change column type—might truncate or fail. These need the expand-contract pattern: add NEW column, migrate data, switch reads/writes, drop OLD column.

The frustration: you just want to add a column. How hard can it be? On a small table, it's trivial. On 500 million rows, a naive ALTER TABLE can lock for hours. The surprise: tools like gh-ost and pt-osc exist because this problem is so common. Big companies do this weekly. The relief: there's a playbook. Follow it.

---

## Let's Walk Through the Diagram

```
    EXPAND                    MIGRATE                 CONTRACT
    -------                   -------                 --------

  Step 1: Add column       Step 2-4: Move data     Step 5: Remove old
  (nullable, no lock)      and switch code         (optional)

  ┌─────────────┐          ┌─────────────┐         ┌─────────────┐
  │ id │ name   │          │ id │ name   │         │ id │ name   │
  │ 1  │ Alice  │   →      │ 1  │ Alice  │   →     │ 1  │ Alice  │
  │ 2  │ Bob    │          │ 2  │ Bob    │         │ 2  │ Bob    │
  └─────────────┘          │    │ calories│         └─────────────┘
  Add: calories (NULL)     └─────────────┘         Drop: old column
                          Backfill, deploy
```

Never break backward compatibility in one deploy. Always have a transition period. Some migrations take weeks. That's normal. Rushing breaks production.

---

## Real-World Examples (2-3)

**Example 1 — Adding a column:** E-commerce adds `loyalty_points` to users. Add nullable column. Deploy code that calculates and writes. Backfill 10M users in batches. Deploy code that reads. Done.

**Example 2 — Renaming a column:** `email` → `email_address`. Add `email_address`. Deploy write to both. Backfill. Deploy read from `email_address`. Drop `email`. Multiple deploys. Zero downtime.

**Example 3 — GitHub gh-ost:** Creates a shadow copy of the table. Applies the migration to the copy. Swaps the tables. Zero locking. Zero downtime. For huge tables.

The pattern: never break the running app. Every deploy must work with the current schema AND the previous one. That's backward compatibility. It's the foundation of zero-downtime migrations.

---

## Let's Think Together

You need to rename `email` to `email_address`. Ten services read this column. How do you do it safely?

Pause and think.

Add `email_address` column. Deploy services to write to BOTH `email` and `email_address`. Backfill. Deploy services to read from `email_address` only. Drop `email`. Each step is backward compatible. No "big bang" deploy. Coordination across 10 services is the hard part—feature flags, staged rollout. Some teams use a feature flag: "read from email_address if present, else email." Gradual migration. Zero risk.

---

## What Could Go Wrong? (Mini Disaster Story)

A developer ran `ALTER TABLE users ADD COLUMN country VARCHAR(2)` on a table with 500 million rows. MySQL locked the entire table. For 30 minutes. No reads. No writes. No logins. No checkout. Production down.

The alert fire: pages started timing out. On-call got paged. "Database is locked." The fix: wait. Or kill the ALTER and hope the rollback doesn't make things worse. The right approach: add column with `ALGORITHM=INSTANT` (MySQL 8) or use a tool like pt-online-schema-change. Test on a copy. Never alter blindly in production.

---

## Surprising Truth / Fun Fact

GitHub uses a tool called gh-ost for zero-downtime schema migrations. It creates a shadow copy of the table, applies changes in the background, then atomically swaps. Tables with billions of rows. No locking.

---

## Quick Recap (5 bullets)

- **Schema migration** = changing DB structure without breaking the app.
- **Safe add column:** Add nullable → deploy write → backfill → deploy read → optionally NOT NULL.
- **Rename/drop:** Add new column → migrate → switch → drop old. Expand-contract.
- **Danger:** ALTER on huge table = table lock = downtime.
- **Tools:** gh-ost, pt-online-schema-change for zero-downtime on large tables.

---

## One-Liner to Remember

Expand first. Migrate. Then contract. Never break compatibility in one step. Expand. Migrate. Contract. It takes longer. But production stays up. Users stay happy. That's the goal.

---

## Next Video

You added a new column. What about the 5 million existing rows? Backfill—what it is and how to do it safely. Next.
