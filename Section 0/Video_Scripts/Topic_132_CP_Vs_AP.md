# CP vs AP: How to Choose in Practice

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Two doctors. Same clinic. Dr. CP always gives the CORRECT diagnosis. But sometimes she says "I need more tests. Come back tomorrow." You wait. You get the right answer. Dr. AP always sees you immediately. No waiting. But sometimes she says "probably just a cold" when it's actually flu. You get fast service. Not always accurate. Which doctor do you want for a chest pain that could be a heart attack? Dr. CP. Which for a mild headache? Dr. AP is fine. Same logic applies to databases. CP or AP. The choice depends on what you're building. Let me show you how to decide.

---

## The Story

**CP systems** prioritize correctness. When in doubt, they refuse. "I can't reach enough nodes. I won't serve. Try again." ZooKeeper, etcd, HBase, Spanner. Use them when wrong data is unacceptable: config management, leader election, financial transactions, inventory counts. Better to be down than wrong.

**AP systems** prioritize availability. When in doubt, they serve. "Here's what I have. Might be stale. But here you go." Cassandra, DynamoDB (in default mode), DNS. Use them when stale data is acceptable: shopping carts, social feeds, session stores, analytics. Better to be slightly wrong than unavailable.

Most systems aren't purely CP or AP. They're on a spectrum. You tune consistency per operation. Read from leader = stronger. Read from replica = weaker. Write with quorum = stronger. Write with one = weaker. The art is knowing which operation needs which.

---

## Another Way to See It

Think of a GPS. **CP approach:** "I don't have a satellite lock. I won't show you a location." Correct. No wrong direction. But useless when you're lost. **AP approach:** "Here's my best guess from last known position." Might be wrong. Might send you the wrong way. But you have something. For turn-by-turn driving? You want CP—wrong direction is dangerous. For "roughly where am I?" AP is fine. Context defines the choice.

---

## Connecting to Software

**CP systems in practice:** ZooKeeper (config, locks, elections). etcd (Kubernetes config). HBase (strong consistency for analytics). Spanner (Google's globally distributed DB). MongoDB in majority-write mode. Use for: who is the leader? What's the current config? Did this transaction commit? How many items in stock?

**AP systems in practice:** Cassandra. DynamoDB eventually consistent reads. CouchDB. Riak. DNS. Use for: user's shopping cart (can merge), social feed (stale is ok), session data (worst case: re-login), click analytics (approximate is fine).

**The spectrum:** PostgreSQL with synchronous replication = CP. PostgreSQL with async replication = moving toward AP. Redis single node = CP. Redis Cluster with read replicas = tunable. You're rarely "all CP" or "all AP." You're "this operation needs CP, that one can be AP." A single application might use CP for checkout and AP for product recommendations. Same stack. Different guarantees for different operations. That's mature distributed system design.

---

## Let's Walk Through the Diagram

```
    CP vs AP: WHERE THEY LIVE

    ┌────────────────────────────────────────────────────────────┐
    │  CP SIDE (Correct or Nothing)                              │
    │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
    │  │ ZooKeeper   │ │   etcd      │ │   Spanner   │           │
    │  │ Leader elect│ │ K8s config  │ │  Financials │           │
    │  └─────────────┘ └─────────────┘ └─────────────┘           │
    └────────────────────────────────────────────────────────────┘
                            │
                            │  SPECTRUM
                            │  (most systems are here)
                            ▼
    ┌────────────────────────────────────────────────────────────┐
    │  AP SIDE (Always Respond)                                  │
    │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
    │  │ Cassandra   │ │ DynamoDB    │ │    DNS      │           │
    │  │ Shopping    │ │ Session     │ │  Caching    │           │
    │  │ cart, feed  │ │ stores      │ │             │           │
    │  └─────────────┘ └─────────────┘ └─────────────┘           │
    └────────────────────────────────────────────────────────────┘
```

The diagram shows: it's not binary. Systems sit on a spectrum. And within one system, different operations can lean CP or AP. E-commerce: catalog reads AP, payment CP, cart AP. One app. Multiple consistency needs.

---

## Real-World Examples (2-3)

**Example 1: Kubernetes.** etcd holds cluster state. CP. Wrong config = wrong pods, wrong routing. Disaster. They choose consistency. During partition, etcd might refuse writes. Cluster degrades. But no incorrect state.

**Example 2: Netflix.** Recommendation engine. Slightly stale? User gets "maybe you'll like this" that's a day old. Fine. AP. Session data. User's "continue watching"? Stale for 30 seconds? Re-sync. AP. Billing? CP. You don't charge twice or show wrong amount.

**Example 3: Amazon.** Product catalog: AP. Reviews: AP. Shopping cart: AP (merge conflicts ok). Payment: CP. Order confirmation: CP. One company. Many consistency levels.

---

## Let's Think Together

E-commerce system. Three operations: **Product catalog reads.** AP or CP? AP. Stale product name or description for a few seconds? User refreshes. No big deal. **Payment processing.** AP or CP? CP. Wrong amount? Double charge? Refund the wrong person? Never. **User reviews.** AP or CP? AP. Review count 998 vs 1000? Doesn't matter. Order of reviews slightly wrong? Fine. The pattern: money and correctness-critical = CP. Everything else = often AP. Ask: what's the cost of stale? If it's low, lean AP. If it's high, lean CP.

---

## What Could Go Wrong? (Mini Disaster Story)

A team built an inventory system for a warehouse. "We need it fast. AP." During a sale, 1000 users see "5 items left." All add to cart. All checkout. AP meant each node served its local count. No coordination. 800 orders. 5 items. Catastrophic oversell. Refunds. Angry customers. Lost trust. They switched to CP for inventory. Slower. But correct. Lesson: inventory is a correctness problem. AP was the wrong choice. Know your domain.

---

## Surprising Truth / Fun Fact

DynamoDB lets you choose per request. `ConsistentRead: true` costs 2x read capacity. Same table. Same data. You pay for certainty. Most applications use eventual reads (AP) for 90% of traffic. They flip to strong (CP) only for critical paths: checkout, account balance, profile update. One database. Two modes. Design is about using the right mode at the right time.

---

## Quick Recap (5 bullets)

- **CP systems:** Correct or nothing. ZooKeeper, etcd, Spanner. Config, elections, money, inventory.
- **AP systems:** Always respond. Cassandra, DynamoDB, DNS. Carts, feeds, sessions, analytics.
- Most systems are on a **spectrum**—tune consistency per operation.
- Rule of thumb: money, safety, correctness-critical = CP. Speed, scale, best-effort = AP.
- Same app can use both: catalog AP, payment CP. Match the tool to the need.

---

## One-Liner to Remember

**CP or AP? Ask: What's worse—wrong data or no data? Wrong = CP. No = AP. Then tune per operation.**

---

## Next Video

Next: **Consistency models.** Linearizability. Causal. Sequential. What do these words mean? The whiteboard in a meeting room vs a group chat. Different strengths. Different costs. See you there.
