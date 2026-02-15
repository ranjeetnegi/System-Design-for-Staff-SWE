# Distributed Locks: When and How (Redis, etcd)

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A shared bathroom in an office. One person at a time. Lock the door. Others wait. Unlock when done. Simple with one bathroom. But what if there are five offices in five buildings, all sharing one reservation system? "Is the bathroom free?" Each office checks independently. Two people might both think it's free. Walk in simultaneously. Oops. Distributed lock = ensuring only ONE process across multiple servers holds the lock at any time. One bathroom. Many buildings. One winner.

---

## The Story

**When to use distributed locks:** Preventing double-processing—two workers handling the same job. Ensuring single leader—one instance does the cron, others don't. Protecting shared resources—one writer at a time. Preventing concurrent modifications—optimistic locking sometimes; distributed lock when you need strong mutual exclusion.

**Redis approach (Redlock):** `SET key value NX EX 30`—set if not exists, expire in 30 seconds. Simple. Fast. If you get the key, you have the lock. Release by deleting the key. But: what if Redis crashes after granting the lock? What if there's clock skew? What if the process pauses (GC) and the lock expires while it thinks it holds it? Another process gets the lock. Now two "holders." Race. Corruption.

**etcd/ZooKeeper approach:** Consensus-backed. Stronger guarantees. Lease. Fencing. But more overhead. Slower. Choose based on your need for safety vs. speed.

**Fencing tokens:** The lock comes with a monotonically increasing token. When you act on the resource, you include the token. The resource checks: "I've seen token 100. This request has token 99. Reject." Stale lock holder—process that paused, lock expired, another got lock—sends an old token. Rejected. Fencing prevents damage from stale holders. Critical for correctness.

---

## Another Way to See It

Think of a library with one copy of a rare book. Multiple libraries in the city. All share a system. "Who has the book?" One library checks it out. Others see "checked out." Simple? What if the network partitions? Two libraries think they have it. Distributed lock with a central system. One checkout. One holder. Or: fencing. Each checkout gets a ticket number. When you return the book, you must show the ticket. Old ticket? Rejected. Prevents "I thought I had it" confusion.

Or a shared whiteboard. Only one person writes at a time. Token passed. "I have the token. I write." But what if someone copies the token? Old token. Fencing: tokens are sequential numbers. Whiteboard rejects old numbers. "I've seen 47. You're showing 45. No." Stale writer blocked. Fencing.

---

## Connecting to Software

**Redis Redlock:** Multiple Redis instances. Acquire lock on majority. Reduces single-point failure. But: complex. Clock assumptions. Martin Kleppmann's blog post showed flaws. Redis creator Antirez responded. Debate. Use for best-effort. Not for "must be correct" critical sections.

**etcd/ZooKeeper:** Lease-based. Compare-and-swap. Consensus. Stronger. Use when correctness matters. Distributed systems that need agreement. Worth the latency.

**Fencing tokens:** Always use when the resource can enforce. Database. File system. Include token in write. Reject old. Prevents GC-pause, lock-expiry, double-holder problem. The most under-appreciated fix.

---

## Let's Walk Through the Diagram

```
    WITHOUT FENCING                         WITH FENCING

    Process A: lock ✓ (token 5)             Process A: lock ✓ (token 5)
    Process A: GC pause 40s                  Process A: GC pause 40s
    Lock expires.                           Lock expires.
    Process B: lock ✓ (token 6)             Process B: lock ✓ (token 6)
    Process A: wakes up, writes             Process A: wakes up, writes (token 5)
    Process B: writes                       Resource: "token 5 < 6, REJECT"
                                            Process B: writes (token 6) ✓
    Both wrote. Data corrupted 💥           Only B's write applied. Correct ✓
```

Left: stale holder overwrites. Corruption. Right: fencing rejects stale token. Correct.

---

## Real-World Examples (2-3)

**Example 1: Kafka consumer groups.** Only one consumer per partition. Coordination via ZooKeeper or Kafka's internal consensus. Distributed lock. One consumer holds. Others don't process that partition. Fencing: generation ID. Old consumer's commits rejected. Fencing in action.

**Example 2: etcd lease.** Application acquires lease. Does work. Renews lease. If process dies, lease expires. Another process can acquire. But: if process pauses (GC), lease might expire. Another acquires. Fencing: use revision numbers. Include in requests. etcd rejects stale. Designed for this.

**Example 3: Chubby (Google).** Distributed lock service. Used by Bigtable, Megastore. Fencing tokens. Sequence numbers. Critical for Google-scale correctness. Open-source equivalent: etcd. Same ideas.

---

## Let's Think Together

**Process A gets a distributed lock. GC pause for 40 seconds. Lock expires. Process B gets the lock. Both now "hold" the lock. How does fencing help?**

Fencing: lock grants token 10 to A. A pauses. Lock expires. B gets lock, token 11. A wakes. Thinks it has lock. Sends write with token 10. Resource has seen token 11 from B. Rejects A's write. "10 < 11. Stale." A's dangerous write never applies. Fencing saves correctness. Without it: A and B both write. Order undefined. Corruption. With fencing: resource trusts only the latest token. Stale rejected. Correct.

---

## What Could Go Wrong? (Mini Disaster Story)

A team used Redis for a distributed lock. Critical section: deduct inventory. No fencing. One day: GC pause. Lock expired. Another process got lock. Deducted. First process woke. Deducted again. Double deduction. Inventory wrong. Revenue wrong. Refunds. Lesson: for critical sections—money, inventory, identity—use fencing. Or use consensus-based lock (etcd). Redis without fencing: best-effort. Not correct. Know the limits.

---

## Surprising Truth / Fun Fact

Martin Kleppmann's 2016 blog post "How to do distributed locking" criticized Redlock. Redis creator Antirez responded. A famous debate. Kleppmann: Redlock assumes synchronous model. Real systems have async. Pauses. Clocks. Redlock can fail. Antirez: for many use cases, good enough. The debate clarified: distributed locking is hard. Know what you're trading. Fencing tokens emerged as the key insight. Include them. Reject stale. Most systems now document this. One blog post. Industry-wide impact.

---

## Quick Recap (5 bullets)

- **Distributed lock** = one holder across many processes. For double-processing, single leader, shared resources.
- **Redis (Redlock):** simple, fast. But: clock assumptions, no fencing. Best-effort.
- **etcd/ZooKeeper:** consensus-backed. Stronger. More overhead.
- **Fencing tokens:** lock includes monotonically increasing token. Resource rejects old. Prevents stale holder damage.
- **GC pause + expired lock** = two holders. Fencing fixes. Always use for critical sections.

---

## One-Liner to Remember

**Distributed lock: one winner across many servers. Use fencing tokens—or a stale "holder" will corrupt your data.**

---

## Next Video

Next: **Why Multi-Region?** Latency and availability. Why one datacenter isn't enough for the world. Stay tuned.
