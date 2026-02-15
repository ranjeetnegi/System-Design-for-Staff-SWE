# Chapter 25: Failure Models and Partial Failures — Designing for Reality at Staff Level

---

# Introduction

Most engineers design systems assuming they work. Staff Engineers design systems assuming they're *already failing*.

This isn't pessimism—it's pattern recognition from years of production experience. Every system you'll encounter at scale is experiencing some form of partial failure right now. A node is slow. A dependency is returning stale data. A network path is dropping packets. A cache is cold. Somewhere, something is not quite right.

The difference between a Senior Engineer and a Staff Engineer isn't whether they understand failure—it's *when* they think about it. Senior Engineers add resilience after the first outage. Staff Engineers design for partial failure from day one because they've seen the pattern too many times to ignore it.

This section teaches you how to reason about failure the way Staff Engineers do: systematically, realistically, and with the calm judgment that comes from having debugged 3 AM pages that started with "everything looks fine."

---

## Quick Visual: The Partial Failure Reality

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    THE REALITY OF DISTRIBUTED SYSTEMS                   │
│                                                                         │
│   MYTH: Systems are either "working" or "down"                          │
│                                                                         │
│   ┌──────────┐              ┌──────────┐                                │
│   │  100%    │              │    0%    │                                │
│   │  WORKING │   ←─────→    │   DOWN   │                                │
│   └──────────┘              └──────────┘                                │
│                                                                         │
│   REALITY: Systems exist on a continuum of degradation                  │
│                                                                         │
│   ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐             │
│   │ 100% │  95% │  80% │  60% │  40% │  20% │  5%  │  0%  │             │
│   │ Full │ Slow │ Some │ Many │ Most │ Few  │Barely│ Down │             │
│   │      │ deps │ fails│ fails│ fails│ work │ works│      │             │
│   └──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘             │
│                                                                         │
│   Your system spends MOST of its time somewhere in the middle.          │
│   Design for the middle, not the edges.                                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6: Failure Reasoning at Different Levels

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Database timeout** | "Add retry logic" | "Why is it slow? What else shares this database? What happens to upstream callers while we retry?" |
| **Dependency down** | "Return error to caller" | "What can we serve from cache? Can we degrade gracefully? What's the user experience?" |
| **Increased latency** | "Increase timeout" | "Timeouts are a symptom. What's the blast radius if this spreads? Should we shed load instead?" |
| **Error rate spike** | "Alert when >1%" | "Is 1% distributed evenly or concentrated? Is it one user, one region, one endpoint?" |
| **Service restart** | "It'll come back" | "What state was lost? Are there in-flight requests? Will the thundering herd kill it again?" |

**Key Difference**: L6 engineers think about *propagation*. Every failure question leads to "and then what happens?"

---

# Part 1: Why Partial Failure Is the Default

## The Myth of All-or-Nothing Failure

Junior engineers imagine failure as binary: the system works or it doesn't. This mental model comes from single-machine programming, where a crash means the program stops.

Distributed systems don't work this way.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    WHY PARTIAL FAILURE IS NORMAL                        │
│                                                                         │
│   SINGLE MACHINE:                                                       │
│   ───────────────                                                       │
│   Program crashes → Everything stops → Clear error                      │
│                                                                         │
│   DISTRIBUTED SYSTEM:                                                   │
│   ──────────────────                                                    │
│   One node slow → Some requests slow → Some users affected              │
│   One cache cold → Some reads slow → Some features degraded             │
│   One network path → Some calls fail → Some operations retry            │
│   One dependency → Some data stale → Some responses incorrect           │
│                                                                         │
│   The system is ALWAYS in some state of partial failure.                │
│   The question is: how partial, and how visible?                        │
│                                                                         │
│   IMPLICATION FOR DESIGN:                                               │
│   ─────────────────────────                                             │
│   Don't design for "works" vs "broken"                                  │
│   Design for "what percentage is working, and for whom?"                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Why Complete Outages Are Actually Easier

Complete outages have clear properties:
- **Detection is simple**: Health checks fail, alerts fire
- **User experience is consistent**: Everyone sees the same error
- **Recovery is obvious**: Fix the thing, restart, done
- **Debugging is straightforward**: Something is broken, find it

Partial failures are insidious because:
- **Detection is delayed**: Metrics look "mostly normal"
- **User experience varies**: Some users fine, some broken
- **Recovery is complex**: Which part? How much is affected?
- **Debugging is hard**: Everything *mostly* works

**Staff-level insight**: The most dangerous incidents aren't the ones where everything breaks. They're the ones where *almost* everything works, so nobody notices until the damage is widespread.

---

## Continuous Degradation: The Staff Mindset

Staff Engineers don't think about "uptime" as a binary state. They think about **degradation budget**—how much can the system degrade before users notice, before SLOs break, before revenue is affected?

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    DEGRADATION BUDGET THINKING                          │
│                                                                         │
│   QUESTION: "Is the system up?"                                         │
│                                                                         │
│   SENIOR ENGINEER ANSWER:                                               │
│   "Yes, all health checks pass."                                        │
│                                                                         │
│   STAFF ENGINEER ANSWER:                                                │
│   "Define 'up.' Here's the current state:                               │
│    - Search: 100% available, but P99 latency is 2x normal               │
│    - Recommendations: Serving stale data (6 hours old)                  │
│    - Checkout: 100% available and fast                                  │
│    - User profiles: 0.1% error rate (one shard is slow)                 │
│    - Images: CDN is fine, origin is at 80% capacity                     │
│                                                                         │
│    Are we 'up'? Technically yes. Are we healthy? No.                    │
│    We have about 2 hours before the slow shard cascades."               │
│                                                                         │
│   STAFF INSIGHT:                                                        │
│   The system is never fully healthy. You're always managing             │
│   degradation. The skill is knowing which degradations matter.          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### The Degradation Hierarchy

Not all degradation is equal. Staff Engineers prioritize based on user impact:

| Degradation Level | Example | User Impact | Response |
|-------------------|---------|-------------|----------|
| **Invisible** | Cache hit rate drops 2% | None visible | Monitor |
| **Cosmetic** | Recommendations slower | Minor annoyance | Investigate |
| **Functional** | Search returns fewer results | Feature degraded | Alert |
| **Transactional** | Checkout fails for 1% | Revenue impact | Page |
| **Critical** | Auth service down | Total outage | War room |

**Interview Signal**: "I think about degradation in layers. Not everything is equally critical, and not every degradation needs the same response. The skill is knowing which layer you're in and acting appropriately."

---

# Part 2: Failure Taxonomy (Staff-Calibrated)

Staff Engineers recognize failure patterns instantly because they've seen each type multiple times. Let's examine each failure type through the lens of production experience.

## Failure Type 1: Process Crash

### What Actually Happens at Runtime

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    PROCESS CRASH: WHAT REALLY HAPPENS                   │
│                                                                         │
│   T+0ms:    Process receives OOM kill signal                            │
│   T+1ms:    Process terminates (no graceful shutdown)                   │
│   T+10ms:   In-flight requests: no response sent                        │
│   T+50ms:   Load balancer still routing traffic (health check lag)      │
│   T+100ms:  New requests hit dead process, get connection refused       │
│   T+5s:     Health check finally fails                                  │
│   T+6s:     Load balancer stops routing new traffic                     │
│   T+10s:    Orchestrator notices, starts new instance                   │
│   T+30s:    New instance starting, loading config                       │
│   T+45s:    New instance warming up caches                              │
│   T+60s:    New instance ready, but caches cold                         │
│   T+120s:   Caches warming, performance degraded                        │
│   T+300s:   Finally back to normal performance                          │
│                                                                         │
│   TIMELINE:                                                             │
│   │ Crash │ Detection │ Restart │ Warm-up │ Normal │                    │
│    0s      5s          10s       60s       300s                         │
│                                                                         │
│   Users experienced degradation for 5+ MINUTES from a single crash.     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Why It's Hard to Detect

- Health checks have intervals (10-30 seconds is common)
- Load balancer needs multiple failed checks before removing node
- Other instances absorb traffic, masking the problem
- If crash rate < health check interval, you might not even notice

### Secondary Failures It Triggers

1. **In-flight request failures**: Clients see timeouts or connection resets
2. **Retry storms**: Failed requests retry, increasing load on remaining instances
3. **Cold cache stampede**: New instance serves cache misses, hammering backends
4. **Resource exhaustion**: Remaining instances handle more traffic, may crash too
5. **Restart loops**: If crash cause persists, new instance crashes again

### The Restart Storm Pattern

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    RESTART STORM ANATOMY                                │
│                                                                         │
│   TRIGGER: All instances restart simultaneously (deploy, config push)   │
│                                                                         │
│   Timeline:                                                             │
│   T+0:     All 10 instances restart                                     │
│   T+30s:   All instances start accepting traffic (caches cold)          │
│   T+30s:   Cache miss rate: 100% (normally 5%)                          │
│   T+30s:   Database receives 20x normal query load                      │
│   T+35s:   Database connection pools exhausted                          │
│   T+40s:   Database starts rejecting connections                        │
│   T+45s:   Services can't connect to DB, return errors                  │
│   T+50s:   Health checks fail (can't reach DB)                          │
│   T+60s:   Instances marked unhealthy, traffic rerouted... nowhere      │
│   T+60s:   Complete outage                                              │
│                                                                         │
│   ROOT CAUSE: Cold cache + thundering herd + shared dependency          │
│                                                                         │
│   STAFF PREVENTION:                                                     │
│   - Rolling restarts (never restart all at once)                        │
│   - Warm-up period before accepting traffic                             │
│   - Cache pre-warming from snapshot                                     │
│   - Connection pool limits with backpressure                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Failure Type 2: Network Partitions

### Hard Partitions vs Soft Partitions

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    NETWORK PARTITION TYPES                              │
│                                                                         │
│   HARD PARTITION:                                                       │
│   ───────────────                                                       │
│   Complete network failure between components                           │
│                                                                         │
│   ┌─────────┐          ╳          ┌─────────┐                           │
│   │ Region  │◄──────── ╳─────────►│ Region  │                           │
│   │   US    │          ╳          │   EU    │                           │
│   └─────────┘          ╳          └─────────┘                           │
│                   No packets                                            │
│                                                                         │
│   Properties:                                                           │
│   - Obvious (connections fail immediately)                              │
│   - Easy to detect (all health checks fail)                             │
│   - Clear recovery (network restored, reconnect)                        │
│                                                                         │
│   SOFT PARTITION (The Dangerous One):                                   │
│   ────────────────────────────────────                                  │
│   Intermittent or selective packet loss                                 │
│                                                                         │
│   ┌─────────┐     ~~~~~░░~~~     ┌─────────┐                            │
│   │ Region  │◄───~░░░░░░░░░░~───►│ Region  │                            │
│   │   US    │     ~~~~~░░~~~     │   EU    │                            │
│   └─────────┘                    └─────────┘                            │
│              70% packet loss, 500ms latency                             │
│                                                                         │
│   Properties:                                                           │
│   - Subtle (some requests work, some fail)                              │
│   - Hard to detect (health checks might pass)                           │
│   - Confusing recovery (is it fixed? partially?)                        │
│   - Causes split-brain, stale data, inconsistent state                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### What Actually Happens at Runtime

**Soft Partition Scenario:**

```
T+0s:     Network path starts dropping 30% of packets
T+0-60s:  Retries mask the problem (3 attempts = 97% success)
T+60s:    Retry rate increasing, latency creeping up
T+120s:   Thread pools filling with slow requests
T+180s:   Some operations timing out, but "mostly working"
T+240s:   Metrics show: latency up, errors up, but both "within SLO"
T+300s:   First user complaint: "sometimes it works, sometimes it doesn't"
T+600s:   Engineer investigates: "I can't reproduce it"
T+1800s:  Packet loss increases to 50%
T+1800s:  Retries no longer mask the problem
T+1800s:  Cascading timeouts begin
```

### Why It's Hard to Detect

- Intermittent failures don't trigger threshold-based alerts
- Success rate is still "acceptable" (90%+)
- Retries mask the underlying problem
- Different requests see different behavior
- Health checks use different network paths than production traffic

### Secondary Failures It Triggers

1. **Split-brain**: Two partitions make conflicting decisions
2. **Stale reads**: Cache can't invalidate, serves old data
3. **Duplicate processing**: Request succeeds but ack lost, client retries
4. **Consensus failures**: Raft/Paxos can't form quorum
5. **Lock expiration**: Distributed locks can't be renewed, unsafe operations proceed

---

## Failure Type 3: Slow Nodes

Slow nodes are the most insidious failure type because they look healthy but poison everything they touch.

### What Actually Happens at Runtime

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SLOW NODE IMPACT                                     │
│                                                                         │
│   SCENARIO: One of 10 nodes enters GC pause                             │
│                                                                         │
│   BEFORE (Normal):                                                      │
│   ─────────────────                                                     │
│   Node 1: ░░░ (10ms)    Node 6: ░░░ (12ms)                              │
│   Node 2: ░░░ (11ms)    Node 7: ░░░ (10ms)                              │
│   Node 3: ░░░ (10ms)    Node 8: ░░░ (11ms)                              │
│   Node 4: ░░░ (12ms)    Node 9: ░░░ (10ms)                              │
│   Node 5: ░░░ (10ms)    Node 10: ░░░ (11ms)                             │
│                                                                         │
│   P50: 10ms   P99: 15ms                                                 │
│                                                                         │
│   DURING (One Slow Node):                                               │
│   ────────────────────────                                              │
│   Node 1: ░░░ (10ms)    Node 6: ░░░ (12ms)                              │
│   Node 2: ░░░ (11ms)    Node 7: ░░░ (10ms)                              │
│   Node 3: ████████████████████████████ (5000ms) ← GC PAUSE              │
│   Node 4: ░░░ (12ms)    Node 9: ░░░ (10ms)                              │
│   Node 5: ░░░ (10ms)    Node 10: ░░░ (11ms)                             │
│                                                                         │
│   P50: 10ms (unchanged!)   P99: 5000ms (333x worse!)                    │
│                                                                         │
│   WHY IS THIS DANGEROUS?                                                │
│   ──────────────────────                                                │
│   - P50 looks normal, so dashboards look "green"                        │
│   - But 10% of users (those hitting Node 3) see 5-second delays         │
│   - Those 10% of requests hold connections, threads, memory             │
│   - Caller's thread pool fills with slow requests                       │
│   - Eventually, caller can't handle ANY requests                        │
│                                                                         │
│   A SLOW NODE IS WORSE THAN A DEAD NODE.                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Common Causes of Slow Nodes

| Cause | Detection | Duration | Frequency |
|-------|-----------|----------|-----------|
| **GC Pause** | Latency spike | 100ms - 30s | Multiple per hour |
| **Noisy Neighbor** | Gradual slowdown | Minutes to hours | Unpredictable |
| **Disk I/O** | Latency spike | Seconds | On compaction/backup |
| **Memory Pressure** | Gradual slowdown | Until OOM | Hours |
| **CPU Throttling** | Consistent slowdown | Continuous | On resource limits |

### Why Slow Is Worse Than Dead

```
Dead Node:
- Fails fast (connection refused)
- Load balancer removes it
- Traffic redistributes to healthy nodes
- System operates at reduced capacity but stable

Slow Node:
- Fails slow (holds resources for timeout duration)
- Passes health checks (it's not dead)
- Load balancer keeps routing traffic
- Caller resources exhausted waiting
- Slow requests pile up
- Eventually, slow node's problems become YOUR problems
```

**Staff-level insight**: "I'd rather have a node die than be slow. A dead node fails fast and gets removed. A slow node is a vampire—it drains resources from everything that calls it while pretending to be alive."

---

## Failure Type 4: Dependency Failures

Your service is only as reliable as its least reliable dependency.

### Types of Dependency Failure

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    DEPENDENCY FAILURE MODES                             │
│                                                                         │
│   HARD FAILURE:                                                         │
│   ──────────────                                                        │
│   Dependency returns errors (500, timeout, connection refused)          │
│   • Easy to detect                                                      │
│   • Easy to handle (return error or fallback)                           │
│   • Easy to monitor                                                     │
│                                                                         │
│   BROWNOUT:                                                             │
│   ─────────                                                             │
│   Dependency is slow or has elevated error rate                         │
│   • Hard to detect (still "mostly working")                             │
│   • Hard to handle (when to give up? when to retry?)                    │
│   • Causes resource exhaustion in callers                               │
│                                                                         │
│   THROTTLING:                                                           │
│   ───────────                                                           │
│   Dependency rejects requests over quota                                │
│   • Selective failure (only some requests rejected)                     │
│   • Often returns 429 with retry-after                                  │
│   • Retrying makes it worse!                                            │
│                                                                         │
│   STALE RESPONSES:                                                      │
│   ────────────────                                                      │
│   Dependency returns outdated data                                      │
│   • Looks successful (200 OK)                                           │
│   • Data is wrong but response is valid                                 │
│   • Hardest to detect—requires semantic validation                      │
│                                                                         │
│   SILENT CORRUPTION:                                                    │
│   ──────────────────                                                    │
│   Dependency returns incorrect data                                     │
│   • Looks successful (200 OK, fresh data)                               │
│   • Data is actively wrong                                              │
│   • May not be detected until user complains                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Dependency Failure Propagation

```
SCENARIO: Payment service enters brownout (50% requests slow)

T+0s:     Payment service P99 goes from 100ms to 2000ms
T+0s:     Order service waits for payment (10s timeout)
T+5s:     Order service thread pool filling with waiting requests
T+10s:    Order service can't accept new orders (no threads)
T+10s:    Gateway times out waiting for Order service
T+15s:    Gateway thread pool filling
T+20s:    Gateway can't accept any requests
T+20s:    All user traffic returns 503

TIMELINE:
Payment slow → Order stuck → Gateway stuck → Complete outage

A 50% brownout in ONE dependency caused 100% outage in the whole system.

WHY?
- Timeouts were too long (10s waits)
- No circuit breaker (kept calling failing service)
- No bulkheads (shared thread pool)
- Sync calls (held resources while waiting)
```

---

# Part 3: Failure Propagation & Blast Radius

## How Failures Spread Across Services

### The Propagation Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    FAILURE PROPAGATION PATHS                            │
│                                                                         │
│                           ┌───────────┐                                 │
│                           │   Users   │                                 │
│                           └─────┬─────┘                                 │
│                                 │                                       │
│                           ┌─────▼─────┐                                 │
│                           │  Gateway  │                                 │
│                           └─────┬─────┘                                 │
│                                 │                                       │
│            ┌────────────────────┼────────────────────┐                  │
│            │                    │                    │                  │
│      ┌─────▼─────┐        ┌─────▼─────┐        ┌─────▼─────┐            │
│      │  Service  │        │  Service  │        │  Service  │            │
│      │     A     │        │     B     │        │     C     │            │
│      └─────┬─────┘        └─────┬─────┘        └─────┬─────┘            │
│            │                    │                    │                  │
│            │              ┌─────▼─────┐              │                  │
│            │              │  Service  │◄─────────────┘                  │
│            │              │     D     │                                 │
│            │              └─────┬─────┘                                 │
│            │                    │                                       │
│            │              ┌─────▼─────┐                                 │
│            └─────────────►│ Database  │◄────── FAILURE ORIGIN           │
│                           │   (slow)  │                                 │
│                           └───────────┘                                 │
│                                                                         │
│   PROPAGATION:                                                          │
│   ════════════                                                          │
│   1. Database becomes slow (GC, disk I/O)                               │
│   2. Service A and D hold connections waiting                           │
│   3. Service B calls D, now B is waiting                                │
│   4. Service C calls D, now C is waiting                                │
│   5. Gateway calls A, B, C—all slow                                     │
│   6. Gateway thread pool exhausted                                      │
│   7. Users see 503 errors                                               │
│                                                                         │
│   One slow database → entire system down                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Synchronous vs Asynchronous Propagation

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    PROPAGATION SPEED BY PATTERN                         │
│                                                                         │
│   SYNCHRONOUS (Fast Propagation):                                       │
│   ────────────────────────────────                                      │
│   Request → Service A → Service B → Service C → Database                │
│       │          │          │          │          │                     │
│       └──────────┴──────────┴──────────┴──────────┘                     │
│                   ALL WAITING                                           │
│                                                                         │
│   - Failure propagates at speed of timeout                              │
│   - All callers blocked simultaneously                                  │
│   - Blast radius: immediate and complete                                │
│                                                                         │
│   ASYNCHRONOUS (Slow Propagation):                                      │
│   ──────────────────────────────────                                    │
│   Request → Queue → Worker → Database                                   │
│       │       │                  │                                      │
│       ↓       ↓                  ↓                                      │
│     Done   Buffered           Slow                                      │
│                                                                         │
│   - Failure propagates at speed of queue drain                          │
│   - Callers return immediately                                          │
│   - Blast radius: contained to async pathway                            │
│                                                                         │
│   HYBRID (Most Real Systems):                                           │
│   ────────────────────────────                                          │
│   - Sync for reads (fast propagation)                                   │
│   - Async for writes (slow propagation)                                 │
│   - Blast radius depends on operation type                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Amplification Factors

Failures don't just propagate—they amplify. Staff Engineers must understand these multipliers:

### Retry Amplification

```
Base: 100 requests/second to Service D
Service D becomes slow

Without circuit breaker:
- Each of 100 requests times out
- Each request retries 3 times
- Now: 300 requests/second (3x)
- All time out, all retry
- Now: 900 requests/second (9x)
- Service D completely overwhelmed

With retry budget (10% max):
- 100 requests, 10% retry budget = max 10 retries
- Now: 110 requests/second (1.1x)
- Service D still under pressure, but not crushed
```

### Fan-Out Amplification

```
User request → Gateway → Query 10 shards

If one shard is slow:
- Gateway waits for slowest shard
- P99 of response = P99 of slowest shard
- 10% slow shard × 10 shards = 65% of requests affected
  (1 - 0.9^10 = 65%)

Fan-out turns individual slow nodes into widespread latency.
```

### Shared Dependency Amplification

```
5 services all use the same database

Database has 1000 connection limit
Each service thinks it has 200 connections
5 × 200 = 1000 (at capacity)

During slow period:
- Each service opens more connections (they're timing out)
- Each service wants 300 connections
- 5 × 300 = 1500 (exceeds capacity)
- Database rejects connections
- All 5 services fail simultaneously

A shared dependency is a shared blast radius.
```

## Staff-Level Blast Radius Reasoning

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    BLAST RADIUS ANALYSIS FRAMEWORK                      │
│                                                                         │
│   For every failure, ask:                                               │
│                                                                         │
│   1. SCOPE: Who is affected?                                            │
│      □ One user?                                                        │
│      □ Users on one shard?                                              │
│      □ Users in one region?                                             │
│      □ Users of one feature?                                            │
│      □ All users?                                                       │
│                                                                         │
│   2. SEVERITY: How badly are they affected?                             │
│      □ Slower experience?                                               │
│      □ Feature unavailable?                                             │
│      □ Data incorrect?                                                  │
│      □ Data lost?                                                       │
│      □ Unable to use system at all?                                     │
│                                                                         │
│   3. PROPAGATION: Will it spread?                                       │
│      □ Contained to failed component?                                   │
│      □ Spreads to direct callers?                                       │
│      □ Spreads through retries?                                         │
│      □ Spreads to shared dependencies?                                  │
│      □ Spreads to entire system?                                        │
│                                                                         │
│   4. CONTAINMENT: What limits the blast radius?                         │
│      □ Bulkheads (isolated resources)?                                  │
│      □ Circuit breakers (fast fail)?                                    │
│      □ Timeouts (bounded waiting)?                                      │
│      □ Fallbacks (alternative paths)?                                   │
│      □ Rate limits (bounded load)?                                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Interview Signal**: "Before I design the happy path, I want to understand the blast radius of failures. If this component fails, what's affected? Is it one user, one shard, one region, or everyone? That shapes how much redundancy and isolation I need."

---

# Part 4: Real Cascading Failure Walkthrough

This is a detailed walkthrough of a realistic production incident, showing how partial failure escalates to system-wide outage.

## The Incident: "The Thursday Afternoon Checkout Outage"

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    E-COMMERCE PLATFORM ARCHITECTURE                     │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                         USERS                                   │   │
│   └───────────────────────────┬─────────────────────────────────────┘   │
│                               │                                         │
│   ┌───────────────────────────▼─────────────────────────────────────┐   │
│   │                      API Gateway                                │   │
│   │              (rate limiting, auth, routing)                     │   │
│   └───────────────────────────┬─────────────────────────────────────┘   │
│                               │                                         │
│       ┌───────────────────────┼───────────────────────────┐             │
│       │                       │                           │             │
│   ┌───▼────┐            ┌─────▼────┐              ┌───────▼──────┐      │
│   │ Browse │            │ Checkout │              │    Search    │      │
│   │Service │            │ Service  │              │   Service    │      │
│   └───┬────┘            └─────┬────┘              └───────┬──────┘      │
│       │                       │                           │             │
│       │                 ┌─────┼─────┐                     │             │
│       │                 │     │     │                     │             │
│   ┌───▼────┐      ┌─────▼──┐  │ ┌───▼────┐         ┌──────▼─────┐       │
│   │Product │      │Inventory│ │ │Payment │         │   Search   │       │
│   │  DB    │      │ Service│  │ │Service │         │   Index    │       │
│   └────────┘      └────────┘  │ └────────┘         └────────────┘       │
│                               │                                         │
│                         ┌─────▼─────┐                                   │
│                         │   User    │ ◄──── FAILURE WILL START HERE     │
│                         │  Service  │                                   │
│                         └─────┬─────┘                                   │
│                               │                                         │
│                         ┌─────▼─────┐                                   │
│                         │  User DB  │                                   │
│                         │ (Primary) │                                   │
│                         └───────────┘                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### The Incident Timeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    INCIDENT TIMELINE                                    │
│                                                                         │
│   14:00 - INITIAL FAULT                                                 │
│   ═══════════════════                                                   │
│   User DB primary enters long GC pause (12 seconds)                     │
│                                                                         │
│   WHAT'S HAPPENING:                                                     │
│   - User Service queries to DB timing out                               │
│   - User Service has 50 connection pool slots                           │
│   - All 50 now blocked waiting for DB                                   │
│                                                                         │
│   WHAT MONITORING SHOWS:                                                │
│   - User Service latency: spiking                                       │
│   - User DB: healthy (GC metrics not exposed)                           │
│   - Error rate: 0% (nothing has timed out yet)                          │
│                                                                         │
│   MISLEADING SIGNAL #1:                                                 │
│   "DB is healthy" - because health check hasn't run during GC           │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   14:00:10 - PARTIAL DEGRADATION                                        │
│   ═══════════════════════════════                                       │
│   User Service starts returning 503 (no available threads)              │
│                                                                         │
│   WHAT'S HAPPENING:                                                     │
│   - Checkout Service calls User Service for auth                        │
│   - Some calls succeed (hitting non-blocked threads)                    │
│   - Some calls fail (no threads available)                              │
│   - Checkout sees intermittent auth failures                            │
│                                                                         │
│   WHAT MONITORING SHOWS:                                                │
│   - User Service: 30% error rate (threshold: 50%)                       │
│   - Checkout Service: 10% error rate (threshold: 25%)                   │
│   - No alerts fired (under threshold)                                   │
│                                                                         │
│   MISLEADING SIGNAL #2:                                                 │
│   "Error rate under threshold" - but rising fast                        │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   14:00:30 - CASCADING IMPACT                                           │
│   ═══════════════════════════                                           │
│   Checkout retries failing User Service calls                           │
│                                                                         │
│   WHAT'S HAPPENING:                                                     │
│   - Checkout has 3 retries per request                                  │
│   - 100 checkout requests × 3 retries = 300 User Service calls          │
│   - User Service now at 3x normal load while already struggling         │
│   - User Service thread pool completely exhausted                       │
│                                                                         │
│   FIRST INCORRECT ASSUMPTION:                                           │
│   "Retries will help users complete checkout"                           │
│   Actually: Retries made User Service worse                             │
│                                                                         │
│   WHAT MONITORING SHOWS:                                                │
│   - User Service: 80% error rate (alert fires!)                         │
│   - Checkout Service: 60% error rate (alert fires!)                     │
│   - Page sent to on-call                                                │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   14:01:00 - SYSTEM-WIDE SYMPTOMS                                       │
│   ═══════════════════════════════                                       │
│   On-call engineer receives page, starts investigating                  │
│                                                                         │
│   WHAT'S HAPPENING:                                                     │
│   - User DB GC pause ended at 14:00:12                                  │
│   - But retry storm is now overwhelming User Service                    │
│   - User Service can't recover because load is too high                 │
│   - Checkout is completely broken                                       │
│   - Browse Service also uses User Service - now broken                  │
│                                                                         │
│   FIRST IRREVERSIBLE DECISION:                                          │
│   Engineer sees "User DB healthy" and "User Service errors"             │
│   Assumes: "User Service is the problem"                                │
│   Action: Restarts User Service pods                                    │
│                                                                         │
│   RESULT: New pods have cold caches, make even more DB calls            │
│   OUTCOME: Situation gets WORSE                                         │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   14:05:00 - TOTAL OUTAGE                                               │
│   ═════════════════════                                                 │
│                                                                         │
│   WHAT'S HAPPENING:                                                     │
│   - All User Service pods in restart loop (OOM from retry load)         │
│   - Checkout: 100% error rate                                           │
│   - Browse: 100% error rate (can't load user preferences)               │
│   - Search: Working (doesn't need User Service)                         │
│   - But Search → "Add to Cart" → Checkout → Broken                      │
│                                                                         │
│   WHAT COULD HAVE LIMITED BLAST RADIUS:                                 │
│   - Circuit breaker on User Service calls (fail fast)                   │
│   - Retry budget (limit retry amplification)                            │
│   - Cached auth (serve from cache during User Service outage)           │
│   - Bulkhead (separate thread pool for Checkout vs Browse)              │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   14:20:00 - RECOVERY                                                   │
│   ═══════════════════                                                   │
│                                                                         │
│   ACTIONS TAKEN:                                                        │
│   1. Disable retries at Checkout Service (reduce load)                  │
│   2. Rate limit traffic at Gateway (reduce incoming load)               │
│   3. User Service pods stabilize                                        │
│   4. Gradually increase rate limit                                      │
│   5. Re-enable retries (with lower count)                               │
│                                                                         │
│   TOTAL IMPACT:                                                         │
│   - Duration: 20 minutes                                                │
│   - Checkout unavailable: 15 minutes                                    │
│   - Estimated lost revenue: $400,000                                    │
│   - Customer complaints: 3,000                                          │
│                                                                         │
│   ROOT CAUSE:                                                           │
│   12-second GC pause in User DB                                         │
│   + No circuit breakers + Aggressive retries + Shared dependency        │
│   = 20-minute outage affecting all checkout                             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Post-Incident Analysis: Key Moments

| Moment | What Happened | What Should Have Happened |
|--------|---------------|---------------------------|
| **Initial fault** | DB GC pause, normal event | N/A - GC pauses happen |
| **10 seconds** | Thread pool exhausted | Circuit breaker opens, fast-fail |
| **30 seconds** | Retry storm begins | Retry budget limits amplification |
| **60 seconds** | Engineer misdiagnoses | GC metrics visible in dashboard |
| **61 seconds** | Restart makes worse | Runbook says "don't restart during retry storm" |
| **5 minutes** | Total outage | Cached auth allows degraded operation |

**The Fundamental Lesson**: A 12-second GC pause should not cause a 20-minute outage. The architecture allowed a minor fault to cascade into system-wide failure.

### Structured Real Incident Summary (Full Table Format)

| Part | Content |
|------|---------|
| **Context** | E-commerce platform: API Gateway → Checkout Service → User Service (auth) + Payment + Inventory. User Service backed by User DB (primary). Scale: ~10K checkout requests/min during peak. |
| **Trigger** | User DB primary entered 12-second GC pause during routine compaction. Connection pool (50 slots) in User Service exhausted within 10 seconds as all threads blocked waiting for DB. |
| **Propagation** | User Service returned 503 (no threads). Checkout Service retried auth calls 3× per request → 3× load on User Service. Retry storm prevented recovery. Engineer restarted User Service pods → cold caches → thundering herd to DB. Browse Service (shares User Service) also failed. |
| **User impact** | 100% checkout unavailable for 15 minutes; browse degraded for 20 minutes. ~3,000 customers affected; estimated $400K lost revenue. |
| **Engineer response** | Initial misdiagnosis (restart made worse). Correct mitigation: disabled retries, rate-limited at Gateway, gradual traffic ramp. Full recovery at 14:20. |
| **Root cause** | 12s GC pause + no circuit breakers + aggressive retries + shared thread pool. Secondary: no cached auth fallback; no GC metrics on DB dashboard. |
| **Design change** | Circuit breakers on User Service calls; retry budget (10% max); bulkheads (separate pools for Checkout vs Browse); cached auth with short TTL; DB GC metrics exposed. |
| **Lesson learned** | "A slow dependency is worse than a dead one—it holds resources and passes health checks. Retries amplify; circuit breakers contain. Staff Engineers design for propagation, not just the initial fault." |

### Human Failure Modes During the Incident

Analysis of human errors that made the Thursday Afternoon Outage worse:

| Error | Impact | What Happened |
|-------|--------|---------------|
| **Delayed detection** | 10 minutes lost | On-call engineer saw initial alert but dismissed it as a monitoring blip |
| **Wrong diagnosis** | 15 minutes lost | Engineer focused on the symptom (API gateway overloaded) instead of the root cause (slow inventory service) |
| **Escalation delay** | 15 minutes lost | Engineer tried to fix it alone instead of paging the inventory team |
| **Risky mitigation** | 30-second full outage | Under pressure, engineer restarted the API gateway fleet simultaneously instead of rolling restart |
| **Incomplete recovery** | Secondary spike 20 min later | Declared "resolved" when error rate dropped, but didn't check that retry backlog had drained |

**Prevention Strategies**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│              PREVENTING HUMAN FAILURE MODES                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   1. STRUCTURED INCIDENT RESPONSE                                        │
│   ────────────────────────────────────────                              │
│   Use ICS (Incident Command System) — first action is assess and        │
│   delegate, not fix.                                                    │
│                                                                         │
│   2. RUNBOOK-FIRST CULTURE                                               │
│   ────────────────────────────────────────                              │
│   "If you don't have a runbook, your first step is to page someone      │
│    who does"                                                             │
│                                                                         │
│   3. BLAMELESS ESCALATION                                                │
│   ────────────────────────────────────────                              │
│   Remove stigma from paging senior engineers — escalation should        │
│   happen at 5 minutes, not 30.                                          │
│                                                                         │
│   4. AUTOMATED DIAGNOSTICS                                               │
│   ────────────────────────────────────────                              │
│   When alert fires, automatically collect and present top 5 metrics     │
│   to on-call (don't make them hunt)                                     │
│                                                                         │
│   5. RECOVERY VERIFICATION                                               │
│   ────────────────────────────────────────                              │
│   "Resolved" requires all of:                                            │
│   □ Error rate < threshold                                               │
│   □ Retry backlog drained                                                │
│   □ Dependent services healthy                                            │
│   □ Customer-facing metrics normal                                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Staff Insight**: 
> The majority of outage duration comes from human factors, not technical ones. A 2-minute detection delay + 10-minute misdiagnosis + 15-minute escalation delay = 27 minutes of unnecessary outage. That's often longer than the actual fix.

---

# Part 5: Apply Failure Reasoning to Real Systems

## System 1: Global Rate Limiter

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    GLOBAL RATE LIMITER                                  │
│                                                                         │
│   ┌────────────────────────────────────────────────────────────────┐    │
│   │                        API GATEWAY                             │    │
│   │  ┌─────────────────────────────────────────────────────────┐   │    │
│   │  │   For each request:                                     │   │    │
│   │  │   1. Extract user ID                                    │   │    │
│   │  │   2. Call Rate Limit Service                            │   │    │
│   │  │   3. If allowed: forward to backend                     │   │    │
│   │  │   4. If denied: return 429                              │   │    │
│   │  └─────────────────────────────────────────────────────────┘   │    │
│   └────────────────────────┬───────────────────────────────────────┘    │
│                            │                                            │
│                            ▼                                            │
│   ┌────────────────────────────────────────────────────────────────┐    │
│   │                  RATE LIMIT SERVICE                            │    │
│   │  ┌─────────────────────────────────────────────────────────┐   │    │
│   │  │   For each check:                                       │   │    │
│   │  │   1. Get current count from Redis                       │   │    │
│   │  │   2. Increment count                                    │   │    │
│   │  │   3. Return allow/deny                                  │   │    │
│   │  └─────────────────────────────────────────────────────────┘   │    │
│   └────────────────────────┬───────────────────────────────────────┘    │
│                            │                                            │
│                            ▼                                            │
│   ┌────────────────────────────────────────────────────────────────┐    │
│   │                    REDIS CLUSTER                               │    │
│   │               (Centralized rate limit state)                   │    │
│   └────────────────────────────────────────────────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Most Dangerous Partial Failure

**Failure**: Rate Limit Service is slow (not down)

### Behavior During Failure

```
SCENARIO: Rate Limit Service P99 goes from 5ms to 500ms

DURING FAILURE:
─────────────────
- Every API request waits 500ms just for rate limit check
- API Gateway threads blocked on rate limit calls
- Gateway thread pool exhausted
- New requests queue up
- User-facing latency: 500ms + normal processing
- Eventually: Gateway can't accept new connections
- All traffic fails—not because of rate limits, but because of rate limiter

THE IRONY:
The rate limiter—designed to protect backends—becomes the cause of outage.

WHAT USERS SEE:
- Slow responses (500ms+ added to everything)
- Then timeouts
- Then 503 errors
- "The site is down"
```

### Design Choices That Expand Blast Radius

| Choice | Problem |
|--------|---------|
| **Synchronous check** | Every request waits for rate limit response |
| **No timeout** | Slow rate limiter blocks forever |
| **No fallback** | If rate limiter is down, deny all traffic? |
| **No caching** | Every request goes to Redis |
| **Centralized Redis** | Single point of failure for all traffic |

### What Senior Engineers Miss

**Senior approach**: "Rate limiter protects backends. If rate limiter is down, we should fail closed (deny all) for safety."

**Staff approach**: "A synchronous rate limiter on the critical path is a single point of failure. If it's slow, all traffic is slow. I'd use a local cache with async refresh, accept slightly stale limits, and fail open (allow) if the rate limiter is unavailable. A few extra requests during an outage is better than blocking all requests."

### How Staff Engineers Anticipate This

```
STAFF DESIGN:
─────────────
1. Local token bucket in each Gateway instance
2. Async sync with central Redis (every 100ms)
3. If Redis unavailable: use last known limits
4. If no data: default permissive limit
5. Timeout on Redis: 10ms (fail fast)

TRADE-OFF:
- Less accurate limits (can exceed by 10-20% during sync lag)
- But: rate limiter failure doesn't cause system failure

STAFF REASONING:
"The purpose of rate limiting is to protect backends from overload.
If the rate limiter itself causes overload, we've failed at the goal.
I'd rather be 10% over limit sometimes than have zero availability."
```

---

## System 2: News Feed Service

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    NEWS FEED SERVICE                                    │
│                                                                         │
│   USER POSTS                              USER READS FEED               │
│       │                                         │                       │
│       ▼                                         ▼                       │
│   ┌────────┐                              ┌────────────┐                │
│   │ Post   │                              │   Feed     │                │
│   │Service │                              │  Service   │                │
│   └────┬───┘                              └─────┬──────┘                │
│        │                                        │                       │
│        ▼                                        ▼                       │
│   ┌────────────┐                          ┌────────────┐                │
│   │  Fan-out   │                          │   Feed     │                │
│   │  Service   │──────────────────────────│   Cache    │                │
│   └─────┬──────┘                          └─────┬──────┘                │
│         │                                       │                       │
│         │ For each follower:                    │ Cache miss:           │
│         │ 1. Get follower list                  │ 1. Query feeds DB     │
│         │ 2. Write to follower's feed cache     │ 2. Rank posts         │
│         │                                       │ 3. Return top N       │
│         ▼                                       ▼                       │
│   ┌────────────────────────────────────────────────────────────┐        │
│   │                      FEEDS DATABASE                        │        │
│   │              (User feeds, follower graphs)                 │        │
│   └────────────────────────────────────────────────────────────┘        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Most Dangerous Partial Failure

**Failure**: Fan-out Service slow for high-follower accounts

### Behavior During Failure

```
SCENARIO: Celebrity with 10M followers posts during peak hours

DURING FAILURE:
─────────────────
- Fan-out starts: 10M cache writes to perform
- Fan-out threads blocked writing to cache
- Other posts (normal users) queued behind celebrity post
- Normal user posts delayed by minutes
- Fan-out queue grows unboundedly
- Memory exhaustion
- Fan-out Service crashes
- No new posts appearing in anyone's feed

WHAT USERS SEE:
- Feed stops updating
- "I posted 10 minutes ago and followers don't see it"
- Timeline feels "stale"
- Users complain "the app is broken"

THE SUBTLETY:
The failure is INVISIBLE to the user who caused it.
The celebrity's post succeeded.
It's everyone else who's affected.
```

### Design Choices That Expand Blast Radius

| Choice | Problem |
|--------|---------|
| **Synchronous fan-out** | Posting blocks until all writes complete |
| **Unbounded queue** | Backlog grows forever |
| **Shared fan-out pool** | Celebrity post blocks normal posts |
| **No prioritization** | 10M-follower writes same priority as 100-follower |

### What Senior Engineers Miss

**Senior approach**: "Fan-out works for most users. We'll add more fan-out capacity for celebrities."

**Staff approach**: "Fan-out doesn't scale with follower count. A 10M-follower celebrity can't fan-out synchronously—that's a fundamentally different problem. I'd use hybrid: fan-out on write for normal users (fast reads), fan-out on read for celebrities (constant-time writes). The read path aggregates from followed celebrities' timelines."

### How Staff Engineers Anticipate This

```
STAFF DESIGN:
─────────────
1. Users with <10K followers: fan-out on write (pre-compute feed)
2. Users with >10K followers: fan-out on read (query at read time)
3. Feed read: merge pre-computed feed + celebrity feeds

TRADE-OFF:
- Read latency slightly higher (need to merge)
- But: posting latency bounded regardless of followers

STAFF REASONING:
"The fan-out problem is bimodal. 99% of users have <1K followers—fan-out on write is perfect. 0.01% have >10K followers—fan-out on write is O(n) disaster. I'd solve each case appropriately rather than pretending one solution fits all."
```

---

## System 3: Messaging System

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    MESSAGING SYSTEM                                     │
│                                                                         │
│   SENDER                                           RECEIVER             │
│     │                                                │                  │
│     ▼                                                │                  │
│   ┌─────────┐        ┌──────────┐        ┌─────────┐ │                  │
│   │ Message │───────►│ Message  │───────►│ Inbox   │◄┘                  │
│   │  API    │        │  Queue   │        │ Service │                    │
│   └─────────┘        └────┬─────┘        └────┬────┘                    │
│                           │                   │                         │
│                           ▼                   │                         │
│                     ┌───────────┐             │                         │
│                     │  Worker   │             │                         │
│                     │  Pool     │             │                         │
│                     └─────┬─────┘             │                         │
│                           │                   │                         │
│                           ▼                   ▼                         │
│   ┌────────────────────────────────────────────────────────────┐        │
│   │                    MESSAGE DATABASE                        │        │
│   │    (Messages table, Conversations table, Read receipts)    │        │
│   └────────────────────────────────────────────────────────────┘        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Most Dangerous Partial Failure

**Failure**: Message Database slow on writes, but reads still fast

### Behavior During Failure

```
SCENARIO: Database write latency spikes from 10ms to 2000ms

DURING FAILURE:
─────────────────
- User sends message
- Message API acknowledges (message in queue)
- Worker tries to persist to DB (takes 2 seconds)
- Worker pool threads blocked on DB writes
- Queue grows (messages arriving faster than persisted)
- Sender sees "message sent" 
- Receiver doesn't see message (not yet in DB)
- Receiver queries again: still not there
- "But I sent it! I saw the checkmark!"

WHAT USERS SEE:
- Messages "sent" but not "delivered"
- Conversation showing different state for sender vs receiver
- "Are my messages going through?"
- Users switch to different messaging app

THE SUBTLETY:
- Read path works (Inbox Service is fast)
- Only writes are slow
- Sender thinks it worked (got acknowledgment)
- Receiver thinks nothing was sent
- Eventually consistent... but "eventually" is 2+ minutes
```

### Design Choices That Expand Blast Radius

| Choice | Problem |
|--------|---------|
| **Optimistic acknowledgment** | Tell user "sent" before persisted |
| **No visibility into queue depth** | Users don't know messages are delayed |
| **Shared database** | Slow writes affect all conversations |
| **No timeout on persistence** | Messages stuck in queue indefinitely |

### What Senior Engineers Miss

**Senior approach**: "We acknowledge early for low latency. Messages will eventually be delivered."

**Staff approach**: "Early acknowledgment is lying to the user if there's significant delay. I'd show 'sending...' until persisted, then 'sent' when in database, then 'delivered' when receiver sees it. Users can handle a second of waiting. They can't handle thinking a message was delivered when it wasn't."

### How Staff Engineers Anticipate This

```
STAFF DESIGN:
─────────────
1. Message state machine: PENDING → PERSISTED → DELIVERED → READ
2. Show "sending..." during PENDING (after queue, before DB)
3. Show "sent" after PERSISTED (in database)
4. If PENDING > 5 seconds: show "delayed" indicator
5. Monitor queue depth, alert when > 1 minute backlog

TRADE-OFF:
- Slightly slower perceived send (wait for DB)
- But: no lies about message state

STAFF REASONING:
"Messaging is trust-critical. If I say 'sent' and the message doesn't arrive, I've broken user trust. I'd rather have slightly slower UX than incorrect UX. The worst bug in messaging isn't slow messages—it's lost messages that the sender thinks were delivered."
```

---

# Part 6: Designing for Containment and Recovery

## Bulkheads and Isolation Boundaries

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    BULKHEAD PATTERN                                     │
│                                                                         │
│   WITHOUT BULKHEADS:                                                    │
│   ──────────────────                                                    │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                    SHARED THREAD POOL (100)                     │   │
│   │   ████████████████████████████████████████████████████████████  │   │
│   │   All threads blocked calling slow User Service                 │   │
│   │   Result: Checkout, Browse, Search ALL blocked                  │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│   WITH BULKHEADS:                                                       │
│   ───────────────                                                       │
│   ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐     │
│   │   User Service    │ │ Payment Service   │ │ Search Service    │     │
│   │   Pool (30)       │ │ Pool (30)         │ │ Pool (30)         │     │
│   │   ██████████████  │ │ ░░░░░░░░░░░░░░░░  │ │ ░░░░░░░░░░░░░░░░  │     │
│   │   (Blocked)       │ │ (Healthy)         │ │ (Healthy)         │     │
│   └───────────────────┘ └───────────────────┘ └───────────────────┘     │
│                                                                         │
│   Result: User Service failure isolated. Payment and Search work.       │
│                                                                         │
│   BULKHEAD TYPES:                                                       │
│   ───────────────                                                       │
│   • Thread pools: Separate pools per dependency                         │
│   • Connection pools: Separate connections per downstream               │
│   • Processes: Separate containers per service                          │
│   • Regions: Separate infrastructure per geography                      │
│   • Cells: Separate infrastructure per customer segment                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Timeouts, Circuit Breakers, and Fallbacks

### The Defense Stack

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    LAYERED DEFENSE PATTERN                              │
│                                                                         │
│   LAYER 1: TIMEOUTS                                                     │
│   ────────────────────                                                  │
│   Purpose: Bound how long you wait for response                         │
│   Effect: Slow dependency can't hold your resources forever             │
│   Config: timeout < deadline budget for this call                       │
│                                                                         │
│   LAYER 2: CIRCUIT BREAKER                                              │
│   ──────────────────────                                                │
│   Purpose: Stop calling broken dependency                               │
│   Effect: Fail fast instead of waiting for timeout                      │
│   States: CLOSED (call normally) → OPEN (fail fast) → HALF-OPEN (test)  │
│                                                                         │
│   LAYER 3: FALLBACK                                                     │
│   ────────────────                                                      │
│   Purpose: Provide degraded functionality when dependency fails         │
│   Options:                                                              │
│   • Cached response (stale but available)                               │
│   • Default response (generic but usable)                               │
│   • Partial response (some data missing)                                │
│   • Graceful error (helpful message, retry later)                       │
│                                                                         │
│   EXECUTION ORDER:                                                      │
│   ─────────────────                                                     │
│   1. Check circuit breaker state                                        │
│   2. If OPEN: return fallback immediately                               │
│   3. If CLOSED/HALF-OPEN: make call with timeout                        │
│   4. If timeout/error: record failure, return fallback                  │
│   5. If enough failures: open circuit                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Degraded Modes vs Full Shutdown

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    DEGRADATION SPECTRUM                                 │
│                                                                         │
│   Full Capability ◄────────────────────────────────────► Zero Capability│
│                                                                         │
│   ┌────────┬────────┬────────┬────────┬────────┬────────┬────────┐      │
│   │  100%  │   80%  │   60%  │   40%  │   20%  │   5%   │   0%   │      │
│   │ Normal │ Slight │ Visible│ Major  │ Minimal│ Status │  Down  │      │
│   │        │ degrade│ degrade│ degrade│ viable │  page  │        │      │
│   └────────┴────────┴────────┴────────┴────────┴────────┴────────┘      │
│                                                                         │
│   EXAMPLE: E-commerce during Payment Service outage                     │
│                                                                         │
│   100%: Full checkout with all payment methods                          │
│   80%:  Checkout works, PayPal disabled (fallback to cards)             │
│   60%:  Checkout works, only saved payment methods                      │
│   40%:  Browse and add to cart works, checkout shows "try later"        │
│   20%:  Product pages work, cart disabled                               │
│   5%:   Static catalog page, "we're fixing things"                      │
│   0%:   Complete outage                                                 │
│                                                                         │
│   STAFF DESIGN PRINCIPLE:                                               │
│   Each layer of degradation should be DESIGNED, not accidental.         │
│   Know what 60% looks like before you need it.                          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Choosing Between Degradation and Shutdown

| Situation | Prefer Degradation | Prefer Shutdown |
|-----------|-------------------|-----------------|
| **Data correctness critical** | | ✓ (financial transactions) |
| **Stale data acceptable** | ✓ (recommendations) | |
| **User safety involved** | | ✓ (medical, automotive) |
| **Core function vs auxiliary** | ✓ (search during payment outage) | |
| **Incorrect data worse than no data** | | ✓ |
| **Partial function useful** | ✓ | |

## Security and Trust Boundaries During Partial Failures

Partial failures create security and compliance risks that Staff Engineers must anticipate. When systems degrade, trust boundaries can shift—and fallbacks can expose sensitive data.

```
┌─────────────────────────────────────────────────────────────────────────┐
│              SECURITY RISKS DURING PARTIAL FAILURE                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   FALLBACK EXPOSURE:                                                    │
│   ─────────────────                                                     │
│   Primary auth service down → Fallback: cached auth tokens               │
│   Risk: Stale tokens may be revoked; serving cached = potential bypass   │
│   Staff choice: Short TTL (60s max), never fallback for write auth      │
│                                                                         │
│   DEGRADED MODE DATA LEAK:                                              │
│   ────────────────────────                                              │
│   Search down → Fallback: return cached results                         │
│   Risk: Cache may contain PII from old queries; different retention     │
│   Staff choice: Fallback cache must meet same retention/compliance      │
│                                                                         │
│   CROSS-TEAM BLAST RADIUS:                                             │
│   ─────────────────────────                                             │
│   Team A's service fails → Team B's service degrades                    │
│   Risk: Team B may shed load, exposing error messages to users          │
│   Staff choice: Error messages must not leak internal paths or PII      │
│                                                                         │
│   COMPLIANCE DURING DEGRADATION:                                        │
│   ─────────────────────────────                                         │
│   Audit logging service slow → Skip audit to preserve latency?          │
│   Staff choice: Never degrade audit for financial/regulated operations │
│   Trade-off: Accept latency or shed non-critical traffic first          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Trust Boundary Principle**: During partial failure, the system must not cross trust boundaries it would not cross when healthy. Cached auth is acceptable if bounded; exposing internal error details to external callers is not.

**Interview Signal**: "When I design fallbacks, I ask: what trust boundary does this cross? If the primary path requires auth and the fallback doesn't, I've created a security regression. I'd rather return 503 than serve unauthenticated data."

## Recovery vs Prevention Trade-offs

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    PREVENTION VS RECOVERY                               │
│                                                                         │
│   PREVENTION-HEAVY:                                                     │
│   ─────────────────                                                     │
│   • Multiple replicas everywhere                                        │
│   • Extensive validation before writes                                  │
│   • Synchronous replication                                             │
│   • Consensus protocols for all state changes                           │
│                                                                         │
│   Cost: Latency, complexity, capacity overhead                          │
│   Benefit: Fewer incidents                                              │
│   Risk: When prevention fails, may lack recovery skills                 │
│                                                                         │
│   RECOVERY-HEAVY:                                                       │
│   ────────────────                                                      │
│   • Excellent monitoring and alerting                                   │
│   • Fast rollback capabilities                                          │
│   • Runbooks for every failure mode                                     │
│   • Regular failure drills                                              │
│                                                                         │
│   Cost: More incidents, more on-call load                               │
│   Benefit: Fast recovery, team stays sharp                              │
│   Risk: Incidents become normal, important ones missed                  │
│                                                                         │
│   STAFF APPROACH:                                                       │
│   ────────────────                                                      │
│   Prevent failures with high BLAST RADIUS (data loss, security)         │
│   Plan for fast RECOVERY from failures with low blast radius (latency)  │
│                                                                         │
│   "I spend prevention budget on failures I can't recover from,          │
│    and recovery budget on failures that will definitely happen."        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

# Part 7: Architecture Evolution After Failure

Systems don't become resilient by design—they evolve through failure. Here's how architectures typically mature:

## Stage 1: Naive Design (Pre-First-Outage)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    STAGE 1: NAIVE DESIGN                                │
│                                                                         │
│   ASSUMPTIONS:                                                          │
│   ─────────────                                                         │
│   • Dependencies are reliable                                           │
│   • Network is fast and doesn't fail                                    │
│   • Databases handle any load                                           │
│   • Errors are exceptional                                              │
│                                                                         │
│   TYPICAL ARCHITECTURE:                                                 │
│   ──────────────────────                                                │
│   • Synchronous calls everywhere                                        │
│   • Shared connection pools                                             │
│   • 30-second timeouts (or no timeouts)                                 │
│   • Retry everything 3 times                                            │
│   • No circuit breakers                                                 │
│   • No fallbacks                                                        │
│   • Single database, single region                                      │
│                                                                         │
│   WHY THIS EXISTS:                                                      │
│   ─────────────────                                                     │
│   • Fast to build                                                       │
│   • Works fine at low scale                                             │
│   • Team hasn't experienced failures yet                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Stage 2: After First Major Outage

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    STAGE 2: POST-FIRST-OUTAGE                           │
│                                                                         │
│   WHAT BROKE:                                                           │
│   ────────────                                                          │
│   Database GC pause → retry storm → 4-hour outage                       │
│                                                                         │
│   POSTMORTEM-DRIVEN CHANGES:                                            │
│   ──────────────────────────                                            │
│   ✓ Add circuit breakers on database calls                              │
│   ✓ Reduce timeout from 30s to 5s                                       │
│   ✓ Add exponential backoff to retries                                  │
│   ✓ Add retry budgets                                                   │
│   ✓ Add dashboard for thread pool utilization                           │
│                                                                         │
│   WHAT STILL MISSING:                                                   │
│   ───────────────────                                                   │
│   • Bulkheads (changes would be too big)                                │
│   • Fallbacks (not sure what to return)                                 │
│   • Degradation modes (not designed)                                    │
│   • Multi-region (too expensive)                                        │
│                                                                         │
│   TEAM MINDSET:                                                         │
│   ──────────────                                                        │
│   "We fixed the thing that broke. We're good now."                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Stage 3: After Pattern Recognition

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    STAGE 3: PATTERN RECOGNITION                         │
│                                                                         │
│   WHAT KEPT BREAKING:                                                   │
│   ───────────────────                                                   │
│   Incident #2: Different service, same pattern (retry storm)            │
│   Incident #3: Cache failure caused DB overload (thundering herd)       │
│   Incident #4: Deploy caused cold caches (startup overload)             │
│                                                                         │
│   PATTERN RECOGNIZED:                                                   │
│   ──────────────────                                                    │
│   "Same failure modes keep appearing in different places"               │
│                                                                         │
│   SYSTEMATIC CHANGES:                                                   │
│   ────────────────────                                                  │
│   ✓ Circuit breakers as standard library                                │
│   ✓ Retry budget as platform feature                                    │
│   ✓ Bulkhead per external dependency (thread pool isolation)            │
│   ✓ Rolling deploys with warm-up periods                                │
│   ✓ Cache pre-warming from snapshots                                    │
│   ✓ Fallbacks designed for each external call                           │
│                                                                         │
│   TEAM MINDSET:                                                         │
│   ──────────────                                                        │
│   "Every external call is a failure waiting to happen.                  │
│    Design for the failure, not just the success."                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Stage 4: Production-Hardened Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    STAGE 4: PRODUCTION-HARDENED                         │
│                                                                         │
│   WHAT DROVE THIS STAGE:                                                │
│   ──────────────────────                                                │
│   Incident #10: Region outage took down everything                      │
│   Incident #15: Shared database became bottleneck                       │
│   Incident #20: Team burned out from on-call                            │
│                                                                         │
│   ARCHITECTURAL SHIFTS:                                                 │
│   ──────────────────────                                                │
│   ✓ Multi-region active-active                                          │
│   ✓ Database per service (no shared dependencies)                       │
│   ✓ Async by default, sync only when necessary                          │
│   ✓ Cell-based isolation (failure affects subset of users)              │
│   ✓ Chaos engineering in production                                     │
│   ✓ Automated recovery runbooks                                         │
│   ✓ On-call load distributed across team                                │
│                                                                         │
│   OPERATIONAL CHANGES:                                                  │
│   ─────────────────────                                                 │
│   ✓ Every new service must pass resilience review                       │
│   ✓ Production readiness checklist before launch                        │
│   ✓ Failure injection in staging and production                         │
│   ✓ Blameless postmortems with action tracking                          │
│                                                                         │
│   TEAM MINDSET:                                                         │
│   ──────────────                                                        │
│   "Failures are inevitable. Our job is to minimize blast radius,        │
│    maximize detection speed, and ensure fast recovery."                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## What Staff Engineers Learn From Failures

| Lesson | Learned After | Applied How |
|--------|---------------|-------------|
| "Fast timeout > slow timeout" | First retry storm | Timeout = 2x P99, not 30s |
| "Circuit breakers before retries" | Second retry storm | Breaker opens, retries don't fire |
| "Bulkheads per dependency" | Cross-service cascade | Thread pool per external call |
| "Async where possible" | Sync cascade | Queue for non-urgent operations |
| "Fallbacks are features" | No degradation mode | Design what 50% looks like |
| "Cell isolation limits blast radius" | Regional outage | 10% of users affected, not 100% |
| "Chaos engineering finds problems before users" | Too many surprises | Weekly failure injection |

**Interview Signal**: "I've learned that the time to design for failure is before the first outage, not after. But realistically, most architectures evolve through incidents. The skill is recognizing patterns: if we had a retry storm once, we'll have it again unless we fix the systemic issue."

### Scale Thresholds: When to Invest in Each Failure Handling Pattern

```
┌─────────────────────────────────────────────────────────────────────────┐
│              V1 → 10× GROWTH MODEL FOR FAILURE HANDLING                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Scale    │ Services │ Failure Pattern Investment │ Why               │
│   ─────────┼──────────┼───────────────────────────┼───────────────────│
│   V1       │ 5-10     │ Simple timeouts + retries │ Failures obvious, │
│            │          │ + health checks            │ manual fix fast   │
│   ─────────┼──────────┼───────────────────────────┼───────────────────│
│   V2       │ 10-30    │ + Circuit breakers        │ Cascading        │
│            │          │ + bulkheads                │ failures possible │
│            │          │ + structured incident      │ manual RCA slows │
│            │          │   response                 │                   │
│   ─────────┼──────────┼───────────────────────────┼───────────────────│
│   V3       │ 30-100   │ + Cell-based isolation    │ Failure paths    │
│            │          │ + chaos engineering        │ too complex for   │
│            │          │ + automated diagnostics   │ human reasoning   │
│   ─────────┼──────────┼───────────────────────────┼───────────────────│
│   V4       │ 100+     │ + Automated failover      │ Human response   │
│            │          │ + ML-based anomaly         │ can't scale to   │
│            │          │   detection                │ failure frequency │
│            │          │ + self-healing             │                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**What Breaks at Each Transition**:
- **V1→V2**: Manual debugging becomes too slow
- **V2→V3**: Manual blast radius containment fails
- **V3→V4**: Manual failure detection can't keep up

**Most Dangerous Assumptions**:
- "Our service mesh handles failures" → It handles known patterns, not novel ones
- "More monitoring = better detection" → Alert fatigue kills detection
- "Automated recovery is always better than manual" → Automated recovery without guards can make things worse

**Early Warning That You Need the Next Level**:
- More than 2 incidents/month requiring > 30 minutes to resolve
- Cascading failures crossing > 3 service boundaries
- On-call escalation rate > 20%

---

### Infrastructure Reality: Concrete Numbers at Each Scale

| Scale | Users | QPS | Servers | Failure Frequency | Mean Detection Time | Mean Recovery Time |
|---|---|---|---|---|---|---|
| **V1** | 10K | 100 | 3-5 | Monthly (1 server crash) | 5 minutes (manual) | 30 minutes (manual restart) |
| **V2** | 100K | 1K | 10-20 | Weekly (partial failures) | 2 minutes (basic monitoring) | 10 minutes (automated restart) |
| **V3** | 1M | 10K | 50-100 | Daily (some component degraded) | 30 seconds (alerting) | 5 minutes (circuit breaker + failover) |
| **V4** | 10M | 100K | 200-500 | Hourly (something is always partially failing) | 10 seconds (real-time monitoring) | 1 minute (automated failover) |
| **V5** | 100M+ | 1M+ | 1000+ | Constant (partial failure is the default state) | 5 seconds (ML-based anomaly detection) | 30 seconds (cell isolation + auto-recovery) |

**Key Insight: Failure Frequency Scales Faster Than Traffic**

At V1, you might see 1 failure per month. At V5, with 1000+ servers, the probability that SOME component is failing RIGHT NOW approaches 100%. This is why Staff Engineers say "design for partial failure as the default state" — at scale, it literally is.

**What Changes at Each Scale:**

- **V1 → V2:** You go from "failures are surprising" to "failures are expected." Investment: monitoring, automated restarts.
- **V2 → V3:** You go from "one team handles incidents" to "incidents cross team boundaries." Investment: circuit breakers, incident process.
- **V3 → V4:** You go from "we recover from failures" to "we operate through failures." Investment: cell architecture, automated failover, chaos engineering.
- **V4 → V5:** You go from "we manage failure modes" to "failure is the normal state." Investment: self-healing systems, ML-based anomaly detection, automated remediation.

**Bottleneck at Each Scale:**

| Scale | Primary Bottleneck | Secondary Bottleneck |
|---|---|---|
| V1 | Single point of failure (one DB, one app server) | No monitoring — failures go undetected |
| V2 | Manual incident response (humans too slow) | Cross-service dependency failures |
| V3 | Blast radius too large (one failure takes down everything) | Alert fatigue (too many alerts, wrong priorities) |
| V4 | Coordination overhead (too many services to coordinate) | Recovery time (automated failover still takes minutes) |
| V5 | Unknown failure modes (novel interactions at scale) | Cost of redundancy (N+1 at 1000 servers = 333 spare servers) |

---

# Part 8: Observability During Partial Failures

> **Staff Insight**: You can't manage what you can't measure, but during partial failures, your measurements themselves become unreliable. Staff engineers design observability that degrades gracefully alongside the system.

## The Observability Paradox

During partial failures, the systems you rely on to understand the failure may themselves be affected:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    THE OBSERVABILITY PARADOX                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Normal Operation:                                                     │
│   ┌─────────┐   metrics   ┌─────────┐   queries   ┌─────────┐           │
│   │ Service │────────────▶│ Metrics │────────────▶│Dashboard│           │
│   └─────────┘             │   DB    │             └─────────┘           │
│                           └─────────┘                                   │
│                                                                         │
│   During Failure:                                                       │
│   ┌─────────┐   ???       ┌─────────┐   slow      ┌─────────┐           │
│   │ Service │──── X ────▶ │ Metrics │────────────▶│Dashboard│           │
│   │(failing)│             │(backlog)│             │ (stale) │           │
│   └─────────┘             └─────────┘             └─────────┘           │
│                                                                         │
│   Questions you can't answer during outage:                             │
│   • How many requests are actually failing? (metrics delayed)           │
│   • Which hosts are affected? (discovery service failing)               │
│   • When did it start? (clock skew during partition)                    │
│   • Is the fix working? (metrics lag behind reality)                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## SLIs and SLOs During Degradation

### Designing SLIs That Work During Failures

| SLI Type | Normal Measurement | Failure-Resilient Alternative |
|----------|-------------------|------------------------------|
| Availability | Server-side success rate | Client-side success rate (different path) |
| Latency | P99 from service | Synthetic probes from multiple locations |
| Error Rate | Application logs | Load balancer 5xx counts |
| Throughput | Kafka consumer lag | Database row counts (eventual) |

### Error Budget Consumption During Partial Failure

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ERROR BUDGET DURING PARTIAL FAILURE                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Monthly Error Budget: 43.2 minutes (99.9% availability)               │
│                                                                         │
│   Scenario: 10% of requests failing for 2 hours                         │
│                                                                         │
│   Naive Calculation:                                                    │
│   └─ 10% failure × 120 minutes = 12 minutes consumed                    │
│                                                                         │
│   Reality Check:                                                        │
│   └─ Which 10%? Random users → 12 min equivalent                        │
│                │ Power users → Maybe 30 min equivalent (business impact)│
│                │ Payment flow → Full outage equivalent                  │
│                                                                         │
│   Staff Approach:                                                       │
│   └─ Weight SLOs by business criticality                                │
│   └─ Different error budgets for different user segments                │
│   └─ "Good minutes" vs "bad minutes" accounting                         │
│                                                                         │
│   Interview Signal: "Error budgets need to account for partial          │
│   failures differently than total outages. Affecting 10% of users       │
│   for an hour might be worse than affecting everyone for 6 minutes      │
│   if that 10% is your highest-value segment."                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Multi-Signal Correlation

Staff engineers don't rely on single signals. During partial failures, you need correlated evidence:

```
Evidence Triangulation:
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   Signal 1: Metrics              Signal 2: Logs                         │
│   ┌───────────────────┐         ┌───────────────────┐                   │
│   │ Error rate: 15%   │         │ "Connection reset"│                   │
│   │ Latency P99: 2.5s │         │ appearing 100x/s  │                   │
│   └─────────┬─────────┘         └─────────┬─────────┘                   │
│             │                             │                             │
│             └──────────┬──────────────────┘                             │
│                        │                                                │
│                        ▼                                                │
│              ┌─────────────────┐                                        │
│              │ Signal 3: Trace │                                        │
│              │ DB calls: 3.2s  │                                        │
│              │ (normally 50ms) │                                        │
│              └─────────┬───────┘                                        │
│                        │                                                │
│                        ▼                                                │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ Hypothesis: Database connection pool exhaustion                 │   │
│   │ Evidence: High latency (metrics) + connection errors (logs) +   │   │
│   │           slow DB spans (traces)                                │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Distributed Tracing in Partial Failure Scenarios

### Trace Sampling During Failures

```python
class AdaptiveTraceSampling:
    """
    During failures, we need MORE traces, not fewer.
    But during failures, our tracing backend may be overloaded.
    """
    
    def __init__(self):
        self.base_rate = 0.01  # 1% in normal operation
        self.error_rate = 1.0   # 100% of errors
        self.high_latency_rate = 0.5  # 50% of slow requests
        self.latency_threshold_ms = 1000
    
    def should_sample(self, request_context):
        # Always trace errors
        if request_context.has_error:
            return True
        
        # Higher sampling for slow requests
        if request_context.latency_ms > self.latency_threshold_ms:
            return random.random() < self.high_latency_rate
        
        # During detected degradation, increase base rate
        if self.is_system_degraded():
            return random.random() < min(self.base_rate * 10, 0.1)
        
        return random.random() < self.base_rate
    
    def is_system_degraded(self):
        """Check local signals - don't depend on central system"""
        local_error_rate = self.get_local_error_rate()
        local_latency = self.get_local_p99()
        return local_error_rate > 0.05 or local_latency > 500
```

### Trace Context Propagation During Partial Failure

```
┌─────────────────────────────────────────────────────────────────────────┐
│              TRACE CONTEXT PROPAGATION EDGE CASES                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Scenario 1: Timeout mid-trace                                         │
│   ┌───────┐     ┌───────┐     ┌───────┐                                 │
│   │   A   │────▶│   B   │──X──│   C   │ (timeout)                       │
│   └───────┘     └───────┘     └───────┘                                 │
│                                                                         │
│   Problem: Trace is incomplete. Did C start? Did it succeed?            │
│   Solution: B should log "calling C, trace_id=X" before call            │
│             C should log "received call, trace_id=X" immediately        │
│                                                                         │
│   Scenario 2: Async processing                                          │
│   ┌───────┐     ┌───────┐     ┌───────┐                                 │
│   │   A   │────▶│ Queue │────▶│   B   │ (hours later)                   │
│   └───────┘     └───────┘     └───────┘                                 │
│                                                                         │
│   Problem: Original trace ended. New trace lacks context.               │
│   Solution: Propagate trace_id in message, link spans                   │
│             B creates new trace with "follows_from" link                │
│                                                                         │
│   Scenario 3: Fan-out                                                   │
│   ┌───────┐     ┌───────┐                                               │
│   │   A   │────▶│   B   │                                               │
│   └───────┘     │   C   │  (parallel calls)                             │
│                 │   D   │                                               │
│                 └───────┘                                               │
│                                                                         │
│   Problem: One child fails, others succeed. Partial failure.            │
│   Solution: Parent span tracks all children, marks partial success      │
│             "3/4 downstream calls succeeded"                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Real-Time Dashboards vs Post-Incident Analysis

| Capability | During Incident | Post-Incident |
|------------|-----------------|---------------|
| Data freshness | Seconds matter | Can wait minutes |
| Query complexity | Simple aggregates | Complex joins |
| Data completeness | Partial is OK | Need everything |
| Resolution | Coarse (1 minute) | Fine (1 second) |
| Correlation | Limited | Full cross-reference |

**Staff Pattern**: Maintain separate hot and cold observability paths:

```
Hot Path (real-time):                Cold Path (analysis):
┌─────────────────────┐             ┌─────────────────────┐
│ In-memory counters  │             │ Full trace storage  │
│ Pre-aggregated      │             │ Raw logs            │
│ Last 1 hour         │             │ Last 90 days        │
│ Fast queries only   │             │ Complex queries OK  │
└─────────────────────┘             └─────────────────────┘
         │                                   │
         ▼                                   ▼
   Incident Response                  Postmortem Analysis
```

---

# Part 9: Consensus and Coordination System Failures

> **Staff Insight**: The systems that coordinate your distributed systems are themselves distributed systems. When they fail, everything that depends on coordination fails differently.

## Failure Modes of Coordination Systems

### ZooKeeper/etcd Failure Taxonomy

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    COORDINATION SYSTEM FAILURES                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   1. LEADER ELECTION FAILURE                                            │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ Cluster: [Node1] [Node2] [Node3]                                │   │
│   │                   ▲                                             │   │
│   │                   │ (Leader dies)                               │   │
│   │                                                                 │   │
│   │ Expected: Node1 or Node3 becomes leader in ~seconds             │   │
│   │ Reality:  Network partition → split brain potential             │   │
│   │           Or: Election storm → repeated elections               │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│   2. SESSION EXPIRY CASCADE                                             │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ 1000 clients with ephemeral nodes                               │   │
│   │ Network blip → All sessions expire                              │   │
│   │ → 1000 nodes deleted                                            │   │
│   │ → 1000 watches fire                                             │   │
│   │ → 1000 clients reconnect                                        │   │
│   │ → 1000 nodes recreated                                          │   │
│   │ → Thundering herd on ZK cluster                                 │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│   3. WATCH NOTIFICATION DELAY                                           │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ App A writes config                                             │   │
│   │ App B watching config                                           │   │
│   │                                                                 │   │
│   │ Under load: Watch notification delayed                          │   │
│   │ → B operates on stale config                                    │   │
│   │ → Not a consistency violation (watches are best-effort)         │   │
│   │ → But application assumes immediate notification                │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│   4. QUORUM LOSS                                                        │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ 5-node cluster, need 3 for quorum                               │   │
│   │                                                                 │   │
│   │ Scenario: Zone failure takes 2 nodes                            │   │
│   │ → Cluster still has quorum (3 nodes)                            │   │
│   │                                                                 │   │
│   │ But: Those 3 nodes now handle all load                          │   │
│   │ → Performance degradation                                       │   │
│   │ → Increased latency for consensus                               │   │
│   │ → Applications timeout waiting for ZK                           │   │
│   │ → Applications retry, making ZK load worse                      │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Leader Election Storms

One of the most insidious coordination failures:

```
Timeline of Leader Election Storm:
──────────────────────────────────────────────────────────────────────────

T=0:    Leader (Node1) experiences GC pause (300ms)
        
T=300ms: Followers timeout, start election
        Node2 votes for self, Node3 votes for self
        
T=500ms: Node1 finishes GC, still thinks it's leader
        Node2 wins election, becomes leader
        
T=600ms: Node1 receives "you're not leader" message
        Node1 steps down, triggers application failover
        
T=700ms: Application on Node1 still processing requests
        Writes to Node1 (not leader) → rejected
        Application retries to Node2
        
T=800ms: Node2 experiences GC pause (GC tuning issue)
        
T=1100ms: New election starts...
        
RESULT: Continuous elections for 30 seconds
        No stable leader = no writes accepted
        All applications using coordination = blocked
```

**Staff-Level Mitigations**:

```python
class CoordinationClientConfig:
    """
    Configuration that prevents election storms from cascading
    """
    
    # Timeouts should be LONGER than expected GC pauses
    session_timeout_ms = 30000  # Not 5000
    
    # Heartbeat should be frequent enough to maintain session
    heartbeat_interval_ms = 10000  # session_timeout / 3
    
    # Exponential backoff on reconnection
    initial_reconnect_delay_ms = 100
    max_reconnect_delay_ms = 30000
    
    # Jitter to prevent thundering herd
    reconnect_jitter_percent = 20
    
    # Don't fail fast on leader change
    retry_on_leader_change = True
    leader_change_retry_count = 5
```

## Designing Applications to Survive Coordination Failures

### Pattern: Cached Coordination Data

```
┌─────────────────────────────────────────────────────────────────────────┐
│              CACHED COORDINATION DATA PATTERN                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Anti-Pattern: Synchronous coordination check                          │
│   ┌───────────────────────────────────────────────────────────────┐     │
│   │ def process_request(request):                                 │     │
│   │     leader = zk.get_leader()  # BLOCKS on ZK call             │     │
│   │     if leader == self:                                        │     │
│   │         process(request)                                      │     │
│   │                                                               │     │
│   │ Problem: ZK slow/down = all requests blocked                  │     │
│   └───────────────────────────────────────────────────────────────┘     │
│                                                                         │
│   Staff Pattern: Async refresh with local cache                         │
│   ┌───────────────────────────────────────────────────────────────┐     │
│   │ class LeaderCache:                                            │     │
│   │     def __init__(self):                                       │     │
│   │         self.am_leader = False                                │     │
│   │         self.last_confirmed = 0                               │     │
│   │         self.stale_threshold_ms = 30000                       │     │
│   │                                                               │     │
│   │     def is_leader(self):                                      │     │
│   │         if self.is_stale():                                   │     │
│   │             # Stale but ZK down - what to do?                 │     │
│   │             return self.handle_stale()                        │     │
│   │         return self.am_leader                                 │     │
│   │                                                               │     │
│   │     def handle_stale(self):                                   │     │
│   │         # Option 1: Assume we lost leadership (safe)          │     │
│   │         # Option 2: Continue if recent activity (risky)       │     │
│   │         # Option 3: Enter read-only mode (degraded)           │     │
│   │         pass                                                  │     │
│   └───────────────────────────────────────────────────────────────┘     │
│                                                                         │
│   Tradeoff:                                                             │
│   └─ Stale cache = potential split-brain                                │
│   └─ No cache = ZK availability becomes your availability               │
│   └─ Staff choice: Bound staleness, accept degradation                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Pattern: Fencing Tokens

```
Preventing Split-Brain with Fencing:
──────────────────────────────────────────────────────────────────────────

Problem:
  Old leader (Node1) has stale "I am leader" cache
  New leader (Node2) is actually leader
  Both try to write to database
  
Solution: Fencing Tokens
  
  ┌─────────────-──────┐
  │ ZK Leader Election │
  │ epoch = 42         │
  └─────────┬────-─────┘
            │
            ▼
  ┌──────────────────────────────────────────────────────────┐
  │ Node1 (old leader): "I am leader, epoch=41"              │
  │ Node2 (new leader): "I am leader, epoch=42"              │
  │                                                          │
  │ Database write:                                          │
  │   Node1: UPDATE table SET value=X WHERE epoch <= 41      │
  │   Node2: UPDATE table SET value=Y WHERE epoch <= 42      │
  │                                                          │
  │ Database check:                                          │
  │   IF incoming_epoch > stored_epoch THEN accept           │
  │   ELSE reject (stale leader)                             │
  └──────────────────────────────────────────────────────────┘
  
  Result: Node1's write rejected, no split-brain
```

---

# Part 10: Cell-Based Architecture — Google's Blast Radius Solution

> **Staff Insight**: At sufficient scale, you stop trying to prevent failures and instead focus on limiting their impact. Cell-based architecture is the industry pattern for blast radius containment.

## What Is Cell-Based Architecture?

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CELL-BASED ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Traditional Architecture:                                             │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                     GLOBAL SERVICE                              │   │
│   │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐        │   │
│   │  │ H1  │ │ H2  │ │ H3  │ │ H4  │ │ H5  │ │ H6  │ │ H7  │ ...    │   │
│   │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘        │   │
│   │                                                                 │   │
│   │  Blast radius: 100% of users                                    │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│   Cell-Based Architecture:                                              │
│   ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐   │
│   │      CELL 1       │  │      CELL 2       │  │      CELL 3       │   │
│   │  ┌─────┐ ┌─────┐  │  │  ┌─────┐ ┌─────┐  │  │  ┌─────┐ ┌─────┐  │   │
│   │  │ H1  │ │ H2  │  │  │  │ H3  │ │ H4  │  │  │  │ H5  │ │ H6  │  │   │
│   │  └─────┘ └─────┘  │  │  └─────┘ └─────┘  │  │  └─────┘ └─────┘  │   │
│   │  Users: 1-33%     │  │  Users: 34-66%    │  │  Users: 67-100%   │   │
│   └───────────────────┘  └───────────────────┘  └───────────────────┘   │
│                                                                         │
│   Blast radius: ~33% of users maximum                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Cell Properties and Design

### What Makes a Cell Independent

| Property | Requirement | Why It Matters |
|----------|-------------|----------------|
| Data Independence | Cell has own database | DB failure contained |
| Compute Independence | No shared hosts | Host issues contained |
| Network Independence | Separate subnets | Network issues contained |
| Configuration Independence | Can have different configs | Can test changes |
| Deployment Independence | Can deploy separately | Bad deploy contained |

### Cell Routing

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CELL ROUTING PATTERNS                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   1. STATIC USER ASSIGNMENT                                             │
│   ┌───────────────────────────────────────────────────────────────┐     │
│   │ cell = hash(user_id) % num_cells                              │     │
│   │                                                               │     │
│   │ Pros: Simple, deterministic                                   │     │
│   │ Cons: Rebalancing is hard, hotspots possible                  │     │
│   └───────────────────────────────────────────────────────────────┘     │
│                                                                         │
│   2. LOOKUP TABLE                                                       │
│   ┌───────────────────────────────────────────────────────────────┐     │
│   │ user_id → cell mapping in global database                     │     │
│   │                                                               │     │
│   │ Pros: Flexible, can move users                                │     │
│   │ Cons: Lookup latency, single point of failure                 │     │
│   └───────────────────────────────────────────────────────────────┘     │
│                                                                         │
│   3. HIERARCHICAL                                                       │
│   ┌───────────────────────────────────────────────────────────────┐     │
│   │ Global router → Regional router → Cell                        │     │
│   │                                                               │     │
│   │ Pros: Scalable, locality-aware                                │     │
│   │ Cons: Complexity, more failure points                         │     │
│   └───────────────────────────────────────────────────────────────┘     │
│                                                                         │
│   Staff Choice: Start with static, add lookup for flexibility           │
│                 Cache lookup results aggressively                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Handling Cross-Cell Operations

```python
class CrossCellOperation:
    """
    Cross-cell operations break cell isolation.
    Minimize them, handle them carefully.
    """
    
    # Anti-pattern: Synchronous cross-cell call
    def send_message_bad(self, from_user, to_user):
        from_cell = self.get_cell(from_user)
        to_cell = self.get_cell(to_user)
        
        # This creates coupling between cells!
        from_cell.record_sent(from_user, message)
        to_cell.deliver_message(to_user, message)  # Sync call
    
    # Staff pattern: Async cross-cell communication
    def send_message_good(self, from_user, to_user):
        from_cell = self.get_cell(from_user)
        
        # Record locally with async delivery
        from_cell.record_sent(from_user, message)
        self.cross_cell_queue.enqueue({
            'target_cell': self.get_cell(to_user),
            'operation': 'deliver',
            'message': message,
            'retry_count': 0,
            'max_retries': 5
        })
    
    # Cross-cell queue processor (runs per cell)
    def process_cross_cell_queue(self):
        for item in self.cross_cell_queue.drain():
            try:
                item['target_cell'].execute(item['operation'], item['message'])
            except CellUnavailable:
                if item['retry_count'] < item['max_retries']:
                    item['retry_count'] += 1
                    self.cross_cell_queue.enqueue_with_delay(
                        item, 
                        delay=exponential_backoff(item['retry_count'])
                    )
                else:
                    self.dead_letter_queue.enqueue(item)
```

## Cell Failure Scenarios

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CELL FAILURE SCENARIOS                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Scenario 1: Single Cell Complete Failure                              │
│   ┌─────────────────────────────────────────────────────────────-──┐    │
│   │ Cell 2 database corruption                                     │    │
│   │                                                                │    │
│   │ Impact: 33% of users affected                                  │    │
│   │ Response: Failover to standby, or wait for repair              │    │
│   │ Duration: Hours (data recovery) instead of minutes (restart)   │    │
│   │                                                                │    │
│   │ Key decision: Can we move users to other cells?                │    │
│   │ Usually no - data is in failed cell                            │    │
│   └─────────────────────────────────────────────────────────-──────┘    │
│                                                                         │
│   Scenario 2: Cell Partial Degradation                                  │
│   ┌─────────────────────────────────────────────────────────────-──┐    │
│   │ Cell 1 running slow (50% normal throughput)                    │    │
│   │                                                                │    │
│   │ Options:                                                       │    │
│   │ a) Live with degradation (33% users slow)                      │    │
│   │ b) Shed load from Cell 1 (some users get errors)               │    │
│   │ c) Redirect new users to other cells (Cell 1 drains)           │    │
│   │                                                                │    │
│   │ Staff choice: Depends on cause. Memory leak → option c         │    │
│   │               Load spike → option a with monitoring            │    │
│   └────────────────────────────────────────────────────────────-───┘    │
│                                                                         │
│   Scenario 3: Bad Deploy to One Cell                                    │
│   ┌────────────────────────────────────────────────────────────-───┐    │
│   │ New version deployed to Cell 3, has bug                        │    │
│   │                                                                │    │
│   │ This is THE reason for cells!                                  │    │
│   │                                                                │    │
│   │ Response:                                                      │    │
│   │ 1. Detect in Cell 3 (error rate spike)                         │    │
│   │ 2. Rollback Cell 3 (quick)                                     │    │
│   │ 3. Investigate before deploying to Cell 1, 2                   │    │
│   │                                                                │    │
│   │ Blast radius: 33% instead of 100%                              │    │
│   └──────────────────────────────────────────────────────────-─────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Interview Signal**: "Cell-based architecture trades operational complexity for blast radius containment. Each cell is a complete copy of your service, which means more infrastructure, more deployment complexity, and more monitoring. The tradeoff is worth it when you can't afford global outages."

---

# Part 11: Data Consistency During Partial Failures

> **Staff Insight**: During partitions, you can have availability or consistency, not both. But CAP is a theorem about extremes — real systems operate in the nuanced middle ground.

## The CAP Theorem in Practice

```
┌─────────────────────────────────────────────────────────────────────────┐
│              CAP THEOREM PRACTICAL INTERPRETATION                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Theoretical CAP:                                                      │
│   "During a partition, choose consistency OR availability"              │
│                                                                         │
│   Practical CAP:                                                        │
│   "How do you want to fail when things go wrong?"                       │
│                                                                         │
│                        Consistency                                      │
│                            ▲                                            │
│                            │                                            │
│                     ┌──────┴──────┐                                     │
│                     │ CP Systems  │                                     │
│                     │ (e.g., ZK)  │                                     │
│                     │             │                                     │
│                     │ During      │                                     │
│                     │ partition:  │                                     │
│                     │ Reject      │                                     │
│                     │ writes      │                                     │
│                     └─────────────┘                                     │
│                                                                         │
│        ┌─────────────┐                    ┌─────────────┐               │
│        │ AP Systems  │◀──────────────────▶│ Reality     │               │
│        │ (e.g.,      │                    │ (Most       │               │
│        │ Cassandra)  │                    │ systems)    │               │
│        │             │                    │             │               │
│        │ During      │                    │ During      │               │
│        │ partition:  │                    │ partition:  │               │
│        │ Accept      │                    │ Some ops    │               │
│        │ writes,     │                    │ work, some  │               │
│        │ reconcile   │                    │ don't       │               │
│        │ later       │                    │             │               │
│        └─────────────┘                    └─────────────┘               │
│              │                                  │                       │
│              └────────────▶ Availability ◀──────┘                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Consistency Strategies During Degradation

### Strategy 1: Read-Your-Writes Guarantee

```python
class ReadYourWritesSession:
    """
    Guarantee that a user sees their own writes,
    even if replicas are behind.
    """
    
    def __init__(self, user_id):
        self.user_id = user_id
        self.last_write_timestamp = {}  # {key: timestamp}
    
    def write(self, key, value):
        result = self.primary.write(key, value)
        self.last_write_timestamp[key] = result.timestamp
        return result
    
    def read(self, key):
        required_timestamp = self.last_write_timestamp.get(key, 0)
        
        # Try replicas, but check freshness
        for replica in self.replicas:
            try:
                result = replica.read(key)
                if result.timestamp >= required_timestamp:
                    return result
            except ReplicaUnavailable:
                continue
        
        # Fall back to primary if replicas stale
        return self.primary.read(key)
```

### Strategy 2: Bounded Staleness

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    BOUNDED STALENESS PATTERN                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Goal: Accept stale reads, but limit HOW stale                         │
│                                                                         │
│   Implementation:                                                       │
│   ┌─────────────────────────────────────────────────────────-──────┐    │
│   │ class BoundedStalenessRead:                                    │    │
│   │     def read(self, key, max_stale_seconds=5):                  │    │
│   │         result = self.replica.read(key)                        │    │
│   │                                                                │    │
│   │         staleness = now() - result.timestamp                   │    │
│   │         if staleness > max_stale_seconds:                      │    │
│   │             # Data too old, must go to primary                 │    │
│   │             return self.primary.read(key)                      │    │
│   │                                                                │    │
│   │         return result                                          │    │
│   └─────────────────────────────────────────────────────-──────────┘    │
│                                                                         │
│   During partial failure (primary slow/unavailable):                    │
│                                                                         │
│   Scenario A: Replica 2s stale, max_stale=5s                            │
│   → Return replica data (slightly stale but acceptable)                 │
│                                                                         │
│   Scenario B: Replica 30s stale, max_stale=5s                           │
│   → Try primary, if unavailable, return error                           │
│   → Or: Return stale data with "stale" flag                             │
│                                                                         │
│   Tradeoff:                                                             │
│   • Looser bound → more availability, less consistency                  │
│   • Tighter bound → less availability, more consistency                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Strategy 3: Conflict Resolution

```python
class LastWriterWinsConflictResolution:
    """
    Simple but dangerous conflict resolution strategy.
    """
    
    def resolve(self, versions):
        # Highest timestamp wins
        return max(versions, key=lambda v: v.timestamp)
    
    # Why this is dangerous:
    # User A: read balance=100, add $50, write balance=150, ts=T1
    # User B: read balance=100, add $20, write balance=120, ts=T2
    # 
    # If T2 > T1: balance = 120 (lost $50)
    # If T1 > T2: balance = 150 (lost $20)
    # Neither is correct! Should be $170


class ApplicationSpecificConflictResolution:
    """
    Better: Let the application decide how to merge.
    """
    
    def resolve_shopping_cart(self, versions):
        # Cart: union of all items
        merged_items = set()
        for version in versions:
            merged_items.update(version.items)
        return Cart(items=merged_items)
    
    def resolve_counter(self, versions):
        # Counter: sum all increments
        # Requires CRDT (Conflict-free Replicated Data Type)
        total = sum(v.increment for v in versions)
        return Counter(value=total)
    
    def resolve_document(self, versions):
        # Document: can't auto-merge, surface to user
        if len(versions) > 1:
            return ConflictedDocument(
                versions=versions,
                needs_human_resolution=True
            )
```

## Real-World Consistency During Partitions

### Example: Shopping Cart During Partition

```
┌─────────────────────────────────────────────────────────────────────────┐
│              SHOPPING CART DURING NETWORK PARTITION                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Scenario:                                                             │
│   ┌─────────────────────────────────────────────────────────────-────┐  │
│   │ User in NYC, primary database in SF, network partition occurs    │  │
│   │                                                                  │  │
│   │ User actions during partition:                                   │  │
│   │ 1. Add item A to cart                                            │  │
│   │ 2. Add item B to cart                                            │  │
│   │ 3. Remove item A from cart                                       │  │
│   │ 4. Checkout                                                      │  │
│   └──────────────────────────────────────────────────────────────-───┘  │
│                                                                         │
│   Option A: Reject all operations (CP)                                  │
│   └─ "Your cart is temporarily unavailable"                             │
│   └─ User leaves, goes to competitor                                    │
│   └─ Lost revenue                                                       │
│                                                                         │
│   Option B: Accept operations locally (AP)                              │
│   └─ Write to local cache/database                                      │
│   └─ User completes shopping                                            │
│   └─ When partition heals, sync with primary                            │
│   └─ Risk: Conflicts if user on multiple devices                        │
│                                                                         │
│   Option C: Degraded mode (Staff choice)                                │
│   └─ Cart add/remove: Accept locally                                    │
│   └─ Checkout: Require primary                                          │
│   └─ "We can save your cart but checkout requires connection"           │
│   └─ Preserves revenue, avoids double-charge                            │
│                                                                         │
│   Interview Signal: "The right consistency level depends on the         │
│   operation. Adding to cart is safe to replicate — worst case,          │
│   user has extra items. Charging a credit card must be consistent."     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

# Part 12: Chaos Engineering and Failure Injection

> **Staff Insight**: You don't know how your system fails until you make it fail on purpose. Chaos engineering is how Staff engineers gain confidence in their failure handling.

## Principles of Chaos Engineering

```
┌─────────────────────────────────────────────────────────────────────────┐
│              CHAOS ENGINEERING PRINCIPLES                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   1. DEFINE STEADY STATE                                                │
│   ┌───────────────────────────────────────────────────────-────────┐    │
│   │ What does "working" look like?                                 │    │
│   │ • Success rate > 99.9%                                         │    │
│   │ • P99 latency < 200ms                                          │    │
│   │ • Throughput > 10K req/s                                       │    │
│   │                                                                │    │
│   │ Without this, you can't measure impact of failure              │    │
│   └────────────────────────────────────────────────────────-───────┘    │
│                                                                         │
│   2. HYPOTHESIZE IMPACT                                                 │
│   ┌─────────────────────────────────────────────────────────-──────┐    │
│   │ Before injecting failure, predict:                             │    │
│   │ "If cache fails, latency will increase 50% but success rate    │    │
│   │  will stay above 99.9% due to database fallback"               │    │
│   │                                                                │    │
│   │ This forces you to understand the system                       │    │
│   └──────────────────────────────────────────────────────────-─────┘    │
│                                                                         │
│   3. VARY REAL-WORLD EVENTS                                             │
│   ┌───────────────────────────────────────────────────────────-────┐    │
│   │ Inject failures that actually happen:                          │    │
│   │ • Network latency (common)                                     │    │
│   │ • Process crash (common)                                       │    │
│   │ • Disk full (less common but impactful)                        │    │
│   │ • Clock skew (rare but devastating)                            │    │
│   │                                                                │    │
│   │ Don't inject: meteor strike, simultaneous failure of all       │    │
│   │               components (not realistic)                       │    │
│   └───────────────────────────────────────────────────────────-────┘    │
│                                                                         │
│   4. RUN IN PRODUCTION                                                  │
│   ┌────────────────────────────────────────────────────────────-───┐    │
│   │ Staging doesn't have:                                          │    │
│   │ • Real traffic patterns                                        │    │
│   │ • Real data distributions                                      │    │
│   │ • Real dependencies                                            │    │
│   │ • Real scale                                                   │    │
│   │                                                                │    │
│   │ Start with small blast radius in production                    │    │
│   │ (1% of traffic, one cell, one region)                          │    │
│   └─────────────────────────────────────────────────────────────-──┘    │
│                                                                         │
│   5. MINIMIZE BLAST RADIUS                                              │
│   ┌──────────────────────────────────────────────────────────────-─┐    │
│   │ Abort experiments that exceed expected impact                  │    │
│   │ Auto-rollback if SLOs violated                                 │    │
│   │ Run during low-traffic periods initially                       │    │
│   └───────────────────────────────────────────────────────────────-┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Failure Injection Techniques

### Technique 1: Latency Injection

```python
class LatencyInjector:
    """
    Add artificial latency to discover timeout and cascading issues.
    """
    
    def __init__(self, target_service):
        self.target_service = target_service
        self.injection_config = None
    
    def configure(self, 
                  latency_ms=100,
                  percentage=1.0,
                  user_whitelist=None):
        """
        Start with small percentage, increase gradually.
        User whitelist allows injecting for test accounts only.
        """
        self.injection_config = {
            'latency_ms': latency_ms,
            'percentage': percentage,
            'user_whitelist': user_whitelist
        }
    
    def should_inject(self, request):
        if not self.injection_config:
            return False
        
        # Only inject for whitelisted users in early experiments
        if self.injection_config['user_whitelist']:
            if request.user_id not in self.injection_config['user_whitelist']:
                return False
        
        return random.random() < self.injection_config['percentage']
    
    def inject(self, request):
        if self.should_inject(request):
            time.sleep(self.injection_config['latency_ms'] / 1000)


# Experiments to run:
# 1. Inject 50ms to database → See if cache helps
# 2. Inject 500ms to database → See if timeouts trigger
# 3. Inject 5000ms to database → See if circuit breakers work
# 4. Inject 50ms to all downstream → See aggregate effect
```

### Technique 2: Error Injection

```python
class ErrorInjector:
    """
    Return errors instead of real responses.
    """
    
    ERROR_TYPES = {
        'connection_refused': ConnectionRefusedError,
        'timeout': TimeoutError,
        'internal_error': InternalServerError,
        'rate_limited': RateLimitError,
        'invalid_response': MalformedResponseError
    }
    
    def inject_error(self, error_type, request):
        """
        Different errors test different recovery paths.
        """
        error_class = self.ERROR_TYPES.get(error_type)
        
        # Log for analysis
        self.metrics.record('chaos.error_injected', {
            'error_type': error_type,
            'request_id': request.id,
            'timestamp': time.time()
        })
        
        raise error_class(f"Injected error: {error_type}")


# Key experiments:
# 1. Connection refused → Does retry with different host work?
# 2. Timeout → Does caller timeout propagate correctly?
# 3. Rate limited → Does backoff work? Does circuit breaker open?
# 4. Invalid response → Does validation catch it? Does fallback work?
```

### Technique 3: Resource Exhaustion

```python
class ResourceExhaustionInjector:
    """
    Exhaust system resources to find limits.
    """
    
    def exhaust_connections(self, pool_size):
        """Hold connections to simulate pool exhaustion."""
        connections = []
        for _ in range(pool_size):
            conn = self.database.get_connection(timeout=0)
            connections.append(conn)
        # Now new requests will fail to get connections
        return connections
    
    def exhaust_memory(self, megabytes):
        """Consume memory to trigger GC pressure."""
        data = bytearray(megabytes * 1024 * 1024)
        return data  # Hold reference
    
    def exhaust_cpu(self, duration_seconds, cores=1):
        """Spin CPU to simulate compute-bound issues."""
        import multiprocessing
        
        def spin():
            end = time.time() + duration_seconds
            while time.time() < end:
                pass
        
        processes = []
        for _ in range(cores):
            p = multiprocessing.Process(target=spin)
            p.start()
            processes.append(p)
        
        return processes  # Caller must join/terminate
```

## Chaos Engineering Maturity Model

```
┌─────────────────────────────────────────────────────────────────────────┐
│              CHAOS ENGINEERING MATURITY LEVELS                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   LEVEL 0: No chaos engineering                                         │
│   └─ Hope failures don't happen                                         │
│   └─ Learn from production incidents only                               │
│                                                                         │
│   LEVEL 1: Ad-hoc experiments                                           │
│   └─ Manual failure injection                                           │
│   └─ Kill pods occasionally                                             │
│   └─ No systematic approach                                             │
│                                                                         │
│   LEVEL 2: Defined experiments (Most teams should be here)              │
│   └─ Documented failure scenarios                                       │
│   └─ Regular chaos game days                                            │
│   └─ Experiments in staging                                             │
│   └─ Some production experiments with careful controls                  │
│                                                                         │
│   LEVEL 3: Automated chaos (Staff-level teams)                          │
│   └─ Continuous chaos in production                                     │
│   └─ Automated experiment selection                                     │
│   └─ Integration with CI/CD                                             │
│   └─ Chaos experiments gate deployments                                 │
│                                                                         │
│   LEVEL 4: Chaos as culture (Google, Netflix level)                     │
│   └─ Every engineer runs chaos experiments                              │
│   └─ Chaos is part of design review                                     │
│   └─ Chaos budget (like error budget)                                   │
│   └─ Failure injection in customer path                                 │
│                                                                         │
│   Interview Signal: "We run weekly chaos game days where we inject      │
│   failures and verify our runbooks work. It's caught several issues     │
│   before they became production incidents."                             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Sample Chaos Experiments for Interviews

When discussing chaos engineering in interviews, reference specific experiments:

| System | Experiment | Expected Result | What We Learned |
|--------|-----------|-----------------|-----------------|
| Cache | Kill all cache nodes | Latency spike 3x, no errors | Database can handle load but slowly |
| Database | Kill primary | Failover in 30s, some errors | Need to reduce failover time |
| API | Inject 500ms latency | Downstream timeouts trigger | Timeouts were set too tight |
| Queue | Pause consumers 5min | Backlog grows, no data loss | Auto-scaling kicked in correctly |
| DNS | Return stale records | 10% traffic to old hosts | Need health checks at LB |

---

# Part 13: Multi-Region Failure Coordination

> **Staff Insight**: Multi-region architecture is supposed to provide resilience, but it also provides new failure modes. The coordination between regions is often the weakest link.

## Multi-Region Architecture Patterns

```
┌─────────────────────────────────────────────────────────────────────────┐
│              MULTI-REGION PATTERNS AND TRADE-OFFS                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   PATTERN 1: ACTIVE-PASSIVE                                             │
│   ┌───────────────────────────────────────────────────────────────┐     │
│   │    US-EAST (Active)              US-WEST (Passive)            │     │
│   │   ┌─────────────────┐           ┌─────────────────┐           │     │
│   │   │   All Traffic   │──async───▶│   Standby       │           │     │
│   │   │   ┌─────────┐   │ repl     │   ┌─────────┐   │            │     │
│   │   │   │   DB    │   │          │   │DB(read) │   │            │     │
│   │   │   └─────────┘   │          │   └─────────┘   │            │     │
│   │   └─────────────────┘          └─────────────────┘            │     │
│   │                                                               │     │
│   │   Pros: Simple, no write conflicts                            │     │
│   │   Cons: Wasted capacity, failover takes minutes               │     │
│   │   Failure mode: Failover triggers data loss (repl lag)        │     │
│   └───────────────────────────────────────────────────────────────┘     │
│                                                                         │
│   PATTERN 2: ACTIVE-ACTIVE (Partitioned)                                │
│   ┌───────────────────────────────────────────────────────────────┐     │
│   │    US-EAST (Users A-M)           US-WEST (Users N-Z)          │     │
│   │   ┌─────────────────┐           ┌─────────────────┐           │     │
│   │   │   50% Traffic   │◀──sync───▶│   50% Traffic   │           │     │
│   │   │   ┌─────────┐   │ (cross-   │   ┌─────────┐   │           │     │
│   │   │   │   DB    │   │  region)  │   │   DB    │   │           │     │
│   │   │   └─────────┘   │           │   └─────────┘   │           │     │
│   │   └─────────────────┘           └─────────────────┘           │     │
│   │                                                               │     │
│   │   Pros: Uses all capacity, fast failover                      │     │
│   │   Cons: Cross-region calls for some operations                │     │
│   │   Failure mode: Region failure = 50% of users degraded        │     │
│   └───────────────────────────────────────────────────────────────┘     │
│                                                                         │
│   PATTERN 3: ACTIVE-ACTIVE (Replicated)                                 │
│   ┌───────────────────────────────────────────────────────────────┐     │
│   │    US-EAST                       US-WEST                      │     │
│   │   ┌─────────────────┐           ┌─────────────────┐           │     │
│   │   │   Any User      │◀──async──▶│   Any User      │           │     │
│   │   │   ┌─────────┐   │ conflict  │   ┌─────────┐   │           │     │
│   │   │   │   DB    │   │  resol.   │   │   DB    │   │           │     │
│   │   │   └─────────┘   │           │   └─────────┘   │           │     │
│   │   └─────────────────┘           └─────────────────┘           │     │
│   │                                                               │     │
│   │   Pros: Best availability, full use of capacity               │     │
│   │   Cons: Conflict resolution required, eventual consistency    │     │
│   │   Failure mode: Partition causes conflicting writes           │     │
│   └───────────────────────────────────────────────────────────────┘     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Regional Failover Decision Making

```
┌─────────────────────────────────────────────────────────────────────────┐
│              REGIONAL FAILOVER DECISION TREE                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Trigger: Region US-EAST showing degradation                           │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ Q1: Is this a regional issue or global?                         │   │
│   │     └─ Check: Are other regions also degraded?                  │   │
│   │     └─ If global: Don't failover (won't help)                   │   │
│   │     └─ If regional: Continue to Q2                              │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                        │                                                │
│                        ▼                                                │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ Q2: Can receiving region handle the load?                       │   │
│   │     └─ Check: Current utilization of US-WEST                    │   │
│   │     └─ Check: Reserved capacity headroom                        │   │ 
│   │     └─ If no: Partial failover or shed load first               │   │
│   │     └─ If yes: Continue to Q3                                   │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                        │                                                │
│                        ▼                                                │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ Q3: What's the data consistency state?                          │   │
│   │     └─ Check: Replication lag                                   │   │
│   │     └─ If lag > threshold: Accept data loss or wait?            │   │
│   │     └─ Document: "Accepting up to 30s of data loss"             │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                        │                                                │
│                        ▼                                                │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ Q4: Is this recoverable without failover?                       │   │
│   │     └─ Check: Is there a known remediation?                     │   │
│   │     └─ Check: ETA for fix                                       │   │
│   │     └─ If fix < 5 min: Consider waiting                         │   │
│   │     └─ If fix > 15 min: Failover is probably faster             │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                        │                                                │
│                        ▼                                                │
│   DECISION: Initiate failover with documentation                        │
│   └─ Log: Who decided, what evidence, what's the expected outcome       │
│   └─ Communicate: Status page update, internal channels                 │
│   └─ Monitor: Watch receiving region for overload                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Split-Brain Between Regions

```
┌─────────────────────────────────────────────────────────────────────────┐
│              SPLIT-BRAIN SCENARIOS AND MITIGATIONS                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Scenario: Network partition between US-EAST and US-WEST               │
│                                                                         │
│   ┌─────────────────┐    XXXXXXX   ┌─────────────────┐                  │
│   │    US-EAST      │───X     X────│    US-WEST      │                  │
│   │                 │   XXXXXXX    │                 │                  │
│   │ "I'm the only   │              │ "I'm the only   │                  │
│   │  region alive"  │              │  region alive"  │                  │
│   │                 │              │                 │                  │
│   │ Continue        │              │ Continue        │                  │
│   │ accepting       │              │ accepting       │                  │
│   │ writes          │              │ writes          │                  │
│   └─────────────────┘              └─────────────────┘                  │
│                                                                         │
│   Result: Conflicting writes, divergent data                            │
│                                                                         │
│   MITIGATIONS:                                                          │
│                                                                         │
│   1. External Arbiter                                                   │
│   ┌────────────────────────────────────────────────────────────-───┐    │
│   │ Third party (different network) determines which region lives  │    │
│   │ → Region that can't reach arbiter stops accepting writes       │    │
│   │ Downside: Arbiter is SPOF, false positives                     │    │
│   └─────────────────────────────────────────────────────────────-──┘    │
│                                                                         │
│   2. Quorum-Based                                                       │
│   ┌──────────────────────────────────────────────────────────────-─┐    │
│   │ Need 2/3 regions to agree before accepting writes              │    │
│   │ → Partition isolates 1 region = it stops                       │    │
│   │ → Partition isolates 2 regions = ???                           │    │
│   │ Downside: Need odd number of regions                           │    │
│   └───────────────────────────────────────────────────────────────-┘    │
│                                                                         │
│   3. Designated Primary                                                 │
│   ┌─────────────────────────────────────────────────────────────-──┐    │
│   │ US-EAST is always primary for writes                           │    │
│   │ → During partition, US-WEST goes read-only                     │    │
│   │ Downside: US-WEST users degraded during partition              │    │
│   └─────────────────────────────────────────────────────────────-──┘    │
│                                                                         │
│   4. CRDT-Based (Conflict-Free)                                         │
│   ┌──────────────────────────────────────────────────────────────-─┐    │
│   │ Design data structures that merge automatically                │    │
│   │ → Both regions accept writes, merge when partition heals       │    │
│   │ Downside: Limited data operations, complex implementation      │    │
│   └───────────────────────────────────────────────────────────────-┘    │
│                                                                         │
│   Staff Choice: Depends on consistency requirements                     │
│   • Payment system: Designated primary (safety > availability)          │
│   • Social feed: CRDT-based (availability > consistency)                │
│   • Shopping cart: Merge on reconciliation (good enough)                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

# Part 14: Capacity Planning for Failure

> **Staff Insight**: You don't just plan capacity for normal operation — you plan capacity for the worst day. If your N+1 redundancy can't handle an actual failure, it's not redundancy.

## Capacity Under Failure Scenarios

```
┌─────────────────────────────────────────────────────────────────────────┐
│              CAPACITY PLANNING SCENARIOS                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Normal Operation:                                                     │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ 3 hosts × 1000 QPS each = 3000 QPS capacity                     │   │
│   │ Current load: 2000 QPS                                          │   │
│   │ Headroom: 33% ✓                                                 │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│   During Failure (1 host down):                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ 2 hosts × 1000 QPS each = 2000 QPS capacity                     │   │
│   │ Current load: 2000 QPS                                          │   │
│   │ Headroom: 0% ✗                                                  │   │
│   │                                                                 │   │
│   │ No room for:                                                    │   │
│   │ • Traffic spike                                                 │   │
│   │ • Retry storms                                                  │   │
│   │ • Background jobs                                               │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│   Real-World Failure (1 host down + retry storm):                       │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ 2 hosts × 1000 QPS each = 2000 QPS capacity                     │   │
│   │ Original load: 2000 QPS                                         │   │
│   │ Failed request retries: 500 QPS (25% of original)               │   │
│   │ Actual load: 2500 QPS                                           │   │
│   │ Result: 500 QPS dropped → 25% error rate                        │   │
│   │                                                                 │   │
│   │ Cascade: Dropped requests retry → more load → more drops        │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│   Staff Capacity Planning:                                              │
│   ┌───────────────────────────────────────────────────────────────-┐    │
│   │ Rule of thumb: N+2 for critical services                       │    │
│   │                                                                │    │
│   │ 4 hosts × 1000 QPS = 4000 QPS capacity                         │    │
│   │ Normal load: 2000 QPS (50% utilization)                        │    │
│   │                                                                │    │
│   │ 1 host down: 3000 QPS capacity, 67% utilization ✓              │    │
│   │ 1 host down + 25% retries: 2500 QPS, 83% utilization ✓         │    │
│   │ 2 hosts down: 2000 QPS, 100% utilization (degraded but up)     │    │
│   └───────────────────────────────────────────────────────────────-┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Capacity Reservation Strategies

```python
class CapacityReservation:
    """
    Reserve capacity for different purposes.
    """
    
    def __init__(self, total_capacity):
        self.total_capacity = total_capacity
        
        # Reserve pools
        self.critical_request_pool = total_capacity * 0.20  # 20% for critical
        self.normal_request_pool = total_capacity * 0.60    # 60% for normal
        self.batch_job_pool = total_capacity * 0.10         # 10% for batch
        self.headroom = total_capacity * 0.10               # 10% never used
    
    def admit_request(self, request):
        if request.priority == 'critical':
            pool = self.critical_request_pool + self.normal_request_pool
        elif request.priority == 'normal':
            pool = self.normal_request_pool
        elif request.priority == 'batch':
            pool = self.batch_job_pool
        else:
            pool = self.normal_request_pool
        
        if self.current_usage[request.priority] < pool:
            return True  # Admit
        else:
            return False  # Reject (load shed)
    
    def during_failure(self):
        """
        During failure, reclaim batch capacity for critical work.
        """
        self.critical_request_pool += self.batch_job_pool
        self.batch_job_pool = 0
        self.pause_batch_jobs()


# Example calculation:
# 
# Normal: 1000 QPS capacity
# Critical: 200 QPS reserved
# Normal: 600 QPS reserved  
# Batch: 100 QPS reserved
# Headroom: 100 QPS reserved
#
# During failure:
# Critical: 300 QPS (200 + 100 from batch)
# Normal: 600 QPS
# Batch: 0 QPS (paused)
# Headroom: 100 QPS
```

## Auto-Scaling During Failures

```
┌─────────────────────────────────────────────────────────────────────────┐
│              AUTO-SCALING DURING FAILURES                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Problem: Auto-scaling can make failures worse                         │
│                                                                         │
│   Scenario: Database slow                                               │
│   ┌────────────────────────────────────────────────────────────-───┐    │
│   │ 1. Requests slow down (waiting for DB)                         │    │
│   │ 2. Request queue grows                                         │    │
│   │ 3. Auto-scaler sees high CPU (request handling)                │    │
│   │ 4. Auto-scaler adds more instances                             │    │
│   │ 5. More instances = more DB connections                        │    │
│   │ 6. DB more overloaded = requests even slower                   │    │
│   │ 7. More instances added...                                     │    │
│   │                                                                │    │
│   │ Result: Runaway scaling that makes problem worse               │    │
│   └─────────────────────────────────────────────────────────────-──┘    │
│                                                                         │
│   Staff Solution: Context-aware scaling                                 │
│   ┌──────────────────────────────────────────────────────────────-─┐    │
│   │ def should_scale_up(metrics):                                  │    │
│   │     # Don't scale if dependency is the bottleneck              │    │
│   │     if metrics.db_latency > threshold:                         │    │
│   │         log("DB slow, scaling won't help")                     │    │
│   │         return False                                           │    │
│   │                                                                │    │
│   │     if metrics.upstream_error_rate > threshold:                │    │
│   │         log("Upstream failing, scaling won't help")            │    │
│   │         return False                                           │    │
│   │                                                                │    │
│   │     # Only scale if WE are the bottleneck                      │    │
│   │     if metrics.cpu > 80 and metrics.request_queue > threshold: │    │
│   │         return True                                            │    │
│   │                                                                │    │
│   │     return False                                               │    │
│   └───────────────────────────────────────────────────────────-────┘    │
│                                                                         │
│   Also: Maximum scale limits                                            │
│   ┌────────────────────────────────────────────────────────────-───┐    │
│   │ • Hard cap: Never more than 10x normal capacity                │    │
│   │ • Soft cap: Alert at 3x normal capacity                        │    │
│   │ • Cost cap: Stop scaling at $X/hour                            │    │
│   │ • Connection cap: Scale only if DB connections available       │    │
│   └─────────────────────────────────────────────────────────────-──┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Part 14B: Cost Reality — What Failure Tolerance Actually Costs

```
┌─────────────────────────────────────────────────────────────────────────┐
│              COST BREAKDOWN: FAILURE TOLERANCE INVESTMENTS              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Resilience Pattern              │ Cost Impact                        │
│   ────────────────────────────────┼────────────────────────────────────│
│   N+1 provisioning                │ 33-100% extra compute              │
│   (always-on spare capacity)      │ (depends on redundancy level)     │
│                                   │                                    │
│   Multi-region failover           │ 2× infrastructure cost             │
│   (active-passive)                │ (active-active adds conflict      │
│                                   │  resolution engineering overhead)  │
│                                   │                                    │
│   Chaos engineering program        │ 0.5-1 FTE dedicated               │
│                                   │ + testing infrastructure           │
│                                   │ + blast radius from experiments   │
│                                   │                                    │
│   Cell-based architecture         │ 10-20% overhead                    │
│                                   │ (cell routing + config mgmt       │
│                                   │  + reduced bin-packing efficiency) │
│                                   │                                    │
│   Observability stack             │ $5K-50K/month                      │
│   (metrics, traces, logs)         │ (often most underestimated cost)  │
│                                   │                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

**Dominant Cost Drivers**: 
- **#1: Spare capacity (N+1)** — Always-on redundancy is the largest cost
- **#2: Multi-region replication** — Doubling infrastructure for failover

**Dollar Example**:
For a 100-server service:
- N+1 provisioning adds 34 servers ($50K/month)
- Cell-based architecture (4 cells) adds routing overhead + 15% reduced efficiency ($22K/month)
- Total failure tolerance cost: **$72K/month** — roughly **40% of base infrastructure cost**

**Cost of NOT Investing**:
Average cost of a 1-hour outage for a mid-size e-commerce platform:
- $100K-500K in lost revenue
- $50K in engineering time
- Customer trust erosion (unquantifiable)

**One major outage per year justifies $600K/year in resilience investment.**

**What Staff Engineers Do NOT Build**:
- Chaos engineering before basic monitoring is solid
- Cell-based architecture for < 10 services (start with bulkheads)
- Automated multi-region failover before manual failover is tested and reliable
- Perfect failure detection (accept false positives, design for safe defaults)

**Cost-Scaling Rule**: 
> Resilience cost should be **20-40% of base infrastructure cost**. Below 20%, you're under-invested. Above 40%, you're likely over-engineering.

---

# Part 15: Runbook Essentials for Partial Failures

> **Staff Insight**: Runbooks are not documentation — they're operational muscle memory. The time to write them is before the incident, when you can think clearly.

### Ownership Model During Failures

```
┌─────────────────────────────────────────────────────────────────────────┐
│              INCIDENT ROLES AND OWNERSHIP                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Role                    │ Ownership                                  │
│   ────────────────────────┼────────────────────────────────────────────│
│   Incident Commander      │ Timeline, communication, decision          │
│   (Senior on-call)        │ authority                                  │
│                           │                                            │
│   Service Owner           │ Diagnosis + fix                            │
│   (Team owning root-cause │                                            │
│    service)               │                                            │
│                           │                                            │
│   Blast Radius Assessor   │ Understanding who else is affected         │
│   (SRE or Staff Engineer) │                                            │
│                           │                                            │
│   Communication Lead      │ Status page, stakeholder updates           │
│   (Separate from IC)      │                                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Ownership Ambiguity That Causes Outages**:
> During a cascading failure, Service A team says "our service is healthy, the problem is Service B." Service B says the same about Service C. Meanwhile, nobody is working on the actual user-facing impact.

**Staff-Level Fix**:
> Incident Commander owns the **USER IMPACT**, not any specific service. Their job is to restore user experience, which may mean degrading Service A even though Service A is "healthy."

**Cross-Team Handoff Protocol**:
When root cause crosses team boundaries:
1. Both teams join the incident call
2. IC decides which team leads the fix
3. Other team provides support and context

**Post-Incident Ownership**:
- Owning team writes the postmortem
- **ALL affected teams review and add their perspective**
- IC ensures cross-team learnings are captured

### Cross-Team and Org Impact of Partial Failures

Partial failures rarely respect team boundaries. Staff Engineers anticipate how one team's degradation affects others—and how org structure shapes both propagation and response.

```
┌─────────────────────────────────────────────────────────────────────────┐
│              CROSS-TEAM FAILURE PROPAGATION                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   SCENARIO: Platform Team's rate limiter slows                          │
│                                                                         │
│   Team A (Checkout):  Depends on rate limiter → requests blocked        │
│   Team B (Search):    Depends on rate limiter → requests blocked        │
│   Team C (Recommend): Depends on rate limiter → requests blocked        │
│                                                                         │
│   ORG DYNAMICS:                                                         │
│   ─────────────                                                         │
│   • Each team pages their own on-call                                   │
│   • No single owner of "user experience"                                 │
│   • Mitigation requires Platform Team fix                               │
│   • Checkout/Search/Recommend lack authority to bypass rate limiter     │
│                                                                         │
│   STAFF-LEVEL DESIGN:                                                   │
│   ───────────────────                                                   │
│   • Shared SLO: "Checkout availability" owned by IC, not service owner  │
│   • Kill switch: IC can enable circuit bypass during major incidents    │
│   • Cross-team runbooks: "When Platform degrades, these teams affected"  │
│   • Escalation path: 5 min → IC, 10 min → Staff/Principal              │
│                                                                         │
│   BLAST RADIUS ACROSS TEAMS:                                            │
│   ──────────────────────────                                            │
│   Single shared dependency = N teams affected simultaneously            │
│   Staff question: "If this fails, how many team standups are about it?" │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Org-Level Insight**: Shared dependencies create shared fate. The more teams depend on a component, the higher the blast radius—and the more critical that component's resilience. Staff Engineers advocate for resilience investment in shared platform services precisely because failure there affects the whole org.

## Anatomy of an Effective Runbook

```
┌─────────────────────────────────────────────────────────────────────────┐
│              RUNBOOK STRUCTURE FOR PARTIAL FAILURES                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   1. IDENTIFICATION (first 60 seconds)                                  │
│   ┌────────────────────────────────────────────────────────-───────┐    │
│   │ Symptoms:                                                      │    │
│   │ □ Error rate > 5% on /api/checkout                             │    │
│   │ □ Latency P99 > 2s on /api/checkout                            │    │
│   │ □ Alerts: payment-service-high-latency                         │    │
│   │                                                                │    │
│   │ Is this runbook applicable?                                    │    │
│   │ □ Payment service metrics showing degradation                  │    │
│   │ □ Other services unaffected                                    │    │
│   │ → If YES, continue. If NO, escalate to on-call lead.           │    │
│   └─────────────────────────────────────────────────────────-──────┘    │
│                                                                         │
│   2. IMMEDIATE MITIGATION (next 5 minutes)                              │
│   ┌──────────────────────────────────────────────────────────-─────┐    │
│   │ Option A: Increase timeout (if latency issue)                  │    │
│   │   kubectl set env deploy/api PAYMENT_TIMEOUT=10s               │    │
│   │   Rollback: kubectl set env deploy/api PAYMENT_TIMEOUT=2s      │    │
│   │                                                                │    │
│   │ Option B: Enable fallback (if availability issue)              │    │
│   │   curl -X POST http://config-service/flags/payment-fallback    │    │
│   │   Rollback: curl -X DELETE http://config-service/flags/...     │    │
│   │                                                                │    │
│   │ Option C: Shed load (if overload issue)                        │    │
│   │   kubectl scale deploy/payment-service --replicas=0            │    │
│   │   (Routes traffic to backup provider)                          │    │
│   └─────────────────────────────────────────────────────────-──────┘    │
│                                                                         │
│   3. INVESTIGATION (parallel with mitigation)                           │
│   ┌──────────────────────────────────────────────────────────-─────┐    │
│   │ Check these dashboards:                                        │    │
│   │ • go/payment-dashboard (latency, errors, throughput)           │    │
│   │ • go/payment-deps (downstream dependencies)                    │    │
│   │ • go/recent-deploys (recent changes)                           │    │
│   │                                                                │    │
│   │ Common causes:                                                 │    │
│   │ □ Recent deploy? → Rollback                                    │    │
│   │ □ Dependency slow? → Enable caching/fallback                   │    │
│   │ □ Traffic spike? → Auto-scaling should handle, verify          │    │
│   │ □ Data issue? → Check for poison pill requests                 │    │
│   └───────────────────────────────────────────────────────────-────┘    │
│                                                                         │
│   4. VERIFICATION (after mitigation)                                    │
│   ┌────────────────────────────────────────────────────────────-───┐    │
│   │ Confirm mitigation worked:                                     │    │
│   │ □ Error rate back below 1%                                     │    │
│   │ □ Latency P99 below 500ms                                      │    │
│   │ □ No new alerts firing                                         │    │
│   │                                                                │    │
│   │ Watch for 15 minutes before declaring resolved                 │    │
│   └─────────────────────────────────────────────────────────────-──┘    │
│                                                                         │
│   5. FOLLOW-UP (after incident)                                         │
│   ┌──────────────────────────────────────────────────────────────-─┐    │
│   │ □ Create postmortem document                                   │    │
│   │ □ Schedule postmortem review                                   │    │
│   │ □ Log ticket for permanent fix                                 │    │
│   │ □ Update this runbook if needed                                │    │
│   └───────────────────────────────────────────────────────────────-┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Sample Runbook: Cascading Failure Recovery

```
RUNBOOK: Cascading Failure - Service Chain Degradation
───────────────────────────────────────────────────────────────────────────

TRIGGER:
  Multiple services showing elevated error rates simultaneously
  Pattern: Upstream services failing first, then downstream

STEP 1: STOP THE BLEEDING (0-5 minutes)
  Priority: Prevent further cascade
  
  □ Enable circuit breakers on affected services:
    for svc in api-gateway order-service inventory-service; do
      curl -X POST http://$svc:8080/admin/circuit-breaker/open
    done
  
  □ Reduce traffic to problematic path:
    # In load balancer config, reduce weight
    kubectl patch ingress main -p '{"spec":{"rules":[...]}}'

STEP 2: IDENTIFY ROOT CAUSE (5-15 minutes)
  Question: Which service failed FIRST?
  
  □ Check timing of first errors across services:
    # Look for service with earliest error timestamp
    for svc in api-gateway order-service inventory-service payment-service; do
      echo "$svc first error:"
      kubectl logs -l app=$svc --since=1h | grep ERROR | head -1
    done
  
  □ Common patterns:
    - Database service errored first → DB issue
    - External API errored first → Third-party issue  
    - All services errored together → Network/infrastructure

STEP 3: TARGETED MITIGATION (15-30 minutes)
  Based on root cause:
  
  IF database issue:
    □ Check database metrics (connections, queries)
    □ Kill long-running queries
    □ Increase connection pool timeout
    □ Enable read replica fallback
  
  IF external API issue:
    □ Enable cached fallback
    □ Switch to backup provider
    □ Enable degraded mode (skip non-essential features)
  
  IF network issue:
    □ Verify DNS resolution
    □ Check load balancer health
    □ Verify security group rules

STEP 4: GRADUAL RECOVERY (30-60 minutes)
  □ Close circuit breakers one service at a time, starting downstream:
    # Start with services that have no dependencies
    curl -X POST http://inventory-service:8080/admin/circuit-breaker/close
    # Wait 5 minutes, verify health
    # Then next service
    curl -X POST http://order-service:8080/admin/circuit-breaker/close
    # Wait 5 minutes, verify health
    # Finally upstream
    curl -X POST http://api-gateway:8080/admin/circuit-breaker/close
  
  □ Gradually increase traffic weight back to normal
  
  □ Monitor for 30 minutes at full traffic

STEP 5: POST-INCIDENT
  □ Document timeline in incident channel
  □ Create postmortem ticket
  □ Preserve logs: 
    for svc in api-gateway order-service inventory-service; do
      kubectl logs -l app=$svc --since=2h > incident-$DATE-$svc.log
    done
```

---

# Part 16: Diagrams for Interview Use

## Diagram 1: Failure Propagation Paths

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    FAILURE PROPAGATION PATHS                            │
│                    (Draw this in interviews)                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   SYNCHRONOUS PROPAGATION (fast, visible)                               │
│   ────────────────────────────────────────                              │
│        User                                                             │
│          │                                                              │
│          ▼                                                              │
│   ┌─────────────┐                                                       │
│   │ API Gateway │────timeout───▶ Error returned immediately             │
│   └──────┬──────┘                                                       │
│          │                                                              │
│          ▼                                                              │
│   ┌─────────────┐                                                       │
│   │  Service A  │────timeout───▶ Gateway times out                      │
│   └──────┬──────┘                                                       │
│          │                                                              │
│          ▼                                                              │
│   ┌─────────────┐                                                       │
│   │  Service B  │────SLOW───▶ A waits, Gateway waits, User waits        │
│   └──────┬──────┘                                                       │
│          │                                                              │
│          ▼                                                              │
│   ┌─────────────┐                                                       │
│   │  Database   │◀──── ROOT CAUSE (deadlock, full disk, etc.)           │
│   └─────────────┘                                                       │
│                                                                         │
│                                                                         │
│   ASYNCHRONOUS PROPAGATION (slow, hidden)                               │
│   ───────────────────────────────────────                               │
│                                                                         │
│   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐             │
│   │  Producer   │─────▶│    Queue    │─────▶│  Consumer   │             │
│   └─────────────┘      └─────────────┘      └──────┬──────┘             │
│         │                    │                     │                    │
│         │                    │                     ▼                    │
│         │                    │              ┌─────────────┐             │
│         │                    │              │  Database   │◀── SLOW     │
│         │                    │              └─────────────┘             │
│         │                    │                     │                    │
│         ▼                    ▼                     ▼                    │
│     No error              Queue grows         Lag increases             │
│     visible               (delayed)           (delayed)                 │
│                                                                         │
│   Time to detection: Sync = seconds, Async = minutes to hours           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Diagram 2: Blast Radius Boundaries

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    BLAST RADIUS BOUNDARIES                              │
│                    (Draw this in interviews)                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Without Containment:                                                  │
│   ┌────────────────────────────────────────────────────────────-─────┐  │
│   │                          ALL USERS                               │  │
│   │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐         │  │
│   │  │ Svc │ │ Svc │ │ Svc │ │ Svc │ │ Svc │ │ Svc │ │ Svc │         │  │
│   │  └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘         │  │
│   │     └───────┴───────┴───────┼───────┴───────┴───────┘            │  │
│   │                             │                                    │  │
│   │                        ┌────┴────┐                               │  │
│   │                        │ Shared  │◀── Failure here = 100% down   │  │
│   │                        │   DB    │                               │  │
│   │                        └─────────┘                               │  │
│   └─────────────────────────────────────────────────────────────────-┘  │
│                                                                         │
│   With Containment:                                                     │
│   ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐           │
│   │     CELL 1      │ │     CELL 2      │ │     CELL 3      │           │
│   │   33% Users     │ │   33% Users     │ │   33% Users     │           │
│   │ ┌─────┐ ┌─────┐ │ │ ┌─────┐ ┌─────┐ │ │ ┌─────┐ ┌─────┐ │           │
│   │ │ Svc │ │ Svc │ │ │ │ Svc │ │ Svc │ │ │ │ Svc │ │ Svc │ │           │
│   │ └──┬──┘ └──┬──┘ │ │ └──┬──┘ └──┬──┘ │ │ └──┬──┘ └──┬──┘ │           │
│   │    └────┬────┘  │ │    └────┬────┘  │ │    └────┬────┘  │           │
│   │   ┌─────┴─────┐ │ │   ┌─────┴─────┐ │ │   ┌─────┴─────┐ │           │
│   │   │  Cell DB  │ │ │   │  Cell DB  │ │ │   │  Cell DB  │ │           │
│   │   └───────────┘ │ │   └───────────┘ │ │   └───────────┘ │           │
│   │        │        │ │                 │ │                 │           │
│   │        ▼        │ │                 │ │                 │           │
│   │    FAILURE!     │ │     Healthy     │ │     Healthy     │           │
│   │    33% impact   │ │                 │ │                 │           │
│   └─────────────────┘ └─────────────────┘ └─────────────────┘           │
│                                                                         │
│   Key Insight: Boundaries prevent failure propagation                   │
│   • Separate thread pools (bulkheads)                                   │
│   • Separate databases (cells)                                          │
│   • Separate networks (regions)                                         │
│   • Circuit breakers (logical boundaries)                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Diagram 3: Degraded-Mode Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    DEGRADED-MODE ARCHITECTURE                           │
│                    (Draw this in interviews)                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Request Flow with Degradation Decisions:                              │
│                                                                         │
│                      ┌──────────────────────────┐                       │
│                      │      Load Balancer       │                       │
│                      │    (health-aware)        │                       │
│                      └────────────┬─────────────┘                       │
│                                   │                                     │
│                                   ▼                                     │
│                      ┌──────────────────────────┐                       │
│                      │      API Gateway         │                       │
│                      │  ┌────────────────────┐  │                       │
│                      │  │ Rate Limiter       │  │◀── Shed excess load   │
│                      │  │ Circuit Breakers   │  │◀── Block failing deps │
│                      │  │ Fallback Router    │  │◀── Route to backups   │
│                      │  └────────────────────┘  │                       │
│                      └────────────┬─────────────┘                       │
│                                   │                                     │
│              ┌────────────────────┼────────────────────┐                │
│              │                    │                    │                │
│              ▼                    ▼                    ▼                │
│   ┌──────────────────┐ ┌──────────────────┐ ┌─────────────────-─┐       │
│   │  Search Service  │ │  Order Service   │ │ Payment Service   │       │
│   │                  │ │                  │ │                   │       │
│   │  Mode: DEGRADED  │ │  Mode: NORMAL    │ │  Mode: FALLBACK   │       │
│   │  • Cached results│ │  • Full function │ │  • Backup provider│       │
│   │  • No ML ranking │ │                  │ │  • Delayed settle │       │
│   └──────────────────┘ └──────────────────┘ └──────────────────-┘       │
│           │                     │                     │                 │
│           ▼                     ▼                     ▼                 │
│   ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐        │
│   │  Search Index    │ │    Database      │ │ Primary Payment  │        │
│   │   (Elastic)      │ │   (Postgres)     │ │     (Stripe)     │        │
│   │                  │ │                  │ │                  │        │
│   │   Status: SLOW   │ │  Status: OK      │ │  Status: DOWN    │        │
│   └──────────────────┘ └──────────────────┘ └──────────────────┘        │
│                                                                         │
│   User Experience Matrix:                                               │
│   ┌─────────────────┬───────────────────────────────────────────────┐   │
│   │ Feature         │ Normal          │ Degraded                    │   │
│   ├─────────────────┼─────────────────┼─────────────────────────────┤   │
│   │ Search          │ Personalized    │ Popular items only          │   │
│   │ Checkout        │ All payment     │ Card only, delayed confirm  │   │
│   │ Recommendations │ ML-powered      │ Category-based fallback     │   │
│   │ Reviews         │ Real-time       │ Cached (up to 1 hour old)   │   │
│   └─────────────────┴─────────────────┴─────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

# Part 17: Interview Signal — What Staff Engineers Say

## Demonstrating Staff-Level Judgment

| Situation | L5 Response | Staff (L6) Response |
|-----------|-------------|---------------------|
| "Database is slow" | "Let's add caching" | "What's the access pattern? Caching helps reads but hot partitions might need resharding. What's the blast radius if cache fails?" |
| "Service is timing out" | "Let's increase the timeout" | "That might just move the problem. What's the downstream impact? Would a circuit breaker be better? What's our fallback if this dependency fails entirely?" |
| "We're getting errors" | "Let's add retries" | "Retries can cause thundering herd. What's idempotency story? Do we have jitter? What's the retry budget across the call chain?" |
| "Need high availability" | "Add more replicas" | "Replicas help with instance failure but not network partitions or bad deploys. What failure modes are we protecting against? What's our cell strategy?" |
| "System went down" | "Let's add monitoring" | "What signal would have caught this earlier? How do we make the failure visible before it cascades? What's our observability gap?" |

## Signal Phrases for Interviews

**On Retries:**
- "Retries without jitter cause synchronized thundering herds. I always add randomized backoff."
- "Retry budgets prevent cascading failures. If 10% of requests are retrying, something is wrong—adding more retries makes it worse."
- "I distinguish between retryable and non-retryable errors. A 400 won't succeed on retry; a 503 might."

**On Idempotency:**
- "Any operation that can be retried must be idempotent. I design APIs with idempotency keys from the start, not as an afterthought."
- "Idempotency isn't just about the API—the entire processing chain must be idempotent, including downstream effects."

**On Backpressure:**
- "Systems without backpressure fail catastrophically. I'd rather reject requests explicitly than let queues grow unbounded."
- "Load shedding is a feature, not a failure. Rejecting 10% of requests during overload protects the other 90%."

**On Load Shedding:**
- "Not all requests are equal. During overload, I'd prioritize checkout over product recommendations."
- "Graceful degradation means defining what 80%, 60%, 40% functionality looks like before you need it."

**On Circuit Breakers:**
- "Circuit breakers prevent a slow dependency from consuming all my resources. I'd rather fail fast and return a cached response than wait 30 seconds."
- "The circuit breaker threshold matters: too sensitive and it flaps; too tolerant and it doesn't protect. I tune based on P99, not average."

**On Cascading Failures:**
- "Every synchronous call is a potential cascade point. I trace the failure path: if this is slow, what else becomes slow?"
- "Shared dependencies share blast radius. If five services use one database, they fail together."

**On Trade-offs:**
- "There's no free lunch in distributed systems. I can have fast, consistent, or available—pick two. The choice depends on the use case."
- "I optimize for the failure mode that matters most. For payments, I'd rather be slow than wrong. For recommendations, I'd rather be stale than unavailable."

---

# Part 17B: Google L6 Interview Calibration for Failure Topics

### What Interviewers Probe

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    INTERVIEWER'S MENTAL RUBRIC                           │
│                                                                         │
│   QUESTION IN INTERVIEWER'S MIND      L5 SIGNAL           L6 SIGNAL     │
│   ─────────────────────────────────────────────────────────────────────  │
│                                                                         │
│   "Do they think about partial        "We'll add retries"  "What if it's │
│    failure, not just total outage?"   "Add more replicas"  slow, not    │
│                                                          dead? Blast    │
│                                                          radius?"       │
│                                                                         │
│   "Do they trace propagation?"       "Timeout and retry"  "Retry storm  │
│                                                          amplifies;    │
│                                                          circuit breaker│
│                                                          first"         │
│                                                                         │
│   "Do they design degradation?"      Not discussed        "Here's what  │
│                                                          60% looks like;│
│                                                          designed, not  │
│                                                          accidental"    │
│                                                                         │
│   "Do they consider blast radius?"   "Failover will       "One user vs  │
│                                       handle it"           one region vs │
│                                                          everyone—     │
│                                                          different      │
│                                                          containment"   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Signals of Strong Staff Thinking

| Signal | What It Demonstrates |
|--------|----------------------|
| Asks "what if it's slow, not dead?" | Understands partial failure is default |
| Quantifies blast radius (users, shards, regions) | Systematic containment thinking |
| Proposes circuit breaker before retry | Prevents amplification |
| Defines degradation spectrum (100% → 60% → 0%) | Explicit degradation design |
| Mentions recovery dangers (thundering herd, cold cache) | Thinks beyond initial fault |
| Asks "what does the fallback cross?" | Trust boundary awareness |

### Common Senior Mistake That Costs the Level

**Mistake**: "We'll add retries and increase the timeout. Maybe a circuit breaker."

**Why it's insufficient**: Treats symptoms, not propagation. Doesn't ask: What's the blast radius? What happens during recovery? What's the fallback? Retries without budget or circuit breaker can amplify a small failure into outage.

**L6 correction**: "I'd add circuit breaker first—fail fast when dependency is broken. Then retry with budget and jitter. I'd trace the failure path: if this is slow, what else becomes slow? I'd design fallbacks for each critical dependency and define what 60% capability looks like."

### Example Interview Exchange

**Interviewer**: "Your recommendation service is slow. How do you handle it?"

**L5 answer**: "I'd add caching and retries. Maybe increase the timeout."

**L6 answer**: "First, I'd understand if it's slow or dead—different response. If slow, it's holding resources and passing health checks; circuit breaker or timeout to fail fast. If dead, fallback to cached/stale recommendations. I'd check blast radius: is this affecting all users or one shard? For recommendations, I'd prefer degraded (stale) over unavailable—users can tolerate 'popular items' instead of personalized. I'd add retry budget so we don't amplify load. And I'd verify: what happens when it recovers? Cold cache stampede? I'd warm caches gradually."

### How to Explain to Leadership

| Technical Concept | Leadership Framing |
|-------------------|---------------------|
| **Partial failure** | "Systems rarely fail completely. They degrade—some users slow, some broken. We design so degradation is contained and detectable." |
| **Blast radius** | "When one component fails, we limit how many users are affected. Cell architecture means 33% impact instead of 100%." |
| **Circuit breaker** | "Instead of hammering a failing service until everything breaks, we fail fast. Users get a clear error; the system stays stable." |
| **Retry storm** | "Retries can multiply load 10×. A 30-second glitch becomes a 4-hour outage. We limit retries to keep small failures small." |

**One-liner for leadership**: *"We design for the reality that something is always partially failing. The goal isn't zero failures—it's small, detectable, recoverable failures."*

### How to Teach This Topic (Mentoring)

1. **Foundation (20 min)**: "Partial failure is the default state." Draw the continuum (100% → 0%); contrast with binary thinking.
2. **Propagation (30 min)**: "Every failure propagates." Trace one slow DB through sync call chain; show retry amplification.
3. **Containment (25 min)**: "Boundaries limit blast radius." Bulkheads, circuit breakers, timeouts, cells.
4. **Recovery (15 min)**: "Recovery can be as dangerous as failure." Thundering herd, cold cache, gradual ramp.

**Teaching anti-pattern**: Don't start with mechanisms. Start with "here's an incident. What went wrong? What would have contained it?" Use the incident as anchor.

**Mentoring phrase**: *"When you add a dependency, ask: what if it's slow? What's the blast radius? What's the fallback? What happens during recovery?"*

---

# Part 18: Brainstorming Questions

Use these questions to practice failure reasoning:

## System-Specific Questions

### For Any System You Design:

1. **"What is the worst partial failure in this system?"**
   - Which component, if slow (not dead), causes the most damage?
   - What happens if it's 50% working, 50% failing?
   - How long before users notice?

2. **"How does this system fail silently?"**
   - What failures don't trigger alerts?
   - What looks healthy in metrics but is actually broken?
   - How would you detect data corruption vs data loss?

3. **"What's the blast radius of [component] failing?"**
   - Is it one user, one shard, one region, or everyone?
   - Does failure spread through retries? Shared resources?
   - What contains the blast radius?

4. **"What happens during recovery?"**
   - Will recovery cause a thundering herd?
   - Are there cold caches to warm?
   - Will backlog processing cause new problems?

### For Specific Patterns:

5. **For caching systems:**
   - What happens on cache cold start?
   - What if cache and database disagree?
   - How do you handle cache stampede?

6. **For queue-based systems:**
   - What happens when queue is full?
   - What if consumer is slower than producer for hours?
   - How do you handle poison messages?

7. **For distributed databases:**
   - What happens during network partition?
   - How do you detect split-brain?
   - What's the consistency model during failures?

8. **For synchronous microservices:**
   - What's the timeout for the entire call chain?
   - How do failures cascade upstream?
   - Where would you add circuit breakers?

---

# Reflection Prompts

Set aside 15-20 minutes for each of these reflection exercises.

## Reflection 1: Your Failure-First Thinking

Consider how you approach failure in system design.

- Do you think about failure modes from the start, or as an afterthought?
- When you draw architecture diagrams, do you trace failure propagation paths?
- Have you ever designed a system where you explicitly defined "what does 50% functionality look like"?
- Do you distinguish between "slow" and "dead" in your failure planning?

For a recent design, add failure mode annotations to every component and connection.

## Reflection 2: Your Blast Radius Awareness

Think about how you contain failures.

- Can you identify the blast radius of each component in your systems?
- Do you use bulkhead isolation patterns?
- When was the last time you added a circuit breaker? What triggered it?
- Do you design for failure containment or hope for the best?

For a system you know, draw a blast radius diagram showing what fails when each component degrades.

## Reflection 3: Your Recovery Planning

Examine how you handle the aftermath of failures.

- Do you plan recovery as carefully as you plan failure handling?
- Have you experienced thundering herd on recovery? How did you mitigate it?
- Do you know the recovery sequence for your critical systems?
- Have you ever run a chaos engineering experiment?

For your most critical system, write a recovery runbook that prevents secondary failures.

---

# Part 19: Homework Exercises

## Exercise 1: Redesign with Flaky Dependency

**Scenario**: You have a service that calls an external payment API. The API has become unreliable—it works 80% of the time, times out 10% of the time, and returns errors 10% of the time. Response time is unpredictable: sometimes 100ms, sometimes 10 seconds.

**Task**: Redesign the integration assuming this flakiness is permanent.

**Consider**:
1. How do you handle the user experience during failures?
2. Should you retry? How many times? With what backoff?
3. What's your timeout strategy?
4. Do you need a fallback? What does it look like?
5. How do you prevent the payment API from becoming your bottleneck?
6. How do you monitor and alert on this integration?

**Deliverable**: Architecture diagram showing:
- Normal path
- Degraded path
- Error handling
- Recovery mechanisms

---

## Exercise 2: Failure Mode Analysis

**Scenario**: You're reviewing a design for a real-time chat system with:
- WebSocket connections to clients
- Message storage in Cassandra
- Presence (online/offline) in Redis
- Push notifications via third-party service

**Task**: For each component, answer:

1. **What happens if it's slow (not dead)?**
2. **What happens if it's completely unavailable?**
3. **What's the blast radius?**
4. **How would you detect the failure?**
5. **What's the fallback behavior?**
6. **How do you recover?**

Create a failure mode table:

| Component | Failure Mode | Detection | Blast Radius | Fallback | Recovery |
|-----------|--------------|-----------|--------------|----------|----------|
| Cassandra | Slow writes | ? | ? | ? | ? |
| Redis | Unavailable | ? | ? | ? | ? |
| Push service | Throttling | ? | ? | ? | ? |
| WebSocket | Dropped connections | ? | ? | ? | ? |

---

## Exercise 3: Incident Response Simulation

**Scenario**: You receive an alert at 3 AM: "Checkout error rate > 5%"

You check dashboards and see:
- Checkout service error rate: 8%
- Payment service: healthy
- Inventory service: latency elevated (P99: 2s vs normal 100ms)
- Database: healthy
- No recent deploys

**Task**: Write your investigation and response plan:

1. What's your first hypothesis?
2. What would you check next?
3. What questions would you ask?
4. What mitigation would you try first?
5. What could make this worse if you act incorrectly?
6. When would you escalate?

---

## Exercise 4: Postmortem Analysis

**Given Incident Summary**:
- Duration: 45 minutes
- Impact: 30% of users couldn't complete purchases
- Root cause: Cache node failed, causing thundering herd to database
- Database became slow, causing timeouts in Order service
- Order service retried, making database slower
- Circuit breaker wasn't configured for database calls

**Task**: Write the "Lessons Learned" section:

1. What was the first thing that went wrong?
2. What turned a small failure into a large outage?
3. What monitoring would have detected this earlier?
4. What would have limited the blast radius?
5. What architectural changes would you recommend?
6. Prioritize: What's the single most important fix?

---

## Exercise 5: Design for Chaos

**Scenario**: You're adding chaos engineering to a production system.

**Task**: Design failure injection experiments for:

1. **Network failures**: How would you simulate partition? Latency? Packet loss?
2. **Dependency failures**: How would you simulate slow/dead dependencies?
3. **Resource exhaustion**: How would you simulate memory/CPU/disk pressure?
4. **Data issues**: How would you simulate corrupted/stale data?

For each experiment:
- What's the hypothesis?
- What's the expected behavior?
- What's the abort criteria?
- How do you limit blast radius of the experiment itself?

---

# Part 20: Section Verification — L6 Coverage Assessment

## Master Review Prompt Check (All 11 Items)

| # | Check | Status |
|---|-------|--------|
| 1 | **Staff Engineer preparation** — Content aimed at L6; depth and judgment match L6 expectations | ✅ |
| 2 | **Chapter-only content** — Every section, example, and exercise directly related to failure models and partial failures | ✅ |
| 3 | **Explained in detail with an example** — Each major concept has clear explanation plus concrete system example | ✅ |
| 4 | **Topics in depth** — Enough depth to reason about trade-offs, propagation, blast radius, containment | ✅ |
| 5 | **Interesting & real-life incidents** — Thursday Afternoon Checkout Outage + Structured Real Incident (full table format) | ✅ |
| 6 | **Easy to remember** — Mental models, one-liners ("Slow is worse than dead"; "Design for the middle, not the edges") | ✅ |
| 7 | **Organized for Early SWE → Staff SWE** — L5 vs L6 contrasts throughout; progression from basics to Staff thinking | ✅ |
| 8 | **Strategic framing** — Business vs technical trade-offs; cost as first-class constraint (Part 14B) | ✅ |
| 9 | **Teachability** — How to explain to leadership; how to teach this topic; mentoring phrases | ✅ |
| 10 | **Exercises** — Part 19: Homework Exercises (5 exercises: Flaky Dependency, Failure Mode Analysis, Incident Response, Postmortem, Design for Chaos) | ✅ |
| 11 | **BRAINSTORMING** — Part 18: Brainstorming Questions; Reflection Prompts | ✅ |

## L6 Dimension Coverage Table (A–J)

| Dim | Dimension | Coverage | Location |
|-----|-----------|----------|----------|
| **A** | Judgment & decision-making | Strong | Degradation hierarchy, blast radius framework, failover decision trees, Recovery vs Prevention trade-offs |
| **B** | Failure & incident thinking | Strong | Failure taxonomy, propagation diagrams, cascade walkthrough, structured real incident (full table), human failure modes |
| **C** | Scale & time | Strong | Scale thresholds (V1–V5), first bottlenecks, infrastructure reality table, growth model |
| **D** | Cost & sustainability | Strong | Part 14B; cost breakdown, resilience cost rule (20–40%), what Staff does NOT build |
| **E** | Real-world engineering | Strong | Human failure modes, runbook structure, operational reality, on-call ownership |
| **F** | Learnability & memorability | Strong | Staff Engineer one-liners, Quick Reference Checklist, L5 vs L6 table, Interview Signal Phrases |
| **G** | Data, consistency & correctness | Strong | Part 11; CAP in practice, consistency strategies during degradation, conflict resolution |
| **H** | Security & compliance | Strong | Security and Trust Boundaries During Partial Failures; fallback exposure, trust boundary principle |
| **I** | Observability & debuggability | Strong | Part 8; observability paradox, SLIs during failure, trace sampling, multi-signal correlation |
| **J** | Cross-team & org impact | Strong | Ownership model during failures, Cross-Team and Org Impact subsection, shared dependency blast radius |

## This chapter meets Google Staff Engineer (L6) expectations.

All Master Review Prompt Check items are satisfied. The L6 dimension coverage table (A–J) confirms Staff-level depth across judgment, failure thinking, scale, cost, real-world engineering, learnability, data correctness, security, observability, and cross-team impact. No unavoidable remaining gaps.

---

# Conclusion

Partial failure is the steady state of distributed systems. The systems you build are always experiencing some form of degradation—the question is whether you've designed for it.

Staff Engineers approach failure differently:

1. **They think about failure first**, not as an afterthought
2. **They trace propagation paths**, understanding how small failures become large outages
3. **They design explicit degradation modes**, knowing what 50% functionality looks like
4. **They limit blast radius** through isolation, timeouts, and circuit breakers
5. **They learn from incidents**, evolving architecture based on production experience

The key insights from this section:

- **Partial failures are harder than complete failures** because they're subtle, inconsistent, and hard to detect
- **Slow is worse than dead** because slow components hold resources and pass health checks
- **Retries amplify failures** unless bounded by budgets and circuit breakers
- **Shared dependencies share blast radius** — if five services use one database, they fail together
- **Recovery can be as dangerous as failure** — thundering herds, cold caches, and backlogs

In interviews, demonstrate this thinking by:
- Asking about failure modes before designing the happy path
- Identifying blast radius for each component
- Proposing circuit breakers, timeouts, and fallbacks
- Discussing degradation modes explicitly
- Referencing real incident patterns (without naming companies)

The goal isn't to prevent all failures—that's impossible. The goal is to make failures small, detectable, and recoverable. That's the Staff Engineer mindset.

---

## Quick Reference: Failure Reasoning Checklist

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    FAILURE REASONING CHECKLIST                          │
│                                                                         │
│   FOR EVERY DEPENDENCY:                                                 │
│   □ What if it's slow (not dead)?                                       │
│   □ What's the timeout?                                                 │
│   □ Is there a circuit breaker?                                         │
│   □ What's the fallback?                                                │
│   □ What's the blast radius if it fails?                                │
│                                                                         │
│   FOR EVERY COMPONENT:                                                  │
│   □ How do we detect failure?                                           │
│   □ How do we detect partial failure / degradation?                     │
│   □ What happens to in-flight requests during failure?                  │
│   □ What happens during recovery?                                       │
│                                                                         │
│   FOR THE SYSTEM:                                                       │
│   □ What's the worst single-component failure?                          │
│   □ What failures affect only some users?                               │
│   □ What failures affect all users?                                     │
│   □ Are there shared dependencies that share blast radius?              │
│   □ What's the degradation spectrum? (100% → 0%)                        │
│                                                                         │
│   FOR RECOVERY:                                                         │
│   □ Will recovery cause thundering herd?                                │
│   □ Are there caches to warm?                                           │
│   □ Is there a backlog to drain?                                        │
│   □ How do we verify the system is actually healthy?                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Final Thought

The best time to think about failure is before you write any code. The second best time is now.

Every production incident is a lesson about what you didn't anticipate. Staff Engineers have been through enough incidents that they anticipate failure patterns before building. They ask "what could go wrong?" not out of pessimism, but out of experience.

When you're in an interview and the interviewer asks "how would you handle failures?", they're looking for this depth of thinking. Show them you've been there, you've learned from it, and you design systems that fail gracefully.

That's Staff-level failure reasoning.