# Section 0 — Fundamentals: Mindmap

```
Section 0: Fundamentals
│
├── Ch 1: Systems, Servers & Clients
│   ├── What is a System?
│   │   ├── Many components working together
│   │   ├── Servers, DBs, caches, queues, LBs, clients
│   │   └── Boundaries → ownership, failure modes, SLAs
│   ├── Application vs Service vs System
│   ├── Server & Client
│   │   ├── Server = process on a port
│   │   ├── Client = initiates requests
│   │   ├── Same process can be both
│   │   └── Deployment: bare metal → VM → container → serverless
│   ├── What Happens When You Type a URL
│   │   ├── DNS (0–100 ms)
│   │   ├── TCP 3-way handshake (1 RTT)
│   │   ├── TLS (1–2 RTT)
│   │   ├── HTTP request → server → response → render
│   │   └── 14 hops from keystroke to response
│   ├── Request & Response
│   │   ├── HTTP: method, URL, headers, body
│   │   ├── Sync vs async (webhooks, queues)
│   │   ├── HTTP/2 multiplexing, keep-alive
│   │   └── Request amplification / fan-out
│   │       └── e.g. Instagram: 1 user request → 15–30 internal
│   ├── Blast Radius
│   │   └── How much fails when a component fails
│   └── L5 vs L6 Thinking
│       ├── L5: component scope, retries
│       └── L6: system boundaries, degradation matrix, fan-out
│
├── Ch 2: APIs, Frontend, Backend & Databases
│   ├── APIs = Contracts
│   │   ├── REST: resources + HTTP methods
│   │   ├── Versioning: URL, header, query
│   │   ├── Backward compatibility & deprecation
│   │   ├── Internal vs external vs partner APIs
│   │   ├── Naming: resource URLs, not verbs
│   │   ├── Error format: code, message, details, request_id
│   │   ├── Pagination: cursor vs offset
│   │   └── Conway's Law — APIs as team boundaries
│   ├── Frontend vs Backend
│   │   ├── Frontend: UI, input, display
│   │   ├── Backend: logic, data, integrations, security
│   │   ├── BFF (Backend for Frontend)
│   │   ├── Thin vs thick client
│   │   └── Rendering: SSR, CSR, SSG, hydration
│   └── Databases
│       ├── Relational: tables, SQL, ACID, joins, indexes
│       ├── NoSQL: key-value, document, column-family, graph
│       ├── Selection: data shape → access pattern → consistency → scale → team
│       ├── Scaling: single DB → replicas → pooling → cache → sharding
│       └── Read/write ratio drives caching & replication
│
├── Ch 3: OS Fundamentals
│   ├── Processes & Threads
│   │   ├── Process: own address space, isolation
│   │   ├── Thread: shared memory, lightweight
│   │   ├── Context switch: ~1–10 μs + cache effects
│   │   ├── Thread-per-request vs event loop
│   │   ├── Goroutines, green threads, coroutines
│   │   └── C10K problem → event-driven I/O
│   ├── Memory (RAM)
│   │   ├── ~100 ns access, volatile
│   │   ├── Heap vs stack
│   │   ├── GC pauses → latency spikes
│   │   ├── Memory leaks: unbounded caches, listeners
│   │   └── Redis: in-memory, very fast
│   ├── CPU
│   │   ├── Most web servers: I/O-bound
│   │   ├── CPU-bound: video, ML, encryption, compression
│   │   └── Serialization, TLS, compression can dominate
│   └── Disk I/O
│       ├── HDD vs SSD (~100× difference random I/O)
│       ├── WAL: sequential writes for durability
│       └── IOPS vs throughput
│
├── Ch 4: Networking Foundations
│   ├── OSI Model (7 layers)
│   │   └── Practical focus: L4 (TCP/UDP), L7 (HTTP)
│   ├── TCP vs UDP
│   │   ├── TCP: reliable, ordered, 3-way handshake
│   │   ├── UDP: unreliable, low overhead
│   │   └── HTTP/3 (QUIC): UDP-based, per-stream reliability
│   ├── Sockets & Connections
│   │   ├── Socket = IP + port
│   │   ├── File descriptor limits (ulimit)
│   │   ├── Connection pooling & keep-alive
│   │   └── WebSocket: persistent bidirectional
│   ├── HTTP
│   │   ├── Methods: GET, POST, PUT, PATCH, DELETE
│   │   ├── Idempotency: GET/PUT/DELETE yes, POST needs keys
│   │   ├── Status codes: 2xx, 3xx, 4xx, 5xx
│   │   └── HTTP/1.1 vs HTTP/2 vs HTTP/3
│   └── Bandwidth vs Latency
│       ├── Small requests → latency dominates
│       ├── Large transfers → bandwidth dominates
│       └── CDN, Geo-DNS, Anycast → reduce latency
│
├── Ch 5: Numbers Every Engineer Must Know
│   ├── Orders of Magnitude
│   │   ├── 1K, 1M, 1B, 1T
│   │   └── Powers of 2: 2^10≈1K, 2^20≈1M, 2^30≈1B
│   ├── Scale Dimensions
│   │   ├── Users, requests, data, geography, team
│   │   ├── Vertical vs horizontal scaling
│   │   └── Inflection points: 100K, 1M, 10M, 100M users
│   ├── Latency
│   │   ├── L1: 0.5 ns | RAM: 100 ns | SSD: 16 μs | HDD: 2 ms
│   │   ├── p50 vs p99 — tail latency matters
│   │   ├── Tail amplification (sequential & parallel)
│   │   └── Latency budgets per hop
│   ├── QPS & Throughput
│   │   ├── QPS = DAU × actions/day ÷ 86,400
│   │   ├── Peak: 3–5× average
│   │   └── Internal QPS = user QPS × fan-out
│   ├── Availability
│   │   ├── 99.9% → 8.76 h/yr | 99.99% → 52.6 min/yr
│   │   ├── Serial: A × B × C
│   │   ├── Redundancy: 1 − (1−A)(1−B)
│   │   └── SLI → SLO → SLA → error budgets
│   └── Server Capacity
│       ├── Static: 10K–100K QPS
│       ├── API+DB: 100–1K QPS
│       └── Servers = total QPS ÷ per-server QPS + redundancy
│
└── Ch 6: Core Building Blocks
    ├── Hash Functions
    │   ├── Deterministic, fixed output
    │   ├── Types: MD5, SHA-256, xxHash, MurmurHash, bcrypt
    │   ├── Uses: hash tables, sharding, checksums, cache keys
    │   └── Consistent hashing: ring, virtual nodes, ~1/N key moves
    ├── Caching
    │   ├── Faster/smaller copy of hot data
    │   ├── Layers: browser, CDN, app, DB, CPU
    │   ├── Cache-aside: app manages, lazy loading
    │   ├── Invalidation: TTL, on-write, write-through, write-behind
    │   ├── Stampede: locking, probabilistic early expiry, background refresh
    │   └── Hot keys: replicate, local cache, shard
    ├── State vs Stateless
    │   ├── Stateful: sticky sessions, harder to scale
    │   ├── Stateless: horizontal scaling, external store
    │   └── JWT (stateless) vs session cookies (lookup)
    ├── Idempotency
    │   ├── Same effect when repeated
    │   ├── Idempotency keys for POST
    │   └── Prevents double charges on retry
    ├── Queues
    │   ├── Decouple producer & consumer
    │   ├── Types: FIFO, priority, DLQ, log (Kafka)
    │   ├── Delivery: at-most-once, at-least-once, exactly-once
    │   └── Patterns: fan-out, competing consumers, delay
    └── Sync vs Async
        ├── Sync: caller waits (login, checkout)
        ├── Async: caller continues (email, analytics)
        └── Sync facade: fast response, heavy work async
```
