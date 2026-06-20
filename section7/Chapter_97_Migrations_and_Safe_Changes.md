# Chapter 76: Migrations and Safe Changes

> TODO: Full chapter to be written.

---

## Planned Coverage

**Core thesis:** Every system you will ever work on needs to change while it is running. Migrations are not a one-time event — they are a core engineering discipline. The question is never "can we do this?" but "how do we do this without losing data or availability?"

**Topics to cover:**

### Part 1: Why Live Migrations are Hard
- The fundamental tension: old system must keep running while you build the new one
- Data migrations vs code migrations vs infrastructure migrations — each needs a different approach
- The "airplane mid-flight" analogy
- Intern → Staff: same migration, four levels of caution and rollback strategy

### Part 2: The Expand-Contract Pattern (The Universal Migration Method)
- Phase 1 EXPAND: add the new thing alongside the old. Don't remove the old yet.
- Phase 2 MIGRATE: move traffic/data gradually to the new thing
- Phase 3 CONTRACT: remove the old thing once migration is complete
- Why skipping any phase causes incidents
- Real examples: adding a column, renaming a column, changing an API

### Part 3: Zero-Downtime Database Migrations
- Why `ALTER TABLE ADD COLUMN NOT NULL` can lock a 100M-row table for hours
- Safe migration sequence for adding a NOT NULL column (5 steps)
- Safe migration sequence for renaming a column (6 steps with dual-write)
- Safe migration sequence for changing a data type
- Backfilling large tables without blocking reads/writes
- Tools: pt-online-schema-change, gh-ost (GitHub's online schema change tool)

### Part 4: Dual-Write Pattern
- When to use it: migrating data from one store to another while keeping both in sync
- The three phases: write to both, read from old, verify parity, read from new
- The "shadow mode" variant: write to new, don't read from it, just compare
- Common dual-write bugs: ordering issues, partial failures, consistency gaps

### Part 5: Strangler Fig Pattern
- Migrating a monolith to microservices without a big bang rewrite
- How the strangler wraps the old system and intercepts traffic gradually
- The routing layer: what it looks like and how to build it
- Real example: how Shopify and Airbnb migrated incrementally

### Part 6: Feature-Flag-Driven Cutover
- Using feature flags to migrate 1% → 5% → 20% → 100% of traffic
- How to define the rollback condition before you start
- Measuring parity: what does "the new thing works correctly" mean in numbers?
- When to speed up vs slow down the rollout

### Part 7: API Migrations and Versioning
- How to add a new API version without breaking old clients
- Backward-compatible changes vs breaking changes — the full list
- Deprecation policy: how to sunset an old API without breaking partners
- The consumer-driven contract testing approach

### Real Incidents to include
- GitHub: migrating from MySQL to Vitess (multi-year migration)
- Stripe: API versioning strategy for 10+ years of backward compatibility
- Twitter: MySQL to Manhattan (failed migration attempt, lessons learned)
- Airbnb: service extraction from the Rails monolith

### Exercises
- Design the migration plan for adding a required field to a 50M-row table
- Design the strangler fig routing layer for extracting a payments service
- Write the rollback plan for a dual-write migration that has been running for 2 weeks

---

*Status: TODO — placeholder only*
