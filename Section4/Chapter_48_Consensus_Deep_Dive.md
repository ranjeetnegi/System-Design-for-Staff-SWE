# Chapter 48: Consensus Deep Dive — Raft & Paxos, Step by Step

> Consensus is the bedrock of every distributed system that promises consistency: etcd,
> ZooKeeper, Chubby, Spanner, CockroachDB, TiKV. It is mentioned in dozens of chapters
> but rarely explained mechanically. This chapter builds the intuition from absolute zero —
> what "consensus" means in plain English — and then climbs, step by step, through Paxos,
> Multi-Paxos, and Raft until you can trace every message in a leader election or a log
> replication round without looking anything up.

---

## Why This Chapter Matters

At an L5 interview you can say "we use etcd for leader election." At an L6 interview the
follow-up question is immediate: "Walk me through what happens when the etcd leader crashes.
Which messages are exchanged? What makes it safe to elect a new leader? What if the cluster
is partitioned?" Saying "Raft handles that" is not enough. This chapter gives you the
mechanical understanding to answer every follow-up.

---

## Part 1: The Consensus Problem — What Are We Trying to Solve?

### 1.1 Starting From Plain Language

Imagine a committee of five people trying to agree on a single candidate for president.
The rules are simple: everyone casts a vote, and whoever gets the majority wins. If the
meeting is held in person, this is trivial. But now imagine the five committee members
are in different cities, communicating only by postal mail. Letters can be delayed for
days, lost entirely, or arrive out of order. Some members might fall asleep mid-vote and
never respond. Some might even lie (Byzantine scenario, which we'll set aside for now).
Under these conditions, can the committee still always agree on exactly one president,
without waiting forever?

That is the consensus problem, restated for distributed computers.

In the computer version, the "committee members" are servers (or processes). The "vote"
is a value each server wants to agree on (could be "who is the leader," "what is the
next command to execute," or "is this transaction committed"). The "postal delays" are
network delays. The "falling asleep" is a server crash.

Formally, a consensus protocol must satisfy three properties:

**Agreement**: No two non-faulty processes decide on different values. If server A decides
"the leader is X," server B cannot decide "the leader is Y."

**Validity**: The agreed-upon value must have been proposed by some process. The servers
cannot agree on a value that nobody suggested.

**Termination**: Eventually, every non-faulty process decides on some value. The protocol
cannot run forever without an answer.

The tricky part is achieving all three simultaneously when messages can be delayed and
servers can crash.

### 1.2 Why It Is Hard — Three Concrete Scenarios

**Scenario 1: Message delay looks like a crash.** Server A sends a message to Server B.
B receives it and sends back a reply. But the reply is delayed for 60 seconds. From A's
perspective, has B crashed, or is the network just slow? A cannot tell the difference.
If A assumes B crashed and proceeds without B, it might contradict a decision B already
made.

**Scenario 2: Duplicate messages.** A sends a "commit" message to B. The network
delivers it twice. If B naively processes it twice, it might apply the same operation
twice, corrupting state.

**Scenario 3: Split decisions.** Five servers try to elect a leader. At the same
moment, Server A gets votes from B and C (a majority). Server E gets votes from D and
a delayed vote from C (which C sent before hearing from A). Now A and E both think they
are leader. This is split-brain, and it is catastrophic.

These scenarios are not hypothetical. Real production incidents happen because of them.
The consensus problem is about systematically preventing all three even in the worst
possible network conditions.

### 1.3 FLP Impossibility — The Fundamental Limit

In 1985, three researchers — Fischer, Lynch, and Paterson — proved something
surprising: in a purely asynchronous distributed system (one where there are no bounds
on message delivery time), it is impossible to guarantee consensus even if only one
process can fail.

The intuition behind FLP: if you cannot put any bound on how long a message might take
to arrive, you can never distinguish a crashed process from a very slow one. The protocol
gets stuck waiting for a reply that might come in one millisecond or might never come.
There is always a "bad execution" where the adversary delays messages just long enough to
prevent the protocol from terminating.

This sounds like a death sentence for distributed systems. If consensus is impossible,
how does etcd work?

### 1.4 The Practical Escape: Timeouts

The escape from FLP is to add timing assumptions. Real networks are not perfectly
asynchronous. Messages usually arrive within some reasonable bound. If a process does
not respond within that bound, we assume it has crashed.

This is the timeout. It is a lie — maybe the process is just slow — but it is a
useful lie. By introducing timeouts, we leave the purely asynchronous model and enter a
partially synchronous model, where consensus becomes solvable.

The cost: sometimes you declare a process dead when it is actually alive (a false
positive timeout). This causes brief disruptions (a new leader is elected, the old one
is fenced out) but the system recovers. The safety properties — agreed-upon values are
never contradicted — are still maintained. Only the liveness guarantee (the protocol
eventually terminates) temporarily breaks down during the false timeout period.

Every real consensus protocol — Paxos, Raft, ZAB, Viewstamped Replication — implicitly
relies on this assumption. The papers describe the protocols as if they work in
asynchronous systems for simplicity, but the actual implementations all have timeouts.

### 1.5 Replicated State Machines — Why We Need Consensus

The reason we care about consensus is replicated state machines. Here is the core idea.

A state machine is any system that starts in some state and transitions to a new state
when it receives a command. A key-value store is a state machine: it starts empty, and
each "set x = 5" or "delete y" is a command that transitions it to a new state.

A replicated state machine runs the same state machine on N servers. If all N servers
start in the same initial state and apply the same commands in the same order, they will
always be in the same state. This gives you fault tolerance: if one server crashes, the
others have the exact same state and can continue serving requests.

The problem: how do you ensure all N servers apply the same commands in the same order?
This is precisely the consensus problem. The "value to agree on" at each step is "which
command comes next in the log."

```
REPLICATED STATE MACHINE ARCHITECTURE
======================================

Client Write: "set x = 5"
        |
        v
+-------+-------+    AppendEntries    +---------------+
|   LEADER      |  ----------------> |  FOLLOWER 1   |
|               |                    |               |
| Log:          |  ----------------> |  Log:         |
| [1] set a=1   |    (replicate)     | [1] set a=1   |
| [2] del b     |                    | [2] del b     |
| [3] set x=5   |                    | [3] set x=5   |
+---------------+                    +---------------+
        |
        |         AppendEntries    +---------------+
        +------------------------> |  FOLLOWER 2   |
        |                          |               |
        |                          | Log:          |
        |                          | [1] set a=1   |
        |                          | [2] del b     |
        |                          | [3] set x=5   |
        |                          +---------------+
        |
        v
  When majority (e.g., 3/5) ack entry [3]:
  entry [3] is COMMITTED
  All servers apply "set x=5" to their state machine
  All state machines reach the same state
```

The key insight: consensus guarantees that all replicas apply log entries in the same
order. The state machine determinism then guarantees all replicas reach the same state.
Together, these give you a reliable, consistent, distributed key-value store (or
distributed lock, or distributed counter — any state machine).

### Brainstorming: The Consensus Problem

**Q: Why can't we just use a primary-backup setup without a consensus protocol? The
primary sends writes to all backups. If the primary crashes, promote a backup. Done.**

The primary-backup approach sounds simple but hides the consensus problem inside it.
How does the system decide which backup to promote when the primary crashes? You need all
surviving nodes to agree on the same new primary. If they do not agree, you get two
primaries (split-brain), each accepting writes, and the data diverges.

Furthermore, during the promotion process, you need to determine which backup has the
most up-to-date data. The crashed primary might have sent some writes to some backups
but not others. Figuring out which writes are "real" — i.e., which writes the client
considers committed — requires consensus reasoning even if you do not call it that.

Paxos and Raft make this reasoning explicit and provably correct. Primary-backup systems
that skip formal consensus tend to have subtle bugs that surface under network partition
scenarios, which are exactly the conditions where correctness matters most.

**Q: What does "majority quorum" mean and why is majority sufficient (rather than
requiring all N nodes to agree)?**

A majority quorum means more than half of the nodes: in a 5-node cluster, a majority is
3. The mathematical property that makes majority sufficient is: any two majorities must
overlap by at least one node. In a 5-node cluster, if one majority is {A, B, C} and
another majority is {B, C, D}, they share B and C.

This overlap property is what ensures consistency. If one set of nodes agreed on value
V1, and another set tries to agree on value V2, the overlapping node knows about V1 and
will prevent V2 from being chosen (via the protocol's voting rules). You do not need all
N nodes to agree; you just need a majority to make a decision, secure in the knowledge
that any future majority will include at least one node that witnessed the old decision.

Requiring all N nodes would mean that a single crashed node blocks all progress, which
defeats the purpose of having replicas. With a majority quorum and N = 2F+1 nodes, you
can tolerate F failures and still make progress.

**Q: The FLP result seems to say consensus is impossible. Does this mean distributed
databases are theoretically unsound?**

The FLP result applies to a very specific model: purely asynchronous systems where
processes can crash and message delays are unbounded. Real systems operate in a
partially synchronous world. Networks usually deliver messages within some bound. This
is the key word: usually. Not always — there are network storms, GC pauses, and
overloaded switches. But usually.

Paxos and Raft handle the "usually" case and degrade gracefully in the unusual case.
During a period of severe asynchrony (network storm), the cluster might temporarily fail
to elect a leader (liveness breaks). But once the network recovers, the protocol
converges and the safety properties — committed data is never lost or contradicted —
were maintained the entire time. This is the right trade-off for most real systems. The
alternative — sacrificing safety for liveness — would mean risking data corruption,
which is far worse than temporary unavailability.

---

## Part 2: Paxos — The Original Consensus Protocol

### 2.1 The Setting and the Cast

Paxos was developed by Leslie Lamport and published in 1998 (though the original paper
circulated since 1989). It is the grandparent of all modern consensus protocols.
Understanding Paxos — even imperfectly — gives you the conceptual vocabulary for
everything else.

Paxos has three roles. In a real implementation, the same physical process can play
multiple roles, but it helps to think of them separately.

**Proposer**: The process that wants to get a specific value agreed upon. Think of the
Proposer as a client who wants a group decision. It initiates the protocol.

**Acceptor**: The voter. Acceptors receive proposals and decide whether to accept them.
A majority of Acceptors accepting the same value means consensus is reached. The safety
of Paxos rests entirely on Acceptor behavior.

**Learner**: The observer. Learners learn the decided value so they can act on it. In a
key-value store, the Learner is the component that actually applies the decided command
to the state machine.

In most implementations: the Leader plays Proposer, all replicas play Acceptors, and all
replicas also play Learners.

### 2.2 Phase 1: Prepare and Promise

Paxos runs in two phases. Phase 1 is the "reservation" phase.

The Proposer picks a proposal number n. This number must be unique and higher than any
proposal number it has used before. Then:

**Step 1a (Prepare)**: The Proposer sends a Prepare(n) message to a majority of
Acceptors. This message says: "I want to make a proposal with number n. Please promise
not to accept any proposal with a number lower than n."

**Step 1b (Promise)**: Each Acceptor that receives Prepare(n) responds with Promise(n)
if n is greater than any proposal number it has promised before. The Promise means:
"I agree not to accept any proposal numbered below n." The Acceptor also includes in
its response the highest-numbered proposal it has already accepted (if any), along with
the value of that accepted proposal.

If the Acceptor has already promised a higher number to someone else, it rejects the
Prepare message.

```
PAXOS PHASE 1: PREPARE AND PROMISE
=====================================

Proposer (wants to propose "v=5")
    |
    | Prepare(n=7)
    |-------------> Acceptor 1 (promised n<=5)
    |                   |  Promise(n=7, accepted=(6,"v=3"))
    |                   |<-----------
    |
    | Prepare(n=7)
    |-------------> Acceptor 2 (promised n<=4)
    |                   |  Promise(n=7, accepted=null)
    |                   |<-----------
    |
    | Prepare(n=7)
    |-------------> Acceptor 3 (promised n<=3)
    |                   |  Promise(n=7, accepted=null)
    |                   |<-----------
    |
    | (majority of 3 responded with Promise)
    |
    | Proposer sees: Acceptor 1 had accepted (6,"v=3")
    | Proposer MUST propose "v=3" (not "v=5")
    | This is the key safety rule
    v
  Phase 2 begins
```

Notice the critical rule: if any Acceptor reports a previously accepted value, the
Proposer MUST propose that value in Phase 2, not the value it originally wanted. This
is how Paxos ensures that previously agreed-upon values are never overridden.

### 2.3 Phase 2: Accept and Accepted

**Step 2a (Accept)**: The Proposer sends Accept(n, v) to a majority of Acceptors, where
v is either:
- The value from the highest-numbered accepted proposal it received in Phase 1 responses,
  or
- The Proposer's own desired value, if no Acceptor reported a previously accepted value.

**Step 2b (Accepted)**: Each Acceptor that receives Accept(n, v) accepts the proposal
if n is at least as large as the highest proposal number it has promised. When it
accepts, it sends Accepted(n, v) to all Learners (and also back to the Proposer).

When a majority of Acceptors have sent Accepted(n, v) for the same n and v, the value v
is chosen. Consensus is reached.

```
PAXOS PHASE 2: ACCEPT AND ACCEPTED
=====================================

Proposer (has received majority Promises, must propose "v=3" due to Phase 1)
    |
    | Accept(n=7, v="v=3")
    |-------------> Acceptor 1
    |                   |  Accepted(n=7, v="v=3")
    |                   |<---------- (also sent to Learners)
    |
    | Accept(n=7, v="v=3")
    |-------------> Acceptor 2
    |                   |  Accepted(n=7, v="v=3")
    |                   |<----------
    |
    | Accept(n=7, v="v=3")
    |-------------> Acceptor 3
    |                   |  Accepted(n=7, v="v=3")
    |                   |<----------
    |
    | (majority accepted n=7 with v="v=3")
    |
    v
  VALUE "v=3" IS CHOSEN

Learner receives Accepted(n=7, v="v=3") from majority:
  -> applies "v=3" to state machine
```

### 2.4 The Safety Argument — Why Two Proposals Cannot Conflict

The heart of Paxos safety is this: if value v was accepted by a majority in round n,
any proposal in a higher-numbered round n' will also propose v.

Here is the proof sketch. Suppose v was accepted by a majority M1 in round n. Now a new
Proposer runs Phase 1 with proposal number n' > n. Phase 1 requires a response from a
majority M2. Since M1 and M2 are both majorities, they must overlap — at least one
Acceptor, call it A, is in both M1 and M2.

When A responds to the new Proposer's Prepare(n'), it reports the accepted value from
round n (which is v). The Proposer's Phase 1 response includes this (n, v) pair. Since
n is the highest-numbered accepted proposal the Proposer sees, it is forced to propose v
in Phase 2. So the new round also proposes v. By induction, every future round proposes
v. Consensus is maintained.

This is elegant. The quorum overlap — the mandatory intersection of any two majorities —
is doing all the safety work.

### 2.5 A Concrete Example With Five Acceptors

Let us trace through a concrete scenario with 5 Acceptors, showing how Paxos handles
a concurrent Proposer.

```
Scenario: Two Proposers compete. Proposer P1 wants to commit "A".
          Proposer P2 wants to commit "B".
          5 Acceptors: Acc1, Acc2, Acc3, Acc4, Acc5.

TIME 0: P1 sends Prepare(n=1) to Acc1, Acc2, Acc3 (majority)
        All three promise. None have accepted anything.
        P1 receives Promises from Acc1, Acc2, Acc3.

TIME 1: P2 sends Prepare(n=2) to Acc3, Acc4, Acc5 (majority)
        All three promise (n=2 > n=1, so they override their promise).
        (Note: Acc3 now promised n=2, which voids its promise of n=1 to P1.)

TIME 2: P1 sends Accept(n=1, v="A") to Acc1, Acc2, Acc3.
        Acc1 accepts (n=1 >= promised n=1 for Acc1). -> Accepted(1,"A")
        Acc2 accepts (n=1 >= promised n=1 for Acc2). -> Accepted(1,"A")
        Acc3 REJECTS (n=1 < promised n=2). -> returns rejection.
        P1 got only 2 accepts (not majority of 5). "A" is NOT chosen.

TIME 3: P2 sends Accept(n=2, v="B") to Acc3, Acc4, Acc5.
        BUT WAIT: Phase 1 responses from Acc3, Acc4, Acc5 showed no accepted values.
        So P2 proposes its own value "B".
        But: Acc1 and Acc2 already accepted (1,"A"). They are not in P2's quorum.

        Acc3 accepts (n=2 >= promised n=2). -> Accepted(2,"B")
        Acc4 accepts (n=2 >= promised n=2). -> Accepted(2,"B")
        Acc5 accepts (n=2 >= promised n=2). -> Accepted(2,"B")
        Majority! "B" is chosen.

Is this a problem? Did P1's "A" get overridden?
Answer: No. "A" was never chosen (P1 got only 2/5 accepts). 
"B" is safely chosen with a proper majority.

If P1 had gotten 3/5 accepts before P2 ran Phase 1:
  - P2's Phase 1 would have hit at least one Acceptor that accepted "A".
  - P2 would be forced to propose "A" too. Both would agree on "A".
```

This example shows Paxos in action. The protocol's complexity is entirely in service of
this one guarantee: two different values can never both achieve majority acceptance.

### 2.6 What Paxos Does Not Specify

Basic Paxos (single-decree Paxos) reaches agreement on a single value. But a database
needs to agree on a sequence of values — a log of commands. And the original Paxos paper
leaves many practical questions unanswered:

- How does the system pick a unique proposal number? (Not specified.)
- How do you run Paxos for a growing log of commands? (Multi-Paxos, partially specified.)
- How does a new server catch up on missed decisions? (Not specified.)
- How do you change cluster membership? (Not specified.)
- How does a client retry a request if it does not hear back? (Not specified.)
- How do you compact the log so it does not grow forever? (Not specified.)

This underspecification is why Paxos is notoriously hard to implement correctly. Each
team that implements Paxos essentially invents their own extensions to fill in the gaps,
producing different variants (Chubby's Paxos, Spanner's Paxos, Cassandra's Paxos-like
protocol) that are not directly comparable.

### Brainstorming: Paxos

**Q: Why does the Proposer have to use the previously accepted value from Phase 1 responses?
Why can't it just ignore old values and propose whatever it wants?**

The whole safety of Paxos rests on this rule. If a Proposer could ignore previously
accepted values, here is what could go wrong. Suppose Proposer P1 runs Phase 2 and gets
value "A" accepted by Acceptors {1, 2, 3} — a majority. Consensus on "A" is reached.
Now Proposer P2 runs Phase 1 and collects Promises from Acceptors {2, 3, 4}. Acceptors
2 and 3 report that they accepted "A," but P2 ignores this and proposes "B" in Phase 2.
P2 collects accepts from {3, 4, 5} — another majority. Now "B" is also chosen by a
majority. We have two different values both chosen by majorities: catastrophic.

By forcing P2 to propose "A" when it sees an accepted value in Phase 1 responses,
Paxos ensures this scenario cannot happen. Even if P2 wanted "B," it is forced to
propagate "A" to the remaining acceptors, reinforcing the original decision. The protocol
is structured so that once a value is accepted by any majority, it becomes the only
value any future Proposer can possibly choose.

**Q: What happens if two Proposers keep competing and neither gets a majority? Can Paxos
livelock forever?**

Yes, this is the classic Paxos livelock scenario. Suppose Proposer P1 sends Prepare(n=1)
and gets Promises. Before P1 can send Accept, Proposer P2 sends Prepare(n=2), invalidating
P1's promises. P1 sees the rejection, increments to Prepare(n=3), which invalidates P2's
promises. P2 increments to n=4, and so on. Neither Proposer ever completes Phase 2.

This is the liveness problem Paxos does not solve. The standard solution is leader
election: only one Proposer (the Leader) runs Paxos at a time. Multi-Paxos and Raft both
implement this. When there is a single stable leader, there is no competition, and the
livelock disappears. Leader election itself uses Paxos or a similar mechanism,
bootstrapping the stability of the protocol.

**Q: At an interview, how deeply should I understand Paxos vs. just knowing Raft?**

For most L5/L6 system design interviews, deep Paxos knowledge is not required unless
you are explicitly interviewing for a distributed systems role (storage systems, database
internals, consensus libraries). What you need is: the two-phase structure (Prepare/Promise
then Accept/Accepted), the quorum overlap property that makes it safe, and why Paxos is
underspecified for production use.

Raft, by contrast, is what most modern systems use, and understanding Raft mechanically —
every message field, every state transition — is genuinely valuable in interviews. Raft
was designed to be understandable, so it is a better teaching tool. However, knowing that
Paxos came first, that Chubby and Spanner use Paxos-derived protocols, and the key
conceptual differences between Paxos and Raft will set you apart from candidates who only
know "we use Raft."

---

## Part 3: Multi-Paxos — Running Consensus for a Log

### 3.1 From Single Value to Log

Basic Paxos reaches consensus on one value. A replicated state machine needs consensus
on a sequence of values — the log. Multi-Paxos extends basic Paxos for this purpose.

The idea is simple: run a separate instance of Paxos for each log slot. Slot 1 reaches
consensus on the first command, slot 2 on the second command, and so on. Each slot is
independent.

```
MULTI-PAXOS: PAXOS PER LOG SLOT
==================================

Log slot: [  1  ][  2  ][  3  ][  4  ][  5  ]...
           set    del    set    ???    ???
           a=1    b      x=5

Paxos instance 1: reached consensus on "set a=1"
Paxos instance 2: reached consensus on "del b"
Paxos instance 3: reached consensus on "set x=5"
Paxos instance 4: currently running Phase 1
Paxos instance 5: not started yet
```

### 3.2 The Stable Leader Optimization

Running full two-phase Paxos for every log slot is expensive: two round trips per slot.
Multi-Paxos optimizes this with a stable leader.

If one server is designated the Leader, it can run Phase 1 once (for all future slots)
and then skip to Phase 2 for each new log entry. The Leader gets blanket Promises from
a majority for all future proposal numbers, so it can issue Accept messages directly.

This reduces the cost from two round trips per slot to one round trip per slot (just the
Accept/Accepted exchange). This is the same efficiency as Raft's log replication.

The catch: the Leader designation itself requires a Paxos round to establish. And if the
Leader crashes, a new Phase 1 must be run to establish the next Leader. But in practice,
Leaders are stable for long periods, and the optimization pays off greatly.

### 3.3 What Multi-Paxos Still Leaves Undefined

Even Multi-Paxos leaves important practical details unspecified:

**Leader election**: How does a server decide to become Proposer? How does it ensure
only one Proposer runs at a time? The paper says "elect a distinguished proposer" but
does not specify how.

**Log compaction**: Logs grow forever. At some point, the log must be truncated. The
original Paxos literature provides no mechanism for this.

**Membership changes**: How do you add or remove servers? The quorum size changes when
membership changes, and this is extremely subtle to do safely.

**Client interaction**: How does a client retry a request if it does not hear back?
How does it avoid submitting duplicates? The paper does not say.

**Reads**: Reading from a leader that might no longer be leader could return stale data.
How do you serve linearizable reads?

These gaps mean that every team implementing Multi-Paxos must make independent design
decisions. Google's implementation for Chubby, Spanner, and Megastore all differ. This
fragmentation and the resulting complexity is one reason Raft's author Diego Ongaro
decided to design a new protocol from scratch with explicitness as the primary goal.

### Brainstorming: Multi-Paxos

**Q: If Multi-Paxos optimizes away Phase 1 with a stable leader, how is it different
from Raft at that point?**

This is a great question, and the honest answer is: they are conceptually very similar.
Both use a stable leader to replicate a log, with the leader sending entries to a
majority of followers and committing once a majority acknowledges. The key difference is
that Raft explicitly defines every part of the protocol — leader election algorithm,
log matching properties, membership change procedure, snapshot format — while Multi-Paxos
leaves these as implementation-defined.

A Raft cluster and a Multi-Paxos cluster with a stable leader will have very similar
message patterns. Raft's AppendEntries is essentially Multi-Paxos's Accept. The commit
index in Raft corresponds to the "chosen" value in Paxos. The divergence is in what each
protocol specifies and what it leaves to the implementor. Raft's authors argue that
making everything explicit was the right choice for building reliable systems, because
the underspecified parts of Multi-Paxos are precisely where real bugs live.

**Q: Google has used Paxos for Chubby and Spanner for over a decade. Is Paxos actually
unusable or is the "hard to implement" reputation overblown?**

Paxos is absolutely implementable — Google, Amazon, and others have done it. The
"hard to implement" reputation is not about Paxos being theoretically intractable; it
is about the effort required to fill in all the underspecified parts correctly. Each
team must re-invent log compaction, membership changes, read linearizability, and
leader election. These are non-trivial problems. Done wrong, they introduce subtle safety
violations that may only surface during rare network partitions.

The teams that have successfully implemented Paxos (Chubby, Spanner, Cassandra's
lightweight transactions) are deep distributed systems experts. For most engineering
teams, Raft is a better starting point because the design is fully specified and well-
documented implementations (etcd, CockroachDB, TiKV) are battle-tested and open source.
The recommendation for an interview is: know Paxos conceptually, understand why it is
underspecified, and articulate why Raft was designed as the more accessible alternative.

---

## Part 4: Raft — Designed for Understandability

### 4.1 The Design Philosophy

Raft was introduced by Diego Ongaro and John Ousterhout in their 2014 paper "In Search
of an Understandable Consensus Algorithm." The title is not subtle — Raft's primary
design goal was to be easier to understand than Paxos. Not faster, not more efficient,
not more powerful — just easier to understand.

The authors decomposed the consensus problem into three relatively independent
subproblems:

1. **Leader election**: How does the cluster select a single Leader? What happens when
   the Leader fails?

2. **Log replication**: Once a Leader is elected, how does it accept client requests
   and replicate them to followers reliably?

3. **Safety**: How do we guarantee that committed data is never lost, even if the leader
   crashes at any point?

By separating these three concerns, Raft makes each part independently understandable.
You can study leader election in isolation. You can study log replication without worrying
about leader election. This compartmentalization is a major improvement over Paxos, where
these concerns are interleaved.

### 4.2 Terms as Logical Clocks

Raft introduces the concept of a term. A term is a monotonically increasing integer that
acts as a logical clock for the cluster.

A new term begins whenever a server starts an election. Within one term, there is at most
one leader. If a leader from term 3 is separated from the cluster and a new leader is
elected for term 4, Raft uses the term number to prevent the old leader (still thinking
it is in term 3) from causing confusion.

The rule is simple: if a server receives a message with a higher term number than its
own, it immediately updates its term and reverts to Follower status. An old leader
receiving messages from the new term will see that its term is stale and stand down.

```
RAFT TERMS AS LOGICAL CLOCKS
===============================

Time ------>

Term 1:  [Leader S1]---------------[S1 crashes]
Term 2:  ----[election]----[Leader S2]-----------[S2 crashes]
Term 3:  ----------------------[election]-[Leader S3]----------

If old S1 comes back:
  S1 thinks it's in term 1.
  S3's heartbeat says term=3.
  S1 sees 3 > 1, updates term to 3, becomes Follower.
  Split-brain prevented.
```

### 4.3 The Three Server States

Every Raft server is in exactly one of three states at all times: Follower, Candidate,
or Leader.

**Follower**: The passive state. Followers receive log entries from the Leader and vote
in elections. A server starts as a Follower when it first boots. Followers set a timer
called the election timeout. If the timer expires without receiving a heartbeat from
the Leader, the Follower concludes that the Leader has crashed and starts an election.

**Candidate**: The election state. A Follower that times out becomes a Candidate. It
increments its term, votes for itself, and sends RequestVote RPCs to all other servers.
If it receives votes from a majority, it becomes Leader.

**Leader**: The active state. There is at most one Leader per term. The Leader receives
all client requests, replicates them to Followers, and sends periodic heartbeats (empty
AppendEntries RPCs) to prevent Followers from timing out and starting unnecessary
elections.

### Brainstorming: Raft's Design Goals

**Q: Raft says it is designed for understandability. Does that mean it sacrifices
performance compared to Paxos?**

Not in practice. Raft and Multi-Paxos with a stable leader have nearly identical
performance characteristics — both require one round trip from leader to a majority of
followers for each committed log entry. Raft does have a couple of deliberate
simplifications that might cost performance in edge cases. For example, Raft does not
allow holes in the log (Paxos can have gaps filled in any order), which means a slow
follower blocks the leader from skipping ahead. For most workloads, this difference is
negligible.

Where Raft's performance matters more is the performance of the full-stack implementation
built on top of it. Because Raft is fully specified and well-understood, implementations
like etcd can focus optimization effort on the storage layer, RPC batching, and
read-optimization (leader leases, follower reads) rather than re-inventing basic protocol
correctness. The clarity of the specification enables better engineering.

**Q: Are there consensus protocols faster than Raft for specific use cases?**

Yes. EPaxos (Egalitarian Paxos) allows any replica to commit non-conflicting commands
independently, without a leader, which can reduce latency for geographically distributed
clusters. Flexible Paxos relaxes the quorum requirement asymmetrically. Fast Paxos
allows clients to send directly to acceptors under some conditions, saving a round trip.

However, these protocols are harder to understand and implement correctly, and they
optimize for specific scenarios (geo-distribution, high-throughput non-conflicting
workloads). For the vast majority of production systems — a 3 or 5 node cluster in one
data center — Raft's simplicity and battle-tested implementations (etcd, CockroachDB)
make it the right choice. At an interview, mentioning that faster variants exist (and
naming EPaxos) is a sign of depth, but the interviewer will almost always be satisfied
with Raft as the implementation choice.

---

## Part 5: Raft Leader Election — Step by Step

### 5.1 The State Machine in Detail

```
RAFT SERVER STATE MACHINE
===========================

                    +------------+
          Start --> |  FOLLOWER  |
                    +------------+
                    |            |
  Times out,        |            | Receives heartbeat
  no heartbeat      |            | or valid AppendEntries
                    v            |
                    +------------+
                    | CANDIDATE  |<---+
                    +------------+    |
                    |      |          |
                    |      | Times out,
  Receives votes    |      | splits    |
  from majority     |      | vote      |
                    |      +-----------+
                    |
                    | Wins election (majority votes)
                    v
                    +------------+
                    |   LEADER   |
                    +------------+
                    |            |
                    |            | Discovers server
  Sends heartbeats  |            | with higher term
  AppendEntries     |            |
                    |            v
                    |         +------------+
                    +-------> |  FOLLOWER  |
                              +------------+

Notes:
- Candidate -> Follower: if it discovers another leader OR gets AppendEntries 
  with higher/equal term
- Leader -> Follower: if it gets any message with higher term
- Election timeout: randomized 150-300ms per server to avoid split votes
```

### 5.2 The RequestVote RPC — Every Field Explained

When a Candidate starts an election, it sends RequestVote RPCs to all other servers.
Here are all the fields:

```
RequestVote RPC (Candidate -> all servers)
============================================

Fields sent:
  term          : Candidate's current term (this election is for this term)
  candidateId   : The ID of the Candidate sending this request
  lastLogIndex  : Index of the Candidate's last log entry
  lastLogTerm   : Term of the Candidate's last log entry

Response:
  term          : Voter's current term (Candidate uses this to update itself)
  voteGranted   : true if the voter grants a vote, false otherwise

Vote-granting rules (both must be satisfied):
  1. The voter has not already voted for someone else in this term
  2. The Candidate's log is at least as up-to-date as the voter's log
     ("up-to-date" rule: higher lastLogTerm wins; if same, higher lastLogIndex wins)
```

The "up-to-date" log check is Raft's election restriction and is the cornerstone of
Raft's safety guarantee. We cover it in detail in Part 7.

### 5.3 A Concrete Election — Step by Step

Let us trace a full election in a 5-server cluster after the leader crashes.

```
RAFT ELECTION: CONCRETE TRACE
================================

Cluster: S1 (Leader, crashes), S2, S3, S4, S5
All servers' logs: entries up to index 23, term=4
Current term at crash: T=4

S1 crashes at T=0.

--- S3's election timeout fires first at T=172ms ---

S3 increments term to T=5.
S3 votes for itself (votedFor = S3).
S3 sends RequestVote(term=5, candidateId=S3, lastLogIndex=23, lastLogTerm=4)
  to S2, S4, S5, S1.

S2 receives RequestVote:
  - S2's term is 4 < 5, so S2 updates its term to 5.
  - S2 has not voted in term 5.
  - S3's log: index=23, term=4. S2's log: index=23, term=4. Same -> up-to-date.
  - S2 grants vote. Responds: (term=5, voteGranted=true).
  - S2 resets its election timeout.

S4 receives RequestVote:
  - Same checks pass.
  - S4 grants vote. Responds: (term=5, voteGranted=true).

S3 has now received 3 votes (itself, S2, S4) = majority of 5.
S3 becomes Leader for term 5.

S3 immediately sends heartbeats (empty AppendEntries) to all:
  AppendEntries(term=5, leaderId=S3, prevLogIndex=23, prevLogTerm=4,
                entries=[], leaderCommit=commitIndex)

S5 receives heartbeat:
  - S5's term is 4 < 5, updates to 5, becomes Follower.
S4 receives heartbeat: already Follower in term 5, resets timer.
S2 receives heartbeat: resets timer.

If S5 also sent a RequestVote for term 5 (started election around same time):
  - S5 gets S3's heartbeat with term=5. S5 sees an existing leader, reverts to Follower.
  - S5's RequestVote messages arrive at S2, S4. They already voted for S3 in term 5.
    They respond voteGranted=false. S5 stays Follower.

Election complete. S3 is Leader for term 5.
Total time: ~172ms (election timeout) + ~5ms (message round trips) = ~177ms downtime.
```

### 5.4 Split Vote and Recovery

What if two Followers time out at almost the same time and each gets exactly two votes
(neither gets a majority)?

```
SPLIT VOTE SCENARIO
====================

S1 crashes. S2 and S3 both timeout at nearly the same time.

S2 sends RequestVote(term=5): gets votes from S4 -> 2 votes (S2, S4)
S3 sends RequestVote(term=5): gets votes from S5 -> 2 votes (S3, S5)

Neither has 3/5. Both are still Candidates.

Resolution:
  - Each Candidate has a randomized election timeout.
  - Suppose S2's timeout fires first: S2 increments to term=6, sends RequestVote again.
  - S3 receives RequestVote for term=6. S3's term is 5 < 6. S3 updates to term 6,
    reverts to Follower, grants vote to S2.
  - S2 gets a majority and becomes Leader for term 6.

The randomized timeout is the key. On average, only one server times out first,
avoiding repeated split votes. In practice, split votes are rare and resolve quickly.
```

### 5.5 Term Numbers Preventing Old Leaders

Here is a subtle but important scenario: what happens when the old leader comes back?

```
OLD LEADER SCENARIO
====================

T=0:  S1 is Leader (term=4). Cluster has 5 servers.
T=100ms: Network partition. S1 is isolated. S1 cannot reach others.
T=272ms: S2 times out. Election. S2 becomes Leader for term=5.
T=1000ms: S2 has been leader for 728ms, committed many entries.

T=1500ms: Network heals. S1 and S2 can communicate.

S1 still thinks it is Leader in term=4.
S1 tries to send AppendEntries(term=4, ...) to S2.

S2 receives AppendEntries from S1:
  - S2's current term is 5 > 4.
  - S2 responds: (term=5, success=false).
  - Rule: S1 sees a higher term in the response, updates its term to 5.
  - S1 reverts to Follower. S1 accepts S2 as the current leader.

S1's uncommitted entries from term=4 will be overwritten by S2's log.
Committed entries from term=4 are safe (they are also in S2's log, guaranteed by
the election restriction).
```

### Brainstorming: Leader Election

**Q: What is the exact definition of "more up-to-date" log? Why not just compare log
length?**

Comparing just log length would be unsafe. Consider a server that crashed while the
leader was in term 2, and another server that stayed connected through term 3. The
first server might have a longer log from term 2, but the second server has entries
from term 3 that were actually committed. If you elected the first server as leader,
it would overwrite the committed term-3 entries with its longer-but-staler term-2 log.

Raft's "up-to-date" rule is: compare the term of the last log entry first (higher term
wins). If the last log entries have the same term, compare the log length (longer wins).
This rule ensures that a server with entries from a more recent term always wins over
a server with a longer log from an older term. The intuition is that more recent terms
reflect more up-to-date state — a server that participated in later elections and log
replication is closer to the current cluster state.

**Q: Raft uses randomized timeouts to avoid split votes. Are there more sophisticated
approaches?**

Yes. The simplest randomization (each server picks a random timeout between 150ms and
300ms) works well in practice and is what the Raft paper specifies. The variance (150ms
range) means the probability of two servers timing out within 5ms of each other —
close enough to cause a split vote — is low.

More sophisticated approaches include PreVote (a candidate first checks whether it could
win an election without actually incrementing the term, preventing unnecessary term
inflation), leader stickiness (recently seen leaders get preference), and check-in
intervals (servers exchange state proactively to detect stale leaders sooner). etcd
implements PreVote to reduce disruption from flapping servers. These are optimizations;
the base randomized timeout is sufficient for correctness and handles most production
scenarios well.

**Q: How long is the cluster unavailable during a leader election? Does this matter?**

Unavailability during leader election is bounded by the election timeout plus the time
to complete one round of voting, typically 150-300ms election timeout + a few milliseconds
for network round trips = about 150-310ms in a well-configured LAN deployment.

For most applications, 200-300ms of write unavailability during a failover is acceptable.
The cluster is still available for reads that tolerate slight staleness (followers can
serve reads from their local state). For applications that require sub-100ms failover,
there are workarounds: leader leases (followers track when their lease expires and serve
reads without contacting the leader), PreVote to reduce disruption, and tuning the
election timeout lower (but then you risk spurious elections due to GC pauses or network
jitter). The right timeout depends on your network RTT and GC behavior.

---

## Part 6: Raft Log Replication — Step by Step

### 6.1 The AppendEntries RPC — Every Field Explained

All log replication in Raft goes through the AppendEntries RPC. The Leader sends this
RPC to all followers. It is also used as the heartbeat (with an empty entries list).

```
AppendEntries RPC (Leader -> Follower)
========================================

Fields sent:
  term          : Leader's current term
  leaderId      : Leader's server ID (followers can redirect clients)
  prevLogIndex  : Index of the log entry immediately before the new entries
  prevLogTerm   : Term of the entry at prevLogIndex
  entries[]     : Log entries to store (empty for heartbeat)
  leaderCommit  : Leader's current commit index

Response:
  term          : Follower's current term (leader uses this to step down if stale)
  success       : true if Follower accepted the entries, false otherwise

Rules for Follower when it receives AppendEntries:
  1. If term < current term: reject (respond false, include own term)
  2. If log does not contain entry at prevLogIndex with term prevLogTerm: reject
     (the log consistency check fails)
  3. If an existing entry conflicts with a new one (same index, different term):
     delete the existing entry and all that follow
  4. Append any new entries not already in the log
  5. If leaderCommit > commitIndex: set commitIndex = min(leaderCommit, last log index)
  6. Apply newly committed entries to state machine (lastApplied advances to commitIndex)
```

### 6.2 The Commit Index vs. Last Applied

Two important indices in Raft that students often confuse:

**commitIndex**: The highest log index known to be committed (safely replicated to a
majority). The leader updates this when a majority of servers acknowledge a log entry.
Committed entries are guaranteed to survive any future leader election.

**lastApplied**: The highest log index applied to the state machine. This starts at 0
and advances as committed entries are applied. lastApplied <= commitIndex always.

The gap between commitIndex and lastApplied represents entries that are committed but
not yet applied. The server applies them in order, closing the gap. This separation
allows the state machine application to be asynchronous relative to the commit process.

### 6.3 A Concrete Replication Trace With 5 Servers

```
RAFT LOG REPLICATION: COMPLETE TRACE
======================================

Cluster: S1 (Leader, term=3), S2, S3, S4, S5.
Current log state (all servers): entries up to index=10, committed up to index=9.

Client sends: "set x = 42"

--- Step 1: Leader appends entry to its own log ---

S1 appends: LogEntry(index=11, term=3, command="set x=42")
S1's log: [..., (10, T=2, "del y"), (11, T=3, "set x=42")]
S1's commitIndex: still 9 (not yet replicated)

--- Step 2: Leader sends AppendEntries to all Followers ---

S1 sends to S2, S3, S4, S5 (in parallel):
  AppendEntries(
    term=3,
    leaderId=S1,
    prevLogIndex=10,
    prevLogTerm=2,        <- term of entry at index 10
    entries=[(11, T=3, "set x=42")],
    leaderCommit=9
  )

--- Step 3: Followers process AppendEntries ---

S2 receives AppendEntries:
  - term=3 == S2's current term. OK.
  - Check: does S2's log have entry at index=10 with term=2? Yes.
  - Append: LogEntry(index=11, term=3, "set x=42").
  - leaderCommit=9 > S2's commitIndex=9? No. commitIndex stays 9.
  - Respond: (term=3, success=true)

S3, S4 respond similarly: (term=3, success=true)

S5 was slow (briefly disconnected). S5's log only has entries up to index=8.
S5's consistency check fails: S5 has no entry at index=10.
S5 responds: (term=3, success=false)

--- Step 4: Leader updates commitIndex ---

S1 has received success from S2, S3, S4 (3 out of 5 = majority).
Entry (index=11, term=3) is now replicated to a majority.
S1 updates: commitIndex = 11.
S1 applies "set x=42" to its state machine. x is now 42.
S1 responds to client: "OK, x=42"

--- Step 5: Next heartbeat/AppendEntries carries updated commitIndex ---

S1 sends next AppendEntries to all:
  AppendEntries(term=3, ..., leaderCommit=11)

S2 receives: leaderCommit=11 > commitIndex=9. S2 updates commitIndex=11.
S2 applies entries at indices 10 and 11 to its state machine.
S3, S4 do the same.

--- Step 6: S5 catch-up ---

S1 receives success=false from S5 for index=11.
S1 knows S5 is behind. S1 tries with an earlier entry.
S1 backs up: sends AppendEntries with prevLogIndex=7, prevLogTerm=1,
  entries=[(8,T=2,...), (9,T=2,...), (10,T=2,...), (11,T=3,...)]
S5 checks: has entry at index=7 with term=1? Yes.
S5 appends entries 8-11. Responds: success=true.
S5 is now caught up.
```

### 6.4 Log Inconsistency: When Do Followers Have Different Logs?

Followers can have inconsistent logs when a leader crashes in the middle of replication.
Some followers might have entries that the crashed leader had not yet committed, while
others do not. The new leader repairs these inconsistencies using the prevLogIndex/
prevLogTerm check: it walks back until it finds where the follower's log agrees, then
overrides everything after that point.

```
LOG INCONSISTENCY AFTER LEADER CRASH
======================================

After S1 (old leader) crashes with term=2:
 
        Index:  1  2  3  4  5  6  7  8  9 10
 S2 (new ldr):  1  1  1  2  2  2  2  3  3  3
          S3:   1  1  1  2  2  2  2  3  3  --  (missing one entry)
          S4:   1  1  1  2  2  2  2  3  --  --  (missing two entries)
          S5:   1  1  1  2  2  2  2  --  --  --  (missing three entries)
  (dead S1):   1  1  1  2  2  2  2  4  4  4   (had uncommitted entries from term 4)

S2 becomes new leader (term=5). It sends AppendEntries.

For S3: prevLogIndex=9, prevLogTerm=3. S3 has entry at 9 with term=3. 
  S3 appends index=10 from S2. OK.

For S4: prevLogIndex=9 fails (S4 has no index 9). 
  S2 backs up to prevLogIndex=8. S4 has index=8, term=3. OK.
  S2 sends entries 9 and 10. S4 appends.

For S5: backs up to prevLogIndex=7, term=2. S5 has it. 
  S2 sends entries 8, 9, 10. S5 appends.

When S1 comes back:
  S1 had entries at index 8, 9, 10 with term=4 (uncommitted from old leadership).
  S2's AppendEntries for term=5: S1 sees higher term, becomes Follower.
  S1's entries 8-10 (term=4) are overwritten by S2's log.
  This is safe: those entries were never committed (not in a majority).
```

### Brainstorming: Log Replication

**Q: How does the leader know how far behind each follower is? Does it track this
individually?**

Yes. Each leader maintains two arrays indexed by server: nextIndex[] and matchIndex[].
nextIndex[i] is the index of the next log entry the leader will send to server i. It
starts optimistically at leader's log length + 1. If a follower rejects AppendEntries
because its log is behind, the leader decrements nextIndex[i] and retries with an
earlier prevLogIndex. matchIndex[i] is the index of the highest log entry known to be
replicated on server i. The leader uses matchIndex[] to compute the commit index: if
matchIndex[i] >= N for a majority of servers, and the entry at index N has term equal
to the leader's current term, then the leader sets commitIndex = N.

This per-follower tracking is why Raft leaders are stateful and cannot simply be
replaced without a proper election. A new leader resets nextIndex optimistically and
rediscovers each follower's state through the AppendEntries consistency check mechanism,
which is correct but involves some initial back-and-forth for followers that are far
behind.

**Q: If the leader commits an entry and crashes before notifying followers, can that
entry be lost?**

This is the central question. The entry is committed only after a majority of servers
have it in their logs. When the leader "commits," it means at least a majority already
have it. When a new leader is elected, it must have had the most up-to-date log among
the voting majority (election restriction). Since the committed entry was in a majority
of servers, and the new leader got votes from a majority, the new leader must have had
at least one server that holds the committed entry — and that server would only vote for
a candidate with an equally or more up-to-date log. So the new leader must have the
committed entry. It cannot be lost.

The only scenario where this breaks is if you use an incorrect implementation where the
leader commits before waiting for a majority. Do not do that. The protocol as specified
by Raft is safe: a leader only marks an entry as committed after receiving success
responses from a majority.

**Q: What does "linearizable" mean for reads? Can followers serve reads?**

Linearizability means that reads reflect the most recent committed write. If you write
x=5 and then immediately read x, you must see 5, not an older value. This is strong
consistency.

By default, only the leader can serve linearizable reads, because only the leader knows
the current commit index. A follower's committed state might lag the leader's. There are
two standard approaches to let followers serve reads. First, leader leases: the leader
can guarantee it is still the leader for some time window (based on the election timeout),
and followers trust this. Within the lease window, the leader can read from local state
without another round trip. Second, read index: the leader records its current commit
index (the "read index"), confirms it is still the leader by broadcasting a heartbeat,
then tells the follower the read index; the follower waits until it has applied entries
up to the read index, then serves the read. Both approaches avoid the overhead of
running a Paxos round for every read.

---

## Part 7: Raft Safety — Why Committed Data Is Never Lost

### 7.1 The Election Restriction

The centerpiece of Raft's safety guarantee is the election restriction: a Candidate can
only be elected if its log is at least as up-to-date as the log of any server that votes
for it.

"At least as up-to-date" means:
- If the last log entries have different terms, the Candidate with the higher term wins.
- If the last log entries have the same term, the Candidate with the longer log wins.

This rule ensures that only a Candidate with all committed entries can win an election.
Here is why.

### 7.2 Log Matching Property

**Claim**: If two logs contain an entry with the same index and term, then the logs are
identical in all entries up to that index.

**Proof**: By the AppendEntries consistency check. When a leader sends entries to a
follower, it includes prevLogIndex and prevLogTerm. The follower rejects the request if
its log does not have an entry matching those values. This means the follower's log
matches the leader's log at prevLogIndex before any new entries are appended. By
induction, if the logs agree at one point, and each follower verifies that the preceding
entry matches before accepting a new entry, then the logs agree at all points up to
the new entry.

This property means that log divergence can only happen after the last matching point.
The new leader finds this matching point using the prevLogIndex/prevLogTerm check and
repairs the follower's log from that point onward.

### 7.3 Leader Completeness Theorem

**Claim**: If a log entry is committed in term T, that entry will be present in the logs
of all leaders for all terms greater than T.

**Proof sketch**: By contradiction. Suppose entry E at index I was committed in term T
(meaning a majority of servers had E in their logs). Suppose a later leader L in term
T' does not have E. For L to be elected, it must have received votes from a majority.
Since E was committed, a majority had E. Any two majorities overlap — so at least one
server (call it S) both had E in its log and voted for L.

S voted for L, which means L's log was at least as up-to-date as S's log. S has entry
E at index I (from term T). L does not have E at index I. For L's log to be considered
"at least as up-to-date" as S's despite missing E, L would need a more recent term at
the position where E is. But E being committed means it was accepted by a majority in
term T. If L had a conflicting entry at that position from a later term, that entry would
also have needed a majority of servers to accept it — but those servers had already
accepted E at that position, and the AppendEntries consistency check prevents overwriting.
The only exception is uncommitted entries, which are allowed to be overwritten. But E
is committed. Contradiction.

Therefore, L must have E. Every future leader has all committed entries.

### 7.4 The Safety Guarantee in Plain English

Put it all together. Once an entry is committed (replicated to a majority), three things
guarantee it is never lost:

1. **Majority durability**: The entry is on a majority of servers. For all of them to
   crash simultaneously, F+1 servers would need to fail, which exceeds our failure
   tolerance (we can only tolerate F failures).

2. **Election restriction**: Any new leader must have had a log at least as up-to-date
   as a majority. Since the committed entry is on a majority, any new leader must have
   it.

3. **Log matching**: Once the new leader has the committed entry, it will propagate it
   to all followers through normal log replication. No follower can have a conflicting
   entry at that position (because that would violate the log matching property).

```
SAFETY INVARIANT VISUALIZATION
=================================

Committed entry E at index=11, term=3:

Server:  S1  S2  S3  S4  S5
Has E:   YES YES YES NO  NO     <- 3/5 majority has E
Votes:   ??? ??? ??? YES YES    <- any new leader needs 3 votes

To win election, new leader needs votes from 3 servers.
The possible 3-vote winning sets:
  {S1,S2,S3}: all have E -> new leader has E. SAFE.
  {S1,S2,S4}: S1,S2 have E -> election restriction ensures winner has E. SAFE.
  {S1,S2,S5}: S1,S2 have E -> same. SAFE.
  {S1,S3,S4}: S1,S3 have E -> same. SAFE.
  {S1,S3,S5}: S1,S3 have E -> same. SAFE.
  {S2,S3,S4}: S2,S3 have E -> same. SAFE.
  {S2,S3,S5}: S2,S3 have E -> same. SAFE.
  ...

In every possible 3-server winning coalition, at least one server has E.
(Because E is on 3 servers and any winning set must overlap with those 3.)
The election restriction ensures the winner must have at least as up-to-date a log
as every server that voted for it, so the winner has E.
```

### Brainstorming: Safety

**Q: What if a disk fails and a server loses its log? Doesn't that break the majority?**

Disk failure is a different kind of failure than crash failure. The Raft paper assumes
that a server that recovers from a crash still has its durable log (stored on disk). If
the disk is corrupted, the server cannot recover its log and effectively cannot rejoin
the cluster as if it were a normal recovery — it needs to be re-provisioned as a new
server from scratch (getting a full snapshot from the leader).

In terms of quorum: if a server loses its disk, it is out of commission. The remaining
servers continue. If you lose a majority's disks simultaneously, you have lost committed
data — this is outside Raft's fault model. Raft tolerates F crash failures where N >= 2F+1.
If you want to tolerate F disk failures as well, you need a different configuration (e.g.,
local RAID for disk redundancy + Raft across multiple machines for node redundancy).

**Q: Is there any scenario where Raft could return stale data?**

For linearizable reads, no — the protocol as specified does not return stale data for
reads going through the leader. However, implementation shortcuts can introduce
staleness. If a server is a follower and you read directly from it without going through
the leader, the follower might be behind by several entries. Many systems (TiDB, etcd)
offer "stale reads" as a deliberate optimization (lower latency, higher throughput) for
applications that can tolerate bounded staleness. But if you configure a system for
linearizable reads and implement it correctly, staleness is impossible by the safety
guarantee.

---

## Part 8: Network Partitions in Raft

### 8.1 What Happens During a Partition

A network partition splits the cluster into two groups that cannot communicate. For a
5-server cluster, a common split is 3 servers on one side (the majority partition) and
2 on the other (the minority partition).

```
NETWORK PARTITION SCENARIO
============================

Before partition:
  S1 (Leader, T=3), S2, S3 | S4, S5
  All connected. Normal operation.

Partition happens at T=100ms:
  LEFT side:  S1, S2, S3 (3 servers)
  RIGHT side: S4, S5     (2 servers)

--- LEFT SIDE (majority) ---

S1 is still Leader. S1 can reach S2 and S3 (2 followers).
S1 + S2 + S3 = 3 out of 5 = majority.
S1 continues to commit entries. Heartbeats keep S2, S3 from timing out.

Client writes go to S1. S1 replicates to S2, S3. Commits with 3/5.
LEFT SIDE CONTINUES NORMAL OPERATION.

--- RIGHT SIDE (minority) ---

S4 and S5 cannot reach S1 (no heartbeats).
S4 times out first, starts election in term=4.
S4 sends RequestVote to S5. S5 grants vote.
S4 gets 2/5 votes (only S4 and S5). NOT a majority.
S4 cannot become Leader.

S5 might also try. S5 gets 2/5 votes. Also cannot become Leader.

RIGHT SIDE CANNOT MAKE PROGRESS. Cannot commit anything. 
Client writes routed to S4 or S5 are rejected (no leader) or stall.

Terms keep incrementing on the right side (each failed election).
S4 might be in term=10 while left side is in term=3.
```

### 8.2 Partition Heals — Leadership Change

When the partition heals, the two sides can communicate again. Here is what happens:

```
PARTITION HEALS AT T=5000ms
==============================

S4 (currently in term=10, was trying to be Candidate) sees S1's heartbeat:
  S1 sends AppendEntries(term=3, ...).
  S4's term is 10 > 3. S4 responds: (term=10, success=false).
  
S1 receives response with term=10 > its term=3.
  S1 sees higher term. S1 immediately steps down to Follower.
  S1 updates its term to 10.

Cluster is now leaderless. An election starts.
S2 or S3 or someone will time out and run an election in term=11 or higher.
Whoever wins (with the most up-to-date log from the LEFT side) becomes the new leader.

Newly elected leader replicates left side's committed log to S4 and S5.
S4's term=10 entries (if any uncommitted ones existed) are overwritten.
Cluster is now unified and consistent.
```

### 8.3 Raft Is CP, Not AP

The CAP theorem says a distributed system can provide at most two of: Consistency,
Availability, Partition tolerance. Raft chooses Consistency over Availability.

During a network partition, the minority side becomes completely unavailable for writes.
If your service is deployed across two data centers and the inter-DC link fails, and your
majority is on one side, the other side is dark. This is the trade-off Raft makes.

The alternative — AP systems like DynamoDB or Cassandra — allow both sides to continue
accepting writes, reconciling conflicts later. This gives higher availability but
potentially allows divergent state (which must be resolved, e.g., with last-write-wins
or application-level conflict resolution).

For use cases where consistency is paramount (distributed locks, leader election, service
discovery, financial transactions), CP systems using Raft or Paxos are the right choice.
For use cases where availability matters more than strict consistency (social feeds,
shopping carts, user preferences), AP systems are better.

### 8.4 Real Incident: etcd Split-Brain in Kubernetes

In 2018-2019, several Kubernetes production clusters experienced split-brain events in
their etcd clusters. etcd is the database that stores all Kubernetes cluster state
(pods, services, deployments). A split-brain in etcd means two parts of the cluster
believe they are the authoritative source of truth.

The root cause in several incidents was misconfigured election timeouts combined with
slow disk I/O. etcd's leader must write to disk synchronously before responding to
clients (to ensure durability). If the disk becomes slow (common in cloud VMs under
high I/O), the leader's heartbeats are delayed. Followers interpret the heartbeat delay
as a leader failure and start an election. If disk writes are slow enough that
heartbeats are consistently delayed, followers keep starting elections, fragmenting the
cluster.

The fix involves several layers: using dedicated SSDs for etcd, setting the disk I/O
priority for the etcd process, adjusting heartbeat and election timeouts to account for
disk latency, and using Linux cgroups to prevent other processes from starving etcd's
I/O. Kubernetes documentation now explicitly recommends etcd on dedicated nodes with
fast SSDs for production clusters.

This incident illustrates a subtle point: Raft's theoretical correctness does not
protect against incorrect timeout configuration. A well-specified protocol running with
bad parameters can still cause outages.

### Brainstorming: Network Partitions

**Q: If the minority side's terms kept incrementing during the partition (S4 went from
term=3 to term=10), does that cause problems when the partition heals?**

The high term number from the minority side's failed elections does cause a brief
disruption when the partition heals. The majority-side leader (in term=3) receives a
response with term=10 and immediately steps down. This causes a new election in the
full cluster. The new election is fast (a few hundred milliseconds), and the winning
candidate will be from the majority side (because it has the most up-to-date log).

This is the design intent — the high term from the minority side is forcing the stale
majority-side leader to yield. Even though term=3 was the last committed term, it is now
outdated. The new leader in term=11 will continue from where the majority left off. There
is no data loss or inconsistency. The downside is a brief additional disruption (the
new election) when the partition heals. This is sometimes called "leadership storm" and
can be mitigated by PreVote (candidates check if they can win before incrementing the
term, preventing unnecessary term inflation from failed elections).

**Q: If Raft is CP and the minority partition cannot make progress, what happens to
clients sending requests to the minority side?**

The clients sending to the minority side will get errors or timeouts. Specifically:
S4 and S5 cannot commit anything because they cannot get a majority (they have only
2 votes). If S4 is running as leader (it got S5's vote), it can accept client writes
to its log but can never commit them. When the partition heals and a new leader takes
over, S4's uncommitted entries will be discarded. This means clients on the minority
side experience either: (a) explicit errors ("no leader"), (b) timeouts, or (c)
apparent success that is silently reverted. The correct client behavior is to treat
any response other than an explicit "committed" acknowledgment as a potential failure
and retry.

This is why distributed systems engineers say "if you don't get a success response,
you don't know whether your write was committed." The client must be prepared to retry
idempotently. Raft's protocol itself does not solve the client retry problem — that is
an application-level concern, usually addressed with idempotency keys or at-least-once
delivery semantics.

---

## Part 9: Membership Changes — Adding and Removing Servers

### 9.1 The Naive Approach and the Split-Vote Problem

Suppose you want to add two servers to a 3-server Raft cluster, going from 3 to 5
servers. The naive approach: tell all servers simultaneously that the new configuration
is {1, 2, 3, 4, 5}.

The problem: configuration switches are not atomic. At the moment of the switch, some
servers might have switched to the new config (needing 3/5 for a majority) while others
are still on the old config (needing 2/3 for a majority).

```
SPLIT-VOTE PROBLEM WITH NAIVE APPROACH
========================================

Old config: {S1, S2, S3}  -- majority = 2/3
New config: {S1, S2, S3, S4, S5} -- majority = 3/5

At transition moment:
  S1 (old config): majority = 2/3. S1 + S2 = majority. S1 is Leader.
  S4 (new config): majority = 3/5. S4 + S3 + S5 = majority. S4 is Leader.

Both S1 and S4 are "leaders" simultaneously. Split-brain.
```

### 9.2 Joint Consensus — Raft's Safe Approach

Raft's solution is joint consensus: before transitioning to the new configuration, enter
a joint configuration that requires majorities from both the old AND the new configuration.

The joint configuration C_old,new is treated as a single configuration. For any decision
(log commit, leader election), a majority of both C_old and C_new must agree.

```
JOINT CONSENSUS CONFIGURATION CHANGE
=======================================

Step 1: Leader receives membership change request (add S4, S5).
  Leader commits a special C_old,new log entry:
    "New config = {S1,S2,S3} AND {S1,S2,S3,S4,S5}"

Step 2: During C_old,new, all commits need:
  - Majority of old config: >= 2/3 of {S1,S2,S3}
  - Majority of new config: >= 3/5 of {S1,S2,S3,S4,S5}
  Both majorities must say yes.

Step 3: Once C_old,new is committed to a majority of BOTH configs:
  Leader commits C_new log entry: "New config = {S1,S2,S3,S4,S5}"

Step 4: Servers that are in C_new and have committed C_new:
  Switch to requiring majority of new config only (3/5).

Step 5: Old servers not in C_new can safely be shut down.
  No split-brain possible: during any transition, the joint config
  requires agreement from overlapping majorities.
```

### 9.3 etcd's Single-Server-at-a-Time Approach

Joint consensus is correct but complex to implement. etcd (the reference Raft
implementation used by Kubernetes) uses a simpler approach for most membership changes:
add or remove one server at a time.

When you add one server to a 3-server cluster (going to 4), the majority requirement
changes from 2/3 to 3/4. A single-server change never creates a disjoint pair of
majorities, so the split-vote problem does not occur. The proof: in the old config
(N servers), majority is N/2 + 1. In the new config (N+1 servers), majority is (N+1)/2 + 1
if N+1 is even, or (N+2)/2 if N is even. You can verify that these two majority sets
always overlap.

For most production use cases (adding a server for redundancy, removing a failed server),
one-at-a-time changes are sufficient. Joint consensus is needed when you want to atomically
replace multiple servers simultaneously.

### Brainstorming: Membership Changes

**Q: What happens if a membership change is attempted while the cluster is in the middle
of a leader election?**

Membership changes should only be initiated by the leader. A server receiving a
membership change request while there is no leader (during an election) will queue or
reject the request. Once a new leader is elected, it can process the membership change.

The subtlety is that the new leader must not apply a membership change from a previous
leader's log without understanding its implications. Raft handles this by treating
membership change entries like any other log entry: they are committed through the normal
AppendEntries mechanism. Once a membership change entry is committed, its effects take
place. The election restriction ensures that any new leader after a membership change
entry was committed will have that entry in its log and will operate with the new
membership.

**Q: If you are removing a server, how does that server know when it can safely shut
down?**

A server that is being removed will eventually see a committed log entry for the new
configuration (C_new) that does not include itself. At that point, it knows it is no
longer part of the cluster. It can then safely shut down or become a non-voting observer.

The tricky part: the server should not shut down until C_new is committed, because if it
shuts down early and the leader crashes before committing C_new, a new election might
need the removed server's vote. Raft handles this by having the removed server remain
active (and potentially vote) until it has applied the C_new log entry and confirmed it
is not in C_new.

---

## Part 10: Log Compaction and Snapshots

### 10.1 The Log Growth Problem

A Raft cluster that runs indefinitely will accumulate an ever-growing log. If the log
is stored on disk, it will eventually fill the disk. If a server restarts, it must
replay the entire log to reconstruct the state machine, which becomes prohibitively slow.
A server that was offline for a week and restarts cannot realistically replay a week's
worth of writes.

The solution is snapshotting: periodically, a server takes a snapshot of its state
machine's current state, writes it to disk, and then truncates the log up to the
snapshot point. The snapshot replaces the log as the starting point for state machine
reconstruction.

### 10.2 What a Snapshot Contains

```
RAFT SNAPSHOT STRUCTURE
=========================

A snapshot represents the state machine state at a specific point in the log.

Snapshot contents:
  lastIncludedIndex : The index of the last log entry covered by this snapshot
  lastIncludedTerm  : The term of the log entry at lastIncludedIndex
  state machine data: The complete serialized state of the state machine
                      (e.g., the entire key-value store as of index lastIncludedIndex)
  cluster configuration: The cluster membership as of lastIncludedIndex (if changed)

After taking snapshot at index=100:
  - Log entries 1 through 100 are deleted.
  - Log retains entries 101, 102, 103, ...
  - When recovering, first load snapshot (restores state as of index=100),
    then replay log entries 101, 102, 103, ... to get current state.

Disk layout:
  [snapshot: state as of index=100, term=5] [log: 101, 102, 103, ...]
  
  vs. old layout:
  [log: 1, 2, 3, ..., 100, 101, 102, 103, ...]
```

### 10.3 InstallSnapshot RPC — For Lagging Followers

Sometimes a follower falls so far behind that the leader has already compacted the log
entries the follower needs to catch up. The leader cannot send the missing log entries
(they are gone). Instead, the leader sends the entire snapshot to the follower.

```
InstallSnapshot RPC (Leader -> Follower)
==========================================

Fields:
  term              : Leader's current term
  leaderId          : Leader's ID
  lastIncludedIndex : Index of last entry covered by snapshot
  lastIncludedTerm  : Term of last entry covered by snapshot
  offset            : Byte offset in snapshot data (for chunked transfer)
  data[]            : Snapshot data chunk
  done              : true if this is the last chunk

Follower response:
  term              : Follower's current term

Follower actions upon receiving InstallSnapshot:
  1. If done=false: write chunk to disk and wait for more.
  2. If done=true and lastIncludedIndex > commitIndex:
     - Discard entire log (replace with snapshot).
     - Set commitIndex = lastApplied = lastIncludedIndex.
     - Load the snapshot into the state machine.
     - Respond success.
  3. If lastIncludedIndex <= commitIndex (follower is not actually behind):
     - Keep existing log. Truncate any entries before lastIncludedIndex.
     - Do not replace state machine (it is already past this snapshot).
```

### 10.4 When to Take a Snapshot

The decision of when to snapshot is implementation-specific. Common strategies:

- **Log size threshold**: Take a snapshot when the log exceeds N megabytes (etcd uses
  a configurable threshold, default 100MB).
- **Entry count threshold**: Take a snapshot every M log entries.
- **Time-based**: Take a snapshot every T minutes.
- **Hybrid**: Take a snapshot when log size exceeds N and a minimum of M entries have
  been committed since the last snapshot.

Snapshotting is expensive (serializing the full state machine takes time and CPU). It
should not happen too frequently. But it should happen often enough that the log stays
bounded and follower catch-up is feasible.

### 10.5 Real Incident: CockroachDB Raft Replication Lag

CockroachDB uses Raft for each range (a contiguous key range, typically 64MB). A
production incident involved a cluster where several nodes were offline for an extended
period (firmware updates). When they came back, they needed to receive snapshots from
the Raft leaders of all ranges they were replicas for. Simultaneously receiving hundreds
of large snapshots overloaded the nodes' disk I/O, causing them to time out in responding
to AppendEntries RPCs, which caused additional leader elections, which caused more
snapshot sends. The cluster entered a positive feedback loop.

CockroachDB's engineering team resolved this by rate-limiting snapshot sends (one range
snapshot per node per second, configurable) and prioritizing snapshots for ranges with
the most urgent lag. They also added backpressure: if a node is already receiving N
snapshots, it rejects additional snapshot requests from leaders until it has processed
the in-flight snapshots.

The lesson: even when Raft is technically correct, operational concerns — snapshot
bandwidth, recovery ordering, concurrent snapshot traffic — can cause real outages. Rate
limiting and backpressure are essential production features that no consensus paper
discusses.

### Brainstorming: Log Compaction

**Q: After a snapshot, if the leader needs to send entries to a slow follower, how does
it know to send a snapshot instead of log entries?**

The leader tracks nextIndex[i] for each follower — the next log entry to send that
follower. If nextIndex[i] is less than or equal to the leader's snapshotted index (the
log entries before that index are gone), the leader cannot send those entries. It switches
to sending a snapshot instead. This is a straightforward check: if nextIndex[follower] <
leader.snapshotLastIndex, send InstallSnapshot. Otherwise, send AppendEntries with entries
starting at nextIndex[follower].

The leader's decision is automatic and correct. The only operational concern is the cost
of sending a snapshot. Large state machines produce large snapshots. For a key-value store
with 100GB of data, the snapshot is 100GB. Sending 100GB across the network to a slow
follower is expensive and can take minutes. During this time, the follower is not catching
up on the log and may continue falling further behind on new writes. This is why rate
limiting and snapshot compression are important production features.

**Q: What if a snapshot is taken during an ongoing write operation? Is the snapshot
consistent?**

A correct implementation takes the snapshot at a specific committed log index. The
state machine is in a consistent state at every committed log index (because committed
entries are applied in order, deterministically). Taking a snapshot at index N means
serializing the state machine's state after applying entry N, before applying entry N+1.
This is a consistent point-in-time state.

In practice, taking a snapshot while also applying new entries could cause a race condition.
Implementations handle this by pausing state machine application briefly while copying
state, or by using copy-on-write semantics (the snapshot sees the state at the snapshot
index even as new entries are applied to a copy of the state). etcd uses the former
approach (brief pause), which is acceptable because etcd's state machine (bolt/bbolt
B-tree database) supports transactional reads.

---

## Part 11: Paxos vs. Raft vs. ZAB vs. Viewstamped Replication

### 11.1 The Protocol Landscape

Several consensus protocols exist, each with different origins, design philosophies, and
trade-offs. Understanding where each is used and why is important for interview discussions.

### 11.2 Comparison Table

```
CONSENSUS PROTOCOL COMPARISON
================================

Protocol    | Used In                      | Consensus | Key Feature
------------|------------------------------|-----------|----------------------------
Multi-Paxos | Chubby (Google), Spanner     | Strong    | Original; underspecified;
            | (Google), Cassandra (LWT)    |           | each impl. is a variant
------------|------------------------------|-----------|----------------------------
Raft        | etcd (Kubernetes), CockroachDB| Strong   | Explicit spec; all parts
            | TiKV (TiDB), Consul (HashiCorp)|          | defined; easier to implement
------------|------------------------------|-----------|----------------------------
ZAB         | ZooKeeper (Yahoo/Apache)     | Strong    | Primary-order semantics;
            |                              |           | epoch numbers; designed for
            |                              |           | ZK's specific use case
------------|------------------------------|-----------|----------------------------
Viewstamped | Academic (Liskov & Cowling)  | Strong    | Historically important;
Replication |                              |           | predates Paxos; equivalent
            |                              |           | in power
------------|------------------------------|-----------|----------------------------
EPaxos      | Research; some storage systems| Strong   | Leaderless; non-conflicting
            |                              |           | commands can commit in
            |                              |           | parallel; lower geo latency
------------|------------------------------|-----------|----------------------------
PBFT        | Byzantine fault tolerance    | BFT       | Works even if nodes lie
            | (blockchain adjacent)        |           | (malicious nodes); very
            |                              |           | expensive; N >= 3F+1
------------|------------------------------|-----------|----------------------------
```

### 11.3 ZAB — ZooKeeper Atomic Broadcast

ZAB (ZooKeeper Atomic Broadcast) is the protocol underlying ZooKeeper. It is not quite
Paxos or Raft — it was designed independently for ZooKeeper's specific requirements.

Key differences from Raft:
- **Primary-order semantics**: ZAB ensures that all updates from a given primary are
  delivered in the order the primary sent them, to all replicas. This is a slightly
  stronger property than Raft's log ordering.
- **Epochs instead of terms**: ZAB uses epoch numbers that serve a similar role to
  Raft's terms, but with different mechanics.
- **Broadcast instead of replication**: ZAB is framed as a broadcast protocol. The
  primary broadcasts updates to all other servers. The framing is slightly different
  from Raft's log replication model, though the practical effect is similar.

### 11.4 Real Incident: ZooKeeper Leader Election Outage

In 2015, a major financial services firm running Kafka (which uses ZooKeeper for leader
election) experienced a ZooKeeper leader election outage that lasted 47 minutes. The
root cause: ZooKeeper was running on Java with large heaps (8GB). A full GC pause lasted
18 seconds — far longer than ZooKeeper's session timeout configuration. When the GC
pause ended, ZooKeeper clients had all expired their sessions, and every Kafka broker
lost its topic partition leader assignments simultaneously.

The ZooKeeper cluster itself recovered quickly (the election completed in under 500ms),
but the cascade of Kafka leader re-elections — hundreds of partitions across dozens of
brokers all re-electing simultaneously — took 47 minutes to stabilize. During this time,
no messages could be produced to or consumed from the affected topics.

The fix: reduce Java heap size to reduce GC pause duration, tune ZooKeeper session
timeout to be longer than worst-case GC pause, and stagger broker restart timing. The
deeper lesson: consensus protocol correctness is not the same as operational reliability.
GC pauses, disk slowness, and cascading failures can overwhelm a technically correct
implementation.

### 11.5 Choosing a Protocol for a System Design

In a system design interview, you will almost never be asked to design a new consensus
protocol. Instead, you will choose an existing one (or an existing system that uses one).
The guidance:

- If you need coordination (distributed locks, leader election, service discovery):
  use etcd or ZooKeeper. etcd uses Raft and is the Kubernetes standard. ZooKeeper uses
  ZAB and is the Kafka/Hadoop ecosystem standard.

- If you need a strongly consistent distributed database:
  CockroachDB and TiDB use Raft per shard. Google Spanner uses Paxos per shard. All
  are good choices with different geographic distribution and operational trade-offs.

- If you need geo-distribution with lower latency than Raft:
  Spanner uses TrueTime + Paxos to achieve global consistency with ~7ms read latency.
  CockroachDB uses Raft with follower reads for geo-distribution. EPaxos is an
  academic alternative not widely available as a production system.

### Brainstorming: Protocol Comparison

**Q: Why does ZooKeeper exist separately from etcd? They both provide coordination.
Should new systems use ZooKeeper or etcd?**

ZooKeeper predates etcd by about five years (ZooKeeper 2008, etcd 2013). ZooKeeper was
designed as a general coordination service with a hierarchical namespace (like a
filesystem). Its watch mechanism — receive a notification when a node changes — is a
powerful primitive for building distributed coordination primitives like locks and
barriers. etcd has a similar watch mechanism but uses a flat key space and a more RESTful
API.

For new systems, etcd is generally the better choice for several reasons. First, it is
the Kubernetes standard, so it has massive adoption, extensive testing, and active
development. Second, Raft is fully specified and etcd's implementation is open and
well-understood. Third, etcd's gRPC API is more modern. Fourth, etcd's operational
tooling (etcdctl, embedded in k8s control plane) is excellent.

ZooKeeper remains the choice for systems already deeply integrated with it (Kafka,
Hadoop, HBase). Kafka is actually migrating away from ZooKeeper to KRaft (Kafka's own
Raft implementation) in newer versions, which tells you something about the direction
the industry is moving.

**Q: EPaxos is described as avoiding a leader and committing non-conflicting commands
in parallel. How does it avoid the performance bottleneck of a single leader?**

In Raft and Multi-Paxos, all writes must go through the leader. The leader is a single
point of throughput. In a geo-distributed cluster (say, data centers in US-East, EU-West,
and AP-Southeast), a write from a client in AP-Southeast must travel to the US-East
leader and back — a round trip of perhaps 200ms. This latency is unavoidable in a
leader-based protocol.

EPaxos (Egalitarian Paxos) allows any replica to act as a "command leader" for a specific
command. If two commands do not conflict (do not touch the same key), both can be
committed concurrently by different replicas without coordination. A client in AP-Southeast
submits to the AP-Southeast replica, which acts as command leader for that command, gets
a fast quorum, and commits. The latency is the AP-Southeast local round trip, not the
trans-oceanic round trip.

The catch: EPaxos is significantly harder to implement correctly. Handling conflicting
commands, crash recovery, and log reconstruction is more complex than Raft. As of 2024,
no widely available production system uses EPaxos unmodified. This is a protocol to
mention in an interview as evidence of depth, but Raft remains the right recommendation
for a system design.

---

## Part 12: Interview Application — L5 vs. L6 Answers

### 12.1 How Consensus Questions Appear in Interviews

Consensus questions rarely appear as "explain Paxos to me." They appear embedded in
system design questions:

- "You are designing a distributed key-value store that must be strongly consistent.
  How do you achieve consistency?"

- "How does Kubernetes maintain cluster state? What happens when the API server is down
  but etcd is still running?"

- "How does your distributed lock service ensure two clients never hold the lock
  simultaneously?"

- "What happens to your service during a network partition? How does it behave?"

- "How does Chubby elect a master? What is the protocol?"

- "You are using etcd for leader election. A network issue causes the etcd leader to be
  partitioned. What happens? When does service resume?"

### 12.2 The Five-Level Progression

Here is how answers to "how does etcd maintain consistency?" improve with depth:

**Intern**: etcd is a key-value store used by Kubernetes to store cluster state.

**Junior (L3)**: etcd stores cluster state in a replicated database. It has multiple
replicas so that if one crashes, the others have the data.

**Mid-level (L4)**: etcd uses the Raft consensus protocol. There is one leader and
multiple followers. All writes go to the leader, which replicates them to followers.
An entry is committed when a majority of servers have it.

**Senior (L5)**: etcd uses Raft with a 3 or 5 server configuration. The leader sends
AppendEntries RPCs to followers. An entry at log index N is committed when matchIndex[i]
>= N for a majority of servers i. If the leader crashes, followers time out (election
timeout: 150-300ms), run a leader election using RequestVote RPCs, and the server with
the most up-to-date log wins. The cluster is briefly unavailable for writes during the
election (~200ms typically). During a network partition, the majority side continues
operating; the minority side cannot commit (no majority). This makes etcd CP, not AP.

**Staff (L6)**: All of the above, plus: The election restriction (Candidate must have
log at least as up-to-date as majority) guarantees that committed entries are never lost
during leader transitions. This is the Leader Completeness theorem: any future leader
has all committed entries. After a partition heals, the minority side's high term number
(from failed elections) causes the stale majority-side leader to step down, triggering
another election. The winner will be from the majority side (it has the full committed
log). For read linearizability, etcd uses ReadIndex: the leader records its commit index,
confirms leadership with a heartbeat, then serves the read only after the follower (or
leader itself) has applied up to that index. For operational robustness, etcd requires
fast disks because Raft needs synchronous fsync before responding to clients — slow disk
I/O delays heartbeats and causes spurious elections. We saw this in the Kubernetes etcd
split-brain incidents of 2018-2019. Production etcd clusters should have dedicated SSDs
and careful timeout tuning (heartbeat interval < disk fsync time, election timeout >
worst-case GC pause time).

### 12.3 Specific Interview Questions and Full Answers

**Q: "What happens when a Raft leader receives a write request, the write is appended
to the log, the leader crashes before sending AppendEntries to any follower, and then
a new leader is elected? Is the write lost?"**

**Answer**: The write might be lost, and that is correct behavior. The leader had appended
the entry to its own log but had not yet replicated it to any follower. When the leader
crashes, the entry exists only on the crashed leader. When the new leader is elected, it
does not have the entry. The new leader's log is at least as up-to-date as a majority
of servers, and no server in that majority has the entry (since the crashed leader never
sent AppendEntries). The entry was never committed — the leader never replied to the
client. The client did not receive a success response and must retry the request.

From the client's perspective, the write timed out. The client should retry with an
idempotency key so that the retry does not apply the same operation twice if the original
write did somehow reach a quorum (possible in other failure scenarios). Raft does not
guarantee that writes in progress (unacknowledged) survive leader failures. Only
acknowledged (committed) writes are guaranteed to survive.

**Q: "You have a 5-server etcd cluster. Two servers crash simultaneously. Can the cluster
still commit writes?"**

**Answer**: Yes. With 5 servers and 2 crashed, there are 3 servers remaining. A majority
of 5 is 3. The 3 remaining servers can elect a leader (using RequestVote, the candidate
needs 3 votes out of 5 — it can get its own vote plus the 2 other surviving servers) and
can commit log entries (the leader needs 3 servers to acknowledge an entry, and 3 servers
are available). The cluster is degraded — it can now only tolerate 0 more failures (any
additional crash would drop it below majority) — but it is functional.

If 3 servers crash simultaneously (3 of 5), the remaining 2 servers cannot form a
majority and the cluster is unavailable for writes. It can still serve reads from the
(potentially stale) logs of the remaining 2 servers.

**Q: "How do you ensure that two clients do not both believe they hold a distributed
lock at the same time when using etcd?"**

**Answer**: etcd provides distributed locks via its lease mechanism (or the STM API for
compare-and-swap). A client acquires a lock by creating a key in etcd with a lease
(TTL). If the client dies, the lease expires and the key is deleted, releasing the lock.

The subtlety is that a client that is paused (GC, sleep) might still believe it holds
the lock while the lease has expired and another client has acquired it. This is the
fencing problem. The solution is fencing tokens: etcd returns a monotonically increasing
revision number when a client acquires the lock. The client includes this revision number
in all requests to the backend resource. The backend rejects any request with a lower
revision number than the highest it has seen. If a zombie client (with an expired lock)
sends a request, its revision number is lower than the new lock holder's, and the request
is rejected. This fencing mechanism, combined with etcd's Raft-based consistency, prevents
double-locking even in the presence of GC pauses and network delays.

### 12.4 Common Interview Mistakes — 5 Specific Errors

**Mistake 1: Confusing "replicated" with "committed."**

Saying "a write is committed when the leader sends it to followers" is wrong. A write is
committed when a majority of servers have acknowledged receiving it. The leader sending
it is the start of replication, not the end. If the leader crashes after sending but
before getting majority acknowledgment, the write may or may not be committed depending
on how many followers actually received it.

**Mistake 2: Thinking Raft prevents all data loss.**

Raft guarantees that committed writes are never lost. Uncommitted writes can be lost
during leader failures. If a client does not receive a success response, it should not
assume the write succeeded. The protocol only guarantees durability for writes that
received explicit acknowledgment (the leader replied "OK" to the client, which only
happens after majority commit).

**Mistake 3: Claiming the cluster is available during leader election.**

During leader election (the 150-300ms window), the cluster is unavailable for writes.
Some candidates say "the cluster is always available because the followers can serve
reads." This conflates read availability with write availability. Writes require a
leader. Reads require either a leader or a stale-read-capable follower, depending on
the consistency level. The cluster is CP: during a partition or leader election, write
availability is sacrificed for consistency.

**Mistake 4: Confusing term numbers and log indices.**

A term is an election period (monotonically increasing integer). A log index is the
position of an entry in the log (also monotonically increasing). These are different.
Log entry (index=47, term=3) means the 47th log entry, committed during term 3. A
common mistake: thinking that term=3 means the third log entry, or that all entries in
term=3 have index 3. The term of a log entry is the term of the leader that created it.
Multiple entries can have the same term and different indices.

**Mistake 5: Saying "etcd is available during network partition because the minority
can serve reads."**

This conflates read availability with consistency. Serving reads from the minority side
of a partition returns potentially stale data (because commits happened on the majority
side that the minority has not seen). If you use these stale reads for decisions (e.g.,
"is the lock held?"), you can make incorrect decisions. etcd's strong consistency model
means it rejects reads from the minority side (by default) to preserve consistency.
"Available for stale reads" is not the same as "available."

**Mistake 6: Thinking that adding more servers always improves throughput.**

In a Raft cluster, adding more servers increases fault tolerance but can reduce write
throughput. Every write requires replication to a majority. With 5 servers, replication
goes to 3. With 7 servers, replication goes to 4 servers. Each write now waits for the
4th acknowledgment, which is slower than waiting for the 3rd. The bottleneck is the
slowest server in the quorum. Larger quorums have a higher probability of including a
slow server on any given write. The general guidance: use 3 servers for most production
deployments (tolerates 1 failure), use 5 servers when you need to tolerate 2 simultaneous
failures. Using 7+ servers rarely improves reliability enough to justify the throughput
cost.

### Brainstorming: Interview Application

**Q: If an interviewer asks "how does Chubby elect a master?" and I don't remember
whether Chubby uses Paxos or Raft, what should I do?**

First, you should remember: Chubby uses Paxos. It is one of the classic references.
Google published the Chubby paper in 2006, eight years before Raft. But more importantly,
if you forgot, the right move is to say "I believe Chubby uses a Paxos-derived protocol,
but let me describe the mechanism and you can correct me if I have the wrong name." Then
describe the mechanism: there is a cell of 5 replicas, one of which is elected master
via a Paxos-based vote. The master holds a lease (typically several seconds). The lease
prevents the old master from acting as master after the lease expires, even if it is
still running. A new master is elected by any server that runs Paxos Phase 1, collects
Promises from a majority (3/5), and then sends Accept messages. The new master's term
(analogous to a term number) invalidates the old master's lease upon expiry. This answer
demonstrates genuine understanding of the mechanism, which is what the interviewer cares
about.

**Q: How does understanding consensus protocols change how you design a system at L6
versus L5?**

At L5, you choose etcd or ZooKeeper for coordination and trust that they handle the hard
parts. At L6, you design the system knowing the failure modes of the consensus protocol
underneath. For example, you know that etcd is unavailable for writes for ~200ms during
leader election, so you design your service's client to handle etcd write timeouts
gracefully (retry with backoff, idempotent operations, health check using reads rather
than writes). You know that etcd has a write throughput ceiling (~10,000 writes/second
for most configurations), so you design your system to not put high-frequency writes into
etcd (use etcd for leadership and config, not for high-volume data).

You also know that snapshot transfers can cause I/O spikes, so you plan capacity
accordingly. You know that misconfigured election timeouts (too short) cause unnecessary
elections during GC pauses, so you check the GC profile of etcd (it is Go) and set
timeouts conservatively. You know that the minority partition of etcd returns errors
rather than stale data, so your client code must handle etcd errors without crashing.
These are the design decisions that distinguish L6 from L5: not just knowing which tool
to use, but understanding the operational envelope and failure behavior deeply enough to
build a robust system around it.

---

## Common Interview Mistakes — Summary

Here is a consolidated list of the most common mistakes candidates make when discussing
consensus protocols in system design interviews:

**Mistake 1 — Committed vs. Replicated**: A log entry that has been sent to followers is
"replicated in progress." It is "committed" only when a majority has acknowledged it.
Never say "committed" when you mean "replicated to followers."

**Mistake 2 — Raft Prevents All Data Loss**: Raft only guarantees durability for
committed entries. Unacknowledged writes can be lost during leader failure. Always
mention idempotent retries when discussing write failures.

**Mistake 3 — Cluster Available During Election**: The cluster is unavailable for writes
during leader election (typically 150-300ms). Do not claim otherwise. Mention this as a
known trade-off and explain how to mitigate it (PreVote, shorter timeouts, client-side
retry).

**Mistake 4 — Confusing Terms and Log Indices**: Term = election period. Log index =
position in the log. They are orthogonal. An entry (index=100, term=3) is the 100th
log entry, created during election term 3. Do not confuse them.

**Mistake 5 — Minority Partition Serves Consistent Reads**: The minority side of a Raft
partition may or may not serve reads depending on implementation, but it cannot serve
linearizable reads (its state may be stale). Do not say the minority is "available."
Say it is unavailable for linearizable reads and completely unavailable for writes.

**Mistake 6 — More Servers = More Throughput**: Adding servers increases fault tolerance
but decreases write throughput (larger quorum = wait for more acks = slower). Explicitly
acknowledge this trade-off when recommending cluster sizes.

---

## Exercises

**Exercise 1**: Simulate a 5-server Raft cluster on paper. Start all servers as
Followers in term=1. Server S3 has the shortest timeout and fires first. Trace all
RequestVote and AppendEntries messages for the first complete election and the first
write (command "set y = 99"). Label every message with sender, receiver, and all fields
including term, prevLogIndex, prevLogTerm, etc.

**Exercise 2**: Draw the message timeline for a Paxos round with 3 Acceptors, where
two Proposers (P1 wants "A," P2 wants "B") compete. Show Phase 1 and Phase 2 for both
Proposers. Determine which value is chosen (if any), and explain why.

**Exercise 3**: Explain what happens when a 5-server Raft cluster (3-2 partition) is
asked: (a) to commit a write on the majority side, (b) to commit a write on the minority
side, (c) to serve a read on the minority side. For each, describe the protocol behavior
and the client experience.

**Exercise 4**: Draw the Raft log for a cluster of 5 servers immediately after a leader
crash, showing log inconsistencies (some followers ahead, some behind). Label committed
vs. uncommitted entries. Then trace how the new leader discovers and repairs each
follower's log inconsistency.

**Exercise 5**: You have a 3-server Raft cluster with a 100MB log. Describe the full
snapshot process: what triggers it, what data is in the snapshot, what happens to the
log, and what happens when a lagging follower needs the snapshot rather than log entries.

**Exercise 6**: A client sends a write to a Raft leader. The leader appends to its log
and sends AppendEntries to followers. S2 and S3 acknowledge. Before the leader replies
to the client, the leader crashes. S4 and S5 never received AppendEntries. What is the
state of each server's log? What happens during the next election? Is the write
committed? What must the client do?

**Exercise 7**: Describe the joint consensus membership change in Raft when adding two
servers (S4 and S5) to a 3-server cluster (S1, S2, S3). Trace the log entries for the
C_old,new entry and the C_new entry. For each configuration state (C_old, C_old,new,
C_new), specify the majority requirement.

**Exercise 8**: Compare the behavior of etcd and ZooKeeper in these scenarios: (a) a
single server fails, (b) a majority of servers fail, (c) a 3-2 network partition occurs,
(d) the leader's disk becomes very slow. For each scenario, describe what each system
does and whether there are any behavioral differences.

---

## Homework

**Homework 1**: Read the Raft paper ("In Search of an Understandable Consensus
Algorithm," Ongaro and Ousterhout, 2014). Focus on Sections 3-7. After reading, write
a 500-word explanation of one aspect of Raft that surprised you or that you found
especially elegant. Compare it to how Paxos handles the same concern.

**Homework 2**: Install etcd locally (or use a Docker container). Use etcdctl to observe
cluster behavior: (a) check cluster health, (b) write and read a key, (c) forcefully
stop the leader and observe the election (monitor with etcdctl endpoint health and
etcdctl get on the key). Write a paragraph describing what you observed and how it maps
to the Raft protocol.

**Homework 3**: Read the Chubby paper ("The Chubby lock service for loosely-coupled
distributed systems," Burrows, 2006). Identify three design decisions in Chubby that
are motivated by the limitations of Paxos (the underspecification, the need for lease
mechanism, etc.). Write a one-paragraph explanation for each decision.

**Homework 4**: Find a public post-mortem or incident report involving etcd, ZooKeeper,
or a distributed consensus system (GitHub issues, public blog posts, HackerNews threads).
Summarize: what failed, what the root cause was, and which part of the consensus protocol
(leader election, log replication, snapshot, membership change) was implicated. Explain
whether the failure was a protocol correctness bug or an operational/configuration issue.

**Homework 5**: Design a simple distributed counter service using etcd as the consensus
layer. The counter must support: increment (atomic, linearizable), read (strongly
consistent), and reset (atomic, conditional on current value). Write pseudocode for the
client library that uses etcd's compare-and-swap. Address the following: how does the
client handle etcd being unavailable? How does it handle etcd returning a conflict on
compare-and-swap? How does it ensure the increment is idempotent across retries?

---

## KEY TAKEAWAYS

```
+------------------------------------------------------------------+
|                    CONSENSUS DEEP DIVE — KEY TAKEAWAYS           |
+------------------------------------------------------------------+
|                                                                  |
| CONSENSUS PROBLEM                                                |
|   • N processes must agree on one value despite crashes and      |
|     message delays                                               |
|   • FLP: impossible in purely async systems with any crash       |
|   • Practical escape: timeouts (assume crashed if no response)   |
|   • Consensus enables replicated state machines: same commands   |
|     in same order -> same state on all replicas                  |
|                                                                  |
| PAXOS                                                            |
|   • Phase 1 (Prepare/Promise): reserve a proposal number,       |
|     learn any previously accepted values                         |
|   • Phase 2 (Accept/Accepted): propose value, collect majority  |
|   • Safety: quorum overlap ensures any two majorities share      |
|     at least one server that knows the old decision              |
|   • Underspecified: leader election, log compaction, membership  |
|     changes all left undefined                                   |
|                                                                  |
| RAFT                                                             |
|   • Three states: Follower -> Candidate -> Leader                |
|   • Terms: logical clocks; old leaders step down on seeing      |
|     higher term                                                  |
|   • Leader election: RequestVote RPC, majority wins, randomized  |
|     timeouts prevent split votes                                 |
|   • Log replication: AppendEntries RPC, commit on majority ack  |
|   • Safety: election restriction (must have up-to-date log);    |
|     log matching; leader completeness                            |
|                                                                  |
| NETWORK PARTITIONS                                               |
|   • Majority side continues; minority side cannot commit         |
|   • Raft is CP (consistency + partition tolerance)               |
|   • Write unavailability during election: ~150-300ms             |
|                                                                  |
| OPERATIONAL CONCERNS                                             |
|   • Disk I/O delay looks like crash to other servers             |
|   • GC pauses can trigger spurious elections                     |
|   • Rate-limit snapshot sends; backpressure for lagging followers|
|   • Fencing tokens required for distributed locks                |
|                                                                  |
| WHERE EACH PROTOCOL IS USED                                      |
|   • Paxos: Chubby, Spanner (Google)                              |
|   • Raft: etcd (Kubernetes), CockroachDB, TiKV, Consul           |
|   • ZAB: ZooKeeper (Kafka, Hadoop ecosystem)                     |
|                                                                  |
| L6 SIGNALS IN INTERVIEWS                                         |
|   • Explain committed vs. replicated                             |
|   • Trace AppendEntries fields (term, prevLogIndex, prevLogTerm, |
|     entries, leaderCommit)                                       |
|   • Explain why committed entries survive leader election        |
|     (election restriction + leader completeness theorem)         |
|   • Describe partition behavior: CP, minority unavailable        |
|   • Cite operational failure modes: disk I/O, GC pauses,        |
|     snapshot storms                                              |
|   • Mention fencing tokens for distributed locks on top of Raft  |
+------------------------------------------------------------------+
```

---

---

## Part 13: Byzantine Fault Tolerance — Why Raft Is Not Enough for All Settings

### 13.1 CFT vs BFT

Raft (and Paxos) are **crash fault tolerant (CFT)**: they assume nodes fail by stopping.
A crashed node does not respond. It does not send corrupted messages. It does not lie.

**Byzantine fault tolerant (BFT)** protocols handle a stronger threat model: nodes may
behave arbitrarily. A byzantine node can send inconsistent messages to different peers,
lie about its state, or coordinate with other byzantine nodes to subvert the protocol.

```
CFT MODEL:        Node fails → stops sending messages. Other nodes time out and elect new leader.
                  Raft handles this correctly. Requires f+1 nodes for f failures: 3 nodes for 1 failure.

BFT MODEL:        Node fails → might send different messages to different peers.
                  Raft is BROKEN under this model. A byzantine leader can split the cluster.
                  Requires 3f+1 nodes for f failures: 4 nodes for 1 byzantine node.

WHEN DOES BFT MATTER?
  - Blockchain consensus (Bitcoin, Ethereum, Hyperledger): nodes are untrusted peers
  - Cross-organizational coordination where no single organization controls all nodes
  - Space systems where cosmic ray bit flips can corrupt node behavior

WHEN DOES BFT NOT MATTER (i.e., CFT is sufficient)?
  - Internal distributed systems where all nodes are owned by one organization
  - All standard databases: etcd, ZooKeeper, CockroachDB, Spanner
  - Kafka, HDFS, Redis Cluster
  Reason: an attacker who controls a node in your internal infrastructure has already
  won (they have your data). BFT doesn't protect against this threat.
```

**The key interview point:** "Raft is CFT, not BFT. For internal systems (all nodes owned
by one org), CFT is the correct and sufficient model. BFT adds 2-3× message overhead
and is only needed when nodes are untrusted — like in public blockchain networks."

### 13.2 Practical BFT: PBFT, Tendermint, HotStuff

For completeness (L6 awareness, not L5 requirement):

- **PBFT (Practical Byzantine Fault Tolerance)**: O(n²) message complexity, impractical
  above ~20 nodes. The first practical BFT algorithm (1999).
- **Tendermint**: Used in Cosmos blockchain. O(n) message complexity per round.
- **HotStuff**: Used in Diem (Meta's blockchain). O(n) complexity, pipelined rounds.

None of these are used in standard distributed databases. If an interviewer asks "what
about Byzantine faults in Raft?", the answer is: "Raft doesn't handle byzantine faults —
it's CFT only. For systems with untrusted nodes (blockchain, cross-org consensus), you'd
use a BFT protocol like PBFT or HotStuff. For internal systems, CFT is the right model."

---

## Part 14: etcd and Consul in Practice

Consensus is an academic concept; etcd and Consul are where engineers actually encounter
it in production. Know both.

### 14.1 etcd

etcd is the distributed key-value store at the heart of Kubernetes. It uses Raft.

```
ETCD FACTS:
  - Raft consensus with 3 or 5 nodes typical
  - Stores Kubernetes cluster state: all API objects (Pods, Services, ConfigMaps, etc.)
  - Linearizable reads by default (reads from leader, guaranteed up-to-date)
  - Serializable reads (lower consistency, any follower) available with --serializable flag
  - MVCC: keeps previous versions for a configurable period; compaction needed
  - Watches: clients subscribe to key changes — etcd streams updates (Raft log notification)
  - Max recommended DB size: 8GB (larger = slow defragmentation + election pressure)
  - Performance: ~10,000 writes/second, ~100,000 reads/second on typical hardware

OPERATIONAL CONCERN:
  etcd is the source of truth for Kubernetes. If etcd loses quorum:
  - Kubernetes API server returns errors to all API calls
  - No new Pods scheduled; no existing Pod changes acknowledged
  - Existing Pods CONTINUE running (kubelet operates autonomously from etcd)
  - Recovery: restore from etcd backup (snapshot + WAL replay)
  
  This is why Kubernetes production setups use 5-node etcd clusters (tolerates 2 failures).
```

### 14.2 Consul

Consul (HashiCorp) combines: distributed key-value store, service discovery, and health
checking. Uses Raft for the key-value store. DNS interface for service discovery.

```
CONSUL vs ETCD:
  etcd: pure KV store with watches. No service discovery built in.
  Consul: KV store + service catalog + health checks + DNS + ACLs.
  
  Kubernetes uses etcd directly. Traditional microservices often use Consul for
  service discovery outside of Kubernetes.

CONSUL RAFT CLUSTER:
  3 or 5 server nodes run Raft. Data centers connected via gossip (WAN federation).
  Leader handles all writes. Followers serve reads (stale reads) or forward to leader.
  
  Common interview question: "How does Consul guarantee consistency for service discovery?"
  Answer: Service registrations go through Raft. A service is registered only when the
  registration entry is committed to the Raft log on a quorum of servers. Health check
  results are stored in Raft but with a shorter propagation path via gossip.
```

---

## Part 15: Pre-Interview Drill — Consensus

### 15.1 The Four Questions You Must Answer Without Hesitation

**"Explain Raft leader election in 60 seconds."**
"Raft servers start as followers. If a follower doesn't hear from the leader within the
election timeout (random 150-300ms), it becomes a candidate, increments its term, and sends
RequestVote RPCs to all peers. A server grants a vote if: (a) the candidate's term ≥ the
voter's current term, and (b) the candidate's log is at least as up-to-date as the voter's.
A candidate that receives votes from a majority becomes leader and immediately sends
heartbeat AppendEntries to assert authority. The random timeout is what prevents split votes."

**"What happens to Raft during a network partition?"**
"The partition splits the cluster into two groups. If the leader is in the minority partition:
it can't commit new entries (no majority ack). The majority partition elects a new leader.
After healing, the old leader discovers a higher term, steps down, and its uncommitted
entries are overwritten by the new leader's log. If the leader is in the majority: it
continues operating normally. The minority partition cannot make progress. Raft is CP
(consistent, partition-tolerant, not always available)."

**"How many nodes do you need to tolerate f failures in Raft?"**
"2f+1 nodes. For 1 failure: 3 nodes. For 2 failures: 5 nodes. The majority quorum
requires ⌊(2f+1)/2⌋ + 1 = f+1 nodes, which is always achievable when at most f nodes fail."

**"What is the difference between Paxos and Raft?"**
"They solve the same problem (consensus on a value). Paxos defines only the single-value
case (Single-Decree Paxos); Multi-Paxos (a sequence of Paxos instances for a log) requires
additional engineering not specified in the original paper. Raft was designed from the start
as a replicated log with explicit leader election, log matching invariant, and leader
completeness theorem — it's easier to understand and implement correctly. Google uses
Multi-Paxos (Spanner, Chubby); etcd/CockroachDB use Raft."

### 15.2 Self-Check Before the Interview

```
[ ] Can explain the consensus problem in one sentence?
[ ] Knows the 2f+1 quorum formula?
[ ] Can describe Raft leader election (random timeout, RequestVote, majority vote)?
[ ] Can describe log replication (AppendEntries, commit when majority ACK)?
[ ] Can explain what happens during a network partition (CP, minority unavailable)?
[ ] Knows the leader completeness theorem (committed entries survive elections)?
[ ] Can distinguish CFT vs BFT (Raft is CFT)?
[ ] Can name where Raft is used in production (etcd, CockroachDB, TiKV)?
[ ] Can name where Paxos is used (Spanner, Chubby, Zookeeper)?
[ ] Knows the 3-node vs 5-node tradeoff (3 tolerates 1 failure, 5 tolerates 2)?
[ ] Can explain log compaction / snapshots (needed to prevent log growth)?
[ ] Knows the CAP position of Raft (CP, not AP)?
```

### 15.3 Common Interview One-Liners

```
"Raft requires majority quorum for both leader election and log commitment."
"The random election timeout prevents split votes by making simultaneous candidacies rare."
"Committed = majority of servers have the entry in their log."
"Raft is CP: it sacrifices availability for consistency during partitions."
"etcd uses Raft; Spanner and Chubby use Paxos."
"Raft is CFT only — byzantine faults require PBFT or HotStuff."
"A 5-node Raft cluster tolerates 2 simultaneous failures; 3-node tolerates 1."
"Log compaction prevents log growth: snapshot = apply all committed entries, discard old log."
"Joint consensus handles membership changes (add/remove nodes) without split-brain."
```

---

## Part 16: Key Numbers and Production Reality

Numbers interviewers expect you to know cold.

### 16.1 Consensus Latency Budget

```
RAFT WRITE LATENCY (typical):
  Leader receives write request           →  0ms
  Leader appends to local log             →  ~0.1ms (memory write)
  Leader sends AppendEntries to followers →  ~0.5ms (serialization)
  Network RTT to followers                →  0.5-5ms (same DC), 50-150ms (cross-region)
  Follower appends and ACKs               →  ~0.1ms
  Leader receives majority ACK            →  = RTT
  Leader commits, applies, responds       →  ~0.1ms
  
  SAME DATACENTER TOTAL: ~2-5ms per write
  CROSS-REGION (WAN): 100-300ms per write (dominates: RTT)

WHY THIS MATTERS:
  etcd benchmarks: ~10,000 writes/second on a 3-node cluster in the same DC
  Spanner (multi-Paxos across DCs): 5-10ms typical (uses TrueTime to minimize wait)
  ZooKeeper: ~30,000 writes/second on LAN (ZAB protocol, batching helps)
```

### 16.2 Cluster Size Tradeoffs

```
NODES   FAILURES TOLERATED   QUORUM SIZE   WRITE LATENCY   USE CASE
  3           1                   2         Lowest          Dev/small prod, etcd default
  5           2                   3         +1 RTT          Production standard (Kubernetes)
  7           3                   4         +2 RTT          Critical data, additional resilience
  9+          4+                  5+        High            Rarely justified; ZAB does this

RULE: Add nodes for resilience, not performance. More nodes = more latency for writes
(must wait for larger quorum). Only add beyond 5 nodes if risk model demands it.
```

### 16.3 Operational Numbers

```
ETCD:
  Max DB size:      8GB recommended (compaction/defrag slow above this)
  Max key size:     1.5MB
  Max request size: 1.5MB
  Disk requirement: dedicated SSD, fsync on every commit (NFS will break etcd)
  Backup:           Snapshot every 30min + WAL retained for at least 1 snapshot interval
  Recovery RTO:     ~2-5 minutes from snapshot (WAL replay)

ZOOKEEPER:
  Data stored in memory, flushed to disk; all data must fit in memory
  Transaction log: append-only, needs dedicated disk to avoid competition with snapshots
  Leader election after partition healing: ~200-500ms

KAFKA (KRAFT MODE):
  Replaced ZooKeeper in Kafka 3.3+ (KRaft)
  Raft metadata quorum: 3 controllers
  Scales to millions of partitions vs ZooKeeper's ~200,000 limit
```

### 16.4 The L5 vs L6 Calibration

```
L5 (Senior SWE) — expected to know:
  ✓ Raft leader election mechanism
  ✓ Log replication and commit rule (majority ACK)
  ✓ CAP theorem: Raft is CP
  ✓ Network partition behavior
  ✓ Why you need 2f+1 nodes for f failures
  ✓ etcd is Raft, ZooKeeper is ZAB, Spanner is Multi-Paxos
  ✓ Why consensus is needed (split-brain without it)

L6 (Staff SWE) — additional depth:
  ✓ Log matching invariant and leader completeness theorem
  ✓ Joint consensus for membership changes
  ✓ Log compaction / snapshot mechanism
  ✓ CFT vs BFT distinction and when each is needed
  ✓ Operational concerns: etcd disk requirements, compaction, defragmentation
  ✓ Paxos Phase 1/Phase 2 in detail and why Multi-Paxos needs engineering
  ✓ ZAB vs Raft differences (ZAB uses epoch+counter, Raft uses term+index)
  ✓ Performance numbers: write latency budget, quorum size tradeoffs
  ✓ When NOT to use consensus (disaggregate control plane from data plane)

TRAP QUESTION AT L6:
  "Should every distributed write go through Raft?"
  WRONG: "Yes, Raft guarantees consistency."
  CORRECT: "No. Raft is for the control plane (metadata, configuration, leader election).
  The data plane should be partition-local with consistency enforced at the application
  layer. Google Spanner uses Paxos per shard but serves reads from followers with
  external consistency via TrueTime — not all reads go through the leader."
```

---

*This chapter pairs with:*
- *Ch22: Leader Election and Coordination — builds directly on Part 5*
- *Ch31: Caching at Scale — etcd used for cache invalidation coordination*
- *Ch33: Event-Driven Architectures — Kafka relies on ZooKeeper/KRaft*
- *Appendix B: Chubby — Paxos in production (Google)*
- *Appendix C: Spanner — Paxos per shard + TrueTime*

*Chapter 48 — Section 4: Deep Technical Foundations.*
*Core concepts: Raft (leader election + log replication + safety), Paxos, CFT vs BFT,*
*network partition behavior (CP), quorum formula (2f+1), log compaction, etcd in production.*
*Key numbers: election timeout 150-300ms random, majority = ⌊n/2⌋+1, etcd max 8GB,*
*write latency ~2-5ms (same DC), ~100-300ms (cross-region), 10K writes/sec etcd capacity.*
*Protocol map: etcd → Raft, ZooKeeper → ZAB, Spanner → Multi-Paxos, Kafka 3.3+ → KRaft.*
*Safety rule: 2f+1 nodes for f failures (3-node: tolerates 1, 5-node: tolerates 2).*
*CAP position: CP — Raft always consistent, unavailable during minority partition.*
*Operational footprint: 3-node for dev/small prod, 5-node standard, 7-node for critical data.*
*BFT threshold: 3f+1 nodes required (4 nodes to tolerate 1 byzantine fault) vs CFT 2f+1.*
*Do not use consensus for data plane — use it only for control plane (metadata, leadership).*
*Disk requirement for etcd: dedicated SSD with fsync on every commit. NFS will corrupt etcd.*
*Snapshot interval: compact WAL every 10,000 entries or every 5 minutes, whichever comes first.*
*Follower reads: allowed in etcd with --serializable (stale), linearizable requires leader.*
*Last updated: 2026-06-25. System Design for L6: The Complete Guide.*
