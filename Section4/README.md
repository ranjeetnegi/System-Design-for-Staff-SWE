# Section 4: Data Systems & Global Scale

---

## Overview

This section bridges theory and practice. Section 3 taught you the **laws of physics** for distributed systems; this section shows you how those laws manifest in the **concrete systems you'll design and discuss in interviews**: databases, caches, event pipelines, multi-region architectures, and the long-term concerns—cost, compliance, and evolution—that separate Staff-level designs from Senior ones.

Every chapter in this section confronts a common misconception head-on. Databases aren't "SQL vs NoSQL"—they're access-pattern-driven choices. Caching isn't "add Redis for speed"—it's a reliability and cost strategy. Event-driven architecture isn't always "modern and scalable"—it trades debuggability for producer independence. Multi-region isn't "higher availability"—it's a consistency decision you're making whether you realize it or not.

The chapters in this section answer the fundamental question: **How do Staff Engineers choose, combine, and evolve data systems at global scale—while keeping them affordable, compliant, and changeable?**

---

## Who This Section Is For

- Senior Engineers who know *how* to use databases, caches, and queues but want to articulate *why* one choice fits a context better than another
- Engineers who've built single-region systems and need to reason about multi-region trade-offs
- Anyone preparing for Staff (L6) interviews who needs to go beyond component selection into system-wide reasoning about cost, compliance, and evolution

**Prerequisites**: Section 3 (Distributed Systems) provides the theoretical foundations—consistency models, replication, coordination, failure handling—that this section applies to real data systems. Section 2 (5-Phase Framework) tells you *when* these decisions surface in an interview.

---

## Section Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SECTION 4: LEARNING PATH                                 │
│                                                                            │
│   ┌── Core Data Systems ────────────────────────────────────────────────┐  │
│   │                                                                     │  │
│   │  Chapter 21                                                         │  │
│   │  ┌──────────────────────────────────────────────────────────────┐   │  │
│   │  │  DATABASES AT STAFF LEVEL                                    │   │  │
│   │  │  Choosing, using, and evolving data stores                   │   │  │
│   │  └──────────────────────────────────────────────────────────────┘   │  │
│   │                            │                                        │  │
│   │                            ▼                                        │  │
│   │  Chapter 22                                                         │  │
│   │  ┌──────────────────────────────────────────────────────────────┐   │  │
│   │  │  CACHING AT SCALE                                            │   │  │
│   │  │  Redis, CDN, and edge systems — reliability, not just speed  │   │  │
│   │  └──────────────────────────────────────────────────────────────┘   │  │
│   │                            │                                        │  │
│   │                            ▼                                        │  │
│   │  Chapter 23                                                         │  │
│   │  ┌──────────────────────────────────────────────────────────────┐   │  │
│   │  │  EVENT-DRIVEN ARCHITECTURES                                  │   │  │
│   │  │  Kafka, streams, and when events make things worse           │   │  │
│   │  └──────────────────────────────────────────────────────────────┘   │  │
│   │                                                                     │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                            │                                               │
│                            ▼                                               │
│   ┌── Global Scale ─────────────────────────────────────────────────────┐  │
│   │                                                                     │  │
│   │  Chapter 24                                                         │  │
│   │  ┌──────────────────────────────────────────────────────────────┐   │  │
│   │  │  MULTI-REGION SYSTEMS                                        │   │  │
│   │  │  Geo-replication, latency, and regional failure               │   │  │
│   │  └──────────────────────────────────────────────────────────────┘   │  │
│   │                            │                                        │  │
│   │                            ▼                                        │  │
│   │  Chapter 25                                                         │  │
│   │  ┌──────────────────────────────────────────────────────────────┐   │  │
│   │  │  DATA LOCALITY, COMPLIANCE, AND SYSTEM EVOLUTION             │   │  │
│   │  │  Where data lives, who says so, and what it costs            │   │  │
│   │  └──────────────────────────────────────────────────────────────┘   │  │
│   │                                                                     │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                            │                                               │
│                            ▼                                               │
│   ┌── Long-Term Viability ──────────────────────────────────────────────┐  │
│   │                                                                     │  │
│   │  Chapter 26                                                         │  │
│   │  ┌──────────────────────────────────────────────────────────────┐   │  │
│   │  │  COST, EFFICIENCY, AND SUSTAINABLE DESIGN                    │   │  │
│   │  │  Can we afford this at 10x? 100x?                            │   │  │
│   │  └──────────────────────────────────────────────────────────────┘   │  │
│   │                            │                                        │  │
│   │                            ▼                                        │  │
│   │  Chapter 27                                                         │  │
│   │  ┌──────────────────────────────────────────────────────────────┐   │  │
│   │  │  SYSTEM EVOLUTION, MIGRATION, AND RISK MANAGEMENT            │   │  │
│   │  │  Build it to change safely                                   │   │  │
│   │  └──────────────────────────────────────────────────────────────┘   │  │
│   │                                                                     │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Chapter Summaries

### Chapter 21: Databases at Staff Level — Choosing, Using, and Evolving Data Stores

**Core Question**: How do you choose a database—and when do you choose three?

**Key Concepts**:
- Why "SQL vs NoSQL" is the wrong first question—access patterns are the right one
- The database decision framework: data shape → access patterns → consistency needs → scale requirements
- When relational databases remain correct (more often than you'd think)
- When document stores make sense (less often than vendors claim)
- Polyglot persistence: combining multiple stores with careful synchronization
- Planning migration paths—the database that's right at 10K users might strangle you at 10M

**Key Insight**: Nearly every candidate makes the same mistake: they reach for a familiar database first and justify it afterward. Staff Engineers do the opposite—they understand the problem deeply and let constraints guide them to the right store.

---

### Chapter 22: Caching at Scale — Redis, CDN, and Edge Systems

**Core Question**: When is caching a reliability strategy, and when is it a liability?

**Key Concepts**:
- Caching as a reliability and cost strategy, not just a performance optimization
- The four questions before adding any cache: cold start, failure mode, staleness tolerance, invalidation strategy
- Cache layers: application cache, distributed cache (Redis/Memcached), CDN, edge
- Cache stampedes, thundering herds, and cold-start amplification
- When NOT to cache—masking underlying problems until they become critical
- Consistency implications across cache layers

**Key Insight**: Junior engineers add Redis and things get faster. Senior engineers understand cache invalidation is hard. Staff Engineers see caching as a system-wide architecture decision with profound implications for reliability, consistency, and operational complexity.

---

### Chapter 23: Event-Driven Architectures — Kafka, Streams, and Staff-Level Trade-offs

**Core Question**: When do events make systems better—and when do they make systems worse?

**Key Concepts**:
- Events trade consistency and debuggability for scalability and producer independence
- Five questions to answer before adopting events (consumer downtime, ordering, deduplication, cross-service debugging, on-call ownership)
- Kafka internals: partitions, consumer groups, offset management—because mechanics predict failure modes
- Event sourcing vs event notification vs event-carried state transfer
- Anti-patterns that turn promising architectures into production nightmares
- When synchronous calls are the better choice

**Key Insight**: Every event you publish is a promise you're making to the future. Teams adopt Kafka because it's "modern and scalable," then spend two years fighting the consequences—not because Kafka is bad, but because they chose event-driven architecture when something simpler would have sufficed.

---

### Chapter 24: Multi-Region Systems — Geo-Replication, Latency, and Failure

**Core Question**: When does multi-region make things better—and when does it just make things more expensive and more broken?

**Key Concepts**:
- Multi-region as a consistency decision, not just an availability decision
- Five questions before going multi-region (region disagreement, network partitions, cross-continent debugging, follow-the-sun on-call, cost justification)
- Active-active vs active-passive vs read-local/write-global topologies
- Cross-region replication lag and its user-visible consequences
- Regional failover mechanics and the dangers of untested failover
- When single-region with good DR is the right answer

**Key Insight**: Every region you add is a consistency decision you're making. Most teams hear "multi-region" and think "higher availability." They add regions, deploy everywhere, and discover during an incident that they've created a distributed system with all the complexity of consensus but none of the safeguards.

---

### Chapter 25: Data Locality, Compliance, and System Evolution

**Core Question**: Where does every piece of user data live—including copies, caches, logs, and derived data?

**Key Concepts**:
- Data locality as an architectural constraint, not a database configuration problem
- Compliance failures hide in logs, caches, analytics pipelines, and backups—not primary databases
- GDPR, data residency, and right-to-deletion as design constraints from day one
- Tracking data lineage across every layer of the system
- Designing for regulatory evolution: new requirements arrive faster than you can retrofit
- The 10x cost difference between compliance-aware design and compliance retrofitting

**Key Insight**: If you can't explain where every piece of user data is at any moment—including copies, caches, logs, and derived data—you cannot claim compliance. Engineers treat data locality as a policy concern until an audit reveals data flowing where it shouldn't.

---

### Chapter 26: Cost, Efficiency, and Sustainable System Design

**Core Question**: Can we afford this system at 10x scale? At 100x?

**Key Concepts**:
- Cost as a first-class design constraint, not a post-build optimization
- The sustainability equation: Correct + Scalable + Affordable + Operable
- Cost cliffs: where the next increment of scale becomes prohibitively expensive
- Hidden O(n^2) and O(n) costs that lurk in naive designs
- The cost of each additional "nine" of availability
- When over-provisioning is cheaper than the engineering cost of optimization
- "Good enough" vs optimal—knowing which components warrant investment

**Key Insight**: A system that works but cannot be afforded is not a working system. Economic sustainability is part of correctness. The most expensive designs aren't wrong—they're excessive, solving problems that don't exist and optimizing for scenarios that never occur.

---

### Chapter 27: System Evolution, Migration, and Risk Management

**Core Question**: How do you change a running system without breaking it?

**Key Concepts**:
- Every successful system becomes a legacy system—evolution is inevitable
- Reversible vs one-way-door decisions and their implications for design
- Migration patterns: strangler fig, dual-write, shadow traffic, expand-contract
- Blast radius containment: limiting the damage when migrations fail
- Multi-team coordination for cross-cutting changes
- Designing for change from day one: seams, abstractions, and version contracts
- Why migrations fail more often than greenfield projects

**Key Insight**: A system that cannot change safely is already failing. Evolution is not technical debt—it is the natural state of successful systems. You are evaluated on how you manage change, not how you avoid it.

---

## How to Use This Section

1. **Read Chapters 21–23 first**: These three cover the core data systems (databases, caches, events) you'll use in nearly every design problem
2. **Read Chapters 24–25 for global scope**: Multi-region and compliance are critical for Staff interviews—they demonstrate thinking beyond a single data center
3. **Read Chapters 26–27 for the long view**: Cost and evolution are what separate Senior designs ("does it work?") from Staff designs ("does it work *sustainably*?")
4. **Apply to Section 5 problems**: As you practice Senior-level designs, return here when choosing databases, designing cache layers, or reasoning about failure
5. **Revisit for Section 6 depth**: Staff-level problems in Section 6 require multi-region reasoning, cost analysis, and evolution planning—these chapters are your reference

---

## Key Themes Across All Chapters

### 1. Question the Defaults

Every chapter starts by dismantling a common misconception. "SQL vs NoSQL" is the wrong question. "Add cache for speed" is the wrong framing. "Multi-region for availability" is incomplete. Staff Engineers question defaults and reason from first principles.

### 2. Skepticism Over Enthusiasm

Staff Engineers approach new technologies and architectures with healthy skepticism. Kafka is excellent—when it fits. Multi-region is powerful—when justified. The chapters repeatedly emphasize asking "should we?" before "how do we?"

### 3. The Non-Technical Dimensions Matter

Cost, compliance, team capacity, migration risk—these "soft" constraints shape architecture as much as latency and throughput. Staff Engineers design for the full picture: technical, organizational, financial, and regulatory.

### 4. Design for the System You'll Have in Two Years

Today's design becomes tomorrow's constraint. Every chapter emphasizes forward-looking decisions: migration paths for databases, evolution strategies for architectures, cost profiles at 10x scale. Staff Engineers design for change, not permanence.

### 5. Every Decision Is a Trade-off With a Name

Caching trades consistency for latency. Events trade debuggability for decoupling. Multi-region trades simplicity for geographic resilience. Naming the trade-off—clearly and explicitly—is what Staff Engineers do differently.

---

## Concept Map: How the Chapters Connect

| When you're designing... | You'll need... | Chapter |
|--------------------------|----------------|---------|
| Storage and data access layer | Database selection framework | Ch 21 |
| Read-heavy performance optimization | Caching strategy (app, distributed, CDN, edge) | Ch 22 |
| Async processing or decoupled services | Event-driven architecture assessment | Ch 23 |
| Global user base or regional failover | Multi-region topology and replication | Ch 24 |
| Systems handling PII or regulated data | Data locality and compliance architecture | Ch 25 |
| Capacity planning or budget justification | Cost modeling and sustainability analysis | Ch 26 |
| Schema changes, platform migrations, rewrites | Evolution strategy and risk management | Ch 27 |

---

## Reading Time Estimates

| Chapter | Topic | Estimated Reading Time | Estimated Practice Time |
|---------|-------|----------------------|------------------------|
| Chapter 21 | Databases at Staff Level | 60–90 minutes | 1 hour applied exercises |
| Chapter 22 | Caching at Scale | 60–90 minutes | 1 hour applied exercises |
| Chapter 23 | Event-Driven Architectures | 60–90 minutes | 1 hour applied exercises |
| Chapter 24 | Multi-Region Systems | 60–90 minutes | 1 hour case studies |
| Chapter 25 | Data Locality & Compliance | 45–60 minutes | 45 minutes applied exercises |
| Chapter 26 | Cost & Sustainable Design | 60–90 minutes | 1 hour cost modeling practice |
| Chapter 27 | Evolution & Migration | 60–90 minutes | 1 hour migration planning practice |

**Total Section**: ~7–10 hours reading + ~6–7 hours practice

---

## What's Next

After completing Section 4, you'll be ready for:

- **Section 5**: Senior Design Problems — 13 complete system designs where you'll choose databases, design cache strategies, reason about failure modes, and estimate costs using the concepts from this section
- **Section 6**: Staff-Level Design Problems — The same problem domains elevated to global scale, multi-region topologies, cross-team platform concerns, and long-term evolution planning

---

*This section is where distributed systems theory meets engineering practice. The concepts here don't just help you pass interviews—they're how Staff Engineers make decisions every day.*
