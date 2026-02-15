# Paxos: The Idea (Not the Full Proof)

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A monk on a mountain peak raises a lantern. Far away, another monk sees the signal and nods. A third is asleep. A fourth's messenger pigeon never arrives. Yet they MUST agree. One date for the festival. One value. All committed. No second chances. This is Paxos. Monks on separate peaks. Pigeons that get lost. Sleepers who miss rounds. And the relentless need to agree on one thing. Let me show you how it works—and why it's beautiful, hard, and rarely used raw.

---

## The Story

**Paxos** solves the consensus problem: how do nodes agree on one value when messages fail, nodes crash, and nothing is reliable? Leslie Lamport designed it. The idea: two phases. **Phase 1: Prepare.** A proposer says: "I want to propose something. Here's my proposal number." Acceptors reply: "We promise not to accept any proposal older than yours." The proposer collects promises from a majority. **Phase 2: Accept.** The proposer sends the actual value. "Here's what we're agreeing on." If a majority of acceptors say yes, consensus is reached. Done.

Why is it hard? Multiple proposers can run at once. Proposer A sends value X. Proposer B sends value Y. Who wins? Paxos uses proposal numbers. Higher number wins. If an acceptor already promised to a higher number, it rejects the lower one. Lost messages? Retry. Node crashes mid-protocol? Others continue. The protocol handles all of these. That's its power. But the devil is in the details. Implementing it correctly is famously difficult. Subtle bugs hide in edge cases.

---

## Another Way to See It

Think of a parliament. Senators propose bills. They vote. But senators leave. New ones arrive. Votes get lost in the mail. Yet the parliament must pass exactly one law. Not two. Not zero. One. Paxos is that process. Proposers are senators with bills. Acceptors are the voting mechanism. The "promise" in Phase 1 is: "I won't vote for anything older than this." Phase 2 is the actual vote. Majority wins. The protocol survives senators leaving, votes arriving late, and new bills constantly appearing. Same idea. Different scale.

---

## Connecting to Software

**Roles:** **Proposer**—suggests a value. **Acceptor**—votes. Accepts or rejects. **Learner**—learns the final result. Doesn't vote. Just observes. In practice, a node can be all three. Or split. Design choice.

**Two phases.** Prepare: get promises. "Don't accept anything older than my number." Accept: send the value. Get majority approval. That's it. The genius is in handling overlaps. Two proposers. Lost messages. Crashes. The protocol still converges.

**Why nobody uses raw Paxos:** Too complex. Edge cases everywhere. Multi-Paxos (run Paxos multiple times, one per log slot) and Raft are practical. Raft was designed to be understandable. Same correctness. Clearer. Paxos is the theory. Raft is the practice.

---

## Let's Walk Through the Diagram

```
    PAXOS: TWO PHASES

    Phase 1: PREPARE (get promises)
    ┌─────────┐                    ┌─────────┐
    │Proposer │ ─── Prepare(n) ──► │Acceptors│
    │         │ ◄── Promise(n) ─── │  A B C  │
    └─────────┘    (majority says   └─────────┘
                    "we promise")
    
    Phase 2: ACCEPT (get agreement)
    ┌─────────┐                    ┌─────────┐
    │Proposer │ ─── Accept(v) ───► │Acceptors│
    │         │ ◄── Accepted ───── │  A B C  │
    └─────────┘    (majority says  └─────────┘
                    "we accept v")
    
    Result: Consensus on value v.
    Even if: pigeons lost, monks slept, another proposer tried.
```

The diagram shows: two clear phases. Prepare locks out old proposals. Accept delivers the value. Majority at each step. That's the core. Everything else is handling the chaos around it.

---

## Real-World Examples (2-3)

**Example 1: Chubby.** Google's distributed lock service. Uses Paxos-like consensus internally. Nearly every Google service relies on it. Locks. Leader election. Configuration. Paxos under the hood.

**Example 2: ZooKeeper.** Uses ZAB (ZooKeeper Atomic Broadcast). Similar to Paxos. Coordinated updates. Used by Kafka, HBase, Hadoop. The coordination pattern—agree despite failures—is Paxos-style.

**Example 3: Many systems say "Paxos" but use Multi-Paxos or variants.** Few run classic Paxos as written. They adapt it. Simplify it. Raft is often the implementation. The idea is Paxos. The code is Raft. Or ZAB. Or something else. The spirit lives on.

---

## Let's Think Together

Proposer A sends value X. Proposer B sends value Y. Simultaneously. Who wins?

Neither, at first. They might conflict. Proposer A gets promises from acceptors 1 and 2. Proposer B gets promises from 2 and 3. Acceptor 2 promised both? The one with the higher proposal number wins. If B's number is higher, B's prepare invalidates A's. A's accept might fail—acceptors reject because they promised B. B can then accept Y. If A's number was higher, A wins. The protocol uses numbers to order proposals. Higher number has priority. In the end, one value is chosen. Always. That's the guarantee.

---

## What Could Go Wrong? (Mini Disaster Story)

A team implemented Paxos from the paper. "We understand it." They didn't. Under a specific partition, two values could be "chosen" in different parts of the cluster. Split-brain at the consensus layer. Data corruption. They spent months debugging. Switched to etcd. Raft. Never looked back. Lesson: Paxos is correct. But implementing it correctly is a research project. Use a library. Use etcd, ZooKeeper, Consul. Don't build consensus from scratch. The monks had Lamport. You have etcd.

---

## Surprising Truth / Fun Fact

Leslie Lamport published Paxos in 1998 in a paper disguised as a story about a Greek island parliament. Reviewers didn't understand it. For years. The paper was rejected. Misunderstood. He had to rewrite it as "Paxos Made Simple" in 2001. Still not simple. But the idea endured. Same Lamport who invented LaTeX. Who won the Turing Award. Paxos is one of the most influential algorithms in distributed systems. And it started as a story about an island. Sometimes the best ideas need a good story to survive.

---

## Quick Recap (5 bullets)

- **Paxos** = two-phase consensus: Prepare (get promises), Accept (get agreement).
- **Roles:** Proposer (suggests), Acceptor (votes), Learner (learns result).
- **Why hard:** Multiple proposers, lost messages, crashes—Paxos handles all of them via proposal numbers.
- **Why rarely used raw:** Too complex to implement correctly. Multi-Paxos, Raft are practical.
- **Spirit lives on:** Chubby, ZooKeeper, etcd—all use Paxos-like consensus under different names.

---

## One-Liner to Remember

**Paxos: Monks on peaks. Pigeons that fail. One date everyone must agree on. Prepare for promises. Accept for agreement. Theory is beautiful. Implementation is brutal.**

---

## Next Video

Next: **Raft Leader Election.** A classroom with no teacher. Five students. Who becomes class representative? Majority votes. Random timeouts. No split-brain. The algorithm you can actually understand. See you there.
