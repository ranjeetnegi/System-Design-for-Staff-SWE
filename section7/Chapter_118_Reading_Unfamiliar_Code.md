# Chapter 118: Reading Unfamiliar Code — Day 1 at a New Team

> *"You join a new team. The codebase has 500,000 lines of code written by 50 engineers over 5 years. Your first task lands on Monday. Nobody teaches you how to build a mental model of a system you didn't write. This chapter does."*

---

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                  AT-A-GLANCE: READING UNFAMILIAR CODE                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│  FIRST PRIORITY    Entry points — trace ONE request end-to-end               │
│  SECOND PRIORITY   Data model — schema reveals purpose before code does      │
│  THIRD PRIORITY    Tests — they are the executable spec                       │
│  FOURTH PRIORITY   Git history — commit messages explain the "why"           │
│                                                                                │
│  L3 APPROACH   Read code top-to-bottom. Weeks to be productive.              │
│  L5 APPROACH   Find entry points → trace one flow → draw the box diagram.   │
│                Productive in 1-2 weeks.                                       │
│  L6 APPROACH   Data model + entry points + tests → mental model in 3 days.  │
│                Reviewing PRs by end of week 1.                                │
│                                                                                │
│  TIME TARGETS  Day 1: draw the box diagram (input → process → output)       │
│                Week 1: make a small real change (fix a bug, add a test)      │
│                Week 4: own one component, review others' PRs                 │
│                                                                                │
│  ANTI-PATTERN  "Reading for 3 months without shipping" — the classic trap    │
│  WARNING       Code that has no tests = undocumented behavior = danger zone  │
│  SIGNAL        git blame on confusing code often reveals "why" in 30 seconds │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: The Mental Model Problem

Every engineer changes teams. You might be changing teams within your company, joining a new org via a transfer, or starting at a new company entirely. The speed at which you become productive on an unfamiliar codebase is a direct, visible signal of seniority.

**The fundamental mistake: linear reading.**

New engineers (and many experienced ones) approach an unfamiliar codebase by starting at the top of the main file and reading down. This is understandable — it's how we read everything else. But code is not a book. It has no beginning or end. It has no linear narrative. Reading code linearly produces one outcome: weeks of confusion followed by cargo-culting patterns you don't understand.

The real goal is not to memorize code. The goal is to build a **mental model** of the system.

A mental model has four components:

```
┌─────────────────────────────────────────────────────────────────┐
│                 MENTAL MODEL COMPONENTS                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. DATA FLOW     Where does data enter the system?             │
│                   How does it transform?                        │
│                   Where does it end up?                         │
│                                                                  │
│  2. STATE         What does the system remember?                │
│     OWNERSHIP     Who is the source of truth for each piece?    │
│                   What can change what?                         │
│                                                                  │
│  3. INVARIANTS    What must always be true?                     │
│                   What is the system protecting?                │
│                   What breaks if an invariant is violated?      │
│                                                                  │
│  4. FAILURE       What happens when each component fails?       │
│     MODES         Is failure silent or loud?                    │
│                   Does the system degrade gracefully?           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Once you have these four things, you can read any piece of code and understand where it fits. You can review a PR without getting lost in the details. You can debug an incident without following every code path.

**"Read to understand, not to remember."**

You will read the same piece of code many times over the next 3 months. The first time, your goal is orientation — not retention. Build navigation instinct: know that "authentication lives in the auth/ package" and "billing flows through the payment_processor module" — you can find the details when you need them.

---

## Part 2: The Entry Points Strategy (First 2 Hours)

The single most productive thing you can do in your first two hours is find and trace **one request end-to-end**.

**Step 1: Find the entry points.**

Every system has entry points — the places where external input arrives. Common entry points:

```
HTTP server:       main.go → router.go → handler_users.go
gRPC server:       main.go → grpc_server.go → UserServiceServer.Handle()
Queue consumer:    main.go → consumer.go → ProcessMessage(msg Kafka.Message)
Cron job:          main.go → scheduler.go → RunDailyReportJob()
Event handler:     main.go → event_bus.go → OnUserCreated(event UserCreated)
Batch processor:   main.go → batch_runner.go → ProcessBatch(input []Record)
```

Grep for `main.go`, `server.go`, `handler`, `router`, `consumer`, `processor`. Most systems have only 2-4 entry points.

**Step 2: Trace one request.**

Pick the most common request type (usually the API endpoint that handles the core business action — "create order", "charge payment", "send message"). Trace it from the entry point to the database write and back.

```bash
# Find the handler
grep -r "POST /orders" --include="*.go" .
# → Found: handlers/order_handler.go:CreateOrder()

# Read the handler
cat handlers/order_handler.go
# → Calls: order_service.CreateOrder(req)

# Find the service
grep -r "func.*CreateOrder" --include="*.go" .
# → Found: services/order_service.go:CreateOrder()

# Read the service
cat services/order_service.go
# → Calls: db.InsertOrder(), kafka.PublishOrderCreated()
```

You now have the critical path. Draw it on paper or in a notes doc:

```
POST /orders
    → OrderHandler.CreateOrder()
        → ValidateRequest()
        → OrderService.CreateOrder()
            → db.InsertOrder() [MySQL: orders table]
            → kafka.Publish("order_created", OrderCreatedEvent)
    → return 201 Created
```

**Goal after 2 hours:** You can draw a rough box diagram of the system. You know what the system does at a 10,000-foot level and have traced one path through the forest.

**What to look for while tracing:**

```
Middleware layers:     authentication, authorization, rate limiting, logging
Validation:           where does input validation happen?
Error handling:       does the system fail open or closed?
External calls:       which services, databases, queues does this call?
Transactions:         is the operation atomic? What happens on partial failure?
```

---

## Part 3: Data First, Code Second

After finding the entry points and tracing one flow, your next priority is the **data model**. Data structures reveal the system's purpose more clearly than code does.

**Why data comes before code:**

Code is implementation — how the system works right now. Data is the record of what the system was built to store. The data model reflects the product design decisions, the business rules, and the constraints that were negotiated over years. Understanding the data model gives you 70% of what you need to understand the system.

**Step 1: Find the schema.**

```bash
# Database migrations (Rails/Flyway/Liquibase/golang-migrate)
ls db/migrations/
ls schema/
find . -name "*.sql" | head -20

# ORMs with auto-generated schemas
find . -name "models.py" | head -5  # Django
find . -name "*.proto"              # Protobuf
find . -name "schema.graphql"       # GraphQL
find . -name "*.avsc"               # Avro
```

**Step 2: Reconstruct the ERD.**

Read each table definition and note:
- What is the primary key design? (UUID vs auto-increment vs composite)
- What foreign keys exist? (What references what?)
- What indexes exist? (What are the common query patterns?)
- What columns are nullable? (What business rules are they encoding?)
- What columns have constraints or defaults? (What invariants is the DB enforcing?)

Example of what tables tell you:

```sql
CREATE TABLE orders (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id),
    status      VARCHAR(20) NOT NULL DEFAULT 'pending',
    total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fulfilled_at TIMESTAMPTZ  -- nullable: not yet fulfilled
);

CREATE TABLE order_items (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id   UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    price_cents INTEGER NOT NULL
);
```

From this schema alone, without reading a single line of application code, you know:
- Orders have multiple items (one-to-many)
- Orders have a lifecycle (`status` field with `pending` default)
- Prices are stored in cents (no floating point precision bug possible)
- `fulfilled_at` is nullable = orders can exist unfulfilled
- Items are deleted when order is deleted (CASCADE)
- The system protects against negative prices and zero quantities at the DB level

**Step 3: Find the event schemas.**

If the system publishes events (Kafka, Pub/Sub, SQS), find the event schemas. Events are the API between services. They reveal the integration points more clearly than any architecture diagram.

```bash
# Avro schemas
find . -name "*.avsc"
# Protobuf events
find . -name "*Event*.proto"
# JSON schemas
find . -name "*schema*.json" | grep -i event
# Golang event types
grep -r "type.*Event struct" --include="*.go" .
```

**Step 4: Find the key structs/classes.**

In Go, these are structs. In Python, dataclasses or Pydantic models. In Java, POJOs. These are the domain objects the system reasons about — they reveal the vocabulary of the domain.

```bash
# Go
grep -r "type.*struct" --include="*.go" . | grep -v "_test.go"
# Python
grep -r "class.*:" --include="*.py" . | grep -E "(Model|Schema|Request|Response)"
# Java
find . -name "*.java" | xargs grep -l "@Entity\|@Value\|@Data"
```

---

## Part 4: Find the Tests (They Are the Spec)

Tests are the most underused resource when reading a new codebase. They are:

1. **Living documentation** — test names describe behavior in plain English
2. **Executable spec** — they prove what the system is supposed to do
3. **Historical record** — test cases represent bugs that were caught and codified
4. **Risk map** — areas with no tests are areas that can break silently

**Types of tests and what each tells you:**

```
Unit tests:           what behavior does this function guarantee?
Integration tests:    how does this module behave with real dependencies?
End-to-end tests:     what does the full system do from a user's perspective?
Contract tests:       what does this service expect from its upstream providers?
Property tests:       what invariants must hold across all possible inputs?
```

**How to read tests as documentation:**

```python
# The test name IS the spec
def test_payment_fails_if_insufficient_balance():
    # This tells you: payment should fail, not partially succeed, when funds are insufficient

def test_order_is_idempotent_for_same_idempotency_key():
    # This tells you: the system has idempotency protection (probably because
    # duplicate requests were once a real problem)

def test_user_email_is_normalized_to_lowercase():
    # This tells you: email normalization happens; there was probably a bug
    # where the same user could sign up with "User@Example.com" and "user@example.com"
```

**Running the tests is the first productive action you can take:**

```bash
# Whatever the test runner is, run it
go test ./...
pytest
./gradlew test
npm test

# If tests pass: you have a working baseline
# If tests fail: your FIRST task is to understand why
# If tests don't exist: take note — this area is undocumented and high-risk
```

**Coverage reports as a risk map:**

Low test coverage indicates either:
- Legacy code that predates the test culture
- Areas that are hard to test (often because of poor separation of concerns)
- Areas that rarely change (might be safe, might be forgotten)

High test coverage does not mean correctness — tests can be wrong too. But low coverage + high churn = highest-risk area in the codebase.

```bash
# Go coverage report
go test -coverprofile=coverage.out ./...
go tool cover -html=coverage.out -o coverage.html

# Python
pytest --cov=myapp --cov-report=html

# Sort by lowest coverage to find the riskiest areas
go tool cover -func=coverage.out | sort -k3 -n | head -20
```

---

## Part 5: Read the Git History (Code Has a Story)

Git history is one of the most underutilized tools for reading unfamiliar code. Every piece of confusing code was written by someone who understood it at the time. The commit message often explains why.

**Core commands for code archaeology:**

```bash
# What has changed recently? (who is active, what are they working on?)
git log --oneline -20

# What files change together? (implicit coupling)
git log --name-only --pretty=format: | sort | uniq -c | sort -rn | head -20

# Who wrote this confusing line? What was the PR about?
git blame path/to/file.go

# When was this function added? What was the context?
git log -S "function_name" --source --all

# What changed in a specific commit?
git show <commit-hash>

# What commits touched a specific file?
git log --follow path/to/file.go

# Full commit message for a commit
git log --format="%B" -n 1 <commit-hash>
```

**Reading git history strategically:**

```
Recent changes (last 30 days):   What is actively being worked on?
                                  These are the areas most likely to have bugs.

Large commits:                    Usually refactors, migrations, or major features.
                                  Read these to understand why the architecture looks the way it does.

Commits with "hotfix/emergency/   These reveal the fragile areas of the system.
rollback" in the message:        The comment above the confusing code that says
                                  "DO NOT REMOVE THIS" was probably added after an incident.

Commits that touch many files:   Cross-cutting changes (adding a field to an event,
                                  renaming a shared interface) reveal system-wide patterns.
```

**The git blame workflow:**

You encounter a mysterious line of code:

```python
# Why is this here? It looks wrong.
if user.created_at < datetime(2019, 3, 15):
    fee = 0
else:
    fee = calculate_fee(order)
```

```bash
git blame path/to/billing.py
# Shows: commit abc123 by alice 2019-03-14

git show abc123
# Commit message: "Legacy users grandfathered into free tier during migration"
# "Users who signed up before March 15, 2019 were promised free billing
#  during the transition to our new pricing model. This condition should
#  be removed when we complete the billing migration in Q3 2019."
# (It's now 2024 — this was never removed)
```

In 30 seconds, you went from "mysterious magic date" to "legacy condition from a 2019 migration that was never cleaned up." Now you can decide: is this still necessary, or is it dead code?

---

## Part 6: Find the Invariants and the Sharp Edges

An **invariant** is a condition that must always be true. Systems are built around invariants. Violating an invariant causes bugs, data corruption, or security vulnerabilities. Before making any change to a codebase, you must know what the invariants are.

**Where to find invariants:**

```go
// 1. Assertions and panics
func (a *Account) Debit(amount int64) {
    if a.Balance < amount {
        panic("invariant violated: debit cannot exceed balance")
    }
    a.Balance -= amount
}

// 2. Database constraints
CHECK (balance_cents >= 0)
UNIQUE (user_id, idempotency_key)

// 3. Comments with MUST / NEVER / ALWAYS
// MUST be called while holding the account lock
func (a *Account) unsafeDebit(amount int64) { ... }

// NEVER call this with a nil context
func (s *Service) Process(ctx context.Context, ...) { ... }

// 4. Validation logic at boundaries
func ValidateOrder(o *Order) error {
    if len(o.Items) == 0 {
        return errors.New("order must have at least one item")
    }
    if o.TotalCents != sumItems(o.Items) {
        return errors.New("order total must equal sum of item prices")
    }
    ...
}
```

**Sharp edges to look for explicitly:**

```
Global mutable state:    If multiple goroutines/threads access shared state without
                         synchronization, you have a race condition waiting to happen.
                         grep -r "var .* = " --include="*.go" | grep -v "func\|:="

Singletons:              Database connections, caches, configuration managers.
                         They seem convenient but hide dependencies and make testing hard.

Retry logic:             Is the operation idempotent before retrying?
                         Retrying a non-idempotent operation creates duplicate records.

Timeout handling:        Does every external call have a timeout?
                         grep -r "context.Background()" — these are often missing timeouts.

Error swallowing:        Does the code silently ignore errors?
                         grep -r "_ =" --include="*.go" | grep -v "_test"
                         grep -r "except:" --include="*.py" | grep -v "log\|raise"
```

---

## Part 7: Static Analysis Tools (Power Tools for Code Reading)

When reading a large codebase, manual tracing only gets you so far. Static analysis tools let you see patterns across the entire codebase in minutes.

**Dependency analysis:**

```bash
# Go module dependencies
go mod graph | head -20

# Python import graph (pip install pydeps)
pydeps mypackage --max-bacon=3

# Find circular imports
# Go: these don't compile; Python: these cause issues at runtime
grep -r "^import\|^from" --include="*.py" . | \
  awk -F: '{print $2}' | sort | uniq -c | sort -rn
```

**Finding the most complex code:**

```bash
# Lines of code per file (biggest files = most complex?)
find . -name "*.go" | xargs wc -l | sort -rn | head -20

# Cyclomatic complexity (Go)
go install github.com/fzipp/gocyclo/cmd/gocyclo@latest
gocyclo -over 15 .  # Functions with complexity > 15 are hard to understand

# Python complexity
pip install radon
radon cc . -a  # average cyclomatic complexity by file
```

**Finding the hottest code (most changed files):**

```bash
# Files changed most often = most actively developed = most likely to have bugs
git log --name-only --pretty=format: | grep -v '^$' | sort | uniq -c | sort -rn | head -20
```

**Finding all the places a function is called:**

```bash
# Go: who calls CreateOrder?
grep -r "CreateOrder" --include="*.go" . | grep -v "_test.go"

# Or use your IDE: "Find Usages" / "Go to References"
# This is often faster and shows the call hierarchy visually
```

**Linting configuration as documentation:**

The linting configuration tells you what patterns the team considers important:

```bash
cat .golangci.yml     # Go: enabled linters reveal team conventions
cat .pylintrc         # Python
cat .eslintrc.json    # JavaScript/TypeScript
cat checkstyle.xml    # Java

# What linters are enabled? They reveal what bugs the team has been burned by.
# errcheck enabled: they've been burned by unchecked errors
# govet enabled: alignment and type mismatches have been problems
# exhaustruct enabled: they've been burned by zero-value struct bugs
```

---

## Part 8: Running the System Locally

Reading code in isolation is always harder than reading code while you can run it. Your Day 1 task should include getting the system running locally.

**The setup hierarchy:**

```
1. README/DEVELOPMENT.md:     Start here. If it's outdated, updating it is
                               your first contribution.

2. docker-compose.yml:        If it exists, `docker compose up` is often all you need.

3. Makefile:                  `make help` or `make dev` — common targets:
                               make build, make test, make run, make lint

4. CI pipeline:               .github/workflows/ or .gitlab-ci.yml
                               The CI script is the authoritative "how to build" document.
                               If CI passes, this is the ground truth.
```

**Local data and test fixtures:**

```bash
# Find seed data / test fixtures
find . -name "fixtures" -type d
find . -name "testdata" -type d
find . -name "seed*.sql"
find . -name "*.fixture.json"

# Does the system have a development mode with fake data?
grep -r "DEV_MODE\|FAKE_DATA\|USE_STUBS" --include="*.go" .
grep -r "development\|staging" --include="*.env.example" .
```

**The rubber duck debugging technique for code reading:**

Once the system runs locally, you can validate your mental model:

1. Make a request to the system using `curl` or the test suite
2. Add a `log.Printf("HERE: order_id=%s", order.ID)` at key points
3. Observe the logs — does data flow where you expected?
4. Remove the log lines

This is faster than reading code to understand data flow, and it validates your mental model against reality.

```bash
# Watch logs in real time while making requests
kubectl logs -f deployment/order-service | grep "HERE"
# or
tail -f /var/log/app.log | grep "HERE"
```

---

## Part 9: Reading Code You Didn't Write (The Human Factor)

Code is written by people under time pressure, with changing requirements, with varying levels of experience. Understanding the human context makes the code more readable.

**Common patterns that look wrong but aren't:**

```python
# The "magic number" with no comment
RETRY_LIMIT = 7

# Read git blame: "7 was chosen because this is the max we can handle within
# the 30-second SLA window — retrying every 4 seconds with exponential backoff"
# It's not magic; it's engineering under constraint.

# The "duplicate code" that isn't
def process_us_payment(amount, card):
    ...

def process_eu_payment(amount, card):
    ...
    
# These look like DRY violations. But git history shows: EU payments have different
# tax rules, different fraud checks, and different retry limits — combining them
# into one function caused bugs in 2021. The duplication is intentional isolation.
```

**Comments that lie (the most dangerous kind):**

```python
# Returns the user's email address
def get_user_contact(user_id):
    user = db.find_user(user_id)
    return user.phone  # BUG: comment says email, code returns phone
```

Outdated comments are common in actively developed codebases. When a comment and the code disagree, **trust the code, not the comment.** The comment was correct when written; the code was changed without updating the comment.

**Copy-paste code: intentional or accidental?**

Some code looks identical across multiple files. This might be:
- Accidental duplication (a DRY violation to fix)
- Intentional isolation (each instance evolved differently, unifying them would couple them)

Check git history: if both copies change together (same commits), they should be unified. If they diverge (different changes over time), the duplication is probably intentional.

**Dead code:**

```bash
# Find functions defined but never called (Go)
go vet ./...
# More thorough dead code finder
go install golang.org/x/tools/cmd/deadcode@latest
deadcode .

# Find unused Python imports
pip install autoflake
autoflake --check -r .

# Find unreachable code
grep -n "return\|panic\|os.Exit" --include="*.go" . | \
  awk -F: '{print $1 ":" $2}' | sort -t: -k1,1 -k2,2n
```

Dead code is a trap: you think you can delete it safely, but sometimes it's still used through reflection, dynamic dispatch, or an import you missed. Always search for usages before deleting.

---

## Part 10: Making Your First Change

The fastest way to validate your mental model is to make a real change and ship it. Not a massive feature — a single, small, safe change. The goal is to verify that:
1. You understand where to make the change
2. You understand how to test the change
3. You understand the CI/CD pipeline
4. Your change doesn't break anything unexpected

**The progression of first changes:**

```
Level 1: Fix a typo in a comment or README        (zero risk, proves git workflow)
Level 2: Add a missing test for an edge case      (reads code, understands tests)
Level 3: Fix a small bug from the backlog         (reads code, understands data flow)
Level 4: Add a non-critical feature               (validates full understanding)
```

**The value of a small first PR is not the change — it is the signal:**

A merged PR is proof to your team that you:
- Can find your way around the codebase
- Understand the CI/CD pipeline and how to get code through it
- Write tests in the style the team expects
- Can navigate the code review process

It is also proof to yourself that your mental model is at least partially correct.

**What to do if you break something:**

Breaking something in your first week is normal and expected. The important signals are:
- Did the CI catch it before review? (good — tests worked)
- Did the reviewer catch it? (fine — code review worked)
- Did it reach production? (less good — understand why CI/review missed it)
- What was the blast radius? (small = acceptable first-week mistake; large = flag and learn)

The engineers who never break anything in their first month are usually the ones who didn't ship anything in their first month. Bias toward action; accept small mistakes; learn from them.

---

## Part 11: The 30-60-90 Day Ramp Plan

The 30-60-90 day plan is a widely used framework for onboarding. Here is what it looks like specifically for a software engineer ramping onto a new codebase:

**Days 1-7: Build the mental model.**

```
Day 1:  Setup environment, trace one request end-to-end, draw the box diagram
Day 2:  Read the data model (schema, key structs, event schemas)
Day 3:  Run all tests, read test names as documentation
Day 4:  Read git history — last 30 commits, identify recent focus areas
Day 5:  Find the invariants and sharp edges (assertions, panics, comments)
Day 6:  Make a Level 1 change (typo or README fix) — merge it
Day 7:  Write a doc: "What I understand about this system so far"
        (sharing forces clarity; the gaps in your doc reveal the gaps in your model)
```

**Days 8-30: Make a small real change.**

```
Week 2:  Pick a small bug (ideally something you noticed while reading code)
         Write the fix + add a test
         Get through code review — note every piece of feedback

Week 3:  Make a slightly larger change (small feature or non-trivial bug fix)
         Can you now predict where the bug is before you find it?

Week 4:  Attend an incident review or design review
         Can you follow the discussion without asking for context on every term?
         Write down every term you don't understand; look them up after
```

**Red flag at end of month 1:** You have read code for 30 days and not shipped anything.

This is more common than it should be. The psychological barrier is real: "I don't understand it well enough yet to make a change." But you will never understand it well enough by reading alone. The act of changing code (and having your change reviewed) forces the kind of understanding that reading cannot produce.

**Days 31-60: Own a component.**

```
By day 60:  You should be the person others ask about at least one area of the codebase
            You can review PRs in that area and explain why they are correct or not
            You have shipped at least 3-5 real changes independently
            You can sketch the architecture from memory without looking at the code
```

**Days 61-90: Be a multiplier.**

```
By day 90:  You are unblocking others, not asking others to unblock you
            You have identified at least one significant problem that predates your arrival
            You have a proposal for how to address it
            Your teammates consider you reliable for your area
```

**The calibration question at 90 days:**
> "If you had to explain this system to a new hire tomorrow, what would you say in 15 minutes?"

If you can answer that confidently, you have a functional mental model. If you hedge everything, your model is still incomplete.

---

## Part 12: L3 vs L5 vs L6 Calibration

How you approach an unfamiliar codebase is a signal that interviewers, skip-level managers, and new teammates observe closely. Here is what each level looks like:

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│              READING UNFAMILIAR CODE: SENIORITY CALIBRATION                       │
├──────────┬──────────────────────────────────────────────────────────────────────────┤
│ SIGNAL   │ L3 / Junior              L5 / Senior          L6 / Staff                │
├──────────┼──────────────────────────────────────────────────────────────────────────┤
│ Strategy │ Read top-to-bottom       Entry points +        Data model first +        │
│          │ Ask for walkthrough      trace one flow        entry points + tests       │
├──────────┼──────────────────────────────────────────────────────────────────────────┤
│ Time to  │ 3-6 months               2-4 weeks             3-7 days for mental model │
│ first    │ (if ever fully ramped)   (productive in        (reviewing PRs by week 1) │
│ PR       │                          month 1)                                        │
├──────────┼──────────────────────────────────────────────────────────────────────────┤
│ Git      │ Never looks at it        Uses git blame for    Analyzes git history as   │
│ history  │                          confusing code        a first step to understand │
│          │                                                 system evolution           │
├──────────┼──────────────────────────────────────────────────────────────────────────┤
│ Tests    │ Runs tests to see if     Reads test names as   Treats test coverage as   │
│          │ CI passes                documentation         a risk map; adds missing   │
│          │                                                 tests as a contribution    │
├──────────┼──────────────────────────────────────────────────────────────────────────┤
│ Data     │ Reads code, infers       Finds schema early,   Starts with schema before │
│ model    │ data model from code     uses it to orient     reading a single code file │
├──────────┼──────────────────────────────────────────────────────────────────────────┤
│ First    │ Waits until "I'm ready"  Ships a small change  Ships a Level 1 change    │
│ change   │ (takes too long)         by end of week 2      by end of day 3-5          │
├──────────┼──────────────────────────────────────────────────────────────────────────┤
│ Asks     │ Asks before reading      Reads first, then     Rarely needs to ask —     │
│ for help │ ("where is the X?")      asks targeted         synthesizes from code,     │
│          │                          questions ("why does  git, tests; asks when      │
│          │                          X use Y instead of Z?") something is genuinely   │
│          │                                                 undiscoverable from code   │
├──────────┼──────────────────────────────────────────────────────────────────────────┤
│ Blockers │ "I don't understand      "I don't understand   "The documentation         │
│ they     │ the codebase yet"        why this design       doesn't explain the        │
│ report   │                          decision was made"    original constraints —     │
│          │                                                 I need to talk to someone  │
│          │                                                 who was there"             │
└──────────┴──────────────────────────────────────────────────────────────────────────┘
```

The key L6 differentiator: L6 engineers treat code reading as an investigation, not a tutorial. They approach it with hypotheses ("I think this service owns the billing state") and validate them against code, tests, schema, and history. They are wrong sometimes, but they have a clear mental model of what they know and what they don't.

---

## Part 13: War Stories — Code Archaeology in Practice

**War Story 1: The Mystery Timeout**

A senior engineer joins a team. On day 3, she notices that every API call to the payment service has a hardcoded 5-second timeout. She doesn't understand why it's 5 seconds and not 10 or 30.

She runs `git log -S "timeout" --source --all path/to/payment_client.go`:

```
commit 8f3a91c
Author: Bob Chen <bob@company.com>
Date:   Fri Oct 13 16:22:00 2021

Emergency: reduce payment timeout from 30s to 5s

During today's incident, the payment provider went down for 45 minutes.
Every request held a DB connection for 30 seconds waiting for the payment
response. We ran out of DB connections and the entire API went down.
5 seconds is the max we can hold a DB connection safely.

This means some payment calls will time out and need to be retried by the
client. The payment provider confirmed their operations are idempotent.
```

In 30 seconds, she learned:
- There was a major incident in 2021
- The timeout is a constraint driven by DB connection pool exhaustion
- The payment provider is idempotent (so retries are safe)
- This is not a place to "fix" the timeout without understanding the connection pool math

This is 6 months of tribal knowledge, acquired in 30 seconds.

---

**War Story 2: The Comment That Saved a Migration**

An engineer is asked to migrate a billing table to a new schema. He reads the table and notices:

```sql
ALTER TABLE invoices ADD COLUMN v2_migrated BOOLEAN DEFAULT FALSE;
```

The column looks like a migration artifact — something that should have been cleaned up. He's about to add it to the cleanup list when he decides to check:

```bash
git log -S "v2_migrated" --source --all
```

```
commit 2c8f441
Author: Alice Park <alice@company.com>
Date:   Mon Mar 8 2021

Add v2_migrated flag for rollback safety

This flag marks which invoices have been migrated to the v2 billing system.
The v2 system is live for new invoices. We cannot roll back the DB migration
once the v2 billing service has read these invoices and applied discounts.

DO NOT REMOVE THIS COLUMN until the v1 billing service is completely
decommissioned. The v1 service checks this column to skip invoices it
has already handed off.
```

He checks: is the v1 billing service still running?

```bash
kubectl get deployment | grep billing
# billing-v1   1/1     Running
```

It is. Deleting that column would have broken billing for all legacy invoices. The column is load-bearing despite looking like an artifact.

---

**War Story 3: The Engineer Who Read for Three Months**

A mid-level engineer joins a team. He is conscientious and doesn't want to break anything. He spends 3 months reading code, attending meetings, and asking questions. He hasn't shipped a single PR.

At the 3-month mark, his manager asks: "What do you understand about the codebase that you didn't understand 3 months ago?"

He can answer the question. He has learned a lot. But his team has learned nothing about him: his coding style, his judgment, his approach to testing. He hasn't demonstrated that his understanding is correct by having his code reviewed.

At the end of Q1, his performance review notes: "Not yet productive. Team is uncertain about ability to deliver independently."

The lesson: reading without shipping builds private knowledge. Code review turns private knowledge into validated competence — visible to your team.

**The anti-pattern this reveals:**

```
"I'll ship once I understand it well enough."
→ You will never understand it well enough to feel confident.
→ The only way to get confident is to ship and get feedback.
→ Fear of being wrong is the real blocker, not lack of knowledge.
```

---

## Part 14: Practical Code Reading Exercises

### Exercise 1: Trace a Request End-to-End

**Setup:** Pick any open-source project (e.g., Prometheus, Gitea, Mattermost).

**Task:**
1. Clone the repo
2. Find the HTTP server entry point
3. Trace `POST /api/v1/login` end-to-end to the database
4. Draw the call chain on paper: handler → service → repository → SQL
5. Answer: where is the password hashed? where is the session token created?

**Time limit:** 30 minutes.

**What you'll learn:** Entry point finding, call graph tracing, security-sensitive code location.

---

### Exercise 2: Schema Archaeology

**Setup:** Take any project with a `db/migrations/` directory.

**Task:**
1. Read the migrations in chronological order (oldest first)
2. For each migration, write one sentence: "This migration added X because Y"
3. Reconstruct the ERD as it exists today
4. Find one table that has been modified multiple times — what story does it tell?

**Time limit:** 1 hour.

**What you'll learn:** How systems evolve, how business requirements drive schema changes, how to read migrations as a history of product decisions.

---

### Exercise 3: Git Blame an Interesting File

**Setup:** Any file in a large open-source project that has been modified many times.

**Task:**
1. Run `git blame` on the file
2. Find the 5 oldest lines — what were they doing in the original commit?
3. Find a line that has been changed 3+ times — what does its history say?
4. Find a commit message that explains a "why" you wouldn't have inferred from code

**Time limit:** 20 minutes per file.

---

### Exercise 4: Find All the Invariants

**Setup:** Take the payment processing module from any open-source billing library.

**Task:**
1. List every invariant you can find: database constraints, assertions, panics, validation
2. For each invariant, write: "This enforces [business rule]"
3. Find one invariant that is enforced in code but not in the database (or vice versa)
4. Is there any invariant that is documented in a comment but not enforced in code?

**Time limit:** 45 minutes.

---

## Part 15: The "Ramp Up" Behavioral Interview Answer

Interviewers at Google, Meta, and other companies ask behavioral questions specifically designed to assess how you operate when you don't have context. "Tell me about a time you joined a new team and ramped up quickly" is a classic.

**What they are evaluating:**
1. Do you have a systematic approach, or do you wing it?
2. Do you bias toward action (ship early) or toward analysis (read endlessly)?
3. Can you identify what you don't know and fill the gaps intentionally?
4. Do you make your teammates' lives better as you ramp up, or do you take their time?

**Strong answer structure (STAR format):**

```
SITUATION:  "I joined [team] and inherited [X lines of code / Y services]
             with [Z engineers] who were all focused on [major project]."

TASK:       "I needed to become productive quickly with minimal disruption
             to my teammates."

ACTION:     "In the first week, I used three strategies:
             (1) Entry points first — I traced the most important request
                 end-to-end and drew a box diagram before asking any questions.
             (2) Data model before code — I read the schema to understand
                 what the system stores, which gave me 70% of the context.
             (3) Ship something small first — by day 5 I had a test-only
                 PR merged, which validated my understanding and gave my
                 teammates signal that I was functional.

             By week 3, I had shipped a real bug fix. By week 6, I was
             reviewing others' PRs in the payments module."

RESULT:     "My manager noted in my 90-day review that I was the fastest-
             ramping engineer who had joined the team. I later documented
             the ramp-up strategy in the team wiki so future engineers could
             benefit from it."
```

**Common weak answers to avoid:**

| Weak answer | Why it's weak |
|-------------|---------------|
| "I read all the code" | Not credible; no one reads 500k lines. Shows no strategy. |
| "I asked my teammates a lot of questions" | Passive. Doesn't show self-direction. |
| "I shadowed the senior engineers" | Passive. No evidence of initiative. |
| "It took about 3 months to feel comfortable" | This is the anti-pattern. L5 shouldn't take 3 months. |
| "I studied the architecture docs" | Docs are often outdated. Good start but not sufficient. |

---

## Part 16: The Onboarding Document You Should Write

One of the most high-value contributions a new engineer can make in their first 30 days is to write (or update) an onboarding document for the next person. Here is why:

1. **Forces clarity:** Writing forces you to identify what you know vs. what you think you know.
2. **Creates value:** Every subsequent new hire benefits from your effort.
3. **Builds visibility:** Your manager and team see that you think beyond your immediate task.
4. **Surfaces gaps:** Reviewers will add the things you got wrong, giving you free corrections.

**Onboarding doc template:**

```markdown
# [Team/Service Name] Onboarding Guide

## What This System Does (1-paragraph summary)

## Architecture Overview
(box diagram: services, databases, queues, external dependencies)

## Key Entry Points
- API: handlers/api.go — HTTP server on port 8080
- Worker: workers/processor.go — Kafka consumer for "order_created" events
- Cron: jobs/report_generator.go — runs daily at 2am UTC

## Data Model
(table names, key relationships, what each table stores)

## How to Run Locally
1. ...
2. ...
3. Run `make test` to verify everything works

## How to Deploy
(brief description of CI/CD pipeline)

## Key Invariants (Do Not Break These)
- Orders table: total_cents must equal sum of order_items.price_cents × quantity
- Payment records are immutable once in status "captured"
- The idempotency_key on payment_requests must be globally unique per user

## Sharp Edges (Things That Have Caused Bugs Before)
- Timezone handling: all times stored in UTC, all user-facing times converted to user TZ
- The retry logic in payment_client.go is idempotent but the inventory deduction is NOT
- DB connection pool: max 100 connections total — do not increase pool size without updating HPA

## Common Tasks
- "How do I add a new API endpoint?" ...
- "How do I add a new Kafka consumer?" ...
- "How do I run a DB migration?" ...

## Who To Ask
- Database questions: @alice
- Payment integration: @bob  
- Infrastructure/K8s: @charlie
```

Writing this document and getting it reviewed is often more valuable than any code change in your first month.

---

## Part 17: Documentation Quality as a Signal

When you join a new codebase, the quality of documentation tells you a lot about the engineering culture. Read it critically:

**High-quality documentation signals:**
- Team invests in maintainability, not just shipping
- Architecture decisions are recorded with rationale (ADRs)
- Runbooks are updated after incidents
- README has "last updated" dates or is tied to CI validation

**Low-quality / absent documentation signals:**
- The system lives in people's heads (bus factor risk)
- New engineers are expected to ask for walkthrough
- Historical decisions are undocumented (you'll find out by breaking things)
- The system has grown organically without intentional design

Neither is good or bad per se — but it changes your onboarding strategy:

```
Good docs:     Start with docs, then validate against code
               (docs may still be outdated but give you orientation)

Poor docs:     Start with code, schema, tests — the source of truth
               Consider writing docs as your first contribution
               (high-leverage activity with immediate team appreciation)
```

---

## Part 18: Architecture Decision Records (ADRs)

ADRs are one of the highest-value artifacts in a codebase. They explain *why* the system looks the way it does — not what it does.

When you encounter a puzzling design decision ("why does this use gRPC but everything else uses REST?"), check for an ADR:

```bash
find . -name "ADR*" -o -name "adr-*" -o -name "*.adr.md"
ls docs/decisions/
ls docs/adr/
```

An ADR typically contains:
- **Title:** ADR-0042: Use Kafka instead of RabbitMQ for event streaming
- **Status:** Accepted / Deprecated / Superseded by ADR-0089
- **Context:** What was the problem?
- **Decision:** What was chosen?
- **Consequences:** What are the trade-offs we accepted?

Reading ADRs teaches you the constraints and trade-offs that shaped the current design. It prevents you from "fixing" things that look wrong but are actually the result of a deliberate decision.

**If there are no ADRs:** Note this. It means design decisions live in commit messages, PR descriptions, Slack threads, and people's heads. Your job during onboarding is to extract these from wherever they live.

---

## Part 19: Domain Knowledge vs. Technical Knowledge

An important distinction when ramping on a new codebase: **technical knowledge** (how the system works) is acquired by reading code. **Domain knowledge** (why the system works that way) requires talking to people.

Examples of domain knowledge you cannot get from code:
- "Why do we have both `users` and `accounts` tables? What's the semantic difference?"
- "Why is the fulfillment timeout 48 hours and not 24?"
- "Why does the system have a legacy v1 API that's still maintained?"
- "What happened in 2020 that caused us to add all this retry logic?"

Your code reading will surface these questions. Write them down. Then schedule 30 minutes with the most senior person on your team to answer them. Do this in the first 2 weeks, not the first 2 months.

**The questions that signal strong onboarding:**

An L5 engineer's questions in week 1:
- "I noticed orders can be in status `pending` for up to 72 hours — is that expected or a bug?"
- "The payment service has two retry implementations — one in the HTTP client and one in the queue consumer. Were they designed to coexist?"
- "git blame shows this function hasn't been touched since 2018. Is it still used?"

These questions show:
1. You have read the code carefully (you found the anomalies)
2. You know the difference between "this is a design decision" and "this might be a bug"
3. You are verifying your mental model before assuming it's correct

---

## Part 20: Code Reading Anti-Patterns

**Anti-Pattern 1: "I'll ask first, read second"**

Asking your teammates for a walkthrough is the least efficient way to ramp up. Their time is limited. Their explanation will be at 10,000 feet. You will not retain it without the anchor of having read the code first.

Better: Read the code, form a hypothesis ("I think the order is processed by OrderService.Process() and then published to Kafka"), then ask: "Is my understanding of this flow correct?"

---

**Anti-Pattern 2: "I'll wait until I understand it before shipping"**

This is the most common anti-pattern. The feeling "I don't understand it well enough yet" is always there. It doesn't go away by reading more. It goes away by shipping and getting feedback.

---

**Anti-Pattern 3: Reading without taking notes**

Reading 500,000 lines of code without building an external artifact (a doc, a diagram, a set of notes) is like watching a lecture without taking notes. The information doesn't stick, and you have nothing to show for the time spent.

Write things down as you read. Even bullet points. Even wrong bullet points (you'll correct them). The act of writing forces synthesis.

---

**Anti-Pattern 4: Following every import recursively**

When you're tracing a function and it calls another function, the temptation is to open that function and read it fully before returning to the original. This leads to reading 20 levels deep and losing the thread of what you were trying to understand.

Better: treat function calls as black boxes at first. Read the function signature and the comment (if any). Trust that it does what it says. Only go deeper if the function is the source of your confusion.

---

**Anti-Pattern 5: Trusting comments over code**

Comments lie. Code cannot. When they conflict, trust the code. Note the lie (update the comment as a contribution).

---

**Anti-Pattern 6: Skipping the tests**

Tests are often more informative than the code they test. A well-named test like `TestOrderCancellationDoesNotRefundNonRefundableItems` tells you a complete business rule in one line — a rule you might spend 20 minutes trying to infer from reading the service code.

---

**Anti-Pattern 7: Not using the IDE**

Manually grepping for symbol references is fine for quick checks. But for understanding complex call graphs, IDE features are dramatically faster:
- "Go to Definition" follows a reference to its source
- "Find All References" shows everywhere a function is called
- "Show Call Hierarchy" shows the full call tree
- "Rename Symbol" shows all the places a name is used

If you're reading a 500,000-line codebase with only `grep`, you're working harder than you need to.

---

## Part 21: When to Ask for a Walkthrough

Reading the code first is not the same as never asking for help. There are times when a 15-minute conversation with a senior engineer saves you 3 days of reading:

**Good times to ask:**
- You have found an anomaly you cannot explain by any hypothesis ("the payment service skips validation for users where `legacy=true` — I can't find why")
- You need domain context that doesn't exist in the code ("why is the discount applied before tax and not after?")
- You have read the code and formed a hypothesis and want to validate it ("I think the session is stored in Redis with a 24-hour TTL — is that right?")
- You are stuck in a local minimum — reading the same code and not making progress for 2+ hours

**Poor times to ask:**
- You haven't read the code yet ("can you explain how the payment service works?")
- You want confirmation of something you can verify yourself ("does this function return null or throw?")
- You want to avoid the discomfort of confusion ("I don't understand this code, can you walk me through it?")

The ratio: for every hour you spend asking questions, you should spend at least 4 hours reading independently. This ratio will improve over time as your mental model becomes complete.

---

## Part 22: System Diagram Styles for Your Mental Model

Different diagram types reveal different aspects of the system. Use all of them:

**1. Box diagram (architecture overview):**

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  API Service │───▶│ Order Service│───▶│   Database   │
│  (HTTP/REST) │    │  (Business   │    │   (MySQL)    │
│              │    │   Logic)     │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
                           │                              
                           ▼                              
                    ┌──────────────┐    ┌──────────────┐
                    │    Kafka     │───▶│  Fulfillment │
                    │  (Events)   │    │   Service    │
                    └──────────────┘    └──────────────┘
```

Reveals: components and their relationships. Good for orientation.

**2. Sequence diagram (one flow end-to-end):**

```
Client      API         OrderService    DB           Kafka
  │          │                │          │              │
  │─POST ──▶│                │          │              │
  │         │─CreateOrder()─▶│          │              │
  │         │                │─INSERT──▶│              │
  │         │                │◀─OK──────│              │
  │         │                │─Publish──────────────────▶
  │         │◀─201 Created───│          │              │
  │◀─resp───│                │          │              │
```

Reveals: ordering and timing of operations. Good for understanding transactions.

**3. Data flow diagram:**

```
user input ──▶ validate ──▶ normalize ──▶ persist ──▶ events ──▶ cache
                  │                           │
                  ▼                           ▼
            return 400              audit log + metrics
```

Reveals: how data is transformed and stored. Good for understanding correctness.

**4. State machine diagram:**

```
              ┌──────────────────────────────────────────┐
              │                  ORDER                    │
              └──────────────────────────────────────────┘
                                   │
            create                 │ pending
            ─────────────────────▶ │
                                   │
                    payment_success │           payment_failed
                ┌──────────────────┴────────────────────────────────┐
                │                                                    │
                ▼                                                    ▼
          confirmed                                          payment_failed
                │                                                    │
    fulfilled   │                                          customer   │
    ────────────▶                                          cancels    │
                │                                         ────────────▶ cancelled
                ▼
          fulfilled
```

Reveals: valid state transitions. Absolutely critical for understanding systems with complex lifecycle.

---

## Part 23: Tools Reference Card

```
┌────────────────────────────────────────────────────────────────────────────┐
│                   CODE READING TOOLS CHEAT SHEET                          │
├───────────────────────────────┬────────────────────────────────────────────┤
│ TASK                          │ COMMAND / TOOL                             │
├───────────────────────────────┼────────────────────────────────────────────┤
│ Find entry points             │ grep -r "func main\|http.Listen\|          │
│                               │   StartServer\|RegisterHandler"            │
│                               │   --include="*.go" .                       │
├───────────────────────────────┼────────────────────────────────────────────┤
│ Trace a function's callers    │ IDE: Find All References                   │
│                               │ grep -r "FunctionName" --include="*.go" .  │
├───────────────────────────────┼────────────────────────────────────────────┤
│ Find when code was added      │ git log -S "function_name" --source --all  │
├───────────────────────────────┼────────────────────────────────────────────┤
│ See who wrote a line          │ git blame path/to/file.go                  │
├───────────────────────────────┼────────────────────────────────────────────┤
│ Find the hottest files        │ git log --name-only --pretty=format: |     │
│                               │   sort | uniq -c | sort -rn | head -20    │
├───────────────────────────────┼────────────────────────────────────────────┤
│ Find complex functions        │ gocyclo -over 15 .   (Go)                  │
│                               │ radon cc . -a         (Python)             │
├───────────────────────────────┼────────────────────────────────────────────┤
│ Find unused code              │ deadcode .  (Go)                           │
│                               │ autoflake --check -r .  (Python)           │
├───────────────────────────────┼────────────────────────────────────────────┤
│ Find all assertions/panics    │ grep -rn "panic\|assert\|must\|            │
│                               │   invariant" --include="*.go" .            │
├───────────────────────────────┼────────────────────────────────────────────┤
│ Find global state             │ grep -rn "^var " --include="*.go" .        │
│                               │   | grep -v "_test.go"                     │
├───────────────────────────────┼────────────────────────────────────────────┤
│ Find error swallowing         │ grep -rn "_ =" --include="*.go" .          │
│                               │   | grep -v "_test.go"                     │
├───────────────────────────────┼────────────────────────────────────────────┤
│ Find missing timeouts         │ grep -rn "context.Background()"            │
│                               │   --include="*.go" . | grep -v "_test"     │
├───────────────────────────────┼────────────────────────────────────────────┤
│ Generate coverage report      │ go test -coverprofile=c.out ./...          │
│                               │ go tool cover -html=c.out                  │
├───────────────────────────────┼────────────────────────────────────────────┤
│ Find schema files             │ find . -name "*.sql" -o -name "*.proto"    │
│                               │   -o -name "*.avsc" -o -name "*.graphql"   │
├───────────────────────────────┼────────────────────────────────────────────┤
│ Find ADRs                     │ find . -name "ADR*" -o -name "adr-*"       │
│                               │   -o -path "*/decisions/*.md"              │
└───────────────────────────────┴────────────────────────────────────────────┘
```

---

## Part 24: The Onboarding Interview Question

Some interviewers ask: "Walk me through how you would onboard a new engineer to a system you own."

This question tests whether you have thought about your system from the perspective of someone who doesn't know it. An L5 answer shows a systematic approach. An L6 answer includes what is non-obvious or dangerous, and has been battle-tested.

**Strong answer structure:**

```
"I would structure the first week around four things:

 1. Architecture tour (30 min): I'd walk through the box diagram — 
    components, data flows, integration points. Not code — just the map.

 2. Trace one request (2 hours together): We'd sit down and trace the 
    most important request in the system end-to-end, from the entry 
    point to the database and back. I'd let them do the navigation, 
    I'd fill in context.

 3. The invariants document (15 min): I'd show them the list of things 
    that cannot be violated — the database constraints, the ordering 
    guarantees, the idempotency assumptions. These are the landmines.

 4. First PR review (first week): I'd ask them to make a small change 
    and walk me through their PR description. The PR description tells 
    me more about their understanding than the code does.

For self-service resources: we have an onboarding doc in Confluence 
with the box diagram, the schema, and a list of common tasks. I update 
it after every new hire tells me what was unclear."
```

---

## Part 25: The Five Levels of Code Understanding

Reading unfamiliar code is not binary. Understanding exists on a spectrum. Knowing which level you're at for each component helps you prioritize where to go deeper.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│              FIVE LEVELS OF CODE UNDERSTANDING                                 │
├──────────┬──────────────────────────────────────────────────────────────────────┤
│ Level 1  │ ORIENTATION                                                          │
│          │ "This component exists and handles X"                               │
│          │ Can locate the files; cannot explain what they do                   │
├──────────┼──────────────────────────────────────────────────────────────────────┤
│ Level 2  │ FUNCTION                                                             │
│          │ "This component does X by doing Y"                                  │
│          │ Can explain the happy path; doesn't know failure modes              │
├──────────┼──────────────────────────────────────────────────────────────────────┤
│ Level 3  │ INVARIANTS                                                           │
│          │ "This component does X and requires Y to be true"                   │
│          │ Knows the constraints; can predict what changes are safe            │
├──────────┼──────────────────────────────────────────────────────────────────────┤
│ Level 4  │ HISTORY                                                              │
│          │ "This component does X because of decision Y made in Z"             │
│          │ Understands the "why"; can evaluate alternatives intelligently      │
├──────────┼──────────────────────────────────────────────────────────────────────┤
│ Level 5  │ OWNERSHIP                                                            │
│          │ "I can predict how this component will behave in any scenario"      │
│          │ Can review all changes, design extensions, and debug any incident   │
└──────────┴──────────────────────────────────────────────────────────────────────┘
```

**The goal for L5 after 90 days:** Level 4 or 5 for your primary area; Level 3 for adjacent areas; Level 2 for the rest of the system.

**The goal for L6 after 90 days:** Level 5 for your domain; Level 3-4 for the entire system; able to review any PR across the system for correctness.

---

## Part 26: Reading Code in a Production Incident

Reading unfamiliar code under incident pressure is a distinct skill. You have no time for systematic reading. The approach changes:

**During an incident, code reading is hypothesis-driven:**

```
Step 1: Look at the error / symptom
        "payment_service returning 500 errors since 14:23"

Step 2: Form 3 hypotheses (fastest to verify first)
        H1: Database is down or query is failing
        H2: External payment provider is returning errors
        H3: Recent deploy introduced a bug

Step 3: Check metrics first, not code
        (metrics tell you which hypothesis to pursue; code reading confirms)
        → check db_query_error_rate: normal
        → check payment_provider_error_rate: 100% on /charge endpoint
        → H2 confirmed: no need to read application code

Step 4: Mitigate first, understand fully later
        (circuit breaker, roll back, failover — don't need to read code for this)
        
Step 5: Post-incident: now read the code to understand why the circuit
        breaker didn't kick in sooner, and fix the gap
```

**The anti-pattern during incidents:** reading code before checking metrics. Metrics tell you where to look; code tells you what you're looking at. Check metrics first.

---

## Part 27: System-Level Code Reading (Multiple Services)

When you're responsible for multiple services (a common L5/L6 expectation), the entry points strategy expands:

**Cross-service code reading checklist:**

```
□ Find all the integration points between services
  (HTTP calls, gRPC calls, Kafka topics, shared databases)

□ For each integration point, find:
  - The producer (who writes/sends)
  - The consumer (who reads/receives)  
  - The contract (schema, SLO, error handling)

□ Find all the shared state:
  - Databases that multiple services write to (split brain risk)
  - Caches that multiple services read from (invalidation risk)
  - Configuration that multiple services consume (change blast radius)

□ Find the failure modes at integration points:
  - What happens if Service A is slow? Does B time out gracefully?
  - What happens if a Kafka topic has a schema change? 
    Does the consumer handle unknown fields?
  - What happens if the DB is temporarily unavailable? 
    Does the service queue writes or fail fast?
```

---

## Part 28: Pre-Interview Drill — 12 Questions

Use these to test your readiness to discuss "reading unfamiliar code" in any interview or in any conversation where you need to demonstrate engineering judgment:

**1.** You've just been given access to a 400,000-line codebase. What's the first thing you do?
> *Trace one request end-to-end. Find the entry point and draw the call chain.*

**2.** How do you decide which parts of the codebase to read first vs. skip?
> *Entry points (critical path), data model (reveals purpose), tests (spec), git history for sharp edges.*

**3.** Why is the data model more informative than the code for understanding what a system does?
> *Code is implementation; data is what the system remembers. The schema reflects business rules, constraints, and product decisions made over years.*

**4.** You find a magic number in the code (e.g., `timeout = 17`). What do you do?
> *git blame the line, read the commit message. Magic numbers almost always have a story.*

**5.** The tests are all failing when you clone the repo. What does that tell you?
> *Either the dev setup is broken (common), or there's a pre-existing test failure. Fix it — it's your first contribution and your baseline.*

**6.** How do you find the invariants in an unfamiliar codebase?
> *Assertions/panics, database constraints, comments with MUST/NEVER/ALWAYS, validation at boundaries.*

**7.** What is the most common mistake engineers make when ramping onto a new codebase?
> *Reading without shipping. The act of making a change and having it reviewed is how you validate your mental model.*

**8.** How would you explain to a product manager why you need 2 weeks before you can give an estimate on a new feature?
> *"I need to understand the data model and the invariants of the system before I can safely estimate the blast radius of a new feature. Reading the code and running the tests lets me identify the constraints that will affect the timeline."*

**9.** What does low test coverage in a module tell you?
> *It's either legacy code (predates test culture), hard to test (often because of poor isolation), or rarely changed. It's a risk zone — any change to it could break things silently.*

**10.** How long should it take an L5 engineer to make their first real code change?
> *No more than 2 weeks. A Level 1 change (typo, test) within the first week is ideal.*

**11.** What's the difference between domain knowledge and technical knowledge, and how do you acquire each?
> *Technical knowledge (how) = code, tests, schema, git. Domain knowledge (why) = conversations with senior engineers and product owners. Both are required; only the latter requires interrupting teammates.*

**12.** You're in a design review for a new feature in a system you've been on for 2 months. You notice a proposed change that might violate an invariant you found in the code. What do you do?
> *Raise it immediately: "I noticed in the schema that [X] must always be [Y]. Does this design maintain that invariant?" If you're wrong, you'll learn something. If you're right, you prevent a bug.*

---

## Key Takeaways

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      KEY TAKEAWAYS: READING UNFAMILIAR CODE                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  1. STRATEGY       Entry points → data model → tests → git history             │
│                    This order builds understanding in the fastest sequence      │
│                                                                                 │
│  2. MENTAL MODEL   You need 4 things: data flow, state ownership,              │
│                    invariants, failure modes                                    │
│                                                                                 │
│  3. SHIP EARLY     A small merged PR by day 5-7 validates your mental model    │
│                    and makes your competence visible to your team               │
│                                                                                 │
│  4. GIT BLAME      30 seconds of git blame replaces days of guessing           │
│                    why mysterious code exists                                   │
│                                                                                 │
│  5. TESTS = SPEC   Test names are the most dense documentation in the          │
│                    codebase. Read them before reading the implementation.       │
│                                                                                 │
│  6. DATA FIRST     The schema reveals purpose. Read it before reading code.    │
│                                                                                 │
│  7. ANTI-PATTERN   Reading for 3 months without shipping = invisible           │
│                    competence that no one can vouch for                         │
│                                                                                 │
│  8. 30-60-90       Day 7: box diagram. Week 4: first real change.              │
│                    Month 2: own a component. Month 3: be a multiplier.         │
│                                                                                 │
│  9. CONTRIBUTE     Update the README, write the onboarding doc, add           │
│                    missing tests — high-leverage, visible, permanent.           │
│                                                                                 │
│  10. DOMAIN VS.    Technical knowledge from code/tests/schema.                 │
│      TECHNICAL     Domain knowledge from people. Don't skip either.            │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Homework

**Immediate (this week):**

1. Pick an open-source project you've never read before (Prometheus, Gitea, Mattermost, Temporal). Spend 2 hours applying the entry points strategy. Write a 1-paragraph summary of what the system does and how it works.

2. `git blame` the most confusing piece of code in any codebase you've worked on. What does the history say?

3. Find the invariants in any payment or financial system you have access to. List them. Are they all enforced in both code and the database?

**Before your next interview:**

4. Practice the "tell me about a time you ramped up quickly" STAR story. Time yourself: can you tell it in 2 minutes?

5. Review an open-source codebase's schema. Write 5 business rules that the schema enforces. (Example: "users.email has a UNIQUE constraint, so the system doesn't allow duplicate accounts per email.")

---

---

## Part 29: Reading Distributed Systems Code

Reading a distributed system is harder than reading a monolith because behavior emerges from the interaction of multiple components. The same strategies apply, but the failure modes are more subtle.

**The distributed-specific questions to answer first:**

```
□ What is the consistency model?
  - Are reads from the database or from a cache?
  - Is the cache write-through or write-behind?
  - Can users see stale data? For how long?

□ Where is the state?
  - Which service is the source of truth for each data type?
  - What happens if two services try to write the same record simultaneously?
  - Is there a distributed lock? What happens if the lock service is unavailable?

□ How are failures handled at the boundary?
  - Does Service A retry on timeout? Is the operation idempotent?
  - Does Service A circuit-break on errors? What is the fallback?
  - What happens if a message is processed twice (at-least-once delivery)?

□ What is the event ordering guarantee?
  - Are events processed in order per partition? Per user? Globally?
  - Can events arrive out of order? Does the code handle that?
  - What happens if an event is lost?
```

**Finding the consistency model in code:**

```go
// This tells you: the system reads from cache first, falls back to DB
func (s *UserService) GetUser(ctx context.Context, id string) (*User, error) {
    // Check cache first
    if u, err := s.cache.Get(ctx, "user:"+id); err == nil {
        return u, nil          // stale if DB was updated and cache not invalidated
    }
    return s.db.GetUser(ctx, id)
}

// This tells you: write-through cache (writes to both)
func (s *UserService) UpdateUser(ctx context.Context, u *User) error {
    if err := s.db.UpdateUser(ctx, u); err != nil {
        return err
    }
    s.cache.Set(ctx, "user:"+u.ID, u, 5*time.Minute)  // invalidate or update
    return nil
}
// Question: what if cache.Set fails? The cache is stale but DB is updated.
// This is a race condition. git blame to see if this was intentional.
```

---

## Part 30: Reading Security-Sensitive Code

Some parts of the codebase deserve extra scrutiny: authentication, authorization, payment processing, and anything that handles personal data. Apply the reading strategy from Chapter 115 (Security Mindset) when you reach these areas.

**Red flags to look for in security-sensitive code:**

```python
# Red flag 1: Algorithm confusion in JWT
jwt.decode(token, SECRET)
# Should be: jwt.decode(token, SECRET, algorithms=["HS256"])

# Red flag 2: SQL without parameterization
cursor.execute(f"SELECT * FROM users WHERE email = '{email}'")
# Should be: cursor.execute("SELECT * FROM users WHERE email = ?", (email,))

# Red flag 3: User input in a file path
filepath = f"/uploads/{user_id}/{filename}"
open(filepath)  # Path traversal: filename could be "../../etc/passwd"

# Red flag 4: HTTP request with user-provided URL (SSRF)
response = requests.get(url_from_user)

# Red flag 5: Logging sensitive data
logger.info(f"Processing payment for card {card_number}")
```

When you find one of these, don't fix it immediately. Note it, understand the blast radius, and report it to the team with context. A "fix" without understanding the full context can introduce a different vulnerability.

---

## Part 31: Technical Debt Archaeology

Every large codebase contains technical debt. The skill is distinguishing between debt that is:
- **Intentional and tracked:** shortcuts made deliberately, with a plan to address later
- **Accidental and forgotten:** things that "we meant to fix" but never did
- **Unknown:** patterns that were correct when written but are now wrong

**Finding technical debt in code:**

```bash
# Explicit TODOs and FIXMEs
grep -rn "TODO\|FIXME\|HACK\|XXX\|DEBT" --include="*.go" . | wc -l
grep -rn "TODO\|FIXME\|HACK\|XXX\|DEBT" --include="*.go" . | head -20

# Commented-out code (often dead code or failed experiments)
grep -rn "^//" --include="*.go" . | grep -v "// " | head -20
# (lines starting with // but not followed by a space — often code)

# "temporary" things that became permanent
grep -rn "temp\|temporary\|quick fix\|workaround" --include="*.go" . -i
```

**Categorizing debt:**

```
HIGH RISK (address soon):
  - Security vulnerabilities (SQL injection, missing auth, plaintext secrets)
  - Data integrity risks (missing transactions, race conditions)
  - Debt that is actively blocking feature work

MEDIUM RISK (note and track):
  - Performance debt (N+1 queries, missing indexes, expensive operations in hot paths)
  - Reliability debt (missing timeouts, poor error handling, no circuit breakers)
  - Maintainability debt (God classes, untested critical paths, no comments on sharp edges)

LOW RISK (accept or defer):
  - Style debt (naming inconsistencies, missing documentation on non-critical code)
  - Architecture debt (wrong abstractions that don't cause bugs yet)
```

Your job in the first 30 days is not to fix technical debt — it's to understand which debt is load-bearing and which is safe to address.

---

## Part 32: Learning From Code Reviews on Your PRs

Code reviews on your first PRs are a compressed learning experience. Each comment is a piece of the mental model you didn't have yet.

**How to extract maximum learning from code review:**

```
For each comment, ask:
  1. What did I not understand about the codebase that led to this mistake?
  2. Where is the code I should have read first?
  3. Is there an invariant or convention I violated?
  4. What would I search for next time to avoid this mistake?
```

**A common pattern:**

Engineer makes a change that breaks a subtle invariant. Reviewer comments: "This will cause duplicate charges if the network request is retried."

The engineer didn't know:
- The payment operation is not idempotent (yet)
- The network client retries on timeout
- An idempotency_key must be passed to prevent duplicates

The fix is 5 lines. But the learning is: *"before touching payment code, check whether the operation is idempotent and understand the retry behavior."* This learning prevents the same class of bug in the future.

Write down these learnings. They are building your mental model. After 10 code reviews, you will have a pattern library specific to this codebase.

---

## Part 33: When You Inherit a Legacy Codebase

Inheriting a legacy codebase (typically: old technology, minimal tests, no living author) is a specific scenario that requires additional strategies.

**The characterization test approach** (from Chapter 116):

Before changing anything in a legacy codebase without tests, write characterization tests:

```python
# Don't know what this function returns? Test what it currently returns.
# The current behavior IS the spec until you decide to change it.
def test_legacy_discount_function_characterization():
    result = legacy_calculate_discount(user_id=1001, order_total=100.00)
    assert result == 5.00  # This is what it returns NOW — not necessarily what it SHOULD return
    # Note: user 1001 was created before 2019 (legacy pricing)
```

Characterization tests give you a safety net before refactoring. They also force you to understand the current behavior — which is the prerequisite for understanding whether a change is safe.

**The strangler fig for reading:**

You don't have to understand all legacy code at once. Pick one flow. Understand it fully. Then expand outward from there. Trying to understand all 500,000 lines before making a change is the same mistake as linear reading.

**Questions to ask when inheriting legacy code:**

```
□ Who were the original authors? Can I talk to them?
  (Even 30 minutes with the original author saves weeks of reverse-engineering)

□ Why was it built this way? Was it a constraint at the time?
  (Legacy code is often correct for its original context; understanding the context
  prevents you from "fixing" things that are actually intentional)

□ What does it still do correctly that I must not break?
  (Find the invariants before changing anything)

□ What has broken before? (Look for hotfixes, rollbacks in git history)
  (Previous failures are the best predictor of future failures)

□ Is there a migration plan? Or is this permanent?
  (Context: if there's a plan to replace it in 6 months, the risk calculus changes)
```

---

## Part 34: Companion Resources

- **"Working Effectively with Legacy Code"** — Michael Feathers (the definitive guide to changing code without tests)
- **"The Art of Readable Code"** — Boswell & Foucher (naming, comments, and structure that aids reading)
- **"Code Reading: The Open Source Perspective"** — Diomidis Spinellis (systematic approach to reading unfamiliar code)
- **"A Philosophy of Software Design"** — John Ousterhout (what makes code easy vs. hard to read; deep modules vs. shallow modules)
- **git-blame** documentation and tutorials — surprisingly powerful, rarely taught
- **"Accelerate"** — Forsgren, Humble, Kim (data on what leads to high-performing engineering orgs; related: time-to-first-commit as a productivity metric)

---

## Vocabulary Quick Reference

| Term | One-line definition |
|------|---------------------|
| Mental model | Internal representation of a system's data flow, state, invariants, and failure modes |
| Entry point | Where external input enters the system (HTTP handler, queue consumer, cron job) |
| Characterization test | Test that captures current behavior of code as its spec, before refactoring |
| Invariant | A condition that must always be true; violating it causes bugs or data corruption |
| git blame | Shows which commit last modified each line, with author and message |
| Dead code | Code defined but never executed; safe to delete if no dynamic dispatch or reflection |
| ADR | Architecture Decision Record; documents the why behind a design decision |
| Technical debt | Shortcuts or suboptimal designs that create future maintenance cost |
| Code archaeology | Using git history, blame, and log to understand the history of a codebase |
| L=λW | Little's Law; also the mental model principle: latency × arrival rate = queue depth |

---

## Part 35: The Reading Session Template

When starting a formal "read this codebase" session, use this template to stay structured:

```markdown
# Code Reading Session — [System Name] — [Date]

## Goal of this session
(What am I trying to understand?)

## Entry points found
- [entry_point_1]: [description]
- [entry_point_2]: [description]

## Request traced
Flow: [component A] → [component B] → [storage] → [response]
Key observations:
- [observation 1]
- [observation 2]

## Data model
Tables / key structs:
- [table 1]: [purpose]
- [table 2]: [purpose]
Key relationships:
- [table 1] → [table 2]: [cardinality]

## Invariants found
- [invariant 1]: enforced by [DB constraint / code assertion / both]
- [invariant 2]: enforced by [...]

## Sharp edges
- [sharp edge 1]: [why it's dangerous]
- [sharp edge 2]: [...]

## Questions to answer next
- [question 1]: I think [hypothesis] — need to verify by [action]
- [question 2]: The [X] looks unusual — git blame to understand why

## Things I don't understand yet
- [unknown 1]
- [unknown 2]

## First PR I could make
[description of small, safe change that would validate my understanding]
```

Filling this out after your first 2-4 hours of reading forces you to synthesize what you've learned and identify the gaps explicitly.

---

## Part 36: Memorable Quotes

> *"Programs must be written for people to read, and only incidentally for machines to execute."* — Harold Abelson, SICP

> *"Any fool can write code that a computer can understand. Good programmers write code that humans can understand."* — Martin Fowler

> *"Code is like humor. When you have to explain it, it's bad."* — Cory House

> *"The most important skill in software engineering is not writing code. It is reading code."* — paraphrase from Working Effectively with Legacy Code

> *"There is no such thing as 'I'll figure it out when I get there.' Ship something. Reading is private knowledge. A merged PR is public proof."* — engineering manager at a large tech company

> *"The git log is a time machine. Use it."* — from internal engineering docs at a large tech company

---

## Part 37: Code Reading and the Design Interview

In a system design interview, you will sometimes be asked to reason about a system you've designed before — "how would a new engineer understand this system?" or "what would make this system hard to maintain?"

Use the mental model framework as your answer:

```
"A new engineer would need to understand four things:
 
 1. Data flow:       Where does [the core entity] enter the system?
                     How is it transformed? Where does it persist?
                     Answer: trace POST /[endpoint] to DB write.
 
 2. State ownership: Which service is the source of truth for [X]?
                     We designed [ServiceA] to own [entity], so the
                     schema lives there and other services query via API.
 
 3. Invariants:      The key invariant is [X must always be Y].
                     It's enforced by [DB constraint + service validation].
                     Violating it would cause [Z].
 
 4. Failure modes:   If [Component] fails, [behavior].
                     We handle it by [circuit breaker / cache / graceful degradation]."
```

This answer signals to the interviewer that you think about systems from the perspective of someone who has to maintain them — an L5/L6 quality signal.

---

## Part 38: The Five Questions Every Senior Engineer Should Be Able to Answer About Any System They Own

L5 engineers are expected to "own" components. Ownership means you can answer these five questions for your area without looking anything up:

```
1. "What does this system do?"
   (1-paragraph, non-technical summary — you should be able to explain it to a PM)

2. "What happens when [component X] fails?"
   (failure modes, blast radius, recovery path)

3. "What are the invariants I must not break?"
   (data integrity, ordering guarantees, idempotency requirements)

4. "What is the capacity envelope?"
   (current QPS, limit before degradation, time to provision more)

5. "What is the most dangerous part of this codebase to change?"
   (the area with the least tests, the most implicit dependencies, or the history of incidents)
```

If you cannot answer #5, you have not finished reading the codebase. The "most dangerous area" insight requires having read enough of the code to form an opinion about relative risk — which is a strong signal that you have built a real mental model.

---

## Final Pre-Interview Checklist

Before any interview where you might be asked about ramping up on a new codebase, or asked to reason about how a system is built:

- [ ] Can you explain the 5-step code reading strategy? (Entry points → data model → tests → git history → invariants)
- [ ] Can you articulate why data model comes before code?
- [ ] Can you give a concrete example of git blame revealing a "why" that wasn't in the code?
- [ ] Can you explain what an invariant is and give 2-3 examples from any system?
- [ ] Can you describe your first 7 days joining a new team?
- [ ] Do you have a STAR story for "ramp up quickly" that is < 2 minutes?
- [ ] Can you explain L3 vs L5 vs L6 approaches to a new codebase in 30 seconds?
- [ ] Can you describe the "reading for 3 months without shipping" anti-pattern and why it happens?
- [ ] Do you know the difference between domain knowledge and technical knowledge?
- [ ] Can you describe how you'd onboard a new engineer to a system you own?

---

## 30-Day Study Schedule

**Week 1: Foundations**
- Day 1: Read Parts 1-3 (mental model, entry points, data first)
- Day 2: Apply entry points strategy to an open-source project (Exercise 1)
- Day 3: Read Parts 4-6 (tests, git history, invariants)
- Day 4: Apply git blame to real code (Exercise 3)
- Day 5: Read Parts 7-9 (tools, running locally, human factor)

**Week 2: Practice**
- Day 6: Apply schema archaeology to a real project (Exercise 2)
- Day 7: Find all invariants in a payment module (Exercise 4)
- Day 8: Read Parts 10-12 (first change, 30-60-90, calibration)
- Day 9: Read war stories (Parts 13) and internalize the anti-pattern
- Day 10: Draft your "ramp up quickly" STAR story

**Week 3: Application**
- Day 11: Read Parts 14-20 (exercises, behavioral interview, onboarding doc, ADRs)
- Day 12: Practice the behavioral interview answer out loud (timed: 2 minutes)
- Day 13: Read Parts 21-28 (diagram styles, tools reference, distributed systems)
- Day 14: Write an onboarding document for any system you know well

**Week 4: Integration**
- Day 15-21: Apply the full reading strategy to one unfamiliar codebase
  - Day 15: Entry points + request trace → box diagram
  - Day 16: Data model → ERD reconstruction
  - Day 17: Tests → read as documentation
  - Day 18: Git history → identify 3 interesting decisions
  - Day 19: Invariants → list them
  - Day 20: First change → make and describe a Level 1 PR
  - Day 21: Write the reading session template for what you've learned

---

## The One-Sentence Summary

> *"Reading unfamiliar code = find the entry points (trace one request end-to-end) + read the data model (schema reveals purpose) + run the tests (they are the spec) + git blame the confusing parts (history explains decisions) — building a mental model takes days, not weeks, if you follow this order instead of reading linearly — and shipping a small change by day 5 validates your model and makes your competence visible."*

---

## Company-Specific Notes

**Google / Alphabet:**
- Systems are large and well-instrumented; metrics exist for almost everything
- Code search (`cs.opensource.google`) is extremely powerful — use it
- ADRs and design docs (go/[project]) are the canonical "why" source
- Many systems have an "Owners" file — these people are the domain experts to ask

**Meta / Facebook:**
- Phabricator (now GitHub Enterprise) — detailed PR history is often more useful than git log
- Internal wiki has extensive runbooks and design documents
- Systems often have internal visualization tools — find them before reading code

**Amazon:**
- 6-pager design documents live in wikis — find them for any major system
- Operational excellence is deeply embedded; look for "Correction of Errors" (COE) documents
- Deep ownership culture: every service has a clear owner who is the source of truth

---

*Pairs with Chapter 116 (Refactoring Large Systems) for when you need to change unfamiliar code, Chapter 117 (Capacity Planning) for when you inherit a system and need to assess its capacity, and Chapter 109 (On-Call Engineering) for when you inherit on-call responsibility for a system you don't know yet.*

`Chapter 118 | Section 7: Engineering Excellence | Reading Unfamiliar Code`

