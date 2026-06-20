# Chapter 6b: The Real Work of a Staff Engineer

> What interviews don't test, but your first 6 months on the job will.

---

```
+===========================================================================+
|          CHAPTER 6b: THE REAL WORK OF A STAFF ENGINEER                   |
+===========================================================================+
|                                                                           |
|  CORE INSIGHT: Staff engineers operate on PEOPLE and SYSTEMS              |
|  simultaneously. Interviews test systems. The job tests both.             |
|                                                                           |
|  THE 6 REAL-WORLD SKILLS THIS CHAPTER COVERS:                            |
|                                                                           |
|  1. Incident Command       -- Running a live outage, not just fixing it   |
|  2. Influence Without Auth -- Getting things done across teams you don't  |
|                               manage                                      |
|  3. Running Design Reviews -- Giving feedback that makes engineers grow   |
|  4. Technical Strategy     -- Vision docs, tech debt, business cases      |
|  5. Multiplying Through    -- Mentorship, game days, promotion calibration |
|     People                                                                |
|  6. Operating Under        -- Triage, escalation, measuring in business   |
|     Pressure                  terms                                       |
|                                                                           |
|  WHY THESE ARE NOT IN INTERVIEWS:                                         |
|  A 45-minute interview can test your system design. It cannot test        |
|  whether you can run a 3 AM incident without panicking, or convince       |
|  a skeptical team to adopt your standard, or give feedback that           |
|  makes a junior engineer grow instead of quit.                            |
|  These skills show up in month 1-6 on the job. If you are not            |
|  prepared, the job feels impossible despite the strong interview.         |
|                                                                           |
|  L5 vs L6 ONE-LINER PER SKILL:                                           |
|  +--------------------+-------------------------+----------------------+  |
|  | Skill              | L5 (Senior)             | L6 (Staff)           |  |
|  +--------------------+-------------------------+----------------------+  |
|  | Incident Command   | Fixes the problem       | Runs the room;       |  |
|  |                    |                         | others fix problem   |  |
|  | Influence          | Escalates when blocked  | Finds the champion   |  |
|  |                    |                         | before the blocker   |  |
|  | Design Reviews     | Reviews their own design| Improves others'     |  |
|  |                    |                         | designs at scale     |  |
|  | Tech Strategy      | Writes the tech debt    | Gets the debt funded |  |
|  |                    | ticket                  | with business case   |  |
|  | People Multiply    | Mentors when asked      | Builds teams that    |  |
|  |                    |                         | don't need them      |  |
|  | Under Pressure     | Handles urgent things   | Sequences important  |  |
|  |                    |                         | vs urgent correctly  |  |
|  +--------------------+-------------------------+----------------------+  |
|                                                                           |
|  KEY NUMBERS TO CARRY INTO EVERY SITUATION:                              |
|  - 3 minutes: max time to make the rollback call in a SEV1               |
|  - 15 minutes: stakeholder update cadence during active incident         |
|  - 48 hours: deadline to publish post-mortem after incident resolves     |
|  - 5 levels: influence stack to try before escalating to VP              |
|  - 10x: question to ask in every design review ("what breaks at 10x?")  |
|  - 1 paragraph: maximum length of an escalation memo to leadership       |
|                                                                           |
+===========================================================================+
```

---

## Intern to Staff: Same Problem, Four Levels

**The problem:** Production is down. Payment service is returning 503s. It is 3 AM. You are paged first because you are on call.

Read carefully. The situation is *identical* at all four levels. What changes is everything else.

---

### Intern

```
T+0:00  Paged. Alert says "payment-service: 503 rate > 30%"
T+0:05  Logs into production. Sees lots of red in the logs.
        Thinking: "Restarting usually fixes this."
T+0:08  Runs: kubectl rollout restart deployment/payment-service
T+0:15  Service restarts. 503s drop to 0%. Marks ticket "Resolved."
        Slack message: "Fixed it." Goes back to sleep.
T+6:00  Same 503s return. Different engineer gets paged.
        Root cause: a new deploy at 11 PM introduced an N+1 query
        on the orders table that exhausted the DB connection pool.
        Restart cleared the connections temporarily. Same deploy,
        same code, same problem -- 3 hours later.

Blast radius: ~3 hours of degraded payments + ~3 more hours later
Learning for the org: ZERO. Same bug will hit again from same deploy.
```

**What the intern missed:** Restarting is a band-aid, not a fix. The intern did not ask: *why* did the service fail? They treated the symptom (service down) not the cause (pool exhausted). They also communicated nothing to anyone -- no context for the next engineer, no escalation.

---

### L4 (Mid-level)

```
T+0:00  Paged. Alert says "payment-service: 503 rate > 30%"
T+0:03  Opens Datadog. Sees DB connection pool at 100% (500/500).
        DB CPU also spiked. Last deploy: 11 PM (3 hours ago).
T+0:08  Checks git log. New query in payments/orders.py.
        Recognizes N+1 pattern. "This is it."
T+0:12  Runs rollback: kubectl set image deployment/payment-service
        payment-service=payment-service:v2.3.1-prev
T+0:20  Service recovers. 503s gone. Connection pool drops to 45%.
T+0:22  Slack: "Rolled back v2.3.2. N+1 query on orders table was
        exhausting the connection pool. Should be stable now."
T+0:25  Goes back to sleep.

Next morning: files a ticket "fix N+1 query in orders endpoint"
4 months later: different engineer writes a similar N+1 query
in a different endpoint. Same incident. 20 minutes of downtime.

Blast radius: ~20 minutes this incident
Learning: this particular bug fixed. But the CLASS of bug is open.
```

**What L4 missed:** Great debugging. Good rollback call. But no post-mortem, no systemic fix, no alert on "connection pool > 80%." The ticket gets deprioritized and closed. Four months later a different person makes the exact same class of mistake and the org has no defense against it.

---

### L5 (Senior)

```
T+0:00  Paged. Alert says "payment-service: 503 rate > 30%"
T+0:02  Declares SEV2 in the #incidents channel.
        Slack: "Payment service 503s. Taking IC. Anyone on DB team
        available? Need eyes on connection pool."
T+0:05  Assigns roles:
        - Self: Incident Commander
        - DB oncall: investigate root cause
        - Engineer A: draft stakeholder update
T+0:09  DB oncall confirms: connection pool at 100%, N+1 query
        from 11 PM deploy.
T+0:11  Makes rollback call. "Rolling back v2.3.2 to v2.3.1."
T+0:20  Rollback complete. 503s gone.
T+0:22  Stakeholder update sent:
        "Payment service incident resolved. Root cause: N+1 query
        in v2.3.2 deploy exhausted DB connection pool. Rolled back
        to v2.3.1. All payments processing normally. Post-mortem
        to follow."
T+0:25  Goes back to sleep.

Next morning: writes post-mortem.
- Timeline: clear, accurate
- Root cause: "N+1 query on orders table. Engineer X introduced
  the pattern. Should have been caught in code review."
- Action items:
  - Add DB connection pool alert at 80% threshold (done in 3 days)
  - Engineer X to fix the N+1 query (done next sprint)

2 months later: different N+1 from a different engineer.
The alert fires early this time (80% threshold). On-call catches
it before users are affected. Rolls back.
But the PATTERN still reaches production. Post-mortem action item
was monitoring, not prevention.

Blast radius: ~20 min per incident
Learning: monitoring improved. Prevention: none.
```

**What L5 missed:** Great incident command. Clear communication. Good post-mortem. But the action items are defensive (monitoring) not preventive (tooling). The post-mortem also names the individual engineer -- "Engineer X introduced the pattern" -- which is blame-adjacent. The real question is: *why can an N+1 query reach production undetected?* L5 answered "it should have been caught in code review." That is a people answer. The systemic answer is: "We have no automated tooling to detect N+1 queries before they deploy."

---

### L6 (Staff)

```
T+0:00  Paged. Alert says "payment-service: 503 rate > 30%"
T+0:01  FIRST CHECK: when was the last deploy?
        11 PM -- 3 hours ago. DB CPU spike matches deploy time.
T+0:02  Declares SEV2. Assigns roles immediately.
        Does NOT start debugging personally. Delegates it.
T+0:03  Rollback decision: "Deploy was 3 hours ago. DB metrics
        degraded immediately after. I am calling rollback now.
        We do not need root cause to make this call. Users first."
T+0:05  VP Engineering update (plain English, no jargon):
        "Payment service is degraded. ~$180K revenue at risk per
        hour at current traffic. Rollback in progress. Expected
        resolution: 15-20 minutes. I will update you when stable."
T+0:20  Rollback complete. Recovery confirmed.
T+0:22  VP update: "Resolved. Payments processing normally.
        Post-mortem within 48 hours."

Next day: post-mortem published.
Key section: ROOT CAUSE ANALYSIS

"This is the third N+1 query incident in 8 months:
- March: orders endpoint (engineer A)
- July: search endpoint (engineer B)
- Today: payments endpoint (engineer C)

Pattern: Three different engineers, three different endpoints,
same class of mistake. This is not a people problem.
It is a tooling gap. Our CI pipeline runs unit tests but
has no automated query analysis step. An N+1 query that
processes 400 rows in a test environment will process
400,000 rows in production -- invisibly, until it breaks.

ACTION ITEMS (systemic, not individual):
+---------------------------------------+-------+----------+
| Action                                | Owner | Due      |
+---------------------------------------+-------+----------+
| Add sqlfluff N+1 detection to CI      | Infra | 2 weeks  |
| Add DB connection pool alert at 80%   | SRE   | 3 days   |
| Add query explain-plan review to TDD  | Staff | 1 week   |
| Runbook for pool exhaustion mitigation| Oncal | 3 days   |
+---------------------------------------+-------+----------+

WHAT GOOD LOOKS LIKE: CI detects the pattern before merge.
Engineer submits PR. CI runs query analysis. PR blocked with:
'Detected potential N+1: orders query inside user loop.
Consider joining or batching.'"

30 days later: CI ships with N+1 detection.
Next 6 months: CI catches 4 similar patterns from 4 engineers.
NONE reach production.

Blast radius: ~20 min this incident
Learning: entire class of bug eliminated from production.
```

**The L6 difference:** Same scenario. Same rollback time. But L6 asked: *why can this class of problem reach production three times in 8 months from three different engineers?* The answer is tooling. The fix is automation. The result is that the next N engineer who makes this mistake gets caught by a machine, not by a production incident.

**L6 also communicated differently:** The VP update was in dollars, not decibels. "$180K per hour at risk" is what a VP needs to make decisions. "N+1 query exhausted the connection pool" is what an SRE needs. Know your audience.

---

## Part 1: Incident Command -- Running the Room

### The Analogy That Changes How You Think About This

Imagine an emergency room at 3 AM. A car crash victim arrives. There are 5 doctors available.

The wrong way: all 5 doctors crowd around the patient, each doing what they think is most urgent, bumping into each other, nobody tracking what the others are doing. The patient might survive. Or two doctors might both give blood thinners without knowing the other did it.

The right way: one doctor becomes the Attending (incident commander). They do NOT perform surgery. They call the shots:
- "You: airway and breathing."
- "You: IV line and blood pressure."
- "You: call the OR and get it ready."
- "I need a status update from all of you every 3 minutes."

The Attending is not the best surgeon in the room. They are the person who ensures the best surgeons can work without stepping on each other.

A production incident is the ER. The Incident Commander (IC) is the Attending. And the hardest thing for a senior engineer to learn is: **when you become IC, you stop touching the keyboard.** Your job is coordination, not fixing.

---

### Why This Is Hard for Great Engineers

Great engineers become great by being the best fixer in the room. That instinct gets them promoted to L5. At L6, the same instinct becomes a liability during incidents.

**The scenario:** You are the best person on the team at debugging DB issues. A DB-related incident fires at 3 AM. You become IC and assign the DB investigation to someone less experienced than you. They are 30% slower than you would be.

The wrong move: take over the investigation. "I'll just look at this real quick." Now you are both IC and investigator. The stakeholder update is 20 minutes late. No one is tracking the timeline. Two other engineers who joined to help are confused about what to do.

The right move: let them investigate at 70% of your speed while you coordinate. You gain: stakeholder updates sent on time, other engineers have clear roles, timeline is being recorded, mitigation decision stays centralized. You lose: maybe 5 minutes of investigation speed. Net result: better for the org, harder for your ego.

---

### Severity Levels and Who Gets Woken Up

```
  +-------+-------------------+------------------------+------------------+
  | SEV   | Definition        | Who Gets Paged         | Update Cadence   |
  +-------+-------------------+------------------------+------------------+
  | SEV1  | Core product is   | IC, VP Eng, VP Product,| Every 10 minutes |
  |       | down for ALL users| on-call rotation,      | to executives    |
  |       |                   | CTO if > 30 min        |                  |
  +-------+-------------------+------------------------+------------------+
  | SEV2  | Major feature     | IC, team lead,         | Every 15-30 min  |
  |       | down OR large %   | on-call, DB/infra      | to stakeholders  |
  |       | of users affected | if needed              |                  |
  +-------+-------------------+------------------------+------------------+
  | SEV3  | Minor degradation,| On-call only           | End-of-day       |
  |       | workaround exists,|                        | summary          |
  |       | < 5% of users     |                        |                  |
  +-------+-------------------+------------------------+------------------+

  REAL EXAMPLES:
  SEV1: Stripe payment processing returns 500 for all merchants
  SEV2: GitHub PR merge button broken for 40% of users
  SEV3: GitHub PR label filter returns wrong results for some repos

  UPGRADE PATH:
  SEV2 --> SEV1 IF:
  - Duration > 30 minutes with no clear mitigation path
  - Revenue impact > $X/hour (define your company's threshold)
  - More users becoming affected (expanding blast radius)
  - Regulatory/compliance data at risk
```

---

### The Rollback Decision: Make It in 3 Minutes

The single most important decision in most incidents is: roll back or investigate?

Most engineers delay this decision because they want certainty. They want to know the root cause before acting. This is backwards. The cost of investigation time is measured in user-facing downtime. The cost of a rollback is almost always reversible.

```
  THE 3-MINUTE ROLLBACK RULE:

  ROLL BACK if ALL of these are true:
  +-------------------------------------------+----------+
  | Condition                                  | Check?   |
  +-------------------------------------------+----------+
  | A deploy happened in the last 4 hours      | YES/NO   |
  | Metrics degraded AFTER the deploy, not     | YES/NO   |
  | before                                     |          |
  | Rollback itself is safe (no schema         | YES/NO   |
  | migration, no data written in new format)  |          |
  +-------------------------------------------+----------+
  If all YES: roll back immediately. Root cause later.

  DO NOT ROLL BACK if any of these are true:
  - No recent deploy (could be infra change, traffic spike, etc.)
  - Metrics were already degraded before the deploy
  - Rollback requires a database schema migration downgrade
  - New data format was written that old code cannot read

  WHEN YOU CANNOT ROLL BACK: mitigate differently.
  - Route traffic to a different region
  - Turn off the feature flag
  - Shed load (return 429 to lower-priority users)
  - Increase resource limits (connection pool, memory limit)
```

**Why the time limit matters:** In a real incident, you will feel pressure to understand the problem before acting. Engineers do not like acting without understanding. The IC's job is to override that instinct when users are actively affected. 3 minutes is the discipline. If you cannot decide in 3 minutes, default to rollback (if safe) or default to shedding load (if not safe to rollback).

---

### The Stakeholder Update: Plain English, Every Time

The most common failure in incident communication: technical jargon sent to non-technical stakeholders.

**Bad update (real pattern, made up company):**
```
  T+15min update:
  "We are investigating an anomalous increase in HTTP 503
   responses originating from the payment-service pod cluster.
   Initial analysis suggests potential connection pool
   exhaustion related to the v2.3.2 deployment artifact.
   Rollback is in progress. ETA indeterminate."
```

A VP reads this and thinks: "I have no idea what is happening. Are we losing money? How long until it's fixed? Should I wake up the CEO?"

**Good update (same situation):**
```
  T+15min update -- SEV2 -- Payment Service

  WHAT IS HAPPENING:
  Payment processing is failing for ~40% of checkout attempts.
  This started at 3:05 AM, 15 minutes ago.

  IMPACT RIGHT NOW:
  Estimated $180,000 per hour in failed transactions at
  current traffic levels. Browse, search, and account
  management are NOT affected.

  WHAT WE ARE DOING:
  Rolling back a code change from 11 PM. This is expected
  to resolve the issue. ETA: payments fully restored in
  10-15 minutes.

  NEXT UPDATE: 3:30 AM, or sooner if status changes.

  -- Ranjeet, Incident Commander
```

The VP now knows: the dollar figure, the scope of impact, what is being done, and when they will hear next. They can make decisions. They can answer questions from the CEO without calling you.

**The formula:** WHAT IS HAPPENING + IMPACT IN NUMBERS + WHAT WE ARE DOING + NEXT UPDATE TIME.

---

### The Blameless Post-Mortem: A Deeper Look

"Blameless" is often misunderstood. It does NOT mean:
- No accountability
- Everyone is equally responsible
- The incident was nobody's fault
- We cannot identify what went wrong

It means: **the system is accountable, not the individual.** This is not a moral position. It is an engineering position, grounded in a practical observation:

Any system where one person making one mistake causes a major incident is a fragile system. The fix is not to hire perfect people. The fix is to build systems that tolerate imperfect people -- because all people are imperfect.

**Example: the blame-adjacent version**

```
  ROOT CAUSE:
  "Engineer X introduced an N+1 query that exhausted the
   database connection pool."

  ACTION ITEM:
  "Engineer X to be more careful when writing database queries."

  WHAT HAPPENS NEXT:
  Engineer X feels bad. Everyone else feels slightly superior.
  Nobody changes their behavior because they believe they
  wouldn't make that mistake. 4 months later, Engineer Y
  makes the same class of mistake.
```

**Example: the blameless + systemic version**

```
  ROOT CAUSE:
  "The CI pipeline has no automated query analysis. An N+1
   query that executes once per test row will execute once
   per 400,000 production rows -- and this difference is
   invisible to the author writing the code.

   This incident is the third N+1 query in 8 months from
   three different engineers. This is not three people making
   the same mistake. This is one systemic gap being encountered
   repeatedly."

  ACTION ITEMS (fix the SYSTEM):
  - Add automated N+1 detection to CI (catches all engineers)
  - Add DB connection pool alerting at 80% (catches it earlier)
  - Update code review checklist to include query analysis
  - Write runbook for "pool exhaustion" scenario

  WHAT HAPPENS NEXT:
  The next engineer who writes an N+1 query gets caught by CI,
  not by production. Their PR is blocked with a clear message.
  They learn. The incident never happens. The pattern is gone.
```

**The blameless test:** After writing your action items, ask: "If a different engineer made this mistake tomorrow, would these action items prevent it?" If the answer is no (because the action item is "be more careful"), the post-mortem is not done.

---

### Real Production Incident 1: Google BGP Leak (2012)

**What happened:** A Pakistani ISP (Pakistan Telecom, AS17557) accidentally announced that they were the best path to Google's IP address space. This announcement propagated across Tier-1 internet providers. For about 90 minutes, internet traffic meant for Google was being routed to Pakistan, where it was dropped.

**Why this is interesting for IC skill:** The Google network team could not "fix" the routing tables of every ISP on the internet. They had to *coordinate* -- call the right people at Tier-1 providers and get them to filter the announcement.

```
  WHAT BGP HIJACKING LOOKS LIKE:

  NORMAL:
  User in USA --> ISP --> Internet routing --> Google (AS15169)

  DURING HIJACK:
  User in USA --> ISP --> "Pakistan says it is Google" -->
  Traffic routed to Pakistan AS17557 --> Dropped (no Google there)

  THE FIX (what Google IC coordinated):
  Google IC calls AT&T, Level3, Telia (Tier-1 providers):
  "We are seeing our prefix space announced by AS17557.
   Please filter routes from AS17557 claiming 8.8.8.0/24
   and related Google prefixes. This is not legitimate."
  Tier-1 providers update BGP filters.
  Traffic returns to normal routes.
```

**IC lesson:** The IC's highest-leverage action was not touching the routing tables (they couldn't). It was knowing which 3 phone calls to make, having the contact numbers, and communicating clearly enough that ISP engineers on the other end could act in minutes.

**Staff lesson:** Build your contact list before the incident. Know who to call at AWS, at your CDN provider, at your DNS provider. The call you make at 3 AM should not be the first time you introduce yourself to that person.

---

### Real Production Incident 2: Cloudflare Outage (July 2022)

**What happened:** Cloudflare deployed a change to their backbone network that inadvertently took down 19 of their 21 data centers. About 50% of all internet traffic that passes through Cloudflare was affected for ~1 hour.

**The IC challenge:** The engineers who could fix the problem were located in offices across multiple time zones. The deploy system itself was partially broken. Standard rollback procedures could not be followed because the change had affected the network the rollback tools needed to communicate over.

```
  THE CASCADING FAILURE:

  Change deployed to backbone network
          |
          v
  Backbone connectivity degraded
          |
          v
  Deploy/rollback tools unreachable (they use the backbone)
          |
          v
  Manual fixes required, one datacenter at a time
  (instead of automated rollback)
          |
          v
  ~1 hour to restore all 19 datacenters sequentially

  WHAT WOULD HAVE HELPED:
  - Out-of-band rollback mechanism (separate network)
  - Deploy guard that tests a single datacenter before rolling
    out to 19 simultaneously
  - Runbook for "deploy system is also affected" scenario
```

**Post-mortem action items (actual Cloudflare post-mortem):**
1. Convert backbone to use a new routing protocol in stages, not globally
2. Add a test bed for network changes that is isolated from production
3. Add automated rollback that does not require production network access

**Staff lesson:** Your rollback mechanism is only useful if it works when things are broken. Test your rollback in a degraded-network game day, not just in a healthy-network test.

---

### Brainstorming Questions -- Part 1: Incident Command

These questions test whether you understand the WHY behind incident practices, not just the rules.

**Q1.** You are IC. Your best DB engineer says "I need 2 more hours to confirm the root cause before we roll back." Users have been down for 45 minutes. What do you say and do?

*Think about: whose job is the rollback decision? What is the cost of 2 more hours of investigation vs 15 minutes of recovery?*

**Q2.** A post-mortem lists this action item: "The on-call engineer should have investigated logs before attempting a restart." Why is this a bad action item? Rewrite it as a systemic action item.

**Q3.** You receive two pages simultaneously: the payment API is returning 503s AND the authentication service is returning 200s with wrong session data. You have 4 engineers available. How do you allocate them? What determines the severity of each?

**Q4.** An incident was caused by a configuration change, not a code deploy. How does this change your rollback decision? What information do you need first?

**Q5.** Your monitoring system alerts 40 minutes *after* users started seeing errors. Write two action items: one for the alerting gap and one for how to detect user-visible impact faster than your monitoring system.

**Q6.** During a SEV1 incident, a VP asks you in Slack: "Is customer data at risk?" You do not know yet. What do you say? (There is a right answer and a wrong answer here.)

*The wrong answer: silence while you investigate. The right answer: "Investigating now. No indication of data risk at this time. Will update in 10 minutes."*

**Q7.** It is 48 hours after an incident. Your team wants to move on and ship the feature that was reverted. The post-mortem is not done. The bug fix has been code-reviewed and is ready to merge. What do you do?

**Q8.** A junior engineer on your team was the one who wrote the buggy code. They feel terrible. How do you handle this in the post-mortem review meeting?

---

## Part 2: Influence Without Authority

### The Analogy

You are an architect hired to design a new city neighborhood. You draw the plans. You know exactly where the roads should go, where the parks should be, where the mixed-use buildings belong.

But you own none of the land. You do not employ the construction crews. You cannot sign the contracts. Every single person who needs to do something to make your vision real is working for someone else, with their own boss, their own priorities, and their own definition of success.

Do you put your blueprints in a drawer and wait? Do you storm into meetings and demand compliance? Neither works.

What works: understanding that each stakeholder has a reason to say yes or no, and that your job is to make it easier for them to say yes than to say no.

This is influence without authority. It is the core job of a staff engineer.

---

### Why L4 and L5 Engineers Struggle With This

L4 engineers get things done by being individually productive. Their team lead runs interference with other teams. When blocked by another team, L4 engineers escalate to their manager: "Team B is blocking me."

L5 engineers are technically excellent and can architect systems that span teams. But when blocked, their instinct is either to escalate to VP ("this needs to be mandated") or to do the work themselves ("I'll just build it in my team and they can use it if they want"). Both approaches fail at scale.

L6 engineers treat cross-team alignment as a *design problem* -- solvable with the right inputs and the right sequence of moves. They almost never need to escalate to VP because they never let a situation get to the point where escalation is the only option.

---

### The 5 Levels of Influence

Use these in order. Start at Level 1 every single time, even if you are confident the other team is wrong. Skipping levels is expensive.

```
  +-----------------------------------------------------------+
  | Level 5: EXECUTIVE MANDATE                                |
  | "I need VP to mandate this across the org."               |
  | When: org-wide systemic blocker, exhausted all below,     |
  |        6+ months of timeline at stake, or safety/security |
  | Cost: HIGH political capital, damages relationship,       |
  |       creates resentment, the other team now has a        |
  |       legitimate grievance                                |
  +-----------------------------------------------------------+
          ^ Only go here if Level 4 fails
  +-----------------------------------------------------------+
  | Level 4: MAKE IT TRIVIALLY EASY TO SAY YES               |
  | Do most of the work FOR the other team.                   |
  | Write the adapter. Write the migration script.            |
  | Write the PR. Write the runbook.                          |
  | "All you need to do is review and merge this PR."         |
  | Cost: your time. Worth it if the alternative is           |
  |        months of delay.                                   |
  +-----------------------------------------------------------+
          ^ Only go here if Level 3 fails
  +-----------------------------------------------------------+
  | Level 3: DATA + COST OF INACTION                          |
  | Make the cost of NOT adopting visible in concrete terms.  |
  | "Every quarter we delay costs $X in incidents."           |
  | "We spend Y engineer-hours per month on toil this fixes." |
  | This only works if the data is real and compelling.       |
  +-----------------------------------------------------------+
          ^ Only go here if Level 2 fails
  +-----------------------------------------------------------+
  | Level 2: FIND AND ENABLE THE CHAMPION                     |
  | Somewhere on their team, one person already agrees        |
  | with you. Find them. Share your data with them.           |
  | Let them carry the message internally.                    |
  | "I talked to Sarah on the payments team -- she gets it."  |
  | People trust their teammates more than they trust you.    |
  +-----------------------------------------------------------+
          ^ Only go here if Level 1 is not enough alone
  +-----------------------------------------------------------+
  | Level 1: UNDERSTAND THEIR INCENTIVES (START HERE ALWAYS)  |
  | What is this team measured on? What is their biggest pain |
  | right now? How does your proposal make THEIR life easier? |
  | Can you frame your ask in terms of their goals?           |
  | "I know you are measured on checkout conversion. This     |
  |  auth change drops your latency by 120ms. Worth a look?"  |
  +-----------------------------------------------------------+
```

**Real example -- Level 1 working alone:**

You need the recommendations team to adopt your new shared logging format. Their team lead says they are too busy.

Level 1 question: what are they measured on? Answer: recommendation relevance (a machine learning metric) and infrastructure cost reduction (a Q4 OKR).

Your reframe: "The new logging format captures the exact signals your ML training pipeline needs for click-through rate features. It also reduces your log storage by 40% because it drops the fields you don't use. I ran the numbers on your current volume -- that's about $8K/month savings. Is that worth a 2-day integration?"

You just solved their ML problem and their Q4 cost OKR simultaneously. They will find the time.

---

### How to Say No at L6 Level

A junior engineer says no by refusing. A senior engineer says no by explaining why. A staff engineer never says no without an alternative.

**The formula:**
```
  "No to [specific request], because [technical or resource reason].
   Yes to [alternative], with [specific constraints], by [specific date].
   Trade-off: [what we gain] / [what we give up].
   If this does not work for you, let's talk about [third option]."
```

**Real scenario (Stripe-style situation):**

Request from PM: "Add Apple Pay support to the checkout flow by end of next sprint (3 weeks)."

Background you know: A major authentication infrastructure migration starts in 4 weeks. Adding Apple Pay now means it will need to be migrated as part of that effort, adding 3 weeks of migration work on top of the 3 weeks of implementation.

**Wrong response:**
```
  "We can't do this right now. We have the auth migration."
```

The PM hears: "Engineering is blocking my roadmap item." They escalate.

**Wrong response #2:**
```
  "Sure, we'll squeeze it in." (you are now overcommitted and
  the auth migration will slip)
```

**Right response:**
```
  "I want to get Apple Pay shipped. Here is the situation:

  If we build it in the next 3 weeks, we will hit the auth
  migration in week 4 and spend 3 additional weeks migrating
  Apple Pay to the new auth system. Total: 6 weeks of eng
  time, two integration tests, higher risk.

  If we wait 6 weeks for the migration to complete, we build
  Apple Pay once on the new foundation. Total: 3 weeks of
  eng time, one integration test, lower risk.

  My recommendation: wait 6 weeks. We save 3 eng weeks and
  reduce incident risk. The timeline from the customer's
  perspective is the same: Apple Pay live in ~9 weeks either
  way. I can put it first in queue after the migration.

  If the 6-week timeline is a hard blocker for a business
  reason I'm not aware of, let me know and we can talk about
  what we deprioritize to fit it in now."
```

The PM now understands the real trade-off. They can make an informed decision. You have not blocked them -- you have given them the information to decide.

---

### The Ownership Gap: The Most Common L6 Opportunity

The most common source of cross-team friction in large engineering orgs is not disagreement about the right solution. It is a *gap* -- something that nobody owns, that sits between two teams, that breaks, and that both teams point at each other over.

```
  TEAM A (owns Service A)       TEAM B (owns Service B)
  +------------------+          +------------------+
  |   Service A      |          |   Service B      |
  |                  |  ???     |                  |
  |                  |--------->|                  |
  +------------------+          +------------------+
                         ^
                         |
              Nobody owns this interface.
              When it breaks:
              Team A: "That is Team B's service."
              Team B: "Team A is calling us wrong."
              Users: "Nothing works."
```

**What L4 engineers do:** File a bug ticket assigned to "Team B" and wait.

**What L5 engineers do:** Escalate to their manager. "Team B needs to fix this."

**What L6 engineers do:** Volunteer to own the gap for 30 days, resolve the immediate incident, then drive the permanent ownership conversation.

"Nobody owns this interface right now. I am going to own it temporarily -- I will file bugs, write the runbook, and coordinate fixes for 30 days while we figure out permanent ownership. At the end of 30 days, I need both team leads to agree on who owns this permanently. Can I get 30 minutes on both your calendars next Thursday?"

This move costs you 30 days of partial attention on a gap that is not technically your problem. It gains you: user impact stopped, org goodwill, credibility as someone who solves problems rather than pointing fingers, and a clear process to establish permanent ownership.

---

### Real Production Incident 3: AWS S3 US-EAST-1 Outage (2017)

**What happened:** An AWS engineer was debugging S3's billing subsystem and ran a command to remove a small number of servers from the subsystem. The command had a documentation error -- the number to remove was much larger than intended. A significant portion of S3's infrastructure in US-EAST-1 was taken offline. Dozens of major services (Slack, Trello, GitHub, etc.) that depended on S3 went down for ~4 hours.

**The influence without authority lesson:** AWS's IC had to coordinate mitigation with engineering teams across many different products simultaneously -- S3, EC2, CloudFront, RDS -- all of which were affected in different ways. None of these teams were under the IC's authority.

The IC's approach (from the public post-mortem):
1. Identified which components needed to be restarted in what order (dependency mapping)
2. Coordinated the restart sequence across teams who did not usually talk to each other
3. Provided clear status to thousands of AWS customers through the service health dashboard

```
  THE DEPENDENCY ORDER PROBLEM:

  You cannot restart S3 subsystem components in random order.
  Some components depend on others being healthy first.

  WRONG ORDER --> cascading failures
  RIGHT ORDER --> sequential recovery

  IC job: figure out the right order across teams,
          communicate it clearly, enforce the sequence.

  This requires influence: the teams being sequenced are not
  under your authority. They need to trust your sequencing
  because it is correct, not because you are their boss.
```

**Staff lesson:** Build the dependency map before the incident. Know which services depend on which other services. When a shared dependency fails, you need to know the restart sequence in advance -- not discover it under pressure at 3 AM.

---

### Brainstorming Questions -- Part 2: Influence Without Authority

**Q1.** A team has been saying "yes" to adopting your API standard in every meeting for 6 weeks. Nothing has shipped. What does this pattern signal? What is your next move, and which level of the influence stack are you at?

**Q2.** You disagree fundamentally with a principal engineer about a core architectural decision. The decision meeting is tomorrow. You are both L6. Who decides, and how? What is your role if the decision goes against your recommendation?

**Q3.** Two teams both claim ownership of a shared database table. Neither will agree to own schema migrations. Three PRs have been blocked for 6 weeks waiting for ownership clarification. You do not manage either team. Walk through your influence strategy level by level.

**Q4.** A team refuses your new distributed tracing standard because it adds "2ms latency to every request." You believe the observability benefit outweighs the latency cost. How do you find out if you are right or wrong before your next conversation with them?

**Q5.** When is escalating to a VP the right move? Write the checklist: what conditions must all be true before escalation is appropriate?

**Q6.** You need 6 months of engineering time from a team that is at 110% capacity with their own roadmap. What do you do *before* the conversation with their engineering manager?

**Q7.** An engineer on another team is technically wrong about a design choice in their system -- not just stylistically different, but factually incorrect in a way that will cause incidents. They are defensive about it. Their team lead supports them. What do you do?

---

## Part 3: Running Design Reviews

### The Analogy

A book editor does not rewrite the book. A book editor reads the manuscript and asks questions that make the author see what the author cannot see about their own work:
- "I don't understand why the character does this in chapter 7."
- "The ending resolves too quickly -- what did the character learn?"
- "Chapter 3 and Chapter 9 contradict each other."

The author knows the story better than the editor. The editor knows what a reader who has not lived inside the author's head will experience.

A staff engineer in a design review is the editor. The team writing the design knows the domain better than you. Your job is to see what they cannot see because they have been staring at the problem for 6 weeks.

The test of a good design review is not whether you found issues. It is whether the design got *stronger* AND the engineer grew *smarter* from the experience.

---

### Three Types of Design Documents

```
  TDD (Technical Design Document)
  +-----------------------------------------+
  | When: before implementing a new service  |
  |        or major refactor                 |
  | Author: L4 or L5 engineer               |
  | Audience: team + adjacent team leads    |
  | Scope: one system or service            |
  | Decision type: local (team owns it)     |
  | Length: 3-10 pages                      |
  | Contains: problem, solution, trade-offs, |
  |   alternatives considered, rollout plan  |
  +-----------------------------------------+

  RFC (Request for Comments)
  +-----------------------------------------+
  | When: proposing a cross-team standard,   |
  |        new API contract, deprecation of  |
  |        a shared dependency               |
  | Author: L5 or L6 engineer               |
  | Audience: all teams affected            |
  | Scope: cross-team or org-wide           |
  | Decision type: requires alignment from  |
  |   multiple team leads or up to VP       |
  | Length: 5-20 pages                      |
  | Contains: motivation, proposal, impact  |
  |   on each affected team, migration path,|
  |   alternatives, explicit decision ask   |
  +-----------------------------------------+

  1-pager (Architecture Decision Record)
  +-----------------------------------------+
  | When: after a decision is made, to       |
  |        record it permanently             |
  | Author: whoever made the decision       |
  | Audience: future engineers              |
  | Scope: one specific decision            |
  | Decision type: already decided          |
  | Length: 1 page                          |
  | Contains: the decision, the context,    |
  |   the alternatives rejected, the        |
  |   expected outcome, review date         |
  +-----------------------------------------+
```

---

### The 5-Question Framework for Every Design Review

These 5 questions will surface 90% of the problems in any design. Use them every time, in this order. They move from high-level to low-level -- if the answer to question 1 is wrong, questions 2-5 don't matter.

**Question 1: What problem does this solve?**

Not "what does this build" -- are we solving the right problem in the first place?

Example of this going wrong: A team designs an elaborate caching system to speed up a search endpoint. But the endpoint is called 4 times per day by 3 internal tools. The real problem is that a slow search endpoint is annoying for 3 internal users. The right solution is a 2-hour fix to an inefficient database query. The elaborate caching system would take 6 weeks.

Question to ask: "What does success look like for users when this is done? And can we measure it?"

---

**Question 2: What breaks at 10x?**

Not "will it scale" -- that is too vague. Name the specific component that breaks first.

Example: "At 10x traffic, your Redis single instance becomes the bottleneck. You are at 1,000 reads/sec today. Redis can handle ~100,000 reads/sec on a single node. At 10x you are at 10,000 -- still fine. But at 100x (10 years of growth at 25% per year), you need Redis Cluster. The design should note this and either add cluster support now or document 'add cluster at 50K reads/sec.'"

---

**Question 3: What is the blast radius if this fails?**

Three specific sub-questions:
- Which users are affected, and how many?
- Which dependent services break, and which of those are mission-critical?
- What is the recovery time (RTO) and how much data is lost (RPO)?

Example: "If this new auth service is unavailable, who is affected? Every user who needs to log in. That is 100% of users. But also: every service that validates tokens internally. That includes payments, recommendations, and the mobile API. This service has an effective blast radius that affects every surface of the product. Does the availability target (99.9%) reflect that?"

---

**Question 4: How do you undo this?**

Three types of changes need specific rollback analysis:
- **Schema migrations:** How do you roll back if the new schema breaks something? Is there a safe down-migration?
- **Data migrations:** If the new code writes data in a new format, can the old code read it during a partial rollout?
- **API contracts:** If you deploy a new API version and clients update to it, what happens if you need to roll back the server?

Example: "You are adding a new `payment_method` column to the `orders` table with a NOT NULL constraint. If you roll back the deploy, the old code will try to insert rows without this column. That will fail at the database level. You need either: a nullable column that the old code tolerates, or a two-phase deploy (deploy the column separately, then deploy the code that uses it)."

---

**Question 5: What is the smallest thing you can ship to validate the core assumption?**

Every design has a core assumption that, if wrong, invalidates the entire approach. This question finds that assumption and asks: can we test it cheaply?

Example: "The core assumption of this design is that users will prefer async processing (submit order, get email when done) over synchronous processing (wait 5-10 seconds for confirmation). This assumption should be validated with 100 users before you build the entire async infrastructure. Can we add a feature flag and test with 1% of traffic for 2 weeks?"

---

### How to Give Feedback That Makes Engineers Smarter

The difference between feedback that corrects and feedback that teaches is the difference between an engineer who does not repeat the mistake and an engineer who understands why the mistake was a mistake.

**Feedback that corrects:**
```
  "Use DateTimeFormatter instead of SimpleDateFormat.
   SimpleDateFormat is not thread-safe."
```

The engineer makes the change. Fine. But next month, they reach for `Calendar` in a shared context. Same class of bug.

**Feedback that teaches:**
```
  "SimpleDateFormat is not thread-safe -- here is exactly why,
   because it matters for the next 10 years of your career:

   SimpleDateFormat stores its parsing state in mutable instance
   variables (a Calendar object and a NumberFormat object).
   When two threads call parse() simultaneously, they both write
   to the same Calendar instance. The result is corrupted dates --
   silently, no exception, just wrong output.

   Here is a quick mental model: if a class keeps track of
   'where I am in the process' between method calls, it is
   stateful and not thread-safe unless it synchronizes.
   SimpleDateFormat does this. DateTimeFormatter does not --
   it is immutable, so every parse() call is fully independent.

   General rule for java.text: assume not thread-safe.
   General rule for java.time: assume thread-safe.

   You can reproduce the bug in 5 minutes: create one
   SimpleDateFormat, parse from 10 threads simultaneously,
   and watch it produce corrupted dates within seconds."
```

The engineer now has a mental model that catches `Calendar`, `SimpleDateFormat`, `NumberFormat`, and anything else in `java.text` -- for the rest of their career.

---

### The Feedback Prioritization Rule

A code review with 18 comments is not 4x more valuable than one with 4 comments. Often it is less valuable: the engineer is overwhelmed, cannot tell what is important, and may feel attacked rather than helped.

```
  COMMENT ON:
  - Correctness bugs: ALL of them (no exceptions)
  - Security vulnerabilities: ALL of them (no exceptions)
  - Design problems: TOP 2-3 ONLY
    (if there are more, schedule a conversation -- this is
     a design review problem, not a code review problem)

  DO NOT COMMENT ON:
  - Style (use a linter; do not waste relationship capital on spaces)
  - "I would have done this differently" (unless your way has
     a specific, concrete advantage)
  - Personal preference in variable naming

  THE 5-COMMENT RULE:
  If you have more than 5 substantive comments, stop.
  Add a top-level comment: "I have a lot of feedback here.
  Before I put it all in comments, can we spend 30 minutes
  walking through this together? I think that will be more
  efficient."
  Then have the conversation. Code review comments are an
  async tool that becomes worse than a synchronous conversation
  past a certain volume.
```

---

### Running the Design Review Meeting

Most design review meetings fail for the same reason: decisions made in the meeting evaporate within 48 hours because nobody wrote them down clearly.

```
  DESIGN REVIEW MEETING STRUCTURE (60 minutes):

  0-10 min:   SILENT READING
              Everyone reads the doc. No talking.
              Everyone writes their questions on paper or in a
              shared doc while reading.
              (If you assign reading "before the meeting" and
              people do not read it, this fixes that.)

  10-20 min:  AUTHOR OVERVIEW
              Author walks through the design.
              No interruptions during this section.
              The author gets 10 minutes to present their vision
              without being derailed.

  20-50 min:  STRUCTURED QUESTIONS
              Use the 5-question framework.
              IC (usually the staff engineer) moderates.
              No solutions during this phase -- only questions
              and identification of issues.

  50-58 min:  EXPLICIT DECISIONS
              For each issue surfaced: is this a blocker?
              Who owns the resolution? By when?
              Document this in real-time.

  58-60 min:  SUMMARY READ-BACK
              IC reads back every decision and action item.
              Anyone can correct the record.
              Send the written summary within 24 hours.

  THE SILENCE RULE:
  If the room goes quiet during Q&A, that is not awkward.
  It means people are thinking.
  Do not fill the silence. Let it breathe for 10 seconds.
  The best question in the meeting often comes from the
  person who was thinking during the silence.
```

**Decision documentation template:**
```
  DECISION: [We will / We will not] [specific choice]
  REASON: [one sentence]
  OWNER: [specific person]
  DUE: [specific date]
  OPEN QUESTION: [if not fully resolved]
  REVISIT: [date to check if assumption was correct]
```

---

### Real Production Incident 4: Amazon "The 14-Person Design Review" (reported in "Working Backwards")

**What happened:** A major Amazon feature team spent 6 weeks in design reviews with 14 engineers attending every meeting. The reviews were "consensus-based" -- decisions required everyone to agree. Three major architectural issues raised in week 1 remained unresolved in week 6. The feature shipped with all three issues. Two became incidents within the first month.

```
  WEEK 1: Engineer A raises concern about the data model.
          "If we store user preferences this way, we cannot
           query across users efficiently."
  Response: "Good point. Let's table it and discuss next week."

  WEEK 2: Same concern raised again by a different engineer.
  Response: "We should align on this. Let's come back to it."

  WEEKS 3-5: Issue mentioned but not resolved. No owner.

  WEEK 6: Feature ships. Data model unchanged.

  MONTH 2: The cross-user query runs in 90 seconds because
           of the inefficient data model. Alert fires.
           Incident declared. Root cause: the design review
           identified this in week 1.
```

**The root cause of the meeting failure:** No decision authority. Fourteen people with opinions and zero people with the authority to say "we are doing it this way."

**What Amazon changed (from the Working Backwards framework):**
- Maximum 2 "decision makers" in any design review
- All other attendees are "informed and input" -- they can comment, not veto
- Design review owner is clearly identified in the document header
- Unresolved issues are escalated within 1 week, not carried indefinitely

**Staff lesson:** Running a good design review means establishing decision authority at the start, not at the end. "I am the decision owner for this review. I will collect input from everyone, but the final call on unresolved points is mine by Thursday."

---

### Brainstorming Questions -- Part 3: Running Design Reviews

**Q1.** A junior engineer is defensive about design feedback. Every time you raise an issue, they explain why it is actually fine. How do you handle this in the moment, and how do you handle it in the longer-term relationship?

**Q2.** Two L5 engineers are in strong disagreement about the database choice in a design review you are running. They have been arguing for 10 minutes. You have 8 minutes left. What do you do?

**Q3.** A design doc says "we will add database sharding when needed." What is the specific follow-up question that separates an L6 reviewer from an L4 reviewer?

*(L4 might accept this. L6 asks: "At what metric do we add sharding? Who makes that call? What is the migration plan from unsharded to sharded? How long does that migration take? Should we design for it now or document the trigger point?")*

**Q4.** You are reviewing a design 3 weeks before launch. You find a fundamental flaw that requires rethinking the data model. The team has already written 70% of the code. What do you do? What changes if it is 3 days before launch?

**Q5.** When should a design review result in "approved with changes" vs "approved" vs "not approved -- needs revision"? Write the decision criteria for each outcome.

**Q6.** A team skips the design review because "the feature is small." It causes a 4-hour incident because of an edge case that a design review would have caught. How do you change the culture without mandating every feature go through review?

**Q7.** You are reviewing a design from a team you are not close to. The design is technically sound but clearly over-engineered -- 3x the complexity needed for the current scale. How do you give this feedback without demoralizing a team that worked hard on it?

---

## Part 4: Technical Strategy and the Business Case for Tech Debt

### The Analogy

Technical debt is exactly like financial debt. It is not inherently bad. Taking out a mortgage is sensible if you need a house and can pay the monthly payments. The problems are:

1. **You forget you have a mortgage.** You stop paying it down. Interest accumulates.
2. **You take out 5 mortgages on the same house.** The payments exceed what you can afford.
3. **You need to renovate the house but cannot because all your cash goes to mortgage payments.** Every new feature touches the monolith and takes 2x longer because of accumulated debt.

And when the roof is leaking and you need money to fix it, you cannot just say "the roof is broken." You have to say: "The roof costs us $400/month in heating bills. If we don't fix it this winter, it will collapse. Fixing it now costs $8,000. Waiting costs $40,000 plus emergency restoration costs plus 3 months of unusable second floor."

That is the business case. Without it, "the roof is broken" competes with "we want a new deck" for the same budget. The deck wins because it is visible and exciting. The roof loses because it is invisible and boring.

---

### Writing a Technical Vision Document

A technical vision document is not a wishlist. It is a *funded plan* for where the technical foundation needs to go over the next 12-36 months. The document's job is to make one specific ask: "Give me this headcount and timeline. In return, I will deliver these measurable improvements."

```
  STRUCTURE OF A TECHNICAL VISION DOCUMENT:

  PART 1: CURRENT STATE (with data -- NOT with adjectives)

  Wrong: "Our auth service is a mess and causes lots of problems."
  Right:
  "Auth Service: Current State (Q2 2026)
  - 2 engineers spend 35% of their time on auth toil
    (manual token rotation, cert management, permission updates)
  - 4 incidents per month attributable to auth service
    (avg 2.5 hours each, 2 engineers per incident)
  - Payment team: every feature touching auth takes 3 extra
    weeks due to auth service complexity
  - Mobile team: cannot ship biometric auth (6 months blocked)
    because auth service does not support the required API

  Annual cost of current state: $374K (calculated below)"

  PART 2: TARGET STATE (specific, not aspirational)

  Wrong: "A modern, scalable, developer-friendly auth service."
  Right:
  "Auth Service: Target State (Q4 2027, 18 months)
  - Zero manual token rotation (automated via OIDC)
  - p99 auth check: < 20ms (today: 120ms average)
  - Zero auth-related incidents (today: 4/month)
  - Payment team: auth-touching features take 1 extra week
    (today: 3 extra weeks)
  - Mobile team: biometric auth supported (6-month OKR unlocked)"

  PART 3: GAP ANALYSIS
  What needs to change to get from current to target.
  Which dependencies need to change first (ordering matters).

  PART 4: MIGRATION PATH
  How you move from current to target without breaking things.
  No "big bang" rewrites. Show the incremental stages.
  Each stage should be independently releasable.

  PART 5: INVESTMENT ASK (in business terms)
  - Headcount: 2 engineers full-time for 6 months
  - Cost: $300K (loaded salary estimate)
  - What you will NOT be building instead: [list]
  - Risk of not doing this: $374K/year ongoing

  PART 6: RISKS OF INACTION (the most important section)
  If leadership reads nothing else, they read this.
```

---

### The Business Case Formula: Converting Tech Metrics to Money

This is the skill that separates staff engineers who get tech debt funded from those who don't. Every number you carry about technical debt should be translatable to a dollar figure.

**Step 1: Count the engineer toil**
```
  FORMULA: (engineers) x (% time on toil) x (loaded salary)

  EXAMPLE:
  2 engineers spend 35% of time on auth toil
  Loaded salary per engineer: $300K/year
  Annual cost: 2 x 0.35 x $300K = $210,000/year
```

**Step 2: Count the incident cost**
```
  FORMULA: (incidents/month) x (12) x (hours/incident) x
           (engineers per incident) x (hourly cost per engineer)

  EXAMPLE:
  4 incidents/month, 2.5 hours each, 2 engineers
  Engineer hourly cost: $300K / 2,000 hours = $150/hour
  Annual cost: 4 x 12 x 2.5 x 2 x $150 = $36,000/year

  (This is engineer time only. Add revenue impact separately
  if you have the number.)
```

**Step 3: Count the velocity tax**
```
  FORMULA: (features/year touching this system) x
           (extra weeks per feature) x (engineer-week cost)

  EXAMPLE:
  Payment team ships 8 features/year that touch auth.
  Each takes 3 extra weeks due to auth complexity.
  1 engineer-week cost: $300K / 52 = $5,769 ~ $6K

  Annual velocity tax: 8 x 3 x $6K = $144,000/year
```

**Step 4: Add up and make the table**
```
  +-----------------------------------+--------------+--------------+
  | Debt Category                     | Annual Cost  | Fix Cost     |
  +-----------------------------------+--------------+--------------+
  | Engineer toil (auth service)      | $210,000     | included     |
  | Incident response (4/month)       | $36,000      | included     |
  | Velocity tax (payment team)       | $144,000     | included     |
  | Velocity tax (mobile team --      | ~$72,000     | included     |
  |   blocked biometric feature)      |              |              |
  +-----------------------------------+--------------+--------------+
  | TOTAL ANNUAL COST                 | $462,000/yr  | $300,000     |
  +-----------------------------------+--------------+--------------+

  ROI: The fix pays for itself in 8 months.
       Every subsequent year saves $462,000.
       Over 3 years: $1.386M savings from a $300K investment.
```

Now you have a business conversation, not a technical complaint.

---

### The Real Reason Tech Debt Doesn't Get Fixed

Even with a perfect business case, tech debt often doesn't get prioritized. Here is why, and what to do about it:

**Reason 1: The debt is invisible to leadership**

A new feature is visible. It ships, users see it, revenue metrics move (hopefully). Tech debt reduction is invisible -- what you measure is what *didn't* happen (incidents that didn't occur, time that wasn't wasted). Invisible things don't compete well for budget.

Fix: create visible progress metrics. "Auth incidents per month: Q1: 4, Q2: 2 (after phase 1), Q3: 0 (target after phase 2)." Show the trend.

**Reason 2: The PM has a different definition of "urgent"**

Urgency = visible user pain + imminent deadline. Tech debt is neither -- it is slow-moving invisible cost. In the PM's world, an urgent customer request is more urgent than your auth migration.

Fix: connect the debt to a PM's OKR. "The mobile team cannot ship biometric auth until we fix the auth service. Biometric auth is on your Q3 roadmap. Your Q3 OKR is at risk."

**Reason 3: Leadership doesn't trust the estimate**

"6 months? Last time we said 3 months and it took 12." This is a trust problem.

Fix: break the work into independently valuable 6-week phases. Each phase ships something usable. "Phase 1 (6 weeks): eliminate manual token rotation. You will see this: auth toil drops from 35% to 15% of 2 engineers' time. Measure that. If I'm wrong, we stop." Deliver phase 1. Then ask for phase 2.

---

### Real Production Incident 5: Twitter "Fail Whale" Era (2008-2012)

**What happened:** Twitter's Ruby on Rails monolith could not handle the traffic load as Twitter grew explosively. The service went down during every major event: Super Bowl, earthquakes, celebrity deaths, elections. The "Fail Whale" error page became so culturally ubiquitous that it was turned into merchandise.

```
  THE COST CURVE OF DELAYED TECH DEBT:

  2008: Ruby on Rails monolith
        Fix cost estimate: ~$5M (small team, 6-month rewrite)
        Business decision: "Ship features. Rewrite when we have
        time." (They never had time while shipping features.)

  2009: Site goes down 2-3 times per week during traffic spikes.
        Fix cost estimate: ~$15M (codebase now larger)
        Business decision: same.

  2010: Site down during every major world event.
        Brand damage begins. Press writes "Twitter is unreliable."
        Fix cost: ~$30M

  2011: Can no longer avoid it. Begin Scala/JVM migration.
        Full cost: ~$75M + 2 years of engineer time pulled
        from feature development.

  2013: Migration complete. Twitter stable.

  TOTAL COST OF DELAY: ~$75M + brand damage + user loss
  COST OF FIXING IN 2008: ~$5M
  COST OF DELAY: ~$70M

  The staff engineer's job is to make this argument in 2008,
  not help clean up the mess in 2011.
```

**The lesson for your day job:** Every month you delay addressing a known architectural problem, the codebase grows around the problem. More services depend on the broken thing. More data is in the bad schema. More engineers build assumptions on the shaky foundation. The cost of the fix grows faster than the cost of the ongoing debt in most cases.

**The number to remember:** A problem you can see today and delay addressing typically costs 3-5x more to fix in 2 years than it does today, because of accumulated dependencies. Use this in your business case: "If we do not fix this now, fixing it in 2027 will cost $900K instead of $300K, because by then 6 more services will have built dependencies on the current behavior."

---

### Brainstorming Questions -- Part 4: Technical Strategy

**Q1.** A PM says "we cannot afford to pay down tech debt -- we have customer commitments to hit." What is wrong with this framing, and how do you reframe the conversation?

**Q2.** You have identified $800K of tech debt across 4 systems. You have budget for $300K this year. How do you prioritize which debt to pay down? Write the decision criteria.

**Q3.** What is the difference between tech debt and a poor design that should simply be lived with? Give an example of debt that is acceptable to carry indefinitely.

**Q4.** A technical vision doc says "we will migrate from monolith to microservices." A skeptical VP asks "why?" Write the one-sentence business answer that is not "because microservices are better."

**Q5.** Your team has been paying down tech debt for 4 months. No new features have shipped. Leadership is losing patience. How do you show progress without shipping a user-visible feature?

**Q6.** When is it acceptable to intentionally take on new technical debt? Write the conditions that must be true. Who needs to be aware of and agree to the decision?

**Q7.** An engineer on your team proposes a "complete rewrite" of a core service. What is your immediate reaction, and what questions do you ask before deciding whether to support or oppose the proposal?

*(Hint: "Complete rewrite" is almost always the wrong answer. Joel Spolsky's 2000 essay "Things You Should Never Do" applies almost universally. The right question is: can we replace this ship's planks one at a time while sailing?)*

---

## Part 5: Multiplying Through People

### The Analogy

A master chef at a Michelin-starred restaurant can cook 30 perfect dishes a night. If the restaurant wants to serve 300 covers, the master chef has two choices:

Choice A: Work 10x harder. Cook 300 dishes. This is physically impossible and also misses the point of running a restaurant.

Choice B: Teach 10 cooks to cook at 90% of master-chef quality. The restaurant serves 300 covers at excellent quality, the master chef is the architect of the food, and each cook is growing.

A staff engineer who does everything personally is choice A. A staff engineer who builds the team's capability is choice B.

The shift from A to B is uncomfortable. You will watch junior engineers do things more slowly than you would. You will see them make mistakes that you would not have made. Every instinct says "I should just do this." Resist that instinct. The only way to multiply your impact is to invest in the people around you.

---

### Code Review That Builds Engineers

The most consistent multiplier opportunity a staff engineer has is code review. Most engineers do 10-20 code reviews per week. If each review teaches something, that is 10-20 learning moments per week.

Most code review does none of this. It corrects mistakes, which is necessary but not sufficient.

**The difference between correcting and teaching -- three examples:**

*Example 1: Concurrency*

Correction: "Use a concurrent map here. This will cause race conditions."

Teaching:
```
  "This map is accessed from multiple goroutines simultaneously.
   In Go, map operations are not atomic -- two concurrent writes
   can corrupt the internal data structure, which can cause
   anything from wrong values to a fatal panic.

   The Go race detector will catch this: run with '-race' and
   you will see it immediately. This is actually a great
   exercise -- add a test that spawns 100 goroutines that all
   write to this map simultaneously and run with '-race'.

   Fix: use sync.Map for concurrent access, or protect the
   regular map with a sync.RWMutex (read lock for reads,
   write lock for writes).

   The deeper principle: any time you see a data structure
   shared across goroutines without explicit synchronization,
   ask 'who owns the synchronization?' If the answer is
   'nobody', that is a race condition waiting to happen."
```

*Example 2: Database indexing*

Correction: "Add an index on user_id here."

Teaching:
```
  "This query: SELECT * FROM orders WHERE user_id = ? AND
   status = 'pending' will do a full table scan when orders
   grows past ~100K rows, because there is no index on
   (user_id, status).

   The composite index (user_id, status) serves this query
   efficiently because the database can use the user_id to
   narrow to that user's orders, then use status to filter
   within those.

   Note the order matters: (user_id, status) is better than
   (status, user_id) for this query because user_id has
   higher cardinality (more unique values) -- it filters down
   to a small set faster.

   Check the query plan with EXPLAIN: EXPLAIN SELECT * FROM
   orders WHERE user_id = 123 AND status = 'pending'
   Look for 'Seq Scan' -- that tells you there is no index
   being used. After adding the index, 'Index Scan' appears."
```

*Example 3: Security*

Correction: "Sanitize this input."

Teaching:
```
  "This query is vulnerable to SQL injection:
   query = 'SELECT * FROM users WHERE email = ' + user_input

   If user_input is: ' OR '1'='1
   The query becomes: SELECT * FROM users WHERE email = '' OR '1'='1'
   That returns every user in the database.

   If user_input is: '; DROP TABLE users; --
   The query becomes: SELECT * FROM users WHERE email = '';
   DROP TABLE users; -- ...
   (This drops the users table.)

   Fix: use parameterized queries:
   db.query('SELECT * FROM users WHERE email = ?', [user_input])

   The database driver sends the query and the parameters
   separately. The database treats the parameter as data,
   never as SQL code. Injection is structurally impossible.

   Rule: never concatenate user input into any query string.
   Ever. Not 'mostly never'. Never."
```

---

### Promotion Calibration: What L6 Engineers Assess

When a team lead or manager asks a staff engineer to weigh in on an engineer's promotion case, here is the framework:

```
  ASSESS ON 5 DIMENSIONS:

  1. SCOPE OF IMPACT
     Is the engineer solving problems at the NEXT level,
     or are they doing current-level work very well?
     L4 --> L5: Are they driving a project independently,
     not just completing assigned tasks?
     L5 --> L6: Are they identifying and solving problems
     that nobody asked them to solve?

  2. CONSISTENCY
     One great quarter is not a promotion signal.
     Three quarters of consistent impact at the next level is.
     "High ceiling, low floor" is not a promotion profile.
     "Reliable, consistent" is.

  3. INDEPENDENCE + JUDGMENT
     L4 --> L5: Can they own a project from start to finish
     with minimal hand-holding?
     L5 --> L6: Can they identify the right project to own
     without being told?

  4. CONCRETE IMPACT (measurable, not impressionistic)
     Not: "writes great code"
     Yes: "reduced checkout p99 from 800ms to 180ms,
          contributing to 2.3% increase in conversion"
     Not: "very collaborative"
     Yes: "drove adoption of shared logging standard across
          3 teams, reducing on-call alert noise by 40%"

  5. INFLUENCE ON OTHERS
     Are other engineers coming to them for advice?
     Are junior engineers growing faster because of them?
     Do designs get better when they are in the room?
```

**The most common promotion mistake:** Promoting for potential rather than demonstrated performance. "They are SO good, they are clearly ready." The question is not whether they *can* do the next level. The question is whether they *have been doing* the next level consistently.

---

### Game Days: Rehearsing Failure Before It Happens

A game day is a scheduled, controlled production failure designed to find gaps in your runbooks, alerting, and on-call response before a real incident finds them.

The key word is *scheduled*. This is not a surprise drill. You tell the business, you tell all stakeholders, you coordinate the timing. The only person you do not tell is the on-call engineer.

```
  GAME DAY DESIGN TEMPLATE:

  CHOOSE THE SCENARIO:
  Pick the failure you are MOST afraid of but have NOT
  prepared for. Not the one you have a runbook for.
  The gap between "we have a runbook for this" and
  "we have a runbook for this that actually works" is
  what game days find.

  EXAMPLE SCENARIOS BY SYSTEM TYPE:
  Web service:      Primary database fails completely
  Caching layer:    All cache nodes fail simultaneously
                    (cache stampede)
  Distributed sys:  Network partition between two datacenters
  Queue-based:      Consumer group falls behind by 10 minutes
  Streaming:        Producer rate 10x normal (sudden spike)

  DEFINE SUCCESS CRITERIA FIRST:
  "Success: on-call detects the failure within 5 minutes and
   mitigates (restore service or shed load gracefully) within
   30 minutes, with no data loss and no unintended blast radius."

  WHAT TO OBSERVE:
  - How quickly does monitoring detect the failure?
  - Is the alert clear enough that on-call knows what happened?
  - Is the runbook step-by-step enough to follow at 3 AM?
  - What broke that the runbook did not mention?
  - Who had to be called that was not in the runbook?

  AFTER:
  - Update runbook with every gap found
  - Add/adjust monitoring for every gap in detection
  - Write the retrospective
  - Schedule the next game day (quarterly is minimum)
```

**Netflix Chaos Monkey:** Netflix's chaos engineering tool randomly kills production services during business hours, multiple times per week. The team that builds a service must build it to survive random instance failure, because Chaos Monkey will kill instances whether or not they are ready. Result: every Netflix service is built to survive partial failure by default.

```
  CHAOS MONKEY PHILOSOPHY:
  +------------------------------------------+
  | Without chaos: team builds service.       |
  | Service works in happy path.              |
  | Someday, an instance dies unexpectedly.  |
  | Team scrambles. Users affected.           |
  +------------------------------------------+
  | With chaos: team builds service.          |
  | Chaos Monkey kills an instance Tuesday.  |
  | Team fixes the weakness Wednesday.        |
  | Next chaos kill: Wednesday. Team ready.  |
  | Real failure someday: team handles it.    |
  +------------------------------------------+
  Reliability is a muscle. You build it by training.
```

---

### Structured Mentoring: What Good 1:1s Look Like

Most mentoring fails because it has no structure. An ad-hoc conversation every few weeks where the engineer says "things are going okay" and you say "great, let me know if you need anything" is not mentoring. That is a status check.

Effective mentoring requires a structure that creates accountability, surfaces real blockers, and tracks growth over time.

**The Monthly Growth 1:1 (45 minutes, monthly)**

```
  AGENDA:

  5 min:  WHAT DID YOU SHIP THIS MONTH?
          Not "what did you work on" -- what shipped?
          Shipped = merged, deployed, or decided.

  10 min: WHAT DID YOU LEARN?
          One technical thing. One people/process thing.
          If they say "nothing specific", probe:
          "What was the hardest problem you ran into?"
          "What would you do differently?"

  15 min: WHERE ARE YOU STUCK?
          This is the most important section.
          Engineers rarely volunteer what they are stuck on.
          They are afraid of looking incompetent.
          Ask directly: "What is the one thing slowing
          you down the most right now?"
          Then ask: "Is it a knowledge gap, a tools gap,
          a people gap, or a process gap?"
          Each has a different fix.

  10 min: GROWTH TARGET CHECK
          At the start of each quarter, you set 1-2 growth
          targets together. Review progress.
          "Last month you said you wanted to run your first
          design review independently. Did that happen?
          What got in the way?"

  5 min:  WHAT DO YOU NEED FROM ME THIS MONTH?
          Specific. Not "more feedback" --
          "more feedback on what, in what form, by when?"
```

**Growth target examples by level:**

```
  L3 -> L4 GROWTH TARGETS:
  - Own a task from initial investigation to production
    without waiting to be told what to do next
  - Write one runbook for something they know how to do
  - Participate in one design review and ask one question

  L4 -> L5 GROWTH TARGETS:
  - Own a full project: scope, timeline, execution, ship
  - Write a TDD for a non-trivial change
  - Unblock yourself on a cross-team dependency once
    without asking me first

  L5 -> L6 GROWTH TARGETS:
  - Identify a problem nobody asked them to solve, and
    propose a solution with business case
  - Run a design review (not just attend one)
  - Drive adoption of something across one other team
```

**The growth plan document (written together, quarterly):**

```
  GROWTH PLAN: [Engineer Name], [Quarter]

  CURRENT LEVEL: L4
  TARGET LEVEL: L5 (target date: Q3 2027)

  WHERE THEY ARE STRONG:
  - Technical execution (writes solid, correct code)
  - Debugging (fastest on the team at finding root cause)

  WHERE THEY ARE DEVELOPING:
  - Scope: currently reactive; needs to identify own work
  - Communication: good at 1:1 technical chat; quieter
    in group settings with senior engineers

  GROWTH TARGETS THIS QUARTER:
  1. Own the caching layer refactor from start to finish
     (scope it, write the TDD, execute, ship)
     Success: ships by month 3 without me coordinating it
  2. Speak up in 3 design reviews with at least one
     substantive question per review
     Success: I observe it happening

  MY ROLE (what I will do differently):
  - Not answer questions they could answer themselves;
    instead ask "what do you think?" first
  - Connect them with the search team lead for the
    caching work (they will need to coordinate there)

  REVIEW DATE: [End of quarter]
```

The document is written together -- not delivered to them. An engineer who co-authors their growth plan is 3x more likely to act on it than one who receives it from above.

---

### Hiring and Running Interview Loops

Hiring is one of the highest-leverage activities a staff engineer does, and most engineers underinvest in it.

Why it matters: if you hire one engineer who is 20% more capable than the bar, they compound. They ship more, they raise the quality of code reviews, they give better design feedback. The benefit accrues for years. Conversely, a bad hire -- someone clearly below the bar -- costs 6-12 months of a manager's time to manage out and sets a precedent that the bar is lower than it should be.

**The interview loop structure:**

```
  A STAFF ENGINEER'S ROLE IN THE LOOP:

  BEFORE THE LOOP:
  - Define the bar: what does "L5 hire" look like for
    this specific role? Write it down. Share it with
    all interviewers before the loop starts.
  - Calibrate with interviewers: run a mock interview
    with a new interviewer and give them feedback before
    they interview real candidates.

  DURING THE LOOP:
  - Staff engineer typically runs 1-2 interviews per loop:
    - System design (your wheelhouse)
    - Technical deep dive (debugging, architecture)
  - Your job is not to trick the candidate -- it is to
    assess whether they can do the job.

  AFTER THE LOOP (debrief):
  - Every interviewer submits a written assessment BEFORE
    the debrief call. Written first, then discussed.
    (Otherwise the first person to speak anchors everyone.)
  - Debrief structure:
    T+0: Each interviewer reads their written assessment.
    T+15: "Is there any signal that changes anyone's mind?"
    T+25: Make the decision.
  - The decision is HIRE or NO HIRE. "Lean hire" or
    "lean no hire" are weasel words that avoid making
    a call. Make the call.
```

**How to assess system design in an interview:**

The system design interview is not about getting the "right" answer. It is about watching how someone thinks.

```
  WHAT TO ASSESS:

  REQUIREMENTS GATHERING (first 10 minutes):
  Strong signal: "Let me make sure I understand the scope.
  Are we designing for global users or one region?
  What is the read/write ratio? What does failure look like?"
  Weak signal: Jumps straight to "I'll use Kafka."

  SCALING AWARENESS:
  Strong signal: "At 1M users, Redis single instance works.
  At 100M users, we need Redis Cluster. Let me design for
  the 1M case and note the 100M inflection point."
  Weak signal: "We just need to shard."

  FAILURE MODE THINKING:
  Strong signal: "What happens if the cache layer fails?
  Do requests fall through to the database? What is the
  thundering herd risk?"
  Weak signal: "It's fine, we'll add monitoring."

  TRADE-OFF ARTICULATION:
  Strong signal: "I'm choosing eventual consistency here.
  That means users might see stale data for up to 5 seconds.
  For this use case (social feeds), that is acceptable.
  For payments, it would not be."
  Weak signal: Describes one approach with no alternatives.

  LEVEL CALIBRATION:
  +--------+------------------------------------------------+
  | Level  | What you expect                                |
  +--------+------------------------------------------------+
  | L4     | Designs a correct single-region system.        |
  |        | Knows the standard components.                 |
  |        | Needs prompts on failure modes.                |
  +--------+------------------------------------------------+
  | L5     | Designs a scalable system with trade-offs.     |
  |        | Identifies failure modes without prompts.      |
  |        | Considers operations (monitoring, alerting).   |
  +--------+------------------------------------------------+
  | L6     | Starts from requirements, not components.      |
  |        | Proactively asks about the WRONG requirements. |
  |        | ("Are you sure you need strong consistency?")  |
  |        | Designs for the failure modes you didn't ask   |
  |        | about. Knows what to cut for the MVP.          |
  +--------+------------------------------------------------+
```

**The "bar raiser" role:**

At many large companies (Amazon, Google, Meta), staff engineers serve as bar raisers or equivalent -- an independent check on the hiring bar who can veto a hire even if the rest of the loop voted to hire.

```
  WHEN TO USE YOUR VETO:

  USE IT when:
  - The candidate is clearly below the bar for the level
    and interviewers are going to hire out of excitement
    about one strong area that doesn't represent the role
  - The candidate showed a serious red flag (dishonesty,
    inability to accept feedback, claimed credit for
    others' work) that the loop is hand-waving away

  DO NOT USE IT when:
  - You would have designed the system differently
  - The candidate interviews better in writing than speech
  - The candidate is "good but not exceptional" -- that
    is a hire at the right level, not a veto

  THE VETO IS FOR PROTECTING THE BAR.
  Not for expressing personal preferences.
```

**Calibrating after a bad hire:**

If a hire turns out to be wrong, run a debrief on the interview loop itself:
- Which signal predicted the miss? (something the interviewers should have weighted more)
- Which signal was misleading? (something that looked good but wasn't predictive)
- What question would have surfaced the gap?

Update the interview scorecard with the finding. The goal is that the loop learns over time.

---

### Real Production Incident 6: Slack Mass Reconnection (New Year's Day 2021)

**What happened:** Slack performed a planned maintenance operation and brought their systems back online on New Year's Day 2021. When systems came back, millions of Slack clients that had been waiting for reconnection all attempted to reconnect simultaneously. The reconnection handling logic was designed for normal staggered reconnects (clients reconnecting randomly throughout the day), not for synchronized mass reconnects after a maintenance window.

The result: a 5-hour partial outage affecting millions of users during what should have been a routine maintenance recovery.

```
  NORMAL RECONNECT PATTERN:
  Clients reconnect randomly over time (natural jitter).
  System load curve:
  |
  |~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  |
  +--time-->  (flat, manageable load)

  AFTER PLANNED MAINTENANCE:
  All clients reconnect simultaneously.
  System load curve:
  |
  |     |
  |     |
  |~~~~~|_______________________
  +--time-->  (spike, then normal)
         ^
         |
    All clients reconnect here.
    System designed for flat curve.
    Spike: 10-100x normal load in seconds.

  WHAT HAPPENED:
  Reconnect spike --> Auth service overwhelmed
                  --> Token validation backed up
                  --> Clients timeout and retry
                  --> More reconnect load (retry storm)
                  --> Degraded for 5 hours
```

**Why this is a "Multiplying Through People" lesson:**

The failure mode -- "what happens when all clients reconnect simultaneously after a maintenance window?" -- was a known theoretical risk. It had been raised in design discussions. But it was never *tested*. No game day had ever simulated maintenance recovery at scale.

The engineers who built the reconnect handling built it correctly for the normal case. Nobody ran a game day that said "simulate: all clients reconnect at once after a 30-minute window." If that game day had happened, the engineers would have seen the spike immediately and built in exponential backoff and jitter.

```
  THE FIX (implemented after the incident):
  Reconnect with jitter:
    backoff = min(base_delay * 2^attempt, max_delay)
    jitter = random(0, backoff * 0.3)
    wait(backoff + jitter)

  This spreads reconnects over minutes instead of seconds.
  The spike becomes a gentle ramp-up.
  Maintenance recovery is now safe.
```

**Staff lesson:** The multiplying-through-people angle is this: the fix required one senior engineer to write the exponential backoff with jitter algorithm. But the *game day* that would have caught it required a staff engineer to ask: "What is our riskiest maintenance window scenario?" and then build the practice of testing it annually. The game day design and the culture of testing failure scenarios is a multiplier. The individual fix is an individual contribution.

---

### Brainstorming Questions -- Part 5: Multiplying Through People

**Q1.** A junior engineer writes clean, correct code but never speaks up in design reviews. Three months of this pattern. How do you develop the skill in them without making them feel singled out?

*Think about: giving them a specific, safe assignment before the meeting ("you're going to ask the rollback question"), debriefing them 1:1 after, not calling on them publicly before they're ready.*

**Q2.** You are reviewing a PR. You have 12 issues to raise. How do you decide which 3-4 to actually comment on? Write the prioritization logic.

*Think about: correctness and security are always raised, design issues only the top 2-3, style goes to a linter. If you have more than 5 substantive issues, stop and schedule a conversation instead.*

**Q3.** An engineer you have been mentoring for 4 months is not improving despite specific, concrete feedback each month. You have had 3 direct conversations. What do you do now?

*Think about: Is the growth plan written down? Is the feedback landing (do they understand it or just nod)? Have you checked whether there's a blocker you don't know about (team dynamics, outside-work issue)? After 4 months, the conversation shifts from coaching to documentation. Alert their manager that your mentoring is not moving the needle.*

**Q4.** A team's on-call rotation has averaged 4 pages per week per engineer for 6 months. Engineers are burning out. The team says "we just need to fix the bugs." What is the staff engineer's diagnosis and what do you actually do?

*(This is not a bug fixing problem. It is an alert threshold problem, a toil problem, or a system reliability problem. The fix is tooling and architecture, not individual bug fixes.)*

**Q5.** You are designing a game day. What failure scenario do you choose, and why? What information do you need before you can write the success criteria?

*Think about: choose the failure you are most afraid of that has no runbook. Success criteria must be specific: not "system recovers" but "on-call detects within 5 minutes and mitigates within 30 minutes with no data loss."*

**Q6.** An engineer asks you to review every PR they write. You have 10 other engineers doing similar things. How do you make this sustainable without making that engineer feel abandoned?

*Think about: help them build their own review checklist so they self-review before coming to you. Pair them with an L5 reviewer for routine PRs. Reserve your review for architecture-impacting changes. Teach them what you look for so they internalize it.*

**Q7.** What is the difference between mentoring an engineer and being their manager? Where is the line, and what happens when you cross it?

*Think about: a mentor influences growth; a manager owns performance. The line: if you find yourself managing their deliverables, resolving their team conflicts, or participating in their performance review process -- that is management. Crossing it without the title creates confusion about accountability and can undermine the actual manager.*

---

## Part 6: Operating Under Pressure

### The Analogy

An air traffic controller manages 30 planes in the air simultaneously. Every pilot believes their landing is urgent. The controller cannot land all 30 planes at once.

The controller's job is not to make every pilot happy. It is to sequence the landings so no planes crash and all land safely. Some planes circle longer than others. Some are diverted. The controller is constantly triaging -- not by urgency of the pilot's request, but by the real constraints of the runway and the real risk of collision.

A staff engineer under pressure is the air traffic controller. Multiple P0 items, multiple blocked teams, multiple critical decisions, all arriving simultaneously. The job is not to handle every urgent request immediately. It is to sequence what is actually important in the right order.

The junior engineer's instinct: handle what is loudest. The staff engineer's discipline: handle what matters most.

---

### Escalate vs Absorb: The Decision Framework

One of the highest-leverage judgment calls at L6 is deciding whether to handle something yourself or to pull in leadership. Getting this wrong in either direction is costly:

- **Over-escalating:** Trains leadership that you cannot operate autonomously. Wastes leadership time on things you should handle. Reduces your credibility.
- **Under-escalating:** You sit on a problem that requires resources or authority you do not have. The problem gets worse. The eventual escalation is more expensive than an early one would have been.

```
  ABSORB IT YOURSELF WHEN:
  +-----------------------------------------------+
  | - Blast radius is within your team or          |
  |   adjacent (one other team at most)            |
  | - You have a path to resolution within 48 hrs  |
  | - You have the resources to resolve it         |
  |   (no headcount or budget ask required)        |
  | - The decision is reversible                   |
  | - Pulling in leadership adds noise, not         |
  |   capability                                   |
  +-----------------------------------------------+

  ESCALATE WHEN:
  +-----------------------------------------------+
  | - Blast radius crosses multiple team           |
  |   boundaries and nobody has cross-org          |
  |   authority                                    |
  | - You need headcount or budget to resolve it   |
  | - The decision has VP-level business           |
  |   implications (revenue, legal, security)      |
  | - You have been blocked for 72+ hours with     |
  |   no path forward at your level               |
  | - The situation is deteriorating faster        |
  |   than you can manage it                       |
  | - A safety, legal, or compliance issue         |
  |   is in play                                   |
  +-----------------------------------------------+

  THE WRONG ESCALATION (most common mistake):
  Escalating because you disagree with another team.
  "They won't adopt our standard" is an influence problem.
  It is not an escalation-worthy problem until you have
  exhausted levels 1-4 of the influence stack.
```

**What to bring when you escalate:**

Never escalate just with the problem. Escalate with:
1. The problem, defined precisely (not "things are broken")
2. What you have tried already (not "I tried everything")
3. The specific ask (headcount? decision authority? budget?)
4. The cost of not deciding by [specific date]

```
  ESCALATION MEMO TEMPLATE (maximum 1 page):

  SITUATION:
  The payments team and the auth team have been unable to
  agree on session token format for 8 weeks. 3 features
  are blocked waiting for this decision.

  WHAT I HAVE TRIED:
  - Joint meeting (week 1): no decision, both teams dug in
  - Data on impact (week 3): both teams agreed the cost
    is real but could not agree on the solution
  - Proposed a third-party technical review (week 6):
    both teams agreed to the review; review recommended
    solution A. Auth team accepted. Payments team rejected.

  SPECIFIC ASK:
  I need you to make the final call on session token format.
  Both teams will accept a VP-level decision. They will not
  accept a staff engineer decision because they believe the
  choice affects their team's roadmap for 2 years.

  COST OF DELAY:
  3 features blocked. At 1 engineer each, that is 3 engineers
  idle for 8 weeks already = $192K in wasted capacity.
  Each additional week costs $24K. Decision needed by Friday.

  OPTIONS:
  A) Adopt payments team's recommendation (pros/cons attached)
  B) Adopt auth team's recommendation (pros/cons attached)
  C) Adopt the third-party recommendation from week 6
```

---

### Prioritizing When Everything Is P0

In any large engineering org, by the time something reaches a staff engineer's desk, it has been declared "critical" or "P0" by whoever sent it. The system has no self-limiting mechanism on the number of P0 items.

Your job is to be that mechanism.

```
  THE ICE FRAMEWORK:
  Impact (H/M/L): how many users / revenue / engineer-time
  Confidence (0-100%): how confident you are this is the fix
  Ease (days): engineering effort to resolve

  SCORING: roughly rank by (Impact x Confidence) / Ease
  This is a heuristic, not a formula. Use judgment.

  REAL EXAMPLE: 4 competing "P0" items on a Monday morning

  +-----------------------------+--------+------------+------+--------+
  | Item                        | Impact | Confidence | Ease | Order  |
  +-----------------------------+--------+------------+------+--------+
  | DB connection pool alert    | High   | 95%        | 2d   | 1st    |
  | (prevents next SEV2)        |        |            |      |        |
  +-----------------------------+--------+------------+------+--------+
  | Cache pre-warm script       | Medium | 80%        | 1d   | 2nd    |
  | (reduces morning slowness)  |        |            |      |        |
  +-----------------------------+--------+------------+------+--------+
  | Auth migration proposal     | High   | 70%        | 2 wk | 3rd*  |
  | (*needs its own roadmap)    |        |            |      |        |
  +-----------------------------+--------+------------+------+--------+
  | Metrics dashboard refresh   | Low    | 90%        | 3d   | 4th   |
  | (nice to have, not urgent)  |        |            |      |        |
  +-----------------------------+--------+------------+------+--------+

  HOW TO COMMUNICATE THE SEQUENCE:
  "I am prioritizing these in this order: [1, 2, 4, then 3].
   Item 3 is important but too large to be a sprint item --
   I will write the roadmap proposal for it by Thursday.
   Items 1 and 2 will be done by Wednesday.
   Any objections or information I am missing?"

  By making the sequence explicit and asking for input, you:
  - Signal that you have thought about it (not just reacting)
  - Give stakeholders a chance to correct your information
  - Create accountability (you said Wednesday)
  - Prevent the "why isn't this done yet?" conversation
```

---

### Translating Technical Success to Business Terms

Every quarter, staff engineers present results to leadership. The language of leadership is not latency, not throughput, not error rates. It is revenue, retention, operational cost, and risk.

The translation is your job.

```
  FROM TECHNICAL METRIC TO BUSINESS OUTCOME:

  EXAMPLE 1: Latency improvement
  Technical: "We reduced p99 checkout latency from 800ms to 180ms."
  Business:  "A/B testing showed 2.3% higher checkout completion
              when latency is under 200ms. At $10M/month GMV,
              that is $230K/month in additional completed purchases."

  EXAMPLE 2: Reliability improvement
  Technical: "We improved availability from 99.5% to 99.9%."
  Business:  "We went from 43.8 hours of downtime/year to 8.7 hours.
              At our $180K/hour revenue impact during downtime,
              that is $630K/year in protected revenue."

  EXAMPLE 3: Deploy velocity
  Technical: "We reduced deploy time from 2 hours to 20 minutes."
  Business:  "Engineering teams can now ship 4-6 times per day
              instead of once. Our mean time to detect a bug and
              ship a fix dropped from 3 days to 4 hours.
              We estimate this will allow 2 additional features
              per team per quarter, based on Q1 data."

  EXAMPLE 4: Toil reduction
  Technical: "We automated token rotation, saving 2 engineers
              35% of their time."
  Business:  "Two engineers are now available for feature work
              that was previously blocked by auth toil. At loaded
              cost, that is $210K/year of engineering capacity
              redirected from maintenance to growth."
```

---

### Making Decisions Under Incomplete Information

This is the skill nobody talks about because it is uncomfortable to admit: at L6, you regularly have to make decisions where you do not have enough data to be certain. Waiting for certainty is not an option. Every day you delay, the situation is evolving, teams are blocked, and the decision is being made by default.

The instinct of a technically trained person is: "Get more data. Then decide." This works for a research paper. It fails for a production incident at 3 AM, a cross-team architecture choice that has been in review for 6 weeks, and a quarterly planning decision where the context changes monthly.

**The two failure modes:**

```
  FAILURE MODE 1: PREMATURE CERTAINTY
  You decide with 30% of the data because you are
  impatient or overconfident. Result: wrong decision
  + the cost of the reversal.

  FAILURE MODE 2: WAITING FOR CERTAINTY
  You wait until 90% certain before deciding.
  In a fast-moving org, "90% certain" often means
  "the decision has already been made for you by
  circumstances" or "you have been blocked for 6 weeks."
  Result: you are irrelevant to the outcome.

  THE L6 ZONE: decide at 60-70% confidence.
  Confident enough to commit. Not so late you missed the window.
  Make the decision reversible whenever possible.
  Define the signal that would cause you to reverse.
```

**The decision framework for incomplete information:**

```
  STEP 1: NAME WHAT YOU KNOW AND WHAT YOU DON'T

  "I know: the auth service is the bottleneck.
           reads at p99 are 120ms.
           3 incidents last month were auth-related.
   I don't know: whether the bottleneck is the DB or
                 the token validation logic.
                 (I have 2 theories, no data yet.)"

  STEP 2: WHAT IS THE COST OF EACH OPTION IF WRONG?

  "Option A (rewrite token validation):
   Cost if right: 4 weeks of work, problem solved.
   Cost if wrong: 4 weeks wasted. DB is still the
   bottleneck. We are back to square one.

   Option B (add DB read replica):
   Cost if right: 1 week of work, problem solved.
   Cost if wrong: 1 week wasted. Token validation
   is still the bottleneck.

   Option A is 4x more expensive if wrong.
   Unless we have strong reason to believe it is
   the token logic, start with Option B."

  STEP 3: MAKE THE DECISION REVERSIBLE IF POSSIBLE

  "We will add the DB read replica first.
   We will instrument the token validation path in parallel.
   If the replica solves it: done.
   If after 2 weeks the p99 is still >100ms:
   we will then invest in the token validation rewrite."

  STEP 4: SET A DECISION REVIEW DATE

  "We will revisit this in 2 weeks.
   If p99 has not dropped below 80ms, we change course."
```

**The single most important habit:** When you make a decision under uncertainty, write down the assumption your decision depends on. Then check that assumption at the review date. This is the difference between an engineer who learns from decisions and one who makes the same uncertain decisions repeatedly.

**Real example -- Google SRE practice:**

Google's Site Reliability Engineering book documents this as "error budgets." Instead of asking "is this safe to deploy?" (which is unanswerable with certainty), they ask: "How much reliability have we consumed this quarter? Do we have budget left for this risk?" The error budget converts an unanswerable certainty question into a tractable data question. The decision is still uncertain, but the uncertainty is *bounded and explicit*.

---

### The Staff Engineer as Bottleneck: Protecting Your Leverage

There is a trap that catches almost every new staff engineer within 6 months of joining. It happens gradually:

1. You are the most experienced technical person on several initiatives.
2. Teams start coming to you for decisions, reviews, and advice.
3. Your calendar fills up. You have 14 hours of meetings a week.
4. You are now the critical path for 6 different projects simultaneously.
5. Every project slows down because it has to wait for you.
6. You are exhausted, producing nothing yourself, and feel like you are failing everyone.

This is the staff engineer bottleneck trap. And it is not solved by working harder.

```
  THE BOTTLENECK TRAP:

  Week 1: 3 teams come to you for decisions.
  Week 4: 6 teams come to you for decisions.
  Week 8: 10 teams + your own team's work.
  Week 12: You are the critical path for everything.
            Nothing ships without you.
            You are working 60+ hours and falling behind.

  THE TRAP CLOSES HERE:
  If you try to work harder, you become more of the
  bottleneck -- because you are doing more of the work
  that should be done by the teams around you.

  THE COUNTER-INTUITIVE FIX:
  Do LESS. Delegate MORE. Build the capability in others
  so they do not need to come to you.
  This feels wrong in the short term.
  It is correct in the long term.
```

**The three bottleneck types and their fixes:**

```
  TYPE 1: DECISION BOTTLENECK
  Symptom: Every architectural decision waits for you.
  Root cause: Teams do not have clear decision-making
              authority or they lack confidence.
  Fix: Write a decision framework document.
       "For decisions that affect only your team: team
        lead decides.
        For decisions that affect 2-3 teams: team leads
        decide jointly, I consult if asked.
        For decisions with org-wide impact: I drive,
        VP approves.
        When in doubt, use this criteria: [...]"
  Result: Teams decide without you. You are consulted,
          not required.

  TYPE 2: REVIEW BOTTLENECK
  Symptom: Every design doc, major PR, and RFC waits for
           your approval before moving.
  Root cause: Unclear review standards, or fear of making
              a mistake without your sign-off.
  Fix: Write clear review standards ("a design doc is ready
       when it answers these 5 questions"). Identify one
       L5 on each team who can approve team-level design docs.
       Reserve your review for cross-team or org-level changes.
  Result: Your review queue drops by 80%.

  TYPE 3: KNOWLEDGE BOTTLENECK
  Symptom: You are the only person who knows how a critical
           system works. Everyone comes to you for questions.
  Root cause: Knowledge is in your head, not in runbooks,
              architecture docs, or code comments.
  Fix: Write a "how this system works" document.
       Teach one engineer per team the internals.
       Require questions to go to those engineers first.
       Within 3 months, you should rarely be paged for
       questions about systems you did not just build.
  Result: You are no longer the only one who can answer.
```

**Your calendar is your strategy:**

```
  WHAT A STAFF ENGINEER'S WEEK SHOULD LOOK LIKE:

  +-------------------+-------+-----------------------------+
  | Activity          | Time% | What it enables             |
  +-------------------+-------+-----------------------------+
  | Deep work (design,| 30%   | The technical output that   |
  | code, writing)    |       | no one else can do          |
  +-------------------+-------+-----------------------------+
  | Cross-team        | 25%   | Alignment, unblocking,      |
  | collaboration     |       | influence work              |
  +-------------------+-------+-----------------------------+
  | Code reviews /    | 20%   | Multiplying others          |
  | design reviews /  |       |                             |
  | 1:1s              |       |                             |
  +-------------------+-------+-----------------------------+
  | Planning /        | 15%   | Shaping direction           |
  | strategy /        |       |                             |
  | roadmap work      |       |                             |
  +-------------------+-------+-----------------------------+
  | Slack/email/      | 10%   | Communication overhead      |
  | administrative    |       |                             |
  +-------------------+-------+-----------------------------+

  RED FLAGS IN YOUR CALENDAR:
  - Deep work < 20%: you are a manager without the title
  - Meetings > 50%: you are a scheduler, not a builder
  - No blocked 2-hour windows: your best thinking cannot happen
  - No time for 1:1s: you are growing nobody

  HOW TO PROTECT DEEP WORK:
  Block 2-3 hour windows 3x per week. Mark them as "focus
  time" or "project work." Decline meetings during these
  blocks unless they are genuinely urgent (not just
  convenient for the meeting requester).
  This is not rude. This is how you do the work that
  nobody else can do.
```

---

### Real Production Incident 7: Meta's Cross-Team Cache Invalidation (2021)

**What happened:** Meta's content team deployed a new feature that triggered cache invalidation events in the social graph team's service. The social graph team had not been notified of the deployment because neither team knew that the content service was calling the social graph cache internally. The result was a 90-minute degradation in friend recommendation accuracy for millions of users.

**The "Operating Under Pressure" lesson:**

When the incident was declared, the IC faced a pressure-under-fire challenge: nobody had a complete dependency map. No single person in the room knew which services called which other services. The IC was making decisions under genuine uncertainty about who was affected and why.

```
  WHAT THE IC KNEW AT T+0:
  - Friend recommendations degraded
  - Social graph cache hit rate dropped from 95% to 40%

  WHAT THE IC DID NOT KNOW:
  - Why the cache was being invalidated
  - Which team's deploy caused it
  - Which other services might also be affected

  WHAT THE IC DID (operating under this uncertainty):
  T+0:  Declared SEV2. Assigned investigation roles.
        "Two engineers investigate cache invalidation source.
         One engineer monitors blast radius to other services.
         One engineer drafts stakeholder update."
  T+15: Content team deploy identified as the trigger.
        IC made a call without certainty: "Roll back content
        team deploy as a precaution while we investigate.
        If we are wrong, we can re-deploy in 10 minutes."
  T+25: Rollback complete. Cache hit rate recovering.
        Root cause confirmed: content service was calling
        social graph API (nobody knew this call existed).
  T+90: Full recovery. Dependency mapping project started.

  THE KEY DECISION UNDER UNCERTAINTY:
  "Roll back the content deploy" at T+15 was made with
  ~60% confidence. The IC did not have proof. They had
  correlation (deploy time matched the cache drop).
  They made the call anyway because the cost of being
  wrong was low (re-deploy in 10 min) and the cost of
  waiting for certainty was high (continued user impact).
```

**Staff lesson:** Operating under pressure means making time-critical decisions with incomplete information. The practice of "mitigation before root cause" is also the practice of "act at 60% confidence when waiting for 90% is too expensive." The IC at Meta applied this correctly: roll back, validate, investigate -- in that order.

---

### The L5 vs L6 Calibration Table

```
  +---------------------+----------------------------+-----------------------------+
  | Dimension           | L5 (Senior)                | L6 (Staff)                  |
  +---------------------+----------------------------+-----------------------------+
  | Incident Command    | Fixes the problem.         | Delegates the fix to        |
  |                     | Excellent debugger and     | others, runs coordination,  |
  |                     | solver.                    | makes mitigation decisions. |
  |                     |                            | Does NOT debug personally.  |
  +---------------------+----------------------------+-----------------------------+
  | Post-mortem focus   | Finds root cause and       | Finds the systemic gap      |
  |                     | fixes the specific bug.    | that allowed the root cause |
  |                     | Action items are           | to exist. Action items      |
  |                     | individual and specific.   | prevent the class of bug.   |
  +---------------------+----------------------------+-----------------------------+
  | Cross-team block    | Escalates to their         | Works through the influence |
  |                     | manager or waits for       | stack. Rarely needs to      |
  |                     | the block to clear.        | escalate. Volunteers to own |
  |                     |                            | the gap temporarily.        |
  +---------------------+----------------------------+-----------------------------+
  | Stakeholder update  | Technical language,        | Plain English, dollar       |
  |  in incidents       | accurate but not           | figures, impact scope,      |
  |                     | accessible to non-tech     | next update time. Audience- |
  |                     | executives.                | aware.                      |
  +---------------------+----------------------------+-----------------------------+
  | Design review       | Reviews their own design   | Runs reviews of others'     |
  |                     | and adjacent team          | designs. Makes decisions    |
  |                     | designs. Good at finding   | when the room is stuck.     |
  |                     | issues.                    | Gives feedback that         |
  |                     |                            | teaches, not just corrects. |
  +---------------------+----------------------------+-----------------------------+
  | Tech debt           | Files the ticket. Writes   | Writes the business case.   |
  |                     | clear technical            | Gets budget approved.       |
  |                     | description of the         | Breaks it into fundable     |
  |                     | problem.                   | phases. Shows ROI.          |
  +---------------------+----------------------------+-----------------------------+
  | Vision              | Executes on a vision       | Authors the vision. Aligns  |
  |                     | that was handed to them.   | the org around it.          |
  |                     | Very good at it.           | Negotiates the investment.  |
  +---------------------+----------------------------+-----------------------------+
  | Mentorship          | Mentors when asked.        | Proactively identifies who  |
  |                     | Gives good advice.         | needs what kind of growth.  |
  |                     |                            | Builds capability in others |
  |                     |                            | before they ask.            |
  +---------------------+----------------------------+-----------------------------+
  | Code review         | Corrects mistakes clearly. | Teaches the mental model    |
  |                     | Thorough.                  | behind the fix. Engineer    |
  |                     |                            | learns the class, not just  |
  |                     |                            | the instance.               |
  +---------------------+----------------------------+-----------------------------+
  | Under pressure      | Handles urgent things      | Explicitly sequences items  |
  |                     | in order of arrival.       | by importance vs urgency.   |
  |                     | Responsive.                | Communicates the sequence   |
  |                     |                            | to stakeholders.            |
  +---------------------+----------------------------+-----------------------------+
  | Success metric      | "The system is faster."    | "p99 improvement drives     |
  |                     | "Availability is better."  | $230K/month in additional   |
  |                     |                            | checkout completions."      |
  +---------------------+----------------------------+-----------------------------+
  | Hiring signal       | Identifies strong          | Shapes the interview        |
  |                     | candidates.                | process. Raises the bar     |
  |                     |                            | for the team's standards.   |
  +---------------------+----------------------------+-----------------------------+
  | Game days           | Participates actively      | Designs the game day.       |
  |                     | in game days. Good at      | Writes the success          |
  |                     | finding gaps.              | criteria. Converts findings |
  |                     |                            | into permanent improvements.|
  +---------------------+----------------------------+-----------------------------+
```

---

### Brainstorming Questions -- Part 6: Operating Under Pressure

**Q1.** You receive 3 pages simultaneously at 2 PM on a Tuesday:
- Payment service: 5% error rate (increasing)
- Auth service: p99 spiked from 20ms to 2 seconds (stable, not increasing)
- Search service: index build job failed (no user-visible impact yet)

How do you triage? What is your first action? Second?

*Think about: payment service is the most urgent (increasing error rate + revenue impact). Auth p99 spike is serious but stable -- assign it to the auth on-call and monitor. Search index build failure has zero user impact yet -- put it in the queue. You cannot work on all three simultaneously; declare severity on payment immediately and delegate the other two.*

**Q2.** You have been absorbing a cross-team problem for 5 weeks. You are making progress but it is slow. Two engineers on your team have complained that your involvement in this is pulling you away from the team's roadmap. At what point do you escalate, and what do you bring to the escalation?

*Think about: escalate when (a) you have been blocked for 72+ hours with no path, (b) you need resources you cannot allocate, or (c) the situation is worsening. If you are making slow progress, that is not an escalation trigger -- it is a timeline conversation with your team. If you escalate, bring: what you tried, the specific decision you need, and the cost of not deciding by a specific date.*

**Q3.** Leadership asks: "Was the 6-month reliability investment worth it?" You improved availability from 99.5% to 99.9%. Write the 2-paragraph answer you give in the all-hands review.

*Think about: never say "we went from 99.5% to 99.9%." Convert it: from 43.8 hours of downtime/year to 8.7 hours. At $X/hour revenue impact, that is $Y/year in protected revenue. Paragraph 2: what did we learn, and what is the next inflection point we are designing for?*

**Q4.** An engineer on your team is spending 50% of their time on on-call toil. Their feature output has dropped significantly. Their manager says "they just need to work faster." What is your diagnosis, and how do you fix this without being the engineer's manager?

*Think about: the manager is wrong. "Work faster" does not solve toil -- it just burns the engineer out faster. Your diagnosis: the alert threshold is too sensitive, or the system has reliability gaps that generate repeated manual intervention. Your fix: calculate the toil cost in dollars (engineer time x salary), propose a reliability investment, frame it to the manager as "we are spending $X/year on manual work this automation would eliminate." You are not managing the engineer -- you are fixing the system that is eating their time.*

**Q5.** You are asked to give a 10-minute presentation to the C-suite on "the state of our infrastructure." You have an audience that includes the CEO, CFO, CPO, and 3 board observers. How do you structure 10 minutes? What do you say, and what do you not say?

*Think about: 3 minutes on the business outcome (what did the infrastructure enable or protect this quarter, in dollars). 3 minutes on the one risk (what is the single biggest infrastructure risk and what we are doing about it). 2 minutes on investment ask if you have one, in business terms. 2 minutes for questions. What not to say: latency numbers, specific services, architecture jargon. Everything must translate to business impact.*

**Q6.** Your team discovers a serious security vulnerability -- not actively exploited, but exploitable. Fixing it requires 4 weeks of work and will delay a major customer-visible feature that the CEO announced at a conference. What do you do, and in what order?

*(There is a specific right answer: security vulnerabilities of this severity are escalated immediately to security and legal, fix takes priority, customer communication is handled by the communications team. The feature delay is a business decision, but the fix is not negotiable.)*

**Q7.** You are one month into a new staff engineer role at a company. You have not shipped anything yet. Your manager says "when are you going to make an impact?" How do you respond, and is this a reasonable question for month 1?

*Think about: month 1 is legitimately for listening, mapping the landscape, and finding where the highest leverage is. Shipping something in month 1 that fixes a symptom but creates a new problem is worse than shipping nothing. A reasonable answer: "I have identified 3 areas where I think I can make the highest impact. Here is my plan for months 2-3, and here is the metric I will use to show impact by month 4." The manager's question is not unreasonable -- impatience is normal. Your job is to show a clear plan, not to defend doing nothing.*

---

---

## Part 7: The First 90 Days as a Staff Engineer

This section exists because the hardest part of being a staff engineer is often the first 3 months in a new role. The chapter's six skills above describe what you do once you are established. This section covers how to get established.

### Why the First 90 Days Are Different

A senior engineer (L5) can start contributing meaningfully in week 2. They find a codebase, read it, write some code, ship something. The feedback loop is fast and the success signal is clear.

A staff engineer cannot do this. The work is larger, less defined, and dependent on relationships and context that take months to build. The feedback loop is slow. You might spend 6 weeks listening and mapping and feel like you have accomplished nothing -- while actually building the foundation for the next 18 months of high-leverage work.

The danger: impatience leads to premature action. You ship something in month 1 to "show impact." It turns out you misunderstood the context, and the thing you shipped creates a new problem or steps on an existing initiative. You have now made a first impression as someone who acts before listening.

The discipline: earn the right to drive by first understanding what is actually going on.

---

### The 90-Day Map

```
  WEEKS 1-2: LISTEN AND MAP

  Goal: Build the map, not the territory.
  Every conversation is an input. Nothing is an output yet.

  What to do:
  - Meet every team lead whose work you will touch.
    Ask: "What is working well? What is most broken?
    What do you wish someone would fix?"
  - Read the last 12 months of incident post-mortems.
    Patterns in incidents reveal where the bodies are buried.
  - Read the last 3 quarterly planning docs.
    This shows you what leadership thinks is important.
  - Find the "dependency map" or build one:
    which systems depend on which other systems?
  - Find the "unofficial" technical decisions:
    the ones that were made but never written down.
    Ask: "Is there anything that everyone knows but
    nobody has written down?"

  Output: a written landscape doc.
  Not published yet. Just for you.
  "Here is what I understand about the system, the teams,
   the priorities, and the biggest open problems."

  ---

  WEEKS 3-6: IDENTIFY AND VALIDATE

  Goal: Identify where you can have the highest impact.
  Validate that your hypothesis is correct with others.

  What to do:
  - From your landscape doc: list the 5-10 biggest
    gaps or problems.
  - For each: "Is this actually a problem, or just
    technically interesting?" (Only act on problems
    that actually cost the org something.)
  - For each real problem: "Has someone tried to fix
    this before? Why did it fail?"
    (If it failed before, you need to know why before
    you try again.)
  - Share your findings with your manager and 2-3 team
    leads you trust. "Here is what I am seeing. Am I
    missing something important?"

  Output: a "first things" document.
  This is short (1 page). It says:
  "Based on the first 6 weeks, the highest-leverage
   thing I can do is [X]. Here is why I believe that.
   Here is what I will do in months 2-3.
   Here is how I will measure impact."

  Share this with your manager. Get alignment.
  This becomes your contract for the next 6 months.

  ---

  WEEKS 7-12: DELIVER THE FIRST WIN

  Goal: Ship something concrete that validates your judgment.

  What to do:
  - Execute on the "first things" document.
  - The first win should be: visible, real, and
    representative of the kind of work you will do.

  GOOD FIRST WINS:
  - Run a design review on a major decision and make
    the design measurably stronger
  - Write and get adopted a technical standard that
    3+ teams need
  - Identify and fix a systemic incident pattern
    (like the N+1 CI tooling example)
  - Build the cross-team dependency map that everyone
    knows is missing

  BAD FIRST WINS:
  - Rewriting something that was already working
    (no visible improvement, high disruption risk)
  - Shipping a feature yourself (that is an individual
    contributor win, not a staff win)
  - Mandating an org standard before you have credibility
    (people will resist; you will spend 6 months fighting)
```

---

### The 3 Failure Modes in the First 90 Days

**Failure mode 1: The "I'll just fix it" trap**

New staff engineer joins. Sees a well-known problem. Fixes it themselves in week 2. Feels great.

Problem: they did not understand *why* the problem was not already fixed. Maybe there is a cross-team dependency. Maybe a previous fix created a regression. Maybe the team was already planning to fix it differently. By acting before listening, they created confusion and may have stepped on someone else's work.

Fix: Before fixing anything, ask "why hasn't this been fixed already?" The answer is almost always more interesting than the problem itself.

---

**Failure mode 2: The "I'm still learning" trap**

New staff engineer joins. Listens carefully. Month 3 arrives. Month 6 arrives. They are still "learning the codebase." They have shipped nothing.

This is the opposite failure. Listening is not an end state. It is a means to acting well.

The discipline: by week 6, you should have a hypothesis about where you can have impact. By week 12, you should have delivered the first win. If you are at month 4 with nothing shipped, something is wrong and you need to have an honest conversation with your manager about what is blocking you.

---

**Failure mode 3: The "everybody's best friend" trap**

New staff engineer joins. Everyone asks for their time. They say yes to every review, every meeting, every "quick question." By month 2, their calendar is full and their own work is not happening.

This is the bottleneck trap early. The fix is the same: protect your deep work time from week 1. "I have focus time blocked on Tuesday and Thursday mornings. For anything time-sensitive, here is who else can help."

---

### What to Say in Your First All-Hands Presentation

Most new staff engineers are asked to give a brief introduction or "where I've been, what I'm focusing on" update in their first all-hands.

```
  THE WRONG APPROACH:
  "I've been meeting everyone and learning the systems.
   It's been great so far. I'm looking forward to
   contributing more in the coming months."

  This communicates: nothing. Nobody knows why you are here
  or what you are going to do.

  THE RIGHT APPROACH:
  "In my first 6 weeks, I spent time with every team
   that touches [your area]. Here is what I heard most
   consistently: [the 1-2 biggest themes, in plain English].

   Based on that, I am focusing on [the first things doc
   summary -- one sentence].

   My goal for the next quarter is [specific, measurable].
   I will share progress at the Q3 all-hands.

   Three people I owe a huge thanks to for the onboarding:
   [names]. They showed me where the real work happens."

  This communicates:
  - You listened to the org before acting (credibility)
  - You have a focus (accountability)
  - You will measure it (reliability)
  - You are building relationships (cultural fit)
```

---

### Brainstorming Questions -- Part 7: First 90 Days

**Q1.** You are 4 weeks in. Your manager asks "what are you planning to work on?" You are still in listening mode. What do you say?

*Think about: share what you have heard so far (the landscape as you understand it), share your hypotheses about where the highest leverage is, and share when you will have a concrete first-things document. "I am not sure yet" is honest but not sufficient. "Here is what I'm seeing, and here is my working hypothesis" is better.*

**Q2.** Two weeks in, you discover that a major project you were hired to lead is already in progress under a different engineer's ownership. Nobody told you. What do you do?

*Think about: talk to the engineer first (before your manager). Understand what they are doing, where they are, and what they think they need. The question is not "who owns this" -- it is "how do I add value to this that the engineer currently leading it cannot provide?" Maybe you run design reviews, help with cross-team alignment, or own a specific component. Go with a specific offer, not a territorial question.*

**Q3.** At month 3, you have built good relationships and written a thorough landscape document, but your manager says "you are not making enough impact." What is the disconnect, and how do you address it?

*Think about: the disconnect is likely that your manager is measuring visible output (shipped features, resolved incidents) while you have been producing invisible output (context, relationships, planning). Neither is wrong but they need to be aligned. Translate your invisible work to visible outcomes: "Here is the decision I shaped that prevented 3 weeks of rework. Here is the design review that caught a data loss bug before production." Then agree on what visible impact looks like for month 4.*

---

## Exercises (Fully Worked)

### Exercise 1: Incident Timeline Construction (45 minutes)

**The scenario:**

You are IC for the following incident. Read the raw events and reconstruct:
(a) The correct severity level and why
(b) The stakeholder update you send at T+20 minutes
(c) The rollback decision (yes/no and why)
(d) Three systemic action items for the post-mortem

**Raw events (in order):**
- 2:03 AM: Alert fires. "payment-api: error_rate > 5%"
- 2:05 AM: Error rate now 28%
- 2:07 AM: Last deploy was at 11:45 PM (2 hours, 20 min ago)
- 2:08 AM: DB CPU: 85% (normal: 25%)
- 2:09 AM: DB connection pool: 490/500 (normal: ~80)
- 2:10 AM: Revenue impact estimate: ~$240K/hour at current traffic
- 2:12 AM: DB query logs show a new `SELECT * FROM line_items WHERE order_id IN (...)` pattern -- executes one query per order
- 2:15 AM: Engineer on DB team confirms: this pattern processes 200 line items per order. At current QPSr it generates ~3,600 extra queries/second
- 2:20 AM: Stakeholder update time
- 2:28 AM: Rollback of 11:45 PM deploy completes. DB CPU drops to 30%. Pool: 85/500.
- 2:32 AM: Error rate: 0%. Service fully recovered.

**Expected answers:**

(a) **Severity: SEV2.** Major feature (payments) down for a significant percentage of users. Revenue impact is high ($240K/hour) but the product is not completely down. Upgrade to SEV1 if duration exceeds 30 minutes with no mitigation path. (It resolved in 25 minutes, so SEV2 was correct.)

(b) **Stakeholder update at T+20 (2:23 AM):**
```
  SEV2 UPDATE -- Payment Service -- 2:23 AM

  WHAT IS HAPPENING:
  Payment processing is failing for ~28% of requests.
  Started at 2:03 AM. Ongoing for 20 minutes.

  IMPACT:
  ~$240K/hour in failed transactions at current traffic.
  Browse, search, and account functions are NOT affected.

  WHAT WE ARE DOING:
  Rolling back the 11:45 PM deploy. The rollback is in
  progress and expected to complete in the next 5 minutes.
  Expected full recovery: 2:30-2:35 AM.

  NEXT UPDATE: 2:30 AM or upon resolution.

  -- [Your name], Incident Commander
```

(c) **Rollback: YES.** Deploy was 2 hours ago. DB metrics degraded after deploy (confirmed by the N+1 query pattern in the deploy). Rollback is safe (no schema migration in the deploy, based on the query log analysis). The rollback decision could have been made at 2:10-2:12 AM when the deploy correlation was confirmed, rather than waiting until 2:28. A 6-minute improvement here.

(d) **Three systemic action items:**

1. **CI N+1 detection:** "The N+1 query pattern (1 query per order, with 200 line items per order) was undetectable in staging because staging has only 5-10 line items per order. Add automated query analysis to CI that detects 'query inside loop' patterns before merge. Tool: sqlfluff or a custom AST check."

2. **DB connection pool alert:** "Alert fired at 5% error rate. By then, the connection pool was at 490/500. Add a pre-emptive alert: 'connection pool > 70% for 5 minutes.' This would fire at ~2:04 AM with the DB at 70%, giving 5-8 minutes more time before user-visible errors."

3. **Staging data volume test:** "Staging uses 5 items per order. Production averages 200. The N+1 pattern is invisible in staging at 5 items but catastrophic at 200. Add a 'high-volume data' CI test environment that mirrors production data density. This class of bug requires production-scale data to surface."

---

### Exercise 2: The Influence Map (45 minutes)

**The scenario:**

You need 4 teams to adopt a new distributed tracing standard by Q4. The standard (OpenTelemetry) adds 1.5ms overhead to every request but provides full request tracing across all services. Without it, debugging cross-service incidents takes 4x longer.

**Team profiles:**
- **Team A (Payments):** Measured on checkout conversion rate and p99 latency. Currently at 150ms p99. SLA is 200ms. 1.5ms overhead is uncomfortable.
- **Team B (Recommendations):** Measured on ML model relevance (offline metric) and infra cost (OKR: reduce log storage 20% by Q4). Team is understaffed.
- **Team C (Mobile API):** Enthusiastic. Team lead already uses distributed tracing on a personal project. Team OKR: "improve debuggability of mobile incidents."
- **Team D (Auth):** Has its own internal tracing system built 3 years ago. Team lead believes it is superior. Team is proud of it.

**Work through:**

(a) Draw the influence map: who is champion, blocker, neutral, decision maker?
(b) For Teams A and D specifically, walk through the influence stack (levels 1-4)
(c) What do you do if Teams A and D still say no at month 2?

**Expected answers:**

(a) **Influence map:**
```
  Champion: Team C (already aligned, can advocate internally)
  Blocker:  Team D (has invested alternative, status quo bias)
  Neutral:  Team B (understaffed, not opposed, just not prioritizing)
  Potential Blocker: Team A (latency concern is real)
  Decision Maker: Depends on org. If this requires a standard,
                  VP Eng is decision maker. If voluntary,
                  team leads are decision makers.
```

(b) **Team A influence strategy:**

Level 1 (incentives): Team A is measured on p99 latency and checkout conversion. Your opener: "I know you are watching every millisecond. Before we talk about the 1.5ms overhead, I want to show you the data from the last 3 cross-service payment incidents. In each one, finding the root cause took 4+ hours because we had no tracing. With tracing, our estimate is 45-minute MTTR. For a team measured on conversion rate, a 4-hour incident is much more expensive than 1.5ms."

Level 2 (find the champion): Who on Team A has been most frustrated by long incident investigations? Find that person. Share the data with them. Ask them to bring it up internally.

Level 3 (data): Show the latency impact vs incident cost. If Team A had 3 incidents in the last 6 months averaging 4 hours each, and Team A has 4 engineers, that is 48 engineer-hours = ~$36K. The 1.5ms overhead at their traffic (assume 100K req/sec) adds 150K ms of latency per second -- but this is latency that users wait for, not engineer time. These are incommensurable numbers: the relevant comparison is 1.5ms added per request vs faster incident resolution that protects their conversion rate SLA.

Level 4 (make it easy): Offer to do the integration for Team A yourself, or provide a PR that integrates OpenTelemetry into their service with a feature flag so they can turn it off if it causes issues.

**Team D influence strategy:**

Level 1 (incentives): Team D is proud of their internal system. They believe it is superior. Your opener is not "our standard is better." It is: "Help me understand what your system does that OpenTelemetry doesn't. I want to evaluate whether there are things we should incorporate into the standard." This disarms the defensive stance.

Level 2 (find the champion): Is there anyone on Team D who has worked at a company that used OpenTelemetry? Someone who knows its ecosystem and plug-in support?

Level 3 (data): The internal system works for Team D but does not interoperate with other teams' services. Whenever an incident spans Team D and another team, the traces stop at the service boundary. Build the data: how many cross-service incidents touched Team D in the last 6 months? How much longer did they take to debug?

Level 4 (make it easy): Propose a bridge: Team D keeps their internal system but exports data in OpenTelemetry format. This preserves their investment while allowing interoperability. "You keep building your system. We add an exporter so the rest of the org can see your traces too. Best of both worlds."

(c) **If Teams A and D still say no at month 2:**

For Team A: Present the data at a quarterly review showing that the 3 cross-service incidents cost $X in on-call time and potentially $Y in conversion impact during the outages. Ask: "Is $X + $Y greater than the value of the 1.5ms we save by not adopting?" If yes, the business case has been made. If they still say no, you need VP alignment.

For Team D: Escalate only if this is preventing incidents from being debugged in ways that have measurable business impact. Bring the VP the specific data: "Team D's internal tracing system created a 6-hour incident investigation blind spot in [incident]. Cross-service tracing would have reduced this to 45 minutes. We estimate the cost of this gap is $X/year. I need a decision on whether Team D's internal system needs to export to a common standard."

---

### Exercise 3: Business Case (45 minutes)

Write the business case for a 5-month auth service refactor given these inputs:
- 3 engineers spend 30% of time on auth toil
- 5 incidents/month attributable to auth, avg 3 hours each, 2 engineers each
- Senior engineer loaded salary: $280K/year
- The mobile team's Q4 OKR (face/fingerprint auth) is blocked by auth service API limitations
- The mobile team has 3 engineers building toward this OKR for 8 weeks -- they have made partial progress but are blocked on the last 40% of the work
- Payment team ships 10 features/year that touch auth, each takes 3 extra weeks
- Engineer-week cost: $280K / 52 = ~$5,400
- The refactor requires: 3 engineers for 5 months

**Expected calculation:**

Toil cost: 3 engineers x 0.30 x $280K = $252,000/year

Incident cost: 5 incidents/month x 12 x 3 hours x 2 engineers x ($280K / 2,000hr) = 5 x 12 x 3 x 2 x $140 = $50,400/year

Velocity tax (payment team): 10 features x 3 weeks x $5,400/week = $162,000/year

Mobile team OKR at risk: 3 engineers x 8 weeks x $5,400/week = $129,600 already spent; 40% blocked = $51,840 of that is wasted if OKR fails. Plus the business impact of not shipping the OKR (revenue from face auth, competitive positioning) -- estimate conservatively or acknowledge this is unmeasured.

Refactor cost: 3 engineers x 5 months x (280K / 12) = 3 x 5 x $23,333 = $350,000

**The table:**
```
  +----------------------------------+-------------+-----------+
  | Annual Cost of Not Acting        | Per Year    | 3-Year    |
  +----------------------------------+-------------+-----------+
  | Engineer toil                    | $252,000    | $756,000  |
  | Incident response                | $50,400     | $151,200  |
  | Velocity tax (payment team)      | $162,000    | $486,000  |
  +----------------------------------+-------------+-----------+
  | TOTAL ANNUAL ONGOING COST        | $464,400    |$1,393,200 |
  +----------------------------------+-------------+-----------+
  | One-time cost of refactor        | $350,000    | n/a       |
  | Mobile OKR already at risk       | ~$52K waste | n/a       |
  +----------------------------------+-------------+-----------+

  ROI: Refactor pays for itself in 9 months.
       Years 2-3 net savings: $928,000 over 2 years.
       Total 3-year benefit of acting now vs. not:
       $1,393,200 - $350,000 = $1,043,200 net.
```

**The one-paragraph ask:**
"I am requesting 3 engineers for 5 months to refactor the auth service. The current auth service costs us $464K/year in toil, incidents, and velocity tax, and is blocking the mobile team's Q4 OKR (which has already absorbed $52K of investment). The refactor costs $350K and pays for itself in 9 months. Over 3 years, acting now saves $1M net compared to not acting. I can break this into 3 independently valuable phases. If I deliver phase 1 (automated token rotation) in 6 weeks, you will see toil drop from 30% to 12% of 3 engineers' time -- measurably, within 6 weeks of the refactor starting."

---

### Exercise 4: Design Review Feedback (30 minutes)

**The design:** A junior engineer proposes storing all user session data in a Redis instance with the following properties:
- Single Redis node, no replication, no clustering
- All API requests make a synchronous Redis call to validate the session
- Session TTL: 30 days (every session key has a 30-day expiry)
- No fallback if Redis is unavailable

Apply the 5-question framework. Prioritize the most critical issue. Teach the why.

**Expected feedback (in priority order):**

**Issue 1 (Critical -- Blast Radius):** "What happens when this Redis instance is unavailable? Every API request makes a synchronous session validation call. If Redis is down for any reason -- network partition, memory pressure, instance failure -- 100% of authenticated requests fail immediately. This is a complete service outage from a single component failure. The fix options are: (a) Add a replica with automatic failover (Redis Sentinel or Redis Cluster), (b) Add a local in-memory cache as a fallback so requests can continue for a short window even if Redis is unreachable, or (c) Make the session validation call non-blocking with a reasonable timeout and a sensible failure mode ('if session validation times out, allow the request but log it'). Which failure mode does the product require?"

**Issue 2 (Scalability):** "At 10x users, you have 10x sessions. 30-day TTL means sessions accumulate. If you have 1M active users each with up to 5 active sessions (mobile, web, tablet, etc.), that is up to 5M keys in Redis, each storing session data. What is the average size of your session data? If it is 1KB per session, that is 5GB -- fine for a single Redis node. But this should be documented and monitored. When does the Redis node need to be upgraded? Add a metric: 'Redis memory utilization as % of limit, with alert at 70%.'"

**Issue 3 (Availability SLA):** "A single Redis node with no replication has availability limited by the instance uptime. AWS reports single-instance Redis availability at ~99.9% (about 8.7 hours of downtime per year). Is that acceptable for session validation, which blocks all authenticated requests? If your availability SLA is 99.99%, you need replication and automatic failover."

**Issue 4 (Operational/Rollback):** "What is your recovery plan if a bug in the session format is deployed and you need to roll back? 30-day TTL means old sessions will still be in Redis for up to 30 days after a rollback. If the new session format is incompatible with the old code, rolling back the application code will cause the old code to fail to parse sessions written by the new code. Document the session format clearly, use a version field in the session data, and handle unknown versions gracefully."

---

### Exercise 5: Promotion Assessment (20 minutes)

**Engineer profile (L5, being considered for L6 promotion by their manager):**
- Led the migration of the payment service from one database vendor to another over 8 months. No production incidents during migration.
- Drove adoption of a new API versioning standard across 2 teams (3rd team declined, engineer did not escalate)
- Has a weekly "office hours" for junior engineers. 4 junior engineers have said this helped them.
- Identified and proactively fixed a N+1 query class across 6 files (not just their own service)
- Has not written a technical vision document
- Has not run a post-mortem where the action items prevented recurrence at the class level
- Cross-team influence attempts have been limited to 2 teams; has not influenced at the org level
- Reviewed 15-20 PRs per week consistently

**Assessment: Ready for L6? What is the specific gap?**

**Expected assessment:**

Not ready yet, but trajectory is strong. The specific L6 gap: scope of impact and influence reach.

The database migration and the N+1 fix across 6 files are L5 signals: high-quality, cross-team execution on a specific task. The API versioning standard is an L6 attempt -- but it stopped at 2 teams. The third team declined and the engineer did not pursue it further. An L6 engineer would have continued through the influence stack or made a documented decision about when to escalate vs accept.

The missing L6 signals:
1. No technical vision document -- a document that sets direction for the org rather than executing on direction set by others
2. Post-mortems have been technically correct but have not driven systemic change (the N+1 fix is a good sign, but it was in code, not in the CI pipeline/process)
3. Influence reach is 2 teams -- L6 typically requires demonstrated influence across 3+ teams or at the org level

**Growth plan for the next 2 quarters:**
- Write a technical vision document for one system they own. The doc should propose a 12-month direction and get it accepted by leadership.
- Lead a post-mortem where the action items are systemic (tooling, automation, process) and measurable -- and then verify 3 months later that the action items prevented recurrence.
- Pursue the 3rd team on the API versioning standard. Document what level of the influence stack you reached. If you escalate to leadership, do it with a written business case.

---

## Homework

### Short (30-45 minutes each)

**1. Post-mortem audit:**
Find any public post-mortem (Cloudflare, GitHub Status, AWS, Slack all publish them). Read it carefully. Then write:
- The action item that was listed
- Whether it fixes the instance or the class
- The systemic action item that would fix the class (the one they should have written)

**2. Business case translation:**
Pick one piece of tech debt you know about personally. Calculate:
- Annual cost (toil + incidents + velocity tax)
- Fix cost (engineering time)
- Payback period
Write it in 3 bullet points, each with a number. No adjectives.

**3. Design review practice:**
Take any technical design you have been involved with recently. Apply the 5-question framework to it. Write the feedback you *should have given* (or should give now) for each question where the design has a gap.

---

### Deep (2-4 hours each)

**1. Technical vision document:**
Write a 1-year technical vision document for a system you know well. Use the template from Part 4. Include: current state with data (not adjectives), target state with specific measurable goals, gap analysis with ordering, migration path in phases, investment ask with ROI calculation.

**2. Influence campaign design:**
Choose a real or realistic cross-team technical initiative (adopt a new standard, deprecate a shared library, align on a data model). Draw the full influence map. Write the strategy for each team using the 5-level stack. Include: what you say at each level, how you know when a level has failed, and what the escalation memo looks like if you reach Level 5.

**3. Game day design:**
Design a complete game day for a system you know. Include:
- Failure scenario (be specific)
- Pre-conditions and timeline
- Success criteria (specific, measurable)
- Expected gaps (at least 3 runbook gaps you predict finding)
- Post-game-day retrospective format
- The first complete page of the runbook you would update after the game day

---

## Glossary

**ADR (Architecture Decision Record):** A short document (1 page) that records a specific technical decision permanently -- the context, what was decided, what was rejected, and when to revisit. Written *after* a decision is made, for future engineers who need to understand why things are the way they are.

**Bar raiser:** A staff or senior staff engineer who serves as an independent check on the hiring bar in an interview loop. Can veto a hire even if all other interviewers voted yes. Used when the rest of the loop is inflating their assessment due to enthusiasm for one strong area.

**BGP (Border Gateway Protocol):** The routing protocol of the internet. Routers exchange BGP announcements to say "I can reach these IP addresses via this path." A misconfigured BGP announcement can hijack traffic globally.

**Blameless post-mortem:** A post-mortem that identifies system-level failures as root causes, not individual engineer errors. The test: would your action items prevent this incident from recurring even if a different engineer were on call?

**Blast radius:** The scope of user and system impact when a component fails. A staff engineer always defines blast radius *before* shipping anything significant.

**Bottleneck trap:** The state a staff engineer falls into when they become the critical path for too many decisions, reviews, and projects simultaneously. Symptoms: calendar > 50% meetings, teams waiting on you, deep work time < 20%. Fix: delegate decisions, build review capacity in others, write decision frameworks so teams can self-serve.

**Chaos engineering:** The practice of intentionally introducing controlled failures into production systems to find weaknesses before uncontrolled failures do. Netflix Chaos Monkey is the canonical example.

**Champion (in influence strategy):** A person on another team who already agrees with your proposal and can carry the message internally. People trust their teammates more than they trust outsiders. Finding the champion is Level 2 of the influence stack.

**Conway's Law:** "Organizations which design systems are constrained to produce designs which are copies of the communication structures of these organizations." If you want a different architecture, you may need to change the team structure first.

**Design review:** A structured evaluation of a technical design before implementation begins. Purpose: find correctness, scalability, blast radius, and rollback issues while change is cheap.

**Error budget:** A reliability practice (originated at Google SRE) that frames reliability questions as: "How much downtime are we allowed this quarter, and how much have we used?" Converts unanswerable certainty questions ("is this safe to deploy?") into tractable budget questions ("do we have budget for this risk?").

**Game day:** A scheduled rehearsal of a production failure. The on-call engineer responds to a real (controlled) failure to test runbooks, alerting, and response processes. The only person not told in advance is the on-call engineer.

**Growth plan:** A written quarterly document co-authored by the mentor and the engineer, capturing current strengths, development areas, specific growth targets, and the mentor's commitments. Co-authoring is essential -- an engineer who writes their own growth plan is 3x more likely to act on it than one who receives it from above.

**ICE scoring:** A prioritization heuristic: Impact x Confidence / Ease. Used to rank competing technical items when resources are limited. A heuristic, not a formula -- use judgment to adjust.

**Incident Commander (IC):** The engineer who coordinates an incident response. The IC makes decisions and assigns roles but does NOT personally debug or fix the problem. Most difficult adjustment for great individual contributors moving to staff level.

**Influence stack:** The five levels of cross-team influence to try in order before escalating to a VP: (1) understand their incentives, (2) find the champion, (3) use data and cost of inaction, (4) make it trivially easy to say yes, (5) executive mandate. Start at Level 1 every time.

**N+1 query:** A database anti-pattern where 1 query fetches N parent records, then N more queries fetch child records one at a time. Fix: use a JOIN or a batch fetch to reduce to 1-2 queries. Dangerous because it is invisible in test environments with small datasets but catastrophic in production with large datasets.

**Ownership gap:** A gap between two teams -- an interface, service, or process that neither team officially owns. When it breaks, both teams say "that's not ours." The L6 move: volunteer to own it temporarily while driving a permanent ownership conversation.

**OpenTelemetry:** An open standard for distributed tracing, metrics, and logging. Allows observability data to be collected consistently across services from different teams and languages.

**RFC (Request for Comments):** A document that proposes a cross-team technical standard, API contract, or architectural decision and solicits feedback before committing to a direction. Written by L5 or L6 engineers, audience is all affected teams.

**RTO / RPO:** Recovery Time Objective (how long you can be down) and Recovery Point Objective (how much data you can lose) in a disaster scenario. Both should be defined before a system goes to production.

**SEV1 / SEV2 / SEV3:** Severity levels for production incidents. SEV1: core product down for all users, executives notified every 10 minutes. SEV2: major feature or significant percentage of users affected, stakeholders updated every 15-30 minutes. SEV3: minor degradation with workaround, end-of-day summary.

**Technical debt:** Implementation or design shortcuts taken for speed, which create ongoing maintenance cost and velocity tax. Not inherently bad -- bad when unacknowledged or not paid down strategically. Must be expressed in dollars to get funded.

**Technical vision document:** A 12-36 month technical direction paper that proposes where the technical foundation needs to go, includes a business case, and requests a specific investment. Written by staff engineers, approved by leadership. The key section is "risks of inaction" -- expressed in annual cost, not adjectives.

**Toil:** Repetitive, manual operational work that scales with traffic rather than with engineering investment. Toil is work that could be automated. It is the enemy of leverage. Convert toil to dollar cost (engineer time x salary) to get it funded for elimination.

**Velocity tax:** The extra engineering time required per feature because the underlying system is complex, brittle, or poorly documented. A form of tech debt cost. Example: "every feature touching the auth service takes 3 extra weeks" -- those 3 weeks per feature, summed across the year, is the velocity tax.

---

*Chapter 12b complete.*
