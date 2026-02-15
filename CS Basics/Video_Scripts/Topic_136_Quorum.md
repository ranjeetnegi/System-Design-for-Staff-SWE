# Quorum: Why Majority Matters

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A committee of five judges. To pass a verdict, you need majority. At least three out of five must agree. Two judges vote yes. Two vote no. One is absent. No verdict. You need that third vote. Now: two judges are absent. Three remain. They vote. Three is majority of five. Verdict passed. But if three are absent? Only two remain. Two is not majority of five. They cannot decide. That rule—majority—is a **quorum**. In distributed systems, it's the same. You need more than half to agree. Why? It prevents chaos. It prevents split-brain. Let me show you the math.

---

## The Story

**Quorum** is the minimum number of nodes that must agree for an operation to succeed. Usually: **majority**. More than half. For N nodes, quorum = floor(N/2) + 1. Five nodes? Quorum = 3. Three nodes? Quorum = 2. Seven nodes? Quorum = 4. The formula ensures: any two quorums MUST overlap. If you need 3 out of 5, and I need 3 out of 5, we can't both "win" without at least one node in common. That overlap is the key. It guarantees: only one side of a partition can form quorum. Split-brain impossible.

For reads and writes: **Write quorum (W)** nodes must ack a write. **Read quorum (R)** nodes must be queried. If W + R > N, then at least one node in the read set saw the write. You read the latest. Guaranteed. Common setup: N=3, W=2, R=2. Tolerates 1 failure. N=5, W=3, R=3. Tolerates 2 failures. The math is elegant. Simple. Powerful.

---

## Another Way to See It

Think of a group of friends planning a trip. Five friends. Decision rule: majority must agree. Three say "beach." Two say "mountains." Beach wins. Now they split into two groups at the airport. Group A: three friends. Group B: two friends. Group A can make decisions—they have majority. Group B cannot—two is not majority of five. They must wait for Group A or reconnect. Same with nodes. Partition 3-2? Only the side with 3 has quorum. Only that side can elect a leader. Decide. Write. The side with 2 is stuck. By design.

---

## Connecting to Software

**Quorum for N nodes:** floor(N/2) + 1. Memorize it. **Write quorum W, Read quorum R:** W + R > N ensures read-your-writes. Why? Write hits W nodes. Read hits R nodes. Sets overlap (because W + R > N). So at least one read node has the write. You see it.

**Common configurations:** N=3, W=2, R=2. One failure tolerated. N=5, W=3, R=3. Two failures. N=5, W=1, R=5. Fast writes, slow reads. N=5, W=5, R=1. Slow writes, fast reads. Trade-offs. Cassandra uses tunable quorum. DynamoDB uses majority. etcd uses Raft—majority for everything. The principle is the same: overlap. Agreement. No split-brain.

---

## Let's Walk Through the Diagram

```
    QUORUM: MAJORITY WINS

    N=5 nodes. Quorum = 3.

    ┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐
    │ 1 │ │ 2 │ │ 3 │ │ 4 │ │ 5 │
    └───┘ └───┘ └───┘ └───┘ └───┘

    Write: Need 3 acks. Write to 1,2,3. ✓

    Partition: [1,2] | [3,4,5]
    Left: 2 nodes. No quorum. Cannot write.
    Right: 3 nodes. Quorum. Can write.
    Only one side can proceed. Safe.

    W=2, R=2, N=3: W+R=4 > 3.
    Read overlaps write. Always see latest.
```

The diagram captures it: partition splits nodes. Only the majority side has quorum. Only that side proceeds. The minority waits. Or stays read-only. No conflict. No split-brain. Math does the work.

---

## Real-World Examples (2-3)

**Example 1: Cassandra.** You set consistency level per request. QUORUM = majority. Write with QUORUM, read with QUORUM. Guaranteed to see your writes. Or ONE for speed—but then you might not see latest. Tunable. You choose.

**Example 2: etcd.** Uses Raft. Every write needs majority. Leader replicates to followers. Majority acks = committed. No quorum = no commit. Simple. CP. **Example 3: Kafka.** ISR (In-Sync Replicas). Leader + replicas. Message committed when all in ISR ack. Or when majority ack—configurable. Same idea: overlap. Agreement. Kafka's design ensures: once a message is committed, it's replicated to enough brokers that you won't lose it. The quorum of brokers that acked forms your durability guarantee. Lose fewer than that many brokers? Your data is safe. That's quorum in action for a message broker.

---

## Let's Think Together

Five nodes. W=3, R=3. Two nodes crash. Can you still write? Can you still read?

Write: Need W=3 acks. Three nodes remain. You can write to all three. ✓ Yes. Read: Need R=3 responses. Three nodes remain. You can read from all three. ✓ Yes. You tolerate up to 2 failures (N/2 for N=5, minus 1). With 2 crashed, 3 remain. Quorum is 3. You're exactly at the limit. One more crash? Down to 2. No quorum. Cannot write. Cannot guarantee read. System degrades. That's the failure tolerance: (N-1)/2 for N odd. Or N/2 - 1 for even. Roughly: half minus one.

---

## What Could Go Wrong? (Mini Disaster Story)

A team set N=4, W=2, R=2. W+R=4, not greater than N. Edge case. Partition 2-2. Both sides can get W=2. Both write. No overlap guarantee. Conflicting writes. Split-brain at the data level. They thought "quorum" meant "some nodes." It means "majority." W and R must each be majority, or W+R > N with care. They fixed: N=5, W=3, R=3. Proper quorum. No more conflicts. Lesson: quorum math is precise. Get it wrong, you get split-brain.

---

## Surprising Truth / Fun Fact

The word "quorum" comes from Latin: "of whom." As in "of whom we need a minimum present to do business." Parliaments used it for centuries. Can't pass laws without enough members. Same logic in distributed systems. Can't commit writes without enough nodes. Old concept. New context. Still majority. Still overlap. Still the key to agreement.

---

## Quick Recap (5 bullets)

- **Quorum** = minimum nodes to agree. Usually majority: floor(N/2) + 1.
- **W + R > N** ensures reads see latest writes. Overlap guarantee.
- **Common:** N=3, W=2, R=2 (1 failure). N=5, W=3, R=3 (2 failures).
- **Partition:** Only majority side has quorum. Prevents split-brain.
- **Tolerance:** Can lose up to (N-1)/2 nodes and still operate (for odd N).

---

## One-Liner to Remember

**Quorum: Need more than half to decide. Two halves of a partition can't both have majority. That's why it works.**

---

## Next Video

Next: **BASE.** ACID is a strict boarding school. BASE is a flexible startup. Different rules. Different trade-offs. Most of the internet runs on BASE. Why? See you there.
