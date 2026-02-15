# Vector Clocks: Detecting Concurrent Events

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Two friends. Different cities. Both write diary entries. They don't talk. Their entries are concurrent—neither caused the other. Lamport timestamps would give both a number. But we can't tell if one caused the other or they're independent. Enter vector clocks. Each node keeps a counter for every node. [A:3, B:2, C:1]. Compare two vectors: did one happen before the other? Or were they concurrent? If every entry in V1 is <= V2 and at least one is strictly less, V1 happened before V2. Otherwise: concurrent. Conflict. The system knows. Can ask the user. Can merge. Let me show you how.

---

## The Story

**Vector clock** = array of counters. One per node. [A:0, B:0, C:0] initially. **On local event:** Increment your entry. [A:1, B:0, C:0]. **On send:** Attach the whole vector. **On receive:** Take element-wise max of your vector and the received vector. Then increment your entry. Merge, then bump. Same idea as Lamport. But we track everyone. Not just the max.

**Comparison:** V1 happened before V2 if: every entry in V1 is <= corresponding entry in V2, AND at least one is strictly less. V1 = [2,3], V2 = [3,3]. V1 < V2. A's events in V1 are a subset of V2. Causality. **Concurrent:** Otherwise. Neither vector dominates. V1 = [2,3], V2 = [3,2]. V1[A]=2 < V2[A]=3. But V1[B]=3 > V2[B]=2. No ordering. Concurrent. Conflict. Resolve it.

**Use:** Multi-leader replication. Two leaders write. Sync. Conflict? Vector clocks detect it. "These are concurrent. Merge or ask user." Dynamo (2007) used this for shopping cart. Last-write-wins loses data. Vector clocks detect conflicts. Present both. User chooses. Better.

---

## Another Way to See It

Think of version numbers per author. Document A by Alice: v1. Bob edits: v2. Alice edits again: v3. But if Alice and Bob edit in parallel? Alice has [A:2, B:0]. Bob has [A:1, B:1]. Neither is "newer." Both have info the other doesn't. Vector clocks capture that. Each dimension is a "version" per node. Full picture. Concurrency visible.

---

## Connecting to Software

**Rules:** Local event: V[i]++ (your index i). Send: attach V. Receive: V = element_wise_max(V, V_received); V[i]++. Three rules. Same structure as Lamport. Richer state.

**Conflict detection:** Two writes. Same key. Vector V1 and V2. Compare. If V1 < V2: V2 wins. V2 has all of V1's causal history and more. If V2 < V1: V1 wins. If concurrent: conflict. Save both. Merge. Or LWW as fallback (loses data). Vector clocks give you the choice.

**Real systems:** Dynamo paper (2007). Amazon's original design. Shopping cart. Vector clocks for conflict detection. Riak. Version vectors. Same idea. Modern DynamoDB evolved. Vector clocks can grow large. One entry per node. 1000 nodes? 1000 entries per write. Scaling issue. Hybrid logical clocks. Simpler. Trade-offs.

---

## Let's Walk Through the Diagram

```
    VECTOR CLOCK COMPARISON

    V1 = [A:2, B:3]    V2 = [A:3, B:2]

    V1 < V2?  V1[A]=2 <= V2[A]=3 ✓
              V1[B]=3 <= V2[B]=2 ✗  (3 > 2)
    No. Not before.

    V2 < V1?  V2[A]=3 <= V1[A]=2 ✗  (3 > 2)
    No. Not before.

    ⇒ CONCURRENT. Conflict. Resolve.

    V1 = [A:2, B:2]    V2 = [A:3, B:3]
    Every V1 <= V2, and 2<3. ⇒ V1 < V2. V2 dominates.
```

The diagram shows: element-wise compare. All <= and at least one < ⇒ before. Otherwise ⇒ concurrent.

---

## Real-World Examples (2-3)

**Example 1: Amazon Dynamo (2007).** Shopping cart. Multi-datacenter. Writes can conflict. Vector clocks track causal history. Concurrent writes? Vector clocks differ. No dominant. System returns both. "Your cart has milk (from DC1) and eggs (from DC2)." Application merges. User sees both. No silent overwrite.

**Example 2: Riak.** Distributed key-value store. Version vectors. Conflict resolution. Read returns multiple versions if concurrent. Application decides. Or use CRDTs for automatic merge. Vector clocks are the detection. Resolution is separate.

**Example 3: Cassandra.** Does NOT use vector clocks by default. Uses timestamps. LWW. Simpler. But conflicts can lose data. Cassandra offers "row-level conflict" with custom logic. Vector clocks are an option in some designs. Trade-off: correctness vs. complexity.

---

## Let's Think Together

V1 = [A:2, B:3]. V2 = [A:3, B:2]. Is V1 before V2? V2 before V1? Or concurrent?

Concurrent. V1 before V2 requires: V1[A]<=V2[A] and V1[B]<=V2[B], with at least one strict. V1[A]=2<=3 ✓. V1[B]=3<=2 ✗. No. V2 before V1 requires: V2[A]<=V1[A] and V2[B]<=V1[B]. V2[A]=3<=2 ✗. No. Neither dominates. Concurrent. Both have causal info the other doesn't. A's events in V1 go to 2. In V2 to 3. B's: 3 in V1, 2 in V2. Crossed. Independent. Conflict. Resolve.

---

## What Could Go Wrong? (Mini Disaster Story)

A system used vector clocks. 500 nodes. Each write: 500 integers. Metadata exploded. Each key had a 500-dimensional vector. Storage. Network. Unmanageable. They moved to hybrid logical clocks (HLC). Single timestamp. Bounded size. Sacrificed full concurrency detection for some cases. But scaled. Lesson: vector clocks don't scale to huge clusters. One entry per node. Consider HLC. Or LWW with synced clocks. Or CRDTs. Vector clocks are correct. But expensive at scale.

---

## Surprising Truth / Fun Fact

DynamoDB evolved beyond vector clocks. The original Dynamo paper (2007) used them. But as Amazon scaled, vector size grew. DynamoDB today uses simpler approaches. Last-write-wins. Hybrid logical clocks in some cases. The idea survives in Riak, in research, in systems that need precise conflict detection. But production at massive scale often simplifies. Vector clocks: correct, expensive. Design for your scale.

---

## Quick Recap (5 bullets)

- **Vector clock** = one counter per node. Tracks causal history per node.
- **Rules:** Local: increment yours. Send: attach. Receive: max + increment yours.
- **Compare:** V1 < V2 if all V1 <= V2 and one strict. Else: concurrent.
- **Use:** Conflict detection. Multi-leader. Present both. User or app resolves.
- **Scaling:** Vector size = node count. Large clusters = problem. HLC, LWW alternatives.

---

## One-Liner to Remember

**Vector clocks: Each node tracks every node. Compare: before, or concurrent? Concurrency = conflict. Resolve. Or merge.**

---

## Next Video

That's our deep dive into consensus, leader election, heartbeats, gossip, clocks, and logical time. From Paxos to vector clocks. The foundations of distributed systems. What topic should we cover next? Let us know in the comments. See you there.
