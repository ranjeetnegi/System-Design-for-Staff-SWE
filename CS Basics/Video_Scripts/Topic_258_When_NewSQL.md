# When to Use NewSQL (Spanner, CockroachDB)

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

For years, the choice was brutal. SQL gives you transactions. Consistency. Relations. But it doesn't scale horizontally. Add more machines? Pain. NoSQL scales—shard forever—but no transactions. No strong consistency. Pick one: correctness or scale. Then NewSQL said: "Why not both?" Distributed SQL databases that scale horizontally AND give you ACID transactions. Spanner. CockroachDB. Sounds like magic. What's the catch? And when do you actually need it?

---

## The Story

For decades, we had two camps. Traditional SQL: one server, or primary-replica. Writes go to one place. Scale reads with replicas. Scale writes? Hard. Sharding = application complexity. Distributed transactions = nightmare. So we lived with it. Single-node SQL for "serious" data. NoSQL for "big" data.

NewSQL challenged that. Data sharded across nodes. Distributed transactions using consensus—Raft, Paxos. SQL interface. ACID. You write normal SQL. The system figures out distribution. Replication. Consistency. Google Spanner did it first. CockroachDB, TiDB, YugabyteDB followed. Same promise: SQL + horizontal scale + strong consistency.

But there's a catch. Consensus has overhead. Every write might touch multiple nodes. Latency is higher than single-node. Operations are more complex. Cost is higher. When is it worth it?

---

## Another Way to See It

Imagine a library. Old way: one building. All books. Can't expand. New way: many buildings, but no card catalog. Find a book? Good luck. NewSQL: many buildings, one catalog, synchronized. You ask for a book. The system knows where it is. You get it. Consistency across buildings. Scale plus order. That's the dream. The cost? Coordinating across buildings takes time. Not instant. But it works.

---

## Connecting to Software

**NewSQL examples:** Google Spanner, CockroachDB, TiDB, YugabyteDB. Distributed. Sharded. SQL. ACID.

**How:** Data partitioned by key range or hash. Each partition replicated (often 3 nodes). Consensus (Raft) for writes. Read-your-writes. Serializable isolation. SQL on top.

**The catch:** Higher latency than single-node. Cross-node transactions = multiple round trips. Operational complexity. More moving parts. Cost—licensing, hardware, expertise.

**When to use:** Need SQL + horizontal scale + strong consistency. Global app. Multi-region. Financial data. Can't shard at app level. Need cross-shard transactions.

**When NOT:** Simple key-value (Redis, DynamoDB). Read-heavy, eventual consistency OK (PostgreSQL + replicas). Small scale (single PostgreSQL is fine). Prototype or MVP—don't start with distributed complexity. Migrate when you hit the limits. Premature optimization is real. NewSQL is powerful. It's also heavy. Use it when the problem demands it.

**Migration path:** Many teams start with PostgreSQL. Grow. Hit connection limits, or storage limits, or need multi-region. Options: Citus (sharded PostgreSQL), or full NewSQL (CockroachDB, TiDB). Migration is non-trivial. Schema might need changes. Test thoroughly. NewSQL isn't drop-in PostgreSQL—close, but not identical. Plan the move.

---

## Let's Walk Through the Diagram

```
NewSQL Architecture:

  [App] --SQL--> [Node 1] --+
  [App] --SQL--> [Node 2] ---+-> Consensus (Raft)
  [App] --SQL--> [Node 3] --+    Replication
  [App] --SQL--> [Node 4] --+    Sharding
  [App] --SQL--> [Node 5] --+

  Shard A: nodes 1,2,3 (replicated)
  Shard B: nodes 2,4,5
  ...

  Single SQL interface. Distribution hidden.
  Cross-shard transaction? Consensus. Slower. But works.
```

---

## Real-World Examples (2-3)

**Google Spanner:** Powers Google Ads, GCP. Global. Multi-region. Strong consistency. When you need "one database, worldwide," Spanner is the answer. Cost: high. Complexity: high.

**CockroachDB:** Open-source Spanner-like. Used by Comcast, Bose. Multi-region deployment. Survives region failure. SQL. Good for global apps that need consistency.

**TiDB:** MySQL-compatible. Scales horizontally. Used in China at massive scale. When you have MySQL skills but need scale, TiDB fits. Migration path from MySQL. PingCAP (TiDB's company) serves customers with hundreds of TB. Same story: need SQL, need scale, need consistency.

**YugabyteDB:** PostgreSQL-compatible. Distributed. Multi-region. Another Spanner-inspired system. Good for teams that want PostgreSQL semantics with horizontal scale. Less mature than CockroachDB in some areas, but growing. The NewSQL ecosystem is vibrant—Spanner, CockroachDB, TiDB, YugabyteDB. Pick based on your stack (MySQL vs PostgreSQL), scale, and operational preference.

---

## Let's Think Together

**Question:** Your app has 100 million users across 5 continents. You need strong consistency for payment data. Options: single PostgreSQL? Sharded PostgreSQL? CockroachDB?

**Answer:** Single PostgreSQL won't scale to 100M users with global latency. Sharded PostgreSQL: you handle distribution. Cross-shard payments = 2PC or SAGA. Complex. CockroachDB (or Spanner): built for this. Distributed. SQL. ACID across shards. You pay with latency and cost, but you get consistency without building it yourself. For payments, consistency matters. NewSQL is a strong fit. For non-critical data, maybe read replicas + eventual consistency is enough. Match the tool to the requirement.

---

## What Could Go Wrong? (Mini Disaster Story)

A team picks CockroachDB for a simple CRUD app. 10,000 users. Single region. They wanted "future-proof scale." Reality: 5x the operational complexity. Higher latency than PostgreSQL—every write goes through consensus. Bugs in the new system—less mature than PostgreSQL. Overkill. Six months later they migrate back to PostgreSQL. The lesson: NewSQL solves real problems. Don't use it because it's cool. Use it when you have the problem. "We might need it someday" is not a good reason. "We need it now" is.

---

## Surprising Truth / Fun Fact

Spanner uses atomic clocks. TrueTime. For global ordering of transactions without a single bottleneck. GPS + atomic clocks = timestamps accurate to 7 milliseconds. That enables global consistency across datacenters. No single leader. CockroachDB uses hybrid logical clocks—no atomic clocks needed. Same idea, different implementation. Distributed time is hard. NewSQL solves it. The result: you can run a transaction that touches rows in Tokyo and New York, and the system guarantees correctness. That's the promise. The cost is latency—round trips, consensus—but for the right workload, it's worth it. Evaluate honestly: do you have the problem NewSQL solves? If yes, it's a powerful tool. If no, stick with PostgreSQL and scale it. Don't over-engineer. Start simple. Add complexity when you hit real limits. NewSQL is there when you need it—not before. Patience pays off.

---

## Quick Recap (5 bullets)

- **NewSQL** = distributed SQL with ACID; Spanner, CockroachDB, TiDB
- **How** = sharding + consensus (Raft) + replication; SQL interface
- **Catch** = higher latency, more complexity, higher cost than single-node
- **Use when** = need SQL + horizontal scale + strong consistency; global, financial
- **Don't use when** = key-value, read-heavy with eventual consistency OK, small scale

---

## One-Liner to Remember

**NewSQL: SQL plus horizontal scale plus ACID—when you need all three, and you're willing to pay the complexity and latency cost.**

---

## Next Video

Up next: Time-series databases. Why they're different. And the Gorilla compression trick that shrinks billions of readings.
