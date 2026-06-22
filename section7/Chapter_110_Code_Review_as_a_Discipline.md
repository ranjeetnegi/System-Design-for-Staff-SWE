# Chapter 96: Code Review as a Discipline

> **Core thesis:** Code review is not a gatekeeping step. It is the highest-leverage teaching moment in software engineering. A staff engineer who reviews 10 PRs per week is teaching 10 engineers per week. A staff engineer who just writes LGTM on 10 PRs per week is wasting the most powerful tool they have.

---

## Why This Chapter Exists

Most engineers think they know how to do code review. They open a pull request, read through the diff, leave some comments, click approve. Done. Five minutes, ship it.

That is not code review as a discipline. That is code review as a checkbox.

This chapter is about the version of code review that actually makes systems better over time, that teaches junior engineers how to think, that catches the security bug before it ships to production, and that builds a team culture where everyone trusts the work they inherit.

The gap between a checkbox reviewer and a disciplined reviewer is the gap between an L4 and an L6. This chapter closes that gap.

---

## Table of Contents

- Part 1: What Code Review is Actually For
- Part 2: The Review Hierarchy — Five Levels of Looking at Code
- Part 3: How to Give Feedback That Teaches
- Part 4: Being a Bar Raiser Without Being a Bottleneck
- Part 5: Being Reviewed — How to Write Reviewable Code
- Part 6: The Staff Engineer's Review Lens
- Part 7: Code Review at Google — The Critique System
- Part 8: Setting Team Review Norms
- Part 9: Security-Specific Code Review
- Part 10: Architecture Review vs Code Review
- Part 11: Real Examples and Anti-Patterns
- Common Interview Mistakes
- Exercises
- Homework
- Key Takeaways

---

## Part 1: What Code Review is Actually For

### The Four Real Goals

When you ask most engineers why we do code review, they say something like "to catch bugs" or "to make sure the code is correct." That is goal one of four. If correctness were the only goal, you could just run a test suite and call it done. Code review is doing more work than that, and if you do not know what that work is, you will do it badly.

**Goal 1: Correctness.**
Does the code do what it claims to do? This is the obvious one. Does it handle the happy path? Does it handle the error path? If the PR says "fix the login timeout bug," does it actually fix the login timeout bug in all the ways that bug can manifest? This is what most engineers think is the whole job.

**Goal 2: Maintainability.**
Will the next engineer — who might be you in six months, exhausted at 2 AM on an incident — be able to understand this code? Can they modify it without breaking something three directories away? Maintainability includes naming, structure, comments where the logic is non-obvious, and avoiding clever tricks that require the original author's brain to decode.

**Goal 3: Knowledge Transfer.**
The reviewer learns what the author knows. The author learns what the reviewer knows. Both learn what the codebase contains. This is not a side effect of code review — it is one of the primary reasons it exists. When a junior engineer submits a PR, a senior reviewer who writes a thoughtful comment about *why* a certain pattern exists is delivering more value than any documentation ever could. When a new engineer submits their first PR to a legacy codebase, they are also teaching the senior engineer what the codebase looks like to fresh eyes.

**Goal 4: Raising the Bar.**
Every approved PR sets a precedent. If you approve a PR that has inconsistent error handling, you have now told the entire team that inconsistent error handling is acceptable. If you block a PR to ask for proper logging, you have taught the entire team that logging is required. Code review is how team standards propagate. It is the mechanism by which one staff engineer's judgment becomes thirty engineers' habits.

### What Code Review Is NOT For

This is the list that most engineers have never been given explicitly, and it is responsible for most of the dysfunction in code review culture.

**Not for enforcing personal style preferences.** If the author wrote `camelCase` and you prefer `snake_case` and neither is specified in the style guide, do not block the PR. Silence is the correct response. If there is a lint rule, let the lint tool enforce it. If there is not, write one, and do not block individual PRs while waiting for it.

**Not for showing you read it.** The comment "I read through this" adds zero value. Approving without comment when the code is genuinely good is fine. Nitpicking minor things to demonstrate engagement is not.

**Not for winning arguments.** Code review is not a debate stage. If the author did something a way you disagree with, and there is a genuine tradeoff to discuss, discuss it. If your only objection is "I would have done it differently," that is not a blocking concern.

**Not for catching everything a test suite should catch.** If a function has a simple off-by-one error that a unit test would have caught, the review comment should be "this needs a test" not a detailed walkthrough of the error. Let the tests be the detailed first layer of correctness verification. Code review is for catching the things tests cannot easily catch: design problems, missing edge cases in logic that is hard to test, security issues, and architectural drift.

**Not a substitute for design review.** If someone submits a 2,000-line PR that fundamentally misunderstood the problem, blocking it in code review is too late. That conversation should have happened at the design doc stage. We will come back to this in Part 10.

### Why L5 and L6 Engineers Review Completely Differently

An L4 engineer reviewing a PR reads it like an English essay — line by line, front to back, commenting on things that look wrong as they appear. This produces a lot of comments about variable names and a failure to notice that the entire approach is wrong.

An L5 engineer reads the PR description first, understands the intended change, then reads the code to verify the code matches the intent. They catch logical errors and miss architectural problems.

An L6 engineer reads the PR description and immediately asks: is this the right change? Then they look at which files changed. The file list tells them the blast radius. Then they read the core logic. They have a mental model of the system that lets them see, from a 20-line function, what cascading effects it might have in a service three layers away. They are not reading a document — they are simulating a system.

### The "Teaches vs Corrects" Distinction

Here is the single most important idea in this chapter.

A comment that corrects says: "This is wrong. Do it this way."

A comment that teaches says: "This will work for the happy path, but here is what happens when the upstream service returns a 504. Have you considered using a circuit breaker here, or explicitly failing with a meaningful error? Here is where we do that in the payments service if you want to see the pattern."

The correcting comment produces a PR that works. The teaching comment produces an engineer who writes better code next week, and the week after that, and trains the engineers after them.

This distinction determines whether code review is a cost center or a force multiplier.

---

### Brainstorming Q&A — Part 1

**Q1: If knowledge transfer is a goal of code review, should code review replace documentation?**

No, but they serve overlapping purposes and understanding which is which helps you do both better. Code review transfers the implicit knowledge — the "why" behind a specific decision, the context for why this approach was chosen over three alternatives, the operational reality that shapes the code. Documentation captures the explicit and stable knowledge — APIs, architecture, deployment procedures, SLAs. The problem with depending on code review for knowledge transfer is that it is synchronous and ephemeral. If someone joins the team two years after a code review happened, they cannot benefit from a discussion that happened in a PR comment thread unless someone went and wrote it down. The best teams use code review to surface knowledge and then have a habit of promoting that knowledge into documentation, ADRs, or runbooks. The reviewer who says "I explained this in the PR comment" has done half the job. The reviewer who says "I added a comment to the function explaining why this approach" has completed it.

**Q2: How do you handle the pressure to approve PRs quickly when your team is shipping fast?**

Speed and quality are genuinely in tension in code review, but they are less opposed than most teams think. The main drag on review quality is not time spent per review — it is review cycle time. A PR that takes 48 hours to get its first response, receives comments, and then waits another 24 hours for the second round is both slow and getting worse review quality because the reviewer has lost context between rounds. The solution is not to review faster, it is to review once, completely. If you sit down and give a PR your full focused attention for 20 minutes and write all your comments in one pass, the author can address everything at once. That is faster total cycle time and better coverage than five five-minute reviews spread over two days. The other lever is PR size. The chapter covers this in Part 5, but small PRs (under 400 lines) reviewed once, thoroughly, is almost always faster than large PRs reviewed partially.

**Q3: What do you do when the author is more senior than you?**

Review their code exactly the same way. Seniority does not exempt anyone from the review process, and a junior engineer who catches a bug in a staff engineer's code has done something genuinely valuable. The difference is in how you frame uncertain feedback. If you are reviewing a senior engineer's code and something seems wrong but you are not sure, say that explicitly: "I might be missing something here, but I don't see where X is being cleaned up. Is that handled somewhere else, or is this intentional?" That is not hedging — that is honest calibration about your uncertainty. Senior engineers who create cultures where juniors cannot question their code are creating systems that fail in predictable ways. If a senior engineer responds poorly to genuine questions, that is a culture problem worth escalating, not a sign that you should stop asking questions.

---

## Part 2: The Review Hierarchy — Five Levels of Looking at Code

### The Core Problem with Undisciplined Review

When engineers do not have a framework for code review, they pay attention to whatever catches their eye. Variable names catch the eye. Comments catch the eye. Inconsistent spacing catches the eye. What does not catch the eye is a missing bounds check, an SQL query that will full-table-scan at scale, a missing authentication check that lets any user read any other user's data.

The review hierarchy is the fix for this. It forces you to check things in the order that matters — highest severity first.

```
THE REVIEW HIERARCHY
====================

LEVEL 5: Security / Performance / Observability
         [Highest severity if wrong — ship it broken, pay forever]
              |
              |  "Are there security holes? Perf cliffs? Missing metrics?"
              |
LEVEL 4: Design / Problem Fit
         [Is this solving the right problem the right way?]
              |
              |  "Should this feature exist? Is this the right abstraction?"
              |
LEVEL 3: Maintainability
         [Will the next engineer survive this?]
              |
              |  "Can you understand this without the author? Is naming right?"
              |
LEVEL 2: Robustness / Edge Cases
         [Does it break in ways that are not immediately obvious?]
              |
              |  "What happens at zero? At max? When the network fails?"
              |
LEVEL 1: Correctness
         [Does it do what it claims?]
              |
              |  "Does this code implement what the PR description says?"
              |
         START HERE — Read the PR description first.
```

### Level 1: Correctness

You read the PR description. It says: "Add retry logic to the payment processor so that transient failures do not cause order failures."

Then you read the code. You see retry logic. You check: does it retry on the right errors? (Is it retrying on a 400 Bad Request, which will never succeed, or only on 5xx errors, which might?) Does it have a maximum retry count? Does it wait between retries?

Level 1 is asking: does the code do what it says it does? This catches the most obvious bugs. If a PR says "fix the null pointer exception on empty cart" and the code still allows null when the cart has a zero-price item, that is a Level 1 failure.

### Level 2: Robustness and Edge Cases

The code does what it claims. Does it also handle everything it claims not to handle but must?

For the retry example: What happens if all retries fail? Does it throw a readable exception or does it silently swallow the error? What is the backoff strategy? Is there exponential backoff with jitter, or does it hammer the already-overloaded payment service at 100ms intervals? Is there a timeout on the entire retry sequence, or can this block a request for 30 seconds during a sustained outage?

Level 2 is where you bring in your mental inventory of failure modes. Any function that calls an external system needs to handle network failure. Any function that accepts input needs to handle invalid input. Any function that reads from a database needs to handle not found.

### Level 3: Maintainability

The code is correct and robust. Can the next engineer maintain it?

Variables named `x`, `temp`, `data` in functions longer than twenty lines are a maintainability problem. Logic split across four files when it could be in one is a maintainability problem. A function that is 200 lines long when it is doing ten distinct things is a maintainability problem. Comments that say "this is important!" without explaining why are a maintainability problem.

The test you apply at Level 3 is: if the author is hit by a bus tomorrow and I need to debug this at 2 AM six months from now, can I do it?

### Level 4: Design and Problem Fit

This is where senior reviewers separate from everyone else.

At Level 4 you are asking: is this the right solution? Not "is the code correct" but "is this change a good idea." This catches the PR that correctly implements a cache with a 30-second TTL in front of a database that only updates once per day — correct code, wrong design. This catches the PR that adds a new microservice when the problem could have been solved with two functions in an existing service. This catches the PR that implements a complex feature that a different team has already built.

Level 4 also catches the PR that is solving the right problem in the wrong abstraction. "We should have a service for this" vs "this should be a library" vs "this should just be a database query" are Level 4 questions.

### Level 5: Security, Performance, and Observability

These are placed at Level 5 not because they are least important but because they are often the most expensive to miss and require deliberate attention to catch.

**Security:** Is user input validated before use? Is the user authenticated before accessing this resource? Is this query parameterized or does it concatenate user input into SQL? Are secrets in the code? Is this logging information that should not be logged (passwords, SSNs, full credit card numbers)?

**Performance:** Is this making N database calls in an N-item loop? Is there a sort that is O(n log n) being called inside a loop, making it O(n² log n)? Is there a missing index for a query that will be called millions of times per day?

**Observability:** When this fails in production, will an on-call engineer have the information they need to debug it? Are there logs at the right level? Are there metrics that will page when something goes wrong? Is there a way to see what this is doing in real time without attaching a debugger?

### The Intern-to-Staff Progression: Same PR, Different Eyes

Let us use a concrete PR as an example. The PR description says: "Add endpoint to get user account balance."

Here is the code (simplified):

```python
@app.route('/balance')
def get_balance():
    user_id = request.args.get('user_id')
    result = db.execute(f"SELECT balance FROM accounts WHERE user_id = {user_id}")
    return jsonify(result)
```

**Intern review:**
"Looks good to me, I tested it locally and it worked."

**Junior (L3) review:**
"What happens if user_id is None? We should add a check for that."

**Mid-level (L4) review:**
"Missing null check on user_id. Also, the response should probably include the currency, not just the number. And should we have a test for this?"

**Senior (L5) review:**
"Several issues: (1) user_id is not validated — if it's None the query will fail messily. (2) This is a SQL injection vulnerability — user_id is being interpolated directly into the SQL string. It should be parameterized. (3) There is no authentication — any user can query any other user's balance by passing a different user_id. (4) The response format is inconsistent with our other balance endpoints which return `{balance: X, currency: Y}`. (5) No test coverage."

**Staff (L6) review:**
Everything the L5 caught, plus: "More importantly — should this endpoint exist at all? Our account service already exposes a `/account/summary` endpoint that includes balance. Are we creating a duplicate? If this is a different use case, we need to understand who is calling this and why, and whether it should be in this service or the account service. Before we address the implementation issues, let's align on whether this is the right design."

The staff engineer caught everything the L5 caught and then stepped back to ask the question none of the others asked: should we build this at all?

---

### Brainstorming Q&A — Part 2

**Q1: Do you always go through all five levels for every PR?**

Not always in equal depth, but yes, you always check all five. For a small bug fix that changes two lines of a well-tested utility function, your Level 4 and Level 5 checks are fast: "does this change affect anything security-sensitive? No. Does it affect performance? No. Is the design still right? Yes." The check still happens, it just takes five seconds instead of five minutes. The danger of skipping levels based on PR size is that you start believing small PRs cannot have security implications, which is false. A one-line change to how a password is hashed can be the most security-critical change in a year of work.

**Q2: What is the difference between a Level 2 issue and a Level 1 issue?**

A Level 1 issue means the code does not do what the PR description says it does. If the PR says "handle the case where the cart is empty" and the code crashes when the cart is empty, that is Level 1. A Level 2 issue means the code does what the PR description says but fails in cases the PR description did not mention — cases that must be handled anyway. If the PR says "add an endpoint to get user balance" and the endpoint works for valid users but panics for user IDs above 2 billion because they overflow an int32, that is a Level 2 issue. The code is "correct" by the PR's own definition but it is not robust. This distinction matters when you are triaging which issues to block on. Level 1 issues always block. Level 2 issues almost always block. Levels 3-5 require judgment about severity.

**Q3: How do you handle a PR where you catch a Level 4 design issue after also writing Level 1-3 comments?**

This happens constantly and it is one of the hardest social dynamics in code review. You have already written six detailed comments about implementation, and then you realize the entire approach is wrong. The best practice is: write the Level 4 concern first, prominently, as the top comment in the PR. Say something like: "Before I get into implementation details, I want to flag a design concern that might change the approach significantly. [Explanation.] I've also left notes on the implementation as-is, but let's discuss the design question first to avoid work that might get thrown away." This respects the author's time by front-loading the most important concern, prevents confusion about whether they should fix the implementation comments when the design might change, and signals that you are thinking at multiple levels simultaneously.

---

## Part 3: How to Give Feedback That Teaches

### The Three Types of Comments

The most important structural improvement you can make to your code review practice is to label every comment you leave. There are three labels:

**[BLOCKING]** — This must be fixed before I can approve this PR. Either there is a bug, a security hole, a significant maintainability problem, or a design issue that makes this change unsafe to ship.

**[SUGGESTION]** — I think this would be better a different way, and I recommend making the change, but I will approve either way. It is my opinion with a reasoning behind it, and the author gets to make the final call.

**[NIT]** — This is a minor style or preference issue. The author can take it or leave it. Do not spend more than thirty seconds on it.

This labeling system does three things. First, it tells the author exactly how much they need to do before the PR can merge. Second, it prevents the author from guessing which comments are blocking, which causes either defensive over-arguing or unnecessary work. Third, it forces the reviewer to actually decide whether each comment is important enough to block on — which frequently reveals that many comments that feel like blocking concerns are actually suggestions.

### Question vs Declaration

This is the tone shift that turns code review from confrontation into collaboration.

**Declaration style (bad):**
"This is wrong. You need to handle the null case."

**Question style (good):**
"What happens here if `user` is null? I think we need to handle that case — am I missing something?"

The declaration style creates an adversarial dynamic. The author now has to either agree (which feels like admitting a mistake publicly) or argue (which creates conflict). The question style creates a collaborative dynamic. The author can confirm you caught a bug ("you're right, I missed that"), clarify that it is handled elsewhere ("the middleware guarantees user is never null at this point, I'll add a comment to explain that"), or explain that your assumption is wrong ("the type system prevents null here because this is Kotlin"). All three outcomes are better than a declaration, which only allows "I agree" or "I disagree."

The question style also makes the reviewer more honest. When you write "this is wrong," you have staked your identity on being right. When you write "am I missing something?", you have left room for you to be wrong, which you sometimes are.

### Context for Why, Not Just What

Here is the most common weak review comment pattern:

```
WEAK: "Use a Set here instead of a List."
```

The author sees this comment, changes List to Set, and has no idea why. Two months later, the same author writes code that uses a List in an identical situation and makes the same mistake again.

Here is the same comment done right:

```
STRONG: "[SUGGESTION] Consider using a Set here instead of a List.
We're using this collection to check membership (the `contains` call
on line 47), and Set.contains() is O(1) while List.contains() is O(n).
At the scale this code runs (this function is called for every API
request), the difference will be noticeable. The existing `UserIdSet`
type in our commons library would work well here."
```

The author now knows: what to change, why to change it, what the performance implication is, and where to find the right tool. This is the last time they make this mistake. Teaching.

### Side-by-Side Transformation Examples

Let us walk through transforming bad review comments into good ones.

---

**Example 1: Missing error handling**

*Original code:*
```python
def get_user(user_id):
    response = requests.get(f"https://api.example.com/users/{user_id}")
    user = response.json()
    return user
```

*Bad review comment:*
```
This is broken. Handle errors.
```

*Good review comment:*
```
[BLOCKING] This function will raise an exception if:
1. The network is unavailable (requests.get raises ConnectionError)
2. The API returns a non-200 status code (response.json() may fail or
   the data may be unexpected)
3. The response is valid JSON but the user doesn't exist (no handling
   for 404)

I'd suggest wrapping this in try/except and returning a typed result
(either the user or None/an error type). See how `get_payment_method()`
in payments/client.py handles this pattern — it's a good reference.
```

---

**Example 2: Performance issue**

*Original code:*
```python
def get_user_names(user_ids):
    names = []
    for user_id in user_ids:
        user = db.query("SELECT name FROM users WHERE id = ?", user_id)
        names.append(user.name)
    return names
```

*Bad review comment:*
```
N+1 query problem
```

*Good review comment:*
```
[BLOCKING] This is an N+1 query pattern — it makes one database call per
user_id, so if this is called with 100 user IDs, it makes 100 database
calls. At our current load (roughly 10k RPM on this endpoint), this will
produce 1M database calls per minute and will likely cause database
saturation.

The fix is to batch the query:
  SELECT name FROM users WHERE id IN (?, ?, ...)

Our db library supports this with db.query_many(). Here's how we use it
in the notifications service for a similar pattern: [link to example]
```

---

**Example 3: Naming**

*Original code:*
```python
def proc(d, f, t):
    ...
```

*Bad review comment:*
```
Name these properly.
```

*Good review comment:*
```
[NIT] The parameter names `d`, `f`, `t` are hard to parse without running
the code. Could these be `document`, `format_type`, `target_path` or
similar? This function will be called by other engineers, and self-
documenting parameter names reduce the cognitive load significantly,
especially since this file doesn't have type annotations yet.
```

---

**Example 4: Security issue**

*Original code:*
```python
@app.route('/admin/users')
def list_all_users():
    users = db.query("SELECT * FROM users")
    return jsonify(users)
```

*Bad review comment:*
```
Missing auth check
```

*Good review comment:*
```
[BLOCKING] This endpoint has no authentication or authorization check —
any user (including unauthenticated requests) can call it and receive the
full users table. This exposes emails, hashed passwords, and account
status for all users.

This endpoint needs two things:
1. Authentication: verify the request has a valid session token
   (use the @require_login decorator, same as /admin/reports)
2. Authorization: verify the authenticated user has the 'admin' role
   (use @require_role('admin') from auth/decorators.py)

This should be treated as a security vulnerability — please flag this
to the security team if any version of this code has been deployed.
```

The difference in every case is the same: the good comment explains what is wrong, why it matters, what the impact is, and gives the author a concrete path forward. It is more words, but the author learns something.

### When You Disagree With the Author's Choice

Sometimes you review code where you would have made a different technical decision, but the author's decision is defensible. This is not the same as the code being wrong.

The pattern to use: "I would have approached this with X because Y. I can see why you chose Z — the tradeoff is [acknowledge the valid reason]. I'm going to mark this as a suggestion rather than blocking, but let's discuss if you have context I'm missing."

This respects the author's autonomy while surfacing the tradeoff. You are not hiding your opinion, but you are not weaponizing your seniority either.

The rule of thumb: if two reasonable engineers could disagree about the right approach, it is a suggestion. If the code has a clear bug, a security hole, or a clear correctness problem, it is blocking.

---

### Brainstorming Q&A — Part 3

**Q1: How many comments is too many comments in a code review?**

There is no magic number, but there is a pattern that signals trouble: if you are leaving more than fifteen to twenty comments on a 300-line PR, either the PR needs to be sent back for a full rewrite (in which case, say that, not fifteen individual comments) or you are nitpicking things that do not matter. Fifteen small nitpick comments produce more friction than one clear "this needs significant rework" comment. The guideline to internalize is: if the total volume of your comments would take the author more than two hours to address, consider whether the right path is to request a design conversation or a full rewrite instead of incremental comments. The one exception is a PR from a junior engineer that you are explicitly mentoring — in that case, detailed comments are the point, and the author expects them.

**Q2: Should you leave positive comments in code reviews?**

Yes, and more engineers should. When you see something done really well — a clever algorithm, an especially clear test, a function that is exactly the right level of abstraction — saying so takes five seconds and builds the kind of culture where engineers feel their good work is noticed. Positive comments also serve a practical purpose: they help the author understand what to repeat. If every comment is a correction, the author does not know what they did right, which means they cannot do it intentionally. Positive comments also defuse the adversarial dynamic that heavy criticism can create. A review with twelve corrections and three genuine "this is exactly the right approach" comments feels much more collaborative than a review with twelve corrections and nothing else.

**Q3: What do you do when you cannot figure out whether code is correct because you do not understand the business logic?**

Ask. Do not approve code you do not understand, and do not leave a comment that pretends you understand when you do not. "I'm not familiar enough with the billing system's proration logic to verify this calculation is correct — can you add a comment explaining the formula and why this is the right approach? It would also help to have a test that covers the edge case where a subscription is upgraded mid-cycle." That comment is honest, teaches the author to document their business logic, and asks for a test that will catch future regressions. Pretending to understand and approving a billing calculation you cannot verify is how you get financial bugs that are very hard to detect and very expensive to fix.

---

## Part 4: Being a Bar Raiser Without Being a Bottleneck

### The Two Failure Modes of Code Reviewers

Failure Mode 1: The rubber stamp. Glances at the PR, clicks approve, moves on. Code quality degrades. Security holes slip through. Junior engineers receive no mentorship. The team's bar slowly drops to the lowest common denominator.

Failure Mode 2: The bottleneck. Reviews everything meticulously but slowly. Engineers wait 48 hours for first feedback. Leaves 30 comments in five separate rounds. Blocks PRs on personal style preferences. Engineers start routing around this person. Eventually the team's velocity drops to nothing or engineers begin merging without review.

The goal is neither. The goal is high signal, fast response, high quality.

### The 24-Hour Rule

Your first response to any PR that lands in your queue should happen within 24 hours. This does not mean you must have a full review done in 24 hours. It means you must say something within 24 hours.

That something could be: "I'll get to this tomorrow morning." or "I've done a first pass — leaving detailed comments. Should be done by end of day." or "This is a complex change. I'm going to need until Thursday to review it properly."

Why does the acknowledgment matter even without a full review? Because engineers are blocked waiting for review. Every hour a PR sits unacknowledged is an hour the engineer cannot close the loop, cannot start the next thing with confidence, and cannot get feedback that might change the work they are doing on parallel tasks. A 24-hour acknowledgment is a professional contract: I see your work, I am taking it seriously, here is when you can expect a full response.

### Response Time as Respect

This is the cultural message that most review systems fail to teach explicitly: how fast you review someone's work signals how much you value that work.

When a senior engineer submits a PR and it gets reviewed within two hours, they learn that their work matters to the team. When a junior engineer submits a PR and it sits for five days, they learn the opposite.

In many teams, there is an informal seniority hierarchy to review speed — senior engineers' PRs get reviewed first. This is backwards. Senior engineers can redirect their own energy while waiting. Junior engineers are blocked in a way that is more total. A junior engineer waiting for PR review is often literally stuck — they cannot move to the next task because they might need to rewrite based on feedback on this one.

The correct policy: review PRs in order of how blocked the author is, not in order of how senior the author is.

### Batch Your Feedback

This is the rule that most reviewers violate most often, and it produces the most reviewer-author friction.

**Wrong pattern:**
- Monday 9 AM: Reviewer leaves 3 comments.
- Monday 11 AM: Author addresses comments, requests re-review.
- Monday 2 PM: Reviewer leaves 4 more comments they "missed" before.
- Monday 4 PM: Author addresses comments, requests re-review.
- Tuesday 10 AM: Reviewer leaves 2 more comments.
- Tuesday 3 PM: Author finishes, PR merges.

Total calendar time: 2 days. Total round trips: 3. Author experience: exhausting.

**Right pattern:**
- Monday 9 AM: Reviewer does full review, leaves all comments.
- Monday 11 AM: Author addresses all comments, requests re-review.
- Monday 2 PM: Reviewer verifies changes, approves.

Total calendar time: 5 hours. Total round trips: 1. Author experience: clear and efficient.

The second pattern requires that the reviewer read the entire PR before leaving any comments. Do not comment-as-you-read. Read once to understand. Then read again to comment. This is harder because it requires holding more things in your head, but it produces a review that the author can address in a single pass.

### When to Block, When to Approve-With-Comment, When to Let It Go

```
DECISION FRAMEWORK FOR REVIEW OUTCOME
======================================

                [Find an issue]
                     |
         +-----------+-----------+
         |                       |
   BLOCKING?               NOT BLOCKING?
   (safety, security,      (preference, style,
    correctness, data       suggestion, nit)
    integrity issue)              |
         |                       |
   [Request Changes]      +-----------+-----------+
                          |                       |
                    IMPORTANT ENOUGH         PERSONAL PREFERENCE
                    TO RECOMMEND?            OR MINOR NIT?
                    (perf improvement,              |
                     better pattern,         [Leave as NIT]
                     maintainability         [Or stay silent]
                     concern)
                          |
                    [Approve + Leave
                     Suggestion Comment]
```

**Block (Request Changes) when:**
- The code has a bug that will cause incorrect behavior
- There is a security vulnerability
- The approach has a fundamental design flaw
- There is missing test coverage for critical paths
- The code violates an explicitly documented team standard

**Approve with suggestion when:**
- You have opinions that would improve the code but the code is safe and correct as written
- There are maintainability improvements that are genuinely worthwhile but not urgent
- There is a better pattern that would help the author grow but this approach works

**Approve silently (or with brief positive note) when:**
- The code is good
- The only comments you have are nitpicks about style that match the existing surrounding code
- The author is more expert in this area than you

**Do not block on:**
- Code style that matches existing patterns in the codebase even if you prefer a different style
- Technology choices that are already established in the codebase
- Approaches you personally would not have taken that are nonetheless defensible
- Anything you label as a NIT

### How to Approve With Learning

One of the most underused tools in code review is the "approve and teach" comment. This is for when you are approving a PR but want to plant a seed for the author's growth without blocking.

Example:
```
LGTM. Shipping this.

One thing for future reference: the pattern we used for authentication
here (checking the session token in every handler) is something the team
is in the process of moving into middleware so we do not have to
remember it in every endpoint. Worth looking at the upcoming RFC for
auth middleware if you haven't seen it — you're going to love not having
to write this check manually.
```

The author ships their work, gets credit for it, and learns something about where the system is going. This is the version of LGTM that multiplies your impact.

---

### Brainstorming Q&A — Part 4

**Q1: What do you do when an author repeatedly argues back on blocking comments?**

First, distinguish between good-faith disagreement and defensiveness. Good-faith disagreement looks like: "I hear your concern about X. My understanding is that Y makes it safe because Z. Can you help me understand what I'm missing?" That is excellent engagement and you should work through the disagreement together. Defensiveness looks like: "this works fine in my testing" or "other code in the codebase does this" or simply not addressing the comment and requesting re-review. For good-faith disagreement: engage with the technical substance. Sometimes you are wrong and the author's argument is correct — change your position. Sometimes they are wrong — explain more clearly and hold the block. For defensiveness on blocking issues: escalate calmly. "I want to make sure we're aligned on this before merging. Can we get on a quick call to walk through my concern?" If escalation fails, involve a tech lead. A culture where blocking comments can be ignored is a culture without standards.

**Q2: How do you handle a PR that needs major rework — do you leave detailed comments or just say "needs rework"?**

The answer depends on why it needs rework. If the PR is implementing the wrong thing (Level 4 design issue), detailed implementation comments will confuse the author. Leave a clear explanation of the design concern, do not comment on implementation details, and request a design discussion before the author writes more code. If the PR is implementing the right thing but doing it in a fundamentally broken way, leave a high-level comment explaining the core issue and one or two specific examples to illustrate it, but do not enumerate every instance of the problem in a 2,000-line PR. "The core issue is that this is using mutable shared state across requests, which will cause race conditions under concurrent load. Line 47 and 83 are examples. Once we fix the approach, we should review the implementation together." That is more useful than 40 individual comments on 40 places where the shared state is used incorrectly.

**Q3: Is there a maximum number of PRs a single reviewer should be assigned to at once?**

In practice, a reviewer can give thoughtful attention to about three to five non-trivial PRs per day. Beyond that, review quality drops because the reviewer is fatigued and rushing. The failure mode in many teams is one or two "go-to" reviewers who are listed on every PR, creating a review bottleneck and burning out those reviewers. The fix is review rotation — spreading review assignments across the team based on domain expertise and capacity, not based on who is most available or most senior. Some teams use automated review assignment (GitHub's CODEOWNERS, for example) to distribute load. Others use a rotation schedule. The goal is that no single engineer should ever be blocking more than five to seven PRs simultaneously, and team norms should treat review as a first-class commitment, not something you do with leftover time.

---

## Part 5: Being Reviewed — How to Write Reviewable Code

### The Most Important Skill No One Teaches

Engineering education and most workplace culture focuses almost entirely on the reviewer side of code review. The author side is treated as passive — write code, submit it, address comments when they arrive.

This is wrong. The author's behavior before and during review has as much impact on review quality as the reviewer's behavior. A well-structured PR with a clear description gets better review than a 1,500-line PR with the description "misc fixes." The author is not passive — they are setting the conditions for the reviewer's success or failure.

### PR Size: The 200-400 Line Rule

Research and practice consistently show that code review quality drops off sharply above 400 lines of diff. There are two reasons for this.

First, cognitive load. Holding the full context of a 1,500-line change in your head while reviewing line 1,400 is impossible. By line 400, reviewers have forgotten what they saw at line 50. Small PRs allow the reviewer to hold the full context simultaneously.

Second, time investment. A 1,500-line PR requires hours of review time. Most engineers do not have hours of uninterrupted review time available. The PR sits in the queue while reviewers wait for a big block of time. Smaller PRs can be reviewed in 20 minutes, which fits into the natural gaps in an engineer's day.

```
REVIEW QUALITY VS PR SIZE
==========================

Review     |
Quality    |████
           |████████
           |████████████
           |████████████████
           |████████████████████  <-- drops sharply above 400 lines
           |████████████████████████████
           +--+------+--------+--------+----> Lines of diff
              100    200     400      800+

Optimal    [----SWEET SPOT----]
zone:       200-400 lines
```

This does not mean features must be tiny. It means large features must be broken into a sequence of small PRs, each of which can stand on its own. A feature that requires 2,000 lines of change can often be structured as:

1. PR 1: Add the data model (200 lines)
2. PR 2: Add the service layer with tests (400 lines)
3. PR 3: Add the API endpoint (300 lines)
4. PR 4: Add the frontend integration (400 lines)
5. PR 5: Wire up the feature flag and cleanup (150 lines)

Each PR is independently reviewable. Each can be merged safely without waiting for the others. The reviewer can give focused attention to each piece.

### The Anatomy of a Good PR Description

A PR description is not a commit message. A commit message describes what changed. A PR description explains the context that a reviewer needs to review the change well.

```
ANATOMY OF A GOOD PR DESCRIPTION
==================================

## What this does (2-3 sentences)
   Why this change exists. What problem it solves.
   NOT what the code does — the code shows that. WHY we are changing it.

## Background / Context
   What did this look like before? What was the limitation?
   Link to relevant issues, design docs, or prior PRs.

## How to test this
   What should the reviewer do to verify this works?
   Include specific steps: "POST to /api/v2/users with body X,
   expect response Y."

## What to focus the review on
   If there is a specific section you want feedback on, say so.
   "I'm not sure about the error handling in process_payment() —
   would appreciate eyes on that specifically."

## What's NOT in scope
   If there are known issues not addressed here, say so.
   "This PR doesn't address the performance issue on line 120 —
   that's tracked in JIRA-4521."

## Screenshots / logs (if applicable)
   For UI changes: before and after screenshots.
   For performance changes: before and after metrics.
```

A PR description with this structure takes ten minutes to write and saves thirty minutes of review time. The reviewer does not have to chase down context. They know exactly what to look at, why it matters, and what the author is uncertain about.

### How to Respond to Feedback Without Being Defensive

This is the hardest interpersonal skill in engineering and it is almost never discussed.

When you receive a critical code review comment, your first instinct will be to defend your code. This is natural — you wrote it, you care about it, it represents hours of work, and the comment feels like an attack on your judgment.

Resist this instinct. Here is the alternative script:

**When the reviewer is right:**
"Good catch, fixing it. I didn't consider that case."
Simple. Gracious. Moves forward. Do not over-explain why you missed it.

**When you are not sure if the reviewer is right:**
"Interesting point. Let me think through this. My understanding was X — can you help me see where my reasoning breaks down?"
Collaborative. Surfaces your reasoning. Invites a productive exchange.

**When the reviewer is wrong:**
"I think I might not have explained this clearly in the PR description — let me add some context. The reason this works is X, because of Y constraint. Does that address your concern?"
Charitable. Explains rather than contradicts. Offers to update the PR description to make the intent clear.

**When you strongly disagree and neither side is clearly wrong:**
"I see your concern, and I understand the tradeoff you're pointing at. I went with this approach because [specific reasons]. I'm open to either approach, but I'd like us to align on it explicitly rather than defaulting. Can we discuss?"
Escalates the conversation to explicit decision-making rather than leaving it as an unresolved standoff.

The common thread in all four: the author is not defending the code, they are engaging with the concern. The code is not you. The review is about the code.

---

### Brainstorming Q&A — Part 5

**Q1: How do you break a large PR into smaller ones without making each PR impossible to test?**

The key is building in the right order — data layer first, business logic second, API third. Each layer can be tested in isolation even if the full feature is not yet functional. For features that require all layers simultaneously, use feature flags. You can merge the backend code behind a flag that is off in production, merge the frontend code in the same way, and only turn the flag on when all the pieces are in place. This lets you merge small, testable PRs continuously while controlling when the feature is visible to users. Another technique is the "dark launch" or "shadow mode" approach: the new code runs alongside the old code, its results are logged but not returned to users, and you validate correctness before switching over. This is especially useful for replacing existing behavior rather than adding new behavior.

**Q2: What is the right way to handle review comments when you are on a deadline?**

Acknowledge the deadline explicitly in the PR. "This needs to ship by Thursday for the client demo. I've marked the blocking issues — addressing those now. The suggestions I'd like to address after the demo in a follow-up PR." Most reviewers will accept this if the deadline is real and you commit explicitly to the follow-up. What does not work: ignoring suggestions without acknowledgment (the reviewer will re-raise them), or agreeing to address them and then not creating the follow-up ticket. If you say you will create a follow-up, create the ticket before you merge, link it in the PR, and put your name on it. This builds trust. A team that has seen engineers commit to follow-ups and then not deliver them will stop trusting "I'll fix it after the release."

**Q3: When should you request a code review sync (meeting) instead of working through comments asynchronously?**

Request a sync when: the same disagreement has gone back and forth more than twice in comments without resolution; the PR has more than ten blocking comments and a synchronous walkthrough would be faster; the PR involves a novel approach that is hard to explain in text; or the relationship between reviewer and author has become adversarial and a human conversation is needed to reset. Async review works well for clear, factual concerns ("this is missing error handling") and poorly for complex tradeoffs ("is this the right architecture for this problem"). When you feel yourself writing a paragraph-long comment to explain a concern that would take thirty seconds to explain verbally, that is a signal to suggest a sync.

---

## Part 6: The Staff Engineer's Review Lens

### Why Staff Review Is Fundamentally Different

Staff engineers are not better-than-senior engineers at reading individual functions. They are better at reading systems. The difference is not intelligence — it is accumulated mental models. A staff engineer has seen enough code in enough contexts to have an intuitive sense of what changes are likely to cause problems downstream.

This changes how they read a PR. They are not reading a document sequentially. They are loading a set of changed files into their mental model of the system and simulating what happens.

### Reading the File List First

A staff engineer's first action on opening a PR is not reading the code. It is reading the file list.

The file list tells you:
- What layers of the system are touched (database? service? API? UI?)
- What is the blast radius (how many places are affected)
- Is this change self-contained or does it cross multiple service boundaries
- Are the files you would expect to see changed present (if a payment flow is changed, is there a corresponding change to the audit log?)
- Are there files you would not expect to see changed (why is the authentication module changed by a PR that claims to fix a display bug?)

The file list is like looking at an X-ray before an MRI. It gives you the structure before you see the details.

### Reviewing Across Multiple PRs as a Sequence

Staff engineers often review large features that are delivered as a sequence of PRs. The level 4 and 5 review happens at the sequence level, not the individual PR level.

Questions to ask across a PR sequence:
- Is the data migration before or after the code that depends on the new schema?
- Is the feature flag removing PR merged before the code that depends on the flag being gone?
- Is there a PR that changes behavior without a corresponding PR that updates the runbook or the monitoring dashboard?
- Is there a PR that introduces new failure modes without a PR that adds alerting for those failure modes?

A staff engineer who approves all five PRs in a sequence without checking that they form a coherent whole has missed the most important review they could do.

### Catching Design Flaws That Look Like Implementation Choices

This is the highest-skill move in code review. It requires recognizing when an implementation choice is actually encoding a design assumption.

Example: A PR adds a new table to the database with a `user_id` column. The PR description says it's for caching user preferences. A junior reviewer checks that the column is indexed, the queries are parameterized, and the service has tests. Approved.

A staff reviewer looks at the table and asks: why is this a table and not a key-value store? User preferences are accessed by user_id, rarely updated, and read on every page load. A relational database table is a poor fit for this read pattern. The fact that the author chose a table is not an implementation detail — it is a design decision that will cost significantly more infrastructure to operate than a Redis-based alternative, and it will be very hard to migrate once users' data is in it.

That is the Level 4 catch. It looks like "why is this a table" but it is actually "this design decision will be with us for five years."

### The System-Level Correctness Check

Code can be locally correct and globally incorrect.

A function that returns a 200 OK and an empty list when there are no results is locally correct. If the calling service treats an empty list as "no error, continue" but the intended behavior is "stop and show an error to the user," the system is globally incorrect.

A staff engineer reviews the boundary between code, not just the code itself. They look at what the calling context will do with the output of this code, not just whether the code produces the right output.

This requires understanding the system beyond the PR. It requires having read the code that calls this code, even if that code is not in the PR. This is why staff engineers are expensive and valuable — they carry the system context that allows them to catch integration errors that are invisible if you only look at the code in front of you.

---

### Brainstorming Q&A — Part 6

**Q1: How do you build the system-level mental model that lets you do this kind of review?**

You build it deliberately, over time, through three practices. First: read code you are not assigned to review. When you have spare time, read recent PRs in services adjacent to yours. You are not looking for problems to fix, you are building a map. Second: do incident reviews and post-mortems, not just for incidents you were on-call for. Incidents reveal the coupling and failure modes that do not appear in the design documents. Third: draw architecture diagrams regularly, not to publish them but to test your own understanding. When you cannot draw how Service A communicates with Service B, you do not actually know how they communicate. The process of drawing reveals the gaps in your model. Most staff engineers did not arrive at their system-level thinking through any single insight — they built it through five to seven years of deliberate attention to the system as a whole.

**Q2: When should a staff engineer step back and let a senior engineer own the review?**

When the senior engineer is the domain expert. A staff engineer who is expert in infrastructure reviewing a PR in the recommendation algorithm service should be humble about Level 4 and 5 concerns in the algorithm itself — the senior ML engineer who owns that service knows things the infrastructure expert does not. The staff engineer's value in this review is system-level concerns (how does this service communicate with others? what happens to the data pipeline if this changes?) not algorithm-level concerns. Knowing the limit of your own expertise and deferring on things outside it is a staff-level behavior, not a weakness. The worst outcome is a staff engineer whose seniority causes junior engineers to defer to wrong opinions in areas the staff engineer does not actually understand.

**Q3: How do you review code when you are not familiar with the language or framework?**

Focus on what transfers across languages and frameworks. Correctness, security patterns, and design are largely language-agnostic. An SQL injection vulnerability looks the same in Python, Java, and Go — string interpolation into a query. N+1 queries look the same in any ORM. Missing error handling is obvious regardless of whether it is exceptions or error codes. You can catch 60-70% of the important issues in unfamiliar code. For the remaining 30% that requires deep language knowledge — idiomatic patterns, memory management, language-specific concurrency gotchas — flag it explicitly: "I'm not familiar enough with Go's channel semantics to verify the concurrency model here is correct. I'd recommend getting a second review from someone with deep Go experience." Partial coverage done honestly is better than full coverage done with false confidence.

---

## Part 7: Code Review at Google — The Critique System

### How Google Does Code Review

Google's internal code review tool is called Critique (and its older predecessor, Mondrian). The way code review is structured at Google is worth understanding because it reflects deliberate choices about how to make code review scale across tens of thousands of engineers.

**The "owner" concept.** Every directory in Google's monorepo has an `OWNERS` file. An OWNERS file specifies which engineers have the authority to approve changes in that directory. A PR can have many reviewers, but it can only be submitted if an owner of each changed directory has approved it. This creates explicit responsibility. The owner of a directory is accountable for what gets merged into it.

**Readability reviewers.** Google has a program called "readability." An engineer earns "readability" certification in a language by demonstrating that they write idiomatic, high-quality code in that language through a separate review process. Any PR that introduces new code in a language must be approved by someone with readability certification in that language. This creates a distributed quality enforcement mechanism — you do not need a single gatekeeper to enforce code style because every certified engineer is a gatekeeper.

**When a LGTM is binding.** At Google, different reviewers' approvals carry different weight. If a reviewer who owns the changed directory approves, that is a binding approval for the directory. If a readability reviewer approves, that satisfies the readability requirement. A PR that has all required approvals — one owner per changed directory, one readability reviewer per new language — can be submitted. A PR with enthusiastic LGTMs from ten non-owners in non-relevant languages cannot.

**The culture of the comment.** Google's code review culture heavily favors leaving comments over staying silent. Engineers are expected to leave at least one comment acknowledging they reviewed something. A silent approval is considered weaker than an explicit "I've reviewed this carefully, looks good" approval. This creates a paper trail of who saw what and when, which matters both for accountability and for post-incident learning.

### What You Can Learn From Google's System

Even if you are not at Google, the principles transfer.

**OWNERS files.** Any team can implement the concept of explicit ownership. Who has the authority to approve changes to the authentication module? The payments service? The core data models? Making ownership explicit forces the question of who understands the system well enough to approve changes to it.

**Readability as a concept.** What would "readability" mean for your team? Who has deep expertise in your primary language? In your primary framework? Creating informal versions of this expertise recognition helps route reviews to people who can actually verify correctness.

**Binding approvals.** The distinction between "I reviewed it" and "I am approving it as the owner" is valuable. Every team has people whose opinion on certain code carries more weight. Making that weight explicit helps everyone know when a review is thorough enough to merge.

### Amazon's Review Culture

Amazon's code review culture is shaped by the "two-pizza team" model — small, autonomous teams that own their services end-to-end. This means Amazon teams typically review within their own team rather than across teams. The bar for internal team review is typically high on correctness and security (both of which have real consequences at Amazon's scale) and moderate on style (teams have autonomy over their own style choices as long as they are consistent).

Amazon also uses a practice called "bar raisers" in the hiring process that bleeds into code review culture. A bar raiser is someone outside the team who has veto power on a hire to ensure the overall quality bar rises over time. Some Amazon teams apply this concept to code review — a designated reviewer who is specifically responsible for asking "does this PR raise or lower the overall quality of the codebase?" rather than just "does this PR work."

---

### Brainstorming Q&A — Part 7

**Q1: Why does Google use a monorepo and how does that affect code review?**

Google's monorepo means all of Google's code is in a single repository. This has significant implications for code review. A PR that changes a utility function can be immediately seen to affect every service that uses that function — because they are all in the same repo. This makes cross-team impact visible in a way that separate repos cannot. A change to a shared authentication library in a separate repo can take months to propagate through other teams that have to update their dependency. In the monorepo, the impact is immediate and visible. Code review in the monorepo context therefore places more weight on changes to widely-used shared code, because those changes affect everyone immediately. This also drives the OWNERS model — because changes are immediately propagated, you need explicit gates on who can approve changes to shared code.

**Q2: Should small companies implement OWNERS files and readability reviews?**

At small companies (under fifty engineers), the overhead of formal OWNERS files and readability review processes often exceeds the benefit. The equivalent at a small company is implicit — everyone knows who owns what, who has deep expertise in what language. The transition point where formalizing this makes sense is around fifty to one hundred engineers, when you can no longer hold the full ownership map in your head. At that point, making ownership explicit (even if it is just a simple CODEOWNERS file in GitHub that routes review assignments) pays dividends in review quality and in post-incident accountability. The readability concept is worth formalizing earlier — having a designated "we trust this person to approve Python style" engineer at a twenty-person company costs nothing and provides a clear signal when review quality questions arise.

**Q3: What is the Amazon Leadership Principle connection to code review?**

Amazon's culture of "ownership" (one of the leadership principles) directly shapes how their engineers approach code review. Owners care deeply about their code's quality because they are accountable for it. An engineer who knows they will be on-call for their service and will be paged when it has an incident reviews their code differently than an engineer who knows someone else will handle operations. This is why Amazon's code review culture tends toward high scrutiny of observability, error handling, and operational readiness — engineers who will operate the code they write are motivated to review those dimensions carefully. The lesson for any team: when reviewers will also be operators (on-call for the service they review), review quality on operational dimensions improves dramatically.

---

## Part 8: Setting Team Review Norms

### What Healthy vs Toxic Review Culture Looks Like

Most teams do not have an explicit code review culture. They have an implicit one, shaped by whoever reviews the most PRs and whatever behaviors those reviewers model. The culture forms slowly, invisibly, and becomes very hard to change once it is established.

```
HEALTHY REVIEW CULTURE vs TOXIC REVIEW CULTURE
===============================================

HEALTHY                          TOXIC
-------                          -----
Reviews happen within 24 hrs  | PRs sit for days unacknowledged
Comments explain the "why"    | Comments say "wrong" with no context
Labels are used (BLOCKING/    | Every comment feels like a block
 SUGGESTION/NIT)              |
Positive feedback is given    | Only problems are mentioned
PRs are small and focused     | 2000-line PRs are common
Disagreements are discussed   | Disagreements are silent or adversarial
Juniors feel safe asking      | Juniors just change what they're told
 follow-up questions          |
Review is seen as teaching    | Review is seen as gatekeeping
```

Healthy culture produces engineers who improve over time and feel safe taking technical risks. Toxic culture produces engineers who write defensive code, avoid controversial changes, and eventually leave.

### How to Shift a Team's Review Culture

Shifting an established review culture is a 3-6 month project, not a 3-6 day project. It requires:

**Step 1: Name the current culture explicitly.** Have a team retro specifically about code review. Ask: what does it feel like to submit a PR? What does it feel like to review? What do you wish were different? Most teams have never had this conversation explicitly.

**Step 2: Define norms in writing.** Document the team's review standards: expected response time, the three comment labels (blocking/suggestion/nit), PR size limits, PR description expectations. A written norm is much harder to inadvertently violate than an unstated expectation.

**Step 3: Model the behavior yourself.** If you are senior enough that other engineers watch how you behave, your behavior is the culture. Start labeling your comments. Start leaving positive comments. Start responding within 24 hours. This changes the team's sense of what is normal faster than any policy document.

**Step 4: Name culture violations when they happen, gently.** When someone leaves a blocking comment on a nit issue, say: "I think this is a suggestion or nit rather than blocking — would you change the label? It helps authors prioritize." This is less comfortable than staying silent but it is the only thing that changes behavior.

**Step 5: Celebrate culture wins.** When a review is done exceptionally well, say so. "This review was exactly the right level of detail and it's clear you put real thought into the teaching. This is what we want code review to look like."

### The Senior Engineer's Responsibility for Culture

A single senior or staff engineer can set the review culture for a team of twenty. They have disproportionate influence because their behavior is watched and modeled. This is the leverage point.

If the most senior reviewer on the team leaves harsh, unlabeled, detailed comments on every PR, within six months, junior engineers who want to seem rigorous will do the same. If the most senior reviewer leaves thoughtful, labeled, teaching-oriented comments and approves quickly, those behaviors will propagate.

The question for every senior engineer is: do you know what culture your review behavior is creating?

---

### Brainstorming Q&A — Part 8

**Q1: How do you handle a senior engineer who is a bottleneck but who is also producing genuinely high-quality reviews?**

This is one of the most common and most delicate problems in engineering management. The reviews are good, but they are slow, or they have too high a bar, and the team's velocity is suffering. The approach has to be two-pronged. First, acknowledge the value genuinely — their reviews are good, and you do not want to lose that quality. Second, name the constraint specifically, not vaguely. "The team is averaging 4 days for first review response. That is blocking engineers from moving forward on parallel work. Can we work on getting response times to 24 hours, even if the first response is an acknowledgment rather than a full review?" Third, work on distributing the load. If the bottleneck is because everyone wants this engineer's review, create pathways for other engineers to develop their review credibility so the load is shared. The wrong approach is telling the senior engineer to do faster but lower quality reviews — that will produce exactly that.

**Q2: What should you do if your manager does not care about code review quality?**

Start at the team level without waiting for manager buy-in. You can improve the review culture of the engineers you interact with directly regardless of whether your manager is invested. Write good reviews consistently. Label your comments. Respond within 24 hours. When other engineers see a better pattern, they often adopt it. If you want formal support, frame code review quality as a business issue with your manager: "Our review cycle time is averaging 4 days, which means features take 30% longer to ship than if we had 24-hour reviews. I'd like to propose some team norms that could address this." Most managers care about velocity even if they do not care about code review quality as an abstract principle. Find the intersection.

**Q3: How do you set review norms for a team across multiple time zones?**

Time zone distribution makes the 24-hour rule both more important and harder to achieve. If your reviewers are in Singapore and your authors are in London, a 9 AM PR submission will not get a response until their 9 AM, which is your next morning. The norms need to account for this explicitly. Options: async-first with a 24-hour window measured in business hours (not wall clock time), review rotation that assigns reviewers based on time zone overlap (reviewers in the same or adjacent time zone get first dibs), and documented "review windows" when each engineer commits to doing their review pass. The worst outcome is unclear expectations where engineers in different time zones have different assumptions about response time and are mutually frustrated. Write the norm down explicitly: "We target a first response within one business day, measured from when the PR is submitted during your timezone's business hours."

---

## Part 9: Security-Specific Code Review

### Why Security Deserves Its Own Part

Security issues are the review failures with the longest tail. A performance problem in a reviewed PR will show up in metrics within days of shipping. A security hole in a reviewed PR might not be discovered for months or years — and when it is discovered, it is often because an attacker found it first.

This means the cost of a security miss in code review is asymmetric: low cost if caught, potentially catastrophic cost if missed. This justifies a specific, deliberate, checklist-style approach to security in code review rather than treating it as one of many concerns.

### The Security Review Checklist

**1. Input Validation — Is all user input validated before use?**

Any data that comes from an external source (HTTP request parameters, form fields, JSON bodies, database records that originated from user input) must be validated before it is used. This is not just about SQL injection — it is about any use of that data.

```python
# BAD: User input used directly in a database query
user_id = request.args.get('user_id')
query = f"SELECT * FROM users WHERE id = {user_id}"

# GOOD: Parameterized query prevents injection
user_id = request.args.get('user_id')
if not user_id or not user_id.isdigit():
    return error_response(400, "Invalid user_id")
user_id = int(user_id)
query = db.execute("SELECT * FROM users WHERE id = ?", [user_id])
```

**2. Authentication Boundaries — Is every endpoint checking authentication?**

Every endpoint that serves sensitive data or performs actions must verify that the caller is who they claim to be. Missing authentication checks are the single most common high-severity security vulnerability in web applications.

Signs of missing authentication:
- Endpoint has no `@require_login` decorator or equivalent
- Endpoint reads a user_id from the request body rather than from the authenticated session
- Endpoint returns data without first verifying the session is valid

**3. Authorization Boundaries — Is every endpoint verifying that the authenticated user can perform this action?**

Authentication says "I know who you are." Authorization says "I know what you are allowed to do." Both are required.

```python
# BAD: Authenticated but not authorized
@require_login
def get_document(document_id):
    return db.get_document(document_id)  # Any logged-in user can get any document

# GOOD: Authenticated AND authorized
@require_login
def get_document(document_id):
    document = db.get_document(document_id)
    if document.owner_id != current_user.id and not current_user.has_role('admin'):
        return error_response(403, "Access denied")
    return document
```

**4. SQL Injection — Is every database query parameterized?**

No exceptions. String interpolation into SQL queries is never acceptable. It does not matter how the input was validated before reaching the query — parameterize it anyway. Defense in depth is the principle.

**5. Secrets in Code — Are there credentials, API keys, or passwords in the code?**

Look for:
- Hardcoded connection strings (`postgres://user:password@host/db`)
- Hardcoded API keys (`api_key = "sk-abc123"`)
- Hardcoded passwords (`admin_password = "changeme"`)
- Environment variable defaults that are actual values (`secret = os.getenv("SECRET", "my-actual-secret")`)

These should be configuration, not code. The fix is environment variables, secrets management systems (AWS Secrets Manager, HashiCorp Vault, Kubernetes secrets), or configuration files that are excluded from version control.

**6. Logging Sensitive Data — Is the code logging information that should not be logged?**

PII, payment data, passwords, session tokens, and health data should never appear in logs. Even if the logs are access-controlled, they persist indefinitely and often get shipped to third-party logging systems with weaker access controls.

```python
# BAD: Password and card number in log
logger.info(f"Processing payment for user {user.email}, card {card.number}, password confirmed: {user.password}")

# GOOD: Log only what is needed for debugging
logger.info(f"Processing payment for user_id={user.id}, card_last_four={card.number[-4:]}")
```

**7. Cross-Site Scripting (XSS) — Is user input being rendered as HTML without escaping?**

Any place where user-supplied text is inserted into HTML output must escape the content. Most modern frameworks handle this automatically if you use their template systems correctly, but raw string concatenation into HTML is still a common pattern.

**8. Cross-Site Request Forgery (CSRF) — Are state-changing endpoints protected?**

Any endpoint that changes state (creates, updates, deletes data) should verify that the request originated from your application and not from a malicious third-party site. This is typically handled by CSRF tokens, but check that the protection is not accidentally disabled for specific endpoints.

**9. Rate Limiting — Are endpoints that could be abused rate limited?**

Login endpoints, password reset endpoints, and any endpoint that allows enumeration of data are common targets. A login endpoint with no rate limiting allows unlimited brute force attempts.

**10. Dependency Versions — Are new dependencies pinned to a specific version?**

An unpinned dependency (`requests` instead of `requests==2.31.0`) can silently upgrade to a version with breaking changes or known vulnerabilities. New dependencies should be pinned, and ideally run through a security audit before being added.

---

### Brainstorming Q&A — Part 9

**Q1: Is it a reviewer's job to catch all security issues or is that the security team's job?**

Both. The security team cannot review every PR in a company with more than a few dozen engineers — the math does not work. The security team's role is to define the security standards, provide tools and training, and review high-risk changes. The reviewer's role is to catch the obvious, common, high-severity issues during regular code review. The ten-item checklist above covers the issues that account for the vast majority of reported security vulnerabilities in web applications — SQL injection, missing auth, secrets in code, XSS. These are not exotic — they are well-understood and you can learn to spot them without being a security specialist. The security team handles the complex, subtle issues: cryptographic implementation, complex access control models, threat modeling for new product areas. The reviewer handles the basics. Both are necessary.

**Q2: How do you handle a situation where you suspect a security issue but are not confident enough to block the PR?**

Block it anyway and ask the question. It is much better to ask "is this SQL query parameterized, or am I misreading this?" and have the author explain why it is safe, than to let a SQL injection vulnerability ship because you were not confident enough to ask. The author who is paged at 2 AM when the database is being exfiltrated will not be grateful that you did not want to seem like you were over-reading. The social norm around security should be: false positives (blocking on something that turns out to be fine) are acceptable. False negatives (approving something that turns out to be a vulnerability) are serious failures. When in doubt, ask.

**Q3: What is the most commonly missed security issue in code review?**

Authorization, not authentication. Most engineers are well-trained to look for authentication checks — is the user logged in? But authorization — can this specific user take this specific action on this specific resource? — is harder to check because it requires understanding the data model and the permission model simultaneously. The pattern to watch for is any endpoint that accepts a resource ID (document_id, user_id, account_id) in the request without verifying that the authenticated user owns or has permission to access that resource. An authenticated user who can access anyone's document by changing the ID in the URL has an Insecure Direct Object Reference (IDOR) vulnerability. This is consistently one of the top-five most reported security vulnerabilities across web applications.

---

## Part 10: The Architecture Review vs Code Review Distinction

### When Code Review Is the Wrong Venue

Code review is the wrong place to discover that the approach is fundamentally wrong. By the time code is written, the engineer has invested days or weeks of effort. Blocking a PR because the approach is wrong at that stage is painful, demoralizing, and often politically difficult. The right time to catch design problems is before the code is written.

The distinction:

**Code review is for:** Implementation correctness, robustness, maintainability, security, and performance of a design that has already been agreed upon.

**Architecture or design review is for:** Whether the design is right in the first place — whether this is the right abstraction, the right service boundary, the right data model, the right technology choice.

When a reviewer looks at a PR and thinks "this entire approach is wrong," the right action is not to leave 40 comments on the implementation. The right action is to block the PR with a single comment that says: "I have a significant concern about the overall approach here that I'd like to discuss before we go further on the implementation. Can we have a design conversation?" This respects the author's time and surfaces the real issue.

### When to Require a Design Doc

Not every change needs a design document. A design document is required when:

- The change touches multiple services or systems
- The change introduces a new data model or significantly changes an existing one
- The change introduces a new dependency or technology
- The change is estimated to take more than one week of implementation
- The change introduces a new pattern that other engineers will be expected to follow

A design doc written before implementation is reviewed before any code is written. This is efficient: changing a diagram and a few paragraphs is much cheaper than throwing away a week of code.

```
WHEN DOES WHAT GET REVIEWED
============================

TYPE OF CHANGE         | RIGHT REVIEW MECHANISM
-----------------------|---------------------------
2-line bug fix         | Code review (brief)
New feature <1 week    | Code review (thorough)
New feature >1 week    | Design doc + Code review
New service            | Architecture review + Design doc + Code review
Schema migration       | Design doc (rollback plan required) + Code review
New external dependency| Design doc + Security review + Code review
Performance change     | Design doc with benchmarks + Code review
Security-sensitive     | Security team review + Code review
```

### How to Escalate from Code Review to Design Review

The right way to escalate a code review concern to a design review:

1. Leave a single summary comment on the PR explaining the design concern
2. Block the PR (request changes)
3. Propose a concrete next step: "Can we set up a 30-minute call to discuss the approach? I want to make sure we're aligned on the right design before investing more time in the implementation."
4. Do not leave 20 implementation-level comments on a PR you are blocking for design reasons — it creates confusion about what needs to be fixed

The signal that a code review has become a design review is when the reviewer's concern cannot be addressed by changing the code — it can only be addressed by changing the approach. At that point, the code review has ended and the design review has begun.

---

### Brainstorming Q&A — Part 10

**Q1: How do you write a design doc that gets useful review?**

A design doc is most useful when it is a decision document, not a specification document. A spec describes what will be built. A design doc explains why the chosen approach is better than the alternatives. The critical section of any design doc is the "alternatives considered" section: what else did you think about, and why did you reject it? This section does the two things a design review needs to accomplish — it shows the author thought broadly about the problem, and it gives reviewers the context to push back on the choice of alternatives if they think an important one was not considered. A design doc without an alternatives section is a design doc that cannot be reviewed meaningfully — reviewers will re-propose the alternatives that were rejected, which wastes everyone's time.

**Q2: Who should review a design doc vs a code review?**

Design docs should be reviewed by people who understand the problem domain and the system context, regardless of whether they will be reviewing the code. This often means tech leads, staff engineers, and sometimes PMs or SREs who will operate the system. Code reviews should be reviewed by people who understand the code, which is often a narrower set. A common mistake is sending a design doc to the same people who will review the code — this misses the value of getting broader input at the design stage, before implementation. The best practice is: design doc review is wide (five to ten reviewers, including people outside the immediate team). Code review is deep (two to three reviewers, focused on the implementation).

**Q3: What happens when engineers skip the design doc and submit a large PR directly?**

This is a governance and culture question as much as a technical one. On teams with strong review culture, a reviewer who receives a large, design-unchallenged PR simply blocks it and requests a design doc: "This change is significant enough that I'd like to see a design doc before we proceed with the implementation. Can you write up the approach and the alternatives you considered?" This is not punitive — it is a quality gate. On teams with weak review culture, the reviewer approves the PR because not approving would cause conflict, and the team ends up with a large, contested design that cannot be changed easily because code is already written. The preventive measure is team norms that specify: changes of X size or complexity require a design doc. The reactive measure is not being afraid to be the reviewer who says "we need a design doc for this, even though code is already written."

---

## Part 11: Real Examples and Anti-Patterns

### Real Example 1: The Security Bug That Should Have Been Caught

*Context:* A team at a mid-size company is building a "share document" feature. A junior engineer writes the endpoint.

*The code (simplified):*
```python
@app.route('/documents/<doc_id>/share', methods=['POST'])
@require_login
def share_document(doc_id):
    recipient_email = request.json['email']
    document = Document.query.get(doc_id)
    share = Share(document_id=doc_id, recipient_email=recipient_email)
    db.session.add(share)
    db.session.commit()
    send_share_email(recipient_email, document)
    return jsonify({'status': 'shared'})
```

*What the intern reviewer said:*
"LGTM, tested it and it works!"

*What the L4 reviewer said:*
"What if doc_id doesn't exist? Should probably add a 404 check."

*What the security-aware L5 reviewer said:*
```
[BLOCKING] Three security issues here:

1. AUTHORIZATION MISSING: There is no check that current_user owns or
   has permission to share document `doc_id`. Any authenticated user can
   share any document by calling POST /documents/12345/share with any
   doc_id. This is an Insecure Direct Object Reference (IDOR) vulnerability.
   
   Fix: Add `if document.owner_id != current_user.id: abort(403)` after
   the query.

2. NO 404 HANDLING: Document.query.get() returns None if doc_id is invalid.
   Calling document.title on None will raise AttributeError and leak a stack
   trace to the caller.
   
   Fix: `document = Document.query.get_or_404(doc_id)`

3. EMAIL ENUMERATION: By returning a success response even when the
   recipient email doesn't exist in the system, an attacker can use this
   endpoint to confirm which email addresses have accounts. Consider returning
   a generic "we sent an email if that address is registered" response.

Happy to pair on the fixes if helpful.
```

*The difference:* The L5 review prevented a vulnerability that would have allowed any authenticated user to share any other user's documents. The intern and L4 reviews would have shipped it.

### Real Example 2: The Performance Cliff

*Context:* A team adds a new feature to show a user's "related contacts." The feature ships and immediately causes database saturation.

*The code:*
```python
def get_related_contacts(user_id):
    user = User.query.get(user_id)
    contacts = []
    for contact_id in user.contact_ids:  # might be 500+ ids
        contact = User.query.get(contact_id)  # N database queries
        if contact.is_active:
            contacts.append(contact)
    return contacts
```

*What was missed in review:*
The reviewer caught that `user.contact_ids` should be a list comprehension. They did not notice the N+1 query pattern.

*What the correct comment would have been:*
```
[BLOCKING] This is an N+1 query pattern. For each of the N contact_ids,
this makes a separate database call. A user with 500 contacts will trigger
500 individual SELECT queries, and this endpoint is called on every page
load.

At our current DAU of 200k, if 10% of users view this section per day,
that's 20k * average_contacts database calls = potentially millions of
additional queries per day.

Fix: Use a single IN query:
  active_contacts = User.query.filter(
    User.id.in_(user.contact_ids),
    User.is_active == True
  ).all()

This is O(1) database calls regardless of contact count.
```

### Anti-Pattern 1: The Nit Overload

A reviewer leaves 25 comments on a PR. 22 of them are about variable names, spacing, and comment style. 3 of them are about actual issues. The author spends two hours addressing the 22 nits and then in their exhaustion addresses the 3 real issues incorrectly.

**Fix:** Label comments. If 22 out of 25 comments are NITs, that signals the review is unfocused. Consider: are these nits worth leaving at all? Is there a lint rule that could handle these automatically?

### Anti-Pattern 2: The Passive-Aggressive Approval

"LGTM, though I'm not sure why we decided to use this approach. Seems like there might be better ways to do this. Shipping anyway."

This is not a useful review. If there is a concern, raise it. If it is blocking, block. If it is a suggestion, say "suggestion: here is what I would have done and why." A vague expression of concern that does not give the author anything to act on is noise.

### Anti-Pattern 3: The Moving Goalposts

Round 1: Reviewer blocks on missing error handling.
Round 2: Author adds error handling. Reviewer now blocks on missing tests.
Round 3: Author adds tests. Reviewer now blocks on style inconsistency.
Round 4: Author fixes style. Reviewer now blocks on a design concern.

This pattern, whether intentional or not, is deeply demoralizing and is the primary cause of engineers losing confidence in the review process. The fix: read the entire PR before leaving any comments. If you cannot fully review it in one session, say so, complete the review in the next session, and do not leave partial feedback in rounds.

### Anti-Pattern 4: The Approval Without Reading

The reviewer opens the PR, sees it is from a senior engineer they trust, clicks approve, moves on. Three weeks later there is an incident caused by a bug in that PR that a fifteen-minute review would have caught.

Seniority is not a substitute for review. The senior engineer who gets an unread approval does not get mentorship on their edge cases, does not get a second pair of eyes on their security assumptions, and does not get the benefit of the reviewer's distinct perspective. Approving without reading devalues both the reviewer's and the author's time.

### Anti-Pattern 5: The Off-Topic Review

A PR adds a new endpoint to the user service. The reviewer blocks it to ask about an unrelated technical debt issue in a file that was not changed by this PR.

Code review scope is the diff. If you see a problem in code the PR did not change, file a separate ticket or create a follow-up PR. Do not block the current PR on unrelated technical debt.

---

### Brainstorming Q&A — Part 11

**Q1: How do you handle a situation where a PR has a mix of good and bad patterns and you are not sure whether to approve or block?**

Create a clear inventory. Write down your blocking comments first — the things that must be fixed before this merges. Then write your suggestions. Then your nits. If the blocking comments are addressable (fixable in under two hours of work) and not fundamental design issues, block with a clear list and expect the author to address them in the current PR. If the blocking comments would require significant rework, consider whether to block for a redesign vs approve with a follow-up ticket. The deciding question is: if this ships as-is, what is the worst realistic outcome? If the answer is "a bug that is hard to detect and expensive to fix" or "a security vulnerability" — block. If the answer is "code that is less maintainable than it should be" — consider approve with a follow-up ticket, depending on how unmaintainable.

**Q2: What do you do when you submit a PR and realize mid-review-process that it needs significant changes you had not anticipated?**

Tell the reviewer immediately. Do not let them finish a review on code you know is going to change significantly. "I realized while addressing your first few comments that the approach needs to change significantly. I'm going to close this PR and open a new one. Thank you for the initial feedback — it helped me see the issue." This respects the reviewer's time and prevents confusion. Reviewers who go back to review round 2 of a PR and find the code has completely changed feel their time was wasted. Closing and reopening with a clean slate is the respectful move.

**Q3: How do you give feedback on a PR from someone who is clearly more knowledgeable than you in the domain?**

The same way you give feedback to anyone, with appropriate calibration of your confidence. "I might be missing something, but I don't see where the circuit breaker timeout is being configured. Is there a default somewhere I'm not seeing?" is a valid comment regardless of who wrote the code. If they are more expert than you, they will either explain why your concern is addressed (and you learned something) or acknowledge you caught something they missed (and you added value). Neither outcome is bad. The only bad outcome is not asking — either because you assumed the expert could not miss something, or because you were worried about seeming naive. Both of those fears are more costly than the rare discomfort of being wrong in a comment.

---

## Common Interview Mistakes

When interviewers at L5+ companies ask "how do you approach code review?", most candidates make one or more of these mistakes. Each one signals a candidate who does code review as a checkbox rather than a discipline.

### Mistake 1: Treating "Catching Bugs" as the Only Goal

**What candidates say:** "I read through the code carefully to make sure there are no bugs, check for edge cases, and then approve."

**Why it fails:** This is only Level 1 and Level 2 of the review hierarchy. A candidate who only mentions correctness has not demonstrated awareness that code review also creates knowledge transfer, raises team standards, and catches design-level problems. The interviewer's follow-up will be: "And what else do you look for?" If you have no answer, you have failed to demonstrate staff-level thinking.

**What to say instead:** Start with the four goals. Correctness is one of them. Show you know all four and can explain how they each manifest differently in a review.

### Mistake 2: Not Distinguishing Between Types of Feedback

**What candidates say:** "I leave comments on whatever I notice."

**Why it fails:** This does not show any framework for communicating priority. The interviewer wants to hear about blocking vs suggestion vs nit, and why the distinction matters for the author experience. "Whatever I notice" is what every reviewer does — the discipline is in how you communicate what you noticed.

**What to say instead:** Explain the labeling system and why it exists. The author needs to know what must be fixed vs what is optional. Without labels, the author either over-addresses everything (slow and exhausting) or under-addresses everything (you never know which comments are blocking).

### Mistake 3: Not Mentioning Response Time

**What candidates say:** They talk at length about what to look for in a review but never mention timing.

**Why it fails:** Review cycle time is one of the primary levers on team velocity. An interviewer who asks about code review culture cares about the behavioral norms around review, not just the technical checklist. Omitting response time is omitting one of the most important dimensions of the discipline.

**What to say instead:** Mention the 24-hour acknowledgment rule. Explain that you batch comments in one pass. Explain that review speed is a form of respect for the author's time.

### Mistake 4: Only Discussing the Reviewer's Role

**What candidates say:** A full answer about how they review, with nothing about how they write PRs or respond to feedback.

**Why it fails:** Code review is a two-sided interaction. An interviewer at L5+ knows that how you behave as an author is as revealing as how you behave as a reviewer. Do you write small, focused PRs? Do you write good descriptions? Do you respond to feedback collaboratively or defensively? Not mentioning the author side suggests you have not thought about review as a two-way discipline.

**What to say instead:** After explaining your reviewer behavior, briefly describe what you do as an author: PR size, description anatomy, how you respond to feedback. This shows you understand both sides.

### Mistake 5: No Concrete Examples

**What candidates say:** Abstract descriptions of good review practice with no specific examples of what a bad comment vs a good comment looks like.

**Why it fails:** "I try to be constructive and explain the why behind my comments" is a true statement that reveals nothing about your actual behavior. Everyone believes they are constructive. Interviewers are listening for the concrete: can you give me an example of a bad comment, and can you rewrite it as a good one?

**What to say instead:** Have two or three concrete examples ready. "Instead of 'this is broken,' I would write 'this will fail when X because of Y — here is how I would fix it.' The difference is that the author learns something from the second version." Concrete is credible.

### Mistake 6: Confusing Code Review With Architecture Review

**What candidates say:** "If I see a fundamental design problem in a PR, I leave detailed comments explaining how to redesign it."

**Why it fails:** Design problems caught in code review are design problems caught too late. A staff engineer knows that a fundamental design concern should trigger a design conversation, not 40 implementation comments. Treating code review as the right venue for design decisions signals that the candidate does not know when to escalate.

**What to say instead:** "If I see a design concern, I block the PR with a single comment describing the concern and propose a design conversation. I don't leave implementation comments on a PR I'm blocking for design reasons — it creates confusion about what needs to change."

---

## Exercises

**Exercise 1: Classify These Comments**

Read the following five review comments and classify each as BLOCKING, SUGGESTION, or NIT. For each BLOCKING classification, explain why. For each SUGGESTION, explain what makes it worth recommending but not blocking on.

1. "Use `is None` instead of `== None` in Python."
2. "This function mutates the input list directly. The caller might not expect that."
3. "I'd use a dictionary here instead of two parallel lists, it's cleaner."
4. "There's no authentication check on this endpoint — any unauthenticated user can call it."
5. "The variable name `data` is not very descriptive."
6. "This query will produce a full table scan on the users table which has 50M rows."

**Exercise 2: Rewrite Five Bad Comments**

For each of the following bad review comments, rewrite it as a good one (with a label, with context for the "why," and with a concrete suggestion).

1. "Wrong. Use a prepared statement."
2. "This will not work."
3. "Please add tests."
4. "Bad naming."
5. "Security issue here."

**Exercise 3: Review the Following PR**

Read this code and write a complete code review, applying the five-level hierarchy. Label every comment. Include at least one positive comment.

```python
import os
import mysql.connector

def get_user_profile(user_id):
    conn = mysql.connector.connect(
        host="db.internal.company.com",
        user="admin",
        password="Secur3P@ss!",
        database="users_db"
    )
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
    user = cursor.fetchone()
    print(f"Retrieved user: {user}")
    return user

@app.route('/profile')
def profile():
    user_id = request.args.get('user_id')
    user = get_user_profile(user_id)
    return jsonify(user)
```

**Exercise 4: Write a PR Description**

You have written a change that: (a) adds a `last_login` column to the users table via migration, (b) updates the login endpoint to populate the column on each login, (c) adds a new `/api/users/inactive` endpoint that returns users who have not logged in for 90 days, and (d) adds an index on the `last_login` column. Write a complete PR description using the anatomy from Part 5.

**Exercise 5: The Intern-to-Staff Progression**

For the following code, write four versions of a code review comment: Intern, L3 (Junior), L4 (Mid), L5 (Senior). Then write the L6 (Staff) version that adds a consideration none of the others raised.

```python
def send_welcome_email(user):
    email_service.send(
        to=user.email,
        subject="Welcome!",
        body=f"Hello {user.name}, welcome to our platform!"
    )
```

**Exercise 6: Design the Review Norms**

Your team has: six engineers at L3-L4, two senior L5 engineers, and you (L5/L6). Currently: PRs sit for 2-4 days on average, comments are unlabeled, PRs are often 1000+ lines. Write the team's code review norms document that you would propose, covering: expected response times, comment labeling, PR size expectations, PR description requirements, and how design-level concerns are escalated.

**Exercise 7: Security Review Pass**

Review the following code and produce a security-focused review. Identify every security issue, label each as critical/high/medium/low, and provide a specific fix for each.

```python
@app.route('/api/search')
def search():
    q = request.args.get('q')
    results = db.execute(f"SELECT title, content FROM posts WHERE title LIKE '%{q}%'")
    
    logger.info(f"User {request.headers.get('X-User-Email')} searched for: {q}")
    
    html_results = ""
    for r in results:
        html_results += f"<div>{r['title']}: {r['content']}</div>"
    
    return f"<html><body>{html_results}</body></html>"
```

**Exercise 8: Code Review Calibration**

You are reviewing a PR that makes 450 lines of changes to the payment processing service. You have read through it and have the following list of observations. For each, decide: block, suggest, nit, or ignore.

1. A function called `process` that does payment processing, refund processing, and subscription upgrades
2. A missing try/except around the external payment API call
3. Variable named `x` that is used for a transaction ID
4. Retry logic that retries on ALL exceptions including 400 Bad Request
5. A new `payment_log` table with no index on the timestamp column
6. Logging that includes the last four digits of a credit card number
7. A comment that says "TODO: add auth check here" next to an endpoint
8. Inconsistent spacing between functions (some have two blank lines, some have one)

---

## Homework

**Homework 1: Code Review Audit**

For the next two weeks, keep a log of every code review you give. For each review, record: how long did it take to acknowledge? How long until the full review? How many comments did you leave, and what fraction were blocking vs suggestion vs nit? How many rounds did it take to approve? At the end of two weeks, compute your averages and identify one specific behavior to improve.

**Homework 2: Transform Your Team's Review Culture**

Identify one specific code review anti-pattern on your current team (unlabeled comments, long cycle times, PRs that are too large, etc.). Write a proposal for addressing it: what the current state is, what the desired state is, how you would measure improvement, and what specific norm change would produce it. Share this with your team in a retro.

**Homework 3: Intern Review → Staff Review**

Find a recent PR on your codebase that you were not involved in reviewing. Review it yourself from scratch, applying the five-level hierarchy. Compare your comments to the comments that were actually left. What did you catch that the real reviewers missed? What did the real reviewers catch that you missed? Write a one-page reflection on what the comparison reveals about your review blind spots.

**Homework 4: Security Review Pass on Production Code**

Pick one service or module you own that has not had a dedicated security review in the last six months. Apply the security review checklist from Part 9 to the most recently changed files. File tickets for every issue you find. How many issues were there? What was their severity distribution? What does this tell you about your team's security review practices?

**Homework 5: Write a Team Code Review Norm**

Draft a "code review charter" for your team: a one-to-two page document that defines expected behavior for both reviewers and authors. Cover response times, comment labeling, PR size, PR description, and the process for escalating design concerns. Bring it to your team's next planning meeting and gather feedback. Iterate based on the feedback and get consensus on at least one concrete change the team will make.

---

## Key Takeaways

```
+================================================================+
|                    KEY TAKEAWAYS                               |
|                                                                |
|  1. CODE REVIEW HAS FOUR GOALS — not one.                     |
|     Correctness. Maintainability. Knowledge Transfer.         |
|     Raising the Bar. Only knowing goal one is not enough.     |
|                                                                |
|  2. THE REVIEW HIERARCHY EXISTS TO PROTECT YOUR ATTENTION.   |
|     Check correctness → robustness → maintainability →        |
|     design → security/perf/observability. In that order.     |
|     Do not spend 20 minutes on variable names when the        |
|     auth check is missing.                                     |
|                                                                |
|  3. LABEL EVERY COMMENT: BLOCKING / SUGGESTION / NIT.        |
|     Unlabeled comments create guessing games. Labeled          |
|     comments let authors prioritize correctly.                 |
|                                                                |
|  4. CONTEXT AND WHY, NOT JUST WHAT.                          |
|     "Use a Set" teaches nothing.                               |
|     "Use a Set because List.contains() is O(n) and you're     |
|      calling this in a hot path" teaches the engineer.         |
|                                                                |
|  5. BATCH YOUR FEEDBACK. ONE ROUND, FULLY READ FIRST.        |
|     Multiple rounds of partial feedback wastes the             |
|     author's time and yours. Read all, then comment.          |
|                                                                |
|  6. 24-HOUR ACKNOWLEDGMENT IS THE PROFESSIONAL MINIMUM.      |
|     Silence is not neutral. Authors are blocked, waiting.     |
|                                                                |
|  7. PR SIZE: 200-400 LINES IS THE SWEET SPOT.               |
|     Review quality drops sharply above 400 lines.             |
|     Large features are sequences of small PRs.                |
|                                                                |
|  8. STAFF REVIEW READS THE SYSTEM, NOT JUST THE CODE.       |
|     Read the file list first. Ask if this is the right        |
|     problem. Think about what the caller does with output.    |
|                                                                |
|  9. SECURITY HAS A CHECKLIST. USE IT.                        |
|     Input validation. Auth. Authz. SQL injection.             |
|     Secrets in code. PII in logs. Rate limiting.              |
|                                                                |
| 10. CODE REVIEW IS NOT WHERE DESIGN GETS DECIDED.           |
|     Design concerns in a PR mean a design doc was missing.   |
|     Escalate with one comment. Do not leave 40 impl notes.   |
|                                                                |
| 11. YOUR REVIEW BEHAVIOR IS YOUR TEAM'S CULTURE.            |
|     The most senior reviewer in the room models the norm.    |
|     Review how you want your team to review.                  |
|                                                                |
| 12. THE BEST CODE REVIEW TEACHES. THE WORST JUST CORRECTS.  |
|     A correction fixes one PR. A teaching moment fixes        |
|     every PR the engineer writes from that point on.          |
+================================================================+
```

---

## Further Reading

- *Code Review Guidelines* — Google Engineering Practices (publicly available at google.github.io/eng-practices)
- *The Code Reviewer's Guide* — Derek Prior (talk)
- *Accelerate* — Forsgren, Humble, Kim (for the research on review cycle time and deployment frequency)
- *The Pragmatic Programmer* — Hunt and Thomas (chapters on code ownership and collective code ownership)
- *Building Secure and Reliable Systems* — Google SRE Book supplemental (for the security review lens)

---

*Chapter 96 — Section 7: Engineering as a Discipline*
*System Design for L6: The Complete Guide*
