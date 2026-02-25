# Section 5 — Senior Design Problems: Mindmap

```
Section 5: Senior (L5) Design Problems
│
├── Core Infrastructure (Ch 34–37)
│   │
│   ├── Ch 34: URL Shortener
│   │   ├── Key-value store, read-heavy (~100:1 read/write)
│   │   ├── Short Code Generation
│   │   │   ├── Counter-based
│   │   │   ├── Hash-based
│   │   │   ├── Pre-generated
│   │   │   └── Hybrid: counter + shuffling
│   │   ├── Write: validate → generate code → store
│   │   ├── Read: extract code → cache → DB → cache populate → redirect
│   │   ├── Sharding for key-value lookups
│   │   ├── Caching for redirects
│   │   └── Abuse prevention
│   │
│   ├── Ch 35: Single-Region Rate Limiter
│   │   ├── Algorithms
│   │   │   ├── Fixed window
│   │   │   ├── Sliding window log
│   │   │   ├── Sliding window counter (recommended)
│   │   │   └── Token bucket
│   │   ├── Accuracy vs performance trade-off
│   │   ├── Distributed state via Redis + Lua
│   │   ├── Fail-open vs fail-closed
│   │   ├── Rate limiter as library, not service
│   │   └── Headers: X-RateLimit-Limit, Remaining, Reset, Retry-After
│   │
│   ├── Ch 36: Distributed Cache (Single Cluster)
│   │   ├── Cache Patterns
│   │   │   ├── Read-through: miss → DB → populate
│   │   │   ├── Write-through: update DB + cache together
│   │   │   ├── Write-behind: cache first, async DB
│   │   │   └── Cache-aside: delete on update
│   │   ├── Invalidation: TTL, event-driven
│   │   ├── Stampede prevention: locking, probabilistic early expiry
│   │   ├── Eviction: LRU, LFU
│   │   └── Cache-down failure handling
│   │
│   └── Ch 37: Object / File Storage
│       ├── Durability via replication + erasure coding
│       ├── Metadata vs data storage (separate)
│       ├── Operations: PUT, GET, DELETE, LIST
│       ├── Range requests (streaming, resumable downloads)
│       ├── Silent data corruption detection
│       └── Durability target: 11 nines
│
├── Application Systems (Ch 38–41)
│   │
│   ├── Ch 38: Notification System
│   │   ├── Channels: push, email, SMS, in-app
│   │   ├── User preferences & do-not-disturb
│   │   ├── Delivery: at-least-once + deduplication
│   │   ├── Idempotency keys (e.g. payment:transaction_id)
│   │   ├── Channel priority & fallback chains
│   │   └── Centralized system vs per-service delivery
│   │
│   ├── Ch 39: Authentication System (AuthN)
│   │   ├── Fail closed — deny if can't verify
│   │   ├── Token lifecycle: issue → validate → refresh → revoke
│   │   ├── Access token (short-lived, 15 min) + refresh token
│   │   ├── JWT validation without DB lookup
│   │   ├── Secure credential storage (bcrypt)
│   │   └── Rate limiting on login (prevent credential stuffing)
│   │
│   ├── Ch 40: Search System (Single Cluster)
│   │   ├── Inverted index: token → doc IDs
│   │   ├── Query parsing, tokenization, analysis
│   │   ├── Ranking: TF-IDF, BM25, boosting
│   │   ├── Near-real-time (NRT) indexing
│   │   ├── Autocomplete & faceted search
│   │   └── Relevance tuning & feedback
│   │
│   └── Ch 41: Metrics Collection System
│       ├── Time-series: counters, gauges, histograms
│       ├── High-throughput ingestion (millions of points/sec)
│       ├── Write: emit → scrape → ingest → store
│       ├── Retention & downsampling
│       │   └── 15s (recent) → 5m (medium) → 1h (long-term)
│       ├── Query: dashboards + alert evaluation
│       └── Last system that should go down
│
└── Advanced Patterns (Ch 42–46)
    │
    ├── Ch 42: Background Job Queue
    │   ├── Enqueue → persist → dispatch → execute
    │   ├── Retry: exponential backoff with jitter
    │   ├── Lease-based visibility: no ACK → re-dispatch
    │   ├── Poison-pill detection → DLQ
    │   ├── Priority scheduling & fair queueing
    │   └── Never silently lose work
    │
    ├── Ch 43: Payment Flow
    │   ├── Flow: authorize → capture → ledger
    │   ├── Idempotency keys — first-class concern
    │   │   └── Deterministic, never timestamps or random
    │   ├── Timeout = UNKNOWN, not FAILED
    │   ├── Internal ledger = source of truth
    │   ├── Double-entry: sum(debits) = sum(credits)
    │   ├── Reconciliation: internal vs processor
    │   └── Money must never be created or destroyed by a bug
    │
    ├── Ch 44: API Gateway
    │   ├── Request routing to backends
    │   ├── Cross-cutting: auth, rate limiting, logging
    │   ├── Request/response transformation
    │   ├── Graceful degradation on backend failure
    │   └── Must never become the bottleneck
    │
    ├── Ch 45: Real-Time Chat
    │   ├── WebSocket connection management at scale
    │   ├── Connection registry: user_id → connections
    │   ├── Message routing: 1:1 and group fan-out
    │   ├── Delivery: persist before acknowledge
    │   ├── Per-conversation sequence numbers for ordering
    │   ├── At-least-once + client-side dedup
    │   ├── Offline delivery via push notification
    │   └── Reconnection storm handling
    │
    └── Ch 46: Configuration Management
        ├── Config change = production deployment
        ├── Storage, versioning, schema validation
        ├── Propagation: push + local cache (15s convergence)
        ├── Feature flags & staged rollouts
        ├── Instant rollback
        ├── Kill switches for emergencies
        └── Audit trail for every change
```
