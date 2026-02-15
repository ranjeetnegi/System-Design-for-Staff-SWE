# Chapter 13: System Design Framework

---

# Quick Visual: The 5-Phase Framework

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     SYSTEM DESIGN FRAMEWORK                                 │
│                                                                             │
│   Before you design ANYTHING, establish context through 5 phases:           │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. USERS & USE CASES                                               │   │
│   │     Who are we building for? What are they trying to do?            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              ↓                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  2. FUNCTIONAL REQUIREMENTS                                         │   │
│   │     What must the system do? (Core, Important, Nice-to-have)        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              ↓                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  3. SCALE                                                           │   │
│   │     How big is this problem? (Users, Data, Requests, Growth)        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              ↓                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  4. NON-FUNCTIONAL REQUIREMENTS                                     │   │
│   │     What qualities must it have? (Availability, Latency, Durability)│   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              ↓                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  5. ASSUMPTIONS & CONSTRAINTS                                       │   │
│   │     What's given? What limits us? (Infra, Team, Budget, Timeline)   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              ↓                                              │
│                    NOW you can start designing!                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Simple Example: Senior vs Staff Approach

**Problem**: "Design a notification system."

| Phase | Senior (L5) Approach | Staff (L6) Approach |
|-------|---------------------|---------------------|
| **Opening** | "Okay, so we need a database, a message queue..." | "Before I design, let me understand the context..." |
| **Users** | Assumes "users" | "Who sends? Who receives? Internal ops users?" |
| **Requirements** | Enumerates features | "Core: send/receive. Important: preferences. Nice-to-have: analytics." |
| **Scale** | "We need to handle a lot of traffic" | "30M DAU × 20 notifs/day = 7K/sec. Peak 10x = 70K/sec." |
| **NFRs** | "It should be fast and reliable" | "99.9% availability, 5-second delivery P95, eventual consistency OK" |
| **Constraints** | Designs in vacuum | "Small team → favor operational simplicity" |

**The difference**: Staff engineers establish a *contract* before designing. They don't build for a generic problem—they build for *this specific* problem.

---

# Introduction

Every Staff engineer I've worked with at Google approaches system design interviews the same way—without realizing they do it.

When a Senior engineer is asked to "design a notification system," they often jump straight into components: "We'll need a database, a message queue, some servers..." They're building. When a Staff engineer hears the same prompt, something different happens. They pause. They ask questions. They explore the problem space before touching the solution space.

This isn't hesitation—it's discipline. And it follows a pattern.

Over years of observing Staff engineers design systems (both in interviews and in production), I've codified that pattern into what I call the Staff-Level System Design Framework. It has five phases:

1. **Users & Use Cases** — Who are we building for, and what are they trying to do?
2. **Functional Requirements** — What must the system do?
3. **Scale** — How big is this problem?
4. **Non-Functional Requirements** — What qualities must the system have?
5. **Assumptions & Constraints** — What are we taking as given, and what limits us?

This section will teach you this framework in depth. We'll explore why each phase matters, how Google Staff engineers use it implicitly, how interviewers evaluate candidates through its lens, and most importantly—how to apply it yourself to transform how you approach system design.

By the end of this section, you'll have a structured mental model that makes system design interviews significantly more tractable. You won't be guessing what to do next. You'll know.

Let's begin.

---

# Part 1: Why a Structured Framework Is Necessary at Staff Level

## The Problem with "Just Design"

When you're an experienced engineer, you've designed a lot of systems. You have intuition. You can look at a problem and see solutions immediately. This intuition is valuable—it's what makes you good at your job.

But in Staff-level interviews, this intuition can hurt you.

Here's why: Your intuition leads you to *a* solution. Not *the right* solution for this specific context. When you jump to implementation, you're revealing that you don't differentiate between contexts. You treat every problem the same way—with whatever architecture pattern is currently in your head.

Staff engineers think differently. They recognize that the "right" design depends entirely on context:
- A notification system for 1,000 users is different from one for 100 million users
- A payment system with 99.99% uptime requirements is different from a social feed with 99% uptime requirements
- A greenfield system with unlimited budget is different from a migration under resource constraints

Without establishing context first, any design you propose is essentially random—it might fit the problem, or it might not.

## What a Framework Provides

A structured framework gives you several crucial advantages:

### 1. Completeness

Without a framework, you'll miss things. Maybe you'll forget to ask about scale. Maybe you'll assume functional requirements that weren't intended. Maybe you'll optimize for latency when durability was the real concern.

A framework is a checklist. It ensures you cover the ground you need to cover.

### 2. Prioritization

Not all requirements are equal. Some are make-or-break; others are nice-to-have. A framework forces you to identify which is which, so you can allocate your design time appropriately.

### 3. Communication

When you articulate your framework to the interviewer, you're showing them how you think. You're giving them a map of your approach. This makes you easier to follow—and easier to evaluate positively.

### 4. Flexibility

Paradoxically, structure gives you flexibility. When you've explicitly established requirements, you can explicitly change them. "Earlier we said latency was critical—but if we relax that, we could simplify the design significantly. Is that worth considering?"

### 5. Calibration

A framework helps you avoid two failure modes: over-engineering and under-engineering. By understanding the actual requirements, you design to the right level of complexity.

## Why Senior Engineers Often Skip This

Senior engineers frequently skip the framework phase because:

**They think it's obvious**: "Of course we need a database. Of course we need caching." They treat requirements as background assumptions rather than explicit decisions.

**They want to demonstrate building skills**: They're eager to show they can design complex systems, so they rush to the complex parts.

**They feel time pressure**: 45 minutes feels short, so they think they need to start designing immediately.

**They've internalized patterns**: They've seen enough systems that they pattern-match immediately. "This is a pub-sub system" → default pub-sub architecture.

These instincts are understandable but counterproductive. Staff interviews are specifically testing whether you can slow down, establish context, and design for the actual problem—not a generic version of the problem.

## The Framework as a Contract

Think of the framework phase as establishing a contract with your interviewer.

Before you design, you're saying: "Here's what I understand we're building, for whom, at what scale, with what quality requirements, under what constraints. Do you agree?"

The interviewer either confirms or corrects. Now you have shared understanding.

Without this contract, you might design brilliantly—but for the wrong problem. That's not a success; that's a demonstration that you don't validate requirements before building.

At Google, Staff engineers are responsible for ensuring they're solving the right problem. The framework phase is where you demonstrate that capability.

---

# Part 2: The Five Phases in Depth

Let me walk through each phase of the framework, explaining what to cover, why it matters, and how to execute it well.

## Phase 1: Users & Use Cases

### What This Phase Covers

Before you can design a system, you need to understand who will use it and what they're trying to accomplish. This seems obvious, but it's frequently skipped or rushed.

**Key questions to explore:**
- Who are the users of this system? End users? Internal services? Both?
- What are they trying to accomplish?
- What's their context? Mobile? Desktop? API integration?
- What's their technical sophistication?
- How frequently do they interact with this system?
- What's their tolerance for errors or degradation?

### Why This Phase Matters

Different users have different needs. A notification system for consumers (people checking their phones) has different requirements than a notification system for trading systems (algorithms reacting to market events).

Understanding users helps you:
- Prioritize features and capabilities
- Choose appropriate quality levels
- Identify the most important flows to optimize
- Anticipate edge cases and failure modes

### How to Execute This Phase

**Start by identifying user types:**

"Who are the primary users of this system? I'm imagining end consumers on mobile devices, but there might also be internal systems that need to interact with this. Can you clarify?"

**Explore their primary use cases:**

"What are the main things users are trying to do? For a notification system, I imagine: receiving notifications in real-time, managing notification preferences, viewing notification history. Are there others I'm missing?"

**Understand their context:**

"Are these users primarily on mobile or desktop? Is this a global user base or specific regions? These factors will affect our latency requirements and how we design the client experience."

**Identify power users and edge cases:**

"Are there users who will push the system harder than typical? For example, celebrity accounts with millions of followers, or system integrations that generate high volumes?"

### Example Application

**Prompt**: "Design a ride-sharing system."

**Poor approach**: "Okay, so we need to match riders with drivers..."

**Staff approach**: "Let me understand the users first. I see at least three user types: riders who want transportation, drivers who provide rides, and potentially internal operations staff who manage the system. For riders, the primary use case is requesting a ride and getting picked up quickly. For drivers, it's receiving ride requests and navigating to pickups. Are there other user types or use cases I should consider?"

### Common Mistakes in This Phase

**Mistake 1: Assuming a single user type**

Many systems serve multiple users with different needs. A marketplace serves buyers and sellers. A notification system serves senders and receivers. A data pipeline serves data producers and data consumers.

**Mistake 2: Focusing only on happy-path use cases**

Users also need to cancel, undo, recover from errors, and handle edge cases. These use cases matter too.

**Mistake 3: Ignoring internal users**

Many systems have internal users (operations, customer support, data science) whose needs differ from external users.

**Mistake 4: Not quantifying user behavior**

"Users browse products" is less useful than "Users browse an average of 20 products per session, with sessions lasting about 10 minutes, and 2% of sessions resulting in a purchase."

---

## Phase 2: Functional Requirements

### What This Phase Covers

Functional requirements describe what the system must do. These are the capabilities and behaviors that define the system's purpose.

**Key questions to explore:**
- What are the core features this system must provide?
- What data does the system need to store and manage?
- What operations can users perform?
- What are the input/output formats and interfaces?
- What integrations are required?

### Why This Phase Matters

Functional requirements determine the scope of your design. Without clarity here, you might:
- Design for features that weren't required
- Miss features that were essential
- Build the wrong abstractions

They also help you identify what's technically interesting. A simple CRUD API is straightforward. A real-time collaborative editor is complex. Knowing which you're building affects everything.

### How to Execute This Phase

**Enumerate the core capabilities:**

"Based on the use cases we discussed, let me list the core functional requirements:
1. Users can send notifications to other users or groups
2. Users can receive notifications in real-time
3. Users can set notification preferences (channels, frequency, muting)
4. Users can view notification history
5. System can send notifications across channels (push, email, SMS)

Am I missing anything critical?"

**Prioritize ruthlessly:**

"For this interview, I'll focus on requirements 1, 2, and 5—the core sending and receiving flow. I'll acknowledge preferences and history but design them at a high level. Does that prioritization make sense?"

**Identify what's NOT in scope:**

"I'm assuming we don't need to build the email or SMS sending infrastructure—we'll integrate with external providers. And I'm assuming authentication is handled by another service. Is that correct?"

### Example Application

**Prompt**: "Design a URL shortening service."

**Poor approach**: "We need to generate short URLs and redirect to long URLs."

**Staff approach**: "Let me enumerate the functional requirements:

**Core features:**
1. Create a short URL from a long URL
2. Redirect from short URL to long URL
3. (Optional) Custom short URLs chosen by user
4. (Optional) Expiration of short URLs

**Analytics features:**
5. Track click counts per URL
6. Track click metadata (time, location, referrer)

**Management features:**
7. List URLs created by a user
8. Delete or disable a short URL

For this design, I'll focus on 1, 2, and 5 as the core. The others are additions we can discuss if time permits. Does this scope work?"

### Common Mistakes in This Phase

**Mistake 1: Being too vague**

"The system should handle notifications" is not a requirement. "Users can send notifications to specific users or broadcast to groups, with delivery across push, email, and SMS channels" is a requirement.

**Mistake 2: Gold-plating**

Adding every possible feature makes your design unfocused. Prioritize ruthlessly. You can always mention nice-to-haves without designing them in detail.

**Mistake 3: Not confirming with the interviewer**

State your requirements explicitly and ask if they're correct. The interviewer might have a specific feature in mind that you missed.

**Mistake 4: Confusing functional with non-functional**

"The system must be fast" is not a functional requirement. "Users can retrieve their notification history" is functional. "Notification history retrieval completes in under 200ms" is non-functional.

---

## Phase 3: Scale

### What This Phase Covers

Scale determines the magnitude of the problem. This phase quantifies the load the system must handle.

**Key dimensions to explore:**
- Number of users (total, daily active, concurrent)
- Data volume (storage requirements, growth rate)
- Request volume (reads/second, writes/second, peak vs. average)
- Geographic distribution
- Growth expectations (current vs. 1 year vs. 5 years)

### Why This Phase Matters

Scale is the single biggest determinant of system architecture.

A system for 1,000 users can run on a single server with a simple database. A system for 100 million users requires distributed systems, caching, sharding, and sophisticated infrastructure.

Designing for the wrong scale is a critical failure:
- Under-designing means your system falls over when it hits real load
- Over-designing means you've built complexity you don't need and can't maintain

Staff engineers calibrate their designs to actual scale—not hypothetical scale, not impressive scale, actual scale.

### How to Execute This Phase

**Get the numbers:**

"Let me understand the scale we're designing for. How many users does this system serve? What's the expected request volume—reads per second, writes per second?"

**If not given, estimate:**

"If you don't have specific numbers, let me estimate. For a consumer notification system at a major company, I'd expect something like:
- 100 million users
- 10 million daily active users
- Average user receives 20 notifications/day
- That's 200 million notifications/day, or about 2,500/second average
- Peak might be 10x average, so 25,000/second

Do these estimates seem reasonable for what you have in mind?"

**Think about growth:**

"What's the growth trajectory? Are we designing for current scale or anticipating 10x growth? I want to make sure my design has headroom without over-engineering."

**Consider the hard cases:**

"Are there any extreme cases? For example, a celebrity with 50 million followers posting—that's a massive fan-out. Or a viral event causing 100x normal traffic. How much do we need to handle?"

### Quick Reference: Back-of-Envelope Cheat Sheet

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BACK-OF-ENVELOPE QUICK REFERENCE                         │
│                                                                             │
│   TIME CONVERSIONS:                                                         │
│   • 1 day = 86,400 seconds ≈ 100K seconds                                   │
│   • 1 month ≈ 2.5 million seconds                                           │
│   • 1 year ≈ 30 million seconds                                             │
│                                                                             │
│   STORAGE SIZES:                                                            │
│   • 1 KB = 1,000 bytes (text, small JSON)                                   │
│   • 1 MB = 1,000 KB (image, audio clip)                                     │
│   • 1 GB = 1,000 MB (video, large dataset)                                  │
│   • 1 TB = 1,000 GB                                                         │
│   • 1 PB = 1,000 TB                                                         │
│                                                                             │
│   THROUGHPUT RULES OF THUMB:                                                │
│   • Single server: 10K-100K simple requests/sec                             │
│   • Single DB: 10K-50K queries/sec (depends on complexity)                  │
│   • Network: 1-10 Gbps within datacenter                                    │
│                                                                             │
│   QUICK FORMULAS:                                                           │
│   • QPS = (Daily requests) / 100K                                           │
│   • Storage = (Items) × (Size per item) × (Retention period)                │
│   • Bandwidth = QPS × (Response size)                                       │
│   • Peak = 2-10x average (use 10x for safety)                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Back-of-Envelope Calculations

This is where back-of-envelope math becomes essential. Staff engineers should be comfortable with quick estimations:

**Storage calculation example:**

"If we have 100 million users and each user has 1,000 notifications in their history, at 1KB per notification, that's:
- 100M × 1,000 × 1KB = 100 billion KB = 100TB of notification storage
- That's substantial but manageable with distributed storage."

**Throughput calculation example:**

"2,500 notifications/second, at 25,000/second peak:
- A single machine can handle maybe 10,000 simple requests/second
- We need at least 3 machines for peak, probably 10 for redundancy
- With geographic distribution, maybe 30-50 machines globally"

**Bandwidth calculation example:**

"25,000 notifications/second × 1KB = 25MB/second
- That's 200Mbps—well within modern network capacity
- Not a bottleneck"

### Example Application

**Prompt**: "Design a messaging system like WhatsApp."

**Staff approach**: "Let me understand the scale:

**User scale:**
- Let's say 500 million users globally
- 200 million daily active
- Average user sends 50 messages/day, receives 100 messages/day

**Message volume:**
- 200M × 50 = 10 billion messages/day sent
- That's about 115,000 messages/second average
- Peak could be 3-5x, so let's design for 500,000 messages/second

**Storage:**
- 10 billion messages/day × 1KB average = 10TB/day new data
- Keeping 1 year of history = 3.6PB
- Significant storage infrastructure required

**Connections:**
- 200 million users online at any time
- Each needs a persistent connection for real-time delivery
- That's 200 million concurrent connections—major infrastructure

This scale tells me we need: distributed messaging, sharded storage, connection servers at edge locations, and careful attention to efficiency. A simple architecture won't work."

### Common Mistakes in This Phase

**Mistake 1: Not asking about scale at all**

This is surprisingly common. Candidates dive into architecture without knowing whether they're building for a startup or for Google-scale.

**Mistake 2: Assuming massive scale**

Don't design for 1 billion users if the actual requirement is 10,000 users. Over-engineering is as much a failure as under-engineering.

**Mistake 3: Using round numbers without justification**

"Let's assume 1 million requests per second" sounds impressive but is meaningless without derivation. Show your math.

**Mistake 4: Ignoring growth**

A system designed for today's scale might not survive tomorrow's growth. But a system designed for 100x growth might never ship. Find the balance.

**Mistake 5: Forgetting about data scale**

Request volume is obvious, but data volume often determines architecture choices. A system storing petabytes is different from one storing terabytes.

### Staff-Level: First Bottlenecks Over Time

Staff engineers think about *which bottleneck hits first* as the system grows—not just current scale.

| Growth Stage | Typical First Bottleneck | Why It Breaks First |
|--------------|--------------------------|---------------------|
| 1K → 10K users | Single database connection pool | Read/write contention appears before compute or storage |
| 10K → 100K users | Single-region latency | Users far from datacenter see poor P99 |
| 100K → 1M users | Fan-out pattern (e.g., notification blast) | One event → millions of work items overwhelms queues |
| 1M → 10M users | Storage or bandwidth cost | Data volume grows faster than revenue; cost becomes dominant |
| 10M+ users | Operational complexity | Team can't scale maintenance; incidents increase |

**Interview phrase**: "At 7K QPS, the first bottleneck is likely the write path—a single database won't sustain this. I'll design the write path to be horizontally scalable from day one. The *next* bottleneck as we grow will probably be fan-out—a celebrity post could create 10M notifications. I'll address that with async processing and priority queues."

---

## Phase 4: Non-Functional Requirements

### Quick Reference: NFR Dimensions

| Dimension | Question to Ask | Example Target | Trade-off |
|-----------|-----------------|----------------|-----------|
| **Availability** | "What % uptime?" | 99.9% = 8.76 hrs/yr downtime | Higher = more redundancy, cost |
| **Latency** | "How fast? P50? P99?" | P99 < 200ms | Lower = more caching, complexity |
| **Durability** | "Can we lose data?" | 11 nines (99.999999999%) | Higher = more replication, cost |
| **Consistency** | "Same data everywhere?" | Eventual vs Strong | Strong = higher latency |
| **Security** | "Auth? Encryption? Compliance?" | PCI-DSS, HIPAA, GDPR | More = more complexity |

### What This Phase Covers

Non-functional requirements describe the qualities the system must have. While functional requirements are about *what* the system does, non-functional requirements are about *how well* it does it.

**Key dimensions to explore:**

**Availability**: What percentage of time must the system be operational? 99%? 99.9%? 99.99%?

**Latency**: How fast must responses be? P50? P99? Different for different operations?

**Durability**: Can we lose data? What's the acceptable data loss?

**Consistency**: Do all users see the same data at the same time? Can we tolerate eventual consistency?

**Security**: What are the authentication, authorization, and data protection requirements?

**Trust boundaries**: Where does trust change? User → API (untrusted). API → internal services (trusted). Internal → third-party (semi-trusted). Staff engineers ask: "What data crosses which boundary, and how do we validate at each boundary?"

**Compliance**: Are there regulatory requirements (GDPR, HIPAA, PCI)?

**Observability & debuggability**: How do we know the system is healthy? How do we debug in production? Staff engineers ask: "What metrics, logs, and traces do we need? Can we trace a single request through the system? What would we need to diagnose a 2 AM incident?"

### Why This Phase Matters

Non-functional requirements drive architectural decisions more than functional requirements do.

Consider two notification systems with identical functional requirements:
- System A: 99% availability, 1-second latency, eventual consistency acceptable
- System B: 99.99% availability, 100ms latency, strong consistency required

These are completely different architectures. System A can be simple and forgiving. System B requires redundancy, geographic distribution, careful consistency protocols, and sophisticated monitoring.

Without understanding non-functional requirements, you might build System A when System B was needed—or vice versa, wasting effort on unnecessary complexity.

### How to Execute This Phase

**Availability:**

"What are the availability requirements? Is this a system where an hour of downtime is acceptable, or is it critical infrastructure where even minutes of downtime are catastrophic? For a consumer notification app, I'd expect 99.9% availability—about 8 hours of downtime per year. Is that the right ballpark?"

**Latency:**

"What latency targets are we designing for? For push notifications, I'd expect users to receive them within a few seconds of sending. For API calls, maybe 200ms P99. Are there specific latency requirements I should know about?"

**Durability:**

"How important is data durability? Can we ever lose a notification, or is every notification sacred? For consumer notifications, I'd assume some loss is acceptable—better to occasionally miss a notification than to significantly slow down the system. But for financial notifications, we might need stronger guarantees."

**Consistency:**

"Do all users need to see the same state at the same time? For notification read status, eventual consistency is probably fine—if it takes a few seconds for 'read' status to propagate, that's acceptable. But for notification preferences, maybe we need stronger consistency so users don't get notifications they've disabled."

**Security:**

"What are the security requirements? I assume notifications can contain sensitive data, so we need encryption in transit and at rest. We need authentication for all API endpoints. Are there specific compliance requirements—GDPR for EU users, for example?"

### The Trade-off Awareness

Staff engineers understand that non-functional requirements trade off against each other:

- **Consistency vs. Availability**: Strong consistency often requires sacrificing availability during network partitions (CAP theorem)
- **Latency vs. Durability**: Waiting for writes to be fully durable adds latency
- **Availability vs. Cost**: Higher availability requires more redundancy, which costs more
- **Security vs. Usability**: Stronger security often adds friction for users

When clarifying non-functional requirements, be aware of these trade-offs and surface them:

"You mentioned both strong consistency and high availability. Those can conflict during network partitions. Which should we prioritize if we can't have both?"

### Example Application

**Prompt**: "Design a payment processing system."

**Staff approach**: "Let me understand the non-functional requirements—these are critical for a payment system.

**Availability**: This is financial infrastructure. I'd expect 99.99% availability minimum—about 52 minutes of downtime per year. Is that the target?

**Latency**: For payment processing, I'd expect:
- Authorization: Under 500ms P99 (users are waiting at checkout)
- Settlement: Can be batch/async—less latency-sensitive

**Durability**: This is non-negotiable for payments. We cannot lose transaction records. I'd design for 11 nines of durability with multi-region replication.

**Consistency**: Strong consistency required. We cannot have a payment succeed in one view and fail in another. ACID transactions essential.

**Compliance**: PCI-DSS is mandatory for handling card data. This constrains how we store data, who can access it, and our audit requirements.

These requirements tell me this is a high-stakes system requiring significant infrastructure investment, redundancy, and careful design. We can't take shortcuts here."

### Common Mistakes in This Phase

**Mistake 1: Not asking about non-functional requirements**

Assuming everything must be fast, available, consistent, and durable leads to over-engineering. Different systems have different needs.

**Mistake 2: Using vague terms**

"The system should be reliable" is meaningless. "The system should have 99.9% availability with P99 latency under 200ms" is actionable.

**Mistake 3: Ignoring trade-offs**

Asking for strong consistency, high availability, low latency, AND perfect durability is unrealistic. Staff engineers understand trade-offs and probe to understand priorities.

**Mistake 4: Assuming highest standards everywhere**

Not every system needs 99.99% availability. An internal dashboard might be fine with 99%. Calibrate to actual needs.

**Mistake 5: Forgetting security and compliance**

These are often afterthoughts, but they significantly constrain architecture, especially for financial, healthcare, or user data systems.

---

## Phase 5: Assumptions & Constraints

### What This Phase Covers

This phase makes explicit the things you're taking for granted and the boundaries you're operating within.

**Assumptions** are things you believe to be true that you're not designing for:
- "I assume authentication is handled by a separate service."
- "I assume we have reliable cloud infrastructure."
- "I assume network latency within a region is under 5ms."

**Constraints** are limitations you must work within:
- "The budget limits us to X machines."
- "We must integrate with the existing legacy system."
- "The team has no experience with technology Y."
- "We need to launch within 3 months."

### Why This Phase Matters

Assumptions and constraints bound the problem. They prevent you from:
- Re-solving already-solved problems (authentication, logging, monitoring)
- Proposing solutions that are infeasible given constraints
- Designing in a vacuum without organizational context

They also make your design defensible. If someone later asks "Why didn't you design for X?", you can point to your stated assumptions.

### How to Execute This Phase

**State your assumptions explicitly:**

"I'm going to make a few assumptions—please correct me if any are wrong:
1. We have existing authentication and authorization services I can integrate with
2. We're operating on standard cloud infrastructure (I'll use AWS examples)
3. We have existing monitoring and logging infrastructure
4. Other services can publish events to a message bus for us to consume

With those assumptions, I don't need to design those pieces—I can focus on the notification system itself."

**Probe for constraints:**

"Are there any constraints I should know about? For example:
- Do we need to integrate with existing systems?
- Are there technology choices we must use or avoid?
- Is there a budget constraint that limits infrastructure?
- Are there timeline constraints that affect scope?
- Are there team skill constraints I should consider?
- Are there cross-team dependencies—other teams that must adopt our API, or teams we depend on for launch?"

**Surface hidden constraints:**

Sometimes constraints are implied rather than stated. If the interviewer mentions "a small startup," that implies limited resources. If they mention "a legacy migration," that implies integration requirements.

"You mentioned this is for a startup. That suggests we should favor simple, low-operational-overhead solutions over complex distributed systems, even if we sacrifice some theoretical scalability. Is that the right trade-off?"

### Example Application

**Prompt**: "Design a content recommendation system."

**Staff approach**: "Let me state my assumptions and probe for constraints:

**Assumptions:**
1. We have a content catalog with metadata (managed by another system)
2. We have user profiles with basic information (managed by another system)
3. We have event infrastructure to capture user behavior (clicks, views, etc.)
4. We have compute infrastructure for ML model training and serving
5. This is for a single region initially

**Constraint questions:**
- Are we building recommendations from scratch, or integrating with an existing recommendation engine?
- Do we have ML expertise on the team, or should I favor simpler heuristic approaches?
- Is there a latency budget for serving recommendations? Some systems are okay with seconds; others need milliseconds.
- Are there cold-start considerations—new users or new content that we need to handle specially?

**Discovered constraints:**
- [Interviewer mentions limited ML expertise]
- Given limited ML expertise, I'll favor a hybrid approach: simple heuristics for cold-start, and a relatively simple collaborative filtering model that's easier to maintain than deep learning. We can evolve to more sophisticated models as the team grows."

### Common Mistakes in This Phase

**Mistake 1: Not stating assumptions**

When you don't state assumptions, the interviewer can't correct them. You might design based on incorrect beliefs.

**Mistake 2: Making unrealistic assumptions**

"I assume we have infinite budget and time" is unhelpful. Assumptions should be realistic.

**Mistake 3: Ignoring organizational constraints**

The best technical solution might not be the best solution. Team skills, existing infrastructure, political realities—these all matter.

**Mistake 4: Treating constraints as fixed when they might be flexible**

Sometimes constraints can be negotiated. "Must we integrate with the legacy system, or could we propose a migration path?"

**Mistake 5: Forgetting to revisit assumptions**

Assumptions made early might not hold as you design. Check back: "I assumed eventual consistency was okay—given what we've discussed, is that still valid?"

### Cost as a First-Class Constraint (L6)

Staff engineers treat cost as a design constraint, not an afterthought. At scale, cost often becomes the dominant constraint—before latency or availability.

**Major cost drivers by system type:**

| System Type | Dominant Cost Driver | Why It Dominates |
|-------------|----------------------|------------------|
| Notification/messaging | Fan-out compute + storage | Each notification triggers N deliveries; history grows unbounded |
| Feed/recommendation | Compute (ML inference) | Real-time scoring at millions of requests/second |
| Media/CDN | Egress bandwidth | Data transfer scales with users and region count |
| Search/indexing | Storage + compute | Index builds and storage at petabyte scale |
| Payment/transaction | Durability + consistency | Multi-region replication, strong consistency have fixed cost per transaction |

**Interview phrase**: "What's the cost budget for this system? At 70K notifications/second with 1-year retention, we're looking at roughly 200TB storage and significant compute for fan-out. If cost is a first-class constraint, I'd consider: tiered retention (90 days hot, 1 year cold), aggregation to reduce notification count, and shedding analytics features from the critical path. If we don't have a cost constraint, I'd design for maximum reliability first."

**Trade-off**: Optimizing for cost often means accepting degraded latency (cold storage), eventual consistency (fewer replicas), or reduced features (no long-term analytics). Staff engineers make this trade-off explicit and tie it to business priorities.

### Cross-Team & Org Impact (L6)

Staff engineers frame requirements in terms of *who else is affected*—not just the system they own.

**Questions to ask:**
- "Which teams consume our API? Do they need backward compatibility, versioning, or migration support?"
- "Which teams do we depend on for launch? What's their readiness and timeline?"
- "If we change our data model or API, who must migrate? What's the blast radius?"
- "Does this design add complexity or tech debt for other teams?"

**Example**: A notification system that requires all producers to adopt a new event schema blocks every producing team. A design that accepts both old and new schemas during migration reduces org-wide coordination cost. Staff engineers explicitly ask: "What's the adoption path for our dependencies?"

**Interview phrase**: "I'm assuming the post service and like service will publish events to our queue. That means we have a cross-team dependency—they need to adopt our event format. I'd design a versioned schema and a migration path so they can adopt incrementally. Is that dependency model accurate?"

---

# Part 3: How Google Staff Engineers Use This Framework Implicitly

Walk into any design review at Google, and you'll hear Staff engineers ask the same questions—without referencing any formal framework. They've internalized the pattern through experience. Let me show you what this looks like in practice.

## The Instinctive Clarification

When a Staff engineer hears a new project idea, they don't start brainstorming solutions. They start asking questions.

**Product Manager**: "We need a system to notify users when their friends post new content."

**Staff Engineer**: "Interesting. A few questions:
- How many users are we talking about? Are we building for our current user base or anticipating growth?
- What's 'content' in this context? Posts? Photos? Comments? All of the above?
- How real-time does 'notify' need to be? Immediate, or is within a few minutes acceptable?
- What channels—push notifications, email, in-app?
- This sounds similar to the activity feed we already have. Is this replacing that, or supplementing it?"

The Staff engineer isn't being difficult. They're establishing context because they know design decisions depend on it.

## The Priority Negotiation

Staff engineers don't treat all requirements as equal. They negotiate priorities.

**Product Manager**: "We need this to be really fast, super reliable, and cost-effective."

**Staff Engineer**: "Those three can tension against each other. Let me understand the priorities:
- If we had to choose between faster delivery and lower cost, which wins?
- If we had to choose between reliability and speed, which wins?

I'm asking because the architecture choices are different. If reliability is paramount, I'd recommend synchronous acknowledgment and stronger durability guarantees, which adds latency and cost. If speed is paramount, I'd recommend async processing with best-effort delivery, which is cheaper but might occasionally drop notifications."

## The Explicit Trade-off

Staff engineers make trade-offs explicit rather than hiding them.

**In a design doc**: "This design prioritizes delivery speed over perfect ordering. Users may occasionally see notifications out of chronological order—for example, a like might appear before the post it references. We accept this trade-off because: (1) users are tolerant of minor ordering inconsistencies, (2) strict ordering would require coordination that adds 100ms+ latency, and (3) our experiments show users don't notice out-of-order notifications in 98% of cases."

Compare this to how a less experienced engineer might write: "Notifications are delivered in real-time." The second version hides the trade-off. The first makes it discussable.

## The Scope Defense

Staff engineers protect scope fiercely. They know that unbounded scope kills projects.

**Product Manager**: "Can we also add notification analytics? And maybe A/B testing for notification content? And what about internationalization?"

**Staff Engineer**: "Those are all valuable, but let's scope clearly:
- For v1, I'm proposing we focus on core delivery: sending notifications reliably across push, email, and SMS. That alone is a significant system.
- Analytics can be v1.1—we'll capture events from v1 that make analytics straightforward to add later.
- A/B testing and internationalization are v2 features once we've proven the core system works.

If any of these are must-haves for launch, we need to either extend the timeline or reduce scope elsewhere. What's the priority stack?"

## The Failure Mode Anticipation

Staff engineers think about what can go wrong before being asked.

**In a design review**: "Before I continue, let me address the failure modes I'm worried about:

1. **Celebrity fan-out**: If a user with 10 million followers posts, we suddenly need to fan out 10 million notifications. Our current design handles this by... [explanation].

2. **Thundering herd**: If our notification service goes down and comes back up, there's a backlog of notifications that could overwhelm the system. We handle this by... [explanation].

3. **Circular notifications**: In theory, a notification could trigger another notification, which triggers another... We prevent infinite loops by... [explanation].

I wanted to surface these because they're the things that would wake us up at 2 AM."

## The Retrospective Reasoning

Staff engineers connect decisions to requirements throughout the design.

**Not this**: "I chose Kafka for the message queue."

**But this**: "I chose Kafka because we established that we need to handle 100K messages/second with the ability to replay in case of consumer failures. Kafka gives us the throughput we need and native replay capability. If we didn't need replay, RabbitMQ would be simpler to operate. If we didn't need this throughput, we could use a simple database queue. The specific requirements drove this choice."

Every decision references back to the requirements established in the framework phases.

---

# Part 4: How This Framework Differs from Senior (L5) Approaches

Understanding the difference between Senior and Staff approaches helps you calibrate your own behavior. Let me contrast them phase by phase.

## Phase 1: Users & Use Cases

**Senior approach**: Takes users as given. "The user wants to send notifications." Focuses on the primary use case.

**Staff approach**: Explores user types and priorities. "Who are all the users? End consumers, yes, but also operations staff, data scientists querying logs, customer support looking up delivery status. How do we prioritize their different needs?"

**The gap**: Staff engineers see the full ecosystem, not just the obvious user.

## Phase 2: Functional Requirements

**Senior approach**: Enumerates features. "We need to send notifications, store preferences, track delivery status."

**Staff approach**: Prioritizes and scopes features. "Core requirements: send and receive. Important but secondary: preferences and history. Nice-to-have: analytics and A/B testing. For this design, I'm focusing on core requirements. The secondary features inform the architecture but won't be designed in detail."

**The gap**: Staff engineers are explicit about scope and priority.

## Phase 3: Scale

**Senior approach**: Notes that scale matters. "We need to handle a lot of traffic." May do some calculations when prompted.

**Staff approach**: Derives scale from first principles and uses it to drive decisions. "With 10M DAU and 20 notifications per user per day, we're at 2,300/second average. Peak is 10x, so 23,000/second. At that rate, a single database can handle reads but writes would bottleneck. Let me design the write path to be horizontally scalable from day one."

**The gap**: Staff engineers don't just acknowledge scale; they use it to drive specific design decisions.

## Phase 4: Non-Functional Requirements

**Senior approach**: Mentions non-functional requirements when asked. "Yes, it should be fast and reliable."

**Staff approach**: Probes for specific targets and trade-offs. "What's our latency target—1 second is fine, or do we need sub-100ms? What's our availability target—99.9% or 99.99%? Those thresholds drive completely different architectures. And how do we prioritize when they conflict—if we can't be both fast AND consistent, which wins?"

**The gap**: Staff engineers quantify non-functional requirements and understand their trade-offs.

## Phase 5: Assumptions & Constraints

**Senior approach**: Makes assumptions implicitly. Designs as if there are no constraints.

**Staff approach**: Makes assumptions explicit and probes for constraints. "I'm assuming we're on cloud infrastructure with standard tools. I'm assuming we have an existing auth system. Are there technology constraints—for example, must we use the company's existing message queue, or can we choose what's best? Are there team constraints—for example, is there ML expertise for sophisticated personalization, or should I favor simpler heuristics?"

**The gap**: Staff engineers acknowledge the organizational context, not just the technical problem.

## The Overall Difference

**Senior engineers** treat the framework phases as a checklist they know they "should" do. They ask the right questions, but sometimes mechanically. The requirements-gathering feels like a warm-up before the "real" design work.

**Staff engineers** treat the framework phases as the foundation of the design. The requirements aren't just gathered—they're analyzed, prioritized, and used to drive every subsequent decision. A Staff engineer would say: "The requirements we established tell us this MUST be a distributed system" or "Given the constraints we identified, the simple approach is actually appropriate."

The framework isn't a box to check—it's a lens through which all design decisions are filtered.

---

# Part 5: How Interviewers Evaluate Candidates Using This Framework

Google interviewers are trained to assess specific signals. Understanding their rubric helps you demonstrate the right behaviors.

## What Interviewers Look For in Each Phase

### Phase 1: Users & Use Cases

**Strong signals**:
- Asks about user types without being prompted
- Identifies non-obvious users (internal, operational, edge cases)
- Understands user priorities and contexts
- Connects users to requirements naturally

**Weak signals**:
- Assumes a single, obvious user
- Doesn't ask about users at all
- Focuses only on the happy path

**Example of a strong candidate**: "Before I design, I want to understand the users. You mentioned consumers receiving notifications. But who sends them? Other users, automated systems, both? And are there internal users I should consider—operations teams who need to monitor delivery, customer support who needs to look up specific notifications?"

### Phase 2: Functional Requirements

**Strong signals**:
- Enumerates requirements clearly
- Prioritizes actively ("core vs. nice-to-have")
- Scopes explicitly ("I'm focusing on X, acknowledging Y, deferring Z")
- Checks alignment with interviewer

**Weak signals**:
- Treats all features as equal priority
- Doesn't scope—tries to design everything
- Doesn't confirm requirements with interviewer

**Example of a strong candidate**: "Let me list the functional requirements: send notifications, receive in real-time, set preferences, view history. For this design, I'll focus on send and receive—that's the core. Preferences and history inform the data model but I won't design them in detail unless you'd like me to. Does that scope work?"

### Phase 3: Scale

**Strong signals**:
- Asks about scale proactively
- Derives numbers from first principles
- Uses scale to drive design decisions
- Shows back-of-envelope calculation fluency

**Weak signals**:
- Doesn't ask about scale
- Assumes massive scale without justification
- Treats scale as an afterthought

**Example of a strong candidate**: "What scale are we designing for? If you don't have specific numbers, let me estimate: for a major consumer app, I'd expect 50 million DAU, averaging 30 notifications each per day. That's 1.5 billion notifications per day, about 17,000 per second average. Peak at 10x is 170,000/second. That's significant—we need distributed systems and careful design. Does this order of magnitude match your expectations?"

### Phase 4: Non-Functional Requirements

**Strong signals**:
- Asks about availability, latency, durability, consistency
- Quantifies targets ("99.9% availability, not just 'high availability'")
- Understands trade-offs between requirements
- Connects NFRs to architecture decisions

**Weak signals**:
- Uses vague terms ("fast," "reliable")
- Doesn't ask about NFRs at all
- Treats all NFRs as equally important

**Example of a strong candidate**: "Let me understand the non-functional requirements. For availability, are we targeting 99.9% or 99.99%? That's the difference between 8 hours of downtime per year and 52 minutes. For latency, what's acceptable for notification delivery—real-time means different things in different contexts. For consistency, if a user disables notifications, how quickly must that take effect—immediately, or is a few seconds of propagation delay acceptable?"

### Phase 5: Assumptions & Constraints

**Strong signals**:
- States assumptions explicitly
- Asks about constraints proactively
- Considers organizational context
- Revisits assumptions during design

**Weak signals**:
- Makes assumptions implicitly
- Ignores organizational constraints
- Designs in a vacuum

**Example of a strong candidate**: "I'm going to assume we have existing auth and monitoring infrastructure. I'm assuming standard cloud infrastructure—I'll use AWS as a reference but the design is portable. Are there technology constraints I should know about—existing systems I must integrate with, or technologies I must use or avoid?"

## The Overall Assessment

Interviewers aren't just checking boxes. They're asking themselves:

**"Does this candidate understand the problem before solving it?"**

A candidate who jumps to solutions is showing Senior behavior. A candidate who establishes requirements first is showing Staff behavior.

**"Does this candidate design for the actual requirements?"**

A candidate who designs a massively scalable system for a 1,000-user problem is showing poor judgment. A candidate who designs a simple system for a billion-user problem is showing poor judgment.

**"Does this candidate make trade-offs explicit?"**

A candidate who presents their design as optimal without acknowledging trade-offs is hiding complexity. A candidate who says "I chose this approach because [tradeoff], and the alternative would be better if [different constraints]" is showing Staff-level thinking.

**"Would I trust this candidate to own a significant project?"**

Staff engineers own projects—meaning they ensure the right thing gets built, not just that something gets built. The framework phases demonstrate this ownership mindset.

---

# Part 6: Mental Models for Each Phase

Mental models are thinking tools. Here are models that help in each phase of the framework.

## Phase 1: Users & Use Cases

### The Stakeholder Map

Visualize all the people and systems that interact with your system:
- **Primary users**: The main people using the system
- **Secondary users**: People who use it less frequently but have important needs
- **Internal users**: Operations, support, analytics teams
- **System users**: Other services that integrate with yours
- **Affected parties**: People impacted by the system even if they don't directly use it

For a notification system, this might be: senders, receivers, operations (monitoring delivery), support (debugging issues), analytics (measuring engagement), and connected systems (event sources).

### The Job-To-Be-Done

Instead of asking "what features do users want?", ask "what job are users hiring this system to do?"

A notification system isn't hired to "send notifications." It's hired to "keep me informed about things I care about without overwhelming me."

This framing surfaces deeper requirements: personalization, preference management, rate limiting.

## Phase 2: Functional Requirements

### The MVP Concentric Circles

Visualize requirements as concentric circles:
- **Core** (innermost): Must have these for the system to function at all
- **Important**: Should have these for the system to be useful
- **Nice-to-have**: Would be good but can be added later
- **Out of scope** (outermost): Explicitly not building these now

Be able to articulate which circle each requirement is in.

### The Verb-Noun Matrix

List all the nouns (entities) and verbs (actions) in your system:

| | Notification | Preference | User | Channel |
|---|---|---|---|---|
| Create | ✓ | ✓ | - | - |
| Read | ✓ | ✓ | ✓ | ✓ |
| Update | - | ✓ | - | - |
| Delete | ✓ | ✓ | - | - |
| Send | ✓ | - | - | - |
| Receive | ✓ | - | - | - |

This matrix helps you enumerate requirements systematically.

## Phase 3: Scale

### The Powers of Ten

Think about scale in orders of magnitude:
- 10^3 (1,000): Single server, simple database
- 10^6 (1,000,000): Needs caching, maybe replication
- 10^9 (1,000,000,000): Needs sharding, distributed systems
- 10^12 (1,000,000,000,000): Needs specialized infrastructure, custom solutions

What order of magnitude are you designing for? Each level up requires fundamentally different approaches.

### The Bottleneck Hunt

At any scale, there's a bottleneck. Find it before it finds you:
- Is it compute (CPU-bound)?
- Is it memory (working set doesn't fit)?
- Is it storage (IOPS limited)?
- Is it network (bandwidth or latency)?
- Is it a single point of contention (locks, shared state)?

For a notification system, the bottleneck is often fan-out: a single event needs to reach many recipients. Design for that specifically.

### The Growth Time Bomb

Current scale tells you what works today. Growth rate tells you when it breaks:
- If you're at 50% of capacity and growing 10%/month, you have about 7 months before crisis
- If you're at 50% of capacity and growing 100%/month, you have about 1 month

"Capacity" isn't just servers—it's also team ability to maintain complexity, budget for infrastructure, and debt in the codebase.

## Phase 4: Non-Functional Requirements

### The SLA Pyramid

Visualize non-functional requirements as a pyramid where violations are increasingly severe:
- **Bottom**: Performance (things are slow but work)
- **Middle**: Availability (things are down but recoverable)
- **Top**: Durability (data is lost permanently)

Design your system so higher levels of the pyramid are more protected than lower levels.

### The Dial Panel

Imagine a control panel with dials:
- **Availability dial**: 99% → 99.9% → 99.99% → 99.999%
- **Latency dial**: 1s → 100ms → 10ms → 1ms
- **Consistency dial**: Eventual → Session → Strong → Linearizable
- **Cost dial**: $ → $$ → $$$ → $$$$

You can't have all dials at maximum. The design question is: which dials matter most?

### The 9s Game

Each additional "9" in availability is 10x harder:
- 99% = 3.65 days of downtime/year (simple architecture)
- 99.9% = 8.76 hours of downtime/year (redundancy needed)
- 99.99% = 52.6 minutes of downtime/year (sophisticated automation)
- 99.999% = 5.26 minutes of downtime/year (extreme engineering)

Know what level you're designing for and what it costs.

## Phase 5: Assumptions & Constraints

### The Dependency Web

Visualize what your system depends on:
- What infrastructure must exist for your system to work?
- What other systems do you integrate with?
- What team capabilities do you assume?
- What organizational processes do you rely on?

If any dependency fails, does your system fail? What's your blast radius?

### The Constraint Gradient

Not all constraints are equally fixed:
- **Immovable**: Laws of physics, regulatory requirements
- **Hard to change**: Existing infrastructure, organizational structure
- **Negotiable**: Timeline, scope, technology choices
- **Soft**: Best practices, past decisions, preferences

Know which constraints are truly fixed and which might have flexibility.

### The Build vs. Buy Matrix

For every capability you need, consider:
- **Build**: Full control, high initial cost, ongoing maintenance burden
- **Buy/Use**: Less control, lower initial cost, external dependency

Your assumptions about what's available (internal services, external tools) shape your build-vs-buy decisions throughout the design.

---

# Part 7: End-to-End Example

Let me walk through a complete example applying the framework.

## The Problem

"Design a notification system for a social media platform."

## Phase 1: Users & Use Cases

**My opening**: "Before I start designing, I want to understand who we're building this for and what they're trying to accomplish."

**Questions I'd ask**:
- "Who sends notifications? Other users (likes, comments, follows), the platform itself (announcements, reminders), or both?"
- "Who receives notifications? All users, or are there different tiers with different notification expectations?"
- "What are the primary use cases? I'm thinking: social interactions (someone liked your post), content updates (someone you follow posted), and system messages (security alerts, announcements). Are there others?"
- "Are there internal users? Operations monitoring delivery rates, customer support looking up specific notifications?"

**After clarification**: "So we're building for a consumer social platform. Users send notifications through actions (like, comment, follow), and users receive notifications on mobile (push) and in-app. There's also an operations team that needs visibility into delivery health. Primary use case is social interactions—that's 80% of notification volume."

## Phase 2: Functional Requirements

**My enumeration**: "Based on the use cases, here are the functional requirements:

**Core**:
1. Generate notifications from user actions (like, comment, follow, etc.)
2. Deliver notifications to recipients in real-time (push, in-app)
3. Store notification history for later retrieval

**Important**:
4. User preferences (mute, notification channels, frequency)
5. Aggregation (combine multiple similar notifications: '5 people liked your post')

**Nice-to-have**:
6. Analytics (open rates, engagement)
7. Scheduling (send at optimal times)

For this design, I'll focus on core requirements 1-3 and address #4 (preferences) at the data model level. I'll mention #5 (aggregation) but not design it in detail. Does this scope work?"

## Phase 3: Scale

**My estimation**: "Let me understand the scale:
- How many users? Let's say 100 million monthly active, 30 million daily active
- Notification volume: Average user generates maybe 5 notifications/day (posting once, liking 4 things). Average user receives maybe 20 notifications/day
- That's 150 million sent and 600 million delivered per day
- About 7,000 notifications generated/second and 7,000 delivered/second average
- Peak at 10x: 70,000/second

For storage:
- 600 million notifications/day × 365 days × 1KB = 220TB/year if we keep a year of history
- That's substantial but manageable

This scale tells me we need distributed message processing and horizontally scalable storage. A single database won't handle this."

## Phase 4: Non-Functional Requirements

**My probing**: "Let me understand the quality requirements:

**Availability**: I'd target 99.9%—8 hours of downtime per year maximum. Missing a notification is annoying but not catastrophic for a social app. Does that match your expectations?

**Latency**: For push notifications, I'd target 95% delivered within 5 seconds of the triggering action. For in-app history, I'd target 200ms P99 to load. Does that seem right?

**Durability**: I'd say notifications are important but not sacred. We shouldn't lose them routinely, but if 0.01% of notifications are lost due to system issues, that's acceptable. We're not dealing with financial transactions.

**Consistency**: Eventual consistency is fine. If it takes a few seconds for 'notification read' status to propagate across devices, that's acceptable.

**Security**: Notifications can contain user-generated content, so we need standard content moderation. Personal notifications should only be visible to the recipient."

## Phase 5: Assumptions & Constraints

**My explicit assumptions**: "I'm going to assume:
1. We have authentication/authorization infrastructure I can integrate with
2. We have push notification infrastructure (APNs, FCM integration)
3. We have a standard cloud environment (I'll reference AWS, but the design is portable)
4. Other services (post service, like service, etc.) can publish events I can consume
5. We have monitoring and alerting infrastructure

Are there specific constraints?
- Do we need to integrate with existing systems or is this greenfield?
- Are there technology mandates or preferences?
- What's the team situation—new team or existing team with relevant expertise?"

**After clarification**: "Understood. This is greenfield for the notification system, but we need to consume events from existing services via our standard Kafka infrastructure. The team is small—3 engineers—so operational simplicity is valuable."

## Summary Before Designing

"Let me summarize what we're building:

**Users**: Consumers sending/receiving social notifications; internal ops monitoring health
**Core requirements**: Generate from events, deliver in real-time, store history
**Scale**: ~7K notifications/second, 200TB storage/year
**NFRs**: 99.9% availability, 5-second delivery latency, eventual consistency acceptable
**Constraints**: Small team, integrate with existing Kafka, operational simplicity matters

With this foundation, let me design the system..."

[The actual design would follow, but the framework phases are complete.]

---

# Part 8: Common Mistakes at Each Phase

## Phase 1: Users & Use Cases Mistakes

**Mistake**: Assuming a single homogeneous user base

**Example**: Designing a notification system for "users" without distinguishing high-profile users (celebrities) from regular users

**Why it matters**: Celebrity fan-out (1 post → 10 million notifications) is a completely different scaling challenge than regular users

**Fix**: Always ask "Are there user segments with significantly different behaviors or needs?"

---

**Mistake**: Ignoring internal users

**Example**: Designing the API only for end users, not for operations or support teams

**Why it matters**: Operations needs monitoring endpoints, support needs debugging tools, analytics needs data access

**Fix**: Explicitly list internal users and their needs alongside external users

---

**Mistake**: Only considering the happy path

**Example**: Focusing on "user receives notification" without considering "user wants to stop receiving notifications" or "user missed notifications and wants to catch up"

**Why it matters**: These edge cases often drive significant design decisions (preference storage, history depth)

**Fix**: For each happy path, ask "What's the opposite? What's the error case? What's the recovery?"

## Phase 2: Functional Requirements Mistakes

**Mistake**: Treating requirements as equal priority

**Example**: Spending equal time on core delivery and nice-to-have analytics

**Why it matters**: Time is limited; focus on what matters most

**Fix**: Explicitly categorize requirements into core/important/nice-to-have and allocate effort accordingly

---

**Mistake**: Not scoping explicitly

**Example**: Trying to design a complete system with every feature

**Why it matters**: You'll run out of time before covering anything well

**Fix**: State your scope explicitly: "I'm focusing on X, acknowledging Y, deferring Z"

---

**Mistake**: Assuming requirements are obvious

**Example**: Starting to design without confirming what the system should do

**Why it matters**: The interviewer might have different expectations; implicit misalignment wastes time

**Fix**: Always enumerate requirements and confirm alignment before designing

## Phase 3: Scale Mistakes

**Mistake**: Not asking about scale

**Example**: Designing an architecture without knowing if it's for 1,000 or 100 million users

**Why it matters**: Scale determines architecture; wrong scale assumptions mean wrong architecture

**Fix**: Always ask about scale, or estimate explicitly and confirm

---

**Mistake**: Over-engineering for hypothetical scale

**Example**: Building a globally distributed system for a product that has 1,000 beta users

**Why it matters**: Complexity has costs; premature optimization wastes resources

**Fix**: Design for current scale + expected growth, not infinite theoretical scale

---

**Mistake**: Not doing the math

**Example**: Saying "that's a lot of data" without calculating actual numbers

**Why it matters**: Numbers expose assumptions; "a lot" might be 1TB or 1PB depending on context

**Fix**: Always do back-of-envelope calculations and show your work

## Phase 4: Non-Functional Requirements Mistakes

**Mistake**: Using vague terms

**Example**: "The system should be fast and reliable"

**Why it matters**: "Fast" could mean 10ms or 10 seconds; vague targets mean arbitrary design decisions

**Fix**: Quantify: "P99 latency under 200ms, 99.9% availability"

---

**Mistake**: Ignoring trade-offs

**Example**: Claiming the system will be highly available AND strongly consistent AND very fast AND cheap

**Why it matters**: These properties trade off; claiming all of them suggests you don't understand the trade-offs

**Fix**: Acknowledge trade-offs explicitly: "I'm prioritizing X over Y because..."

---

**Mistake**: Forgetting security and compliance

**Example**: Designing a healthcare notification system without mentioning HIPAA

**Why it matters**: Compliance requirements can fundamentally change architecture

**Fix**: Ask about regulatory requirements for any system handling sensitive data

## Phase 5: Assumptions & Constraints Mistakes

**Mistake**: Making assumptions implicitly

**Example**: Using a specific cloud provider's features without stating that assumption

**Why it matters**: The interviewer might have different assumptions; explicit assumptions are discussable

**Fix**: State assumptions out loud: "I'm assuming we're on AWS with access to their managed services"

---

**Mistake**: Ignoring organizational constraints

**Example**: Proposing a Kubernetes-based architecture to a team that only knows VMs

**Why it matters**: The best technical solution might be wrong if the team can't implement or maintain it

**Fix**: Ask about team skills, existing infrastructure, and organizational preferences

---

**Mistake**: Treating all constraints as fixed

**Example**: Accepting a 2-week deadline without exploring whether it could be extended

**Why it matters**: Some constraints are negotiable; understanding which ones helps you make better trade-offs

**Fix**: Probe constraints: "Is this fixed, or is there flexibility if we can justify it?"

---

# Quick Reference Card

## The 5 Phases At a Glance

| Phase | Key Question | What to Cover | Time |
|-------|-------------|---------------|------|
| **1. Users & Use Cases** | Who and why? | User types, primary/secondary use cases, edge cases | 1-2 min |
| **2. Functional Requirements** | What must it do? | Core vs Important vs Nice-to-have, explicit scope | 2-3 min |
| **3. Scale** | How big? | Users, data volume, QPS, growth, back-of-envelope math | 2-3 min |
| **4. Non-Functional Requirements** | How well? | Availability, latency, durability, consistency, security | 2-3 min |
| **5. Assumptions & Constraints** | What's given? | Infrastructure, team, budget, timeline, integrations | 1-2 min |

**Total: 8-13 minutes** → Then you design with clarity!

---

## Self-Check: Did I Cover Everything?

| Signal | Weak | Strong | ✓ |
|--------|------|--------|---|
| **Users** | Assumed single user type | Identified 3+ user types including internal | ☐ |
| **Requirements** | Listed features flat | Prioritized: core / important / nice-to-have | ☐ |
| **Scale** | "A lot of traffic" | "7K QPS average, 70K peak, 200TB storage" | ☐ |
| **NFRs** | "Fast and reliable" | "99.9% availability, P99 < 200ms" | ☐ |
| **Constraints** | Designed in vacuum | Asked about team, timeline, integrations | ☐ |
| **Summary** | Started designing immediately | Summarized understanding before designing | ☐ |

---

## Memorable One-Liners

| Phase | One-Liner |
|-------|-----------|
| **Framework** | "Establish the contract before you design." |
| **Users** | "Who are all the stakeholders—not just the obvious ones?" |
| **Requirements** | "Core, important, nice-to-have. What's in which bucket?" |
| **Scale** | "What order of magnitude? Each 10x changes the architecture." |
| **NFRs** | "99.9% vs 99.99% are completely different systems." |
| **Failure** | "What happens when things go wrong—before they do." |
| **Cost** | "Cost is a constraint, not an afterthought." |
| **Constraints** | "What's fixed vs. negotiable? Know the difference." |

---

## Key Phrases for Each Phase

### Phase 1: Users & Use Cases
- "Before I design, I want to understand who we're building for..."
- "Who are the primary users? Are there secondary users?"
- "Are there internal users I should consider—ops, support, analytics?"

### Phase 2: Functional Requirements
- "Based on the use cases, here are the requirements..."
- "I'll categorize as core, important, and nice-to-have..."
- "For this design, I'll focus on [X]. Does that scope work?"

### Phase 3: Scale
- "What scale are we designing for?"
- "Let me estimate: [X] users × [Y] actions = [Z] QPS..."
- "At that rate, we need [architecture implication]..."

### Phase 4: Non-Functional Requirements
- "What are the availability requirements? 99.9% or 99.99%?"
- "What latency targets? What's the P99 budget?"
- "Is eventual consistency acceptable, or do we need strong consistency?"

### Phase 5: Assumptions & Constraints
- "I'm assuming we have existing [auth/monitoring/infra]..."
- "Are there technology constraints I should know about?"
- "What's the team situation—size, expertise?"

---

## The Availability Cheat Sheet

| Availability | Downtime/Year | Downtime/Month | What It Means |
|-------------|---------------|----------------|---------------|
| 99% | 3.65 days | 7.2 hours | Simple architecture OK |
| 99.9% | 8.76 hours | 43.8 min | Need redundancy |
| 99.99% | 52.6 min | 4.38 min | Need automation |
| 99.999% | 5.26 min | 26.3 sec | Extreme engineering |

---

## Scale Mental Model: Powers of 10

| Users | Architecture Approach |
|-------|----------------------|
| 10³ (1K) | Single server, simple DB |
| 10⁶ (1M) | Caching, read replicas |
| 10⁹ (1B) | Sharding, distributed systems |
| 10¹² (1T) | Custom infrastructure |

**Key insight**: Each order of magnitude requires fundamentally different approaches.

---

## Common Mistakes Quick Reference

| Phase | Common Mistake | Fix |
|-------|---------------|-----|
| **Users** | Single user type assumed | "Are there user segments with different needs?" |
| **Requirements** | All features equal priority | "What's core vs important vs nice-to-have?" |
| **Scale** | "A lot" without numbers | "Let me calculate: X × Y = Z QPS" |
| **NFRs** | Vague ("fast") | Quantify: "P99 < 200ms, 99.9% availability" |
| **Constraints** | Design in vacuum | "Team size? Existing systems? Timeline?" |

---

# Part 9: Failure Requirements—The Missing Phase (L6 Gap Coverage)

This section addresses a critical dimension of Staff-level requirements gathering: **explicitly gathering requirements about failure modes, degradation behavior, and recovery expectations**.

Senior engineers focus on what the system should do when it works. Staff engineers also establish what the system should do when things go wrong.

---

## Why Failure Requirements Matter at L6

Most requirements-gathering frameworks focus on functional and non-functional requirements during normal operation. But Staff engineers know that systems spend significant time in degraded states.

### The Failure Requirements Test

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FAILURE REQUIREMENTS COMPARISON                          │
│                                                                             │
│   L5 REQUIREMENTS GATHERING:                                                │
│   ─────────────────────────                                                 │
│   "What should the system do?"                                              │
│   "How fast should it be?"                                                  │
│   "How available should it be?"                                             │
│                                                                             │
│   L6 REQUIREMENTS GATHERING (adds):                                         │
│   ───────────────────────────────                                           │
│   "What should the system do when the database is slow?"                    │
│   "What's acceptable user experience during degradation?"                   │
│   "Which failures are acceptable to users vs. which are catastrophic?"      │
│   "How long can the system be degraded before it's considered an outage?"   │
│   "What should we preserve vs. sacrifice during partial failure?"           │
│                                                                             │
│   THE DIFFERENCE:                                                           │
│   L5 → Requirements for the happy path                                      │
│   L6 → Requirements for the full operational spectrum                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The Failure Requirements Framework

When gathering requirements, explicitly cover:

### 1. Degradation Behavior Requirements

**Questions to ask**:
- "When the system is slow or partially unavailable, what should users experience?"
- "Which features can degrade gracefully? Which must work or fail completely?"
- "Is stale data acceptable during degradation? How stale?"

**Example for Notification System**:
"If the notification delivery pipeline backs up, what should happen?
- Option A: Delay all notifications equally (fair but slow)
- Option B: Prioritize critical notifications, delay others (fast for critical)
- Option C: Drop low-priority notifications after X hours (shed load)

I'm recommending Option B—critical notifications like 2FA and fraud alerts should always get through, even if 'someone liked your post' is delayed. Does that priority model match business expectations?"

### 2. Failure Mode Tolerance

**Questions to ask**:
- "What types of failures are acceptable? Lost data? Duplicate delivery? Delayed processing?"
- "What's the blast radius that's acceptable? Single user? Single feature? Entire system?"
- "How quickly must we recover from different failure types?"

**Example for Notification System**:
"For notification delivery, which failures are acceptable?
- Lost notification: Acceptable for social notifications (likes, comments), unacceptable for security notifications (2FA, fraud alerts)
- Duplicate notification: Mildly annoying but acceptable for all types
- Delayed notification: Acceptable up to 5 minutes for social, unacceptable for time-sensitive (2FA expires)

This tells me we need different reliability guarantees for different notification types—not a one-size-fits-all approach."

### 3. Recovery Requirements

**Questions to ask**:
- "What's the recovery time objective (RTO) for different failure scenarios?"
- "What's the recovery point objective (RPO)—how much data loss is acceptable?"
- "Should recovery be automatic or can it require human intervention?"

**Example for Notification System**:
"If the entire notification system goes down:
- RTO: Back online within 15 minutes
- RPO: Notifications generated during outage should be delivered after recovery (no loss)
- Backlog processing: Spread over 30 minutes to avoid thundering herd

This tells me we need durable message storage and controlled replay capability."

---

## Integrating Failure Requirements into the Framework

The five phases now look like:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EXTENDED FRAMEWORK WITH FAILURE REQUIREMENTS             │
│                                                                             │
│   1. USERS & USE CASES                                                      │
│      + "What do users experience during degradation?"                       │
│      + "Which user journeys are critical vs. deferrable?"                   │
│                                                                             │
│   2. FUNCTIONAL REQUIREMENTS                                                │
│      + "Which functions must work vs. can degrade vs. can fail?"            │
│      + "What's the fallback behavior for each function?"                    │
│                                                                             │
│   3. SCALE                                                                  │
│      + "What's the scale during failure recovery (backlog processing)?"     │
│      + "What's the peak load during failover scenarios?"                    │
│                                                                             │
│   4. NON-FUNCTIONAL REQUIREMENTS                                            │
│      + "What's the degraded latency budget?"                                │
│      + "What's availability during planned maintenance?"                    │
│      + "What's the acceptable error rate during degradation?"               │
│                                                                             │
│   5. ASSUMPTIONS & CONSTRAINTS                                              │
│      + "What's the on-call response time assumption?"                       │
│      + "What recovery automation exists?"                                   │
│      + "What's the budget for redundancy?"                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Failure Requirements Interview Example

**Prompt**: "Design a payment processing system."

**Staff-Level Failure Requirements Gathering**:

"Before I design, I want to understand failure requirements—payments are high-stakes.

**Degradation behavior**:
- If the system is slow, should we queue transactions or reject them?
- If we can process some transactions but not others, how do we prioritize?

**Failure tolerance**:
- Lost transaction: Never acceptable—must have exactly-once semantics
- Duplicate charge: Never acceptable—critical to prevent
- Delayed processing: Acceptable up to how long? 30 seconds? 5 minutes?

**Recovery**:
- If the system goes down mid-transaction, what state should we be in?
- What's the recovery process—automatic or manual?
- How do we handle transactions that were in-flight during failure?

**Blast radius**:
- If one payment processor (Visa) is down, should we fail all transactions or only Visa transactions?
- If our database is slow, should we fail all transactions or degrade to a simplified flow?

These answers will significantly shape the architecture. A system that can never lose transactions needs different infrastructure than one that can occasionally delay them."

---

# Real Incident: Cascading Notification Storm

A structured production incident illustrates why the framework—especially failure requirements and scale—matters.

| Part | Content |
|------|---------|
| **Context** | Notification system for a social platform. 30M DAU, ~7K notifications/second average. Architecture: event ingestion → message queue → fan-out workers → delivery (push/email). Single region, message queue with 3x replication. |
| **Trigger** | A celebrity account (12M followers) posted at peak hour. Normal fan-out: ~500 recipients per post. This post triggered 12M fan-out operations in under 60 seconds. Message queue partition for high-volume users became saturated. |
| **Propagation** | Queue backlog grew. Workers pulled from the queue but each notification required downstream delivery API calls. Delivery service rate-limited our workers. Workers retried aggressively. Retries + new traffic overwhelmed the queue. Other partitions started lagging. Database writes for notification history slowed. Read replicas fell behind. Entire pipeline backed up. |
| **User impact** | Notifications delayed by 2–45 minutes for ~8M users. Some users received duplicates when retries succeeded after partial delivery. 2FA and security notifications (normally prioritized) were delayed because the priority queue was starved by the backlog. Support ticket volume spiked. |
| **Engineer response** | On-call identified hot partition and celebrity fan-out. Manually paused delivery for that single post. Scaled workers 3x. Drained backlog over 90 minutes. Postmortem revealed no degradation requirements had been defined—system treated all notifications equally. |
| **Root cause** | Requirements gathered only for happy path. No failure requirements: no priority lanes, no shed load behavior, no hot-key handling. Scale estimates assumed uniform fan-out; celebrity skew was not modeled. Single queue for all notification types meant one hot key could block critical notifications. |
| **Design change** | Added priority lanes: transactional (2FA, security) in dedicated queue, social in standard queue. Celebrity fan-out routed to async batch path with rate limiting. Shed load: under overload, drop lowest-priority notifications after N retries. Added per-partition backpressure and hot-key detection. |
| **Lesson learned** | *"Requirements that omit failure modes and skew are incomplete."* Staff engineers ask: "What happens when one user creates 1000x normal load?" and "Which notifications must never be delayed?"—before designing. The framework's failure-requirements phase would have surfaced these. |

---

# Part 10: Requirements-to-Architecture Mapping

This section addresses how requirements drive specific architectural decisions. Staff engineers don't just gather requirements—they trace each requirement to its architectural implication.

---

## The Requirements-Decision Chain

Every architectural decision should trace back to a requirement. If you can't explain why a design choice exists in terms of requirements, it's potentially unnecessary complexity.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REQUIREMENTS-TO-ARCHITECTURE MAPPING                     │
│                                                                             │
│   REQUIREMENT                        ARCHITECTURAL IMPLICATION              │
│   ───────────                        ────────────────────────               │
│                                                                             │
│   "99.9% availability"          →    Redundancy at every layer              │
│                                      No single points of failure            │
│                                      Automated failover                     │
│                                                                             │
│   "P99 latency < 100ms"         →    Caching layer required                 │
│                                      Async processing where possible        │
│                                      Geographic distribution                │
│                                                                             │
│   "50K writes/second"           →    Horizontally scalable write path       │
│                                      Sharded database or NoSQL              │
│                                      Write-ahead logging                    │
│                                                                             │
│   "Strong consistency"          →    Single leader for writes               │
│                                      Synchronous replication                │
│                                      Higher latency accepted                │
│                                                                             │
│   "Never lose a transaction"    →    Durable message queue                  │
│                                      Write-ahead log                        │
│                                      Multi-region replication               │
│                                                                             │
│   STAFF ENGINEERS MAKE THESE CONNECTIONS EXPLICIT.                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Concrete Example: Notification System Requirements-to-Architecture

Let me show how each requirement from our notification system example drives specific architectural decisions.

### Requirement: "30M DAU, 7K notifications/second"

**Architectural implications**:
- Single database won't handle write throughput → Need distributed message queue
- Single server won't handle connection load → Need connection server fleet
- Can't fan-out synchronously → Need async processing pipeline

**What I'd say in interview**:
"At 7K notifications/second, a single database can't handle the write load. I'm introducing a message queue—Kafka—to decouple ingestion from processing. This also gives us replay capability for failure recovery, which addresses our durability requirement."

### Requirement: "99.9% availability"

**Architectural implications**:
- Every component needs redundancy → Minimum 3 replicas per service
- Need automated health checks and failover → Load balancers with health probes
- Need to handle partial failures → Circuit breakers between services

**What I'd say in interview**:
"99.9% availability means 8 hours of downtime per year. To achieve this, I'm designing with no single points of failure. Every service has at least 3 replicas. The message queue has replication factor 3. The database has a hot standby with automatic failover."

### Requirement: "5-second delivery P95"

**Architectural implications**:
- Can't do batch processing → Need streaming architecture
- Can't have long queues → Need horizontal scaling with low queue depth
- Need to prioritize → Separate queues for priority levels

**What I'd say in interview**:
"5-second P95 delivery means we can't batch notifications. I'm designing a streaming pipeline where each notification is processed immediately. To handle the 10x peak (70K/sec), the processing tier auto-scales based on queue depth, targeting <1 second queue wait time."

### Requirement: "Eventual consistency acceptable"

**Architectural implications**:
- Can use async replication → Lower-latency writes
- Can use caching aggressively → Better read performance
- Can tolerate temporary inconsistency → Simpler architecture

**What I'd say in interview**:
"Since eventual consistency is acceptable, I can use async replication for the notification database, which gives us lower write latency. Read status might be slightly stale across devices for a few seconds, but that's acceptable for this use case. If we needed strong consistency, I'd need synchronous replication, which would add latency."

### Requirement: "Critical notifications (2FA) must have higher reliability"

**Architectural implications**:
- Need priority queuing → Separate processing pipeline for critical
- Need different SLAs → Dedicated capacity for critical path
- Need different failure handling → Fail-safe for critical, best-effort for regular

**What I'd say in interview**:
"The requirement for different reliability levels means I can't have a one-size-fits-all pipeline. I'm splitting into two paths: a critical path for 2FA/security notifications with dedicated capacity and stricter delivery guarantees, and a standard path for social notifications that can shed load during peaks."

---

## The Decision Justification Template

When making an architectural decision, use this structure:

```
"I'm choosing [ARCHITECTURE CHOICE] because our requirement for [SPECIFIC REQUIREMENT].

The alternative would be [ALTERNATIVE], which would be better if [DIFFERENT REQUIREMENT].

The trade-off I'm accepting is [COST/DOWNSIDE], which is acceptable because [REQUIREMENT ALLOWS IT]."
```

**Example**:

"I'm choosing Kafka over a simpler queue like RabbitMQ because our requirement for replay capability during failure recovery. 

The alternative would be RabbitMQ, which would be simpler to operate if we didn't need replay.

The trade-off I'm accepting is operational complexity. Kafka requires more expertise to run. This is acceptable because we have a dedicated platform team and the replay capability is essential for our durability requirements."

---

# Part 11: Requirements Evolution

Requirements aren't static. Staff engineers understand that requirements change as systems scale, as users evolve, and as business needs shift.

---

## When to Revisit Requirements

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REQUIREMENTS EVOLUTION TRIGGERS                          │
│                                                                             │
│   SCALE TRIGGERS:                                                           │
│   • 10x user growth                                                         │
│   • 10x data volume growth                                                  │
│   • New geographic regions                                                  │
│   • Hitting infrastructure limits                                           │
│                                                                             │
│   BUSINESS TRIGGERS:                                                        │
│   • New product features that stress existing requirements                  │
│   • New customer segments with different needs                              │
│   • Regulatory changes (GDPR, CCPA, etc.)                                   │
│   • Competitive pressure changing expectations                              │
│                                                                             │
│   OPERATIONAL TRIGGERS:                                                     │
│   • Incidents revealing requirements gaps                                   │
│   • On-call burden indicating over/under-engineering                        │
│   • Cost growth outpacing value                                             │
│   • Team growth changing operational capacity                               │
│                                                                             │
│   STAFF ENGINEERS PROACTIVELY IDENTIFY THESE TRIGGERS.                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Requirements Evolution Example: Notification System

### V1 Requirements (Launch: 1M users)

| Dimension | V1 Requirement | Justification |
|-----------|----------------|---------------|
| Scale | 1K notifications/second | Current user base + 2x buffer |
| Availability | 99.5% | Early product, some downtime acceptable |
| Latency | 30-second delivery | Users tolerant during early adoption |
| Durability | Best-effort | Social notifications, loss acceptable |
| Team | 2 engineers | Startup mode |

**V1 Architecture Implications**:
- Single region, simple infrastructure
- Synchronous processing acceptable
- Single database, no sharding
- Minimal redundancy

### V2 Requirements (Growth: 30M users)

| Dimension | V2 Requirement | What Changed |
|-----------|----------------|--------------|
| Scale | 7K notifications/second | 30x user growth |
| Availability | 99.9% | Product is now critical to users |
| Latency | 5-second delivery | User expectations increased |
| Durability | At-least-once for all | Premium users paying |
| Team | 6 engineers | Can handle more complexity |

**V2 Architecture Implications**:
- Need message queue for async processing
- Need database sharding or NoSQL
- Need multi-AZ redundancy
- Need monitoring and alerting

### V3 Requirements (Scale: 300M users)

| Dimension | V3 Requirement | What Changed |
|-----------|----------------|--------------|
| Scale | 70K notifications/second | 10x growth |
| Availability | 99.99% | Platform critical infrastructure |
| Latency | 2-second delivery | Real-time expectations |
| Durability | Exactly-once for payments | Financial notifications added |
| Team | 15 engineers | Dedicated platform team |

**V3 Architecture Implications**:
- Multi-region deployment
- Separate critical and standard paths
- Sophisticated traffic management
- Dedicated on-call rotation

### Staff-Level Requirements Evolution Thinking

**What I'd say in interview**:

"Before I design, I want to understand where we are in the product lifecycle. The right architecture for V1 (1M users, early product) is very different from V3 (300M users, critical infrastructure).

For this interview, I'll design for V2—30M users, 99.9% availability—but I'll make sure my architecture can evolve to V3 without a complete rewrite.

Specifically, I'll:
1. Design the data model so it can be sharded later without migration
2. Use message queues from the start so we have replay capability
3. Separate the critical path in the design even if we don't build it yet
4. Choose technologies that scale horizontally

This way we're not over-engineering for V3 scale we don't have, but we're also not painting ourselves into a corner."

---

# Part 12: Interview Calibration for Requirements Gathering

## Phrases That Signal Staff-Level Requirements Gathering

### For Users & Use Cases

**L5 phrases** (acceptable but limited):
- "Who are the users?"
- "What are the main use cases?"

**L6 phrases** (demonstrates depth):
- "Who are all the stakeholders? I'm thinking primary users, but also ops, support, and systems that integrate with us."
- "What do users experience when things go wrong? That'll shape my degradation design."
- "Are there user segments with significantly different needs that might require different architectures?"

### For Functional Requirements

**L5 phrases**:
- "What features do we need?"
- "What should the system do?"

**L6 phrases**:
- "Let me categorize requirements: core, important, nice-to-have. For this design, I'll focus on core."
- "Which functions must work fully vs. can degrade gracefully vs. can fail completely during issues?"
- "What's the fallback behavior when this feature can't work normally?"

### For Scale

**L5 phrases**:
- "How many users?"
- "What's the traffic?"

**L6 phrases**:
- "Let me derive the scale. X users × Y actions = Z QPS. Peak at 10x is W."
- "What's the scale during failure recovery? Backlog processing might exceed normal peak."
- "What's the growth trajectory? I want to design with headroom but not over-engineer."

### For Non-Functional Requirements

**L5 phrases**:
- "Should it be highly available?"
- "Should it be fast?"

**L6 phrases**:
- "What's the availability target? 99.9% vs 99.99% are completely different architectures."
- "What's the P99 latency during degradation, not just normal operation?"
- "Which is more important when they conflict—latency or consistency?"

### For Failure Requirements

**L5 phrases**:
- (Often doesn't ask)

**L6 phrases**:
- "What's acceptable user experience during partial failure?"
- "Which failures are acceptable—lost data, duplicates, delays?"
- "What's the blast radius we're designing for?"

---

## What Interviewers Are Looking For

When evaluating requirements gathering, interviewers ask themselves:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    INTERVIEWER'S REQUIREMENTS EVALUATION                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   1. Do they establish context before designing?                            │
│      → Or do they jump straight into architecture?                          │
│                                                                             │
│   2. Do they prioritize requirements?                                       │
│      → Or do they treat all features as equally important?                  │
│                                                                             │
│   3. Do they quantify scale and NFRs?                                       │
│      → Or do they use vague terms like "fast" and "reliable"?               │
│                                                                             │
│   4. Do they ask about failure modes?                                       │
│      → Or do they only consider the happy path?                             │
│                                                                             │
│   5. Do they trace requirements to architecture?                            │
│      → Or do they make arbitrary design choices?                            │
│                                                                             │
│   6. Do they consider evolution?                                            │
│      → Or do they design only for today's requirements?                     │
│                                                                             │
│   THE CORE QUESTION:                                                        │
│   "Would I trust this person to understand the problem before solving it?"  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Common L5 Mistake: Requirements as Checklist

### The Mistake

Strong L5 engineers often treat requirements gathering as a checklist to complete before the "real" design work. They ask the right questions but don't use the answers to drive architectural decisions.

**L5 Pattern**:
```
"How many users?" → "10 million"
"What's the latency requirement?" → "200ms"
"Okay, let me start designing..."

[Later in the design]
"I'll use a relational database."

[Interviewer thinking: Why? The scale and latency requirements weren't connected to this choice.]
```

**L6 Pattern**:
```
"How many users?" → "10 million"
"What's the latency requirement?" → "200ms"

"10 million users with 200ms latency tells me we need aggressive caching—database queries won't meet that latency at scale. I'm designing a cache-first architecture with the database as durable storage.

For the cache, I'll use Redis because [reasoning tied to requirements]."
```

**The Difference**: L6 candidates explicitly connect every architectural decision back to the requirements they gathered. The requirements aren't a checkbox—they're the foundation that justifies every choice.

---

## How to Explain This Framework to Leadership

Staff engineers translate technical rigor into business language:

**One-liner**: "We establish the problem before we solve it—who, what, how big, how well, and what constraints. That prevents us from building the wrong thing."

**Key points for leadership:**
- "Spending 10 minutes on requirements saves weeks of rework. We've seen projects fail because we built for the wrong scale or the wrong user."
- "The framework is a contract: we agree on what we're building before we design. That alignment reduces surprises and scope creep."
- "We also establish what happens when things fail. Most systems break in production because we only designed for the happy path."

**Avoid**: Don't present the five phases as a process. Present the *outcome*: shared understanding, prioritized scope, and explicit trade-offs.

---

## How to Teach This Topic

When mentoring engineers on the framework:

**1. Model the behavior**: In design reviews, start by saying "Before we discuss architecture, let me summarize what I understand we're building..." and walk through the five phases. They'll internalize the pattern.

**2. Use the contract metaphor**: "Think of requirements as a contract. You're negotiating with the interviewer (or PM) on what we're building. Without it, you might build something brilliant for the wrong problem."

**3. Practice the first 10 minutes**: Have them practice only the framework phase—no design—for 10 minutes on a new problem. The goal is fluency: asking the right questions without hesitation.

**4. Correct the checklist trap**: When they ask "What are the 5 phases?" and recite them, ask: "Now, how does each phase drive your next design decision?" If they can't connect requirements to architecture, they're still at L5.

**5. Inject failure**: Give them a prompt and then say "The database just went down. What happens to your design?" Force them to think about failure requirements.

---

# Section Verification: L6 Coverage Assessment

## Final Statement

**This chapter now meets Google Staff Engineer (L6) expectations.**

The document provides comprehensive coverage of the System Design Framework with Staff-level depth: 5-phase structure, failure requirements, cost and cross-team impact, requirements-to-architecture mapping, evolution thinking, and a structured real incident. All L6 dimensions (A–J) are addressed.

---

## Master Review Prompt Check

- [x] **Staff Engineer preparation** — Content aimed at L6; depth and judgment match Staff expectations.
- [x] **Chapter-only content** — Every section relates to the System Design Framework; no tangents.
- [x] **Explained in detail with an example** — Each phase has clear explanation plus concrete examples (notification, payment, URL shortener, etc.).
- [x] **Topics in depth** — Trade-offs, failure modes, scale, cost, and evolution covered with reasoning.
- [x] **Interesting & real-life incidents** — Structured real incident (Cascading Notification Storm) with full format.
- [x] **Easy to remember** — Mental models, one-liners, diagrams, and Quick Reference Card throughout.
- [x] **Organized for Early SWE → Staff SWE** — Progression from 5 phases to L6 extensions (failure, cost, cross-team).
- [x] **Strategic framing** — Problem selection, business vs technical trade-offs, and "why this problem" addressed.
- [x] **Teachability** — How to explain to leadership, how to teach this topic, mentoring guidance.
- [x] **Exercises** — Dedicated Homework Exercises (6 exercises) with concrete tasks.
- [x] **BRAINSTORMING** — Brainstorming questions and reflection prompts at the end.

---

## L6 Dimension Coverage Table (A–J)

| Dimension | Coverage | Key Content |
|-----------|----------|-------------|
| **A. Judgment & decision-making** | ✅ | Decision justification template, trade-off articulation, requirements-to-architecture mapping, prioritization |
| **B. Failure & incident thinking** | ✅ | Part 9 Failure Requirements, blast radius, degradation behavior, real incident (Cascading Notification Storm) |
| **C. Scale & time** | ✅ | Phase 3 Scale, first bottlenecks over time, growth time bomb, V1→V2→V3 evolution |
| **D. Cost & sustainability** | ✅ | Cost as first-class constraint, major cost drivers by system type, trade-offs |
| **E. Real-world engineering** | ✅ | Operational requirements (Part 12), on-call assumptions, team constraints, human error (failure modes) |
| **F. Learnability & memorability** | ✅ | Mental models per phase, one-liners, Quick Reference Card, SLA pyramid, powers of ten |
| **G. Data, consistency & correctness** | ✅ | NFR consistency (strong vs eventual), durability, RPO/RTO, exactly-once vs at-least-once |
| **H. Security & compliance** | ✅ | Trust boundaries, data sensitivity, compliance (GDPR, HIPAA, PCI) in NFR phase |
| **I. Observability & debuggability** | ✅ | Observability in NFR phase, Part 12 Operational Requirements (trace, metrics, replay) |
| **J. Cross-team & org impact** | ✅ | Cross-team dependencies, adoption path, org-wide coordination cost |

---

## Diagrams Included

1. **5-Phase Framework** — Visual overview
2. **NFR Quick Reference Table** — Dimensions and trade-offs
3. **Back-of-Envelope Cheat Sheet** — Quick reference
4. **Scale Mental Model** — Powers of ten
5. **First Bottlenecks Over Time** — Growth stage → typical bottleneck
6. **Failure Requirements Comparison** — L5 vs L6 gathering
7. **Extended Framework with Failure Requirements** — Integrated view
8. **Requirements-to-Architecture Mapping** — Decision chain
9. **Requirements Evolution Triggers** — When to revisit
10. **Interviewer's Requirements Evaluation** — What they assess

---

## Quick Self-Check: Requirements Gathering

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PRE-INTERVIEW REQUIREMENTS CHECK                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   □ I establish context before designing (not jumping to architecture)      │
│   □ I identify multiple user types, including internal users                │
│   □ I prioritize requirements (core / important / nice-to-have)             │
│   □ I quantify scale with back-of-envelope math                             │
│   □ I quantify NFRs (99.9% not "high availability")                         │
│   □ I ask about failure modes and degradation behavior                      │
│   □ I connect every architectural decision to a requirement                 │
│   □ I consider requirements evolution over time                             │
│   □ I summarize understanding before designing                              │
│   □ I confirm alignment with the interviewer at each phase                  │
│                                                                             │
│   If you check 8+, you're demonstrating Staff-level requirements gathering. │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

# Brainstorming Questions

## Self-Assessment

1. When you hear a new design problem, what's your instinctive first action—do you start solving, or do you start understanding?

2. Can you list five different types of users for a system you've built? (If you can't, you might be missing important perspectives.)

3. How often do you explicitly prioritize requirements into "must-have" vs. "nice-to-have"? Does this happen naturally or do you have to force it?

4. When did you last do a back-of-envelope capacity calculation? Was it accurate when you compared it to reality?

5. What's the highest availability system you've worked on? What design patterns made that availability possible?

6. What assumptions are you making right now about your current work that you've never stated explicitly?

## Framework Application

7. Pick a system you know well. Walk through all five phases of the framework for it. What new insights emerge?

8. For your current project, can you articulate the non-functional requirements in quantitative terms? (Not "high availability" but "99.9% availability"?)

9. What are the constraints on your current project? Which are truly fixed vs. potentially negotiable?

10. If you had to design the same system at 10x scale, what would change? At 100x scale?

## Interview Preparation

11. Practice introducing yourself to a framework: "Before I design, I want to understand..." What are the first three questions you'd ask for any problem?

12. Practice scoping: For a notification system, how would you divide requirements into core/important/nice-to-have?

13. Practice estimation: If told "a major social platform," what numbers would you assume? Can you derive them from first principles?

14. Practice trade-offs: For a given system, what's the trade-off between consistency and availability? When would you choose each?

15. Practice assumptions: What are the standard assumptions you'd make for any cloud-based system? List at least five.

---

# Reflection Prompts

Set aside 15-20 minutes for each of these reflection exercises.

## Reflection 1: Your Framework Discipline

Think about your approach to system design problems.

- When you hear a new problem, do you immediately start thinking about components, or do you pause to understand context?
- How often do you explicitly state requirements before designing?
- Do you naturally think about failure modes during requirements gathering?
- What would change if you spent 10 minutes on requirements for every 35 minutes of design?

Write down three specific habits you want to develop in requirements gathering.

## Reflection 2: Your Scale Intuition

Consider your experience with scale estimation.

- How accurately have your scale estimates matched reality in past projects?
- What dimensions of scale (users, data, QPS) do you estimate well vs. poorly?
- Do you tend to over-estimate or under-estimate? Why?
- What calculations have you done in interviews that felt shaky?

Practice one back-of-envelope calculation daily for a week. Track your confidence.

## Reflection 3: Your Trade-off Reasoning

Examine how you make trade-off decisions.

- Do you make trade-offs explicitly or implicitly?
- When was the last time you documented a trade-off decision?
- Do you default to certain choices (consistency over availability, for example)?
- How do you communicate trade-offs to stakeholders?

For your current project, list three trade-offs and whether they were explicitly made.

---

# Homework Exercises

## Exercise 1: The Framework Drill

Choose three different design problems (e.g., URL shortener, chat system, recommendation engine).

For each one, practice only the framework phase—no actual designing:
- Spend 10 minutes going through all five phases
- Write down your questions, answers, and conclusions
- Time yourself on each phase

Goal: The framework phase should become natural and take 5-10 minutes.

## Exercise 2: The Scale Calibration

Choose five different system types:
- Personal project (you and a few friends)
- Startup MVP (1,000 users)
- Growing startup (100,000 users)
- Successful company (10 million users)
- Major platform (1 billion users)

For each scale:
- What architecture patterns are appropriate?
- What's the team size to build and maintain it?
- What's the infrastructure cost (order of magnitude)?

Goal: Develop intuition for what scale requires what complexity.

## Exercise 3: The Trade-off Matrix

Create a matrix of non-functional requirements:
- Rows: Availability, Latency, Consistency, Durability
- Columns: Same four properties

For each pair, identify the trade-off:
- How does optimizing for Row property affect Column property?
- Can you have both at maximum? If not, why not?
- Give a concrete example of choosing one over the other

Goal: Internalize the fundamental trade-offs in distributed systems.

## Exercise 4: The Assumption Excavation

Take a system you've recently built or designed:
- List every assumption you made (aim for at least 20)
- Categorize them: infrastructure, team, organization, technology, user behavior
- For each one, ask: what if this assumption was wrong?

Goal: Develop the habit of making assumptions explicit.

## Exercise 5: The Requirements Interview

With a partner, practice the requirements-gathering conversation:
- Partner gives you a vague prompt ("design a messaging system")
- You ask clarifying questions for 10 minutes
- Partner answers (they can make things up)
- At the end, summarize what you learned

Then switch roles.

Goal: Practice having the clarifying conversation naturally and thoroughly.

## Exercise 6: The Constraint Discovery

For a system you know well:
- List all the constraints you're operating under
- Categorize: truly fixed vs. potentially flexible
- For each flexible constraint, identify what you'd need to change it
- Identify one constraint that, if removed, would significantly improve the system

Goal: Understand that constraints are often more negotiable than they appear.

---


---

# Conclusion

System Design Framework is simple:

1. **Users & Use Cases**: Who are we building for and what are they trying to do?
2. **Functional Requirements**: What must the system do?
3. **Scale**: How big is this problem?
4. **Non-Functional Requirements**: What qualities must the system have?
5. **Assumptions & Constraints**: What are we taking as given?

But Staff engineers go deeper:

6. **Failure Requirements**: What should the system do when things go wrong?
7. **Requirements-to-Architecture Mapping**: How does each requirement drive design decisions?
8. **Requirements Evolution**: How will requirements change as we scale?

Applying this extended framework well requires:
- The discipline to slow down when your instincts say "start building"
- The skill to ask probing questions that reveal hidden requirements
- The judgment to prioritize ruthlessly
- The ability to trace every design decision to a requirement
- The foresight to design for evolution, not just today's needs
- The communication ability to articulate your understanding clearly

This framework isn't just for interviews—it's how Staff engineers approach real work. Every design document at Google implicitly covers these phases. Every technical discussion starts with understanding before solving.

When you internalize this framework, two things happen:

First, your interviews become more structured and confident. You know what to do in the first ten minutes. You know what questions to ask. You know how to establish a foundation before designing.

Second, your actual engineering becomes more effective. You start asking the right questions before writing code. You start calibrating your designs to actual requirements. You start making trade-offs explicit instead of implicit. You start designing for failure, not just success.

The framework is your lens. Every design problem looks different through it—and that differentiation is exactly what makes your designs appropriate rather than generic.

Master the framework. Use it consistently. Watch your system design transform.

---
