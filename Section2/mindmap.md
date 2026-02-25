# Section 2 — System Design Framework (5 Phases): Mindmap

```
Section 2: System Design Framework
│
├── Ch 13: Framework Overview
│   ├── 5-Phase Framework
│   │   ├── Phase 1: Users & Use Cases (5–7 min)
│   │   ├── Phase 2: Functional Requirements (5–7 min)
│   │   ├── Phase 3: Scale (3–5 min)
│   │   ├── Phase 4: Non-Functional Requirements (3–5 min)
│   │   └── Phase 5: Assumptions & Constraints (2–3 min)
│   └── Context Before Design
│       └── No boxes until you know why they exist
│
├── Ch 14: Phase 1 — Users & Use Cases
│   ├── Four User Types
│   │   ├── Human (end users)
│   │   ├── System (automated callers)
│   │   ├── Service (internal services)
│   │   └── Operational (SREs, on-call)
│   ├── Primary vs Secondary Users
│   │   └── Whose needs drive the design?
│   ├── Intent vs Implementation
│   │   └── What users want vs how they ask for it
│   ├── Core vs Edge Use Cases
│   │   └── Design core first, handle edges later
│   ├── User–Use Case Matrix
│   ├── Scope Control
│   │   └── Explicit in/out of scope
│   └── Failure by User Type
│       └── How each user type experiences failure
│
├── Ch 15: Phase 2 — Functional Requirements
│   ├── Sweet Spot
│   │   └── Specific enough to drive design, not lock implementation
│   ├── Prioritization
│   │   ├── Core (must-have)
│   │   ├── Important (should-have)
│   │   └── Nice-to-have
│   ├── Flow Types
│   │   ├── Read flows
│   │   ├── Write flows
│   │   └── Control flows
│   ├── Behavior Pattern
│   │   └── When [trigger] → system [action] → for [entities] → per [rules]
│   └── Edge Cases
│       └── Handle fully, handle gracefully, or exclude explicitly
│
├── Ch 16: Phase 3 — Scale & Capacity
│   ├── Scale Pipeline
│   │   └── Users → Activity → Rates → Peaks
│   ├── QPS Formula
│   │   └── QPS = (DAU × actions_per_user) / 86,400
│   ├── Peak Multipliers
│   │   ├── Normal: 2–5× average
│   │   └── Events: 10–50×
│   ├── Read/Write Ratio
│   │   └── Drives caching vs write optimization
│   ├── Fan-out
│   │   ├── 1 post × 1K followers = 1M ops
│   │   └── Celebrity problem
│   ├── Hot Keys
│   │   ├── Top 1% ≈ 50% of load
│   │   └── Mitigations: cache, replicate, split, rate limit
│   └── Growth Planning
│       └── 2×, 10× migration paths
│
├── Ch 17: Cost, Efficiency & Sustainability
│   ├── Sustainability = Correct + Scalable + Affordable + Operable
│   ├── Four Cost Dimensions
│   │   ├── Compute (CPU, memory, GPU)
│   │   ├── Storage (hot/warm/cold tiers)
│   │   ├── Network (cross-region, egress)
│   │   └── Operational (engineering time, on-call)
│   └── Staff-Level Cost Thinking
│       ├── Right-sizing vs over-provisioning
│       ├── Elasticity vs fixed capacity
│       ├── Cost of each extra "nine"
│       └── Over-engineering as failure mode
│
├── Ch 18: Phase 4 & 5 — NFRs, Assumptions & Constraints
│   ├── Six Core NFRs
│   │   ├── Reliability
│   │   ├── Availability (99% → 99.999%)
│   │   ├── Latency (e.g. P99 < 200 ms)
│   │   ├── Scalability
│   │   ├── Consistency
│   │   └── Security
│   ├── 4-Step NFR Reasoning
│   │   ├── 1. Non-negotiable
│   │   ├── 2. Flexible
│   │   ├── 3. Costs
│   │   └── 4. Explicit choice
│   ├── Trade-offs
│   │   ├── Consistency vs availability
│   │   ├── Latency vs durability
│   │   └── Operational NFRs: observability, deployability
│   ├── Assumptions
│   │   └── "I'm assuming X. If not, here's how I'd adjust"
│   ├── Constraints = hard limits
│   └── Simplifications = what we defer
│
└── Ch 19: End-to-End Example — News Feed
    ├── Phase 1: 8+ user types (consumers, creators, ops, services)
    ├── Phase 2: Read/write/control flows, 60s freshness, cursor pagination
    ├── Phase 3: 200M DAU, 12K avg / 50K peak QPS
    │   └── Fan-out: 100M posts × 500 followers = 50B writes/day
    ├── Phase 4: P99 < 300 ms, 99.9% availability, eventual consistency
    ├── Phase 5: Assumptions stated, single region, text focus
    └── Architecture
        ├── Hybrid push–pull (push < 10K followers, pull for celebrities)
        ├── Feed Service, Fan-Out Service, Feed Storage, Feed Cache
        └── Failure: cache stampede → request coalescing, cache warming
```
