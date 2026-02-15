# Replication Lag: Monitoring and Handling Stale Reads

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A news anchor reads live news. The sign language interpreter stands beside them. The interpreter is 3 seconds behind. That's fine. Viewers understand. But what if the interpreter falls 30 seconds behind? The deaf viewer sees old news—"Stock market is up!"—while everyone else sees current news—"Stock market has crashed." Same broadcast. Different timing. That's replication lag in databases. The primary has the latest data. The replica is behind. Users reading from the replica see STALE data. How far behind? That's replication lag. And it matters. Let's dig in.

---

## The Story

In a primary-replica setup, the primary takes writes. Replicas get a copy. Replication is asynchronous (usually). The primary writes. It sends changes to the replica. The replica applies them. There's a delay. That delay is **replication lag**.

Users reading from the replica might see data that's seconds—or minutes—old. For a dashboard showing yesterday's metrics? Fine. For a user who just updated their profile and refreshes the page? Problem. They see the old name. "I changed it. Why doesn't it show?" Replication lag.

**Measurement:** compare the primary's latest write position (LSN in PostgreSQL, binlog position in MySQL, etc.) to the replica's position. The difference is lag. Expressed in bytes, number of transactions, or—most intuitive—seconds. "Replica is 5 seconds behind" means the replica's data is as of 5 seconds ago.

---

## Another Way to See It

A relay race. The primary is the runner with the baton. The replica is the next runner, waiting. The baton (data) is being passed. There's a gap. The gap is the lag. The smaller the gap, the more up-to-date the replica. If the gap grows—runner slows, or the primary writes faster than the replica can apply—lag increases. Monitor the gap. Alert when it gets too big.

---

## Connecting to Software

**Monitoring:** track lag as a metric. PostgreSQL: `pg_stat_replication` shows `replay_lag` or similar. MySQL: `SHOW REPLICA STATUS` (or `SHOW SLAVE STATUS`) shows `Seconds_Behind_Master`. Cloud providers expose this. Set up alerts: if lag > 5 seconds (or your threshold), page someone. Lag can indicate replica overload, network issues, or primary write burst.

**Handling:** if lag is high, options include: (1) route reads to the primary (at cost of primary load)—users get fresh data. (2) Tolerate staleness for non-critical reads—caches, analytics, reports. (3) Read-your-writes consistency—route a user's reads to the node they wrote to, or use session sticky routing. (4) Scale replicas—add more, reduce load per replica. (5) Investigate—why is lag high? Slow queries on replica? Network? Disk?

---

## Let's Walk Through the Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│              REPLICATION LAG: PRIMARY vs REPLICA                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   WRITES                          READS                                  │
│   ┌─────────────┐                 ┌─────────────┐                        │
│   │   PRIMARY   │ ── replicate ──►│   REPLICA   │                        │
│   │   (latest)  │    (async)      │   (behind)  │                        │
│   │             │                 │             │                        │
│   │  LSN: 1000  │     LSN: 980    │  LSN: 980   │                        │
│   └─────────────┘                 └──────┬──────┘                        │
│         ▲                                │                               │
│         │                                ▼                               │
│    All writes                    User reads here                         │
│    go here                       Sees data as of LSN 980                  │
│                                  LAG = 1000 - 980 = 20 txns / N seconds  │
│                                                                          │
│   Alert when LAG > threshold. Route critical reads to primary if needed. │
└─────────────────────────────────────────────────────────────────────────┘
```

The replica is behind. Users reading from it see stale data. Monitor. React.

---

## Real-World Examples

**E-commerce:** product catalog reads from replica. A few seconds lag is fine. But "add to cart" and "view cart" must be consistent. Solution: session-affinity—after write, route that user's reads to primary (or use read-your-writes). Or: accept that "view cart" might miss the last add for a second. Trade-off.

**Social feed:** feed generation reads from replica. Lag of 5–10 seconds usually acceptable. User posts, sees their post (read from primary or same session). Others see it when their feed is generated from replica—a few seconds later. Mostly fine.

**Banking:** balance must be accurate. Reads often go to primary. Or use synchronous replication (no lag, but higher latency on writes). Replication lag is unacceptable for critical financial data.

---

## Let's Think Together

**"Replica lag is 10 seconds. User updates their profile name. Immediately refreshes the page (read from replica). What do they see?"**

Answer: The old name. The write went to the primary. The replica hasn't applied it yet—it's 10 seconds behind. The refresh hits the replica. Stale data. Solutions: (1) Read-your-writes: route this user's requests to the primary for a short window after a write. (2) Session affinity: same. (3) Wait: tell the user "refresh in a moment" (bad UX). (4) Always read from primary for profile (increases primary load). (5) Reduce lag (scale replicas, optimize). The right answer depends on your architecture. But the user will see stale data unless you route them to fresh data.

---

## What Could Go Wrong? (Mini Disaster Story)

A trading platform routed all reads to replicas to protect the primary. Replica lag spiked to 2 minutes during a flash crash. Traders saw stale prices. They placed orders based on outdated data. Losses. Lawsuits. The fix: for price-critical reads, route to primary. Or use synchronous replication for that tier. Replication lag is fine for some use cases. For money and trades, it's not. Know which reads can tolerate staleness. Which cannot.

---

## Surprising Truth / Fun Fact

Some databases offer "bounded staleness" as a consistency level. You can say "give me data that's at most 5 seconds old." The database routes your read to a replica only if its lag is under 5 seconds. Otherwise, it routes to primary. You get a guarantee. It's a way to use replicas without risking unbounded staleness. Cosmos DB has this. Other systems implement similar logic in the application layer. Ask for what you need. Design for it.

---

## Quick Recap (5 bullets)

- **Replication lag:** replica is behind the primary; users reading from replica see stale data.
- **Measurement:** primary position minus replica position (bytes, transactions, or seconds); e.g., `Seconds_Behind_Master`.
- **Monitoring:** track lag as a metric; alert when it exceeds a threshold (e.g., >5 seconds).
- **Handling:** route critical reads to primary, tolerate staleness for non-critical, use read-your-writes, scale replicas, investigate root cause.
- **Know your reads:** some can tolerate lag (dashboards); some cannot (balance, profile right after update). Design accordingly.

---

## One-Liner to Remember

*"Replication lag is the gap between what the primary knows and what the replica has. Close the gap or route around it."*

---

## Next Video

Up next: We'll continue with more system design topics. Check the playlist for the next episode!
