# What is Database Replication? (Leader-Follower)

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A news anchor reads the evening news. Live. Three other TV channels take that broadcast and show it to their viewers. Same content. Same words. The anchor is the SOURCE. The others are COPIES. If the anchor makes a mistake? The copies show the mistake too. If one channel goes down? The other two still work. But if the ANCHOR goes down? Nobody has new content. That is leader-follower replication. The backbone of every production database. Let me show you how it works.

---

## The Story

Picture the studio. One anchor. One camera. Live broadcast. Channel A, B, and C — they do not have their own anchors. They RECEIVE the signal. They replicate it. Same video. Same audio. To their audiences. The anchor creates. The channels copy. That is the model.

Now imagine the anchor makes a mistake. Says "Tuesday" instead of "Thursday." The followers show it. They do not correct it. They replicate. Faithfully. Whatever the leader does, the followers reflect. That is **leader-follower replication**. One source of truth. Many copies.

What if Channel B has a technical glitch? Goes offline? Channel A and C keep broadcasting. The system is resilient. One follower down. Others continue.

But here is where things go WRONG. What if the anchor — the leader — collapses? Heart attack. Or the studio loses power. Now nobody has NEW content. The followers have yesterday's news. Last hour's news. But nothing fresh. The leader is gone. Who creates now? Someone has to step up. That moment — when a follower becomes the new leader — is called **leader election**. And it is one of the hardest problems in distributed systems.

---

## Another Way to See It

A head chef creates a recipe. Writes it down. Sous chefs have copies. They follow the recipe exactly. If the head chef changes the recipe — adds salt, removes pepper — she tells everyone. They update their copies. All sous chefs now have the new recipe. If one sous chef loses their copy? Others still have it. If the head chef leaves? Someone must become the new head chef. Take over recipe creation. That is leader-follower. One creator. Many followers. Sync when possible. Promote when necessary.

---

## Connecting to Software

**Leader (primary/master):** Accepts ALL writes. The single source of truth. The anchor. The head chef.

**Followers (replicas/slaves):** Receive copies of writes. Serve reads. They replicate from the leader. Same data. Eventually.

**Why replicate?** Three reasons. (1) **High availability** — if the leader dies, promote a follower. No single point of failure. (2) **Read scaling** — spread reads across followers. Less load on leader. (3) **Geographic distribution** — place replicas in Tokyo, London, New York. Users read from the nearest replica. Lower latency.

**Replication methods:**
- **Statement-based:** Leader sends the actual SQL. "INSERT INTO users VALUES (...)". Followers execute it. Simple. But non-deterministic functions (NOW(), RAND()) can cause divergence.
- **Row-based:** Leader sends the actual data changes. "Row 5 in users table: name changed to X." Followers apply the change. More precise.
- **WAL shipping:** Leader ships the Write-Ahead Log. The raw log of changes. Followers replay it. PostgreSQL, MySQL use variants of this. Fast. Efficient.

**Leader election:** Leader crashes. Who becomes the new leader? Follower 1? Follower 2? They must agree. Consensus. Protocols like Raft, Paxos. We will dive into that later. For now — know that it is complex. Race conditions. Split brain. The stuff of nightmares.

---

## Let's Walk Through the Diagram

```
LEADER-FOLLOWER REPLICATION

[Client] -- Write --> [LEADER]
                          |
                          | Replication stream
                          | (WAL / statements / rows)
                          |
            +-------------+-------------+
            |             |             |
            v             v             v
      [Follower 1]  [Follower 2]  [Follower 3]
            ^             ^             ^
            |             |             |
[Client] -- Read -- [Client] -- Read -- [Client] -- Read

Writes: Leader only. Reads: Any follower (or leader).
Replication: async or sync (next video).
```

---

## Real-World Examples (2-3)

**1. PostgreSQL** — Built-in streaming replication. One primary. Multiple standbys. WAL shipping. Promote a standby to primary if the main one fails. Default pattern for production.

**2. MongoDB** — Replica set. One primary. Multiple secondaries. Same idea. Writes to primary. Replication to secondaries. Automatic failover.

**3. MySQL** — Master-replica (historically master-slave). Binary log replication. Same leader-follower model. Every major database uses it.

---

## Let's Think Together

**Question:** The leader crashes. Follower 2 is promoted to the new leader. But Follower 2 was 5 seconds behind. What happens to those 5 seconds of data?

**Pause. Think.**

**Answer:** That data might be LOST. If the leader had written 5 seconds of transactions that never reached Follower 2, those writes are gone. The old leader is dead. The new leader (Follower 2) never received them. Clients who thought their writes succeeded? They might get an error on retry. Or — if the leader had acknowledged the write but died before replicating — the data is lost. This is why sync vs async replication matters. Next video.

---

## What Could Go Wrong? (Mini Disaster Story)

**Split brain.** Network glitch. The followers cannot reach the leader. They think: "Leader is dead." They promote Follower 1 to the new leader. Follower 1 starts accepting writes. But the OLD leader is not dead. It was just a network partition. It recovers. Now there are TWO leaders. Both accepting writes. Data diverges. User A writes to Leader 1. User B writes to Leader 2. Same key. Different values. Chaos. Replication cannot fix this. You need consensus. Quorum. To prevent split brain. This is why distributed systems are hard.

---

## Surprising Truth / Fun Fact

PostgreSQL, MySQL, MongoDB, Redis, Cassandra — almost every production database uses leader-follower replication. It is the **default pattern of the internet**. When you deploy a database in AWS, GCP, or Azure, you get it automatically. One primary. Replicas. Replication. It is so common we forget how powerful it is. And how dangerous when it goes wrong.

---

## Quick Recap (5 bullets)

- **Leader** = accepts all writes. **Followers** = receive copies, serve reads.
- **Why replicate?** High availability. Read scaling. Geographic distribution.
- **Methods:** Statement-based, row-based, WAL shipping. Different trade-offs.
- **Leader election** = when leader dies, promote a follower. Consensus required.
- **Split brain** = two leaders. Network partition. Data diverges. Disaster. Avoid with quorum.

---

## One-Liner to Remember

> One anchor creates the news. Many channels broadcast it. Same content. Until the anchor falls.

---

## Next Video

So replication happens. But WHEN does the leader wait for the follower? Does it wait at all? What if the leader says "I am done" and the follower has not received the data yet? The leader crashes. Data lost. This is the sync vs async question. Next: **Sync vs Async Replication** — the trade-off between safety and speed. And why banks do it differently from social media.
