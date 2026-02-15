# When "Eventually Consistent" Is Not OK

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

"Eventually" your parachute will open. "Eventually" the brakes will work. Some things CANNOT wait for "eventually." In software: bank balance. Inventory count. Access permissions. Payment status. If you revoke someone's admin access and it's "eventually" propagated... they might delete your production database in those 5 seconds of "eventually." Eventually consistent is a tool. A powerful one. But it's not the right tool for every job. And knowing when NOT to use it—that's Staff-level judgment.

---

## The Story

Imagine a library. One copy of a rare book. Two people reserve it online at the same time. The system is "eventually consistent." Both get confirmation. Both show up. One person gets the book. The other gets an apology. That's bad for a library. Now imagine it's not a book. It's a million dollars. Two withdrawal requests. Both approved. Both processed. The bank is "eventually consistent." You see the problem. Some data cannot be wrong for even a second. Money. Access. Inventory. Locks. The cost of staleness is too high. "Eventually" is fine when the worst case is a slightly old profile picture. "Eventually" is a disaster when the worst case is a security breach or a double-spend.

---

## Another Way to See It

Think of a traffic light. Green for you. Green for the car crossing your path. "Eventually" the system will realize there's a conflict. Eventually. After the crash. Traffic lights are STRONGLY consistent. Both directions cannot be green at the same time. The system waits. Coordinates. Ensures mutual exclusion. That's what strong consistency gives you. For traffic, there's no "eventually." For your bank balance, there shouldn't be either.

---

## Connecting to Software

**When eventual consistency is dangerous.** Four categories where "eventually" breaks everything:

**(1) Financial transactions.** Double-spend. User has Rs 1,000. Pays merchant A. Pays merchant B. Both read balance as Rs 1,000. Both deduct. Both succeed. User spent Rs 2,000 with Rs 1,000. If balance replication is eventual, you have a race. You need strong consistency. Single source of truth. Or distributed consensus. No "eventually" for money.

**(2) Inventory.** Overselling. Ten items in stock. Two customers order 10 each. Both read "10 available." Both get orders. You sold 20. You have 10. Backorders. Refunds. Anger. Inventory must be strongly consistent at checkout. Lock. Reserve. Deduct atomically.

**(3) Access control.** Admin revoked. Access removed in primary database. Replica in another region hasn't synced. Admin still has access for 5 seconds. In 5 seconds they can run `DROP TABLE users`. Permissions cannot be eventually consistent. Revocation must be immediate. Or as immediate as replication allows.

**(4) Distributed locks.** Two nodes think they hold the lock. Both proceed. Both modify. Data corruption. Locks require consensus. Strong consistency. There's no "eventually" for mutual exclusion.

**How to identify.** Ask: "What's the WORST that happens if this data is stale for 5 seconds?" If the answer involves money loss, security breach, data corruption, or safety risk—you need strong consistency. If the answer is "user sees slightly old data"—eventual is fine.

**Solutions.** Use strong consistency for critical paths: synchronous writes, consensus protocols (Raft, Paxos), single-writer patterns. Use eventual consistency for everything else: feeds, analytics, recommendations, cache. Mix them. Most systems do.

---

## Let's Walk Through the Diagram

```
WHEN TO USE STRONG vs EVENTUAL CONSISTENCY
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   STRONG CONSISTENCY (Never eventual)                            │
│                                                                  │
│   💰 Payments     ──► Double-spend risk. Must be exact.          │
│   📦 Inventory    ──► Oversell risk. Must reserve atomically.   │
│   🔐 Access       ──► Revoked user can still act. Security.     │
│   🔒 Locks        ──► Two nodes "hold" lock. Corruption.        │
│                                                                  │
│   EVENTUAL CONSISTENCY (OK)                                      │
│                                                                  │
│   📰 News feed    ──► Stale by 1 min? Fine.                      │
│   👤 Profile pic  ──► Old pic for 5 sec? Fine.                   │
│   📊 Analytics    ──► Approximate. Fine.                         │
│   🛒 Cart (temp)  ──► Merge on checkout. Fine.                   │
│                                                                  │
│   THE TEST: "Worst case if stale 5 sec?"                         │
│   Money/Security/Corruption → STRONG                             │
│   Inconvenience  → EVENTUAL                                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Draw a line. Left: things that cannot be wrong. Right: things that can wait. The line is the "5 second test." If 5 seconds of wrong data causes harm—strong consistency. If it causes annoyance—eventual. Staff engineers don't default to one. They reason from consequence.

---

## Real-World Examples (2-3)

**Amazon.** Shopping cart: eventually consistent. You add items on phone, see on laptop. Maybe a second of lag. Fine. Checkout inventory: strongly consistent. When you click "Place Order," they lock. Reserve. Deduct. No "eventually" at that moment. Different phases, different requirements.

**Google Docs.** Real-time collaboration. They use operational transforms and CRDTs. But the "save" moment—when you export or share—that's strongly consistent. You don't want "eventually" when sharing a final document. The live editing can be eventually consistent with conflict resolution. The finality cannot.

**AWS IAM.** When you revoke a user's permissions, that change propagates. But critical actions—deleting an S3 bucket, changing billing—use strong consistency. You can't have "eventually" for "does this user have delete permission?" The blast radius of a few seconds of wrong permission is unlimited.

---

## Let's Think Together

**"Shopping cart: eventually consistent. Inventory: strongly consistent. Payment: strongly consistent. Why the different choices?"**

Shopping cart is pre-commitment. You're browsing. Adding. Removing. No money has moved. If your cart on your phone shows 3 items and your laptop shows 2 for a few seconds—merge them. No harm. Inventory at browse time can be approximate. "Only 3 left!"—eventual is OK. But the moment you click "Buy," you're committing. Inventory must be locked. Deducted. Payment must be processed. Atomic. Both need strong consistency at that exact moment. The cart is a draft. The purchase is a contract. Different lifecycles. Different consistency requirements. Staff engineers understand the transition point. That's where you switch from eventual to strong.

---

## What Could Go Wrong? (Mini Disaster Story)

A company built a ticket-selling system. "First 500 tickets at early-bird price." They used eventual consistency for the counter. Five servers. Each had a local count. Sync every 10 seconds. At 10:00:00, 600 people clicked "Buy." Load balanced across 5 servers. Each server thought it had capacity. Each sold 100. Total: 500? No. 600. They oversold by 100. Customers showed up. No seats. Refunds. Lawsuits. Bad press. The fix: use a centralized, strongly consistent counter for ticket sales. Or: use a queue. One writer. Serialize the commits. "Eventually" for ticket inventory is a promise you cannot keep. The disaster was predictable. The requirement was wrong from the start.

---

## Surprising Truth / Fun Fact

CAP theorem says you can't have consistency, availability, and partition tolerance all at once. But in practice, "partition" means network failure. Most of the time, the network works. So most systems choose consistency + availability when the network is fine. They only sacrifice consistency during an actual partition. "Eventually consistent" is often a choice for performance, not because of CAP. You're trading read latency for write speed. Strong consistency often means: write waits for replication. Slower writes. Eventually consistent: write returns fast. Replicate later. Faster writes. Stale reads. The trade-off is often performance, not just CAP. Know why you're choosing.

---

## Quick Recap (5 bullets)

- **Eventually consistent is dangerous** for: money, inventory, access control, distributed locks.
- **The test:** "Worst case if stale 5 seconds?" Money/security/corruption → strong. Inconvenience → eventual.
- **Solutions:** Strong consistency for critical paths. Eventual for feeds, analytics, recommendations.
- **Shopping cart** can be eventual (pre-commitment). **Inventory at checkout** must be strong (commitment).
- **Access revocation** cannot be eventual. Revoked admin with 5 seconds of access = disaster.

---

## One-Liner to Remember

**If stale data for 5 seconds can cost money, breach security, or corrupt data—eventual consistency is not OK.**

---

## Next Video

Next: designing for partial failure. When one service is slow, the whole system doesn't have to fall. The domino checklist.
