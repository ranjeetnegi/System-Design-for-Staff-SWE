# Hash-Based Sharding Explained

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Four friends. One house. They must split the cleaning. How to assign rooms? Each person picks a room? Fights. Someone gets the bathroom. Someone gets the hallway. Unfair. So they use a magic number machine. Type "kitchen" — out comes 7. 7 divided by 4, remainder 3. Friend 3 cleans the kitchen. Type "bedroom" — 12. Remainder 0. Friend 0. Type "bathroom" — 5. Remainder 1. Friend 1. Same room. Same friend. Every time. Random-looking but DETERMINISTIC. And roughly even. That machine? That's a hash function. That's hash-based sharding.

---

## The Story

Four friends share a house. Weekly cleaning. How to assign rooms fairly? They could argue. Or they could use a rule. A magic number machine — a hash function. You type a room name. It gives you a number. Kitchen → 7. Bedroom → 12. Bathroom → 5. Living room → 22. Then: divide by 4 (number of friends). Take the remainder. 7 mod 4 = 3. Friend 3 cleans the kitchen. 12 mod 4 = 0. Friend 0. 5 mod 4 = 1. Friend 1. 22 mod 4 = 2. Friend 2. Every room maps to exactly one friend. And the distribution? Roughly even. No one gets overloaded. That's hash-based sharding.

In databases: hash(key) mod N = shard number. N = number of shards. user_id 12345 → hash(12345) = 87392 → 87392 mod 4 = 0 → Shard 0. user_id 67890 → hash(67890) = 21047 → 21047 mod 4 = 3 → Shard 3. Same key. Same shard. Every time. Deterministic. No lookup table. Just math.

**Even distribution:** Hash functions spread values uniformly. No natural clusters. user_id 1, 2, 3, 4 don't all go to the same shard. Spread out. Good.

But here's where things go WRONG. Business grows. You need a fifth friend. Five shards. hash(key) mod 5. Everything changes. What was mod 4 is now mod 5. Keys that went to Shard 0 might now go to Shard 4. Keys that went to Shard 3 might now go to Shard 2. MASSIVE reshuffling. Adding one shard? Roughly 80% of your data moves. Think about that.

---

## Another Way to See It

A deck of cards. Deal to 4 players. Each gets 13 cards. Even. Fair. Now add a 5th player. You have to redeal. EVERYTHING. Not just give 5 cards to the new player. The whole deck. Re-shuffle. Re-distribute. Hash mod N is the same. Change N. Re-shuffle everything.

---

## Connecting to Software

**Formula:** hash(partition_key) mod N = shard_number. N = total shards. MD5, SHA-256, CRC32 — any hash works. Consistent output for same input.

**Properties:**
- **Deterministic:** Same key → same shard. Always. No need to store a mapping.
- **Even distribution:** Hash functions uniform. User IDs. Order IDs. Spread across shards. No hot spots. Usually.
- **Fast routing:** Compute hash. Mod. Done. O(1). No database lookup. No metadata table.

**The BIG problem:** Resharding. Add a shard. N becomes N+1. hash mod 5 ≠ hash mod 4. Most keys map elsewhere. Data migration. Massive. Downtime. Complexity. That's why consistent hashing was invented. Next video. Think about that — you design a system. It works. You grow. You need one more shard. And suddenly 80% of your data has to move. The simplicity of hash mod N comes with a hidden cost.

---

## Let's Walk Through the Diagram

```
HASH-BASED SHARDING

Key: user_id = 12345
N = 4 shards

    user_id          hash()           mod 4
        │                │               │
   [12345]  ──────►  [87392]  ──────►  [0]
        │                │               │
        │                │               ▼
        │                │          ┌─────────┐
        │                │          │ Shard 0 │
        │                │          └─────────┘

Same key → Same hash → Same shard. Every time.

ADD SHARD 5:  mod 4 → mod 5
87392 mod 4 = 0  (Shard 0)
87392 mod 5 = 2  (Shard 2)  ← MOVED!
Most keys move. Reshuffle. Pain.
```

Step 1: Key enters. Step 2: Hash function. Step 3: Mod by N. Step 4: Shard number. Simple. Fast. But N changes? Chaos.

---

## Real-World Examples (2-3)

**1. MySQL Vitess:** Uses hash-based sharding. Vtables. Vtgate routes by hash. Simple. Fast. But resharding is a project. They have tools. Still complex.

**2. Elasticsearch:** Index shards. By default hashes document ID. Even distribution across shards. Add node? Rebalance. Not instant.

**3. Redis Cluster:** 16384 hash slots. Keys hash to slots. Slots assigned to nodes. Add node? Reassign slots. Migration. Same idea. Same pain.

---

## Let's Think Together

You have 4 shards. Business grows. You add a 5th. Hash mod 4 becomes hash mod 5. What percentage of data needs to move?

*Let that sink in.*

With simple modular hashing, when you add 1 shard to N shards, roughly (N-1)/N of all data moves. For 4 → 5: about 80%. For 10 → 11: about 90%. Almost everything. That's why companies invented consistent hashing. Minimal movement. Only the data that would map to the new shard. We'll see that next.

---

## What Could Go Wrong? (Mini Disaster Story)

Startup. 4 shards. 100 million rows. Growing fast. Need more capacity. Add shard 5. The migration begins. 80 million rows must move. Copy. Verify. Delete from old. Takes days. During migration: dual-write. Double the write load. Reads: check both old and new locations. Complexity. A bug. Some rows copied wrong. Inconsistency. Reads return stale data. Users complain. Rollback? Too far in. Fix forward. Sleepless nights. Hash-based sharding. Simple to start. Painful to change. Plan for growth from day one.

---

## Surprising Truth / Fun Fact

With simple modular hashing and N shards, adding 1 shard reshuffles roughly (N-1)/N of all data. For 4 → 5 shards, about 80% of data moves. For 100 → 101, about 99% moves. Almost everything. That's why consistent hashing — where only 1/N of data moves — was a breakthrough. Invented in 1997. For web caching. Now used everywhere.

---

## Quick Recap (5 bullets)

- **Hash-based sharding:** hash(key) mod N = shard. Deterministic. Even distribution. No lookup.
- **Pros:** Simple. Fast. Fair. No hot spots from key skew.
- **Con:** Resharding. Add/remove shard → N changes → most data reshuffles. Massive migration.
- **For 4→5 shards:** ~80% of data moves. Painful.
- Consistent hashing (next) solves the resharding problem. Minimal movement.

---

## One-Liner to Remember

> Hash the key. Mod by N. Same key, same shard. Change N? Everything moves. That's the trade-off.

---

## Next Video

Adding a shard shouldn't move 80% of your data. There's a better way. A ring. Servers on a circle. Data maps to the next server. Add one? Only nearby data moves. Consistent hashing. The musical chairs of distributed systems. Next.
