# Network Partition: What Happens When the Link Fails?

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Family reunion. Grandma in house A. Grandkids in house B. The two houses are connected by a single road. Dinner is at 6. Everyone knows. Then a tree falls. The road is blocked. Grandma can't reach the kids. The kids can't reach Grandma. They're both fine. But they can't communicate. Grandma doesn't know if the kids are safe. The kids don't know if dinner is ready. Each house continues. Independently. But they're cut off. That's a network partition. In distributed systems, it's not a rare event. It's inevitable. Let me show you what happens.

---

## The Story

A **network partition** is when the network fails between parts of a distributed system. The parts can't talk. Can't exchange data. Can't agree. Important: it's not the same as a node crashing. In a partition, BOTH sides are alive. Both are running. Both are serving requests. They just can't reach each other. The link is broken. The wire is cut. The router failed. The data center is isolated.

What happens? Each side continues. Writes on one side stay on that side. Writes on the other side stay there. The data diverges. When the partition eventually heals—when the road is cleared—the two sides must reconcile. Which version of the data wins? What about conflicting updates? Merge? Overwrite? The partition creates the split. The healing creates the mess. Unless you've planned for it.

---

## Another Way to See It

Two islands. Each has a copy of the community ledger. Normally they send boats to sync. Storm hits. No boats for a week. Island A: someone gets married. Ledger updated. Island B: someone dies. Ledger updated. Both ledgers changed. Both are "correct" from their island's view. When the storm passes and boats run again: two different truths. Reconciliation is hard. That's the partition problem. Not the split. The merge.

---

## Connecting to Software

In software: two data centers. DC1 in Mumbai. DC2 in Delhi. Link between them fails. Routing issue. Fiber cut. Doesn't matter. DC1 and DC2 can't replicate. User in Mumbai updates profile on DC1. User in Delhi updates the same profile on DC2. Different updates. Different values. Both think they're correct. Partition heals. Now what? Last-write-wins? Merge? Application-level resolution? The design decision happens before the partition. Not after. Partition-tolerant systems plan for this. They have conflict resolution. Merge strategies. Vector clocks. CRDTs. Systems that don't plan—crash. Corrupt. Lose data. The difference between a resilient system and a fragile one is often: did you design for partition before it happened? Add conflict resolution to your checklist. Before production. Not after the first outage.

---

## Let's Walk Through the Diagram

```
    NETWORK PARTITION

    NORMAL:
    ┌─────────────┐  ◄────────────►  ┌─────────────┐
    │   DC1       │    replication   │   DC2       │
    │   Mumbai    │                  │   Delhi     │
    └─────────────┘                  └─────────────┘
           │                                │
           └────────── Both in sync ────────┘

    PARTITION (link fails):
    ┌─────────────┐       X        ┌─────────────┐
    │   DC1       │   (no route)   │   DC2       │
    │   Mumbai    │                │   Delhi     │
    │  Write: A   │                │  Write: B   │
    └─────────────┘                └─────────────┘
           │                                │
           └──── Diverging. Can't sync. ────┘

    HEALING: Must reconcile. Conflict resolution.
```

The diagram tells the story: normal = sync. Partition = divergence. Healing = conflict. Every distributed system that replicates must handle the middle picture. Not if. When.

---

## Real-World Examples (2-3)

**Example 1: AWS us-east-1 outage, 2011.** A network partition in a data center caused Elastic Load Balancers to misbehave. Some instances couldn't reach others. Partial failures. Cascading. Partition was the root cause. Systems that assumed "we can always talk" failed.

**Example 2: Multi-region database.** User in Asia updates. User in Europe updates same row. Network hiccup. Partition. Each region has different value. When link returns: merge or overwrite? DynamoDB, Cassandra—they have conflict resolution. Simple DB without it? Data loss or corruption.

**Example 3: Kubernetes cluster split.** Control plane in one network. Nodes in another. Partition. Nodes can't reach API server. They keep running existing pods. But no new deployments. No scaling. "Frozen" cluster. Partition causes operational blindness. Not crash. Stasis. The pods keep serving. But you've lost control. You can't roll out. Can't scale. Can't debug. The cluster is in a zombie state. When the partition heals, you might find conflicting state. Deployments that were requested during the partition. Pods that were killed. Reconciliation is the next challenge. Partition is just the beginning. Healing is when the real work starts.

---

## Let's Think Together

Two data centers. Partition happens. Users in DC1 update their profile—add phone number. Users in DC2 update the same profile—add address. Same user. Different fields. Partition heals. Which version wins?

If they updated different fields: merge. Combine phone + address. Easy. If they updated the SAME field differently: conflict. Name: "Rahul" vs "Rahul Kumar." Need a rule. Last-write-wins (timestamp)? Custom merge? Ask user? The answer is in your design. Before the partition. Design for conflict. Expect it. Handle it.

---

## What Could Go Wrong? (Mini Disaster Story)

A company ran two MySQL masters. One in each region. Replication between them. Network partition. Both accepted writes. Same account. User deposited in Region A. User's wife withdrew in Region B. Both succeeded. Replication lag. Partition. When it healed: negative balance. Overspent. The system wasn't designed for partition. It assumed the link was always there. One partition. Financial disaster. Lesson: if you replicate, assume partition. Design for it. Or use single-leader. Or accept read-only replicas. Multi-write without partition awareness = time bomb.

---

## Surprising Truth / Fun Fact

Network partitions are often **asymmetric**. One side might think the link is up (sends, gets no ack, retries). The other might know it's down. " split-brain" can result: both sides think they're fine but they're operating on diverged state. Detection is hard. TCP might hang. Applications might not notice for minutes. Designing for partition means: assume it's happened. Act accordingly. Don't wait for perfect detection.

---

## Quick Recap (5 bullets)

- **Partition** = network failure between parts. They can't communicate. Both sides alive.
- Not same as node crash. Partition = link broken. Crash = node dead.
- During partition: writes diverge. Each side has its own truth.
- When partition heals: must resolve conflicts. Merge, LWW, or custom logic.
- Design for partition before it happens. Conflict resolution. Merge strategies. Or single-leader.

---

## One-Liner to Remember

**Network partition: The road is blocked. Both houses are fine. They just can't talk. And when the road clears, they have two different stories to merge.**

---

## Next Video

Next: **Split-brain.** Two kings. One kingdom. Partition splits it. Both sides elect a new king. Now there are two. Giving different orders. Chaos. That's split-brain. Why it's dangerous. How to prevent it. See you there.
