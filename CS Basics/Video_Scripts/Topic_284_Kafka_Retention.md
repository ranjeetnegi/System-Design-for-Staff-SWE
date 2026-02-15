# Kafka Retention and Compaction: Time, Size, and Latest-Only

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A library with limited shelf space. Policy one: "Keep books for 7 days. After that, remove them." Old books disappear—doesn't matter if it's a rare first edition or a magazine. Policy two: "For each book TITLE, keep only the LATEST edition. Remove older editions." So you have one copy of "Harry Potter"—the newest one. Space-efficient. Latest info preserved. Kafka has both. Retention: delete old messages after time or size. Compaction: keep only the latest value per key. Let's see when to use which.

---

## The Story

Kafka stores messages on disk. Forever? No. Disk is finite. And sometimes you don't need everything. You need a policy for what to keep and what to drop.

**Time-based retention:** the default. "Keep messages for 7 days." After 7 days, Kafka deletes the oldest segments. Simple. Predictable. You know: "I can replay the last week." Good for event streams—signups, clicks, logs. Old data loses value. Delete it.

**Size-based retention:** "Keep only 50GB per partition." When the partition hits 50GB, Kafka deletes the oldest segments. Use when disk space is the constraint. Or when you want "last N gigabytes" of data.

**Log compaction:** different game entirely. "For each KEY, keep only the LATEST message. Delete older versions." So if key=user_123 has 50 messages over time (profile updated, settings changed, address modified, preferences tweaked), after compaction you have 1 message—the latest state. Used for changelog topics, state stores, CDC. "What's the current state of each user?" Compaction gives you that without replaying 50 messages.

**Combining both:** you can use BOTH retention and compaction together. `cleanup.policy=compact,delete`. Compaction keeps the latest per key. But if a key hasn't been updated in 30 days, retention deletes even the compacted version. Useful when you want "current state" but also don't want ancient keys hanging around forever. Dead users from 5 years ago? Eventually cleaned up.

**Segments matter:** Kafka stores data in segments (files). Retention and compaction work on SEGMENTS, not individual messages. Active segment (being written to) is never cleaned. Only closed segments get processed. This means there's always a delay between when a message "should" be deleted and when it actually is. Understanding segments helps you understand why disk usage doesn't drop immediately after changing retention.

---

## Another Way to See It

Think of a whiteboard. Retention is like erasing the left side when the board gets full—old stuff goes. Compaction is like having one row per topic: "User 123" → latest update, "User 456" → latest update. You overwrite. You keep only the current row. Retention = time/space limit. Compaction = key-based "latest only."

---

## Connecting to Software

**Time-based retention:** `retention.ms=604800000` (7 days). Segments older than 7 days get deleted. Simple. Standard for event streaming.

**Size-based retention:** `retention.bytes=53687091200` (50GB per partition). When total size exceeds, delete oldest. Use with care—high-throughput topics can hit this fast.

**Log compaction:** `cleanup.policy=compact`. Kafka runs a compaction process. For each key, it keeps the latest message (by offset). Older messages for that key are removed. Topics used as changelogs, materialized views, "current state" stores use this. Warning: compaction is not instantaneous. There's a lag. And deletes are special: you send a message with key=X and value=null. Compaction treats that as "tombstone"—remove key X. So you can delete.

---

## Let's Walk Through the Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    RETENTION vs COMPACTION                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   RETENTION (time/size):          COMPACTION (latest per key):           │
│   Delete old segments            Keep latest message per key            │
│                                                                          │
│   Before (7 days):                Before compaction:                     │
│   ┌─────────────────┐             key=A: v1, v2, v3, v4                  │
│   │ Day 1  Day 2  Day 3 ... Day 7│ key=B: v1, v2                         │
│   │  ██    ██    ██        ██   │ key=C: v1, v2, v3                     │
│   └─────────────────┘             (old + new)                           │
│   After: Day 1-3 deleted          After compaction:                     │
│   ┌─────────────────┐             key=A: v4  (latest only)                 │
│   │ Day 4 ... Day 7│             key=B: v2  (latest only)                │
│   └─────────────────┘             key=C: v3  (latest only)               │
│                                                                          │
│   Time/space limit.               Key-based "current state."             │
└─────────────────────────────────────────────────────────────────────────┘
```

Left: time wins. Right: key wins. Different tools for different jobs.

---

## Real-World Examples

**Event stream:** click events, page views. Retention 7 days. No compaction. You don't need the "current state" of a click. You need the last week for analytics. Retention is enough.

**User profile changelog:** key=user_id, value=profile JSON. Compaction. After compaction, one message per user—the latest profile. Consumers can rebuild state by reading the topic. Or use it as a materialized view.

**CDC (Change Data Capture):** database changes. Key=table+primary_key. Value=row. Compaction gives you "current row state" per key. Exactly what you need for syncing to a replica or search index.

---

## Let's Think Together

**"Topic with compaction. Key=user_123 has 50 messages over time. After compaction, how many remain?"**

Answer: One. Compaction keeps only the latest message per key. The 49 older messages for user_123 are removed. The one remaining has the most recent offset for that key. So: 50 → 1. Space saved. And any new consumer reading the topic gets the "current state" of user_123 in one message instead of replaying 50. That's the power of compaction.

---

## What Could Go Wrong? (Mini Disaster Story)

A team used compaction for a "user-preferences" topic. They expected one message per user. But they didn't use tombstones for deletes. When a user requested "delete my data," they removed the record from the source database. They never sent a null value to Kafka for that key. After compaction, the old "user prefs" message was still there. Deleted users stayed in the topic. GDPR problem. Fix: when deleting, produce a message with key=user_id, value=null. Compaction treats it as a tombstone. The key is removed. Deletion propagates.

---

## Surprising Truth / Fun Fact

Compaction doesn't run continuously. It runs in the background. There's a "log cleaner" that works through segments. For a busy topic, the compaction lag can be hours. If you need "guaranteed latest state right now," compaction alone isn't enough—you might need to read from the "active" (non-compacted) tail. Or use a materialized store (Kafka Streams state store, RocksDB) that gets updated in real time. Compaction is for storage efficiency and catch-up, not necessarily real-time consistency.

---

## Quick Recap (5 bullets)

- **Time-based retention:** delete messages older than X days (default 7); simple, common for event streams.
- **Size-based retention:** delete when partition exceeds Y bytes; use when disk is the limit.
- **Log compaction:** keep only latest message per key; delete older versions; used for changelogs, state, CDC.
- **Tombstones:** send key + value=null to "delete" a key during compaction.
- **Compaction lag:** compaction runs async; don't rely on it for real-time "latest" without understanding lag.

---

## One-Liner to Remember

*"Retention deletes by time. Compaction deletes by key—keeping only the latest."*

---

## Next Video

Up next: **Kafka Exactly-Once: Limits**—the ATM that debits once and dispenses once, even if you press the button twice. We'll see what exactly-once really means and where it stops.
