# Section 2: System Design Framework (5 Phases)

---

## Overview

This section gives you **a repeatable methodology** for approaching any system design problem. While Section 1 established the mindset, this section provides the **structure**—a 5-phase framework that transforms a vague one-sentence prompt into a well-scoped, well-reasoned architecture.

The framework is not a template to memorize. It's a thinking discipline: establish context before designing, derive architecture from requirements, and make every decision traceable back to a stated need. Staff Engineers who use this framework don't produce "better" designs—they produce designs that are **justified, scoped, and defensible**.

The chapters in this section answer the fundamental question: **How do you systematically turn an ambiguous prompt into a production-grade system design?**

---

## Who This Section Is For

- Senior Engineers (L5) who can design systems but want a structured approach for interviews
- Engineers who tend to jump straight into architecture without establishing requirements first
- Anyone preparing for Staff (L6) interviews who wants a framework that works for *any* problem

**Prerequisites**: Section 1 (Staff Engineer Mindset) provides the philosophical foundation. This section translates that mindset into a concrete, phase-by-phase methodology.

---

## The 5-Phase Framework at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                THE 5-PHASE SYSTEM DESIGN FRAMEWORK                          │
│                                                                             │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  Phase 1: USERS & USE CASES                                        │    │
│   │  Who are we building for? What are they trying to do?              │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                              ↓                                              │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  Phase 2: FUNCTIONAL REQUIREMENTS                                  │    │
│   │  What must the system do? (Core, Important, Nice-to-have)          │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                              ↓                                              │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  Phase 3: SCALE                                                    │    │
│   │  How big is this problem? (Users, Data, Requests, Growth)          │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                              ↓                                              │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  Phase 4: NON-FUNCTIONAL REQUIREMENTS                              │    │
│   │  What qualities must it have? (Availability, Latency, Durability)  │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                              ↓                                              │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  Phase 5: ASSUMPTIONS & CONSTRAINTS                                │    │
│   │  What's given? What limits us? (Infra, Team, Budget, Timeline)     │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                              ↓                                              │
│                    NOW you can start designing!                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Section Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SECTION 2: LEARNING PATH                                 │
│                                                                             │
│   Chapter 7                                                                 │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  THE STAFF-LEVEL SYSTEM DESIGN FRAMEWORK                           │    │
│   │  The complete 5-phase overview — why context before design         │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│                              ▼                                              │
│   Chapter 8                                                                 │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  PHASE 1 — USERS & USE CASES                                       │    │
│   │  Identify all user types and what they're trying to accomplish     │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│                              ▼                                              │
│   Chapter 9                                                                 │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  PHASE 2 — FUNCTIONAL REQUIREMENTS                                 │    │
│   │  Define what the system does with Staff-level precision            │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│                              ▼                                              │
│   Chapter 10                                                                │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  PHASE 3 — SCALE: CAPACITY PLANNING AND GROWTH                     │    │
│   │  Translate vague scale into concrete numbers that drive design     │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│                              ▼                                              │
│   Chapter 11                                                                │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  COST, EFFICIENCY, AND SUSTAINABLE DESIGN                          │    │
│   │  The hidden dimension: can we afford what we've designed?          │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│                              ▼                                              │
│   Chapter 12                                                                │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  PHASE 4 & PHASE 5 — NFRs, ASSUMPTIONS, AND CONSTRAINTS            │    │
│   │  Establish qualities, state assumptions, acknowledge limits        │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│                              ▼                                              │
│   Chapter 13                                                                │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  END-TO-END SYSTEM DESIGN USING THE 5-PHASE FRAMEWORK              │    │
│   │  Full walkthrough: News Feed system from prompt to architecture    │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Chapter Summaries

### Chapter 7: The Staff-Level System Design Framework

**Core Question**: What separates a structured, Staff-level approach from ad-hoc whiteboarding?

**Key Concepts**:
- The complete 5-phase framework: Users & Use Cases → Functional Requirements → Scale → NFRs → Assumptions & Constraints
- Why establishing context before designing is non-negotiable
- How the framework maps to a 45-minute interview timeline
- The difference between following a framework rigidly and using it as a thinking discipline
- How each phase informs and constrains the next

**Key Insight**: The framework isn't a checklist to recite—it's a thinking sequence that ensures your architecture *emerges* from requirements rather than being imposed on them. Architecture designed before requirements are understood is guesswork dressed up as engineering.

---

### Chapter 8: Phase 1 — Users & Use Cases

**Core Question**: Who are we building for, and what are they actually trying to do?

**Key Concepts**:
- Four types of users most candidates miss: Human Users, System Users, Service Users, Operational Users
- How different user types drive different design constraints (latency vs throughput, usability vs API stability)
- Identifying primary vs secondary use cases
- Using use cases to scope what's in and out of the design
- Staff behavior: proactively surfacing users the interviewer didn't mention

**L5 vs L6 Contrast**:
| L5 Approach | L6 Approach |
|-------------|-------------|
| Considers only end users | Considers human, system, service, and operational users |
| "Users send messages" | "End users send messages; internal services ingest via API; SREs need dashboards and kill-switches" |
| Moves quickly to design | Uses user identification to bound scope |

---

### Chapter 9: Phase 2 — Functional Requirements

**Core Question**: What must the system do—and, just as importantly, what must it *not* do?

**Key Concepts**:
- The sweet spot: requirements that are specific enough to drive design but not so detailed they constrain implementation
- Prioritization tiers: Core (must-have), Important (should-have), Nice-to-have (could-have)
- Explicit scoping: what's in scope vs what's deliberately out of scope
- Edge case identification as a signal of Staff-level thinking
- Confirming requirements with the interviewer before proceeding

**Key Insight**: Describe *what* the system does, not *how* it does it. "Users can send text messages to other users" drives design decisions. "Store in Cassandra with user_id partition key" constrains implementation prematurely.

---

### Chapter 10: Phase 3 — Scale: Capacity Planning and Growth

**Core Question**: How do you translate a vague "design for a large system" into concrete numbers that shape architecture?

**Key Concepts**:
- The scale translation pipeline: Users → Activity → Rates → Peaks
- Deriving throughput from user counts (DAU × actions/day ÷ 86,400 = RPS)
- Accounting for peak-to-average ratios (typically 2–5×)
- Storage estimation: data size × retention × growth
- How scale numbers directly drive architectural choices (single node vs sharded, sync vs async)

**L5 vs L6 Contrast**:
| L5 Approach | L6 Approach |
|-------------|-------------|
| "It needs to handle a lot of traffic" | "200M DAU × 20 actions/day = 46K avg RPS, 140K peak RPS" |
| Guesses at numbers | Derives from first principles, states assumptions |
| Designs first, checks scale later | Uses scale to *choose* between architectures |

---

### Chapter 11: Cost, Efficiency, and Sustainable System Design

**Core Question**: Can we actually afford the system we've designed—and will it remain affordable as it grows?

**Key Concepts**:
- The sustainability equation: Correct + Scalable + Affordable + Operable
- Cost as a first-class design constraint, not an afterthought
- Compute, storage, network, and operational cost estimation
- Cost-per-unit metrics (cost per request, cost per GB stored, cost per user)
- Designing for cost efficiency without sacrificing reliability
- When over-provisioning is cheaper than complexity

**Key Insight**: A system can be technically perfect but economically unsustainable. Staff Engineers design for both. Most candidates never mention cost; the ones who do immediately signal senior judgment.

---

### Chapter 12: Phase 4 & Phase 5 — NFRs, Assumptions, and Constraints

**Core Question**: What qualities must the system have, and what are we taking for granted?

**Key Concepts**:
- **Phase 4 — Non-Functional Requirements**: availability targets (99.9% vs 99.99%), latency budgets (P50 vs P99), consistency models, durability guarantees
- Why the same functional requirements with different NFRs produce fundamentally different architectures
- Quantifying NFRs: "fast" is not a requirement; "P99 < 200ms" is
- **Phase 5 — Assumptions & Constraints**: infrastructure assumptions, team constraints, timeline, budget
- Stating assumptions explicitly so the interviewer can correct them

**L5 vs L6 Contrast**:
| L5 Approach | L6 Approach |
|-------------|-------------|
| Doesn't ask about NFRs; assumes | "What availability target? What latency budget?" |
| "It should be fast" | "P99 latency under 200ms for reads" |
| "Highly available AND consistent" | "Prioritizing availability over consistency because..." |
| Implicit assumptions | "I'm assuming we have Redis. If not, here's how I'd adjust" |

---

### Chapter 13: End-to-End System Design Using the 5-Phase Framework

**Core Question**: What does it look like when all five phases come together in a real design?

**Key Concepts**:
- Complete walkthrough of a News Feed system using the 5-phase framework
- 45-minute interview timeline breakdown: Phases 1–5 (~20 min) → Architecture (~15–20 min) → Wrap-up (~5 min)
- How each phase's output feeds into the next
- Demonstrating that architecture *emerges* from the requirements—not the other way around
- Handling interviewer probes and pivots mid-design

**Key Insight**: Architecture should feel inevitable by the time you draw it. If you've done Phases 1–5 well, the design decisions almost make themselves—and you can explain *why* each one was made.

---

## How to Use This Section

1. **Read Chapter 7 first**: It provides the complete framework overview that the subsequent chapters expand upon
2. **Study each phase deeply**: Chapters 8–12 unpack individual phases—read them sequentially to build the full picture
3. **Practice with Chapter 13**: After understanding the phases, study the end-to-end walkthrough to see how they connect
4. **Apply to real problems**: Pick any system design prompt and practice running through the 5 phases before designing. Time yourself—Phases 1–5 should take ~15–20 minutes in a 45-minute interview
5. **Return during practice**: When doing Section 5 or 6 problems, revisit specific phase chapters to sharpen your approach

---

## Key Themes Across All Chapters

### 1. Context Before Design

The single most important habit this section builds: never draw a box on the whiteboard until you've established *why* that box needs to exist. Requirements drive architecture, not the other way around.

### 2. Derive, Don't Guess

Whether it's scale numbers, cost estimates, or latency budgets—show your work. Staff Engineers derive from first principles and state assumptions explicitly. Guessing signals inexperience; deriving signals judgment.

### 3. Scope Is a Feature

Deciding what *not* to build is as important as deciding what to build. Every chapter emphasizes explicit scoping—what's in, what's out, and why.

### 4. Trade-offs Are Made Explicit

The framework forces trade-offs to the surface: availability vs consistency, cost vs performance, simplicity vs flexibility. Making these explicit is what separates Staff interviews from Senior ones.

### 5. The Framework Is a Lens, Not a Script

Reciting the framework will fail. Interviewers detect rote answers instantly. The goal is to internalize the thinking discipline so deeply that it feels natural, not rehearsed.

---

## Quick Reference: 45-Minute Interview Timeline

| Phase | Time | Deliverable |
|-------|------|-------------|
| **Phase 1**: Users & Use Cases | 5–7 min | User types identified, primary use cases scoped |
| **Phase 2**: Functional Requirements | 5–7 min | Prioritized requirements (Core / Important / Out of scope) |
| **Phase 3**: Scale | 3–5 min | Derived RPS, storage, peak estimates |
| **Phase 4**: NFRs | 3–5 min | Quantified availability, latency, consistency targets |
| **Phase 5**: Assumptions & Constraints | 2–3 min | Stated assumptions, acknowledged constraints |
| **Architecture Design** | 15–20 min | High-level design + deep dives into 2–3 components |
| **Wrap-up** | 3–5 min | Summary, limitations, future evolution |

---

## What's Next

After completing Section 2, you'll be ready for:

- **Section 3**: Distributed Systems — Deep technical foundations (consistency, replication, coordination, failure models) that you'll need for the architecture phase
- **Section 4**: Data Systems & Global Scale — Advanced patterns for databases, caching, event-driven systems, and multi-region design
- **Section 5**: Senior Design Problems — 13 complete system designs where you'll apply this framework end-to-end
- **Section 6**: Staff-Level Design Problems — The same framework at L6 scope and depth

---

## Reading Time Estimates

| Chapter | Topic | Estimated Reading Time | Estimated Practice Time |
|---------|-------|----------------------|------------------------|
| Chapter 7 | The 5-Phase Framework | 45–60 minutes | 30 minutes reflection |
| Chapter 8 | Phase 1 — Users & Use Cases | 45–60 minutes | 45 minutes practice |
| Chapter 9 | Phase 2 — Functional Requirements | 45–60 minutes | 45 minutes practice |
| Chapter 10 | Phase 3 — Scale | 45–60 minutes | 1 hour practice |
| Chapter 11 | Cost & Sustainable Design | 60–90 minutes | 1 hour practice |
| Chapter 12 | Phase 4 & 5 — NFRs, Assumptions | 45–60 minutes | 45 minutes practice |
| Chapter 13 | End-to-End Walkthrough | 45–60 minutes | 2 hours mock interviews |

**Total Section**: ~7–9 hours reading + ~6–7 hours practice

