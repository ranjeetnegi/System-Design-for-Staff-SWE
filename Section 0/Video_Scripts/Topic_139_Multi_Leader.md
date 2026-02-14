# Multi-Leader Replication: When and Problems

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Two newspaper editors. Delhi and Mumbai. Both can publish headlines independently. No waiting. No approval from the other. Editor A: "India wins!" (cricket). Editor B: "India loses!" (different match). When they sync, both headlines exist. Different stories. Fine. But what if both editors change the SAME headline? "Breaking: PM speaks at 5 PM." Delhi edits to "5:30 PM." Mumbai edits to "6 PM." Sync. Conflict. Which version wins? That's multi-leader replication. Great for availability. Terrible for conflicts. Let me show you when to use it—and how to survive the conflicts.

---

## The Story

**Multi-leader** means multiple nodes can accept writes independently. No single leader. Each "leader" serves its region, its clients, its data center. Writes go to the nearest leader. Replication happens in the background. Between leaders. Async. When network is good: smooth. When partition happens: each leader keeps accepting. Great availability. When partition heals: conflicts. Same key. Different values. Different timestamps. Which wins?

**When used:** Multi-datacenter (each DC has its own leader—low latency for local writes). Offline clients (each device is a leader—sync when online). Collaborative editing (Google Docs—each user's edits go to a "leader" that merges). The common thread: you need writes to succeed locally. You can't afford to round-trip to a central leader. Latency or disconnection makes single-leader impractical. Multi-leader trades complexity for responsiveness. Acceptable when the alternative is worse.

**The problem:** Write conflicts. Same data. Two leaders. Two writes. No coordination. When they sync: merge? Overwrite? Ask user? The resolution strategy defines the system. Get it wrong and you lose data. Get it right and you have a powerful, available architecture. The conflict resolution is not an afterthought. It's the core design decision for multi-leader. Plan it first.

---

## Another Way to See It

Two chefs. Same recipe book. Both can edit. Chef A adds "salt to taste." Chef B adds "no salt." Same line. Different edits. When they combine the books: conflict. Do you merge? "Salt to taste, or no salt—chef's choice"? Do you pick one? Do you ask a third chef? Multi-leader is powerful. But conflict resolution is the hard part. Design it before you need it.

---

## Connecting to Software

**Conflict resolution strategies:** (1) **Last-write-wins (LWW):** Timestamp. Latest wins. Simple. But older write is lost. Data loss. And watch out: clock skew can make "latest" wrong. Two servers, different times? The wrong one might "win." (2) **Merge:** Combine both. For some data types—lists, sets—merge works. Add from A, add from B. Union. Works for shopping carts. Works for tags. (3) **Custom logic:** Application decides. Present both to user. "You have two versions. Pick one." User resolves. Slower. But correct. (4) **CRDTs:** Conflict-free replicated data types. Math guarantees merge. No user intervention. Complex to implement. But automatic when it works. Choose based on your data and your tolerance for loss.

**Systems:** Cassandra (multi-DC), CouchDB (offline sync), DynamoDB Global Tables (multi-region). Each has conflict handling. Understand it before you rely on it.

---

## Let's Walk Through the Diagram

```
    MULTI-LEADER: CONFLICT

    Leader A (Delhi)          Leader B (Mumbai)
    ┌─────────────────┐      ┌─────────────────┐
    │ Edit: "5:30 PM"  │      │ Edit: "6 PM"    │
    │ timestamp: T1    │      │ timestamp: T2    │
    └────────┬────────┘      └────────┬────────┘
             │                        │
             └──────────┬─────────────┘
                        │
                        ▼  Sync. Conflict!
                 ┌─────────────────┐
                 │ Same key.       │
                 │ Two values.     │
                 │ Resolve: LWW?   │
                 │ Merge? Custom?  │
                 └─────────────────┘
```

The diagram shows: two writes. One key. Sync. Collision. Resolution is not automatic. You design it. LWW loses data. Merge saves both. Custom gives control. CRDT makes it automatic. Choose.

---

## Real-World Examples (2-3)

**Example 1: DynamoDB Global Tables.** Multi-region. Each region has a leader. Writes local. Replicate async. Conflict: LWW. Last writer wins. Simple. But be careful: clock skew can cause wrong "last" writer. Use with caution.

**Example 2: CouchDB.** Offline-first. Each device is a leader. Edit offline. Sync when online. Conflicts: application merge or user choice. Designed for it. **Example 3: Cassandra multi-DC.** Each datacenter can accept writes. Replicate between DCs. LWW by default. Or application-managed timestamps. Scale globally. Conflict is the cost. Cassandra's design says: we optimize for writes. Multi-DC writes mean conflicts. You'll get them. Have a strategy. Use timestamps. Use application versioning. Or accept that some updates might overwrite others. Know the trade-off before you deploy.

---

## Let's Think Together

Google Docs: two users edit the same paragraph simultaneously. How is this different from multi-leader replication?

It IS multi-leader. Each user's edits go to a backend. Operational transformation (OT) or CRDTs merge them. No "last writer wins." They combine. "User A typed X. User B typed Y." Both appear. Order preserved. Conflict resolved by merge—character by character. Collaborative editing is multi-leader with sophisticated merge. Same problem. Different solution. Docs uses OT. Some systems use CRDTs. Both avoid "pick one, lose the other."

---

## What Could Go Wrong? (Mini Disaster Story)

A company ran multi-leader across three regions. LWW. User updated profile in Region A. Clock skewed. Region B's "last write" had an older timestamp but was processed later. Region B's stale data "won." Overwrote Region A's correct update. User's phone number reverted to old. Support calls. Confusion. They fixed: use logical timestamps (version vectors). Or avoid LWW for critical data. Lesson: LWW is simple until clocks lie. Multi-leader + LWW + bad clocks = data loss. Design carefully.

---

## Surprising Truth / Fun Fact

CRDTs (Conflict-free Replicated Data Types) are mathematical structures that always merge. No conflict. Add to a set from two leaders? Both adds appear. Union. Delete from two leaders? Both deletes apply. The math guarantees convergence. Invented by Shapiro and others. Used in Riak, Redis (some structures), and collaborative editing. Elegant. But not all data types have a CRDT. Text? Complex. Numbers? Tricky. Research continues. CRDTs are the "holy grail" of multi-leader—when they exist for your use case.

---

## Quick Recap (5 bullets)

- **Multi-leader:** Multiple nodes accept writes. Great for multi-DC, offline, collaborative editing.
- **Problem:** Write conflicts. Same key, different leaders, different values.
- **Resolution:** LWW (simple, data loss), Merge (combine), Custom (app decides), CRDTs (auto-merge).
- **When to use:** Need availability and local writes. Accept conflict resolution complexity.
- **Google Docs** = multi-leader with OT/CRDT-style merge. Same concept, sophisticated resolution.

---

## One-Liner to Remember

**Multi-leader: Two editors, one story. Both publish. Sync brings conflict. Design resolution before it happens. Merge, don't just overwrite.**

---

## Next Video

Next: **What is consensus?** Five friends. One restaurant. Everyone must agree. Some aren't responding. Consensus = getting distributed nodes to agree on one value. Why it's hard. The algorithms that solve it. See you there.
