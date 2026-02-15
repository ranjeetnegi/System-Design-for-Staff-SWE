# Three-Phase Commit: Why Is It Rarely Used?

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Imagine you're at a wedding. The priest asks: "Do you take this person?" Everyone says "Yes." Then—*poof*—the priest faints before saying "I now pronounce you." Are you married? Are you not? Nobody knows. And nobody can move forward. That's the nightmare of distributed transactions. Today: why three-phase commit tried to fix this—and why almost nobody uses it.

## The Story

Let's talk about two-phase commit first. You've got a coordinator and several participants—maybe a database, a message queue, and a cache. The coordinator says: "Prepare? Can everyone do this?" Everyone replies: "Yes, I'm ready." Coordinator says: "Commit!" Everyone does it. Done. Simple.

But here's the disaster. What if the coordinator **crashes** after "Prepare" but before "Commit"? Participants said yes. They're holding locks. They're waiting. But the coordinator is gone. They can't commit—they need the go-ahead. They can't abort—someone might have already committed. They're **blocked**. Indefinitely. Until someone manually intervenes. That's the 2PC blocking problem.

Three-phase commit tries to fix this. It adds a **third phase**: Pre-commit.

```
Phase 1: PREPARE    → Coordinator: "Can you do it?" Participants: "Yes"
Phase 2: PRE-COMMIT → Coordinator: "We're about to commit. Hold tight."
Phase 3: COMMIT     → Coordinator: "Go!" Everyone commits.
```

If the coordinator crashes after pre-commit, participants now **know** the intent. They were about to commit. They can use timeouts: "If I don't hear back, and everyone else pre-committed, I'll commit." They're not stuck. They can proceed independently. Sounds better, right?

## Another Way to See It

Think of it like a group project. **2PC**: Teacher asks "Are you done?" Everyone says yes. Teacher says "Hand it in." If the teacher leaves before saying "Hand it in," no one knows whether to hand it in or not. **3PC**: Teacher adds "I'm about to tell you to hand it in—get ready." Now if the teacher leaves, everyone knows: we were about to hand it in. We hand it in.

The extra phase gives participants *information* so they're not blind when the coordinator disappears.

## Connecting to Software

In real systems, 2PC is used everywhere: XA transactions, JTA in Java, database distributed transactions. The coordinator is usually your application server or transaction manager. Participants are databases, message brokers, etc. When the coordinator fails between prepare and commit, you need recovery logs, manual intervention, or timeouts. It's painful but manageable.

3PC was designed in the 1980s to avoid that blocking. The idea: make the protocol *non-blocking* so participants can decide on their own if the coordinator vanishes. In theory, it's elegant. In practice, it rarely shows up. Why? Because the assumptions it makes about the world—reliable failure detection, no partitions—don't hold in real distributed systems. Engineers learned that the hard way.

## Let's Walk Through the Diagram

```
     COORDINATOR          PARTICIPANT A      PARTICIPANT B

  1. PREPARE?  ----------->  (prepare)  ------>  (prepare)
     <--------- YES  ----  YES  <--------------- YES

  2. PRE-COMMIT ----------> (pre-commit) -----> (pre-commit)
     <--------- ACK  -----  ACK  <--------------- ACK

  3. COMMIT    -----------> (commit)    ------> (commit)
     <--------- DONE  -----  DONE  <--------------- DONE
```

In 2PC, if the coordinator dies after step 1, participants are stuck. In 3PC, if it dies after step 2, participants know: we're in pre-commit. We can time out and commit. No blocking.

## Real-World Examples (2-3)

- **Distributed databases** like CockroachDB and Google Spanner use consensus (Raft/Paxos), not 3PC. They solved the problem differently: replicated logs and leader election.
- **XA transactions** in Java and C# stick with 2PC. Recovery logs and timeouts handle coordinator failure.
- **Saga pattern** in microservices avoids distributed transactions altogether: local transactions + compensating actions. Order service creates order. Payment service charges. Inventory service reserves. If any step fails, run compensating transactions (refund, release inventory). No 2PC or 3PC. No coordinator. Eventually consistent, but simpler to operate.

## Let's Think Together

Here's a question: **If 3PC adds safety and removes blocking, why does the industry prefer 2PC plus recovery logs over 3PC?**

Pause and think. What could go wrong with 3PC?

## What Could Go Wrong? (Mini Disaster Story)

Picture this. Your distributed database uses 3PC. One day, a network cable gets unplugged between two data centers. Now you have two islands: North and South. North thinks South is dead. South thinks North is dead. Some participants in North commit. Some in South abort. You've just violated atomicity. The whole point of the protocol is gone. **Network partitions.** That's the killer. 3PC assumes you can reliably detect failures. "Coordinator is down" vs "Coordinator is slow" vs "Network between me and coordinator is broken." In a partition, some participants might think the coordinator is dead. Others might think they're partitioned. You can end up with a split: some commit, some abort. **Consistency is lost.** 3PC is not safe under network partitions. And in distributed systems, partitions happen. So 3PC's main advantage—non-blocking—breaks down when you need it most.

Plus: more phases = more round-trips = higher latency. Every phase is a network round-trip. 3PC triples the coordination overhead. And here's the kicker: Raft and Paxos handle consensus better in practice. They don't need a coordinator that can vanish. They use leader election and replicated logs. The industry voted with its feet: 2PC plus recovery logs, or Raft/Paxos, or Sagas. 3PC stayed in the textbook.

## Surprising Truth / Fun Fact

The original 3PC paper is from 1982 by Skeen. It's elegant. It solves the blocking problem *in theory*. But the CAP theorem wasn't fully appreciated then. Today we know: you can't have consistency, availability, *and* partition tolerance. 3PC assumes perfect failure detection—which doesn't exist in a partition. That's why you'll see 2PC in production. You'll almost never see 3PC. It's a beautiful theoretical solution to a problem that, in the real world, gets solved differently: accept blocking and recover, or use consensus algorithms that don't need a coordinator, or avoid distributed transactions entirely with patterns like Sagas. The lesson: theory and practice don't always align. Know the theory. Build for reality.

---

## Quick Recap (5 bullets)

- 2PC blocks if the coordinator fails between prepare and commit—participants hold locks indefinitely
- 3PC adds a pre-commit phase so participants know the intent and can proceed with timeouts
- 3PC breaks under network partitions: you can't reliably distinguish "coordinator dead" from "network split"
- More phases = more latency; Raft/Paxos handle consensus better in practice
- The industry uses 2PC + recovery logs; 3PC remains a theoretical curiosity

## One-Liner to Remember

*3PC fixes 2PC's blocking—until a network partition proves you can't tell who's really dead.*

---

## Next Video

Up next: OpenID Connect vs OAuth—what's the difference between "who are you?" and "what can you do?" See you there.
