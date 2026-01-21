# Volume 3, Part 2: Replication and Sharding — Scaling Without Losing Control

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

```python
# Conceptual configuration (PostgreSQL-style)
synchronous_standby_names = 'FIRST 1 (replica1, replica2, replica3)'
# Wait for first one to respond, others are async
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

```python
# User service with read-your-writes guarantee
class UserService:
    def update_profile(self, user_id, data):
        result = self.leader_db.update(user_id, data)
        write_ts = result.timestamp
        
        # Store the write timestamp in user's session
        self.session.set(f"last_write:{user_id}", write_ts, ttl=30)
        return result
    
    def get_profile(self, user_id):
        last_write = self.session.get(f"last_write:{user_id}")
        
        if last_write:
            # User recently wrote, read from leader
            return self.leader_db.get(user_id)
        else:
            # No recent writes, followers are fine
            return self.follower_db.get(user_id)
```

This pattern—**write-flag routing**—is simple, effective, and handles 99% of read-your-writes scenarios.

#### Advanced Consistency Patterns (Staff-Level Deep Dive)

**Pattern 1: Causal Consistency with Logical Clocks**

Read-your-writes is just one guarantee. Full causal consistency ensures that if operation A happened before operation B, everyone sees A before B.

```python
from dataclasses import dataclass
from typing import Dict, Optional
import threading

@dataclass
class LogicalClock:
    """
    Lamport clock for establishing causal ordering.
    
    Rules:
    1. Increment before each local event
    2. On send: include clock value
    3. On receive: max(local, received) + 1
    """
    value: int = 0
    lock: threading.Lock = None
    
    def __post_init__(self):
        self.lock = threading.Lock()
    
    def increment(self) -> int:
        with self.lock:
            self.value += 1
            return self.value
    
    def update(self, received: int) -> int:
        with self.lock:
            self.value = max(self.value, received) + 1
            return self.value


class VectorClock:
    """
    Vector clock for detecting concurrent vs causal events.
    
    Each node maintains a vector of all node's clocks.
    Can determine: happened-before, happened-after, or concurrent.
    """
    
    def __init__(self, node_id: str, num_nodes: int):
        self.node_id = node_id
        self.node_index = hash(node_id) % num_nodes
        self.vector = [0] * num_nodes
    
    def increment(self) -> list:
        """Local event: increment own position."""
        self.vector[self.node_index] += 1
        return self.vector.copy()
    
    def update(self, received_vector: list) -> list:
        """Receive event: take element-wise max, then increment."""
        for i in range(len(self.vector)):
            self.vector[i] = max(self.vector[i], received_vector[i])
        self.vector[self.node_index] += 1
        return self.vector.copy()
    
    def compare(self, other_vector: list) -> str:
        """
        Compare two vector clocks.
        Returns: 'before', 'after', 'concurrent', or 'equal'
        """
        dominated = False  # self < other (at least one element)
        dominates = False  # self > other (at least one element)
        
        for i in range(len(self.vector)):
            if self.vector[i] < other_vector[i]:
                dominated = True
            elif self.vector[i] > other_vector[i]:
                dominates = True
        
        if dominated and not dominates:
            return 'before'
        elif dominates and not dominated:
            return 'after'
        elif not dominated and not dominates:
            return 'equal'
        else:
            return 'concurrent'  # Conflict!


class CausalConsistencyManager:
    """
    Ensure clients always see causally consistent data.
    
    Key insight: Client carries their "read position" and we ensure
    they never see data older than their position.
    """
    
    def __init__(self, replicas):
        self.replicas = replicas
        self.leader = replicas[0]
        
        # Each replica tracks its replication position
        self.replica_positions = {r.id: 0 for r in replicas}
    
    def write(self, key: str, value: any, client_position: int) -> dict:
        """
        Write to leader, return new position for client.
        """
        result = self.leader.write(key, value)
        new_position = result.log_position
        
        return {
            'success': True,
            'position': new_position,
            'value': value
        }
    
    def read(self, key: str, client_position: int) -> dict:
        """
        Read from replica that's caught up to client's position.
        """
        # Find a replica that's past the client's known position
        eligible_replicas = [
            r for r in self.replicas
            if self.replica_positions[r.id] >= client_position
        ]
        
        if not eligible_replicas:
            # No replica is caught up, must read from leader
            result = self.leader.read(key)
            return {
                'value': result.value,
                'position': result.log_position,
                'source': 'leader'
            }
        
        # Choose least-loaded eligible replica
        replica = min(eligible_replicas, key=lambda r: r.load)
        result = replica.read(key)
        
        return {
            'value': result.value,
            'position': max(client_position, result.log_position),
            'source': replica.id
        }
    
    def update_replica_position(self, replica_id: str, position: int):
        """Called by replicas as they apply replication log."""
        self.replica_positions[replica_id] = position
```

**Pattern 2: Session Consistency Across Services**

In microservices, consistency must span multiple databases:

```python
import jwt
from dataclasses import dataclass
from typing import Dict, List
import time

@dataclass
class CausalToken:
    """
    Token carrying causal dependencies across services.
    Passed in HTTP headers or message metadata.
    """
    positions: Dict[str, int]  # service_name -> log_position
    timestamp: float
    
    def to_header(self) -> str:
        return jwt.encode({
            'positions': self.positions,
            'timestamp': self.timestamp
        }, 'secret', algorithm='HS256')
    
    @classmethod
    def from_header(cls, header: str) -> 'CausalToken':
        data = jwt.decode(header, 'secret', algorithms=['HS256'])
        return cls(
            positions=data['positions'],
            timestamp=data['timestamp']
        )
    
    def merge(self, other: 'CausalToken') -> 'CausalToken':
        """Merge two tokens, keeping max positions."""
        merged_positions = {}
        all_services = set(self.positions.keys()) | set(other.positions.keys())
        
        for service in all_services:
            merged_positions[service] = max(
                self.positions.get(service, 0),
                other.positions.get(service, 0)
            )
        
        return CausalToken(
            positions=merged_positions,
            timestamp=max(self.timestamp, other.timestamp)
        )


class CausalMiddleware:
    """
    Middleware for maintaining causal consistency across services.
    """
    
    def __init__(self, service_name: str, db_client):
        self.service_name = service_name
        self.db = db_client
    
    def before_request(self, request):
        """Extract causal token from incoming request."""
        token_header = request.headers.get('X-Causal-Token')
        
        if token_header:
            token = CausalToken.from_header(token_header)
            
            # Wait for local DB to catch up to required position
            required_position = token.positions.get(self.service_name, 0)
            self._wait_for_position(required_position)
            
            request.causal_token = token
        else:
            request.causal_token = CausalToken(positions={}, timestamp=time.time())
    
    def after_write(self, request, write_position: int):
        """Update causal token after a write."""
        request.causal_token.positions[self.service_name] = write_position
        request.causal_token.timestamp = time.time()
    
    def before_response(self, request, response):
        """Include updated causal token in response."""
        response.headers['X-Causal-Token'] = request.causal_token.to_header()
    
    def _wait_for_position(self, required_position: int, timeout_ms: int = 5000):
        """Wait for replica to reach required position."""
        start = time.time()
        
        while True:
            current_position = self.db.get_replication_position()
            
            if current_position >= required_position:
                return
            
            elapsed_ms = (time.time() - start) * 1000
            if elapsed_ms > timeout_ms:
                # Timeout: fall back to leader
                raise ReplicaLagTimeout(
                    f"Replica not caught up to position {required_position}"
                )
            
            time.sleep(0.01)  # 10ms poll interval


# Usage in microservice
class OrderService:
    def __init__(self):
        self.causal = CausalMiddleware('order-service', self.db)
    
    def create_order(self, request, order_data):
        # Middleware ensures we see user's latest data
        self.causal.before_request(request)
        
        # Create order
        result = self.db.insert('orders', order_data)
        
        # Update causal position
        self.causal.after_write(request, result.log_position)
        
        # Response includes updated token
        response = Response({'order_id': result.id})
        self.causal.before_response(request, response)
        
        return response
```

**Pattern 3: Monotonic Reads Guarantee**

```python
class MonotonicReadsRouter:
    """
    Ensure each client never sees time go backwards.
    
    If client saw data at position 100, they should never
    subsequently see data from position 99.
    """
    
    def __init__(self, replicas, session_store):
        self.replicas = replicas
        self.session_store = session_store
    
    def get_client_position(self, client_id: str) -> int:
        return int(self.session_store.get(f"read_pos:{client_id}") or 0)
    
    def update_client_position(self, client_id: str, position: int):
        current = self.get_client_position(client_id)
        if position > current:
            self.session_store.set(f"read_pos:{client_id}", position, ttl=3600)
    
    def route_read(self, client_id: str, key: str) -> dict:
        min_position = self.get_client_position(client_id)
        
        # Find replicas that can satisfy monotonic read
        for replica in self.replicas:
            if replica.replication_position >= min_position:
                result = replica.read(key)
                
                # Update client's high-water mark
                self.update_client_position(client_id, result.position)
                
                return {
                    'value': result.value,
                    'position': result.position,
                    'replica': replica.id
                }
        
        # No replica caught up, use leader
        result = self.leader.read(key)
        self.update_client_position(client_id, result.position)
        
        return {
            'value': result.value,
            'position': result.position,
            'replica': 'leader'
        }


class SequentialConsistencyRouter:
    """
    Strongest practical guarantee: all clients see same order of operations.
    
    Implementation: All reads go through leader, or replicas with
    strong ordering guarantees.
    """
    
    def __init__(self, leader, replicas):
        self.leader = leader
        self.replicas = replicas
        self.global_position = 0
        self.lock = threading.Lock()
    
    def write(self, key: str, value: any) -> dict:
        with self.lock:
            result = self.leader.write(key, value)
            self.global_position = result.log_position
            return result
    
    def read(self, key: str) -> dict:
        # Wait for at least one replica to have our position
        target_position = self.global_position
        
        for replica in self.replicas:
            if replica.wait_for_position(target_position, timeout_ms=100):
                return replica.read(key)
        
        # Timeout: read from leader
        return self.leader.read(key)
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

```python
class GCounter:
    """
    A counter that only grows. Each node tracks its own increments.
    Merge = sum of all node values.
    
    Use case: Page view counts, like counts
    """
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.counts = {}  # node_id -> count
    
    def increment(self, amount: int = 1):
        """Increment local node's counter."""
        if self.node_id not in self.counts:
            self.counts[self.node_id] = 0
        self.counts[self.node_id] += amount
    
    def value(self) -> int:
        """Get total count across all nodes."""
        return sum(self.counts.values())
    
    def merge(self, other: 'GCounter') -> 'GCounter':
        """Merge with another counter - always converges!"""
        result = GCounter(self.node_id)
        all_nodes = set(self.counts.keys()) | set(other.counts.keys())
        
        for node in all_nodes:
            # Take max of each node's count (handles duplicate increments)
            result.counts[node] = max(
                self.counts.get(node, 0),
                other.counts.get(node, 0)
            )
        
        return result


# Example: Counting likes across US and EU datacenters
us_counter = GCounter("us-east")
eu_counter = GCounter("eu-west")

# US gets 100 likes
for _ in range(100):
    us_counter.increment()

# EU gets 50 likes
for _ in range(50):
    eu_counter.increment()

# Merge (can happen in either direction, result is same!)
merged = us_counter.merge(eu_counter)
print(f"Total likes: {merged.value()}")  # 150

# Even if we merge again, result is stable (idempotent)
merged_again = merged.merge(eu_counter)
print(f"Still: {merged_again.value()}")  # Still 150
```

**Example: OR-Set (Observed-Remove Set)**

```python
import uuid
from dataclasses import dataclass
from typing import Set, Dict, Any

@dataclass(frozen=True)
class Element:
    value: Any
    unique_id: str  # Makes each add unique

class ORSet:
    """
    A set that supports add and remove with proper conflict resolution.
    
    Key insight: Each add creates a new "version" with a unique ID.
    Remove only removes the versions we've seen, not future adds.
    
    Use case: Shopping cart items, user follows
    """
    
    def __init__(self):
        self.elements: Set[Element] = set()
        self.tombstones: Set[Element] = set()  # Removed elements
    
    def add(self, value: Any):
        """Add value with a unique ID."""
        element = Element(value=value, unique_id=str(uuid.uuid4()))
        self.elements.add(element)
    
    def remove(self, value: Any):
        """Remove all observed versions of this value."""
        to_remove = {e for e in self.elements if e.value == value}
        self.elements -= to_remove
        self.tombstones |= to_remove
    
    def contains(self, value: Any) -> bool:
        return any(e.value == value for e in self.elements)
    
    def values(self) -> Set[Any]:
        return {e.value for e in self.elements}
    
    def merge(self, other: 'ORSet') -> 'ORSet':
        """Merge two OR-Sets."""
        result = ORSet()
        
        # Union of all elements
        all_elements = self.elements | other.elements
        all_tombstones = self.tombstones | other.tombstones
        
        # Keep elements that aren't tombstoned
        result.elements = all_elements - all_tombstones
        result.tombstones = all_tombstones
        
        return result


# Example: Shopping cart on two devices
phone_cart = ORSet()
laptop_cart = ORSet()

# Add item on phone
phone_cart.add("milk")
phone_cart.add("bread")

# Add item on laptop (same time, offline)
laptop_cart.add("eggs")

# Merge carts - all items present!
merged = phone_cart.merge(laptop_cart)
print(merged.values())  # {'milk', 'bread', 'eggs'}

# Now remove milk on phone
phone_cart.remove("milk")

# Merge again - milk is gone (remove wins for seen versions)
final = phone_cart.merge(laptop_cart)
print(final.values())  # {'bread', 'eggs'}
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

```python
# Lag-aware replica selection
class ReplicaRouter:
    def get_replica(self, max_acceptable_lag_ms=1000):
        healthy_replicas = []
        
        for replica in self.replicas:
            lag = replica.get_replication_lag_ms()
            if lag < max_acceptable_lag_ms:
                healthy_replicas.append((replica, lag))
        
        if not healthy_replicas:
            # All replicas too laggy, fall back to leader
            return self.leader
        
        # Return least-laggy replica
        return min(healthy_replicas, key=lambda x: x[1])[0]
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

```python
def get_shard(key, num_shards):
    return hash(key) % num_shards
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

```python
import hashlib
import bisect
from typing import List, Dict, Any

class ConsistentHashRing:
    """
    Production-grade consistent hashing with virtual nodes.
    
    Virtual nodes solve the problem of uneven distribution
    when you have few physical nodes.
    """
    
    def __init__(self, nodes: List[str] = None, virtual_nodes: int = 150):
        self.virtual_nodes = virtual_nodes  # More = better distribution
        self.ring: Dict[int, str] = {}       # hash -> physical node
        self.sorted_keys: List[int] = []     # sorted hash positions
        
        if nodes:
            for node in nodes:
                self.add_node(node)
    
    def _hash(self, key: str) -> int:
        """MD5 provides good distribution. SHA256 for crypto needs."""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)
    
    def add_node(self, node: str) -> None:
        """Add a physical node with virtual_nodes positions on ring."""
        for i in range(self.virtual_nodes):
            # Each virtual node gets a unique position
            virtual_key = f"{node}:vn{i}"
            hash_val = self._hash(virtual_key)
            self.ring[hash_val] = node
            bisect.insort(self.sorted_keys, hash_val)
    
    def remove_node(self, node: str) -> None:
        """Remove all virtual nodes for a physical node."""
        for i in range(self.virtual_nodes):
            virtual_key = f"{node}:vn{i}"
            hash_val = self._hash(virtual_key)
            if hash_val in self.ring:
                del self.ring[hash_val]
                self.sorted_keys.remove(hash_val)
    
    def get_node(self, key: str) -> str:
        """Find the node responsible for this key."""
        if not self.ring:
            return None
        
        hash_val = self._hash(key)
        
        # Find first node position >= key's hash (walk clockwise)
        idx = bisect.bisect(self.sorted_keys, hash_val)
        
        # Wrap around if we've passed the last node
        if idx == len(self.sorted_keys):
            idx = 0
        
        return self.ring[self.sorted_keys[idx]]
    
    def get_nodes(self, key: str, count: int = 3) -> List[str]:
        """Get multiple nodes for replication."""
        if not self.ring:
            return []
        
        hash_val = self._hash(key)
        idx = bisect.bisect(self.sorted_keys, hash_val)
        
        nodes = []
        seen = set()
        
        for i in range(len(self.sorted_keys)):
            pos = (idx + i) % len(self.sorted_keys)
            node = self.ring[self.sorted_keys[pos]]
            
            if node not in seen:
                nodes.append(node)
                seen.add(node)
                
            if len(nodes) >= count:
                break
        
        return nodes


# Usage example
ring = ConsistentHashRing(
    nodes=["shard-0", "shard-1", "shard-2", "shard-3"],
    virtual_nodes=150  # 150 virtual nodes per physical shard
)

# Route a key
user_id = "user_12345"
shard = ring.get_node(user_id)
print(f"{user_id} -> {shard}")

# Add a new shard (only ~25% of keys move)
ring.add_node("shard-4")

# Get replicas for durability
replicas = ring.get_nodes(user_id, count=3)
print(f"{user_id} replicated to: {replicas}")
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

```python
SHARD_RANGES = [
    (0, 1000000, "shard_0"),
    (1000001, 2000000, "shard_1"),
    (2000001, 3000000, "shard_2"),
]

def get_shard(user_id):
    for (start, end, shard) in SHARD_RANGES:
        if start <= user_id <= end:
            return shard
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

```python
class ShardDirectory:
    def __init__(self):
        self.mapping = {}  # Loaded from database/cache
    
    def get_shard(self, key):
        return self.mapping.get(key)
    
    def set_shard(self, key, shard):
        self.mapping[key] = shard
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

```python
class CompoundShardKey:
    """
    Use multiple fields to create optimal sharding.
    
    Example: E-commerce orders
    - Primary access: "Get all orders for user X" 
    - Secondary access: "Get all orders for merchant Y"
    - Tertiary access: "Get orders by date range"
    
    Solution: Compound key that satisfies primary access pattern
    while allowing efficient secondary access.
    """
    
    def __init__(self, num_shards=64):
        self.num_shards = num_shards
        # Secondary index for cross-shard lookups
        self.merchant_index = {}  # merchant_id -> list of (shard, order_id)
    
    def get_shard_for_order(self, user_id: str, order_id: str) -> int:
        """Primary sharding by user_id - all user's orders co-located."""
        return hash(user_id) % self.num_shards
    
    def store_order(self, order):
        shard = self.get_shard_for_order(order.user_id, order.order_id)
        
        # Store in primary shard
        self.shards[shard].insert(order)
        
        # Update secondary index for merchant access
        if order.merchant_id not in self.merchant_index:
            self.merchant_index[order.merchant_id] = []
        self.merchant_index[order.merchant_id].append((shard, order.order_id))
    
    def get_user_orders(self, user_id: str) -> list:
        """Fast path: single shard lookup."""
        shard = self.get_shard_for_order(user_id, "")
        return self.shards[shard].query(f"user_id = '{user_id}'")
    
    def get_merchant_orders(self, merchant_id: str) -> list:
        """Slow path: scatter-gather using secondary index."""
        locations = self.merchant_index.get(merchant_id, [])
        
        orders = []
        # Group by shard for efficient batch queries
        by_shard = defaultdict(list)
        for shard, order_id in locations:
            by_shard[shard].append(order_id)
        
        for shard, order_ids in by_shard.items():
            orders.extend(self.shards[shard].get_by_ids(order_ids))
        
        return orders


class HierarchicalCompoundKey:
    """
    Multi-level compound key for complex hierarchies.
    
    Example: Chat messages in Slack-like app
    - Organization -> Workspace -> Channel -> Message
    
    Sharding strategy:
    - Shard by (org_id, workspace_id) - keeps workspace data together
    - Within shard, partition by channel_id for parallelism
    """
    
    def __init__(self, num_shards=256):
        self.num_shards = num_shards
    
    def get_shard(self, org_id: str, workspace_id: str) -> int:
        """All channels in a workspace are on same shard."""
        compound = f"{org_id}:{workspace_id}"
        return hash(compound) % self.num_shards
    
    def get_partition(self, channel_id: str) -> int:
        """Within-shard partitioning for parallelism."""
        return hash(channel_id) % 16  # 16 partitions per shard
    
    def get_messages(self, org_id, workspace_id, channel_id, limit=50):
        shard = self.get_shard(org_id, workspace_id)
        partition = self.get_partition(channel_id)
        
        return self.shards[shard].query(
            partition=partition,
            filter=f"channel_id = '{channel_id}'",
            order_by="timestamp DESC",
            limit=limit
        )
    
    def get_workspace_activity(self, org_id, workspace_id, since):
        """All channels in workspace - single shard query."""
        shard = self.get_shard(org_id, workspace_id)
        
        # Query all partitions in parallel within the shard
        return self.shards[shard].parallel_query(
            filter=f"timestamp > '{since}'",
            order_by="timestamp DESC"
        )
```

**Pattern 2: Geographic + Hash Hybrid**

```python
class GeoHashHybridSharding:
    """
    Two-level sharding: Geographic first, then hash within region.
    
    Use when:
    - Data residency requirements (GDPR, data sovereignty)
    - Latency optimization (data close to users)
    - Regional compliance
    """
    
    REGIONS = {
        'us-east': ['shard-us-0', 'shard-us-1', 'shard-us-2', 'shard-us-3'],
        'us-west': ['shard-us-4', 'shard-us-5', 'shard-us-6', 'shard-us-7'],
        'eu-west': ['shard-eu-0', 'shard-eu-1', 'shard-eu-2', 'shard-eu-3'],
        'eu-central': ['shard-eu-4', 'shard-eu-5', 'shard-eu-6', 'shard-eu-7'],
        'ap-southeast': ['shard-ap-0', 'shard-ap-1', 'shard-ap-2', 'shard-ap-3'],
    }
    
    def __init__(self):
        self.user_region_cache = {}
    
    def get_shard(self, user_id: str, user_region: str = None) -> str:
        # Level 1: Determine region
        if user_region:
            region = user_region
        else:
            region = self.user_region_cache.get(user_id, 'us-east')
        
        # Level 2: Hash within region
        region_shards = self.REGIONS[region]
        shard_index = hash(user_id) % len(region_shards)
        
        return region_shards[shard_index]
    
    def migrate_user_region(self, user_id: str, old_region: str, new_region: str):
        """
        Handle user moving between regions (e.g., user moves from US to EU).
        GDPR right to data portability!
        """
        old_shard = self.get_shard(user_id, old_region)
        new_shard = self.get_shard(user_id, new_region)
        
        # Copy data to new region
        user_data = self.shards[old_shard].export_user(user_id)
        self.shards[new_shard].import_user(user_id, user_data)
        
        # Update routing
        self.user_region_cache[user_id] = new_region
        
        # Delete from old region (GDPR compliance)
        self.shards[old_shard].delete_user(user_id)
    
    def cross_region_query(self, user_ids: list) -> dict:
        """
        Query users across multiple regions.
        Groups by region for efficiency.
        """
        by_region = defaultdict(list)
        for user_id in user_ids:
            region = self.user_region_cache.get(user_id, 'us-east')
            by_region[region].append(user_id)
        
        results = {}
        for region, region_users in by_region.items():
            # Query each region in parallel
            for user_id in region_users:
                shard = self.get_shard(user_id, region)
                results[user_id] = self.shards[shard].get_user(user_id)
        
        return results
```

**Pattern 3: Time-Based + Hash Hybrid (Time-Series Data)**

```python
class TimeHashHybridSharding:
    """
    Partition by time first, then hash within time partition.
    
    Ideal for:
    - Event logs, metrics, analytics
    - Data with natural time-based access patterns
    - Data with TTL/retention policies
    """
    
    def __init__(self, partition_duration_days=30, shards_per_partition=8):
        self.partition_days = partition_duration_days
        self.shards_per_partition = shards_per_partition
        
        # Cache of active partitions
        self.partitions = {}
    
    def get_partition_id(self, timestamp: datetime) -> str:
        """Determine time partition."""
        # Partition by month
        return timestamp.strftime("%Y-%m")
    
    def get_shard(self, entity_id: str, timestamp: datetime) -> str:
        partition_id = self.get_partition_id(timestamp)
        
        # Hash within partition
        shard_index = hash(entity_id) % self.shards_per_partition
        
        return f"events-{partition_id}-shard-{shard_index}"
    
    def write_event(self, entity_id: str, event: dict):
        timestamp = datetime.utcnow()
        shard = self.get_shard(entity_id, timestamp)
        
        # Ensure shard exists
        self._ensure_partition(self.get_partition_id(timestamp))
        
        self.shards[shard].insert({
            **event,
            'entity_id': entity_id,
            'timestamp': timestamp
        })
    
    def query_entity_events(self, entity_id: str, 
                            start_time: datetime, 
                            end_time: datetime) -> list:
        """Query events for entity across time range."""
        results = []
        
        # Determine which partitions to query
        current = start_time
        while current <= end_time:
            partition_id = self.get_partition_id(current)
            shard = self.get_shard(entity_id, current)
            
            if shard in self.shards:
                partition_results = self.shards[shard].query(
                    filter=f"entity_id = '{entity_id}' AND "
                           f"timestamp >= '{start_time}' AND "
                           f"timestamp <= '{end_time}'"
                )
                results.extend(partition_results)
            
            # Move to next partition
            current = current + timedelta(days=self.partition_days)
        
        return sorted(results, key=lambda x: x['timestamp'])
    
    def query_time_range(self, start_time: datetime, 
                         end_time: datetime) -> list:
        """
        Query ALL events in time range (scatter-gather within partition).
        Much faster than full scatter-gather across all shards.
        """
        results = []
        
        current = start_time
        while current <= end_time:
            partition_id = self.get_partition_id(current)
            
            # Query all shards in this partition (parallel)
            for i in range(self.shards_per_partition):
                shard = f"events-{partition_id}-shard-{i}"
                if shard in self.shards:
                    results.extend(self.shards[shard].query(
                        filter=f"timestamp >= '{start_time}' AND "
                               f"timestamp <= '{end_time}'"
                    ))
            
            current = current + timedelta(days=self.partition_days)
        
        return results
    
    def cleanup_old_partitions(self, retention_days: int = 365):
        """Delete partitions older than retention period."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        cutoff_partition = self.get_partition_id(cutoff)
        
        for partition_id in list(self.partitions.keys()):
            if partition_id < cutoff_partition:
                # Delete all shards in partition
                for i in range(self.shards_per_partition):
                    shard = f"events-{partition_id}-shard-{i}"
                    self.shards[shard].drop()
                
                del self.partitions[partition_id]
```

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

```python
class TieredShardRouter:
    """Route queries to appropriate tier based on data age."""
    
    TIERS = {
        'hot': {'max_age_hours': 24, 'prefix': 'hot-'},
        'warm': {'max_age_days': 30, 'prefix': 'warm-'},
        'cold': {'max_age_days': float('inf'), 'prefix': 'cold-'}
    }
    
    def get_tier(self, timestamp: datetime) -> str:
        age = datetime.utcnow() - timestamp
        
        if age < timedelta(hours=24):
            return 'hot'
        elif age < timedelta(days=30):
            return 'warm'
        else:
            return 'cold'
    
    def route_write(self, entity_id: str, timestamp: datetime) -> str:
        """Writes always go to hot tier."""
        shard_index = hash(entity_id) % 8  # 8 hot shards
        return f"hot-shard-{shard_index}"
    
    def route_read(self, entity_id: str, timestamp: datetime) -> str:
        tier = self.get_tier(timestamp)
        config = self.TIERS[tier]
        
        if tier == 'hot':
            shard_index = hash(entity_id) % 8
        elif tier == 'warm':
            shard_index = hash(entity_id) % 16
        else:
            shard_index = hash(entity_id) % 32
        
        return f"{config['prefix']}shard-{shard_index}"
    
    def age_out_data(self):
        """Background job: move data between tiers."""
        # Hot -> Warm
        cutoff_warm = datetime.utcnow() - timedelta(hours=24)
        self._migrate_tier('hot', 'warm', cutoff_warm)
        
        # Warm -> Cold
        cutoff_cold = datetime.utcnow() - timedelta(days=30)
        self._migrate_tier('warm', 'cold', cutoff_cold)
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

```python
# User ID 1234 is a celebrity with 50 million followers
# Every post creates 50 million fan-out events
# All targeting shard = hash(1234) % 4 = 2

# Shard 2 is now processing 50M events
# while other shards process thousands

# Your "evenly distributed" system is now 99% focused on shard 2
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

```python
# Without salting
def get_shard(user_id):
    return hash(user_id) % num_shards  # Always same shard

# With salting for hot keys
def get_shard_salted(user_id, is_celebrity=False):
    if is_celebrity:
        # Distribute across shards
        salt = random.randint(0, 9)
        return hash(f"{user_id}_{salt}") % num_shards
    return hash(user_id) % num_shards

# Reading requires scatter-gather for celebrities
def get_all_data_for_celebrity(user_id):
    results = []
    for salt in range(10):
        shard = hash(f"{user_id}_{salt}") % num_shards
        results.extend(query_shard(shard, user_id, salt))
    return results
```

**Staff-Level Insight:** The best solution to hot partitions is often domain-specific. Don't reach for generic solutions immediately. Understand WHY your partition is hot and design accordingly.

For example: If celebrity posts are hot because of fan-out, maybe the answer isn't better sharding—it's redesigning fan-out to be pull-based instead of push-based.

#### Advanced Hot Partition Mitigation (Staff-Level Deep Dive)

**Technique 1: Request Coalescing for Hot Keys**

```python
import asyncio
from collections import defaultdict
import time

class RequestCoalescer:
    """
    Coalesce multiple concurrent requests for the same key.
    
    If 1000 requests arrive for 'celebrity_123' simultaneously,
    only ONE database query is made. All 1000 requests share the result.
    
    Use when: Read-heavy hot keys with identical queries.
    """
    
    def __init__(self, db_client, coalesce_window_ms=50):
        self.db = db_client
        self.window_ms = coalesce_window_ms
        self.pending = {}  # key -> asyncio.Future
        self.lock = asyncio.Lock()
    
    async def get(self, key: str):
        async with self.lock:
            if key in self.pending:
                # Another request is already fetching this key
                # Wait for that result instead of making another query
                return await self.pending[key]
            
            # We're the first request for this key
            future = asyncio.get_event_loop().create_future()
            self.pending[key] = future
        
        try:
            # Fetch from database (only one query for N concurrent requests)
            result = await self.db.get(key)
            future.set_result(result)
            return result
        except Exception as e:
            future.set_exception(e)
            raise
        finally:
            # Clean up after short delay (allows batching within window)
            await asyncio.sleep(self.window_ms / 1000)
            async with self.lock:
                if key in self.pending:
                    del self.pending[key]


class BatchingCoalescer:
    """
    Batch multiple keys into single database round-trip.
    
    Instead of: GET key1, GET key2, GET key3 (3 round trips)
    Do: MGET key1, key2, key3 (1 round trip)
    """
    
    def __init__(self, db_client, batch_size=100, batch_timeout_ms=5):
        self.db = db_client
        self.batch_size = batch_size
        self.timeout_ms = batch_timeout_ms
        self.pending_keys = []
        self.pending_futures = {}
        self.lock = asyncio.Lock()
        self.batch_task = None
    
    async def get(self, key: str):
        future = asyncio.get_event_loop().create_future()
        
        async with self.lock:
            self.pending_keys.append(key)
            self.pending_futures[key] = future
            
            if len(self.pending_keys) >= self.batch_size:
                # Batch is full, execute immediately
                await self._execute_batch()
            elif self.batch_task is None:
                # Start timeout for batch execution
                self.batch_task = asyncio.create_task(self._batch_timeout())
        
        return await future
    
    async def _batch_timeout(self):
        await asyncio.sleep(self.timeout_ms / 1000)
        async with self.lock:
            await self._execute_batch()
            self.batch_task = None
    
    async def _execute_batch(self):
        if not self.pending_keys:
            return
        
        keys = self.pending_keys[:]
        self.pending_keys.clear()
        
        # Single round-trip for all keys
        results = await self.db.mget(keys)
        
        for key, result in zip(keys, results):
            if key in self.pending_futures:
                self.pending_futures[key].set_result(result)
                del self.pending_futures[key]
```

**Technique 2: Adaptive Load Shedding**

```python
import time
import random
from collections import deque

class AdaptiveLoadShedder:
    """
    Progressively shed load from hot shards based on real-time metrics.
    
    When a shard is overloaded:
    1. Start rejecting lowest-priority requests
    2. Increase rejection rate as load increases
    3. Automatically recover as load decreases
    """
    
    def __init__(self, shard_id: str, target_latency_ms=50, max_latency_ms=200):
        self.shard_id = shard_id
        self.target_latency = target_latency_ms
        self.max_latency = max_latency_ms
        
        # Sliding window of recent latencies
        self.latencies = deque(maxlen=100)
        self.lock = threading.Lock()
        
        # Current rejection probability
        self.rejection_rate = 0.0
    
    def record_latency(self, latency_ms: float):
        with self.lock:
            self.latencies.append(latency_ms)
            self._update_rejection_rate()
    
    def _update_rejection_rate(self):
        if len(self.latencies) < 10:
            return
        
        avg_latency = sum(self.latencies) / len(self.latencies)
        
        if avg_latency <= self.target_latency:
            # Good performance, reduce rejection
            self.rejection_rate = max(0, self.rejection_rate - 0.05)
        elif avg_latency >= self.max_latency:
            # Critical overload, max rejection
            self.rejection_rate = min(0.9, self.rejection_rate + 0.1)
        else:
            # Proportional adjustment
            overload_ratio = (avg_latency - self.target_latency) / (self.max_latency - self.target_latency)
            target_rejection = overload_ratio * 0.5  # Up to 50% rejection
            
            # Smooth adjustment
            self.rejection_rate = 0.9 * self.rejection_rate + 0.1 * target_rejection
    
    def should_accept(self, priority: int = 5) -> bool:
        """
        Decide whether to accept request based on priority and current load.
        
        Priority 1 = highest (admin), 10 = lowest (background job)
        Higher priority requests are less likely to be rejected.
        """
        if self.rejection_rate == 0:
            return True
        
        # Adjust rejection rate based on priority
        # Priority 1 gets 10% of base rejection rate
        # Priority 10 gets 100% of base rejection rate
        adjusted_rate = self.rejection_rate * (priority / 10)
        
        return random.random() > adjusted_rate
    
    def get_metrics(self) -> dict:
        with self.lock:
            return {
                'shard_id': self.shard_id,
                'rejection_rate': self.rejection_rate,
                'avg_latency_ms': sum(self.latencies) / len(self.latencies) if self.latencies else 0,
                'sample_count': len(self.latencies)
            }
```

**Technique 3: Automated Shard Splitting**

```python
import threading
import time
from enum import Enum

class SplitState(Enum):
    NORMAL = "normal"
    PREPARING = "preparing"
    COPYING = "copying"
    SWITCHING = "switching"
    COMPLETED = "completed"

class AutomaticShardSplitter:
    """
    Automatically split hot shards when they exceed thresholds.
    
    Process:
    1. Detect hot shard (load > threshold)
    2. Create new shard
    3. Copy half the keyspace to new shard
    4. Update routing
    5. Verify and cleanup
    """
    
    def __init__(self, shard_manager, router, metrics_collector):
        self.shard_manager = shard_manager
        self.router = router
        self.metrics = metrics_collector
        
        # Thresholds
        self.load_threshold = 0.85  # 85% capacity
        self.duration_threshold = 300  # 5 minutes sustained
        self.cooldown = 3600  # 1 hour between splits
        
        # State
        self.split_states = {}  # shard_id -> SplitState
        self.last_split = {}  # shard_id -> timestamp
    
    def check_and_split(self):
        """Called periodically by background job."""
        for shard in self.shard_manager.get_all_shards():
            if self._should_split(shard):
                self._initiate_split(shard)
    
    def _should_split(self, shard) -> bool:
        # Check cooldown
        last = self.last_split.get(shard.id, 0)
        if time.time() - last < self.cooldown:
            return False
        
        # Check if already splitting
        if self.split_states.get(shard.id) != SplitState.NORMAL:
            return False
        
        # Check load threshold
        metrics = self.metrics.get_shard_metrics(shard.id)
        return metrics['sustained_high_load_seconds'] > self.duration_threshold
    
    def _initiate_split(self, shard):
        """Begin the split process."""
        self.split_states[shard.id] = SplitState.PREPARING
        
        # Run in background
        threading.Thread(
            target=self._execute_split,
            args=(shard,),
            daemon=True
        ).start()
    
    def _execute_split(self, shard):
        try:
            # 1. Create new shard
            self.split_states[shard.id] = SplitState.PREPARING
            new_shard = self.shard_manager.create_shard()
            
            # 2. Determine split point (median key)
            split_key = self._find_split_point(shard)
            
            # 3. Start double-writing to both shards
            self.router.add_shadow_write(shard.id, new_shard.id, 
                                         key_filter=lambda k: k > split_key)
            
            # 4. Copy historical data
            self.split_states[shard.id] = SplitState.COPYING
            self._copy_data(shard, new_shard, key_filter=lambda k: k > split_key)
            
            # 5. Verify data integrity
            if not self._verify_copy(shard, new_shard, split_key):
                raise Exception("Data verification failed")
            
            # 6. Switch routing
            self.split_states[shard.id] = SplitState.SWITCHING
            self.router.split_shard(shard.id, new_shard.id, split_key)
            
            # 7. Cleanup old data from both shards
            self._cleanup_after_split(shard, new_shard, split_key)
            
            self.split_states[shard.id] = SplitState.COMPLETED
            self.last_split[shard.id] = time.time()
            
        except Exception as e:
            self._handle_split_failure(shard, e)
    
    def _find_split_point(self, shard) -> str:
        """Find the median key to split evenly."""
        # Sample keys to find distribution
        samples = shard.sample_keys(1000)
        samples.sort()
        return samples[len(samples) // 2]
    
    def _copy_data(self, source, target, key_filter):
        """Copy data in batches."""
        cursor = None
        while True:
            batch, cursor = source.scan(cursor, count=1000)
            
            filtered = [(k, v) for k, v in batch if key_filter(k)]
            if filtered:
                target.mset(filtered)
            
            if cursor is None:
                break
    
    def _verify_copy(self, source, target, split_key) -> bool:
        """Verify data integrity after copy."""
        # Sample verification
        samples = source.sample_keys(100, key_filter=lambda k: k > split_key)
        
        for key in samples:
            source_value = source.get(key)
            target_value = target.get(key)
            if source_value != target_value:
                return False
        
        return True
```

**Technique 4: Write-Behind Caching for Hot Keys**

```python
import threading
import queue
import time
from collections import defaultdict

class WriteBehindCache:
    """
    Cache with asynchronous writes to reduce database pressure.
    
    Writes go to cache immediately, then batch-written to DB.
    Useful for high-frequency updates to hot keys.
    
    Trade-off: Risk of data loss if cache fails before flush.
    """
    
    def __init__(self, cache, database, flush_interval=1.0, batch_size=100):
        self.cache = cache
        self.db = database
        self.flush_interval = flush_interval
        self.batch_size = batch_size
        
        # Pending writes
        self.write_queue = queue.Queue()
        self.pending_keys = set()
        self.lock = threading.Lock()
        
        # Start background flusher
        self.flusher = threading.Thread(target=self._flush_loop, daemon=True)
        self.flusher.start()
    
    def get(self, key: str):
        """Read from cache, fallback to DB."""
        value = self.cache.get(key)
        if value is not None:
            return value
        
        value = self.db.get(key)
        if value is not None:
            self.cache.set(key, value)
        return value
    
    def set(self, key: str, value):
        """Write to cache immediately, queue DB write."""
        self.cache.set(key, value)
        
        with self.lock:
            self.pending_keys.add(key)
        
        self.write_queue.put((key, value, time.time()))
    
    def increment(self, key: str, amount: int = 1) -> int:
        """Increment counter with write coalescing."""
        # Use cache for fast increment
        new_value = self.cache.incr(key, amount)
        
        with self.lock:
            self.pending_keys.add(key)
        
        # Queue periodic sync to DB (not every increment)
        if new_value % 100 == 0:  # Sync every 100 increments
            self.write_queue.put((key, new_value, time.time()))
        
        return new_value
    
    def _flush_loop(self):
        """Background thread: flush writes to database."""
        batch = []
        last_flush = time.time()
        
        while True:
            try:
                # Collect items with timeout
                try:
                    item = self.write_queue.get(timeout=self.flush_interval)
                    batch.append(item)
                except queue.Empty:
                    pass
                
                # Flush if batch is full or timeout
                should_flush = (
                    len(batch) >= self.batch_size or
                    time.time() - last_flush >= self.flush_interval
                )
                
                if should_flush and batch:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = time.time()
                    
            except Exception as e:
                # Log error but don't crash
                print(f"Flush error: {e}")
    
    def _flush_batch(self, batch):
        """Write batch to database."""
        # Deduplicate: keep only latest write per key
        latest_by_key = {}
        for key, value, timestamp in batch:
            if key not in latest_by_key or timestamp > latest_by_key[key][1]:
                latest_by_key[key] = (value, timestamp)
        
        # Batch write to DB
        writes = [(k, v) for k, (v, _) in latest_by_key.items()]
        self.db.mset(writes)
        
        # Update pending set
        with self.lock:
            for key, _, _ in batch:
                self.pending_keys.discard(key)
    
    def flush_sync(self):
        """Force synchronous flush (for shutdown)."""
        batch = []
        while not self.write_queue.empty():
            batch.append(self.write_queue.get_nowait())
        
        if batch:
            self._flush_batch(batch)
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

```python
# Inspired by GitHub's gh-ost

class OnlineResharding:
    def migrate(self):
        # 1. Create new shard structure
        self.create_new_shards()
        
        # 2. Start capturing changes (binlog/CDC)
        self.start_change_capture()
        
        # 3. Copy existing data in batches
        for batch in self.get_batches():
            self.copy_batch(batch)
            self.apply_captured_changes()  # Keep up with writes
        
        # 4. Final sync and cutover
        self.pause_writes()  # Brief pause
        self.apply_remaining_changes()
        self.switch_traffic()
        self.resume_writes()
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

```python
# Instead of joining at query time, store user_name in orders
class Order:
    id: int
    user_id: int
    user_name: str        # Denormalized from users table
    user_email: str       # Denormalized from users table
    total: Decimal
    created_at: datetime

# Update denormalized data when user changes
def update_user_name(user_id, new_name):
    # Update users table
    users_shard.update(user_id, name=new_name)
    
    # Async update all orders with this user
    for order in orders_by_user(user_id):
        orders_shard.update(order.id, user_name=new_name)
```

**Trade-off:** Storage cost for query simplicity. Updates become expensive.

**Solution B: Application-Level Joins**

```python
def get_orders_with_users(start_date):
    # Step 1: Query orders from all shards (scatter)
    orders = []
    for shard in order_shards:
        orders.extend(shard.query(
            "SELECT * FROM orders WHERE created_at > %s", 
            [start_date]
        ))
    
    # Step 2: Collect unique user_ids
    user_ids = set(o.user_id for o in orders)
    
    # Step 3: Batch fetch users (grouped by shard)
    users_by_id = {}
    for user_id in user_ids:
        shard = get_user_shard(user_id)
        user = shard.get_user(user_id)
        users_by_id[user_id] = user
    
    # Step 4: Join in application
    for order in orders:
        order.user = users_by_id.get(order.user_id)
    
    return orders
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

```python
class TwoPhaseCommitCoordinator:
    def transfer(self, from_user, to_user, amount):
        txn_id = generate_txn_id()
        
        from_shard = get_user_shard(from_user)
        to_shard = get_user_shard(to_user)
        
        # Phase 1: Prepare
        try:
            from_prepared = from_shard.prepare(
                txn_id, "UPDATE balance SET amount = amount - %s WHERE user_id = %s",
                [amount, from_user]
            )
            to_prepared = to_shard.prepare(
                txn_id, "UPDATE balance SET amount = amount + %s WHERE user_id = %s",
                [amount, to_user]
            )
        except PrepareError:
            # Abort if any prepare fails
            from_shard.abort(txn_id)
            to_shard.abort(txn_id)
            raise TransactionAborted()
        
        # Phase 2: Commit
        # This MUST succeed (participants promised in prepare phase)
        from_shard.commit(txn_id)
        to_shard.commit(txn_id)
        
        return Success
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

```python
class TransferSaga:
    def execute(self, from_user, to_user, amount):
        saga_id = generate_saga_id()
        
        # Step 1: Deduct from sender
        try:
            self.deduct_balance(saga_id, from_user, amount)
        except InsufficientFunds:
            return Failure("Insufficient funds")
        
        # Step 2: Add to receiver
        try:
            self.add_balance(saga_id, to_user, amount)
        except Exception as e:
            # Compensate: refund the sender
            self.add_balance(saga_id, from_user, amount)  # Compensation
            return Failure(f"Transfer failed: {e}")
        
        return Success
    
    def deduct_balance(self, saga_id, user_id, amount):
        shard = get_user_shard(user_id)
        # Record saga step for idempotency
        shard.execute("""
            INSERT INTO saga_log (saga_id, step, status) VALUES (%s, 'deduct', 'started');
            UPDATE balances SET amount = amount - %s WHERE user_id = %s AND amount >= %s;
            UPDATE saga_log SET status = 'completed' WHERE saga_id = %s AND step = 'deduct';
        """, [saga_id, amount, user_id, amount, saga_id])
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

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

class ScatterGatherAggregator:
    def __init__(self, shards, max_workers=32):
        self.shards = shards
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
    
    async def aggregate(self, query, merge_func):
        # Scatter: query all shards in parallel
        futures = []
        for shard in self.shards:
            future = asyncio.get_event_loop().run_in_executor(
                self.executor,
                shard.execute,
                query
            )
            futures.append(future)
        
        # Gather: collect all results
        results = await asyncio.gather(*futures, return_exceptions=True)
        
        # Handle failures
        successful_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logging.error(f"Shard {i} failed: {result}")
                # Option: fail entire query, or continue with partial results
            else:
                successful_results.append(result)
        
        # Merge: combine results
        return merge_func(successful_results)

# Usage
aggregator = ScatterGatherAggregator(order_shards)

def merge_order_stats(results):
    total_count = sum(r['count'] for r in results)
    total_amount = sum(r['sum'] for r in results)
    return {'count': total_count, 'sum': total_amount}

stats = await aggregator.aggregate(
    "SELECT COUNT(*) as count, SUM(amount) as sum FROM orders WHERE status = 'completed'",
    merge_order_stats
)
```

**Optimization: Pre-Aggregation**

For frequently-needed aggregations, maintain running totals:

```python
# Instead of scatter-gather every time, maintain a summary table
class OrderStatsCache:
    def on_order_completed(self, order):
        # Update per-shard summary
        self.local_shard.increment('completed_orders_count', 1)
        self.local_shard.increment('completed_orders_sum', order.amount)
        
        # Async sync to global summary
        self.publish_to_aggregator({
            'shard': self.shard_id,
            'delta_count': 1,
            'delta_sum': order.amount
        })
```

---

### 2.7 Distributed ID Generation

In a sharded system, you can't use auto-increment IDs. Two shards would generate the same ID.

#### Strategy 1: UUID

```python
import uuid

def generate_id():
    return str(uuid.uuid4())
    # Example: "550e8400-e29b-41d4-a716-446655440000"
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

```python
import time
import threading

class SnowflakeGenerator:
    # Custom epoch: Jan 1, 2020
    EPOCH = 1577836800000
    
    # Bit allocations
    MACHINE_ID_BITS = 10
    SEQUENCE_BITS = 12
    
    MAX_MACHINE_ID = (1 << MACHINE_ID_BITS) - 1  # 1023
    MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1      # 4095
    
    def __init__(self, machine_id: int):
        if machine_id < 0 or machine_id > self.MAX_MACHINE_ID:
            raise ValueError(f"Machine ID must be 0-{self.MAX_MACHINE_ID}")
        
        self.machine_id = machine_id
        self.sequence = 0
        self.last_timestamp = -1
        self.lock = threading.Lock()
    
    def _current_millis(self) -> int:
        return int(time.time() * 1000)
    
    def generate(self) -> int:
        with self.lock:
            timestamp = self._current_millis()
            
            if timestamp == self.last_timestamp:
                # Same millisecond: increment sequence
                self.sequence = (self.sequence + 1) & self.MAX_SEQUENCE
                if self.sequence == 0:
                    # Sequence exhausted, wait for next millisecond
                    while timestamp <= self.last_timestamp:
                        timestamp = self._current_millis()
            else:
                # New millisecond: reset sequence
                self.sequence = 0
            
            self.last_timestamp = timestamp
            
            # Compose the ID
            id = ((timestamp - self.EPOCH) << (self.MACHINE_ID_BITS + self.SEQUENCE_BITS)) \
                 | (self.machine_id << self.SEQUENCE_BITS) \
                 | self.sequence
            
            return id
    
    @staticmethod
    def parse(snowflake_id: int) -> dict:
        """Decompose a snowflake ID for debugging."""
        sequence = snowflake_id & 0xFFF
        machine_id = (snowflake_id >> 12) & 0x3FF
        timestamp = (snowflake_id >> 22) + SnowflakeGenerator.EPOCH
        
        return {
            'timestamp': timestamp,
            'machine_id': machine_id,
            'sequence': sequence,
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S', 
                                        time.localtime(timestamp / 1000))
        }


# Usage
generator = SnowflakeGenerator(machine_id=42)

order_id = generator.generate()
print(f"Generated ID: {order_id}")
print(f"Parsed: {SnowflakeGenerator.parse(order_id)}")
# Output:
# Generated ID: 7199348347483156522
# Parsed: {'timestamp': 1705678901234, 'machine_id': 42, 'sequence': 42, 
#          'created_at': '2024-01-19 12:34:56'}
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

```python
# ULID: 26 characters, Crockford Base32 encoded
# Format: TTTTTTTTTTSSSSSSSSSSSSSSSS
#         timestamp (10) + randomness (16) = 128 bits

import ulid

def generate_id():
    return str(ulid.new())
    # Example: "01ARZ3NDEKTSV4RRFFQ69G5FAV"

# ULIDs are sortable by creation time
id1 = ulid.new()
time.sleep(0.001)
id2 = ulid.new()
assert id2 > id1  # True!
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

```python
# Simple PostgreSQL setup
# users table with all user data

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255),
    profile JSONB,
    created_at TIMESTAMP
);

# Everything on one server. ~50ms queries. Life is good.
```

#### Phase 2: Growth Pains (100K-10M Users)

```python
# Add read replicas for scaling reads

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
```python
# Sticky sessions for recently-updated users
def get_user(user_id):
    if cache.get(f"recently_updated:{user_id}"):
        return primary.get_user(user_id)
    return load_balanced_replica.get_user(user_id)

def update_user(user_id, data):
    result = primary.update_user(user_id, data)
    cache.set(f"recently_updated:{user_id}", True, ttl=30)
    return result
```

#### Phase 3: Sharding Required (10M+ Users)

```python
# Hash-based sharding on user_id

SHARD_COUNT = 16

def get_user_shard(user_id):
    # Consistent hashing for future expansion
    return consistent_hash(user_id, SHARD_COUNT)

# Each shard has primary + replicas
# Shard 0: users whose hash maps to 0
# Shard 1: users whose hash maps to 1
# ... etc
```

**Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                    USER SERVICE                             │
│                                                             │
│    ┌──────────────────────────────────────────────┐         │
│    │            SHARD ROUTER                       │        │
│    │                                               │        │
│    │   shard_id = consistent_hash(user_id) % 16   │         │
│    └──────────────────────────────────────────────┘         │
│                          │                                  │
│    ┌─────────┬─────────┬─┴───────┬─────────┬─────────┐      │
│    ▼         ▼         ▼         ▼         ▼         ▼      │
│ ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐        │
│ │Sh 0 │  │Sh 1 │  │Sh 2 │  │ ... │  │Sh 14│  │Sh 15│        │
│ │     │  │     │  │     │  │     │  │     │  │     │        │
│ │P + R│  │P + R│  │P + R│  │     │  │P + R│  │P + R│        │
│ └─────┘  └─────┘  └─────┘  └─────┘  └─────┘  └─────┘        │
│                                                             │
│ P = Primary, R = Replicas                                   │
└─────────────────────────────────────────────────────────────┘
```

**Challenge: Email Lookups**

Users log in by email, not user_id. But we sharded by user_id.

```python
# Problem: 
# login(email) → which shard?

# Solution: Secondary index
# Separate lookup table: email → user_id
# This table is small (just the mapping) and can be replicated

CREATE TABLE email_to_user (
    email VARCHAR(255) PRIMARY KEY,
    user_id BIGINT
);

def login(email, password):
    # 1. Lookup user_id from email (this table is small, unsharded)
    user_id = email_lookup.get(email)
    
    # 2. Route to correct shard
    shard = get_user_shard(user_id)
    
    # 3. Verify password
    user = shard.get_user(user_id)
    return verify_password(user, password)
```

**Failure Modes to Handle:**

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Single shard down | ~6% of users affected | Failover to replica, alerting |
| Router failure | All requests fail | Multiple router instances |
| Email lookup down | No logins possible | Replicate heavily, cache aggressively |
| Shard split-brain | Data inconsistency | Fencing, leader election |

---

### 3.2 Scenario: Rate Limiter Counters

Rate limiting looks simple until you try to do it at scale. Let's design a distributed rate limiter.

**Requirements:**
- 100M users
- Limit: 100 requests per minute per user
- Sub-millisecond latency
- Globally consistent-ish (eventually consistent OK for slight over-limit)

#### Naive Approach (Won't Scale)

```python
# Single Redis instance
def check_rate_limit(user_id):
    key = f"rate:{user_id}"
    count = redis.incr(key)
    if count == 1:
        redis.expire(key, 60)
    return count <= 100
```

**Why it fails:**
- Single Redis is SPOF
- Can't handle 100K+ QPS
- Memory limited for 100M keys

#### Sharded Rate Limiter

```python
# Shard by user_id

class ShardedRateLimiter:
    def __init__(self, num_shards=64):
        self.shards = [Redis(host=f"ratelimit-{i}") for i in range(num_shards)]
        self.num_shards = num_shards
    
    def get_shard(self, user_id):
        return self.shards[hash(user_id) % self.num_shards]
    
    def check_rate_limit(self, user_id, limit=100, window=60):
        shard = self.get_shard(user_id)
        key = f"rate:{user_id}"
        
        # Atomic increment with TTL
        pipe = shard.pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        count, _ = pipe.execute()
        
        return count <= limit
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

```python
import time
from collections import deque
import threading

class SlidingWindowLog:
    """
    Precise rate limiting using timestamp log.
    Trade-off: Memory usage scales with request rate.
    
    Use when: Precision matters more than memory.
    """
    
    def __init__(self, redis_client, window_seconds=60, max_requests=100):
        self.redis = redis_client
        self.window = window_seconds
        self.limit = max_requests
    
    def is_allowed(self, user_id: str) -> bool:
        key = f"ratelimit:log:{user_id}"
        now = time.time()
        window_start = now - self.window
        
        # Atomic operation using Lua script
        lua_script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local window_start = tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        local window = tonumber(ARGV[4])
        
        -- Remove old entries outside the window
        redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)
        
        -- Count current entries
        local count = redis.call('ZCARD', key)
        
        if count < limit then
            -- Add current request
            redis.call('ZADD', key, now, now .. ':' .. math.random())
            redis.call('EXPIRE', key, window)
            return 1
        else
            return 0
        end
        """
        
        result = self.redis.eval(
            lua_script, 1, key, 
            now, window_start, self.limit, self.window
        )
        return result == 1


class SlidingWindowCounter:
    """
    Memory-efficient approximation of sliding window.
    Interpolates between current and previous window counts.
    
    Use when: Memory efficiency matters, small error is acceptable.
    """
    
    def __init__(self, redis_client, window_seconds=60, max_requests=100):
        self.redis = redis_client
        self.window = window_seconds
        self.limit = max_requests
    
    def is_allowed(self, user_id: str) -> bool:
        now = time.time()
        current_window = int(now // self.window)
        previous_window = current_window - 1
        
        # Position within current window (0.0 to 1.0)
        window_position = (now % self.window) / self.window
        
        current_key = f"ratelimit:{user_id}:{current_window}"
        previous_key = f"ratelimit:{user_id}:{previous_window}"
        
        # Lua script for atomic read-increment
        lua_script = """
        local current_key = KEYS[1]
        local previous_key = KEYS[2]
        local limit = tonumber(ARGV[1])
        local window_position = tonumber(ARGV[2])
        local window = tonumber(ARGV[3])
        
        local current_count = tonumber(redis.call('GET', current_key) or '0')
        local previous_count = tonumber(redis.call('GET', previous_key) or '0')
        
        -- Weighted count: full current + partial previous
        local weighted_count = current_count + (previous_count * (1 - window_position))
        
        if weighted_count < limit then
            redis.call('INCR', current_key)
            redis.call('EXPIRE', current_key, window * 2)
            return 1
        else
            return 0
        end
        """
        
        result = self.redis.eval(
            lua_script, 2, current_key, previous_key,
            self.limit, window_position, self.window
        )
        return result == 1
```

**Solution 2: Token Bucket (Smooth Rate Limiting)**

```python
import time

class TokenBucket:
    """
    Allows bursts while maintaining average rate.
    
    Bucket fills with tokens at a constant rate.
    Each request consumes one token.
    Requests are rejected when bucket is empty.
    
    Use when: You want to allow bursts but cap sustained rate.
    """
    
    def __init__(self, redis_client, bucket_size=100, refill_rate=10):
        """
        Args:
            bucket_size: Maximum tokens (burst capacity)
            refill_rate: Tokens added per second
        """
        self.redis = redis_client
        self.bucket_size = bucket_size
        self.refill_rate = refill_rate
    
    def is_allowed(self, user_id: str, tokens_required: int = 1) -> bool:
        key = f"tokenbucket:{user_id}"
        now = time.time()
        
        lua_script = """
        local key = KEYS[1]
        local bucket_size = tonumber(ARGV[1])
        local refill_rate = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])
        local tokens_required = tonumber(ARGV[4])
        
        -- Get current state
        local bucket = redis.call('HMGET', key, 'tokens', 'last_update')
        local tokens = tonumber(bucket[1]) or bucket_size
        local last_update = tonumber(bucket[2]) or now
        
        -- Calculate refill
        local time_passed = now - last_update
        local refill = time_passed * refill_rate
        tokens = math.min(bucket_size, tokens + refill)
        
        -- Check and consume
        if tokens >= tokens_required then
            tokens = tokens - tokens_required
            redis.call('HMSET', key, 'tokens', tokens, 'last_update', now)
            redis.call('EXPIRE', key, bucket_size / refill_rate * 2)
            return 1
        else
            -- Update timestamp even on rejection (for refill calculation)
            redis.call('HMSET', key, 'tokens', tokens, 'last_update', now)
            redis.call('EXPIRE', key, bucket_size / refill_rate * 2)
            return 0
        end
        """
        
        result = self.redis.eval(
            lua_script, 1, key,
            self.bucket_size, self.refill_rate, now, tokens_required
        )
        return result == 1
    
    def get_wait_time(self, user_id: str, tokens_required: int = 1) -> float:
        """Return seconds to wait before request would be allowed."""
        key = f"tokenbucket:{user_id}"
        now = time.time()
        
        bucket = self.redis.hmget(key, 'tokens', 'last_update')
        tokens = float(bucket[0] or self.bucket_size)
        last_update = float(bucket[1] or now)
        
        time_passed = now - last_update
        current_tokens = min(self.bucket_size, tokens + time_passed * self.refill_rate)
        
        if current_tokens >= tokens_required:
            return 0
        
        tokens_needed = tokens_required - current_tokens
        return tokens_needed / self.refill_rate


class LeakyBucket:
    """
    Enforces constant output rate regardless of input pattern.
    
    Requests enter a queue (bucket).
    Queue drains at constant rate.
    Requests rejected when queue is full.
    
    Use when: Downstream system needs constant request rate.
    """
    
    def __init__(self, redis_client, bucket_size=100, leak_rate=10):
        """
        Args:
            bucket_size: Maximum queue size
            leak_rate: Requests processed per second
        """
        self.redis = redis_client
        self.bucket_size = bucket_size
        self.leak_rate = leak_rate
    
    def is_allowed(self, user_id: str) -> bool:
        key = f"leakybucket:{user_id}"
        now = time.time()
        
        lua_script = """
        local key = KEYS[1]
        local bucket_size = tonumber(ARGV[1])
        local leak_rate = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])
        
        local bucket = redis.call('HMGET', key, 'water', 'last_update')
        local water = tonumber(bucket[1]) or 0
        local last_update = tonumber(bucket[2]) or now
        
        -- Calculate leak (water that drained since last update)
        local time_passed = now - last_update
        local leaked = time_passed * leak_rate
        water = math.max(0, water - leaked)
        
        -- Try to add to bucket
        if water < bucket_size then
            water = water + 1
            redis.call('HMSET', key, 'water', water, 'last_update', now)
            redis.call('EXPIRE', key, bucket_size / leak_rate * 2)
            return 1
        else
            redis.call('HSET', key, 'last_update', now)
            return 0
        end
        """
        
        result = self.redis.eval(
            lua_script, 1, key,
            self.bucket_size, self.leak_rate, now
        )
        return result == 1
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

```python
import threading
import time
from collections import defaultdict

class DistributedRateLimiter:
    """
    Two-tier rate limiting:
    1. Local counters for fast path (no network)
    2. Global sync for accuracy
    
    Key insight: Accept small over-limit in exchange for speed.
    """
    
    def __init__(self, redis_cluster, gateway_id: str, 
                 global_limit=1000, sync_interval=1.0):
        self.redis = redis_cluster
        self.gateway_id = gateway_id
        self.global_limit = global_limit
        self.sync_interval = sync_interval
        
        # Local state
        self.local_counts = defaultdict(int)
        self.local_limits = {}  # Allocated quota per user
        self.lock = threading.Lock()
        
        # Start background sync
        self.sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.sync_thread.start()
    
    def is_allowed(self, user_id: str) -> bool:
        """Fast path: check local counter."""
        with self.lock:
            self.local_counts[user_id] += 1
            local_limit = self.local_limits.get(user_id, self.global_limit // 10)
            return self.local_counts[user_id] <= local_limit
    
    def _sync_loop(self):
        """Background thread: sync with global store."""
        while True:
            time.sleep(self.sync_interval)
            self._sync_to_global()
    
    def _sync_to_global(self):
        with self.lock:
            counts_to_sync = dict(self.local_counts)
            self.local_counts.clear()
        
        for user_id, local_count in counts_to_sync.items():
            key = f"global_rate:{user_id}"
            
            # Report our counts, get global total
            lua_script = """
            local key = KEYS[1]
            local gateway_id = ARGV[1]
            local local_count = tonumber(ARGV[2])
            local global_limit = tonumber(ARGV[3])
            local window = tonumber(ARGV[4])
            
            -- Add our gateway's count
            redis.call('HINCRBY', key, gateway_id, local_count)
            redis.call('EXPIRE', key, window)
            
            -- Get total across all gateways
            local all_counts = redis.call('HVALS', key)
            local total = 0
            for i, v in ipairs(all_counts) do
                total = total + tonumber(v)
            end
            
            -- Calculate remaining quota
            local remaining = math.max(0, global_limit - total)
            return remaining
            """
            
            remaining = self.redis.eval(
                lua_script, 1, key,
                self.gateway_id, local_count, self.global_limit, 60
            )
            
            # Update local limit based on remaining global quota
            # Divide remaining among gateways (assume 3 gateways)
            with self.lock:
                self.local_limits[user_id] = max(10, remaining // 3)


class MultiDimensionRateLimiter:
    """
    Rate limit by multiple dimensions simultaneously.
    Example: 100 req/min per user AND 1000 req/min per endpoint AND 10000 req/min per IP
    """
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.limiters = {}
    
    def add_dimension(self, name: str, extractor, limit: int, window: int):
        """
        Args:
            name: Dimension name (e.g., 'user', 'endpoint', 'ip')
            extractor: Function to extract key from request
            limit: Max requests in window
            window: Window size in seconds
        """
        self.limiters[name] = {
            'extractor': extractor,
            'limit': limit,
            'window': window
        }
    
    def is_allowed(self, request) -> tuple[bool, str]:
        """
        Check all dimensions. Return (allowed, rejected_dimension).
        """
        for name, config in self.limiters.items():
            key = config['extractor'](request)
            full_key = f"rate:{name}:{key}"
            
            count = self.redis.incr(full_key)
            if count == 1:
                self.redis.expire(full_key, config['window'])
            
            if count > config['limit']:
                return False, name
        
        return True, None


# Usage
limiter = MultiDimensionRateLimiter(redis)

limiter.add_dimension(
    name='user',
    extractor=lambda req: req.user_id,
    limit=100,
    window=60
)

limiter.add_dimension(
    name='endpoint',
    extractor=lambda req: req.path,
    limit=1000,
    window=60
)

limiter.add_dimension(
    name='ip',
    extractor=lambda req: req.client_ip,
    limit=500,
    window=60
)

# Check request
allowed, rejected_by = limiter.is_allowed(request)
if not allowed:
    return Response(429, f"Rate limited by {rejected_by}")
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

```python
# Shard feeds by user_id (feed owner)

class FeedStore:
    def __init__(self, num_shards=256):
        self.shards = [FeedShard(i) for i in range(num_shards)]
    
    def get_shard(self, user_id):
        return self.shards[consistent_hash(user_id) % len(self.shards)]
    
    def add_to_feed(self, user_id, post):
        shard = self.get_shard(user_id)
        shard.add_post(user_id, post)
    
    def get_feed(self, user_id, limit=20):
        shard = self.get_shard(user_id)
        return shard.get_posts(user_id, limit)
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

```python
# Shard posts by author_id

class PostStore:
    def get_recent_posts(self, author_id, since, limit):
        shard = self.get_shard(author_id)
        return shard.query_posts(author_id, since, limit)

class FeedService:
    def get_feed(self, user_id, limit=20):
        following = self.social_graph.get_following(user_id)
        
        # Parallel fetch from all followed users
        futures = []
        for author_id in following:
            futures.append(
                self.executor.submit(
                    self.post_store.get_recent_posts,
                    author_id, since=one_day_ago, limit=5
                )
            )
        
        # Gather and merge
        all_posts = []
        for future in futures:
            all_posts.extend(future.result())
        
        # Sort by time, return top N
        all_posts.sort(key=lambda p: p.created_at, reverse=True)
        return all_posts[:limit]
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

```python
class HybridFeedSystem:
    CELEBRITY_THRESHOLD = 10_000
    
    def __init__(self, num_feed_shards=256, num_post_shards=64):
        # Feeds: sharded by feed owner
        self.feed_shards = [FeedShard(i) for i in range(num_feed_shards)]
        
        # Posts: sharded by author (for celebrity lookup)
        self.post_shards = [PostShard(i) for i in range(num_post_shards)]
        
        # Celebrity registry
        self.celebrities = set()
    
    def on_new_post(self, author_id, post):
        # Store the post
        self.store_post(author_id, post)
        
        # Fan out only if not celebrity
        if author_id not in self.celebrities:
            followers = self.get_followers(author_id)
            for follower_id in followers:
                self.add_to_feed(follower_id, post.id)
    
    def get_feed(self, user_id):
        # Get pre-computed feed (non-celebrity posts)
        precomputed = self.get_precomputed_feed(user_id)
        
        # Get celebrity posts user follows
        celebrity_posts = self.get_celebrity_posts_for_user(user_id)
        
        # Merge
        return self.merge_and_rank(precomputed, celebrity_posts)
```

#### Advanced Feed Patterns (Staff-Level Deep Dive)

**Pattern 1: Cursor-Based Pagination Across Shards**

Offset-based pagination breaks with sharded feeds. Cursor-based pagination is the solution.

```python
import base64
import json
from dataclasses import dataclass
from typing import List, Optional, Tuple

@dataclass
class FeedCursor:
    """
    Encapsulates pagination state across shards.
    
    Cursor contains:
    - Last seen timestamp (for ordering)
    - Last seen post ID (for uniqueness)
    - Per-shard positions (for efficient resume)
    """
    timestamp: float
    post_id: str
    shard_positions: dict  # shard_id -> position within shard
    
    def encode(self) -> str:
        """Encode cursor for client transmission."""
        data = {
            'ts': self.timestamp,
            'pid': self.post_id,
            'sp': self.shard_positions
        }
        return base64.urlsafe_b64encode(
            json.dumps(data).encode()
        ).decode()
    
    @classmethod
    def decode(cls, cursor_str: str) -> 'FeedCursor':
        """Decode cursor from client."""
        data = json.loads(
            base64.urlsafe_b64decode(cursor_str.encode())
        )
        return cls(
            timestamp=data['ts'],
            post_id=data['pid'],
            shard_positions=data['sp']
        )


class ShardedFeedPaginator:
    """
    Efficient pagination for feeds spanning multiple shards.
    
    Key insight: Use cursor to avoid re-scanning seen items.
    """
    
    def __init__(self, feed_shards, post_shards):
        self.feed_shards = feed_shards
        self.post_shards = post_shards
    
    def get_feed_page(self, user_id: str, 
                      cursor: Optional[FeedCursor] = None,
                      page_size: int = 20) -> Tuple[List[dict], Optional[FeedCursor]]:
        """
        Get one page of feed items.
        
        Returns: (items, next_cursor)
        """
        # Get user's primary feed shard
        feed_shard = self.get_feed_shard(user_id)
        
        # Get celebrity posts the user follows
        celebrity_ids = self.get_followed_celebrities(user_id)
        
        if cursor:
            # Resume from cursor position
            feed_items = feed_shard.query(
                user_id=user_id,
                timestamp_lt=cursor.timestamp,
                exclude_id=cursor.post_id,
                limit=page_size + 10  # Over-fetch for merge
            )
            
            celebrity_items = self.fetch_celebrity_posts(
                celebrity_ids,
                timestamp_lt=cursor.timestamp,
                limit=page_size + 10
            )
        else:
            # First page
            feed_items = feed_shard.query(
                user_id=user_id,
                limit=page_size + 10
            )
            celebrity_items = self.fetch_celebrity_posts(
                celebrity_ids,
                limit=page_size + 10
            )
        
        # Merge and sort by timestamp
        all_items = feed_items + celebrity_items
        all_items.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Take exactly page_size items
        page_items = all_items[:page_size]
        
        if len(page_items) < page_size:
            # No more items
            return page_items, None
        
        # Create cursor for next page
        last_item = page_items[-1]
        next_cursor = FeedCursor(
            timestamp=last_item['timestamp'],
            post_id=last_item['post_id'],
            shard_positions={
                feed_shard.id: feed_shard.get_position(last_item['post_id'])
            }
        )
        
        return page_items, next_cursor
    
    def fetch_celebrity_posts(self, celebrity_ids: List[str], 
                              timestamp_lt: float = None,
                              limit: int = 20) -> List[dict]:
        """
        Fetch posts from celebrities (fan-out on read).
        Parallel fetch from post shards.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        all_posts = []
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {}
            
            for celeb_id in celebrity_ids:
                shard = self.get_post_shard(celeb_id)
                future = executor.submit(
                    shard.get_posts,
                    author_id=celeb_id,
                    timestamp_lt=timestamp_lt,
                    limit=5  # Few posts per celebrity
                )
                futures[future] = celeb_id
            
            for future in as_completed(futures):
                posts = future.result()
                all_posts.extend(posts)
        
        return all_posts


class InfiniteScrollOptimizer:
    """
    Optimize for infinite scroll UX patterns.
    
    Key insights:
    1. Pre-fetch next page while user reads current
    2. Cache nearby pages for back-navigation
    3. Use approximate counts for "more content" indicator
    """
    
    def __init__(self, paginator, cache):
        self.paginator = paginator
        self.cache = cache
        self.prefetch_pages = 2
    
    def get_page_with_prefetch(self, user_id: str, 
                                cursor: Optional[str] = None) -> dict:
        """
        Get page and trigger async prefetch of next pages.
        """
        cursor_obj = FeedCursor.decode(cursor) if cursor else None
        
        # Get current page
        items, next_cursor = self.paginator.get_feed_page(
            user_id, cursor_obj
        )
        
        # Cache this page
        cache_key = f"feed:{user_id}:{cursor or 'first'}"
        self.cache.set(cache_key, {
            'items': items,
            'next_cursor': next_cursor.encode() if next_cursor else None
        }, ttl=300)
        
        # Async prefetch next pages
        if next_cursor:
            self.trigger_prefetch(user_id, next_cursor, self.prefetch_pages)
        
        return {
            'items': items,
            'next_cursor': next_cursor.encode() if next_cursor else None,
            'has_more': next_cursor is not None
        }
    
    def trigger_prefetch(self, user_id: str, cursor: FeedCursor, count: int):
        """Async prefetch next N pages."""
        import threading
        
        def prefetch():
            current_cursor = cursor
            for _ in range(count):
                if not current_cursor:
                    break
                
                items, next_cursor = self.paginator.get_feed_page(
                    user_id, current_cursor
                )
                
                # Cache prefetched page
                cache_key = f"feed:{user_id}:{current_cursor.encode()}"
                self.cache.set(cache_key, {
                    'items': items,
                    'next_cursor': next_cursor.encode() if next_cursor else None
                }, ttl=300)
                
                current_cursor = next_cursor
        
        threading.Thread(target=prefetch, daemon=True).start()
```

**Pattern 2: Feed Pruning and TTL Management**

```python
import time
from datetime import datetime, timedelta
from dataclasses import dataclass

@dataclass
class FeedRetentionPolicy:
    max_items: int = 1000           # Max items per user's feed
    max_age_days: int = 30          # Max age of feed items
    prune_batch_size: int = 100     # Items to prune per batch
    prune_interval_hours: int = 6   # How often to run pruning

class FeedPruner:
    """
    Manage feed size and TTL across shards.
    
    Strategies:
    1. Count-based: Keep last N items
    2. Time-based: Keep items from last M days
    3. Hybrid: Whichever removes more
    """
    
    def __init__(self, shards, policy: FeedRetentionPolicy):
        self.shards = shards
        self.policy = policy
    
    def prune_user_feed(self, user_id: str, shard) -> int:
        """
        Prune a single user's feed.
        Returns number of items removed.
        """
        removed = 0
        
        # Get current feed stats
        stats = shard.get_feed_stats(user_id)
        
        # Count-based pruning
        if stats['count'] > self.policy.max_items:
            excess = stats['count'] - self.policy.max_items
            removed += shard.remove_oldest(user_id, limit=excess)
        
        # Time-based pruning
        cutoff = datetime.utcnow() - timedelta(days=self.policy.max_age_days)
        removed += shard.remove_before_timestamp(user_id, cutoff)
        
        return removed
    
    def run_pruning_job(self):
        """
        Background job to prune all feeds.
        Runs across all shards in parallel.
        """
        from concurrent.futures import ThreadPoolExecutor
        
        total_removed = 0
        
        with ThreadPoolExecutor(max_workers=len(self.shards)) as executor:
            futures = []
            
            for shard in self.shards:
                future = executor.submit(self.prune_shard, shard)
                futures.append(future)
            
            for future in futures:
                total_removed += future.result()
        
        return total_removed
    
    def prune_shard(self, shard) -> int:
        """Prune all feeds on a single shard."""
        removed = 0
        cursor = None
        
        while True:
            # Get batch of user IDs
            users, cursor = shard.scan_users(
                cursor=cursor,
                count=self.policy.prune_batch_size
            )
            
            for user_id in users:
                removed += self.prune_user_feed(user_id, shard)
            
            if cursor is None:
                break
        
        return removed


class AdaptiveFeedSize:
    """
    Adjust feed size based on user activity.
    
    Active users get larger feeds (they scroll more).
    Inactive users get smaller feeds (save storage).
    """
    
    def __init__(self, shard, activity_tracker):
        self.shard = shard
        self.activity = activity_tracker
    
    def get_max_items_for_user(self, user_id: str) -> int:
        """Calculate appropriate feed size for user."""
        activity_score = self.activity.get_score(user_id)
        
        # Activity score 0-1, where 1 is very active
        if activity_score > 0.8:
            return 2000  # Power user
        elif activity_score > 0.5:
            return 1000  # Regular user
        elif activity_score > 0.2:
            return 500   # Occasional user
        else:
            return 200   # Inactive user
    
    def should_fan_out_to_user(self, user_id: str, 
                                author_priority: int) -> bool:
        """
        Decide whether to fan out to this user.
        
        For inactive users, only fan out high-priority content.
        """
        activity_score = self.activity.get_score(user_id)
        
        if activity_score > 0.5:
            return True  # Active user: always fan out
        
        # Inactive user: only high-priority posts
        return author_priority >= 7  # 1-10 scale
```

**Pattern 3: Feed Deduplication and Ranking Integration**

```python
from typing import List, Set
import hashlib

class FeedDeduplicator:
    """
    Prevent duplicate posts in feeds.
    
    Duplicates happen when:
    1. User follows both author and re-sharer
    2. Post is edited and re-indexed
    3. Cross-posted to multiple channels
    """
    
    def __init__(self, dedup_window_hours=24):
        self.window = dedup_window_hours
        self.seen_cache = {}  # user_id -> set of content_hashes
    
    def get_content_hash(self, post: dict) -> str:
        """
        Generate content hash for deduplication.
        Hash based on: original author, content text, media.
        """
        canonical = f"{post['original_author']}:{post['content'][:100]}"
        return hashlib.md5(canonical.encode()).hexdigest()[:16]
    
    def filter_duplicates(self, user_id: str, 
                          posts: List[dict]) -> List[dict]:
        """Remove duplicates from post list."""
        if user_id not in self.seen_cache:
            self.seen_cache[user_id] = set()
        
        seen = self.seen_cache[user_id]
        unique_posts = []
        
        for post in posts:
            content_hash = self.get_content_hash(post)
            
            if content_hash not in seen:
                seen.add(content_hash)
                unique_posts.append(post)
        
        return unique_posts
    
    def add_to_feed_with_dedup(self, shard, user_id: str, post: dict) -> bool:
        """
        Add post to feed only if not duplicate.
        Returns True if added, False if duplicate.
        """
        content_hash = self.get_content_hash(post)
        
        # Check recent feed for duplicates
        existing = shard.query(
            user_id=user_id,
            content_hash=content_hash,
            limit=1
        )
        
        if existing:
            return False  # Duplicate
        
        shard.insert(user_id, {**post, 'content_hash': content_hash})
        return True


class RankedFeedMerger:
    """
    Merge multiple feed sources with ML-based ranking.
    
    Sources:
    1. Pre-computed feed (fan-out on write)
    2. Celebrity posts (fan-out on read)
    3. Recommended posts (discovery)
    4. Ads (monetization)
    """
    
    def __init__(self, ranking_model, ad_service):
        self.ranker = ranking_model
        self.ads = ad_service
    
    def merge_and_rank(self, user_id: str,
                       feed_posts: List[dict],
                       celebrity_posts: List[dict],
                       recommended: List[dict]) -> List[dict]:
        """
        Merge all sources with ranking.
        """
        # Tag source for later analysis
        for p in feed_posts:
            p['source'] = 'feed'
        for p in celebrity_posts:
            p['source'] = 'celebrity'
        for p in recommended:
            p['source'] = 'recommended'
        
        # Combine all candidates
        candidates = feed_posts + celebrity_posts + recommended
        
        # Score each candidate
        user_features = self.get_user_features(user_id)
        
        for post in candidates:
            post['score'] = self.ranker.score(
                user_features=user_features,
                post_features=self.get_post_features(post),
                context_features=self.get_context_features()
            )
        
        # Sort by score
        candidates.sort(key=lambda x: x['score'], reverse=True)
        
        # Insert ads at appropriate positions
        final_feed = self.insert_ads(user_id, candidates)
        
        return final_feed
    
    def insert_ads(self, user_id: str, posts: List[dict]) -> List[dict]:
        """Insert ads at regular intervals."""
        ad_frequency = 5  # One ad every 5 posts
        
        result = []
        ad_index = 0
        
        for i, post in enumerate(posts):
            result.append(post)
            
            if (i + 1) % ad_frequency == 0:
                ad = self.ads.get_next_ad(user_id, ad_index)
                if ad:
                    result.append({'type': 'ad', **ad})
                    ad_index += 1
        
        return result
    
    def get_user_features(self, user_id: str) -> dict:
        """Extract features for ranking model."""
        return {
            'user_id': user_id,
            'interests': self.get_user_interests(user_id),
            'activity_level': self.get_activity_level(user_id),
            'recent_interactions': self.get_recent_interactions(user_id)
        }
    
    def get_post_features(self, post: dict) -> dict:
        """Extract features from post."""
        return {
            'post_id': post['post_id'],
            'author_id': post['author_id'],
            'content_type': post.get('content_type', 'text'),
            'age_hours': (time.time() - post['timestamp']) / 3600,
            'engagement_score': post.get('likes', 0) + post.get('comments', 0) * 2
        }
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

```python
# Fencing token example
class FencingLeader:
    def acquire_leadership(self):
        # Atomically increment and get fencing token
        token = self.consensus.increment_and_get("leader_token")
        self.current_token = token
        return token
    
    def write(self, data):
        # Storage rejects writes with old tokens
        self.storage.write(data, fencing_token=self.current_token)

# Storage side
class FencedStorage:
    def write(self, data, fencing_token):
        if fencing_token < self.highest_seen_token:
            raise StaleLeaderError("You've been fenced")
        self.highest_seen_token = fencing_token
        # Proceed with write
```

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
│  ┌──────────────────────────────────┐           ┌──────────────────┐    │
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

```python
from prometheus_client import Counter, Histogram, Gauge

# Per-shard metrics
shard_requests = Counter(
    'shard_requests_total',
    'Total requests per shard',
    ['shard_id', 'operation']  # operation: read, write
)

shard_latency = Histogram(
    'shard_request_duration_seconds',
    'Request latency per shard',
    ['shard_id', 'operation'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

shard_replication_lag = Gauge(
    'shard_replication_lag_seconds',
    'Replication lag in seconds',
    ['shard_id', 'replica_id']
)

shard_size_bytes = Gauge(
    'shard_size_bytes',
    'Data size per shard',
    ['shard_id']
)

shard_connection_pool = Gauge(
    'shard_connection_pool_size',
    'Active connections per shard',
    ['shard_id', 'pool_state']  # pool_state: active, idle, waiting
)

# Cross-shard operation metrics
cross_shard_queries = Counter(
    'cross_shard_queries_total',
    'Queries spanning multiple shards',
    ['query_type']
)

scatter_gather_shards = Histogram(
    'scatter_gather_shards_count',
    'Number of shards hit per scatter-gather query',
    buckets=[1, 2, 4, 8, 16, 32, 64]
)
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

```yaml
# Example Prometheus alerting rules
groups:
  - name: sharding_alerts
    rules:
      - alert: ShardReplicationLagHigh
        expr: shard_replication_lag_seconds > 5
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Shard {{ $labels.shard_id }} replication lag is {{ $value }}s"
      
      - alert: ShardReplicationLagCritical
        expr: shard_replication_lag_seconds > 30
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "CRITICAL: Shard {{ $labels.shard_id }} lag {{ $value }}s - routing reads to leader"
      
      - alert: HotShardDetected
        expr: (shard_requests_total / ignoring(shard_id) group_left avg(shard_requests_total)) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Shard {{ $labels.shard_id }} receiving 2x average traffic"
```

#### Distributed Tracing for Sharded Queries

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

class TracedShardRouter:
    def execute_query(self, query, shard_key):
        with tracer.start_as_current_span("shard_query") as span:
            # Record shard routing decision
            shard_id = self.get_shard(shard_key)
            span.set_attribute("shard.id", shard_id)
            span.set_attribute("shard.key", str(shard_key))
            
            # Execute with timing
            start = time.time()
            try:
                result = self.shards[shard_id].execute(query)
                span.set_attribute("shard.row_count", len(result))
                return result
            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                raise
            finally:
                span.set_attribute("shard.duration_ms", (time.time() - start) * 1000)
    
    def scatter_gather(self, query):
        with tracer.start_as_current_span("scatter_gather") as span:
            span.set_attribute("scatter.shard_count", len(self.shards))
            
            results = []
            for shard_id, shard in enumerate(self.shards):
                with tracer.start_as_current_span(f"shard_{shard_id}") as child:
                    child.set_attribute("shard.id", shard_id)
                    results.append(shard.execute(query))
            
            span.set_attribute("gather.total_rows", sum(len(r) for r in results))
            return self.merge(results)
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

```python
class ShardMigrationOrchestrator:
    def __init__(self, shards, migration_id):
        self.shards = shards
        self.migration_id = migration_id
        self.state_store = MigrationStateStore()
    
    def run_migration(self, ddl_statement, parallel=True):
        """Run DDL across all shards with tracking."""
        
        # Initialize state
        for shard in self.shards:
            self.state_store.set(self.migration_id, shard.id, 'pending')
        
        if parallel:
            self._run_parallel(ddl_statement)
        else:
            self._run_sequential(ddl_statement)
        
        # Verify all completed
        return self._verify_all_complete()
    
    def _run_parallel(self, ddl):
        futures = {}
        with ThreadPoolExecutor(max_workers=16) as executor:
            for shard in self.shards:
                future = executor.submit(self._migrate_shard, shard, ddl)
                futures[future] = shard
            
            for future in as_completed(futures):
                shard = futures[future]
                try:
                    future.result()
                    self.state_store.set(self.migration_id, shard.id, 'complete')
                except Exception as e:
                    self.state_store.set(self.migration_id, shard.id, f'failed: {e}')
    
    def _migrate_shard(self, shard, ddl):
        state = self.state_store.get(self.migration_id, shard.id)
        
        if state == 'complete':
            return  # Already done (idempotent)
        
        self.state_store.set(self.migration_id, shard.id, 'running')
        shard.execute(ddl)
    
    def get_status(self):
        """Get migration status across all shards."""
        status = {}
        for shard in self.shards:
            status[shard.id] = self.state_store.get(self.migration_id, shard.id)
        return status
    
    def resume(self, ddl):
        """Resume a failed migration - only run on incomplete shards."""
        status = self.get_status()
        incomplete = [s for s in self.shards if status[s.id] != 'complete']
        
        for shard in incomplete:
            self._migrate_shard(shard, ddl)
```

#### Handling Mixed Schema State

During migration, some shards have new schema, some have old:

```python
class SchemaAwareRepository:
    def __init__(self, shards, migration_tracker):
        self.shards = shards
        self.migration_tracker = migration_tracker
    
    def get_user(self, user_id):
        shard = self.get_shard(user_id)
        
        if self.migration_tracker.is_complete('add_preferences', shard.id):
            # New schema - include preferences
            return shard.query(
                "SELECT id, name, email, preferences FROM users WHERE id = %s",
                [user_id]
            )
        else:
            # Old schema - set default
            user = shard.query(
                "SELECT id, name, email FROM users WHERE id = %s",
                [user_id]
            )
            user['preferences'] = {}  # Default value
            return user
```

**Staff-Level Insight:** Never make breaking schema changes. Use expand-contract. A "breaking" change (like renaming a column) becomes: add new column → backfill → migrate code → drop old column. Tedious? Yes. Safe? Also yes.

---

### 4.6 Testing Sharded Systems

Testing distributed systems is fundamentally harder than testing monoliths. Here's how to do it right.

#### Unit Testing Shard Routing

```python
import pytest

class TestShardRouting:
    """Test that routing logic is correct and consistent."""
    
    def test_same_key_same_shard(self):
        """Same key should always route to same shard."""
        router = ConsistentHashRing(nodes=["s0", "s1", "s2", "s3"])
        
        key = "user_12345"
        shard1 = router.get_node(key)
        shard2 = router.get_node(key)
        
        assert shard1 == shard2
    
    def test_distribution_evenness(self):
        """Keys should be evenly distributed across shards."""
        router = ConsistentHashRing(nodes=["s0", "s1", "s2", "s3"])
        
        distribution = {"s0": 0, "s1": 0, "s2": 0, "s3": 0}
        
        for i in range(10000):
            shard = router.get_node(f"user_{i}")
            distribution[shard] += 1
        
        # Each shard should have ~2500 keys (25% each)
        for shard, count in distribution.items():
            assert 2000 < count < 3000, f"{shard} has {count} keys (expected ~2500)"
    
    def test_minimal_rebalancing_on_add(self):
        """Adding a shard should move ~20% of keys, not all."""
        router = ConsistentHashRing(nodes=["s0", "s1", "s2", "s3"])
        
        # Record initial placement
        initial_placement = {}
        for i in range(1000):
            key = f"user_{i}"
            initial_placement[key] = router.get_node(key)
        
        # Add a shard
        router.add_node("s4")
        
        # Count how many keys moved
        moved = 0
        for key, original_shard in initial_placement.items():
            if router.get_node(key) != original_shard:
                moved += 1
        
        # Should move ~20% (1/5 of keys)
        assert 150 < moved < 300, f"Moved {moved} keys (expected ~200)"
```

#### Integration Testing with Multiple Shards

```python
import docker
import pytest

@pytest.fixture(scope="session")
def sharded_database():
    """Spin up multiple database containers for integration tests."""
    client = docker.from_env()
    
    containers = []
    for i in range(4):
        container = client.containers.run(
            "postgres:14",
            detach=True,
            ports={5432: 5432 + i},
            environment={
                "POSTGRES_DB": f"shard_{i}",
                "POSTGRES_PASSWORD": "test"
            },
            name=f"test_shard_{i}"
        )
        containers.append(container)
    
    # Wait for all to be ready
    for container in containers:
        wait_for_postgres(container)
    
    # Initialize schema on all shards
    for i, container in enumerate(containers):
        apply_schema(host="localhost", port=5432 + i)
    
    yield containers
    
    # Cleanup
    for container in containers:
        container.stop()
        container.remove()

class TestCrossShardOperations:
    def test_scatter_gather_aggregation(self, sharded_database):
        """Test that aggregation across shards works correctly."""
        # Insert data across shards
        for shard_id in range(4):
            insert_test_orders(shard_id, count=100)
        
        # Scatter-gather query
        total_count, total_sum = aggregate_orders_across_shards()
        
        assert total_count == 400
        # Sum should be correct (depends on test data)
    
    def test_cross_shard_transaction_saga(self, sharded_database):
        """Test saga pattern handles failures correctly."""
        # Setup: user A on shard 0, user B on shard 2
        create_user(shard=0, user_id="A", balance=100)
        create_user(shard=2, user_id="B", balance=50)
        
        # Transfer that should succeed
        result = transfer_money("A", "B", amount=25)
        assert result.success
        assert get_balance("A") == 75
        assert get_balance("B") == 75
        
        # Transfer that should fail (insufficient funds)
        result = transfer_money("A", "B", amount=100)
        assert not result.success
        assert get_balance("A") == 75  # Unchanged
        assert get_balance("B") == 75  # Unchanged
```

#### Chaos Engineering for Sharded Systems

```python
class ShardChaosTests:
    """Test system behavior under failure conditions."""
    
    def test_single_shard_failure(self, sharded_cluster):
        """System should continue operating when one shard is down."""
        # Kill shard 2
        sharded_cluster.kill_shard(2)
        
        # Requests to other shards should work
        for user_id in self.users_on_shards([0, 1, 3]):
            response = get_user(user_id)
            assert response.status == 200
        
        # Requests to shard 2 should fail gracefully
        for user_id in self.users_on_shard(2):
            response = get_user(user_id)
            assert response.status == 503  # Service unavailable
            assert "shard unavailable" in response.error
    
    def test_shard_failover(self, sharded_cluster):
        """Replica should take over when primary fails."""
        # Record current primary
        original_primary = sharded_cluster.get_primary(shard=1)
        
        # Kill the primary
        sharded_cluster.kill_node(original_primary)
        
        # Wait for failover
        time.sleep(30)  # Failover timeout
        
        # New primary should be serving
        new_primary = sharded_cluster.get_primary(shard=1)
        assert new_primary != original_primary
        
        # Requests should work
        for user_id in self.users_on_shard(1):
            response = get_user(user_id)
            assert response.status == 200
    
    def test_network_partition(self, sharded_cluster):
        """Test behavior during network partition between shards."""
        # Create partition: shards 0,1 can't reach shards 2,3
        sharded_cluster.create_partition([0, 1], [2, 3])
        
        # Cross-partition scatter-gather should timeout
        with pytest.raises(TimeoutError):
            aggregate_all_shards(timeout=5)
        
        # Same-partition operations should work
        response = get_user(self.users_on_shard(0)[0])
        assert response.status == 200
        
        # Heal partition
        sharded_cluster.heal_partition()
        
        # Full cluster should work again
        result = aggregate_all_shards(timeout=30)
        assert result.success
    
    def test_replication_lag_handling(self, sharded_cluster):
        """Test read-your-writes under replication lag."""
        # Inject artificial lag
        sharded_cluster.inject_replication_lag(shard=0, lag_ms=5000)
        
        # Write and immediate read
        update_user("user_123", {"name": "New Name"})
        
        # Without read-your-writes handling, would get stale data
        # With proper handling, should get fresh data
        user = get_user("user_123")
        assert user.name == "New Name"
```

#### Migration Testing

```python
class TestMigration:
    """Test resharding migrations thoroughly before production."""
    
    def test_migration_data_integrity(self, source_shards, target_shards):
        """All data should be present after migration."""
        # Get checksums before
        before_checksums = {}
        for shard in source_shards:
            before_checksums[shard.id] = shard.checksum_all_tables()
        
        # Run migration
        migrator = ShardMigrator(source_shards, target_shards)
        migrator.run()
        
        # Verify all data present in target
        for key in get_all_keys():
            source_value = get_from_source(key)
            target_value = get_from_target(key)
            assert source_value == target_value, f"Mismatch for {key}"
    
    def test_migration_under_load(self, source_shards, target_shards):
        """Migration should handle concurrent writes."""
        # Start migration in background
        migrator = ShardMigrator(source_shards, target_shards)
        migration_thread = threading.Thread(target=migrator.run)
        migration_thread.start()
        
        # Hammer with writes during migration
        for i in range(10000):
            write_to_source(f"key_{i}", f"value_{i}")
        
        # Wait for migration
        migration_thread.join()
        
        # Verify all writes made it
        for i in range(10000):
            assert get_from_target(f"key_{i}") == f"value_{i}"
    
    def test_migration_rollback(self, source_shards, target_shards):
        """Should be able to rollback failed migration."""
        # Inject failure midway
        migrator = ShardMigrator(source_shards, target_shards)
        migrator.fail_at_percentage = 50
        
        with pytest.raises(MigrationError):
            migrator.run()
        
        # Rollback
        migrator.rollback()
        
        # Source should be unchanged and serving
        for key in get_all_keys():
            value = get_from_source(key)
            assert value is not None
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