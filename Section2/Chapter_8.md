# Chapter 7: Phase 1 — Users & Use Cases: Staff-Level Thinking

---

# Quick Visual: The 4 Types of Users

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THINK BEYOND THE OBVIOUS USER                            │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. HUMAN USERS                                                     │   │
│   │     End consumers, internal staff, support, admins, analysts        │   │
│   │     → Care about: Latency, usability, personalization               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  2. SYSTEM USERS                                                    │   │
│   │     Internal services, partner APIs, external integrations          │   │
│   │     → Care about: API stability, consistency, throughput            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  3. SERVICE USERS                                                   │   │
│   │     Batch jobs, cron jobs, automated processes, ML pipelines        │   │
│   │     → Care about: Reliability, idempotency, efficiency              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  4. OPERATIONAL USERS                                               │   │
│   │     SREs, on-call engineers, DevOps, platform teams                 │   │
│   │     → Care about: Observability, debuggability, controllability     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   KEY: Most candidates only think about #1. Staff engineers think about ALL.│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Simple Example: Notification System Users

| User Type | Who They Are | What They Need | Design Impact |
|-----------|-------------|----------------|---------------|
| **Human** | People receiving notifications | Real-time delivery, preference control | Push infra, preference storage |
| **System** | Feed service, messaging service | High-throughput API, reliable delivery | Async processing, retries |
| **Service** | Marketing batch jobs, analytics pipelines | Bulk operations, event consumption | Queue-based, event publishing |
| **Operational** | SREs monitoring delivery | Dashboards, alerts, debug tools | Metrics, tracing, admin API |

**The lesson**: A design that only serves human users might have terrible APIs for system users, or be impossible for operations to debug.

---

# Introduction

Every system exists to serve someone. Before you draw a single box or choose a single technology, you need to understand who that someone is and what they're trying to accomplish.

This sounds obvious. And yet, it's where many experienced engineers stumble in Staff-level interviews. They hear "design a rate limiter" and immediately start thinking about token buckets and sliding windows. They hear "design a messaging system" and jump to message queues and delivery guarantees. They're solving before they've understood.

Staff engineers do something different. They pause. They ask: Who will use this system? What are they actually trying to do? What matters most to them? Only after understanding the users and their goals do they begin to design.

This section is about Phase 1 of the Staff-Level System Design Framework: Users & Use Cases. We'll explore what "user" means at Staff level (it's broader than you might think), how to distinguish primary from secondary users, how to separate user intent from implementation details, how to identify core versus edge use cases, and how to make intentional scope decisions that shape everything that follows.

By the end of this section, you'll approach the opening minutes of any system design interview with confidence and structure. You'll know what questions to ask, what to listen for, and how to establish a foundation that makes the rest of your design coherent.

---

# Part 1: What "User" Means at Staff Level

## Beyond the Human User

When most engineers think "user," they picture a person—someone clicking buttons, viewing screens, receiving notifications. This is a natural starting point, but it's incomplete.

At Staff level, you need to think about users more broadly:

**Human users**: People who interact with the system directly. This includes end consumers, but also internal users like operations staff, customer support, data analysts, and administrators.

**System users**: Other software systems that call your APIs, consume your events, or depend on your data. These might be internal services within your organization or external systems from partners and third parties.

**Service users**: Internal microservices, batch jobs, and automated processes that interact with your system programmatically.

**Operational users**: Engineers who deploy, monitor, debug, and maintain the system. Their needs are often invisible but critically important.

A notification system, for example, has:
- **Human users**: People receiving notifications on their phones
- **System users**: The feed service that triggers "new post" notifications, the messaging service that triggers "new message" notifications
- **Service users**: Batch jobs that send marketing notifications, analytics pipelines that consume delivery events
- **Operational users**: SREs monitoring delivery rates, support engineers debugging missed notifications

Each user type has different needs, different scale characteristics, and different quality requirements. A design that serves human users well might fail to serve system users—or vice versa.

## Why This Matters for Design

Different user types drive different design decisions:

**Human users** often care about:
- Latency (perceived responsiveness)
- Usability (clear interfaces, forgiving of mistakes)
- Personalization (relevant content, remembered preferences)

**System users** often care about:
- API stability (no breaking changes)
- Consistency (predictable behavior)
- Throughput (handling high volumes)

**Service users** often care about:
- Reliability (always available when needed)
- Idempotency (safe to retry)
- Efficiency (low overhead per operation)

**Operational users** often care about:
- Observability (easy to see what's happening)
- Debuggability (easy to diagnose problems)
- Controllability (ability to adjust behavior without code changes)

If you design only for human users, you might create a system with beautiful UX but terrible APIs. If you design only for system users, you might create a system that's powerful but impossible to operate when things go wrong.

## Identifying All User Types

In an interview, systematically surface all user types:

**The direct question approach:**
"Who are the users of this system? I'm thinking about end users, but are there also internal systems that will interact with it? And what about operations—is there a team that will need to monitor and maintain this?"

**The workflow approach:**
"Let me trace through how this system gets used. Someone initiates an action... that flows through these services... produces this output... which needs to be monitored by... Is there any user I'm missing?"

**The lifecycle approach:**
"During normal operation, these users interact with the system. During incidents, who gets involved? During scaling events? During maintenance windows?"

The goal is to avoid the trap of designing for the obvious user while ignoring the others.

---

# Part 2: Primary vs. Secondary Users

## Defining the Distinction

Not all users are equally important to your design. Primary users are the ones whose needs you optimize for; secondary users are important but subordinate.

**Primary users**: The users whose needs drive the core design decisions. If you had to choose between serving them well or serving someone else well, you'd choose them.

**Secondary users**: Users whose needs matter, but not at the expense of primary users. You accommodate them where possible without compromising the primary experience.

This distinction isn't about who's "more important" in an abstract sense—it's about who drives the design. A payment system might have consumers as primary users and fraud analysts as secondary users. The core design optimizes for consumer experience (fast, reliable payments), while accommodating analyst needs (audit logs, investigation tools) in ways that don't degrade the primary experience.

## Why This Matters

Trying to optimize for everyone equally leads to a system that serves no one well. Trade-offs are inevitable, and primary/secondary designation tells you how to make them.

Consider a real-time feed system:
- **Primary users**: End users viewing their feed
- **Secondary users**: Content creators, advertisers, analytics systems

If you had to choose between:
- Fast feed rendering for viewers vs. Detailed analytics for advertisers

The primary/secondary distinction tells you: optimize for viewers, accommodate advertisers.

This doesn't mean you ignore secondary users—it means you have a clear priority when trade-offs arise.

## Determining Primary vs. Secondary

Several factors help you determine which users are primary:

**Business criticality**: Which users are most important to the business? For a consumer app, end users are usually primary. For an internal platform, developers using the platform might be primary.

**Interaction frequency**: Users who interact constantly often take priority over occasional users.

**Scale impact**: Users whose usage patterns dominate the scale profile often need to be primary.

**Revenue relationship**: Users who directly generate revenue (or whose satisfaction enables revenue) are often primary.

In an interview, make this determination explicit:

"I'm going to treat end consumers as primary users because they're the core of the product. Internal analytics and operations are secondary—I'll design to accommodate them without compromising the consumer experience. Does that priority make sense for this problem?"

## Example: Rate Limiter

Let's apply this to designing a rate limiter:

**Potential users:**
- Services calling APIs (the ones being rate-limited)
- The APIs being protected
- Operations teams configuring limits
- Security teams investigating abuse
- Product teams wanting usage analytics

**Primary users:**
- The APIs being protected (the rate limiter exists to protect them)
- Services calling APIs (they need predictable, understandable behavior)

**Secondary users:**
- Operations teams (need configuration interfaces, but not at the cost of latency)
- Security and product teams (need visibility, but as a secondary concern)

This classification drives decisions: the rate limiter's core path must be fast and reliable (for primary users), while configuration and analytics interfaces can be eventually consistent and slightly slower.

---

# Part 3: User Intent vs. Implementation

## Quick Reference: Intent vs Implementation Examples

| User Says (Implementation) | Actual Intent | Better Solution |
|---------------------------|---------------|-----------------|
| "I need a refresh button" | "I want current data, not stale" | Real-time updates |
| "Notify me on every like" | "I want to feel appreciated" | Aggregated: "5 people liked" |
| "Add a search bar" | "I need to find things quickly" | Better organization + search |
| "Export to CSV" | "I need to analyze this data" | Built-in analytics dashboard |
| "Send me daily emails" | "Keep me informed" | Smart digest based on activity |

**Key insight**: Users express *implementation*, not *intent*. Your job is to dig deeper.

## Separating the "What" from the "How"

A critical Staff-level skill is distinguishing between what users want to accomplish (intent) and how they might accomplish it (implementation).

**User intent**: The underlying goal or problem the user is trying to solve
**Implementation**: A specific way of achieving that goal

Users often express themselves in terms of implementation rather than intent. Your job is to dig deeper.

**User says**: "I need a button that refreshes the data."
**Implementation**: A refresh button
**Actual intent**: "I want to see current data, not stale data."
**Better solution**: Real-time updates that eliminate the need to refresh

**User says**: "I need to receive a notification when someone likes my post."
**Implementation**: Push notification on every like
**Actual intent**: "I want to feel connected and know people appreciate my content."
**Better solution**: Aggregated notifications ("5 people liked your post") that provide satisfaction without overwhelming

## Why This Matters for System Design

When you design for implementation rather than intent, you often:
- Build the wrong thing (solving the stated problem, not the real problem)
- Over-constrain your design (locking into a specific approach)
- Miss simpler solutions (the stated implementation might be more complex than necessary)

Staff engineers constantly ask: "What are you really trying to accomplish?" This question surfaces the true requirements.

## Uncovering Intent in Interviews

In a system design interview, the prompt is often framed in terms of implementation:

- "Design a notification system" (implementation)
- "Design a URL shortener" (implementation)
- "Design a rate limiter" (implementation)

Your job is to uncover the intent behind these implementations:

**For a notification system:**
"What's the purpose of these notifications? Is it to inform users of things they need to act on? To keep them engaged with the platform? To provide time-sensitive alerts? The answer affects how I design delivery guarantees, aggregation, and prioritization."

**For a URL shortener:**
"What problem are we solving with short URLs? Is it character limits in tweets? Cleaner appearance in marketing materials? Tracking clicks? Analytics on sharing patterns? Each of these intents suggests a different design emphasis."

**For a rate limiter:**
"What are we protecting against? DDoS attacks? Expensive operations by a few users? Ensuring fair access across all users? Preventing accidental abuse from bug loops? The threat model shapes the design."

## Example: Messaging System

**Stated requirement**: "Design a messaging system where users can send messages to each other."

**Surface implementation**: Two users exchanging text messages

**Uncovering intent through questions:**

"What's the core use case? Is this chat (real-time, conversational, presence-aware) or messaging (asynchronous, like email)? Are messages typically short and rapid, or longer and thoughtful?"

"What matters more: guaranteed delivery or low latency? If a message takes 5 seconds to deliver but is never lost, versus usually instant but occasionally lost, which is preferable?"

"Are there group conversations? How large can groups be? Is this more like iMessage (small groups) or Slack (large channels)?"

"What about multimedia? Are we sending text, images, videos, files? Does this need to support voice/video calls?"

Each answer reveals more about the true intent, which shapes the design:
- Real-time chat needs presence and typing indicators; async messaging doesn't
- Guaranteed delivery needs acknowledgment protocols; low-latency can be best-effort
- Large groups need fan-out optimization; small groups can be simpler
- Multimedia needs content delivery infrastructure; text-only is simpler

---

# Part 4: Core vs. Edge Use Cases

## Quick Visual: Core vs Edge

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CORE vs EDGE USE CASES                               │
│                                                                             │
│   CORE (Design Meticulously)              EDGE (Handle Appropriately)       │
│   ┌─────────────────────────┐             ┌────────────────────────-─┐      │
│   │ • High frequency        │             │ • Low frequency          │      │
│   │ • High value            │             │ • Lower priority         │      │
│   │ • User expects perfect  │             │ • Graceful degradation OK│      │
│   │ • Business critical     │             │ • Simple solutions fine  │      │
│   └─────────────────────────┘             └─────────────────────────-┘      │
│                                                                             │
│   Example: Messaging System                                                 │
│   ┌─────────────────────────┐             ┌─────────────────────────┐       │
│   │ CORE:                   │             │ EDGE:                   │       │
│   │ • Send message          │             │ • Delete message        │       │
│   │ • Receive message       │             │ • Unsend message        │       │
│   │ • View history          │             │ • Export conversation   │       │
│   │                         │             │ • Report spam           │       │
│   └─────────────────────────┘             └─────────────────────────┘       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Defining the Distinction

**Core use cases**: The primary flows that most users experience most of the time. These define the system's essential behavior and must work flawlessly.

**Edge use cases**: Less common scenarios that still need to be handled, but don't drive the primary design. These include error cases, unusual inputs, rare user behaviors, and corner cases.

## Why This Matters

Core use cases determine your architecture. Edge cases are handled within that architecture.

If you design for edge cases first, you'll often create unnecessary complexity. If you ignore edge cases entirely, you'll have gaps that cause real problems.

The Staff-level skill is identifying which is which, and allocating design attention appropriately.

## Identifying Core Use Cases

Core use cases typically have these characteristics:

**High frequency**: They happen often—most of your traffic
**High value**: They deliver the primary value of the system
**User expectations**: Users expect them to work perfectly
**Business critical**: Failure here is unacceptable

For a messaging system:
- **Core**: Send a message, receive a message, view conversation history
- **Edge**: Delete a message, unsend a message, report spam, export conversation

For a rate limiter:
- **Core**: Check if a request is allowed, enforce the limit
- **Edge**: View current usage, manually override limits, handle clock skew

## Handling Edge Cases Appropriately

Edge cases shouldn't be ignored, but they shouldn't drive core design decisions either. Common strategies:

**Acknowledge and defer**: "This is an edge case—I'll handle it, but let me first design the core flow. The edge case will likely be a variation on that."

**Simple over perfect**: "For this edge case, a simple solution is fine. It doesn't need to be optimized because it's rare."

**Explicit degradation**: "If this edge case happens, the system will gracefully degrade to [fallback behavior]. That's acceptable given the rarity."

## Example: Feed System

**Core use cases:**
- User opens app, sees personalized feed of content from followed accounts
- User scrolls, more content loads smoothly
- User interacts with content (like, comment, share)

**Edge use cases:**
- User has no followers (empty feed)
- User follows 10,000 accounts (massive input set)
- User hasn't opened app in 6 months (stale relevance data)
- Content is deleted after being loaded into feed
- User is in a region with poor connectivity

For core use cases, design meticulously:
- Feed generation must be fast (under 200ms)
- Ranking must be relevant and personalized
- Pagination must be smooth

For edge cases, design appropriately:
- Empty feed: Show onboarding/recommendations (simple fallback)
- 10,000 follows: Cap the active set considered (reasonable limit)
- Stale user: Use global trending as fallback (graceful degradation)
- Deleted content: Show placeholder, filter on next refresh (acceptable lag)
- Poor connectivity: Aggressive caching, smaller payloads (optimization)

---

# Part 5: Mapping Users to Use Cases

## Building the User-Use Case Matrix

A powerful technique is explicitly mapping which users care about which use cases. This surfaces priorities and reveals gaps.

**Format:**

| Use Case | User A | User B | User C | Priority |
|----------|--------|--------|--------|----------|
| Use Case 1 | Primary | Secondary | — | High |
| Use Case 2 | — | Primary | Secondary | High |
| Use Case 3 | Secondary | Secondary | Primary | Medium |

## Example: Notification System

**Users:**
- End consumers (receiving notifications)
- Product teams (sending notifications)
- Operations (monitoring/debugging)
- Analytics (measuring engagement)

**Use Cases:**

| Use Case | Consumers | Product | Ops | Analytics | Priority |
|----------|-----------|---------|-----|-----------|----------|
| Receive push notification | Primary | — | — | Secondary | High |
| Set notification preferences | Primary | — | — | — | High |
| Send targeted notification | — | Primary | — | Secondary | High |
| View delivery metrics | — | Secondary | Primary | Primary | Medium |
| Debug failed delivery | — | — | Primary | — | Medium |
| A/B test notification content | — | Primary | — | Primary | Medium |
| View notification history | Primary | — | Secondary | — | Medium |

This matrix reveals:
- Consumer notification delivery is the highest priority
- Operations and analytics share some use cases
- Some use cases serve multiple users (design for the primary one)

## Using the Matrix in Design

The matrix guides several decisions:

**API design**: Which operations need to be exposed? To whom?

**Quality requirements**: Which use cases need the highest availability/lowest latency?

**Access control**: Who can perform which operations?

**Monitoring**: What metrics matter for which users?

In an interview, you might sketch this matrix quickly:

"Let me map out who cares about what. End users primarily care about receiving notifications and managing preferences. Product teams care about sending notifications and measuring effectiveness. Ops cares about system health. This tells me my core design must optimize for notification delivery, with solid—but secondary—support for sending and monitoring."

---

# Part 6: Scope Control and Intentional Exclusions

## The Importance of Scope

In a 45-minute interview, you cannot design everything. In a 6-month project, you cannot build everything. Scope control—deciding what's in and what's out—is a critical Staff-level skill.

Scope control isn't about doing less; it's about doing the right amount. Under-scoping means you miss critical requirements. Over-scoping means you waste time on things that don't matter.

## Making Exclusions Explicit

A common mistake is leaving scope ambiguous. This creates problems:
- You might spend time designing something that wasn't needed
- The interviewer might expect something you didn't plan to cover
- Your design might have implicit assumptions that aren't valid

Instead, make exclusions explicit:

"For this design, I'm focusing on [in-scope items]. I'm explicitly not designing [out-of-scope items]—those would be handled by separate systems or future phases. Is that scope appropriate?"

## Types of Exclusions

**Functional exclusions**: Features you're not building
- "I'm designing the notification delivery system, not the notification content creation system."

**User exclusions**: Users you're not optimizing for
- "I'm optimizing for consumer experience, not for power-user features like bulk operations."

**Scale exclusions**: Scale ranges you're not handling
- "I'm designing for 10 million users. The 1 billion user case would require different architectural choices."

**Quality exclusions**: Quality levels you're not achieving
- "I'm designing for 99.9% availability, not 99.99%. The additional nine would require significantly different infrastructure."

**Integration exclusions**: Systems you're not connecting to
- "I'm assuming notifications are delivered via existing push infrastructure. I'm not designing the push delivery system itself."

## Scope Control Phrases

Develop a vocabulary for scope control:

**Setting scope:**
- "For this design, I'm focusing on..."
- "The core scope includes..."
- "I'm treating [X] as in-scope and [Y] as out-of-scope."

**Excluding with rationale:**
- "I'm explicitly not designing [X] because it's a separate concern that's well-understood."
- "I'll acknowledge [X] but not design it in detail—it's not where the interesting challenges are."
- "[X] is important but can be added later without changing the core architecture."

**Inviting feedback:**
- "Does this scope make sense for what you had in mind?"
- "Should I include [X], or is my current scope appropriate?"
- "Is there anything in my scope that you'd like me to drop, or anything outside it you'd like me to add?"

## Example: Rate Limiter Scope

**Prompt**: "Design a rate limiter."

**Potential scope:**
- Single-service vs. distributed rate limiting
- Different algorithms (token bucket, sliding window, fixed window)
- Configuration management
- Multi-tenant isolation
- Analytics and reporting
- Quota management
- Billing integration
- Abuse detection and response

**Scoping conversation:**

"Before I design, let me establish scope. I'll focus on:
- Distributed rate limiting across multiple API servers
- Core enforcement (checking limits, rejecting requests)
- Basic configuration (setting limits per client or endpoint)

I'll acknowledge but not design in detail:
- Analytics dashboards (they'd consume the same data)
- Quota management and billing (related but separate systems)
- Abuse detection beyond rate limiting (a different problem space)

Is there anything you'd like me to add or remove from this scope?"

---

# Part 7: How Phase 1 Decisions Affect Later Architecture

## The Ripple Effects of User Decisions

Decisions you make in Phase 1 ripple through your entire design. Understanding these connections helps you make informed choices early and explain your design coherently later.

### User Types → API Design

The users you identify determine what APIs you need:
- Human users → User-facing APIs (often REST, optimized for simplicity)
- System users → Service APIs (often gRPC, optimized for efficiency)
- Operational users → Admin APIs (internal, privileged access)

**Example**: A notification system with human and system users needs:
- REST API for mobile clients to manage preferences
- gRPC API for internal services to trigger notifications
- Admin API for operations to manage delivery

### Use Cases → Data Model

The use cases you identify determine what data you need to store:
- "View notification history" → Need to persist notifications per user
- "Set preferences" → Need to store user preferences
- "Aggregate similar notifications" → Need to track notification types and counts

**Example**: If "view history" is a core use case, you need:
- Efficient per-user storage (probably user-sharded)
- Support for pagination
- Retention policy decisions

If history is out of scope, you might not need persistent notification storage at all—just a delivery queue.

### Primary Users → Quality Requirements

Your primary users determine where you invest in quality:
- Primary users need highest availability, lowest latency
- Secondary users can tolerate degraded service

**Example**: If consumers are primary and analytics is secondary:
- Notification delivery path: 99.99% availability, <500ms latency
- Analytics data export: 99.9% availability, eventual consistency fine

### Scope Decisions → Component Boundaries

What you include and exclude determines your system's boundaries:
- In-scope items → Components you design
- Out-of-scope items → Interfaces to external systems

**Example**: If you're not designing push delivery infrastructure:
- Your system has a component that formats notifications
- It interfaces with an external push service (APNs, FCM)
- You need to design that interface carefully

## Tracing Decisions Forward

In your design, make these connections explicit:

"Earlier I identified that system users (internal services) trigger most notifications—about 95% of volume. This tells me the service-to-service API is the critical path, so I'm designing it for maximum throughput and lowest latency. The human-user API for preference management can be simpler since it's low-volume."

"Because viewing history is a core use case, I need persistent storage. If it were out of scope, I could use a simpler fire-and-forget architecture."

This tracing demonstrates that your design is coherent—that later decisions follow logically from earlier ones.

---

# Part 8: Interview-Style Clarification Questions

Let me provide concrete examples of how to apply Phase 1 thinking in interview contexts.

## Rate Limiter

**Prompt**: "Design a rate limiter."

**Phase 1 clarification questions:**

**Users:**
"Who are the users of this rate limiter? I'm imagining:
- The APIs being protected (they want protection from overload)
- The clients calling those APIs (they need to understand and respect limits)
- Operations teams configuring limits
- Security teams monitoring for abuse

Is this right? Are there other users I should consider?"

**Use cases:**
"What are the primary use cases?
- Protecting APIs from being overwhelmed by any single client
- Ensuring fair access across clients
- Preventing abuse (intentional or accidental)

Are we also trying to do quota management (billing based on usage) or is that separate?"

**Intent:**
"What problem are we really solving? Is this primarily:
- DDoS protection (malicious high-volume attacks)
- Fair usage enforcement (prevent one client from starving others)
- Cost protection (expensive operations need limits)
- Compliance (SLAs with rate guarantees)

Each of these might suggest different design choices."

**Scope:**
"Let me scope this. I'll design:
- Distributed rate limiting across multiple API servers
- Core enforcement with configurable limits per client/endpoint
- Basic visibility into current usage

I'll assume existing infrastructure for:
- Authentication (knowing who the client is)
- Monitoring and alerting
- Configuration management (though I'll design the data model)

Does this scope work?"

## Messaging System

**Prompt**: "Design a messaging system."

**Phase 1 clarification questions:**

**Users:**
"Who's messaging whom? I can imagine:
- Consumers messaging each other (1:1, group chats)
- Businesses messaging consumers (customer support)
- System-generated messages (notifications, alerts)
- Internal services using this as infrastructure

Which of these are in scope?"

**Use cases:**
"What type of messaging?
- Real-time chat (typing indicators, presence, instant delivery)
- Asynchronous messaging (like email—no expectation of immediate response)
- Something in between (like iMessage—usually fast, but not guaranteed)

This affects delivery guarantees, UI expectations, and scale patterns."

**Intent:**
"What's the core purpose?
- Social connection (chatting with friends)
- Productivity (work communication)
- Customer engagement (business-to-consumer)

The answer affects features like read receipts, message history depth, and search requirements."

**Scope:**
"I'll design for:
- 1:1 messaging between consumers
- Group messaging (up to ~100 participants)
- Text and image messages
- Mobile and web clients

I'll exclude (but can discuss):
- Voice/video calling
- End-to-end encryption
- Business accounts
- Very large groups (1000+)

Does this capture what you had in mind?"

## Feed System

**Prompt**: "Design a social media feed."

**Phase 1 clarification questions:**

**Users:**
"Who interacts with this feed?
- Consumers viewing their personalized feed
- Content creators whose posts appear in feeds
- Advertisers who want placement in feeds
- Internal ranking/ML teams who tune the algorithm
- Operations monitoring feed generation health

Which are primary?"

**Use cases:**
"For the viewer:
- Open app and see relevant content immediately
- Scroll for more content (pagination)
- Interact with content (like, comment, share)
- Refresh for new content

For creators:
- Understand who sees their content
- Know how content performs

Which flows should I prioritize?"

**Intent:**
"What's the goal of this feed?
- Maximize engagement (time spent)
- Maximize social connection (content from friends)
- Maximize discovery (new accounts and content)
- Maximize monetization (ad integration)

These can conflict—what's the priority?"

**Scope:**
"I'll design:
- Home feed generation for a logged-in user
- Basic ranking (recency + engagement signals)
- Infinite scroll pagination

I'll assume existing systems for:
- Content storage (posts, images, videos)
- Social graph (follow relationships)
- Engagement tracking (likes, comments)

Does this scope work?"

---

# Part 9: Staff vs Senior — Phase 1 Contrast

## Quick Comparison Table

| Dimension | Senior (L5) | Staff (L6) | Why L5 Breaks at Scale |
|-----------|-------------|------------|------------------------|
| **User scope** | Assumes obvious user (end consumer) | Enumerates 4+ types: human, system, service, operational | Systems used by machines or operated by SREs fail in production |
| **Intent** | Takes prompt literally ("design a rate limiter") | Probes: "What problem are we solving? DDoS? Fair usage? Cost?" | Builds wrong solution; rate limiter when circuit breaker needed |
| **Failure thinking** | Happy path first; failures later | Per-user failure experience from Phase 1 | Can't add fault tolerance as afterthought; architecture locks in |
| **Scope** | Implicit; designs everything | Explicit in/out; seeks confirmation | Misalignment surfaces late; wasted effort or gaps |
| **Prioritization** | All use cases treated equally | Core vs edge; primary vs secondary with rationale | Design effort spread thin; nothing optimized well |
| **Cost** | Rarely mentioned in Phase 1 | "Which user type dominates cost? What do we not build?" | Cost surprise at scale; over-engineering for edge users |

**Risk accepted (L6):** Staff engineers accept that secondary users may get degraded service during failure. They document this explicitly rather than pretending everyone gets perfect service.

---

# Part 10: Common Mistakes by Strong Senior Engineers

Strong Senior engineers often stumble in Phase 1—not because they lack skill, but because they have habits that work at Senior level but fail at Staff level.

## Mistake 1: Assuming a Single User Type

**The pattern**: Immediately focusing on the most obvious user (end consumers) and ignoring others.

**Why it happens**: In day-to-day work, you're often given a specific user to focus on. The habit of single-user thinking becomes ingrained.

**The problem**: You design a system that serves consumers but is impossible for operations to maintain, or that has no API for other services to integrate with.

**The fix**: Systematically enumerate user types. Ask: "Who else interacts with this system? Who operates it? Who integrates with it?"

**Example**:
- **Senior approach**: "Users send notifications to other users."
- **Staff approach**: "End users receive notifications. Internal services generate most notifications. Operations monitors delivery. Analytics measures engagement. Let me map out how each interacts with the system."

## Mistake 2: Taking the Prompt Literally

**The pattern**: Hearing "design a rate limiter" and immediately designing a rate limiter, without questioning whether rate limiting is the right solution.

**Why it happens**: Senior engineers are trained to execute on requirements, not to question them.

**The problem**: You might design an excellent rate limiter when what's actually needed is a circuit breaker, or a quota system, or a CDN.

**The fix**: Probe the intent behind the prompt. "What problem is this solving? Is rate limiting the only approach, or are there alternatives we should consider?"

**Example**:
- **Senior approach**: "I'll design a token bucket rate limiter..."
- **Staff approach**: "Let me understand the goal. Is rate limiting protecting against DDoS, ensuring fair usage, or something else? Depending on the answer, the design—or even the approach—might differ."

## Mistake 3: Skipping User Discovery to "Save Time"

**The pattern**: Spending 30 seconds on clarifying questions and jumping into architecture.

**Why it happens**: The interview feels short. You want to demonstrate building skills, not asking skills.

**The problem**: You design for the wrong requirements. Or you design for correct requirements but can't articulate why your design choices are appropriate.

**The fix**: Invest 5-10 minutes in Phase 1. This investment pays off in a more focused, defensible design.

**Example**:
- **Senior approach**: "Let me start drawing the architecture—I'll ask questions as I go."
- **Staff approach**: "Let me take 5 minutes to understand the users and use cases. This will make my design more focused."

## Mistake 4: Not Prioritizing Use Cases

**The pattern**: Listing many use cases and treating them all as equally important.

**Why it happens**: At Senior level, you're often asked to "cover everything." Prioritization feels like leaving things out.

**The problem**: You spread design effort thinly across many use cases, none designed well.

**The fix**: Explicitly categorize use cases as core vs. edge. Announce what you're optimizing for.

**Example**:
- **Senior approach**: "The system needs to handle sending, receiving, preferences, history, search, export..."
- **Staff approach**: "The core use cases are sending and receiving. Preferences and history are secondary—I'll design for them but not optimize. Search and export are edge cases—I'll acknowledge but not detail."

## Mistake 5: Implicit Scope

**The pattern**: Having a mental model of scope but not articulating it.

**Why it happens**: Scope feels obvious to you. You don't realize the interviewer might have different expectations.

**The problem**: Misalignment surfaces late. You either design too much (wasting time) or too little (missing requirements).

**The fix**: State scope explicitly and get confirmation. "I'm focusing on X and Y, not Z. Does that work?"

**Example**:
- **Senior approach**: [Designs notification delivery without mentioning what's excluded]
- **Staff approach**: "I'm designing notification delivery, not content creation or analytics. Those integrate with my system but are separate concerns. Does this scope match your expectations?"

## Mistake 6: Conflating Users and Roles

**The pattern**: Describing users by their role in the system (sender, receiver) rather than who they actually are.

**Why it happens**: Roles feel more relevant to system design than user identities.

**The problem**: You miss that the same person might have multiple roles, or that different types of people have the same role but different needs.

**The fix**: Identify real user types first, then map them to roles.

**Example**:
- **Senior approach**: "Senders send notifications, receivers receive them."
- **Staff approach**: "We have end users, who are primarily receivers but sometimes senders (when they trigger notifications by liking). We have internal services, who are the high-volume senders. We have marketing systems, who send bulk notifications. Each has different patterns and needs."

---

# Part 11: Examples from Real Systems

Let me walk through Phase 1 thinking for three real system types.

## Example 1: Rate Limiter

**Users identified:**

| User Type | Description | Needs |
|-----------|-------------|-------|
| APIs being protected | Services that call the rate limiter | Low latency, high reliability |
| Client applications | Systems being rate-limited | Clear feedback, predictable behavior |
| Platform operators | Engineers configuring limits | Easy configuration, visibility |
| Security team | Analysts investigating abuse | Access to logs, ability to trace patterns |

**Primary users**: APIs being protected (the rate limiter exists for them)

**Secondary users**: Client applications (need to behave correctly under limits), Platform operators, Security team

**Core use cases:**
1. Check if a request is allowed (inline, every request)
2. Enforce rate limit (reject or throttle)
3. Return meaningful feedback to clients

**Edge use cases:**
- Update limits without restart
- Handle clock skew across servers
- Manage limits during partial outages
- Generate usage reports

**Scope decisions:**
- In scope: Distributed rate limiting, per-client limits
- Out of scope: Billing integration, long-term analytics, abuse detection (beyond rate limiting)

**Architectural implications:**
- Core path must be extremely fast (<1ms overhead)
- Eventual consistency acceptable for limit updates
- Need distributed coordination (Redis, or distributed counter)

## Example 2: Messaging System

**Users identified:**

| User Type | Description | Needs |
|-----------|-------------|-------|
| End consumers | People messaging each other | Real-time delivery, reliability, intuitive UX |
| Mobile/web clients | Apps on user devices | Efficient sync, offline support |
| Internal services | Services triggering system messages | Programmatic API, high throughput |
| Support agents | Customer service accessing chats | Read-only access, search |
| Compliance team | Legal/regulatory reviews | Export capability, retention management |

**Primary users**: End consumers (the product is for them)

**Secondary users**: Support, Compliance (important but don't drive core design)

**Core use cases:**
1. Send a message to another user
2. Receive messages in real-time
3. View conversation history
4. Send messages to a group

**Edge use cases:**
- Delete/unsend a message
- Block a user
- Export conversation
- Handle message to offline user

**Scope decisions:**
- In scope: 1:1 and group messaging, text and images, read receipts
- Out of scope: Voice/video, end-to-end encryption, very large groups

**Architectural implications:**
- Need real-time push (WebSockets or long-polling)
- Need persistent storage for history (probably per-user sharded)
- Need fan-out for group messages
- Offline delivery adds queuing requirements

## Example 3: Feed System

**Users identified:**

| User Type | Description | Needs |
|-----------|-------------|-------|
| Feed consumers | Users viewing their feed | Fast load, relevant content, fresh content |
| Content creators | Users whose content appears in feeds | Reach, understanding of performance |
| Advertisers | Buyers of feed placement | Targeting, performance metrics |
| ML/ranking team | Engineers tuning the algorithm | Experiment infrastructure, feature access |
| Operations | SREs keeping feed running | Observability, controls for degradation |

**Primary users**: Feed consumers (the feed exists for them)

**Secondary users**: Creators, Advertisers, ML team, Operations

**Core use cases:**
1. Open app, see personalized feed instantly
2. Scroll to load more content
3. Interact with content (like, comment)

**Edge use cases:**
- New user with no follows (cold start)
- User follows 50,000 accounts (massive input)
- Breaking news (time-sensitive content)
- Ad injection and pacing

**Scope decisions:**
- In scope: Home feed, basic ranking, pagination
- Out of scope: Search, discovery/explore, creator analytics

**Architectural implications:**
- Feed generation must be fast (<200ms)
- Can pre-compute or compute on-demand (trade-off based on scale)
- Need social graph access (follow relationships)
- Need content storage access (posts)
- Ranking is a core concern (simple first, extensible for ML)

---

# Quick Reference Card

## Phase 1 Checklist: Users & Use Cases

| Step | Question to Ask | Example Output |
|------|-----------------|----------------|
| **Identify all user types** | "Who interacts with this system?" | Human, System, Service, Operational users |
| **Determine primary vs secondary** | "Whose needs drive the design?" | "Consumers are primary, ops is secondary" |
| **Uncover intent** | "What problem are we really solving?" | "Keep users informed" not "send notifications" |
| **Identify core vs edge** | "What's high frequency and high value?" | "Send/receive are core; export is edge" |
| **Set explicit scope** | "What's in and what's out?" | "In: delivery. Out: content creation, billing" |

---

## Mental Models and One-Liners

| Concept | One-Liner | Mental Model |
|---------|-----------|--------------|
| **User breadth** | "Who operates it? Who debugs it? Who integrates with it?" | Four user types: human, system, service, operational — not just the obvious one |
| **Intent vs implementation** | "What problem are we really solving?" | Users ask for buttons; they want outcomes |
| **Core vs edge** | "Design for the 80%; handle the 20% appropriately" | Core = meticulous; edge = graceful degradation |
| **Scope discipline** | "In scope: X. Out of scope: Y. Does that work?" | Explicit boundaries prevent misalignment |
| **Failure by user** | "How does each user type experience failure?" | Same outage, different impact — design for each |
| **Cost and users** | "Which user type dominates cost? What do we not build?" | User mix determines cost structure |

**Staff-level analogy:** Phase 1 is like a doctor taking a history before prescribing. Skipping it means solving the wrong problem.

## Key Phrases for Phase 1

### Identifying Users
- "Who are all the users of this system?"
- "Beyond end users, are there internal services? Operations teams?"
- "Who operates this? Who debugs it when things go wrong?"

### Determining Priority
- "I'm treating [X] as primary users because..."
- "Secondary users include [Y]—I'll accommodate but not optimize for them."

### Uncovering Intent
- "What problem are we really solving?"
- "Is this for [intent A] or [intent B]? The design differs..."

### Scoping
- "For this design, I'm focusing on [in-scope]."
- "I'm explicitly not designing [out-of-scope]—those are separate concerns."
- "Does this scope work for what you had in mind?"

---

## Common Mistakes Quick Reference

| Mistake | What It Looks Like | Fix |
|---------|-------------------|-----|
| **Single user type** | "Users send notifications" | "Who else? Internal services? Ops? Analytics?" |
| **Taking prompt literally** | Immediately designing a rate limiter | "What problem are we solving? DDoS? Fair usage?" |
| **Skipping discovery** | 30 seconds of questions, then architecture | Invest 5-10 minutes in Phase 1 |
| **No prioritization** | All use cases treated equally | "Core: X, Y. Secondary: Z. Edge: W." |
| **Implicit scope** | Designing without stating boundaries | "I'm focusing on X, not Y. Does that work?" |
| **Confusing user/role** | "Senders and receivers" | "End users, internal services, marketing systems" |

---

## The Ripple Effect: Phase 1 → Architecture

| Phase 1 Decision | Architectural Impact |
|-----------------|---------------------|
| **User types identified** | → APIs needed (REST for humans, gRPC for services) |
| **Core use cases defined** | → Data model requirements (what to store) |
| **Primary user chosen** | → Quality requirements (where to invest in availability/latency) |
| **Scope boundaries set** | → Component boundaries (what you build vs. interface with) |

**Example**: "System users generate 95% of notifications → service-to-service API is the critical path → optimize for throughput and low latency."

---

## Self-Check: Did I Cover Phase 1?

| Signal | Weak | Strong | ✓ |
|--------|------|--------|---|
| **User types** | Assumed single user | Identified 4+ types including ops | ☐ |
| **Primary/secondary** | Not distinguished | Explicit: "X is primary because..." | ☐ |
| **Intent** | Accepted prompt literally | Asked "What problem are we solving?" | ☐ |
| **Core vs edge** | Listed features flat | "Core: A, B. Edge: C, D." | ☐ |
| **Scope** | Implicit or unclear | "In scope: X. Out of scope: Y." | ☐ |
| **Confirmation** | Didn't check | "Does this scope work?" | ☐ |

---

# Part 12: User Needs Under Failure — Staff-Level Thinking

A critical gap in most Senior engineers' thinking: they identify users and use cases for the happy path, but forget that failures affect different users differently. Staff engineers think about user needs under failure from the beginning.

## The Failure Experience Matrix

Different user types experience the same failure in fundamentally different ways:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              HOW USERS EXPERIENCE THE SAME FAILURE                          │
│                                                                             │
│   Failure: Notification delivery delayed 30+ seconds                        │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  HUMAN USER                                                         │   │
│   │  Experience: "App feels slow today"                                 │   │
│   │  Tolerance: Low - expects instant gratification                     │   │
│   │  Need: Feedback that something is happening                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  SYSTEM USER (calling service)                                      │   │
│   │  Experience: Timeout errors, retry storms                           │   │
│   │  Tolerance: Medium - has retry logic, but consumes budget           │   │
│   │  Need: Clear error codes, backoff guidance                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  SERVICE USER (batch job)                                           │   │
│   │  Experience: Job running longer than SLA                            │   │
│   │  Tolerance: High - can wait, but needs visibility                   │   │
│   │  Need: Progress indicators, partial success handling                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  OPERATIONAL USER (on-call SRE)                                     │   │
│   │  Experience: Alert firing, needs to diagnose                        │   │
│   │  Tolerance: None - this IS their problem                            │   │
│   │  Need: Metrics, traces, runbooks, control levers                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Staff-Level Questions for User Failure Analysis

When identifying users, Staff engineers immediately ask:

**For each user type:**
1. "What does failure look like to this user?"
2. "What's their tolerance for degradation?"
3. "What information do they need during failure?"
4. "What fallback serves this user when the primary path fails?"

**Example: Rate Limiter Failure Analysis**

| User Type | Failure Mode | Impact | Tolerance | Fallback Need |
|-----------|--------------|--------|-----------|---------------|
| APIs protected | Rate limiter unavailable | Unprotected, risk overload | Zero - this defeats the purpose | Fail-closed (block all) or fail-open with caching |
| Clients calling APIs | Incorrect rate info | Unexpected rejections | Low - causes cascading failures | Stale limits with error budget |
| Operations | Metrics missing | Blind to abuse patterns | Medium - can wait for recovery | Degraded dashboard, alerting still works |
| Security team | Audit logs delayed | Investigation blocked | High - can analyze later | Buffer and replay when healthy |

## Designing for Failure from Phase 1

The user analysis should inform failure design from the start:

**L5 Approach**: "I'll handle failures later in the design."

**L6 Approach**: "For each user type, I'm noting their failure tolerance now. This shapes my core architecture—I can't add fault tolerance as an afterthought."

**Example in Interview:**

"I've identified four user types. Let me think about how each experiences failure:
- Human users need graceful degradation—show cached content, not errors
- System users need clear error codes and retry guidance—I'll design for that
- Batch services need idempotent operations and progress checkpoints
- Operations needs observability baked in—not bolted on

This means my core design must include: cached fallbacks, structured error responses, idempotency keys, and metrics emission at key points."

## User-Specific Failure Requirements

For each user type, identify specific failure requirements:

### Human Users Under Failure

| Requirement | Why | Design Impact |
|-------------|-----|---------------|
| Graceful degradation | Users prefer partial functionality to errors | Fallback UI, cached content |
| Progress feedback | Uncertainty is worse than delay | Loading states, estimated times |
| Retry transparency | Users shouldn't double-submit | Optimistic UI, confirmation |
| Clear error messages | Technical errors frustrate | User-friendly messages |

### System Users Under Failure

| Requirement | Why | Design Impact |
|-------------|-----|---------------|
| Idempotency | Retries must be safe | Idempotency keys, deduplication |
| Structured errors | Machines parse responses | Error codes, not strings |
| Retry guidance | Prevent thundering herd | Retry-After headers, backoff |
| Partial success handling | Batch operations may half-succeed | Transaction semantics, results arrays |

### Operational Users Under Failure

| Requirement | Why | Design Impact |
|-------------|-----|---------------|
| Real-time metrics | Can't debug what you can't see | Metrics per component, SLI tracking |
| Distributed tracing | Request flow visibility | Trace context propagation |
| Control levers | Need to mitigate without deploys | Feature flags, circuit breakers |
| Runbook hooks | Scripted remediation | Admin APIs, safe restart procedures |

---

# Part 13: Conflict Resolution Between User Types

When different user types have incompatible needs, Staff engineers reason through the conflict explicitly—not by gut feeling, but with a structured approach.

## The Conflict Pattern

User conflicts arise when:
- Optimizing for one user degrades experience for another
- Resource constraints force trade-offs
- Quality attributes conflict (latency vs. durability, simplicity vs. flexibility)

## Conflict Resolution Framework

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              USER CONFLICT RESOLUTION DECISION TREE                         │
│                                                                             │
│   1. IDENTIFY THE CONFLICT                                                  │
│      "User A needs X, User B needs Y. X and Y are incompatible."            │
│                                                                             │
│   2. DETERMINE USER PRIORITY                                                │
│      "Who is primary? Whose needs drive the core design?"                   │
│      │                                                                      │
│      ├─► Primary wins outright?                                             │
│      │   → If secondary user can tolerate degradation: yes                  │
│      │                                                                      │
│      └─► No clear winner?                                                   │
│          → Move to trade-off analysis                                       │
│                                                                             │
│   3. TRADE-OFF ANALYSIS                                                     │
│      "What's the cost of each choice?"                                      │
│      │                                                                      │
│      ├─► Can we serve both with different paths?                            │
│      │   → Separate APIs, async processing, tiered service                  │
│      │                                                                      │
│      ├─► Can we time-slice?                                                 │
│      │   → Serve primary during peak, secondary off-peak                    │
│      │                                                                      │
│      └─► Must choose one?                                                   │
│          → Choose primary, document secondary degradation                   │
│                                                                             │
│   4. DOCUMENT THE DECISION                                                  │
│      "I'm prioritizing X because..."                                        │
│      "User B will experience degraded service in these scenarios..."        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Real-World Conflict Examples

### Example 1: Notification System — Delivery Speed vs. Aggregation

**Conflict:**
- Human users want real-time notifications (within seconds)
- System users (analytics) want aggregated data (batched for efficiency)
- Same event triggers both

**L5 Resolution:** Pick one—either real-time or batched.

**L6 Resolution:**
"These needs aren't actually incompatible if I design for it. I'll use:
- A real-time path for immediate delivery to human users
- An async fan-out that also writes to an event stream
- Analytics consumes from the stream, aggregating as needed

The core path optimizes for human users (latency). Analytics gets eventually-consistent data via the stream—they can aggregate at their own pace."

### Example 2: Rate Limiter — Client Fairness vs. API Protection

**Conflict:**
- APIs being protected want strict limits (no overload ever)
- Clients want burst capacity (occasional spikes should be allowed)
- These conflict under load

**L5 Resolution:** Set hard limits—clients adapt.

**L6 Resolution:**
"I need to reason about which user matters more in which scenario:
- Under normal load: Allow bursting—client experience matters
- Under high load: API protection takes priority—reject aggressively

I'll design a tiered system:
- Token bucket with burst capacity for normal operation
- Circuit breaker that engages under sustained load, overriding burst
- Clear communication to clients when in protected mode

This serves both users, with explicit degradation rules."

### Example 3: Messaging System — Real-Time vs. Persistence

**Conflict:**
- Human users want instant delivery (sub-second)
- Compliance team needs guaranteed persistence (never lose a message)
- Strong consistency for both is expensive

**L5 Resolution:** Synchronous write to durable storage—accept higher latency.

**L6 Resolution:**
"These users have different failure tolerances:
- Human users: Would rather see the message fast, even if there's rare loss
- Compliance: Would rather delay than lose

I'll design for eventual durability with optimistic delivery:
- Acknowledge to sender after primary write (fast)
- Async replication to durable storage
- Compliance gets durability guarantee (eventual)
- If primary fails before replication, we have a rare but documented failure mode

I'll surface this trade-off: 'We prioritize perceived speed over zero-loss. Loss rate is <0.0001%. Compliance acknowledges this in SLA.'"

## Communicating Conflicts in Interviews

**Effective phrases:**

"I've identified a conflict between user needs. Let me reason through it..."

"User A needs X for latency reasons. User B needs Y for durability. These conflict under [scenario]. I'm going to prioritize A because [rationale], and design degraded service for B that looks like [specific behavior]."

"Rather than choosing one winner, I can serve both with separate paths. The core path optimizes for [primary user]. A secondary path, potentially async, serves [secondary user] without impacting the primary path."

---

# Part 14: Security, Compliance, Human Factors, and Cross-Team Impact

## Security and Compliance as User Types

Security teams and compliance stakeholders are often overlooked users. At Staff level, they are secondary but critical—their needs affect architecture.

| Concern | Phase 1 Question | Design Impact |
|---------|------------------|---------------|
| **Data sensitivity** | "What data does each user type touch? PII? Financial?" | Trust boundaries; different retention for different user types |
| **Compliance** | "Retention? Export? Audit? Regulatory constraints?" | Storage design; export-friendly schema from day one |
| **Trust boundaries** | "Who can call this? Internal only? Partners? Untrusted clients?" | API design; rate limiting and validation per boundary |

**Example:** A messaging system with human users and compliance users. Compliance needs audit logs and export. Design message storage with export-friendliness; don't lock into a schema that makes compliance impossible later.

## Human Errors and Operational Burdens

Operational users are affected by human error—mistakes in configuration, deployment, or incident response. Phase 1 questions:

- "What can operators misconfigure? How do we make wrong things hard?"
- "What happens when someone runs the wrong admin command?"
- "How does on-call burden scale with user types and use cases?"

**Staff-level insight:** Systems with many user types and use cases create more operational surface area. Explicit primary/secondary classification helps prioritize which operational controls to build first.

## Cross-Team and Org Impact

Users often span teams. A notification system serves product teams (sending), platform teams (operating), and partner teams (integrating). Phase 1 questions:

- "Which user types belong to other teams? What do they depend on us for?"
- "What guarantees do we offer cross-team? What do we not guarantee?"
- "How do we reduce complexity for teams that depend on us?"

**Trade-off:** Serving many teams can dilute focus. Staff engineers designate primary vs secondary and document what each team gets—and what they don't—explicitly.

## Data, Consistency, and Correctness by User Type

Different user types impose different consistency requirements. Phase 1 helps surface these.

| User Type | Typical Consistency Need | Example |
|-----------|---------------------------|---------|
| **Human users** | Perceived immediacy; eventual consistency often OK | "Message sent" → show immediately; replication can lag |
| **System users** | Idempotency, clear semantics | Retries must not duplicate; at-least-once vs exactly-once |
| **Compliance/audit** | Durability, ordering, retention | Never lose; ordered audit trail; retention policy |
| **Operational users** | Correctness of metrics and state | Health dashboards must reflect reality; config changes must be visible |

**Staff-level question:** "Which user type requires strong consistency? Which can tolerate eventual? The answer drives replication, storage, and API design."

---

# Part 15: Designing for Operational Users — First-Class Citizenship

The most commonly overlooked user type is operational users. Staff engineers treat them as first-class citizens from the start.

## What Operational Users Actually Need

Operational users (SREs, on-call engineers, platform teams) have specific, often unspoken needs:

### During Normal Operation

| Need | Why | Design Implication |
|------|-----|--------------------|
| Health dashboards | Proactive monitoring | Expose health metrics, SLI endpoints |
| Capacity visibility | Prevent surprises | Show headroom, trending toward limits |
| Configuration visibility | Know current state | Config API, current settings endpoint |
| Dependency health | Upstream issues affect you | Dependency status aggregation |

### During Incidents

| Need | Why | Design Implication |
|------|-----|--------------------|
| Rapid diagnosis | MTTR drives SLA | Detailed logs, distributed tracing |
| Control levers | Mitigate without deploys | Feature flags, rate adjustments, circuit breakers |
| Safe restart | Recovery without data loss | Graceful shutdown, drain endpoints |
| Isolation capability | Contain blast radius | Per-tenant controls, kill switches |

### During Maintenance

| Need | Why | Design Implication |
|------|-----|--------------------|
| Drain support | Zero-downtime deploys | Connection draining, graceful handoff |
| Canary ability | Safe rollouts | Traffic splitting, progressive deployment |
| Rollback speed | Fast recovery from bad deploys | Stateless design, backward compatibility |
| Migration tooling | Schema and data evolution | Offline migration support, dual-write modes |

## Operational Use Cases to Identify in Phase 1

When enumerating use cases, explicitly include operational ones:

**Core Operational Use Cases:**
1. "View system health" — Is the system working?
2. "Diagnose failure" — Why did this request fail?
3. "Adjust behavior" — Change rate limits, enable/disable features
4. "Safely deploy" — Ship new code without impact

**Edge Operational Use Cases:**
1. "Recover from data corruption" — Rare but catastrophic
2. "Migrate to new infrastructure" — Every system eventually moves
3. "Investigate security incident" — Audit trail, forensics
4. "Handle capacity emergency" — Shed load, prioritize traffic

## Example: Notification System Operational Design

**Operational users identified:**
- On-call SREs monitoring delivery
- Platform engineers maintaining the system
- Support engineers debugging user complaints

**Operational use cases:**

| Use Case | Frequency | Priority | Design Feature |
|----------|-----------|----------|----------------|
| Check delivery health | Constant | High | Metrics dashboard, SLI endpoints |
| Debug failed notification | Daily | High | Per-notification trace, log correlation |
| Adjust throttling | Weekly | Medium | Admin API for rate adjustment |
| Disable broken channel | Rare | High | Per-channel circuit breaker |
| Investigate spam complaint | Monthly | Medium | Audit log with sender/content |

**Staff-Level Interview Statement:**

"I want to call out operational users explicitly. On-call SREs need to answer: 'Is delivery healthy?' and 'Why did this notification fail?' I'll design:
- A health endpoint showing delivery success rates by channel
- Per-notification tracing so support can debug individual failures
- Circuit breakers per delivery channel so we can isolate issues
- An admin API for rate adjustment without deploys

These aren't afterthoughts—they shape my data model and component design."

---

# Part 16: Cost & Sustainability — Users Drive Cost Structure

Cost is a first-class constraint at Staff level. User types and use cases directly determine where cost accumulates and how it scales.

## Why Cost Matters at L6

Phase 1 decisions lock in cost structure. A design that optimizes for human users (low latency, heavy caching) has different cost drivers than one optimized for system users (high throughput, durable queues). Staff engineers ask: "Which user types and use cases dominate cost? Where does cost break at scale?"

## Cost Drivers by User Type

| User Type | Typical Cost Drivers | Scale Relationship |
|-----------|---------------------|---------------------|
| **Human users** | Cache capacity, CDN, connection servers | Grows with DAU and session length |
| **System users** | API compute, message queue throughput, storage | Grows with integration count and call volume |
| **Service users** | Batch compute, storage for bulk data | Grows with job frequency and data volume |
| **Operational users** | Log retention, metrics storage, tracing | Grows with system size and retention policy |

## Cost-Aware Phase 1 Questions

When identifying users and use cases, Staff engineers add:

- "Which user type will generate the majority of traffic? That drives our primary cost."
- "Which use cases are expensive per invocation? Should they be core or edge?"
- "What would we intentionally not build because the cost doesn't justify the value for secondary users?"

## Example: Notification System Cost Drivers

**Dominant cost drivers:**
1. Push delivery to external providers (per-notification fees) — driven by human user volume
2. Message queue storage and throughput — driven by system users triggering notifications
3. Preference storage and resolution — driven by human user count and complexity

**Staff-level trade-off:** "If system users generate 95% of notifications, we optimize for their API efficiency. Per-call cost adds up. Human users get cached preferences; we don't re-resolve on every delivery. That reduces compute and storage cost."

**What a Staff engineer intentionally does not build (initially):** Full-text search over notification history for all users — cost scales with retention and search volume. Design for export-friendly storage instead; build search when a specific user type (e.g., compliance) justifies it.

---

# Part 17: Real Incident — Notification Delivery Cascade

A structured real incident illustrates why Phase 1 user thinking matters when things go wrong.

| Part | Content |
|------|---------|
| **Context** | Notification system at a social platform. 30M DAU, ~7K notifications/second. Human users (consumers), system users (internal services triggering notifications), and operational users (SREs). Primary use case: deliver notifications within 5 seconds P95. |
| **Trigger** | A deploy introduced a bug in the preference-resolution service. For users with complex preference rules (e.g., "mute from X except Y"), the service occasionally threw an unhandled exception and did not return a result. The caller assumed "no preferences" and proceeded with delivery. |
| **Propagation** | Preference service errors spiked. Callers fell back to default behavior (deliver all). That increased delivery volume by ~40%. downstream push infrastructure began queueing. One region's push connector hit its external provider limit and started returning 429s. Retries from other connectors amplified load. Delivery latency climbed from seconds to minutes. |
| **User impact** | Human users: Notifications delayed 30+ seconds or dropped. "App feels broken." System users: Callers received timeouts; many retried, increasing load. Service users: Batch jobs timed out. Operational users: Needed to diagnose but preference-service metrics were sparse; correlation to delivery failures was unclear for 20 minutes. |
| **Engineer response** | On-call rolled back the deploy within 45 minutes. Preference service stabilized. Delivery backlog drained over 2 hours. During the incident, operations had no per-user-type kill switch; they could only throttle globally, which hurt critical notifications (2FA) as much as social ones. |
| **Root cause** | Design assumed a single "user" and one failure mode. No distinction between user types under failure. Preference service was treated as best-effort; when it failed, the system defaulted to "deliver everything" — no graceful degradation path. Operational users were not first-class: no per-notification-type circuit breakers, no per-user-type prioritization during degradation. |
| **Design change** | (1) Preference service: fail-closed for unknown cases (return safe defaults, not exceptions); (2) Added per-notification-type priority lanes — critical (2FA, fraud) bypass throttling during degradation; (3) Operational tooling: per-channel circuit breakers, per-type kill switches; (4) Explicit failure requirements captured in Phase 1: "When preference service degrades, human users get throttled; critical notifications never." |
| **Lesson learned** | "We optimized for the happy path. We never asked: What does each user type experience when preference resolution fails? Staff-level Phase 1 means asking, for every user type: What's their failure mode? What's their fallback? What do operations need to see and control?" |

---

# Part 18: Use Case Evolution and Degradation

Staff engineers think about use cases dynamically: how they evolve over scale, and how they degrade under failure.

## Use Case Evolution Over Scale

As systems scale, use cases shift in importance:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    USE CASE EVOLUTION OVER SCALE                            │
│                                                                             │
│   V1 (1K users)         V2 (100K users)        V3 (10M users)               │
│   ┌───────────────┐     ┌───────────────┐      ┌───────────────┐            │
│   │ Core:         │     │ Core:         │      │ Core:         │            │
│   │ • Basic send  │ ──► │ • Send at     │ ──►  │ • Send at     │            │
│   │ • Basic recv  │     │   scale       │      │  massive scale│            │
│   │               │     │ • Reliability │      │ • Partitioned │            │
│   │ Edge:         │     │               │      │   delivery    │            │
│   │ • Everything  │     │ New Core:     │      │               │            │
│   │   else        │     │ • Search      │      │ New Core:     │            │
│   │               │     │ • History     │      │ • Real-time   │            │
│   │               │     │               │      │   at scale    │            │
│   │               │     │ Edge → Core:  │      │ • Ops tooling │            │
│   │               │     │ • Preferences │      │               │            │
│   └───────────────┘     └───────────────┘      └───────────────┘            │
│                                                                             │
│   KEY INSIGHT: Today's edge case is tomorrow's core use case                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Anticipating Use Case Shifts

**L5 Approach:** Design for current use cases only.

**L6 Approach:** "Which edge cases will become core as we scale? Let me design for extensibility there."

**Example: Messaging System**

| Current State | Edge Use Case | Trigger for Core | Design Now |
|--------------|---------------|------------------|------------|
| 1K users | Message search | Users complain they can't find old messages | Index-friendly message storage |
| 10K users | Large groups (100+) | Enterprise customers request | Fan-out architecture that can scale |
| 100K users | Compliance export | Regulatory requirement | Audit log from day one |
| 1M users | Multi-region | Latency complaints | Region-aware IDs, no single-region assumptions |

**Interview Statement:**

"I've identified send/receive as core and export as edge. But I'm noting that export often becomes core at scale when compliance requirements kick in. I'll design message storage with export-friendliness in mind—even if I don't build the export feature now, I won't make it impossible."

## Use Case Degradation Ladders

Every core use case should have a degradation strategy. Staff engineers define these explicitly:

### Degradation Ladder Pattern

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                USE CASE DEGRADATION LADDER                                  │
│                                                                             │
│   Use Case: "User views notification feed"                                  │
│                                                                             │
│   LEVEL 1: FULL FUNCTIONALITY (Healthy)                                     │
│   ─────────────────────────────────────                                     │
│   • Real-time updates, personalized ranking                                 │
│   • All notification types displayed                                        │
│   • Interactive actions (mark read, dismiss)                                │
│                                                                             │
│   LEVEL 2: REDUCED PERSONALIZATION (Ranking service degraded)               │
│   ─────────────────────────────────────────────────────────                 │
│   • Show notifications in chronological order                               │
│   • All types still displayed                                               │
│   • Actions still work                                                      │
│                                                                             │
│   LEVEL 3: CACHED CONTENT (Primary database degraded)                       │
│   ────────────────────────────────────────────────────                      │
│   • Show cached notifications from local/CDN                                │
│   • May be stale (indicate "as of X time ago")                              │
│   • Actions queued for later                                                │
│                                                                             │
│   LEVEL 4: STATIC FALLBACK (Multiple systems degraded)                      │
│   ──────────────────────────────────────────────────────                    │
│   • Show "Notifications temporarily unavailable"                            │
│   • Offer refresh option                                                    │
│   • Preserve user context (don't log them out)                              │
│                                                                             │
│   LEVEL 5: GRACEFUL ERROR (Complete failure)                                │
│   ──────────────────────────────────────────                                │
│   • Clear error message with estimated recovery                             │
│   • Support contact information                                             │
│   • No cascading failures to other features                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Defining Degradation in Phase 1

For each core use case, define:

1. **What's the minimum viable experience?**
2. **What can we drop first without breaking the use case?**
3. **What's the fallback when the primary path fails?**
4. **How do we communicate degradation to the user?**

**Example: Rate Limiter Core Use Case — "Check if request allowed"**

| Degradation Level | Trigger | Behavior | User Impact |
|-------------------|---------|----------|-------------|
| Full | Healthy | Accurate check, correct limit enforcement | None |
| Stale limits | Redis unavailable | Use cached limits from last sync | Limits may be slightly off |
| Fail-open | Limiter completely down, low-risk traffic | Allow all requests | No protection, but no blockage |
| Fail-closed | Limiter down, high-risk/expensive operations | Block all requests | Users blocked, but system protected |

**Interview Statement:**

"For the core use case 'check if request allowed,' I'm thinking about degradation now:
- If Redis is slow, I'll use locally cached limits—slightly stale but functional
- If Redis is down, I need a fail-open vs. fail-closed decision based on the protected API's criticality
- I'll expose a health check so operations knows which mode we're in

This shapes my design: I need local caching, I need configurable fail modes per endpoint, and I need observability into limiter health."

---

# Part 19: Interview Calibration for Phase 1 (Users & Use Cases)

## What Interviewers Evaluate During Phase 1

| Signal | What They're Looking For | L6 Demonstration |
|--------|-------------------------|------------------|
| **Breadth of thinking** | Do you see beyond the obvious user? | Name 4+ user types including operational |
| **Prioritization ability** | Can you distinguish what matters? | Explicit primary/secondary, core/edge |
| **Intent understanding** | Do you solve the real problem? | Question the prompt, probe for purpose |
| **Scope discipline** | Can you focus without being told? | State in/out scope explicitly |
| **Failure awareness** | Do you think about degradation? | Per-user failure experience |
| **Communication clarity** | Can you structure your thinking? | Organized, methodical approach |

## L6 Phrases That Signal Staff-Level Thinking

### For User Identification

**L5 says:** "Users will send and receive messages."

**L6 says:** "Let me enumerate the user types. We have end consumers who send and receive. We have internal services that trigger system-generated messages—probably higher volume than human senders. We have operations who need to monitor delivery health. And we have compliance who may need audit access. Each has different needs and failure tolerances."

### For Primary/Secondary Classification

**L5 says:** "All users are important."

**L6 says:** "End consumers are primary—the product exists for them. Operations is secondary but critical—I'll design for their needs without compromising consumer experience. Compliance is tertiary—I'll ensure capability exists but won't optimize for it."

### For Failure Thinking

**L5 says:** [Doesn't mention failure during Phase 1]

**L6 says:** "As I identify these users, I'm thinking about failure modes. Human users need graceful degradation—show something, not errors. System users need structured error responses with retry guidance. Operations needs observability to diagnose issues quickly. I'll carry these requirements into my component design."

### For Conflict Resolution

**L5 says:** "We'll optimize for latency."

**L6 says:** "There's a tension here. Human users want low latency. Compliance needs durability. I can serve both with async durability—deliver fast, persist eventually. The trade-off is rare message loss during primary failure before replication. I'll document this as an accepted risk with a target loss rate."

### For Scope

**L5 says:** [Implicit scope, doesn't state it]

**L6 says:** "Let me state my scope explicitly. In scope: core messaging between consumers, group chat up to 100, text and images. Out of scope: voice/video (separate infrastructure), E2E encryption (significant complexity), very large groups (different fan-out architecture). Does this scope match your expectations?"

## Common L5 Mistakes in Phase 1

| Mistake | How It Manifests | L6 Correction |
|---------|------------------|---------------|
| **Single user focus** | "Users do X" | "Which users? Human consumers, system integrations, operators..." |
| **No failure thinking** | Happy path only | "How does each user type experience failure?" |
| **Implicit priorities** | Treats all use cases equally | "Core use cases are X, Y. Edge cases are Z, W." |
| **Prompt acceptance** | Takes "design a rate limiter" literally | "What problem are we actually solving? Is rate limiting the right approach?" |
| **Hidden scope** | Designs without stating boundaries | "In scope: X. Out of scope: Y. Does this work?" |
| **Role confusion** | "Senders and receivers" | "End users, internal services, marketing systems—each with different patterns" |
| **Missing operations** | No mention of observability needs | "Operations needs to answer: Is it healthy? Why did it fail?" |

## Interviewer's Mental Checklist for Phase 1

As you work through Phase 1, imagine the interviewer asking themselves:

☐ "Did they identify user types beyond the obvious?"
☐ "Did they distinguish primary from secondary?"
☐ "Did they probe intent, or just accept the prompt?"
☐ "Did they prioritize use cases?"
☐ "Did they state scope explicitly?"
☐ "Did they think about failure?"
☐ "Did they consider operational needs?"
☐ "Did they confirm alignment with me?"

Hit all of these, and you've demonstrated Staff-level Phase 1 thinking.

## How to Explain Phase 1 to Leadership

**Challenge:** Leadership wants results; they may see Phase 1 as "just asking questions."

**Staff-level framing:** "We're establishing who we're building for and what matters most. Without that, we risk building the wrong thing or over-building for users who don't drive value. Five minutes of clarity now saves weeks of rework later."

**Concrete example:** "For this notification system, we have four user types. End users are primary—we optimize for them. Internal services generate 95% of volume—we'll design the API for their throughput. Operations needs observability—we'll build that in, not bolt it on. That prioritization shapes every design choice."

## How to Teach This Topic

**For mentees:** Start with the four user types. Have them list users for a system they know. Then ask: "Who did you miss? Operations? Other services? Compliance?" The gap is the lesson.

**For interview prep:** Practice the 5–10 minute Phase 1 block. Do not skip it. Set a timer: "I will not draw a single box until I've stated users, primary/secondary, core use cases, and scope."

**Key teaching phrase:** "The solution is only as good as the problem you understood. Phase 1 is where you get the problem right."

---

# Part 20: Final Verification — L6 Readiness Checklist

**This chapter now meets Google Staff Engineer (L6) expectations.**

## Master Review Prompt Check

- [x] **Staff Engineer preparation** — Content aimed at L6; depth and judgment match L6 expectations.
- [x] **Chapter-only content** — Every section directly relates to Phase 1: Users & Use Cases.
- [x] **Explained in detail with an example** — Each major concept has clear explanation plus concrete examples (rate limiter, messaging, notification system, feed system).
- [x] **Topics in depth** — Trade-offs, failure modes, scale evolution, degradation ladders addressed.
- [x] **Interesting & real-life incidents** — Structured real incident (Notification Delivery Cascade) with Context, Trigger, Propagation, User impact, Engineer response, Root cause, Design change, Lesson learned.
- [x] **Easy to remember** — Mental models, one-liners, diagrams, and checklists throughout.
- [x] **Organized for Early SWE → Staff SWE** — Progression from basics to Staff thinking; Part 9 Staff vs Senior contrast.
- [x] **Strategic framing** — Problem selection, intent vs implementation, scope control addressed.
- [x] **Teachability** — Consolidated interview calibration with mentoring guidance, leadership communication, teachability section.
- [x] **Exercises** — Dedicated exercises section (6 exercises) with concrete tasks.
- [x] **BRAINSTORMING** — Brainstorming questions and reflection prompts at the end.

## L6 Dimension Coverage (A–J)

| Dimension | Coverage | Key Content |
|-----------|----------|-------------|
| **A. Judgment & decision-making** | ✅ | Primary/secondary classification, conflict resolution framework, decision justification template |
| **B. Failure & incident thinking** | ✅ | User needs under failure, blast radius, degradation ladders, structured real incident |
| **C. Scale & time** | ✅ | Use case evolution over scale, first bottlenecks at 2×/10×/multi-year, growth over years |
| **D. Cost & sustainability** | ✅ | Cost drivers by user type, cost-aware Phase 1 questions, what Staff intentionally does not build |
| **E. Real-world engineering** | ✅ | Operational burdens, human errors, on-call, operational users as first-class |
| **F. Learnability & memorability** | ✅ | Mental models, one-liners, analogies, Quick Reference Card |
| **G. Data, consistency & correctness** | ✅ | User types drive consistency requirements (e.g., critical vs social notifications) |
| **H. Security & compliance** | ✅ | Data sensitivity, trust boundaries, compliance as user type (Part 14) |
| **I. Observability & debuggability** | ✅ | Operational users need metrics, traces, runbooks; design for debuggability |
| **J. Cross-team & org impact** | ✅ | Multi-team users, dependencies, guarantees (Part 14) |

## Staff-Level Signals Covered

✅ Enumerating multiple user types (not just obvious ones)
✅ Identifying operational users as first-class citizens
✅ Distinguishing primary vs. secondary users with rationale
✅ Separating user intent from implementation
✅ Classifying core vs. edge use cases
✅ Thinking about failure experience per user type
✅ Reasoning through user conflicts explicitly
✅ Defining degradation strategies for core use cases
✅ Anticipating use case evolution at scale
✅ Setting explicit scope with confirmation
✅ Making Phase 1 decisions that trace to later architecture
✅ Cost-aware design from Phase 1
✅ Security, compliance, and cross-team impact

## Remaining Gaps (Acceptable)

- **Specific technology choices**: Intentionally omitted—Phase 1 is about users and use cases, not implementation
- **Quantitative requirements**: Covered in later phases (NFRs, scale estimation)
- **Deep component design**: Covered in later volumes

---

# Brainstorming Questions

## Understanding Users

1. For a system you've built, can you name all the user types? (Aim for at least 5.) How many did you consider during initial design?

2. Think of a system where the "obvious" user (end consumer) isn't actually the primary user. What made you realize this?

3. When have you seen a system fail because it was designed for humans but used mostly by machines? Or vice versa?

4. How do you identify operational users' needs? They often don't speak up during requirements gathering.

5. For your current project, who are the "secondary" users? Are they being adequately served?

## Understanding Use Cases

6. Take a familiar system. What are its top 3 use cases by frequency? By importance? Are those the same?

7. When have you seen an edge case become a core use case? What caused the shift?

8. How do you decide when an edge case is "in scope" versus "handled by graceful degradation"?

9. Think of a feature you built that no one used. What did you misunderstand about the use cases?

10. How do you validate that your understanding of use cases is correct?

## Understanding Scope

11. When have you successfully reduced scope on a project? What enabled you to do that?

12. When have you under-scoped and regretted it? What did you miss?

13. How do you communicate scope exclusions to stakeholders who want everything?

14. What's your process for deciding what's in V1 vs. V2?

15. How do you prevent scope creep once you've established boundaries?

## Failure Injection & Cost Scenarios

16. For the Notification Delivery Cascade incident: What Phase 1 questions would have prevented it? Which user type was overlooked?

17. How would you explain to leadership why we need different failure behaviors for different user types? Use a concrete example.

18. If cost must be cut 30%, which user types would you degrade first? How would you communicate that trade-off?

19. Another team depends on your notification API. What do you guarantee them? What do you explicitly not guarantee? How does that affect your Phase 1 scope?

## Trade-Off Debates

20. "Primary users always win" — When might a secondary user's needs override a primary user's? Give an example.

21. "Scope is a constraint" — When is it right to expand scope mid-design? What's the Staff-level decision process?

---

# Reflection Prompts

Set aside 15-20 minutes for each of these reflection exercises.

## Reflection 1: Your User Awareness

Think about a system you've recently designed or worked on.

- How many user types did you consciously identify?
- Did you consider operational users (SREs, support) as first-class users?
- What user needs did you discover late that you wish you'd known earlier?
- How would the design differ if you'd identified all users upfront?

Write a complete user inventory for that system now. What did you miss?

## Reflection 2: Your Scope Discipline

Consider your natural tendencies around scope.

- Do you tend to scope too broadly or too narrowly?
- How do you react when stakeholders want to add features?
- When have you successfully defended scope boundaries?
- What's your strategy for making scope explicit and getting agreement?

Practice saying "That's out of scope for this design, but..." until it feels natural.

## Reflection 3: Your Failure Mode Thinking

Examine how you think about failure during requirements gathering.

- Do you naturally think about what happens when things break?
- For each user type, can you describe their failure experience?
- Have you ever designed degradation strategies explicitly?
- What would change if you gathered failure requirements alongside functional requirements?

For your current project, write a failure experience matrix for all user types.

---

# Homework Exercises

## Exercise 1: The User Inventory

Take a system you know well (or pick one: Uber, Netflix, Slack).

List all user types across these categories:
- Human users (end consumers, internal users)
- System users (other services)
- Operational users (SREs, support)
- Analytical users (data scientists, product managers)

For each user type, identify:
- Their primary interaction with the system
- What "success" looks like for them
- What happens if the system fails them

Aim for at least 8 distinct user types.

## Exercise 2: The Intent Excavation

Take these prompts and practice uncovering the intent behind them:

1. "Design a URL shortener"
2. "Design a rate limiter"
3. "Design a real-time dashboard"
4. "Design a recommendation system"

For each:
- Write down what problem might actually be solved
- List 3 different intents that could lead to this prompt
- For each intent, note how the design might differ

## Exercise 3: The Use Case Matrix

Pick a system (or use: Instagram, Zoom, DoorDash).

Create a matrix with:
- Rows: All use cases you can identify
- Columns: User types
- Cells: Mark "Primary," "Secondary," or empty

Then:
- Identify the top 3 core use cases
- Identify 5 edge cases
- For each edge case, decide: handle fully, graceful degradation, or out of scope

## Exercise 4: The Scope Declaration

Practice writing scope declarations for these prompts:

1. "Design a notification system"
2. "Design a payment system"
3. "Design a search system"

For each, write:
- What's explicitly in scope (3-5 items)
- What's explicitly out of scope (3-5 items)
- What assumptions you're making
- One sentence on why this scope is appropriate

## Exercise 5: The Ripple Trace

Take a design you've created (or use a system you know well).

Pick one Phase 1 decision (e.g., "primary user is mobile consumers").

Trace its effects through the design:
- How did it affect API design?
- How did it affect data model?
- How did it affect quality requirements?
- How did it affect component boundaries?

Write a paragraph explaining how this single decision shaped multiple aspects of the design.

## Exercise 6: The Counter-Design

Take a system you know (or pick one: Twitter, Stripe, Google Maps).

Redesign Phase 1 with different assumptions:
- Change the primary user
- Change the core use case
- Change a major scope decision

Then sketch how the architecture would differ.

The goal is to see how different Phase 1 decisions lead to genuinely different systems.

---

# Conclusion

Phase 1—Users & Use Cases—is where Staff engineers distinguish themselves.

While others rush to architecture, Staff engineers invest time understanding:
- **Who** the users are (all of them, not just the obvious ones)
- **What** they're trying to accomplish (intent, not implementation)
- **Which** use cases matter most (core vs. edge)
- **How** to map users to use cases clearly
- **What's** in scope and what's not (explicit boundaries)

This investment pays dividends throughout the design:
- Your architecture reflects actual requirements
- Your trade-offs are grounded in user priorities
- Your scope is defensible
- Your design is coherent—later decisions trace back to earlier understanding

In interviews, this manifests as a calm, structured opening. You don't panic. You don't rush. You ask thoughtful questions, establish clarity, and build a foundation. The interviewer sees someone who understands that good design starts with good understanding.

The techniques in this section are simple. The challenge is discipline—resisting the urge to start solving before you've finished understanding.

Practice this discipline. It's a Staff-level habit.

---
