# System Design Interview Preparation for Google Staff Engineer (L6)

## Volume 2, Section 1: The Staff-Level System Design Framework

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

---

## Phase 4: Non-Functional Requirements

### What This Phase Covers

Non-functional requirements describe the qualities the system must have. While functional requirements are about *what* the system does, non-functional requirements are about *how well* it does it.

**Key dimensions to explore:**

**Availability**: What percentage of time must the system be operational? 99%? 99.9%? 99.99%?

**Latency**: How fast must responses be? P50? P99? Different for different operations?

**Durability**: Can we lose data? What's the acceptable data loss?

**Consistency**: Do all users see the same data at the same time? Can we tolerate eventual consistency?

**Security**: What are the authentication, authorization, and data protection requirements?

**Compliance**: Are there regulatory requirements (GDPR, HIPAA, PCI)?

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
- Are there team skill constraints I should consider?"

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

# Conclusion

The Staff-Level System Design Framework is simple:

1. **Users & Use Cases**: Who are we building for and what are they trying to do?
2. **Functional Requirements**: What must the system do?
3. **Scale**: How big is this problem?
4. **Non-Functional Requirements**: What qualities must the system have?
5. **Assumptions & Constraints**: What are we taking as given?

But simple doesn't mean easy. Applying this framework well requires:
- The discipline to slow down when your instincts say "start building"
- The skill to ask probing questions that reveal hidden requirements
- The judgment to prioritize ruthlessly
- The communication ability to articulate your understanding clearly

This framework isn't just for interviews—it's how Staff engineers approach real work. Every design document at Google implicitly covers these five phases. Every technical discussion starts with understanding before solving.

When you internalize this framework, two things happen:

First, your interviews become more structured and confident. You know what to do in the first ten minutes. You know what questions to ask. You know how to establish a foundation before designing.

Second, your actual engineering becomes more effective. You start asking the right questions before writing code. You start calibrating your designs to actual requirements. You start making trade-offs explicit instead of implicit.

The framework is your lens. Every design problem looks different through it—and that differentiation is exactly what makes your designs appropriate rather than generic.

Master the framework. Use it consistently. Watch your system design transform.

---

*End of Volume 2, Section 1*

*Next: Volume 2, Section 2 – "Deep Dive: Storage and Database Design Patterns"*
