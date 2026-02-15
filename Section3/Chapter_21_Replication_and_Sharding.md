# Chapter 21: Replication and Sharding — Scaling Without Losing Control

---

## Preamble: The Moment You Realize One Server Isn't Enough

You've built a beautiful system. Clean schemas, proper indexes, query patterns optimized. Your single PostgreSQL instance handles 50,000 queries per second. Life is good.

Then your product goes viral. Or your company acquires three competitors. Or December happens and everyone decides to use your e-commerce platform simultaneously.

Suddenly you're staring at graphs that look like hockey sticks, and not the good kind.

**This is the inflection point where junior engineers panic and senior engineers get excited.** It's where you stop thinking about code and start thinking about systems. Where the word "distributed" stops being theoretical and becomes your daily reality.

This section is about what happens next—and more importantly, how to do it without losing your mind, your data, or your job.

---

## Quick Visual: The Scaling Journey

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WHEN DO YOU NEED WHAT?                                   │
│                                                                             │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  SINGLE NODE (Start Here)                                          │    │
│   │  • Can handle your load? STOP. Don't over-engineer.                │    │
│   │  • Optimize queries, add indexes, upgrade hardware first           │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                              ↓ Read bottleneck?                             │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  REPLICATION (Add Read Replicas)                                   │    │
│   │  • Scales READS horizontally                                       │    │
│   │  • Provides failover (high availability)                           │    │
│   │  • Does NOT scale writes                                           │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                              ↓ Write bottleneck OR data too large?          │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  SHARDING (Partition Data)                                         │    │
│   │  • Scales WRITES horizontally                                      │    │
│   │  • Scales storage horizontally                                     │    │
│   │  • Massive complexity cost - avoid until necessary                 │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│   GOLDEN RULE: Add complexity only when you've proven you need it.          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Simple Example: L5 vs L6 Scaling Decisions

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **DB hitting 80% CPU** | "Let's add read replicas" | "What's causing the load? Query optimization? Caching? Then replicas if needed." |
| **Need more write throughput** | "Let's shard the database" | "Can we batch writes? Use write-behind cache? Shard only if fundamentally constrained." |
| **Cross-region latency** | "Multi-leader replication" | "What data actually needs low-latency writes? Cache reads, replicate writes async for most." |
| **One user has 40% of data** | "That's a hot partition problem" | "Can we isolate this user? Dedicated shard? Or is this our largest customer who deserves VIP treatment?" |
| **Resharding needed** | "Plan the migration" | "Why do we need to reshard? Did we choose wrong key? Can we delay with vertical scaling?" |

---

## Part 1: Replication — More Than Just "Don't Lose My Data"

### 1.1 The Naive Understanding of Replication

Ask a junior engineer why we replicate data, and you'll get: *"So we don't lose it if a server dies."*

That's true. But it's like saying we have fire departments because fires are hot. It misses the strategic value.

**Replication serves four distinct purposes:**

| Purpose | What It Means | When It Matters |
|---------|---------------|-----------------|
| **Durability** | Data survives hardware failure | Always |
| **Availability** | System stays up when nodes fail | High-SLA systems |
| **Read Scaling** | Distribute read load across copies | Read-heavy workloads |
| **Latency Reduction** | Place data closer to users | Global systems |

The first two are about not dying. The second two are about thriving. Staff engineers think about all four simultaneously.

---

### 1.2 Leader-Follower Replication: The Workhorse

This is where 90% of production systems start, and where many stay forever.

```
┌─────────────────────────────────────────────────────────┐
│                     CLIENTS                             │
│                                                         │
│        ┌─────────┐                    ┌─────────┐       │
│        │  Writes │                    │  Reads  │       │
│        └────┬────┘                    └────┬────┘       │
│             │                              │            │
│             ▼                              ▼            │
│       ┌──────────┐               ┌─────────────────┐    │
│       │  LEADER  │──────────────▶│   FOLLOWERS     │    │
│       │ (Primary)│  Replication  │ (Read Replicas) │    │
│       └──────────┘    Stream     └─────────────────┘    │
│             │                              │            │
│             ▼                              ▼            │
│       ┌──────────┐              ┌─────────────────┐     │
│       │  Disk    │              │   Disk  Disk    │     │
│       └──────────┘              └─────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

**How it works:**
1. All writes go to a single leader node
2. Leader writes to its local storage
3. Leader streams changes to follower nodes
4. Followers apply changes in the same order
5. Reads can go to leader OR followers (with caveats)

**Why this model dominates:**
- Simple to reason about (one source of truth)
- No write conflicts possible
- Easy to implement correctly
- Matches most application read/write ratios (90%+ reads)

#### The Critical Decision: Synchronous vs Asynchronous Replication

This is where things get interesting—and where many teams make decisions they later regret.

**Synchronous Replication:**
```
Client ──▶ Leader ──▶ Follower(s) ──▶ ACK ──▶ Leader ──▶ Client
                         │
                   Must succeed
                   before response
```

- Write isn't acknowledged until at least one follower confirms
- Guarantees durability: if leader dies immediately after ACK, data exists elsewhere
- Cost: every write pays network latency to follower
- Risk: if follower is slow/dead, writes block

**Asynchronous Replication:**
```
Client ──▶ Leader ──▶ Client (ACK)
              │
              └──────▶ Follower(s) (eventually)
```

- Write acknowledged as soon as leader persists locally
- Fast: only local disk latency
- Risk: if leader dies before replication, data is lost
- Reality: this is what most systems actually use

**The Pragmatic Middle Ground: Semi-Synchronous**

Most production systems I've worked on use semi-synchronous:
- Wait for ACK from ONE follower before responding to client
- Other followers replicate asynchronously
- Balance between durability and performance

```
// Conceptual configuration (PostgreSQL-style)
synchronous_standby_names = 'FIRST 1 (replica1, replica2, replica3)'
// Wait for first one to respond, others are async
```

**Staff-Level Insight:** The choice between sync and async isn't about which is "better." It's about understanding your data's durability requirements per use case. User authentication tokens? Maybe async is fine—worst case, user logs in again. Financial transactions? You want synchronous. The same database can have both behaviors for different tables.

#### Quick Visual: Sync vs Async Trade-offs

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                REPLICATION MODE DECISION                                    │
│                                                                             │
│                        ┌─────────────────┐                                  │
│                        │   Your Write    │                                  │
│                        └────────┬────────┘                                  │
│                                 │                                           │
│              ┌──────────────────┴──────────────────┐                        │
│              ▼                                     ▼                        │
│   ┌─────────────────────┐              ┌─────────────────────┐              │
│   │   SYNCHRONOUS       │              │   ASYNCHRONOUS      │              │
│   ├─────────────────────┤              ├─────────────────────┤              │
│   │ ✓ Zero data loss    │              │ ✓ Low latency       │              │
│   │ ✓ Strong durability │              │ ✓ High throughput   │              │
│   │ ✗ Higher latency    │              │ ✗ Data loss risk    │              │
│   │ ✗ Availability risk │              │ ✗ Stale reads       │              │
│   ├─────────────────────┤              ├─────────────────────┤              │
│   │ USE FOR:            │              │ USE FOR:            │              │
│   │ • Financial txns    │              │ • Session data      │              │
│   │ • Payments          │              │ • Analytics         │              │
│   │ • Legal records     │              │ • Caches            │              │
│   │ • Audit logs        │              │ • Social features   │              │
│   └─────────────────────┘              └─────────────────────┘              │
│                                                                             │
│   SEMI-SYNC: Wait for 1 replica (best of both for most cases)               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 1.3 The Replication Lag Problem

Here's where junior engineers get bitten:

```
Timeline:
─────────────────────────────────────────────────────────────▶
   0ms         10ms        20ms        30ms        40ms

Leader:    [Write X=1]
                          [Write X=2]
                                      [Write X=3]

Follower:              [Apply X=1]
                                               [Apply X=2]
                                                          ... X=3 coming

Client reads from follower at 35ms: sees X=1 (stale!)
```

**Replication lag** is the delay between when data is written to the leader and when it appears on followers. This delay is usually milliseconds but can spike to seconds or minutes during:
- Network partitions
- Follower disk I/O pressure  
- Large transactions
- Schema migrations
- Follower restarts

**Real Production Scenario:**

User updates profile picture:
1. `POST /profile/picture` → hits leader → returns 200 OK
2. User immediately refreshes page
3. `GET /profile` → hits follower → returns OLD picture
4. User files support ticket: "Your website is broken"

This is called **read-your-own-writes inconsistency**, and it's one of the most common bugs in distributed systems.

**Solutions:**

| Approach | How It Works | Trade-off |
|----------|--------------|-----------|
| **Sticky sessions** | Route user to same replica for a time window | Uneven load distribution |
| **Read from leader** | After write, force reads to leader for N seconds | Leader becomes bottleneck |
| **Causal consistency** | Track write timestamps, ensure reads see them | Complexity, latency |
| **Version vectors** | Client carries version, reject stale responses | Client complexity |

**What We Actually Do at Scale:**

```
WRITE-FLAG ROUTING (read-your-writes guarantee)
───────────────────────────────────────────────
update_profile(user_id, data):
  result = leader_db.update(user_id, data)
  session.set("last_write:{user_id}", result.timestamp, ttl=30)
  RETURN result

get_profile(user_id):
  last_write = session.get("last_write:{user_id}")
  
  IF last_write:
    RETURN leader_db.get(user_id)   // User recently wrote → read from leader
  ELSE:
    RETURN follower_db.get(user_id) // No recent writes → followers are fine
```

This pattern—**write-flag routing**—is simple, effective, and handles 99% of read-your-writes scenarios.

#### Advanced Consistency Patterns (Staff-Level Deep Dive)

**Pattern 1: Causal Consistency with Logical Clocks**

Read-your-writes is just one guarantee. Full causal consistency ensures that if operation A happened before operation B, everyone sees A before B.

```
LAMPORT CLOCK (for establishing causal ordering)
───────────────────────────────────────────────
    Rules:
  1. Before each local event: clock = clock + 1
  2. On send: include clock value in message
  3. On receive: clock = max(local_clock, received_clock) + 1

VECTOR CLOCK (for detecting concurrent events)
──────────────────────────────────────────────
Each node maintains: [clock_node1, clock_node2, clock_node3, ...]

On local event: increment own position
On receive: take element-wise max, then increment own position

Compare two vectors:
  - A < B (all elements ≤, at least one <): A happened-before B
  - A > B: A happened-after B  
  - Neither: CONCURRENT (potential conflict!)

CAUSAL CONSISTENCY MANAGER
──────────────────────────
Write:
  result = leader.write(key, value)
  return {position: result.log_position}

Read(key, client_position):
  eligible_replicas = replicas WHERE position >= client_position
  IF no eligible replicas: read from leader
  ELSE: read from least-loaded eligible replica
  return {value, position}  // Client carries position forward
```

**Key Insight:** Client carries their "read position" and we ensure they never see data older than their position.

**Pattern 2: Session Consistency Across Services**

In microservices, consistency must span multiple databases:

```
CAUSAL TOKEN (passed in HTTP headers)
─────────────────────────────────────
Structure:
  positions: {service_name → log_position}  // e.g., {"user-service": 1234, "order-service": 5678}
    timestamp: float
    
Merge two tokens: take MAX position for each service

CAUSAL MIDDLEWARE (in each microservice)
────────────────────────────────────────
Before Request:
  token = decode(request.headers['X-Causal-Token'])
  required_position = token.positions[my_service_name]
  wait_until(local_db.position >= required_position)  // or timeout → use leader

After Write:
  token.positions[my_service_name] = write_result.log_position

Before Response:
  response.headers['X-Causal-Token'] = encode(token)

EXAMPLE FLOW
────────────
1. User updates profile (User Service)
   → Token: {user-service: 100}

2. User creates order (Order Service receives token)
   → Wait until Order Service replica >= 100 for user-service
   → Create order, update token: {user-service: 100, order-service: 200}

3. User views order (Order Service)
   → Guaranteed to see their own order (position 200)
```

**Pattern 3: Monotonic Reads Guarantee**

```
MONOTONIC READS ROUTER
──────────────────────
Goal: If client saw position 100, never show them position 99

Per-client state (in session/Redis):
  read_position: highest position client has seen

Route Read(client_id, key):
  min_position = get_client_position(client_id)
  
  FOR each replica:
    IF replica.position >= min_position:
                result = replica.read(key)
      update_client_position(client_id, result.position)  // high-water mark
      RETURN result
  
  // No replica caught up → use leader
  RETURN leader.read(key)

SEQUENTIAL CONSISTENCY ROUTER
─────────────────────────────
Goal: All clients see same order of operations (strongest practical guarantee)

Write(key, value):
  result = leader.write(key, value)
  global_position = result.log_position  // track latest write
  RETURN result

Read(key):
  target_position = global_position
  
  FOR each replica:
    IF replica.wait_for_position(target_position, timeout=100ms):
      RETURN replica.read(key)
  
  // Timeout → read from leader
  RETURN leader.read(key)
```

**Consistency Guarantee Comparison:**

| Guarantee | What It Means | Implementation Complexity | Performance Impact |
|-----------|--------------|--------------------------|-------------------|
| **Eventual** | All replicas converge eventually | Low | None |
| **Read-your-writes** | You see your own writes | Low | Minimal |
| **Monotonic reads** | Time never goes backwards | Medium | Low |
| **Monotonic writes** | Your writes applied in order | Medium | Low |
| **Causal** | Cause precedes effect | High | Medium |
| **Sequential** | All clients see same order | High | High |
| **Linearizable** | Real-time ordering | Very High | Very High |

#### Quick Visual: Consistency Spectrum

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONSISTENCY SPECTRUM                                     │
│                                                                             │
│   WEAKER ◄─────────────────────────────────────────────────────► STRONGER   │
│                                                                             │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│   │ Eventual │ │ Read-    │ │ Causal   │ │Sequential│ │Linearize │          │
│   │          │ │ Your-    │ │          │ │          │ │          │          │
│   │          │ │ Writes   │ │          │ │          │ │          │          │
│   └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│                                                                             │
│   Faster        ◄────────────────────────────────►        Slower            │
│   Cheaper                                                 Expensive         │
│   Available                                               Less available    │
│                                                                             │
│   USE CASES:                                                                │
│   • Analytics    • User profiles • Social feeds  • Inventory  • Banking     │
│   • Caches       • Session data  • Messaging     • Auctions   • Payments    │
│   • Metrics      • Preferences   • Comments      • Bookings   • Transfers   │
│                                                                             │
│   INTERVIEW TIP: Match consistency to business need, not technical purity   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Staff-Level Decision Matrix:**

| Use Case | Recommended Consistency | Why |
|----------|------------------------|-----|
| Social media feeds | Eventual + Read-your-writes | User sees own posts, others can lag |
| Shopping cart | Causal | Items depend on prior actions |
| Inventory count | Sequential or higher | Prevent overselling |
| Financial transactions | Linearizable | Regulatory requirements |
| Analytics/metrics | Eventual | Accuracy not critical |
| Collaborative editing | Causal + CRDTs | Order matters for merging |

---

### 1.4 Multi-Leader Replication: When You Need It (And When You Don't)

Multi-leader (or multi-master) replication allows writes to multiple nodes:

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│     ┌──────────┐                   ┌──────────┐             │
│     │ Leader A │◀────────────────▶ │ Leader B │             │
│     │  (US)    │   Bi-directional  │  (EU)    │             │
│     └──────────┘    Replication    └──────────┘             │
│          ▲                              ▲                   │
│          │                              │                   │
│     US Users                       EU Users                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Why would you want this?**

1. **Geographic latency**: Users in Europe write to Europe; users in US write to US
2. **Datacenter resilience**: Either datacenter can accept writes independently
3. **Offline operation**: Think mobile apps that sync when connectivity returns

**Why it's terrifying:**

CONFLICTS. When two leaders accept concurrent writes to the same data, you have a conflict.

```
Timeline:
─────────────────────────────────────────────────────────────▶

Leader A:    User.name = "Alice"
                    │
Leader B:    User.name = "Alicia"
                    │
                    ▼
             CONFLICT: Which value is correct?
```

**Conflict Resolution Strategies:**

| Strategy | How It Works | When to Use |
|----------|--------------|-------------|
| **Last-write-wins (LWW)** | Higher timestamp wins | Simple, accepts data loss |
| **First-write-wins** | Lower timestamp wins | Rare, specific use cases |
| **Merge** | Combine both values somehow | CRDTs, text editing |
| **Custom logic** | Application-specific resolution | Complex business rules |
| **Conflict flagging** | Mark for human resolution | Can't automate |

**The Dirty Secret:** Last-write-wins "works" but silently loses data. If Alice and Bob both edit the same document, one of their changes vanishes. Most systems using LWW don't realize how much data they're losing.

#### Deep Dive: CRDTs (Conflict-free Replicated Data Types)

CRDTs are data structures mathematically designed to always merge without conflicts. They're the "right" solution for multi-leader scenarios where conflicts are unavoidable.

##### Quick Visual: How CRDTs Work

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CRDT: CONFLICT-FREE BY DESIGN                            │
│                                                                             │
│   PROBLEM: Two datacenters increment a counter simultaneously               │
│                                                                             │
│   Regular Counter (BROKEN):         G-Counter CRDT (WORKS):                 │
│   ─────────────────────────         ─────────────────────────               │
│                                                                             │
│   US: counter = 5                   US: {US: 5, EU: 0}                      │
│   EU: counter = 3                   EU: {US: 0, EU: 3}                      │
│                                                                             │
│   US: counter++ → 6                 US: {US: 6, EU: 0}                      │
│   EU: counter++ → 4                 EU: {US: 0, EU: 4}                      │
│                                                                             │
│   Merge: counter = 6? 4? 10?        Merge: {US: 6, EU: 4} → total = 10 ✓    │
│          (lost updates!)                    (both updates preserved!)       │
│                                                                             │
│   KEY INSIGHT: Each node tracks its OWN increments                          │
│   Merge = take MAX of each node's value (idempotent, commutative)           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Common CRDT Types:**

| Type | Use Case | Merge Rule |
|------|----------|------------|
| **G-Counter** | Page views, likes | Sum of all increments |
| **PN-Counter** | Inventory, voting | Separate positive/negative counters |
| **G-Set** | Tags, follows | Union of elements |
| **OR-Set** | Mutable collections | Track adds with unique IDs |
| **LWW-Register** | Single values | Timestamp-based last-write |
| **MV-Register** | Preserve all concurrent values | Return all conflicting values |

**Example: G-Counter (Grow-only Counter)**

```
G-COUNTER (Grow-only Counter)
─────────────────────────────
    Use case: Page view counts, like counts

Structure: {node_id → count}  // Each node tracks its own increments

Increment(amount):
  counts[my_node_id] += amount

Value():
  RETURN sum(all counts)

Merge(other_counter):
  FOR each node_id in (my_nodes ∪ other_nodes):
    result[node_id] = MAX(my_count, other_count)
  RETURN result

EXAMPLE
───────
US datacenter: {us: 100, eu: 0}   // 100 likes in US
EU datacenter: {us: 0, eu: 50}    // 50 likes in EU

After merge:   {us: 100, eu: 50}  // Total = 150 ✓

Key properties:
  - Commutative: merge(A,B) = merge(B,A)
  - Associative: merge(merge(A,B),C) = merge(A,merge(B,C))
  - Idempotent: merge(A,A) = A
```

**Example: OR-Set (Observed-Remove Set)**

```
OR-SET (Observed-Remove Set)
────────────────────────────
    Use case: Shopping cart items, user follows

Key insight: Each add creates a UNIQUE version. Remove only removes 
versions we've SEEN, not future adds.

Structure:
  elements: {(value, unique_id), ...}
  tombstones: {(value, unique_id), ...}  // Removed versions

Add(value):
  elements.add((value, generate_uuid()))

Remove(value):
  to_remove = all elements WHERE element.value == value
  elements -= to_remove
  tombstones += to_remove

Merge(other):
  all_elements = my_elements ∪ other_elements
  all_tombstones = my_tombstones ∪ other_tombstones
        result.elements = all_elements - all_tombstones
  RETURN result

EXAMPLE: Shopping cart on two devices
─────────────────────────────────────
Phone adds: milk, bread    → {(milk, uuid1), (bread, uuid2)}
Laptop adds: eggs          → {(eggs, uuid3)}

Merge: {milk, bread, eggs} ✓

Phone removes milk         → tombstones: {(milk, uuid1)}
Merge again: {bread, eggs} ✓

If laptop ALSO adds milk (uuid4) after phone removed it:
Merge: {bread, eggs, milk} // uuid4 wasn't in tombstones!
```

**When to Use CRDTs:**
- Collaborative editing (Google Docs uses similar concepts)
- Distributed counters (analytics, rate limiting)
- Shopping carts across devices
- Offline-first applications

**When NOT to Use CRDTs:**
- Data with strict invariants (account balances can't use G-Counter—no decrements!)
- When you need "exactly once" semantics
- When data model doesn't fit CRDT patterns

**Staff-Level Guidance:**

Multi-leader replication is the right choice when:
- You have genuine multi-region write requirements
- Latency for writes is unacceptable across regions
- You can design your data model to avoid conflicts

Multi-leader replication is the WRONG choice when:
- You're just trying to "scale writes" (sharding is usually better)
- Your data model has significant conflict potential
- You don't have the engineering capacity to handle conflict resolution properly

**Real Example: Why Google Spanner Exists**

Google built Spanner because they needed multi-region writes with strong consistency. Instead of traditional multi-leader with conflict resolution, Spanner uses globally synchronized clocks (TrueTime) to achieve serializable transactions across regions.

This is a $100M+ engineering investment. Unless you're at Google/Amazon/Microsoft scale, you probably don't need this. Accept the limitations of leader-follower or carefully constrained multi-leader.

---

### 1.5 Read Replicas: The Practical Scaling Tool

While the theory of replication is fascinating, the practical application in 90% of systems is simple: **read replicas for read scaling**.

```
┌───────────────────────────────────────────────────────────────┐
│                         LOAD BALANCER                         │
│                                                               │
│    Writes (5%)                             Reads (95%)        │
│        │                                       │              │
│        ▼                                       ▼              │
│  ┌──────────┐                    ┌─────────────────────┐      │
│  │  LEADER  │────replication────▶│     FOLLOWERS       │      │
│  │          │                    │  ┌─────┐ ┌─────┐    │      │
│  │          │                    │  │ F1  │ │ F2  │    │      │
│  │          │                    │  └─────┘ └─────┘    │      │
│  │          │                    │  ┌─────┐ ┌─────┐    │      │
│  │          │                    │  │ F3  │ │ F4  │    │      │
│  └──────────┘                    │  └─────┘ └─────┘    │      │
│                                  └─────────────────────┘      │
└───────────────────────────────────────────────────────────────┘
```

**Capacity Planning for Read Replicas:**

```
Given:
- Current: 10,000 QPS total
- Leader capacity: 15,000 QPS
- Write ratio: 5%
- Expected growth: 3x in 12 months

Calculation:
- Current writes: 500 QPS (must all go to leader)
- Current reads: 9,500 QPS
- Projected writes: 1,500 QPS (still fits on leader)
- Projected reads: 28,500 QPS

With 4 followers @ 10,000 QPS each:
- Total read capacity: 40,000 QPS
- Headroom for projected reads: ✓ 
```

**Read Replica Pitfalls:**

1. **Connection pool exhaustion**: Each replica needs its own connection pool. 4 replicas × 100 connections = 400 connections from your application tier.

2. **Uneven replica health**: One slow replica can become a latency trap. Use active health checking, not just TCP liveness.

3. **Replication lag variance**: Not all replicas are equally caught up. Critical reads might need lag-aware routing.

```
LAG-AWARE REPLICA SELECTION
───────────────────────────
get_replica(max_acceptable_lag_ms = 1000):
  healthy = []
  
  FOR each replica:
    lag = replica.get_replication_lag_ms()
    IF lag < max_acceptable_lag_ms:
      healthy.append((replica, lag))
  
  IF healthy is empty:
    RETURN leader  // All replicas too laggy
  
  RETURN replica with minimum lag
```

---

## Part 2: Sharding — Cutting Your Data Into Manageable Pieces

### 2.1 When Replication Isn't Enough

Replication scales **reads**. It does nothing for **writes**.

If you have:
- 100,000 write operations per second
- A leader that maxes out at 20,000 WPS
- Already optimized everything possible

Replication cannot help you. Every write must still go through that single leader.

**This is where sharding enters the picture.**

Sharding (also called partitioning) splits your data across multiple independent databases, each handling a subset of the data:

```
┌─────────────────────────────────────────────────────────────────┐
│                       TOTAL DATASET                             │
│                                                                 │
│   ┌────────────┐    ┌────────────┐    ┌────────────┐            │
│   │  Shard 0   │    │  Shard 1   │    │  Shard 2   │            │
│   │            │    │            │    │            │            │
│   │ Users A-H  │    │ Users I-P  │    │ Users Q-Z  │            │
│   │            │    │            │    │            │            │
│   │  Leader    │    │  Leader    │    │  Leader    │            │
│   │     +      │    │     +      │    │     +      │            │
│   │ Followers  │    │ Followers  │    │ Followers  │            │
│   └────────────┘    └────────────┘    └────────────┘            │
│                                                                 │
│   Each shard is an independent replicated database              │
└─────────────────────────────────────────────────────────────────┘
```

**What sharding gives you:**
- Horizontal write scaling (each shard has its own leader)
- Larger total data capacity (sum of all shards)
- Independent failure domains (shard failures are partial)

**What sharding costs you:**
- Massive operational complexity
- Loss of cross-shard operations
- Potential for hot spots and imbalanced load
- Complicated application logic

---

### 2.2 The Evolution: From Single Node to Sharded System

Let me walk you through how this actually happens in the real world, because it's never a clean "let's redesign from scratch."

#### Stage 1: The Happy Single Node

```
┌─────────────────────────────────────┐
│           PostgreSQL                │
│                                     │
│  Users: 100K                        │
│  Writes: 500/sec                    │
│  Reads: 5,000/sec                   │
│  Storage: 20GB                      │
│                                     │
│  Status: Fine. Go home.             │
└─────────────────────────────────────┘
```

Everything fits on one machine. Queries are fast. Backups are simple. Life is good.

#### Stage 2: Read Scaling with Replicas

Growth happened. Reads are now at 50,000/sec, and your single node can only handle 15,000.

```
┌────────────────────────────────────────────────────────┐
│                                                        │
│         ┌───────────┐                                  │
│         │  Primary  │◄── All writes (2,000/sec)        │
│         └─────┬─────┘                                  │
│               │                                        │
│      ┌────────┼────────┐                               │
│      ▼        ▼        ▼                               │
│  ┌───────┐┌───────┐┌───────┐                           │
│  │Replica││Replica││Replica│◄── Reads distributed      │
│  └───────┘└───────┘└───────┘    (16K/sec each)         │
│                                                        │
│  Status: Stable. Can scale reads by adding replicas.   │
└────────────────────────────────────────────────────────┘
```

This works until writes become the bottleneck or storage exceeds single-node capacity.

#### Stage 3: The Uncomfortable Middle

Your primary is now handling 15,000 writes/sec (its limit), and your dataset is 2TB (getting large for a single machine). You have options:

**Option A: Vertical Scaling (Buy Bigger Machine)**
- Move to a machine with more CPU, RAM, faster disks
- Simple, no code changes
- Limits: eventually there's no bigger machine to buy

**Option B: Functional Partitioning**
- Separate different tables onto different databases
- Users on one database, Orders on another, Analytics on a third
- Works until single tables become too large

**Option C: Sharding (Horizontal Partitioning)**
- Split single tables across multiple databases
- Users 0-1M on shard 0, Users 1M-2M on shard 1, etc.
- Most complex, but truly scalable

Most teams try A, then B, then finally accept C is necessary.

#### Stage 4: Application-Level Sharding

You've decided to shard. Now the fun begins.

```
┌─────────────────────────────────────────────────────────────────┐
│                        APPLICATION                              │
│                                                                 │
│    ┌─────────────────────────────────────────────────────┐      │
│    │              SHARD ROUTER                           │      │
│    │                                                     │      │
│    │   user_id = 12345                                   │      │
│    │   shard = hash(user_id) % num_shards                │      │
│    │   shard = 12345 % 4 = 1                             │      │
│    │                                                     │      │
│    │   Route to Shard 1                                  │      │
│    └─────────────────────────────────────────────────────┘      │
│                            │                                    │
│         ┌──────────────────┼──────────────────┐                 │
│         ▼                  ▼                  ▼                 │
│    ┌─────────┐       ┌─────────┐       ┌─────────┐              │
│    │ Shard 0 │       │ Shard 1 │       │ Shard 2 │              │
│    └─────────┘       └─────────┘       └─────────┘              │
│                            ▲                                    │
│                            │                                    │
│                     user 12345 lives here                       │
└─────────────────────────────────────────────────────────────────┘
```

**The routing layer becomes critical infrastructure.** Every query must know which shard to hit. This is typically embedded in your application or abstracted into a proxy layer.

---

### 2.3 Sharding Strategies: The Big Three

#### Quick Visual: The Three Sharding Strategies at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SHARDING STRATEGY COMPARISON                             │
│                                                                             │
│   HASH-BASED                    RANGE-BASED                 DIRECTORY       │
│   ───────────                   ───────────                 ─────────       │
│                                                                             │
│   shard = hash(key) % N         shard = lookup_range(key)   shard = dir[key]│
│                                                                             │
│   ┌─┬─┬─┬─┐                     ┌─────┬─────┬─────┐         ┌─────────────┐ │
│   │0│1│2│3│ ← distributed       │ A-H │ I-P │ Q-Z │         │ key → shard │ │
│   └─┴─┴─┴─┘   evenly            └─────┴─────┴─────┘         │ usr1 → 0    │ │
│                                        ↑ ordered            │ usr2 → 2    │ │
│   ✓ Even distribution           ✓ Range queries             │ vip1 → 5    │ │
│   ✓ Simple                      ✓ Easy splits               └─────────────┘ │
│   ✗ No range queries            ✗ Hot spots                 ✓ Full control  │
│   ✗ Reshard = chaos             ✗ Uneven load               ✗ Extra lookup  │
│                                                              ✗ SPOF risk    │
│                                                                             │
│   Best for: Point queries       Best for: Time-series       Best for: VIPs  │
│             User lookups                   Logs, events              Tenants│
│             Session data                   Analytics                 Custom │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Strategy 1: Hash-Based Sharding

```
get_shard(key, num_shards):
  RETURN hash(key) MOD num_shards
```

**How it works:**
- Hash the partition key (e.g., user_id)
- Modulo by number of shards
- Deterministically routes to a shard

**Pros:**
- Even distribution (if hash is good)
- No lookup table needed
- Simple to implement

**Cons:**
- Range queries require scatter-gather (hit all shards)
- Adding shards requires massive data movement
- Hash collisions in the algorithm aren't hash collisions in data—it's about distribution

**When to use:**
- Point queries are dominant (get user by ID)
- Data doesn't need to be queried by range
- You want simplicity over optimization

**Critical Detail: Consistent Hashing**

Simple modulo hashing has a fatal flaw. When you add a shard:

```
Before: hash(key) % 3 = 0, 1, or 2
After:  hash(key) % 4 = 0, 1, 2, or 3

Key "user_123" might have been on shard 0, now goes to shard 3.
Most keys move to different shards!
```

**Consistent hashing** solves this by only moving ~1/N keys when adding a shard:

```
┌───────────────────────────────────────────────────────────┐
│                     HASH RING                             │
│                                                           │
│                         0°                                │
│                         │                                 │
│                    Shard 0                                │
│                   /         \                             │
│                  /           \                            │
│           270° ─┤   Keys     ├─ 90°                       │
│                  \  mapped   /  Shard 1                   │
│                   \ to ring /                             │
│                    Shard 2                                │
│                         │                                 │
│                       180°                                │
│                                                           │
│   Key placement: walk clockwise to find owning shard      │
└───────────────────────────────────────────────────────────┘
```

Adding a shard only affects keys between it and its neighbor, not the entire keyspace.

**Deep Dive: Consistent Hashing Implementation**

The diagram above is conceptual. Here's how it actually works in production:

```
CONSISTENT HASH RING WITH VIRTUAL NODES
───────────────────────────────────────
Structure:
  ring: {hash_position → physical_node}
  sorted_keys: [sorted list of all hash positions]
  virtual_nodes: 150 per physical node (for even distribution)

Add Node(node):
  FOR i = 0 to virtual_nodes:
    hash_position = hash(node + ":vn" + i)
    ring[hash_position] = node
    insert hash_position into sorted_keys

Remove Node(node):
  FOR i = 0 to virtual_nodes:
    hash_position = hash(node + ":vn" + i)
    delete ring[hash_position]
    remove from sorted_keys

Get Node(key):
  key_hash = hash(key)
  // Find first node position >= key_hash (walk clockwise)
  idx = binary_search(sorted_keys, key_hash)
  IF idx >= length(sorted_keys): idx = 0  // Wrap around
  RETURN ring[sorted_keys[idx]]

Get Nodes(key, count=3):  // For replication
  start_idx = binary_search(sorted_keys, hash(key))
  nodes = []
  
  FOR i = 0 to length(sorted_keys):
    pos = (start_idx + i) % length(sorted_keys)
    node = ring[sorted_keys[pos]]
    IF node NOT IN nodes:
      nodes.append(node)
    IF length(nodes) >= count: BREAK
  
  RETURN nodes

EXAMPLE
───────
ring = new ConsistentHashRing(["shard-0", "shard-1", "shard-2", "shard-3"])
shard = ring.get_node("user_12345")  // → "shard-2"

ring.add_node("shard-4")  // Only ~20% of keys move (not 80%!)
replicas = ring.get_nodes("user_12345", count=3)  // → ["shard-2", "shard-0", "shard-4"]
```

**Why Virtual Nodes Matter:**

```
Without virtual nodes (4 physical nodes):
─────────────────────────────────────────────────────────────────────────
Hash Ring: 0────────────────────────────────────────────────────────MAX

           S0              S1                    S2          S3
            │               │                     │           │
Uneven! S2 owns ~40% of keyspace, S3 owns only ~15%
```

```
With 150 virtual nodes per physical node (600 total positions):
─────────────────────────────────────────────────────────────────────────
Hash Ring: 0────────────────────────────────────────────────────────MAX

S0 S2 S1 S3 S0 S2 S1 S0 S3 S2 S1 S0 S3 S2 S1 S3 S0 S2 S1 S0 S3...

Distribution approaches 25% per node (statistically even)
```

**Production Considerations:**

| Setting | Recommendation | Why |
|---------|----------------|-----|
| Virtual nodes | 100-200 per physical node | Balances memory vs. distribution |
| Hash function | MD5 or MurmurHash3 | Fast, good distribution |
| Replication factor | 3 | Survives 2 failures |
| Node naming | Include rack/AZ info | Avoid replicas on same rack |

---

#### Strategy 2: Range-Based Sharding

```
SHARD_RANGES = [
  (0 - 1,000,000) → shard_0
  (1,000,001 - 2,000,000) → shard_1
  (2,000,001 - 3,000,000) → shard_2
]

get_shard(user_id):
  for each (start, end, shard) in SHARD_RANGES:
    if start <= user_id <= end:
      RETURN shard
```

**How it works:**
- Divide keyspace into ranges
- Each shard owns a contiguous range
- Lookup table maps ranges to shards

**Pros:**
- Range queries are efficient (only hit relevant shards)
- Easy to split hot shards (divide range)
- Intuitive for ordered data

**Cons:**
- Prone to hot spots (recent users on one shard)
- Requires maintaining range mapping
- Uneven distribution if access patterns are skewed

**When to use:**
- Range queries are common
- Data has natural ordering (time, alphabetical)
- You can monitor and rebalance as needed

**Example: Time-Based Range Sharding**

```
┌────────────────────────────────────────────────────────────┐
│                   EVENTS TABLE                             │
│                                                            │
│  Shard 0: events from 2023-01 to 2023-04                   │
│  Shard 1: events from 2023-05 to 2023-08                   │
│  Shard 2: events from 2023-09 to 2023-12                   │
│  Shard 3: events from 2024-01 onwards (ACTIVE)             │
│                                                            │
│  Query: "events from last week"                            │
│  → Only hits Shard 3 ✓                                     │
│                                                            │
│  Query: "events from March 2023"                           │
│  → Only hits Shard 0 ✓                                     │
│                                                            │
│  Problem: Shard 3 gets ALL current writes                  │
│           (hot spot)                                       │
└────────────────────────────────────────────────────────────┘
```

---

#### Strategy 3: Hybrid (Directory-Based) Sharding

```
SHARD DIRECTORY
───────────────
mapping: {key → shard}  // Loaded from database/cache

get_shard(key):
  RETURN mapping[key]

set_shard(key, shard):
  mapping[key] = shard
```

**How it works:**
- Maintain explicit mapping of keys to shards
- Lookup table stored in fast storage (Redis, dedicated DB)
- Complete flexibility in placement

**Pros:**
- Total control over data placement
- Easy to move individual keys between shards
- Can implement custom balancing logic

**Cons:**
- Lookup table is critical dependency
- Additional latency for directory lookup
- Complexity in maintaining directory

**When to use:**
- Highly variable data sizes (large tenants need dedicated shards)
- Complex placement requirements
- VIP tenant isolation

**Real Example: Multi-Tenant SaaS**

```
┌────────────────────────────────────────────────────────────┐
│                  SHARD DIRECTORY                           │
│                                                            │
│  Tenant "small_co_1"     → Shard 0 (shared)                │
│  Tenant "small_co_2"     → Shard 0 (shared)                │
│  Tenant "small_co_3"     → Shard 0 (shared)                │
│  Tenant "medium_corp"    → Shard 1 (shared)                │
│  Tenant "enterprise_inc" → Shard 2 (DEDICATED)             │
│  Tenant "whale_co"       → Shard 3 (DEDICATED)             │
│                                                            │
│  Enterprise and Whale get dedicated shards for:            │
│  - Performance isolation                                   │
│  - Compliance requirements                                 │
│  - Custom SLAs                                             │
└────────────────────────────────────────────────────────────┘
```

#### Advanced Hybrid Sharding Patterns (Staff-Level Deep Dive)

**Pattern 1: Compound Shard Keys**

Single-dimension sharding often fails. Compound keys solve multiple access patterns.

```
COMPOUND SHARD KEY (E-commerce Example)
───────────────────────────────────────
Access patterns:
  Primary:   "Get all orders for user X"      → Fast (single shard)
  Secondary: "Get all orders for merchant Y"  → Slower (scatter-gather)

Sharding: by user_id (co-locates all user's orders)
Secondary index: merchant_id → [(shard, order_id), ...]

get_shard_for_order(user_id, order_id):
  RETURN hash(user_id) % num_shards

store_order(order):
  shard = get_shard_for_order(order.user_id)
  shards[shard].insert(order)
  merchant_index[order.merchant_id].append((shard, order.order_id))

get_user_orders(user_id):     // FAST: single shard
  shard = get_shard_for_order(user_id)
  RETURN shards[shard].query("user_id = ?", user_id)

get_merchant_orders(merchant_id):  // SLOW: scatter-gather
  locations = merchant_index[merchant_id]
  group locations by shard
  batch-fetch from each shard
  RETURN merged results


HIERARCHICAL COMPOUND KEY (Slack-like Chat)
───────────────────────────────────────────
Hierarchy: Organization → Workspace → Channel → Message

Sharding: by (org_id, workspace_id) → co-locates all workspace data
Within-shard partitioning: by channel_id (for parallelism)

get_shard(org_id, workspace_id):
  RETURN hash(org_id + ":" + workspace_id) % num_shards

get_partition(channel_id):
  RETURN hash(channel_id) % 16  // 16 partitions per shard

get_messages(org_id, workspace_id, channel_id):
  shard = get_shard(org_id, workspace_id)  // Single shard!
  partition = get_partition(channel_id)
  RETURN query(shard, partition, "channel_id = ?")

get_workspace_activity(org_id, workspace_id):
  shard = get_shard(org_id, workspace_id)  // Still single shard!
  RETURN parallel_query_all_partitions(shard)
```

**Pattern 2: Geographic + Hash Hybrid**

```
GEOGRAPHIC + HASH HYBRID SHARDING
─────────────────────────────────
Use when: GDPR, data residency, latency optimization

Two-level sharding:
  Level 1: Geographic region
  Level 2: Hash within region

REGIONS = {
  'us-east':     [shard-us-0, shard-us-1, shard-us-2, shard-us-3],
  'eu-west':     [shard-eu-0, shard-eu-1, shard-eu-2, shard-eu-3],
  'ap-southeast':[shard-ap-0, shard-ap-1, shard-ap-2, shard-ap-3],
}

get_shard(user_id, user_region):
  region = user_region OR user_region_cache[user_id] OR default('us-east')
  region_shards = REGIONS[region]
  shard_index = hash(user_id) % length(region_shards)
  RETURN region_shards[shard_index]

migrate_user_region(user_id, old_region, new_region):
  // GDPR right to data portability!
  old_shard = get_shard(user_id, old_region)
  new_shard = get_shard(user_id, new_region)
  
  user_data = shards[old_shard].export_user(user_id)
  shards[new_shard].import_user(user_id, user_data)
  user_region_cache[user_id] = new_region
  shards[old_shard].delete_user(user_id)  // GDPR compliance

cross_region_query(user_ids):
  group user_ids by region
  query each region in parallel
  merge results
```

**Pattern 3: Time-Based + Hash Hybrid (Time-Series Data)**

```
TIME + HASH HYBRID SHARDING
───────────────────────────
Use for: Event logs, metrics, analytics, data with TTL

Two-level sharding:
  Level 1: Time partition (e.g., monthly)
  Level 2: Hash within partition

get_partition_id(timestamp):
  RETURN timestamp.format("YYYY-MM")  // e.g., "2024-01"

get_shard(entity_id, timestamp):
  partition = get_partition_id(timestamp)
  shard_index = hash(entity_id) % shards_per_partition
  RETURN "events-{partition}-shard-{shard_index}"

write_event(entity_id, event):
  shard = get_shard(entity_id, now())
  ensure_partition_exists(partition)
  shards[shard].insert({event, entity_id, timestamp})

query_entity_events(entity_id, start_time, end_time):
  results = []
  FOR each partition in time range:
    shard = get_shard(entity_id, partition_start)  // Only 1 shard per partition!
    results += query(shard, entity_id, time_filter)
  RETURN sorted(results, by timestamp)

query_time_range(start_time, end_time):  // All entities
  results = []
  FOR each partition in time range:
    FOR each shard in partition:  // Scatter-gather WITHIN partition
      results += query(shard, time_filter)
  RETURN results

cleanup_old_partitions(retention_days = 365):
  cutoff = now() - retention_days
  FOR each partition older than cutoff:
    drop all shards in partition  // Easy TTL!
```

**Key benefit:** Range queries hit fewer shards, TTL cleanup is trivial (drop entire partitions).

**Pattern 4: Tiered Sharding (Hot/Warm/Cold)**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      TIERED SHARDING ARCHITECTURE                       │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                        HOT TIER                                 │   │
│   │   Last 24 hours | NVMe SSDs | 8 shards | In-memory caching      │   │
│   │                                                                 │   │
│   │   Fast reads, fast writes, high cost                            │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                            │ Age out after 24h                          │
│                            ▼                                            │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                        WARM TIER                                │   │
│   │   Last 30 days | Standard SSDs | 16 shards | Read replicas      │   │
│   │                                                                 │   │
│   │   Good read performance, moderate cost                          │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                            │ Age out after 30 days                      │
│                            ▼                                            │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                        COLD TIER                                │   │
│   │   Historical | HDDs/Object storage | 32 shards | Compressed     │   │
│   │                                                                 │   │
│   │   Slow reads, low cost, archival queries only                   │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

```
TIERED SHARD ROUTER
───────────────────
Tiers:
  HOT  (< 24 hours):  8 shards, NVMe SSDs, in-memory cache
  WARM (< 30 days):   16 shards, standard SSDs
  COLD (> 30 days):   32 shards, HDDs/object storage, compressed

get_tier(timestamp):
  age = now() - timestamp
  IF age < 24 hours: RETURN 'hot'
  IF age < 30 days:  RETURN 'warm'
  ELSE:              RETURN 'cold'

route_write(entity_id):
  // Writes ALWAYS go to hot tier
  shard_index = hash(entity_id) % 8
  RETURN "hot-shard-{shard_index}"

route_read(entity_id, timestamp):
  tier = get_tier(timestamp)
  num_shards = 8 if hot, 16 if warm, 32 if cold
  shard_index = hash(entity_id) % num_shards
  RETURN "{tier}-shard-{shard_index}"

age_out_data():  // Background job
  migrate data older than 24 hours: hot → warm
  migrate data older than 30 days:  warm → cold
```

**Choosing the Right Hybrid Strategy:**

| Access Pattern | Recommended Strategy | Why |
|----------------|---------------------|-----|
| User + Time queries | Compound (user_id, timestamp) | Co-locate user data, time-ordered |
| Multi-tenant SaaS | Directory + Hash | Tenant isolation, flexible placement |
| Global users | Geographic + Hash | Data residency, latency |
| Time-series analytics | Time + Hash | Efficient range queries, TTL |
| Mixed hot/cold data | Tiered | Cost optimization |
| Chat/Messaging | Hierarchical compound | Org→Workspace→Channel locality |

---

### 2.4 Hot Partitions and Skew: When Theory Meets Reality

#### Quick Visual: Why Hot Partitions Happen

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE FOUR TYPES OF SKEW                                   │
│                                                                             │
│   DATA SKEW                              ACCESS SKEW                        │
│   ─────────                              ───────────                        │
│   Some keys have MORE data               Some keys get MORE requests        │
│                                                                             │
│   ┌──────┐ ┌──────┐ ┌──────┐            ┌──────┐ ┌──────┐ ┌──────┐          │
│   │██████│ │██    │ │██    │            │→→→→→→│ │→     │ │→     │          │
│   │██████│ │██    │ │██    │            │→→→→→→│ │      │ │      │          │
│   │██████│ │      │ │      │            │→→→→→→│ │      │ │      │          │
│   └──────┘ └──────┘ └──────┘            └──────┘ └──────┘ └──────┘          │
│   Shard 0   Shard 1  Shard 2            Shard 0   Shard 1  Shard 2          │
│   (too big)                              (overloaded)                       │
│                                                                             │
│   TEMPORAL SKEW                          POPULARITY SKEW                    │
│   ─────────────                          ────────────────                   │
│   Recent data is HOT                     Celebrity/viral content            │
│                                                                             │
│   ┌──────┐ ┌──────┐ ┌──────┐            Celebrity posts to 50M followers    │
│   │ 2024 │ │ 2023 │ │ 2022 │            All 50M writes → same shard         │
│   │ HOT! │ │ warm │ │ cold │            Your "evenly distributed" system    │
│   └──────┘ └──────┘ └──────┘            is now 99% focused on one shard     │
│                                                                             │
│   SOLUTION: Salting, caching, dedicated infrastructure, or redesign         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

You've carefully designed your sharding scheme. You launch. And then:

```
Shard Utilization After 1 Month:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Shard 0:  ████████████░░░░░░░░  60%
Shard 1:  ██████████████████░░  90%  ← HOT
Shard 2:  ████████░░░░░░░░░░░░  40%
Shard 3:  ████░░░░░░░░░░░░░░░░  20%

Shard 1 is dying. The others are bored.
```

**Why does this happen?**

1. **Data skew**: Some partition keys have way more data than others
2. **Access skew**: Some partition keys are accessed way more frequently
3. **Temporal skew**: Recent data is always hotter than old data
4. **Popularity skew**: Celebrity accounts, viral content, etc.

**The Celebrity Problem:**

```
User ID 1234 is a celebrity with 50 million followers
Every post creates 50 million fan-out events
All targeting shard = hash(1234) % 4 = 2

Shard 2 is now processing 50M events
while other shards process thousands

Your "evenly distributed" system is now 99% focused on shard 2
```

**Solutions to Hot Partitions:**

| Approach | Description | Trade-off |
|----------|-------------|-----------|
| **Salting** | Add random suffix to hot keys | Scatter-gather for reads |
| **Split hot shards** | Subdivide overloaded shards | Operational complexity |
| **Rate limiting** | Throttle hot keys | User experience impact |
| **Caching** | Cache hot key responses | Cache invalidation |
| **Dedicated infrastructure** | Hot keys get special handling | Cost, complexity |

**Salting Implementation:**

```
WITHOUT SALTING
───────────────
get_shard(user_id):
  RETURN hash(user_id) % num_shards  // Always same shard

WITH SALTING FOR HOT KEYS
─────────────────────────
get_shard_salted(user_id, is_celebrity):
  IF is_celebrity:
    salt = random(0, 9)  // Distribute across shards
    RETURN hash("{user_id}_{salt}") % num_shards
  RETURN hash(user_id) % num_shards

// Reading requires scatter-gather for celebrities
get_all_data_for_celebrity(user_id):
  results = []
  FOR salt = 0 to 9:
    shard = hash("{user_id}_{salt}") % num_shards
    results += query_shard(shard, user_id, salt)
  RETURN results
```

**Staff-Level Insight:** The best solution to hot partitions is often domain-specific. Don't reach for generic solutions immediately. Understand WHY your partition is hot and design accordingly.

For example: If celebrity posts are hot because of fan-out, maybe the answer isn't better sharding—it's redesigning fan-out to be pull-based instead of push-based.

#### Advanced Hot Partition Mitigation (Staff-Level Deep Dive)

**Technique 1: Request Coalescing for Hot Keys**

```
REQUEST COALESCING
──────────────────
Problem: 1000 concurrent requests for 'celebrity_123'
Solution: Only ONE database query, share result with all 1000

get(key):
  IF key in pending_requests:
    RETURN await pending_requests[key]  // Wait for existing fetch
  
  // We're the first request for this key
  pending_requests[key] = new_future()
  
  TRY:
    result = await db.get(key)  // Only ONE query
    pending_requests[key].set_result(result)
    RETURN result
  FINALLY:
    sleep(coalesce_window_ms)  // Allow more requests to batch
    delete pending_requests[key]


BATCHING COALESCER
──────────────────
Problem: 100 separate GET requests = 100 round trips
Solution: Batch into MGET = 1 round trip

get(key):
  add key to pending_keys
  pending_futures[key] = new_future()
  
  IF length(pending_keys) >= batch_size OR timeout_elapsed:
    execute_batch()
  
  RETURN await pending_futures[key]

execute_batch():
  keys = pending_keys.copy()
  pending_keys.clear()
  
  results = db.MGET(keys)  // Single round-trip!
  
  FOR each (key, result):
    pending_futures[key].set_result(result)
```

**Technique 2: Adaptive Load Shedding**

```
ADAPTIVE LOAD SHEDDER
─────────────────────
Goal: Progressively reject requests as shard becomes overloaded

State:
  latencies: sliding window of last 100 request latencies
  rejection_rate: 0.0 to 0.9

record_latency(latency_ms):
  latencies.append(latency_ms)
  update_rejection_rate()

update_rejection_rate():
  avg_latency = average(latencies)
  
  IF avg_latency <= target_latency (e.g., 50ms):
    rejection_rate -= 0.05  // Reduce rejection
  ELSE IF avg_latency >= max_latency (e.g., 200ms):
    rejection_rate += 0.10  // Increase rejection (max 0.9)
  ELSE:
    // Proportional adjustment
    overload_ratio = (avg_latency - target) / (max - target)
    rejection_rate = 0.9 * rejection_rate + 0.1 * (overload_ratio * 0.5)

should_accept(priority):  // priority 1=highest, 10=lowest
  IF rejection_rate == 0: RETURN True
  
  // High priority = less likely to reject
  adjusted_rate = rejection_rate * (priority / 10)
  RETURN random() > adjusted_rate

EXAMPLE
───────
Shard at 120ms avg latency (overloaded):
  - Priority 1 (admin):     ~10% rejection
  - Priority 5 (normal):    ~50% rejection  
  - Priority 10 (background): ~100% rejection
```

**Technique 3: Automated Shard Splitting**

```
AUTOMATIC SHARD SPLITTER
────────────────────────
Thresholds:
  load_threshold: 85% capacity
  duration_threshold: 5 minutes sustained
  cooldown: 1 hour between splits

check_and_split():  // Called by background job
  FOR each shard:
    IF should_split(shard):
      initiate_split(shard)

should_split(shard):
  IF time_since_last_split < cooldown: RETURN False
  IF already_splitting: RETURN False
  IF sustained_high_load > duration_threshold: RETURN True
  RETURN False

execute_split(shard):
  state = PREPARING
  
  // 1. Create new shard
  new_shard = create_shard()
  
  // 2. Find split point (median key)
  split_key = find_median_key(shard.sample_keys(1000))
  
  // 3. Start double-writing (new writes go to both)
  enable_shadow_write(shard, new_shard, keys > split_key)
  
  state = COPYING
  // 4. Copy historical data (keys > split_key)
  FOR each batch in shard.scan():
    copy filtered batch to new_shard
  
  // 5. Verify integrity
  IF NOT verify_sample(source, target, split_key):
    ROLLBACK and ALERT
  
  state = SWITCHING
  // 6. Update routing
  router.split_shard(shard, new_shard, split_key)
  
  // 7. Cleanup
  delete moved keys from old shard
  state = COMPLETED
```

**Technique 4: Write-Behind Caching for Hot Keys**

```
WRITE-BEHIND CACHE
──────────────────
Trade-off: Fast writes, but risk data loss if cache fails before flush

get(key):
  value = cache.get(key)
  IF value exists: RETURN value
  
  value = db.get(key)
  cache.set(key, value)
  RETURN value

set(key, value):
  cache.set(key, value)  // Immediate
  write_queue.add((key, value, timestamp))  // Async

increment(key, amount):
  new_value = cache.incr(key, amount)  // Fast, in-memory
  
  // Sync to DB periodically, not every increment
  IF new_value % 100 == 0:
    write_queue.add((key, new_value, timestamp))
  
  RETURN new_value

// Background thread
flush_loop():
  WHILE True:
    batch = collect_from_queue(timeout=flush_interval)
    
    IF length(batch) >= batch_size OR timeout_elapsed:
      flush_batch(batch)

flush_batch(batch):
  // Deduplicate: keep only latest write per key
  latest = {}
  FOR each (key, value, timestamp) in batch:
    IF timestamp > latest[key].timestamp:
      latest[key] = value
  
  db.MSET(latest)  // Single batch write

flush_sync():  // Called on shutdown
  flush all pending writes immediately
```

---

### 2.5 Re-Sharding: The Migration Everyone Dreads

The day will come when your sharding scheme no longer works:
- You need more shards (growth)
- You need fewer shards (consolidation)
- Your partition key was wrong (design error)
- Hot spots require rebalancing

#### Quick Visual: Migration Strategy Comparison

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RESHARDING MIGRATION STRATEGIES                          │
│                                                                             │
│   DOUBLE-WRITE                  GHOST TABLES                  READ-THROUGH  │
│   ────────────                  ────────────                  ────────────  │
│                                                                             │
│   ┌─────────┐                   ┌─────────┐                   ┌─────────┐   │
│   │  Write  │                   │  Write  │                   │  Read   │   │
│   └────┬────┘                   └────┬────┘                   └────┬────┘   │
│        │                             │                             │        │
│   ┌────┴────┐                   ┌────▼────┐                   ┌────▼────┐   │
│   ▼         ▼                   │ Capture │                   │  New?   │   │
│ Old       New                   │ Changes │                   └────┬────┘   │
│ Shard    Shard                  └────┬────┘                   Yes  │  No    │
│   │         │                        │                         ▼   │   ▼    │
│   │   + Backfill old data       Copy + Apply                Return │  Old   │
│   │   + Verify parity           in batches                         │ Shard  │
│   │   + Switch reads                 │                             │   │    │
│   │   + Stop old writes         Brief pause                   Copy to new   │
│   │                             + Cutover                     Return data   │
│                                                                             │
│   Downtime: Zero                Downtime: Seconds             Downtime: Zero│
│   Duration: Days-Weeks          Duration: Hours               Duration: Lazy│
│   Risk: Double load             Risk: Change capture          Risk: Slow    │
│                                                                             │
│   BEST FOR:                     BEST FOR:                     BEST FOR:     │
│   Large datasets                Schema changes                Low-priority  │
│   Can afford 2x resources       Need speed                    Can wait      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**The Challenge:**

```
Current: 4 shards
Target:  8 shards

During migration:
- System must stay online
- Reads must return correct data
- Writes must not be lost
- Consistency must be maintained
```

**Migration Strategies:**

#### Strategy 1: Double-Write Migration

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: Start double-writing                              │
│                                                             │
│     Write ──┬──▶ Old shard (source of truth)                │
│             └──▶ New shard (building up)                    │
│                                                             │
│  Phase 2: Backfill historical data                          │
│                                                             │
│     Old shard ──copy──▶ New shard                           │
│                                                             │
│  Phase 3: Verify parity                                     │
│                                                             │
│     Compare old and new shards                              │
│                                                             │
│  Phase 4: Switch reads                                      │
│                                                             │
│     Reads ──▶ New shard                                     │
│                                                             │
│  Phase 5: Stop old writes, decommission old shards          │
└─────────────────────────────────────────────────────────────┘
```

**Pros:** Zero downtime, can rollback easily
**Cons:** 2x write load, 2x storage during migration, complex coordination

#### Strategy 2: Ghost Tables (Online Schema Change Pattern)

```
ONLINE RESHARDING (inspired by GitHub's gh-ost)
───────────────────────────────────────────────
migrate():
  1. create_new_shards()
  
  2. start_change_capture()  // binlog/CDC
  
  3. FOR each batch of existing data:
       copy_batch(batch)
       apply_captured_changes()  // Keep up with writes during copy
  
  4. // Final cutover
     pause_writes()  // Brief pause (seconds)
     apply_remaining_changes()
     switch_traffic()
     resume_writes()
```

**Pros:** Minimal downtime (seconds), battle-tested pattern
**Cons:** Requires change data capture, complex implementation

#### Strategy 3: Gradual Migration with Read-Through

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   Read Request                                              │
│        │                                                    │
│        ▼                                                    │
│   ┌─────────────────────────────────────────────┐           │
│   │           MIGRATION PROXY                   │           │
│   │                                             │           │
│   │  1. Check new shard                         │           │
│   │     - Found? Return it                      │           │
│   │     - Not found? Continue                   │           │
│   │                                             │           │
│   │  2. Check old shard                         │           │
│   │     - Found? Migrate to new, return it      │           │
│   │     - Not found? Return 404                 │           │
│   │                                             │           │
│   └─────────────────────────────────────────────┘           │
│        │                   │                                │
│        ▼                   ▼                                │
│   ┌─────────┐        ┌─────────┐                            │
│   │   New   │◀─copy──│   Old   │                            │
│   │ Shards  │        │ Shards  │                            │
│   └─────────┘        └─────────┘                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Pros:** Lazy migration, no big-bang cutover
**Cons:** Extended migration period, read latency penalty

---

### 2.6 Cross-Shard Operations: The Hardest Problem

Sharding breaks joins, transactions, and aggregations. Here's how to handle each.

#### Quick Visual: Cross-Shard Operation Patterns

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CROSS-SHARD OPERATIONS                                   │
│                                                                             │
│   THE PROBLEM                                                               │
│   ───────────                                                               │
│   Query: SELECT * FROM orders JOIN users ON orders.user_id = users.id       │
│          WHERE order_date > '2024-01-01'                                    │
│                                                                             │
│          Orders on Shard 0-3          Users on Shard 4-7                    │
│          ┌───┐ ┌───┐ ┌───┐ ┌───┐     ┌───┐ ┌───┐ ┌───┐ ┌───┐                │
│          │ O │ │ O │ │ O │ │ O │  ?  │ U │ │ U │ │ U │ │ U │                │
│          └───┘ └───┘ └───┘ └───┘     └───┘ └───┘ └───┘ └───┘                │
│                      Can't join across shards!                              │
│                                                                             │
│   THE SOLUTIONS                                                             │
│   ─────────────                                                             │
│                                                                             │
│   1. DENORMALIZE           2. APP-LEVEL JOINS        3. SCATTER-GATHER      │
│      Store user_name          Fetch orders              Query all shards    │
│      in orders table          Then fetch users          Merge results       │
│                               Then merge in app                             │
│      ✓ Fast reads             ✓ Normalized data       ✓ Any query           │
│      ✗ Update complexity      ✗ Multiple round-trips  ✗ Slow, expensive     │
│      ✗ Storage cost           ✗ App complexity        ✗ N+1 problem         │
│                                                                             │
│   BEST PRACTICE: Co-locate related data on same shard when possible         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Problem 1: Cross-Shard Joins

```
Query: SELECT orders.*, users.name 
       FROM orders 
       JOIN users ON orders.user_id = users.id
       WHERE orders.created_at > '2024-01-01'

Problem: orders and users are on different shards!
```

**Solution A: Denormalization**

Store redundant data to avoid joins:

```
DENORMALIZED ORDER
──────────────────
Order {
  id, user_id,
  user_name,   // Copied from users table
  user_email,  // Copied from users table
  total, created_at
}

update_user_name(user_id, new_name):
  users_shard.update(user_id, name=new_name)
  
  // Async update all orders (expensive!)
  FOR each order in orders_by_user(user_id):
    orders_shard.update(order.id, user_name=new_name)
```

**Trade-off:** Storage cost for query simplicity. Updates become expensive.

**Solution B: Application-Level Joins**

```
APPLICATION-LEVEL JOIN
──────────────────────
get_orders_with_users(start_date):
  // Step 1: Scatter - query orders from all shards
  orders = []
  FOR each shard in order_shards:
    orders += shard.query("SELECT * FROM orders WHERE created_at > ?", start_date)
  
  // Step 2: Collect unique user_ids
  user_ids = unique(order.user_id for order in orders)
  
  // Step 3: Batch fetch users (group by shard for efficiency)
  users_by_id = {}
  FOR each user_id in user_ids:
    shard = get_user_shard(user_id)
    users_by_id[user_id] = shard.get_user(user_id)
  
  // Step 4: Join in application memory
  FOR each order in orders:
    order.user = users_by_id[order.user_id]
  
  RETURN orders
```

**Trade-off:** Multiple round-trips, more code, but data stays normalized.

#### Problem 2: Cross-Shard Transactions

```
Scenario: Transfer $100 from User A (Shard 0) to User B (Shard 2)

Must be atomic: either both happen or neither happens.
```

##### Quick Visual: 2PC vs Saga Pattern

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              TWO-PHASE COMMIT (2PC)          vs          SAGA PATTERN       │
│                                                                             │
│   ┌──────────────┐                           ┌──────────────┐               │
│   │ Coordinator  │                           │ Orchestrator │               │
│   └──────┬───────┘                           └──────┬───────┘               │
│          │                                          │                       │
│   Phase 1: PREPARE                           Step 1: Deduct from A          │
│   "Can you commit?"                                 │                       │
│          │                                          ▼                       │
│     ┌────┴────┐                              ┌─────────────┐                │
│     ▼         ▼                              │ Success?    │                │
│  Shard A   Shard B                           └──────┬──────┘                │
│  "Yes!"    "Yes!"                             Yes   │   No → Stop           │
│     │         │                                     ▼                       │
│     └────┬────┘                              Step 2: Add to B               │
│          │                                          │                       │
│   Phase 2: COMMIT                                   ▼                       │
│   "Do it!"                                   ┌─────────────┐                │
│          │                                   │ Success?    │                │
│     ┌────┴────┐                              └──────┬──────┘                │
│     ▼         ▼                               Yes   │   No → COMPENSATE     │
│  Shard A   Shard B                            Done  │   (Add back to A)     │
│  Commit!   Commit!                                  ▼                       │
│                                                   Done                      │
│                                                                             │
│   ✓ Strong consistency                       ✓ Better availability          │
│   ✗ Blocking (coordinator SPOF)              ✗ Eventual consistency         │
│   ✗ 2+ round trips                           ✗ Complex compensation         │
│                                                                             │
│   Use for: Financial, regulated              Use for: E-commerce, bookings  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Solution A: Two-Phase Commit (2PC)**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        TWO-PHASE COMMIT                                 │
│                                                                         │
│  PHASE 1: PREPARE                                                       │
│  ─────────────────                                                      │
│                                                                         │
│     Coordinator ──prepare──▶ Shard 0: "Can you deduct $100 from A?"     │
│                  ──prepare──▶ Shard 2: "Can you add $100 to B?"         │
│                                                                         │
│     Shard 0 ──vote YES──▶ Coordinator                                   │
│     Shard 2 ──vote YES──▶ Coordinator                                   │
│                                                                         │
│  PHASE 2: COMMIT                                                        │
│  ───────────────                                                        │
│                                                                         │
│     Coordinator ──commit──▶ Shard 0: "Do it"                            │
│                  ──commit──▶ Shard 2: "Do it"                           │
│                                                                         │
│     Both shards commit their prepared transactions                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

```
TWO-PHASE COMMIT
────────────────
transfer(from_user, to_user, amount):
  txn_id = generate_txn_id()
  from_shard = get_user_shard(from_user)
  to_shard = get_user_shard(to_user)
  
  // PHASE 1: PREPARE
  TRY:
    from_shard.prepare(txn_id, "deduct $amount from from_user")
    to_shard.prepare(txn_id, "add $amount to to_user")
  CATCH:
    from_shard.abort(txn_id)
    to_shard.abort(txn_id)
    THROW TransactionAborted
  
  // PHASE 2: COMMIT
  // Participants promised in prepare → MUST succeed
  from_shard.commit(txn_id)
  to_shard.commit(txn_id)
  
  RETURN Success
```

**2PC Problems:**
- Blocking: If coordinator dies, participants are stuck
- Latency: 2 round-trips minimum
- Coordinator is SPOF

**Solution B: Saga Pattern (Eventual Consistency)**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           SAGA PATTERN                                  │
│                                                                         │
│  Forward transactions (try each step):                                  │
│  ─────────────────────────────────────                                  │
│                                                                         │
│     T1: Deduct $100 from User A                                         │
│     T2: Add $100 to User B                                              │
│                                                                         │
│  Compensating transactions (undo if failure):                           │
│  ─────────────────────────────────────────────                          │
│                                                                         │
│     C1: Add $100 back to User A                                         │
│     C2: Deduct $100 from User B                                         │
│                                                                         │
│  If T2 fails after T1 succeeds:                                         │
│     Execute C1 to rollback                                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

```
SAGA PATTERN
────────────
execute(from_user, to_user, amount):
  saga_id = generate_saga_id()
  
  // Step 1: Deduct from sender
  TRY:
    deduct_balance(saga_id, from_user, amount)
  CATCH InsufficientFunds:
    RETURN Failure("Insufficient funds")
  
  // Step 2: Add to receiver
  TRY:
    add_balance(saga_id, to_user, amount)
  CATCH Exception:
    // COMPENSATE: refund the sender
    add_balance(saga_id, from_user, amount)
    RETURN Failure("Transfer failed")
  
  RETURN Success

deduct_balance(saga_id, user_id, amount):
  shard = get_user_shard(user_id)
  // Record saga step for idempotency
  INSERT INTO saga_log (saga_id, step='deduct', status='started')
  UPDATE balances SET amount = amount - $amount WHERE user_id = $user_id AND amount >= $amount
  UPDATE saga_log SET status='completed' WHERE saga_id = $saga_id AND step='deduct'
```

**Saga Trade-offs:**
- Eventually consistent (not immediately atomic)
- Requires idempotent operations
- Compensation logic can be complex
- Better availability than 2PC

#### Problem 3: Cross-Shard Aggregations

```
Query: SELECT COUNT(*), SUM(amount) FROM orders WHERE status = 'completed'

Problem: Orders are spread across 64 shards
```

**Solution: Scatter-Gather**

```
SCATTER-GATHER AGGREGATION
──────────────────────────
aggregate(query, merge_function):
  // SCATTER: query all shards in parallel
  futures = []
  FOR each shard:
    futures.append(async_execute(shard, query))
  
  // GATHER: collect results
  results = await_all(futures)
  
  // Handle failures
  successful = []
  FOR each result:
    IF is_exception(result):
      log_error("Shard failed")
      // Option: fail entire query OR continue with partial
    ELSE:
      successful.append(result)
  
  // MERGE: combine results
  RETURN merge_function(successful)

EXAMPLE
───────
query = "SELECT COUNT(*), SUM(amount) FROM orders WHERE status='completed'"

merge_order_stats(results):
  RETURN {
    count: sum(r.count for r in results),
    sum: sum(r.sum for r in results)
  }

stats = aggregate(query, merge_order_stats)
// → {count: 1000000, sum: 50000000}
```

**Optimization: Pre-Aggregation**

For frequently-needed aggregations, maintain running totals:

```
// Instead of scatter-gather every time, maintain a summary table
ORDER STATS CACHE (pre-aggregation)
───────────────────────────────────
on_order_completed(order):
  // Update per-shard summary (fast, local)
  local_shard.increment('completed_orders_count', 1)
  local_shard.increment('completed_orders_sum', order.amount)
  
  // Async sync to global summary
  publish_to_aggregator({shard, delta_count: 1, delta_sum: order.amount})
```

---

### 2.7 Distributed ID Generation

In a sharded system, you can't use auto-increment IDs. Two shards would generate the same ID.

#### Strategy 1: UUID

```
generate_id():
  RETURN uuid4()  // Example: "550e8400-e29b-41d4-a716-446655440000"
```

**Pros:** Simple, no coordination needed
**Cons:** 128 bits (storage), not sortable, poor index performance

#### Strategy 2: Snowflake IDs (Twitter's Approach)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      SNOWFLAKE ID STRUCTURE (64 bits)                   │
│                                                                         │
│   ┌───────────────────────────────────────────────────────────────────┐ │
│   │ 1 bit │    41 bits      │   10 bits   │      12 bits              │ │
│   │unused │   timestamp     │  machine ID │     sequence              │ │
│   └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│   Timestamp: milliseconds since custom epoch (69 years of IDs)          │
│   Machine ID: 1024 unique generators (workers + datacenters)            │
│   Sequence: 4096 IDs per millisecond per machine                        │
│                                                                         │
│   Total capacity: ~4 million IDs/second/machine                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

```
SNOWFLAKE ID GENERATOR
──────────────────────
State per generator:
  machine_id: unique per server (0-1023)
  sequence: counter within same millisecond (0-4095)
  last_timestamp: track for sequence reset

generate():
  timestamp = current_millis()
  
  IF timestamp == last_timestamp:
    sequence = (sequence + 1) AND 0xFFF  // Wrap at 4095
    IF sequence == 0:
      // Exhausted 4096 IDs this millisecond, wait
      WHILE timestamp <= last_timestamp:
        timestamp = current_millis()
  ELSE:
    sequence = 0  // New millisecond, reset sequence
  
  last_timestamp = timestamp
  
  // Compose the 64-bit ID
  id = ((timestamp - EPOCH) << 22) | (machine_id << 12) | sequence
  RETURN id

parse(snowflake_id):  // For debugging
  sequence = snowflake_id AND 0xFFF
  machine_id = (snowflake_id >> 12) AND 0x3FF
  timestamp = (snowflake_id >> 22) + EPOCH
  RETURN {timestamp, machine_id, sequence}

EXAMPLE
───────
generator = new SnowflakeGenerator(machine_id=42)
id = generator.generate()
// → 7199348347483156522
// Parsed: {timestamp: 2024-01-19 12:34:56, machine_id: 42, sequence: 0}
```

**Pros:** 
- 64 bits (fits in BIGINT)
- Time-sortable (newer IDs are larger)
- No coordination between machines
- Encodes creation time (useful for debugging)

**Cons:**
- Requires unique machine IDs (coordination at deploy time)
- Clock skew can cause issues

#### Strategy 3: ULID (Universally Unique Lexicographically Sortable Identifier)

```
ULID: 26 characters, Crockford Base32 encoded
Format: TTTTTTTTTTSSSSSSSSSSSSSSSS
        timestamp (10) + randomness (16) = 128 bits

generate_id():
  RETURN ulid.new()  // Example: "01ARZ3NDEKTSV4RRFFQ69G5FAV"

// ULIDs are sortable by creation time
id1 = ulid.new()
sleep(1ms)
id2 = ulid.new()
assert id2 > id1  // True!
```

**Comparison Table:**

| Strategy | Size | Sortable | Coordination | Performance |
|----------|------|----------|--------------|-------------|
| UUID v4 | 128 bits | ❌ No | ❌ None | ⭐⭐⭐ High |
| Snowflake | 64 bits | ✅ Yes | ⚠️ Machine ID | ⭐⭐⭐ High |
| ULID | 128 bits | ✅ Yes | ❌ None | ⭐⭐⭐ High |
| Auto-increment | 64 bits | ✅ Yes | ❌ N/A (single node) | N/A |
| Database sequence | 64 bits | ✅ Yes | ✅ Central DB | ⭐ Low |

**Recommendation:** Use Snowflake IDs for most sharded systems. The time-based sorting is invaluable for debugging and querying, and 64 bits fits in a BIGINT efficiently.

---

## Part 3: Applied Scenarios

### 3.1 Scenario: User Data Store Evolution

Let's trace the evolution of a user data store from startup to scale.

#### Phase 1: Early Days (0-100K Users)

```
Simple PostgreSQL setup:

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255),
    profile JSONB,
    created_at TIMESTAMP
);

// Everything on one server. ~50ms queries. Life is good.
```

#### Phase 2: Growth Pains (100K-10M Users)

```
Add read replicas for scaling reads:

                    ┌──────────┐
    Writes ────────▶│ Primary  │
                    └────┬─────┘
                         │ replication
            ┌────────────┼────────────┐
            ▼            ▼            ▼
       ┌────────┐   ┌────────┐   ┌────────┐
       │Replica1│   │Replica2│   │Replica3│
       └────────┘   └────────┘   └────────┘
            ▲            ▲            ▲
            └────────────┴────────────┘
                    Reads (load balanced)
```

**Issues Encountered:**
- Read-your-writes inconsistency for profile updates
- Primary becoming bottleneck for writes
- Connection pool exhaustion

**Solutions Applied:**

```
Sticky sessions for recently-updated users:

get_user(user_id):
  IF cache.get("recently_updated:{user_id}"):
    RETURN primary.get_user(user_id)
  RETURN load_balanced_replica.get_user(user_id)

update_user(user_id, data):
  result = primary.update_user(user_id, data)
  cache.set("recently_updated:{user_id}", True, ttl=30)
  RETURN result
```

#### Phase 3: Sharding Required (10M+ Users)

```
Hash-based sharding on user_id:

SHARD_COUNT = 16

get_user_shard(user_id):
  RETURN consistent_hash(user_id, SHARD_COUNT)

// Each shard has primary + replicas
// Shard 0: users whose hash maps to 0
// Shard 1: users whose hash maps to 1
// ... etc
```

**Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                    USER SERVICE                             │
│                                                             │
│    ┌──────────────────────────────────────────────┐         │
│    │            SHARD ROUTER                      │         │
│    │                                              │         │
│    │   shard_id = consistent_hash(user_id) % 16   │         │
│    └──────────────────────────────────────────────┘         │
│                          │                                  │
│    ┌─────────┬─────────┬─┴───────┬─────────┬─────────┐      │
│    ▼         ▼         ▼         ▼         ▼         ▼      │
│ ┌─────┐  ┌─────┐   ┌─────┐     ┌─────┐  ┌─────┐  ┌─────┐    │
│ │Sh 0 │  │Sh 1 │   │Sh 2 │     │ ... │  │Sh 14│  │Sh 15│    │
│ │     │  │     │   │     │     │     │  │     │  │     │    │
│ │P + R│  │P + R│   │P + R│     │     │  │P + R│  │P + R│    │
│ └─────┘  └─────┘   └─────┘     └─────┘  └─────┘  └─────┘    │
│                                                             │
│ P = Primary, R = Replicas                                   │
└─────────────────────────────────────────────────────────────┘
```

**Challenge: Email Lookups**

Users log in by email, not user_id. But we sharded by user_id.

```
Problem: login(email) → which shard?

Solution: Secondary index
Separate lookup table: email → user_id (small, replicated)

CREATE TABLE email_to_user (
    email VARCHAR(255) PRIMARY KEY,
    user_id BIGINT
);

login(email, password):
  user_id = email_lookup.get(email)  // Small unsharded table
  shard = get_user_shard(user_id)
  user = shard.get_user(user_id)
  RETURN verify_password(user, password)
```

**Failure Modes to Handle:**

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Single shard down | ~6% of users affected | Failover to replica, alerting |
| Router failure | All requests fail | Multiple router instances |
| Email lookup down | No logins possible | Replicate heavily, cache aggressively |
| Shard split-brain | Data inconsistency | Fencing, leader election |

---

### Quantitative Growth Thresholds: When to Scale

Staff engineers don't guess when to scale—they model thresholds based on measurable metrics. Here's when each scaling decision becomes necessary.

#### Scale Thresholds: What Breaks First

| Scale | Users | Write QPS | Read QPS | What Breaks First | Action Required |
|-------|-------|-----------|----------|-------------------|-----------------|
| **Early** | 10K | 50 | 500 | Nothing—single node handles easily | Monitor, optimize queries |
| **Growth** | 100K | 500 | 5K | Connection pool exhaustion | Add connection pooling, read replicas |
| **Scale** | 1M | 5K | 50K | Write bottleneck (WAL saturation) | Read replicas mandatory, consider sharding |
| **Large** | 10M | 50K | 500K | Read replicas saturate, replication lag | Sharding required, aggressive caching |
| **Massive** | 100M | 500K | 5M | Shard rebalancing overhead | Multi-region, specialized sharding strategies |

#### Specific Breaking Points

**At 5K Write QPS: Single PostgreSQL Primary Hits WAL Bottleneck**

```
PostgreSQL Write-Ahead Log (WAL) limits:
- Single disk: ~2,000-3,000 writes/sec sustained
- NVMe SSD: ~5,000-8,000 writes/sec sustained
- Beyond this: WAL becomes bottleneck, commit latency spikes

Symptoms:
- p99 write latency > 100ms (was < 10ms)
- WAL write queue depth > 10
- Disk I/O saturation at 90%+

Action: Read replicas help reads, but writes still bottlenecked
→ Need sharding OR write optimization (batch writes, denormalize)
```

**At 50K Read QPS: Read Replicas Saturate — Need Sharding or Caching**

```
Read replica saturation math:
- Single replica capacity: ~10K-15K QPS (depends on query complexity)
- 3 replicas: ~30K-45K QPS total
- At 50K QPS: Replicas at 80-90% utilization

Replication lag grows under write pressure:
- Low write load: Replication lag < 100ms
- High write load (5K+ writes/sec): Replication lag 500ms-2s
- At 50K reads/sec + 5K writes/sec: Lag spikes to 5-10s

Users see stale data. Read replicas no longer sufficient.
→ Need sharding (distribute reads across shards) OR aggressive caching (Redis, CDN)
```

**At 100+ Shards: Operational Overhead Exceeds Engineering Capacity**

```
Operational overhead quantification:
- Schema migration: 5 min × 100 shards = 500 min = 8.3 hours (sequential)
- Parallel migration: Requires coordination, rollback complexity, 2-3 hours + risk
- Incident response: 1 shard failure = 1% users affected, but requires investigation
- At 100 shards: Expect 1-2 shard incidents per month = 4-8 hours/month

Team capacity (5-person team):
- 100 shards: ~30% of team time on shard operations
- 200 shards: ~60% of team time on shard operations
- 500 shards: Requires dedicated platform team (2-3 engineers)

Staff insight: At 100+ shards, you've outgrown simple sharding. Need:
- Automated shard management (Vitess, Citus, custom)
- Specialized platform team
- Or reconsider architecture (maybe sharding isn't the answer)
```

#### Early Warning Metrics

Monitor these metrics to predict scaling needs **before** systems break:

| Metric | Threshold | What It Predicts |
|--------|-----------|------------------|
| **Replication lag trend** | > 500ms and growing | Read replicas saturating, need sharding soon |
| **Connection pool utilization** | > 80% sustained | Need more replicas or connection pooling optimization |
| **Disk I/O saturation** | > 85% sustained | WAL bottleneck approaching, write scaling needed |
| **p99 query latency** | > 100ms (was < 20ms) | Capacity limit approaching, investigate root cause |
| **Shard key distribution** | > 20% variance in shard sizes | Hot shards forming, rebalancing needed |

**Staff approach**: Set alerts at 60% of breaking point, not 90%. Gives you 3-6 months to plan and execute scaling.

#### Most Dangerous Assumptions

**1. "Read replicas scale linearly" (FALSE)**

```
Assumption: 3 replicas = 3x read capacity
Reality: Replication lag grows non-linearly under write pressure

Write load → Replication lag:
- 1K writes/sec → 50ms lag
- 5K writes/sec → 500ms lag
- 10K writes/sec → 2-5s lag

At high write load, replicas become unusable (stale data). You get 1.5-2x effective capacity, not 3x.
```

**2. "Sharding doubles capacity" (FALSE)**

```
Assumption: 16 shards = 16x write capacity
Reality: Cross-shard overhead consumes 15-30% of capacity

Overhead sources:
- Shard routing: +1-2ms per request
- Cross-shard queries: 10-50ms additional latency
- Rebalancing: Ongoing 5-10% capacity reserved for migrations
- Operational overhead: Team time on shard management

Effective capacity: 16 shards ≈ 11-14x single-node capacity (not 16x)
```

**3. "We'll shard when we hit 80% capacity" (DANGEROUS)**

```
Reality: Sharding takes 3-6 months to implement properly
- Design: 2-4 weeks
- Implementation: 4-8 weeks
- Testing: 2-4 weeks
- Migration: 2-4 weeks
- Stabilization: 2-4 weeks

If you wait until 80% capacity, you'll hit 100% before sharding is ready.
Staff approach: Start sharding design at 50-60% capacity, implement at 70-75%
```

---

### 3.2 Scenario: Rate Limiter Counters

Rate limiting looks simple until you try to do it at scale. Let's design a distributed rate limiter.

**Requirements:**
- 100M users
- Limit: 100 requests per minute per user
- Sub-millisecond latency
- Globally consistent-ish (eventually consistent OK for slight over-limit)

#### Naive Approach (Won't Scale)

```
Single Redis instance:

check_rate_limit(user_id):
  key = "rate:{user_id}"
  count = redis.INCR(key)
  IF count == 1: redis.EXPIRE(key, 60)
  RETURN count <= 100
```

**Why it fails:**
- Single Redis is SPOF
- Can't handle 100K+ QPS
- Memory limited for 100M keys

#### Sharded Rate Limiter

```
SHARDED RATE LIMITER
────────────────────
64 Redis shards, each with primary + replica

get_shard(user_id):
  RETURN shards[hash(user_id) % num_shards]

check_rate_limit(user_id, limit=100, window=60):
  shard = get_shard(user_id)
  key = "rate:{user_id}"
  
  // Atomic increment with TTL (pipeline)
  count = shard.INCR(key)
  shard.EXPIRE(key, window)
  
  RETURN count <= limit
```

**Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                   RATE LIMITER SERVICE                      │
│                                                             │
│   Request ─▶ hash(user_id) % 64 ─▶ Redis Shard              │
│                                                             │
│   ┌───────────────────────────────────────────────────┐     │
│   │                 64 Redis Shards                   │     │
│   │                                                   │     │
│   │   Shard 0    Shard 1    Shard 2    ...   Shard 63 │     │
│   │   ┌─────┐    ┌─────┐    ┌─────┐         ┌─────┐   │     │
│   │   │Redis│    │Redis│    │Redis│         │Redis│   │     │
│   │   │     │    │     │    │     │         │     │   │     │
│   │   │ P+R │    │ P+R │    │ P+R │         │ P+R │   │     │
│   │   └─────┘    └─────┘    └─────┘         └─────┘   │     │
│   │                                                   │     │
│   │   Each shard: Primary + 1 Replica (async)         │     │
│   └───────────────────────────────────────────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Trade-offs Made:**

1. **Async replication**: We accept that on failover, some counts might reset. Users might get a few extra requests through. This is acceptable for rate limiting.

2. **No cross-shard queries**: Each user's count is on exactly one shard. No aggregation needed.

3. **Hot user handling**: For viral users, their shard might become hot. Solution: monitor per-shard load and be prepared to split.

**Failure Mode Analysis:**

```
Scenario: Shard 15 goes down

Impact:
- Users mapped to shard 15 (~1.5M users) have no rate limiting
- They can burst traffic
- This lasts until failover completes (~30 seconds)

Mitigation:
- Fail fast to replica
- Apply aggressive local rate limiting at API gateway
- Alert on-call immediately

Scenario: Network partition between shards

Impact:
- Split-brain: users counted in two places
- Effectively 2x limit during partition
- Resolves when partition heals

Mitigation:
- Accept this as tolerable for rate limiting
- Alternative: use consensus (Raft) but pay latency cost
```

#### Advanced Rate Limiting Algorithms (Staff-Level Deep Dive)

The naive counter approach has a fundamental flaw: **boundary bursts**.

```
Problem: Fixed Window Boundary Burst
─────────────────────────────────────────────────────────────────────────
Window 1 (00:00-00:59)          Window 2 (01:00-01:59)
                    │                     │
User sends 0 requests until    │ User sends 100 requests at 01:00
00:55, then sends 100 at 00:59 │ 
                    │                     │
Result: 200 requests in 4 seconds! Limit was 100/minute.
─────────────────────────────────────────────────────────────────────────
```

**Solution 1: Sliding Window Log**

```
SLIDING WINDOW LOG (Precise, but memory-heavy)
──────────────────────────────────────────────
Structure: Sorted set of timestamps per user

is_allowed(user_id):
  key = "ratelimit:log:{user_id}"
  now = current_time()
  window_start = now - window_seconds
  
  // Atomic Lua script:
  ZREMRANGEBYSCORE key -inf window_start  // Remove old entries
  count = ZCARD key
  
  IF count < limit:
    ZADD key now "{now}:{random}"  // Add current request
    EXPIRE key window_seconds
    RETURN True
  ELSE:
    RETURN False

Memory: O(requests per window) per user


SLIDING WINDOW COUNTER (Memory-efficient approximation)
───────────────────────────────────────────────────────
Structure: Two counters per user (current + previous window)

is_allowed(user_id):
  current_window = now // window_seconds
  previous_window = current_window - 1
  window_position = (now % window_seconds) / window_seconds  // 0.0 to 1.0
  
  current_count = GET "ratelimit:{user_id}:{current_window}"
  previous_count = GET "ratelimit:{user_id}:{previous_window}"
  
  // Weighted count: full current + partial previous
  weighted_count = current_count + (previous_count × (1 - window_position))
  
  IF weighted_count < limit:
    INCR current_key
    RETURN True
  ELSE:
    RETURN False

Memory: O(1) per user (just 2 counters)
```

**Solution 2: Token Bucket (Smooth Rate Limiting)**

```
TOKEN BUCKET (allows bursts, caps sustained rate)
─────────────────────────────────────────────────
Parameters:
  bucket_size: 100 (burst capacity)
  refill_rate: 10 tokens/second

State per user: {tokens, last_update}

is_allowed(user_id, tokens_required=1):
  // Get current state
  tokens = GET tokens (default: bucket_size)
  last_update = GET last_update (default: now)
  
  // Calculate refill since last request
  time_passed = now - last_update
  tokens = MIN(bucket_size, tokens + time_passed × refill_rate)
  
  IF tokens >= tokens_required:
    tokens -= tokens_required
    SAVE {tokens, last_update: now}
    RETURN True
  ELSE:
    SAVE {tokens, last_update: now}
    RETURN False

get_wait_time(user_id, tokens_required):
  current_tokens = calculate_current_tokens()
  IF current_tokens >= tokens_required: RETURN 0
  tokens_needed = tokens_required - current_tokens
  RETURN tokens_needed / refill_rate


LEAKY BUCKET (constant output rate, no bursts)
──────────────────────────────────────────────
Parameters:
  bucket_size: 100 (queue capacity)
  leak_rate: 10 requests/second (drain rate)

State per user: {water, last_update}

is_allowed(user_id):
  // Get current state
  water = GET water (default: 0)
  last_update = GET last_update (default: now)
  
  // Calculate leak (water that drained since last update)
  time_passed = now - last_update
  water = MAX(0, water - time_passed × leak_rate)
  
  IF water < bucket_size:
    water += 1
    SAVE {water, last_update: now}
    RETURN True
  ELSE:
    RETURN False
```

**Solution 3: Distributed Rate Limiting Across API Gateways**

```
┌─────────────────────────────────────────────────────────────────────────┐
│               DISTRIBUTED RATE LIMITING ARCHITECTURE                    │
│                                                                         │
│   User Request                                                          │
│        │                                                                │
│        ▼                                                                │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                    LOAD BALANCER                                │   │
│   └────────────────────────┬────────────────────────────────────────┘   │
│                            │                                            │
│         ┌──────────────────┼──────────────────┐                         │
│         ▼                  ▼                  ▼                         │
│   ┌───────────┐      ┌───────────┐      ┌───────────┐                   │
│   │  Gateway  │      │  Gateway  │      │  Gateway  │                   │
│   │    #1     │      │    #2     │      │    #3     │                   │
│   │           │      │           │      │           │                   │
│   │ ┌───────┐ │      │ ┌───────┐ │      │ ┌───────┐ │                   │
│   │ │ Local │ │      │ │ Local │ │      │ │ Local │ │                   │
│   │ │Counter│ │      │ │Counter│ │      │ │Counter│ │                   │
│   │ └───┬───┘ │      │ └───┬───┘ │      │ └───┬───┘ │                   │
│   └─────┼─────┘      └─────┼─────┘      └─────┼─────┘                   │
│         │                  │                  │                         │
│         └──────────────────┼──────────────────┘                         │
│                            │ Periodic Sync (every 1s)                   │
│                            ▼                                            │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                   GLOBAL RATE LIMIT STORE                       │   │
│   │                     (Redis Cluster)                             │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

```
DISTRIBUTED RATE LIMITER (Two-Tier)
───────────────────────────────────
Trade-off: Accept small over-limit in exchange for speed

Tier 1: Local counters (fast, no network)
Tier 2: Global sync (accurate, periodic)

Per-gateway state:
  local_counts: {user_id → count}
  local_limits: {user_id → allocated_quota}

is_allowed(user_id):  // FAST PATH - no network!
  local_counts[user_id] += 1
  local_limit = local_limits[user_id] OR (global_limit / 10)
  RETURN local_counts[user_id] <= local_limit

sync_to_global():  // Background, every 1 second
  FOR each (user_id, local_count) in local_counts:
    // Report our counts to Redis, get remaining quota
    HINCRBY "global_rate:{user_id}" gateway_id local_count
    total = SUM(HVALS "global_rate:{user_id}")
    remaining = MAX(0, global_limit - total)
    
    // Update local quota (divide among gateways)
    local_limits[user_id] = MAX(10, remaining / num_gateways)
  
  local_counts.clear()


MULTI-DIMENSION RATE LIMITER
────────────────────────────
Example: 100/min per user AND 1000/min per endpoint AND 500/min per IP

add_dimension(name, extractor, limit, window):
  limiters[name] = {extractor, limit, window}

is_allowed(request):
  FOR each (name, config) in limiters:
    key = config.extractor(request)
    full_key = "rate:{name}:{key}"
    
    count = INCR full_key
    IF count == 1: EXPIRE full_key window
    
    IF count > limit:
      RETURN (False, name)  // Rejected by this dimension
  
  RETURN (True, None)

EXAMPLE USAGE
─────────────
add_dimension('user', req → req.user_id, 100, 60)
add_dimension('endpoint', req → req.path, 1000, 60)
add_dimension('ip', req → req.client_ip, 500, 60)

(allowed, rejected_by) = is_allowed(request)
IF NOT allowed: RETURN 429 "Rate limited by {rejected_by}"
```

**Rate Limiting Algorithm Comparison:**

| Algorithm | Precision | Memory | Burst Handling | Use Case |
|-----------|-----------|--------|----------------|----------|
| **Fixed Window** | Low | O(1) | Poor (boundary burst) | Simple, low-stakes |
| **Sliding Log** | High | O(n) | Excellent | Precision-critical |
| **Sliding Counter** | Medium | O(1) | Good | Best general purpose |
| **Token Bucket** | High | O(1) | Controlled bursts | API rate limiting |
| **Leaky Bucket** | High | O(1) | No bursts (smoothing) | Backend protection |

---

### 3.3 Scenario: Feed Storage (Complex Multi-Tenant Data)

Feed systems (Twitter timeline, Facebook News Feed, Instagram home) are among the most complex sharding challenges.

#### Quick Visual: The Feed Storage Trade-off

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FAN-OUT: THE FUNDAMENTAL TRADE-OFF                       │
│                                                                             │
│   User posts "Hello World"                                                  │
│   They have 10,000 followers                                                │
│                                                                             │
│   OPTION A: FAN-OUT ON WRITE              OPTION B: FAN-OUT ON READ         │
│   ────────────────────────                ─────────────────────             │
│                                                                             │
│   When posted:                            When posted:                      │
│   Write to 10,000 feeds                   Write to 1 place (author's posts) │
│   10,000 writes!                          1 write                           │
│                                                                             │
│   When reading:                           When reading:                     │
│   Read from 1 feed (pre-computed)         Fetch from 500 followed users     │
│   1 read                                  500 reads + merge + sort!         │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ CELEBRITY PROBLEM: Taylor Swift has 50M followers                   │   │
│   │                                                                     │   │
│   │ Fan-out on write: 50M writes per tweet = DISASTER                   │   │
│   │ Fan-out on read: Everyone queries her posts = acceptable            │   │
│   │                                                                     │   │
│   │ SOLUTION: HYBRID                                                    │   │
│   │ • Regular users (< 10K followers): Fan-out on write                 │   │
│   │ • Celebrities (> 10K followers): Fan-out on read                    │   │
│   │ • Merge at read time                                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**The Problem:**
- Each user has a feed
- Feed contains posts from users they follow
- Posts must be ordered by time
- Feeds must be fast to read (p99 < 50ms)
- Writes happen constantly (new posts, deletes, edits)

#### Approach 1: Fan-Out on Write

```
When User A posts:

┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  User A posts "Hello World"                                 │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────────────┐                                    │
│  │   POST SERVICE      │                                    │
│  │                     │                                    │
│  │   1. Store post     │                                    │
│  │   2. Get followers  │─────▶ 10,000 followers             │
│  │   3. Fan out        │                                    │
│  └─────────────────────┘                                    │
│           │                                                 │
│           ▼                                                 │
│  Write to 10,000 user feeds                                 │
│                                                             │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐     ┌─────────┐        │
│  │ Feed 1  │ │ Feed 2  │ │ Feed 3  │ ... │Feed 10K │        │
│  │ +post   │ │ +post   │ │ +post   │     │ +post   │        │
│  └─────────┘ └─────────┘ └─────────┘     └─────────┘        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Sharding for Fan-Out on Write:**

```
FEED STORE (sharded by feed owner)
──────────────────────────────────
get_shard(user_id):
  RETURN shards[consistent_hash(user_id) % num_shards]

add_to_feed(user_id, post):
  shard = get_shard(user_id)
  shard.add_post(user_id, post)

get_feed(user_id, limit=20):
  shard = get_shard(user_id)  // Single shard read!
  RETURN shard.get_posts(user_id, limit)
```

**Pros:**
- Reads are FAST (single shard, pre-computed)
- Scales reads horizontally

**Cons:**
- Writes are expensive (celebrity with 50M followers = 50M writes)
- Storage explosion (same post stored 50M times)
- Deletes are nightmares

#### Approach 2: Fan-Out on Read

```
When User B reads their feed:

┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  User B requests feed                                       │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────────────────────────┐                        │
│  │        FEED SERVICE             │                        │
│  │                                 │                        │
│  │  1. Get B's following list      │                        │
│  │     (follows 500 users)         │                        │
│  │                                 │                        │
│  │  2. Fetch recent posts from     │                        │
│  │     each followed user          │                        │
│  │                                 │                        │
│  │  3. Merge and sort              │                        │
│  │                                 │                        │
│  │  4. Return top 20               │                        │
│  └─────────────────────────────────┘                        │
│           │                                                 │
│    Scatter-gather to many shards                            │
│           │                                                 │
│  ┌───┬───┬───┬───┬───┬───┬───┐                              │
│  │S1 │S2 │S3 │S4 │S5 │...│Sn │                              │
│  └───┴───┴───┴───┴───┴───┴───┘                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Sharding for Fan-Out on Read:**

```
POST STORE (sharded by author_id)
─────────────────────────────────
get_recent_posts(author_id, since, limit):
  shard = get_shard(author_id)
  RETURN shard.query_posts(author_id, since, limit)


FEED SERVICE (scatter-gather)
─────────────────────────────
get_feed(user_id, limit=20):
  following = social_graph.get_following(user_id)  // e.g., 500 users
  
  // Parallel fetch from all followed users
  futures = []
  FOR each author_id in following:
    futures.append(async post_store.get_recent_posts(author_id, since=1_day_ago, limit=5))
  
  // Gather and merge
  all_posts = []
  FOR each future in futures:
    all_posts.extend(future.result())
  
  // Sort by time, return top N
  sort(all_posts, by=created_at, descending)
  RETURN all_posts[:limit]
```

**Pros:**
- Writes are cheap (single write for a post)
- Storage efficient (post stored once)
- Deletes are easy

**Cons:**
- Reads are expensive (scatter-gather)
- Read latency depends on following count
- Harder to scale reads

#### Approach 3: Hybrid (What Twitter Actually Does)

```
┌─────────────────────────────────────────────────────────────┐
│                     HYBRID APPROACH                         │
│                                                             │
│  For regular users (< 10K followers):                       │
│  ────────────────────────────────                           │
│     Fan-out on write                                        │
│     Pre-computed feeds                                      │
│     Fast reads                                              │
│                                                             │
│  For celebrities (> 10K followers):                         │
│  ─────────────────────────────────                          │
│     Fan-out on read                                         │
│     Posts stored once                                       │
│     Merged at read time                                     │
│                                                             │
│  Read Path:                                                 │
│  ┌──────────────────────────────────────────────┐           │
│  │                                              │           │
│  │   1. Fetch pre-computed feed (regular posts) │           │
│  │   2. Fetch celebrity posts (on-demand)       │           │
│  │   3. Merge and rank                          │           │
│  │   4. Return                                  │           │
│  │                                              │           │
│  └──────────────────────────────────────────────┘           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Sharding Strategy for Hybrid:**

```
HYBRID FEED SYSTEM
──────────────────
CELEBRITY_THRESHOLD = 10,000 followers

Sharding:
  - Feed shards: 256, sharded by feed owner
  - Post shards: 64, sharded by author

on_new_post(author_id, post):
  store_post(author_id, post)
  
  IF author_id NOT IN celebrities:
    // Fan-out on write for regular users
    FOR each follower_id in get_followers(author_id):
      add_to_feed(follower_id, post.id)
  // Celebrities: no fan-out (read on demand)

get_feed(user_id):
  // Pre-computed feed (regular user posts)
  precomputed = get_precomputed_feed(user_id)  // Single shard read
  
  // Celebrity posts (fan-out on read)
  celebrity_posts = get_celebrity_posts_for_user(user_id)  // Scatter-gather
  
  // Merge both
  RETURN merge_and_rank(precomputed, celebrity_posts)
```

#### Advanced Feed Patterns (Staff-Level Deep Dive)

**Pattern 1: Cursor-Based Pagination Across Shards**

Offset-based pagination breaks with sharded feeds. Cursor-based pagination is the solution.

```
FEED CURSOR
───────────
Structure (encoded in base64 for client):
  timestamp: last seen timestamp
  post_id: last seen post ID (for uniqueness)
  shard_positions: {shard_id → position}  // For efficient resume


SHARDED FEED PAGINATOR
──────────────────────
get_feed_page(user_id, cursor, page_size=20):
  feed_shard = get_feed_shard(user_id)
  celebrity_ids = get_followed_celebrities(user_id)
  
  IF cursor:
    // Resume from cursor position
    feed_items = feed_shard.query(user_id, timestamp < cursor.timestamp, limit=page_size+10)
    celebrity_items = fetch_celebrity_posts(celebrity_ids, timestamp < cursor.timestamp)
  ELSE:
    // First page
    feed_items = feed_shard.query(user_id, limit=page_size+10)
    celebrity_items = fetch_celebrity_posts(celebrity_ids)
  
  // Merge and sort by timestamp
  all_items = feed_items + celebrity_items
  sort(all_items, by=timestamp, descending)
  page_items = all_items[:page_size]
  
  IF length(page_items) < page_size:
    RETURN (page_items, None)  // No more pages
  
  // Create cursor for next page
  last_item = page_items[-1]
  next_cursor = {timestamp: last_item.timestamp, post_id: last_item.post_id}
  RETURN (page_items, next_cursor)

fetch_celebrity_posts(celebrity_ids, timestamp_lt):
  // Parallel fetch from post shards (fan-out on read)
  FOR each celeb_id in celebrity_ids (parallel):
    shard = get_post_shard(celeb_id)
    posts += shard.get_posts(celeb_id, timestamp_lt, limit=5)
  RETURN posts


INFINITE SCROLL OPTIMIZER
─────────────────────────
Key optimizations:
  1. Pre-fetch next 2 pages while user reads current
  2. Cache nearby pages for back-navigation
  3. Use approximate counts for "more content" indicator

get_page_with_prefetch(user_id, cursor):
  (items, next_cursor) = paginator.get_feed_page(user_id, cursor)
  
  // Cache this page (TTL 5 min)
  cache.set("feed:{user_id}:{cursor}", {items, next_cursor})
  
  // Async prefetch next 2 pages
  IF next_cursor:
    async trigger_prefetch(user_id, next_cursor, count=2)
  
  RETURN {items, next_cursor, has_more: next_cursor != null}
```

**Pattern 2: Feed Pruning and TTL Management**

```
FEED RETENTION POLICY
─────────────────────
max_items: 1000        // Keep last N items per user
max_age_days: 30       // Keep items from last M days
prune_interval: 6 hours

FEED PRUNER
───────────
Strategies:
  1. Count-based: Keep last N items
  2. Time-based: Keep items from last M days
  3. Hybrid: Apply whichever removes more

prune_user_feed(user_id, shard):
  removed = 0
  stats = shard.get_feed_stats(user_id)
  
  // Count-based pruning
  IF stats.count > max_items:
    excess = stats.count - max_items
    removed += shard.remove_oldest(user_id, limit=excess)
  
  // Time-based pruning
  cutoff = now() - max_age_days
  removed += shard.remove_before_timestamp(user_id, cutoff)
  
  RETURN removed

run_pruning_job():  // Background job
  FOR each shard (parallel):
    FOR each user_id in shard.scan_users(batch=100):
      prune_user_feed(user_id, shard)


ADAPTIVE FEED SIZE
──────────────────
Adjust feed size based on user activity:
  - Power users (score > 0.8):    2000 items
  - Regular users (score > 0.5):  1000 items
  - Occasional (score > 0.2):     500 items
  - Inactive (score <= 0.2):      200 items

should_fan_out_to_user(user_id, author_priority):
  activity_score = activity_tracker.get_score(user_id)
  
  IF activity_score > 0.5: RETURN True  // Always fan out to active users
  
  // Inactive users: only high-priority posts
  RETURN author_priority >= 7
```

**Pattern 3: Feed Deduplication and Ranking Integration**

```
FEED DEDUPLICATOR
─────────────────
Duplicates happen when:
  1. User follows both author and re-sharer
  2. Post is edited and re-indexed
  3. Cross-posted to multiple channels

get_content_hash(post):
  canonical = "{original_author}:{first_100_chars_of_content}"
  RETURN md5(canonical)[:16]

filter_duplicates(user_id, posts):
  seen = seen_cache[user_id]  // Set of content_hashes
  unique_posts = []
  
    content_hash = get_content_hash(post)
    IF content_hash NOT IN seen:
      seen.add(content_hash)
      unique_posts.append(post)
  
  RETURN unique_posts

add_to_feed_with_dedup(shard, user_id, post):
  content_hash = get_content_hash(post)
  
  // Check recent feed for duplicates
  existing = shard.query(user_id, content_hash, limit=1)
  
  IF existing: RETURN False  // Duplicate
  
  shard.insert(user_id, {post, content_hash})
  RETURN True


RANKED FEED MERGER
──────────────────
Sources:
  1. Pre-computed feed (fan-out on write)
  2. Celebrity posts (fan-out on read)
  3. Recommended posts (discovery)
  4. Ads (monetization)

merge_and_rank(user_id, feed_posts, celebrity_posts, recommended):
  // Tag source for analytics
  tag feed_posts with source='feed'
  tag celebrity_posts with source='celebrity'
  tag recommended with source='recommended'
  
  candidates = feed_posts + celebrity_posts + recommended
  
  // ML-based scoring
  user_features = get_user_features(user_id)
  FOR each post in candidates:
    post.score = ranking_model.score(user_features, post_features, context)
  
  // Sort by score
  sort(candidates, by=score, descending)
  
  // Insert ads every 5 posts
  RETURN insert_ads(user_id, candidates, frequency=5)

insert_ads(user_id, posts, frequency=5):
  result = []
  FOR i, post in enumerate(posts):
    result.append(post)
    IF (i + 1) % frequency == 0:
      ad = ad_service.get_next_ad(user_id)
      IF ad: result.append({type='ad', ad})
  RETURN result
```

**Feed Storage Architecture Summary:**

| Component | Sharding Strategy | Why |
|-----------|------------------|-----|
| User feeds | Hash by user_id | Single-shard read for user's feed |
| Posts | Hash by author_id | Co-locate author's posts |
| Social graph | Hash by follower_id | Efficient "who do I follow" |
| Feed metadata | Same as user feeds | Co-located with feed data |
| Ranking features | Hash by user_id | Fast feature lookup |

---

## Part 4: Failure Modes and Operational Reality

#### Quick Visual: Failure Mode Decision Tree

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WHAT FAILED? QUICK DIAGNOSIS                             │
│                                                                             │
│   Symptom                     │ Likely Cause      │ First Action            │
│   ────────────────────────────┼───────────────────┼─────────────────────────│
│   All writes failing          │ Leader down       │ Promote replica         │
│   Some reads stale            │ Replication lag   │ Route to leader         │
│   Latency spikes on 1 shard   │ Hot partition     │ Enable cache            │
│   Partial users affected      │ Shard down        │ Failover shard          │
│   Data inconsistent           │ Split brain       │ FENCE NOW!              │
│   Everything slow             │ Network partition │ Investigate network     │
│                                                                             │
│   PRIORITY ORDER:                                                           │
│   1. Split brain → Fence immediately (data loss risk)                       │
│   2. Leader down → Promote replica (service down)                           │
│   3. Hot partition → Cache/shed load (degraded service)                     │
│   4. Replication lag → Route around (stale reads acceptable short-term)     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Replication Failure Modes

| Failure | Symptoms | Detection | Recovery |
|---------|----------|-----------|----------|
| **Leader crash** | Writes fail, replication stops | Health check, heartbeat | Promote replica, redirect traffic |
| **Follower crash** | Reduced read capacity | Health check | Restart, catch up from binlog |
| **Replication lag** | Stale reads | Lag monitoring | Investigate root cause, maybe skip to head |
| **Split brain** | Two nodes think they're leader | Fencing, consensus | Forcibly fence one, reconcile data |
| **Network partition** | Timeouts, partial failures | Connectivity monitoring | Wait for heal, or force one side down |

**Split Brain Deep Dive:**

This is the scariest failure mode. Two nodes accept writes independently.

```
Normal:
┌────────┐         ┌────────┐
│ Leader │────────▶│Follower│
│   ✓    │         │        │
└────────┘         └────────┘

Network Partition:
┌────────┐    X    ┌────────┐
│ Leader │    X    │Follower│
│ (real) │    X    │(thinks │
│        │    X    │it's    │
└────────┘         │leader) │
                   └────────┘

Both accepting writes = DATA DIVERGENCE
```

**Prevention:**
- Quorum-based leader election
- Fencing tokens (STONITH: Shoot The Other Node In The Head)
- Lease-based leadership with strict timeouts

```
FENCING TOKENS (prevent split-brain writes)
───────────────────────────────────────────
Leader side:
  acquire_leadership():
    token = consensus.increment_and_get("leader_token")
    current_token = token
    RETURN token
  
  write(data):
    storage.write(data, fencing_token=current_token)

Storage side:
  write(data, fencing_token):
    IF fencing_token < highest_seen_token:
      THROW StaleLeaderError("You've been fenced")
    highest_seen_token = fencing_token
    // Proceed with write

// If old leader wakes up and tries to write with old token → REJECTED
```

---

### Blast Radius Quantification per Failure Type

Staff engineers quantify impact, not just identify failures. Here's the exact blast radius for each failure mode.

#### Blast Radius Matrix

| Failure Type | % Users Affected | Duration | Recovery Action | Business Impact |
|--------------|------------------|----------|-----------------|-----------------|
| **Single replica down** | 0% (if quorum intact) | 5-30 min | Failover to other replicas | 33% read capacity reduction, no data loss |
| **Primary down (async replication)** | 0% (failover) | 1-5 min | Promote replica, redirect writes | Brief write unavailability, potential data loss window |
| **Primary down (sync replication)** | 0% (failover) | 1-5 min | Promote replica, redirect writes | Brief write unavailability, zero data loss |
| **Shard failure (16 shards)** | 6.25% (1/16) | 5-30 min | Failover to shard replica | Isolated to one shard's users, N-1/N unaffected |
| **Shard failure (64 shards)** | 1.56% (1/64) | 5-30 min | Failover to shard replica | Even smaller blast radius, 98.44% unaffected |
| **Replication lag > 30s** | 70-80% (all read-replica users) | Until lag resolves | Investigate root cause, possibly throttle writes | Stale data visible, user confusion, potential revenue impact |
| **Replication lag > 5min** | 70-80% | Until lag resolves | Emergency: promote lagging replica or reduce write load | Critical: users see data from hours ago, major UX degradation |
| **Cross-shard query failure** | 5-15% (features using cross-shard joins) | Until query fixed | Fallback to degraded mode or fix query | Isolated to specific features, core functionality works |
| **Router failure** | 100% | Until router restarted | Restart router instance, failover to backup | Complete outage, but typically < 1 min recovery |
| **Rebalancing failure mid-migration** | 5-15% (affected key range) | Until rollback completes | Rollback migration, restore from backup | Data in affected range unavailable, but bounded |
| **Split-brain (2 primaries)** | 50% (half see one primary, half see other) | Until resolved | Fence one primary, reconcile data | Data divergence, potential corruption, requires manual reconciliation |
| **Network partition (quorum lost)** | 0-100% (depends on partition) | Until network heals | Wait for heal or force one side down | CP system: rejects all writes, AP system: accepts writes (divergence risk) |

#### Detailed Blast Radius Analysis

**Single Replica Down: 0% Users Affected, But 33% Capacity Reduction**

```
Scenario: 3 read replicas, 1 fails

User impact: 0% (other 2 replicas handle all reads)
Capacity impact: 33% reduction (from 3 replicas to 2)

Latency impact:
- Before: p99 latency 50ms (load balanced across 3)
- After: p99 latency 75ms (load balanced across 2)
- If already at 80% capacity: May hit 100%, latency spikes to 200ms+

Staff insight: "0% users affected" is misleading. Capacity reduction can cause cascading failures if system is near limits.
```

**Shard Failure: 1/N of Users Completely Down, N-1/N Unaffected**

This is WHY we shard—natural blast radius isolation.

```
Scenario: 16 shards, shard 7 fails

User impact:
- Shard 7 users: 100% down (6.25% of total users)
- Other 15 shards: 0% impact (93.75% of users unaffected)

Recovery:
- Failover to shard 7 replica: 5-15 min
- During failover: Shard 7 users see errors
- After failover: Shard 7 users back online

Contrast with single-node failure:
- Single node down: 100% of users affected
- Shard down: 6.25% of users affected

Staff insight: Sharding provides natural fault isolation. This is an underappreciated benefit beyond just scaling.
```

**Replication Lag > 30s: All Read-Replica Users See Stale Data**

```
Scenario: 70% of reads go to replicas, replication lag spikes to 30s

User impact: 70-80% of users see stale data
- Profile updates: Not visible for 30s
- New posts: Missing for 30s
- Likes/comments: Delayed by 30s

Business impact:
- User confusion: "Why didn't my update save?"
- Support tickets: Spike in "data not updating" complaints
- Revenue impact: If pricing/catalog data stale, potential revenue loss

Duration: Until lag resolves (could be minutes to hours)

Staff insight: Replication lag is a silent killer. Users don't see errors, they see wrong data. Hard to detect without monitoring.
```

**Cross-Shard Query Failure: Only Features Using Cross-Shard Joins Affected**

```
Scenario: Feed feature requires joining user data across shards, query fails

User impact: 5-15% (only users using feed feature)
- Feed: Broken
- Profile: Works (single-shard query)
- Messages: Work (single-shard query)
- Search: Works (uses separate search index)

Isolated blast radius: Core functionality unaffected, only specific feature down

Recovery options:
1. Fallback: Show cached feed (stale but functional)
2. Degraded mode: Show feed without cross-shard data
3. Fix query: Usually 10-30 min

Staff insight: Cross-shard queries are architectural debt. They break isolation. Prefer denormalization.
```

**Rebalancing Failure Mid-Migration: Affected Key Range Unavailable**

```
Scenario: Migrating 20% of users from shard 3 to shard 7, migration fails halfway

User impact: 5-15% (users in affected key range)
- Users being migrated: Data unavailable (in limbo between shards)
- Users not being migrated: Unaffected

Data state:
- Some data copied to shard 7, some still on shard 3
- Router doesn't know which shard has which data
- Queries may return 404 or wrong data

Recovery:
- Rollback: Restore from backup, revert router config (30-60 min)
- Or: Complete migration manually (2-4 hours)

Staff insight: Rebalancing is risky. Always have rollback plan. Test on staging with production-like data volumes.
```

#### Staff Insight: Sharding Provides Natural Blast Radius Isolation

This is an underappreciated benefit of sharding beyond just scaling:

```
Single-node architecture:
- Node failure → 100% users affected
- No natural isolation

Sharded architecture:
- Shard failure → 1/N users affected
- Natural fault boundaries
- Can design features to be shard-local (zero cross-shard dependencies)

Example: User profile service
- Sharded by user_id
- Profile reads/writes: Single shard (isolated)
- Feed (requires cross-shard): Separate service, can fail independently
- Messages (shard-local): Isolated from feed failures

Result: Shard failure affects 6% of users, not 100%
```

**Quantification**: In a 16-shard system, a single shard failure affects 6.25% of users. In a 64-shard system, it's 1.56%. This natural isolation is why companies like Facebook, Twitter, and Instagram shard aggressively—not just for scale, but for fault tolerance.

---

### 4.1A Real Incident: Replication Lag and Stale Read Cascade

| Field | Details |
|-------|---------|
| **Context** | Large e-commerce platform. User database: 1 primary + 6 read replicas. 95% of reads routed to replicas. Write-flag routing for read-your-writes: 30-second TTL after writes. |
| **Trigger** | Nightly analytics batch job (scheduled 2 AM) was upgraded to run more complex aggregations. Unintentionally, it issued 50K heavy queries against the primary instead of being routed to a dedicated analytics replica. |
| **Propagation** | Primary CPU spiked to 95%. WAL replication lag grew from 50ms to 45 seconds within 8 minutes. Application read routing: users who had written in last 30s were sent to primary; others to replicas. Primary became saturated. Writes queued; read-your-writes routing sent more traffic to primary; positive feedback loop. |
| **User impact** | 70% of users saw stale data (cart updates, inventory, pricing). Checkout failures for users who had just added items. Support tickets spiked 400%. Duration: 42 minutes until batch job was killed and lag recovered. |
| **Engineer response** | On-call received alert (replication lag > 5s) but initially assumed transient. Paged secondary after 15 min. Identified batch job via query logs. Killed batch job; lag dropped within 10 min. Added circuit breaker: if lag > 10s, route all reads to replicas and accept staleness; primary reserved for writes only. |
| **Root cause** | Analytics batch misconfigured to run against primary. No query-class separation (analytics vs. transactional). No circuit breaker for replication lag. |
| **Design change** | 1) Dedicated analytics replica, excluded from read pool. 2) Query-class routing: heavy analytics never hit primary. 3) Lag-aware circuit breaker: beyond 10s lag, fail "open" to stale reads rather than overload primary. 4) Batch job resource limits and time-of-day isolation. |
| **Lesson learned** | Replication lag is a silent killer—users see wrong data, not errors. Separate read pools by workload class. Staff engineers ask: "What happens when the primary is slow?" not just "What happens when it's down?" |

---

### 4.1B Degradation Ladder: How Replicated and Sharded Systems Degrade Gracefully

Staff Engineers don't design binary systems (working/broken). They design explicit degradation levels.

**Replication Degradation Ladder:**

| Level | Trigger | System Behavior | User Experience | Automatic? |
|---|---|---|---|---|
| **L0: Healthy** | All replicas in sync, lag < 100ms | Full read/write, reads distributed across replicas | Normal — fast reads, fast writes | N/A |
| **L1: Elevated lag** | Replication lag > 1s | Route sensitive reads to primary, non-sensitive to replicas | Slightly slower for profile updates; feeds may be 1-2s stale | Yes — automatic routing |
| **L2: Replica down** | 1 of N replicas unreachable | Remaining replicas absorb read load; capacity reduced by 1/N | Slightly higher latency (fewer replicas); no errors | Yes — health check removes node |
| **L3: Quorum risk** | Only majority+1 replicas alive | All reads routed to primary; replicas marked unhealthy | Higher latency; write-heavy periods may queue | Yes — failover routing |
| **L4: Read-only mode** | Primary unreachable, replicas available | Serve stale reads from replicas; reject all writes | "Read-only mode — changes temporarily unavailable" | Semi-auto (requires operator confirmation for safety) |
| **L5: Full outage** | All replicas unreachable | Return cached data if available; otherwise error | "Service temporarily unavailable" with cached content | Yes — cache fallback |

**Sharding Degradation Ladder:**

| Level | Trigger | System Behavior | User Experience | Automatic? |
|---|---|---|---|---|
| **L0: Healthy** | All shards operational | Full functionality across all users | Normal | N/A |
| **L1: Hot shard** | One shard at 80%+ capacity | Rate limit requests to hot shard; serve others normally | Users on hot shard see slightly slower responses | Yes — adaptive throttling |
| **L2: Shard degraded** | One shard's primary slow (> 500ms p99) | Route reads to shard replica; queue writes | Users on degraded shard see stale reads; writes queue | Yes — automatic routing |
| **L3: Shard down** | One shard completely unreachable | Return cached data for affected users; reject writes for that shard | 1/N of users see cached/stale data + "temporarily read-only" | Yes — cache fallback |
| **L4: Multiple shards down** | > 1 shard unreachable | Global degraded mode: disable non-critical features, serve cached data | "Limited functionality — some features temporarily unavailable" | Semi-auto (IC decides scope) |
| **L5: Shard map corrupted** | Routing table inconsistent | Emergency: halt writes, serve from cache, rebuild routing table | "Maintenance mode — please try again later" | No — requires manual intervention |

**Key Design Principles:**

1. **Each level must be automatically detectable** — don't rely on humans to notice degradation at 3 AM
2. **Each level must be independently recoverable** — L3 should recover to L2 to L1 to L0, not require a jump to L0
3. **Communication must change per level** — users see different messaging at each level
4. **Monitoring must track WHICH level you're at** — dashboard should show current degradation level per shard and per replica set
5. **Blast radius narrows with sharding** — shard failure only affects 1/N of users (this is a key benefit of sharding that's often overlooked)

**Staff Insight:** "The most valuable property of a degradation ladder is that it buys you TIME. Instead of 'everything is on fire,' you have 'we're at L2, we have 30 minutes before L3 if we don't fix the lag.' That changes incident response from panic to procedure."

---

### 4.2 Sharding Failure Modes

| Failure | Symptoms | Detection | Recovery |
|---------|----------|-----------|----------|
| **Shard unavailable** | Partial outage (subset of users) | Health checks | Failover or wait |
| **Hot shard** | Latency spike on one shard | Latency monitoring | Rebalance, split |
| **Routing failure** | Wrong data returned, 404s | Consistency checks | Fix routing logic |
| **Cross-shard corruption** | Data appears in wrong shard | Periodic audits | Manual migration |
| **Resharding gone wrong** | Mixed data, missing data | Verification scripts | Rollback, retry |

**Hot Shard Runbook:**

```
1. DETECT
   - Alert fires: shard_latency_p99 > threshold
   - Check metrics dashboard for shard distribution

2. DIAGNOSE
   - Identify hot keys: query slow_log, trace requests
   - Determine cause: data skew? access skew? viral content?

3. MITIGATE (short term)
   - Enable caching for hot keys
   - Apply rate limiting to hot keys
   - Shift traffic from affected shard if possible

4. REMEDIATE (long term)
   - Split the hot shard
   - Redesign partitioning for hot keys
   - Add dedicated infrastructure for VIP keys

5. POST-MORTEM
   - Why wasn't this predicted?
   - How can we detect earlier next time?
   - Update capacity planning models
```

---

### 4.3 Staff-Level Trade-offs Matrix

| Dimension | Choice A | Choice B | How to Decide |
|-----------|----------|----------|---------------|
| **Consistency** | Strong (sync replication) | Eventual (async) | Data sensitivity, latency budget |
| **Availability** | Fail closed (reject if uncertain) | Fail open (best effort) | Safety vs. user experience |
| **Partition tolerance** | Favor consistency (CP) | Favor availability (AP) | Business requirements |
| **Complexity** | Simple (fewer shards) | Complex (more shards) | Team capacity, growth rate |
| **Cost** | Over-provision (headroom) | Right-size (efficiency) | Budget, scaling speed needed |

**The Hard Questions You'll Face:**

1. **"Should we shard now or wait?"**
   - Early: Pay complexity cost longer, but smoother scaling
   - Late: Simpler for now, but painful migration later
   - Answer: Shard when write bottlenecks are 6-12 months away

2. **"How many shards?"**
   - Too few: You'll need to reshard soon
   - Too many: Operational overhead, underutilized resources
   - Answer: 2-4x your current needs, with consistent hashing for easy expansion

3. **"Synchronous or asynchronous replication?"**
   - Sync: Pay latency for durability
   - Async: Fast but risk data loss
   - Answer: Semi-sync for critical data, async for everything else

4. **"Should we build or buy?"**
   - Build: Control, customization, learning
   - Buy: Speed, reliability, focus on business logic
   - Answer: Buy unless you have genuine unique requirements AND capacity

---

### Cost Reality: What Replication and Sharding Actually Cost

Staff engineers don't just architect systems—they quantify the cost of every decision. Here's what replication and sharding actually cost at scale.

#### Cost Comparison: Single Node vs. Read Replicas vs. Sharding

| Scale | Single Node | 3 Read Replicas | 16 Shards (P+R each) | Cost Multiplier |
|-------|-------------|-----------------|---------------------|-----------------|
| **1M users** | $500/month | $2,000/month | $8,000/month | 4x → 16x |
| **10M users** | $2,000/month | $8,000/month | $32,000/month | 4x → 16x |
| **100M users** | $10,000/month | $40,000/month | $160,000/month | 4x → 16x |

*Assumptions: AWS RDS PostgreSQL, db.r5.xlarge (4 vCPU, 32GB RAM) for primary, db.r5.large for replicas, 1TB storage, multi-AZ enabled*

#### Top 2 Cost Drivers

**1. Network Bandwidth for Replication**

Replication isn't free. Every write to the primary must be replicated to all replicas:

```
Write amplification:
- Primary write: 1KB
- Replication to 3 replicas: 3KB additional network traffic
- At 10K writes/sec × 1KB = 10MB/sec × 3 replicas = 30MB/sec sustained
- Monthly cost: ~$200-400/month for inter-AZ data transfer
```

At 100K writes/sec, replication bandwidth alone costs $2,000-4,000/month. This is often overlooked until the AWS bill arrives.

**2. Operational Complexity Multiplier per Shard**

Each shard multiplies operational overhead:

| Operation | Single Shard | 16 Shards | Multiplier |
|-----------|--------------|-----------|------------|
| Schema migrations | 1 execution | 16 coordinated executions | 16x |
| Backup verification | 1 check | 16 checks | 16x |
| Monitoring alerts | 1 alert config | 16 alert configs | 16x |
| Incident response | 1 on-call | 16 potential incidents | 16x |
| Capacity planning | 1 forecast | 16 forecasts | 16x |

**Hidden cost**: A schema migration that takes 5 minutes on a single node takes 80 minutes across 16 shards (sequential) or requires sophisticated coordination (parallel with rollback complexity). Staff engineers budget 2-3x calendar time for sharded migrations.

#### Dollar-Value Example: 10M User System

```
Scenario: Social media app at 10M users

Option A: 3 read replicas
- Primary: $2,000/month
- 3 replicas: $6,000/month
- Network bandwidth: $300/month
- Total: $8,300/month
- Operational overhead: 0.2 FTE (1 engineer 1 day/month)

Option B: 16 shards (each with primary + 2 replicas)
- 16 primaries: $32,000/month
- 32 replicas: $48,000/month
- Network bandwidth: $2,400/month
- Total: $82,400/month
- Operational overhead: 1.5 FTE (3 engineers 50% time)

Difference: $74,100/month = $889,200/year

That difference funds:
- 8-10 senior engineers (at $150K/year fully loaded)
- OR 2-3 Staff engineers (at $300K/year fully loaded)
- OR entire infrastructure for 3-4 other services
```

**Staff insight**: The $74K/month difference isn't just infrastructure—it's opportunity cost. That money could fund features that drive revenue, not just scale.

#### Cost as a First-Class Constraint (Staff-Level Framing)

At L6, cost is not an afterthought—it shapes architecture from day one.

| Principle | What It Means | Why It Matters at L6 |
|-----------|---------------|----------------------|
| **Right-size before you scale** | Prove single-node limits before adding replicas or shards | Sharding costs 10–16x; over-provisioning burns budget for years |
| **Model cost before build** | Calculate infra + operational cost (FTE) before proposing design | Leadership expects ROI on complexity; quantify or face pushback |
| **Cost-aware degradation** | Cheaper fallbacks (cache, stale reads) before expensive failover | Not every failure needs full HA; cost-appropriate resilience |
| **Sustainability over heroics** | Automate ops; avoid designs that require constant heroism | On-call burnout is a cost; simple systems scale with team |

**Real example:** A team proposed 64 shards for "future growth." Staff Engineer: "Model when we hit 16-shard limits. If that's 4+ years out, start with 16. The $400K/year saved funds 2 Staff engineers." Leadership approved.

#### Security, Compliance, and Trust Boundaries (Data Sensitivity in Replication and Sharding)

Replication and sharding multiply trust boundaries. Staff engineers treat data sensitivity as a first-class design constraint.

| Concern | Implications | What Staff Engineers Do |
|---------|--------------|--------------------------|
| **Data residency** | EU GDPR, sector-specific rules. Data must stay in region. | Geographic sharding: shard by region, replicate only within region. Cross-region sync only for non-PII. |
| **Replication of sensitive data** | Every replica is a copy that can be compromised. | Sync replication for PII; fewer replicas for sensitive data. Encryption at rest and in transit. Audit logs for replica access. |
| **Shard key leakage** | Shard key often encodes user/tenant info. | Avoid PII in shard key; use opaque IDs. Directory-based sharding for tenant isolation without exposing tenant mapping. |
| **Cross-shard query exposure** | Scatter-gather can expose data across tenants if not isolated. | Enforce tenant_id in every query. Query validation layer rejects cross-tenant queries. |
| **Multi-leader conflicts** | Conflict resolution can merge data from different trust zones. | Avoid multi-leader for regulated data. If required, conflict resolution must preserve auditability. |

**Trust boundary diagram:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    TRUST BOUNDARIES IN SHARDED SYSTEMS                  │
│                                                                         │
│   App Tier (trusted)                                                    │
│        │                                                                │
│        ▼                                                                │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  ROUTER / SHARD MAP (high trust)                                │   │
│   │  • Knows key → shard mapping                                     │   │
│   │  • Must not leak tenant boundaries                               │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│        │                                                                │
│        ├──────────────────┬──────────────────┬──────────────────┬───   │
│        ▼                   ▼                  ▼                  ▼     │
│   Shard 0              Shard 1             Shard 2           Shard N     │
│   (tenant A–C)         (tenant D–F)        (tenant G–I)     (...)       │
│   │                                                                │   │
│   │  BOUNDARY: Shard must not serve data from another shard's      │   │
│   │  tenants. Enforce: tenant_id in WHERE clause, validated.     │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│   Replication: Each replica is a COPY. Same trust level as primary.     │
│   Compliance: If primary is in EU, replicas must be in EU (GDPR).       │
└─────────────────────────────────────────────────────────────────────────┘
```

**Trade-off:** Geographic sharding for compliance reduces flexibility (e.g., can't easily move users between regions). Document the trade-off; accept it for regulated workloads.

#### What Staff Engineers Intentionally Do NOT Build

**1. Over-sharding for growth that may never come**

```
Anti-pattern: "We'll need 64 shards in 2 years, so let's build for 64 now"
Reality: You're paying 64x operational complexity for capacity you may never need
Staff approach: Start with 4-8 shards, use consistent hashing, expand when metrics show need
```

**2. Custom rebalancing when database-native works**

```
Anti-pattern: Building custom shard rebalancing logic from scratch
Reality: PostgreSQL logical replication, MongoDB chunk migration, Cassandra nodetool all exist
Staff approach: Use database-native tools unless you have unique requirements (you probably don't)
```

**3. Cross-shard joins when denormalization is cheaper**

```
Anti-pattern: "We'll join user data across shards for the feed"
Reality: Cross-shard joins cost 10-100ms latency + 16x network overhead
Staff approach: Denormalize user data into feed shards, accept eventual consistency
Cost savings: $20K/month in reduced query complexity + infrastructure
```

#### Cost Scaling: Non-Linear Growth

Costs don't scale linearly. Each shard adds operational burden:

```
Linear assumption: 16 shards = 16x cost
Reality: 16 shards = 16x infrastructure + 2-3x operational complexity

Why non-linear?
- Monitoring: 16 shards require shard-aware dashboards (custom work)
- Incident response: Shard failures cascade (one shard down → load shifts → others fail)
- Schema changes: Must coordinate across all shards (exponential complexity)
- Capacity planning: Hot shards require rebalancing (ongoing work)
- Team training: Engineers must understand shard routing (knowledge overhead)
```

**Quantification**: A 5-person team can comfortably manage:
- Single node: 100% capacity
- 4 shards: 80% capacity (20% overhead)
- 16 shards: 50% capacity (50% overhead)
- 64 shards: 20% capacity (80% overhead)

At 64 shards, you need a dedicated platform team. That's 2-3 engineers × $300K/year = $600-900K/year in human cost, separate from infrastructure.

---

### 4.4 Monitoring and Observability for Sharded Systems

You cannot manage what you cannot measure. Sharded systems require specialized monitoring.

#### Essential Dashboards

**Dashboard 1: Shard Health Overview**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SHARD HEALTH DASHBOARD                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  SHARD STATUS                                    REPLICATION LAG        │
│  ┌──────────────────────────────────┐           ┌──────────────────┐    │
│  │ Shard 0  ● Healthy    [|||||||]  │           │ Shard 0: 45ms    │    │
│  │ Shard 1  ● Healthy    [|||||||]  │           │ Shard 1: 52ms    │    │
│  │ Shard 2  ⚠ Degraded   [|||||  ]  │           │ Shard 2: 8.5s ⚠  │    │
│  │ Shard 3  ● Healthy    [|||||||]  │           │ Shard 3: 38ms    │    │
│  │ Shard 4  ● Healthy    [|||||||]  │           │ Shard 4: 41ms    │    │
│  └──────────────────────────────────┘           └──────────────────┘    │
│                                                                         │
│  QPS BY SHARD (last 5 min)                      LATENCY P99 BY SHARD    │
│  ┌─────────────────────────────ß─────┐           ┌──────────────────┐    │
│  │    ████████████  Shard 0: 12.5K  │           │ Shard 0: 45ms    │    │
│  │    ████████████  Shard 1: 12.1K  │           │ Shard 1: 48ms    │    │
│  │    ██████████████████ Shard 2: 18.2K 🔥      │ Shard 2: 125ms ⚠ │    │
│  │    ████████████  Shard 3: 11.8K  │           │ Shard 3: 42ms    │    │
│  │    ████████████  Shard 4: 12.4K  │           │ Shard 4: 44ms    │    │
│  └──────────────────────────────────┘           └──────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Dashboard 2: Data Distribution**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    DATA DISTRIBUTION DASHBOARD                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  STORAGE BY SHARD                               ROW COUNT BY SHARD      │
│  ┌──────────────────────────────────┐           ┌──────────────────┐    │
│  │ Shard 0: ████████░░░ 156GB       │           │ Shard 0: 45.2M   │    │
│  │ Shard 1: ████████░░░ 162GB       │           │ Shard 1: 46.8M   │    │
│  │ Shard 2: ██████████████ 245GB ⚠  │           │ Shard 2: 72.1M ⚠ │    │
│  │ Shard 3: ████████░░░ 158GB       │           │ Shard 3: 44.9M   │    │
│  │ Shard 4: ████████░░░ 151GB       │           │ Shard 4: 43.2M   │    │
│  └──────────────────────────────────┘           └──────────────────┘    │
│                                                                         │
│  IMBALANCE ALERTS:                                                      │
│  ⚠ Shard 2 is 53% larger than average - consider splitting              │
│  ⚠ Shard 2 has 60% more rows than average - check for hot tenant        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Key Metrics to Collect

```
KEY METRICS TO COLLECT
──────────────────────
Per-shard metrics:
  shard_requests_total        [shard_id, operation: read/write]
  shard_request_duration_sec  [shard_id, operation] buckets: 1ms, 5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s
  shard_replication_lag_sec   [shard_id, replica_id]
  shard_size_bytes            [shard_id]
  shard_connection_pool_size  [shard_id, state: active/idle/waiting]

Cross-shard metrics:
  cross_shard_queries_total      [query_type]
  scatter_gather_shards_count    buckets: 1, 2, 4, 8, 16, 32, 64 shards
```

#### Alert Thresholds

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Replication lag | > 5 seconds | > 30 seconds | Route reads to leader |
| Shard latency P99 | > 100ms | > 500ms | Check for hot keys |
| Shard size imbalance | > 1.5x average | > 2x average | Plan split |
| Connection pool exhaustion | > 80% used | > 95% used | Scale pool or add replicas |
| Cross-shard query ratio | > 10% | > 25% | Review access patterns |
| Failover time | > 30 seconds | > 2 minutes | Review automation |

```
ALERTING RULES
──────────────
Alert: ShardReplicationLagHigh
  Condition: replication_lag_seconds > 5 for 1 minute
  Severity: warning
  Message: "Shard X replication lag is Ys"

Alert: ShardReplicationLagCritical
  Condition: replication_lag_seconds > 30 for 30 seconds
  Severity: critical
  Action: Route reads to leader
  Message: "CRITICAL: Shard X lag Ys"

Alert: HotShardDetected
  Condition: shard_requests > 2x average for 5 minutes
  Severity: warning
  Message: "Shard X receiving 2x average traffic"
```

#### Distributed Tracing for Sharded Queries

```
TRACED SHARD ROUTER
───────────────────
execute_query(query, shard_key):
  span = start_span("shard_query")
  
  shard_id = get_shard(shard_key)
  span.set("shard.id", shard_id)
  span.set("shard.key", shard_key)
  
  start = now()
  TRY:
    result = shards[shard_id].execute(query)
    span.set("shard.row_count", length(result))
    RETURN result
  CATCH Exception:
    span.set("error", True)
    span.set("error.message", error)
    THROW
  FINALLY:
    span.set("shard.duration_ms", (now() - start) × 1000)

scatter_gather(query):
  span = start_span("scatter_gather")
  span.set("scatter.shard_count", length(shards))
  
  results = []
  FOR each shard_id, shard in shards:
    child_span = start_span("shard_{shard_id}")
    child_span.set("shard.id", shard_id)
    results.append(shard.execute(query))
  
  span.set("gather.total_rows", sum(length(r) for r in results))
  RETURN merge(results)
```

---

### 4.5 Schema Evolution in Sharded Systems

Running migrations across shards is one of the most dangerous operations.

#### The Challenge

```
Problem: ALTER TABLE users ADD COLUMN preferences JSONB;

With 64 shards:
- Must run on all 64 shards
- Order matters (or does it?)
- Some shards might fail
- Application must handle mixed schema state
```

#### Strategy 1: Expand-Contract Pattern

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     EXPAND-CONTRACT MIGRATION                           │
│                                                                         │
│  PHASE 1: EXPAND (Add new column, nullable)                             │
│  ─────────────────────────────────────────────                          │
│                                                                         │
│     ALTER TABLE users ADD COLUMN preferences JSONB;                     │
│                                                                         │
│     - Run on all shards (can be parallel)                               │
│     - Old code continues working (ignores new column)                   │
│     - New code can start writing to new column                          │
│                                                                         │
│  PHASE 2: MIGRATE (Backfill data)                                       │
│  ────────────────────────────────                                       │
│                                                                         │
│     UPDATE users SET preferences = '{}' WHERE preferences IS NULL;      │
│                                                                         │
│     - Run in batches to avoid locking                                   │
│     - Can run during normal traffic                                     │
│                                                                         │
│  PHASE 3: CONTRACT (Add constraint, remove old code paths)              │
│  ─────────────────────────────────────────────────────────              │
│                                                                         │
│     ALTER TABLE users ALTER COLUMN preferences SET NOT NULL;            │
│                                                                         │
│     - Only after all code uses new column                               │
│     - Only after backfill complete on ALL shards                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Orchestrating Migrations Across Shards

```
SHARD MIGRATION ORCHESTRATOR
────────────────────────────
run_migration(ddl_statement, parallel=True):
  // Initialize state tracking
  FOR each shard:
    state_store.set(migration_id, shard.id, 'pending')
  
  IF parallel:
    run_parallel(ddl_statement)
  ELSE:
    run_sequential(ddl_statement)
  
  RETURN verify_all_complete()

migrate_shard(shard, ddl):
  state = state_store.get(migration_id, shard.id)
  
  IF state == 'complete':
    RETURN  // Idempotent - already done
  
  state_store.set(migration_id, shard.id, 'running')
  shard.execute(ddl)
  state_store.set(migration_id, shard.id, 'complete')

resume(ddl):  // Resume failed migration
  status = get_status()
  incomplete = shards WHERE status != 'complete'
  FOR each shard in incomplete:
    migrate_shard(shard, ddl)
```

#### Handling Mixed Schema State

During migration, some shards have new schema, some have old:

```
SCHEMA-AWARE REPOSITORY
───────────────────────
get_user(user_id):
  shard = get_shard(user_id)
  
  IF migration_tracker.is_complete('add_preferences', shard.id):
    // New schema - has preferences column
    RETURN shard.query("SELECT id, name, email, preferences FROM users WHERE id = ?")
  ELSE:
    // Old schema - set default value
    user = shard.query("SELECT id, name, email FROM users WHERE id = ?")
    user.preferences = {}  // Default
    RETURN user
```

**Staff-Level Insight:** Never make breaking schema changes. Use expand-contract. A "breaking" change (like renaming a column) becomes: add new column → backfill → migrate code → drop old column. Tedious? Yes. Safe? Also yes.

---

### 4.6 Testing Sharded Systems

Testing distributed systems is fundamentally harder than testing monoliths. Here's how to do it right.

#### Unit Testing Shard Routing

```
UNIT TEST: SHARD ROUTING
────────────────────────
test_same_key_same_shard():
  key = "user_12345"
  assert router.get_node(key) == router.get_node(key)  // Deterministic

test_distribution_evenness():
  FOR i = 0 to 10000:
    shard = router.get_node("user_{i}")
    distribution[shard]++
  
  // Each shard should have ~25% of keys
  FOR each shard:
    assert 20% < distribution[shard] < 30%

test_minimal_rebalancing_on_add():
  record initial_placement for 1000 keys
  router.add_node("s4")
  count keys that moved
  // Should move ~20% (1/5), not 80%
  assert 15% < moved < 25%
```

#### Integration Testing with Multiple Shards

```
FIXTURE: SHARDED DATABASE
─────────────────────────
Setup:
  Spin up 4 Postgres containers (ports 5432-5435)
  Wait for each to be ready
  Apply schema to all shards

Teardown:
  Stop and remove all containers


INTEGRATION TESTS
─────────────────
test_scatter_gather_aggregation():
  Insert 100 orders to each of 4 shards
  result = aggregate_orders_across_shards()
  assert result.count == 400

test_cross_shard_transaction_saga():
  create_user(shard=0, user="A", balance=100)
  create_user(shard=2, user="B", balance=50)
  
  // Successful transfer
  result = transfer_money("A", "B", amount=25)
  assert result.success
  assert get_balance("A") == 75
  assert get_balance("B") == 75
  
  // Failed transfer (insufficient funds) + rollback
  result = transfer_money("A", "B", amount=100)
  assert NOT result.success
  assert get_balance("A") == 75  // Unchanged (compensated)
  assert get_balance("B") == 75  // Unchanged
```

#### Chaos Engineering for Sharded Systems

```
CHAOS TESTS
───────────
test_single_shard_failure():
  kill_shard(2)
  
  // Other shards should work
  assert requests to shards [0, 1, 3] return 200
  
  // Shard 2 should fail gracefully
  assert requests to shard 2 return 503 "shard unavailable"

test_shard_failover():
  original_primary = get_primary(shard=1)
  kill_node(original_primary)
  
  wait(30 seconds)  // Failover timeout
  
  new_primary = get_primary(shard=1)
  assert new_primary != original_primary
  assert requests to shard 1 return 200

test_network_partition():
  create_partition([0, 1], [2, 3])  // Shards 0,1 can't reach 2,3
  
  assert aggregate_all_shards() THROWS TimeoutError
  assert single-shard requests work (200)
  
  heal_partition()
  assert aggregate_all_shards() succeeds

test_replication_lag_handling():
  inject_replication_lag(shard=0, lag_ms=5000)
  
  update_user("user_123", {name: "New Name"})
  user = get_user("user_123")
  
  // With read-your-writes handling, should get fresh data
  assert user.name == "New Name"
```

#### Migration Testing

```
MIGRATION TESTS
───────────────
test_migration_data_integrity():
  // Get checksums before
  for each shard in source_shards:
    before_checksums[shard.id] = checksum_all_tables()
  
  run ShardMigrator(source → target)
  
  // Verify all data present in target
  for each key:
    assert source_value == target_value

test_migration_under_load():
  start migration in background thread
  
  // Hammer with writes during migration
  for i = 0 to 10000:
    write_to_source(key_i, value_i)
  
  wait for migration to complete
  
  // Verify all writes made it
  for i = 0 to 10000:
    assert get_from_target(key_i) == value_i

test_migration_rollback():
  migrator.fail_at_percentage = 50%
  
  expect MigrationError when running
  
  rollback()
  
  // Source should be unchanged and serving
  for each key:
    assert source value exists
```

---

## Simple Example: Staff-Level Interview Answers

| Question | Weak Answer (L5) | Strong Answer (L6/Staff) |
|----------|------------------|--------------------------|
| "How would you shard this database?" | "Hash by user_id with 16 shards" | "Before deciding, I need to understand access patterns. What's the read/write ratio? Do we need range queries? Are there celebrity users who might cause hot spots? For user data, hash sharding works, but for time-series we'd want range-based..." |
| "What about replication lag?" | "We use async replication so there's some lag" | "Our p50 lag is 50ms, p99 is 200ms. For user-facing reads after writes, we route to leader for 30 seconds. For analytics queries, eventual consistency is fine. We alert if lag exceeds 5 seconds." |
| "How do you handle a hot partition?" | "Add caching" | "First, identify what's hot - data skew or access skew? For celebrity users, we salt their partition key. For viral content, we use a caching layer with request coalescing. Long-term, we might need dedicated shards for VIP customers." |
| "What if you need to change the partition key?" | "We'd do a migration" | "That's a major undertaking. We'd use double-write with gradual cutover: write to both old and new, backfill historical data, verify checksums, switch reads, then stop old writes. Expect 2-4 weeks for a large dataset." |
| "How many shards do you need?" | "Let's start with 8" | "Let me calculate: 500GB data ÷ 50GB target per shard = 10 shards minimum. Write throughput: 5000 WPS ÷ 1000 per shard = 5 shards. Read throughput with 2 replicas: 50K RPS ÷ (10K × 2) = 2.5 shards. So writes drive this - I'd go with 16 shards for 2-3 year headroom." |

---

## Part 5: Brainstorming Questions

Before diving into your homework, reflect on these questions. They don't have clean answers—that's the point.

### On Replication

1. **Your multi-leader setup has 0.1% conflict rate. Is that acceptable?**
   - What does 0.1% mean in absolute numbers for your system?
   - Are all conflicts equal, or are some catastrophic?
   - How would you even detect silent data loss from LWW?

2. **Replication lag is normally 50ms but spikes to 30 seconds during daily batch jobs. What do you do?**
   - Is this lag causing user-visible problems?
   - Can you reschedule the batch job?
   - Should you route reads away from laggy replicas?
   - Is this a hardware problem or a query problem?

3. **Your follower promotion took 3 minutes during the last outage. How do you get to 30 seconds?**
   - What took the time: detection, decision, or execution?
   - Can you pre-warm standby replicas?
   - Is your health check interval too long?
   - Do you have automation, or was it manual?

### On Sharding

4. **You sharded by user_id, but now your most important query is "all orders from yesterday." What now?**
   - This query requires scatter-gather to all shards
   - Options: secondary index, materialized view, CQRS pattern
   - How did this query become important? Could you have predicted it?

5. **One customer is 40% of your traffic. They want dedicated infrastructure. How do you deliver this without rebuilding everything?**
   - Can you route them to specific shards?
   - Can you create a "VIP shard" just for them?
   - What isolation guarantees do they actually need?
   - How do you charge for this?

6. **A resharding migration is stuck at 95% for 3 hours. Rollback or push forward?**
   - What's blocking the last 5%?
   - Is the system functional in this state?
   - What's the risk of rollback vs. forward?
   - Who's available to help, and what's their expertise?

### On Trade-offs

7. **Your consistency requirements differ by data type. Users are OK with eventual consistency for likes count but need strong consistency for payments. How do you architect this?**
   - Same database with different replication settings?
   - Different databases for different data types?
   - Application-level routing logic?

8. **Adding a shard takes your team 2 weeks of work. Growth requires adding 2 shards per quarter. Is this sustainable?**
   - 4 weeks per quarter = 1/3 of your team's capacity on sharding
   - When does automation investment pay off?
   - Can you automate partially? Fully?

---

## Part 6: Homework Assignment

### Assignment: Design and Defend a Sharding Strategy

**Scenario:**

You're building a ride-sharing platform (like Uber/Lyft). You have three main data stores:

1. **User Profiles**: 50M users, 10KB average size, read-heavy (100:1 read:write)
2. **Ride History**: 500M rides, 5KB average size, time-series access patterns
3. **Real-time Location**: 2M active drivers, updated every 5 seconds, read by nearby riders

**Requirements:**
- 99.9% availability
- Read latency p99 < 100ms
- Write latency p99 < 200ms
- Data must survive single datacenter failure

**Your Task:**

**Part A: Design** (2-3 pages)

For EACH data store, specify:
1. Sharding strategy (hash, range, hybrid) with justification
2. Partition key with rationale
3. Replication approach (sync/async, leader-follower/multi-leader)
4. Number of shards and how you arrived at that number
5. How you'll handle growth (resharding approach)

**Part B: Failure Analysis** (1-2 pages)

For the data store of your choice:
1. List the top 5 failure modes
2. For each failure mode, describe:
   - Detection mechanism
   - Impact to users
   - Recovery procedure
   - Prevention measures

**Part C: Defend** (1 page)

Write a brief document addressing:
1. The trade-off you're least comfortable with
2. What would make you change your design
3. What you'd do differently with unlimited budget
4. What you'd do if you had to launch in 2 weeks instead of 2 months

---

### Evaluation Criteria

**Strong Answer Characteristics:**
- Clear reasoning for each decision
- Awareness of alternatives not chosen
- Specific numbers with justification
- Realistic failure mode analysis
- Acknowledges uncertainty and trade-offs

**Red Flags:**
- "Just use Cassandra/DynamoDB/etc." without justification
- Ignoring operational complexity
- Over-engineering for hypothetical scale
- Under-engineering for stated requirements
- Not addressing the failure modes

---

## Conclusion: The Art of Scaling

Replication and sharding are not just technical patterns—they're organizational decisions with long-term consequences.

**What I've learned after scaling multiple systems:**

1. **Start simple, evolve deliberately.** Most systems don't need sharding. Most that do can start with 4-8 shards, not 256.

2. **The partition key is forever.** Changing it is a full migration. Spend the time to get it right.

3. **Replication lag will bite you.** Build for eventual consistency from the start, even if you don't think you need it.

4. **Hot partitions will happen.** Design monitoring to catch them early, and have a playbook ready.

5. **Automate operations.** Manual resharding, failover, and recovery don't scale. Automate or die.

6. **The team matters.** A complex sharding setup requires on-call engineers who understand it. Staff for the complexity you're creating.

Your job as a Staff Engineer isn't to build the most sophisticated distributed system. It's to build the simplest system that meets requirements—and to know when requirements change enough to warrant increased complexity.

Scale is not a goal. Serving users is. Keep that in focus, and the sharding decisions become clearer.

---

# Part 7: Staff-Level Coordination and Communication

Replication and sharding decisions aren't just technical—they have organizational impact. Staff engineers drive these decisions across teams.

## Coordinating Resharding Across Teams

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RESHARDING COORDINATION TIMELINE                          │
│                                                                             │
│   Week -4     Week -2      Week 0        Week 2        Week 4              │
│   ────────    ────────     ────────      ────────      ────────             │
│                                                                             │
│   PLANNING    PREPARATION  EXECUTION     VALIDATION    CLEANUP              │
│                                                                             │
│   • RFC to    • Schema     • Enable      • Verify      • Remove             │
│     eng leads   changes      double-       checksums     old shards         │
│   • Impact    • Client       write       • Monitor     • Update docs        │
│     analysis    library    • Backfill      latency    • Retro               │
│   • Timeline    updates    • Cutover     • Customer                         │
│   • Rollback  • Runbooks     (staged)      feedback                         │
│     plan                                                                    │
│                                                                             │
│   STAKEHOLDERS AT EACH PHASE:                                               │
│   ─────────────────────────────                                             │
│   Planning:    All dependent teams, SRE, Product                            │
│   Preparation: Dependent teams (for client updates)                         │
│   Execution:   SRE, On-call, Platform team                                  │
│   Validation:  Product, Customer success                                    │
│   Cleanup:     Engineering leads                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Cross-Team Communication Template

**Staff-Level Communication: Resharding Announcement**

```
TO: Engineering leads, SRE, Product
SUBJECT: [RFC] User Database Resharding - Q2 2024

SUMMARY:
We need to reshard the user database from 16 to 64 shards to support 
projected growth. This affects all services that query user data.

IMPACT:
• Teams affected: Auth, Profile, Billing, Analytics (4 teams)
• Client library update required: user-db-client v3.x → v4.x
• Expected downtime: Zero (online migration)
• Risk: Medium (well-tested pattern, but scale is new)

TIMELINE:
• Week 1-2: Client library updates (all teams)
• Week 3: Enable double-write (platform team)
• Week 4-6: Backfill and verification
• Week 7: Staged cutover (10% → 50% → 100%)
• Week 8: Cleanup and retro

YOUR ACTION REQUIRED:
• Auth team: Update user-db-client by April 15
• Profile team: Update user-db-client by April 15
• All teams: Review rollback procedure
• SRE: Review monitoring dashboards

DECISION DEADLINE: March 20
QUESTIONS/CONCERNS: Reply to this thread or join office hours (Thursday 2pm)
```

## Blast Radius Quantification for Common Failures

| Failure Scenario | Users Affected | Duration | Revenue Impact | Priority |
|-----------------|----------------|----------|----------------|----------|
| **Single shard down** | ~6% (1/16 shards) | Until failover (30s-2min) | Low-Medium | P1 |
| **Single shard degraded** | ~6% | Until diagnosed | Low | P2 |
| **Shard router down** | 100% | Until recovery | Critical | P0 |
| **Replication lag > 30s** | All users reading stale data | Until resolved | Low | P2 |
| **Split brain (2 leaders)** | ~6% (data corruption risk) | Until fenced | Critical | P0 |
| **Hot shard (latency spike)** | ~6-20% (spillover effects) | Until mitigated | Medium | P1 |
| **Cross-region replication failure** | 0% immediately; DR risk | Until restored | Low immediate | P2 |
| **Resharding stuck** | 0% if double-write active | Until resolved | Low | P2 |

## Staff-Level Reasoning: When to Push Back on Sharding

**Scenario: Product wants to shard a 50GB database**

L5 Response: "OK, I'll design the sharding strategy."

L6 Response: "Let me understand why we think we need sharding. 50GB fits comfortably on a single node with modern hardware. What problem are we trying to solve?
- If it's read scaling → read replicas are simpler
- If it's write scaling → what's our actual write QPS? Is query optimization possible?
- If it's for 'future growth' → let's model when we'd actually need it

Sharding adds significant operational complexity. I'd estimate 2-3 engineer-months to implement properly, plus ongoing maintenance cost. Unless we have a clear timeline where single-node limits are exceeded, I'd recommend investing in caching and query optimization first."

---

# Part 7B: Organizational Reality — Ownership and Human Failures

Staff engineers don't just design systems—they design organizational structures that prevent human error. Here's who owns what, and how humans break sharded systems.

## Ownership Model: Who Owns What

| Component | Owner | Responsibilities | Escalation Path |
|-----------|-------|-----------------|-----------------|
| **Shard map / routing logic** | Platform team | Maintains consistent hashing, shard assignment, router configuration | Staff Engineer + Platform Lead |
| **Rebalancing decisions** | Staff Engineer + Platform | When to rebalance, which shards, migration strategy | Engineering Director |
| **Shard-specific incidents** | Product team (with platform support) | On-call for their shard, debugging shard-specific issues | Platform team for infrastructure issues |
| **Schema changes** | Product team (coordinated) | Design schema, coordinate rollout across all shards | Platform team for migration tooling |
| **Monitoring & alerting** | Platform team | Shard-aware dashboards, per-shard alerts, capacity planning | Staff Engineer for alert tuning |
| **Backup & disaster recovery** | Platform team | Per-shard backups, restore procedures, DR drills | Staff Engineer for DR strategy |
| **Shard capacity planning** | Staff Engineer + Platform | Forecast growth per shard, identify hot shards, plan splits | Engineering Director for resource allocation |

### Cross-Team Coordination Requirements

**Resharding Requires Coordinated Downtime/Migration Windows**

```
Scenario: Need to split 8 shards into 16 shards

Coordination required:
1. Product teams: Feature freeze during migration (2-4 weeks)
2. Platform team: Execute migration, monitor, rollback if needed
3. SRE team: On-call coverage during migration window
4. Business: Communicate potential user impact (even if < 1%)

Timeline:
- Planning: 2 weeks (Staff Engineer + Platform)
- Execution: 1-2 weeks (Platform, with Product on standby)
- Stabilization: 1 week (all teams monitoring)

Staff insight: Resharding is an organizational event, not just a technical one. Budget 4-6 weeks calendar time.
```

**Schema Changes Must Be Rolled Across ALL Shards**

```
Scenario: Add new column to users table

Naive approach: "I'll just run ALTER TABLE on each shard"
Reality: Requires coordination, testing, rollback plan

Proper process:
1. Design: Product team designs schema change
2. Review: Staff Engineer reviews for sharding implications
3. Testing: Test on staging shards (mirror production)
4. Rollout: Platform team coordinates sequential rollout
   - Shard 0: Apply, verify, wait 1 hour
   - Shard 1: Apply, verify, wait 1 hour
   - ... repeat for all 16 shards
5. Rollback: If any shard fails, rollback all shards

Time: 2-3 days for 16 shards (vs. 5 minutes for single node)

Staff insight: Schema changes are 16x more expensive in a sharded system. Design schemas carefully upfront.
```

**Monitoring Must Be Shard-Aware**

```
Anti-pattern: Aggregate metrics across all shards
Example: "Average latency across all shards: 50ms" (hides hot shard at 500ms)

Staff approach: Per-shard monitoring
- Alert per shard: "Shard 7 latency > 200ms"
- Dashboard: Show all shards, highlight outliers
- Capacity planning: Track per-shard growth, not aggregate

Complexity: 16 shards = 16x alert configs, 16x dashboards (or shard-aware tooling)
```

## Human Failure Modes

Humans break sharded systems in predictable ways. Here's how to prevent each failure mode.

| Failure Mode | Frequency | Cost to Fix | Prevention |
|--------------|-----------|-------------|------------|
| **Wrong shard key selection** | Most common | Very expensive (resharding required) | Staff Engineer review, load testing |
| **Accidental data deletion during rebalancing** | Rare but catastrophic | Data loss, restore from backup | Automated backups, dry-run migrations |
| **Configuration drift across shards** | Common | Gradual degradation, hard to detect | Infrastructure as code, automated validation |
| **Promoting lagging replica during failover** | Occasional | Data loss, inconsistency | Automated lag checks, quorum requirements |
| **Cross-shard query in hot path** | Common | Latency spikes, cascading failures | Architecture review, performance testing |
| **Shard key not in WHERE clause** | Common | Full table scan across all shards | Query analyzer, automated checks |
| **Rebalancing during peak traffic** | Occasional | Service degradation | Change windows, capacity planning |

### Wrong Shard Key Selection (Most Common, Most Expensive)

```
Example: Sharded by user_id, but 80% of queries filter by created_at

Problem:
- Queries like "users created in last 7 days" hit ALL shards
- Each shard scans its entire user table
- 16 shards × full scan = 16x worse than single node

Cost to fix:
- Resharding: 2-3 engineer-months
- Migration: 1-2 weeks downtime
- Risk: Data loss if migration fails

Prevention:
- Staff Engineer reviews shard key selection
- Load test with realistic query patterns
- Model query distribution before sharding
```

### Accidental Data Deletion During Rebalancing

```
Example: Migration script has bug, deletes users instead of copying

Scenario:
1. Script: DELETE FROM shard_3 WHERE user_id IN (migrated_users)
2. Bug: Deletes ALL users from shard_3, not just migrated ones
3. Result: 6.25% of users deleted

Recovery:
- Restore from backup: 1-2 hours
- Replay transactions from WAL: 2-4 hours
- Total downtime: 3-6 hours

Prevention:
- Automated backups before migration
- Dry-run migrations on staging
- Two-person review of migration scripts
- Gradual rollout (migrate 1% first, verify, then 10%, then 100%)
```

### Configuration Drift Across Shards

```
Example: Shard 7 has different indexes than other shards

How it happens:
- Engineer adds index to shard 7 manually (urgent fix)
- Forgets to add to other shards
- Over time: Each shard drifts

Symptoms:
- Shard 7: Fast queries (has index)
- Other shards: Slow queries (missing index)
- Hard to detect: Aggregate metrics look fine

Prevention:
- Infrastructure as code (Terraform, Ansible)
- Automated validation: Compare configs across shards
- Schema migration tooling: Apply to all shards automatically
```

### Promoting Lagging Replica During Failover

```
Example: Primary fails, promote replica with 30s lag

Scenario:
1. Primary crashes
2. Automated failover promotes replica
3. Replica has 30s replication lag (wasn't checked)
4. Result: Last 30s of writes lost

Prevention:
- Check replication lag before promotion
- Require quorum (multiple replicas agree on promotion)
- Use semi-sync replication (at least one replica confirms write)
- Staff Engineer designs failover logic, not junior engineers
```

## Runbook: Shard X is Down

When a shard fails, follow this runbook. Staff engineers write these, not SREs.

```
INCIDENT: Shard X is down

STEP 1: Verify failure
- Check shard health endpoint: curl https://shard-X.internal/health
- Check metrics: Is shard X returning errors?
- Check logs: What errors are shard X returning?

STEP 2: Check if hash ring updated
- Is router aware shard X is down?
- Are requests still routing to shard X? (They shouldn't)
- If not updated: Manually update hash ring, redirect traffic

STEP 3: Verify failover to replica
- Is shard X replica healthy?
- Has replica been promoted to primary?
- Check replication lag: Is replica caught up?
- If lag > 5s: Wait for catch-up OR accept data loss window

STEP 4: Check dependent services
- Which services depend on shard X?
- Are they handling errors gracefully?
- Check error rates in dependent services

STEP 5: Communicate affected user segment
- Calculate: Shard X = 1/N of users (e.g., 6.25% for 16 shards)
- Notify: Product team, Support team, Leadership
- Message: "Shard 7 is down, affecting ~6.25% of users. Estimated recovery: 15 min"

STEP 6: Root cause analysis
- Why did shard X fail? (Disk full? OOM? Network partition?)
- Document: Add to postmortem, update runbook if needed

STEP 7: Prevent recurrence
- Fix root cause (if infrastructure issue)
- Update monitoring (if detection was slow)
- Update runbook (if steps were missing)
```

**Staff insight**: Runbooks aren't just for SREs. Product engineers who own shards need these. Write them proactively, test them in fire drills.

---

# Part 8: Interview Calibration for Replication and Sharding

## Staff vs. Senior: Contrast at a Glance

| Dimension | Senior (L5) | Staff (L6) |
|-----------|-------------|------------|
| **Scaling decision** | "We need read replicas" | "What's driving the load? Query optimization first, then replicas if needed." |
| **Shard count** | "Let's use 16 shards" | "50GB data ÷ 50GB target + 50% headroom = 16. Here's the math." |
| **Partition key** | "Hash by user_id" | "Primary access is by user_id; secondary is email. I'll need a lookup table." |
| **Failure handling** | "We have replicas for failover" | "Failover takes 30s; 6% of users affected per shard; we monitor lag and have a circuit breaker." |
| **Cost** | "Sharding costs more" | "16 shards = ~$82K/month vs. $8K for replicas. That's 1.5 FTE in ops. We model ROI." |
| **Replication lag** | "We use async replication" | "p99 lag is 200ms; we route to leader for 30s after writes. Alert if lag > 5s." |
| **Hot partition** | "Add caching" | "Is it data skew or access skew? Celebrity users get salting; viral content gets request coalescing." |
| **Communication** | Technical details only | "We need to decide now; sharding takes 4–6 months and we hit limits in 12." |

**Staff differentiator:** Staff engineers quantify, anticipate failure modes, and frame decisions for leadership. Senior engineers implement; Staff engineers decide *whether* to implement.

---

## Interviewer Probing Questions

When you discuss replication/sharding, expect these follow-ups:

| Your Statement | Interviewer Probe | What They're Testing |
|----------------|-------------------|---------------------|
| "I'll shard by user_id" | "What about queries by email?" | Secondary access patterns |
| "We'll use async replication" | "What happens if the leader crashes?" | Durability understanding |
| "16 shards should be enough" | "Show me your math" | Capacity planning rigor |
| "Consistent hashing for easy scaling" | "What's the rebalancing impact?" | Implementation knowledge |
| "We'll use 2PC for cross-shard transactions" | "What's the latency cost? Failure modes?" | Trade-off awareness |
| "Fan-out on write for the feed" | "What about celebrities with 50M followers?" | Edge case thinking |

## Common L5 Mistakes in Replication/Sharding Discussions

| Mistake | Why It's L5 | L6 Approach |
|---------|-------------|-------------|
| "We'll shard to scale" | Doesn't specify what's bottlenecked | "Writes are bottlenecked at 15K QPS; sharding addresses this" |
| "16 shards" without math | Arbitrary number | "50GB data / 50GB target + 50% headroom = 16 shards" |
| "Use Cassandra" | Tool-first thinking | "Need: high write throughput, eventual OK, partition tolerance" |
| Ignoring replication lag | Only considers happy path | "Lag is normally 50ms; we route to leader for 30s after writes" |
| "2PC for transactions" | Ignores latency cost | "2PC adds 100-200ms; acceptable for checkout, not for likes" |
| Not mentioning hot partitions | Assumes even distribution | "Celebrity accounts need salting or pull-based fan-out" |
| "Range sharding for user data" | Doesn't consider access patterns | "Hash for user lookups; range only if we need range queries" |

## L6 Signals Interviewers Look For

| Signal | What It Looks Like |
|--------|-------------------|
| **Access pattern analysis** | "Before choosing a partition key, I need to understand the query patterns. What's the primary access path?" |
| **Quantified capacity planning** | "500GB data, 10K WPS, 100K RPS. That's 10 shards minimum for data, 5 for writes, 5 for reads with replicas. I'd go with 16." |
| **Trade-off articulation** | "Async replication gives us lower latency but risks data loss on leader crash. For user profiles, that's acceptable. For payments, we need sync." |
| **Failure mode awareness** | "Split-brain is the scariest failure. We prevent it with fencing tokens and quorum-based leader election." |
| **Evolution thinking** | "We can start with 16 shards with consistent hashing. When we need to grow, we add nodes and only 1/N of data moves." |
| **Operational maturity** | "We'd monitor replication lag, per-shard latency, and cross-shard query ratio. Alert on lag > 5 seconds." |

## Sample L6 Answer: "How would you shard a user database?"

"Before I design, let me understand the access patterns. 

For user data, I expect:
- **Primary access**: Get user by ID (point queries)
- **Secondary access**: Login by email (lookup pattern)
- **Read/write ratio**: Probably 100:1 (read-heavy)
- **Data size**: Let's say 50M users at 10KB = 500GB

For point queries by user_id, hash-based sharding works well—each lookup hits exactly one shard.

For email lookups, I have options:
1. Secondary index: Small table mapping email→user_id, replicated
2. Scatter-gather: Query all shards (expensive, avoid if possible)

I'd choose option 1. The email index is maybe 2GB—easily replicated to all application servers.

**Shard count**: 500GB / 50GB target = 10 shards. With consistent hashing and 50% headroom, I'd start with 16 shards. This gives 3-4 years of growth.

**Replication**: Leader-follower per shard, semi-synchronous (wait for 1 replica). This balances durability and latency. For reads, I'd use read replicas with lag-aware routing—if lag exceeds 1 second, route to leader.

**Failure handling**: Each shard has 2 replicas. Single shard failure affects ~6% of users until failover (30 seconds target). We'd have automated leader election.

**Hot partition risk**: If some users are significantly larger, we might see imbalance. We'd monitor per-shard size and QPS, alert on 2x average, and be prepared to split.

**What I'd validate**: I'd want to confirm the email lookup frequency. If it's 50% of queries, I might consider double-sharding by both user_id AND email hash, accepting the complexity for performance."

---

## How to Explain Replication and Sharding to Leadership

Staff engineers translate technical decisions into business impact.

| Concept | Leadership Framing | Avoid |
|---------|--------------------|-------|
| **Why we're adding replicas** | "Read traffic has doubled. Replicas let us serve more users without slowing writes. Cost: ~$X/month; avoids outage risk during peak." | "We need read replicas for scaling." |
| **Why we're sharding** | "Our write capacity will be maxed in 9 months. Sharding gives us 3+ years of headroom. One-time cost: 2–3 engineer-months; ongoing: ~1.5 FTE for ops." | "We need to shard the database." |
| **Replication lag incident** | "Users saw stale data for 40 minutes because a batch job overloaded the primary. We've isolated analytics traffic and added a circuit breaker. Won't recur." | "We had replication lag." |
| **Shard failure** | "One shard failed; 6% of users were affected for 15 minutes. Others untouched. We've improved failover automation." | "The database had an issue." |

**Script for "should we shard?" conversation:** "I've modeled our growth. At current rates, we hit single-node limits in 12 months. Sharding takes 4–6 months to do properly. So we need to decide now. The alternative is to optimize further—we could gain 6 months. I recommend we optimize first and plan sharding for Q3."

---

## How to Teach This Topic (Mentoring and Tech Talks)

| Audience | Approach | Key Messages |
|----------|----------|--------------|
| **Junior engineers** | Start with "why": replication for durability and reads; sharding when writes bottleneck. Use diagrams. Avoid CRDTs and vector clocks initially. | "Don't shard until you need to. The partition key is forever." |
| **Senior engineers** | Deep dive into trade-offs: sync vs. async, 2PC vs. Saga, when to use each sharding strategy. Include failure modes and runbooks. | "Always quantify: shard count, failover time, blast radius." |
| **Interview prep** | Practice the "access pattern first" frame. Walk through: primary access → shard key → secondary access → indexes. Include capacity math. | "Ask clarifying questions before proposing a design." |
| **Tech talk (30 min)** | Outline: 1) When replication vs. sharding. 2) One sharding strategy in depth (e.g., hash-based). 3) One real failure (e.g., replication lag). 4) Takeaway: "Add complexity only when proven necessary." | Focus on one mental model per talk. |

**Teaching tip:** Use the "scaling ladder" diagram. Ask: "Where are we today? Where will we be in 12 months? What's the next rung we need?"

---

# Part 9: Final Verification — L6 Readiness Checklist

## Master Review Prompt Check (All 11 Checkboxes)

| # | Check | Status |
|---|-------|--------|
| 1 | Judgment and decision-making (when to scale, when to push back) | ✅ |
| 2 | Failure and incident thinking (partial failures, blast radius, real incident) | ✅ |
| 3 | Scale and time (growth over years, first bottlenecks, thresholds) | ✅ |
| 4 | Cost and sustainability (cost as first-class constraint, cost drivers) | ✅ |
| 5 | Real-world engineering (operational burdens, human errors, on-call) | ✅ |
| 6 | Learnability and memorability (mental models, one-liners, analogies) | ✅ |
| 7 | Data, consistency, and correctness (invariants, consistency models, durability) | ✅ |
| 8 | Security and compliance (data sensitivity, trust boundaries, residency) | ✅ |
| 9 | Observability and debuggability (metrics, logs, dashboards, tracing) | ✅ |
| 10 | Cross-team and org impact (ownership, coordination, stakeholder communication) | ✅ |
| 11 | Exercises and brainstorming (homework, reflection prompts, applied scenarios) | ✅ |

---

## L6 Dimension Coverage Table (A–J)

| Dim | Dimension | Coverage | Evidence |
|-----|------------|----------|----------|
| **A** | Judgment & decision-making | Strong | L5 vs L6 tables, decision trees, when-to-use guidance, "when to push back on sharding" |
| **B** | Failure & incident thinking | Strong | Blast radius matrix, degradation ladder, structured real incident, runbooks, split-brain |
| **C** | Scale & time | Strong | Quantitative thresholds, growth patterns, first bottlenecks, capacity planning formulas |
| **D** | Cost & sustainability | Strong | Cost comparison tables, cost as first-class constraint, operational overhead quantification |
| **E** | Real-world engineering | Strong | Human failure modes, ownership model, operational burdens, on-call runbooks |
| **F** | Learnability & memorability | Strong | Mental models, one-liners table, scaling ladder diagram, quick reference cards |
| **G** | Data, consistency & correctness | Strong | Consistency spectrum, CRDTs, durability trade-offs, invariants (2PC vs Saga) |
| **H** | Security & compliance | Strong | Trust boundaries, data residency, GDPR implications, shard key leakage |
| **I** | Observability & debuggability | Strong | Shard health dashboards, per-shard metrics, lag monitoring, tracing considerations |
| **J** | Cross-team & org impact | Strong | Coordination templates, stakeholder timeline, ownership model, resharding communication |

---

## Does This Section Meet L6 Expectations?

| L6 Criterion | Coverage | Notes |
|-------------|----------|-------|
| **Judgment & Decision-Making** | ✅ Strong | Decision trees, trade-off matrices, when-to-use guidance |
| **Failure & Degradation Thinking** | ✅ Strong | Extensive failure modes, runbooks, split-brain handling |
| **Implementation Depth** | ✅ Strong | Consistent hashing, CRDTs, vector clocks, Snowflake IDs |
| **Scale & Evolution** | ✅ Strong | Capacity planning, resharding strategies, growth patterns |
| **Operational Readiness** | ✅ Strong | Monitoring, alerting, schema evolution, testing |
| **Real-World Application** | ✅ Strong | User data, rate limiter, feed storage scenarios |
| **Interview Calibration** | ✅ Strong | Probing questions, L5 mistakes, L6 signals, sample answer |
| **Cross-Team Coordination** | ✅ Strong | Communication templates, stakeholder management |

## Staff-Level Signals Demonstrated in This Section

✅ Decision trees for replication type selection
✅ Quantified capacity planning with formulas
✅ Multiple sharding strategies with clear when-to-use guidance
✅ Deep implementation details (consistent hashing, CRDTs)
✅ Failure modes with blast radius and recovery procedures
✅ Hot partition mitigation strategies (coalescing, load shedding, auto-split)
✅ Cross-shard operation patterns (2PC, Saga, scatter-gather)
✅ Distributed ID generation trade-offs
✅ Applied scenarios with production-like complexity
✅ Operational concerns (monitoring, testing, schema evolution)
✅ Cross-team coordination and communication
✅ Interview-ready answer structures

## Key Takeaways for L6 Interviews

1. **Never jump to sharding** without proving single-node won't work
2. **Always quantify** your shard count with capacity math
3. **Consider all access patterns** before choosing partition key
4. **Address secondary lookups** explicitly (indexes, scatter-gather)
5. **Name your replication mode** and explain the trade-off
6. **Discuss failure modes** proactively, don't wait to be asked
7. **Acknowledge operational cost** of distributed systems
8. **Think about evolution** — how does this grow?

---

### Mental Models and One-Liners (Learnability & Memorability)

Staff engineers use compact mental models to reason quickly and teach others.

| Concept | One-Liner | Use When |
|---------|-----------|----------|
| **Replication vs. sharding** | "Replication scales reads; sharding scales writes." | Explaining when to use which. |
| **Async replication risk** | "You acknowledged the write before it survived." | Justifying sync for critical data. |
| **Shard key** | "The partition key is forever—choose wrong, pay for years." | Pushing back on rushed shard key selection. |
| **Hot partition** | "One key can burn one shard." | Explaining celebrity/viral skew. |
| **Consistent hashing** | "Add a shard, move 1/N of data—not 80%." | Justifying consistent hashing over modulo. |
| **Cross-shard cost** | "Every cross-shard query pays N round-trips." | Arguing for denormalization. |
| **Blast radius** | "Sharding gives you 1/N fault isolation." | Explaining why sharding helps resilience. |
| **Replication lag** | "Silent killer: users see wrong data, not errors." | Prioritizing lag monitoring. |
| **Scaling timing** | "Shard when write bottlenecks are 6–12 months away." | Pushing back on premature sharding. |

**Mental model: The scaling ladder**

```
Single node → Read replicas → Sharding → Multi-region
     ↑              ↑              ↑            ↑
  Optimize      Scale reads    Scale writes   Scale globally
  first         (cheap)        (expensive)    (very expensive)
```

**One-liner for leadership:** "We add complexity only when we've proven we need it. Sharding is a 3–6 month project; we start when metrics say we have 6–12 months until we hit limits."

---

*End of Volume 3, Part 2*

---

## Key Numbers to Remember

| Metric | Typical Value | Why It Matters |
|--------|---------------|----------------|
| **Replication lag (healthy)** | 10-100ms | Anything higher = investigate |
| **Replication lag (concerning)** | > 1 second | Start routing reads to leader |
| **Replication lag (critical)** | > 30 seconds | Failover may lose data |
| **Failover time (good)** | 10-30 seconds | Your downtime window |
| **Failover time (bad)** | > 2 minutes | Users are angry |
| **Shard count (start)** | 4-16 shards | Enough for 2-3 years |
| **Shard size (target)** | 100-500 GB | Manageable backups, migrations |
| **Cross-shard query ratio** | < 10% | Higher = bad shard key choice |
| **Hot shard threshold** | 2x average load | Time to split or cache |
| **Resharding frequency** | 1-2 years | More often = poor planning |
| **Virtual nodes per shard** | 100-200 | Good distribution in consistent hashing |
| **Scatter-gather timeout** | 100-500ms | Slowest shard = your latency |

---

## Simple Example: Interview Scenario

**Interviewer:** "Design a database for a social network with 500M users."

| Level | Response Approach |
|-------|-------------------|
| **L5 (Senior)** | "I'll use PostgreSQL with read replicas, shard by user_id using hash partitioning." |
| **L6 (Staff)** | "Let me first understand the access patterns. User profiles are read-heavy, so replicas help. But user feeds require fan-out - should we push or pull? For 500M users, I'd estimate 50TB+ data, so sharding is needed. Hash by user_id for profiles, but feed storage needs hybrid approach. What's our read/write ratio? What's the celebrity distribution?" |

**Key Difference:** L6 asks clarifying questions, considers access patterns, and proposes different strategies for different data types.

---

## Quick Reference Card

### Replication Decision Tree

```
Need to scale reads?
    YES → Add read replicas
        Need strong consistency?
            YES → Route reads to leader after writes
            NO  → Load balance across replicas

Need to survive datacenter failure?
    YES → Cross-region replication
        Can tolerate async replication lag?
            YES → Async (faster, cheaper)
            NO  → Sync (slower, durable)

Need low-latency writes in multiple regions?
    YES → Multi-leader replication
        Can your data model handle conflicts?
            YES → Implement conflict resolution
            NO  → Reconsider, or accept data loss
```

### Sharding Decision Tree

```
Hitting single-node limits?
    NO → Don't shard. Go home.
    YES → Can you optimize queries first?
        YES → Do that first.
        NO  → Proceed to sharding...

What's your primary access pattern?
    Point queries (by ID) → Hash-based sharding
    Range queries (by time/range) → Range-based sharding
    Both → Compound key or hybrid

How will you handle growth?
    Predictable growth → Plan shard count for 2-3 years
    Unpredictable growth → Use consistent hashing
```

### Capacity Planning Formula

```
Required Shards = max(
    Total Data Size / Target Shard Size,
    Total Write QPS / Per-Shard Write Capacity,
    Total Read QPS / (Per-Shard Read Capacity × Replicas)
)

Add 50% headroom for safety.
Round up to power of 2 for consistent hashing.
```

### Common Failure Modes Quick Reference

| Failure | Symptom | First Response |
|---------|---------|----------------|
| Leader crash | Writes fail | Promote replica |
| Replication lag spike | Stale reads | Route to leader |
| Hot shard | Latency spike | Enable caching |
| Split brain | Data divergence | Fence one side |
| Shard unavailable | Partial outage | Failover or wait |

### Migration Checklist

```
□ Backups verified and tested
□ Rollback plan documented
□ Monitoring dashboards ready
□ On-call team briefed
□ Customer communication prepared
□ Maintenance window scheduled
□ Double-write enabled and verified
□ Backfill progress tracking in place
□ Verification queries ready
□ Cutover runbook reviewed
```

### Key Metrics to Monitor

**Replication:**
- Replication lag (seconds behind leader)
- Replication throughput (bytes/second)
- Failover time (time to promote replica)

**Sharding:**
- Per-shard QPS and latency
- Shard size distribution
- Cross-shard query percentage
- Hot key detection

**Operations:**
- Migration progress percentage
- Data verification checksums
- Capacity utilization per shard

---
---

# Brainstorming Questions

## Understanding Replication

1. For a system you've built, what replication strategy is used? Is it the right one for the access patterns?

2. Think of a scenario where replication lag caused user-visible issues. How was it detected? How would you prevent it?

3. When would you choose multi-leader replication despite its complexity? What conflict resolution would you use?

4. How do you explain the difference between synchronous and asynchronous replication to a non-technical stakeholder?

5. What's the most dangerous failure mode in a replicated system? How would you design to prevent it?

## Understanding Sharding

6. For a large-scale system you know, how is data sharded? Would you make the same choice today?

7. When have you seen a poor shard key choice cause problems? What were the symptoms?

8. How do you handle the need for cross-shard queries? When is scatter-gather acceptable vs. unacceptable?

9. What's your process for deciding when to shard vs. when to optimize the existing system?

10. How do you plan for resharding before it becomes urgent? What signals tell you it's time?

## Applied Scenarios

11. Design a sharding strategy for a social network with 500M users. What's your shard key? Why?

12. You inherit a system with 100 shards but only 10 are hot. What do you do?

13. How would you migrate from a monolithic database to a sharded architecture with zero downtime?

14. What monitoring and alerting would you implement for a sharded system?

15. How do you explain sharding trade-offs to a product manager who wants "just make it faster"?

---

# Reflection Prompts

Set aside 15-20 minutes for each of these reflection exercises.

## Reflection 1: Your Scaling Intuition

Think about your approach to database scaling.

- When do you know it's time to add replicas vs. shards?
- Have you ever over-sharded too early? Under-sharded too late?
- Do you do capacity planning proactively or reactively?
- Can you estimate shard counts from requirements in your head?

For a system you know, calculate the ideal shard count from first principles.

## Reflection 2: Your Failure Mode Coverage

Consider how you think about replication and sharding failures.

- Do you know the failover time for your replicated systems?
- Have you tested what happens when a shard becomes unavailable?
- Can you explain what split-brain means and how you prevent it?
- Do you design for the "slow shard" problem or just the "dead shard" problem?

Write a failure mode analysis for a sharded system you've worked on.

## Reflection 3: Your Trade-off Communication

Examine how you discuss scaling decisions with stakeholders.

- Can you explain why sharding adds complexity in terms of operational cost?
- How do you justify the infrastructure cost of replication?
- Do you communicate the trade-offs of different replication modes clearly?
- Can you estimate the cost difference between approaches?

Practice explaining a sharding decision to both a technical lead and a product manager.

---

# Homework Exercises

## Exercise 1: Sharding Strategy Design

For each system, design a complete sharding strategy:

**System A: E-commerce orders table**
- 100M orders/year, 5-year retention
- Access patterns: by order_id (80%), by user_id (15%), by date range (5%)

**System B: IoT sensor data**
- 1M sensors, readings every 10 seconds
- Access: by sensor_id + time range (90%), aggregations across sensors (10%)

**System C: Multi-tenant SaaS**
- 10,000 tenants, varying sizes (some are 1000x larger than others)
- Access: always within a tenant, never cross-tenant

For each:
- Choose shard key with justification
- Calculate shard count
- Design for hot key mitigation
- Plan resharding strategy

## Exercise 2: Replication Mode Decision

For each scenario, choose the replication mode and justify:

1. Banking transaction log (never lose data, high availability)
2. Social media likes (high write volume, read-heavy)
3. User session store (low latency, acceptable loss)
4. Inventory system (consistency critical, moderate volume)
5. Analytics data warehouse (append-only, high volume)

Create a decision matrix showing your reasoning.

## Exercise 3: Failure Scenario Response

Design runbooks for these failure scenarios:

1. Primary database becomes unresponsive, replication lag is 30 seconds
2. One shard in a 16-shard cluster goes down, failover fails
3. Replication lag has been slowly growing over 24 hours
4. Hot shard detected with 5x average load
5. Split-brain detected in multi-leader setup

For each:
- Detection mechanism
- Immediate response
- Root cause investigation
- Recovery steps
- Prevention measures

## Exercise 4: Migration Planning

Plan a migration from:
- Single PostgreSQL (2TB, 10K QPS) to sharded architecture

Include:
- Phase breakdown with timeline
- Double-write strategy
- Backfill approach
- Verification process
- Cutover plan
- Rollback plan

## Exercise 5: Interview Practice

Practice explaining these concepts (3 minutes each):

1. "When would you use synchronous vs. asynchronous replication?"
2. "How do you choose a shard key for a user-facing system?"
3. "What happens when a shard fails in your design?"
4. "How do you handle cross-shard queries?"
5. "Walk me through capacity planning for a sharded database"

Record yourself and review for clarity, structure, and trade-off acknowledgment.

---

# Conclusion

Replication and sharding are fundamental to building systems that scale beyond a single node. The key insights from this section:

1. **Replication is for availability and read scaling.** Understand the trade-offs between sync and async replication, and when to use multi-leader.

2. **Sharding is for write scaling and data volume.** But it comes with complexity—don't shard until you've exhausted other options.

3. **The shard key determines everything.** Choose based on access patterns, not data characteristics. A bad shard key creates hot partitions.

4. **Plan for resharding from day one.** Use consistent hashing or logical sharding to make future splits easier.

5. **Failure modes multiply with distribution.** Understand what happens when replicas lag, shards fail, or split-brain occurs.

6. **Operational cost is real.** Sharded systems require more sophisticated monitoring, testing, and incident response.

In interviews, demonstrate that you understand both the power and the cost of these techniques. Don't reach for sharding by default—justify when it's needed. Don't ignore failure modes—address them proactively. That's Staff-level thinking.

---
