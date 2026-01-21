# Volume 3, Part 3: Leader Election, Coordination, and Distributed Locks

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

```python
class LamportClock:
    """
    Lamport Clock: Simplest logical clock.
    
    Rules:
    1. Before each event, increment clock
    2. When sending message, include clock value
    3. When receiving message, set clock = max(local, received) + 1
    
    Property: If event A happened-before event B, then L(A) < L(B)
    Warning: L(A) < L(B) does NOT imply A happened-before B
    """
    
    def __init__(self):
        self.time = 0
    
    def tick(self):
        """Internal event occurred."""
        self.time += 1
        return self.time
    
    def send(self):
        """Prepare to send message."""
        self.time += 1
        return self.time
    
    def receive(self, received_time):
        """Received message with timestamp."""
        self.time = max(self.time, received_time) + 1
        return self.time


# Example usage
node_a = LamportClock()
node_b = LamportClock()

# Node A does some work
node_a.tick()  # A's clock: 1

# Node A sends message to B
msg_time = node_a.send()  # A's clock: 2

# Node B receives message
node_b.receive(msg_time)  # B's clock: 3

# Now we know: A's event (2) happened-before B's event (3)
```

#### 2.5.2 Vector Clocks

```python
class VectorClock:
    """
    Vector Clock: Captures causality between events.
    
    Unlike Lamport clocks, vector clocks can detect concurrent events.
    
    Each node maintains a vector of counters, one per node.
    VC[i] = "number of events I know about from node i"
    """
    
    def __init__(self, node_id, node_ids):
        self.node_id = node_id
        self.clock = {nid: 0 for nid in node_ids}
    
    def tick(self):
        """Local event occurred."""
        self.clock[self.node_id] += 1
        return dict(self.clock)
    
    def send(self):
        """Prepare to send message."""
        self.clock[self.node_id] += 1
        return dict(self.clock)
    
    def receive(self, received_clock):
        """Merge received clock with local clock."""
        for node_id in self.clock:
            self.clock[node_id] = max(
                self.clock[node_id],
                received_clock.get(node_id, 0)
            )
        self.clock[self.node_id] += 1
        return dict(self.clock)
    
    @staticmethod
    def compare(vc1, vc2):
        """
        Compare two vector clocks.
        Returns:
          -1: vc1 happened-before vc2
           1: vc2 happened-before vc1
           0: Concurrent (neither happened-before the other)
        """
        less = False
        greater = False
        
        all_keys = set(vc1.keys()) | set(vc2.keys())
        for key in all_keys:
            v1 = vc1.get(key, 0)
            v2 = vc2.get(key, 0)
            if v1 < v2:
                less = True
            if v1 > v2:
                greater = True
        
        if less and not greater:
            return -1  # vc1 < vc2
        if greater and not less:
            return 1   # vc1 > vc2
        if less and greater:
            return 0   # Concurrent!
        return 0       # Equal (also concurrent)


# Example: Detecting concurrent writes
node_a = VectorClock("A", ["A", "B", "C"])
node_b = VectorClock("B", ["A", "B", "C"])

# A writes value
vc_a = node_a.tick()  # {'A': 1, 'B': 0, 'C': 0}

# B writes value (concurrently, no communication)
vc_b = node_b.tick()  # {'A': 0, 'B': 1, 'C': 0}

# These are concurrent!
result = VectorClock.compare(vc_a, vc_b)
assert result == 0  # Concurrent - need conflict resolution
```

#### 2.5.3 Hybrid Logical Clocks (HLC)

```python
class HybridLogicalClock:
    """
    Hybrid Logical Clock: Combines physical and logical time.
    
    Benefits:
    - Provides happens-before ordering like Lamport clocks
    - Timestamps are close to wall-clock time (useful for queries)
    - Bounded divergence from physical time
    
    Used by: CockroachDB, MongoDB, TiDB
    
    Format: (physical_time, logical_counter)
    """
    
    def __init__(self):
        self.physical = 0  # Wall clock component
        self.logical = 0   # Logical counter
    
    def now(self):
        """Get current HLC timestamp."""
        wall = self._get_wall_time()
        
        if wall > self.physical:
            # Physical time advanced
            self.physical = wall
            self.logical = 0
        else:
            # Physical time didn't advance (fast consecutive calls)
            self.logical += 1
        
        return (self.physical, self.logical)
    
    def receive(self, received_physical, received_logical):
        """Update HLC on receiving message."""
        wall = self._get_wall_time()
        
        if wall > self.physical and wall > received_physical:
            # Wall clock is ahead of both
            self.physical = wall
            self.logical = 0
        elif self.physical > received_physical:
            # Our physical is ahead
            self.logical += 1
        elif received_physical > self.physical:
            # Received physical is ahead
            self.physical = received_physical
            self.logical = received_logical + 1
        else:
            # Physical times equal
            self.logical = max(self.logical, received_logical) + 1
        
        return (self.physical, self.logical)
    
    def _get_wall_time(self):
        """Get current wall clock in milliseconds."""
        return int(time.time() * 1000)


# Example: Ordering events with HLC
hlc = HybridLogicalClock()

ts1 = hlc.now()  # (1642000000000, 0)
ts2 = hlc.now()  # (1642000000000, 1) - same ms, logical incremented
time.sleep(0.001)
ts3 = hlc.now()  # (1642000000001, 0) - new ms, logical reset

# All timestamps are orderable AND close to wall time
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
│   │                              │                                  │   │
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

```python
class TrueTimeSimulator:
    """
    Simulated TrueTime for understanding Spanner's approach.
    
    In practice, you'd use actual TrueTime or HLC.
    """
    
    def __init__(self, max_uncertainty_ms=7):
        self.max_uncertainty = max_uncertainty_ms
    
    def now(self):
        """Returns time interval [earliest, latest]."""
        wall = time.time() * 1000
        uncertainty = self.max_uncertainty
        
        return TTInterval(
            earliest=wall - uncertainty,
            latest=wall + uncertainty
        )
    
    def after(self, timestamp):
        """True if timestamp is definitely in the past."""
        now = self.now()
        return timestamp < now.earliest
    
    def before(self, timestamp):
        """True if timestamp is definitely in the future."""
        now = self.now()
        return timestamp > now.latest


class SpannerStyleTransaction:
    """
    Spanner-style commit with external consistency.
    """
    
    def __init__(self, truetime):
        self.tt = truetime
    
    def commit(self, writes):
        """Commit with external consistency guarantee."""
        # Get commit timestamp
        now = self.tt.now()
        commit_ts = now.latest  # Use latest to be safe
        
        # Perform writes
        for write in writes:
            self._apply_write(write, commit_ts)
        
        # COMMIT WAIT: Wait until commit_ts is definitely in the past
        while not self.tt.after(commit_ts):
            time.sleep(0.001)  # ~1ms sleep
        
        # Now we're guaranteed:
        # - Any subsequent transaction will see our writes
        # - Any transaction that started before will not see our writes
        # - This is external consistency (linearizability)!
        
        return commit_ts
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
│     │ 🗳️  │    │ 🗳️  │    │ 🗳️  │                                       │
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

```python
class LeaseBasedLeader:
    """
    Leader holds a time-limited lease. Must renew before expiry.
    If renewal fails, leadership is lost.
    """
    
    LEASE_DURATION = 10  # seconds
    RENEWAL_INTERVAL = 3  # seconds (renew well before expiry)
    
    def __init__(self, node_id, lease_store):
        self.node_id = node_id
        self.lease_store = lease_store  # Redis, etcd, ZooKeeper, etc.
        self.is_leader = False
    
    def try_become_leader(self):
        """Attempt to acquire leadership lease."""
        # Atomic: only succeeds if no current leader
        acquired = self.lease_store.set_if_not_exists(
            key="leader_lease",
            value=self.node_id,
            ttl=self.LEASE_DURATION
        )
        
        if acquired:
            self.is_leader = True
            self._start_renewal_loop()
        
        return acquired
    
    def _start_renewal_loop(self):
        """Keep renewing lease while we want to stay leader."""
        while self.is_leader:
            time.sleep(self.RENEWAL_INTERVAL)
            
            # Only renew if we're still the leader
            renewed = self.lease_store.set_if_equals(
                key="leader_lease",
                expected_value=self.node_id,
                new_value=self.node_id,
                ttl=self.LEASE_DURATION
            )
            
            if not renewed:
                # Lost leadership (someone else took over or we're partitioned)
                self.is_leader = False
                self._on_leadership_lost()
    
    def _on_leadership_lost(self):
        """Critical: Stop all leader-only activities immediately."""
        logging.warning("LEADERSHIP LOST - stopping all leader activities")
        # Stop processing, close connections, etc.
```

**Key Properties:**
- Leader must actively renew lease
- If network partitions leader from lease store, leadership is lost automatically
- No split-brain: old leader's lease expires before new leader can acquire

#### Mechanism 2: Quorum-Based Election

```python
class QuorumLeaderElection:
    """
    Leader must maintain quorum (majority) support.
    Uses heartbeats to detect failures.
    """
    
    def __init__(self, node_id, peers):
        self.node_id = node_id
        self.peers = peers  # List of peer addresses
        self.quorum_size = len(peers) // 2 + 1
        self.current_leader = None
        self.current_term = 0
    
    def start_election(self):
        """Start a new election when leader is suspected dead."""
        self.current_term += 1
        votes_received = 1  # Vote for self
        
        for peer in self.peers:
            try:
                response = peer.request_vote(
                    candidate_id=self.node_id,
                    term=self.current_term
                )
                if response.vote_granted:
                    votes_received += 1
            except TimeoutError:
                continue  # Peer unreachable, skip
        
        if votes_received >= self.quorum_size:
            self._become_leader()
        else:
            # Failed to win, wait and maybe try again
            self._wait_for_next_election()
    
    def _become_leader(self):
        self.current_leader = self.node_id
        logging.info(f"Won election for term {self.current_term}")
        self._start_heartbeat_loop()
    
    def _start_heartbeat_loop(self):
        """Send heartbeats to maintain leadership."""
        while self.current_leader == self.node_id:
            acks = 0
            for peer in self.peers:
                try:
                    peer.heartbeat(leader_id=self.node_id, term=self.current_term)
                    acks += 1
                except TimeoutError:
                    continue
            
            if acks < self.quorum_size - 1:
                # Lost quorum, step down
                self.current_leader = None
                logging.warning("Lost quorum, stepping down")
            
            time.sleep(self.HEARTBEAT_INTERVAL)
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
│                         ⚠️ DATA CORRUPTION ⚠️                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**This happens because:**
1. Clocks can drift (TTL expires sooner/later than expected)
2. GC pauses can freeze a process for seconds
3. Network delays can make a process appear dead when it's not
4. The lock holder has no way to know the lock has expired

### 4.3 Fencing Tokens: The Solution

```python
class FencedLockService:
    """
    Each lock acquisition gets a monotonically increasing token.
    Resources reject operations with stale tokens.
    """
    
    def __init__(self):
        self.current_token = 0
        self.lock_holder = None
        self.lock_expiry = None
    
    def acquire(self, client_id, ttl=10):
        now = time.time()
        
        # Check if lock is expired or free
        if self.lock_holder is None or now > self.lock_expiry:
            self.current_token += 1  # Increment token
            self.lock_holder = client_id
            self.lock_expiry = now + ttl
            
            return LockResult(
                acquired=True,
                fencing_token=self.current_token
            )
        
        return LockResult(acquired=False)


class FencedResource:
    """
    Resource that rejects operations with stale fencing tokens.
    """
    
    def __init__(self):
        self.highest_token_seen = 0
    
    def write(self, data, fencing_token):
        if fencing_token < self.highest_token_seen:
            raise StaleTokenError(
                f"Token {fencing_token} is stale. "
                f"Current: {self.highest_token_seen}"
            )
        
        self.highest_token_seen = fencing_token
        self._do_write(data)
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

### 4.4 Implementing Distributed Locks Correctly

```python
import redis
import uuid
import time

class DistributedLock:
    """
    Production-grade distributed lock using Redis.
    
    Features:
    - Unique lock identifiers prevent unlocking others' locks
    - TTL prevents deadlocks from crashed holders
    - Fencing tokens for downstream protection
    """
    
    def __init__(self, redis_client, name, ttl_seconds=10):
        self.redis = redis_client
        self.name = f"lock:{name}"
        self.ttl = ttl_seconds
        self.token = None
        self.lock_id = None
    
    def acquire(self, timeout=30):
        """Try to acquire lock. Returns fencing token on success."""
        self.lock_id = str(uuid.uuid4())
        deadline = time.time() + timeout
        
        while time.time() < deadline:
            # Atomic: SET if not exists, with TTL
            # Also increment fencing token atomically
            result = self.redis.eval(
                """
                local current = redis.call('GET', KEYS[1])
                if current == false then
                    local token = redis.call('INCR', KEYS[2])
                    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
                    return token
                end
                return nil
                """,
                2,  # Number of keys
                self.name,  # KEYS[1]: lock key
                f"{self.name}:token",  # KEYS[2]: token counter
                self.lock_id,  # ARGV[1]: unique lock identifier
                self.ttl  # ARGV[2]: TTL
            )
            
            if result is not None:
                self.token = int(result)
                return self.token
            
            time.sleep(0.1)  # Retry after short delay
        
        raise LockAcquisitionTimeout(f"Could not acquire {self.name}")
    
    def release(self):
        """Release lock, but only if we still own it."""
        if self.lock_id is None:
            return
        
        # Atomic: DELETE only if value matches our lock_id
        self.redis.eval(
            """
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('DEL', KEYS[1])
            end
            return 0
            """,
            1,
            self.name,
            self.lock_id
        )
        
        self.lock_id = None
        self.token = None
    
    def __enter__(self):
        return self.acquire()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


# Usage
lock = DistributedLock(redis_client, "job-123")

try:
    fencing_token = lock.acquire()
    
    # Do work with fencing token
    process_job(job_id="123", fencing_token=fencing_token)
    
finally:
    lock.release()

# Or with context manager
with DistributedLock(redis_client, "job-456") as token:
    process_job(job_id="456", fencing_token=token)
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

```python
class DistributedRWLock:
    """
    Distributed Read-Write Lock.
    
    - Multiple readers can hold lock simultaneously
    - Writer needs exclusive access
    - Writers wait for all readers to finish
    
    Implementation uses ZooKeeper-style sequential nodes.
    """
    
    def __init__(self, redis_client, name):
        self.redis = redis_client
        self.name = name
        self.read_lock_key = f"rwlock:{name}:readers"
        self.write_lock_key = f"rwlock:{name}:writer"
        self.reader_count_key = f"rwlock:{name}:reader_count"
    
    def acquire_read(self, timeout=30):
        """
        Acquire read lock. Blocks if writer holds or is waiting for lock.
        """
        deadline = time.time() + timeout
        reader_id = str(uuid.uuid4())
        
        while time.time() < deadline:
            # Check if writer is holding or waiting
            writer = self.redis.get(self.write_lock_key)
            
            if writer is None:
                # No writer, acquire read lock
                pipe = self.redis.pipeline()
                pipe.sadd(self.read_lock_key, reader_id)
                pipe.incr(self.reader_count_key)
                pipe.expire(self.read_lock_key, timeout)
                pipe.execute()
                
                # Double-check no writer snuck in
                if self.redis.get(self.write_lock_key) is None:
                    return ReadLockHandle(self, reader_id)
                else:
                    # Writer acquired, release our read
                    self._release_read(reader_id)
            
            time.sleep(0.01)
        
        raise LockTimeout("Could not acquire read lock")
    
    def acquire_write(self, timeout=30):
        """
        Acquire write lock. Blocks until all readers finish.
        """
        deadline = time.time() + timeout
        writer_id = str(uuid.uuid4())
        
        # First, try to become the waiting writer
        acquired = self.redis.set(
            self.write_lock_key,
            writer_id,
            ex=timeout,
            nx=True
        )
        
        if not acquired:
            raise LockContention("Another writer is waiting")
        
        # Wait for all readers to finish
        while time.time() < deadline:
            reader_count = int(self.redis.get(self.reader_count_key) or 0)
            
            if reader_count == 0:
                return WriteLockHandle(self, writer_id)
            
            time.sleep(0.01)
        
        # Timeout - release write lock
        self.redis.delete(self.write_lock_key)
        raise LockTimeout("Readers did not release in time")
    
    def _release_read(self, reader_id):
        pipe = self.redis.pipeline()
        pipe.srem(self.read_lock_key, reader_id)
        pipe.decr(self.reader_count_key)
        pipe.execute()
    
    def _release_write(self, writer_id):
        # Only release if we're the writer
        self.redis.eval(
            """
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('DEL', KEYS[1])
            end
            return 0
            """,
            1, self.write_lock_key, writer_id
        )
```

#### 4.6.2 Hierarchical Locks (Lock Ordering)

```python
class HierarchicalLockManager:
    """
    Hierarchical Lock Manager prevents deadlocks through lock ordering.
    
    Principle: Always acquire locks in a consistent order.
    
    Example hierarchy:
    - Level 0: Database
    - Level 1: Table
    - Level 2: Row
    
    Must acquire parent before child. Must release child before parent.
    """
    
    LOCK_HIERARCHY = {
        "database": 0,
        "table": 1,
        "row": 2,
    }
    
    def __init__(self, lock_service):
        self.lock_service = lock_service
        self.held_locks = {}  # Stack of held locks
    
    def acquire(self, resource_type, resource_id):
        """
        Acquire lock with hierarchy enforcement.
        """
        level = self.LOCK_HIERARCHY.get(resource_type)
        if level is None:
            raise ValueError(f"Unknown resource type: {resource_type}")
        
        # Check hierarchy - can only acquire at same or higher level
        for held_type, _ in self.held_locks.items():
            held_level = self.LOCK_HIERARCHY[held_type]
            if level < held_level:
                raise HierarchyViolation(
                    f"Cannot acquire {resource_type} lock while holding {held_type}"
                )
        
        # Acquire the lock
        lock_key = f"{resource_type}:{resource_id}"
        lock = self.lock_service.acquire(lock_key)
        
        self.held_locks[lock_key] = (resource_type, lock)
        return lock
    
    def release(self, resource_type, resource_id):
        """
        Release lock with hierarchy enforcement.
        """
        lock_key = f"{resource_type}:{resource_id}"
        
        # Must release in reverse order
        if lock_key not in self.held_locks:
            raise LockNotHeld(f"Lock {lock_key} not held")
        
        # Check that no child locks are still held
        my_level = self.LOCK_HIERARCHY[resource_type]
        for held_key, (held_type, _) in self.held_locks.items():
            if held_key == lock_key:
                continue
            held_level = self.LOCK_HIERARCHY[held_type]
            if held_level > my_level:
                raise HierarchyViolation(
                    f"Cannot release {resource_type} while holding {held_type}"
                )
        
        # Release
        _, lock = self.held_locks.pop(lock_key)
        lock.release()


# Usage example
lock_mgr = HierarchicalLockManager(lock_service)

# Correct usage:
lock_mgr.acquire("database", "mydb")
lock_mgr.acquire("table", "users")
lock_mgr.acquire("row", "user:123")
# ... do work ...
lock_mgr.release("row", "user:123")
lock_mgr.release("table", "users")
lock_mgr.release("database", "mydb")

# This would fail:
lock_mgr.acquire("row", "user:123")
lock_mgr.acquire("table", "users")  # HierarchyViolation!
```

#### 4.6.3 Try-Lock with Deadlock Detection

```python
class DeadlockDetector:
    """
    Detect deadlocks using wait-for graph analysis.
    
    When a process waits for a lock, we add an edge to the graph.
    If the graph has a cycle, there's a deadlock.
    """
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.wait_for_graph_key = "deadlock:wait_for"
    
    def register_wait(self, waiter_id, holder_id):
        """Record that waiter is waiting for holder."""
        # Add edge: waiter → holder
        self.redis.hset(self.wait_for_graph_key, waiter_id, holder_id)
        
        # Check for cycle
        if self._has_cycle(waiter_id):
            # Remove edge and report deadlock
            self.redis.hdel(self.wait_for_graph_key, waiter_id)
            return DeadlockDetected(
                f"Deadlock detected: {waiter_id} waiting for {holder_id}"
            )
        
        return None
    
    def clear_wait(self, waiter_id):
        """Clear wait record when lock acquired or abandoned."""
        self.redis.hdel(self.wait_for_graph_key, waiter_id)
    
    def _has_cycle(self, start_node, max_depth=100):
        """
        DFS to detect cycle starting from start_node.
        """
        visited = set()
        current = start_node
        
        for _ in range(max_depth):
            if current in visited:
                return True  # Cycle!
            
            visited.add(current)
            
            # Get next node in wait chain
            next_node = self.redis.hget(self.wait_for_graph_key, current)
            if next_node is None:
                return False  # End of chain, no cycle
            
            current = next_node.decode()
        
        # Too deep, assume potential deadlock
        return True


class DeadlockAwareLock:
    """Lock that detects and prevents deadlocks."""
    
    def __init__(self, lock_service, deadlock_detector, process_id):
        self.lock_service = lock_service
        self.detector = deadlock_detector
        self.process_id = process_id
    
    def acquire(self, resource_id, timeout=30):
        deadline = time.time() + timeout
        
        while time.time() < deadline:
            # Try to acquire
            result = self.lock_service.try_acquire(resource_id)
            
            if result.acquired:
                self.detector.clear_wait(self.process_id)
                return result.lock
            
            # Register that we're waiting
            holder_id = result.current_holder
            deadlock = self.detector.register_wait(self.process_id, holder_id)
            
            if deadlock:
                # We're the chosen victim - abort
                raise deadlock
            
            time.sleep(0.01)
        
        self.detector.clear_wait(self.process_id)
        raise LockTimeout()
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

```python
class IntentionLockManager:
    """
    Multi-granularity locking with intention locks.
    """
    
    class LockMode(Enum):
        IS = "IS"   # Intention Shared
        IX = "IX"   # Intention Exclusive
        S = "S"     # Shared
        X = "X"     # Exclusive
        SIX = "SIX" # S + IX
    
    # Compatibility matrix
    COMPATIBLE = {
        ("IS", "IS"): True,  ("IS", "IX"): True,  ("IS", "S"): True,
        ("IS", "X"): False, ("IS", "SIX"): True,
        
        ("IX", "IS"): True,  ("IX", "IX"): True,  ("IX", "S"): False,
        ("IX", "X"): False, ("IX", "SIX"): False,
        
        ("S", "IS"): True,   ("S", "IX"): False,  ("S", "S"): True,
        ("S", "X"): False,  ("S", "SIX"): False,
        
        ("X", "IS"): False,  ("X", "IX"): False,  ("X", "S"): False,
        ("X", "X"): False,  ("X", "SIX"): False,
        
        ("SIX", "IS"): True, ("SIX", "IX"): False, ("SIX", "S"): False,
        ("SIX", "X"): False, ("SIX", "SIX"): False,
    }
    
    def __init__(self, lock_service):
        self.lock_service = lock_service
        self.locks = {}  # resource -> {txn_id: mode}
    
    def acquire(self, txn_id, resource_path, mode):
        """
        Acquire intention locks up the hierarchy, then the actual lock.
        
        resource_path: ["database", "table:users", "row:123"]
        mode: The desired lock mode on the leaf resource
        """
        # Determine intention mode for ancestors
        intention_mode = self.LockMode.IS if mode in (self.LockMode.S,) \
                        else self.LockMode.IX
        
        # Acquire intention locks on all ancestors
        for i in range(len(resource_path) - 1):
            ancestor = "/".join(resource_path[:i+1])
            self._acquire_lock(txn_id, ancestor, intention_mode)
        
        # Acquire the actual lock on the target
        target = "/".join(resource_path)
        self._acquire_lock(txn_id, target, mode)
    
    def _acquire_lock(self, txn_id, resource, mode):
        """Acquire specific lock, checking compatibility."""
        current_locks = self.locks.get(resource, {})
        
        # Check compatibility with all current locks
        for holder_txn, holder_mode in current_locks.items():
            if holder_txn == txn_id:
                continue  # Upgrade our own lock
            
            if not self.COMPATIBLE.get((mode.value, holder_mode.value), False):
                raise LockConflict(
                    f"Cannot acquire {mode} on {resource}: "
                    f"conflicts with {holder_mode} held by {holder_txn}"
                )
        
        # Compatible, acquire lock
        if resource not in self.locks:
            self.locks[resource] = {}
        self.locks[resource][txn_id] = mode
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

#### 5.5.2 Raft State Machine

```python
class RaftNode:
    """
    Simplified Raft node implementation showing core state and transitions.
    
    States:
    - FOLLOWER: Passive, responds to leaders and candidates
    - CANDIDATE: Actively seeking votes to become leader
    - LEADER: Handles all client requests, replicates log
    """
    
    def __init__(self, node_id, peers):
        self.node_id = node_id
        self.peers = peers
        
        # Persistent state (must survive restarts)
        self.current_term = 0
        self.voted_for = None
        self.log = []  # List of (term, command) entries
        
        # Volatile state
        self.commit_index = 0
        self.last_applied = 0
        self.state = "FOLLOWER"
        
        # Leader-only volatile state
        self.next_index = {}   # For each peer: next log index to send
        self.match_index = {}  # For each peer: highest replicated index
        
        # Timing
        self.election_timeout = self._random_timeout(150, 300)  # ms
        self.last_heartbeat = time.time()
    
    def on_election_timeout(self):
        """No heartbeat received. Start election."""
        self.state = "CANDIDATE"
        self.current_term += 1
        self.voted_for = self.node_id
        votes_received = 1  # Vote for self
        
        # Request votes from all peers
        for peer in self.peers:
            response = self._request_vote(peer)
            if response.vote_granted:
                votes_received += 1
        
        if votes_received > len(self.peers) // 2:
            self._become_leader()
        else:
            self.state = "FOLLOWER"
    
    def _request_vote(self, peer):
        """RequestVote RPC."""
        return peer.handle_vote_request(
            term=self.current_term,
            candidate_id=self.node_id,
            last_log_index=len(self.log) - 1,
            last_log_term=self.log[-1].term if self.log else 0
        )
    
    def handle_vote_request(self, term, candidate_id, last_log_index, last_log_term):
        """Handle incoming RequestVote RPC."""
        # Update term if stale
        if term > self.current_term:
            self.current_term = term
            self.voted_for = None
            self.state = "FOLLOWER"
        
        # Grant vote if:
        # 1. We haven't voted for anyone else this term
        # 2. Candidate's log is at least as up-to-date as ours
        vote_granted = False
        
        if term >= self.current_term:
            if self.voted_for in (None, candidate_id):
                if self._is_log_up_to_date(last_log_index, last_log_term):
                    self.voted_for = candidate_id
                    vote_granted = True
        
        return VoteResponse(term=self.current_term, vote_granted=vote_granted)
    
    def _is_log_up_to_date(self, last_log_index, last_log_term):
        """Check if candidate's log is at least as up-to-date as ours."""
        my_last_term = self.log[-1].term if self.log else 0
        my_last_index = len(self.log) - 1
        
        # Compare by term first, then by index
        if last_log_term != my_last_term:
            return last_log_term > my_last_term
        return last_log_index >= my_last_index
    
    def _become_leader(self):
        """Transition to leader state."""
        self.state = "LEADER"
        
        # Initialize leader state
        for peer in self.peers:
            self.next_index[peer.id] = len(self.log)
            self.match_index[peer.id] = 0
        
        # Immediately send heartbeats
        self._send_heartbeats()
        
        # Append no-op entry to commit entries from previous terms
        self._append_entry(None)  # No-op
    
    def handle_client_request(self, command):
        """Leader handles client write request."""
        if self.state != "LEADER":
            raise NotLeaderError(f"Redirect to leader")
        
        # Append to local log
        entry = LogEntry(term=self.current_term, command=command)
        self.log.append(entry)
        entry_index = len(self.log) - 1
        
        # Replicate to followers
        self._replicate_to_followers()
        
        # Wait for commit
        return self._wait_for_commit(entry_index)
    
    def _replicate_to_followers(self):
        """Send AppendEntries RPCs to all followers."""
        for peer in self.peers:
            next_idx = self.next_index[peer.id]
            
            entries = self.log[next_idx:]
            prev_log_index = next_idx - 1
            prev_log_term = self.log[prev_log_index].term if prev_log_index >= 0 else 0
            
            response = peer.handle_append_entries(
                term=self.current_term,
                leader_id=self.node_id,
                prev_log_index=prev_log_index,
                prev_log_term=prev_log_term,
                entries=entries,
                leader_commit=self.commit_index
            )
            
            if response.success:
                self.next_index[peer.id] = len(self.log)
                self.match_index[peer.id] = len(self.log) - 1
            else:
                # Decrement next_index and retry
                self.next_index[peer.id] = max(0, self.next_index[peer.id] - 1)
        
        # Update commit index if new entries replicated to majority
        self._update_commit_index()
    
    def _update_commit_index(self):
        """Advance commit index if entries replicated to majority."""
        for n in range(self.commit_index + 1, len(self.log)):
            # Only commit entries from current term
            if self.log[n].term != self.current_term:
                continue
            
            # Count replicas
            replicas = 1  # Self
            for peer in self.peers:
                if self.match_index[peer.id] >= n:
                    replicas += 1
            
            if replicas > len(self.peers) // 2:
                self.commit_index = n
```

#### 5.5.3 Raft Safety Properties

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

#### 5.5.4 Raft Optimizations for Production

```python
class ProductionRaftOptimizations:
    """
    Key optimizations used in real Raft implementations.
    """
    
    # 1. PRE-VOTE: Prevents disruptive elections from partitioned nodes
    def pre_vote(self, peers):
        """
        Before incrementing term and starting real election,
        check if we could win. Prevents term inflation.
        """
        pre_votes = 0
        for peer in peers:
            # "Would you vote for me if I started an election?"
            response = peer.pre_vote_request(
                term=self.current_term + 1,  # Proposed next term
                last_log_index=len(self.log) - 1,
                last_log_term=self.log[-1].term if self.log else 0
            )
            if response.would_vote:
                pre_votes += 1
        
        if pre_votes > len(peers) // 2:
            # We could win, proceed with real election
            self.start_election()
        # Otherwise, stay follower - don't disrupt cluster
    
    # 2. PIPELINING: Send multiple entries without waiting for acks
    def pipeline_append_entries(self, peer, entries):
        """
        Send entries in flight without waiting for each ack.
        Dramatically improves throughput.
        """
        in_flight = []
        batch_size = 100
        
        for i in range(0, len(entries), batch_size):
            batch = entries[i:i + batch_size]
            future = peer.async_append_entries(batch)
            in_flight.append((i, future))
            
            # Limit in-flight to prevent memory issues
            if len(in_flight) >= 10:
                idx, fut = in_flight.pop(0)
                self._handle_response(peer, idx, fut.result())
    
    # 3. LEARNER NODES: Non-voting members for safe scaling
    def add_learner(self, new_node):
        """
        Add node as learner first. Learner receives log but doesn't vote.
        Once caught up, promote to voter.
        """
        self.learners.append(new_node)
        
        # Replicate log to learner
        self._catch_up_learner(new_node)
        
        # Once caught up, propose membership change
        if self._is_caught_up(new_node):
            self._propose_membership_change(
                add_voter=new_node.id
            )
    
    # 4. BATCHING: Batch multiple client requests
    def batch_client_requests(self, requests, max_batch_size=100, max_wait_ms=1):
        """
        Batch requests for single consensus round.
        Amortizes consensus cost across multiple operations.
        """
        batch = []
        deadline = time.time() + max_wait_ms / 1000
        
        while len(batch) < max_batch_size and time.time() < deadline:
            try:
                request = self.request_queue.get(timeout=0.001)
                batch.append(request)
            except Empty:
                break
        
        if batch:
            # Single log entry with multiple commands
            self._append_entry(BatchCommand(batch))
    
    # 5. READ LEASES: Avoid consensus for reads
    def read_with_lease(self, key):
        """
        Leader can serve reads without consensus if it has a valid lease.
        Lease is refreshed by successful heartbeats.
        """
        if self.state != "LEADER":
            raise NotLeaderError()
        
        if self.lease_valid_until > time.time():
            # Lease is valid, serve read locally
            return self.state_machine.get(key)
        else:
            # Lease expired, need to confirm leadership
            if self._confirm_leadership():
                self._refresh_lease()
                return self.state_machine.get(key)
            raise LeadershipLostError()
    
    def _confirm_leadership(self):
        """Confirm we're still leader by reaching quorum."""
        acks = 0
        for peer in self.peers:
            try:
                if peer.heartbeat(self.current_term):
                    acks += 1
            except TimeoutError:
                continue
        return acks >= len(self.peers) // 2
```

#### 5.5.5 Raft vs Paxos Comparison

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
│                           EPAXOS OVERVIEW                                │
│                                                                          │
│   Unlike Raft/Multi-Paxos, EPaxos is LEADERLESS.                        │
│   Any node can propose commands directly.                               │
│                                                                          │
│   FAST PATH (no conflicts):                                             │
│   ─────────────────────────                                             │
│   Proposer ──propose──▶ Fast Quorum (F+1 nodes)                        │
│                              │                                           │
│                              ▼                                           │
│                         COMMITTED in 1 RTT!                             │
│                                                                          │
│   SLOW PATH (conflicts detected):                                       │
│   ────────────────────────────────                                      │
│   Proposer ──propose──▶ Fast Quorum                                    │
│                         │                                                │
│                    conflicts!                                            │
│                         │                                                │
│            ◀─────────────                                               │
│   Proposer ──accept───▶ Classic Quorum (majority)                      │
│                              │                                           │
│                              ▼                                           │
│                         COMMITTED in 2 RTTs                             │
│                                                                          │
│   BENEFITS:                                                              │
│   - Lower latency for non-conflicting commands                         │
│   - No leader bottleneck                                                │
│   - Better geo-distribution (closest replica handles request)          │
│                                                                          │
│   DRAWBACKS:                                                            │
│   - Complex implementation                                              │
│   - Command interference detection overhead                            │
│   - Execution order requires dependency tracking                        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 5.6.2 Flexible Paxos

```python
class FlexiblePaxos:
    """
    Flexible Paxos: Quorum intersection, not quorum size, matters.
    
    Traditional: Q1 = Q2 = majority
    Flexible: Q1 ∩ Q2 ≠ ∅ (just need overlap)
    
    Example with 5 nodes:
    - Traditional: Write quorum = 3, Read quorum = 3
    - Flexible: Write quorum = 4, Read quorum = 2 (still overlap!)
    
    Use case: Optimize for read-heavy or write-heavy workloads.
    """
    
    def __init__(self, nodes, write_quorum_size, read_quorum_size):
        self.nodes = nodes
        self.write_quorum = write_quorum_size
        self.read_quorum = read_quorum_size
        
        # Validate: quorums must overlap
        assert write_quorum_size + read_quorum_size > len(nodes), \
            "Quorums must overlap!"
    
    def write(self, key, value):
        """Write requires write_quorum acks."""
        acks = 0
        for node in self.nodes:
            if node.write(key, value):
                acks += 1
                if acks >= self.write_quorum:
                    return True
        return False
    
    def read(self, key):
        """Read requires read_quorum responses."""
        responses = []
        for node in self.nodes:
            response = node.read(key)
            if response:
                responses.append(response)
                if len(responses) >= self.read_quorum:
                    # Return most recent value
                    return max(responses, key=lambda r: r.version)
        raise QuorumNotReached()
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

```python
class LinearizabilityExplained:
    """
    Linearizability: The gold standard of consistency.
    
    Definition: Every operation appears to take effect instantaneously
    at some point between its invocation and response.
    
    Key properties:
    1. Real-time ordering: If op A completes before op B starts,
       then A appears before B in the global order.
    2. Single-copy semantics: Behaves as if there's one copy of data.
    """
    
    # Example: Is this execution linearizable?
    #
    # Timeline:
    # Client A:  |--write(x=1)--|
    # Client B:             |--read()-->x=0--|
    # Client C:                    |--read()-->x=1--|
    #
    # Question: Can B read 0 while A's write is in progress?
    #
    # Answer: YES, if A's write hasn't "taken effect" yet.
    #         But if C reads 1, B must NOT read 0 after C's read completes.
    #
    # This is linearizable:
    # - A's write takes effect at some point during its execution
    # - B's read happens before the write takes effect
    # - C's read happens after the write takes effect
    
    def demonstrate_linearizable_violation(self):
        """
        This execution is NOT linearizable:
        
        Client A:  |--write(x=1)--|
        Client B:                      |--read()-->x=1--|
        Client C:                               |--read()-->x=0--|
        
        Why: B reads 1 (write has taken effect)
             C reads 0 AFTER B's read completed (!)
             This violates real-time ordering.
             Once a value is observed, it cannot "un-happen".
        """
        pass
    
    def linearizable_register(self):
        """
        Implementing a linearizable register requires:
        1. Total order on all operations
        2. Consensus for writes
        3. Reading from latest committed state
        
        Typically achieved via:
        - Raft/Paxos for writes
        - Read from leader, or quorum read
        """
        pass


class LinearizableKeyValueStore:
    """
    Example linearizable KV store using Raft.
    """
    
    def __init__(self, raft_node):
        self.raft = raft_node
    
    def write(self, key, value):
        """
        Write goes through Raft consensus.
        Returns only after committed to majority.
        """
        entry = WriteCommand(key=key, value=value)
        
        # Propose to Raft, wait for commit
        commit_result = self.raft.propose_and_wait(entry)
        
        if not commit_result.success:
            raise WriteRejected(commit_result.error)
        
        return commit_result
    
    def read_linearizable(self, key):
        """
        Option 1: Read from leader with ReadIndex.
        Confirms leadership before serving read.
        """
        # Confirm we're still leader
        if not self.raft.is_leader():
            raise NotLeader()
        
        # ReadIndex: Wait for commit index to advance past read request
        read_index = self.raft.get_read_index()
        self.raft.wait_for_apply(read_index)
        
        # Now safe to read from state machine
        return self.state_machine.get(key)
    
    def read_quorum(self, key):
        """
        Option 2: Quorum read.
        Read from majority, return most recent value.
        """
        responses = []
        for node in self.raft.peers + [self]:
            try:
                response = node.local_read(key)
                responses.append(response)
            except Unreachable:
                continue
        
        if len(responses) < self.raft.quorum_size:
            raise QuorumNotReached()
        
        # Return value with highest log index
        return max(responses, key=lambda r: r.log_index).value
```

#### 5.7.3 Sequential Consistency

```python
class SequentialConsistencyExplained:
    """
    Sequential Consistency: Weaker than linearizability.
    
    Definition: All processes see all operations in the same order,
    and each process's operations appear in program order.
    
    Key difference from linearizability:
    - Does NOT require real-time ordering
    - Operations can be reordered as long as:
      1. All processes see the same order
      2. Each process's operations maintain their relative order
    """
    
    # Example: This is sequentially consistent but NOT linearizable:
    #
    # Real time:
    # Process 1:  write(x=1)  .......................  read(y)→0
    # Process 2:  .........  write(y=1)  ............  read(x)→0
    #
    # Both read 0! In real time, both writes completed before reads.
    # NOT linearizable (writes should be visible).
    #
    # But it IS sequentially consistent with this order:
    # read(x)→0, read(y)→0, write(x=1), write(y=1)
    #
    # Each process's operations are in program order,
    # and both see the same global order.
    
    pass
```

#### 5.7.4 Causal Consistency

```python
class CausalConsistency:
    """
    Causal Consistency: Only causally-related operations must be ordered.
    
    If A causally depends on B (A "happened after" B):
    - All processes must see B before A
    
    Concurrent operations (no causal relationship):
    - Can be seen in any order by different processes
    
    Used by: MongoDB (default), Cassandra (with LWW), DynamoDB
    """
    
    def __init__(self):
        self.vector_clock = VectorClock()
        self.data = {}
        self.pending_writes = []
    
    def write(self, key, value):
        """
        Write with vector clock for causality tracking.
        """
        self.vector_clock.tick()
        
        write = CausalWrite(
            key=key,
            value=value,
            vector_clock=self.vector_clock.copy(),
            dependencies=self._get_dependencies()
        )
        
        self.data[key] = write
        return write
    
    def read(self, key):
        """
        Read returns value with its causal dependencies.
        """
        write = self.data.get(key)
        if write:
            # Update our vector clock
            self.vector_clock.merge(write.vector_clock)
        return write
    
    def receive_write(self, write):
        """
        Receive write from another replica.
        Only apply when all dependencies are satisfied.
        """
        if self._dependencies_satisfied(write):
            self._apply_write(write)
        else:
            # Buffer until dependencies arrive
            self.pending_writes.append(write)
    
    def _dependencies_satisfied(self, write):
        """Check if we've seen all causal dependencies."""
        for key, vc in write.dependencies.items():
            local_write = self.data.get(key)
            if local_write is None:
                return False
            if not local_write.vector_clock.dominates(vc):
                return False
        return True


# Example: Causal consistency in action
#
# User A posts: "I'm getting married!"
# User B likes the post
# User C comments: "Congratulations!"
#
# Causal order: Post → Like → Comment
#
# All replicas must show:
# - Like after Post
# - Comment after Post
# - But Like and Comment can appear in any order relative to each other
#   if they're concurrent
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
│   │      │👑 │    │   │    │   │    │   │    │   │                  │   │
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
│   │   │👑 │    │   │    │  ║  │   │👑 │    │   │    │   │           │   │
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

```python
class ClockSkewSafeLock:
    """Lock that accounts for clock skew."""
    
    MAX_CLOCK_SKEW = 5  # seconds, conservative estimate
    
    def acquire(self, ttl=30):
        # Use TTL that's safe even with clock skew
        effective_ttl = ttl + self.MAX_CLOCK_SKEW
        
        result = self.lock_service.acquire(ttl=effective_ttl)
        
        # But locally, assume lock is only valid for original TTL
        # (pessimistic, but safe)
        self.local_expiry = time.time() + ttl - self.MAX_CLOCK_SKEW
        
        return result
    
    def is_still_valid(self):
        """Check if we should still consider ourselves lock holder."""
        return time.time() < self.local_expiry
```

### 6.4 Failure Detection: How Do You Know a Node Is Dead?

In distributed systems, you can't distinguish between a dead node and a slow/partitioned one. Failure detection is about **probabilistic suspicion**, not certainty.

#### 6.4.1 The Phi Accrual Failure Detector

```python
class PhiAccrualFailureDetector:
    """
    Phi Accrual Failure Detector (used by Akka, Cassandra).
    
    Instead of binary alive/dead, outputs a "suspicion level" (phi).
    Higher phi = more likely to be dead.
    
    Benefits:
    - Adapts to network conditions automatically
    - Configurable threshold based on requirements
    - Accounts for variable heartbeat intervals
    """
    
    def __init__(self, threshold=8.0, window_size=100, min_std_dev_ms=500):
        self.threshold = threshold  # Phi value to consider dead
        self.window_size = window_size
        self.min_std_dev = min_std_dev_ms
        self.heartbeat_intervals = []
        self.last_heartbeat = None
    
    def heartbeat_received(self):
        """Record that a heartbeat was received."""
        now = time.time() * 1000  # ms
        
        if self.last_heartbeat is not None:
            interval = now - self.last_heartbeat
            self.heartbeat_intervals.append(interval)
            
            # Keep window bounded
            if len(self.heartbeat_intervals) > self.window_size:
                self.heartbeat_intervals.pop(0)
        
        self.last_heartbeat = now
    
    def phi(self):
        """
        Calculate current phi (suspicion level).
        
        Phi is based on the probability that we would have received
        a heartbeat by now, given the historical distribution.
        
        phi = -log10(P(interval > time_since_last))
        
        Example interpretation:
        - phi = 1: 10% chance node is alive
        - phi = 2: 1% chance node is alive
        - phi = 3: 0.1% chance node is alive
        """
        if self.last_heartbeat is None or len(self.heartbeat_intervals) < 2:
            return 0.0  # Not enough data
        
        now = time.time() * 1000
        time_since_last = now - self.last_heartbeat
        
        # Calculate mean and std dev of intervals
        mean = sum(self.heartbeat_intervals) / len(self.heartbeat_intervals)
        variance = sum((x - mean) ** 2 for x in self.heartbeat_intervals) / len(self.heartbeat_intervals)
        std_dev = max(math.sqrt(variance), self.min_std_dev)
        
        # Calculate phi using normal distribution CDF
        # P(X > time_since_last) where X ~ Normal(mean, std_dev)
        y = (time_since_last - mean) / std_dev
        probability_alive = 1 - self._normal_cdf(y)
        
        if probability_alive < 1e-10:
            return 10.0  # Cap at 10
        
        return -math.log10(probability_alive)
    
    def is_available(self):
        """Check if node is considered available."""
        return self.phi() < self.threshold
    
    def _normal_cdf(self, x):
        """Approximate normal CDF."""
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))


# Usage example
detector = PhiAccrualFailureDetector(threshold=8.0)

# In normal operation, heartbeats arrive regularly
for _ in range(10):
    detector.heartbeat_received()
    time.sleep(1)  # 1 second intervals

print(f"Phi: {detector.phi()}")  # Low phi, node is alive
print(f"Available: {detector.is_available()}")  # True

# Simulate node failure
time.sleep(10)  # No heartbeat for 10 seconds
print(f"Phi: {detector.phi()}")  # High phi, likely dead
print(f"Available: {detector.is_available()}")  # False
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

```python
class SWIMProtocol:
    """
    Simplified SWIM implementation showing core concepts.
    """
    
    def __init__(self, node_id, members, protocol_period_ms=1000, suspect_timeout_ms=5000):
        self.node_id = node_id
        self.members = set(members)
        self.protocol_period = protocol_period_ms
        self.suspect_timeout = suspect_timeout_ms
        
        self.alive = {}      # member_id -> incarnation number
        self.suspected = {}  # member_id -> suspect timestamp
        self.dead = set()
        
        self.k_indirect_probes = 3  # Number of indirect probes
        
        # Dissemination queue (piggyback on messages)
        self.updates_to_disseminate = []
    
    def protocol_round(self):
        """Execute one round of SWIM protocol."""
        # Pick random member to probe
        target = self._pick_random_member()
        if target is None:
            return
        
        # Step 1: Direct probe
        if self._direct_probe(target):
            self._mark_alive(target)
            return
        
        # Step 2: Indirect probe through K random members
        probers = random.sample(
            list(self.members - {target, self.node_id}),
            min(self.k_indirect_probes, len(self.members) - 2)
        )
        
        indirect_success = False
        for prober in probers:
            if self._indirect_probe(prober, target):
                indirect_success = True
                break
        
        if indirect_success:
            self._mark_alive(target)
        else:
            # Step 3: Mark as suspect
            self._mark_suspect(target)
    
    def _direct_probe(self, target):
        """Send ping, wait for ack."""
        try:
            response = self._send_ping(target, timeout_ms=200)
            return response.is_ack
        except TimeoutError:
            return False
    
    def _indirect_probe(self, prober, target):
        """Ask prober to ping target on our behalf."""
        try:
            response = self._send_ping_req(prober, target, timeout_ms=500)
            return response.target_responded
        except TimeoutError:
            return False
    
    def _mark_alive(self, member, incarnation=None):
        """Mark member as alive."""
        current_incarnation = self.alive.get(member, 0)
        new_incarnation = incarnation or current_incarnation
        
        if new_incarnation >= current_incarnation:
            self.alive[member] = new_incarnation
            if member in self.suspected:
                del self.suspected[member]
            self.dead.discard(member)
            
            self._queue_update(("ALIVE", member, new_incarnation))
    
    def _mark_suspect(self, member):
        """Mark member as suspected."""
        if member not in self.suspected:
            self.suspected[member] = time.time() * 1000
            self._queue_update(("SUSPECT", member, self.alive.get(member, 0)))
    
    def _check_suspect_timeout(self):
        """Promote long-suspected members to dead."""
        now = time.time() * 1000
        
        for member, suspect_time in list(self.suspected.items()):
            if now - suspect_time > self.suspect_timeout:
                self._mark_dead(member)
    
    def _mark_dead(self, member):
        """Confirm member as dead."""
        if member in self.suspected:
            del self.suspected[member]
        self.dead.add(member)
        self.members.discard(member)
        
        self._queue_update(("DEAD", member, 0))
    
    def refute_suspicion(self):
        """
        If WE are suspected, increment incarnation to prove we're alive.
        This overrides suspicion from other nodes.
        """
        self.alive[self.node_id] = self.alive.get(self.node_id, 0) + 1
        self._queue_update(("ALIVE", self.node_id, self.alive[self.node_id]))
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

```python
# BROKEN: Race condition galore
class BrokenJobScheduler:
    def poll_and_run(self):
        while True:
            # Multiple workers might see the same job!
            job = db.query("SELECT * FROM jobs WHERE status='pending' LIMIT 1")
            
            if job:
                # Another worker might have grabbed it between SELECT and UPDATE!
                db.execute("UPDATE jobs SET status='running' WHERE id = ?", job.id)
                self.run_job(job)
                db.execute("UPDATE jobs SET status='completed' WHERE id = ?", job.id)
            
            time.sleep(1)
```

**Failure Modes:**
1. Two workers grab the same job (duplicate execution)
2. Worker crashes after claiming job (job stuck in 'running')
3. No coordination on which jobs to prioritize

### 7.3 Correct Approach: Leader-Based Scheduler

```python
class CoordinatedJobScheduler:
    """
    Uses leader election and distributed locks for exactly-once execution.
    """
    
    def __init__(self, redis_client, worker_id):
        self.redis = redis_client
        self.worker_id = worker_id
        self.leader_election = LeaseBasedLeader(
            node_id=worker_id,
            lease_store=redis_client
        )
    
    def run(self):
        while True:
            if self.leader_election.is_leader:
                self._leader_loop()
            else:
                self._follower_loop()
            time.sleep(0.1)
    
    def _leader_loop(self):
        """Leader assigns jobs to workers."""
        # Get ready jobs
        jobs = db.query("""
            SELECT * FROM jobs 
            WHERE status = 'pending' 
            AND scheduled_time <= NOW()
            ORDER BY priority DESC
            LIMIT 100
        """)
        
        # Get available workers
        workers = self.redis.smembers("active_workers")
        
        for job, worker in zip(jobs, cycle(workers)):
            # Assign job to worker
            self.redis.lpush(f"worker:{worker}:queue", job.id)
            db.execute(
                "UPDATE jobs SET status='assigned', worker_id=? WHERE id=?",
                [worker, job.id]
            )
    
    def _follower_loop(self):
        """Workers process their assigned jobs."""
        # Register as active
        self.redis.sadd("active_workers", self.worker_id)
        self.redis.expire(f"worker:{self.worker_id}:active", 30)
        
        # Get my assigned job
        job_id = self.redis.brpop(f"worker:{self.worker_id}:queue", timeout=5)
        
        if job_id:
            self._process_job_safely(job_id)
    
    def _process_job_safely(self, job_id):
        """Process job with exactly-once semantics."""
        lock = DistributedLock(self.redis, f"job:{job_id}")
        
        try:
            fencing_token = lock.acquire(timeout=5)
            
            # Check job is still assigned to us (not reassigned due to timeout)
            job = db.query("SELECT * FROM jobs WHERE id = ?", job_id)
            if job.worker_id != self.worker_id:
                return  # Someone else took it
            
            # Execute
            db.execute("UPDATE jobs SET status='running' WHERE id=?", job_id)
            
            result = self.run_job(job)
            
            db.execute(
                "UPDATE jobs SET status='completed', result=?, fencing_token=? WHERE id=?",
                [result, fencing_token, job_id]
            )
            
        except Exception as e:
            db.execute(
                "UPDATE jobs SET status='failed', error=? WHERE id=?",
                [str(e), job_id]
            )
        finally:
            lock.release()
```

### 7.4 What Happens When Coordination Fails

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Leader dies | New jobs not assigned until new leader | Fast election (< 10s), job queue buffers |
| Redis down | No locks, no queues | Graceful degradation, local queue fallback |
| Worker dies mid-job | Job stuck in 'running' | Timeout-based job reclamation |
| Network partition | Workers can't reach leader | Local job buffering, eventual sync |

```python
class JobReclaimer:
    """Background process to reclaim stuck jobs."""
    
    def run(self):
        while True:
            # Find jobs stuck in 'running' for too long
            stuck_jobs = db.query("""
                SELECT * FROM jobs 
                WHERE status = 'running' 
                AND updated_at < NOW() - INTERVAL '5 minutes'
            """)
            
            for job in stuck_jobs:
                # Check if worker is still alive
                if not self.is_worker_alive(job.worker_id):
                    db.execute(
                        "UPDATE jobs SET status='pending', worker_id=NULL, attempts=attempts+1 WHERE id=?",
                        [job.id]
                    )
                    logging.warning(f"Reclaimed stuck job {job.id} from dead worker {job.worker_id}")
            
            time.sleep(60)
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
│   Accuracy:  ⭐          ⭐⭐⭐          ⭐⭐⭐⭐⭐       ⭐⭐⭐⭐⭐   │
│   Latency:   ⭐⭐⭐⭐⭐     ⭐⭐⭐⭐         ⭐⭐⭐          ⭐⭐      │
│   Complexity: ⭐          ⭐⭐           ⭐⭐⭐⭐        ⭐⭐⭐        │
│   Fault Tol: ⭐⭐⭐⭐⭐     ⭐⭐⭐⭐         ⭐⭐           ⭐         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 8.3 Approach 1: Local Counters (No Coordination)

```python
class LocalRateLimiter:
    """Each server maintains its own counter. No coordination."""
    
    def __init__(self, limit_per_server):
        # Assume N servers, so each gets limit/N
        self.limit = limit_per_server
        self.counters = {}  # user_id -> count
        self.window_start = time.time()
    
    def is_allowed(self, user_id):
        self._maybe_reset_window()
        
        current = self.counters.get(user_id, 0)
        if current >= self.limit:
            return False
        
        self.counters[user_id] = current + 1
        return True
```

**Problems:**
- If user hits same server, they get 1/N of actual limit
- If user spreads across servers, they get N× actual limit
- Load balancer changes can drastically change effective limit

### 8.4 Approach 2: Periodic Sync (Light Coordination)

```python
class PeriodicSyncRateLimiter:
    """
    Local counters synced periodically to central store.
    Best balance of accuracy and latency.
    """
    
    SYNC_INTERVAL = 1.0  # seconds
    
    def __init__(self, redis_client, global_limit):
        self.redis = redis_client
        self.global_limit = global_limit
        self.local_counts = defaultdict(int)
        self.local_limits = {}  # Cached from global
        
        # Start sync thread
        threading.Thread(target=self._sync_loop, daemon=True).start()
    
    def is_allowed(self, user_id):
        """Fast path: check local counter."""
        local_limit = self.local_limits.get(user_id, self.global_limit)
        
        if self.local_counts[user_id] >= local_limit:
            return False
        
        self.local_counts[user_id] += 1
        return True
    
    def _sync_loop(self):
        """Background sync to Redis."""
        while True:
            time.sleep(self.SYNC_INTERVAL)
            self._sync()
    
    def _sync(self):
        """Sync local counts to Redis, get updated limits."""
        counts_to_sync = dict(self.local_counts)
        self.local_counts.clear()
        
        pipe = self.redis.pipeline()
        
        for user_id, count in counts_to_sync.items():
            key = f"rate:{user_id}:{self._window_key()}"
            pipe.incrby(key, count)
            pipe.expire(key, 120)  # TTL slightly longer than window
            pipe.get(key)
        
        results = pipe.execute()
        
        # Update local limits based on global counts
        i = 0
        for user_id in counts_to_sync.keys():
            global_count = int(results[i * 3 + 2] or 0)
            remaining = max(0, self.global_limit - global_count)
            # Give this server a share of remaining quota
            self.local_limits[user_id] = remaining // self.num_servers
            i += 1
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

```python
class ResilientRateLimiter:
    """Rate limiter with graceful degradation."""
    
    def is_allowed(self, user_id):
        try:
            return self._check_distributed(user_id)
        except RedisError:
            # Redis down, fall back to local
            logging.warning("Redis unavailable, using local rate limiting")
            return self._check_local(user_id)
    
    def _check_distributed(self, user_id):
        # Full distributed check
        ...
    
    def _check_local(self, user_id):
        # Local-only, less accurate but still functional
        local_limit = self.global_limit // self.expected_server_count
        return self.local_counter.check(user_id, local_limit)
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
│   │    │   👑    │    │         │    │         │                    │   │
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

```python
class LeaderElectionViaMetadataService:
    """
    Use the metadata service itself for leader election of other services.
    """
    
    def __init__(self, etcd_client, service_name, node_id):
        self.client = etcd_client
        self.key = f"/leaders/{service_name}"
        self.node_id = node_id
        self.lease = None
    
    def campaign(self):
        """Attempt to become leader."""
        # Create a lease (TTL = 10 seconds)
        self.lease = self.client.lease(10)
        
        # Try to create leader key with lease
        success, _ = self.client.transaction(
            compare=[
                self.client.transactions.version(self.key) == 0  # Key doesn't exist
            ],
            success=[
                self.client.transactions.put(
                    self.key, 
                    self.node_id, 
                    lease=self.lease
                )
            ],
            failure=[]
        )
        
        if success:
            self._keep_alive()
            return True
        return False
    
    def _keep_alive(self):
        """Keep lease alive while we want to stay leader."""
        while self.is_leader:
            self.lease.refresh()
            time.sleep(3)  # Refresh every 3s (well before 10s TTL)
```

#### Pattern 2: Distributed Lock via Metadata Service

```python
class MetadataServiceLock:
    """Distributed lock using etcd's transaction support."""
    
    def __init__(self, etcd_client, lock_name):
        self.client = etcd_client
        self.key = f"/locks/{lock_name}"
        self.lease = None
    
    def acquire(self, timeout=30):
        deadline = time.time() + timeout
        
        while time.time() < deadline:
            self.lease = self.client.lease(10)
            
            success, responses = self.client.transaction(
                compare=[
                    self.client.transactions.version(self.key) == 0
                ],
                success=[
                    self.client.transactions.put(
                        self.key,
                        "locked",
                        lease=self.lease
                    )
                ],
                failure=[
                    self.client.transactions.get(self.key)
                ]
            )
            
            if success:
                return True
            
            # Wait for lock to be released (watch for delete)
            watch_id = self.client.watch(self.key)
            for event in watch_id:
                if event.type == 'DELETE':
                    break  # Lock released, try again
        
        raise LockTimeout()
    
    def release(self):
        if self.lease:
            self.lease.revoke()  # Automatically deletes key
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

```python
class ResilientMetadataClient:
    """Client that handles metadata service failures gracefully."""
    
    def __init__(self, etcd_endpoints, cache_ttl=300):
        self.client = etcd3.client(endpoints=etcd_endpoints)
        self.cache = TTLCache(maxsize=10000, ttl=cache_ttl)
        self.degraded_mode = False
    
    def get(self, key):
        try:
            value = self.client.get(key)
            self.cache[key] = value  # Update cache
            self.degraded_mode = False
            return value
        except EtcdException as e:
            logging.warning(f"Metadata service unavailable: {e}")
            self.degraded_mode = True
            
            if key in self.cache:
                logging.info(f"Returning cached value for {key}")
                return self.cache[key]
            
            raise MetadataUnavailable("No cached value available")
    
    def watch(self, key, callback):
        """Watch for changes with reconnection logic."""
        while True:
            try:
                for event in self.client.watch(key):
                    callback(event)
            except EtcdException:
                logging.warning("Watch disconnected, reconnecting...")
                time.sleep(1)
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

```python
class ZooKeeperPatterns:
    """
    Common ZooKeeper patterns with production considerations.
    """
    
    def __init__(self, zk_client):
        self.zk = zk_client
    
    # PATTERN 1: Leader Election with Sequential Nodes
    def leader_election(self, election_path, node_id):
        """
        ZooKeeper-style leader election using sequential ephemeral nodes.
        
        Algorithm:
        1. Create sequential ephemeral node
        2. Get all children
        3. If we're the lowest, we're leader
        4. Otherwise, watch the node just before us
        """
        # Create our candidate node
        my_node = self.zk.create(
            f"{election_path}/candidate-",
            value=node_id.encode(),
            ephemeral=True,
            sequence=True
        )
        my_seq = self._get_sequence(my_node)
        
        while True:
            # Get all candidates
            children = sorted(self.zk.get_children(election_path))
            
            if children[0] == my_node.split("/")[-1]:
                # We're the leader!
                return True
            
            # Find node just before us
            my_index = children.index(my_node.split("/")[-1])
            predecessor = children[my_index - 1]
            
            # Watch predecessor (efficient: only one watch)
            event = self.zk.exists(
                f"{election_path}/{predecessor}",
                watch=True
            )
            
            if event is None:
                # Predecessor gone, check again
                continue
            
            # Wait for predecessor to disappear
            self._wait_for_watch()
    
    # PATTERN 2: Distributed Lock
    def distributed_lock(self, lock_path, timeout=30):
        """
        ZooKeeper lock using write lock recipe.
        """
        lock_node = self.zk.create(
            f"{lock_path}/lock-",
            ephemeral=True,
            sequence=True
        )
        
        deadline = time.time() + timeout
        
        while time.time() < deadline:
            children = sorted(self.zk.get_children(lock_path))
            
            if children[0] == lock_node.split("/")[-1]:
                # We hold the lock
                return ZKLock(self.zk, lock_node)
            
            # Watch predecessor
            my_index = children.index(lock_node.split("/")[-1])
            predecessor = children[my_index - 1]
            
            if self.zk.exists(f"{lock_path}/{predecessor}", watch=True):
                self._wait_for_watch(timeout=deadline - time.time())
        
        # Timeout - clean up
        self.zk.delete(lock_node)
        raise LockTimeout()
    
    # PATTERN 3: Group Membership
    def join_group(self, group_path, member_id, member_data):
        """
        Join a group using ephemeral nodes.
        Node automatically removed if member disconnects.
        """
        member_node = self.zk.create(
            f"{group_path}/{member_id}",
            value=member_data.encode(),
            ephemeral=True
        )
        return member_node
    
    def get_group_members(self, group_path):
        """Get current group members."""
        children = self.zk.get_children(group_path)
        members = {}
        for child in children:
            data, stat = self.zk.get(f"{group_path}/{child}")
            members[child] = data.decode()
        return members
    
    def watch_group(self, group_path, callback):
        """Watch for membership changes."""
        @self.zk.ChildrenWatch(group_path)
        def watch_children(children):
            callback(children)
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

```python
class EtcdPatterns:
    """
    Production etcd patterns for Kubernetes-style coordination.
    """
    
    def __init__(self, etcd_client):
        self.client = etcd_client
    
    # PATTERN 1: Leader Election with Lease
    def leader_election(self, name, node_id, ttl=15):
        """
        etcd leader election using lease and campaign.
        """
        election = self.client.election(name)
        lease = self.client.lease(ttl)
        
        # Campaign blocks until we become leader
        # Automatically renews lease
        election.campaign(node_id, lease=lease)
        
        return EtcdLeader(election, lease)
    
    # PATTERN 2: Distributed Lock with Fencing Token
    def lock_with_fencing(self, name, ttl=30):
        """
        etcd lock that provides fencing token (revision).
        """
        lock = self.client.lock(name, ttl=ttl)
        lock.acquire()
        
        # The lock's revision serves as fencing token
        # It's monotonically increasing across all locks
        fencing_token = lock.revision
        
        return EtcdLock(lock, fencing_token)
    
    # PATTERN 3: Watch with Reconnection
    def reliable_watch(self, key_prefix, callback, start_revision=None):
        """
        Watch that handles disconnections and resumes from last seen revision.
        """
        revision = start_revision or 0
        
        while True:
            try:
                events, cancel = self.client.watch_prefix(
                    key_prefix,
                    start_revision=revision
                )
                
                for event in events:
                    callback(event)
                    # Track revision to resume from
                    revision = event.mod_revision + 1
                    
            except EtcdConnectionError:
                logging.warning("Watch disconnected, reconnecting...")
                time.sleep(1)
                continue
    
    # PATTERN 4: CAS Transaction
    def compare_and_swap(self, key, expected_value, new_value):
        """
        Atomic compare-and-swap using etcd transaction.
        """
        success, responses = self.client.transaction(
            compare=[
                self.client.transactions.value(key) == expected_value
            ],
            success=[
                self.client.transactions.put(key, new_value)
            ],
            failure=[
                self.client.transactions.get(key)
            ]
        )
        
        if success:
            return True, None
        else:
            # Return current value
            current = responses[0].value
            return False, current
    
    # PATTERN 5: Batch Operations with Single Revision
    def atomic_batch_update(self, updates: dict):
        """
        Apply multiple updates atomically.
        All updates get the same revision.
        """
        ops = [
            self.client.transactions.put(key, value)
            for key, value in updates.items()
        ]
        
        success, _ = self.client.transaction(
            compare=[],  # No preconditions
            success=ops,
            failure=[]
        )
        
        return success
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

```python
class RegionalLeaderPattern:
    """
    Each region has its own leader for local operations.
    Global operations coordinate across regional leaders.
    
    Used by: Spanner (with TrueTime), CockroachDB
    """
    
    def __init__(self, region, regional_cluster, global_coordinator):
        self.region = region
        self.regional_cluster = regional_cluster
        self.global_coord = global_coordinator
    
    def local_read(self, key):
        """Reads served by regional leader - fast!"""
        return self.regional_cluster.read(key)
    
    def local_write(self, key, value):
        """
        Writes to keys owned by this region - fast!
        Uses regional consensus only.
        """
        if self._is_owned_by_region(key):
            return self.regional_cluster.write(key, value)
        else:
            # Must coordinate with owning region
            return self._cross_region_write(key, value)
    
    def global_transaction(self, operations):
        """
        Transaction spanning multiple regions.
        Uses 2PC with TrueTime-style commit wait.
        """
        # Phase 1: Prepare in all regions
        participants = self._get_regions_for_operations(operations)
        prepare_results = {}
        
        for region, region_ops in participants.items():
            prepare_results[region] = self.global_coord.prepare(
                region, region_ops
            )
        
        if all(r.prepared for r in prepare_results.values()):
            # Phase 2: Commit with synchronized timestamp
            commit_ts = self._get_global_commit_timestamp()
            
            for region in participants:
                self.global_coord.commit(region, commit_ts)
            
            # Wait for commit timestamp to be in the past (TrueTime)
            self._commit_wait(commit_ts)
            
            return TransactionResult(committed=True, timestamp=commit_ts)
        else:
            # Abort all
            for region in participants:
                self.global_coord.abort(region)
            return TransactionResult(committed=False)
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

```python
class WitnessReplica:
    """
    Lightweight replica that participates in consensus but doesn't
    store full data. Only stores Raft log for voting.
    """
    
    def __init__(self, node_id):
        self.node_id = node_id
        self.raft_log = []        # Only the log
        self.current_term = 0
        self.voted_for = None
        # NO state_machine - can't serve reads
    
    def handle_append_entries(self, entries, leader_commit):
        """Append to log, vote, but don't apply to state machine."""
        self.raft_log.extend(entries)
        # Acknowledge but don't apply - we're just voting
        return AppendEntriesResponse(success=True)
    
    def handle_vote_request(self, term, candidate_id, last_log_index, last_log_term):
        """Full voting participation."""
        if term > self.current_term:
            self.current_term = term
            self.voted_for = candidate_id
            return VoteResponse(vote_granted=True)
        return VoteResponse(vote_granted=False)
    
    # CANNOT serve reads - no state machine
    def handle_read(self, key):
        raise WitnessCannotServeReads()
```

#### 9.6.4 Pattern 3: Hierarchical Coordination

```python
class HierarchicalCoordination:
    """
    Two-level coordination:
    - Regional coordinators handle local operations
    - Global coordinator handles cross-region operations
    
    Reduces global coordination overhead.
    """
    
    def __init__(self, region, regional_coord, global_coord):
        self.region = region
        self.regional = regional_coord
        self.global_coord = global_coord
    
    def acquire_local_lock(self, resource_id):
        """
        Fast lock for resources owned by this region.
        No global coordination needed.
        """
        return self.regional.lock(f"local:{resource_id}")
    
    def acquire_global_lock(self, resource_id):
        """
        Lock that spans regions. Higher latency.
        Uses global coordinator.
        """
        # First, get regional intention lock (fast)
        regional_lock = self.regional.lock(f"intent:{resource_id}")
        
        try:
            # Then, get global lock (slow)
            global_lock = self.global_coord.lock(resource_id)
            return HierarchicalLock(regional_lock, global_lock)
        except LockFailed:
            regional_lock.release()
            raise
    
    def regional_leader_election(self, service_name):
        """
        Elect a leader within this region only.
        Fast - no cross-region communication.
        """
        return self.regional.elect(f"{service_name}:{self.region}")
    
    def global_leader_election(self, service_name):
        """
        Elect a single global leader.
        Slow - requires global consensus.
        Only use when truly necessary.
        """
        return self.global_coord.elect(service_name)
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

```python
class MultiRegionFailover:
    """
    Strategies for handling region-level failures.
    """
    
    def __init__(self, regions, consensus_cluster):
        self.regions = regions
        self.cluster = consensus_cluster
    
    def handle_region_failure(self, failed_region):
        """
        Steps when a region becomes unavailable.
        """
        # 1. Detect region failure
        if not self._is_region_failure_confirmed(failed_region):
            return  # Might be transient
        
        logging.critical(f"Region {failed_region} confirmed failed")
        
        # 2. Update cluster membership (remove failed nodes)
        nodes_in_region = self._get_nodes_in_region(failed_region)
        for node in nodes_in_region:
            self.cluster.remove_member(node)
        
        # 3. Check if we still have quorum
        if not self.cluster.has_quorum():
            # Disaster scenario - need manual intervention
            raise QuorumLost("Lost quorum due to region failure")
        
        # 4. Re-elect if leader was in failed region
        if self._leader_in_region(failed_region):
            self.cluster.force_election()
        
        # 5. Failover traffic to remaining regions
        self._update_routing(exclude=failed_region)
        
        # 6. Start data recovery if needed
        self._schedule_data_recovery(failed_region)
    
    def _is_region_failure_confirmed(self, region):
        """
        Confirm region failure with multiple signals.
        Avoid false positives from network blips.
        """
        checks = [
            self._check_heartbeats(region),
            self._check_health_endpoints(region),
            self._check_network_reachability(region),
        ]
        
        # Require multiple confirmations
        failures = sum(1 for c in checks if not c)
        return failures >= 2
```

---

<a name="anti-patterns"></a>
## 10. Anti-Patterns: How Good Intentions Go Wrong

### Anti-Pattern 1: The God Lock

```python
# TERRIBLE: One lock for everything
class GodLockAntiPattern:
    def __init__(self):
        self.god_lock = DistributedLock("god-lock")
    
    def do_anything(self):
        with self.god_lock:
            # All operations go through this single lock
            # Throughput: 1 operation at a time, globally
            ...
```

**Why it's bad:**
- Serializes all operations
- Single point of failure
- Any slow operation blocks everything

**Fix: Fine-grained locks**
```python
class FineGrainedLocks:
    def update_user(self, user_id):
        with DistributedLock(f"user:{user_id}"):
            # Only locks this specific user
            ...
    
    def update_order(self, order_id):
        with DistributedLock(f"order:{order_id}"):
            # Only locks this specific order
            ...
```

### Anti-Pattern 2: The Chatty Coordinator

```python
# TERRIBLE: Constant coordination for every operation
class ChattyCoordinator:
    def handle_request(self, request):
        # 1. Check if I'm leader (network call)
        if not self.am_i_leader():
            return redirect_to_leader()
        
        # 2. Acquire lock (network call)
        lock = self.acquire_lock(request.resource_id)
        
        # 3. Read config (network call)
        config = self.metadata_service.get("config")
        
        # 4. Get peer list (network call)
        peers = self.metadata_service.get("peers")
        
        # 5. Finally do the actual work
        result = self.process(request)
        
        # 6. Release lock (network call)
        lock.release()
        
        # 5 coordination calls for 1 business operation!
        return result
```

**Why it's bad:**
- 5× latency just for coordination
- Coordination service becomes bottleneck
- Any coordination failure blocks everything

**Fix: Cache and batch**
```python
class EfficientCoordinator:
    def __init__(self):
        self.cached_leader = None
        self.cached_config = None
        self.config_version = 0
    
    def handle_request(self, request):
        # Use cached values when possible
        if self._need_coordination():
            self._refresh_state()
        
        # Do work with local state
        result = self.process(request, self.cached_config)
        
        return result
```

### Anti-Pattern 3: Unbounded Lock Hold Time

```python
# TERRIBLE: Holding lock while doing slow operations
class UnboundedLockHold:
    def process_job(self, job_id):
        with DistributedLock(f"job:{job_id}"):
            # Download 10GB file (could take minutes)
            data = download_large_file(job.url)
            
            # Process it (could take hours)
            result = expensive_ml_inference(data)
            
            # Lock held the entire time!
            save_result(result)
```

**Why it's bad:**
- Lock TTL might expire during processing
- Other processes starve waiting for lock
- System throughput tanks

**Fix: Minimize lock scope**
```python
class MinimalLockScope:
    def process_job(self, job_id):
        # Claim job quickly
        with DistributedLock(f"job:{job_id}", ttl=5):
            job = db.query("SELECT * FROM jobs WHERE id = ?", job_id)
            db.execute("UPDATE jobs SET status='processing' WHERE id = ?", job_id)
        
        # Do slow work WITHOUT the lock
        data = download_large_file(job.url)
        result = expensive_ml_inference(data)
        
        # Reacquire lock only for commit
        with DistributedLock(f"job:{job_id}", ttl=5):
            db.execute(
                "UPDATE jobs SET status='completed', result=? WHERE id = ?",
                [result, job_id]
            )
```

### Anti-Pattern 4: Ignoring Lock Timeout

```python
# TERRIBLE: Assuming you still have the lock
class IgnoresTimeout:
    def process(self):
        lock = DistributedLock("resource", ttl=10)
        lock.acquire()
        
        # Work that might take longer than 10 seconds...
        do_slow_work()  # Takes 30 seconds!
        
        # Lock expired 20 seconds ago, but we don't know
        # Someone else might have the lock now
        write_critical_data()  # DANGEROUS!
        
        lock.release()  # Releasing a lock we don't own!
```

**Fix: Check lock validity before critical operations**
```python
class ChecksValidity:
    def process(self):
        lock = DistributedLock("resource", ttl=10)
        fencing_token = lock.acquire()
        
        try:
            do_slow_work()
            
            # Before critical section, verify we still own lock
            if not lock.is_still_valid():
                raise LockExpired("Lost lock during processing")
            
            # Use fencing token for defense in depth
            write_critical_data(fencing_token=fencing_token)
        finally:
            lock.release()
```

### Anti-Pattern 5: Coordination for Read-Only Operations

```python
# TERRIBLE: Lock for reads
class LocksReads:
    def get_user(self, user_id):
        with DistributedLock(f"user:{user_id}"):  # WHY?
            return db.query("SELECT * FROM users WHERE id = ?", user_id)
```

**Why it's bad:**
- Reads don't need mutual exclusion
- Serializes all access to each user
- Massive performance penalty for no benefit

**Fix: Only lock writes**
```python
class CorrectLocking:
    def get_user(self, user_id):
        # No lock needed for reads
        return db.query("SELECT * FROM users WHERE id = ?", user_id)
    
    def update_user(self, user_id, data):
        # Lock only for writes
        with DistributedLock(f"user:{user_id}"):
            db.execute("UPDATE users SET ... WHERE id = ?", [data, user_id])
```

---

<a name="when-not-to-use-locks"></a>
## 11. When NOT to Use Locks

### Rule 1: If You Can Use Idempotent Operations Instead

```python
# Instead of locking to prevent double-increment:
with lock("counter"):
    value = db.get("counter")
    db.set("counter", value + 1)

# Use idempotent atomic operation:
db.increment("counter", 1)  # Atomic, no lock needed
```

### Rule 2: If You Can Partition the Work

```python
# Instead of global lock on job queue:
with lock("job-queue"):
    job = queue.pop()
    process(job)

# Partition jobs by hash:
my_partition = hash(worker_id) % num_partitions
job = queue.pop(partition=my_partition)  # Each worker has own partition
process(job)
```

### Rule 3: If Eventual Consistency Is Acceptable

```python
# Instead of lock for analytics counter:
with lock("page-view-counter"):
    views = db.get("page:123:views")
    db.set("page:123:views", views + 1)

# Use eventual consistency:
# Local buffer, batch writes every second
local_buffer["page:123:views"] += 1

# Background job:
for page_id, count in local_buffer.items():
    db.increment(f"page:{page_id}:views", count)
local_buffer.clear()
```

### Rule 4: If CRDTs Can Model Your Data

```python
# Instead of lock for shopping cart:
with lock(f"cart:{user_id}"):
    cart = db.get(f"cart:{user_id}")
    cart.add(item)
    db.set(f"cart:{user_id}", cart)

# Use Add-Wins Set CRDT (no lock needed):
class AWSetCart:
    """Add-Wins Set for concurrent shopping cart operations."""
    
    def __init__(self):
        self.adds = {}      # {item_id: {(timestamp, replica_id)}}
        self.removes = {}   # {item_id: {(timestamp, replica_id)}}
    
    def add(self, item_id, replica_id):
        timestamp = time.time()
        if item_id not in self.adds:
            self.adds[item_id] = set()
        self.adds[item_id].add((timestamp, replica_id))
    
    def remove(self, item_id, replica_id):
        timestamp = time.time()
        if item_id not in self.removes:
            self.removes[item_id] = set()
        self.removes[item_id].add((timestamp, replica_id))
    
    def get_items(self):
        """Item is in cart if any add is more recent than all removes."""
        result = []
        for item_id in self.adds:
            latest_add = max(self.adds[item_id]) if self.adds[item_id] else (0, '')
            latest_remove = max(self.removes.get(item_id, set()), default=(0, ''))
            if latest_add > latest_remove:
                result.append(item_id)
        return result
    
    def merge(self, other):
        """Merge two carts - conflict-free!"""
        for item_id, timestamps in other.adds.items():
            if item_id not in self.adds:
                self.adds[item_id] = set()
            self.adds[item_id].update(timestamps)
        
        for item_id, timestamps in other.removes.items():
            if item_id not in self.removes:
                self.removes[item_id] = set()
            self.removes[item_id].update(timestamps)
```

### Rule 5: If You Can Use Optimistic Concurrency Control

```python
# Instead of pessimistic locking:
with lock(f"account:{account_id}"):
    account = db.get(f"account:{account_id}")
    account.balance -= amount
    db.set(f"account:{account_id}", account)

# Use optimistic concurrency with version numbers:
def transfer_optimistic(account_id, amount):
    for attempt in range(MAX_RETRIES):
        # Read with version
        account, version = db.get_with_version(f"account:{account_id}")
        
        # Prepare update
        account.balance -= amount
        
        # Conditional write (CAS - Compare And Swap)
        success = db.set_if_version(
            f"account:{account_id}", 
            account, 
            expected_version=version
        )
        
        if success:
            return True
        
        # Someone else modified, retry
        logging.info(f"Conflict detected, retrying (attempt {attempt + 1})")
    
    raise TooManyConflicts("Could not complete transfer")
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
│   Safety: ⭐⭐⭐⭐⭐  ⭐⭐⭐⭐         ⭐⭐⭐           ⭐             │
│   Availability: ⭐   ⭐⭐⭐          ⭐⭐⭐⭐         ⭐⭐⭐⭐⭐       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 12.2 Building Resilient Coordination Clients

```python
class ResilientCoordinationClient:
    """
    Coordination client with graceful degradation.
    
    Design principles:
    1. Always have a fallback
    2. Prefer availability over strict consistency in degraded mode
    3. Make degradation observable (metrics, logs, alerts)
    4. Auto-recover when coordination becomes available
    """
    
    def __init__(self, coordination_service, config):
        self.coord = coordination_service
        self.config = config
        self.degraded_mode = False
        self.degraded_since = None
        self.cache = TTLCache(maxsize=10000, ttl=300)
        self.metrics = MetricsClient()
    
    def get_config(self, key, default=None):
        """Get config with fallback chain."""
        try:
            value = self.coord.get(key)
            self.cache[key] = value  # Update cache
            self._exit_degraded_mode()
            return value
        
        except CoordinationUnavailable:
            self._enter_degraded_mode()
            
            # Fallback 1: Local cache
            if key in self.cache:
                self.metrics.increment("config.cache_hit")
                return self.cache[key]
            
            # Fallback 2: Static default
            if default is not None:
                self.metrics.increment("config.default_used")
                return default
            
            # Fallback 3: Fail if critical
            raise ConfigUnavailable(f"No fallback for {key}")
    
    def acquire_lock(self, resource_id, timeout=30):
        """Acquire lock with degraded mode handling."""
        try:
            lock = self.coord.lock(resource_id, timeout=timeout)
            self._exit_degraded_mode()
            return DistributedLockHandle(lock)
        
        except CoordinationUnavailable:
            self._enter_degraded_mode()
            
            # Degraded strategy depends on use case
            strategy = self.config.get(
                f"lock.{resource_id}.degraded_strategy",
                "local"
            )
            
            if strategy == "local":
                # Use local lock (only protects within this process)
                return LocalLockHandle(resource_id)
            
            elif strategy == "fail":
                # Fail closed
                raise LockUnavailable("Coordination service down")
            
            elif strategy == "proceed":
                # Fail open (dangerous!)
                self.metrics.increment("lock.proceed_without_lock")
                return NoOpLockHandle()
    
    def _enter_degraded_mode(self):
        if not self.degraded_mode:
            self.degraded_mode = True
            self.degraded_since = time.time()
            logging.warning("Entering degraded mode - coordination unavailable")
            self.metrics.increment("coordination.degraded_mode.entered")
            alert("Coordination service unavailable - operating in degraded mode")
    
    def _exit_degraded_mode(self):
        if self.degraded_mode:
            duration = time.time() - self.degraded_since
            self.degraded_mode = False
            self.degraded_since = None
            logging.info(f"Exiting degraded mode after {duration:.1f}s")
            self.metrics.timing("coordination.degraded_mode.duration", duration)
```

### 12.3 Circuit Breaker for Coordination

```python
class CoordinationCircuitBreaker:
    """
    Circuit breaker prevents hammering a failing coordination service.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Coordination failing, fast-fail all requests
    - HALF_OPEN: Testing if coordination recovered
    """
    
    FAILURE_THRESHOLD = 5      # Failures before opening
    RESET_TIMEOUT = 30         # Seconds before trying again
    SUCCESS_THRESHOLD = 3      # Successes to close circuit
    
    def __init__(self, coordination_service):
        self.coord = coordination_service
        self.state = "CLOSED"
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
    
    def call(self, operation, *args, **kwargs):
        if self.state == "OPEN":
            if self._should_attempt_reset():
                self.state = "HALF_OPEN"
            else:
                raise CircuitOpen("Coordination circuit breaker is open")
        
        try:
            result = operation(*args, **kwargs)
            self._on_success()
            return result
        
        except CoordinationError as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        if self.state == "HALF_OPEN":
            self.success_count += 1
            if self.success_count >= self.SUCCESS_THRESHOLD:
                self.state = "CLOSED"
                self.failure_count = 0
                self.success_count = 0
                logging.info("Circuit breaker closed - coordination recovered")
        else:
            self.failure_count = 0
    
    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.FAILURE_THRESHOLD:
            self.state = "OPEN"
            logging.warning(
                f"Circuit breaker opened after {self.failure_count} failures"
            )
    
    def _should_attempt_reset(self):
        return (
            self.last_failure_time is not None and
            time.time() - self.last_failure_time > self.RESET_TIMEOUT
        )
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

```python
class DegradedModeTests:
    """Tests to verify system behaves correctly in degraded mode."""
    
    def test_coordination_unavailable(self):
        """System should continue with degraded functionality."""
        # Simulate coordination failure
        with mock_coordination_failure():
            # Service should not crash
            response = service.handle_request(test_request)
            
            # Should get degraded response, not error
            assert response.status != 500
            assert response.headers.get("X-Degraded-Mode") == "true"
    
    def test_cache_fallback(self):
        """Should use cached values when coordination fails."""
        # Prime the cache
        service.get_config("feature_flag_x")  # Caches value
        
        # Fail coordination
        with mock_coordination_failure():
            # Should return cached value
            value = service.get_config("feature_flag_x")
            assert value is not None
    
    def test_degraded_mode_metrics(self):
        """Should emit metrics when entering/exiting degraded mode."""
        with mock_coordination_failure():
            service.handle_request(test_request)
        
        assert metrics.get("coordination.degraded_mode.entered") == 1
        
        # Restore coordination
        service.handle_request(test_request)
        
        assert metrics.get("coordination.degraded_mode.duration") > 0
    
    def test_circuit_breaker_opens(self):
        """Circuit breaker should open after repeated failures."""
        with mock_coordination_failure():
            # Trigger enough failures
            for _ in range(10):
                try:
                    service.coordinate_something()
                except:
                    pass
        
        # Circuit should be open
        assert service.circuit_breaker.state == "OPEN"
        
        # Fast-fail without calling coordination
        with assert_no_network_calls():
            with pytest.raises(CircuitOpen):
                service.coordinate_something()
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

```python
class EtcdMaintenanceRunbook:
    """
    Runbook for etcd database size issues.
    """
    
    def diagnose_size_issue(self):
        """
        Step 1: Check current database size
        """
        commands = [
            # Check database size
            "etcdctl endpoint status --write-out=table",
            
            # Check revision numbers
            "etcdctl endpoint status --write-out=json | jq '.revision'",
            
            # Count keys by prefix
            "etcdctl get '' --prefix --keys-only | cut -d/ -f1-2 | sort | uniq -c | sort -rn | head -20",
        ]
        return commands
    
    def compact_and_defrag(self):
        """
        Step 2: Compact history and defragment
        
        WARNING: Defrag causes brief unavailability!
        Only run on one node at a time.
        """
        steps = """
        # 1. Get current revision
        REVISION=$(etcdctl endpoint status --write-out=json | jq '.revision')
        
        # 2. Compact old revisions (keep last 10000)
        COMPACT_REV=$((REVISION - 10000))
        etcdctl compact $COMPACT_REV
        
        # 3. Defragment each node (one at a time!)
        for endpoint in $ENDPOINTS; do
            echo "Defragmenting $endpoint..."
            etcdctl defrag --endpoints=$endpoint
            sleep 10  # Wait for node to recover
        done
        
        # 4. Verify size reduced
        etcdctl endpoint status --write-out=table
        """
        return steps
    
    def setup_auto_compaction(self):
        """
        Step 3: Enable automatic compaction
        """
        config = """
        # Add to etcd config:
        auto-compaction-mode: periodic
        auto-compaction-retention: "1h"  # Keep 1 hour of history
        
        # OR for revision-based:
        auto-compaction-mode: revision
        auto-compaction-retention: "10000"  # Keep last 10000 revisions
        """
        return config
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

```python
class CoordinationDR:
    """
    Disaster recovery procedures for coordination services.
    """
    
    def backup_etcd(self):
        """
        Regular backup procedure for etcd.
        Should run every 1-6 hours.
        """
        script = """
        #!/bin/bash
        BACKUP_DIR=/var/backups/etcd
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        
        # Create snapshot
        etcdctl snapshot save $BACKUP_DIR/snapshot_$TIMESTAMP.db
        
        # Verify snapshot
        etcdctl snapshot status $BACKUP_DIR/snapshot_$TIMESTAMP.db
        
        # Upload to remote storage
        aws s3 cp $BACKUP_DIR/snapshot_$TIMESTAMP.db s3://my-backups/etcd/
        
        # Cleanup old local backups (keep last 24)
        ls -t $BACKUP_DIR/snapshot_*.db | tail -n +25 | xargs rm -f
        """
        return script
    
    def restore_etcd_from_backup(self):
        """
        Restore etcd cluster from backup.
        
        WARNING: This creates a new cluster. Old cluster data is lost!
        """
        steps = """
        # 1. Stop all etcd members
        for host in $ETCD_HOSTS; do
            ssh $host 'systemctl stop etcd'
        done
        
        # 2. Download backup
        aws s3 cp s3://my-backups/etcd/snapshot_latest.db /tmp/snapshot.db
        
        # 3. Restore on each member with new cluster configuration
        for host in $ETCD_HOSTS; do
            ssh $host 'rm -rf /var/lib/etcd/*'
            scp /tmp/snapshot.db $host:/tmp/
            ssh $host 'etcdctl snapshot restore /tmp/snapshot.db \\
                --name=$HOSTNAME \\
                --data-dir=/var/lib/etcd \\
                --initial-cluster=$NEW_CLUSTER_CONFIG \\
                --initial-cluster-token=$NEW_TOKEN'
        done
        
        # 4. Start all members
        for host in $ETCD_HOSTS; do
            ssh $host 'systemctl start etcd'
        done
        
        # 5. Verify cluster health
        etcdctl endpoint health --cluster
        """
        return steps
    
    def recover_from_quorum_loss(self):
        """
        Emergency procedure when quorum is lost.
        Last resort - may result in data loss!
        """
        procedure = """
        QUORUM LOSS RECOVERY (etcd):
        ════════════════════════════
        
        If majority of nodes are permanently lost:
        
        Option 1: Force new cluster from surviving member
        ─────────────────────────────────────────────────
        1. Stop all etcd processes
        2. On surviving member:
           etcd --force-new-cluster --data-dir=/var/lib/etcd
        3. This creates single-node cluster with existing data
        4. Add new members normally
        
        Option 2: Restore from backup
        ─────────────────────────────
        1. Follow restore procedure above
        2. Accept that data since last backup is lost
        
        PREVENTION:
        ───────────
        - Use 5 nodes instead of 3 for critical services
        - Spread across failure domains (racks, AZs)
        - Regular backup testing
        - Monitoring for member health
        """
        return procedure
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

```python
class CoordinationMonitoring:
    """
    Essential metrics and alerts for coordination services.
    """
    
    ESSENTIAL_METRICS = {
        # etcd metrics
        "etcd": {
            "etcd_server_has_leader": "1 = healthy, 0 = no leader",
            "etcd_server_leader_changes_seen_total": "Election frequency",
            "etcd_disk_wal_fsync_duration_seconds": "Write latency",
            "etcd_network_peer_round_trip_time_seconds": "Cluster communication",
            "etcd_mvcc_db_total_size_in_bytes": "Database size",
            "etcd_server_proposals_failed_total": "Consensus failures",
            "grpc_server_handled_total": "Request rate",
        },
        
        # ZooKeeper metrics
        "zookeeper": {
            "zk_outstanding_requests": "Queued requests",
            "zk_avg_latency": "Average request latency",
            "zk_num_alive_connections": "Active clients",
            "zk_znode_count": "Total znodes",
            "zk_ephemerals_count": "Ephemeral nodes",
            "zk_watch_count": "Active watches",
            "jvm_gc_pause_seconds": "GC pause duration",
        },
    }
    
    CRITICAL_ALERTS = [
        {
            "name": "CoordinationNoLeader",
            "condition": "etcd_server_has_leader == 0 for 30s",
            "severity": "critical",
            "action": "Cluster cannot accept writes. Check node health.",
        },
        {
            "name": "CoordinationHighLatency",
            "condition": "etcd_disk_wal_fsync_duration_seconds_p99 > 0.1",
            "severity": "warning",
            "action": "Disk latency high. Check for noisy neighbors or disk issues.",
        },
        {
            "name": "CoordinationDatabaseFull",
            "condition": "etcd_mvcc_db_total_size_in_bytes > 6GB",
            "severity": "critical",
            "action": "etcd default limit is 8GB. Compact and defrag immediately.",
        },
        {
            "name": "CoordinationFrequentElections",
            "condition": "rate(etcd_server_leader_changes_seen_total[5m]) > 0.1",
            "severity": "warning",
            "action": "Elections happening too frequently. Check network stability.",
        },
        {
            "name": "ZKSessionExpiration",
            "condition": "rate(zk_session_expirations[5m]) > 1",
            "severity": "warning",
            "action": "Clients losing sessions. Check server load and client connectivity.",
        },
    ]
    
    def create_grafana_dashboard(self):
        """Template for essential coordination dashboard."""
        panels = [
            {"title": "Leader Status", "type": "stat", "metric": "etcd_server_has_leader"},
            {"title": "Elections/hour", "type": "graph", "metric": "rate(etcd_server_leader_changes)"},
            {"title": "Request Latency p99", "type": "graph", "metric": "histogram_quantile(0.99, ...)"},
            {"title": "Database Size", "type": "gauge", "metric": "etcd_mvcc_db_total_size_in_bytes"},
            {"title": "Active Connections", "type": "stat", "metric": "etcd_debugging_mvcc_current_revision"},
            {"title": "Error Rate", "type": "graph", "metric": "rate(grpc_server_handled_total{code!=\"OK\"})"},
        ]
        return panels
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