# Section 4 — Data Systems & Global Scale: Mindmap

```
Section 4: Data Systems & Global Scale
│
├── Ch 28: Databases — Choosing, Using & Evolving
│   ├── Decision Framework
│   │   └── Data shape → access patterns → consistency → scale → team
│   ├── "SQL vs NoSQL" Is the Wrong Question
│   │   └── Access patterns and constraints matter more
│   ├── Data Shapes
│   │   ├── Structured (relational)
│   │   ├── Semi-structured (documents)
│   │   ├── Unstructured (blobs)
│   │   └── Time-series
│   ├── Access Patterns
│   │   ├── Point lookups, range scans, joins
│   │   ├── Aggregations, full-text search, graph traversal
│   │   └── Read/write flows & failure points
│   ├── Polyglot Persistence
│   │   └── Multiple stores, keeping them in sync
│   ├── Migration Paths (10K → 10M users)
│   └── Supplement: DB Internals
│       ├── B-Tree / B+ Tree — high branching, fewer disk reads
│       ├── Secondary Indexes — write amplification, covering indexes
│       ├── WAL — sequential writes, crash recovery, replication
│       ├── MVCC — readers/writers don't block, snapshots, VACUUM
│       ├── Connection Pooling — Little's Law, PgBouncer
│       └── NewSQL — Spanner, CockroachDB, TiDB, YugabyteDB
│           └── SQL + horizontal scale + strong consistency
│
├── Ch 31: Caching at Scale
│   ├── Three Reasons to Cache
│   │   ├── Protection (absorb spikes)
│   │   ├── Cost (cheaper than DB)
│   │   └── Latency
│   ├── Five Questions Before Adding Cache
│   │   ├── Cold start? Failure mode? Staleness?
│   │   └── Invalidation? Operational cost?
│   ├── Cache Invariants
│   │   ├── No cross-user data leakage
│   │   └── Stale permissions never grant access
│   ├── Cache Layers
│   │   ├── Application (in-process)
│   │   ├── Distributed (Redis / Memcached)
│   │   ├── CDN
│   │   └── Edge
│   ├── Failure Patterns
│   │   ├── Stampede / thundering herd
│   │   ├── Cold-start amplification
│   │   └── Cache down → DB overload → cascading failure
│   ├── Redis vs Memcached
│   └── Supplement: Redis & Cache Internals
│       ├── Key Design — resource type + ID + variant, namespacing
│       ├── Cache Poisoning — wrong data persists until TTL
│       ├── Redis Persistence — RDB snapshots, AOF, hybrid
│       ├── Redis Cluster — 16,384 hash slots, MOVED/ASK
│       ├── Time-Series DB — append-only, delta compression
│       └── Inverted Index — term → posting list, TF-IDF, BM25
│
├── Ch 33: Event-Driven Architectures
│   ├── Temporal Coupling
│   │   └── Events decouple producers & consumers in time
│   ├── When Events Help
│   │   ├── Fan-out, buffering spikes
│   │   ├── Failure isolation, replay
│   │   └── Multiple independent consumers
│   ├── When Events Hurt
│   │   ├── Simple request/response
│   │   ├── Transactions, low latency
│   │   └── Debugging & observability
│   ├── Decoupling Myth
│   │   └── Schema, semantics, ordering, ops coupling remain
│   ├── Event Types
│   │   ├── Event sourcing
│   │   ├── Notification
│   │   └── Event-carried state transfer
│   └── Supplement: Kafka Internals
│       ├── Topics, Partitions, Offsets
│       │   └── Partitions = parallelism ceiling
│       ├── Consumer Groups — 1 consumer/partition/group
│       ├── Ordering — only within partition, partition by entity ID
│       ├── Retention & Compaction — time/size-based, log compaction
│       ├── Exactly-Once — inside Kafka only, need idempotent external writes
│       ├── When Kafka Is Overkill → SQS or simpler
│       └── Pub/Sub vs Kafka — push/no-replay vs pull/replay
│
├── Ch 36: Multi-Region Systems
│   ├── Multi-Region = Consistency Choice
│   │   └── Not only availability
│   ├── Three Definitions
│   │   ├── Multi-region deployment (compute)
│   │   ├── Multi-region data (replicated state)
│   │   └── Active-active
│   ├── Physics
│   │   └── Latency 50–200 ms, partitions, clock skew
│   ├── Topologies
│   │   ├── Active-active
│   │   ├── Active-passive
│   │   └── Read-local / write-global
│   ├── Replication Lag & User-Visible Effects
│   ├── Regional Failover — danger of untested failover
│   └── When Single-Region + Good DR Is Enough
│
├── Ch 37: Data Locality, Compliance & Evolution
│   ├── Three Data Layers
│   │   ├── Data at rest
│   │   ├── Data in transit
│   │   └── Derived data
│   ├── Compliance Failures in
│   │   └── Logs, caches, analytics, backups (not just primary DB)
│   ├── GDPR, Data Residency, Right-to-Deletion
│   ├── Deletion Manifest
│   │   └── "Deleted from DB" ≠ "deleted everywhere"
│   └── Cost of Retrofitting vs Designing In (often 10×)
│
├── Ch 38: Cost, Efficiency & Sustainability
│   ├── Cost as Design Constraint
│   ├── Five Dimensions
│   │   ├── Compute, storage, network, ops, engineering
│   ├── Cost Cliffs & Hidden O(n²) Costs
│   ├── Cost of Each Extra "Nine"
│   └── When Over-Provisioning Is Cheaper Than Optimization
│
├── Ch 39: System Evolution & Migration
│   ├── Evolution as Default
│   ├── Why Migrations Fail
│   │   ├── Incomplete understanding
│   │   ├── Data inconsistency
│   │   ├── Performance regression
│   │   └── Impossible rollback
│   ├── Reversible vs One-Way-Door Decisions
│   ├── Migration Patterns
│   │   ├── Strangler fig
│   │   ├── Dual-write
│   │   ├── Shadow traffic
│   │   └── Expand-contract
│   └── Designing for Change
│       └── Seams, abstractions, version contracts
│
└── Ch 39 Supplement: Deployment & Operations
    ├── Blue-Green Deployment
    │   └── Two environments, instant rollback, double cost
    ├── Canary Deployment
    │   └── 1–5% traffic, automated analysis (Kayenta)
    ├── Runbooks & Incident Response
    │   └── Detect → Triage → Mitigate → Root Cause → Fix → Postmortem
    ├── Observability
    │   └── Logs (what?) + Metrics (how bad?) + Traces (where?)
    ├── SLO, SLI, Error Budget
    │   └── Error budget = 100% − SLO = permission to fail
    ├── Capacity Planning
    │   └── Measure → model → scale at 70–80%
    └── Rollback Strategies
        └── Roll back vs fix forward; schema backward compatibility
```
