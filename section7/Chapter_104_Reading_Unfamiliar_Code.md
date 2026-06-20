# Chapter 83: Reading Unfamiliar Code — Day 1 at a New Team

> You join a new team. The codebase has 500,000 lines of code written by
> 50 engineers over 5 years. Your first task lands on Monday. Nobody teaches
> you how to build a mental model of a system you didn't write.
> This chapter does.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

Every engineer changes teams, companies, or codebases. The speed at which you
become productive on an unfamiliar codebase is a direct signal of seniority.
L3s read code linearly. L5s find the entry points. L6s build a mental model of
the entire system in days, not weeks — by following a deliberate strategy, not
by reading every file.

---

## Planned Content

### Part 1: The Mental Model Problem
- Code is not a story; it has no beginning or end
- The mistake: reading code from top to bottom (linear reading = weeks)
- The goal: build a mental model of the SYSTEM, not memorize the code
- Mental model components: data flow, state ownership, invariants, failure modes
- "Read to understand, not to remember" — you'll reread; build navigation instinct

### Part 2: The Entry Points Strategy (First 2 Hours)
- Find the main entry points: HTTP handler, queue consumer, cron job entrypoint
- Trace one request end-to-end: input → processing → output → storage
- Don't read every function — read the CALL GRAPH at a high level
- Tools: IDE "go to definition", `grep`, call hierarchy viewers
- Goal after 2 hours: can draw a rough box diagram of the system

### Part 3: Data First, Code Second
- Find the data model: database schema, protobuf definitions, key structs/classes
- Data structures reveal the system's purpose more clearly than code
- What tables exist? What are the foreign keys? What's the primary key design?
- What's in the event schemas (Kafka topics, pubsub messages)?
- Goal: understand what the system STORES before understanding what it DOES

### Part 4: Find the Tests (They Are the Spec)
- Integration tests: show how the system behaves end-to-end
- Unit tests: show what edge cases the author thought about
- Test names are free documentation: "test_payment_fails_if_insufficient_balance"
- Run the tests: if they pass, you have a working baseline; if not, first task = fix them
- Missing tests = undocumented behavior = high-risk areas for changes

### Part 5: Read the Git History (Code Has a Story)
- `git log --oneline` for recent changes: what has been touched lately?
- `git blame` for confusing code: who wrote this and when? (context in commit message)
- Large commits: usually refactors or migrations — read these to understand past decisions
- `git log -S "function_name"`: when was this function introduced? what was the PR?
- Incident-related commits: look for "hotfix", "emergency", "rollback" — these reveal fragile areas

### Part 6: Find the Invariants and the Sharp Edges
- Invariants: conditions that must always be true ("balance is never negative")
- Look for: assertions, panics, validation logic, comments with "MUST", "NEVER", "ALWAYS"
- Sharp edges: code that's easy to misuse, has non-obvious preconditions, or has caused bugs
- Singletons, global state, shared mutable state: always dangerous, always worth understanding
- Rate limits, timeouts, retry logic: often the difference between "works" and "works at scale"

### Part 7: The 30-60-90 Day Ramp Plan
- Day 1–7: understand the system (data model, entry points, main flows)
- Day 8–30: make a small but real change (bug fix or small feature) to verify understanding
- Day 31–60: make a medium change independently; identify gaps in understanding
- Day 61–90: own a component; be able to review others' changes for correctness
- Week 1 red flag: still reading without running the code

### Part 8: Interview Application
- Behavioral question: "Tell me about a time you joined a new team and had to ramp up quickly"
- L6 answer structure: specific strategy used (entry points, data model, git history),
  what you built first to validate understanding, how long until you were productive,
  what you wish you had done differently
- Avoid: "I read all the code" (not credible) or "I asked my teammates" (passive)

---

## The One-Sentence Summary

> "Reading unfamiliar code = find the entry points (trace one request end-to-end) + read the data model (schema reveals purpose) + run the tests (they are the spec) + git blame the confusing parts (history explains decisions) — building a mental model takes days, not weeks, if you follow this order instead of reading linearly."

---

*Full chapter: ~2,500 lines. Section 7 craft chapter.*
