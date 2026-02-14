# Clock Sync in Distributed Systems: The Problem

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Kitchen clock: 10:02. Bedroom clock: 10:05. Living room: 9:58. You run between rooms. Which meeting is first? You can't tell. The clocks lie. Now imagine 1000 servers. Each with its own clock. Each slightly wrong. Server A logs an event at 10:00:00.001. Server B logs at 10:00:00.005. But B's clock is 10 milliseconds ahead. So A's event actually happened later—but looks earlier. Ordering is broken. Causality is broken. That's the clock problem in distributed systems. Let me show you why it matters and what we do about it.

---

## The Story

**Why clocks drift:** Hardware. Every crystal oscillator is different. Temperature affects them. Servers in cold aisles vs. hot. Age. Even two "identical" servers will drift apart. Milliseconds per day. Seconds per week. Without sync, chaos. **Network delay:** Asking "what time is it?" over the network adds latency. The answer is late when it arrives. Time sync over a network is fundamentally approximate.

**Why it matters:** Event ordering. "Which write came first?" Cache expiry. "Is this cached value stale?" Distributed transactions. "What's the commit order?" Log correlation. "Debug this bug across 10 services." All need some notion of time. Wrong clocks = wrong answers. Data corruption. Stale reads. Confusion.

**NTP (Network Time Protocol):** Syncs clocks over the internet. Accuracy: 1–10ms on LAN. 10–100ms over WAN. Better than nothing. But not enough for strict ordering. Two events 5ms apart? You can't tell order with 10ms uncertainty. NTP is "good enough" for many things. Not for globally consistent transactions.

---

## Another Way to See It

Think of time zones. New York: 10 AM. London: 3 PM. Tokyo: midnight. Same moment. Different numbers. Now imagine each clock is not just in a different zone—it's running at a different speed. Fast. Slow. Drifting. Comparing "when" across servers becomes a guess. Clock sync tries to align them. Get them close. But perfect sync is impossible. We approximate. We design around the uncertainty.

---

## Connecting to Software

**NTP:** Syncs to time servers. Stratum 1 = atomic clock. Stratum 2 = syncs to stratum 1. And so on. Your server might be stratum 4. Each hop adds error. Typical: ±10ms. Fine for logs. Fine for "approximately when." Not for "which happened first" when events are milliseconds apart.

**Google TrueTime:** Spanner's solution. GPS + atomic clocks in every datacenter. Each server knows time within an uncertainty bound. Usually < 7ms. Spanner uses this for globally consistent timestamps. Commit timestamps. Ordered. Correct. Expensive. Google-level infrastructure. Most of us don't have it.

**Alternatives:** Logical clocks (Lamport, vector). Forget physical time. Use counters. Ordering without clocks. Next videos cover these. When physical time fails, logic wins.

---

## Let's Walk Through the Diagram

```
    CLOCK DRIFT: THE PROBLEM

    Server A (clock fast by 5ms)    Server B (clock correct)
    Event at real time T=100        Event at real time T=102
    Logs: T=105                    Logs: T=102
    
    A's event LOOKS later (105 > 102)
    But A's event actually happened FIRST (100 < 102)
    
    Ordering broken. Causality broken.

    NTP: Reduces drift. ±10ms typical.
    TrueTime: ±7ms. Better. Expensive.
    Logical clocks: No physical time. Use counters.
```

The diagram shows: drift causes wrong ordering. Sync helps. Doesn't fix. Logical clocks avoid the problem.

---

## Real-World Examples (2-3)

**Example 1: Cassandra.** Uses timestamps for conflict resolution. Last-write-wins. Clock skew? Wrong "last" writer. Data loss. Cassandra recommends NTP. Tight sync. Or use application-provided timestamps. Know the risk.

**Example 2: Spanner.** TrueTime. Distributed transactions. Global consistency. Commit timestamps ordered correctly. The gold standard. Requires GPS + atomic clocks. Not for everyone.

**Example 3: MongoDB.** Cluster time. Internal logical clock. Replication uses it. Reduces dependence on physical clocks for ordering. Hybrid approach. Logical time for critical ordering. Physical for display.

---

## Let's Think Together

Server A writes at T=100ms (its clock). Server B writes at T=99ms (its clock). But B's clock is 5ms ahead. Which write actually happened first?

A's. In real time: A wrote when real time was ~100ms (assuming A's clock is correct). B wrote when real time was ~94ms (B's clock says 99, but it's 5ms fast, so real = 94). So B actually wrote first. But if you use timestamps as-is, A (100) looks later than B (99). You'd think A is "last write." Wrong. B wrote first. A wrote second. Clock skew reversed the order. That's why LWW with unsynced clocks is dangerous. Sync your clocks. Or use logical time.

---

## What Could Go Wrong? (Mini Disaster Story)

A distributed system used timestamps for cache invalidation. "If data is older than 5 seconds, refresh." Server A's clock was 10 seconds behind. Cached data looked "fresh" to A (timestamp in future). Never refreshed. Stale data served for hours. Server B's clock was 5 minutes ahead. Every request triggered refresh. Overload. One deployment. Two clock problems. Opposite directions. They enforced NTP. Monitoring. Alerts on clock drift. Lesson: don't trust clocks without sync. And monitor. Drift happens.

---

## Surprising Truth / Fun Fact

Google has custom atomic clocks and GPS receivers in every data center for TrueTime. Each server knows the exact time within a few microseconds. Not milliseconds. Microseconds. They built their own time infrastructure. Spanner's global consistency depends on it. When you need planet-scale ordered transactions, you need planet-scale time. Google did it. Most of us use NTP and hope. Or we use logical clocks and avoid the problem entirely.

---

## Quick Recap (5 bullets)

- **Clocks drift:** Hardware, temperature, network. Can't be avoided. Only reduced.
- **Why it matters:** Event ordering, cache expiry, distributed transactions, debugging.
- **NTP:** ±10ms typical. Good for logs. Not for strict ordering.
- **TrueTime:** Google's solution. ±7ms. GPS + atomic clocks. Spanner uses it.
- **Alternative:** Logical clocks. No physical time. Counters. Next up.

---

## One-Liner to Remember

**Clock sync: Three clocks at home. All wrong. 1000 servers? Ordering breaks. NTP helps. TrueTime is better. Or skip clocks—use logic.**

---

## Next Video

Next: **Lamport Timestamps.** No clocks? No problem. Use a counter. Every event: increment. Send message: attach counter. Receive: max + 1. Ordering without time. Logical clocks. Simple. Powerful. See you there.
