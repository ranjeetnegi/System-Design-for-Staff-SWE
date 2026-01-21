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

# System Design Interview Preparation for Google Staff Engineer (L6)

## Volume 2, Section 2: Phase 1 — Users & Use Cases: Staff-Level Thinking

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

# Part 9: Common Mistakes by Strong Senior Engineers

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

# Part 10: Examples from Real Systems

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

*End of Volume 2, Section 2*

# System Design Interview Preparation for Google Staff Engineer (L6)

## Volume 2, Section 3: Phase 2 — Functional Requirements: Staff-Level Precision

---

# Introduction

After understanding your users and their use cases, the next step is defining what the system actually does. This is Phase 2: Functional Requirements.

Functional requirements describe the behaviors and capabilities of your system. They answer the question: "What must this system do?" Not how it does it (that's architecture), not how well it does it (that's non-functional requirements), but what it does.

This sounds straightforward, and in some ways it is. But Staff-level precision in functional requirements is harder than it appears. Too vague, and your design has no foundation. Too detailed, and you've wasted precious interview time on specifications that don't matter. Too broad, and you'll never finish. Too narrow, and you've missed critical functionality.

Staff engineers hit the sweet spot: precise enough to drive design decisions, focused enough to fit the time available, complete enough to cover the core, and explicit enough about what's excluded.

This section will teach you how to define functional requirements with Staff-level precision. We'll cover what functional requirements really mean, how to distinguish core from supporting functionality, how to think about different types of system operations, how to handle edge cases explicitly, and how to avoid the feature creep that derails many designs.

---

# Part 1: What Functional Requirements Really Mean

## The Definition

Functional requirements describe what a system does—the capabilities it provides and the behaviors it exhibits. They are:

**Observable**: Users or other systems can see the effects
**Testable**: You can verify whether the system meets them
**Behavior-focused**: They describe what happens, not how it happens internally

Contrast with non-functional requirements, which describe qualities like performance, availability, and security. Functional requirements say "the system sends notifications"; non-functional requirements say "notifications are delivered within 5 seconds."

## Functional vs. Non-Functional: The Line

The distinction matters because functional and non-functional requirements drive different design decisions.

| Functional | Non-Functional |
|------------|----------------|
| Users can send messages | Messages are delivered within 1 second |
| Users can search their message history | Search returns results in under 200ms |
| Users can set notification preferences | Preferences take effect within 5 seconds |
| System logs all API calls | Logs are retained for 90 days |

When defining functional requirements, focus on the capability, not the quality. You'll address quality in Phase 4 (Non-Functional Requirements).

## Functional Requirements vs. Use Cases

Use cases describe user goals and workflows. Functional requirements describe system capabilities that enable those workflows.

**Use case**: "A user wants to message a friend."
**Functional requirements**:
- System allows users to compose and send messages
- System delivers messages to recipients
- System notifies recipients of new messages
- System stores messages for later retrieval

A single use case often requires multiple functional requirements. And a single functional requirement often supports multiple use cases.

## The Right Level of Detail

Functional requirements should be:

**Specific enough** to guide design decisions:
- ❌ "System handles messages" (too vague)
- ✅ "System allows users to send text messages up to 10,000 characters to other users"

**Abstract enough** to avoid implementation details:
- ❌ "System stores messages in a Cassandra table with user_id as partition key" (implementation)
- ✅ "System stores messages and allows retrieval by conversation"

**Bounded enough** to be achievable:
- ❌ "System handles all possible message types" (unbounded)
- ✅ "System handles text messages and image attachments"

---

# Part 2: Core vs. Supporting Functionality

## Defining the Distinction

Not all functionality is equally important. Staff engineers distinguish:

**Core functionality**: The capabilities without which the system has no value. These define the system's essential purpose. If core functionality fails, the system is useless.

**Supporting functionality**: Capabilities that enhance the system but aren't essential to its basic operation. The system still works (in a diminished way) if these fail.

## Why This Matters

This distinction drives multiple decisions:

**Design priority**: Core functionality is designed first and most carefully. Supporting functionality fits around it.

**Quality investment**: Core functionality needs the highest reliability and performance. Supporting functionality can have lower guarantees.

**Scope management**: When time is limited, supporting functionality is what you cut.

**Failure modes**: Core functionality failures are emergencies. Supporting functionality failures are degradations.

## Identifying Core Functionality

Ask these questions:

**Would the system be useless without this?**
- Sending messages in a messaging system: Yes → Core
- Read receipts in a messaging system: No → Supporting

**Is this the primary reason the system exists?**
- Rate limiting in a rate limiter: Yes → Core
- Usage analytics in a rate limiter: No → Supporting

**Would users abandon the product without this?**
- Viewing the feed in a social app: Yes → Core
- Filtering the feed by content type: No → Supporting

## Examples Across Systems

### Messaging System

**Core functionality:**
- Send a message to a user or group
- Receive messages in real-time
- Retrieve conversation history

**Supporting functionality:**
- Message reactions (emoji)
- Read receipts
- Typing indicators
- Message search
- Message deletion/unsend

### Rate Limiter

**Core functionality:**
- Check if a request is within limits
- Enforce the limit (allow or reject)
- Track usage per client/endpoint

**Supporting functionality:**
- View current usage
- Configure limits via API
- Generate usage reports
- Alert on limit exhaustion

### Feed System

**Core functionality:**
- Generate a personalized feed for a user
- Render feed content
- Support pagination/infinite scroll

**Supporting functionality:**
- Feed filtering by content type
- Hiding/snoozing accounts
- Saving posts for later
- Feed refresh controls

## Articulating the Distinction in Interviews

Make your prioritization explicit:

"For this notification system, the core functionality is:
1. Accepting notification requests from services
2. Delivering notifications to users across channels
3. Respecting user preferences

Supporting functionality includes:
- Notification history/inbox
- Analytics on open rates
- A/B testing notification content

I'll design the core in detail. Supporting functionality will inform my data model but won't be fully designed unless we have time."

---

# Part 3: Read, Write, and Control Flows

## The Three Flow Types

Most systems have three types of operations. Understanding these helps you enumerate functional requirements systematically.

**Read flows**: Operations that retrieve data without modifying it
- View messages
- Check rate limit status
- Fetch user profile
- Load feed

**Write flows**: Operations that create or modify data
- Send a message
- Update preferences
- Create a post
- Record an event

**Control flows**: Operations that modify system behavior or configuration
- Set rate limits
- Enable/disable features
- Configure routing rules
- Manage user permissions

## Why This Taxonomy Matters

Different flow types have different characteristics:

| Aspect | Read | Write | Control |
|--------|------|-------|---------|
| Frequency | Usually highest | Medium | Usually lowest |
| Latency sensitivity | Often high | Variable | Usually low |
| Consistency needs | Can be eventual | Often needs strong | Often needs strong |
| Failure tolerance | Can serve stale | Must not lose data | Must not corrupt state |
| Cacheability | Often cacheable | Not cacheable | Rarely relevant |

These differences drive design decisions. A system that's 99% reads might be designed completely differently from one that's 50% writes.

## Enumerating Flows Systematically

For each flow type, ask: "What operations exist?"

### Example: Notification System

**Read flows:**
- Fetch user preferences
- Get notification history for user
- Get delivery status of a notification
- View notification metrics (ops)

**Write flows:**
- Create/send a notification
- Mark notification as read
- Update user preferences
- Record delivery confirmation

**Control flows:**
- Enable/disable notification types
- Configure rate limits for notifications
- Set up routing rules (e.g., route to SMS if push fails)
- Manage channel configurations (APNs credentials, etc.)

### Example: Rate Limiter

**Read flows:**
- Check if request is allowed
- Get current usage for a client
- View configured limits

**Write flows:**
- Record a request (increment counter)
- Reset usage (periodic or manual)

**Control flows:**
- Configure rate limits
- Override limits for specific clients
- Enable/disable rate limiting
- Set up alerting thresholds

### Example: URL Shortener

**Read flows:**
- Resolve short URL to long URL
- Get analytics for a short URL
- List URLs created by a user

**Write flows:**
- Create a short URL
- Delete a short URL
- Record a click event

**Control flows:**
- Configure URL expiration policies
- Set up custom domain mappings
- Manage banned URL patterns

## Using Flows to Structure Requirements

In an interview, use this taxonomy to ensure completeness:

"Let me enumerate the functional requirements by flow type.

**Read flows:**
- Users can view their notification history
- Users can check their notification preferences
- Ops can view delivery metrics

**Write flows:**
- Services can send notifications to users
- Users can mark notifications as read
- Users can update their preferences

**Control flows:**
- Ops can configure notification routing
- Ops can enable/disable notification types

Does this cover the functionality you had in mind, or are there flows I'm missing?"

---

# Part 4: Defining Behavior Without Over-Specifying

## The Goldilocks Zone

Functional requirements need to be specific enough to be useful but not so detailed that they constrain implementation or waste time.

**Too vague:**
"System sends notifications"
- What triggers a notification?
- To whom?
- Through what channels?
- How do users control this?

**Too detailed:**
"When a user with ID matching pattern /^[a-z0-9]+$/ receives a message from a user they follow, and they have push_enabled=true in the preferences table, and they haven't been active in the last 5 minutes, send a push notification using Firebase Cloud Messaging with the message body truncated to 100 characters..."
- This is implementation, not requirements
- It constrains design unnecessarily
- It takes too long to articulate

**Just right:**
"When a triggering event occurs (like, comment, message, etc.), the system sends a notification to the affected user through their preferred channels, respecting their preference settings and suppression rules."
- Clear enough to understand what the system does
- Flexible enough to allow design choices
- Complete enough to identify key behaviors

## The Behavior Specification Pattern

A useful pattern for specifying behavior:

**When** [trigger condition] **the system** [action] **for** [affected entities] **according to** [relevant rules/conditions]

Examples:

"When a message is sent, the system delivers it to the recipient in real-time and stores it for later retrieval."

"When a request arrives, the system checks the client's usage against their configured limits and allows or rejects accordingly."

"When a user creates a short URL, the system generates a unique key and stores the mapping for the configured retention period."

## What to Specify vs. Leave Open

**Specify:**
- What triggers the behavior
- What the observable outcome is
- Who/what is affected
- What constraints or rules apply

**Leave open:**
- How the behavior is implemented
- What technologies are used
- Internal data representations
- Optimization strategies

**Example - Notification delivery:**

**Specify:**
- "Notifications are delivered to users in near-real-time"
- "Delivery occurs through the user's preferred channels"
- "Failed deliveries are retried up to 3 times"
- "Users can suppress notifications from specific sources"

**Leave open:**
- Whether to use push vs. pull for delivery
- The exact retry timing and backoff
- How preferences are stored and looked up
- The notification queueing mechanism

## Avoiding Premature Commitment

A common mistake is committing to details too early:

**Premature commitment:**
"The notification is stored in Cassandra with the user_id as partition key, then published to a Kafka topic, which triggers a consumer that calls the FCM API..."

**Why it's a problem:**
- You haven't validated that Cassandra, Kafka, or FCM are the right choices
- You're mixing requirements with design
- You're spending interview time on implementation details

**Better approach:**
"The notification needs to be stored durably and delivered in real-time. Let me first establish all the requirements, then I'll design the architecture to meet them. The choice of specific technologies will come from the requirements."

---

# Part 5: Handling Edge Cases Explicitly

## What Are Edge Cases?

Edge cases are scenarios that deviate from the typical flow. They include:

**Unusual inputs**: Empty values, maximum values, invalid formats
**Error conditions**: Network failures, service unavailable, timeout
**Boundary conditions**: First item, last item, exactly at limit
**Race conditions**: Concurrent updates, out-of-order events
**Exceptional users**: Power users, inactive users, new users

## Why Edge Cases Matter

Edge cases reveal the true complexity of a system. A design that only handles the happy path will fail in production.

But edge cases can also be a trap. Trying to enumerate every possible edge case leads to analysis paralysis and wasted time.

Staff engineers find the balance: they identify significant edge cases, decide how to handle them (fully, gracefully, or explicitly exclude), and move on.

## The Edge Case Triage

For each edge case, decide:

**Handle fully**: Design a complete solution
- Use for: Edge cases that happen frequently or have severe consequences

**Handle gracefully**: Provide degraded but acceptable behavior
- Use for: Edge cases that are rare but shouldn't crash the system

**Exclude explicitly**: State that this case is out of scope
- Use for: Edge cases that are very rare or would add disproportionate complexity

## Identifying Significant Edge Cases

Ask these questions:

**What if inputs are extreme?**
- Empty list, zero value, maximum allowed value
- Very long strings, very large numbers
- Malformed data, unexpected types

**What if things fail?**
- Downstream service unavailable
- Database write fails
- Network timeout
- Partial failure (some operations succeed, some fail)

**What if timing is unusual?**
- Request received twice
- Events arrive out of order
- Update during read
- Stale data

**What if users are unusual?**
- Brand new user (no history)
- Extremely active user (10x normal volume)
- User who hasn't been active in years
- User at the exact limit

## Edge Cases by System Type

### Messaging System

| Edge Case | How to Handle |
|-----------|---------------|
| Message to self | Handle fully (allow it) |
| Empty message | Handle fully (reject with error) |
| Very long message | Handle fully (enforce limit, provide error) |
| Message to non-existent user | Handle fully (reject with clear error) |
| Message while recipient is offline | Handle fully (queue for later delivery) |
| Recipient blocks sender after message sent | Handle gracefully (deliver, but block future) |
| Message contains malicious content | Handle gracefully (content moderation, flag) |
| Exactly at rate limit | Handle fully (reject cleanly) |
| Sender deletes account after sending | Exclude (message remains, sender shows as "deleted user") |

### Rate Limiter

| Edge Case | How to Handle |
|-----------|---------------|
| First request ever | Handle fully (initialize counter) |
| Exactly at limit | Handle fully (reject this request) |
| Request from unknown client | Handle fully (use default limits or reject) |
| Limit changed while request in flight | Handle gracefully (use old or new, document which) |
| Clock skew across servers | Handle gracefully (tolerate small drift, document bounds) |
| Distributed counter inconsistency | Handle gracefully (may slightly over/under limit) |
| Limit set to zero | Handle fully (reject all requests) |
| Negative limit configured | Exclude (prevent at configuration time) |

### Feed System

| Edge Case | How to Handle |
|-----------|---------------|
| New user with no follows | Handle fully (show recommendations/trending) |
| User follows 100,000 accounts | Handle gracefully (limit considered sources) |
| User hasn't opened app in 1 year | Handle gracefully (fall back to trending + recent) |
| Post deleted after loaded in feed | Handle gracefully (show placeholder or filter on scroll) |
| Simultaneous scroll and new content | Handle fully (merge without disruption) |
| All followed accounts inactive | Handle gracefully (show recommendations) |
| Content flagged during feed generation | Handle gracefully (filter, refresh on next load) |

## Articulating Edge Cases in Interviews

Be explicit about your edge case decisions:

"Let me address a few edge cases.

**Messages to offline users**: I'll handle this fully—messages are queued and delivered when the user comes online.

**Very long messages**: I'll enforce a character limit. If exceeded, the client shows an error before sending.

**Sender blocks recipient after message sent**: I'll handle this gracefully—the message is delivered, but future messages are blocked. This is simpler than trying to recall an in-flight message.

**Sender deletes account**: I'm excluding this—if a sender deletes their account, their messages remain but the sender shows as 'deleted user.'

Are there other edge cases you'd like me to address?"

---

# Part 6: In-Scope vs. Out-of-Scope Decisions

## The Purpose of Scope Boundaries

In an interview (and in real projects), you can't design everything. Scope boundaries define what you're responsible for and what you're not.

Clear scope boundaries:
- Focus your design effort
- Set expectations with the interviewer
- Prevent scope creep
- Enable integration assumptions

## Types of Scope Boundaries

### Functional Boundaries

What features are included vs. excluded:
- "I'm designing message delivery, not message search"
- "I'm designing notification sending, not notification content creation"
- "I'm designing the rate limiter, not the quota billing system"

### User Boundaries

Which users are served:
- "I'm designing for end consumers, not for admin users"
- "I'm designing for API clients, not for web UI"

### Scale Boundaries

What scale range is addressed:
- "I'm designing for 1-10 million users, not for 1 billion"
- "I'm designing for the initial launch, not for the 10-year vision"

### Integration Boundaries

What's assumed to exist vs. what's being built:
- "I'm assuming authentication exists; I'm not designing it"
- "I'm assuming we have a message queue; I'm not choosing which one"

## Making Scope Decisions

For each potential scope item, ask:

**Is this core to the problem?** If yes, it's in scope.

**Is this interesting or differentiating?** If yes, consider including it.

**Is this well-understood/standard?** If yes, consider excluding it.

**Does the interviewer seem interested?** If yes, include it.

**Do I have time?** If no, exclude it.

## Articulating Scope Clearly

Use explicit language:

**Positive scope (what's in):**
- "I will design..."
- "In scope for this design..."
- "I'm focusing on..."

**Negative scope (what's out):**
- "I'm explicitly not designing..."
- "Out of scope..."
- "I'm assuming this exists..."

**Scope rationale:**
- "I'm excluding [X] because it's a separate concern that's well-understood."
- "I'm including [Y] because that's where the interesting complexity is."

**Scope confirmation:**
- "Does this scope match what you had in mind?"
- "Should I include [X], or is my scope appropriate?"

## Example: Notification System Scope

"For this notification system, my scope is:

**In scope:**
- Accepting notification requests from internal services
- Storing notifications for later retrieval
- Delivering notifications via push and email
- Managing user preferences
- Basic delivery tracking

**Out of scope:**
- Creating notification content (done by calling services)
- Email and push infrastructure (using existing providers)
- Rich analytics (separate analytics system)
- A/B testing notification content (separate experimentation platform)
- Admin UI (assuming CLI/API for now)

**Assumptions:**
- Authentication/authorization is handled
- We have existing push (FCM/APNs) and email (SendGrid) integrations
- User data (names, emails, device tokens) is available from user service

Does this scope work?"

---

# Part 7: How Staff Engineers Avoid Feature Creep

## What Is Feature Creep?

Feature creep is the gradual expansion of scope beyond original boundaries. It happens when:
- You keep adding "just one more thing"
- You design for hypothetical future needs
- You can't say no to nice-to-have features
- You don't distinguish core from supporting functionality

## Why Feature Creep Is Dangerous

In interviews:
- You run out of time before covering the essentials
- Your design becomes shallow and spread thin
- You look unfocused and undisciplined

In real projects:
- Timelines slip
- Complexity increases
- Quality suffers
- The core product is delayed

## Staff-Level Discipline

Staff engineers avoid feature creep through:

### 1. Ruthless Prioritization

"I only have 45 minutes. What matters most?"

Rank everything: must-have, should-have, could-have, won't-have. Design only the must-haves in detail.

### 2. Explicit "Not Now" Lists

Instead of vaguely deferring things, explicitly list what's excluded:

"These features are valuable but out of scope for this design:
- Message search
- Message reactions  
- Read receipts

They can be added later without changing the core architecture."

### 3. Scope Checkpoints

Periodically reassess scope:

"I've been designing for 15 minutes. Let me check: am I still focused on core functionality? Have I drifted into supporting features?"

### 4. The "Do We Need This?" Question

For every feature, ask:
- "Do we need this for the system to work?"
- "Do we need this for the core use case?"
- "Would users accept V1 without this?"

If no, it's a candidate for exclusion.

### 5. Resisting the "While We're At It" Trap

"While we're building notifications, we could also add..."

This is where feature creep starts. The answer is usually: "We could, but we won't—let's stay focused."

## Feature Creep in Interviews

**Common pattern:**

Candidate is designing a messaging system. They cover:
- Message sending ✓
- Message delivery ✓
- Message history ✓

Then they keep going:
- "We should also add reactions..."
- "And read receipts..."
- "And typing indicators..."
- "And message search..."
- "And voice messages..."
- "And video calling..."

They run out of time having shallowly covered many features, with none designed well.

**Better pattern:**

"For core functionality, I'm focusing on sending, delivery, and history. Those are the must-haves for a messaging system.

Features like reactions, read receipts, and search are valuable but supporting. I'll note that the data model supports them, but I won't design them in detail.

Voice and video are out of scope—they're really a different system that could integrate with messaging.

Let me spend our time going deep on the core."

---

# Part 8: Functional Requirements for Common Systems

Let me provide detailed functional requirements for several common system design problems.

## Rate Limiter

### Core Functional Requirements

**F1: Rate Check**
- Given a client identifier and request details, determine if the request should be allowed
- Return allow/deny decision with remaining quota information

**F2: Rate Enforcement**
- When a request is allowed, record it against the client's quota
- When a request is denied, return appropriate error with retry-after information

**F3: Limit Configuration**
- Allow limits to be configured per client, per endpoint, or per client-endpoint combination
- Support different time windows (per second, per minute, per hour)

### Supporting Functional Requirements

**F4: Usage Query**
- Allow clients to check their current usage without making a request
- Allow operators to view usage across all clients

**F5: Manual Override**
- Allow operators to temporarily increase/decrease limits for specific clients
- Allow emergency block of specific clients

**F6: Limit Reset**
- Automatically reset usage counters at window boundaries
- Allow manual reset for specific clients

### Edge Cases Addressed

- Unknown client: Apply default limits
- Limit changed mid-window: New limit applies to new window
- Counter overflow: Reset counter (with logging)
- Distributed inconsistency: May allow slightly over limit (documented tolerance)

### Out of Scope

- Quota management (billing based on usage)
- Abuse detection beyond rate limiting
- Historical usage analytics

## Notification System

### Core Functional Requirements

**F1: Notification Ingestion**
- Accept notification requests from internal services
- Validate notification data (recipient, content, channel)
- Queue notifications for processing

**F2: Notification Delivery**
- Deliver notifications through specified channels (push, email, SMS)
- Handle delivery confirmations and failures
- Retry failed deliveries according to policy

**F3: User Preferences**
- Allow users to set notification preferences by type and channel
- Respect preferences when delivering notifications
- Allow users to mute specific sources

**F4: Notification Storage**
- Store notifications for later retrieval (inbox/history)
- Allow users to view, read, and dismiss notifications

### Supporting Functional Requirements

**F5: Notification Aggregation**
- Aggregate similar notifications ("5 people liked your post")
- Prevent notification spam to users

**F6: Delivery Tracking**
- Track delivery status (sent, delivered, read)
- Provide delivery metrics to sending services

**F7: Channel Fallback**
- If primary channel fails, attempt secondary channels
- Respect user preferences in fallback decisions

### Edge Cases Addressed

- Recipient offline: Queue and deliver when online (push), send immediately (email)
- Invalid recipient: Reject with error, notify sender
- Preference changed mid-delivery: Apply new preference to future notifications
- Very high volume (celebrity post): Rate limit fan-out, prioritize recent followers

### Out of Scope

- Notification content creation (done by sending services)
- Push/email infrastructure (external providers)
- Rich analytics and A/B testing

## Feed System

### Core Functional Requirements

**F1: Feed Generation**
- Generate a personalized feed for a logged-in user
- Include content from followed accounts
- Rank content by relevance and recency

**F2: Feed Rendering**
- Return feed content in paginated format
- Support efficient infinite scroll
- Handle mixed content types (posts, images, videos)

**F3: Feed Refresh**
- Detect new content since last load
- Allow user to refresh for new content
- Merge new content without disrupting position

### Supporting Functional Requirements

**F4: Feed Personalization**
- Apply user-specific ranking adjustments
- Learn from user interactions (likes, time spent)
- Support A/B testing of ranking algorithms

**F5: Feed Controls**
- Allow users to hide specific posts
- Allow users to mute specific accounts
- Allow users to snooze accounts temporarily

**F6: Content Injection**
- Inject ads into feed at appropriate intervals
- Inject recommendations for new accounts to follow

### Edge Cases Addressed

- New user (no follows): Show trending content and recommendations
- User follows 50,000 accounts: Limit content sources considered
- User inactive for 1 year: Fall back to trending + recent from top follows
- Content deleted after loaded: Show placeholder, filter on next load

### Out of Scope

- Content storage and creation (separate content service)
- Ad selection and targeting (separate ads platform)
- Detailed engagement analytics

## URL Shortener

### Core Functional Requirements

**F1: URL Creation**
- Accept a long URL and create a short URL
- Generate unique, unpredictable short keys
- Support optional custom short keys

**F2: URL Resolution**
- Given a short URL, return the corresponding long URL
- Support fast redirects (low latency)
- Handle expired or non-existent URLs gracefully

**F3: URL Management**
- Allow users to list their created URLs
- Allow users to delete/disable URLs
- Support URL expiration policies

### Supporting Functional Requirements

**F4: Click Analytics**
- Track click counts per URL
- Capture click metadata (time, referrer, geography)
- Provide analytics dashboard

**F5: Custom Domains**
- Support branded short domains
- Map custom domains to URL namespaces

### Edge Cases Addressed

- Collision in short key generation: Retry with new key
- URL already exists: Return existing short URL (optional deduplication)
- Malicious long URL: Check against blocklist, reject known malware
- Very long URL: Enforce reasonable limits (2048 characters)
- Expired URL: Return 404 with helpful message

### Out of Scope

- Marketing automation (email campaigns, etc.)
- QR code generation (separate utility)
- Deep linking for mobile apps

---

# Part 9: Phrasing Requirements in Interviews

## The Requirement Statement Pattern

A clear format for stating requirements:

**[User/System] can [action] [object] [optional: conditions/constraints]**

Examples:
- "Users can send text messages to other users"
- "Services can submit notifications with recipient, content, and channel"
- "Operators can configure rate limits per client, effective within 1 minute"

## Grouping Requirements

Organize requirements for clarity:

**By flow type:**
- "For read operations: ... For write operations: ... For control operations: ..."

**By user type:**
- "For end users: ... For internal services: ... For operators: ..."

**By priority:**
- "Core requirements: ... Supporting requirements: ... Nice-to-have: ..."

## Checking Completeness

After listing requirements, verify:

"Let me check completeness:
- Can users do all the things they need to do? [lists]
- Can services integrate as needed? [lists]
- Can operators manage the system? [lists]

Is there functionality I'm missing?"

## Confirming with the Interviewer

Always confirm your requirements:

"Based on my understanding, here are the functional requirements:
[lists requirements]

Does this capture what you had in mind? Is there anything you'd like me to add or remove?"

## Example: Complete Requirements Statement

"For the notification system, here are the functional requirements:

**Core (must design in detail):**
1. Services can submit notifications with recipient, content, and channel
2. System delivers notifications to users in near-real-time
3. System respects user preferences when delivering
4. Users can view their notification history
5. Users can manage their notification preferences

**Supporting (will acknowledge in design):**
6. System aggregates similar notifications
7. System tracks delivery status
8. System falls back to alternative channels on failure

**Out of scope:**
- Notification content creation
- Push/email infrastructure
- Rich analytics

Does this scope align with your expectations?"

---

# Part 10: Common Pitfalls and How to Avoid Them

## Pitfall 1: Requirements Too Vague

**The problem:**
"System handles notifications" doesn't tell you what the system actually does.

**Why it happens:**
Candidates want to move quickly to architecture. They assume requirements are "obvious."

**How to avoid:**
Force yourself to be specific. Use the pattern: "[User] can [action] [object]." If you can't fill in the blanks, you're not specific enough.

**Example:**
- ❌ "System handles messages"
- ✅ "Users can send text messages to other users, who receive them in real-time"

## Pitfall 2: Requirements Include Implementation

**The problem:**
"Messages are stored in Cassandra and delivered via Kafka" is implementation, not requirements.

**Why it happens:**
Experienced engineers naturally jump to solutions. They conflate what with how.

**How to avoid:**
Ask yourself: "Am I describing observable behavior, or internal mechanism?" Requirements describe behavior; implementation describes mechanism.

**Example:**
- ❌ "Messages are published to Kafka for async delivery"
- ✅ "Messages are delivered asynchronously with at-least-once guarantee"

## Pitfall 3: No Prioritization

**The problem:**
Listing 15 requirements with no distinction between essential and nice-to-have.

**Why it happens:**
Candidates don't want to "miss" anything. Prioritization feels like excluding things.

**How to avoid:**
Explicitly categorize: core, supporting, out-of-scope. Announce what you're optimizing for.

**Example:**
- ❌ "The system should send notifications, track delivery, aggregate similar ones, support A/B testing, provide analytics..."
- ✅ "Core: send and deliver notifications. Supporting: aggregation and tracking. Out of scope: A/B testing and analytics."

## Pitfall 4: Missing Edge Cases

**The problem:**
Only describing the happy path. "Users send messages" but what about failures, limits, invalid inputs?

**Why it happens:**
Happy path is the obvious case. Edge cases require more thought.

**How to avoid:**
Systematically ask: "What if input is invalid? What if something fails? What about boundaries?"

**Example:**
- ❌ "Users can send messages to other users"
- ✅ "Users can send messages to other users. If the recipient doesn't exist, return error. If message exceeds length limit, reject. If delivery fails, retry 3 times."

## Pitfall 5: Scope Creep

**The problem:**
Starting with 3 requirements and ending with 15 as you keep adding "one more thing."

**Why it happens:**
Each addition seems small. "While we're at it" thinking.

**How to avoid:**
Set scope explicitly at the start. Use a "not now" list for things you think of later. Periodically check if you've drifted.

**Example:**
- ❌ [Keeps adding features throughout the interview]
- ✅ "I defined 5 core requirements at the start. I've thought of 3 more nice-to-haves—I'll note them but not design them."

## Pitfall 6: Not Confirming with Interviewer

**The problem:**
Assuming your understanding is correct without checking.

**Why it happens:**
Candidates want to seem confident. Checking feels like uncertainty.

**How to avoid:**
Confirmation is not weakness; it's collaboration. Always check: "Does this capture what you had in mind?"

**Example:**
- ❌ [States requirements and immediately moves to design]
- ✅ "Here are my requirements. Does this match your expectations? Should I adjust the scope?"

## Pitfall 7: Requirements Don't Enable Use Cases

**The problem:**
Your requirements don't actually support the use cases you identified.

**Why it happens:**
Requirements and use cases were defined separately without checking alignment.

**How to avoid:**
After defining requirements, trace each use case: "Can a user accomplish [use case] with these requirements?"

**Example:**
- Use case: "User views conversation history"
- Required functionality: "System stores messages and allows retrieval by conversation"
- Check: ✅ Use case is enabled by requirements

## Pitfall 8: Ignoring Control/Admin Flows

**The problem:**
Focusing entirely on user-facing functionality, forgetting about system management.

**Why it happens:**
User flows are more interesting. Admin flows seem boring.

**How to avoid:**
Explicitly enumerate control flows: "What operations do administrators need? What configuration is required?"

**Example:**
- ❌ [Only describes user sending/receiving messages]
- ✅ "Users send and receive messages. Operators can configure message retention, view delivery metrics, and block abusive users."

---

# Brainstorming Questions

## Understanding Requirements

1. For a system you've built, can you list 5 core and 5 supporting functional requirements? What made them core vs. supporting?

2. Think of a project where requirements were unclear. How did that affect the design? What would clearer requirements have changed?

3. When have you seen a system fail because edge cases weren't considered? What was missed?

4. How do you distinguish functional requirements from non-functional requirements? Where's the line?

5. Take a feature you've built. What was the observable behavior (functional) vs. the quality targets (non-functional)?

## Scope and Prioritization

6. When have you successfully cut scope on a project? What enabled you to do that?

7. When have you experienced feature creep? What caused it and how could it have been prevented?

8. How do you decide what's in V1 vs. V2? What's your mental model?

9. Think of a system with too many features. Which would you remove to simplify it?

10. How do you say "no" to stakeholders who want more features?

## Flow Analysis

11. Take a familiar system. What are its read, write, and control flows? Is the balance what you'd expect?

12. Which flow type is typically the bottleneck: read, write, or control? Why?

13. For a system you know, what's the ratio of reads to writes? How does that affect the design?

14. What control flows do people often forget to design? Why are they overlooked?

15. How do you ensure control flows are secure? What's the threat model?

---

# Homework Exercises

## Exercise 1: Requirements Specification

Take three system prompts:
1. "Design a rate limiter"
2. "Design a notification system"
3. "Design a URL shortener"

For each, write:
- 5 core functional requirements
- 3 supporting functional requirements
- 3 explicit exclusions (out of scope)
- 3 edge cases and how to handle them

Use the format: "[User/System] can [action] [object] [constraints]"

## Exercise 2: Core vs. Supporting Analysis

Take a product you use daily (e.g., Slack, Uber, Instagram).

List 10 features. For each, classify as:
- Core: Product is useless without it
- Supporting: Enhances but not essential
- Nice-to-have: Could remove without much impact

Now imagine you're building V1 with 50% of the features. Which 5 do you build?

## Exercise 3: Flow Enumeration

Pick a system (or use: Stripe, Dropbox, Spotify).

Enumerate all the flows you can identify:
- At least 5 read flows
- At least 5 write flows
- At least 3 control flows

For each flow, note:
- Who initiates it
- What data is involved
- What the expected outcome is

## Exercise 4: Edge Case Catalog

For a messaging system, enumerate edge cases across these categories:
- Invalid inputs (at least 5)
- Failure conditions (at least 5)
- Boundary conditions (at least 3)
- Timing/concurrency issues (at least 3)

For each, decide: handle fully, handle gracefully, or exclude?

## Exercise 5: Scope Negotiation

Practice scope negotiation with a partner.

Partner gives you an intentionally broad prompt:
"Design a complete social media platform."

Your task: negotiate it down to something designable in 45 minutes.

Practice:
- Asking clarifying questions to narrow scope
- Proposing boundaries and getting agreement
- Explicitly listing exclusions
- Confirming the scope before designing

## Exercise 6: Requirements-to-Use-Case Mapping

Take your requirements from Exercise 1.

For each use case you identified in Phase 1 (users & use cases), trace:
- Which requirements enable this use case?
- Are any use cases unsupported by requirements?
- Are any requirements not linked to use cases?

This validates that your requirements and use cases are aligned.

---

# Conclusion

Functional requirements are the bridge between understanding your users (Phase 1) and designing your system (later phases). They define what you're building.

Staff-level precision in functional requirements means:

**Being specific enough** to drive design decisions—not vague hand-waving like "system handles messages"

**Being abstract enough** to avoid implementation details—not premature commitment to technologies

**Distinguishing core from supporting**—knowing what's essential vs. what's nice-to-have

**Covering all flow types**—read, write, and control, not just the obvious user flows

**Handling edge cases explicitly**—not just the happy path

**Managing scope actively**—saying no to feature creep, being explicit about exclusions

**Confirming alignment**—checking with the interviewer that your requirements match their expectations

The functional requirements you define in this phase become the contract for your design. Every architectural decision should trace back to a requirement. If you find yourself designing something that isn't required, question whether you need it.

Get the requirements right, and the design becomes clearer. Get them wrong, and you'll build the wrong system—no matter how elegant your architecture.

Take the time to be precise. It's a Staff-level habit.

---

*End of Volume 2, Section 3*

# System Design Interview Preparation for Google Staff Engineer (L6)

## Volume 2, Section 4: Phase 3 — Scale: Capacity Planning and Growth at Staff Level

---

# Introduction

Scale changes everything.

A system serving 1,000 users can run on a single server with a simple database. A system serving 100 million users requires distributed infrastructure, careful capacity planning, and fundamentally different architectural decisions. The same functional requirements lead to completely different designs depending on scale.

This is why Phase 3—Scale—is where Staff engineers spend significant time. Before you can design an architecture, you need to know how big the problem is. Before you can choose technologies, you need to understand the load they'll face. Before you can make trade-offs, you need to quantify what you're trading.

In this section, we'll cover how to think about scale at Staff level. We'll explore the key metrics you need to understand, how to translate vague prompts into concrete numbers, how to reason about growth, and how to identify the patterns—like fan-out and hot keys—that make scale challenging. By the end, you'll approach scale estimation with confidence and precision.

---

# Part 1: Why Scale Is a First-Class Concern at Staff Level

## Scale Determines Architecture

The most fundamental truth in system design: **scale determines architecture**.

At small scale, almost anything works. You can use a monolith, a single database, synchronous processing. Simplicity is a virtue because the overhead of distributed systems isn't justified.

At large scale, you have no choice but to distribute. A single database can't handle a million writes per second. A single server can't maintain 10 million concurrent connections. The laws of physics and the limits of hardware force you into distributed systems.

The transition points—where simple solutions break and complex solutions become necessary—are driven by scale. Knowing where you are relative to these points is essential for making appropriate design choices.

## Scale Reveals Hidden Complexity

Systems that work perfectly at small scale often fail in surprising ways at large scale:

- A database query that takes 10ms becomes a bottleneck when executed 10,000 times per second
- A fan-out that's negligible with 100 followers becomes catastrophic with 10 million followers
- An algorithm that's linear in complexity becomes unusable when N grows by 1000x
- A hot key that's invisible at low load causes cascading failures at high load

Staff engineers anticipate these failure modes. They don't just ask "Will this work?" They ask "Will this work at our expected scale? What about 10x that scale?"

## Scale Affects Cost

Every unit of scale costs money:

- More users = more servers
- More data = more storage
- More requests = more bandwidth
- More complexity = more engineering time

Staff engineers think about cost efficiency at scale. A 10% inefficiency is negligible at 1,000 users but costs millions of dollars at 100 million users. The design decisions you make at the whiteboard translate directly to infrastructure bills.

## Interviewers Test Scale Thinking

In Staff-level interviews, interviewers probe your scale awareness:

- Do you ask about scale before designing?
- Can you translate user numbers into technical metrics?
- Do you recognize when scale changes design choices?
- Can you estimate capacity with reasonable accuracy?
- Do you anticipate scale-related failure modes?

A candidate who designs without establishing scale is showing Senior-level (or below) behavior. A candidate who uses scale to drive every design decision is showing Staff-level thinking.

---

# Part 2: Translating Vague Scale into Concrete Numbers

## The Problem with Vague Scale

Interviewers often provide vague scale hints:

- "Design for a large social network"
- "Assume this is for a major e-commerce platform"
- "Think about Netflix-scale"
- "This should work for millions of users"

These hints are deliberately imprecise. The interviewer wants to see if you can translate vagueness into specificity.

## The Translation Process

Staff engineers translate vague scale into concrete metrics through a systematic process:

### Step 1: Anchor on Users

Start with the user count. This is usually the most grounded number:

- "For a large social network, I'm thinking 500 million monthly active users, 200 million daily active users. Does that match your expectations?"

If the interviewer hasn't given a hint, propose a range:

- "Let me assume we're designing for a significant scale—say 10 million daily active users. I can adjust if you have a different scale in mind."

### Step 2: Derive Activity Metrics

From users, derive activity:

- Average actions per user per day
- Average sessions per day
- Average session length
- Average content consumed/produced per session

"With 200 million DAU, if the average user opens the app 5 times per day and views 20 items per session, that's:
200M × 5 × 20 = 20 billion item views per day"

### Step 3: Convert to Requests

Activity translates to system requests:

- Each item view might require 1-3 API calls
- Each action (like, comment) might require 1-2 API calls
- Background sync might add additional requests

"20 billion item views, let's say 1.5 API calls each = 30 billion API calls per day"

### Step 4: Calculate Rates

Daily totals become per-second rates:

- 30 billion requests per day
- 30B / 86,400 seconds = ~350,000 requests per second average

### Step 5: Account for Peaks

Average is not peak. Systems must handle peak load:

- Peak is typically 2-10x average depending on usage patterns
- Events (sports, news, product launches) can cause spikes

"350K average RPS, but peak during prime time might be 3x, so ~1 million RPS. And during major events, we might see 2-3x peak, so design for 2-3 million RPS burst capacity."

## When Numbers Aren't Given

If the interviewer provides no scale hints, you have two options:

### Option A: Ask Directly

"Before I design, I need to understand scale. How many users are we designing for? Is this a startup MVP or a major platform?"

### Option B: Propose and Confirm

"Let me establish some scale assumptions. I'll design for:
- 50 million daily active users
- 500 requests per second per million users = 25,000 RPS average
- 100,000 RPS peak

If the scale is significantly different, some architectural choices might change. Does this order of magnitude work?"

---

# Part 3: Key Scale Metrics

## DAU and MAU

**DAU (Daily Active Users)**: Unique users who engage with the product each day.

**MAU (Monthly Active Users)**: Unique users who engage at least once per month.

**DAU/MAU Ratio**: Indicates engagement stickiness.
- 10-20%: Low engagement (occasional use apps)
- 30-50%: Moderate engagement (social media, news)
- 50%+: High engagement (messaging, essential tools)

**Why they matter**:
- DAU determines daily load
- MAU determines total data scale (profiles, history)
- DAU/MAU affects caching strategies (active user data is hot)

**Example calculation**:
- MAU: 100 million
- DAU: 30 million (30% DAU/MAU ratio)
- Data for 100M users, but daily load from 30M

## QPS (Queries Per Second)

**QPS**: The number of requests your system handles each second.

**Variants**:
- Read QPS vs Write QPS
- Average QPS vs Peak QPS
- External QPS vs Internal QPS (microservices amplify)

**Calculating QPS**:
```
QPS = (DAU × actions_per_user_per_day) / seconds_per_day
    = (DAU × actions_per_user_per_day) / 86,400
```

**Example**:
- 30 million DAU
- 100 actions per user per day
- QPS = 30M × 100 / 86,400 = ~35,000 QPS average

**Peak multiplier**:
- Apply 2-5x for peak hours
- Apply additional 2-3x for special events
- Peak QPS = 35K × 3 = 105K, event peak = 300K

## Throughput and Bandwidth

**Throughput**: Data volume processed per unit time (bytes/second, records/second).

**Bandwidth**: Network capacity (bits/second or bytes/second).

**Calculating data throughput**:
```
Throughput = QPS × average_payload_size
```

**Example**:
- 35,000 QPS
- Average response size: 5 KB
- Throughput = 35K × 5 KB = 175 MB/second = 1.4 Gbps

**Why it matters**:
- Network capacity planning
- Database I/O sizing
- Cache sizing
- CDN capacity

## Storage

**Types of storage**:
- Hot storage: Frequently accessed, fast (SSD, in-memory)
- Warm storage: Occasional access (regular disk)
- Cold storage: Archive, rarely accessed (object storage)

**Calculating storage**:
```
Total storage = number_of_items × average_item_size × retention_period_factor
```

**Example for messages**:
- 1 billion messages per day
- Average message size: 500 bytes
- Keep 1 year of history
- Storage = 1B × 500 bytes × 365 = 182 TB

**Growth considerations**:
- Data compounds over time
- 182 TB year 1, 364 TB year 2, 546 TB year 3
- Plan for 3-5 years of growth

---

# Part 4: Peak vs. Average Load

## Why Peak Matters

Systems don't fail at average load—they fail at peak load. Designing for average leaves you vulnerable when usage spikes.

**The peak/average ratio** varies by use case:

| System Type | Typical Peak/Average Ratio |
|-------------|---------------------------|
| Messaging apps | 2-3x |
| Social feeds | 3-5x |
| E-commerce | 5-10x (sales, holidays) |
| Streaming video | 3-4x (primetime) |
| Sports/news | 10-50x (events) |

## Understanding Peak Patterns

### Daily Patterns

Most consumer applications follow daily patterns:
- Low: 3 AM - 6 AM local time
- Ramp: 6 AM - 9 AM
- Moderate: 9 AM - 6 PM
- Peak: 6 PM - 11 PM
- Decline: 11 PM - 3 AM

**Global systems** see smoother curves because time zones overlap, but still have patterns.

### Weekly Patterns

- Weekday vs. weekend differences
- Friday/Saturday evenings often highest
- Monday mornings can spike (catch-up behavior)

### Event-Driven Spikes

Unpredictable but significant:
- Breaking news
- Celebrity activity
- Product launches
- Sports events (Super Bowl, World Cup final)
- System failures elsewhere (users flood alternatives)

## Designing for Peak

### Option 1: Provision for Peak

Size your system for maximum expected load.

**Pros**: Always available, simple operations
**Cons**: Expensive, wasted capacity at low load

### Option 2: Auto-Scaling

Dynamically add/remove capacity based on load.

**Pros**: Cost-efficient, handles variability
**Cons**: Scale-up latency, complexity, may not handle sudden spikes

### Option 3: Graceful Degradation

Accept that extreme peaks may receive degraded service.

**Pros**: Practical for extreme events
**Cons**: User experience impact, requires careful design

### Hybrid Approach (Most Common)

- Provision baseline capacity (maybe 2x average)
- Auto-scale for normal peaks (up to 5x average)
- Graceful degradation for extreme events (beyond 5x)

## Articulating Peak in Interviews

"The average load is 50,000 QPS. Peak during primetime is 3x, so 150,000 QPS. During major events—a celebrity announcement or breaking news—we might see 10x average, so 500,000 QPS.

I'll design the system to auto-scale from 50K to 200K smoothly. Beyond that, we'll have graceful degradation: non-critical features (like recommendations) might be disabled, but core functionality (posting, viewing) remains available."

---

# Part 5: Read vs. Write Ratios

## Why the Ratio Matters

Most systems have asymmetric read/write patterns. Understanding this ratio drives fundamental architecture decisions.

**Read-heavy systems** (read/write >> 1):
- Can benefit heavily from caching
- Can use read replicas
- Eventually consistent often acceptable
- Examples: Social feeds, e-commerce product pages, news sites

**Write-heavy systems** (read/write ≈ 1 or < 1):
- Caching provides limited benefit
- Write scaling is the challenge
- Need fast, efficient write path
- Examples: Logging, metrics, IoT data ingestion

**Balanced systems** (read/write ≈ 1-10):
- Need balanced optimization
- Can't ignore either path
- Examples: Messaging, collaborative documents

## Typical Ratios by System Type

| System | Typical Read:Write Ratio |
|--------|--------------------------|
| Social feed | 100:1 to 1000:1 |
| E-commerce catalog | 100:1 to 10,000:1 |
| URL shortener | 100:1 to 1000:1 |
| Messaging | 1:1 to 10:1 |
| Metrics/logging | 1:10 to 1:100 (write-heavy) |
| Collaborative docs | 5:1 to 20:1 |
| User profiles | 50:1 to 500:1 |

## Deriving the Ratio

Calculate from user behavior:

**Example: Social Feed**
- User opens feed: 1 read
- User scrolls: 5-20 more reads
- User posts: Rare (maybe 0.1 posts per session)
- User likes: Maybe 2 per session

Per session: ~15 reads, 2 writes → 7.5:1

But likes affect many users' feeds (fan-out), while reads are singular.

Actual system ratio: Very read-heavy on the database, but write fan-out means significant write processing.

## Impact on Architecture

### For Read-Heavy (100:1+)

- **Caching is essential**: Cache aggressively; cache hits avoid database load
- **Read replicas**: Distribute read load across replicas
- **CDN for static content**: Push content to the edge
- **Precomputation**: Compute results ahead of time
- **Eventually consistent is often fine**: Stale data acceptable for seconds

### For Write-Heavy (1:1 or below)

- **Write optimization is critical**: Fast write path, minimal overhead
- **Append-only designs**: Write ahead, process later
- **Partitioning/sharding**: Distribute writes across nodes
- **Asynchronous processing**: Accept writes quickly, process in background
- **Batching**: Group small writes into larger operations

### For Balanced (10:1)

- **Can't ignore either path**: Need reasonable read and write performance
- **Careful cache invalidation**: Writes must invalidate/update caches correctly
- **Trade-off awareness**: Improving one path might hurt the other

## Articulating in Interviews

"Let me think about the read/write ratio. For a social feed:
- Every time a user opens the app, they read the feed
- They might scroll through 20-30 items
- Occasionally they like or comment—maybe 2-3 times per session
- Rarely they post—maybe once per day if active

This is heavily read-biased—probably 100:1 or more for the feed reads. This tells me caching is essential, read replicas make sense, and eventual consistency is acceptable for the feed. The write path is less frequent but has fan-out implications—when someone posts, it affects many feeds."

---

# Part 6: Fan-Out and Amplification Effects

## What Is Fan-Out?

**Fan-out** occurs when a single action triggers multiple subsequent actions or operations.

**Examples**:
- One post → notify 1000 followers
- One message to group → deliver to 500 members
- One API call → 10 internal service calls
- One database write → updates 50 cache entries

## Why Fan-Out Is Critical

Fan-out multiplies load. What looks like a reasonable operation at the source becomes massive at the destination.

**The math**:
- 1,000 posts per second
- Average 1,000 followers per poster
- Fan-out: 1,000 × 1,000 = 1,000,000 notifications per second

Your "1,000 posts per second" system actually needs to handle a million notifications per second.

## Types of Fan-Out

### Write-Time Fan-Out (Push Model)

When content is created, immediately push to all destinations.

**Pros**:
- Fast reads (data already at destination)
- Simple read path

**Cons**:
- Slow writes (must complete fan-out)
- High storage (duplicated data)
- Wasted work if content never read

**Good for**:
- Users with small follower counts
- Time-sensitive notifications
- Systems with high read/write ratios

### Read-Time Fan-Out (Pull Model)

When content is requested, pull from all sources.

**Pros**:
- Fast writes (minimal work at write time)
- Storage efficient
- No wasted work

**Cons**:
- Slow reads (must aggregate at read time)
- Complex read path
- Repeated work if content read multiple times

**Good for**:
- Users with large follower counts (celebrities)
- Content with uncertain readership
- Systems with lower read/write ratios

### Hybrid Fan-Out

Combine approaches based on characteristics:
- Push for "normal" users (< 10K followers)
- Pull for celebrities (> 10K followers)

This is what Twitter, Facebook, and other major social platforms do.

## Calculating Fan-Out Impact

**Example: Feed system**

Setup:
- 1,000 posts per second
- Users have average 500 followers
- Celebrity accounts (1%) have 5 million followers

Without special handling:
- Regular users: 990 posts × 500 = 495,000 fan-out operations
- Celebrities: 10 posts × 5,000,000 = 50,000,000 fan-out operations

Celebrities (1% of posts) cause 99% of fan-out load!

**Solution**:
- Push for regular users: 495K/second (manageable)
- Pull for celebrities at read time
- Total managed load vs. 50M/second chaos

## Microservice Amplification

In microservice architectures, a single external request often triggers many internal requests:

**Example**:
- 1 feed request → 10 content service calls → 50 user service calls → 5 recommendation calls
- Amplification factor: 65x

**Implications**:
- Internal systems must handle much higher load than external
- Internal latency adds up
- Internal failures can cascade

**Articulating in interviews**:

"I need to consider fan-out. When a user posts, that post needs to appear in all followers' feeds. The average user has 500 followers, so our 1,000 posts/second becomes 500,000 feed updates/second.

But we have celebrity accounts with millions of followers. Pushing to them at write time would be catastrophic—10 million operations for one post. For these accounts, I'll use a pull model: we store the post once and pull it into feeds at read time. The trade-off is slightly slower feed load for users who follow celebrities, but that's acceptable given the alternative."

---

# Part 7: Hot Keys and Skew

## What Are Hot Keys?

**Hot keys** are specific keys (user IDs, product IDs, etc.) that receive disproportionate traffic. They create load imbalance and can overwhelm individual nodes.

**Examples**:
- Celebrity user posting (millions rush to see)
- Viral product (everyone checking the same product page)
- Breaking news article
- Popular hashtag
- Default or example values in systems

## Why Hot Keys Are Dangerous

Distributed systems spread load by partitioning data:

| Partition | Normal Load | With Hot Key |
|-----------|-------------|--------------|
| Partition A | 10,000 QPS | 10,000 QPS |
| Partition B | 10,000 QPS | 500,000 QPS ← Hot key here |
| Partition C | 10,000 QPS | 10,000 QPS |
| Partition D | 10,000 QPS | 10,000 QPS |

Total capacity: 200,000 QPS
Actual capacity limited by Partition B: ~500,000 QPS or failure

A single hot key can bring down a partition, causing cascading failures.

## Types of Skew

### Temporal Skew

Load concentrated in time periods:
- Flash sales
- Event starts (concert tickets on sale)
- Time-zone-aligned activity

### Key Skew

Load concentrated on specific keys:
- Celebrity accounts
- Popular content
- Viral items

### Partition Skew

Uneven data/load distribution across partitions:
- Poor partition key choice
- Natural data distribution (power law)

## Handling Hot Keys

### Strategy 1: Caching

For read-heavy hot keys, cache aggressively:

- Cache at multiple levels (CDN, application cache, database cache)
- Use short TTLs to balance freshness and load reduction
- Pre-warm caches for predictable hot keys

**Example**: Celebrity profile → cached at CDN, 1-minute TTL, serves 99% of requests

### Strategy 2: Replication

Replicate hot data across multiple nodes:

- Read replicas for read-heavy hot keys
- Multiple copies of hot partition
- Route requests across replicas

### Strategy 3: Splitting

Split hot keys into multiple virtual keys:

- user_123 becomes user_123_0, user_123_1, user_123_2
- Distribute across partitions
- Aggregate at read time

**Example**: Celebrity follower list split into 100 shards. Writes distribute. Reads aggregate.

### Strategy 4: Rate Limiting

Accept that hot keys can only be served so fast:

- Rate limit requests to hot keys
- Queue excess requests
- Return cached/stale data for overflow

### Strategy 5: Separate Infrastructure

Route hot keys to dedicated infrastructure:

- Separate cluster for celebrities
- Dedicated cache layer for popular products
- Specialized handling for known hot spots

## Anticipating Hot Keys

In an interview, proactively address hot keys:

"I need to think about hot keys. In a social platform, celebrity accounts are hot keys—one user might have 50 million followers, all trying to see their latest post.

My partitioning strategy puts user data on specific shards. A celebrity's data on one shard would overwhelm it.

I'll handle this three ways:
1. Heavy caching: Celebrity content cached at CDN with 10-second TTL
2. Read replicas: Hot user profiles replicated to multiple read nodes
3. Follower list sharding: Large follower lists split across multiple partitions

For celebrities with over 1 million followers, I'll use the pull model for feed updates rather than push, which avoids the fan-out hot key problem entirely."

---

# Part 8: Short-Term vs. Long-Term Growth Planning

## The Growth Planning Dilemma

You can't design for current scale and ignore growth—you'll constantly be rebuilding. But you also can't design for 100x scale day one—you'll waste time and money on complexity you don't need.

Staff engineers find the balance: design for reasonable growth, with a migration path to higher scale.

## Time Horizons

### Immediate (Launch - 6 months)

- Design for current expected scale
- Include some headroom (2x)
- Focus on shipping and learning

### Near-term (6 months - 2 years)

- Plan for 5-10x growth
- Architecture should handle without major redesign
- May need to add capacity, optimize, tune

### Medium-term (2-5 years)

- Consider 10-50x growth
- Major architectural decisions should support this
- Accept that some components may need redesign

### Long-term (5+ years)

- Plan for 100x+ only if business trajectory supports it
- Focus on extensibility, not specific solutions
- Accept significant uncertainty

## Growth-Aware Architecture

### Design Principles

**Horizontal scaling**: Prefer architectures that scale by adding nodes, not by upgrading nodes.

**Stateless services**: Stateless components scale easily; state should be in dedicated stores.

**Partition-ready data**: Choose partition keys that will work at 10x scale.

**Replaceable components**: Don't couple tightly to specific technologies.

### Migration Paths

For each component, know the migration path:

| Scale | Database Approach | Migration Path |
|-------|-------------------|----------------|
| 10K users | Single PostgreSQL | Add read replicas |
| 100K users | PostgreSQL + replicas | Shard hot tables |
| 1M users | Sharded PostgreSQL | Consider specialized stores |
| 10M users | Distributed database | Evaluate Spanner/CockroachDB |

### Scale Indicators

Know what metrics signal it's time to evolve:

- Database CPU consistently > 70%
- P99 latency degrading
- Storage capacity > 60%
- Write queue growing
- Hot keys emerging

## Articulating Growth in Interviews

"Let me think about growth. We're launching with 1 million users, expecting to grow to 10 million in a year.

For V1, I'll use a single primary database with read replicas. That handles our launch scale with room to grow.

At 5 million users, we'll likely need to shard the messages table—I'll choose user_id as the partition key now so the schema supports this.

At 10+ million users, we might need a distributed database like Spanner for strong consistency at scale, or accept eventual consistency with a sharded MySQL setup.

The key is: my initial design supports 10x growth with operational changes (adding capacity). Beyond 10x requires architectural evolution, which is expected."

---

# Part 9: Step-by-Step Scale Estimation Examples

Let me walk through complete scale estimations for common systems.

## Example 1: URL Shortener

### Given Information
"Design a URL shortener for a major tech company, similar to bit.ly."

### Step 1: Establish User Scale
- Assume 100 million monthly active users
- 10 million daily active users (10% DAU/MAU ratio—utility service)
- Most users only create URLs occasionally

### Step 2: Calculate Operations

**URL Creation (Writes)**:
- Average user creates 1 URL per month
- 100M URLs created per month
- 100M / 30 days / 86,400 seconds = ~40 URL creations per second
- Peak (3x): ~120 creations per second

**URL Resolution (Reads)**:
- Each URL clicked average 100 times over lifetime
- 100M URLs × 100 clicks = 10 billion clicks per month
- 10B / 30 / 86,400 = ~4,000 clicks per second
- Peak (5x): ~20,000 clicks per second

**Read:Write Ratio**: 4,000:40 = 100:1 (heavily read-biased)

### Step 3: Calculate Storage

**URL Storage**:
- 100M new URLs per month
- Average long URL: 200 bytes
- Average short key: 7 bytes
- Metadata: 100 bytes
- Per URL: ~300 bytes
- Monthly: 100M × 300 = 30 GB
- Yearly: 360 GB
- 5 years with growth: ~2-3 TB

**Click Analytics** (if included):
- 10B clicks per month
- 100 bytes per click event
- Monthly: 1 TB
- Much larger than URL storage

### Step 4: Design Implications

- Read-heavy → caching is critical
- URL resolution must be fast (<50ms)
- Can use read replicas extensively
- Creation latency less critical (can be 200-500ms)
- Storage is modest for URLs, large for analytics

### Summary Statement

"For this URL shortener:
- ~40 creates/second, ~4,000 resolves/second average
- Peak: 120 creates/second, 20,000 resolves/second
- 100:1 read:write ratio
- ~2 TB storage for URLs over 5 years
- Caching is essential; resolution path is the priority"

## Example 2: Notification System

### Given Information
"Design a notification system for a social media platform with 200 million DAU."

### Step 1: Establish Scale
- 200 million DAU
- 500 million MAU
- Global platform, 24/7 activity

### Step 2: Calculate Notification Volume

**Notification Generation**:
- Average user generates 5 notifications/day (likes, comments, follows)
- But receives 20 notifications/day (from others' actions)
- Total notifications: 200M × 20 = 4 billion notifications/day
- Per second: 4B / 86,400 = ~46,000 notifications/second
- Peak (3x): ~140,000 notifications/second

**Delivery Operations**:
- Each notification → 1 push delivery attempt
- Each notification → possibly email, SMS
- Average 1.5 deliveries per notification
- 46K × 1.5 = ~70,000 delivery operations/second

### Step 3: Consider Fan-Out

**Celebrity Problem**:
- 1% of users have 100K+ followers
- A celebrity post generates: 1 post → 100K+ notifications
- 200M × 1% = 2M celebrities
- If each posts once/day: 2M × 100K = 200 billion extra notifications

This is infeasible with push. Must use pull model for celebrities.

**Revised with hybrid**:
- Regular users (99%): Push notifications
- Celebrities (1%): Pull at read time
- Manageable: ~46K/second push + pull aggregation

### Step 4: Calculate Storage

**Notification Storage**:
- 4B notifications/day
- Keep 30 days of history
- 120B notifications
- 500 bytes per notification
- Storage: 60 TB
- With celebrity posts stored once (not fanned out): ~10 TB

### Step 5: Design Implications

- High throughput system
- Fan-out is the key challenge
- Hybrid push/pull for celebrities
- Need efficient per-user storage
- Delivery reliability matters (retry logic)

### Summary Statement

"For this notification system:
- 46K notifications/second generated, 140K/second peak
- 70K delivery operations/second average
- Must handle celebrity fan-out with hybrid push/pull
- ~10-60 TB storage for 30-day history
- Delivery latency target: <5 seconds
- Critical path: ingestion → processing → delivery"

## Example 3: Rate Limiter

### Given Information
"Design a rate limiter for an API gateway handling 1 million requests per second."

### Step 1: Understand the Load
- 1 million RPS to the API gateway
- Every request needs rate limit check
- Rate limit check must be extremely fast

### Step 2: Calculate Rate Limiter Load

**Check Operations**:
- 1M checks per second (same as API RPS)
- Each check: lookup client, check counter, maybe increment
- Latency budget: <1ms (to not significantly impact API latency)

**Counter Updates**:
- 1M increments per second
- Distributed across clients (maybe 100K active clients)
- Average 10 RPS per client
- But some clients much higher (power users, scrapers)

### Step 3: Identify Hot Keys

**Client Distribution**:
- Likely power-law: top 1% of clients = 50% of traffic
- Top 1% of 100K = 1K clients causing 500K RPS
- Average: 500 RPS per power client

**Hot Client Risk**:
- A single scrapy client might send 10K+ RPS
- That's 10K increments/second on one counter
- Potential hot key

### Step 4: Calculate Storage

**Counter Storage**:
- 100K active clients
- Per client: client_id (16 bytes) + counter (8 bytes) + window (8 bytes)
- Per client: ~32 bytes
- Total: 3.2 MB
- Trivially fits in memory

**Configuration Storage**:
- Rate limit rules
- Client-specific overrides
- Small: < 1 MB

### Step 5: Design Implications

- Ultra-low latency required (<1ms)
- Must be distributed (single node can't handle 1M/s)
- In-memory storage (Redis or custom)
- Hot key handling for power clients
- Eventual consistency acceptable (slightly over limit OK)

### Summary Statement

"For this rate limiter:
- 1M checks per second
- <1ms latency budget
- 100K clients, power-law distribution
- 3 MB state—fits in memory
- Distributed across nodes with eventual consistency
- Hot key handling for power clients (maybe local counters with periodic sync)"

---

# Part 10: Common Scale-Related Mistakes

## Mistake 1: Not Asking About Scale

**The problem**: Designing without establishing scale, leading to over- or under-engineering.

**Example**: Building a sharded database for a system that will never exceed 10,000 users.

**The fix**: Always ask about scale first. "Before I design, I need to understand scale. How many users? How much data? What's the growth expectation?"

## Mistake 2: Using Average Instead of Peak

**The problem**: Designing for average load and failing during peaks.

**Example**: "We have 10,000 QPS, so one database can handle it." But peak is 50,000 QPS.

**The fix**: Always calculate peak. "Average is 10K QPS, but peak during primetime is 3x, and during events is 10x. I need to design for 100K QPS capacity with graceful degradation beyond."

## Mistake 3: Ignoring Fan-Out

**The problem**: Calculating direct operations without considering multiplication effects.

**Example**: "1,000 posts per second—easy." But each post fans out to 1,000 followers = 1M operations.

**The fix**: Always trace the full path. "1,000 posts/second × 1,000 followers = 1M feed updates. Plus microservice amplification..."

## Mistake 4: Assuming Uniform Distribution

**The problem**: Designing for average case when reality has hot keys and skew.

**Example**: "100,000 clients × 10 RPS each = 1M RPS spread evenly." But actually 1% of clients generate 50% of traffic.

**The fix**: Consider distribution. "Power-law distribution means top 1% generate 500K RPS. Some individual clients might send 10K+ RPS. I need hot key handling."

## Mistake 5: Round Numbers Without Derivation

**The problem**: Throwing out impressive numbers without showing how they're derived.

**Example**: "Let's assume 1 billion QPS." Without explanation, this is meaningless.

**The fix**: Show your work. "200M DAU × 50 actions/day = 10B actions/day = 115K actions/second. Peak at 3x = 350K/second."

## Mistake 6: Over-Engineering for Hypothetical Scale

**The problem**: Building massive infrastructure for scale that may never materialize.

**Example**: Designing for billion-user scale when building an internal tool for 500 people.

**The fix**: Design for current + reasonable growth. "We have 500 users now, expecting 5,000 in a year. I'll design for 10,000 with a migration path to 100,000 if needed."

## Mistake 7: Under-Engineering for Obvious Growth

**The problem**: Ignoring clear growth trajectory and being forced into emergency redesigns.

**Example**: Using a single database for a rapidly growing startup, then scrambling when it can't scale.

**The fix**: Acknowledge growth trajectory. "We're at 100K users but growing 20% monthly. In 18 months, we'll be at 1M. I need to design the schema to support sharding from day one."

## Mistake 8: Forgetting Data Scale

**The problem**: Focusing only on request rate, ignoring storage and data processing needs.

**Example**: "50K QPS—that's fine." But 50K QPS × 1 KB × 1 year = 1.5 PB of data.

**The fix**: Calculate all dimensions. "50K writes/second × 1 KB = 50 MB/second = 4 TB/day = 1.5 PB/year. Storage is actually the primary challenge."

---

# Brainstorming Questions

## Understanding Scale

1. For a system you've built, what was the actual scale vs. what you designed for? Were you over or under?

2. Can you identify a system where scale forced a fundamental architecture change? What was the trigger?

3. Think of a hot key incident you've experienced or heard about. What caused it? How was it handled?

4. What's the read/write ratio of systems you work with? How does it affect the architecture?

5. When have you seen fan-out cause problems? How was it addressed?

## Estimation Practice

6. Estimate the QPS for Gmail. For Google Search. For YouTube. How do they differ?

7. How much storage does Instagram need for photos? What assumptions are you making?

8. What's the bandwidth requirement for Netflix streaming? For Zoom video calls?

9. How many messages per second does WhatsApp need to handle? Show your derivation.

10. What's the fan-out factor for Twitter when a celebrity tweets?

## Growth and Planning

11. For a system you know, what would break first if load increased 10x?

12. How do you decide when to invest in scaling vs. accepting limitations?

13. What's the cost of over-provisioning vs. under-provisioning? How do you balance?

14. How far ahead should you design? 2x? 10x? 100x? What factors influence this?

15. What metrics would tell you it's time to scale before users notice problems?

---

# Homework Exercises

## Exercise 1: Scale Estimation Practice

For each system, estimate:
- DAU/MAU
- QPS (read and write separately)
- Storage requirements
- Peak load factors

Systems:
1. Uber (rides only, not Uber Eats)
2. Slack (for a 10,000-person company)
3. A major bank's mobile app
4. A news website (like BBC or CNN)

Show your derivations.

## Exercise 2: Hot Key Analysis

Take a system you know (or choose: Twitter, DoorDash, Airbnb).

Identify:
- At least 3 potential hot keys
- What causes each to become hot
- How you would handle each

Create a mitigation strategy document.

## Exercise 3: Fan-Out Calculation

For a social media platform:

Calculate the actual operation count for:
- 1,000 posts/second
- Average 500 followers
- 1% of users are "celebrities" with 1M+ followers
- Each post generates 3 notifications (post, like, comment)

Then design a hybrid push/pull strategy with specific thresholds.

## Exercise 4: Read/Write Optimization

For each system, determine:
- Read/write ratio
- Which path is more critical
- Key optimization strategies

Systems:
1. A banking transaction system
2. A social media feed
3. An IoT sensor data platform
4. A multiplayer game leaderboard

## Exercise 5: Growth Modeling

Take a hypothetical startup:
- Launching with 10,000 users
- Growing 15% month-over-month
- Average user creates 50 MB of data per month

Model:
- User count at 6, 12, 24, 36 months
- Storage requirements at each milestone
- When single-database architecture breaks
- When you'd need to migrate to distributed storage

## Exercise 6: Complete Scale Analysis

Pick a system design prompt (notification system, chat app, etc.).

Produce a complete scale analysis document including:
- User scale derivation
- Request rate calculations (read/write/peak)
- Storage calculations
- Fan-out analysis
- Hot key identification
- Growth projections (1 year, 3 years)
- Architecture implications

Present this as you would in an interview (5-10 minutes).

---

# Conclusion

Scale is not a number—it's a lens for understanding your system.

Staff engineers approach scale systematically:

**They quantify before designing.** Before drawing any boxes, they establish: How many users? How many requests? How much data? What's the growth trajectory?

**They derive, not guess.** Numbers come from first principles: users × actions × multipliers. They show their work so it can be validated and adjusted.

**They think in peaks, not averages.** Systems fail at peak, not average. Peak during normal operation, peak during events, peak during failures.

**They consider the hidden multipliers.** Fan-out turns one operation into millions. Microservices turn one external call into dozens of internal calls. Read/write ratios change everything about optimization.

**They anticipate hot keys.** Skew is real. Power users, celebrity accounts, viral content—they all concentrate load. Designs must handle this.

**They plan for growth.** Not infinite growth, but reasonable growth. They know where the current design breaks and what the migration path looks like.

In interviews, scale estimation demonstrates maturity. It shows you've operated real systems at real scale. It shows you understand that the whiteboard design must survive contact with production reality.

Take the time to get scale right. It's the foundation for everything that follows.

---

*End of Volume 2, Section 4*


# System Design Interview Preparation for Google Staff Engineer (L6)

## Volume 2, Section 5: Phase 4 & Phase 5 — Non-Functional Requirements, Assumptions, and Constraints

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

**Example articulation**:
"This system handles user notification preferences, which is PII. All data will be encrypted at rest. All API endpoints require authentication. User data is only accessible to the owning user—no cross-user data access. We'll log all data access for audit purposes, and data must be deletable for GDPR compliance."

---

# Part 3: How Staff Engineers Reason About NFR Trade-Offs

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

*End of Volume 2, Section 5*



# System Design Interview Preparation for Google Staff Engineer (L6)

## Volume 2, Section 6: End-to-End System Design Using the 5-Phase Framework

### A Staff-Level Walkthrough: The News Feed System

---

# Introduction

This section demonstrates the complete application of the 5-Phase Framework to a real system design problem. We'll walk through the design of a **News Feed System** as a Staff Engineer would approach it in an interview—methodically, with explicit reasoning at each step.

This is not a reference architecture to memorize. It's a demonstration of *how to think* through a complex system design. Pay attention to:

- How each phase builds on the previous
- How decisions are made explicit and justified
- Where an L5 candidate might stop, and how L6 goes further
- How trade-offs are surfaced and resolved
- The interview narration style that communicates your thinking

Let's begin.

---

# The Prompt

**Interviewer**: "Design a news feed system for a social media platform."

*At this point, I would take a breath, acknowledge the prompt, and signal that I'm going to approach this systematically.*

**My response**: "A news feed system—that's a rich problem with interesting challenges. Before I start designing, I'd like to work through this systematically. I'll spend a few minutes understanding the users and use cases, then define requirements, establish scale, clarify non-functional requirements, and state my assumptions. That will give us a solid foundation for the architecture discussion. Does that approach work for you?"

*This signals to the interviewer that I have a structured approach and I'm taking ownership of the conversation.*

---

# Phase 1: Users & Use Cases

## Identifying Users

**My narration**: "Let me start by understanding who the users of this system are. I see several types:"

### Human Users

1. **Feed Consumers** (Primary)
   - End users who open the app and view their personalized feed
   - They scroll, interact, and expect immediate content
   - This is the primary use case—the feed exists for them

2. **Content Creators** (Secondary)
   - Users who create posts that appear in others' feeds
   - They care about reach—who sees their content
   - Overlap with consumers (same people, different mode)

3. **Advertisers** (Secondary)
   - Businesses whose ads appear in feeds
   - They care about targeting, placement, and performance

### System Users

4. **Content Service**
   - Internal service that stores and serves posts
   - Provides content when we build the feed

5. **Social Graph Service**
   - Provides follow relationships
   - Tells us whose content should appear in whose feed

6. **Ranking/ML Service**
   - Provides relevance scores for content
   - Helps personalize the feed

7. **Analytics Service**
   - Consumes feed events (loads, scrolls, interactions)
   - Used for metrics and ML training

### Operational Users

8. **SRE/Operations Team**
   - Monitors feed health
   - Needs visibility into latency, errors, queue depths

*At this point, I would pause and check alignment.*

**My narration**: "I've identified consumers as the primary user—feed generation and loading is optimized for them. Content creators and advertisers are secondary; their needs inform the design but don't drive core decisions. The system users tell me what services I'm integrating with. Does this user landscape match what you had in mind?"

---

## Identifying Use Cases

**My narration**: "Now let me map out the use cases, starting with core use cases and then edge cases."

### Core Use Cases

| Use Case | User | Description | Priority |
|----------|------|-------------|----------|
| Load home feed | Consumer | User opens app, sees personalized content | P0 (Critical) |
| Scroll for more | Consumer | User scrolls, more content loads seamlessly | P0 |
| Refresh feed | Consumer | User pulls to refresh for new content | P0 |
| Publish content | Creator | User posts, content appears in followers' feeds | P0 |
| Interact with content | Consumer | Like, comment, share, hide | P1 |

### Supporting Use Cases

| Use Case | User | Description | Priority |
|----------|------|-------------|----------|
| Control feed preferences | Consumer | Mute accounts, snooze, "see less" | P1 |
| View content performance | Creator | See reach and engagement metrics | P2 |
| Inject ads | Ad service | Insert ads at appropriate positions | P1 |
| Monitor feed health | Ops | View latency, error rates, throughput | P1 |

### Edge Cases

| Edge Case | Handling Approach |
|-----------|-------------------|
| New user (no follows) | Show trending/recommended content |
| User follows 50,000 accounts | Limit sources considered; prioritize |
| Celebrity posts (10M+ followers) | Pull model for fan-out; don't push |
| User inactive for 1 year | Fall back to trending + re-engagement signals |
| Post deleted after loaded in feed | Show placeholder or filter on scroll |
| User in poor connectivity | Aggressive caching, smaller payloads |

---

## Scope Control

*This is where Staff engineers distinguish themselves. I'm going to explicitly state what's in and out of scope.*

**My narration**: "Let me be explicit about scope. For this design session, I'm focusing on:"

### In Scope

- Home feed generation and serving for logged-in users
- Basic ranking (combining recency and engagement signals)
- Pagination (infinite scroll)
- Content from followed accounts
- Basic personalization

### Out of Scope (Explicitly)

- **Content storage and creation** — separate content service; I'll assume it exists
- **Social graph management** — separate service; I'll integrate with it
- **Search and discovery feeds** — different system, different ranking
- **Sophisticated ML ranking** — I'll treat ranking as a service that returns scores
- **Ad selection and targeting** — separate system; I'll leave slots for ad injection
- **Notifications** — separate system
- **Stories/ephemeral content** — separate feature
- **Video feed (like TikTok)** — different interaction model

**My narration**: "I'm scoping to the core feed experience: load, scroll, refresh. The most interesting challenges are feed generation at scale and the freshness/latency trade-off. Is this scope appropriate, or should I adjust?"

---

## Where L5 Stops vs. L6 Goes Further

*An L5 candidate might identify "users viewing feed" and "users posting content" but miss:*

- System users (what services exist? what do we integrate with?)
- Operational users (how is this thing monitored?)
- The celebrity edge case (which drives major architectural decisions)
- Explicit scope control (what we're NOT designing)

*A Staff engineer explicitly surfaces all of these, demonstrating awareness of the full ecosystem.*

---

# Phase 2: Functional Requirements

## Defining Core Functionality

**My narration**: "Based on the use cases, let me define the functional requirements. I'll organize these by flow type: read, write, and control."

### Read Flows

**F1: Generate Feed**
- Given a user ID, generate a personalized list of content items
- Content comes from followed accounts
- Content is ranked by relevance and recency
- Support pagination (cursor-based, not offset-based)

**F2: Load Feed Page**
- Return a page of feed items (e.g., 20 items per page)
- Include necessary metadata for rendering (author, content, interaction counts)
- Return next-page cursor for continued scrolling

**F3: Detect New Content**
- Allow client to check if new content is available
- Support "pull to refresh" with count of new items

### Write Flows

**F4: Publish Content**
- When a user publishes, make content available to their followers' feeds
- Content should appear in follower feeds within 1 minute (freshness target)

**F5: Record Interaction**
- When a user likes/comments/shares, record for ranking signals
- Update interaction counts (eventually consistent is fine)

**F6: Hide/Mute**
- When a user hides content or mutes an account, reflect in future feeds
- Should take effect within the current session

### Control Flows

**F7: Manage Feed Preferences**
- Operators can adjust global ranking parameters
- Support A/B testing of ranking algorithms

**F8: Manage Celebrity Thresholds**
- Configure thresholds for push vs. pull model
- Adjust based on system performance

---

## Avoiding Over-Specification

**My narration**: "Notice I'm specifying *what* happens, not *how*. For example, 'content should appear in follower feeds within 1 minute'—I'm not specifying whether that's push or pull, synchronous or async. That's an architecture decision I'll make based on scale and NFRs."

---

## Handling Edge Cases Explicitly

**My narration**: "Let me explicitly address the edge cases I identified earlier."

| Edge Case | Functional Handling |
|-----------|---------------------|
| New user (cold start) | F1 falls back to trending content + onboarding recommendations |
| Massive followee list | F1 limits sources to top N by engagement history |
| Celebrity posts | F4 uses pull model—content stored once, pulled into feeds at read time |
| Deleted content | F2 filters deleted content; may show placeholder |
| Stale user | F1 uses trending as primary signal, reduces personalization weight |

---

## Where L5 Stops vs. L6 Goes Further

*An L5 candidate might define:*
- "Users can view their feed"
- "Users can post content"

*A Staff engineer:*
- Separates flows by type (read/write/control)
- Specifies behaviors precisely ("within 1 minute")
- Addresses edge cases explicitly
- Avoids implementation details in requirements
- Considers operational flows (not just user flows)

---

# Phase 3: Scale

## Establishing Scale

**My narration**: "Let me establish the scale we're designing for. I'll make some assumptions and check if they're in the right ballpark."

### User Scale

| Metric | Value | Rationale |
|--------|-------|-----------|
| MAU | 500 million | Major social platform |
| DAU | 200 million | 40% DAU/MAU ratio (good engagement) |
| Concurrent users (peak) | 20 million | ~10% of DAU online at peak |

### Activity Scale

| Metric | Value | Derivation |
|--------|-------|------------|
| Feed loads per day | 1 billion | 200M DAU × 5 sessions/day |
| Feed loads per second (avg) | ~12,000 | 1B / 86,400 |
| Feed loads per second (peak) | ~50,000 | 4x average at peak hours |
| New posts per day | 100 million | 50% of DAU posts once |
| New posts per second (avg) | ~1,200 | 100M / 86,400 |
| New posts per second (peak) | ~5,000 | 4x average |

### Read/Write Ratio

**Feed loads : Posts = 1B : 100M = 10:1**

*But that's external requests. The interesting ratio is internal:*

**Feed generation reads : Post fan-out writes**

If average user has 500 followers:
- 100M posts × 500 followers = 50 billion fan-out writes per day (if push model)
- vs. 1 billion feed reads

This is why we need to think carefully about push vs. pull.

---

## Peak vs. Average Load

**My narration**: "I need to design for peak, not average. Let me think about what drives peak."

| Factor | Peak Multiplier | Notes |
|--------|-----------------|-------|
| Time of day (primetime) | 3-4x | Evening hours in major markets |
| Day of week | 1.2x | Weekends slightly higher |
| Special events | 5-10x | Breaking news, major sports events |

**Design target**: 50K feed loads/second sustained, ability to handle 100K+ with graceful degradation.

---

## Identifying Bottlenecks

**My narration**: "At this scale, where are the bottlenecks?"

1. **Feed Generation** — Computing a personalized feed at 50K/second is non-trivial
2. **Fan-Out** — If we push updates to followers, celebrity posts create massive write amplification
3. **Ranking** — ML-based ranking at this scale requires careful design
4. **Database I/O** — 50K reads/second from user's content is significant

---

## How Scale Influences Architecture

**My narration**: "Scale is driving several key architecture decisions:"

1. **Precomputation vs. Real-time**
   - At 50K/second, we can't compute feeds from scratch each time
   - Need some form of precomputation or caching

2. **Push vs. Pull**
   - For normal users (< 10K followers): Push is efficient
   - For celebrities (> 10K followers): Pull is necessary
   - Hybrid model required

3. **Caching**
   - Feed cache is essential
   - Content cache reduces database load
   - User preference cache avoids repeated lookups

4. **Sharding**
   - User data sharded by user_id
   - Content data sharded by author_id
   - Feed data sharded by owner_id

---

## Where L5 Stops vs. L6 Goes Further

*An L5 candidate might say:*
- "It's a large system, millions of users"
- "We'll need to scale horizontally"

*A Staff engineer:*
- Derives specific numbers from first principles
- Shows the math: "200M DAU × 5 sessions = 1B feed loads"
- Calculates internal amplification (fan-out)
- Identifies specific bottlenecks
- Connects scale to architecture decisions

---

# Phase 4: Non-Functional Requirements

## Establishing NFRs

**My narration**: "Now let me establish the quality requirements that will drive architecture decisions."

### Latency

| Operation | Target | Rationale |
|-----------|--------|-----------|
| Feed load (initial) | <300ms P99 | User waiting, app launch |
| Feed scroll (next page) | <200ms P99 | Seamless scrolling experience |
| Refresh (new content check) | <100ms P99 | Pull-to-refresh responsiveness |
| Content publish to feed | <60 seconds P95 | Tolerable delay for new posts |

**My narration**: "I'm prioritizing read latency over write latency. Users are actively waiting for feed loads. A 60-second delay for new posts appearing is acceptable—users don't usually check immediately if their post is in followers' feeds."

### Availability

| Component | Target | Rationale |
|-----------|--------|-----------|
| Feed serving | 99.9% | Core product experience |
| Feed generation | 99.9% | Required for fresh feeds |
| Content ingestion | 99.99% | Can't lose posts |

**My narration**: "99.9% is about 8 hours of downtime per year. For the feed, that's our target. For content ingestion, we need higher availability—losing user content is unacceptable."

### Consistency

| Aspect | Model | Rationale |
|--------|-------|-----------|
| Feed content | Eventual (30-60 sec) | Acceptable for new posts to appear with delay |
| Interaction counts | Eventual | Likes/comments can lag |
| User preferences | Read-your-writes | User expects mute to take effect immediately |
| Content existence | Strong | Deleted content should disappear quickly |

**My narration**: "I'm accepting eventual consistency for most things. The feed isn't a real-time system—nobody expects their post to appear in followers' feeds within milliseconds. But user preferences (like muting an account) should take effect immediately for that user."

### Reliability

- **No content loss**: Once a post is acknowledged, it cannot be lost
- **No feed corruption**: Feed should never show duplicate or broken content
- **Idempotent operations**: Retries should be safe

### Security

- **Authentication**: All feed requests from authenticated users
- **Authorization**: Users only see content they have access to
- **Rate limiting**: Protect against abuse
- **Content safety**: Integration with content moderation (out of scope for this design)

---

## Explicit Trade-Offs

**My narration**: "Let me be explicit about the trade-offs I'm making."

| Trade-Off | Choice | What We Sacrifice | Why |
|-----------|--------|-------------------|-----|
| Freshness vs. Latency | Latency | Tolerate 60-second staleness | Users expect instant app launch |
| Consistency vs. Availability | Availability | Eventual consistency for most data | Feed doesn't need strong consistency |
| Personalization vs. Simplicity | Moderate personalization | Full ML optimization | Can iterate; start simpler |
| Push vs. Pull | Hybrid | Complexity | Neither alone works at scale |

---

## Where L5 Stops vs. L6 Goes Further

*An L5 candidate might say:*
- "The system should be fast and reliable"
- "We need caching for performance"

*A Staff engineer:*
- Quantifies every NFR: "P99 <300ms, 99.9% availability"
- Distinguishes requirements by component
- Makes trade-offs explicit: "I'm choosing X over Y because..."
- Connects NFRs to architecture: "Because we need <300ms, we need precomputation"

---

# Phase 5: Assumptions & Constraints

## Assumptions

**My narration**: "Let me state my assumptions explicitly. If any of these are wrong, the design might need adjustment."

### Infrastructure Assumptions

1. **Cloud infrastructure** with auto-scaling, load balancing, managed databases
2. **CDN** for static content delivery (images, videos)
3. **Distributed caching** (Redis cluster or equivalent)
4. **Message queue** for async processing (Kafka or equivalent)
5. **Monitoring/alerting** infrastructure exists

### Service Assumptions

1. **Content service** exists and provides content by ID
2. **Social graph service** exists and provides follow relationships
3. **User service** exists with authentication/profile data
4. **Ranking service** exists and can score content for a user
5. **Analytics pipeline** exists to consume events

### Behavioral Assumptions

1. **Traffic follows typical patterns**: 3-4x peak during primetime
2. **Power-law distribution**: 1% of users create 50% of content
3. **Celebrity accounts**: ~0.1% have 1M+ followers
4. **Typical follow count**: Median ~200, mean ~500 (heavy tail)

### Environmental Assumptions

1. **Network latency** within region is <5ms
2. **Third-party services** (CDN, push) have 99.9% availability
3. **Database replication lag** is <100ms for read replicas

---

## Constraints (Given by Problem)

1. **Scale**: 200M DAU, 50K feed loads/second peak
2. **Latency**: <300ms P99 for feed load
3. **Freshness**: New posts appear within 60 seconds
4. **Platform**: Existing microservice ecosystem

---

## Simplifications

**My narration**: "I'm making some simplifications to focus on the core challenges. I'll note what I'm simplifying so we can discuss if needed."

1. **Single region**: Designing for single region first; global adds complexity
2. **Text focus**: Not designing media delivery in detail (CDN handles it)
3. **Simple ranking**: Treating ranking as a black box that returns scores
4. **No ads**: Leaving slots for ads but not designing ad selection
5. **No Stories**: Ephemeral content is a separate feature

---

## Why These Are Reasonable

**My narration**: "These simplifications are reasonable because:
- Single region captures the core complexity; multi-region is an extension
- Media delivery is a solved problem (CDN)
- Ranking is a deep topic worthy of its own design
- Ad selection is typically a separate team's domain
- Stories have different access patterns and would complicate this design"

---

## Where L5 Stops vs. L6 Goes Further

*An L5 candidate might:*
- Not state assumptions (they're implicit)
- Design without acknowledging constraints
- Simplify without saying so (looks like oversight)

*A Staff engineer:*
- States all assumptions explicitly
- Categorizes: assumptions vs. constraints vs. simplifications
- Explains why simplifications are reasonable
- Invites correction: "Is this assumption valid?"

---

# Architecture Design

**My narration**: "Now I have a solid foundation. Let me design the architecture that meets these requirements."

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Clients (Mobile/Web)                       │
└────────────────────────────────────┬────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                            API Gateway                               │
│                    (Auth, Rate Limiting, Routing)                    │
└────────────────────────────────────┬────────────────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
              ▼                      ▼                      ▼
     ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
     │  Feed Service   │    │ Content Service │    │  Publish Flow   │
     │                 │    │   (Existing)    │    │    Service      │
     └────────┬────────┘    └────────┬────────┘    └────────┬────────┘
              │                      │                      │
              ▼                      │                      │
     ┌─────────────────┐             │                      │
     │   Feed Cache    │◄────────────┘                      │
     │    (Redis)      │                                    │
     └────────┬────────┘                                    │
              │                                             │
              ▼                                             ▼
     ┌─────────────────┐                          ┌─────────────────┐
     │  Feed Storage   │                          │   Fan-Out       │
     │   (Sharded)     │◄─────────────────────────│   Service       │
     └────────┬────────┘                          └────────┬────────┘
              │                                            │
              │                      ┌─────────────────────┘
              ▼                      ▼
     ┌─────────────────┐    ┌─────────────────┐
     │  Ranking        │    │  Message Queue  │
     │  Service        │    │    (Kafka)      │
     └─────────────────┘    └─────────────────┘
```

---

## Component Design

### Feed Service

**Responsibility**: Generate and serve personalized feeds

**Design decisions**:

1. **Feed Construction Strategy**: Hybrid push-pull
   - For users with <10K followers: Pre-materialized feeds (push at publish time)
   - For celebrities (>10K followers): Merge at read time (pull)
   
2. **Feed Cache**:
   - Cache generated feeds in Redis
   - Cache key: `feed:{user_id}:{page}`
   - TTL: 5 minutes (balance freshness vs. load)
   - On cache miss: Generate from feed storage + celebrity pull

3. **Pagination**:
   - Cursor-based, not offset-based
   - Cursor encodes: timestamp + last_item_id
   - Prevents duplicate/missed items across pages

**Why this design**:
"At 50K requests/second, we can't compute feeds from scratch. Precomputation (push) works for most users. But celebrities have millions of followers—pushing to all of them would be 50B writes/day for just the top 1000 accounts. That's untenable. So we pull celebrity content at read time and merge it with the pre-materialized feed."

---

### Fan-Out Service

**Responsibility**: Distribute new content to followers' feeds

**Design decisions**:

1. **Fan-Out Logic**:
   ```
   if author.follower_count < 10,000:
       push_to_followers(content)  # Write to each follower's feed
   else:
       store_for_pull(content)      # Just store; pulled at read time
   ```

2. **Async Processing**:
   - Content publish → Kafka message
   - Fan-out workers consume and distribute
   - Decouples publish latency from fan-out completion

3. **Prioritization**:
   - Fan-out workers prioritize active users
   - Inactive users' feeds updated with lower priority

**Why this design**:
"The fan-out service handles the write amplification. For a user with 500 followers, one post becomes 500 writes to follower feeds. We do this asynchronously so publish latency stays low. The 10K threshold for push vs. pull is tunable based on observed system performance."

---

### Feed Storage

**Responsibility**: Store materialized feeds

**Design decisions**:

1. **Data Model**:
   ```
   feed_items table:
     user_id (partition key)
     timestamp (sort key)
     content_id
     author_id
     ranking_score
   ```

2. **Sharding**:
   - Shard by user_id
   - Each user's feed is on one shard
   - No cross-shard queries for feed read

3. **Storage Choice**:
   - Key-value store (Cassandra or DynamoDB)
   - Optimized for write throughput (fan-out)
   - Optimized for range queries (feed read)

4. **Retention**:
   - Keep 7 days of feed items per user
   - Background job cleans older items
   - Reduces storage, feed stays fresh

**Why this design**:
"Sharding by user_id means each feed read hits exactly one shard—no scatter-gather. Cassandra handles the write throughput for fan-out. 7-day retention keeps storage bounded."

---

### Content Merging (Read Path)

**My narration**: "Let me trace through what happens when a user loads their feed."

**Read Path (Detailed)**:

1. **Request arrives**: Client requests feed for user_id
2. **Cache check**: Look for `feed:{user_id}:1` in Redis
3. **Cache hit**: Return cached feed (most requests)
4. **Cache miss**:
   a. Fetch pre-materialized feed items from Feed Storage (500 items)
   b. Fetch celebrity content IDs (from users they follow with >10K followers)
   c. Fetch content details from Content Service
   d. Merge and rank using Ranking Service
   e. Return top 20, store in cache
5. **Pagination**: Subsequent pages use cursor to fetch next batch

**Latency breakdown**:

| Step | Target | Notes |
|------|--------|-------|
| Cache lookup | <5ms | Redis is fast |
| Feed Storage query | <50ms | Single shard |
| Celebrity content fetch | <50ms | Parallel fetches |
| Content Service calls | <50ms | Parallel, batched |
| Ranking | <50ms | Pre-loaded model |
| Merge & serialize | <10ms | In-memory |
| **Total (cache miss)** | **<215ms** | Within 300ms budget |

---

## Alternative Architectures Considered

**My narration**: "Before settling on this design, I considered two alternatives."

### Alternative 1: Pure Push (Rejected)

**Description**: Push every post to every follower's feed at publish time.

**Why rejected**:
- Celebrity with 50M followers → 50M writes per post
- Top 1000 celebrities posting once/day = 50B writes/day
- Storage cost: ~50B × 100 bytes = 5TB/day just for celebrity posts
- Not sustainable

**When it would work**: Platforms where max follower count is limited (like private social networks).

### Alternative 2: Pure Pull (Rejected)

**Description**: No precomputation; compute feed entirely at read time.

**Why rejected**:
- 50K feeds/second, each requiring:
  - Fetch 500 followee IDs
  - Fetch recent content from each (500 queries)
  - Rank 5000+ items
- Total: 25M content queries/second
- Latency would exceed 1 second

**When it would work**: Very small scale (< 100K users) or with aggressive caching.

### Chosen: Hybrid Push-Pull

**Why**: Best of both worlds. Push handles 99% of users efficiently. Pull handles the 1% that would explode the push model.

---

## Failure Scenarios and Degradation

**My narration**: "Let me address what happens when things go wrong."

### Feed Cache Failure (Redis Down)

**Impact**: All requests hit Feed Storage and Content Service
**Degradation**:
- Latency increases from ~50ms to ~200ms
- Still within 300ms budget
- **Action**: Auto-scale Feed Storage reads, alert on-call

### Feed Storage Failure (Shard Down)

**Impact**: Users on that shard can't load feeds
**Degradation**:
- Return cached feed if available (stale but functional)
- If no cache, return trending content as fallback
- **Action**: Failover to replica, page on-call

### Content Service Failure

**Impact**: Can't fetch content details for feed items
**Degradation**:
- Return feed with basic metadata (titles only)
- Disable rich content (images, videos)
- **Action**: Alert, activate fallback rendering

### Fan-Out Service Failure

**Impact**: New posts don't appear in feeds
**Degradation**:
- Posts still stored (durability preserved)
- Feeds become stale but still functional
- **Action**: Queue builds up in Kafka, workers catch up when restored

### Ranking Service Failure

**Impact**: Can't personalize feeds
**Degradation**:
- Fall back to chronological ordering
- Reduced engagement but functional
- **Action**: Alert, monitor engagement metrics

---

## Evolution Over 1-2 Years

**My narration**: "Systems evolve. Here's how I'd expect this to change."

### Year 1: Optimization and Scaling

1. **Improved ranking**: Move from simple heuristics to ML-based ranking
2. **Global expansion**: Multi-region deployment with regional feeds
3. **Real-time signals**: Incorporate trending topics, breaking news
4. **Ad integration**: Full ad injection with pacing

### Year 2: Advanced Features

1. **Interest-based content**: Content from non-followed accounts based on interests
2. **Video-first feed**: Optimization for video consumption
3. **Stories integration**: Ephemeral content in feed
4. **Explore feed**: Separate discovery feed with different ranking

### Architecture Evolution

| Phase | Change | Impact |
|-------|--------|--------|
| 6 months | Multi-region | Replicated Feed Storage per region |
| 1 year | ML ranking | Add feature store, model serving infrastructure |
| 18 months | Video | Add video-specific caching, CDN optimization |
| 2 years | Interest graph | New signals, content expansion beyond follows |

---

## Complete Phase Summary

**My narration**: "Let me summarize how the phases connected."

| Phase | Key Decisions | Impact on Design |
|-------|---------------|------------------|
| Phase 1: Users | Consumers are primary; celebrity edge case | Hybrid push-pull for celebrities |
| Phase 2: Functional | 60-second freshness; infinite scroll | Async fan-out; cursor-based pagination |
| Phase 3: Scale | 50K feeds/sec; 10:1 read/write | Precomputation; heavy caching |
| Phase 4: NFRs | <300ms latency; eventual consistency | Cache-first; async updates acceptable |
| Phase 5: Assumptions | Social graph exists; ranking service exists | Integration design; not building from scratch |

**Each phase informed the next, and the final architecture addresses all the requirements we established.**

---

# Where L5 Stops vs. L6 Goes Further: Summary

Throughout this design, I've highlighted where a Staff engineer goes beyond Senior-level thinking. Let me summarize:

| Aspect | L5 Approach | L6 Approach |
|--------|-------------|-------------|
| Users | "Users view feeds" | Identifies 8+ user types, distinguishes primary/secondary |
| Use Cases | Lists happy path | Addresses edge cases explicitly (celebrity, cold start) |
| Scale | "Large scale" | Derives: "200M DAU × 5 sessions = 1B loads/day = 12K/sec" |
| NFRs | "Fast and reliable" | Quantifies: "P99 <300ms, 99.9% availability" |
| Trade-offs | Implicit | Explicit: "Choosing latency over freshness because..." |
| Assumptions | Implicit | Stated and categorized |
| Alternatives | One design | Considers and rejects alternatives with reasoning |
| Failures | Not addressed | Degradation strategy for each failure mode |
| Evolution | Not addressed | 1-2 year roadmap |

---

# Brainstorming Questions

## Phase 1: Users & Use Cases

1. What other edge cases might we have missed? How would each affect the design?

2. If we were designing for a professional network (like LinkedIn) instead of a social network, how would the users and use cases differ?

3. How would the design change if we prioritized content creators over content consumers?

## Phase 2: Functional Requirements

4. If we required content to appear in feeds within 5 seconds (instead of 60), what would change?

5. What if we needed to support "undo" for published content? How would that affect the functional requirements?

6. How would the requirements differ for an algorithmic feed vs. a chronological feed?

## Phase 3: Scale

7. At 10x this scale (2 billion DAU), what breaks first? How would you address it?

8. If the read/write ratio were reversed (10 writes per read), how would the architecture change?

9. What if 10% of users were celebrities (instead of 0.1%)? How would that affect push vs. pull?

## Phase 4: NFRs

10. If we needed strong consistency for the feed, what would we sacrifice and what would we change?

11. What if we targeted 99.99% availability instead of 99.9%? What would that cost?

12. How would the design change for a market with poor network connectivity (high latency, packet loss)?

## Phase 5: Assumptions

13. What if we couldn't use a managed cache (Redis)? How would we handle caching?

14. What if the ranking service had 1-second latency instead of 50ms?

15. Which assumption, if wrong, would most invalidate this design?

---

# Homework Exercises

## Exercise 1: Redesign Under Different Constraints

Redesign the news feed system under these constraints:

**Scenario A**: Latency target is 100ms instead of 300ms
- What changes?
- What do you sacrifice?

**Scenario B**: Freshness target is 5 seconds instead of 60 seconds
- What changes?
- Is pure push now required?

**Scenario C**: 99.99% availability instead of 99.9%
- What redundancy is needed?
- How does cost change?

Write a 1-page summary of how the design changes for each scenario.

## Exercise 2: Identify the Riskiest Assumption

Review all the assumptions made in this design:

1. Rank them by risk (likelihood of being wrong × impact if wrong)
2. For the top 3 riskiest assumptions:
   - How would you validate them?
   - What's the contingency plan if they're wrong?
   - How would the design change?

## Exercise 3: Simplify the Design Further

The current design has:
- Feed Service
- Fan-Out Service
- Feed Storage
- Feed Cache
- Integration with 4 external services

Simplify it for a startup with:
- 100K DAU (not 200M)
- 3-person engineering team
- 3-month timeline

What components do you eliminate? What complexity do you remove? How does the simplified design differ?

## Exercise 4: Apply to a Different System

Apply the same 5-phase framework to design a **Rate Limiter** system.

For each phase:
- What are the key questions?
- What are the key decisions?
- How does each phase influence the next?

Compare the complexity of Rate Limiter vs. News Feed. Which phases are more important for each?

## Exercise 5: Failure Mode Expansion

For each failure scenario discussed:

1. Define the monitoring/alerting that would detect it
2. Define the runbook for on-call response
3. Design an automated mitigation (if possible)
4. Estimate the blast radius (how many users affected)

## Exercise 6: Interview Practice

Practice presenting this design in 35 minutes:

- 5 minutes: Phase 1 (Users & Use Cases)
- 5 minutes: Phase 2 (Functional Requirements)
- 5 minutes: Phase 3 (Scale)
- 5 minutes: Phase 4 (NFRs)
- 3 minutes: Phase 5 (Assumptions & Constraints)
- 10 minutes: Architecture walkthrough
- 2 minutes: Summary and questions

Record yourself. Watch for:
- Did you maintain the structure?
- Did you explain trade-offs?
- Did you check in with the "interviewer"?
- Was your pacing appropriate?

---

# Conclusion

This walkthrough demonstrated how a Staff Engineer approaches system design:

**Structured, not chaotic**: Five clear phases, each building on the previous.

**Explicit, not implicit**: Assumptions stated, trade-offs acknowledged, scope controlled.

**Quantified, not vague**: Specific numbers for scale, latency, availability.

**Trade-off aware**: Every design choice comes with sacrifices; we name them.

**Failure-minded**: Systems break; we plan for it.

**Evolution-aware**: Today's design is tomorrow's legacy; we plan for change.

The news feed system is complex, but by working through the framework systematically, it becomes tractable. Each phase reduces uncertainty until the architecture emerges naturally from the requirements.

This is Staff-level thinking: not just building systems that work, but building systems that work well, with explicit reasoning that can be challenged, defended, and evolved.

Practice this framework until it's second nature. Then in the interview room, you won't be wondering what to do next—you'll be leading a design discussion with confidence.

---

*End of Volume 2, Section 6*