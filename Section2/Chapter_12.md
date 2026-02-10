# Chapter 10: Phase 4 & Phase 5 — Non-Functional Requirements, Assumptions, and Constraints

---

# Quick Visual: NFRs Drive Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      NFRs DRIVE ARCHITECTURE                                │
│                                                                             │
│   Same functional requirements, different NFRs = DIFFERENT systems          │
│                                                                             │
│   ┌─────────────────────────────┐    ┌─────────────────────────────-┐       │
│   │  SYSTEM A (Basic)           │    │  SYSTEM B (High-Performance) │       │
│   │  • 99% availability         │    │  • 99.99% availability       │       │
│   │  • 5-second latency         │    │  • 100ms latency             │       │
│   │  • Eventual consistency     │    │  • Strong consistency        │       │
│   ├─────────────────────────────┤    ├─────────────────────────────-┤       │
│   │  Result:                    │    │  Result:                     │       │
│   │  • Single region            │    │  • Multi-region active-active│       │
│   │  • Basic backup             │    │  • Full redundancy           │       │
│   │  • Simple, async processing │    │  • Sync, guaranteed delivery │       │
│   │  • Cost: $                  │    │  • Cost: $$$$                │       │
│   └─────────────────────────────┘    └────────────────────────────-─┘       │
│                                                                             │
│   KEY: Establish NFRs BEFORE designing. They determine your architecture.   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Simple Example: Senior vs Staff NFR Thinking

| Aspect | Senior (L5) Approach | Staff (L6) Approach |
|--------|---------------------|---------------------|
| **Asking about NFRs** | Doesn't ask, assumes | "What availability? What latency budget?" |
| **Quantification** | "It should be fast" | "P99 latency under 200ms" |
| **Trade-offs** | "Highly available AND consistent" | "Prioritizing availability over consistency because..." |
| **Assumptions** | Implicit, unstated | "I'm assuming we have Redis. If not, I'd adjust." |
| **Constraints** | Accepts all as fixed | "Is 99.99% firm, or could we discuss 99.9%?" |
| **Simplifications** | Doesn't acknowledge | "I'm simplifying to single region; multi-region is an extension" |

---

# Introduction

You've identified your users, defined your functional requirements, and established your scale. Now comes the part that separates adequate designs from excellent ones: non-functional requirements, assumptions, and constraints.

These phases are where Staff engineers demonstrate mastery. Anyone can design a system that "works." Staff engineers design systems that work *reliably*, *quickly*, *securely*, and *cost-effectively*—and they explicitly acknowledge the assumptions and constraints that make those qualities achievable.

**Phase 4: Non-Functional Requirements** defines the qualities your system must have. Not what it does, but how well it does it. Availability, latency, consistency, security—these aren't afterthoughts. They're often the hardest problems to solve and the most important to get right.

**Phase 5: Assumptions and Constraints** makes explicit what you're taking for granted and what limits you're working within. This phase protects your design from misunderstanding and your time from wasted effort.

This section covers both phases together because they're deeply interrelated. Non-functional requirements often depend on assumptions, and constraints often force trade-offs between non-functional requirements.

By the end of this section, you'll approach these phases with confidence. You'll know which quality attributes to consider, how to reason about trade-offs, and how to articulate the foundation your design stands on.

---

# Part 1: Why Non-Functional Requirements Shape Architecture

## The NFR Reality

Here's a truth that junior engineers often miss: **non-functional requirements determine architecture more than functional requirements do.**

Consider two notification systems with identical functional requirements:
- System A: 99% availability, 5-second delivery latency, eventual consistency
- System B: 99.99% availability, 100ms delivery latency, strong consistency

These are completely different architectures:

| Aspect | System A | System B |
|--------|----------|----------|
| Redundancy | Basic backup | Multi-region active-active |
| Processing | Async, best-effort | Sync, guaranteed |
| Data stores | Simple, eventually consistent | Replicated, strongly consistent |
| Infrastructure cost | $ | $$$$ |
| Engineering complexity | Moderate | Very high |

Same functional requirements. Different NFRs. Completely different systems.

## The Architecture-Forcing Effect

Non-functional requirements force specific architectural patterns:

**High availability (99.99%+)** forces:
- Redundancy at every layer
- Automatic failover
- No single points of failure
- Geographic distribution

**Low latency (<100ms)** forces:
- Caching
- Denormalization
- Edge computing
- Minimized network hops

**Strong consistency** forces:
- Distributed consensus
- Careful transaction management
- Often: higher latency, lower availability

**High throughput** forces:
- Horizontal scaling
- Asynchronous processing
- Partitioning/sharding

If you don't establish NFRs before designing, you'll make architecture choices that may not support the qualities you actually need.

## NFRs vs. Functional Requirements: The Interview Implication

In interviews, candidates often focus heavily on functional requirements and treat NFRs as an afterthought. This is backwards.

**Strong candidates**:
- Ask about NFRs early
- Let NFRs guide architecture choices
- Explain how their design achieves the required qualities
- Acknowledge trade-offs between NFRs

**Weak candidates**:
- Don't ask about NFRs
- Design first, hope it meets NFRs later
- Can't explain what quality levels their design achieves
- Treat all NFRs as equally achievable

---

# Part 2: The Core Non-Functional Requirements

## Quick Reference: The 6 Core NFRs

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        THE 6 CORE NFRs                                      │
│                                                                             │
│   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│   │   RELIABILITY   │  │  AVAILABILITY   │  │    LATENCY      │             │
│   │                 │  │                 │  │                 │             │
│   │ "Does it work   │  │ "Is it there    │  │ "How fast does  │             │
│   │  correctly?"    │  │  when needed?"  │  │  it respond?"   │             │
│   │                 │  │                 │  │                 │             │
│   │ • Durability    │  │ • 99% = 3.6d/yr │  │ • P50 (median)  │             │
│   │ • Correctness   │  │ • 99.9% = 8.7h  │  │ • P95           │             │
│   │ • Data integrity│  │ • 99.99% = 52m  │  │ • P99           │             │
│   └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│                                                                             │
│   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│   │  SCALABILITY    │  │  CONSISTENCY    │  │    SECURITY     │             │
│   │                 │  │                 │  │                 │             │
│   │ "Can it handle  │  │ "Do all users   │  │ "Is it          │             │
│   │  more load?"    │  │  see same data?"│  │  protected?"    │             │
│   │                 │  │                 │  │                 │             │
│   │ • Vertical      │  │ • Strong        │  │ • AuthN/AuthZ   │             │
│   │ • Horizontal    │  │ • Eventual      │  │ • Encryption    │             │
│   │ • Auto-scaling  │  │ • Causal        │  │ • Audit         │             │
│   └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Reliability

**Definition**: The system works correctly—producing the right results and not losing data.

**Key questions**:
- Can the system lose data? Under what circumstances?
- Can the system produce incorrect results? How is this prevented?
- What's the impact of data loss or corruption?

**Reliability considerations**:
- **Durability**: Data, once written, is not lost
- **Correctness**: Operations produce expected results
- **Data integrity**: Data remains consistent and uncorrupted

**Design implications**:
- Write-ahead logging
- Replication before acknowledgment
- Checksums and validation
- Transaction support

**Example articulation**:
"For this payment system, reliability is non-negotiable. We cannot lose a transaction or record an incorrect amount. I'll use synchronous replication to at least two nodes before acknowledging writes. Every operation will be logged for audit and recovery."

## Availability

**Definition**: The system is accessible and operational when users need it.

**Key metric**: Percentage of time the system is available.

| Level | Downtime/Year | Downtime/Month | Typical Use |
|-------|---------------|----------------|-------------|
| 99% | 3.65 days | 7.3 hours | Internal tools |
| 99.9% | 8.76 hours | 43.8 minutes | Business apps |
| 99.99% | 52.6 minutes | 4.38 minutes | Critical services |
| 99.999% | 5.26 minutes | 26.3 seconds | Core infrastructure |

**Key questions**:
- What availability level is required?
- What's the cost of downtime? (Revenue, users, reputation)
- Is partial availability acceptable? (Some features degraded)

**Design implications**:
- Redundancy (no single points of failure)
- Health checks and automatic recovery
- Graceful degradation
- Geographic distribution for regional failures

**Example articulation**:
"For this consumer notification system, I'm targeting 99.9% availability—about 43 minutes of downtime per month. We'll achieve this with redundant services in two availability zones. If we needed 99.99%, I'd add a third region with active-active deployment, but that's 10x the infrastructure cost."

## Latency

**Definition**: How quickly the system responds to requests.

**Key metrics**:
- P50 (median): 50% of requests faster than this
- P95: 95% of requests faster than this
- P99: 99% of requests faster than this

**Why percentiles matter**:
Average latency hides problems. A system with 50ms average might have P99 of 2 seconds—5% of users experience 40x worse performance.

**Key questions**:
- What latency is acceptable for this operation?
- What's the user impact of slow responses?
- Are there different latency requirements for different operations?

**Typical targets by operation type**:

| Operation Type | Typical P99 Target |
|----------------|-------------------|
| Real-time API (user waiting) | 100-500ms |
| Interactive (tolerable delay) | 500ms-2s |
| Background processing | Seconds to minutes |
| Batch processing | Minutes to hours |

**Design implications**:
- Caching for read latency
- Async processing to avoid blocking
- Denormalization to reduce joins
- Edge computing for geographic latency
- Connection pooling and keep-alive

**Example articulation**:
"For feed loading, I'm targeting P99 under 300ms. Users expect instant response when opening the app. For notification delivery, I'm targeting P99 under 5 seconds—users don't expect instant push notifications. For analytics data, latency is less critical—minutes is acceptable."

## Scalability

**Definition**: The system can handle increased load by adding resources.

**Types of scalability**:
- **Vertical scaling**: Adding resources to existing machines (CPU, RAM)
- **Horizontal scaling**: Adding more machines

**Key questions**:
- What's the expected load growth?
- Can the system scale horizontally?
- What components are scaling bottlenecks?
- At what point does the current design break?

**Design implications**:
- Stateless services (easy to replicate)
- Partitioned data stores (distribute load)
- Auto-scaling infrastructure
- Avoiding global bottlenecks

**Example articulation**:
"This system needs to handle 10x growth over 2 years. I'm designing for horizontal scalability: stateless application servers behind a load balancer, sharded database with user_id as the partition key. The main scaling bottleneck will be the central rate limiting service—I'll address that by making it distributed."

## Consistency

**Definition**: Different users/components see the same data at the same time.

**Consistency levels**:

| Level | Description | Trade-off |
|-------|-------------|-----------|
| Strong consistency | All readers see the latest write immediately | Higher latency, lower availability |
| Eventual consistency | Readers will eventually see the write | Lower latency, higher availability |
| Causal consistency | Causally related operations seen in order | Middle ground |
| Read-your-writes | You always see your own writes | Often acceptable compromise |

**The CAP theorem reminder**:
In a distributed system experiencing a network partition, you must choose between consistency and availability. You cannot have both.

**Key questions**:
- Can users tolerate stale data? For how long?
- What's the impact of inconsistent views?
- Are there operations that require strong consistency?

**Design implications**:
- Strong consistency: Distributed consensus (Paxos, Raft), single leader
- Eventual consistency: Async replication, conflict resolution
- Mixed: Strong for some operations, eventual for others

**Invariants as NFR:** Staff engineers define *data invariants*—properties that must always hold—as explicit NFRs. Examples: "Balance never negative," "Every notification has exactly one delivery attempt or is in retry," "User preferences are eventually consistent but never lost." Invariants drive consistency model choice: strong consistency for invariants that cannot be violated; eventual consistency where temporary violation is acceptable.

**Example articulation**:
"For the notification system, eventual consistency is acceptable for read status—if it takes a few seconds for 'read' to propagate, users won't notice. But for user preferences (muting notifications), I want read-your-writes consistency at minimum—if a user mutes something, they should immediately stop seeing notifications from it."

## Security

**Definition**: The system protects against unauthorized access and malicious actions.

**Security dimensions**:
- **Authentication**: Verifying identity (who are you?)
- **Authorization**: Verifying permissions (what can you do?)
- **Confidentiality**: Protecting data from unauthorized access
- **Integrity**: Protecting data from unauthorized modification
- **Audit**: Recording who did what and when

**Key questions**:
- What data is sensitive?
- Who should have access to what?
- What are the compliance requirements? (GDPR, HIPAA, PCI-DSS)
- What are the threat models?

**Design implications**:
- Encryption at rest and in transit
- Access control at every layer
- Input validation and sanitization
- Audit logging
- Principle of least privilege

**Trust boundaries:** Staff engineers map trust boundaries—where data or control crosses from trusted to untrusted (or less trusted) domains. Examples: user input → API; external client → internal service; internal service → third-party. Each boundary has NFR implications: validation, rate limiting, auth. Defining trust boundaries explicitly prevents security NFRs from being vague ("we'll secure it") and drives concrete design (validate at boundary, never trust internal data from untrusted source).

**Example articulation**:
"This system handles user notification preferences, which is PII. All data will be encrypted at rest. All API endpoints require authentication. User data is only accessible to the owning user—no cross-user data access. We'll log all data access for audit purposes, and data must be deletable for GDPR compliance."

---

# Part 3: How Staff Engineers Reason About NFR Trade-Offs

## Quick Visual: The Trade-Off Reasoning Process

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     THE 4-STEP TRADE-OFF REASONING PROCESS                  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  STEP 1: IDENTIFY WHAT'S NON-NEGOTIABLE                             │   │
│   │  "We CANNOT lose transactions" → Durability is fixed                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  STEP 2: IDENTIFY WHAT'S FLEXIBLE                                   │   │
│   │  "We'd like 99.99%, but 99.9% might be acceptable"                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  STEP 3: UNDERSTAND THE COSTS                                       │   │
│   │  "Strong consistency → write latency goes from 10ms to 100ms"       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  STEP 4: MAKE EXPLICIT CHOICES                                      │   │
│   │  "I'm choosing eventual consistency because [1, 2, 3 reasons]"      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## The Trade-Off Reality

Here's what many engineers miss: **you can't maximize all NFRs simultaneously.** They trade off against each other.

**Common trade-offs**:

| Optimizing For | Often Sacrifices |
|----------------|------------------|
| Consistency | Availability, Latency |
| Availability | Consistency |
| Latency | Consistency, Cost |
| Durability | Latency |
| Security | Performance, Usability |
| Cost | All of the above |

## The Trade-Off Reasoning Process

Staff engineers use a systematic process:

### Step 1: Identify What's Non-Negotiable

Some NFRs are fixed by the business context:
- "We cannot lose transactions" → Durability is non-negotiable
- "Users are waiting at checkout" → Latency must be low
- "This is healthcare data" → Security and compliance are non-negotiable

### Step 2: Identify What's Flexible

Other NFRs have room for adjustment:
- "We'd like 99.99% availability, but 99.9% might be acceptable"
- "Real-time would be great, but within 30 seconds is probably fine"
- "Strong consistency would be ideal, but eventual is probably okay"

### Step 3: Understand the Trade-Off Costs

For each trade-off, understand what you're giving up:
- "If we choose eventual consistency, users might see stale data for up to 5 seconds"
- "If we choose strong consistency, our write latency increases from 10ms to 100ms"
- "If we target 99.99% availability instead of 99.9%, infrastructure costs 5x"

### Step 4: Make Explicit Choices

State your choices and reasoning:
- "I'm choosing eventual consistency because: (1) the functional requirements tolerate 5 seconds of staleness, (2) it lets us achieve 99.9% availability, (3) it reduces write latency from 100ms to 10ms"

## Trade-Off Examples

### Example 1: Notification System

**Conflicting requirements**:
- "Notifications should be delivered immediately" (low latency)
- "Notifications should never be lost" (high durability)
- "System should always accept new notifications" (high availability)

**Trade-off reasoning**:

"I can't optimize all three simultaneously. Here's my reasoning:

Durability is most important—lost notifications mean missed information. I'll use persistent storage with replication before acknowledgment.

Availability is second—users should always be able to trigger notifications. I'll accept a slight increase in latency to ensure notifications are durably stored.

Latency is third—I'll target 'within a few seconds,' not 'instant.' This gives me room to queue and batch for efficiency.

Specifically: I accept 2-5 second delivery latency to ensure no notification is lost and the ingestion endpoint is always available."

### Example 2: Rate Limiter

**Conflicting requirements**:
- "Rate limit check must be instant" (low latency)
- "Rate limits must be accurate" (consistency)
- "Rate limiter must never be the reason requests fail" (availability)

**Trade-off reasoning**:

"The rate limiter is on the critical path—every request passes through it. Trade-offs:

Latency is most critical—I have <1ms budget. I'll use in-memory counters with no synchronous writes.

Availability is second—if the rate limiter fails, we should fail open (allow requests) rather than fail closed (block everything). Better to occasionally allow over-limit requests than to block all requests.

Accuracy is third—I'll accept eventual consistency. In a distributed setup, we might allow slightly over the limit due to counter sync delays. For a limit of 100 req/sec, we might occasionally allow 105. That's acceptable.

Specifically: I choose approximately correct limits with low latency over perfectly accurate limits with high latency."

### Example 3: Feed System

**Conflicting requirements**:
- "Feed should load instantly" (low latency)
- "Feed should show the latest content" (freshness/consistency)
- "Feed should handle 100M users" (scalability)

**Trade-off reasoning**:

"At 100M users, precomputing every feed in real-time isn't feasible. Trade-offs:

Latency is most critical—users expect instant app launch. I'll precompute and cache feeds.

Scalability is second—the architecture must handle the user count. I'll use sharding and denormalization.

Freshness is third—I'll accept that the feed might be slightly stale. A new post might take 30-60 seconds to appear in followers' feeds. Users tolerate this.

Specifically: I choose cached, slightly stale feeds that load instantly over always-fresh feeds that require real-time aggregation."

## Articulating Trade-Offs in Interviews

Use this structure:

1. State the conflicting requirements
2. Explain which matters most and why
3. Describe what you're sacrificing
4. Quantify the impact
5. Invite feedback

**Example**:
"I see a trade-off between consistency and latency here. I'm prioritizing latency because users are actively waiting for this response. I'm accepting eventual consistency, which means reads might be stale for up to 5 seconds. Is that acceptable, or do we need stronger consistency?"

---

# Part 4: Why Assumptions Must Be Stated Explicitly

## The Assumption Problem

Every design rests on assumptions. Some examples:

- "I assume we have existing authentication infrastructure"
- "I assume users have smartphones with push notification support"
- "I assume database read replicas have <100ms replication lag"
- "I assume network latency within a region is <5ms"

If these assumptions are wrong, the design may fail.

## Why Explicit Assumptions Matter

### They Protect Against Misunderstanding

The interviewer might have different assumptions. If you assume "the system has 100K users" and they assume "100M users," your design will be inappropriate—and you won't know until they point it out.

Stating assumptions explicitly invites correction: "I'm assuming 100K users—is that the right order of magnitude?"

### They Define the Design's Validity

Every design is valid only under certain conditions. Explicit assumptions define those conditions:

"This design works if:
- Replication lag stays under 1 second
- We have at least two availability zones
- Peak load doesn't exceed 10x average"

If any assumption is violated, the design may need revision.

### They Demonstrate Professional Maturity

Staff engineers know that designs don't exist in a vacuum. They're embedded in organizational contexts, technical environments, and uncertain futures. Stating assumptions shows awareness of this reality.

### They Enable Faster Alignment

Instead of designing for 30 minutes and discovering misalignment, you surface assumptions in 2 minutes and correct course immediately.

## Types of Assumptions

### Infrastructure Assumptions

What technical infrastructure exists?
- "We have cloud infrastructure with auto-scaling"
- "We have a CDN for static content"
- "We have a message queue like Kafka"
- "We have monitoring and alerting infrastructure"

### Organizational Assumptions

What organizational capabilities exist?
- "We have a team that can operate distributed systems"
- "We have on-call support for 24/7 operation"
- "We have existing relationships with push notification providers"

### Behavioral Assumptions

How do users and systems behave?
- "Traffic follows a typical daily pattern with 3x peak"
- "Users access the system from mobile devices 80% of the time"
- "Data access follows a power-law distribution"

### Environmental Assumptions

What is the operating environment?
- "Network latency within region is <5ms"
- "Third-party services have 99.9% availability"
- "Disk failure rate is approximately 2% per year"

## Articulating Assumptions

**The simple formula**: "I'm assuming [assumption]. Is that valid?"

**Grouped assumptions**:
"Let me state my key assumptions:
1. We're on standard cloud infrastructure (I'll use AWS examples)
2. Authentication and authorization are handled by existing systems
3. We have push notification infrastructure (APNs/FCM integration)
4. Traffic follows typical consumer patterns with 3x peak

Do any of these need adjustment?"

---

# Part 5: Constraints vs. Assumptions vs. Simplifications

## Quick Visual: Assumptions vs Constraints vs Simplifications

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              ASSUMPTIONS vs CONSTRAINTS vs SIMPLIFICATIONS                  │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │  ASSUMPTIONS                                                          │ │
│   │  "Things I believe are true"                                          │ │
│   │                                                                       │ │
│   │  Your stance: "I believe this is true"                                │ │
│   │  Can change: YES (if corrected)                                       │ │
│   │  Purpose: Defines when your design is valid                           │ │
│   │                                                                       │ │
│   │  Example: "I assume we have Redis for caching"                        │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │  CONSTRAINTS                                                          │ │
│   │  "Limits I must work within"                                          │ │
│   │                                                                       │ │
│   │  Your stance: "I must work with this"                                 │ │
│   │  Can change: NO (given by context)                                    │ │
│   │  Purpose: Limits your solution space                                  │ │
│   │                                                                       │ │
│   │  Example: "Latency must be under 200ms P99"                           │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │  SIMPLIFICATIONS                                                      │ │
│   │  "Things I'm choosing to ignore"                                      │ │
│   │                                                                       │ │
│   │  Your stance: "I'm choosing to defer this"                            │ │
│   │  Can change: YES (your choice)                                        │ │
│   │  Purpose: Manages complexity                                          │ │
│   │                                                                       │ │
│   │  Example: "I'm designing for single region; multi-region is extension"│ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Definitions

These three concepts are related but distinct:

**Assumptions**: Things you believe to be true that you're not explicitly designing for.
- "I assume the network is reliable within a datacenter"
- These are conditions under which your design is valid

**Constraints**: Limits you must work within; these are given, not chosen.
- "We must use the existing Oracle database"
- "Budget limits us to $10K/month infrastructure"
- These constrain your solution space

**Simplifications**: Deliberate reductions of scope or complexity that you choose for tractability.
- "I'm simplifying by assuming all users are in one time zone"
- "For this design, I'm treating the database as a black box"
- These are your choices for managing complexity

## Why the Distinction Matters

| Type | Your Stance | Can Change? | Purpose |
|------|-------------|-------------|---------|
| Assumption | "I believe this is true" | Yes, if corrected | Defines validity conditions |
| Constraint | "I must work with this" | No (given by context) | Limits solution space |
| Simplification | "I'm choosing to ignore this" | Yes, your choice | Manages complexity |

**Assumptions** can be wrong, and you want to be corrected.
**Constraints** are facts you must accept.
**Simplifications** are your choices, and you should be ready to un-simplify if needed.

## Examples

### Rate Limiter Design

**Assumptions**:
- "I assume we have a distributed cache infrastructure (Redis or similar)"
- "I assume client IDs are provided with each request"
- "I assume clock synchronization across servers is within 100ms"

**Constraints**:
- "The rate limiter must add <1ms latency to request processing"
- "We must handle 1M requests per second"
- "We must integrate with the existing API gateway"

**Simplifications**:
- "I'm simplifying by assuming a single rate limit per client, not per-endpoint limits"
- "I'm simplifying by ignoring geographic distribution initially"
- "I'm treating the exact rate limiting algorithm as an implementation detail"

### Feed System Design

**Assumptions**:
- "I assume we have a social graph service that provides follower relationships"
- "I assume content (posts) is stored in a separate content service"
- "I assume we have ranking/ML infrastructure for feed personalization"

**Constraints**:
- "Feed must load in under 300ms"
- "We have 200M daily active users"
- "Storage budget is limited to current infrastructure costs + 20%"

**Simplifications**:
- "I'm simplifying by assuming text-only content; media adds complexity"
- "I'm simplifying by treating ranking as a black box that returns a score"
- "I'm not designing the ad injection system—I'll just leave placeholder slots"

## Articulating the Distinction

Use explicit language to categorize:

"Before I design, let me state my assumptions, constraints, and simplifications.

**Assumptions** (things I believe are true):
- We have cloud infrastructure with auto-scaling
- Authentication is handled externally
- We have standard monitoring tools

**Constraints** (limits I must work within):
- The system must handle 10K QPS
- Latency must be under 200ms P99
- We must integrate with the existing user service

**Simplifications** (things I'm choosing to not address):
- I'll design for a single region; multi-region adds complexity I can address later
- I'll assume a simple ranking function; ML-based ranking is a separate system
- I won't design the admin interface in detail

Is this framing appropriate for what you want to explore?"

---

# Part 6: How Phase 5 Protects Design Decisions

## The Protection Mechanism

Phase 5 (Assumptions & Constraints) serves as a defensive shield for your design. It:

### Prevents Misalignment

By stating assumptions explicitly, you catch misunderstandings early:

**Without Phase 5**:
- You design for 30 minutes
- Interviewer: "But this needs to work globally, not just US"
- Your design is invalidated

**With Phase 5**:
- You state: "I'm assuming US-only initially"
- Interviewer: "Actually, this needs to be global"
- You adjust before designing

### Defines Scope Clearly

Phase 5 draws explicit boundaries:

"I'm designing the notification delivery system. I'm explicitly NOT designing:
- Notification content creation (handled by calling services)
- Push infrastructure (using existing APNs/FCM)
- Long-term analytics (separate system)

These are in my 'assumptions' bucket—I assume they exist and work."

### Enables Valid Simplification

Phase 5 lets you simplify without appearing ignorant:

**Without Phase 5**:
"We'll just use a simple database." (Interviewer wonders: Do they not know about sharding?)

**With Phase 5**:
"I'm simplifying by using a single database initially. For this scale, it's sufficient. If scale increases 10x, we'd shard by user_id—the schema I'm designing supports that." (Interviewer sees: They know about sharding but are choosing appropriate simplicity)

### Makes Trade-Offs Discussable

Phase 5 opens conversations:

"I'm assuming eventual consistency is acceptable. If we need strong consistency, the design would change significantly—we'd need distributed consensus, which would impact latency. Is eventual consistency okay, or should I explore the strongly consistent approach?"

## Example: Phase 5 as Protection

**Design prompt**: "Design a URL shortener"

**Phase 5 statement**:

"Let me state my assumptions and constraints:

**Assumptions**:
1. We have basic cloud infrastructure (compute, storage, CDN)
2. Custom short URLs are a premium feature, not needed for MVP
3. Analytics are important but can be eventually consistent
4. We don't need to support extremely high-profile URLs (like Super Bowl ads)

**Constraints**:
1. Redirect latency must be <50ms (users clicking links)
2. We're designing for 10M active URLs, 100K redirects/second
3. URLs should work for at least 1 year

**Simplifications**:
1. I'm designing for a single region; global distribution is an extension
2. I'm not designing the billing/monetization system
3. I'm treating abuse prevention as a separate concern

Given these, does my framing match what you want to explore?"

Now, if the interviewer says "Actually, we need this for Super Bowl ads," you haven't wasted time—you can adjust your assumptions before designing.

---

# Part 7: How Interviewers Evaluate These Phases

## What Interviewers Look For in Phase 4 (NFRs)

### Proactive NFR Identification

**Strong signal**: Candidate asks about NFRs without prompting
- "What availability level are we targeting?"
- "What's the latency budget for this operation?"
- "Is strong consistency required, or is eventual acceptable?"

**Weak signal**: Candidate doesn't ask about NFRs
- Designs without knowing quality requirements
- Makes assumptions about NFRs without stating them

### Quantification

**Strong signal**: Candidate uses specific numbers
- "I'm targeting 99.9% availability, which is about 8 hours downtime per year"
- "P99 latency should be under 200ms"

**Weak signal**: Candidate uses vague terms
- "It should be highly available"
- "It should be fast"

### Trade-Off Awareness

**Strong signal**: Candidate acknowledges trade-offs and makes reasoned choices
- "I'm choosing eventual consistency here, which sacrifices immediate consistency but gains us better availability and lower latency"

**Weak signal**: Candidate implies all NFRs can be maximized
- "The system will be highly available AND strongly consistent AND very fast"

### Connection to Architecture

**Strong signal**: NFRs drive architecture decisions
- "Because we need 99.99% availability, I'm designing with no single points of failure and multi-region deployment"

**Weak signal**: NFRs disconnected from architecture
- Lists NFRs, then designs without reference to them

## What Interviewers Look For in Phase 5 (Assumptions & Constraints)

### Explicit Statements

**Strong signal**: Candidate lists assumptions unprompted
- "Let me state my assumptions: we have cloud infrastructure, authentication is handled, we have monitoring..."

**Weak signal**: Candidate makes implicit assumptions
- Designs assuming infrastructure that may not exist
- Doesn't clarify organizational context

### Reasonable Assumptions

**Strong signal**: Assumptions are realistic and appropriate
- "I assume network latency within a region is under 5ms"
- "I assume standard cloud infrastructure"

**Weak signal**: Assumptions are unrealistic or extreme
- "I assume we have unlimited budget"
- "I assume the network never fails"

### Awareness of Constraints

**Strong signal**: Candidate probes for constraints
- "Are there technology constraints I should know about?"
- "Is there an existing system I need to integrate with?"

**Weak signal**: Candidate ignores organizational reality
- Designs in a vacuum without considering team, infrastructure, or constraints

### Explicit Simplifications

**Strong signal**: Candidate simplifies intentionally and explains why
- "I'm simplifying by designing for a single region first. Multi-region adds complexity we can address as an extension"

**Weak signal**: Candidate simplifies without acknowledging it
- Interviewer can't tell if simplification is intentional or due to ignorance

---

# Part 8: Concrete Examples

## Example 1: Rate Limiter — Complete NFR and Assumptions Write-Up

### Non-Functional Requirements

**Latency**:
- Rate limit check: <1ms P99 (on the critical path of every request)
- This is non-negotiable—we can't meaningfully slow down the API

**Availability**:
- 99.99% availability
- The rate limiter cannot be a single point of failure
- If the rate limiter is unavailable, we fail open (allow requests) rather than fail closed

**Consistency**:
- Eventual consistency is acceptable
- We tolerate slight inaccuracy (might allow 5-10% over limit in distributed scenarios)
- Strong consistency would add latency we can't afford

**Durability**:
- Counter state does not need to survive complete system restarts
- If we lose state, limits reset—this is acceptable

**Scalability**:
- Must handle 1M requests/second
- Must scale horizontally without coordination

### Assumptions

1. **Infrastructure**: We have distributed caching infrastructure (Redis cluster or similar)
2. **Request identification**: Every request includes a client ID we can use for limiting
3. **Clock synchronization**: Server clocks are synchronized within 100ms (NTP)
4. **Load distribution**: We have load balancers distributing requests across rate limiter instances

### Constraints

1. **Latency budget**: 1ms—this is fixed by the API SLA
2. **Integration**: Must integrate with existing API gateway
3. **Algorithm**: Must support token bucket for burst handling

### Simplifications

1. **Single limit per client**: I'm not designing per-endpoint limits initially
2. **Single region**: Multi-region rate limiting adds complexity; focusing on single region
3. **No persistence**: Counter state is ephemeral; designing for recovery, not durability

### Trade-Off Summary

| Trade-Off | Choice | Rationale |
|-----------|--------|-----------|
| Accuracy vs. Latency | Latency | On critical path; approximate is acceptable |
| Durability vs. Simplicity | Simplicity | Rate limits aren't valuable enough to persist |
| Strong vs. Eventual Consistency | Eventual | Can't afford distributed consensus latency |

## Example 2: Feed System — Complete NFR and Assumptions Write-Up

### Non-Functional Requirements

**Latency**:
- Feed load: <300ms P99 (user is waiting, app open)
- Feed scroll (next page): <200ms P99
- Content load (images/videos): CDN-served, separate from feed latency

**Availability**:
- 99.9% availability
- Graceful degradation acceptable: If personalization fails, show trending content

**Freshness**:
- New posts should appear in followers' feeds within 1 minute
- 30-second freshness is acceptable for most content

**Consistency**:
- Eventual consistency acceptable
- User should see their own posts immediately (read-your-writes)

**Scalability**:
- 200 million DAU
- 10,000 feed loads per second average
- 50,000 feed loads per second peak

### Assumptions

1. **Social graph**: We have a social graph service providing follow relationships
2. **Content service**: Posts are stored and served by a separate content service
3. **Ranking**: We have ML infrastructure for ranking feeds
4. **CDN**: We have CDN for serving media content
5. **User distribution**: Users are globally distributed; we have regional infrastructure

### Constraints

1. **Latency**: 300ms P99—this is fixed by user experience requirements
2. **User count**: 200M DAU—this is the scale we're designing for
3. **Integration**: Must integrate with existing content and user services

### Simplifications

1. **Single feed type**: I'm designing the home feed; Explore/Search are separate
2. **Text focus**: I'm focusing on feed structure; media optimization is a separate concern
3. **No ads**: I'm leaving placeholder slots for ads; ad selection is a separate system

### Trade-Off Summary

| Trade-Off | Choice | Rationale |
|-----------|--------|-----------|
| Freshness vs. Latency | Latency | Users expect instant load; 1-min staleness acceptable |
| Personalization vs. Availability | Availability | Fall back to trending if personalization fails |
| Precomputation vs. Real-time | Hybrid | Precompute for most users, real-time for celebrities |

## Example 3: Notification System — Complete NFR and Assumptions Write-Up

### Non-Functional Requirements

**Latency**:
- Notification delivery: <5 seconds P95 for push
- Email/SMS: Within 1 minute (external provider dependent)
- Notification history load: <200ms P99

**Availability**:
- Ingestion: 99.99% (we should always accept notifications)
- Delivery: 99.9% (occasional delivery delay acceptable)
- History: 99.9%

**Reliability**:
- No notification should be lost once accepted
- At-least-once delivery (duplicates possible)
- Deduplication is the receiver's responsibility

**Consistency**:
- Eventual consistency for read status
- Read-your-writes for preference changes

**Scalability**:
- 100K notifications/second ingestion
- 500K delivery operations/second (including retries)
- 10TB notification storage (30-day history)

### Assumptions

1. **Push infrastructure**: We have APNs/FCM integration via existing services
2. **Email/SMS**: We have existing providers (SendGrid, Twilio)
3. **User data**: Device tokens, email addresses available from user service
4. **Authentication**: Calling services are authenticated; we trust them

### Constraints

1. **Delivery latency**: 5 seconds for push—user experience requirement
2. **Storage**: 30-day history required for product features
3. **Integration**: Must accept notifications from existing event system (Kafka)

### Simplifications

1. **No aggregation logic**: I'm noting aggregation as a capability but not designing the rules
2. **Simple preference model**: Mute/unmute; not designing complex rules
3. **Single retry policy**: Same policy for all notification types

### Trade-Off Summary

| Trade-Off | Choice | Rationale |
|-----------|--------|-----------|
| Exactly-once vs. At-least-once | At-least-once | Exactly-once adds complexity; receivers can dedupe |
| Strong vs. Eventual (read status) | Eventual | Not critical if read status takes seconds to propagate |
| Storage vs. History Depth | 30 days | Product requirement; older history less valuable |

---

# Part 9: Common Mistakes at L5 That Staff Engineers Avoid

## Mistake 1: Not Asking About NFRs

**L5 Pattern**: Jumps into design without establishing quality requirements. Assumes "it should work well."

**Staff Pattern**: Explicitly asks about each major NFR category before designing. "What availability level are we targeting? What's the latency budget?"

**Why it matters**: NFRs drive architecture. Without knowing them, you might design something that doesn't meet requirements—or over-engineer for requirements that don't exist.

## Mistake 2: Using Vague NFR Language

**L5 Pattern**: "The system should be fast and reliable."

**Staff Pattern**: "The system should have P99 latency under 200ms and 99.9% availability, which is about 43 minutes of monthly downtime."

**Why it matters**: Vague terms can't be designed for or tested. Specific numbers enable concrete decisions.

## Mistake 3: Implying All NFRs Can Be Maximized

**L5 Pattern**: "We'll make it highly available AND strongly consistent AND very low latency."

**Staff Pattern**: "There's a trade-off here. I'm prioritizing availability and latency over strong consistency because [reasoning]. We'll accept eventual consistency with up to 5 seconds of staleness."

**Why it matters**: The trade-offs are real (CAP theorem, physics). Claiming you can have everything suggests you don't understand the constraints.

## Mistake 4: Making Assumptions Implicitly

**L5 Pattern**: Uses specific technologies or infrastructure without acknowledging the assumption.

**Staff Pattern**: "I'm assuming we have Redis for caching. If that's not available, I'd use a different approach."

**Why it matters**: Implicit assumptions can be wrong. The interviewer can't correct what they don't hear.

## Mistake 5: Treating Constraints as Fixed When They're Negotiable

**L5 Pattern**: Accepts all stated constraints without question.

**Staff Pattern**: "You mentioned 99.99% availability. Is that firm, or could we discuss 99.9%? The difference is 10x in infrastructure complexity."

**Why it matters**: Some constraints are truly fixed; others are negotiable. Staff engineers probe to understand which is which.

## Mistake 6: Not Simplifying (or Simplifying Without Acknowledging)

**L5 Pattern**: Either tries to design everything (runs out of time) or simplifies without saying so (looks like they don't know the complexity).

**Staff Pattern**: "I'm simplifying by designing for a single region. Multi-region adds complexity we can explore if time permits."

**Why it matters**: Explicit simplification shows you understand the complexity but are managing scope. Implicit simplification looks like ignorance.

## Mistake 7: NFRs Disconnected from Architecture

**L5 Pattern**: Lists NFRs, then designs without reference to them. The architecture doesn't clearly achieve the stated requirements.

**Staff Pattern**: "Because we need 99.99% availability, I'm designing with no single points of failure. Every component has redundancy. Here's how failover works..."

**Why it matters**: NFRs should drive architecture. If you can't explain how your design achieves the NFRs, you haven't designed for them.

## Mistake 8: Ignoring Operational NFRs

**L5 Pattern**: Focuses only on user-facing requirements (latency, availability). Ignores operational concerns (debuggability, deployability, observability).

**Staff Pattern**: "For observability, I'll add structured logging at each stage, metrics on processing time and queue depth, and distributed tracing. When something goes wrong, we need to diagnose it quickly."

**Why it matters**: Systems need to be operated, not just used. Staff engineers think about the full lifecycle.

---

# Quick Reference Card

## NFR Checklist

| NFR | Question to Ask | How to Quantify |
|-----|-----------------|-----------------|
| **Reliability** | "Can we lose data? What's the impact?" | "Zero data loss", "RPO < 1 min" |
| **Availability** | "What uptime is required?" | "99.9%" (8.7h/yr), "99.99%" (52m/yr) |
| **Latency** | "How fast must it respond?" | "P99 < 200ms", "P50 < 50ms" |
| **Scalability** | "How much growth expected?" | "Handle 10x in 2 years" |
| **Consistency** | "Can users see stale data?" | "Eventual (5s stale OK)", "Strong" |
| **Security** | "What's sensitive? Compliance?" | "GDPR", "PCI-DSS", "Encryption at rest" |

---

## Common Trade-Offs Quick Reference

| If You Optimize For... | You Often Sacrifice... |
|------------------------|------------------------|
| **Consistency** | Availability, Latency |
| **Availability** | Consistency |
| **Latency** | Consistency, Cost |
| **Durability** | Latency |
| **Security** | Performance, Usability |
| **Cost** | All of the above |

---

## Availability Quick Reference

| Level | Annual Downtime | Monthly Downtime | Typical Use |
|-------|-----------------|------------------|-------------|
| **99%** | 3.65 days | 7.3 hours | Internal tools |
| **99.9%** | 8.76 hours | 43.8 minutes | Business apps |
| **99.99%** | 52.6 minutes | 4.38 minutes | Critical services |
| **99.999%** | 5.26 minutes | 26.3 seconds | Core infrastructure |

---

## Latency Targets Quick Reference

| Operation Type | Typical P99 Target |
|----------------|-------------------|
| Real-time API (user waiting) | 100-500ms |
| Interactive (tolerable delay) | 500ms-2s |
| Background processing | Seconds to minutes |
| Batch processing | Minutes to hours |

---

## Phase 5 Template

```
ASSUMPTIONS (things I believe are true):
1. We have cloud infrastructure with auto-scaling
2. Authentication is handled externally
3. We have standard monitoring tools

CONSTRAINTS (limits I must work within):
1. The system must handle X QPS
2. Latency must be under Y ms P99
3. We must integrate with existing Z service

SIMPLIFICATIONS (things I'm choosing to defer):
1. Single region; multi-region adds complexity
2. Simple ranking; ML-based ranking is separate
3. Not designing admin interface in detail
```

---

## Staff One-Liners and Mental Models

| Mental Model | One-Liner |
|--------------|-----------|
| **NFRs drive architecture** | "Same function, different NFRs = different system." |
| **Trade-off reality** | "You can't maximize all NFRs; state what you're sacrificing." |
| **Failure is specified** | "Every NFR implies acceptable failure; define it explicitly." |
| **Assumptions are validity conditions** | "Your design is valid only when your assumptions hold." |
| **Blast radius** | "Define how far failure propagates before you design." |
| **First bottleneck** | "At 10x scale, what breaks first? Design for that." |
| **Cost of nines** | "Each nine costs more; right-size for the use case." |

---

## Common Mistakes Quick Reference

| Mistake | What It Looks Like | Fix |
|---------|-------------------|-----|
| **Not asking about NFRs** | Designs without knowing targets | "What availability? What latency?" |
| **Vague language** | "It should be fast" | "P99 latency under 200ms" |
| **Maximize all NFRs** | "Highly available AND consistent AND fast" | "Prioritizing X over Y because..." |
| **Implicit assumptions** | Uses Redis without mentioning | "I'm assuming we have Redis" |
| **Treating all constraints as fixed** | Accepts everything | "Is 99.99% firm, or could we discuss 99.9%?" |
| **Silent simplification** | Simplifies without saying | "I'm simplifying to single region" |
| **NFRs disconnected from design** | Lists NFRs, designs separately | "Because we need X, I'm doing Y" |

---

## Self-Check: Did I Cover Phase 4 & 5?

| Signal | Weak | Strong | ✓ |
|--------|------|--------|---|
| **NFRs asked** | Didn't ask | "What availability? Latency?" | ☐ |
| **Quantified** | "Should be fast" | "P99 < 200ms" | ☐ |
| **Trade-offs acknowledged** | All maximized | "Choosing X over Y because..." | ☐ |
| **Assumptions stated** | Implicit | "I assume we have X, Y, Z" | ☐ |
| **Constraints probed** | All accepted | "Is X firm or negotiable?" | ☐ |
| **Simplifications explicit** | Silent | "I'm simplifying by..." | ☐ |
| **NFRs drive architecture** | Disconnected | "Because NFR X, design choice Y" | ☐ |

---

# Part 10: NFRs and Failure Modes — Staff-Level Thinking

NFRs don't just define how well the system works—they define how the system fails. Staff engineers understand that NFRs implicitly specify acceptable failure behavior.

## NFRs Define Acceptable Failure

Every NFR has a failure mode embedded in it:

| NFR | What It Says | What It Implies About Failure |
|-----|--------------|------------------------------|
| 99.9% availability | System up 99.9% of time | ~43 min/month downtime is acceptable |
| P99 latency < 200ms | 99% of requests < 200ms | 1% of requests CAN be slower |
| Eventual consistency | Data converges eventually | Stale reads ARE acceptable |
| At-least-once delivery | All messages delivered | Duplicates ARE acceptable |

## What Happens When NFRs Are Violated?

Staff engineers define explicit behaviors when NFRs are exceeded:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              NFR VIOLATION RESPONSE FRAMEWORK                               │
│                                                                             │
│   For each NFR, define:                                                     │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. DETECTION                                                       │   │
│   │     "How do we know the NFR is being violated?"                     │   │
│   │     → Metrics, alerts, SLI tracking                                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  2. GRACEFUL DEGRADATION                                            │   │
│   │     "What's the degraded behavior?"                                 │   │
│   │     → Reduced functionality, cached data, shed load                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  3. RECOVERY                                                        │   │
│   │     "How do we return to normal?"                                   │   │
│   │     → Auto-recovery, manual intervention, gradual ramp              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  4. COMMUNICATION                                                   │   │
│   │     "Who needs to know?"                                            │   │
│   │     → Alerts to ops, status page, user messaging                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Example: Latency NFR Violation Response

**NFR:** P99 latency < 200ms

| Phase | Response |
|-------|----------|
| **Detection** | Latency metrics breach threshold for 5+ minutes |
| **Degradation** | Disable personalization, serve cached/generic content |
| **Recovery** | Monitor latency, re-enable features when recovered |
| **Communication** | Alert on-call, consider status page if prolonged |

## Degradation as an NFR

Staff engineers treat degradation behavior as an explicit requirement:

**Format:** "When [NFR] is violated, the system [degraded behavior] until [recovery condition]"

**Examples:**

| NFR | Degradation Requirement |
|-----|------------------------|
| Availability < 99.9% | Non-critical features disabled; core functionality preserved |
| Latency > 500ms | Personalization disabled; return cached results |
| Consistency delayed > 30s | Show "data may be delayed" indicator to users |
| Storage > 90% capacity | Oldest data archived; new writes throttled |

## Articulating Failure-Aware NFRs

**L5 Approach:** "We need 99.9% availability."

**L6 Approach:** "We're targeting 99.9% availability, which means we accept up to 43 minutes of downtime monthly. When availability drops:
- Partial availability is preferred over complete outage
- Non-critical features (recommendations, analytics) degrade first
- Core functionality (message send/receive) is protected
- Users see 'some features temporarily unavailable' not an error page
- On-call is alerted at 99.5% (early warning before SLO breach)"

## Blast Radius and Partial Failure — Staff-Level Depth

**Why it matters at L6:** Staff engineers don't just define *what* fails—they define *how far* failure propagates. Partial failures are the norm; total outages are rare. Understanding blast radius shapes NFR boundaries and degradation design.

**Blast radius** is the set of users, services, or data affected when a component fails. NFRs implicitly specify acceptable blast radius:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BLAST RADIUS VISUALIZATION                          │
│                                                                             │
│   Component fails → Who/what is affected?                                   │
│                                                                             │
│   ┌─────────┐     ┌─────────┐     ┌─────────┐                             │
│   │ Service │────▶│ Downstream│────▶│  Users  │   Blast radius expands      │
│   │   A     │     │ Service B │     │ (100%)  │   with each dependency      │
│   └─────────┘     └─────────┘     └─────────┘                             │
│        │                 │                 │                                │
│   Failure here      Cascade?          Full outage?                          │
│   affects:         1 shard?          Or degraded?                           │
│   • A only         • B only          • Partial failure OK                   │
│   • A + B          • All shards      • Per NFR spec                         │
│                                                                             │
│   STAFF QUESTION: "When X fails, what's the acceptable blast radius?"       │
└─────────────────────────────────────────────────────────────────────────────┘
```

| NFR Choice | Acceptable Blast Radius | Design Implication |
|------------|-------------------------|---------------------|
| Single-region | Entire region if region fails | Regional failover sufficient |
| Multi-region active-active | Single region if region fails | Traffic shifts; other regions unaffected |
| Sharded by user | Users in one shard if shard fails | Isolation; 1/N of users affected |
| Shared rate limiter | All users if limiter fails | Fail open; degraded but not blocked |

**Partial failure as NFR:** Staff engineers specify *degraded* behavior when only part of the system fails:

- "If the personalization service is down, we serve cached feeds for 90% of users; core feed still loads."
- "If one region fails, we serve 80% of traffic from the other region; latency may increase for 20% of users."

**Real-world example:** A feed system that depends on a ranking service. If the ranking service fails, the L5 approach might assume "we're down." The Staff approach: "We degrade to chronological feed. Users see content; quality drops. Blast radius: 100% of users see degraded quality, 0% see total failure."

**Trade-off:** Designing for partial failure adds complexity (fallback paths, circuit breakers). The alternative—all-or-nothing failure—often violates availability NFRs. Staff engineers accept the complexity for critical paths.

---

# Part 10b: Real Incident — NFR Violation in Production

**Context:** A notification delivery system served 50M daily active users. NFRs: 99.9% availability, delivery within 5 seconds P95, zero notification loss.

**Trigger:** A scheduled config change to increase queue consumer count was applied with a typo: consumer count set to 100 instead of 1000. The config validation passed (numeric range) but the value was wrong.

**Propagation:** Within 30 minutes, queue depth grew from 10K to 2M messages. Delivery latency breached 5-second P95. Users reported delayed or missing notifications. The incident was detected via latency metrics, not queue depth.

**User impact:** ~15% of users experienced delayed notifications (5–30 minutes). ~2% saw no delivery for several hours. Support tickets spiked.

**Engineer response:** On-call identified the config error within 45 minutes. Rollback took 10 minutes (config service update). Queue drain took 2 hours. Full recovery: 3 hours.

**Root cause:** The NFR was "delivery within 5 seconds" but the design did not include: (1) queue depth as an SLI, (2) config change validation for operational-critical values, (3) automatic rollback on delivery latency breach.

**Design change:** Added queue depth SLO and alerting. Introduced config change dry-run and canary for consumer scaling. Added automatic latency-based circuit breaker: if delivery P95 > 30 seconds for 5 minutes, trigger rollback and alert.

**Lesson learned:** NFRs must be matched with operational safeguards. "Delivery within 5 seconds" alone is insufficient; the system needed detection, degradation, and recovery for the *failure mode* (queue backlog), not just the SLA metric. Staff engineers now design: "When latency NFR is violated, we [detect], [degrade], [recover]—and we prevent human error from propagating via config safeguards."

---

# Part 11: Operational NFRs as First-Class Requirements

Operational NFRs define how the system is run, not just how it performs. Staff engineers treat these as first-class requirements.

## The Operational NFR Categories

| Category | What It Covers | Key Questions |
|----------|---------------|---------------|
| **Observability** | Ability to understand system state | Can we see what's happening? |
| **Debuggability** | Ability to diagnose issues | Can we find root cause quickly? |
| **Deployability** | Ability to ship changes safely | Can we deploy with confidence? |
| **Operability** | Ability to control and adjust | Can we tune behavior without code changes? |
| **Human-error resilience** | Misconfig, fat-finger, bad deploy | Can we survive and recover from operator mistakes? |

## Human Error as an Operational NFR

**Why it matters at L6:** Most production incidents are triggered by human action—config mistakes, bad deploys, incorrect runbook execution. Staff engineers treat "survive operator error" as a first-class NFR.

**Design implications:**
- **Safeguards:** Require confirmation for destructive ops; dry-run mode for config changes
- **Blast radius control:** Feature flags, canary deploys, and gradual rollout limit bad-change impact
- **Recoverability:** Fast rollback, immutable config history, documented rollback procedures
- **On-call burden:** Simple runbooks reduce fatigue-induced errors; automation reduces manual steps

**Example articulation:** "We assume operators will occasionally misconfigure rate limits or deploy bad code. Our NFR: any config change can be rolled back in under 5 minutes. All deploys use canary with automatic rollback on error spike. This keeps operational NFRs sustainable even when humans make mistakes."

## Observability Requirements

| Requirement | Why It Matters | Design Implication |
|-------------|----------------|-------------------|
| Real-time metrics at service boundaries | SLO tracking | Metrics emission at every hop |
| Latency percentiles (P50, P95, P99) | Performance monitoring | Histogram metrics, not just averages |
| Error rates by type and endpoint | Issue detection | Structured error classification |
| Queue depths and processing rates | Capacity visibility | Instrumented queues |

## Debuggability Requirements

| Requirement | Why It Matters | Design Implication |
|-------------|----------------|-------------------|
| Distributed tracing | Cross-service debugging | Trace context propagation |
| Correlation IDs on all requests | Log aggregation | ID in request context |
| Structured, searchable logs | Investigation speed | JSON logs with consistent fields |
| Request/response logging (sanitized) | Reproduction | Audit trail capability |

## Deployability Requirements

| Requirement | Why It Matters | Design Implication |
|-------------|----------------|-------------------|
| Zero-downtime deployments | Availability SLO | Rolling deploys, drain support |
| Canary deployment support | Safe rollout | Traffic splitting capability |
| Fast rollback (<5 min) | Incident recovery | Stateless services, backward compatible |
| Feature flags | Risk mitigation | Flag infrastructure, gradual rollout |

## Operability Requirements

| Requirement | Why It Matters | Design Implication |
|-------------|----------------|-------------------|
| Runtime configuration changes | Rapid response | Admin API, config service |
| Circuit breakers | Failure isolation | Per-dependency breakers |
| Rate limit adjustments | Load management | Dynamic limit configuration |
| Graceful shutdown | Safe operations | Drain endpoints, connection handling |

## Articulating Operational NFRs

**L5 Approach:** "We'll add monitoring later."

**L6 Approach:** "Beyond performance NFRs, I have operational requirements:

**Observability:**
- Latency metrics at P50/P95/P99 at every service boundary
- Error rates by type (client error, server error, dependency failure)
- Queue depths and processing lag

**Debuggability:**
- Distributed tracing across all services
- Correlation ID in every log entry
- Ability to trace any request through the full path

**Deployability:**
- Zero-downtime rolling deploys
- Canary capability with automated rollback
- Feature flags for all new functionality

**Operability:**
- Circuit breakers between services
- Runtime-adjustable rate limits
- Graceful shutdown with connection draining

These aren't nice-to-haves—at this scale, they're required for the system to be maintainable."

---

# Part 12: NFR Evolution at Scale

NFRs aren't static—they evolve as systems scale. Staff engineers anticipate this evolution.

## How NFRs Change Across Scale

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NFR EVOLUTION ACROSS SCALE                               │
│                                                                             │
│   V1 (Launch)              V2 (Growth)              V3 (Scale)              │
│   ───────────────────────────────────────────────────────────────────────   │
│                                                                             │
│   AVAILABILITY                                                              │
│   "Best effort"      →    "99.9%"           →    "99.99%"                   │
│   Single server           Redundancy              Multi-region              │
│                                                                             │
│   LATENCY                                                                   │
│   "Acceptable"       →    "P99 < 500ms"     →    "P99 < 200ms"              │
│   Optimize later          Cache critical path     Edge deployment           │
│                                                                             │
│   CONSISTENCY                                                               │
│   "Strong OK"        →    "Eventual OK"     →    "Per-operation choice"     │
│   Single DB               Replicas                Hybrid per use case       │
│                                                                             │
│   OBSERVABILITY                                                             │
│   "Logs exist"       →    "Metrics + Logs"  →    "Full tracing"             │
│   Basic logging           Dashboards              Distributed tracing       │
│                                                                             │
│   KEY INSIGHT: Design V1 to not block V2/V3 NFR upgrades                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## NFRs That Intensify at Scale

| NFR | V1 (10K users) | V2 (1M users) | V3 (100M users) |
|-----|----------------|---------------|-----------------|
| **Availability** | 99% acceptable | 99.9% required | 99.99% required |
| **Latency** | 1s acceptable | 500ms required | 200ms required |
| **Durability** | Nightly backup OK | Continuous backup | Zero data loss |
| **Security** | Basic auth | SOC2 compliance | Full audit trail |
| **Operability** | Manual ops OK | Automation needed | Self-healing required |

## Designing for NFR Evolution

**L5 Approach:** "We'll improve NFRs later."

**L6 Approach:** "For V1, I'm targeting 99.9% availability, which is achievable with two availability zones. But I'm designing so we can reach 99.99% without major rearchitecture:
- Stateless services (can add regions without coordination changes)
- Database schema supports sharding (partition key chosen for future growth)
- Health check endpoints ready (for load balancer integration)
- Metrics emission from day one (for SLO tracking)

V2 NFR upgrade is operational changes, not architecture changes."

---

# Part 13: NFR Validation — How to Verify Your Design Meets NFRs

Staff engineers don't just state NFRs—they explain how the design achieves them.

## The NFR Validation Pattern

For each NFR, Staff engineers trace:

1. **What's the NFR?** (Quantified target)
2. **What design element achieves it?** (Specific component/pattern)
3. **How would we measure it?** (SLI definition)
4. **What's the fallback if it's not met?** (Degradation behavior)

## Example: Validating Notification System NFRs

| NFR | Design Element | Measurement (SLI) | Fallback |
|-----|----------------|-------------------|----------|
| 99.9% availability | Redundant services in 2 AZs | Successful requests / total requests | Shed non-critical notifications |
| P99 delivery < 5s | Async queue + parallel workers | Time from submit to delivery | Show in-app even if push fails |
| Zero notification loss | Persistent queue, ack after store | Notifications in - notifications delivered | Dead letter queue, manual replay |
| Eventual consistency (prefs) | Read-through cache, 5s TTL | Staleness age on cache hits | Use defaults if cache miss |

## Connecting NFRs to SLIs/SLOs

Staff engineers speak in SLI/SLO terms:

**SLI (Service Level Indicator):** What we measure
**SLO (Service Level Objective):** The target for that measurement

| NFR | SLI | SLO |
|-----|-----|-----|
| Availability | Successful requests / total requests | > 99.9% over 30-day window |
| Latency | Request duration at P99 | < 200ms |
| Durability | Items written - items lost / items written | > 99.9999% |
| Freshness | Time since last data update | < 5 seconds for 99% of reads |

## Articulating NFR Validation in Interviews

**L5 Approach:** "The system will be highly available."

**L6 Approach:** "I'm targeting 99.9% availability. Here's how I achieve and verify it:

**Design elements:**
- Stateless application tier behind load balancer (no single point of failure)
- Database with synchronous replica (failover in < 30 seconds)
- Health checks every 10 seconds (fast detection)

**Measurement:**
- SLI: Successful responses / total requests, measured at load balancer
- SLO: > 99.9% calculated over 30-day rolling window

**Fallback:**
- If approaching SLO breach (99.5%), shed non-critical features
- Alert at 99.7% for early warning

This gives us defense in depth and visibility into whether we're meeting the target."

---

# Part 14: NFR Conflicts and Prioritization

When multiple NFRs conflict and can't all be met, Staff engineers have a framework for prioritization.

## Common NFR Conflict Patterns

| NFR A | NFR B | Conflict | Resolution Pattern |
|-------|-------|----------|-------------------|
| Low latency | Strong consistency | Consensus adds latency | Choose per-operation; strong for writes, eventual for reads |
| High availability | Strong consistency | CAP theorem | Accept eventual consistency or reduced availability |
| Low cost | High availability | Redundancy costs money | Tier availability by feature criticality |
| Fast deployment | Zero downtime | Blue-green needs double resources | Accept increased cost or slower deploys |

## Cost Drivers in NFR Decisions

**Why it matters at L6:** Changing NFRs changes cost. Staff engineers know which levers drive cost so they can reason about trade-offs.

| NFR Change | Cost Driver | Rough Magnitude |
|------------|------------|-----------------|
| 99% → 99.9% availability | Redundancy (2x), failover | ~2-3x infra |
| 99.9% → 99.99% availability | Multi-AZ, better monitoring | ~5-10x infra |
| 99.99% → 99.999% availability | Multi-region, active-active | ~20-50x infra |
| Eventual → strong consistency | Consensus, sync replication | Latency + 2-5x write cost |
| 500ms → 100ms latency | Caching, edge, optimization | Varies; often 2-5x |
| Basic → full audit trail | Logging, retention, compliance | Storage + operational overhead |

**Staff one-liner:** "Each nine costs more. Right-size for the use case."

## NFR Prioritization Framework

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NFR PRIORITIZATION FRAMEWORK                             │
│                                                                             │
│   STEP 1: IDENTIFY THE CONFLICT                                             │
│           "NFR A and NFR B can't both be fully met"                         │
│                                                                             │
│   STEP 2: ASSESS BUSINESS IMPACT                                            │
│           "What's the cost of degrading each?"                              │
│           • Revenue impact                                                  │
│           • User trust impact                                               │
│           • Regulatory impact                                               │
│           • Operational impact                                              │
│                                                                             │
│   STEP 3: FIND THE DOMINANT NFR                                             │
│           Usually one of:                                                   │
│           • User-facing over internal                                       │
│           • Safety over performance                                         │
│           • Correctness over availability (for money/data)                  │
│           • Availability over correctness (for engagement/content)          │
│                                                                             │
│   STEP 4: DEFINE ACCEPTABLE DEGRADATION                                     │
│           "For the subordinate NFR, what's the minimum acceptable?"         │
│                                                                             │
│   STEP 5: DOCUMENT AND COMMUNICATE                                          │
│           "We're prioritizing A over B because..."                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Domain-Specific NFR Priorities

| Domain | Typical Priority Order | Rationale |
|--------|----------------------|-----------|
| **Financial/Payments** | Correctness > Durability > Availability > Latency | Money can't be wrong or lost |
| **Social/Content** | Availability > Latency > Eventual Consistency > Durability | Engagement matters; slight staleness OK |
| **Healthcare** | Security > Correctness > Availability > Latency | Compliance and patient safety |
| **Real-time Gaming** | Latency > Availability > Consistency | Responsiveness is the product |
| **E-commerce** | Availability > Latency > Consistency | Can't sell if site is down |

## Articulating NFR Prioritization

**L5 Approach:** "We need all these NFRs." (Doesn't acknowledge conflict)

**L6 Approach:** "I see a conflict between our latency and consistency NFRs. Let me prioritize:

**For this notification system:**
1. **Durability** (top): Lost notifications break user trust
2. **Availability**: Users should always be able to receive notifications
3. **Latency**: 5-second delivery is acceptable
4. **Consistency**: Eventual consistency is fine for read status

**The trade-off:** I'm accepting 2-5 second delivery latency to ensure durability (write to persistent queue before acknowledging). If latency were the top priority, I'd acknowledge faster but risk notification loss.

**Business rationale:** Users tolerate slight delay; they don't tolerate missed notifications."

---

# Part 14b: Cross-Team and Organizational Impact — Staff-Level Scope

**Why it matters at L6:** NFR decisions don't exist in isolation. They affect dependent teams, escalate support burden, and create org-wide cost. Staff engineers consider impact beyond their service boundary.

## NFR Decisions That Cross Boundaries

| NFR Decision | Cross-Team Impact | Staff Consideration |
|--------------|-------------------|---------------------|
| 99.99% availability | Increases dependency SLO expectations | "Downstream teams will depend on our uptime; we need to communicate clearly" |
| Eventual consistency | Callers must handle staleness | "API consumers need retry and caching guidance" |
| Degradation behavior | Support and docs teams need to explain | "When we degrade, users see X; support needs runbook" |
| On-call escalation | Other teams paged for our deps | "Our failure cascades to Y; we need joint runbooks" |

## Cost of Over-Provisioning at Org Level

**Real-world example:** A team provisions 99.99% availability for an internal tool used by 50 engineers. The cost: multi-region deployment, 24/7 on-call, complex runbooks. The alternative: 99.9% with planned maintenance windows. The org pays 5x infra and 2 engineers full-time for an NFR that doesn't match the tool's value.

**Staff thinking:** "Who pays for this NFR? Is the cost proportional to the value? Should we negotiate 99.9% with stakeholders so we can use those engineers for higher-impact work?"

## Articulating Cross-Team Impact

**L5 Approach:** Designs NFRs for the system in isolation.

**L6 Approach:** "Our 99.99% availability SLO means downstream teams will build features that depend on us. I'll document our degradation behavior and SLAs so they can design accordingly. We'll also need to coordinate with the auth team—our availability depends on theirs—for joint incident response."

---

# Part 15: Interview Calibration for NFRs and Assumptions (Phase 4 & 5)

## What Interviewers Evaluate

| Signal | What They're Looking For | L6 Demonstration |
|--------|-------------------------|------------------|
| **Proactive NFR inquiry** | Do you ask about quality requirements? | "What availability target? What latency budget?" |
| **Quantification** | Do you use specific numbers? | "99.9% availability, P99 < 200ms" |
| **Trade-off reasoning** | Do you acknowledge conflicts? | "Prioritizing X over Y because..." |
| **Failure awareness** | Do you define failure behavior? | "When latency exceeds SLO, we degrade by..." |
| **Operational thinking** | Do you include ops NFRs? | "For observability, I need metrics at every boundary" |
| **Assumptions explicit** | Do you state what you assume? | "I'm assuming we have Redis. If not..." |
| **Validation approach** | Do you explain how to verify? | "SLI is X, measured at Y, target Z" |

## L6 Phrases That Signal Staff-Level Thinking

### For NFR Quantification

**L5 says:** "The system should be fast and reliable."

**L6 says:** "I'm targeting P99 latency under 200ms for the critical path, and 99.9% availability measured as successful requests over total requests. That's about 43 minutes of allowed downtime monthly."

### For NFR Trade-offs

**L5 says:** "We'll have strong consistency and low latency."

**L6 says:** "There's tension between consistency and latency. For this use case, I'm prioritizing latency because users are waiting. I'm accepting eventual consistency with up to 5 seconds of staleness. For the few operations that need strong consistency—like preference updates—I'll accept higher latency."

### For Failure Behavior

**L5 says:** [Doesn't discuss what happens when NFRs are violated]

**L6 says:** "When latency exceeds our SLO:
- We detect via metrics breaching threshold for 2+ minutes
- We degrade by disabling personalization, serving cached content
- We alert on-call and update status page if prolonged
- We recover gradually, re-enabling features as latency stabilizes"

### For Operational NFRs

**L5 says:** "We'll add monitoring."

**L6 says:** "For operational NFRs, I need:
- Observability: Latency histograms and error rates at every service boundary
- Debuggability: Distributed tracing with correlation IDs
- Deployability: Canary releases with automated rollback
- Operability: Runtime-adjustable rate limits and feature flags

These shape my architecture—I need metrics emission, trace context propagation, and an admin API."

### For Assumptions

**L5 says:** [Uses Redis without mentioning it's an assumption]

**L6 says:** "I'm assuming we have distributed caching infrastructure like Redis. If that's not available, I'd adjust—maybe use local caching with shorter TTLs, or provision caching as part of this design. Is Redis available, or should I include cache infrastructure in scope?"

## Common L5 Mistakes in Phase 4 & 5

| Mistake | How It Manifests | L6 Correction |
|---------|------------------|---------------|
| **No NFR questions** | Designs without knowing targets | "What availability? What latency budget?" |
| **Vague NFRs** | "Should be fast" | "P99 < 200ms, measured at the API gateway" |
| **All NFRs maximized** | "Highly available AND consistent" | "Prioritizing availability, accepting eventual consistency" |
| **No failure behavior** | Only happy path | "When SLO breached, we degrade by X, alert Y" |
| **No operational NFRs** | Forgets observability | "For debuggability, I need tracing and correlation IDs" |
| **Implicit assumptions** | Uses infra without stating | "I'm assuming Redis exists. Is that valid?" |
| **NFRs disconnected** | Lists NFRs, designs separately | "Because we need 99.9%, I'm adding redundancy here" |
| **No validation approach** | Can't explain how to verify | "SLI is X, measured at Y, SLO is Z%" |

## Interviewer's Mental Checklist

As you work through Phase 4 & 5, imagine the interviewer asking:

☐ "Did they ask about availability, latency, consistency?"
☐ "Did they use specific numbers, not vague terms?"
☐ "Did they acknowledge NFR trade-offs?"
☐ "Did they explain what happens when NFRs are violated?"
☐ "Did they include operational NFRs?"
☐ "Did they state assumptions explicitly?"
☐ "Did they explain how to validate the design meets NFRs?"
☐ "Did they connect NFRs to architecture decisions?"

Hit all of these, and you've demonstrated Staff-level Phase 4 & 5 thinking.

## What Interviewers Probe Deeper

| Probe | What They're Testing |
|-------|---------------------|
| "What if we need 99.99% instead of 99.9%?" | Can you reason about cost of NFR changes? |
| "What happens when the database goes down?" | Do you define failure behavior, not just happy path? |
| "Who are your dependencies? What if they fail?" | Blast radius and cascading failure awareness |
| "How would you validate this design meets the NFRs?" | SLI/SLO and measurement thinking |
| "Which of these constraints could we relax?" | Negotiation and prioritization judgment |

## How to Explain NFR Trade-Offs to Leadership

**Avoid:** "We need strong consistency and high availability." (Implies no trade-off.)

**Use:** "We're prioritizing availability over strong consistency because [business reason]. The trade-off: users may see data up to 5 seconds stale. For [use case], that's acceptable. If we needed strong consistency, we'd pay 10x in latency and infrastructure. Here's the cost impact of each option."

**Key:** Lead with business impact, not technical terms. Quantify the trade-off. Offer alternatives with costs.

## How to Teach This Topic to Others

1. **Start with the trade-off reality:** "You can't have everything. Pick what matters."
2. **Use the 4-step process:** Non-negotiable → Flexible → Costs → Explicit choice.
3. **Practice with constraints:** Give a conflicting set (e.g., fast + consistent + cheap) and have them prioritize.
4. **Require quantification:** "Fast" is not acceptable; "P99 < 200ms" is.
5. **Stress assumptions:** "State what you assume. Invite correction. Your design is only valid when assumptions hold."

---

# Part 16: Final Verification — L6 Readiness Checklist

## Does This Section Meet L6 Expectations?

| L6 Criterion | Coverage | Notes |
|-------------|----------|-------|
| **Judgment & Decision-Making** | ✅ Strong | NFR trade-offs, prioritization framework, conflict resolution |
| **Failure & Degradation Thinking** | ✅ Strong | NFR violation response, degradation as NFR, failure behavior |
| **Scale & Evolution** | ✅ Strong | NFR evolution V1→V2→V3, anticipating changes |
| **Staff-Level Signals** | ✅ Strong | L6 phrases, interviewer evaluation, L5 mistakes |
| **Real-World Grounding** | ✅ Strong | Rate limiter, feed, notification examples throughout |
| **Interview Calibration** | ✅ Strong | Explicit signals, phrases, mental checklist |

## Staff-Level Signals Covered

✅ Proactively asking about NFRs before designing
✅ Quantifying NFRs with specific numbers (not vague terms)
✅ Acknowledging and reasoning through NFR trade-offs
✅ Defining failure/degradation behavior for each NFR
✅ Including operational NFRs (observability, debuggability)
✅ Stating assumptions explicitly with validation
✅ Distinguishing assumptions, constraints, and simplifications
✅ Connecting NFRs to architecture decisions
✅ Explaining how to validate design meets NFRs (SLI/SLO)
✅ Anticipating NFR evolution at scale

## Remaining Gaps (Acceptable)

- **Specific SRE practices**: Would require more operational depth
- **Detailed capacity planning**: Covered in Scale section
- **Compliance details**: Varies by domain

---

# Brainstorming Questions

## Non-Functional Requirements

1. For a system you've built, what were the actual NFRs? Were they explicit or implicit?

2. Can you recall a time when NFR trade-offs caused conflict? How was it resolved?

3. What's the highest availability system you've worked on? What made it achievable?

4. When have you seen latency requirements drive architecture? What patterns emerged?

5. How do you decide between strong and eventual consistency? What factors matter?

6. What security considerations have you seen significantly change a design?

## Assumptions and Constraints

7. Think of a project where assumptions turned out to be wrong. What was the impact?

8. What constraints have you worked with that initially seemed limiting but turned out helpful?

9. How do you distinguish between fixed constraints and negotiable requirements?

10. What simplifications do you commonly make in system design? When do you un-simplify?

## Trade-Off Reasoning

11. Describe a trade-off you've made between cost and quality. How did you justify it?

12. When have you chosen complexity for the sake of NFRs? Was it worth it?

13. How do you communicate NFR trade-offs to non-technical stakeholders?

14. What trade-offs have you made that you later regretted?

15. How do you know when you're over-engineering for NFRs that don't matter?

## Blast Radius and Cross-Team Impact

16. For a system you've worked on, what's the blast radius when the primary dependency fails?

17. When have NFR decisions you made affected other teams? How did you communicate?

18. What's an example of over-provisioning (e.g., 99.99% where 99.9% would suffice)? What was the org cost?

---

# Reflection Prompts

Set aside 15-20 minutes for each of these reflection exercises.

## Reflection 1: Your NFR Quantification

Think about how you specify non-functional requirements.

- Do you use vague terms ("fast," "reliable") or quantified targets ("P99 < 200ms," "99.9% availability")?
- For your current project, can you state the availability target and what it means in downtime?
- Do you know the latency budgets for your system's critical paths?
- How do you validate that your design actually meets the NFRs?

Rewrite the NFRs for a system you've designed using precise, measurable language.

## Reflection 2: Your Trade-off Awareness

Consider how you navigate NFR trade-offs.

- What trade-offs have you made between consistency and availability?
- When have you chosen simplicity over performance? Was it right?
- Do you explicitly document trade-offs, or are they implicit?
- How do you communicate trade-off decisions to stakeholders?

For your current project, create a trade-off matrix showing which NFRs conflict and how you resolved them.

## Reflection 3: Your Assumption Discipline

Examine how you handle assumptions and constraints.

- How many assumptions are you currently making implicitly?
- What happens when assumptions turn out to be wrong?
- Which constraints on your current project are truly fixed vs. negotiable?
- Do you revisit assumptions as you design, or set them once and forget?

List 20 assumptions for your current project. Categorize them by risk of being wrong.

---

# Homework Exercises

## Exercise 1: NFR Specification

For each system, specify:
- Availability target (with justification)
- Latency targets for each operation type
- Consistency model
- Security requirements
- Key trade-offs

Systems:
1. A banking mobile app
2. A social media feed
3. A real-time gaming leaderboard
4. An IoT sensor data platform

## Exercise 2: Trade-Off Analysis

Take a design decision you've made (or pick a famous one, like Twitter's eventual consistency).

Write a trade-off analysis:
- What was being optimized for?
- What was sacrificed?
- What was the quantitative impact?
- Was it the right choice? Would you change it?

## Exercise 3: Assumptions Excavation

Take a system you know well.

List at least 15 assumptions it makes across:
- Infrastructure (5+)
- User behavior (3+)
- Organizational capability (3+)
- Environmental conditions (3+)

For each, ask: "What if this assumption was wrong?"

## Exercise 4: Phase 5 Write-Up

Choose a system design prompt (or use: "Design a chat application").

Write a complete Phase 5 document:
- All NFRs with specific numbers
- All assumptions (at least 5)
- All constraints (at least 3)
- All simplifications (at least 3)
- Trade-off summary table

## Exercise 5: NFR-Driven Architecture

Start with these NFRs:
- 99.99% availability
- P99 latency <50ms
- Strong consistency for writes
- 100K QPS

Design the architecture that achieves these.

Then change to:
- 99.9% availability
- P99 latency <500ms
- Eventual consistency
- 100K QPS

Design again. Compare the two architectures. What changed and why?

## Exercise 6: Constraint Negotiation

Practice with a partner.

Partner gives you a design prompt with seemingly impossible constraints:
- "Design a system that's strongly consistent, highly available, and globally distributed with <50ms latency"

Your task:
- Probe to understand which constraints are truly fixed
- Negotiate which can be relaxed
- Propose alternatives that meet the underlying needs
- Document the final agreed constraints

---

# Conclusion

Phase 4 and Phase 5—Non-Functional Requirements, Assumptions, and Constraints—are where Staff engineers distinguish themselves.

**In Phase 4**, you move from "what does the system do" to "how well does it do it." You establish:
- **Specific, quantified targets**: Not "fast" but "P99 <200ms"
- **Explicit trade-offs**: Not "highly available AND consistent" but "prioritizing availability over strong consistency"
- **Architecture-driving requirements**: NFRs that directly shape your design decisions

**In Phase 5**, you make explicit the foundation your design stands on:
- **Assumptions**: What you believe to be true
- **Constraints**: What limits you must work within
- **Simplifications**: What you're choosing to defer

Together, these phases:
- Protect you from misalignment with the interviewer
- Enable valid simplification without appearing ignorant
- Make your trade-offs transparent and discussable
- Show that you design for reality, not an ideal vacuum

The Staff engineer's advantage is not knowing more NFR categories or making more assumptions. It's the discipline to surface these explicitly before designing, to reason about trade-offs clearly, and to connect every architectural decision back to the requirements and constraints it addresses.

This discipline takes practice. But once internalized, it transforms how you approach system design—in interviews and in production.

You're not just building systems that work. You're building systems that work reliably, quickly, securely, and cost-effectively—and you can explain exactly how.

---
