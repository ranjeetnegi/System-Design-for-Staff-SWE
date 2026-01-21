# System Design Interview Preparation for Google Staff Engineer (L6)

## Volume 1, Section 2: Scope, Impact, and Ownership at Google Staff Engineer Level

---

# Introduction

In the previous section, we explored how Google evaluates Staff Engineers and what distinguishes L6 thinking from L5 thinking. Now we need to dig deeper into three concepts that are central to Staff-level performance: scope, impact, and ownership.

These words get thrown around constantly in engineering career discussions. "You need more scope." "Demonstrate broader impact." "Take more ownership." But what do they actually mean? And more importantly, how do you demonstrate them—both in your daily work and in an interview setting?

This section will give you clear mental models for understanding scope, impact, and ownership at the Staff level. We'll explore how these concepts differ from Senior-level expectations, how they manifest in system design work, and how interviewers detect them (often implicitly) during your interview. By the end, you'll have practical frameworks you can apply immediately.

---

# Part 1: What "Scope" Means at Staff Level

## Quick Visual: Scope at a Glance

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SCOPE DIMENSIONS BY LEVEL                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   TECHNICAL SCOPE (What you reason about)                               │
│   L5: ████░░░░░░░░░░  My component + interfaces                         │
│   L6: ████████████░░  Systems + cross-team patterns                     │
│   L7: ██████████████  Org-wide architecture                             │
│                                                                         │
│   TEMPORAL SCOPE (How far ahead you think)                              │
│   L5: ██░░░░░░░░░░░░  This quarter                                      │
│   L6: ████████░░░░░░  1-2 years                                         │
│   L7: ██████████████  3-5 years                                         │
│                                                                         │
│   ORGANIZATIONAL SCOPE (How far your influence reaches)                 │
│   L5: ███░░░░░░░░░░░  My team                                           │
│   L6: █████████░░░░░  Multiple teams                                    │
│   L7: ██████████████  Entire organization                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## The Scope Misconception

Let's start by dismantling a common misconception: scope is not about project size.

Many engineers believe that to demonstrate Staff-level scope, they need to work on bigger projects—more users, more data, more complexity. They think, "If I could just get staffed on a larger initiative, I'd be able to demonstrate Staff-level work."

This gets it backwards. Scope is not something assigned to you. Scope is something you create.

A Staff Engineer on a "small" project finds ways to have outsized impact. They identify connections to other teams. They build reusable abstractions. They establish patterns that spread. They solve problems once that would otherwise be solved poorly many times. The project may be small, but the scope of their thinking and influence is large.

Conversely, an engineer on a "large" project who only executes their assigned tasks has narrow scope regardless of the project's size. They're doing important work, but they're not demonstrating the expansive thinking that characterizes Staff-level contribution.

## The Three Dimensions of Scope

Scope at Staff level has three dimensions:

### 1. Technical Scope: How much of the system do you reason about?

A Senior engineer typically reasons deeply about their component and its immediate interfaces. They know their service inside and out. They understand how it connects to adjacent services.

A Staff engineer reasons about entire systems—or even systems of systems. They think about:
- How components interact and where the interactions create problems
- How changes in one area ripple through others
- How technical decisions affect not just their team but the broader organization
- What infrastructure or patterns could benefit multiple teams

**Example**: A Senior engineer owns the recommendation service. They optimize its algorithms, improve its latency, and ensure its reliability.

A Staff engineer asks: "Why do we have three different recommendation services across the company? What would it take to consolidate them? What are the tradeoffs? Even if we don't consolidate, could we share the underlying ML pipeline?"

The Senior engineer's scope is the service. The Staff engineer's scope is the problem space.

### 2. Temporal Scope: How far into the future do you think?

A Senior engineer typically thinks about the current quarter, maybe the next one. They're focused on delivering committed work and responding to immediate needs.

A Staff engineer holds multiple time horizons simultaneously:
- **This week**: What fires need fighting? What blockers need removing?
- **This quarter**: What's on the roadmap? Are we on track?
- **This year**: Where is the product and technology headed? Are we building the right foundation?
- **Two-plus years**: What will break when we 10x? What bets are we making about technology trends?

**Example**: A Senior engineer is asked to add a new feature to the payment system. They implement it well, considering edge cases and writing good tests.

A Staff engineer, while implementing the feature, notices that the payment system architecture is showing strain. They think: "This feature is fine for now, but if we keep adding features this way, we'll have a maintenance nightmare in 18 months. Let me propose a refactoring roadmap that we can execute incrementally alongside feature work."

The Senior engineer solved today's problem. The Staff engineer solved today's problem while preventing tomorrow's.

### 3. Organizational Scope: How broadly do you influence?

A Senior engineer's influence typically extends to their team and immediate collaborators. They're respected by the people who work with them directly.

A Staff engineer's influence extends across team boundaries. They:
- Are known and respected by engineers on other teams
- Participate in cross-team technical discussions
- Shape standards and practices beyond their immediate team
- Get consulted on decisions outside their direct responsibility

**Example**: A Senior engineer is the expert on their team's caching layer. When their teammates have caching questions, they come to this engineer.

A Staff engineer is the expert on caching across the organization. When any team is making caching decisions, they're consulted. They've written the caching best practices doc. They've established the patterns that other teams follow. They review caching-related designs across the organization.

The Senior engineer is an expert. The Staff engineer is a reference.

## Scope is Not Authority

Here's a crucial distinction: scope is not authority.

A manager has authority over their team. They can assign work, make decisions, and hold people accountable. Their scope comes from their organizational position.

A Staff engineer has no such authority. They can't tell other teams what to do. They can't mandate architectural decisions. They can't assign work to anyone.

Yet their scope is often comparable to a manager's, or larger. How?

Staff engineers expand scope through:
- **Credibility**: They've earned trust through consistent excellent judgment
- **Visibility**: Their work is known and respected beyond their team
- **Initiative**: They identify problems and propose solutions without being asked
- **Communication**: They explain their thinking clearly and build consensus
- **Humility**: They incorporate feedback and give others credit

Authority-based scope is fragile—it disappears when you change roles. Credibility-based scope is durable—it follows you wherever you go.

## Simple Example: Same Situation, Different Scope

**Situation**: You notice the API is slow.

| Level | Response | Scope Signal |
|-------|----------|--------------|
| **L4** | "I'll profile and optimize the slow endpoints." | Task-focused |
| **L5** | "I'll optimize the endpoints and add performance monitoring to catch this earlier." | Component ownership |
| **L6** | "I'll fix this, but I noticed three other services have similar issues. Let me propose a shared performance library and org-wide latency SLOs." | Problem space ownership |

The L6 response shows: **fix immediate issue + identify pattern + propose systemic solution**.

## How to Expand Your Scope

If scope is something you create rather than something you're given, how do you create it?

### Look Beyond Your Boundaries

Most engineers, even good ones, stay within their assigned boundaries. They do their tickets, attend their meetings, and focus on their team's goals. This is fine for Senior level.

To expand scope, you need to look beyond those boundaries:
- What problems exist at the intersection of your team and others?
- What infrastructure is everyone building separately?
- What patterns are being discovered independently in different places?
- What decisions being made elsewhere will affect your team?

Don't wait for someone to point these out. Look for them actively.

### Follow the Pain

Scope opportunities often hide in places where people are frustrated. When you hear "Ugh, we have to deal with X again" or "I wish Y wasn't so complicated," that's a signal. Someone's pain is your scope opportunity.

A Senior engineer hears these complaints and sympathizes. A Staff engineer hears them and thinks: "Is there a systemic solution? Could I make this pain go away for everyone?"

### Build Bridges

Scope expansion often starts with relationships. Get to know engineers on other teams. Understand their problems. Look for connections.

These relationships pay dividends:
- You hear about problems before they become crises
- You understand constraints that aren't visible from your team
- You build trust that enables future collaboration
- You become a connector—someone who knows how the pieces fit together

### Write Things Down

One of the highest-leverage ways to expand scope is to document your knowledge in ways that others can use. Write design docs that become references. Create onboarding guides that help new engineers. Document patterns and anti-patterns from your experience.

Written artifacts spread your influence beyond the people you talk to directly. They scale your impact.

### Volunteer for Cross-Cutting Work

When cross-team initiatives come up—incident response, infrastructure migration, process improvement—volunteer. These are scope opportunities in disguise.

Yes, this work is often unglamorous. But it gives you visibility across teams, relationships with engineers you wouldn't otherwise know, and understanding of how the organization actually works.

---

# Part 2: Difference Between Team-Level, Multi-Team, and Org-Level Impact

## The Impact Ladder

Impact at Google is often described in terms of scope of effect:

- **Team-level impact**: Your work directly improves your team's outcomes
- **Multi-team impact**: Your work improves outcomes for multiple teams
- **Org-level impact**: Your work shapes the direction or capability of an entire organization
- **Company-level impact**: Your work affects Google as a whole (typically L7+)

Staff engineers (L6) typically operate at the multi-team level, with some org-level impact. Let's explore what each level looks like in practice.

## Team-Level Impact (Typical Senior)

At team level, impact is measured by contribution to your team's goals:
- Features shipped
- Bugs fixed
- Performance improved
- Technical debt paid down
- Team members mentored

This work is essential. Companies can't function without engineers doing excellent team-level work. A strong Senior engineer (L5) is characterized by consistent, reliable team-level impact.

**What team-level impact looks like**:
- "I implemented the new checkout flow, which improved conversion by 3%"
- "I reduced API latency from 200ms to 50ms"
- "I mentored two junior engineers who are now self-sufficient"
- "I paid down technical debt that was causing weekly on-call issues"

**What it doesn't look like**:
- Impact that extends beyond your team's direct work
- Systems or patterns adopted by other teams
- Influence on technical direction beyond your team's roadmap

## Multi-Team Impact (Typical Staff)

At multi-team level, impact extends beyond your immediate team:
- Your work enables or improves other teams' work
- You solve problems that would otherwise be solved separately by multiple teams
- You establish patterns or create tools that others adopt
- You influence technical decisions across team boundaries

This is the core of Staff-level impact. You're not just doing your job—you're multiplying the effectiveness of multiple teams.

**What multi-team impact looks like**:
- "I built a shared authentication library that four teams now use"
- "I identified an architectural problem affecting three services and drove a coordinated fix"
- "I established a design review process that improved quality across the product area"
- "I mentored the tech leads of two other teams on scaling challenges"

**The key distinction**: Multi-team impact isn't about working on a project that touches multiple teams. It's about having influence and effect on teams beyond your own, often without direct authority or project assignment.

**Example**: You notice that three teams are implementing similar retry logic with different (and sometimes wrong) approaches. You:
1. Research best practices for retry logic
2. Write a design doc proposing a shared library
3. Discuss with tech leads of the affected teams
4. Build (or coordinate building) the shared library
5. Help teams migrate to it
6. Document the patterns for future teams

This is multi-team impact. You identified a cross-team problem and solved it, improving outcomes for teams beyond your own.

## Org-Level Impact (Strong Staff / L7)

At org level, impact shapes the direction or capability of an entire organization (typically a collection of teams with a shared mission):
- You define technical strategy for a product area
- You drive architectural decisions that affect the whole org
- You establish standards and practices org-wide
- Your technical judgment shapes investment decisions

This is typically expected for L7 (Senior Staff), but strong L6 candidates often demonstrate some org-level impact, especially in their current role.

**What org-level impact looks like**:
- "I defined the three-year technical roadmap for the payments organization"
- "I drove the decision to migrate from monolith to microservices, affecting 15 teams"
- "I established the org's approach to observability and trained all teams on it"
- "I created the architectural review process that all major initiatives go through"

**The key distinction**: Org-level impact is about shaping direction, not just executing well. You're not just doing excellent work within the existing structure—you're influencing what the structure should be.

## How Impact Levels Show Up in Interviews

In a system design interview, your impact level shows up through:

### Problem Framing

**Team-level thinking**: "We need to build this service. Here's how I'd design it."

**Multi-team thinking**: "We need to build this service, but I notice it overlaps with what Team X is doing. Let me consider whether we should integrate with their system, build our own, or propose a shared solution."

**Org-level thinking**: "Before designing this service, let me understand the broader context. What's the product strategy? How does this fit with the organization's technical direction? Are we solving a one-off problem or establishing a pattern for the future?"

### Solution Design

**Team-level thinking**: Optimizes for the immediate problem. Designs a solution that works well for the specific use case.

**Multi-team thinking**: Considers reusability and broader applicability. Asks, "If I were solving this for three teams instead of one, how would the design change?"

**Org-level thinking**: Designs for extensibility and evolution. Thinks about how this solution fits into the larger technical landscape and how it enables future work.

### Tradeoff Discussion

**Team-level thinking**: Discusses tradeoffs in terms of implementation effort, performance, and reliability.

**Multi-team thinking**: Adds considerations like: "This approach is simpler for us, but it'll make Team X's integration harder" or "This pattern aligns with what other teams are doing, which reduces organizational complexity."

**Org-level thinking**: Includes strategic considerations: "This approach commits us to a certain architectural direction. Let me discuss the long-term implications..."

## Demonstrating Multi-Team Impact in Interviews

You can demonstrate multi-team thinking even when designing a system from scratch:

### Ask About Organizational Context
- "Are there other teams building similar systems that we should learn from or integrate with?"
- "Is this a one-off need or something multiple teams might want?"
- "What existing infrastructure should we build on vs. build fresh?"

### Consider Broader Implications
- "If we design it this way, other teams could potentially use it too"
- "This pattern is consistent with what [hypothetical other team] would need"
- "We should document this approach so other teams facing similar problems can benefit"

### Discuss Integration Points
- "The API design should be general enough that other consumers could use it"
- "We should think about how this interacts with [related system]"
- "The monitoring should integrate with the org's existing observability stack"

---

# Part 3: Ownership vs Leadership vs Influence

These three concepts are related but distinct. Understanding their differences is crucial for Staff-level performance.

## Ownership

Ownership means you're accountable for outcomes, not just activities. When you own something:
- You're responsible for its success or failure
- You don't wait to be told what to do—you figure it out
- You ensure problems get solved, even if you don't personally solve them
- You care deeply about the outcome, not just your contribution to it

**What ownership looks like at Staff level**:

A Senior engineer might own a component. They're responsible for its quality, reliability, and evolution. They fix bugs, add features, and keep it healthy.

A Staff engineer owns a problem space. They're responsible for ensuring the problem is solved well, regardless of which components or teams are involved. They might not write most of the code, but they ensure the right code gets written.

**Example**: A Senior engineer owns the notification service. They:
- Keep it running reliably
- Fix bugs quickly
- Add features as requested
- Improve performance over time

A Staff engineer owns notification delivery. They:
- Ensure notifications reach users reliably across all channels
- Coordinate work across the teams that touch notification flow
- Identify and resolve cross-cutting issues
- Set the technical direction for notification infrastructure
- May not personally write most of the code, but ensures it gets written well

### The Accountability Test

Here's a simple test: if something goes wrong in your area, do you feel responsible even if you didn't directly cause it?

**Senior-level accountability**: "I feel responsible for things I directly worked on."

**Staff-level accountability**: "I feel responsible for outcomes in my problem space, regardless of who touched the code."

A Staff engineer who owns notification delivery doesn't say, "The email team broke something—not my problem." They say, "Users aren't getting notifications. Let me understand what's happening and coordinate a fix."

## Leadership

Leadership means guiding others toward a goal. When you lead:
- You set direction for a group
- You align people around a common vision
- You make decisions (or facilitate making them)
- You remove obstacles for others
- You take responsibility for the group's success

**What leadership looks like at Staff level**:

Staff engineers lead without formal authority. They're not managers—they can't hire, fire, or assign work. Yet they lead technical initiatives, guide architectural decisions, and align engineers across teams.

**Example**: A Staff engineer leads a database migration:
- They develop the migration strategy
- They align stakeholders on the approach
- They break down the work and help teams plan
- They remove technical blockers
- They track progress and adjust the plan
- They communicate status to leadership
- They ensure the migration completes successfully

They might do some of the hands-on work, but their primary contribution is direction and coordination. Without their leadership, the migration would be chaotic, slow, or stalled.

### The Direction Test

Here's a simple test: if you left, would the initiative lose direction?

**Senior-level contribution**: If you left, your tasks wouldn't get done, but the initiative would continue with similar direction.

**Staff-level leadership**: If you left, the initiative would need someone else to step up and lead, or it would drift.

## Influence

Influence means shaping decisions and behaviors without direct control. When you influence:
- People consider your opinion even when you're not present
- Your patterns and practices are adopted by others
- Your technical judgment shapes decisions beyond your direct involvement
- You change how others think about problems

**What influence looks like at Staff level**:

Staff engineers build influence through credibility, communication, and consistency. Their influence extends beyond what they directly lead or own.

**Example**: A Staff engineer is known for thoughtful API design. Over time:
- Other engineers seek their review on API designs
- Their design patterns spread through the codebase
- New engineers are pointed to their work as examples
- Their opinions on API design are considered even when they're not in the room

They never mandated anything. They built influence through excellent work and clear communication.

### The Ripple Test

Here's a simple test: do your ideas spread beyond conversations you're directly part of?

**Senior-level impact**: Your ideas are implemented in your direct work.

**Staff-level influence**: Your ideas are adopted by others, even when you're not involved.

## How These Concepts Interact

Ownership, leadership, and influence aren't independent—they reinforce each other.

**Ownership builds credibility**: When you consistently own outcomes well, people trust your judgment. That trust becomes influence.

**Leadership creates visibility**: When you lead initiatives successfully, people across the organization learn who you are. That visibility creates opportunities for ownership and influence.

**Influence enables ownership**: When you have influence, you can take on broader ownership because people will follow your direction.

For Staff engineers, all three are expected:
- **Ownership**: Accountable for outcomes in a significant problem space
- **Leadership**: Driving technical initiatives across team boundaries
- **Influence**: Shaping decisions and practices beyond direct involvement

A candidate who demonstrates all three is showing Staff-level contribution. A candidate who demonstrates only one or two may be assessed as a strong Senior.

## Quick Reference: Ownership vs Leadership vs Influence

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   OWNERSHIP        LEADERSHIP         INFLUENCE                         │
│   ─────────        ──────────         ─────────                         │
│                                                                         │
│   "I'm accountable "I'm driving       "People follow my                 │
│    for this         this initiative"   patterns even when               │
│    outcome"                            I'm not involved"                │
│                                                                         │
│   TEST:            TEST:              TEST:                             │
│   If it fails,     If you left,       Do your ideas spread              │
│   do you feel      would it lose      beyond conversations              │
│   responsible?     direction?         you're part of?                   │
│                                                                         │
│   EXAMPLE:         EXAMPLE:           EXAMPLE:                          │
│   "Notifications   "I'm leading       "Teams use my API                 │
│   aren't being     the database       design patterns even              │
│   delivered—I'm    migration across   when I'm not                      │
│   investigating"   3 teams"           reviewing"                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Simple Self-Check: Am I Demonstrating Staff-Level Ownership?

Ask yourself these questions:

| Question | L5 Answer | L6 Answer |
|----------|-----------|-----------|
| What do you own? | "The recommendation service" | "User relevance outcomes" |
| When something breaks in your area, what do you do? | "Check if it's my code" | "Coordinate the fix regardless of whose code" |
| How do you describe your responsibility? | "I build features for X" | "I ensure X works well for users" |
| What happens when you go on vacation? | "My tasks wait" | "My ownership continues through docs/delegation" |

---

# Part 4: How Staff Engineers Drive Direction Without Authority

This is one of the most important skills for Staff engineers: getting things done when you can't simply tell people what to do.

## Why Authority Is Rare

At Google, formal authority is concentrated in management. Even engineering managers have limited authority—Google's culture emphasizes consensus and influence over command and control.

Staff engineers have essentially no formal authority. They can't:
- Assign work to engineers on other teams
- Mandate architectural decisions
- Force teams to adopt their proposals
- Hold people accountable through org charts

Yet they're expected to drive direction across teams. How?

## The Influence Toolkit

Staff engineers drive direction through a combination of tools:

### 1. Credibility

Credibility is the foundation. If people don't trust your judgment, nothing else works.

You build credibility through:
- **Track record**: Consistently making good decisions and delivering results
- **Technical depth**: Demonstrating expertise that others respect
- **Intellectual honesty**: Acknowledging uncertainty and changing your mind with evidence
- **Reliability**: Following through on commitments

**Example**: A Staff engineer has a reputation for excellent system design. When they propose an architectural change, engineers take it seriously because they've seen this person's proposals work out before. Their credibility shortcuts the persuasion process.

### 2. Clear Communication

Ideas don't spread themselves. You need to articulate your thinking clearly enough that others can understand, evaluate, and adopt it.

This means:
- **Written documents**: Design docs, proposals, and technical guides
- **Presentations**: Explaining ideas to groups of varying technical depth
- **Conversations**: 1:1 discussions that build understanding and buy-in
- **Code**: Working examples that demonstrate the idea

**Example**: A Staff engineer wants to change how the organization handles configuration. They:
- Write a detailed design doc explaining the problem, the proposal, and alternatives considered
- Present it at a tech talk, taking questions and feedback
- Have 1:1 conversations with skeptical tech leads
- Build a prototype that demonstrates the approach
- Write documentation that helps others adopt it

The communication is as important as the idea.

### 3. Relationship Building

Influence flows through relationships. People are more receptive to ideas from someone they know and respect than from a stranger.

Relationship building at Staff level means:
- **Knowing the key people**: Who are the tech leads, architects, and decision-makers in related areas?
- **Understanding their concerns**: What are they worried about? What are their priorities?
- **Being a resource**: How can you help them, not just get help from them?
- **Maintaining connections**: Regular check-ins, even when you don't need anything

**Example**: A Staff engineer maintains relationships with tech leads across the organization. When they need to drive a cross-team initiative, they already know who to talk to, what they care about, and how to frame proposals in terms that resonate.

### 4. Coalition Building

For significant changes, one person's influence isn't enough. You need to build coalitions.

This means:
- **Identifying stakeholders**: Who cares about this decision? Who will be affected?
- **Understanding interests**: What does each stakeholder want? Where are they aligned, and where do they conflict?
- **Finding common ground**: What framing or approach addresses multiple stakeholders' concerns?
- **Building support incrementally**: Starting with friendly stakeholders, then expanding

**Example**: A Staff engineer wants to consolidate three logging systems into one. They:
- Talk to each team that owns a logging system to understand their concerns
- Identify a few engineers on each team who are frustrated with fragmentation
- Work with these allies to draft a joint proposal
- Bring the proposal to tech leads with preliminary buy-in from engineers
- Facilitate discussions to resolve remaining concerns
- Build enough consensus that the consolidation moves forward

They never had authority to mandate consolidation. They built a coalition that made it happen.

### 5. Problem Framing

How you frame a problem shapes what solutions seem reasonable. Staff engineers are skilled at framing problems in ways that make their preferred direction seem natural.

This isn't manipulation—it's clarity. Often the "right" answer becomes obvious when you frame the problem correctly.

**Example**: 

Poor framing: "Should we use Kafka or RabbitMQ for the message queue?"

Better framing: "We need reliable message delivery with at-least-once semantics at 100K messages/second with low latency. Given those requirements, which technology is the best fit?"

The first framing invites a technology debate. The second framing focuses on requirements, which may make the choice clear—or may reveal that the choice doesn't matter as much as how you configure it.

### 6. Data and Evidence

Arguments backed by data are more compelling than arguments backed by opinion. Staff engineers gather evidence to support their proposals.

This includes:
- **Metrics**: Performance data, error rates, usage patterns
- **Case studies**: Examples from other teams or companies
- **Prototypes**: Working demonstrations of the proposed approach
- **Analysis**: Written evaluation of options with clear criteria

**Example**: A Staff engineer wants to change the team's testing strategy. Instead of saying "I think we should do more integration testing," they:
- Analyze the past year's bugs to categorize root causes
- Show that 60% of production issues would have been caught by integration tests
- Estimate the engineering time spent on debugging vs. the time that integration tests would require
- Propose a specific testing strategy with expected outcomes

The data makes the argument.

### 7. Organizational Patience

Influence takes time. Ideas that seem obvious to you may take months to gain traction. Staff engineers have patience.

This means:
- **Planting seeds**: Introducing ideas before you need decisions
- **Letting others discover**: Sometimes people need to find the problem themselves before they're receptive to solutions
- **Iterating on proposals**: Incorporating feedback and improving over time
- **Accepting partial progress**: Getting 60% of what you wanted this quarter and the rest next quarter

**Example**: A Staff engineer believes the organization should adopt a new infrastructure approach. They:
- Mention the idea informally in conversations
- Write a blog post about the general concept
- Do a small pilot on their own team
- Present results to a wider group
- Propose a broader rollout
- Work through concerns incrementally
- Eventually, the organization adopts the approach—nine months after the first conversation

## Driving Direction in Interviews

In interviews, you can demonstrate this capability through:

### How You Handle Interviewer Pushback

When the interviewer challenges your design, do you:
- Defend your position rigidly? (Weak)
- Immediately abandon your position? (Weak)
- Explore the interviewer's concern, integrate valid points, and either adjust your position or explain why you still prefer your original approach? (Strong)

The third approach shows you can drive direction through discussion rather than authority.

### How You Propose Tradeoffs

Do you present tradeoffs as:
- "We could do A or B" and wait for the interviewer to decide? (Weak)
- "A is better, end of discussion"? (Weak)
- "Given our requirements, I recommend A because [reasons], though B would be better if [different priorities]"? (Strong)

The third approach shows you can drive direction while remaining open to input.

### How You Frame Problems

Do you accept the problem as stated and solve it? (Fine for Senior)

Or do you reframe the problem, question assumptions, and clarify what problem is really worth solving? (Staff-level)

## Quick Example: Driving Direction Without Authority

**Situation**: You believe the team should adopt a new testing approach.

**Approach WITH Authority** (Manager):
> "We're switching to integration tests. I've assigned tickets to everyone."

**Approach WITHOUT Authority** (Staff Engineer):
> 1. Analyze data: "60% of our prod bugs would've been caught by integration tests"
> 2. Build credibility: Run a pilot on your own code, show results
> 3. Write a proposal: Document the approach, tradeoffs, migration path
> 4. Get buy-in: Discuss with skeptics 1:1, address concerns
> 5. Build coalition: Get 2-3 allies who agree
> 6. Propose to team: Present with data, allies, and a concrete plan
> 7. Support adoption: Help others, iterate based on feedback

The second approach takes longer but creates **durable change with genuine buy-in**.

---

# Part 5: Examples of Staff-Level Ownership in System Design

Let me walk through concrete examples of how Staff-level ownership manifests in system design work.

## Example 1: The Cross-Service Reliability Problem

**The Situation**: A user-facing product has reliability issues. Users complain about errors, but no single team can identify the cause because requests flow through multiple services owned by different teams.

**Senior-Level Response**: A Senior engineer on one of the teams investigates their service, confirms it's behaving correctly, and reports: "Not our problem." Each team does the same. The reliability issue persists.

**Staff-Level Response**: A Staff engineer notices the pattern and takes ownership of the end-to-end reliability, even though no single service is theirs:
- They instrument the request flow across all services
- They identify that errors correlate with timing: when Service A is slow, Service B times out, causing cascading failures
- They propose changes to timeout configurations and circuit breaker patterns
- They work with all three teams to implement the changes
- They establish cross-service monitoring to catch similar issues in the future

The Staff engineer owned the outcome (user-facing reliability) rather than a component (their team's service).

**In an Interview**: If given a system design problem, a Staff-level candidate would naturally consider cross-service interactions and failure modes, not just the component they're designing.

## Example 2: The Undifferentiated Heavy Lifting

**The Situation**: Multiple teams are building similar authentication wrappers, each slightly different and each with its own bugs.

**Senior-Level Response**: A Senior engineer builds a good authentication wrapper for their team. If they're particularly thoughtful, they might mention to a colleague that they solved the same problem.

**Staff-Level Response**: A Staff engineer recognizes the organizational waste:
- They survey the existing implementations across teams
- They identify common requirements and edge cases
- They design a shared library that handles 90% of use cases
- They socialize the proposal with affected teams
- They build the library (or coordinate building it)
- They help teams migrate and deprecate their custom implementations
- They maintain the library or establish shared ownership

The Staff engineer saw a multi-team problem and solved it at the right level.

**In an Interview**: When designing authentication for a system, a Staff-level candidate might ask: "Is this authentication pattern specific to this service, or is it something other services need too? Should I design this as a reusable component?"

## Example 3: The Long-Term Sustainability

**The Situation**: A system works well today but has architectural limitations that will cause problems at 10x scale.

**Senior-Level Response**: A Senior engineer flags the concern in planning discussions. They might create a tech debt ticket. But they focus on current work—after all, the system works today.

**Staff-Level Response**: A Staff engineer owns the long-term sustainability:
- They quantify when the architectural limits will be hit based on growth projections
- They propose a migration path that can be executed incrementally alongside feature work
- They design the new architecture to avoid similar limitations
- They create a phased roadmap that balances current delivery with future sustainability
- They advocate for resourcing the migration and get leadership buy-in
- They track progress and adjust the plan as circumstances change

The Staff engineer owned not just today's system but tomorrow's.

**In an Interview**: A Staff-level candidate would naturally discuss scaling limits: "This design works for our current scale. When we hit [threshold], we'll need to [change]. Let me design the initial system so that migration is straightforward."

## Example 4: The Operational Excellence

**The Situation**: A system has recurring on-call pain—not catastrophic outages, but frequent alerts, confusing runbooks, and late-night pages.

**Senior-Level Response**: A Senior engineer responds to on-call events effectively. They might improve a runbook or fix a bug that caused a page. They're good at fighting fires.

**Staff-Level Response**: A Staff engineer attacks the root causes:
- They analyze on-call patterns: what pages repeatedly? What takes longest to diagnose?
- They identify systemic issues: alerting on symptoms rather than causes, missing monitoring, architectural fragility
- They propose and prioritize improvements that reduce on-call burden
- They lead a project to implement the most impactful improvements
- They measure the result: fewer pages, faster resolution, happier on-call

The Staff engineer owned operational excellence as a problem space, not just individual incidents.

**In an Interview**: A Staff-level candidate would discuss operational concerns proactively: "For monitoring, I'd instrument [specific metrics] and alert on [specific conditions]. Here's how I'd design the runbooks for common scenarios..."

## Example 5: The Mentorship and Capability Building

**The Situation**: A team has several junior-to-mid engineers who are productive but not growing into senior roles.

**Senior-Level Response**: A Senior engineer mentors one or two individuals. They do good code reviews. They're helpful when people have questions.

**Staff-Level Response**: A Staff engineer thinks about capability building systemically:
- They identify growth areas for the team as a whole
- They design stretch opportunities that develop specific skills
- They create learning resources (documents, workshops, design exercises)
- They give feedback that's targeted at development, not just correctness
- They gradually increase the complexity of what they delegate
- They track how engineers are developing and adjust their approach

The Staff engineer owned the team's capability growth, not just individual mentorship moments.

**In an Interview**: A Staff-level candidate's designs often include considerations like: "This component could be a good stretch assignment for a more junior engineer with some guidance..."

---

# Part 6: How Scope Shows Up Implicitly in Interviews

Interviewers don't ask: "Tell me about your scope." But they're evaluating your scope constantly through indirect signals.

## Signal 1: How You Frame the Problem

**Narrow scope**: Takes the problem as stated, asks a few clarifying questions, and dives into solution.

**Broad scope**: Explores the problem space. Asks about related systems, organizational context, and long-term goals. Considers whether this is the right problem to solve.

**Example**:

Interviewer: "Design a notification system."

Narrow scope candidate: "Okay, so we need to send notifications to users. How many users do we have? What's the notification rate?"

Broad scope candidate: "Before I dive in, I'd like to understand the context. Is this a new system or replacing something existing? What's driving this need? Are there other systems that do similar things we should consider integrating with or learning from? What's the organization's long-term vision for user communication?"

## Signal 2: Where You Draw Boundaries

**Narrow scope**: Designs within the stated boundaries. If told "design Service X," designs exactly Service X with clean interfaces.

**Broad scope**: Questions boundaries. "I noticed that Service X would need to interact heavily with Service Y. Would it make sense to combine them, or should I design for a clean interface? What are the team boundaries here?"

**Example**:

Interviewer: "Design a caching layer for the product database."

Narrow scope candidate: Designs a caching layer. Clean, efficient, well-considered.

Broad scope candidate: "Before I design the caching layer, let me ask: is caching the right solution? Sometimes caching is a band-aid for an underlying performance problem. Have we considered whether the query patterns could be optimized at the database level? Or whether the data model could be restructured? Assuming caching is the right approach, let me think about the scope: are we caching just for this product, or could other products benefit from a shared caching infrastructure?"

## Signal 3: What Future States You Consider

**Narrow scope**: Designs for current requirements. Mentions scaling as an afterthought.

**Broad scope**: Designs with multiple time horizons. Explicitly discusses how the system evolves as requirements change.

**Example**:

Narrow scope candidate: "This design handles our current 10K QPS. If we need more, we can add more servers."

Broad scope candidate: "For our current 10K QPS, this design works well with two replicas. At 100K QPS, we'll need to shard the data—I've designed the key structure to support that. At 1M QPS, we might want to consider a fundamentally different approach like CQRS. Let me talk about the migration path between these states..."

## Signal 4: What Stakeholders You Consider

**Narrow scope**: Designs for the primary user. Considers the happy path.

**Broad scope**: Considers multiple stakeholders: end users, operators, other engineering teams, product managers, compliance requirements.

**Example**:

Narrow scope candidate: "The API returns user data in JSON format. Here's the schema."

Broad scope candidate: "For the API, I need to consider several audiences. End users need low latency and a clean response format. The mobile team has bandwidth constraints, so we might want a compressed option. The analytics team will want to export bulk data, so we need a different API for that. The compliance team will want audit logs. Let me prioritize these and start with the core user-facing API..."

## Signal 5: How You Handle Adjacent Problems

**Narrow scope**: Acknowledges adjacent problems but stays focused. "That's a concern, but it's out of scope."

**Broad scope**: Engages with adjacent problems. "That's related to our design. Let me think about how our decisions here affect that problem, and vice versa."

**Example**:

Interviewer: "What about the case where user data changes while a notification is in flight?"

Narrow scope candidate: "The user service would need to handle that. We'd just send whatever data we have at the time of notification creation."

Broad scope candidate: "That's an interesting cross-service consistency challenge. We have a few options. We could accept stale data—if a name change takes 30 seconds to reflect in notifications, that's probably okay. We could delay notification processing briefly and fetch fresh data. We could implement event-driven updates so we get notified of changes. The choice depends on how often data changes and how sensitive it is. Let me think about what makes sense for our use case..."

## Quick Interview Example: Narrow vs Broad Scope

**Question**: "Design a caching layer for the product catalog."

**Narrow Scope Response** (L5):
> "I'll use Redis with a write-through cache. Keys will be product IDs, values will be product JSON. TTL of 5 minutes. Cache invalidation on product updates."

*Analysis*: Correct, but limited to the stated problem.

**Broad Scope Response** (L6):
> "Before I design the cache, a few questions:
> - Is caching the right solution, or is this masking a DB performance issue we should fix?
> - Are other services also caching product data? Should we have a shared cache?
> - What's the consistency requirement? Some use cases (checkout) need fresh data; others (browsing) can tolerate staleness.
> 
> Assuming caching is right, I'd design it as a reusable service that other teams can use, with configurable consistency levels..."

*Analysis*: Questions the premise, considers broader patterns, designs for reuse.

## Signal 6: How You Talk About Tradeoffs

**Narrow scope**: Discusses tradeoffs in terms of technical merits. "Approach A is faster, Approach B is simpler."

**Broad scope**: Discusses tradeoffs in terms of broader impact. "Approach A is faster, which matters for user experience. Approach B is simpler, which matters for team velocity and maintainability. Given our team's current priorities..."

**Example**:

Narrow scope candidate: "We could use SQL for strong consistency or NoSQL for better scaling."

Broad scope candidate: "The database choice has several dimensions. SQL gives us strong consistency and familiar tooling—our team has deep SQL expertise, which reduces risk. NoSQL could scale more easily, but would require the team to learn new patterns and tooling. Given that we're not at the scale where SQL struggles, and that team productivity matters for our roadmap, I'd start with SQL and plan for a migration path if we hit scaling limits."

---

# Part 7: Clear Mental Models for Scope, Impact, and Ownership

Let me consolidate what we've covered into mental models you can apply.

## Mental Model 1: The Ripple Effect

Imagine dropping a stone into water. The ripples spread outward from the point of impact.

- **L5 (Senior)**: Your stone creates ripples that reach the edge of your pond (team). Occasionally, a ripple crosses to an adjacent pond.
- **L6 (Staff)**: Your stone creates ripples that regularly cross pond boundaries. Other ponds are affected by what you do.
- **L7 (Senior Staff)**: You're not dropping stones into ponds—you're affecting the water table that feeds all the ponds.

Apply this to your work: How far do the ripples of your contributions travel?

## Mental Model 2: The Problem vs. Solution Ownership

- **L5**: Owns solutions. Given a problem, you produce an excellent solution. You're evaluated on solution quality.
- **L6**: Owns problems. You identify what problems need solving, not just how to solve them. You're evaluated on whether the right problems get solved well.

Apply this to your work: Do you wait for problems to be handed to you, or do you identify problems worth solving?

## Mental Model 3: The Zoom Levels

Imagine a camera that can zoom in and out:

- **Zoomed in (L5)**: You see your code, your component, your immediate context. You excel at this level of detail.
- **Zoomed out (L6)**: You see the system, the organization, the multi-year trajectory. You can operate at this level effectively.
- **All zoom levels (L6+)**: You move fluidly between zoom levels, understanding how decisions at one level affect others.

Apply this to your work: How often do you zoom out? Can you reason about the big picture without losing grasp of the details?

## Mental Model 4: The Builder vs. Architect Spectrum

This is a spectrum, not a binary:

- **Pure Builder**: Given a blueprint, you build it excellently. You don't question the blueprint; you execute it.
- **Pure Architect**: You design blueprints but don't build. You're disconnected from construction realities.
- **Staff Engineer**: You're somewhere in the middle—you architect when needed, build when needed, and understand the connection between the two. You don't just design; you ensure designs become reality.

Apply this to your work: Do you balance design and execution? Can you move between them fluidly?

## Mental Model 5: The Leverage Multiplier

Think about leverage—doing things that multiply your output:

- **1x leverage**: Your impact is proportional to your effort. More hours = more output.
- **10x leverage**: Your impact multiplies through others. Something you do enables many people to be more effective.
- **100x leverage**: Your impact shapes systems or organizations. Something you do changes how a group operates at a fundamental level.

Staff engineers consistently find 10x+ leverage opportunities: building reusable tools, establishing patterns that spread, solving problems once that would otherwise be solved many times poorly.

Apply this to your work: What's the highest-leverage work you could be doing?

---

# Part 8: Comparison with Senior Engineer Expectations

To make the Staff expectations concrete, let's compare them directly with Senior expectations.

| Dimension | Senior (L5) | Staff (L6) |
|-----------|-------------|------------|
| **Scope of Ownership** | Components, features, well-defined projects | Problem spaces, multi-component systems |
| **Planning Horizon** | Current quarter, next quarter | One year, two-plus years |
| **Sphere of Influence** | Team, immediate collaborators | Multiple teams, organization |
| **Problem Sourcing** | Problems are given to you | You identify which problems need solving |
| **Decision Authority** | Decisions within your component | Decisions with cross-team implications |
| **Failure Accountability** | Accountable for your component's failures | Accountable for outcomes in your problem space |
| **Mentorship** | Mentor individuals | Develop team capability |
| **Communication** | Clear technical communication to team | Clear communication across audiences and levels |
| **Conflict Resolution** | Escalate when stuck | Resolve conflicts across team boundaries |
| **Technical Depth** | Deep in your domain | Deep in multiple areas, broad across many |

### Concrete Comparison Examples

**Situation: A production issue is discovered**

- Senior: Investigate if it's in their area. Fix it if it is, escalate if it isn't.
- Staff: Assess severity and coordinate response regardless of whose code it is. Ensure post-mortem happens and systemic fixes are implemented.

**Situation: A new project needs design**

- Senior: Given a project, produce a thorough design doc and implement it.
- Staff: Identify whether this project is the right approach. Explore alternatives. Consider interaction with other teams' work. Design for the broader context.

**Situation: Two teams have conflicting approaches**

- Senior: Express their opinion, defer to leadership or let teams work it out.
- Staff: Facilitate discussion. Understand both perspectives. Find common ground or make a recommendation. Drive resolution.

**Situation: A technology choice needs to be made**

- Senior: Evaluate technologies for their team's needs. Make a recommendation.
- Staff: Evaluate technologies for multiple teams' needs. Consider organizational factors (expertise, maintenance, consistency). Drive alignment across teams.

---

# Brainstorming Questions

Use these questions to reflect on your own experience and prepare for interviews.

## Understanding Your Scope

1. What is the largest "blast radius" of a technical decision you've made? How many teams or systems were affected?

2. When was the last time you identified a problem that wasn't explicitly assigned to you and drove its resolution? What was it?

3. What systems or components do people outside your team come to you for advice about?

4. How far into the future does your current technical planning extend? One quarter? One year? Longer?

5. If you left your current role, what would break that isn't a specific component you maintain?

## Understanding Your Impact

6. What work have you done that affected teams other than your own? How did you drive it without formal authority?

7. What patterns, tools, or practices have you established that others have adopted? How did that adoption happen?

8. Can you quantify the multiplier effect of your work? How many engineers does it make more effective, and by how much?

9. What organizational problems (not just technical ones) have you solved or improved?

10. What's the most significant tradeoff you've navigated that involved multiple teams or stakeholders?

## Understanding Your Ownership

11. What do you own that you weren't explicitly assigned? How did you come to own it?

12. When was the last time you felt responsible for something that broke, even though you didn't directly cause it?

13. What would you do if you discovered a critical problem in an area adjacent to your official responsibility?

14. How do you stay aware of what's happening in related areas, beyond your direct work?

15. What's the hardest decision you've made where you had to commit despite incomplete information?

---

# Reflection Prompts

Set aside 15-20 minutes for each of these reflection exercises.

## Reflection 1: Your Scope Evolution

Think back over the past 2-3 years of your career.

- How has your scope evolved? Be specific about the dimensions: technical scope, temporal scope, organizational scope.
- What events or decisions led to scope expansion? What did you do to make them happen?
- What opportunities for scope expansion have you missed? Why?
- What's currently limiting your scope? What could you do about it?

Write down three specific actions you could take in the next quarter to expand your scope.

## Reflection 2: Your Influence Inventory

Think about the technical decisions and practices in your organization.

- Which ones did you directly influence? How?
- Which ones do you disagree with but didn't try to change? Why not?
- What ideas do you have that haven't gained traction? What would it take to build support?
- Who are the key people you'd need to influence for your ideas to spread?

Map out an influence campaign for one idea you think is important.

## Reflection 3: Ownership Gaps

Think about the systems and problems you care about.

- What aspects of these are owned clearly? By whom?
- What aspects fall between the cracks—things that nobody is clearly accountable for?
- Which of these gaps could you fill? What would it take?
- What's stopping you from owning more? Is it legitimate constraints or self-imposed limits?

Identify one ownership gap you could step into, and write a short plan for doing so.

## Reflection 4: Your Staff Readiness

Based on what you've read, assess your own readiness for Staff level.

- On a scale of 1-10, how would you rate yourself on technical scope?
- On a scale of 1-10, how would you rate yourself on multi-team impact?
- On a scale of 1-10, how would you rate yourself on driving direction without authority?
- On a scale of 1-10, how would you rate yourself on ownership of problem spaces?

For each dimension where you rated yourself below 7, identify the specific gap and what experience would help you close it.

---

# Homework Exercises

## Exercise 1: The Scope Map

Create a visual map of your current scope.

1. Draw yourself in the center
2. Draw the components/systems you directly own
3. Draw adjacent systems you interact with
4. Draw systems that you influence but don't own
5. Draw systems that affect you but that you don't influence

Look at the map:
- Is your scope concentrated or distributed?
- Where are the opportunities for expansion?
- What relationships do you need to build?

## Exercise 2: The Impact Journal

For the next two weeks, keep an impact journal.

Each day, write down:
- What work did you do?
- What was the immediate output?
- What was the ripple effect beyond the immediate output?
- Who did it help besides yourself?

At the end of two weeks, review:
- How much of your work had multi-team impact?
- What patterns do you see?
- What could you do differently to increase leverage?

## Exercise 3: The Ownership Audit

Pick a problem space you care about (e.g., "API reliability," "Developer productivity," "User onboarding").

Write a one-page ownership audit:
- What's the current state of this problem space?
- Who owns which aspects currently?
- What aspects are unowned or under-owned?
- What would it look like if you owned the whole problem space?
- What would you do in the first 30 days of owning it?

## Exercise 4: The Influence Campaign

Pick a technical change you believe the organization should make.

Write a short influence campaign plan:
- What's the change you want?
- Who needs to be persuaded?
- What are their concerns and how will you address them?
- What evidence or proof points will you gather?
- What's your timeline for building support?
- What's your plan if you face resistance?

## Exercise 5: The Staff-Level Redesign

Take a system design problem you've solved before (or a practice problem).

Redesign it with explicit Staff-level thinking:
- Spend more time on problem exploration
- Consider cross-team implications explicitly
- Discuss 1-year and 3-year evolution
- Address operational excellence in depth
- Consider how you'd build organizational support for the approach

Compare the two designs. What's different about Staff-level thinking?

## Exercise 6: The Mentorship Scaling Exercise

Think about a skill or knowledge area where you're an expert.

Design a scalable capability-building plan:
- How do you currently share this expertise? (1:1 mentoring, answering questions, etc.)
- What would it look like to share it at 10x scale? (Documentation, workshops, etc.)
- What would it look like to share it at 100x scale? (Tools, processes, organizational practices)
- Pick one level-up and create a plan to execute it

---

# Conclusion

Scope, impact, and ownership are the currency of Staff-level contribution. They're not granted by job titles or project assignments—they're created through initiative, credibility, and consistent excellent judgment.

Understanding these concepts intellectually is the easy part. Embodying them in your daily work—and demonstrating them in interviews—is the challenge.

As you continue preparing:
- Look for opportunities to expand scope in your current role
- Seek out multi-team impact, even when it's not required
- Take ownership of problem spaces, not just components
- Practice driving direction through influence, not authority

The interview is a performance, but it's a performance of something real. The best way to perform Staff-level thinking in an interview is to practice Staff-level thinking in your work.

---

# Quick Reference Card

## Phrases That Signal Staff-Level Scope

**For Demonstrating Broad Scope:**
- "Before I solve this, let me understand the broader context..."
- "I notice this affects Team X too. Should we coordinate?"
- "This is a pattern I've seen in three places. Maybe we need a shared solution."
- "This works for now, but in 18 months when we hit X scale..."

**For Demonstrating Ownership:**
- "I own [problem space], not just [component]."
- "Even though it's not my code, I feel responsible for the outcome."
- "Let me coordinate the fix across teams."
- "I'll make sure this gets resolved."

**For Driving Direction:**
- "I've analyzed the data, and here's what I recommend..."
- "I've talked to the affected teams, and here's the common ground..."
- "Let me propose a path forward and get your feedback."
- "I think we should do X because [evidence]. What am I missing?"

## Impact Level Quick Reference

| Level | Typical Impact | Example |
|-------|----------------|---------|
| **Team** | Improves your team's work | "I reduced our build time by 50%" |
| **Multi-team** | Improves multiple teams | "I built a shared auth library 4 teams use" |
| **Org** | Shapes organizational direction | "I defined the testing strategy for the org" |

## The 3 Tests for Staff-Level Contribution

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   THE OWNERSHIP TEST                                                    │
│   If something breaks in your area, do you feel responsible             │
│   even if you didn't directly cause it?                                 │
│                                                                         │
│   THE RIPPLE TEST                                                       │
│   Do your ideas spread beyond conversations you're part of?             │
│                                                                         │
│   THE DIRECTION TEST                                                    │
│   If you left, would the initiative lose direction?                     │
│                                                                         │
│   All 3 YES = Staff-level. 1-2 YES = Strong Senior. 0 = Keep growing.   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## One-Page Summary: Senior vs Staff Scope

```
SENIOR (L5) SCOPE                STAFF (L6) SCOPE
──────────────────────           ──────────────────────

✓ Owns component                 ✓ Owns problem space
✓ Plans this quarter             ✓ Plans 1-2 years ahead
✓ Influences team                ✓ Influences multiple teams
✓ Solves given problems          ✓ Identifies which problems to solve
✓ Accountable for code           ✓ Accountable for outcomes
✓ Respected by teammates         ✓ Consulted across org
✓ Mentors individuals            ✓ Builds team capability
✓ Escalates blockers             ✓ Resolves cross-team conflicts
```

## Common Mistakes When Demonstrating Scope

| Mistake | Fix |
|---------|-----|
| "That's not my area" | Own the outcome, coordinate the fix |
| Waiting for scope to be assigned | Create scope through initiative |
| Going deep on your component only | Reason about the whole system |
| Only thinking about today's problem | Discuss 1-year and 3-year implications |
| Designing for just your team | Ask "Could other teams use this?" |
| Describing what you built | Describe the outcomes you enabled |

---

*End of Volume 1, Section 2*