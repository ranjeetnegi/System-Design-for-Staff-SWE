# Why 2PC Is Painful in Practice

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Everyone voted yes. The dinner is on. But the organizer's phone dies. Right before they can say "Let's go!" Now what? Six people. Schedules cleared. Restaurant tentatively held. And they're frozen. Do we go? Do we stay? No one can decide without the organizer. Resources locked. Time ticking. That's not just a bad evening. That's 2PC when the coordinator dies.

---

## The Story

Back to the dinner. Everyone checked their schedule. Everyone voted YES. Pizza Palace. Saturday. Perfect. Then—the organizer's phone dies. Right before they can announce the final decision. Everyone is stuck. "Do we go? Do we stay?" The venue is holding the table. People have cleared their calendars. But the organizer—the only one who can make the final call—is gone. Resources locked. Nobody can do anything. They wait. Maybe the organizer comes back. Maybe they don't. That's 2PC in practice. The coordinator is the single point of failure. Crash after prepare, before commit? Everyone is blocked. Possibly forever.

---

## Another Way to See It

Imagine a jury. They've all voted. Guilty or not guilty. But the judge—the one who must read the verdict—has left the building. The jury can't leave. The defendant can't leave. The court is frozen. The verdict exists. But it's unpronounceable. That's 2PC. The verdict is the commit decision. The judge is the coordinator. No judge, no verdict. No verdict, no one moves.

---

## Connecting to Software

**Why is 2PC painful?** Four big reasons.

**One: Blocking protocol.** Participants hold locks. They voted YES. They're holding resources. Waiting. For the coordinator. If the coordinator dies, they can't safely commit—they need the decision. They can't safely abort—same. They block. Indefinitely. One dead process. All participants frozen.

**Two: Performance.** Two round-trips minimum. Prepare. Wait for all. Commit. Wait for all. Every participant must respond. Latency = slowest participant. One slow service? Everyone waits. Add network delays. Add lock contention. 2PC is not fast.

**Three: Availability.** Any participant failure blocks the whole transaction. N services = N points of failure. One says NO? Abort. One times out? Uncertainty. Did it vote? Did it not? Coordinator doesn't know. One crashes? Maybe it voted yes, maybe it didn't. Coordinator can't tell. Block or abort? Block: wait forever for a dead participant. Abort: maybe it had voted yes, and we're aborting unnecessarily. Either way, you lose. In a system with 10 participants, the probability that all 10 are healthy and fast is 0.99^10. Roughly 90%. Ten percent of transactions see some failure. Scale that. Pain.

**Four: Not partition-tolerant.** Network split. Coordinator on one side. Participant on the other. Coordinator can't reach the participant. Participant can't reach the coordinator. Can't commit. Can't abort. Stuck. CAP says: in a partition, choose consistency or availability. 2PC chooses consistency. It blocks. Availability suffers. In a distributed system, partitions happen. Not often. But when they do, 2PC freezes. That's the trade-off. Strong consistency. Weak availability under failure. For many use cases, that's unacceptable. Especially in microservices. Especially when you have SLAs. "We need 99.99% availability." 2PC and partitions don't mix.

---

## Let's Walk Through the Diagram

```
    COORDINATOR DIES AFTER PREPARE

    COORDINATOR          PARTICIPANTS
         |                    |
         |---- PREPARE ------>| A: vote YES, LOCK
         |---- PREPARE ------>| B: vote YES, LOCK
         |                    |
         |     💀 CRASH       |
         |                    |
         ✗                    | A: waiting... LOCK held
         gone                 | B: waiting... LOCK held
                              |
                              | BLOCKED. Forever? Or until
                              | timeout + manual recovery.
```

The diagram shows: one crash. Many blockers. No automatic escape. Recovery requires human or complex logic.

---

## Real-World Examples (2-3)

**Example 1: Banking lockup.** A payment coordinator died mid-2PC. Two banks. Both voted YES. Both holding fund reserves. Coordinator gone. Two hours. Manual escalation. Someone had to decide: commit or abort. Money stuck. Customers calling. Not fun.

**Example 2: E-commerce checkout.** 2PC across inventory, payment, order services. Payment service slow. 5 second response. Prepare phase: 5 seconds. Commit phase: another 5. Total: 10+ seconds for one checkout. Users abandon. Timeout. 2PC killed conversion.

**Example 3: Multi-datacenter.** Coordinator in DC1. Participants in DC2 and DC3. Network partition. DC1 can't reach DC2. Prepare sent. Some voted. Some didn't. Coordinator doesn't know. Block. Or guess. Guessing in finance is dangerous.

---

## Let's Think Together

**Why not just use 3PC?** Three-phase commit. It adds a "pre-commit" phase. The idea: if we all reach pre-commit, we're "safe"—even if the coordinator dies, participants can commit among themselves. Sounds good. Problem: in asynchronous networks, 3PC can still have edge cases. Partitions. Split brain. Some systems use it. But it's not a silver bullet. And it adds another round-trip. More latency. Trade-offs everywhere.

---

## What Could Go Wrong? (Mini Disaster Story)

A cloud provider offered "distributed transactions" across their DB services. 2PC under the hood. A customer ran it. High load. Coordinator overloaded. Started crashing. Randomly. Transactions blocked. Locks held for minutes. Cascading failures. Other transactions waited for those locks. System-wide stall. They disabled 2PC. Moved to SAGA. Lesson: 2PC scales poorly under failure. When the coordinator is weak, the whole system suffers.

---

## Surprising Truth / Fun Fact

Some databases use 2PC internally and hide it. PostgreSQL. MySQL with XA. You don't see the protocol. It just works. Because it's one database. One vendor. Controlled environment. Cross-service 2PC? Different story. Different teams. Different failures. That's when the pain shows.

---

## Quick Recap (5 bullets)

- **Blocking:** Coordinator dies → participants hold locks → stuck until manual recovery.
- **Performance:** Two round-trips, latency = slowest participant.
- **Availability:** Any participant failure can block the whole transaction.
- **Partitions:** Network split → coordinator can't decide → block or guess.
- **3PC** helps with blocking but has its own issues. No free lunch.

---

## One-Liner to Remember

**2PC is painful because one dead coordinator can freeze everyone. Locks held. No decision. No escape. Plan for it—or avoid 2PC.**

---

## Next Video

So what's the alternative? SAGA. No distributed locks. No blocking. Just a sequence of steps—and when one fails, you compensate. Step backward. Business-level undo. That's next. See you there.
