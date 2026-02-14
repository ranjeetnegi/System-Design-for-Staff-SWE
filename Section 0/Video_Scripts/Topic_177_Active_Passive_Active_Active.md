# Active-Passive vs Active-Active (High Level)

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Two restaurants owned by the same chef. Active-Passive: Restaurant A is open, serves food. Restaurant B is closed but fully set up, ready to open if A burns down. Only one serves at a time. Active-Active: both restaurants are open. Both serve food simultaneously. If one burns down, the other absorbs the extra customers. Active-passive = standby. Active-active = both working. Different designs. Different trade-offs.

---

## The Story

**Active-Passive:** Primary handles all traffic. Secondary is idle. Or warm standby—replicated data, maybe occasional sync. Normal operation: one does the work. Failover: when primary fails, traffic switches to secondary. 30 seconds. A few minutes. Brief disruption. Simpler to build. Less to go wrong. But: wasted resources. Secondary does nothing in normal times. And failover takes time. Users notice.

**Active-Active:** Both regions serve traffic simultaneously. Load distributed. US users → US region. EU users → EU region. Or round-robin. Both working. If one fails, the other absorbs. No "switchover." Just more load on the survivor. Zero-downtime feel. Better utilization. Both regions earn their keep. But: complex. Data replication. Conflict resolution. Same user, two regions, concurrent updates. What's the truth? Hard problems.

---

## Another Way to See It

Think of a backup generator. Active-passive: generator sits idle. Power fails. Switch. Generator kicks in. Brief darkness. Active-active: solar panels and grid both feed the house. Both working. Grid fails? Solar continues. No switch. Seamless. Different design. Different cost.

Or two pilots. Active-passive: one flies, one monitors. Copilot takes over if captain incapacitated. Active-active: both flying—autopilot and human. Redundant systems. Overkill for a restaurant. Normal for a plane. Depends on criticality.

---

## Connecting to Software

**When active-passive:** Simpler requirements. Acceptable failover time (minutes). Budget conscious. Many enterprises. Database with replica. Primary serves. Replica waits. Failover: promote replica. Done. Proven. Well understood.

**When active-active:** Global users. Zero-downtime requirement. Latency-sensitive—write in local region. High availability. Willing to invest in complexity. Replication. Conflict resolution. Consistency models. Worth it when the business demands it.

**The conflict problem:** Active-active means writes in multiple regions. User in US updates profile. User in EU (same user, different session?) updates profile. Both regions have different data. Replication runs. Conflict. Which wins? Last-writer-wins? Merge? CRDTs? Application resolution? This is the hard part. Active-passive avoids it—only one writer. Active-active embraces it—and must solve it.

**Sticky routing.** One way to reduce conflicts: route the same user to the same region. User's first request hits US. All subsequent requests go to US. Writes in one place. No cross-region conflict for that user. Simplifies a lot. But: user travels? User uses VPN? Might hit different region. Design for both. Sticky reduces conflicts. Doesn't eliminate them.

---

## Let's Walk Through the Diagram

```
    ACTIVE-PASSIVE                     ACTIVE-ACTIVE

    [Primary] ── ALL traffic            [Region A] ── 50% traffic
    [Standby] ── idle                   [Region B] ── 50% traffic
         │                                   │
         │  Primary fails                    │  One fails
         ▼                                   ▼
    Failover. Switch to standby.       Other absorbs. No switch.
    Brief disruption.                  Zero-downtime feel.
    Wasted standby.                   Both working. Complex.
```

Left: one active. Simple. Failover delay. Right: both active. Complex. Seamless failover.

---

## Real-World Examples (2-3)

**Example 1: DynamoDB Global Tables.** Active-active. Multi-region replication. Write in any region. Replicates to others. Conflict: last-writer-wins. Timestamps. Simple. Good enough for many use cases. True active-active. Writes everywhere.

**Example 2: Traditional RDS.** Primary in one region. Standby in another. Active-passive. Primary serves. Standby replicates. Failover: promote standby. 1-2 minutes. Many companies. Proven. Simpler than active-active.

**Example 3: Cassandra multi-datacenter.** Write to local DC. Replicates to others. Eventually consistent. Active-active. Reads and writes in any DC. Conflict resolution: timestamps, or application logic. Used for scale. Trades consistency for availability and latency.

---

## Let's Think Together

**Active-active: user in US writes to US region. User in EU writes to EU region. Same data updated. Conflict! How to resolve?**

Options: (1) Last-writer-wins (LWW)—timestamps. Simple. Can lose updates. (2) Merge—combine non-conflicting fields. Complex. (3) CRDTs—data structures that merge automatically. Good for some types. (4) Application-level—business logic decides. E.g., "profile updates: most recent wins. Inventory: decrement both, resolve manually." (5) Avoid—route same user to same region. Sticky routing. Reduces conflicts. No single answer. Depends on data type. Consistency needs. Choose and document.

---

## What Could Go Wrong? (Mini Disaster Story)

A team went active-active. Two regions. Writes in both. Conflict resolution: last-writer-wins by timestamp. Seemed fine. Then: clock skew. US server clock 2 seconds ahead of EU. US write: 10:00:02. EU write: 10:00:01. LWW picked US. But EU write was actually later in real time. User in EU made the change. Got overwritten. Confusion. "I changed it. Why did it revert?" Lesson: LWW with clock skew is dangerous. Use logical timestamps. Vector clocks. Or application version numbers. Never rely on wall-clock for conflict resolution across regions. Clocks lie.

---

## Surprising Truth / Fun Fact

Many "active-active" systems are actually "active-passive with fast failover." Both regions have app servers. But only one has the primary database. The "passive" region has a read replica. Writes go to primary. Failover: promote replica. Switch DNS. A few minutes. True active-active—writes in both regions—is rarer. Harder. DynamoDB Global Tables, Cassandra, some others. Most companies: active-passive with good automation. Good enough for 99.99%.

---

## Quick Recap (5 bullets)

- **Active-passive:** primary serves, standby waits. Failover switches. Simpler. Wasted standby.
- **Active-active:** both regions serve. Both handle writes. Complex. Conflict resolution required.
- **When active-passive:** simpler, acceptable failover time.
- **When active-active:** global users, zero-downtime, latency-sensitive. Worth the complexity.
- **Conflict resolution:** LWW, merge, CRDTs, application logic. Clock skew danger with LWW.

---

## One-Liner to Remember

**Active-passive: one works, one waits. Active-active: both work. Standby vs. dual-write. Simplicity vs. zero downtime.**

---

## Next Video

Next: **Cross-Region Replication**—the challenges. Latency. Conflicts. Data sovereignty. What makes it hard. Stay tuned.
