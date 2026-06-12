# Chapter 26 Supplement: Advanced Distributed Systems — 3PC, HLC, CRDTs, Read Consistency, and Chaos Engineering

---

# Introduction

Chapter 20 covers the core distributed systems landscape—consensus, transactions, failure modes. This supplement extends that foundation with advanced concepts that Staff engineers encounter in production and interviews: **Three-Phase Commit (3PC)**, **Read-Your-Writes and Monotonic Reads**, **Hybrid Logical Clocks (HLC)**, **Conflict-Free Replicated Data Types (CRDTs)**, and **Chaos Engineering**. These topics (301, 310, 316–319) represent the edge of distributed systems thinking—where theory meets reality and where many interviewers probe for depth.

**The Staff Engineer's Advanced Distributed Principle**: You don't need to implement 3PC or design a CRDT from scratch. You do need to understand *why* 3PC is rarely used, *when* read-your-writes matters, *how* HLC solves the physical vs logical clock tension, *what* CRDTs offer that last-write-wins does not, and *why* chaos engineering is a culture, not a tool. These concepts shape real systems—CockroachDB, Figma, Netflix—and your ability to reason about them signals Staff-level fluency.

---

## Visual 1: Chapter at a Glance

```
╔═════════════════════════════════════════════════════════════════════════════╗
║   CHAPTER AT A GLANCE: Advanced Distributed Systems                         ║
║   Core Concept: Theory meets reality — Staff-level fluency in distributed  ║
║   consensus, consistency, ordering, conflict-free merge, and chaos         ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║   TOPIC FLOW DIAGRAM:                                                      ║
║   ┌─────┐   ┌─────────────┐   ┌─────┐   ┌──────────┐   ┌───────┐          ║
║   │ 3PC │ → │ Read Consist │ → │ HLC │ → │  CRDTs   │ → │ Chaos │          ║
║   └──┬──┘   └──────┬──────┘   └──┬──┘   └────┬─────┘   └───┬───┘          ║
║      │             │             │            │              │              ║
║      ▼             ▼             ▼            ▼              ▼              ║
║   "Why not?"   "Your write"   "Order +    "Merge both"  "Break it        ║
║   Partitions   must be       real time"   no conflict"  on purpose"       ║
║   break it     visible                     Figma-style                      ║
║                                                                            ║
║   KEY TAKEAWAYS:                                                           ║
║   1. 3PC stays in textbooks — partitions violate failure-detection         ║
║      assumption; 2PC+recovery or Raft wins in production                   ║
║   2. Read-your-writes: route (user_id, last_write_ts) to primary           ║
║      within lag threshold — critical for UX and correctness                ║
║   3. HLC = (physical, logical, node_id) — CockroachDB, YugabyteDB use it   ║
║   4. CRDTs merge without coordination — OR-Set for lists, no LWW data loss ║
║   5. Chaos is culture: define steady state → hypothesize → inject → fix    ║
║                                                                            ║
╚═════════════════════════════════════════════════════════════════════════════╝
```

---

## Quick Visual: Advanced Distributed Systems at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   ADVANCED DISTRIBUTED: THE GAPS THAT STAFF ENGINEERS FILL                   │
│                                                                             │
│   L5 Framing: "We use 2PC / Raft / read replicas / CRDTs"                   │
│   L6 Framing: "We chose 2PC over 3PC because partitions break 3PC; we use   │
│                read-your-writes for session consistency; HLC for ordering;  │
│                CRDTs for collaborative editing; chaos to find weaknesses" │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  3PC: Non-blocking in theory. Partition-prone in practice.          │   │
│   │  Why 2PC + recovery logs beat 3PC in production.                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  READ CONSISTENCY: Read-your-writes, monotonic reads, consistent      │   │
│   │  prefix. Hierarchy: linearizability > sequential > causal > RYW.     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  HLC: Physical time + logical counter. Order + real time.           │   │
│   │  CockroachDB, YugabyteDB. Bounded clock uncertainty.                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  CRDTs: Merge without conflict. Commutative, associative.           │   │
│   │  Figma, Riak, collaborative apps. No "last write wins" data loss.    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  CHAOS: Break it on purpose. Find weaknesses. Build immunity.         │   │
│   │  Culture > tool. Start small. Game days. Blast radius control.      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Advanced Distributed Systems Thinking

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **3PC vs 2PC** | "3PC is better because it's non-blocking" | "3PC assumes reliable failure detection. In a network partition, we can't tell 'coordinator dead' from 'coordinator unreachable.' Participants in different partitions can make different decisions. 2PC with recovery logs handles coordinator failure; Raft/Paxos handle consensus without a coordinator. 3PC stays in textbooks." |
| **Read-your-writes** | "We use read replicas for scale" | "Read-your-writes requires routing recent writers to the primary. We track (user_id, last_write_ts). If now - last_write_ts < replica_lag_threshold, read from primary. Otherwise, read from replica. Small % of reads hit primary; users never see their own write disappear." |
| **Monotonic reads** | "Sticky sessions fix it" | "Sticky routing ensures same replica per user—no backward jumps. Alternative: version-aware reads. Client sends highest version seen; server rejects or delays staler responses. Sticky is simpler; version-aware works across devices." |
| **CRDTs** | "We use last-write-wins for conflicts" | "LWW loses data when two users edit the same field offline. For collaborative lists, OR-Set. Each add/remove gets a unique tag. Merge = union of adds minus union of removes. Both additions survive. Figma uses CRDT-like structures for vector graphics." |
| **Chaos engineering** | "We run Chaos Monkey" | "Chaos is a culture: define steady state, hypothesize, inject, observe, fix. Start with game days—planned chaos with the team watching. Then automated chaos in staging. Prod chaos only after runbooks are tested. Blast radius control: one instance, then one AZ, then one region." |

**Key Difference**: L6 engineers connect mechanisms to failure modes, partition scenarios, and operational reality. They know when theory breaks down and what production systems actually do.

---

# Part 1: Three-Phase Commit (3PC) — Why Rarely Used (Topic 301)

## Context: Distributed Transactions and 2PC

Distributed transactions span multiple participants—databases, message queues, caches. The goal: **atomicity**—all commit or all abort. No partial state. Two-Phase Commit (2PC) is the classic algorithm: a coordinator asks participants to prepare; if all say yes, coordinator tells them to commit. It works when everything works. The problem is failure.

## The 2PC Problem: Blocking When the Coordinator Crashes

Two-Phase Commit (2PC) is the workhorse of distributed transactions. The coordinator asks participants: "Can you commit?" (Phase 1: Prepare). All say yes. Coordinator says: "Commit!" (Phase 2: Commit). Everyone commits. Simple.

**The failure case**: The coordinator crashes *after* participants voted "yes" in Prepare but *before* sending "Commit." Participants are now **stuck**:

- They cannot **commit**—they need the coordinator's go-ahead.
- They cannot **abort**—someone might have already committed (in some implementations, a participant could commit after voting yes if it receives commit from another participant).
- They hold **locks** indefinitely. No one can proceed. Manual intervention required.

```
    2PC BLOCKING SCENARIO

    COORDINATOR          PARTICIPANT A      PARTICIPANT B

    1. PREPARE?  ----------->  (prepare)  ------>  (prepare)
       <--------- YES  ----  YES  <--------------- YES

    2. [COORDINATOR CRASHES HERE]
       Participants: holding locks, waiting...
       Can't commit (no go-ahead)
       Can't abort (might violate atomicity)
       STUCK. Indefinitely.
```

### Visual: 2PC — The Wedding Ceremony Analogy

```
╔═════════════════════════════════════════════════════════════════════════════╗
║   2PC: THE WEDDING CEREMONY — Why Everyone Gets Stuck                       ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║   COORDINATOR = Minister    PARTICIPANTS = Bride & Groom                    ║
║                                                                            ║
║   PHASE 1 (PREPARE):                                                       ║
║   Minister: "Do you take this person...?"  ──►  Both: "I do" (VOTE YES)      ║
║                                                                            ║
║   PHASE 2 (COMMIT):                                                        ║
║   Minister: "I now pronounce you..."      ──►  Wedding complete!           ║
║                                                                            ║
║   ─── IF EITHER SAYS "NO" ───                                             ║
║   Minister: "Ceremony cancelled." (ABORT) ✓                                 ║
║                                                                            ║
║   ─── THE BLOCKING PROBLEM ───                                              ║
║   Minister gets votes "I do" ... then FAINTS before saying "pronounce"!    ║
║                                                                            ║
║   Bride & Groom: "Now what? We said yes, but no one pronounced us..."       ║
║   • Can't marry (no go-ahead from minister)                                 ║
║   • Can't leave (maybe minister will wake up and commit?)                   ║
║   • EVERYONE STUCK. Waiting. Forever.                                       ║
║                                                                            ║
║   That's 2PC blocking: coordinator dies after PREPARE → participants stuck. ║
║                                                                            ║
╚═════════════════════════════════════════════════════════════════════════════╝
```

Locks block other transactions. Users see timeouts. Recovery requires reading coordinator logs, querying participants, and manually deciding commit or abort. Painful.

## The 3PC Solution: Add a Pre-Commit Phase

Three-Phase Commit adds a **third phase** between Prepare and Commit: **Pre-Commit**.

```
    3PC PHASES

    Phase 1: CanCommit?   — Coordinator: "Can you do it?" Participants: "Yes"
    Phase 2: PreCommit    — Coordinator: "We're about to commit. Hold tight."
    Phase 3: DoCommit      — Coordinator: "Go!" Everyone commits.
```

The insight: after PreCommit, participants **know the intent**. Everyone voted yes. Everyone acknowledged "we're about to commit." If the coordinator crashes now, participants can use **timeouts**: "I haven't heard from the coordinator. Everyone else pre-committed. I'll commit." No blocking. They proceed independently.

## ASCII Diagram: 3PC vs 2PC Message Flow

```
    2PC (Two Phases)
    ────────────────

    Coordinator          Part A         Part B

    PREPARE?  --------------> (prepare) --------> (prepare)
               <----- YES ---- YES <------------- YES

    COMMIT    --------------> (commit) --------> (commit)
               <----- DONE ---- DONE <----------- DONE

    If coordinator dies after PREPARE: participants BLOCKED.


    3PC (Three Phases)
    ──────────────────

    Coordinator          Part A         Part B

    CanCommit? -----------> (prepare) --------> (prepare)
               <----- YES ---- YES <------------- YES

    PreCommit  -----------> (pre-commit) ------> (pre-commit)
               <----- ACK ---- ACK <------------- ACK

    DoCommit   -----------> (commit) --------> (commit)
               <----- DONE ---- DONE <----------- DONE

    If coordinator dies after PreCommit: participants can TIMEOUT and commit.
    (They know intent was to commit.)
```

### Visual: 3PC — Adding a Safety Net (Backup Minister)

```
╔═════════════════════════════════════════════════════════════════════════════╗
║   3PC: SAME WEDDING, BUT WITH A BACKUP MINISTER                            ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║   PHASE 1: CanCommit?  ──►  "Do you take...?"  Both: "I do"                ║
║                                                                            ║
║   PHASE 2: PreCommit   ──►  "We're about to marry. Hold tight." (NEW!)     ║
║            ▲                                                              ║
║            │  KEY INSIGHT: After this, everyone KNOWS the intent.           ║
║            │  Bride, Groom, AND backup minister all heard "we're doing it" ║
║                                                                            ║
║   PHASE 3: DoCommit    ──►  "I now pronounce..."  Done!                   ║
║                                                                            ║
║   ─── IF MAIN MINISTER FAINTS AFTER PreCommit ───                          ║
║                                                                            ║
║   Backup minister: "I saw what happened. Everyone pre-committed.            ║
║                    I'll complete the ceremony."  → COMMIT ✓                ║
║                                                                            ║
║   No more stuck! Backup can decide based on what already happened.         ║
║                                                                            ║
║   ─── THE CATCH: PARTITIONS ───                                             ║
║   What if backup is in another room (network partition)?                   ║
║   North room thinks: "Backup knows, we'll commit."                         ║
║   South room thinks: "Backup is gone, maybe we aborted." → ABORT           ║
║   RESULT: North commits, South aborts. ATOMICITY VIOLATED.                  ║
║   Partitions break 3PC's "reliable failure detection" assumption.         ║
║                                                                            ║
╚═════════════════════════════════════════════════════════════════════════════╝
```

## Why 3PC Is Rarely Used

### 1. Network Partitions Break It

3PC assumes **reliable failure detection**. In reality: "Coordinator is down" vs "Coordinator is slow" vs "Network between me and coordinator is broken" are **indistinguishable** during a partition.

```
    NETWORK PARTITION

    [North DC]                    [South DC]
    Coordinator, Part A           Part B

    Cable unplugged. Partition.
    North thinks South is dead. South thinks North is dead.

    Part A (North): "Coordinator is gone. Everyone pre-committed. I'll commit."
    Part B (South): "Coordinator is gone. Maybe we aborted? I'll abort."

    Result: Part A committed. Part B aborted. ATOMICITY VIOLATED.
```

In a partition, some participants might commit, others abort. Consistency is lost. 3PC's main advantage—non-blocking—breaks down precisely when you need it most.

### 2. More Phases = More Latency

Each phase is a network round-trip. 3PC has three phases; 2PC has two. 50% more round-trips. For distributed transactions, latency matters. 3PC adds cost without guaranteed benefit in partition-prone environments.

### 3. Modern Alternatives Handle the Problem Better

- **Raft / Paxos**: No coordinator that can vanish. Leader election. Replicated log. Consensus without 2PC/3PC.
- **2PC + Recovery Logs**: Coordinator logs its state. On restart, recovery process reads logs, queries participants, completes or aborts. Blocking is rare; recovery handles it.
- **Saga Pattern**: Avoid distributed transactions. Local transactions + compensating actions. Eventually consistent, simpler to operate.

### 4. When You Might See 3PC

**Textbooks.** Almost never in production. CockroachDB, Spanner use Raft. XA/JTA use 2PC. Microservices use Sagas. 3PC remains a theoretical curiosity.

## Comparison Table: 2PC vs 3PC vs Paxos/Raft

| Property | 2PC | 3PC | Paxos/Raft |
|----------|-----|-----|------------|
| **Blocking** | Blocks if coordinator fails between prepare and commit | Non-blocking (with timeouts) | No coordinator; leader election |
| **Latency** | 2 round-trips | 3 round-trips | Varies (leader election + log replication) |
| **Partition tolerance** | Blocks; recovery possible | **Fails**—can violate atomicity | Handles partitions (quorum) |
| **Complexity** | Medium | Higher | High (but well-understood) |
| **Production use** | Common (XA, JTA, distributed DBs) | Rare (textbooks) | Common (Kubernetes, CockroachDB, etcd) |

## Visual 3: 2PC vs 3PC — Decision and Comparison

```
╔═════════════════════════════════════════════════════════════════════════════╗
║   2PC vs 3PC: WHAT EACH DOES, WHEN EACH FAILS, WHEN TO USE                 ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║   WHAT EACH DOES:                                                          ║
║   ┌─────────────────────────────────────────────────────────────────────┐  ║
║   │ 2PC: Prepare → Commit. All say yes? Everyone commits.              │  ║
║   │ 3PC: CanCommit → PreCommit → DoCommit. Extra "hold tight" phase.    │  ║
║   └─────────────────────────────────────────────────────────────────────┘  ║
║                                                                            ║
║   WHEN EACH FAILS:                                                         ║
║   ┌──────────────────────┬──────────────────────┬──────────────────────┐   ║
║   │ 2PC                  │ 3PC                  │ Raft/Paxos           │   ║
║   ├──────────────────────┼──────────────────────┼──────────────────────┤   ║
║   │ Coordinator dies     │ Coordinator dies     │ (N/A — no single      │   ║
║   │ after Prepare→BLOCK   │ after PreCommit→     │  coordinator)        │   ║
║   │ Participants STUCK   │ can timeout & commit  │                      │   ║
║   │ Locks held forever   │                      │ Partition: minority  │   ║
║   │                      │ NETWORK PARTITION→   │ can't elect; safe    │   ║
║   │                      │ SPLIT COMMIT/ABORT   │ Majority continues   │   ║
║   │                      │ North commits,       │                      │   ║
║   │                      │ South aborts→VIOLATION                      │   ║
║   └──────────────────────┴──────────────────────┴──────────────────────┘   ║
║                                                                            ║
║   WHEN TO USE:                                                             ║
║   ┌─────────────────────────────────────────────────────────────────────┐  ║
║   │ 2PC: XA/JTA, distributed DBs, single-admin systems. Recovery logs.  │  ║
║   │ 3PC: NEVER in production. Partitions break failure detection.       │  ║
║   │ Raft/Paxos: etcd, Consul, CockroachDB, Kubernetes. Consensus.      │  ║
║   └─────────────────────────────────────────────────────────────────────┘  ║
║                                                                            ║
╚═════════════════════════════════════════════════════════════════════════════╝
```

### 3PC vs Paxos/Raft Detailed Comparison

**Why the industry moved from 3PC to consensus algorithms**:
- 3PC's non-blocking guarantee relies on **reliable failure detection**. In a partition, "coordinator is dead" vs "coordinator is unreachable" are indistinguishable. Participants in different partitions can make different decisions (some commit, some abort). Atomicity is violated.
- Paxos and Raft provide **distributed consensus** without a single coordinator. No one node is critical. Leader election handles failure. Quorum ensures agreement across partitions. The system makes progress as long as a majority is reachable.
- 3PC optimizes for the "coordinator crash" case. Paxos/Raft optimize for the "network partition" case—which is the dominant failure mode in distributed systems.

**Message complexity**:
- 2PC: 2 rounds (Prepare + Commit). 2N messages from coordinator to N participants, plus 2N responses = 4N messages.
- 3PC: 3 rounds (CanCommit + PreCommit + DoCommit). 6N messages.
- Raft: Normal case: 1 round (leader sends AppendEntries to followers; majority acks). Log replication only. Leader election adds 1–2 rounds when leader fails. Typical: O(1) per operation when stable.

**Partition behavior**:
- 2PC: Coordinator and participants in same partition can block. Recovery process can complete when coordinator restarts. No split-brain (only one coordinator).
- 3PC: Partition can cause **split commit**: North partition commits, South aborts. Data divergence. Unrecoverable without application logic.
- Raft: Partition: minority partition cannot elect leader; no progress. Majority partition continues. When partition heals, minority rejoins and catches up. Safe.

**Practical implementation**:
- 3PC: Virtually no production implementations. Theoretical interest only.
- 2PC: XA, JTA, distributed DBs (MySQL XA, PostgreSQL two-phase). Coordinator + participants. Recovery logs. Works for single-administered systems.
- Raft/Paxos: etcd, Consul, CockroachDB, TiKV. No coordinator. Replicated log. Leader handles writes; followers replicate. Industry standard for distributed coordination.

### Capacity and Failure Modes: Why 2PC Persists

**2PC in practice**: XA transactions in Java (JTA), C# (TransactionScope), and database drivers. Coordinator is usually the application server or a dedicated transaction manager. Participants: PostgreSQL, MySQL, Kafka, Redis (with XA support). When coordinator fails, recovery process reads durable log, queries participant status, and either commits or aborts. Blocking window: typically seconds to minutes, not indefinite. For many systems, that's acceptable.

**3PC's fatal assumption**: Perfect failure detection. In a partition, Node A might think "coordinator is dead" and commit. Node B might think "I'm partitioned" and abort. Both acted on incomplete information. The protocol cannot distinguish "coordinator crashed" from "coordinator unreachable." This is a fundamental limitation, not an implementation bug. The 1982 Skeen paper predated widespread appreciation of CAP. Today we know: partition tolerance isn't optional. 3PC optimizes for the wrong failure mode.

### When You Might Mention 3PC in an Interview

If asked "what's the difference between 2PC and 3PC?": Explain the pre-commit phase and non-blocking intent. Then immediately pivot: "But 3PC is rarely used because network partitions break the assumption of reliable failure detection. Production systems use 2PC with recovery logs, or Raft/Paxos for consensus, or Sagas to avoid distributed transactions entirely." That demonstrates both knowledge and pragmatism.

## One-Liner to Remember

**3PC fixes 2PC's blocking—until a network partition proves you can't tell who's really dead.**

---

# Part 2: Read-Your-Writes Consistency (Topic 316)

## The Problem: Your Own Write Is Invisible to You

You have a leader-follower database. Writes go to the leader. Reads can go to followers (replicas) for scalability. Replication is asynchronous. There's lag—100ms, 500ms, sometimes seconds.

**Scenario**: User updates bio to "Software Engineer." Immediately reads. The read goes to a **replica**. The replica hasn't replicated that write yet. User sees "Student." Their own update is invisible. Confusing. "Did it save?!"

```
    WITHOUT Read-Your-Writes

    User: "Update bio to Engineer"
              │
              ▼
    ┌─────────┴─────────┐
    │     LEADER        │  ← Write goes here (saved!)
    │  bio = Engineer   │
    └─────────┬─────────┘
              │ replicate (500ms lag)
              ▼
    ┌─────────────────┐
    │    REPLICA      │  ← Read goes here (stale!)
    │  bio = Student  │  User sees OLD data. Confusion!
    └─────────────────┘


    WITH Read-Your-Writes

    User: "Update bio" + "Read bio" (within 5 sec)
              │
              ▼
    ┌─────────────────┐
    │     LEADER      │  ← BOTH go to leader
    │  bio = Engineer │  User sees their own write. ✓
    └─────────────────┘
```

**Read-your-writes**: After YOU write something, YOUR subsequent reads must always see that write. Others may see a delay. But YOU must see YOUR changes.

### Visual: Read-Your-Writes — Two Scenarios Side by Side

```
╔═════════════════════════════════════════════════════════════════════════════╗
║   READ-YOUR-WRITES: Stale Replica vs Primary Routing                       ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║   SCENARIO A: WITHOUT Read-Your-Writes (broken UX)                         ║
║   User posts photo ──► Write goes to LEADER (saved!)                        ║
║   User refreshes    ──► Read goes to STALE REPLICA (hasn't synced yet)      ║
║   User sees: "Photo not there."  ← "Did it save?!"                          ║
║                                                                            ║
║   SCENARIO B: WITH Read-Your-Writes (correct UX)                           ║
║   User posts photo ──► Write goes to LEADER                                 ║
║   User refreshes    ──► Read ROUTED to LEADER (has the latest write)        ║
║   User sees: "Photo is there."  ← ✓                                         ║
║                                                                            ║
║   IMPLEMENTATION: Track (user_id, last_write_ts). If within lag window,    ║
║   route reads to primary. Else, read from replica.                          ║
║                                                                            ║
╚═════════════════════════════════════════════════════════════════════════════╝
```

## Solutions

### 1. Route Recent Writers to Leader

Track `(user_id, last_write_timestamp)`. On read: if `now - last_write_ts < threshold` (e.g., 5 seconds, or replica lag + buffer), route to **leader**. Otherwise, route to replica.

```
    Implementation:
    - On write: record (user_id, write_timestamp)
    - On read: if now - write_timestamp < LAG_THRESHOLD → read from primary
               else → read from replica
```

**Trade-off**: Routing reads to primary increases primary load. But typically only a small percentage of reads—those within seconds of a write. Acceptable.

### 2. Sticky Sessions (to Leader for Writers)

Route all traffic for a user who recently wrote to the leader. Sticky to leader for writers. After the lag window passes, can route to replicas.

### 3. Client-Side Version Tracking

Client tracks its last write version. On read, client sends "I need at least version X." Server ensures response is at least that fresh—may read from leader or wait for replica to catch up. Works across devices; more complex.

## Special Case: Multi-Device

User writes on phone. Reads on laptop. Different sessions. Sticky sessions don't help. Cross-device read-your-writes requires **centralized version tracking**—e.g., user-level "last write version" in a shared store. Client on laptop fetches "my last write was version 500"; server ensures read reflects at least version 500.

### Implementation Details: Session Store and Threshold Tuning

**Where to store last_write_ts**: In-memory per process (simple, lost on restart), Redis (shared across instances, survives restarts), or database (durable, adds latency). For most web apps, Redis with a short TTL (e.g., 60 seconds) works. Key: `ryw:{user_id}`. Value: `{timestamp}`. On write: SET with TTL. On read: GET; if within threshold, route to primary.

**Threshold choice**: Must exceed typical replica lag. If p99 lag is 500ms, use 2–5 seconds. Too short: false negatives (user reads from replica before it caught up). Too long: excessive primary load. Monitor replica lag; tune threshold accordingly.

### Decision Framework: When to Implement Read-Your-Writes

| Scenario | Read-your-writes needed? | Approach |
|----------|-------------------------|----------|
| Profile edit, refresh | Yes | Route to primary for 5s after write |
| Social feed (user's own posts) | Yes | Sticky to primary for recent posters |
| Product catalog browse | No | Read from replicas; no user-specific writes |
| Balance check after transfer | Yes, critical | Always primary for balance reads |
| Public timeline | No | Replicas fine; eventual consistency OK |

### Staff-Level Insight

For critical flows (payments, balance checks, profile updates), never read from stale replicas for the actor who just wrote. A bank allowed replica reads for all users. User transferred $100. Immediately checked balance. Read hit lagging replica. Balance showed pre-transfer amount. User thought transfer failed. Tried again. Double transfer. Read-your-writes isn't just UX—it's correctness.

---

# Part 3: Monotonic Reads and Consistent Prefix (Topic 317)

## Monotonic Reads: No Time Travel

**Definition**: Once you've seen data at version V, you never see data older than V on subsequent reads. Your view only moves forward. No "time travel."

**How it breaks**: Load balancer routes reads to different replicas. Replica A is at time 100. Replica B is at time 90. Read from A → fresh data. Next read from B → stale data. You went backward.

```
    VIOLATION: Load balancer sends to different replicas

    Read 1 ──▶ Replica A (up to date) ──▶ "India 250/3" ✓
    Read 2 ──▶ Replica B (lagging)   ──▶ "India 230/2" ✗ (went backward!)
    Read 3 ──▶ Replica A             ──▶ "India 260/4" ✓

    User experience: Score jumps around. Confusing.


    FIX: Sticky routing (same user → same replica)

    Read 1 ──▶ Replica A ──▶ "250/3"
    Read 2 ──▶ Replica A ──▶ "255/3" (same replica, moved forward)
    Read 3 ──▶ Replica A ──▶ "260/4" (monotonic ✓)
```

### Visual: Monotonic Reads — No Time Travel

```
╔═════════════════════════════════════════════════════════════════════════════╗
║   MONOTONIC READS: Your View Must Only Move Forward                        ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║   WITHOUT Monotonic Reads (violation):                                     ║
║   Timeline:  Read1 ──► v5 ──► Read2 ──► v3 ──► Read3 ──► v6                 ║
║                    ✓              ✗                                         ║
║              "You saw v5, then v3?"  TIME TRAVEL! User confused.            ║
║                                                                            ║
║   WITH Monotonic Reads (correct):                                          ║
║   Timeline:  Read1 ──► v5 ──► Read2 ──► v5 or higher ──► Read3 ──► v6       ║
║                    ✓              ✓                          ✓              ║
║              Once you see v5, you'll NEVER see anything older.               ║
║              No backward jumps. View only moves forward.                    ║
║                                                                            ║
║   FIX: Sticky routing (same user → same replica) OR version-aware reads.    ║
║                                                                            ║
╚═════════════════════════════════════════════════════════════════════════════╝
```

**Fixes**: (1) Sticky routing—always use same replica for a user. (2) Version-aware reads—client tracks highest version seen; server rejects or delays staler responses.

## Consistent Prefix: See Cause Before Effect

**Definition**: Reads see writes in the order they were applied. If A happened before B, you never see B without A. Causality preserved.

**Example**: Chat. Alice: "What time is the meeting?" Bob: "3 PM." Without consistent prefix, you might see "3 PM" before the question. Nonsense. Bob's reply is a response to Alice's question. The question must be seen first.

**Fix**: Causal ordering. If message B is a reply to message A, ensure B is always seen after A. Use vector clocks, causal dependencies, or deterministic routing that preserves order.

## Consistency Model Hierarchy

```
    STRONGEST
        │
        ▼
    Linearizability      — Single-operation linearizable. Strongest.
        │
        ▼
    Sequential consistency — All operations in some total order; all processes see same order.
        │
        ▼
    Causal consistency   — Causally related operations seen in order.
        │
        ▼
    Read-your-writes     — You see your own writes.
        │
        ▼
    Monotonic reads      — Your view never goes backward.
        │
        ▼
    Eventual consistency — Eventually everyone agrees. Weakest.
        │
    WEAKEST
```

### Consistency Models Hierarchy: Detailed Explanation

| Model | Guarantee | Example | When Appropriate |
|-------|-----------|---------|-------------------|
| **Linearizability** | Every operation appears to occur at a single point in time between invocation and response. Strongest. | Bank balance: read always sees latest write. | Financial systems, locks, critical config. |
| **Sequential** | All operations in some total order; every process sees that order. Slightly weaker than linearizable (no real-time guarantee). | Distributed queue: dequeue order is agreed. | When order matters but not real-time. |
| **Causal** | If A happened before B (causally), everyone sees A before B. Concurrent ops may be seen in different order. | Chat: reply always after message. | Chat, comments, collaborative docs. |
| **Read-your-writes** | After you write, you always see your write. Others may see later. | Profile edit: you see it immediately. | User-facing edits, sessions. |
| **Monotonic reads** | Your view never goes backward. Once you see version N, you never see version < N. | Live score: 250, then 255, never 230. | Dashboards, scores, feeds. |
| **Eventual** | No ordering guarantee. Eventually all replicas converge. | DNS propagation, CDN cache. | Static content, non-critical data. |

**Decision framework**:
1. **Financial / correctness-critical?** → Linearizability (or sequential at minimum).
2. **User's own data, must see edits?** → Read-your-writes.
3. **Causal dependencies (chat, comments)?** → Causal consistency.
4. **Score, balance, anything that must not go backward?** → Monotonic reads.
5. **Static or rarely changing?** → Eventual consistency.
6. **Cost**: Stronger = more coordination, higher latency. Weaker = cheaper, faster. Choose the weakest that satisfies requirements.

### Version-Aware Reads: Alternative to Sticky Routing

Client sends `X-Read-After-Version: 500` (or similar). Server checks: "Do I have data at least version 500?" If replica is at 480, either (a) wait until it reaches 500, (b) forward to primary, or (c) return 503 "try again." Works across devices—version lives in account, not session. Used by some collaborative systems and distributed databases.

### Consistent Prefix in Practice: Chat and Comments

**Chat**: Messages have causal dependencies. Reply must appear after the message it replies to. Implement with: (1) Vector clocks per message—reply carries clock of original. (2) Deterministic ordering—server assigns sequence numbers; clients display in order. (3) Single writer per channel—simplest; one server orders all messages.

**Comment threads**: Same idea. Comment B is reply to Comment A. B must be seen after A. Most systems use a single logical order (e.g., timestamp at write, or server-assigned ID). Replicas apply in same order; readers see consistent prefix.

### Capacity Consideration: Sticky Session State

Sticky routing requires tracking "user U → replica R." In a cluster of 100 API servers, where does this live? Options: (1) Affinity cookie—load balancer sets cookie; same replica for same cookie. (2) Consistent hashing—hash(user_id) → replica. (3) Redis—store user_id → replica_id; 100ms read per request. (1) and (2) avoid extra storage; (3) allows dynamic rebalancing.

**Staff insight**: Choose the weakest guarantee that satisfies your use case. Strong consistency is expensive. Monotonic reads are cheap and prevent the worst UX bugs (score going backward, balance jumping).

---

# Part 4: Hybrid Logical Clocks — HLC (Topic 318)

## The Tension: Physical vs Logical Clocks

**Physical clocks**: Tell you the time of day. But they **drift** between servers. NTP accuracy: 1–10ms. Servers can be milliseconds or seconds apart. You can't trust physical time for ordering across nodes.

**Logical clocks (Lamport)**: Guarantee causal ordering. Event 1, 2, 3, 4. But no connection to real time. Event 5000—when did it happen? Unknown. Retention policies ("delete events older than 7 days") don't work.

**HLC**: Combine both. Timestamp = (physical_time, logical_counter, node_id). You get ordering AND approximate real time.

### Visual: Hybrid Logical Clocks Explained

```
╔═════════════════════════════════════════════════════════════════════════════╗
║   HLC: Physical Clock + Logical Counter — Like a Wall Clock + Step Counter  ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║   NODE A:  Event 1 at 10:00:00  →  HLC = (10:00, 0, A)                     ║
║            Event 2 at 10:00:00  →  HLC = (10:00, 1, A)  ← same tick, +1    ║
║            Sends to B at (10:00, 1)                                         ║
║                                                                            ║
║   NODE B:  Receives msg. B's wall clock says 10:01:00  →  HLC = (10:01, 0, B) ║
║            (Physical advanced, reset logical counter)                     ║
║                                                                            ║
║   RULE: HLC always moves forward. Never goes backward.                      ║
║   • Same physical time? Increment logical counter.                        ║
║   • Physical advanced? Reset counter.                                      ║
║   • Result: Causal order + approximate real time for retention policies.  ║
║                                                                            ║
║   ┌─────────────┐     ┌─────────────┐                                     ║
║   │ Wall Clock  │  +  │ Step Counter│  =  (10:00, 3, A)                    ║
║   │  "When?"    │     │  "Order?"   │     Order + real time                ║
║   └─────────────┘     └─────────────┘                                     ║
║                                                                            ║
╚═════════════════════════════════════════════════════════════════════════════╝
```

## HLC Algorithm

- On event: set `physical_time = max(local_clock, last_event_physical_time)`.
- If same physical time as last event: increment logical counter.
- If physical time advanced: reset counter.
- Guarantee: if A causally precedes B → HLC(A) < HLC(B). AND physical component ≈ wall clock.

## Tie-Breaking

Same physical time on different nodes: compare logical counter, then node_id. Unambiguous total order.

```
    HLC Timestamp: (physical_time, logical_counter, node_id)

    Server A                    Server B
    ────────                    ────────
    Event 1: (100, 0, A)        Event 2: (100, 0, B)
              │                            │
              │   Same physical time!      │
              │   Compare: A < B (node id) │
              │   So: (100,0,A) < (100,0,B)│
              │                            │
    Event 3: (100, 1, A)  ←─ message from Event 1
              │   Counter incremented (causal dependency)

    ORDERING: 1 < 3 < 2 (by HLC comparison)
    Real time: all ~100ms. Good for logs, retention.
```

## Used By

- **CockroachDB**: Distributed transactions. Global ordering. Physical component for retention.
- **YugabyteDB**: Same. Multi-region. Serializable transactions without a single timestamp oracle.
- **Event sourcing**: Order events correctly; retain by approximate date.

## Comparison: Lamport vs Vector Clocks vs HLC

| Property | Lamport | Vector Clocks | HLC |
|----------|---------|---------------|-----|
| **Causality** | ✓ | ✓ | ✓ |
| **Concurrent detection** | ✗ | ✓ | ✗ |
| **Space per timestamp** | 1 number | N numbers (N = nodes) | 3 (physical, logical, node_id) |
| **Real-time approximation** | ✗ | ✗ | ✓ |
| **Use case** | Simple ordering | Conflict detection | Ordering + retention + logs |

### HLC and Distributed Transactions: CockroachDB Example

CockroachDB uses HLC for serializable transactions across nodes. Each transaction gets an HLC timestamp. Writes are ordered by HLC. Readers use HLC to determine visibility—e.g., "show me data as of timestamp T." If clocks drift, HLC bounds the uncertainty: physical component is within NTP sync (typically <10ms); logical component handles same-millisecond events. No single timestamp oracle. Each node has HLC. Sync on message exchange. Global ordering emerges. Enables geo-distributed SQL without a bottleneck.

### Bounded Clock Uncertainty and Read Snapshot

When a client reads with snapshot isolation, the database picks a read timestamp. With physical clocks only: if clocks drift, "read as of 2:00:00" might miss writes that happened at 1:59:59 on a slow clock. HLC: read timestamp includes logical component. Guaranteed to include all causally prior writes. Bounded uncertainty: typically 1–2 logical ticks per node. Small enough for most workloads.

### When to Use HLC vs Lamport vs Vector Clocks

| Need | Use |
|------|-----|
| Simple causal order, no real time | Lamport |
| Detect concurrent events (conflict resolution) | Vector clocks |
| Order + retention + logs + distributed transactions | HLC |
| Single-node ordering | Physical clock + sequence |

## One-Liner to Remember

**HLC: physical time for "when" (approximate), logical counter for "order" (exact). Best of both clocks.**

---

# Part 5: CRDTs — Conflict-Free Replicated Data Types (Topic 319)

## The Problem: Concurrent Updates Without Coordination

Multiple nodes update the same data concurrently. Offline. No coordination. When they sync—what happens? **Last-write-wins** = data loss. User A and B both change the same field. One overwrites the other. User B's edit vanishes.

**CRDTs**: Data structures mathematically designed so that **all concurrent operations merge without conflict**. Guaranteed convergence. No coordination. No "choose A or B" dialog.

### Visual: CRDT — The Shopping List (G-Set)

```
╔═════════════════════════════════════════════════════════════════════════════╗
║   CRDT: THE SHOPPING LIST — Two People, Both Offline, No Conflict          ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║   ALICE (offline)              BOB (offline)                               ║
║   Shared list: []              Shared list: []                              ║
║                                                                            ║
║   Alice adds "milk"            Bob adds "eggs"                              ║
║   Alice's list: [milk]         Bob's list: [eggs]                           ║
║                                                                            ║
║   ─────────── RECONNECT / SYNC ───────────                                  ║
║                                                                            ║
║   G-Set merge = UNION of both sets                                         ║
║   Result: [milk, eggs]  ← BOTH survive! No conflict!                       ║
║                                                                            ║
║   LWW would do: One overwrites. "milk" OR "eggs" — one loses.              ║
║   CRDT does: MERGE. Milk + eggs. Both keep their additions.                ║
║                                                                            ║
║   That's a G-Set (Grow-only Set) — add-only, merge = union.               ║
║   OR-Set extends this for add+remove with unique tags.                     ║
║                                                                            ║
╚═════════════════════════════════════════════════════════════════════════════╝
```

## Types of CRDTs

| CRDT | Semantics | Merge |
|------|-----------|-------|
| **G-Counter** | Grow-only. Each node has own counter. | Sum of all |
| **PN-Counter** | Add and subtract | Sum of increments minus sum of decrements |
| **G-Set** | Add-only set | Union |
| **OR-Set** | Add and remove (observed-remove) | Union of adds minus union of removes (with unique tags) |
| **LWW-Register** | Last-writer-wins by timestamp | Keep higher timestamp |
| **MV-Register** | Multi-value; expose conflicts to app | Return all concurrent values |

## State-Based vs Operation-Based

- **State-based (CvRDTs)**: Each node maintains state. Merge function: commutative, associative, idempotent. Ship full state or deltas.
- **Operation-based (CmRDTs)**: Broadcast operations. Operations must be commutative. Often more compact.

## ASCII Diagram: G-Counter Merging

```
    Two nodes, offline. Add to shared counter.

    Node A                    Node B
    ──────                    ──────
    +5                        +3
    Counter: 5                Counter: 3

    Merge (sync)
              │
              ▼
    G-Counter merge = SUM (each node's contribution)
              │
              ▼
    Result: 8  ← A's 5 + B's 3. Both survive!

    No "which increment wins?" — all increments are kept.
```

## Visual 2: CRDT Merge Without Conflict — Two Concurrent Edits Resolve Automatically

```
╔═════════════════════════════════════════════════════════════════════════════╗
║   CRDT: MERGE WITHOUT CONFLICT — OR-Set Example                            ║
║   Problem: User A and User B both edit a shared list OFFLINE. Then sync.   ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║   NODE A (offline)                    NODE B (offline)                     ║
║   ───────────────                     ───────────────                      ║
║   Initial: [apple, banana]             Initial: [apple, banana]            ║
║                                                                             ║
║   A adds "cherry" (tag: A1)            B adds "date" (tag: B1)              ║
║   A removes "banana" (tag: A2)        B adds "elderberry" (tag: B2)        ║
║                                                                             ║
║   A's state:                           B's state:                          ║
║   add_set: {(apple,A0),(cherry,A1)}    add_set: {(apple,A0),(date,B1),     ║
║   remove_set: {(banana,A2)}                     (elderberry,B2)}           ║
║                                                                             ║
║                        SYNC / MERGE                                         ║
║                              │                                              ║
║   Merge = UNION(add_set) − UNION(remove_set)                                ║
║   Each (element, tag) uniquely identifies — no collision                   ║
║                              │                                              ║
║                              ▼                                              ║
║   MERGED RESULT: {apple, cherry, date, elderberry}                           ║
║   ✓ Both A's cherry AND B's date/elderberry survive                        ║
║   ✓ banana removed (A2 in remove_set)                                       ║
║   ✓ NO "last write wins" — NO data loss — MATH GUARANTEES convergence       ║
║                                                                            ║
║   LWW would do: One add "wins", other loses. CRDT: BOTH survive.           ║
║                                                                            ║
╚═════════════════════════════════════════════════════════════════════════════╝
```

## Real-World Use

- **Figma**: Collaborative design. CRDT-like structures for vector graphics.
- **Riak**: Distributed DB with CRDT support (counters, sets, maps).
- **Redis CRDT module**: Multi-master conflict-free structures.
- **Apple Notes**: Sync across devices. CRDT-inspired merge.
- **Collaborative text editors**: Often CRDT-based or OT-based.

## CRDT vs Operational Transform (OT)

| | CRDT | OT |
|---|------|-----|
| **Coordination** | Peer-to-peer; no central server | Central server transforms operations |
| **Conflict resolution** | Merge function (math) | Transform rules (complex) |
| **Examples** | Figma, Riak | Google Docs |
| **Offline** | Natural | Harder |

## Limitations

- Limited data structures. Not all types have CRDT versions.
- Metadata overhead (tombstones, version vectors).
- Complex for non-trivial types (e.g., rich text).
- Not suitable when strong consistency is required.

### CRDT Implementation Examples: Pseudocode

**G-Counter (Grow-only)**:
```
    struct GCounter:
        map node_id -> integer   // one counter per node

    def increment(node_id):
        self[node_id] += 1

    def value():
        return sum(self.values())

    def merge(other):
        for node_id, count in other:
            self[node_id] = max(self.get(node_id, 0), count)
```
Merge: element-wise max. Commutative, associative, idempotent. Concurrent increments on different nodes: both preserved. Example: Node A adds 5, Node B adds 3. Merge → 8.

**PN-Counter (Positive-Negative, add and subtract)**:
```
    struct PNCounter:
        GCounter positive
        GCounter negative

    def increment(node_id):
        positive[node_id] += 1

    def decrement(node_id):
        negative[node_id] += 1

    def value():
        return positive.value() - negative.value()

    def merge(other):
        positive.merge(other.positive)
        negative.merge(other.negative)
```
Two G-Counters. Merge each. Used for like counts (up/down), inventory (add/remove).

**OR-Set (Observed-Remove Set)**:
```
    struct ORSet:
        set add_set   // (element, unique_tag)
        set remove_set

    def add(element):
        tag = (element, node_id, timestamp_or_seq)
        add_set.add(tag)

    def remove(element):
        // Remove only tags we've observed (add-set for this element)
        for tag in add_set where tag.element == element:
            remove_set.add(tag)

    def lookup(element):
        has_add = any(tag for tag in add_set where tag.element == element)
        has_remove = any(tag for tag in remove_set where tag.element == element)
        return has_add and not (add_set for element ⊆ remove_set)
        // Simpler: element in set iff exists add tag not in remove_set

    def merge(other):
        add_set = add_set union other.add_set
        remove_set = remove_set union other.remove_set
        // Garbage collect: remove (add,remove) pairs seen by all replicas
```
Concurrent add and remove: add wins if the remove didn't see the add. Both adds of same element with different tags: both survive (multiset semantics) or application resolves. Merge = union of adds minus union of removes (with observed-remove rule).

**Concurrent updates resolving automatically**: Node A adds "apple", Node B adds "banana". Merge: both in set. Node A removes "apple" (the one it added), Node B adds "apple" again. A's remove only applies to A's original add. B's add is new. Result: {banana, apple}. No conflict.

### OR-Set Deep Dive: Add and Remove Without Conflict

G-Set can only add. OR-Set (Observed-Remove Set) supports remove. Trick: don't remove elements; track "add" and "remove" as sets of unique identifiers. Each add gets a unique tag (e.g., (element, node_id, sequence)). Remove adds the tag to "removed" set. Merge: (union of adds) minus (union of removes). When do we remove from "removed"? When we've seen the add and its remove in all replicas. Tombstones and garbage collection get complex. But the merge is still commutative and associative. Used for collaborative lists, presence, etc.

### CRDT Metadata Overhead

OR-Set: each element might need (element_id, node_id, seq) = tens of bytes. For a 1000-element list, 10s of KB. G-Counter: N integers (one per node). For 100 nodes, 400–800 bytes. PN-Counter: 2N. LWW-Register: value + timestamp + node_id. Overhead grows with concurrency and number of nodes. For small, tightly coupled groups (e.g., 5 users editing a doc), fine. For millions of users, consider sharding or different design.

### CRDT and Offline-First Architecture

CRDTs shine when nodes can update independently and sync later. Offline-first mobile app: user edits on subway (no network). Edits queue. When online, sync with server. Server merges using CRDT. Other users get merged state. No "connection lost, retry?" for the editing experience. Sync is eventually consistent. Conflict-free by construction. Apple Notes, Figma, and collaborative editors use this pattern.

## One-Liner to Remember

**CRDTs: design data so concurrent edits merge automatically. No conflict. No coordination. Math does the work.**

---

# Part 6: Chaos Engineering (Topic 310)

## Principle: Break It on Purpose

Don't wait for a real fire to test your evacuation plan. Simulate it. Chaos engineering: **deliberately inject failures** in production (or staging) to find weaknesses before real outages find them.

## The Netflix Approach

**Chaos Monkey**: Randomly terminates production instances. If the system recovers → resilient. If not → you found a bug. Better to find it Tuesday 2 PM than Saturday 2 AM.

## Chaos Engineering Process

```
    ┌─────────────────────────────────────────────────────────┐
    │  CHAOS ENGINEERING FEEDBACK LOOP                        │
    │                                                         │
    │  1. DEFINE STEADY STATE                                 │
    │     What does "normal" look like? Latency p99, error     │
    │     rate, throughput.                                    │
    │                                                         │
    │  2. HYPOTHESIZE                                         │
    │     "If DB primary fails, we expect: read replica        │
    │     promotes in 30s, clients reconnect, no data loss."   │
    │                                                         │
    │  3. INJECT FAILURE                                      │
    │     Kill server. Add latency. Drop packets. Fill disk.   │
    │                                                         │
    │  4. OBSERVE                                             │
    │     Did the system behave as expected?                   │
    │                                                         │
    │  5. FIX                                                 │
    │     Found weakness? Fix it. Improve runbooks.             │
    │                                                         │
    │  6. REPEAT                                              │
    │     New failure mode. Test again.                        │
    └─────────────────────────────────────────────────────────┘
```

## Types of Chaos

| Type | Example |
|------|---------|
| Instance termination | Kill 1 of N API servers |
| Network partition | Split cluster into two islands |
| Latency injection | Add 500ms to DB calls |
| Disk failure | Fill disk, corrupt block |
| DNS failure | Return wrong IP or timeout |
| Dependency failure | Make payment service return 5xx |
| Clock skew | Set server clock 5 minutes ahead |

## Tools

- **Netflix Chaos Monkey**: Random instance termination.
- **Gremlin**: Commercial chaos platform.
- **Litmus, Chaos Mesh**: Kubernetes-native chaos.
- **AWS Fault Injection Simulator**: Inject EC2, ECS, RDS failures.

## Game Days

Scheduled chaos events. Team aware. Prepared. "Today at 2 PM we're killing the primary. Watch the runbooks." Good for building confidence and testing procedures. Start here before automated chaos.

## Blast Radius Control

```
    Start small:
    - One instance in staging
    - One instance in prod (non-critical)
    - One AZ
    - One region (last)
```

Don't start by killing an entire region. Build up. Learn. Expand gradually.

### Chaos Engineering Maturity Model: 5 Levels

| Level | Name | What It Looks Like | How to Progress |
|-------|------|-------------------|----------------|
| **0** | No chaos | No deliberate failure injection. Hope nothing breaks. | Start with post-incident game day (retrospective). |
| **1** | Ad hoc game days | Scheduled chaos exercises. Manual. Team watches. Runbooks tested. | Document findings. Run quarterly. |
| **2** | Automated staging chaos | Automated chaos in staging (Chaos Monkey, Litmus). Regular cadence. No prod. | Add alerting. Validate runbooks. |
| **3** | Controlled prod chaos | Chaos in production with blast radius control. One instance, one AZ. Off-peak. | Expand to more services. Reduce blast radius per experiment. |
| **4** | Continuous chaos in production | Chaos runs continuously. Random instance kills. Latency injection. Part of normal operations. | Netflix level. Requires mature SRE, runbooks, monitoring. |
| **5** | Chaos as validation | Every deployment validated by chaos. Canary + chaos. No release without chaos pass. | Rare. High maturity. |

**Level 0 → 1**: Run one game day. Kill one non-critical service in staging. Observe. Fix what breaks. Document.

**Level 1 → 2**: Automate. Chaos Monkey in staging runs daily. Team gets weekly report. No manual trigger.

**Level 2 → 3**: Move one experiment to prod. One instance of 20. Off-hours. Define success criteria. If recovery works, celebrate. If not, fix before expanding.

**Level 3 → 4**: Expand to multiple services. Reduce human involvement. Chaos becomes background noise. Team responds to alerts as usual.

**Level 4 → 5**: Chaos gates releases. New service must survive chaos before production. Culture: "if it hasn't been chaos-tested, it's not ready."

**Maturity assessment**: Most organizations are at Level 0 or 1. Reaching Level 2 (automated staging chaos) requires tooling (Chaos Mesh, Litmus, Gremlin) and CI integration. Level 3 requires production access, blast radius control, and leadership buy-in. Level 4–5 is rare—Netflix, Amazon, Google operate at this level. Staff Engineers advocate for progression: start with one game day, document value, expand incrementally.

## Staff-Level Insight

**Chaos engineering is a CULTURE, not a tool.** It requires:

- Buy-in from leadership (we value resilience over "don't touch prod")
- Runbooks that work (test them!)
- Monitoring and alerting (you need to see what broke)
- Blameless culture (chaos finds bugs; people fix them)

Hope is not a strategy. Break it on purpose so it doesn't break when you don't.

### Chaos and Resilience Metrics

What to measure during chaos: (1) **Recovery time**—how long until error rate returns to baseline? (2) **Degradation**—does latency spike 2x or 10x? (3) **Cascading failure**—did killing one component take down others? (4) **Data loss**—did we lose writes? (5) **Manual intervention**—did we need to fix something by hand? Set SLOs: "Failover completes in <60s." Chaos validates or invalidates those SLOs.

### Anti-Patterns: Chaos Done Wrong

- **Starting too big**: Killing the primary database on day one. Site down. No runbook. Panic. Start with one API instance of 20.
- **No hypothesis**: "Let's kill something and see." Without a hypothesis, you don't know what to observe. Define expected behavior first.
- **No steady state**: You can't tell if chaos caused degradation if you don't know normal. Establish baseline metrics.
- **Blaming people**: Chaos finds bugs. The goal is to fix systems, not punish. Blameless postmortems.

### Game Day Checklist

1. Schedule during business hours. Team online.
2. Define scope: "We're killing 1 of 5 API servers in staging."
3. Document hypothesis: "Load balancer routes around in <10s. No errors."
4. Run chaos. Observe.
5. If hypothesis holds: celebrate. Document.
6. If not: fix. Re-run. Repeat until hypothesis holds.
7. Expand blast radius when confident (e.g., 1 prod instance).

---

# Summary: Key Takeaways

1. **3PC**: Non-blocking in theory. Partition-prone in practice. 2PC + recovery logs, Raft, or Sagas win in production. 3PC stays in textbooks.

2. **Read-your-writes**: Route recent writers to primary. Track (user_id, last_write_ts). Critical for UX and correctness (e.g., payments).

3. **Monotonic reads**: Sticky routing or version-aware reads. Prevents "score went backward" confusion.

4. **Consistent prefix**: Causal order. Chat, collaborative docs. Never see effect before cause.

5. **HLC**: Physical + logical + node_id. Order AND real time. CockroachDB, YugabyteDB.

6. **CRDTs**: Merge without conflict. G-Counter, OR-Set, etc. Figma, Riak. Math guarantees convergence.

7. **Chaos engineering**: Define, hypothesize, inject, observe, fix, repeat. Culture > tool. Start small. Game days. Blast radius control.

---

## Visual 5: Chapter 26 Supplement in One Picture

```
╔═════════════════════════════════════════════════════════════════════════════╗
║   VISUAL SUMMARY: ADVANCED DISTRIBUTED SYSTEMS — ALL KEY TAKEAWAYS          ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║   ┌───────────────────────────────────────────────────────────────────┐   ║
║   │ 3PC       │ Non-blocking theory. Partitions break it. Use 2PC+    │   ║
║   │           │ recovery or Raft. Never in production.                │   ║
║   ├───────────┼───────────────────────────────────────────────────────┤   ║
║   │ RYW       │ Route (user_id, last_write_ts) to primary. Critical   │   ║
║   │           │ for payments, profile edits. Redis + TTL typical.     │   ║
║   ├───────────┼───────────────────────────────────────────────────────┤   ║
║   │ Monotonic │ Sticky routing or version-aware reads. No backward     │   ║
║   │ Reads     │ jumps (score 250→230→260). Same replica per user.     │   ║
║   ├───────────┼───────────────────────────────────────────────────────┤   ║
║   │ HLC       │ (physical, logical, node_id). Order + real time.      │   ║
║   │           │ CockroachDB, YugabyteDB. Retention + ordering.        │   ║
║   ├───────────┼───────────────────────────────────────────────────────┤   ║
║   │ CRDTs     │ Merge = commutative, associative. G-Counter, OR-Set.  │   ║
║   │           │ Figma, Riak. No LWW data loss. Both edits survive.    │   ║
║   ├───────────┼───────────────────────────────────────────────────────┤   ║
║   │ Chaos     │ Define steady state → hypothesize → inject → fix.      │   ║
║   │           │ Culture > tool. Game days first. Blast radius control. │   ║
║   └───────────┴───────────────────────────────────────────────────────┘   ║
║                                                                            ║
║   CONSISTENCY HIERARCHY: Linearizable > Sequential > Causal > RYW >       ║
║   Monotonic > Eventual. Choose weakest that satisfies requirements.        ║
║                                                                            ║
╚═════════════════════════════════════════════════════════════════════════════╝
```

---

# Appendix: Interview One-Liners

- **"Why not 3PC?"** — Partitions break it. Can't distinguish coordinator dead from network split. 2PC + recovery or Raft/Paxos in practice.
- **"Read-your-writes?"** — Route recent writers to primary. Track last write time; if within lag window, read from primary.
- **"Monotonic reads?"** — Sticky routing so same user hits same replica. No backward jumps.
- **"HLC vs Lamport?"** — HLC adds physical time. Order + approximate real time. Lamport has order only.
- **"CRDT vs LWW?"** — CRDT merges; both edits survive. LWW overwrites; one loses. Use CRDT for collaboration.
- **"Chaos engineering?"** — Inject failure on purpose. Find weaknesses. Start with game days. Blast radius control.

---

# Extended Interview Q&A

**Q: "We have read replicas. Users sometimes see stale data after editing. How do we fix it?"**  
A: Read-your-writes. Track (user_id, last_write_timestamp). Route reads to primary if now - last_write_ts < replica_lag_threshold (e.g., 5 seconds). Store in Redis with TTL. Small % of reads hit primary; users always see their edits. Alternative: sticky sessions to primary for recent writers.

**Q: "Our cricket score widget sometimes shows 250, then 230, then 260. Users complain."**  
A: Monotonic reads violation. Load balancer sends to different replicas with different lag. Fix: sticky routing—same user always hits same replica. Or version-aware reads: client sends highest version seen; server rejects staler responses.

**Q: "We need global ordering of events across regions. Physical clocks drift. What do we use?"**  
A: Hybrid Logical Clocks (HLC). (physical_time, logical_counter, node_id). Guarantees causal order. Physical component ≈ real time for retention and logging. Used by CockroachDB, YugabyteDB.

**Q: "Two users edit the same document offline. When they sync, one overwrites the other. How to fix?"**  
A: CRDTs or Operational Transform. CRDT: design data structure so merges are commutative—both edits survive. OR-Set for lists. LWW-Register only for single-value fields where overwrite is acceptable (e.g., display name). OT requires central server; CRDTs can be peer-to-peer.

**Q: "How do we validate our failover actually works?"**  
A: Chaos engineering. Game day: schedule failover test. Kill primary (or simulate). Observe: does replica promote? How long? Any data loss? Runbooks tested? Then automate: Chaos Monkey in staging. Eventually prod, with blast radius control. Don't hope—test.

## Staff Interview Walkthrough: "Design a Collaborative Document Editor"

**Interviewer**: "Users edit documents offline. When they sync, we can't lose edits. How do you handle conflicts?"

**Strong Answer Structure**:

1. **Problem**: Last-write-wins loses data. Two users edit same paragraph offline. One overwrites the other. Bad UX.

2. **Options**: (a) Operational Transform—central server transforms operations. Google Docs. (b) CRDTs—merge function; no central server. Figma, some collaborative editors. (c) Locking—one writer at a time. Doesn't work offline.

3. **CRDT choice**: For lists (bullets, lines), OR-Set. Each add/remove gets unique tag. Merge = union of adds minus union of removes. Both users' adds survive. For rich text, more complex—blocks as CRDT, or use OT. Trade-off: CRDT simpler for sync, more metadata; OT needs server.

4. **Read consistency**: When user A syncs, they need to see their local edits + remote edits merged. Monotonic reads: don't show them a version older than what they had. Version vector or HLC per operation.

5. **Scale**: CRDT state grows with concurrent edits. Tombstones for removes. Garbage collect when all nodes have seen add+remove. For large docs, consider block-level CRDTs (each paragraph/block is a CRDT).

**Key Staff Signal**: Candidate compares options (OT vs CRDT), chooses based on constraints (offline, server availability), and addresses consistency (monotonic reads, merge semantics). They don't just say "use CRDT"—they explain why and what the trade-offs are.

---

## Visual 4: Real-World Application — CockroachDB, Figma, Netflix

```
╔═════════════════════════════════════════════════════════════════════════════╗
║   HOW COCKROACHDB, FIGMA, NETFLIX APPLY THESE ADVANCED CONCEPTS            ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║   ┌─────────────────────────────────────────────────────────────────────┐  ║
║   │ COCKROACHDB                                                         │  ║
║   │ • HLC: (physical, logical, node_id) for serializable transactions  │  ║
║   │ • Global ordering without single timestamp oracle                    │  ║
║   │ • Avoids 3PC: uses Raft for consensus, not 2PC/3PC                  │  ║
║   │ • Read-your-writes: consistency levels including RYW               │  ║
║   │ • Chaos: tested with partition injection, node failures             │  ║
║   └─────────────────────────────────────────────────────────────────────┘  ║
║                                                                            ║
║   ┌─────────────────────────────────────────────────────────────────────┐  ║
║   │ FIGMA                                                               │  ║
║   │ • CRDT-like structures for vector graphics, collaborative editing  │  ║
║   │ • Merge without conflict: multiple users edit same canvas offline   │  ║
║   │ • No "last write wins" — both additions survive (OR-Set style)     │  ║
║   │ • Real-time sync with eventual consistency                         │  ║
║   └─────────────────────────────────────────────────────────────────────┘  ║
║                                                                            ║
║   ┌─────────────────────────────────────────────────────────────────────┐  ║
║   │ NETFLIX                                                             │  ║
║   │ • Chaos Monkey: random instance termination (chaos engineering)     │  ║
║   │ • Chaos Kong: whole AZ failure simulation                           │  ║
║   │ • Define steady state → hypothesize → inject → observe → fix         │  ║
║   │ • Culture: "if it hasn't been chaos-tested, it's not resilient"     │  ║
║   └─────────────────────────────────────────────────────────────────────┘  ║
║                                                                            ║
╚═════════════════════════════════════════════════════════════════════════════╝
```

---

# Cross-Topic Integration: How These Concepts Connect

Understanding each topic in isolation is necessary but not sufficient. Staff engineers see how they compose. Consider a **collaborative document editor** deployed globally:

- **CRDTs** handle concurrent edits—merge without conflict. OR-Set for list operations. No locks.
- **Read-your-writes** ensures when you type, you see your keystroke immediately. Route your reads to the node that received your write, or to a primary.
- **Monotonic reads** ensure you never see version 5 then version 3. Sticky routing or version vectors per user.
- **HLC** (or similar) orders operations for display. "Which edit happened first?" HLC timestamps. Also useful for retention—"delete events older than 7 days."
- **Chaos engineering** validates: "If the node serving this user dies, does another pick up? Does merge still work? Do we lose edits?" Run chaos. Find out.

A **distributed database** like CockroachDB uses HLC for transaction ordering, avoids 3PC (uses Raft for consensus), and may offer read-your-writes as a consistency level. Chaos tests failover and split-brain scenarios. The concepts are not isolated—they form a design space. Your job is to choose the right combination for the problem.

---

# Operational Scenarios: When Things Go Wrong

| Scenario | Relevant Concepts | Response |
|----------|-------------------|----------|
| User sees stale data after editing | Read-your-writes | Route recent writers to primary; tune threshold |
| Score/balance jumps backward | Monotonic reads | Sticky routing; version-aware reads |
| Chat shows reply before question | Consistent prefix | Causal ordering; vector clocks or single writer |
| Coordinator fails mid-transaction | 2PC vs 3PC | 2PC: recovery logs. 3PC: don't use—partitions break it |
| Two users' edits overwrite each other | CRDT vs LWW | Use CRDT for collaboration; OR-Set for lists |
| Need ordering + retention | HLC | HLC gives both; Lamport gives order only |
| "Does failover work?" | Chaos | Game day; kill primary; observe; fix |

When an interviewer asks "what would you do if X?"—map X to one of these patterns. The concepts are your toolkit.

---

# Deep Dive: Saga Pattern as 3PC/2PC Alternative

Because 2PC blocks and 3PC breaks under partitions, many systems **avoid distributed transactions entirely** using the **Saga pattern**. Instead of one atomic transaction across services, each service runs a **local transaction**. If a later step fails, run **compensating transactions** to undo prior steps.

**Example**: Order placement. (1) Order service: create order. (2) Payment service: charge card. (3) Inventory service: reserve stock. If (3) fails (out of stock), compensate: (2') refund, (1') cancel order. Each step is local. No 2PC. Eventually consistent. Possible states: order created but not charged; order charged but inventory not reserved; all complete; or compensated (rolled back logically).

**Choreography vs Orchestration**: Choreography—each service emits events; others react. Decentralized. Hard to reason about. Orchestration—central orchestrator calls each service, tracks state, triggers compensations. Easier to debug. Trade-off: choreography scales; orchestration is clearer. Saga is the dominant pattern for distributed business transactions in microservices. Know it when 2PC/3PC come up—Saga is the practical alternative.

---

# Deep Dive: Vector Clocks vs HLC — When to Use Which

**Vector clocks** assign each node a vector of logical timestamps (one per node). On event, increment own position. On message receive, merge: element-wise max. Guarantee: if A causally precedes B, VC(A) < VC(B). And: if VC(A) and VC(B) are incomparable, A and B are concurrent. **Concurrent detection**—vector clocks can tell you "these two events might conflict." Used in conflict resolution (Dynamo-style), version vectors (Riak).

**HLC** gives total order (physical + logical + node_id) but does not explicitly represent "concurrent." You get order; you don't get "A and B are concurrent." Use HLC when you need: (a) global transaction ordering, (b) retention by approximate time, (c) logs with causal order. Use vector clocks when you need: (a) conflict detection, (b) multi-version storage (keep both concurrent versions), (c) causal broadcast. Different tools for different needs.

---

# Further Reading and Mental Models

- **3PC**: Skeen (1982). Understand the pre-commit phase; know why partitions break it. Don't implement—understand.
- **Read consistency**: "Designing Data-Intensive Applications" (Kleppmann)—excellent coverage of consistency models. Practice: sketch the hierarchy (linearizability → eventual) and where your system sits.
- **HLC**: Kulkarni et al. (2014). CockroachDB docs on timestamps. Mental model: physical for "when," logical for "order."
- **CRDTs**: Shapiro et al. (2011). "A comprehensive study of Convergent and Commutative Replicated Data Types." Know G-Counter, OR-Set. Understand commutativity, associativity, idempotence—why they guarantee convergence.
- **Chaos**: "Chaos Engineering" (O'Reilly). Netflix Chaos Monkey. Principles of Chaos Engineering (principlesofchaos.org). Mental model: scientific method for failure. Hypothesis → experiment → learn.

---

# Exercises and Brainstorming

## Exercise 1: 3PC Partition Walkthrough

Three nodes (coordinator C, participants P1, P2) are mid-3PC commit. C has sent `PREPARE-TO-COMMIT` to both participants and received `READY` from P1, but the network partitions before P2 responds.

1. Walk through every possible state each node can be in when the partition occurs.
2. Which states are safe to continue from? Which require recovery?
3. A new coordinator takes over. What does it observe? What decision can it make?
4. Compare: in 2PC at the same point (coordinator has sent `PREPARE`, received YES from P1, partition before P2 responds), what can the new coordinator determine that it couldn't in 3PC? What *can't* it determine?
5. Given both 2PC and 3PC have blocking failure modes under partitions, what does the Saga pattern offer that they don't?

---

## Exercise 2: Read-Your-Writes Without a Primary Replica

Your collaborative document system uses 3 replicas (R1, R2, R3) with leader-based replication. The leader (R1) is removed from the design — all replicas are equal peers.

1. User Alice writes a document update. Her request lands on R2. Replication lag to R3 is ~200ms.
2. Alice's next request (read) routes to R3 (load balancer). She sees her old document.
3. Design a read-your-writes guarantee without a primary. Consider: sticky sessions, version tokens, causal tokens, quorum reads.
4. For each approach: what's the added latency? What happens when the node tracking Alice's session fails?
5. How does DynamoDB's Sessions Token approach work for this problem?

---

## Exercise 3: HLC Clock Skew — What Breaks?

Your distributed database uses Hybrid Logical Clocks (HLC). Physical clocks across 10 nodes are synchronized via NTP, typically within ±10ms.

1. A rogue NTP server causes node N7 to drift +500ms ahead of wall clock. Walk through: which operations does N7 timestamp incorrectly? Which dependent operations on other nodes are affected?
2. CockroachDB uses HLC and bounds clock uncertainty to 500ms ("max clock skew"). What does it do when it encounters a timestamp in the uncertainty window? What's the performance cost?
3. Your HLC invariant is: `HLC(e) >= physical_time(e)`. N7's physical clock is now 500ms *ahead*. Does this violate the invariant? What if it were 500ms *behind*?
4. How would you detect a drifting node in production monitoring? What alert threshold would you set?

---

## Exercise 4: CRDT vs OT for Collaborative Editing

Two users (Alice and Bob) are simultaneously editing a shared text document. Alice inserts "Hello" at position 0. Bob deletes the character at position 0. Both operations are concurrent — neither has seen the other's change.

1. With Last-Write-Wins (LWW): what's the outcome? What data is lost?
2. With an Operational Transform (OT) approach: how does the server transform Bob's delete against Alice's insert? What's the final state?
3. With a CRDT (specifically, an RGA — Replicated Growable Array): how does RGA resolve this? What does the final merged document look like?
4. Why is OR-Set insufficient for this problem? What property of RGA makes it better for ordered sequences?
5. Figma uses CRDT-like structures for vector graphics. Why is LWW acceptable for position properties (X, Y coordinates) but not for list operations (adding/removing layers)?

---

## Exercise 5: Chaos Engineering — Design a Game Day

Your team owns a payment processing service with a 99.95% SLO. You want to run your first Game Day to validate your circuit breakers and fallback paths.

1. Write a steady-state hypothesis: what does "normal" look like for this service in metrics terms? (Include: QPS, p99 latency, error rate, circuit breaker state)
2. Design three specific fault injection experiments, ordered by blast radius (smallest to largest):
   - Experiment A: localized, low risk
   - Experiment B: moderate blast radius
   - Experiment C: worst-case scenario (run in staging only)
3. For each experiment, define: the action, expected system behavior, pass/fail criterion, and rollback trigger.
4. Your circuit breaker opens during Experiment B. What should happen to in-flight requests? What happens to new requests? How long does the half-open probe wait?
5. How do you link the Game Day results to your error budget policy? If Experiment C reveals a gap that would consume 20% of your monthly error budget, how does that change your feature release schedule?

---

## "What If X Changes?" Brainstorming

**3PC and Transactions:**
- "Your payment system uses 2PC. The coordinator crashes mid-transaction. How long are participants blocked? What's the maximum blocking time in your design?"
- "You're asked to guarantee exactly-once payment processing across 3 microservices without 2PC. What pattern do you propose?"
- "A Saga's compensating transaction fails. Now what? Design a dead-letter handling strategy for failed compensations."

**Read Consistency:**
- "A user changes their email address and is immediately redirected to their profile page. The profile is served from a read replica with 500ms replication lag. What does the user see? How do you fix this without routing all reads to primary?"
- "Your system uses sticky sessions for read-your-writes. A sticky session server crashes. How do you handle users whose session was on that server?"

**HLC and Ordering:**
- "Two events happen 1ms apart on different nodes. Your HLC says event A happened before event B, but physical clocks say B happened first. Is your system correct? What guarantee does HLC actually provide?"
- "You need to generate globally unique, roughly time-ordered IDs for database rows. Compare: UUID v4, ULID, Snowflake ID, and HLC-based ID. Which do you choose and why?"

**CRDTs:**
- "You're building a collaborative spreadsheet. Cells can be numbers, strings, or formulas. Which CRDT (or combination) would you use for: (a) a counter cell, (b) a text cell with free-form editing, (c) a formula cell that references other cells?"
- "An OR-Set has 10,000 items added and removed over 1 year. What's the size of the metadata the OR-Set must track? Is there a garbage collection strategy?"

**Chaos Engineering:**
- "Your chaos experiment accidentally takes down production for 10 minutes. How do you run a blameless postmortem? What process changes do you make before the next experiment?"
- "You want to introduce chaos engineering to a risk-averse organization. What's your pitch to leadership? How do you start with zero blast radius?"

---

## Failure Injection Scenarios

**Scenario 1: Causal Consistency Violation**
A social media system uses causal consistency. Alice posts "I just got promoted!" (event A). Bob sees Alice's post and replies "Congratulations!" (event B, causally depends on A). Carol loads the thread and sees Bob's reply but not Alice's original post.

- Is this a causal consistency violation? Why or why not?
- What mechanism failed in the causal ordering guarantee?
- How do vector clocks or causal tokens prevent this?
- What's the user experience during recovery?

**Scenario 2: Split-Brain Under HLC**
A 3-node cluster using HLC experiences a network partition. Nodes N1+N2 form one partition; N3 is isolated. N3 continues accepting writes with monotonically increasing HLC timestamps.

- When the partition heals, N3's timestamps are 2 minutes ahead of N1+N2. What does the merge look like?
- HLC rule: `HLC = max(own_HLC, message_HLC) + epsilon`. When N3 sends its first message post-merge, what does N1 do with its HLC?
- If your system uses HLC timestamps for conflict resolution (higher timestamp wins), which writes from N3 survive? Are they causally correct?

**Scenario 3: CRDT Metadata Explosion**
Your collaborative editor uses an OR-Set (Observed-Remove Set) to track active collaborators. Over 2 years, 50,000 users have joined and left. Each add/remove generates a unique tag.

- What's the cumulative size of the OR-Set metadata after 2 years?
- Design a garbage collection strategy that removes tombstones for elements that are definitively gone (not just in a removed state locally).
- What coordination is required to safely garbage-collect a tombstone in a distributed system?
