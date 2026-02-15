# What Is Consensus? (Agreeing in Distributed Systems)

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Five friends. Deciding where to eat. Pizza? Sushi? Thai? One friend's phone died. Not responding. Another is stuck in traffic. Slow to reply. But they MUST agree on one restaurant before they go. One choice. Everyone committed. How do you get five people—with delays, dropouts, and different preferences—to agree on a single value? That's consensus. In distributed systems, it's the same problem. Nodes crash. Networks fail. Messages are delayed. No global clock. Yet the system must make a decision. One value. Everyone agrees. Let me show you how it works—and why it's one of the hardest problems in computing.

---

## The Story

**Consensus** is the process of getting all (or a majority of) nodes in a distributed system to agree on a single value. Even when some nodes are slow. Unreliable. Or unreachable. They must still decide. One outcome. Commitment. No ambiguity.

Why is it hard? Nodes crash. You don't know if they're dead or just slow. Networks fail. Messages arrive late. Or never. There's no global clock. "Happened before" is fuzzy. Yet you need: leader election (who's the boss?), transaction commit (did it succeed or not?), configuration change (new setting—apply or not?), distributed lock (who holds it?). All require consensus. All require agreement despite failure.

The impossibility result: the **FLP theorem** (Fischer, Lynch, Paterson) proves: in an asynchronous system with even one faulty node, consensus is theoretically impossible to guarantee. You can't always decide. In practice: we use timeouts. Probabilities. "Good enough" failure detection. We engineer around the impossibility. Paxos, Raft, ZAB—they don't violate FLP. They assume failure detector. They work in practice.

---

## Another Way to See It

Think of a jury. Twelve people. Must decide: guilty or not guilty. Unanimous? Or majority? They deliberate. Vote. Some jurors take longer. Some change their mind. But eventually—usually—they reach a verdict. One outcome. That's consensus. In distributed systems, the "jurors" are nodes. The "verdict" is the agreed value. The deliberation is the protocol. Paxos. Raft. Same idea. Different scale.

---

## Connecting to Software

**What needs consensus:** Leader election (who leads the cluster?), transaction commit (all nodes commit or all abort?), configuration (what's the current config?), distributed locks (who has the lock?). Any decision that must be global. That must be consistent across nodes. Consensus is the machinery.

**Algorithms:** **Paxos:** The classic. Theoretical. Correct. Hard to implement. Understand. **Raft:** Designed to be understandable. Same correctness. Clearer. Used by etcd, Consul, TiKV. **ZAB:** ZooKeeper Atomic Broadcast. ZooKeeper's protocol. Similar to Paxos. Purpose-built for ZooKeeper's use case. All achieve the same goal: agreement. Despite failures. Despite delays.

---

## Let's Walk Through the Diagram

```
    CONSENSUS: AGREE ON ONE VALUE

    Nodes must decide: value = X (or Y, or Z)
    ┌────┐  ┌────┐  ┌────┐  ┌────┐  ┌────┐
    │ N1 │  │ N2 │  │ N3 │  │ N4 │  │ N5 │
    └─┬──┘  └─┬──┘  └─┬──┘  └─┬──┘  └─┬──┘
      │       │       │       │       │
      └───────┴───────┴───────┴───────┘
                    │
              Exchange messages
              Propose, vote, commit
                    │
                    ▼
              All agree: value = X
              (or majority agrees)

    Challenges: N3 slow. N4 crashes. Messages delayed.
    Protocol still reaches agreement. Eventually.
```

The diagram shows: many nodes. One decision. Messages fly. Votes. Commitment. Despite faults. That's consensus. The protocol is the detail. The goal is simple: agree.

---

## Real-World Examples (2-3)

**Example 1: etcd.** Kubernetes uses it for cluster state. Consensus via Raft. Configuration changes. Leader election. All go through etcd. Without consensus: split-brain. With it: one truth. **Example 2: Kafka.** Topic partition leadership. Who is the leader for partition 5? Consensus (via ZooKeeper or KRaft). All brokers agree. **Example 3: PostgreSQL.** Not distributed consensus for data. But tools like Patroni use etcd for leader election. Consensus decides who is primary. Data replication follows.

---

## Let's Think Together

Three servers. Vote for a new leader. Server 1 votes for A. Server 2 votes for B. Server 3 hasn't responded yet. How do you decide?

You need a majority. With 3 nodes, majority = 2. Server 1 says A. Server 2 says B. No majority for either. You wait. For Server 3. Or for a timeout. If Server 3 votes A: A wins (2 votes). If Server 3 votes B: B wins. If Server 3 never responds: you're stuck. Or you assume Server 3 is dead. Remove it from the set. Now it's 2 nodes. Majority = 2. But 2-node cluster is fragile. One failure = no majority. In practice: use odd numbers. 3, 5, 7. And timeouts. "Server 3 didn't respond in 5 seconds. Proceed without it." Consensus in the real world uses time. FLP says we can't guarantee termination. Timeouts give us "good enough."

---

## What Could Go Wrong? (Mini Disaster Story)

A company built a custom consensus layer. "We don't need Raft. We'll do it ourselves." Bug: under partition, both sides could "commit" different values. Split-brain at the consensus layer. Data corruption. Two leaders. Conflicting configs. They switched to etcd. Raft. Battle-tested. Consensus is hard. Don't implement it yourself. Use a library. Use etcd, Consul, ZooKeeper. Let the experts handle the edge cases. Lesson: consensus has subtle failure modes. Use proven implementations.

---

## Surprising Truth / Fun Fact

Leslie Lamport created Paxos in 1989. He wrote it as a story about a fictional parliament on the island of Paxos. The parliament had to agree despite senators being in and out. The paper was legendary: hard to understand. He later wrote "Paxos Made Simple." Still not simple. Raft was created in 2014 specifically to be teachable. "In Search of an Understandable Consensus Algorithm." Same correctness. Clearer. Sometimes the best engineering is making the complex understandable. Raft succeeded. It's everywhere now.

---

## Quick Recap (5 bullets)

- **Consensus** = getting nodes to agree on one value despite crashes, delays, and network failures.
- **Used for:** Leader election, transaction commit, config changes, distributed locks.
- **FLP theorem:** In async system with one fault, consensus is impossible to guarantee. We use timeouts to work around.
- **Algorithms:** Paxos (complex), Raft (understandable), ZAB (ZooKeeper). All achieve agreement.
- **Don't implement yourself.** Use etcd, Consul, ZooKeeper. Consensus has subtle bugs. Use battle-tested code.

---

## One-Liner to Remember

**Consensus: Five friends, one restaurant. Phones die. Traffic delays. They must still decide. Same for distributed systems—agree despite chaos.**

---

## Next Video

Next up in our distributed systems series: we'll dive deeper into **Raft**—the consensus algorithm you can actually understand. How leaders are elected. How logs are replicated. The algorithm that powers etcd and so much more. See you there.
