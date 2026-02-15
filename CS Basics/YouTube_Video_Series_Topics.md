# YouTube Video Series: 300+ Topics (Beginner → Staff-Level)

**Format:** 4–5 min per video · **Audience:** Absolute beginner to ~2 years experience · **Goal:** Long-term prep for Staff-level (L6) system design

**Total topics:** 320+

---

## How to Use This List

- **Order:** Watch in sequence for a clear learning path.
- **Levels:**  
  - **B** = Beginner (0–1 year)  
  - **I** = Intermediate (1–2 years)  
  - **S** = Senior / Staff track (2+ years, building toward L6)
- **SysDesignL6:** Chapter references point to your notes for deeper reading.

---

# PART 0: Absolute Basics (For Complete Beginners)

## 0.1 How Software & the Internet Work

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 1 | What is a "system" in software? | B | — |
| 2 | What is a server? What is a client? | B | — |
| 3 | What happens when you type a URL and press Enter? | B | — |
| 4 | What is a request and a response? | B | — |
| 5 | What is an API? (Plain English) | B | — |
| 6 | Frontend vs backend: what's the difference? | B | — |
| 7 | What is a database and why do we need it? | B | — |
| 8 | What is "scale" and why does it matter? | B | Ch 2, 10 |
| 9 | What is latency? Why does speed matter? | B | Ch 10 |
| 10 | What is a "service" or "microservice"? (High level) | B | Ch 3 |

## 0.2 Numbers Every Beginner Should Know

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 11 | Orders of magnitude: 1K, 1M, 1B | B | — |
| 12 | How to estimate: users, requests per second | B | Ch 10 |
| 13 | What is "QPS" or "throughput"? | B | Ch 10 |
| 14 | What does "99.9% availability" mean? | B | Ch 12 |
| 15 | How much can one server handle? (Rough numbers) | B | Ch 10 |

## 0.3 Basic CS Concepts (No Deep Theory)

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 16 | What is a process and a thread? | B | — |
| 17 | What is memory (RAM) and why it matters for servers | B | — |
| 18 | What is CPU and when does it become a bottleneck? | B | — |
| 19 | What is disk I/O and why it's slow | B | — |
| 20 | What is a hash function? (Simple intuition) | B | Ch 15, 30 |
| 21 | What is caching? (Everyday analogy) | B | Ch 22 |
| 22 | What is "state" vs "stateless"? | B | Ch 7, 38 |
| 23 | What is idempotency? (One simple example) | B | Ch 17 |
| 24 | What is a queue? (Real-world analogy) | B | Ch 18 |
| 25 | What is synchronous vs asynchronous? (Simple) | B | Ch 18 |

---

# PART 1: Networking Fundamentals

## 1.1 HTTP & Web Basics

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 26 | HTTP: What is a method (GET, POST, PUT, DELETE)? | B | Ch 28, 38 |
| 27 | HTTP status codes: 200, 404, 500 (what they mean) | B | — |
| 28 | What are HTTP headers and why they matter | B | Ch 38 |
| 29 | What is REST? (Simple explanation) | B | Ch 8, 48 |
| 30 | HTTP vs HTTPS: What is the difference? | B | Ch 38 |
| 31 | What is TLS/SSL? (Encryption in transit) | I | Ch 38, 52 |
| 32 | What is a reverse proxy? | I | Ch 38 |
| 33 | What is a load balancer? (Basic idea) | I | Ch 38, 48 |
| 34 | What is DNS and how does it work? | B | Ch 24, 48 |
| 35 | What is a CDN? (Content delivery in plain English) | I | Ch 22, 57 |

## 1.2 TCP/IP & Lower Layers

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 36 | TCP vs UDP: When to use which? | I | Ch 18 |
| 37 | What is a socket and a connection? | I | — |
| 38 | What is connection pooling and why use it? | I | Ch 38 |
| 39 | What is the OSI model? (7 layers overview) | I | — |
| 40 | What is bandwidth vs latency? | I | Ch 10 |
| 41 | What is Geo-DNS and when is it used? | S | Ch 24, 48 |
| 42 | What is Anycast routing? | S | Ch 24, 48 |

---

# PART 2: Data & Databases (Beginner to Intermediate)

## 2.1 Database Basics

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 43 | What is a relational database? (Tables, rows, columns) | B | Ch 21 |
| 44 | What is SQL? (SELECT, INSERT, UPDATE, DELETE) | B | Ch 21 |
| 45 | What is a primary key and an index? | B | Ch 21 |
| 46 | Why do we need indexes? Trade-offs | I | Ch 21 |
| 47 | What is a transaction? (ACID in plain English) | I | Ch 21, 37 |
| 48 | ACID: Atomicity explained | I | Ch 21 |
| 49 | ACID: Consistency explained | I | Ch 21 |
| 50 | ACID: Isolation and Durability | I | Ch 21 |
| 51 | When does a single database "run out"? | I | Ch 10, 21 |
| 52 | SQL vs NoSQL: When to use which? | I | Ch 21 |
| 53 | What is a key-value store? (Redis, DynamoDB style) | I | Ch 21, 30 |
| 54 | What is a document store? (MongoDB style) | I | Ch 21 |
| 55 | What is a search engine? (Elasticsearch style) | I | Ch 21, 34, 49 |
| 56 | OLTP vs OLAP: What's the difference? | I | Ch 21 |
| 57 | What is read replica? Why separate read and write? | I | Ch 15, 21 |
| 58 | What is database replication? (Leader-follower) | I | Ch 15 |
| 59 | Sync vs async replication: Trade-offs | I | Ch 15 |
| 60 | What is replication lag and why it matters? | I | Ch 15 |

## 2.2 Sharding & Partitioning

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 61 | What is sharding? (Splitting data across DBs) | I | Ch 15 |
| 62 | What is a partition key? How to choose one? | I | Ch 15, 43 |
| 63 | Hash-based sharding explained | I | Ch 15 |
| 64 | Range-based sharding explained | I | Ch 15 |
| 65 | What is consistent hashing? (Simple version) | I | Ch 15, 30 |
| 66 | What are hot partitions and hot keys? | I | Ch 10, 15 |
| 67 | How to handle hot keys: Caching, splitting, salting | S | Ch 10, 15, 21 |
| 68 | What is data skew and how to avoid it? | S | Ch 15, 43 |
| 69 | Denormalization: When and why? | I | Ch 21 |
| 70 | Multi-tenant data: How to isolate? | I | Ch 21, 49, 52 |

## 2.3 Storage Types & Data Lifecycle

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 71 | Block vs file vs object storage (high level) | I | Ch 31 |
| 72 | What is object storage? (S3-style) | I | Ch 31 |
| 73 | When to use object storage vs database | I | Ch 31 |
| 74 | Soft delete vs hard delete | I | Ch 25, 39 |
| 75 | Data retention and archival (basics) | I | Ch 25, 55 |
| 76 | Schema migration: Adding a column safely | I | Ch 27 |
| 77 | What is backfill and when do you need it? | I | Ch 27 |
| 78 | Data compression: Why and when (overview) | I | Ch 22, 46, 55 |

---

# PART 3: Caching (Full Arc)

## 3.1 Caching Concepts

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 79 | Why cache? Latency and load reduction | B | Ch 22 |
| 80 | Where to cache: Client, edge, server, DB layer | I | Ch 22, 42 |
| 81 | Cache-aside pattern (lazy loading) | I | Ch 22, 30 |
| 82 | Write-through cache | I | Ch 22, 30 |
| 83 | Write-back and write-around (when used) | I | Ch 22 |
| 84 | Cache invalidation: Why it's hard | I | Ch 22 |
| 85 | TTL (time-to-live): Simple invalidation | I | Ch 22 |
| 86 | Invalidate on write: When and how | I | Ch 22 |
| 87 | Cache eviction: LRU explained | I | Ch 22, 30 |
| 88 | Cache eviction: LFU and other policies | I | Ch 22 |
| 89 | What is cache stampede? (Thundering herd) | I | Ch 22, 30 |
| 90 | How to prevent cache stampede: Locking, jitter | I | Ch 22, 30 |
| 91 | Hot keys in cache: Replication, local cache | S | Ch 22, 42 |
| 92 | How to measure cache: Hit rate, miss rate | I | Ch 22, 42 |
| 93 | When caching hurts: Stale data, complexity | I | Ch 22 |
| 94 | Distributed cache: Redis cluster basics | I | Ch 30, 42 |
| 95 | CDN: How it works and when to use it | I | Ch 22, 57 |

---

# PART 4: APIs, Security & Rate Limiting

## 4.1 API Design

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 96 | What is an API endpoint? (REST basics) | B | Ch 8 |
| 97 | API versioning: Why and how (v1, v2) | I | Ch 3, 48 |
| 98 | API design: Idempotency for write APIs | I | Ch 17, 36 |
| 99 | How to evolve APIs without breaking clients | I | Ch 3, 47, 48 |
| 100 | Request IDs and tracing (why they matter) | I | Ch 38 |

## 4.2 Authentication & Authorization

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 101 | Authentication vs authorization (difference) | B | Ch 33, 52 |
| 102 | Session-based auth: How it works | I | Ch 33, 52 |
| 103 | Token-based auth: How it works | I | Ch 33, 52 |
| 104 | What is JWT? (Structure and use) | I | Ch 33, 38, 52 |
| 105 | OAuth 2.0: High-level flow | I | Ch 33, 52 |
| 106 | When to use session vs token | I | Ch 33, 52 |
| 107 | mTLS: Service-to-service auth | S | Ch 52 |

## 4.3 Rate Limiting & Protection

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 108 | Why rate limiting? Overload and abuse | B | Ch 29, 41 |
| 109 | Token bucket algorithm (simple) | I | Ch 29, 38 |
| 110 | Sliding window and fixed window | I | Ch 29, 38 |
| 111 | Rate limiting per user vs per IP vs global | I | Ch 48 |
| 112 | How to rate limit without hurting good users | I | Ch 29, 38, 48 |
| 113 | Distributed rate limiting: The challenge | S | Ch 41 |
| 114 | Protecting downstream services from spikes | I | Ch 29, 41, 48 |

---

# PART 5: System Design Framework (First Pass)

## 5.1 Thinking in Systems

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 115 | What is system design? (Interview and real world) | B | Ch 7 |
| 116 | Requirements first: Why clarify before designing | B | Ch 7, 8 |
| 117 | Functional vs non-functional requirements | B | Ch 9, 12 |
| 118 | Capacity estimation: Users, QPS, storage | I | Ch 10 |
| 119 | Back-of-the-envelope math (orders of magnitude) | I | Ch 10 |
| 120 | What breaks first at 2x, 10x, 100x scale? | I | Ch 10, 28, 30 |
| 121 | Single point of failure: How to avoid it | I | Ch 21, 42 |
| 122 | Vertical vs horizontal scaling: When which? | I | Ch 10, 21, 28 |
| 123 | When to split a monolith into services | I | Ch 3, 27 |
| 124 | Request flow: From user to DB and back | I | Ch 28, 38 |
| 125 | Sync vs async: When to use which in design | I | Ch 18 |
| 126 | Queue vs direct RPC: When to use which? | I | Ch 18 |
| 127 | Design for backpressure (high-level) | I | Ch 17, 18 |

---

# PART 6: Distributed Systems (Core Concepts)

## 6.1 Consistency & CAP

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 128 | What is consistency in distributed systems? | I | Ch 14 |
| 129 | Strong consistency vs eventual consistency | I | Ch 14, 19 |
| 130 | CAP theorem: What it says (simple) | I | Ch 14, 20 |
| 131 | CAP: Why you can't have all three | I | Ch 14, 20 |
| 132 | CP vs AP: How to choose in practice | S | Ch 14, 19, 20 |
| 133 | Consistency models: Linearizability, causal | S | Ch 14, 16 |
| 134 | Network partition: What happens when link fails? | I | Ch 19, 20 |
| 135 | Split-brain: What it is and why it's dangerous | S | Ch 19, 21, 24 |
| 136 | Quorum: Why majority matters | I | Ch 14, 16 |
| 137 | BASE (Basically Available, Soft state, Eventual) | I | Ch 14, 20 |

## 6.2 Replication & Consensus

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 138 | Leader-follower replication (detailed) | I | Ch 15 |
| 139 | Multi-leader replication: When and problems | S | Ch 15 |
| 140 | What is consensus? (Agreeing in distributed system) | I | Ch 16 |
| 141 | Paxos: Idea (not full proof) | S | Ch 16 |
| 142 | Raft: Leader election (simple) | I | Ch 16 |
| 143 | Raft: Log replication (simple) | I | Ch 16 |
| 144 | When to use Raft/Paxos (etcd, ZooKeeper) | S | Ch 16 |
| 145 | Leader election: Why and how | I | Ch 16 |
| 146 | Heartbeats: Detecting failures | I | Ch 16, 19, 53 |
| 147 | Gossip protocol: Epidemic spread of info | S | Ch 16, 38 |
| 148 | Clock sync in distributed systems: The problem | S | Ch 16 |
| 149 | Logical clocks: Lamport timestamps | S | Ch 16, 45 |
| 150 | Vector clocks: Detecting concurrent events | S | Ch 16 |

## 6.3 Transactions & Messaging

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 151 | Distributed transaction: Why it's hard | I | Ch 15, 21 |
| 152 | Two-phase commit (2PC): How it works | I | Ch 15, 16 |
| 153 | Why 2PC is painful in practice | I | Ch 15 |
| 154 | SAGA pattern: Idea and when to use | I | Ch 15, 23, 56 |
| 155 | SAGA: Choreography vs orchestration | S | Ch 23, 56 |
| 156 | Compensation in SAGA: Rolling back without 2PC | S | Ch 23, 56 |
| 157 | Outbox pattern: Reliable event publishing | I | Ch 18, 23, 40 |
| 158 | Inbox / idempotent consumer: Avoiding duplicates | I | Ch 18, 23 |
| 159 | Delivery semantics: At-most-once, at-least-once | I | Ch 18, 23 |
| 160 | "Exactly-once" is at-least-once + idempotency | I | Ch 18, 23 |
| 161 | Message queue vs log (Kafka-style): Difference | I | Ch 18 |
| 162 | When to use a queue vs a log vs a stream | I | Ch 18 |
| 163 | Change Data Capture (CDC): What and why | I | Ch 23, 34, 40 |
| 164 | Retries and exponential backoff | I | Ch 17 |
| 165 | Circuit breaker: Stop cascading failures | I | Ch 17, 19 |

---

# PART 7: Failure, Reliability & Availability

## 7.1 Failure Modes

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 166 | Availability vs reliability vs durability | I | Ch 12, 19 |
| 167 | Fault tolerance vs high availability | I | Ch 16, 19 |
| 168 | Partial failure: Why things fail in pieces | I | Ch 19 |
| 169 | Cascading failure: How one failure spreads | I | Ch 19 |
| 170 | Timeouts: Why set them and what value? | I | Ch 17, 38 |
| 171 | Health checks: Liveness vs readiness | I | Ch 38, 48 |
| 172 | Graceful degradation: What to shed first | S | Ch 44, 48, 49 |
| 173 | Load shedding: Dropping work to save the system | S | Ch 43, 44, 48 |
| 174 | Deadlock and how to avoid it (distributed) | I | Ch 16 |
| 175 | Distributed locks: When and how (Redis, etcd) | S | Ch 16 |

## 7.2 Multi-Region & Global

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 176 | Why multi-region? Latency and availability | I | Ch 24 |
| 177 | Active-passive vs active-active (high level) | I | Ch 24 |
| 178 | Cross-region replication: Challenges | S | Ch 24 |
| 179 | Data residency and compliance (GDPR-style) | I | Ch 25 |
| 180 | Failover and failback: Basics | I | Ch 24 |

---

# PART 8: Architecture Patterns & Styles

## 8.1 Service Architecture

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 181 | Monolith: When it's fine | B | Ch 3, 27 |
| 182 | Microservices: What and when to split | I | Ch 3, 11, 27 |
| 183 | Event-driven architecture: Overview | I | Ch 23 |
| 184 | Serverless: When and trade-offs | I | Ch 11, 53 |
| 185 | API gateway: What it does | I | Ch 38, 48 |
| 186 | API gateway: Auth, rate limit, route, proxy | I | Ch 38 |
| 187 | Service mesh: What problem it solves | S | Ch 38 |
| 188 | WebSockets: When to use for real-time | I | Ch 38, 39, 45 |
| 189 | Long polling vs WebSocket vs SSE | I | Ch 39, 45, 47 |
| 190 | Server-Sent Events (SSE): One-way push | I | Ch 38, 47 |

## 8.2 Data Flow & Pagination

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 191 | Cursor-based pagination vs offset | I | Ch 49 |
| 192 | Why offset pagination breaks at scale | I | Ch 49 |
| 193 | Event sourcing (high-level idea) | S | Ch 23 |
| 194 | CQRS: Command Query Responsibility Segregation (idea) | S | — |

---

# PART 9: Staff-Level Mindset & Interview

## 9.1 What Staff-Level Means

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 195 | L5 vs L6: What changes in system design? | S | Ch 1 |
| 196 | Scope: Not assigned, created by you | S | Ch 2 |
| 197 | Impact: Outcomes, not output | S | Ch 2 |
| 198 | Ownership: Beyond your code | S | Ch 2 |
| 199 | Trade-offs: Making them explicit | S | Ch 4, 5 |
| 200 | Designing under ambiguity | S | Ch 4, 6 |
| 201 | APIs as long-term contracts | S | Ch 3 |
| 202 | When to version, when to split services | S | Ch 3 |
| 203 | Cost as a first-class constraint | S | Ch 11, 26 |
| 204 | What to build vs what not to build | S | Ch 1, 7 |

## 9.2 Interview & Communication

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 205 | How Staff system design interviews are evaluated | S | Ch 1 |
| 206 | Driving the conversation (interview leadership) | S | Ch 6 |
| 207 | The 4-phase flow: Understand, High-level, Deep, Wrap-up | S | Ch 6 |
| 208 | Stating assumptions out loud | S | Ch 4, 6 |
| 209 | Defending your design under challenge | S | Ch 6 |
| 210 | Time management in a 45-min design | S | Ch 6 |
| 211 | Phrases that signal Staff-level thinking | S | Ch 6 |
| 212 | When to go deep vs when to stay high-level | S | Ch 6 |

---

# PART 10: Design Problems (Broken Into Topics)

*Each design can be 3–8 short videos: problem, requirements, high-level, key components, scale, failure, trade-offs.*

## 10.1 Classic Problems (Senior-Level)

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 213 | URL shortener: Problem and requirements | I | Ch 28 |
| 214 | URL shortener: High-level design and flow | I | Ch 28 |
| 215 | URL shortener: Scale and bottlenecks | I | Ch 28 |
| 216 | Rate limiter: Problem and algorithms | I | Ch 29 |
| 217 | Rate limiter: Single-region design | I | Ch 29 |
| 218 | Distributed cache: What and when | I | Ch 30 |
| 219 | Distributed cache: Sharding and consistent hashing | I | Ch 30 |
| 220 | Object storage: Durability and API | I | Ch 31 |
| 221 | Object storage: Scaling and cost | I | Ch 31 |
| 222 | Notification system: Channels and delivery | I | Ch 32 |
| 223 | Notification system: Queue and scaling | I | Ch 32 |
| 224 | Authentication system: Flows and tokens | I | Ch 33 |
| 225 | Search system: Index and query path | I | Ch 34 |
| 226 | Metrics pipeline: Ingestion and storage | I | Ch 35 |
| 227 | Background job queue: Enqueue, workers, retries | I | Ch 36 |
| 228 | Payment flow: ACID and idempotency | I | Ch 37 |
| 229 | API gateway: Pipeline and components | I | Ch 38 |
| 230 | Real-time chat: WebSocket and persistence | I | Ch 39 |
| 231 | Configuration management: Push vs pull | I | Ch 40 |

## 10.2 Staff-Level Problems (Deep Dives)

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 232 | Global rate limiter: Distributed counting | S | Ch 41 |
| 233 | Global rate limiter: Consistency vs latency | S | Ch 41 |
| 234 | Distributed cache at scale: Multi-region | S | Ch 42 |
| 235 | News feed: Fan-out, ranking, scale | S | Ch 43 |
| 236 | News feed: Backpressure and load shedding | S | Ch 43 |
| 237 | Real-time collaboration: CRDTs and ordering | S | Ch 44 |
| 238 | Messaging platform: Delivery and presence | S | Ch 45 |
| 239 | Messaging platform: Scale and WebSockets | S | Ch 45 |
| 240 | Metrics/observability: Cardinality and cost | S | Ch 46 |
| 241 | Config and feature flags: Propagation and safety | S | Ch 47 |
| 242 | API gateway at scale: Rate limit layers | S | Ch 48 |
| 243 | API gateway: Backpressure and failover | S | Ch 48 |
| 244 | Search system: Sharding and indexing | S | Ch 49 |
| 245 | Recommendation system: Data and ranking | S | Ch 50 |
| 246 | Notification fan-out: Scale and dedup | S | Ch 51 |
| 247 | Auth & authorization: mTLS and revocation | S | Ch 52 |
| 248 | Distributed scheduler: Heartbeats and guarantees | S | Ch 53 |
| 249 | A/B testing: Assignment and consistency | S | Ch 54 |
| 250 | Log aggregation: Tiering and compression | S | Ch 55 |
| 251 | Payment system: SAGA and compliance | S | Ch 56 |
| 252 | Media pipeline: Storage and transcoding | S | Ch 57 |

---

# PART 11: Deep Dives (One Concept = One Video)

## 11.1 Data & Storage Deep Dives

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 253 | B-tree index: Why databases use it | I | Ch 21 |
| 254 | Secondary indexes: Cost and use | I | Ch 21 |
| 255 | Write-ahead log (WAL): What and why | I | Ch 21 |
| 256 | MVCC: Multi-version concurrency (idea) | S | Ch 21 |
| 257 | Database connection pooling in practice | I | Ch 21, 38 |
| 258 | When to use NewSQL (Spanner, Cockroach) | S | Ch 21 |
| 259 | Time-series DB: Why different (Gorilla compression) | I | Ch 35, 46 |
| 260 | Inverted index: How search engines work | I | Ch 34, 49 |

## 11.2 Caching & CDN Deep Dives

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 261 | Cache key design: What to include | I | Ch 22 |
| 262 | Cache poisoning: How to prevent | I | Ch 22 |
| 263 | Stale reads: When acceptable | I | Ch 14, 22 |
| 264 | Edge caching: Cache control headers | I | Ch 22 |
| 265 | Redis persistence: RDB vs AOF | I | Ch 30 |
| 266 | Redis cluster: Slots and routing | I | Ch 30 |

## 11.3 Reliability & Ops

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 267 | Blue-green vs canary deployment | I | Ch 27, 48 |
| 268 | Feature flags: Safe rollout | I | Ch 47 |
| 269 | Runbooks and incident response | I | Ch 19 |
| 270 | Observability: Logs, metrics, traces | I | Ch 46 |
| 271 | SLO, SLI, error budget (basics) | I | Ch 12 |
| 272 | Capacity planning: How to do it | I | Ch 10, 11 |
| 273 | Cost modeling: Major drivers | I | Ch 11, 26 |
| 274 | Migration without downtime: Strategies | S | Ch 27 |
| 275 | Rollback: When and how | I | Ch 27 |

## 11.4 Security & Compliance

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 276 | Principle of least privilege | I | Ch 52 |
| 277 | Secrets management: Don't hardcode | I | Ch 47 |
| 278 | Encryption at rest vs in transit | I | Ch 25, 38 |
| 279 | Audit logging: What and why | I | Ch 25 |
| 280 | Data deletion and right to erasure | I | Ch 25 |

## 11.5 Kafka & Event Systems

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 281 | Kafka: Topic, partition, offset | I | Ch 18, 23 |
| 282 | Kafka consumer groups | I | Ch 18, 23 |
| 283 | Kafka: Ordering and partitioning key | I | Ch 18, 23 |
| 284 | Kafka retention and compaction | I | Ch 23 |
| 285 | Kafka exactly-once: Limits | I | Ch 18, 23 |
| 286 | When Kafka is overkill | I | Ch 23 |
| 287 | Pub/Sub vs Kafka: When which? | I | Ch 18, 23 |

## 11.6 More Staff-Level Nuances

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 288 | Replication lag: Monitoring and handling | S | Ch 15 |
| 289 | Cross-region consistency: The real trade-offs | S | Ch 20, 24 |
| 290 | When "eventually consistent" is not OK | S | Ch 14, 21 |
| 291 | Designing for partial failure (checklist) | S | Ch 19 |
| 292 | Organizational scaling: APIs and ownership | S | Ch 3 |
| 293 | Platform vs product team mindset | S | Ch 3 |
| 294 | Deprecation and migration of APIs | S | Ch 3, 27 |
| 295 | What interviewers probe at Staff level | S | Ch 1 |
| 296 | Rejecting the wrong solution (out loud) | S | Ch 6 |
| 297 | Scope creep in interviews: How to avoid | S | Ch 6 |
| 298 | Drawing and explaining in 2 minutes | S | Ch 6 |
| 299 | End of interview: What to say | S | Ch 6 |
| 300 | Learning path: From beginner to Staff (roadmap) | S | README |

---

# PART 12: Bonus Topics (Extend Beyond 300)

| # | Topic | Level | Notes ref |
|---|--------|--------|-----------|
| 301 | Three-phase commit (3PC): Why rarely used | S | — |
| 302 | OpenID Connect vs OAuth (identity layer) | I | — |
| 303 | gRPC vs REST: When to use which | I | Ch 48 |
| 304 | GraphQL: When it fits | I | — |
| 305 | Webhook vs polling | I | — |
| 306 | Idempotency keys: Client-generated | I | Ch 17, 36 |
| 307 | Deduplication windows in event systems | I | Ch 18, 51 |
| 308 | Redundant requests: When to dedupe | I | Ch 17 |
| 309 | Bulkheads: Isolating failure | S | Ch 19 |
| 310 | Chaos engineering: Why and how (intro) | S | — |
| 311 | Feature flags and experimentation (A/B) | I | Ch 54 |
| 312 | Data lineage and governance (intro) | I | Ch 25 |
| 313 | Multi-region failover: Decision process | S | Ch 24 |
| 314 | Cold start: Serverless and caches | I | Ch 53, 55 |
| 315 | Warm pool and pre-warming | I | — |
| 316 | Database read-your-writes consistency | S | Ch 14 |
| 317 | Monotonic reads and consistent prefix | S | Ch 14 |
| 318 | Hybrid Logical Clocks (HLC) (idea) | S | Ch 16 |
| 319 | CRDT: Conflict-free replicated data types (intro) | S | Ch 44 |
| 320 | Event sourcing vs event-driven (difference) | S | Ch 23 |

---

## Summary

| Part | Topic range | Approx. count |
|------|-------------|----------------|
| Part 0: Absolute basics | 1–25 | 25 |
| Part 1: Networking | 26–42 | 17 |
| Part 2: Data & databases | 43–78 | 36 |
| Part 3: Caching | 79–95 | 17 |
| Part 4: APIs & security | 96–114 | 19 |
| Part 5: System design framework | 115–127 | 13 |
| Part 6: Distributed systems | 128–165 | 38 |
| Part 7: Failure & availability | 166–180 | 15 |
| Part 8: Architecture patterns | 181–194 | 14 |
| Part 9: Staff mindset & interview | 195–212 | 18 |
| Part 10: Design problems | 213–252 | 40 |
| Part 11: Deep dives | 253–300 | 48 |
| Part 12: Bonus | 301–320 | 20 |

**Total: 320 topics** (each suitable for a 4–5 min video).

---

## Suggested Release Order

1. **Phase 1 (Beginner):** Part 0 → Part 1 → Part 2.1–2.2 → Part 3.1 → Part 4.1–4.2 → Part 5.1.  
2. **Phase 2 (Intermediate):** Part 2.3, 3.2, 4.3, 5 (rest), Part 6.1–6.2, Part 7, Part 8.  
3. **Phase 3 (Senior/Staff):** Part 6.3, Part 9, Part 10, Part 11, Part 12.  

You can also release by “tracks” (e.g. “Caching track”, “Distributed systems track”) for viewers who want to go deep in one area.

*Align with your SysDesignL6 notes: chapter references point to the relevant markdown files.*
