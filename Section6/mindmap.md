# Section 6 — Staff Engineer Design Problems: Mindmap

```
Section 6: Staff (L6) Design Problems
│
├── Infrastructure & Scale
│   │
│   ├── Ch 55: Global Rate Limiter
│   │   ├── Protection over precision
│   │   ├── Algorithms: fixed/sliding window, token/leaky bucket
│   │   ├── Approximate counting often better than exact
│   │   ├── Partition by customer
│   │   ├── Fail open with degraded limits
│   │   ├── Avoid global consensus for limits
│   │   └── Failures: node crash, counter corruption, config down, partition
│   │
│   ├── Ch 56: Distributed Cache
│   │   ├── "A cache is a lie you tell the system"
│   │   ├── Edge cases: thundering herd, stampede, hot keys, negative caching
│   │   ├── Cache down → DB overload → cascading failure
│   │   ├── Cache failure degradation strategies
│   │   ├── Cache migration patterns
│   │   └── Cross-team ownership challenges
│   │
│   ├── Ch 60: Metrics / Observability System
│   │   ├── Time-series ingestion, storage, querying, alerting
│   │   ├── Cardinality limits
│   │   ├── Cost allocation per team/service
│   │   └── Multi-tenant isolation
│   │
│   ├── Ch 61: Configuration, Feature Flags & Secrets
│   │   ├── Runtime config + feature flags + secrets
│   │   ├── Propagation across thousands of instances
│   │   ├── Safety gates & validation
│   │   └── Blast-radius containment on bad config
│   │
│   └── Ch 62: API Gateway / Edge Request Routing
│       ├── Edge routing & request lifecycle
│       ├── Multi-region routing
│       ├── Failover strategies
│       └── Auth, rate limiting, observability at edge
│
├── Application & User-Facing Systems
│   │
│   ├── Ch 57: News Feed
│   │   ├── Feed storage, content cache, fan-out workers
│   │   ├── Celebrity index & celebrity problem
│   │   ├── Ranking pipeline
│   │   └── Multi-source retrieval at scale
│   │
│   ├── Ch 58: Real-Time Collaboration
│   │   ├── Real-time sync & conflict resolution
│   │   ├── Operational transforms / CRDTs
│   │   ├── Presence detection
│   │   └── Multi-user editing consistency
│   │
│   ├── Ch 59: Messaging Platform
│   │   ├── Message delivery, ordering, persistence
│   │   ├── Multi-device fan-out
│   │   ├── WebSocket management at scale
│   │   ├── Connection registry
│   │   └── Per-conversation ordering
│   │
│   ├── Ch 63: Search / Indexing System
│   │   ├── Inverted index at scale
│   │   ├── Multi-phase ranking pipeline
│   │   ├── Tiered freshness (real-time vs batch)
│   │   ├── Multi-tenancy
│   │   └── Graceful degradation under load
│   │
│   ├── Ch 64: Recommendation / Ranking System
│   │   ├── Candidate retrieval → scoring → re-ranking funnel
│   │   ├── Feature store
│   │   ├── Feedback loop & cold start
│   │   ├── Multi-source retrieval
│   │   └── Fallback stack when ML fails
│   │
│   ├── Ch 65: Notification Delivery (Fan-out at Scale)
│   │   ├── Priority isolation: P0 / P1 / P2 queues
│   │   ├── Celebrity fan-out
│   │   ├── Multi-channel routing
│   │   ├── Preference evaluation pipeline
│   │   └── Deduplication across channels
│   │
│   └── Ch 66: Authentication & Authorization
│       ├── Auth (identity) vs authorization (access)
│       ├── Short-lived tokens, local validation
│       ├── Token propagation & revocation
│       ├── Policy engine for authorization
│       └── mTLS for service-to-service
│
├── Platforms & Pipelines
│   │
│   ├── Ch 67: Distributed Scheduler / Job Orchestration
│   │   ├── Job scheduling & DAG orchestration
│   │   ├── Resource-aware placement
│   │   ├── State durability & liveness detection
│   │   ├── Multi-tenancy
│   │   └── Priority preemption
│   │
│   ├── Ch 68: Feature Experimentation / A/B Testing
│   │   ├── Hash-based assignment
│   │   ├── Interaction isolation between experiments
│   │   ├── Guardrails & safety metrics
│   │   ├── Statistical rigor: SRM detection, CUPED
│   │   └── Sequential testing
│   │
│   ├── Ch 69: Log Aggregation & Query System
│   │   ├── Write-heavy, read-sparse
│   │   ├── Hot / warm / cold storage tiers
│   │   ├── Inverted index for search
│   │   ├── Live tailing
│   │   └── Agent disk buffer for resilience
│   │
│   ├── Ch 70: Payment / Transaction Processing
│   │   ├── State machine for payment lifecycle
│   │   ├── Idempotency & double-entry ledger
│   │   ├── Processor failover
│   │   ├── Refund handling
│   │   ├── Reconciliation
│   │   └── PCI tokenization
│   │
│   └── Ch 71: Media Upload & Processing Pipeline
│       ├── Resumable chunked uploads
│       ├── Processing DAG
│       ├── Poison input isolation
│       ├── Tiered storage
│       ├── CDN-first serving
│       └── Per-stage retry
│
├── Ch 72: Bonus Advanced Topics
│   ├── OIDC vs OAuth — OAuth=authz, OIDC=identity (ID token)
│   ├── gRPC vs REST — gRPC for internal, REST for public
│   ├── GraphQL — client-specified queries, N+1, DataLoader
│   ├── Webhooks vs Polling — push vs pull, idempotency
│   ├── CQRS — separate write/read models, event sourcing
│   └── Warm Pools / Pre-warming — pre-provision, cache warming
│
└── Staff-Level Dimensions (applied in every chapter)
    ├── L5 vs L6 decision comparison
    ├── Concrete scale: QPS, storage, "what breaks first"
    ├── Deep failure treatment: partial, cascading, deployment
    ├── Cost breakdown & optimization levers
    ├── Data model & consistency
    ├── Evolution: V1 → V2 → V3, migration paths
    ├── Team ownership & operations
    ├── Organizational stress tests
    ├── Alternatives & explicit rejections
    └── Interview calibration
```
