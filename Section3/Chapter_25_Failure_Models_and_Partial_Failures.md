# Chapter 25: Failure Models and Partial Failures
## (Simplified Edition)

*(Note to reader: This chapter is about what happens when your system is neither fully working nor completely dead — and why that middle ground is the most dangerous place to be. Most engineers spend 90% of their learning time on how to build systems that work. Staff Engineers spend an equal amount of time thinking about how systems fail. Not because they are pessimistic, but because failure is the default state of any system at scale. This chapter will teach you to think about failure the way a doctor thinks about a patient: not just "alive or dead," but "what exactly is wrong, where, by how much, and what are we doing about it right now?")*

---

## At a Glance — What This Chapter Covers

```
+================================================================+
|           CHAPTER 25: FAILURE MODELS AND PARTIAL FAILURES      |
+================================================================+
|                                                                |
|  THE DEGRADATION CONTINUUM                                     |
|                                                                |
|  100%  ------>  80%  ------>  60%  ------>  40%  ------> 0%  |
|  Full       Slow deps     Some errors   Major errors   Down   |
|  Health     (users         (some users    (most users         |
|             notice lag)    see errors)    affected)           |
|                                                                |
+----------------------------------------------------------------+
|  KEY TAKEAWAYS                                                 |
|  1. Partial failure is the DEFAULT, not the exception          |
|  2. Complete failures are EASIER to handle than partial ones   |
|  3. Every system needs a "degradation budget" mindset          |
|  4. Different failure types need different detection methods   |
|  5. Health checks must go DEEP, not just surface-level         |
+----------------------------------------------------------------+
|  THE DEFENSE STACK (bottom = first line, top = last resort)    |
|                                                                |
|        [ 4. Monitoring + Alerting ]   <-- catch what slips     |
|        [ 3. Fallback / Graceful Deg ] <-- serve something      |
|        [ 2. Circuit Breaker        ] <-- stop the bleeding     |
|        [ 1. Timeouts               ] <-- don't wait forever    |
|                                                                |
+================================================================+
```

---

## Part 1: Why Partial Failure Is the Default, Not the Exception

### The Hook

> "Most engineers design for when things work. Staff Engineers design for when they're already failing."

Let that sit for a second.

When you first learn to build software, almost all of your energy goes into making things work. You figure out the right API, the right database query, the right algorithm. You test the happy path. You ship it.

And that is completely fine for a junior engineer. That is your job at that stage.

But at the Staff Engineer level, the question shifts. You stop asking "does this work?" and start asking "what happens when this breaks, and what does it break next, and how long until someone notices, and what does the user experience during that time?"

Those are different questions. They require a different way of thinking.

This chapter is about building that way of thinking.

---

### The Myth vs. The Reality

Here is the myth most engineers carry around without realizing it:

**THE MYTH:** A system is either up (working) or down (not working).

You check a health endpoint. It returns 200. System is up. You go home.

This is a comforting fiction. Real systems do not work this way.

**THE REALITY:** A system is almost always somewhere on a spectrum between "fully working" and "completely dead." That spectrum has infinite points between the two ends. Most incidents happen somewhere in the middle of that spectrum — not at the "completely dead" end.

Here is what that spectrum looks like in practice:

```
THE DEGRADATION SPECTRUM
========================

100%          80%           60%           40%           20%           5%           0%
  |             |             |             |             |             |            |
  |             |             |             |             |             |            |
FULL        SLOW DEPS     SOME          MAJOR         MINIMAL       BARELY       DOWN
HEALTH      appearing     ERRORS        ERRORS        FUNCTION      ALIVE
            All core      Some users    Most users    Critical      1 in 10
            features      hit errors    affected,     path only,    requests
            work, but     or timeouts.  errors on     all else      succeed.
            latency       Core paths    non-critical  failing.      System
            is 2-3x       still OK.     paths.                      responding
            normal.                                                  but broken.

  "Is it    "Sort of     "Kind of       "Mostly        "Barely       "Almost      "No."
   up?"      yeah"        yeah"          no"            yes"          no"
```

Notice that question at the bottom: "Is it up?" has six different honest answers before you get to "No." Every single one of those answers describes a different user experience, a different severity level, and a different required response.

The dangerous part is that from the outside — from a simple health check — many of these states look identical. Your load balancer might see a 200 OK from an instance that is at 20% function. Your monitoring dashboard might show "green" for a service that is silently dropping 40% of requests.

That is why partial failures are so treacherous.

---

### The Restaurant Kitchen Analogy

Think about a small restaurant with one chef.

That chef gets sick. They call in. The kitchen cannot operate. The restaurant is closed. This is a **complete failure**. It is obvious. Everyone knows immediately. You put up a "Closed" sign. There is no ambiguity. Recovery is straightforward: get a new chef.

Now think about a large restaurant with 20 chefs, each running a different station. Grill. Salad. Dessert. Pasta. Sauces.

The grill chef gets sick and calls in.

What happens?

- Grilled items take 3x longer because someone is doubling up
- Tables ordering steak wait much longer
- Some diners notice and complain
- Other diners getting pasta or salad have no idea anything is wrong
- The manager knows something is off but it takes 20 minutes to identify the problem
- Some tables get up and leave; others have a fine meal

This is a **partial failure**. The kitchen is not "down." But it is not fully operational either. It is running at maybe 70% capacity, with the degradation concentrated specifically on grilled items.

This is exactly how distributed systems fail. Most of the time.

- One microservice goes slow: only features that call that service are affected
- One database replica falls behind: reads from that replica return stale data
- One region has network congestion: users in that region see timeouts
- One cache node fails: requests that would have hit that node now go to the database

The users affected by each of these failures have a terrible experience. The users not touching those paths have no idea anything is wrong. Your health checks may not catch it for minutes. Your on-call engineer may take even longer.

---

### Why Partial Failures Are HARDER Than Complete Failures

You might think partial failures are less serious than complete failures because "at least some things are working." But partial failures are almost always **harder to handle** than complete failures. Here is why:

```
COMPLETE FAILURE vs. PARTIAL FAILURE
=====================================

Dimension               Complete Failure          Partial Failure
-----------             ----------------          ----------------
Detection time          Seconds                   Minutes to hours
                        (alerts fire fast,        (degraded, not dead
                        monitoring obvious)        -- hard to threshold)

User experience         Consistent: everyone      Inconsistent: some
                        sees same error           users fine, some not
                        or timeout                (support gets flooded
                                                   with "works for me")

System behavior         Predictable: nothing      Unpredictable: some
                        works                     requests work, others
                                                   fail seemingly randomly

Debugging               Focused: "what           Scattered: "WHY are
                        broke?"                   SOME requests failing?"

Recovery                Clear: fix the thing      Unclear: rolling back?
                        that is completely        partial rollback? which
                        dead                      component? how much?

SLO impact              Obvious spike             Slow burn: may erode
                        in error rate             SLO over hours before
                                                   anyone acts

User trust              "The site is down,        "The site seems broken
                        happens sometimes"         sometimes, unreliable"
                                                   (WORSE for retention)
```

The last row is the one that surprises most engineers. A complete outage is bad, but users understand it. A partial failure that makes the site feel "sometimes broken" — that erodes trust faster and is harder to recover from.

---

### The Swiss Cheese Model

There is a famous model in safety engineering called the Swiss Cheese Model. It was created by psychologist James Reason to explain how major accidents happen. Every system has multiple layers of protection. Each layer has holes in it (like Swiss cheese). A disaster happens when the holes in all layers line up at the same time.

This maps perfectly to distributed systems.

```
THE SWISS CHEESE MODEL FOR DISTRIBUTED SYSTEMS
================================================

                         FAILURE
                            |
                            v
+---------------------------+---------------------------+
|     Layer 1: TIMEOUTS     |                           |
|  [====  HOLE  ====  ] <---+-- failure slips through   |
|  [==================]     |   (timeout too long,      |
|                           |    not set at all)        |
+-----------+---------------+---------------------------+
            |
            v (passes through hole in Layer 1)
+---------------------------+---------------------------+
|  Layer 2: CIRCUIT BREAKER |                           |
|  [===  HOLE  =========]   |                           |
|  [==================]  <--+-- failure slips through   |
|                           |   (breaker never opened,  |
|                           |    threshold too high)    |
+-----------+---------------+---------------------------+
            |
            v (passes through hole in Layer 2)
+---------------------------+---------------------------+
|   Layer 3: FALLBACK       |                           |
|  [================  ]     |                           |
|  [==  HOLE  ========] <---+-- failure slips through   |
|                           |   (no fallback defined,   |
|                           |    fallback also broken)  |
+-----------+---------------+---------------------------+
            |
            v (passes through hole in Layer 3)
+---------------------------+---------------------------+
|  Layer 4: MONITORING      |                           |
|  [===  HOLE  ========] <--+-- failure slips through   |
|  [==================]     |   (alert threshold wrong, |
|                           |    wrong metric watched)  |
+---------------------------+---------------------------+
            |
            v
      USER EXPERIENCES
         THE FAILURE
```

Key insight: no single layer has to fail completely for the user to be affected. Each layer just has to have a hole big enough for this specific failure to pass through.

This is why defense in depth matters. Multiple imperfect layers beat one perfect layer. Because no layer is actually perfect.

---

## Part 2: The Degradation Budget Mindset

### How L5 and L6 Engineers Think Differently

Here is a question you will hear in any engineering review or incident post-mortem:

**"Is the system up?"**

Listen carefully to the answer. It tells you a lot about how that engineer thinks.

**L5 Answer:** "All health checks are passing. No alerts firing. The system is up."

**L6 Answer:** "Define up. Let me break it down: Search is serving at 100% request volume but P99 latency is 2x normal, which tells me something upstream is slow. Recommendations are serving data but it is 6 hours stale because the ML pipeline had a backlog. Checkout is at 100% with normal latency — that is the critical path and it is fine. User profile reads have a 2% error rate on one shard, but retry logic is handling it transparently. So: the critical path is healthy, two non-critical features are degraded, one is degraded-but-hidden. I would not page anyone right now but I want those three things on someone's radar before end of day."

Same system. Completely different level of understanding.

The L6 answer is not just more detailed. It reflects a different mental model. The L6 engineer is not asking "is it up?" — they are asking "what is the current health of each component, what is the user impact of any degradation, and what is my risk exposure?"

---

### L5 vs. L6 Thinking: Five Scenarios

```
SCENARIO COMPARISON TABLE
==========================

Scenario           L5 Answer                  L6 Answer
---------          ---------                  ---------

Database           "DB timed out, need to     "DB timed out. Retries
timeout            fix connection string."    will hit the same
                                              overloaded DB and make
                                              it worse. What is the
                                              retry backoff? Is the
                                              connection pool
                                              exhausted? What happens
                                              to in-flight requests
                                              while we recover? Do
                                              we have a read replica
                                              we can fail over to?"

Dependency         "Service B is down,        "Service B is down.
down               Service A will fail        Which features of
                   until it comes back."      Service A call B? Are
                                              those features critical
                                              path? Can we serve
                                              cached/stale data? Can
                                              we disable that feature
                                              and serve the rest? How
                                              long before B recovers
                                              and how do we handle
                                              the thundering herd
                                              when it does?"

Latency            "P99 went from 200ms       "P99 jumped to 800ms.
increase           to 800ms, looking          At that latency, our
                   into it."                  JS frontend timeouts
                                              at 1000ms, so we are
                                              near the cliff. Is
                                              this one service or
                                              cascading? Is the
                                              slowdown affecting
                                              our checkout flow?
                                              What is the SLO
                                              burn rate right now?"

Error spike        "Error rate went from      "2% error rate. That is
                   0.1% to 2%, deploying      above our SLO of 0.5%.
                   a fix."                    At this rate we burn
                                              the entire error budget
                                              in 4 hours. Do we roll
                                              back now or is the fix
                                              faster? Who is getting
                                              affected — all users
                                              or a specific segment?"

Service            "Service restarted,        "Service restarted. How
restart            all clear now."            many in-flight requests
                                              were dropped? Was the
                                              state properly drained?
                                              Are there any correlated
                                              failures we should watch
                                              for in the next 10 min?
                                              Was this a single crash
                                              or a restart loop?"
```

Notice the pattern in the L6 column: every answer ends with "and then what happens?" The L6 engineer is always looking one step ahead.

---

### The Degradation Hierarchy

Not all degradation is equal. Here is a framework for classifying it:

```
DEGRADATION HIERARCHY
======================

Level        Name           Example                  User Impact       Response
-----        ----           -------                  -----------       --------

Level 0      INVISIBLE      Search results are        None visible.     Monitor.
             DEGRADATION    missing 0.1% of items.   Users may not     Fix in
                            Data pipeline lag of      notice at all.    next sprint.
                            10 minutes in analytics.

Level 1      COSMETIC       Profile pictures load     Noticeable but    Fix in
             DEGRADATION    slower. Animations        not blocking.     48 hours.
                            janky. Fonts wrong.       Users annoyed.    Not a page.

Level 2      FUNCTIONAL     Recommendations are       Users cannot      Fix in
             DEGRADATION    unavailable. Search       use a feature     4 hours.
                            filters not working.      they expected.    Wake up
                            Push notifications        Complain to       on-call if
                            delayed.                  support.          worsening.

Level 3      TRANSACTIONAL  Checkout fails for        Users cannot      Page
             DEGRADATION    10% of users. Payment     complete          immediately.
                            errors intermittent.      purchases.        All hands.
                            Order status not          Direct revenue    Stop the
                            updating.                 impact.           bleeding.

Level 4      CRITICAL       Core auth down.           Nobody can        Wake
             DEGRADATION    Login broken. Data        log in or use     everyone.
                            corruption occurring.     the product.      War room.
                            Complete data loss        Existential       All-stop.
                            possible.                 risk.
```

The key insight here is that your **response** should be proportional to the **level**. Not every degradation deserves a 3am page. Not every degradation can wait until next sprint.

Most teams make one of two mistakes:

**Mistake 1 — Alert on everything at Level 0/1:** Engineers get paged constantly for non-critical issues, alert fatigue sets in, and the genuinely important alerts get ignored.

**Mistake 2 — Only alert at Level 4:** By the time you know about it, you have already been in a critical degradation for an hour and the damage is done.

The right approach is calibrated alerting: Level 0-1 goes to a ticket. Level 2 goes to a Slack notification. Level 3 pages the on-call. Level 4 wakes everyone up.

---

## Part 3: Failure Type 1 — Process Crash

### Why Process Crashes Are Not Simple

When most engineers think "process crash," they think: service goes down, load balancer stops sending traffic, orchestrator (like Kubernetes) starts a new pod, service comes back up. Simple.

But that is the ideal case. The reality has a lot more steps, and those steps have time attached to them. That time is the problem.

Here is what actually happens when a single process crashes:

```
PROCESS CRASH TIMELINE — THE FULL PICTURE
==========================================

T+0ms        T+10ms        T+5s          T+10s         T+45s         T+300s
  |             |             |             |             |             |
  v             v             v             v             v             v

PROCESS      IN-FLIGHT     HEALTH        ORCHESTRATOR  NEW INSTANCE  CACHE
KILLED       REQUESTS      CHECK         STARTS NEW    FULLY         FULLY
BY OOM       DROPPED       DETECTS       INSTANCE      LOADED,       WARM,
OR SIGKILL   (no           FAILURE       (Kubernetes   accepting     normal
             response      (usually      or ECS        traffic       latency
             sent)         5-30s         schedules     but COLD      resumed
                           interval)     new pod)      CACHE)

   [CRASH]   [DROPPED]    [DETECTED]    [SCHEDULED]  [STARTED]     [RECOVERED]
      |           |            |              |            |              |
      |           |            |              |            |              |
      +-----+-----+-----+------+----+---------+-----+------+              |
            |                       |               |                     |
        5 minutes of degradation from a single crash                      |
        <----------------------------------------------------------------->
            Requests either dropping or hitting cold cache
            Users experiencing errors or 3-5x slower responses
```

Let that sink in: **a single process crash causes 5 minutes of degraded user experience**, even if everything else goes perfectly. And "perfectly" requires:

- Health check interval is short (not all are)
- Orchestrator has capacity to schedule immediately (not always true)
- New instance starts quickly (depends on image size, dependencies)
- Cache warms quickly (depends on traffic volume and cache size)

In practice, it is often longer.

---

### Why Process Crashes Are Hard to Detect

You might think: "If a process crashes, the health check will catch it immediately."

But health checks have intervals. A typical Kubernetes liveness probe has:

- `initialDelaySeconds: 10` — wait 10 seconds after start before first check
- `periodSeconds: 10` — check every 10 seconds
- `failureThreshold: 3` — fail after 3 consecutive failures

That means: a process can be dead for up to 30 seconds before Kubernetes acts on it. During those 30 seconds, the load balancer is still sending traffic to a dead pod.

And even after detection, the dead pod has to be removed from the load balancer's rotation, which is another step with its own delay.

Meanwhile, the other instances are absorbing the traffic. If you had 5 instances and one dies, the remaining 4 suddenly handle 25% more traffic. That might push them toward their own OOM limit. Which might cause a second crash. Which is how one crash becomes two.

---

### Shallow vs. Deep Health Checks

Here is one of the most important distinctions in distributed systems health monitoring.

Think about this from everyday life. Your friend texts you: "You home?"

You text back: "Yeah."

But what they actually needed to know was: "Are you home AND can you open the door AND do you have the package I shipped to you AND is your fridge working because I'm bringing over food that needs to be refrigerated?"

"Are you home?" is a **shallow check**. "Are you home AND all those conditions are true?" is a **deep check**.

In systems, we call these liveness and readiness checks.

```
LIVENESS vs. READINESS — WHAT EACH CATCHES
============================================

CHECK TYPE     QUESTION ASKED        CATCHES             MISSES
----------     --------------        -------             ------

LIVENESS       "Is the process       - Process is dead   - Database connection
(Shallow)      alive at all?"        - Process is in       is down
                                       infinite loop     - OOM pressure building
               Returns: 200 if       - Process stopped   - Thread pool exhausted
               any response,           responding        - Downstream dependency
               nothing if dead         at all              is timing out
                                                         - Disk full
                                                         - Certificate expired

READINESS      "Is the process       Everything          Almost nothing --
(Deep)         ready to serve        liveness catches,   only truly external
               real traffic?"        PLUS:               conditions outside
                                     - DB connections    the service's control
               Returns: 200 only       healthy
               when truly ready      - Cache connected
               to handle requests    - Thread pool has
                                       capacity
                                     - Dependencies
                                       are reachable
                                     - Config loaded
                                     - Disk space OK
```

The difference matters enormously. A liveness check that passes when a service cannot actually serve traffic is useless. Worse than useless, because it gives you false confidence.

Here is an analogy. Imagine you run a pizza delivery business. You call each driver to ask "Are you available?" A driver says "Yes." But they have a flat tire. They are "available" in the sense that they answered the phone, but they cannot actually deliver a pizza.

A liveness check is asking "Did you answer the phone?" A readiness check is asking "Did you answer the phone, is your car working, do you have the pizza, and do you know the address?"

---

### Deep vs. Shallow Health Check Comparison

```
HEALTH CHECK DEPTH DIAGRAM
============================

SHALLOW (Liveness only):
========================

   Request --> [Process Alive?]
                    |
                   YES
                    |
               Returns 200
               Load balancer
               keeps sending
               traffic
                    |
                    v
              BUT PROCESS
              CANNOT SERVE:
              +-----------+
              | DB is down|  <-- liveness doesn't know
              | OOM soon  |  <-- liveness doesn't know
              | TPool full|  <-- liveness doesn't know
              +-----------+
              Users get errors
              but health check
              says "all good"


DEEP (Readiness):
=================

   Request --> [Process Alive?]
                    |
                   YES
                    |
              [DB Connected?]
                    |
                   YES
                    |
              [Cache Connected?]
                    |
                   YES
                    |
              [Thread Pool OK?]
                    |
                   YES
                    |
               Returns 200
               Load balancer
               sends traffic
               Service can
               actually serve it


              If ANY check fails:
              Returns 503
              Load balancer
              removes from rotation
              until healed
```

Readiness checks prevent the situation where traffic is routed to an instance that cannot serve it. This is especially critical during startup (when the instance is alive but not ready) and during dependency failures (when the process is fine but a dependency is not).

---

### The Restart Storm

Now for one of the most dangerous failure patterns in distributed systems: the **restart storm**.

Imagine you have 10 instances of a service. Each instance has a local in-memory cache that stores the results of expensive database queries. When a query comes in, the instance checks its cache first. If the answer is there, it returns immediately. If not, it queries the database.

Under normal load, maybe 90% of queries hit the cache. Only 10% go to the database. The database handles this load easily.

Now, something happens — a bad deployment, a configuration change, a memory leak — and all 10 instances restart at roughly the same time.

```
THE RESTART STORM SEQUENCE
============================

BEFORE RESTART:
   10 instances, each with warm cache (90% hit rate)
   DB load: 10 queries/second (10% of 100 req/sec reach DB)

   [Instance 1] [Instance 2] [Instance 3] ... [Instance 10]
       ^90%          ^90%          ^90%              ^90%
       cache         cache         cache             cache
       hit           hit           hit               hit
                          \    |    /
                           \   |   /
                            [  DB  ]   <-- handles 10 q/s easily
                               OK


T+0s: ALL 10 INSTANCES RESTART SIMULTANEOUSLY
   All caches are empty (cold start)
   Cache hit rate: 0%

   [Instance 1] [Instance 2] [Instance 3] ... [Instance 10]
       ^0%           ^0%           ^0%               ^0%
       cache         cache         cache             cache
       MISS          MISS          MISS              MISS
                          \    |    /
                           \   |   /
                            [  DB  ]   <-- now receiving 100 q/s
                            OVERLOADED  (10x normal load)


T+5s: DATABASE STARTS REJECTING CONNECTIONS
   Connection pool exhausted
   Queries timing out

   [Instance 1] [Instance 2] [Instance 3] ... [Instance 10]
       TIMEOUT       TIMEOUT       TIMEOUT           TIMEOUT
       (DB refused)  (DB refused)  (DB refused)      (DB refused)


T+10s: INSTANCES START CRASHING (unhandled DB timeouts)
   Or retry storms: each instance retries DB queries
   making overload even worse

   [Instance 1]  --  CRASH (OOM from retry queue buildup)
   [Instance 2]  --  CRASH
   ...

T+15s: COMPLETE OUTAGE
   All instances down or unresponsive
   What started as a rolling restart became
   a complete outage

   TIMELINE: restart -> cache miss -> DB overload -> crashes -> outage
```

This is the restart storm. It is a cascade. One event (restart) causes a secondary effect (cache miss) which causes a tertiary effect (DB overload) which causes the actual outage (crashes).

Notice that the restart itself was not the problem. The cache miss was not even the problem. The problem was the **interaction** between these components under load.

**How to prevent restart storms:**

1. **Stagger restarts (rolling updates):** Never restart all instances at once. Kubernetes rolling deployments restart one pod at a time, waiting for the new one to pass readiness checks before restarting the next. This keeps most of the cache warm at all times.

2. **Cache warmup before traffic:** Before a newly restarted instance receives traffic, pre-populate its cache from a warm instance or a database read-ahead.

3. **Circuit breaker on DB:** If the DB starts rejecting connections, instances should fail fast instead of queuing up more retries. This stops the cascade from getting worse.

4. **Backoff + jitter on retries:** If you must retry, add exponential backoff with randomized jitter so all 10 instances do not hammer the DB at exactly the same time.

---

### Rolling Restarts vs. All-at-Once

```
ROLLING RESTART (Safe):
========================

T=0s:    Restart Instance 1
         Instances 2-10 still serving (with warm cache)
         DB load: normal

T=30s:   Instance 1 passes readiness check (cache warmed)
         Restart Instance 2
         Instances 1, 3-10 serving
         DB load: slightly elevated (Instance 2 warming)

T=60s:   Instance 2 ready
         Restart Instance 3
         ... and so on

T=5min:  All instances restarted
         Cache was never fully cold
         DB load never spiked
         Users experienced no degradation


ALL-AT-ONCE RESTART (Dangerous):
==================================

T=0s:    Restart ALL 10 instances simultaneously
         0 instances serving
         OR all instances serving with 0% cache

T=0-30s: All instances try to warm cache
         All miss, all query DB
         DB load: 10x normal
         DB starts struggling

T=30s:   DB overloaded, starts timing out
         Instances queuing up retries
         Memory growing

T=45s:   OOM kills begin
         Restart storm in progress
         Complete outage
```

Rolling restarts are not just a nice-to-have. For any service with meaningful cache or state, they are the difference between zero user impact and a complete outage.

---

## Summary of Part A1

You have covered four major ideas in this part:

**1. Partial failure is the default.** Systems are almost never fully working or fully dead. They exist on a spectrum, and most incidents happen somewhere in the middle of that spectrum. The restaurant analogy: 20 chefs, one sick, the kitchen keeps running but the grill station is slow.

**2. Partial failures are harder than complete ones.** They are harder to detect, create inconsistent user experiences, are harder to debug, and erode user trust faster than clean outages.

**3. The degradation budget mindset.** L6 engineers do not ask "is it up?" They ask "what is the current state of each component, what is the user impact, and what is the response priority?" The five-scenario comparison table shows this in practice.

**4. Process crash is not simple.** A single crash causes 5 minutes of degradation from the full timeline: crash → dropped requests → health check lag → orchestrator scheduling → instance startup → cache warmup. Shallow health checks give false confidence. Deep readiness checks catch what matters. Restart storms turn one crash into a complete outage — rolling restarts prevent them.

---

*Part A2 will cover: Failure Type 2 (Dependency Failure), Failure Type 3 (Slow Dependencies and the Latency Cliff), and the Timeout Budget framework.*

---
# Chapter 25: Failure Models and Partial Failures — Part A2
## (Simplified Edition)

*(Continuing from Part A1, which covered what partial failures are and Failure Type 1: Process Crashes.
This file covers Failure Types 2, 3, and 4, then a full summary table of all four types.)*

---

## Quick Orientation — What We Are Covering Here

```
PART A2 ROADMAP
===============

  Failure Type 2: Network Partitions
       ├─ Hard partition vs Soft partition
       ├─ Why soft partitions are insidious
       ├─ The soft partition timeline
       └─ Secondary failures that follow

  Failure Type 3: Slow Nodes
       ├─ The classroom analogy
       ├─ Why slow is worse than dead
       ├─ P50 vs P99 — why dashboards lie
       └─ Common causes and how to spot them

  Failure Type 4: Dependency Failures
       ├─ Five types of dependency failure
       ├─ Gray failure — not up, not dead
       ├─ How one failure cascades across a system
       └─ Why the cascade happens (the mechanics)

  Summary Table
       └─ All 4 failure types side by side
```

---

## Failure Type 2: Network Partitions

### What Is a Network Partition?

When two parts of your system cannot talk to each other over the network, you have a
**network partition**.

This sounds simple. In practice, it is one of the most misunderstood and dangerous
failure modes in distributed systems — because it comes in two very different flavors,
and only one of them is obvious.

---

### The Two Flavors: Hard vs Soft

Think about a phone call.

**Hard partition** — someone physically cuts the telephone line. The call drops
immediately. Both people know right away. You hear nothing, the connection error is
instant, and you both hang up and try again. The failure is obvious. The recovery is
clear.

**Soft partition** — you are on a call with your friend, but every third word is
garbled. "Hey, can you —zzzt— meet at —zzzt— okay?" You are not sure if they heard
you. They are not sure if you heard them. The call is technically still connected.
Your phone shows full bars. But communication is broken in a way that is really hard
to detect and even harder to fix.

Distributed systems experience both kinds. And the soft kind is the dangerous one.

---

### Hard Partition — The Cut Phone Line

```
HARD PARTITION
==============

  ┌─────────────┐                    ┌─────────────┐
  │  Region US  │                    │  Region EU  │
  │             │                    │             │
  │  app-1      │                    │  app-4      │
  │  app-2      │        ╳           │  app-5      │
  │  app-3      │   (link cut)       │  app-6      │
  │             │                    │             │
  └─────────────┘                    └─────────────┘

  Connections fail immediately.
  TCP timeout or RST packet received.
  Errors are logged. Alerts fire.
  Engineers know within seconds.
```

With a hard partition:

- Every connection attempt fails immediately with a clear error
- Health checks from US to EU start failing
- Load balancers stop sending traffic across the cut
- Alerts fire: "EU region unreachable"
- On-call engineer gets paged within minutes
- The problem is obvious, the scope is clear, recovery has a known playbook

This is bad, but it is manageable. You know what broke. You know where. You can
start fixing it.

---

### Soft Partition — The Garbled Phone Call

```
SOFT PARTITION
==============

  ┌─────────────┐                          ┌─────────────┐
  │  Region US  │                          │  Region EU  │
  │             │   ~~~░░~~░~~~░░~~░~~~    │             │
  │  app-1      │  (30% packet loss)       │  app-4      │
  │  app-2      │  ~~~░~~░░~~░~~~░~~░~~~   │  app-5      │
  │  app-3      │                          │  app-6      │
  │             │   ░ = lost packet        │             │
  └─────────────┘   ~ = arrived packet     └─────────────┘

  Health checks: PASS  ✓
  Ping: responds  ✓
  Dashboard: GREEN  ✓
  Users experiencing errors: YES
  Engineers: confused
```

With a soft partition, 30% of packets are being silently dropped somewhere in the
network between your two regions. This could be a flapping router, a misconfigured
firewall, a NIC on a switch that is going bad, or a congested peering link.

Here is what makes it so dangerous:

**Health checks pass.** Most health checks send a single small packet to a `/health`
endpoint. That packet might make it through. The check returns 200. The system says
"everything is fine."

**Retries mask the problem.** Your application probably retries failed requests
once or twice. If 30% of requests fail on the first try, but succeed on the retry,
your retry logic hides the failure. The request eventually succeeds. No error logged.
No alert fired. But the request took 3 times as long as normal.

**Some requests work, some do not.** Because the packet loss is probabilistic,
some requests go through fine. Some fail. This is not consistent enough to trip any
specific alert threshold. Your error rate might go from 0.1% to 2% — bad, but not
obviously catastrophic.

**Engineers cannot reproduce it.** When an engineer opens a terminal and manually
runs a test request, that specific request might succeed. "Works fine from here."
The problem remains invisible.

---

### The Soft Partition Timeline

Here is what actually happens, minute by minute, during a soft partition event.
This timeline is based on real production incident patterns.

```
SOFT PARTITION TIMELINE
=======================

T+0s    Packet loss begins (30% of packets dropped)
         └─ Somewhere in the network. Could be a router. Could be a switch.
            Nobody knows yet.

T+0 to T+60s    Retries mask the problem
         └─ App sends request → fails → retries → succeeds on second try
            Each successful request takes 2-3x longer than normal.
            Error rate: 0.1% → 1.5% (below alert threshold of 5%)
            Latency P99: 200ms → 600ms (painful but alert threshold is 1s)
            Dashboard: YELLOW (mild warnings, no pages)

T+60s    Thread pools start filling
         └─ Requests take longer → caller threads held longer
            Thread pool: 100 threads → 65 in use (normally 20)
            New requests queue up. Queue depth rising.

T+180s   Some requests start timing out
         └─ Requests that retry twice and still fail finally time out
            Error rate: 1.5% → 4.8% (still below 5% alert threshold)
            P99 latency: 600ms → 900ms
            Queue depth: 200 deep and growing

T+300s   "Mostly working" state
         └─ System appears functional. Most requests succeed eventually.
            But every request is slower. Thread pools 85% full.
            Memory usage rising (queued requests consuming memory).
            Dashboard: ORANGE on some services

T+600s   Engineer investigates
         └─ On-call sees elevated P99 latency alerts.
            Manually tests: their test request succeeds in 180ms.
            "Looks fine from here." Marks alert as noise. Goes back to sleep.
            Thread pools: 90% full. Queue depth: 500+.

T+1800s  Packet loss worsens (50% now)
         └─ Something changed. More packets dropping.
            Retry success rate drops. Errors spike.
            Error rate: 4.8% → 23% (alert fires, engineer paged)

T+1860s  Cascade begins
         └─ Thread pools hit 100%. New requests rejected immediately.
            Callers of THIS service start filling THEIR thread pools.
            The cascade spreads outward.

T+1900s  Full outage
         └─ Multiple services rejecting requests.
            Users see errors across the board.
            Incident declared. All hands on deck.
```

Notice: the cascade that caused the "full outage" at T+1900s started at T+0s.
The system spent 30 minutes slowly drowning before anyone realized it.

---

### Secondary Failures That Follow Soft Partitions

A soft partition does not just cause direct errors. It triggers a whole family of
secondary problems that are often worse than the partition itself.

**Split-brain.** If two parts of your system can no longer talk to each other, they
each think they are the "real" one. Two servers both believe they are the primary
database. Both start accepting writes. Now you have two diverged copies of your data.
When the partition heals, reconciling them is extremely painful — and sometimes you
cannot reconcile them at all.

```
SPLIT-BRAIN
===========

  Before partition:
    Server A (primary) ──────────── Server B (replica)
                         healthy

  During soft partition (servers cannot reliably communicate):
    Server A: "I haven't heard from B. I must still be primary."
    Server B: "I haven't heard from A. A must be down. I'll promote myself."

    Server A (primary) ~~~░~~░~~   Server B (also primary!)
    Accepts writes              Accepts writes
    Data diverges               Data diverges
```

**Stale reads.** Caches and replicas that are supposed to stay in sync with the
primary can fall behind during a partition. Reads from those replicas return old data.
Your application thinks it got a fresh answer, but it is actually seeing data from
20 minutes ago.

**Duplicate processing.** This is a subtle one. A client sends a request. The
request arrives at the server and is processed. The server sends back "success," but
that acknowledgment packet is dropped. The client never sees the response. The client
assumes the request failed and retries. Now the server processes the same request
twice. If that request was "charge this customer's credit card," you just charged
them twice.

**Consensus failures.** Systems that use voting — like distributed databases that
require a majority of nodes to agree before committing a write — can fail to reach
quorum during a partition. Writes that would normally succeed start failing, even
though most nodes are perfectly healthy.

**Lock expiration.** A service holds a distributed lock to coordinate access to a
shared resource. During the partition, it cannot renew the lock. The lock expires.
Another service acquires the lock and starts modifying the resource. Now two services
are modifying the same resource at the same time.

---

## Failure Type 3: Slow Nodes — "Worse Than Dead"

### The Classroom Analogy

Picture a classroom with 10 students taking a test.

Nine students finish in 10 minutes. One student — maybe they did not sleep well,
maybe they are having an anxiety attack, maybe they just really do not know the
material — takes 5 hours to finish.

The professor has a rule: everyone must turn in their test before the class can move
on to the next assignment. So the entire class sits there, waiting, for 5 hours.

Now imagine if that slow student had simply been absent. The professor would have
waited a few minutes, marked them as absent, and moved on. The whole class would have
gotten the next assignment on time.

The absent student caused no harm. The present-but-slow student caused 5 hours of
delay for everyone.

**That is exactly what a slow node does to a distributed system.**

---

### The Performance Picture

```
10 NODES, 1 IN GC PAUSE
========================

  Node 1: ████ 8ms
  Node 2: █████ 11ms
  Node 3: ████████████████████████████████████████ 5000ms  ← GC PAUSE
  Node 4: ███ 7ms
  Node 5: ████ 9ms
  Node 6: ██████ 13ms
  Node 7: ████ 8ms
  Node 8: █████ 10ms
  Node 9: ███ 6ms
  Node 10: ████ 9ms

  P50 (median): 9ms    ← UNCHANGED. Looks healthy on dashboards.
  P99 (worst 1%): 5000ms  ← 333x worse than normal.

  "The P50 line on your latency dashboard stays green.
   10% of your users are waiting 5 seconds for every request.
   They are leaving. You do not know."
```

Your monitoring dashboard shows a green P50 latency line. Your on-call engineer
glances at it and thinks everything is fine. But 10% of your users — the ones whose
requests happened to land on Node 3 — are sitting there watching a loading spinner
for five seconds.

This is one of the most important reasons engineers at senior level always look at
P99 and P999 latency, not just P50 or average.

---

### Dead Node vs Slow Node: A Direct Comparison

| Scenario | Dead Node | Slow Node |
|---|---|---|
| Health check result | FAIL | PASS |
| Traffic routed to it | NO (load balancer stops) | YES (keeps receiving traffic) |
| Caller threads blocked | NO | YES (held for full timeout) |
| Detection speed | Seconds (fails fast) | Minutes to hours |
| Recovery | Clear: failover | Unclear: what is wrong? |
| Impact on callers | None (traffic rerouted) | Severe (threads fill up) |
| Self-identifying | Yes (errors logged) | No (appears to work) |

A dead node is like a closed store with a "Closed" sign on the door. You see it is
closed, you go to the next store.

A slow node is like a store that is technically open, but it takes 45 minutes to
serve each customer. The line backs up. People waiting in line cannot go to other
stores because they already committed to this one. New customers join the line without
knowing it is going to take 45 minutes. The whole street gets backed up.

**"A slow node is a vampire — drains resources while pretending to be alive."**

It consumes your caller's threads, memory, and time while showing "healthy" on every
dashboard. Your load balancer keeps sending it traffic because as far as the load
balancer knows, it is perfectly fine.

---

### Why Slow Nodes Are Worse Than Dead Nodes (The Mechanics)

When a node is dead, here is what happens:
- Connection attempt fails immediately (milliseconds)
- Error is returned to the caller immediately
- Caller's thread is freed immediately
- Load balancer marks node as unhealthy
- No new traffic sent to that node
- System operates at reduced capacity but functions correctly

When a node is slow (say, 10-second response time with a 30-second timeout), here is
what happens:
- Request is sent
- Caller thread is blocked, waiting for response
- After 10 seconds: response arrives (or timeout at 30 seconds)
- During those 10-30 seconds, the caller's thread cannot serve anyone else
- If your thread pool has 100 threads, and each is blocked for 10 seconds, you can
  only serve 10 requests per second instead of your normal 1,000
- New requests queue up waiting for a free thread
- If requests arrive faster than threads free up, the queue grows until you run out
  of memory
- You are now not just slow — you are completely unable to accept new requests

```
SLOW NODE THREAD EXHAUSTION
============================

  Thread pool: 100 threads
  Normal request time: 20ms
  Normal throughput: 100 threads / 20ms = 5,000 req/sec

  Slow node causes requests to take 10,000ms
  Throughput: 100 threads / 10,000ms = 10 req/sec

  Incoming request rate: 1,000 req/sec
  Threads freed per second: 10
  Threads consumed per second: 1,000

  Minute 1:  Queue depth 59,400. Memory rising.
  Minute 2:  Queue depth 118,800. Memory critical.
  Minute 2.5: Out of memory. Service crashes.

  ONE slow node → service crash in under 3 minutes.
```

---

### Common Causes of Slow Nodes

Understanding why a node becomes slow helps you detect and prevent it.

```
COMMON CAUSES OF SLOW NODES
============================

  Cause            | What Happens         | Detection         | Duration  | Frequency
  ─────────────────┼──────────────────────┼───────────────────┼───────────┼──────────
  GC Pause         | JVM/Go runtime stops | P99 latency spike | 50ms-5s   | Every
  (garbage collect)| all threads briefly  | at intervals      |           | few min
                   |                      |                   |           |
  Noisy Neighbor   | Another VM on same   | CPU steal metric  | Hours     | Random
                   | physical host hogs   | elevated          |           |
                   | CPU/memory/disk      |                   |           |
                   |                      |                   |           |
  Disk I/O         | Disk writing slowly, | iowait metric     | Minutes   | Varies
                   | reads blocking       | elevated, disk    | to hours  |
                   |                      | latency high      |           |
                   |                      |                   |           |
  Memory Pressure  | OS starts swapping   | Swap usage up,    | Until     | During
                   | to disk (1000x       | page fault rate   | restart   | traffic
                   | slower than RAM)     | high              | or scale  | spikes
                   |                      |                   |           |
  CPU Throttling   | Cloud provider caps  | CPU throttle %    | Ongoing   | Constant
                   | CPU when burst       | metric in         | if under- | if
                   | credits exhausted    | container stats   | provisioned| undersized
```

The tricky part: all five of these look like a "slow node" from the outside. The
node is responding, health checks pass, but every request takes much longer than
normal. Distinguishing between them requires looking at the right metrics on the
right host.

---

## Failure Type 4: Dependency Failures

### Your System Is Not an Island

Almost every service depends on other services. Your order service calls the payment
service. Your payment service calls a bank API. Your frontend calls the auth service.
Your auth service queries the user database.

When any of those dependencies break down, your service can break down too — even
if your code is perfectly correct and your servers are perfectly healthy.

Dependency failures are particularly nasty because they look different on each side
of the relationship:
- On the dependency side: "We are mostly fine"
- On your side: "Everything is on fire"

Here are the five types of dependency failure you will encounter.

---

### The Five Types

```
FIVE TYPES OF DEPENDENCY FAILURE
==================================

  ┌─────────────────────────────────────────────────────────────────────┐
  │  Type 1: Hard Failure                                               │
  │  ─────────────────────                                              │
  │  What: Dependency returns 500 errors or connection refused          │
  │  Signal: Explicit error codes (5xx, connection error)               │
  │  Danger: Medium — at least you know                                 │
  │  Detection: Easy. Errors show up in logs immediately.               │
  └─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────┐
  │  Type 2: Brownout                                                   │
  │  ─────────────────                                                  │
  │  What: Dependency is slow AND returning elevated errors             │
  │  Signal: P99 latency up, error rate up, but not 100% failing        │
  │  Danger: HIGH — system limps along, masking total failure           │
  │  Detection: Hard. Requires watching both latency AND error rate.    │
  └─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────┐
  │  Type 3: Throttling                                                 │
  │  ──────────────────                                                 │
  │  What: Dependency returns 429 (Too Many Requests)                  │
  │  Signal: HTTP 429 responses, "rate limit exceeded" messages         │
  │  Danger: HIGH — retrying makes it WORSE                            │
  │  Detection: Medium. 429s are logged but often not alerted on.       │
  │  Note: Naive retry logic will hammer the throttled dependency,      │
  │        making your throttling worse, which makes you retry more,    │
  │        which makes throttling worse. Exponential backoff required.  │
  └─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────┐
  │  Type 4: Stale Responses                                            │
  │  ────────────────────────                                           │
  │  What: Dependency returns 200 OK, but the data is old              │
  │  Signal: 200 OK. Nothing looks wrong. Data is stale.               │
  │  Danger: HIGH — invisible. No errors to alert on.                   │
  │  Detection: Very hard. Requires data freshness checks.              │
  │  Example: Price cache returns yesterday's prices as if they         │
  │           are current. Orders placed at wrong prices.               │
  └─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────┐
  │  Type 5: Silent Corruption                                          │
  │  ──────────────────────────                                         │
  │  What: Dependency returns 200 OK, but the data is WRONG            │
  │  Signal: HTTP 200. No errors. Data is subtly incorrect.            │
  │  Danger: EXTREME — corrupts your data silently                      │
  │  Detection: Nearly impossible without end-to-end validation.        │
  │  Example: User profile service returns User B's data when asked     │
  │           for User A. Your system uses it. Wrong user sees          │
  │           wrong data. Could be a privacy violation.                 │
  └─────────────────────────────────────────────────────────────────────┘
```

Notice the pattern: as you move down the list, the failure becomes less visible and
more dangerous. A hard failure (Type 1) is bad but detectable. Silent corruption
(Type 5) is a catastrophe you might not discover for days.

---

### Gray Failure — Not Up, Not Dead

Types 4 and 5 are examples of a broader pattern called **gray failure**.

```
THE FAILURE SPECTRUM
=====================

  CLEARLY UP                                              CLEARLY DOWN
  ──────────────────────────────────────────────────────────────────────
  ✓ Green       ░ Stale    ░ Slow    ░ Corrupt   ✗ Red
  200 OK        200 OK     200 OK    200 OK       500 Error
  Fresh data    Old data   5s delay  Wrong data   No response

                └──────────────────────────┘
                         GRAY ZONE
                   "Not up, not dead —
                    the dangerous middle"
```

Gray failure is **the single most dangerous failure mode in production systems**
because:

- Health checks return "healthy"
- HTTP status codes show "success"
- Monitoring dashboards stay green
- No alerts fire
- Engineers assume nothing is wrong

Meanwhile, users are experiencing problems. Maybe they see old data. Maybe 10% of
their requests return wrong results. Maybe every operation takes five seconds instead
of one. They notice. They complain. They leave. But the engineers watching dashboards
have no idea anything is happening.

**Three gray failure examples:**

Example A — Stale data with green health check:
```
  Cache service health check: GET /health → 200 OK  ✓
  Cache service actual state: Last synced with database 4 hours ago
  Result: Every price, every inventory count, every user preference
          is 4 hours stale. Customers order out-of-stock items.
          Engineers see no errors.
```

Example B — Partial corruption:
```
  Recommendation service health check: → 200 OK  ✓
  Recommendation service actual state: A bug introduced yesterday
          corrupts 10% of recommendation responses (swaps user IDs)
  Result: 1 in 10 users sees recommendations meant for someone else.
          10% of sessions are degraded. No 5xx errors anywhere.
          Engineers see no errors.
```

Example C — Latency gray failure:
```
  Auth service health check: GET /health → 200 OK in 5ms  ✓
  Auth service actual traffic: Every /authenticate call takes 5,000ms
  Result: Every page load in your app that requires authentication
          takes 5 seconds. Users think the app is broken.
          Engineers check dashboards. Auth service: GREEN.
```

In all three cases, the system is technically "up." Every monitoring signal says
"up." But users are suffering.

---

### How One Dependency Failure Cascades Into a Full Outage

This is the most important thing to understand about dependency failures: they do not
stay contained. A partial failure in one service can cause a complete failure in
services that depend on it — and then their dependents — until the whole system is
down.

Here is a realistic example using a payment service going into brownout.

**Setup:**
- Users send checkout requests to the Gateway service
- Gateway calls the Order service
- Order service calls the Payment service to charge cards
- Payment service is experiencing a brownout: 50% of requests take 10 seconds,
  50% succeed normally

```
DEPENDENCY CASCADE TIMELINE
============================

  PAYMENT SERVICE enters brownout (50% slow, 50% normal)
  ─────────────────────────────────────────────────────
  Payment's own metrics: 50% degraded. Team aware, investigating.

  T+0s
  ─────
  Order service starts calling Payment service.
  50% of those calls now take 10 seconds.
  Order service has a 10-second timeout (unfortunately exactly equal to
  the payment delay, so it never actually times out — just barely waits).

  Order service thread pool: 200 threads.
  Normally each request takes 200ms → can handle 1,000 req/sec.
  Now 50% take 10,000ms → effective throughput drops to ~100 req/sec.

  Requests: 800/sec incoming. Threads freed: 100/sec.
  Queue growing at 700 requests per second.

  T+30s
  ──────
  Order service thread pool: 90% full.
  Order service response time: P99 = 8,000ms.
  Order service starts queuing requests faster than it clears them.

  Gateway calls Order service. Order service is now slow too.
  Gateway's threads start backing up (same mechanics, one level up).

  T+60s
  ──────
  Order service thread pool: 100% full. New requests rejected: 503.
  Error rate for Order service: 60% (half fail immediately, half succeed).

  Gateway threads: 95% full.
  Gateway response time: P99 = 12,000ms.

  T+90s
  ──────
  Gateway thread pool: 100% full. Complete failure.
  Every user request: 503 Service Unavailable.

  ┌───────────┐     ┌─────────────┐     ┌─────────────┐
  │  Gateway  │────▶│  Order Svc  │────▶│  Payment    │
  │ 100% fail │     │ 100% fail   │     │  50% slow   │
  └───────────┘     └─────────────┘     └─────────────┘
       ▲                  ▲                    ▲
    TOTAL              TOTAL            PARTIAL BROWNOUT
    OUTAGE             OUTAGE           (where it started)

  A 50% problem in ONE service caused 100% outage in the whole system.
```

**Why did this happen?** Four specific engineering mistakes let this cascade unfold:

1. **No timeout short enough.** The Order service had a 10-second timeout on Payment
   calls. But the brownout was causing 10-second delays. The timeout was set
   optimistically based on normal behavior, not failure behavior. A 2-second timeout
   would have failed fast and freed threads quickly.

2. **No circuit breaker.** When 50% of Payment calls started failing, nothing
   automatically stopped Order from calling Payment. It kept trying. A circuit breaker
   would have noticed "50% of calls are failing" and stopped sending new requests,
   returning a fast error instead of waiting 10 seconds each time.

3. **Shared thread pool.** Order service used a single thread pool for all operations:
   user profile lookups, inventory checks, payment calls. When payment calls filled
   up the pool, inventory checks and profile lookups could not run either. Bulkheading
   (separate thread pools per downstream dependency) would have contained the damage.

4. **Synchronous calls holding resources.** The entire call chain was synchronous.
   Order service held a thread for the entire duration of the Payment call. If the
   call was asynchronous (fire and forget, or callback-based), the thread could have
   been freed while waiting for the response.

These are not obscure bugs. They are the default behavior of most web frameworks. If
you do not explicitly add timeouts, circuit breakers, bulkheads, and async patterns,
you are vulnerable to this exact cascade.

---

## Summary Table: All Four Failure Types

You have now seen all four major failure types in distributed systems. Here they are
side by side, so you can recognize each one quickly and know what to do.

```
ALL FOUR FAILURE TYPES — COMPARISON TABLE
==========================================

  Type              │ Key Signal        │ Primary Danger     │ Detection Method
  ──────────────────┼───────────────────┼────────────────────┼──────────────────────
  Type 1:           │ Process missing   │ Obvious outage if  │ Process monitor,
  Process Crash     │ from process list │ not replicated;    │ health check fails,
                    │ Health check fail │ data loss if no    │ TCP connection
                    │ Connection refused│ persistent storage │ refused
  ──────────────────┼───────────────────┼────────────────────┼──────────────────────
  Type 2:           │ Hard: conn errors │ Hard: manageable   │ Hard: connection
  Network           │ Soft: elevated    │ Soft: INSIDIOUS.   │ errors, easy.
  Partition         │ P99 latency with  │ Split-brain, stale │ Soft: requires
                    │ green health      │ reads, duplicates, │ packet loss metrics,
                    │ checks            │ silent data loss   │ correlation analysis
  ──────────────────┼───────────────────┼────────────────────┼──────────────────────
  Type 3:           │ P99 latency spike │ Thread exhaustion  │ P99/P999 latency
  Slow Node         │ P50 unchanged     │ in caller services;│ dashboards (NOT P50),
                    │ Health checks     │ invisible to most  │ per-node latency
                    │ still pass        │ dashboards         │ breakdown, GC logs
  ──────────────────┼───────────────────┼────────────────────┼──────────────────────
  Type 4:           │ Varies by subtype │ Gray failure:      │ End-to-end synthetic
  Dependency        │ Hard: 5xx errors  │ 200 OK responses   │ checks, data
  Failure           │ Brownout: slow+   │ with wrong or      │ freshness metrics,
                    │ elevated errors   │ stale data; no     │ client-side error
                    │ Gray: 200 OK      │ alerts fire while  │ tracking, canary
                    │ but wrong data    │ users suffer       │ analysis

  Type              │ Primary Defense
  ──────────────────┼───────────────────────────────────────────────────────────────
  Type 1:           │ Replication + health check monitoring +
  Process Crash     │ automatic restart (systemd, Kubernetes) +
                    │ persistent storage separate from process
  ──────────────────┼───────────────────────────────────────────────────────────────
  Type 2:           │ Hard: handled by load balancer failover
  Network           │ Soft: aggressive packet loss monitoring per network segment,
  Partition         │ distributed tracing to find slow paths, consensus protocols
                    │ (Raft/Paxos) for split-brain, idempotent writes for duplicates
  ──────────────────┼───────────────────────────────────────────────────────────────
  Type 3:           │ Short timeouts (fail fast, do not wait 30s),
  Slow Node         │ P99 latency alerts (not just P50),
                    │ per-node latency monitoring,
                    │ load balancer least-response-time routing,
                    │ GC tuning + off-heap memory management
  ──────────────────┼───────────────────────────────────────────────────────────────
  Type 4:           │ Circuit breakers (stop calling failing dependencies),
  Dependency        │ bulkheads (separate thread pools per dependency),
  Failure           │ short timeouts (2s not 30s),
                    │ fallback responses (serve stale rather than nothing),
                    │ data integrity checks (do not trust 200 OK blindly)
```

---

## Putting It All Together — Why You Need to Know All Four

A senior engineer does not wait for a production incident to teach them about failure
modes. They design systems that handle all four types from the start, because:

- **Type 1 (Process Crash)** is the most obvious and most commonly handled. Most
  teams have some form of auto-restart and replication.

- **Type 2 (Network Partition)** is handled by most teams for the hard case, and
  almost completely unhandled for the soft case. Soft partitions are where incidents
  that "came out of nowhere" usually come from.

- **Type 3 (Slow Nodes)** is commonly unhandled or partially handled. Most teams
  track P50 latency, which is useless for detecting slow nodes. P99 and P999 are
  what you need.

- **Type 4 (Dependency Failure)** is the most complex and the most commonly
  mishandled. Teams add timeouts but make them too long. Teams add retries but do not
  add exponential backoff. Teams do not add circuit breakers. The cascade scenario
  from this chapter happens in production every single week at companies of all sizes.

The good news: every one of these failure modes has known, well-understood defenses.
The techniques — circuit breakers, bulkheads, short timeouts, P99 monitoring, packet
loss metrics, idempotency keys — exist precisely because engineers have been burned
by these exact failures for decades and built defenses.

Part B of this chapter will cover those defenses in depth.

---

## Key Vocabulary Review

**Network partition** — a failure where two parts of a system cannot communicate.
Can be hard (complete and obvious) or soft (partial and insidious).

**Hard partition** — complete network failure. Connections refuse immediately.
Easy to detect and respond to.

**Soft partition** — partial network failure. Some packets arrive, some are dropped.
Health checks pass. Retries mask the problem. Very dangerous.

**Split-brain** — when two nodes both believe they are the primary, causing them
to independently accept writes and diverge.

**Slow node** — a node that is alive and responding, but much slower than normal.
Worse than a dead node because it holds caller resources while pretending to be healthy.

**GC pause** — a garbage collection pause in Java or Go runtime where all application
threads are stopped briefly while memory is cleaned up. Can cause latency spikes.

**P50 / P99 / P999** — percentile latency metrics. P50 is the median. P99 means
99% of requests are faster than this value. P999 means 999 out of 1,000 requests are
faster. P99 and P999 reveal slow nodes that P50 hides.

**Brownout** — a degraded state where a service is slow and returning elevated
errors, but not completely down.

**Throttling** — a dependency returning 429 (Too Many Requests) to tell you to
slow down. Retrying without backoff makes it worse.

**Gray failure** — a failure where all monitoring signals show "healthy" but
users are experiencing real problems. Returns 200 OK with wrong or stale data.

**Dependency cascade** — a situation where a partial failure in one service
causes complete failure in its callers, which causes failure in their callers,
propagating through the whole system.

**Circuit breaker** — a pattern where after a threshold of failures, a service
stops calling the failing dependency and returns fast errors instead, preventing
thread exhaustion.

**Bulkhead** — a pattern where separate thread pools are used for different
downstream dependencies, so that one slow dependency cannot block calls to other
dependencies.

---

*(End of Part A2. Part B will cover defenses: timeouts, circuit breakers,
bulkheads, retry strategies, and chaos engineering.)*
---
# Part B: The Defense Stack — Timeouts, Circuit Breakers, Bulkheads, and Load Shedding

---

## Quick Recap from Part A

Part A covered what failures look like — crashes, slowdowns, network drops, data corruption.
Part B is about **what you do about them**.

Think of Part A as learning that fires exist.
Part B is learning how to build a fireproof building.

---

## Section 1: The Defense Stack Overview

### The Castle Analogy

Imagine a medieval castle.
The king (your core service) sits in the middle.
Enemies (failures) try to get in from all sides.

The castle has **layers of defense**:

```
OUTSIDE WORLD
      |
      v
  ~~~MOAT~~~         <-- First line: turns away attackers before they reach the wall
      |
      v
 [OUTER WALL]        <-- Second line: catches what gets past the moat
      |
      v
  [TOWERS]           <-- Third line: isolated guard posts (one falling doesn't lose the castle)
      |
      v
 [INNER KEEP]        <-- Fourth line: last resort, protected core
      |
      v
    KING             <-- Your core business logic, protected
```

Each layer is independent.
If the moat fails, the outer wall still holds.
If the outer wall falls, the towers still fight.
The king is safe until every layer collapses.

Your distributed system needs the same thing.

### The Defense Stack

Here is the full defense stack we will cover in this part:

```
INCOMING REQUEST
      |
      v
+------------------+
|    TIMEOUT       |  "If no answer in X seconds, give up"
+------------------+
      |
      v
+------------------+
| CIRCUIT BREAKER  |  "If service keeps failing, stop calling it"
+------------------+
      |
      v
+------------------+
|    BULKHEAD      |  "Isolate failures so they don't spread"
+------------------+
      |
      v
+------------------+
|    FALLBACK      |  "If this fails, use this backup plan"
+------------------+
      |
      v
+------------------+
| GRACEFUL DEGRAD. |  "Do less, but keep working"
+------------------+
      |
      v
+------------------+
|  LOAD SHEDDING   |  "When overwhelmed, reject some to save the rest"
+------------------+
      |
      v
YOUR SERVICE CORE
```

These are not competing ideas.
You use **all of them at the same time**, in layers.

Let's go through each one.

---

## Section 2: Timeouts

### The Texting Analogy

You text your friend: "Hey, want to hang out tonight?"

How long do you wait before making other plans?

If you wait **forever**, you are stuck.
You can't plan anything else.
Your whole evening is on hold.

If you wait **5 minutes** and hear nothing, you assume they're busy.
You make other plans.
You move on.

**That's a timeout.**
You decide in advance: "If I don't hear back in X time, I act as if the answer is no."

Servers do the same thing.
When Service A calls Service B, A sets a timer.
If B doesn't respond before the timer runs out, A stops waiting and deals with it.

### Why Timeouts Are Critical

Without timeouts:

```
Service A                    Service B (very slow)
    |                              |
    |------- request ------------->|
    |                              |
    |  (waiting...)                |  (hung, never responds)
    |  (waiting...)                |
    |  (waiting...)                |
    |  (waiting...)                |
    |  (waiting...)                |
    |  (waiting...)                |
    |                              |
    |  Thread is BLOCKED           |
    |  Memory is HELD              |
    |  Other requests pile up      |
```

One slow dependency can freeze your entire service.
Threads pile up waiting.
Memory fills up.
Your service dies — **because of someone else's slowness**.

With a timeout:

```
Service A                    Service B (very slow)
    |                              |
    |------- request ------------->|
    |                              |
    |  (waiting... 2s)             |  (hung)
    |                              |
TIMEOUT! Give up.                  |
    |                              |
    |  Thread is FREED             |
    |  Handle error                |
    |  Serve next request          |
```

You set yourself free.

### The Three Types of Timeouts

There are actually three different timeouts, and they mean different things:

```
Timeline of a network call:

  [CONNECT]     [SEND]    [WAIT FOR RESPONSE]    [READ]
     |             |              |                  |
     v             v              v                  v
   +-----+      +-----+       +-------+           +------+
   |TCP  |      | req |       | server|           | resp |
   |hand-|      | data|       | proc- |           | data |
   |shake|      |     |       | essing|           |      |
   +-----+      +-----+       +-------+           +------+

   ^_____^                                         ^_____^
   Connection                                      Read
   Timeout                                         Timeout
   (1-5s)                                          (1-30s)

   ^__________________________________________________^
                    Total Request Timeout
```

**1. Connection Timeout (1-5 seconds)**
- How long to wait to establish the TCP connection.
- If the server doesn't even pick up the phone in 5 seconds, something is very wrong.
- Set this short.

**2. Read Timeout (1-30 seconds)**
- How long to wait for the server to send back data **after** the connection is established.
- This is the one you tune most carefully.
- Depends on what the operation does (fast reads vs. slow report generation).

**3. Total Request Timeout**
- The hard ceiling on the entire operation.
- "No matter what, this call cannot take longer than X seconds total."
- Protects against edge cases where individual timeouts don't fire.

### How to Set Timeouts Correctly

The formula is simple:

```
Read Timeout = P99 latency of the called service × 2 to 3
```

What is P99 latency?
It means: 99% of requests finish faster than this number.
The slowest 1% take longer.

So if your database normally responds in:
- P50 (median) = 5ms
- P95 = 20ms
- P99 = 80ms
- P99.9 = 500ms

Your read timeout should be: `80ms × 2 = 160ms` to `80ms × 3 = 240ms`

You give it a little buffer above the P99.
But you don't wait forever for the P99.9 outliers.

**The rule: Never set a timeout to "none" or "infinite".**

Ever.
In any environment.
For any reason.
It is always a mistake.

### The 30-Second Mistake

Here is one of the most common mistakes in production systems:

```
Engineer: "I don't know how long this could take, so I'll set 30 seconds
           to be safe."

Reality:
  - Normal requests: 50ms
  - Occasionally slow: 500ms
  - When DB is struggling: 29 seconds (timeout fires at 30s)

What happens during a DB slowdown:
  t=0s:   1000 requests/sec arrive
  t=5s:   500 threads waiting (each holding memory, DB connection)
  t=10s:  1000 threads waiting, system memory at 80%
  t=15s:  1500 threads waiting, memory exhausted
  t=20s:  System crashes or starts rejecting everything

Why? Because 30-second timeouts mean threads are tied up for 30 SECONDS
     before being released. At 1000 req/sec, that's 30,000 held threads.
```

A 30-second timeout is not "safe."
It is **dangerous**.
Set your timeout to 2-3× P99, which might be 160ms.
That means at 1000 req/sec, you hold threads for max 160ms.
At most 160 threads held at any moment.
Way more manageable.

### Timeout Propagation: The Chain Problem

In microservices, calls chain together.
Service A calls B, which calls C, which calls D.

This creates a critical rule:

```
Each timeout in the chain must be SHORTER than the one before it.

A calls B calls C calls D

A's timeout:   10 seconds
B's timeout:    8 seconds    (must be < A's timeout)
C's timeout:    5 seconds    (must be < B's timeout)
D's timeout:    2 seconds    (must be < C's timeout)
```

Why?

If C has a 10-second timeout but A only waits 8 seconds:
- A gives up at 8 seconds and returns an error
- But C is **still running** for 2 more seconds, doing useless work
- C's result will be thrown away because A already gave up

```
BAD setup (timeouts not propagated):

   A (timeout=8s)
   |
   +---> B (timeout=10s)   <-- B's timeout is LONGER than A's
         |
         +---> C (timeout=10s)
               |
               +---> D (slow)

Timeline:
t=0s:   Request starts
t=8s:   A gives up, returns error to client
t=10s:  B and C finally timeout — but A already gave up!
        B and C did 2 seconds of wasted work.
        Still holding DB connections, memory, threads.
```

```
GOOD setup (timeouts propagated correctly):

   A (timeout=8s)
   |
   +---> B (timeout=6s)
         |
         +---> C (timeout=4s)
               |
               +---> D (timeout=2s, slow)

Timeline:
t=0s:   Request starts
t=2s:   D times out, returns error to C
t=2s:   C handles error quickly, returns error to B
t=2s:   B handles error quickly, returns error to A
t=2s:   A handles error, returns error to client

Everyone cleans up quickly.
No wasted work.
```

### Deadline Propagation (the advanced version)

Even better than chained timeouts is **deadline propagation**.

Instead of each service setting its own timeout, you pass a **deadline** — an absolute time — from the very first request.

```
Client sends request at time T=0, with deadline = T+10s

A receives request. Remaining time = 10s.
|
+---> A calls B. Passes deadline: T+10s. Remaining for B = 9s.
      |
      +---> B calls C. Passes deadline: T+10s. Remaining for C = 7s.
            |
            +---> C calls D. Passes deadline: T+10s. Remaining for D = 5s.
                  |
                  D checks: "Do I have enough time to do this work?"
                  D sees only 1s left. Returns error immediately.
                  "Not enough time, won't even start."
```

This prevents useless work at every level.
If C knows the upstream deadline already passed, why start the query?

gRPC and many modern RPC frameworks support this natively.
HTTP headers like `X-Request-Deadline` or `X-Timeout` carry it.

### Timeout Lifecycle Diagram

```
                    REQUEST LIFECYCLE WITH TIMEOUT

   Thread picks up request
          |
          v
   +--------------+
   | Start timer  |
   | (e.g., 200ms)|
   +--------------+
          |
          v
   Make network call to dependency
          |
          |<--- timer running --->|
          |                       |
          |  Two possible outcomes:
          |
          +----------- (a) Response arrives before timeout -----------+
          |                                                            |
          v                                                            v
   +------------------+                                    +--------------------+
   | Timer cancelled  |                                    | TIMEOUT fires      |
   | Process response |                                    | Timer callback runs|
   | Return result    |                                    | Connection closed  |
   +------------------+                                    | Thread freed       |
                                                           | Error returned     |
                                                           +--------------------+
                                                                    |
                                                                    v
                                                           Handle timeout error:
                                                           - Log it
                                                           - Increment counter
                                                           - Try fallback
                                                           - Return 503 or 504
```

### Timeout Summary

| Setting         | Value             | Why                           |
|-----------------|-------------------|-------------------------------|
| Connection      | 1-5 seconds       | TCP should connect fast       |
| Read            | P99 × 2-3         | Buffer for slow but real work |
| Total           | Slightly > Read   | Hard ceiling                  |
| Never set to    | 0 / null / infinite | Always a mistake            |

---

## Section 3: Circuit Breakers

### The Home Electrical Analogy

In your house, every circuit has a breaker.

When too many appliances run at once, the circuit draws too much current.
The breaker **trips** — it cuts power to that circuit.
Your appliances stop working, but your house doesn't catch fire.

When the problem is fixed, you walk to the breaker box.
You flip the switch back.
Power comes on.

**The circuit breaker protected the house by accepting short-term loss to prevent total disaster.**

A software circuit breaker works the same way.
When calls to a service keep failing, the circuit breaker **trips** — it stops making those calls.
Instead of trying and failing and waiting for timeouts over and over, it **fails immediately**.
After a wait period, it cautiously tries again.

### The Three States

A circuit breaker has exactly three states.

```
+------------------------------------------+
|                                          |
|         CIRCUIT BREAKER STATES           |
|                                          |
|                                          |
|    +----------+        +----------+      |
|    |          |        |          |      |
|    |  CLOSED  |        |   OPEN   |      |
|    | (normal) |        | (tripped)|      |
|    |          |        |          |      |
|    +----------+        +----------+      |
|         |                    |           |
|         |                    |           |
|         v                    v           |
|    Requests flow         Requests        |
|    to dependency         BLOCKED         |
|    normally              Fail fast       |
|                          (no actual call)|
|                                          |
|              +-------------+            |
|              |             |            |
|              |  HALF-OPEN  |            |
|              |  (testing)  |            |
|              |             |            |
|              +-------------+            |
|                    |                    |
|                    v                    |
|              One probe request          |
|              sent to dependency         |
|                                         |
+------------------------------------------+
```

### State Transitions

```
STATE MACHINE:

                   failures > threshold
   CLOSED ---------------------------------> OPEN
     ^                                         |
     |                                         | after timeout (e.g., 30s)
     |                                         v
     |                                     HALF-OPEN
     |                                         |
     |             probe SUCCESS               |
     +<----------------------------------------+
                                               |
                         probe FAILURE         |
                         (back to full OPEN) <-+
```

Let's walk through each state:

**CLOSED state (normal operation)**
```
State: CLOSED
- All requests pass through to the dependency
- Track results in a sliding window
- Example window: last 10 requests

Window: [OK, OK, OK, FAIL, OK, OK, FAIL, FAIL, FAIL, FAIL]
        Success: 6    Fail: 5 (50%)

Threshold: 50% error rate

50% >= 50%  -->  TRIP! Move to OPEN state.
```

**OPEN state (tripping)**
```
State: OPEN
- NO requests go to the dependency
- Fail immediately without making a network call
- Return error (or fallback) right away

Timeline after tripping:
t=0s:   Circuit breaker trips
t=0-30s: ALL calls return error immediately
         No network calls made
         No timeouts waited
         Fast failure, threads freed quickly

t=30s:  Timer fires. Move to HALF-OPEN.
```

**HALF-OPEN state (cautious testing)**
```
State: HALF-OPEN
- Let ONE request through as a probe
- All other requests still fail fast

If probe SUCCEEDS:
  --> Move back to CLOSED. Service is healthy again.

If probe FAILS:
  --> Move back to OPEN. Wait another 30s. Try again.
```

### Why Circuit Breakers Are Essential: The Retry Storm

Without a circuit breaker, here is what happens when a downstream service fails:

```
WITHOUT circuit breaker:

User request --> Service A --> Service B (FAILING)
                    |               |
                    |   timeout!    |  (no response, 10s wait)
                    |               |
User retries --> Service A --> Service B (still failing)
                    |               |
                    |   timeout!    |  (another 10s wait)
                    |               |
All users retry--> 100 parallel calls to Service B
                    |               |
                   100 threads × 10s timeout
                   = 1000 thread-seconds of waste
                   Service A runs out of threads
                   Service A crashes too!

One failing service takes down a healthy service.
This is called a CASCADING FAILURE.
```

```
WITH circuit breaker:

t=0:    Service B starts failing
t=0-10: First 10 requests timeout normally. Circuit tracks: 10 fails.
t=10:   Circuit OPENS (100% failure rate exceeded threshold)

t=10+:  User requests --> Service A --> Circuit breaker: OPEN
                                         |
                                         +--> FAIL FAST (0ms)
                                              Return error or fallback

Result:
- No more calls to failing Service B
- Service A's threads are freed immediately
- Service A stays healthy
- When Service B recovers, circuit moves to HALF-OPEN, tests, re-CLOSES
```

### Circuit Breaker Pseudocode

```python
class CircuitBreaker:

    def __init__(self, failure_threshold=0.5, window_size=10, reset_timeout=30):
        self.state = "CLOSED"
        self.failure_threshold = failure_threshold  # 50%
        self.window = []                             # last N results
        self.window_size = window_size              # 10 requests
        self.reset_timeout = reset_timeout          # 30 seconds
        self.last_trip_time = None

    def call(self, func, *args):

        if self.state == "OPEN":
            # Check if reset timeout has passed
            if time_since(self.last_trip_time) > self.reset_timeout:
                self.state = "HALF-OPEN"
            else:
                raise CircuitOpenError("Service unavailable (circuit open)")

        if self.state == "HALF-OPEN":
            # Let one probe through
            try:
                result = func(*args)
                self.state = "CLOSED"   # probe succeeded
                self.window = []        # reset window
                return result
            except Exception:
                self.state = "OPEN"     # probe failed, stay open
                self.last_trip_time = now()
                raise

        # State is CLOSED — normal operation
        try:
            result = func(*args)
            self.record("success")
            return result
        except Exception as e:
            self.record("failure")
            if self.failure_rate() >= self.failure_threshold:
                self.state = "OPEN"
                self.last_trip_time = now()
            raise

    def failure_rate(self):
        if len(self.window) < self.window_size:
            return 0   # not enough data yet
        failures = self.window.count("failure")
        return failures / len(self.window)

    def record(self, outcome):
        self.window.append(outcome)
        if len(self.window) > self.window_size:
            self.window.pop(0)   # keep only last N
```

### Payment Service Walkthrough

Let's trace through a real scenario: your payment service calling an external payment gateway.

```
Setup:
  - Payment Service calls Stripe API
  - Circuit breaker: 50% threshold, 10-request window, 30s reset

Normal operation (window: 10 successes):
+----------+    +---------------+    +------------------+
| Payment  |--->| Circ. Breaker |--->| Stripe API       |
| Service  |    | State: CLOSED |    | (responding OK)  |
+----------+    +---------------+    +------------------+
                 Window: [OK OK OK OK OK OK OK OK OK OK]
                 Failure rate: 0%

Stripe starts having problems at t=0:
Request 1:  FAIL (timeout)    Window: [OK OK OK OK OK OK OK OK OK FAIL]  10% fail
Request 2:  FAIL (timeout)    Window: [OK OK OK OK OK OK OK OK FAIL FAIL] 20% fail
Request 3:  FAIL              Window: [OK OK OK OK OK OK OK FAIL FAIL FAIL] 30% fail
Request 4:  FAIL              Window: [OK OK OK OK OK OK FAIL FAIL FAIL FAIL] 40% fail
Request 5:  FAIL              Window: [OK OK OK OK OK FAIL FAIL FAIL FAIL FAIL] 50% fail

50% >= 50% threshold!
CIRCUIT OPENS at t=5 timeouts × 10s each = ~50 seconds after Stripe broke.

State: OPEN
  Request 6:  --> FAIL FAST (no call to Stripe, 0ms)
  Request 7:  --> FAIL FAST (0ms)
  ...
  All payment attempts fail instantly. Users see error page.
  No thread pile-up. Payment service stays healthy.

t = 50s + 30s reset = 80s after Stripe broke:
  State: HALF-OPEN
  Request: Probe sent to Stripe.
  
  If Stripe still broken: FAIL FAST --> back to OPEN, wait 30 more seconds
  If Stripe recovered:    SUCCESS   --> CLOSED, normal operation resumes
```

### Circuit Breaker Settings Reference

| Setting           | Typical Value      | Notes                           |
|-------------------|--------------------|---------------------------------|
| Window size       | 10-20 requests     | Enough to spot a trend          |
| Failure threshold | 50%                | Don't trip on 1-2 flukes        |
| Reset timeout     | 30-60 seconds      | Give service time to recover    |
| Min requests      | 5-10               | Don't trip on first 2 requests  |

The "minimum requests" setting prevents a new circuit from opening on its very first call.
You need enough data before tripping.

---

## Section 4: Bulkheads

### The Titanic Analogy

The Titanic was designed with hull compartments.
Each compartment could be sealed off.
If the ship took on water in one compartment, the crew sealed it.
The flooding was **contained**.

The rest of the ship kept working.
(Unfortunately the iceberg damaged too many compartments — but the design was right.)

**Bulkheads contain damage.
One flooding section cannot sink the whole ship
— unless too many sections flood at once.**

In distributed systems, a bulkhead is **thread pool isolation**.
Each dependency gets its own thread pool.
If one dependency is slow or broken, only its thread pool fills up.
Other thread pools are fine.
Other dependencies keep working.

### The Problem Without Bulkheads

Imagine your service has one shared thread pool of 100 threads.
It calls three dependencies: Database, Cache, External API.

```
WITHOUT BULKHEADS:

Thread Pool: [100 threads total, shared by all]

   Normal load:
   +--[ DB call ]---------+
   +--[ Cache call ]------+
   +--[ API call ]--------+
   Threads used: ~30. Fine.

   DB gets slow (takes 10s per query):
   t=0:   10 threads waiting for slow DB
   t=5:   30 threads waiting for slow DB
   t=10:  70 threads waiting for slow DB
   t=15:  100 threads ALL waiting for slow DB

   Now Cache calls come in: "No threads available!"
   Cache calls start failing.

   API calls come in: "No threads available!"
   API calls start failing.

   DB was slow. DB infected Cache AND API.
   One bad dependency took down everything else.

   Thread pool:
   +-----+-----+-----+-----+-----+-----+-----+-----+-----+-----+
   | DB  | DB  | DB  | DB  | DB  | DB  | DB  | DB  | DB  | DB  |
   +-----+-----+-----+-----+-----+-----+-----+-----+-----+-----+
   | DB  | DB  | DB  | DB  | DB  | DB  | DB  | DB  | DB  | DB  |
   +-----+-----+-----+-----+-----+-----+-----+-----+-----+-----+
   | DB  | DB  | DB  | DB  | DB  | DB  | DB  | DB  | DB  | DB  |
   +-----+-----+-----+-----+-----+-----+-----+-----+-----+-----+
   ... (all 100 threads blocked on slow DB)
```

### The Solution With Bulkheads

Give each dependency its own thread pool.

```
WITH BULKHEADS:

   DB Thread Pool:         [50 threads]
   Cache Thread Pool:      [30 threads]
   External API Pool:      [20 threads]

   DB gets slow (takes 10s per query):
   t=0:   DB pool filling up
   t=5:   30/50 DB threads blocked
   t=10:  50/50 DB threads blocked <-- DB pool exhausted

   Cache calls: "Use Cache pool." --> 30/30 cache threads AVAILABLE. Working fine.
   API calls:   "Use API pool."   --> 20/20 API threads AVAILABLE. Working fine.

   DB pool is full. Only DB calls are affected.
   Cache and API keep serving requests normally.
   CONTAINED damage.

   DB Thread Pool (50 threads):
   +--+--+--+--+--+--+--+--+--+--+
   |DB|DB|DB|DB|DB|DB|DB|DB|DB|DB|
   +--+--+--+--+--+--+--+--+--+--+
   |DB|DB|DB|DB|DB|DB|DB|DB|DB|DB|  <- ALL full (DB is slow)
   +--+--+--+--+--+--+--+--+--+--+
   ... (50 threads blocked on DB, fine, isolated)

   Cache Thread Pool (30 threads):
   +--+--+--+--+--+--+--+--+--+--+
   |Ca|  |  |  |  |  |  |  |  |  |  <- Only 1-2 used, rest available
   +--+--+--+--+--+--+--+--+--+--+
   (Cache pool is healthy, serving requests normally)

   API Thread Pool (20 threads):
   +--+--+--+--+--+--+--+--+--+--+
   |AP|AP|  |  |  |  |  |  |  |  |  <- A few in use, rest available
   +--+--+--+--+--+--+--+--+--+--+
   (API pool is healthy, serving requests normally)
```

### Thread Pool Isolation vs Semaphore Isolation

There are two ways to implement bulkheads:

**Thread Pool Isolation**

```
+------------------+
| Request thread   |
+------------------+
         |
         | submits task to...
         v
+------------------+
| Dependency-      |
| specific pool    |   <-- Separate threads run the actual call
+------------------+
         |
         v
   Dependency
```

- Actual calls run on **separate threads** from the request thread.
- Request thread is never blocked — it just waits for the pool result.
- Full isolation: pool exhaustion doesn't block the request thread.
- Slightly higher overhead (thread context switching).
- Best for: high-volume, latency-sensitive paths.

**Semaphore Isolation**

```
+------------------+
| Request thread   |
+------------------+
         |
         | acquires semaphore permit
         v
+------------------+
| Semaphore        |   <-- Just a counter of concurrent calls allowed
| (max=50 permits) |
+------------------+
         |
         v
   Request thread makes the call itself
```

- The **same request thread** makes the call, but a semaphore limits concurrency.
- If 50 concurrent calls are already happening, the 51st is rejected immediately.
- Lower overhead than thread pools.
- But: if the call blocks, the request thread is blocked.
- Best for: lower-volume dependencies, trusted internal services.

**Which to use?**

```
Dependency is slow / unreliable / external?   --> Thread Pool Isolation
Dependency is fast / internal / trusted?      --> Semaphore Isolation
Dependency handles sensitive operations?       --> Thread Pool Isolation
```

### Bulkhead Sizing

How big should each pool be?

Start with this formula:

```
Pool size = (P99 latency in seconds) × (target concurrent requests) × (safety factor)
```

**Example:**

Your service handles 100 concurrent users.
Each user might make a DB call.
DB P99 latency = 50ms = 0.05 seconds.

```
Pool size = 0.05s × 100 requests × 1.5 (safety)
          = 7.5
          ≈ 10 threads
```

Only 10 threads can satisfy 100 concurrent requests because each thread only holds the DB for 50ms.
During that 50ms, the same thread can be reused.

**Full example breakdown for a service:**

```
Service handles: 500 req/sec
Total thread pool available: 200 threads

+-------------------+--------+--------+----------+--------+
| Dependency        | P99    | Target | Formula  | Pool   |
|                   | Latency| Concur.|          | Size   |
+-------------------+--------+--------+----------+--------+
| Primary DB        | 20ms   |  100   | .02×100  |   50   |
| Read Cache        | 5ms    |   80   | .005×80  |   30   |
| External Payment  | 200ms  |   30   | .2×30    |   30   |
| Internal APIs     | 10ms   |  200   | .01×200  |   90   |
+-------------------+--------+--------+----------+--------+
| TOTAL             |        |        |          |  200   |
+-------------------+--------+--------+----------+--------+

DB pool fills up? Max 50 threads blocked. Cache, Payment, Internal still work.
Payment gateway slow? Max 30 threads blocked. Everything else fine.
```

### Bulkhead: What It Protects Against

```
Bulkhead protects against:  Resource exhaustion spreading from one dependency to others

Bulkhead does NOT protect against: The dependency itself being slow.
                                   (It just prevents the slowness from spreading.)
```

Use bulkheads + circuit breakers together.
Circuit breaker stops you from calling a failing service.
Bulkhead limits damage even before the circuit breaker trips.

---

## Section 5: Fallbacks

### The GPS Analogy

You're driving in the mountains.
Your GPS loses satellite signal.

A bad GPS app: shows you a blank screen with "No signal."
A good GPS app: shows you the **last known position** on a cached map.
It says "Updating..." but keeps displaying something useful.
You can still navigate, roughly.
When signal returns, it updates.

**That's a fallback.**
When the live data source fails, serve something — anything — rather than nothing.

### The Four Types of Fallbacks

**Type 1: Static Response**
```
Live service down --> Return hardcoded value

Example: Feature flag service is down
  --> Return "feature disabled" (safe default)
  --> All users see the basic version, no one errors
```

**Type 2: Cached Response**
```
Live service down --> Return last cached result

Example: Product catalog service is down
  --> Return products from cache (5 minutes old)
  --> Users see slightly stale data
  --> Better than an error page
```

**Type 3: Default Value**
```
Live service down --> Return sensible default

Example: Personalization service is down
  --> Return generic homepage (no personalization)
  --> Users see same page everyone sees
  --> No error, no crash
```

**Type 4: Degraded Version**
```
Live service down --> Return simpler version of the feature

Example: Full search with ML ranking is down
  --> Return simple keyword search results
  --> Less relevant, but still works
  --> Degraded but functional
```

### The Fallback Chain

Chain multiple fallbacks from best to worst:

```
FALLBACK CHAIN: Recommendation Service

+---------------------------+
| 1. Live recommendations   |  <-- Best: personalized, real-time
|    (ML service call)      |
+---------------------------+
          |
          | FAILS (service down / timeout)
          v
+---------------------------+
| 2. Cached recommendations |  <-- Good: personalized, slightly stale
|    (last 5 min from cache)|
+---------------------------+
          |
          | FAILS (cache miss / cache down)
          v
+---------------------------+
| 3. "Popular items" list   |  <-- OK: not personalized, but relevant
|    (static, pre-computed) |
+---------------------------+
          |
          | FAILS (static file read fails, very rare)
          v
+---------------------------+
| 4. Empty list with message|  <-- Last resort: "Nothing to show"
|    "Check back later"     |
+---------------------------+
          |
          | (never fail here — this is always available)
          v
+---------------------------+
| User sees SOMETHING       |
| Not an error page         |
+---------------------------+
```

At each step, you try the next option.
You only show an error page if every fallback exhausted.

### Fallback Decision Diagram

```
Request for recommendations
           |
           v
   Try live ML service
           |
   +-------+-------+
   |               |
SUCCESS          FAIL/TIMEOUT
   |               |
   v               v
Return live     Try cache
results         |
                +-------+-------+
                |               |
             CACHE HIT      CACHE MISS
                |               |
                v               v
            Return cache    Return popular
            results         items (static)
            (mark as        |
            slightly        v
            stale)      Log the double
                        failure
                        Return popular items
```

### What Fallbacks CANNOT Do

This is critical to understand.

**Fallbacks work for reads (getting data).**
**Fallbacks do NOT work for writes (changing data).**

```
READ operations -- fallbacks make sense:
  - Show user profile --> fallback: show cached profile
  - Get product price --> fallback: show last known price
  - Get recommendations --> fallback: show popular items

WRITE operations -- fallbacks are WRONG:
  - Process payment --> fallback: ??? CANNOT fake a payment
  - Submit order --> fallback: ??? User thinks order placed but it wasn't
  - Transfer money --> fallback: ??? Cannot pretend money moved
```

For write operations, when the downstream fails, you have two real options:
1. Return an error to the user. "Payment failed, please try again."
2. Queue the write. "Your order is being processed." (with retry logic)

**Never silently drop a write or pretend it succeeded.**
Users will be confused or worse — you'll have money problems.

### Recommendation Service Full Example

```
E-commerce site. Recommendation service is down.

Without fallback:
  User visits homepage
  --> Call recommendation service
  --> Timeout after 5s
  --> Show error: "Recommendations unavailable"
  --> User sees broken page
  --> User leaves

With fallback chain:
  User visits homepage
  --> Call recommendation service
  --> Timeout after 200ms (short timeout for non-critical)
  --> Try cache: CACHE HIT (5 minutes stale)
  --> Show cached recommendations
  --> User sees "You might also like..." (slightly stale)
  --> User stays, maybe buys something

Business impact of fallback: kept user on page, preserved revenue opportunity.
```

### Choosing Fallback Values

```
+----------------------+----------------------------------+--------------------+
| Operation            | Good Fallback                    | Bad Fallback       |
+----------------------+----------------------------------+--------------------+
| User preferences     | Default preferences              | Error              |
| Product availability | "Check availability in cart"     | Show as available  |
| Pricing              | Cached price (mark as estimate)  | Wrong price        |
| Fraud score          | Fail safe (block transaction)    | Allow transaction  |
| Search results       | Keyword-only results             | Empty results      |
| Feature flags        | Feature OFF (safe default)       | Feature ON (risky) |
+----------------------+----------------------------------+--------------------+

Note the fraud score row: sometimes the "safe" fallback is to be restrictive.
If fraud detection is down, blocking is safer than allowing.
"Fail safe" means fail in the direction of safety for your use case.
```

---

## Section 6: Load Shedding

### The Nightclub Bouncer Analogy

A nightclub has capacity for 200 people.
On a busy Saturday, 400 people line up outside.

The bouncer has two options:

**Option A (no load shedding):**
Let everyone in.
Club is at 400 people — twice capacity.
Bar can't serve people fast enough.
Bathroom lines are 30 minutes.
No one is having a good time.
Fire marshal shuts the place down.
Nobody benefits.

**Option B (load shedding):**
Let 200 people in.
Turn away 200 with "Sorry, at capacity."
Those 200 find another bar or wait outside.
The 200 inside have a great time.
Club functions perfectly.
Business survives the night.

**That's load shedding.**
Deliberately rejecting some requests so that accepted requests are served well.

It seems mean.
But it is the kindest thing you can do.
Better to tell 10% of users "try again in a moment" than to crash and tell 100% of users "nothing works."

### Why Servers Fail Under Load

```
Normal load:
  1000 req/sec --> Server --> 1000 responses/sec (50ms each)
  CPU: 40%, Memory: 50%, Queue: short

Overload (sudden spike):
  5000 req/sec --> Server --> requests pile up
  Queue grows: 100 waiting, 500 waiting, 2000 waiting...

  What happens as queue grows:
  - Memory usage rises (holding queued requests)
  - GC pressure increases (Java, Python, etc.)
  - GC pauses get longer
  - Pauses cause more queue buildup
  - More queue buildup = more memory = more GC
  - Vicious cycle

  Eventually:
  - Out of memory crash
  - OR: responses are so slow they're useless anyway
  - A 30-second response to a web request is as bad as an error

  Outcome A (no load shedding): All 5000 users wait 30 seconds then get errors
  Outcome B (load shedding):    1000 users get 50ms responses, 4000 get "try again"
```

### Types of Load Shedding

**Type 1: Queue Depth Threshold**
```
Monitor: incoming request queue length

if queue.length > MAX_QUEUE_DEPTH:
    return 429 "Too Many Requests"

Example:
  MAX_QUEUE_DEPTH = 500
  Current queue = 510
  --> Reject new incoming request with 429
  --> Queue drains, falls below 500
  --> Accept requests again
```

**Type 2: CPU / Memory Threshold**
```
Monitor: system CPU and memory usage

if cpu_usage > 80% OR memory_usage > 85%:
    reject_fraction = (cpu_usage - 80%) / 20%  # scale rejection
    if random() < reject_fraction:
        return 429

Example:
  CPU = 90%
  rejection fraction = (90-80)/20 = 50%
  --> 50% of new requests rejected
  --> CPU drops to 80%
  --> Rejection fraction drops to 0%
  --> Full traffic accepted again
```

**Type 3: Priority-Based Shedding**

Not all requests are equal.
When under stress, shed the least important ones first.

```
PRIORITY TIERS (shed from bottom):

Tier 0: System health checks         NEVER shed (must keep these)
+---------------------------------------------------+
Tier 1: Auth, payments, core writes  NEVER shed (business critical)
+---------------------------------------------------+
Tier 2: Profile reads, product reads Shed only under severe stress
+---------------------------------------------------+
Tier 3: Non-critical writes          Shed under moderate stress
+---------------------------------------------------+
Tier 4: Analytics, recommendations   Shed first, always

When CPU hits 70%: start shedding Tier 4
When CPU hits 80%: also shed Tier 3
When CPU hits 90%: also shed Tier 2
Never shed Tier 0 or Tier 1.
```

**Type 4: RED (Rate, Errors, Duration) Based Shedding**

Monitor three signals:
- **R**ate: requests per second
- **E**rrors: current error rate
- **D**uration: current P99 latency

```
RED thresholds example:
  Rate:     > 10,000 req/sec --> start shedding
  Errors:   > 5% error rate  --> start shedding (something is already wrong)
  Duration: P99 > 500ms      --> start shedding (slowing down, near overload)

If any threshold exceeded:
  - Calculate shed percentage
  - Reject that percentage of non-critical requests
```

### The 429 Response

When you shed load, return this HTTP response:

```
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 5
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1718000100

{
  "error": "rate_limit_exceeded",
  "message": "Server under heavy load. Please retry after 5 seconds.",
  "retry_after": 5
}
```

The `Retry-After` header tells the client exactly how long to wait.
Good clients honor this.
They wait 5 seconds and try again.
The server gets breathing room.

**Don't just return 500 (Internal Server Error).**
500 says "I'm broken."
429 says "I'm fine, just busy — try again soon."
This helps clients behave correctly.

### Priority-Based Shedding Example

```
E-commerce site under DDoS traffic spike.
Normal load: 1,000 req/sec
Current load: 8,000 req/sec

Tier classification:
+------------------+------------------+----------------------------------+
| Request Type     | Tier             | Current Action                   |
+------------------+------------------+----------------------------------+
| /healthz         | Tier 0           | PASS (always)                    |
| /login           | Tier 1           | PASS (auth is critical)          |
| /checkout        | Tier 1           | PASS (revenue critical)          |
| /product/123     | Tier 2           | PASS for 50% (partial shed)      |
| /search?q=shoes  | Tier 2           | PASS for 50% (partial shed)      |
| /cart/add        | Tier 3           | SHED (not immediately critical)  |
| /recommendations | Tier 4           | SHED (non-critical)              |
| /analytics/track | Tier 4           | SHED (can lose this data)        |
+------------------+------------------+----------------------------------+

Result:
  Tier 0 + Tier 1 traffic: ~500 req/sec  (always served)
  Tier 2 at 50%:           ~1,000 req/sec (partial service)
  Tier 3 + Tier 4: SHED

Total served: ~1,500 req/sec vs system capacity of ~2,000 req/sec
System healthy, critical paths functioning.
Users who can't check out: few (Tier 1 pass-through).
Users who can't get recommendations: many (Tier 4 shed). Fine.
```

### Load Shedding vs Rate Limiting: The Difference

These sound similar but they solve different problems:

```
RATE LIMITING:
  Goal:      Prevent any single USER from abusing the system
  Per:       Per user, per API key, per IP
  Trigger:   "You've sent 100 requests in 1 minute, slow down"
  Protects:  Against individual bad actors
  Normal:    Most users never hit rate limits
  Example:   "Your API key allows 1,000 req/min"

LOAD SHEDDING:
  Goal:      Protect the SYSTEM from being overwhelmed overall
  Per:       Global / system-wide
  Trigger:   "The whole system is at capacity right now"
  Protects:  Against overload even from legitimate traffic
  Normal:    Most traffic patterns never trigger load shedding
  Example:   "We're at capacity, please retry in 5 seconds"
```

```
You need BOTH:

  User sends 10,000 req/min:    Rate limiting kicks in (block that user)
  1 million users all at once:  Load shedding kicks in (protect system)
  
  Rate limiting without load shedding: one user can't DOS, but a traffic
    spike (like a viral tweet about your product) can still crash you.
    
  Load shedding without rate limiting: system survives spikes, but a
    single bad actor can eat all your capacity.
```

### Implementing Graceful Load Shedding

```
Where to place load shedding:

Option 1: At the load balancer / gateway (recommended)
  +------------------+
  |   Load Balancer  |
  |   / API Gateway  |   <-- Shed here FIRST
  +------------------+
           |
           v
  +------------------+
  |   Your Service   |   <-- Already-shed traffic arrives here
  +------------------+

  Advantage: cheap, before hitting your service at all.

Option 2: In the service itself
  +------------------+
  |   Your Service   |
  |  (check CPU/mem) |   <-- Shed here if you need app-level awareness
  +------------------+

  Advantage: can make smarter decisions (priority-based, per-feature).

Best practice: BOTH.
  Gateway: shed based on request rate.
  Service: shed based on internal state (CPU, queue, feature priority).
```

---

## Section 7: Putting It All Together

### The Full Request Flow

Here is what a production request goes through with all defenses in place:

```
INCOMING REQUEST
      |
      v
+----------------------+
| API GATEWAY /        |
| LOAD BALANCER        |
|                      |
| - Rate limiting      |    <-- Block abusive clients
| - Rough load shedding|    <-- Block if at capacity
+----------------------+
      |
      | (request passed through)
      v
+----------------------+
| SERVICE ENTRY POINT  |
|                      |
| - Auth check         |    <-- Validate request is legitimate
| - Fine-grained       |
|   load shedding      |    <-- Shed by priority if under stress
+----------------------+
      |
      | (request accepted, now processing)
      v
+----------------------+
| CIRCUIT BREAKERS     |
| (per dependency)     |
|                      |
| - Check DB circuit   |    <-- Is DB circuit OPEN? Fail fast, use fallback
| - Check cache circuit|    <-- Is cache circuit OPEN? Skip cache, go to DB
| - Check API circuit  |    <-- Is external API OPEN? Return cached data
+----------------------+
      |
      | (circuit is CLOSED, proceed)
      v
+----------------------+
| BULKHEADS            |
| (thread pool per dep)|
|                      |
| - DB pool            |    <-- Use DB thread pool
| - Cache pool         |    <-- Use cache thread pool
| - External API pool  |    <-- Use API thread pool
+----------------------+
      |
      | (acquired thread from pool)
      v
+----------------------+
| TIMEOUTS             |
| (per call)           |
|                      |
| - Set timer          |    <-- Start countdown
| - Make actual call   |    <-- Call dependency
| - Cancel if timeout  |    <-- Free thread if too slow
+----------------------+
      |
      | (call returns — success or timeout/error)
      v
+----------------------+
| FALLBACK HANDLER     |
|                      |
| - Success? Return it |    <-- Happy path
| - Error? Try cache   |    <-- Fallback level 1
| - No cache? Default  |    <-- Fallback level 2
| - Nothing? Error msg |    <-- Last resort
+----------------------+
      |
      v
RESPONSE TO CLIENT
```

Every layer is a safety net.
If one layer fails to catch a problem, the next one does.

### E-Commerce Checkout: Full Walkthrough

Let's trace a checkout request through every defense layer.

```
User clicks "Place Order"

Request: POST /api/checkout
         { cart_id: 123, payment: {...}, shipping: {...} }

System state during this example:
  - Inventory service: SLOW (high load)
  - Payment gateway: HEALTHY
  - Order DB: HEALTHY
```

**Step 1: API Gateway**
```
Gateway checks:
  - Rate limit for this user: 50 req/min, user has sent 3 this minute. OK.
  - Global load: CPU at 65%. Below 80% threshold. OK.
  - Request passes through.
```

**Step 2: Service Entry Point**
```
Checkout service checks:
  - Priority of request: /checkout = Tier 1. Will never be shed. OK.
  - Auth token valid: yes. OK.
  - Request proceeds to business logic.
```

**Step 3: Circuit Breakers**
```
Checkout needs three dependencies:
  1. Inventory service (check item availability)
  2. Payment gateway (charge card)
  3. Order DB (save order)

Check circuits:
  Inventory service circuit: OPEN! (was failing, 60% error rate, tripped 20s ago)
  Payment gateway circuit: CLOSED. (healthy)
  Order DB circuit: CLOSED. (healthy)

For inventory: circuit is OPEN. Don't call it. Use fallback.
  Fallback: assume item is available (optimistic). Mark order as "availability pending."
For payment: circuit CLOSED. Proceed to call it.
For Order DB: circuit CLOSED. Proceed to call it.
```

**Step 4: Bulkheads**
```
Checkout acquires threads:
  Inventory: skipped (circuit OPEN)
  Payment gateway pool: 30 threads total. 8 currently in use. Acquire one. OK.
  Order DB pool: 50 threads total. 12 currently in use. Acquire one. OK.

If DB pool was full (50/50):
  --> Reject request immediately with 503. Don't wait for a thread.
  --> Better than queuing and causing memory issues.
```

**Step 5: Timeouts**
```
Payment gateway call:
  Connection timeout: 3 seconds (TCP connect)
  Read timeout: 5 seconds (payment processing)
  (Propagated deadline from original request: 10 seconds remaining)

Order DB write:
  Connection timeout: 1 second
  Read timeout: 2 seconds

Both calls proceed with timers set.
```

**Step 6: Calls complete**
```
Payment gateway: SUCCESS (took 800ms, well within 5s timeout)
Order DB write: SUCCESS (took 12ms, well within 2s timeout)
```

**Step 7: Fallback Handler**
```
Inventory (was skipped due to circuit OPEN):
  Fallback used: assume available. Mark order "pending inventory check."
  Background job will re-check inventory when circuit closes.

Payment: SUCCESS. No fallback needed.
Order DB: SUCCESS. No fallback needed.
```

**Step 8: Response**
```
HTTP/1.1 200 OK
{
  "order_id": "ORD-789",
  "status": "processing",
  "payment": "confirmed",
  "inventory": "pending_confirmation",
  "message": "Your order is placed! We'll confirm availability shortly."
}

User experience: order placed successfully.
                 Small note about inventory confirmation.
                 Not an error. Not a failure.
                 Graceful degradation.
```

The checkout succeeded despite the inventory service being broken.

### The Complete Defense Stack Decision Tree

```
Something is wrong with a dependency.
Walk through this tree:

         Is the call timing out?
         /        \
       YES         NO
       |            |
       v            v
  Adjust       Is it returning errors?
  timeout?     /            \
              YES            NO
              |               |
              v               v
        Is error rate    Then what's wrong?
        > 50%?           (different problem)
        /     \
      YES      NO
      |         |
      v         v
   OPEN       Keep trying
   circuit    (circuit stays
   breaker    CLOSED)
      |
      v
   Available?
   /       \
 YES        NO
  |          |
  v          v
 Use        Use
fallback    default
  |          |
  v          v
Is system  Return 429
at capacity? (load shed)
  /    \
YES    NO
 |      |
 v      v
Shed   Process
low    request
priority normally
requests
```

### Staff Engineer Insight Box

```
+------------------------------------------------------------------+
|                                                                  |
|   STAFF ENGINEER INSIGHT: Defense in Depth                      |
|                                                                  |
|   Junior engineers ask: "Which pattern should I use?"           |
|   Staff engineers answer: "All of them, layered."               |
|                                                                  |
|   The patterns are not alternatives. They are complements.      |
|                                                                  |
|   TIMEOUT catches slow calls before they pile up.               |
|   CIRCUIT BREAKER catches systematic failures fast.             |
|   BULKHEAD prevents failures from spreading sideways.           |
|   FALLBACK keeps partial functionality running.                 |
|   LOAD SHEDDING saves the system when overwhelmed.              |
|                                                                  |
|   Miss any one, and you have a gap.                             |
|                                                                  |
|   Real production systems need all five:                        |
|   - Timeouts on every network call                              |
|   - Circuit breakers on every dependency                        |
|   - Bulkheads on every thread pool                              |
|   - Fallbacks for every non-critical read                       |
|   - Load shedding at the gateway and service level              |
|                                                                  |
|   Second insight: set aggressive timeouts.                      |
|   Most engineers set timeouts 10x too long "to be safe."        |
|   That's not safe. That's dangerous.                            |
|   Safe is short timeouts + good fallbacks.                      |
|                                                                  |
|   Third insight: test your fallbacks.                           |
|   Fallback code is rarely tested in development.                |
|   Run chaos engineering to make sure fallbacks work.            |
|   The fallback that was never tested will fail when you         |
|   need it most.                                                  |
|                                                                  |
+------------------------------------------------------------------+
```

### Common Interview Questions and Answers

**Q: "How would you prevent a slow database from crashing your service?"**

```
Full answer:

1. Timeouts (immediate protection)
   Set read timeout to P99 × 2-3. If DB is slow, timeout quickly.
   Don't hold threads for 30 seconds.

2. Circuit breaker (systematic protection)
   If DB timeouts hit 50%+ over a 10-request window, OPEN the circuit.
   Fail fast without waiting for timeouts.

3. Bulkhead (blast radius containment)
   Give DB its own thread pool (e.g., 50 threads).
   DB slowness can't use more than 50 threads.
   Other dependencies unaffected.

4. Fallback (degraded functionality)
   For read operations: use cache fallback.
   For write operations: queue writes, retry when DB recovers.

5. Load shedding (if truly overwhelmed)
   If all 50 DB threads are full, reject new DB-bound requests
   with 503 rather than queuing more.
```

**Q: "What is the difference between a circuit breaker and a timeout?"**

```
Timeout: per-call protection
  "I've been waiting 200ms, I give up on THIS call."
  Works for occasional slow responses.

Circuit breaker: systematic protection
  "10 of the last 10 calls failed, stop calling entirely."
  Works when a service is down/broken for an extended period.

They work together:
  Timeout detects single slow calls.
  Those timed-out calls count as failures in the circuit breaker.
  When failures accumulate, circuit opens.
  Circuit breaker prevents future timeouts from even happening.
```

**Q: "How would you handle a Black Friday traffic spike?"**

```
Answer includes ALL layers:

Pre-spike (before Black Friday):
  - Load test to find actual capacity limits
  - Set load shedding thresholds based on real numbers
  - Ensure all circuit breakers are configured
  - Pre-warm caches with popular product data
  - Pre-compute recommendation lists

During spike:
  - Auto-scaling: add more servers (horizontal scaling)
  - Load shedding: shed analytics, recommendations first (Tier 4)
  - Cache-first: serve as much as possible from cache
  - Circuit breakers: protect external payment gateway
  - Fallbacks: if inventory service overwhelmed, show "add to cart" and verify asynchronously

Priority protection:
  - Tier 1 (checkout, payments): never shed. These are revenue.
  - Tier 2 (product pages): partial shed if needed.
  - Tier 4 (analytics): shed completely. Don't need real-time analytics on Black Friday.

The goal: everyone who wants to BUY can buy.
          Everyone who just wants to BROWSE might see slower pages.
          That's acceptable.
```

### Quick Reference Card

```
+------------------+----------------------------+-------------------------+
| Pattern          | Protects Against           | Key Setting             |
+------------------+----------------------------+-------------------------+
| Timeout          | Thread exhaustion from     | P99 × 2-3x, per call   |
|                  | slow dependencies          |                         |
+------------------+----------------------------+-------------------------+
| Circuit Breaker  | Cascading failures from    | 50% error rate,         |
|                  | broken dependencies        | 10-request window,      |
|                  |                            | 30s reset               |
+------------------+----------------------------+-------------------------+
| Bulkhead         | Failure spreading across   | Separate pool per dep.  |
|                  | dependencies               | P99 × concurrency       |
+------------------+----------------------------+-------------------------+
| Fallback         | Bad user experience when   | Cached → static →       |
|                  | dependencies fail          | default → error         |
+------------------+----------------------------+-------------------------+
| Load Shedding    | System crash from          | Tier-based, return 429  |
|                  | overload                   | with Retry-After        |
+------------------+----------------------------+-------------------------+
```

### The One Mental Model

If you remember only one thing from this entire part, remember this:

```
Every call you make to another service is a gamble.
That service WILL be slow or broken at some point.
Your job is to make sure THEIR bad day doesn't become YOUR bad day.

Timeouts:          "I won't wait for you forever."
Circuit Breakers:  "If you keep failing, I'll stop asking."
Bulkheads:         "Your failure can only hurt so much of me."
Fallbacks:         "I have a backup plan when you're not around."
Load Shedding:     "I know my limits and I'll enforce them."

Together: your service keeps running even when everything around it is on fire.
```

---

## Summary: Part B in One Page

```
THE DEFENSE STACK

1. TIMEOUT
   Set it: P99 latency × 2-3x (not 30 seconds "to be safe")
   Purpose: Free threads from slow dependencies
   Rule:    Propagate deadlines through service chains
   Never:   Set to "none" or "infinite"

2. CIRCUIT BREAKER
   Three states: CLOSED (normal) → OPEN (tripped) → HALF-OPEN (testing)
   Trips when: 50%+ failures over 10-request window
   Resets when: 30s passes, probe succeeds
   Purpose: Stop calling broken services, fail fast instead

3. BULKHEAD
   What: Separate thread pool per dependency
   Purpose: Slow DB can only fill DB pool, not Cache pool
   Size: P99 latency × target concurrency × safety factor
   Types: Thread pool isolation (strong) vs semaphore (lighter)

4. FALLBACK
   Chain: live → cache → static → error
   Works for: reads (show stale data, defaults, degraded version)
   Does NOT work for: writes (never fake a payment or order)
   Test it: your fallback code must be tested before you need it

5. LOAD SHEDDING
   Why: better to reject 10% than to crash and fail 100%
   Priority tiers: Tier 0 (health) → Tier 1 (payments) → ... → Tier 4 (analytics)
   Shed Tier 4 first, never shed Tier 0 or Tier 1
   Return: 429 with Retry-After header
   Different from: rate limiting (per-user) vs load shedding (global)

USE ALL FIVE. They are layers, not alternatives.
```

---

*End of Chapter 25, Part B*
# Chapter 25: Failure Models and Partial Failures
## Part C1: Graceful Degradation, Thundering Herd, Cascading Failures, Metastable Failures

---

## 1. Graceful Degradation — Designing Failure Modes in Advance

### The Core Idea

Most engineers design for success. They ask: "How does this work when everything is healthy?"

The senior engineer asks a different question: "How does this work when things break?"

Graceful degradation means planning your failure modes *before* you need them. Not improvising at 3 AM when the system is on fire. Not discovering what "partial outage" looks like while users are screaming. Planning it, testing it, and shipping it as a feature.

### The Airplane Analogy

Think about how airplanes are designed.

A commercial airplane has two engines. If one engine fails at 35,000 feet, the plane does not crash. It can fly on one engine. It may divert to the nearest airport. It may turn off non-essential systems — the in-flight entertainment goes dark, some cabin lights go dim — to conserve power for the things that matter. The pilots land the plane safely.

Now imagine the airplane was NOT designed this way. Imagine the pilots discovered "how to fly on one engine" *during the emergency* while passengers were panicking. How would that go?

That is exactly what happens when engineers discover degradation modes during an incident.

The airplane engineers planned this out in advance:
- Two engines fail independently? Here is what we do.
- What gets shut off first? Entertainment. Non-essential lights.
- What stays on no matter what? Navigation. Controls. Landing gear.
- At what point do we declare emergency and divert?

They built a ladder of responses for every level of failure, tested each level, trained pilots on each level. By the time the failure happens, everyone knows exactly what to do.

Your system needs the same thing.

### The E-Commerce Degradation Ladder

Here is a concrete example. Imagine you run an e-commerce website. You have a lot of moving parts: a personalization engine, a recommendation service, multiple payment processors, inventory systems, and so on.

What happens when pieces fail?

If you have NOT planned this, the answer is: chaos. Some pages 500. Some load half-broken. The checkout might silently fail. Users lose trust.

If you HAVE planned this, you have a ladder — a pre-defined set of tiers that the system can drop into, each worse than the last but still controlled and predictable.

```
E-COMMERCE DEGRADATION LADDER
==============================

TIER 0 — 100% HEALTHY
+--------------------------------------------------+
|  - Personalized homepage ("Hi Ranjeet, welcome") |
|  - ML recommendations ("You might also like...")  |
|  - All payment methods (cards, wallets, BNPL)    |
|  - Real-time inventory counts                    |
|  - Order history and tracking                    |
|  - Search with personalized ranking              |
+--------------------------------------------------+
                       |
              [Rec service fails]
                       |
                       v
TIER 1 — 80% — RECOMMENDATIONS DOWN
+--------------------------------------------------+
|  - Personalized homepage still works             |
|  - "Popular items" shown instead of ML recs      |
|    (pre-cached top-sellers list, always available)|
|  - All payment methods still work                |
|  - Everything else unchanged                     |
|  User impact: minor, most users won't notice     |
+--------------------------------------------------+
                       |
         [Personalization service fails]
                       |
                       v
TIER 2 — 60% — PERSONALIZATION DOWN
+--------------------------------------------------+
|  - Generic homepage (no "Hi Ranjeet")            |
|  - "Popular items" still showing                 |
|  - All payment methods still work                |
|  - User still can browse, search, buy            |
|  User impact: moderate, feels like a generic site|
+--------------------------------------------------+
                       |
        [New payment processor fails]
                       |
                       v
TIER 3 — 40% — LIMITED PAYMENTS
+--------------------------------------------------+
|  - Generic homepage                              |
|  - Popular items                                 |
|  - Saved cards only (no new cards, no wallets)   |
|  - Banner: "Some payment options temporarily     |
|    unavailable. Your saved card still works."    |
|  User impact: significant, new users can't buy   |
+--------------------------------------------------+
                       |
           [Core payment service fails]
                       |
                       v
TIER 4 — 20% — BROWSE ONLY
+--------------------------------------------------+
|  - Full browse and search still works            |
|  - Product pages still load                      |
|  - Checkout DISABLED                             |
|  - Banner: "Checkout temporarily unavailable.    |
|    We're back shortly. Add to cart still works." |
|  User impact: severe, no revenue, but data safe  |
+--------------------------------------------------+
                       |
          [Database / core systems fail]
                       |
                       v
TIER 5 — 0% — MAINTENANCE PAGE
+--------------------------------------------------+
|  - Static HTML page only                         |
|  - "We're doing maintenance. Back soon."         |
|  - Status page URL                               |
|  - No database calls, no app servers needed      |
|  User impact: total, but controlled and honest   |
+--------------------------------------------------+
```

Notice what this ladder gives you:

1. At every tier, the site is still coherent. It does not half-work. It works at a reduced level, by design.
2. Users see honest messaging, not broken pages.
3. Engineers have a clear target. Tier 3 is not a disaster, it is a known state.
4. You can test each tier before you need it.

### How to Design Your Degradation Ladder

For each feature in your system, ask two questions:

**Question 1: What does this feature depend on?**

Draw the dependency graph. A recommendation widget depends on: the recommendation service, user history, item catalog. If ANY of those go down, the widget cannot work in full form. But maybe it can show "popular items" if just the user-history part fails. Maybe it shows nothing if the item catalog fails.

**Question 2: What can I show if that dependency fails?**

For each dependency failure, what is the fallback?
- Dependency fails → show cached data from 24 hours ago
- Dependency fails → show a generic version
- Dependency fails → hide the feature entirely
- Dependency fails → show static content

Go through every feature. Fill in the fallback for every dependency. Now you have your ladder.

### Feature Flags for Manual Degradation

Sometimes you want the ability to manually flip a switch and disable a feature, without waiting for automatic detection.

Maybe a new payment processor is causing weird errors. You do not have automatic detection set up yet. But you want to be able to say: "Turn off the new payment processor right now, serve saved-cards-only."

Feature flags give you this.

```
MANUAL DEGRADATION VIA FEATURE FLAGS
=====================================

NORMAL STATE:
+------------------+    +-----------------------+
|  Feature Flag    |    |  Application Logic    |
|  Store           |    |                       |
|                  |    |  if flag("new_payment")|
|  new_payment=ON  +--->|    use new processor  |
|  ml_recs=ON      |    |  else                 |
|  personalize=ON  |    |    use saved cards    |
+------------------+    +-----------------------+

INCIDENT — ENGINEER FLIPS FLAG:
+------------------+    +-----------------------+
|  Feature Flag    |    |  Application Logic    |
|  Store           |    |                       |
|                  |    |  if flag("new_payment")|
|  new_payment=OFF +--->|    use new processor  |
|  ml_recs=ON      |    |  else  <== TAKES THIS |
|  personalize=ON  |    |    use saved cards    |
+------------------+    +-----------------------+

Engineer changes ONE flag. All instances pick it up within seconds.
No deploy. No code change. No risky rollout.
System drops to Tier 3 in a controlled, pre-planned way.
```

This is why feature flags are considered a safety feature, not just a release tool. They are your emergency brake.

### The 3 AM Rule

Here is the principle that ties this all together:

**"If you haven't designed the degraded state, you'll accidentally design it under pressure at 3 AM."**

When a failure hits and there is no plan, engineers improvise. They make quick decisions under stress. They might:
- Disable a feature in a way that breaks something else
- Leave the system in a half-broken state that confuses users
- Make the fallback worse than the failure

Pre-designed degradation states are tested, documented, and safe. The 3 AM improvised degradation state is none of those things.

Spend thirty minutes now designing your ladder. Save yourself hours of chaos later.

---

## 2. Thundering Herd — Recovery That Kills

### The Core Idea

A thundering herd happens when a large number of clients or requests all do the same thing at the same time, creating a spike of load that overwhelms a system.

The dangerous thing about thundering herds: they often happen during *recovery*, not during the initial failure. Your system goes down, starts recovering, and then the thundering herd kills it again before it can get back on its feet.

### The Traffic Light Analogy

Picture a busy intersection. A traffic light gets stuck on red. Cars back up for twenty minutes. Now there are two hundred cars waiting at the light.

The light turns green.

All two hundred cars accelerate at once. The intersection is immediately jammed. Cars trying to turn left are blocked. The queue clears the light but backs up the cross street. The "recovery" created a new traffic jam that takes another ten minutes to clear.

This is a thundering herd. The sudden synchronized behavior of all those cars — all reacting to the same trigger at the same time — overwhelmed the system even though each individual car was doing the right thing.

### Three Forms of Thundering Herd

#### Form 1: Cache Stampede

You have a popular product page. It gets cached for one hour. At the end of that hour, the cache entry expires.

In that exact moment, one hundred users are on the site. All one hundred requests arrive at the cache. They all see: cache miss. They all think: "I need to fetch this from the database." All one hundred go to the database simultaneously.

```
CACHE STAMPEDE
==============

BEFORE EXPIRY — healthy:
 Users --> [ Cache: HIT ] --> returns cached page
            (no DB hit)

AT EXPIRY MOMENT:
 100 users arrive simultaneously
       |
       v
 [ Cache: MISS ] <-- all 100 see this
       |
       | (all 100 fire DB queries)
       v
+------+------+------+------+ ... (100 total)
|  DB  |  DB  |  DB  |  DB  |
| query| query| query| query|
+------+------+------+------+

DB connection pool: max 20 connections
80 queries wait in queue
DB CPU spikes to 100%
Query time goes from 5ms to 4000ms
Other queries (for other pages) also slow down
Site-wide slowdown from ONE cache expiry
```

The database did not fail. It got overwhelmed by a synchronized rush caused by a single cache miss.

#### Form 2: Restart Storm

You have fifty application instances. There is a deployment. All fifty instances restart at roughly the same time.

When they restart, their local caches are empty (cold start). Every request they handle goes to the database. All fifty instances, handling traffic, all cold, all hammering the database simultaneously.

The database handles normal traffic fine. It cannot handle fifty cold instances all hitting it at once during startup.

#### Form 3: Retry Storm

A dependency service goes down for two minutes. Every client has retry logic. The retry interval is set to exactly 30 seconds.

The service comes back up. In the next 30 seconds, every single client fires a retry. The service that just barely recovered from the outage is immediately hit with the backlog of all retried requests plus normal traffic. It falls over again.

The retries are synchronized because they all started at roughly the same time (when the dependency went down) and all have the same retry interval.

### Prevention: Cache Stampede

**Method 1 — Probabilistic Early Expiry**

Instead of letting the cache entry expire and then scrambling to fill it, start refreshing it *before* it expires. The idea: when a request checks the cache and finds an entry that is close to expiring, there is a small random probability it will go ahead and refresh it early.

```
Normal TTL: 60 minutes
Early refresh window: last 5 minutes of TTL

At T=55 minutes, each request has a 10% chance of triggering a refresh.
One request wins the coin flip and refreshes the cache.
By T=60 minutes, the cache already has a fresh entry.
No stampede ever happens.
```

**Method 2 — Mutex / Single-Fill**

When the cache misses, only ONE thread is allowed to go to the database. The other threads wait for that one thread to finish and populate the cache. Then all threads read from the cache.

```
WITHOUT MUTEX:
100 cache misses --> 100 DB queries (stampede)

WITH MUTEX:
100 cache misses --> thread 1 acquires lock --> goes to DB
                     threads 2-99 wait for lock
                     thread 1 fills cache, releases lock
                     threads 2-99 read from cache (hit)
                 --> 1 DB query total
```

**Method 3 — Jitter on TTLs**

Do not set the same TTL for all cache entries of the same type. Add random jitter.

```
WITHOUT JITTER: all 1000 product pages cached with TTL=60min
  --> all expire at roughly the same time
  --> stampede at T=60min

WITH JITTER: TTL = 60min + random(0 to 10min)
  --> entries expire spread across a 10-minute window
  --> ~100 entries expire per minute instead of 1000 at once
  --> smooth, manageable load on DB
```

### Prevention: Restart Storm

**Rolling Restarts**: restart one instance at a time, wait for it to become healthy before restarting the next one. Never have more than a few instances simultaneously in cold-start state.

**Stagger Startup**: add a delay between instance starts. 30 seconds between each instance gives the database time to handle the cold-start load before the next instance adds to it.

**Cache Pre-Warming**: before traffic hits a newly started instance, pre-load its cache from a snapshot. The instance starts warm instead of cold, reducing the DB hammering during startup.

### Prevention: Retry Storm

The key is exponential backoff WITH jitter. This is so important it deserves its own diagram.

```
RETRY BEHAVIOR COMPARISON
==========================

SCENARIO: 100 clients all lose connection at T=0

WITHOUT JITTER (exponential backoff only):
T=0    : all connections fail
T=1s   : SPIKE -- all 100 clients retry simultaneously  [##########]
T=2s   : SPIKE -- all 100 clients retry again          [##########]
T=4s   : SPIKE -- all 100 clients retry again          [##########]
T=8s   : SPIKE -- all 100 clients retry again          [##########]

Service recovers at T=3s, immediately hit by spike at T=4s
Service goes down again.

WITH JITTER (exponential backoff + random jitter):
T=0    : all connections fail
T=0.3s : client 7 retries                              [#]
T=0.8s : clients 3,41 retry                            [##]
T=1.2s : clients 12,67,88 retry                        [###]
T=1.6s : clients 5,19,33,72 retry                      [####]
T=2.1s : clients 2,28,55,63 retry                      [####]
... spread over many seconds, smooth load ...

Service recovers at T=3s, sees gradual ramp-up
Service stays up and clients reconnect over ~10 seconds
```

The jitter breaks the synchronization. Instead of a wave that overwhelms the system, you get a smooth distribution that the system can handle.

The formula: `wait = min(cap, base * 2^attempt) * random(0.5, 1.5)`

The `random(0.5, 1.5)` is the jitter. It spreads retries across a window instead of concentrating them at a point.

---

## 3. Cascading Failures — When One Failure Becomes Total Outage

### The Domino Analogy

Stand up a thousand dominoes in a line. Push the first one. It falls into the second. The second falls into the third. Eventually all one thousand are down.

Nobody said "knock down all the dominoes." One push, one failure, propagated through tight coupling.

Cascading failures work the same way. One service slows down. That slowness spreads to the services depending on it. Those services slow down, which spreads to the services depending on *them*. A single point failure becomes a total outage.

### What Makes Cascading Failures Happen

**Tight Coupling via Synchronous Calls**

Service A calls Service B synchronously. A cannot finish its request until B responds. If B is slow, A is slow. Every request to A that touches B is now slow. A's thread pool fills with threads all waiting for B. A becomes unresponsive. Services calling A are now waiting on A.

The slowness spreads upstream.

**Shared Resources**

A database connection pool is shared by many services. One service starts making slow queries, holding connections. Other services cannot get connections. They queue. The queue fills. They time out. They look unresponsive.

One slow query path takes down unrelated features because they share a resource.

**Retry Amplification**

A slow dependency causes requests to time out. Those timed-out requests retry. Now there are two requests in flight for every one original request. If those also time out, four requests. Load on the slow dependency increases. It gets slower. More timeouts. More retries. Exponential amplification of load on an already struggling system.

### Full Cascade Anatomy

Here is a realistic cascade scenario. Walk through it carefully.

```
CASCADING FAILURE — STEP BY STEP
==================================

NORMAL STATE:
+----------+    +----------+    +----------+
| Service A|--->| Service B|--->| Service C|
| (frontend|    | (business|    | (database|
|  calls)  |    |  logic)  |    |  queries)|
+----------+    +----------+    +----------+
Latency: A=50ms, B=30ms, C=10ms. Healthy.

STEP 1: C enters a GC (garbage collection) pause
+----------+    +----------+    +----------+
| Service A|--->| Service B|--->| Service C|
+----------+    +----------+    | [GC PAUSE|
                                |  not dead|
                                |  just    |
                                |  slow:   |
                                |  3000ms] |
                                +----------+
C is not down. Health checks pass. It responds, just slowly.

STEP 2: B's threads fill waiting for C (10s timeout, no bulkhead)
+----------+    +----------+    +----------+
| Service A|--->| Service B|--->| Service C|
+----------+    | Thread 1:|    | [GC PAUSE|
                | waiting  |    |  3000ms] |
                | for C... |    +----------+
                | Thread 2:|
                | waiting  |
                | for C... |
                | Thread 3:|
                | waiting  |
                | for C... |
                | ...      |
                | Thread 50|  <-- thread pool FULL
                | waiting  |
                +----------+
B's thread pool is exhausted. New requests to B queue up.
B appears slow/unresponsive to A.

STEP 3: A's threads fill waiting for B
+----------+    +----------+    +----------+
| Service A|    | Service B|    | Service C|
| Thread 1:|    | Thread 1:|    | [GC PAUSE|
| waiting  |--->| waiting  |    |  3000ms] |
| for B... |    | for C... |    +----------+
| Thread 2:|    | Thread 2:|
| waiting  |    | waiting  |
| for B... |    | for C... |
| ...      |    | ...      |
| Thread 50|    | Thread 50|
| waiting  |    | waiting  |
+----------+    +----------+
A's thread pool is now exhausted.
Users calling A get no response.

STEP 4: Health checks fail on A
Load balancer sees A not responding to health checks.
Removes A instance from rotation.
Sends traffic to other A instances.

STEP 5: Other A instances also fill threads
Other A instances now receive MORE traffic (they absorbed
the traffic from the removed instance). They ALSO start
waiting for B, which is waiting for C. Their thread pools
fill even faster.

STEP 6: Complete outage
All A instances have full thread pools.
No requests can be served.
Total outage — caused by ONE GC pause in C.

TIMELINE: C's GC pause: 3 seconds
          Total outage: 45 seconds later
          Root cause: 3 levels of tight coupling,
                      no timeouts short enough to break cascade,
                      no bulkheads to contain blast
```

The GC pause in C lasted 3 seconds. The outage lasted minutes. One slow service took down everything.

### Breaking the Cascade at Each Step

The cascade above had four places it could have been broken. Each represents a protection mechanism:

**Timeouts — Stop Waiting**

If B had a timeout of 500ms on calls to C (instead of 10 seconds), B's threads would have freed up after half a second. The cascade would not have reached A. Threads would have returned errors, but they would have returned *quickly*. The pool would have stayed manageable.

Rule: every synchronous call needs a timeout. No exceptions. The timeout should be shorter than you think — if your SLA is 1 second, your timeouts on dependencies should be 200-300ms.

**Circuit Breakers — Stop Calling**

A circuit breaker monitors the error rate on calls to a dependency. When errors pass a threshold (say, 50% of calls failing), the circuit "trips" open. Further calls are rejected immediately without even trying to reach the dependency. After a recovery period, the circuit tries a few requests — if they succeed, it closes.

```
CIRCUIT BREAKER STATES:

CLOSED (normal):
  Request --> [CB: closed] --> Service C
  All calls go through. CB tracks error rate.

OPEN (tripped):
  Request --> [CB: OPEN] --> returns error immediately
  No calls reach C. C gets a chance to recover.
  No threads wasted waiting.

HALF-OPEN (testing recovery):
  Request --> [CB: half-open] --> lets 1 request through to C
  If C responds ok: CB closes again
  If C still fails: CB opens again
```

If B had a circuit breaker on calls to C, the moment C started failing, the CB would have tripped. B's threads would not have filled. Cascade stops at C.

**Bulkheads — Contain the Blast**

A bulkhead gives each downstream dependency its own thread pool. Calls to C use a pool of 10 threads. Calls to D use a different pool of 10 threads. If C is slow and fills its 10-thread pool, it does not affect calls to D.

```
WITHOUT BULKHEAD:
B's thread pool: 50 threads
  C consuming all 50... D calls queued and timing out
  C's problem cascades into D's traffic

WITH BULKHEAD:
B's thread pool for C: 10 threads  <-- C fills these
B's thread pool for D: 10 threads  <-- D still gets served
B's thread pool for E: 10 threads  <-- E still gets served

C's GC pause cannot consume resources meant for D and E.
```

**Fallbacks — Serve a Degraded Response**

When C is unavailable, instead of waiting and timing out, B can return a fallback response: cached data, a default value, an empty list, a degraded result. The user gets *something* instead of an error.

```
WITH FALLBACK:
B calls C --> C is slow/down
B's timeout fires (200ms)
B returns fallback: last cached result from 5 minutes ago
A gets a response (degraded but not an error)
User gets slightly stale data instead of an error page
```

### The Staff Engineer Audit

Here is the mindset shift that separates senior from staff-level design:

**"I audit every synchronous call in a design. No timeout = potential cascade trigger. I ask: what happens if this call takes 30 seconds?"**

When reviewing a design, find every place where Service A calls Service B synchronously. For each one:
1. What is the timeout? (There should be one. If not, red flag.)
2. Is there a circuit breaker?
3. Is there a bulkhead (or does this call share resources with other calls)?
4. Is there a fallback?
5. What happens to A's users if B is slow for 30 seconds?

If you cannot answer these questions, the design is not ready.

---

## 4. Metastable Failures — The Self-Perpetuating Outage

### The Forest Fire Analogy

A large forest fire generates its own weather. The heat creates updrafts. The updrafts bring in fresh oxygen. The fire creates wind that spreads embers further ahead of the fire front. The fire becomes self-sustaining and self-spreading.

You remove the original match. The fire continues anyway. The conditions the fire created are now maintaining the fire.

This is a metastable failure. The system entered a state where its own defensive responses are perpetuating the problem. You cannot just fix the original cause — the fix has to break the self-sustaining loop.

### What Makes a Failure Metastable

A normal failure has this shape:
```
Cause --> Effect --> Recovery
  GC pause --> slow responses --> GC pause ends --> system recovers
```

A metastable failure has this shape:
```
Cause --> Effect --> Effect feeds back into Cause --> Effect gets worse
  GC pause --> slow responses --> retries --> more load --> more GC --> more pauses
```

The feedback loop keeps the failure alive even after the original cause resolves.

### Metastable Example 1: Retry Storm Loop

Here is the self-perpetuating retry storm:

```
METASTABLE RETRY STORM
========================

T=0: Service goes under heavy load, response time increases
         |
         v
T=1: Response times exceed client timeouts
         |
         v
T=2: Clients start retrying (they assume request failed)
         |
         v
T=3: Retries ADD to the load on the already-struggling service
         |
         v
T=4: Service load goes HIGHER, more timeouts
         |
         v
T=5: Even more retries fire
         |
         v
T=6: Service effectively down, fully overwhelmed
         |
         v
T=7: Engineer adds capacity, service starts recovering
         |
         v
T=8: Briefly handles a few requests...
         |
         v
T=9: All the queued retries fire simultaneously (thundering herd)
         |
         v
T=10: Service overwhelmed again
         |
         v
         LOOP CONTINUES
```

The retries — designed as a recovery mechanism — are themselves preventing recovery. Every time the service tries to come up, the accumulated retries knock it back down.

### Metastable Example 2: GC Spiral

```
GC SPIRAL (MEMORY PRESSURE LOOP)
===================================

[1] Service under load, memory usage climbs
              |
              v
[2] JVM (Java Virtual Machine) triggers GC (garbage collection)
    to free memory
              |
              v
[3] GC pause — service freezes for hundreds of milliseconds
              |
              v
[4] Requests during GC pause time out at clients
              |
              v
[5] Clients retry timed-out requests
              |
              v
[6] Retried requests arrive after GC pause ends
    MORE requests than before (originals + retries)
              |
              v
[7] Higher load means MORE memory allocated faster
              |
              v
[8] GC triggers again sooner, more frequently
              |
              v
[9] More frequent GC pauses --> more timeouts --> more retries
              |
              v
         BACK TO [3], WORSE EACH CYCLE
```

The GC is trying to help — it is cleaning up memory. But the retries caused by GC pauses create more load which creates more memory pressure which triggers more GC. The cure is making the disease worse.

### Why Normal Recovery Fails

When you are in a metastable state, normal operational responses do not work:

- **Adding capacity**: more instances join, they immediately get hammered by the retry backlog, they fall over too. The retry storm is not bounded by your capacity at normal load — it is amplified above normal load.

- **Restarting instances**: fresh instances start cold, get hit by the full retry wave, potentially go down again before they can warm up.

- **Waiting it out**: the system does not self-heal because the feedback loop is self-sustaining. It will not get better on its own.

- **Normal circuit breakers**: if retries are coming from many different clients, a server-side circuit breaker does not stop the clients from sending retries.

### How to Escape a Metastable State

**You have to break the feedback loop. Directly.**

```
BREAKING THE METASTABLE LOOP
==============================

OPTION 1: Shed load aggressively (load shedding)
  - Temporarily reject requests above a threshold
  - Return 503 immediately for excess requests
  - Reduces load below the overload threshold
  - Service can start processing the queue
  - Gradually raise the threshold as service recovers

  [Service] <-- 1000 RPS (too many)
  Apply load shedder: reject 80%
  [Service] <-- 200 RPS (manageable)
  Service recovers, processes backlog
  Gradually accept more traffic

OPTION 2: Disable retries temporarily
  - Push a config change to all clients: retry=OFF
  - Eliminates the retry amplification immediately
  - Service gets only "natural" traffic
  - Can recover at natural load level
  - Re-enable retries gradually after recovery

OPTION 3: Scale up rapidly (buy time)
  - Throw capacity at it to break out of the spiral
  - 10x instances can absorb the retry storm
  - System stabilizes, retries drain
  - Then scale back down
  - Expensive but fast

OPTION 4: Circuit break the retry path
  - At the load balancer or API gateway level,
    detect the retry storm signature
  - Automatically throttle clients showing
    high retry rates
  - Breaks the client-side loop from the server side
```

The key insight is that you are not fixing the original problem — you are breaking the feedback loop that is perpetuating the failure. Once the loop is broken, the system can recover at normal operating parameters.

### The Metastable Failure Signature

How do you know you are in a metastable failure versus a normal failure?

```
NORMAL FAILURE:
  Metric: request rate goes up, then down as you fix the cause
  Recovery: fix cause -> system recovers
  Retries: under control, bounded

METASTABLE FAILURE:
  Metric: request rate HIGHER than normal traffic
          (retries amplifying above normal level)
  Recovery: fix cause -> system briefly improves -> crashes again
  Retries: growing over time, not bounded
  Key signal: "We fixed the root cause but it keeps falling over"
```

If your system keeps crashing after you fix what you thought was the root cause, suspect a metastable loop. Ask: what mechanism could be creating a feedback loop between the symptom and the cause?

### The Design Principle

Build systems that can break their own feedback loops.

This means:
- **Retry budgets**: clients have a maximum retry rate, not just a maximum retry count. If you have retried 5 times in the last second, stop for 10 seconds regardless of backoff.
- **Server-side rate limiting with backpressure**: when overloaded, tell clients to slow down, do not just fail silently. A `Retry-After: 30` header tells clients to wait 30 seconds. This breaks the retry storm at the source.
- **Load shedding built in**: have a pre-designed "shed 80% of traffic" mode that can be activated instantly, not improvised during an incident.
- **Canary recovery**: when coming back from an outage, accept a small fraction of traffic first (5%), verify stability, then ramp up. Never go from 0% to 100% instantly.

**"Normal recovery procedures don't work. You have to break the loop."**

This is the mental model. When normal playbook steps are not working — more capacity, restarts, fixing the root cause — stop and ask: "Is there a feedback loop I have not broken yet?" Find the loop. Break it first. Then recover.

---

## Summary Table

```
FAILURE PATTERN QUICK REFERENCE
=================================

+--------------------+------------------+--------------------+
| Pattern            | Signature        | Key Prevention     |
+--------------------+------------------+--------------------+
| Thundering Herd    | Spike load at    | Jitter, mutex fill,|
|                    | exact moment of  | rolling restarts,  |
|                    | recovery/expiry  | exponential backoff|
+--------------------+------------------+--------------------+
| Cascading Failure  | One slow service | Timeouts, circuit  |
|                    | causes total     | breakers, bulkheads|
|                    | outage upstream  | fallbacks          |
+--------------------+------------------+--------------------+
| Metastable Failure | System won't     | Load shedding,     |
|                    | recover after    | disable retries,   |
|                    | root cause fixed | rapid scale-up,    |
|                    |                  | break the loop     |
+--------------------+------------------+--------------------+
| Graceful           | Uncontrolled     | Pre-designed tiers,|
| Degradation        | partial failures | feature flags,     |
| (prevention)       | during incidents | test degraded modes|
+--------------------+------------------+--------------------+
```

### The Three Questions

When you review any system design for failure modes, ask:

1. **Have you designed your degradation ladder?** What does 80%, 60%, 40%, 20% look like? Test each tier.

2. **Where are your thundering herd risks?** Any synchronized timers, cache TTLs, or retry intervals? Add jitter. Add mutexes for cache fill.

3. **What breaks the cascade and the metastable loop?** For every synchronous dependency: timeout, circuit breaker, bulkhead, fallback. For every potential overload spiral: load shedding, retry budget, server-side backpressure.

Systems that handle failure well are not lucky. They were designed for failure before failure happened.
# Chapter 25: Failure Models and Partial Failures — Part C2

## Real Incidents, Observability, and Scale Thresholds

---

## Section 1: Real Incident 1 — DynamoDB Brownout Causing Cascading Checkout Failure

### What Is a Brownout?

A full outage is easy to detect. Everything stops. Alerts fire. Engineers get paged.

A brownout is harder. The service is still running. Most requests succeed. But some fail, and the ones that succeed are much slower than normal. A brownout is like a highway with two lanes closed out of ten. Traffic is still moving, but everything is backed up.

This incident shows why brownouts are actually more dangerous than full outages — because they cause cascading failures in a way that a clean outage does not.

---

### The Setup

```
+--------------------------------------------------+
|              E-COMMERCE ORDER SYSTEM             |
+--------------------------------------------------+
|                                                  |
|   [User Browser]                                 |
|        |                                         |
|        v                                         |
|   [API Gateway]  <-- handles ALL requests        |
|        |                                         |
|        v                                         |
|   [Order Service]  <-- handles checkout          |
|        |                                         |
|        v                                         |
|   [DynamoDB us-east-1]  <-- stores order state   |
|        |                                         |
|   (globally replicated across regions)           |
|                                                  |
+--------------------------------------------------+
```

The order service stores every order in DynamoDB. When a user clicks "Place Order," the order service writes the order state to DynamoDB and reads it back to confirm the write. Under normal conditions, this takes about 50 milliseconds.

The order service has a timeout setting of 30 seconds. That means: if DynamoDB does not respond within 30 seconds, give up and return an error. The engineers who set this timeout thought 30 seconds was conservative — DynamoDB is usually 50ms, so 30 seconds gives enormous room. They were wrong about why that matters.

---

### The Incident — Step by Step

```
TIMELINE OF THE BROWNOUT INCIDENT
==================================

T+0:00  DynamoDB us-east-1 brownout: 20% hard-fail, 80% slow (2-5s)
        Normal latency = 50ms. Each slow request holds a thread.

T+0:02  Threads in Order Service start waiting (2-5s each)
        Thread pool begins filling.

T+0:08  Thread pool 60% full. P99 spikes to 8s.
        Error rate still low — NO ALERT fires yet.

T+0:15  Thread pool 100% full. Order Service unresponsive.
        API Gateway threads start filling (gateway serves
        ALL endpoints: search, browse, account, checkout).

T+0:22  All endpoints show 30-second load times for all users.

T+0:30  First alert fires: error rate > 1%
        40% of checkouts have already failed or timed out.
        P99 spike was visible 22 minutes ago.

T+0:32  On-call engineer sees P99 spike in historical metrics.
T+0:35  Engineer sets DynamoDB timeout: 30s -> 3s
        Threads fail fast. Thread pool drains.
T+0:37  Circuit breaker threshold lowered: 10% -> 5%, opens.
T+0:40  DynamoDB self-recovers. Circuit closes. Normal traffic.

Total duration: ~40 minutes  |  User impact: 40% checkout failure
```

---

### Incident Summary Table

| Field | Detail |
|---|---|
| System | E-commerce order service |
| Database | DynamoDB (globally replicated, us-east-1) |
| Trigger | DynamoDB brownout: 20% hard fails, 80% slow (2-5s) |
| Normal latency | 50ms |
| Brownout latency | 2,000 - 5,000ms |
| Original timeout | 30 seconds |
| Thread pool behavior | Filled completely — threads held waiting 2-5s each |
| Cascade path | DynamoDB slow → Order Service threads full → Order Service unresponsive → Gateway threads full → All endpoints slow |
| First alert | P99 latency spike at T+0:08 |
| Error rate alert | Fired at T+0:30 — 22 minutes later |
| User impact | 40% of checkouts failed during 30-minute window |
| Fix | Timeout to 3s, circuit breaker threshold to 5% |
| Recovery | DynamoDB self-recovered, circuit closed |

---

### Why Each Defense Failed

```
WHAT WAS MISSING AND WHY IT MATTERED
======================================

MISSING: Short timeout (set 30s, should be 3s)
  Each slow call held a thread for 30s instead of 3s.
  100-thread pool fills with 33 waits at 30s.
  At 3s timeouts: pool can handle 333 simultaneous waits.

MISSING: Circuit breaker (threshold was 10%, should be 5%)
  Circuit stayed closed through the early brownout.
  Calls kept flowing to degraded DynamoDB, holding threads.
  5% threshold would have opened circuit early, freeing threads.

MISSING: Bulkhead (one shared thread pool for everything)
  DynamoDB calls filled the SAME pool used for all work.
  When DynamoDB swamped the pool, logging, health checks,
  cache reads — everything stopped.
  Dedicated 50-thread pool for DynamoDB = failure stays contained.
```

---

### The Fix and Design Changes

```
BEFORE (broken)                    AFTER (fixed)
================                   ==============

DynamoDB timeout: 30s       -->    DynamoDB timeout: 3s

Circuit breaker: 10%        -->    Circuit breaker: 5%

Thread pool: shared         -->    Thread pool: dedicated 50
                                   threads for DynamoDB only

Alert: error rate > 1%      -->    Alert: P99 latency > 500ms
                                   (fires BEFORE errors start)
```

| Defense Added | Value |
|---|---|
| 3s timeout on all DynamoDB calls | Threads fail fast, pool does not fill |
| Circuit breaker on every DynamoDB call | Opens at 5% error rate, stops traffic to degraded DB |
| Dedicated thread pool for DynamoDB (50 threads) | DynamoDB problems cannot steal threads from other work |
| P99 latency alert at 500ms | Alerts fire 20+ minutes before error rate alerts |

---

### The Lesson

> **"Latency is the leading indicator. Alert on P99 before you alert on error rate."**

In this incident, P99 latency spiked to 8 seconds at T+0:08. The error rate alert did not fire until T+0:30. The engineer had a 22-minute window where the system was clearly sick, but no alert fired.

Think of it like a car engine. A high temperature gauge is the leading indicator. Waiting until smoke appears means the engine has already seized. P99 at 500ms would have fired 22 minutes earlier — turning a 30-minute checkout failure into a 5-minute one.

---

## Section 2: Real Incident 2 — Thundering Herd After Full Fleet Restart

### What Is a Thundering Herd?

Imagine a concert where 50,000 fans are all told to arrive at exactly 8pm. The venue gates cannot handle that load. Nobody gets in quickly.

If fans arrive across two hours instead, the gates are never overwhelmed.

A thundering herd in software is the same problem. Many services restart at the same instant, all need the same resource at the same instant, and that resource collapses under the simultaneous load.

---

### The Setup

```
+--------------------------------------------------+
|              AD SERVING SYSTEM                   |
+--------------------------------------------------+
|                                                  |
|   [Ad Request] --> [Ad Server Instance x50]      |
|                          |                       |
|                          v                       |
|                    [Redis Cache]                 |
|                    TTL = 5 minutes               |
|                    Stores auction results        |
|                          |                       |
|                   (cache miss)                   |
|                          v                       |
|                  [PostgreSQL DB]                 |
|                  Max connections: 100            |
|                                                  |
+--------------------------------------------------+
```

The system serves ads. For every ad request, the ad server checks Redis for a cached auction result. Cache hit = fast. Cache miss = query PostgreSQL to run the auction, store result in Redis, return ad.

Under normal operation, cache hit rate is ~95%. PostgreSQL only handles 5% of requests — the cache misses. The system runs fine with 50 instances because the database only sees 5% of load.

---

### The Incident — Step by Step

```
TIMELINE OF THE THUNDERING HERD
================================

T-0:05  Engineering team starts deploy
        - Decision: restart all 50 instances simultaneously

T+0:00  All 50 instances restart cold
        - Redis still has data but instances start with no
          local warm-up state; first requests all miss

T+0:01  100% cache miss rate
        - Every ad request falls through to PostgreSQL
        - 50 instances each open multiple DB connections

T+0:10  PostgreSQL connection pool exhausted (max 100)
        - All 100 connections used in 10 seconds
        - PostgreSQL rejects new connections ("too many connections")
        - Ad serving returns errors to all users

T+0:18  On-call engineer paged, sees 100% error rate
        - Identifies cause: all instances restarted at once

T+0:20  Engineer rolls back deploy
T+0:25  PostgreSQL connections drop, DB recovers
T+0:28  Cache warms from traffic, hit rate climbs to 95%
T+0:38  System fully recovered

Total downtime: ~8 minutes  |  Revenue loss: ~$200K
```

---

### Incident Summary Table

| Field | Detail |
|---|---|
| System | Ad serving system |
| Scale | 50 instances |
| Cache | Redis, 5-minute TTL on auction results |
| Database | PostgreSQL, max 100 connections |
| Trigger | Full fleet restart: all 50 instances simultaneously |
| Cache state after restart | Cold — 100% miss rate |
| Database impact | All 50 instances hit PostgreSQL simultaneously |
| Time to exhaust DB pool | 10 seconds |
| User impact | 100% ad serving failure for 8 minutes |
| Revenue loss | ~$200K |
| Engineer response | Rolled back deploy, DB recovered, gradual restart |
| Recovery time | ~8 minutes |

---

### Why It Failed

```
ROOT CAUSE ANALYSIS
====================

Root cause 1: No rolling restart process
-----------------------------------------
  All 50 instances restarted at the same time.
  Each instance started cold. All 50 hit the database
  simultaneously. The database is sized for normal load
  (5% of traffic), not for a full-fleet cold start
  (100% of traffic).

Root cause 2: No cache pre-warming
------------------------------------
  When an instance starts, it should warm its cache
  before accepting traffic. Loading hot data from a
  snapshot at startup means the first real requests
  have a high cache hit rate instead of 0%.

Root cause 3: TTL too short (5 minutes)
-----------------------------------------
  A 5-minute TTL means that in normal operation,
  cache entries expire every 5 minutes. During a deploy
  that takes more than 5 minutes, entries that were
  cached at the start have already expired by the time
  the new instances start. Extending to 30 minutes
  gives much more overlap between the old cache
  state and the new instances starting up.
```

---

### The Fix and Design Changes

```
BEFORE (broken)                    AFTER (fixed)
================                   ==============

Full fleet restart at once  -->    Rolling restart:
                                   5 instances at a time,
                                   2-minute gap between
                                   each batch

No warm-up period           -->    5-minute warm-up period
                                   before instance receives
                                   traffic

No cache pre-warming        -->    Load cache snapshot at
                                   startup (pre-warm from
                                   yesterday's hot data)

TTL: 5 minutes              -->    TTL: 30 minutes
```

| Defense Added | Value |
|---|---|
| Rolling restart (5 at a time, 2-min gap) | Only 10% of fleet cold at any moment; DB sees gradual load not a spike |
| 5-min warm-up before receiving traffic | Instance has warm cache before real users hit it |
| Cache pre-warm from snapshot at startup | First requests hit cache, not DB |
| TTL extended to 30 minutes | Cache entries survive a typical deploy window |

---

### The Rolling Restart Visualized

```
BROKEN: Full fleet restart
===========================
T+0:00  [Instance 1-50: ALL COLD]
         ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
         PostgreSQL: 100 connections used in 10s
         PostgreSQL: REJECTS connections
         Ad serving: 100% failure

FIXED: Rolling restart
=======================
T+0:00  [Instances 1-5: cold]   [Instances 6-50: warm, serving]
         ↓↓↓↓↓              (small DB spike, handled)
T+2:00  [Instances 1-5: warm]  [Instances 6-10: cold]  [11-50: warm]
         ↓↓↓↓↓              (small DB spike, handled)
T+4:00  [Instances 1-10: warm] [Instances 11-15: cold] [16-50: warm]
         ...and so on

At any moment: only 10% of fleet is cold
DB sees: 10% of normal traffic spike, not 100%
User impact: zero
```

---

### The Lesson

> **"A restart of all instances is an outage. Always roll."**

This is one of the most common causes of self-inflicted outages. The team was trying to do something routine — deploy a new version. The deploy itself was fine. The restart strategy caused a catastrophic thundering herd.

Every deploy checklist should include: rolling restart only. Never restart more than 10-20% of your fleet at once. And every instance should have a warm-up period before it receives live traffic.

---

## Section 3: Observability for Partial Failures — Seeing What's Invisible

### The Package Tracking Analogy

You order something online. Three days later, it has not arrived. You call customer service. They say: "It shipped. That's all we know."

That is distributed systems without observability. You know a request went in. You know it did not come out. You do not know where it got stuck.

Now imagine you have a package tracking system. You can see: picked up at warehouse, arrived at regional facility, sat at depot 3 for 2 hours, loaded on delivery truck, out for delivery. You know exactly where the delay is. You can fix it.

Distributed tracing is the package tracking system for your requests. Each request carries a trace ID through every service it touches. You can see exactly where time was spent, where errors occurred, and which service in the chain is responsible for a slowdown.

Without tracing, you know a request took 8 seconds. You do not know if it was 8 seconds in Service A, or 0.1 seconds in each of 80 calls to Service B.

---

### Why Standard Metrics Miss Partial Failures

Here is the problem with averages and overall error rates:

```
SCENARIO: One endpoint is broken
==================================

System has 5 endpoints:
  /search     - 200ms, 0% errors, 500 req/s
  /browse     - 150ms, 0% errors, 400 req/s
  /cart       - 100ms, 0% errors, 200 req/s
  /account    - 80ms,  0% errors, 100 req/s
  /checkout   - 8000ms, 30% errors, 50 req/s

Total requests: 1,250 req/s

Average latency = (200*500 + 150*400 + 100*200 + 80*100 + 8000*50) / 1250
               = (100,000 + 60,000 + 20,000 + 8,000 + 400,000) / 1250
               = 588,000 / 1250
               = 470ms

Overall error rate = (50 * 0.30) / 1250 = 15 / 1250 = 1.2%

What your dashboard shows: Average latency 470ms, error rate 1.2%
What is actually happening: Checkout is completely broken
What users experience: Cannot buy anything
```

The aggregate numbers look "fine." Checkout is on fire. This is how partial failures hide in plain sight.

---

### The Four Golden Signals

The four golden signals are the most important metrics for understanding system health. Each catches different problems. Each also has blind spots.

```
THE FOUR GOLDEN SIGNALS
========================

1. LATENCY
   What it measures: How long requests take
   What it catches:  Slow nodes, slow dependencies,
                     resource contention
   Blind spot:       P50 (median) masks outliers.
                     Use P99 and P999.

   Example: P50 = 50ms (looks great)
            P99 = 5,000ms (1 in 100 users waits 5 seconds)
            At 1M req/day: 10,000 users per day see 5s waits

2. TRAFFIC
   What it measures: How many requests are being made
   What it catches:  Overload, unexpected drops in requests,
                     bot attacks
   Blind spot:       Does not tell you if requests succeed
                     or what users experience

   Example: Traffic drops 50% -- is it a load shedder
            dropping traffic, or did users give up and leave?

3. ERRORS
   What it measures: How many requests fail
   What it catches:  Hard failures -- services returning 500,
                     timeouts that you catch, explicit errors
   Blind spot:       Gray failures -- service returns 200
                     but with wrong data, or request succeeds
                     but takes 30 seconds

   Example: Error rate = 0.1% (looks fine)
            But P99 = 8 seconds (catastrophe)
            Latency degradation before errors -- always

4. SATURATION
   What it measures: How full your resources are
                     (CPU, memory, thread pools, disk)
   What it catches:  Resource exhaustion before it becomes
                     an outage -- leading indicator
   Blind spot:       Does not tell you which requests are
                     affected or why

   Example: Thread pool at 90% capacity
            Next spike will exhaust it and cause a cascade
            Alert now, before it hits 100%
```

---

### Key Metrics for Partial Failures

Standard metrics catch full outages. These metrics catch partial failures — the hard ones.

| Metric | What It Reveals | Why Aggregate Metrics Miss It |
|---|---|---|
| Per-endpoint latency (not aggregate) | One slow endpoint hides in average latency | /checkout at 8s averages down to 470ms with healthy endpoints |
| Thread pool utilization | Approaching the limit is a leading indicator of cascade | CPU and error rate look fine while threads fill |
| Circuit breaker state changes | Many open/close cycles per hour = instability | Error rate might be low if circuit is working, but instability is growing |
| Retry rate | High retry rate means your system is hiding failures | Success rate looks high; retries are masking failures |
| Downstream latency | Your service may be fast; the problem is downstream | Your service P99 looks fine; the database call inside is 5s |

---

### Percentile Latency Explained

Most engineers look at average latency. Average latency is almost useless for user experience.

```
WHY AVERAGE LATENCY MISLEADS
==============================

1000 requests in one minute:
  990 requests: 50ms each
  10 requests:  5,000ms each (these users are having a bad time)

Average latency = (990*50 + 10*5000) / 1000
               = (49,500 + 50,000) / 1000
               = 99,500 / 1000
               = 99.5ms

Average says: 99.5ms (pretty good!)
Reality: 10 users per minute are waiting 5 seconds

WHAT PERCENTILES TELL YOU
==========================

P50 = 50ms    -- half of users wait this long or less
P90 = 50ms    -- 90% of users wait this long or less
P99 = 5,000ms -- 99% of users wait this long or less
               -- 1% of users wait MORE than 5 seconds
P999 = 5,000ms -- 99.9% wait this long or less

P99 tells you: 1 in 100 requests hits 5 seconds.

At 1,000,000 requests per day:
  10,000 users per day experience 5-second waits.
  That is 10,000 frustrated users. Every day.
```

The right way to think about percentiles: P99 is your worst-case user. P999 is your worst-case user on a bad day. Both matter. At high request volumes, even P999 represents real people.

---

### Dashboard Design for Partial Failures

```
WHAT TO PUT ON YOUR DASHBOARD
================================

TOP ROW (primary health indicators):
+------------------+------------------+------------------+
| Per-endpoint P99 | Error rate by    | Thread pool      |
| latency          | endpoint         | utilization      |
| (not aggregate)  | (not aggregate)  | by service       |
+------------------+------------------+------------------+

SECOND ROW (leading indicators of cascade):
+------------------+------------------+------------------+
| Retry rate       | Circuit breaker  | Downstream       |
| (should be ~0%)  | state changes    | service latency  |
| High = hiding    | (open/close/hr)  | (not just yours) |
| failures         |                  |                  |
+------------------+------------------+------------------+

THIRD ROW (resource saturation):
+------------------+------------------+------------------+
| CPU utilization  | Memory usage     | DB connection    |
| by service       | by service       | pool utilization |
+------------------+------------------+------------------+
```

**The most important dashboard insight:**

Show retry rate prominently. A high retry rate is the canary in the coal mine. It means your system is working overtime to hide failures from users. Success rate looks fine. Error rate looks fine. But the system is making 3 attempts for every successful request. That means throughput is 3x higher than you think. The retry load is often what tips a degraded system into a full outage.

---

### Synthetic Monitoring: Testing What Users Actually Do

A health check endpoint (`GET /health`) returning HTTP 200 means the service process is running. It does not mean checkout works.

```
HEALTH CHECK vs SYNTHETIC MONITORING
======================================

Health check:
  GET /health -> 200 OK
  What it tests: Is the process alive?
  What it misses: Is the database connected?
                  Can users check out?
                  Are payments processing?
                  Is the email service working?

Synthetic monitor (what you should also run):
  Every 60 seconds, run this test:
  1. Create a test user session
  2. Add a test item to cart
  3. Start checkout flow
  4. Complete test payment (test card number)
  5. Verify order confirmation received
  6. Verify confirmation email sent
  7. Clean up test data

  If any step fails or takes > 3 seconds: fire alert

What synthetic monitoring catches:
  - Checkout broken while /health returns 200
  - Payment processor down while everything else works
  - Email service silently failing
  - Database write succeeds but read returns stale data
```

Run synthetic monitors from multiple regions. Your service might be healthy in us-east-1 but unreachable from Europe due to a routing issue. The synthetic monitor in Europe will catch what the health check in us-east-1 misses.

---

## Section 4: Scale Thresholds — How Failure Patterns Change With Scale

### The Key Insight

At different scales, you face completely different failure modes. The defenses that work at V1 are not enough at V3. The defenses at V3 are not enough at V5.

Each time you add more services, more instances, and more dependencies, entirely new failure modes appear that you have never encountered before. This is not a failure of engineering. It is a property of distributed systems. Scale changes physics.

---

### Scale Levels and Their Failure Modes

```
EVOLUTION OF FAILURE MODES BY SCALE
======================================

V1: Single Service
-------------------
         [Your Service]
              |
         [Database]

Failure mode: Process crash = total outage
Detection: Easy. One thing to watch.
Recovery: Restart the process.
Complexity: Low.

V2: 2-3 Services
-----------------
         [Service A]
          /       \
    [Service B] [Service C]

Failure mode: Cascades. Service B fails, holds threads in A,
              A becomes slow, users see degradation.
Detection: Need per-service metrics.
Recovery: Timeouts and circuit breakers on every call.
Complexity: Medium.

V3: 10+ Services
-----------------
     [A] --> [B] --> [C] --> [D]
      \               /
       [E] --> [F] --

Failure mode: Blast radius analysis needed.
              Which service failing affects which users?
              Bulkheads required to contain failures.
              Need distributed tracing to find root cause.
Detection: Need distributed tracing, per-service dashboards.
Recovery: Bulkheads, circuit breakers, fallbacks.
Complexity: High.

V4: 50+ Services
-----------------
     Too complex to draw by hand.
     Dozens of inter-service dependencies.

Failure mode: Manual configuration of timeouts and circuit
              breakers is error-prone and incomplete.
              Need service mesh (Istio, Linkerd) to enforce
              policies automatically.
              Game days needed to find failure modes before
              they find you in production.
Detection: Distributed tracing is essential, not optional.
Recovery: Service mesh handles circuit breaking automatically.
Complexity: Very high.

V5: 100+ Services
------------------
     Microservice ecosystem. Many teams. Many languages.
     Thousands of inter-service calls per second.

Failure mode: You cannot reason about failure modes in your head.
              Must inject failures in production to find them.
              Chaos engineering is standard practice.
              Unknown failure modes exist in production right now.
Detection: Distributed tracing, anomaly detection, ML-based
           alerting.
Recovery: Chaos engineering + game days to build muscle memory.
Complexity: Extreme. Requires dedicated reliability teams.
```

---

### Scale Levels Summary Table

| Scale Level | Services | Primary Failure Mode | Key Defense Needed |
|---|---|---|---|
| V1 | 1 | Process crash = total outage | Restart mechanism, health checks |
| V2 | 2-3 | Cascades between services | Timeouts + circuit breakers |
| V3 | 10+ | Blast radius, thread starvation | Bulkheads + distributed tracing |
| V4 | 50+ | Manual config errors, unknown failure paths | Service mesh (Istio/Linkerd) + game days |
| V5 | 100+ | Unknown unknowns, emergent failures | Chaos engineering as normal practice |

---

### When to Add Each Defense

A common mistake is adding complexity before you need it. Another common mistake is waiting until an outage forces you to add it. Here is the right timing:

```
DEFENSE INTRODUCTION TIMELINE
================================

FROM DAY 1 (V1+):
  Timeouts on every external call
    - Without them, one slow dependency hangs your service forever
    - Cost to add: Low. A config value.

  Health checks
    - Load balancers need to know if your process is alive
    - Cost to add: One endpoint.

  Structured logging
    - You will need to debug production. Grep-able logs save hours.

AT V2 (2-3 services):
  Circuit breakers on every inter-service call
    - Now you can cascade. Circuit breakers prevent downstream
      failures from taking down your service.
    - Cost to add: One library, configure per dependency.

  Per-service metrics dashboards
    - You need to know WHICH service has the problem.

AT V3 (10+ services):
  Bulkheads (separate thread pools per dependency)
    - One slow dependency can now starve others.
    - Bulkheads contain the blast radius.

  Distributed tracing
    - A request touches 10 services. You cannot find
      the slow one without tracing.

  Blast radius analysis
    - Before every deploy: if this service fails, what breaks?

AT V4 (50+ services):
  Service mesh (Istio, Linkerd, Envoy)
    - Manual timeout/circuit-breaker config across 50 services
      will have gaps. Service mesh enforces policies automatically.

  Game days
    - Practice recovery before the real incident finds you at 2am.

AT V5 (100+ services):
  Chaos engineering in production
    - At this scale there are failure modes only real traffic exposes.
    - Staging cannot replicate production complexity.
    - Cost to not add: unknown failures waiting to surface.
```

---

### Defense Introduction Summary Table

| Defense | Add At | Why That Timing |
|---|---|---|
| Timeouts | Day 1 (V1) | Applies to any external call; cost is near zero |
| Health checks | Day 1 (V1) | Required for basic load balancing and restarts |
| Circuit breakers | V2 | First time cascades are possible |
| Per-service metrics | V2 | Need to know which service has the problem |
| Bulkheads | V3 | First time one dependency can starve others |
| Distributed tracing | V3 | First time you cannot manually trace a request |
| Blast radius analysis | V3 | Complex enough that failures have non-obvious scope |
| Service mesh | V4 | Too many services to configure manually without gaps |
| Game days | V4 | Need to rehearse recovery before a real incident |
| Chaos engineering | V5 | Unknown failure modes that only appear at production scale |

---

### "Each Scale Introduces New Failure Modes You Have Not Seen Before"

This is the most important takeaway from the scale discussion. You cannot design for V5 failure modes when you are at V2. The complexity does not exist yet. The interconnections that create emergent failures have not been built yet.

The practical implication: do not over-engineer for scale you do not have. But do watch for the transition points. When you go from 3 services to 10, add bulkheads and distributed tracing. When you go from 10 to 50, consider a service mesh. When you hit 100, invest in chaos engineering.

The teams that get into trouble are the ones who grow from V2 to V5 quickly — through a major product success or an acquisition — without adding the defenses that each scale transition requires.

```
THE TRANSITION DANGER ZONE
============================

V2 with V2 defenses --> grow --> V3 with V2 defenses
                                      ^
                                      |
                               THIS IS DANGEROUS.
                               You have V3 failure modes
                               (bulkhead, blast radius) but
                               only V2 defenses (timeouts,
                               circuit breakers).

                               This is where the DynamoDB
                               brownout incident lives.
                               This is where the thundering
                               herd incident lives.

The defense checklist should be reviewed every time
you add a significant number of new services or
significantly increase traffic.
```

---

## Part C2 Summary

| Topic | Key Takeaway |
|---|---|
| DynamoDB brownout incident | Latency is the leading indicator. Alert on P99 before error rate. Short timeouts + circuit breakers + bulkheads prevent cascade. |
| Thundering herd incident | A full fleet restart is an outage. Always roll. Pre-warm caches. Extend TTLs. |
| Observability for partial failures | Aggregate metrics hide partial failures. Per-endpoint P99 latency, retry rate, and thread pool utilization are the metrics that catch what others miss. |
| Synthetic monitoring | Health checks test if the process is alive. Synthetic monitors test if users can actually complete their journey. Both are required. |
| Scale thresholds | Each scale level introduces new failure modes. Add defenses at the right transition: timeouts at V1, circuit breakers at V2, bulkheads at V3, service mesh at V4, chaos engineering at V5. |

---

*Chapter 25, Part C2 — End*
# Chapter 25: Failure Models and Partial Failures
## Part D1 — Anti-Patterns, Failure Scenario Design, and Chaos Engineering

---

## Section 1: Anti-Patterns — The Mistakes That Cause 3 AM Pages

An anti-pattern is a solution that feels right but makes things worse. Every item in this list has
caused real production outages. Learn them so you don't repeat them.

---

### Anti-Pattern 1: Retry Blindly Without Backoff

**MISTAKE**

Your service calls a downstream API. It fails. You retry immediately. Three times. Each retry has a
10-second timeout. You think you are being a good engineer because you handled the error.

```python
# BAD: Naive retry with no delay
def call_payment_service(order):
    for attempt in range(3):
        try:
            return payment_api.charge(order)
        except Exception:
            continue  # try again RIGHT NOW
    raise PaymentFailed("All retries exhausted")
```

**PROBLEM**

Single user: 3 retries × 10s timeout = 30 seconds of waiting, then an error page.

At scale — retry storm:

```
Payment service starts struggling at T=0.
Every user's code retries immediately.

T=0:    1,000 requests hit payment service  (it starts slowing)
T=1ms:  3,000 requests hit payment service  (everyone's first retry)
T=2ms:  9,000 requests hit payment service  (second retries stacking)

Payment service: completely crushed.
You turned a small hiccup into a full outage.
```

Think of a restaurant kitchen getting backed up. Every customer immediately reorders. Now the
waiter fields 300 orders instead of 100. The kitchen gets MORE backed up, not less.

**FIX**

Exponential backoff with jitter — wait longer between retries, add randomness so all clients
don't retry at the exact same millisecond.

```python
# GOOD: Exponential backoff with jitter
import random, time

def call_payment_service(order):
    base_delay = 0.1   # 100ms
    max_delay  = 30.0  # 30 seconds

    for attempt in range(5):
        try:
            return payment_api.charge(order)
        except TransientError:
            if attempt == 4:
                raise
            delay = base_delay * (2 ** attempt)          # 100ms, 200ms, 400ms...
            delay = delay * (0.5 + random.random())      # jitter
            delay = min(delay, max_delay)
            time.sleep(delay)
```

```
Client A retries at: T=100ms, T=300ms, T=700ms
Client B retries at: T=110ms, T=325ms, T=680ms  (jitter spreads them out)

Result: no synchronized storm. Retries distributed across a time window.
```

Also: respect `Retry-After` headers on 429/503 responses, and pair every retry loop with a
circuit breaker that stops retries when the service is clearly down (not just slow).

---

### Anti-Pattern 2: Timeout Set to 60 Seconds "To Be Safe"

**MISTAKE**

A developer worries about slow DB queries and sets the timeout to 60 seconds "just in case."
Feels cautious. Is actually dangerous.

**PROBLEM**

Threads are the bottleneck. Each slow request holds a thread for the full timeout duration.

```
Web server has a thread pool of 100 threads.
A slow DB query holds each request for 60 seconds.

T=0:    10 slow requests arrive. 10 threads tied up.
T=30s:  50 slow requests have arrived. 50 threads tied up.
T=60s:  100 threads all waiting for DB responses. Pool exhausted.

New requests arrive: NO THREADS AVAILABLE.
Response: immediate error, or queued until timeout.

You now have TWO outages:
  - DB is slow (original problem)
  - Web server completely unresponsive (problem you created)
```

Think of parking spaces. If every car parks for 60 minutes, the lot fills fast. Shorter time
limits keep spots turning over for everyone.

**FIX**

Set timeouts based on real data, not instinct.

```
Formula:  timeout = P99 latency × 3

P99 latency = slowest 1% of requests under normal load
× 3         = buffer for occasional variance

Example:
  DB query P99 = 200ms
  Timeout      = 600ms

  If a query exceeds 600ms, something is wrong.
  Fail fast. Free the thread. Don't wait 60 seconds.
```

Alert when P99 approaches 30% of your timeout:

```
Timeout = 600ms
Warning threshold = 180ms P99

P99 > 180ms → Slack alert. Trend is bad, act before timeouts fire.
P99 > 600ms → Timeouts firing → page on-call.
```

---

### Anti-Pattern 3: Shared Thread Pool for All Dependencies

**MISTAKE**

One thread pool handles all outgoing calls: database, cache, payment API, email. Simple to set up.

**PROBLEM**

One slow dependency starves everything else.

```
SHARED POOL — 200 threads total

Normal:
  [DB: ~20]  [Cache: ~10]  [Payment: ~5]  [Email: ~2]  [Free: 163]

DB starts slowing (maybe a long migration is running):
  [DB: 188 threads waiting]  [Cache: 6]  [Payment: 4]  [Email: 2]  [Free: 0]

DB still slow:
  [DB: 200 threads — ALL THREADS waiting for DB]
  Cache calls:    NO THREADS AVAILABLE
  Payment calls:  NO THREADS AVAILABLE
  API responses:  NO THREADS AVAILABLE

TOTAL FAILURE from ONE slow dependency.
```

This is the "noisy neighbor" problem inside your own process. The slow DB took all the
resources and starved cache and payment — even though those services were perfectly healthy.

**FIX**

Bulkhead pattern. Separate thread pools per dependency. A slow dependency can only exhaust its
own pool, not yours.

```
BULKHEAD — Separate pools

  +--------------+  +--------------+  +---------------+
  |  DB Pool     |  |  Cache Pool  |  |  Payment Pool |
  |  50 threads  |  |  30 threads  |  |  20 threads   |
  +--------------+  +--------------+  +---------------+

DB slows down → DB pool fills to 50 → DB calls fail fast (their pool is full)
Cache pool:    still 30 threads → cache calls work fine
Payment pool:  still 20 threads → checkouts work fine

PARTIAL FAILURE. Other systems unaffected.
```

```python
from concurrent.futures import ThreadPoolExecutor

# Separate pools created at startup
db_pool      = ThreadPoolExecutor(max_workers=50, thread_name_prefix="db")
cache_pool   = ThreadPoolExecutor(max_workers=30, thread_name_prefix="cache")
payment_pool = ThreadPoolExecutor(max_workers=20, thread_name_prefix="payment")

def get_user(user_id):
    future = db_pool.submit(db_client.query, f"SELECT * FROM users WHERE id={user_id}")
    return future.result(timeout=0.6)
```

Name comes from ship bulkheads — watertight compartments that stop one breach from sinking the
whole ship. One compartment floods; the others stay dry.

---

### Anti-Pattern 4: "Health Check Passes = Service Is Healthy"

**MISTAKE**

Load balancer checks `/health`. It returns 200. You assume the service is healthy.

```python
# BAD: Shallow health check
@app.route("/health")
def health():
    return {"status": "ok"}, 200  # always returns 200
```

**PROBLEM**

A 200 from `/health` tells you the HTTP server is running. Nothing more.

```
Scenario: DB connection string is wrong after a config deployment.

/health returns:  200 OK  (load balancer is happy, routes traffic here)
Reality:
  GET /product/123   → works (result is cached in Redis)
  POST /order        → SILENTLY FAILS (needs DB write, DB unreachable)
  PUT  /cart         → SILENTLY FAILS
  DELETE /item       → SILENTLY FAILS

Reads work. Writes fail. Health check says everything is fine.
Engineers don't notice for 2 hours. Orders are lost.
```

**FIX**

Deep readiness check. Exercise the actual paths the service needs.

```python
@app.route("/health/ready")
def readiness():
    checks = {}

    # Check DB write path
    try:
        db_client.execute("INSERT INTO health_pings (ts) VALUES (NOW())")
        db_client.execute("DELETE FROM health_pings WHERE ts < NOW() - INTERVAL 1 MINUTE")
        checks["db_write"] = {"ok": True}
    except Exception as e:
        checks["db_write"] = {"ok": False, "error": str(e)}

    # Check cache connectivity
    try:
        redis_client.set("health_ping", "1", ex=10)
        checks["cache"] = {"ok": True}
    except Exception as e:
        checks["cache"] = {"ok": False, "error": str(e)}

    all_ok = all(c["ok"] for c in checks.values())
    return checks, (200 if all_ok else 503)
```

Two endpoints: `/health/live` (is the process alive? — shallow, for restart decisions) and
`/health/ready` (can it handle traffic? — deep, for load balancer routing). A pod only gets
traffic when `/health/ready` returns 200. DB write failure pulls the pod from rotation immediately.

---

### Anti-Pattern 5: "Our Dependency Is Reliable, No Fallback Needed"

**MISTAKE**

Skip fallback design because the dependency has great uptime. "AWS S3 is basically never down."
"Stripe has 99.99% uptime." No fallback built. Total dependency on the external service.

**PROBLEM**

Every dependency fails eventually.

```
AWS S3 us-east-1 outage, February 28, 2017:
  Duration: ~4 hours
  Cause: human error (one command removed too many servers during debugging)
  Impact: most of the US internet was degraded or down
  Sites affected: Slack, Quora, Trello, GitHub, many more

AWS DynamoDB brownouts: periodic 5-10% elevated error rates during peak traffic.
  Not "down" but 5-10% of users having bad experiences is still a real problem.
```

"Reliable" does not mean "never fails." It means "usually works." Plan for the times it doesn't.

**FIX**

Before writing any code that calls an external service, answer: "What do we show users if this
call fails?"

```
Dependency         | Fallback
-------------------|-----------------------------------------
Product images     | Placeholder image from local CDN
Recommendations    | Popular products from precomputed list
Search service     | Category browse instead of search
Notification svc   | Queue message, deliver when recovered
Auth service       | Allow access with cached session token
Analytics events   | Buffer locally, flush when recovered
```

```python
def get_recommendations(user_id):
    try:
        return recommendation_service.get(user_id, timeout=0.2)
    except (Timeout, ServiceUnavailable):
        return popular_items_cache.get_top_20()  # never fails, always fast
    except Exception:
        return []  # feature disappears gracefully — no error thrown
```

---

### Anti-Pattern 6: Restart All Instances Simultaneously to Fix the Problem

**MISTAKE**

Service is misbehaving. Memory leak, stuck threads, bad state. On-call engineer restarts all 20
instances at once to clear the problem. Logical. Catastrophic.

**PROBLEM**

Simultaneous restart creates a cold cache stampede.

```
Before restart:
  20 instances running. Each has 10,000 items in warm cache.
  DB load: normal (most reads served from cache).

All 20 instances restart at T=0:

T=0:    All 20 caches wiped. Everything cold.
T=1s:   First requests arrive. Every request = cache miss.
        Every request falls through to the database.
        DB load: 20x normal (200,000 items being re-fetched simultaneously).

T=2s:   DB overwhelmed. Response times spike from 50ms to 5,000ms.
        Instances start timing out on DB calls.
        Errors cascade.

T=3s:   DB falls over. All 20 instances now failing.

Original problem: 20% degraded.
After restart: 100% down. You made it worse.
```

This is a "thundering herd" — all instances woke up hungry at the same time and rushed the same
resource. The stampede killed the database.

**FIX**

Rolling restart. One instance at a time. Warm-up period between each.

```
T=0:    Restart instance 1/20. 19 still warm and serving traffic.
T=30s:  Instance 1 warmed up. Restart instance 2/20.
T=60s:  Instance 2 warmed up. Restart instance 3/20. ... continue ...
T=10m:  All 20 restarted. DB load normal throughout.
        Never more than 1 cold instance at a time.
```

```bash
# BAD: restarts all pods at once
kubectl rollout restart deployment/myapp

# GOOD: rolling update config in deployment spec
# maxUnavailable: 1   (at most 1 pod down at a time)
# maxSurge: 1         (spin up 1 new before killing 1 old)
```

Same rule applies to deployments and config changes. Always roll changes gradually.

---

## Section 2: Failure Scenario Design Walkthrough

### How to Approach This in an Interview

When an interviewer says "design the failure model for X," they want structured thinking — not
just "add circuit breakers." Use this eight-step framework.

**Problem: Design the failure model for an e-commerce checkout flow.**

---

#### Step 1: Map Your Dependencies

Before you design failures, identify what can fail.

```
User Browser
     |
     v
+----------------+
|  Checkout API  |
+----------------+
     |
     |-----> [Inventory Service]     "do we have this item in stock?"
     |-----> [Payment Service]       "charge the credit card"
     |-----> [Order Database]        "save the order record"
     |-----> [Notification Service]  "send confirmation email/SMS"
     |-----> [Recommendations]       "show related items after purchase"
```

Five dependencies. Each can fail independently.

---

#### Step 2: For Each Dependency — Three Failure Modes

For every box, ask: slow? down? wrong data?

```
Inventory Service:
  Slow?       → Short timeout (500ms). Show "checking availability..."
  Down?       → Allow purchase optimistically, verify async. If out of stock, refund.
  Wrong data? → Cannot catch at checkout. Catch in fulfillment pipeline.

Payment Service:
  Slow?       → Payment gateway often takes 1-3s. Timeout at 3s. Show spinner.
  Down?       → Hard failure. Store order as "pending". Show clear error. Use idempotency keys.
  Wrong data? → "Declined" when card is valid, or "approved" without charging.
                Reconciliation job runs nightly to catch mismatches.

Order Database:
  Slow?       → Write is blocking. Timeout at 1s.
  Down?       → Hard failure. Cannot take money without a record.
  Wrong data? → Duplicate order IDs. Use unique constraints + idempotency.

Notification Service:
  Slow?       → User does not need to wait for email. Make this async.
  Down?       → Queue the notification. Send when service recovers.
  Duplicate?  → User gets two emails. Annoying but not critical.

Recommendations:
  Slow?       → Don't show personalized recs. Use cached popular list.
  Down?       → Same fallback. Never critical path.
  Wrong data? → Filter on checkout side. Never crash because recs returned null.
```

---

#### Step 3: Set Timeouts for Each Dependency

```
Dependency          P99 Latency    Timeout (P99 × 3)    Notes
--------------------+--------------+-------------------+------------------------------
Inventory Service   150ms          500ms                Cached data. Fast.
Payment Service     1,000ms        3,000ms              External network. Slower.
Order Database      300ms          1,000ms              Local network. Medium.
Notification Svc    200ms          N/A                  Async — no timeout needed.
Recommendations     60ms           200ms                Very short. Non-critical.
```

---

#### Step 4: Add Circuit Breakers on Each External Call

```
Dependency         | Error Threshold | Window   | Open Duration | Half-Open Probe
-------------------+-----------------+----------+---------------+----------------
Inventory Service  | 50% errors      | 10 calls | 30 seconds    | 1 call
Payment Service    | 20% errors      | 5 calls  | 60 seconds    | 1 call
Order Database     | 30% errors      | 10 calls | 30 seconds    | 1 call
Recommendations    | 80% errors      | 20 calls | 15 seconds    | 1 call
```

Payment gets a tight threshold (20%) — payment errors are high signal. Recommendations get a
loose threshold (80%) — non-critical, keep trying longer.

---

#### Step 5: Define Fallbacks Per Dependency

```
Dependency         | Primary                  | Fallback
-------------------+--------------------------+----------------------------------
Inventory Service  | Check live stock         | Assume in-stock, verify async
Payment Service    | Charge in real-time      | No fallback — must fail clearly
Order Database     | Write to primary DB      | No fallback — must fail clearly
Notification Svc   | Send inline              | Queue to SQS, deliver async
Recommendations    | Personalized recs        | Cached top-20 popular items
```

---

#### Step 6: Define Degradation Tiers

This is what distinguishes a senior answer. Not just "circuit breaker open → error" — think in
tiers of graceful degradation.

```
Tier 1 — Full Checkout (all healthy)
  Real-time inventory + payment + instant confirmation + personalized recs.

Tier 2 — Recommendations degraded
  Recs service down. Popular items shown instead.
  User experience: 99% normal.

Tier 3 — Inventory check degraded
  Inventory service down. Optimistic purchase, async verification.
  User experience: 98% normal. Tiny risk of out-of-stock handled by fulfillment.

Tier 4 — Notifications degraded
  Email/SMS delayed (from queue, not inline). Checkout still works.
  User experience: confirmation delayed by minutes.

Tier 5 — Payment service down
  Cannot charge card. Show clear error. Preserve cart. "Try again in a few minutes."
  Revenue impact. Page on-call immediately.

Tier 6 — Order database down
  Cannot save record. Show clear error. Preserve cart.
  Revenue impact. Page on-call immediately.
```

Tiers 1-4 = graceful degradation. Tiers 5-6 = hard failures that must be fixed now.

---

#### Step 7: Define Load Shedding Order

When checkout itself is overloaded, shed in this priority order:

```
1. Shed recommendations first      (non-critical, compute-expensive)
2. Shed real-time inventory checks (use optimistic/cached instead)
3. Shed guest user sessions        (registered users = higher intent)
4. Shed new cart sessions          (protect users already at checkout)
5. Last resort: 503 with retry guidance
```

Always protect users closest to payment the longest.

---

#### Step 8: Define Monitoring

```
Metric                          | Type   | Threshold
--------------------------------+--------+----------------------------------
checkout_success_rate           | Page   | < 95% for 2 minutes
payment_error_rate              | Page   | > 2% for 1 minute
inventory_circuit_breaker_open  | Alert  | any opening event
p99_checkout_latency            | Alert  | > 3,000ms
order_db_write_latency          | Page   | > 1,000ms (near timeout)
notification_queue_depth        | Alert  | > 10,000 unprocessed messages
payment_latency_p99             | Alert  | > 900ms (approaching 3s timeout)
```

Page = wake someone up now. Revenue at risk.
Alert = Slack message. Investigate within 30 minutes.

---

#### Full Architecture Diagram

```
                      User Browser
                           |
                           v
                  +------------------+
                  |   Load Balancer  |
                  +------------------+
                           |
             +-------------+--------------+
             |             |              |
             v             v              v
   +--------------+  +-----------+  +-----------+
   | Checkout API |  | Checkout  |  | Checkout  |
   |  Instance 1  |  | Instance2 |  | Instance3 |
   +--------------+  +-----------+  +-----------+
        |
        | Each call below:
        | [CB] = circuit breaker
        | [TO] = timeout
        | [FB] = fallback defined
        |
        +--[CB][TO:500ms][FB:optimistic]--> Inventory Service
        |
        +--[CB][TO:3s][FB:none/fail]------> Payment Service (Stripe)
        |
        +--[CB][TO:1s][FB:none/fail]------> Order Database
        |
        +--[async/SQS buffer]-------------> Notification Service
        |
        +--[CB][TO:200ms][FB:popular]-----> Recommendations Service
```
[CB]=circuit breaker  [TO]=timeout  [FB]=fallback  async=not in critical path

---

## Section 3: Chaos Engineering — Controlled Failure Injection

### The Fire Drill Analogy

Schools run fire drills before there is an actual fire. When the real fire comes, you don't want
people figuring out the route while panicking — you want them to already know: which door, which
stairwell, where to meet outside. Chaos engineering is a fire drill for software systems.

You intentionally inject failures in a controlled way. You find the gaps. You fix them. When a
real failure hits at 3 AM, your system already knows what to do.

The goal is not to break things. The goal is to find weaknesses before your users do.

Formally: state a hypothesis ("killing one payment instance will not affect success rate because
the other two absorb load"), then test it by actually killing the instance. In production.

Two outcomes, both valuable:
1. Hypothesis correct. Evidence your resilience works.
2. Hypothesis wrong. You find out in a controlled test, not at 3 AM.

---

### Netflix Chaos Monkey

Netflix pioneered this in 2011. Chaos Monkey randomly terminated EC2 instances in production during
business hours. Before it existed, engineers said "our system is resilient." Chaos Monkey tested
whether that was actually true, not just theoretically true. Engineers were forced to build systems
that tolerated instance death — because if they didn't, their service would break repeatedly.

Netflix later expanded into the "Simian Army": Chaos Monkey (kills instances), Latency Monkey
(injects latency), Chaos Gorilla (kills an entire AZ).

Key insight: regular controlled failures made failure a normal operating condition, not an
exceptional edge case engineers scrambled to handle for the first time.

---

### Types of Chaos Experiments

**Kill a Process / Pod**
```
Test:    Does the service recover from a random instance dying?
Method:  kubectl delete pod <random-pod-name>
Observe: Does Kubernetes restart the pod? Do other pods absorb traffic?
         Any user-visible error? How long until fully recovered?
Target:  < 5 second impact. Users do not notice.
```

**Add Network Latency**
```
Test:    Does the circuit breaker trip when a dependency slows?
Method:  Inject 500ms latency to calls to inventory service (Toxiproxy or tc)
Target:  Circuit breaker opens. Fallback serves users. No full outage.
```

**Drop Packets**
```
Test:    Does retry logic handle intermittent packet loss?
Method:  Drop 10% of packets to a dependency using iptables
Target:  P99 increases slightly. No user-visible errors. No retry storm.
```

**Max CPU**
```
Test:    Does the service degrade gracefully under compute pressure?
Method:  Run a CPU-intensive process alongside the application
Target:  Latency increases, health check detects it, new instances spin up.
```

**Fill the Disk**
```
Test:    What happens when the log disk fills up?
Method:  Write a large file to consume disk space
Target:  Alert fires. Log rotation frees space. No crash.
```

**Kill an Entire Zone**
```
Test:    Does multi-zone deployment actually handle an AZ failure?
Method:  Block all traffic to/from us-east-1a
Target:  < 30 second impact. Automatic failover.
```

---

### How to Run a Chaos Experiment

Follow this process every time. Don't just randomly break things and watch.

```
Step 1: Define Steady State
  Pick measurable metrics: checkout_success_rate > 99%, p99_latency < 500ms.
  This is your baseline. Experiment succeeds only if these hold.

Step 2: State Your Hypothesis
  "Killing one payment instance will not affect checkout success rate because
   the circuit breaker reroutes traffic to remaining instances within 5 seconds."
  Be specific. Vague hypotheses produce vague results.

Step 3: Plan the Rollback
  Have the rollback command ready BEFORE you start.
  Kill the latency process, restore the pod, unblock the route.

Step 4: Inject Gradually
  Kill one pod, not all. Inject 100ms before 500ms. Drop 1% packets before 10%.
  Escalate slowly. Stop if things go wrong.

Step 5: Observe
  Watch your metrics dashboard in real time.
  Did steady state hold? Any unexpected cascades? How long until recovery?

Step 6: Analyze and Fix
  Steady state held → document it. Evidence your system is resilient.
  Steady state broke → gap found. Fix it. This is a win.

Step 7: Expand Scope
  Gradually: staging → production off-hours → production any time.
```

---

### Chaos Maturity Model

Not every team is ready to run chaos in production on a Tuesday afternoon. Build up gradually.

```
Level 1 — Kill Processes in Staging
  Kill pods, restart processes in non-production.
  Nobody affected (no real users in staging).
  Goal: confirm deployment and restart mechanics work.
  Risk: very low. Every team should be here.

Level 2 — Latency and Errors in Staging
  Inject latency, drop packets, return errors for dependencies in staging.
  Nobody affected.
  Goal: confirm circuit breakers, fallbacks, and timeout behavior.
  Risk: very low. All distributed systems teams should reach here.

Level 3 — Kill Processes in Production (Off-Hours)
  Kill pods in production, but only at 2 AM Sunday.
  Real users affected, but low-traffic window limits blast radius.
  Goal: confirm production systems behave like staging. They often don't.
  Risk: medium. Requires proven staging resilience and good monitoring.

Level 4 — Full Chaos in Production, Any Time
  Netflix-style random failures during business hours.
  Real users, peak traffic.
  Goal: continuous validation of production resilience under real conditions.
  Risk: higher. Requires excellent monitoring, fast rollback, years of work at lower levels.
```

Most teams should target Level 2 as a baseline and work toward Level 3. Do not jump to Level 4
without passing through the earlier levels. That is not chaos engineering. That is just chaos.

---

### Key Principle: Make Failure Boring

The goal is to run enough experiments that failures become routine events your system handles
automatically — not emergencies that wake up engineers.

```
Before chaos engineering:
  Failure → engineers scramble → figure out fallback on the fly
  → 2 hour outage → post-mortem → "we should have had a fallback"

After chaos engineering:
  Failure → pre-tested fallback activates automatically
  → alert fires → engineer checks dashboard → looks fine → back to sleep
```

Boring failures. Automatic recovery. No 3 AM pages. That is the goal.

---

## Summary

**Anti-Patterns** — Six patterns that cause outages: blind retries, generous timeouts, shared
thread pools, shallow health checks, skipped fallbacks, and simultaneous restarts. Each has a
specific fix. Know them by heart.

**Failure Scenario Design** — Eight-step framework: map dependencies, ask three failure-mode
questions per dependency, set timeouts (P99 × 3), add circuit breakers, define fallbacks, define
degradation tiers, define load shedding order, define monitoring. Use this for any interview
question about designing for failure.

**Chaos Engineering** — Fire drills before the fire. Start in staging. Inject latency and
process kills. Find gaps. Fix gaps. Work up to production off-hours. The goal is boring failures
— handled automatically before a real incident tests you.

---

*Part D2 will cover: runbooks and incident response, post-mortem structure, and SLO burn-rate
alerting.*
# Chapter 25: Failure Models and Partial Failures
## Part D2: Interview Calibration, Practice Questions, and Quick Reference

---

## Section 1: L5 vs L6 Interview Calibration

When you walk into a system design interview, the interviewer is not just listening to what you say. They are running a mental checklist. Every answer you give gets silently scored against a rubric. The difference between an L5 hire and an L6 hire often comes down to one thing: **specificity under pressure**.

An L5 engineer says the right category of answer. An L6 engineer says the right answer with numbers, tradeoffs, and second-order consequences.

Here is the mental rubric the interviewer is running in their head:

---

### Interviewer Mental Rubric

```
+------------------------+----------------------------------+------------------------------------------+
| INTERVIEWER QUESTION   | L5 SIGNAL (they heard this)      | L6 SIGNAL (they want this)               |
+------------------------+----------------------------------+------------------------------------------+
| Failure handling:      | "I'd add retry logic and         | "Timeout per dependency, circuit         |
| How do you handle a    |  maybe alert on errors"          |  breaker with threshold, fallback path,  |
| dependency that fails? |                                  |  retry with exponential backoff + jitter,|
|                        |                                  |  retry budget so we don't amplify load"  |
+------------------------+----------------------------------+------------------------------------------+
| Slow dependency:       | "I'd increase the timeout so     | "Slow is worse than dead. I'd use an     |
| Service B is slow but  |  we give it more time to         |  aggressive timeout — 200ms — open       |
| not down. What do you  |  respond"                        |  circuit breaker after 5 failures in     |
| do?                    |                                  |  10s, bulkhead so B's thread pool        |
|                        |                                  |  can't starve other calls"               |
+------------------------+----------------------------------+------------------------------------------+
| Partial failure:       | "I'd set up an alert when        | "Error rate lags by minutes. I alert on  |
| How do you detect      |  error rate goes above 1%"       |  P99 latency first — when P99 > 2x       |
| problems early?        |                                  |  baseline, something is wrong even if    |
|                        |                                  |  errors are still near zero"             |
+------------------------+----------------------------------+------------------------------------------+
| Recovery:              | "Restart the service and see     | "Rolling restart, not fleet restart.     |
| Service is degraded.   |  if that fixes it"               |  Pre-warm cache before traffic hits.     |
| How do you recover?    |                                  |  Watch for thundering herd — add jitter  |
|                        |                                  |  to reconnect timers. Watch for cascade  |
|                        |                                  |  as load redistributes"                  |
+------------------------+----------------------------------+------------------------------------------+
| Design question:       | "The system handles failures     | "Here is the degradation ladder: Tier 1  |
| How does your design   |  gracefully"                     |  full features, Tier 2 read-only mode    |
| handle failures?       |                                  |  with cached data, Tier 3 essential only |
|                        |                                  |  (no recommendations, no social), Tier 4 |
|                        |                                  |  static page with status message"        |
+------------------------+----------------------------------+------------------------------------------+
```

The pattern is consistent across all five rows:
- L5 gives the category ("retry", "alert", "restart")
- L6 gives the category PLUS the mechanism PLUS the number PLUS the consequence

---

### L5 vs L6 Phrases: Direct Contrast

Think of these as phrase upgrades. If you catch yourself saying the L5 version, swap it for the L6 version.

```
+----+----------------------------------------------------+-------------------------------------------------------+
| #  | L5 PHRASE (avoid)                                  | L6 PHRASE (use this)                                  |
+----+----------------------------------------------------+-------------------------------------------------------+
| 1  | "We should retry failed requests"                  | "Retry with exponential backoff and jitter, capped    |
|    |                                                    |  at a retry budget so we don't amplify a cascade"     |
+----+----------------------------------------------------+-------------------------------------------------------+
| 2  | "We'll set a timeout on that call"                 | "200ms for internal services, 1s for external APIs.   |
|    |                                                    |  Slow is worse than dead — timeout fast and fail"     |
+----+----------------------------------------------------+-------------------------------------------------------+
| 3  | "We'll alert on errors"                            | "Alert on P99 latency first. Error rate lags by       |
|    |                                                    |  minutes. P99 is the early warning"                   |
+----+----------------------------------------------------+-------------------------------------------------------+
| 4  | "We'll use a circuit breaker"                      | "Circuit breaker opens after 5 failures in 10s,       |
|    |                                                    |  half-opens after 30s to test recovery. Each          |
|    |                                                    |  dependency gets its own breaker"                     |
+----+----------------------------------------------------+-------------------------------------------------------+
| 5  | "We can degrade gracefully"                        | "Here is the explicit degradation ladder: five tiers, |
|    |                                                    |  each with a named feature list and the trigger       |
|    |                                                    |  condition that moves us to that tier"                |
+----+----------------------------------------------------+-------------------------------------------------------+
| 6  | "We'll use bulkheads to isolate services"          | "Each critical dependency gets its own thread pool.   |
|    |                                                    |  Payment gets 20 threads, recommendations gets 5.     |
|    |                                                    |  Recommendations saturating cannot touch payment"     |
+----+----------------------------------------------------+-------------------------------------------------------+
```

---

### Full Interview Exchange Example

**Interviewer:** "How would you handle partial failures in a distributed checkout system?"

---

**L5 Answer (what gets you an L5 rating):**

"I'd add retry logic for failed requests. If a dependency goes down we'd catch the exception and retry a few times. We'd also add monitoring and alert if the error rate goes above a threshold. The payment service would be wrapped in a try-catch and we'd show the user an error message if it fails."

What the interviewer hears: This engineer knows failure handling exists. They don't have a system for it. They'll handle failures reactively.

---

**L6 Answer (what gets you an L6 rating):**

"Let me think through this systematically.

**Step 1 — Identify the failure types per dependency.**
Checkout calls: Payment service, Inventory service, User service, Fraud detection. Each can fail differently:
- Payment: slow (most dangerous), partial (card declined vs service error), dead
- Inventory: stale data is okay for a few seconds, full failure means we can't confirm stock
- User service: we probably have session cache, full failure is survivable
- Fraud: slow detection is worse than skipping it — I'd rather process the order

**Step 2 — Timeout per dependency.**
- Payment: 1000ms hard limit. Payment failing slowly is worse than failing fast.
- Inventory: 200ms. If inventory is slow, use last-known cached value.
- User: 100ms. Session data is in cache anyway.
- Fraud: 150ms. Async fraud check post-payment is the fallback.

**Step 3 — Circuit breakers.**
Each dependency gets its own breaker. Threshold: 5 failures in a 10-second window opens the breaker. Half-open after 30 seconds to probe recovery. This prevents a slow payment service from holding threads across all checkout workers.

**Step 4 — Bulkheads.**
Separate thread pools per dependency. Payment gets 30 threads. Fraud gets 10. User gets 5. Inventory gets 10. A slow fraud service saturating its pool does not touch payment threads.

**Step 5 — Fallbacks.**
- User service down: use session cache (TTL 5 minutes). Degrade gracefully.
- Inventory down: proceed with order, verify inventory async, cancel and notify if out of stock.
- Fraud down: flag for async review post-purchase, do not block checkout.
- Payment down: no fallback — this is hard. Circuit open means we show 'payment unavailable' immediately rather than hanging for 30 seconds.

**Step 6 — Degradation tiers.**
- Tier 1: Full checkout, all features
- Tier 2: No fraud check (async), checkout proceeds, flagged for review
- Tier 3: Cached inventory, order confirmed pending inventory validation
- Tier 4: Payment service degraded, show 'checkout temporarily unavailable' with estimated time

**Step 7 — Monitoring.**
Alert on P99 payment latency > 500ms BEFORE error rate moves. Error rate lags by 2-5 minutes. Latency spike is the first signal.

**Step 8 — Chaos testing plan.**
Monthly: kill payment service, verify circuit breaker opens in under 15 seconds. Kill fraud service, verify checkout still completes. Inject 2-second delay into inventory, verify timeout fires at 200ms and cache fallback activates.

This gives checkout a defense-in-depth model. Users can complete purchases even when 2 of 4 dependencies are degraded."

---

What the interviewer hears: This engineer has a system. They've thought about failure types, not just failure existence. They have numbers. They know what each number buys them. They have a degradation model before the incident happens.

---

### Staff Engineer One-Liners

These are phrases worth memorizing. They are not just interview phrases — they communicate a mental model in a single sentence. When you drop these naturally in conversation, the interviewer updates their mental model of you.

```
1. "Slow is worse than dead."
   Why: A dead service fails fast. A slow service holds threads, blocks timeouts,
   and turns one failure into a cascade.

2. "Partial failure is the default state, not the exception."
   Why: At scale, something is always degraded. Design for it.

3. "Design the 60% state before you need it."
   Why: You cannot design a graceful degradation mode during an incident.
   It has to be pre-built.

4. "Every external call without a timeout is a cascade waiting to happen."
   Why: One slow dependency, no timeout, thread pool fills up. Everything stops.

5. "Retry without backoff is just delayed spam."
   Why: Immediate retry into a degraded system adds load, making recovery slower.

6. "A shared thread pool is a single point of failure."
   Why: Bulkheads exist precisely because shared resources let one bad caller
   starve everyone else.

7. "Latency is the leading indicator. Alert on P99 before error rate."
   Why: Error rate tells you you're already failing. P99 latency tells you
   you're about to fail. Alert earlier.

8. "Recovery can kill. Rolling restart, not fleet restart."
   Why: Restarting the whole fleet floods backends with cold-cache traffic.
   Rolling restart + cache pre-warming avoids the thundering herd.
```

---

## Section 2: Brainstorming Questions

These questions are for studying, not for the interviewer to ask you. Use them to stress-test your understanding. For each question, try to answer it out loud in 2 minutes before reading further.

---

### Category 1: Understanding Failure Models

**Q1. Why are partial failures harder to detect than complete failures?**

A complete failure has a clear signal: the service is down, health checks fail, alerts fire. A partial failure looks like normal operation from some angles. 3 out of 10 nodes are slow. Errors are 0.5%, below the threshold. Users are having a bad experience, but the monitoring says "green." The danger of partial failure is that it hides in the noise. Detection requires looking at the right signals — percentiles, not averages; latency before errors; user-facing metrics before infrastructure metrics.

**Q2. Why is a slow node worse than a dead node?**

A dead node gets removed from the load balancer quickly. Health checks fail, the node is marked unhealthy, traffic stops going there. A slow node keeps passing health checks. Traffic keeps going to it. Each request that hits the slow node ties up a thread waiting. Those threads fill up. New requests queue behind them. The queue fills the thread pool. The whole service starts responding slowly — even to requests that don't touch the slow node, because the thread pool is saturated. One slow node can degrade an entire fleet.

**Q3. What is a gray failure and why is it dangerous?**

A gray failure is a condition where a component works correctly by all automated checks but is degraded in a way users experience. Examples: a cache that hits 95% of the time instead of 99% (latency goes up, no errors), a database with a slow index (queries take 3x longer, no timeouts hit), a network with 0.1% packet loss (TCP retransmits, everything is slower, nothing hard-fails). Gray failures are dangerous because they do not trigger standard alerting. They require percentile monitoring, user-facing synthetic checks, and correlation across signals to detect.

**Q4. What is the degradation budget mindset?**

Instead of asking "will this fail?" ask "how much degradation can I afford?" For a given user action, define what the minimum acceptable experience is. For a social media feed: minimum = show some posts, even if stale. For a payment: minimum = do not lose the transaction. The degradation budget is the gap between full functionality and minimum acceptable. Knowing the budget lets you design fallbacks that fill the gap rather than collapsing to zero.

**Q5. How does the Swiss cheese model apply to distributed systems?**

The Swiss cheese model: each safety layer has holes (things it doesn't catch). A disaster happens when the holes in every layer line up. In distributed systems: your timeout catches most slow-dependency failures, but the circuit breaker catches the ones that slip through, but the bulkhead catches the ones that overwhelm the breaker, but the fallback catches what the bulkhead misses, but graceful degradation catches everything else. Each layer has gaps. Stack them so the gaps don't align. No single mechanism catches everything — that's why defense in depth matters.

---

### Category 2: Reasoning About Defense

**Q6. When do you use a circuit breaker vs just a timeout?**

Use a timeout for every call. Timeouts are not optional. Use a circuit breaker when you have a dependency that can become slow or partially unavailable in a sustained way. A circuit breaker avoids the cost of the timeout — instead of waiting 500ms on every request to a known-dead service, the breaker open means you fail immediately, no thread wasted. Timeouts handle individual request failures. Circuit breakers handle sustained dependency failures.

**Q7. How do you set timeout values?**

Start with: what does the P99 latency of this dependency look like when it's healthy? If a healthy Postgres read is 50ms at P99, set the timeout at 100-200ms — 2-4x the healthy P99. This gives the service room to be temporarily slower without tripping false timeouts, but catches true degradation fast. For user-facing calls, work backwards from user experience: if the total budget for a page load is 1 second, and you have 4 serial hops, each hop gets ~200ms. Set timeouts to enforce that budget.

**Q8. How do you size a bulkhead thread pool?**

Start with: how many concurrent requests do you expect to this dependency? Use Little's Law: concurrent requests = arrival rate * average latency. If you send 100 requests per second to a service with 50ms latency, you need 5 concurrent threads at steady state. Add a buffer — 2-3x — so you have 10-15 threads. Then ask: if this pool fills up, what is the cost? For a non-critical dependency, a small pool is fine — it fails fast. For a critical path dependency, size generously but still bounded.

**Q9. What operations can have fallbacks and what can't?**

Operations that can have fallbacks:
- Read operations (can use stale cache)
- Non-essential features (recommendations, ads, social features)
- Validation that can be done asynchronously (fraud checks)
- Enrichment (user profile data on a feed item)

Operations that usually cannot have fallbacks:
- Financial transactions (cannot fabricate a payment)
- Write operations that must be durable (order placement)
- Authentication (cannot fabricate identity)
- Operations where stale data causes real-world harm

The pattern: fallbacks work when stale or absent data is better than nothing. They fail when correctness is mandatory.

**Q10. How do you prioritize what to shed under load?**

Shed in reverse order of criticality. Define tiers before the incident:
- Never shed: authentication, payment, core write operations
- Shed early: recommendations, ads, analytics events, social features
- Shed in the middle: search, notifications, enriched data
- Keep until last: the core read/write path for the primary use case

Document this as a load-shedding priority list. When load shedding activates, it follows the list. Not ad hoc decisions during an incident.

---

### Category 3: System-Specific

**Q11. Design the failure model for a ride-sharing app's dispatch service.**

Dispatch service calls: GPS location service, driver availability service, pricing service, maps/routing service, notification service.

Failure modes:
- GPS slow: use last known location (acceptable if under 30 seconds old)
- Driver availability slow: use cached availability list, accept some stale data
- Pricing slow: use default pricing tier, flag for audit
- Maps slow: use cached route, accept slightly stale ETA
- Notification slow: degrade gracefully — driver gets the ride, notification retries async

Critical path: match driver to rider. Everything else is enrichment. Design the system so the match can happen with GPS + availability. Everything else degrades.

**Q12. Design fallbacks for a payment service.**

Payment is the hard case — you cannot fabricate success. Fallbacks for payment:

- Retry: yes, but with idempotency keys so retries don't double-charge
- Circuit breaker: yes — fail fast, do not hold user connections open
- Fallback to secondary payment processor: yes, if you have one contracted
- Queue for async processing: careful — tell user "processing, will confirm" not "success"
- Degradation: no degradation of the actual payment. Degrade surrounding features (no real-time fraud check, no loyalty points calculation) but the payment itself must complete or fail cleanly

The fallback design for payment is: fail fast and clearly rather than fail ambiguously.

**Q13. How would a cascading failure start in a social media feed system?**

Scenario: recommendation service gets a traffic spike from a viral post.

1. Recommendation service is slow. Latency climbs from 50ms to 800ms.
2. Feed service calls recommendation service. Threads wait 800ms instead of 50ms.
3. Feed service thread pool fills. Requests queue. Feed service response time climbs.
4. Upstream load balancer sees feed service slow. Adds more connections.
5. More connections means more threads waiting on recommendations.
6. Feed service starts dropping requests. Users get errors.
7. Users retry. More load.
8. Cascade spreads to auth service (more auth checks from retries), CDN origin (more cache misses as users retry), database (more reads as caches get bypassed).

Where a circuit breaker stops this: at step 2. Recommendations circuit opens after 5 slow calls. Feed service stops calling recommendations. Feed returns without recommendations. Thread pool drains. Feed service stabilizes.

**Q14. Design graceful degradation for a search feature.**

Search calls: inverted index service, ranking service, autocomplete service, personalization service, spell-check service.

Degradation tiers:
- Tier 1: Full search — all features active
- Tier 2: No personalization — same results for everyone, no user history factored in
- Tier 3: No spell-check — user must type exact terms
- Tier 4: No autocomplete — user types full query, submits
- Tier 5: Default ranking only — no ML ranking, just recency + simple relevance
- Tier 6: Search unavailable — show top 20 trending items as substitute

At each tier, users lose something but they don't lose everything. The site still functions.

**Q15. What happens to a global CDN during a regional network partition?**

During a regional network partition, one region of the CDN loses connectivity to the origin or to other regions.

What works: cached content in that region continues to be served. Static assets, previously cached pages — users in that region still get those with normal latency.

What breaks: cache misses. If content is not cached, the CDN edge cannot reach origin to fetch it. Requests fail or time out.

What can help: high cache TTLs mean more content survives from cache. Stale-while-revalidate headers let the CDN serve stale content while waiting for origin. Origin shield (a mid-tier caching layer) reduces the number of requests that need to reach origin.

Staff mindset: a CDN is itself a degradation mechanism. When origin is unavailable, the CDN's ability to serve stale is the fallback.

---

## Section 3: Homework Exercises

These exercises are meant to be done away from this document. Close it, open a blank page, and work through them. The point is not to get a perfect answer — it is to practice the thinking pattern.

---

### Exercise 1: Dependency Audit

**The task:** Pick a service you know — it can be a side project, something from work (sanitized), or a fictional e-commerce checkout service.

**What to do:** List ALL external dependencies that service calls. For each dependency, answer three questions:

```
+---------------------------+------------------+-----------------------------+---------------------------+
| DEPENDENCY                | TIMEOUT          | CIRCUIT BREAKER THRESHOLD   | FALLBACK                  |
+---------------------------+------------------+-----------------------------+---------------------------+
| Example: User service     | 100ms            | 5 failures / 10s window     | Session cache (5 min TTL) |
| Example: Payment service  | 1000ms           | 3 failures / 10s window     | No fallback — fail fast   |
| Example: Recommendations  | 150ms            | 10 failures / 30s window    | Empty list (hide section) |
| [Your dependency 1]       |                  |                             |                           |
| [Your dependency 2]       |                  |                             |                           |
| [Your dependency 3]       |                  |                             |                           |
+---------------------------+------------------+-----------------------------+---------------------------+
```

**Reflection questions:**
- Are there dependencies with no timeout today? Those are your highest risk.
- Are there dependencies with no fallback? Are those truly hard requirements, or could you design one?
- Which dependency failure would cause the most user-visible impact?

---

### Exercise 2: Degradation Ladder for a Social Media App

**The task:** Design a 5-tier degradation ladder for a social media app.

**Features to include:** Home feed, Stories, Search, Direct messages, Notifications, Profile page.

**What to do:** Fill in this table. For each tier, list which features are active and what the trigger condition is.

```
+--------+---------------------------+-------------------------------------------+
| TIER   | FEATURES ACTIVE           | TRIGGER CONDITION                         |
+--------+---------------------------+-------------------------------------------+
| Tier 1 | All 6 features            | Normal operation                          |
| Tier 2 |                           |                                           |
| Tier 3 |                           |                                           |
| Tier 4 |                           |                                           |
| Tier 5 |                           |                                           |
+--------+---------------------------+-------------------------------------------+
```

**Hints to get you started:**
- Home feed is the core feature — it should survive until the last tier
- Notifications and stories are enrichment — consider shedding them early
- Search involves ML ranking and indexing — it has natural degradation tiers within itself
- Direct messages are somewhere in the middle — higher value than stories, lower than feed

**Reflection:** How does this compare to what you think happens on real social media apps during incidents? (If you have ever noticed that Instagram shows "couldn't refresh" but the app still works for DMs, that is a degradation tier in action.)

---

### Exercise 3: Blast Radius Calculation

**The task:** Map how a single failure cascades through a service graph.

**The graph:**

```
         [Service A]
        /            \
  [Service B]    [Service C]
      |                |
  [Service D]    [Service E]
```

**Additional context:**
- Service A calls B and C (parallel)
- Service B calls D
- Service C calls E
- D and E do not call anything else
- Each service has a 500ms timeout on its downstream calls
- No circuit breakers exist (worst case scenario)
- Service X = Service D

**The exercise:**
1. Service D fails completely. Trace what happens to each service.
2. At what point does Service A become fully unavailable?
3. If you added circuit breakers to B and C's calls (threshold: 3 failures in 5 seconds), how does the blast radius change?
4. If you added a fallback to Service B for when D is unavailable, what would A's behavior be?

**Answer framework:**

```
Without circuit breakers:
- D fails: B's calls to D time out after 500ms
- B is slow (500ms response instead of normal): A's calls to B take 500ms
- A is slow: user-facing latency doubles
- Eventually B's thread pool fills: B becomes unavailable
- A's calls to B fail: A becomes unavailable

With circuit breakers at B and C:
- D fails: B's first 3 calls fail in under 5 seconds
- B's circuit breaker opens: B returns immediately with error
- A's call to B fails immediately (not after 500ms)
- A can still call C and E — partial success
- Blast radius contained to B and D

With fallback at B:
- D fails: B's circuit breaker opens
- B uses fallback (stale cache or empty response)
- A receives partial data from B, full data from C/E
- Degraded but functional
```

---

### Exercise 4: Timeout Audit

**The task:** For each operation, choose a timeout value and justify it.

Work through each row. Write your answer before reading the guidance.

```
+-------------------------------+-------------------+--------------------------------+
| OPERATION                     | YOUR TIMEOUT      | JUSTIFICATION                  |
+-------------------------------+-------------------+--------------------------------+
| Postgres read (indexed query) |                   |                                |
| Redis GET                     |                   |                                |
| External payment API          |                   |                                |
| Internal auth service         |                   |                                |
| Kafka consume (poll)          |                   |                                |
+-------------------------------+-------------------+--------------------------------+
```

**Reference answers (cover until you've answered):**

```
+-------------------------------+-------------------+--------------------------------------------------+
| OPERATION                     | SUGGESTED TIMEOUT | JUSTIFICATION                                    |
+-------------------------------+-------------------+--------------------------------------------------+
| Postgres read (indexed)       | 100-200ms         | Healthy P99 is 5-20ms. 100ms is 5-20x headroom. |
|                               |                   | More than 100ms means something is wrong.        |
+-------------------------------+-------------------+--------------------------------------------------+
| Redis GET                     | 10-20ms           | In-memory, same datacenter. >20ms means          |
|                               |                   | network issue or Redis is saturated.             |
+-------------------------------+-------------------+--------------------------------------------------+
| External payment API          | 1000-2000ms       | External APIs are slower. 1s is standard.        |
|                               |                   | More than 2s means hold the user connection       |
|                               |                   | open for no good reason.                         |
+-------------------------------+-------------------+--------------------------------------------------+
| Internal auth service         | 50-100ms          | Should be cached. >100ms means cache miss        |
|                               |                   | or service degraded. Fail fast — auth is         |
|                               |                   | on the hot path of every request.                |
+-------------------------------+-------------------+--------------------------------------------------+
| Kafka consume (poll)          | Configurable      | Kafka poll timeout sets how long to wait for     |
|                               |                   | new messages. 100-500ms is typical.              |
|                               |                   | Not the same as a call timeout.                  |
+-------------------------------+-------------------+--------------------------------------------------+
```

**Takeaway:** The pattern is 2-5x the healthy P99 for internal services, more generous for external services. Always tie the timeout to what you know about the service, not to a round number you picked arbitrarily.

---

### Exercise 5: Interview Practice — Twitter Home Timeline

**The task:** Spend 5 minutes (set a timer) answering this question out loud:

**"Design the failure model for Twitter's home timeline."**

**What to cover in those 5 minutes:**
1. Failure taxonomy — what are all the dependencies the home timeline calls? What can fail in each?
2. Timeout values — one per dependency, with brief justification
3. Circuit breakers — which dependencies get one and at what threshold?
4. Degradation tiers — at least 3 tiers with feature list
5. Key monitoring metrics — what 3 metrics would you alert on?

**Scoring guide (honest self-assessment):**

```
Did you name at least 4 dependencies? (fanout service, cache, social graph, ads, recommendations)
Did you give timeout values with justification?
Did you distinguish between "slow" and "down" failure modes?
Did you design a specific degradation ladder (not just "graceful degradation")?
Did you name P99 latency as a monitoring metric?
Did you mention thundering herd as a recovery risk?
Did you mention chaos testing or how you'd verify the model works?
```

If you hit 5 or more, you are thinking at L6 depth on this topic.

---

## Section 4: Conclusion and Quick Reference Card

---

### Defense Stack Summary

Every pattern in this chapter has a job. Here is the full stack in one table:

```
+---------------------+------------------------------------------+---------------------------+-----------------------+
| PATTERN             | ONE-LINE DESCRIPTION                     | WHEN TO USE               | KEY NUMBER            |
+---------------------+------------------------------------------+---------------------------+-----------------------+
| Timeout             | Stop waiting after a set time            | Every external call.      | 2-5x healthy P99.     |
|                     |                                          | No exceptions.            | Internal: 100-200ms.  |
|                     |                                          |                           | External: 1-2s.       |
+---------------------+------------------------------------------+---------------------------+-----------------------+
| Circuit Breaker     | Stop calling a known-failed dependency   | Sustained failures or     | Open: 5 failures in   |
|                     | to avoid holding threads and amplifying  | slowness. Not for         | 10s. Half-open: 30s   |
|                     | load on a degraded system                | one-off errors.           | probe interval.       |
+---------------------+------------------------------------------+---------------------------+-----------------------+
| Bulkhead            | Give each dependency its own thread pool | Any system where one      | Size: 2-3x expected   |
|                     | so one bad dependency can't starve       | dependency failing         | concurrency.          |
|                     | the others                               | slowly matters.           |                       |
+---------------------+------------------------------------------+---------------------------+-----------------------+
| Fallback            | Return a cached/default response when    | Read operations,          | Cache TTL: 30s-5min   |
|                     | a dependency is unavailable              | non-critical enrichment.  | depending on staleness|
|                     |                                          | NOT for writes/payments.  | tolerance.            |
+---------------------+------------------------------------------+---------------------------+-----------------------+
| Load Shedding       | Reject low-priority requests when        | Approaching capacity.     | Shed at 80% capacity. |
|                     | system is near capacity to protect       | Better to degrade some    | Keep core path alive. |
|                     | the critical path                        | than fail all.            |                       |
+---------------------+------------------------------------------+---------------------------+-----------------------+
| Graceful            | Serve a reduced feature set when         | Any user-facing system    | Pre-define 3-5 tiers  |
| Degradation         | full functionality is unavailable        | where some value is       | before the incident.  |
|                     |                                          | better than none.         |                       |
+---------------------+------------------------------------------+---------------------------+-----------------------+
```

---

### Failure Type Quick Reference

```
+---------------------+-----------------------------------+----------------------------------+
| FAILURE TYPE        | KEY DETECTION SIGNAL              | PRIMARY DEFENSE                  |
+---------------------+-----------------------------------+----------------------------------+
| Process Crash       | Health check fails. Load          | Health checks + auto-restart.    |
|                     | balancer removes node.            | Redundancy (>1 instance).        |
+---------------------+-----------------------------------+----------------------------------+
| Network Partition   | Timeout on all calls to a         | Timeout + circuit breaker.       |
|                     | region or service cluster.        | Fallback to cache or default.    |
+---------------------+-----------------------------------+----------------------------------+
| Slow Node           | P99 latency spike WITHOUT         | Aggressive timeout. Circuit      |
|                     | corresponding error rate spike.   | breaker. Remove from LB pool.    |
+---------------------+-----------------------------------+----------------------------------+
| Dependency Failure  | Your service's error rate         | Timeout + circuit breaker +      |
|                     | climbs or latency climbs          | bulkhead + fallback.             |
|                     | for one call path.                |                                  |
+---------------------+-----------------------------------+----------------------------------+
| Gray Failure        | P99 elevated but no hard          | Synthetic monitoring. Percentile |
|                     | failures. User complaints.        | alerts. User-facing health       |
|                     | Metrics look "okay."              | checks (not just infra checks).  |
+---------------------+-----------------------------------+----------------------------------+
```

---

### Common Mistakes Checklist

Review this list before every system design. Check yourself.

```
  [ ] x MISTAKE: No timeout on external calls
  [✓] CORRECT: Every external call has a timeout. Sized to 2-5x healthy P99.

  [ ] x MISTAKE: One timeout for all dependencies
  [✓] CORRECT: Each dependency has its own timeout based on its own P99.

  [ ] x MISTAKE: Alerting only on error rate
  [✓] CORRECT: Alert on P99 latency first. Error rate lags by minutes.

  [ ] x MISTAKE: Retry without backoff or budget
  [✓] CORRECT: Exponential backoff with jitter. Retry budget to limit amplification.

  [ ] x MISTAKE: Single shared thread pool for all downstream calls
  [✓] CORRECT: Bulkheads: each critical dependency has its own thread pool.

  [ ] x MISTAKE: Saying "handles failures gracefully" without specifics
  [✓] CORRECT: Named degradation tiers with explicit feature list at each tier.

  [ ] x MISTAKE: Designing recovery as "restart the service"
  [✓] CORRECT: Rolling restart, cache pre-warm, watch for thundering herd.

  [ ] x MISTAKE: Building failure handling during the incident
  [✓] CORRECT: Failure model designed, documented, and chaos-tested before the incident.
```

---

### Pre-Interview Self-Check

Run through these 7 questions the night before your interview. If you cannot answer any of them in under 30 seconds, spend another hour on that topic.

```
  1. Can I name at least 5 failure patterns (not just "retry" and "timeout")?
     [Timeout / Circuit Breaker / Bulkhead / Fallback / Load Shedding /
      Graceful Degradation / Retry with backoff]

  2. Can I give timeout values for internal vs external calls and justify them?
     [Internal: 100-200ms. External: 1-2s. Based on 2-5x healthy P99.]

  3. Can I describe a degradation ladder with 3+ tiers and specific feature lists?
     [Tier 1: full. Tier 2: no ML. Tier 3: no non-critical features. Tier 4: read-only.]

  4. Can I explain why P99 latency matters more than error rate for early detection?
     [Error rate lags 2-5 minutes. P99 latency is the first signal of degradation.]

  5. Can I explain why slow is worse than dead?
     [Dead: fast fail, threads free. Slow: threads held, pool fills, cascade spreads.]

  6. Can I explain the thundering herd problem and one mitigation?
     [Cold cache after restart floods database. Pre-warm cache or jitter reconnects.]

  7. Can I name 3 operations that cannot have fallbacks and explain why?
     [Financial transactions, authentication, durable writes — correctness mandatory.]
```

---

### Final Thought

There is a temptation in systems thinking to chase perfection. To want zero failures. To build the system that never goes down.

Staff Engineers know this is not the goal. The goal is narrower and more achievable:

**Staff Engineers don't eliminate failures. They eliminate surprises.**

The goal isn't zero incidents — it's zero incidents that weren't designed for.

When a circuit breaker opens and your service serves cached data for 2 minutes while a dependency recovers, that is not a failure. That is the system working as designed. When the payment service times out in 1 second and shows the user a clear error instead of a 30-second hang, that is the system working as designed.

The measure of a resilient system is not: did anything go wrong? It is: when something went wrong, did the system behave as we expected?

That is the shift in mindset from L5 to L6. From reactive to designed. From handling failures to anticipating them.

---

### Visual Summary: Chapter 25 in One Box

```
+==============================================================================+
|                    CHAPTER 25: FAILURE MODELS — MASTER VIEW                 |
+==============================================================================+
|                                                                              |
|  FAILURE TAXONOMY                 DEFENSE STACK                             |
|  +-----------------------+        +----------------------------------+       |
|  | Process Crash         |        | Timeout         → Every call     |       |
|  | Network Partition     |        | Circuit Breaker → Sustained fail |       |
|  | Slow Node (worst)     |        | Bulkhead        → Isolate pools  |       |
|  | Dependency Failure    |        | Fallback        → Cached default |       |
|  | Gray Failure (hidden) |        | Load Shedding   → Shed early     |       |
|  +-----------------------+        | Graceful Degrade→ Pre-define tiers|      |
|                                   +----------------------------------+       |
|                                                                              |
|  KEY NUMBERS                      DEGRADATION LADDER                        |
|  +---------------------------+    +----------------------------------+       |
|  | Internal timeout: 100ms   |    | Tier 1: Full features            |       |
|  | External timeout: 1-2s    |    | Tier 2: No ML/personalization    |       |
|  | Circuit open: 5 fail/10s  |    | Tier 3: No non-critical features |       |
|  | Half-open probe: 30s      |    | Tier 4: Read-only mode           |       |
|  | Retry: exp backoff+jitter |    | Tier 5: Static page + status     |       |
|  | Shed at: 80% capacity     |    +----------------------------------+       |
|  +---------------------------+                                               |
|                                                                              |
|  MONITORING PRIORITY              STAFF ENGINEER MINDSET                    |
|  P99 latency  (alert FIRST)       "Partial failure is the default state"    |
|  Error rate   (lags by minutes)   "Design the 60% state before you need it" |
|  Thread pool  (bulkhead signal)   "Slow is worse than dead"                 |
|  Queue depth  (pressure signal)   "Every call without timeout = cascade"    |
|                                   "Recovery can kill — rolling restart"     |
|                                                                              |
|  INTERVIEW SHORTCUT                                                          |
|  L5: "retry + alert"                                                         |
|  L6: timeout → circuit breaker → bulkhead → fallback → degradation tiers    |
|       → P99 monitoring → chaos testing plan                                  |
|                                                                              |
|  FINAL PRINCIPLE:                                                            |
|  Staff Engineers don't eliminate failures. They eliminate surprises.         |
|  The goal isn't zero incidents — it's zero incidents not designed for.       |
+==============================================================================+
```

---

*End of Chapter 25, Part D2*
*Chapter 25 complete: Parts A, B, C, D1, D2*
