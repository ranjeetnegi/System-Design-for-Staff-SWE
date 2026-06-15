# Chapter 40 -- Deployment Strategies and Operations
### Blue-Green, Canary, Observability, SLOs, and Running Production Systems at Scale

> "Hope is not a strategy. Runbooks are."
> -- Every on-call engineer who survived their first 3 AM page.

---

## Table of Contents

1. Chapter Introduction + Quick Visual
2. Blue-Green Deployment
3. Canary Deployment
4. Runbooks and Incident Response
5. Observability: Logs, Metrics, and Traces
6. SLOs, SLIs, and Error Budgets
7. Capacity Planning
8. Cost Modeling
9. Rollback Strategies
10. How Your Thinking Evolves: Intern to Staff
11. L5 vs L6 Calibration Table
12. Named Production Incidents (5)
13. Brainstorming Questions (20+)
14. Exercises (6)
15. Homework

---

## 1. Chapter Introduction

### What this chapter is really about

Software that is never deployed is software that has never existed for your users.
The code you write on your laptop means nothing until it is running in production,
serving real traffic, handling real failures, being monitored by real dashboards.

The gap between "code is done" and "code is safely running in production for
millions of users" is what this chapter covers. That gap is where L5 engineers
struggle and L6 engineers shine.

Think of it this way. A chef can learn to cook an amazing dish. But running a
restaurant is a completely different skill -- managing the kitchen during dinner
rush, handling a stove fire without panicking, knowing when to 86 a menu item,
tracking food costs per plate so the restaurant stays profitable. The dish is
the code. Running the restaurant is operations.

This chapter teaches you the restaurant operations of software engineering.

### The nine skills of production operations

```
+---------------------------------------------------------------------+
|              THE NINE SKILLS OF PRODUCTION OPERATIONS              |
+---------------------------------------------------------------------+
|                                                                     |
|  DEPLOY SAFELY           DETECT PROBLEMS        RESPOND FAST        |
|  +-----------------+     +-----------------+    +----------------+  |
|  | Blue-Green      |     | Logs            |    | Runbooks       |  |
|  | Canary          |     | Metrics         |    | Incident Mgmt  |  |
|  | Rollback Plan   |     | Traces          |    | Postmortems    |  |
|  +-----------------+     +-----------------+    +----------------+  |
|                                                                     |
|  PLAN FOR SCALE          UNDERSTAND COST        COMMIT TO TARGETS   |
|  +-----------------+     +-----------------+    +----------------+  |
|  | Capacity Plan   |     | Unit Economics  |    | SLOs / SLIs    |  |
|  | Load Testing    |     | Cost Modeling   |    | Error Budgets  |  |
|  +-----------------+     +-----------------+    +----------------+  |
|                                                                     |
|  A junior engineer knows: "my code deploys and my tests pass."      |
|  A Staff engineer knows: all nine columns above AND how they        |
|  interact. A bad deployment is caught by observability. A runbook   |
|  guides the rollback. The rollback is constrained by the SLO.       |
|  The SLO is informed by capacity. Capacity drives cost.             |
+---------------------------------------------------------------------+
```

---

## 2. Blue-Green Deployment

### The analogy: switching railroad tracks

Imagine a commuter train is on Track A pulling into the station. While the train
is running, mechanics need to replace a faulty section of Track A. They cannot
stop the train mid-route -- passengers are on board.

So they lay a brand new Track B in parallel. They verify Track B is safe, test
every connection, confirm it leads to the right destination. Then -- with one
switch throw -- all new trains route to Track B. Track A now sits empty. If
Track B has a problem, one switch throw sends trains back to Track A.

That is Blue-Green deployment. Your users are the passengers. Track A is your
current production environment. Track B is the new version you built and tested.
The switch is your load balancer. The old track stays intact until you are
certain the new one works.

### What blue-green looks like in a real system

```
+---------------------------------------------------------------------+
|                  BLUE-GREEN DEPLOYMENT FLOW                         |
+---------------------------------------------------------------------+
|                                                                     |
|  BEFORE CUTOVER:                                                    |
|                                                                     |
|  [Users]                                                            |
|     |                                                               |
|     v                                                               |
|  [Load Balancer] -----> [BLUE: v1.2 running, 100% traffic]          |
|                                                                     |
|  [GREEN: v1.3 deployed, 0% traffic, being tested]                   |
|                                                                     |
|  -------------------------------------------------------------------  |
|                                                                     |
|  CUTOVER (one config change):                                       |
|                                                                     |
|  [Users]                                                            |
|     |                                                               |
|     v                                                               |
|  [Load Balancer] -----> [GREEN: v1.3, 100% traffic]                 |
|                                                                     |
|  [BLUE: v1.2 idle, kept warm for rollback]                          |
|                                                                     |
|  -------------------------------------------------------------------  |
|                                                                     |
|  ROLLBACK (if green has problems):                                  |
|                                                                     |
|  [Load Balancer] -----> [BLUE: v1.2, 100% traffic again]            |
|  (switch flips back -- usually under 60 seconds)                    |
|                                                                     |
+---------------------------------------------------------------------+
```

### The four steps every blue-green deployment follows

**Step 1 -- Build the green environment.**
Provision servers, containers, or Kubernetes pods with the new version. Do not
touch blue. Run all smoke tests against green while zero real traffic touches it.

**Step 2 -- Verify green is healthy.**
Run integration tests. Check that green can reach the database. Confirm
configuration is correct. This is the step most teams rush and then regret.

**Step 3 -- Shift traffic.**
Change one value in your load balancer config: route to green instead of blue.
This should take under five seconds. If it takes longer, your deployment
infrastructure is too manual.

**Step 4 -- Monitor, then clean up.**
Watch error rates, latency, and business metrics for 15-30 minutes. If
everything is green (no pun intended), decommission blue. Keep the blue
environment warm for at least 24 hours in case a slow problem surfaces.

### When to use blue-green deployment

Blue-green is the right tool when:

- Your deployment unit is the entire application, not individual services.
- You can afford to run two full environments simultaneously (2x cost for the
  overlap window, usually 1-2 hours).
- You need instant rollback capability -- seconds, not minutes.
- Your database schema changes are backward-compatible (both v1.2 and v1.3 can
  read the same tables without conflict).

Blue-green is the wrong tool when:

- Your database schema is changing in a way that v1.2 cannot read (you need to
  run a migration strategy like expand-contract first).
- You cannot afford 2x infrastructure cost even temporarily.
- Your services are so fine-grained (hundreds of microservices) that the concept
  of "two full environments" is impractical.

### The database problem that breaks blue-green if you ignore it

Most engineers understand the "switch the load balancer" part. The part that
bites them: the database.

Both your blue and green environments share the same database during the cutover
window. If your new code (green v1.3) adds a column called `user_tier` to the
`users` table, but your old code (blue v1.2) does not know that column exists,
you have a problem during rollback. If v1.3 writes `user_tier` values and you
roll back to v1.2, your v1.2 code may error when it sees a column it does not
recognize, or lose data written by v1.3.

The solution is the **expand-contract pattern**:

```
+---------------------------------------------------------------------+
|                THE EXPAND-CONTRACT PATTERN                          |
+---------------------------------------------------------------------+
|                                                                     |
|  PHASE 1 -- EXPAND (deploy with old code still running):            |
|  - Add new column user_tier (nullable, no default required)         |
|  - Old code ignores it. New code writes it.                         |
|  - Both versions work against the same schema.                      |
|                                                                     |
|  PHASE 2 -- MIGRATE (after full cutover to new code):               |
|  - Backfill user_tier for existing rows                             |
|  - Add NOT NULL constraint if needed                                |
|                                                                     |
|  PHASE 3 -- CONTRACT (cleanup):                                     |
|  - Remove any columns old code needed that new code no longer does  |
|  - Old code is long gone. Safe to clean up.                         |
|                                                                     |
|  This is the only safe way to change schema with zero downtime.     |
+---------------------------------------------------------------------+
```

### Blue-green trade-offs at a glance

```
+----------------------------+------------------------------------------+
|  ADVANTAGE                 |  DISADVANTAGE                            |
+----------------------------+------------------------------------------+
|  Instant rollback          |  2x infrastructure cost during overlap   |
|  Zero user-visible         |  Database schema must be compatible      |
|  downtime during           |  across both versions                    |
|  cutover                   |                                          |
|  Full environment          |  Does not help you catch bugs that       |
|  testing before any        |  only appear under real production       |
|  real traffic              |  load patterns                           |
|  Simple mental model       |  Full environment = more infra to        |
|  (binary: old or new)      |  manage and keep in sync                 |
+----------------------------+------------------------------------------+
```

---

## 3. Canary Deployment

### The analogy: the coal mine bird

Coal miners used to bring canary birds underground. Canaries are extremely
sensitive to toxic gases like carbon monoxide. If the gas concentration reached
a dangerous level, the canary would show distress or die before the gas affected
the humans. The miners got an early warning signal and could evacuate.

Canary deployment works the same way. You send a small percentage of real traffic
to your new version first -- maybe 1%, maybe 5%. The canary (new version) gets
exposed to the real production environment with real users. If something bad
happens -- errors spike, latency increases, payments fail -- it affects a small
number of users and triggers an alert, not a full outage. You pull back before
the damage spreads to everyone.

### What canary deployment looks like

```
+---------------------------------------------------------------------+
|                    CANARY DEPLOYMENT FLOW                           |
+---------------------------------------------------------------------+
|                                                                     |
|  STAGE 1 -- CANARY (1% of traffic):                                 |
|                                                                     |
|  [All Users]                                                        |
|     |                                                               |
|     v                                                               |
|  [Load Balancer]                                                    |
|     |                     |                                         |
|     v (99%)               v (1%)                                    |
|  [STABLE: v1.2]       [CANARY: v1.3]                                |
|                            |                                        |
|                            v                                        |
|                       [Monitoring]                                  |
|                       - Error rate                                  |
|                       - p99 latency                                 |
|                       - Business metrics                            |
|                            |                                        |
|                    OK?     |     NOT OK?                             |
|                   /        |         \                              |
|                  v         |          v                             |
|           Expand to 10%    |      Roll back canary                  |
|                            |      (99% users unaffected)            |
|                                                                     |
|  STAGE 2 -- EXPAND (10%, then 25%, then 50%, then 100%):           |
|                                                                     |
|  Each stage: monitor for 10-30 minutes. Only advance if metrics     |
|  stay within acceptable bounds.                                     |
|                                                                     |
+---------------------------------------------------------------------+
```

### The metrics that drive canary analysis

A canary deployment without metrics is just a slow rollout. The metrics tell you
whether to advance or abort. The key metrics to compare between stable and canary:

**Error rate** -- the most obvious signal. If v1.3 has a 0.5% error rate and
v1.2 has 0.01%, something is wrong. Do not deploy further.

**Latency percentiles (p50, p95, p99)** -- average latency hides outliers.
p99 tells you what your slowest 1% of requests experience. A canary that is
faster on average but has a p99 that doubled is still bad -- those are real users
having a terrible experience.

**Business metrics** -- add-to-cart rate, payment success rate, search result
click-through. A canary that has normal error rates but users are not buying
anything is a bug. These metrics require instrumenting your application code, not
just your infrastructure. This is the difference between L4 and L5 monitoring.

**Saturation signals** -- CPU, memory, database connection pool utilization on
the canary hosts. If v1.3 uses 40% more memory than v1.2, it will cause OOM
kills at scale even if the 1% canary looks fine.

### Automated canary analysis

Manual analysis is error-prone. Humans get tired. Humans skip checks under
pressure. The right answer is automated canary analysis:

```
+---------------------------------------------------------------------+
|              AUTOMATED CANARY ANALYSIS PIPELINE                     |
+---------------------------------------------------------------------+
|                                                                     |
|  1. DEPLOY canary (1% traffic)                                      |
|         |                                                           |
|         v                                                           |
|  2. COLLECT metrics for N minutes (baseline: stable group,          |
|     treatment: canary group)                                        |
|         |                                                           |
|         v                                                           |
|  3. COMPARE using statistical significance thresholds:              |
|     - Is canary error rate within X% of stable?                     |
|     - Is canary p99 latency within Y ms of stable?                  |
|     - Are business metrics within Z% of stable?                     |
|         |                                                           |
|         v                                                           |
|  4. SCORE: pass / warn / fail                                       |
|         |                       |                 |                 |
|         v (pass)                v (warn)          v (fail)          |
|  Advance to next stage     Alert humans       Auto-rollback         |
|                            Pause rollout      Page on-call          |
|                                                                     |
|  Tools that do this: Spinnaker, Argo Rollouts, Flagger,             |
|  Netflix's Kayenta, AWS CodeDeploy.                                 |
+---------------------------------------------------------------------+
```

### Canary vs blue-green: when to use which

```
+------------------------+-------------------+-------------------+
|  SCENARIO              |  BLUE-GREEN       |  CANARY           |
+------------------------+-------------------+-------------------+
|  Need instant rollback |  Better           |  Possible but     |
|  (< 60 seconds)        |                   |  slower           |
|                        |                   |                   |
|  Want real user        |  No (no real      |  Yes (real users  |
|  validation before     |  traffic until    |  hit canary)      |
|  full rollout          |  cutover)         |                   |
|                        |                   |                   |
|  High-risk change      |  Reasonable       |  Better (small    |
|  with unknown impact   |                   |  blast radius)    |
|                        |                   |                   |
|  Database schema       |  Easier to        |  Harder (both     |
|  changes               |  control          |  versions run     |
|                        |                   |  simultaneously)  |
|                        |                   |                   |
|  Stateful sessions     |  Easier (one      |  Tricky (users    |
|  (cookies, sessions)   |  environment      |  can shift        |
|                        |  at a time)       |  between pools)   |
+------------------------+-------------------+-------------------+
```

---

## 4. Runbooks and Incident Response

### The analogy: the airplane emergency checklist

Commercial airline pilots are among the most skilled professionals on earth. They
train for years and log thousands of hours before flying passengers. And yet: when
an engine fails at 35,000 feet, pilots do not improvise. They pull out a physical
checklist -- the runbook for that specific failure -- and follow it step by step.

Why? Because humans under stress make mistakes. Adrenaline causes tunnel vision.
Experienced people skip steps. The checklist is not an insult to the pilot's
skill. It is how complex, high-stakes systems get handled reliably when the stakes
are highest.

Your production runbook is the same thing. When the payment service is down at
2 AM and your on-call engineer just woke up from deep sleep, they cannot be
expected to remember every diagnostic step from memory. The runbook is the
checklist that makes the response reliable regardless of who is on-call.

### What a runbook contains

A good runbook answers these questions in order:

```
+---------------------------------------------------------------------+
|                    RUNBOOK STRUCTURE                                 |
+---------------------------------------------------------------------+
|                                                                     |
|  HEADER                                                             |
|  - Service name                                                     |
|  - Alert name that triggers this runbook                            |
|  - Severity level (P1/P2/P3/P4)                                     |
|  - Owner team                                                       |
|  - Last reviewed date                                               |
|                                                                     |
|  SECTION 1: WHAT IS HAPPENING                                       |
|  - Plain English description of the symptom                         |
|  - Example: "Users are getting 503 errors on checkout"              |
|                                                                     |
|  SECTION 2: IMMEDIATE TRIAGE (first 5 minutes)                      |
|  - Is this a partial or total outage?                               |
|  - What is the blast radius? (how many users affected)              |
|  - Is there a known deployment in progress?                         |
|  - Dashboard links (pre-filled, no searching required)              |
|                                                                     |
|  SECTION 3: DIAGNOSTIC STEPS (ordered by likelihood)               |
|  - Step 1: Check X dashboard. If Y, go to step 4.                  |
|  - Step 2: Run this exact command: `kubectl get pods -n payments`   |
|  - Decision trees with exact commands, not vague guidance           |
|                                                                     |
|  SECTION 4: MITIGATION OPTIONS                                      |
|  - Option A: Restart service (command: X, risk: low)                |
|  - Option B: Roll back deployment (command: X, risk: medium)        |
|  - Option C: Enable circuit breaker (command: X, risk: low)         |
|  - Option D: Fail over to backup region (command: X, risk: high)    |
|                                                                     |
|  SECTION 5: ESCALATION                                              |
|  - If not resolved in 15 minutes, page: [person/team]              |
|  - Slack channel: #incidents                                        |
|  - If data loss risk: page VP Engineering immediately               |
|                                                                     |
|  SECTION 6: COMMUNICATION TEMPLATE                                  |
|  - Status page update template                                      |
|  - Internal Slack message template                                  |
+---------------------------------------------------------------------+
```

### Incident severity levels

Not every alert is a 3 AM all-hands call. You need a severity framework so
people respond proportionally:

```
+----------+----------------------------------+------------------------+
|  LEVEL   |  DEFINITION                      |  RESPONSE              |
+----------+----------------------------------+------------------------+
|  P1      |  Total outage: all users cannot  |  All hands on deck.    |
|  (SEV1)  |  use core functionality. Revenue |  Page on-call eng,     |
|          |  impact in progress.             |  eng manager, VP.      |
|          |  Example: site is down.          |  War room in 5 min.    |
+----------+----------------------------------+------------------------+
|  P2      |  Partial outage: significant %   |  On-call + one backup  |
|  (SEV2)  |  of users affected, or one core  |  engineer. Incident    |
|          |  feature is down.                |  commander assigned.   |
|          |  Example: checkout failing.      |  Status page update.   |
+----------+----------------------------------+------------------------+
|  P3      |  Degraded: users affected but    |  On-call handles it.   |
|  (SEV3)  |  workarounds exist. Not growing. |  No escalation unless  |
|          |  Example: slow search results.   |  it worsens.           |
+----------+----------------------------------+------------------------+
|  P4      |  Minor: edge case, no user       |  Ticket for next       |
|  (SEV4)  |  impact yet, or internal tool    |  business day. No      |
|          |  degradation.                    |  paging.               |
|          |  Example: admin dashboard slow.  |                        |
+----------+----------------------------------+------------------------+
```

### The incident commander role

Every P1 or P2 incident needs one person in the role of Incident Commander (IC).
This person does NOT do the debugging. Their job is:

- Keep everyone focused on the same problem.
- Assign tasks clearly ("Alice, check database connections. Bob, check the
  application logs from the last deployment.").
- Prevent "too many cooks" from all debugging the same thing simultaneously.
- Drive communication to stakeholders every 15 minutes.
- Decide when to escalate.
- Call the all-clear when the incident is resolved.

The biggest mistake in incident response is the absence of an IC. When everyone
is debugging and no one is coordinating, you get duplicated effort, dropped tasks,
and no one communicating to the business.

### The postmortem: learning from failure

Within 48-72 hours after a P1 or P2 incident, the involved team writes a
postmortem. This is not a blame document. It is a learning document.

A good postmortem has five sections:

```
+---------------------------------------------------------------------+
|                    POSTMORTEM STRUCTURE                             |
+---------------------------------------------------------------------+
|                                                                     |
|  1. SUMMARY (2-3 sentences)                                         |
|     What happened, how long, how many users affected.               |
|                                                                     |
|  2. TIMELINE (with exact timestamps)                                |
|     14:32 -- Alert fires for elevated error rate                    |
|     14:35 -- On-call acknowledges                                   |
|     14:41 -- Root cause identified (bad config push at 14:28)       |
|     14:55 -- Config reverted, error rate returns to baseline        |
|     15:10 -- Incident declared resolved                             |
|                                                                     |
|  3. ROOT CAUSE (not the symptom, the actual cause)                  |
|     Bad: "The service returned errors."                              |
|     Good: "A config push changed the database connection pool        |
|     size from 100 to 10, causing connection exhaustion under         |
|     normal production load."                                         |
|                                                                     |
|  4. WHAT WENT WELL                                                  |
|     - Alert fired within 3 minutes of degradation starting.         |
|     - Rollback took 8 minutes, within SLO recovery target.          |
|                                                                     |
|  5. ACTION ITEMS (with owners and due dates)                        |
|     - Add config validation to deployment pipeline. [Alice, 2 wks]  |
|     - Add connection pool exhaustion alert. [Bob, 1 week]           |
|     - Test rollback procedure in staging monthly. [Team, ongoing]   |
|                                                                     |
|  WHAT A GOOD POSTMORTEM DOES NOT CONTAIN:                           |
|  - Names of individuals who made mistakes                           |
|  - Blame language ("Charlie should have caught this")               |
|  - Vague action items ("improve testing")                           |
+---------------------------------------------------------------------+
```

---

## 5. Observability: Logs, Metrics, and Traces

### The analogy: the doctor's instruments

Imagine you are a doctor trying to understand why a patient feels sick. You have
three tools:

**The patient's diary** (logs) -- a detailed record of everything that happened.
"At 2 PM I ate lunch. At 3 PM I started feeling nauseous. At 4 PM I vomited."
Extremely detailed, but you have to read through a lot of entries to find the
relevant ones.

**The vital signs monitor** (metrics) -- numbers updated every second: heart
rate, blood pressure, temperature. Great for seeing trends and triggering alarms,
but numbers alone do not tell you why something is wrong.

**The MRI scan** (traces) -- a picture of the patient's entire internal state at
a specific moment, showing how every system is connected and where the problem is
located. The most powerful tool, but also the most expensive and complex to run.

In production systems: logs are your diary, metrics are your vital signs monitor,
traces are your MRI. A well-instrumented system has all three.

### The three pillars of observability

```
+---------------------------------------------------------------------+
|                 THE THREE PILLARS OF OBSERVABILITY                  |
+---------------------------------------------------------------------+
|                                                                     |
|  LOGS                    METRICS                   TRACES           |
|  +------------------+    +------------------+    +----------------+ |
|  | Timestamped text  |    | Numeric time     |    | End-to-end     | |
|  | records of events |    | series data      |    | request flow   | |
|  |                  |    |                  |    | across services| |
|  | Example:         |    | Example:         |    |                | |
|  | 2024-01-15       |    | api.error_rate   |    | Request 7f3a:  | |
|  | 14:32:01         |    | = 0.5%           |    | API (12ms)     | |
|  | ERROR            |    | api.p99_latency  |    |  -> Auth (3ms) | |
|  | UserNotFound     |    | = 450ms          |    |  -> DB (40ms)  | |
|  | user_id=12345    |    | db.connections   |    |  -> Cache miss | |
|  |                  |    | = 98/100         |    |  -> DB (35ms)  | |
|  | Good for:        |    |                  |    |                | |
|  | Debugging        |    | Good for:        |    | Good for:      | |
|  | specific events  |    | Alerting,        |    | Finding where  | |
|  | Audit trails     |    | trending,        |    | time is spent  | |
|  | Error details    |    | capacity         |    | in a request   | |
|  |                  |    | planning         |    |                | |
|  | Cost: medium     |    | Cost: low        |    | Cost: high     | |
|  | Volume: high     |    | Volume: low      |    | Volume: medium | |
|  +------------------+    +------------------+    +----------------+ |
|                                                                     |
|  Tools:                  Tools:                  Tools:            |
|  Elasticsearch,          Prometheus,             Jaeger,           |
|  Splunk,                 Datadog,                Zipkin,           |
|  CloudWatch Logs         Grafana                 AWS X-Ray         |
+---------------------------------------------------------------------+
```

### Logs: what to log and what not to log

Common log mistakes:

**Log too little**: "An error occurred." -- useless. You cannot diagnose
anything from this.

**Log too much**: logging every function call, every variable value, every
database read. Your log storage bill will exceed your server bill. More
importantly, signal drowns in noise.

**The right level of logging**:

```
+---------------------------------------------------------------------+
|               WHAT BELONGS IN YOUR LOGS                             |
+---------------------------------------------------------------------+
|                                                                     |
|  LOG THESE:                                                         |
|  + Request start and end (with latency, status code, user ID)       |
|  + All errors and exceptions (with stack trace)                     |
|  + External calls (to databases, APIs, queues) with latency         |
|  + Authentication events (login, logout, failed login)              |
|  + Business events (order placed, payment processed, user deleted)  |
|  + Config changes (who changed what, when)                          |
|  + Deployment events (version X deployed at timestamp Y)            |
|                                                                     |
|  DO NOT LOG THESE:                                                  |
|  - Passwords, API keys, credit card numbers, SSNs (ever)            |
|  - Internal function calls in hot paths (too noisy)                 |
|  - Every database row read (too expensive)                          |
|  - Debug statements left in from development                        |
|                                                                     |
|  LOG FORMAT -- always structured (JSON), never free text:           |
|  {                                                                  |
|    "timestamp": "2024-01-15T14:32:01Z",                            |
|    "level": "ERROR",                                                |
|    "service": "payment-service",                                    |
|    "trace_id": "7f3a9b2c",   <-- connects to your trace system      |
|    "user_id": "u_12345",                                            |
|    "event": "payment_failed",                                       |
|    "error": "card_declined",                                        |
|    "amount_cents": 4999,                                            |
|    "duration_ms": 230                                               |
|  }                                                                  |
+---------------------------------------------------------------------+
```

### Metrics: the four golden signals

Google's Site Reliability Engineering book introduced the concept of the four
golden signals. Every service should monitor these four:

```
+---------------------------------------------------------------------+
|              THE FOUR GOLDEN SIGNALS                                 |
+---------------------------------------------------------------------+
|                                                                     |
|  1. LATENCY                                                         |
|     How long does a request take?                                   |
|     Track: p50, p95, p99 (NOT just average)                        |
|     Alert when: p99 > SLO threshold                                 |
|     Pitfall: always separate latency of successful vs failed        |
|     requests -- a fast error is not a good fast.                    |
|                                                                     |
|  2. TRAFFIC                                                         |
|     How much demand is the system receiving?                        |
|     Track: requests per second (RPS), messages per second (MPS)     |
|     Use for: capacity planning, detecting traffic anomalies         |
|     Pitfall: sudden traffic drop is often worse than a spike --     |
|     it may mean your load balancer or DNS is broken.                |
|                                                                     |
|  3. ERRORS                                                          |
|     How often do requests fail?                                     |
|     Track: error rate (errors / total requests * 100)               |
|     Track: 5xx rate separately from 4xx (server errors vs          |
|     client errors -- very different problems)                       |
|     Alert when: error rate > SLO threshold                          |
|                                                                     |
|  4. SATURATION                                                      |
|     How "full" is the service?                                      |
|     Track: CPU %, memory %, DB connection pool %, disk %            |
|     Alert when: approaching limits (80%+ CPU, 90%+ connections)     |
|     Why: saturation predicts future problems. High saturation       |
|     now means errors and latency spikes under more load.            |
+---------------------------------------------------------------------+
```

### Traces: following a request across services

Imagine you order a pizza. The order goes to the counter, who passes it to the
kitchen, who tells the oven operator, who hands it to the delivery driver.
If your pizza arrives cold, which step caused the delay? You need to trace the
order through every station.

A distributed trace does exactly this for a request through your microservices:

```
+---------------------------------------------------------------------+
|                    DISTRIBUTED TRACE EXAMPLE                        |
+---------------------------------------------------------------------+
|                                                                     |
|  User clicks "Buy Now"                                              |
|  Trace ID: 7f3a9b2c                                                 |
|                                                                     |
|  |-- API Gateway (15ms total) -------------------------------|      |
|       |-- Auth Service (4ms) ------|                                |
|       |-- Order Service (180ms total) ----------------------|       |
|            |-- Inventory DB read (45ms) ---|                        |
|            |-- Price Service (22ms) ------|                         |
|            |-- Payment Service (80ms total) ---|                    |
|                  |-- Stripe API call (65ms) ---|                    |
|            |-- Order DB write (28ms) ---|                           |
|       |-- Email Service (async, 300ms) <-- NOT in critical path     |
|                                                                     |
|  Total user-visible latency: API Gateway 15ms + Order 180ms = 195ms |
|                                                                     |
|  What the trace tells you:                                          |
|  - Stripe API call is 65ms of the 80ms payment step                |
|  - Inventory DB read is 45ms -- is this index missing?              |
|  - Email is async so it does not affect user latency                |
|                                                                     |
|  Without traces: "the API is slow (195ms)"                          |
|  With traces: "the Stripe call and inventory read need optimization" |
+---------------------------------------------------------------------+
```

### Connecting the three pillars: correlation

The three pillars are most powerful when connected. The key is the **trace ID**:
a unique identifier generated at the entry point of every request, and passed
through every service and log line in that request's journey.

When an alert fires for high error rate (metric), you navigate to the affected
time window, find trace IDs with errors (trace), and pull the logs for those
specific trace IDs to see exact error messages (log). Without the trace ID
connecting them, you are doing three separate investigations instead of one.

---

## 6. SLOs, SLIs, and Error Budgets

### The analogy: the airline on-time guarantee

An airline promises: "85% of our flights arrive within 15 minutes of scheduled
time." This is a concrete, measurable commitment. Not "we try to be on time." Not
"we are usually on time." A specific number.

When they miss that target -- say, only 78% of flights were on time last quarter
-- they know they have a problem. They can investigate: was it weather, staffing,
maintenance delays? They can decide: do we need new operational procedures?

But here is the key insight: they did not promise 100% on-time flights. Because
promising 100% is both impossible (weather exists) and would require such extreme
redundancy and caution that planes would rarely fly at all. The target is set at
a level that is achievable with good operations, while accepting that some
imperfection is the cost of operating efficiently.

Your SLO (Service Level Objective) is that airline promise for your software.

### Definitions: SLI, SLO, SLA

These three terms are frequently confused. Here is the precise definition of each:

```
+---------------------------------------------------------------------+
|              SLI vs SLO vs SLA -- CLEAR DEFINITIONS                 |
+---------------------------------------------------------------------+
|                                                                     |
|  SLI -- Service Level INDICATOR                                     |
|  The actual measurement. A ratio or number.                         |
|  Example: "The fraction of HTTP requests that returned a 2xx        |
|  status code in the last 30 days."                                  |
|  Formula: SLI = good_requests / total_requests                      |
|  The SLI is just data. It has no target yet.                        |
|                                                                     |
|  SLO -- Service Level OBJECTIVE                                     |
|  The target you set for your SLI. Internal commitment.              |
|  Example: "99.9% of requests must return a 2xx status code."        |
|  This is what your engineering team commits to achieving.           |
|  It is not a contract with customers -- it is an internal goal.     |
|                                                                     |
|  SLA -- Service Level AGREEMENT                                     |
|  The external, contractual commitment to customers. Usually         |
|  set more loosely than your SLO, with financial penalties if        |
|  missed.                                                            |
|  Example: "We guarantee 99.5% uptime. If we miss it, you get       |
|  a 10% bill credit."                                                |
|  Relationship: SLA < SLO. Your internal target must be harder       |
|  than your customer promise to give yourself a buffer.              |
|                                                                     |
|  +------+     +------+     +------+                                 |
|  | SLI  | --> | SLO  | --> | SLA  |                                 |
|  | 99.93%|    | 99.9% |    | 99.5% |                               |
|  | (fact)|    |(target)|   |(contract)                              |
|  +------+     +------+     +------+                                 |
|  You measure   You aim at   Customer        |                       |
|  this          this         gets this       |                       |
+---------------------------------------------------------------------+
```

### The math of uptime and downtime

Engineers quote uptime percentages casually. Few stop to calculate what they
actually mean in hours of downtime per year:

```
+---------------------+------------------+------------------+
|  UPTIME TARGET      |  DOWNTIME/YEAR   |  DOWNTIME/MONTH  |
+---------------------+------------------+------------------+
|  99%                |  87.6 hours      |  7.3 hours       |
|  99.5%              |  43.8 hours      |  3.6 hours       |
|  99.9% ("3 nines")  |  8.76 hours      |  43.8 minutes    |
|  99.95%             |  4.38 hours      |  21.9 minutes    |
|  99.99% ("4 nines") |  52.6 minutes    |  4.4 minutes     |
|  99.999% ("5 nines")|  5.26 minutes    |  26 seconds      |
+---------------------+------------------+------------------+

Note: every additional "9" requires roughly 10x more engineering
effort and cost. Going from 99.9% to 99.99% is not 0.09% more
work. It is a complete change to your deployment, redundancy,
and on-call practices.
```

### Error budgets: making reliability a math problem

The error budget is the most powerful concept in SRE (Site Reliability
Engineering). Here is the idea:

If your SLO is 99.9% availability over 30 days, you are implicitly allowing
0.1% unavailability. That 0.1% is your **error budget**.

```
+---------------------------------------------------------------------+
|                    ERROR BUDGET MATH                                |
+---------------------------------------------------------------------+
|                                                                     |
|  SLO: 99.9% availability over 30 days                               |
|  Total minutes in 30 days: 30 * 24 * 60 = 43,200 minutes           |
|  Error budget: 0.1% * 43,200 = 43.2 minutes of downtime allowed    |
|                                                                     |
|  Week 1: You deploy a bad release. 20 minutes of downtime.          |
|  Remaining budget: 43.2 - 20 = 23.2 minutes                        |
|                                                                     |
|  Week 2: Database maintenance causes 5 minutes degradation.         |
|  Remaining budget: 23.2 - 5 = 18.2 minutes                         |
|                                                                     |
|  Week 3: Your team wants to deploy a major refactor.                |
|  Question: Can you afford the deployment risk given only            |
|  18.2 minutes of budget remaining?                                  |
|  Answer: You decide, with data. Not with gut feeling.               |
+---------------------------------------------------------------------+
```

### Error budget policy: what happens when you burn it

The error budget creates a concrete policy for when to slow down:

```
+---------------------------------------------------------------------+
|                    ERROR BUDGET POLICY                              |
+---------------------------------------------------------------------+
|                                                                     |
|  Budget remaining > 50%:                                            |
|  - Full deployment velocity. Ship features aggressively.            |
|  - Acceptable to take calculated risks with deployments.            |
|                                                                     |
|  Budget remaining 25%-50%:                                          |
|  - Increased caution. Code review bar raised.                       |
|  - No experiments or risky architectural changes.                   |
|  - Postmortem required for any incident.                            |
|                                                                     |
|  Budget remaining 10%-25%:                                          |
|  - Only critical bug fixes and security patches deployed.            |
|  - All deployment risk reviewed by staff engineer or TL.            |
|  - Reliability improvements prioritized over features.              |
|                                                                     |
|  Budget remaining < 10% (or already burned):                        |
|  - Feature freeze. No new deployments.                              |
|  - All engineering time goes to reliability work.                   |
|  - SLO miss reported to customers. SLA credits issued.              |
|  - Postmortem for every incident this month.                        |
+---------------------------------------------------------------------+
```

Why is this powerful? It turns the abstract argument between the product team
("ship faster!") and the SRE team ("slow down, stability first!") into a
concrete, data-driven conversation. When the budget is full, product wins. When
it is burned, reliability wins. No politics. The math decides.

---

## 7. Capacity Planning

### The analogy: planning parking for a stadium

A stadium is being built. You need to decide how many parking spaces to build.
If you build too few spaces, game days are a disaster -- cars circle the area for
an hour and fans are furious before they even get inside. If you build too many,
you spend millions on concrete that sits empty 340 days a year.

Capacity planning is making this parking lot decision -- but for servers,
database connections, and network bandwidth -- before you hit a game day.

The good news: unlike a parking lot, cloud infrastructure is somewhat flexible.
You can add capacity faster than pouring concrete. The bad news: provisioning
takes time, lead time matters, and many companies have learned this lesson the
hard way by running out of capacity during their biggest moment.

### The five steps of capacity planning

```
+---------------------------------------------------------------------+
|                   CAPACITY PLANNING PROCESS                         |
+---------------------------------------------------------------------+
|                                                                     |
|  STEP 1 -- MEASURE CURRENT STATE                                    |
|  - What is current traffic? (RPS, concurrent users, DB QPS)         |
|  - What is current utilization? (CPU %, memory %, connection pool)  |
|  - What is the trend? (growing 10% month-over-month?)               |
|  - Where are the bottlenecks? (what saturates first?)               |
|                                                                     |
|  STEP 2 -- FORECAST GROWTH                                          |
|  - What does the business expect? (product roadmap, growth targets) |
|  - What growth events are planned? (launch in Japan next quarter,   |
|    Super Bowl ad, major feature launch)?                            |
|  - Historical growth rate as a baseline                             |
|  - Build a model: if RPS grows 15% month-over-month, where are      |
|    we in 3 months? 6 months? 12 months?                             |
|                                                                     |
|  STEP 3 -- FIND THE BREAKING POINT                                  |
|  - Load test: gradually increase traffic until something fails       |
|  - Identify: which component fails first? At what RPS?              |
|  - Is it the API servers? The database? The cache? The queue?       |
|  - This is the system's current ceiling.                            |
|                                                                     |
|  STEP 4 -- CALCULATE WHEN YOU HIT THE CEILING                       |
|  - If ceiling is 10,000 RPS and you grow 10% per month:             |
|  - If current traffic is 5,000 RPS:                                 |
|    5000 * (1.10)^N = 10000 -> N = 7.3 months                       |
|  - Plan to scale before month 5-6 to have buffer.                   |
|                                                                     |
|  STEP 5 -- PLAN THE SCALING ACTION                                  |
|  - Vertical scaling: bigger instances (quick but limited)           |
|  - Horizontal scaling: more instances (preferred for stateless tiers)|
|  - Database sharding: more complex but necessary for large datasets  |
|  - Caching layer: reduce load on database                           |
|  - Async processing: move work off critical path                    |
+---------------------------------------------------------------------+
```

### Load testing: finding your ceiling before users do

Load testing is how you find the stadium's maximum safe occupancy before you
invite 80,000 fans.

```
+---------------------------------------------------------------------+
|                    LOAD TEST TYPES                                   |
+---------------------------------------------------------------------+
|                                                                     |
|  BASELINE TEST                                                      |
|  - Normal expected load for 30-60 minutes                           |
|  - Purpose: confirm system behaves normally                         |
|  - Frequency: before every major release                            |
|                                                                     |
|  STRESS TEST                                                        |
|  - Gradually ramp traffic: 100% -> 150% -> 200% -> 300% of normal  |
|  - Purpose: find where things break                                 |
|  - Key question: which component fails first?                       |
|  - Key question: does it fail gracefully or catastrophically?       |
|                                                                     |
|  SPIKE TEST                                                         |
|  - Sudden 10x traffic increase for 2-5 minutes                      |
|  - Purpose: simulate viral event or DDoS                            |
|  - Key question: does autoscaling keep up? How long does it take?  |
|                                                                     |
|  SOAK TEST                                                          |
|  - Normal load for 72+ hours                                        |
|  - Purpose: find memory leaks, connection pool exhaustion,          |
|    disk filling up over time                                        |
|  - These bugs only appear at runtime, not in short tests            |
|                                                                     |
|  Tools: k6, Locust, Apache JMeter, Gatling, AWS Load Testing        |
+---------------------------------------------------------------------+
```

### Capacity planning triggers: when to act

Good systems have defined triggers that automatically start the capacity planning
conversation:

```
+------------------------------+----------------------------------------+
|  TRIGGER                     |  ACTION                                |
+------------------------------+----------------------------------------+
|  CPU > 70% sustained         |  Evaluate horizontal scaling           |
|  Memory > 80% sustained      |  Profile for memory leaks, or scale    |
|  DB connections > 80%        |  Add read replicas or connection pool  |
|  Cache hit rate drops < 80%  |  Investigate cache eviction, grow cache|
|  Traffic growth > 20%        |  Capacity review meeting               |
|  per month                   |                                        |
|  P99 latency growing 10%     |  Profile and optimize or scale         |
|  week-over-week              |                                        |
|  Storage > 70% full          |  Plan storage expansion (3-6 mo lead)  |
+------------------------------+----------------------------------------+
```

---

## 8. Cost Modeling

### The analogy: tracking the cost per pizza slice

Imagine you run a pizza restaurant. You know your total monthly costs: $20,000
for rent, $8,000 for staff, $5,000 for ingredients. Total: $33,000 per month.

Now imagine you sold 3,000 pizzas this month. Your cost per pizza is $11. If you
sell a pizza for $15, you make $4 per pizza. If you sell 3,000 pizzas you make
$12,000 profit.

But here is the key question: if you double your pizza output to 6,000 pizzas per
month, do your costs double? The rent stays the same. Staff might grow by 20%.
Ingredients double. So total cost goes to roughly $22,600 -- less than double.
Your cost per pizza drops to $3.77 and your profit per pizza jumps to $11.23.

This is **unit economics**: understanding the cost and revenue per unit as scale
changes. Every software business needs the same analysis -- not for pizzas, but
for API calls, users, transactions, or gigabytes stored.

### Unit economics for software systems

```
+---------------------------------------------------------------------+
|               UNIT ECONOMICS FRAMEWORK                              |
+---------------------------------------------------------------------+
|                                                                     |
|  STEP 1 -- DEFINE YOUR UNIT                                         |
|  What is the atomic unit of value your business delivers?           |
|  - E-commerce: cost per order processed                             |
|  - SaaS: cost per active user per month                             |
|  - API business: cost per 1,000 API calls                           |
|  - Storage: cost per GB stored per month                            |
|                                                                     |
|  STEP 2 -- TALLY YOUR COSTS                                         |
|  Fixed costs (same regardless of usage):                            |
|  - Engineer salaries, base cluster size, office costs               |
|  Variable costs (scale with usage):                                 |
|  - Compute: $/hour per server or $/request (serverless)             |
|  - Storage: $/GB/month                                              |
|  - Data transfer: $/GB egressed                                     |
|  - Third-party APIs: $/call or $/record                             |
|                                                                     |
|  STEP 3 -- CALCULATE COST PER UNIT                                  |
|  Total infrastructure cost / total units served                     |
|  Example: $50,000/month infra / 5,000,000 API calls                 |
|         = $0.01 per API call                                        |
|                                                                     |
|  STEP 4 -- IDENTIFY COST DRIVERS                                    |
|  What fraction of total cost does each component represent?         |
|  If database costs are 60% of total infra spend, focus there.       |
|  If data transfer is 30% of costs, investigate CDN or compression.  |
|                                                                     |
|  STEP 5 -- MODEL SCALING                                            |
|  At 10x current usage: which costs scale linearly?                  |
|  Which costs are fixed and get amortized?                           |
|  What is the unit cost at 10x? Is the business still viable?        |
+---------------------------------------------------------------------+
```

### Cost optimization strategies

Cost optimization is not about being cheap. It is about extracting maximum value
per dollar spent, which requires understanding where the dollars go:

```
+---------------------------------------------------------------------+
|                   COST OPTIMIZATION LEVERS                          |
+---------------------------------------------------------------------+
|                                                                     |
|  COMPUTE OPTIMIZATION                                               |
|  - Right-size instances: not every service needs the largest box    |
|  - Use Spot/Preemptible instances for fault-tolerant batch work     |
|    (60-90% cheaper than on-demand)                                  |
|  - Reserved instances for predictable baseline load (30-60% savings)|
|  - Autoscaling: scale down at night, weekends, low-traffic periods  |
|                                                                     |
|  STORAGE OPTIMIZATION                                               |
|  - Tiered storage: hot data on SSD, warm on HDD, cold on S3         |
|  - Lifecycle policies: auto-archive logs after 30 days              |
|  - Compression: compress logs, large JSON payloads, cold data       |
|  - Deduplication: do not store the same data twice                  |
|                                                                     |
|  DATA TRANSFER OPTIMIZATION                                         |
|  - Data transfer costs are often invisible until they are not        |
|  - Use CDN to serve static content from edge (avoid origin hits)    |
|  - Put services in the same region to avoid cross-region transfer   |
|  - Compress API responses (gzip, Brotli)                            |
|                                                                     |
|  DATABASE OPTIMIZATION                                              |
|  - Cache aggressively to reduce database reads                      |
|  - Right-size: most databases are over-provisioned 3-5x             |
|  - Separate hot and cold data (archive old records)                 |
|  - Query optimization: a missing index can cost 100x in DB compute  |
+---------------------------------------------------------------------+
```

### The FinOps mindset: who owns cost?

At a startup, one person (usually the CTO) looks at the AWS bill. At a large
company, costs are often a shared responsibility mess where no single team feels
accountable for infrastructure spend. The FinOps approach assigns cost ownership
to the teams that generate costs:

```
+---------------------------------------------------------------------+
|                   FINOPS OWNERSHIP MODEL                            |
+---------------------------------------------------------------------+
|                                                                     |
|  BEFORE FINOPS:                                                     |
|  - One platform team gets the AWS bill                              |
|  - Feature teams have no visibility into what their services cost   |
|  - No one is incentivized to optimize                               |
|  - Costs grow with no clear accountability                          |
|                                                                     |
|  WITH FINOPS:                                                        |
|  - Every service tagged with owning team in cloud resources         |
|  - Monthly cost reports sent to each team showing their cost        |
|  - Teams set cost-per-unit targets (cost per API call, per user)    |
|  - Cost anomaly alerts go to the owning team, not just platform     |
|  - Cost efficiency is a metric on engineering scorecards            |
|                                                                     |
|  Result: engineers start asking "how much does this query cost?"    |
|  before writing it. That mindset shift saves millions at scale.     |
+---------------------------------------------------------------------+
```

---

## 9. Rollback Strategies

### The analogy: the surgeon's decision

A surgeon is performing an operation. Midway through, they encounter an unexpected
complication -- an artery is closer to the tumor than expected. They have two
choices:

**Option A -- Fix forward**: adapt the surgical plan, carefully work around the
artery, and complete the operation with a modified approach. Riskier because the
situation is uncertain, but the patient is already open on the table.

**Option B -- Rollback**: close the patient up safely, bring them back to a stable
state, and reschedule the operation after studying the unexpected anatomy with
more imaging. Less immediately risky but delays the treatment.

Every deployment incident is this surgeon's dilemma. Rolling back (closing up and
rescheduling) is usually safer. But sometimes fixing forward is the right call.
Knowing which to choose under pressure is a Staff-level skill.

### The rollback vs fix-forward decision tree

```
+---------------------------------------------------------------------+
|              ROLLBACK VS FIX-FORWARD DECISION TREE                  |
+---------------------------------------------------------------------+
|                                                                     |
|  [Incident detected after deployment]                               |
|         |                                                           |
|         v                                                           |
|  Is the root cause clearly the new deployment?                      |
|  YES --> proceed                                                    |
|  NO  --> investigate further before rollback (rollback may not help)|
|         |                                                           |
|         v (YES)                                                     |
|  Is a rollback possible? (no data migration that makes it unsafe?)  |
|  NO  --> fix forward only                                           |
|  YES --> proceed                                                    |
|         |                                                           |
|         v (YES)                                                     |
|  Can you fix forward in < 15 minutes with high confidence?          |
|  YES --> fix forward                                                |
|  NO  --> continue                                                   |
|         |                                                           |
|         v (NO)                                                      |
|  How much error budget is remaining?                                |
|  < 25% remaining --> ROLLBACK immediately                           |
|  > 25% remaining --> continue                                       |
|         |                                                           |
|         v (> 25%)                                                   |
|  Is the impact growing or stable?                                   |
|  GROWING --> ROLLBACK immediately                                   |
|  STABLE  --> fix forward with 15-minute checkpoint                  |
|                                                                     |
|  GOLDEN RULE: When in doubt, roll back. You can always re-deploy.   |
|  You cannot un-cause an outage that damaged users.                  |
+---------------------------------------------------------------------+
```

### When rollback is not an option: the data migration trap

The most dangerous deployment scenario is one where rolling back would corrupt
or lose data. This happens when:

- New code writes to a new database column that the old code does not know how
  to read.
- New code deletes records that the old code expects to exist.
- New code transforms data in a way that is not reversible.

If your deployment involves any of these, rollback becomes "roll back and lose
data" or "roll back and cause errors in old code." Neither is acceptable.

The answer: use the expand-contract pattern (described in Section 2). Design
deployments so both old and new code can run against the same schema simultaneously.
If you cannot guarantee this, you need a separate data migration strategy, not
a simple rollback plan.

### Types of rollback by deployment mechanism

```
+---------------------+------------------------------+------------------+
|  DEPLOYMENT TYPE    |  ROLLBACK MECHANISM          |  SPEED           |
+---------------------+------------------------------+------------------+
|  Blue-Green         |  Load balancer switch back   |  < 60 seconds    |
|                     |  to blue environment         |                  |
+---------------------+------------------------------+------------------+
|  Canary             |  Remove canary from pool,    |  < 2 minutes     |
|                     |  set weight to 0%            |                  |
+---------------------+------------------------------+------------------+
|  Kubernetes         |  kubectl rollout undo        |  1-5 minutes     |
|  Deployment         |  deployment/<name>           |                  |
+---------------------+------------------------------+------------------+
|  Feature Flags      |  Toggle flag off in control  |  < 10 seconds    |
|                     |  panel, no deploy needed     |                  |
+---------------------+------------------------------+------------------+
|  Database migration |  Down migration script       |  5-30 minutes    |
|                     |  (if written in advance)     |  (risky)         |
+---------------------+------------------------------+------------------+
|  Config change      |  Revert config in config     |  < 30 seconds    |
|                     |  management system (Consul,  |                  |
|                     |  AWS Parameter Store)        |                  |
+---------------------+------------------------------+------------------+
```

### Feature flags: the safest rollback

Feature flags (also called feature toggles) are a pattern where new behavior is
wrapped in a conditional check:

```
NORMAL CODE (no feature flag):
  function processOrder(order):
    applyNewPricingAlgorithm(order)
    return charge(order)

WITH FEATURE FLAG:
  function processOrder(order):
    if featureFlag.isEnabled("new_pricing_algo", user):
      applyNewPricingAlgorithm(order)
    else:
      applyOldPricingAlgorithm(order)
    return charge(order)
```

With feature flags, you can deploy the code to 100% of servers but only enable
it for 1% of users. If something is wrong, you disable the flag in your control
panel -- no deployment needed, rollback in under 10 seconds. This is better than
any deployment-level rollback because it is nearly instantaneous and requires
zero coordination with the deployment pipeline.

---

## 10. How Your Thinking Evolves: Intern to Staff

### The intern mindset

The intern's world is the laptop. Code runs, tests pass, PR is merged. The concept
of "production" is abstract. Deployment is something that happens after your PR
is approved. Incidents are something the on-call person handles.

An intern engineer who has been on-call once and spent 3 AM looking at a dashboard
while someone's checkout is broken learns more about production operations in that
night than in months of coding. This is not a criticism -- it is how the learning
happens.

### The progression across levels

```
+--------+--------------------------------------------------------------+
|  LEVEL |  HOW THEY THINK ABOUT DEPLOYMENT AND OPERATIONS              |
+--------+--------------------------------------------------------------+
|        |                                                              |
|  L3    |  "I write code and run tests. Deployment is someone else's   |
|  Intern|  job. I have never been on-call. When an alert fires I call  |
|        |  my manager."                                                |
|        |                                                              |
+--------+--------------------------------------------------------------+
|        |                                                              |
|  L4    |  "I can deploy my service using the pipeline. I have been    |
|  Junior|  on-call and I can follow a runbook. I know what a dashboard |
|        |  is. I panic a little when an alert fires."                  |
|        |                                                              |
+--------+--------------------------------------------------------------+
|        |                                                              |
|  L5    |  "I own my service's deployment and operational health. I    |
|  Mid   |  have SLOs defined. I write runbooks for my service. I can   |
|        |  diagnose most incidents using logs, metrics, and traces. I  |
|        |  do postmortems. I can do a canary deployment."              |
|        |                                                              |
+--------+--------------------------------------------------------------+
|        |                                                              |
|  L6    |  "I set the deployment strategy for multiple services. I     |
|  Staff |  define the SLO framework the organization uses. I review    |
|        |  cost models quarterly. I run the incident commander role    |
|        |  for P1s. I know which runbooks are stale and get them       |
|        |  fixed. I can see when a capacity plan is optimistic or      |
|        |  understated. I think about reliability as a product         |
|        |  property, not a devops property."                           |
|        |                                                              |
+--------+--------------------------------------------------------------+
|        |                                                              |
|  L7    |  "I set organizational policy on reliability targets. I      |
|  Sr    |  build relationships with platform and SRE teams to evolve   |
|  Staff |  shared infrastructure. I define the FinOps model. I create  |
|        |  the capacity planning process for a division. I write the   |
|        |  incident management playbook. I am consulted in the first   |
|        |  five minutes of a P1."                                      |
|        |                                                              |
+--------+--------------------------------------------------------------+
```

### The Staff engineer's three operational principles

**Principle 1 -- Reliability is a feature, not a tax.**
Junior engineers treat operational work as overhead that takes time away from
feature development. Staff engineers understand that a service that goes down
every month is a worse product than one that ships features 20% slower but never
falls over. Reliability is a customer-facing property. It belongs on the
roadmap alongside feature work.

**Principle 2 -- Automate the toil, own the judgment.**
Toil is the repetitive manual work of running a system -- manual deployments,
manual capacity checks, manually rotating secrets. Toil is automatable and should
be. But the judgment layer -- when to roll back, how to set SLOs, whether a
canary metric difference is significant -- requires human expertise. Staff
engineers automate the toil aggressively so they can spend time on the judgment.

**Principle 3 -- Every incident is a design review.**
When something breaks in production, a Staff engineer's first question is not
"how do we fix this" but "what about our design allowed this to happen." The
incident is feedback from the production environment about the design decisions
you made 6 months ago. Reading that feedback and improving the design is how
systems get more reliable over time.

---

## 11. L5 vs L6 Calibration Table

```
+------+-------------------------------+---------------------------------+
| ROW  | L5 ENGINEER BEHAVIOR          | L6 ENGINEER BEHAVIOR            |
+------+-------------------------------+---------------------------------+
|      |                               |                                 |
|  1   | Uses canary deployment when   | Defines when canary vs          |
|      | the team prescribes it.       | blue-green is the right tool    |
|      |                               | for a given service or change.  |
|      |                               |                                 |
|  2   | Monitors error rate and        | Defines the complete metrics    |
|      | latency on their service.      | strategy for a team: which      |
|      |                               | SLIs matter, what constitutes   |
|      |                               | a meaningful alert.             |
|      |                               |                                 |
|  3   | Follows a runbook during an    | Writes runbooks for the team.   |
|      | incident.                      | Identifies which runbooks are   |
|      |                               | stale and drives updates.       |
|      |                               |                                 |
|  4   | Sets an SLO for their service  | Defines the SLO framework for   |
|      | based on org guidance.         | the org, including error budget  |
|      |                               | policy and SLA relationship.    |
|      |                               |                                 |
|  5   | Contributes to a postmortem    | Facilitates postmortems,        |
|      | for their service.             | ensures action items are        |
|      |                               | tracked to closure, and finds   |
|      |                               | systemic patterns across        |
|      |                               | multiple incidents.             |
|      |                               |                                 |
|  6   | Can read a capacity plan       | Creates and reviews capacity    |
|      | and identify obvious risks.    | plans for multiple services.    |
|      |                               | Pushes back on optimistic       |
|      |                               | growth assumptions.             |
|      |                               |                                 |
|  7   | Knows what cost their service  | Owns the unit economics model   |
|      | incurs (roughly).              | for a team. Tracks cost per     |
|      |                               | unit quarterly and sets targets.|
|      |                               |                                 |
|  8   | Can execute a rollback using   | Decides whether to roll back    |
|      | documented procedures.         | or fix forward under pressure,  |
|      |                               | weighing error budget, blast    |
|      |                               | radius, and fix confidence.     |
|      |                               |                                 |
|  9   | Instruments their service      | Defines the observability       |
|      | with standard logs and         | standards for a team: log       |
|      | metrics.                       | schema, trace sampling rates,   |
|      |                               | metric naming conventions.      |
|      |                               |                                 |
| 10   | Responds to P1/P2 incidents    | Acts as incident commander for  |
|      | as a responder.                | P1 incidents. Coordinates       |
|      |                               | response, communication,        |
|      |                               | and escalation decisions.       |
|      |                               |                                 |
| 11   | Thinks about load testing      | Designs and drives the load     |
|      | for their specific service     | testing strategy for a          |
|      | before a release.              | platform. Identifies cross-     |
|      |                               | service bottlenecks.            |
|      |                               |                                 |
| 12   | Understands the difference     | Uses SLOs as a negotiation      |
|      | between SLI, SLO, SLA.         | tool with product: uses error   |
|      |                               | budget data to justify slowing  |
|      |                               | feature delivery for            |
|      |                               | reliability investment.         |
+------+-------------------------------+---------------------------------+
```

---

## 12. Named Production Incidents

These are five real or realistic production incidents that illustrate the concepts
in this chapter. Each follows the postmortem format.

---

### Incident 1: The Knight Capital Flash Crash (2012)

**Summary**: Knight Capital Group, a major stock trading firm, deployed new
software to 8 of their 9 production servers. The 9th server still ran old code
due to a deployment error. On August 1, 2012, the market opened and the system
sent millions of erroneous orders in 45 minutes. The company lost $440 million --
more than their entire annual profit -- before engineers could shut it down.

**Root cause**: The deployment was manual and inconsistent. One server ran
different code than the others. Neither automated verification nor canary analysis
was in place. By the time humans identified the issue, the damage was done.

**Relevance to this chapter**: Blue-green and canary deployments solve exactly
this problem. With blue-green, you do not send traffic to any server until all
servers are on the new version. With canary analysis, the anomalous trading
behavior would have been detected within the first 1% of traffic and stopped.

**Key lesson**: Manual deployment to N servers, where N > 1, is a race condition
waiting to happen. Atomic deployment (all or nothing) is mandatory for financial
systems.

---

### Incident 2: Cloudflare BGP Leak (July 2019)

**Summary**: On July 2, 2019, a small network provider in Pennsylvania made a
BGP misconfiguration that caused a significant fraction of internet traffic to
route through their under-provisioned network. Cloudflare, which handles traffic
for millions of websites, saw massive degradation for about an hour.

**Root cause**: A configuration change by a third party (not Cloudflare) caused
traffic that normally took efficient routes to instead traverse a congested path.
Cloudflare's monitoring detected it quickly, but the fix required coordination
with external providers, taking about 60 minutes.

**Relevance to this chapter**: This incident illustrates the limits of monitoring.
You can observe what is happening with metrics and traces, but some failure modes
are externally caused and cannot be fixed through deployment or rollback. Your
SLO must account for this: your error budget includes time lost to third-party
failures, not just your own code.

**Key lesson**: SLO design must reflect what you can and cannot control. Your
error budget policy should distinguish between self-caused outages (require
engineering changes) and third-party caused (require vendor management).

---

### Incident 3: Slack Degradation (January 4, 2021)

**Summary**: Slack experienced a widespread outage affecting users for several
hours on the first business day of 2021 (the day millions of people returned to
work after the holidays). The root cause was a surge of reconnecting clients
after a maintenance window combined with a configuration change that had been
pushed just before the surge.

**Root cause**: Multiple factors compounded. A configuration change reduced
caching, increasing database load. At the same time, millions of users all
reconnected within minutes of each other -- a thundering herd. The combination
exceeded the system's capacity.

**Relevance to this chapter**: This is a capacity planning and canary deployment
failure. The configuration change should have been tested with simulated surge
conditions (load test). The thundering herd on return-from-holiday was a
predictable event that did not have a capacity plan.

**Key lesson**: Capacity planning must include non-linear events (holidays,
marketing launches, product launches). "Normal growth" extrapolation misses
these. SLOs should trigger a capacity review before known high-load events.

---

### Incident 4: Facebook Six-Hour Outage (October 4, 2021)

**Summary**: Facebook, Instagram, and WhatsApp were completely unavailable for
approximately six hours. The root cause was a BGP configuration change that
accidentally removed Facebook's own systems from the internet routing tables.
This also locked out Facebook's own engineers from internal tools, because
those tools required network paths that were also gone.

**Root cause**: A routine BGP update had a bug. The systems that should have
caught the bug were also unreachable via the same broken network path. It took
six hours partly because engineers had to physically access data centers to
restore connectivity.

**Relevance to this chapter**: A textbook example of what happens when your
runbooks, incident tools, and communication channels depend on the same
infrastructure that is failing. Your incident response tooling must be on
separate, isolated infrastructure from the service it monitors.

**Key lesson**: Runbooks must include out-of-band communication paths. If your
Slack, your incident management tool, and your dashboards are all hosted on
infrastructure that fails during a P1, you cannot respond to that P1 using
those tools. Have a backup: phone trees, secondary communication channels,
physically separated monitoring infrastructure.

---

### Incident 5: Google Cloud Multi-Region Storage Outage (November 2021)

**Summary**: A Google Cloud incident affected Cloud Storage across several regions
due to a metadata service failure. The incident persisted for several hours and
affected customers across multiple products.

**Root cause**: A metadata management plane issue caused storage operations to
fail. The issue was compounded by the fact that the same metadata plane was
responsible for storing the diagnostic data engineers needed to investigate the
failure.

**Relevance to this chapter**: This illustrates why observability infrastructure
must be isolated from the product infrastructure. When the database that stores
your metrics is the same one that is broken, you lose your visibility at the
exact moment you need it most.

**Key lesson**: Your monitoring stack, log aggregation, and trace storage must
be in separate failure domains from your product. This is a non-negotiable
design constraint for any system targeting 99.9%+ availability.

---

## 13. Brainstorming Questions

These questions are designed to help you think deeply about deployments and
operations. The best answers are not yes/no -- they require you to reason through
trade-offs.

1. Your team wants to go from monthly releases to daily deployments. What
   operational prerequisites must be in place before this is safe? List at
   least six specific requirements.

2. A stakeholder says "we need five nines (99.999%) availability." How do you
   respond? What questions do you ask? What would it actually require to
   achieve this, and is it worth it for most products?

3. Your error budget is 80% burned with two weeks left in the month. The product
   team wants to ship a major feature. Walk through your decision-making process.
   Who do you involve? What data do you use? What are the possible outcomes?

4. You are designing the observability strategy for a new payment processing
   service. What logs would you emit? What metrics? What would you trace? What
   alerts would you set? Walk through your complete reasoning.

5. A canary deployment is at 5% traffic. Your automated analysis shows: error
   rate is 0.08% on canary vs 0.05% on stable. P99 latency is 220ms on canary
   vs 195ms on stable. Business metrics (add-to-cart rate) are identical. Do
   you advance or abort? What would change your answer?

6. Your service's load test shows it can handle 8,000 RPS before database
   connections saturate. Current traffic is 3,000 RPS growing at 15% per month.
   Build a capacity plan: when do you need to act? What are your options?
   What are the trade-offs of each option?

7. A postmortem reveals that the same class of bug (a missing database index
   causing slow queries under load) has appeared in three different services in
   the past six months. What systemic changes do you propose?

8. A new service has no SLO defined. The team says "we do not have enough data
   yet." How do you get started? What is the minimum viable SLO definition?
   How do you evolve it as you learn more?

9. You are designing a runbook for a payment service that has five different
   failure modes. The runbook needs to be usable by an engineer who has never
   seen the service before, at 3 AM, when they have just been woken up. What
   are the most important design principles for this runbook?

10. Your unit cost per API call is $0.008 today. The business wants to grow 10x
    in the next 18 months. If costs scale linearly, what is the new monthly
    infrastructure bill? What strategies would you use to achieve sub-linear
    cost scaling?

11. A developer argues: "Feature flags add code complexity and technical debt.
    We should just do better testing so we never need to roll back." How do you
    respond? What are the limits of testing as a substitute for rollback
    capability?

12. Your team currently does blue-green deployments. A new service is a
    stateless API with 50 microservices, each with independent release cycles.
    Does blue-green still make sense? What deployment strategy would you
    recommend and why?

13. An on-call engineer pages you into a P1 and says: "I can't tell if the
    problem started before or after the deployment." What three steps do you
    take first?

14. The product team argues: "We should not waste engineering time on capacity
    planning. If we run out of capacity we will scale up quickly -- cloud is
    elastic." What is the flaw in this reasoning? Give three concrete examples
    of where "scale up quickly" fails.

15. Your SLA promises 99.9% uptime. Your internal SLO is 99.95%. Your actual
    measured uptime this month is 99.92%. Walk through the implications: for
    your SLA, for your error budget, for your deployment velocity, and for
    the conversation you need to have with your product team.

16. A service goes down. The on-call engineer rolls back the deployment and the
    service recovers. The postmortem action item is "don't deploy on Fridays."
    Is this a good action item? What is wrong with it? What would a better
    action item look like?

17. You are joining a company that has no defined incident severity levels. Every
    alert wakes up the same people regardless of customer impact. What problems
    does this cause? How would you propose fixing it?

18. A database migration is required as part of a new feature. The migration
    adds a NOT NULL column with no default to a table with 200 million rows.
    Why is this dangerous? How do you deploy this safely with zero downtime?

19. Your service's p99 latency has been slowly increasing for 3 weeks -- from
    180ms to 280ms -- but your error rate is unchanged. No deployments have
    happened. What might be causing this? List at least five hypotheses and
    describe how you would investigate each.

20. You are setting up monitoring for a new service. Someone says "just alert
    when CPU goes above 80%." Why is this an incomplete monitoring strategy?
    What else would you add?

21. Your team is spending 40% of sprint time on on-call toil -- manual
    investigations, manual restarts, manual capacity adjustments. How do you
    prioritize fixing this? What is the argument you make to your manager?

22. A startup says "we do not need SLOs yet -- we are too small." At what point
    does a company need SLOs? What early signals indicate it is time to start?

---

## 14. Exercises

### Exercise 1: Write a Runbook

Pick a service you are familiar with (or invent one: an e-commerce checkout
service). Write a complete runbook for one failure mode: "checkout is returning
500 errors for more than 2% of requests."

Your runbook must include:
- Header with severity, owner, and triggering alert name.
- Triage steps (what to check first, with exact dashboard/query instructions).
- At least three diagnostic paths (database issue vs application bug vs
  deployment issue).
- Mitigation options with risks for each.
- Escalation path.
- Communication template.

Evaluation criteria: Could a new engineer who has never seen this service use
your runbook at 3 AM without calling anyone for the first 15 minutes?

---

### Exercise 2: Design a Canary Deployment

You are deploying a change to a payment processing service that switches from
one payment gateway to another. This change could affect payment success rates.

Design a complete canary rollout plan:
- What percentage steps will you use? (1%, 5%, 25%, 50%, 100%? Or different?)
- How long will you hold at each step?
- What metrics will you monitor at each step?
- What are your pass/warn/fail thresholds for each metric?
- Who gets paged if the canary fails?
- What does the rollback procedure look like?
- What database or state considerations exist (are there any)?

---

### Exercise 3: Calculate Error Budgets

Your service has two SLOs:
1. Availability: 99.95% over 30 days.
2. Latency: 95% of requests respond in under 200ms.

This month's events:
- Day 3: Bad deploy caused 22 minutes of elevated errors (> 1% error rate).
- Day 11: Database maintenance caused 8 minutes of full downtime.
- Day 18: A slow query caused 3 hours where 20% of requests exceeded 200ms.

Calculate:
- Initial error budget (in minutes) for each SLO.
- Remaining budget after each event.
- What deployment policy applies for the rest of the month?
- If a new feature deployment is planned for Day 25, what risks does the team
  need to communicate to the product team?

---

### Exercise 4: Build a Cost Model

You run an e-commerce API with these characteristics:
- 2 million API calls per day.
- Infrastructure costs: $8,000/month compute, $3,000/month database,
  $2,000/month data transfer, $1,500/month monitoring and logging.
- The business projects 3x growth in 12 months.

Build a cost model:
- Current cost per 1,000 API calls.
- Projected cost at 3x if costs scale linearly.
- Which cost categories are likely to scale linearly vs sub-linearly?
- What optimizations would you investigate to achieve sub-linear cost scaling?
- What is the cost per API call you need to reach to maintain margins if the
  product team wants to keep the same infrastructure budget?

---

### Exercise 5: Design an Observability Strategy

A new service is being built: a real-time inventory management system for a
retailer. It receives events from stores (items sold, items received, items
returned) and maintains accurate inventory counts that other services query.

Design the complete observability strategy:
- What logs should the service emit? (Give five specific log events with fields.)
- What metrics should be tracked? (Give six specific metrics.)
- What should be traced? (Describe the trace structure for two key request types.)
- What are the four most important alerts? (Metric, threshold, severity.)
- How would you correlate a customer-facing inventory error (seen in the
  frontend) back to its root cause in this service?

---

### Exercise 6: Rollback Decision Under Pressure

It is 2:47 PM on a Friday. Your team deployed a new recommendation algorithm
at 2:30 PM. Since then:
- Error rate: stable at 0.05% (no change).
- P99 latency: increased from 180ms to 340ms (89% increase).
- Revenue metrics: add-to-cart rate dropped from 4.2% to 3.1% (26% drop).
- Error budget: 35% remaining for the month.
- The fix is unclear -- the engineer who wrote the algorithm is in a meeting.

Answer these questions:
1. Using the decision tree from Section 9, walk through the rollback decision.
2. What is your decision? Roll back or fix forward?
3. Who do you communicate with and what do you say?
4. If you roll back, what is the message to the product team?
5. What does your postmortem focus on?

---

## 15. Homework

### Short-form assignments (pick two)

**Assignment A: Deployment audit.**
Pick a service or application you work on. Identify the current deployment
strategy. Write a one-page analysis covering: what strategy is used (blue-green,
canary, rolling, or none), what the rollback procedure is, how long a rollback
takes, and what one change would most improve the safety of deployments.

**Assignment B: SLO draft.**
For a service you own or are familiar with, draft a complete SLO document:
define at least two SLIs, set targets for each, calculate the error budget per
30 days, and write the error budget policy (what the team commits to doing at
each budget depletion level).

**Assignment C: Runbook gap analysis.**
Review the existing runbooks for a service your team operates. For each runbook:
- Is it up to date with the current architecture?
- Does it have exact commands or only vague guidance?
- Does it cover the three most likely failure modes?
- When was it last tested?

Write a prioritized list of runbook improvements with owners and timelines.

**Assignment D: Cost model.**
Access your team's cloud cost dashboard. Build a model for one service: identify
the top three cost categories, calculate cost per unit (per request, per user,
or per transaction), and identify two cost optimization opportunities with
estimated savings.

---

### Deep dive (pick one)

**Deep Dive 1: Implement automated canary analysis.**
Using a tool of your choice (Flagger, Argo Rollouts, or manual Prometheus
queries), implement a canary analysis pipeline for one service. The pipeline
must: compare error rate and latency between canary and stable, make a
pass/fail decision automatically, and either advance or abort without human
intervention. Document what you built and what you learned.

**Deep Dive 2: Run a game day.**
A game day is a controlled exercise where you intentionally cause a failure in
a test environment to practice incident response. Design and run a game day for
your team: choose a failure mode (e.g., database connection pool exhaustion),
trigger it in staging, run the incident response process as if it were real
(including runbook, incident commander, communication templates), and write a
postmortem. Present findings to your team.

**Deep Dive 3: Capacity planning model.**
Build a capacity model for a service your team operates. The model must include:
current utilization measurements, a growth projection (using actual business
growth data), identification of the bottleneck component, the date at which you
hit 80% of maximum capacity at current growth rates, and at least two scaling
options with cost and complexity trade-offs for each.

---

### Interview preparation questions

Practice answering these out loud. Time yourself. Aim for 3-4 minutes for
each. A strong answer uses a specific example from your own experience, covers
the trade-offs, and concludes with what you would do differently.

1. "Tell me about a production incident you were involved in. What was your
   role? What did you learn?"

2. "How do you decide when to roll back a deployment vs fix forward?"

3. "Walk me through how you would design the deployment strategy for a new
   payment processing service."

4. "What SLOs would you set for a search service? How did you arrive at those
   numbers?"

5. "How do you think about the relationship between feature development velocity
   and system reliability?"

6. "Describe the observability strategy you would build for a service you are
   responsible for."

---

## Deeper Dives: Concepts That Separate Good Engineers from Great Ones

### Blue-Green in Practice: The Warm-Up Problem

There is a subtlety with blue-green that bites teams the first time they do it
correctly: the new (green) environment needs to be fully warmed up before it
receives production traffic.

Think about a restaurant kitchen that has been cold all day. When the chef walks
in for dinner service and fires up the stoves, the kitchen is not at operating
temperature yet. The first orders out of a cold kitchen take longer than normal.
If you put a customer in a chair and hand them a menu before the kitchen is ready,
their experience is bad even though the kitchen is technically "open."

The same happens with software. Your green environment just launched. The JVM
has not JIT-compiled the hot code paths. The connection pools are all empty and
need to be established. The CPU caches for frequently accessed data are cold.
Your in-process caches are empty. The first 5-10 minutes of traffic to a brand
new environment is always slower and more error-prone than steady-state traffic.

If you switch the load balancer immediately after deploying green, you send real
users through this cold startup. Here is what you need to do instead:

```
+---------------------------------------------------------------------+
|             SOLVING THE WARM-UP PROBLEM IN BLUE-GREEN               |
+---------------------------------------------------------------------+
|                                                                     |
|  OPTION 1 -- SYNTHETIC TRAFFIC WARM-UP                              |
|  Before switching the load balancer:                                |
|  - Send synthetic (fake) traffic through green for 5-10 minutes     |
|  - Run your most common request types                               |
|  - Let JIT compile, pools fill, caches warm                         |
|  - Monitor green's metrics during warm-up: they should look normal  |
|  - Then switch real traffic                                         |
|                                                                     |
|  OPTION 2 -- CANARY-WITHIN-BLUE-GREEN                               |
|  - Switch 1% of real traffic to green                               |
|  - Wait 5 minutes for warm-up to complete                           |
|  - If metrics look normal, switch to 100%                           |
|  - This is a hybrid approach                                        |
|                                                                     |
|  OPTION 3 -- SLOW RAMP                                              |
|  - 5% for 5 minutes -> 20% for 5 minutes -> 100%                   |
|  - The ramp itself provides the warm-up time                        |
|  - This blurs the line between blue-green and canary                |
|  - Often the most practical in real systems                         |
|                                                                     |
|  COMMON MISTAKE: switching 100% of traffic immediately after        |
|  deploy, then blaming the new version for high latency that is      |
|  actually just cold start behavior.                                  |
+---------------------------------------------------------------------+
```

### Advanced Canary: Demographic Targeting

A basic canary sends random 1% of traffic to the new version. An advanced canary
targets specific user segments. This allows you to get meaningful signal while
controlling who sees the new behavior.

**Why random 1% is sometimes wrong:**

Imagine you are rolling out a change to the payments flow. A random 1% of traffic
includes a mix of users: some are first-time buyers, some are returning customers,
some are in the US, some are in the EU (with different regulatory requirements),
some are on mobile, some on desktop.

If the new payments flow only breaks for EU users due to a GDPR compliance change
that you forgot to handle, your random 1% canary might not give you enough EU
traffic to detect the problem. With 1% of traffic you might get 1000 EU users in
30 minutes. If the failure rate is 5% among EU users, that is 50 errors out of
1000 EU requests -- but the overall error rate increase is tiny (50 errors out of
perhaps 100,000 total canary requests = 0.05% error rate increase). The automated
canary analysis might not flag this as significant.

The solution: target your canary at the segment most likely to expose problems.

```
+---------------------------------------------------------------------+
|              DEMOGRAPHIC CANARY TARGETING STRATEGIES                |
+---------------------------------------------------------------------+
|                                                                     |
|  STRATEGY 1 -- INTERNAL USERS FIRST                                 |
|  - Send all traffic from your company's IP ranges to canary         |
|  - If the change breaks something obvious, your own engineers see   |
|    it before customers do                                           |
|  - Risk: internal usage patterns may not match customer patterns    |
|                                                                     |
|  STRATEGY 2 -- POWER USERS                                          |
|  - Send traffic from your most active users to canary               |
|  - They use more features, find more bugs                           |
|  - Risk: if something breaks for them, impact is higher than        |
|    breaking it for casual users                                     |
|                                                                     |
|  STRATEGY 3 -- BETA USERS (opt-in)                                  |
|  - Some users opt in to receive early releases                      |
|  - They expect occasional rough edges, are more forgiving           |
|  - They often report bugs proactively                               |
|  - This is how Chrome and Firefox run their Beta channels           |
|                                                                     |
|  STRATEGY 4 -- ONE GEOGRAPHIC REGION                                |
|  - Rollout to one country or region first (e.g., New Zealand,       |
|    which is first to see the next day due to timezone)              |
|  - Smaller blast radius + similar usage patterns to global          |
|  - Netflix calls this a "dark launch" in some contexts              |
|                                                                     |
|  BEST PRACTICE: combine strategies. Start with internal users for   |
|  1 hour, then 1% random, then 10%, then 100%.                       |
+---------------------------------------------------------------------+
```

### Observability: The Missing Fourth Pillar -- Profiling

Many engineers learn "logs, metrics, traces" and think that is the complete
observability picture. There is a fourth pillar that matters at high scale:
**continuous profiling**.

Think of a doctor again. Logs are the patient diary. Metrics are vital signs.
Traces are an MRI. Profiling is something different: it is like attaching sensors
to every muscle and nerve and recording exactly how much work each one does during
a 10-minute exercise session. It tells you not just that the patient ran slowly,
but which specific muscle group is under-developed and costing efficiency.

Continuous profiling takes a statistical sample of what the CPU is doing every
few milliseconds -- which function is executing, how much memory it allocates,
how long each hot code path takes. Unlike traces (which show you the time spent
in each service), profiling shows you the time spent in each line of code.

```
+---------------------------------------------------------------------+
|           CONTINUOUS PROFILING vs DISTRIBUTED TRACING               |
+---------------------------------------------------------------------+
|                                                                     |
|  DISTRIBUTED TRACE (what you already know):                         |
|  Request 7f3a:                                                      |
|    Order Service: 180ms total                                       |
|      -> DB read: 45ms                                               |
|      -> Price Service: 22ms                                         |
|      -> Payment: 80ms                                               |
|  --> Tells you WHICH SERVICE is slow                                 |
|                                                                     |
|  CONTINUOUS PROFILE (the deeper view):                              |
|  Order Service breakdown of 180ms:                                  |
|    -> JSON serialization: 55ms (31% of time -- suspicious!)         |
|    -> DB connection acquisition: 40ms (22%)                         |
|    -> Business logic: 12ms (7%)                                     |
|    -> Network I/O wait: 73ms (41%)                                  |
|  --> Tells you WHICH CODE inside the service is slow                 |
|                                                                     |
|  LESSON: you can have excellent traces and still have no idea why   |
|  Order Service takes 180ms internally. Profiling gives you that     |
|  visibility. At high scale (millions of requests/day), the 55ms     |
|  JSON serialization cost translates to thousands of CPU-hours per   |
|  month -- a real cost optimization opportunity.                     |
|                                                                     |
|  Tools: Pyroscope, Parca, Google Cloud Profiler, Datadog Profiling  |
+---------------------------------------------------------------------+
```

### SLO Multi-Window Approach: Why 30-Day Windows Are Not Enough

The SLO discussion in Section 6 used a 30-day window. Real SLO implementations
use multiple windows simultaneously. Here is why that matters.

Imagine your service has a 30-day error budget of 43.2 minutes. It is Day 29.
You have used 40 minutes of budget this month. There are 3.2 minutes left. The
product team wants to know: can we do a deployment?

The 30-day window says: barely. 3.2 minutes is not much, but it is technically
not zero.

But now imagine that all 40 minutes of budget were burned in the last 2 days --
not spread across the month. That means the service has been in a degraded state
for the last 48 hours. The system is not in a healthy operational posture right
now. Doing a deployment in this state is much riskier than if the budget had
been burned steadily over 29 days.

The multi-window approach adds a short window (typically 1 hour and 6 hours) to
catch "right now is actually bad" situations:

```
+---------------------------------------------------------------------+
|              MULTI-WINDOW SLO EVALUATION                            |
+---------------------------------------------------------------------+
|                                                                     |
|  WINDOW 1: 5-minute window                                          |
|  Error budget: 0.1% * 5 min = 0.3 seconds of errors allowed        |
|  Purpose: Is something actively broken RIGHT NOW?                   |
|  Action if burned: page immediately                                 |
|                                                                     |
|  WINDOW 2: 1-hour window                                            |
|  Error budget: 0.1% * 60 min = 3.6 minutes                         |
|  Purpose: Is this an ongoing sustained problem?                     |
|  Action if burned: escalate to team lead                            |
|                                                                     |
|  WINDOW 3: 6-hour window                                            |
|  Error budget: 0.1% * 360 min = 21.6 minutes                       |
|  Purpose: Is there a degraded but not critical trend?               |
|  Action if burned: investigate and plan intervention                |
|                                                                     |
|  WINDOW 4: 30-day window                                            |
|  Error budget: 0.1% * 43,200 min = 43.2 minutes                    |
|  Purpose: Deployment velocity policy                                |
|  Action if burned: feature freeze, reliability sprint               |
|                                                                     |
|  EVALUATION RULE:                                                   |
|  If any window is > 50% burned, the service is in a questionable   |
|  state. If any window is > 100% burned, act immediately.            |
|                                                                     |
|  This is sometimes called the "burn rate" approach. Google's SRE    |
|  workbook describes this as the recommended method for              |
|  production-grade SLO alerting.                                     |
+---------------------------------------------------------------------+
```

### Capacity Planning: The Thundering Herd Problem

The capacity planning discussion in Section 7 covered linear growth models. But
the most common capacity surprise is not gradual growth -- it is sudden simultaneous
demand from many clients at once. This is called the thundering herd.

Think about a popular music venue releasing tickets at 10 AM on a Friday. A
million fans all hit the ticketing website at exactly 10:00:00. The site was
perfectly fine at 9:59. At 10:00 it has 1,000x normal traffic simultaneously.

Thundering herd problems appear in several specific patterns:

**Pattern 1 -- Cache stampede:**
Your cache holds 1 million items. A cache server fails and restarts empty. Every
client that tries to read from the cache misses. Every miss goes directly to the
database. The database receives 50x its normal query rate and falls over. The
cache was the shield; when the shield disappeared, the database was exposed to
raw traffic it was never sized for.

```
+---------------------------------------------------------------------+
|              CACHE STAMPEDE PATTERN                                  |
+---------------------------------------------------------------------+
|                                                                     |
|  NORMAL OPERATION:                                                  |
|  [100,000 requests/sec] -> [Cache] -> [Cache HIT: 95%]              |
|                               |                                     |
|                               -> [Cache MISS: 5%] -> [Database]     |
|                                                      5,000 req/sec  |
|                                                      (manageable)   |
|                                                                     |
|  AFTER CACHE RESTART (empty cache):                                 |
|  [100,000 requests/sec] -> [Empty Cache] -> [MISS: 100%]            |
|                                                  |                  |
|                                                  v                  |
|                                            [Database]               |
|                                          100,000 req/sec            |
|                                          (20x over capacity!)       |
|                                          --> Database falls over     |
|                                          --> Everything falls over   |
|                                                                     |
|  MITIGATIONS:                                                        |
|  1. Cache warming: pre-populate the cache after restart before      |
|     routing traffic to it                                           |
|  2. Probabilistic cache expiry: instead of all keys expiring at     |
|     the same time, add random jitter to expiry times                |
|  3. Background refresh: refresh cache keys before they expire,      |
|     so the old value is always served while the new one is fetched  |
|  4. Request coalescing: if 100 requests all miss on the same key,   |
|     only send ONE request to the database, then share the result    |
+---------------------------------------------------------------------+
```

**Pattern 2 -- Retry storm:**
Your API starts returning errors due to a brief database blip. All clients
retry. But they all retry at the same time (no jitter). The retries arrive in
waves, each wave coinciding. The database blip is over in 2 seconds but the
retry storm keeps the system degraded for 20 more minutes.

```
+---------------------------------------------------------------------+
|              RETRY STORM PATTERN AND MITIGATION                      |
+---------------------------------------------------------------------+
|                                                                     |
|  BAD RETRY PATTERN (no jitter):                                     |
|  All clients fail at T=0. All retry at T=1 second. All fail again.  |
|  All retry at T=2 seconds. Synchronized waves of load.             |
|                                                                     |
|  GOOD RETRY PATTERN (with exponential backoff + jitter):            |
|  Client 1 fails. Retries at T=1.0 + random(0, 0.5) = T=1.3 sec    |
|  Client 2 fails. Retries at T=1.0 + random(0, 0.5) = T=1.1 sec    |
|  Client 3 fails. Retries at T=1.0 + random(0, 0.5) = T=1.47 sec   |
|                                                                     |
|  Result: retries are spread out. Database receives a smooth stream  |
|  of retries instead of a synchronized hammer.                       |
|                                                                     |
|  EXPONENTIAL BACKOFF WITH JITTER:                                   |
|  Attempt 1: wait 1s +/- 0.5s jitter                                 |
|  Attempt 2: wait 2s +/- 1s jitter                                   |
|  Attempt 3: wait 4s +/- 2s jitter                                   |
|  Attempt 4: wait 8s +/- 4s jitter                                   |
|  Max attempts: 5 (never retry forever)                              |
|                                                                     |
|  This is not optional in a distributed system. Every service that   |
|  calls another service must implement this pattern.                 |
+---------------------------------------------------------------------+
```

### Cost Modeling: The Hidden Costs That Break Your Budget

When engineers build cost models, they typically account for the obvious: compute,
storage, database. The hidden costs that surprise finance teams every quarter:

**Data egress costs:**
Cloud providers charge significantly for data leaving their network. AWS charges
$0.09 per GB for data transferred out to the internet from US East. If your
service serves 1TB of video or images per day to users, that is $90/day = $2,700
per month in data transfer alone -- before a single server is counted.

Many teams discover this cost only after their cloud bill quadruples. The fix:
use a CDN (content delivery network) to serve user-facing content from edge
locations. CDN providers have negotiated wholesale bandwidth rates that are 10-20x
cheaper per GB than your cloud provider's public egress rate.

**Log and monitoring costs:**
A service that emits 100GB of logs per day to CloudWatch Logs at $0.50/GB
ingestion = $50/day = $1,500/month. If you have 20 services at this volume:
$30,000/month just for log ingestion. Many teams only discover this when their
observability bill is 40% of their total cloud spend.

```
+---------------------------------------------------------------------+
|           HIDDEN COST CATEGORIES AND ORDER OF MAGNITUDE             |
+---------------------------------------------------------------------+
|                                                                     |
|  COST CATEGORY        | OFTEN MISSED BECAUSE...                     |
|  ---------------------|--------------------------------------------  |
|  Data egress          | Not visible in compute line items            |
|  Log ingestion        | Grows silently with traffic                   |
|  Database storage     | Grows with every write, never shrinks         |
|  Snapshot / backup    | Accumulates over time, never cleaned up       |
|  Support contracts    | Fixed cost not tied to usage                  |
|  Data transfer        | Between services in different AZs             |
|  (cross-AZ)           | often 2 cents/GB, adds up at scale           |
|  Idle resources       | Dev/staging environments running 24/7         |
|  Licensing            | Third-party tools with per-seat pricing        |
|                                                                     |
|  RULE: any cost that scales with data volume will eventually        |
|  dominate your infrastructure budget. Model these from day one.     |
+---------------------------------------------------------------------+
```

**Cross-AZ traffic costs:**
A common architecture: your API servers in AZ-1 call your database in AZ-2 for
high availability. AWS charges $0.02/GB for data transferred between Availability
Zones in the same region. If your services pass 500GB of data per day between
AZs (common for a busy API), that is $10/day = $300/month. At 50 services with
cross-AZ traffic, this becomes a significant monthly expense that no one modeled.

The solution is not to stop using multiple AZs (that breaks high availability).
The solution is to model this cost upfront and look for opportunities to reduce
unnecessary cross-AZ traffic (co-locate services that communicate heavily).

### Rollback Strategies: The Soft Launch Approach

Beyond blue-green and canary, there is a third deployment pattern that is
especially useful for major product launches: the **soft launch** (sometimes
called a dark launch or shadow mode).

The analogy: a new restaurant opens for a "friends and family" dinner the night
before their public opening. Real food, real kitchen, real service -- but only
a small trusted group of guests. The team can test everything under realistic
conditions with a forgiving audience before the public arrives.

A software soft launch works the same way: the new feature is deployed to
production infrastructure and tested with a small group of real users (employees,
beta users, or a single geography) before it is open to everyone. The key
difference from canary: in a soft launch, users know they are seeing a new
feature and have agreed to it. In a canary, users do not know.

```
+---------------------------------------------------------------------+
|              SOFT LAUNCH vs CANARY vs BLUE-GREEN                     |
+---------------------------------------------------------------------+
|                                                                     |
|  SOFT LAUNCH:                                                       |
|  - Small, opted-in user group sees new feature                      |
|  - Users know they are on the new version                           |
|  - Feedback is qualitative AND quantitative                         |
|  - Long bake time (days to weeks)                                   |
|  - Great for product validation, not just technical validation       |
|                                                                     |
|  CANARY:                                                            |
|  - Small random percentage of all users (1-10%)                     |
|  - Users do not know they are on canary                             |
|  - Feedback is purely quantitative (metrics)                        |
|  - Short bake time (hours)                                          |
|  - Great for technical validation of a single deployment             |
|                                                                     |
|  BLUE-GREEN:                                                        |
|  - Binary: 0% or 100% of users                                      |
|  - Users do not know about the switch                               |
|  - No validation with real traffic before full cutover              |
|  - Near-instant cutover and rollback                                |
|  - Great for fast, atomic changes with strong pre-testing            |
|                                                                     |
|  REAL PRODUCTION PATTERN:                                           |
|  Use all three together:                                            |
|  1. Soft launch to beta users for 1 week (product validation)       |
|  2. Canary at 1% -> 10% -> 50% over 2 days (technical validation)   |
|  3. Blue-green switch to 100% (atomic final cutover)                |
+---------------------------------------------------------------------+
```

### Advanced Incident Response: The OODA Loop

Military strategist John Boyd developed the OODA Loop for fighter pilot
decision-making: Observe, Orient, Decide, Act. This framework applies directly
to incident response.

```
+---------------------------------------------------------------------+
|               THE OODA LOOP IN INCIDENT RESPONSE                    |
+---------------------------------------------------------------------+
|                                                                     |
|  OBSERVE                                                            |
|  What is actually happening?                                        |
|  - Read the alert text carefully. What metric triggered?            |
|  - Look at dashboards: what changed? When?                          |
|  - Check for recent deployments, config changes, cron jobs          |
|  - What is the blast radius? (how many users, what features)        |
|  Time budget: 3-5 minutes                                           |
|                                                                     |
|  ORIENT                                                             |
|  What does this pattern mean?                                       |
|  - Have you seen this before? Check past incidents / postmortems    |
|  - What is the most likely cause given what you see?                |
|  - What are the top 3 hypotheses? Rank by likelihood.               |
|  Time budget: 2-3 minutes                                           |
|                                                                     |
|  DECIDE                                                             |
|  What is your next action?                                          |
|  - Pick the fastest test of your top hypothesis                     |
|  - Do not try to test all hypotheses at once                        |
|  - If in doubt: mitigate first (rollback), diagnose second          |
|  Time budget: 1-2 minutes                                           |
|                                                                     |
|  ACT                                                                |
|  Execute clearly, communicate what you are doing.                   |
|  - If you are Incident Commander: announce what you are doing        |
|  - If you are a responder: confirm with IC before acting            |
|  - Announce results: "I rolled back the deployment. Error rate is   |
|    still elevated. The deployment was not the cause."               |
|  Then loop: OBSERVE the new state and repeat.                       |
|                                                                     |
|  COMMON MISTAKE: spending 25 minutes in ORIENT (theorizing)         |
|  when you should have ACTed to test a hypothesis after 3 minutes.  |
|  An action provides data. Theorizing does not.                      |
+---------------------------------------------------------------------+
```

### Incident Response: Communication Templates

One of the most overlooked parts of incident response is communicating to
customers and stakeholders. Engineers who are excellent at debugging often
struggle here because they are wired to dig into the problem, not explain it.

Bad status page update: "We are currently experiencing issues. Our team is
investigating. We apologize for the inconvenience."

This is useless to customers. It says nothing about what is broken, how many
users are affected, or when it will be fixed.

Good status page update:

```
+---------------------------------------------------------------------+
|         INCIDENT COMMUNICATION TEMPLATE (customer-facing)           |
+---------------------------------------------------------------------+
|                                                                     |
|  [TIME] -- INVESTIGATING                                            |
|  We are investigating elevated error rates affecting checkout on    |
|  our platform. Approximately 15% of checkout attempts are failing   |
|  with a 503 error. Users can retry and approximately 80% of retries |
|  succeed. Our team identified this at [TIME] and is actively        |
|  working on a fix. We will post an update in 15 minutes.            |
|                                                                     |
|  KEY ELEMENTS:                                                      |
|  - What is broken (checkout, not "the platform")                    |
|  - How many users affected (15%, not "some users")                  |
|  - Whether there is a workaround (retry works 80% of the time)      |
|  - When you will give the next update (15 minutes -- then honor it) |
|                                                                     |
|  [TIME+15] -- UPDATE                                                |
|  We have identified the root cause: a configuration change deployed  |
|  at [TIME-X] increased database connection pool size beyond the      |
|  supported limit, causing connection exhaustion under load. We are  |
|  rolling back this change now. ETA to resolution: 10 minutes.       |
|                                                                     |
|  [TIME+25] -- RESOLVED                                              |
|  The issue is resolved. Checkout error rates have returned to        |
|  normal levels (< 0.1%). Users who experienced errors during the    |
|  window from [START TIME] to [END TIME] should retry their          |
|  transactions. No data was lost. We apologize for the disruption.   |
|  A full postmortem will be published within 72 hours.               |
+---------------------------------------------------------------------+
```

### Capacity Planning: The Autoscaling Illusion

A common mistake at growing companies: "We are on cloud. We have autoscaling.
We do not need capacity planning."

This reasoning fails in four specific ways:

**Failure 1 -- Autoscaling lag:**
AWS EC2 autoscaling takes 2-5 minutes to launch a new instance, pass health
checks, and receive traffic. During a sudden spike (traffic doubles in 30
seconds), your existing instances are at capacity and failing for those 2-5
minutes. Autoscaling helps for gradual growth. It does not help for sudden spikes.

**Failure 2 -- Database autoscaling is limited:**
Compute autoscales easily. Databases do not. Adding a read replica takes 10-20
minutes for RDS. Increasing RDS instance size requires a maintenance window
with several minutes of downtime. You cannot autoscale your way out of a
database bottleneck in real time.

**Failure 3 -- Cost surprise:**
If your autoscaling is misconfigured and your service gets hit by a traffic spike
(legitimate or DDoS), you may autoscale to 100x normal capacity before your
team notices. Cloud providers generally do not cap costs automatically. Teams
have received surprise bills for tens of thousands of dollars from autoscaling
events. Capacity planning includes setting autoscaling limits and cost alerts.

**Failure 4 -- Regional capacity:**
Cloud regions have finite capacity. During major events (COVID-19 surge, major
sporting events), cloud regions sometimes cannot provision new instances quickly
because everyone is scaling simultaneously. Your autoscaling policy says "add
100 instances" but AWS says "sorry, no c5.2xlarge available in this AZ." You
need capacity reservations for predictable high-demand events.

```
+---------------------------------------------------------------------+
|          WHAT AUTOSCALING COVERS vs WHAT IT DOES NOT COVER          |
+---------------------------------------------------------------------+
|                                                                     |
|  AUTOSCALING HANDLES WELL:                                          |
|  + Gradual traffic growth over hours                                |
|  + Daily traffic patterns (peak business hours)                     |
|  + Recovering from instance failures (replace failed nodes)         |
|  + Reducing cost during low-traffic periods (scale down at night)   |
|                                                                     |
|  AUTOSCALING DOES NOT HANDLE:                                       |
|  - Sudden traffic spikes faster than provisioning time              |
|  - Database bottlenecks (databases do not autoscale like compute)   |
|  - Cost overruns from unexpected scale events                       |
|  - Regional capacity constraints during global events               |
|  - Stateful services (you cannot add a database primary mid-traffic) |
|                                                                     |
|  CAPACITY PLANNING STILL REQUIRED FOR:                              |
|  - Database sizing (right-size the primary, plan replica additions)  |
|  - Predictable high-traffic events (Black Friday, product launches) |
|  - Regional failover capacity (the backup region must handle 2x     |
|    traffic if primary fails)                                        |
|  - License-based services (each instance needs a license)           |
+---------------------------------------------------------------------+
```

### The Relationship Between All Nine Concepts

This chapter covers nine concepts. At L5, you know each one independently. At
L6, you understand how they form a single interconnected system. Here is a map
of the key dependencies:

```
+---------------------------------------------------------------------+
|               HOW THE NINE CONCEPTS CONNECT                         |
+---------------------------------------------------------------------+
|                                                                     |
|   [Blue-Green] <----> [Canary]                                      |
|        |                  |                                         |
|        v                  v                                         |
|   [Rollback Strategy] <---- "What if it goes wrong?"               |
|        |                                                            |
|        v                                                            |
|   [SLO / Error Budget] <--- "How much can we afford to be wrong?"  |
|        |                                                            |
|        v                                                            |
|   [Incident Response] <--- "What do we do when we are wrong?"      |
|        |                                                            |
|        v                                                            |
|   [Observability] <--- "How do we know something is wrong?"        |
|        |                                                            |
|        v                                                            |
|   [Capacity Planning] <--- "Are we sized for future demand?"       |
|        |                                                            |
|        v                                                            |
|   [Cost Modeling] <--- "Can we afford the capacity we need?"       |
|                                                                     |
|  THE FEEDBACK LOOPS:                                                |
|  - Observability data feeds capacity planning (we see 80% CPU ->   |
|    plan to scale)                                                   |
|  - Incident postmortems drive rollback strategy improvements         |
|  - Error budget policy drives deployment strategy choice             |
|  - Cost models constrain capacity planning choices                  |
|  - Runbooks reference observability dashboards and rollback steps   |
|                                                                     |
|  A Staff engineer sees the whole picture. Every deployment          |
|  decision affects all nine nodes in this graph.                     |
+---------------------------------------------------------------------+
```

---

## The Deployment Pipeline: Everything Before Traffic Hits Production

Many engineers focus on what happens when a deployment arrives in production.
Equally important is the pipeline that runs before that moment: the automated
gates that catch problems in lower environments so real users never see them.

Think of an automobile factory's quality control line. Each car body passes
through dozens of inspection stations before it reaches the paint shop and
final assembly. Each station catches a class of defects: weld integrity, panel
alignment, dimension tolerances. By the time the car leaves the factory, hundreds
of checks have already passed. The final customer test drive is the last
gate, not the first.

Your CI/CD pipeline is the same assembly line for software.

### The stages of a production-grade deployment pipeline

```
+---------------------------------------------------------------------+
|          PRODUCTION-GRADE DEPLOYMENT PIPELINE                       |
+---------------------------------------------------------------------+
|                                                                     |
|  [Code commit to main branch]                                       |
|         |                                                           |
|         v                                                           |
|  STAGE 1 -- FAST CHECKS (< 5 minutes, blocks merge)                |
|  - Unit tests (must pass)                                           |
|  - Linting and static analysis                                      |
|  - Security scanning (known vulnerable dependencies)               |
|  - License compliance check                                         |
|         |                                                           |
|         v                                                           |
|  STAGE 2 -- BUILD AND PACKAGE (< 10 minutes)                        |
|  - Build artifact (Docker image, binary, JAR)                       |
|  - Scan built artifact for vulnerabilities                          |
|  - Tag with version + commit SHA                                    |
|  - Push to artifact registry                                        |
|         |                                                           |
|         v                                                           |
|  STAGE 3 -- INTEGRATION TESTS (< 20 minutes)                        |
|  - Deploy to ephemeral test environment                             |
|  - Run integration tests (service + database + external mocks)      |
|  - Run API contract tests                                           |
|  - Tear down ephemeral environment                                  |
|         |                                                           |
|         v                                                           |
|  STAGE 4 -- STAGING DEPLOYMENT (< 10 minutes)                       |
|  - Deploy to staging (production-like environment)                  |
|  - Run smoke tests against staging                                  |
|  - Run end-to-end tests                                             |
|  - Performance regression test (latency must not regress > 10%)     |
|         |                                                           |
|         v                                                           |
|  STAGE 5 -- PRODUCTION DEPLOYMENT                                   |
|  - Canary to 1%, monitor for 15 minutes                             |
|  - Advance to 10%, monitor for 15 minutes                           |
|  - Advance to 100% OR full blue-green switch                        |
|  - Post-deploy smoke test                                           |
|  - Alert on-call engineer: "Deployment complete, monitor for 30min" |
|         |                                                           |
|         v                                                           |
|  STAGE 6 -- POST-DEPLOY OBSERVATION WINDOW                          |
|  - 30-minute bake time with active monitoring                       |
|  - Automated check: error rate vs pre-deploy baseline               |
|  - If all clear: deployment declared successful                     |
|  - If degraded: automated rollback or page on-call                  |
|                                                                     |
|  TOTAL TIME (well-run pipeline): 45-90 minutes from commit to       |
|  full production rollout. This is fast AND safe.                    |
+---------------------------------------------------------------------+
```

### What staging environments are for (and are not for)

Staging is your last dress rehearsal before the real performance. Like an actor
who goes through the full show the night before opening with costumes and
lighting, staging lets you catch problems in a realistic environment while the
stakes are still low.

But staging has a fundamental limitation: it is never exactly like production.
It has different traffic patterns, different data (usually sanitized copies),
different load, and often different configuration. Bugs that only appear under
real production traffic loads or with specific real-user data patterns will not
be caught in staging.

This is why canary deployments exist: to validate behavior with a small slice
of real production traffic that staging cannot replicate.

The right mental model: staging catches 80% of problems. Canary catches most
of the remaining 20%. The final 10% that slips through is why you have
monitoring, alerting, runbooks, and rollback procedures.

```
+---------------------+------------------------+---------------------+
|  WHAT IS CAUGHT IN  |  WHAT IS CAUGHT IN     |  WHAT REACHES FULL  |
|  STAGING            |  CANARY                |  PRODUCTION         |
+---------------------+------------------------+---------------------+
|  Logic errors       |  Real-traffic-only     |  Extremely rare     |
|  Integration        |  failures              |  edge cases         |
|  failures           |  Performance under     |  Data-dependent     |
|  Config problems    |  production load       |  bugs with unusual  |
|  Missing dependencies|  Real user behavior   |  user data patterns |
|  Obvious regressions|  Third-party API       |  Long-tail failure  |
|                     |  behavior with real    |  modes              |
|                     |  production accounts   |                     |
+---------------------+------------------------+---------------------+
```

### Secrets management in deployment pipelines

A topic often overlooked in discussions of deployment safety: how do secrets
(API keys, database passwords, TLS certificates) get into your production
environment?

Common bad practices seen in real organizations:

**Bad practice 1**: Hardcoded in source code. Everyone who reads the repo has the
secret. The secret is in git history forever, even after rotation.

**Bad practice 2**: In a .env file committed to the repo. Same problem, plus
accidental commits are common.

**Bad practice 3**: In CI/CD environment variables set in the pipeline dashboard
as plain text. Better, but environment variables are often visible in logs and
not rotatable easily.

**Good practice**: Use a dedicated secrets management system. Each service
at startup authenticates with a central secrets store (AWS Secrets Manager,
HashiCorp Vault, GCP Secret Manager) and retrieves only the secrets it needs.

```
+---------------------------------------------------------------------+
|              SECRETS MANAGEMENT PIPELINE                            |
+---------------------------------------------------------------------+
|                                                                     |
|  DEVELOPMENT:                                                       |
|  Engineer authenticates with vault using their identity             |
|  Vault issues a short-lived token for local development             |
|  No secret is ever in source code                                   |
|                                                                     |
|  CI PIPELINE:                                                       |
|  Pipeline authenticates with vault using machine identity           |
|  (IAM role, OIDC token)                                             |
|  Vault issues a scoped token: only the secrets needed for testing   |
|  Token expires after pipeline completes                             |
|                                                                     |
|  PRODUCTION:                                                        |
|  Each service pod/instance authenticates with vault using its       |
|  cloud IAM role (no human in the loop)                              |
|  Vault issues the secret with TTL (e.g., 24 hours)                  |
|  Service re-authenticates before expiry                             |
|  Secret rotation is automatic: update in vault, services re-fetch  |
|                                                                     |
|  BENEFITS:                                                          |
|  - Secrets never appear in source code, logs, or environment vars   |
|  - Rotation requires no redeployment                                |
|  - Audit log: who accessed which secret, when                       |
|  - Least privilege: each service only gets its own secrets          |
+---------------------------------------------------------------------+
```

---

## The On-Call Experience: What It Actually Teaches You

No chapter on operations is complete without discussing on-call honestly. If you
have never been on-call for a production system, much of what this chapter
describes is abstract. If you have been on-call for even one rotation, everything
changes.

### What on-call actually feels like

It is 2:47 AM. Your phone buzzes. You are immediately awake because your brain
has learned to associate that sound with something serious. You open the alert.
"Payment service error rate > 5%." You are still 30% asleep. You open a laptop.
You have maybe 10 minutes to figure out what is wrong before more users are
affected.

This experience teaches things that no amount of studying teaches:

**You learn to move fast without panicking.** Panic is the enemy. Panic causes
you to make commands without reading the output, to skip steps, to escalate
without trying the obvious fix first. Engineers who have been on-call long enough
develop a calm, methodical approach under pressure. Observe, orient, decide, act.

**You learn what your dashboards are actually useful for.** The first time you
are paged at 3 AM, you discover that half your dashboards are useless -- too much
data, no easy way to find what matters. After the incident, you rebuild them.
After a few incidents, you have dashboards that actually help you find the
problem in under 3 minutes. This is a skill that only comes from experience.

**You learn to hate toil.** After the third time you fix the same thing with the
same manual command, you write the automation. On-call is the best forcing
function for reducing operational toil.

**You develop better empathy for the user.** An abstract "1% error rate" becomes
very concrete when you are the one being woken up to fix it and thinking about
the user who could not complete their payment. Engineers who have been on-call
write better error handling, better fallbacks, and more careful deployments.

### The good on-call culture vs the bad

```
+---------------------------------------------------------------------+
|        HEALTHY ON-CALL vs UNHEALTHY ON-CALL                         |
+---------------------------------------------------------------------+
|                                                                     |
|  HEALTHY ON-CALL:                                                   |
|  - Pages are meaningful: > 90% of pages require action              |
|  - On-call shift is < 3 pages per night on average                  |
|  - Runbooks exist for all common alerts                              |
|  - Engineers rotate regularly: no one is always on-call             |
|  - Postmortems improve the system over time                         |
|  - On-call time is recognized and compensated                       |
|  - Burnout is monitored: overloaded rotations get headcount          |
|                                                                     |
|  UNHEALTHY ON-CALL:                                                 |
|  - Constant noise: alerts fire 20+ times per shift                  |
|  - Same issues repeat week after week (no follow-through)           |
|  - No runbooks: every incident requires tribal knowledge            |
|  - Same 2-3 people always on-call                                   |
|  - No postmortems: incidents fade into memory                       |
|  - On-call is unpaid or de-emphasized                               |
|  - Engineers burn out and leave                                     |
|                                                                     |
|  SIGNAL: if your team has high on-call turnover, the on-call        |
|  system itself is the problem. A Staff engineer's job is to         |
|  fix the system, not just to absorb the pain.                       |
+---------------------------------------------------------------------+
```

### Chaos engineering: proactive reliability testing

The most advanced teams do not wait for production incidents to test their
operational procedures. They intentionally introduce failures in production
(carefully, with safeguards) to verify that their runbooks, rollback procedures,
and monitoring all work correctly.

This practice, popularized by Netflix, is called chaos engineering. The analogy:
fire departments do not wait for a real fire to train firefighters. They run
controlled drills in real buildings. Chaos engineering is the fire drill for
software systems.

Netflix's Chaos Monkey is a tool that randomly terminates production instances
during business hours. The outcome: engineers write code that is resilient to
instance failure, because they know it will happen. Services that cannot survive
a random instance termination are found and fixed during controlled hours rather
than at 3 AM on a holiday.

```
+---------------------------------------------------------------------+
|              CHAOS ENGINEERING SAFETY PRINCIPLES                    |
+---------------------------------------------------------------------+
|                                                                     |
|  PRINCIPLE 1 -- START SMALL                                         |
|  Begin in staging or a small production subset.                     |
|  Never start chaos experiments on your most critical path.          |
|                                                                     |
|  PRINCIPLE 2 -- HYPOTHESIZE FIRST                                   |
|  Before injecting a failure, write down your prediction:            |
|  "If we kill one instance of service X, the load balancer will      |
|  route to the remaining instances within 30 seconds and error       |
|  rates will not exceed 0.1%."                                       |
|  If reality matches your prediction: confidence confirmed.          |
|  If not: you found a gap.                                           |
|                                                                     |
|  PRINCIPLE 3 -- HAVE A STOP BUTTON                                  |
|  Every chaos experiment must be abortable in under 60 seconds.      |
|  If something goes wrong that you did not expect, you stop it.      |
|                                                                     |
|  PRINCIPLE 4 -- RUN DURING BUSINESS HOURS                           |
|  Counter-intuitive: run chaos experiments when your best engineers  |
|  are awake and at their desks. Not at night. The goal is to find    |
|  gaps, not to cause an unattended outage.                           |
|                                                                     |
|  PRINCIPLE 5 -- MEASURE EVERYTHING                                  |
|  Record exactly what happened: which failure was injected, what     |
|  the system did, what the user impact was. This is your data.       |
+---------------------------------------------------------------------+
```

---

## Common Interview Traps and How to Avoid Them

### Trap 1: "Our SLO is 100% uptime."

When a candidate says this in an interview, it signals one of two things: they
have never run a production system, or they have not thought carefully about what
100% means.

100% uptime is not achievable for any non-trivial system. Why?

- Every cloud provider has scheduled maintenance windows.
- Network equipment fails and requires rebooting.
- Security patches require restarts.
- DNS has propagation delays that look like downtime during failovers.
- Even "stateless" services have startup time.

More importantly, pursuing 100% uptime is actively harmful. The only way to
approach it is to make every change so cautious and gradual that your deployment
velocity approaches zero. You would test every change for weeks. You would run
massive redundancy at enormous cost. You would never do maintenance.

The right answer is always to set an SLO that reflects the actual business need.
For most consumer applications, 99.9% is appropriate. For healthcare or financial
systems where downtime directly causes harm, 99.99% may be justified. For an
internal tool, 99.5% is probably fine. The number is a business decision, not a
technical one.

**Interview answer**: "One hundred percent uptime is not achievable and not
desirable. The question is: what is the right target for this specific business?
For a checkout flow, I would probably start at 99.9% -- that allows 8.7 hours
of downtime per year, which is enough headroom for maintenance and improvement.
If this is a payment processing backend, I might push to 99.95%."

---

### Trap 2: Treating a postmortem as a blame session

In an interview, if you are asked to describe how you handled an incident, and
your answer is "we figured out it was the database team's fault," you have
signaled that you do not understand modern incident culture.

Blameless postmortems are the industry standard at every top-tier tech company.
The reasoning is both ethical and practical:

**Ethical**: people make mistakes. Punishing individuals for mistakes in complex
systems discourages candor in postmortems (no one will tell you what actually
happened if they fear punishment), and it targets the wrong thing. The human who
made a mistake is not the root cause -- the system that allowed that mistake to
reach production without detection is the root cause.

**Practical**: if you fire or penalize the engineer who caused an outage, you
lose the person who knows the most about what happened and how to prevent it.
You also create an environment where incidents are hidden rather than reported.

The correct framing is: "Why did our system allow this mistake to propagate to
users?" -- not "who made this mistake?"

**Interview answer**: "When we wrote the postmortem, we focused on what in our
process and architecture allowed this to happen, not who did it. The action items
were all systemic: we added a validation step in the deployment pipeline so this
class of configuration error cannot reach production. We did not need to know
whose finger pressed the button."

---

### Trap 3: Conflating availability with latency

A system can be "available" (returning 200 responses) while being so slow that
users cannot complete their tasks. A checkout that takes 30 seconds to respond
is technically available but functionally broken.

Your SLOs must cover both dimensions:
- Availability SLO: what fraction of requests succeed (error rate < X%).
- Latency SLO: what fraction of requests respond within a time threshold.

Both must be met for the service to be considered healthy. A common mistake is
to have an availability alert that fires at 99.9% error-free, declare the system
healthy, and miss that latency has degraded 5x because latency is "not breaking."

**Interview answer**: "I would define separate SLOs for availability and latency.
For this service I would track: error rate (targeting < 0.1%) and p99 latency
(targeting < 500ms for 99% of requests). Both need to be healthy. A service
that returns fast errors or slow successes is not meeting user expectations."

---

### Trap 4: Treating deployment and operations as separate concerns

Junior engineers often think: deployment is a one-time event (ship the code),
operations is the ongoing work of keeping it running. These are treated as
separate responsibilities, often owned by separate teams.

This is the old "throw it over the wall" model: dev team writes code, ops team
runs it. It creates misaligned incentives. The dev team is rewarded for shipping
features quickly. The ops team bears the cost of every feature that is hard to
run, monitor, or debug.

The modern model (DevOps, you build it you run it) puts both responsibilities on
the same team. This is not just cultural preference -- it is a design feedback
loop. When the engineers who write the code are also the ones paged at 3 AM when
it breaks, they make better decisions about logging, error handling, graceful
degradation, and deployment safety.

**Interview answer**: "At Staff level, I think about operability as part of the
design. Before a service ships, I ask: does it emit enough logs to debug a
production incident? Are there runbooks? Is there a canary deployment path? What
is the rollback procedure? If these are not answered before launch, the on-call
rotation inherits a system they cannot safely operate."

---

### Trap 5: Forgetting that deployment risk compounds

If you deploy once per week, a bad deploy affects one week's worth of changes.
If you deploy 20 times per day, a bad deploy affects a few hours of changes --
making it much easier to identify and roll back.

But there is a second-order effect: teams that deploy infrequently batch up
large changes. Large changes have more moving parts, more interactions, and are
harder to reason about. When something goes wrong, it is harder to identify which
of the 50 changes in the release caused the problem.

Teams that deploy frequently ship small changes. Small changes are easier to
reason about, easier to roll back, and easier to debug.

This is why CI/CD (Continuous Integration / Continuous Deployment) is a
reliability practice as much as a velocity practice. Higher deployment frequency
with smaller batches reduces the risk per deployment.

```
+---------------------------------------------------------------------+
|        DEPLOYMENT BATCH SIZE vs RISK                                |
+---------------------------------------------------------------------+
|                                                                     |
|  LARGE BATCH (weekly):                                              |
|  50 changes in one release                                          |
|  One change causes an outage                                        |
|  Investigation: which of 50 changes is responsible?                |
|  Rollback: undo all 50 or debug the one?                            |
|  Risk: HIGH (complex, slow to diagnose)                             |
|                                                                     |
|  SMALL BATCH (multiple times per day):                              |
|  1-3 changes in one release                                         |
|  One change causes an outage                                        |
|  Investigation: obvious -- it is one of 1-3 changes                 |
|  Rollback: simple, well-scoped                                      |
|  Risk: LOW per deployment (simple, fast to diagnose)                |
|                                                                     |
|  PARADOX: deploying more often reduces per-deployment risk          |
|  Most teams believe the opposite.                                   |
+---------------------------------------------------------------------+
```

---

## Observability Deep Dive: Building an Alert That Does Not Lie

Bad alerts are one of the most damaging operational problems a team can have.
An alert that fires too often (false positive) trains engineers to ignore it.
An alert that fires too rarely (false negative) lets real problems go undetected.

Here is a framework for designing alerts that are honest:

### The four properties of a good alert

**Property 1 -- Actionable:**
Every alert should have a clear action associated with it. If your response to
an alert is "hmm, I'll look at it when I have time," that alert should not exist
as a page. It should be a dashboard view or a weekly report.

**Property 2 -- Symptom-based, not cause-based:**
Alert on user-visible symptoms, not internal implementation details. Alert on
"checkout error rate > 1%" (symptom), not "database connection pool > 80%"
(cause). Why? Many internal implementation problems never cause user-visible
symptoms. Alerting on every internal metric creates noise. Alerting on symptoms
ensures you are always dealing with something that actually hurts users.

**Property 3 -- Calibrated threshold:**
The threshold should be set so it fires when action is genuinely needed, not
at the first sign of anything unusual. If your error rate normally varies
between 0.01% and 0.08%, an alert at 0.1% is appropriate. An alert at 0.05%
will fire constantly during normal variation.

**Property 4 -- Short MTTR when it fires:**
A good alert fires early enough that you can act before significant damage is
done. An alert that fires when the error budget is 5% remaining gives you no
time to act. Multi-window alerting (burn rate approach) is designed to catch
problems when there is still budget to fix them.

```
+---------------------------------------------------------------------+
|         ALERT QUALITY CHECKLIST                                     |
+---------------------------------------------------------------------+
|                                                                     |
|  For every alert in your system, ask:                               |
|                                                                     |
|  [  ] What action should the on-call take when this fires?          |
|       If no clear action: delete or demote to dashboard.            |
|                                                                     |
|  [  ] Is this a symptom (user impact) or a cause (internal metric)? |
|       Prefer symptom alerts. Cause alerts belong on dashboards.     |
|                                                                     |
|  [  ] What is the false positive rate of this alert?                |
|       If it fires more than once per week without action needed:     |
|       raise the threshold or add a duration requirement.            |
|                                                                     |
|  [  ] What is the false negative rate?                              |
|       Has a real incident happened that this alert did not catch?   |
|       Lower the threshold.                                          |
|                                                                     |
|  [  ] Does this alert have a corresponding runbook?                  |
|       If not: write one before the next on-call rotation.           |
|                                                                     |
|  ALERT HEALTH METRIC:                                               |
|  Track "alert fatigue": total pages per on-call shift.              |
|  > 10 pages per shift = alert fatigue is a real problem.            |
|  < 2 pages per week = likely missing coverage.                      |
|  Target: meaningful alerts only. Every page should matter.          |
+---------------------------------------------------------------------+
```

### A note on synthetic monitoring

Passive monitoring (collecting metrics from real traffic) tells you something is
wrong after users experience it. Synthetic monitoring runs automated "fake user"
tests from outside your system and can detect problems before any real user does.

The analogy: passive monitoring is reading customer complaint cards after dinner.
Synthetic monitoring is sending a secret shopper before the restaurant opens and
every 5 minutes throughout the day.

A synthetic monitor for a checkout flow might:
- Every 2 minutes, use a test account to add an item to cart and begin checkout.
- Measure how long the checkout page takes to load.
- Verify the expected UI elements are present.
- Alert if the test fails or takes more than 3 seconds.

This catches outages, regressions, and third-party API failures even during
low-traffic periods when real user traffic might not trigger alerts.

---

## Quick-Reference Glossary

These are terms you will encounter in system design interviews and production
environments. Know the precise definition for each.

```
+---------------------+------------------------------------------------+
|  TERM               |  PRECISE DEFINITION                            |
+---------------------+------------------------------------------------+
|  Blue-Green         |  Deployment strategy with two identical        |
|  Deployment         |  environments; traffic switches atomically.    |
+---------------------+------------------------------------------------+
|  Canary Deployment  |  Incremental traffic shift to new version,     |
|                     |  monitored at each percentage step.            |
+---------------------+------------------------------------------------+
|  Feature Flag       |  Runtime conditional enabling/disabling new    |
|                     |  code without a deployment.                    |
+---------------------+------------------------------------------------+
|  SLI                |  A measurable metric representing service       |
|                     |  behavior (e.g., request success rate).        |
+---------------------+------------------------------------------------+
|  SLO                |  The target value for an SLI (e.g., 99.9%      |
|                     |  success rate). Internal commitment.           |
+---------------------+------------------------------------------------+
|  SLA                |  External contractual commitment to customers,  |
|                     |  usually with financial penalties if missed.   |
+---------------------+------------------------------------------------+
|  Error Budget       |  The allowed downtime/errors implicit in an     |
|                     |  SLO. (1 - SLO) * time window.                |
+---------------------+------------------------------------------------+
|  Burn Rate          |  The rate at which error budget is consumed.   |
|                     |  Burn rate > 1 means budget is depleting.      |
+---------------------+------------------------------------------------+
|  MTTR               |  Mean Time To Recover. Average time from        |
|                     |  incident start to full resolution.            |
+---------------------+------------------------------------------------+
|  MTBF               |  Mean Time Between Failures. Average time       |
|                     |  between one incident and the next.            |
+---------------------+------------------------------------------------+
|  Runbook            |  Step-by-step operational guide for a specific  |
|                     |  alert or failure mode.                        |
+---------------------+------------------------------------------------+
|  Postmortem         |  Blameless document written after an incident   |
|                     |  to learn and prevent recurrence.              |
+---------------------+------------------------------------------------+
|  Incident Commander |  Role in incident response: coordinates people,  |
|                     |  does NOT debug. Owns communication.           |
+---------------------+------------------------------------------------+
|  Four Golden        |  Latency, Traffic, Errors, Saturation.         |
|  Signals            |  Google's framework for service monitoring.    |
+---------------------+------------------------------------------------+
|  Distributed Trace  |  End-to-end record of a single request as it   |
|                     |  flows through multiple services.              |
+---------------------+------------------------------------------------+
|  Thundering Herd    |  Many clients simultaneously make identical     |
|                     |  requests after a failure or event.            |
+---------------------+------------------------------------------------+
|  Cache Stampede     |  Cache becomes empty; all requests miss and     |
|                     |  flood the backend simultaneously.             |
+---------------------+------------------------------------------------+
|  Expand-Contract    |  Schema migration strategy: expand schema to    |
|                     |  support both versions, then contract after.   |
+---------------------+------------------------------------------------+
|  P50 / P95 / P99    |  Percentile latency. P99 = 99th percentile:    |
|                     |  the latency exceeded by the slowest 1%.       |
+---------------------+------------------------------------------------+
|  Unit Economics     |  Cost and revenue analysis per unit of output   |
|                     |  (per user, per request, per transaction).     |
+---------------------+------------------------------------------------+
|  FinOps             |  Practice of managing cloud costs with          |
|                     |  per-team ownership and accountability.        |
+---------------------+------------------------------------------------+
|  Load Test          |  Controlled test applying artificial traffic to  |
|                     |  find system limits before real traffic does.  |
+---------------------+------------------------------------------------+
|  Soft Launch        |  New feature deployed to small opted-in group   |
|                     |  before general availability.                  |
+---------------------+------------------------------------------------+
|  Dark Launch        |  New feature deployed to production but not     |
|                     |  visible to users; used for load testing.      |
+---------------------+------------------------------------------------+
```

---

## Summary: What You Should Now Be Able to Do

After completing this chapter, you should be able to:

```
+---------------------------------------------------------------------+
|               CHAPTER 40 COMPETENCY CHECKLIST                       |
+---------------------------------------------------------------------+
|                                                                     |
|  DEPLOYMENT STRATEGY                                                |
|  [  ] Explain blue-green and canary with a clear analogy            |
|  [  ] Identify when to use each strategy for a given service        |
|  [  ] Design a canary rollout plan with specific metrics/thresholds  |
|  [  ] Explain the database migration problem and the expand-contract |
|       solution                                                      |
|                                                                     |
|  INCIDENT RESPONSE                                                  |
|  [  ] Write a complete runbook for a failure mode                   |
|  [  ] Define severity levels and explain the incident commander role |
|  [  ] Write a proper postmortem with blameless root cause and        |
|       concrete action items                                         |
|                                                                     |
|  OBSERVABILITY                                                      |
|  [  ] Explain the three pillars and when to use each                |
|  [  ] Name the four golden signals and explain why each matters      |
|  [  ] Design an observability strategy for a new service            |
|  [  ] Explain how trace IDs connect logs, metrics, and traces       |
|                                                                     |
|  SLOs AND ERROR BUDGETS                                             |
|  [  ] Define SLI, SLO, SLA and explain the relationship             |
|  [  ] Calculate error budget for a given SLO over 30 days           |
|  [  ] Explain the error budget policy at each depletion level       |
|  [  ] Use error budget data to have a velocity vs reliability debate |
|                                                                     |
|  CAPACITY AND COST                                                  |
|  [  ] Run through the five-step capacity planning process           |
|  [  ] Explain what load testing reveals and when to run each type   |
|  [  ] Calculate unit cost for a service                             |
|  [  ] Identify the top cost optimization strategies for a service   |
|                                                                     |
|  ROLLBACK                                                           |
|  [  ] Use the decision tree to decide rollback vs fix forward       |
|  [  ] Explain when rollback is not an option and why                |
|  [  ] Describe feature flags as the safest rollback mechanism       |
+---------------------------------------------------------------------+
```

---

*Chapter 40 of Section 4. Next: Chapter 41 -- Advanced Topics in System Design.*
