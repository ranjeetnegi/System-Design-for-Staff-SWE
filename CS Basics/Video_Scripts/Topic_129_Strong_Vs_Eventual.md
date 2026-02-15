# Strong Consistency vs Eventual Consistency

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You're at the post office. You hand the clerk a letter. She stamps it. Drops it in the bag. "Confirmed. It's sent." You walk out KNOWING. No doubt. That's strong consistency. Now imagine you drop a letter in a street mailbox. No clerk. No stamp. No confirmation. It WILL get delivered. Probably today. Maybe tomorrow. You HOPE. But there's a window—hours, maybe a day—where you're not sure. That's eventual consistency. Same goal: letter arrives. Different certainty. Different speed. Same in software.

---

## The Story

Strong consistency is like the post office moment. You write. The system confirms. Instantly. Every read after that write returns the new value. No exceptions. If Server A gets your update, Server B and C get it too—before anyone can read. You never see stale data. You never get "I thought I saved that." Predictable. Safe. But slow. Because the system must coordinate. Wait. Confirm. Before it can respond.

Eventual consistency is the mailbox. You write. The system accepts. Fast. But it might take a moment—seconds, minutes—to reach all servers. During that window, someone might read the OLD value. Stale. Wrong. But eventually—if no new writes come in—all replicas will converge. They'll all show the new value. Given enough time. "Eventually" means: not now, but soon. Probably. The key question: how long is "eventually"? For a well-designed system: seconds. For a stressed system across continents: maybe minutes. You trade certainty for speed. Know your "eventually" window. Design for it.

---

## Another Way to See It

Think of a group chat. Strong consistency: you send "Meeting at 3 PM." The system buffers. Waits. Makes sure every participant's app has received it. Then it shows "sent." Slow but everyone sees it at the same moment. Eventual consistency: you hit send. Your app shows "sent" immediately. But your colleague's app might show it 2 seconds later. Fast for you. Slightly delayed for them. Both valid. Different trade-offs.

---

## Connecting to Software

**Strong consistency:** After a write, ALL reads return the new value. Immediately. No stale reads. Achieved by: synchronous replication (leader waits for followers), consensus protocols, single leader. Cost: latency. Throughput. Availability during failures.

**Eventual consistency:** After a write, reads MIGHT return old value for a while. But they will EVENTUALLY return the new one. Achieved by: asynchronous replication, multi-leader, read-from-replica. Benefit: fast writes, high availability, scales easily. Cost: temporary inconsistency.

Use cases matter. Bank balance? Strong. Wrong balance = wrong money. Social media likes? Eventual. 999,987 vs 1,000,000 for a few seconds? Nobody dies. Shopping cart? Often eventual. Payment? Strong. Always. The rule of thumb: if wrong data can cause financial, legal, or safety harm, choose strong. If the worst case is a user refresh or a slightly stale number, eventual is fine. Your domain defines your consistency requirement.

---

## Let's Walk Through the Diagram

```
    STRONG vs EVENTUAL

    STRONG CONSISTENCY:
    User ──► Write ──► [Leader] ──► Wait for all replicas ──► "Done"
                                    │
                                    ├── Replica 1 ✓
                                    ├── Replica 2 ✓
                                    └── Replica 3 ✓
    Read anywhere → Always gets NEW value. Slow but correct.

    EVENTUAL CONSISTENCY:
    User ──► Write ──► [Leader] ──► "Done" (immediately!)
                                    │
                                    └── Replicas sync in background (async)
    Read from Replica 2 (not synced yet) → OLD value. Fast but stale.
    Read after a few seconds → NEW value. Eventually correct.
```

Strong: wait, confirm, then respond. Eventual: respond fast, sync later. The diagram captures the difference: one path is linear, blocking. The other is fire-and-forget. Both have a place.

---

## Real-World Examples (2-3)

**Example 1: Bank transfer.** You transfer Rs 10,000. The system MUST deduct from your account and add to the recipient's—atomically. Strong consistency. No "eventually." The moment you see "transfer complete," it's done. Everywhere. Banks use strong consistency. No choice.

**Example 2: Instagram likes.** A post hits 1 million likes. Does every user need to see exactly 1,000,000 at the same instant? No. 999,987 is fine. 1,000,012 is fine. A few seconds of drift? Acceptable. Instagram uses eventual consistency for counts. Scale demands it.

**Example 3: Amazon product catalog.** Product name, price, description. Updates propagate. Might take minutes. During that time, some users see old price. Rare. Acceptable. But checkout and payment? Strong. You don't charge the wrong amount. Catalog: eventual. Money: strong. Same company. Different consistency for different operations. That's the pattern: match the guarantee to the consequence of being wrong.

---

## Let's Think Together

Instagram post gets 1 million likes. Does every user need to see EXACTLY 1,000,000 at the same instant?

Think about it. User A in Mumbai. User B in New York. Do they need the same count, to the digit, in real time? For a like count—no. It's a vanity metric. A few thousand off for a few seconds? Nobody notices. Nobody cares. Eventual consistency wins. Fast. Cheap. Good enough.

But what about a "limited to 100" flash sale? First 100 buyers get a discount. Now you need accuracy. Strong consistency. Otherwise: 150 people "win." Chaos. Context matters. Always.

---

## What Could Go Wrong? (Mini Disaster Story)

A ticket-selling platform uses eventual consistency for seat availability. Two users see "1 seat left" on the same flight. Both add to cart. Both pay. Both get confirmation. The system eventually syncs. Realizes: we sold 2 seats. We have 1. One customer gets "sorry, overbooked." After payment. Refund. Complaint. Lawsuit. The company learned: inventory and payment need strong consistency. Eventual is fine for "trending now." Not for "last ticket."

---

## Surprising Truth / Fun Fact

Amazon's DynamoDB offers both. You choose per read: "consistent read" (strong) costs 2x the "eventually consistent read" in capacity units. Same database. Same data. You pay more for certainty. That's the real trade-off in one product: double the cost for strong consistency. Most reads on DynamoDB are eventual. Because most use cases don't need strong. When they do, you flip a parameter. Design is choice.

---

## Quick Recap (5 bullets)

- **Strong consistency:** After write, ALL reads return new value. Safe, predictable, slower.
- **Eventual consistency:** After write, reads might return old value briefly; they'll eventually converge.
- **Strong:** Banks, payments, inventory. **Eventual:** Likes, feeds, catalogs.
- Trade-off: Strong = coordination, latency. Eventual = speed, scale, temporary staleness.
- Same system can use both for different operations (e.g., catalog eventual, payment strong).

---

## One-Liner to Remember

**Strong consistency: Post office stamp. You know it's sent. Eventual: Mailbox drop. Hope it arrives. Pick based on what you can't afford to get wrong.**

---

## Next Video

Next: **CAP theorem.** You can have a car that's cheap, fast, or reliable. Pick two. Same with databases: Consistency, Availability, Partition tolerance. Pick two. Why? See you there.
