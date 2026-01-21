# System Design Interview Preparation for Google Staff Engineer (L6)

## Volume 1, Section 1: How Google Evaluates Staff Engineers in System Design Interviews

---

# Introduction

If you're reading this, you're likely an experienced engineer—perhaps already at a senior level—preparing to interview for a Staff Engineer position at Google. You've shipped products, led teams through technical challenges, and built systems that serve real users. You know how to code, how to design, and how to ship.

And yet, something about the Staff interview feels different. It should. The Staff Engineer interview isn't simply a harder version of the Senior Engineer interview. It evaluates a fundamentally different mode of engineering. Understanding this distinction is the single most important thing you can do to prepare.

This section will help you understand exactly what Google is looking for when they interview Staff Engineer candidates. We'll explore what L6 means in Google's leveling system, how it differs from L5 and L7, what signals interviewers are trained to identify, and why many excellent Senior engineers struggle to demonstrate Staff-level thinking. By the end, you'll have a clear mental model for how to approach your system design interviews—not just to pass them, but to demonstrate genuine Staff-level capability.

Let's begin.

---

# Part 1: What Staff Engineer (L6) Means at Google

## The Leveling Landscape

Google's engineering ladder runs from L3 (entry-level) through L11 (Distinguished Engineer/Fellow). For most engineers, the meaningful career progression looks like this:

- **L3**: Entry-level, typically new graduates
- **L4**: Software Engineer, the "journey" level where engineers become fully productive
- **L5**: Senior Software Engineer, the "terminal" level where most engineers can stay indefinitely
- **L6**: Staff Software Engineer, the first level where scope extends beyond a single team
- **L7**: Senior Staff Software Engineer, where scope typically spans an organization
- **L8+**: Principal/Distinguished, where scope is company-wide or industry-wide

The jump from L5 to L6 is often described as the hardest transition in a Google engineer's career. It's not simply about being a better coder or knowing more technologies. It represents a qualitative shift in how you approach engineering problems.

## Quick Visual: L5 vs L6 at a Glance

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    L5 (Senior) vs L6 (Staff) QUICK COMPARISON           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   L5 SENIOR                          L6 STAFF                           │
│   ─────────                          ─────────                          │
│   "Here's how I'll build it"   →    "Here's what we should build"       │
│   "I finished my task"         →    "I identified the next 3 tasks"     │
│   "My code is solid"           →    "The system is solid"               │
│   "I asked for requirements"   →    "I defined the requirements"        │
│   "I work well with my team"   →    "I influence multiple teams"        │
│                                                                         │
│   SCOPE: Component/Feature           SCOPE: System/Problem Space        │
│   FOCUS: Execution                   FOCUS: Direction + Execution       │
│   IMPACT: Within team                IMPACT: Across teams               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## What L6 Actually Means in Practice

A Staff Engineer at Google is expected to:

**1. Own technical direction for a significant problem space**

At L5, you execute on problems given to you—often brilliantly. At L6, you define what problems need to be solved. You're not waiting for a product manager or tech lead to hand you requirements. You're identifying gaps, anticipating future needs, and shaping the technical roadmap.

Consider this example: A Senior engineer might implement a brilliant caching layer that reduces latency by 40%. A Staff engineer would have recognized six months earlier that the current architecture would hit scaling limits, evaluated multiple approaches (caching, sharding, redesign), considered the maintenance burden of each, and driven consensus on the right path forward—before anyone else had identified the problem.

**2. Influence beyond your immediate team**

L5 engineers are often deeply effective within their team. L6 engineers extend that effectiveness across team boundaries. This doesn't mean you manage other teams—you don't have that authority. It means you build relationships, establish credibility, and influence through technical excellence and clear communication.

A Staff engineer might notice that three teams are building similar authentication wrappers. Rather than just building a better one for their own team, they'll initiate a cross-team discussion, understand each team's requirements, and either consolidate the efforts or establish a shared standard. This is influence without authority.

**3. Make ambiguous problems concrete**

Senior engineers often excel when given well-defined problems. Staff engineers excel at taking a vague concern—"our system feels slow" or "we're worried about reliability"—and turning it into a clear technical investigation with concrete findings and actionable recommendations.

**4. Balance short-term and long-term thinking**

L5 engineers often optimize for the problem in front of them. L6 engineers hold both the immediate need and the two-year horizon in their minds simultaneously. They might say, "We can solve today's problem with a quick fix, but here's a migration path to a better architecture that we should start planning now."

**5. Mentor and elevate other engineers**

Staff engineers make the engineers around them more effective. This isn't just about formal mentorship (though that helps). It's about code reviews that teach, design documents that clarify, and architectural decisions that create space for others to contribute meaningfully.

## The Scope Question

One of the most common misunderstandings about L6 is that it requires a specific project scope. "I need to be working on a bigger project" is something I've heard many L5 engineers say.

This gets it backwards. Scope is not something you're given—it's something you create. Staff engineers are characterized by their ability to identify impactful work, regardless of their current project assignment. An L6 engineer on a "small" team finds ways to have outsized impact—perhaps by building tools that other teams adopt, establishing patterns that spread across the organization, or solving a problem once that would otherwise be solved poorly a dozen times.

The question interviewers ask themselves is not "Has this person worked on big projects?" but rather "Does this person think and act in ways that naturally lead to outsized impact?"

## Simple Example: Same Problem, Different Levels

**Problem**: "The checkout page is slow."

| Level | Response |
|-------|----------|
| **L4** | "I'll profile the page and fix the slow queries." |
| **L5** | "I'll investigate, find the bottleneck was N+1 queries, fix it, and add monitoring to catch this earlier next time." |
| **L6** | "I investigated, and the immediate cause is N+1 queries. But the real issue is our data access layer encourages this pattern. I'll fix checkout now, but I'm also proposing a team discussion on repository patterns to prevent this class of issue across all pages." |

The L6 response shows: **fixing immediate issue + identifying systemic cause + proposing broader solution**.

---

# Part 2: How L6 Differs from L5 (Senior) and L7 (Principal)

Understanding the distinctions between adjacent levels helps clarify what's expected at L6. Let me walk through these differences in detail.

## L5 to L6: The Qualitative Shift

### Ownership Model

**L5 (Senior)**: Owns components, features, or well-defined projects. Takes technical specifications and delivers excellent solutions. May push back on requirements or propose alternatives, but generally works within a defined problem space.

**L6 (Staff)**: Owns problem spaces, not just solutions. Defines what should be built, not just how to build it. Actively shapes the technical roadmap. Creates clarity from ambiguity.

*Example*: A Senior engineer is asked to "improve the recommendation system's latency." They profile the system, identify bottlenecks, implement optimizations, and achieve measurable improvement. Excellent work.

A Staff engineer, noticing user complaints about recommendations, would investigate whether latency is actually the problem (maybe it's relevance), understand the business impact of different improvements, propose a prioritized roadmap of changes, align stakeholders on the approach, and then execute—or delegate execution while staying accountable for outcomes.

### Influence Model

**L5**: Influences through individual contribution and team collaboration. Respected within their team and immediate collaborators.

**L6**: Influences across team and organizational boundaries. Establishes technical credibility that enables them to shape decisions in teams they don't directly work with.

*Example*: A Senior engineer writes excellent code reviews for their team and occasionally helps a neighboring team with a tricky problem. 

A Staff engineer notices that code review quality varies widely across the organization, proposes and documents code review standards, gets buy-in from tech leads across multiple teams, and helps establish a culture of thorough review. They didn't have authority to mandate this—they made it happen through influence.

### Risk and Uncertainty

**L5**: Executes confidently when requirements are clear. May struggle or escalate when facing significant ambiguity.

**L6**: Thrives in ambiguity. Takes vague directives and creates structure. Makes decisions with incomplete information and adjusts course as needed.

*Example*: Leadership says "We're worried about reliability." A Senior engineer might ask, "Which service should I focus on? What's the target SLA?" and wait for answers.

A Staff engineer would investigate current reliability metrics across services, identify the highest-impact areas, propose a phased approach to improvement, and present this analysis to leadership—turning a vague concern into an actionable plan.

### Communication and Alignment

**L5**: Communicates well within team contexts. Writes clear technical documents for their immediate audience.

**L6**: Communicates effectively across audiences—from fellow engineers to product managers to directors. Adapts message and detail level appropriately. Creates alignment across groups with different priorities.

### Technical Depth vs. Breadth

**L5**: Deep expertise in their domain. May have broad knowledge of adjacent areas.

**L6**: Deep expertise in multiple areas, combined with broad architectural understanding. Can reason about systems they haven't directly built. Understands organizational context and constraints.

## L6 to L7: The Scale Shift

The difference between L6 and L7 is primarily one of scale, though there are qualitative elements as well.

### Scope of Impact

**L6**: Impact typically spans a team or a few closely related teams. Might own a significant component or subsystem.

**L7**: Impact typically spans an organization (a collection of teams) or a company-wide concern. Might own an entire product area's architecture or a cross-cutting technical initiative.

*Example*: An L6 might own the architecture for a specific service that handles user authentication. An L7 might own the technical strategy for identity and access management across all of Google's consumer products.

### Strategic vs. Tactical

**L6**: Balances strategic thinking with hands-on execution. Still writes significant code and directly contributes to technical work.

**L7**: Primarily strategic. May still write code, but impact comes mainly through influence, direction-setting, and enabling others.

### Organizational Leadership

**L6**: Leads through technical contribution and local influence. May be the technical leader for their team.

**L7**: Shapes organizational direction. Works closely with senior management. Often represents engineering perspective in cross-functional leadership discussions.

### What This Means for L6 Candidates

Understanding the L6-L7 distinction helps calibrate your interview performance. In an L6 interview, you should demonstrate:

- Clear Staff-level thinking (as contrasted with L5)
- Strong execution orientation (you're still hands-on)
- Appropriate scope awareness (you don't need to boil the ocean)

Overreaching toward L7 behaviors—being too abstract, too strategic, too hands-off—can actually hurt you. Interviewers want to see that you can own and execute at Staff level, not that you're already thinking like a Principal.

---

# Part 3: What Interviewers Are Really Looking For in System Design Rounds

## The Purpose of System Design Interviews

Let's be direct about what system design interviews are for. They're not testing whether you can recite the components of a distributed system. They're not checking if you know the difference between SQL and NoSQL. They're not even primarily testing whether you can design a working system.

System design interviews are testing how you think about engineering problems at scale.

The system you design is almost incidental. What matters is:
- How you approach ambiguity
- How you make tradeoffs
- How you communicate your reasoning
- How you incorporate constraints and feedback
- How you demonstrate awareness of real-world complexity

An interviewer who has conducted hundreds of system design interviews has seen every possible design for "design a URL shortener" or "design Twitter." They're not looking for a novel design—they're looking for evidence of Staff-level thinking.

## The Signals Interviewers Are Trained to Identify

### Signal 1: Problem Decomposition

**What it looks like at Staff level**: Before diving into components, a Staff engineer clarifies the problem space. They ask about use cases, scale, constraints, and priorities. They identify what's actually hard about this problem. They break an amorphous challenge into tractable pieces.

**What weak candidates do**: Jump immediately into drawing boxes and arrows. Start with "We'll need a load balancer and some web servers..." without understanding what they're building or why.

*Example*: Asked to "design a notification system," a Staff candidate might spend the first five minutes clarifying:
- What types of notifications? (Push, email, SMS, in-app?)
- What's the expected scale? (Users, notifications per user, peak load?)
- What are the reliability requirements? (Can we lose a notification? What about duplicates?)
- What are the latency requirements? (Real-time? Best-effort? Eventual?)
- What systems already exist that we need to integrate with?

This isn't stalling—it's demonstrating that they understand the problem space matters more than the solution.

**Quick Reference: Good Clarifying Questions by Problem Type**

| Problem | Ask About |
|---------|-----------|
| **"Design Twitter"** | Read/write ratio? Celebrities with millions of followers? Real-time or eventual? Global or single region? |
| **"Design URL Shortener"** | Expected QPS? Custom URLs allowed? Analytics needed? Expiration? |
| **"Design Chat App"** | 1:1 or group? Persistent history? Delivery guarantees? Presence/typing indicators? |
| **"Design Rate Limiter"** | Per-user or per-IP? Fixed window or sliding? Precision requirements? Distributed or local? |
| **"Design Payment System"** | Exactly-once critical? Multi-currency? Fraud detection scope? Refund handling? |

### Signal 2: Tradeoff Articulation

**What it looks like at Staff level**: Every design decision is presented with explicit tradeoffs. "We could use X, which gives us Y but costs us Z." The candidate demonstrates awareness that there are no perfect solutions, only contextually appropriate ones.

**What weak candidates do**: Present design decisions as obvious or optimal without acknowledging alternatives. "We'll use Kafka for the message queue" without explaining why Kafka over RabbitMQ, or why a message queue at all.

*Example*: "For the data store, we have a few options. We could use a relational database like Spanner, which gives us strong consistency and SQL queries but requires careful schema design and has higher per-query latency. We could use Bigtable, which scales horizontally and has great write throughput but requires us to handle consistency in the application layer. Given that we said reads vastly outnumber writes and strong consistency matters for this use case, I'd lean toward Spanner—but I want to check: is the query latency budget tight?"

### Signal 3: Appropriate Depth

**What it looks like at Staff level**: The candidate knows when to go deep and when to stay high-level. They can zoom into any component and discuss implementation details, but they don't waste time on components that aren't interesting or differentiating.

**What weak candidates do**: Either stay too shallow (just drawing boxes without substance) or go too deep on irrelevant details (spending ten minutes on the hashing algorithm for an unimportant cache).

*Example*: "The notification delivery service is the critical path here—let me go deeper on that. For the user preference storage, we can use a standard key-value store with caching; there's nothing unusual about that use case, so I'll keep it simple unless you want me to elaborate."

### Signal 4: Failure Mode Awareness

**What it looks like at Staff level**: The candidate proactively considers what can go wrong. They discuss failure modes, degradation strategies, and operational concerns. They think about the system not just when it's working but when it's partially broken.

**What weak candidates do**: Design for the happy path only. When asked "what happens if this component fails?", they're caught off guard.

*Example*: "If the primary database becomes unavailable, we have a few options. We could fail closed and return errors, which is safest but impacts user experience. We could fail open and serve stale data from the cache, which is what I'd recommend for this read-heavy use case—users would rather see slightly stale notifications than an error page. We could also have a hot standby that we failover to, but that adds operational complexity. Let me sketch out the failover logic..."

### Signal 5: Operational Maturity

**What it looks like at Staff level**: The candidate thinks about day-2 operations: monitoring, alerting, debugging, rollback, capacity planning. They know that a system isn't complete when it ships—it's complete when it can be safely operated.

**What weak candidates do**: Stop at the architecture diagram. Don't consider how you'd know if the system is healthy, or how you'd diagnose a problem at 3 AM.

*Example*: "For monitoring, we'll want to track end-to-end latency at each stage of the notification pipeline, not just aggregate latency, so we can identify bottlenecks. We should alert on the 99th percentile, not the average, since averages hide latency spikes. We'll also want to track notification delivery rates by channel and surface drops prominently—if email delivery drops to 0, we need to know immediately, not when users complain."

### Signal 6: Practical Judgment

**What it looks like at Staff level**: The candidate demonstrates pragmatic decision-making. They don't over-engineer for hypothetical scale or under-engineer for real constraints. They show awareness of the cost of complexity.

**What weak candidates do**: Either build a Death Star when a bicycle would do, or propose something so simple it clearly won't work.

*Example*: "You mentioned we're starting with 10,000 users but could grow to 10 million. For the initial build, I'd start with a simpler architecture—single primary database, basic caching, synchronous processing. This gets us to market faster and lets us learn. When we hit 100,000 users, we'll need to add read replicas and async processing. At 1 million, we'll need to shard. I'd rather spend time on the business logic now and invest in scale later when we understand the actual access patterns."

### Signal 7: Communication Clarity

**What it looks like at Staff level**: The candidate's explanation is structured and easy to follow. They summarize before diving deep. They check for alignment. They use the whiteboard (or virtual equivalent) effectively to convey information.

**What weak candidates do**: Ramble. Jump between topics. Draw diagrams that only they can understand. Leave the interviewer confused about the overall structure.

*Example*: "Let me summarize the architecture before I go into details. We have three main components: ingestion, processing, and delivery. Ingestion handles incoming events from various sources and normalizes them. Processing determines what notifications to send and to whom, applying user preferences. Delivery handles the actual sending across channels. Now let me walk through each one—I'll start with ingestion because that's where the main scaling challenges are."

## What Interviewers Are NOT Looking For

Let me dispel some common misconceptions about what matters in Staff system design interviews.

### Not: Perfect Recall of Technologies

You don't need to know the exact configuration parameters for Kafka or the precise consistency guarantees of every database. It's fine to say, "I'd use a distributed log like Kafka here—I don't remember the exact retention settings off the top of my head, but we'd configure it based on our throughput and recovery time requirements."

What matters is knowing what tools exist, roughly what they're good for, and how to reason about applying them.

### Not: A Single Correct Answer

There are many valid designs for any problem. Interviewers are not comparing your design against a rubric of "correct" answers. Two candidates can propose completely different architectures and both receive strong feedback—if both demonstrated clear thinking, appropriate tradeoffs, and Staff-level judgment.

### Not: Covering Every Possible Feature

You won't have time to fully design every aspect of a complex system in 45 minutes. That's by design. Interviewers want to see how you prioritize, how you go deep where it matters, and how you acknowledge what you're leaving out.

### Not: Fancy Vocabulary

Using buzzwords doesn't impress experienced interviewers. If anything, it raises skepticism. "We'll use a CQRS pattern with event sourcing and a saga orchestrator" is meaningless unless you can explain why each of those choices makes sense for this specific problem.

### Not: Years of Experience

Interviewers don't care how many years you've been in the industry. They care about how you think today. A candidate with 8 years of experience who thinks like a mid-level engineer will be leveled as a mid-level engineer.

---

# Part 4: Signals of Staff-Level Thinking vs. Senior-Level Thinking

To make the distinction concrete, let me walk through how Staff and Senior candidates typically differ in their approach to a system design interview.

## The Opening: Clarifying Questions

### Senior-Level Approach

A strong Senior candidate asks reasonable clarifying questions:
- "How many users do we expect?"
- "What's the read/write ratio?"
- "Do we need to support mobile?"

These are good questions, but they're often asked from a checklist mentality—things you're "supposed to ask" in a system design interview.

### Staff-Level Approach

A Staff candidate asks questions that reveal deeper thinking:
- "What's the core user problem we're solving? I want to make sure I'm optimizing for the right thing."
- "You mentioned reliability is important—can you help me understand the cost of failure? Is a missed notification a minor annoyance or a critical failure?"
- "What's the team and organizational context? Is this a new system, or are we replacing something existing? Are there other teams whose systems we need to integrate with?"

The Staff candidate is trying to understand the problem space, not just collect parameters. They're demonstrating that they know design decisions depend on context.

## The Architecture: High-Level Design

### Senior-Level Approach

A strong Senior candidate produces a reasonable architecture:
- Clearly labeled components (API gateway, web servers, database, cache)
- Sensible data flow
- Acknowledgment of scale requirements

The design works. It's correct. It's what you'd find in a system design textbook.

### Staff-Level Approach

A Staff candidate produces a design that's grounded in the specific problem:
- Components are named for what they do in this domain, not generic infrastructure terms
- The design reflects the specific tradeoffs of this problem
- There's a clear rationale for why the design is shaped this way

More importantly, the Staff candidate explains their reasoning:

"I'm structuring this as three services rather than a monolith because [specific reason related to this problem]. I'm keeping these two components together because they share data access patterns and separating them would add latency without clear benefit. If the team grows or requirements change in [specific way], we might want to split them later."

## Deep Dives: Going into Detail

### Senior-Level Approach

A strong Senior candidate can go deep when prompted:
- Explains how a component works internally
- Discusses algorithms and data structures
- Handles follow-up questions competently

### Staff-Level Approach

A Staff candidate drives the deep dive strategically:
- Identifies which component is most interesting or challenging before being asked
- Goes deep with purpose, tying details back to the overall design goals
- Proactively surfaces tradeoffs and alternatives

"The most interesting part of this design is the deduplication logic. Let me go deep there. We have a few options: we could deduplicate at ingestion time using a bloom filter, which is memory-efficient but has false positive rates. We could deduplicate at processing time using a proper index, which is more accurate but adds latency. Given our requirement for [specific thing mentioned earlier], I'd recommend the bloom filter approach at ingestion, with exact deduplication as a background job. Let me walk through the bloom filter parameters..."

## Edge Cases and Failure Modes

### Senior-Level Approach

A strong Senior candidate handles edge cases when asked:
- "What if the database goes down?" → "We'd failover to a replica."
- "What about network partitions?" → "We'd need to handle that."

The answers are correct but reactive.

### Staff-Level Approach

A Staff candidate proactively addresses failure modes:

"Before I move on, let me talk about failure modes. The most likely failure is [X], and we handle it by [Y]. The most dangerous failure is [Z]—this is the scenario that wakes you up at 2 AM—and here's how we detect and mitigate it. There's also a more subtle failure mode where [A] and [B] interact in unexpected ways; I've seen this happen in production at [high-level description], and the solution is [C]."

The Staff candidate demonstrates operational maturity—they've thought about production reality, not just architecture diagrams.

## Estimation and Scaling

### Senior-Level Approach

A strong Senior candidate does capacity estimation when prompted:
- Calculates storage, bandwidth, and QPS
- Applies standard formulas correctly
- Concludes that "we'll need X servers"

### Staff-Level Approach

A Staff candidate uses estimation to inform design decisions:

"Let me do some back-of-envelope math to validate my architecture choices. If we have X users doing Y actions per day, that's Z QPS. That's well within what a single Spanner node can handle, so my initial single-primary design is appropriate. But I mentioned we might grow to 10X users—at that point, we'd exceed single-node capacity and would need to shard. Let me think about sharding strategy now so our initial schema supports it later..."

The estimation isn't an exercise—it's a tool for decision-making.

## Wrapping Up

### Senior-Level Approach

A strong Senior candidate summarizes their design:
- Reviews the components
- Confirms it meets the requirements
- Asks if the interviewer has questions

### Staff-Level Approach

A Staff candidate reflects on the design critically:

"To summarize: we've designed a system that handles the core use case with [specific characteristics]. The main strengths of this design are [X and Y]. The main risks are [A and B], and here's how I'd mitigate them. If I had more time, I'd want to explore [C], because I suspect there's an opportunity to [D]. I'd also want to validate my assumptions about [E] with the team before committing to this design."

The Staff candidate shows that they view this as a starting point for discussion, not a finished artifact.

## Quick Example: Weak vs Strong Responses

**Question**: "Design a notification system."

**Weak Opening** (L5 signals):
> "Okay, so for notifications we'll need an API gateway, then some web servers, a message queue like Kafka, and a database to store notifications. The API will receive requests..."

*Problem*: Jumped straight into components without understanding the problem.

**Strong Opening** (L6 signals):
> "Before I start designing, I want to understand the problem space. What types of notifications—push, email, SMS, in-app? What's the expected scale? And importantly, what's the cost of failure—is a missed notification a minor UX issue or a critical failure like a 2FA code? Also, are we building this from scratch or integrating with existing systems?"

*Why it's better*: Shows the design will be context-specific, not generic.

---

**Question**: "How would you store the data?"

**Weak Response**:
> "I'd use PostgreSQL."

*Problem*: No reasoning, no alternatives considered.

**Strong Response**:
> "For the notification data, we have a few options. PostgreSQL would give us strong consistency and flexible queries, which matters for the preference management side. But the notification delivery logs are write-heavy and don't need ACID—for those, I'd consider Cassandra or even just S3 with a separate query layer. Let me think about what matters most here... Given that we said reliability is critical, I'd lean toward PostgreSQL for the core data and evaluate a separate store for logs as we scale."

*Why it's better*: Shows tradeoff thinking, connects to requirements, proposes evolution path.

---

# Part 5: Why Strong L5 Candidates Often Fail L6 Interviews

This is perhaps the most important section of this document. If you're an experienced engineer preparing for Staff interviews, you likely already know how to design systems and write code. The question is whether you can demonstrate Staff-level thinking under interview conditions. Many excellent Senior engineers struggle with this. Let me explain why.

## Failure Pattern 1: Execution Excellence Without Strategic Framing

**The Syndrome**: You're so good at building things that you dive straight into building. Given a problem, you immediately see a solution and start describing how to implement it.

**Why It Fails at L6**: Staff engineers don't just build—they make sure they're building the right thing. Jumping into implementation signals that you're an executor, not a leader.

**What It Looks Like**: 
- Interviewer: "Design a system for scheduling rides."
- Candidate: "Okay, so we'll have an API that takes origin and destination, then we'll calculate the route, match with nearby drivers..."

The candidate has immediately constrained the problem to one interpretation and one solution without exploring the space.

**The Fix**: Force yourself to spend the first 5-10 minutes on problem understanding. Ask clarifying questions. Articulate your understanding back to the interviewer. State your assumptions explicitly. Only then propose an approach—and frame it as "here's my initial direction, let me know if we should adjust."

## Failure Pattern 2: Technical Depth Without Breadth

**The Syndrome**: You're an expert in your domain—maybe you know everything about databases, or distributed systems, or frontend architecture. In interviews, you gravitate toward your area of expertise and treat everything else superficially.

**Why It Fails at L6**: Staff engineers need to reason across domains. A system isn't just a database or just an API—it's an integrated whole. Over-indexing on one area while hand-waving others signals narrow thinking.

**What It Looks Like**:
- The candidate spends 30 minutes designing an elaborate caching strategy
- When asked about the API design, they say "we'll have standard REST endpoints"
- When asked about operational concerns, they say "we'll add monitoring"

The depth disparity reveals where the candidate is comfortable—and where they're not.

**The Fix**: Practice designing systems that require you to reason about areas outside your expertise. If you're a backend engineer, spend extra time on the client-side considerations. If you're a distributed systems expert, practice articulating frontend and UX implications. You don't need to be an expert in everything—you need to reason competently about everything.

## Failure Pattern 3: Solving the Stated Problem Without Questioning It

**The Syndrome**: You're so good at solving problems that you take the problem as given and optimize your solution for it. You don't consider whether the problem is well-framed or whether there's a better problem to solve.

**Why It Fails at L6**: Staff engineers are expected to push back, reframe, and clarify. Accepting a problem statement without examination suggests you'll build exactly what you're told rather than what's actually needed.

**What It Looks Like**:
- Interviewer: "Design a system to send 10 million push notifications per day."
- Candidate: "Okay, let me calculate the throughput requirements..." 
- (Proceeds to design an elaborate high-throughput system without ever asking why we need 10 million notifications or whether users actually want that many)

**The Fix**: Before solving, question. Why does this problem exist? What's the user need? What would happen if we didn't build this? What's the simplest thing that might work? Even if you end up building exactly what was asked, the questioning demonstrates Staff-level judgment.

## Failure Pattern 4: Local Optimization Without Global Awareness

**The Syndrome**: You optimize each component perfectly but don't consider how they interact. Your database design is great. Your API design is great. Your caching strategy is great. But together, they create problems.

**Why It Fails at L6**: Staff engineers think in systems, not components. They understand that a system's behavior emerges from component interactions, and they design for the whole.

**What It Looks Like**:
- The candidate designs a highly normalized database for consistency
- Then adds aggressive caching for performance
- Then describes read-after-write use cases that will fail due to cache inconsistency
- Doesn't notice the conflict until the interviewer points it out

**The Fix**: Regularly zoom out during your design. After designing a component, ask yourself: "How does this interact with what I've already designed? What assumptions am I making that other components need to respect? Where might there be conflicts?" Make the connections explicit.

## Failure Pattern 5: Answering Questions Instead of Driving Discussion

**The Syndrome**: You treat the interview as a Q&A session. The interviewer asks a question, you answer it, then you wait for the next question. You're reactive rather than proactive.

**Why It Fails at L6**: Staff engineers drive technical discussions. They don't wait to be asked—they identify what's important and address it. Waiting for prompts signals that you need direction rather than providing it.

**What It Looks Like**:
- Interviewer: "How would you handle failures?"
- Candidate: "We'd add retry logic."
- (Silence. Waiting for next question.)
- Interviewer: "What about cascading failures?"
- Candidate: "We'd add circuit breakers."
- (Silence. Waiting for next question.)

The candidate's answers are correct, but they're not demonstrating leadership.

**The Fix**: After answering a question, extend the discussion. "We'd add retry logic. And actually, thinking about failure modes more broadly, let me walk through the main scenarios..." Take ownership of the conversation. Volunteer information that the interviewer would want to know, even if they didn't ask.

## Failure Pattern 6: Overconfidence in One Solution

**The Syndrome**: You propose a design and defend it vigorously. When the interviewer challenges an aspect, you double down rather than considering alternatives.

**Why It Fails at L6**: Staff engineers hold their designs loosely. They know that good ideas can come from anywhere and that early designs are always wrong in some ways. Rigidity signals ego, not expertise.

**What It Looks Like**:
- Interviewer: "Have you considered using a graph database instead of SQL for the social relationships?"
- Candidate: "No, SQL is the right choice here."
- Interviewer: "But the query patterns seem heavily relational—"
- Candidate: "SQL can handle relational queries just fine with proper indexing."

The candidate may be right, but they're missing an opportunity to explore and demonstrate flexibility.

**The Fix**: Treat pushback as a gift. When the interviewer challenges your design, your response should be: "That's interesting—let me think about that." Then genuinely consider the alternative. You might say, "You raise a good point about graph patterns. Let me compare the approaches..." Even if you ultimately defend your original choice, the openness to alternatives signals maturity.

## Failure Pattern 7: Ignoring the Human Element

**The Syndrome**: You design technically elegant systems without considering who will build, maintain, and operate them. You treat engineering as pure problem-solving rather than sociotechnical work.

**Why It Fails at L6**: Staff engineers understand that systems exist in organizational contexts. The best technical solution might be wrong if the team can't build it, doesn't have expertise to maintain it, or if it requires cross-team coordination that doesn't exist.

**What It Looks Like**:
- "We'll build a custom database engine optimized for this use case."
- "This requires teams A, B, and C to coordinate their releases perfectly."
- "We'll use this obscure technology that only I know."

The designs might be technically optimal but organizationally infeasible.

**The Fix**: Bring organizational awareness into your designs. "This approach requires expertise in X—do we have that on the team, or should I propose something more aligned with our current skills?" Consider not just what's ideal but what's achievable. Acknowledge when a design requires coordination and think about how to make that coordination tractable.

## Failure Pattern 8: Perfectionism Over Pragmatism

**The Syndrome**: You want to design the perfect system—scalable to billions, resilient to any failure, extensible for any feature. You spend so much time on the perfect design that you don't complete a working one.

**Why It Fails at L6**: Staff engineers are pragmatic. They know that perfect is the enemy of good, that systems evolve, and that shipping something imperfect often beats waiting for perfection.

**What It Looks Like**:
- The candidate spends 25 minutes on an elaborate scaling strategy for a system that starts with 1000 users
- When asked about the core logic, they say "I'm getting to that"
- The interview ends before they've described a working system

**The Fix**: Start simple. Design for today's requirements first, then layer on scale and resilience. Explicitly say, "For v1, I'd keep this simple. Here's what we'd add as we grow." This demonstrates both pragmatism and forward thinking.

---

# Part 6: How Google's Staff Expectations Compare with Staff Roles at Other Companies

If you're coming from another company with a Staff title, or comparing Google's expectations with other FAANG/Big Tech companies, this section will help calibrate your expectations.

## The Title Inflation Problem

Let's address the elephant in the room: "Staff Engineer" means very different things at different companies.

At some companies, Staff is handed out after a certain number of years or after leading a medium-sized project. The title is more about tenure and reward than about a qualitative difference in contribution.

At Google, Staff (L6) represents a genuine level requiring demonstrated Staff-level impact. You don't get it for longevity—you get it for thinking and working at a different level than Senior engineers.

This creates challenges for candidates:
- If you're a "Staff Engineer" at a company with looser criteria, Google may assess you at Senior (L5).
- If you're a "Senior Engineer" at a company with stricter criteria, you might be assessed at Staff (L6) at Google.

The title on your resume matters less than the work you've done and how you describe it.

## Google L6 vs. Meta E6

Meta's E6 (Staff Engineer) is roughly equivalent to Google's L6. The expectations are similar:
- Technical leadership beyond a single team
- Driving ambiguous initiatives
- Influence without authority
- Strong execution combined with strategic thinking

Candidates from Meta generally find Google's Staff expectations familiar, though Google may place slightly more emphasis on technical depth and slightly less on organizational navigation.

## Google L6 vs. Amazon L6

Amazon's L6 (Senior SDE) is generally closer to Google's L5. Amazon's L7 (Principal SDE) is more equivalent to Google's L6.

This is one of the most common misalignments. Amazon Senior SDEs interviewing for Google Staff frequently underestimate the expectation gap. If you're coming from Amazon L6, you should approach the Google Staff interview as a step up, not a lateral move.

The key difference: Amazon L6 often operates within well-defined organizational structures and leverages Amazon's strong tenets culture. Google L6 requires more autonomous direction-setting and navigating ambiguity.

## Google L6 vs. Microsoft Principal

Microsoft's Principal Engineer is roughly equivalent to Google's L6. The expectations are similar in scope, though the cultures differ.

Microsoft Principal engineers often operate in more structured environments with clearer team boundaries. Google's flatter structure means L6 engineers need to be more entrepreneurial about creating impact.

## Google L6 vs. Startups "Staff"

Staff titles at startups vary wildly. At a 50-person company, the "Staff Engineer" might be anyone experienced. At a 500-person company, it might indicate genuine technical leadership.

If you're coming from a startup with a Staff title, focus less on the title and more on demonstrating Staff-level behaviors:
- Did you set technical direction for significant initiatives?
- Did you influence decisions beyond your immediate team?
- Did you take ambiguous problems and create clarity?
- Did you mentor and elevate other engineers?

If yes, you can demonstrate L6 capability regardless of your previous title. If no, you may want to interview for Senior and earn Staff through impact.

## Cultural Differences That Matter

Beyond level equivalence, there are cultural factors that affect how Staff is evaluated:

### Google's Emphasis on Technical Depth

Google interviews, more than some other companies, reward genuine technical depth. You can't bluff your way through with high-level architecture speak. Interviewers will probe for understanding and expect you to reason about implementation details.

### Google's "Googleyness"

Beyond technical skill, Google evaluates cultural alignment: intellectual humility, comfort with ambiguity, collaborative orientation. Being technically brilliant but arrogant or dismissive will hurt you more at Google than at some other companies.

### Google's Design Doc Culture

Google engineers often communicate through long-form design documents. If you're coming from a company with a more verbal or Agile culture, practice articulating your designs in structured written form. This habit of clear technical writing is embedded in how Google works.

### Google's Data-Driven Culture

Google engineers are expected to make decisions based on data. "I think this is better" is weaker than "I ran an experiment that showed 15% improvement." If you're coming from a culture with less measurement rigor, practice incorporating metrics and experimentation into your design thinking.

---

# Part 7: Common Misconceptions and Clarifications

Let me address some frequent misunderstandings about Staff interviews at Google.

## Misconception: "I Need to Have Led a Large Team"

Staff Engineer is not a management track. You don't need reports. Many excellent Staff engineers are individual contributors who lead through technical contribution and influence rather than organizational authority.

What matters is impact and influence, not headcount.

## Misconception: "I Need to Know Everything About Google's Stack"

You're not expected to be a Google expert before you join. Interviewers assess your ability to reason about problems, not your knowledge of specific Google technologies. If you've worked with distributed systems, databases, and modern infrastructure anywhere, you have the relevant background.

That said, understanding Google's scale does help calibrate your answers. Reading about how Google approaches problems (through public engineering blogs, papers, and talks) helps you speak the same language as your interviewers.

## Misconception: "System Design Interviews Are About Getting the 'Right' Answer"

There is no right answer. There are thoughtful answers and unreflective answers. A design that demonstrates clear thinking, explicit tradeoffs, and appropriate scope is "right" even if an interviewer would have designed it differently.

Two candidates can propose completely different designs and both pass—or both fail. It's about how you think, not what you conclude.

## Phrases That Signal Staff-Level Thinking

Use these naturally (not as scripts) to demonstrate Staff-level reasoning:

**For Problem Understanding:**
- "Before I dive in, help me understand the core user problem..."
- "What's the cost of getting this wrong? That'll help me prioritize..."
- "Is this replacing something existing, or greenfield?"

**For Tradeoff Articulation:**
- "We could go with A or B. A gives us X but costs us Y. Given our constraints, I'd lean toward A because..."
- "This is a classic tension between consistency and availability. For this use case..."
- "The simpler approach works for now, but won't scale past X. Let me design for that growth path..."

**For Showing Flexibility:**
- "That's a good point. Let me reconsider..."
- "I hadn't thought about that constraint. Here's how that changes things..."
- "There's another approach that might work better given what you just said..."

**For Demonstrating Depth:**
- "The most interesting part of this problem is X. Let me go deeper there..."
- "This looks standard, but there's a subtle issue with Y..."
- "I've seen this pattern fail when Z happens. Here's how we prevent that..."

**For Wrapping Up:**
- "To summarize the key decisions and their rationale..."
- "The main risks in this design are X and Y. Here's how we mitigate them..."
- "If I had more time, I'd want to explore..."

## Misconception: "I Should Prepare By Memorizing System Designs"

Rote memorization is the worst possible preparation strategy. Interviewers have seen every standard design. They'll quickly probe beyond the surface, and memorized answers collapse under scrutiny.

Instead, understand principles deeply. Know why systems are designed certain ways, not just how. Practice reasoning through novel problems, not regurgitating familiar ones.

## Misconception: "Staff Interviews Are Just Harder Senior Interviews"

This is the most damaging misconception. Staff interviews evaluate different capabilities, not just higher performance on the same capabilities.

A Senior interview asks: "Can you design a working system?"
A Staff interview asks: "Can you lead a team to design the right system for this context?"

Preparing for Staff interviews by doing more practice problems (as you would for Senior) misses the point. You need to practice demonstrating Staff-level thinking—which is what the rest of this guide will help you develop.

---

# Part 8: What Happens in the Interview Room

Let me give you a realistic picture of how Staff system design interviews unfold at Google.

## The Setup

You'll have 45-60 minutes with one interviewer. The interviewer is typically a Staff or Senior Staff engineer with experience evaluating candidates at this level. They've been trained on what signals to look for and how to calibrate their assessment.

The problem will be presented simply—often a single sentence. "Design a photo-sharing application." "Design a notification system." "Design a global configuration service." The simplicity is intentional. The interviewer wants to see how you expand from a vague prompt into a structured design.

You'll have a whiteboard (or virtual equivalent). You're expected to draw, write, and explain simultaneously. The interviewer may be quiet for long stretches or may pepper you with questions—both are valid interviewing styles.

## Sample 45-Minute Interview Timeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    IDEAL TIME ALLOCATION (45 min)                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   0:00 - 0:02   Problem statement from interviewer                      │
│                                                                         │
│   0:02 - 0:08   CLARIFY (6 min)                                         │
│                 • Ask 4-6 clarifying questions                          │
│                 • State your understanding back                         │
│                 • Confirm scope and priorities                          │
│                                                                         │
│   0:08 - 0:15   HIGH-LEVEL DESIGN (7 min)                               │
│                 • Draw main components                                  │
│                 • Explain data flow                                     │
│                 • State key design decisions                            │
│                                                                         │
│   0:15 - 0:35   DEEP DIVES (20 min)                                     │
│                 • Focus on 2-3 most interesting areas                   │
│                 • Discuss tradeoffs                                     │
│                 • Handle interviewer questions                          │
│                 • Cover failure modes                                   │
│                                                                         │
│   0:35 - 0:42   SCALE & OPERATIONS (7 min)                              │
│                 • Capacity estimation                                   │
│                 • Monitoring and alerting                               │
│                 • Scaling strategy                                      │
│                                                                         │
│   0:42 - 0:45   WRAP UP (3 min)                                         │
│                 • Summarize key decisions                               │
│                 • Acknowledge limitations                               │
│                 • Invite questions                                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Pro Tip**: Watch the clock. If you're 20 minutes in and still on clarifying questions, you're in trouble.

## The First Five Minutes

How you start matters enormously. Strong candidates demonstrate Staff-level thinking immediately:

"Before I start designing, I'd like to understand the problem space. Can you help me understand..."

Then: thoughtful clarifying questions. Not a checklist, but genuine exploration of what matters for this problem.

Weak candidates do this:

"Okay, so we need [restates problem]. Let me draw the architecture..."

They've jumped into solution mode without establishing context.

## The Middle Thirty Minutes

This is where the design takes shape. Strong candidates:
- Draw a clear high-level architecture, explaining choices as they go
- Dive deep into the most interesting or challenging components
- Surface tradeoffs explicitly
- Proactively address failure modes and operational concerns
- Check in with the interviewer: "Does this direction make sense? Shall I go deeper here or move on?"

The interviewer may:
- Ask clarifying questions
- Challenge design decisions
- Propose constraints or changes ("What if we need to handle 10x the load?")
- Probe for depth on specific components
- Stay quiet and let you drive

All of these are normal. Don't interpret questions as criticism—they're exploration.

## The Last Ten Minutes

Strong candidates use this time to:
- Summarize the design and key decisions
- Acknowledge limitations and future work
- Reflect on what they'd do differently with more time
- Invite questions

Weak candidates:
- Rush to finish one more component
- End abruptly without synthesis
- Leave without summarizing, assuming the interviewer followed everything

## The Interviewer's Perspective

Put yourself in the interviewer's shoes. They've done this dozens or hundreds of times. They're not looking for impressive vocabulary or perfect designs. They're asking themselves:

- "Would I want this person leading a technical initiative at Google?"
- "Do they think about problems the way our best Staff engineers do?"
- "Can they own a significant problem space and drive it forward?"
- "Would they make the engineers around them more effective?"

Everything you do in the interview is evidence for or against these questions.

---

# Part 9: Realistic Anecdotes and Patterns

Let me share some patterns I've observed (details generalized to respect confidentiality) that illustrate how Staff interviews succeed and fail.

## The Expert Who Couldn't Zoom Out

A candidate with deep expertise in distributed databases was asked to design a user analytics system. They spent 35 minutes designing an elaborate distributed data store, explaining every nuance of partitioning, replication, and consistency.

When the interviewer asked about how data would be ingested, the candidate said, "That's straightforward—we'll have an API." When asked about access patterns and query optimization, they said, "We'll add indexes as needed."

The candidate was genuinely expert in one area—and the interviewer knew it. But Staff engineers need to reason across the whole system. The feedback: "Strong L5, not demonstrating L6 scope."

**Lesson**: Depth is important, but not at the expense of breadth. Cover the whole system competently, then go deep where it matters most.

## The Big Company Architect

A candidate from a large tech company with a "Principal Architect" title came in with obvious confidence. Asked to design a notification system, they produced an elegant architecture with perfectly labeled boxes and clean separation of concerns.

When the interviewer asked, "How would you handle the case where a user unsubscribes from notifications mid-delivery?", the candidate said, "We'd have the delivery team handle that."

When asked about data consistency between the preference store and the delivery pipeline, they said, "We'd need to align with the platform team on that."

The candidate was thinking at the organizational level, delegating implementation details to hypothetical teams. But in a Staff interview, you need to own the technical details, not just the architecture.

**Lesson**: At L6, you're still hands-on. You can delegate in practice, but in an interview, you need to demonstrate that you can reason about the details.

## The Perfect Interviewer

A candidate was technically solid but treated the interview as a presentation. They drew their architecture, explained every component, and answered questions correctly. But there was no dialogue. The interviewer couldn't tell if the candidate could collaborate, incorporate feedback, or adjust their thinking.

When the interviewer suggested an alternative approach, the candidate said, "That would work too," and moved on without exploring it. When asked about tradeoffs, they listed pros and cons without committing to a recommendation.

The candidate was competent but passive. Staff engineers are expected to have opinions and drive decisions.

**Lesson**: Engage actively. Have opinions. Drive the discussion. Treat it as a collaboration, not a presentation.

## The Over-Communicator

A candidate was so focused on being thorough that they couldn't finish. They spent 15 minutes on clarifying questions, exploring every possible interpretation of the problem. They took 10 minutes to draw a high-level architecture, explaining every arrow. When they started going deep on the first component, the interviewer realized there was no chance of covering the system in the remaining time.

The candidate's thinking was good—but so slow that the interviewer couldn't assess whether they could actually design a complete system.

**Lesson**: Time management matters. Practice pacing. Spend 5-10 minutes on clarification, 25-30 on design, 5-10 on synthesis. Adjust based on interviewer signals.

## The Staff Candidate

Let me describe a Staff-level performance for contrast.

Asked to design a location-sharing service, the candidate started by clarifying: "Help me understand the use case. Is this real-time tracking like Find My Friends, or periodic check-ins like Swarm? What's the expected precision—city level or GPS-accurate? What's the scale—millions of users sharing with friends, or billions of users with public locations?"

Once the scope was clear, they proposed a design and explained their reasoning: "I'm choosing [approach] because [specific tradeoffs related to the clarified requirements]. The main alternative would be [different approach], which would be better if [different constraints]."

When the interviewer challenged a choice, the candidate said, "That's a good point. Let me think about that... You're right that my approach has [weakness]. We could address that by [modification], or we could switch to [alternative] if the constraint you mentioned is more important than I thought. What's your intuition?"

They went deep on the most novel component—not the database or the API (standard) but the real-time location fanout to friends (specific to this problem). They addressed failure modes proactively: "If the location service goes down, we can serve stale locations from cache with a 'last updated' timestamp. Users understand that location data might be slightly stale."

They wrapped up by summarizing key decisions, acknowledging limitations, and reflecting: "If I had more time, I'd want to think more carefully about privacy implications—there are subtle leakage risks I didn't fully explore."

The interviewer left thinking: "This person thinks like our Staff engineers. They'd be effective on day one."

---

# Part 10: What to Do Next

You now understand how Google evaluates Staff engineers in system design interviews. You understand what L6 means, how it differs from L5 and L7, what interviewers are looking for, common failure patterns, and how Google's expectations compare with other companies.

This is the foundation. But understanding is not preparation—it's the start of preparation.

The sections that follow will give you practical frameworks for approaching system design problems, deep dives into common problem domains, worked examples with detailed analysis, and practice exercises with feedback rubrics.

For now, let me leave you with some immediate next steps:

**1. Reflect on your current approach.** Based on what you've read, how would you assess your own system design interview performance? Which failure patterns might apply to you?

**2. Practice with the L6 mindset.** In your next practice session (or even your real work), consciously try to demonstrate Staff-level thinking. Ask clarifying questions before solving. Articulate tradeoffs explicitly. Drive discussions rather than waiting to be asked.

**3. Get calibrated feedback.** If possible, do practice interviews with people who have experience at Google or similar companies. Generic feedback ("good design!") is useless. You need calibrated feedback on whether you're demonstrating L6 thinking.

**4. Study systems, not solutions.** Read about how real systems are built. Google's engineering blog, papers from systems conferences, and postmortems from major outages are goldmines. Understand why systems are designed the way they are.

**5. Develop your own point of view.** Staff engineers have informed opinions. What do you believe about system design that others might disagree with? What patterns have you seen succeed or fail? Your unique perspective is an asset.

The road to Staff is not about becoming a better version of a Senior engineer. It's about becoming a different kind of engineer—one who leads, shapes, and elevates. The interview is your chance to show that you're already there.

---

# Quick Reference Card

## Self-Assessment Checklist

After each practice interview, honestly assess yourself:

**Did I demonstrate Staff-level thinking?**

| Behavior | ✅ Yes | ❌ No |
|----------|--------|-------|
| Asked clarifying questions that revealed deeper thinking (not just checklist) | | |
| Stated explicit tradeoffs for major design decisions | | |
| Identified the most interesting/challenging part and went deep | | |
| Proactively addressed failure modes (not just when asked) | | |
| Considered operational concerns (monitoring, debugging, rollback) | | |
| Used estimation to inform decisions (not as separate exercise) | | |
| Drove the discussion (not just answered questions) | | |
| Showed flexibility when challenged (not defensive) | | |
| Summarized with key decisions, risks, and future work | | |
| Managed time well (covered the whole system) | | |

**Scoring**: 8+ checks = Staff-level performance. 5-7 = Borderline. <5 = Senior-level.

## Common Mistakes Quick Reference

| Mistake | Fix |
|---------|-----|
| Jumping into boxes and arrows | Spend 5 min clarifying first |
| "We'll use Kafka" (no explanation) | "I'd use Kafka because... alternatively..." |
| 30 min on one component | Set time goals, check the clock |
| "We'll add monitoring" | Specify what metrics, what alerts |
| Defending design when challenged | "Good point, let me think about that..." |
| Waiting for next question | Extend the discussion yourself |
| Designing for billions when asked for thousands | Start simple, then discuss growth path |

## The 5 Questions Interviewers Ask Themselves

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   1. Would I want this person LEADING a technical initiative?           │
│                                                                         │
│   2. Do they THINK like our best Staff engineers?                       │
│                                                                         │
│   3. Can they OWN a problem space and drive it forward?                 │
│                                                                         │
│   4. Would they make engineers around them MORE EFFECTIVE?              │
│                                                                         │
│   5. Can they COMMUNICATE clearly to different audiences?               │
│                                                                         │
│   Everything you do is evidence FOR or AGAINST these questions.         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## One-Page Summary: L5 vs L6 Signals

```
L5 (SENIOR) SIGNALS              L6 (STAFF) SIGNALS
──────────────────────           ──────────────────────

✓ Designs working system         ✓ Designs RIGHT system for context
✓ Answers questions well         ✓ Drives the discussion
✓ Goes deep when prompted        ✓ Identifies where to go deep
✓ Handles edge cases asked       ✓ Proactively surfaces edge cases
✓ Estimates correctly            ✓ Uses estimates to make decisions
✓ Produces correct design        ✓ Articulates design tradeoffs
✓ Covers requirements            ✓ Questions/refines requirements
✓ Works within scope             ✓ Identifies broader implications
```

---


