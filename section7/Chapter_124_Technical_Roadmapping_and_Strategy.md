# Chapter 124 — Technical Roadmapping and Engineering Strategy

> *"A roadmap is not a promise. It's a shared understanding of what we're trying to accomplish and why — updated as we learn."*

---

```
┌──────────────────────────────────────────────────────────────────────────────┐
│           AT-A-GLANCE: TECHNICAL ROADMAPPING AND ENGINEERING STRATEGY       │
├──────────────────────────────────────────────────────────────────────────────┤
│  WHAT IT IS      A technical roadmap is a time-sequenced plan of            │
│                  engineering work that connects to business goals.           │
│                  It answers: what are we building, in what order, and why.  │
│                                                                              │
│  WHY IT MATTERS  Without a roadmap, teams react to requests.                │
│                  With a roadmap, teams invest in the right things at        │
│                  the right time — before the house is on fire.              │
│                                                                              │
│  THE TENSION     Feature work (visible to product/users) vs.                │
│                  foundational work (invisible until you need it).           │
│                  Roadmapping is the art of doing both without neglecting    │
│                  either.                                                     │
│                                                                              │
│  KEY ARTIFACTS   Technical strategy doc, quarterly roadmap, tech debt        │
│                  inventory, investment ratios (70/20/10 rule).              │
│                                                                              │
│  L5 SIGNAL       Builds a team-level roadmap. Aligns it with product.      │
│                  Can make the case for foundational investment with data.   │
│  L6 SIGNAL       Drives org-level technical strategy across teams.         │
│                  Shapes how the company allocates engineering capacity.     │
│                  Writes the multi-year technical vision.                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: What Is a Technical Roadmap (and What It Isn't)

*(Intern → L3 level)*

When you're a new engineer, someone else decides what you work on. As you become more senior, you start contributing to those decisions. At L5, you're expected to help shape what your team works on — not just sprint-to-sprint, but quarter-to-quarter and year-to-year.

A technical roadmap is the answer to: "What engineering work will this team do over the next N months, and why?"

**What a roadmap is:**

```
✅ A prioritized list of engineering work tied to goals
✅ A communication tool for stakeholders outside engineering
✅ A forcing function to make trade-offs explicit
✅ A shared understanding that gets updated as reality changes
✅ A planning horizon: usually 1-4 quarters out
```

**What a roadmap is NOT:**

```
❌ A promise (it will change)
❌ A detailed project plan (that's a sprint plan)
❌ An exhaustive list of every task
❌ A list of technologies you want to try
❌ A document you write once and never update
```

**The planning horizons:**

```
HORIZON 1: Now (current sprint / 2 weeks)
  What are we working on this sprint?
  Owned by: engineers + tech lead
  Granularity: individual tasks, story points

HORIZON 2: Near-term (current quarter / 3 months)
  What are we delivering this quarter?
  Owned by: engineering manager + senior engineers
  Granularity: projects, milestones

HORIZON 3: Mid-term (next 2-4 quarters / 6-12 months)
  What major initiatives are planned?
  Owned by: staff engineer + EM + product
  Granularity: initiatives, not tasks

HORIZON 4: Long-term (1-3 years)
  What is the technical vision?
  Owned by: staff/principal engineer + engineering leadership
  Granularity: directions, not dates
```

At L5, you own Horizon 2 and contribute to Horizon 3. At L6, you drive Horizon 3 and shape Horizon 4.

**Why many teams don't have a roadmap:**

```
"We move too fast for a roadmap." → Actually: you're reacting, not planning.
"Product changes too often." → A roadmap absorbs change; it's not rigidity.
"We don't know far enough ahead." → Plan at the right granularity — not tasks,
                                     initiatives. Initiatives are stable; tasks aren't.
"Nobody asked for one." → At L5, you propose it. You don't wait to be asked.
```

**Brainstorming Questions:**
1. Your team has never had a written technical roadmap. The EM says "we just respond to product requests." What arguments would you make for starting one? What concerns would you address?
2. What's the difference between a roadmap and a sprint backlog? Could you combine them into one artifact? What would you lose?
3. At what point does "the roadmap changed" become a warning sign vs. a healthy adaptation?
4. Who should own the technical roadmap — the EM, the tech lead, the product manager, or someone else? What does each perspective contribute?

---

## Part 2: The Core Tension — Feature Work vs. Foundational Work

*(L3 → L4 level)*

Every engineering team faces this tension: the product team wants features shipped. The engineering team knows the infrastructure is showing cracks. You can't do both simultaneously at full speed. Roadmapping is fundamentally the art of managing this tension.

**The two types of work:**

```
FEATURE WORK                          FOUNDATIONAL WORK
─────────────────────────────────     ──────────────────────────────────────
Visible to users                      Invisible to users
Appears on product roadmap            Rarely appears on product roadmap
Stakeholders request it               Engineers discover the need for it
Value is easy to measure              Value is hard to quantify
Gets prioritized in meetings          Gets deprioritized in meetings
Fast feedback loop (user reactions)   Long feedback loop (future leverage)
───────────────────────────────────   ──────────────────────────────────────
Example: new checkout flow            Example: migrating to a new DB
Example: adding notifications         Example: extracting a shared service
Example: improving search results     Example: rewriting a slow API
```

**The debt spiral:**

If a team does 100% feature work for 18 months, the codebase accumulates technical debt. Engineers start working slower as everything is tangled. Features take longer to build. More bugs appear. The team is slower, which means fewer features shipped. The product team wants more features, so they push harder on the team, which means the team has even less time for foundational work. This is the debt spiral.

```
    100% feature work
          │
          ▼
    Technical debt accumulates
          │
          ▼
    Each feature takes longer
          │
          ▼
    Fewer features shipped
          │
          ▼
    "Ship faster!" pressure from product
          │
          ▼
    Even less time for foundational work ← ─ ─ ─ ┐
          │                                       │
          └─────────────────────────────────────→ spiral
```

**The investment ratio:**

A common framework for managing this tension: the **70/20/10 rule**.

```
70% — Feature work and product-requested engineering
      (building new things, growing the product)

20% — Foundational / technical debt work
      (making the existing system better: performance, reliability,
       maintainability, developer productivity)

10% — Exploration and innovation
      (PoCs, learning, prototypes that may become future features)
```

This ratio is a starting point, not a law. Teams in a heavy debt situation might do 50/40/10 for a quarter. Teams in a maintenance phase might do 40/50/10.

**Making the ratio explicit:**

The power of naming the ratio: it creates a shared agreement that foundational work IS scheduled, not just hoped for. Without it, every planning meeting defaults to "what new features can we build?"

```
Without explicit ratio:
  Planning meeting: "We have 10 engineer-weeks this quarter."
  Product: "We need features A, B, C, D, E — all are urgent."
  Engineering: "But we also need to migrate the database."
  Product: "Features first, database next quarter."
  [Next quarter: same conversation]

With explicit ratio:
  Planning meeting: "We have 10 engineer-weeks. 70% = 7 for features,
                     20% = 2 for foundational, 10% = 1 for exploration."
  Product: "OK, we get 7 weeks of feature capacity. Which features?"
  Engineering: "And we're committing 2 weeks to the database migration."
  [The foundational work is planned, not negotiated every meeting]
```

**Brainstorming Questions:**
1. Your team is under heavy product pressure. The EM proposes going to 90% feature work "just this quarter." What are the risks? How would you evaluate whether this is acceptable?
2. How do you quantify the cost of technical debt to a product manager who doesn't think in code? What metrics or stories would make the argument land?
3. The 70/20/10 ratio means foundational work never gets > 20% of engineering time. Are there situations where you'd argue for temporarily inverting this? What conditions justify 50% foundational work?
4. How do you distinguish "foundational work" from "gold-plating"? What's the difference between necessary investment and over-engineering?

---

## Part 3: Building the Quarterly Roadmap

*(L4 level)*

A quarterly roadmap is a 3-month plan for an engineering team. It's the most actionable planning artifact — specific enough to guide work, broad enough to adapt as things change.

**The inputs to a quarterly roadmap:**

```
1. PRODUCT ROADMAP
   What features/initiatives does product want this quarter?
   This is the primary input — engineering doesn't operate in isolation.
   But it's an INPUT, not a dictation — engineering responds with capacity
   estimates and trade-offs, not just "yes" to everything.

2. TECHNICAL DEBT INVENTORY
   What are the top technical liabilities that are slowing the team down?
   (Failing on-call alerts, slow build times, brittle tests, scaling limits)
   Engineers maintain this list. Staff engineers synthesize it into
   a prioritized set of investments.

3. RELIABILITY AND INCIDENT HISTORY
   What broke in the last quarter? What caused the most on-call pain?
   Reliability work earns its place in the roadmap by pointing at real pain.

4. ENGINEERING CAPACITY
   How many engineer-weeks are available? (Account for: vacations, interviews,
   on-call rotation, unplanned work — usually 10-20% of capacity)

5. DEPENDENCIES
   What work requires other teams to complete first?
   What work blocks other teams?
   Dependencies are the most common reason roadmaps slip.
```

**The quarterly roadmap format:**

```markdown
## Team: [Name] — Q3 2026 Roadmap
Updated: 2026-06-25 | Owner: [Staff Engineer + EM]

### Capacity
Total: 12 engineer-weeks
  Feature work (70%): 8.4 weeks
  Foundational (20%): 2.4 weeks
  Buffer/exploration (10%): 1.2 weeks

### Feature Initiatives
1. [Initiative A] — 3 weeks
   Why: Product roadmap goal [X]. Unlocks [metric].
   Key milestone: shipped to 100% users by week 10.
   Dependencies: API design review with team Y (week 1).

2. [Initiative B] — 2 weeks
   Why: Customer-reported pain point, top-3 NPS complaint.
   Key milestone: beta launched by week 6.

3. [Initiative C] — 2 weeks
   Why: Enables monetization feature planned for Q4.
   Key milestone: implementation complete by week 8; Q4 team picks up.

Remaining 1.4 weeks feature: unplanned/reactive work buffer.

### Foundational Initiatives
1. [Database migration phase 1] — 1.5 weeks
   Why: Current DB hitting connection limits. P99 latency up 40% YoY.
        If not addressed, will cause incidents in Q4 at holiday traffic.
   Key milestone: migration scripts written, tested in staging.

2. [Test flakiness reduction] — 0.9 weeks
   Why: 30% of CI runs have at least 1 flaky test. Slowing shipping velocity.
   Key milestone: flaky test count < 5 by end of quarter.

### Exploration
1. [PoC: new search infrastructure] — 1.2 weeks
   Why: Current search is a recurring source of complaints. Exploring options
        before Q4 planning.
   Outcome: recommendation in eval doc before Q4 kickoff.

### What's NOT on the roadmap (and why)
- [Feature D] — deprioritized; unblocked only after initiative C ships.
- [Full DB migration] — phase 1 only this quarter; phase 2 in Q4.
- [Performance rewrite of service X] — no incident data to justify;
  revisit if on-call pain increases.
```

**The "what's NOT on the roadmap" section:**

This section is underrated. It explicitly records what was considered and intentionally deferred. It prevents:
- "Why didn't you work on X?" — "Because it was deprioritized. Here's why."
- Forgotten commitments — things that were "promised" but never formally scheduled
- Scope creep mid-quarter — "well, if X isn't on the roadmap, why not add it?" (because adding it means removing something else)

**Brainstorming Questions:**
1. Your EM asks you to draft the team's Q4 roadmap. Walk through what inputs you'd gather, who you'd talk to, and what the draft would contain.
2. Midway through the quarter, product comes with a new "urgent" feature request that will take 3 weeks. How do you respond? What information do you need to decide whether to reprioritize?
3. How do you estimate capacity for a quarter? What factors reduce available engineering time from the theoretical "12 engineers × 12 weeks"?
4. A well-intentioned engineer keeps adding small "cleanup" tasks to the roadmap throughout the quarter. How do you manage scope creep without discouraging good habits?

---

## Part 4: Making the Case for Foundational Work

*(L4 → L5 level)*

Convincing non-technical stakeholders to invest engineering time in invisible work is one of the hardest communication challenges for senior engineers. The foundational work is essential, but its value is easy to dismiss.

**The problem with "technical debt" framing:**

```
What engineers say:        What stakeholders hear:
"We need to pay down       "Engineers made bad decisions before and now
 technical debt."           want time to fix their own mistakes."

"We need to refactor       "Engineers want to do art projects that don't
 the authentication         help users."
 service."

"We need to upgrade        "That sounds like IT work, not product work."
 our database."
```

The word "technical debt" is often counterproductive. It focuses on the past ("we owe a debt") rather than the future ("this investment will unlock X").

**Reframe: foundational work as enabling capacity:**

The key shift: frame foundational work not as fixing the past but as enabling the future.

```
Instead of:                    Say:
"We need to pay down debt."  → "This work will let us ship features 30%
                                faster starting next quarter."

"We need to refactor auth."  → "The authentication service is blocking 3
                                planned product features. This work unblocks
                                them and reduces our p99 auth latency from
                                800ms to 100ms."

"We need to upgrade the DB." → "At current growth, we hit our database's
                                scaling limit in Q4. This migration, done
                                now in 2 weeks, avoids a critical incident
                                during the holiday season."
```

**The four arguments that work:**

```
1. THE INCIDENT PREVENTION ARGUMENT
   "Here is a specific system that will fail in N months at our growth rate.
    Here is the data: current error rate = X%, traffic growth = Y%/quarter,
    estimated failure point = Z date.
    Doing this work now costs 2 weeks. An incident costs 1-4 days of all-hands
    firefighting, plus SLA penalties, plus customer trust damage."

   Works best: when you have data showing a trending problem.
   Data to gather: error rates, latency trends, capacity usage trends.

2. THE VELOCITY UNLOCK ARGUMENT
   "This foundational work is blocking feature work.
    Our current deployment process takes 45 minutes. Engineers spend 2 hours/day
    waiting for deploys. Fixing the deployment pipeline saves 10 engineer-hours/week
    = 1.25 engineer-weeks/quarter.
    Invested cost: 1 week. Payback: 1.25× per quarter, every quarter."

   Works best: when foundational work has a clear, measurable velocity impact.
   Data to gather: time spent on pain points (surveys, observability data).

3. THE PLATFORM MULTIPLIER ARGUMENT
   "This work enables 3 other teams to move faster.
    The shared authentication library, once updated, reduces each team's
    auth integration from 2 weeks to 2 days. 5 teams × 8 days saved = 40
    engineer-days in Q4 alone."

   Works best: for infrastructure/platform work that benefits multiple teams.

4. THE RISK QUANTIFICATION ARGUMENT
   "Our data at rest is not encrypted at rest. This is a compliance gap.
    A security audit in Q4 or a data breach would cost:
      - Regulatory penalty: $50K-$2M depending on jurisdiction
      - Customer notification: 2 engineer-weeks
      - Reputational damage: unknown but significant
    Encryption-at-rest work: 3 engineer-weeks.
    Expected cost if not done: $50K minimum."

   Works best: for security, compliance, and risk-reduction work.
```

**The "bad debt vs. good debt" mental model:**

Not all technical debt is equally urgent. Help stakeholders understand which debt is actively slowing you down (bad debt) vs. which is just suboptimal but not causing harm (tolerable debt).

```
BAD DEBT (prioritize):
  - Directly causes on-call incidents
  - Actively slows feature delivery
  - Creates security or compliance exposure
  - Blocks other teams

TOLERABLE DEBT (schedule when capacity permits):
  - Code that works but is harder to read than it could be
  - A service that's slightly over-complicated for its current purpose
  - Old library version (no known CVEs, just not latest)
  - Tests that are slow but not flaky
```

**Brainstorming Questions:**
1. Your product manager says "technical debt is an engineering problem — we can't prioritize it over features." How do you respond? What argument do you make and with what data?
2. You want to convince leadership to allocate 1 month (one engineer) to improving deployment pipeline speed. Write the 3-sentence pitch that leads with business value, not technical improvement.
3. When making the incident prevention argument, what data would make it most compelling? Where do you get that data?
4. A colleague argues: "we should just always do foundational work without asking for permission — just do it within feature tickets." What are the pros and cons of this approach vs. making it explicit on the roadmap?

---

## Part 5: Writing a Technical Strategy Document

*(L5 level)*

A technical strategy document is a longer-horizon artifact than a quarterly roadmap. It answers: "Where is our technical system going over the next 1-3 years, and why?"

It's written by staff+ engineers, reviewed by engineering leadership, and used as a reference when making quarterly planning decisions.

**When to write one:**

```
Write a technical strategy doc when:
  - Your team's architecture has major gaps that need multi-year investment
  - There's a significant migration ahead (e.g., monolith → microservices)
  - Your technical direction is unclear and causing conflicting decisions
  - A new platform capability is being designed (data platform, auth system, etc.)
  - Engineering leadership is asking "what's the plan for [X] over the next 2 years?"

Do NOT write one for:
  - Every quarterly initiative (too granular — that's a project doc)
  - Theoretical architecture improvements with no business driver
  - Technology you want to explore (that's a PoC proposal)
```

**The technical strategy doc structure:**

```markdown
# Technical Strategy: [Area]
Date: YYYY-MM-DD | Author: [Name] | Status: DRAFT / APPROVED
Review cycle: every 6 months

---

## 1. Executive Summary
2-3 sentences. What is the current state? What are we changing and why?
For a non-engineer: what business problem does this strategy address?

## 2. Current State
Where are we now? What systems exist? What are their limitations?
Use data: performance numbers, incident history, team velocity metrics.
Be honest about problems — this is a planning doc, not a marketing doc.

## 3. Target State (12-24 months)
What will the system look like when this strategy is complete?
Be specific: which systems will be replaced, what will be their properties?
What capabilities will engineering teams have that they don't have today?

## 4. Gap Analysis
Current state → target state: what specifically needs to change?
Technical gaps (systems to build, migrations to execute, debt to pay)
Skill gaps (capabilities the team needs to develop or hire)
Process gaps (ways of working that need to change)

## 5. Proposed Approach
How do we get from current to target?
Phase it: what do we do first (foundational), then second, then third?
Explain the sequencing: why this order?

## 6. Risks and Mitigations
What could go wrong with this strategy?
How do we mitigate those risks?
What are the explicit assumptions this strategy depends on?

## 7. Metrics for Success
How will we know the strategy is working?
What metrics improve as we execute? By when?

## 8. Investment Required
How many engineer-weeks/months of foundational work is this strategy?
What is the opportunity cost (feature work not done while this is executing)?

## 9. Alternatives Considered
What other approaches were evaluated? Why was this one chosen?

## 10. Quarterly Checkpoints
What should be true at the end of each quarter for this strategy to be on track?
```

**Example: a data platform technical strategy (abbreviated)**

```
Current state:
  Each team owns their own database. Analytics queries run on production
  databases, causing latency spikes. No central data warehouse. Business
  reporting is done via manual SQL queries by engineers on request.
  6 incidents in the last quarter caused by analytics queries impacting
  production traffic.

Target state (18 months):
  Central data warehouse (Snowflake). Production databases replicated
  via change data capture (CDC). Analytics runs on warehouse, never on
  production. Engineers can self-serve most analytics. 0 analytics-caused
  production incidents.

Phase 1 (Q3): CDC pipeline from 3 largest databases to data warehouse.
Phase 2 (Q4): Analytics team migrated off production queries.
Phase 3 (Q1 next year): Self-serve analytics tooling for product/biz teams.
Phase 4 (Q2 next year): Remaining 12 databases migrated to CDC pipeline.

Investment: 6 engineer-months over 4 quarters.
Benefit: 0 analytics-caused production incidents (saving ~15 engineer-days/quarter).
         Product/biz team self-service (saving ~5 engineer-hours/week in query requests).
```

**Brainstorming Questions:**
1. Your team's technical strategy doc from 12 months ago is now partially outdated because a major product pivot changed priorities. How do you handle this? Do you update it, archive it, or keep it as-is?
2. A technical strategy says "migrate to microservices over 18 months." Halfway through, the team has hit unexpected complexity and the migration is 3 months behind. How do you communicate this? What do you adjust?
3. Who should review a technical strategy doc? How broadly should it be shared? What happens if a peer engineer disagrees with the strategy?
4. What's the difference between a technical strategy doc and a system design doc? Could they be the same document? When are they the same and when are they different?

---

## Part 6: Aligning the Engineering Roadmap with Product

*(L4 → L5 level)*

Engineering and product roadmaps should not be two separate documents. They should be coordinated views of the same work. When they diverge, the team has two masters pulling in different directions.

**How the misalignment happens:**

```
Product roadmap:                  Engineering roadmap:
  Q3: Feature A (3 weeks)           Q3: Database migration (4 weeks)
  Q3: Feature B (4 weeks)               (no feature capacity left)
  Q3: Feature C (2 weeks)
  
Nobody reconciled these two plans. The result: the team tries to do everything,
delivers neither well, and everyone is frustrated.
```

**The alignment process:**

```
STEP 1: Joint capacity review (beginning of quarter planning)
  Engineering: "We have 12 engineer-weeks this quarter."
  Engineering: "We need 2 weeks for the DB migration."
  Engineering: "Available for features: 10 weeks."
  Product: "Features A, B, C would take 9 weeks. We can do all three."

  Result: shared understanding of what fits in the quarter.

STEP 2: Priority ordering (if more work than capacity)
  Product: "If we can only do 2 of A/B/C, which 2 are most important?"
  Engineering: "Are any of A/B/C dependent on the DB migration? (If A depends
               on the migration, then migration is effectively feature work)"
  
  The conversation becomes: "given constraints, what's the highest-value sequence?"

STEP 3: Dependency mapping
  "Feature B requires the auth service refactor Engineering was planning.
   Is that in the foundational budget? Or does it move into feature capacity?"
  
  Surface these dependencies before the quarter starts, not week 6.

STEP 4: Written commitment (the combined roadmap)
  Document both together: features AND foundational work, with capacity accounted for.
  Both product and engineering sign off.
  Deviations are tracked and explained.
```

**The product partnership model:**

The best staff engineers don't just respond to product roadmaps — they actively shape them.

```
Reactive (L3/L4):
  Product: "We want to build feature X."
  Engineering: "OK, we can build it in 3 weeks."

Proactive (L5):
  Engineering: "We notice you're planning to build features X, Y, Z.
                All three are in the payment service.
                That service has a known scaling limit — it will fail at
                holiday traffic if we don't address it first.
                Recommendation: we add a 1-week service hardening milestone
                before features X, Y, Z. Otherwise we risk an incident
                right when features launch."

Proactive (L6 / Staff):
  Engineering: "Based on the 12-month product vision, I see 3 major
                technical investments needed to support it.
                Here's how I'd phase them to minimize impact on feature
                delivery while ensuring the platform can support the product roadmap."
```

**Brainstorming Questions:**
1. Your product manager is resistant to any foundational work because "it doesn't directly ship value to users." How do you establish a working relationship where technical investments are respected? What would you propose structurally?
2. You're in a planning meeting and product has requested 15 weeks of feature work in a quarter where engineering has 10 weeks of capacity. How do you run this conversation? What outcome are you aiming for?
3. A feature request comes in mid-quarter that product labels "critical." It will take 2 weeks. Your team already has 0 slack capacity. What are your options, and how do you decide?
4. How do you handle a situation where the engineering roadmap and product roadmap are consistently misaligned quarter after quarter? What structural change would you propose?

---

## Part 7: Sequencing — What to Do First and Why

*(L5 level)*

One of the hardest parts of roadmapping is sequencing: deciding which projects go in Q3, which go in Q4, and which wait until next year. The order matters because projects have dependencies, and a badly sequenced roadmap creates bottlenecks.

**The sequencing principles:**

```
PRINCIPLE 1: UNBLOCK OTHERS FIRST
  Work that other teams are waiting on should usually go first.
  An unblocked team compounds your investment — their work builds on yours.
  
PRINCIPLE 2: FOUNDATION BEFORE FEATURE
  If a feature requires a technical foundation that doesn't exist,
  build the foundation first. Don't build on sand.
  
  Counter: if the feature can be built without the ideal foundation
  (with some technical debt), and the foundation can be built later
  with acceptable migration cost, sometimes ship the feature first.
  
PRINCIPLE 3: RISKIEST WORK FIRST
  Projects with high technical uncertainty (new approaches, unknown scope)
  should happen early in the quarter or year — not at the end.
  
  If the risky project fails, you learn early and can adjust.
  If it's last, failure cascades into missed commitments.

PRINCIPLE 4: DEPENDENCIES DEFINE SEQUENCE
  Map the dependency graph: project B requires project A to be done.
  A before B is not optional. The rest of the sequence is.
  
PRINCIPLE 5: MIGRATIONS BEFORE GREENFIELD
  Migrating away from an old system is usually more complex than
  building a new system. Do it earlier when team energy is highest
  and the old system is still functioning.
  
  Migrations done "later" tend to become migrations done "never."
```

**Dependency mapping — a worked example:**

```
Projects planned for the next 6 months:
  A: Upgrade auth service
  B: Build multi-tenant support
  C: Launch new pricing tier
  D: Migrate to new payment processor
  E: Add audit logging
  F: SOC 2 compliance review

Dependency analysis:
  C depends on B (multi-tenant support enables new pricing tier)
  B depends on A (multi-tenant requires auth service upgrade)
  E depends on A (audit logging requires updated auth service)
  F depends on E (SOC 2 requires audit logging to exist)
  D is independent (payment processor migration is self-contained)

Dependency graph:
  A → B → C
  A → E → F
  D (independent)

Valid sequences:
  Q3: A + D (in parallel)     ← auth upgrade + payment migration together
  Q4: B + E (in parallel)     ← multi-tenant + audit logging both unblocked by A
  Q1: C + F (in parallel)     ← pricing tier + SOC 2 both ready to execute

Invalid sequences:
  Q3: B (requires A, not done yet)
  Q3: C (requires B, not done yet)
  Q3: F (requires E, which requires A)
```

**The "golden path" sequencing heuristic:**

Ask: "What sequence minimizes the total time from start to the most valuable outcome?"

```
If the most valuable outcome is "SOC 2 compliance by Q1":
  Start with A immediately (it unblocks E and F)
  Run D in parallel (independent)
  E follows A immediately
  F follows E immediately
  B and C can wait — they don't block SOC 2

If the most valuable outcome is "new pricing tier launched in Q1":
  Same start: A immediately (it unblocks B, which unblocks C)
  D in parallel
  B follows A immediately
  C follows B immediately
  E and F can wait — they don't block pricing tier
```

The roadmap looks different depending on which outcome is most valuable. **Sequencing requires knowing the goal, not just the project list.**

**Brainstorming Questions:**
1. You have 5 projects and limited capacity. Two are independent; three have a chain dependency. Draw the dependency graph and identify the optimal 2-quarter sequence.
2. Your team chose to do a "greenfield" feature before migrating the system it depends on. The feature launched but the migration never happened. 18 months later, the old system is causing incidents. What went wrong in the sequencing decision, and how do you handle it now?
3. A project has high technical uncertainty — it could take 2 weeks or 8 weeks. How does this uncertainty affect where you put it in the sequence? What information would help you reduce the uncertainty before committing to a date?
4. "Riskiest work first" is a principle, but it can conflict with "product wants features first." How do you navigate this conflict in a specific scenario?

---

## Part 8: The Tech Debt Inventory

*(L4 → L5 level)*

Without a maintained list of technical debt, foundational work competes on memory rather than evidence. The team that shouts loudest about their tech debt gets the resources. This is a bad system.

A tech debt inventory is a living document that records the known technical liabilities in a system — what they are, why they matter, and what addressing them would cost.

**What goes in the inventory:**

```
For each item, capture:
  1. Name: short description of the debt
  2. Location: which service/codebase/infrastructure
  3. Impact: what problem is this causing TODAY?
  4. Severity: is it causing incidents? Slowing development? A latency risk?
  5. Estimated fix cost: rough engineer-weeks
  6. Estimated cost of NOT fixing: time lost/quarter, incident risk, etc.
  7. Date discovered: when was this first logged?
  8. Owner: who is responsible for tracking this?
```

**A sample inventory entry:**

```markdown
## [AUTH-001] Legacy session token format

Location: auth-service, ~3,500 lines in session_handler.go

Current impact:
  - Auth service accounts for 30% of on-call alerts
  - Session validation is 450ms p99 (should be < 50ms)
  - Can't implement SSO (depends on OAuth refresh tokens, which this format
    doesn't support)

Severity: HIGH
  - Blocking: SSO feature (top-5 customer request)
  - Contributing: 3 incidents in Q2 caused by session edge cases
  
Fix cost: 4 engineer-weeks (rewrite session handling, migrate existing sessions)
Cost of not fixing:
  - SSO blocked indefinitely
  - ~2 on-call incidents/quarter × 8 hours each = 16 eng-hours/quarter
  - Growing risk: session store is at 70% capacity, will hit limit in ~2 quarters

First logged: 2025-10-15
Owner: [Name]
```

**Prioritizing the inventory:**

Use a simple scoring: **impact × urgency ÷ cost**

```
Impact: how much is this hurting? (1-5 scale)
Urgency: how soon will it get worse? (1-5: 1 = stable, 5 = will fail this quarter)
Cost: how expensive to fix? (inverse scale: 1 = very expensive, 5 = cheap)

Score = Impact × Urgency × Cost
High score = high priority

Example:
AUTH-001: Impact=5 (blocking feature, causing incidents) × Urgency=4
          (will hit capacity limit in 2 quarters) × Cost=3 (4 weeks = medium) = 60

BUILD-002: Impact=2 (slow CI, annoying but not blocking) × Urgency=1 (stable) × Cost=4 (1 week) = 8

Priority: AUTH-001 >> BUILD-002
```

**When to add items, when to close them:**

```
Add to inventory when:
  - A postmortem identifies a structural root cause
  - Engineers flag a pain point in retro that takes > 1 week to fix
  - A feature request is blocked by existing technical limitations
  - A scaling limit is projected to be hit in the next 4 quarters

Close / remove items when:
  - The item is resolved (migrated, refactored, decommissioned)
  - The system it referred to no longer exists
  - The item was superseded by a larger initiative that addresses it
  - Re-evaluation shows the cost of fixing > cost of living with it
```

**Brainstorming Questions:**
1. Your team has no tech debt inventory. How would you bootstrap one? How would you gather the initial list of items without it turning into a complaint session?
2. Two engineers both believe their debt item is the highest priority. How do you adjudicate? What makes the scoring framework useful here?
3. A tech debt item has been on the inventory for 2 years without being addressed. What does that tell you? What would you do about it?
4. A product manager asks to see the tech debt inventory "to understand the engineering state." What would you share and what would you hold back? How would you present it to a non-technical audience?

---

## Part 9: Communicating the Roadmap to Stakeholders

*(L5 level)*

A roadmap that isn't communicated isn't useful. Different audiences need different levels of detail. The skill is adjusting the message without changing the substance.

**The audience matrix:**

```
AUDIENCE          WHAT THEY CARE ABOUT          WHAT TO SHARE
──────────────────────────────────────────────────────────────────────────────
Your team         What we're doing, why,         Full roadmap + context
                  in what order, context         Weekly stand-ups + retros

Product manager   Will features ship on time?    Feature initiatives + dates
                  What are the risks?            Dependencies + blockers
                  What's engineering doing?      1-page quarter summary

Engineering EM    Team health, velocity,         Full roadmap + investment
                  technical risk                 ratios + risk areas

VP/Director       Strategic direction,           1-page executive summary
                  business risk,                 Top 3 bets + key risks
                  resource needs                 No implementation detail

Cross-team        Interfaces and dependencies    Shared milestones only
engineers         that affect their work         API contracts + timelines
```

**The 1-page quarterly summary (for leadership):**

```markdown
## Engineering Q3 2026 Summary

**What we're delivering:**
  1. Multi-tenant support (unblocks new pricing tier in Q4)
  2. Auth service upgrade (unblocks SSO, reduces on-call by ~40%)
  3. Payment processor migration (reduces transaction fees ~15%)

**What we're investing in (foundational):**
  Database migration Phase 1 — prevents capacity incident in Q4 holiday season.
  Test pipeline reliability — saves ~5 engineer-hours/week starting Q4.

**Key risks:**
  Multi-tenant has higher complexity than estimated; may slip 1 week.
  Payment migration requires vendor coordination — dependency outside our control.

**What we're NOT doing this quarter (and why):**
  Full DB migration deferred to Q4 — Phase 1 is sufficient to handle Q3 growth.
  Feature D deferred — blocked by multi-tenant work which ships late in Q3.
```

**Handling roadmap changes mid-quarter:**

Things change. The question isn't whether the roadmap will change but how to communicate changes well.

```
Good communication when things change:
  1. EARLY: communicate as soon as you know, not at the end of the quarter
  2. SPECIFIC: "Feature B is slipping by 2 weeks because [specific reason]"
  3. SOLUTIONS: "We can either: (a) remove Feature C, (b) extend timelines,
                  (c) add 1 more engineer from team Y. Recommendation: option A."
  4. UPDATED DOC: update the roadmap doc to reflect the new reality

Bad communication:
  "Things are going well." (not specific)
  "We might be a little late." (too vague)
  Surprise at the end of the quarter: "we didn't ship B." (no warning)
```

**The roadmap review cadence:**

```
Weekly: Brief status check in team standup
  "Roadmap items on track / at risk / blocked — any updates?"

Monthly: Brief write-up to stakeholders
  1 paragraph: what shipped, what's in progress, any changes.
  
Quarterly: Full roadmap review + next quarter planning
  Retrospective on last quarter: what was planned vs. delivered?
  Next quarter draft: based on what we learned.
  Stakeholder review and sign-off.
```

**Brainstorming Questions:**
1. Halfway through Q3, a major initiative will miss the quarter by 3 weeks. How do you communicate this to your product manager? Write the Slack message.
2. Your team's VP asks "what is engineering working on?" You have 2 minutes to explain the quarter. What do you say?
3. A cross-team dependency slipped — another team didn't deliver what your team was depending on. How do you handle the communication both internally (to your team) and externally (to stakeholders)?
4. You notice that the team's quarterly roadmap is consistently 70% delivered — 30% of planned work always slips. What systemic problems could cause this, and how do you diagnose which one is affecting your team?

---

## Part 10: The Engineering Strategy — Multi-Year Vision

*(L5 → L6 level)*

At the largest scope, above the quarterly roadmap and the technical strategy doc, is the engineering strategy: the multi-year direction for how engineering will scale and evolve to match the business.

This is L6 / Staff territory. Most engineers never write one. But understanding what it is helps you work with staff engineers and participate in the conversations that shape it.

**What an engineering strategy answers:**

```
1. What kind of engineering organization do we want to be in 3 years?
   (Platform-first? Product-engineering? Embedded specialists?)

2. What are the 3-5 most important technical bets for the company?
   (Which capabilities, if built, give us sustainable competitive advantage?)

3. What technical liabilities most threaten the business at scale?
   (Which architectural problems, if not addressed, will limit growth?)

4. How do we balance engineering velocity vs. engineering resilience?
   (Move fast? Or build it right? Under what conditions does each apply?)

5. What should we build, buy, or open-source?
   (Where does ownership create advantage? Where does it create burden?)
```

**The difference between strategy and roadmap:**

```
ROADMAP:                          STRATEGY:
  "Q3: migrate auth service"        "Auth is a core competency we own.
                                     In 3 years, it will support SSO,
                                     OAuth, and passkeys — industry-standard
                                     security for enterprise customers."

  "Q4: build data warehouse"        "Data infrastructure is a multiplier.
                                     In 2 years, every team self-serves
                                     their analytics without engineering help."

  Specific projects + timelines     Principles + direction + rationale
  1-4 quarters                      1-3 years
  Changes often                     Changes rarely (major pivots only)
  Owned by team tech lead/EM        Owned by staff+ engineers + CTO/VPE
```

**Real-world example: Stripe's infrastructure strategy**

Stripe published aspects of their infrastructure philosophy publicly. Key principles:
1. **Ownership over outsourcing** for core fintech components — payment logic, reconciliation, fraud detection. They build what differentiates them.
2. **Managed services for non-core** — they use vendor services aggressively for things that aren't their core competency (Datadog for monitoring, GCP for compute).
3. **Reliability as a product** — their internal reliability standards (five nines for payment processing) are treated as product requirements, not engineering preferences.
4. **Platform as a force multiplier** — internal platform teams enable product engineers to move at startup speed.

This kind of strategy document says: "here's what we believe about building engineering organizations, and here's how it shapes every technical decision we make."

**Brainstorming Questions:**
1. What is the technical strategy of your current employer (stated or unstated)? How does it manifest in the day-to-day technical decisions the team makes?
2. How does a company's business model influence its engineering strategy? Give an example of how two different business models would lead to different engineering strategies.
3. At what company size does a formal engineering strategy become necessary? What forces make it necessary?
4. A technical strategy from 3 years ago says "mobile-first." The company's usage patterns have shifted — 60% of revenue now comes from API partners (not mobile users). How do you update the strategy? Who needs to be involved?

---

## Part 11: Named Real-World Roadmapping Stories

*(L5 — named examples for interview depth)*

**Story 1: Spotify's "Squad Model" and the Technical Strategy Behind It**

In 2012, Spotify published their squad model — a way of organizing engineering teams into small, autonomous squads with clear missions. Behind this was a technical strategy: enable squads to move independently without coordinating on shared infrastructure. The technical investment required: a platform team that built shared services (deployment pipeline, observability, A/B testing) so each squad could build product features without reinventing infrastructure. The roadmap implication: years of platform investment before the squad model worked as intended. The lesson: organizational strategy and technical strategy are intertwined. The roadmap must reflect both.

**Story 2: Amazon's Migration to SOA (Service Oriented Architecture)**

Jeff Bezos's "API mandate" (2002) was an engineering strategy decision: all teams must expose data through service interfaces. This was a 3-year+ technical roadmap item across all of Amazon. The sequencing challenge was immense — thousands of internal dependencies, no clear "start here." Amazon's approach: teams migrated incrementally to SOA as they needed new capabilities; the monolith didn't disappear overnight. The lesson: large architecture migrations need a compelling business reason (the mandate was driven by internal tooling needs AND the vision of AWS), clear principles, and years of sustained investment.

**Story 3: Netflix's Infrastructure Migration to AWS**

In 2008, Netflix had a major database corruption incident. Their strategy: migrate everything to the cloud (AWS) over the next 7 years. The roadmap was explicitly sequenced: start with non-critical systems, prove the pattern, expand. They published their migration architecture openly. The migration took until 2015 — 7 years. The business driver: Netflix's streaming growth required elastic scaling that their own data centers couldn't provide. The lesson: multi-year technical roadmaps require sustained leadership commitment and a clear business driver (elastic scaling in this case). Without the business driver, the migration would have been deprioritized every quarter.

**Story 4: GitHub's Monolith Scaling Strategy (2021)**

GitHub runs one of the largest Ruby on Rails monoliths in existence. Rather than "migrate to microservices" (a common but expensive choice), GitHub's engineering strategy chose to scale the monolith through: improved sharding, asynchronous job processing (Resque → Sidekiq), read replicas, and careful performance optimization. Their public engineering blog documents decisions to NOT break up the monolith despite pressure. The technical strategy: "the monolith is a feature, not a bug — optimize it." The lesson: a good technical strategy sometimes means explicitly NOT doing what's fashionable, when evidence shows the current approach can be scaled further.

**Story 5: Airbnb's "Service Mesh" Investment Decision**

Airbnb grew from a monolith to hundreds of microservices by 2017. With scale came coordination problems: services couldn't discover each other reliably, observability was inconsistent, and traffic management was manual. Their engineering strategy: invest in a service mesh (SmartStack, then migration to Envoy). This was a multi-year platform investment with no direct user-facing value. The roadmapping argument was made by quantifying the cost of the current state: 3 hours/engineer/week lost to service discovery issues × 300 engineers × 52 weeks = 46,800 engineer-hours/year. The platform investment paid back in reduced operational overhead within 18 months. The lesson: quantify the cost of the current state to make the investment argument for platform work.

---

## Part 12: L5 vs L6 Calibration

```
┌────────────────────────────────────────────────────────────────────────────────┐
│         L3 / L4 / L5 / L6 ROADMAPPING AND STRATEGY CALIBRATION               │
├──────────────┬─────────────────────────────────────────────────────────────────┤
│  L3 (SWE)    │ Works from the roadmap. Provides task estimates.               │
│              │ Flags technical concerns when asked.                           │
│              │ Does not own planning artifacts.                               │
├──────────────┼─────────────────────────────────────────────────────────────────┤
│  L4 (SSE)    │ Owns sprint-level planning within the team.                   │
│              │ Contributes to quarterly roadmap with estimates and risks.     │
│              │ Flags tech debt. Can draft foundational work proposals.        │
├──────────────┼─────────────────────────────────────────────────────────────────┤
│  L5 (Sr SWE) │ Owns the team's quarterly roadmap.                            │
│              │ Maintains the tech debt inventory.                             │
│              │ Makes the case for foundational work with data.                │
│              │ Aligns engineering roadmap with product roadmap.               │
│              │ Writes technical strategy docs for their team's scope.         │
│              │ Communicates roadmap status to stakeholders proactively.       │
├──────────────┼─────────────────────────────────────────────────────────────────┤
│  L6 (Staff)  │ Drives technical strategy across multiple teams.              │
│              │ Shapes company-level engineering investment ratios.            │
│              │ Writes multi-year technical vision.                            │
│              │ Connects technical direction to business strategy.             │
│              │ Defines which decisions are strategic vs. tactical.            │
│              │ Creates technology radar for the organization.                 │
│              │ Influences hiring and team composition to match strategy.      │
└──────────────┴─────────────────────────────────────────────────────────────────┘
```

---

## Part 13: Pre-Interview Drill — 10 Questions

**Q1: How do you build a quarterly roadmap for your team?**

"I start by gathering inputs: what does product want this quarter, what's in the tech debt inventory, what reliability/incident data is telling us we need to fix. I estimate capacity (total engineer-weeks × 70/20/10 split). I draft the roadmap with product + EM: feature initiatives with dependencies mapped, foundational work with a clear business case, and a buffer. I document what's NOT on the roadmap and why. Then socialize, get sign-off, and track weekly."

**Q2: How do you make the case for technical foundational work to a product manager who only cares about features?**

"I never lead with 'tech debt.' I frame it in terms of business impact. The four arguments: incident prevention ('this system will fail in Q4 at holiday traffic — here's the data'), velocity unlock ('this investment saves 10 engineer-hours/week = 1 quarter's worth of feature work per year'), platform multiplier ('this enables 3 other teams to move faster'), or risk quantification ('the compliance gap represents a $500K regulatory exposure'). I show the data, not just the opinion."

**Q3: How do you balance feature work and foundational work?**

"I use an explicit investment ratio — 70% feature, 20% foundational, 10% exploration — and make it visible in the roadmap. The ratio creates a shared agreement that foundational work IS planned, not just hoped for. If the team is in heavy debt, I'd argue for a temporary 50/40/10 for one quarter, with data to justify it. Without the explicit ratio, every planning meeting defaults to 100% features."

**Q4: How do you sequence projects on a technical roadmap?**

"I map the dependency graph first — some projects must come before others. Then apply these principles: unblock other teams first, foundation before feature, riskiest work early in the quarter. The sequence falls out of the dependency graph + these principles. I also ask: 'what's the highest-value outcome, and what sequence gets us there fastest?'"

**Q5: How do you communicate a roadmap change (when something slips)?**

"Early, specific, and with options. As soon as I know something will slip, I communicate: '[Project X] will slip by [N weeks] because [specific reason]. Options are: (a) drop [Y] to absorb the slip, (b) extend timeline, (c) get additional help from [team Z]. Recommendation: [A]. Updating the roadmap doc now.' I don't wait until the end of the quarter. I don't hedge."

**Q6: What is a technical strategy document?**

"A technical strategy doc is a 1-3 year direction document for a technical area. It covers current state (with real data), target state, gap analysis, phased approach, risks, and success metrics. It answers: 'where is our technical system going and why?' It's more stable than a quarterly roadmap — changes only on major pivots. It's the context that makes quarterly roadmap decisions legible."

**Q7: How do you maintain a tech debt inventory?**

"Each item has: what it is, what it's costing us (incidents, velocity, blocked features), rough fix cost, and a priority score (impact × urgency ÷ cost). I add items from postmortems, retros, and blocked feature work. I prioritize the top 3-5 items for inclusion in the quarterly roadmap. I close items when they're resolved or superseded. The inventory lives in a doc that's reviewed quarterly."

**Q8: How do you align the engineering roadmap with the product roadmap?**

"Joint capacity review at the start of each quarter: here's our total capacity, here's the split, here's available feature capacity. Product brings their list; we compare against capacity. Surface dependencies (engineering work that features need). Write a combined roadmap that both product and engineering sign off on. The goal: one shared truth, not two competing documents."

**Q9: What's the difference between a roadmap and a backlog?**

"A backlog is a comprehensive list of all known work — prioritized but unbounded. A roadmap is a commitment: this is what we will do this quarter, with capacity allocated, dependencies mapped. A backlog is reactive (we'll get to it when there's space); a roadmap is proactive (we've made specific commitments). At L5, you convert the important parts of the backlog into a roadmap with explicit time allocation."

**Q10: Tell me about a time you influenced engineering strategy.**

"At [company], our deployment pipeline was taking 45-60 minutes per deploy, and engineers were doing 3-5 deploys/day. Engineers were losing 2-3 hours/day waiting. The impact: feature velocity was constrained, and urgent fixes took hours to deploy. I built the business case (data: 150 engineer-hours/week lost × $150/hour fully loaded = $22K/week), proposed a 3-week investment to rebuild the pipeline on GitHub Actions with parallel test execution. Got it on the Q2 roadmap. Result: deploys dropped from 50 minutes to 8 minutes. Estimated velocity improvement: ~20% more feature work per quarter."

---

## Part 14: Exercises

**Exercise 1: Draft a quarterly roadmap**

Pick your current team (or a hypothetical one). Define: 8 engineer-weeks total capacity, 70/20/10 split. Choose 3 feature initiatives (with sizes) and 1-2 foundational items. Map any dependencies between them. Document what's NOT on the roadmap and why. Share with a colleague and explain your sequencing decisions.

**Exercise 2: Build a mini tech debt inventory**

List 5 technical debt items in a system you know well. For each, fill in: what it is, what it's costing the team today (be specific), estimated fix cost, and a severity score. Rank them by priority using impact × urgency ÷ cost. Which item would you put on next quarter's roadmap first?

**Exercise 3: Make the case for foundational work**

Pick a foundational item from your tech debt inventory. Write a 150-word pitch for a product manager — no jargon, focused on business impact. Use one of the four argument types: incident prevention, velocity unlock, platform multiplier, or risk quantification.

**Exercise 4: Sequence a dependency graph**

Draw the dependency graph for these 6 projects: A → B → D, A → C → E, F (independent). You have 2 quarters of capacity. If the most valuable outcomes are D and E, which sequence minimizes total time to delivery? Now answer: if the business priority shifts so that only F and D matter, does the sequence change?

---

## Part 15: Homework

**Reading:**
- "Staff Engineer" by Will Larson, Chapters 4-5 — the definitive guide to technical strategy at staff level. Will Larson was VPE at Calm and has helped dozens of engineers grow to staff level.
- "An Elegant Puzzle" by Will Larson — the systems thinking approach to engineering management and strategy. Read Chapters on technical strategy and roadmapping.
- Thoughtworks Technology Radar (public, thoughtworks.com/radar) — a real-world example of a technology strategy artifact.

**At your current job:**
- Find or reconstruct your team's technical roadmap for the current quarter. If it doesn't exist, ask your EM what the team is working on and why. Compare what you hear against what's actually being worked on.
- Ask a staff or senior engineer on your team: "what's the one technical investment you'd make if you had 4 engineer-weeks of unrestricted time?" Write down the answer and see if you can build a mini business case for it.

**Research:**
- Read Netflix's engineering blog posts about their AWS migration (2008-2015). What was the business driver? How was it sequenced? What did they do first?
- Read Stripe's or Shopify's engineering blog for any post about infrastructure investment. What argument did they make for doing foundational work?

---

## Part 16: Vocabulary Quick Reference

```
Technical roadmap:     Time-sequenced plan of engineering work connected
                        to business goals. Usually 1-4 quarters.

Technical strategy:    Multi-year direction for a technical area. More stable
                        than a roadmap; changes only on major pivots.

Engineering strategy:  Company-wide multi-year technical direction. Owned by
                        staff+/principal/CTO.

70/20/10 rule:         Default investment ratio: 70% features, 20% foundational,
                        10% exploration. Explicit split prevents 100% feature work.

Tech debt inventory:   Living list of known technical liabilities with impact,
                        cost-to-fix, and priority scores. Used to select
                        foundational roadmap items.

Dependency graph:      Map of which projects require which other projects to
                        complete first. Determines valid sequencing.

Strangler fig:         Incremental migration pattern. Not specific to databases —
                        applies to any system migration.

Planning horizon:      Now (sprint), Near-term (quarter), Mid-term (year),
                        Long-term (multi-year). Different owners, different granularity.

Investment ratio:      Explicit allocation of engineering capacity across work
                        types (features, foundational, exploration).

Capacity buffer:       Reserve of engineering time for unplanned work, on-call,
                        interviews, sick time. Usually 10-20% of total.
```

---

## Memorable Quotes

> *"A roadmap is not a promise. It's a shared understanding of what we're trying to accomplish and why — updated as we learn."*

> *"The best time to invest in your foundation was two years ago. The second best time is this quarter."*

> *"Technical debt is not a past mistake to be ashamed of. It's a future cost to be managed."*

> *"A feature request without an engineering estimate is just a wish. An engineering estimate without a sequenced roadmap is just a hope."*

> *"Strategy is not a list of good ideas. It's a set of connected choices about where to focus and where not to."*

---

---

## Part 17: Common Roadmapping Mistakes

*(All levels — recognizing and avoiding the traps)*

Even experienced engineers make predictable mistakes when building roadmaps. Here are the most common, with examples and fixes.

**Mistake 1: Planning at 100% capacity**

```
The mistake:
  12 engineer-weeks available.
  Roadmap includes 12 weeks of work.
  Every item lands exactly on time in the plan.

Why it fails:
  Real capacity is never 100%. Unplanned work happens every quarter:
  - Production incidents: 4-8 hours each
  - Interviews: 2-3 hours each (and teams do many per quarter)
  - Onboarding new engineers: 2-3 hours/week for the first month
  - Team sync overhead: standups, planning, retros, 1:1s
  - Scope discovery: features are always larger than estimated
  
  Typical real capacity: 70-80% of theoretical.
  A 12-engineer-week quarter actually has 8-10 weeks of execution capacity.

The fix:
  Build in a 20% buffer explicitly.
  "12 engineer-weeks × 80% = 9.6 weeks of planned work."
  The remaining 2.4 weeks absorbs unplanned work.
```

**Mistake 2: No definition of "done"**

```
The mistake:
  "We're working on the database migration." (end of quarter review)
  "How far did you get?" 
  "We started the schema design."
  
  The roadmap said "database migration" but nobody defined what
  "done" meant for this quarter. Was it design? Scripts? Staging? Production?

Why it fails:
  Without a definition of done, progress is unmeasurable.
  Slip happens but isn't visible until it's too late.
  Stakeholders think "database migration" means production-ready;
  engineering thought it meant "design doc."

The fix:
  Each roadmap item has a milestone definition:
  "Database migration — Done = migration scripts written, tested in staging,
   rollback plan documented. NOT: production migration (that's Q4)."
```

**Mistake 3: Underestimating dependencies**

```
The mistake:
  "Feature B: 3 weeks."
  [Week 6]: "Feature B is blocked — we're waiting for team X to finish
              their API changes."
  
  The dependency on team X was known but not scheduled with team X.
  Or: the dependency was not known until feature B started.

Why it fails:
  Dependencies on other teams are the #1 cause of roadmap slippage.
  Cross-team work requires synchronization that takes more time than expected.

The fix:
  Before finalizing the roadmap:
  1. List all projects that require other teams to deliver something.
  2. Confirm with those teams that they have the corresponding work on their roadmap.
  3. If not: escalate to EM or staff engineer to negotiate priority.
  4. Add explicit "dependency check" milestones: "Week 2: confirm team X's API
     design is finalized."
```

**Mistake 4: Roadmap as a wish list, not a commitment**

```
The mistake:
  17 items on the Q3 roadmap. Team has capacity for 8.
  Everyone knows only 8 will happen, but nobody says which 8.
  End of quarter: 6 shipped, 11 not. "We deprioritized things."
  
  The roadmap was a wish list, not a commitment.

Why it fails:
  Stakeholders thought everything on the roadmap was committed.
  Engineers were context-switching between too many initiatives.
  No clear priority ordering — "urgent" was whatever was asked about most recently.

The fix:
  The roadmap should only contain what fits in the capacity.
  Everything else goes on a "backlog" or "next quarter candidates" list.
  Items in the backlog are acknowledged ("we know about these") but not committed.
  
  Rule: if you can't answer "what gets cut if this takes 2 weeks longer?", 
  your roadmap is over-committed.
```

**Mistake 5: Foundational work without a "done" definition**

```
The mistake:
  "20% foundational work this quarter = 2 weeks."
  Week 12: "We spent some time on the database migration. Still in progress."
  
  The foundational bucket was treated as general permission to work on
  technical improvements whenever there was slack, not as a committed project.

Why it fails:
  Foundational work without a milestone never finishes.
  The 2 weeks gets absorbed by other things.
  At end of quarter, it shows up as "incomplete" or "not started."

The fix:
  Foundational work needs a milestone definition just like feature work.
  "Database migration Phase 1 — Done = schema design complete, 
   migration script written, tested in staging, rollback plan documented."
  This is a concrete deliverable. You can know on day 1 of Q4 whether it happened.
```

**Brainstorming Questions:**
1. You're reviewing your team's previous quarter and notice only 60% of the roadmap shipped. What process would you run to diagnose the root cause? List 5 possible causes and how you'd distinguish between them.
2. Your team consistently underestimates features (they take 2× as long as planned). How do you build this bias into your capacity planning? Is this a planning problem, a scope problem, or an estimation problem?
3. The same foundational item has been "in progress" for 3 consecutive quarters without completing. What structural change would you make?
4. A new engineer on your team says "why do we need milestones? We know what done looks like." How do you explain why explicit milestone definitions matter, especially for a distributed or async team?

---

## Part 18: Roadmapping in Different Organizational Contexts

*(L5 level — the roadmap looks different based on where you are)*

**Startup (< 30 engineers, moving fast):**

```
Typical situation:
  Product roadmap changes every 2-4 weeks based on user feedback.
  "Planning" happens in weekly all-hands, not quarterly docs.
  The team ships whatever is most important today.

Challenge:
  No foundational investment ever happens because every week has a "more urgent" feature.
  Technical debt accumulates. First indication: engineers start saying "it's complicated."

What to do:
  Even at startup stage, name the tech debt explicitly.
  Use a simple traffic light in the weekly all-hands:
    "Engineering health: 🟡 Yellow. Auth service is fragile — 
     we'll hit a wall in 8 weeks without hardening it."
  
  This creates visibility without a full planning process.
  Don't try to impose quarterly roadmaps at startup stage —
  they'll be wrong immediately and engineers will stop trusting them.
```

**Growth stage (30-200 engineers, scaling fast):**

```
Typical situation:
  Multiple product teams, each with their own roadmap.
  Engineering teams support multiple product areas.
  Dependencies between teams are constant.

Challenge:
  Each team plans independently. Discovered dependencies break timelines.
  Foundational work (shared platform) competes with product feature work.

What to do:
  Quarterly roadmaps with explicit capacity splits.
  Cross-team dependency review before quarter starts.
  A platform or infrastructure team with a separate roadmap for shared work.
  Monthly roadmap check-ins across teams (not just within teams).
```

**Large company (200+ engineers, multiple orgs):**

```
Typical situation:
  Each org/team has a roadmap. Teams have tech leads and PMs.
  Staff engineers run cross-team technical strategy.
  Annual planning cycles (OKRs, H1/H2 roadmaps).

Challenge:
  Long planning cycles mean foundational work decisions are made annually,
  not quarterly. Urgency gets lost in the planning process.
  
  "We'll add that to next year's planning" is how technical debt accumulates
  at large companies.

What to do:
  Staff engineers need to champion foundational investments through the
  annual planning cycle by: building the business case early (not last minute),
  tying technical investments to company-level OKRs, and having allies in
  product who understand the trade-offs.
  
  At this scale, roadmap alignment is a political skill as much as a
  technical one.
```

**Brainstorming Questions:**
1. How would you introduce a quarterly roadmap process at a startup that currently has no formal planning? What's the minimum viable version that adds value without adding bureaucracy?
2. At a large company, a critical foundational investment keeps getting "pushed to next year" in annual planning. What can a staff engineer do to get it prioritized in the current cycle?
3. What are the unique roadmapping challenges of a platform team (whose "customers" are internal engineering teams rather than users)?
4. You join a new team as a senior engineer. They have no roadmap, no tech debt inventory, and no planning process. What would you prioritize setting up first, and why?

---

## Part 19: The Roadmap and Engineering Culture

*(L5 → L6 level)*

A roadmap is more than a planning artifact. The way a team plans reflects and shapes its engineering culture. The roadmap process teaches the team what's valued, what's rewarded, and how decisions are made.

**Roadmapping signals culture:**

```
CULTURE SIGNAL: How is foundational work treated?

  If foundational work is always "next quarter":
    → Culture: shipping features is the only thing that counts.
    → Engineers learn: don't raise technical concerns, just build.
    → Result: technical debt accumulates; experienced engineers leave.

  If foundational work is scheduled alongside feature work:
    → Culture: quality and velocity are both valued.
    → Engineers learn: raising technical concerns is welcome and respected.
    → Result: engineers invest in the codebase; it stays healthy.

CULTURE SIGNAL: Who participates in roadmap planning?

  If only EM + PM decide:
    → Engineers feel like order-takers, not owners.
    → Technical input is missing from planning (risk of unrealistic estimates).
    
  If engineers participate in defining what goes on the roadmap:
    → Engineers feel ownership over the direction.
    → Better estimates because engineers who do the work contribute the numbers.
    → Technical context improves product decisions.
```

**The "no surprises" principle:**

A well-run roadmapping process means no one is surprised at the end of the quarter. Stakeholders knew what was planned. Engineers knew what was committed. Changes were communicated as they happened.

```
Signs of a healthy roadmapping culture:
  ✅ End-of-quarter delivery matches mid-quarter predictions
  ✅ Changes to roadmap are communicated within 1 week of being known
  ✅ Engineers can describe the team's priorities without looking at the doc
  ✅ Foundational work shows up on the roadmap, not just feature work
  ✅ "What's NOT on the roadmap" is an explicit and visible list

Signs of a broken roadmapping culture:
  ❌ Nobody knows what "the roadmap" is
  ❌ The roadmap doc is 6 months old and clearly wrong
  ❌ End of quarter: "we deprioritized half the roadmap"
  ❌ Foundational work is always "next quarter"
  ❌ Engineers feel like the roadmap doesn't reflect reality
```

**The engineer's role in culture:**

At L3/L4: participate honestly. Provide good estimates. Flag risks early.

At L5: actively shape the process. If the roadmap culture is broken, diagnose why and propose a fix — don't just complain about it.

At L6: define the standards for roadmapping across teams. The staff engineer creates the template, coaches tech leads on the process, and holds the bar for quality of planning artifacts across the organization.

**Brainstorming Questions:**
1. What does the way your current team plans tell you about its engineering culture? Is the roadmap process a strength or a weakness?
2. You notice that engineers on your team don't read the roadmap after it's published. Why might this happen? What would you change to make the roadmap a living document the team actually uses?
3. How does psychological safety relate to roadmapping? Specifically: why might engineers NOT raise technical concerns in planning if the culture is wrong?
4. A team you're joining has a tradition of "sprint commitments" — the team commits to completing everything in the sprint, no exceptions. This creates predictability but leaves zero room for unplanned work. How do you evaluate this practice?

---

## Part 20: Tooling — How Teams Actually Track Roadmaps

*(Practical, L4 → L5 level)*

Knowing the conceptual framework for roadmaps is step one. Knowing how teams actually implement it in practice is equally important.

**Common tools and their trade-offs:**

```
NOTION / CONFLUENCE (wiki-style docs)
  Pros:  Free-form, easy to structure, good for text-heavy strategy docs,
         version history, commenting for async review.
  Cons:  No native project tracking (tasks, status), can become stale fast,
         hard to visualize timeline.
  Best for: technical strategy docs, team wikis, meeting notes.

JIRA / LINEAR (issue trackers)
  Pros:  Built for task tracking, sprint planning, status tracking at granularity.
         Good for "what is being worked on right now."
  Cons:  Poor for strategic narrative, roadmap view is bolted on,
         can create false precision (story points ≠ delivery dates).
  Best for: sprint-level task tracking, bug tracking, cross-team dependencies.

PRODUCTBOARD / AHA! / ROADMUNK (roadmap tools)
  Pros:  Timeline views, dependency visualization, stakeholder-facing views.
  Cons:  Expensive, primarily built for product roadmaps (not engineering),
         can overformalize the process.
  Best for: product-engineering combined roadmap in growth/large companies.

SIMPLE SPREADSHEET OR DOC (e.g., Google Sheets / Docs)
  Pros:  Fast, low-friction, everyone can edit, no tool overhead.
  Cons:  No automation, no visualization, can become disorganized.
  Best for: startups, small teams, quarterly planning in simple format.

LINEAR (for engineering teams)
  Pros:  Modern issue tracker, good for engineering team workflow,
         cycles (sprints), project-level views.
  Cons:  Less suited for stakeholder-facing roadmap communication.
  Best for: engineering team's day-to-day work tracking.
```

**The recommendation:**

```
For quarterly roadmaps: use a doc (Notion or Confluence or Google Docs).
  Simple, human-readable, easy to share with non-engineers.
  
For sprint/task tracking: use Linear or Jira.
  Granular task management for engineers.
  
For stakeholder communication: extract a 1-page summary from the doc.
  Don't make stakeholders navigate your engineering tool.

For technical strategy: doc (Notion or Confluence).
  Long-form writing, version history, review comments.
```

**The anti-patterns in tooling:**

```
❌ The roadmap lives only in someone's head ("we discussed it in planning")
❌ The roadmap is a 200-item Jira backlog with no priority or dates
❌ The roadmap is a 60-slide deck that nobody reads
❌ Three different "roadmaps" exist and they contradict each other
❌ The roadmap tool is so complex nobody updates it
   (if updating the roadmap takes > 15 minutes, the tool is wrong)
```

**Brainstorming Questions:**
1. Your team uses Jira for all planning, including the roadmap. A product manager complains they can't get a "big picture" view. What would you propose?
2. A team has a beautiful roadmap in a dedicated roadmap tool that's always out of date. Another team has a simple Google Doc that's always current. What does this tell you about what matters in roadmap tooling?
3. How do you handle a situation where engineering tracks work in Linear and product tracks roadmap in Productboard, and they don't match?
4. What is the minimum viable roadmap artifact — the simplest thing that would genuinely help a team coordinate? What would it contain?

---

## Appendix A: The Roadmapping Quick Reference

```
QUARTERLY ROADMAP INPUTS:
  □ Product roadmap (what features?)
  □ Tech debt inventory (top 3-5 items to address)
  □ Incident history (what broke? what's likely to break?)
  □ Capacity calculation (total weeks × 80% × 70/20/10 split)
  □ Dependency map (what do we need from other teams?)

QUARTERLY ROADMAP STRUCTURE:
  □ Capacity summary (total, feature %, foundational %)
  □ Feature initiatives (with milestone definitions and dependencies)
  □ Foundational initiatives (with milestone definitions and business case)
  □ Exploration / PoC (with expected output)
  □ What's NOT on the roadmap (explicit deferral list)

SEQUENCING CHECKLIST:
  □ Map all dependency chains (A before B, B before C)
  □ Put risky work early (first 4 weeks, not last 4)
  □ Put unblocking work first (what are other teams waiting for?)
  □ Validate cross-team dependencies are on partner teams' roadmaps
  □ Leave buffer for unplanned work (don't plan > 80% capacity)

COMMUNICATION CADENCE:
  □ Weekly: brief team standup update
  □ Monthly: 1-paragraph written update to stakeholders
  □ Mid-quarter: explicit "at-risk" flagging if anything slipping
  □ End of quarter: retro on delivery vs. plan + lessons learned

MAKING THE CASE FOR FOUNDATIONAL WORK:
  □ Incident prevention (data: trending metrics, capacity limits)
  □ Velocity unlock (data: time lost to pain point × weeks × engineers)
  □ Platform multiplier (data: teams unblocked × time saved each)
  □ Risk quantification (data: compliance/security exposure cost)
```

---

## Appendix B: The Staff Engineer's Roadmapping Contribution

This appendix is specifically for engineers at or approaching L5, who are asking: "what is my specific contribution to the roadmap process?"

**What L5 owns (not EM, not PM):**

```
TECHNICAL JUDGMENT
  The EM and PM cannot evaluate technical complexity and risk alone.
  You are the technical authority in the room.
  You estimate accurately (don't sandbag, don't overcommit).
  You flag technical dependencies before they become blockers.
  You say "this feature requires X foundational work first" — and you're right.

TECH DEBT ADVOCACY
  Product managers will not advocate for foundational work.
  That advocacy falls to you.
  You maintain the tech debt inventory.
  You build the business case.
  You pick the right moment to raise it.

SEQUENCING WISDOM
  You know which projects are high-risk.
  You know which work unblocks other teams.
  You know which "quick" features are actually architecture changes in disguise.
  You surface this in planning, not after commitments are made.

TECHNICAL STRATEGY INPUT
  When staff engineers define technical strategy, your job is to
  push back on things you know won't work, propose alternatives you've seen
  work elsewhere, and ensure the strategy is grounded in technical reality.
```

**What L5 does NOT own:**

```
NOT YOUR JOB: Deciding which features to build
  That's product's job. You contribute to the conversation but don't dictate.

NOT YOUR JOB: Managing the EM's relationship with stakeholders
  You can support the EM, but don't go around them.

NOT YOUR JOB: Sprint-level task assignment
  If you're assigning tasks to individual engineers, you've dropped into
  management and out of technical leadership. Delegate that to the EM.
```

---

---

## Appendix C: The OKR Connection — Linking Roadmap to Company Goals

Most tech companies use OKRs (Objectives and Key Results) to set and track goals. The technical roadmap must connect to OKRs or it will be seen as engineering doing whatever it wants, disconnected from business outcomes.

**What OKRs are:**

```
Objective: a qualitative, ambitious goal.
  Example: "Make our platform reliable enough for enterprise customers."

Key Results: measurable outcomes that indicate the objective is being achieved.
  KR1: "p99 API latency < 100ms (currently 450ms)"
  KR2: "99.9% uptime in Q3 (currently 99.6%)"
  KR3: "Zero Sev-1 incidents caused by infrastructure in Q3 (currently 2/quarter)"
```

**How the roadmap connects to OKRs:**

Each roadmap initiative should trace to an OKR. This forces the question: "why are we doing this?" And more importantly: it enables you to argue for foundational work by connecting it to a KR that leadership cares about.

```
Technical roadmap initiative → KR it contributes to → Objective it serves

"Database migration" → KR2 (99.9% uptime) → "Reliable platform for enterprise"
"Auth refactor" → KR1 (p99 < 100ms), KR2 (99.9% uptime) → "Reliable platform"
"Feature: SSO" → supports customer contracts → "Enterprise readiness"
```

If a roadmap initiative doesn't trace to any OKR: question whether it should be on the roadmap at all.

If an OKR has no roadmap initiatives pointing to it: it's a wish, not a plan.

**The OKR planning cycle and the technical roadmap:**

```
Typical cycle at large companies:
  Q4 of current year: plan OKRs for next year
  January: OKRs finalized
  Each quarter: roadmap derived from the OKRs
  
Where engineers often fall down:
  They know the OKRs but don't connect roadmap items to them.
  The roadmap is "what we're building" but not "why it matters for the OKRs."
  
  Result: leadership sees the roadmap and can't tell if engineering is
  working on the right things.

Where staff engineers add value:
  They ensure the mapping is explicit.
  "Auth refactor" isn't on the roadmap because "it's tech debt."
  It's on the roadmap because KR2 (99.9% uptime) requires it, and
  the auth service accounts for 40% of current downtime incidents.
```

**Brainstorming Questions:**
1. Your company's top OKR is "grow revenue 50% this year." Your team wants to invest 20% of capacity in foundational reliability work. How do you connect the reliability work to the revenue OKR to justify the investment?
2. An OKR says "reduce p99 latency by 50%." The roadmap has 3 initiatives that each claim to contribute to this KR. How do you determine which one will have the most impact?
3. Mid-year, your company changes its top OKR due to a strategic pivot. How does this force a re-evaluation of your technical roadmap?
4. Some engineering work clearly has no direct connection to an OKR (e.g., upgrading dependency versions for security). How do you handle this in OKR-driven planning?

---

## Appendix D: Scenario Walkthroughs

These are complete mini-scenarios to practice applying the framework. Read each one, form your own answer, then compare to the suggested approach.

**Scenario 1: The burning platform**

You join a team as a staff engineer. The system is in trouble: 5 on-call incidents per week, deployment takes 2 hours and fails 30% of the time, the codebase hasn't been touched by half the services in 2 years. The product roadmap is full.

*Your job: build a 2-quarter plan that stabilizes the platform without blocking all product work.*

```
Suggested approach:
  Q3: triage mode
    Feature capacity: 50% (not 70%) — explicitly negotiate this reduction
    Why: the instability makes 70% feature work impossible; incidents are
         consuming 30%+ of capacity anyway
    
    Foundational (40%):
      1. On-call reduction: find the top 3 alert sources, fix each.
         Goal: from 5 incidents/week to < 1/week.
      2. Deployment pipeline: fix the failure rate.
         Goal: from 30% failure rate to < 5%.
    
    Metric: by end of Q3, on-call burden reduced enough that 70% feature
            capacity is actually achievable in Q4.

  Q4: return to normal
    Feature capacity: 70%
    Foundational (20%): service modernization (oldest services first)
    
  Key argument to make:
    "We cannot deliver 70% feature capacity while the system is on fire.
     The on-call burden is already consuming 25% of engineering time.
     The real feature delivery is 45%, not 70%.
     By investing 40% in stabilization this quarter, we get to genuine
     70% feature delivery next quarter — a net gain."
```

**Scenario 2: The conflicting priorities**

Your team has two "top priority" projects from two different product managers. Both are "urgent." Both will take 4 weeks. You have 4 weeks of feature capacity this quarter.

*Your job: navigate the conflict and produce a workable plan.*

```
Suggested approach:
  Step 1: Clarify the business impact of each project.
    "What metric does project A improve by when?"
    "What metric does project B improve by when?"
    "What happens if A is delayed 1 quarter? What happens if B is delayed?"
  
  Step 2: Check for a dependency.
    Is one project a prerequisite for the other?
    If A enables B, do A first.
  
  Step 3: Escalate to the right decision-maker.
    "I have two 'top priority' projects and capacity for one this quarter.
     I've analyzed the trade-offs and recommend A because [specific reason].
     I need a decision from [PM A + PM B + EM] by Thursday so we can plan."
    
    Don't try to solve this yourself — this is a prioritization decision
    that involves the business, not just engineering.
  
  Step 4: Document the decision.
    "We're doing A this quarter. B is Q4. Here's why."
    The reasoning for the deferral is in the roadmap doc.
```

**Scenario 3: The invisible technical investment**

You've identified a platform investment that would save the entire engineering org 20 engineer-weeks per quarter. But it requires 6 engineer-weeks of upfront work with no visible user-facing output. How do you make this happen?

```
Suggested approach:
  Step 1: Quantify the benefit precisely.
    "20 engineer-weeks/quarter" is the claim. Validate it.
    Survey engineers: "how much time do you spend on [pain point] per week?"
    Extrapolate: N engineers × hours/week × 12 weeks = total.
    This is your data.
  
  Step 2: Calculate the payback period.
    6 weeks invested → saves 20 weeks/quarter.
    Payback: < 1 quarter.
    3-year value: 20 weeks/quarter × 12 quarters = 240 engineer-weeks saved.
    
    This is a 40× return on investment. Make this the headline.
  
  Step 3: Find the right sponsor.
    Who owns the metrics this improves? (Velocity? Engineering quality?)
    Make them the champion, not just you.
  
  Step 4: Put it on the roadmap with the business case attached.
    "Platform investment: CI pipeline improvement.
     Cost: 6 engineer-weeks in Q3.
     Benefit: 20 engineer-weeks/quarter saved starting Q4.
     ROI: 40× over 3 years."
    
    Nobody can argue with a 40× ROI when the data is solid.
```

---

## Final Note: Roadmapping as a Senior Engineering Skill

Most engineers think of roadmapping as something done TO them — a list of things they're assigned to build. Senior engineers understand it as something they actively shape — a tool for translating technical understanding into strategic decisions.

The engineers who advance to staff level are almost always the ones who:
- Raise technical risks before they become incidents
- Make the case for foundational work with data, not just intuition
- Connect engineering decisions to business outcomes
- Communicate clearly to stakeholders who don't have technical background
- Build trust by delivering what they commit to and flagging problems early

A roadmap is a communication tool. Build it with your team. Update it honestly. Use it to have better conversations about what matters, in what order, and why.

The best roadmap is the one that makes the right trade-offs obvious — even to people who aren't engineers.

---

## Appendix E: Interview Answer Patterns — SOAR Format

When asked roadmapping questions in system design or behavioral interviews, use the SOAR format: Situation → Objective → Action → Result.

**Template for "Tell me about a time you influenced engineering direction":**

```
SITUATION:
  At [company], our [system/team] was experiencing [specific problem].
  The impact was: [measurable business impact — not just "it was slow"].

OBJECTIVE:
  I was asked to [define the ask] OR I identified that [what needed to happen].
  The goal was: [specific, measurable outcome].

ACTION:
  1. [First thing you did — usually: gathered data, defined the problem clearly]
  2. [Built the case — how you quantified the benefit of foundational investment]
  3. [Got alignment — how you worked with product/EM/stakeholders]
  4. [Executed — what specifically was done]

RESULT:
  [Measurable outcome: metric improved, velocity increased, incidents reduced]
  [Longer-term impact: what did it enable?]
  
Example:
  SITUATION: "At [company], our deployment pipeline took 50 minutes and failed
  30% of the time. Engineers were losing 2-3 hours/day to pipeline failures."

  OBJECTIVE: "I wanted to reduce deployment time below 10 minutes and failure
  rate below 5%."

  ACTION: "I first quantified the cost: 15 engineers × 2.5 hours/day × 5 days
  = 187.5 engineer-hours/week lost = roughly 5 engineer-weeks/quarter.
  I built a proposal and connected it to the company's OKR on engineering
  velocity. I got 3 weeks of capacity approved in Q2 planning.
  We rebuilt the pipeline on GitHub Actions with parallel test execution."

  RESULT: "Deployment time dropped from 50 minutes to 8 minutes. Failure rate
  dropped from 30% to 2%. The team shipped 20% more feature work in Q3 and
  Q4 compared to the prior two quarters."
```

**Template for "How do you prioritize technical work vs. product work?":**

```
"I use an explicit investment ratio — 70% feature, 20% foundational, 10% exploration —
and make it visible in the roadmap so there's a shared agreement that foundational
work IS planned, not just hoped for.

For the foundational 20%, I prioritize based on: is this preventing an incident,
unlocking feature velocity, or reducing engineering risk? I quantify each using
data: incident history, developer time surveys, capacity trending.

I connect the foundational work to product OKRs wherever possible — reliability
work ties to uptime targets, infrastructure work ties to velocity targets.
The goal is to make foundational investment legible to product stakeholders
as a business decision, not an engineering preference."
```

---

## Appendix F: 15-Minute Roadmap Preparation Drill

Use this drill before any interview or planning conversation about engineering roadmapping. It takes 15 minutes and covers all the key angles.

```
THE DRILL (15 minutes):

1. Name the team (2 min)
   What is the team's mission? What product does it serve?
   How many engineers? What's the current technical health?

2. Name the top product priority (2 min)
   What is the most important thing product wants this quarter?
   What metric does it move? What's the business case?

3. Name the top foundational priority (2 min)
   What is the most important technical investment the team needs?
   What data supports prioritizing it?
   What's the business argument (incident prevention / velocity unlock / risk)?

4. Name the biggest dependency (2 min)
   What work requires another team to deliver first?
   Is that on their roadmap? Who would you talk to to confirm?

5. Name one risk (2 min)
   What is the most likely thing to cause the roadmap to slip?
   How do you mitigate it?

6. Name the metric for success (1 min)
   How will you know at the end of the quarter whether the roadmap succeeded?
   One metric, one number.

7. Name one thing NOT on the roadmap and why (2 min)
   What was considered and intentionally deferred?
   Why?

Total: ~13 minutes. Fills the remaining 2 minutes with cleanup.
After this drill, you can answer almost any roadmapping question in an interview.
```

---

## Appendix G: Companion Framework Summary

A one-page visual summary of the frameworks introduced in this chapter.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  CHAPTER 124 FRAMEWORK SUMMARY                             │
├───────────────────────────┬─────────────────────────────────────────────────┤
│  70/20/10 RULE            │ Feature: 70%  Foundation: 20%  Explore: 10%    │
│  (investment ratio)       │ Make it explicit in the roadmap doc.            │
├───────────────────────────┼─────────────────────────────────────────────────┤
│  PLANNING HORIZONS        │ Sprint (now) → Quarter → Year → Multi-year     │
│                           │ Different owners, different granularity.        │
├───────────────────────────┼─────────────────────────────────────────────────┤
│  SEQUENCING PRINCIPLES    │ 1. Unblock others first                         │
│                           │ 2. Foundation before feature                    │
│                           │ 3. Riskiest work early                          │
│                           │ 4. Dependencies define order                    │
│                           │ 5. Migrations before greenfield                 │
├───────────────────────────┼─────────────────────────────────────────────────┤
│  FOUNDATIONAL WORK        │ 1. Incident prevention (data: trends)           │
│  ARGUMENTS                │ 2. Velocity unlock (data: time lost/week)       │
│                           │ 3. Platform multiplier (data: teams × time)     │
│                           │ 4. Risk quantification (data: exposure cost)    │
├───────────────────────────┼─────────────────────────────────────────────────┤
│  TECH DEBT PRIORITY       │ Score = Impact × Urgency × (1/Cost)             │
│  SCORING                  │ High score = prioritize this quarter            │
├───────────────────────────┼─────────────────────────────────────────────────┤
│  ROADMAP ANTI-PATTERNS    │ 100% capacity planned; no milestone definition; │
│                           │ ignored dependencies; wish list not commitment; │
│                           │ foundational work without done criteria         │
├───────────────────────────┼─────────────────────────────────────────────────┤
│  COMMUNICATION CADENCE    │ Weekly (standup); Monthly (1-paragraph);        │
│                           │ Mid-quarter (at-risk flag); End-of-quarter      │
│                           │ (retro + next quarter draft)                    │
├───────────────────────────┼─────────────────────────────────────────────────┤
│  L5 OWNS                  │ Team quarterly roadmap; tech debt inventory;    │
│                           │ foundational work advocacy; technical strategy  │
│                           │ doc for team scope; alignment with product.     │
├───────────────────────────┼─────────────────────────────────────────────────┤
│  L6 OWNS                  │ Multi-year technical vision; org-wide strategy; │
│                           │ technology radar; engineering investment ratios  │
│                           │ at company level; cross-team sequencing.        │
└───────────────────────────┴─────────────────────────────────────────────────┘
```

---

---

## Appendix H: The "Stop Doing" List

Great roadmaps include not just what to start, but what to stop. Explicitly sunsetting work that no longer serves the team is as important as adding new work. Without a stop-doing list, teams accumulate obligations that never get retired.

**Things worth stopping (examples):**
- A weekly report nobody reads → auto-generate or eliminate
- A service maintained for one internal team whose use case is now covered by a platform feature
- A manual QA process that a test suite now covers
- A data pipeline feeding a dashboard nobody has opened in 90 days (check access logs)
- A feature flag for a rollout that completed 8 months ago (the code should be permanent or removed, not flagged)

**How to build the stop-doing list:**
1. At end of every quarter, ask: "What did we work on that nobody would notice if we stopped?"
2. Check server logs and dashboards for unused endpoints and services.
3. Ask product: "Which features have zero user engagement in the last 90 days?"
4. Review on-call runbooks: are any of these alerts for systems that could be decommissioned?

Every item you stop doing frees capacity for what actually matters. Roadmapping is not just about adding — it's about making hard choices to subtract.

**Brainstorming Questions:**
1. In your current role, what are 3 things your team does regularly that you suspect nobody would notice if they stopped? How would you validate this suspicion before stopping?
2. A team is nervous about stopping a service because "someone might be using it." What process would you use to safely decommission a service without causing an incident?
3. The "stop doing" list requires someone to make the call that work is no longer valuable. Who should own this decision? What happens when multiple stakeholders disagree?
4. Product asks to decommission a feature that engineering is proud of but that has low usage. How do you handle this conversation gracefully?

---

## The One Rule to Remember

If there is one rule from this entire chapter worth memorizing, it is this:

**A roadmap that nobody updates is worse than no roadmap.**

A stale roadmap creates false confidence. Stakeholders think the commitments are real; engineers know they're not. That gap — between what's written and what's true — erodes trust faster than having no plan at all.

Update your roadmap when things change. Communicate changes early. Be honest about what's slipping and why. A roadmap that reflects reality — even an imperfect or behind-schedule reality — is a powerful tool for building the kind of trust that lets engineering teams make the long-term investments they need to make.

The best engineering teams aren't the ones that never miss a roadmap. They're the ones that communicate clearly, adapt quickly, and use their roadmap as a conversation tool rather than a commitment stone.

That's what this chapter is really about: not the artifact, but the conversations it enables.

**The ask for the next conversation:** Before your next planning meeting or 1:1 with your manager, write down the answer to two questions: (1) What is the single most important technical investment your team should make this quarter? (2) What is the business argument for making it now, rather than later? If you can answer both in 3 sentences each, you're ready to advocate for it. If you can't, the investment isn't well-enough defined yet — and that's a signal too.

The engineers who make this habit — consistently framing technical needs in business terms, preparing before planning conversations, building the business case with data — are the ones who reliably get the foundational investments their teams need. Not because they're louder, but because they're clearer.

Clarity is the senior engineer's most underrated tool. And a well-built roadmap — honest, prioritized, communicated — is clarity made concrete.

If you remember one thing from this chapter, let it be this: the roadmap is not a bureaucratic artifact. It is how your team decides what matters, communicates that decision, and holds itself accountable over time. Done well, it is one of the most powerful tools you have.

Done poorly — stale, disconnected from reality, never updated — it is worse than having no plan at all. The difference is not talent. It is the habit of keeping it honest.

And honesty is the one skill no framework can substitute for. You can learn the 70/20/10 rule, the sequencing principles, the OKR connection — but none of it matters if the roadmap is a performance rather than a commitment. Make it real. Keep it current. Use it as the foundation for every important planning conversation your team has. That is how the best engineering organizations operate at the highest levels, and it is available to every team, at every scale, starting today.

The frameworks are the scaffolding. Honesty is the building.

Build real things. Plan honestly. Ship what you commit to. That is the entire discipline in three sentences.

---

## Exercises

**Exercise 1 — Feature vs. foundational split.** Your team has 20 engineer-sprints next quarter. Product wants 15 sprints of features. Engineering needs 8 sprints of foundational work. Design the negotiation: what data do you bring, how do you frame foundational work in business terms, and what's your minimum acceptable foundational allocation?

**Exercise 2 — Roadmap prioritization.** You have 10 technical roadmap items. Score each: business impact (1-5) × urgency (1-5) ÷ effort (1-5). Do the resulting priorities feel right? Where does the formula break down? What items need manual override and why?

**Exercise 3 — Stakeholder communication.** You've finished your quarterly roadmap. Write three one-paragraph summaries: for your engineering team, for the product manager, and for the VP. What changes between versions? What must stay consistent?

**Exercise 4 — Risk tracking design.** Your roadmap has a high-risk authentication migration. Design risk tracking: leading indicators that show the migration is on track vs. in trouble, early warning system, and contingency if the migration slips 4 weeks.

**Exercise 5 — Roadmap retrospective.** Find a quarterly roadmap from the past. What was planned vs. delivered? What caused gaps? What planning assumption was wrong? Write a one-paragraph lessons-learned.

**Exercise 6 — Strategy document.** Write a 1-page technical strategy for your team for the next 12 months: the problem you're solving, 3 bets you're making, 2 things explicitly deprioritized, and how you'll measure success.

---

## Homework

**Assignment 1 — Write next quarter's technical roadmap.** Draft a roadmap using this chapter's framework: items with business justification, effort estimates, dependencies, risk flags. Present it in a team meeting and collect feedback.

**Assignment 2 — Annual technical strategy.** Write a 2-page technical strategy for the next year. What's the one technical bet that unlocks the most value? What's the one reliability investment that prevents the most risk?

**Assignment 3 — Interview practice: roadmapping question.** Practice "how do you prioritize technical debt against new feature work" in 5 minutes. Cover: your framework for quantifying tech debt impact, how you communicate it to product, and a specific example.

**Assignment 4 — Read "An Elegant Puzzle" (Will Larson), Part 3 on Strategy.** Write a one-paragraph summary of how Will Larson recommends writing engineering strategy and how it connects to quarterly roadmapping.

*Pairs with [Chapter 123: Technology Evaluation Framework](Chapter_123_Technology_Evaluation_Framework.md) and [Chapter 119: Promotion and Career Navigation](Chapter_119_Promotion_and_Career_Navigation.md). Next: [Chapter 125: Interview Execution Meta-Skills](../section8/Chapter_125_Interview_Execution_Meta_Skills.md).*

*Pairs with [Chapter 123: Technology Evaluation Framework](Chapter_123_Technology_Evaluation_Framework.md) (evaluation feeds the roadmap) and [Chapter 119: Promotion and Career Navigation](Chapter_119_Promotion_and_Career_Navigation.md) (roadmapping ability is a key L5→L6 signal). Next: [Chapter 125: Interview Execution Meta-Skills](../section8/Chapter_125_Interview_Execution_Meta_Skills.md).*