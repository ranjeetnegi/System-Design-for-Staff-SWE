# System Design Interview Preparation for Google Staff Engineer

A comprehensive, structured guide for experienced backend engineers preparing for Staff Engineer (L6) system design interviews at Google and equivalent roles at top technology companies.

---

## At a Glance

| | |
|---|---|
| **Target Role** | Google Staff Engineer (L6) / equivalent |
| **Audience** | Senior Engineers (8+ years) preparing for Staff-level interviews |
| **Chapters** | 57 across 6 sections |
| **Coverage** | Mindset, Framework, Distributed Systems, Data Systems, Senior-level Problems, Staff-level Problems |
| **Progress** | Sections 1–5 complete, Section 6 in progress (8 of 17 chapters) |

---

## What This Is

This is not a collection of templates to memorize. It is a deep, opinionated guide that takes you from **Staff Engineer mindset** through **repeatable frameworks** and **distributed systems fundamentals** to **30 complete system design problems** at both Senior and Staff levels.

Every chapter emphasizes:
- **Trade-off reasoning** over pattern matching
- **Ambiguity navigation** over memorized steps
- **Judgment under uncertainty** over "correct" answers
- **Holistic systems thinking** over component-level knowledge

---

## Who This Is For

Experienced backend engineers — typically 8+ years — who are:

- Senior at another major tech company, seeking to level-match at Google
- Senior at Google, preparing for internal promotion to Staff
- Technical leaders at startups, seeking formal recognition of that scope
- Engineers at companies where "Staff" means something different, needing to calibrate to Google's bar

You are not learning system design from scratch. You are learning how to **demonstrate your existing capabilities** in the specific context of a Staff-level interview.

---

## Repository Structure

```
System-Design/
├── README.md                  ← You are here
├── Section1/                  ← Staff Engineer Mindset & Evaluation (Ch. 1–6)
│   ├── README.md
│   └── Chapter_1.md … Chapter_6.md
├── Section2/                  ← System Design Framework — 5 Phases (Ch. 7–13)
│   ├── README.md
│   └── Chapter_7.md … Chapter_13.md
├── Section3/                  ← Distributed Systems (Ch. 14–20)
│   ├── README.md
│   └── Chapter_14.md … Chapter_20.md
├── Section4/                  ← Data Systems & Global Scale (Ch. 21–27)
│   ├── README.md
│   └── Chapter_21.md … Chapter_27.md
├── Section5/                  ← Senior-Level Design Problems (Ch. 28–40)
│   ├── README.md
│   └── Chapter_28.md … Chapter_40.md
└── Section6/                  ← Staff-Level Design Problems (Ch. 41–57)
    ├── README.md
    └── Chapter_41.md … Chapter_57.md
```

Each section has its own `README.md` with an overview, learning objectives, and reading guidance.

---

## Table of Contents

### Section 1 — Staff Engineer Mindset & Evaluation

Establishes the foundational mindset: how Google evaluates Staff Engineers and what distinguishes L6 thinking from L5.

| # | Chapter | Link |
|---|---------|------|
| 1 | How Google Evaluates Staff Engineers in System Design Interviews | [Chapter 1](Section1/Chapter_1.md) |
| 2 | Scope, Impact, and Ownership at Google Staff Engineer Level | [Chapter 2](Section1/Chapter_2.md) |
| 3 | Designing Systems That Scale Across Teams (Staff Perspective) | [Chapter 3](Section1/Chapter_3.md) |
| 4 | Staff Engineer Mindset — Designing Under Ambiguity | [Chapter 4](Section1/Chapter_4.md) |
| 5 | Trade-offs, Constraints, and Decision-Making at Staff Level | [Chapter 5](Section1/Chapter_5.md) |
| 6 | Communication and Interview Leadership for Google Staff Engineers | [Chapter 6](Section1/Chapter_6.md) |

---

### Section 2 — System Design Framework (5 Phases)

A repeatable methodology for approaching any system design problem — from vague prompt to justified architecture.

| # | Chapter | Link |
|---|---------|------|
| 7 | System Design Framework | [Chapter 7](Section2/Chapter_7.md) |
| 8 | Phase 1 — Users & Use Cases | [Chapter 8](Section2/Chapter_8.md) |
| 9 | Phase 2 — Functional Requirements | [Chapter 9](Section2/Chapter_9.md) |
| 10 | Phase 3 — Scale: Capacity Planning and Growth | [Chapter 10](Section2/Chapter_10.md) |
| 11 | Cost, Efficiency, and Sustainable Design | [Chapter 11](Section2/Chapter_11.md) |
| 12 | Phase 4 & Phase 5 — NFRs, Assumptions, Constraints | [Chapter 12](Section2/Chapter_12.md) |
| 13 | End-to-End System Design Using the 5-Phase Framework | [Chapter 13](Section2/Chapter_13.md) |

---

### Section 3 — Distributed Systems

The technical bedrock — deep vocabulary for designing systems that actually work at scale.

| # | Chapter | Link |
|---|---------|------|
| 14 | Consistency Models — Guarantees, Trade-offs, and Failure Behavior | [Chapter 14](Section3/Chapter_14.md) |
| 15 | Replication and Sharding — Scaling Without Losing Control | [Chapter 15](Section3/Chapter_15.md) |
| 16 | Leader Election, Coordination, and Distributed Locks | [Chapter 16](Section3/Chapter_16.md) |
| 17 | Backpressure, Retries, and Idempotency | [Chapter 17](Section3/Chapter_17.md) |
| 18 | Queues, Logs, and Streams — Choosing the Right Asynchronous Model | [Chapter 18](Section3/Chapter_18.md) |
| 19 | Failure Models and Partial Failures — Designing for Reality at Staff Level | [Chapter 19](Section3/Chapter_19.md) |
| 20 | CAP Theorem — Behavior Under Partition (Applied Case Studies) | [Chapter 20](Section3/Chapter_20.md) |

---

### Section 4 — Data Systems & Global Scale

Bridges theory and practice — databases, caches, event pipelines, multi-region architectures, and long-term system concerns.

| # | Chapter | Link |
|---|---------|------|
| 21 | Databases — Choosing, Using, and Evolving Data Stores | [Chapter 21](Section4/Chapter_21.md) |
| 22 | Caching at Scale — Redis, CDN, and Edge Systems | [Chapter 22](Section4/Chapter_22.md) |
| 23 | Event-Driven Architectures — Kafka, Streams, and Staff-Level Trade-offs | [Chapter 23](Section4/Chapter_23.md) |
| 24 | Multi-Region Systems — Geo-Replication, Latency, and Failure | [Chapter 24](Section4/Chapter_24.md) |
| 25 | Data Locality, Compliance, and System Evolution | [Chapter 25](Section4/Chapter_25.md) |
| 26 | Cost, Efficiency, and Sustainable System Design | [Chapter 26](Section4/Chapter_26.md) |
| 27 | System Evolution, Migration, and Risk Management | [Chapter 27](Section4/Chapter_27.md) |

---

### Section 5 — Senior-Level Design Problems

13 complete system design problems at the Senior Engineer level — production-grade designs with explicit trade-offs.

| # | Chapter | Link |
|---|---------|------|
| 28 | URL Shortener | [Chapter 28](Section5/Chapter_28.md) |
| 29 | Single-Region Rate Limiter | [Chapter 29](Section5/Chapter_29.md) |
| 30 | Distributed Cache (Single Cluster) | [Chapter 30](Section5/Chapter_30.md) |
| 31 | Object / File Storage System | [Chapter 31](Section5/Chapter_31.md) |
| 32 | Notification System | [Chapter 32](Section5/Chapter_32.md) |
| 33 | Authentication System (AuthN) | [Chapter 33](Section5/Chapter_33.md) |
| 34 | Search System | [Chapter 34](Section5/Chapter_34.md) |
| 35 | Metrics Collection System | [Chapter 35](Section5/Chapter_35.md) |
| 36 | Background Job Queue | [Chapter 36](Section5/Chapter_36.md) |
| 37 | Payment Flow | [Chapter 37](Section5/Chapter_37.md) |
| 38 | API Gateway | [Chapter 38](Section5/Chapter_38.md) |
| 39 | Real-Time Chat | [Chapter 39](Section5/Chapter_39.md) |
| 40 | Configuration Management | [Chapter 40](Section5/Chapter_40.md) |

---

### Section 6 — Staff-Level Design Problems

17 system design problems at the Staff Engineer level — multi-region, cross-team, production-grade architectures with deep trade-off analysis.

Each Staff-level chapter elevates a Senior problem to global scale, introducing multi-region consistency, cross-team ownership, migration strategy, and organizational impact.

| # | Chapter | Status | Link |
|---|---------|--------|------|
| 41 | Global Rate Limiter | Done | [Chapter 41](Section6/Chapter_41.md) |
| 42 | Distributed Cache | Done | [Chapter 42](Section6/Chapter_42.md) |
| 43 | News Feed | Done | [Chapter 43](Section6/Chapter_43.md) |
| 44 | Real-Time Collaboration | Done | [Chapter 44](Section6/Chapter_44.md) |
| 45 | Messaging Platform | Done | [Chapter 45](Section6/Chapter_45.md) |
| 46 | Metrics / Observability System | Done | [Chapter 46](Section6/Chapter_46.md) |
| 47 | Configuration, Feature Flags & Secrets Management | Done | [Chapter 47](Section6/Chapter_47.md) |
| 48 | API Gateway / Edge Request Routing System | Done | [Chapter 48](Section6/Chapter_48.md) |
| 49 | Search / Indexing System (Read-heavy, Latency-sensitive) | Planned | — |
| 50 | Recommendation / Ranking System (Simplified) | Planned | — |
| 51 | Notification Delivery System (Fan-out at Scale) | Planned | — |
| 52 | Authentication & Authorization System | Planned | — |
| 53 | Distributed Scheduler / Job Orchestration System | Planned | — |
| 54 | Feature Experimentation / A/B Testing Platform | Planned | — |
| 55 | Log Aggregation & Query System | Planned | — |
| 56 | Payment / Transaction Processing System | Planned | — |
| 57 | Media Upload & Processing Pipeline | Planned | — |

---

## Progress

```
Section 1  ██████████████████████████████  6/6   chapters — Complete
Section 2  ██████████████████████████████  7/7   chapters — Complete
Section 3  ██████████████████████████████  7/7   chapters — Complete
Section 4  ██████████████████████████████  7/7   chapters — Complete
Section 5  ██████████████████████████████  13/13 chapters — Complete
Section 6  ██████████████░░░░░░░░░░░░░░░░  8/17  chapters — In Progress

Overall    ████████████████████████░░░░░░  48/57 chapters — 84%
```

---

## How to Read This Material

This is designed to be read in order, but you can adapt the path to your needs.

**Recommended reading order:**

1. **Section 1** — Internalize the Staff mindset before touching architecture
2. **Section 2** — Learn the 5-Phase Framework you will use in every design
3. **Section 3** — Build the distributed systems vocabulary for trade-off reasoning
4. **Section 4** — Connect theory to concrete data systems and global-scale concerns
5. **Section 5** — Practice Senior-level problems to build fluency with the framework
6. **Section 6** — Tackle Staff-level problems that add multi-region scale, cross-team impact, and migration strategy

**If you are short on time:**

- Sections 1 + 2 give you the mindset and framework (essential, ~2 hours)
- Section 3 chapters 14, 17, 19 cover the highest-impact distributed systems concepts
- Section 5 gives you 13 ready-to-practice problems at Senior level
- Section 6 gives you Staff-level versions with elevated scope and complexity

**Principles for effective study:**

- **Read actively.** Pause after each concept and connect it to systems you have built.
- **Practice deliberately.** Reading about system design is not the same as doing it. Practice with a partner who can ask probing questions.
- **Revisit and refine.** First pass plants seeds. Subsequent passes — especially after practice — deepen understanding.
- **Focus on understanding, not coverage.** Deep understanding of a few concepts beats shallow coverage of everything.

---

## Key Concepts

Throughout this guide, these themes recur at every level:

| Concept | What It Means |
|---------|---------------|
| **Ambiguity Navigation** | Turning vague prompts into scoped, justified requirements before designing |
| **Trade-off Reasoning** | Explicitly stating alternatives and why one choice fits this context |
| **Assumptions as First-Class Citizens** | Stating, validating, and designing around what you don't know |
| **Scope Definition** | Deciding what to build, what not to build, and why — the Staff differentiator |
| **Systems Thinking** | Reasoning about interactions, failure propagation, and future constraints |
| **Interview Leadership** | Driving the conversation like a senior technical leader, not answering like a student |

---

## Section 5 vs Section 6 — Senior vs Staff

A central design choice of this guide: every Staff-level problem in Section 6 has a Senior-level counterpart in Section 5. This lets you see exactly what changes when you elevate scope.

| Dimension | Senior (Section 5) | Staff (Section 6) |
|-----------|--------------------|--------------------|
| **Scale** | Single region, single cluster | Multi-region, global |
| **Scope** | One team owns the system | Cross-team ownership boundaries |
| **Trade-offs** | Component-level choices | System-wide and organizational trade-offs |
| **Failure** | Handle errors gracefully | Design for partial failures, cascading failures, regional outages |
| **Evolution** | Build it right | Migrate from the existing system without downtime |
| **Cost** | Implicit | Explicit cost modeling and efficiency targets |

---

## License

Personal study notes. Not affiliated with Google.
