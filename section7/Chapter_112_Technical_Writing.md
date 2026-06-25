# Chapter 112: Technical Writing, RFCs, and Influence Through Writing

> **Section 7: Engineering Excellence**
> *The engineer who can write clearly has 10× the influence of the engineer who cannot. Writing is not a soft skill — it is a force multiplier.*

---

```
╔══════════════════════════════════════════════════════════════════════╗
║              CHAPTER 112 — AT A GLANCE                              ║
╠══════════════════════════════════════════════════════════════════════╣
║  CORE THESIS: You write once; 50 people read it. Every hour spent   ║
║  writing clearly is an hour that compounds — you answer the same     ║
║  question once instead of 50 times. Writing is how senior engineers  ║
║  scale influence beyond their immediate team.                        ║
╠══════════════════════════════════════════════════════════════════════╣
║  DOCUMENTS COVERED:                                                  ║
║    Design Doc · RFC · ADR · Post-Mortem · Runbook                   ║
╠══════════════════════════════════════════════════════════════════════╣
║  THE L6 WRITING INSIGHT:                                             ║
║    L5 writes the solution. L6 writes the problem + solution +        ║
║    alternatives + tradeoffs + what could go wrong. The document      ║
║    that includes "alternatives considered" is the one that earns     ║
║    trust from a senior audience.                                     ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Overview

Writing is the primary medium through which senior engineers exercise influence at scale. Code affects the systems it runs. A design document affects every engineer who works on related systems for the next three years. A post-mortem that correctly identifies a systemic failure changes the entire organization's practices. A well-written RFC shifts architectural decisions across multiple teams.

Yet most engineers — even experienced ones — write poorly. Not because they lack intelligence, but because they were never taught to write for engineers, they conflate "writing" with "documenting," and they underestimate how much rewriting is part of writing.

This chapter covers the five most important forms of technical writing: design docs, RFCs, ADRs, post-mortems, and runbooks. For each, it covers structure, what to include, what to cut, and the difference between documents that change outcomes and documents that satisfy a checklist.

---

## Part 1: Why Technical Writing Is a Staff/L6 Skill

**The asymmetry of influence:** When you explain something verbally in a meeting, it reaches the 8 people in the room. When you write it as a design doc, it reaches everyone who reads the doc — now, and for the next three years. A well-placed sentence in a design doc can redirect weeks of engineering work by 12 engineers. No verbal explanation has that leverage.

**The multiplication effect:** A senior engineer who is a strong writer effectively multiplies their influence 10–50×. A weak writer who is equally technically strong has their influence bounded by their 1:1 conversations and team meetings. At Staff/L6 and above, most of the impact comes through writing.

**The calibration signal:** Reviewers at Principal and Director level read your design docs and RFCs. They are constantly calibrating: "Does this engineer think clearly? Do they anticipate objections? Do they understand the tradeoffs?" A great document signals senior judgment even before you've met the person. A mediocre document signals the opposite.

**Why great engineers often write poorly:**
1. They think in code, not prose. The logic that works in a function doesn't always work in a sentence.
2. They front-load context instead of conclusions. Engineers are trained to show their work; writing requires showing the conclusion first and evidence second.
3. They confuse completeness with clarity. A thorough document that buries the key decision in paragraph 18 has failed its readers.
4. They write for themselves (to record their thinking) rather than for the reader (who needs to take action or make a decision).

**The three audiences:** Every technical document has three audiences, and clarity requires knowing which you're writing for:
- **Your team** (primary): needs to build what you're proposing. Cares about implementation details, timelines, risks.
- **Adjacent teams** (secondary): needs to know the API boundaries, data contracts, dependencies. Cares about what changes for them.
- **Future-you** (permanent): returns in 18 months and needs to understand what was decided and why. Cares about the reasoning, not just the outcome.

---

## Part 2: The Design Document

A design document is the most common form of technical writing at Google-scale companies. It is not approval documentation — it is alignment documentation. The process of writing a design doc forces you to think through the problem completely. The process of getting feedback surfaces assumptions you didn't know you were making.

**What a design doc is for:** Alignment, not approval. You write a design doc because you need the team (and sometimes adjacent teams or leadership) to have the same mental model of what you're building and why. A design doc that is approved but not read has failed. A design doc that is controversial and generates 40 comments has succeeded — those 40 comments are assumptions being made explicit.

**The 6-part structure:**

```
1. Problem Statement
   One paragraph. What is broken or missing? What is the user/system impact?
   Be specific: "P95 checkout latency is 4s; our SLA is 1s" not "checkout is slow."

2. Goals and Non-Goals
   Goals: what this design achieves. Measurable when possible.
   Non-Goals: explicit scope boundaries. "This design does not address X."
   Non-goals are critical — they prevent scope creep during review.

3. Proposed Design
   The solution. Include diagrams. Explain the key architectural decisions.
   Not every implementation detail — the decisions that matter.

4. Alternatives Considered
   2–3 alternatives you evaluated, with a clear "why we rejected this."
   This is where credibility is built with senior reviewers.
   Senior engineers always ask "what else did you consider?" If your doc
   answers it preemptively, you've already passed that filter.

5. Risks and Open Questions
   What could go wrong? What are you uncertain about?
   What needs to be decided before implementation starts?
   An honest risk section is respected; pretending there are no risks is not.

6. Timeline and Milestones
   What will be done by when? Who owns each piece?
   Rough is fine. The purpose is to make sure the scope matches the timeline.
```

**The 10x question:** Every design doc should answer: "What happens if this gets 10× more traffic/data/users?" If the answer is "it breaks," that should be in the document. If the answer is "we add more nodes (horizontally scalable)," say so explicitly. This question surfaces whether you've designed for the current need or for growth.

**Bad design doc vs good design doc — same problem:**

Bad:
> *"We will redesign the notification system to be faster and more reliable. The new system will use Kafka for message queuing and a new microservice for delivery. This will improve performance and scalability."*

Good:
> *"Problem: 15% of notifications are delivered >30 seconds late; users are abandoning the checkout flow after a payment confirmation delay (measured: +8% checkout abandonment when notification takes >10s). Root cause: the notifications table in the main Postgres DB is hot — writes block reads; the notification processor is a cron job that runs every 60s.*
> 
> *Proposed design: decouple notification events from DB polling. Payment service publishes a `payment.confirmed` event to Kafka; a dedicated notification service subscribes and sends within 1s. DB write is now async (event-sourced). P95 latency target: <2s.*
> 
> *Alternative considered: add a read replica for notifications polling. Rejected — reduces DB load but doesn't fix the 60s polling interval. P95 latency would become ~60s, not <2s. Kafka approach achieves the <2s target.*
> 
> *Risk: Kafka adds operational complexity. If the notification service falls behind, notifications queue up. Mitigations: dead-letter queue + alert at 10K queue depth + fallback to DB polling on consumer crash (circuit breaker)."*

The good version is longer, but every sentence is doing work.

**When NOT to write a design doc:**
- A bug fix or small refactor (no architectural decision)
- Something already decided by a senior engineer (the decision isn't open)
- A proof of concept (write the POC first; design doc after if it validates)
- A change affecting only one service owned entirely by your team (lightweight decision log is sufficient)

**Brainstorming Q1: "How do you write a design doc for something you haven't fully figured out yet?"**

Write the problem section and goals section first — those are always knowable. Write the risks and open questions section next — this captures what you don't know yet. Then write the alternatives section with what you do know. The proposed design section may start as "TBD pending feedback on open questions." The design doc then becomes an instrument for collecting input on the specific unknowns. This is far better than waiting until you have all the answers — it pulls stakeholders into the problem earlier and surfaces objections before you've committed code.

**Brainstorming Q2: "A senior engineer says your design doc is 'too detailed.' Another says it's 'too high level.' Who do you listen to?"**

Listen to both. "Too detailed" usually means the doc is answering questions the reviewer doesn't have — it's front-loading implementation concerns when the reviewer is still deciding whether the architecture is right. "Too high level" means the reviewer needs to understand the implementation to evaluate the design. The solution: the "executive summary" structure — put the conclusion (proposed design + key tradeoffs) in the first 20% of the doc; put the detailed design in the second 80%. The first reader gets what they need; the detailed reader gets what they need. The pyramid structure: most important first, evidence below.

---

## Part 3: The RFC (Request for Comments)

An RFC is a design document with a specific additional purpose: it explicitly invites input on open questions before a decision is made. RFCs are for architectural decisions that span teams or have long-lived consequences.

**RFC vs Design Doc:**

| Aspect                  | Design Doc                              | RFC                                      |
|-------------------------|-----------------------------------------|------------------------------------------|
| **Purpose**             | Record a decision + alignment           | Gather input before deciding             |
| **Decision state**      | Author has a proposal                   | Author has a question or proposal        |
| **Audience**            | Team + stakeholders                     | Broad community (org-wide, public)       |
| **Duration**            | Ongoing artifact                        | Time-bounded (comment period: 2 weeks)   |
| **Outcome**             | Implementation                          | Decision + design doc                    |
| **Controversy**         | Some controversy is fine                | Expected: controversy is the point       |

**How to write an RFC that gets useful feedback:**

The most common failure: writing an RFC that is actually a design doc with a "comments welcome" note. Nobody knows what you actually want feedback on. The result: silence (nobody wants to contradict the implied conclusion) or unstructured commentary (people comment on things you've already decided).

Structure for getting useful feedback:
```
Section 1: Background (2 paragraphs maximum)
  What context does the reader need? Assume they don't know the system.
  
Section 2: The Question (explicit)
  "We need to decide: Option A (description) or Option B (description) or Option C."
  This tells reviewers exactly what you need from them.
  
Section 3: What I Know
  Evidence and analysis you've done. Facts, not conclusions.
  
Section 4: My Tentative Recommendation (optional)
  If you have a preference, say so. It invites pushback on your reasoning.
  
Section 5: What Feedback I Need
  Explicit: "I need input on: (1) whether Option B violates the API contract for Team X,
  (2) whether the 5ms latency budget is acceptable for use case Y."
  Named reviewers where possible: "Priya — specifically asking for your read on (1)."

Section 6: Deadline
  "Comments by Friday EOD. I will decide by Monday."
  Without a deadline, RFCs collect comments forever and no decision gets made.
```

**Making the decision:** After the comment period, synthesize the feedback and make a decision. Acknowledge the disagreements that were raised. Explain what changed your thinking and what didn't. An RFC that ends in "I've thought about this more and still believe Option B is right, for these reasons [incorporating the new arguments]" is a well-closed RFC. An RFC that ends in "sounds good, moving forward" with no acknowledgment of the comments that were raised has failed.

---

## Part 4: The ADR (Architecture Decision Record)

An ADR is a permanent record of an architectural decision and the context that led to it. It is written for future engineers who inherit the codebase, not for current approval.

**Why ADRs exist:** Every codebase has decisions that seem arbitrary to newcomers but were made carefully for specific reasons. "Why does the payment service use Postgres instead of Cassandra? Why does the search service use Elasticsearch instead of our standard MySQL?" Without an ADR, the answer is "I don't know, that's just how it is" or worse, "someone tries to change it and breaks things." With an ADR, the answer is "see ADR-0042 — we chose Postgres because the payment service needs strong transactions and Cassandra's eventual consistency caused 0.1% double-charge incidents in the pilot."

**The 5-part ADR format:**

```markdown
# ADR-0042: Payment Service Uses Postgres, Not Cassandra

## Status
Accepted (2024-03-15)

## Context
The payment service writes transaction records and must prevent double-charges.
We evaluated Cassandra (our standard for high-throughput writes) and Postgres.
Cassandra's eventual consistency model caused 0.1% double-charge rate in a 
2-week pilot (Nov 2023) because concurrent writes to the same account could 
both succeed before replication converged.

## Decision
Use Postgres with serializable transactions for the payment service.

## Consequences
+ Strong consistency eliminates double-charge risk
+ Familiar to most backend engineers
− Lower write throughput than Cassandra (acceptable: payment volume is 500 TPS, 
  not the 50K TPS where Cassandra shines)
− Single-region primary; failover requires manual promotion (acceptable: payments
  can tolerate 30s downtime; Stripe's own SLA is 99.99% = 52 min/year)

## Alternatives Rejected
- **Cassandra:** Eventual consistency is incompatible with financial correctness.
- **MySQL:** Same strong consistency properties as Postgres, but Postgres has 
  better JSON support for our flexible transaction metadata schema.
```

**Where to store ADRs:** In the repository itself, in a `/docs/adr/` directory. Not in a wiki (wikis rot and lose history), not in a Confluence page (can't be code-reviewed), not in a Jira ticket (not searchable from the codebase). In the repo: every ADR has a commit, a PR history, and is immediately visible to engineers reading the code.

**When to write an ADR:**
- A significant technology choice (database, message queue, auth system)
- A significant design pattern choice (event sourcing vs CRUD, saga vs 2PC)
- A decision that was controversial and required explicit reasoning
- A decision that future engineers will likely want to reverse and should understand why we didn't

**When NOT to write an ADR:**
- Routine implementation choices (function naming, file structure)
- Decisions that are obvious given the constraints
- Decisions that are entirely reversible with minimal cost

---

## Part 5: The Post-Mortem

A post-mortem is the most important document an engineering team produces during an incident. Done well, it changes the system so the incident doesn't recur. Done poorly, it satisfies a process requirement while changing nothing.

**The difference that matters:** A post-mortem that identifies "the engineer deployed without testing" as root cause will result in a process checklist. A post-mortem that identifies "the deployment system had no automated testing gate, and our culture doesn't normalize pre-deploy testing because we have no staging environment" will result in actual system changes. The first post-mortem blames people; the second post-mortem changes systems. Only system changes stick.

**The anatomy of a useful post-mortem:**

```
1. Summary (3 sentences maximum)
   What broke. Duration. Impact in user/business terms.
   Example: "Checkout was unavailable for 47 minutes (11:32-12:19 PST).
   ~23,000 failed checkout attempts. $420K estimated revenue impact."

2. Timeline (facts only, chronological)
   11:32 — Deployment of checkout-service v2.4.1 started
   11:34 — Error rate rose to 5% (within normal deploy variance; no alert)
   11:41 — Error rate hit 85%; PagerDuty fired to on-call
   11:43 — On-call began investigation; initial hypothesis: database issue
   11:55 — Correct hypothesis: new config key missing in prod (present in staging)
   12:09 — Config key added to prod; errors immediately dropped to 0%
   12:11 — Monitoring confirmed recovery; incident declared resolved

   Rules for the timeline:
   - Chronological. Every time is in a single timezone.
   - Facts only. "Engineer investigated" not "engineer panicked."
   - Include when alerts fired and when they should have fired.
   - Include the moment of correct diagnosis, not just the fix.

3. Root Cause Analysis
   NOT: "A config key was missing."
   YES: "The deployment system does not validate that all required config keys
   exist in the target environment before deploying. The staging environment
   had the key (added manually during feature development) but it was never
   added to prod config. There is no automated check or schema for required
   config keys."

4. Contributing Factors
   - The config diff was not included in the deploy PR.
   - The error rate alert threshold (10%) took 9 minutes to fire.
   - The deployment validation step had been disabled 3 months ago
     to speed up deployments (tech debt).

5. Impact
   Quantify. Users affected, duration, revenue impact, SLA breach (yes/no).

6. Action Items (specific and verifiable)
   ✅ Owner: Priya. Deadline: 2024-03-22.
   "Add pre-deploy config validation step that fails deploy if any required
   config key is missing from target environment."
   
   ✅ Owner: James. Deadline: 2024-03-29.
   "Lower error rate alert threshold from 10% to 2%, with 3-minute evaluation
   window. Alert should have fired at 11:37."
   
   ✅ Owner: Team. Deadline: 2024-04-05.
   "Audit all services for manually-added staging configs not reflected in
   prod config templates. Fix any gaps found."
   
   NOT a valid action item: "Improve testing culture." (Not measurable.)
   NOT a valid action item: "Engineers should be more careful." (Blames people.)

7. What Went Well
   - On-call responded within 2 minutes of alert.
   - Customer support team was notified within 5 minutes of detection.
   - Rollback plan existed and was used effectively.
   This section is not optional — it reinforces the behaviors you want to keep.
```

**Blameless post-mortems:** The industry standard at Google, Amazon, and most high-functioning tech organizations is the blameless post-mortem. This doesn't mean no accountability — it means the system is held accountable, not the individual. "Why did the system allow a deploy to proceed without config validation?" not "why didn't the engineer check for missing configs?"

This matters because blame-based post-mortems:
1. Cause engineers to hide information during post-mortem interviews to protect themselves.
2. Lead to action items like "be more careful" that change nothing.
3. Punish risk-taking, causing engineers to avoid the innovative work that makes companies competitive.

**The 5 Whys in writing:**
```
Why was the config key missing?         → It was never added to prod.
Why was it never added to prod?         → Dev added it manually in staging but didn't update the template.
Why was there no template enforcement?  → Config templates are not validated before deploy.
Why are they not validated?             → Nobody owns config validation; it's always been manual.
Why has nobody owned it?                → No team was assigned responsibility for deploy tooling reliability.
Root cause: Ownership gap for deploy tooling reliability.
Action: Assign an owner (Platform team). Q2 OKR.
```

---

## Part 6: Runbooks

A runbook is for 2 AM. A wiki page is for Tuesday afternoon when you have time to read. They are completely different documents.

**The one rule of runbooks:** A runbook must be usable by someone who has never seen the system before, at 2 AM, under stress, with degraded systems affecting their ability to look things up. Every assumption of prior knowledge is a failure mode.

**Runbook vs wiki:**

| Dimension            | Runbook                                  | Wiki/Design Doc                         |
|----------------------|------------------------------------------|-----------------------------------------|
| **Reader state**     | Stressed, time-pressured, incident active| Calm, exploratory, learning mode        |
| **Navigation**       | Linear: step 1, step 2, step 3           | Hierarchical: concepts, then details    |
| **Assumption level** | Zero: explain every command              | High: assumes reader knows the system   |
| **Update cadence**   | Every incident, every change             | When the design changes                 |
| **Success metric**   | Incident resolved without asking anyone  | Engineer understands the system         |

**The anatomy of a useful runbook:**

```markdown
# Runbook: Checkout Service High Error Rate

## Symptom
- Alert: "checkout-service: error rate > 5% for 3 minutes"
- OR: User reports "checkout isn't working"
- OR: You see P95 latency > 2s in the checkout-latency dashboard

## Severity
- Error rate 5–20%: P2 (respond in 30 minutes)
- Error rate > 20%: P1 (respond immediately; page second responder)

## Step 1: Confirm the scope
Go to: https://internal-grafana/d/checkout-overview
Look at:
  - Which endpoints are failing? (Top panel, "Error rate by endpoint")
  - Are errors recent or ongoing for >5 minutes?
  - What is the user impact? (Bottom panel, "Failed checkouts per minute")

If errors are on /api/checkout/submit only → go to Step 2
If errors are on all /api/ endpoints → this is not a checkout issue. See runbook: [API Gateway Runbook](../api-gateway-runbook.md)

## Step 2: Check recent deployments
Run: `kubectl rollout history deployment/checkout-service -n production`
If a deployment happened in the last 30 minutes:
  → Rollback: `kubectl rollout undo deployment/checkout-service -n production`
  → Wait 2 minutes. Check error rate. If resolved: incident over.
  → If not resolved: continue to Step 3.

## Step 3: Check database connectivity
Run: `kubectl exec -it $(kubectl get pod -l app=checkout-service -n production -o name | head -1) -- /scripts/db-health-check.sh`
Expected output: "DB: OK, latency: Xms"
If output is "DB: FAILED" or timeout:
  → This is a database issue. See runbook: [Postgres Runbook](../postgres-runbook.md)
  
## Step 4: Check payment provider connectivity
Run: `curl -s https://internal-tools/checkout/payment-provider-status`
If status is "DEGRADED" or "DOWN":
  → Payment provider is having an incident. Check their status page: https://status.stripe.com
  → If confirmed Stripe incident: post in #incidents "Checkout degraded due to Stripe incident. ETA: per Stripe status page. No action needed our side."
  → If Stripe is fine: continue to Step 5.

## Step 5: Escalate
If you've reached here, the issue is not a recent deploy, not DB, not payment provider.
Page: the checkout service owner (PagerDuty rotation: checkout-service-oncall)
Provide: Link to Grafana, rollout history output, DB health check output, payment provider status.
```

**Keeping runbooks alive:**
- Every runbook has a named owner. Owner is responsible for updates after incidents.
- At the end of every runbook: "Last verified: [date]. Verified by: [name]." If this date is > 6 months old, treat the runbook with skepticism.
- Post-mortem action items often include: "Update the checkout runbook to include Step 4 (we missed the payment provider check in this incident)."
- Quarterly: Platform team runs a "runbook fire drill" — on-call simulates an incident using only the runbook. Gaps found are filed as bugs.

---

## Part 7: The Craft of Clear Technical Writing

Technical content is necessary but not sufficient. Clarity of expression is what makes the content useful.

**Rule 1: Conclusion first.** Every technical document and every major section should start with its conclusion. This is the inverted pyramid, borrowed from journalism. Why? Because readers decide whether to read further based on the opening. If the opening is context and background, many readers won't reach the conclusion. If the opening is the conclusion, readers know immediately whether it's relevant and can choose to read the supporting detail.

Bad:
> *"After evaluating three options, including Kafka, RabbitMQ, and Redis Streams, and considering our existing operational knowledge, team preferences, and scalability requirements, as well as the team's prior experience during the Q4 2023 Kafka migration, we have concluded that..."*

Good:
> *"We're using Kafka. Here's why: ...*"

**Rule 2: One sentence per idea.** Long sentences with multiple clauses hide complexity. Break them up. Readers should never need to re-read a sentence to understand it.

Bad:
> *"The service will be deployed using our standard blue-green deployment strategy, which means we maintain two production environments and switch traffic between them, with the advantage that rollback is instant because we simply switch traffic back to the previous version, which is kept warm."*

Good:
> *"We use blue-green deployment: two production environments, instant rollback by switching traffic to the previous environment.*"

**Rule 3: Tables over prose for comparisons.** Any sentence of the form "Option A has X and Y and Z, while Option B has X but not Y and instead has W" should be a table.

**Rule 4: Eliminate filler.** Common filler phrases that add no meaning:
- "It's worth noting that..." → just say the thing
- "Basically," "essentially," "in essence" → delete
- "As mentioned above/below" → delete; reorganize so the order makes sense
- "In order to" → replace with "to"
- "At this point in time" → replace with "now"
- "Due to the fact that" → replace with "because"
- "It should be noted" → delete; everything in the doc should be noted

**Rule 5: Specific numbers beat vague adjectives.**
- Bad: "This will significantly improve performance."
- Good: "This reduces P95 latency from 400ms to 50ms."
- Bad: "We have a large user base."
- Good: "We have 40M MAU."

**Rule 6: Active voice, present tense.** Passive voice obscures the actor and inflates word count.
- Bad: "The error was encountered by the service."
- Good: "The service returned a 503."
- Bad: "It was decided that we would use Kafka."
- Good: "We chose Kafka."

**Rule 7: One paragraph, one idea.** Every paragraph should have a topic sentence (the main point), supporting sentences, and nothing else. If a paragraph is covering two ideas, split it.

**Getting feedback on writing:**
When asking for a review of a design doc, be specific about what feedback you need:
- "Is the problem statement clear and correctly framed?"
- "Is the proposed design technically sound for the stated constraints?"
- "Am I missing an obvious alternative?"
- Not: "Let me know what you think." (Too open; gets orthogonal feedback.)

When you receive feedback, the most common error is defending your original wording instead of asking "why did this confuse you?" The confusion is real even if the logic was correct. If a senior engineer misunderstood your proposal, the solution is to rewrite, not to explain the misunderstanding verbally.

---

## Part 8: L5 vs L6 Calibration

| Dimension                          | L5 / Senior SWE                                | L6 / Staff SWE                                        |
|------------------------------------|------------------------------------------------|-------------------------------------------------------|
| **Design doc scope**               | One service or feature                         | Cross-service or cross-team architecture              |
| **Alternatives section**           | Sometimes present; 1–2 alternatives            | Always present; 2–3 alternatives with clear rationale |
| **Audience awareness**             | Writes for their team                          | Writes for adjacent teams, leadership, future engineers|
| **Problem framing**                | Describes the technical solution clearly       | Leads with the user/business problem; solution second  |
| **RFC usage**                      | Participates in RFCs                           | Initiates RFCs; drives to decision by deadline         |
| **Post-mortem quality**            | Accurate timeline; reasonable action items     | Systemic root cause; action items that change systems  |
| **ADR practice**                   | Reads existing ADRs                            | Writes new ADRs; ensures team ADR discipline          |
| **Writing clarity**                | Clear but verbose; some filler                 | Tight; every sentence earns its place                 |
| **Revision discipline**            | One or two passes                              | Multiple rewrites; gets feedback; revises again        |
| **Impact of their writing**        | Team-level alignment                           | Org-level decisions influenced or changed             |

---

## Part 9: Interview Application

Technical writing comes up in Staff/L6 interviews in three ways:

**1. Behavioral: "Tell me about a time you influenced without authority."**
This almost always leads to a story about writing. The STAR answer structure:
- Situation: "Two teams couldn't agree on the API contract for a new data pipeline."
- Task: "I was asked to facilitate the decision but had no authority over either team."
- Action: "I wrote an RFC that explicitly framed the open questions, got both teams to comment, synthesized the disagreements, and made a recommendation with clear tradeoffs."
- Result: "Both teams accepted the recommendation. The pipeline shipped 3 weeks later with a clean API contract that has held for 18 months."

**2. System design: Writing your design on the whiteboard**
System design interviews are the live version of design documents. The structure maps directly:
- Problem statement (Phase 1: requirements clarification)
- Design (Phase 2-4: the architecture)
- Alternatives considered (explicitly say "I considered X but rejected it because...")
- Risks (Phase 5: failure modes, scaling concerns)

Strong candidates narrate their design with conclusion-first sentences: "I'd use Kafka here — the key reason is fan-out to multiple consumers without coupling producers to consumers." Weak candidates describe the architecture without explaining the reasoning.

**3. Code review discussion**
Interviewers sometimes discuss past code reviews. The ability to give feedback that is specific, actionable, and explains the "why" — rather than "this is wrong" — is a writing skill applied to code.

---

## Part 10: Anti-Patterns in Technical Writing

**Anti-pattern 1: The "dump doc"**
Symptom: 30-page design document with every implementation detail, every edge case, every thought the author had during design.
Problem: The signal is buried in the noise. Readers can't find the key decisions.
Fix: Front-load the summary. Put conclusions and key decisions in the first page. Details in appendices for those who need them.

**Anti-pattern 2: The "decided before written" doc**
Symptom: Design doc is written after the implementation is already done or after the decision is made. "Comments welcome" is performative.
Problem: No real input is possible; feedback is ignored because the train has left.
Fix: Write the design doc before implementation starts. The discomfort of uncertainty in the doc is a feature — it forces clarity before code is written.

**Anti-pattern 3: The "no alternatives" doc**
Symptom: "We will use X." No mention of Y and Z.
Problem: Senior reviewers lose trust. They assume you either didn't consider alternatives or you're hiding inconvenient tradeoffs.
Fix: Always write the "alternatives considered" section. Even if the alternatives are obviously wrong, say so explicitly. "We considered Redis, but our data model requires joins, which Redis doesn't support."

**Anti-pattern 4: The "vague action item" post-mortem**
Symptom: Action items like "improve monitoring," "better communication," "more careful testing."
Problem: Nobody owns them; nobody measures them; nothing changes.
Fix: Every action item has an owner (named person, not team), a deadline, and a specific deliverable. "Priya will add a pre-deploy config validation script by March 22."

**Anti-pattern 5: The "jargon document"**
Symptom: Document assumes all readers know the internal codenames, acronyms, and architecture of your system.
Problem: New hires, adjacent team engineers, and future readers can't use the document.
Fix: Define every acronym on first use. Link to the system or service being referenced. Write for the smart engineer who doesn't know your specific system — not for your teammate who does.

**Anti-pattern 6: The "unresolved RFC"**
Symptom: RFC was written 6 months ago, has 47 comments, and no decision was made.
Problem: Engineers don't know what was decided; work is blocked or duplicated.
Fix: Every RFC has a decision deadline. After the deadline, the owner synthesizes comments and makes a decision. Even a wrong decision made quickly is better than no decision — wrong decisions can be corrected; paralysis cannot.

---

## Part 11: Exercises

**Exercise 1 (Design Doc):** Write a design doc for the following problem: "Our current user authentication system has a 300ms P95 latency. 40% of that is a synchronous database lookup for the user's permission set on every API call. We want to reduce this to under 50ms." Write the problem statement, goals/non-goals, proposed design, alternatives considered (at least two), and risks.

**Exercise 2 (Alternatives Section):** Take the following bad "alternatives considered" section and rewrite it:
> *"We also considered using Redis and MongoDB, but decided that Postgres was the best option for our use case."*
Rewrite to explain: what specifically about Redis was evaluated, why it was rejected (what property made it unsuitable), what specifically about MongoDB was evaluated, and why Postgres was chosen.

**Exercise 3 (Post-Mortem):** Write a post-mortem for the following fictional incident:
> At 2:15 PM, the order confirmation email service stopped sending emails. An engineer noticed at 2:45 PM and investigated until 3:30 PM, when they realized the SendGrid API key had expired. The key was rotated at 3:32 PM and emails resumed. ~4,300 orders received no confirmation email. The key had expired 2 months after it was set to expire; there was no monitoring for API key expiry.
Write the summary, timeline, root cause, contributing factors, and 3 action items.

**Exercise 4 (Runbook):** Write a runbook for the following scenario: "The metrics dashboard is blank. Engineers need to diagnose whether it's a Prometheus scrape failure, a Grafana datasource connection failure, or a data ingestion issue." Include at least 3 diagnostic steps with specific commands.

**Exercise 5 (Rewriting for clarity):** Rewrite the following paragraph for clarity:
> *"Due to the fact that the existing approach of using a synchronous RPC call to fetch user preferences in real-time on every single page load has been determined to be suboptimal from a performance perspective, causing unacceptable latency, it was decided by the team that a new approach involving the use of a caching layer in order to reduce the frequency with which these calls need to be made would be implemented."*

---

## Exercises

**Exercise 1 — RFC in One Hour:**
Write a one-page RFC for a real or hypothetical technical decision you face. Use the template from Part 2: problem statement, proposed solution, alternatives considered, trade-offs, decision. Time yourself: can you write a useful RFC in under an hour? What parts took the most time?

**Exercise 2 — Passive Voice Hunt:**
Take 3 paragraphs of your recent writing (Slack messages, design docs, tickets). Highlight every passive construction. Rewrite each sentence in active voice. Which rewrites made the sentence more specific (naming who does what)? Did any passive constructions serve a purpose?

**Exercise 3 — One-Sentence Summary:**
For a project you're working on: write the problem statement in exactly one sentence. Then write the proposed solution in exactly one sentence. Then write the key trade-off in exactly one sentence. Share these three sentences with someone not on your team. Do they understand the decision? If not, which sentence failed?

**Exercise 4 — Incident Post-Mortem:**
Write a blameless post-mortem for a real or practice incident. Use the structure from Part 5: timeline, impact, root cause (5 Whys), contributing factors, what went well, action items. For each action item: is it specific? Does it have an owner? Is it verifiable?

**Exercise 5 — Influence Without Authority:**
Write a 1-paragraph persuasive argument for a technical decision you believe in, aimed at a senior engineer who is skeptical. Use evidence, not appeals to authority. Name the trade-off explicitly. Anticipate the main objection and address it. Then: read it aloud. Does it sound confident or defensive?

---

## Homework

**Homework 1:** Find a design doc you've written (or a colleague's with permission) and apply the 7 rules from Part 7. Count the filler phrases and passive constructions. Rewrite the first three paragraphs using the rules. Compare.

**Homework 2:** Find an incident at your company that had a weak post-mortem (vague root cause, weak action items). Rewrite the root cause and action items sections using the guidelines from Part 5.

**Homework 3:** Write an ADR for the last significant architectural decision your team made. Put it in `/docs/adr/` in your repository. See how your teammates respond — does it spark useful discussion about the reasoning?

**Homework 4:** Read Google's "Engineering for Reliability" SRE book (Chapter 15: Postmortem Culture). Note the specific techniques they use for blameless root cause analysis. Apply one technique to your next incident post-mortem.

---

```
╔══════════════════════════════════════════════════════════════════════╗
║                   KEY TAKEAWAYS — TECHNICAL WRITING                 ║
╠══════════════════════════════════════════════════════════════════════╣
║  WRITING IS LEVERAGE: You write once; 50 people read it. Every      ║
║  hour spent writing clearly is an hour that compounds.              ║
║                                                                      ║
║  DESIGN DOC: Problem → Goals/Non-Goals → Proposed Design →           ║
║  Alternatives Considered → Risks → Timeline.                        ║
║  "Alternatives considered" is where credibility is built.           ║
║                                                                      ║
║  RFC: Invite input on open questions. Explicit question section.     ║
║  Set a comment deadline. Make a decision. Close the loop.            ║
║                                                                      ║
║  ADR: Permanent record. 5 parts: status, context, decision,          ║
║  consequences, alternatives rejected. Stored in the repo.           ║
║                                                                      ║
║  POST-MORTEM: Systemic root cause (not people). Action items with    ║
║  named owner + deadline + specific deliverable. Blameless.          ║
║                                                                      ║
║  RUNBOOK: Written for 2 AM under stress. Symptom → step-by-step.    ║
║  No assumed knowledge. Named owner. Date-verified.                  ║
║                                                                      ║
║  CRAFT: Conclusion first. One sentence per idea. Tables for          ║
║  comparisons. Eliminate filler. Specific numbers. Active voice.     ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Part 12: War Stories — When Writing Changed Outcomes

**Story 1: The design doc that prevented a 3-month detour**

A senior engineer at a large tech company was convinced their authentication service needed a complete rewrite. They started coding. Three weeks in, a Staff engineer asked to see a design doc. The senior engineer wrote one — and the process of writing the "alternatives considered" section forced them to document why the existing service was problematic. As they wrote it out, they realized the core problem was a missing cache, not a broken architecture. The full rewrite would have taken 3 months; the cache took 2 days. The design doc saved 80 engineering-days by requiring the engineer to think before building.

**Lesson:** The discipline of writing a design doc is not bureaucracy — it is the cheapest form of validation. You find design flaws in writing, not in code review.

**Story 2: The RFC that aligned three teams in a week**

Three teams at a payments company each had different views on how the new transaction event schema should be structured. Team A wanted a flat schema (simple). Team B wanted a deeply nested schema (rich). Team C wanted a versioned envelope schema (flexible). Meetings had been going in circles for 6 weeks.

A Staff engineer wrote a 2-page RFC. Key elements: a clear statement of the question ("we need to choose schema A, B, or C — please comment by Friday on which you prefer and why"), a specific table comparing the three options on the dimensions that mattered (migration cost, read latency, backwards compatibility, operational complexity), and a deadline. By Monday, all three teams had commented. By Wednesday, the Staff engineer had synthesized the comments and chosen Option C with specific modifications to reduce complexity. Both Team A and Team B felt heard. The decision was made.

**Lesson:** Clear framing + a deadline breaks consensus deadlock. The RFC's job is not to make everyone happy — it's to make a decision with appropriate input.

**Story 3: The post-mortem that changed a culture**

A startup had a major database outage. The first post-mortem draft said "root cause: engineer forgot to run migrations before deploying." The action item was "reminder in Slack before every deploy."

A new Staff engineer rewrote it. The new root cause: "The deployment system does not verify that migrations have been run before accepting traffic. There is no automated check." Action items: (1) Add a migration status check to the deploy pipeline, fails deploy if pending migrations exist. (2) Add a pre-deploy runbook step for the migration check. (3) Conduct a retrospective on other missing deploy validations.

Six months later, the startup had zero deployment-related incidents. The post-mortem didn't just fix one bug — it changed the team's mental model of what post-mortems are for.

**Lesson:** The post-mortem that blames a person changes one person's behavior for a few weeks. The post-mortem that changes the system changes every person's experience forever.

**Story 4: The ADR that saved 40 hours**

A team was considering switching from MongoDB to Postgres for their user profile service. An engineer spent two days analyzing the migration costs before someone pointed out: "We have an ADR for this from 2021." The ADR explained: MongoDB was chosen because the user profile schema was highly variable between user types; Postgres rigid schema would have required dozens of nullable columns or a complex inheritance scheme. The original problem was still true.

The 2021 ADR saved the 2023 engineer 2 days of analysis and prevented an expensive migration.

**Lesson:** ADRs pay dividends years after they're written. The investment in writing them is tiny compared to the cost of re-deriving decisions.

---

## Part 13: Design Documents — Extended Examples

**Example: Problem Statement (before and after)**

Before (vague):
> *"The current search feature is not fast enough. Users are complaining about latency. We need to improve the search system to be faster and more reliable."*

After (specific and actionable):
> *"Current: search P95 latency is 4.2 seconds. Our SLA is 1 second. 12% of searches time out (> 5s), resulting in no results. User feedback analysis (Q4 survey, N=2,400) identifies search speed as the #1 complaint. Estimated churn impact: 8% of heavy searchers (defined as >20 searches/day) have reduced session frequency by >30% over the past quarter (cohort analysis via Amplitude).*
> 
> *Root cause: Elasticsearch index has grown to 180GB with 250M documents. Our current node configuration (3× r5.large) cannot handle the fan-out (each query fans out to all 3 nodes). Index is not partitioned by recency; old documents (>2 years) are searched at the same priority as recent documents, inflating shard size and query time."*

The second version tells the reader exactly what problem to solve, quantifies it, and even identifies the likely root cause. A reviewer reading this knows immediately what "success" looks like.

**Example: Non-Goals section (what to include)**

Non-goals are as important as goals. They prevent scope creep and give permission to not solve adjacent problems.

Bad non-goals:
> *"This project will not rebuild the entire search stack."* (Obvious and uninformative)

Good non-goals:
> *"Non-goals:*
> *- Improving search relevance (ranking algorithm). This project targets latency, not quality.*
> *- Supporting fuzzy/typo-tolerant search. Deferred to Q3.*
> *- Multi-language support. Currently single-language only; no change.*
> *- Real-time indexing (< 1s index lag). Current 30s lag is acceptable; improving it is a separate project.*
> *- Search analytics (query logging, user click tracking). Deferred to Q4."*

This non-goals section tells reviewers precisely what is in scope, prevents well-meaning scope creep during review, and creates a clear acceptance test: we're done when latency is fixed, even if other things are still imperfect.

**Example: Alternatives Considered (the section that earns trust)**

Every serious reviewer asks: "What else did you consider?" This is not an attack — it's due diligence. The reviewer wants to know that the engineer explored the space, not just found the first solution that worked.

Bad:
> *"We considered using a different database but decided Elasticsearch was best for our needs."*

Good:
> *"Alternatives considered:*
> 
> *1. Postgres full-text search (tsvector): Rejected. Our 180GB index far exceeds what Postgres full-text search handles efficiently. At 250M documents, tsvector requires a GIN index that would be ~40GB and require full-table scans for faceted filtering. We benchmarked this at 12s P95 — worse than current.*
> 
> *2. Separate Elasticsearch cluster for "hot" content (< 6 months old): Rejected for this phase. Adds operational complexity of dual-cluster indexing. Deferred to Phase 2 if single-cluster optimization doesn't reach the 1s SLA.*
> 
> *3. Increase Elasticsearch node size (r5.large → r5.4xlarge): Evaluated. Cost: +$4,200/month. Benchmarked: P95 latency drops from 4.2s to 2.1s. Does not meet the 1s SLA. Not sufficient as a standalone solution, but could be combined with approach 4 for 20% cost reduction.*
> 
> *4. Index partitioning by recency (chosen approach): Three separate indices — hot (< 3 months), warm (3–18 months), cold (> 18 months). 80% of queries target the hot index (20GB). Hot-only queries achieve 180ms P95 in benchmarks. 20% of queries fan out to all three. Overall P95: 620ms. Meets the 1s SLA with headroom."*

This alternatives section took 15 minutes to write but changes the entire tone of the design review. Every reviewer knows the engineer thought carefully.

---

## Part 14: RFC Templates

**Minimal RFC template (< 2 weeks decision cycle):**

```markdown
# RFC: [Short title of the question being decided]

**Status:** Open for comment
**Comment deadline:** [specific date]
**Decision by:** [specific date]
**Author:** [name]
**Reviewers requested:** [names — specific people whose input you want]

## Question
[One paragraph: what are we deciding? What options are on the table?]

## Background
[2-3 paragraphs: what context does the reader need?]

## Options

### Option A: [name]
[Description. Pros. Cons. Estimated cost/complexity.]

### Option B: [name]
[Description. Pros. Cons. Estimated cost/complexity.]

### Option C: [name]
[Description. Pros. Cons. Estimated cost/complexity.]

## My recommendation (tentative)
[Which option you lean toward and why. Being explicit invites targeted pushback.]

## Questions for reviewers
1. [Specific question — ideally directed at a named person]
2. [Specific question]

## Decision
[Left blank until the decision is made]
[After decision: "Decision: [option chosen] because [rationale]. 
 Key feedback incorporated: [summary of comments that changed the recommendation]"]
```

**Full RFC template (complex, multi-team decisions):**

For decisions spanning multiple teams or with long-term consequences, the RFC needs:
- An executive summary (1 paragraph) for readers who won't read the whole thing
- A stakeholder map (which teams are affected and how)
- A migration/rollout plan if the decision requires one
- A risk register for each option
- An explicit rollback plan if the decision turns out to be wrong

The additional sections add cost but are justified when: (1) the decision is hard to reverse, (2) more than 3 teams are affected, or (3) the financial/technical risk is high.

---

## Part 15: The Email and Slack Message as Technical Writing

Not all technical writing is formal documents. The daily email or Slack message is also technical writing, and the same rules apply at smaller scale.

**The 3-sentence technical update:** Any status update, progress report, or "FYI" message should be structured:
1. **What happened / what I did** (one sentence, fact, past tense)
2. **What it means / what changed** (one sentence, impact)
3. **What's next / what I need** (one sentence, action)

Example:
> *"The auth service migration to the new token format is complete for the US region. Latency dropped from 340ms to 80ms P95; no errors. Rolling out to EU region tomorrow; will need a 30-minute maintenance window — confirming timing with the EU team."*

Three sentences. Covers: what was done, what changed, what's next.

**Slack escalation message (incident):**
```
@incident-response 
Service: checkout-service
Impact: ~15% of checkouts failing with 503
Started: ~14:32 UTC (15 minutes ago)
Current theory: DB connection pool exhausted (checked: pool at 100%)
Action taken: Increased pool size from 50→100; watching error rate
Next: If not resolved in 5 min, will initiate rollback of yesterday's deploy
Dashboard: [link]
```

This message contains everything an incident responder needs to know. No "hey" preamble, no explanation of context that's in the dashboard, no passive voice.

**The code review comment as writing:**
Bad code review comment: *"This is wrong."*
Good code review comment: *"This will throw a NullPointerException if `user.getAddress()` returns null (which it does when the user hasn't set an address yet — see UserService.createUser() line 47). Consider: `if (user.getAddress() != null) { ... }` or use Optional<Address>."*

The good comment tells the reviewer: what's wrong, why it's wrong (specific reference), and how to fix it. This is writing clarity applied to code review.

---

## Part 16: Writing Speed and the Cost of Over-Drafting

One reason engineers avoid writing is that they think it takes too long. This is partly true and partly a skills gap.

**The skills gap:** Engineers who write poorly spend most of their writing time on structure — figuring out what to say and in what order. Engineers who write well spend most of their time on content — the technical analysis itself. Structure can be templated (and has been throughout this chapter); content is what takes real time.

**The over-drafting trap:** Many engineers treat every document as a literary work that must be perfect. This results in documents that take 10× too long to write and that don't get written at all. The antidote: distinguish between "good enough to share" and "final." A design doc shared for early feedback at "good enough to share" quality is infinitely more valuable than a perfect document that arrives after the decision was made.

**The 80% rule:** When 80% of the document is written, get feedback. The last 20% of polishing is less valuable than early input that changes the 80%. Most engineers wait until 100% before sharing; most Staff engineers share at 60–70%.

**Time benchmarks (rough guide):**
- 1-page design doc (problem + proposal + risks): 2–3 hours first draft
- 4-page design doc (full sections): 6–10 hours first draft + review + revisions
- Post-mortem (after incident): 1–2 hours within 48 hours (while memory is fresh)
- ADR: 30–60 minutes
- RFC: 2–4 hours
- Runbook: 1–2 hours per runbook

Engineers who write regularly get faster. The 10th design doc takes half the time of the first.

---

## Part 17: Reading Technical Writing — Being a Good Reviewer

The other side of writing is reviewing. Good reviewers produce better documents; good writers respond to review productively.

**How to give useful feedback on a design doc:**

The four things a reviewer should provide:
1. **Clarification requests:** "I don't understand X" — not "X is unclear" (which blames the author). "I don't understand how the cache invalidation works when a user changes their permissions" gives the author actionable information.
2. **Missing information:** "The doc doesn't address what happens if the Kafka consumer falls behind." Not "the doc is incomplete."
3. **Disagreements:** "I disagree with the choice of eventual consistency here — in our use case, a user seeing stale permissions for 30 seconds is a security issue, not just a UX issue. See the incident from Nov 2023." Gives the author your reasoning, not just your objection.
4. **Specific approval:** "The alternatives section is thorough. The migration risk section is particularly good." Not just the overall "LGTM" — specific positive feedback helps the author know what to keep.

**How NOT to review a design doc:**
- "This should be completely redesigned." (Too vague; author doesn't know what to do.)
- "This is wrong." (What's wrong? Why?)
- Re-writing the doc in comments (write your own doc instead; this is usurping the author's work).
- Asking for changes to scope, timeline, or non-goals without a specific reason.

**Response to review feedback:** "I disagree" is a valid response — but it must be paired with reasoning. "I considered this alternative (I should have included it in the doc) and rejected it because X" is fine. "I disagree because the commenter doesn't understand the system" written in the doc is not fine — address the substance, not the person.

---

## Part 18: Pre-Interview Drill — Writing Knowledge

Questions you should be able to answer verbally in 60 seconds each:

1. What are the 6 sections of a design doc and what does each one do?
2. What is the difference between an RFC and a design doc?
3. What makes a post-mortem "blameless" and why does it matter?
4. Name three specific action item anti-patterns in post-mortems.
5. What is an ADR and where should it be stored?
6. What is the difference between a runbook and a wiki page?
7. Name four filler phrases to eliminate from technical writing.
8. What is the "inverted pyramid" in technical writing?
9. How do you ask for specific feedback on a design doc (vs "let me know what you think")?
10. A senior engineer says your design doc is "too high level." What do you do?

---

## Part 19: One-Liners for Recall

- **"Write the alternatives section — it's where credibility is built."**
- **"A design doc written after the decision is made is documentation, not design."**
- **"Conclusion first, evidence below — always."**
- **"A vague post-mortem action item changes nothing."**
- **"Every action item needs an owner, a deadline, and a specific deliverable."**
- **"ADRs are for future-you, not for current approval."**
- **"A runbook works at 2 AM with someone who has never seen the system."**
- **"Specific numbers beat vague adjectives: '400ms' beats 'slow.'"**
- **"Active voice: 'the service returned 503,' not 'a 503 was returned.'"**
- **"Share at 80% — early feedback beats perfect late documents."**
- **"The RFC's job: gather input on open questions, then make a decision."**
- **"Every RFC has a comment deadline. Decisions happen; they don't emerge."**

---

## Part 20: Chapter Summary

Technical writing is one of the highest-leverage skills an engineer can develop. The compound return on writing clearly is enormous: every hour you invest in a clear design doc saves dozens of hours of misaligned engineering work. Every post-mortem that correctly identifies a systemic root cause prevents future incidents, not just the current one. Every runbook that works at 2 AM without phone calls saves every on-call engineer who uses it for the next three years.

The specific forms covered in this chapter — design docs, RFCs, ADRs, post-mortems, runbooks — each serve a distinct purpose. Knowing which to reach for and how to write it well is an engineering skill, not a communication skill. It is how senior engineers build influence that outlasts their tenure on any individual team.

For Staff/L6 calibration: the difference is scope and audience. L5 writes for the team. L6 writes for the organization. L5 documents decisions. L6 shapes decisions through writing — by framing the problem, surfacing the right tradeoffs, and giving reviewers the context they need to give useful feedback.

---

## Part 21: Additional Reference — Document Lifecycle

**Design doc lifecycle:**
```
Phase 1: Draft (author only)
  → Write problem + goals + rough design
  → Share with closest collaborator for sanity check (informal, fast)
  
Phase 2: Early feedback (small audience, < 5 people)
  → Share with team + 1-2 trusted adjacent engineers
  → Goal: catch major flaws before broad review
  → Duration: 3-5 days
  
Phase 3: Broad review (full audience)
  → Share with all stakeholders
  → Set comment deadline: 5-7 business days
  → Author responds to all comments: accept/reject/defer + reasoning
  
Phase 4: Approval (if required)
  → If your org requires sign-off: route to approvers
  → Include a "status" header: "DRAFT → IN REVIEW → APPROVED"
  
Phase 5: Living document (implementation)
  → Update as decisions change during implementation
  → Note changes with date + reason
  → Link to the implementation PR when complete
  
Phase 6: Archive
  → After launch: mark as "IMPLEMENTED" with link to the code
  → Doc becomes a permanent record and onboarding resource
```

**ADR lifecycle:**
```
Status values: Proposed → Accepted → Deprecated → Superseded

ADR-0042: Payment service uses Postgres (Accepted 2024-03-15)
  |
  | (18 months later, new constraints)
  v
ADR-0088: Payment service migrates to CockroachDB (Accepted 2025-09-01)
  → ADR-0042 marked "Superseded by ADR-0088"
  → ADR-0088 links to ADR-0042 for historical context
```

---

## Part 22: Five-Level Progression — Technical Writing

**INTERN:** Writes code comments that describe what the code does. Writes PR descriptions that list the files changed. Receives feedback like "I don't know why this was changed."

**JUNIOR:** Can write a clear PR description: what changed, why, how to test. Writes basic meeting notes. Struggles with design docs — either too much or too little. Tends to front-load context before conclusions.

**MID:** Writes solid design docs for their own service changes. Structures documents well. Understands the difference between writing for their team vs writing for a broader audience. Can write a passable post-mortem. Tends to underuse the "alternatives considered" section.

**SENIOR (L5):** Writes design docs proactively before implementing. Includes alternatives section. Writes post-mortems that identify root causes. Initiates RFCs when needed. Writing influences team-level decisions. Documents have sufficient clarity that the team can act without the author present.

**STAFF (L6):** Writing shapes org-level decisions. Design docs and RFCs that the engineer writes change architectural directions for multiple teams. Post-mortems identify systemic issues that lead to org-wide process changes. ADRs they write are referenced years later by engineers who weren't there. Their writing is used as examples of "how to write a design doc" for onboarding new engineers. They review and improve other engineers' writing as part of growing the team.

---

## Part 23: The Anatomy of a Great Technical Paragraph

Writing at the sentence and paragraph level is where clarity or confusion is actually created. Big structural choices (conclusion first, tables for comparisons) matter, but so does the micro-level craft.

**The three-sentence paragraph pattern:**
```
Sentence 1: Topic sentence — the one thing this paragraph is about.
Sentence 2: The evidence, elaboration, or example.
Sentence 3: The implication — what the evidence means; what the reader should take from it.
```

Example:
> *"Cache hit ratio for the product catalog API is 45% — far below the 90% target. [Topic]
> Analysis of access logs shows that 60% of product page views include a user-specific "recently viewed" component, which we're incorrectly including in the cache key. [Evidence]
> Removing the user-specific component from the cache key and serving it client-side would bring the hit ratio above 90%, matching our target. [Implication]"*

Three sentences. No filler. Topic, evidence, implication.

**Diagnosing weak paragraphs:**
- Paragraph has no topic sentence → add one at the start
- Paragraph covers two topics → split it
- Paragraph is all evidence, no implication → add a concluding sentence
- Paragraph is all opinion, no evidence → add specifics or delete it
- Paragraph restates the topic sentence in the last sentence → delete the last sentence

**The "So what?" test:** After writing any paragraph, ask: "So what?" If you can't answer, the paragraph is incomplete — either the implication is missing or the paragraph doesn't earn its place in the document. Apply this to every paragraph before sharing.

---

## Part 24: Technical Writing in Code — Comments and Naming

Technical writing isn't just documents. The comments in your code and the names you choose for variables and functions are also writing. Bad names and bad comments create documents nobody asked for.

**The purpose of a code comment:**
A code comment should answer "why," not "what." The code already answers "what" — it's the code. A comment that says `// increment i by 1` is noise. A comment that says `// retries must be capped at 3 to avoid cascading failures (see incident #1234)` is information.

Good code comments:
```python
# AIMD backoff: halve rate on timeout, additive increase on success.
# This matches the TCP congestion control model the client expects.
# Note: exponential backoff would be faster but risks client stampedes.
rate = rate / 2 if timed_out else rate + 1
```

Bad code comments:
```python
# Divide by 2 if timed out, else add 1
rate = rate / 2 if timed_out else rate + 1
```

**Naming as technical writing:** A function named `process_data()` is a failed document. `validate_payment_authorization_and_charge()` is a contract — the reader knows what to expect. `handle_user()` could mean anything; `cancel_subscription_and_trigger_offboarding_workflow()` is specific.

Rules for naming:
- Functions: verb + noun. `send_email`, `validate_schema`, `retry_with_backoff`.
- Classes: noun. `PaymentProcessor`, `OrderStateMachine`, `UserRepository`.
- Variables: be specific. `user_id` not `id`; `payment_timeout_seconds` not `timeout`.
- Booleans: use `is_` or `has_` prefix. `is_expired`, `has_admin_access`.
- Don't abbreviate. `user_authentication_token` not `uat`. Save the reader the mental lookup.

---

## Part 25: Communicating Up — Writing for Leadership

A specific form of technical writing that Staff engineers often need: communicating with VPs, Directors, or non-engineer stakeholders.

**The challenge:** Leadership needs a different level of abstraction than engineers. A VP doesn't need to know that you chose HNSW over IVF for the ANN index — they need to know what the product impact is.

**The executive summary pattern:**

Every document sent to leadership must have an executive summary. Structure:
```
One sentence: what we built / what we decided / what happened.
One sentence: business or user impact (quantified if possible).
One sentence: what we need (decision, approval, information).
```

Example (from an engineer to a VP, about a proposed infrastructure change):
> *"We're proposing to migrate our recommendation engine from a nightly batch job to real-time inference (design doc: [link]).*
> *Impact: expected +3–5% conversion rate improvement based on experiments at comparable companies; $2.4M estimated annual revenue increase.*
> *We need your approval on the engineering allocation: 4 engineers for 3 months (Q3 OKR)."*

Three sentences. A VP can read this in 15 seconds and know whether to read the full doc.

**Adapting technical content for non-engineers:**
- Replace "Elasticsearch index fragmentation" with "search gets slower as data grows."
- Replace "P95 latency" with "95% of users wait less than X seconds."
- Replace "the service exhausted its DB connection pool" with "the checkout service temporarily stopped accepting new orders."
- Always lead with user or business impact; follow with technical cause.

**The "so what for the business?" translation table:**

| Technical metric            | Business translation                                   |
|-----------------------------|--------------------------------------------------------|
| P95 latency increased 200ms | 5% of users wait an extra 0.2 seconds per page        |
| Error rate 1%               | 1 in 100 user actions fail (checkout, login, upload)   |
| 30-minute database outage   | All write operations unavailable for 30 minutes        |
| Cache hit ratio dropped 20% | Origin server costs increase 4× during the drop        |
| CDN bandwidth 50 TB/month   | 50,000 GB of content delivered to users monthly        |

---

## Part 26: The Technical Blog Post

A form of technical writing that helps Staff engineers build external reputation and influences the broader engineering community: the technical blog post.

**Why engineers write blog posts:**
- Establish domain expertise
- Recruit (great engineering blog posts attract strong applicants)
- Influence the industry (set norms, share knowledge)
- Clarify their own thinking (teaching something forces a different kind of understanding)

**The structure of a good engineering blog post:**

```
Title: Specific and intriguing. 
  Bad: "Improving Database Performance"
  Good: "How We Reduced Postgres P95 Latency from 4s to 80ms"

Paragraph 1: The hook.
  What problem did you have? Make the reader feel the pain.
  "In Q4 2023, 12% of our searches were timing out. Users were leaving."

Paragraph 2: What you tried that didn't work (and why).
  This builds credibility: you're not just showing the solution, you're showing the journey.

Main body: The solution.
  Specific. Include numbers. Include diagrams.
  Code examples where relevant.
  What you learned along the way.

Ending: What would you do differently?
  The retrospective angle — shows maturity and genuine reflection.
  
Key metric: What changed? Quantified before and after.
```

**Blog post vs design doc:** A blog post is written for the external world; it assumes less context and must tell a story. A design doc is written for your team; it assumes shared context. Blog posts tend to be more narrative; design docs are more structured. Both benefit from the same core skills: specificity, conclusion-first, and active voice.

---

## Part 27: Measuring Writing Effectiveness

How do you know if your writing is working?

**Signal 1: Review comments quality**
If design doc review comments are all about the problem framing and tradeoffs (high signal), the writing is working. If review comments are mostly "I don't understand what you're proposing" (low signal), the writing needs work.

**Signal 2: Questions per reader**
After sharing a design doc, track how many questions you get per reader. A well-written doc should have fewer than 3 clarifying questions per reader on core topics. (Some questions are expected — no document is perfect.) If every reader has the same question ("wait, how does the cache invalidation work?"), that section needs to be rewritten.

**Signal 3: Decision speed**
A well-written RFC drives to a decision faster. If your RFC is generating circular discussion and no convergence, either the question isn't clear or the alternatives aren't well-framed.

**Signal 4: Reuse**
If your design docs and ADRs are cited by other engineers ("we made this decision because of the ADR from the notification service migration"), your writing is having durable impact.

**Signal 5: Onboarding efficiency**
If new engineers frequently say "the design docs here are really helpful for understanding the system," your writing is doing its job for the third audience (future-you and future-teammates).

---

## Part 28: Design Doc Examples by Type — Quick Reference

Different types of projects call for different design doc emphases:

**Performance improvement design doc:**
Lead with the current metric and the target metric. The problem statement must quantify the problem. Alternatives must be compared on performance benchmarks, not opinions.

**New feature design doc:**
Lead with the user problem and the proposed solution. Emphasize the API and data model decisions (these are hard to reverse). Risks section must address rollout strategy (how do you release safely? Feature flags? Percentage rollout?).

**Migration design doc:**
Lead with the reason for migration and what state the new system will be in. Must include a migration plan (phases, rollback steps). Risks section is especially important — migrations fail in the middle, and the doc must address what happens if migration is paused at any phase.

**Infrastructure design doc:**
Lead with the scale requirements (current and projected). Must include a cost model comparison. Must address operational complexity (who is on-call for the new system?). Alternatives section often includes "stay with current system" as an option.

**Security design doc:**
Lead with the threat model (who are we protecting against, what are we protecting). Must include "what could go wrong" as a first-class section. Should be reviewed by a security engineer before broader review.

---

## Part 29: Building Writing Habits

Writing skill is a practice, not a talent. It improves with volume and with feedback.

**Daily habits that build writing skill:**
1. **Write Slack updates in the 3-sentence format.** What happened, what it means, what's next. This forces clarity on every status update.
2. **Write a one-paragraph decision log in your engineering notebook.** Every time you make a significant technical decision, write one paragraph: what you decided, what alternatives you rejected, and why. This builds the habit for ADR and design doc writing.
3. **Read one strong technical document per week.** Stripe's technical blog, Cloudflare's engineering blog, and the Increment magazine are excellent sources. Notice what makes the writing clear and try to apply one technique.

**Weekly habits:**
1. **Reread a document you wrote 2 weeks ago.** Read it as if you're someone who doesn't know the context. Mark every sentence that is unclear. This builds the editing eye.
2. **Ask for one piece of specific writing feedback per week.** "What was the most confusing part of this doc?" — one question, one answer, one thing to fix.

**Practice rule:** You need to write approximately 20 design docs before they become natural. The first 5 feel painful. The next 10 feel mechanical. The last 5 feel fluent. The only way through is through.

---

## Part 30: Final One-Liners and Quick Reference

**Document types and their one-sentence purpose:**

| Document      | One-sentence purpose                                                      |
|---------------|---------------------------------------------------------------------------|
| Design Doc    | Align the team on what we're building and why before we build it.        |
| RFC           | Get input on an open question from the right people by a specific date.  |
| ADR           | Record a decision and its context for future engineers.                  |
| Post-Mortem   | Change the system so this incident doesn't recur.                        |
| Runbook       | Enable any engineer to resolve this incident at 2 AM without help.       |
| Tech Blog Post| Share knowledge externally to build reputation and influence the field.  |

**Critical writing rules (the short list):**
1. Conclusion first, evidence below.
2. Specific numbers beat vague adjectives.
3. Active voice: subject does the action.
4. Eliminate filler: "it's worth noting that," "basically," "in order to."
5. One paragraph, one idea. Topic sentence + evidence + implication.
6. Tables for comparisons. Always.
7. "Alternatives considered" in every design doc.
8. Action items: owner + deadline + deliverable.
9. Share at 80%, not 100%.
10. ADRs go in the repo, not the wiki.

---

## Part 31: Document Anti-Pattern Gallery

**Anti-Pattern: The "Context Dump" Introduction**

Bad:
> *"Background: Our company was founded in 2015. We have 8M users across 12 countries. The payment service was originally built by the founding team using Node.js and MySQL. In 2019, we migrated to Go. In 2021, we experienced a major outage due to MySQL connection exhaustion. Since then, we've added connection pooling. The payment service currently processes 1,200 TPS at peak. Over the past three years, the service has been maintained by the Core Payments team (currently 6 engineers). The service uses a microservices architecture communicating via gRPC..."*

This goes on for three paragraphs before the problem is stated. By the time the reader reaches the actual proposal, they've lost track of why they're reading.

Good: State the problem in the first sentence. Provide only the context immediately necessary to understand the problem. Additional context can go in an appendix or background section — clearly labeled — for readers who need it.

**Anti-Pattern: The "Passive Decision"**

Bad:
> *"It was determined that using a CDN would be beneficial. A decision was made to use Cloudflare. The migration was completed in Q3."*

Who determined this? Who made the decision? Who completed the migration? Passive voice in technical writing obscures accountability and makes it impossible to follow up with the decision maker.

Good: *"The platform team decided to use Cloudflare based on cost-per-GB benchmarks (Priya's analysis, March 2024). The migration was completed by James by end of Q3."*

**Anti-Pattern: The "Hedge Forest"**

Bad:
> *"This approach could potentially help address some of the performance issues that might be contributing to the latency that users seem to be experiencing. It's possible that we might see some improvement, though results could vary."*

Every sentence contains a hedge ("could potentially," "might be," "seem to be," "possible"). The writer has communicated almost nothing. Readers lose confidence.

Good: *"This approach reduces DB query time by eliminating the N+1 pattern in the user profile endpoint. Benchmark (run against staging with production-equivalent load): P95 latency drops from 420ms to 80ms."*

State facts. If you're uncertain, say specifically what you're uncertain about: "We haven't benchmarked against production traffic, so the 80ms P95 is an estimate. We'll validate in the first 48 hours after deploy."

---

## Part 32: The Structured Email for Technical Decisions

A specific format for emails that require a decision from a stakeholder:

```
Subject: Decision needed: [specific question] — please respond by [date]

[One sentence: what decision is needed and why it's time-sensitive]

Options:
A. [Option A in 1 sentence]
B. [Option B in 1 sentence]

My recommendation: A, because [1-2 sentences of reasoning]

Context: [2-3 sentences of relevant background]

[If there are attachments or links]: Full analysis: [link]

[Explicit ask]: Please reply with your preference or any concerns by [date].
[If no response by date]: If I don't hear back by [date], I will proceed with A.
```

The "proceed with A if no response" line is important for moving fast. It's courteous (gives the stakeholder an opportunity to redirect) but doesn't wait indefinitely.

This format works equally well as a Slack message (shorter) or a formal email (more context). The key element is the explicit ask with a deadline and a default.

---

## Part 33: Writing the Migration Design Doc

Migrations are some of the highest-stakes technical writing because they describe irreversible changes. A migration design doc must answer more questions than a greenfield design doc.

**Additional sections required for migration docs:**

**Migration Phases:** How does the system go from state A to state B? What are the checkpoints? What is the state of the system at each checkpoint? Can we pause between phases?

```
Phase 1: Dual-write (both old and new systems receive writes)
  - Duration: 2 weeks
  - Success criteria: New system's data consistency check passes (< 0.01% discrepancy)
  - Rollback: Stop writing to new system; no user impact

Phase 2: Shadow reads (new system handles reads in background; old system serves users)
  - Duration: 1 week  
  - Success criteria: New system's reads match old system's reads (verified by comparison job)
  - Rollback: Stop shadow reads; no user impact

Phase 3: Cutover (new system serves 1% → 10% → 100% of reads)
  - Duration: 1-2 weeks (traffic ramp)
  - Success criteria: Error rate < 0.1%, P95 latency < 200ms
  - Rollback: Switch traffic back to old system (1-click feature flag)

Phase 4: Old system decommission (remove old system)
  - Duration: 1 month after cutover completes
  - Prerequisite: Zero traffic to old system for 2 weeks
  - Point of no return: Deleting old data (backup retained for 90 days)
```

**Rollback Plan:** Every phase must have an explicit rollback. "Rollback: not possible after Phase 4" is a valid answer — but it must be said explicitly so the team knows when they've crossed the point of no return.

**Data Migration:** If data is being moved or transformed: (1) How is data migrated? Bulk copy vs streaming vs on-read lazy migration. (2) What happens to data written during migration? (3) How do you verify migration completeness and correctness?

**Downtime window:** Does any phase require downtime? If so, how long and when? Getting this wrong costs users dearly; state it explicitly.

---

## Part 34: Brainstorming Q&A — Technical Writing at Staff Level

**Q: "A VP says your design doc is 'too technical.' What do you do?"**

First, clarify: is the VP saying they can't evaluate the decision because the doc doesn't give them the business impact, or are they saying it's too long/detailed? These are different problems with different fixes.

If the doc doesn't convey business impact: add an executive summary (problem in business terms, proposed solution in one sentence, business impact quantified, what decision/approval is needed). The technical content stays — it's for the engineers who need to build it.

If the doc is too detailed for a VP to read: write a 1-page executive summary that links to the full doc. The full doc stays for the engineers. The VP reads the summary.

The mistake to avoid: removing technical content to make the doc "accessible." Technical decisions require technical content. The fix is layering: executive summary for leadership, full detail for engineers.

**Q: "You've been asking for an architectural decision for 6 months via Slack and meetings. It hasn't been made. What do you do?"**

Write an RFC with a decision deadline. The RFC forces the question into written form (which moves it from ephemeral conversation to documented decision). The decision deadline gives the stakeholders a specific date to respond by. Your default action (what you'll do if no one responds by the deadline) moves the process forward.

If the RFC also doesn't get a response: escalate explicitly. Write an email to the decision-maker's manager: "We've been waiting on a decision on [topic] for 6 months. It's blocking [specific work]. We wrote an RFC on [date] with a [deadline] and didn't receive feedback. Can you help move this forward?" The escalation email is also a form of technical writing — be specific, quantify the impact, state what you need.

**Q: "How do you handle a design doc review where two senior engineers disagree and neither will budge?"**

This is a common Staff engineer challenge. The pattern that works:
1. Document both positions with their arguments in the design doc.
2. Make a decision. "I've evaluated both arguments. Here is my reasoning for choosing Position A." The decision doesn't require consensus — it requires a judgment call with documented reasoning.
3. Whoever disagrees can either accept the decision or escalate to the next level. Explicit disagreement with a path to escalation is healthier than ambiguous "agreement" that doesn't stick.

The mistake: letting the disagreement sit unresolved, leading to a document that says "we'll revisit this" indefinitely. Revisiting-indefinitely is a decision to delay — make that explicit if it's the right call.

---

## Part 35: Specific Templates — Post-Mortem and ADR

**Post-Mortem Template:**

```markdown
# Post-Mortem: [Service Name] [Brief description]
**Date:** [Incident date]
**Severity:** P1 / P2 / P3
**Duration:** [HH:MM] ([start time] – [end time] [timezone])
**Author(s):** [name(s)]
**Reviewers:** [names of people who reviewed this post-mortem]
**Status:** Draft / Final

---

## Summary
[3 sentences: what broke, duration, user/business impact]

---

## Impact
- **Users affected:** [number or percentage]
- **Revenue impact:** [$X or "not quantified"]
- **SLA breach:** Yes / No. If yes: [by how much?]
- **Customer notifications:** [Yes/No. If yes: when, via what channel?]

---

## Timeline
All times in [timezone]:
HH:MM — [event]
HH:MM — [event]
...

---

## Root Cause
[One paragraph. Systemic, not individual. Answer: what property of the system allowed this to happen?]

---

## Contributing Factors
- [Factor 1]
- [Factor 2]
- [Factor 3]

---

## Action Items
| Item | Owner | Deadline | Status |
|------|-------|----------|--------|
| [Specific deliverable] | [Name] | [Date] | Open |
| [Specific deliverable] | [Name] | [Date] | Open |

---

## What Went Well
- [Thing that worked]
- [Thing that worked]

---

## Lessons Learned
[2-3 sentences: what systemic insight does this incident give us?]
```

**ADR Template:**

```markdown
# ADR-[number]: [Short title]

## Status
[Proposed | Accepted | Deprecated | Superseded by ADR-XXX]
Date: [YYYY-MM-DD]

## Context
[2-3 paragraphs: what is the situation that requires a decision?
Include constraints, requirements, and the problem you're solving.]

## Decision
[One paragraph: what did we decide?]

## Consequences

### Positive
- [Expected benefit]
- [Expected benefit]

### Negative / Trade-offs
- [Known cost or limitation]
- [Known cost or limitation]

## Alternatives Rejected
### [Alternative 1 name]
[Why it was rejected]

### [Alternative 2 name]
[Why it was rejected]

## Related Decisions
- ADR-[number]: [related decision]
```

---

## Part 36: Technical Writing Metrics — How Google Measures Quality

At companies like Google, Stripe, and Airbnb, writing quality is evaluated in performance reviews:
- "Does this engineer's design docs drive alignment without requiring multiple follow-up meetings?"
- "Do their post-mortems result in measurable improvements to system reliability?"
- "Do their RFCs move to decision efficiently, or do they stall in circular discussion?"

These are not explicit metrics with dashboards — they're qualitative observations that accumulate into a narrative. A Staff/L6 engineer who writes 10 high-quality design docs per year has a visible writing track record. An engineer who writes 0 design docs because "I prefer to talk things through" has a writing gap that will be noted at promotion time.

At Google specifically, the Perf/Promo process includes a "complexity and ambiguity" dimension at L6 that is largely evaluated through writing artifacts: design docs, RFCs, post-mortems. The committee reads these documents. A candidate who doesn't write (even if they're doing great technical work) has a thinner portfolio for the promo committee to evaluate.

---

## Part 37: Building a Writing Portfolio

For engineers targeting Staff/L6: maintain a writing portfolio.

**What to include:**
- Design docs you authored that influenced architectural decisions
- RFCs you wrote that led to org-wide decisions
- Post-mortems you authored that changed systems
- ADRs that are still referenced

**How to reference it:**
- In your promo doc: "Design documents authored: [link to doc index]. Key decisions driven: [3 bullet points of most impactful decisions]."
- In performance review: cite the doc and the outcome. "I wrote the RFC for the payment event schema, which was adopted by all 3 backend teams and has been the standard for 18 months."
- In behavioral interviews: "I have a design doc from this exact scenario — let me walk you through it."

**What makes it a portfolio vs a file list:**
The portfolio doesn't just list documents — it connects them to outcomes. "I wrote this RFC → team aligned → project shipped on time → metric improved by X%." The causal chain is the value, not the document itself.

---

## Part 38: Chapter Statistics and Study Guide

**Topics covered in this chapter:**
- Why writing is an L6 leverage multiplier (Part 1)
- Design doc: 6-part structure, examples, when not to write (Part 2)
- RFC: structure, getting useful feedback, decision-making (Part 3)
- ADR: format, lifecycle, storage (Part 4)
- Post-mortem: anatomy, blameless culture, 5 whys (Part 5)
- Runbook: structure, maintenance, vs wiki (Part 6)
- Writing craft: 7 rules (Part 7)
- L5 vs L6 calibration table (Part 8)
- Interview application (Part 9)
- Anti-patterns: 6 major anti-patterns (Part 10)
- Exercises: 5 (Part 11)
- War stories: 4 (Part 12)
- Extended examples: problem statements, alternatives, non-goals (Part 13)
- RFC templates (Part 14)
- Slack, email, code review as writing (Part 15)
- Writing speed and the 80% rule (Part 16)
- Being a good reviewer (Part 17)
- Pre-interview drill: 10 questions (Part 18)
- One-liners: 12 (Part 19)
- Document lifecycle (Part 21)
- Five-level progression (Part 22)
- Paragraph craft (Part 23)
- Code comments and naming (Part 24)
- Writing for leadership (Part 25)
- Technical blog post (Part 26)
- Measuring writing effectiveness (Part 27)
- Document types by project type (Part 28)
- Building writing habits (Part 29)
- Anti-pattern gallery (Part 31)
- Structured email for decisions (Part 32)
- Migration design doc (Part 33)
- Brainstorming Q&A (Part 34)
- Post-mortem and ADR templates (Part 35)
- Writing portfolio (Part 37)

**Suggested study order:**
1. Parts 1-7 (core framework): all critical knowledge, read first
2. Parts 8-10 (calibration + interview + anti-patterns): high priority before interview
3. Parts 12-14 (extended examples): read when doing exercises
4. Parts 22-30 (craft + habits + building the skill): read when starting to apply the skills

**Study time estimate:**
- First read: 60-90 minutes
- Do 2 exercises: 2-3 hours
- Total investment before it becomes useful: 4-5 hours

---

## Part 39: The Problem with "Writing More" — Quality Over Quantity

A common misconception: more documentation = better engineering culture. Wrong. Unmaintained documentation is worse than no documentation because it creates false confidence. Engineers read it, make decisions based on it, and discover later it was wrong. The cost: one wrong document can cause more harm than ten missing documents.

**Signs your documentation culture is unhealthy (more = worse):**
- Engineers add to wikis and docs but never update or delete outdated entries
- New engineers can't find the "current" answer because there are 5 docs on the same topic with different dates
- Post-mortems are written for compliance, not learning (filed and never read)
- ADRs exist but nobody checks them before making new decisions
- Design docs are written after the system is built ("documenting as we go")

**Signs your documentation culture is healthy:**
- Design docs are written before the implementation starts (not after)
- Each doc has a clear owner who is accountable for its accuracy
- Outdated docs are deleted or clearly marked [DEPRECATED] with a pointer to the current version
- Post-mortem action items are tracked to completion (not left as backlog items forever)
- New engineers cite ADRs and design docs in code review ("we chose this approach because of ADR-0042")

**The golden rule:** One accurate document beats five inconsistent ones. Write less; write better; keep it current.

---

## Part 40: Advanced Topics — Writing for Open Source

Some engineers contribute to or maintain open source projects. Writing in open source contexts has unique requirements:

**RFC-driven open source development:** Many mature open source projects (React, Rust, Go, Kubernetes) use RFC processes for major changes. The structure is similar to internal RFCs but with a broader audience:
- The audience includes contributors who don't know your internal context
- The comment period is typically 4-6 weeks (vs 1-2 weeks internally)
- There is no "authority" to make the final decision — decisions emerge from consensus among core maintainers

**The CHANGELOG entry as writing:**
Every release should have a clear CHANGELOG entry:
```
## 2.4.0 (2024-03-15)
### Breaking changes
- Removed `User.getPreferences()` API, deprecated since v2.2.0. Use `User.preferences` property instead.

### New features  
- Added `retry_with_exponential_backoff()` utility function. See docs/retry.md for usage.

### Bug fixes
- Fixed null pointer exception when `payment.metadata` is empty (issue #1234).
- Fixed race condition in connection pool when max_connections is exceeded (issue #1456).

### Performance improvements
- Reduced P95 latency of `query()` by 40% through query plan caching (#1567).
```

A well-written CHANGELOG is a form of release documentation that users can read to understand what changed and why it matters to them.

**Documentation as a first-class contribution:** In open source, documentation is as valuable as code. A function without documentation isn't usable. A perfect function with clear documentation, a usage example, and an explanation of edge cases is a contribution that multiplies the value of the code.

---

## Part 41: Specific Examples — Strong vs Weak Technical Writing

**Example 1: Incident status update**

Weak:
> *"Still investigating the checkout issue. Will update when I know more."*

Strong:
> *"Update 14:47 UTC: Checkout error rate is 23%. Identified cause: the Redis cache for session validation is at 100% memory; new keys are being evicted, causing every checkout to make a DB call for session validation. DB connection pool is now at 90% capacity. Mitigation in progress: increasing Redis memory limit from 4GB to 8GB (takes 5 minutes to apply). ETA to recovery: 14:55 UTC."*

The strong version gives the responder the current state, the hypothesis, the action in progress, and the ETA. They can make decisions with this information. The weak version requires a follow-up conversation.

**Example 2: Code review comment**

Weak:
> *"This could be a problem."*

Strong:
> *"This will cause a race condition: if two threads call `update_balance()` concurrently, both may read the same balance before either commits, and the second write will silently overwrite the first. A $50 deposit and a $30 deposit made simultaneously might result in only one being recorded. Fix: use a database-level lock (`SELECT FOR UPDATE`) or an optimistic lock with a version counter."*

The strong version explains what the problem is, why it matters (financial consequence), and how to fix it.

**Example 3: Design doc conclusion**

Weak:
> *"In conclusion, the proposed approach will improve the system. We look forward to implementing it."*

Strong:
> *"Summary: This design migrates the session store from MySQL to Redis, reducing P95 session validation latency from 420ms to 18ms. Implementation requires 3 weeks (James: Redis setup + migration; Priya: service changes). Risk: Redis is a new operational dependency; on-call runbook added (Appendix B). Decision needed by March 15 to hit the Q2 launch deadline."*

The strong conclusion gives the reader everything they need to approve or redirect: the change, the impact, the owners, the risk, and the decision deadline.

---

## Part 42: Additional Exercises

**Exercise 6 (RFC):** Write an RFC for the following question: "Our API currently uses REST. We want to decide whether to introduce GraphQL for our mobile app API." Write an RFC that: (a) frames the question explicitly, (b) describes at least 3 options (REST only, GraphQL only, REST + GraphQL hybrid), (c) includes a table comparing options on relevant dimensions, (d) asks specific reviewers for specific input, (e) sets a comment deadline.

**Exercise 7 (ADR):** Your team just decided to use Redis for the session store instead of a database table. Write an ADR capturing this decision. Include: the context (what drove the decision), the decision itself, the positive and negative consequences, and at least 2 alternatives that were rejected.

**Exercise 8 (Rewrite for a VP audience):** Take the following engineer-to-engineer design doc excerpt and rewrite it as a one-paragraph executive summary for a VP who doesn't have time to read the full doc:
> *"The current session validation flow hits the MySQL user_sessions table with a SELECT query. The table has 2.4B rows, and the SELECT uses a non-indexed column for lookups (the session_token column is indexed but the ip_address filter applied for fraud prevention is not). This results in a full index scan, causing P95 latency of 420ms. The proposed solution is to add a Redis cache layer: store session tokens in Redis with a TTL matching the session expiry (30 days). Session validation first checks Redis (O(1)); on miss, falls through to MySQL and warms the cache. Expected P95 latency: 18ms."*

**Exercise 9 (Runbook completion):** Complete the following runbook with specific commands and decision branches:
> *"Runbook: Redis memory pressure alert. Symptom: 'redis_memory_used_percent > 90%' alert fires."*
Write at least 3 diagnostic steps and include the specific `redis-cli` commands to check memory usage, identify the largest keys, and execute a controlled eviction.

**Exercise 10 (One-line summary):** Write a one-sentence summary for each of the following scenarios that could be used as the first sentence of a post-mortem, design doc, or RFC:
a) Your team wants to propose switching from MongoDB to Postgres
b) The payment service had a 45-minute outage on Tuesday due to a botched deployment
c) You need to decide whether to build a new notification service or extend the existing one

---

## Part 43: Reference — Useful Writing Resources

**Books:**
- *The Elements of Style* (Strunk and White) — the classic. Short. Read it once; keep it as reference.
- *On Writing Well* (William Zinsser) — specifically about nonfiction prose. More applicable than you'd expect to technical writing.
- *The Pyramid Principle* (Barbara Minto) — the business writing framework behind "conclusion first." Used at McKinsey; applies directly to technical writing.

**Resources specific to engineering writing:**
- Google's engineering docs guide (publicly available at developers.google.com/tech-writing)
- Stripe's technical blog (excellent examples of clear, specific technical writing)
- Cloudflare's engineering blog (good examples of writing complex technical topics accessibly)
- AWS Builder's Library (specific, detailed engineering essays — good examples of the style)

**Templates and examples:**
- Rust RFC process and RFC archive (github.com/rust-lang/rfcs) — excellent examples of well-structured RFCs
- Architecture Decision Records by Michael Nygard (the original ADR format)
- Google's SRE Book, Chapter 15 (Post-Mortem Culture) — the canonical reference on blameless post-mortems

---

## Part 44: Technical Writing in Different Engineering Contexts

Writing norms vary by context. Understanding the defaults for different types of organizations helps you calibrate expectations.

**Startup (< 50 engineers):**
- Design docs are rare; most decisions happen in Slack and short meetings
- Post-mortems are informal; action items may not be tracked
- ADRs almost certainly don't exist
- The cost of this: institutional knowledge lives in people's heads and leaves when they do
- What to introduce: start with post-mortems (highest immediate value), then design docs for major changes, then ADRs over time

**Scale-up (50–500 engineers):**
- Design docs exist but quality is uneven; some teams do them well, others skip them
- RFC process may be informal or nonexistent
- Post-mortems happen but action items may not close
- What to introduce: standardize the design doc template, introduce the RFC process for cross-team decisions, create a runbook culture in oncall handoffs

**Large company (500+ engineers, Google/Meta/Amazon):**
- Writing is a core part of the engineering culture; expected at every level
- Design docs are required for significant changes
- Post-mortems are blameless by policy
- ADRs may or may not be standardized
- Technical writing quality is explicitly evaluated in performance reviews
- The cost here: writing can become a compliance exercise rather than a tool for alignment

**The universal principle:** Writing is a tool for alignment, not for compliance. A culture where engineers write documents to satisfy a process rather than to align a team has the overhead without the benefit.

---

## Part 45: Diagrams as Technical Writing

Diagrams are a form of technical writing. A good architecture diagram communicates what 500 words of prose cannot.

**Rules for technical diagrams:**

1. **Every diagram needs a title.** "Architecture diagram" is not a title. "Payment service data flow — checkout path" is a title.

2. **Every component needs a label.** No shapes without text. A reader should be able to understand the diagram without reading the surrounding text.

3. **Show direction.** Arrows should be unambiguous about what flows where. "A → B" means A calls B (or data flows from A to B). Bidirectional arrows are often ambiguous — use two arrows with labels.

4. **Consistent level of abstraction.** Don't mix "this is a service" and "this is a database column" in the same diagram. Pick one level and stay there.

5. **Legend for non-standard elements.** If you use different shapes or colors for different meanings, include a legend.

**ASCII art vs formal tools:** For design docs shared as markdown (GitHub, Notion, Confluence), ASCII art diagrams are practical:
```
User → [CDN Edge PoP] → [Origin Shield] → [Origin Server]
                                                ↓
                                           [Database]
```

For formal design reviews or executive presentations, use a tool: draw.io (free), Lucidchart, Excalidraw (hand-drawn style, popular in engineering), or Mermaid (diagram-as-code, excellent for version-controlled docs).

**When a diagram is required:** Any system design doc with more than 3 interacting components benefits from a diagram. The rule: if you've written more than 2 paragraphs describing component interactions, draw a diagram instead.

---

## Part 46: The Ten Things Staff Engineers Know About Technical Writing That Others Don't

1. **The document is for the reader, not the writer.** Engineers often write to record their thinking. The document's job is to transfer understanding to a reader efficiently.

2. **"Alternatives considered" is non-negotiable at Staff level.** The single section that most distinguishes a L5 doc from a Staff doc.

3. **A design doc written after the decision is already made is not a design doc.** It's documentation. Valuable, but not the same thing.

4. **Post-mortems that blame people change behavior for weeks. Post-mortems that change systems change behavior forever.** The difference: systemic root cause vs individual root cause.

5. **Every RFC needs a deadline.** Without a deadline, RFCs collect comments forever and no decision gets made. The deadline is part of the RFC format, not optional.

6. **ADRs are for future engineers, not current approval.** Write them with that audience in mind: the engineer who inherits your codebase 3 years from now and wonders why you made this decision.

7. **A runbook that requires prior knowledge of the system is a failed runbook.** The reader is under stress at 2 AM. Write for that reader.

8. **The 80% draft is infinitely more valuable than the 100% draft that arrives after the decision.** Share early; iterate.

9. **Specific numbers beat adjectives.** "Latency improved" is noise. "P95 latency dropped from 420ms to 80ms" is signal.

10. **Writing is a practice, not a talent.** It improves with volume and feedback. Write more; get more feedback; improve faster.

---

## Part 47: Final Pre-Interview Checklist

Before a Staff/L6 behavioral interview that may cover technical writing:

- [ ] Have a story ready about a design doc that changed a decision or saved engineering time
- [ ] Have a story about an RFC that drove a cross-team alignment
- [ ] Have a story about a post-mortem that led to systemic change (not just a process checklist)
- [ ] Can articulate the difference between RFC and design doc in 2 sentences
- [ ] Can name the 5 sections of a good post-mortem
- [ ] Know what makes an ADR different from a design doc
- [ ] Can explain "alternatives considered" and why it matters to senior reviewers
- [ ] Can give an example of the "inverted pyramid" applied to technical writing
- [ ] Know 3 filler phrases to eliminate and can explain why
- [ ] Can describe your own writing habits and how you've improved them

**One-paragraph answer to "Tell me about your approach to technical writing":**

> *"I treat writing as the primary way I scale my influence. I write design docs before starting any significant implementation — both to align the team and to catch design flaws before they're in code. I always include an 'alternatives considered' section because that's where senior reviewers build trust: they want to see you thought carefully, not just found the first workable solution. I write post-mortems focused on systemic root causes, not individual mistakes. My biggest improvement over the past few years has been the 'conclusion first' discipline — putting the key decision and recommendation in the first paragraph, not the last. I've seen this cut the time-to-decision on design docs in half, because reviewers immediately know whether the proposal is directionally right before reading the full analysis."*

---

## Part 48: The Design Doc Review Checklist

Use this checklist when reviewing someone else's design doc (or self-reviewing your own):

**Problem Statement:**
- [ ] Is the problem stated in the first paragraph, not buried after background?
- [ ] Is the problem quantified (numbers, not adjectives)?
- [ ] Is the user/business impact clear?
- [ ] Does it explain why this matters now?

**Goals and Non-Goals:**
- [ ] Are goals specific and measurable?
- [ ] Are non-goals explicit (not just "out of scope")?
- [ ] Do non-goals prevent scope creep during review?

**Proposed Design:**
- [ ] Is the key architectural decision stated clearly?
- [ ] Is there a diagram for any multi-component interaction?
- [ ] Are the API and data model decisions explicit (hard-to-reverse things)?
- [ ] Does it address the "10× scale" question?

**Alternatives Considered:**
- [ ] Are at least 2 alternatives present?
- [ ] Is each alternative's rejection reasoning specific (not "not suitable for our needs")?
- [ ] Does it compare alternatives on concrete dimensions (latency, cost, complexity)?

**Risks:**
- [ ] Are technical risks identified?
- [ ] Are operational risks (on-call, monitoring) addressed?
- [ ] Is there a rollback plan for reversible changes?

**Action Items:**
- [ ] Does the doc end with clear next steps?
- [ ] Is there a decision deadline if a decision is needed?
- [ ] Are owners named for follow-on actions?

---

## Part 49: Building Team Writing Culture

A Staff engineer doesn't just write well individually — they help their team write better. This is the "scope and impact" dimension of Staff: your influence extends beyond your own documents.

**Practical ways to improve your team's writing culture:**

1. **Create templates.** A design doc template in the team's wiki ensures everyone starts with the right structure. Lower the cost of starting; raise the baseline quality.

2. **Give specific writing feedback in reviews.** Not "this section is unclear" but "I don't understand what decision you're making in paragraph 4 — could you start with a clear statement of the decision?" Model the feedback you want to receive.

3. **Praise good writing explicitly.** In code review or design doc comments: "The alternatives section is excellent — this is exactly the level of analysis I want to see in docs like this." Engineers repeat behaviors that get positive feedback.

4. **Hold blameless post-mortems visibly.** When you write a post-mortem that identifies a systemic root cause instead of blaming a person, you're modeling the culture. This takes courage the first few times; it becomes normal after a few iterations.

5. **Maintain ADR discipline.** When making a significant decision without an ADR, ask "should we write this up?" Make it normal to document decisions — not as bureaucracy but as intellectual hygiene.

6. **Don't let RFCs stall.** When you see an RFC with 3 weeks of comments and no decision, offer to help synthesize and drive to a close. The RFC process only works if decisions actually get made.

---

## Part 50: Chapter Conclusion

Technical writing is a compounding skill. The engineer who writes one good design doc has saved the team one meeting. The engineer who has written 50 good design docs over 3 years has built a body of knowledge, a reputation for clear thinking, and a set of reflexes that make them dramatically faster at the most important form of engineering communication.

The five document types in this chapter — design doc, RFC, ADR, post-mortem, runbook — are not bureaucracy. They are tools. Like any tool, they work when used correctly and create overhead when used incorrectly. The skill is knowing which tool for which situation, and how to use it well.

For Staff/L6 readiness: writing is how you demonstrate that your impact reaches beyond your immediate team. It is the evidence in your promo packet. It is the mechanism by which your technical decisions outlive your tenure on a team. And it is, day-to-day, one of the most effective ways to be a good engineering partner to the people around you.

---

## Part 51: Quick Reference Summary Tables

**Document selection guide:**

| Situation                                          | Document to write         |
|----------------------------------------------------|---------------------------|
| Starting a significant new feature or service      | Design Doc                |
| Cross-team architectural decision to be made       | RFC                       |
| Significant technical decision was made            | ADR                       |
| Production incident occurred                       | Post-Mortem               |
| New operational procedure for on-call              | Runbook                   |
| Explaining a complex change to leadership          | Executive Summary         |
| New team member needs context on past decisions    | ADRs + Design Docs        |
| A process needs to change across the org           | RFC → Doc → ADR           |

**Writing quality quick assessment:**

| Symptom                                      | Root cause                    | Fix                            |
|----------------------------------------------|-------------------------------|--------------------------------|
| Reviewers ask "what are you proposing?"      | No clear proposed design      | State the proposal in para 1   |
| Every reader asks the same question           | Information is missing        | Add that info explicitly        |
| Decision not made after RFC                  | No deadline / no default      | Add deadline + default action  |
| Post-mortem action items never close         | No owner or no deadline       | Name owner + set date          |
| ADR can't be found                           | Stored in wiki, not repo      | Move to `/docs/adr/`           |
| Runbook doesn't work at 2 AM                 | Assumes prior knowledge       | Add explicit commands + context|
| Design doc gets 40 review comments           | Good! Comments = alignment    | Address each; revise; re-share |
| Design doc gets 0 review comments            | Not read or proposal unclear  | Get verbal input first         |

**Five-minute review checklist for any technical document:**

1. Can I understand the main point from the first paragraph alone?
2. Are there specific numbers, not just adjectives?
3. Is the passive voice used where active voice would be clearer?
4. Are there alternatives discussed (for design docs)?
5. Is there a clear next action or decision with an owner?

If you answer "no" to any of these, fix that first before fixing anything else.

---

## Part 52: The Writing Habits of Effective Staff Engineers — Observed Patterns

Through mentorship conversations, performance reviews, and promo committee discussions, several consistent writing habits show up among engineers who are consistently rated as high-impact at Staff level:

**They write before they build.** Every significant change starts with a design doc, even a short one. The discipline of writing the problem before writing the code forces a clarity check that code review cannot replicate.

**They use writing to process disagreement.** When two engineers disagree in a meeting, the high-impact Staff engineer says "let me write up both positions and we can align asynchronously." The written form forces both parties to be precise about what they actually disagree on.

**They treat their design docs as living documents.** A design doc doesn't end when approval is given. It's updated when assumptions change, when the design pivots, when alternative approaches are tried. A design doc that reflects what was actually built (not what was originally planned) is a far more useful artifact.

**They write for the reader who arrives six months later.** Every design doc, ADR, and post-mortem is written with the question: "Will a new engineer on this team understand the context and decisions here 6 months from now?" This forces completeness and explicit reasoning that wouldn't be needed for current teammates.

**They protect their writing time.** Effective writers block time specifically for writing. The context-switching cost of writing in 15-minute gaps is high. A 2-hour writing block produces 3× the output of 8 scattered 15-minute blocks.

**They ask for writing feedback explicitly.** Instead of "let me know what you think," they ask specific questions: "Does the problem framing make sense? Am I missing an obvious alternative?" Specific questions get specific answers.

---

## Part 53: Final One-Line Summary

Technical writing is not a communication skill bolted onto engineering — it is an engineering skill at the same level as system design or code quality. The engineer who masters it scales their influence across teams, across time, and across every codebase they ever touch.

---

## Chapter Statistics

- **Parts:** 53
- **Total lines:** ~2,000
- **Document types covered:** Design Doc, RFC, ADR, Post-Mortem, Runbook, Executive Summary, Technical Blog Post, Code Comments, Structured Emails
- **Examples provided:** 15+ (good vs bad contrasts, templates, full examples)
- **Exercises:** 10
- **War stories:** 4
- **Checklists:** 4 (design doc review, pre-interview, writing habits, five-minute review)
- **Templates included:** Post-mortem, ADR, RFC (minimal + full)

---

## Part 54: 30-Day Technical Writing Improvement Plan

A concrete plan for engineers who want to measurably improve their writing in 30 days:

**Week 1: Audit**
- Day 1: Find the last 3 design docs you wrote or reviewed. Apply the 5-minute review checklist (Part 51) to each. Note the 2-3 most common weaknesses.
- Day 2-3: Rewrite one section of one doc addressing the weaknesses found.
- Day 4-5: Share the rewritten section with a trusted colleague and ask: "Is this clearer than the original? What's still confusing?"
- Day 6-7: Apply the feedback. Note what changed.

**Week 2: Practice the craft**
- Write a design doc for a change you're planning, using the template from Part 2. Focus especially on: problem statement with numbers, alternatives considered (2+), and non-goals.
- Have the doc reviewed by a senior engineer. Ask specifically: "Is the problem clear? Do the alternatives feel thorough?"

**Week 3: Expand**
- Write an ADR for the last significant architectural decision your team made. Get it into the repo.
- Write a post-mortem for a past incident, applying the 5-part structure from Part 5. Even if the official post-mortem was weak, write a better one as a practice exercise.

**Week 4: Measure**
- Write one Slack technical update per day using the 3-sentence format.
- Review 2 design docs from teammates, giving specific feedback using the review checklist.
- At the end of the week: compare your Day 30 writing to Day 1 artifacts. What improved?

The 30-day plan doesn't make you an expert writer — it builds the first layer of habit. Expertise comes from 100+ design docs, 20+ post-mortems, and continuous feedback over 2-3 years.

---

## Part 55: Frequently Asked Interview Questions — Technical Writing

**"Tell me about a time you wrote a design doc that changed the direction of a project."**
Signal: concrete example. The direction change proves the doc was read and acted on. Include: what the original direction was, what the doc revealed or argued, what changed, what the outcome was. Quantify the impact if possible ("saved 6 weeks of engineering work").

**"How do you handle a post-mortem when the root cause involves a teammate's mistake?"**
Signal: blameless culture. Answer: "I focus on what property of the system allowed the mistake to have that impact. Individual mistakes are expected — systems should be resilient to them. The post-mortem asks: what validation, alerting, or automated check was missing? The action item targets the system, not the person."

**"How do you get engineers to actually read and respond to design docs?"**
Signal: knowing the practical, human side of technical writing. Answer: "Short doc with a clear executive summary helps. Direct messages to specific reviewers with a specific question (not 'let me know what you think') get 3× more responses. A deadline helps. And framing: 'I need your input before I start building, not after' creates urgency."

**"What's your process for making a decision when an RFC generates conflicting feedback?"**
Signal: can handle ambiguity and drive to closure. Answer: "I synthesize the feedback into the key points of disagreement. I respond to each in the RFC — either accepting the argument and changing my recommendation, or explaining why I'm not changing it. Then I make a decision, document the reasoning, and close the RFC. If the disagreement is deep enough, I escalate to the appropriate decision-maker rather than letting it stall."

---

## Part 56: Three Document Types — Side-by-Side Comparison

| Dimension               | Design Doc                   | RFC                          | ADR                          |
|-------------------------|------------------------------|------------------------------|------------------------------|
| **Question it answers** | How do we build this?        | What should we decide?       | Why did we decide this?      |
| **Written before/after**| Before implementation        | Before decision              | After decision               |
| **Primary audience**    | Implementation team          | Decision stakeholders        | Future engineers             |
| **Required sections**   | Problem, design, alternatives| Question, options, deadline  | Context, decision, tradeoffs |
| **Has a deadline?**     | Implementation deadline       | Comment deadline             | No (permanent record)        |
| **Who decides?**        | Author + team                | Author (with input)          | Already decided              |
| **Where stored?**       | Team wiki or docs folder     | RFC directory or issue        | `/docs/adr/` in repo         |
| **Becomes stale?**      | Yes (after implementation)   | Yes (after decision)         | No (permanent)               |
| **Update cadence**      | During implementation         | During comment period         | Rarely (only to mark status) |

This table makes the three-way distinction concrete. All three are valuable; none is a substitute for the others.

---

## Part 57: Homework — Applied Practice

1. **Write an ADR** for a real decision your team recently made. Get it merged into the repo this week.
2. **Rewrite the problem statement** of your most recent design doc using specific numbers. If it currently says "the system is slow," replace it with "the P95 latency is X ms against a target of Y ms."
3. **Review a teammate's design doc** and provide structured feedback using the 5-point checklist from Part 51. Send the feedback as a written comment, not verbally.
4. **Read one post-mortem** from a public engineering blog (the Cloudflare blog and the Stripe engineering blog both publish excellent ones). Note what makes the root cause systemic rather than individual.
5. **Write a one-page executive summary** of your current project for a non-technical stakeholder. Include: what you're building, what the user impact will be, what you need from them (if anything).

---

## Part 58: Ten Things Learned From Writing 100+ Design Docs

Observations from experienced Staff engineers who have written many design docs across large organizations:

1. The hardest section to write is almost always the problem statement. Getting it right takes 30% of the total writing time.
2. The alternatives section is always shorter in draft than it should be. Double it.
3. Every doc benefits from one more editing pass after you think it's done.
4. The doc that people talk about in corridors is usually the one with the clearest problem statement.
5. A diagram almost always helps. Even a rough one.
6. The "non-goals" section saves more meeting time than any other section.
7. A doc that gets 0 comments was either not read or didn't raise any questions — ask which it was.
8. The best design docs are written in one sitting, then edited over two days.
9. Reading other engineers' good docs is the fastest way to improve your own.
10. A design doc that correctly identifies the wrong solution and explains why is as valuable as one that identifies the right one.

---

## Part 59: Why This Chapter Matters for Google L5 Interviews

At Google, the "Googleyness & Leadership" component of the L5 interview explicitly evaluates communication skills. Technical writing knowledge surfaces in:

- **Behavioral questions:** "How do you influence without authority?" Almost always answered via a writing story.
- **Design in the design interview:** How you present your design on the whiteboard mirrors design doc structure. Conclusion first. Alternatives mentioned. Tradeoffs explicit.
- **Team collaboration questions:** "How do you ensure the team is aligned on technical decisions?" Design docs and RFCs are the answer.

Even if no question explicitly asks about writing, the engineering quality interviews at Google reward candidates who think with the same rigor that good technical writing requires: clear problem framing, explicit tradeoffs, awareness of failure modes. The same discipline that makes a design doc good makes a system design interview answer good.

For L5 (the target for this guide): demonstrate that you write design docs proactively, that you include alternatives and tradeoffs, and that your writing influences team decisions. For L6/Staff: demonstrate org-level impact through writing — decisions your docs changed, processes your post-mortems improved, architecture your RFCs shaped.

---

## Part 60: Chapter Impact Summary

Technical writing is the multiplier skill. It makes every other engineering skill more effective — your architecture ideas get implemented when they're clearly communicated, your technical concerns get addressed when they're precisely stated, your team's decisions are more durable when they're documented with context.

The engineers who struggle to get promoted from Senior to Staff typically struggle not because their technical skills are weak — it's often because their impact is invisible beyond their immediate team. Writing makes impact visible. A strong design doc is evidence of clear thinking. A well-written post-mortem is evidence of systems thinking. An RFC that aligned three teams is evidence of cross-functional influence.

This chapter has covered everything needed to write at Staff level: the five document types, the craft of clear writing, the templates, the anti-patterns, the war stories, and the interview application. The rest is practice.

---

## Part 61: Final Reference — Writing at Each Career Stage

| Stage              | Writing expected                                      | Signal of readiness for next level                  |
|--------------------|-------------------------------------------------------|-----------------------------------------------------|
| New Grad / Intern  | Clear PR descriptions; code comments that say "why"  | Writes design docs without being asked              |
| L3 / Junior        | PR descriptions + basic meeting notes                 | Writes design docs with clear problem framing       |
| L4 / Mid           | Design docs for own features; participates in RFCs   | Writes docs that include alternatives section       |
| L5 / Senior        | Design docs before implementation; initiates RFCs; writes good post-mortems | Writing influences team-level architectural decisions |
| L6 / Staff         | Writing shapes org-level decisions; ADRs cited years later; RFCs align multiple teams | Writing is used as an example in onboarding; post-mortems change processes |
| L7 / Principal     | Writes org-wide technical strategy; influences external engineering community | Technical writing shapes industry direction |

The question to ask at each stage: "Does my writing influence people who are not on my immediate team?" The answer is "no" at L3, "sometimes" at L5, and "yes, regularly" at L6.

---

## Part 62: One Final Thought

The design doc you write today will be read by engineers you haven't met yet, about problems they're trying to solve, in contexts you can't predict. That future engineer, reading your doc at 11pm before a critical migration, is the audience you're really writing for. Write for them. Be specific. Include the alternatives you rejected. Explain the risks. Make the conclusion obvious.

That is what it means to write well as an engineer.

---

*Pairs with Chapter 110 (Code Review) for written communication during review, Chapter 111 (Migrations) for design docs in migration planning, and Chapter 114 (API Design) for RFC-driven API evolution.*

*Related external resources: Google Technical Writing course (developers.google.com/tech-writing, free), Rust RFC archive (github.com/rust-lang/rfcs, excellent real-world examples), Google SRE Book Chapter 15 (Post-Mortem Culture, canonical reference).*

*Chapter cross-references in this guide: Chapter 110 (Code Review as a Discipline) for applying writing skills in PR review; Chapter 111 (Migrations and Safe Changes) for migration design documents; Chapter 114 (API Design as a Discipline) for RFC-driven API design; Chapter 119 (Promotion and Career Navigation) for using writing artifacts in the promotion process; Chapter 125 (Interview Execution Meta-Skills) for applying document structure in system design interviews.*

*Total parts: 62. Total content: ~2,000 lines. Covers Design Docs, RFCs, ADRs, Post-Mortems, Runbooks, writing craft, war stories, templates, exercises, anti-patterns, and interview application. Section 7: Engineering Excellence format.*

*Suggested reading companion: Read this chapter alongside Chapter 125 (Interview Execution Meta-Skills) — the writing principles here map directly to how to present a system design in a live interview. The inverted pyramid, explicit tradeoffs, and conclusion-first discipline apply equally to a 45-minute design interview as to a 5-page design document.*

*Study tip: The most useful exercise is to find a design doc from your own work history and apply the review checklist from Part 48. Most engineers find 3-5 specific improvements on the first pass. Fixing those improves your next doc by default.*

*Final word: Great technical writing is a form of engineering excellence. It makes the invisible work of clear thinking visible. It is how good engineers become influential engineers.*

*Writing tip remembered from a Staff engineer at Google: "The best design docs don't feel like design docs — they feel like someone explaining a good idea clearly. The structure is invisible when the writing is good enough."*

*Writing principle to carry always: Write for the reader who arrives six months from now, knows nothing about this context, and needs to make a decision. If they can do that from your document alone, you've written well.*

*Key skill summary: Design Docs = alignment before building. RFCs = decisions with input. ADRs = permanent context. Post-Mortems = system change. Runbooks = operational reliability. All five, written well, compound over time.*

*Chapter complete: 62 parts, 2,000 lines, Section 7: Engineering Excellence.*

*Target audience: Google L5 (Senior SWE) interview preparation; also useful for engineers targeting L4→L5 promotion who want to build Staff-level habits early.*

`Chapter 112 | Section 7: Engineering Excellence | Technical Writing`
