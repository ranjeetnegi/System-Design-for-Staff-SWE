# Section 5: Senior Software Engineer — Design Problems

---

## Overview

This section is the **practice arena**. After building the mindset (Section 1), learning the framework (Section 2), understanding distributed systems (Section 3), and studying data systems at scale (Section 4), you now apply everything to **13 complete system design problems** at the Senior Engineer level.

Each chapter takes a classic system design prompt and walks through it end-to-end: problem definition, requirements, capacity planning, architecture, deep dives into failure handling, and operational concerns. These are not toy sketches—they are production-grade designs with explicit trade-offs, realistic numbers, and honest discussion of what can go wrong.

The chapters in this section answer the fundamental question: **Can you design a real system from scratch, reason about its trade-offs, and operate it reliably at scale?**

---

## Who This Section Is For

- Senior Engineers (L5) preparing for system design interviews at Google or equivalent companies
- Engineers who want to practice applying the 5-Phase Framework (Section 2) to real problems
- Anyone looking for production-grade reference designs with explicit reasoning

**Prerequisites**: Sections 1–4 provide the conceptual foundation. You can jump directly into problems here, but you'll get the most value if you've internalized the framework and distributed systems concepts first.

---

## Section Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SECTION 5: DESIGN PROBLEMS                               │
│                                                                             │
│   ┌── Core Infrastructure ──────────────────────────────────────────────┐   │
│   │  Ch 28: URL Shortener                                               │   │
│   │  Ch 29: Single-Region Rate Limiter                                  │   │
│   │  Ch 30: Distributed Cache (Single Cluster)                          │   │
│   │  Ch 31: Object / File Storage System                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   ┌── Application Systems ──────────────────────────────────────────────┐   │
│   │  Ch 32: Notification System                                         │   │
│   │  Ch 33: Authentication System                                       │   │
│   │  Ch 34: Search System                                               │   │
│   │  Ch 35: Metrics Collection System                                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   ┌── Advanced Patterns ────────────────────────────────────────────────┐   │
│   │  Ch 36: Background Job Queue                                        │   │
│   │  Ch 37: Payment Flow                                                │   │
│   │  Ch 38: API Gateway                                                 │   │
│   │  Ch 39: Real-Time Chat                                              │   │
│   │  Ch 40: Configuration Management                                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Chapter Summaries

### Chapter 28: URL Shortener

**Core Question**: How do you design a deceptively simple system that must handle massive read-to-write ratios at scale?

**Key Concepts**:
- Unique short code generation strategies (counter-based, hash-based, pre-generated)
- Massive read-to-write ratio (~100:1) and its architectural implications
- Database sharding for key-value lookups
- Caching strategies for redirect performance
- Abuse prevention and link expiration

**Key Insight**: The URL shortener appears trivial but reveals how a candidate thinks about scale, reliability, and trade-offs. Start with the simplest design that works, then add complexity only where the problem demands it.

---

### Chapter 29: Single-Region Rate Limiter

**Core Question**: How do you protect APIs from abuse without degrading performance for legitimate users?

**Key Concepts**:
- Rate limiting algorithms (token bucket, sliding window, fixed window)
- Accuracy vs performance trade-offs in counting
- Distributed state management across multiple instances
- Failure behavior: fail-open vs fail-closed
- Latency impact—protection must be invisible to legitimate users

**Key Insight**: A rate limiter that adds 50ms of latency to every request has failed its mission. Protection should be invisible to legitimate users.

---

### Chapter 30: Distributed Cache (Single Cluster)

**Core Question**: How do you build a caching layer that actually improves performance without introducing consistency nightmares?

**Key Concepts**:
- Cache invalidation strategies (TTL, write-through, write-behind, event-driven)
- Consistency trade-offs between cache and source of truth
- Cache stampede prevention (locking, probabilistic early expiration)
- Memory management and eviction policies (LRU, LFU)
- Failure handling—what happens when the cache goes down

**Key Insight**: There are only two hard things in computer science—cache invalidation and naming things. The first one will cause production incidents.

---

### Chapter 31: Object / File Storage System (Single Cluster)

**Core Question**: How do you store arbitrary files with extreme durability guarantees and retrieve them reliably at scale?

**Key Concepts**:
- Data durability through replication and erasure coding
- Metadata management separate from data storage
- Consistency models for object operations
- Silent data corruption detection and repair
- Flat namespace design vs hierarchical file systems

**Key Insight**: Data durability is not a feature—it's a promise. Breaking that promise destroys trust permanently.

---

### Chapter 32: Notification System

**Core Question**: How do you deliver the right message, to the right user, on the right channel, at the right time—without overwhelming them?

**Key Concepts**:
- Multi-channel delivery (push, email, SMS, in-app)
- User preference management and do-not-disturb logic
- Delivery guarantees: at-least-once vs exactly-once semantics
- Deduplication and idempotency across channels
- Failure handling when downstream providers (email, SMS) are unreliable

**Key Insight**: Users trust notifications to be timely, relevant, and not duplicated. Violate any of these, and they disable notifications entirely—then you have no channel left.

---

### Chapter 33: Authentication System (AuthN)

**Core Question**: How do you build a front door that keeps attackers out while letting legitimate users in seamlessly?

**Key Concepts**:
- Token issuance, validation, and lifecycle (JWT, opaque tokens)
- Session management and secure credential storage
- Rate limiting login endpoints against credential-stuffing attacks
- Fail-closed design: if you can't verify identity, deny access
- Token revocation and session invalidation at scale

**Key Insight**: Authentication must fail closed. The difference between a secure system and a breached one is rarely a sophisticated zero-day—it's usually a misconfigured token expiry or a missing rate limit.

---

### Chapter 34: Search System (Single Cluster)

**Core Question**: How do you build a system that returns relevant results in under 200ms across millions of documents?

**Key Concepts**:
- Inverted index construction and maintenance
- Query parsing, tokenization, and analysis
- Ranking pipelines (TF-IDF, BM25, boosting)
- Index updates: real-time vs batch re-indexing
- Relevance tuning and the feedback loop

**Key Insight**: A search system that returns results fast but irrelevant is worse than one that's slow. Users tolerate 500ms; they don't tolerate garbage.

---

### Chapter 35: Metrics Collection System

**Core Question**: How do you build the system that monitors everything else—and keep it more reliable than what it monitors?

**Key Concepts**:
- Time-series data model (counters, gauges, histograms)
- High-throughput ingestion (millions of data points per second)
- Retention policies and downsampling for cost management
- Query patterns for dashboards and alerting
- Silent data loss detection—metrics that "look normal" but are missing data

**Key Insight**: The metrics system is the last system that should go down. If it's unreliable, every other system becomes unobservable.

---

### Chapter 36: Background Job Queue

**Core Question**: How do you reliably process deferred work at scale without losing jobs or silently failing?

**Key Concepts**:
- Job enqueueing, persistence, and dispatch to workers
- Retry policies and exponential backoff
- Poison-pill detection and dead-letter queues
- Priority scheduling and fair queueing
- Monitoring and visibility into job status and queue depth

**Key Insight**: A job queue must never silently lose work. If a job fails, that failure must be visible, retriable, and debuggable. Invisible failure is the worst kind of failure.

---

### Chapter 37: Payment Flow

**Core Question**: How do you move money correctly, exactly once, in a world of network partitions and ambiguous responses?

**Key Concepts**:
- Authorization → capture → ledger flow
- Idempotency as a first-class design concern
- Reconciliation between internal ledger and external processors
- Handling ambiguous gateway timeouts (the scariest failure mode)
- Refund processing and the ledger must always balance

**Key Insight**: Money must never be created or destroyed by a bug. A system that occasionally charges someone twice is catastrophic—because money is trust, and trust is non-recoverable.

---

### Chapter 38: API Gateway

**Core Question**: How do you build the single entry point to your entire system—one that must never become the bottleneck?

**Key Concepts**:
- Request routing to backend services
- Cross-cutting concerns: authentication, rate limiting, logging
- Request/response transformation and protocol translation
- Graceful degradation during backend failures
- Observability and the operational reality of shared infrastructure

**Key Insight**: If the gateway goes down or slows down, every service behind it is effectively down. Design it as the most reliable, most observable, and simplest component in your entire stack.

---

### Chapter 39: Real-Time Chat

**Core Question**: How do you deliver messages instantly, reliably, and in order to millions of concurrent users?

**Key Concepts**:
- WebSocket connection management at scale
- Message routing and fan-out (1:1 and group)
- Delivery guarantees: persist before acknowledge, order within conversation
- Presence tracking and reconnection storm handling
- Offline delivery via push notification fallback

**Key Insight**: Messages must never be lost, and they must never be delivered out of order within a conversation. Users tolerate 2 seconds of latency; they do not tolerate a missing message or a conversation where replies appear before questions.

---

### Chapter 40: Configuration Management

**Core Question**: How do you safely change production behavior without deploying code—when a single key-value change can take down your fleet?

**Key Concepts**:
- Config storage, versioning, and schema validation
- Propagation and convergence across thousands of instances
- Feature flags, staged rollouts, and percentage-based targeting
- Instant rollback mechanics
- Audit trails—every config change is a production deployment

**Key Insight**: Configuration is code that doesn't go through your CI/CD pipeline. If your config system doesn't have validation, staged rollout, instant rollback, and audit trails, you've built a loaded gun pointed at your production environment.

---

## How to Use This Section

1. **Pick a problem and time yourself**: Set a 45-minute timer and design the system from scratch before reading the chapter. This simulates interview conditions.
2. **Compare your design**: After your attempt, read through the chapter and compare. Focus on what you missed—failure modes, scale calculations, trade-offs you didn't consider.
3. **Practice with a partner**: Have someone play interviewer and probe your design. The chapters provide the depth needed for follow-up questions.
4. **Don't memorize designs**: Each chapter presents *one* valid design. In an interview, the specific design matters less than *how you arrive at it*. Focus on the reasoning, not the boxes.
5. **Revisit after Section 6**: The Staff-level versions of several of these problems (global rate limiter, distributed cache, etc.) appear in Section 6. Seeing the contrast illuminates the L5 → L6 shift.

---

## Key Themes Across All Chapters

### 1. Start Simple, Add Complexity With Justification

Every chapter begins with the simplest viable design and adds complexity only where the problem demands it. Over-engineering is a common failure mode in interviews.

### 2. Failure Handling Is Not an Afterthought

Each design explicitly addresses what happens when components fail. The "happy path" is table stakes; what distinguishes strong candidates is how they reason about unhappy paths.

### 3. Explicit Trade-offs Over Implicit Assumptions

Every architectural choice involves a trade-off. These chapters model the habit of stating what you're gaining, what you're giving up, and why that trade-off fits this context.

### 4. Operational Reality Matters

A design isn't complete until you've considered how to monitor it, how to debug it when things go wrong, and how to deploy changes without downtime. Production readiness separates Senior designs from junior ones.

### 5. Numbers Ground the Design

Capacity estimates, latency budgets, and storage calculations appear throughout. These aren't exercises in arithmetic—they're how you verify that your design actually works at the stated scale.

---

## Problem Categories

| Category | Chapters | Key Skills Tested |
|----------|----------|-------------------|
| **Core Infrastructure** | 28, 29, 30, 31 | Data modeling, sharding, caching, durability |
| **Application Systems** | 32, 33, 34, 35 | Multi-channel delivery, security, indexing, time-series |
| **Advanced Patterns** | 36, 37, 38, 39, 40 | Async processing, financial correctness, real-time delivery, dynamic config |

---

## Reading Time Estimates

| Chapter | Topic | Estimated Reading Time | Estimated Practice Time |
|---------|-------|----------------------|------------------------|
| Chapter 28 | URL Shortener | 60–90 minutes | 45 minutes design practice |
| Chapter 29 | Rate Limiter | 60–90 minutes | 45 minutes design practice |
| Chapter 30 | Distributed Cache | 60–90 minutes | 45 minutes design practice |
| Chapter 31 | Object Storage | 60–90 minutes | 45 minutes design practice |
| Chapter 32 | Notification System | 90–120 minutes | 60 minutes design practice |
| Chapter 33 | Authentication System | 60–90 minutes | 45 minutes design practice |
| Chapter 34 | Search System | 60–90 minutes | 45 minutes design practice |
| Chapter 35 | Metrics Collection | 60–90 minutes | 45 minutes design practice |
| Chapter 36 | Background Job Queue | 60–90 minutes | 45 minutes design practice |
| Chapter 37 | Payment Flow | 60–90 minutes | 60 minutes design practice |
| Chapter 38 | API Gateway | 60–90 minutes | 45 minutes design practice |
| Chapter 39 | Real-Time Chat | 60–90 minutes | 60 minutes design practice |
| Chapter 40 | Configuration Management | 60–90 minutes | 45 minutes design practice |

**Total Section**: ~16–22 hours reading + ~10–12 hours practice

---

## What's Next

After completing Section 5, you'll be ready for:

- **Section 6**: Staff-Level Design Problems — The same problem domains (rate limiting, caching, chat, payments, etc.) elevated to L6 scope: multi-region, cross-team, platform-level thinking. Comparing your Section 5 designs to Section 6 designs is one of the most effective ways to internalize the Senior → Staff shift.

---

*This section is where theory meets practice. Every concept from Sections 1–4 converges here into complete, production-grade system designs.*
