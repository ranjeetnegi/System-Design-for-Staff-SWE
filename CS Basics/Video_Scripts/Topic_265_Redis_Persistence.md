# Redis Persistence: RDB vs AOF

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You keep a whiteboard of daily tasks. Two backup strategies. Strategy one: take a PHOTO of the whiteboard every hour. If the whiteboard gets erased, restore from the last photo. You lose up to one hour of work. Strategy two: write every single change in a NOTEBOOK as it happens. If the whiteboard gets erased, replay the notebook from the start. You lose nothing. But the notebook gets huge. Redis gives you both options. RDB is the photo. AOF is the notebook. Let's understand when to use each—and the hybrid that gives you the best of both.

---

## The Story

Redis is an in-memory database. Blazing fast. Sub-millisecond latency. But memory is volatile. Power off. Crash. Restart. Everything in RAM—gone. For a cache, that might be okay. Warm up from the database. For Redis as a primary data store—sessions, real-time rankings, leaderboards—losing everything is unacceptable. You need persistence. Redis offers two mechanisms: RDB and AOF.

RDB—Redis Database—is a snapshot. A point-in-time copy of your entire dataset, written to a file. Like a photograph. Quick to take. Quick to load. But between snapshots? If you snapshot every hour and crash at 59 minutes, you lose 59 minutes of data.

AOF—Append-Only File—is a log. Every write command (SET, INCR, LPUSH) gets appended to a file. On restart, Redis replays every command. You recover to the exact state before the crash. Zero data loss. But the file grows. And grows. Replay can take minutes or hours for huge datasets.

---

## Another Way to See It

Imagine a diary. RDB is like taking a photo of every page at the end of the day. Fast. Compact. But if you spill coffee at 3 PM, you lose everything you wrote after the morning photo. AOF is like writing every word you add to the diary in a second notebook, in order. If you spill coffee, you reconstruct the diary by rereading that notebook. Nothing lost. But that second notebook is massive—and reading it all back takes time.

---

## Connecting to Software

**RDB (Redis Database):** Periodic point-in-time snapshots. Redis forks its process. The child process serializes the in-memory data to a file (dump.rdb). The parent keeps serving requests. When the child finishes, the snapshot is done. Recovery is fast: load the file, you're back. But you accept data loss between snapshots. Configure with `save 900 1` (snapshot if 1 key changed in 15 min) or `save 60 10000` (snapshot if 10K keys changed in 1 min). Tune based on your tolerance for loss.

**AOF (Append-Only File):** Every write command is logged. On startup, Redis reads the AOF and replays commands one by one. Zero data loss—if the disk doesn't fail. But the file grows without bound. Redis supports AOF rewrite: periodically compact the file by replaying the current state into a new file. Options: `appendfsync always` (sync after every write—safest, slowest), `appendfsync everysec` (sync once per second—good balance), `appendfsync no` (let OS decide—fastest, most risk).

**Hybrid (Redis 4.0+):** RDB snapshot PLUS AOF of changes since the last snapshot. Best of both. Fast recovery from the RDB. Minimal data loss from the incremental AOF. Recommended for production when data matters.

---

## Let's Walk Through the Diagram

```
RDB Snapshot:
┌─────────────────┐     fork()      ┌─────────────────┐
│   Redis         │ ───────────────►│  Child Process  │
│   (parent)      │                 │  (writes RDB    │
│   Serves        │                 │   to disk)      │
│   requests      │                 └────────┬────────┘
└─────────────────┘                         │
         │                                  │ dump.rdb
         │ still serving                    ▼
         │                          ┌───────────────┐
         │                          │  Disk File    │
         │                          │  (snapshot)   │
         │                          └───────────────┘
         │
         └──► Crash? Load dump.rdb → Lose data since last snapshot

AOF Log:
┌─────────────────┐
│   Redis         │  SET user:1 "John"
│   (writes)      │  INCR counter
│                 │  LPUSH list "a"
└────────┬────────┘
         │ append each command
         ▼
┌─────────────────┐
│  appendonly.aof │  *3\r\n$3\r\nSET\r\n$6\r\nuser:1\r\n$4\r\nJohn\r\n
│  (grows)        │  *2\r\n$4\r\nINCR\r\n$7\r\ncounter\r\n
└─────────────────┘
         │
         └──► Crash? Replay AOF → Zero data loss, slow recovery
```

The diagram shows the trade-off: RDB is fast and lightweight but loses data. AOF preserves everything but costs space and recovery time.

---

## Real-World Examples (2-3)

**Session store:** RDB might be fine. Losing 15 minutes of sessions? Users re-login. Acceptable. Fast recovery matters more.

**Shopping cart:** AOF or hybrid. Losing cart data = lost sales. Users abandon when their cart disappears. Persistence is critical.

**Leaderboard / gaming:** Depends. If you can rebuild from a source of truth (game events in Kafka), RDB is okay. If Redis IS the source of truth, use AOF or hybrid.

---

## Let's Think Together

**"Redis has 50GB of data. RDB snapshot takes 30 seconds. During those 30 seconds, can Redis still serve requests?"**

Yes. Redis uses copy-on-write when forking. The parent process continues serving. The child writes the snapshot. Memory can spike (up to 2x briefly) because of copy-on-write—modified pages get copied. But requests keep flowing. The only caveat: if you have limited memory, the fork + copy-on-write can cause OOM. Monitor memory during snapshots. For 50GB, ensure you have headroom—maybe 60–70GB total RAM to be safe.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup uses Redis for payment transaction IDs. They rely on RDB with a 1-hour snapshot interval. One morning: Redis crashes at 58 minutes past the hour. They restore from the last snapshot. 58 minutes of transaction IDs—gone. Duplicate IDs get generated. Payments fail. Refunds go to wrong customers. They discover the issue when a customer complains about a double charge. AOF would have saved them. They switch to hybrid. Never again. The lesson: know what you're storing. Financial data, user-generated content, anything irrecoverable—use AOF or hybrid. RDB alone is for data you can afford to lose.

---

## Surprising Truth / Fun Fact

Redis was originally designed as a cache. Persistence was almost an afterthought. The name comes from "REmote DIctionary Server"—emphasis on remote and dictionary, not durability. Today, people use Redis for everything from caching to queues to primary data stores. Persistence options evolved to support that. The "cache" has grown up.

---

## Quick Recap (5 bullets)

- **RDB** = periodic snapshots; fast recovery, data loss between snapshots.
- **AOF** = log every write; replay on restart; zero data loss, large files, slower recovery.
- **Hybrid (Redis 4.0+)** = RDB + AOF since last snapshot; fast recovery + minimal loss.
- **Fork** = Redis forks for RDB; parent keeps serving; child writes to disk.
- **Choose** = cache/tolerable loss → RDB; critical data → AOF or hybrid.

---

## One-Liner to Remember

*RDB is a photo of your whiteboard—fast but you lose what happened after the photo. AOF is a notebook of every change—nothing lost, but the notebook gets heavy.*

---

## Next Video

Next: Redis Cluster. One Redis node is not enough. How do you split 16,384 slots across nodes? Hash slots, client routing, and what happens when you add a fourth node. See you there.
