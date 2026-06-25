# Chapter 116: Refactoring Large Systems

```
┌─────────────────────────────────────────────────────────────────────┐
│              REFACTORING LARGE SYSTEMS — AT A GLANCE                │
│                                                                     │
│  Core thesis: A large system is never refactored in one move.       │
│  It is changed incrementally while it runs, maintaining             │
│  correctness and deployability at every intermediate step.          │
│                                                                     │
│  L5 signal: "We should refactor this module."                       │
│  L6 signal: Lays out the seam-based plan, the test strategy,        │
│             the migration path, the rollback condition,             │
│             and the org coordination needed — before writing        │
│             a single line.                                          │
│                                                                     │
│  Key patterns: Strangler Fig · Branch by Abstraction                │
│                Expand and Contract · Dark Launch                    │
│                Mikado Method · Characterization Tests               │
└─────────────────────────────────────────────────────────────────────┘
```

> "The key to successful large-scale refactoring is that you never stop shipping. If you can't deploy on any given day, your refactoring has become a liability." — Adapted from Martin Fowler

---

## Overview

Refactoring a large system is one of the highest-leverage skills a Staff engineer has — and one of the most dangerous when done wrong. Done well, it improves velocity, reliability, and developer experience for every engineer on the team for years. Done wrong, it produces a six-month feature freeze, an accumulation of bugs that pile up in two parallel codebases, and a "big bang" cutover that fails at 2 AM on a Friday.

This chapter covers the patterns, decision frameworks, and war stories that make the difference. It is organized around the question every Staff engineer faces when handed a legacy system: "How do we change this without breaking it?"

---

## Part 1: What Makes a System "Large" and Why Refactoring Is Hard

"Large" in this context does not mean many lines of code. It means:

- **Many callers:** A change to the interface or behavior breaks downstream consumers
- **Many owners:** Different teams wrote different parts; no single engineer understands the whole
- **Long history:** Behavior accumulated over years; some of it is wrong, but it is *relied upon* being wrong
- **No tests (or wrong tests):** The test suite checks implementation details rather than behavior; refactoring causes test failures that are not real bugs
- **Production traffic:** The system is live; you cannot take it down to change it

These properties create the fundamental difficulty: **you cannot understand the system before changing it, and you cannot change it before understanding it.** The codebase is too large to hold in one engineer's head; the behavior is too subtle to fully specify; the blast radius of a change is unknown.

### The Big Rewrite Temptation

When a system is sufficiently painful, the natural impulse is to rewrite it. Joel Spolsky called this "the single worst strategic mistake any software company can make." The argument:

1. The existing system embeds years of bug fixes, edge cases, and business logic — most undocumented. A rewrite starts with none of this.
2. During the rewrite, the old system gets new features. The rewrite chases a moving target.
3. The rewrite is never "done." It accumulates its own technical debt as shortcuts are taken to ship faster.
4. The rewrite team loses touch with production; the original team stops investing in the old system; both codebases decay.

**When rewrite is justified:** The underlying architecture makes the domain model impossible to express correctly. The technology is end-of-life with no migration path (e.g., Flash, Python 2). The codebase is shorter than the refactor plan. These are rare.

**The default:** Incremental refactoring with the patterns in this chapter.

---

## Part 2: The Strangler Fig Pattern

The Strangler Fig is the most important pattern for large-scale refactoring. Named after the fig tree that grows around a host tree, eventually replacing it while the host still stands.

**The pattern:**

1. **Intercept** — Put a routing layer (proxy, feature flag, or facade) in front of the existing system
2. **Implement** — Build the new implementation behind the router
3. **Route** — Migrate traffic from old to new incrementally (1% → 10% → 50% → 100%)
4. **Retire** — Once 100% of traffic is on the new implementation, delete the old one

```
Before:
  [Client] → [Old System]

During migration:
  [Client] → [Router/Strangler Facade]
                 ├── [Old System]    (90% of traffic)
                 └── [New System]   (10% of traffic)

After:
  [Client] → [New System]
```

**Why it works:** At no point does the old system stop serving traffic until you are confident in the new one. You can roll back at any traffic split. You ship the new system incrementally, discovering integration problems early.

**HTTP-level strangler (most common):**
```python
# Nginx or application-level router
def route_request(request):
    # Read user assignment from feature flag service
    if feature_flags.is_enabled("new_checkout", user_id=request.user_id):
        return new_checkout_service.handle(request)
    else:
        return old_checkout_service.handle(request)
```

**Database-level strangler:** When the old and new systems need to share state, use dual-write: both systems write; new system reads from its own store; compare outputs; switch reads when confident.

**The critical discipline:** The router must be simple. It must not accumulate business logic. If it does, you have added a third system rather than replacing the first.

---

## Part 3: Branch by Abstraction

Used when you cannot route at the HTTP level — the change is deeper inside a single service. Branch by Abstraction lets multiple implementations coexist behind an interface.

**Steps:**

1. **Create an abstraction** — Define an interface over the thing you want to change
2. **Implement the old behavior** — Make the existing code implement the interface (no behavior change yet)
3. **Build the new implementation** — Write the new version behind the same interface
4. **Switch** — Change which implementation is injected (via dependency injection, feature flag, or config)
5. **Delete the old** — Once the new is validated, remove the old implementation

```python
# Step 1: Define the interface
class PaymentProcessor(Protocol):
    def charge(self, amount: Decimal, card_token: str) -> ChargeResult: ...

# Step 2: Old implementation
class StripeV1PaymentProcessor:
    def charge(self, amount: Decimal, card_token: str) -> ChargeResult:
        # old Stripe API implementation
        ...

# Step 3: New implementation
class StripeV2PaymentProcessor:
    def charge(self, amount: Decimal, card_token: str) -> ChargeResult:
        # new Stripe API implementation
        ...

# Step 4: Injection point
def get_processor(feature_flags) -> PaymentProcessor:
    if feature_flags.is_enabled("stripe_v2"):
        return StripeV2PaymentProcessor()
    return StripeV1PaymentProcessor()
```

**When to use branch by abstraction vs strangler fig:**
- Strangler Fig: replacing an entire service or system; HTTP-level routing is natural
- Branch by Abstraction: replacing an internal component within a service; the change is below the API boundary

---

## Part 4: Database Refactoring — Expand and Contract

Database schemas are the hardest part of large-scale refactoring. Unlike code, you cannot just switch between two implementations — data persists, and different application versions may be running simultaneously during a deployment.

**The Expand and Contract pattern (also called "parallel change"):**

**Phase 1: Expand** — Add the new schema without removing the old
- Add the new column/table
- Deploy application code that writes to *both* old and new schema
- Verify new schema is being populated correctly

**Phase 2: Migrate** — Move existing data
- Backfill historical data from old schema to new schema
- Verify backfill completeness

**Phase 3: Switch reads** — Start reading from the new schema
- Deploy application code that reads from new schema, writes to both
- Run in production; verify correctness

**Phase 4: Contract** — Remove the old schema
- Deploy application code that only writes to new schema
- Drop the old column/table

**Example — renaming a column:**
```sql
-- Phase 1: Add new column (keep old)
ALTER TABLE users ADD COLUMN full_name VARCHAR(255);

-- Application: writes both columns
UPDATE users SET full_name = first_name || ' ' || last_name;

-- Phase 2: Backfill
UPDATE users SET full_name = first_name || ' ' || last_name
WHERE full_name IS NULL;

-- Phase 3: Read from new column, write both (in application code)

-- Phase 4: Drop old columns (after all app versions read full_name)
ALTER TABLE users DROP COLUMN first_name;
ALTER TABLE users DROP COLUMN last_name;
```

**Why naive column renames fail:** If you rename `first_name` to `full_name` in a single migration and deploy the application, the old application version (still running during rolling deploy) hits a `column not found` error. Expand and Contract ensures every application version can read and write at every stage.

**Zero-downtime constraint:** Each phase must be deployable and rollback-safe independently. Never combine phases in one deploy.

---

## Part 5: Characterization Tests — Testing What You Have

Before refactoring, you need tests. But the existing code often has no tests, or the tests are tightly coupled to implementation details. The solution: **characterization tests**.

A characterization test does not test what the code *should* do. It tests what the code *currently does* — including the bugs. The goal is to document existing behavior so that the refactored code produces identical outputs for identical inputs.

```python
# Characterization test: capture actual behavior
def test_price_calculation_characterization():
    # This behavior may be wrong, but it's what callers depend on
    result = legacy_calculate_price(
        base_price=100,
        user_type="premium",
        discount_code="SAVE10"
    )
    assert result == 83.0  # whatever the old code actually returns

# After refactoring: new implementation must match
def test_price_calculation_new_implementation():
    result = new_calculate_price(
        base_price=100,
        user_type="premium",
        discount_code="SAVE10"
    )
    assert result == 83.0  # same output; refactoring is safe
```

**The process:**
1. Run the old code against a set of representative inputs
2. Record the outputs (even if they seem wrong)
3. These recordings become the test suite
4. Refactor; all tests must still pass
5. If a "bug" in the old behavior is intentional (callers depend on it), document it before fixing it separately

**Characterization tests are not the end state.** Once the refactor is complete, replace them with proper behavior-based tests. But they are an invaluable safety net during the migration.

---

## Part 6: The Mikado Method

The Mikado Method is a structured approach for navigating refactoring dependencies. Named after the Japanese pickup-sticks game: you must remove sticks in the right order without disturbing others.

**The problem it solves:** You start a refactor, discover a dependency, start fixing the dependency, discover another dependency, and after a week you have five half-finished changes and a codebase that doesn't compile.

**The method:**
1. **State the goal** — Write down the desired end state: "Extract PaymentService into its own module"
2. **Attempt the goal directly** — Try to make the change naively; let it fail
3. **Record what broke** — These are the prerequisite changes (the "child nodes")
4. **Revert** — Roll back all changes; return to a clean state
5. **Work on the prerequisites** — Apply the Mikado Method recursively to each prerequisite
6. **Try again** — Once prerequisites are met, attempt the goal again

The key discipline: **always revert to a clean state** when you discover a new blocker. Never accumulate a pile of half-done changes. Each step either moves forward cleanly or is completely reverted.

```
Goal: Extract PaymentService
├── Prerequisite: Define PaymentService interface
│   ├── Prerequisite: Identify all payment-related methods in OrderService
│   └── Prerequisite: Agree on interface with billing team
├── Prerequisite: Move payment tests to new test file
└── Prerequisite: Update dependency injection setup
```

This produces a tree. Work leaves-first. Each leaf should be a small, safe, independently-deployable change.

---

## Part 7: Extracting Services from a Monolith

The most ambitious form of refactoring is extracting a service from a monolith. The Strangler Fig and Branch by Abstraction are the technical patterns; this part covers the decision framework and execution playbook.

**When extraction is worth it:**
- The component needs to scale independently (different traffic patterns from the monolith)
- Different teams need to deploy it independently (organizational boundary)
- The component has a different technology requirement (e.g., needs to be in Go for performance; monolith is Ruby)
- The component is a shared capability consumed by multiple teams

**When extraction is not worth it:**
- "We should have microservices" is not a reason
- The component is small and unlikely to grow
- The team doesn't have the operational maturity to run services independently
- The component is tightly coupled to monolith state that can't be separated

**The extraction playbook:**

**Step 1: Define the boundary.** Use Domain-Driven Design (DDD): identify the bounded context. What data does this component own? What operations does it perform? What external events does it emit/consume? Draw the boundary on paper first.

**Step 2: Define the interface.** Before extracting, define the API the new service will expose. Add that API as an internal interface in the monolith. Route the monolith through the interface (Branch by Abstraction). This validates the interface before extraction.

**Step 3: Test the boundary.** Write integration tests that test the monolith via the interface. These will become the tests for the extracted service.

**Step 4: Extract and deploy alongside.** Create the new service. It shares the same database initially (dual-read/write). Deploy it alongside the monolith.

**Step 5: Migrate data ownership.** Use Expand and Contract to move data out of the monolith database into the service's database. The service becomes the authoritative owner; the monolith calls the service via API.

**Step 6: Remove the monolith code.** Once the service is stable, delete the extracted code from the monolith.

**The distributed monolith anti-pattern:** The most common failure mode. The extracted service is deployed separately but is still tightly coupled: it shares a database with the monolith, or it calls back into the monolith synchronously for every request. The result is all the operational complexity of microservices with none of the independence benefits. The cure: the service must own its own data; it must not call back into the monolith.

---

## Part 8: Feature Flags for Code Migration

Feature flags are not just for product experiments. They are an essential tool for code migration.

**The migration flag pattern:**
```python
def calculate_shipping_cost(order):
    if feature_flags.is_enabled("new_shipping_calculator", user_id=order.user_id):
        return new_shipping_calculator.calculate(order)
    else:
        return legacy_shipping_calculator.calculate(order)
```

**Stages of a code migration with flags:**

1. **Shadow mode (0% traffic, both run):** Run both old and new; use old result; log discrepancies. This validates the new implementation without affecting users.

```python
def calculate_shipping_cost(order):
    old_result = legacy_shipping_calculator.calculate(order)
    if feature_flags.is_enabled("new_shipping_shadow"):
        new_result = new_shipping_calculator.calculate(order)
        if old_result != new_result:
            logger.warning(f"Shipping calc discrepancy: {old_result} vs {new_result}")
    return old_result  # always use old result
```

2. **Canary (1-5% traffic):** Route a small percentage to the new implementation. Monitor error rates and latency. Roll back immediately if metrics degrade.

3. **Gradual rollout (5% → 25% → 50% → 100%):** Increase traffic with monitoring gates between each step.

4. **Cleanup:** Once at 100%, delete the old implementation and the flag.

**Flag hygiene:** Feature flags accumulate. A codebase with 50 active feature flags is unmaintainable. Enforce a "flag lifespan" — a migration flag must be removed within 90 days of reaching 100% rollout. Track flags in your issue tracker with a removal ticket created at the same time as the flag.

---

## Part 9: Measuring Progress — Metrics for Refactors

Refactoring is invisible to business stakeholders unless you measure it. Staff engineers need two kinds of metrics: metrics that justify the investment, and metrics that track progress.

**Justification metrics (before starting):**

| Metric | What It Measures | How to Calculate |
|--------|------------------|------------------|
| Change failure rate | % of deployments causing incidents | incidents / deploys over 90 days |
| Lead time for change | Hours from commit to production | median over 90 days |
| Cyclomatic complexity | Code complexity (proxy for bug rate) | tool: `radon`, `complexity-report` |
| Coupling metric | % of files changed in same PR as target file | git log analysis |
| Test coverage | % of lines covered by tests | coverage.py, Istanbul |

**Progress metrics (during the refactor):**

| Metric | Interpretation |
|--------|---------------|
| Lines deleted | Net reduction means simplification; flat means you are rewriting, not refactoring |
| Flag count | Should decrease as migrations complete |
| Parallel code paths | How many old/new pairs exist; should decrease monotonically |
| Integration test coverage on new paths | Should increase monotonically |
| P99 latency comparison | New implementation should not regress |

**The business case:** "We want to refactor the payment module" is not a business case. "The payment module has a 12% change failure rate (industry average: 2%), causing an average 45-minute incident per deployment. The team deploys 3 times a week; that's 2.7 hours of incident response per week, plus the customer impact. The refactoring will take 6 engineer-weeks. Break-even is 6 weeks after completion." That is a business case.

---

## Part 10: Testing Strategy for Large Refactors

The biggest risk in a large refactor is undetected behavioral change. Your testing strategy must evolve alongside the refactoring.

**Testing pyramid during a refactor:**

**Pre-refactor (characterization phase):**
- Write characterization tests as described in Part 5
- Focus on public API behavior, not internal implementation
- Cover the happy path AND the known edge cases AND the "known-wrong" behavior that callers depend on

**During extraction (parallel implementation):**
- Shadow mode comparison (old output vs new output, logged for discrepancy)
- Integration tests against the interface, not the implementation
- Contract tests: if extracting a service, define the API contract and test both sides against it

**Post-extraction:**
- Replace characterization tests with proper behavior-based unit tests
- Add tests for edge cases discovered during the migration
- Delete tests that tested implementation details that no longer exist

**The test debt trap:** Refactoring often surfaces the lack of tests. The temptation is to write tests while refactoring. Resist: writing tests and refactoring in the same commit makes it impossible to know whether a failing test is due to a test bug or a refactoring regression. Write the tests first, verify they pass, then refactor.

**Property-based testing for equivalence:** If the refactored function should produce identical outputs to the original for all inputs, property-based testing is highly effective:

```python
from hypothesis import given, strategies as st

@given(
    base_price=st.floats(min_value=0, max_value=10000),
    user_type=st.sampled_from(["standard", "premium", "enterprise"]),
    discount_code=st.one_of(st.none(), st.sampled_from(["SAVE10", "VIP20"]))
)
def test_price_calculation_equivalence(base_price, user_type, discount_code):
    old = legacy_calculate_price(base_price, user_type, discount_code)
    new = new_calculate_price(base_price, user_type, discount_code)
    assert old == new
```

Property-based testing generates hundreds of random inputs. It is far more thorough than a hand-written set of examples for verifying behavioral equivalence.

---

## Part 11: Team and Org Dynamics in Large Refactors

Technical patterns are necessary but not sufficient. Large refactors fail at the organizational level as often as the technical level.

**Common org failure modes:**

**1. The refactor that never ends.** The team commits to a 6-month refactoring effort. At month 4, business pressure demands new features. The refactoring is "paused." The old code and new code coexist permanently. Complexity doubles.
- Prevention: Time-box the refactoring. Define the minimum valuable change. Ship it. Subsequent improvements are incremental, not a second phase of the same project.

**2. No stakeholder buy-in.** Engineering tells product "we need 3 months with no features." Product says no. Stalemate.
- Prevention: Make the business case quantitatively (change failure rate, incident cost, developer time). Don't ask for 3 months; ask for 20% engineering capacity for 6 months. The refactoring happens alongside features.

**3. Knowledge silo.** One engineer understands the legacy system. The refactoring depends on that engineer's availability. They get sick, quit, or get pulled into a different project.
- Prevention: Pair-program the exploration phase. Write the characterization tests in pairs. Document the surprising behaviors. Distribute knowledge before starting the refactoring.

**4. The API consumer problem.** The system being refactored has many callers. A behavior change breaks a caller. The caller team blames the refactoring team.
- Prevention: Define and publish a compatibility contract before starting. Communicate migration timelines. Create an API versioning strategy. Test against caller teams' test suites.

**Staff engineer's role in the org dynamics:**
- Own the communication to stakeholders: metrics, timeline, rollback plan
- Coordinate with dependent teams before breaking changes
- Run the architecture review that confirms the boundary is right before extraction
- Make the go/no-go call at each migration milestone

---

## Part 12: War Stories

### Basecamp's 20-Year Incremental Refactor

Basecamp (formerly 37signals) has operated the same Rails monolith since 2004. Over 20 years, it has been incrementally improved without a full rewrite. Key practices: the "boy scout rule" (every change leaves the code better than you found it); strict module boundaries that prevent the monolith from becoming a ball of mud; willingness to say "this code is fine even if it's old." The result: one of the most successful SaaS products in history, still shipping from a single Rails application.

**The lesson:** Incremental refactoring over decades is sustainable and valuable. Big rewrites are almost never necessary if you maintain discipline continuously.

### Amazon's SOA Migration (2002)

Jeff Bezos issued his famous "API Mandate" in 2002: every team must expose its data and functionality through service interfaces, and teams can only communicate through those interfaces. This forced a decade-long migration from a coupled monolith to a service-oriented architecture. The discipline of the mandate — you *must* go through the API — is what made it work. Teams that found back-channel shortcuts were punished.

**The lesson:** Large-scale architectural change requires organizational authority, not just technical patterns. The strangler fig was the technical pattern; the mandate was the organizational mechanism.

### Uber's "God Monolith" to Microservices (2014-2016)

Uber's original Node.js monolith became a scaling bottleneck as the company grew. The extraction to microservices happened under intense time pressure. The result was hundreds of services deployed before the organization had the observability, service mesh, or on-call practices to manage them. Incidents multiplied. The operational complexity created the "distributed monolith" anti-pattern at scale.

**The lesson:** Extract services at the pace your operations team can absorb. Microservices require investment in observability, deployment automation, and on-call practices that must precede the extraction, not follow it.

### Google's Large-Scale Change Tooling

Google routinely makes changes across billions of lines of code — renaming APIs, updating deprecated patterns, migrating from one library to another. They built tooling (Rosie) to automate the mechanical parts: search for the pattern, apply the transformation, submit the review, monitor the test results. Large-scale changes that would take a human engineer months of mechanical work are automated to run overnight.

**The lesson:** At sufficient scale, even "simple" refactoring tasks require automation. Staff engineers at large companies should invest in tooling for mechanical migrations rather than doing them by hand.

---

## Part 13: L5 vs L6 Calibration Table

| Dimension | L5 (Senior SWE) | L6 (Staff SWE) |
|-----------|----------------|----------------|
| **Scope** | Refactors a module or service | Plans and coordinates extraction of a service from a monolith |
| **Justification** | "This code is hard to work with" | Business case: change failure rate, incident cost, developer velocity impact |
| **Test strategy** | Writes unit tests before refactoring | Defines characterization test strategy, shadow mode comparison, contract tests |
| **Risk management** | Feature flags for the change | Rollback condition defined upfront; go/no-go criteria at each milestone |
| **Database changes** | Applies a migration in one step | Expand and contract across multiple deploy windows; zero-downtime by design |
| **Org coordination** | Notifies team in Slack | Aligns with dependent teams; API contract published; migration timeline communicated |
| **Ambiguity** | Refactors well-understood code | Develops understanding of legacy system before refactoring; documents surprising behaviors |
| **Outcome** | Code is cleaner | Developer velocity measurably improved; change failure rate reduced |

The L6 signal is not technical sophistication. It is **planning completeness**: knowing what can go wrong, having a rollback plan, having communicated the change to all affected parties, and having defined the criteria for calling it done.

---

## Part 14: Anti-Patterns in Large Refactoring

**1. The Parallel Universe Rewrite.** A new team is formed to build "v2" while the old team maintains "v1." Both systems grow. The v2 team discovers they need all the edge cases from v1. The migration date slips. Eventually one system or the other is abandoned.
- Detection: "v2 team" in org chart; two separate codebases serving the same function
- Fix: One team; Strangler Fig; incremental migration

**2. Refactoring Without Tests.** "We'll add tests after." After never comes. The refactored code has no characterization baseline; every subsequent change is risky.
- Detection: Commit history shows refactoring without corresponding test additions
- Fix: Characterization tests first; no refactoring commit without test coverage

**3. The Scope Creep Refactor.** The plan was to extract the payment module. Three months in, the team is also refactoring the user model and the notification system because "we're already in there."
- Detection: The "refactoring" PR touches files unrelated to the original goal
- Fix: Mikado Method discipline: work on one goal at a time; create tickets for discovered issues but don't fix them now

**4. Abandoning the Strangler.** The routing layer is in place; the new implementation is partially built; the team pivots to a new project. The routing layer stays in the codebase as dead weight for two years.
- Detection: Feature flags with a creation date > 90 days ago that aren't at 100% rollout
- Fix: Define completion criteria and timeline before starting; add flag removal to the same epic

**5. The Distributed Monolith.** Services are extracted, but they share a database. A schema change in one service requires coordination with every service that shares the table. The operational complexity of microservices with none of the independence.
- Detection: "If we deploy service A, we need to coordinate with teams B and C"
- Fix: Each service owns its data; cross-service data access is via API, not direct DB access

**6. Underestimating Data Migration.** The code refactoring is fast; the data migration takes months. Billions of rows need to be backfilled. The new schema has been deployed for months but old data is still in the old schema.
- Detection: Backfill that takes weeks or months, blocking the "contract" phase
- Fix: Estimate data migration time *before* starting; test backfill performance at production scale; plan for incremental backfills

---

## Part 15: Exercises

**Exercise 1:** Take a God class (a class with 20+ methods and 500+ lines) from your codebase or a hypothetical scenario. Apply the Mikado Method: state the goal (extract a specific responsibility), attempt it, identify the prerequisites, draw the dependency tree. Do not write any code yet.

**Exercise 2:** Design the Expand and Contract migration for this schema change: rename the `user_email` column to `email` on a 50M-row table with 200 QPS of reads and writes, zero-downtime requirement.

**Exercise 3:** Write three characterization tests for a function you know is buggy. Record its actual behavior, not its correct behavior. Then fix the bug and update the tests to reflect the correct behavior. Notice the separation.

**Exercise 4:** Design the shadow mode comparison for migrating a pricing calculation from a legacy formula to a new one. Include: where the comparison runs, what discrepancies are logged, what threshold triggers an alert, and what happens with the discrepancy data.

**Exercise 5:** Your team has a monolith with a `NotificationService` that handles email, SMS, and push notifications. Design the extraction: the API contract, the data ownership decision, the dual-write period, and the criteria for calling the extraction complete.

**Exercise 6:** A team proposes a 6-month feature freeze to "fix our technical debt." Write the counter-proposal: how would you achieve the same outcome through incremental refactoring without a feature freeze? What are the tradeoffs?

---

## Part 16: Five-Level Progression

**L1 (Junior SWE):** Refactors a single function with a clear improvement (extract variable, rename, remove duplication). Change is small and self-contained.

**L2 (SWE):** Refactors a class or module. Adds tests before changing. Opens a focused PR with a clear explanation of the improvement. Does not break callers.

**L3 (Senior SWE I):** Designs the refactoring of a component. Uses Branch by Abstraction for internal components. Writes characterization tests. Coordinates with the team before changes that affect shared interfaces.

**L4 (Senior SWE II / L5):** Designs and executes service extraction from a monolith for a small, well-understood component. Uses Strangler Fig with feature flags. Defines rollback criteria. Communicates with dependent teams.

**L5 (Staff / L6):** Designs the multi-quarter migration of a large, tightly-coupled system. Makes the business case. Defines the boundary with DDD. Coordinates across multiple teams. Instruments migration progress. Defines the operational readiness requirements before service extraction begins. Calls "done" and ensures cleanup happens.

---

## Part 17: One-Liners for Recall

1. "A refactor that can't be deployed is a liability, not an improvement."
2. "Characterization tests: test what the code does, not what it should do."
3. "The Strangler Fig: intercept, implement, route, retire — in that order."
4. "Expand and Contract: never rename a column in one migration."
5. "The distributed monolith: extracted but still coupled — all the operational cost, none of the independence."
6. "Feature flags are refactoring infrastructure, not just product experimentation tools."
7. "The Mikado Method: attempt → fail → revert → address prerequisite → retry."
8. "Shadow mode: run both, use old result, log discrepancies — validate before routing traffic."
9. "A business case for refactoring: change failure rate × incidents per year × cost per incident = annual tech debt tax."
10. "The parallel universe rewrite never finishes because v2 always needs the edge cases v1 spent years accumulating."

---

## Part 18: Interview Application

**When asked "How would you refactor a legacy system?":**

Signal: Not "rewrite it" and not "gradually improve it" (too vague). The signal is naming specific patterns and demonstrating awareness of risk.

**Template answer:**
"I'd start with characterization tests to understand current behavior before touching anything. Then I'd identify the seams — places where the system can be split without affecting the whole — and apply Branch by Abstraction or the Strangler Fig depending on whether the change is internal or service-level. For any database changes, I'd use Expand and Contract: additive schema changes first, dual-write period, then clean up old schema after the new one is validated. I'd use feature flags throughout to enable incremental rollout with dark-launch comparison. The criteria for calling it done: the old code path is deleted, the flags are removed, and the key health metrics (change failure rate, P99 latency) haven't regressed."

**Brainstorming Q&A:**

**Q: How do you handle a refactoring that requires changing a shared database schema used by 5 different services?**

The right answer requires three components:

1. **The technical pattern.** Use Expand and Contract across all services simultaneously. Add the new schema element (new column, new table, new index). Update all 5 services to write to both old and new. Backfill historical data. Once all services are confirmed writing to the new schema, switch reads. Verify. Drop the old schema element.

2. **The coordination mechanism.** A shared schema change across 5 teams requires a migration coordinator role (typically Staff engineer). Write a migration spec that defines: what is changing, what each service must do in each phase, the timeline for each phase, and the go/no-go criteria. Each team's tech lead signs off on their service's readiness before the phase advances.

3. **The rollback plan.** Because the Expand and Contract phases are independent deployments, rollback is defined per phase. Rollback from Phase 1 (added new column): drop the column. Rollback from Phase 2 (all writing to both): revert application code to only write old. Rollback from Phase 3 (reads switched): revert reads to old column. No phase rollback cascades to previous phases — each is independently safe.

**Q: A team says "we can't refactor because we don't understand the code." How do you respond?**

"That's exactly backwards: you refactor to understand the code. The first step is not changing behavior — it's adding characterization tests. Running the existing code against representative inputs and recording its outputs tells you what it does. Then you rename, extract, and reorganize to make the structure match your improving understanding. The structure change doesn't change behavior (tests enforce this), but it makes the next change safer. You build understanding incrementally through the refactoring, not before it."

---

## Part 19: Managing Technical Debt Strategically

Technical debt is not inherently bad. The term comes from Ward Cunningham, who used it to describe a specific tradeoff: shipping code you know is imperfect in order to learn faster, with the intention of paying it back later. The debt metaphor is precise: like financial debt, it accrues interest (slowing future development), can be refinanced (restructured without eliminating it), and should be paid down deliberately rather than ignored.

**The Debt Quadrant (Martin Fowler):**

|           | Reckless | Prudent |
|-----------|----------|---------|
| **Deliberate** | "We don't have time for design" | "We must ship now and will refactor later" |
| **Inadvertent** | "What's layering?" | "Now we know how we should have done it" |

Only Prudent-Deliberate debt is acceptable. Reckless debt is not a business decision — it is engineering negligence. Inadvertent debt is unavoidable but should be addressed as soon as it's recognized.

**Making the business case for paying down debt:**

The productivity tax model:
- Measure the current velocity (story points per sprint, or PRs per week)
- Measure the change failure rate (% of PRs that cause incidents)
- Calculate the cost: (incidents per month × average incident duration × fully-loaded eng cost per hour)
- Project the improvement: "Teams that reduced complexity in similar systems saw 30-40% velocity improvement within 6 months"
- Calculate the investment: (engineer-weeks × cost per engineer-week)
- Calculate break-even: investment / (monthly cost savings post-refactoring)

A concrete example: "Our payment service has a 15% change failure rate. We deploy 4 times per week; 60 deploys per month. 9 incidents per month × 2-hour average resolution × $500/hour = $9,000/month. The refactoring will take 8 engineer-weeks = $80,000. Break-even: 9 months. Beyond 9 months, we are saving $9,000/month." That is a business case. "The code is messy" is not.

**The Boy Scout Rule:** Leave the code better than you found it. This is not permission to rewrite adjacent modules while fixing a bug. It means: if you touch a file, clean up one small thing in that file — a confusing variable name, a missing type annotation, an unused import. Applied consistently, this prevents incremental decay without requiring dedicated refactoring time.

---

## Part 20: Code Ownership and Refactoring

Large refactors often span module boundaries, and module boundaries often correspond to team boundaries. Understanding code ownership is a prerequisite for coordinating a large refactor.

**Ownership models:**

**Strong ownership:** Each module has one team. No other team can merge changes to that module without the owner's review. Advantages: clear accountability; the owner develops deep expertise. Disadvantages: refactors that cross boundaries require inter-team coordination; bottleneck if owner team is busy.

**Weak ownership:** Teams have preferred areas of ownership, but any engineer can contribute to any module. Advantages: flexibility; no bottlenecks. Disadvantages: inconsistency accumulates; no one feels responsible for long-term quality.

**Collective ownership:** The codebase belongs to everyone. Common in small teams. Breaks down past ~20 engineers — no one has enough context to review changes everywhere.

**The Staff engineer's role:** In a large refactor, you are often changing code owned by other teams. The rules:
1. Give the owning team advance notice of the plan and timeline
2. Include them in the design of the interface
3. Do not merge changes to their code without their review
4. Offer to pair-program or co-author the changes in their area
5. Make the change easy to review: small PRs, clear commit messages, no unrelated changes

Violating these rules creates org friction that can derail the entire refactoring effort. Technical correctness is necessary but not sufficient — you need organizational alignment.

---

## Part 21: Refactoring Legacy Data Models

Data model changes are the riskiest part of any large refactor. They require both schema migrations and data migrations, which have different properties:

**Schema migrations** (DDL changes): Fast to apply; reversible with drop; but may block reads/writes during execution on large tables.

**Data migrations** (DML changes): Slow on large tables; can run incrementally; difficult to reverse if the old data is overwritten.

**The three-part migration structure:**

**Part A: Schema change only (additive)**
- Add new tables, new columns (nullable or with defaults)
- Add new indexes
- All existing code still works unchanged

**Part B: Data migration (backfill)**
- Populate new structures from old data
- Run in batches: `UPDATE table SET new_col = transform(old_col) WHERE id BETWEEN ? AND ? AND new_col IS NULL`
- Rate-limit batches to avoid production impact
- Monitor replication lag; pause if it falls behind

**Part C: Schema cleanup (destructive)**
- Drop old columns, old tables
- Remove indexes no longer needed
- Only execute after all application code has been migrated to the new schema and verified

**Data integrity during migration:** When both old and new data structures exist simultaneously (during Part A → B transition), write code that keeps them consistent:

```python
def update_user_profile(user_id, data):
    with db.transaction():
        # Write to both old and new schema
        db.execute("UPDATE users SET name = ? WHERE id = ?", [data['name'], user_id])
        # New schema: split name into first/last
        first, _, last = data['name'].partition(' ')
        db.execute("UPDATE user_profiles SET first_name = ?, last_name = ? WHERE user_id = ?",
                   [first, last, user_id])
```

This dual-write ensures both schemas are consistent, enabling rollback to the old schema at any point before Part C.

---

## Part 22: Brownfield vs Greenfield Design

A Staff engineer must understand the difference between designing systems from scratch (greenfield) and improving existing ones (brownfield). The patterns, constraints, and success criteria differ significantly.

**Greenfield:** You control all decisions. The main risk is over-engineering. The temptation is to design for scale and flexibility that will never be needed. The correct approach: design for the next 18 months of known requirements; build extension points only for changes you are highly confident will occur; accept that you will refactor when reality diverges from the initial design.

**Brownfield (most of real engineering):** You inherit constraints. The main risk is under-estimating those constraints. The temptation is to design the "right" solution without accounting for what the existing system makes impossible or expensive.

**Brownfield design principles:**
1. Understand the existing system before proposing changes. Read the code. Run it. Break it. Understand the implicit contracts.
2. Make the minimum change that achieves the goal. Do not redesign the whole system to fix one module.
3. Work with the grain of the existing system. If the existing code is object-oriented, the refactored code should be object-oriented. A design that requires changing the paradigm of everything around it will fail.
4. Prefer reversible changes. If the refactoring direction turns out to be wrong, can you go back?
5. Define what "better" means quantitatively. If you can't measure improvement, you can't know when you're done.

---

## Part 23: Pre-Interview Drill

**1.** What is the Strangler Fig pattern? Name the four steps.
**2.** What is the difference between Strangler Fig and Branch by Abstraction? When do you use each?
**3.** What is a characterization test? Why do you write it before refactoring?
**4.** What is Expand and Contract? Walk through the four phases for renaming a database column.
**5.** What is the Mikado Method? What is the discipline that makes it work?
**6.** What is the distributed monolith anti-pattern? How do you detect and fix it?
**7.** How do you make the business case for a large refactoring effort? What metric do you use?
**8.** What is shadow mode in a code migration? What does it validate?
**9.** Why do big rewrites usually fail? What is the fundamental problem?
**10.** How do you handle a refactoring that requires changes to a shared database used by 5 different services?
**11.** What is the Boy Scout Rule? What are its limits?
**12.** How does code ownership affect a large refactoring effort? What process do you use when changing code owned by another team?

---

## Part 24: Key Takeaways

```
╔═══════════════════════════════════════════════════════════════════╗
║          KEY TAKEAWAYS: REFACTORING LARGE SYSTEMS                ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║  1. Big rewrites almost never finish. Use incremental patterns.   ║
║                                                                   ║
║  2. Strangler Fig: intercept → implement → route → retire.        ║
║     Routing layer must stay simple.                               ║
║                                                                   ║
║  3. Branch by Abstraction: for internal component replacement.    ║
║     Interface → old impl → new impl → switch → delete old.        ║
║                                                                   ║
║  4. Expand and Contract: the only safe database refactoring.      ║
║     Never rename a column in one migration.                       ║
║                                                                   ║
║  5. Characterization tests first. Record actual behavior.         ║
║     Refactor only after the tests pass on old code.               ║
║                                                                   ║
║  6. Shadow mode: run both, use old result, log discrepancies.     ║
║     Validate before routing any real traffic.                     ║
║                                                                   ║
║  7. Feature flags have a lifespan. Remove within 90 days.         ║
║                                                                   ║
║  8. The business case requires numbers. Change failure rate ×     ║
║     incident cost = the annual tax of current debt.               ║
║                                                                   ║
║  9. The distributed monolith is the worst outcome of extraction:  ║
║     all microservice complexity, none of the independence.        ║
║                                                                   ║
║  10. Org coordination is as important as technical patterns.      ║
║      Advance notice, API contracts, inter-team reviews.           ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
```

---

## Part 25: Additional Exercises

**Exercise 7:** You're asked to extract the `AuthenticationService` from a Ruby on Rails monolith. The service authenticates 50M users. Design: what is the extraction boundary? What data does it own? How do you migrate session management? What is the rollback plan?

**Exercise 8:** A legacy pricing engine uses a complex formula accumulated over 10 years. It has no tests. You need to replace the formula with a new one that handles additional edge cases. Design the full migration: characterization tests, shadow mode, traffic ramp plan, monitoring.

**Exercise 9:** Your team has been working on a "refactoring" for 4 months. The original scope was one module; it has expanded to 6 modules. The feature freeze has been extended twice. No code has been deployed to production from the refactoring branch. What has gone wrong? How do you recover?

**Exercise 10:** Design the Mikado dependency tree for this goal: "Replace the in-process job queue with a Redis-based distributed queue." Start from the goal, identify prerequisites, and draw the tree to a depth of at least 3 levels.

---

## Part 26: Homework

**Assignment 1:** Take a real legacy codebase (your own, open source, or a tutorial project). Pick one God class. Write 5 characterization tests for its most important method. Then design — but don't implement — the extraction of one responsibility to a new class. Write the Mikado tree.

**Assignment 2:** Find a large, successful software project that was refactored incrementally rather than rewritten (Rails, Linux kernel, PostgreSQL). Write a 500-word case study: what were the key decisions that kept it maintainable? What patterns did they use (even informally)?

**Assignment 3:** Design the Expand and Contract migration for this scenario: the `orders` table has an `address` column (single VARCHAR). Split it into `street`, `city`, `state`, `postal_code`, `country`. The table has 200M rows. 5,000 QPS of reads. Write the migration plan, including batch sizing, backfill strategy, and the dual-write application code.

---

## Part 27: Seam-Based Decomposition — Finding the Cut Points

Michael Feathers introduced the concept of "seams" in "Working Effectively with Legacy Code." A seam is a place in the code where you can change behavior without modifying the code in that place. Seams are the safe cut points for refactoring.

**Types of seams:**

**Object seam:** A virtual method or interface allows behavior to be substituted. The most powerful seam in OOP.
```python
# Seam: PaymentGateway is injected — behavior can be substituted
class OrderProcessor:
    def __init__(self, gateway: PaymentGateway):
        self.gateway = gateway

    def process(self, order):
        return self.gateway.charge(order.amount)
```

**Link seam:** The behavior changes based on which library or module is linked at build time. Less common in modern languages.

**Preprocessing seam:** A macro or conditional compilation changes behavior. Common in C/C++.

**Finding seams in a legacy codebase:**
1. Look for constructor new-calls (`new DatabaseConnection()` inside a method — not a seam; `DatabaseConnection` passed as argument — a seam)
2. Look for static method calls (`DateTime.now()` — not a seam; `clock.now()` where `clock` is injected — a seam)
3. Look for global state (`Config.database_url` — not a seam; `config.database_url` where `config` is injected — a seam)
4. Look for `if/else` blocks that select behavior based on a type or mode — these are candidates for polymorphism (Replace Conditional with Polymorphism)

**The seam test:** If you can change the behavior of a code path *without editing that specific file*, there is a seam. If every change requires editing the file, you need to introduce a seam first.

**Introducing seams into legacy code (breaking dependencies):**
- Extract parameter: move the `new DatabaseConnection()` out of the method, pass it as a parameter
- Extract interface: define an interface for the dependency; create a production implementation and a test double
- Subclass and override: create a subclass in tests that overrides the specific method you want to control

The goal is not to make the code "testable" in some abstract sense. It is to enable you to change one part of the behavior without accidentally changing another — which is exactly what a large refactoring requires.

---

## Part 28: Domain-Driven Design as a Boundary Guide

When extracting services from a monolith, the hardest decision is: where does the boundary go? Domain-Driven Design (DDD) provides the vocabulary and tools for this decision.

**Key DDD concepts for refactoring:**

**Bounded Context:** A named, explicit boundary within which a domain model applies. Inside the boundary, terms have precise meanings. Outside the boundary, the same word may mean something different.

Example: "Order" in the order management context means a customer's purchase in progress. "Order" in the fulfillment context means a shipping instruction. These are the same word but different concepts — they belong in different bounded contexts.

**Ubiquitous Language:** The domain vocabulary used consistently by engineers and domain experts within a bounded context. If engineers call it an "order" and the business calls it a "transaction," alignment is broken.

**Context Map:** A diagram showing how bounded contexts relate to each other. Types of relationships:
- Partnership: two contexts evolve together; teams coordinate closely
- Shared Kernel: two contexts share a small, explicit subset of the domain model
- Customer/Supplier: one context (downstream) depends on another (upstream); upstream makes API commitments
- Conformist: downstream conforms to upstream's model with no influence
- Anti-Corruption Layer (ACL): downstream translates upstream's model rather than using it directly

**Using DDD to find extraction boundaries:**

1. **Event storming:** Gather engineers and domain experts; write down domain events on stickies (UserRegistered, OrderPlaced, PaymentProcessed). Group events by the aggregate they affect (User, Order, Payment). Natural aggregates reveal bounded contexts.

2. **Look for translation points:** If you see code that converts between two representations of the "same" concept, you have found a context boundary. The translation is the seam.

3. **Look for data ownership:** Which team/module is the authoritative source for this data? Data ownership reveals context boundaries.

**The anti-pattern:** Defining extraction boundaries based on technical layers (all database code together, all HTTP code together). This produces a technically-organized but domain-incoherent architecture. Services organized around technical function instead of domain function will have high coupling across services and low cohesion within them.

---

## Part 29: Refactoring Code Reviews — What to Look For

Reviewing a refactoring PR requires different attention than reviewing a feature PR. The primary question is not "does this add the right feature?" but "does this change behavior?"

**Reviewer checklist for refactoring PRs:**

- [ ] Does the PR include characterization tests or existing tests that cover the changed behavior?
- [ ] Are all tests passing (including tests of callers)?
- [ ] Has the interface changed? If so, have all callers been updated?
- [ ] Is there a database migration? Does it follow Expand and Contract?
- [ ] Does the PR include both the old and new code paths (for Strangler/Branch by Abstraction) or only the new path?
- [ ] Is the feature flag properly configured? (default off for new path; cleanup ticket exists)
- [ ] Has the performance impact been considered? (new abstraction layers can add latency)
- [ ] Is the scope contained? (no unrelated changes)
- [ ] Does the PR description explain what it does and why? (crucial for future archaeology)

**The most common refactoring review error:** Approving a refactoring because "it looks cleaner" without verifying that behavior is preserved. Cleaner code with changed behavior is a bug, not an improvement.

**When to ask for a split:** If the PR includes both the refactoring and a behavior change, ask for it to be split. The refactoring should be a separate, reviewable change that makes the behavior change easier. Mixing them makes both harder to review.

---

## Part 30: Refactoring and Performance

A common objection to refactoring is "the abstractions will be slower." This is sometimes true and needs to be addressed directly.

**The performance tradeoff:**

Abstractions (interfaces, indirection, dependency injection) add overhead: a virtual method call is slower than a direct function call; an additional layer of indirection adds memory allocation; a Strategy pattern is slower than a hardcoded if/else. In most application code, this overhead is negligible (microseconds vs milliseconds).

**When it matters:**
- Hot paths: code called millions of times per second (serialization, parsing, request routing)
- Tight loops: inner loop of a computation-heavy algorithm
- Memory-constrained environments: mobile apps, embedded systems

**The approach:**
1. Profile before optimizing. Most code is not performance-critical. Premature optimization is the root of much unnecessary complexity.
2. Refactor first for clarity; then profile. If the profiler identifies the abstraction as a hotspot, optimize that specific location.
3. Measure the actual overhead. A virtual call costs ~1-3ns. If the function does 1μs of work, the overhead is 0.1-0.3%. Not worth pre-optimizing.
4. When abstractions must be removed for performance: isolate the optimization. Everywhere else remains clean.

**Example:**
```python
# Clean abstraction — correct for most cases
class PriceCalculator(Protocol):
    def calculate(self, order: Order) -> Decimal: ...

# Optimized hot path — only when profiler confirms bottleneck
# (inline the calculation, avoid the virtual dispatch)
def calculate_price_fast(amount: float, discount_pct: float) -> float:
    return amount * (1 - discount_pct / 100)
```

The Staff engineer's position: "We refactor for correctness and maintainability first. Performance optimization is applied after profiling confirms the need. We don't avoid refactoring because of hypothetical performance concerns."

---

## Part 31: The Refactoring Runway

Large refactors often fail because they try to achieve too much too soon. The refactoring runway is the concept of making consistent, small, deployable progress — without long-lived branches or feature freezes.

**Runway rules:**
1. Every refactoring commit is deployable to production
2. No refactoring branch lives longer than one day without merging
3. Each PR is < 300 lines changed (smaller is better for review quality)
4. No refactoring PR changes both structure and behavior
5. Progress is measured in completed, deployed increments — not in percentage of the total plan done

**Trunk-based development for refactors:** The hardest version of the runway discipline is trunk-based development: all refactoring goes directly to main, behind feature flags, with no long-lived feature branches. This forces every intermediate state to be production-safe.

The benefit: no merge conflicts; no "rebase tax" when feature development continues alongside the refactoring; no "big bang merge" at the end.

The cost: requires mature tooling (feature flags, shadow mode, thorough CI). If your deployment pipeline takes 2 hours, a daily merge cadence may not be feasible.

**Practical approach:** Aim for weekly merges at minimum. Each weekly merge should represent one meaningful, testable, deployable step in the Mikado tree.

---

## Part 32: Quick Reference — Refactoring Pattern Selection

| Scenario | Recommended Pattern |
|----------|---------------------|
| Replacing an external service / API | Strangler Fig |
| Replacing an internal component | Branch by Abstraction |
| Renaming / restructuring a database column | Expand and Contract |
| Extracting a microservice from a monolith | Strangler Fig + Expand and Contract |
| Replacing a calculation/algorithm | Shadow Mode + feature flag |
| Dealing with no tests | Characterization Tests first |
| Navigating refactoring dependencies | Mikado Method |
| Incrementally improving code quality | Boy Scout Rule + small PRs |
| Splitting a God class | Seam identification → Branch by Abstraction |
| Migrating shared DB schema across teams | Expand and Contract + migration coordinator |

---

## Part 33: Common Code Smells That Signal Refactoring Need

**God Class / God Object:** One class does everything. Symptoms: 500+ lines; dozens of unrelated methods; imports from many different modules. Fix: identify responsibilities, extract to smaller classes.

**Long Method:** A method > 20 lines is suspicious; > 50 lines is almost always wrong. Symptoms: nested loops and conditionals; requires scrolling to read. Fix: Extract Method for each logical step.

**Feature Envy:** A method in class A is more interested in class B's data than A's own data. Symptom: `order.customer.address.city`. Fix: move the behavior to the class that owns the data.

**Data Clumps:** Three or more data items that always appear together (`first_name, last_name, email`). Fix: extract into an object (`UserIdentity`).

**Primitive Obsession:** Using primitives (strings, ints) for domain concepts. `price = 99.99` vs `price = Money(99.99, currency="USD")`. Fix: introduce value objects.

**Shotgun Surgery:** A single change requires editing many different classes. Symptom: a PR that touches 15 files for one behavior change. Fix: consolidate related behavior; the Strangler Fig or service extraction is often the answer.

**Divergent Change:** A single class changes for many different reasons (payment changes, UI changes, analytics changes all require edits to OrderProcessor). Fix: split by reason for change (Single Responsibility Principle).

Recognizing smells is the first step. The second step is choosing the right pattern — not reflexively "cleaning up" but applying the right structural change for the specific smell.

---

## Part 34: Reference Table — Refactoring Vocabulary

| Term | Definition | Source |
|------|-----------|--------|
| Strangler Fig | Replace a system incrementally by routing traffic from old to new | Martin Fowler |
| Branch by Abstraction | Replace a component by creating an interface, implementing both old and new, then switching | Martin Fowler |
| Expand and Contract | Database change in 4 phases: add new → backfill → switch reads → drop old | Pramod Sadalage |
| Characterization Test | Test that records existing behavior (including bugs) to prevent regression during refactoring | Michael Feathers |
| Mikado Method | Work backward from goal; attempt → fail → revert → address prerequisite | Ellnestam & Brolund |
| Seam | A place where behavior can be changed without modifying the code at that point | Michael Feathers |
| Bounded Context | A named boundary within which a domain model has consistent meaning | Eric Evans (DDD) |
| Shadow Mode | Run new and old implementations; use old result; log discrepancies | Operations best practice |
| Dark Launch | Deploy new feature to production without exposing it to users; validate at scale | Feature flag pattern |
| Boy Scout Rule | Leave the code better than you found it (small, continuous improvement) | Robert C. Martin |
| Technical Debt | Known imperfection shipped deliberately; accrues interest as future maintenance cost | Ward Cunningham |
| Distributed Monolith | Extracted services that remain tightly coupled; worst of both worlds | Industry anti-pattern |
| God Class | A class that does too much; violates Single Responsibility Principle | Riel (OOP anti-pattern) |
| Feature Envy | A method that accesses another class's data more than its own | Fowler (code smell) |

---

## Part 35: Incremental Architecture Evolution

Large-scale refactoring is a subset of a broader skill: evolving system architecture incrementally. Architecture does not need to be designed all at once. It can be grown.

**The evolutionary architecture principles (Ford, Parsons, Kua):**

1. **Fitness functions:** Define explicit criteria for architectural quality — coupling metrics, performance SLOs, test coverage thresholds. Automate them. A fitness function that runs in CI prevents architectural drift rather than detecting it months later.

2. **Incremental change:** Every architectural change should be deployable in multiple small steps, each of which leaves the system in a valid state.

3. **Appropriate coupling:** Some coupling is necessary and intentional. The goal is not zero coupling (an unreachable state in any real system) but appropriate coupling: coupling that matches the domain model rather than being an accident of implementation history.

**Architectural patterns that enable evolution:**

**Hexagonal architecture (ports and adapters):** The core business logic has no dependencies on external systems. It defines ports (interfaces); adapters implement those interfaces for specific external systems (database, message queue, HTTP). To replace the database, change the adapter — the core logic is untouched.

```
[Core Domain Logic]
    ↓ (defines interface)
[Port: UserRepository]
    ↓ (implemented by)
[PostgreSQL Adapter] or [DynamoDB Adapter] or [In-Memory Adapter (tests)]
```

**Event-driven architecture for loose coupling:** Services publish domain events rather than calling each other directly. A new service can subscribe to existing events without requiring changes to the publisher. The monolith can begin publishing events while still handling all logic internally; new services subscribe and gradually take ownership of behavior.

**Anti-corruption layer for legacy integration:** When integrating a new service with a legacy system, the new service should not model itself on the legacy data model. Instead, it implements an ACL — a translation layer that converts the legacy model into the new service's domain model. Changes to the legacy system do not propagate into the new service.

---

## Part 36: The "Boy Scout Rule" at Scale

At the individual level, the Boy Scout Rule means cleaning up small things as you encounter them. At the Staff level, it means establishing team-wide practices that keep the codebase improving continuously.

**Team-level Boy Scout practices:**

**Cleanup PR quota:** Each engineer is expected to open one "cleanup PR" per sprint — renaming something confusing, adding missing tests, simplifying a complex block. These are separate from feature work. They are reviewed quickly and merged the same day. Over time, they compound significantly.

**Complexity ceiling:** Define a complexity ceiling for the codebase: no function > 30 lines; no class > 200 lines; no file > 500 lines. PRs that violate the ceiling require explicit justification. This creates a forcing function for ongoing refactoring.

**Technical debt tracker:** A living document (not a Jira black hole) where engineers record technical debt with severity, impact, and estimated fix time. Reviewed in quarterly planning. High-impact items are scheduled as real engineering work, not deferred indefinitely.

**The compounding effect:** A codebase that is consistently 1% better per sprint is dramatically better in 2 years. The key is consistency: small, steady improvement beats episodic large refactors that cause instability.

**What this looks like in practice:** 
- Junior engineer changes a method name in the same file they're editing for a feature: +1 clarity point
- Mid-level engineer adds the missing test for the function they just called: +1 coverage point
- Senior engineer extracts the third copy of the same logic into a shared utility: -1 duplication point
- Staff engineer removes the feature flag that reached 100% rollout 3 months ago: -1 complexity point

None of these are large efforts. Together over a year they transform a codebase.

---

## Part 37: Case Study — Shopify's Modular Monolith

Shopify runs one of the world's largest e-commerce platforms on a Ruby on Rails monolith — intentionally. Rather than decomposing into microservices, they invested heavily in modular structure within the monolith.

**The approach:**
- The codebase is divided into domains (checkout, fulfillment, payments, merchant admin)
- Each domain has explicit API boundaries — even internal callers must use the API, not access internal tables
- Boundary violations fail in CI (a custom linting rule checks cross-domain database queries)
- Each domain is owned by one team; cross-domain changes require the owning team's review

**The outcome:** Shopify handles millions of orders on Black Friday from a single deployable unit. Teams can work independently within their domain. New domains are added by defining their API boundary and creating a new folder under the domains directory.

**The lesson for refactoring:** The goal of service extraction is organizational independence and technical isolation — not deployment independence for its own sake. A well-structured modular monolith with enforced boundaries may deliver the organizational benefits of microservices without the operational overhead. The decision to extract a service should be based on concrete needs (scaling, independent deployment velocity, technology choice), not on a theoretical architecture principle.

---

## Part 38: Staff Engineer's Refactoring Playbook (Condensed)

When handed a large, messy system to improve:

**Week 1: Understand**
- Read the code; don't edit
- Run it locally; break it deliberately
- Write characterization tests for the most important paths
- Map the dependencies (what does this module depend on? What depends on it?)
- Document the surprising behaviors

**Week 2: Plan**
- Define the goal: what is the measurable improvement?
- Choose the pattern: Strangler Fig, Branch by Abstraction, Expand and Contract, or combination
- Draw the Mikado tree: what must be done first?
- Identify the risks: what can go wrong? What is the rollback plan?
- Communicate to stakeholders: timeline, milestones, success criteria

**Weeks 3-N: Execute**
- Work the Mikado tree leaves-first
- Every change is deployable; every PR is small
- Shadow mode before routing traffic
- Monitor at each traffic increase milestone
- Flag each completed prerequisite; celebrate progress

**Final week: Clean up**
- Delete the old code path
- Remove the feature flags
- Update documentation
- Conduct a post-mortem: what did we learn? What would we do differently?
- Publish the metrics improvement (change failure rate before vs after)

---

## Part 39: Why This Chapter Matters for Google L5

Google L5 (Senior SWE) is expected to:
- Own technical solutions for their team
- Contribute to the direction of the system they work in
- Work effectively across team boundaries when needed

Refactoring large systems is a quintessential L5 task because it requires:
1. Technical depth (knowing the patterns: Strangler Fig, Expand and Contract, Branch by Abstraction)
2. Technical breadth (understanding how the system connects to its callers, databases, and downstream services)
3. Cross-team influence (coordinating with dependent teams, getting buy-in, managing migration contracts)
4. Planning discipline (Mikado Method, rollback criteria, measurement)

A candidate who can describe these patterns with precision, can reason about the failure modes (distributed monolith, scope creep, characterization test gaps), and can make the business case for the investment — that candidate demonstrates L5 competence on the engineering excellence dimension.

The interview question "Tell me about a time you improved a system significantly" is a direct invitation to tell a refactoring story. The STAR structure:
- **S/T:** Legacy system, specific problem (change failure rate, developer friction, performance)
- **A:** Characterization tests, Strangler Fig, feature flags, Expand and Contract — name the patterns
- **R:** Measurable improvement — change failure rate dropped from X to Y, deployment time reduced by Z

---

## Part 40: Chapter Final Summary

Refactoring large systems is the discipline of continuous, incremental improvement — changing systems safely while they serve production traffic, without ever needing a "big bang" cutover that can fail catastrophically.

The toolkit:
- **Strangler Fig:** for replacing external services and subsystems
- **Branch by Abstraction:** for replacing internal components
- **Expand and Contract:** for evolving database schemas
- **Characterization Tests:** for capturing behavior before changing it
- **Mikado Method:** for navigating refactoring dependencies
- **Shadow Mode:** for validating new implementations before routing traffic
- **Feature Flags:** for incremental traffic migration with instant rollback

The org skills:
- Making the quantitative business case
- Coordinating across teams with clear contracts
- Maintaining trunk-based development discipline
- Defining and communicating rollback criteria

The pattern that kills refactoring projects:
- Scope creep (solve one problem at a time)
- Long-lived branches (merge frequently, stay deployable)
- No tests (characterization tests first)
- Distributed monolith (services must own their data)
- Big Bang cut-over (incremental traffic migration, always)

Large-scale refactoring is not glamorous. It does not ship new features. But it is the work that makes all future work faster, safer, and more enjoyable. Staff engineers who do this well create compounding returns for their teams for years.

---

> "Every big rewrite I've seen has failed. The teams that succeed improve their systems incrementally, one safe change at a time." — Adapted from practices described by Martin Fowler, Michael Feathers, and Sam Newman.

---

## Part 41: Code Examples — Patterns in Practice

### Strangler Fig: HTTP-Level Routing

```python
# strangler_router.py
import httpx
from feature_flags import get_flag

class StranglerRouter:
    def __init__(self, old_base_url: str, new_base_url: str):
        self.old = old_base_url
        self.new = new_base_url

    def route(self, request, user_id: str):
        pct = get_flag("new_checkout_rollout_pct", default=0)
        # Deterministic routing: same user always hits same service
        use_new = (hash(user_id) % 100) < pct
        target = self.new if use_new else self.old
        resp = httpx.request(
            method=request.method,
            url=f"{target}{request.path}",
            headers=request.headers,
            content=request.body,
        )
        return resp
```

Key detail: deterministic routing by `hash(user_id) % 100`. The same user always hits the same service during the migration. This avoids split-brain issues where a user experiences both old and new behavior in the same session.

---

### Branch by Abstraction: Swapping Storage Backend

```python
# notification_store.py
from typing import Protocol

class NotificationStore(Protocol):
    def save(self, notification_id: str, data: dict) -> None: ...
    def get(self, notification_id: str) -> dict | None: ...

# Old implementation
class PostgresNotificationStore:
    def __init__(self, db):
        self.db = db

    def save(self, notification_id: str, data: dict) -> None:
        self.db.execute(
            "INSERT INTO notifications (id, data) VALUES (%s, %s)",
            [notification_id, json.dumps(data)]
        )

    def get(self, notification_id: str) -> dict | None:
        row = self.db.fetchone(
            "SELECT data FROM notifications WHERE id = %s", [notification_id]
        )
        return json.loads(row['data']) if row else None

# New implementation
class DynamoNotificationStore:
    def __init__(self, table):
        self.table = table

    def save(self, notification_id: str, data: dict) -> None:
        self.table.put_item(Item={"id": notification_id, **data})

    def get(self, notification_id: str) -> dict | None:
        resp = self.table.get_item(Key={"id": notification_id})
        return resp.get("Item")

# Injection point: flag controls which is returned
def get_notification_store(feature_flags, db, dynamo_table):
    if feature_flags.is_enabled("dynamo_notifications"):
        return DynamoNotificationStore(dynamo_table)
    return PostgresNotificationStore(db)
```

The service code only depends on `NotificationStore` (the Protocol). The switch from Postgres to DynamoDB requires changing only the injection point.

---

### Expand and Contract: Column Split (Python migration example)

```python
# migrations/0042_expand_add_name_columns.py
# Phase 1: EXPAND — add new columns, keep old

def up():
    execute("ALTER TABLE users ADD COLUMN first_name VARCHAR(100)")
    execute("ALTER TABLE users ADD COLUMN last_name VARCHAR(100)")
    # DO NOT drop 'name' column yet

def down():
    execute("ALTER TABLE users DROP COLUMN first_name")
    execute("ALTER TABLE users DROP COLUMN last_name")

# -------------------------------------------------------
# Application code during dual-write period:
def update_user_name(user_id: str, full_name: str) -> None:
    first, _, last = full_name.partition(' ')
    db.execute("""
        UPDATE users
        SET name = %s, first_name = %s, last_name = %s
        WHERE id = %s
    """, [full_name, first, last, user_id])

# -------------------------------------------------------
# migrations/0043_backfill_name_columns.py
# Phase 2: BACKFILL — populate new columns from old

def up():
    # Run in batches to avoid locking
    batch_size = 10_000
    last_id = 0
    while True:
        rows = fetchall("""
            SELECT id, name FROM users
            WHERE id > %s AND first_name IS NULL
            ORDER BY id LIMIT %s
        """, [last_id, batch_size])
        if not rows:
            break
        for row in rows:
            first, _, last = row['name'].partition(' ')
            execute("UPDATE users SET first_name=%s, last_name=%s WHERE id=%s",
                    [first, last, row['id']])
        last_id = rows[-1]['id']
        time.sleep(0.01)  # Rate-limit to avoid replica lag

# -------------------------------------------------------
# migrations/0044_contract_drop_name_column.py
# Phase 4: CONTRACT — drop old column (only after Phase 3 verified)

def up():
    execute("ALTER TABLE users DROP COLUMN name")

def down():
    execute("ALTER TABLE users ADD COLUMN name VARCHAR(255)")
    execute("UPDATE users SET name = first_name || ' ' || last_name")
```

---

### Shadow Mode: Pricing Calculator Validation

```python
# pricing_service.py
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class PricingService:
    def __init__(self, old_calc, new_calc, feature_flags):
        self.old = old_calc
        self.new = new_calc
        self.flags = feature_flags

    def calculate(self, order) -> float:
        old_price = self.old.calculate(order)

        if self.flags.is_enabled("new_pricing_shadow"):
            try:
                new_price = self.new.calculate(order)
                if abs(old_price - new_price) > 0.01:
                    logger.warning(
                        "pricing_discrepancy",
                        extra={
                            "order_id": order.id,
                            "old_price": old_price,
                            "new_price": new_price,
                            "delta": new_price - old_price,
                        }
                    )
            except Exception as e:
                logger.error("new_pricing_error", extra={"order_id": order.id, "error": str(e)})

        # Always return old result during shadow period
        return old_price
```

Monitor the discrepancy log. Zero discrepancies over 48 hours of shadow traffic → safe to flip the flag to route real traffic. Any discrepancy → investigate before proceeding.

---

## Part 42: Extended War Story — The Netscape Rewrite

In 2000, Joel Spolsky wrote "Things You Should Never Do, Part I." The argument: Netscape's decision in 1999 to rewrite their browser from scratch was the single worst strategic mistake in tech company history. They spent three years rewriting. During those three years, they released nothing. IE captured the market. Netscape never recovered.

**What went wrong:**
1. The codebase was perceived as "ugly" and hard to work with. But ugliness is not a reason to rewrite. The ugly code contained years of bug fixes for obscure edge cases that only appear with millions of users.
2. The new code, written cleanly from scratch, reproduced all the obvious cases but missed the obscure ones. Users encountered bugs that had been fixed years earlier — reintroduced by the clean rewrite.
3. The rewrite took three times longer than planned. Every month of delay was another month for competitors to ship.
4. The team lost context. The engineers who understood *why* specific code was written a specific way left or moved on. The new team didn't know what they didn't know.

**The lesson for today:** Every "legacy" codebase that serves millions of users contains embedded knowledge — not in documentation, but in the code itself. The `if user.country == "JP" and order.amount < 1000` conditional that seems arbitrary was probably added in 2017 because Japanese payment processors reject orders under ¥100 for cards without 3D Secure. The rewrite that deletes it will work fine in every test and fail in Japan.

**The refactoring alternative:** Instead of a rewrite, apply the patterns in this chapter. The ugly code becomes less ugly, incrementally. The embedded knowledge is preserved because the behavior is tested before it is changed. The system continues to serve users throughout.

---

## Part 43: Patterns for Very Large Codebases (Google-Scale)

At companies like Google, Facebook, and Microsoft, "large codebase" means billions of lines of code, thousands of engineers, and changes that need to be applied across the entire codebase atomically.

**The challenges:**
- A single API change may require updating thousands of call sites
- Manual updates at this scale would take months; tests would break immediately
- Code review for 1,000 files is not practical

**Google's approach — Large-Scale Change (LSC) tooling:**

1. **Codefmt / gofmt / clang-format:** Automated formatters ensure consistent style; formatting PRs are machine-generated and machine-reviewed (no human review required)

2. **Rosie (internal):** Large-scale automated change system. Write a Clang-Tidy rule or a custom Python script that transforms the pattern; Rosie applies it across the entire codebase, splits the result into per-team PRs, assigns owners, monitors CI, and retries failures

3. **Semantic patching:** Tools like Coccinelle (C/C++) and codemod (JavaScript/Python) apply structural source code transformations — "rename this function and update its signature everywhere it's called"

**The principle for teams without LSC tooling:**
- Identify the scope before starting (count the call sites with grep; estimate the effort)
- Write a script for mechanical changes; don't do them by hand
- Use automated refactoring tools in your IDE (IntelliJ, VS Code) for renames and signature changes
- Split across multiple PRs if the scope exceeds 300 files; coordinate merging order with the team

---

## Part 44: Three-Level Refactoring (Code → Component → System)

Refactoring operates at three levels that require different skills:

**Level 1: Code-level refactoring**
- Scope: single file, single class, single function
- Patterns: Extract Method, Extract Class, Replace Conditional with Polymorphism, Introduce Parameter Object
- Risk: Low. Revert if needed.
- Who: Any engineer
- Time: Hours to days

**Level 2: Component-level refactoring**
- Scope: module, package, or small service
- Patterns: Branch by Abstraction, Characterization Tests, Shadow Mode
- Risk: Medium. May affect callers; interface changes require coordination
- Who: Senior engineer with stakeholder alignment
- Time: Days to weeks

**Level 3: System-level refactoring**
- Scope: multiple services, monolith extraction, data model restructuring
- Patterns: Strangler Fig, Expand and Contract, migration coordinator, DDD boundary mapping
- Risk: High. Org-level coordination, production traffic routing, multi-team data ownership
- Who: Staff engineer with executive sponsorship
- Time: Weeks to quarters

Most engineers spend most of their time at Level 1. Staff engineers are distinguished by their ability to operate at Level 3 — and their judgment about when Level 3 is actually needed versus when Level 1 improvements would achieve the same goal more simply.

---

## Part 45: The Refactoring Retrospective

After a large refactoring project completes, run a retrospective that captures these questions:

**What did we change?**
- What was the scope (files, modules, services affected)?
- What patterns did we use?
- How long did each phase take vs estimated?

**Did it work?**
- Change failure rate: before vs after (6-week windows)
- Deploy frequency: before vs after
- Time to add a specific feature in the affected area: before vs after (subjective engineer survey)
- P99 latency of affected endpoints: before vs after

**What went wrong?**
- Which phases took longer than expected? Why?
- Were there unexpected callers or dependencies?
- Were there characterization test failures that revealed missing coverage?
- Were there production incidents during the migration?

**What would we do differently?**
- Scope more tightly?
- Start shadow mode earlier?
- Involve a specific team sooner?
- Write more characterization tests upfront?

**Publish the retrospective.** Not to a team wiki that no one reads — to the engineering blog or all-hands. Large refactors are high-visibility projects. Sharing what worked and what didn't builds organizational knowledge and demonstrates Staff-level impact.

---

## Part 46: Operational Readiness Before Service Extraction

One of the most common mistakes in service extraction is treating it as a purely technical activity. Extracting a service from a monolith creates operational responsibilities that the team must be ready for. Extracting before you are operationally ready creates a worse situation than the monolith.

**Operational readiness checklist before extracting a service:**

**Observability:**
- [ ] The new service emits structured logs
- [ ] The new service emits latency and error rate metrics
- [ ] Distributed tracing is instrumented (trace IDs propagate from caller to service)
- [ ] An alert exists for error rate > threshold and P99 > threshold
- [ ] The on-call runbook for the service is written

**Deployment:**
- [ ] The service has a CI pipeline that runs tests on every PR
- [ ] The service has a CD pipeline that deploys to staging automatically on merge to main
- [ ] Production deployment is automated (not manual SSH)
- [ ] Rollback takes < 10 minutes (ideally automated)

**Reliability:**
- [ ] The service has a defined SLO (e.g., 99.9% availability, P99 < 100ms)
- [ ] Circuit breakers are configured on the callers
- [ ] Timeouts and retry policies are defined (and tested under failure conditions)
- [ ] The service has been load tested at 2× expected peak traffic

**Data:**
- [ ] The service owns its data (no shared database with the monolith post-extraction)
- [ ] Data backups are tested
- [ ] The data migration plan has been tested in staging

**Why this matters:** A service extracted without observability cannot be debugged in production. A service extracted without CD pipelines creates deployment bottlenecks. A service extracted without SLOs has no accountability. Many "microservices transformations" fail not because of the technical patterns but because the operational infrastructure was not built first.

**The order:** Build the operational infrastructure → extract the service → validate the operational instruments work → then start routing production traffic.

---

## Part 47: The Role of Refactoring in Career Growth

Understanding refactoring is directly linked to career progression in large engineering organizations.

**Why large companies value refactoring skill:**
- Large codebases are the norm; almost no one works greenfield beyond year 2
- The ability to improve existing systems is more valuable at scale than the ability to build new ones from scratch
- Refactoring requires the cross-functional skills that distinguish senior engineers: technical depth, communication, planning, risk management

**What interviewers look for:**
- Can you describe a specific pattern (Strangler Fig, Branch by Abstraction) by name and explain when you'd use each?
- Can you describe a real refactoring you led, including the risks you mitigated?
- Can you explain why the "let's rewrite it" approach is dangerous?
- Can you make the business case for a refactoring investment?

**The STAR story structure for a refactoring interview:**

"At [Company], the [System] had a change failure rate of [X%], causing [N] incidents per month. I was tasked with improving it. I started by writing characterization tests to document the existing behavior — we had [M] tests covering the critical paths after two weeks. I applied the Strangler Fig pattern: added a routing layer, built the new implementation behind it, and rolled out traffic 5% → 25% → 50% → 100% over 6 weeks with shadow mode validation at each step. The database schema was migrated using Expand and Contract across 3 deploy windows. The result: change failure rate dropped from [X%] to [Y%]; deploy frequency increased from [A] per week to [B]. The refactoring took [N] engineer-weeks, and the annual savings in incident response was [Z] hours."

That answer hits: technical patterns, test strategy, data migration, incremental rollout, business impact measurement. It signals L5.

---

## Part 48: Refactoring Legacy Authentication Systems

Authentication systems are among the hardest to refactor because:
1. They are on every request's critical path — any regression affects every user
2. Credentials (hashed passwords, tokens, sessions) persist across deployments
3. Security requirements are high — testing must be thorough
4. Multiple subsystems depend on them (sessions, authorization, audit logging)

**Migration approach for an auth system:**

**Phase 1: Introduce the abstraction**
```python
class AuthProvider(Protocol):
    def authenticate(self, credentials) -> User | None: ...
    def create_session(self, user: User) -> Session: ...
    def validate_token(self, token: str) -> User | None: ...
```

**Phase 2: Wrap the legacy system**
```python
class LegacyAuthProvider:
    # Wraps the existing auth code behind the new interface
    # No behavior changes yet
    def authenticate(self, credentials) -> User | None:
        return legacy_auth.authenticate(credentials)
    ...
```

**Phase 3: Build the new implementation**
```python
class ModernAuthProvider:
    # New implementation: bcrypt, short-lived JWTs, Redis session store
    def authenticate(self, credentials) -> User | None:
        ...
```

**Phase 4: Shadow mode for token validation**
Run both auth providers in parallel. Log discrepancies but use the legacy result. This catches any behavioral difference before traffic is routed.

**Phase 5: Gradual migration by user cohort**
New user registrations go through the new system. Existing users are migrated in batches (at next login, issue new credentials; old credentials remain valid during the overlap period).

**Phase 6: Sunset legacy credentials**
After 90 days, all users have migrated. Issue a warning to users still on legacy credentials. After 30-day warning period, deactivate legacy credential path.

**The never-do:** Force a hard cutover where all sessions are invalidated at once. This logs out all users simultaneously. Even if technically necessary, coordinate with the support team, send advance notice to users, and have rollback ready.

---

## Part 49: Refactoring Anti-Pattern Deep Dive — The Parallel Universe

The Parallel Universe anti-pattern deserves extra attention because it is the most common way large refactoring projects fail, and it is easy to slide into without noticing.

**How it starts:** A team decides the legacy system is too messy to refactor incrementally. They form a "v2 team" to build a clean implementation from scratch, while the "v1 team" maintains the legacy. The plan is to migrate traffic to v2 when it's ready.

**Month 1:** v2 team is excited; the new architecture is clean; they are shipping features quickly.

**Month 3:** v1 team adds features due to business demand. v2 team needs to implement the same features. The feature parity gap grows.

**Month 6:** v2 team discovers they need the legacy system's edge case handling for a specific payment processor. They read the v1 code to understand what it does. The "legacy code is messy" problem now applies to v2 as well — it has its own tech debt after 6 months of fast shipping.

**Month 9:** The migration date slips. The stakeholders who originally sponsored v2 have moved on to other priorities. The v2 team is understaffed.

**Month 12:** The company has two production systems, both partially broken, both maintained by teams with degraded morale. Either v1 is kept indefinitely ("migration" becomes a background project that never completes) or v2 is declared done and traffic is switched in a high-risk cutover.

**The cure:** Prevent the parallel universe from forming. If refactoring is needed:
- Keep one team; use Strangler Fig to make incremental progress
- If a new team is formed, it must ship to production incrementally from week one — not "when it's ready"
- A feature freeze on the old system is acceptable only if it is time-bounded (< 6 weeks) and enforced by leadership

---

## Part 50: Further Reading

**Books:**
- **"Working Effectively with Legacy Code"** — Michael Feathers. The definitive book on seams, characterization tests, and safely modifying code without tests. Required reading.
- **"Refactoring: Improving the Design of Existing Code"** — Martin Fowler. The original catalog of refactoring patterns (Extract Method, Replace Conditional with Polymorphism, etc.). Read the 2nd edition for updated examples.
- **"Building Microservices"** — Sam Newman. Comprehensive guide to service extraction, including the Strangler Fig and data ownership patterns.
- **"The Mikado Method"** — Ellnestam & Brolund. Short book specifically on the Mikado Method for navigating large refactoring dependencies.
- **"Domain-Driven Design"** — Eric Evans. The original DDD text. Dense, but the bounded context concepts are essential for service boundary decisions.

**Articles:**
- Martin Fowler's "StranglerFigApplication" — bliki.martinfowler.com — the original description
- Martin Fowler's "BranchByAbstraction" — bliki.martinfowler.com
- Joel Spolsky's "Things You Should Never Do, Part I" — joelonsoftware.com — the Netscape rewrite argument

**Practice:**
- Refactor a real legacy open-source project (look for ones marked "help wanted" + "refactoring")
- The "Gilded Rose" refactoring kata — a classic exercise in characterization tests and Branch by Abstraction
- The "Strangler Fig" kata — available on GitHub, simulates migrating a monolith endpoint by endpoint

---

## Part 51: Communicating Refactoring Progress to Leadership

Refactoring work is invisible to people who don't read code. Staff engineers must translate technical progress into terms that leadership cares about. Otherwise, refactoring projects lose sponsorship mid-execution.

**What leadership cares about:**
- Developer velocity (are we shipping faster?)
- Incident rate (are we more reliable?)
- Cost (are we using resources efficiently?)
- Risk (are we reducing technical risk?)

**How to frame refactoring in those terms:**

| Technical Metric | Leadership Translation |
|-----------------|----------------------|
| Change failure rate: 15% → 4% | Incidents from deploys cut by 73%; 3.5 hours/week of incident response recovered |
| Deploy frequency: 2/week → 5/week | Time from feature complete to customer: 3.5 days → 1.4 days |
| P99 latency: 800ms → 200ms | Checkout conversion rate estimated +0.5% (industry benchmark: 100ms = 1% conversion) |
| Test coverage: 35% → 78% | New engineer onboarding time reduced; regression rate reduced |

**The progress update format for leadership:**
- Current status: which phase of the migration plan are we in?
- Key metrics now vs baseline
- Any blockers or risks
- Next milestone and date

Send this monthly. Never wait for leadership to ask. Proactive updates build trust and prevent the project from being cancelled mid-migration.

---

## Part 52: Refactoring in the Context of Feature Development

Refactoring does not exist in isolation from feature development. Staff engineers must manage the tension between "improving the system" and "shipping new capabilities."

**The 20% rule:** Some teams allocate a fixed percentage of engineering capacity to technical improvement. 20% is common. The advantage: it sets expectations with product; refactoring is planned, not squeezed in. The disadvantage: it can decouple refactoring from the areas that actually need it most.

**Better approach: just-in-time refactoring.** Before implementing a feature in a particular area, refactor that area first. "We're adding discount code support to the pricing engine — let me first extract the pricing logic from the order processor, since we'll be changing it anyway." The refactoring reduces the cost of the feature; the feature provides the immediate justification for the refactoring.

**The risk of deferred refactoring:** "We'll clean this up later" is the statement that creates legacy systems. "Later" rarely comes without forcing functions. The forcing function is usually either a major incident caused by the messy code or a new feature that is so painful to add that the refactoring becomes unavoidable.

**Prioritization framework:**
1. Refactor areas where you are making changes anyway (highest ROI — the refactoring cost is amortized over the feature)
2. Refactor areas with high change failure rate (the technical debt tax is being paid now)
3. Refactor areas where team velocity is visibly degraded (engineers spending > 20% of their time on accidental complexity)
4. Refactor areas for future capabilities (lowest priority — avoid refactoring for hypothetical future needs)

---

## Part 53: Pattern Interactions — Combining Patterns

Real large-scale refactoring often requires combining multiple patterns. Here are the most common combinations:

**Strangler Fig + Expand and Contract:**
Extracting a service from a monolith almost always requires both. The Strangler Fig handles the application-level routing; Expand and Contract handles the database schema migration. They run in parallel: the application-level strangler routes traffic incrementally while the database migration progresses through its phases.

**Branch by Abstraction + Shadow Mode:**
When replacing an internal component, Branch by Abstraction creates the interface; Shadow Mode validates the new implementation before traffic is routed. They are complementary: Branch by Abstraction is the structure; Shadow Mode is the validation strategy.

**Mikado Method + Characterization Tests:**
The Mikado Method tells you the order of changes; Characterization Tests give you the safety net for each change. Use Mikado to plan; write Characterization Tests before executing each node in the tree.

**Feature Flags + Boy Scout Rule:**
Feature flags are the "cleanup ticket" mechanism for the Boy Scout Rule. Every flag has a creation date and a scheduled removal date. The Boy Scout Rule applies to flags as much as to code: if you touch a file that contains an old, inactive flag, remove it.

---

## Part 54: Additional One-Liners

11. "The Strangler Fig router must stay simple — business logic in the router creates a third system."
12. "Shadow mode is cheaper than a production incident — run it for at least 48 hours before routing real traffic."
13. "Never measure refactoring success in lines deleted. Measure in change failure rate, deploy frequency, and time-to-feature."
14. "The Mikado tree: each node is a small, independently deployable change. If it isn't deployable, it's too large."
15. "A feature freeze for refactoring is a red flag. If the refactoring requires a feature freeze, the approach is wrong."
16. "Characterization tests capture behavior, not intent. The intent is in the business logic; the behavior is in the output."
17. "Service extraction readiness check: can you deploy the service independently, monitor it independently, and roll it back in < 10 minutes?"
18. "The Netscape rule: never throw away a production codebase unless you fully understand everything it does."

---

## Part 55: Chapter Statistics

- **Parts covered:** 55 major sections
- **Patterns covered:** Strangler Fig, Branch by Abstraction, Expand and Contract, Characterization Tests, Mikado Method, Shadow Mode, Feature Flags, Seam-Based Decomposition, DDD Bounded Contexts, Hexagonal Architecture
- **Code examples:** Strangler Fig HTTP router, Branch by Abstraction (storage backend), Expand and Contract (4-phase column split), Shadow Mode (pricing calculator)
- **War stories:** Basecamp 20-year monolith, Amazon SOA mandate (2002), Uber microservices (2014-2016), Google LSC tooling, Netscape rewrite (2000), Shopify modular monolith
- **Exercises:** 10 practice exercises
- **Homework:** 3 assignments
- **Pre-interview drill:** 12 questions

**This chapter in one sentence:** Refactor incrementally, preserve behavior with tests, route traffic gradually with feature flags, migrate databases with Expand and Contract, and never throw away a production codebase's accumulated knowledge by rewriting from scratch.

---

> "The best refactoring is the one that is never noticed by users — because it happened safely, incrementally, and correctly, one small step at a time."

---

## Part 56: Brainstorming Q&A Extended

**Q: You're asked to extract the Search service from a monolith. The search indexes are stored in Elasticsearch shared with 3 other services. How do you approach the data ownership problem?**

The shared Elasticsearch cluster is the critical constraint. The goal of service extraction is for the Search service to own its data — but three other services currently use the same cluster. You have three options:

**Option A: Give Search its own Elasticsearch cluster.** The new Search service gets a dedicated cluster. Data is replicated (or re-indexed) from the shared cluster to the dedicated one. This is the cleanest long-term solution. The cost: running costs for an additional cluster; complexity of keeping two clusters synchronized during the migration.

**Option B: Define data ownership at the index level.** The Search service becomes the authoritative owner of search-related indexes. The other three services migrate to calling the Search service API for search operations rather than querying Elasticsearch directly. Operationally, it's one cluster; logically, Search owns the indexes. This is a pragmatic middle ground that achieves organizational independence (one team owns the indexes) without the operational overhead of a second cluster.

**Option C: Delay extraction until data is separated.** The Search service is not ready to be extracted until data ownership is resolved. Delay the extraction, first resolve data ownership for the other three services, then extract.

For a Google L5 interview, Option B is the most complete answer: it achieves the goal (Search team owns their data), it's incrementally achievable, and it doesn't require an expensive cluster migration. State the tradeoff explicitly: "This is a logical separation rather than physical; if we need independent scaling of the search index, we'd revisit Option A."

---

**Q: A characterization test for a legacy tax calculation function produces a different result on different days. What does that tell you?**

The function has an implicit time dependency — it reads the current date or time without it being passed as a parameter. This is a classic violation of referential transparency: the function produces different outputs for identical inputs depending on when it is called.

**What to do:**
1. Find the time dependency in the code: `datetime.now()`, `Date.today()`, a database lookup for "current tax rates" (which change over time), etc.
2. Make the dependency explicit: add a `calculation_date` parameter to the function signature
3. Update all callers to pass the date explicitly
4. Now the characterization test is deterministic: pass a fixed date; record the output; it never changes

This is also a seam introduction (Part 27): the time is now injected rather than read from global state, enabling testing and safe refactoring.

**Why this matters in production:** If the function silently changes behavior on January 1 (new tax year), that is not a safe refactoring — it is a production behavior change. Making time dependencies explicit is a prerequisite for safe migration.

---

## Part 57: Decision Framework — When to Refactor vs When to Rewrite vs When to Leave It

| Scenario | Decision | Reasoning |
|----------|----------|-----------|
| Code is messy but change failure rate is low and velocity is fine | Leave it | Messy code that works and doesn't slow you down is not a problem |
| Change failure rate > 10%, team spends > 20% on incidents | Refactor | High ROI; the tax is being paid now |
| Single component is a bottleneck for one team | Refactor that component | Targeted refactoring; don't over-scope |
| Technology is end-of-life (Python 2, Flash, IE-specific code) | Targeted rewrite | No migration path; bounded scope |
| Multiple teams blocked by one God service | Service extraction (Strangler Fig) | Organizational independence is the goal |
| Team genuinely cannot understand the code after reading it for weeks | Characterization tests → refactor | You need to understand it to change it safely; tests are how you build understanding |
| Product wants all-new features in the system for the next 12 months | Refactor incrementally alongside features | Just-in-time refactoring; don't front-load |
| The system has been serving production for 10+ years with minimal issues | Leave it or Boy Scout Rule only | Years of accumulated edge case handling; don't disturb it without strong reason |

The rule of thumb: refactor when the cost of the current state exceeds the cost of the change. Measure both. Don't refactor based on aesthetics.

---

## Part 58: Quick Practice Scenarios

**Scenario 1:** You inherit a 3,000-line Python file called `utils.py` that contains functions used by 40 different modules. Where do you start?
- Map the dependencies: which functions are used by which modules?
- Identify clusters: do groups of functions always appear together?
- Extract the largest cluster first (highest impact, most natural boundary)
- Use Branch by Abstraction: new module with same function names; update imports incrementally

**Scenario 2:** A colleague wants to rename the `orders` table to `purchases` across the codebase and database at once. What do you say?
- Don't. Use Expand and Contract.
- Add `purchases` as a view or alias first
- Migrate code to use `purchases` incrementally
- Once all code uses `purchases`, drop the `orders` alias
- This avoids a single high-risk change; each step is independently deployable

**Scenario 3:** A refactoring PR is open for 3 weeks with no progress. The engineer says they're "still figuring out the full scope." What's the problem and what's the solution?
- Problem: the scope is too large; they are trying to understand everything before changing anything
- Solution: Mikado Method. Pick the smallest, most concrete first step. Make that change and ship it. The next step becomes clearer after the first one.
- Remind the engineer: "You don't need to understand the whole system to improve one part of it."

**Scenario 4:** After a 4-month refactoring effort, the change failure rate is unchanged. The code is cleaner, but production stability is the same. What happened?
- Likely: the refactoring improved areas that were not the source of incidents
- The incidents were probably in a different part of the system
- Lesson: start by instrumenting the change failure rate per module; refactor the highest-failure-rate modules first
- Cleaner code is not an end in itself; it is a means to a measurable outcome

---

## Part 59: Refactoring Vocabulary Quick Reference

| Term | One-Line Definition |
|------|---------------------|
| Strangler Fig | Replace system incrementally by routing from old to new; retire old last |
| Branch by Abstraction | Add interface; implement both old and new; switch via injection; delete old |
| Expand and Contract | DB schema change in 4 phases: add → backfill → switch → drop |
| Characterization Test | Records actual (not intended) behavior; safety net during refactoring |
| Mikado Method | Attempt goal → fail → revert → address prerequisites → retry; always revert |
| Seam | A code location where behavior can change without editing that location |
| Shadow Mode | Run new implementation alongside old; use old result; log discrepancies |
| Feature Flag | Runtime switch enabling incremental traffic routing; must be removed post-migration |
| Boy Scout Rule | Leave code better than you found it; continuous incremental improvement |
| God Class | Class with too many responsibilities; violation of Single Responsibility Principle |
| Distributed Monolith | Extracted services that share databases or call each other synchronously; worst outcome |
| Dark Launch | Feature deployed to production but not user-visible; validates at scale |
| Technical Debt | Known imperfection shipped deliberately; accrues interest in future maintenance cost |
| Bounded Context | DDD: named boundary where a domain model has consistent, unambiguous meaning |
| Anti-Corruption Layer | Translation layer that prevents a new service from inheriting a legacy system's model |

---

## Part 60: The Staff Engineer's Mindset for Refactoring

The technical patterns are learnable in weeks. The mindset shift takes longer.

**From:** "This code is bad and needs to be fixed."
**To:** "This system is serving X million users. Any change I make needs to leave it at least as reliable as I found it. The first thing I do is understand what it does, not change it."

**From:** "We should rewrite this."
**To:** "What specifically is this costing us? Can we achieve the same goal with a targeted, incremental improvement? What is the minimum viable change?"

**From:** "The refactoring is done when the code looks better."
**To:** "The refactoring is done when the change failure rate drops, the feature velocity improves, and the old code paths are deleted."

**From:** "I'll clean this up later."
**To:** "I'll clean this up now, before it costs more. If I can't do it now, I'll create a ticket with a concrete cost estimate and schedule it."

**From:** "The team should stop feature work and fix the tech debt."
**To:** "I'll make the business case with numbers, propose a 20% allocation, and prove the ROI in 90 days."

These are not just philosophical positions. Each one maps directly to a concrete engineering behavior — and the sum of those behaviors over a year is the difference between a system that gets better with time and a system that accumulates entropy until it must be abandoned.

Refactoring large systems is, ultimately, the discipline of taking ownership. Not of the glory of shipping new things, but of the long-term health of the systems that the company depends on. That ownership — expressed through patterns, measured through metrics, communicated to stakeholders — is what Staff engineering looks like in practice.

---

## Part 61: Thirty-Day Refactoring Study Schedule

| Days | Focus | Activity |
|------|-------|----------|
| 1–5 | Foundation | Read Feathers "Working Effectively with Legacy Code" chapters 1–10; implement the Gilded Rose kata with characterization tests |
| 6–10 | Patterns | Implement Strangler Fig and Branch by Abstraction on a toy codebase; practice the Mikado Method on a real module |
| 11–15 | Database | Design 3 Expand and Contract migrations for real schema changes; estimate backfill times at 10M rows |
| 16–20 | War stories | Read: Netscape rewrite (Spolsky), Amazon SOA mandate (Bezos API email), Shopify modular monolith blog post; write the refactoring plan each company should have used |
| 21–25 | Business case | For a past project, calculate the change failure rate cost; write the business case for a targeted refactoring |
| 26–30 | Interview prep | Practice the 12-question pre-drill; time yourself telling a refactoring STAR story in under 3 minutes |

---

## Part 62: Ten Things Staff Engineers Know About Refactoring

1. **Incremental always beats big bang.** Every large refactoring project that succeeded used incremental migration. Every big rewrite that succeeded was actually a small, bounded replacement.

2. **Understanding comes from testing, not reading.** You cannot fully understand a 50,000-line legacy system by reading it. Characterization tests make behavior explicit and enable safe exploration.

3. **The Strangler router is sacred.** The routing layer must stay simple. The moment it starts accumulating business logic, you have three systems instead of two.

4. **Data migration is always harder than code migration.** Budget 2× your estimate for data migration. Test the backfill script at production scale in staging.

5. **The distributed monolith is a worse outcome than the monolith.** If you extract a service but it still shares a database, you have added operational complexity without achieving independence. Don't extract until the data ownership question is answered.

6. **Shadow mode before traffic.** Never route real user traffic to an untested implementation. Shadow mode catches discrepancies cheaply.

7. **Feature flags have a lifespan.** A flag that was created 6 months ago and never reached 100% rollout is a sign of an abandoned migration. Either complete it or revert it.

8. **The business case requires numbers.** "The code is messy" has never gotten a refactoring prioritized. Change failure rate × incidents/month × cost/incident = the annual tax of current debt.

9. **Org coordination is as important as technical patterns.** The best Strangler Fig implementation fails if the dependent team doesn't know their API contract is changing.

10. **Completion means deletion.** A refactoring is not complete until the old code path, the old database columns, and the feature flags are deleted. Incomplete refactorings are permanently more expensive than never starting.

---

## Part 63: Final Summary — The Core Loop

Every large-scale refactoring, regardless of size or complexity, runs this loop:

```
1. UNDERSTAND: Characterization tests → document behavior before touching code
2. PLAN: Mikado tree → find prerequisites → define rollback criteria → communicate
3. EXECUTE: One deployable step at a time → shadow mode → incremental traffic routing
4. VALIDATE: Metrics before vs after → discrepancy logging → go/no-go per milestone
5. COMPLETE: Delete old code → remove flags → publish retrospective
```

This loop applies whether you are:
- Renaming a function (1 hour)
- Extracting a class from a God object (1 day)
- Replacing an internal component (1 week)
- Extracting a microservice from a monolith (1 quarter)

The patterns scale. The discipline stays constant: never accumulate half-done changes, never leave the system in an undeployable state, never route production traffic to an unvalidated implementation.

The Staff engineer's value in this work is not in executing the loop faster than others. It is in:
- Recognizing when the loop is needed
- Convincing stakeholders to invest in it
- Coordinating across teams through it
- Measuring and communicating its outcomes
- Ensuring it actually completes — not abandoned halfway

Large systems live or die by the discipline their engineers bring to changing them. This chapter is a guide to that discipline.

---

> "The courage to refactor is the courage to improve something you didn't break, knowing that improvement requires risk, and that doing nothing is also a choice — one with its own compounding cost." 

---

## Part 64: Glossary of Refactoring Smells and Fixes

| Smell | Symptom | Pattern to Apply |
|-------|---------|-----------------|
| God Class | 500+ line class, 20+ methods, unrelated responsibilities | Extract Class → Branch by Abstraction |
| Long Method | 50+ line function, nested conditionals | Extract Method multiple times |
| Feature Envy | `a.b.c.method()` chain accessing another object's internals | Move Method to owning class |
| Shotgun Surgery | One behavior change requires editing 10+ files | Consolidate; Extract Service |
| Divergent Change | One class changes for 5 different reasons | Split by reason (SRP) |
| Data Clumps | Same 3-4 fields always passed together | Introduce Parameter Object |
| Primitive Obsession | `user_type: str` instead of `UserType` enum | Introduce Value Object |
| Parallel Inheritance | Adding subclass in A requires matching subclass in B | Collapse hierarchies; use composition |
| Lazy Class | Class that does almost nothing | Inline Class |
| Speculative Generality | Abstractions for hypothetical future use | Delete unused generality |
| Temporary Field | Field set only under certain conditions | Extract Class or replace with special case |
| Message Chains | `order.customer.address.city` | Hide Delegate; add `order.customer_city()` |

---

## Part 65: Why Refactoring Is a First-Class Engineering Discipline

Shipping new features gets attention. Fixing bugs gets respect. Refactoring rarely gets either. And yet, in any codebase that serves significant traffic, the ability to improve the existing system is what makes all future shipping possible.

The engineers who master this discipline become the ones teams cannot afford to lose. They are the ones who unstick the stuck systems, who know how to move the immovable object safely, who understand that technical leadership is not about the new code you write but about the health you maintain in the code everyone depends on.

This chapter is a reference. Come back to it when you inherit a mess. Come back to it when a colleague proposes a full rewrite. Come back to it when you need to make the business case. The patterns are here. The vocabulary is here. The mindset is the work.

---

## Part 66: Chapter Statistics

| Dimension | Detail |
|-----------|--------|
| Parts | 66 major sections |
| Patterns covered | Strangler Fig, Branch by Abstraction, Expand and Contract, Characterization Tests, Mikado Method, Shadow Mode, Feature Flags, Seam-Based Decomposition, DDD Bounded Contexts, Hexagonal Architecture, ACL, Boy Scout Rule |
| Code examples | 5: HTTP Strangler router, Branch by Abstraction (storage), 4-phase DB migration, Shadow Mode (pricing), Auth system migration |
| War stories | 5: Basecamp, Amazon SOA mandate, Uber microservices, Google LSC tooling, Netscape rewrite |
| Exercises | 10 |
| Homework | 3 assignments |
| Pre-interview drill | 12 questions |
| One-liners | 18 |
| Code smells table | 12 smells with fixes |

**Core thesis, one sentence:** Refactor incrementally using patterns that keep the system deployable at every step, measure improvement in observable metrics, and complete the work — old code deleted, flags removed — before moving on.

---

## Quick Recall: The Three Questions Before Any Refactoring

Before touching a large legacy system, answer these three questions:

**1. What does it actually do?**
Not what the documentation says, not what the original engineers intended — what does it actually do under production load, with production data, including the edge cases and the bugs that callers depend on? Write characterization tests until you can answer this confidently.

**2. What specifically is broken?**
Not "it's hard to work with" — what measurable problem does the current state cause? Change failure rate, incident frequency, developer time spent, inability to add a specific feature? If you can't answer in numbers, you don't have a refactoring case yet.

**3. What is the minimum change that achieves the goal?**
Not the cleanest possible architecture — the minimum change that addresses the specific problem identified in question 2. Scope the refactoring to that minimum. Everything else is future work.

A Staff engineer who can answer all three questions before writing a line of code is a Staff engineer who can actually ship a successful refactoring.

---

## Key Quotes for Refactoring Interviews

> "Any fool can write code that a computer can understand. Good programmers write code that humans can understand." — Martin Fowler

> "If it hurts, do it more frequently." — Jez Humble (on the value of small, frequent deploys rather than rare, painful ones — applies equally to refactoring)

> "Make the change easy, then make the easy change." — Kent Beck (prepare the codebase for the feature, then add the feature cleanly)

> "The second-system effect: architects design their second system with all the embellishments they held back from the first. It is almost always too large." — Fred Brooks

> "Legacy code is code without tests." — Michael Feathers (your legacy code is maintainable once it has tests)

These quotes are useful as anchors in technical conversations and interviews — they signal familiarity with the literature and embed the right intuitions.

---

## Pattern Applicability by System Age

| System Age | Primary Challenges | Recommended First Pattern |
|------------|-------------------|--------------------------|
| < 2 years | Few callers; tests may exist; original engineers available | Branch by Abstraction; Boy Scout Rule |
| 2–5 years | Growing caller count; partial test coverage; some knowledge loss | Characterization Tests; then Strangler Fig |
| 5–10 years | Many callers; sparse tests; knowledge concentrated in few engineers | Characterization Tests; Mikado Method; Strangler Fig |
| > 10 years | All of the above plus: deeply embedded business logic; edge cases with no documentation | Characterization Tests first (weeks); only then plan refactoring |

The older the system, the more time you spend understanding before changing. A 10-year-old system that serves 10 million users has earned deep respect before being touched.

---

## The One Thing to Remember

If you remember nothing else from this chapter, remember this:

**A large refactoring is not a project. It is a discipline.**

Projects have a start and an end. Disciplines are practiced continuously. The engineers who improve large systems are not the ones who periodically declare "this quarter we are doing refactoring." They are the ones who, on every pull request, on every design review, on every incident, ask: "How do we leave this better than we found it? And how do we do it safely?"

That discipline, applied consistently over months and years, is what makes large systems maintainable. Everything else in this chapter is the toolbox. The discipline is the work.

---

## Three Truths That Don't Change

1. Production code that works is more valuable than a perfect design that doesn't exist yet.

2. The test suite is the most important artifact of any refactoring effort — more important than the new code.

3. A refactoring that ships incrementally in 10 weeks is worth more than a rewrite that is "almost done" after 6 months.

---

> "Refactoring is not about making code look better. It is about making the next change cheaper, the next incident less likely, and the next engineer's first week less painful." — The goal in one sentence.

> "The bravest thing you can do in software is say 'this code works, and I understand it well enough to improve it safely.'"

---

## Companion Resources

- **"Working Effectively with Legacy Code"** — Michael Feathers (seams, characterization tests, breaking dependencies)
- **"Refactoring: Improving the Design of Existing Code"** — Martin Fowler (full pattern catalog)
- **"Building Microservices"** — Sam Newman (Strangler Fig, service extraction, data ownership)
- **"The Mikado Method"** — Ellnestam & Brolund (prerequisite-first dependency navigation)
- **"Domain-Driven Design"** — Eric Evans (bounded contexts, ubiquitous language, anti-corruption layers)
- **"Accelerate"** — Forsgren, Humble, Kim (DORA metrics: change failure rate, deploy frequency — the measuring sticks)

---

---

> Make the change easy, then make the easy change. — Kent Beck

---

*Pairs with Chapter 111 (Migrations and Safe Changes) for database migration patterns, Chapter 110 (Code Review as a Discipline) for reviewing refactors, and Chapter 117 (Capacity Planning) for understanding system constraints before extracting services.*

`Chapter 116 | Section 7: Engineering Excellence | Refactoring Large Systems`
