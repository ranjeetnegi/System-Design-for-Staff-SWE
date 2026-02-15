# Section 0: Fundamentals — The Building Blocks of System Design

---

## Overview

This section covers the **foundational concepts** that ALL system design builds upon. Before frameworks, before distributed systems, before Staff-level thinking—you need the basics. What is a system? How do clients and servers communicate? What happens when you type a URL? How do you estimate scale, QPS, and availability? What are the core building blocks—hash functions, caching, state, idempotency, queues, sync and async?

These aren't "beginner" topics you outgrow. Staff Engineers who truly understand the basics make better architecture decisions. When you design a rate limiter, you're using hash functions and state. When you design a payment flow, you're using idempotency. When you design a notification system, you're using queues and async patterns. This section gives you the vocabulary, the numbers, and the mental models you'll use for every design that follows.

---

## Who This Section Is For

- **Engineers starting their system design journey** — Build the foundation before tackling distributed systems and complex designs
- **Experienced engineers refreshing fundamentals** — Revisit the basics with Staff-level depth
- **Interview candidates** — Solid fundamentals underpin every system design interview; weak basics show through
- **Anyone who wants to reason about scale** — Orders of magnitude, QPS, availability, and capacity estimation are universal

**Prerequisites**: None. This section assumes no prior system design knowledge. If you've built web applications or APIs, you'll recognize concepts—this section deepens and structures them.

---

## Section Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SECTION 0: LEARNING PATH                                  │
│                                                                             │
│   Chapter 1                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  SYSTEMS, SERVERS, AND CLIENTS                                       │   │
│   │  What is a system? Request/response. What happens when you type URL │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   Chapter 2                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  APIs, FRONTEND, BACKEND, AND DATABASES                              │   │
│   │  API contracts, BFF, rendering, data persistence, scaling data       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   Chapter 3                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  MICROSERVICES AND REQUEST FLOW                                       │   │
│   │  From monolith to services; tracing requests across the system       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   Chapter 4                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  DATABASES, SCALE, AND WHAT BREAKS                                    │   │
│   │  Single DB → replicas → sharding; inflection points at scale        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   Chapter 5                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  NUMBERS EVERY ENGINEER MUST KNOW                                     │   │
│   │  Orders of magnitude, scale, latency, QPS, availability, capacity   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   Chapter 6                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  CORE BUILDING BLOCKS                                                │   │
│   │  Hash, cache, state vs stateless, idempotency, queues, sync/async   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Chapter Summaries

### Chapter 1: Systems, Servers, and Clients — The Foundation of Everything

Every distributed system rests on the same foundation: systems composed of servers and clients exchanging requests and responses. This chapter defines what a "system" means, distinguishes servers from clients (and why the same process can be both), traces the full journey from typing a URL to rendered page, and shows how the request/response pattern scales—and breaks—in production. You'll learn system boundaries, the role of CDN/load balancer/reverse proxy, and how Staff Engineers think about the full request path.

---

### Chapter 2: APIs, Frontend, Backend, and Databases — The Building Blocks

APIs define how components communicate. The frontend is what users see; the backend does the work; the database persists data. This chapter covers APIs as contracts and organizational boundaries, the frontend/backend split (including BFF and rendering strategies), and databases as the hardest thing to scale. You'll learn when to use REST vs GraphQL, how read/write ratios drive architecture, and why Staff Engineers obsess over data modeling and query patterns.

---

### Chapter 3: Microservices and Request Flow

From monolith to services: when and why to split. This chapter covers request flow across multiple services, fan-out and amplification, and how a single user action can trigger many internal calls. You'll learn to trace requests through load balancers, API gateways, and downstream services—and why Staff Engineers model request amplification for capacity planning.

---

### Chapter 4: Databases, Scale, and What Breaks

Databases are usually the bottleneck. This chapter covers the progression: single database → read replicas → caching → sharding. What breaks at 1K users vs 1M vs 100M? When do you need each technique? You'll learn the inflection points, connection pooling, and why Staff Engineers plan the scaling path before hitting limits.

---

### Chapter 5: Numbers Every Engineer Must Know — Estimation, QPS, and Availability

Staff Engineers make architecture decisions based on rough numbers. This chapter gives you orders of magnitude (1K, 1M, 1B, 1T), data sizes (KB to PB), scale and what breaks at each level, latency numbers every programmer should know, QPS derivation from DAU, availability (the nines, composite availability, redundancy), and server capacity. Includes full worked examples for a URL shortener and chat system. By the end, you'll do back-of-the-envelope estimation with Staff-level fluency.

---

### Chapter 6: Core Building Blocks — Hash, Cache, State, Idempotency, Queues, Sync/Async

Every distributed system is built from a small set of primitives. This chapter covers: hash functions (including consistent hashing for distributed caches), caching (cache-aside, TTL, invalidation, stampede), state vs stateless (why stateless scales, where to put state), idempotency (why every write API should support retries, idempotency keys), queues (decoupling producer and consumer), and synchronous vs asynchronous patterns. Staff Engineers choose and combine these blocks with explicit trade-offs—this chapter gives you the depth to do the same.

---

## How to Use This Section

1. **Read sequentially if new to system design** — Chapters build on each other
2. **Skip to relevant chapters if experienced** — Use as reference; Chapters 5 and 6 are especially useful for interview prep
3. **Practice the numbers** — Chapter 5: derive QPS, storage, and capacity from DAU. Do it until it's automatic
4. **Apply the building blocks** — Chapter 6: when you design a system, ask which blocks you're using and why

---

## Key Themes Across All Chapters

### 1. Fundamentals Aren't Just for Beginners

Staff Engineers who truly understand the basics—what a request is, how scale manifests, what each building block does—make better architecture decisions. The basics compound. Weak fundamentals show up as vague designs and missed trade-offs.

### 2. Numbers Ground Design

"You need to scale" is not a design. "10M DAU × 20 requests/day = ~2.3K QPS average, ~9K peak" is. Numbers transform vague requirements into concrete architecture. Master the estimation formulas.

### 3. Every System Composes the Same Blocks

Hash, cache, state, idempotency, queues, sync/async—these appear in every design. The difference between systems is *how* these blocks are composed and *what trade-offs* are made. Learn the blocks; then learn to compose.

### 4. Boundaries and Ownership Matter

System boundaries, API boundaries, team boundaries—they're linked. Staff-level thinking connects technical design to organizational reality. Who owns the cache? Who owns the queue? Design includes ownership.

### 5. Failure Modes Are First-Class

What happens when the cache goes down? When a worker dies mid-processing? When a retry doubles a charge? Design for failure from the start. Idempotency, statelessness, and redundancy aren't afterthoughts.

---

## Quick Reference: Essential Numbers

| What | Value |
|------|-------|
| Seconds per day | 86,400 |
| 99.9% downtime/year | 8.76 hours |
| 99.99% downtime/year | 52.6 minutes |
| Same-DC RTT | ~0.5 ms |
| Cross-country RTT | ~40 ms |
| L1 cache | 0.5 ns |
| RAM | 100 ns |
| SSD random read | 16 μs |
| Peak / Average QPS | 3–5× |

---

## What's Next

After completing Section 0, you'll be ready for:

- **Section 1**: Staff Engineer Mindset & Evaluation — How Google evaluates L6, scope, impact, ownership, and the mindset shift from Senior to Staff
- **Section 2**: System Design Framework (5 Phases) — The repeatable methodology for approaching any system design problem
- **Section 3**: Distributed Systems — Consistency, replication, coordination, failure models
- **Section 4**: Data Systems & Global Scale — Advanced patterns for databases, caching, multi-region

Section 0 is the foundation. The frameworks and deep dives in later sections assume you can estimate scale, reason about availability, and recognize when to use a cache, a queue, or an idempotency key. Master the fundamentals; the rest builds on them.

---

## Reading Time Estimates

| Chapter | Topic | Estimated Reading Time |
|---------|-------|------------------------|
| Chapter 1 | Systems, Servers, Clients | 60–90 minutes |
| Chapter 2 | APIs, Frontend, Backend, DB | 60–90 minutes |
| Chapter 3 | Microservices, Request Flow | 45–60 minutes |
| Chapter 4 | Databases, Scale, What Breaks | 45–60 minutes |
| Chapter 5 | Numbers, Estimation, QPS, Availability | 75–100 minutes |
| Chapter 6 | Core Building Blocks | 75–100 minutes |

**Total Section**: ~7–10 hours of focused reading

---

*This section lays the foundation. Every system design you encounter will use these concepts. Internalize them.*
