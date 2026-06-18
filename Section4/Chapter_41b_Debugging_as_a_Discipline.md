# Chapter 41b: Debugging as a Discipline

> You have spent 41 chapters learning how systems are built.
> This chapter teaches you what to do when they break and nobody knows why.

---

```
+===========================================================================+
|            CHAPTER 41b: DEBUGGING AS A DISCIPLINE                         |
+===========================================================================+
|                                                                           |
|  CORE INSIGHT: Debugging is not luck or experience. It is a method.      |
|  Every great debugger you have ever watched works the same way --         |
|  they just do it so fast it looks like intuition. This chapter            |
|  makes the method explicit so you can learn it in months, not years.     |
|                                                                           |
|  THE 7 PARTS OF THIS CHAPTER:                                            |
|                                                                           |
|  1. The Debugging Mental Model  -- Why most debugging fails               |
|  2. The 5-Step Framework        -- The universal method                   |
|  3. The 5 Classes of Bugs       -- Each needs a different strategy        |
|  4. Local vs Production         -- Different environment, different tools  |
|  5. Distributed System Bugs     -- The hard stuff: races, consistency     |
|  6. Performance Debugging       -- Latency, CPU, memory, p99 spikes       |
|  7. Intermittent / Flaky Bugs   -- The hardest class. There is a method.  |
|                                                                           |
|  THE UNIVERSAL 5-STEP DEBUGGING FRAMEWORK:                               |
|  +--------+-----------------------------------------------------+        |
|  | Step 1 | DEFINE: What exactly is wrong? (not a theory)       |        |
|  | Step 2 | REPRODUCE: Get a reliable reproduction first        |        |
|  | Step 3 | ISOLATE: Binary search the search space             |        |
|  | Step 4 | HYPOTHESIZE: One theory at a time, test it cleanly  |        |
|  | Step 5 | FIX + VERIFY: Fix, write a regression test, confirm |        |
|  +--------+-----------------------------------------------------+        |
|                                                                           |
|  THE 5 CLASSES OF BUGS (each needs a different approach):                |
|  1. Logic bugs       -- wrong output, deterministic, reproducible        |
|  2. Concurrency bugs -- race conditions, deadlocks, intermittent         |
|  3. Memory bugs      -- leaks, corruption, use-after-free                |
|  4. Performance bugs -- latency spikes, CPU saturation, memory growth    |
|  5. Distributed bugs -- split brain, stale cache, message ordering       |
|                                                                           |
|  L5 vs L6 IN DEBUGGING:                                                  |
|  +-------------------+------------------------+------------------------+  |
|  | Dimension         | L5                     | L6                     |  |
|  +-------------------+------------------------+------------------------+  |
|  | Starts with       | A theory               | A precise symptom      |  |
|  | Reproduces by     | Trying in production   | Writing a test case    |  |
|  | Isolates by       | Reading the diff       | Binary searching       |  |
|  | Fixes             | This bug               | This class of bug      |  |
|  | Documents         | The fix in a comment   | The method for others  |  |
|  +-------------------+------------------------+------------------------+  |
|                                                                           |
|  KEY RULE: Never change two things at once while debugging.              |
|  You will not know which change fixed it. Or broke it more.              |
|                                                                           |
+===========================================================================+
```

---

## Intern to Staff: Same Bug, Four Levels

**The bug:** "The checkout page is slow sometimes."

That is the entire bug report. No reproduction steps. No error message. No timing. Just: "slow sometimes."

This is the most common bug report in the world. Watch how four levels of engineer respond to it.

---

### Intern

```
  Receives: "checkout page slow sometimes"
  Action:   Opens Chrome DevTools. Refreshes the page.
            Page loads in 800ms. Seems fine.
  Slack:    "I checked and it seems okay now."
  Result:   Ticket marked "cannot reproduce."
            Bug recurs next day. Same ticket reopened.

  What went wrong:
  - "Seems okay now" is not a verification.
  - The intern tested happy path at 10 AM with no load.
    The bug happens at 5 PM under traffic.
  - No data collected. No hypothesis formed.
  - No understanding of WHEN "sometimes" means.
```

---

### L4 (Mid-level)

```
  Receives: "checkout page slow sometimes"
  Action 1: Checks Datadog. Finds p99 latency spikes at 5 PM.
            Spikes are 3-4 seconds. Normal is 300ms.
  Action 2: Looks at the code changed in the last deploy.
            Finds a new "fetch related products" call added
            to the checkout page.
  Action 3: Reads the query. Recognizes N+1 pattern:
            one query per cart item, fetches related products.
  Action 4: Fixes the N+1 query. Ships the fix.

  Result:   The 5 PM p99 spike drops. Ticket closed.

  What they did well:
  - Used monitoring to define "sometimes" precisely
  - Found the specific bug

  What they missed:
  - The N+1 fix reduced latency to 800ms. Still slow.
  - Why? Because there are TWO more contributing factors
    they didn't investigate after finding the first one.
  - The DB connection pool also starves at 5 PM traffic.
  - The CDN cache misses on the related products endpoint.
  - All three compound. Fixing one reduces the symptom
    but does not solve the problem.
  - Stopped after finding the first theory that was correct.
    Did not verify the fix actually matched the symptom.
```

---

### L5 (Senior)

```
  Receives: "checkout page slow sometimes"

  Step 1 -- Define precisely:
  Checks Datadog. p99 spikes at 5 PM weekdays only.
  p50 is normal. This is a tail latency problem, not
  average latency. Already tells them: it's not ALL
  requests, it's a subset under specific conditions.

  Step 2 -- Reproduce reliably:
  Writes a load test: simulate 500 concurrent users
  adding 20+ items to cart. Reproduces the spike locally.
  Now has a controlled reproduction. Can test fixes
  without waiting for 5 PM.

  Step 3 -- Isolate:
  Adds timing instrumentation to each phase of checkout:
  - Cart fetch: 12ms
  - Product data fetch: 2,800ms  <-- here
  - Tax calculation: 8ms
  - Payment token: 15ms
  Found it in one pass.

  Step 4 -- Hypothesize and test:
  Theory 1: N+1 query on product data fetch.
            Test: add EXPLAIN ANALYZE to the query.
            Confirmed: 1 query per item, 23 items = 23 queries.
            Fix: JOIN. Rerun load test. Product fetch: 45ms.
  Does the overall p99 fix?
            Rerun load test. p99 still 1,200ms. Not fixed yet.
  Theory 2: Connection pool exhaustion.
            Test: add connection pool metrics to load test.
            Confirmed: pool hits 100% at 450 concurrent users.
            Fix: raise pool size from 20 to 50. Rerun.
            p99: 380ms. Close to normal.

  Shipped. Both fixes in one deploy. Wrote regression test
  that fails if p99 exceeds 500ms at 500 concurrent users.

  What they did well:
  - Systematic. Did not stop at the first fix.
  - Reproduced before fixing.
  - Measured after each fix.

  What they missed:
  - Did not check whether this class of bug can recur.
  - No CI check prevents N+1 from being introduced again.
  - No alert on connection pool utilization.
  - Post-mortem: none.
```

---

### L6 (Staff)

```
  Receives: "checkout page slow sometimes"

  Starts differently: does NOT open the code yet.

  Step 1 -- Define the symptom precisely with data:
  "slow sometimes" is not a bug definition.
  Opens Datadog, New Relic, and distributed traces.
  
  Finds:
  - p99 spikes: 5 PM - 7 PM weekdays. ~8x normal.
  - p50: unchanged. Tail problem, not average.
  - Spike started: last Tuesday. Not gradual. Sudden.
  - Tuesday's deploy: added "related products" to checkout.
  - Revenue impact: ~$40K/day in abandoned carts
    (from funnel analysis: conversion drops 2.3% when
     p99 > 1 second, confirmed by A/B test data).

  Now has: precise symptom, onset time, revenue impact.
  BEFORE opening the code.

  Step 2 -- Reproduce reliably:
  Writes a load test that reproduces the spike in 10 minutes.
  Confirms: reproducible at > 400 concurrent users + 20 items.
  Below that threshold: fine.

  Step 3 -- Isolate by binary search:
  Not just "find the slow query." Find ALL contributing factors.
  Adds OpenTelemetry spans to each checkout phase.
  Distributed trace shows THREE compounding issues:
  
  TRACE VIEW:
  checkout_request [total: 3,200ms]
  |-- cart_service [45ms]
  |-- product_data [2,800ms]   <-- dominant
  |   |-- db_query x 23 [2,600ms]  <-- N+1
  |-- connection_pool_wait [350ms] <-- secondary
  |-- cdn_cache_miss [180ms]       <-- tertiary
  
  Three bugs, not one.

  Step 4 -- Fix in order of impact:
  Fix 1: N+1 JOIN. Load test. p99: 1,100ms.
  Fix 2: Connection pool 20 -> 50. Load test. p99: 380ms.
  Fix 3: CDN cache TTL for related products: 0 -> 60s.
         Load test. p99: 280ms. Normal is 300ms. Done.

  Step 5 -- Systemic fixes (what L5 didn't do):
  - Adds N+1 detection to CI (prevents class recurrence)
  - Adds connection pool alert at 80% (catches it earlier)
  - Writes "checkout performance debugging runbook" so
    any on-call engineer can reproduce and diagnose this
    class in 15 minutes next time
  - Post-mortem: root cause is "related products feature
    had no performance review before shipping"
  - Adds: "performance review checklist" to the TDD template

  Result: bug fixed. Class of bug has a prevention mechanism.
  Future engineer who introduces N+1 in checkout gets caught
  by CI before it reaches production.
```

**The L6 difference in one sentence:** L6 did not just fix the checkout page. They made it structurally harder for the next engineer to break the checkout page in the same way.

---

## Intern to Staff: Second Scenario -- The Race Condition

**The bug:** "Users are sometimes losing items from their cart."

Three to five times a day, a user adds an item to their cart. The item appears for a few seconds, then vanishes. A different engineer checks the cart every time and sees it empty.

---

### Intern (Scenario 2)

```
  Receives: "users losing items from cart"

  Action 1: Manually adds items to own test account.
            Items stay. Works every time.
  Action 2: Checks DB: SELECT * FROM cart_items WHERE user_id = 12345;
            Sees 0 items. "Cart is empty, as expected."
  Slack:    "I checked the cart and the database. Cannot
            reproduce. The user may have removed the items
            themselves."
  
  What went wrong:
  1. Tested alone. The bug requires two concurrent operations
     on the same cart. A single test user in a quiet
     environment never triggers the race window.
  2. "Cannot reproduce" = "cannot reproduce with 1 user
     in a quiet environment." That is not a resolution.
  3. The intern looked at the DB too late. The items WERE
     there, then a race condition deleted them. Looking
     after the fact confirms nothing.
```

---

### L4 (Scenario 2)

```
  Receives: "users losing items from cart"

  Action 1: Pulls logs for the affected user (12345).

  Log output:
  [14:23:01.003] cart.addItem:    user=12345 item=SKU-789 qty=1
  [14:23:01.004] cart.addItem:    user=12345 item=SKU-789 qty=1 (duplicate event)
  [14:23:01.105] cart.reconcile:  user=12345 reading DB...
  [14:23:01.108] cart.reconcile:  user=12345 DB returned [] (0 items)
  [14:23:01.110] cart.setCache:   user=12345 items=[]   <-- OVERWRITES!

  Action 2: Finds the reconcile code:
  
    func reconcileCart(userID) {
      items := db.getCartItems(userID)  // reads DB
      cache.setCart(userID, items)       // writes to cache
    }
  
  "The reconcile read the DB BEFORE addItem committed,
   got 0 items, then overwrote the cache with 0."

  Fix: adds sleep(200ms) before reconcile reads the DB.
       "This gives addItem time to commit first."
  
  Result: bug frequency drops from 5x/day to 1x/day.
          Not fixed. Just slower to trigger.

  What they missed:
  A 200ms delay makes the race window smaller, not zero.
  Under any load spike or DB latency, addItem can still
  take > 200ms to commit. The race fires again.
  Timing hacks are not fixes. They are deferred failures.
```

---

### L5 (Scenario 2)

```
  Receives: "users losing items from cart"

  Step 1 -- Define precisely:
  Pulls logs for all affected users over 7 days.
  23 occurrences. Each one has: a cart.reconcile event
  within 200ms of a cart.addItem for the same user.
  Pattern confirmed: this is a race, not random.

  Step 2 -- Reproduce reliably:
  
    func TestCartRace(t *testing.T) {
      userID := "race-test-001"
      var wg sync.WaitGroup
      wg.Add(2)
      go func() {
        defer wg.Done()
        cart.AddItem(ctx, userID, "SKU-789", 1)
      }()
      go func() {
        defer wg.Done()
        time.Sleep(2 * time.Millisecond) // reconcile runs slightly after add
        cart.Reconcile(ctx, userID)
      }()
      wg.Wait()
      items := cart.GetItems(ctx, userID)
      assert.Len(t, items, 1, "expected 1 item after add+reconcile")
    }
  
  Runs 1,000 times. Fails ~28% of runs. Race confirmed.

  Step 3 -- Race timeline (drawn out):
  
    T+0ms:   addItem writes to DB. DB commit in progress.
    T+1ms:   reconcile reads DB. Sees 0 items (add not committed yet).
    T+5ms:   addItem DB commit finishes.
    T+6ms:   addItem writes cache: cache = [SKU-789]
    T+8ms:   reconcile writes cache with stale read: cache = []
  
  The reconcile's read was stale. Its cache write wins
  because it happens last, erasing the correct state.

  Fix: optimistic locking with a version number.
  
    // DB and cache now carry a version counter.
    // Reconcile only writes cache if the DB version
    // it read is NEWER than the current cache version.
    func reconcileCart(userID) {
      items, dbVersion := db.getCartItemsWithVersion(userID)
      cacheVersion := cache.getCartVersion(userID)
      if dbVersion > cacheVersion {
        cache.setCartWithVersion(userID, items, dbVersion)
      }
      // If cacheVersion >= dbVersion: cache already has
      // a more recent write. Don't overwrite it.
    }
  
  TestCartRace now passes 10,000/10,000 runs. Shipped.

  What they missed:
  Three other cart functions (applyPromoCode, removeItem,
  clearExpiredItems) have the same read-then-overwrite
  pattern. All three can produce the same race.
  Fixed one instance. Missed the class.
```

---

### L6 (Scenario 2)

```
  Receives: "users losing items from cart"

  Starts by scoping, not by reading code.

  Step 1 -- Understand the scope:
  - 23 occurrences in 7 days = ~3.3/day
  - Week 1: 3/day. Week 2: 8/day. GROWING. Why?
  - Check recent changes: reconcile job was changed from
    running every 5 minutes to every 30 seconds, 14 days ago.
  - More frequent reconcile = more chances to hit the race.
  - This will be 20+/day within a month without a fix.
  - Revenue: avg cart $85, 23 losses = ~$2K. Small now.
    But if reconcile runs every 10 seconds next quarter: ~$30K/day.

  Step 2 -- Find ALL race surfaces before fixing any:
  
    # Find every place that writes to cart cache
    grep -rn "cache.setCart\|cache.set.*cart\|setCartItems" \
         --include="*.go" ./internal/cart/
  
  Output:
    cart/reconcile.go:47:   cache.setCart(userID, items)
    cart/promo.go:83:       cache.setCartItems(userID, items)
    cart/remove.go:31:      cache.setCart(userID, updated)
    cart/expire.go:62:      cache.setCartItems(userID, active)
  
  4 write surfaces. All 4 have the same stale-read pattern.

  Step 3 -- Fix the abstraction, not the instances:
  
    // New: all cart cache writes go through one function.
    // Internally uses Redis COMPARE-AND-SWAP on the version.
    func updateCartCache(ctx context.Context, userID string,
                         fn func(*Cart)) error {
      const maxRetries = 3
      for i := 0; i < maxRetries; i++ {
        cart, version, err := cache.getCartWithVersion(ctx, userID)
        if err != nil { return err }
        fn(cart)   // apply mutation to local copy
        swapped, err := cache.casCart(ctx, userID, cart, version)
        if err != nil { return err }
        if swapped { return nil }
        // another writer committed: back off and retry
        time.Sleep(time.Duration(i*i) * time.Millisecond) // exp backoff
      }
      return ErrConcurrentCartUpdate
    }
  
  All 4 callers rewritten to use updateCartCache.
  All 4 race tests now pass 10,000/10,000 runs.

  Step 4 -- Prevent recurrence:
  - Linter rule: cache.setCart() is forbidden; use updateCartCache().
    Any PR calling cache.setCart() directly fails CI.
  - Post-mortem root cause: "reconcile frequency was increased
    without a concurrency review." New engineering checklist:
    "Does this change affect write frequency to a shared
     mutable resource? If yes: attach a concurrency review."
  - Runbook: "cart item loss" added to the on-call wiki
    with the race pattern and the commands to diagnose it.

  Result: 0 cart loss incidents in 45 days post-fix.
```

**The second scenario teaches a different L6 lesson:** The performance scenario showed that L6 fixes the CLASS of bug. This scenario shows that L6 first maps ALL instances of the pattern before fixing ANY of them. Fixing one and missing three is not a fix — it is a delay.

---

## Part 1: The Debugging Mental Model

### The Analogy

A doctor and an engineer both diagnose problems. The doctor cannot open the patient up every time something feels wrong. They have to reason from symptoms to cause, form a hypothesis, run a test, observe the result, and update the hypothesis.

An engineer debugging a system is doing exactly the same thing. The "patient" is the system. The "symptoms" are the error messages, latency spikes, wrong outputs. The "tests" are log statements, profilers, and load tests.

The difference between a great debugger and a mediocre one is the same as the difference between a great diagnostician and a mediocre one: the great one forms a *specific, testable hypothesis* before running a test. The mediocre one tries things randomly and hopes something works.

---

### Why Most Debugging Fails

There are four failure modes that account for 90% of wasted debugging time:

**Failure 1: Debugging a theory instead of a symptom**

```
  WRONG START: "I think it's the cache. Let me check the cache."
  WHY IT FAILS: You are testing your first guess, not the
                problem. If the cache is fine, you wasted
                30 minutes and learned nothing useful.

  RIGHT START: "The API returns 503 for 12% of requests.
               Let me define exactly when, for whom, and
               what the error code actually means."
               Now you have a symptom. You can bisect from it.
```

**Failure 2: Changing multiple things at once**

```
  WRONG:
  Day 1: Increase connection pool size AND upgrade Redis version
         AND change the cache TTL from 30s to 60s.
  Day 2: Problem is gone.
  Day 2 question: Which change fixed it?
  Answer: Nobody knows.
  Day 3: New incident. Can you reverse just the change that
          caused a problem? No, because you don't know which one.

  RIGHT:
  Change one thing. Observe. Change one thing. Observe.
  Slower per step. Faster to root cause.
```

**Failure 3: Not reproducing before fixing**

```
  WRONG:
  Engineer sees a bug. Has a theory. Ships a fix.
  Production is watched. Problem seems gone.
  Bug recurs 3 days later in a different form.
  Was the fix wrong? Did it fix the wrong thing?
  Nobody knows because there was never a reliable test.

  RIGHT:
  Before touching any code: get a reproduction.
  A reproduction is: "I can make this bug happen in
  under 5 minutes, on demand, consistently."
  If you can reproduce it, you can verify the fix.
  If you can't reproduce it, you cannot verify you fixed it.
```

**Failure 4: Stopping at the first thing that looks wrong**

```
  WRONG:
  Find an N+1 query. Fix it. Ship it.
  p99 drops from 3,200ms to 1,100ms.
  "That wasn't the only issue but at least I improved it."
  Teams get used to 1,100ms. Ticket closed.

  RIGHT:
  After fixing the first thing: measure again.
  "p99 is 1,100ms. The target is 300ms. I am not done."
  Keep bisecting until the symptom is actually resolved.
```

---

### The Scientific Method, Applied to Code

```
  SCIENTIFIC METHOD          DEBUGGING EQUIVALENT
  +-----------------+        +---------------------------+
  | Observe         |  -->   | Collect data from logs,   |
  |                 |        | metrics, traces           |
  +-----------------+        +---------------------------+
  | Define the      |  -->   | Write a precise bug       |
  | question        |        | statement: when, what,    |
  |                 |        | how often, impact         |
  +-----------------+        +---------------------------+
  | Form hypothesis |  -->   | List 2-3 theories. Rank   |
  |                 |        | by likelihood. Pick the   |
  |                 |        | most testable first.      |
  +-----------------+        +---------------------------+
  | Design test     |  -->   | Write the reproduction    |
  |                 |        | case or add instrumentation|
  +-----------------+        +---------------------------+
  | Run test        |  -->   | Execute. Do not change    |
  |                 |        | anything else while       |
  |                 |        | the test runs.            |
  +-----------------+        +---------------------------+
  | Analyze result  |  -->   | Did the result match the  |
  |                 |        | hypothesis? If yes: fix.  |
  |                 |        | If no: new hypothesis.    |
  +-----------------+        +---------------------------+
  | Communicate     |  -->   | Post-mortem, runbook,     |
  |                 |        | regression test           |
  +-----------------+        +---------------------------+
```

---

### Brainstorming Questions -- Part 1: Mental Model

**Q1.** You receive a bug report: "The search is broken." What are the first 3 questions you ask before looking at any code?

*Full answer: (1) "Broken how?" -- wrong results? no results? slow? error message? crashes? Each means a completely different class of bug and a different investigation path. (2) "When does it happen -- always, or only sometimes?" -- always means deterministic (logic or configuration bug); sometimes means intermittent (race condition, load-dependent, data-specific). (3) "Since when?" -- if it started after a specific deploy, start there; if it has always been broken, the bug was introduced when the feature was written and has been silently wrong since. Without answers to these three, any code you read is noise. You don't know what you're looking for.*

**Q2.** A colleague says "I fixed the bug by restarting the service." Is this a fix? What would you do next?

*Full answer: No, a restart is a mitigation, not a fix. A restart clears accumulated state. This tells you the bug is state-related -- something built up in memory, in an open connection pool, in a cache, or in a goroutine/thread that was not properly cleaned up. The restart did not change any code. The root cause is still in the code. When the service runs long enough, the state will accumulate again and the bug will return. Next steps: (1) monitor memory and connection counts over time to see what grows, (2) take a heap dump before the next restart to capture the accumulated state, (3) check for obvious leaks: unclosed connections, unbounded caches, goroutines/threads that loop without exit. The restart bought time. The investigation is still not done.*

**Q3.** You are debugging and you have 3 theories. Theory A is 70% likely but takes 2 hours to test. Theory B is 20% likely but takes 10 minutes to test. Theory C is 10% likely and takes 5 minutes. In what order do you test them?

*Full answer: Test B then C then A. Here is why: B + C together take 15 minutes and together have a 30% chance of being correct. If either B or C is correct, you found the bug in 15 minutes instead of 2 hours. If both B and C are ruled out (70% likely), you then test A knowing it is the only remaining hypothesis. Ruling out B and C also sharpens A: you now know the bug is NOT a cache issue or NOT a timeout, which may help you narrow where in A to look. The general rule is: among the plausible hypotheses, test the most testable ones first, not just the most likely one. "Most testable" means: cheapest to set up, fastest to run, gives a clear yes/no answer. This strategy is called "cheap tests first" and it minimizes expected debugging time.*

**Q4.** You have been debugging for 4 hours with no progress. What do you do?

*Full answer: Stop, step away for 15 minutes, then write down two lists. List 1: everything you KNOW is true (confirmed by data, not by assumption). List 2: everything you have TRIED and what result it produced. This forces clarity. Most 4-hour debugging blocks are caused by one of two things: (a) you have been testing the same hypothesis in different ways without getting a clean negative result, meaning your reproduction is not reliable or your test does not actually test what you think it does. (b) The real cause is something you have not considered -- your hypothesis list is incomplete. Sharing both lists with one other engineer for 10 minutes almost always breaks the block. Fresh eyes are not smarter; they just don't have your false assumptions. The other person will almost immediately say "wait, what about X?" and X will be the thing you never considered. This is why pair debugging on hard bugs is more efficient, not less.*

**Q5.** Why is "it works on my machine" so common, and what does it tell you about the bug?

*Full answer: "It works on my machine" is one of the most informative debugging clues you can get. It tells you precisely this: the bug is triggered by a condition that exists in one environment but not the other. Your job is to enumerate the differences between environments and find which one matters. Common differences to check: (1) Data -- production has millions of rows; your machine has hundreds. Bugs that require large datasets or specific data patterns are invisible locally. (2) Concurrency -- production has 500 concurrent users; your machine has 1. Race conditions are invisible in single-threaded testing. (3) Configuration -- production uses different env vars, feature flags, external service endpoints, or TLS certificates. (4) OS/dependency versions -- a bug in a specific version of a library, or a Linux-only vs macOS difference in system behavior. (5) Network -- production services communicate over a network with real latency; locally everything is loopback (0ms). Bugs that depend on timeout timing are invisible locally. Systematically compare the environments on each dimension until you find the one that matters.*

---

## Part 2: The 5-Step Debugging Framework

This framework works for every class of bug: logic errors, race conditions, performance problems, and distributed system failures. The steps always apply in this order.

```
  +-------+-------------------+------------------------------------+
  | Step  | Name              | What it means                      |
  +-------+-------------------+------------------------------------+
  |   1   | DEFINE            | Write down what is actually        |
  |       |                   | happening vs what should happen.   |
  |       |                   | Must be specific. No theories yet. |
  +-------+-------------------+------------------------------------+
  |   2   | REPRODUCE         | Make the bug happen on demand.     |
  |       |                   | Do not fix until you can reproduce.|
  +-------+-------------------+------------------------------------+
  |   3   | ISOLATE           | Binary search the search space.    |
  |       |                   | Cut the problem in half each time. |
  +-------+-------------------+------------------------------------+
  |   4   | HYPOTHESIZE       | One theory. One test. One change.  |
  |       |                   | Observe the result. Update theory. |
  +-------+-------------------+------------------------------------+
  |   5   | FIX + VERIFY      | Ship the fix. Verify with the      |
  |       |                   | reproduction case. Add a test.     |
  +-------+-------------------+------------------------------------+
```

---

### Step 1: DEFINE -- What Exactly Is Wrong?

The most skipped step. Engineers jump to theories before they have a precise symptom. A vague symptom produces vague hypotheses which produce wasted time.

**The bug definition template:**
```
  BUG STATEMENT TEMPLATE:

  WHAT IS HAPPENING:
  [Specific observable behavior -- no theory, just observation]
  Example: "The checkout API returns HTTP 503 for approximately
           12% of requests."

  WHAT SHOULD HAPPEN:
  [Expected behavior]
  Example: "The checkout API should return HTTP 200 for all
           valid requests."

  WHEN DOES IT HAPPEN:
  [Conditions: always? only under load? specific time? specific user?]
  Example: "Only between 5 PM and 7 PM on weekdays. Not
           reproducible at other times at normal load."

  SINCE WHEN:
  [When did it start? Was there a deploy?]
  Example: "Started Tuesday after the v2.3.2 deploy."

  IMPACT:
  [Users affected, revenue, severity]
  Example: "~$40K/day in abandoned carts. 12% of checkout
           attempts failing."

  WHAT HAS BEEN TRIED:
  [Honest list of what was already attempted]
  Example: "Rolled back the CDN config change -- no effect.
           Restarted 2 pods -- error rate unchanged."
```

**Why this matters:** Without a precise bug statement, two engineers working on the same bug will investigate different problems. With it, everyone starts from the same place.

---

### Step 2: REPRODUCE -- Get a Reliable Test

```
  WHY REPRODUCTION FIRST (before any code change):

  WITH REPRODUCTION:
  - You can test theories in 5 minutes, not 5 days
  - You can verify the fix before shipping
  - You can write a regression test so the bug cannot
    silently return
  - You KNOW you fixed it (vs. "it seems better")

  WITHOUT REPRODUCTION:
  - Every theory requires a production deploy to test
  - You cannot verify the fix
  - "Fixed" = "we haven't seen it in 3 days"
  - The bug returns from the same root cause 2 months later

  THE REPRODUCTION RULE:
  If you cannot reproduce it, you cannot fix it.
  You can only hope it goes away.
  Hoping is not engineering.
```

**Types of reproduction by difficulty:**

```
  EASIEST: deterministic bugs
  "Run this specific input and it always fails."
  Test case writes itself.

  MEDIUM: load-dependent bugs
  "Fails at > 400 concurrent users."
  Reproduction: write a load test with 500 concurrent users.

  HARD: time-dependent bugs
  "Fails on the first request after 30 minutes of inactivity."
  Reproduction: wait 30 minutes, then make a request.
  (Often a connection timeout or session expiry bug.)

  VERY HARD: race conditions
  "Fails occasionally, cannot predict when."
  Reproduction techniques:
  - Increase concurrency until failure rate is measurable
  - Add artificial delays to make the race window larger
  - Use thread sanitizer / race detector tools
  - Add logging around the suspected critical section

  INTERMITTENT: the hardest class
  Covered in Part 7.
```

---

### Step 3: ISOLATE -- Binary Search the Search Space

Binary search is not just for sorted arrays. It is the fundamental strategy for finding anything in a large space.

**Binary search on a commit history:**

```
  SCENARIO: A regression was introduced sometime in the
            last 100 commits. You don't know which one.

  NAIVE APPROACH: Read all 100 commits. Try to guess.
  Time: hours.

  BINARY SEARCH APPROACH:
  1. The bug exists in commit 100. Does it exist in commit 50?
     Test commit 50.
  2. If YES (bug in 50): narrow to commits 1-50. Test commit 25.
  3. If NO (no bug in 50): narrow to commits 51-100. Test commit 75.
  ...continue...

  Result: 7 tests to find the bug in 100 commits.
  (log2(100) = 6.6, so ~7 tests)

  In git this is: git bisect start
                  git bisect bad HEAD
                  git bisect good [last known good commit]
                  [git bisect run ./test.sh]  # automated
```

**Binary search on a codebase:**

```
  SCENARIO: A function returns the wrong value. You don't
            know where in 500 lines of logic the error is.

  BINARY SEARCH APPROACH:
  Add a print/log at the midpoint of the function:
  "At line 250: value is X"

  Is X correct or wrong?
  If WRONG: bug is in lines 1-250.
  If CORRECT: bug is in lines 251-500.

  Repeat on the half that contains the bug.
  ~9 iterations to find a bug in 500 lines of code.
```

**Binary search on a distributed trace:**

```
  SCENARIO: A request takes 3,200ms. It touches 6 services.

  Service A (auth) --> Service B (cart) --> Service C (product)
  --> Service D (pricing) --> Service E (tax) --> Service F (checkout)

  BINARY SEARCH APPROACH:
  Check the midpoint: what is the cumulative time when
  the request leaves Service C?

  T=45ms? Bug is in D, E, or F.
  T=2,800ms? Bug is in A, B, or C.

  Repeat. 3 checks to find which service is slow in 6.
```

---

### Step 4: HYPOTHESIZE -- One Theory, One Test, One Change

```
  THE HYPOTHESIS FORMAT:

  "I believe the slow checkout is caused by [specific thing].
   If I am right, then [specific observable consequence]
   will happen when I [specific test action].
   If I am wrong, I will see [alternative result] instead."

  EXAMPLE:
  "I believe the slow checkout is caused by the N+1 query
   on product_data. If I am right, then adding an
   EXPLAIN ANALYZE to that query will show N queries
   where N = number of cart items. If I am wrong, the
   query plan will show a single JOIN or index scan."

  WHY THE FORMAT MATTERS:
  If you cannot complete the "if I am wrong" sentence,
  your hypothesis is not testable. It is unfalsifiable.
  Unfalsifiable hypotheses are not hypotheses -- they
  are guesses dressed up as hypotheses.
```

---

### Step 5: FIX + VERIFY -- Never Ship a Fix Without a Test

```
  THE INCOMPLETE FIX (what most engineers do):
  1. Find the bug
  2. Fix the code
  3. Run in production
  4. Monitor for 30 minutes
  5. Declare victory

  THE COMPLETE FIX (what staff engineers do):
  1. Find the bug
  2. Write a test that FAILS because of the bug
  3. Fix the code
  4. Confirm the test now passes
  5. Run in production
  6. Confirm the reproduction case also passes
  7. Add the test to CI so the bug cannot silently return

  WHY THE REGRESSION TEST MATTERS:
  Without a regression test, the same bug can be silently
  reintroduced by any engineer in 6 months. With it, the
  CI pipeline catches the regression before it ships.

  The regression test is not for you. It is for the next
  engineer who accidentally reintroduces the bug at 2 AM
  on a Friday 8 months from now.
```

---

### Brainstorming Questions -- Part 2: The 5-Step Framework

**Q1.** You are debugging a production issue and your manager says "just fix it, we don't need a reproduction first." How do you respond, and why is your manager wrong?

*Full answer: The right response is to explain the tradeoff, not just comply. Say: "Skipping reproduction means we ship a change we cannot verify. If it does not fix the bug, we will not know that until users report it again. We will have wasted a deploy cycle and possibly introduced a new issue. Getting a reproduction takes 30-60 minutes but lets us verify the fix in 5 minutes instead of waiting 24-48 hours for the bug to recur. I can start the reproduction in parallel while reading the code -- they are not sequential steps." If the manager insists because users are actively impacted, the right answer is different: mitigate first (rollback or feature flag), then get a reproduction. Never skip reproduction entirely -- that means you can never verify the fix.*

**Q2.** A bug exists somewhere in a 200-line function. You have no idea where. Without reading every line, how do you find it in under 10 minutes?

*Full answer: Add a log or print statement at the exact midpoint (line 100) that prints the value you care about. Run the reproduction. Is the value correct at line 100? If yes: the bug is in lines 101-200 (the midpoint is before the bug). If no: the bug is in lines 1-100 (the bug happened before the midpoint). Now take the half that contains the bug and add a log at its midpoint. Repeat. After 8 iterations (log2(200) ≈ 7.6), you have narrowed to a single line. This is binary search on code. It feels slower than "just reading the code" but it is strictly faster for any function over ~30 lines, because reading 200 lines to understand logic takes much longer than 8 targeted log insertions. The key insight: you do not need to understand the code to find where a value becomes wrong. You only need to know whether the value at each midpoint is correct or incorrect.*

**Q3.** After you ship a fix, how do you know you actually fixed the bug and did not just suppress the symptom?

*Full answer: The reproduction case must pass -- not "I haven't seen the error in 30 minutes of monitoring." Monitoring tells you the symptom is not currently visible. The reproduction case tells you the specific conditions that caused the bug no longer produce the bug. These are different. A fix that suppresses a symptom (e.g., catching an exception and returning an empty result instead of an error) will pass the monitoring check but fail the reproduction case. The correct order: (1) write a test that fails because of the bug, (2) ship the fix, (3) confirm the test now passes, (4) add the test to CI so it runs on every future deploy. If you cannot write a test that fails because of the bug, you do not understand the bug well enough to fix it reliably.*

**Q4.** You have been told "this bug is too intermittent to reproduce." Is that a valid reason to stop investigating? What do you do instead?

*Full answer: No. "Too intermittent to reproduce" means "we don't know the trigger conditions yet." No bug fires randomly. Every intermittent bug has a pattern. The investigation shifts from "fix the bug" to "find the trigger condition." Approach: (1) Instrument the system to log maximum context every time the bug occurs: timestamp, request parameters, system load, which pod/instance, active user count, recent cache TTL expirations, recent deploys. (2) Wait for the next occurrence and read that context data. (3) Collect 5-10 occurrences and look for what they have in common. The trigger condition will appear in that comparison. Once you have the trigger condition, you can write a reproduction. The ticket stays open with a note: "Trigger unknown. On next occurrence, log: [specific fields]. Will update when pattern found." Closing intermittent bugs as "cannot reproduce" is how bugs fester for years.*

**Q5.** The bug is fixed. What is the minimum acceptable set of artifacts before you close the ticket?

*Full answer: Three things: (1) The fix itself -- code change merged and deployed. (2) A regression test that reproduces the bug and now passes. This test must be in CI so it runs on every future PR. This is the thing that prevents the same bug from being silently reintroduced in 6 months when someone changes nearby code without realizing the invariant they are breaking. (3) A one-paragraph explanation in the ticket or post-mortem: what caused it, how to recognize it in the future, and what the systemic fix is (if applicable). Without the regression test: you fixed it once. With it: you fixed it for the lifetime of the codebase. A fix without a test is a fix with an expiration date.*

---

## Part 2b: Reading Error Messages and Stack Traces

This is the skill no one explicitly teaches. Most engineers read stack traces the wrong way — they look at the top line (the error) and start fixing from there. The top line is almost never where the bug is.

### The Anatomy of a Stack Trace

A stack trace is a snapshot of every function call that was active when the crash or exception happened. It reads from the bottom (the first call) to the top (the most recent call where the error was thrown).

```
  STACK TRACE READING DIRECTION:

  Bottom = where execution started (main, request handler)
  Top    = where the exception was thrown

  THE BUG IS ALMOST NEVER AT THE TOP.
  The top is where the system gave up.
  The bug is in the middle -- in the code YOUR TEAM wrote,
  somewhere between the bottom (framework) and the top
  (the library that threw the error).

  THE RULE:
  Scan down from the top until you see the FIRST LINE
  that is YOUR CODE (not a library or framework).
  That is your entry point for investigation.
```

---

### Reading a Java Stack Trace (Worked Example)

```java
  Exception in thread "main" java.lang.NullPointerException
      at java.util.Objects.requireNonNull(Objects.java:246)     // <-- top: library code
      at java.util.ArrayList.<init>(ArrayList.java:153)          // <-- library
      at java.util.ArrayList.<init>(ArrayList.java:126)          // <-- library
      at com.myapp.cart.CartService.buildItemList(CartService.java:87)  // <-- YOUR CODE
      at com.myapp.cart.CartService.getCartForUser(CartService.java:52) // <-- YOUR CODE
      at com.myapp.checkout.CheckoutController.processOrder(CheckoutController.java:34) // <-- entry
      at sun.reflect.NativeMethodAccessorImpl.invoke0(NativeMethod)     // <-- framework
      at org.springframework.web.servlet.FrameworkServlet.service(FrameworkServlet.java:897) // framework
```

**How to read this:**

```
  Step 1: Read the first line.
  "NullPointerException" -- something is null that shouldn't be.
  This tells you the CLASS of error, not the cause.
  Don't start fixing here.

  Step 2: Scan down to the first line of YOUR code.
  "com.myapp.cart.CartService.buildItemList(CartService.java:87)"
  This is where the NPE propagated INTO your code.
  
  But actually: go one line lower.
  "CartService.getCartForUser(CartService.java:52)"
  This is what CALLED buildItemList.
  The bug is often in the CALLER, not where the exception fired.

  Step 3: Open CartService.java, line 87.
  Look at what could be null.
  Look at what line 52 is passing to it.

  WHAT YOU FIND (CartService.java:52):
    public Cart getCartForUser(String userId) {
      User user = userRepo.findById(userId);  // can return null!
      List<CartItem> items = buildItemList(user.getCartId()); // NPE if user is null
      ...
    }
  
  THE BUG: userRepo.findById() can return null when the userId
  does not exist. The code does not check for null before
  calling user.getCartId().

  FIX:
    User user = userRepo.findById(userId);
    if (user == null) {
      return Cart.empty();  // or throw a meaningful exception
    }
    List<CartItem> items = buildItemList(user.getCartId());
```

---

### Reading a Python Traceback (Worked Example)

Python tracebacks read top-to-bottom (unlike Java). The LAST line is the error. Your code is usually a few frames above the last line.

```python
  Traceback (most recent call last):
    File "app/api/orders.py", line 43, in create_order    # YOUR CODE (entry point)
      cart = CartService.load_cart(user_id)
    File "app/services/cart.py", line 78, in load_cart    # YOUR CODE (drill here)
      return redis_client.get(f"cart:{user_id}")
    File "lib/redis/client.py", line 234, in get          # LIBRARY
      return self._execute_command("GET", name)
    File "lib/redis/client.py", line 194, in _execute_command  # LIBRARY
      raise ConnectionError(f"Redis connection failed: {e}")
  redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379. Connection refused.
```

**How to read this:**

```
  LAST LINE: ConnectionError -- Redis connection refused.
  This is the symptom, not the cause.

  SCAN UP from the bottom to find YOUR code:
  "app/services/cart.py, line 78, in load_cart"
  --> redis_client.get(f"cart:{user_id}")
  This is where your code is calling Redis.

  WHAT THE STACK TRACE TELLS YOU:
  - Your code is trying to connect to Redis at localhost:6379.
  - Connection was refused (port not open / Redis not running).
  
  CHECK:
  redis-cli ping        # is Redis running?
  echo $REDIS_URL       # is the URL env var set correctly?
  
  MOST LIKELY CAUSE:
  - In development: Redis is not running locally.
  - In production: wrong Redis host in env vars.
    The service is pointing to localhost instead of
    the actual Redis instance (redis.internal:6379).
  
  FIX: set REDIS_URL=redis.internal:6379 in production env.
```

---

### Reading a Go Panic (Worked Example)

```
  goroutine 1 [running]:
  main.processPayment(...)
      /app/payment/processor.go:134 +0x19c          // YOUR CODE
  main.handleCheckout(0xc000112000, 0x7f...)
      /app/handlers/checkout.go:67 +0x248            // YOUR CODE
  net/http.HandlerFunc.ServeHTTP(...)
      /usr/local/go/src/net/http/server.go:2192      // STDLIB
  net/http.(*ServeMux).ServeHTTP(...)
      /usr/local/go/src/net/http/server.go:2731      // STDLIB
  
  panic: runtime error: index out of range [5] with length 3
```

**How to read this:**

```
  FIRST LINE OF PANIC:
  "index out of range [5] with length 3"
  -> Code tried to access index 5 of a slice with 3 elements.
  -> Off-by-one error or wrong assumption about slice length.

  WHERE IN YOUR CODE:
  payment/processor.go:134
  
  OPEN THAT LINE:
    func processPayment(items []LineItem) {
      // ... somewhere ...
      total := items[5].Price  // BUG: assumes slice has >=6 elements
    }
  
  WHY DID THIS NOT FAIL IN TESTS?
  Test data had 6+ items. Production cart had only 3.
  Tests didn't cover small cart sizes.
  
  FIX:
    if len(items) == 0 {
      return 0, ErrEmptyCart
    }
    // iterate, don't index with a hardcoded number
    for _, item := range items {
      total += item.Price
    }
```

---

### The Most Misleading Error Messages

Some errors sound like one thing but mean another. Memorize these.

```
  ERROR MESSAGE                      WHAT IT ACTUALLY MEANS
  +-----------------------------+    +--------------------------------+
  | "Too many open files"       | -> Too many file descriptors open. |
  |                             |    Could be: actual files, sockets,|
  |                             |    pipes. NOT just network sockets. |
  +-----------------------------+    +--------------------------------+
  | "Connection refused"        | -> The target port is not open.    |
  |                             |    Could be: wrong host, wrong port,|
  |                             |    service crashed, firewall.       |
  +-----------------------------+    +--------------------------------+
  | "Out of memory"             | -> The process asked for more RAM   |
  |                             |    than the OS would give it.      |
  |                             |    NOT always a memory leak. Could  |
  |                             |    be: single large allocation,     |
  |                             |    container memory limit hit.      |
  +-----------------------------+    +--------------------------------+
  | "Segmentation fault"        | -> Process tried to access memory   |
  |                             |    it does not own. In native code: |
  |                             |    null pointer, buffer overflow.   |
  |                             |    In managed code: extremely rare, |
  |                             |    usually a native library bug.    |
  +-----------------------------+    +--------------------------------+
  | "Deadlock detected"         | -> Two or more transactions each    |
  | (PostgreSQL)                |    waiting for a lock held by the  |
  |                             |    other. Postgres kills one to     |
  |                             |    break the cycle. NOT always the  |
  |                             |    query shown in the error that    |
  |                             |    caused it -- look at all active  |
  |                             |    transactions at that moment.     |
  +-----------------------------+    +--------------------------------+
  | "Timeout expired"           | -> A time limit was hit. Could be: |
  |                             |    connection timeout, query        |
  |                             |    timeout, request timeout. The    |
  |                             |    question is: what was TOO SLOW,  |
  |                             |    not why did the timeout fire.    |
  +-----------------------------+    +--------------------------------+
  | "ECONNRESET"                | -> The remote end closed the       |
  |                             |    connection while you were using  |
  |                             |    it. Common causes: server        |
  |                             |    restart, idle timeout on a       |
  |                             |    connection pool, load balancer   |
  |                             |    closing idle connections.        |
  +-----------------------------+    +--------------------------------+
```

---

### Brainstorming Questions -- Part 2b: Stack Traces

**Q1.** You see this error: `NullPointerException at com.google.guava.collect.ImmutableList.of(ImmutableList.java:79)`. Should you look at Guava's source code? Where should you actually look?

*Full answer: No. Guava is a library -- it is not the source of the bug. ImmutableList.of() throws NPE when you pass null to it. The real bug is in YOUR code that is passing null. Scan down the stack trace from that line until you find the first line in a package you own (e.g., com.mycompany.*). That line in your code is passing null where it should not be. Fix: find why that value is null before it reaches Guava, and either guard against null or fix the upstream code that produces it.*

**Q2.** A Python traceback ends with `KeyError: 'user_id'`. Your first instinct is to add a `.get('user_id', None)` to silence the error. Why is this usually wrong?

*Full answer: `.get('user_id', None)` converts a loud failure (KeyError with a clear message) into a silent failure (returns None, which then causes a harder-to-debug AttributeError or incorrect behavior somewhere downstream). The right approach: the KeyError tells you that the dictionary does not have the key `user_id`. Ask: why not? Is the data coming from an API that changed its schema? Is there a code path that builds the dictionary without setting `user_id`? Fix the upstream code that is producing an incomplete dictionary, not the downstream code that correctly expects the key to exist.*

**Q3.** A Go panic says `goroutine 12345 [chan send (nil chan)]`. What does this mean, and what is the fix?

*Full answer: Code is trying to send a value on a channel that was never initialized (is nil). In Go: `var ch chan int` declares a nil channel. Sending to a nil channel blocks forever, but when the goroutine is forced to terminate (e.g., context cancellation), the runtime panics. Fix: initialize the channel before use: `ch := make(chan int, 1)`. The root cause is usually that a channel field in a struct was declared but `make()` was never called, often because the struct was created with a zero-value literal instead of a constructor.*

---

## Part 3: The 5 Classes of Bugs

Every bug belongs to one of five classes. Each class has a characteristic signature in the symptoms, and each requires a different investigation strategy. Knowing which class you are in tells you immediately which tools to reach for.

---

### Class 1: Logic Bugs

**What they look like:** Wrong output. Deterministic. Always reproducible. Same input always produces the same wrong output.

```
  SIGNATURE:
  - Reproducible 100% of the time with specific input
  - Wrong output, not no output
  - Not timing-dependent
  - Not load-dependent

  EXAMPLES:
  - Function returns incorrect total because of integer overflow
  - Sort returns wrong order because comparator is incorrect
  - Date calculation off by one day because of timezone
  - Business rule applied to wrong tier of users

  INVESTIGATION STRATEGY:
  1. Find the simplest input that produces wrong output
  2. Binary search the code path
  3. Add assertions at each step to find where the value
     becomes wrong
  4. The bug is at the step where the value transitions
     from correct to incorrect
```

**Real example: The Leap Year Bug**

```
  BUG: "User subscription expires 1 day early in leap years."

  DEFINE:
  Expected: subscription expires on March 1 for users who
  subscribed on March 1 of a leap year.
  Actual: subscription expires on Feb 29 (doesn't exist in
  non-leap years), system throws an error and expires early.

  ROOT CAUSE:
  Code: expiry_date = subscription_start + timedelta(days=365)
  Feb 29, 2024 + 365 days = Feb 28, 2025 (not March 1).
  Should use: relativedelta(years=1) which accounts for
  leap years by adding 1 year, not 365 days.

  FIX: Replace timedelta(days=365) with relativedelta(years=1)

  LESSON: Date arithmetic is a class of logic bugs.
  Never add "365 days" to mean "1 year."
  Never add "30 days" to mean "1 month."
  Use calendar-aware date arithmetic libraries.
```

---

### Class 2: Concurrency Bugs

**What they look like:** Intermittent. Not reproducible with single thread. Appears under load. Often manifests as wrong data, not a crash.

```
  SIGNATURE:
  - Works fine with 1 user, breaks with 100
  - Inconsistent results for the same input
  - Sometimes correct, sometimes wrong (non-deterministic)
  - Disappears when you add logging (Heisenbug)

  EXAMPLES:
  - Two threads both read a counter (value=5), both increment,
    both write 6 back. Expected: 7. Actual: 6. Lost update.
  - Deadlock: Thread A holds lock X, waits for Y.
    Thread B holds lock Y, waits for X. Both stuck forever.
  - Race condition: check-then-act pattern where the check
    becomes stale by the time the act happens.

  INVESTIGATION STRATEGY:
  1. Increase concurrency until you get reliable failures
  2. Use race detector tools (Go: -race, Java: ThreadSanitizer,
     C: AddressSanitizer)
  3. Add artificial delays around the suspected critical section
     to widen the race window
  4. Look for any shared mutable state accessed without a lock
```

**The Lost Update diagram:**

```
  THREAD A           SHARED STATE         THREAD B
                     counter = 5
  read: value=5                           read: value=5
  compute: 5+1=6                          compute: 5+1=6
  write: 6                                write: 6
                     counter = 6
                     (should be 7!)

  Fix: use atomic operation or mutex around read-compute-write.
  Redis: INCR is atomic at the machine instruction level.
  Database: UPDATE counter = counter + 1 (atomic in SQL).
  Go: sync/atomic.AddInt64(&counter, 1)
```

**The Heisenbug:** A bug that disappears when you try to observe it. Usually a race condition where adding a log statement changes the timing enough that the race no longer occurs. Diagnosis: if your bug disappears when you add logging, it is a race condition. The log statement is serializing execution that was previously concurrent.

**The Deadlock -- a full worked example:**

```
  SCENARIO: A payment service occasionally hangs forever.
  No errors. No timeouts. Just: the request never returns.
  CPU: 0%. Memory: normal. The service appears "healthy."

  INVESTIGATION:
  1. Check what threads are blocked:
     # Java
     kill -3 <PID>   # sends SIGQUIT, dumps thread state to stdout
     # or: jstack <PID> > thread_dump.txt
     
     # Go
     curl http://localhost:6060/debug/pprof/goroutine?debug=2
     
     # Python
     import signal, traceback
     signal.signal(signal.SIGUSR1, lambda s,f: traceback.print_stack())
  
  2. Thread dump output shows:
  
     Thread "payment-worker-1": BLOCKED
       waiting to acquire lock on PaymentService.accountLock
       held by Thread "payment-worker-2"
     
     Thread "payment-worker-2": BLOCKED
       waiting to acquire lock on PaymentService.ledgerLock
       held by Thread "payment-worker-1"
  
  DEADLOCK DIAGRAM:
  
  Worker 1                  Worker 2
  locks accountLock         locks ledgerLock
  waits for ledgerLock      waits for accountLock
        |                         |
        +---- waiting forever ----+
  
  THE CODE:
  // Worker 1 (transfer money)
  synchronized(accountLock) {           // grabs account lock first
    synchronized(ledgerLock) {           // then tries ledger lock
      account.debit(amount);
      ledger.record(amount);
    }
  }
  
  // Worker 2 (generate report)
  synchronized(ledgerLock) {             // grabs ledger lock first
    synchronized(accountLock) {          // then tries account lock
      report.add(ledger.entries(), account.balance());
    }
  }
  
  LOCK ORDER INVERSION: the two workers grab the same two locks
  in opposite order. When they both start at the same moment,
  each gets the first lock and blocks waiting for the second.

  FIX: Establish a GLOBAL LOCK ORDERING.
  Always acquire locks in the same order everywhere.
  Convention: alphabetical or by a defined priority.
  
  // Both workers now grab accountLock first, then ledgerLock.
  synchronized(accountLock) {    // always first
    synchronized(ledgerLock) {   // always second
      // ... work ...
    }
  }
  
  With consistent ordering: Worker 2 waits for Worker 1 to
  release accountLock. No circular wait. No deadlock.
```

---

### Class 3: Memory Bugs

**What they look like:** Service slowly grows in memory until it crashes or is OOM-killed. Or: occasional crashes with memory corruption errors.

```
  SIGNATURE:
  Memory leak:
  - Service memory grows over hours/days, never drops
  - Restarting the service fixes it temporarily
  - Memory growth correlates with specific operation

  Memory corruption:
  - Random crashes, often in unrelated code paths
  - Segfaults, access violations
  - Values change unexpectedly

  INVESTIGATION STRATEGY (memory leak):
  1. Graph memory usage over time. Is the growth linear?
     Correlated with traffic? Or a fixed rate?
  2. Take two heap dumps: one now, one 10 minutes later.
     Compare: what grew?
  3. Common causes: event listeners not removed, cache with
     no eviction policy, objects kept alive by hidden references,
     goroutines/threads that never terminate

  TOOLS:
  Java:    heap dump + Eclipse MAT, or JProfiler
  Node.js: --inspect + Chrome heap snapshot
  Go:      pprof (net/http/pprof)
  Python:  tracemalloc, memory_profiler
```

**Real example pattern -- the event listener leak:**

```
  CODE (JavaScript, simplified):
  function setupDashboard(userId) {
    const socket = connect(userId);
    socket.on('data', handleData);
    // When user navigates away, socket is not disconnected.
    // handleData holds a reference to the DOM element.
    // DOM element holds a reference to handleData.
    // Circular reference: neither gets garbage collected.
  }

  SYMPTOM: Browser tab memory grows from 50MB to 400MB
           after using the dashboard for 4 hours.

  FIX:
  function teardownDashboard(userId) {
    socket.off('data', handleData);  // remove listener
    socket.disconnect();
  }
  // Call teardownDashboard when user navigates away.
```

---

### Class 4: Performance Bugs

**What they look like:** Everything works correctly, but slowly. Not a crash, not wrong output -- just too slow.

```
  SIGNATURE:
  - Latency is higher than expected
  - CPU or memory higher than expected at given traffic
  - Degrades over time or under load

  TYPES:
  - Latency: slow response time (p99 spikes)
  - Throughput: cannot handle required requests/sec
  - CPU: CPU at 90%+ at normal traffic
  - Memory: memory growing or higher than expected

  INVESTIGATION ORDER:
  1. Profile FIRST. Never optimize without data.
     "The code is slow because of X" without profiling
     data is a guess. Optimizing the wrong thing wastes
     time and can make things worse.
  2. Find the hot path (where most time is spent)
  3. Understand WHY it is slow before changing it
  4. Make one change, measure, repeat
```

**The Performance Investigation Flow:**

```
  SLOW REQUEST
       |
       v
  Is it CPU-bound or I/O-bound?
       |
       +-- HIGH CPU: profile CPU
       |   --> Find the hot function
       |   --> Is it doing unnecessary work? (N+1, no cache)
       |   --> Is the algorithm wrong? (O(n^2) vs O(n log n))
       |
       +-- NORMAL CPU, HIGH LATENCY: I/O is the bottleneck
           --> Which I/O? (DB, network, disk, cache miss)
           --> Add timing to each I/O call
           --> Find the slow one
           --> Is it slow always or only sometimes?
               Always: query problem, missing index, bad network path
               Sometimes: contention, connection pool, retry storms
```

---

### Class 5: Distributed System Bugs

**What they look like:** Everything works on one machine. Breaks when multiple services or nodes are involved. Often related to ordering, consistency, partial failure, or network issues.

```
  SIGNATURE:
  - Works in local development, fails in staging/production
  - One node sees data that another node doesn't
  - System gets stuck in an inconsistent state
  - Timing-dependent behavior between services

  THE HARD PART: distributed bugs are invisible locally.
  A race condition between two services is not reproducible
  on a single machine. You need the distributed environment
  to see it.

  COMMON DISTRIBUTED BUG TYPES:
  +--------------------+------------------------------------+
  | Bug Type           | What Happens                       |
  +--------------------+------------------------------------+
  | Split brain        | Two nodes both think they are      |
  |                    | the leader. Both accept writes.    |
  |                    | Data diverges.                     |
  +--------------------+------------------------------------+
  | Stale cache        | Cache returns old value after      |
  |                    | database was updated. Reads and    |
  |                    | writes disagree.                   |
  +--------------------+------------------------------------+
  | Message ordering   | Service B processes message 2      |
  |                    | before message 1 because they      |
  |                    | arrived on different partitions.   |
  +--------------------+------------------------------------+
  | Partial failure    | 3 of 4 replicas acknowledge a      |
  |                    | write. The 4th does not. Client    |
  |                    | thinks write succeeded. Data lost  |
  |                    | when the 4th replica becomes the   |
  |                    | primary.                           |
  +--------------------+------------------------------------+
  | Clock skew         | Two services timestamp an event    |
  |                    | differently because their clocks   |
  |                    | differ by 200ms. Audit log shows   |
  |                    | effect before cause.               |
  +--------------------+------------------------------------+
```

---

### Brainstorming Questions -- Part 3: The 5 Classes

**Q1.** Your service works correctly in testing but produces wrong results in production for users in the UTC+5:30 timezone (India). Which class of bug is this, and what do you check first?

*Think about: Logic bug, specifically a timezone/date handling issue. Check: are dates being stored as UTC? Are they being converted to local time correctly? Is the timezone offset being applied correctly? Classic mistake: storing "current time" as local machine time (which in production is UTC) and displaying it without conversion.*

**Q2.** Your Redis counter for "active sessions" slowly drifts from reality. The database shows 1,000 active sessions. Redis shows 1,012. After a week it shows 1,087. Which class is this, and what are the two most likely causes?

*Think about: concurrency bug (lost decrement from a race condition) or logic bug (session expiry removes from DB but not Redis, or vice versa). Check: is the session increment and decrement always an atomic pair? What happens when a session expires vs when a user explicitly logs out?*

**Q3.** Your service's memory grows by approximately 50MB every day, regardless of traffic. Restarting the service always fixes it. Which class of bug is this, and what is your first investigation step?

*Think about: memory leak (Class 3). First step: take two heap dumps 10 minutes apart and compare what grew. If traffic is zero during those 10 minutes and memory still grows: it's a background task or timer leak, not a request-path leak.*

**Q4.** A payment service processes a charge successfully (returns 200) but the charge does not appear in the user's billing history. Which class of bug is this likely to be, and what specific thing do you check in the distributed system?

*Think about: distributed bug. Check: is the charge written to one service (payment processor) but not replicated to another (billing history service)? Is it a Kafka message that was produced but consumed in the wrong order? Is there a two-phase commit failure where the payment succeeded but the database write for the billing record failed and was not retried?*

**Q5.** You optimize a function from O(n²) to O(n log n). You expect 100x speedup. You measure and get only 3x speedup. Why might the optimization not deliver the expected improvement?

*Think about: Amdahl's Law. If the function you optimized was only 10% of the total request time, even making it infinitely fast only gives you 11% total improvement. The speedup is limited by the un-optimized 90%. This is why you must profile before optimizing -- you need to find the dominant bottleneck, not just an obvious inefficiency.*

---

## Part 3b: The Debugging Toolkit

These are the actual commands experienced engineers run. Most debugging guides explain concepts but never show the commands. This section fixes that.

---

### lsof -- "What files/connections does this process have open?"

```
  SYNTAX:
  lsof -p <PID>              # all open files for a process
  lsof -p <PID> | wc -l     # count of open file descriptors
  lsof -p <PID> -i           # only network connections
  lsof -i :8080              # who is listening on port 8080?
  lsof -u <username>         # all files opened by a user

  SAMPLE OUTPUT:
  COMMAND   PID    USER   FD   TYPE    DEVICE SIZE/OFF NODE NAME
  java     1234    app   cwd    DIR     253,0     4096  128 /app
  java     1234    app   txt    REG     253,0   123456 5432 /usr/bin/java
  java     1234    app    4u   IPv4   12345678      0t0  TCP app:38432->db:5432 (ESTABLISHED)
  java     1234    app    5u   IPv4   12345679      0t0  TCP app:38433->redis:6379 (ESTABLISHED)
  java     1234    app    6r   REG     253,0   1048576  789 /app/logs/app.log

  READING THIS:
  - "FD" column: 4u = file descriptor #4, open for reading+writing (u)
  - "TYPE" column: IPv4 = network socket, REG = regular file, DIR = directory
  - Last column: shows connections (host:port->host:port) or file paths

  USE CASE: "Too many open files" error
  
  STEP 1: How many FDs are open?
    lsof -p 1234 | wc -l
    Output: 4328    <-- getting close to the 4096 default limit
  
  STEP 2: What kind of FDs?
    lsof -p 1234 | awk '{print $5}' | sort | uniq -c | sort -rn
    Output:
    3891 REG      <-- 3,891 regular files open!
     425 IPv4     <-- 425 network connections
      12 DIR

  STEP 3: Which files?
    lsof -p 1234 | grep REG | head -20
    All pointing to /app/logs/users/*.log  <-- one per user, never closed
```

---

### netstat / ss -- "What network connections exist?"

```
  SYNTAX (prefer ss on modern Linux, faster than netstat):
  ss -tlnp          # listening TCP sockets + which process
  ss -tnp           # all TCP connections + process
  ss -s             # summary statistics
  netstat -an       # all connections (old way)

  SAMPLE OUTPUT (ss -tnp):
  State    Recv-Q Send-Q  Local Address:Port  Peer Address:Port  Process
  LISTEN   0      128     0.0.0.0:8080        0.0.0.0:*          pid=1234,app
  ESTAB    0      0       10.0.1.5:42156      10.0.0.1:5432      pid=1234,app
  ESTAB    0      0       10.0.1.5:42157      10.0.0.1:5432      pid=1234,app
  TIME_WAIT 0     0       10.0.1.5:42001      10.0.0.1:80        pid=-

  READING CONNECTION STATES:
  LISTEN    = waiting for incoming connections (normal for servers)
  ESTAB     = active connection (normal)
  TIME_WAIT = connection just closed, OS holding port briefly (normal)
              Too many TIME_WAIT = closing connections very frequently
              (connection pool not being reused, or too aggressive timeouts)
  CLOSE_WAIT = remote end closed connection, local end hasn't noticed yet
              Too many CLOSE_WAIT = BUG. Local code is not closing sockets
              after the remote end closes. Connection leak.

  USE CASE: "Connection pool exhausted" bug
  
  ss -tnp | grep 5432 | wc -l   # count connections to Postgres
  Output: 52
  
  Your pool max is 50. You have 52 connections. 2 leaked connections
  are keeping the pool full. Find which transactions are not closing.
```

---

### top / htop -- "What is consuming CPU and memory right now?"

```
  SYNTAX:
  top             # all processes, live updating
  top -p 1234    # only process 1234
  htop           # prettier version, mouse-friendly

  KEY COLUMNS IN TOP:
  PID    -- process ID
  %CPU   -- CPU usage (>100% means using multiple cores)
  %MEM   -- memory percentage of total RAM
  RES    -- resident memory (actual RAM used, in KB)
  S      -- process state: R=running, S=sleeping, D=disk wait, Z=zombie

  STATE "D" (disk wait, uninterruptible sleep):
  A process in D state is waiting for disk I/O.
  It cannot be killed. It is stuck waiting for the disk.
  Many processes in D state = disk I/O bottleneck.
  Check: iostat -x 1

  ZOMBIE PROCESS (state Z):
  A zombie is a process that has finished but its parent
  has not called wait() to collect the exit code.
  Zombies consume no CPU or memory but do consume a PID.
  If you have thousands of zombies: the parent process
  has a bug -- it is spawning children without waiting
  for them to finish.
  Check: ps aux | grep Z
  Fix: in the parent process, call waitpid() after fork().

  USE CASE: "High CPU, don't know why"
  
  top output shows:
  PID   %CPU  %MEM  COMMAND
  1234  98.2   4.3  java
  
  Next: find WHICH THREAD inside java is using 98% CPU.
  
  # Step 1: find thread IDs of the java process
  ps -eLf | grep 1234
  # Look for threads with high CPU
  
  # Step 2: get stack trace of the hot thread
  jstack 1234 | grep -A 30 "nid=0x<thread_hex>"
  # The stack trace of the hot thread shows what code is spinning.
```

---

### strace -- "What system calls is this process making?"

```
  SYNTAX:
  strace -p <PID>              # attach to running process
  strace -p <PID> -e trace=network  # only network syscalls
  strace -p <PID> -e trace=file     # only file syscalls
  strace -c -p <PID>           # count syscalls (summary mode)
  
  WARNING: strace adds overhead (~50-100x slower for I/O-heavy code).
  Use in production only on a single instance, briefly.

  SAMPLE OUTPUT:
  openat(AT_FDCWD, "/app/logs/user_12345.log", O_RDWR|O_CREAT) = 7
  read(7, "", 4096)                                              = 0
  write(7, "2024-01-15 processing...\n", 25)                    = 25
  openat(AT_FDCWD, "/app/logs/user_12346.log", O_RDWR|O_CREAT) = 8
  read(8, "", 4096)                                              = 0
  write(8, "2024-01-15 processing...\n", 25)                    = 25
  openat(AT_FDCWD, "/app/logs/user_12347.log", O_RDWR|O_CREAT) = 9
  ...

  WHAT THIS SHOWS:
  The process is opening a new file for every user.
  File descriptors: 7, 8, 9 ... going up. Never closed.
  This is the LinkedIn "too many open files" bug in action.
  
  strace -c summary mode is safer for production:
  % time   seconds  usecs/call  calls  syscall
  85.23    0.432145        432   1000  openat       <-- opening 1000 files per second!
   8.12    0.041234         41   1000  write
   6.65    0.033789         33   1000  read
   0.00    0.000000          0      0  close        <-- ZERO closes! Bug confirmed.
```

---

### vmstat -- "Is the system under memory pressure?"

```
  SYNTAX:
  vmstat 1 10    # print every 1 second, 10 times

  SAMPLE OUTPUT:
  procs  memory           swap     io    system   cpu
  r  b   swpd   free  buff  cache  si  so   bi  bo  in  cs  us sy id wa
  2  0      0 1234M  234M  5678M   0   0    1   5  500 800  45  5 50  0
  4  3      0  234M  234M  5678M   0  50  100 500  800 1200 85 10  0  5

  KEY COLUMNS:
  b   = processes in uninterruptible wait (disk I/O wait)
        If b > 0 frequently: disk is the bottleneck
  si/so = swap in/swap out (memory swapping to disk)
          si or so > 0: system is running out of RAM
          Swapping makes everything 100-1000x slower
  wa  = CPU wait percentage (waiting for I/O)
        wa > 10%: I/O is limiting performance
  us/sy = user/system CPU
          sy > 20%: system calls are expensive (lots of I/O or networking)

  READING THE SAMPLE:
  Second row: b=3 (3 processes waiting on disk), wa=5%
  io.bi=100, io.bo=500: significant disk activity
  This system is doing heavy disk I/O. If this correlates
  with your slowness: disk is the bottleneck.
```

---

### Brainstorming Questions -- Part 3b: The Toolkit

**Q1.** Your service has 847 connections to PostgreSQL but your connection pool max is 100. `ss -tnp | grep 5432 | wc -l` confirms 847. Where do you look next?

*Full answer: 847 connections to Postgres with a pool max of 100 means you have connections that exist outside the pool, or the pool is not enforcing its limit properly. Check: (1) Are multiple instances of your service running? 847 / 8 instances = ~106 connections per instance, which slightly exceeds 100 per instance. If you have 8 instances each at max pool: 800 connections, plus 47 leaked connections. (2) Are there direct connections bypassing the pool? Grep your codebase for `db.connect()` or `DriverManager.getConnection()` called directly. (3) Is the pool configured correctly? Pool configs are often in environment variables that differ between environments. Check `POOL_SIZE` env var.*

**Q2.** `vmstat 1` shows `si=50` and `so=50` consistently. Your service is slow. Why?

*Full answer: `si=50` (swap in) and `so=50` (swap out) means the system is actively moving data between RAM and disk swap space. This happens when the system has more memory in use than physical RAM available. When the OS needs RAM for new data, it moves old data to disk (swap out = so). When old data is needed again, it brings it back from disk (swap in = si). Disk is 100-1000x slower than RAM. Every access to swapped data adds milliseconds where microseconds are expected. Fix: reduce memory usage of the process (find the memory leak or reduce cache size) OR add more RAM to the machine OR reduce the number of processes competing for RAM.*

**Q3.** `strace -c -p 1234` shows 95% of syscall time is in `futex` calls. What does this tell you?

*Full answer: `futex` is the Linux system call underlying mutexes, condition variables, and semaphores. If 95% of time is in `futex`, your process is spending almost all its time waiting for locks. This is lock contention -- too many threads competing for too few locks. The process is not doing useful work; it is mostly waiting. Fix approach: (1) profile which lock is most contended (Java: use JProfiler lock contention view; Go: use pprof mutex profile), (2) reduce critical section size (hold the lock for less time), (3) use finer-grained locking (one lock per user instead of one global lock), (4) use lock-free data structures for the most contended paths.*

---

## Part 4: Local vs Production Debugging

### The Fundamental Difference

```
  LOCAL ENVIRONMENT:
  +------------------------------------------+
  | Single machine. No network latency.       |
  | Small dataset (hundreds of rows, not      |
  | millions). Single thread or few threads.  |
  | Full access to debugger and profiler.     |
  | No traffic. No concurrent users.          |
  | Restart freely. No impact.                |
  +------------------------------------------+

  PRODUCTION ENVIRONMENT:
  +------------------------------------------+
  | Distributed. Network latency everywhere.  |
  | Real dataset (millions of rows).          |
  | High concurrency (thousands of users).    |
  | No debugger (cannot pause production).    |
  | Restarting has user impact.               |
  | Every investigation must be non-intrusive.|
  +------------------------------------------+

  THE CONSEQUENCE:
  A bug that is invisible locally (because it requires
  concurrency, real data volume, or network timing) is
  the most common class of production bug.

  "Works on my machine" = "The conditions that trigger
  the bug don't exist on my machine."
```

---

### Local Debugging Tools

```
  DEBUGGER (best tool for deterministic bugs):
  - Set a breakpoint at the suspicious line
  - Inspect all variable values at that point
  - Step through execution line by line
  - Evaluate expressions in the current context

  WHEN TO USE A DEBUGGER:
  - Logic bugs (wrong output, deterministic)
  - You have a reliable reproduction
  - The bug is in local code, not in a remote service

  WHEN NOT TO USE A DEBUGGER:
  - Race conditions (pausing one thread changes timing)
  - Production bugs (no debugger available)
  - Performance bugs (debugger adds overhead)

  PRINT/LOG STATEMENTS (often better than people admit):
  - Faster to add than setting up a debugger for some languages
  - Can see execution path across multiple functions
  - Can print intermediate values through complex logic
  - Rule: add timestamps to every log statement when
    investigating timing issues.

  ASSERTIONS:
  assert(value > 0, f"Expected positive, got {value}")
  - Document assumptions about invariants
  - Fail loudly if assumption is violated
  - Best used to narrow the search space quickly
```

---

### Production Debugging: The Three Pillars

In production you cannot pause the system, attach a debugger, or reproduce freely. You have three tools: logs, metrics, and traces.

```
  THE THREE PILLARS OF PRODUCTION OBSERVABILITY:

  +-----------+     +-----------+     +-----------+
  |   LOGS    |     |  METRICS  |     |  TRACES   |
  +-----------+     +-----------+     +-----------+
  | What:     |     | What:     |     | What:     |
  | Discrete  |     | Numeric   |     | End-to-end|
  | events    |     | aggregates|     | request   |
  | with      |     | over time |     | path      |
  | context   |     |           |     | across    |
  |           |     |           |     | services  |
  +-----------+     +-----------+     +-----------+
  | Answers:  |     | Answers:  |     | Answers:  |
  | What      |     | When did  |     | Which     |
  | happened? |     | it start? |     | service   |
  | What was  |     | How bad?  |     | is slow?  |
  | the error?|     | Trend?    |     | Where is  |
  |           |     |           |     | the time  |
  |           |     |           |     | going?    |
  +-----------+     +-----------+     +-----------+
  | Best for: |     | Best for: |     | Best for: |
  | Root cause|     | Detection |     | Isolating |
  | analysis  |     | + triage  |     | to a      |
  |           |     |           |     | service   |
  +-----------+     +-----------+     +-----------+

  THE DEBUGGING SEQUENCE:
  1. METRICS: "When did it start? What component? How bad?"
  2. TRACES:  "Which service is the bottleneck?"
  3. LOGS:    "What exactly happened in that service?"
```

---

### How to Read Logs Without Getting Lost

Most engineers open logs and scroll. They look for the word "ERROR." They find one, read it, and either fix the wrong thing or get overwhelmed by noise.

```
  THE STRUCTURED LOG READING METHOD:

  STEP 1: FILTER BY TIME WINDOW
  Only look at logs from the time the bug was occurring.
  Logs outside that window are noise.

  STEP 2: FILTER BY REQUEST ID / TRACE ID
  Every request should have a unique ID that propagates
  through all services. Filter all logs to that one ID
  to see the complete path of a single failing request.

  STEP 3: READ CHRONOLOGICALLY
  Read from the first log line of the request to the last.
  The error line is rarely where the bug is.
  The bug is almost always earlier, in the lines that
  produced the state that caused the error.

  STEP 4: LOOK FOR THE LAST NORMAL LINE
  Find the last log line that looks correct.
  The next line is where the system diverged from expected.

  EXAMPLE:
  [10:01:03] Request received: checkout for user 12345
  [10:01:03] Cart loaded: 23 items
  [10:01:03] Product data fetch started         <-- LAST NORMAL
  [10:01:05] Product data fetch timeout (2000ms) <-- DIVERGENCE
  [10:01:05] Error: checkout failed

  The bug is between "Product data fetch started" and the
  timeout. Not at the "checkout failed" line.
```

---

### The Golden Rule: Do Not Change Production During Investigation

```
  NEVER DO THIS (common, catastrophic):

  1. Production incident ongoing
  2. Engineer has a theory
  3. Engineer makes a config change to test the theory
  4. Service restarts
  5. Incident "resolves" (actually: restart temporarily
     cleared the accumulated state that caused the bug)
  6. Bug returns 2 hours later
  7. Now the system has both the original bug AND
     an untested config change

  DO THIS INSTEAD:

  Investigation in production: add READ-ONLY instrumentation.
  - Extra log lines
  - Metric counters
  - Distributed trace spans
  NEVER modify behavior during investigation.

  Hypothesis testing in production:
  - If you must change something to test a hypothesis,
    use a feature flag on 1% of traffic
  - Observe the effect
  - Only roll it out fully when confirmed

  Exception: if users are actively affected, mitigation
  (rollback, shed load) takes priority over clean investigation.
  Investigate on a restored system, not a broken one.
```

---

### Real Production Incident 1: LinkedIn "Too Many Open Files" (2011)

**What happened:** LinkedIn's services started failing with the error `java.net.SocketException: Too many open files`. Engineers initially investigated the socket handling code, assuming a networking bug. The service was restarted multiple times. The error always returned within hours.

**The misleading error message:**

```
  ERROR: java.net.SocketException: Too many open files

  WHAT ENGINEERS ASSUMED: network/socket code bug
  WHAT ACTUALLY CAUSED IT: a background job that opened
  log files for each user (millions of users) and never
  closed them. File handles accumulated until hitting the
  OS limit (default: 1024 open files per process).

  THE LESSON: the error message says "too many open files"
  but "files" in Unix includes sockets, pipes, and actual
  files. Engineers fixated on "sockets" and ignored that
  actual file handles could be the cause.
```

**The fix:**
```
  INVESTIGATION:
  lsof -p [PID] | wc -l  --> shows count of open file descriptors
  lsof -p [PID] | grep -v socket  --> shows non-socket FDs
  --> Found: 900,000+ open file handles to log files

  ROOT CAUSE:
  BackgroundJob.processUserLogs(userId) {
    file = open("logs/" + userId + ".log")
    // process log
    // BUG: file.close() missing
  }

  FIX: add file.close() after processing
  SYSTEMIC FIX: use try-with-resources / context managers
  that close files automatically even if an exception occurs
```

**Staff lesson:** Read error messages literally, not idiomatically. "Too many open files" means exactly that -- too many open file descriptors. Check `lsof` before assuming it is a networking bug. The most misleading error messages are the ones that are technically accurate but point you in the wrong direction.

---

### Brainstorming Questions -- Part 4: Local vs Production

**Q1.** A bug only occurs in production, never in local development or staging. List 5 specific conditions in production that differ from local/staging that could cause this.

*Think about: data volume (millions vs hundreds of rows), concurrency (thousands of users vs single-threaded testing), network latency (inter-service calls take 10ms in production, 0ms locally), real user data (edge cases in real names/addresses not in test data), environment variables (production has different API keys, feature flags, connection strings).*

**Q2.** You want to investigate a production bug without affecting users. What are three safe investigation techniques that do not change system behavior?

*Think about: (1) add read-only log lines via a feature flag to 1% of traffic, (2) query the database in read-only mode to inspect current state, (3) analyze existing distributed traces and logs without touching running services. Never change configs or restart services during investigation.*

**Q3.** A service logs 50,000 lines per minute. You need to find the logs for a specific failing request. What is the first thing a well-instrumented system has that makes this possible in 30 seconds?

*Think about: a request ID or trace ID that is assigned at the edge (load balancer or API gateway) and propagated to every service and every log line for that request. With a trace ID, you run: grep [trace_id] across all service logs and get the complete path of that one request instantly.*

**Q4.** Your monitoring shows an error rate spike at 5:03 PM. The spike lasted 4 minutes and then disappeared. You check at 5:30 PM. No changes were made. How do you investigate a bug that has already resolved itself?

*Think about: logs don't disappear. Find all logs between 5:03 and 5:07 PM. Find a trace ID from a failing request. Reconstruct what happened from logs and metrics. Check: was there a deploy? A cron job that ran at 5 PM? A scheduled task? An external dependency that had a blip? "Fixed itself" usually means the triggering condition (traffic pattern, data state, external service) went away temporarily.*

---

## Part 5: Distributed System Debugging

This is where debugging gets genuinely hard. Local tools stop working. The state is spread across dozens of services. The bug disappears when you look at one service and reappears in another. Timing is everything.

### The Analogy

Imagine a relay race where each runner passes a baton to the next. If the final runner drops the baton, who made the mistake? It could be any runner in the chain: the first runner who started too early, the third runner who passed the baton at the wrong angle, or the final runner who dropped it.

To debug a distributed system failure, you have to watch the whole relay race, not just the runner who dropped the baton.

---

### Tool: Distributed Tracing

```
  WITHOUT DISTRIBUTED TRACING:
  Service A logs: "sent request to B at T+0"
  Service B logs: "received request at T+5ms, sent to C at T+8ms"
  Service C logs: "received request at T+12ms, returned error at T+15ms"
  Service A logs: "received error at T+25ms"

  You have 4 separate log files. You have to manually
  correlate them by timestamp. You miss the fact that
  the "error at T+15ms" in Service C is related to the
  "error at T+25ms" in Service A.

  WITH DISTRIBUTED TRACING (OpenTelemetry / Jaeger / Zipkin):
  One trace ID propagates through A -> B -> C.
  One view shows:

  Request [trace: abc123]
  |-- Service A [0ms - 25ms]
      |-- Service B [5ms - 23ms]
          |-- Service C [12ms - 15ms] ERROR: db timeout
```

**The difference:** Distributed tracing makes the relay race visible as one picture instead of four separate pictures.

---

### The 5 Most Common Distributed Bugs

**Bug 1: Stale Cache**

```
  THE PATTERN:
  1. User updates their profile name to "Alice Smith"
  2. Database: updated. profile.name = "Alice Smith"
  3. Cache: not updated. Still has "Alice Johnson" (old value)
  4. User refreshes page. API reads from cache.
  5. Shows "Alice Johnson". User confused.

  +-----------+   update   +-----------+
  |  Client   |----------->|  Database |  name = "Alice Smith"
  +-----------+            +-----------+
                                 |
                                 | (cache not invalidated)
                                 v
  +-----------+   read     +-----------+
  |  Client   |<-----------|   Cache   |  name = "Alice Johnson"
  +-----------+            +-----------+  (stale!)

  INVESTIGATION:
  1. Check: does the database have the new value?
     SELECT name FROM profiles WHERE user_id = X;
  2. Check: does the cache have the old value?
     redis-cli GET profile:X
  3. If DB has new value and cache has old: cache invalidation bug.

  FIXES:
  - Cache-aside with TTL: cache expires, next read fetches fresh
  - Write-through: update cache atomically with DB write
  - Event-driven invalidation: DB change event invalidates cache
```

**Bug 2: Message Ordering**

```
  THE PATTERN (Kafka example):
  Event 1: "user created account" (partition 0)
  Event 2: "user completed onboarding" (partition 1)

  Partition 0 is processed by Consumer A.
  Partition 1 is processed by Consumer B.
  Consumer B is faster. Processes event 2 first.
  Consumer A processes event 1 second.

  Downstream sees: "user completed onboarding" BEFORE
  "user created account".

  If downstream requires the account to exist before
  processing onboarding: error. User state is inconsistent.

  INVESTIGATION:
  - Check event timestamps vs processing timestamps
  - Look for "entity not found" errors in consumers
    where the entity should have been created by an
    earlier event
  - Check: are related events on the same partition?
    (Kafka guarantees ordering within a partition, not across)

  FIX: Partition by the entity key (user_id).
  All events for user_id=123 go to the same partition.
  Same partition = same consumer = ordered processing.
```

**Bug 3: Split Brain**

```
  THE PATTERN:
  Primary DB is healthy. Network partition occurs.
  Replica cannot reach primary for 30 seconds.
  Replica promotes itself to primary.
  Network heals. Now TWO primaries accepting writes.

  Primary 1: receives order #5001 for $100
  Primary 2: receives order #5001 for $50 (different request)
  Network heals. Both primaries merge. Conflict.
  Which order #5001 is correct?

  INVESTIGATION:
  - Look for duplicate IDs in the database
  - Check replication lag metrics around the incident time
  - Check: did the primary ever lose reachability to its replicas?

  FIX: Distributed consensus (Raft, Paxos) -- a replica only
  promotes if it gets acknowledgement from a majority of nodes.
  If the network partition means the replica cannot reach a
  majority, it stays a replica. Only one node can get majority
  acknowledgement at a time.
```

**Bug 4: Partial Failure**

```
  THE PATTERN:
  Your service calls 3 other services to build a response.
  Services A and B succeed. Service C times out.
  What do you return to the user?

  OPTION 1: Return error (fail closed)
  User sees error page even though most of the data is available.
  Safe but bad UX.

  OPTION 2: Return partial response (fail open)
  User sees most of the page. One section is missing.
  Better UX but requires careful handling of missing data.

  OPTION 3: Return cached/stale data for Service C
  User sees complete page with data that may be slightly old.
  Best UX, requires a cache layer.

  INVESTIGATION:
  - Look for timeout errors on specific service-to-service calls
  - Check: is the timeout always the same service?
  - Check: is it all requests or specific ones?
    (if specific: data-dependent issue in Service C)
    (if all: Service C is overloaded or network route is broken)

  THE DEBUGGING CLUE: partial failures often manifest as
  "intermittent errors" because only some requests hit the
  slow path in Service C.
```

---

### Real Production Incident 2: GitHub's Database Failover (2012)

**What happened:** GitHub's MySQL primary database failed. An automatic failover promoted the replica to primary. Engineers confirmed the failover occurred and the new primary was accepting writes. But for the next 90 minutes, certain repository pushes were silently lost.

**Root cause:**

```
  WHAT ENGINEERS EXPECTED:
  Primary fails --> Replica promoted --> All writes continue
  on new primary. No data loss.

  WHAT ACTUALLY HAPPENED:
  Primary failed after accepting writes that had NOT yet
  been replicated to the replica.
  The replica was 90 seconds behind the primary at failover.
  90 seconds of writes existed on the primary (now dead)
  and nowhere else.

  REPLICATION LAG:
  Primary (dead): [W1][W2][W3][W4][W5] <-- last 90 seconds
  Replica (new primary): [W1][W2][W3] <-- 90 seconds behind

  Writes W4 and W5 are on the dead primary.
  Nobody knows they are missing because the replica
  appeared "healthy" by standard metrics.

  IMPACT: Git pushes from 90 seconds before failover
          were accepted with HTTP 200 but never stored.
          Data loss with a success response. Worst outcome.
```

**The investigation:**

```
  How they found it:
  1. Users reported: "I pushed code but my commit isn't
     there." Repository showed the commit as missing but
     the push had returned success.
  2. Compared git log on user's machine vs on GitHub.
     Missing commits identified.
  3. Checked MySQL binary log on the dead primary
     (recovered from disk): confirmed the writes existed
     and were never replicated.
  4. Root cause: replication lag + no synchronous
     replication confirmation before returning success.

  Fix: require at least 1 replica to acknowledge writes
       before returning success (semi-synchronous replication).
       This adds latency per write but prevents silent data loss.
```

**Staff lesson for debugging:** "The service is healthy" based on metrics can be wrong if your metrics don't measure the right thing. GitHub's replica looked healthy (replication lag was acceptable) until the exact moment it mattered. The lesson: define what "healthy" means for a failover candidate, not just for normal operation. A replica that is 90 seconds behind is not a safe failover candidate.

---

### Real Production Incident 3: Cloudflare WAF Regex Catastrophe (2019)

**What happened:** Cloudflare deployed a new Web Application Firewall (WAF) rule. The rule contained a poorly written regular expression. The regex entered catastrophic backtracking on certain inputs, consuming 100% CPU on every Cloudflare edge node globally. For ~27 minutes, HTTP traffic through Cloudflare returned 502 errors.

**The bug:**

```
  THE REGEX (simplified version of what caused it):
  Pattern: (?:(?:\"|'|\]|\}|\\|\d|(?:null|true|false|yes)...)
           (?:(?:[-+]|\d)+)?
           [a-z0-9 ]+    <-- the problem is here
           (?:(?:[-+]|\d)+)?
           [a-z0-9]+)+
           ^...

  WHY IT CAUSES CATASTROPHIC BACKTRACKING:
  The regex engine tries every possible way to match
  the pattern. For certain inputs with overlapping
  alternatives, the number of attempts grows exponentially.

  String of length N: 2^N backtracking attempts.
  A 30-character string: 2^30 = 1 billion attempts.
  CPU pegged at 100% trying to match ONE request.
  Multiplied by millions of requests per second: global outage.
```

**Investigation clue:**

```
  CPU: 100% on all edge nodes
  |
  |-- What process? Firewall rule evaluation
  |-- What changed? New WAF rule deployed 3 minutes ago
  |-- What is different about the failing requests?
  |   They all contain specific patterns in the URL/body
  |
  --> Performance bug. Root cause: catastrophic regex.
  --> Fix: roll back the WAF rule.
  --> Time to diagnose and mitigate: 27 minutes.
```

**Staff lesson for debugging:** CPU at 100% is almost never about hardware. It is always about an algorithm. Profile first: find the hot path. In this case: `strace` and `perf` would have shown the WAF regex evaluation consuming all CPU within minutes. The lesson: regex engines on untrusted input must be tested with adversarial inputs before deployment. Any regex with nested quantifiers (`+`, `*`) on overlapping character classes is a catastrophic backtracking risk.

---

### Brainstorming Questions -- Part 5: Distributed Systems

**Q1.** Users report that after updating their shipping address, the old address appears on their next order. The database shows the correct new address. Where is the bug, and how do you confirm it?

*Think about: cache is serving stale data. Confirm: check the cache key for that user's address directly. If cache has old value and DB has new value: cache invalidation is missing. The write path updates DB but does not invalidate the cache entry.*

**Q2.** Your payment service sends an event to Kafka after a successful charge. The billing history service consumes that event and records the charge. Users report that sometimes their billing history shows charges from 3 days ago appearing today. Which Kafka concept is likely involved, and what is the fix?

*Think about: consumer lag. The billing history consumer fell behind (maybe it was redeployed, maybe Kafka had a partition rebalance). When it came back up, it replayed 3 days of backlogged events. Fix: monitor consumer lag. Set an alert when lag exceeds X minutes. Process backlog in order without confusing the user-visible "charge date" (event timestamp from Kafka) with the "processed date" (when the consumer processed it).*

**Q3.** You have two microservices: User Service (writes user data) and Profile Service (reads user data for display). A user updates their name. The Profile Service shows the old name for 5 minutes before showing the new one. Is this a bug or a design decision? How do you tell the difference?

*Think about: if the system was designed with eventual consistency (async replication between services), 5 minutes of lag is a design decision -- the system chose availability over consistency. If the system was designed with strong consistency (synchronous replication), 5 minutes of lag IS a bug. Check the design doc. If no design doc exists: write one, because this ambiguity will cause more bugs.*

**Q4.** A write to your database returns HTTP 200. But 1 minute later, reading that data returns the old value. This happens for 2% of writes. What are 3 possible distributed system explanations?

*Think about: (1) read replica lag -- the write went to primary, read went to a replica that hasn't received the update yet. (2) Cache not invalidated after write -- the read hit cache which has the old value. (3) Quorum write with async acknowledgment -- the write was acknowledged before all replicas confirmed. The read hit a replica that hasn't received the write yet.*

---

### Real Production Incident 6: Slack's "Reconnection Storm" (2021)

**What happened:** In January 2021, Slack experienced a roughly 5-hour major outage. When millions of users tried to connect at roughly the same time after a rolling restart, every client immediately attempted to reconnect. This created a massive, coordinated connection storm that overwhelmed Slack's backend infrastructure.

**The sequence:**

```
  PRE-INCIDENT STATE:
  Slack has ~10 million daily active users.
  Most users are connected via a persistent WebSocket connection.
  Slack does rolling restarts of backend nodes periodically.

  ROLLING RESTART BEGINS:
  Node A restarts. Closes 500,000 WebSocket connections.
  
  CLIENT BEHAVIOR (the bug):
  All 500,000 clients: "Connection closed. Reconnect!"
  All 500,000 clients reconnect IMMEDIATELY (no backoff).
  
  Connection storm:
  Node A comes back online.
  Node A: 500,000 simultaneous connection attempts.
  Node A: overwhelmed. Drops connections.
  Clients: "Connection failed. Reconnect!"
  --> RETRY LOOP WITH NO BACKOFF <-- the actual bug

  MEANWHILE:
  Node B starts its rolling restart. Closes another 500,000.
  Node C starts its rolling restart. Another 500,000.
  
  Total simultaneous reconnect attempts: 1.5 million.
  Each backend node is being hammered by 500K concurrent
  connection attempts per second.
  Each failed attempt triggers an immediate retry.
  Retry attempts compound the load.
  System enters a self-reinforcing overload loop.
```

**What the investigation looked like:**

```
  T+0:00  Metrics: connection success rate drops from 99.9% to 60%
  T+0:05  Alert fires. IC (incident commander) assigned.
  T+0:10  Theory 1: "New deploy is broken."
          Check: rolling restart was started. Not a bad deploy.
  T+0:20  Check connection attempt rate.
          Normal: 50,000/second. Current: 2,500,000/second.
          50x normal rate. WHAT IS GENERATING THIS TRAFFIC?
  T+0:25  Theory 2: "DDoS."
          Check: traffic is coming from our own clients.
          Not DDoS. Our own clients are retrying too aggressively.
  T+0:30  Find: client SDK has no exponential backoff on reconnect.
          All clients retry immediately on connection failure.
  T+0:35  Mitigation: push config to clients to wait 5-30 seconds
          before retrying (jitter + backoff).
  T+1:30  Backoff config fully propagated to clients.
          Reconnect storm starts to subside.
  T+5:00  System fully recovered.

  ROOT CAUSE:
  Client reconnection code: "If connection fails, retry after 0ms."
  Should have been: "If connection fails, retry after
  min(base * 2^attempt + random(0, 1000ms), max_wait)"
  (Exponential backoff with jitter.)
  
  SYSTEMIC FIX:
  Client SDK updated with exponential backoff.
  Load tests now include: "simulate 1M simultaneous reconnects."
  Rolling restart playbook updated: restart max 1 node at a time,
  wait for connection count to recover before restarting the next.
```

**Staff debugging lesson:** The investigation took 30 minutes to find the root cause not because it was hidden, but because the first instinct (bad deploy) was wrong. The key was checking the CONNECTION ATTEMPT RATE, not just the connection success rate. The 50x spike in attempts told the story. Once you know "clients are reconnecting immediately without backoff," the fix is obvious. The trap is jumping to the first plausible theory (bad deploy) and spending 10+ minutes on it before checking the actual metrics.

---

### Real Production Incident 7: Amazon DynamoDB Partial Outage (2015)

**What happened:** Amazon DynamoDB experienced elevated latencies and errors for approximately 5 hours. The root cause was a configuration management bug that caused incorrect metadata to be propagated across the cluster, which was then compounded by a retry storm from affected nodes.

**Why it's valuable for debugging education:**

```
  THE SEQUENCE (simplified):
  
  1. A configuration change was deployed to DynamoDB metadata nodes.
     The change contained an error in the serialization format.
  
  2. Metadata nodes began serving incorrect routing information.
     Storage nodes received bad routing tables.
  
  3. Requests started failing because storage nodes were routing
     to the wrong partitions.
  
  4. Automatic retry logic kicked in:
     Failed requests --> retry --> hit wrong partition again
     --> fail --> retry --> fail --> retry
     
     Each retry amplified the load. Storage nodes received
     3-5x normal traffic from retry storms.
  
  5. Even after the configuration error was identified and rolled back,
     the retry storm continued for an hour because:
     - Clients with cached bad routing tables kept using them
     - Automatic retries kept the load elevated
     - The system needed time to drain the backlog

  THE DEBUGGING CHALLENGE:
  The symptoms looked like: intermittent DynamoDB errors,
  high latency, occasional timeouts.
  
  It looked like a performance bug.
  It was actually a distributed system bug:
  configuration corruption + retry amplification.
  
  INVESTIGATION CLUE:
  Which requests were failing?
  
  If random: performance problem (overloaded nodes)
  If patterned by partition key: routing bug
  
  Amazon's investigation: mapped failures to partition keys.
  All failures were clustered around specific partitions.
  Partitions that were being incorrectly routed to wrong nodes.
  This narrowed the investigation from "performance" to
  "routing/metadata" within 45 minutes.

  LESSON: Correlate failures with data characteristics.
  "Which requests fail?" is often more informative than
  "how many requests fail?"
```

**Staff debugging lesson:** When you have a distributed system with both a config bug AND a retry storm, you are debugging TWO problems simultaneously. The retry storm masks the original problem (it looks like an overload issue) and persists even after the original bug is fixed. The investigation sequence must be: (1) identify and roll back the original bug, (2) drain the retry storm separately (often by throttling retries or temporarily increasing capacity). Treating them as one problem leads to confusion.

---

## Part 6: Performance Debugging

### The One Rule

```
  NEVER OPTIMIZE WITHOUT PROFILING FIRST.

  "I think the database is slow" is not a reason to add
  an index. It is a reason to run EXPLAIN ANALYZE.

  "I think the function is slow" is not a reason to
  rewrite it. It is a reason to run a profiler.

  Every hour spent optimizing the wrong thing is an hour
  not spent on the actual bottleneck.

  The actual bottleneck is almost always surprising.
  If you already knew where it was, it would not be
  a performance problem -- it would have been optimized.
```

---

### The Profiling Ladder

```
  LEVEL 1: "Is the system CPU-bound or I/O-bound?"

  CPU-bound: CPU at 90%+ at the load where perf degrades.
             Fix: algorithmic improvement, caching, parallelism.

  I/O-bound: CPU low, but requests are slow.
             Something is waiting: DB query, network call,
             disk read, or external API.
             Fix: find the slow I/O, fix it.

  +---------------------------+
  | Check: CPU utilization    |
  | at the time of slowness   |
  +---------------------------+
        |              |
    CPU high?       CPU normal?
        |              |
    Profile CPU    Profile I/O
        v              v
  Find hot        Find slow
  function        I/O call

  LEVEL 2: "Which function / query is slow?"

  Language-specific profilers:
  Go:     pprof -- go tool pprof http://localhost:6060/debug/pprof/profile
  Java:   async-profiler, JFR (Java Flight Recorder)
  Python: cProfile, py-spy (for production, no restart needed)
  Node:   --prof flag, clinic.js
  Any:    perf (Linux) for native/system-level profiling

  LEVEL 3: "Is this a database problem?"

  EXPLAIN ANALYZE: shows the actual query execution plan.
  Tells you: how many rows scanned, which indexes used,
  whether a sort happened, where time was spent.

  Key things to look for in EXPLAIN output:
  - "Seq Scan": full table scan. Missing index.
  - "Sort": in-memory sort. Missing index on ORDER BY column.
  - "Hash Join" vs "Nested Loop": for large tables,
    hash join is usually faster.
  - Rows estimate vs actual: large discrepancy means
    statistics are stale. Run ANALYZE.
```

---

### Reading an EXPLAIN Output (The Most Useful Debugging Skill Nobody Teaches)

```
  QUERY:
  SELECT * FROM orders o
  JOIN users u ON o.user_id = u.id
  WHERE o.status = 'pending'
  AND u.country = 'IN';

  EXPLAIN ANALYZE output:
  Nested Loop  (cost=0.42..18543.21 rows=12 width=387)
               (actual time=0.043..2847.321 rows=12 loops=1)
    -> Seq Scan on orders o
       (cost=0.00..9243.00 rows=47 width=156)
       (actual time=0.012..1823.443 rows=47890 loops=1)
       Filter: (status = 'pending')
       Rows Removed by Filter: 952110
    -> Index Scan using users_pkey on users u
       (cost=0.42..194.64 rows=1 width=231)
       (actual time=0.021..0.021 rows=1 loops=47890)
       Index Cond: (id = o.user_id)

  READING THIS:
  1. "Seq Scan on orders" + "Rows Removed by Filter: 952110"
     --> Scanning 1,000,000 rows to find 47,890 pending ones.
     --> Missing index on orders.status
     --> FIX: CREATE INDEX ON orders(status)

  2. "loops=47890" on the Index Scan
     --> For every one of the 47,890 pending orders,
         it does a separate index lookup on users.
     --> This is the N+1 problem at the database level.
     --> FIX: rewrite as a JOIN with a compound index
         on (status, user_id) to allow a single pass.

  3. "actual time=2847ms" vs "cost=18543"
     --> The planner estimated 18,543 cost units.
         The actual time was 2.8 seconds.
     --> This query is doing 1 billion unnecessary row comparisons.
```

---

### The Latency Breakdown Chart

When investigating p99 spikes, always get a latency breakdown by component.

```
  REQUEST TIME BREAKDOWN (add to every API endpoint):

  Total request: 3,200ms
  |
  +-- Authentication check:    12ms
  +-- Cache lookup (Redis):    8ms   (miss, went to DB)
  +-- Database query:          2,800ms  <-- HERE
  |   |-- Query planning:      2ms
  |   +-- Query execution:     2,798ms
  |       |-- Index scan:      45ms
  |       +-- Nested loop:     2,753ms  <-- 47,890 iterations
  +-- Response serialization:  22ms
  +-- Network (measured):      38ms

  Without this breakdown: "the API is slow"
  With this breakdown: "the nested loop at the DB level
  is executing 47,890 times when it should execute once"

  Implementation:
  - Add OpenTelemetry spans to each phase
  - Or: add manual timing: start = time.now() ... elapsed = time.now() - start
  - Or: use APM tools (Datadog APM, New Relic, Dynatrace)
```

---

### Real Production Incident 4: Stripe Payment Processing Slowdown (2021)

**What happened:** Stripe's payment processing API experienced elevated latency (p99 from 200ms to 8,000ms) for approximately 90 minutes. Most payments eventually succeeded but took 40x longer than normal.

**Root cause (reported publicly):**

```
  WHAT STRIPE SAW:
  - p99 latency spike to 8 seconds
  - Throughput unchanged (payments still processing)
  - Database CPU: normal
  - Application CPU: elevated

  INVESTIGATION PATH:
  1. Latency breakdown: most time in "fraud scoring" service
  2. Fraud scoring service: CPU at 95%
  3. Profiler on fraud scoring: CPU in regex evaluation
  4. Recent deploy: new fraud detection rule with complex regex
  5. Reproduce: specific payment amounts triggered the regex
     catastrophic backtracking (same class as Cloudflare)
  6. Mitigation: rolled back the fraud rule
  7. Fix: rewrote rule without nested quantifiers on
     overlapping character classes

  TIMELINE:
  T+0:   p99 spike detected by monitoring
  T+8:   latency breakdown pointed to fraud service
  T+15:  profiler confirmed CPU in regex evaluation
  T+22:  fraud rule rollback deployed
  T+25:  p99 returns to 200ms
  T+90:  (total incident duration due to detection delay)
```

**Staff lesson on performance debugging:** The first tool was metrics (p99 spike). The second tool was the latency breakdown (pointed to fraud service). The third tool was a profiler (confirmed CPU in regex). No guessing. Each tool narrowed the search space by an order of magnitude. Total diagnosis time: 22 minutes from "we have a problem" to "we know the fix."

---

### Brainstorming Questions -- Part 6: Performance Debugging

**Q1.** Your API's p99 latency is 800ms. Your p50 is 80ms. What does this tell you about where the bug is?

*Think about: p50 = 80ms means half of requests are fast. p99 = 800ms means 1% of requests are 10x slower. This is not a uniform slowness -- it is a specific slow path that only some requests hit. Common causes: cache miss (those requests miss cache and hit DB), a specific data pattern (requests with large carts, or many items), or a slow secondary operation triggered by specific inputs. Start by finding what is different about the slow 1%.*

**Q2.** You run EXPLAIN ANALYZE on a query and see "Seq Scan" with "Rows Removed by Filter: 4,500,000". What does this tell you and what do you do?

*Think about: the database is scanning 4.5 million rows and discarding most of them to find the rows you want. This is a missing index. Add an index on the column in the WHERE clause. After adding: re-run EXPLAIN ANALYZE and confirm "Index Scan" replaced "Seq Scan".*

**Q3.** A microservice's memory grows from 200MB to 2GB over 48 hours and then gets OOM-killed. Restarting it fixes the memory. CPU is normal throughout. Which class of bug is this and what is your first investigation step?

*Think about: memory leak (Class 3). First step: take a heap dump now and another one in 4 hours. Compare: which object type grew? In Java: use Eclipse MAT to find "dominator tree" (what is keeping the most objects alive). In Go: use pprof heap profiling. The growing object type will point directly to the code path that is creating objects without releasing them.*

**Q4.** After deploying a new feature, your database CPU jumps from 15% to 65%. No increase in traffic. Which 3 things do you check first, in order?

*Think about: (1) Run EXPLAIN ANALYZE on any new queries added by the feature -- look for missing indexes or N+1 patterns. (2) Check query volume in slow query log -- is one new query type running 100x more than expected? (3) Check for any new background jobs or scheduled tasks that run database queries more frequently than intended.*

---

## Part 7: Intermittent and Flaky Bugs

### The Hardest Class

An intermittent bug is one that does not reproduce consistently. It happens sometimes. You cannot predict when. This is the class that drives engineers to despair.

The bad news: you cannot fix a bug you cannot reproduce.

The good news: there is no such thing as a truly random bug. Every intermittent bug has a trigger condition. Your job is to find the trigger condition.

```
  "RANDOM" BUG                   WHAT IT ACTUALLY IS
  +-----------------+            +---------------------------+
  | Fails sometimes |  --------> | Fails when concurrency    |
  |                 |            | exceeds 50 threads        |
  +-----------------+            +---------------------------+
  +-----------------+            +---------------------------+
  | Fails sometimes |  --------> | Fails when cache TTL      |
  |                 |            | expires (every 30 min)    |
  +-----------------+            +---------------------------+
  +-----------------+            +---------------------------+
  | Fails sometimes |  --------> | Fails when payload > 64KB |
  |                 |            | (HTTP chunked encoding)   |
  +-----------------+            +---------------------------+
  +-----------------+            +---------------------------+
  | Fails sometimes |  --------> | Fails on Feb 29 only      |
  |                 |            | (leap year calculation)   |
  +-----------------+            +---------------------------+
```

---

### The Intermittent Bug Playbook

```
  STEP 1: COLLECT FAILURE INSTANCES
  Before you can find the pattern, you need data.
  Every time the bug occurs: log as much context as possible.
  - Exact timestamp
  - Request parameters
  - System state (CPU, memory, active connections)
  - Which instance/pod the failure occurred on
  - What the user was doing

  Do NOT try to fix yet. Collect 10+ failure instances first.

  STEP 2: FIND THE PATTERN
  Compare the failure instances. What do they have in common
  that normal (non-failing) requests do not?

  CHECK THESE DIMENSIONS:
  +------------------------+--------------------------------+
  | Dimension              | Questions to ask               |
  +------------------------+--------------------------------+
  | Time                   | Does it fail at a specific     |
  |                        | hour? Day of week? When cron   |
  |                        | jobs run?                      |
  +------------------------+--------------------------------+
  | Load                   | Does it correlate with traffic |
  |                        | spikes? Concurrent users?      |
  +------------------------+--------------------------------+
  | Data                   | Is the input data special?     |
  |                        | Large payload? Specific user?  |
  |                        | Specific product or category?  |
  +------------------------+--------------------------------+
  | Infrastructure         | Always the same instance/pod?  |
  |                        | Always the same region?        |
  +------------------------+--------------------------------+
  | External               | Does it correlate with a       |
  |                        | third-party API being slow?    |
  +------------------------+--------------------------------+

  STEP 3: CONVERT TO A RELIABLE REPRODUCTION
  Once you know the trigger condition, build a test
  that forces that condition.

  Trigger: "fails when 50+ concurrent users add to cart"
  Test: locust/k6 load test with 60 concurrent users
  Result: fails 100% of the time
  Now you have a reliable reproduction.

  STEP 4: INVESTIGATE AND FIX AS NORMAL
  Once reproducible, use the 5-step framework.
```

---

### Techniques to Make a Race Condition Reproducible

Race conditions are the most common class of intermittent bug. The race window (the time between the check and the act) is usually microseconds. Your tests run at microsecond timing. The race is invisible.

```
  TECHNIQUE 1: INCREASE CONCURRENCY
  Run 1,000 threads simultaneously.
  What was a 0.01% failure rate becomes a 99% failure rate.
  Now you can reproduce it reliably.

  TECHNIQUE 2: ADD ARTIFICIAL DELAYS
  If the race condition is between Thread A and Thread B:

  Before:
  Thread A: check (done in 1ms) --> act
  Thread B:                              check --> act

  After (with artificial delay in Thread A):
  Thread A: check --> sleep(100ms) --> act
  Thread B:          check (now overlaps!) --> act

  Adding sleep() makes the race window 10,000x larger.
  Suddenly the race is reproducible in every run.

  In production, use feature flags to slow down the
  specific operation during investigation.

  TECHNIQUE 3: USE RACE DETECTOR TOOLS
  Go:     go test -race ./...
  C/C++:  -fsanitize=thread (ThreadSanitizer)
  Java:   no built-in, but Helgrind (Valgrind) works
  Python: not applicable (GIL prevents true races,
          but async bugs can occur in asyncio code)

  The race detector adds overhead (~5-10x slower)
  but catches races that never manifested in testing.
  Run it in CI, not production.
```

---

### Real Production Incident 5: Facebook's Thundering Herd (2010)

**What happened:** Facebook's memcached layer would occasionally see a burst of traffic that would saturate the backend databases. The bug was intermittent -- it happened when a popular piece of content went viral and its cache entry expired at the same time that thousands of users were requesting it.

```
  NORMAL OPERATION:
  10,000 users request viral post
       |
       v
  Cache: HIT! Return cached value to all 10,000 users.
  Database: 0 requests. Cache handles everything.

  THE BUG (cache entry expires at T=X):
  At T=X, cache entry expires.
  1 microsecond later: 10,000 simultaneous cache MISS.
  10,000 requests go to the database simultaneously.
  Database: overwhelmed. Latency spikes. Returns errors.

  This is called "thundering herd" or "cache stampede."

  +------------------+
  | Cache expires    |
  | at exactly T=X   |
  +------------------+
          |
          v
  10,000 simultaneous
  cache misses
          |
          v
  10,000 DB queries
  at the same instant
          |
          v
  Database overwhelmed

  WHY INTERMITTENT:
  Only happens when a popular item's cache EXPIRES.
  Popular items are constantly requested (so cache misses
  all hit DB simultaneously). Less popular items: 1-2
  simultaneous misses, not 10,000. Invisible at low traffic.

  THE FIX:
  Two approaches:

  1. Cache locking (mutex on cache miss):
     First request on cache miss: acquires a lock, fetches
     from DB, populates cache, releases lock.
     Other 9,999 requests: wait for the lock, then read
     from cache (now populated).
     DB load: 1 request per cache miss.

  2. Probabilistic early expiration (XFetch algorithm):
     Before the cache entry actually expires, occasionally
     (probabilistically) refresh it.
     The refresh happens BEFORE the entry expires, so
     the cache never goes empty for the viral content.
```

**Staff lesson on intermittent bugs:** The thundering herd bug was "intermittent" because it only occurred when a specific combination of conditions aligned: popular content + cache expiry + simultaneous traffic. Finding the pattern (it happened after cache TTL expiry events for high-traffic keys) converted it from "random database spikes" to "predictable behavior on cache expiry for popular content." Once the pattern was known, reproduction was trivial.

---

### Brainstorming Questions -- Part 7: Intermittent Bugs

**Q1.** A bug happens approximately once per day, always between 2 AM and 4 AM. The bug does not happen at any other time. What is the most likely cause, and what do you check first?

*Think about: a scheduled job. Background jobs, cron tasks, nightly batch processes, backup jobs, report generation jobs. Check: what cron jobs run between 2 AM and 4 AM? Does the bug correlate with the start or end of one of those jobs? Also check: is there a time zone issue (2 AM UTC might be peak business hours somewhere)?*

**Q2.** Your CI tests are flaky. They pass 95% of the time and fail 5% of the time with no code changes. The failures are not consistent (different tests fail each time). What are the three most common causes of flaky CI tests?

*Think about: (1) Tests that depend on ordering -- test B expects state set up by test A, but test execution order is not guaranteed. (2) Tests that use real time or `time.now()` -- passing/failing based on clock speed of the CI machine. (3) Tests that share global state -- if test A sets a global variable, test C might read an unexpected value if the order changes.*

**Q3.** An engineer says "this bug is not reproducible, we should close it." Another engineer says "non-reproducible bugs should stay open." Who is right, and what should happen to the ticket?

*Think about: the second engineer is right. A bug that cannot be reproduced is still a bug -- you just haven't found the trigger yet. The ticket should stay open with a note: "trigger condition unknown. Collect context data on next occurrence: [specific fields to log]." When the next occurrence happens, you have a data collection plan. Close only when: (a) you understand the root cause and it is fixed, or (b) the behavior is confirmed as intended.*

**Q4.** You add a sleep(100ms) to a function in development and your race condition bug suddenly becomes 100% reproducible. What does this tell you, and what is the actual fix?

*Think about: the artificial delay widened the race window enough that the race now always fires. This CONFIRMS it is a race condition and shows you exactly where the race is (at the sleep() point). The fix is NOT to keep the sleep() -- that makes it reliable but slower. The fix is to make the critical section atomic: use a mutex, a database transaction, an atomic operation (like Redis INCR), or redesign to avoid shared mutable state.*

---

## The Complete Debugging Decision Tree

Use this when you don't know where to start:

```
  BUG REPORTED
       |
       v
  CAN YOU DEFINE THE SYMPTOM PRECISELY?
  (when? what error? which users? since when?)
       |
       +-- NO --> Collect data from logs/metrics first.
       |          Do not touch code until you can answer these.
       |
       +-- YES --> Can you reproduce it reliably?
                       |
                       +-- YES --> Jump to ISOLATE
                       |
                       +-- NO --> What type of intermittent?
                                       |
                       +-- Time-based? --> Check cron jobs, TTLs
                       +-- Load-based? --> Write a load test
                       +-- Race cond?  --> Add race detector,
                       |                   increase concurrency
                       +-- Unknown?   --> Collect 10+ failure
                                         instances, find pattern
                                              |
                                              v
                                         ISOLATE:
                                  Binary search the space.
                                  Metrics --> Trace --> Logs.
                                              |
                                              v
                                        HYPOTHESIZE:
                                  One theory. One test.
                                  Observe result.
                                              |
                                              v
                                         FIX + VERIFY:
                                  Test must pass.
                                  Regression test added.
                                  Ship.
```

---

## Exercises (Fully Worked)

### Exercise 1: Debugging Scenario -- The Slowdown (45 minutes)

**Scenario:**

Your checkout API has these metrics at baseline (Tuesday, 10 AM):
- p50: 95ms, p99: 210ms, error rate: 0.1%, DB CPU: 18%

On Wednesday 5 PM you see:
- p50: 98ms (unchanged), p99: 4,200ms, error rate: 0.1% (unchanged), DB CPU: 85%

A deploy happened at 4:45 PM Wednesday: "added recommended products section to checkout page."

**Answer these questions:**
(a) Which class of bug is this?
(b) What does "p50 unchanged, p99 spiked" tell you specifically?
(c) Write the bug statement using the template.
(d) What is the most likely root cause?
(e) How do you reproduce it reliably without waiting until 5 PM Thursday?
(f) Write the EXPLAIN ANALYZE finding you would expect to see.
(g) What systemic fix prevents this class of bug from recurring?

---

**Expected answers:**

(a) **Performance bug (Class 4)**, specifically a database latency issue introduced by the deploy.

(b) **p50 unchanged, p99 spiked** means: most requests (50th percentile) are not affected. Only the tail (top 1%) is slow. This means the slow path is only triggered for some requests -- specifically, requests where the new "recommended products" feature queries the database with an inefficient query. Not all checkouts trigger the expensive path (maybe only checkouts with >10 items, or only for certain product categories).

(c) **Bug statement:**
```
  WHAT IS HAPPENING:
  Checkout API p99 latency spiked from 210ms to 4,200ms.
  DB CPU spiked from 18% to 85% simultaneously.

  WHAT SHOULD HAPPEN:
  p99 should remain under 500ms. DB CPU under 40%.

  WHEN DOES IT HAPPEN:
  Started at 4:45 PM Wednesday (immediately after deploy).
  Appears to affect a subset of checkout requests (p50 unchanged).

  SINCE WHEN:
  Since the v2.4.1 deploy at 4:45 PM Wednesday.

  IMPACT:
  ~1% of checkout requests taking 4.2 seconds.
  Estimated 0.5% checkout abandonment increase.
  No revenue data yet (incident is active).
```

(d) **Most likely root cause:** The "recommended products" query introduced an N+1 pattern or a missing index. For each cart item, the query fetches recommended products separately: N items → N queries, each scanning a large table. At 5 PM traffic with more concurrent users, the DB connection pool saturates, causing the p99 spike. p50 is unaffected because lighter checkouts (fewer items) hit the slow path less.

(e) **Reproduce without waiting:**
Write a load test:
```
  load_test(
    endpoint="/checkout",
    concurrent_users=300,
    cart_items=15,  # above the threshold where it slows
    duration_seconds=60
  )
  assert p99_latency < 500ms  # this should FAIL, confirming repro
```
Run the load test immediately after deploying to staging. If p99 exceeds 500ms at 300 concurrent users with large carts: reproduced.

(f) **Expected EXPLAIN ANALYZE finding:**
```
  Nested Loop (actual time=3,800ms)
    Seq Scan on products
      (Rows Removed by Filter: 4,200,000)   <-- full table scan
    Index Scan on recommended_products
      (loops=23)   <-- 23 iterations = 23 cart items = N+1
```
23 iterations = N+1 (one per cart item). Seq Scan = missing index on the products table for the recommended products lookup.

(g) **Systemic fix:**
- Add automated query analysis to CI that detects N+1 patterns
- Add EXPLAIN ANALYZE as a required step in the TDD template for any new DB queries
- Add a load test as a CI gate: "checkout p99 must remain under 500ms at 300 concurrent users"

---

### Exercise 2: Bug Classification (20 minutes)

**Classify each bug and name your first investigation step:**

1. "Service returns 500 every time a user's cart has more than 100 items"
2. "User balance decrements by $10 but sometimes the balance check shows the pre-decrement value for 2-3 seconds"
3. "Service crashes every 3 days. Restarting fixes it."
4. "Test passes when run alone but fails when run as part of the test suite"
5. "Users in Tokyo report the checkout page loads in 8 seconds. Users in New York see 300ms."

---

**Expected answers:**

1. **Logic bug** (deterministic, specific input trigger). First step: write a test with 101 cart items and confirm it fails. Then add assertions to the cart processing code to find where it fails.

2. **Distributed bug (stale cache or read replica lag)**. First step: after the decrement, query both the database (write primary) and the cache/replica directly. If primary shows new balance and cache/replica shows old: the read path is not reading from the primary.

3. **Memory leak (Class 3)**. First step: graph memory usage over 3 days. Confirm linear growth. Take heap dumps at day 1, day 2, day 3. Compare what grew. The growing object type points to the code path.

4. **Concurrency/ordering bug in tests**. First step: identify what global state or shared resource the failing test reads that another test writes. Add `--shuffle` to the test runner to expose ordering dependencies.

5. **Performance bug, likely network latency or missing CDN coverage**. First step: add distributed tracing that records where in the request the time is spent. If the latency is in the first network hop (DNS + TCP handshake): no edge node in Tokyo region. If it's in the API response time: the API server is in US-East and Tokyo users are paying full round-trip for every API call.

---

### Exercise 3: Read the Distributed Trace (30 minutes)

**Given this trace for a failing order creation request (total: 6,800ms):**

```
  POST /api/v1/orders [trace_id: xyz789]
  |-- auth.validateToken           [0ms - 18ms]      OK
  |-- inventory.checkStock         [18ms - 6,200ms]  OK
  |   |-- db.select (inventory)    [18ms - 6,195ms]  OK
  |-- pricing.calculateTotal       [6,200ms - 6,220ms] OK
  |-- orders.createRecord          [6,220ms - 6,800ms] ERROR
      |-- db.insert (orders)       [6,220ms - 6,250ms] OK
      |-- events.publish (kafka)   [6,250ms - 6,800ms] TIMEOUT
```

**Answer:**
(a) Which service is responsible for the 6.8 second total?
(b) Where exactly is the time going?
(c) Write 3 hypotheses for the Kafka publish timeout.
(d) Which hypothesis do you test first and why?
(e) The Kafka publish times out but the DB insert succeeded. What is the data consistency risk?

---

**Expected answers:**

(a) Two services are responsible: `inventory.checkStock` takes 6,182ms (91% of the time) AND `events.publish` times out at 550ms. The order creation fails at Kafka, but inventory check was also extremely slow.

(b) The time breakdown:
- `db.select (inventory)`: 6,177ms → this is the dominant cost. A query on the inventory table is taking 6 seconds.
- `events.publish (kafka)`: 550ms timeout → Kafka publish timed out after the 550ms timeout limit.

(c) **Three hypotheses for Kafka timeout:**
1. Kafka broker is overwhelmed (high producer queue, slow to acknowledge)
2. The Kafka producer's timeout is set too low (550ms) for normal operation under load
3. The network path between the orders service and the Kafka broker is congested

(d) **Test hypothesis 1 first**: check Kafka broker metrics (producer request queue depth, request latency). This takes 2 minutes (open a dashboard) versus the others which require code changes. Fastest to rule in or out.

(e) **Data consistency risk:** The DB insert (order record) succeeded. The Kafka publish (order created event) failed. This means: the order exists in the database but no downstream services know about it. The payment service has not been notified. The fulfillment service has not been notified. The user may see their order in their history (it's in the DB) but it will never be fulfilled or charged. This is a **partial write consistency bug** -- the system is in an inconsistent state. Fix requires: either a transactional outbox pattern (write the Kafka message to the DB atomically with the order, publish separately) or a saga pattern with compensating transactions.

---

### Exercise 4: Intermittent Bug Investigation (30 minutes)

**Scenario:** Your team has a bug ticket: "Users occasionally see a 'session expired' error while actively using the app. It happens 2-3 times per day. Cannot reproduce."

You have the following data from 4 recent occurrences:
- Occurrence 1: 2:03 AM, user was on the app for 1 hour 58 minutes
- Occurrence 2: 8:47 AM, user was on the app for 1 hour 59 minutes
- Occurrence 3: 3:15 PM, user was on the app for 1 hour 57 minutes
- Occurrence 4: 11:22 PM, user was on the app for 2 hours 01 minute

**Answer:**
(a) Is this actually an intermittent bug, or is there a pattern?
(b) What is the trigger condition?
(c) Write the reproduction case.
(d) What is the most likely root cause?
(e) What is the fix?

---

**Expected answers:**

(a) **Not actually intermittent.** There is a clear pattern: all four occurrences happen after approximately 2 hours of session activity (range: 1h57m to 2h01m). The "randomness" is because different users start sessions at different times.

(b) **Trigger condition:** a session that has been active for exactly ~2 hours triggers the session expiry error.

(c) **Reproduction:**
```
  1. Log in to the app.
  2. Make any API call to keep the session "active."
  3. Wait exactly 2 hours without triggering session refresh.
  4. Make an API call.
  Expected: session expired error.
```
This will reproduce 100% of the time.

(d) **Most likely root cause:** the session token has a 2-hour absolute TTL that is not refreshed by activity. The app considers the session "active" (user is using it) but the server-side session token expires at the 2-hour mark regardless of activity. The client does not proactively refresh the token before expiry.

(e) **Fix options:**
1. Sliding window TTL: refresh the token on every API call. Session expires 2 hours after the LAST activity, not the FIRST login.
2. Proactive client refresh: client tracks token expiry, refreshes 10 minutes before expiry using a background timer.
3. Increase absolute TTL: change from 2 hours to 8 hours (or appropriate for your security model).
Correct choice depends on security requirements. For most user-facing apps: sliding window TTL is the right answer.

---

### Exercise 5: Write the Post-Mortem (30 minutes)

**Scenario (from Exercise 1 above):** The recommended products N+1 query caused a 90-minute p99 spike on checkout. Revenue impact: estimated $180K in abandoned carts (2.3% abandonment rate, $10M/day checkout GMV). The deploy was rolled back at 6:15 PM. p99 returned to normal by 6:18 PM.

**Write a complete blameless post-mortem including:**
(a) Impact section
(b) Timeline (use T+0 = 4:45 PM when the deploy happened)
(c) Root cause (systemic, not "the engineer wrote a bad query")
(d) Three action items that prevent the class of bug

---

**Expected answer:**

**(a) Impact:**
```
Duration: 90 minutes (4:45 PM - 6:15 PM Wednesday)
User impact: checkout p99 degraded from 210ms to 4,200ms
             (top 1% of checkouts took 20x longer than normal)
Revenue impact: estimated $180K in abandoned carts
               (2.3% abandonment increase x $10M/day GMV x
                90/1440 minutes = ~$180K)
Scope: checkout path only. Browse, search, account unaffected.
```

**(b) Timeline:**
```
T+0:00  v2.4.1 deployed: "recommended products on checkout"
T+0:15  First p99 spike detected (alert threshold: > 1,000ms)
T+0:20  DB CPU alert fires: 85% (threshold: 70%)
T+0:25  On-call declares SEV2. IC assigned.
T+0:35  Distributed trace points to inventory service DB query
T+0:45  EXPLAIN ANALYZE confirms: N+1 on recommended products
T+0:50  Decision: roll back v2.4.1 (deploy was 50 min ago, safe to rollback)
T+1:30  Rollback deployed
T+1:33  p99 returns to 215ms. Incident resolved.
T+1:35  SEV2 closed. Post-mortem scheduled.
```

**(c) Root cause (systemic):**
```
The recommended products feature was implemented and code-reviewed
but had no performance review. Our TDD template does not require
EXPLAIN ANALYZE for new database queries. Our CI pipeline has no
load test gate for checkout p99.

The specific query executed 1 query per cart item (N+1) against
a 40M-row products table with no index on the filter column.
At 300+ concurrent users, 23 items per cart, this generated
~6,900 database queries per second from checkout alone.

This class of bug (N+1 query shipped without performance review)
has occurred twice before in 12 months on different endpoints.
This is the third occurrence. It is a process gap, not an
individual error.
```

**(d) Three systemic action items:**
```
+--------------------------------------------+-------+----------+
| Action                                     | Owner | Due      |
+--------------------------------------------+-------+----------+
| Add N+1 detection to CI pipeline.          | Infra | 2 weeks  |
| sqlfluff rule: query inside a loop blocks  |       |          |
| PR merge.                                  |       |          |
+--------------------------------------------+-------+----------+
| Add checkout p99 load test to CI.          | Perf  | 1 week   |
| Gate: p99 must stay < 500ms at 300         |       |          |
| concurrent users. Fails build if exceeded. |       |          |
+--------------------------------------------+-------+----------+
| Update TDD template: any new DB query      | Staff | 3 days   |
| requires EXPLAIN ANALYZE output in the     |       |          |
| design doc before review approval.         |       |          |
+--------------------------------------------+-------+----------+
```

---

## Homework

### Short (30-45 minutes each)

**1. EXPLAIN ANALYZE practice:**
Take any query you work with regularly. Run `EXPLAIN ANALYZE` on it. Find: does it do a Seq Scan anywhere? If yes, add an index and re-run. Compare the actual execution time before and after. Write down what the index changed and why.

**2. Race detector:**
In any multi-threaded or concurrent code you have access to, enable the race detector and run the tests. Report: did it find anything? If yes, what was the race condition and how did you fix it? If not, what does that tell you (and what does it NOT tell you)?

**3. Intermittent bug pattern-finding:**
Find a bug report in your team's issue tracker that says "intermittent" or "cannot reproduce." Look at any data attached (timestamps, user reports, error logs). Can you find a pattern? Write the pattern you found (or write why it is genuinely random -- which almost never happens).

---

### Deep (2-4 hours each)

**1. Production debugging walkthrough:**
Next time an incident occurs in your team, document your debugging process using the 5-step framework. Write down: the bug statement, how you reproduced it, how you isolated it (what binary search steps you took), your hypotheses in order, and the final root cause. Compare to what you would have done before reading this chapter.

**2. Add observability to a service you own:**
Pick one service you own that has poor observability (no distributed tracing, or logs without request IDs). Add: (a) a trace ID that propagates through all downstream calls, (b) a timing span for each major operation, (c) structured logging with the trace ID on every log line. Measure: how much faster can you diagnose the next incident with these in place?

**3. Write the debugging runbook:**
For your most complex or most frequently broken service, write a "debugging runbook" that any on-call engineer can follow. It should answer: (a) what are the 5 most common failure modes? (b) for each failure mode: what is the symptom in logs/metrics? (c) for each failure mode: what is the investigation sequence? (d) for each failure mode: what is the mitigation? Test the runbook by giving it to a colleague who doesn't know the service and asking them to follow it during a game day.

---

## Glossary

**Amdahl's Law:** The speedup from optimizing part of a system is limited by the fraction of time that part is used. If a function takes 5% of total request time, making it infinitely fast only gives 5.3% total improvement. Always profile to find the dominant bottleneck before optimizing.

**Assertion:** A check inserted into code that verifies an invariant: `assert(user != null)`. Fails loudly if the assumption is violated. Excellent for narrowing the search space during debugging -- add assertions at the midpoint of a function to bisect where a value becomes wrong.

**Binary search debugging:** The technique of repeatedly dividing the search space in half to find a bug. Applied to: commit history (git bisect), code paths (add logging at the midpoint), distributed traces (check cumulative time at each service boundary).

**Cache stampede (thundering herd):** A performance bug where a cache entry expires and many simultaneous requests miss the cache and hit the backend database at the same moment. Fix: cache locking (only one request fetches from DB on miss) or probabilistic early expiration (refresh before expiry).

**Catastrophic backtracking:** A performance bug in regex engines where certain patterns and inputs cause the engine to try exponentially many matching paths. A 30-character string can cause 2^30 (1 billion) attempts. Detected with profiling (CPU in regex evaluation). Caused by nested quantifiers on overlapping character classes.

**Consumer lag:** In a message queue (Kafka, SQS), the number of messages that have been produced but not yet consumed. High consumer lag means the consumer is falling behind. Causes: consumer redeployed, consumer crashed, consumer processing is too slow for the production rate.

**Distributed tracing:** The technique of assigning a unique trace ID to each incoming request and propagating it through all services that handle the request. Allows reconstructing the complete path of a single request across multiple services. Tools: Jaeger, Zipkin, OpenTelemetry.

**EXPLAIN ANALYZE:** A PostgreSQL (and MySQL) command that shows the actual execution plan and timing for a query. Key things to look for: "Seq Scan" (missing index), high "loops" count (N+1), large "Rows Removed by Filter" (bad selectivity).

**Heisenbug:** A bug that disappears or changes behavior when you try to observe it. Named after Heisenberg's uncertainty principle. Almost always a race condition: adding a log statement serializes concurrent operations enough to eliminate the race.

**Memory leak:** A bug where allocated memory is never freed, causing the process's memory usage to grow over time. Common causes: event listeners not removed, cache without eviction, circular references preventing garbage collection, goroutines/threads that never terminate.

**N+1 query:** A database anti-pattern where 1 query fetches N parent records and then N separate queries fetch related data one by one. Total: N+1 queries. At production scale (N=100,000), this causes database saturation. Fix: JOIN or batch fetch.

**Partial failure:** A distributed system failure mode where some components of a request succeed and others fail. The system is in an inconsistent state. Fix patterns: transactional outbox (ensure downstream events are committed atomically with the primary write), sagas (compensating transactions), idempotent retries.

**Post-mortem:** A document written after an incident that records: timeline, root cause, impact, and action items. A blameless post-mortem identifies system gaps as the root cause, not individual engineer errors. Test: would the action items prevent this bug if a different engineer triggered it?

**Race condition:** A bug where the correctness of a program depends on the timing or ordering of concurrent operations. The "race window" is the gap between a check and an act. Detected with race detector tools (Go: -race) or by adding artificial delays to widen the race window.

**Regression test:** A test written specifically to catch a bug that was previously fixed. Ensures the same bug cannot be silently reintroduced. Every bug fix should be accompanied by a regression test.

**Replication lag:** The delay between a write being committed on the primary database and being available on a replica. Normal: <1 second. Dangerous during failover: if the primary fails and the replica is 90 seconds behind, those 90 seconds of writes are lost.

**Split brain:** A distributed system failure mode where two nodes both believe they are the primary (leader) and both accept writes. Causes data divergence and conflicts. Fixed by requiring a majority quorum (Raft/Paxos consensus) before a node can promote itself to primary.

**Trace ID / Request ID:** A unique identifier assigned to each incoming request at the entry point (load balancer or API gateway) and propagated to every service and every log line for that request. Enables filtering all logs for a single request across dozens of services.

---

*Chapter 41b complete.*
