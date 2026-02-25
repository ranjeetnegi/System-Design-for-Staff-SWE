# Section 1 — Staff Engineer Mindset & Evaluation: Mindmap

```
Section 1: Staff Engineer Mindset & Evaluation
│
├── Ch 7: How Google Evaluates Staff Engineers
│   ├── Leveling
│   │   ├── L5 (Senior): component/feature scope, execution
│   │   ├── L6 (Staff): system/problem-space scope, direction + execution
│   │   └── L7 (Senior Staff): org-wide scope, strategic
│   ├── L5 → L6 Shift
│   │   ├── "How I'll build it" → "What we should build"
│   │   ├── "Finished my task" → "Identified the next 3 tasks"
│   │   └── "My code is solid" → "The system is solid"
│   ├── 7 Evaluation Signals
│   │   ├── 1. Problem decomposition
│   │   ├── 2. Trade-off articulation
│   │   ├── 3. Appropriate depth (deep vs high-level)
│   │   ├── 4. Failure mode awareness
│   │   ├── 5. Operational maturity (monitoring, rollback)
│   │   ├── 6. Practical judgment (not over-engineered)
│   │   └── 7. Communication clarity
│   ├── What Interviewers Don't Care About
│   │   ├── Perfect tech recall
│   │   ├── Single "correct" answer
│   │   └── Buzzwords or years of experience
│   ├── Why Strong L5s Fail L6
│   │   ├── Execution without strategic framing
│   │   ├── Depth without breadth
│   │   ├── Solving stated problem without questioning it
│   │   ├── Local optimization without global view
│   │   ├── Answering instead of driving
│   │   └── Ignoring organizational side
│   └── Staff-Level Deep Dives
│       ├── Blast radius & failure containment
│       ├── Scale evolution (V1 → 100×)
│       ├── Cross-team influence
│       ├── Cost-aware thinking
│       └── Observability & debuggability
│
├── Ch 8: Scope, Impact & Ownership
│   ├── Three Dimensions of Scope
│   │   ├── Technical: component → system
│   │   ├── Temporal: quarter → 1–2 years
│   │   └── Organizational: team → multiple teams
│   ├── Scope Is Created, Not Assigned
│   ├── Impact Levels
│   │   ├── Team-level (Senior): features, bugs, mentoring
│   │   ├── Multi-team (Staff): shared libs, cross-team fixes
│   │   └── Org-level (strong Staff/L7): strategy, standards
│   ├── Ownership vs Leadership vs Influence
│   │   ├── Ownership: "If it fails, I feel responsible"
│   │   ├── Leadership: "If I left, direction would be lost"
│   │   └── Influence: "My ideas spread without me reviewing"
│   ├── Influence Without Authority
│   │   ├── Credibility, clear communication
│   │   ├── Relationships, coalition building
│   │   └── Problem framing, data & evidence
│   └── Failure Ownership
│       ├── Blast radius ownership
│       ├── Cross-team failure ownership
│       └── Failure prevention as ownership
│
├── Ch 9: Designing Systems That Scale Across Teams
│   ├── Two Dimensions of Scale
│   │   ├── Technical: QPS, data, regions, fault tolerance
│   │   └── Organizational: teams, people, use cases, longevity
│   ├── Systems Fail for Human Reasons Too
│   ├── Design Principles for Team Scale
│   │   ├── Clear ownership — one team per component
│   │   ├── Strong vs weak coupling
│   │   ├── APIs as long-term contracts
│   │   ├── Independent evolution
│   │   ├── Limiting blast radius
│   │   ├── Data ownership & consistency boundaries
│   │   └── Trust boundaries & compliance
│   └── Failure Patterns at Org Scale
│       ├── Centralized service becomes bottleneck
│       ├── Overloaded platform teams
│       ├── Hidden dependencies
│       └── Breaking changes without coordination
│
├── Ch 10: Designing Under Ambiguity
│   ├── L5 vs L6
│   │   ├── L5: "I need requirements before I can design"
│   │   └── L6: "Let me understand what problem we're solving"
│   ├── Ambiguity Navigation Framework
│   │   ├── 1. Understand the core problem
│   │   ├── 2. Identify critical unknowns
│   │   ├── 3. Ask targeted questions
│   │   ├── 4. State assumptions explicitly
│   │   └── 5. Proceed with flexibility
│   ├── Assumption Safety Matrix
│   │   ├── Safe to assume: large scale, standard stack
│   │   ├── Ask first: consistency, latency SLAs, compliance
│   │   └── Don't assume: problem scope, success criteria
│   └── Avoiding Analysis Paralysis
│       ├── Time-box clarification (3–5 min)
│       ├── Make reversible decisions
│       └── "Two paths" technique
│
├── Ch 11: Trade-offs, Constraints & Decision-Making
│   ├── Common Trade-off Dimensions
│   │   ├── Latency vs Consistency
│   │   ├── Throughput vs Latency
│   │   ├── Consistency vs Availability
│   │   ├── Simplicity vs Flexibility
│   │   ├── Cost vs Performance
│   │   └── Speed vs Quality
│   ├── 6-Step Trade-off Communication
│   │   ├── 1. State the tension
│   │   ├── 2. Explain why both sides matter
│   │   ├── 3. Describe options
│   │   ├── 4. Articulate trade-offs for each
│   │   ├── 5. Recommend with reasoning
│   │   └── 6. Identify reversibility
│   └── Constraint Types
│       ├── Technical: latency, throughput, APIs
│       ├── Organizational: team size, structure
│       ├── Business: budget, time-to-market
│       └── Regulatory: PCI, HIPAA, GDPR
│
└── Ch 12: Communication & Interview Leadership
    ├── 4-Phase Interview Flow (45 min)
    │   ├── Understand (5–8 min): clarify, summarize, scope
    │   ├── High-level design (10–12 min): architecture, data flow
    │   ├── Deep dives (15–20 min): 2–3 areas, trade-offs, failures
    │   └── Wrap-up (3–5 min): summarize, limitations
    ├── Driving vs Following
    │   ├── Passive (L5): waits, answers, seeks validation
    │   └── Active (L6): sets agenda, narrates thinking, proposes next
    ├── 5 Explanation Patterns
    │   ├── Top-down: big picture → details
    │   ├── Bottom-up: components → how they fit
    │   ├── Chronological: follow the request
    │   ├── Comparative: option A vs B
    │   └── Problem–solution: challenge → solution
    └── Signposting
        ├── Transitions: "Now let me move on to…"
        ├── Depth: "Let me go deeper on…"
        └── Summary: "To recap…"
```
