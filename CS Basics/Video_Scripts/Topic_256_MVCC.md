# MVCC: Multi-Version Concurrency Control

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A shared Google Doc. You're reading it. Someone else is editing. You see a clean, consistent snapshot—version 5. No half-edited sentences. No flickering text. The editor sees their in-progress version 6. Both of you work at the same time. No blocking. No waiting.

That's MVCC. Multi-Version Concurrency Control. Multiple versions of data coexist. Readers don't block writers. Writers don't block readers. It's how databases stay fast under load. Here's how it works.

---

## The Story

Without MVCC, it's chaos. Or slow. Option one: reader locks a row. Writer wants to update it. Writer waits. Option two: writer locks the row. Reader wants to read it. Reader waits. Either way—someone waits. Contention. Queues. Slow systems.

MVCC changes the game. Each write creates a new version. The old version stays. Readers see the latest committed version at the time they started. Writers create new versions. No locking between readers and writers. Both proceed. Parallel. Fast.

Think of it like this. You open a document at 10:00 AM. You read for 5 minutes. At 10:02, someone else saves a new version. You don't see it. You still see the 10:00 version. Your snapshot is frozen in time. Consistent. When you're done, you close. The next reader gets the latest. Clean.

---

## Another Way to See It

A photo album. Every time someone "updates" a photo, we add a new copy. We don't erase the old one. You're looking at the album from last week—you see last week's photos. Your sister is looking at today's—she sees today's. Same album. Different snapshots. Nobody blocks nobody.

---

## Connecting to Software

**The problem:** Locks create contention. Reader locks block writers. Writer locks block readers. Throughput suffers.

**MVCC solution:** Each row has a version identifier. Often a transaction ID or timestamp. When a transaction starts, it gets a "snapshot" time. It sees only rows with version <= that time. Rows with newer versions are invisible. Writers create new versions. Old versions remain until garbage collected.

**Implementation:** PostgreSQL adds xmin and xmax to every row. Which transaction created it. Which (if any) deleted it. A reader checks: is this row visible to my transaction? Version numbers tell the story.

**Garbage collection:** Old versions can't live forever. Eventually, no transaction needs them. PostgreSQL runs VACUUM. It reclaims space. Deletes obsolete versions. Without it, tables bloat. Vacuum is maintenance. Essential. Autovacuum runs by default—but busy tables might need tuning. Long-running transactions block vacuum from reclaiming space they might still "see."

**Isolation levels:** Read Uncommitted, Read Committed, Repeatable Read, Serializable. MVCC enables Read Committed and Repeatable Read without reader locks. Serializable adds conflict detection—if two transactions would create a serialization anomaly, one aborts. MVCC gives you the snapshot; serializable adds the safety for complex interleavings.

---

## Let's Walk Through the Diagram

```
Time 100: Transaction A starts (sees snapshot at 100)
Time 102: Transaction B updates row X -> creates version 2
Time 103: Transaction A reads row X
          -> Sees version 1 (version 2 has timestamp 102 > 100)
          -> A's snapshot is frozen at 100
Time 105: Transaction B commits
Time 106: Transaction A reads again -> still sees version 1
Time 108: Transaction A commits
Time 109: New reader sees version 2 (latest committed)

    [Version 1]     [Version 2]
    created t=50    created t=102
         |               |
    A sees this    B sees this
    (snapshot 100) (writing)
```

---

## Real-World Examples (2-3)

**PostgreSQL:** MVCC is core. Default isolation level (Read Committed) uses it. No reader locks. Writers don't block readers. Long-running reports don't block updates.

**MySQL (InnoDB):** Uses MVCC for consistent reads. Undo logs store old versions. Same idea.

**Oracle:** Pioneered MVCC-like behavior decades ago. Multi-version read consistency. Industry standard. Undo segments store old row versions. Same idea: readers see a snapshot, writers create new versions. Battle-tested at the largest scales.

**MySQL InnoDB:** Undo logs. Each row has a rollback pointer. Old versions in undo. Consistent read uses them. Isolation without locking. The implementation varies—PostgreSQL keeps multiple versions in the main table; InnoDB uses separate undo segments—but the result is the same: non-blocking reads and writes.

---

## Let's Think Together

**Question:** Transaction A starts at time 100. Transaction B commits a new row at time 105. Does A see B's row? Why not?

**Answer:** No. A's snapshot is at time 100. B's row was created at 105. A only sees rows with creation time <= 100. B's row is "in the future" for A. Invisible. That's snapshot isolation. A sees a consistent view of the database as it was at 100. Nothing more, nothing less. When A commits, the next transaction will see B's row—it's committed.

---

## What Could Go Wrong? (Mini Disaster Story)

A long-running analytics query. Reads for an hour. Uses snapshot from 10:00. Meanwhile, deletes and updates happen. Old row versions pile up. The table bloats. 10 GB becomes 50 GB. Queries slow. Vacuum runs—but it can't reclaim space that the long query still "sees." Eventually the query finishes. Vacuum catches up. But the bloat was real. The lesson: long transactions hold back vacuum. Keep transactions short. Set statement timeouts. Kill runaway queries. Monitor long-running transactions—they're a common source of bloat and replication lag. A 2-hour "SELECT *" from an analytics tool can hold back vacuum for the entire table. Nip it in the bud.

---

## Surprising Truth / Fun Fact

MVCC enables one of the coolest features: time travel. Want to see the database as it was yesterday? Restore from a backup? No. With MVCC and WAL archiving, you can do point-in-time recovery. Replay to any second. "Show me the data at 3:42 PM." Some systems expose this. Audit. Debug. Magic. Oracle Flashback, SQL Server temporal tables, PostgreSQL with careful WAL retention—all leverage the same idea: versions exist. Query them. The past is queryable. Powerful for compliance and forensics. MVCC isn't just performance—it unlocks capabilities that locking never could.

---

## Quick Recap (5 bullets)

- **MVCC** = multiple versions of data; readers see snapshot, writers create new versions
- **No blocking** = readers don't block writers; writers don't block readers
- **Snapshot** = each transaction sees data as of its start time; consistent view
- **Garbage collection** = VACUUM (or similar) removes old versions when safe
- **Trade-off** = storage for versions; long transactions prevent cleanup

---

## One-Liner to Remember

**MVCC: every write creates a new version; readers see a frozen snapshot—so nobody waits for nobody.**

---

## Next Video

Up next: Database connection pooling. Why 1000 connections will crash your database—and how 20 can serve 500.
