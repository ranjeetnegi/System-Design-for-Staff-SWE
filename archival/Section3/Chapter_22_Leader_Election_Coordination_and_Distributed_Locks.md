# Chapter 22: Leader Election, Coordination, and Distributed Locks

## When Your System Needs a Boss—And When It Doesn't

---

# Quick Visual: The Coordination Landscape

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COORDINATION: WHEN DO YOU NEED IT?                       │
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │  PREFER NO COORDINATION (Best)                                       │  │
│   │  • Idempotent operations                                             │  │
│   │  • CRDTs (conflict-free replicated data types)                       │  │
│   │  • Partition data so each node owns its subset                       │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                              ↓                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │  IF YOU MUST: LEADER ELECTION                                        │  │
│   │  • Single coordinator for consistency                                │  │
│   │  • Database primary, job scheduler, metadata service                 │  │
│   │  • Use: Raft, ZooKeeper, etcd                                        │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                              ↓                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │  IF YOU MUST: DISTRIBUTED LOCKS                                      │  │
│   │  • Short-term mutual exclusion                                       │  │
│   │  • Protect critical sections                                         │  │
│   │  • ALWAYS use fencing tokens!                                        │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   RULE: Coordination is expensive. Minimize it. Plan for its failure.       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Simple Example: L5 vs L6 Coordination Thinking

| Scenario | L5 Approach | L6 Approach |
|----------|------------|-------------|
| **Job scheduler** | "Use a distributed lock" | "First, can we partition jobs by ID? If not, use leader election with degraded mode" |
| **Rate limiter** | "Use Redis for global counters" | "Per-node limits + async sync. Accept approximate. Plan for Redis failure." |
| **Config updates** | "Lock the config during update" | "Versioned configs. Readers use stale with TTL. No lock needed." |
| **Lock failure** | "Retry until success" | "Timeout + graceful degradation. What if lock service is down?" |
| **Duplicate prevention** | "Distributed lock per request" | "Idempotency keys. No coordination needed." |

---

# Key Numbers to Remember

| Metric | Typical Value | Why It Matters |
|--------|---------------|----------------|
| **NTP clock skew** | 10-100ms | Can't use timestamps for coordination |
| **TrueTime uncertainty** | ~7ms | Spanner waits this long for external consistency |
| **Leader election time** | 10-30 seconds | This is your failover window |
| **Lock TTL** | 10-30 seconds | Balance: too short = constant renewal, too long = slow recovery |
| **Raft heartbeat** | 50-150ms | Lower = faster detection, higher = less network overhead |
| **Raft election timeout** | 150-300ms | Must be > heartbeat interval |

---

## Table of Contents

1. [Introduction: The Coordination Tax](#introduction)
2. [Why Coordination Is Hard](#why-coordination-is-hard)
3. [Leader Election: Crowning a King in a Democracy](#leader-election)
4. [Distributed Locks: The Double-Edged Sword](#distributed-locks)
5. [Consensus: The Foundation (High-Level)](#consensus)
6. [Failure Scenarios That Will Ruin Your Week](#failure-scenarios)
7. [Case Study: Job Scheduler](#case-study-job-scheduler)
8. [Case Study: Rate Limiter Coordination](#case-study-rate-limiter)
9. [Case Study: Metadata Service](#case-study-metadata-service)
10. [Anti-Patterns: How Good Intentions Go Wrong](#anti-patterns)
11. [When NOT to Use Locks](#when-not-to-use-locks)
12. [Graceful Degradation: What Happens When Coordination Fails](#graceful-degradation)
13. [Interview Explanations](#interview-explanations)
14. [Brainstorming Questions](#brainstorming-questions)
15. [Homework: Remove Coordination and Re-Architect](#homework)

---

<a name="introduction"></a>
## 1. Introduction: The Coordination Tax

There's a moment in every distributed systems engineer's career when they realize a terrifying truth: **the hardest problems aren't about moving data—they're about getting machines to agree on anything.**

You want five servers to agree on who's the leader? Prepare for edge cases that will haunt your dreams.

You want a distributed lock so only one worker processes a job? Get ready for the lock to become a bottleneck, a single point of failure, or—worst of all—something that *looks* like it's working but isn't.

**Coordination is the dark matter of distributed systems.** It's invisible when it works and catastrophic when it fails. This section is about understanding when you need it, when you don't, and how to survive when it breaks.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    THE COORDINATION TAX — LATENCY COST                  │
│                                                                         │
│   Every coordination mechanism adds latency. More coordination = slower │
│                                                                         │
│   Mechanism           Latency      Use Case                             │
│   ─────────────────────────────────────────────────────────────         │
│   No coordination     ~1 ms       Best! Partition, idempotency          │
│   Partition-based     ~2 ms       Each node owns its subset             │
│   Leader election     ~10 ms      Single coordinator failover           │
│   Distributed lock   ~50 ms      Per-operation mutual exclusion        │
│   Consensus (Raft)    ~100 ms+    Strong agreement, replicated log      │
│                                                                         │
│   Latency ▲                                                             │
│     │                                                                   │
│ 100│                              ████████ Consensus                    │
│  50│                    ████████ Lock                                   │
│  10│          ████████ Leader                                           │
│   2│    ████ Partition                                                 │
│   1│ ██ None                                                           │
│   0└─────────────────────────────────────────────────────►            │
│                                                                         │
│   RULE: Coordination is expensive. Minimize it.                        │
└─────────────────────────────────────────────────────────────────────────┘
```

### The Fundamental Problem

In a distributed system, there is no global clock, no shared memory, and no guaranteed message delivery. Yet we often need exactly these things:

| What We Want | Why It's Hard |
|--------------|---------------|
| One leader at a time | Network partitions can create two "leaders" |
| Exactly-once processing | Failures can cause zero or duplicate processing |
| Mutual exclusion | Locks can be held by dead processes |
| Consistent ordering | Different nodes see events in different orders |
| Atomic operations | Partial failures leave inconsistent state |

Every coordination mechanism is a bet against the universe—a bet that the network will behave, that clocks won't drift too far, that processes will fail cleanly. Sometimes you win. Sometimes at 3 AM, you don't.

### Visual 1: Chapter at a Glance

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                    CHAPTER 22: COORDINATION AT A GLANCE                       ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  CORE CONCEPT: Coordination is expensive and fragile. Minimize it.             ║
║  When you must coordinate, use the right tool and plan for failure.           ║
║                                                                               ║
║  ┌─────────────────────────────────────────────────────────────────────────┐  ║
║  │                    COORDINATION DECISION FLOW                          │  ║
║  │                                                                         │  ║
║  │   Can I avoid it?  ──YES──► Idempotency / CRDTs / Partition ──► DONE    │  ║
║  │         │                                                                 │  ║
║  │        NO                                                                 │  ║
║  │         ▼                                                                 │  ║
║  │   Need 1 coordinator? ──YES──► Leader Election (Raft, etcd)              │  ║
║  │         │                                                                 │  ║
║  │        NO                                                                 │  ║
║  │         ▼                                                                 │  ║
║  │   Need short-term exclusion? ──► Distributed Locks + FENCING TOKENS      │  ║
║  └─────────────────────────────────────────────────────────────────────────┘  ║
║                                                                               ║
║  KEY TAKEAWAYS:                                                               ║
║  • Avoid coordination first: partition, idempotency, CRDTs                    ║
║  • Leader election > locks: one coordinator vs. many lock points              ║
║  • ALWAYS use fencing tokens with distributed locks                            ║
║  • Leader election time: 10-30 sec; Lock TTL: 10-30 sec; NTP skew: 10-100ms  ║
║  • Design graceful degradation: what happens when coordination fails?        ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

---

<a name="why-coordination-is-hard"></a>
## 2. Why Coordination Is Hard

### 2.1 The Two Generals Problem

Imagine two generals on opposite sides of a valley. They need to attack simultaneously or the attack fails. They can only communicate by messenger, but messengers might be captured.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        THE TWO GENERALS PROBLEM                         │
│                                                                         │
│     General A                                              General B    │
│     ┌───────┐                                              ┌───────┐    │
│     │       │         "Attack at dawn!"                    │       │    │
│     │   A   │ ────────────────────────────────────────────▶│   B   │    │
│     │       │                                              │       │    │
│     └───────┘                                              └───────┘    │
│                                                                         │
│     A doesn't know if B received the message.                           │
│                                                                         │
│     ┌───────┐                                              ┌───────┐    │
│     │       │            "Got it, I'll attack!"            │       │    │
│     │   A   │ ◀────────────────────────────────────────────│   B   │    │
│     │       │                                              │       │    │
│     └───────┘                                              └───────┘    │
│                                                                         │
│     Now B doesn't know if A knows that B will attack.                   │
│     This loops infinitely. Neither can ever be certain.                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Lesson:** In an unreliable network, **you cannot achieve guaranteed agreement with just message passing.** This isn't a limitation of your code—it's mathematically proven.

### 2.2 The FLP Impossibility Result

In 1985, Fischer, Lynch, and Paterson proved that **no deterministic consensus protocol can guarantee progress in an asynchronous system if even one process can fail.**

Translation for engineers:
- You cannot build a perfect consensus system
- Any system you build will either sacrifice availability (block forever) or consistency (give wrong answer)
- This is fundamental, not a bug in your implementation

**What this means practically:** All real coordination systems make trade-offs. They use timeouts, probabilistic guarantees, or stronger assumptions (like partially synchronous networks).

### 2.3 The Three Impossibilities You'll Fight

```
┌────────────────────────────────────────────────────────────────────────-─┐
│                     THE COORDINATION TRILEMMA                            │
│                                                                          │
│                           CORRECTNESS                                    │
│                          (Agreement)                                     │
│                               ▲                                          │
│                              ╱ ╲                                         │
│                             ╱   ╲                                        │
│                            ╱     ╲                                       │
│                           ╱  ???  ╲                                      │
│                          ╱         ╲                                     │
│                         ▼───────────▼                                    │
│                   LIVENESS        FAULT                                  │
│                  (Progress)     TOLERANCE                                │
│                                                                          │
│     You can have two strongly, the third weakly.                         │
│                                                                          │
│     Correctness + Liveness = Works until any failure (fragile)           │
│     Correctness + Fault Tolerance = May block forever (unavailable)      │
│     Liveness + Fault Tolerance = May give wrong answer (inconsistent)    │
│                                                                          │
└───────────────────────────────────────────────────────────────────────-──┘
```

### 2.4 Why Clocks Don't Help

"Just use timestamps to decide who wins!" — Famous last words

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          CLOCK SKEW DISASTER                            │
│                                                                         │
│   Server A clock: 10:00:00.000                                          │
│   Server B clock: 10:00:00.150 (150ms ahead)                            │
│                                                                         │
│   Timeline (real time):                                                 │
│   ─────────────────────────────────────────────────────────────▶        │
│                                                                         │
│   T=0ms:     A writes X=1 (timestamp 10:00:00.000)                      │
│   T=50ms:    B writes X=2 (timestamp 10:00:00.200) ← APPEARS LATER!     │
│                                                                         │
│   If using last-write-wins by timestamp:                                │
│   B's write wins, even though A wrote later in real time.               │
│                                                                         │
│   Result: Your "consistent" system just lost data.                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Clock skew in practice:**
- NTP can drift 10-100ms between syncs
- Cloud VMs can have sudden clock jumps (especially on VM migration)
- Leap seconds cause chaos
- Even Google's TrueTime has 7ms uncertainty bounds

**Lesson:** Clocks are useful for *ordering* but not for *coordination*. Never use timestamps as the sole arbitration mechanism for critical decisions.

### 2.5 Logical Clocks and Time in Distributed Systems

Since physical clocks can't be trusted, distributed systems use **logical clocks** to establish ordering.

#### 2.5.1 Lamport Clocks

```
LAMPORT CLOCK (Pseudo-code)
═══════════════════════════

Rules:
  1. Before each event: clock++
  2. When sending: clock++, attach clock to message
  3. When receiving: clock = max(local, received) + 1

Property: If A happened-before B, then L(A) < L(B)
Warning:  L(A) < L(B) does NOT imply A happened-before B

Example:
  Node A: tick() → clock=1, send() → clock=2 (message carries 2)
  Node B: receive(2) → clock = max(0, 2) + 1 = 3
  
  Conclusion: A's event (2) happened-before B's event (3)
```

#### 2.5.2 Vector Clocks

```
VECTOR CLOCK (Pseudo-code)
══════════════════════════

Unlike Lamport clocks, vector clocks detect concurrent events.
Each node maintains: VC[i] = "events I know about from node i"

Operations:
  tick():     VC[self]++
  send():     VC[self]++, attach VC to message
  receive(R): for each i: VC[i] = max(VC[i], R[i]), then VC[self]++

Compare(VC1, VC2):
  - If all VC1[i] ≤ VC2[i] and at least one <  → VC1 happened-before VC2
  - If all VC1[i] ≥ VC2[i] and at least one >  → VC2 happened-before VC1
  - If some VC1[i] < VC2[i] AND some VC1[j] > VC2[j] → CONCURRENT!

Example:
  A.tick() → {A:1, B:0, C:0}
  B.tick() → {A:0, B:1, C:0}   (no communication)
  
  Compare: A has A>0 but B<1, B has B>0 but A<1 → CONCURRENT
  Result: Need conflict resolution (LWW, merge, etc.)
```

#### 2.5.3 Hybrid Logical Clocks (HLC)

```
HYBRID LOGICAL CLOCK (Pseudo-code)
══════════════════════════════════

Format: (physical_time, logical_counter)
Used by: CockroachDB, MongoDB, TiDB

now():
  wall = get_wall_time()
  if wall > physical:
    physical = wall, logical = 0
  else:
    logical++
  return (physical, logical)

receive(recv_physical, recv_logical):
  wall = get_wall_time()
  if wall > max(physical, recv_physical):
    physical = wall, logical = 0
  elif physical > recv_physical:
    logical++
  elif recv_physical > physical:
    physical = recv_physical, logical = recv_logical + 1
  else:
    logical = max(logical, recv_logical) + 1

Example:
  ts1 = now() → (1642000000000, 0)
  ts2 = now() → (1642000000000, 1)  ← same ms, logical incremented
  [wait 1ms]
  ts3 = now() → (1642000000001, 0)  ← new ms, logical reset

Benefit: Orderable timestamps that track real time
```

#### 2.5.4 Google TrueTime

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          GOOGLE TRUETIME                                │
│                                                                         │
│   TrueTime doesn't give you a single timestamp.                         │
│   It gives you an INTERVAL: [earliest, latest]                          │
│                                                                         │
│   API:                                                                  │
│   - TT.now() → returns TTinterval [earliest, latest]                    │
│   - TT.after(t) → true if t is definitely in the past                   │
│   - TT.before(t) → true if t is definitely in the future                │
│                                                                         │
│   Implementation:                                                       │
│   - GPS receivers in every datacenter                                   │
│   - Atomic clocks as backup                                             │
│   - Uncertainty bound: typically 1-7ms                                  │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                                                                 │   │
│   │   Real time:      ─────────────────────────────────────▶        │   │
│   │                             │                                   │   │
│   │   TT.now():        [earliest│───────│latest]                    │   │
│   │                             │       │                           │   │
│   │                             │◀─────▶│                           │   │
│   │                             uncertainty                         │   │
│   │                             (ε ≈ 7ms)                           │   │
│   │                                                                 │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│   SPANNER'S COMMIT WAIT:                                                │
│   ─────────────────────                                                 │
│   After committing, Spanner waits until TT.after(commit_time) is true.  │
│   This guarantees the commit timestamp is definitely in the past.       │
│   Cost: ~7ms added to every write.                                      │
│   Benefit: External consistency (linearizability) without locks!        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

```
TRUETIME API (Pseudo-code)
══════════════════════════

TT.now()      → returns interval [earliest, latest]
TT.after(t)   → true if t is DEFINITELY in the past
TT.before(t)  → true if t is DEFINITELY in the future

SPANNER COMMIT WAIT:
  1. commit_ts = TT.now().latest
  2. apply_writes(commit_ts)
  3. wait until TT.after(commit_ts)  // ~7ms wait
  4. return commit_ts

Guarantee: Any future transaction sees our writes,
           any past transaction does not.
           = External consistency (linearizability) without locks!
```

### 2.6 Clock Synchronization Protocols

| Protocol | Accuracy | Use Case |
|----------|----------|----------|
| **NTP** | 10-100ms | General purpose |
| **PTP (IEEE 1588)** | 1μs-1ms | Financial, telecom |
| **GPS** | ~10ns | Spanner, TrueTime |
| **Atomic Clocks** | ~1ns | Backup for GPS |

**Staff-Level Insight:** The choice of clock synchronization affects your entire system design:
- **NTP-only:** Use logical clocks, assume 100ms+ skew
- **PTP:** Can use physical timestamps with ~1ms uncertainty
- **TrueTime:** Can achieve external consistency with commit-wait

---

<a name="leader-election"></a>
## 3. Leader Election: Crowning a King in a Democracy

### 3.1 What Leader Election Solves

Many distributed systems need a single authoritative node:

| Use Case | Why One Leader? |
|----------|-----------------|
| Database primary | Single source of truth for writes |
| Job scheduler | Avoid duplicate job execution |
| Metadata service | Consistent view of cluster state |
| Distributed lock service | Coordinate lock ownership |
| Message queue coordinator | Assign partitions to consumers |

Without leader election, you have two unpalatable options:
1. **No coordination:** Everyone acts independently (chaos, duplication, conflicts)
2. **Static configuration:** Hardcode the leader (single point of failure, manual intervention)

Leader election gives you **dynamic, automatic failover** with **exactly one leader** at any time.

```
┌─────────────────────────────────────────────────────────────────────────┐
│              WHY DO WE NEED A LEADER? — THE TRAFFIC COP ANALOGY         │
│                                                                         │
│   WITHOUT LEADER (Chaos):                                                │
│   ┌─────┐    ┌─────┐    ┌─────┐                                        │
│   │ S1  │    │ S2  │    │ S3  │   All 3 try to write to same data       │
│   │write│    │write│    │write│   → CONFLICT! → CORRUPTION!             │
│   └──┬──┘    └──┬──┘    └──┬──┘                                        │
│      │          │          │                                            │
│      └──────────┼──────────┘                                            │
│                 ▼                                                        │
│           ┌──────────┐                                                   │
│           │ Storage  │   Three writes at once = inconsistent state       │
│           │  ???     │                                                   │
│           └──────────┘                                                   │
│                                                                         │
│   WITH LEADER (Order):                                                  │
│   ┌─────┐    ┌─────┐    ┌─────┐                                        │
│   │ S1  │    │ S2  │    │ S3  │   One decides, others follow            │
│   │FOLL │    │LEAD │    │FOLL │   → Single source of truth              │
│   └──┬──┘    └──┬──┘    └──┬──┘                                        │
│      │          │          │                                            │
│      └──────────┼──────────┘                                            │
│                 ▼                                                        │
│           ┌──────────┐     Like a traffic cop: one direction at a time   │
│           │ Storage  │     No conflicts, no corruption                  │
│           │  ✓       │                                                   │
│           └──────────┘                                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 How Leader Election Works (Conceptually)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      LEADER ELECTION LIFECYCLE                          │
│                                                                         │
│   PHASE 1: ELECTION                                                     │
│   ─────────────────                                                     │
│                                                                         │
│     ┌─────┐    ┌─────┐    ┌─────┐                                       │
│     │  A  │    │  B  │    │  C  │    All nodes: "I want to be leader!"  │
│     │ 🗳️  |     │ 🗳️  │    │ 🗳️  │                                       │
│     └─────┘    └─────┘    └─────┘                                       │
│                                                                         │
│   PHASE 2: VOTING / CONSENSUS                                           │
│   ──────────────────────────                                            │
│                                                                         │
│     Nodes exchange votes based on:                                      │
│     - Who has the most up-to-date data?                                 │
│     - Who has the highest ID? (tie-breaker)                             │
│     - Who can reach majority of nodes?                                  │
│                                                                         │
│   PHASE 3: LEADERSHIP                                                   │
│   ───────────────────                                                   │
│                                                                         │
│     ┌─────┐    ┌─────┐    ┌─────┐                                       │
│     │  A  │    │  B  │    │  C  │                                       │
│     │ 👑  │───▶│     │───▶│     │    A is leader, B and C are followers │
│     │LEAD │    │FOLL │    │FOLL │                                       │
│     └─────┘    └─────┘    └─────┘                                       │
│                                                                         │
│   PHASE 4: HEARTBEAT                                                    │
│   ──────────────────                                                    │
│                                                                         │
│     Leader sends periodic heartbeats                                    │
│     Followers reset election timer on each heartbeat                    │
│     If no heartbeat for timeout period → back to Phase 1                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Leader Election Mechanisms

#### Mechanism 1: Lease-Based Leadership

```
LEASE-BASED LEADERSHIP (Pseudo-code)
════════════════════════════════════

Constants: LEASE_TTL = 10s, RENEWAL_INTERVAL = 3s

try_become_leader():
  acquired = store.SET_IF_NOT_EXISTS("leader", node_id, TTL=10s)
        if acquired:
    is_leader = true
    start renewal_loop

renewal_loop:
  while is_leader:
    sleep(RENEWAL_INTERVAL)
    renewed = store.SET_IF_EQUALS("leader", node_id, TTL=10s)
            if not renewed:
      is_leader = false
      on_leadership_lost()  // STOP ALL LEADER ACTIVITIES

on_leadership_lost():
  // CRITICAL: Immediately stop processing, close connections
  // Do NOT assume you're still the leader
```

**Key Properties:**
- Leader must actively renew lease
- If network partitions leader from lease store, leadership is lost automatically
- No split-brain: old leader's lease expires before new leader can acquire

#### Mechanism 2: Quorum-Based Election

```
QUORUM-BASED ELECTION (Pseudo-code)
═══════════════════════════════════

quorum_size = (num_peers / 2) + 1

start_election():
  term++
  votes = 1  // vote for self
  
  for each peer:
    response = peer.request_vote(candidate=self, term)
    if response.granted: votes++
  
  if votes >= quorum_size:
    become_leader()
        else:
    wait_random_timeout()
    maybe retry

heartbeat_loop():
  while i_am_leader:
            acks = 0
    for each peer:
      if peer.heartbeat(leader=self, term): acks++
    
    if acks < quorum_size - 1:
      step_down()  // lost quorum
    
    sleep(HEARTBEAT_INTERVAL)
```

### 3.4 What Leader Election Introduces (The Costs)

Leader election solves problems but creates new ones:

| Cost | Description |
|------|-------------|
| **Unavailability during election** | No leader = no progress for leader-dependent operations |
| **Election storms** | Under network instability, repeated elections waste resources |
| **Split-brain risk** | Improper implementation can lead to two leaders |
| **Leader bottleneck** | All coordination through one node limits throughput |
| **Failover latency** | Time between leader death and new leader = downtime |

**Real Example: ZooKeeper Election Storm**

```
Timeline of an actual incident:
─────────────────────────────────────────────────────────────────────────
00:00 - Leader dies (hardware failure)
00:01 - Followers detect missing heartbeat
00:02 - Election starts, Node B wins
00:03 - Node B dies (same hardware issue, shared rack)
00:04 - Another election, Node C wins
00:05 - Network glitch, C appears dead
00:06 - Election again, Node A (recovered) wins
00:07 - Cluster finally stable

7 minutes of instability, 3 elections, 0 progress on actual work.
─────────────────────────────────────────────────────────────────────────
```

**Lesson:** Leader election is not free. Design for fast elections, but also design your system to tolerate brief periods without a leader.

---

<a name="distributed-locks"></a>
## 4. Distributed Locks: The Double-Edged Sword

### 4.1 What Distributed Locks Promise

A distributed lock is supposed to provide **mutual exclusion** across multiple machines:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      DISTRIBUTED LOCK CONCEPT                           │
│                                                                         │
│   Goal: Only ONE process executes the critical section at a time        │
│                                                                         │
│   Process A        Lock Service        Process B                        │
│   ─────────        ────────────        ─────────                        │
│       │                 │                  │                            │
│       │──acquire()─────▶│                  │                            │
│       │◀────granted─────│                  │                            │
│       │                 │◀──acquire()──────│                            │
│       │    [critical    │────blocked──────▶│                            │
│       │     section]    │                  │                            │
│       │──release()─────▶│                  │                            │
│       │                 │◀──────────────-──│                            │
│       │                 │────granted──────▶│                            │
│       │                 │                  │   [critical section]       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 The Redlock Controversy: Why This Is Harder Than It Looks

Redis's Redlock algorithm was proposed as a distributed lock. Martin Kleppmann (author of "Designing Data-Intensive Applications") famously critiqued it. The debate reveals fundamental issues:

**The Problem:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    THE DISTRIBUTED LOCK RACE CONDITION                  │
│                                                                         │
│   Timeline:                                                             │
│   ─────────────────────────────────────────────────────────────▶        │
│                                                                         │
│   T1: Client A acquires lock (TTL = 10 seconds)                         │
│   T2: Client A starts long GC pause (or network issue)                  │
│   T3: Lock expires (A doesn't know, still paused)                       │
│   T4: Client B acquires lock (valid!)                                   │
│   T5: Client A wakes up, thinks it still has lock                       │
│   T6: Both A and B execute critical section simultaneously!             │
│                                                                         │
│   ┌──────────┐                              ┌──────────┐                │
│   │ Client A │ ←── Thinks it has lock ──→   │ Client B │                │
│   │          │                              │          │                │
│   │ [writes] │                              │ [writes] │                │
│   └──────────┘                              └──────────┘                │
│                         ⚠️ DATA CORRUPTION ⚠️                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**This happens because:**
1. Clocks can drift (TTL expires sooner/later than expected)
2. GC pauses can freeze a process for seconds
3. Network delays can make a process appear dead when it's not
4. The lock holder has no way to know the lock has expired

### 4.3 Fencing Tokens: The Solution

```
FENCING TOKENS (Pseudo-code)
════════════════════════════

LOCK SERVICE:
  acquire(client_id, ttl):
    if lock_free or lock_expired:
      token++
      holder = client_id
      expiry = now + ttl
      return {acquired: true, fencing_token: token}
    return {acquired: false}

PROTECTED RESOURCE:
  write(data, fencing_token):
    if fencing_token < highest_token_seen:
      REJECT("stale token")
    highest_token_seen = fencing_token
    do_write(data)
```

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    FENCING TOKENS IN ACTION                             │
│                                                                         │
│   T1: Client A acquires lock, gets token=33                             │
│   T2: Client A pauses (GC)                                              │
│   T3: Lock expires                                                      │
│   T4: Client B acquires lock, gets token=34                             │
│   T5: Client B writes to storage with token=34                          │
│   T6: Storage records highest_token = 34                                │
│   T7: Client A wakes up, tries to write with token=33                   │
│   T8: Storage REJECTS write: 33 < 34                                    │
│                                                                         │
│   Result: Data integrity preserved!                                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Critical Insight:** Fencing tokens only work if the downstream resource checks them. If you're writing to a legacy database that doesn't understand fencing tokens, you're not protected.

```
┌─────────────────────────────────────────────────────────────────────────┐
│              FENCING TOKENS: WHY THEY MATTER — STEP BY STEP             │
│                                                                         │
│   T1: Old Leader (token=33) still thinks it's leader (GC pause)           │
│       ┌────────────┐                                                    │
│       │ Old Leader │  "I have token 33, I'll write!"                     │
│       │ token=33   │                                                    │
│       └─────┬──────┘                                                    │
│             │                                                            │
│   T2: New Leader (token=34) elected                                     │
│       ┌────────────┐                                                    │
│       │ New Leader │  "I have token 34"                                 │
│       │ token=34   │  Write ACCEPTED ✓                                  │
│       └─────┬──────┘                                                    │
│             │                                                            │
│   T3: Storage has seen token 34                                         │
│       ┌─────────────────────────────────────────────┐                   │
│       │  Storage: highest_token_seen = 34           │                   │
│       └─────────────────────────────────────────────┘                   │
│             ▲                                                            │
│             │                                                            │
│   T4: Old Leader tries to write with token=33                           │
│       ┌────────────┐   write(data, token=33)                             │
│       │ Old Leader │ ────────────────────────────────►                   │
│       │ token=33   │                                                    │
│       └────────────┘                                                    │
│                                                                         │
│   T5: Storage REJECTS: "33 < 34, you're stale!"                         │
│       ┌─────────────────────────────────────────────┐                   │
│       │  Storage: REJECT — Safety preserved! ✓      │                   │
│       └─────────────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.4 Implementing Distributed Locks Correctly

```
REDIS DISTRIBUTED LOCK (Pseudo-code)
════════════════════════════════════

acquire(timeout):
  lock_id = uuid()
  deadline = now + timeout
  
  while now < deadline:
    // Atomic: SET if not exists + increment fencing token
    result = redis.EVAL("""
      if not EXISTS(lock_key) then
        token = INCR(token_key)
        SET(lock_key, lock_id, EX=ttl)
                    return token
                return nil
    """)
    
    if result != nil:
      return result  // fencing token
    
    sleep(100ms)
  
  raise Timeout

release():
  // Atomic: DELETE only if we still own it
  redis.EVAL("""
    if GET(lock_key) == lock_id then
      DEL(lock_key)
  """)

Usage:
  token = lock.acquire()
  process_job(token)  // pass fencing token to storage
    lock.release()
```

### 4.5 The Hidden Costs of Distributed Locks

| Cost | Impact |
|------|--------|
| **Lock service is SPOF** | If lock service is down, all locked operations fail |
| **Latency** | Every lock operation adds network round-trip |
| **Deadlocks** | Complex lock hierarchies can deadlock |
| **Starvation** | Busy locks may starve some clients |
| **Reduced throughput** | Serialization limits parallelism |
| **Debugging difficulty** | "Who holds the lock?" is hard to answer |

### 4.6 Advanced Locking Patterns

#### 4.6.1 Read-Write Locks

```
READ-WRITE LOCK (Pseudo-code)
═════════════════════════════

Rules:
  • Multiple readers can hold lock simultaneously
  • Writer needs exclusive access
  • Writer waits for all readers to finish

acquire_read():
  while timeout not expired:
    if no writer waiting:
      add self to readers
      reader_count++
      if still no writer: return success
      else: release and retry
  raise Timeout

acquire_write():
  if SET write_lock (NX): // claim writer slot
    while timeout not expired:
      if reader_count == 0:
        return success
    release and raise Timeout
  else:
    raise Contention

release_read(): reader_count--
release_write(): DEL write_lock (only if we own it)
```

#### 4.6.2 Hierarchical Locks (Lock Ordering)

```
HIERARCHICAL LOCKS (Pseudo-code)
════════════════════════════════

Hierarchy: database (0) → table (1) → row (2)
Rule: Acquire parent before child. Release child before parent.

acquire(resource_type, resource_id):
  my_level = HIERARCHY[resource_type]
  
  for each held_lock:
    if held_lock.level > my_level:
      raise HierarchyViolation  // can't acquire parent while holding child
  
  acquire_actual_lock(resource_type, resource_id)

release(resource_type, resource_id):
  my_level = HIERARCHY[resource_type]
  
  for each held_lock:
    if held_lock.level > my_level:
      raise HierarchyViolation  // can't release parent while holding child
  
  release_actual_lock(resource_type, resource_id)

Example:
  ✓ acquire(database) → acquire(table) → acquire(row)
  ✓ release(row) → release(table) → release(database)
  ✗ acquire(row) → acquire(table)  // VIOLATION!
```

#### 4.6.3 Try-Lock with Deadlock Detection

```
DEADLOCK DETECTION (Pseudo-code)
════════════════════════════════

Uses wait-for graph: Process A waits for Process B → edge A→B

register_wait(waiter, holder):
  add_edge(waiter → holder)
  if has_cycle(waiter):
    remove_edge(waiter)
    return DeadlockDetected
  return null

has_cycle(start):
  visited = {}
  current = start
  while current != null:
    if current in visited: return true  // CYCLE!
    visited.add(current)
    current = graph.get_next(current)
  return false

DEADLOCK-AWARE LOCK:
  acquire(resource):
    while timeout not expired:
      if try_acquire(): return success
      
      holder = get_current_holder()
      if register_wait(self, holder) == Deadlock:
        raise DeadlockAbort  // victim chosen
      
      sleep(10ms)
    raise Timeout
```

#### 4.6.4 Intention Locks (Multi-Granularity Locking)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    INTENTION LOCK HIERARCHY                             │
│                                                                         │
│   Lock Modes:                                                           │
│   - IS (Intention Shared): Intend to acquire S locks on descendants     │
│   - IX (Intention Exclusive): Intend to acquire X locks on descendants  │
│   - S (Shared): Read lock                                               │
│   - X (Exclusive): Write lock                                           │
│   - SIX (S + IX): Read this, intend to write descendants                │
│                                                                         │
│   Compatibility Matrix:                                                 │
│   ┌────────┬────┬────┬────┬────┬─────┐                                  │
│   │        │ IS │ IX │  S │  X │ SIX │                                  │
│   ├────────┼────┼────┼────┼────┼─────┤                                  │
│   │   IS   │ ✓  │ ✓  │ ✓  │ ✗  │  ✓  │                                  │
│   │   IX   │ ✓  │ ✓  │ ✗  │ ✗  │  ✗  │                                  │
│   │    S   │ ✓  │ ✗  │ ✓  │ ✗  │  ✗  │                                  │
│   │    X   │ ✗  │ ✗  │ ✗  │ ✗  │  ✗  │                                  │
│   │  SIX   │ ✓  │ ✗  │ ✗  │ ✗  │  ✗  │                                  │
│   └────────┴────┴────┴────┴────┴─────┘                                  │
│                                                                         │
│   Example: Read table T1, write row R1                                  │
│   ─────────────────────────────────────                                 │
│   1. Acquire IS on Database                                             │
│   2. Acquire IX on Table T1                                             │
│   3. Acquire S on Table T1 (read whole table)                           │
│   4. Acquire X on Row R1 (write specific row)                           │
│                                                                         │
│   This allows other transactions to:                                    │
│   - Read other tables (compatible with IS on Database)                  │
│   - Write other rows in T1 (compatible with IX on Table)                │
│                                                                         │
│   But blocks:                                                           │
│   - Exclusive lock on T1 (our S lock blocks it)                         │
│   - Any lock on R1 (our X lock blocks it)                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

```
INTENTION LOCKS (Pseudo-code)
═════════════════════════════

Lock modes: IS (intention shared), IX (intention exclusive),
            S (shared), X (exclusive), SIX (S + IX)

acquire(txn, resource_path, mode):
  // resource_path = ["database", "table:users", "row:123"]
  
  intention = IS if mode == S else IX
  
  // Acquire intention locks on ancestors
  for ancestor in resource_path[:-1]:
    acquire_lock(txn, ancestor, intention)
  
  // Acquire actual lock on target
  acquire_lock(txn, resource_path[-1], mode)

acquire_lock(txn, resource, mode):
  for each (holder, holder_mode) on resource:
    if not COMPATIBLE[mode, holder_mode]:
      raise Conflict
  grant_lock(txn, resource, mode)
```

---

<a name="consensus"></a>
## 5. Consensus: The Foundation (High-Level)

### 5.1 What Consensus Actually Means

Consensus is getting a group of nodes to **agree on a single value**, even when:
- Some nodes may fail
- Messages may be lost or delayed
- There is no global clock

**The Consensus Guarantees:**

| Property | Meaning |
|----------|---------|
| **Agreement** | All non-faulty nodes decide on the same value |
| **Validity** | The decided value was proposed by some node |
| **Termination** | All non-faulty nodes eventually decide |

### 5.2 Why You Need Consensus (Without Knowing It)

Every time you use these, you're using consensus under the hood:

- **etcd, ZooKeeper, Consul:** Configuration stores using Raft/Paxos
- **Kafka:** Leader election for partition leadership
- **CockroachDB, TiDB:** Distributed transactions
- **Kubernetes:** etcd-backed cluster state

### 5.3 Consensus Trade-offs (No Algorithms, Just Intuition)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CONSENSUS COST MODEL                                 │
│                                                                         │
│   For a write to be committed, it must be replicated to a QUORUM        │
│   (majority) of nodes.                                                  │
│                                                                         │
│   3-node cluster: quorum = 2 (survives 1 failure)                       │
│   5-node cluster: quorum = 3 (survives 2 failures)                      │
│   7-node cluster: quorum = 4 (survives 3 failures)                      │
│                                                                         │
│   Write latency = time to reach quorum (slowest of the fast majority)   │
│                                                                         │
│   ┌─────┐    ┌─────┐    ┌─────┐    ┌─────┐    ┌─────┐                   │
│   │ 5ms │    │ 8ms │    │12ms │    │45ms │    │200ms│                   │
│   │Node1│    │Node2│    │Node3│    │Node4│    │Node5│                   │
│   └─────┘    └─────┘    └─────┘    └─────┘    └─────┘                   │
│   ──────────────────────▲                                               │
│                         │                                               │
│              Write commits after Node3 acks (12ms)                      │
│              (quorum of 3 reached)                                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Key Intuitions:**

1. **Odd numbers are better:** 3 nodes and 4 nodes both survive 1 failure, but 4 nodes need more communication.

2. **Quorum overlap guarantees consistency:** Any two quorums share at least one node, so no two conflicting decisions can both succeed.

3. **Leader bottleneck:** Most consensus protocols route all writes through a leader.

4. **Read optimization:** Reads can go to any node (with some consistency trade-offs) or only to leader (for strongest consistency).

### 5.4 When You Need Consensus

| Situation | Need Consensus? | Why |
|-----------|-----------------|-----|
| Picking a leader | ✅ Yes | Must agree on exactly one |
| Committing a transaction | ✅ Yes | All or nothing across nodes |
| Updating cluster configuration | ✅ Yes | All nodes must see same config |
| Incrementing a counter | ⚠️ Maybe | Depends on accuracy requirements |
| Logging events | ❌ Usually no | Ordering often not critical |
| Caching | ❌ No | Eventual consistency is fine |

### 5.5 Raft Consensus Deep Dive

Understanding Raft is essential for Staff-level engineers. It's the consensus algorithm behind etcd, Consul, CockroachDB, and TiDB.

#### 5.5.1 Raft Core Components

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           RAFT ARCHITECTURE                             │
│                                                                         │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │                         REPLICATED LOG                           │  │
│   │                                                                  │  │
│   │   Index:  1       2       3       4       5       6              │  │
│   │         ┌───┐   ┌───┐   ┌───┐   ┌───┐   ┌───┐   ┌───┐            │  │
│   │  Term:  │ 1 │   │ 1 │   │ 2 │   │ 2 │   │ 2 │   │ 3 │            │  │
│   │         ├───┤   ├───┤   ├───┤   ├───┤   ├───┤   ├───┤            │  │
│   │  Cmd:   │x=1│   │y=2│   │x=3│   │z=4│   │y=5│   │x=6│            │  │
│   │         └───┘   └───┘   └───┘   └───┘   └───┘   └───┘            │  │
│   │                                   ▲                              │  │
│   │                             commitIndex                          │  │
│   └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│   Leader replicates log entries to followers.                           │
│   Entry is committed when replicated to majority.                       │
│   Committed entries are applied to state machine.                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    RAFT LOG REPLICATION — FOLLOWER CATCH-UP              │
│                                                                         │
│   Leader                    Followers                                    │
│   ┌────┬────┬────┬────┐    ┌────┬────┬────┐    ┌────┬────┐               │
│   │ 1  │ 2  │ 3  │ 4  │    │ 1  │ 2  │ 3  │    │ 1  │ 2  │  F2 behind!   │
│   └────┴────┴────┴────┘    └────┴────┴────┘    └────┴────┘               │
│        ▲  ▲  ▲  ▲                 ▲  ▲               ▲  ▲                 │
│        │  │  │  │                 │  │               │  │                 │
│   AppendEntries(4) ──────────────►│  │               │  │                 │
│   F1: ACK, committed             │  │               │  │                 │
│                                  │  │  F2: reject (missing 3,4)          │
│   Leader: decrement next_index[F2], retry with entry 3                   │
│   AppendEntries(3) ─────────────────────────────────►│  │                 │
│   F2: ACK                                                               │
│   AppendEntries(4) ─────────────────────────────────►│  │                 │
│   F2: ACK — NOW CAUGHT UP! ✓                                             │
│                                                                         │
│   COMMITTED when majority has entry. Follower behind? Catches up.        │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 5.5.2 Raft Election Step-by-Step

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    RAFT ELECTION: STEP-BY-STEP TIMELINE                  │
│                                                                         │
│   Step (1)  Leader heartbeat stops                                     │
│             ─────────────────────────                                   │
│             Leader L (term 3) crashes or network partitions             │
│             Followers no longer receive heartbeats                      │
│                                                                         │
│   Step (2)  Follower becomes candidate                                  │
│             ─────────────────────────────                               │
│             Follower F1's election timer expires                        │
│             F1: term++ (now term 4), state = CANDIDATE                   │
│                                                                         │
│   Step (3)  Requests votes from peers                                   │
│             ────────────────────────────                                │
│             F1 → F2: "RequestVote(term=4, log_info)"                     │
│             F1 → F3: "RequestVote(term=4, log_info)"                     │
│                                                                         │
│   Step (4)  Gets majority                                               │
│             ─────────────────                                            │
│             F2 grants (F1's log is up-to-date)                          │
│             F3 grants                                                   │
│             F1 has 2/3 votes → MAJORITY!                                │
│                                                                         │
│   Step (5)  Becomes new leader                                         │
│             ────────────────────                                        │
│             F1: state = LEADER, term = 4                                │
│                                                                         │
│   Step (6)  Sends heartbeats                                            │
│             ──────────────────                                           │
│             F1 → F2, F3: AppendEntries (heartbeat, no entries)           │
│             Resets followers' election timers                           │
│                                                                         │
│   TERM NUMBERS: Each election increments term. Higher term wins.       │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 5.5.3 Raft State Machine

```
RAFT CORE (Pseudo-code)
═══════════════════════

States: FOLLOWER, CANDIDATE, LEADER

Persistent state (survives restart):
  current_term, voted_for, log[]

Volatile state:
  commit_index, last_applied, state

Leader-only:
  next_index[peer], match_index[peer]

─────────────────────────────────────────────

ELECTION (on timeout):
  state = CANDIDATE
  term++
  voted_for = self
  votes = 1
  
  for each peer:
    if peer.request_vote(term, my_log_info).granted:
      votes++
  
  if votes > majority: become_leader()
  else: state = FOLLOWER

─────────────────────────────────────────────

VOTE REQUEST HANDLER:
  if request.term > my_term:
    my_term = request.term
    state = FOLLOWER
  
  grant = (haven't voted OR voted for this candidate)
          AND candidate_log >= my_log
  
  if grant: voted_for = candidate
  return grant

─────────────────────────────────────────────

LOG COMPARISON (who's more up-to-date):
  compare last_term first, then last_index
  higher term wins; if equal, longer log wins

─────────────────────────────────────────────

CLIENT REQUEST (leader only):
  append entry to local log
  replicate to followers (AppendEntries RPC)
  wait until majority acks → committed
  apply to state machine

─────────────────────────────────────────────

APPEND_ENTRIES (heartbeat + log replication):
  send: term, prev_log_index, prev_log_term, entries, commit_index
  follower: reject if log doesn't match, accept and append if it does
  leader: on reject, decrement next_index and retry

─────────────────────────────────────────────

COMMIT:
  entry committed when replicated to majority
  only commit entries from current term
```

#### 5.5.4 Raft Safety Properties

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        RAFT SAFETY GUARANTEES                           │
│                                                                         │
│   PROPERTY 1: Election Safety                                           │
│   ─────────────────────────────                                         │
│   At most one leader can be elected in a given term.                    │
│                                                                         │
│   Why: Each node votes once per term. Leader needs majority.            │
│        Two majorities always overlap, so only one can get majority.     │
│                                                                         │
│   PROPERTY 2: Leader Append-Only                                        │
│   ──────────────────────────────                                        │
│   A leader never overwrites or deletes entries in its log.              │
│   It only appends new entries.                                          │
│                                                                         │
│   PROPERTY 3: Log Matching                                              │
│   ────────────────────────────                                          │
│   If two logs contain an entry with the same index and term,            │
│   then the logs are identical in all entries up to that index.          │
│                                                                         │
│   Why: AppendEntries includes prev_log_index and prev_log_term.         │
│        Follower rejects if they don't match, forcing backtrack.         │
│                                                                         │
│   PROPERTY 4: Leader Completeness                                       │
│   ───────────────────────────────                                       │
│   If a log entry is committed in a given term, that entry will be       │
│   present in the logs of all leaders for higher terms.                  │
│                                                                         │
│   Why: Leader election requires up-to-date log. Committed entries       │
│        are on majority. New leader must have received votes from        │
│        at least one node with the committed entry.                      │
│                                                                         │
│   PROPERTY 5: State Machine Safety                                      │
│   ─────────────────────────────────                                     │
│   If a server has applied a log entry at a given index,                 │
│   no other server will ever apply a different entry for that index.     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 5.5.5 Raft Optimizations for Production

```
RAFT PRODUCTION OPTIMIZATIONS
═════════════════════════════

1. PRE-VOTE
   Before starting election, ask "would you vote for me?"
   If can't win, stay follower. Prevents term inflation from partitioned nodes.

2. PIPELINING
   Send multiple AppendEntries batches without waiting for each ack.
   Dramatically improves throughput.

3. LEARNER NODES
   Add new node as non-voting learner first.
   Replicate log to catch up. Then promote to voter.
   Prevents cluster disruption during scaling.

4. BATCHING
   Collect multiple client requests (e.g., 100 or wait 1ms).
   Single consensus round for the batch.
   Amortizes consensus cost.

5. READ LEASES
   Leader maintains lease (refreshed by heartbeats).
   If lease valid: serve read locally (no consensus).
   If expired: confirm leadership with quorum first.
```

#### 5.5.6 Raft vs Paxos Comparison

| Aspect | Raft | Multi-Paxos |
|--------|------|-------------|
| **Understandability** | Designed for clarity | Notoriously complex |
| **Leader** | Always required | Can be leaderless (basic Paxos) |
| **Log ordering** | Strictly ordered | Gaps allowed, fill later |
| **Membership change** | Joint consensus | Separate Paxos instance |
| **Performance** | 2 RTTs for writes | 2 RTTs (with stable leader) |
| **Implementations** | etcd, Consul, TiKV | Chubby (internal), Spanner |

### 5.6 Advanced Consensus Variants

#### 5.6.1 EPaxos (Egalitarian Paxos)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           EPAXOS OVERVIEW                               │
│                                                                         │
│   Unlike Raft/Multi-Paxos, EPaxos is LEADERLESS.                        │
│   Any node can propose commands directly.                               │
│                                                                         │
│   FAST PATH (no conflicts):                                             │
│   ─────────────────────────                                             │
│   Proposer ──propose──▶ Fast Quorum (F+1 nodes)                         │
│                              │                                          │
│                              ▼                                          │
│                         COMMITTED in 1 RTT!                             │
│                                                                         │
│   SLOW PATH (conflicts detected):                                       │
│   ────────────────────────────────                                      │
│   Proposer ──propose──▶ Fast Quorum                                     │
│                         │                                               │
│                    conflicts!                                           │
│                         │                                               │
│            ◀─────────────                                               │
│   Proposer ──accept───▶ Classic Quorum (majority)                       │
│                              │                                          │
│                              ▼                                          │
│                         COMMITTED in 2 RTTs                             │
│                                                                         │
│   BENEFITS:                                                             │
│   - Lower latency for non-conflicting commands                          │
│   - No leader bottleneck                                                │
│   - Better geo-distribution (closest replica handles request)           │
│                                                                         │
│   DRAWBACKS:                                                            │
│   - Complex implementation                                              │
│   - Command interference detection overhead                             │
│   - Execution order requires dependency tracking                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 5.6.2 Flexible Paxos

```
FLEXIBLE PAXOS (Concept)
════════════════════════

Key insight: Only quorum INTERSECTION matters, not quorum SIZE.

Traditional (5 nodes): Write=3, Read=3 (must overlap)
Flexible (5 nodes):    Write=4, Read=2 (still overlap! 4+2 > 5)

Use cases:
  • Read-heavy: smaller read quorum, larger write quorum
  • Write-heavy: smaller write quorum, larger read quorum

Invariant: write_quorum + read_quorum > num_nodes
```

### 5.7 Consistency Models Deep Dive

Understanding consistency models is essential for staff-level engineers. The choice of consistency model affects correctness, performance, and user experience.

#### 5.7.1 The Consistency Spectrum

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CONSISTENCY MODEL SPECTRUM                           │
│                                                                         │
│   Strongest                                              Weakest        │
│   ◀──────────────────────────────────────────────────────────────▶      │
│                                                                         │
│   ┌────────────┐ ┌───────────┐ ┌─────────-─┐ ┌─────────┐ ┌────--─────┐  │
│   │Lineariza-  │ │Sequential │ │ Causal    │ │Read-your│ │Eventual   │  │
│   │bility      │ │Consistency│ │Consistency│ │-writes  │ │Consistency│  │
│   └────────────┘ └───────────┘ └──────────-┘ └─────────┘ └────────--─┘  │
│                                                                         │
│   "Real-time     "All see      "Causally    "See own   "Eventually      │
│    ordering"      same order"   related      writes"    converge"       │
│                                 ordered"                                │
│                                                                         │
│   PERFORMANCE COST:                                                     │
│   High ←─────────────────────────────────────────────────────────→ Low  │
│                                                                         │
│   AVAILABILITY:                                                         │
│   Low ←──────────────────────────────────────────────────────────→ High │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 5.7.2 Linearizability (Strong Consistency)

```
LINEARIZABILITY EXPLAINED
═════════════════════════

Definition: Every operation takes effect instantaneously at some point
            between invocation and response.

Key properties:
  1. Real-time ordering: If A completes before B starts → A before B
  2. Single-copy semantics: Behaves as if there's one copy

Example (IS linearizable):
  Client A:  |--write(x=1)--|
  Client B:             |--read()→0--|    (write hasn't "taken effect" yet)
  Client C:                    |--read()→1--|

Example (NOT linearizable):
  Client A:  |--write(x=1)--|
  Client B:                      |--read()→1--|
  Client C:                               |--read()→0--|  ← VIOLATION!
  
  Once B sees 1, C cannot see 0. Values can't "un-happen".

─────────────────────────────────────────────────────────

IMPLEMENTING LINEARIZABLE READS:

Option 1 - ReadIndex (leader-based):
  1. Confirm still leader (heartbeat quorum)
  2. Wait for commit index to advance
  3. Read from state machine

Option 2 - Quorum read:
  1. Read from majority of nodes
  2. Return value with highest log index
```

#### 5.7.3 Sequential Consistency

```
SEQUENTIAL CONSISTENCY
══════════════════════

Definition: All processes see operations in the SAME order,
            and each process's ops appear in program order.

Difference from linearizability: No real-time ordering required.

Example (sequentially consistent, NOT linearizable):

  Real time:
  Process 1:  write(x=1) ..................  read(y)→0
  Process 2:  .........  write(y=1) .......  read(x)→0

  Both read 0! Both writes completed before reads (in real time).
  NOT linearizable.

  BUT sequentially consistent with order:
    read(x)→0, read(y)→0, write(x=1), write(y=1)

  Both see same order, each process's ops in program order. ✓
```

#### 5.7.4 Causal Consistency

```
CAUSAL CONSISTENCY
══════════════════

Definition: Only causally-related operations must be ordered.
  • If A depends on B → all processes see B before A
  • Concurrent ops → can appear in any order

Used by: MongoDB (default), Cassandra, DynamoDB

Implementation: Track dependencies with vector clocks

write(key, value):
  vector_clock.tick()
  store value with current vector_clock and dependencies
  
receive_write(write):
  if all dependencies satisfied:
    apply_write()
  else:
    buffer until dependencies arrive

Example:
  User A posts: "I'm getting married!"
  User B likes the post
  User C comments: "Congratulations!"

  Causal order: Post → Like, Post → Comment
  
  All replicas must show:
    • Like after Post ✓
    • Comment after Post ✓
    • Like vs Comment? Any order OK (concurrent)
```

#### 5.7.5 Consistency Model Comparison

| Model | Real-time Order | Total Order | Causal Order | Use Case |
|-------|-----------------|-------------|--------------|----------|
| **Linearizability** | ✅ Yes | ✅ Yes | ✅ Yes | Locks, counters, leader election |
| **Sequential** | ❌ No | ✅ Yes | ✅ Yes | Shared memory, caches |
| **Causal** | ❌ No | ❌ No | ✅ Yes | Social feeds, collaborative editing |
| **Eventual** | ❌ No | ❌ No | ❌ No | DNS, session stores |

#### 5.7.6 CAP Theorem and Consistency

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CAP THEOREM PRACTICAL GUIDE                          │
│                                                                         │
│   During a network partition, you must choose:                          │
│                                                                         │
│   CP (Consistency + Partition tolerance):                               │
│   ─────────────────────────────────────────                             │
│   - Sacrifice availability                                              │
│   - Minority partition cannot serve requests                            │
│   - Examples: etcd, ZooKeeper, Spanner                                  │
│                                                                         │
│   AP (Availability + Partition tolerance):                              │
│   ─────────────────────────────────────────                             │
│   - Sacrifice consistency                                               │
│   - All partitions can serve requests (may diverge)                     │
│   - Examples: Cassandra, DynamoDB, Riak                                 │
│                                                                         │
│   MODERN UNDERSTANDING:                                                 │
│   ──────────────────────                                                │
│   - CAP is about the partition state, not normal operation              │
│   - During normal operation, you can have both C and A                  │
│   - The real question: "What happens during partition?"                 │
│                                                                         │
│   PACELC (more nuanced):                                                │
│   ───────────────────────                                               │
│   If Partition: choose Availability or Consistency                      │
│   Else (normal): choose Latency or Consistency                          │
│                                                                         │
│   Examples:                                                             │
│   - Spanner: PC/EC (Consistent always, sacrifice latency)               │
│   - Cassandra: PA/EL (Available in partition, low latency normally)     │
│   - MongoDB: PA/EC (Available in partition, consistent normally)        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

<a name="failure-scenarios"></a>
## 6. Failure Scenarios That Will Ruin Your Week

### 6.1 Split Brain

The most dangerous failure mode in distributed coordination.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        SPLIT BRAIN SCENARIO                             │
│                                                                         │
│   Normal Operation:                                                     │
│   ────────────────                                                      │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                    CLUSTER (5 nodes)                            │   │
│   │                                                                 │   │
│   │      ┌───┐    ┌───┐    ┌───┐    ┌───┐    ┌───┐                  │   │
│   │      │ A │────│ B │────│ C │────│ D │────│ E │                  │   │
│   │      │(L)│    │   │    │   │    │   │    │   │                  │   │
│   │      └───┘    └───┘    └───┘    └───┘    └───┘                  │   │
│   │                                                                 │   │
│   │      A is the leader. All is well.                              │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│   Network Partition:                                                    │
│   ──────────────────                                                    │
│                                                                         │
│   ┌─────────────────────┐  ║  ┌─────────────────────────────────────┐   │
│   │    PARTITION 1      │  ║  │         PARTITION 2                 │   │
│   │                     │  ║  │                                     │   │
│   │   ┌───┐    ┌───┐    │  ║  │   ┌───┐    ┌───┐    ┌───┐           │   │
│   │   │ A │────│ B │    │  ║  │   │ C │────│ D │────│ E │           │   │
│   │   │(L)│    │   │    │  ║  │   │(L)│    │   │    │   │           │   │
│   │   └───┘    └───┘    │  ║  │   └───┘    └───┘    └───┘           │   │
│   │                     │  ║  │                                     │   │
│   │   A thinks it's     │  ║  │   C,D,E elect C as new leader       │   │
│   │   still leader      │  ║  │   (they have quorum!)               │   │
│   └─────────────────────┘  ║  └─────────────────────────────────────┘   │
│                            ║                                            │
│                      NETWORK PARTITION                                  │
│                                                                         │
│   TWO LEADERS! Both accepting writes! DATA DIVERGENCE!                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Visual 4: Split-Brain — What Goes WRONG Without Proper Design

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║           SPLIT-BRAIN FAILURE: CONFLICTING WRITES → DATA CORRUPTION            ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║   WITHOUT proper quorum check + fencing tokens:                                 ║
║                                                                               ║
║   PARTITION 1 (A,B)              ║     PARTITION 2 (C,D,E)                     ║
║   ┌─────────────────────────┐   ║     ┌─────────────────────────────────┐    ║
║   │ Leader A (stale)         │   ║     │ Leader C (new)                  │    ║
║   │ "I'm still leader!"      │   ║     │ "I have quorum"                  │    ║
║   │                         │   ║     │                                 │    ║
║   │ Write: account_1 += $50  │   ║     │ Write: account_1 += $30         │    ║
║   │ (token=33)               │   ║     │ (token=34)                      │    ║
║   └────────────┬──────────────┘   ║     └────────────┬────────────────────┘    ║
║                │                  ║                  │                        ║
║                ▼                  ║                  ▼                        ║
║   ┌─────────────────────────────────────────────────────────────────────┐    ║
║   │                    SHARED STORAGE / DATABASE                         │    ║
║   │                                                                      │    ║
║   │   Partition heals → MERGE CONFLICT                                    │    ║
║   │   Without fencing: Both writes applied → CORRUPTED BALANCE            │    ║
║   │   With fencing: Reject token=33; only token=34 wins → CORRECT         │    ║
║   │                                                                      │    ║
║   │   TIMELINE OF DISASTER:                                               │    ║
║   │   T+0:  Account balance = $100                                       │    ║
║   │   T+1:  A writes +$50 (sees $150)  │  C writes +$30 (sees $100)       │    ║
║   │   T+2:  Merge without ordering → $180? $150? $130? UNDEFINED!         │    ║
║   │   T+3:  Customer dispute, audit failure, $$$ lost                     │    ║
║   └─────────────────────────────────────────────────────────────────────┘    ║
║                                                                               ║
║   PREVENTION: Quorum check (step down if < majority) + Fencing tokens          ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

**Why This Happens:**
1. Network partition isolates minority (A, B) from majority (C, D, E)
2. A doesn't know it's partitioned—from its view, C, D, E just stopped responding
3. C, D, E have quorum (3/5) and elect new leader
4. A continues accepting writes (unless it checks for quorum)

**Prevention:**

```python
class SplitBrainSafeLeader:
    """Leader that steps down if it loses quorum."""
    
    def heartbeat_loop(self):
        while self.is_leader:
            reachable = 0
            for peer in self.peers:
                try:
                    peer.heartbeat()
                    reachable += 1
                except Unreachable:
                    pass
            
            # Include self in count
            if (reachable + 1) < self.quorum_size:
                logging.critical(
                    "Lost quorum! Stepping down to prevent split-brain"
                )
                self.is_leader = False
                self.stop_accepting_writes()
            
            time.sleep(self.heartbeat_interval)
```

### 6.2 Partial Failure

In distributed systems, operations can half-succeed—the worst possible outcome.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        PARTIAL FAILURE SCENARIO                         │
│                                                                         │
│   Operation: Transfer $100 from Account A to Account B                  │
│   Step 1: Deduct from A  →  SUCCESS                                     │
│   Step 2: Add to B       →  NETWORK TIMEOUT (??)                        │
│                                                                         │
│   What actually happened?                                               │
│                                                                         │
│   Option 1: The add failed (B has no money, A has less)                 │
│   Option 2: The add succeeded but ack was lost (both correct)           │
│   Option 3: The add is still in flight (will succeed later)             │
│                                                                         │
│   You cannot tell which happened!                                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Solutions:**

1. **Idempotency Keys:** Make operations safe to retry

```python
def transfer(from_account, to_account, amount, idempotency_key):
    # Check if already processed
    if db.exists(f"transfer:{idempotency_key}"):
        return db.get(f"transfer:{idempotency_key}")  # Return cached result
    
    # Process transfer
    result = do_transfer(from_account, to_account, amount)
    
    # Record result
    db.set(f"transfer:{idempotency_key}", result, ttl=86400)
    
    return result
```

2. **Saga Pattern:** Compensating transactions (covered in Part 2)

3. **Two-Phase Commit:** Prepare all parties before committing

### 6.2B Cascading Failure Timeline: When Coordination Collapses

Coordination failures cascade through dependent services in predictable patterns. Understanding this timeline helps Staff engineers design containment strategies and set realistic SLAs.

```
┌─────────────────────────────────────────────────────────────────────────┐
│         CASCADING FAILURE TIMELINE: ZOOKEEPER LEADER ELECTION           │
│                                                                         │
│   T+0:    ZooKeeper leader node experiences high GC pause (2 seconds)  │
│   T+2s:   Followers detect missed heartbeat, initiate leader election   │
│   T+3s:   All sessions with old leader enter "connection loss" state    │
│   T+5s:   Leader election completes, new leader elected                 │
│   T+5-15s: Session reconnection storm — all clients reconnect           │
│            simultaneously                                               │
│   T+8s:   New leader overwhelmed by session re-establishment            │
│   T+10s:  Lock holders uncertain — fencing tokens may be invalid        │
│   T+12s:  Applications with locks begin "safety timeout" — pause        │
│            operations                                                    │
│   T+15s:  Thundering herd: all paused operations retry simultaneously   │
│   T+20s:  New leader CPU at 100% from reconnection + lock reacquisition │
│   T+30s:  Some clients timeout and escalate to "coordination            │
│            unavailable" mode                                             │
│   T+60s:  Stability returns as reconnection storm subsides              │
│                                                                         │
│   User-Visible Impact:                                                  │
│   - 30-60 seconds of degraded service for all lock-dependent features   │
│   - Partial availability: some operations succeed, others timeout       │
│   - Error rates spike to 20-40% during recovery window                  │
│                                                                         │
│   Blast Radius:                                                         │
│   Every service using this ZK cluster is affected simultaneously.      │
│   If 50 services depend on the cluster, all 50 experience degradation.  │
│                                                                         │
│   Containment Strategies:                                               │
│   1. Separate ZK clusters per criticality tier (critical vs. non-       │
│      critical workloads)                                                │
│   2. Circuit breakers on ZK clients (fail fast when ZK is unhealthy)   │
│   3. Cached last-known-good state (allow degraded mode during outages) │
│                                                                         │
│   Prevention:                                                           │
│   - GC tuning (reduce pause times to < 100ms)                           │
│   - Dedicated coordination nodes (no co-located workloads)              │
│   - Connection pooling to limit reconnection storms                     │
│   - Exponential backoff on reconnection attempts                        │
└─────────────────────────────────────────────────────────────────────────┘
```

**Timeline Breakdown:**

- **T+0**: ZooKeeper leader node experiences high GC pause (2 seconds)
- **T+2s**: Followers detect missed heartbeat, initiate leader election
- **T+3s**: All sessions with old leader enter "connection loss" state
- **T+5s**: Leader election completes, new leader elected
- **T+5-15s**: Session reconnection storm—all clients reconnect simultaneously
- **T+8s**: New leader overwhelmed by session re-establishment
- **T+10s**: Lock holders uncertain—fencing tokens may be invalid
- **T+12s**: Applications with locks begin "safety timeout"—pause operations
- **T+15s**: Thundering herd: all paused operations retry simultaneously
- **T+20s**: New leader CPU at 100% from reconnection + lock reacquisition
- **T+30s**: Some clients timeout and escalate to "coordination unavailable" mode
- **T+60s**: Stability returns as reconnection storm subsides

**User-Visible Impact:**

30-60 seconds of degraded service for all lock-dependent features. Partial availability: some operations succeed, others timeout. Error rates spike to 20-40% during recovery window.

**Blast Radius:**

Every service using this ZK cluster is affected simultaneously. If 50 services depend on the cluster, all 50 experience degradation.

**Containment:**

- Separate ZK clusters per criticality tier (critical vs. non-critical workloads)
- Circuit breakers on ZK clients (fail fast when ZK is unhealthy)
- Cached last-known-good state (allow degraded mode during outages)

**Prevention:**

- GC tuning (reduce pause times to < 100ms)
- Dedicated coordination nodes (no co-located workloads)
- Connection pooling to limit reconnection storms
- Exponential backoff on reconnection attempts

### 6.2C Real Incident: Stale Lock Holder Data Corruption

At Staff level, real incidents teach judgment. This incident illustrates why fencing tokens are non-negotiable and how coordination failures propagate.

| Part | Content |
|------|---------|
| **Context** | Large-scale job scheduler at a cloud provider. 50,000 jobs/day across 200 workers. Single ZooKeeper cluster for leader election and per-job lock claims. Jobs write to shared storage (blob store). |
| **Trigger** | Worker A holds lock for job J1. Worker A enters 12-second GC pause (JVM Full GC). ZooKeeper session times out (session timeout = 10s). Lock expires. Worker B acquires lock for J1. |
| **Propagation** | Worker A wakes from GC, unaware lock expired. Both A and B execute job J1. Both write to blob store. Storage layer had no fencing token check—accepted both writes. Same blob path overwritten twice. Downstream consumers read partially corrupted data. |
| **User impact** | ~200 jobs duplicated; 40 jobs had corrupted output (both workers wrote to same paths). Affected batch pipelines failed. Support tickets from enterprise customers. Estimated 4-hour recovery window for affected pipelines. |
| **Engineer response** | On-call detected duplicate job executions from metrics. Traced to ZooKeeper session expiration spike during GC. Stopped scheduler, identified affected jobs, re-ran from safe checkpoints. Root cause analysis took 6 hours due to distributed traces across ZK, workers, and storage. |
| **Root cause** | No fencing tokens. Storage layer trusted lock holder identity without epoch/token. GC pause exceeded session timeout. Lock service and storage were designed independently—no contract for token propagation. |
| **Design change** | (1) Lock service now returns monotonically increasing fencing token with every lock grant. (2) Storage layer rejects writes with token ≤ last-seen token per resource. (3) Worker passes token to all downstream writes. (4) GC tuning: MaxGCPauseMillis=50ms, moved scheduler off shared JVM. (5) Session timeout increased to 30s with justification documented. |
| **Lesson learned** | "Locks expire. Processes pause. Fencing tokens are not optional—they are the only way to guarantee that a 'stale' lock holder cannot corrupt data. If your storage layer doesn't support tokens, you cannot safely use distributed locks for that resource." |

**L6 Takeaway:** Coordination correctness requires defense in depth. The lock prevents concurrent acquisition; the fencing token prevents stale holders from acting. Both are required.

### 6.3 Clock Skew

Clocks lie. Plan accordingly.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     CLOCK SKEW DISASTER SCENARIOS                       │
│                                                                         │
│   SCENARIO 1: Lease Expires Early                                       │
│   ─────────────────────────────                                         │
│                                                                         │
│   Real time:    |-------- 10 seconds --------|                          │
│   Node A clock: |---- 8 seconds ----|                                   │
│                                     ↑                                   │
│                         Node A thinks lease expired!                    │
│                         Stops working, but lease is actually valid.     │
│                                                                         │
│   SCENARIO 2: Lock Appears Available When It's Not                      │
│   ─────────────────────────────────────────────────                     │
│                                                                         │
│   Node A acquires lock at T=0 with TTL=10s                              │
│   Node B's clock is 15 seconds ahead                                    │
│   Node B thinks lock expired at T=0 (B's time shows T=15)               │
│   Node B takes lock while A still holds it!                             │
│                                                                         │
│   SCENARIO 3: Out-of-Order Events                                       │
│   ────────────────────────────                                          │
│                                                                         │
│   Node A: Event at timestamp 100                                        │
│   Node B: Event at timestamp 95 (clock was behind)                      │
│   Log shows B happened before A, but A actually happened first!         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Mitigations:**

| Approach | Description | Trade-off |
|----------|-------------|-----------|
| **Logical clocks** | Vector clocks, Lamport timestamps | No wall-clock time, complex |
| **Hybrid clocks** | Physical + logical (HLC) | Still needs bounded skew |
| **TrueTime (Google)** | GPS + atomic clocks, bounded uncertainty | Expensive hardware |
| **Conservative TTLs** | Account for worst-case skew | Longer lock durations |

```
CLOCK-SKEW-SAFE LOCK (Pseudo-code)
══════════════════════════════════

MAX_CLOCK_SKEW = 5 seconds (conservative)

acquire(ttl=30):
  // Use longer TTL to handle skew
  effective_ttl = ttl + MAX_CLOCK_SKEW
  lock_service.acquire(effective_ttl)
  
  // But locally, assume shorter validity (pessimistic)
  local_expiry = now + ttl - MAX_CLOCK_SKEW

is_still_valid():
  return now < local_expiry

Key: Be generous to others, conservative for yourself.
```

### 6.4 Failure Detection: How Do You Know a Node Is Dead?

In distributed systems, you can't distinguish between a dead node and a slow/partitioned one. Failure detection is about **probabilistic suspicion**, not certainty.

#### 6.4.1 The Phi Accrual Failure Detector

```
PHI ACCRUAL FAILURE DETECTOR
════════════════════════════

Used by: Akka, Cassandra

Key idea: Instead of binary alive/dead, output a "suspicion level" (phi).
          Higher phi = more likely dead.

phi = -log10(P(heartbeat would arrive by now))

Interpretation:
  phi = 1  →  10% chance alive
  phi = 2  →   1% chance alive
  phi = 3  →  0.1% chance alive
  phi = 8  →  Threshold for "dead" (configurable)

Benefits:
  • Adapts to network conditions automatically
  • Uses historical heartbeat distribution
  • Configurable threshold per use case

Algorithm:
  1. Track heartbeat intervals in sliding window
  2. Calculate mean and std_dev of intervals
  3. When checking: how likely is current gap given history?
  4. If phi > threshold → consider node dead
```

#### 6.4.2 SWIM Protocol (Scalable Weakly-consistent Infection-style Membership)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          SWIM PROTOCOL                                  │
│                                                                         │
│   Used by: Consul, Serf, HashiCorp Memberlist                           │
│                                                                         │
│   PROBLEM: Traditional heartbeat to all nodes = O(n²) messages          │
│   SWIM: Achieves O(n) message complexity                                │
│                                                                         │
│   MECHANISM:                                                            │
│   ──────────                                                            │
│                                                                         │
│   1. DIRECT PROBE: Each period, pick random member, send ping           │
│                                                                         │
│      ┌───┐          ping           ┌───┐                                │
│      │ A │ ─────────────────────▶  │ B │                                │
│      │   │ ◀─────────────────────  │   │                                │
│      └───┘          ack            └───┘                                │
│                                                                         │
│   2. INDIRECT PROBE: If no ack, ask K random members to probe           │
│                                                                         │
│      ┌───┐   ping-req    ┌───┐    ping     ┌───┐                        │
│      │ A │ ────────────▶ │ C │ ──────────▶ │ B │                        │
│      │   │               │   │ ◀────────── │   │                        │
│      │   │ ◀──────────── │   │    ack      │   │                        │
│      └───┘     ack       └───┘             └───┘                        │
│                                                                         │
│   3. SUSPECT: If still no response, mark as SUSPECT (not dead yet)      │
│                                                                         │
│   4. CONFIRM DEAD: After timeout, mark as DEAD and disseminate          │
│                                                                         │
│   DISSEMINATION (Infection-style):                                      │
│   ─────────────────────────────────                                     │
│   Membership updates piggybacked on protocol messages                   │
│   Spreads like gossip: log(n) rounds to reach all members               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

```
SWIM PROTOCOL (Pseudo-code)
═══════════════════════════

State: alive{}, suspected{}, dead{}

protocol_round():
  target = pick_random_member()
  
  // Step 1: Direct probe
  if ping(target).success:
    mark_alive(target)
    return
  
  // Step 2: Indirect probe (ask K others to ping target)
  for prober in random_k_members(3):
    if prober.ping(target).success:
      mark_alive(target)
      return
  
  // Step 3: Mark as suspect (not dead yet!)
  mark_suspect(target)

check_suspect_timeout():
  for each suspected member:
    if now - suspect_time > TIMEOUT:
      mark_dead(member)

refute_suspicion():
  // If I'm suspected, increment my incarnation to prove I'm alive
  incarnation++
  broadcast("ALIVE", self, incarnation)

Key insight: Incarnation numbers let you refute suspicion.
             Higher incarnation = more recent state.
```

#### 6.4.3 Failure Detection Trade-offs

| Detector Type | Detection Time | False Positive Rate | Network Cost |
|---------------|----------------|--------------------| -------------|
| **Fixed timeout** | Fast | High when network varies | Low |
| **Phi Accrual** | Adaptive | Low (self-tuning) | Low |
| **SWIM** | Medium | Low | O(n) total |
| **All-to-all heartbeat** | Fast | Low | O(n²) |

**Staff-Level Insight:** The choice of failure detector affects your SLOs:
- **Fast detection (1s):** More false positives, more failovers, more disruption
- **Slow detection (30s):** Fewer false positives, but longer outages
- **Phi Accrual:** Self-tuning, but complex to operate
- **SWIM:** Scales well, but membership changes are eventually consistent

---

<a name="case-study-job-scheduler"></a>
## 7. Case Study: Job Scheduler

### 7.1 The Problem

Design a distributed job scheduler that:
- Runs jobs at scheduled times
- Ensures each job runs **exactly once**
- Handles worker failures
- Scales horizontally

### 7.2 Naive Approach (And Why It Fails)

```
BROKEN JOB SCHEDULER
════════════════════

poll_and_run():
  while true:
    job = db.query("SELECT ... WHERE status='pending' LIMIT 1")
            if job:
      db.execute("UPDATE ... SET status='running' WHERE id=?", job.id)
      run_job(job)
      db.execute("UPDATE ... SET status='completed' WHERE id=?", job.id)
    sleep(1)

PROBLEMS:
  1. Two workers see same job → duplicate execution!
  2. Worker crashes after claiming → job stuck in 'running'
  3. Race between SELECT and UPDATE → lost updates
```

**Failure Modes:**
1. Two workers grab the same job (duplicate execution)
2. Worker crashes after claiming job (job stuck in 'running')
3. No coordination on which jobs to prioritize

### 7.3 Correct Approach: Leader-Based Scheduler

```
COORDINATED JOB SCHEDULER (Pseudo-code)
═══════════════════════════════════════

LEADER (assigns jobs):
  jobs = get_pending_jobs()
  workers = get_active_workers()
  
  for job in jobs:
    assign to next worker (round-robin)
    push job_id to worker's queue

WORKER (executes jobs):
  register_as_active()
  job_id = pop_from_my_queue()
        
        if job_id:
    lock = acquire_lock(job_id)
    try:
      // Double-check still assigned to me
      if job.worker_id != me: return
      
      set_status('running')
      result = run_job(job)
      set_status('completed', fencing_token=lock.token)
    except:
      set_status('failed', error)
        finally:
      release_lock()
```

### 7.4 What Happens When Coordination Fails

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Leader dies | New jobs not assigned until new leader | Fast election (< 10s), job queue buffers |
| Redis down | No locks, no queues | Graceful degradation, local queue fallback |
| Worker dies mid-job | Job stuck in 'running' | Timeout-based job reclamation |
| Network partition | Workers can't reach leader | Local job buffering, eventual sync |

```
JOB RECLAIMER (Pseudo-code)
═══════════════════════════

run():
  every 60 seconds:
    stuck = find_jobs(status='running', updated_at < 5_min_ago)
    
    for job in stuck:
      if not is_worker_alive(job.worker_id):
        reset_job(status='pending', worker=NULL, attempts++)
        log("Reclaimed stuck job from dead worker")
```

---

<a name="case-study-rate-limiter"></a>
## 8. Case Study: Rate Limiter Coordination

### 8.1 The Problem

Implement a rate limiter that:
- Limits requests per user per time window
- Works across multiple servers
- Has sub-millisecond latency
- Is reasonably accurate (not perfect)

### 8.2 The Coordination Spectrum

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    RATE LIMITER COORDINATION SPECTRUM                   │
│                                                                         │
│   ← Less Coordination                    More Coordination →            │
│                                                                         │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────┐   │
│   │   Local      │  │   Periodic   │  │   Real-time  │  │  Central  │   │
│   │   Counters   │  │   Sync       │  │   Sync       │  │  Counter  │   │
│   └──────────────┘  └──────────────┘  └──────────────┘  └───────────┘   │
│                                                                         │
│   Accuracy:  ⭐          ⭐⭐⭐          ⭐⭐⭐⭐⭐       ⭐⭐⭐⭐⭐         │
│   Latency:   ⭐⭐⭐⭐⭐     ⭐⭐⭐⭐         ⭐⭐⭐          ⭐⭐            │
│   Complexity: ⭐          ⭐⭐           ⭐⭐⭐⭐        ⭐⭐⭐             │
│   Fault Tol: ⭐⭐⭐⭐⭐     ⭐⭐⭐⭐         ⭐⭐           ⭐              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 8.3 Approach 1: Local Counters (No Coordination)

```
LOCAL RATE LIMITER (Pseudo-code)
════════════════════════════════

is_allowed(user_id):
  if counters[user_id] >= limit:
    return false
  counters[user_id]++
  return true

PROBLEMS:
  • Same server → get 1/N of limit
  • Spread across servers → get N× limit
  • Load balancer changes → unpredictable limits
```

**Problems:**
- If user hits same server, they get 1/N of actual limit
- If user spreads across servers, they get N× actual limit
- Load balancer changes can drastically change effective limit

### 8.4 Approach 2: Periodic Sync (Light Coordination)

```
PERIODIC SYNC RATE LIMITER (Pseudo-code)
════════════════════════════════════════

FAST PATH (every request):
  is_allowed(user_id):
    if local_counts[user_id] >= local_limits[user_id]:
      return false
    local_counts[user_id]++
    return true

BACKGROUND SYNC (every 1 second):
  sync():
    // Push local counts to Redis
    for user_id, count in local_counts:
      redis.INCRBY(f"rate:{user_id}:{window}", count)
    local_counts.clear()
    
    // Get updated global counts, recalculate local limits
    for user_id:
      global_count = redis.GET(...)
      remaining = global_limit - global_count
      local_limits[user_id] = remaining / num_servers
```

### 8.5 What Happens When Coordination Fails

```
┌─────────────────────────────────────────────────────────────────────────┐
│                  RATE LIMITER DEGRADATION MODES                         │
│                                                                         │
│   REDIS DOWN:                                                           │
│   ────────────                                                          │
│                                                                         │
│   Option A: Fail Open (allow all requests)                              │
│     - Risk: No rate limiting, system may be overwhelmed                 │
│     - Use when: Rate limiting is best-effort                            │
│                                                                         │
│   Option B: Fail Closed (deny all requests)                             │
│     - Risk: Legitimate traffic blocked                                  │
│     - Use when: Protecting critical resources                           │
│                                                                         │
│   Option C: Local-only mode (fall back to local counters)               │
│     - Risk: Inaccurate limits, but still some protection                │
│     - Use when: "Best effort is good enough"                            │
│                                                                         │
│   NETWORK PARTITION:                                                    │
│   ──────────────────                                                    │
│                                                                         │
│   Servers can't sync with each other.                                   │
│   Each server uses own local view.                                      │
│   Effective limit = local_limit × num_partitioned_servers               │
│                                                                         │
│   Example: 3 servers, limit 100/min, partition isolates 2               │
│   Group 1 (1 server): allows 33/min                                     │
│   Group 2 (2 servers): allows 66/min                                    │
│   Total possible: 99/min (close enough!)                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

```
RESILIENT RATE LIMITER (Pseudo-code)
════════════════════════════════════

is_allowed(user_id):
  try:
    return check_distributed(user_id)
  catch RedisError:
    log("Redis down, using local mode")
    return check_local(user_id)

check_local(user_id):
  local_limit = global_limit / expected_server_count
  return local_counter.check(user_id, local_limit)
```

---

<a name="case-study-metadata-service"></a>
## 9. Case Study: Metadata Service

### 9.1 The Problem

Design a metadata service that:
- Stores cluster configuration (shard mappings, feature flags, etc.)
- Must be strongly consistent (all nodes see same config)
- Must be highly available
- Used by hundreds of services for every request

This is essentially what etcd, ZooKeeper, and Consul do.

### 9.2 The Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    METADATA SERVICE ARCHITECTURE                        │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                     METADATA CLUSTER (3-5 nodes)                │   │
│   │                                                                 │   │
│   │    ┌─────────┐    ┌─────────┐    ┌─────────┐                    │   │
│   │    │  Node 1 │◀──▶│  Node 2 │◀──▶│  Node 3 │                    │   │
│   │    │         │    │         │    │         │                    │   │
│   │    │ LEADER  │    │FOLLOWER │    │FOLLOWER │                    │   │
│   │    └────┬────┘    └────┬────┘    └────┬────┘                    │   │
│   │         │              │              │                         │   │
│   │         └──────────────┼──────────────┘                         │   │
│   │                        │                                        │   │
│   │                   RAFT CONSENSUS                                │   │
│   │              (Writes go through leader,                         │   │
│   │               replicated to quorum)                             │   │
│   │                                                                 │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│              ┌───────────────┼───────────────┐                          │
│              ▼               ▼               ▼                          │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│   │   Service A  │  │   Service B  │  │   Service C  │                  │
│   │              │  │              │  │              │                  │
│   │  ┌────────┐  │  │  ┌────────┐  │  │  ┌────────┐  │                  │
│   │  │ LOCAL  │  │  │  │ LOCAL  │  │  │  │ LOCAL  │  │                  │
│   │  │ CACHE  │  │  │  │ CACHE  │  │  │  │ CACHE  │  │                  │
│   │  └────────┘  │  │  └────────┘  │  │  └────────┘  │                  │
│   └──────────────┘  └──────────────┘  └──────────────┘                  │
│                                                                         │
│   Services cache metadata locally, subscribe to updates via WATCH       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 9.3 Coordination Patterns in Metadata Service

#### Pattern 1: Leader Election via Metadata Service

```
LEADER ELECTION VIA ETCD (Pseudo-code)
══════════════════════════════════════

campaign():
  lease = etcd.create_lease(TTL=10s)
  
  success = etcd.transaction(
    compare: key doesn't exist (version == 0)
    success: PUT key=node_id with lease
    failure: []
        )
        
        if success:
    start_keep_alive_loop()
    return true
  return false

keep_alive():
  while is_leader:
    lease.refresh()
    sleep(3s)  // well before 10s TTL
```

#### Pattern 2: Distributed Lock via Metadata Service

```
DISTRIBUTED LOCK VIA ETCD (Pseudo-code)
═══════════════════════════════════════

acquire(timeout):
  while not timed_out:
    lease = etcd.create_lease(10s)
    
    success = etcd.transaction(
      compare: key doesn't exist
      success: PUT key="locked" with lease
      failure: GET key (see who has it)
    )
    
    if success: return true
    
    // Wait for lock release
    etcd.watch(key).wait_for_delete()
  
  raise Timeout

release():
  lease.revoke()  // automatically deletes key
```

### 9.4 What Happens When Metadata Service Fails

```
┌─────────────────────────────────────────────────────────────────────────┐
│                METADATA SERVICE FAILURE SCENARIOS                       │
│                                                                         │
│   SCENARIO 1: Leader Failure                                            │
│   ─────────────────────────────                                         │
│                                                                         │
│   Impact:                                                               │
│   - Writes blocked for 1-10 seconds (election time)                     │
│   - Reads can continue from followers                                   │
│   - Watches may miss events during transition                           │
│                                                                         │
│   Mitigation:                                                           │
│   - Clients retry with backoff                                          │
│   - Clients cache last known good config                                │
│   - Fast election (sub-second with good config)                         │
│                                                                         │
│   SCENARIO 2: Loss of Quorum                                            │
│   ──────────────────────────                                            │
│                                                                         │
│   Impact:                                                               │
│   - ALL operations blocked (reads and writes)                           │
│   - Service completely unavailable                                      │
│   - All dependent services affected                                     │
│                                                                         │
│   Mitigation:                                                           │
│   - 5-node cluster (survives 2 failures) instead of 3                   │
│   - Cross-AZ deployment                                                 │
│   - Clients use cached config with degraded mode                        │
│                                                                         │
│   SCENARIO 3: Network Partition                                         │
│   ─────────────────────────────                                         │
│                                                                         │
│   Impact:                                                               │
│   - Minority partition: can't read or write                             │
│   - Majority partition: continues operating                             │
│   - Clients in minority partition lose access                           │
│                                                                         │
│   Mitigation:                                                           │
│   - Clients should cache and operate in degraded mode                   │
│   - Alert on partition immediately                                      │
│   - Have runbook for manual partition resolution                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

```
RESILIENT METADATA CLIENT (Pseudo-code)
═══════════════════════════════════════

get(key):
  try:
    value = etcd.get(key)
    cache[key] = value  // update cache on success
            return value
  catch EtcdException:
    if key in cache:
      log("Using cached value")
      return cache[key]
    raise Unavailable

watch(key, callback):
  while true:
    try:
      for event in etcd.watch(key):
        callback(event)
    catch EtcdException:
      log("Watch disconnected, reconnecting...")
      sleep(1s)
```

---

## 9.5 Coordination Services Deep Dive

Understanding the internals of coordination services helps you choose the right one and operate it effectively.

### 9.5.1 Service Comparison

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                    COORDINATION SERVICE COMPARISON                             │
│                                                                                │
│   Feature           │ ZooKeeper    │ etcd         │ Consul       │ Chubby      │
│   ──────────────────┼──────────────┼──────────────┼──────────────┼─────────────│
│   Consensus         │ ZAB          │ Raft         │ Raft         │ Paxos       │
│   Data Model        │ Hierarchical │ Flat KV      │ Flat KV      │ Hierarchical│
│   Language          │ Java         │ Go           │ Go           │ C++         │
│   Watch Model       │ One-shot     │ Streaming    │ Blocking     │ Callback    │
│   Transactions      │ Multi-op     │ Mini-txn     │ Check-set    │ Sequences   │
│   Max Data Size     │ 1MB/znode    │ 1.5MB/key    │ 512KB/key    │ 256KB/file  │
│   Session/Lease     │ Session      │ Lease        │ Session      │ Lock delay  │
│   Typical Use       │ Hadoop, Kafka│ Kubernetes   │ Service mesh │ Google only │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────────────────┐
│              ZooKeeper vs etcd vs Redis Locks — QUICK COMPARISON         │
│                                                                         │
│   ┌─────────────────┬─────────────────┬─────────────────┐               │
│   │   ZooKeeper     │     etcd        │  Redis/Redlock   │               │
│   ├─────────────────┼─────────────────┼─────────────────┤               │
│   │ CP (strong)     │ CP (strong)     │ AP-ish          │               │
│   │ Strong guarantees│ Raft-based    │ Fast, weaker    │               │
│   │ Complex ops     │ K8s native      │ Simple setup    │               │
│   │ Hierarchical    │ Flat KV        │ Key-value       │               │
│   │ Java            │ Go              │ Any             │               │
│   │ Use: Hadoop,    │ Use: K8s,       │ Use: Caching,   │               │
│   │      Kafka      │      Consul     │      Coarse     │               │
│   └─────────────────┴─────────────────┴─────────────────┘               │
│                                                                         │
│   When to pick:                                                          │
│   • Need strong correctness? → ZooKeeper or etcd                         │
│   • Need speed over rigor? → Redis (with fencing token!)                 │
└─────────────────────────────────────────────────────────────────────────┘
```

### 9.5.2 ZooKeeper Internals

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ZOOKEEPER ARCHITECTURE                           │
│                                                                         │
│   ZAB (ZooKeeper Atomic Broadcast) Protocol:                            │
│   ──────────────────────────────────────────                            │
│                                                                         │
│   PHASE 1: LEADER ELECTION                                              │
│   ┌────────────────────────────────────────────────────────────────┐    │
│   │  Nodes exchange votes: (proposed_leader, zxid, epoch)          │    │
│   │  Winner: highest epoch, then highest zxid, then highest id     │    │
│   └────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│   PHASE 2: DISCOVERY                                                    │
│   ┌────────────────────────────────────────────────────────────────┐    │
│   │  Leader collects last zxid from each follower                  │    │
│   │  Establishes new epoch (higher than any seen)                  │    │
│   └────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│   PHASE 3: SYNCHRONIZATION                                              │
│   ┌────────────────────────────────────────────────────────────────┐    │
│   │  Leader syncs followers to same state                          │    │
│   │  Methods: DIFF, TRUNC, SNAP depending on lag                   │    │
│   └────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│   PHASE 4: BROADCAST                                                    │
│   ┌────────────────────────────────────────────────────────────────┐    │
│   │  Normal operation: 2-phase commit for writes                   │    │
│   │  Leader: PROPOSE → followers ACK → Leader: COMMIT              │    │
│   └────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│   DATA MODEL:                                                           │
│   ────────────                                                          │
│   /                                                                     │
│   ├── /app                                                              │
│   │   ├── /app/leader              (ephemeral)                          │
│   │   ├── /app/config                                                   │
│   │   └── /app/workers                                                  │
│   │       ├── /app/workers/worker-001  (ephemeral, sequential)          │
│   │       └── /app/workers/worker-002  (ephemeral, sequential)          │
│   └── /locks                                                            │
│       └── /locks/resource-x        (ephemeral)                          │
│                                                                         │
│   Node Types:                                                           │
│   - Persistent: survives client disconnect                              │
│   - Ephemeral: deleted when session ends                                │
│   - Sequential: ZK appends monotonic counter to name                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

```
ZOOKEEPER PATTERNS (Pseudo-code)
════════════════════════════════

PATTERN 1: Leader Election (Sequential Nodes)
  1. Create sequential ephemeral node: /election/candidate-000001
  2. Get all children, sort by sequence
  3. If I'm lowest → I'm leader
  4. Else watch node just before me (efficient: only 1 watch)
  5. When predecessor deleted → check again

PATTERN 2: Distributed Lock
  1. Create sequential ephemeral node: /locks/lock-000001
  2. If I'm lowest → I hold lock
  3. Else watch predecessor
  4. On timeout: delete my node, raise error

PATTERN 3: Group Membership
  join: create ephemeral node /groups/mygroup/member-id
  leave: node auto-deleted when session ends
  get_members: list children of /groups/mygroup
  watch: ChildrenWatch for membership changes
```

### 9.5.3 etcd Internals

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ETCD ARCHITECTURE                               │
│                                                                         │
│   Built on Raft consensus with MVCC storage.                            │
│                                                                         │
│   KEY FEATURES:                                                         │
│   ──────────────                                                        │
│                                                                         │
│   1. MVCC (Multi-Version Concurrency Control)                           │
│      - Every key has revision history                                   │
│      - Enables watch from any revision                                  │
│      - Compaction removes old revisions                                 │
│                                                                         │
│   2. LEASE SYSTEM                                                       │
│      - TTL-based key expiration                                         │
│      - Multiple keys can attach to one lease                            │
│      - Efficient for ephemeral data                                     │
│                                                                         │
│   3. WATCH                                                              │
│      - Streaming watches (not one-shot)                                 │
│      - Watch from specific revision                                     │
│      - Prefix watches                                                   │
│                                                                         │
│   4. TRANSACTIONS                                                       │
│      - Compare-and-swap style                                           │
│      - If (conditions) Then (ops) Else (ops)                            │
│      - Atomic across multiple keys                                      │
│                                                                         │
│   STORAGE LAYOUT:                                                       │
│   ────────────────                                                      │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  Raft Log (append-only)                                         │   │
│   │  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐                             │   │
│   │  │ 1  │ │ 2  │ │ 3  │ │ 4  │ │ 5  │ ...                         │   │
│   │  └────┘ └────┘ └────┘ └────┘ └────┘                             │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                           │                                             │
│                           ▼                                             │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  BoltDB (MVCC storage)                                          │   │
│   │                                                                 │   │
│   │  Key Index:     key → [(rev1, val1), (rev2, val2), ...]         │   │
│   │  Revision Map:  rev → (key, value, create_rev, mod_rev)         │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

```
ETCD PATTERNS (Pseudo-code)
═══════════════════════════

PATTERN 1: Leader Election
  election = etcd.election(name)
  lease = etcd.lease(15s)
  election.campaign(node_id, lease)  // blocks until leader
  // Lease auto-renewed

PATTERN 2: Lock with Fencing Token
  lock = etcd.lock(name, ttl=30s)
  lock.acquire()
  fencing_token = lock.revision  // monotonically increasing!

PATTERN 3: Reliable Watch
  while true:
    try:
      for event in etcd.watch(prefix, start_revision):
                    callback(event)
        revision = event.mod_revision + 1  // resume point
    catch Disconnect:
      sleep(1s), reconnect

PATTERN 4: Compare-and-Swap
  etcd.transaction(
    compare: value(key) == expected
    success: put(key, new_value)
    failure: get(key)  // return current value
  )

PATTERN 5: Atomic Batch
  etcd.transaction(
    compare: []  // no preconditions
    success: [put(k1,v1), put(k2,v2), ...]
  )
  // All updates get same revision
```

### 9.5.4 Google Chubby (For Reference)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    GOOGLE CHUBBY OVERVIEW                               │
│                                                                         │
│   Chubby is Google's distributed lock service. Not open source,         │
│   but its design influenced ZooKeeper and others.                       │
│                                                                         │
│   KEY INNOVATIONS:                                                      │
│   ─────────────────                                                     │
│                                                                         │
│   1. COARSE-GRAINED LOCKS                                               │
│      - Designed for locks held for hours/days, not milliseconds         │
│      - Small number of clients per lock (< 100s)                        │
│      - Advisory locks (clients must cooperate)                          │
│                                                                         │
│   2. LOCK DELAY                                                         │
│      - When lock holder dies, lock is not immediately available         │
│      - Delay (e.g., 60 seconds) prevents rapid lock churn               │
│      - Allows old lock holder to complete in-flight work                │
│                                                                         │
│   3. SEQUENCER (Fencing Token)                                          │
│      - Lock acquisition returns sequencer                               │
│      - Clients pass sequencer to resources                              │
│      - Resources verify sequencer is valid and current                  │
│                                                                         │
│   4. CACHING                                                            │
│      - Aggressive client-side caching                                   │
│      - Chubby sends invalidations on changes                            │
│      - Reduces read load on Chubby masters                              │
│                                                                         │
│   5. CELL DESIGN                                                        │
│      - Each Chubby cell: 5 replicas using Paxos                         │
│      - One cell per datacenter                                          │
│      - Cross-datacenter uses proxy                                      │
│                                                                         │
│   DESIGN CHOICES (Trade-offs):                                          │
│   ─────────────────────────────                                         │
│                                                                         │
│   Why files/directories (not pure KV)?                                  │
│   → Familiar API, natural hierarchy, ACLs                               │
│                                                                         │
│   Why coarse-grained locks?                                             │
│   → Simple to reason about, fewer lock operations                       │
│                                                                         │
│   Why lock delay?                                                       │
│   → Prevents thundering herd, gives holder time to finish               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 9.5.5 Choosing a Coordination Service

| Use Case | Recommendation | Why |
|----------|----------------|-----|
| **Kubernetes deployments** | etcd | Native integration, well-tested |
| **Hadoop/Kafka ecosystem** | ZooKeeper | Mature, ecosystem integration |
| **Service mesh/discovery** | Consul | Built-in service discovery, health checks |
| **Simple leader election** | etcd or Consul | Simpler API than ZooKeeper |
| **Complex hierarchical data** | ZooKeeper | Native tree structure |
| **Need for watches** | etcd | Streaming watches, no one-shot |
| **Multi-datacenter** | Consul | Built-in WAN federation |

### 9.6 Multi-Region Coordination Patterns

Multi-region coordination is one of the hardest problems in distributed systems. Cross-region latency (50-200ms) makes traditional coordination approaches impractical.

#### 9.6.1 The Multi-Region Challenge

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    MULTI-REGION LATENCY REALITY                         │
│                                                                         │
│   Intra-region RTT:  0.5 - 2ms                                          │
│   Cross-region RTT:  50 - 200ms (US-East ↔ EU, etc.)                    │
│   Cross-continent:   150 - 300ms (US ↔ Asia)                            │
│                                                                         │
│   IMPACT ON COORDINATION:                                               │
│   ───────────────────────                                               │
│                                                                         │
│   Single global leader (Raft/Paxos):                                    │
│   - Write latency = cross-region RTT × 2 (propose + commit)             │
│   - 5 regions → some writes take 300-600ms                              │
│                                                                         │
│   Distributed lock across regions:                                      │
│   - Acquire: 50-200ms (best case)                                       │
│   - Lease renewal must account for cross-region latency                 │
│                                                                         │
│   Leader election across regions:                                       │
│   - Election timeout must be >> cross-region RTT                        │
│   - Longer timeout = longer unavailability during failover              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 9.6.2 Pattern 1: Regional Leaders with Global Coordination

```
REGIONAL LEADER PATTERN (Pseudo-code)
═════════════════════════════════════

Used by: Spanner, CockroachDB

local_read(key):   → regional leader serves (fast!)
local_write(key):  → regional consensus only (fast!)

cross_region_write(key):
  if key not owned by this region:
    forward to owning region

global_transaction(operations):
  // Phase 1: Prepare
  for each region in operations:
    prepare_results[region] = region.prepare(ops)
  
  if all prepared:
    // Phase 2: Commit with synchronized timestamp
    commit_ts = get_global_timestamp()
    for each region: region.commit(commit_ts)
    commit_wait(commit_ts)  // TrueTime wait
    return committed
  else:
    for each region: region.abort()
    return aborted
```

#### 9.6.3 Pattern 2: Witness Replicas

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    WITNESS REPLICA PATTERN                              │
│                                                                         │
│   Problem: 3 replicas across 3 regions = cross-region RTT for quorum    │
│   Solution: Use lightweight "witness" replicas to reduce latency        │
│                                                                         │
│   Traditional 3-region setup:                                           │
│   ──────────────────────────                                            │
│                                                                         │
│      US-East          EU-West          US-West                          │
│      ┌─────┐          ┌─────┐          ┌─────┐                          │
│      │Full │          │Full │          │Full │                          │
│      │ Rep │◀────────▶│ Rep │◀────────▶│ Rep │                          │
│      └─────┘   100ms  └─────┘   150ms  └─────┘                          │
│                                                                         │
│   Quorum needs 2/3 → minimum 100ms write latency                        │
│                                                                         │
│   With witness:                                                         │
│   ──────────────                                                        │
│                                                                         │
│      US-East                           US-West                          │
│      ┌─────┐                          ┌─────┐                           │
│      │Full │◀─────────────────────────│Full │                           │
│      │ Rep │            40ms          │ Rep │                           │
│      └─────┘                          └─────┘                           │
│         │                                │                              │
│         │              ┌───────┐         │                              │
│         └─────────────▶│Witness│◀────────┘                              │
│                        │(logs  │                                        │
│                        │ only) │                                        │
│                        └───────┘                                        │
│                        US-Central                                       │
│                                                                         │
│   Witness only stores Raft log, not full data.                          │
│   Can vote but not serve reads.                                         │
│   Placed to minimize quorum latency.                                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

```
WITNESS REPLICA (Concept)
═════════════════════════

Purpose: Lightweight replica that votes but doesn't store data.

What it stores:
  ✓ Raft log (for voting)
  ✓ Current term, voted_for
  ✗ State machine (no data)

What it does:
  ✓ handle_append_entries → acknowledge
  ✓ handle_vote_request → vote
  ✗ handle_read → CANNOT serve reads

Benefit: Reduces quorum latency without storing full data.
```

#### 9.6.4 Pattern 3: Hierarchical Coordination

```
HIERARCHICAL COORDINATION (Pseudo-code)
═══════════════════════════════════════

Two levels: Regional (fast) vs Global (slow)

local_lock(resource):     → regional coordinator only (fast)
global_lock(resource):    → regional intent lock, then global lock

regional_leader_election: → within-region consensus (fast)
global_leader_election:   → cross-region consensus (slow, avoid if possible)
```

#### 9.6.5 Multi-Region Consensus Options

| Approach | Write Latency | Consistency | Use Case |
|----------|---------------|-------------|----------|
| **Single global leader** | High (cross-region) | Strong | Config store, metadata |
| **Regional leaders (CRDTs)** | Low (local) | Eventual | Counters, sets |
| **Regional leaders (2PC)** | Medium | Strong for cross-region txn | Databases |
| **Spanner (TrueTime)** | Medium + commit-wait | External | Financial, critical |
| **Leaderless (EPaxos)** | Low (nearest replica) | Strong | Geo-distributed KV |

#### 9.6.6 Handling Region Failures

```
MULTI-REGION FAILOVER (Pseudo-code)
═══════════════════════════════════

handle_region_failure(failed_region):
  1. Confirm failure (require 2+ signals: heartbeat, health, network)
  2. Remove failed nodes from cluster membership
  3. Check quorum (if lost → manual intervention)
  4. Force election if leader was in failed region
  5. Update routing to exclude failed region
  6. Schedule data recovery

is_region_failure_confirmed():
  checks = [heartbeats, health_endpoints, network_reachability]
  failures = count(check for check in checks if failed)
  return failures >= 2  // avoid false positives
```

### 9.7 Security, Trust Boundaries, and Compliance for Coordination

Coordination services hold critical metadata: cluster membership, service discovery, config, lock ownership. Staff engineers must treat security as part of reliability—a compromised coordination layer can cause data corruption or service impersonation.

**Trust Boundaries:**

| Boundary | Risk | Mitigation |
|----------|------|------------|
| **Who can acquire locks?** | Malicious client claims lock, blocks legitimate work | Authentication (mTLS, service accounts). Authorization: lock path namespaced by service/team. Audit logs for lock acquisitions. |
| **Who can read config?** | Config may contain secrets (DB URLs, API keys) | Encrypt config at rest. Limit read access to services that need it. Never put raw secrets in coordination store—use secret manager with reference only. |
| **Who can participate in leader election?** | Rogue node forces elections, causes instability | Only authenticated, authorized nodes join cluster. Network-level isolation (VPC, firewall) for coordination cluster. |
| **Cross-team shared cluster** | Team A's misconfiguration affects Team B | Per-team namespaces (ZK paths, etcd prefixes). Quotas per namespace. Isolation tier: critical vs. non-critical clusters. |

**Data Sensitivity in Coordination:**

- **Service discovery:** Instance IPs, ports—low sensitivity but enables reconnaissance
- **Config:** May reference secrets—treat as sensitive
- **Lock metadata:** Client IDs, TTLs—useful for debugging; avoid PII in lock keys
- **Compliance:** If coordination store holds PII or PHI, retention and encryption must meet regulatory requirements. Most coordination stores are not designed for regulated data—store references only.

**Real Example:** A payments platform used ZooKeeper for feature flags. A flag value was set to a database connection string (mistakenly). The ZK ACLs allowed read access to all services. A compromised low-privilege service read the flag and exfiltrated credentials. Design change: Config values in coordination store are now opaque references; actual secrets live in a secret manager with strict access control.

**Trade-off:** Strong authentication and per-namespace authorization add latency and operational complexity. For critical coordination (payments, identity), the trade-off is mandatory. For internal dev tooling, relaxed boundaries may be acceptable with explicit risk acknowledgment.

**L6 Implication:** When proposing coordination infrastructure, articulate the trust model. "Who can acquire locks on payment-related resources? Who can read cluster membership?" Security is not an afterthought—it affects blast radius when things go wrong.

---

<a name="anti-patterns"></a>
## 10. Anti-Patterns: How Good Intentions Go Wrong

### Anti-Pattern 1: The God Lock

```
BAD:  with god_lock:         // One lock for everything
        do_anything()

GOOD: with lock(f"user:{user_id}"):   // Lock per resource
        update_user()
      with lock(f"order:{order_id}"): // Different resource = different lock
        update_order()
```

**Why it's bad:** Serializes all operations, SPOF, any slow op blocks everything

### Anti-Pattern 2: The Chatty Coordinator

```
BAD:  handle_request():
        am_i_leader()        // network
        acquire_lock()       // network
        get_config()         // network
        get_peers()          // network
        do_work()
        release_lock()       // network
        // 5 coordination calls for 1 operation!

GOOD: handle_request():
        if cache_stale: refresh_cached_state()  // rare
        do_work(cached_config)  // no coordination on hot path
```

**Why it's bad:** 5× latency, coordination service = bottleneck

### Anti-Pattern 3: Unbounded Lock Hold Time

```
BAD:  with lock(job_id):
        download_10gb_file()    // minutes
        ml_inference()          // hours
        save_result()           // Lock held entire time!

GOOD: with lock(job_id, ttl=5s):
        claim_job()             // fast
      
      download_10gb_file()      // NO LOCK
      ml_inference()            // NO LOCK
      
      with lock(job_id, ttl=5s):
        save_result()           // fast
```

**Why it's bad:** TTL expires, others starve, throughput tanks

### Anti-Pattern 4: Ignoring Lock Timeout

```
BAD:  lock.acquire(ttl=10s)
      do_slow_work()           // takes 30s, lock expired at 10s!
      write_critical_data()    // DANGEROUS: lock expired!
      lock.release()           // releasing lock we don't own!

GOOD: token = lock.acquire(ttl=10s)
      do_slow_work()
      if not lock.is_still_valid():
        raise LockExpired()
      write_critical_data(fencing_token=token)  // storage rejects stale token
            lock.release()
```

### Anti-Pattern 5: Coordination for Read-Only Operations

```
BAD:  get_user():
        with lock(user_id):        // WHY? Reads don't need locks!
          return db.query(...)

GOOD: get_user():
        return db.query(...)       // No lock for reads
      
      update_user():
        with lock(user_id):        // Lock only for writes
          db.execute(...)
```

**Why it's bad:** Reads don't need mutual exclusion → massive perf penalty for nothing

### Anti-Pattern 6: Human Failure Modes in Coordination

Coordination systems amplify human errors. Staff engineers must anticipate and prevent common mistakes that lead to production incidents.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    HUMAN FAILURE MODES IN COORDINATION                  │
│                                                                         │
│   ┌──────────────────────────────┬──────────────────────────────────┐  │
│   │ Error                        │ Impact                           │  │
│   ├──────────────────────────────┼──────────────────────────────────┤  │
│   │ Forgetting fencing tokens    │ Most common, causes silent data  │  │
│   │ in new service               │ corruption                        │  │
│   ├──────────────────────────────┼──────────────────────────────────┤  │
│   │ Setting TTL too short       │ Locks expire during normal       │  │
│   │                              │ operation, causing duplicate     │  │
│   │                              │ processing                       │  │
│   ├──────────────────────────────┼──────────────────────────────────┤  │
│   │ Setting TTL too long        │ Dead lock holders block          │  │
│   │                              │ resources for minutes            │  │
│   ├──────────────────────────────┼──────────────────────────────────┤  │
│   │ Manual lock release during  │ Can violate safety guarantees,   │  │
│   │ incident                     │ cause split-brain                │  │
│   ├──────────────────────────────┼──────────────────────────────────┤  │
│   │ Not testing coordination    │ "It works when ZK is healthy"    │  │
│   │ failure in staging           │ is not a test                    │  │
│   └──────────────────────────────┴──────────────────────────────────┘  │
│                                                                         │
│   Prevention Strategies:                                               │
│   - Lint rules that require fencing tokens in lock-acquiring code     │
│   - TTL templates per use case (prevent arbitrary TTL values)          │
│   - Lock release requires 2-person approval during incidents           │
│   - Chaos engineering: regularly inject ZK failures in staging        │
│                                                                         │
│   On-Call Reality:                                                     │
│   "Coordination system issues are the hardest to debug at 3 AM         │
│   because symptoms manifest in dependent services, not in the          │
│   coordination system itself."                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Common Human Errors:**

1. **Forgetting fencing tokens in new service**
   - Most common error
   - Causes silent data corruption (two processes think they hold the lock)
   - Detection: Only discovered when duplicate operations occur

2. **Setting TTL too short**
   - Locks expire during normal operation
   - Causes duplicate processing
   - Example: 30-second TTL for a 45-second operation

3. **Setting TTL too long**
   - Dead lock holders block resources for minutes
   - Prevents recovery from process crashes
   - Example: 1-hour TTL for a 10-second operation

4. **Manual lock release during incident**
   - Can violate safety guarantees
   - Causes split-brain scenarios
   - Example: Releasing a lock while the original holder is still active

5. **Not testing coordination failure in staging**
   - "It works when ZK is healthy" is not a test
   - Production failures are the first time the system sees coordination outages
   - Results in cascading failures that could have been prevented

**Prevention Strategies:**

- **Lint rules that require fencing tokens** in lock-acquiring code
- **TTL templates per use case** (prevent arbitrary TTL values)
- **Lock release requires 2-person approval** during incidents
- **Chaos engineering**: Regularly inject ZK failures in staging

**On-Call Reality:**

"Coordination system issues are the hardest to debug at 3 AM because symptoms manifest in dependent services, not in the coordination system itself." Engineers spend hours tracing symptoms back to a coordination failure that occurred minutes earlier.

---

### Ownership Model for Coordination Infrastructure

| Component | Owner | Responsibility | Escalation Path |
|---|---|---|---|
| **ZooKeeper/etcd cluster** | Platform/Infrastructure team | Cluster health, upgrades, capacity planning | Platform on-call → Platform tech lead |
| **Leader election service** | Platform team builds, product team configures | Platform: framework availability. Product: election parameters (timeout, TTL) | Product on-call → Platform on-call if framework issue |
| **Distributed lock usage** | Product/service team | Lock granularity, TTL, fencing token enforcement | Product on-call → Platform if lock service degraded |
| **Lock contention monitoring** | Shared (platform provides tooling, product configures alerts) | Platform: metrics pipeline. Product: alerting thresholds per use case | Product on-call for contention spikes |
| **Coordination failure runbooks** | Platform team writes template, product team customizes | Platform: generic "ZK down" runbook. Product: service-specific degradation steps | Defined in runbook |

**The Ownership Gap That Causes Outages:**

"Platform team deploys a ZooKeeper upgrade during low-traffic window. Upgrade causes brief session reconnection storm. Product Team A's service has a 5-second lock TTL — all locks expire during the storm. Product Team A doesn't know about the upgrade and pages Platform. Platform says 'ZK is healthy now.' Meanwhile, Team A's job scheduler ran duplicate jobs for 10 seconds during the lock gap."

**Prevention:** Coordination service upgrades must be announced to ALL dependent teams 48h in advance with expected impact window. Dependent teams must verify their TTLs and fencing tokens can survive a 30-second session reconnection.

**Cross-Team SLAs:**
- Platform guarantees: ZK/etcd availability > 99.95%, session reconnection < 30s during upgrades
- Product teams guarantee: All lock-dependent operations use fencing tokens, TTLs set > 2× expected session reconnection time

<a name="when-not-to-use-locks"></a>
## 11. When NOT to Use Locks

### Rule 1: If You Can Use Idempotent Operations Instead

```
LOCK:   with lock("counter"):
    value = db.get("counter")
    db.set("counter", value + 1)

BETTER: db.increment("counter", 1)  // Atomic, no lock needed
```

### Rule 2: If You Can Partition the Work

```
LOCK:   with lock("job-queue"):
    job = queue.pop()

BETTER: my_partition = hash(worker_id) % num_partitions
        job = queue.pop(partition=my_partition)  // Each worker owns partition
```

### Rule 3: If Eventual Consistency Is Acceptable

```
LOCK:   with lock("page-view-counter"):
    views = db.get("page:123:views")
    db.set("page:123:views", views + 1)

BETTER: local_buffer[page_id] += 1  // fast, in-memory
        
        // Background job every second:
        for page_id, count in local_buffer:
          db.increment(page_id, count)
local_buffer.clear()
```

### Rule 4: If CRDTs Can Model Your Data

```
LOCK:   with lock(cart_id):
          cart = db.get(cart_id)
    cart.add(item)
          db.set(cart_id, cart)

BETTER: Use Add-Wins Set CRDT (no lock needed):
        
        add(item):    adds[item].add((timestamp, replica_id))
        remove(item): removes[item].add((timestamp, replica_id))
        
        get_items(): return items where latest_add > latest_remove
        merge(other): union all adds and removes (conflict-free!)
```

### Rule 5: If You Can Use Optimistic Concurrency Control

```
PESSIMISTIC (Lock):
  with lock(account_id):
    account = db.get(account_id)
    account.balance -= amount
    db.set(account_id, account)

OPTIMISTIC (CAS - no lock):
  for attempt in retries:
    account, version = db.get_with_version(account_id)
    account.balance -= amount
    
    if db.set_if_version(account_id, account, expected=version):
      return success
    
    // Version changed, retry
  raise TooManyConflicts
```

### Decision Matrix: Lock vs. Alternatives

| Situation | Use Lock? | Better Alternative |
|-----------|-----------|-------------------|
| Increment counter | ❌ No | Atomic increment |
| Update user profile | ⚠️ Maybe | Optimistic concurrency |
| Transfer money between accounts | ✅ Yes | Or Saga pattern |
| Process exactly one job | ✅ Yes | Or claim with CAS |
| Update shopping cart | ❌ No | CRDT |
| Track page views | ❌ No | Eventual consistency |
| Leader election | ✅ Yes | Built-in consensus |
| Distributed cache invalidation | ❌ No | TTL + eventual |

```
┌─────────────────────────────────────────────────────────────────────────┐
│              WHEN NOT TO USE A LOCK — DECISION VISUAL                    │
│                                                                         │
│   Need mutual exclusion?                                                 │
│              │                                                           │
│              ▼                                                           │
│   ┌──────────────────────────┐                                          │
│   │ Can you PARTITION        │──YES──► Use partition (no lock!) ✓        │
│   │ the problem?             │         Each worker owns its slice        │
│   └──────────────────────────┘                                          │
│              │ NO                                                        │
│              ▼                                                           │
│   ┌──────────────────────────┐                                          │
│   │ Can you make it          │──YES──► Idempotent retry ✓                │
│   │ IDEMPOTENT?              │         Same key = same result            │
│   └──────────────────────────┘                                          │
│              │ NO                                                        │
│              ▼                                                           │
│   ┌──────────────────────────┐                                          │
│   │ Can you use CRDTs?       │──YES──► Conflict-free data ✓              │
│   │ (merge without lock)     │         Add-wins, LWW, etc.               │
│   └──────────────────────────┘                                          │
│              │ NO                                                        │
│              ▼                                                           │
│   ┌──────────────────────────┐                                          │
│   │ Still need exactly-one?   │──YES──► OK, use lock WITH FENCING ✓       │
│   │ (money, critical job)     │         Never skip fencing tokens!         │
│   └──────────────────────────┘                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

<a name="graceful-degradation"></a>
## 12. Graceful Degradation: What Happens When Coordination Fails

### 12.1 The Degradation Spectrum

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     DEGRADATION STRATEGIES                              │
│                                                                         │
│   Most Restrictive                              Least Restrictive       │
│   ──────────────────────────────────────────────────────────────▶       │
│                                                                         │
│   ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐           │
│   │    FAIL    │ │   DEGRADE  │ │   CACHE    │ │    FAIL    │           │
│   │   CLOSED   │ │    MODE    │ │  FALLBACK  │ │    OPEN    │           │
│   └────────────┘ └────────────┘ └────────────┘ └────────────┘           │
│                                                                         │
│   Reject all     Reduce         Use cached      Allow all               │
│   requests       functionality   values          requests               │
│                                                                         │
│   Safety: ⭐⭐⭐⭐⭐  ⭐⭐⭐⭐         ⭐⭐⭐           ⭐                  │
│   Availability: ⭐   ⭐⭐⭐          ⭐⭐⭐⭐         ⭐⭐⭐⭐⭐            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 12.2 Building Resilient Coordination Clients

```
RESILIENT COORDINATION CLIENT (Pseudo-code)
═══════════════════════════════════════════

Principles:
  1. Always have a fallback
  2. Prefer availability over strict consistency in degraded mode
  3. Make degradation observable (metrics, logs, alerts)
  4. Auto-recover when coordination becomes available

get_config(key):
  try:
    value = coordination.get(key)
    cache[key] = value
    exit_degraded_mode()
    return value
  catch Unavailable:
    enter_degraded_mode()
    if key in cache: return cache[key]      // Fallback 1
    if default: return default               // Fallback 2
    raise ConfigUnavailable                  // Fail if critical

acquire_lock(resource):
  try:
    return coordination.lock(resource)
  catch Unavailable:
    enter_degraded_mode()
    switch(degraded_strategy):
      "local":   return LocalLock(resource)  // Process-level only
      "fail":    raise LockUnavailable       // Fail closed
      "proceed": return NoOpLock             // Fail open (dangerous!)
```

### 12.3 Circuit Breaker for Coordination

```
CIRCUIT BREAKER (Pseudo-code)
═════════════════════════════

States: CLOSED → OPEN → HALF_OPEN → CLOSED

Constants:
  FAILURE_THRESHOLD = 5    // failures before opening
  RESET_TIMEOUT = 30s      // wait before trying again
  SUCCESS_THRESHOLD = 3    // successes to close

call(operation):
  if state == OPEN:
    if should_attempt_reset(): state = HALF_OPEN
    else: raise CircuitOpen  // fast-fail
  
  try:
    result = operation()
    on_success()
    return result
  catch:
    on_failure()
    raise

on_success():
  if state == HALF_OPEN and success_count >= 3:
    state = CLOSED  // recovered!

on_failure():
  failure_count++
  if failure_count >= 5:
    state = OPEN
```

### 12.4 Degradation Patterns by Service Type

```
┌─────────────────────────────────────────────────────────────────────────┐
│              DEGRADATION PATTERNS BY SERVICE TYPE                       │
│                                                                         │
│   SERVICE TYPE          COORDINATION FAILURE → DEGRADATION STRATEGY     │
│   ────────────────────────────────────────────────────────────────      │
│                                                                         │
│   Job Scheduler         Leader dies → Followers buffer jobs locally     │
│                         Resume when new leader elected                  │
│                         Risk: Duplicate execution if not idempotent     │
│                                                                         │
│   Rate Limiter          Redis down → Local rate limiting only           │
│                         Effective limit = global_limit / server_count   │
│                         Risk: Over-limit by factor of server_count      │
│                                                                         │
│   Feature Flags         etcd down → Use cached flags                    │
│                         Cache TTL = 5 minutes (configurable)            │
│                         Risk: Delayed flag updates during outage        │
│                                                                         │
│   Distributed Lock      Lock service down → ???                         │
│                         Option A: Fail closed (reject operations)       │
│                         Option B: Proceed (risk duplicates)             │
│                         Decision depends on cost of duplicates          │
│                                                                         │
│   Configuration         Metadata unavailable → Use last known config    │
│                         Alert if config age > threshold                 │
│                         Risk: Operating with stale config               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 12.5 Testing Degraded Mode

```
DEGRADED MODE TESTS (What to Test)
══════════════════════════════════

test_coordination_unavailable:
  with mock_failure():
    response = service.handle_request()
    assert response.status != 500
    assert response.headers["X-Degraded-Mode"] == "true"

test_cache_fallback:
  service.get_config("flag_x")              // prime cache
  with mock_failure():
    value = service.get_config("flag_x")    // should use cache
    assert value is not None

test_degraded_mode_metrics:
  with mock_failure(): service.handle_request()
  assert metrics["degraded_mode.entered"] == 1
  
  // Restore
  service.handle_request()
  assert metrics["degraded_mode.duration"] > 0

test_circuit_breaker_opens:
  with mock_failure():
    for 10 times: service.coordinate()  // trigger failures
  assert circuit_breaker.state == "OPEN"
  assert_no_network_calls { service.coordinate() }  // fast-fail
```

---

<a name="interview-explanations"></a>
## 13. Interview Explanations

### 13.1 "Explain distributed locks and when you'd use them"

**Strong Answer:**

> "A distributed lock provides mutual exclusion across multiple machines—ensuring only one process can access a shared resource at a time.
>
> **When to use them:**
> - Exactly-once job execution (like processing a payment)
> - Preventing concurrent modifications to the same entity
> - Coordinating access to external resources with no built-in concurrency control
>
> **Key implementation concerns:**
> 1. **Lock expiration:** Use TTLs to prevent deadlocks from crashed holders
> 2. **Unique identifiers:** Prevent accidentally releasing someone else's lock
> 3. **Fencing tokens:** Monotonically increasing tokens to detect stale lock holders
>
> **When NOT to use them:**
> - If atomic operations exist (use INCR instead of lock → read → write → unlock)
> - If work can be partitioned (each worker handles its own subset)
> - If eventual consistency is acceptable (use CRDTs)
>
> **The fundamental problem** is that distributed locks aren't foolproof—a process can pause after acquiring the lock (GC, network delay), the lock expires, another process acquires it, and now you have two holders. Fencing tokens protect against this by having downstream resources reject operations from stale holders."

### 13.2 "How does leader election work in distributed systems?"

**Strong Answer:**

> "Leader election ensures exactly one node acts as the authoritative coordinator at any time, with automatic failover when the leader fails.
>
> **Two main approaches:**
>
> 1. **Lease-based:** Leader holds a time-limited lease. Must renew before expiry. If the leader is partitioned from the lease store, the lease expires and someone else can take over.
>
> 2. **Quorum-based:** Leader must maintain support from a majority of nodes through heartbeats. If it can't reach quorum, it steps down.
>
> **The critical safety property** is that at any time, at most one node believes it's the leader. This is achieved through:
> - Lease TTLs (old leader's lease expires before new leader can acquire)
> - Epoch/term numbers (operations include term number; stale terms are rejected)
> - Quorum overlap (any two majorities share at least one node)
>
> **What happens during leader failure:**
> 1. Leader stops sending heartbeats (or lease expires)
> 2. Followers detect missing heartbeats after timeout
> 3. Election triggers—nodes vote for new leader
> 4. Winner starts acting as leader
>
> **This creates unavailability during election (typically 1-10 seconds)**. Systems must be designed to buffer operations during this window or fail gracefully."

### 13.3 "What is split-brain and how do you prevent it?"

**Strong Answer:**

> "Split-brain occurs when a network partition causes two groups of nodes to independently elect their own leaders, resulting in two nodes both believing they're the authoritative leader.
>
> **Why it's dangerous:** Both leaders accept writes, data diverges, and when the partition heals, you have conflicting states that may be impossible to reconcile.
>
> **Prevention mechanisms:**
>
> 1. **Quorum requirement:** Leader must maintain support from majority of nodes. In a 5-node cluster, each partition needs 3 nodes to elect a leader. Since there's only 5 total, only one partition can have 3.
>
> 2. **Fencing:** When a new leader is elected, it 'fences' the old leader—prevents it from making changes. This can be done through:
>    - Revoking storage access (STONITH - 'Shoot The Other Node In The Head')
>    - Epoch numbers where resources reject old epochs
>
> 3. **Leader step-down:** Leaders that lose quorum must stop accepting writes immediately, even if they don't know a new leader exists.
>
> **The key insight** is that it's safe for there to be NO leader temporarily, but never safe to have TWO leaders. Systems prefer unavailability over inconsistency during partitions."

### 13.4 "How would you design a distributed job scheduler?"

**Strong Answer:**

> "I'd design it with these components:
>
> **1. Job Storage:** A database holding jobs with status (pending, running, completed, failed), scheduled time, and worker assignment. Partitioned by job_id for scale.
>
> **2. Leader/Coordinator:** Single leader (elected via etcd/ZooKeeper lease) that:
> - Scans for ready jobs
> - Assigns jobs to workers
> - Monitors job progress
> - Reclaims jobs from dead workers
>
> **3. Workers:** Register with leader, receive assignments, process jobs.
>
> **Key mechanisms for exactly-once execution:**
>
> 1. **Claim with lock:** Worker acquires distributed lock before processing. Prevents two workers from processing the same job.
>
> 2. **Idempotency keys:** Each job execution has unique ID. If job already completed with that ID, skip it.
>
> 3. **Fencing tokens:** Include token when writing results. Database rejects writes with stale tokens.
>
> **Handling failures:**
>
> - **Worker dies:** Job stays 'running' too long. Reclaimer process detects this, moves job back to 'pending'.
> 
> - **Leader dies:** Workers buffer jobs locally. New leader elected in seconds.
>
> - **Network partition:** Workers can't reach leader. They pause (if strict) or continue processing local queue (if available).
>
> **Trade-off:** Strictly exactly-once adds latency (lock acquisition). At-least-once is simpler and fine if jobs are idempotent."

### 13.5 "When would you NOT use coordination?"

**Strong Answer:**

> "I'd avoid coordination whenever possible because it adds latency, creates bottlenecks, and introduces failure modes. Specifically:
>
> **1. When atomic operations exist:**
> - Don't lock to increment counter—use atomic INCREMENT
> - Don't lock for append-only operations—just append
>
> **2. When work is naturally partitioned:**
> - Each worker handles specific shard—no contention
> - Message queue partitions assigned to consumers—no shared queue lock
>
> **3. When eventual consistency is acceptable:**
> - Analytics counters—approximate is fine
> - Page view tracking—don't need real-time accuracy
> - Session storage—rarely contested
>
> **4. When CRDTs can model the data:**
> - Shopping carts (Add-Wins Set)
> - Counters (G-Counter, PN-Counter)
> - Sets with concurrent adds/removes (OR-Set)
>
> **5. When optimistic concurrency works:**
> - Low-contention updates—version checks are cheaper than locks
> - Read-heavy workloads—no need to lock reads
>
> **The decision framework:**
> 1. What happens if two processes do this simultaneously?
> 2. Can we make the operation commutative?
> 3. Can we detect and retry conflicts?
> 4. Is 'last write wins' acceptable?
>
> If any of these work, avoid distributed locks."

---

<a name="brainstorming-questions"></a>
## 14. Brainstorming Questions

### Architecture Design Questions

1. **You're building a payment processing system. Each payment must be processed exactly once. How do you ensure this without making the lock service a single point of failure?**

2. **Your distributed cache invalidation is causing thundering herd problems—when a popular key expires, hundreds of requests simultaneously try to rebuild it. How do you coordinate this?**

3. **You have 1000 workers processing jobs from a queue. Using a single lock on the queue would be a bottleneck. How do you scale this?**

4. **Your leader election is using a 10-second lease TTL. During a 5-second network blip, the leader loses its lease and a new leader is elected. Now both think they're leader. How do you prevent data corruption?**

5. **You're designing a distributed rate limiter for 100 million users. Coordinating every request is too expensive. What's your approach?**

### Trade-off Analysis Questions

6. **Compare lease-based vs. quorum-based leader election. When would you prefer each?**

7. **Your coordination service (etcd) is down. You have three options: fail all requests, proceed without coordination, or use cached state. Walk through the trade-offs for a job scheduler.**

8. **You're seeing frequent election storms—leaders getting elected and deposed rapidly. What could cause this and how would you diagnose/fix it?**

9. **Your distributed lock implementation uses Redis. Someone suggests using a "safer" Redlock algorithm with 5 Redis instances. What are the trade-offs?**

10. **You have the choice between using ZooKeeper (strong consistency, lower throughput) vs. Redis (higher throughput, weaker guarantees) for your distributed locks. How do you decide?**

### Debugging and Operations Questions

11. **Your job scheduler is occasionally processing jobs twice. The lock implementation looks correct. What could be happening?**

12. **After a network partition healed, you discovered that some configuration changes were lost. Your metadata service uses Raft for consensus. How is this possible?**

13. **Workers report that lock acquisition is taking 10+ seconds, up from the usual milliseconds. Debugging shows the lock service is healthy. What's happening?**

14. **Your 5-node consensus cluster lost quorum when 2 nodes died. You need to restore service immediately but can't recover the dead nodes. What are your options?**

15. **You're seeing "stale fencing token" errors in production, but your lock service shows only one active holder. How do you investigate this?**

### System Evolution Questions

16. **Your service currently uses leader election for coordination. Traffic has grown 100x and the leader is a bottleneck. How do you evolve the architecture?**

17. **You started with Redis for distributed locks. Now you need stronger consistency guarantees. What's your migration strategy?**

18. **Your multi-region deployment needs a global leader. Cross-region latency makes lease renewal slow and unreliable. How do you adapt your design?**

19. **Your coordination system is causing cascading failures—when it goes down, all services fail. How do you add resilience?**

20. **You're moving from a monolith to microservices. The monolith used database locks for coordination. How do you handle coordination in the distributed version?**

---

<a name="homework"></a>
## 15. Homework: Remove Coordination and Re-Architect

### The Challenge

You've inherited a system with excessive coordination. Your mission: **remove or reduce coordination while maintaining correctness.**

### The Existing System

```python
class OverlyCoordinatedSystem:
    """
    A system that uses distributed locks for EVERYTHING.
    Your job: identify what can be removed or optimized.
    """
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    def increment_page_views(self, page_id):
        """Lock on page to increment view counter."""
        with DistributedLock(self.redis, f"page:{page_id}"):
            views = self.redis.get(f"page:{page_id}:views") or 0
            self.redis.set(f"page:{page_id}:views", int(views) + 1)
    
    def add_item_to_cart(self, user_id, item_id, quantity):
        """Lock on cart to add item."""
        with DistributedLock(self.redis, f"cart:{user_id}"):
            cart = json.loads(self.redis.get(f"cart:{user_id}") or "{}")
            cart[item_id] = cart.get(item_id, 0) + quantity
            self.redis.set(f"cart:{user_id}", json.dumps(cart))
    
    def get_user_profile(self, user_id):
        """Lock on user to read profile (!)."""
        with DistributedLock(self.redis, f"user:{user_id}"):
            return db.query("SELECT * FROM users WHERE id = ?", user_id)
    
    def update_user_profile(self, user_id, updates):
        """Lock on user to update profile."""
        with DistributedLock(self.redis, f"user:{user_id}"):
            db.execute(
                "UPDATE users SET name=?, email=? WHERE id = ?",
                [updates['name'], updates['email'], user_id]
            )
    
    def process_order(self, order_id):
        """Global lock to process any order (!!)."""
        with DistributedLock(self.redis, "order-processing"):
            order = db.query("SELECT * FROM orders WHERE id = ?", order_id)
            self.charge_payment(order)
            self.update_inventory(order)
            self.send_confirmation(order)
            db.execute("UPDATE orders SET status='completed' WHERE id = ?", order_id)
    
    def get_feature_flag(self, flag_name):
        """Lock to read feature flag (!!)."""
        with DistributedLock(self.redis, f"flag:{flag_name}"):
            return self.redis.get(f"feature:{flag_name}") == "true"
    
    def submit_job(self, job_data):
        """Global lock on job queue (!!!)."""
        with DistributedLock(self.redis, "job-queue"):
            job_id = str(uuid.uuid4())
            self.redis.lpush("jobs", json.dumps({
                "id": job_id,
                **job_data
            }))
            return job_id
    
    def claim_job(self):
        """Global lock on job queue to claim job."""
        with DistributedLock(self.redis, "job-queue"):
            job_data = self.redis.rpop("jobs")
            if job_data:
                job = json.loads(job_data)
                return job
            return None
```

### Part 1: Identify the Problems (Analysis)

For each method, answer:
1. Is coordination necessary at all?
2. If yes, is this the right level of granularity?
3. What's the performance impact?
4. What's a better alternative?

**Fill in this table:**

| Method | Necessary? | Problem | Better Alternative |
|--------|------------|---------|-------------------|
| increment_page_views | | | |
| add_item_to_cart | | | |
| get_user_profile | | | |
| update_user_profile | | | |
| process_order | | | |
| get_feature_flag | | | |
| submit_job | | | |
| claim_job | | | |

### Part 2: Re-Architecture (Implementation)

Rewrite the system with minimal coordination. For each method:
- Remove lock if not needed
- Use finer-grained lock if needed
- Use alternative pattern (atomic ops, CRDTs, optimistic concurrency)

**Starter template:**

```python
class OptimizedSystem:
    """
    Refactored system with minimal coordination.
    """
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.feature_cache = TTLCache(maxsize=1000, ttl=60)
    
    def increment_page_views(self, page_id):
        # TODO: Remove lock, use atomic increment
        pass
    
    def add_item_to_cart(self, user_id, item_id, quantity):
        # TODO: Use Redis HINCRBY for atomic hash increment
        # Or: Use CRDT pattern for concurrent carts
        pass
    
    def get_user_profile(self, user_id):
        # TODO: Remove lock entirely
        pass
    
    def update_user_profile(self, user_id, updates):
        # TODO: Use optimistic concurrency with version check
        pass
    
    def process_order(self, order_id):
        # TODO: Use order-level lock (not global)
        # TODO: Consider saga pattern for multi-step process
        pass
    
    def get_feature_flag(self, flag_name):
        # TODO: Use local cache with background refresh
        pass
    
    def submit_job(self, job_data):
        # TODO: Remove lock, use atomic LPUSH
        pass
    
    def claim_job(self, worker_id):
        # TODO: Use BRPOPLPUSH for atomic claim
        # Or: Partition queue by worker
        pass
```

### Part 3: Failure Mode Analysis

For your refactored system, document:

1. **What happens if Redis is unavailable?**
   - Which operations fail?
   - Which can proceed with degraded functionality?

2. **What happens if a worker crashes mid-operation?**
   - Order processing halfway done
   - Job claimed but not completed

3. **What happens under high contention?**
   - Many concurrent cart updates
   - Many workers claiming jobs

### Part 4: Metrics and Observability

Design monitoring for your coordination:

1. **What metrics would you collect?**
   - Lock acquisition time
   - Lock contention rate
   - Optimistic concurrency retry rate

2. **What alerts would you set?**
   - Lock acquisition p99 > 100ms
   - Retry rate > 10%

3. **How would you trace a "slow request" caused by coordination?**

### Deliverables

1. **Completed analysis table** (Part 1)
2. **Refactored code** with comments explaining decisions (Part 2)
3. **Failure mode documentation** (Part 3)
4. **Monitoring design** (Part 4)

### Bonus Challenges

1. **Multi-region:** How would your design change for a system spanning 3 regions?

2. **Hybrid Consistency:** Some operations need strong consistency (order processing), others don't (page views). Design a system that handles both efficiently.

3. **Coordination-Free Claims:** Design a job processing system where workers claim jobs without any distributed coordination. (Hint: consistent hashing, deterministic assignment)

---

## 16. Operational Excellence: Running Coordination Services in Production

### 16.1 Capacity Planning for Coordination Services

```
┌─────────────────────────────────────────────────────────────────────────┐
│                  COORDINATION SERVICE SIZING GUIDE                      │
│                                                                         │
│   ETCD SIZING:                                                          │
│   ────────────                                                          │
│                                                                         │
│   Cluster Size:                                                         │
│   - 3 nodes: Survives 1 failure (most common)                           │
│   - 5 nodes: Survives 2 failures (high availability)                    │
│   - 7 nodes: Survives 3 failures (rarely needed)                        │
│                                                                         │
│   Hardware per node:                                                    │
│   ┌────────────────┬──────────┬──────────┬──────────────┐               │
│   │ Load           │ CPU      │ Memory   │ Disk         │               │
│   ├────────────────┼──────────┼──────────┼──────────────┤               │
│   │ Light (<500 QPS)│ 2 cores │ 8 GB     │ 50 GB SSD    │               │
│   │ Medium (5K QPS) │ 4 cores │ 16 GB    │ 100 GB SSD   │               │
│   │ Heavy (15K QPS) │ 8 cores │ 32 GB    │ 200 GB NVMe  │               │
│   └────────────────┴──────────┴──────────┴──────────────┘               │
│                                                                         │
│   ZOOKEEPER SIZING:                                                     │
│   ─────────────────                                                     │
│                                                                         │
│   Key metrics to monitor:                                               │
│   - Outstanding requests (should be < 10)                               │
│   - Average latency (should be < 10ms)                                  │
│   - znode count (impacts snapshot time)                                 │
│   - Watch count (impacts notification overhead)                         │
│                                                                         │
│   Warning signs:                                                        │
│   - Snapshot taking > 30 seconds                                        │
│   - JVM heap > 80% utilized                                             │
│   - Log directory filling up                                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 16.1B Cost Reality: What Coordination Infrastructure Actually Costs

Coordination services are expensive—not just in compute, but in operational toil. Staff engineers must understand the true cost before committing to a coordination architecture.

```
┌─────────────────────────────────────────────────────────────────────────┐
│              COORDINATION INFRASTRUCTURE COST COMPARISON                │
│                                                                         │
│   ┌──────────────────┬──────────────┬──────────────┬─────────────────┐ │
│   │ Solution         │ 3-node Setup │ 5-node Setup │ Managed Service │ │
│   ├──────────────────┼──────────────┼──────────────┼─────────────────┤ │
│   │ ZooKeeper        │ $1.5K/month  │ $3K/month    │ N/A             │ │
│   │ (self-hosted)    │ + $8K/year   │ + $12K/year  │                 │ │
│   │                  │ (ops toil)   │ (ops toil)   │                 │ │
│   ├──────────────────┼──────────────┼──────────────┼─────────────────┤ │
│   │ etcd             │ $1K/month    │ $2K/month    │ N/A             │ │
│   │ (self-hosted)    │ + $5K/year   │ + $8K/year   │                 │ │
│   │                  │ (ops toil)   │ (ops toil)   │                 │ │
│   ├──────────────────┼──────────────┼──────────────┼─────────────────┤ │
│   │ Managed          │ N/A          │ N/A          │ $5K-8K/month    │ │
│   │ (Cloud-native)   │              │              │ + $2K/year      │ │
│   │                  │              │              │ (ops toil)      │ │
│   └──────────────────┴──────────────┴──────────────┴─────────────────┘ │
│                                                                         │
│   Cost breakdown (5-node ZooKeeper example):                           │
│   - Compute: 5 × (8-core, 32GB RAM) = $2.5K/month                       │
│   - Storage: 5 × 200GB NVMe = $500/month                               │
│   - Network: Inter-zone traffic = $200/month                            │
│   - Operational toil: $10K/year (debugging, upgrades, monitoring)      │
│                                                                         │
│   Total: ~$3.2K/month + $10K/year operational burden                   │
└─────────────────────────────────────────────────────────────────────────┘
```

**Top 2 Cost Drivers:**

1. **Dedicated Coordination Nodes That Can't Be Shared**
   - Coordination services require dedicated resources—you cannot co-locate other workloads
   - CPU and memory must be reserved even during idle periods
   - A 5-node ZooKeeper cluster costs ~$2K-5K/month in compute alone
   - Adding $10K/year in operational toil (debugging sessions, upgrades, monitoring)
   - Managed alternatives cost 2-3× more ($5K-8K/month) but reduce operational burden by 80%

2. **Operational Expertise Required**
   - ZooKeeper and etcd are notorious for subtle failure modes
   - GC pauses, session storms, and split-brain scenarios require deep expertise
   - On-call engineers spend 2-3 hours per incident debugging coordination issues
   - Training and documentation overhead: ~$5K-8K/year per team

**What Staff Engineers Do NOT Build:**

- **Custom consensus implementations** → Use battle-tested Raft libraries (etcd, Consul)
- **Coordination for operations that can be made idempotent** → Idempotency keys eliminate need for locks
- **Distributed locks for operations that can use optimistic concurrency** → Version numbers and CAS operations are cheaper

**Cost of Coordination Failure:**

If ZooKeeper is down for 10 minutes, all lock-dependent services are blocked. For an e-commerce platform:
- Estimated $50K in lost revenue (assuming $5K/minute transaction volume)
- Customer trust degradation (estimated $20K in churn risk)
- Engineering time to diagnose and resolve: 4-6 hours × $200/hour = $800-1.2K

**Total blast radius: $70K-71K per 10-minute outage**

### 16.1C Scale Thresholds: When Coordination Becomes the Bottleneck

Coordination services have hard limits. Staff engineers must recognize early warning signs and plan architectural changes before hitting these limits.

```
┌─────────────────────────────────────────────────────────────────────────┐
│              COORDINATION SCALING THRESHOLDS & ACTIONS                   │
│                                                                         │
│   ┌───────────────┬──────────────┬──────────────────────────────────┐  │
│   │ Lock Acq/sec  │ ZK Latency   │ Action Required                 │  │
│   ├───────────────┼──────────────┼──────────────────────────────────┤  │
│   │ 100/sec       │ < 5ms        │ Single cluster fine              │  │
│   │               │              │ Monitor leader CPU               │  │
│   ├───────────────┼──────────────┼──────────────────────────────────┤  │
│   │ 1K/sec        │ 5-20ms       │ Watch leader CPU                │  │
│   │               │              │ Consider read-only follower      │  │
│   │               │              │ offload                          │  │
│   ├───────────────┼──────────────┼──────────────────────────────────┤  │
│   │ 10K/sec       │ 20-50ms      │ ZK session count limit           │  │
│   │               │              │ approaching                      │  │
│   │               │              │ Need to partition coordination   │  │
│   ├───────────────┼──────────────┼──────────────────────────────────┤  │
│   │ 100K/sec      │ > 100ms      │ Cannot use centralized           │  │
│   │               │              │ coordination                     │  │
│   │               │              │ Must redesign for coordination   │  │
│   │               │              │ avoidance (CRDTs, partitioned    │  │
│   │               │              │ ownership)                       │  │
│   └───────────────┴──────────────┴──────────────────────────────────┘  │
│                                                                         │
│   Most Dangerous Scaling Assumption:                                   │
│   "ZooKeeper scales horizontally" → FALSE                              │
│                                                                         │
│   Reality: ZK writes go through leader only. Adding followers helps    │
│   reads but NOT write throughput. Write capacity is fixed by leader   │
│   node performance.                                                    │
│                                                                         │
│   Early Warning Signs:                                                │
│   - ZK leader CPU > 60%                                                │
│   - Session count > 10K                                                │
│   - Write latency p99 > 100ms                                          │
│                                                                         │
│   What Breaks First:                                                   │
│   Session establishment rate (ZK has hard limits on concurrent new      │
│   sessions). When this limit is hit, new clients cannot connect,       │
│   causing cascading failures in dependent services.                    │
└─────────────────────────────────────────────────────────────────────────┘
```

**Critical Thresholds:**

- **100/sec**: ZooKeeper handles easily, single cluster is fine
- **1K/sec**: Watch leader CPU, consider read-only follower offload
- **10K/sec**: ZK session count limit approaching, need to partition coordination
- **100K/sec**: Cannot use centralized coordination—must redesign for coordination avoidance (CRDTs, partitioned ownership)

**Most Dangerous Scaling Assumption:**

"ZooKeeper scales horizontally" — **FALSE**. ZK writes go through leader only; adding followers helps reads but not write throughput. Write capacity is fixed by leader node performance.

**Early Warning Signs:**

- ZK leader CPU > 60%
- Session count > 10K
- Write latency p99 > 100ms

**What Breaks First:**

Session establishment rate (ZK has hard limits on concurrent new sessions). When this limit is hit, new clients cannot connect, causing cascading failures in dependent services.

#### Concrete Scale Progression: From Startup to Hyperscale

| Scale | Services | Users | Coordination Load | Architecture | Monthly Cost |
|---|---|---|---|---|---|
| **V1: Startup** | 5-10 | 10K | 50 lock ops/sec | Single etcd cluster (3-node), in-process locks for most cases | $500 (shared etcd on app nodes) |
| **V2: Growth** | 10-30 | 100K | 500 lock ops/sec | Dedicated etcd cluster (3-node), leader election for 2-3 services | $2K (dedicated coordination nodes) |
| **V3: Scale** | 30-100 | 1M | 5K lock ops/sec | Dedicated ZK/etcd cluster (5-node), coordination for schedulers + config | $5K + 0.25 FTE ops |
| **V4: Large** | 100-300 | 10M | 20K lock ops/sec | Partitioned coordination (separate clusters per tier), some coordination avoidance via CRDTs | $15K + 0.5 FTE ops |
| **V5: Hyperscale** | 300+ | 100M+ | 100K+ lock ops/sec | Coordination-avoidant architecture, CRDTs, partitioned ownership, coordination only for cluster membership | $50K+ + 1 FTE ops |

**What Breaks at Each Transition:**
- **V1→V2:** Shared coordination on app nodes causes noisy-neighbor issues. Fix: dedicated nodes.
- **V2→V3:** Single 3-node cluster can't handle leader election + locking + config + service discovery. Fix: 5-node cluster or separate concerns.
- **V3→V4:** Single cluster becomes a single point of failure for the entire platform. Fix: partition by criticality tier (payments get their own cluster).
- **V4→V5:** Centralized coordination can't scale to 100K+ ops/sec. Fix: redesign for coordination avoidance — most operations must work without locks.

**Staff Insight:** "The trajectory of every scaling journey is TOWARD less coordination, not more. If you're adding coordination services as you scale, you're going the wrong direction."

### 16.2 Production Runbooks

#### Runbook 1: Leader Election Storm

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    RUNBOOK: LEADER ELECTION STORM                       │
│                                                                         │
│   SYMPTOMS:                                                             │
│   - Frequent leader changes (> 1/minute)                                │
│   - High CPU on consensus nodes                                         │
│   - Increased latency for coordination operations                       │
│   - "leadership transfer" or "new leader elected" log spam              │
│                                                                         │
│   DIAGNOSIS:                                                            │
│   ──────────                                                            │
│   1. Check network latency between nodes                                │
│      $ ping <peer_ip>                                                   │
│      Expected: < 2ms within datacenter                                  │
│                                                                         │
│   2. Check for CPU throttling                                           │
│      $ cat /sys/fs/cgroup/cpu/cpu.stat                                  │
│      nr_throttled should be 0                                           │
│                                                                         │
│   3. Check disk latency                                                 │
│      $ iostat -x 1                                                      │
│      await should be < 5ms for SSD                                      │
│                                                                         │
│   4. Check for clock skew                                               │
│      $ ntpstat or chronyc tracking                                      │
│      Offset should be < 100ms                                           │
│                                                                         │
│   RESOLUTION:                                                           │
│   ───────────                                                           │
│   1. If network issues: Fix network, consider increasing heartbeat      │
│      interval temporarily                                               │
│                                                                         │
│   2. If CPU throttling: Increase CPU limits or move to dedicated host   │
│                                                                         │
│   3. If disk latency: Move to faster storage (NVMe)                     │
│                                                                         │
│   4. If clock skew: Restart NTP, check for VM time drift                │
│                                                                         │
│   5. Temporary mitigation: Increase election timeout                    │
│      etcd: --election-timeout=5000 (5 seconds)                          │
│      ZK: tickTime * initLimit                                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Runbook 2: etcd Database Size Growing

```
ETCD DATABASE SIZE RUNBOOK
══════════════════════════

DIAGNOSE:
  etcdctl endpoint status --write-out=table    // check size
  etcdctl get '' --prefix --keys-only | ...    // count keys by prefix

COMPACT + DEFRAG (one node at a time!):
  REVISION=$(etcdctl endpoint status ... | jq '.revision')
  etcdctl compact $((REVISION - 10000))        // keep last 10K revisions
  etcdctl defrag --endpoints=$endpoint         // ⚠️ brief unavailability

AUTO-COMPACTION (etcd config):
  auto-compaction-mode: periodic
  auto-compaction-retention: "1h"
```

#### Runbook 3: ZooKeeper Session Expiration Storm

```
┌─────────────────────────────────────────────────────────────────────────┐
│                RUNBOOK: ZOOKEEPER SESSION EXPIRATION STORM              │
│                                                                         │
│   SYMPTOMS:                                                             │
│   - Mass client disconnections                                          │
│   - "Session expired" errors across many services                       │
│   - Ephemeral nodes disappearing unexpectedly                           │
│   - Leader election churn in dependent services                         │
│                                                                         │
│   LIKELY CAUSES:                                                        │
│   ───────────────                                                       │
│   1. ZooKeeper overloaded (long GC pauses)                              │
│   2. Network partition between clients and ZK                           │
│   3. Session timeout too aggressive                                     │
│   4. Too many watches or ephemeral nodes                                │
│                                                                         │
│   DIAGNOSIS:                                                            │
│   ──────────                                                            │
│   1. Check ZK server logs for GC pauses:                                │
│      grep "long gc" /var/log/zookeeper/zookeeper.log                    │
│                                                                         │
│   2. Check outstanding requests:                                        │
│      echo "stat" | nc localhost 2181 | grep Outstanding                 │
│                                                                         │
│   3. Check watch count:                                                 │
│      echo "wchs" | nc localhost 2181                                    │
│                                                                         │
│   4. Check ephemeral node count:                                        │
│      echo "stat" | nc localhost 2181 | grep Ephemeral                   │
│                                                                         │
│   RESOLUTION:                                                           │
│   ───────────                                                           │
│   1. If GC pauses:                                                      │
│      - Increase heap size                                               │
│      - Tune GC settings (use G1GC)                                      │
│      - Reduce znode data size                                           │
│                                                                         │
│   2. If too many watches:                                               │
│      - Clients should use single watch per path                         │
│      - Consider moving to etcd (streaming watches)                      │
│                                                                         │
│   3. If session timeout too aggressive:                                 │
│      - Increase client session timeout                                  │
│      - Default 30s is often too short for production                    │
│                                                                         │
│   4. Emergency: Rolling restart of ZK ensemble                          │
│      - Restart followers first, leader last                             │
│      - Wait for full sync between restarts                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 16.3 Disaster Recovery for Coordination Services

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     ETCD BACKUP PROCEDURE                               │
│                     (Run every 1-6 hours)                               │
│                                                                         │
│   1. CREATE SNAPSHOT:                                                   │
│      etcdctl snapshot save /var/backups/etcd/snapshot_$(date).db        │
│                                                                         │
│   2. VERIFY SNAPSHOT:                                                   │
│      etcdctl snapshot status <snapshot_file>                            │
│                                                                         │
│   3. UPLOAD TO REMOTE STORAGE:                                          │
│      aws s3 cp <snapshot_file> s3://my-backups/etcd/                    │
│                                                                         │
│   4. CLEANUP:                                                           │
│      Keep last 24 local backups, delete older ones                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                  ETCD RESTORE FROM BACKUP                               │
│         ⚠️  WARNING: Creates new cluster. Old data is lost!             │
│                                                                         │
│   STEP 1: Stop all etcd members                                         │
│           systemctl stop etcd (on each host)                            │
│                                                                         │
│   STEP 2: Download backup from remote storage                           │
│           aws s3 cp s3://my-backups/etcd/snapshot.db /tmp/              │
│                                                                         │
│   STEP 3: On each member, restore with new cluster config               │
│           rm -rf /var/lib/etcd/*                                        │
│           etcdctl snapshot restore /tmp/snapshot.db \                   │
│               --name=$HOSTNAME \                                        │
│               --data-dir=/var/lib/etcd \                                │
│               --initial-cluster=$NEW_CLUSTER_CONFIG                     │
│                                                                         │
│   STEP 4: Start all members                                             │
│           systemctl start etcd (on each host)                           │
│                                                                         │
│   STEP 5: Verify cluster health                                         │
│           etcdctl endpoint health --cluster                             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                     QUORUM LOSS RECOVERY                                │
│              ⚠️  LAST RESORT - May result in data loss!                 │
│                                                                         │
│   OPTION 1: Force new cluster from surviving member                     │
│   ─────────────────────────────────────────────────────                 │
│   1. Stop all etcd processes                                            │
│   2. On surviving member:                                               │
│      etcd --force-new-cluster --data-dir=/var/lib/etcd                  │
│   3. This creates single-node cluster with existing data                │
│   4. Add new members normally                                           │
│                                                                         │
│   OPTION 2: Restore from backup                                         │
│   ─────────────────────────────                                         │
│   1. Follow restore procedure above                                     │
│   2. Accept that data since last backup is lost                         │
│                                                                         │
│   PREVENTION:                                                           │
│   ───────────                                                           │
│   • Use 5 nodes instead of 3 for critical services                      │
│   • Spread across failure domains (racks, AZs)                          │
│   • Regular backup testing                                              │
│   • Monitoring for member health                                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 16.4 Performance Tuning

```
┌─────────────────────────────────────────────────────────────────────────┐
│              COORDINATION SERVICE PERFORMANCE TUNING                    │
│                                                                         │
│   ETCD TUNING:                                                          │
│   ────────────                                                          │
│                                                                         │
│   # Key performance settings                                            │
│   heartbeat-interval: 100ms    # Default, increase for WAN              │
│   election-timeout: 1000ms     # Must be > 5x heartbeat                 │
│   snapshot-count: 100000       # Increase if write-heavy                │
│   max-wals: 5                  # WAL file retention                     │
│                                                                         │
│   # Client-side tuning                                                  │
│   - Use connection pooling                                              │
│   - Batch reads with txn                                                │
│   - Use lease for multiple ephemeral keys                               │
│   - Avoid hot keys (shard if needed)                                    │
│                                                                         │
│   ZOOKEEPER TUNING:                                                     │
│   ─────────────────                                                     │
│                                                                         │
│   # zoo.cfg key settings                                                │
│   tickTime=2000              # Base time unit (ms)                      │
│   initLimit=10               # Ticks to initial sync                    │
│   syncLimit=5                # Ticks for sync                           │
│   maxClientCnxns=60          # Per-IP connection limit                  │
│   autopurge.snapRetainCount=3                                           │
│   autopurge.purgeInterval=1                                             │
│                                                                         │
│   # JVM settings for ZK                                                 │
│   -Xms4g -Xmx4g              # Fixed heap size                          │
│   -XX:+UseG1GC               # G1 for lower pause times                 │
│   -XX:MaxGCPauseMillis=50    # Target GC pause                          │
│                                                                         │
│   DISTRIBUTED LOCK TUNING:                                              │
│   ────────────────────────                                              │
│                                                                         │
│   - TTL: Balance between                                                │
│     - Too short: False lock expiration during GC                        │
│     - Too long: Slow recovery from crashes                              │
│     - Recommendation: 30-60 seconds for most use cases                  │
│                                                                         │
│   - Renewal interval: TTL / 3                                           │
│     - Renew well before expiry                                          │
│     - Account for network latency                                       │
│                                                                         │
│   - Retry backoff: Exponential with jitter                              │
│     - Prevents thundering herd                                          │
│     - Max backoff: 1-5 seconds                                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 16.5 Monitoring Dashboards

**Essential Metrics to Monitor:**

| Service | Metric | What It Tells You |
|---------|--------|-------------------|
| **etcd** | `etcd_server_has_leader` | 1 = healthy, 0 = no leader |
| | `etcd_server_leader_changes_seen_total` | Election frequency |
| | `etcd_disk_wal_fsync_duration_seconds` | Write latency |
| | `etcd_network_peer_round_trip_time_seconds` | Cluster communication |
| | `etcd_mvcc_db_total_size_in_bytes` | Database size |
| | `etcd_server_proposals_failed_total` | Consensus failures |
| **ZooKeeper** | `zk_outstanding_requests` | Queued requests |
| | `zk_avg_latency` | Average request latency |
| | `zk_num_alive_connections` | Active clients |
| | `zk_ephemerals_count` | Ephemeral nodes |
| | `zk_watch_count` | Active watches |
| | `jvm_gc_pause_seconds` | GC pause duration |

**Critical Alerts:**

| Alert | Condition | Severity | Action |
|-------|-----------|----------|--------|
| **NoLeader** | `has_leader == 0` for 30s | 🔴 Critical | Cluster can't accept writes. Check node health. |
| **HighLatency** | `wal_fsync_p99 > 100ms` | 🟡 Warning | Disk latency high. Check for noisy neighbors. |
| **DatabaseFull** | `db_size > 6GB` | 🔴 Critical | etcd limit is 8GB. Compact and defrag now. |
| **FrequentElections** | `elections > 0.1/min` | 🟡 Warning | Check network stability between nodes. |
| **SessionExpiration** | `expirations > 1/min` | 🟡 Warning | Clients losing sessions. Check ZK load. |

**Essential Dashboard Panels:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   COORDINATION DASHBOARD LAYOUT                         │
│                                                                         │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│   │ Leader Status│  │ Elections/hr │  │ Error Rate   │                  │
│   │   [STAT]     │  │   [GRAPH]    │  │   [GRAPH]    │                  │
│   │    ✓ / ✗     │  │   ~~~~~~~~   │  │   ~~~~~~~~   │                  │
│   └──────────────┘  └──────────────┘  └──────────────┘                  │
│                                                                         │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│   │ Latency p99  │  │ Database Size│  │ Connections  │                  │
│   │   [GRAPH]    │  │   [GAUGE]    │  │   [STAT]     │                  │
│   │   ~~~~~~~~   │  │   [####--]   │  │    1,234     │                  │
│   └──────────────┘  └──────────────┘  └──────────────┘                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Self-Check: Did I Cover Coordination Properly?

| Signal | Weak | Strong | ✓ |
|--------|------|--------|---|
| **Need for coordination** | Assumed it's needed | "First, can we avoid coordination entirely?" | ☐ |
| **Leader election** | "We need a leader" | "Leader with lease-based election, 30s failover, degraded mode when no leader" | ☐ |
| **Distributed locks** | "Lock before write" | "Lock with TTL, fencing tokens, what if lock service fails?" | ☐ |
| **Failure handling** | Not addressed | "If ZooKeeper down, we use local counts and sync later" | ☐ |
| **Clock assumptions** | "Use timestamps" | "Can't trust clocks; use logical clocks or fencing tokens" | ☐ |
| **Trade-offs** | Correctness always | "Accepting approximate limits for availability" | ☐ |

---

## Common Interview Questions & Staff-Level Answers

| Question | Senior Answer | Staff Answer |
|----------|--------------|--------------|
| **"How would you prevent duplicate job execution?"** | "Use a distributed lock" | "First, can we make jobs idempotent? If not, use leader election for the scheduler with a claims table for at-most-once semantics" |
| **"How do you handle the rate limiter's Redis going down?"** | "Retry connection" | "Fail open with local limits. Accept over-limit requests temporarily. Log for analysis. Alert on-call." |
| **"What happens if two nodes both think they're leader?"** | "Shouldn't happen" | "Split-brain is possible. Use fencing tokens. New leader's token > old leader's. Resources reject stale tokens." |
| **"Why not just use timestamps?"** | "That works" | "Clock skew can be 100ms+. Use logical clocks for ordering. Never use timestamps alone for coordination." |

---

## Quick Reference Card

### When to Use Each Coordination Pattern

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    COORDINATION PATTERN DECISION TREE                   │
│                                                                         │
│   Need mutual exclusion?                                                │
│   │                                                                     │
│   ├── YES: Can you use atomic operations?                               │
│   │   ├── YES → Use atomic ops (INCR, CAS)                              │
│   │   └── NO: Is contention low?                                        │
│   │       ├── YES → Use optimistic concurrency                          │
│   │       └── NO: Is the critical section short?                        │
│   │           ├── YES → Use distributed lock                            │
│   │           └── NO → Redesign to minimize lock scope                  │
│   │                                                                     │
│   └── NO: Need a single coordinator?                                    │
│       │                                                                 │
│       ├── YES → Use leader election                                     │
│       └── NO: Need agreed-upon value?                                   │
│           │                                                             │
│           ├── YES → Use consensus (etcd, ZK)                            │
│           └── NO → No coordination needed!                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Lock Implementation Checklist

```
□ Unique lock identifier (prevent releasing others' locks)
□ TTL to prevent deadlocks
□ Fencing tokens for downstream protection
□ Graceful handling of lock service failure
□ Metrics for acquisition time and contention
□ Timeout for acquisition attempts
□ Safe release (only if still owner)
□ Renewal mechanism for long operations (if needed)
```

### Leader Election Checklist

```
□ Single leader guarantee (quorum-based or lease-based)
□ Fast failover (< 10 seconds typically)
□ Leader step-down on quorum loss
□ Epoch/term numbers to fence old leaders
□ Heartbeat mechanism
□ Client redirection when leader changes
□ Degraded mode when no leader
□ Metrics for election frequency and duration
```

### Failure Response Matrix

| Failure | Rate Limiter | Job Scheduler | Config Service |
|---------|-------------|---------------|----------------|
| Leader down | Local counts | Queue jobs | Use cache |
| Lock service down | Fail open | Pause processing | Stale config |
| Network partition | Per-partition limits | Risk duplicates | Stale reads |
| Clock skew | Inaccurate windows | Lease issues | TTL problems |

### Key Metrics to Monitor

| Metric | Warning Threshold | Critical Threshold |
|--------|-------------------|-------------------|
| Lock acquisition p99 | > 50ms | > 200ms |
| Lock contention rate | > 10% | > 50% |
| Election frequency | > 1/hour | > 1/minute |
| Election duration | > 5s | > 30s |
| Coordination errors | > 0.1% | > 1% |
| Fencing token rejections | > 0 | > 0.01% |

---

## Further Reading

1. **"How to do distributed locking"** - Martin Kleppmann
   - The famous Redlock analysis
   - https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html

2. **"Distributed Systems for Fun and Profit"** - Mikito Takada
   - Free online book covering consensus fundamentals
   - http://book.mixu.net/distsys/

3. **"The Raft Consensus Algorithm"** - Diego Ongaro
   - Understandable consensus
   - https://raft.github.io/

4. **"Designing Data-Intensive Applications"** - Martin Kleppmann
   - Chapters 8 (Distributed Systems) and 9 (Consistency & Consensus)

5. **"Time, Clocks, and the Ordering of Events"** - Leslie Lamport
   - The foundational paper on logical clocks
   - https://lamport.azurewebsites.net/pubs/time-clocks.pdf

---

*"The first rule of distributed systems: Don't distribute. The second rule: If you must distribute, don't coordinate. The third rule: If you must coordinate, make it as rare as possible."*

---

# Part 17: Interview Calibration for Coordination Topics

## What Interviewers Are Evaluating

When a candidate discusses coordination in system design, interviewers assess:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    INTERVIEWER'S MENTAL RUBRIC                              │
│                                                                             │
│   QUESTION IN INTERVIEWER'S MIND          L5 SIGNAL           L6 SIGNAL     │
│   ───────────────────────────────────────────────────────────────────────── │
│                                                                             │
│   "Did they question whether                                                │
│    coordination is needed?"             Assumed needed    "Can we avoid it?"│
│                                                                             │
│   "Do they understand the costs?"       Lists benefits    Discusses costs   │
│                                                           AND benefits      │
│                                                                             │
│   "Do they know failure modes?"         "It should work"  Split-brain,      │
│                                                           election storms   │
│                                                                             │
│   "Can they size timeouts?"             Uses defaults     Calculates based  │
│                                                           on latency/skew   │
│                                                                             │
│   "Do they consider operations?"        Not mentioned     Backup, restore,  │
│                                                           runbooks          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## L5 vs L6 Interview Phrases

| Topic | L5 Answer (Competent) | L6 Answer (Staff-Level) |
|-------|----------------------|------------------------|
| **Need for coordination** | "We'll use a distributed lock" | "First, can we avoid coordination? Can we partition the work or use idempotency instead?" |
| **Leader election** | "We'll use ZooKeeper for leader election" | "Leader election with 30s lease, stepping down on quorum loss, and degraded mode when no leader available" |
| **Lock implementation** | "Use Redis SETNX with TTL" | "SETNX with TTL, fencing tokens passed to downstream, and fallback behavior when Redis is unavailable" |
| **Split-brain** | "We prevent it with proper design" | "Split-brain is possible. We use epoch numbers; resources reject stale epochs. If it happens, we have reconciliation procedures." |
| **Failure detection** | "Heartbeat timeout" | "Phi accrual detector that adapts to network conditions. 30s timeout balances false positives against detection speed." |
| **Clock assumptions** | "We use timestamps" | "Clocks can drift 100ms+. We use logical clocks for ordering and never rely on timestamps alone for coordination decisions." |
| **Degradation** | Not discussed | "When coordination is unavailable, we fail closed for writes but allow cached reads for 5 minutes." |

## Common L5 Mistakes That Cost the Level

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    L5 MISTAKES IN COORDINATION DISCUSSIONS                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   MISTAKE 1: "We'll use Kafka for coordination"                             │
│   ─────────────────────────────────────────────                             │
│   Kafka is a log, not a coordination service. Using it for leader           │
│   election or distributed locks requires building consensus on top,         │
│   which is complex and error-prone.                                         │
│                                                                             │
│   L6 CORRECTION: "Kafka is for event streaming. For coordination, I'd       │
│   use etcd or ZooKeeper which provide consensus primitives."                │
│                                                                             │
│   MISTAKE 2: "The lock prevents duplicate processing"                       │
│   ─────────────────────────────────────────────────                         │
│   Locks expire. GC pauses can cause a process to continue after losing      │
│   its lock. Without fencing tokens, duplicates are still possible.          │
│                                                                             │
│   L6 CORRECTION: "The lock provides mutual exclusion, but we also           │
│   need fencing tokens. The downstream resource checks the token and         │
│   rejects stale holders."                                                   │
│                                                                             │
│   MISTAKE 3: "We'll set timeout to 5 seconds"                               │
│   ────────────────────────────────────────────                              │
│   No justification. Timeouts should be calculated based on network          │
│   latency, clock skew, and acceptable detection delay.                      │
│                                                                             │
│   L6 CORRECTION: "Given cross-AZ latency of 2ms P99 and 50ms clock          │
│   skew worst case, I'd set heartbeat at 500ms, timeout at 2 seconds,        │
│   and lease TTL at 10 seconds to account for GC pauses."                    │
│                                                                             │
│   MISTAKE 4: "We use 3-node cluster for high availability"                  │
│   ─────────────────────────────────────────────────────────                 │
│   3 nodes survives 1 failure. But what if you need to do rolling            │
│   updates? Or if 2 nodes are in the same failure domain?                    │
│                                                                             │
│   L6 CORRECTION: "3 nodes survives 1 failure. For a critical service,       │
│   I'd use 5 nodes across 3 AZs. This allows 2 failures and enables          │
│   rolling updates without risking quorum."                                  │
│                                                                             │
│   MISTAKE 5: Not mentioning what happens when coordination fails            │
│   ─────────────────────────────────────────────────────────────────         │
│   This is the Staff-level differentiator. L5s design for the happy          │
│   path. L6s design for failure.                                             │
│                                                                             │
│   L6 CORRECTION: "When etcd is unavailable, the job scheduler buffers       │
│   jobs locally and stops leader election. Jobs continue processing at       │
│   reduced capacity until coordination recovers."                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Example Interview Exchange

```
INTERVIEWER: "How would you coordinate job scheduling across multiple workers?"

L5 ANSWER:
"I'd use a distributed lock. Before processing a job, the worker acquires 
a lock on the job ID. This prevents duplicates. I'd use Redis for the lock 
service."

L6 ANSWER:
"Let me first check if we need coordination at all. 

If jobs can be partitioned by ID, each worker handles a specific partition 
and we avoid coordination entirely. That's the best approach.

If we can't partition, I'd use leader election rather than per-job locks. 
The leader assigns jobs to workers. Benefits: one coordination point, not 
one per job. I'd implement this with etcd leases.

For failure handling:
- Leader dies: 10-30 second election window. Workers buffer jobs locally.
- Worker dies mid-job: Heartbeat-based detection. Leader reassigns after 
  timeout. Job must be idempotent or we use fencing tokens.
- etcd cluster down: Workers continue processing assigned jobs. No new 
  assignments until etcd recovers. We accept reduced throughput.

I'd also add:
- Retry budget: max 10% of requests as retries to prevent storms
- Circuit breaker on etcd calls: fail fast if etcd is struggling
- Metrics on election frequency, lock acquisition latency, queue depth"
```

## How to Explain Coordination to Leadership

Leaders care about risk, cost, and user impact—not Raft heartbeats. Frame coordination in business terms:

**One-liner:** "Coordination is the glue that keeps distributed systems consistent. When it fails, we get duplicate work, data corruption, or service outages. We minimize it because it's expensive and fragile."

**Risk framing:** "Our job scheduler uses leader election. If the coordination service goes down, we stop scheduling new jobs for 30–60 seconds. Existing jobs continue. We've designed for this—no data loss, but throughput drops. The alternative is no coordination, which would mean duplicate jobs and inconsistent state."

**Cost framing:** "Running a dedicated 5-node ZooKeeper cluster costs ~$5K/month plus 0.5 FTE for operations. We could use a managed service for ~$8K/month with less ops burden. The trade-off is lock-in vs. control."

**How to teach this topic:** When mentoring juniors, use the analogy: "Leader election is like electing a class president—only one person can make certain decisions. Locks are like a bathroom key—only one person can use the resource at a time. The hard part isn't the election or the key—it's what happens when the president vanishes or someone forgets to return the key." Teach in this order: (1) Why coordination is hard (Two Generals, FLP), (2) When to avoid it (idempotency, partitioning), (3) Leader election vs. locks (one coordinator vs. many critical sections), (4) Fencing tokens (the non-negotiable add-on), (5) Failure modes (split-brain, election storms, lock expiry). End with: "What happens when the coordination service is down?" If they can't answer, they're not ready for production.

## Staff-Level Reasoning Visibility

When discussing coordination, make your reasoning visible:

```
"I'm choosing leader election over per-job locks because..."
   └─── Shows you considered alternatives

"The timeout needs to be longer than network P99 plus clock skew..."
   └─── Shows you understand the mathematics

"When the lock service fails, we..."
   └─── Shows you plan for failure

"The trade-off is availability for consistency during the election window..."
   └─── Shows you understand trade-offs
```

---

# Part 18: Final Verification

## Master Review Prompt Check (All 11 Items)

Use this checklist to verify chapter completeness:

| # | Check | Status |
|---|-------|--------|
| 1 | **Judgment & decision-making** — When to use coordination vs. alternatives, timeout/TTL sizing, trade-off frameworks | ✅ |
| 2 | **Failure & incident thinking** — Partial failures, blast radius, cascading failure timeline, structured real incident (6.2C) | ✅ |
| 3 | **Scale & time** — Growth over years, first bottlenecks (16.1C), scale thresholds, evolution phases | ✅ |
| 4 | **Cost & sustainability** — Cost as first-class constraint (16.1B), coordination cost reality | ✅ |
| 5 | **Real-world engineering** — Operational burdens, human error (Anti-Pattern 6), on-call reality, ownership model | ✅ |
| 6 | **Learnability & memorability** — Mental models, one-liners, diagrams, Quick Reference Card | ✅ |
| 7 | **Data, consistency & correctness** — Consistency models (5.7), invariants, fencing tokens | ✅ |
| 8 | **Security & compliance** — Trust boundaries (9.7), data sensitivity in coordination | ✅ |
| 9 | **Observability & debuggability** — Metrics (16.5), dashboards, runbooks, alerts | ✅ |
| 10 | **Cross-team & org impact** — Ownership model, cross-team SLAs, dependency impact | ✅ |
| 11 | **Interview calibration** — What interviewers probe, Staff signals, leadership explanation, teaching | ✅ |

## L6 Dimension Coverage Table (A–J)

| Dim | Dimension | Coverage | Location |
|-----|-----------|----------|----------|
| **A** | Judgment & decision-making | Strong | Sections 1, 11; L5 vs L6 table; decision matrix (lock vs. alternatives); timeout justification |
| **B** | Failure & incident thinking | Strong | Sections 6, 6.2B, 6.2C; blast radius; cascading failure timeline; structured real incident |
| **C** | Scale & time | Strong | Section 16.1C; scale thresholds; evolution V1→V5; first bottlenecks |
| **D** | Cost & sustainability | Strong | Section 16.1B; cost reality; monthly cost by scale; cost as constraint |
| **E** | Real-world engineering | Strong | Anti-Pattern 6; ownership model; on-call reality; runbooks (16.2) |
| **F** | Learnability & memorability | Strong | Mental models; one-liners; Quick Reference Card; diagrams throughout |
| **G** | Data, consistency & correctness | Strong | Sections 5.7, 4.3; consistency spectrum; fencing tokens; invariants |
| **H** | Security & compliance | Strong | Section 9.7; trust boundaries; data sensitivity; compliance |
| **I** | Observability & debuggability | Strong | Section 16.5; metrics; dashboards; alerts; runbooks |
| **J** | Cross-team & org impact | Strong | Ownership model; cross-team SLAs; dependency impact; platform vs. product |

## Does This Section Meet L6 Expectations?

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    L6 COVERAGE CHECKLIST                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   JUDGMENT & DECISION-MAKING                                                │
│   ☑ When to use coordination vs. alternatives (idempotency, partitioning)   │
│   ☑ Choosing between leader election, locks, and consensus                  │
│   ☑ Timeout and TTL sizing with justification                               │
│   ☑ Trade-off between availability and consistency during failures          │
│                                                                             │
│   FAILURE & DEGRADATION THINKING                                            │
│   ☑ Split-brain prevention and detection                                    │
│   ☑ Election storms: causes and mitigations                                 │
│   ☑ Graceful degradation when coordination unavailable                      │
│   ☑ Fencing tokens for stale lock holders                                   │
│   ☑ Clock skew handling                                                     │
│                                                                             │
│   SCALE & EVOLUTION                                                         │
│   ☑ Multi-region coordination patterns                                      │
│   ☑ Scaling beyond leader bottleneck                                        │
│   ☑ Migration strategies (Redis to etcd, etc.)                              │
│                                                                             │
│   STAFF-LEVEL SIGNALS                                                       │
│   ☑ Questions coordination necessity first                                  │
│   ☑ Understands operational costs (runbooks, backup, restore)               │
│   ☑ Makes reasoning visible                                                 │
│   ☑ Acknowledges uncertainty and trade-offs                                 │
│                                                                             │
│   REAL-WORLD APPLICATION                                                    │
│   ☑ Job scheduler case study                                                │
│   ☑ Rate limiter coordination                                               │
│   ☑ Metadata service architecture                                           │
│                                                                             │
│   INTERVIEW CALIBRATION                                                     │
│   ☑ L5 vs L6 phrase comparisons                                             │
│   ☑ Common mistakes that cost the level                                     │
│   ☑ Interviewer evaluation criteria                                         │
│   ☑ How to explain to leadership                                            │
│   ☑ How to teach this topic                                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Remaining Gaps (Acceptable for Scope)

| Gap | Reason Acceptable |
|-----|-------------------|
| Byzantine fault tolerance | Rarely needed in practice; covered conceptually |
| Paxos algorithm details | Raft is preferred; Paxos covered at intuition level |
| Vendor-specific tuning | General principles apply; ops teams handle specifics |

## Self-Check Questions Before Interview

Use these to verify your understanding:

```
□ Can I explain why coordination should be avoided when possible?
□ Can I differentiate leader election, locks, and consensus use cases?
□ Can I design a system that degrades gracefully when coordination fails?
□ Can I size timeouts based on network and clock characteristics?
□ Can I explain fencing tokens and why locks alone aren't sufficient?
□ Can I discuss multi-region coordination trade-offs?
□ Can I identify the failure modes of my coordination design?
```

---

*"The best coordination is no coordination. The second best is coordination that fails gracefully."*
---

# Brainstorming Questions

## Understanding Coordination

1. Think of a system that uses distributed coordination. Could it be redesigned to avoid coordination? What would be the trade-offs?

2. When have you seen leader election cause problems? What was the failure mode?

3. How do you size timeouts for distributed locks? What's your mental model?

4. What's the difference between a lock and a lease? When would you choose one over the other?

5. How do you explain fencing tokens to someone who hasn't heard of them?

## Failure Modes

6. You have a distributed lock using Redis. What happens if Redis restarts during lock hold?

7. Design a system where leader election failure causes minimal impact. What patterns do you use?

8. How do you detect and recover from split-brain in a leader-based system?

9. What's an election storm? How do you prevent it?

10. Your lock service is experiencing high latency. What are the implications for lock holders?

## Applied Scenarios

11. Design leader election for a job scheduler. What's your availability vs. consistency trade-off?

12. You need a rate limiter across 100 servers. Do you need coordination? What are the alternatives?

13. How would you implement a lease-based cache invalidation system?

14. Design a metadata service where consistency is critical but availability is also important.

15. What's your go-to technology for coordination? When would you choose something different?

---

# Reflection Prompts

Set aside 15-20 minutes for each of these reflection exercises.

## Reflection 1: Your Coordination Instincts

Think about how you approach problems that seem to need coordination.

- Do you reach for locks and leader election by default?
- When was the last time you avoided coordination by redesigning the problem?
- Can you list three alternatives to distributed locks for a given problem?
- Do you consider the operational cost of coordination infrastructure?

For a system you've built that uses coordination, redesign it to minimize coordination.

## Reflection 2: Your Failure Mode Coverage

Consider how you think about coordination failures.

- Do you design for the case where the lock service itself fails?
- Have you ever debugged a fencing token issue?
- Can you explain what happens during leader election to a non-expert?
- Do you test coordination failure scenarios in your systems?

Write a failure mode analysis for coordination in a system you know well.

## Reflection 3: Your Technology Choices

Examine how you choose coordination technologies.

- Why do you choose one coordination technology over another?
- Do you understand the consistency guarantees of your chosen tools?
- Have you ever migrated between coordination technologies? What triggered it?
- Can you explain the trade-offs of ZooKeeper vs. etcd vs. Redis for locks?

Research a coordination technology you haven't used and compare it to your default choice.

---

# Homework Exercises

## Exercise 1: Coordination Avoidance

Take these problems that seem to require coordination. For each, design a solution that avoids centralized coordination:

1. **Sequential ID generation** across 10 services
2. **Rate limiting** across 50 servers
3. **Cache invalidation** across multiple regions
4. **Task assignment** to workers without double-processing
5. **Configuration updates** that must be atomic across services

For each:
- Describe the no-coordination approach
- What's the trade-off compared to coordinated approach?
- When would coordination still be necessary?

## Exercise 2: Leader Election Design

Design a leader election system for:

**Scenario: Multi-region job scheduler**
- 3 regions, one active leader needed
- Jobs must not be duplicated or lost
- Switchover time < 30 seconds

Include:
- Technology choice with justification
- Timeout values with reasoning
- Fencing mechanism
- Fallback behavior during election
- Monitoring and alerting

## Exercise 3: Failure Scenario Runbooks

Create runbooks for these coordination failure scenarios:

1. **Lock service completely unavailable**
   - Detection, immediate response, recovery

2. **Leader election taking > 5 minutes**
   - Investigation steps, manual intervention options

3. **Split-brain detected** (two leaders active)
   - Immediate actions, damage assessment, resolution

4. **Lock holder crashed without releasing**
   - Detection, automatic vs. manual resolution

5. **Clock skew causing lock issues**
   - Detection, mitigation, prevention

## Exercise 4: Technology Comparison

Compare these coordination approaches for a distributed cache invalidation system:

1. **Redis-based**: SETNX for locks
2. **ZooKeeper/etcd**: Proper consensus-based locks
3. **Kafka-based**: Event-driven invalidation
4. **No coordination**: Version-based invalidation

Create a comparison matrix with:
- Consistency guarantees
- Latency characteristics
- Failure modes
- Operational complexity
- Scalability limits

## Exercise 5: Interview Practice

Practice explaining these concepts (3 minutes each):

1. "Why shouldn't you use distributed locks in most cases?"
2. "Explain fencing tokens and why they're necessary"
3. "How does leader election work and what are its failure modes?"
4. "When would you choose ZooKeeper vs. Redis for coordination?"
5. "Design a job scheduler that's resilient to coordination failures"

Record yourself and evaluate for clarity and trade-off acknowledgment.

---

# Conclusion

Coordination is one of the hardest problems in distributed systems. The key insights from this section:

1. **Avoid coordination when possible.** Redesign problems to use idempotency, partitioning, or CRDTs instead.

2. **When coordination is needed, understand the failure modes.** Leader election can stall, locks can deadlock, consensus can partition.

3. **Timeouts and TTLs require careful tuning.** Too short causes false positives; too long causes availability issues.

4. **Fencing tokens are essential for correctness.** Locks alone are not sufficient in distributed systems.

5. **Graceful degradation matters.** What happens when coordination is unavailable? Design for this.

6. **Operational complexity is high.** Coordination infrastructure (ZooKeeper, etcd) requires expertise to run well.

### Visual 5: Chapter 22 in One Picture

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║              VISUAL SUMMARY: CHAPTER 22 — COORDINATION IN ONE PICTURE          ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  HIERARCHY:  No coord → Partition → Leader Election → Locks (last resort)     ║
║                                                                               ║
║  ┌─────────────────────────────────────────────────────────────────────────┐  ║
║  │ TWO GENERALS / FLP     CLOCKS UNRELIABLE      SPLIT-BRAIN DANGER        │  ║
║  │ Agreement is hard      NTP skew 10-100ms      Two leaders → corruption   │  ║
║  └─────────────────────────────────────────────────────────────────────────┘  ║
║                                                                               ║
║  KEY NUMBERS:                                                                 ║
║  • Leader election: 10-30 sec  • Lock TTL: 10-30 sec  • Raft heartbeat: 50-150ms║
║  • NTP skew: 10-100ms          • TrueTime: ~7ms       • Quorum: (n/2)+1       ║
║                                                                               ║
║  LEADER ELECTION: Raft/etcd, lease vs quorum, heartbeat, step down on quorum   ║
║  DISTRIBUTED LOCKS: TTL race (GC pause→expire→B acquires→A still writes)       ║
║  FENCING TOKENS: Monotonic token; storage rejects stale → integrity           ║
║                                                                               ║
║  CASE STUDIES: Job scheduler (leader) | Rate limiter (partition) | Metadata    ║
║  ANTI-PATTERNS: No fencing, Kafka for coordination, manual lock release       ║
║                                                                               ║
║  STAFF SIGNAL: "What happens when coordination fails?" — Design degradation    ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

In interviews, demonstrate that you think about coordination critically. Don't reach for it by default—question whether it's necessary. When it is, address failure modes proactively. That's Staff-level thinking.

---
