# Write-Ahead Log (WAL): What and Why

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You're an accountant. Big ledger book. Before you change anything—add a row, update a balance—you write in a journal first. "About to add 500 rupees to account number 123." Then you make the change in the ledger.

Why? If you collapse mid-work, someone finds your journal. They know exactly what you were about to do. They can finish it. Or undo it. The journal is your safety net. That journal? It's the Write-Ahead Log. Every serious database uses one.

---

## The Story

The ledger is your database. The data files. Tables, indexes, all of it. You're about to update a row. Add a new index entry. Change a B-tree node. Lots of disk writes. Scattered. Random locations.

Then the power goes out. Or the process crashes. Mid-write. The data file has a half-updated row. A broken index. Corrupted. Inconsistent. How do you recover?

The journal saves you. Before touching the ledger, you write to the journal: "I will add this row. I will update this index." The journal is append-only. Sequential. One write after another. Fast. Durable.

If you crash, the recovery process reads the journal. It sees what was intended. It replays: finish the changes that were in progress. Or roll back. The journal has the truth. The data files might be messy, but the log tells you how to fix them.

---

## Another Way to See It

Think of a to-do list. Before you start a task, you write it down. "Paint the fence." "Fix the leak." If you get interrupted, you look at your list. You know what was done. What wasn't. What was half-done. The list is your write-ahead log. Intent before action.

---

## Connecting to Software

**The problem:** Database writes to multiple places. Data files. Index files. Different disk locations. Random writes. If the server crashes mid-operation, some writes complete, others don't. Data corruption. Broken indexes. Unrecoverable.

**WAL solution:** Before changing any data file, write the change to a sequential log file. The log is append-only. One write at a time. Fast—sequential writes are 10–100x faster than random writes on disk. Durability first. Then apply changes to data files. If crash: replay the log. Recover.

**Why sequential?** Disks are optimized for sequential I/O. Random writes = seek + write. Sequential = just write. Append-only = always sequential. Maximum throughput.

**Who uses it?** PostgreSQL, MySQL, SQLite, MongoDB, Kafka. WAL is foundational. No serious database runs without it. Kafka's log IS the storage—every message is append-only. Same principle: write to log first, then "apply" (in Kafka's case, the log is the truth; consumers read from it). WAL thinking everywhere.

**fsync and durability:** Writing to WAL isn't enough—you must fsync. Otherwise the OS buffers the write; a crash loses it. Durability = written + synced to disk. WAL + fsync = crash-safe. The performance trade-off: fsync is slow. Some systems offer "synchronous" vs "asynchronous" commit. Sync = durable but slower. Async = faster but risk of small data loss on crash.

---

## Let's Walk Through the Diagram

```
Application: "INSERT row X"
        |
        v
+-------------------+
| 1. Write to WAL   |  <- FIRST. Always first.
|    "Insert X"     |     Append. Sequential. Fast.
+-------------------+
        |
        v
+-------------------+
| 2. Apply to       |  <- THEN update data files
|    data files     |     Data + indexes
+-------------------+

CRASH before step 2?
  -> WAL has "Insert X"
  -> Replay on restart
  -> Data recovered

WAL = Append-only = Sequential = Fast
```

---

## Real-World Examples (2-3)

**PostgreSQL:** WAL is central. Every change goes to WAL first. Checkpoints periodically flush dirty pages. WAL segments can be archived for point-in-time recovery. Replication streams WAL to replicas.

**SQLite:** Rollback journal or WAL mode. In WAL mode, reads can happen concurrently with writes. The log is the source of truth. Simple. Effective.

**MongoDB:** Journal before data files. Same idea. Crash recovery reads the journal and reapplies. WiredTiger (MongoDB's storage engine) uses a similar pattern. Write to journal, then to data files. Recoverable.

**Kafka:** The entire system is WAL. Topics are log segments. Producers append. Consumers read. No "data files" separate from the log. The log IS the database. WAL philosophy at its purest. Everything is append. Everything is sequential. Maximum throughput.

---

## Let's Think Together

**Question:** The WAL grows forever. How does the database prevent it from filling the disk? Hint: checkpoints.

**Answer:** Checkpoints. Periodically, the database flushes all dirty data pages to disk. Once data is durable, the WAL entries for those changes are no longer needed for recovery. The database can truncate or recycle WAL segments. Old WAL is deleted. New WAL keeps appending. The disk doesn't fill. Checkpoints are the "we've saved enough, we can forget the old log" moment.

---

## What Could Go Wrong? (Mini Disaster Story)

A database under heavy write load. WAL grows fast. Checkpoints lag. Disk fills. The database tries to write more WAL. No space. It panics. Crashes. Or worse: it blocks all writes. "Disk full." Production down. Alerts screaming.

The fix: add disk. Or tune checkpoint frequency. Or reduce write load. But prevention is better—monitor WAL size. Alert before it's critical. In PostgreSQL, check `pg_ls_waldir()` or `pg_stat_archiver` for WAL segment usage. Set `wal_size` or `checkpoint_timeout` appropriately. A full disk during checkpoint is a nightmare—plan headroom.

---

## Surprising Truth / Fun Fact

WAL isn't just for recovery. PostgreSQL uses it for replication. The primary writes to WAL. Replicas stream the WAL and apply the same changes. Same log, multiple consumers. WAL is the backbone of consistency in distributed databases too. Change Data Capture (CDC) tools—Debezium, etc.—also read from WAL. Stream database changes to Kafka, data warehouses, search indexes. One write, many downstream systems. WAL is the source of truth. Everything else follows. Understanding WAL is understanding how databases achieve durability and replication. It's foundational.

---

## Quick Recap (5 bullets)

- **WAL** = write the change to a log file BEFORE modifying data files
- **Why first?** = if crash, replay the log to recover; log has the truth
- **Why sequential?** = append-only = fast; random writes are slow
- **Checkpoints** = flush data to disk, then truncate old WAL; prevents infinite growth
- **Universal** = PostgreSQL, MySQL, SQLite, MongoDB—all use WAL

---

## One-Liner to Remember

**Write-Ahead Log: write the intention first, then do the work—so when the server crashes, you can replay and recover.**

---

## Next Video

Up next: MVCC. How databases let readers and writers work at the same time without blocking each other. The Google Doc trick.
