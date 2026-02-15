# Cross-Region Replication: Challenges

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Two libraries in different cities. Syncing their catalogs. Library A adds a new book. Sends update to Library B. Postal service is slow. Three-day delay. During those three days, both libraries have different catalogs. What if Library B also added a book in the same spot? Conflict. Which catalog wins? Cross-region replication = keeping data in sync across regions separated by significant network latency. And latency makes everything harder.

---

## The Story

**Latency.** Cross-region network: 50 to 200 milliseconds per round trip. US to EU. US to Asia. Can't avoid it. Physics. Synchronous replication? Every write waits for the remote region to acknowledge. 200ms added to every write. Unacceptable for most apps. Users won't wait. So we replicate asynchronously. Fast writes. Local region acknowledges. Replication happens in background. But: replication lag. For seconds—maybe minutes—regions have different data. Read your write? Maybe not in another region. Stale reads. Eventually consistent. The latency tax.

**Conflict resolution.** User updates email in US region. Same user updates email in EU region. Different values. Async replication. Both propagate. Conflict. Which email wins? Last-writer-wins? Merge? CRDTs? Application-level resolution? No perfect answer. Depends on data. Business rules. Wrong choice: lost updates. Confusion. User anger.

**Data sovereignty.** Some data must stay in specific regions. GDPR: EU data in EU. Can't replicate personal data to US without safeguards. Cross-region replication isn't just technical. It's legal. Compliance. Design for it.

---

## Another Way to See It

Think of two offices. Same company. Different cities. Shared document. Office A edits. Saves. Office B edits. Saves. When do they sync? Email? Next day? Real-time? Conflicts. "I added this." "I added that." Same cell. Merge? Overwrite? Cross-region replication is this at scale. With network delay. With millions of documents.

Or two chefs. Same recipe. Different kitchens. One adds salt. One adds sugar. Recipe syncs. Which version? Replication is easy when nobody writes. When everyone writes everywhere, conflicts. Resolution. Always.

---

## Connecting to Software

**Async replication:** Write to local region. Return success. Replicate to other regions in background. Low latency. But: eventual consistency. Read from another region? Might get stale data. Replication lag. Seconds to minutes. Design for it. Or: route users to home region. Read your write in same region. Accept staleness for cross-region reads.

**Conflict resolution:** LWW (last-writer-wins)—simple. Timestamps. Loses updates. Merge—combine. Complex. CRDTs—automatic merge for special data types. Application-level—business logic. "Inventory: sum the deltas." "Profile: most recent wins." Depends. Choose. Document. Test.

**Data sovereignty:** Know where data can live. EU users? Data in EU. Replicate to US? Maybe not. Or encrypt. Anonymize. Legal review. Cross-region isn't just engineering. It's compliance.

**Read-your-writes.** User writes in US. Immediately reads from EU. Might not see their write. Replication lag. Solutions: route reads to same region as writes for that user. Or accept eventual consistency for cross-region reads. Or use a system that offers strong consistency across regions—rare, expensive. Design for the lag. Or design around it.

---

## Let's Walk Through the Diagram

```
    CROSS-REGION REPLICATION FLOW

    [US Region]                          [EU Region]
    User writes email: "alice@us.com"    User writes email: "alice@eu.de"
           │                                      │
           │  Write acknowledged locally         │  Write acknowledged locally
           │  (fast)                             │  (fast)
           │                                      │
           └────────── Async replicate ──────────┘
                        (50-200ms lag)
                           │
                           ▼
                    CONFLICT
                    Two values. Same key.
                    Which wins? LWW? Merge? App?
```

Latency causes lag. Lag causes divergence. Divergence causes conflict. Resolution required.

---

## Real-World Examples (2-3)

**Example 1: DynamoDB Global Tables.** Multi-region. Async replication. Conflict: last-writer-wins. Uses precise timestamps. Good for many workloads. Not for financial ledgers. Or inventory with concurrent updates. Know the limits. Simple. Works.

**Example 2: Cassandra multi-dc.** Replication factor per datacenter. Writes to local DC. Replicate. Configurable consistency. One, quorum, all. Trade latency for consistency. Conflict: timestamps. Or custom merge. Used at scale. Netflix. Apple. Proven. Complex.

**Example 3: CouchDB.** Multi-master. Conflict detection. Stores both versions. Application resolves. Merge function. Flexible. But: application must handle. Not automatic. Design choice. Control vs. simplicity.

---

## Let's Think Together

**US region: user changes email to A. EU region: same user changes email to B. Async replication. What's the final email?**

Depends on conflict resolution. LWW: whichever write has later timestamp wins. Clock skew? Wrong one might win. Vector clock: partial order. Might keep both. Application merge: maybe concatenate? Probably not for email. Custom: "most recent by user action" — hard to define across regions. Common: LWW with logical timestamps. Or: route user to one region. Sticky. Reduce cross-region writes for same user. Avoid the problem. Prevention beats resolution.

---

## What Could Go Wrong? (Mini Disaster Story)

A company replicated user data US ↔ EU. Conflict: last-writer-wins. One day: US region had a bug. Wrote default values for 10,000 users. "email: null." Replicated to EU. Overwrote good data. LWW: US "won" because those writes were "later." Data loss. Lesson: conflict resolution isn't just "which user wrote last?" It's "which write is correct?" Bad data can "win." Validate. Sanity check. Or: don't replicate everything. Some data: single region. Replicate only what needs global access. Reduce conflict surface. And impact of bugs.

---

## Surprising Truth / Fun Fact

CAP theorem: in a partition, choose consistency or availability. Cross-region: the network is the partition. Always. Long latency. Packet loss. Partitions happen. So cross-region systems are inherently AP or CP with failover. You can't have strict consistency and low latency across regions. Physics. Accept eventual consistency. Or accept limited availability during partitions. This is why cross-region is hard. Not implementation. Fundamentals.

---

## Quick Recap (5 bullets)

- **Cross-region latency:** 50-200ms per round trip. Async replication = fast writes, eventual consistency, lag.
- **Conflict resolution:** LWW, merge, CRDTs, application-level. No perfect answer. Choose for your data.
- **Data sovereignty:** GDPR, etc. Some data must stay in region. Replication has legal limits.
- **Replication lag:** regions have different data for a window. Design for staleness. Route users. Or accept.
- **CAP:** cross-region = partition likely. Consistency vs. availability. Trade-off is fundamental.

---

## One-Liner to Remember

**Cross-region replication: latency causes lag, lag causes conflict. Replicate async. Resolve conflicts. Respect sovereignty. Physics and law both apply.**

---

## Next Video

That's our journey through retries, circuit breakers, fault tolerance, timeouts, health checks, graceful degradation, load shedding, deadlocks, distributed locks, multi-region, and cross-region replication. The resilience toolkit. What topic should we cover next? Let us know. See you there.
