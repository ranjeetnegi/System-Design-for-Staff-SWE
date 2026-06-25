# Chapter 119: Promotion & Career Navigation — Getting to L6 and Beyond

> *"The engineers who get promoted to Staff aren't always the best engineers. They're the ones who understood what 'Staff impact' means at their company, gathered the right evidence, and presented it in the right language at the right time. This chapter is the playbook."*

---

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│               AT-A-GLANCE: PROMOTION & CAREER NAVIGATION                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│  THE FUNDAMENTAL SHIFT    L5 = execute projects → L6 = change direction        │
│                           "I built X" → "I changed what we built and why"      │
│                                                                                 │
│  KEY ACTIONS              Brag doc (running log) → Promo packet (formal doc)   │
│                           Sponsorship → Calibration → Timing                   │
│                                                                                 │
│  TIMING REALITY           Most companies: 2 promo cycles per year              │
│                           Miss one cycle = 6 more months minimum               │
│                           Pre-calibration back-channel often decides outcome   │
│                                                                                 │
│  LEVEL EQUIVALENTS        Google L6 ≈ Meta E6 ≈ Amazon L7 ≈ Apple ICT5       │
│                           Google L5 ≈ Meta E5 ≈ Amazon L6 ≈ Apple ICT4       │
│                                                                                 │
│  EXTERNAL INTERVIEW       L5 → L6 jump is common when interviewing externally │
│                           (Fresh evaluation: no history to overcome)            │
│                                                                                 │
│  MOST COMMON FAILURE      Doing L6 work without making it visible or framing  │
│  MODE                     it at L6 impact level                                │
│                                                                                 │
│  THE BRAG DOC             Start on day 1. Update weekly.                       │
│                           Most engineers start 3 months before promo season.  │
│                           Too late.                                             │
│                                                                                 │
│  SPONSOR REQUIREMENT      Promotions require an advocate in calibration.       │
│                           Good work alone is necessary but not sufficient.     │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: What "Staff Level Impact" Actually Means

The single most important thing to understand about promotion to L6/Staff is what the level actually means. Most engineers have a vague sense that "it requires more experience" or "harder problems." The reality is more specific.

**The level ladder — impact scope:**

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                    THE ENGINEERING LEVEL LADDER                               │
├────────┬──────────────────┬────────────────────────────────────────────────────┤
│ Level  │ Scope            │ What "impact" means at this level                  │
├────────┼──────────────────┼────────────────────────────────────────────────────┤
│ L3/E3  │ Task             │ Completes assigned tasks correctly                 │
│        │                  │ Impact = quality and speed of individual work       │
├────────┼──────────────────┼────────────────────────────────────────────────────┤
│ L4/E4  │ Project          │ Owns a project end-to-end                          │
│        │                  │ Impact = project delivered on time, with quality   │
├────────┼──────────────────┼────────────────────────────────────────────────────┤
│ L5/E5  │ Area             │ Defines what projects to run in an area            │
│        │                  │ Impact = outcomes for a feature/service area       │
│        │                  │ Leads cross-team projects; mentors L3/L4           │
├────────┼──────────────────┼────────────────────────────────────────────────────┤
│ L6/E6  │ Team / Org       │ Changes what the team or org works on              │
│ Staff  │                  │ Impact = technical direction, not just execution   │
│        │                  │ Multiplies L5s; drives strategy; org-wide scope    │
├────────┼──────────────────┼────────────────────────────────────────────────────┤
│ L7/E7  │ Company          │ Drives multi-year technical strategy               │
│ Senior │                  │ Recognized externally; shapes recruiting and       │
│ Staff  │                  │ engineering culture                                │
└────────┴──────────────────┴────────────────────────────────────────────────────┘
```

**The fundamental shift from L5 to L6:**

```
L5 impact framing:
  "I built the new caching layer, which reduced p99 latency by 40%."
  
L6 impact framing:
  "I identified that our caching strategy was fundamentally wrong for our access 
   pattern — we were caching by user when we should have been caching by query 
   type. I made the case to my director, got buy-in from 3 engineering teams, 
   led the cross-team implementation, and reduced p99 latency by 40% — eliminating 
   our biggest customer support complaint category and freeing up 30% of our 
   database capacity."

The difference:
  L5: "I did the technical work"
  L6: "I saw what needed to change, convinced others, led the change, and measured the outcome"
```

**What "technical direction" actually means:**

This phrase is used constantly in Staff promotions but rarely explained. Concrete examples:

- Proposing and getting approved a new architecture for a system (not just implementing it)
- Identifying that the team is building the wrong thing and redirecting it (with evidence and data)
- Establishing a technical standard (API design patterns, testing requirements, data model conventions) that the entire org adopts
- Incubating a new technology or approach, proving it out, and evangelizing it to other teams
- Writing the 3-year technical roadmap for your org (not just your team's roadmap)

**The test question:**

> "If you left the company tomorrow, what technical decisions or directions that you drove would persist for years after you left?"

L5 answer: "The caching system I built would still be running."
L6 answer: "The caching strategy I introduced would still be the standard. The API design principles I established are now part of the onboarding guide. The observability framework I led is the foundation for two other teams' systems."

Impact at L6 is about direction, culture, and leverage — not just the artifacts you shipped.

---

## Part 2: The Promo Packet — Structure and Content

The promo packet is the formal written document you (or your manager) submits to the calibration committee. Understanding its structure helps you gather the right evidence over time, not scramble at the last moment.

**Typical promo packet structure:**

```
1. IMPACT SUMMARY (most important section — 3-5 bullets)
   Each bullet: [Scope] + [What you did] + [Measurable outcome]
   
2. PROJECT EVIDENCE (2-4 major projects)
   Each: context, your role, what you built, outcome, why it's L6 scope
   
3. TECHNICAL DEPTH (1-2 examples)
   Demonstrate that your technical judgment is trusted at the org level
   
4. INFLUENCE & LEADERSHIP (2-3 examples)
   Cross-team, mentorship, org-wide initiatives
   
5. PEER FEEDBACK (3-5 quotes)
   From people outside your team — these carry more weight than teammates
   
6. MANAGER ENDORSEMENT
   Your manager's narrative connecting all the above to the L6 rubric
```

**Writing strong impact bullets:**

The most common mistake: describing activity instead of impact.

```
❌ WEAK (activity-focused):
   "Led the migration of our service to Kubernetes, coordinating with 
    the infrastructure team and rewriting our deployment scripts."

✅ STRONG (impact-focused):
   "Led the Kubernetes migration for 8 services across 2 teams, reducing 
    deployment time from 45 minutes to 90 seconds, eliminating a class of 
    production incidents caused by manual deployment errors, and saving 
    $400K/year in infrastructure costs — established migration playbook 
    now used by 3 other teams."
```

**The SOAR framework for impact bullets:**

```
S = Scope:     What was the scale? (how many teams, users, services, $)
O = Obstacle:  What made this hard? (technical complexity, organizational resistance)
A = Action:    What did YOU specifically do? (not "we" — you)
R = Result:    What measurable outcome resulted?
```

**Example SOAR application:**

```
Scope:    "Across 4 engineering teams, affecting our 50M daily active users"
Obstacle: "The existing auth system had no abstraction layer, requiring each
           team to implement their own token validation, leading to 3 separate 
           security incidents in 2023"
Action:   "I designed a unified auth middleware, built the reference implementation,
           wrote the migration guide, and personally reviewed each team's integration"
Result:   "Zero auth-related security incidents in the 8 months since rollout.
           New teams onboard to auth in <2 hours instead of 2 weeks."
```

**What evidence to collect and how:**

```
Metrics:          Before/after numbers — latency, error rate, cost, developer velocity
                  Screenshots of dashboards (they disappear; save them)

PRs:              Links to your most significant code contributions
                  PRs you reviewed that prevented significant bugs

Design docs:      Every design doc you authored or co-authored
                  Comments you added to others' design docs that shaped the outcome

Incident reports: Postmortems where you drove the solution or the follow-up
                  Incidents you prevented (harder to document but valuable)

Cross-team work:  Emails, Slack messages, doc comments from engineers on other teams
                  "Thank you" messages are evidence; save them

Presentations:    Tech talks, design reviews, org all-hands slides
```

---

## Part 3: Sponsorship — The Hidden Requirement

This is the part most engineers don't talk about: promotions require a sponsor. Good work is necessary but not sufficient. Someone in the room at calibration needs to advocate for you loudly and have credibility with the other managers in the room.

**What a sponsor does:**

```
In calibration:         "Alice should be promoted. Here's why she's operating at L6.
                         [Specific examples.] I've seen her work directly and it's exceptional."

Pre-calibration:        Talks to peer managers informally before the official meeting:
                        "Alice is going up for L6 this cycle. You should know her work on X."

When you're not in       Pushes back when others question your work:
the room:               "I heard there's a concern about scope. Let me give you context on Y."

Raises your visibility: Invites you to present to their skip, includes you in org-wide decisions,
                        puts your name in OKR documents, mentions you in leadership meetings.
```

**How to earn sponsorship:**

You don't ask for a sponsor. You earn one by making your manager and skip-level manager look good, and by creating undeniable evidence that you're operating at the next level.

```
1. MAKE YOUR WORK VISIBLE
   Don't assume your manager knows everything you've done.
   Write weekly snippets. Send concise updates. Give internal talks.
   "My manager knows my impact" is a faith-based assumption; "I tell my manager 
   my impact weekly" is a system.

2. DELIVER ON YOUR COMMITMENTS
   Sponsors advocate for engineers who are reliable.
   Visibility without reliability = risky to advocate for.
   Reliability without visibility = invisible.

3. TAKE ON SCOPE THAT CREATES VISIBILITY FOR YOUR MANAGER
   If your manager's skip cares about X, volunteer to own X.
   Your success is your manager's win.

4. ASK FOR THE CONVERSATION EXPLICITLY
   "I want to be at L6 in 18 months. What do I need to do?"
   This tells your manager: (a) you're motivated, (b) you have a timeline,
   (c) you want their input — which means they're now invested in your success.
```

**The "18 months out" conversation:**

Have this conversation proactively, not reactively. Sample script:

```
"I've been thinking about my career trajectory. I want to be promoted to L6 
 within 18 months. I've been looking at the L6 rubric and I think my gaps are 
 [X and Y]. Can we align on what 'L6 impact' looks like specifically at our 
 org? And would you be willing to help me identify stretch opportunities that 
 address those gaps?"
```

This conversation does several things:
1. Signals ambition and self-awareness
2. Invites your manager to invest in your growth
3. Creates shared accountability ("we agreed on these gaps")
4. Puts your promotion on their radar 18 months out — long before the cycle starts

**What if your manager won't advocate for you?**

This happens. Sometimes the relationship isn't strong. Sometimes the manager is new or distracted. Sometimes the manager doesn't believe you're ready.

Options:
1. Find a secondary sponsor: your skip-level, a senior engineer who knows your work, the TL of another team you've collaborated with
2. Make your work known to your skip independently: design doc reviews, org all-hands presentations, cross-team projects
3. Ask directly: "What would I need to demonstrate to earn your strong support for an L6 promotion?" (Their answer tells you if the path exists)
4. Consider whether the opportunity exists here at all — some orgs are promotion-constrained by headcount

---

## Part 4: The Calibration Process — How Decisions Are Made

Understanding calibration helps you understand why "doing good work" isn't sufficient for promotion.

**How calibration works (typical structure):**

```
Week -4: Manager notifies you that you're being considered for promotion.
         You may or may not be asked to contribute to the promo packet.

Week -2: Promo packet submitted to HR/calibration system.

Week -1: Pre-calibration: your manager talks informally to peer managers.
         This is where many promotions are pre-decided.
         ("I'm putting Alice up for L6. Have you worked with her?" 
          If every manager says yes → very likely to pass calibration.)

Day 0:   Calibration meeting. Managers present their candidates.
         For each candidate: brief summary of impact → discussion → vote.
         The committee may include 5-10 managers you have never met.

Output:  "Promoted", "Strong No (needs development)", "No (close, retry next cycle)"
```

**What the committee is actually evaluating:**

They're not reading your PRs. They're listening to your manager's story and asking:
- "Does this person's impact sound like L6 impact?"
- "Have I seen their work from my team's perspective?" (cross-team visibility matters)
- "Is the scope real — org-wide or just within their team?"
- "Does the evidence match the claim?"

**The "strong yes" vs "yes" vs "no" distinction:**

```
Strong Yes:  "I've heard of this person from multiple directions, their impact is
              clear at L6 scope, no reasonable person would question this."
              → Promoted immediately.

Yes:         "The impact is there but the scope is narrow or the evidence is thin."
              → Usually promoted but sometimes deferred.

No/Close:    "I see potential but they haven't demonstrated sustained L6 impact yet."
              → Not promoted this cycle. Manager gets specific feedback to share.

Strong No:   "This is not ready. The scope is L5 at best."
              → Not promoted. May signal that manager's calibration is off.
```

**Timing — the most underestimated factor:**

Most companies run promotions in H1 (March/April) and H2 (September/October). Missing a cycle costs you 6 months. This means:

- If your packet isn't ready in August for an H2 cycle, your next shot is March.
- If you deliver your biggest project in December, the impact may not be established enough for March. Your real window might be September.

Build a timeline working backward:

```
Target promo cycle: H2 (October)
└── Packet due: August 15
    └── Cross-team feedback collected: August 1
        └── Project impact measurable (metrics stable): July 15
            └── Project shipped and in production: June 1
                └── Project started: January 1
```

---

## Part 5: Building the Evidence (12 Months Out)

The most important realization: promotion evidence is built over 12-18 months. You cannot manufacture it in the 2 months before the cycle. If you haven't started, start today.

**The Brag Doc — your most important tool:**

A brag doc is a running document you maintain throughout the year. Unlike the promo packet (which is polished, formal, and submitted once), the brag doc is your raw material.

```markdown
## Brag Doc — [Your Name] — [Year]

### [Month] [Year]
- Shipped: [project X] — reduced deployment time from 45m to 90s
  - Metric: deployment duration (Grafana dashboard: go/deploy-metrics)
  - Feedback: "This was blocking our entire team — huge unblock" — @bob (Slack, June 15)
  
- Code review: caught auth vulnerability in [PR link] — would have affected all users
  - My comment: [link]

- Design doc: authored [go/cache-redesign] — approved by director
  - Adopted by teams A, B, C

### [Next Month]
...
```

Update it at minimum weekly. Many engineers update it in real time as things happen (add an item when a project ships, when you get a compliment, when a design doc is approved).

**Why the brag doc matters:**

Your manager has many reports. They cannot remember everything you've done over 12 months. The brag doc is the raw material they use to write your promo packet. If you don't have it, they will write from memory — and memory is lossy and biased toward recent events.

**Making your work visible:**

```
Internal tech talks:      Even a 30-minute eng-wide talk on a problem you solved
                          makes you known beyond your immediate team.

Design doc reviews:       Comment on others' design docs. Your comments are visible.
                          Thoughtful technical feedback builds your reputation.

Incident postmortems:     Volunteer to write postmortems. They are high-visibility documents
                          read by directors and VPs. Driving the follow-up actions shows L6 scope.

Cross-team projects:      Any time you can work with engineers outside your team,
                          take that opportunity. Cross-team feedback carries more weight.

OKR documents:            Make sure your name appears in the OKR documents your director owns.
                          "Project led by Alice" in the Q3 OKR doc creates visibility.
```

**Closing the gaps — the L5 → L6 gap analysis:**

Before building evidence, you need to know what gap you're filling. Common gaps and how to close them:

```
GAP: "Scope is too narrow (only your team)"
FIX: Find a project with clear org-wide impact.
     Example: "Establish the observability standard for all 6 teams in our org"
     vs. "Add dashboards to my service"

GAP: "Technical depth is questioned"
FIX: Author a design doc for a hard technical problem.
     Get it reviewed and approved by senior engineers outside your team.

GAP: "Influence/leadership is weak"
FIX: Volunteer to TL a cross-team initiative.
     Mentor an L4 engineer formally — and make the outcome visible.
     Lead a working group.

GAP: "Communication/documentation"
FIX: Write more. Tech talks, design docs, postmortems.
     Get feedback on your writing. Practice writing to non-technical audiences.

GAP: "Not well known beyond your team"
FIX: Give eng-wide talks.
     Review design docs from other teams.
     Volunteer for org-wide projects (migration, tooling, standards).
```

---

## Part 6: When to Interview Externally

External interviewing is a legitimate career tool. Sometimes the most direct path to L6 is not up from within your current company.

**Why external interviews produce different outcomes:**

At your current company, you are evaluated against your history. Managers remember your mistakes from 2 years ago. You may be in a team where the "L6 slot" is perceived as already filled by someone senior. Your manager may have a mental model of you as an L5 that they haven't updated.

External companies evaluate you fresh — against your best interview performance, your narrative, and the evidence you choose to present.

**The L5 → L6 external jump:**

This is extremely common and well-known in the industry. An engineer who is performing at L5.5 — clearly above L5 but not quite with a full L6 promo packet — often gets leveled as L6 externally because:

1. External companies see the best version of your work (you curate your examples)
2. External companies compare you to the candidate pool (which often has many L4s and L5s)
3. The interview format rewards certain skills (whiteboard, system design) that internal promotions don't heavily weight
4. Some companies are specifically trying to hire future-L6 engineers and level optimistically

**Using an external offer as leverage:**

This strategy is real but risky. Sample conversation:

```
You: "I have an L6 offer from [Company] for $[X]. I prefer to stay here, 
     and I'd like to understand what our timeline looks like for L6."

Manager (good outcome): "We value you here. Let me talk to my director 
     about accelerating your promotion cycle. Can you share the offer details?"

Manager (bad outcome): "We don't counter-offer based on external offers.
     Your timeline for promotion is [standard answer]."
```

If the outcome is bad, the offer tells you that your current employer is not matching market rate and/or is not invested in your career. That is also valuable information.

**Risks:**

- If you use an offer as leverage and stay, you must now perform at L6 to justify the retention decision. The bar for your next performance review is raised.
- Some managers view "shopped an offer" as a sign of low loyalty and will deprioritize your work going forward.
- If the offer falls through or you're not actually willing to leave, you've shown your hand without a card to play.

**When to leave entirely:**

```
Signal 1: You've been L5 for 3+ years with consistently strong performance reviews.
          The promotion has been "almost ready" for multiple cycles.
          Interpretation: the org either doesn't have L6 headcount or
          doesn't believe you're there. External evaluation will tell you which.

Signal 2: Your scope keeps shrinking. Despite delivering L6 work, the projects
          given to you are L4/L5 scope. You cannot demonstrate L6 impact if
          you're not given L6 opportunities.

Signal 3: Your manager is blocking you, intentionally or by neglect.
          They're not advocating for you, not getting you visibility,
          not giving you stretch assignments.

Signal 4: The company is in layoff/freeze mode. Promotion headcount is frozen.
          This is external circumstance — not a reflection of your performance.
          This is the best time to interview externally.
```

---

## Part 7: Google vs. Meta vs. Amazon vs. Microsoft — How Levels Differ

The promo process differs meaningfully across companies. If you're at one company targeting another, or comparing your current level to a new offer, this table helps:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                    LEVEL EQUIVALENTS AND PROMO CULTURE                          │
├──────────┬─────────────┬────────────────────────────────────────────────────────┤
│ Company  │ "Senior     │ "Staff / L6 equivalent"                               │
│          │  L5 equiv"  │                                                         │
├──────────┼─────────────┼────────────────────────────────────────────────────────┤
│ Google   │ L5 SWE      │ L6 Staff SWE                                           │
│          │             │ Emphasis: technical depth + cross-org influence         │
│          │             │ "Googleyness": collaborative, ego-free, helpful        │
│          │             │ Promo cycle: H1 (April) and H2 (October)               │
│          │             │ Packet style: detailed, evidence-heavy                  │
├──────────┼─────────────┼────────────────────────────────────────────────────────┤
│ Meta     │ E5          │ E6                                                      │
│          │             │ Emphasis: impact metrics, speed, product sense         │
│          │             │ "Move fast": bias toward shipping over planning         │
│          │             │ Promo cycle: H1 (March) and H2 (September)             │
│          │             │ Packet style: data-driven impact bullets                │
├──────────┼─────────────┼────────────────────────────────────────────────────────┤
│ Amazon   │ L6 SDE II   │ L7 Senior SDE                                          │
│          │             │ Emphasis: Leadership Principles (especially:            │
│          │             │   Ownership, Invent & Simplify, Deliver Results,       │
│          │             │   Customer Obsession, Frugality)                        │
│          │             │ Promo cycle: Q1 (January) and Q3 (July)                │
│          │             │ Packet style: LP-aligned narrative                      │
├──────────┼─────────────┼────────────────────────────────────────────────────────┤
│ Microsoft│ 63/64       │ 65 Senior SWE / 66 Principal                           │
│          │             │ Emphasis: "Model Coach Care" culture                    │
│          │             │ Longer ramp-up expectations; tenure respected           │
│          │             │ Promo cycle: midyear review                             │
├──────────┼─────────────┼────────────────────────────────────────────────────────┤
│ Stripe   │ L5          │ L6                                                      │
│          │             │ Emphasis: technical rigor, written communication        │
│          │             │ Strong culture of writing — impact docs must be strong  │
│          │             │ More meritocratic; tenure less valued                   │
└──────────┴─────────────┴────────────────────────────────────────────────────────┘
```

**Google-specific notes:**

Google's promo process is famously rigorous. The L5 → L6 bar has increased significantly since 2020. Key points:

- **Perf ratings:** Google uses a rating system (Needs Improvement / Meets Expectations / Exceeds / Strongly Exceeds / Superb). Sustained "Exceeds" or "Strongly Exceeds" is a prerequisite for L6 promo consideration.
- **Cross-team requirement:** "Impact outside your immediate team" is explicitly stated in the L6 rubric. One cross-team project is minimum; two or more is the norm for strong cases.
- **Googlebot / design docs:** Go/ links (internal URLs) to design docs, launch reviews, and postmortems are the currency of evidence. Start writing and linking immediately.
- **L6 headcount:** There is typically a headcount constraint on how many L6s an org can have. Even if you're ready, you may be deferred if the org is at its L6 limit.

**Meta-specific notes:**

Meta's performance review cycle uses impact ratings. Impact is measured explicitly: "What user/business metrics moved because of your work?" For L6 at Meta, you need to show that your work moved a metric at scale. Vague "I improved the system" answers don't pass.

**Amazon-specific notes:**

At Amazon, the Leadership Principles are not background context — they are the primary language of performance reviews and promotion packets. Every impact bullet should tie to an LP. "Ownership" and "Deliver Results" are the most commonly cited. "Invent and Simplify" differentiates L6 from L5.

---

## Part 8: After L6 — L7, Principal, and Distinguished

L7/Principal/Distinguished Engineer is an entirely different category. The path is less structured and more political — there is no guaranteed "if you do X you will be promoted."

**The L7 characteristics:**

```
Scope:       Company-level, not org-level
             Your decisions affect the technical direction of multiple orgs

Recognition: Known by VPs and senior directors beyond your org
             May be known externally (conference talks, papers, open source)
             Other senior engineers consult you for your domain expertise

Influence:   You can redirect a team's work with a single conversation
             Your "opinion" has the weight of a decision

Cadence:     Works on problems that take 1-3 years to resolve
             Is comfortable with ambiguity that would paralyze L6 engineers

Rarity:      < 1% of engineers reach L7 or above
             Google's L7 bar is described as "you'd be ready to be CTO of a startup"
```

**The lifestyle trade-offs at L7+:**

Many L6 engineers deliberately do not pursue L7. The incremental compensation (usually meaningful but not as large as L5 → L6) does not offset the additional expectations:

- Constant organizational politics at executive level
- Responsibility for company-wide technical decisions with company-wide blast radius
- Less time coding (increasingly advisory and strategic)
- High visibility means high accountability for company failures as well as successes

The L6 → L7 path for engineers who want to stay technical (as opposed to going into management) often involves becoming a domain expert of rare depth — the person your entire company goes to for a specific class of problems (distributed systems, compiler design, storage engines, ML infrastructure, etc.).

**The management alternative:**

At each level, there is a choice: remain an individual contributor (IC) or enter the engineering management (EM) track. The comparison:

```
L6 IC path:        Stay technical, own systems, lead through technical influence
                   Slower title growth, often more interesting technical problems
                   Less organizational leverage but more freedom

EM path (M1/M2):   People management, team health, hiring, performance reviews
                   Faster path to director-level organizational impact
                   More organizational leverage but further from technical depth
                   
Neither is better. The choice depends on what you find meaningful.
```

---

## Part 9: The Brag Doc — Full Template

Here is a complete brag doc template you can use starting today:

```markdown
# Brag Doc — [Your Name]
# Updated: [Date]
# Target: L6 promotion cycle: [H1/H2] [Year]

---

## Impact Summary (update quarterly)
Most recent 3 bullets — should sound L6 by the time you submit the promo packet.

1. [Your strongest impact bullet — SOAR format]
2. [Second strongest]
3. [Third]

---

## Completed Work (running log — newest first)

### [Month Year]

**[Project Name]:**
- What: [1 sentence]
- Scope: [who was affected — # users, # teams, $ impact]
- My role: [IC / TL / co-lead / reviewer]
- Outcome: [measurable result with metric]
- Evidence: [link to design doc, PR, dashboard, Slack message]
- Feedback received: ["Quote from teammate/manager/cross-team peer" — @person, date]

**[Code review / design review / mentoring:]**
- What: [describe]
- Impact: [how did this change the outcome?]
- Evidence: [link]

---

## Cross-Team Work
(This section is for calibration — these peers can speak to your L6 scope)

- [Name, team, project]: [brief description of collaboration]
  - "Quote from them if you have one" — @name, date
  
---

## Design Docs Authored
| Doc | Link | Status | Impact |
|-----|------|--------|--------|
| [Cache Redesign] | go/link | Approved | Adopted by 3 teams |
| [Auth Middleware] | go/link | Approved | Org standard |

---

## Tech Talks / Presentations
| Date | Title | Audience | Notes |
|------|-------|----------|-------|
| [Date] | [Title] | Eng-wide (200 people) | [impact] |

---

## Mentoring
| Person | Timeframe | Outcome |
|--------|-----------|---------|
| [Name, L4] | [6 months] | Promoted to L5 |

---

## Gaps to Close Before Promo Packet
- [Gap 1]: Plan: [specific action with deadline]
- [Gap 2]: Plan: [specific action with deadline]
```

---

## Part 10: Common Promotion Anti-Patterns

**Anti-Pattern 1: "My work speaks for itself"**

The belief that excellent technical work will be recognized without self-advocacy. It won't — not reliably. In calibration, your manager must tell your story. If your manager doesn't know the full story, your work doesn't speak for itself.

---

**Anti-Pattern 2: "I'm too busy to document my impact"**

Everyone is busy. The engineers who get promoted are busy *and* they spend 15 minutes a week updating their brag doc. Not doing it is a choice to defer your promotion, not a necessary consequence of busyness.

---

**Anti-Pattern 3: Optimizing for lines of code instead of impact scope**

More PRs, more features, more code ≠ L6 impact. L6 impact requires scope (cross-team, org-wide) not volume. An engineer who ships one org-wide infrastructure change has more promotion-relevant impact than an engineer who ships 50 team-internal features.

---

**Anti-Pattern 4: Waiting until you "feel ready"**

L6 is not a feeling. It's a set of evidence. Engineers who wait until they feel confident about every L6 dimension before having the promotion conversation typically wait 6-12 months longer than necessary. Start the conversation when you're at 70% of the bar — the conversation itself helps you fill the remaining 30%.

---

**Anti-Pattern 5: Framing impact from the team perspective ("we built X")**

Promo packets are about your individual impact. "We" dilutes it. "I led, designed, implemented, drove, established, identified" are the words. Even if you worked on a team, your specific contribution must be attributable to you.

---

**Anti-Pattern 6: Not seeking feedback on your promo packet before submission**

Ask your manager to review your impact bullets 3 months before the cycle. Ask a recently promoted L6 to read your packet. Ask a skip-level to give informal feedback. The packet is your one shot — don't save the feedback for after it fails.

---

**Anti-Pattern 7: Conflating "I work hard" with "I have L6 impact"**

L6 is about scope and outcome, not effort. Working 70 hours a week on L4-scope tasks does not produce L6 evidence. Work on the right things, not more things.

---

## Part 11: The Promotion Conversation — Scripts and Templates

**Initiating the promo conversation with your manager:**

Use this when you're 12-18 months from your target cycle:

```
"I want to be intentional about my career growth. I'm targeting L6 promotion 
 in the [H2 Year] cycle. I've looked at the L6 rubric and I think my biggest 
 gaps are [gap 1] and [gap 2]. Can we spend 30 minutes talking about:
 
 1. Whether you agree with my gap assessment
 2. What specific opportunities exist in our org at L6 scope
 3. What you'd need to see to strongly support my promotion
 
 I want to start building the evidence now, not 3 months before the cycle."
```

**The quarterly check-in format:**

Every quarter, ask your manager:

```
"Quick promo check-in:
 
 1. Am I tracking well toward [H2 Year] L6 promo? 
 2. What's the strongest piece of evidence I've built this quarter?
 3. What's my biggest remaining gap?
 4. Is there anything I should be doing differently?"
```

**When your manager says "you need more cross-team impact":**

```
You: "I agree. What specific cross-team opportunities exist in the next quarter?
     Are there org-wide projects I could TL? Working groups I should join?
     Teams I could collaborate with on [your area of expertise]?"

Goal: Make it concrete. "More cross-team impact" is not actionable.
     "TL the Q2 observability initiative that spans 6 teams" is actionable.
```

**When your manager says "you're on track" but cycle after cycle passes:**

```
You: "I've been hearing 'on track' for 3 cycles. Can you help me understand
     specifically what the bar is and what evidence I'm still missing?
     I'd like to understand the delta clearly."
     
If the manager cannot answer clearly, the promotion may not be on the critical path for them.
This is the signal to evaluate whether to stay or interview externally.
```

---

## Part 12: L5 → L6 Gap Analysis Framework

Before building your promo packet, do a structured gap analysis. This table maps the common L6 rubric dimensions to self-assessment questions:

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                     L5 → L6 GAP ANALYSIS                                          │
├─────────────────────┬───────────────────────────────┬──────────────────────────────┤
│ DIMENSION           │ L5 EXAMPLE                    │ L6 EXAMPLE                   │
├─────────────────────┼───────────────────────────────┼──────────────────────────────┤
│ Technical Impact    │ Builds systems for my team     │ Builds systems adopted       │
│                     │ Solves hard technical problems │ org-wide; sets technical     │
│                     │ within a defined scope         │ standards across teams       │
├─────────────────────┼───────────────────────────────┼──────────────────────────────┤
│ Scope               │ 1 team, defined projects       │ 2+ teams, defines projects   │
│                     │                               │ others don't see yet         │
├─────────────────────┼───────────────────────────────┼──────────────────────────────┤
│ Influence           │ Influences immediate team      │ Influences beyond org;       │
│                     │ through code and reviews       │ changes technical direction  │
├─────────────────────┼───────────────────────────────┼──────────────────────────────┤
│ Ownership           │ Owns execution of a project    │ Owns outcome of an area;     │
│                     │                               │ drives strategy not just tasks│
├─────────────────────┼───────────────────────────────┼──────────────────────────────┤
│ Communication       │ Communicates technical work    │ Drives org-level technical   │
│                     │ clearly within team            │ vision through writing and   │
│                     │                               │ presentations                │
├─────────────────────┼───────────────────────────────┼──────────────────────────────┤
│ Mentoring           │ Mentors 1-2 junior engineers   │ Multiplies L5s; creates      │
│                     │                               │ frameworks others use to     │
│                     │                               │ make decisions               │
├─────────────────────┼───────────────────────────────┼──────────────────────────────┤
│ Problem Definition  │ Solves problems given to them  │ Identifies what problems     │
│                     │                               │ the org should be solving    │
│                     │                               │ that it hasn't yet recognized │
└─────────────────────┴───────────────────────────────┴──────────────────────────────┘
```

**Self-assessment exercise:**

For each dimension, write your honest current state, then write what L6 looks like in your specific org. The gap is what you need to build evidence for.

```
TECHNICAL IMPACT
Current state: "My last project reduced billing errors by 20% for my team's service"
L6 bar at my org: "Impact on billing accuracy across all 8 billing services, or
                   establishing the standard that other services adopt"
Gap: "Need to take this work to other teams or establish a standard"
Plan: "Propose a billing reliability working group — volunteer to lead it"
```

---

## Part 13: War Stories — Promotion Paths in Practice

**War Story 1: The Engineer Who Did the Work But Not the Visibility**

A senior engineer at a large tech company spent 18 months building the most sophisticated distributed cache her org had. The cache reduced infrastructure costs by $3M/year and eliminated their most frequent production incident type. She never gave a tech talk. She never wrote a design doc. Her promo packet was "I built a cache that saved $3M."

The promotion committee's response: "The impact is real but we don't understand the technical depth. We don't know if this was a one-person project or a team project. There's no evidence of cross-team influence."

She was deferred. The following cycle, she wrote the design doc (retrospectively, working from the implementation), gave a 45-minute eng-wide talk, and onboarded two other teams onto the cache. Same work — completely different evidence. She was promoted in the second cycle.

**The lesson:** The work doesn't change. The visibility and framing does.

---

**War Story 2: The "Almost There" Engineer Who Left**

An L5 engineer at Google was told "you're close to L6, keep going" for three consecutive promo cycles (18 months). Each cycle, the feedback was slightly different: "needs more cross-team influence," then "needs more technical depth signal," then "the org is at L6 headcount capacity."

After the third deferral, he interviewed externally and received two L6 offers. He returned to his manager with one of the offers. His manager said he couldn't match the level internally "due to headcount." He left.

18 months later, a colleague told him his team had been reorganized, the L6 headcount had been freed up, and two of his former teammates had been promoted to L6 in the following cycle.

**The lesson:** Sometimes the environment is the constraint, not your performance. When the org cannot create the opportunity for you to demonstrate L6 impact, the external market can.

---

**War Story 3: The Fast-Tracker Who Failed the Promo**

A brilliant L5 engineer at a startup had a stellar record: shipped fast, high code quality, excellent code reviews. He applied for L6 after 18 months at L5. His manager supported him strongly.

In calibration, peer managers asked: "Has anyone from other teams worked with him directly?" Answer: "Not really — he's been focused on our team's roadmap."

Deferred. The feedback: "Exceptional within team but no evidence of org-level impact."

He was frustrated. "I've been the most productive engineer on the team for 18 months. Why does it matter if other teams know me?"

Because at L6, you are expected to make other teams better. The promotion system rewards scope — not just productivity at the current scope.

He spent the next 6 months intentionally collaborating cross-team: led a cross-team migration, gave three internal talks, reviewed design docs from two other teams. Promoted in the next cycle.

**The lesson:** Scope is not optional at L6. Being excellent within your team is L5. Influencing beyond your team is L6.

---

## Part 14: The Behavioral Interview Questions — Career and Growth

When interviewing for L6 roles externally, or when skips and directors evaluate you internally, you will face behavioral questions specifically about career growth and ambition. Strong answers show self-awareness, intentionality, and L6-level thinking.

**"Where do you see yourself in 5 years?"**

```
❌ Weak: "I want to be a principal engineer or maybe move into management."
         (Generic, no specifics, no evidence of thought)

✅ Strong: "I see myself continuing on the IC track, likely at Staff or Principal level.
            The problems I find most compelling are [specific domain] — I want to be the
            person in my org who has the deepest expertise in this area and can drive
            the technical strategy for it. In the next 2-3 years, I'm focused on building
            more org-wide impact: driving technical standards, mentoring L5 engineers
            to L6, and building the kind of cross-team trust that lets me influence
            direction without authority."
```

**"Tell me about a time you were passed over for promotion and how you handled it."**

```
Situation: "I was deferred for L6 at [Company] in [cycle]. I had done significant
            technical work that I thought was L6-level."
            
Task:      "I needed to understand the specific gap and address it concretely."

Action:    "I asked my manager for written feedback from calibration — not just
            'needs more cross-team scope,' but specific examples.
            I learned that while my technical work was strong, I had no evidence
            of influence outside my immediate team.
            Over the next two quarters, I deliberately led two cross-team projects,
            gave an eng-wide talk, and collected explicit feedback from two peer teams
            before the next cycle."
            
Result:    "I was promoted in the following cycle. More importantly, I learned
            that promotions require evidence that other people can vouch for —
            and that I needed to actively create those opportunities rather than
            waiting for them."
```

**"Describe a time you influenced a technical decision without having authority."**

This is the core L6 behavioral question. It's testing your ability to drive direction without a title.

```
Strong answer elements:
- The stakeholders involved (should be ≥ 2 teams, ideally cross-org)
- How you built the case (data, prototypes, written proposals)
- How you navigated resistance (specific objections and how you addressed them)
- The outcome (was your approach adopted? how broadly? what was the impact?)
- What you'd do differently (shows self-reflection and learning)
```

---

## Part 15: The "Staff Engineer Archetypes" Framework

Will Larson (author of "Staff Engineer") describes four archetypes of Staff engineers. Understanding which one fits your style helps you target the right kinds of projects for promotion evidence:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                    STAFF ENGINEER ARCHETYPES                                    │
├────────────────┬─────────────────────────────────────────────────────────────────┤
│ Tech Lead      │ Works closely with a team, drives technical direction for a     │
│                │ specific system or service area.                                │
│                │ Best for: engineers who love depth in one area                 │
│                │ Pitfall: too narrow; must show cross-team impact to be L6       │
├────────────────┼─────────────────────────────────────────────────────────────────┤
│ Architect      │ Owns the overall technical vision across multiple teams.        │
│                │ Does system design, sets standards, reviews major decisions.    │
│                │ Best for: engineers who love breadth and system design          │
│                │ Pitfall: can lose technical credibility if too far from code    │
├────────────────┼─────────────────────────────────────────────────────────────────┤
│ Solver         │ Finds and solves the hardest problems in the org.               │
│                │ Moves from crisis to crisis; not tied to one team.              │
│                │ Best for: engineers who like variety and hard technical problems │
│                │ Pitfall: lack of sustained ownership; hard to show impact over  │
│                │          12 months vs. one-off heroics                          │
├────────────────┼─────────────────────────────────────────────────────────────────┤
│ Right Hand     │ Works closely with an executive or director, amplifying their   │
│                │ technical vision and driving their priorities.                   │
│                │ Best for: engineers who are good at organizational navigation   │
│                │ Pitfall: success is tied to their sponsor's success; can be     │
│                │          seen as "political" rather than technical               │
└────────────────┴─────────────────────────────────────────────────────────────────┘
```

Most L6 engineers are a blend. But identifying your natural archetype helps you:
1. Target the right types of projects
2. Frame your impact in terms the calibration committee recognizes
3. Identify which archetypes you're being compared against in calibration

**The Tech Lead trap for L6 candidates:**

The most common L6 failure case is the deep technical engineer who is exceptional within their team but has never demonstrated cross-team influence. They present a Tech Lead archetype but the calibration committee is looking for at least traces of Architect-level influence. The fix: volunteer for cross-team architectural work, even if it's not your natural style.

---

## Part 16: Pre-Interview Drill — 12 Questions

Use these to prepare for any conversation about your career trajectory, promotion readiness, or L6 scope:

**1.** What is the fundamental difference between L5 and L6 impact?
> *L5 defines and executes projects. L6 changes what the team or org works on — direction, not just execution.*

**2.** What are the three components of a successful promotion?
> *Evidence at L6 scope + a sponsor who advocates for you + timing aligned to the cycle.*

**3.** What is a "brag doc" and why does it matter?
> *A running log of accomplishments, metrics, and feedback updated throughout the year. The raw material for the promo packet. Without it, your manager writes from memory — which is lossy.*

**4.** Why do most promotions fail at calibration rather than at the manager level?
> *Because calibration is a committee of managers who don't know you. Your work must be legible to people with no context — through cross-team visibility and clear impact framing.*

**5.** What does "cross-team impact" mean specifically?
> *Engineers outside your team can speak to your contributions. Either you led a project that affected their work, or you established a standard they adopted, or you reviewed their design and changed its direction.*

**6.** How do you use the SOAR framework for impact bullets?
> *Scope + Obstacle + Action (specifically yours) + Result (measured). "Led org-wide migration of 12 services, overcoming [obstacle], reducing infra cost by $2M/year."*

**7.** What is the difference between a sponsor and a manager?
> *A manager writes your performance review. A sponsor advocates for you in calibration when you're not in the room — often your manager, but can also be a skip-level or a senior engineer who knows your work.*

**8.** Why might an engineer do L6 work but not get promoted?
> *Visibility: the work isn't known beyond their team. Framing: the work is described as activity not impact. Timing: the evidence isn't ready when the cycle hits. Headcount: the org is at L6 capacity.*

**9.** When is interviewing externally the right move?
> *After 2+ years at L5 with sustained strong performance and no promotion. When the org can't create L6-scope opportunities for you. When the market is strong and you want to calibrate your market value.*

**10.** What are the four Staff engineer archetypes?
> *Tech Lead (team depth), Architect (cross-team system design), Solver (hardest problems), Right Hand (executive amplifier). Most L6 engineers are a blend.*

**11.** What's the one question to ask your manager 12 months before your target promo cycle?
> *"What do I need to demonstrate to earn your strong support for an L6 promotion in [cycle]? What's my biggest gap today?"*

**12.** What does "technical direction" mean in the context of an L6 promo?
> *Proposing and getting approved changes to the technical strategy — architecture redesigns, new standards, technical roadmap. Not just implementing the direction someone else set.*

---

## Part 17: The Google Rubric — What L6 Looks Like in Practice

Google publishes its engineering ladder internally. The L6 rubric emphasizes:

**Technical Leadership:**
- Develops and maintains a multi-year technical vision for an area
- Makes architectural decisions that influence multiple teams
- Is consulted by other senior engineers for technical judgment

**Impact:**
- Work significantly affects the entire team's productivity and/or company metrics
- Identifies high-priority problems before they become crises
- Influences product roadmap based on technical insights

**Influence without authority:**
- Gets buy-in for major technical changes across org boundaries
- Resolves technical disagreements between teams
- Mentors L5 engineers toward L6 scope

**Communication:**
- Writes design docs and technical proposals that are adopted org-wide
- Presents technical vision to directors and VPs effectively

**The L6 "smell test" at Google:**

An interviewer or calibration committee member asks themselves:
> "If I were a L4 or L5 engineer on a different team, would I have heard of this person's work? Would I seek them out for technical advice?"

If yes → strong L6 signal.
If no → probably L5 operating within their team.

---

## Part 18: Building Cross-Team Visibility Without Being Annoying

One common concern: "I want to build cross-team visibility but I don't want to seem like I'm self-promoting."

The solution is **contribution-based visibility** rather than **presence-based visibility**.

**Contribution-based visibility (good):**

```
Review design docs from other teams with substantive, specific feedback:
  "I reviewed the proposed schema change in go/auth-redesign and noticed
   that the proposed index structure will cause full-table scans for the
   query pattern described in the performance requirements. I left a comment
   with an alternative." → saves that team days of debugging

Offer to do a postmortem for a cross-team incident:
  "I heard your team had an incident last week that touched our service.
   I'd be happy to write the postmortem and drive the follow-up if that
   would be useful." → high-visibility, high-value contribution

Volunteer for cross-team working groups:
  "I noticed the Platform team is forming a reliability working group.
   I'd like to represent our team if that's useful." → builds relationships
   across teams AND creates forum to demonstrate L6 scope

Open-source your internal tools:
  "I built this observability framework for our team. I think other teams
   could benefit — I'll propose sharing it at the next eng-all-hands."
```

**Presence-based visibility (avoid):**

```
Commenting on everything in Slack just to be seen
Attending meetings you weren't invited to "for visibility"
Adding yourself as a reviewer to PRs without being asked
Broadcasting your accomplishments in channels without adding value
```

The difference: contribution-based visibility creates value for others. Presence-based visibility consumes others' attention without creating value. One builds reputation; the other erodes it.

---

## Part 19: Exercises for Building the L6 Skillset

### Exercise 1: Write a Retrospective Impact Bullet

Take a project you completed in the last 12 months. Write the L5 version of the impact bullet and the L6 version.

```
L5 version: [describe what you built]
L6 version: [use SOAR — Scope + Obstacle + Action + Result]

Compare them. What information did you add? Why does it matter for calibration?
```

---

### Exercise 2: Map Your Cross-Team Network

Create a table:

| Engineer name | Team | How we've collaborated | Could they speak to my L6 scope? |
|---------------|------|----------------------|----------------------------------|
| ...           | ...  | Design review / co-TL / ... | Yes / No / With more evidence |

If the "Yes" column has < 3 names, you have a visibility gap to close before your next promo cycle.

---

### Exercise 3: Write Your 18-Month Plan

```
Target cycle: [H1/H2 Year]

Biggest current gap: [specific gap]
Action to close gap: [specific project with cross-team scope]
Timeline: [Q1 / Q2 / Q3 this year]

Second gap: [...]
Third gap: [...]

Sponsorship: Does my manager know I'm targeting L6 in this cycle? Yes / No
If No: When will I have that conversation? [date]
```

---

### Exercise 4: Review Someone Else's Impact Bullet

Find a promo packet template online (they are publicly discussed on Blind, Levels.fyi, and internal wikis). Evaluate 3 impact bullets from a real or hypothetical promo packet:

1. Is it SOAR-structured (Scope + Obstacle + Action + Result)?
2. Does it have measurable outcomes?
3. Is "I" the subject (or is it diluted with "we")?
4. Does the scope suggest L6 (cross-team/org-wide) or L5 (one team)?

---

## Part 20: Promotion and the Engineering Culture at Your Company

The promotion process at a healthy engineering company should be:
1. **Transparent**: rubrics are published; expectations are clear
2. **Fair**: decisions are made by committee, not individual managers
3. **Predictable**: timelines are known; feedback is actionable

The promotion process at an unhealthy engineering company:
1. **Opaque**: "you'll know it when you're there" — no clear rubric
2. **Political**: who you know matters more than what you've done
3. **Arbitrary**: feedback is inconsistent across cycles

Knowing which environment you're in changes the strategy:

```
Healthy environment:
  → Focus on building evidence against the published rubric
  → Trust the system, work the system
  → The feedback is actionable: do what it says

Unhealthy environment:
  → The promotion decision is often made on politics and perception
  → Managing up and sideways is as important as the work
  → If you've been deferred 2+ times with vague feedback, consider exiting
```

This is not cynical — it's practical. Understanding the environment lets you direct your effort correctly rather than being surprised by outcomes that aren't connected to your performance.

---

## Key Takeaways

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                 KEY TAKEAWAYS: PROMOTION & CAREER NAVIGATION                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  1. THE SHIFT      L5 executes projects; L6 changes direction.                 │
│                    "I built X" is L5. "I changed what we built and why" is L6. │
│                                                                                 │
│  2. EVIDENCE       Start building the brag doc today.                          │
│                    Update it weekly. Most engineers start too late.             │
│                                                                                 │
│  3. VISIBILITY     Cross-team impact is not optional at L6.                    │
│                    Give talks, review design docs, lead cross-team projects.   │
│                                                                                 │
│  4. SPONSORSHIP    Good work + invisible = no promotion.                       │
│                    Have the "I want L6 in 18 months" conversation today.       │
│                                                                                 │
│  5. TIMING         2 cycles per year. Missing one = 6 months.                  │
│                    Build the evidence 12 months out, not 3.                    │
│                                                                                 │
│  6. EXTERNAL       L5 → L6 external jump is common.                            │
│     OPTION         Use it to calibrate your market value and your org's bar.   │
│                                                                                 │
│  7. FRAMING        SOAR: Scope + Obstacle + Action + Result.                   │
│                    "We built X" fails. "I led [org-wide] X, reducing Y by Z"   │
│                    is what calibration committees can act on.                  │
│                                                                                 │
│  8. ARCHETYPES     Know your natural archetype (Tech Lead, Architect,          │
│                    Solver, Right Hand) and build evidence in that direction.   │
│                                                                                 │
│  9. ENVIRONMENT    If feedback is consistent and actionable → trust the system. │
│                    If feedback is vague and inconsistent → evaluate your options.│
│                                                                                 │
│  10. L7+           Less structured, more political, higher stakes.             │
│                    Get to L6 first, evaluate from there.                       │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 30-Day Study Schedule

**Week 1: Understand the system**
- Day 1: Read Parts 1-4 (impact, promo packet, sponsorship, calibration)
- Day 2: Read your company's engineering rubric (internal wiki or public equivalent)
- Day 3: Read Parts 5-8 (evidence building, external interviews, company-specific, L7)
- Day 4: Start your brag doc — add everything from the last 6 months you can remember
- Day 5: Schedule the "I want L6 in 18 months" conversation with your manager

**Week 2: Practice**
- Day 6: Write your 3 strongest impact bullets in SOAR format
- Day 7: Identify your cross-team network (Exercise 2)
- Day 8: Read Parts 9-12 (brag doc template, anti-patterns, conversation scripts, gap analysis)
- Day 9: Do the gap analysis (Part 12) — identify your top 2 gaps
- Day 10: Draft your 18-month plan (Exercise 3)

**Week 3: External calibration**
- Day 11: Read Parts 13-16 (war stories, behavioral questions, archetypes)
- Day 12: Practice the behavioral question "Tell me about a time you influenced without authority"
- Day 13: Research your market value — look up compensation and levels at target companies
- Day 14: Decide: are you going for internal promotion, external, or both?

**Week 4: Integration**
- Day 15-21: Apply to the current chapter — write one impact bullet per day
            Review each bullet against the SOAR framework
            Share 2-3 bullets with a trusted peer or your manager for feedback
            Update your brag doc with this week's work
            Identify one cross-team collaboration to pursue this quarter

---

## Part 36: The Career Checkup — Annual Review Questions

Once a year, ask yourself these questions honestly. They reveal whether you're on track or need to recalibrate:

**Technical scope:**
1. In the last 12 months, have I made any decisions that changed what my org built?
2. Have I established any standard or framework that other teams adopted?
3. Have I identified a major technical problem that wasn't already on the roadmap?

**Visibility:**
4. Can 3+ engineers from other teams describe my most impactful work from the last year?
5. Have I given at least one internal tech talk attended beyond my immediate team?
6. Does my skip-level manager have a clear picture of my top 3 impacts?

**Evidence:**
7. Do I have a brag doc with ≥ 10 substantive entries from the last 12 months?
8. Do I have 3 impact bullets in SOAR format that I'm confident about?
9. Are my impact bullets measurable? (If there are no numbers, they're probably not strong enough)

**Sponsorship:**
10. Has my manager explicitly said they plan to support my promotion in the next cycle?
11. Have I had a conversation with my skip in the last 6 months about my career?
12. Do I know who else is being considered for L6 in my org and how my case compares?

If you can answer "yes" to 10/12 of these, you're on track. If you can answer "yes" to 7/12, you have specific gaps to address. If fewer than 7, step back and have a direct conversation with your manager about what a realistic timeline looks like.

---

## Companion Resources

- **"Staff Engineer"** — Will Larson (archetypes, sponsors, promotion paths — the defining book on this topic)
- **"The Staff Engineer's Path"** — Tanya Reilly (complementary; more focused on day-to-day technical leadership)
- **Levels.fyi** — anonymous compensation and level data; useful for external calibration
- **Blind** — anonymous community; useful for anecdotal promo process insights at specific companies
- **"An Elegant Puzzle"** — Will Larson (engineering management; useful for understanding how managers think about promotions)
- **Gergely Orosz's Substack** (The Pragmatic Engineer) — detailed breakdowns of promo processes at major tech companies

---

## Memorable Quotes

> *"Promotions are a lagging indicator. By the time the committee says yes, you should have been operating at the next level for 12 months."*

> *"Your manager is your representative in calibration. If they can't tell your story in 60 seconds, you haven't given them the material."*

> *"The promotion doesn't come from doing the same work better. It comes from doing different work — at a different scope."*

> *"I've never seen someone promoted for working harder. I've seen many people promoted for changing what the team worked on."* — Staff engineer at Google

> *"Writing your brag doc is not self-promotion. It's documentation. The alternative is asking your manager to remember everything you did for 12 months."*

---

---

## Part 21: The L6 "Multiplier" Concept

One of the defining characteristics of an L6 engineer is that they make the engineers around them more effective. This is distinct from being an excellent individual contributor. The word "multiplier" is used specifically:

**What multiplying looks like in practice:**

```
You designed a system architecture that three other teams adopted,
allowing them to ship in weeks instead of months.
Result: you multiplied 3 teams' output.

You wrote a testing framework that became the standard for the org.
Every new service is built with your framework.
Result: you multiplied testing quality across the org.

You mentored an L4 engineer and guided them through their first L5-scope project.
They now operate independently at L5.
Result: you multiplied the team's senior engineering capacity.

You wrote a runbook for a class of incidents that had been escalating to you personally.
On-call engineers can now resolve these without your help.
Result: you multiplied the team's operational resilience.
```

**The test:**

> "What exists in the org that wouldn't exist without your initiative — and that would continue to exist if you left?"

If your answer is only "code I wrote," you're operating as an individual contributor.
If your answer includes frameworks, standards, runbooks, engineers you mentored, or processes you established — you're operating as a multiplier.

**The "code debt" trap:**

Some technically excellent engineers multiply their own output by working harder and faster. They write more code, review more PRs, fix more bugs. This is valuable — and it's not L6. L6 is multiplying the output of others through leverage: frameworks, standards, mentoring, architecture.

The shift is uncomfortable because it means spending time on things that don't produce immediate shipping output. Writing a framework takes 3× as long as writing the feature directly. But the framework pays off when 5 other engineers use it without your involvement.

---

## Part 22: Navigating Organizational Politics

L6 engineers cannot avoid organizational politics — they must navigate it. "I just want to write code" is a valid preference that will cap your career at L5.

**The two types of organizational influence:**

```
Technical influence:   Your technical arguments are correct and compelling.
                       People follow your recommendation because it's right.
                       
Relational influence:  People trust you because of your track record and relationships.
                       They give you the benefit of the doubt when they're uncertain.
```

L5 can survive on technical influence alone. L6 requires both.

**Practical political skills for L6:**

```
Know who makes decisions:     Who is the "DRI" (Directly Responsible Individual)?
                               Some decision-makers aren't the most senior person in the room.

Build relationships before     When you need something from another team, the answer
you need them:                 depends partly on the relationship.
                               "Can you help with this migration?" is easier to ask
                               if you've been giving that team useful design reviews for 6 months.

Understand what others care    Before proposing a change, understand what your stakeholders
about:                         are optimizing for. Your proposal must address their goals,
                               not just the technical ideal.

Surface disagreements early:   A "yes, but..." in a 1:1 is easier to resolve than
                               a "no" in a design review with 10 people watching.
                               Pre-socialize proposals with skeptics before presenting
                               them to the full group.

Don't fight every battle:      L6 engineers learn to distinguish "this is wrong and I must
                               change it" from "this is not how I'd do it but it's fine."
                               The former is worth political capital; the latter is not.
```

**The "trust tax":**

Every time you push back, disagree, or ask someone to change their approach, you spend a small amount of political capital. Engineers who fight every battle run a trust deficit — people start routing around them. Engineers who never push back accumulate capital but let bad decisions happen.

The skill is calibrating: spend capital on the things that matter, build capital by being right and reliable, never go negative.

---

## Part 23: The Shadow Staff Engineer — Learning Before the Title

One of the most effective strategies for building toward L6 is to start behaving like a Staff engineer before you are one. This is sometimes called "operating above your level" or "acting at scope."

**Concrete behaviors to adopt now:**

```
Write design docs proactively:
  Don't wait to be asked. If you're building something non-trivial,
  write a design doc. Share it with your team and adjacent teams.
  Get feedback. This practice alone signals L6 readiness.

Take the TL role on ambiguous projects:
  When a project has unclear ownership, volunteer to own it.
  Ambiguous projects are L6-scope opportunities waiting for someone to claim them.

Bring problems, not just solutions:
  L5: "Here's the solution I built."
  L6: "I identified this problem (with data), here are three options, here's my recommendation."
  The second form demonstrates the full cycle — problem identification, option space, 
  reasoning — that L6 requires.

Seek the uncomfortable conversations:
  A bug in the project plan. A design decision you think is wrong.
  An org structure that's creating friction.
  L6 engineers address these directly, with data, respectfully.
  L5 engineers note them in their head and move on.

Connect technical work to business outcomes:
  L5: "I reduced the P99 latency by 40%."
  L6: "I reduced the P99 latency by 40%, which directly affected our renewal rate.
       Our customer success team identified latency as the #1 complaint in churn
       interviews last quarter."
  This connection — technical work → business metric — is the language of L6.
```

---

## Part 24: The Skip-Level Relationship

In large companies, your skip-level manager (your manager's manager) is often a key figure in your promotion. They are typically in the calibration room. They have influence over promotion headcount. Their opinion matters.

**Building the right relationship with your skip:**

```
DO:
  - Request a skip-level 1:1 once a quarter (or accept if offered)
  - Come with prepared topics: things you're working on, blockers, feedback requests
  - Ask for their perspective on org-level technical direction
  - Make your impact visible to them organically (through projects they care about)

DON'T:
  - Complain about your manager to your skip
  - Ask about your promotion timeline directly (that's your manager's job)
  - Overclaim — skips have good calibration and will see through inflated impact claims
  - Use the skip to route around your manager (this damages trust with your manager)
```

**What to say in a skip-level 1:1:**

```
"I wanted to update you on [Project X] — I know you care about [business outcome Y]
 and I think this directly addresses it. We've seen [metric] improve by [Z%] since launch.
 The unexpected challenge was [thing] — here's how we addressed it."

"I'd love your perspective on [technical decision]. We're evaluating [option A] vs [option B].
 The trade-offs I see are [X] and [Y]. Does that match your view of where we're headed?"
```

This positions you as someone who understands the business context and thinks at the org level — exactly the L6 signal your skip needs to advocate for you in calibration.

---

## Part 25: The Technical Debt Decision — Career Signal

How an engineer handles technical debt in their area is a strong calibration signal:

**L4/L5 approach:**
- "There's a lot of technical debt here. Someone should fix it."
- Documents it in a ticket. Waits for it to be prioritized.
- Complains about it in retros.

**L6 approach:**
- "This technical debt is costing us [X hours of developer time / Y production incidents] per month."
- Builds a business case: "Paying it down would save [Z] per quarter."
- Gets buy-in from manager and product to allocate 20% of sprint capacity to debt reduction.
- Executes and measures the impact.
- Documents the outcome so the next time someone has debt, there's a model to follow.

The L6 behavior turns "technical debt" from a complaint into a prioritized project with a business case and a measured outcome. This is exactly the kind of work that appears in strong promo packets.

---

## Part 26: The Promotion After a Reorg

Reorgs are common at large tech companies and can dramatically affect your promo timeline. Key dynamics:

**How reorgs affect promotions:**

```
New manager: Your new manager doesn't know your history.
             Your promo packet must be legible to someone who doesn't know you.
             Spend the first 30 days getting your new manager up to speed on your impact.

Headcount reset: Reorgs often reset the L6 headcount allocation.
                 This can accelerate or delay you depending on the new org's headcount.

Different rubric: A new org may apply the rubric differently.
                  What counted as L6 scope in your old org may not in the new one.
                  Ask your new manager explicitly: "How does this org calibrate L6?"

New sponsorship needed: If your sponsor moved away in the reorg, you need to rebuild.
                        Your new manager needs 6 months of direct evidence before they
                        can advocate for you in calibration.
```

**If you reorg 3 months before a promo cycle:**

This is often a promo delay of one cycle. You can try to accelerate it by:
1. Providing your new manager with a structured "here's what I've done and why it's L6" document early
2. Getting your old manager to provide a reference to your new manager
3. Getting cross-team feedback before the cycle closes (people who know your work independently)

---

## Part 27: The Two-Year L5 Warning Sign

The "two-year L5 warning" is a well-known pattern: engineers who have been L5 for more than two years without promotion should actively evaluate whether the environment is creating the right conditions for their growth.

Two years at L5 with strong performance reviews and no promotion could mean:

```
1. The bar keeps moving:      Each cycle, the bar for L6 moves.
                               This happens at companies under growth pressure
                               where headcount for L6 is constrained.

2. Headcount is frozen:       External economic conditions (layoffs, hiring freezes)
                               reduce promotion budgets. This is external circumstance,
                               not a performance signal.

3. Manager is passive:        Your manager isn't actively advocating for you.
                               They may not be invested in your promotion or may not
                               have the influence to drive it through.

4. Your scope is genuinely    You might be in a role where L6-scope opportunities
   constrained:               don't naturally arise. Some teams' work is inherently
                               team-scoped. You may need to change teams to change scope.

5. The promotion is real      Sometimes the feedback is genuine: you need 6 more months
   but deferred:              of cross-team evidence. This is actionable — do the work.
```

How to diagnose which case you're in:

```
Ask your manager:
  "What specific evidence would make you feel comfortable strongly supporting
   my L6 promotion in the next cycle? Can you be concrete?"

If they can answer clearly → case 5. Do the work.
If they give vague or inconsistent answers → likely cases 1, 2, 3, or 4.
   Consider a structured conversation: "I've been L5 for 2 years. I want to
   understand whether L6 is achievable here in the next 12 months. What would
   make you say yes with confidence?"
```

---

## Part 28: Impact Framing by Domain

The SOAR framework is general. Here is how to apply it for common engineering domains:

**Infrastructure / platform engineering:**

```
L5: "I migrated 8 services to Kubernetes."
L6: "I led the org-wide Kubernetes migration for 23 services across 4 teams.
     The primary obstacle was that each team had custom deployment scripts with
     no standard interface. I designed a common deployment abstraction that
     reduced the per-service migration from 3 weeks to 3 days, reducing the
     total migration timeline from 18 months to 4 months. The migration
     eliminated 12 types of deployment-related production incidents and reduced
     our infra cost by 30%."
```

**Backend / API engineering:**

```
L5: "I designed and built the new payment API."
L6: "I identified that our payment API had 4 separate incompatible implementations
     (one per acquisition), causing 60% of our customer-reported bugs.
     I designed a unified payment abstraction, got buy-in from 3 product teams
     and 2 engineering orgs, led the 6-month migration, and reduced payment-related
     bugs by 85%. The abstraction is now the standard for all new payment integrations,
     saving an estimated 2-3 months per new integration."
```

**Data / ML platform:**

```
L5: "I built the feature store for the recommendation system."
L6: "I identified that each ML team was building their own feature computation
     pipelines, duplicating work and creating inconsistencies that affected model
     quality. I designed a shared feature store, got buy-in from 6 ML teams,
     led the implementation, and reduced feature computation redundancy by 80%.
     Model training time for new models dropped from 4 weeks to 1 week for
     teams using the shared store."
```

**Security engineering:**

```
L5: "I implemented MFA for our auth system."
L6: "I identified that our auth system lacked consistent MFA enforcement across
     12 services, creating attack surface that our red team confirmed was
     exploitable. I proposed and drove org-wide MFA enforcement, requiring
     coordination with 4 product teams to update 12 authentication flows.
     Post-rollout, we've seen zero auth bypass incidents vs. 3 in the prior year."
```

The pattern is always: **identify the org-level problem → build the case → drive the cross-team solution → measure the org-level outcome.**

---

## Vocabulary Quick Reference

| Term | One-line definition |
|------|---------------------|
| Promo packet | Formal document submitted to calibration committee for promotion consideration |
| Brag doc | Running log of accomplishments and metrics maintained throughout the year |
| Calibration | Committee of managers who collectively decide promotion outcomes |
| Sponsor | An advocate (usually manager or skip) who argues for your promotion in calibration |
| L6 / Staff | Engineering level where impact scope is team/org direction, not individual execution |
| Cross-team impact | Work that affects engineers and outcomes outside your immediate team |
| Technical direction | Changing what the org builds or how it builds it — not just executing existing plans |
| SOAR | Impact bullet framework: Scope + Obstacle + Action + Result |
| Promo cycle | Semi-annual window when promotions are formally submitted and decided |
| Multiplier | L6 archetype: making other engineers more effective through frameworks, standards, mentorship |
| Headcount constraint | Org-level cap on how many L6 slots exist — can block promotions regardless of performance |
| Staff archetype | One of four Staff engineer work styles: Tech Lead, Architect, Solver, Right Hand |

---

---

## Part 29: The Staff Engineer's Relationship with Product Management

One underappreciated dimension of L6 impact: the relationship with product management. Engineers who can influence product direction (not just implement it) demonstrate a key L6 capability.

**What PM partnership looks like at L5 vs. L6:**

```
L5 ↔ PM:  "Here's the feature spec. What's the technical timeline?"
           Engineer implements, estimates, and flags technical risks.
           PM drives the roadmap. Engineer executes it.

L6 ↔ PM:  "I've been looking at our data and I think we're solving the wrong problem.
           The user retention issue isn't missing features — it's latency.
           Here's the data: users who experience p99 > 3s have 40% lower 30-day retention.
           I think we should pause Feature X for one sprint to address this.
           Can we discuss?"
           Engineer proposes changes to the roadmap based on technical insights.
           PM and engineer jointly own the direction.
```

Getting a PM to change the roadmap based on your technical analysis is an L6 impact story. Write it in your brag doc.

---

## Part 30: The Five Most Common L6 Projects

These types of projects consistently appear in successful L6 promo packets because they naturally have org-wide scope, measurable impact, and require cross-team influence:

**1. Platform / infrastructure standardization**
- Replace N different implementations with 1 shared platform
- Example: "unified logging framework adopted by 8 teams"
- Impact: developer velocity, consistency, reduced incidents

**2. Reliability initiative**
- Reduce a class of production incidents across the org
- Example: "on-call response SLO enforcement across 6 services"
- Impact: incident reduction (count and MTTR), on-call burden reduction

**3. Developer tooling**
- Build something that makes other engineers' lives substantially easier
- Example: "CI/CD pipeline standardization: from 45-minute builds to 8 minutes"
- Impact: developer productivity, measurable in time saved per week

**4. Security / compliance org-wide**
- Drive a security or compliance requirement across the org
- Example: "org-wide MFA enforcement for internal tools"
- Impact: risk reduction, compliance certification, zero incidents post-rollout

**5. Technical debt remediation with business case**
- Identify debt that is costing the org money or reliability
- Example: "legacy monolith extraction to reduce deploy risk"
- Impact: deployment frequency, incident count, developer velocity

The common thread: each project has a before/after metric at org scale, required convincing multiple teams, and left a permanent artifact (the platform, the standard, the runbook) that outlasts your involvement.

---

## Part 31: The Manager's Perspective on L6 Candidates

Understanding how your manager thinks about your promotion case helps you give them the material they need.

Your manager's job at calibration is to tell your story in 60-90 seconds to a room full of people who don't know you. They must answer:

1. What did this person do that was L6 scope?
2. What was the measurable outcome?
3. What would not have happened if this person hadn't driven it?
4. Has their impact been recognized by engineers outside our team?

Give your manager these answers in writing. Before the cycle, ask:

```
"I'd like to help you prepare to advocate for me in calibration.
 Can I share a 1-pager with my top 3 impact examples and the supporting evidence?
 I want to make sure the calibration committee has the full picture."
```

A manager who has your impact 1-pager can advocate for you twice as effectively as a manager who is working from memory. And a manager who hasn't thought about your case at all will be unprepared when the committee asks questions.

---

## Part 32: Closing — The Mindset Shift

The most important thing this chapter can leave you with is a mindset shift.

Most engineers approach promotion reactively: they do their work, they hope their manager notices, and they wait to be told they're ready. This approach works at L3 and L4, where the work is closer to defined tasks. It fails at L5 → L6, where the difference between levels is a difference in what work you choose to do — not how well you execute given work.

**The proactive approach:**

1. **Understand the bar** — read the rubric, ask your manager, look at what recently promoted L6s did
2. **Identify your gaps** — be honest about the dimensions where your evidence is weak
3. **Target the right work** — seek projects with L6 scope, not just L5 scope executed faster
4. **Build evidence continuously** — brag doc, design docs, cross-team feedback, metrics
5. **Create visibility** — tech talks, design reviews, working groups, skip-level relationships
6. **Drive the conversation** — tell your manager your timeline, ask for feedback, ask for stretch assignments
7. **Calibrate the environment** — if the org can't create L6 opportunities for you, find one that can

The engineers who are promoted are not the ones who had the most natural talent. They are the ones who understood the system and worked it deliberately — while also doing excellent technical work.

Both are required. Neither alone is sufficient.

> *"The promotion doesn't come from doing the same work better. It comes from doing different work — at a different scope."*

---

## Final Pre-Interview Checklist

- [ ] Can you articulate the L5 → L6 scope shift in one sentence?
- [ ] Do you have 3 SOAR-formatted impact bullets ready?
- [ ] Is your brag doc up to date with the last 12 months?
- [ ] Have you had the "I want L6 in 18 months" conversation with your manager?
- [ ] Do you know your top 2 gaps and have a plan for each?
- [ ] Can you name 3 engineers from other teams who could speak to your L6 scope?
- [ ] Do you know the promo cycle dates at your company?
- [ ] Do you have a STAR story for "time you influenced without authority"?
- [ ] Do you understand the four Staff archetypes and know which one fits you?
- [ ] Have you read the L6 rubric at your company (or the equivalent)?

---

## Part 33: The L6 Candidate Assessment — What an Interviewer Sees

When you interview for an L6 role externally, the interviewers are explicitly calibrating against the L6 bar. Here is what they're assessing in each interview type:

**System design interview:**
```
L5 signal: "Can design a complex system correctly"
L6 signal: "Drives the problem definition — challenges ambiguous requirements,
            identifies the real constraint, proposes a design that reflects
            engineering trade-offs with business outcomes in mind"
            
L6 differentiator: before designing, the L6 candidate asks:
  "What's the 10-year scale target here?"
  "Are we optimizing for read or write latency? What's the business driver?"
  "Is the hard constraint cost, latency, or correctness? They can't all be equal."
```

**Behavioral interview:**
```
L5 signal: "I led this project and shipped it on time"
L6 signal: "I identified that we were working on the wrong problem,
            built the case for changing direction, got buy-in from
            3 teams who were resistant, and redirected 6 months of
            engineering effort — the new direction resulted in [measurable outcome]"
            
Key questions that reveal L6:
  "Tell me about a time you changed what your org was working on."
  "Tell me about a time you drove a decision you had no authority over."
  "Tell me about a time you pushed back on a decision from above."
```

**Coding interview:**
```
L5 signal: "Clean, correct, efficient solution with tests"
L6 signal: Identical technical execution PLUS:
  - Explicitly names the trade-offs they're accepting
  - Asks clarifying questions about performance requirements before starting
  - Notes what the code doesn't handle and why (production consideration)
  - Connects the solution to the larger system context
  
The L6 candidate codes at the same speed as L5 but provides more context
about WHY their approach is correct for this specific problem.
```

---

## Part 34: Compensation Expectations at L6

Understanding compensation helps you evaluate offers and negotiate effectively. These are approximate ranges as of 2025-2026 for top tech companies (total compensation including salary + bonus + equity):

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│           APPROXIMATE L6 COMPENSATION RANGES (2025-2026)                       │
│           Source: Levels.fyi aggregates — individual offers vary widely        │
├──────────────────────────┬──────────────────────────────────────────────────────┤
│ Company                  │ L6 equivalent total compensation (approximate range) │
├──────────────────────────┼──────────────────────────────────────────────────────┤
│ Google L6 (Staff SWE)    │ $450K – $700K+ (wide range based on RSU refreshes)  │
│ Meta E6                  │ $450K – $750K+ (large equity component)             │
│ Amazon L7 (Senior SDE)   │ $350K – $550K (lower base, significant RSUs)        │
│ Apple ICT5               │ $350K – $550K                                        │
│ Microsoft 65/66          │ $300K – $500K                                        │
│ Stripe L6                │ $350K – $600K                                        │
└──────────────────────────┴──────────────────────────────────────────────────────┘

Notes:
- Location matters dramatically: Bay Area / Seattle / NYC vs. remote
- 4-year RSU vesting means year-1 and year-4 take-home differ significantly
- Refreshes at Google/Meta can add $100K-$300K/year for top performers
- These are "typical" ranges — outliers exist in both directions
```

This context helps when evaluating whether an external L6 offer is competitive, and when negotiating (Chapter 127 covers this in detail).

---

## Part 35: Making the Case for L6 at Your Current Company — Template

Here is a structured 1-pager you can write and share with your manager to help them advocate for you in calibration:

```markdown
# [Your Name] — L6 Promotion Case Summary

## Why Now (H2 [Year] cycle)
I've been operating at L6 scope for [X months] across [Y dimensions].
The evidence is documented below.

## Top 3 Impact Bullets

**1. [Project Name] — [Scope]**
[SOAR bullet: Scope + Obstacle + Action + Result with metrics]
Evidence: [link to design doc, dashboard, postmortem]

**2. [Project Name] — [Scope]**
[SOAR bullet]
Evidence: [link]

**3. [Project Name / Initiative] — [Scope]**
[SOAR bullet]
Evidence: [link]

## Cross-Team Validation
Engineers from other teams who can speak to my L6 scope:
- [Name, Team]: collaborated on [Project X], key feedback: "[quote]"
- [Name, Team]: I reviewed their [design], prevented [outcome]
- [Name, Team]: I led the migration that directly affected their service

## Remaining Gaps (and mitigations)
- [Gap]: [why it's acceptable / what compensates for it]

## Ask
Strong support for L6 promotion in the [H2 Year] calibration cycle.
```

Sharing this document with your manager 4-6 weeks before the cycle achieves two things:
1. Your manager can correct any misframing before calibration (not after)
2. Your manager has a written artifact to reference when presenting your case

---

## Memorable Quotes

> *"Promotions are a lagging indicator. By the time the committee says yes, you should have been operating at the next level for 12 months."*

> *"Your manager is your representative in calibration. If they can't tell your story in 60 seconds, you haven't given them the material."*

> *"The promotion doesn't come from doing the same work better. It comes from doing different work — at a different scope."*

> *"I've never seen someone promoted for working harder. I've seen many people promoted for changing what the team worked on."* — Staff engineer at Google

> *"Writing your brag doc is not self-promotion. It's documentation. The alternative is asking your manager to remember everything you did for 12 months."*

> *"The engineers who wait to feel ready for L6 are the same engineers who were ready 12 months ago."*

---

## Vocabulary Quick Reference

| Term | One-line definition |
|------|---------------------|
| Promo packet | Formal document submitted to calibration committee for promotion consideration |
| Brag doc | Running log of accomplishments and metrics maintained throughout the year |
| Calibration | Committee of managers who collectively decide promotion outcomes |
| Sponsor | An advocate (usually manager or skip) who argues for your promotion in calibration |
| L6 / Staff | Engineering level where impact scope is team/org direction, not individual execution |
| Cross-team impact | Work that affects engineers and outcomes outside your immediate team |
| Technical direction | Changing what the org builds or how it builds it — not just executing existing plans |
| SOAR | Impact bullet framework: Scope + Obstacle + Action + Result |
| Promo cycle | Semi-annual window when promotions are formally submitted and decided |
| Multiplier | L6 archetype: making other engineers more effective through frameworks, standards, mentorship |
| Headcount constraint | Org-level cap on how many L6 slots exist — can block promotions regardless of performance |
| Staff archetype | One of four Staff engineer work styles: Tech Lead, Architect, Solver, Right Hand |
| Skip-level | Your manager's manager — key figure in calibration and promotion headcount decisions |
| Pre-calibration | Informal manager conversations before the official calibration meeting — often determines outcome |
| L6 equivalent | Google L6 ≈ Meta E6 ≈ Amazon L7 ≈ Apple ICT5 ≈ Microsoft 65/66 |

---

## The One-Sentence Summary

> *"Promotion to L6 = impact at L6 scope (changing direction, not just executing) + a promo packet that shows outcomes not activities + a sponsor who advocates for you in calibration + timing aligned to the promotion cycle — the most common failure mode is doing L6 work without making it visible or framing it at the right level of impact."*

---

## Company-Specific "Do This First" Advice

**If you're at Google targeting L6:**
Start with the design docs. Every major technical decision you drive should be in a go/ link. Design docs are the primary currency of evidence in Google calibrations. Start writing them for everything, even internal tooling. Also: get a "Strongly Exceeds" (SE) rating before your promo cycle — most L6 promotions require at least one SE in the prior period.

**If you're at Meta targeting E6:**
Lead with impact metrics. Your strongest bullets will have user-facing or revenue metrics. "Reduced latency by 40%" is good. "Reduced latency by 40%, which increased conversion by 2% across 50M users = $X revenue" is strong. Meta's calibration language is impact-per-dollar and impact-per-engineer.

**If you're at Amazon targeting L7:**
Frame every impact bullet using Leadership Principles (LPs). Your promo packet should be legible to someone who doesn't know your technical domain but knows the LPs cold. "Delivered Results" + "Ownership" + "Invent and Simplify" are the three LPs that appear most often in successful L7 packets.

**If you're interviewing externally:**
Do a mock design interview with an engineer at the target company's level or above. External interviews are harder to prepare for without company-specific context — find someone who can tell you the bar, not just the rubric.

---

### Brainstorming Questions — Part 1: Staff Level Impact

1. What's the difference between "I wrote the code for feature X" and "I led the design of feature X"? Why does the distinction matter for promotions?
2. You're an L4 who wants to operate at L5. Name one thing you could do this week that would be clearly L5 behavior, not L4. What makes it different?
3. "Scope" is one of the hardest dimensions of Staff impact to demonstrate. How do you increase your scope without a title change first?

### Brainstorming Questions — Part 2: The Promo Packet

1. If your promo packet has 3 strong bullets and 3 weak bullets, is that good or bad? What's the calibration committee looking for?
2. The SOAR format (Situation, Outcome, Action, Result) is mentioned. What's the most common mistake engineers make in each of the four parts?
3. Your strongest impact is on a project that shipped 18 months ago. Is it still relevant? How do you frame old impact vs. recent impact?

### Brainstorming Questions — Part 3: Sponsorship

1. What's the difference between a mentor and a sponsor? Why do engineers often conflate them and end up with the wrong support?
2. You want a specific Staff engineer as your sponsor. How do you ask without it being awkward? What do you offer in return?
3. Can you get promoted to Staff without a sponsor? What's the success rate? What fills the gap if you don't have one?

### Brainstorming Questions — Parts 4–6: Calibration, Evidence, External Interviews

1. Calibration committees compare you against peers. Who are the other candidates being considered? How do you find out, and how does it change your strategy?
2. "12 months out" strategy: if you knew your promo decision was exactly 12 months away, what would you do differently starting today?
3. When is interviewing externally the right career move vs. a distraction? What are the signals that tell you it's time?

---

## Exercises

**Exercise 1 — Impact audit.** Write the 5 strongest impact bullets from the last 12 months of your work. Use SOAR format for each. Show them to a trusted peer. Ask: would these bullets be convincing to someone who doesn't know you? What's missing?

**Exercise 2 — Scope analysis.** Map your current scope: what systems you own, what teams you influence, what decisions you make. Now map what Staff-level scope looks like at your company. What's the gap? What's one specific way to close it this quarter?

**Exercise 3 — Promo packet draft.** Write a draft promotion packet for yourself right now — even if you're not up for review. Include: strongest impact bullets, cross-team influence examples, evidence of technical leadership. What's the weakest section? That's your focus area.

**Exercise 4 — Sponsor identification.** List 3 people at Staff level or above who know your work well enough to advocate for you. For each: how strong is their advocacy, how often do they speak up in calibration contexts, and what would strengthen the relationship?

**Exercise 5 — Calibration simulation.** Ask your manager: "If calibration happened today, how would I compare to other L5 candidates?" The answer (if honest) is the most valuable feedback you can get. Write down what you'd do differently based on the answer.

**Exercise 6 — External interview benchmark.** If you're curious about the external bar: do one mock interview with an engineer at a FAANG company in your target level. Not to get an offer — to calibrate whether your current trajectory is on track.

---

## Homework

**This week:**
1. Start (or update) your brag doc — add everything from the last 6 months you can remember
2. Write your 3 strongest impact bullets in SOAR format — share them with one trusted peer for feedback
3. Schedule the "I want L6 in 18 months" conversation with your manager

**This month:**
4. Identify your top 2 L6 gaps using the gap analysis framework (Part 12)
5. Map your cross-team network — name 3 engineers outside your team who can speak to your work
6. Find one project in the next quarter with genuine org-wide scope to volunteer for

**Before your next promo cycle:**
7. Write the 1-pager promo summary (Part 35 template) and share with your manager
8. Collect written feedback from 3+ engineers outside your team
9. Verify your timing — when is the next cycle? What is the packet due date? Work backward.

---

## Final Note: The Promotion Is Not the Goal

This chapter is about getting promoted. But it's worth stepping back and asking: to what end?

The promotion is a lagging indicator. It confirms that you've been operating at the next level. It changes your compensation, your visibility, and your opportunities. Those are real and important things.

But the actual goal — the thing worth caring about — is operating at L6 scope. Driving technical direction. Making other engineers more effective. Influencing the systems and the organization in ways that outlast your individual contributions.

The promotion follows naturally from doing that work well and making it visible. Engineers who focus only on the promotion mechanics, without focusing on the actual substance of L6 impact, tend to be disappointed: either they get the title but don't feel the fulfillment they expected, or the committee sees through the mechanics and defers them anyway.

Do the real work. Build real impact. Make it visible. The promotion will come.

---

*Pairs with Chapter 125 (Interview Execution Meta-Skills) for the interview-day application, Chapter 126 (Behavioral/Leadership Interview) for the STAR story preparation, Chapter 127 (Offer Negotiation) for what happens after you get the offer, and Chapter 118 (Reading Unfamiliar Code) for the skills you need when you join a new team at the next level.*

`Chapter 119 | Section 7: Engineering Excellence | Promotion & Career Navigation`




---

## Index of Parts

| Part | Title |
|------|-------|
| 1 | What Staff Level Impact Actually Means |
| 2 | The Promo Packet — Structure and Content |
| 3 | Sponsorship — The Hidden Requirement |
| 4 | The Calibration Process |
| 5 | Building the Evidence (12 Months Out) |
| 6 | When to Interview Externally |
| 7 | Google vs. Meta vs. Amazon vs. Microsoft |
| 8 | After L6 — L7 and Principal |
| 9 | The Brag Doc — Full Template |
| 10 | Common Promotion Anti-Patterns |
| 11 | The Promotion Conversation — Scripts |
| 12 | L5 → L6 Gap Analysis Framework |
| 13 | War Stories |
| 14 | Behavioral Interview Questions |
| 15 | Staff Engineer Archetypes |
| 16 | Pre-Interview Drill |
| 17 | The Google Rubric |
| 18 | Cross-Team Visibility Without Being Annoying |
| 19 | Exercises |
| 20 | Promotion and Engineering Culture |
| 21 | The L6 Multiplier Concept |
| 22 | Organizational Politics |
| 23 | The Shadow Staff Engineer |
| 24 | The Skip-Level Relationship |
| 25 | Technical Debt as a Career Signal |
| 26 | Promotion After a Reorg |
| 27 | The Two-Year L5 Warning |
| 28 | Impact Framing by Domain |
| 29 | The PM Partnership |
| 30 | Five Most Common L6 Projects |
| 31 | The Manager's Perspective |
| 32 | Closing — The Mindset Shift |
| 33 | The L6 Candidate Assessment |
| 34 | Compensation Expectations at L6 |
| 35 | Making the Case — Template |
| 36 | Annual Career Checkup |
