# Chapter 41e: Consensus Deep Dive — Raft & Paxos, Step by Step

> Consensus is mentioned in dozens of chapters (Chubby uses Paxos, etcd uses Raft,
> Spanner uses Paxos per shard) but never explained mechanically. This chapter builds
> the intuition from scratch: why consensus is hard, what Paxos actually does,
> why Raft was designed to be more understandable, and what "leader election" means
> at the protocol level.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

"How does leader election work?" and "how does your system achieve consistency across
replicas?" are L6 questions at Google, Amazon, and any company running distributed
databases or coordination services. Saying "we use Raft" is L4. Explaining the two-phase
protocol, why a majority quorum suffices, what happens during a network partition, and
how log compaction works is L6. This chapter builds that mechanical understanding.

---

## Planned Content

### Part 1: The Consensus Problem
- Formal definition: N processes must agree on a single value, even if some processes fail
- Why it's hard: messages can be delayed, reordered, or lost; processes can crash
- FLP impossibility: in an asynchronous system with even one faulty process, consensus
  is impossible to guarantee (Fisher-Lynch-Paterson, 1985)
- The practical escape: add timing assumptions (timeouts) → consensus becomes solvable
- What consensus enables: replicated state machines — all replicas execute the same
  commands in the same order → always in the same state

### Part 2: Paxos — The Original Protocol
- Three roles: Proposer (wants to get a value agreed), Acceptor (votes), Learner (learns result)
- Phase 1 (Prepare): Proposer sends Prepare(n) to majority of acceptors
  → Acceptors respond with Promise(n) + any previously accepted value
- Phase 2 (Accept): Proposer sends Accept(n, v) to majority
  → Acceptors accept if n >= their promised n
- Safety property: if a value v was accepted by a majority, any future proposal must
  also propose v (guaranteed by Phase 1 response carrying previously accepted values)
- Multi-Paxos: run Paxos repeatedly for a log of commands (one slot per log entry)
  → elect a stable leader to skip Phase 1 for subsequent entries
- Why Paxos is hard to implement: underspecified for many practical concerns
  (leader election, log compaction, membership changes, client interaction)

### Part 3: Raft — Consensus for Understandability
- Designed explicitly to be easier to understand than Paxos
- Three sub-problems: leader election + log replication + safety
- Leader election:
  - Servers start as Followers, wait for heartbeats from Leader
  - Election timeout (150–300ms): if no heartbeat → become Candidate → send RequestVote
  - Candidate wins if it gets votes from majority of servers
  - Term number: monotonically increasing; prevents old leaders from causing split-brain
- Log replication:
  - All writes go to Leader → Leader appends to log → sends AppendEntries to Followers
  - Entry is committed when majority of servers have it in their log
  - Leader sends committed index → Followers apply committed entries to state machine
- ASCII diagram: Raft leader election state machine (Follower → Candidate → Leader)

### Part 4: Log Replication Step by Step
```
Client → Leader: "set x = 5"

Leader:
  1. Appends entry (term=3, index=47, cmd="set x=5") to its log
  2. Sends AppendEntries RPC to all Followers in parallel
  3. Waits for majority (3/5) to acknowledge
  4. Marks entry as committed (commitIndex = 47)
  5. Applies "set x=5" to state machine
  6. Responds to client: "OK"
  7. Next AppendEntries carries commitIndex=47 → Followers also apply

Follower receives AppendEntries(term=3, prevIndex=46, prevTerm=3, entries=[...]):
  1. Verify prevIndex and prevTerm match local log (log consistency check)
  2. Append new entries
  3. Update commitIndex = min(leaderCommit, last log index)
  4. Apply newly committed entries to state machine
  5. Respond: success
```

### Part 5: Leader Election Step by Step
```
Normal operation: Leader sends heartbeat (empty AppendEntries) every 50ms
Follower election timeout: 150–300ms (randomized to avoid split votes)

Scenario: Leader crashes at T=0

T=150ms: Follower A's timeout expires, no heartbeat received
  A increments term: term 4
  A votes for itself
  A sends RequestVote(term=4, candidateId=A, lastLogIndex=47, lastLogTerm=3)

T=152ms: Follower B receives RequestVote from A
  B checks: is A's log at least as up-to-date as mine? (lastLogIndex=47, lastLogTerm=3)
  B's log: index=47, term=3 → same → A is at least as up-to-date
  B grants vote, updates votedFor=A, responds: voteGranted=true

T=154ms: A receives votes from B, C (majority of 5)
  A becomes Leader for term 4
  A immediately sends heartbeats to establish authority
  D, E receive heartbeat → revert to Follower state for term 4
```

### Part 6: Safety — Why Raft Never Loses Committed Data
- Election restriction: a candidate must have a log at least as up-to-date as majority
  → a server with stale log cannot win election → committed entries are never lost
- Log matching property: if two logs have the same index and term, they are identical
  up to that point (enforced by AppendEntries consistency check)
- Leader completeness: if an entry is committed, every future leader has it

### Part 7: Membership Changes (Adding/Removing Servers)
- Naive approach: switch from old config to new config simultaneously → possible split vote
- Raft solution: joint consensus (two-phase config change)
  - Phase 1: enter joint config (old ∪ new) → requires majority of BOTH old and new
  - Phase 2: commit new config once joint config is committed
- etcd uses a simpler single-server-at-a-time approach for most membership changes

### Part 8: Log Compaction (Snapshots)
- Problem: log grows forever; replaying from beginning is too slow
- Solution: periodic snapshots of the state machine + truncate log up to snapshot point
- Snapshot includes: state machine state + last included index + last included term
- InstallSnapshot RPC: Leader sends snapshot to Followers that are too far behind
- After snapshot: log starts from snapshot point, not from index 0

### Part 9: Paxos vs. Raft vs. ZAB vs. Viewstamped Replication
| Protocol | Used In | Key Difference |
|----------|---------|----------------|
| Multi-Paxos | Chubby, Spanner, Cassandra | Original; underspecified; many variants |
| Raft | etcd, CockroachDB, TiKV | Explicit leader; designed for understandability |
| ZAB | ZooKeeper | Leader-based; primary-order semantics |
| Viewstamped Replication | Academic | Historical; similar to Paxos |

### Part 10: Interview Application
- "How does etcd maintain consistency?" → Raft: leader election + log replication + majority quorum
- "What happens during a network partition?" → minority partition cannot commit (no majority)
  → majority partition continues with potentially a new leader (CP, not AP)
- "How does Chubby elect a master?" → Paxos-based election in the 5-replica cell
- L5 vs. L6: L5 says "uses Raft for consensus"; L6 traces the AppendEntries flow,
  explains why majority quorum suffices for safety, and what happens to availability
  during leader election (brief unavailability, typically 150–300ms)

---

## The One-Sentence Summary

> "Consensus (Raft/Paxos) achieves agreement across replicas by requiring a majority quorum for every committed write — in Raft, the leader replicates log entries, waits for majority acknowledgment, then commits; a new leader can only be elected if its log is as up-to-date as the majority, which guarantees committed entries are never lost even if the leader crashes."

---

*Full chapter: ~2,500 lines. Pairs with Ch22 (Leader Election) and Ch86 (Chubby — uses Paxos).*
