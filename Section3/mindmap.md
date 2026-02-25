# Section 3 — Distributed Systems: Mindmap

```
Section 3: Distributed Systems
│
├── Ch 20: Consistency Models
│   ├── Consistency Spectrum
│   │   ├── Linearizability — single global order (banking, config)
│   │   ├── Sequential — same order for all observers (queues)
│   │   ├── Causal — cause before effect (chat, comments)
│   │   ├── Read-your-writes — user sees own writes (profiles)
│   │   └── Eventual — eventually converge (feeds, analytics)
│   ├── Decision Heuristics
│   │   ├── Follow the money → strong
│   │   ├── Follow security → strong
│   │   ├── User expectation → would they notice staleness?
│   │   └── Read vs write load → read-heavy → eventual often OK
│   └── Cost Per 1M Ops (Cross-Region)
│       ├── Linearizable: $15–25
│       ├── Causal: $2–5
│       └── Eventual: $0.50–1.50
│
├── Ch 21: Replication & Sharding
│   ├── Scaling Path
│   │   └── Single node → replication → sharding
│   ├── Replication Models
│   │   ├── Leader–follower — simple, single source of truth
│   │   ├── Multi-leader — multi-region, offline, conflicts
│   │   └── Leaderless (quorum) — high availability, eventual
│   ├── Sync vs Async Replication
│   │   ├── Sync: durability, higher latency
│   │   ├── Async: lower latency, risk of data loss
│   │   └── Semi-sync: wait for one replica (common)
│   ├── Replication Lag Strategies
│   │   ├── Read-your-writes: route recent writers to primary
│   │   ├── Causal: logical/vector clocks
│   │   └── Monotonic reads: sticky routing
│   ├── Sharding Strategies
│   │   ├── Hash-based — even distribution, range queries hard
│   │   ├── Range-based — range queries easy, hot partitions
│   │   └── Directory-based — flexible, directory is bottleneck
│   ├── Hot Partitions
│   │   └── Celebrities, viral content → cache, split, dedicated infra
│   └── Cross-Shard Operations
│       ├── Joins → denormalize or materialized views
│       ├── Transactions → 2PC or Saga
│       └── Aggregations → precompute or fan-out
│
├── Ch 22: Leader Election, Coordination & Locks
│   ├── Coordination Hierarchy (prefer less)
│   │   ├── 1. No coordination — idempotency, CRDTs, partitioning
│   │   ├── 2. Leader election — single coordinator (Raft, etcd)
│   │   └── 3. Distributed locks — last resort
│   ├── Why Coordination is Hard
│   │   ├── Two Generals: no guaranteed agreement
│   │   ├── FLP: no deterministic consensus with 1 fault
│   │   └── Clock skew: NTP 10–100 ms
│   ├── Logical Clocks
│   │   ├── Lamport clocks — causal ordering
│   │   ├── Vector clocks — detect concurrency
│   │   ├── HLC — ordering + approximate real time
│   │   └── TrueTime — Spanner, GPS + atomic clocks
│   ├── Leader Election
│   │   ├── Lease-based: TTL, renewal, auto-failover
│   │   ├── Quorum-based: Raft voting
│   │   └── Failover window: 10–30 seconds
│   └── Distributed Locks
│       ├── Fencing tokens to avoid split-brain
│       ├── Lock TTL: 10–30 seconds
│       └── Timeouts + graceful degradation
│
├── Ch 23: Backpressure, Retries & Idempotency
│   ├── Stability Triangle
│   │   ├── Backpressure — slow producers when consumers overloaded
│   │   ├── Retries — controlled with backoff + jitter
│   │   └── Idempotency — safe retries without duplicates
│   ├── Retry Pitfalls
│   │   ├── Immediate retry → hammers failing service
│   │   ├── Fixed intervals → thundering herd
│   │   ├── Unbounded retries → never gives up
│   │   └── Retrying non-retryable errors (401/403)
│   ├── Retry Amplification
│   │   ├── 3 tiers × 3 retries = 27×
│   │   └── 5 tiers × 3 retries = 243×
│   ├── Correct Retry Pattern
│   │   ├── Exponential backoff + jitter
│   │   ├── Respect Retry-After
│   │   ├── Don't retry 4xx (except 429)
│   │   └── Circuit breakers during outages
│   ├── Idempotency
│   │   ├── Client-supplied idempotency keys
│   │   └── At-least-once + dedup = safe retries
│   └── Backpressure
│       ├── Pull > push for backpressure
│       ├── Load shedding: drop non-critical work
│       └── Graceful degradation: reduce features
│
├── Ch 24: Queues, Logs & Streams
│   ├── Three Models
│   │   ├── Queue — one consumer/msg, delete after (SQS, RabbitMQ)
│   │   ├── Log — append-only, multi-consumer, replay (Kafka)
│   │   └── Stream — continuous, time-windowed (Flink)
│   ├── Key Differences
│   │   ├── Replay: Queue=no, Log=yes, Stream=depends
│   │   ├── Consumers: competing vs independent vs continuous
│   │   └── Ordering: best-effort vs per-partition vs event-time
│   └── When to Use
│       ├── Queue: task distribution, load leveling
│       ├── Log: event sourcing, audit, replay, multi-consumer
│       └── Stream: real-time analytics, windowing
│
├── Ch 25: Failure Models & Partial Failures
│   ├── Partial Failure as Default
│   │   └── Systems are always partially failing
│   ├── Failure Types
│   │   ├── Process crash — restart storm, in-flight lost
│   │   ├── Network partition — hard vs soft
│   │   ├── Slow nodes — worse than dead, hold resources
│   │   └── Dependency failure — brownout, throttling
│   ├── Failure Propagation
│   │   └── Payment slow → Order stuck → Gateway stuck → Full outage
│   ├── Mitigations
│   │   └── Timeouts, circuit breakers, bulkheads
│   └── Degradation Hierarchy
│       └── Invisible → Cosmetic → Functional → Transactional → Critical
│
├── Ch 26: CAP Theorem — Applied
│   ├── CAP Reframed
│   │   ├── Normal: C + A + P all hold
│   │   └── During partition: choose C or A
│   ├── CP vs AP
│   │   ├── CP: errors/timeouts during partition (banking, inventory)
│   │   └── AP: stale/inconsistent data during partition (feeds, analytics)
│   ├── Misconceptions
│   │   ├── "CP means slower" — only during partition
│   │   ├── "We chose CA" — not possible in distributed systems
│   │   └── "P is optional" — P is always present
│   └── Partial Partitions
│       └── Harder than full; some paths work, some don't
│
└── Ch 26 Supplement: Advanced Topics
    ├── 3PC — adds pre-commit, but partitions break it
    ├── Read-Your-Writes — route recent writers to primary
    ├── Monotonic Reads — sticky routing, version-aware
    ├── HLC — physical + logical + node ID (CockroachDB)
    ├── CRDTs — merge without conflicts (G-Counter, OR-Set)
    │   └── Used in: Figma, Riak, collaborative editing
    └── Chaos Engineering
        ├── Define steady state → hypothesize → inject → observe → fix
        └── Blast radius: one instance → one AZ → one region
```
