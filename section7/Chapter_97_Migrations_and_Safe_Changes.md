# Chapter 97: Migrations and Safe Changes

> "The hardest part of migration is not the technical implementation — it is doing the work while the system is still running and customers are still depending on it." — Senior Engineer, Google Infrastructure

---

## Why This Chapter Matters

Every system that has ever been built eventually needs to change. Sometimes that change is small — adding a column to a database table or renaming an API field. Sometimes it is enormous — moving an entire company from a monolithic application to microservices, or migrating 500 million user records from one database engine to another. The challenge that separates senior engineers from junior engineers is not whether they can design systems from scratch. It is whether they can change systems that are already running in production, serving real customers, with zero tolerance for downtime and zero tolerance for data loss.

This chapter is about exactly that skill. We will cover the full spectrum of migrations: database schema changes, API version transitions, infrastructure platform switches, and the coordination challenges that come with moving a large system from one state to another. We will look at the patterns that make migrations safe, the real incidents where migrations went wrong, and the leadership behaviors that staff engineers use to shepherd multi-team migrations to completion.

By the end of this chapter, you will be able to walk into a system design interview and confidently discuss not just how to build a system, but how to evolve it safely over time. That capability is what distinguishes L6 thinking from L5 thinking.

---

## Part 1: Why Live Migrations Are Hard

### The Airplane Mid-Flight Analogy

Imagine you are the chief engineer on a commercial airplane that is currently flying at 35,000 feet with 200 passengers on board. The aircraft manufacturer has just informed you that the engine model you are using has been discontinued, and you need to swap it out for a new model. You cannot land the plane to do the work. You cannot ask the passengers to hold their breath for 30 minutes. You have to perform the engine swap while the plane is flying, the passengers are watching movies, the flight attendants are serving drinks, and air traffic control is routing you through busy airspace.

This is exactly what live migrations feel like. Your production system is the airplane. Your users are the passengers. The engine is whatever you are trying to change — a database, an API contract, an infrastructure platform. And the unbreakable constraint is that you cannot simply turn off the system to do the work.

This analogy reveals several deep truths about live migrations. First, you cannot do the work all at once. You have to do it incrementally, one piece at a time, making sure each incremental step is safe before moving to the next. Second, you need to be able to reverse any step quickly. If you start detaching the old engine and the new engine does not fit properly, you need to be able to reattach the old engine immediately. Third, the passengers (your users) should ideally not notice that anything is happening at all. Fourth, if something goes wrong, you need to know immediately — you cannot afford to discover the problem an hour later when the plane is already falling.

### The Three Types of Migrations

When engineers talk about migrations in a system design context, they are typically referring to one of three broad categories, and understanding which type you are dealing with changes everything about how you approach the problem.

The first type is **data migrations**. These involve moving, transforming, or restructuring data that already exists. Adding a new column to a database table that has 100 million rows. Moving data from a relational database to a document store. Encrypting fields that were previously stored in plaintext. Renaming a column to better reflect its purpose. The common thread is that the data itself needs to change state, and that data is being actively read and written by production traffic while you are trying to change it.

The second type is **code migrations**. These involve changing the behavior of running software — the logic, the contracts between services, the interfaces that clients depend on. Changing the format of an API response. Deprecating an old endpoint and introducing a replacement. Splitting a monolithic service into two separate services. The challenge here is that multiple versions of the code often need to coexist during the transition period: the old version talking to old clients, the new version talking to new clients, and some period where both versions need to work simultaneously.

The third type is **infrastructure migrations**. These involve changing the underlying platform that your system runs on. Moving from bare metal servers to a cloud provider. Switching database engines — for example, from MySQL to Postgres, or from a single-node database to a distributed database like Vitess or CockroachDB. Moving from one cloud region to another. The challenge here is that infrastructure changes often affect latency, consistency, and failure modes in ways that are hard to predict from testing alone.

In practice, most real-world migrations combine all three types simultaneously. The GitHub migration from MySQL to Vitess, which we will examine in detail later in this chapter, required changing the database infrastructure (Vitess instead of MySQL), the data itself (schema changes, data movement), and the code that talked to the database (query compatibility, connection management). Managing all three simultaneously, for a system serving millions of developers, is one of the most complex engineering challenges a team can undertake.

### Why Simple Solutions Do Not Work

When people encounter their first migration problem, they often reach for a simple solution: maintenance mode. Just take the system down for a few hours, do all the changes at once, bring it back up. This approach has three fatal problems.

First, modern internet services cannot afford the downtime. A major e-commerce site that goes down for two hours to migrate a database might lose millions of dollars in sales and erode customer trust permanently. A payment processing system that goes offline during migration might fail regulatory compliance requirements. A social media platform with users in multiple time zones has no "off-peak window" that is quiet everywhere simultaneously.

Second, even if you could take downtime, bulk changes are high-risk changes. If you run a massive batch migration all at once and something goes wrong halfway through, you are in a deeply bad state: half the data is in the old format, half is in the new format, and your system may not be able to handle either correctly. Rolling back a half-completed migration can be as complex as completing it.

Third, "maintenance windows" tend to shrink over time. What starts as "we have a four-hour window every Sunday morning" gradually becomes "we have a two-hour window" and then "we have to justify any downtime to leadership" and then "no downtime allowed." The earlier you build the discipline of zero-downtime migrations, the better your team's long-term trajectory.

### The Fundamental Tension

The core tension in every live migration is this: **you need to change the system, but the system is being used while you change it.** This creates a state-machine problem. Before the migration, the system is in State A. After the migration, the system is in State B. But during the migration, the system needs to be simultaneously compatible with both State A behavior (for old clients and old data) and State B behavior (for new clients and new data). Managing this dual-compatibility window is the heart of what makes migrations hard.

```
Timeline of a Live Migration

STATE A                  TRANSITION WINDOW                 STATE B
(Before Migration)       (Both states must work)           (After Migration)

Users read/write    -->  Old format still works      -->  Only new format
Old data format          New format also works             New data format
Old code                 Both code versions running        New code only
Old infrastructure       Parallel systems running          New infrastructure
                         ^^^^^^^^^^^^^^^^^^^^^^^^^
                         This is the hardest part.
                         Can last days, weeks, or months.
```

### Intern to Staff: How Understanding Grows

**Intern level:** Knows that migrations exist. Might write a one-time SQL script to update some rows. Does not think about concurrent writes during the migration.

**Junior (L3) level:** Understands that migrations need to be tested. Knows to run migrations during low-traffic windows. Has experienced a migration that caused table locking and learned from it.

**Mid-level (L4) level:** Can design a migration that uses transactions properly. Knows about tools like flyway or liquibase for managing migration scripts. Understands the difference between reversible and irreversible changes.

**Senior (L5) level:** Designs migrations that are zero-downtime from the start. Understands the expand-contract pattern. Knows how to use feature flags to gate the migration. Has led migrations that took weeks and involved coordinating multiple services.

**Staff (L6) level:** Defines the migration strategy for the entire organization. Designs the tooling and protocols that make future migrations safer. Coordinates migrations that span multiple teams and services. Sets the sunset deadlines and escalation paths. Thinks about what invariants must be preserved across the entire transition and designs the monitoring to verify them continuously.

### Brainstorming Q&A

**Q: A candidate says "I would just use a maintenance window to do the migration." How would a staff engineer respond to that?**

A staff engineer hearing this response would immediately probe for whether the candidate understands why maintenance windows are problematic at scale. The candidate's instinct is understandable — it simplifies the problem enormously to just stop the system, change everything, restart it. But the staff engineer would push back on several dimensions. First, can the system actually tolerate downtime? For many systems, the answer is no: payment processors, healthcare platforms, real-time communications systems, and global consumer products all have users in multiple time zones who expect continuous availability. Second, even if downtime is permitted, does the candidate understand the rollback complexity? If a maintenance-window migration fails halfway through, you may be in a worse state than before. Third, the staff engineer would ask about organizational trust: once you have a maintenance window, the business will come to rely on it, and eventually it will be scheduled away entirely. Building the discipline of zero-downtime migrations is worth the upfront investment. The candidate who understands these dimensions and frames the maintenance-window approach as a last resort, rather than a first choice, is showing L5+ thinking.

**Q: What is the most dangerous moment in a live migration, and why?**

The most dangerous moment in almost every live migration is the moment you switch reads from the old system to the new system. Up until that point, you have been writing to both systems and can verify that the new system has correct data before anyone depends on it. But the moment you start directing real user traffic to the new system, any data quality problems, performance regressions, or behavioral differences become immediately visible to users. This is the point of no return in a sense — once users are making decisions based on data from the new system, rolling back becomes much more complex because you have to reconcile the divergent state. Smart migration strategies try to make this read switchover moment as low-risk as possible by doing extensive dark reads (reading from the new system without trusting the results), comparing the results against the old system, and gradually shifting traffic rather than doing a hard cutover. The window right before and after the read switchover is when the migration team needs to be most attentive, with dashboards showing key metrics and fingers hovering over the rollback controls.

---

## Part 2: The Expand-Contract Pattern

### What Is Expand-Contract?

The expand-contract pattern (also called parallel-change) is the most important design pattern in safe live migrations. It is not a single technique but a meta-pattern — a way of thinking about how to make any breaking change safely by splitting it into three distinct phases: expand, migrate, and contract.

The key insight behind expand-contract is that you should never make a change that takes the system from supporting the old way directly to supporting only the new way. Instead, you first expand the system so that it supports both the old way and the new way simultaneously. Then you migrate everything to use the new way while the old way is still available as a safety net. Finally, once you have verified that everything is on the new way, you contract by removing support for the old way.

This sounds simple, but it is deceptively powerful. It means that at no point during the migration is the system in a state where some component needs the old behavior and another component needs the new behavior, yet the system only supports one of them. The dual-support window is the transition period, and it can be as long as necessary to ensure confidence before contraction.

### Concrete Example 1: Adding a Column

Consider a users table in a relational database with columns: id, email, created_at. You need to add a phone_number column that will be NOT NULL (mandatory) for all new users. Here is how expand-contract applies.

**Expand phase:** Add the phone_number column as nullable (allowing NULL). Deploy no code changes yet. The database now supports both old users (no phone number) and new users (with phone number). Old code still works because it does not reference the new column. New code can start writing phone numbers but does not yet require them.

**Migrate phase:** Backfill a default phone number for all existing rows that need one. Update the application code to collect and write phone numbers for new users. Gradually, all rows acquire a phone number value. During this phase, you can check what percentage of rows have a non-null phone_number and track progress toward 100%.

**Contract phase:** Once 100% of rows have a non-null value and the application code is consistently writing phone numbers for all new users, add the NOT NULL constraint. The constraint will pass because all rows already satisfy it. Old code paths that do not write phone_number will fail if they create new users, but by this point you have already removed those old code paths.

### Concrete Example 2: Renaming a Column

Renaming a column is one of the most dangerous operations in a live system because the old name and the new name need to coexist for some period. Here is how expand-contract handles it.

The column is currently called `user_name`. You want to rename it to `display_name` because the product team decided `user_name` was confusing.

**Expand phase:** Add a new column called `display_name`. Write application code that writes to both `user_name` and `display_name` simultaneously on every write operation. Do not yet read from `display_name`. This phase ensures that `display_name` will stay in sync with `user_name` going forward.

**Migrate phase:** Backfill `display_name` from `user_name` for all existing rows. Once backfill is complete, update all read paths in the application to read from `display_name` instead of `user_name`. You are now reading from the new column, but still writing to both. Verify with monitoring that `display_name` values are correct and that the application is functioning normally.

**Contract phase:** Stop writing to `user_name`. Remove all references to `user_name` from the application code. Once you have confirmed that no application code reads from or writes to `user_name`, drop the column from the database schema.

### Concrete Example 3: Changing an API Response Format

Suppose your API currently returns a user's name as a single string field: `"name": "John Smith"`. The mobile team wants to change this to a structured object: `"name": {"first": "John", "last": "Smith"}`. Old mobile clients depend on the string format. New mobile clients want the object format.

**Expand phase:** Update the API to return both formats simultaneously: `"name": "John Smith"` and `"name_parts": {"first": "John", "last": "Smith"}`. Old clients continue using `name`. New clients can start using `name_parts`.

**Migrate phase:** Release new versions of mobile apps that use `name_parts`. Wait for the old mobile app versions to age out of active use (this could take weeks or months). Monitor what percentage of API calls still read the `name` field from clients running old app versions.

**Contract phase:** Once the percentage of requests that depend on the `name` field falls below your threshold (perhaps below 1% of traffic, or below 0.1%), remove the `name` field from the response and make `name_parts` the canonical format.

```
Expand-Contract Pattern (3 Phases)

EXPAND                  MIGRATE                   CONTRACT
+--------------+        +--------------+          +--------------+
| Add new way  |        | Move traffic |          | Remove old   |
| Keep old way +------> | to new way   +--------> | way entirely |
| Both work    |        | Verify parity|          | Clean it up  |
+--------------+        +--------------+          +--------------+
                        ^              ^
                        |              |
                    Write to both   Read from new,
                    read from old   verify correctness
```

### Why Teams Skip the Contract Phase (And Why That Is a Problem)

In practice, the phase that teams most often skip or delay indefinitely is the contract phase. After successfully migrating to the new way, there is a temptation to leave the old way in place "just in case" someone still needs it. This is a mistake for several reasons.

First, supporting two ways of doing the same thing forever doubles the maintenance burden. Every future change has to account for both the old column and the new column, both the old API field and the new one. Second, keeping old code paths active means that bugs in those paths can still affect production. Third, unused columns and fields consume storage and confuse future engineers who wonder why both versions exist. The contract phase should be treated as a mandatory part of the migration, not optional cleanup.

### Intern to Staff: How Understanding Grows

**Intern level:** Adds the new column or field, but does not think about what happens to existing data or existing callers.

**Junior (L3) level:** Knows to add columns as nullable first, then backfill, then add constraints. Does migrations in separate deployments.

**Mid-level (L4) level:** Understands the dual-write period. Knows how to write application code that handles both old and new formats gracefully.

**Senior (L5) level:** Designs the full three-phase plan upfront, estimates how long each phase will take, and defines the metrics that will signal readiness to move to the next phase.

**Staff (L6) level:** Identifies all the implicit dependencies that a migration might break. Ensures that the migration plan accounts for caches, downstream consumers, event streams, and monitoring dashboards that might be silently depending on the old format. Defines the organizational process for ensuring the contract phase actually happens.

### Brainstorming Q&A

**Q: Why is the expand-contract pattern sometimes called "parallel change"? Are they exactly the same thing?**

Expand-contract and parallel change are essentially the same concept with different emphases in their naming. The term "parallel change" comes from Martin Fowler's refactoring vocabulary and emphasizes the idea that during the migration period, the old behavior and the new behavior are both running in parallel — side by side. The term "expand-contract" emphasizes the lifecycle shape: you first expand the surface area of what the system supports (adding the new way without removing the old), and then you contract it (removing the old once the new is established). Both terms are describing the same underlying pattern. In practice, "expand-contract" is more common in the database and API migration context, while "parallel change" is more common in the refactoring and code evolution context. Understanding both names is useful because different engineers and different organizations will use different terminology, and being able to recognize the pattern regardless of what it is called is a sign of depth.

**Q: How does expand-contract handle the case where the old and new formats cannot coexist in the same database table — for example, if you are completely restructuring the schema?**

When the old and new schemas are so different that they cannot coexist in the same table, expand-contract works at a higher level of abstraction. Instead of adding new columns to the existing table, you create an entirely new table with the new schema alongside the old table. The expand phase involves creating the new table and writing to both tables simultaneously. The migrate phase involves backfilling the new table from the old table and gradually shifting reads to the new table while verifying correctness. The contract phase involves stopping writes to the old table, verifying that it is no longer referenced by any application code, and eventually dropping it. This is a more extreme form of the pattern, but the three-phase structure is the same. The dual-write-to-two-tables approach is more complex to implement and has more potential for data divergence, so it requires more careful monitoring and a longer verify-before-contracting period. The GitHub Vitess migration used a variant of this approach, where new shards were created alongside old shards, traffic was gradually shifted, and then old shards were decommissioned.

---

## Part 3: Zero-Downtime DB Schema Migrations

### The ALTER TABLE Locking Problem

If you have ever run `ALTER TABLE` on a large MySQL table and watched the entire application grind to a halt for ten minutes, you have experienced the most common database migration disaster. Here is why it happens.

In many database engines, certain schema changes require acquiring an exclusive lock on the entire table for the duration of the operation. An exclusive lock means that no reads and no writes can proceed while the lock is held. For a small table with a few thousand rows, this might take a fraction of a second. For a table with 100 million rows, it can take 15-30 minutes. During those 30 minutes, every application query that touches that table will sit in a queue waiting for the lock to be released. If the queue fills up faster than it drains, connections pile up. Connection pools exhaust. Timeouts cascade. What started as a simple "add a column" turns into a full-scale production incident.

The locking behavior varies significantly between database engines and between different types of schema changes. MySQL InnoDB in modern versions handles many operations with online DDL, which reduces or eliminates locking. But some operations — particularly adding foreign key constraints, changing column types in incompatible ways, or modifying character sets — still require full table locks. PostgreSQL has its own set of locking behaviors that differ from MySQL in important ways. Understanding the specific locking behavior of your database engine for each type of schema change is essential knowledge for any engineer who works with large databases.

### The 5-Step Sequence for Adding a NOT NULL Column

Adding a NOT NULL column to a large table is one of the most common and most dangerous schema migrations in practice. Here is the safe five-step sequence that avoids locking production.

**Step 1: Add the column as nullable with no default.** This operation is fast in most databases because it simply updates the metadata — the database does not need to rewrite all the rows to add the new column. The column is added to the schema, but all existing rows implicitly have NULL as its value. No application code changes yet.

**Step 2: Deploy code that writes the new column on new writes, but does not require it on reads.** This is the beginning of the expand phase. New rows being inserted will now have the column populated. Old rows still have NULL. Reads do not fail because the column is still nullable. This code deployment is safe to roll back because the column being present but nullable does not break old code.

**Step 3: Backfill existing rows in batches.** Write a background job that finds rows where the new column is NULL and updates them in small batches — perhaps 1,000 rows at a time — with brief pauses between batches to avoid overwhelming the database with write load. Do not run a single UPDATE that touches all 100 million rows at once; that would create massive replication lag and lock contention. Monitor the backfill progress and estimate when it will complete. This step can take hours or days depending on table size.

**Step 4: Add a NOT NULL constraint with a default.** Once the backfill is complete and all rows have a value, add the NOT NULL constraint. In PostgreSQL 11+, you can do this by adding the constraint as NOT VALID first, which skips the row-level validation and only validates new rows. Then run VALIDATE CONSTRAINT in a separate step, which does the validation with a weaker lock that does not block reads. In MySQL, if you are using online DDL or gh-ost (discussed below), this step can be done without blocking.

**Step 5: Deploy code that requires the column.** Update the application code to treat the column as required and remove any code that handles the NULL case. The column is now fully mandatory.

### The gh-ost Tool

GitHub's engineers got tired of the ALTER TABLE locking problem and built a tool called gh-ost (GitHub's Online Schema Transmogrifier) to solve it. gh-ost is a trigger-free, online schema migration tool for MySQL that allows you to modify table schemas without locking the table or impacting production traffic.

The way gh-ost works is clever. Instead of directly altering the original table, it creates a ghost table — a new table with the desired new schema. It then reads the binary log (the stream of all writes that MySQL produces for replication) and applies those changes to the ghost table in real time, keeping the ghost table synchronized with the original table as production traffic continues. Simultaneously, it runs a background copy job that reads rows from the original table in chunks and copies them to the ghost table.

Once the background copy catches up with the real-time binary log applier (meaning the ghost table has all the data from the original table plus all the recent changes), gh-ost performs an atomic table swap. It locks both tables for just a fraction of a second, renames the original table to an archive name, and renames the ghost table to the original name. The lock window is typically less than a second — too fast for most application queries to notice. This is how GitHub was able to run schema migrations on tables with hundreds of millions of rows without impacting the developers using their platform.

### Backfilling 100 Million Rows Safely

When you need to backfill a large table, the naive approach — a single SQL UPDATE touching all rows — is almost always wrong in production. Here is why, and what to do instead.

A single UPDATE on 100 million rows creates a massive write operation that will hold locks on rows for an extended period, create enormous amounts of write-ahead log or binary log data that the replicas need to process, potentially cause replication lag to spike to minutes or hours, and consume large amounts of I/O bandwidth that application queries also need.

The safe approach is to batch the backfill. Divide the rows into chunks based on their primary key. Update chunk by chunk — perhaps rows with ID 1 through 1,000, then rows with ID 1,001 through 2,000, and so on. Between each chunk, pause briefly (even just 10 milliseconds) to let the database replicate the changes and let application queries proceed. Monitor replication lag, and automatically slow down or pause the backfill if lag exceeds your threshold (perhaps 5 seconds of lag).

A production-grade backfill job looks something like this in pseudocode: fetch the minimum and maximum ID in the table, then iterate through the range in chunks, running UPDATE WHERE id BETWEEN chunk_start AND chunk_end AND new_column IS NULL, then sleeping briefly, then checking replication lag, then proceeding to the next chunk. Log progress every N chunks. Build a mechanism to pause and resume the job without losing your place.

Twitter built a system called Manhattan partly to handle exactly this kind of large-scale data backfill problem when migrating their storage layer. The key insight they applied was that backfills need to be treated as long-running jobs with explicit progress tracking, rate limiting, and health checks — not as one-shot scripts.

```
Safe Batch Backfill Process

Start                          Backfill Job
  |                                |
  v                                v
Fetch min/max IDs            Read chunk of rows (1k at a time)
  |                                |
  v                                v
Set chunk_size = 1000        Update rows where new_col IS NULL
  |                                |
  v                                v
chunk = min_id          -->  Check replication lag
                                   |
                         lag > 5s? |
                             Yes --+---> Wait, then retry
                             No  -------> Sleep 10ms
                                   |
                                   v
                         chunk += chunk_size
                                   |
                         chunk > max_id? --> Done!
```

### Intern to Staff: How Understanding Grows

**Intern level:** Runs ALTER TABLE directly. Learns about table locking the hard way, usually during their first production incident.

**Junior (L3) level:** Knows to run schema changes during low-traffic windows. Uses nullable columns before adding constraints.

**Mid-level (L4) level:** Uses tools like gh-ost or Flyway. Writes batch backfill scripts with simple rate limiting.

**Senior (L5) level:** Designs the complete multi-step migration plan before starting. Defines the monitoring dashboards that will track progress and detect problems. Calculates the estimated time and resource impact of the backfill before running it.

**Staff (L6) level:** Defines the organizational standards for schema migration approval. Ensures gh-ost or equivalent tooling is available and understood by all engineers. Reviews migration plans for any large or risky tables to ensure safety. May contribute to the tooling itself, as GitHub did when they built gh-ost and open-sourced it.

### Brainstorming Q&A

**Q: A candidate proposes doing the schema migration in a transaction to ensure consistency. Is that a good idea?**

Transactions are the right tool for ensuring that a set of related changes either all succeed or all fail together, and they are essential for maintaining data integrity in normal application code. But for large schema migrations, wrapping the operation in a transaction is often a bad idea, for a nuanced set of reasons. First, long-running transactions hold locks for the entire duration, which can block application queries for the full migration time. Second, if the migration modifies millions of rows, the transaction log (write-ahead log or undo log) becomes enormous, consuming disk space and memory. Third, if the transaction fails at step N of an N-step migration, you have to restart from zero, which may not be practical for a 30-minute operation. The better approach for large migrations is to use small transactions (one per batch), accept that the migration is not atomic at the table level, and rely on the idempotency of the migration operations to handle restarts safely. You design each batch operation so that it can be safely run again if it was partially applied — for example, using WHERE new_column IS NULL so that already-backfilled rows are never touched twice. The migration as a whole is not atomic, but each individual batch step is atomic, and the migration is designed to be resumable from any point.

**Q: How do you handle the case where a schema migration fails midway through a multi-hour backfill?**

This is one of the most important operational questions in database migration engineering. The answer has three parts. First, design the migration to be idempotent: each step should be safe to run multiple times without producing incorrect results. For a backfill, this means the UPDATE condition should include WHERE new_column IS NULL so that already-updated rows are never touched again. Second, track progress persistently: the backfill job should record its checkpoint (the last ID it successfully processed) in a durable location so that if it crashes or is killed, it can resume from where it left off rather than starting over. Third, implement health checks: the migration framework should continuously monitor key metrics like replication lag, error rates, and query latency, and automatically pause or stop the migration if any of these exceed safe thresholds. When a migration fails, the standard recovery procedure is to diagnose why it failed (was it a constraint violation? a connection error? a timeout?), fix the underlying cause, and restart the migration from the last checkpoint. Because the migration is idempotent and progress-tracked, resuming from the checkpoint gives you exactly the same result as if the migration had run continuously from the start.

---

## Part 4: The Dual-Write Pattern

### What Is Dual-Write?

The dual-write pattern is the workhorse technique for migrating data between two storage systems or two schemas while keeping both systems in sync during the transition. The idea is straightforward: during the migration period, every write operation goes to both the old system and the new system. Reads continue to come from the old system, which is trusted as the source of truth. The new system receives writes but is not yet trusted for reads.

This pattern solves a fundamental timing problem in data migration. When you start a migration, you need to backfill historical data from the old system to the new system. But while you are backfilling, new data is being written to the old system. If you backfill first and then switch over, you will miss all the writes that happened during the backfill. Dual-write solves this by ensuring that from the moment it is enabled, all new writes go to both systems, so you do not miss anything after dual-write starts.

### The Four-Stage Sequence

A complete dual-write migration follows four stages that progress the system from old-only to new-only.

**Stage 1 — Write old, read old:** This is the starting state. All writes go to the old system. All reads come from the old system. The new system does not exist yet or is empty.

**Stage 2 — Write both, read old:** Enable dual-write. Every write operation writes to both the old system and the new system. Start backfilling historical data from old to new. Reads still come from the old system. The new system is not yet trusted. During this stage, you can start doing verification reads from the new system (without trusting them) to check data quality.

**Stage 3 — Write both, read new (with shadow verification):** Once backfill is complete and you have verified that the new system has correct data, start routing a small percentage of reads to the new system. Compare the results against what the old system returns. Any discrepancies are logged and investigated. Gradually increase the percentage of reads going to the new system as confidence grows.

**Stage 4 — Write new, read new:** Once you have full confidence in the new system, stop writing to the old system and stop reading from it. The migration is complete. The old system can be decommissioned after a safety period.

### Shadow Mode: Reading Without Trusting

Shadow mode is a variant of the dual-write pattern that applies to the read path. In shadow mode, you send every read request to both the old and new systems simultaneously. You return the response from the old system to the user (because the old system is trusted). But you also capture the response from the new system and compare it to the old system's response in the background, logging any discrepancies.

Shadow mode is invaluable for verifying the correctness of a migration before committing to it. It lets you test the new system with 100% of real production traffic — including all the edge cases and unusual queries that you could never anticipate in a test suite — without any risk to the user experience if the new system returns incorrect results. The old system's response always wins as far as the user is concerned.

Airbnb used a version of this pattern extensively during their migration from a monolithic application to a service-oriented architecture. When they broke out individual services from the monolith, they would run both the monolith code path and the new service code path for the same request, compare results, and only trust the new service once the discrepancy rate had been below their threshold for a sustained period. This let them validate the new service against the full complexity of production traffic before putting user experience at risk.

```
Dual-Write Migration Stages

Stage 2: Dual-Write, Read Old
                    +--------------+
Write Request -->   | Application  | --> OLD DB (primary write)
                    |              | --> NEW DB (secondary write)
Read Request  -->   |              | <-- OLD DB (reads trusted)
                    +--------------+

Stage 3: Dual-Write, Shadow Read
                    +--------------+
Write Request -->   | Application  | --> OLD DB
                    |              | --> NEW DB
Read Request  -->   |              | <-- OLD DB (result returned to user)
                    |   compare!   | <-- NEW DB (result compared in background)
                    +--------------+
                         |
                    Log discrepancies
                    Alert if rate too high
```

### Handling Write Failures in Dual-Write

One subtle danger of dual-write is the case where the write to the old system succeeds but the write to the new system fails. If you allow this to happen silently, the two systems will drift out of sync, and when you eventually switch reads to the new system, some data will be missing.

There are a few approaches to this problem. The simplest is to treat a write failure to either system as a failure: the application returns an error to the user and neither write is committed. This is the safest approach from a consistency standpoint but requires that both systems be highly available, or else failures in the new system (which is presumably less battle-tested) start causing failures for users who were previously happy with just the old system.

A more nuanced approach uses an asynchronous reconciliation queue. If the write to the new system fails, the failure is logged to a queue. A background job processes the queue, retrying failed writes to the new system. Meanwhile, the write to the old system was committed and the user gets a successful response. The new system may be temporarily behind, but the queue ensures it eventually catches up. This approach is less consistent (there is a window where the two systems disagree) but more available (failures in the new system do not affect users). The parity verification job (discussed next) will catch any divergence that the reconciliation queue fails to repair.

### Parity Verification

Running alongside a dual-write migration, a parity verification job continuously spot-checks that the two systems have the same data. It randomly samples records from the old system, reads the corresponding record from the new system, and compares them field by field. If the mismatch rate is above a threshold, the migration is paused until the root cause is identified and fixed.

Parity verification is not a one-time check done at the end of the migration. It is a continuous process that runs throughout the entire dual-write period. This is because data can diverge due to many causes: race conditions in the dual-write logic, failed writes that were not properly reconciled, schema differences that cause data to be stored differently, and bugs in the data transformation code. Catching divergence early, while both systems are still being written to and the data set of interest is small, is much easier than discovering it at the end after you have attempted to switch reads.

### Intern to Staff: How Understanding Grows

**Intern level:** Writes a simple one-off script to copy data from one table to another.

**Junior (L3) level:** Understands that data copied once will become stale as new writes come in. Starts to understand the timing problem.

**Mid-level (L4) level:** Implements basic dual-write. Writes a comparison job to check parity. Can explain the four stages.

**Senior (L5) level:** Designs the full dual-write system with failure handling, retry queues, and continuous parity verification. Defines the acceptance criteria for moving between stages.

**Staff (L6) level:** Designs the framework that makes dual-write a standardized, well-understood pattern in the organization. Ensures that every team doing a storage migration uses the same tooling and the same acceptance criteria. Can identify situations where dual-write is not the right pattern and propose alternatives.

### Brainstorming Q&A

**Q: What is the trickiest operational challenge in running dual-write in production for months?**

The trickiest operational challenge is maintaining consistency in the presence of retries and idempotency. When a dual-write operation fails partway through — the write to the old system succeeded but the write to the new system timed out — the application typically retries the operation. If the retry is not carefully designed, you can end up with duplicate data in the new system (the first write that timed out may have actually landed, and then the retry writes a second copy). Or you can end up with the two systems having different values for the same record if the retry applied a different transformation. The solution requires designing every write operation to be idempotent: running the operation twice should produce the same result as running it once. For databases, this often means using an upsert (INSERT ... ON CONFLICT DO UPDATE) instead of a pure INSERT. For messaging systems, it means using deduplication IDs. For data transformation pipelines, it means ensuring that transforms are pure functions of their input. Getting idempotency right throughout a complex, months-long dual-write migration is genuinely difficult and is one of the primary sources of data quality problems in migration projects.

---

## Part 5: The Strangler Fig Pattern

### The Strangler Fig Tree

The strangler fig is a tropical plant that begins its life as a seed deposited in the canopy of an existing tree. Over years and decades, the fig grows roots down the outside of the host tree, slowly enveloping it. Eventually, the fig's roots reach the ground and it becomes self-supporting. The host tree, deprived of light and nutrients, dies and rots away. The fig continues to live, having replaced the host tree from the outside.

Martin Fowler coined this term as a metaphor for a software migration pattern where a new system is built incrementally around a legacy system. The new system intercepts incoming requests, handles the portions it has been built to handle, and proxies the remaining requests to the legacy system. Over time, the new system handles more and more of the request space. Eventually, it handles everything, and the legacy system can be decommissioned — the tree has been strangled.

The strangler fig pattern is particularly valuable for breaking up monolithic applications into microservices, for migrating legacy systems that cannot be easily rewritten all at once, and for changing the language or framework underlying a service.

### The Three Components

A strangler fig migration has three core components.

The first is a **proxy or facade**. This sits in front of both the legacy system and the new system. Every incoming request goes through the proxy first. The proxy inspects each request and decides: should this go to the legacy system or to the new system? Initially, the proxy routes 100% of traffic to the legacy system. As new capabilities are built in the new system, the proxy starts routing the corresponding requests to the new system instead.

The second is the **new system** being built incrementally. Instead of trying to rewrite the entire legacy system at once (the "big bang rewrite" approach, which has a terrible track record of failure), you build the new system one capability at a time. You pick the most well-defined, least complex capabilities first — ones where you can write the new system with high confidence and where errors will be most easily caught. You build those, route traffic to the new system for just those capabilities, verify they work, and then move on to the next capability.

The third is the **data synchronization layer**. Often the legacy system and the new system share the same database initially, which simplifies the migration. But sometimes the new system needs its own data store, which means you need a synchronization mechanism (often a form of the dual-write pattern) to keep data consistent during the transition.

### Airbnb's Monolith-to-Services Migration

Airbnb's engineering blog has documented their multi-year migration from a Rails monolith called "Monorail" to a service-oriented architecture. This is one of the best-documented examples of the strangler fig pattern in the industry.

Airbnb's approach was to identify service boundaries by looking at the most independently deployable parts of the monolith. Their first services extracted from the monolith were things like search and payments — capabilities with relatively clear interfaces and high business value from independent deployment. They built a service abstraction layer that allowed the monolith to call out to the new services via an internal API, instead of directly accessing the code or database. Over time, more and more of the monolith's behavior was delegated to services. The monolith became progressively smaller, until the core remaining pieces could be rewritten or retired.

The proxy in Airbnb's case was often not a network-level proxy but a code-level adapter: classes inside the monolith that used to directly implement a capability were replaced by classes that delegated to an external service. This kept the changes invisible to the rest of the monolith code, which continued to call the same interface as before.

```
Strangler Fig Pattern

Before Migration:
  Client --> Legacy Monolith --> Database

During Migration:
  Client --> Proxy/Facade --> Legacy Monolith --> Shared or Legacy DB
                    |
                    +--> New Service A --> New DB A
                    +--> New Service B --> New DB B

After Migration (Strangled):
  Client --> Proxy/Facade --> New Service A --> New DB A
             (simplified)--> New Service B --> New DB B
             (legacy removed)
```

### Parallel Operation and Verification

A key best practice in strangler fig migrations is to run the legacy system and the new system in parallel for a period, sending the same request to both and comparing responses. This is similar to the shadow mode described in the dual-write pattern. By running both systems for real production traffic and comparing their responses, you can identify subtle behavioral differences between the new system and the legacy system before routing users exclusively to the new system.

The comparison is not always exact — perhaps the legacy system has a bug that the new system intentionally does not replicate, or perhaps the formatting of timestamps is slightly different. You need to define what "correct parity" means for your specific migration and then measure against that definition. The important thing is to be explicit about what differences are acceptable and which ones indicate a real problem.

### Intern to Staff: How Understanding Grows

**Intern level:** Familiar with the concept of microservices but thinks of migration as a one-time rewrite event.

**Junior (L3) level:** Has participated in extracting one service from a monolith. Understands that the proxy is needed to avoid changing all callers at once.

**Mid-level (L4) level:** Can design the proxy layer and the service boundary for a specific capability. Understands the data synchronization challenge.

**Senior (L5) level:** Designs the full strangler fig plan for a significant portion of a monolith. Defines the sequencing of which capabilities to extract in which order and why. Runs shadow comparison and defines acceptance criteria.

**Staff (L6) level:** Defines the organization-wide approach to strangling a major legacy system. Ensures that all teams working on pieces of the migration are coordinated. Defines the criteria for decommissioning the legacy system. Manages the relationship with stakeholders who depend on the legacy system to understand impact and timing.

### Brainstorming Q&A

**Q: What are the dangers of a big-bang rewrite, and why is strangler fig usually preferable?**

A big-bang rewrite is the approach of throwing away the existing system entirely and building a complete replacement from scratch, then switching over to the new system in a single cutover event. This approach is deeply attractive to engineers because it means they can make clean architectural decisions without being constrained by legacy code. But it has a record of failure that is extraordinary even by the standards of difficult software projects. The dangers are numerous. First, the existing system, however ugly, has accumulated enormous behavioral complexity: edge case handling, regulatory compliance code, obscure customer-specific logic, error handling for situations that only occur once a year. None of this is documented. All of it will be missed in the rewrite, and the misses will only be discovered after the cutover, by users in production. Second, the rewrite takes much longer than anyone estimates, usually two to three times as long, which means the organization is running both systems in parallel for much longer than planned, paying for both. Third, during the rewrite period, the legacy system must continue to be maintained and enhanced, which slows the rewrite team and creates a moving target. The strangler fig approach avoids these dangers by continuously delivering value in small increments, by never having a big-bang cutover moment where everything is at risk simultaneously, and by running both systems side by side long enough to verify that the new system handles all the edge cases correctly before retiring the legacy system.

---

## Part 6: Feature-Flag-Driven Cutover

### What Is a Feature Flag in the Context of Migration?

A feature flag (also called a feature toggle or feature gate) is a configuration setting that controls whether a specific piece of behavior is active. In the context of migrations, feature flags are used to control traffic routing: what percentage of requests go to the old behavior versus the new behavior, and for which users or which request types.

Feature flags are the primary tool for managing the risk of a migration cutover. Instead of deploying a change to 100% of traffic all at once — a moment where a bug in the new behavior would immediately impact all users — you use a feature flag to deploy the change to a small percentage of traffic first, observe the results, and gradually increase the percentage as confidence grows.

### The 1% to 5% to 20% to 100% Ramp Pattern

The canonical ramp pattern for a migration cutover looks like this: start with 1% of traffic routed to the new behavior. Watch the metrics carefully for some period — often 10-30 minutes. If everything looks good, increase to 5%. Watch again. Increase to 20%. Watch again. Increase to 50%. Watch again. Increase to 100%.

The percentages and the observation windows between steps depend on several factors. How much traffic does your system handle? With very high traffic (millions of requests per minute), even 1% gives you thousands of data points per minute, so you can observe for a shorter time. With lower traffic, you may need to wait longer at each step to get statistical significance. How severe would a bug be? If the new behavior could cause data corruption, you want to ramp very slowly. If it is just a UI change that makes text slightly different, you can ramp faster.

The ramp should almost never be based purely on random sampling. You want to make sure that the 1% is a representative sample of your user population. Some implementations use consistent hashing on the user ID so that a given user always sees either the old behavior or the new behavior throughout the ramp (rather than sometimes seeing one and sometimes the other, which can be confusing and make it hard to get user reports about problems). Other implementations use geographic region, user cohort, or account age as the segmentation dimension.

### Rollback Triggers

The most important decision in a feature-flag-driven cutover is defining the rollback triggers before you start. A rollback trigger is a specific, measurable condition that, if observed, automatically or immediately causes the cutover to halt and reverse. Having these defined in advance means that when you are in the middle of a high-stress cutover situation and you see a metric going the wrong direction, you do not have to make a judgment call under pressure. The decision has already been made.

Common rollback triggers include: error rate on the new behavior path exceeds X% (where X is typically 2-5x the baseline error rate), latency at the 99th percentile increases by more than Y milliseconds, business metric (purchases, signups, completions) drops by more than Z%, or any rate of a previously unseen exception type.

The rollback mechanism itself needs to be fast and reliable. Reducing the feature flag percentage from 20% back to 0% should take effect within seconds, not minutes. This means the feature flag system needs to be able to push configuration changes to all servers quickly. Systems like LaunchDarkly, Split.io, or custom-built feature flag systems typically propagate changes in under a second using a combination of server-sent events and local caching.

### Measuring Parity

Before ramping a migration cutover all the way to 100%, you need to measure parity between the old and new behaviors across several dimensions.

**Functional parity:** Do the old and new behaviors produce the same results for the same inputs? For computational transformations, this can be checked exactly. For things like machine learning model outputs, exact parity may not be expected, but the distribution of outputs should be similar.

**Performance parity:** Is the new behavior as fast as the old behavior, or faster? Specifically, check latency percentiles (p50, p95, p99) and throughput. It is easy for a new behavior to be correct but much slower than expected.

**Resource usage parity:** Does the new behavior consume similar amounts of CPU, memory, network, and database connections? A new behavior that is correct and fast but uses 10x the database connections will cause problems at scale.

**Business metric parity:** This is the most important check. Do conversion rates, user engagement metrics, revenue metrics, and other business outcomes look the same (or better) under the new behavior? A migration that changes functional behavior but negatively impacts business outcomes is a migration that should not be completed.

### Real Example: Stripe's API Migration

Stripe is famous in the industry for maintaining backward compatibility across API versions for an extraordinary period. Stripe has API clients running version 2014-06-17 (yes, from 2014) that still work correctly against their current infrastructure. This is not an accident — it is a deliberate architectural choice supported by a sophisticated feature-flag-like system.

When Stripe introduces a change to API behavior, they assign it a version date. API clients send their version date in every request. Stripe's infrastructure looks at the version date and applies the appropriate behavior transformation for that version, even if the underlying data model has changed significantly in the meantime. This versioning system is essentially a feature flag system where the "flag" is the client's declared API version, and the "behavior" is the transformation applied to request and response data.

The engineering cost of this approach is significant: the compatibility layer (which Stripe calls the API versioning layer) must be maintained and extended with every new behavioral change. But the business benefit — zero forced client upgrades, zero breakage of existing integrations — has been a major competitive advantage for Stripe in the payments market.

```
Feature Flag Ramp Pattern

Time --------------------------------------------------------------------->

Traffic   1%    5%       20%            50%              100%
to new    |     |        |              |                |
behavior: +-----+--------+--------------+----------------+---------------->
          |     |        |              |                |
          watch watch    watch          watch            done!
          10min 15min    30min          1hr

If at any point:
  - Error rate > 2x baseline ---------> ROLLBACK to 0%
  - p99 latency +100ms ----------------> ROLLBACK to 0%
  - Business metric drops >2% ---------> ROLLBACK to 0%
```

### Intern to Staff: How Understanding Grows

**Intern level:** Knows feature flags exist. May use them to hide incomplete features during development.

**Junior (L3) level:** Uses feature flags for cutover. Does manual observation between ramp steps.

**Mid-level (L4) level:** Defines rollback triggers before starting. Automates some of the parity measurement. Uses consistent user-level hashing for the flag.

**Senior (L5) level:** Designs the full ramp plan including what metrics to monitor, what rollback triggers to set, and how long to wait at each step. Integrates the feature flag with automated rollback systems.

**Staff (L6) level:** Designs the feature flag infrastructure for the organization. Defines standards for how migrations should be controlled via flags. May build automated ramping systems that increase the percentage automatically when metrics look good and pause when they do not.

### Brainstorming Q&A

**Q: Should feature flags for migrations be stored in code or in an external configuration system? What are the tradeoffs?**

This is a nuanced architectural question. Storing feature flags in code (hardcoded or in a config file in the repository) has the advantage of traceability: you can see in git history exactly when the flag value changed and who changed it. But it has the critical disadvantage of requiring a deployment to change the flag value. During a cutover, you want to be able to adjust the flag value — ramp it up, ramp it back down — in seconds, not minutes. A deployment-based flag change takes however long your deployment pipeline takes (often 5-30 minutes), which is too slow for rapid response to a production problem. External configuration systems like LaunchDarkly, Consul, or a custom-built key-value store allow flag values to be changed in real time without a deployment. The flag value is fetched at request time (with local caching to avoid latency) and can be updated globally in under a second. The disadvantage is that changes to flag values are less traceable unless you have explicit audit logging. For migrations specifically, the right answer is almost always an external configuration system, because the ability to rapidly roll back is more important than the convenience of code-based configuration. The audit trail problem can be solved with explicit logging in the flag management tool.

---

## Part 7: API Migrations

### The Difference Between Backward-Compatible and Breaking Changes

Not all API changes are equal. The most important distinction in API migration is between backward-compatible changes and breaking changes.

A **backward-compatible change** is one where existing clients continue to work correctly without any modifications. Adding a new optional field to a response is backward-compatible: old clients simply ignore the new field. Adding a new optional parameter to a request is backward-compatible: old clients send the same request as before, which still works. Adding a new endpoint is backward-compatible: old clients do not know about it and do not call it.

A **breaking change** is one where existing clients will fail or produce incorrect results without modification. Removing a field from a response is a breaking change: clients that depend on that field will get null or an error. Changing the type of a field from a string to an integer is a breaking change. Changing the meaning of a field — even if it has the same name and type — is a breaking change if clients are relying on the old meaning.

The discipline of backward-compatible API design is essentially the discipline of making changes that only add, never remove or modify. The expand-contract pattern applied to APIs means: add the new field/endpoint/behavior (expand), wait for clients to migrate to using the new one (migrate), and then remove the old one (contract). The challenge is that the contract phase requires coordinating with all the clients, which may be outside your control.

### The Deprecation Lifecycle

When you need to remove or significantly change an API behavior, the responsible approach is a structured deprecation lifecycle rather than an abrupt removal.

The lifecycle typically looks like this: First, introduce the replacement API (the new field, the new endpoint, the new behavior). Then announce deprecation of the old API with a clear timeline. Send deprecation notices to API clients — often via response headers (Deprecation: true, Sunset: [date]) or via developer portal notifications or via email to registered API users. Give clients enough time to migrate — for external APIs with many clients, this is often six months to a year. Monitor usage of the deprecated API to track migration progress. At the sunset date, remove the deprecated API.

The sunset date should be treated as a hard commitment, not a soft suggestion. If you extend the sunset deadline repeatedly because "some clients haven't migrated yet," you undermine the entire deprecation process and clients learn that they do not actually need to migrate. The consequence is that removing old APIs becomes impossible, and you end up in a situation where you are maintaining dozens of deprecated API versions indefinitely — exactly Stripe's situation, except Stripe does it by design, whereas most organizations do it by accident.

### Stripe's 14-Year Backward Compatibility

Stripe's API backward compatibility is both admired and studied as an extreme case of the "never break clients" philosophy. Since 2011, Stripe has never removed a field from an API response without going through an extraordinary process that may take years. Their versioning system allows every API client to run at its original version date indefinitely, and Stripe maintains transformation logic that converts between the current internal data model and whatever the client's version expected to see.

The engineering cost of this system is substantial. Every API change requires updating the versioning layer. Tests must cover every active API version. New engineers must understand the versioning model before they can safely make API changes. But the business argument for this investment is compelling: Stripe's developer experience reputation is a major part of their competitive moat. The fact that a startup that integrated with Stripe in 2014 can still run that same integration code today without modification is a genuine differentiator in the payments market.

Not every organization should aim for Stripe-level backward compatibility. But the principle — that breaking client integrations has a real cost that should be measured and minimized — is universally applicable.

### API Versioning Strategies

There are three common approaches to API versioning, each with different tradeoffs.

**URL versioning** puts the version number in the URL path: /v1/users, /v2/users. This is the most visible and explicit approach. It is easy to see which version a client is using. But it leads to URL duplication and can encourage "just add a new version" thinking rather than careful backward-compatible design.

**Header versioning** puts the version number in a request header: API-Version: 2024-01-15. This is how Stripe does it. The URL stays stable across versions. Clients explicitly declare what behavior they expect. It is cleaner from a REST perspective but requires more sophistication to implement on the server side.

**Content negotiation** uses the Accept header to request different response formats: Accept: application/vnd.myapi.v2+json. This is the most REST-pure approach but is the least common in practice because it is complex to implement and unusual for clients to use correctly.

For internal APIs between services, many organizations skip formal versioning entirely and rely on the fact that they control all the clients, using the expand-contract pattern and coordinated deployments instead.

### Intern to Staff: How Understanding Grows

**Intern level:** Knows that changing an API can break clients. Learns to add new fields rather than changing old ones.

**Junior (L3) level:** Can implement an API deprecation with a sunset date. Knows how to add deprecation headers to responses.

**Mid-level (L4) level:** Designs new APIs with versioning from the start. Manages the deprecation of old APIs with client communication.

**Senior (L5) level:** Defines the API versioning strategy for a service. Designs APIs that are extensible enough to accommodate future changes without breaking clients. Tracks client migration progress during deprecation periods.

**Staff (L6) level:** Defines the API design and deprecation standards for the organization. Designs the tooling that enforces backward compatibility (linting tools that detect breaking changes). Manages the relationship with external developer communities during deprecation cycles. May make the strategic decision to accept a breaking change (with appropriate client coordination) when the cost of maintaining backward compatibility exceeds the migration cost.

### Brainstorming Q&A

**Q: How do you handle the case where a security vulnerability requires an emergency breaking API change?**

Emergency security-driven API changes are the exception that proves the rule about careful deprecation processes. If a security vulnerability in your current API is being actively exploited and the only fix requires a breaking change, the usual deprecation timeline goes out the window. The approach in this situation has several components. First, triage the severity: can the vulnerability be mitigated temporarily by other means (rate limiting, IP blocking, additional authentication) while a backward-compatible fix is developed? If so, do that first to buy time. Second, if a breaking change is truly unavoidable, treat the migration as an emergency and provide maximum support to clients: direct communication to affected clients, a migration guide, and potentially migration assistance. Third, consider a rapid migration window — giving clients 72 hours or one week to migrate, with the understanding that this is an emergency, not a normal deprecation. Fourth, maintain the old vulnerable version for as short a time as possible, ideally removing it as soon as client migration is measured to be complete or as soon as the migration deadline passes. Security incidents are one of the few cases where forcing a breaking change on clients is justified, but the way you handle the communication and support during that forced migration will significantly affect your credibility with clients long-term.

**Q: A junior engineer proposes adding a v3 of your API to avoid making a breaking change to v2. The v3 would have the same endpoints as v2 but with different response formats. Is this a good approach?**

Adding a new API version to avoid a breaking change in an existing version is sometimes the right call, but it is often a mistake when done reflexively. The problem with adding a new version every time you want to make a change is that you quickly end up maintaining many versions simultaneously — v1, v2, v3, v4 — each of which needs to be tested, documented, monitored, and supported. The maintenance burden grows linearly with each version you add. A better first question to ask is: can we make the desired change in a backward-compatible way within v2? Many changes that initially seem like they require a new version can be accomplished with careful use of optional fields, default values, or content negotiation within the same version. Only when the change is truly a breaking semantic shift — where keeping v2 clients working while providing v3 behavior simultaneously would require fundamentally incompatible logic — should you introduce a new version. And when you do introduce v3, you should have a concrete plan for sunsetting v2 by a specific date, not treating v2 as indefinitely maintained. The discipline of forcing yourself to be backward-compatible first will make your API more robust and easier to maintain in the long run.

---

## Part 8: Infrastructure Migrations

### The Most Disruptive Kind of Migration

Infrastructure migrations are the most disruptive type of migration because they change the fundamental operational characteristics of a system: how data is stored and retrieved, how requests are routed and load-balanced, how failures are detected and handled, and how capacity scales. Unlike data migrations (which change what is stored) or code migrations (which change what software does), infrastructure migrations change the entire platform that everything else runs on. The blast radius of something going wrong is correspondingly much larger.

Infrastructure migrations also tend to be the longest-running. A data migration might take days or weeks. An infrastructure migration — moving from bare metal to cloud, changing database engines, migrating between cloud regions — often takes months to years for large organizations.

### Bare Metal to Cloud Migration

The migration from owned, on-premises servers (bare metal) to cloud providers is one of the defining infrastructure migrations of the past decade. Thousands of companies have gone through it, and the patterns have become reasonably well understood.

The fundamental approach is lift-and-shift first, then optimize. In the lift-and-shift phase, you move workloads to the cloud without changing how they work — running the same software on cloud VMs that you were running on physical servers. This is not the cloud's native way of running things (containerized, auto-scaling, serverless) but it minimizes risk by changing only one thing at a time: where the compute runs, not how it runs. Once the workload is running in the cloud, you can iterate on cloud-native optimizations — moving to managed services, enabling auto-scaling, using cloud-native storage — as separate, lower-risk steps.

The trickiest part of bare-metal-to-cloud migration is network connectivity and latency. Physical data centers often have 10 Gigabit or 100 Gigabit internal networking. Cloud providers have fast internal networking, but accessing data across regions or from on-premises systems adds latency. Hybrid periods, where some services are in the cloud and some are still on-premises, can experience unexpected latency increases on cross-environment calls that were previously local.

### Region Migrations

Moving a service from one cloud region to another is often necessary when expanding geographic coverage, optimizing latency for a new user base, or meeting data residency requirements (regulatory mandates that certain user data must remain within a particular country or region).

The technical challenge of region migration is that data stored in one region must be replicated to the new region before traffic can be moved. For databases, this involves setting up cross-region replication, waiting for the replica to catch up, and then doing a controlled failover. For caches, you rebuild them from the source of truth in the new region. For object storage, you use cross-region replication provided by the cloud vendor.

The most critical moment in a region migration is the failover: the moment you stop accepting writes in the old region and start accepting them in the new region. During this cutover window, you need to ensure that no writes are lost (which means draining all in-flight writes from the old region before cutting over) and that all replicas in the new region are fully caught up. The window is typically very short — seconds to minutes — but must be carefully planned and rehearsed.

### Database Engine Changes

Changing database engines — for example, migrating from MySQL to PostgreSQL, or from a relational database to Cassandra, or from a single-node database to a distributed database — is one of the most complex and risky infrastructure migrations that an engineering team can undertake. The reason is that different database engines have different data models, different consistency guarantees, different query languages, and different operational characteristics.

The GitHub migration from MySQL to Vitess (a MySQL-compatible distributed database) is a landmark case study in database engine migration done well. GitHub needed to scale their MySQL infrastructure beyond what a single primary-replica setup could handle. Vitess, originally built by YouTube, provides horizontal sharding on top of MySQL while maintaining MySQL wire-protocol compatibility. The compatibility meant that most application code did not need to change — it still sent MySQL queries — but the underlying execution was now distributed across multiple shards.

GitHub's migration used a combination of the dual-write pattern and the strangler fig pattern. They set up Vitess clusters alongside their existing MySQL clusters. They migrated tables one at a time — starting with lower-risk tables and working toward the most critical ones. For each table migration, they used gh-ost (which they had also built) to copy data to Vitess, kept the two in sync using dual-write, and gradually shifted reads to Vitess. The entire migration took years and required extraordinary coordination across the engineering organization.

```
Infrastructure Migration: Bare Metal to Cloud

Phase 1: Hybrid Setup
  Old DC --> Application Servers --> Database (on-prem)
  Cloud  --> Application Servers --> Database Replica (cloud)
  (both run in parallel, old DC is primary)

Phase 2: Read Migration
  Old DC --> Application Servers --> Database (on-prem, writes)
  Cloud  --> Application Servers --> Database Replica (reads)
  (gradually shift reads to cloud replica)

Phase 3: Write Cutover
  Cloud --> Application Servers --> Database (cloud primary)
  (old DC demoted, new region is primary)

Phase 4: Decommission
  Cloud --> Application Servers --> Database (cloud only)
  (old DC shut down)
```

### Intern to Staff: How Understanding Grows

**Intern level:** Knows that different infrastructure options exist. Has not participated in an infrastructure migration.

**Junior (L3) level:** Has participated in one infrastructure migration. Knows how to set up cross-region replication. Has run runbooks during a migration.

**Mid-level (L4) level:** Can plan a specific infrastructure migration for a bounded service. Understands the replication lag implications and plans the failover window accordingly.

**Senior (L5) level:** Leads an infrastructure migration for a significant service. Designs the detailed cutover plan with rollback options. Conducts pre-migration testing and capacity planning in the new environment.

**Staff (L6) level:** Leads infrastructure migrations that span multiple services or are organizationally complex. Defines the migration strategy and sequencing. Manages vendor relationships (cloud providers, database vendors). Ensures that infrastructure migrations are treated as major engineering programs with appropriate project management, stakeholder communication, and risk management.

### Brainstorming Q&A

**Q: How would you migrate a PostgreSQL database to Cassandra for a service that handles 100,000 writes per second? Where do you start?**

A migration from PostgreSQL to Cassandra is particularly challenging because these are fundamentally different data models: PostgreSQL is relational with strong consistency and ACID transactions, while Cassandra is a wide-column store with eventual consistency and a query model that is driven by access patterns rather than normalization. Before writing a single line of migration code, you need to understand why you are making this change. Is it for write throughput scalability? For geographic distribution? For availability during partition events? The answer determines which Cassandra features you are relying on and what consistency tradeoffs you are accepting. With that understood, the first step is data modeling: you need to redesign your Cassandra tables from scratch based on your read and write access patterns, not simply port the relational schema. Cassandra tables are denormalized and query-driven. Then you apply the dual-write pattern: write to both PostgreSQL and Cassandra simultaneously, backfill historical data to Cassandra, run parity verification to confirm data integrity. At 100,000 writes per second, you need to design the Cassandra schema carefully to avoid hotspots (partition keys that concentrate writes on a single node). The dual-write period also lets you validate Cassandra's operational characteristics — latency, replication behavior, compaction impact — under real production load before you cut over reads. The most important thing to tell this team is that the performance and correctness validation in the dual-write period needs to be thorough, because rolling back after switching reads at this write rate would be extremely complex.

---

## Part 9: The Rollback Protocol

### Design Rollback Before You Design the Migration

The most important principle in the rollback protocol is this: you should fully understand and document how to rollback a migration before you start executing it. This is counterintuitive. Most people think about rollback after something goes wrong. But designing rollback after a migration has started — especially after something has gone wrong — is exactly the wrong time to be thinking about it. You are under pressure, you may not have time to reason carefully, and you are working with a system that is already in an intermediate state.

When you design a migration plan, the rollback plan should be right there alongside it, as a first-class artifact. For every step in the migration, ask: if this step goes wrong, what is the rollback step? Is the rollback step safe to execute? Does it restore the system to the pre-step state, or does it leave it in a different intermediate state? What is the rollback step's rollback?

Some changes are naturally reversible. Adding a column can be reversed by dropping the column. Enabling a feature flag can be reversed by disabling it. Setting up a replica can be reversed by tearing it down. Other changes are much harder to reverse. Dropping a column is hard to reverse if you have already lost the data. Executing a database migration that deleted rows is hard to reverse if you did not back them up. Switching a payment processor and processing transactions through the new one is hard to reverse because you cannot un-process a transaction.

For irreversible changes, the rollback protocol involves either preventing the change from being executed until you are confident it is correct (using extensive shadow mode and parity verification before committing) or having a forward-only recovery path (instead of rolling back, you fix the problem by going forward to a correct state). Forward-only recovery requires that you fully understand what "a correct state" looks like and can get there from wherever the migration is at any given moment.

### Rollback Triggers

Just as with feature flag cutovers, rollback triggers for migrations should be predefined before the migration starts. They are the specific conditions under which rollback is initiated.

For database migrations, rollback triggers might include: replication lag exceeding 30 seconds for more than 5 minutes, error rate on writes exceeding 1%, any detected data inconsistency in parity verification, or p99 write latency increasing by more than 100ms.

For infrastructure migrations, rollback triggers might include: health check failure rate exceeding 0.1%, request error rate increasing by more than 2x baseline, or any complete failure of a critical dependency in the new environment.

The triggers should be objective and measurable — not "someone thinks something looks wrong" but "metric X is above threshold Y for duration Z." This prevents both under-reaction (ignoring a real problem because no one wants to call a rollback) and over-reaction (rolling back on noise that was not actually a problem).

### Rollback Drills

A rollback plan that has never been tested is a rollback plan that will not work when you need it. Rollback drills — practicing the rollback procedure before the migration begins — are one of the most valuable investments a migration team can make.

A rollback drill involves standing up the migration in a test environment (or a staging environment that mirrors production as closely as possible), executing the first few steps of the migration, and then intentionally triggering the rollback. Can you actually rollback? Does the rollback restore the system to its pre-migration state? How long does it take? Are there any steps in the rollback that are unclear or ambiguous? Are there any steps that require manual intervention?

Rollback drills also reveal implicit dependencies that were not considered in the migration plan. Perhaps rolling back a feature flag change requires restarting a service that has the flag value cached in memory. Perhaps rolling back a database schema change requires running a second migration to restore the old schema. These dependencies are much better to discover in a drill than in a production rollback.

### The GitHub Incident: When Rollback Was Not Simple

In 2012, GitHub experienced one of its most significant outages. A MySQL database failover during a high-traffic period triggered a cascade of issues that eventually led to data inconsistency across their replica set. The details are extensively documented in their engineering blog.

One of the lessons GitHub documented was the importance of having rollback procedures that work even when the system is in an inconsistent state. In their case, the inconsistency was discovered after the failover had been in progress for some time, which made rolling back to the pre-failover state complex. They had to reason carefully about what data had been written where, what could be replayed, and what was genuinely lost.

The lesson they drew from this, and which influenced their subsequent migration tooling (including gh-ost), was that migrations need to maintain a clear audit trail of every operation performed, so that in a recovery situation, you can reason precisely about the system's state at any point in time.

```
Rollback Protocol Structure

Migration Step N                    Rollback Step N
----------------                    ----------------
Add column 'phone'      <------->   DROP COLUMN phone
Enable dual-write       <------->   Disable dual-write, verify single write
Shift 20% reads         <------->   Flag: 0%, shift reads back to old
Backfill 50M rows       <------->   Truncate new column (idempotent re-run)
Add NOT NULL constraint <------->   DROP CONSTRAINT (harder, needs data check)

Key Rule: If rollback of step N creates a NEW intermediate state,
          that state must ALSO have a defined rollback path.
```

### Intern to Staff: How Understanding Grows

**Intern level:** Thinks about rollback as something that happens when a deployment fails — just redeploy the old version.

**Junior (L3) level:** Knows that database migrations are harder to rollback than code deployments. Keeps backup of affected rows before modifying them.

**Mid-level (L4) level:** Designs rollback steps for each migration step. Knows which operations are reversible and which are not. Runs a test of the rollback in a staging environment.

**Senior (L5) level:** Defines the full rollback protocol before migration starts. Conducts rollback drills. Defines rollback triggers. Has a communication plan for who to notify when a rollback is triggered.

**Staff (L6) level:** Ensures rollback protocols are a required part of every migration plan in the organization. Reviews rollback plans for major migrations. Has personally been involved in complex production rollbacks and brings that experience to bear in reviewing others' plans. Knows when to override the rollback triggers (e.g., when the cost of rolling back is higher than the cost of proceeding with a known issue) and can make those judgment calls under pressure.

### Brainstorming Q&A

**Q: How would you handle a migration where the rollback is theoretically possible but would take 12 hours? Is that a valid rollback plan?**

A 12-hour rollback is technically a rollback but operationally it means you have almost no rollback capability during a real incident. If something goes wrong and the rollback takes 12 hours, you have 12 hours of customer impact during the rollback. For any customer-facing service with real availability requirements, this is not an acceptable rollback plan. There are two responses to this situation. The first is to redesign the migration so that the rollback is faster. Often a slow rollback is a symptom of an insufficiently phased migration. If you have broken the migration into smaller steps, the rollback of each step should be proportionally smaller and faster. The second response is to reclassify the migration as a forward-only migration and design a forward-only recovery path instead. If you go this route, you need to be extremely confident in the migration before executing it — your shadow mode and parity verification period needs to be much longer, your rollback triggers need to be positioned earlier in the process (before you reach the point of no return), and your monitoring during the migration needs to be extremely sensitive. A staff engineer reviewing a migration plan that includes a 12-hour rollback would push back strongly and ask the team to go back and redesign either the migration phasing or the recovery strategy.

---

## Part 10: Staff Engineer Migration Leadership

### Why Migrations Are a Leadership Problem

By the time a migration is complex enough to need a staff engineer's involvement, it has typically grown beyond what any single team can execute on its own. It involves multiple services, multiple teams, dependencies on external partners, business stakeholder requirements, and coordination with operations and on-call rotations. At this scale, the migration is not primarily a technical problem — it is a coordination, communication, and incentive problem.

Staff engineers leading major migrations spend a surprisingly large fraction of their time not writing code or designing systems, but rather: writing migration proposals and getting alignment, running coordination meetings across teams, tracking progress via metrics and status updates, managing the escalation of blockers, communicating status to leadership, and enforcing sunset deadlines on teams that have not migrated.

### Multi-Team Coordination

A migration that requires multiple teams to change their services or their calling patterns is a migration with coordination risk — the possibility that one team's delay or mistake blocks another team's progress. The staff engineer leading the migration needs to make the dependencies explicit and manage them actively.

The standard tool for this is a migration tracking document that lists every team involved, what they need to do, by when, and their current status. This document is reviewed in a weekly coordination meeting. Teams that are behind schedule are identified early and given support (engineering help, clarification, relaxed deadlines on low-priority items to make room for the migration work). Teams that are blocked by dependencies on other teams are unblocked through explicit escalation.

The staff engineer's superpower in multi-team coordination is their cross-team visibility. They can see that Team A is blocked waiting on Team B's library change, and they can go directly to Team B's manager to get that change prioritized. They can see that three teams have the same question about how to handle a specific edge case, and they can write a canonical answer that unblocks all three. They can see that a migration is systematically slowing because teams are underestimating the effort, and they can escalate to leadership for resourcing adjustments before the deadline is missed.

### Setting Sunset Deadlines That Stick

Sunset deadlines are the single most important governance tool for migrations. Without a hard sunset date, migrations will not complete. Teams that are not mandated to complete a migration by a specific date will always find higher-priority work.

For the sunset deadline to be credible, it needs enforcement. Enforcement typically means: after the sunset date, the old behavior is removed and teams that have not migrated will experience failures. This is uncomfortable, and there will be pressure to extend the deadline for teams that are behind. The staff engineer leading the migration needs to be the person who holds the line.

There are some cases where an extension is genuinely warranted — a team is behind because of circumstances truly outside their control, or because the migration turned out to have an unexpected complexity that was not foreseeable at the outset. But extensions should be exceptions requiring explicit justification, not the default response to any team that asks.

Before the sunset deadline, the staff engineer should provide: clear communication of the deadline many weeks in advance, migration guides that reduce the effort required, office hours or embedded engineering help for teams that are struggling, and escalation of any systemic blockers (library dependencies, unclear specifications) that are affecting many teams. After the deadline, they need to follow through on the enforcement.

### Tracking Migration Progress

Progress tracking for migrations is more complex than tracking a normal software project because the "units of work" are distributed across many teams and services, and the definition of "done" for the migration overall depends on all of them completing their individual pieces.

Common tracking approaches include: a migration dashboard showing the percentage of services or endpoints that have migrated, the percentage of traffic going through the new behavior, and the number of teams that have completed versus not started; a weekly status email sent to all stakeholders; and automatic flagging when a service that was migrated regresses (starts using the old behavior again, perhaps due to a code rollback).

The metric that matters most depends on the migration type. For a data migration, it might be the percentage of rows that have been backfilled or the percentage of reads going to the new storage system. For an API migration, it might be the number of unique API clients still using the deprecated endpoint. For an infrastructure migration, it might be the percentage of traffic served by the new infrastructure.

### The Airbnb and Twitter Playbook

Twitter's migration to Manhattan, their in-house distributed key-value store, from a sharded MySQL setup is a case study in what large-scale infrastructure migration coordination looks like. Manhattan was built to handle Twitter's scale, but migrating hundreds of billions of rows of existing data from MySQL shards to Manhattan while continuing to serve hundreds of millions of active users required a migration program that ran for years and involved dozens of engineering teams.

The key coordination mechanisms Twitter used included: a dedicated migration engineering team whose sole job was to support other teams through the migration; a standardized migration library that every team used so that the migration mechanics were consistent and well-understood; weekly migration review meetings where blockers were escalated; and a migration dashboard visible to all of engineering and leadership.

The organizational lesson from Twitter Manhattan is that large migrations need dedicated resources — engineers who are not also responsible for feature work on their team, who can give the migration the sustained attention it requires. When migration is treated as a side project that teams do alongside their normal responsibilities, it almost always slips.

```
Staff Engineer Migration Coordination Model

                    Staff Engineer (Migration Lead)
                            |
            +---------------+---------------+
            |               |               |
        Team A           Team B          Team C
        (migrating)      (blocked!)      (done)
            |               |
            |          Escalate to
            |          Team B manager
            |               |
        Monitor          Unblock         Sunset
        progress         Team B          enforcement
            |               |               |
            +---------------+---------------+
                    Weekly coordination
                    Migration dashboard
                    Status reports to leadership
```

### Intern to Staff: How Understanding Grows

**Intern level:** Focused on their own task in the migration. Not aware of cross-team dependencies.

**Junior (L3) level:** Completes their team's piece of the migration. Communicates status to their team lead.

**Mid-level (L4) level:** Helps identify and communicate cross-team dependencies within their immediate work area. Participates in migration coordination meetings.

**Senior (L5) level:** Can lead a migration that involves a few teams. Tracks progress, manages dependencies, and escalates blockers. Can define and enforce a sunset deadline for a small migration.

**Staff (L6) level:** Leads migrations that span many teams, involve significant organizational complexity, and run for months or years. Builds the coalition of support (from engineering leadership, product management, and affected teams) needed to sustain the migration to completion. Defines the organizational processes and tooling that make future migrations smoother. Makes the judgment calls that only someone with full cross-organizational visibility can make.

### Brainstorming Q&A

**Q: How do you handle a team that flatly refuses to migrate by the sunset deadline because they say the migration will break something important for their service?**

This is one of the most common and most challenging scenarios in large-scale migration leadership. The first step is to take the team's concern seriously and investigate it. Is there a real compatibility problem that the migration plan missed? Many migration blockers turn out to be legitimate: the migration did not account for an edge case that the resistant team's service relies on. In that case, you fix the migration plan to address the concern — and you thank the team for catching it, because they just prevented a production incident. But sometimes the concern is not legitimate: the team misunderstood the migration, or they have exaggerated the impact, or they are resistant simply because the migration requires effort they would rather spend elsewhere. In that case, you work through the technical details with them to demonstrate that their concern does not actually apply, and you re-establish the deadline. If the team continues to refuse and you are confident the concern is not technically valid, this is a management escalation: you bring in your manager and the resistant team's manager and make the organizational decision at a level where it can be resolved. The migration deadline represents a commitment made by the organization, and one team's resistance cannot unilaterally override it. The key thing to document throughout this process is your evidence: technical analysis showing the migration is safe, the investigation of the team's specific concern and why it is or is not valid, and the escalation chain. This documentation protects everyone and ensures the decision is made based on facts rather than organizational politics.

**Q: A migration has been running for 18 months and is 80% complete. Leadership is asking why it is not done. What do you say?**

This is a real conversation that staff engineers have, and the answer requires honesty about both what has been accomplished and why the remaining 20% is taking so long. The first thing to explain is why the last 20% of a migration often takes disproportionately long: the last 20% typically consists of the hardest cases — services with the most complex dependencies, teams with the least capacity, or technical edge cases that were not anticipated in the original plan. The 80/20 rule applies strongly to migrations. The second thing to explain is what specific blockers are in the way and what is being done to clear them. Are some of the remaining services genuinely complex? Do some teams need additional engineering resources? Is there a technical problem that requires a rethink of part of the migration approach? Third, provide a revised, credible completion date with the specific blockers mapped to specific interventions. "We will complete the remaining 20% by Q3 because we have identified the 5 remaining blockers, we have allocated engineers to help the 3 teams that are under-resourced, and we have solved the technical edge case that was blocking 2 of the services." This conversation is also an opportunity to propose expediting mechanisms: can the sunset deadline be made harder to create urgency? Can engineering resources be temporarily reallocated from lower-priority work? Leadership asking why a migration is not done is, in part, a signal that they are willing to prioritize it — use that attention to unlock the resources you need.

---

## Part 11: Interview Application — L5 vs L6 Calibration

### What the Interviewer Is Testing

When a system design interview question touches on migrations or safe changes, the interviewer is testing several things simultaneously. They want to know whether you reflexively reach for unsafe patterns (maintenance windows, big-bang rewrites, unconstrained ALTER TABLE) or whether you instinctively apply safe migration patterns. They want to know whether you think about rollback as a first-class concern or as an afterthought. They want to know whether you can speak to the organizational coordination challenges of migrations, not just the technical ones. And at L6, they want to know whether you can identify the non-obvious risks in a migration plan and propose monitoring and validation strategies that will catch problems early.

Migrations questions often appear in disguise in system design interviews. You might be asked "how would you migrate a monolithic user service to a distributed one?" or "how would you add a new mandatory field to the database schema without downtime?" or "how would you change the API contract for this service in a way that supports both old and new clients?" These are all migration questions, and recognizing them as such is the first step to a strong answer.

### The L5 Answer Pattern

An L5 answer to a migration question will typically include: identification of the migration type (data/code/infrastructure), a phased approach with distinct steps, some attention to rollback, and consideration of the key risks. The L5 candidate will name specific patterns (expand-contract, dual-write, feature flags) and apply them correctly. They will think about the technical implementation details: how to batch a backfill, how to set up a database replica, how to write an API versioning layer.

An L5 answer might look like this for "how would you add a NOT NULL column to a table with 100M rows without downtime?": "First, I would add the column as nullable — that is a fast metadata operation. Then I would deploy code that writes the new column for all new rows. Then I would run a batch backfill job to populate the column for existing rows, processing maybe 1,000 rows at a time with pauses between batches to avoid overwhelming replication. Once the backfill is complete, I would add the NOT NULL constraint. I would use gh-ost or online DDL to avoid locking the table. And I would monitor replication lag throughout the backfill to make sure I am not causing performance problems."

This is a solid answer. It covers the key steps, names the right tool, and thinks about operational impact.

### The L6 Answer Pattern

An L6 answer builds on the L5 foundation but adds several layers. It questions the assumptions in the question (do we really need NOT NULL? could a default value work instead? is 100M rows in this table a sign of a data modeling problem?). It thinks about organizational coordination (who else needs to be involved? what teams does this affect? when is the right time to run the migration given the release schedule?). It designs the observability before discussing the migration steps (what metrics will tell us the migration is healthy? what is the definition of success?). It addresses rollback as a first-class concern (can we roll back each step? what is our rollback trigger?). And it considers second-order effects (what happens to caches that depend on this column? what happens to analytics pipelines that export this table? what happens to the ORM layer that maps this table?).

An L6 answer might extend the L5 answer above with: "Before I start, I want to make sure we have monitoring set up for replication lag, write error rates, and p99 write latency so we can pause the migration if anything goes sideways. I also want to confirm that our ORM and analytics pipeline are prepared to handle the new column — if they are doing SELECT * they will start getting the new column in results, and if they are not nullable-aware they might choke. For rollback, the easy rollback is at any point before we add the NOT NULL constraint — we just drop the column. But after we add the constraint, rolling back means dropping the constraint, which requires a second schema change. So I want to make sure we are very confident before we move to that step. I would also think about whether there is a maintenance window that makes this safer, even if we are not requiring zero-downtime — a Sunday morning at 3am Eastern reduces the blast radius if something goes wrong."

### Handling the "Just Use Maintenance Mode" Trap

Some interviews will test whether you reflexively say "just use a maintenance window" or whether you instinctively reach for zero-downtime approaches. The right response to "our service has very low traffic at night — why not just use a maintenance window?" is nuanced, not an absolute rejection.

The L6 response: "A maintenance window is a valid option if we can define a window that is acceptable to our SLA. The question I want to answer first is: what is our actual availability commitment? If we are committed to 99.9% uptime, a two-hour maintenance window represents about 2.5% downtime for the month, which blows our SLA. Even if we are not formally SLA-committed, there are often users in different time zones for whom 3am Eastern is peak hours. But if our user base is truly concentrated in one timezone and we have an explicit, contractual maintenance window, I would absolutely use it for very complex migrations rather than trying to do everything online. The zero-downtime approach adds complexity and testing burden that should be justified by a real availability requirement, not just as a default best practice."

---

## Common Interview Mistakes

**Mistake 1: Proposing ALTER TABLE without mentioning locking.** When a candidate says "I would add the column to the database" and does not mention locking, replication lag, or any tool for online DDL, the interviewer immediately flags this as L3/L4 thinking. The locking problem is basic knowledge for anyone who has worked with large-scale databases, and failing to mention it signals limited production experience.

**Mistake 2: Treating rollback as optional or an afterthought.** A candidate who designs a migration plan and mentions rollback only when directly asked about it has not internalized the most important principle of migration engineering. Rollback design is not a separate concern from migration design — it is integral to it. Staff engineers always have rollback on their mind from the moment they start planning a migration.

**Mistake 3: Proposing to do everything in one step.** "I would just stop the service, run the migration, and restart it" or "I would deploy all the changes at once in a release" are answers that reveal unfamiliarity with the risks of big-bang changes. The expand-contract pattern exists precisely because doing everything at once is high-risk. Breaking changes into smaller, independently safe steps is a core skill.

**Mistake 4: Ignoring the organizational and coordination dimension.** Technical candidates sometimes present flawless technical migration plans and then have no answer when asked "how would you coordinate this across six teams?" The coordination dimension is often harder than the technical dimension for large migrations, and ignoring it signals that the candidate has not worked at the scale where it matters.

**Mistake 5: Confusing feature flags with configuration flags.** Some candidates mention feature flags for migration cutover but then describe a flag system that requires a deployment to change the flag value. This defeats the primary purpose of feature flags in migration cutover, which is the ability to rapidly adjust (especially roll back) traffic routing without a deployment.

**Mistake 6: Not defining the success criteria for each phase of the migration.** A migration plan without measurable success criteria for each phase ("we will proceed to the next phase when X metric is within Y% of baseline for Z minutes") is a plan that is difficult to execute and impossible to audit. Interviewers at L6 level expect candidates to define these criteria naturally as part of describing the migration plan, not only when asked.

---

## Exercises

**Exercise 1:** Design the complete migration plan for renaming a column from `user_id` to `account_id` in a PostgreSQL table that has 50 million rows and receives 10,000 writes per second. Include the expand, migrate, and contract phases, the rollback plan for each phase, and the monitoring you would set up.

**Exercise 2:** You are migrating your company's user profile service from a MySQL database to a Redis-backed cache with a PostgreSQL persistent store. Design the dual-write period, including how you handle the case where a write succeeds to MySQL but fails to Redis.

**Exercise 3:** A mobile app uses your API. Version 1 of the API returns `"address": "123 Main St, City, State, Zip"` as a single string. Version 2 will return it as structured components. Design the full API migration, including how you handle the dual-format period, how you sunset v1, and what you do about clients that have not upgraded six months after you announced the sunset.

**Exercise 4:** Sketch the monitoring dashboard you would build for a migration of 100 million user rows from a single MySQL primary to a Vitess sharded cluster. What metrics would you show? What thresholds would trigger a pause? What thresholds would trigger an abort?

**Exercise 5:** A legacy service is being replaced by a new service using the strangler fig pattern. The legacy service uses synchronous HTTP calls. The new service uses an asynchronous event-driven architecture. How do you design the proxy layer to handle both synchronous clients (who need a synchronous response) and the asynchronous new service?

**Exercise 6:** You have completed the expand and migrate phases of a migration but are hesitant to execute the contract phase because you are worried about unknown clients that might still be using the old behavior. How do you identify all clients of the old behavior? What information do you use to make the go/no-go decision on the contract phase?

**Exercise 7:** Design the rollback drill for a migration that involves adding a Kafka topic between two services. The expand phase adds the topic and the consumer. The migrate phase switches the producer to write to the topic. The contract phase removes the direct service-to-service call that the topic replaces. What does a successful rollback drill verify at each phase?

**Exercise 8:** Read the GitHub engineering blog post about their MySQL to Vitess migration and identify: (1) which of the patterns covered in this chapter they used, (2) which aspects of the migration were most technically risky, and (3) what they would have done differently with hindsight.

**Exercise 9:** You are a staff engineer at a company where five ongoing migrations are all stuck at between 60% and 80% completion. The migrations have been running between 6 months and 18 months each. Design a "migration rescue program" — the organizational and technical steps you would take to bring all five migrations to completion within the next 90 days. Consider: how you audit the current state of each migration, how you prioritize among them, how you staff the rescue effort, and how you prevent the same pattern from recurring after the five are complete.

**Exercise 10:** Design a "migration contract" — a standardized document that a team must complete and get signed off before any production-state-changing migration step can begin. What sections does the contract include? What sign-offs does it require? How does it differ between low-risk migrations (adding a nullable column to a small table) and high-risk migrations (database engine change on a 500M-row table)? How do you make the contract lightweight enough that teams use it willingly rather than bypassing it?

**Exercise 11:** A company wants to migrate from storing passwords as MD5 hashes (a major security problem) to bcrypt hashes. The challenge is that you cannot decrypt MD5 hashes to re-encrypt them — the migration can only happen when a user next logs in. Design the migration strategy for this "opportunistic migration" pattern: how do you handle users who do not log in for years, what is the endgame when you want to force all remaining MD5-hashed passwords to be reset, and how do you track migration progress when you cannot control when users log in?

**Exercise 12:** You have just joined a company as a staff engineer. In your first month, you discover that the production database has 200 migration scripts that were applied using Flyway over 4 years, and approximately 30 of those scripts have corresponding "rollback" scripts that were never applied. The database schema has drifted significantly from what the migration scripts would produce if applied fresh to an empty database, suggesting that manual schema changes have been made directly in production. Design a plan to: (1) safely inventory the actual production schema, (2) reconcile it with the migration scripts, (3) prevent future manual production schema changes, and (4) establish a trustworthy migration baseline for future use.

---

## Homework

**Homework 1:** Take a real table in a personal or work project. Write a complete migration plan (using the five-step sequence from Part 3) for adding a new NOT NULL column to that table. Include the SQL statements for each step, the batch backfill script, and the monitoring queries you would run during the migration.

**Homework 2:** Find a public API (Stripe, Twilio, GitHub, etc.) and read their deprecation policy. Compare their approach to the deprecation lifecycle described in Part 7. What aspects of their policy are stronger than the approach described here? What aspects are weaker? What would you change?

**Homework 3:** Design a feature flag system from scratch — not using a third-party service but building it yourself — that supports: (1) per-user rollout (consistent hash on user ID), (2) percentage-based rollout, (3) automatic rollback if an error rate threshold is exceeded. What data model would you use? What API would application code call? How would you ensure fast propagation of flag changes to all servers?

**Homework 4:** Find a case study of a major infrastructure migration (GitHub to Vitess, Twitter to Manhattan, Shopify monolith decomposition, Netflix AWS migration) and analyze it along three dimensions: what patterns from this chapter did they use, what patterns do you wish they had used but did not, and what was the single most important organizational decision that made the migration succeed or fail?

**Homework 5:** Write a 500-word migration proposal for a fictional migration at a fictional company. Include: the problem being solved by the migration, the three-phase expand-contract plan, the rollback plan, the rollback triggers, the monitoring plan, the timeline, and the organizational coordination requirements. Practice presenting this proposal to someone and answering their questions.

**Homework 6:** Find an open-source project on GitHub that uses Flyway or Liquibase for database migrations. Clone the repository, read through all the migration files, and produce a written analysis of: (1) whether the migrations follow safe practices (nullable-first, no raw ALTER TABLE on tables that might be large, proper rollback scripts), (2) any migrations that look risky and why, and (3) what you would change about their migration approach if you were joining this team. This exercise builds the skill of auditing migration code quickly, which is useful in code reviews and technical interviews where you are asked to evaluate someone else's migration plan.

**Homework 7:** Interview two engineers at different experience levels (one junior, one senior) about a migration they have been involved with at their company. Ask them: what went well, what went wrong, what they wish they had known before starting, and what they would do differently. Write a 300-word comparison of their perspectives, noting how experience level affected what they noticed and cared about during the migration. This exercise builds empathy for how migration complexity is perceived at different experience levels, which is useful when leading a migration team with mixed seniority.

**Homework 8:** Take the migration plan you wrote for Homework 1 (the SQL migration for a NOT NULL column). Now introduce three intentional bugs into the plan: one that would cause data loss, one that would cause a production outage, and one that would cause silent data corruption. Write the bugs as if you were a tired engineer making mistakes under deadline pressure. Then swap your plan with a study partner and try to find each other's bugs. This adversarial exercise builds the habit of reading migration plans critically, which directly improves code review quality for migrations.

---

## Part 23: Edge Cases and Special Situations

### Migrating Multi-Tenant Systems

Multi-tenant systems — where a single database or service instance serves many independent customers — present a specialized migration challenge. The data for different tenants is often co-located in the same tables, differentiated by a tenant_id column. A migration that affects all tenants simultaneously must be carefully designed so that tenants who are on different product tiers, who have different data volumes, or who have opted into different features are all handled correctly.

The primary challenge in multi-tenant migrations is that "one size fits all" batch backfill logic often produces significantly different experiences for different tenants. A small tenant with 1,000 rows backfills in seconds and is finished before they notice anything. A large enterprise tenant with 50 million rows might be in the backfill phase for hours, during which the migration team must ensure that the system remains correct and performant for that tenant. If the large tenant happens to be in a demo with a prospective customer during the backfill, even a 10% performance degradation could cost a sale.

The mitigation is tenant-aware rate limiting in the backfill: when processing rows for a specific tenant, monitor that tenant's query performance in real time and automatically slow down or pause the backfill for that tenant if their performance metrics degrade. This requires that the backfill logic be aware of tenant boundaries and can independently pace the migration for each tenant. It also requires per-tenant migration tracking: knowing which tenants have completed the backfill, which are in progress, and which have not started, so that any tenant-specific issues can be investigated without losing track of the overall migration state.

For contract-phase enforcement in multi-tenant systems, be aware that different tenants may be on different product tiers with different API versions. A contract phase that removes an old API behavior may be acceptable for tenants on the current product tier but may break tenants on a legacy tier who were explicitly promised perpetual support for the old behavior. The contract phase planning must account for the full spectrum of tenant product commitments, not just the modal tenant experience.

### Migrating Read-Heavy vs. Write-Heavy Tables

The migration strategy for a table should be calibrated to the table's read/write ratio, because read-heavy and write-heavy tables have very different sensitivities to migration operations.

For read-heavy tables (where the vast majority of operations are reads, with writes being infrequent): the primary risk during migration is that adding a new column, running a backfill, or switching read paths introduces read performance regressions. Any migration step that changes the index structure or the query plan for common read queries can immediately degrade performance for a large number of users. The mitigation is to test the new schema's read performance thoroughly before switching any reads, using the shadow read pattern to compare latency between old and new schemas under real traffic. For read-heavy tables, the observe-before-commit period at each migration step should be longer than for write-heavy tables.

For write-heavy tables (where the majority of operations are writes): the primary risk is that dual-write overhead, backfill write amplification, and any locking from schema changes directly impacts write throughput and latency. For a table receiving 50,000 writes per second, even a 2% increase in write latency is significant. The mitigation is to rate-limit the backfill aggressively and to choose schema change tools (gh-ost, online DDL) that minimize write path overhead. Monitor write latency at every percentile during the migration, not just p99 — the mean and p50 are also important for write-heavy tables because they affect throughput directly.

### Migrating When You Cannot Change the Clients

Some migrations involve a data store or API that is accessed by clients you cannot modify. This could be external clients (third-party integrations that you have no code relationship with), legacy clients running on hardware you cannot update, or embedded clients (like firmware or mobile apps in the field that users have not updated). When you cannot change the clients, the entire migration burden falls on the server side: you must maintain backward compatibility at the server indefinitely, or find a proxy that translates between client expectations and the new server behavior.

The server-side translation approach — sometimes called a "protocol translation layer" or a "compatibility gateway" — sits between old clients and the new system and translates requests and responses to bridge the behavioral gap. For database migrations, this might be a query rewrite layer that translates queries written for the old schema to queries for the new schema. For API migrations, it is a versioning layer similar to Stripe's. The key design constraint for a compatibility gateway is that it must be correct for all client behaviors, including edge cases that you may not have tested. Running old clients in a shadow environment and sending their actual requests through the gateway (compared against the old system) is the best way to discover edge cases that the gateway handles incorrectly.

The sustainability question for a compatibility gateway is: how long does it need to run? If the answer is indefinitely, the gateway becomes a permanent feature of the system's architecture and must be maintained and evolved accordingly. If the answer is "until the last old client is gone," you need a mechanism for tracking old client usage and estimating when the gateway can be retired. The monitoring for old client usage must be specific enough to distinguish between client versions: knowing that 0.1% of requests are from old clients is necessary but not sufficient — you need to know which clients those are, so you can support them in migrating or make an informed decision to force their migration.

### Brainstorming Q&A

**Q: How do you migrate a database that is used by both an online transactional system (OLTP) and an offline analytical system (OLAP), where the analytical system runs nightly batch queries that last 4-6 hours?**

The coexistence of OLTP and OLAP workloads on the same database is itself an antipattern that migrations often expose because it creates competing constraints. The OLTP system needs fast reads and writes, short transactions, and minimal lock contention. The OLAP system needs to run long-reading queries that scan large numbers of rows, which conflicts with the OLTP system's need for low latency. A migration that changes the schema or data distribution often affects OLAP query plans in ways that are not anticipated during testing.

The safest approach for this scenario is to separate the OLAP workload from the migration scope: before starting the migration, ensure that OLAP queries are running against a dedicated read replica rather than the primary or the migration's shadow system. With OLAP isolated to a read replica, you can run the migration on the primary and shadow system without the 4-6 hour analytical queries interfering with migration parity checks, backfill rate limits, or cutover windows. After the migration completes, the read replica can be rebuilt from the new primary, and the OLAP queries can be validated against the new schema in a test replica before being allowed to run against production.

If separating OLAP to a replica is not currently possible (the queries require write access, or they are integrated with the primary for some reason), the migration needs to account for the nightly query window. The backfill job should be paused during the OLAP query window (typically 11pm-5am or whenever the batch runs) to avoid competing for I/O resources. The cutover window must be scheduled outside the OLAP window. And the parity verification job needs to be paused or significantly slowed during OLAP queries, because the long-running queries hold read locks that could interfere with parity checks. This complicates the migration timeline but makes the migration execution much more predictable.

**Q: What is the difference between a migration and a refactoring, and does that distinction matter in practice?**

The distinction is meaningful in some contexts and fuzzy in others, and being clear about which kind of change you are making helps you apply the right level of caution and coordination. A refactoring is a change that preserves existing behavior — the system after the refactoring does exactly what it did before, just implemented differently. A migration is a change that moves the system from one state to another — the system after the migration is genuinely different from before in some observable way (different data model, different API behavior, different infrastructure). Refactorings can generally be rolled back by reverting the code, without any concern about data or state. Migrations may leave behind persistent state changes (new database columns, written data, activated infrastructure) that must be explicitly managed as part of rollback.

In practice, changes often have elements of both: the code is being refactored (rearranged internally) but the change also involves a data migration (the internal data structure is changing). The practical implication of the distinction is that migration-elements of a change require the migration engineering practices described in this chapter, even if the code-elements are a straightforward refactoring. A change that refactors an internal data processing algorithm but also changes the database column format being used is a migration from a data engineering perspective, regardless of whether the code change feels like a refactoring. Categorizing changes correctly — identifying when a change has migration elements that require expand-contract, dual-write, or other migration patterns — is itself a skill that develops with experience.

---

## Self-Assessment: Migration Engineering Maturity

Use this rubric to honestly assess your current migration engineering maturity and identify the specific areas where additional study will have the most impact on your interview performance.

**Level 1 (Intern/Early Junior):** Can describe what a migration is. Has written a SQL ALTER TABLE statement. Does not think about locking, concurrency, or rollback spontaneously. Knowledge gaps: everything in Parts 3 through 9 of this chapter.

**Level 2 (Junior/Mid):** Knows to use nullable columns before NOT NULL. Has used Flyway or Liquibase. Has experienced a migration-related incident and learned from it. Understands that dual-write is needed when migrating between storage systems. Knowledge gaps: the organizational and coordination dimensions of Parts 10 and 11, the anti-patterns in Part 14, and the advanced distributed systems considerations in Parts 15 and 17.

**Level 3 (Mid/Senior):** Can design a complete expand-contract migration plan for a specific technical problem. Knows gh-ost and when to use it versus pt-osc. Has designed and operated a dual-write migration. Can write monitoring queries for a migration and define rollback triggers. Knowledge gaps: staff-level leadership patterns in Part 10, the program management discipline in Part 16, and the full anti-pattern taxonomy.

**Level 4 (Senior/Staff):** Has led a migration that involved multiple teams and ran for multiple months. Has defined rollback triggers and run rollback drills. Can explain all eleven anti-patterns and give a real or plausible example of each. Has designed monitoring frameworks for migrations and tracks parity verification continuously. Can make the organizational case for migration discipline to non-engineering stakeholders. Knowledge gaps: the interview application calibration in Part 11 and the practiced articulation of trade-offs under interview pressure.

**Level 5 (Staff and above):** Has defined organizational standards for migration discipline. Has built or adopted tooling (gh-ost, feature flag systems, migration tracking dashboards) that makes migrations safer at scale. Has personally intervened when a major migration was going wrong and course-corrected it. Can write and defend a complete migration plan for any of the twelve exercises in this chapter without preparation. Has internalized the patterns as instincts rather than checklists.

Honest self-assessment against this rubric is more useful than optimistic self-assessment. If you are at Level 2 or 3, focus your remaining study time on the organizational dimensions (Parts 10, 11, 16) and the anti-patterns (Parts 14, 20), which are most often the differentiator between L4/L5 and L6 interview performance. If you are at Level 4, focus on practiced articulation — doing the exercises in this chapter out loud, explaining trade-offs clearly, and building the pattern of clarifying questions before jumping to solutions that characterizes the best L6 interview performances.

---

## Connection to the Rest of This Guide

Chapter 97 connects most directly to the following chapters in this guide. Understanding these connections helps you synthesize knowledge across the guide rather than treating each chapter as isolated.

**Chapter 83 (Chubby / Distributed Locking):** The dual-write pattern's need for ordering guarantees connects to Chapter 83's treatment of distributed coordination. When dual-write needs strict ordering (financial data, inventory), distributed locks or consensus protocols may be needed to prevent the ordering bugs described in Part 14 Anti-Pattern 4.

**Chapter 85 (Borg / Container Orchestration):** Infrastructure migrations to containerized environments (Part 8 of this chapter) use the deployment mechanisms described in Chapter 85. Understanding rolling deployments, canary releases, and health check-based traffic management in container orchestration platforms is prerequisite knowledge for the infrastructure migration patterns in Part 8.

**Chapter 86 (Video Streaming):** Large-scale data migrations for media files and metadata (Part 8, cloud provider migration) involve object storage migration challenges similar to those in video streaming's content delivery layer. The object replication patterns described in Part 13, Playbook 3 (cloud provider migration) use the same CDN-origin synchronization patterns as video streaming infrastructure.

**Chapter 87 (Location and Maps):** Geographic data has specific migration challenges because spatial indexes (PostGIS, geo-hash partitioning, S2 cells) are difficult to migrate between storage engines. The patterns in Part 12 (online schema change tools) need to be combined with geography-specific index rebuilding strategies that go beyond what vanilla gh-ost handles.

**Chapter 95 (On-Call Engineering):** Part 15 of this chapter (migration monitoring) is the migration-specific specialization of the general observability principles in Chapter 95. The alert routing, runbook design, and incident response procedures described in Chapter 95 apply directly to migration incidents — the migration runbook described in Part 15 is a specific instance of the runbooks described in Chapter 95.

**Chapter 46 (Data Warehouse / OLAP):** The OLAP/OLTP co-location problem described in Part 23 (migrating when OLAP queries run long) is the migration manifestation of the architectural pattern choices described in Chapter 46. The Chapter 46 recommendation to separate OLTP and OLAP workloads is directly supported by the migration advice in Part 23 to ensure OLAP isolation before starting a migration.

Reviewing these connections after completing this chapter and the connected chapters will deepen your understanding of both and will prepare you for interview questions that deliberately bridge two or more of these topics.

---

## Pre-Interview Checklist: Migration Readiness

Use this checklist in the week before your interview to confirm you can discuss each topic fluently. For any item where you cannot immediately formulate a two-minute spoken response, that is a study priority.

**Patterns (can you describe each and give a concrete example?):**
- [ ] Expand-Contract (all three phases, why the contract phase is skipped, consequences)
- [ ] Dual-Write (the four stages, handling write failures, parity verification design)
- [ ] Shadow Mode (how it works, when to use it, what discrepancies tell you)
- [ ] Strangler Fig (the three components, parallel operation period, Airbnb example)
- [ ] Feature Flag Ramp (1% to 100%, rollback triggers, why deployment-based flags fail)
- [ ] Blue-Green Database Deployment (when to use it, the cutover window, rollback)
- [ ] Batch Backfill (chunk size rationale, rate limiting, replication lag monitoring)
- [ ] Rollback Drill (what it verifies, what it reveals, when it should happen)

**Anti-Patterns (can you describe each, give an example, and explain the mitigation?):**
- [ ] Big Bang Cutover
- [ ] Skipping the Contract Phase
- [ ] Not Testing Rollback
- [ ] Dual-Write Ordering Bugs
- [ ] Permanent Temporary Shims
- [ ] Migration That Never Completes
- [ ] Over-Migration
- [ ] Migrating Without a Data Dictionary

**Organizational Dimensions (can you speak to each from experience or principle?):**
- [ ] Multi-team coordination and dependency management
- [ ] Sunset deadline setting and enforcement
- [ ] Migration tracking dashboards and status reporting
- [ ] The last-20%-takes-80%-of-the-time problem and how to plan for it
- [ ] Staff engineer's role vs. senior engineer's role in a migration program

**Interview Performance Behaviors (are these habitual or do they require conscious effort?):**
- [ ] Asking clarifying questions before designing (what is the downtime tolerance? what is the rollback cost?)
- [ ] Mentioning monitoring and rollback without being asked
- [ ] Quantifying estimates (backfill time, replication lag thresholds, ramp step durations)
- [ ] Challenging the premise when appropriate ("do we really need NOT NULL here?")
- [ ] Naming organizational coordination challenges alongside technical ones

**Tool Knowledge (can you explain the tool, when to use it, and its key limitations?):**
- [ ] gh-ost: trigger-free MySQL online schema change using binary log parsing; limitation: requires ROW-based binary log format
- [ ] pt-osc: trigger-based MySQL online schema change; limitation: trigger overhead on high-write tables, conflicts with existing triggers
- [ ] Flyway: SQL migration versioning and deployment tracking; limitation: does not make migrations safer, only tracks them
- [ ] Liquibase: database-agnostic migration versioning; limitation: abstraction can limit database-specific features
- [ ] PostgreSQL online DDL: native online schema changes using NOT VALID constraints and VALIDATE CONSTRAINT to separate lock phases
- [ ] Feature flag systems (LaunchDarkly, Split.io, custom): real-time flag propagation without deployment; limitation: requires discipline to clean up after migration
- [ ] CDC (Change Data Capture): streaming database changes to downstream consumers; used for dual-write alternatives at high scale

---

## KEY TAKEAWAYS

```
+-------------------------------------------------------------------+
|                      KEY TAKEAWAYS                                |
|              Chapter 97: Migrations and Safe Changes              |
+-------------------------------------------------------------------+
|                                                                   |
|  1. MIGRATIONS ARE LIKE CHANGING AN ENGINE MID-FLIGHT             |
|     Three types: data, code, infrastructure.                      |
|     The system must work for both old and new during              |
|     the transition -- that dual-compatibility window is           |
|     the hardest part of any migration.                            |
|                                                                   |
|  2. EXPAND-CONTRACT IS THE MASTER PATTERN                         |
|     Add the new thing (expand). Move to the new thing             |
|     (migrate). Remove the old thing (contract).                   |
|     Never skip the contract phase.                                |
|                                                                   |
|  3. ALTER TABLE ON LARGE TABLES KILLS PRODUCTION                  |
|     Use gh-ost, online DDL, or the 5-step nullable-first          |
|     sequence. Batch backfills with rate limiting.                 |
|     Monitor replication lag throughout.                           |
|                                                                   |
|  4. DUAL-WRITE IS THE DATA MIGRATION WORKHORSE                    |
|     Write old AND new simultaneously. Read old.                   |
|     Verify parity continuously. Then switch reads.                |
|     Shadow mode for read-side verification.                       |
|                                                                   |
|  5. STRANGLER FIG FOR LEGACY SYSTEMS                              |
|     Never big-bang rewrite a working system.                      |
|     Proxy intercepts traffic. New system grows.                   |
|     Legacy system shrinks. Parallel verification                  |
|     before each capability is fully cut over.                     |
|                                                                   |
|  6. FEATURE FLAGS CONTROL RISK                                    |
|     1% --> 5% --> 20% --> 100%.                                   |
|     Define rollback triggers BEFORE starting.                     |
|     Real-time flag changes (not deployment-based).                |
|                                                                   |
|  7. APIs: NEVER BREAK CLIENTS WITHOUT WARNING                     |
|     Backward-compatible first. Deprecation lifecycle.             |
|     Sunset dates that are enforced, not extended.                 |
|     Stripe's 14-year compat is extreme but instructive.           |
|                                                                   |
|  8. DESIGN ROLLBACK BEFORE DESIGNING THE MIGRATION                |
|     If you cannot describe the rollback in detail                 |
|     before starting, you are not ready to start.                  |
|     Irreversible steps need extra verification.                   |
|     Rollback drills reveal hidden assumptions.                    |
|                                                                   |
|  9. MIGRATIONS ARE LEADERSHIP, NOT JUST ENGINEERING               |
|     Multi-team coordination, sunset enforcement,                  |
|     tracking dashboards, stakeholder communication.               |
|     The last 20% is always the hardest 80% of the time.          |
|                                                                   |
| 10. L5 vs L6 CALIBRATION                                          |
|     L5: Correct technical patterns, operational thinking.         |
|     L6: + Organizational coordination, second-order effects,      |
|         questions the problem itself, defines success             |
|         criteria, designs monitoring first.                       |
|                                                                   |
+-------------------------------------------------------------------+
```

---

## Chapter Summary

Live migrations are one of the highest-leverage skills in systems engineering precisely because they are so universally necessary and so frequently done badly. Every system evolves. Every evolution requires migration. And the quality of those migrations determines whether an engineering organization is one that builds trust with its users over time or one that periodically breaks trust in incidents that could have been avoided.

The patterns in this chapter — expand-contract, dual-write, strangler fig, feature flag ramp, the five-step schema migration sequence, the rollback protocol — are not theoretical constructs. They are patterns distilled from real incidents at GitHub, Stripe, Twitter, Airbnb, and hundreds of other organizations that have gone through the hard work of evolving large systems in production.

The meta-lesson that connects all of these patterns is this: **safe migrations are incremental migrations.** They change one thing at a time. They maintain backward compatibility throughout the transition. They have observable intermediate states that can be monitored and measured. They can be reversed at any step without catastrophic data loss. And they are designed so that the humans executing them can understand what state the system is in at any moment.

When you walk into your next system design interview and the question involves changing a system that is already running, remember the airplane mid-flight. You cannot land to do the work. You cannot ask the passengers to hold their breath. You have to do it incrementally, safely, reversibly, and transparently. The engineer who can articulates that clearly, and who can explain the specific patterns for accomplishing it, is the engineer who is ready for L6.

---

*Next chapter: Chapter 98 — Technical Writing for Engineers*

---

## Part 12: Database Migration Patterns Deep Dive

### Blue-Green Database Deployment

The blue-green deployment pattern is widely understood for application servers: you stand up a second, identical environment (green) alongside your current production environment (blue), warm up green, switch traffic from blue to green, and decommission blue. For stateless application servers, this is relatively straightforward. For databases — which are stateful — blue-green is far more complex, but it is a powerful pattern when you need to make a wholesale database change with minimum risk.

In a blue-green database deployment, the blue database is your current production database (the live one). The green database is a new database instance with the desired new schema, configuration, or version. The key challenge is keeping the green database synchronized with the blue database throughout the cutover process. You do this using database replication: set up the green database as a replica of the blue database, let it catch up with all existing data, and then switch application traffic from blue to green during a brief, controlled cutover window. During that window, you stop writes to blue (or drain in-flight transactions), wait for green to fully catch up, promote green to primary, point your application at green, and reopen writes.

The cutover window — the time when blue is accepting no new writes and green is catching up on the last few replication events — is typically five to sixty seconds for well-prepared migrations. This is the moment of maximum risk. If green fails to come up healthy, you flip back to blue (which has been idle, not corrupted) and the only consequence is a few seconds of write downtime. This is the great advantage of blue-green over in-place migration: your rollback is immediate and clean, because blue is sitting there, fully intact, waiting. The green database is only promoted once you have confirmed it is healthy. Many organizations use blue-green for major version upgrades of PostgreSQL or MySQL because the upgrade process can be done offline on the green replica while blue continues to serve production traffic, and the cutover is measured in seconds rather than hours.

```
Blue-Green Database Deployment

BEFORE CUTOVER:
  App --> Blue DB (primary, all writes) --> Green DB (replica, catch up)

CUTOVER WINDOW (< 60 seconds):
  1. Drain in-flight writes from Blue
  2. Blue accepts no new writes
  3. Green catches up to Blue (replication lag = 0)
  4. Health check Green
  5. App --> Green DB (new primary)
  6. Blue becomes standby

AFTER CUTOVER:
  App --> Green DB (primary)
  Blue DB = standby (kept for fast rollback window, e.g. 48 hours)
  Blue DB = decommissioned after confidence period
```

### Online Schema Change Tools: A Comparative Analysis

When you need to alter the schema of a large, live table, four tools dominate the landscape: pt-online-schema-change (pt-osc), gh-ost, Flyway, and Liquibase. They solve different problems and operate at different layers, so understanding where each one fits is essential knowledge for a senior engineer.

**pt-online-schema-change (pt-osc)** is part of the Percona Toolkit and is the older of the two MySQL online DDL tools. Like gh-ost, it creates a shadow table with the new schema and copies data in the background. The critical difference is that pt-osc uses MySQL triggers to keep the shadow table in sync with the original table during the copy: it installs INSERT, UPDATE, and DELETE triggers on the original table that replay each change on the shadow table. The trigger approach works but has operational downsides. Triggers add latency to every write on the original table. On extremely high-write tables, the trigger overhead can become significant. And triggers interact badly with other triggers if the table already has any. Finally, pt-osc requires that the user running the tool have the SUPER or TRIGGER privilege. Despite these drawbacks, pt-osc is battle-tested across many MySQL installations and is simpler to operate than gh-ost for common scenarios.

**gh-ost** (GitHub Online Schema Transmogrifier) takes a different approach. Instead of triggers, gh-ost reads the MySQL binary log (the replication stream) to capture changes to the original table, applying them to the shadow table as they arrive. This trigger-free approach is the primary advantage: no write amplification on the original table, no privilege requirement for triggers, and cleaner operation in high-write environments. gh-ost also has a rich set of operational controls: you can pause and resume the migration by touching a file, you can throttle the copy rate in real time, and you can inspect progress at any moment. The complexity of binary log parsing means gh-ost requires the binary log to be in ROW format and requires specific MySQL privileges for binary log access. But for large, high-write tables at companies like GitHub, it has proved to be significantly superior to pt-osc.

**Flyway** is a different category of tool entirely. It is not an online schema migration tool in the sense of avoiding table locks — it executes whatever DDL statements you give it, which means it can still lock tables. Flyway's value is in schema version management: it tracks which migration scripts have been applied to a database using a metadata table, applies pending migrations in order, and ensures that all database instances in your fleet are running the same schema version. It integrates with deployment pipelines to run migrations automatically during deployments. Flyway is excellent for managing the sequence and versioning of schema changes but does not by itself make those changes safer from a locking perspective. You would pair Flyway with gh-ost or pt-osc for the actual execution of high-risk schema changes, using Flyway to track that the change was applied.

**Liquibase** is similar to Flyway in purpose — schema version management and change tracking — but operates at a higher level of abstraction. Whereas Flyway takes raw SQL migration files, Liquibase uses a database-agnostic XML, YAML, JSON, or SQL format called a changelog to describe changes. The Liquibase engine can generate the appropriate SQL for multiple database engines from the same changelog. This database-agnostic abstraction is valuable for organizations that run the same application against multiple database engines (e.g., PostgreSQL in production and H2 in-memory for tests). The tradeoff is that the abstraction can be limiting for database-specific features, and generating correct SQL for complex operations in a database-agnostic way requires careful testing.

### Event Sourcing as a Migration Strategy

Event sourcing is an architectural pattern where instead of storing the current state of an entity, you store the full history of events that produced that state. The current state is derived by replaying the events. This pattern has an important property that is directly useful in migrations: because all state can be derived from the event log, you can migrate to a new data model by replaying the existing event log through a new projection function.

Imagine you have a user account system that currently stores account balances in a relational database. You need to migrate to a new data model that adds a detailed transaction history and supports multi-currency balances. With a traditional data store, this migration requires transforming existing rows, potentially backfilling historical data that was never captured. With event sourcing, you already have the complete event history (every credit and debit event for every account). Migrating to the new data model means writing a new projection that reads those same events and produces the new data model. You run the new projection in parallel with the old one, verify that the old projection's current balances match what the new projection computes, and then cut over.

The replayability of event sourcing is its migration superpower. You can wipe the entire projected database and rebuild it from scratch at any time by replaying the event log. If the new projection has a bug, you fix the bug and replay again. There is no data loss risk during migration, because the source of truth (the event log) is never modified. This makes certain classes of migration almost trivially safe.

The limitation is that event sourcing introduces significant complexity in other areas: queries become harder (you cannot simply SELECT current state), the event log grows without bound (requiring compaction strategies), and not all domains have natural event semantics. But for systems that are already event-sourced, or for systems where the migration complexity is severe enough to justify adopting event sourcing specifically to enable it, this pattern is worth serious consideration.

### The Replication Lag Problem During Dual-Write

Replication lag is one of the most insidious problems in dual-write migrations. When you write to both an old database and a new database, the new database typically receives its data either through application-level dual-write (the application explicitly writes to both) or through replication (the old database replicates to the new). Either way, if the new database is not keeping up with the write rate, you have replication lag — a period where the new database's data is behind the old database.

The danger is not just that the new database has stale data (which you expect during backfill). The danger is that replication lag during the cutover window creates a window of potential data loss. Suppose you decide to cut over reads to the new database when replication lag is reported at zero seconds. But the lag measurement is itself delayed by measurement interval — the dashboard showing zero seconds of lag might be 30 seconds old. If writes continued to flow to the old database in the last 30 seconds, those writes might not have reached the new database yet. Cutting over with that assumption would serve stale data to users.

The safe practice is to measure replication lag in real time, gate the cutover on lag being zero (or under one second) for a sustained period (not just a momentary dip), and stop writes to the old database before confirming that the replica is fully caught up. This is the same pattern used in blue-green database deployment: drain writes from the source, wait for the replica to fully catch up, confirm lag = 0, then switch. The measurement of lag = 0 should come from a dedicated heartbeat mechanism: write a known value (timestamp) to the old database every second, and measure how quickly that value appears on the replica. This heartbeat approach gives you a continuous, accurate measurement of true replication lag, independent of whatever the database's own lag metric reports.

High write rates during dual-write can also cause replication lag to accumulate faster than normal because every write generates binary log events on the old database (for normal traffic) plus additional writes from the dual-write path (for the migration). The total write load on the old database during dual-write is therefore higher than baseline, and this increased load can cause the replica to fall behind. Rate-limiting the dual-write or the backfill job during peak traffic hours is one mitigation. Another is to scale the replica's compute resources temporarily during the dual-write period to handle the higher load.

### Concrete SQL Migration Scripts: Before and After

Understanding migration patterns conceptually is important, but seeing exactly what the SQL looks like at each stage closes the gap between theory and practice.

**Scenario: Rename the column `username` to `display_name` in a PostgreSQL `users` table with 80 million rows.**

**Before the migration starts — verify the current state:**
```sql
-- Check current table structure
\d users

-- Count rows (for backfill progress tracking)
SELECT COUNT(*) FROM users;

-- Check the current column usage in dependent views
SELECT definition FROM pg_views WHERE definition LIKE '%username%';
```

**Step 1 (Expand) — Add the new column as nullable:**
```sql
-- Fast: this is a metadata-only operation in PostgreSQL, no row rewrite
ALTER TABLE users ADD COLUMN display_name VARCHAR(255);

-- Verify the column was added
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'users' AND column_name IN ('username', 'display_name');
```

**Step 2 — Deploy application code to write both columns. After that code is deployed:**
```sql
-- Verify that new writes are populating display_name (sample recent rows)
SELECT id, username, display_name, created_at
FROM users
ORDER BY created_at DESC
LIMIT 100;
```

**Step 3 (Migrate) — Batch backfill existing rows:**
```sql
-- One batch: update 5,000 rows at a time where display_name is still NULL
-- Repeat this in a loop from application code or a script
UPDATE users
SET display_name = username
WHERE id IN (
    SELECT id FROM users
    WHERE display_name IS NULL
    ORDER BY id
    LIMIT 5000
);

-- Track backfill progress
SELECT
    COUNT(*) FILTER (WHERE display_name IS NULL) AS rows_remaining,
    COUNT(*) FILTER (WHERE display_name IS NOT NULL) AS rows_complete,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE display_name IS NOT NULL) / COUNT(*), 2
    ) AS pct_complete
FROM users;
```

**Step 4 (Contract preparation) — Add NOT NULL constraint safely in PostgreSQL:**
```sql
-- In PostgreSQL 12+: add NOT VALID constraint first (no table scan needed)
ALTER TABLE users ALTER COLUMN display_name SET NOT NULL;
-- OR for large tables, use this two-step approach:
ALTER TABLE users ADD CONSTRAINT display_name_not_null
    CHECK (display_name IS NOT NULL) NOT VALID;

-- Then validate the constraint (weaker lock, does not block reads)
ALTER TABLE users VALIDATE CONSTRAINT display_name_not_null;
```

**Step 5 (Contract) — Drop the old column after code is fully migrated:**
```sql
-- Only after all application code has been updated to use display_name
-- and after verifying zero usage of username column in app code
ALTER TABLE users DROP COLUMN username;

-- Verify final structure
\d users
```

### Part 12 Intern to Staff: How Understanding Grows

**Intern level:** Knows that SQL has ALTER TABLE and can write a basic migration script. Does not think about locking or backfill safety.

**Junior (L3) level:** Has used Flyway or Liquibase to manage migration scripts in a deployment pipeline. Knows to add columns as nullable before adding constraints.

**Mid-level (L4) level:** Has used gh-ost or pt-osc on a production table. Can write a batch backfill script with rate limiting. Understands the replication lag risk and monitors it during migrations.

**Senior (L5) level:** Can compare gh-ost and pt-osc and choose the right tool for the specific table characteristics. Designs the full migration script set including validation queries and rollback scripts. Has experienced and recovered from a replication lag incident during migration.

**Staff (L6) level:** Defines the organization's standard toolchain for schema migrations. Contributes to or evaluates tools like gh-ost for adoption. Designs the migration governance process: which migrations require review, what the review checklist includes, and how migrations are tracked to completion. Has deep intuition for when a schema migration is high-risk enough to warrant extra caution versus when a straightforward approach is fine.

### Brainstorming Q&A

**Q: When would you choose gh-ost over pt-osc, and vice versa?**

The choice between gh-ost and pt-osc depends primarily on write rate and trigger sensitivity. If the table has a very high write rate — for example, more than a few thousand writes per second — gh-ost is almost always preferable because it avoids the trigger overhead that pt-osc imposes on every write. Triggers in MySQL execute synchronously in the transaction that triggered them, meaning every INSERT, UPDATE, and DELETE on the original table now has additional latency from the trigger executing on the shadow table. At high write rates, this latency accumulates into a measurable performance degradation. gh-ost, by contrast, reads the binary log asynchronously and has no impact on the write path's latency. On the other hand, if the table has existing triggers, gh-ost cannot be used — MySQL does not support a single table having multiple triggers of the same type (a limitation that is lifted in some newer MySQL versions), so gh-ost's binary log applier conflicts with existing triggers. In that case, pt-osc is the better choice because it can coexist with existing triggers. Additionally, if your team lacks the MySQL replication expertise needed to safely operate gh-ost's binary log parsing, pt-osc is simpler to understand and troubleshoot. For greenfield tables without existing triggers and at high write rates, gh-ost is the modern choice. For legacy tables with complex trigger setups, pt-osc is more practical.

**Q: How do you handle a situation where the event log in an event-sourced system has grown so large that replaying it for a migration would take 72 hours?**

This is a real operational problem in event-sourced systems that have been running for years. The standard solution is snapshotting combined with selective replay. A snapshot is a point-in-time capture of the projected state at a specific event offset — essentially a checkpoint of what the read model looked like when the event log was at event N. For a migration, instead of replaying from event 0 (the beginning of time), you start from the most recent snapshot and replay only the events that occurred after that snapshot. If you snapshot daily, you replay at most 24 hours of events rather than 72 hours. The migration procedure is: take a fresh snapshot in the current schema, create the new projection, initialize the new projection from the snapshot, then replay events from the snapshot point forward in the new schema format. The challenge is ensuring that the snapshot itself is consistent — that it was captured at a clean point where no partial event updates were in-flight. Snapshot consistency requires that the snapshot captures the state after a complete event was applied, not in the middle of a multi-event transaction. Systems that do event sourcing seriously typically build snapshot infrastructure as part of their event store design, precisely because the replay-only approach becomes impractical at scale.

**Q: In dual-write migrations, is there a risk of write ordering bugs that cause the two databases to diverge?**

Yes, write ordering bugs are one of the most subtle and dangerous failure modes in dual-write migrations, and they deserve their own dedicated concern. The classic scenario is a concurrent update to the same record. Suppose two application servers both process requests that update the same user's profile at the same time. Server A writes to the old database first, then to the new database. Server B writes to the old database first, then to the new database. Because of network timing differences, the order of arrival at the old database might be A then B (leaving B's update as the final state), while the order of arrival at the new database might be B then A (leaving A's update as the final state). The two databases now have different values for the same user's record, even though both servers followed the dual-write pattern correctly. This scenario is called a write ordering bug, and it is more common than most engineers expect. The solution requires either using a distributed transaction (which is expensive and complex) or using optimistic locking with version numbers (each write includes the expected version, and the write fails if the record has been modified since the version was read, forcing a retry). The parity verification job will catch these divergences, but catching them is different from preventing them — in a high-write environment, parity verification needs to run frequently enough to catch ordering bugs before they accumulate into a large backlog of diverged records.

---

## Part 13: Real Migration Playbooks

### Playbook 1: Migrating a PostgreSQL Table to a New Schema (10 Steps)

This playbook covers moving a table from one schema (or set of columns) to a new schema while the service continues to handle production traffic. The example is migrating a `payments` table that stores a flat amount field to a new schema that stores amount plus currency code separately, supporting multi-currency payments.

**Step 1: Audit all consumers of the table.**
What you do: Use code search and database query logs to find every SELECT, INSERT, UPDATE, and DELETE that references the `payments` table. This includes application code, batch jobs, analytics queries, and any external systems that query the database directly.
Why: You need to understand the full blast radius of the migration before changing anything. Missing a consumer means that consumer breaks unexpectedly after the migration.
How to verify: Count the unique code paths that reference the table. Get review sign-off from all teams whose code touches this table.
Rollback if it fails: This step cannot fail in a way that affects production. If you find more consumers than expected, stop and re-plan the migration.

**Step 2: Add new columns as nullable — `amount_value` (NUMERIC) and `currency_code` (VARCHAR(3)).**
What you do: Run `ALTER TABLE payments ADD COLUMN amount_value NUMERIC, ADD COLUMN currency_code VARCHAR(3);` Adding multiple columns in one statement is more efficient than separate ALTER TABLE statements in PostgreSQL because it only requires one table rewrite pass (though in modern PostgreSQL, adding nullable columns without defaults is metadata-only and does not rewrite rows at all).
Why: Nullable columns can be added without locking the table. Old code that inserts rows with only the old `amount` column will still work because the new columns allow NULL.
How to verify: Run `\d payments` and confirm both new columns are present and nullable. Test that existing INSERT statements still work in a staging environment.
Rollback if it fails: `ALTER TABLE payments DROP COLUMN amount_value, DROP COLUMN currency_code;` — fast because the columns are empty.

**Step 3: Deploy the dual-write application code.**
What you do: Update all INSERT and UPDATE paths to write both the old `amount` column and the new `amount_value` + `currency_code` columns simultaneously. Do not yet update any SELECT paths.
Why: From this point forward, all new payments will have both the old format and the new format. This is the beginning of the expand phase.
How to verify: Insert a test payment and confirm all three columns are populated. Monitor the error rate of the dual-write code path in production for 30 minutes.
Rollback if it fails: Deploy the previous version of the application code (which only writes the old column). The new columns will simply remain NULL for any rows inserted during the dual-write period, which is acceptable because you have not switched any reads yet.

**Step 4: Backfill `amount_value` and `currency_code` for existing rows.**
What you do: Run a batch backfill job that sets `amount_value = amount` and `currency_code = 'USD'` (assuming all existing payments were in USD) for all rows where `amount_value IS NULL`. Process in chunks of 5,000 rows with 50ms pauses between chunks.
Why: Historical rows need both columns populated before you can add NOT NULL constraints or switch reads.
How to verify: Monitor backfill progress with `SELECT COUNT(*) FROM payments WHERE amount_value IS NULL`. Monitor replication lag during backfill. Set an alert if replication lag exceeds 10 seconds.
Rollback if it fails: The backfill is idempotent (WHERE amount_value IS NULL) — stop the job and restart from any point. No production impact because reads are still coming from the old column.

**Step 5: Run parity verification for 24 hours.**
What you do: Run a background job that samples 1,000 random rows per hour and compares `amount` to `amount_value`, logging any discrepancies.
Why: Before switching reads, you need high confidence that the new columns are correct.
How to verify: Zero discrepancies in 24 hours of sampling, or discrepancies only in rows from before the backfill started (which you re-backfill and re-verify).
Rollback if it fails: Do not switch reads. Investigate the discrepancy source (is it a bug in the dual-write code? a timezone issue in backfill? a null-handling bug?) and fix before proceeding.

**Step 6: Update read paths to use new columns, starting with 5% of traffic.**
What you do: Use a feature flag to route 5% of SELECT queries to read from `amount_value` and `currency_code` instead of `amount`. Return results from the new columns to the 5% of traffic. Compare results from the old and new paths in the background for shadow validation.
Why: Gradual traffic shift limits blast radius if there is a latent bug in the new read path.
How to verify: Shadow comparison shows zero discrepancies. No new errors in application logs. p99 latency unchanged.
Rollback if it fails: Flip the feature flag back to 0%. Investigate discrepancies.

**Step 7: Ramp reads to 100% over 4 hours (5% → 20% → 50% → 100%).**
What you do: Increase the feature flag in steps of 5% → 20% → 50% → 100%, pausing 30 minutes at each step to monitor.
Why: Each step gives more data points to validate correctness before the next step.
How to verify: At 100%, old `amount` reads are no longer happening. Shadow comparison discrepancy rate remains zero. All business metrics normal.
Rollback if it fails: Flip the feature flag to 0% immediately. Root-cause the issue.

**Step 8: Stop writing to the old `amount` column and add NOT NULL constraints.**
What you do: Remove `amount` from all INSERT and UPDATE statements. Add NOT NULL constraints to `amount_value` and `currency_code`: `ALTER TABLE payments ALTER COLUMN amount_value SET NOT NULL; ALTER TABLE payments ALTER COLUMN currency_code SET NOT NULL;`
Why: This is the contract phase beginning. Writing to two columns indefinitely wastes resources and keeps old code alive.
How to verify: Attempt an INSERT without `amount_value` — it should fail with NOT NULL violation. Verify application code does not break.
Rollback if it fails: Re-add `amount` writes to application code. Drop the NOT NULL constraints (fast).

**Step 9: Drop the old `amount` column.**
What you do: `ALTER TABLE payments DROP COLUMN amount;`
Why: Remove the old column to clean up the schema and eliminate confusion for future engineers.
How to verify: `\d payments` shows `amount` is gone. All application code references to `amount` were already removed.
Rollback if it fails: This step is NOT easily reversible once committed. Do not execute this step until you have been running without the `amount` column in application code for at least one week and have verified that no application or analytics job references it.

**Step 10: Clean up — update monitoring, analytics, and documentation.**
What you do: Update any dashboards, analytics queries, or monitoring alerts that referenced the old `amount` column. Update the database schema documentation.
Why: Migration is not complete until all downstream consumers are updated. Stale dashboards or analytics queries will fail silently and produce incorrect results.
How to verify: Run all analytics queries in staging. Check all monitoring dashboards in production.
Rollback if it fails: This step cannot cause a production failure. If an analytics query breaks, update it.

### Playbook 2: Migrating from a Monolith API to a Microservice (12 Steps)

This playbook covers extracting a capability from a monolithic application into a standalone microservice, using the strangler fig pattern. The example is extracting a `NotificationService` from a Rails monolith.

**Step 1: Define the service boundary precisely.**
What you do: Write a one-page document that specifies exactly what the new NotificationService will own: what data it manages, what APIs it exposes, what it depends on. Get sign-off from all teams that currently call the notification code in the monolith.
Why: An ill-defined boundary is the most common reason microservice extractions fail. You need everyone to agree on what goes into the new service and what does not, before you start building.
How to verify: The document can be reviewed and critiqued by five different engineers without producing five different interpretations.
Rollback if it fails: This is a planning step. If the boundary cannot be agreed upon, the migration should not start.

**Step 2: Build the new NotificationService with a versioned API, deployed independently.**
What you do: Build the new service as a standalone application. Give it its own database if it needs persistent state. Deploy it to a staging environment. Do not connect it to production yet.
Why: Proving the new service works correctly in isolation before connecting it to the monolith reduces risk.
How to verify: All unit tests and integration tests pass. API contract matches the agreed specification.
Rollback if it fails: Delete the new service's deployment. No production impact.

**Step 3: Add a notification adapter in the monolith that abstracts the notification code.**
What you do: Refactor the monolith's notification code to use a NotificationAdapter interface. The concrete implementation is still the monolith's own notification code. This step involves no behavioral change — it only adds abstraction.
Why: The adapter is the strangler fig proxy. By routing all calls through the adapter, you can later swap the implementation without changing the callers.
How to verify: All monolith tests pass. No change in notification behavior in production.
Rollback if it fails: Revert the adapter refactor. Straightforward code rollback.

**Step 4: Add a second NotificationAdapter implementation that calls the new service.**
What you do: Build a RemoteNotificationAdapter that calls the new NotificationService via HTTP or gRPC instead of calling the monolith's local code. Add a feature flag to choose between the local adapter and the remote adapter.
Why: This gives you the ability to switch to the new service and back with a flag change, without a code deployment.
How to verify: In a staging environment, enable the remote adapter and run all notification tests. Verify parity with the local adapter.
Rollback if it fails: Feature flag stays on local adapter. No production impact.

**Step 5: Enable the remote adapter for 1% of notification calls in production.**
What you do: Set the feature flag to route 1% of notification calls to the new NotificationService. Log both the local and remote results and compare them.
Why: Real production traffic will expose edge cases that staging did not.
How to verify: Zero errors from the remote adapter calls. Shadow comparison shows results match local adapter for all 1% of calls.
Rollback if it fails: Set feature flag to 0% (local adapter only).

**Step 6: Ramp the remote adapter to 100% over one week.**
What you do: Increase the feature flag gradually: 1% → 5% → 20% → 50% → 100%. At each step, wait 24 hours and review error rates, latency, and shadow comparison discrepancies.
Why: One week of gradual ramp gives sufficient data to catch latent bugs, including those that only appear under unusual load patterns (e.g., end-of-month batch jobs, holiday traffic).
How to verify: At 100%, no errors attributable to the new service. Latency p99 acceptable.
Rollback if it fails: Reduce feature flag percentage.

**Step 7: Migrate the data — move notification records from the monolith's database to the new service's database.**
What you do: Stand up dual-write for notification data: the new service writes both to its own database and back to the monolith's database via an async queue. Run a backfill to copy historical notification records to the new service's database.
Why: The new service cannot fully own notification data while it depends on the monolith's database.
How to verify: Parity verification shows new service database matches monolith database for all notification records.
Rollback if it fails: Stop the backfill. New service can continue to read from the monolith's database as a fallback.

**Step 8: Switch the new service's reads to its own database.**
What you do: Disable the fallback reads from the monolith's database. The new service now reads exclusively from its own database.
Why: Completing the data ownership transfer.
How to verify: Shadow comparison shows zero discrepancies. Service functions correctly.
Rollback if it fails: Re-enable reads from the monolith's database.

**Step 9: Stop the monolith's notification write path.**
What you do: Remove the monolith's own notification code from the write path. The NotificationAdapter now only has the remote implementation.
Why: The monolith should no longer be responsible for notifications. It calls the new service for all notification needs.
How to verify: No calls to the monolith's local notification code. All notifications go through the new service.
Rollback if it fails: Re-enable the local adapter via feature flag.

**Step 10: Remove the dual-write back to the monolith's database.**
What you do: Stop writing notification records back to the monolith's database. The new service's database is the source of truth.
Why: Dual-write cleanup (the contract phase of the data migration).
How to verify: Monolith's notification tables receive no new writes. New service's database is fully authoritative.
Rollback if it fails: Re-enable dual-write (the queue mechanism is still in place for quick re-enabling).

**Step 11: Remove the feature flag and the local adapter implementation.**
What you do: Delete the feature flag configuration. Delete the LocalNotificationAdapter class from the monolith. The only adapter is now the remote one.
Why: Code cleanup. Removing dead code reduces cognitive load and eliminates the risk of accidentally enabling the old path.
How to verify: Code compiles. Tests pass. No references to LocalNotificationAdapter remain.
Rollback if it fails: Revert the code change. Feature flag can be re-added.

**Step 12: Decommission the monolith's notification tables.**
What you do: Archive the old notification tables in the monolith's database (rename to `notifications_archived_YYYYMMDD`), then drop them after a 30-day holding period.
Why: Final cleanup. Removes confusion and reclaims disk space.
How to verify: No application code references the old table names. Analytics queries have been updated to point to the new service.
Rollback if it fails: During the archive period, re-enable the table by renaming back. After dropping, this is non-reversible — only execute after full confidence.

### Playbook 3: Migrating Data Between Cloud Providers (8 Steps)

This playbook covers the organizational and technical steps for moving data from one cloud provider (e.g., AWS) to another (e.g., GCP). The example is migrating a PostgreSQL database and associated object storage.

**Step 1: Inventory all data assets and classify by sensitivity and size.**
What you do: Catalog every data store: which databases, which object storage buckets, what data volumes, what data classifications (PII, financial, logs, etc.). Identify which data must remain encrypted in transit and at rest during migration.
Why: You cannot migrate what you have not inventoried. Sensitive data requires special handling (encryption, access controls, audit logging during transfer). Size estimates determine how long the migration will take.
How to verify: The inventory is reviewed by security and legal. The estimated data transfer time is calculated and agrees with the proposed migration window.
Rollback if it fails: This is a planning step. Do not proceed until the inventory is complete.

**Step 2: Set up network connectivity between providers (VPN or dedicated interconnect).**
What you do: Establish a secure network link between your AWS VPC and your GCP VPC. Options include an IPSec VPN tunnel (simpler, lower bandwidth) or a dedicated interconnect (Google's Partner Interconnect or AWS Direct Connect, higher bandwidth). Configure routing and security groups.
Why: Data will need to transfer over this link during migration. A secure, dedicated link avoids data traversing the public internet and provides predictable bandwidth.
How to verify: Test connectivity from an AWS instance to a GCP instance. Measure throughput and latency. Verify encryption of the link.
Rollback if it fails: Tear down the network connection. No production impact.

**Step 3: Provision and configure the target infrastructure in GCP.**
What you do: Set up the equivalent services in GCP: Cloud SQL for PostgreSQL (or self-managed Postgres on Compute Engine), Cloud Storage buckets for object storage, VPC networking, IAM roles, and monitoring.
Why: The target environment must be ready before data migration begins. Validating configuration in advance prevents surprises during the cutover.
How to verify: Run your full test suite against the GCP environment with test data. Verify performance benchmarks (latency, throughput) meet requirements.
Rollback if it fails: Tear down GCP resources. AWS remains primary.

**Step 4: Set up cross-cloud PostgreSQL replication from AWS to GCP.**
What you do: Configure the GCP PostgreSQL instance as a logical replica of the AWS PostgreSQL instance using PostgreSQL logical replication (available in PostgreSQL 10+). The GCP instance will stream changes from the AWS instance's write-ahead log.
Why: Logical replication keeps the GCP database in sync with the AWS database continuously, without requiring application-level dual-write. This is simpler and more reliable than application-level dual-write for database migration.
How to verify: Measure replication lag (should be under 1 second after initial data sync completes). Confirm all tables are replicating correctly.
Rollback if it fails: Stop the replication subscription. AWS database is unchanged.

**Step 5: Migrate object storage data incrementally using sync tools.**
What you do: Use a sync tool (AWS's native S3 to GCS sync, or rclone, or a custom sync job) to copy object storage from S3 to GCS. Run in incremental sync mode so that new objects written to S3 after the initial sync begins are also copied.
Why: Object storage data may be tens or hundreds of terabytes and cannot be migrated in a single batch. Incremental sync keeps GCS in sync with S3 as the migration proceeds.
How to verify: Object count in GCS matches object count in S3. Random sample verification compares checksums of files between providers.
Rollback if it fails: Stop the sync job. AWS S3 remains the source of truth.

**Step 6: Update application configuration to dual-point (read from AWS, write to both).**
What you do: For any application code that directly reads from or writes to S3, update it to write to both S3 and GCS. Reads remain from S3. For the database, no application change is needed because GCP is receiving changes via replication.
Why: Ensures that new object storage writes reach both providers, so GCS does not fall behind during the cutover window.
How to verify: Write a test file and confirm it appears in both S3 and GCS within 5 seconds.
Rollback if it fails: Revert application configuration. Remove GCS writes.

**Step 7: Execute the database cutover and traffic migration.**
What you do: At a pre-planned time with all engineers standing by: (a) drain in-flight database writes, (b) stop writes to the AWS database, (c) wait for GCP replica to reach zero replication lag, (d) promote GCP database to primary, (e) update application database connection strings to point to GCP, (f) restart application servers, (g) resume writes. Simultaneously, update the application's object storage reads to point to GCS instead of S3.
Why: This is the cutover — the moment of truth. All preparation in previous steps has been to make this moment as safe and fast as possible.
How to verify: First write to GCP database succeeds. First read from GCS succeeds. Error rates and latency are normal within 60 seconds.
Rollback if it fails: Update connection strings back to AWS. AWS database is still intact (it was only demoted, not deleted). Resume writes to AWS.

**Step 8: Decommission AWS resources after a 30-day validation period.**
What you do: Keep the AWS database and S3 buckets intact for 30 days after cutover as a safety net. Monitor for any unexpected access to AWS resources (which would indicate a consumer you missed). After 30 days with no issues, stop AWS replication, archive or delete data per your retention policy, and shut down AWS infrastructure.
Why: A 30-day validation period is long enough to catch monthly batch jobs, quarterly reports, and other infrequent consumers that might not have appeared in the first week.
How to verify: AWS CloudWatch shows zero read or write traffic to the old S3 buckets and database after the first 24 hours following cutover.
Rollback if it fails: During the 30-day period, rollback is possible (the AWS database is still intact). After decommissioning, this is non-reversible.

### Brainstorming Q&A

**Q: During the PostgreSQL schema migration, what is the risk of adding NOT NULL constraints to columns that have already been backfilled, and how do you mitigate it?**

Adding a NOT NULL constraint in PostgreSQL historically required a full table scan to verify that no row has a NULL value in the column being constrained, and this scan required an ACCESS EXCLUSIVE lock — the strongest possible lock, which blocks all reads and writes. For a table with 80 million rows, this could mean several minutes of complete downtime even if the backfill was perfectly executed. PostgreSQL 12 introduced a mitigation: you can add a NOT NULL constraint using the CHECK constraint mechanism with NOT VALID, which skips the table scan and only validates new rows going forward. The existing rows are implicitly trusted to satisfy the constraint. A subsequent VALIDATE CONSTRAINT operation performs the row-level verification but only requires a SHARE UPDATE EXCLUSIVE lock, which allows concurrent reads and most writes. The mitigation is therefore to always use the two-step approach: ADD CONSTRAINT ... CHECK (column IS NOT NULL) NOT VALID, followed later by VALIDATE CONSTRAINT. The "later" in that sequence can be during a low-traffic period, or it can be run immediately if you are confident about the backfill's completeness. The key insight is that separating the constraint addition from its validation allows you to avoid the full ACCESS EXCLUSIVE lock that would previously have been required.

**Q: In the cloud provider migration playbook, why is a 30-day decommission delay recommended rather than shutting down immediately after cutover?**

The 30-day delay serves as a safety net for consumers that are not captured in your pre-migration inventory. Every organization has infrequent jobs that do not run every day or even every week: monthly billing reconciliation jobs, quarterly compliance reports, annual audit data exports, manually-triggered admin jobs that someone runs every few months. If you decommission immediately after a successful cutover, you will not discover these infrequent consumers until they next run and fail — which might be weeks or months later, long after you have deleted the data they depend on. A 30-day delay is calibrated to catch monthly jobs. For high-stakes migrations where quarterly and annual jobs might be relevant, some organizations keep the source environment readable (read-only, not writable) for 90 days. During the delay, you monitor for any access to the old environment's resources, investigate any access immediately, and update the application code to use the new environment. The incremental cost of keeping the old environment running for 30 days is typically small compared to the cost of a data incident caused by an overlooked consumer. One useful technique during the delay period is to gradually restrict access to the old environment: remove write permissions first (to prevent any accidental dual-writing after cutover), then restrict reads to specific IAM roles, making it increasingly inconvenient to access the old environment while still leaving it available for legitimate recovery use.

---

## Part 14: Anti-Patterns and Failure Modes

### Anti-Pattern 1: The Big Bang Cutover

The Big Bang Cutover is the most common migration mistake at every level of engineering, and it is almost always driven by a desire for simplicity and a dramatic underestimation of risk. The pattern looks like this: the engineering team works on the migration in isolation, building the new system or schema until they believe it is "ready." Then on a chosen date, they make a single switch — a deployment, a database failover, a configuration change — that instantly moves all traffic from the old system to the new one. There is no gradual ramp, no shadow period, no intermediate state where the old system is a safety net.

The fundamental problem with the Big Bang Cutover is that it compresses all migration risk into a single moment. Every bug in the new system, every edge case that was not tested, every behavioral difference between old and new — all of these manifest simultaneously at the cutover moment, in front of all users at once. The team has no recourse. There is no partial rollback, because the old system was not designed to coexist with the new one. Rollback requires going backward through the entire migration, which may have left the old system in a state that is no longer consistent.

Real incident example: In 2015, a major European financial services company attempted a big-bang migration of their core banking system from a legacy platform to a new one over a weekend maintenance window. By Monday morning, customers could not access their accounts. The migration had exposed an edge case in interest calculation for accounts that had been opened before a specific regulatory change in 2009. The old system had a workaround for this edge case that had never been documented. The new system did not have the workaround, and the accounts in question — roughly 8% of all accounts — returned incorrect balances. Rolling back took another 48 hours because the weekend migration had touched so many systems. The total customer impact lasted four days, the regulatory fine was significant, and three senior engineers left the company within the following year.

The lesson is not that migrations cannot have a cutover moment — they must have one eventually. The lesson is that the cutover moment should be the smallest possible event in the migration, not the largest. By the time you execute the cutover in a well-designed migration, you have already done 90% of the hard work: the new system has been receiving shadow traffic, parity has been verified, the team has rehearsed the procedure, and the cutover itself is routine. The Big Bang Cutover tries to skip all that preparation and pay the price in production.

### Anti-Pattern 2: Skipping the Contract Phase of Expand-Contract

The contract phase — removing the old behavior after the new behavior is fully adopted — is the most commonly skipped phase in the expand-contract pattern. The reasons for skipping it are understandable: the migration is "working," users are happy, the new behavior is in place, and removing the old behavior requires additional work that feels unnecessary now that the urgent part is done. But indefinitely skipping the contract phase creates its own category of problems.

The accumulation of un-contracted migrations is technical debt that grows exponentially. If you have skipped the contract phase on ten migrations, you now maintain ten old code paths, ten old database columns, ten old API behaviors — all running in parallel with their replacements. Every future change to the system needs to account for all ten old behaviors. Testing is doubled or worse because both paths need coverage. New engineers joining the team spend weeks understanding why there are two columns for the same data and which one is actually used. The documentation inevitably goes stale and stops reflecting reality.

Real incident example: At a large online retail platform, the team had been running expand-contract migrations for three years without systematically executing the contract phase. By the time a new engineering VP audited the codebase, the payment processing module had six different ways to calculate shipping costs — one for each year of "improved" calculations — all six still active, all six tested by different team members, all six producing slightly different results for edge case shipping addresses. A customer in a specific rural zip code had been seeing different shipping cost estimates on different page loads because the random load balancer was hitting servers running different code versions that had the flag for different shipping calculation versions. Nobody had noticed because the discrepancy was only $0.40 and only affected a small geographic area. The fix required a coordinated two-week effort to identify all six calculation paths, determine which one was correct, consolidate to one, and test exhaustively. The engineering effort was more than what executing the contract phase would have cost at any point in the three years.

The organizational solution to skipping contract phases is to make them a tracked requirement in your migration framework. No migration is closed out in your tracking system until the contract phase is verified complete. The engineer who designed the expand phase is responsible for the contract phase unless they explicitly transfer ownership. Regular audits of the codebase should flag any code paths that look like un-contracted migration artifacts.

### Anti-Pattern 3: Not Testing Rollback Before Starting

Many teams design elaborate rollback plans, document them carefully, and then never test whether those plans actually work before starting the migration. The discovery that the rollback does not work is then made in the worst possible circumstances: the middle of a production incident when the team is under pressure, time is critical, and the system is in an undefined intermediate state.

Rollback failures take many predictable forms. The rollback procedure references a database backup that does not actually exist (the backup job had been silently failing for weeks). The rollback procedure assumes a feature flag can be changed instantly, but the flag is stored in a file on the servers that requires a deployment to change. The rollback procedure drops a table that was needed by a service that was not part of the migration but depends on that table. The rollback procedure works on a single-server setup but fails on the distributed production setup because it does not account for all the replicas.

Real incident example: A payments infrastructure team at a mid-sized fintech company planned a migration of their idempotency key database from PostgreSQL to Redis. The rollback plan stated: "If the Redis migration fails, redirect traffic back to PostgreSQL." During the migration, Redis began exhibiting memory pressure under production load — a failure mode they had not seen in load testing. They attempted to execute the rollback. But the rollback assumed that PostgreSQL still had all the idempotency keys, including the ones that had been written during the Redis period. In fact, the migration had been configured to write new keys only to Redis (not as a dual-write), so a significant number of idempotency keys were in Redis only. Rolling back to PostgreSQL would have lost those keys and potentially allowed duplicate payment processing — the exact problem idempotency keys are designed to prevent. The team spent four hours in an emergency meeting deciding whether to roll back (and risk duplicate payments) or stay on Redis (and risk memory exhaustion). They ultimately stayed on Redis and worked through the memory issue. But the root cause was that the rollback had never been tested, so nobody had discovered the missing dual-write gap until the emergency.

### Anti-Pattern 4: Dual-Write Ordering Bugs

Dual-write ordering bugs occur when two concurrent writes to the same record arrive at the old system and the new system in different orders, causing the systems to diverge. This is not a hypothetical concern — it is a real, reproducible failure mode in any dual-write system under concurrent load.

The bug scenario is this: Record R has value V1. Write W1 attempts to update R to V2. Write W2 attempts to update R to V3. Both writes are concurrent. In the old database, due to network timing, W1 arrives first and sets R to V2, then W2 arrives and sets R to V3. Final state in old database: R = V3. In the new database, W2 arrives first and sets R to V3, then W1 arrives and sets R to V2. Final state in new database: R = V2. The two databases now disagree on the value of R, even though both dual-write paths executed correctly. This is a distributed systems ordering problem, not a bug in either individual write.

The standard mitigation is optimistic locking with version numbers. Each write carries the expected version of the record it is modifying. The database rejects a write if the record's current version is not the expected version. A rejected write retries after re-reading the current state. This eliminates ordering races because only one write can succeed at a given version — the other is rejected and forced to retry with the new state as its baseline. The implementation requires adding a `version` column to the table, incrementing it on every write, and including a `WHERE version = expected_version` clause in every UPDATE.

Real incident example: During a storage migration at a document editing platform, the team used dual-write for six weeks without optimistic locking. Their parity verification job ran hourly and found a discrepancy rate of approximately 0.003% — low enough that the team initially dismissed it as a sampling artifact. After the cutover, users began reporting that document edits were being lost. Investigation revealed that the 0.003% discrepancy rate corresponded to roughly 300 documents per day being in the wrong state — not zero, as the team had assumed. The root cause was ordering bugs in the dual-write path for documents with high concurrent edit activity. The fix required replaying all document events from the event log for the affected documents, a three-day engineering effort.

### Anti-Pattern 5: The "Temporary" Compatibility Shim That Becomes Permanent

Every migration has a transition period when compatibility shims are needed — code that translates between old and new behavior to allow both to coexist. These shims are explicitly intended to be temporary: they will be removed when the contract phase is complete. In practice, a disturbingly large percentage of "temporary" shims become permanent fixtures in the codebase.

The mechanism is straightforward. A shim is added during an expand phase. The migration proceeds. The contract phase is delayed for various organizational reasons. The engineer who added the shim moves to a different team. The shim is no longer flagged as temporary in anyone's mental model of the codebase. New engineers read the shim code and assume it is there for a reason. The shim eventually becomes undocumented technical debt with no clear owner and no obvious path to removal.

The compounding effect is severe. A complex shim may have performance implications that are acceptable during a transition period but unacceptable as a permanent fixture. A shim that converts between old and new data formats on every request adds latency that compounds with every additional migration that stacks another shim on top of it. Systems with years of accumulated shims become progressively slower and harder to reason about.

Real incident example: At a large telecommunications company, an authentication system had accumulated compatibility shims for four different token formats over eight years of migration attempts, none of which had reached the contract phase. Every authentication request had to be checked against all four token formats to determine which one was in use. The combined overhead of the four shim checks had grown from negligible to 40 milliseconds per authentication request. Since authentication was in the critical path of every API call in the system, this 40ms overhead was multiplied across billions of requests per day, representing enormous compute cost. The remediation required a dedicated six-month project to complete all four overdue contract phases — work that would have been trivial if executed promptly after each migration.

### Anti-Pattern 6: The Migration That Never Completes

Some migrations begin but never reach completion. They are partially executed, leaving the system in a permanent intermediate state that was designed to be temporary. The dual-write is running but the cutover never happens. The new column is added but the old column is never dropped. The new service is built but the old code path is never removed.

Incomplete migrations create technical debt that is particularly costly because the system is simultaneously maintaining two versions of a capability at full fidelity — twice the code, twice the tests, twice the operational burden — without getting the full benefit of either. The new capability is not fully validated at production scale (because some traffic is still on the old path). The old capability cannot be simplified (because some traffic is still using it). Engineers maintaining the system must understand both implementations.

The organizational root cause of migrations that never complete is almost always a lack of explicit ownership and deadline tracking. When the engineer who started the migration moves to a different project, there is no one left with the context and the mandate to complete it. The incomplete migration sits in the codebase, silently accumulating debt.

The governance solution is to treat migrations as engineering projects with explicit ownership, milestones, and deadlines — tracked in the same system as other engineering work. Each phase of the migration (expand, migrate, contract) is a separate milestone with a committed completion date. The migration owner is explicitly named and cannot be reassigned without also transferring the migration ownership. Leadership visibility into migration status (via dashboards) ensures that stuck migrations are identified and prioritized before they become permanent fixtures.

Real incident example: An e-commerce company began a migration from their custom in-house cache implementation to Redis in Q3 of one year. By Q3 of the following year, 60% of their cache hits were going to Redis and 40% were still going to the old cache. The engineer who had started the migration had been promoted and was now leading a different team. The remaining 40% included several cache types that the new team did not fully understand, and nobody wanted to take responsibility for completing the migration without that understanding. After two more years in this state, a security audit found that the old cache implementation had a known vulnerability that had been patched in Redis but not in the custom implementation. Completing the migration became an emergency, requiring the company to bring back a consultant who had originally written the old cache code to document its behavior and supervise the final migration steps.

### Part 14 Intern to Staff: How Understanding Grows

**Intern level:** May inadvertently commit any of these anti-patterns, particularly the Big Bang Cutover and skipping rollback testing, because they do not yet have the experience to recognize the risk.

**Junior (L3) level:** Has probably experienced the consequences of one of these anti-patterns firsthand (often the Big Bang Cutover or a dual-write ordering bug) and has learned from it. Knows to use expand-contract but may still skip the contract phase under deadline pressure.

**Mid-level (L4) level:** Recognizes all six anti-patterns and consciously avoids them in their own work. Can explain to a junior engineer why each anti-pattern is dangerous and what to do instead. Has implemented rollback drills. Has caught at least one dual-write ordering bug through parity verification.

**Senior (L5) level:** Actively reviews others' migration plans for these anti-patterns and provides concrete feedback. Can quantify the cost of each anti-pattern in operational terms (additional latency, code complexity, incident risk). Has designed and enforced contract phase completion as part of migration governance within their team.

**Staff (L6) level:** Designs organizational structures and processes that prevent these anti-patterns at scale: migration tracking systems with mandatory contract-phase milestones, rollback drill requirements as part of migration approval, code review policies that flag compatibility shims without an associated contract phase milestone, and architectural review for any migration that involves a Big Bang Cutover moment. Has personally been the person who identified a migration-in-progress that exhibited one of these anti-patterns and led the intervention to correct it before it caused a major incident.

### Brainstorming Q&A

**Q: How do you make the case to a product manager that the engineering team needs time to execute the contract phase of a migration, when from their perspective the feature is already "done"?**

This is fundamentally a communication and prioritization problem, and the way you frame it determines whether you get the time. The mistake is to frame it as "technical cleanup" — product managers hear "cleanup" and categorize it as low priority compared to new features. The correct framing connects the contract phase to concrete business outcomes. First, frame it as a performance improvement: running two code paths instead of one adds latency, and eliminating the old path will reduce p99 latency by X milliseconds, improving user experience for Z% of users. Second, frame it as a reliability improvement: maintaining two implementations means twice as many places where a bug can hide, and completing the migration reduces the probability of certain categories of incidents. Third, frame it as a velocity improvement: engineers spend time understanding both the old and new implementations before every change to this area, and completing the migration will reduce the time it takes to make future changes by roughly Y hours per engineer per quarter. If you can quantify these impacts — even approximately — you are speaking the language of business outcomes rather than technical preferences. Most product managers, when presented with a credible argument that a technical task will improve performance, reliability, or engineering velocity, will find a way to schedule it. The failure mode is leaving the business impact implicit and hoping the product manager values "cleanliness" for its own sake.

**Q: A Big Bang Cutover is scheduled for this weekend. You are convinced it is the wrong approach but you are not the decision-maker. What do you do?**

This is an organizational influence problem, not a technical problem, and the approach should be calibrated to how much time you have before the weekend. If you have a week or more, the approach is to write a clear, evidence-based risk assessment: what specifically could go wrong, what the user impact would be, what alternatives exist (gradual rollout, shadow period, rollback drill), and what it would take in terms of engineering time to implement the safer alternative. Share this document with the decision-maker and request a meeting to discuss. You are not saying "you are wrong" — you are saying "I have a concern and here is the evidence, can we talk about it." If the decision-maker reviews your analysis and still decides to proceed with the Big Bang, respect that decision but make sure your concerns are documented. If the timeline is days rather than weeks, you may need to escalate more urgently: can you at least add a shadow period of 24-48 hours before the hard cutover? Can you put a rollback plan in place and test it before the weekend? Can you reduce the blast radius by doing the cutover in one region or for one user segment before going global? The goal is to make the Big Bang safer at the margins if you cannot prevent it entirely. And if the migration proceeds as planned and goes well, you acknowledge that. If it goes poorly, your documented concerns become the foundation for a better process next time — not "I told you so," but "here is what we can do differently in the future."

**Q: How do you detect and quantify the cost of anti-patterns that have been silently accumulating in a codebase for years?**

Detecting accumulated migration anti-patterns requires both automated tooling and deliberate code archaeology. For the automated side: static analysis tools can flag code that matches patterns like "duplicate columns with similar names," "compatibility shim functions," "code paths with a comment containing TODO-remove or temporary-migration," or "feature flags that have been in the codebase longer than six months." For the quantification side: performance profiling can identify latency contributions from shim code, database query plans can reveal the cost of extra columns that are read but not used, and CPU profiles can show the overhead of maintaining two code paths. The harder part is making the cost visible in terms stakeholders understand. A technical audit that produces a list of "42 incomplete migrations and 16 permanent temporary shims" does not automatically create organizational urgency. Translating those findings into "$X in annual compute cost from redundant code paths," "Y hours per sprint of extra engineering overhead from maintaining dual implementations," and "Z incidents per year attributable to complexity from accumulated migration debt" creates urgency because it connects the anti-patterns to outcomes that matter to engineering leadership and product management. This kind of audit is something a staff engineer is well-positioned to lead: they have the cross-system visibility to identify the patterns, the technical depth to quantify the costs, and the organizational credibility to present findings to leadership in a way that results in remediation being prioritized.

---

## Additional Exercises

**Exercise 9:** Design a "migration health dashboard" for a large engineering organization. What metrics would you display? How would you measure the total number of in-flight migrations, the percentage at each phase (expand/migrate/contract), and the average time to completion for each phase? What alerts would you configure? How would you make the dashboard useful to both individual contributors (who need to know their migration's status) and engineering leadership (who need to know overall migration health)?

**Exercise 10:** A junior engineer on your team proposes the following migration plan for removing a deprecated API field: "We will add a deprecation header to the response for 30 days, then remove the field." Critique this plan. What is missing? What could go wrong? Rewrite the plan to address all the gaps, adding steps that the junior engineer did not include.

**Exercise 11:** You have just discovered that a "temporary" compatibility shim in your codebase has been in place for 3 years and is now processing 50% of all API traffic. The engineer who added it left the company 2 years ago. There is no documentation of what it does or why it was added. Write a plan for: (1) safely understanding what the shim does, (2) determining whether it is safe to remove, and (3) executing the removal with appropriate risk mitigation.

**Exercise 12:** You are the migration lead for a migration that has been running for 14 months and is stuck at 75% completion. Six teams have not migrated. Design the escalation plan: what information do you need about each of the six teams, what options do you have for each type of blocker (organizational, technical, resource-based), and what is your escalation path if teams cannot be unblocked within 30 days?

---

## Additional Homework

**Homework 6:** Read the postmortem for any publicly available migration incident (examples: GitHub's 2012 database incident, Cloudflare's 2019 BGP routing table migration, or any AWS incident involving a data migration). Write a 400-word analysis of: which anti-patterns from Part 14 were present in the incident, what the early warning signs were that the team might have caught with better monitoring, and how you would have designed the migration differently to prevent the incident.

**Homework 7:** Build a small proof-of-concept of the parity verification pattern. Set up two SQLite databases with the same schema. Write a simple Python or Go script that performs dual-writes to both databases. Then write a parity verification script that samples 100 random rows from each database and compares them. Intentionally introduce a bug in the dual-write path (e.g., a race condition or an off-by-one error) and verify that the parity verification script detects the discrepancy within a few minutes of it being introduced.

**Homework 8:** Take any publicly documented API deprecation notice (Stripe, GitHub, Twilio, or any major API provider) and evaluate it against the criteria in Part 7. Did the API provider follow the deprecation lifecycle? Did they provide both Deprecation and Sunset headers? Was the timeline reasonable? Was the communication adequate for external developers? Write a two-paragraph assessment of what the API provider did well and what you would have done differently.

---

## Appendix: Migration Pattern Quick Reference

The following table summarizes when to use each migration pattern covered in this chapter. Use this as a reference when designing a migration and deciding which patterns to combine.

```
MIGRATION PATTERN QUICK REFERENCE

Pattern              | Best For                    | Key Risk           | Rollback Difficulty
---------------------|-----------------------------|--------------------|--------------------
Expand-Contract      | Any schema or API change    | Skipping contract  | LOW (per phase)
Dual-Write           | Storage system migration    | Ordering bugs      | MEDIUM
Shadow Mode          | Verifying new behavior      | Performance cost   | LOW
Feature Flag Ramp    | Any traffic cutover         | Flag system down   | LOW (flag flip)
Strangler Fig        | Monolith decomposition      | Data ownership     | MEDIUM-HIGH
Blue-Green DB        | Major version upgrades      | Replication lag    | LOW (keep blue)
Batch Backfill       | Populating new columns      | Replication lag    | LOW (idempotent)
gh-ost               | MySQL schema changes        | Binary log access  | LOW
Rollback Drill       | Pre-migration rehearsal     | Missed assumptions | N/A (planning)
Sunset Deadline      | API deprecation enforcement | Stakeholder mgmt   | N/A (policy)

Anti-Pattern                 | When Teams Fall Into It
-----------------------------|----------------------------------------------
Big Bang Cutover             | Desire for simplicity, underestimating risk
Skipping Contract Phase      | "Good enough" attitude after expand+migrate
No Rollback Testing          | Time pressure, treating rollback as theoretical
Dual-Write Ordering Bugs     | Not using optimistic locking under concurrency
Permanent Temporary Shims    | Incomplete migrations, engineer turnover
Migration Never Completes    | No ownership tracking, no deadline enforcement
```

---

## Expanded Brainstorming Q&A: Parts 1 Through 11 Supplemental Questions

This section adds one additional full brainstorming question per Part to extend the depth of coverage. Each answer is written at the 130-150% depth level appropriate for L6 interview preparation.

### Part 1 Supplement: Why Live Migrations Are Hard

**Q: How does a company's stage of growth affect the migration patterns it should use? Is expand-contract equally valuable for a 10-person startup as for a 10,000-person company?**

The expand-contract pattern has different costs and benefits depending on organizational scale, and a thoughtful engineer should tailor their approach accordingly. For a 10-person startup, the cost of full expand-contract rigor may genuinely outweigh the benefit. The startup has one or two services, perhaps one or two engineers working on any given system at a time, and the ability to coordinate changes across the entire engineering organization in a single afternoon meeting. In this context, a carefully timed "coordinated deploy" — where all engineers simultaneously deploy changes that switch from old to new — may be lower risk than the overhead of building and maintaining dual code paths for weeks. The startup also typically has less production traffic, meaning that a brief outage causes less damage and is noticed by fewer users. The startup's most important risk is moving too slowly to find product-market fit, and excessive migration rigor can slow velocity.

For the 10,000-person company, the calculus flips entirely. There are hundreds of services with complex interdependencies. Changes propagate slowly through the deployment pipeline. There is always a version skew between services — different instances are running different code versions at any given moment. In this environment, attempting a coordinated deploy means coordinating hundreds of engineers deploying thousands of service instances simultaneously, which is operationally impossible. Expand-contract is not optional at this scale — it is required by the physical impossibility of simultaneous change. Additionally, the large company has significantly more production traffic, making even brief outages extremely costly, and has SLA commitments that often explicitly prohibit planned downtime. The overhead of running dual code paths for a few weeks is trivially small compared to the cost of a production incident from an uncoordinated change.

The practical guidance is: adopt the migration discipline that is slightly ahead of your current pain point, not the one designed for a company 10 times your size. If you are a startup that has never experienced a migration-related incident, start with good practices but do not build the full gh-ost-based migration framework. If you are a mid-size company that has had two migration incidents in the past year, now is the time to invest in the organizational discipline and tooling that prevents the third. Scaling the rigor to match the risk is itself a form of engineering judgment.

### Part 2 Supplement: The Expand-Contract Pattern

**Q: What do you do when the expand phase itself requires a breaking change — that is, when you cannot even add the new capability without first modifying something that existing consumers depend on?**

This scenario, sometimes called a "bootstrap problem" in migrations, requires a careful analysis of the dependency graph to find a valid ordering of changes. The key insight is that the expand phase only needs to be non-breaking from the perspective of the current consumers — it does not need to be zero-effort. Often, what appears to be a breaking change in the expand phase can be decomposed into a sequence of smaller steps where each step is independently non-breaking.

Consider an example: you need to migrate a REST API from using integer user IDs to using UUIDs. Existing clients send integer IDs in requests and parse integer IDs from responses. It appears that you cannot add UUID support without also being able to accept integer IDs in incoming requests (otherwise existing clients break) and also be able to return integer IDs in responses (otherwise existing clients break when parsing). This seems circular — you need UUID support to migrate, but supporting UUIDs requires changes that break existing clients.

The resolution is to identify what actually breaks and what does not. Adding a UUID field to the response alongside the existing integer ID field is not breaking — old clients simply ignore the UUID field. Adding UUID acceptance on the input side with the integer ID still required is also not breaking — old clients continue to send integer IDs. The "breaking" part is only when you make integer IDs optional (allowing UUID-only requests) or when you remove integer IDs from responses. By separating those steps — add UUID output, add UUID input as optional, update all clients to use UUID, then make integer input optional, then remove integer from output — you find a valid non-breaking expansion path that looked impossible when viewed as a single change. The skill of finding this path is one of the distinguishing marks of a senior engineer: the ability to decompose an apparently atomic breaking change into a sequence of non-breaking incremental steps.

### Part 3 Supplement: Zero-Downtime DB Schema Migrations

**Q: How would you approach migrating a column's data type from VARCHAR(255) to TEXT in a table with 200 million rows, where the column has 15 indexes referencing it?**

A data type change on a heavily indexed column is one of the most dangerous schema migration operations because it potentially requires rebuilding every index that references the column, in addition to possibly rewriting the table itself (depending on the database engine and the specific type change). The approach requires understanding the database engine's behavior precisely before making any moves.

In PostgreSQL, changing VARCHAR(255) to TEXT is actually free in most modern versions. Since PostgreSQL 9.2, you can change VARCHAR to TEXT or from VARCHAR(N) to VARCHAR(M) where M > N without rewriting the table, because the internal storage is the same — the difference is only in the constraint applied on write. This specific migration is therefore a metadata-only operation. However, the 15 indexes would need to be rebuilt if the change required a table rewrite. The safe approach is to first check the PostgreSQL documentation to confirm the specific type change requires no table rewrite, then apply the change during a low-traffic window and monitor for any lock wait events.

In MySQL, the situation is more complex. MySQL often rewrites the entire table for type changes, and this would require using gh-ost to perform the change safely. The gh-ost approach creates a shadow table with the new column type, copies all rows to the shadow table (transforming the column type during the copy), rebuilds all 15 indexes on the shadow table, and then does an atomic table swap. The 15 indexes mean that the shadow table creation phase will take significantly longer and use significantly more disk space than a table with fewer indexes. You would need to ensure that disk space is available for the shadow table (roughly equal to the size of the original table plus index overhead) before starting. You would also want to identify whether any of the 15 indexes are actually used by production queries — an unused index is extra cost in every migration and should be considered for removal before the migration rather than rebuilt as part of it. The migration plan should include an index audit step that queries slow query log data to identify unused indexes, dropping them before starting the gh-ost migration to reduce its cost.

### Part 4 Supplement: The Dual-Write Pattern

**Q: How would you design dual-write for an event-driven system where writes are not HTTP requests but messages on a Kafka topic?**

Event-driven systems require a different implementation of dual-write than request-response systems, because the write path is not a function call in application code but a message published to a Kafka topic. The pattern still applies — you want messages to be consumed by both old and new consumers during the transition period — but the mechanics are different.

The most common approach is to use Kafka's consumer group mechanism to create two separate consumer groups for the topic: one consuming on behalf of the old system, and one consuming on behalf of the new system. Both consumer groups read the same messages from the same topic, but apply them independently to their respective data stores. This is the Kafka-native equivalent of application-level dual-write, and it has a significant advantage: there is no write ordering problem, because both consumer groups read from the same ordered Kafka partition. Messages arrive in exactly the same order for both consumer groups. This eliminates the primary source of dual-write divergence that affects request-response systems.

The challenges are different in an event-driven dual-write. First, consumer offset management: the old and new consumer groups maintain separate offsets, so they can fall behind independently. If the new consumer group falls behind due to processing errors, the old system continues working while the new system catches up — but during this period, the new system has stale data. You need to monitor consumer lag for both groups, not just one. Second, schema evolution: Kafka messages typically have a schema (enforced by Schema Registry), and the new consumer may need a different schema version than the old consumer. Kafka's Schema Registry supports schema evolution, but you need to design the new consumer to handle both old and new message schemas during the transition period. Third, backfill: unlike in database dual-write where a backfill job can run against the old database, in Kafka you can only backfill by re-consuming historical messages from the topic. This requires either that the topic has an appropriate retention period (long enough to include all historical messages you need) or that you supplement Kafka replay with a separate bulk data load from the old system's database. The migration plan should account for the Kafka topic retention period when planning the backfill strategy.

### Part 5 Supplement: The Strangler Fig Pattern

**Q: What is the relationship between the strangler fig pattern and service mesh technology? Can a service mesh replace the custom proxy layer?**

The service mesh (technologies like Istio, Linkerd, or AWS App Mesh) provides infrastructure-level traffic management capabilities that overlap significantly with what the strangler fig proxy layer needs to do. A service mesh can perform traffic routing based on HTTP headers, percentage-based traffic splitting, canary deployments, circuit breaking, and retry logic — all of which are useful in a strangler fig migration. In principle, a service mesh can serve as the proxy layer for a strangler fig migration, routing requests to either the legacy system or the new service based on configurable routing rules, without requiring a custom-built proxy application.

The advantage of using a service mesh for this purpose is that it provides a standardized, well-tested implementation of traffic management with a rich control plane API, removing the need to build and maintain custom proxy code. The disadvantage is that service meshes add operational complexity (another system to deploy, configure, monitor, and upgrade), and they require that all services in the mesh run in a mesh-compatible environment (typically Kubernetes sidecars). Service meshes also operate at the network layer, which means they can route traffic but cannot transform the payload — a request goes to either the old service or the new service, but the service mesh cannot translate between the old API format and the new API format. If the strangler fig migration requires any request or response transformation (which is common when the new service has a different API than the legacy system), you still need some application-level logic, even if the routing itself is handled by the service mesh.

The practical design for most teams is to use a service mesh for the routing layer (percentage-based traffic splitting, header-based routing, canary deployments) and implement any necessary request/response transformation in a thin application-layer adapter that sits between the service mesh sidecar and the actual service logic. This hybrid approach gets the operational benefits of the service mesh for routing while keeping transformation logic in application code where it can be tested, versioned, and reasoned about independently of the infrastructure.

### Part 6 Supplement: Feature-Flag-Driven Cutover

**Q: How do you handle the user experience problem where a user sees inconsistent behavior because they are in the 5% bucket for one feature flag but not another?**

This is the "flag interaction" or "flag consistency" problem, and it is one of the most underappreciated challenges in feature-flag-driven migrations. When multiple feature flags are active simultaneously — each at different percentages — users can end up in different buckets for each flag, producing a combination of behaviors that was never tested together and may be incoherent from a user experience perspective.

Imagine a user who sees the new checkout flow (which they are in the 20% bucket for) but also sees the old payment options panel (because they are not in the 10% bucket for the payment options migration). The checkout flow was designed to work with the new payment options panel. The two together produce a UI that was never validated and may have visual inconsistencies or broken interactions. The user files a bug report. The engineering team cannot reproduce the bug because they are testing with either both new flags on or both off — they never tested the combination the affected user experienced.

The solution has two parts. First, for tightly coupled features, use a single feature flag rather than multiple independent flags. If the checkout flow and payment options panel must always be in the same state, they should be controlled by one flag, not two. Second, for features that are partially coupled, use flag dependencies: if flag B (payment options) is enabled for a user, automatically enable flag A (checkout flow) for that user as well. This is sometimes called "flag prerequisites" in feature flag systems. The implementation typically requires storing the user's flag bucket assignments and enforcing prerequisite relationships when evaluating flag state. LaunchDarkly, Split.io, and most mature flag systems support prerequisite flags out of the box. For custom-built flag systems, this needs to be explicitly designed. At a minimum, the flag evaluation logic needs to be able to read multiple flag states and enforce coherence before returning a result, rather than evaluating each flag independently.

### Part 7 Supplement: API Migrations

**Q: How do you manage API migration across mobile clients that you do not control — where the client version in the field can be years behind the current version?**

Mobile client version management is one of the hardest problems in API deprecation because the migration lead does not control when users update their apps. A user might still be running a three-year-old version of your mobile app, and that version is making API calls that depend on deprecated fields you would like to remove. Unlike internal services or web clients — where you can force an upgrade by deploying new code — mobile apps require users to proactively update through the App Store or Play Store. Forced app updates are possible (you can require a minimum version to access the app) but are a significant user experience disruption and should be reserved for security emergencies.

The practical approach has several components. First, use analytics to understand your client version distribution. What percentage of API requests come from clients older than N months? For most consumer apps, 95% of users are on a version from the past six months, and 99% are on a version from the past 12 months. Clients older than 12 months are a very small tail — but "very small" can still be tens of thousands of users for a large app. Second, set API deprecation timelines that align with the observed version churn rate. If 99% of users are on a version less than 12 months old, a deprecation with a 12-month sunset allows 99% of users to have naturally upgraded before the sunset. Third, use the Sunset HTTP response header (RFC 8594) and Deprecation header to communicate the sunset date to any API client that is aware of these headers — third-party clients and sophisticated integrations will respect these. Fourth, for mobile-specific communication, send push notifications or in-app messages to users on old app versions informing them that they need to update before a certain date. This is the closest equivalent to an API client deprecation notice for mobile users.

For the 1% of users who are still on very old versions after all of this, you have a policy decision: do you force them to update (by blocking the deprecated API and showing an "update required" screen) or do you maintain the deprecated API indefinitely for them? Most companies with large user bases choose to set a hard cutoff at the 99th percentile or 99.9th percentile of version age, accept that the very long tail of old clients will break, and invest in customer support to help the affected users upgrade. The alternative — maintaining deprecated APIs indefinitely for the 0.1% of users on very old clients — has a compounding cost that grows with every new deprecation cycle.

### Part 8 Supplement: Infrastructure Migrations

**Q: How do you manage the cost implications of running two infrastructure environments in parallel during a long migration?**

Running two full infrastructure environments simultaneously — the old system and the new system, both sized for production traffic — can double your infrastructure costs for the duration of the migration. For large systems, this can represent millions of dollars per month. Managing these costs requires deliberate planning that begins before the migration starts.

The first cost control strategy is to right-size the parallel environment for its actual role. During the early phases of the migration, the new environment is receiving no production traffic (or very little). It does not need to be sized for full production load — it needs to be sized for the backfill traffic, the shadow read traffic, and the low-percentage canary traffic it is actually handling. A new environment that is 20% of production size costs 80% less than a full-sized environment, and it is perfectly adequate until you start ramping real traffic to it. Design a capacity scaling plan that grows the new environment in parallel with the traffic migration ramp. When you shift 20% of traffic to the new environment, the new environment should be sized for 20-25% of production load (with some headroom for traffic spikes).

The second strategy is to decommission the old environment quickly after cutover. The temptation is to keep the old environment running indefinitely "just in case." But maintaining the old environment at full size for months after cutover is expensive and provides diminishing safety benefit over time. Define a decommission schedule at the start of the migration: the old environment will be decommissioned 30 days after cutover (or 60 days for very large, complex migrations). During that window, keep the old environment available for emergency rollback but scale it down to a warm standby configuration — perhaps 25% of its normal size — which significantly reduces cost while maintaining rapid recovery capability. After the decommission window, shut it down completely. Treating the old environment as a temporary safety net with a defined end date, rather than an indefinite parallel system, is the difference between a migration that has a manageable cost profile and one that doubles your infrastructure budget for a year.

### Part 9 Supplement: The Rollback Protocol

**Q: How do you design a rollback protocol for a migration that involves regulatory data — data that, once deleted or modified, cannot be recreated and may have legal hold requirements?**

Regulatory data — financial transaction records, healthcare records, audit logs, data subject to legal hold — adds a dimension to rollback protocol design that most migration plans underestimate. The core challenge is that standard rollback procedures often involve operations that cannot be safely applied to regulatory data: deleting rows, overwriting records, or discarding intermediate states.

The first principle for regulatory data migrations is to treat deletion as a permanent, irreversible operation that requires an extraordinary level of approval. No rollback procedure for regulatory data should involve deleting rows that have already been committed. Instead, rollbacks should be accomplished by adding new records (correcting bad data with a subsequent correction record, not by overwriting the bad data) or by marking records as superseded rather than removing them. This is consistent with how regulated industries handle data correction: an error in a financial ledger is corrected by an offsetting entry, not by erasing the original entry.

The second principle is to archive rather than drop during the contract phase. When you are removing old columns or old tables that contain regulatory data, the contract phase should not delete that data. Instead, it should archive it to a long-term storage tier (cold storage, a regulatory archive database, or an archival data warehouse) with appropriate retention labels. The regulatory data must be retained for its required period — often 7 years for financial data, longer for some healthcare data — regardless of whether the migration has completed. The migration plan must include explicit steps for archiving regulatory data and explicit sign-off from legal or compliance that the archiving approach meets the retention requirements. A migration that deletes regulatory data prematurely creates legal exposure that no engineering excellence can undo.

### Part 10 Supplement: Staff Engineer Migration Leadership

**Q: How do you lead a migration when you are a staff engineer embedded in a product organization, and the migration is seen as infrastructure work that "should be handled by platform teams"?**

This is a common organizational friction in companies that have both product teams and platform teams. The migration you need to lead crosses both domains: it requires platform teams to build new infrastructure, and product teams to migrate their services to that infrastructure. Neither type of team has full ownership, and without a clear owner, migrations stall.

The staff engineer's role in this situation is to act as the integration point between platform and product — the person who understands both domains deeply enough to speak credibly to both, and who can hold both accountable to the migration timeline. The first step is getting explicit organizational sponsorship: a VP or director-level leader who has authority over both the platform teams and the product teams, and who publicly endorses the migration as a priority. Without this sponsorship, the migration will be deprioritized by each team in favor of their local priorities. With it, the staff engineer has a mandate to enforce timelines and escalate blockers.

The second step is designing the migration so that each team's contribution is as self-contained and independent as possible. The worst case is a migration where Team A cannot start until Team B finishes, and Team B cannot start until Team C finishes — a sequential dependency chain where any delay cascades into every subsequent team's timeline. The better design parallelizes as much of the work as possible, with a clear API contract between platform and product teams that allows both to work simultaneously. Platform builds the new infrastructure and publishes its API. Product teams build against the API spec (using stubs or test environments) and are ready to integrate the moment the real platform is available. This parallel-track approach reduces the total calendar time and reduces the dependency risk. The staff engineer's job is to design and enforce these parallel tracks, and to be the person who resolves any interface disagreement between platform and product before it blocks either track.

### Part 11 Supplement: Interview Application

**Q: An interviewer asks you to design a system for managing database migrations across 500 microservices in a large organization. How do you approach this problem?**

This is an L6-level system design question because it is not about how to execute a single migration — it is about how to build infrastructure that makes migrations safe and manageable at organizational scale. The answer requires thinking at the meta-level: what are the common failure modes across all migrations, and what infrastructure eliminates them?

The migration management system needs to address four key concerns. The first is schema version tracking: every database instance needs a reliable record of which migrations have been applied and which are pending. This is the core function of tools like Flyway and Liquibase, and your system should build on one of them rather than reinventing the metadata store. Each microservice has its own migration history table in its own database. The system aggregates these histories into a central dashboard that shows the migration status of every service.

The second concern is migration execution safety: how do you ensure that a migration script does not accidentally drop a table or lock production? The system should include a pre-execution linter that checks migration scripts for known dangerous patterns (CREATE INDEX without CONCURRENTLY in PostgreSQL, ALTER TABLE on tables above a size threshold without using gh-ost, DROP COLUMN without a preceding grace period for verification) and either blocks the migration or requires an explicit override. This automated safety check catches the most common mistakes before they reach production.

The third concern is coordination and dependency management: some migrations across 500 microservices have dependencies (Service A cannot migrate until Service B has migrated its shared library, for example). The system needs to model these dependencies and enforce them — not just track them. When Service A's migration is queued, the system checks that Service B's prerequisite migration has completed before allowing Service A's migration to proceed.

The fourth concern is rollback orchestration: for any migration that is in progress, the system should be able to generate and execute the rollback procedure, which may involve multiple coordinated rollback steps across multiple services. The rollback procedure is defined at migration creation time (not at incident time) and is stored alongside the migration itself. A single button in the dashboard should trigger the rollback for a failing migration, with the system handling the coordination and sequencing automatically. This turns a high-stress incident into a well-defined operational procedure.

---

## Connecting Chapters: What Comes Before and After

Understanding migrations in isolation is not sufficient for L6 interview preparation. Migrations connect to several adjacent concepts that frequently appear in the same interview conversation. Here is how to think about those connections.

**Migrations and Consistency Models (Chapter 82-83 territory):** Every dual-write migration is making an implicit consistency trade-off. During the transition period, the old system and new system may have slightly different views of the same data. Whether this is acceptable depends on the consistency model your system needs. For systems that require strong consistency (financial ledgers, inventory counts), even a brief divergence between old and new systems may be unacceptable, and the migration design needs to use synchronous dual-write with distributed transaction semantics or a very short migration window. For systems where eventual consistency is acceptable (user profile data, recommendation data), the dual-write period can be longer and the parity verification can be more relaxed. Naming the consistency model your system requires and connecting it to specific migration design choices is a sign of L6 thinking.

**Migrations and Observability (Chapter 95 territory):** The monitoring infrastructure you need during a migration is more sophisticated than your steady-state monitoring. You need to be able to compare metrics between old and new behavior simultaneously, detect divergence in parity verification, track backfill progress at a fine-grained level, and correlate any user-reported issues with the specific phase of the migration that was active at the time of the issue. Describing how you would build this migration-specific observability — what metrics you would add, what dashboards you would create, what alerts you would configure — demonstrates that you understand migration execution as a data-driven process, not just a procedural one.

**Migrations and Deployment Systems (Chapter 96 territory):** The deployment system is the mechanism by which migration changes are progressively rolled out to production. The feature flag ramp described in Part 6 is only possible if the deployment system supports fine-grained traffic control. The ability to quickly roll back a migration phase depends on how fast the deployment system can propagate a configuration change to all instances. Describing the coupling between your migration strategy and your deployment system capabilities is something interviewers at L6 level will probe: how does your canary deployment system integrate with your migration feature flags? How do you handle the case where a migration needs to be rolled back but the rollback requires a new code deployment that goes through the standard deployment pipeline?

**Migrations and Data Governance:** Not all the content in this chapter is strictly technical. The organizational and governance dimensions of migrations — who approves a migration plan, what review process a schema change requires, how you track the completion of contract phases, how you enforce sunset deadlines — are equally important for an L6 engineer operating at the intersection of technology and organization. Being able to discuss these governance dimensions naturally, not as an afterthought, signals that you have operated at the level of organizational complexity where technical excellence is necessary but not sufficient.

---

## Final Calibration: What Separates Good From Great

In an interview setting, every candidate who has prepared adequately can name the patterns: expand-contract, dual-write, strangler fig, feature flag ramp. The patterns themselves are not secret knowledge — they are in books, blog posts, and conference talks. What separates a great interview performance from a good one is not pattern recognition. It is the quality of the reasoning applied when patterns meet constraints.

Great candidates connect patterns to constraints before describing implementation. They do not start with "I would use dual-write" — they start with "the key constraint here is that we cannot afford any data loss, and we have a three-month migration window, so let me think about which approach gives us continuous parity verification while keeping rollback simple." The pattern selection falls out of the constraint analysis, not the other way around.

Great candidates define failure modes before describing success paths. They do not wait for the interviewer to ask "what could go wrong?" — they proactively identify the two or three most dangerous moments in their proposed migration and describe exactly how they would detect a problem and what they would do. This demonstrates that they have thought through the migration end-to-end, not just designed the happy path.

Great candidates quantify. They do not say "the backfill might be slow" — they say "at 1,000 rows per batch with a 50ms pause, processing 100 million rows will take approximately 84 hours, which means we need to start the backfill Thursday if we want it complete by Monday." Quantification shows that the candidate has actually thought through the execution, not just described it at a high level.

And great candidates know when to challenge the premise. The question "how would you add a NOT NULL column to a 100M-row table?" has a standard answer. But the L6 candidate also asks: why does this column need to be NOT NULL? Could a default value work instead? Is the 100M-row table itself a design smell that we should fix rather than work around? Challenging the premise — without dismissing the question — demonstrates architectural maturity: the recognition that the most important migration is sometimes the one you find a way not to do.

---

## Part 15: Migration Monitoring and Observability

### Why Migration Monitoring Is Different from Steady-State Monitoring

Your steady-state monitoring is designed to detect problems with a system behaving in a known, expected way. Alert thresholds are tuned to the system's normal operating characteristics. Dashboards show the metrics that matter for a system at a stable operating point. Migration monitoring is fundamentally different because the system is deliberately changing state. Some metrics will look unusual during migration — not because something is wrong, but because the migration itself is causing expected changes. Other metrics need to be compared between two different systems simultaneously. And new metrics that have never mattered before suddenly become critical: backfill progress, replication lag between old and new systems, parity mismatch rate, percentage of traffic on new versus old behavior.

The failure to build migration-specific monitoring before starting a migration is a common but costly mistake. When a problem occurs during a migration and you have only steady-state dashboards available, you are flying blind. You cannot tell whether elevated error rates are coming from the old path or the new path. You cannot tell whether replication lag is trending toward zero or trending toward thirty seconds. You cannot tell whether parity verification is passing or failing. All of these require instrumentation that was deliberately added for the migration, not inherited from the steady-state setup.

The rule of thumb practiced by experienced migration engineers is: build the migration dashboard before the first line of migration code is deployed. The dashboard should be live and showing data before any migration-related change touches production. This ensures that you have a baseline of what "normal" looks like for migration metrics, making it immediately obvious when something deviates from normal during the migration itself.

### The Migration Metrics Taxonomy

Migration metrics fall into four categories, each serving a different purpose.

**Phase progress metrics** tell you how far along the migration is and when it will complete. For a backfill migration: rows backfilled, rows remaining, estimated time to completion based on current rate. For a dual-write migration: percentage of traffic on new system, percentage of reads switched. For a strangler fig migration: percentage of API endpoints migrated, percentage of traffic handled by new service. Phase progress metrics tell you "are we on track?" and help you communicate status to stakeholders who need to plan around the migration timeline.

**Health metrics** tell you whether the migration is executing safely at this moment. These are the metrics you watch during active migration steps — the ones with rollback triggers attached. For a backfill: replication lag on the database replicas, write error rate, p99 write latency, lock wait rate on the table being backfilled. For a dual-write: error rate on writes to the new system, divergence rate detected by parity verification, message queue depth if using async dual-write. Health metrics need to be monitored in real time during migration steps, with automated alerts set significantly below the rollback trigger thresholds so that humans have time to investigate before the automatic rollback is triggered.

**Parity metrics** tell you whether the old system and new system have the same data. Parity mismatch rate (percentage of sampled records where old and new disagree), parity mismatch by category (are mismatches concentrated in certain record types?), and parity mismatch trend (is the rate going up, down, or stable?) are the key parity metrics. A parity mismatch rate that starts low and trends upward during a dual-write migration indicates a systematic divergence — something in the dual-write path is consistently producing different results in the two systems — and requires immediate investigation. A stable low mismatch rate may indicate acceptable eventual-consistency lag or may indicate a systematic but slowly-accumulating divergence; it needs to be compared against the parity verification sampling rate to distinguish the two.

**Business metrics** tell you whether the migration is affecting user experience. These are the same business metrics you would monitor for any major production change: transaction success rate, checkout completion rate, user signup completion rate, API error rate from external clients. The key is to segment these metrics by which system the traffic was routed to during that request — old system versus new system. If the new system has a lower checkout completion rate than the old system, that is a critical signal that something is functionally wrong with the new system that must be investigated before the traffic ramp proceeds.

```
Migration Monitoring Framework

PHASE PROGRESS METRICS (check hourly)
  - Rows backfilled: X of Y (Z% complete)
  - Estimated completion: N hours at current rate
  - Traffic on new system: X% (target: 100%)
  - APIs migrated: X of Y endpoints

HEALTH METRICS (watch in real time, automated alerts)
  - Replication lag: [THRESHOLD: < 5 seconds] ROLLBACK at 30s
  - Write error rate: [THRESHOLD: < 0.1%] ROLLBACK at 1%
  - p99 write latency: [THRESHOLD: < baseline+50ms] ROLLBACK at +150ms
  - Lock wait rate: [THRESHOLD: < 5/sec] ROLLBACK at 50/sec

PARITY METRICS (check every 15 minutes)
  - Parity mismatch rate: [ACCEPTABLE: < 0.01%]
  - Mismatch by category: [INVESTIGATE any category > 0.1%]
  - Mismatch trend: [ALERT if upward trend for 2+ hours]

BUSINESS METRICS (compare old path vs new path)
  - Transaction success rate: OLD=X%, NEW=Y%
  - API error rate external: OLD=X%, NEW=Y%
  - p99 user-facing latency: OLD=Xms, NEW=Yms
  [ROLLBACK if NEW is worse by >5% on any key metric]
```

### Alerting Strategy During Migrations

Migration alerts need a different strategy than steady-state alerts for two reasons. First, some normal-looking alert conditions are actually expected during a migration (e.g., write latency may be slightly higher because of dual-write overhead). Second, some migration-specific conditions are critically important but would never fire on a steady-state alert (e.g., replication lag between old and new systems).

The approach is to create a separate "migration alerts" namespace in your alerting system with alert rules that are specifically calibrated for the migration context. These alerts are active only while the migration is running and are deactivated after the migration is complete. The alert thresholds are set based on what is acceptable during the migration, not what is normal in steady state. For example, if p99 write latency in steady state is 20ms, the steady-state alert might fire at 50ms. During dual-write, you expect an additional 10ms of overhead, so the migration alert fires at 60ms — acknowledging the expected overhead while still catching unexpected degradation.

Importantly, migration alerts should be routed to a dedicated channel (Slack, PagerDuty, etc.) that the migration team is actively monitoring. Routing migration alerts to the same channel as all other production alerts risks them being lost in the noise during a busy period. The migration team needs to see their migration alerts immediately and without filtering.

### The Migration Runbook

Every migration should have a runbook — a step-by-step operational document that the team executing the migration follows. The runbook is not the same as the migration design document. The design document explains the why and the strategy. The runbook explains the exact steps, the exact commands, the exact verification queries, and the exact rollback steps — in the order they are executed.

A well-written migration runbook has the following properties. It is complete: every step is written out explicitly, with no "you know what to do here" gaps. An engineer who has never seen the migration before should be able to execute it from the runbook alone. It is ordered: steps are numbered and must be executed in sequence, with any parallelism explicitly noted as "these three steps can be executed simultaneously." It is verifiable: each step includes the specific query, metric, or test that confirms the step was successful before proceeding to the next. It includes rollback: for each step that changes system state, the rollback step is written immediately below it. It includes contacts: who to call if something goes wrong at this step, including escalation paths for the specific types of problems this step could encounter. And it is rehearsed: the runbook was used during at least one rollback drill before the production migration, so the team knows from experience that it works.

A runbook that has never been rehearsed is likely to have gaps. Commands that were written from memory may have wrong flags. The verification query may test the wrong thing. The rollback step may have a dependency that was not documented. Rehearsing the runbook — even in a scaled-down environment — catches these gaps before they become production problems.

### Intern to Staff: Migration Monitoring Understanding

**Intern level:** Uses the existing production dashboards to watch a migration. Does not add migration-specific metrics. Discovers missing observability only when something goes wrong.

**Junior (L3) level:** Adds basic migration progress metrics (rows backfilled, percentage complete) before starting. Knows to watch replication lag during backfill.

**Mid-level (L4) level:** Builds a dedicated migration dashboard before starting any migration step. Sets explicit rollback triggers on health metrics. Runs parity verification and includes its results in the dashboard.

**Senior (L5) level:** Designs the full monitoring framework for the migration including all four metric categories. Writes the migration runbook with explicit verification steps. Defines the alert routing strategy for migration alerts. Conducts a monitoring readiness review before starting the migration.

**Staff (L6) level:** Defines the organization-wide standard for migration monitoring. Builds reusable monitoring templates that teams can adapt for their specific migrations. Reviews monitoring plans for major migrations and identifies gaps. Has experienced situations where insufficient monitoring during a migration delayed problem detection and can communicate this experience to drive adoption of better practices across teams.

### Brainstorming Q&A

**Q: How do you build parity verification for a migration where the two systems have different data representations — for example, the old system stores timestamps as Unix epoch integers and the new system stores them as ISO 8601 strings?**

Parity verification across different data representations requires building a normalization layer in the verification system that converts both representations to a canonical form before comparison. In the timestamp example, you would write a normalization function that converts Unix epoch to a canonical representation (perhaps UTC datetime with microsecond precision), and the same function converts ISO 8601 strings to the same canonical representation. The parity check compares the canonical forms, not the raw stored values. This normalization layer needs to handle all the known representational differences between old and new systems, and it needs to be tested independently: you should have unit tests that verify the normalization function produces identical canonical forms for values that are semantically equivalent but representationally different. The normalization layer also needs to account for precision differences: if the old system stores seconds and the new system stores milliseconds, a parity check that compares the raw values will show false mismatches for every row. The canonical form needs to be defined at the precision of the less precise system, or the comparison needs to truncate the more precise representation before comparing. If there are many such representational differences between old and new systems, the normalization layer becomes a significant piece of logic in its own right — it is essentially encoding the semantic mapping between the two data models. This mapping should be documented, reviewed, and tested as carefully as the migration code itself, because a bug in the normalization layer will produce false passes (missed divergences) in the parity verification, which is the worst possible failure mode.

**Q: During a migration, you notice that parity verification is showing a 0.5% mismatch rate, steady over 6 hours. The migration deadline is tomorrow. What do you do?**

A 0.5% mismatch rate that is steady over 6 hours is a significant problem that cannot be dismissed, and the deadline pressure is not a valid reason to proceed despite it. Here is the reasoning. At 0.5% mismatch rate, if you have 100 million records in the system, 500,000 records are incorrect in the new system. Cutting over reads to the new system tomorrow would immediately expose those 500,000 records to users, producing visible errors, data integrity issues, or silent incorrect behavior depending on what data the records contain. No migration deadline is worth that outcome. The right response has three parts. First, immediately investigate the root cause: is the 0.5% concentrated in a specific table, a specific field, a specific time range of records, or is it uniformly distributed? Concentration helps narrow the cause. Second, characterize the severity: are the mismatched records in a high-criticality area (financial data, user authentication, permissions) or a low-criticality area (user preferences, analytics data)? This determines the urgency of the fix. Third, communicate to stakeholders immediately that the migration deadline needs to be extended: you have found a data quality problem that requires investigation and a fix, and proceeding on the original timeline would cause user impact. Then fix the root cause, re-run parity verification to confirm the fix worked, and extend the migration timeline by whatever is needed for the fix plus a new 24-hour clean parity verification period. Stakeholders who understand migration engineering will respect this decision; those who push to proceed anyway are not understanding the risk, and it is the staff engineer's job to clearly communicate what the consequences of proceeding would be.

---

## Part 16: Organizational Patterns for Migration Programs

### When a Migration Becomes a Program

A single migration that one team can execute in a week does not need program management. But a migration that requires changes across twenty services, involves five different teams, depends on a new infrastructure platform, and will take nine months to complete — that migration is a program. And programs require a different set of organizational patterns than individual engineering tasks.

The signal that a migration has become a program is typically one or more of these: more than three teams need to make changes, the migration has dependencies that span organizational boundaries (your team's work is blocked by another team's work and vice versa), the migration has a meaningful business impact that requires leadership visibility and communication to external stakeholders, or the migration timeline extends beyond one quarter. When these signals are present, treating the migration as an informal engineering task is the most common source of delay and eventual abandonment.

A migration program needs a program lead — typically a staff engineer or a technical program manager paired with a staff engineer. The program lead owns the overall migration timeline, tracks dependencies across teams, escalates blockers, and provides regular status updates to leadership. Without a single owner, nobody has the full picture of the migration's status, and problems in one team's work are invisible to other teams until they become blocking dependencies.

### The Migration RFC Process

For large migrations, the pattern of writing a Request for Comments (RFC) document before starting is invaluable. A migration RFC is a structured document that describes the problem, the proposed migration strategy, the alternatives considered, the risks and mitigations, the timeline, and the team dependencies. It is circulated to all affected teams and stakeholders for review and comment before implementation begins.

The RFC process serves several purposes. It forces the migration design to be made explicit and written down, rather than existing only in the heads of the migration's authors. It gives affected teams the opportunity to identify issues they see from their vantage point that the migration authors might have missed. It creates organizational consensus: when everyone has had the opportunity to comment and the RFC has been finalized, there is no room for teams to later claim they were surprised by the migration or that they disagree with the approach. And it creates a historical record: future engineers can read the RFC to understand why the migration was designed the way it was and what alternatives were considered and rejected.

The RFC should specifically include a section on team dependencies and impact: which teams are affected, what they need to do, by when, and what the consequences are if they miss the deadline. This forces the migration authors to think through the organizational impact before starting, and it gives affected teams a concrete understanding of what is being asked of them.

### Migration Velocity: Why the Last 20% Takes 80% of the Time

The "last 20% problem" in migrations is so consistent across organizations and migration types that it deserves explicit treatment as an organizational pattern rather than just a technical observation. Understanding why the last 20% is hard helps you plan for it rather than being surprised by it.

The first reason is selection bias in difficulty. Teams and services that migrate early in a migration program tend to be the ones where migration is easiest: simpler codebases, more available engineers, more straightforward dependencies. The teams that remain at the end are disproportionately those with complex codebases, overwhelmed teams, difficult dependencies, or unusual requirements. The average difficulty of the remaining 20% is much higher than the average difficulty of the first 80%.

The second reason is priority drift. Early in a migration program, it is a high-priority initiative with leadership attention. Engineers clear their schedules to do migration work. As the migration reaches 80% completion, leadership attention moves to other priorities. The urgency dissipates. Teams that have not migrated start postponing migration work in favor of feature work that feels more immediately valuable to their roadmap. Without sustained priority enforcement, the last 20% drifts indefinitely.

The third reason is tail-end complexity. The last 20% often includes the integration points with external systems, legacy code that nobody fully understands, and dependencies that were not fully mapped at the migration's start. These require extra investigation, extra caution, and sometimes extra engineering to handle correctly.

The mitigation for the last 20% problem has three parts. First, plan for it explicitly in the timeline: if you estimate the migration will take six months, budget eight months, knowing that the last 20% will take disproportionately long. Second, maintain leadership attention through the entire migration, not just the first half. Weekly status reports that show "80% done, 6 teams remaining" keep the migration visible without requiring detailed leadership involvement. Third, provide elevated support for the remaining teams: dedicated engineering help, regular office hours, and direct involvement from the migration lead in unblocking specific issues. The teams at the end of the migration are the hardest cases — they need more support, not less.

### Inter-Team Contract Management

In a large migration, different teams are often responsible for different pieces of a shared contract. The provider team implements the new behavior. The consumer teams migrate to calling the new behavior. The contract between them — the API, the data format, the operational requirements — needs to be managed explicitly across the team boundary.

The common failure mode is contract drift: the provider team makes a change to the new behavior based on internal feedback, and consumer teams are not notified. The consumer teams are building their migration code based on the original contract. When they complete their migration work and test it against the real provider, the contract has changed and their code does not work. This causes delays and frustration on both sides.

The solution is explicit contract management with change notification. The contract is documented in a shared location (a schema registry, an API specification document, a shared interface definition file). Any change to the contract goes through a review process that includes notification to all consumer teams. Consumer teams acknowledge that they have reviewed the change and that their migration work still aligns with it. The provider team does not make changes to the contract without this acknowledgment loop. This process adds friction to the provider team, which may feel it slows them down. But the friction is much smaller than the downstream cost of contract drift, and it is the migration lead's job to enforce this process even when provider teams push back.

### The Migration Retrospective

When a major migration completes, a retrospective is not optional — it is one of the highest-return investments the migration team can make. A migration retrospective examines what worked well (to repeat it in future migrations), what did not work well (to avoid in future migrations), and what organizational or technical gaps were discovered that should be addressed before the next migration.

The most valuable retrospectives go beyond surface-level observations ("the parity verification tool was helpful") to root-cause analysis ("the parity verification tool was helpful because it caught a dual-write ordering bug that we would not have caught in testing — and the reason we would not have caught it in testing is that our integration test environment does not generate concurrent writes, which is a test environment gap we should fix"). This level of analysis converts migration experience into durable organizational learning.

The migration retrospective should specifically address: Were our rollback triggers set at the right thresholds? Were there false positives (rollbacks triggered by noise) or false negatives (problems that should have triggered rollback but did not)? Did we have enough time at each phase to build confidence before ramping? Did teams have enough information and support to complete their pieces? Were there any technical surprises that better preparation could have anticipated? Was the migration dashboard sufficient, or did we find ourselves needing metrics that were not available? The answers to these questions become the input for improving the migration framework for the next program.

### Brainstorming Q&A

**Q: How do you handle a migration where a key dependency — a library, a platform service, or an external vendor — is not migrating on your timeline?**

External dependencies that do not migrate on your timeline are one of the most frustrating and common blockers in migration programs. The response depends on where the dependency falls in the migration critical path and what kind of leverage you have over the dependency owner.

For internal dependencies (a library maintained by another team, a platform service maintained by a different organization within the same company), the first step is to make the dependency explicit and escalate it through the migration's program management. The dependency owner's management needs to understand that their team's delay is blocking a company-priority migration. In most organizations, making this escalation visible to VP-level or director-level leaders on both sides is enough to create urgency in the dependency team. If the dependency team is genuinely overwhelmed and cannot prioritize the migration work, there are two options: the migration lead's team temporarily contributes engineering resources to the dependency team to unblock it, or the migration's timeline is extended explicitly (not informally) to account for the dependency delay.

For external dependencies (a vendor-provided SDK that has not been updated for the new behavior), the options are more limited. You can escalate through your vendor relationship to request that the update be expedited. You can build a compatibility adapter internally that allows you to proceed with the migration even though the vendor has not released their update — the adapter translates between your new behavior and the vendor's existing interface until the vendor catches up. Or you can scope the migration to exclude the vendor dependency initially and complete the vendor integration as a follow-on. The worst option is to silently wait for the vendor without escalating or finding a workaround, because vendor timelines are opaque and unreliable, and waiting without a mitigation is how migrations stall indefinitely.

**Q: A team completes their migration work but the migration dashboard shows they have not actually migrated — old behavior is still being triggered by their service. How do you investigate and resolve this?**

This situation is more common than it should be and typically indicates one of three root causes. The first is a code rollback: the team completed the migration, deployed new code, but subsequently rolled back for an unrelated issue and has not re-applied the migration. The migration dashboard shows old behavior because it is reading from the current deployed code version, which is the old version. The resolution is for the team to re-apply their migration changes in a new deployment, this time separating the migration change from any other code that caused the rollback.

The second is a deployment gap: the team deployed the migration to some servers but not all. Perhaps the deployment pipeline has a canary stage that only deploys to 10% of servers, and the team marked the migration as complete after the canary without promoting to the full fleet. The migration dashboard may show reduced old behavior (10% of old traffic, since 90% of servers are now on the new code) but not zero. The resolution is to complete the full deployment.

The third is a hidden code path: the team migrated the code paths they knew about but missed a less obvious one — a batch job, a scheduled task, a background worker, or a third-party SDK that calls the old behavior internally. Finding hidden code paths requires going beyond grep-based code search to include runtime traffic analysis: look at the migration dashboard's breakdown of which request types are still using old behavior, trace those request types back to their source, and investigate what code is generating them. Once the hidden path is identified, it needs to be migrated explicitly. This discovery also means the pre-migration audit from the migration plan was incomplete — the retrospective should note this and recommend improvements to the audit process for future migrations.

---

## Reference: Chapter 97 Pattern Summary with Examples

The following is a condensed reference of every major pattern in this chapter, with a one-sentence description and the canonical real-world example that illustrates it best.

**Expand-Contract (Parallel Change):** The three-phase pattern of adding new behavior alongside old, migrating all traffic to new, then removing old. Canonical example: adding a UUID column alongside an integer ID column in a database table — add UUID (expand), backfill UUID for all rows and write UUID for all new rows (migrate), remove integer ID after all reads are using UUID (contract).

**Dual-Write:** Writing every change to both old and new systems simultaneously during a migration transition period to keep them synchronized. Canonical example: Airbnb's migration from their PostgreSQL user database to a sharded DynamoDB — every user update was written to both databases for months while the new database was validated.

**Shadow Mode:** Sending requests to both old and new systems but only trusting the old system's response, using the new system's response only for comparison. Canonical example: the verification phase during the Airbnb monolith-to-services migration, where both the monolith code path and the new service were called for every request and their responses compared without exposing the new service's results to users.

**Feature Flag Ramp:** Gradually increasing the percentage of traffic routed to new behavior, with rollback triggers that reverse the ramp if metrics degrade. Canonical example: Stripe's rollout of new API endpoint versions, where new behavior is enabled for specific API key prefixes or customer segments before being enabled broadly.

**Strangler Fig:** Building a new system incrementally around a legacy system, routing increasing portions of traffic to the new system until the legacy system handles nothing and can be decommissioned. Canonical example: Airbnb's multi-year Rails monolith decomposition into services, where each service was extracted one at a time behind a proxy layer.

**Blue-Green Database Deployment:** Running a new database instance as a replica of the current primary, then doing an atomic failover to the new instance during a short write-drain window. Canonical example: any major version upgrade of PostgreSQL or MySQL at a company that cannot afford extended downtime, where the replica is built and validated before the failover window.

**gh-ost:** GitHub's Online Schema Transmogrifier — a trigger-free online schema migration tool for MySQL that uses binary log parsing to keep a shadow table synchronized while performing the schema change without locking the production table. Canonical example: GitHub's own use of gh-ost to add and modify columns on their largest GitHub.com tables without disrupting developer traffic.

**Batch Backfill with Rate Limiting:** Processing large data migrations in small batches with controlled pauses to avoid overwhelming database replication and I/O capacity. Canonical example: Twitter's backfill of user data into Manhattan, where batch job throughput was governed by a controller that measured replication lag and automatically reduced write rate when lag exceeded a threshold.

**Rollback Drill:** A rehearsal of the rollback procedure before a migration starts, to verify that the rollback works, identify gaps in the procedure, and build team muscle memory. Canonical example: Netflix's chaos engineering practices extended to migration testing — they deliberately trigger rollback conditions in pre-production environments to verify that the rollback procedure executes correctly before touching production.

**Parity Verification:** Continuous comparison of data between old and new systems during a migration to detect divergence before it accumulates. Canonical example: Airbnb's storage migration framework, which included a background job that continuously sampled records from source and destination stores and compared them field by field, alerting when the mismatch rate exceeded a configured threshold.

**Sunset Deadline Enforcement:** Setting and enforcing hard deadlines by which API consumers or service callers must migrate to new behavior, with the old behavior actually being removed on the deadline date. Canonical example: Google's annual forced upgrades of deprecated Android APIs, where apps using deprecated APIs are removed from the Play Store after the deprecation deadline — a credible enforcement mechanism that drives migration completion.

---

## Part 17: Distributed Systems Considerations in Migrations

### The CAP Theorem and Migration Windows

Every migration that moves data between systems or changes how data is stored must grapple with the CAP theorem's constraints. CAP states that a distributed system can provide at most two of three guarantees simultaneously: Consistency (every read receives the most recent write), Availability (every request receives a response), and Partition tolerance (the system continues to operate when network partitions occur). During a migration, you are typically operating two systems simultaneously, which creates a multi-system distributed environment where CAP applies in new and important ways.

The dual-write pattern, for example, involves two separate data stores that must be kept synchronized. During normal operation (no network partition), both stores receive writes and can be kept consistent. But if a network partition occurs between the application and one of the stores, the application must choose: do we fail the write entirely (sacrificing availability to maintain consistency between stores), or do we write to only the reachable store and accept that the two stores are temporarily inconsistent (sacrificing consistency to maintain availability)? This is the same CAP tradeoff that any distributed system faces, but it becomes particularly consequential during a migration because inconsistency between old and new stores is exactly what your parity verification is designed to detect and alarm on.

The practical implication is that your dual-write design must explicitly decide which side of the CAP tradeoff to take during partition events. For financial data or any data where inconsistency is unacceptable, you take the consistency side: if either write fails, the entire write fails, and the application returns an error to the user. For data where availability is more important than perfect consistency between stores (user preferences, session data, recommendations), you take the availability side: write to the reachable store, queue the failed write for async retry, and accept brief divergence. Your parity verification job serves as the eventual-consistency repair mechanism in this latter case, catching and reconciling any divergence that the async retry queue fails to resolve.

Understanding this tradeoff explicitly and being able to articulate it in an interview is the difference between a candidate who knows the dual-write pattern and a candidate who deeply understands it. The pattern is not just a technique — it is a point in a design space defined by fundamental distributed systems constraints, and the staff engineer must be able to navigate that design space consciously.

### Clock Skew and Migration Timing

In distributed systems, different servers have different local clocks, and those clocks can drift apart by milliseconds or even seconds. This clock skew creates subtle problems in migrations that depend on temporal ordering. If your migration logic uses timestamps to determine which records have been migrated and which have not, clock skew can cause records to be incorrectly classified.

A concrete example: your backfill job marks each row as migrated by setting a `migrated_at` timestamp. Another server, writing a new record, sets its `created_at` timestamp using its local clock. If the backfill server's clock is 2 seconds ahead of the writing server's clock, the backfill might mark a record as migrated at T=1000, while the writing server creates a new record at T=999 (its clock's view of the current time). The backfill job, comparing `migrated_at` to `created_at`, incorrectly concludes that the new record was created before the backfill started and does not include it in the backfill, even though the record actually needs to be migrated.

The solution is to use Lamport timestamps or logical clocks rather than wall-clock timestamps for migration tracking. A Lamport timestamp is a monotonically increasing counter that is incremented on every event and synchronized through message passing — it provides a total ordering of events without depending on synchronized physical clocks. Alternatively, using database transaction IDs (which are monotonically increasing and server-local) rather than timestamps for tracking migration progress avoids clock skew entirely. The backfill job tracks its progress by the maximum transaction ID it has processed, not by the timestamp of the last record it migrated. New records have transaction IDs higher than the backfill's checkpoint, so they are correctly identified as needing migration regardless of what the wall clock said when they were written.

### Idempotency: The Migration Engineer's Best Friend

Idempotency is the property of an operation where executing it multiple times produces the same result as executing it once. In migration engineering, idempotency is not optional — it is the fundamental requirement for every migration operation, because migrations will be interrupted, retried, and replayed. A migration operation that is not idempotent will produce incorrect results when retried.

The canonical idempotency pattern for migrations is the conditional update: instead of blindly updating a record, the update includes a precondition that checks the current state of the record. A backfill update should be `UPDATE table SET new_column = value WHERE id = ? AND new_column IS NULL`, not `UPDATE table SET new_column = value WHERE id = ?`. The `AND new_column IS NULL` condition makes the update idempotent: running it when `new_column` is already populated has no effect, whereas the version without the condition would overwrite the column value on every retry.

For operations that create new records (rather than updating existing ones), idempotency requires an upsert pattern: `INSERT INTO table (...) VALUES (...) ON CONFLICT (id) DO UPDATE SET ... = EXCLUDED....` This ensures that retrying the insert when the record already exists updates it rather than creating a duplicate. The exact syntax for upserts varies between database engines (PostgreSQL uses `ON CONFLICT DO UPDATE`, MySQL uses `INSERT ... ON DUPLICATE KEY UPDATE`, CockroachDB follows the PostgreSQL syntax), and knowing the correct syntax for your specific database is part of migration competence.

For operations that delete records, idempotency means the deletion is safe to retry: deleting a record that has already been deleted should not produce an error. Most SQL databases return a row count of zero for `DELETE WHERE id = ?` when the row does not exist, rather than an error, which makes deletions naturally idempotent as long as your application code does not treat a zero-row-count delete as an error.

The idempotency requirement extends to the migration control plane, not just the data operations. The migration job itself should be resumable from any point: if it crashes at step N, restarting it should re-execute step N safely and then proceed from there. This requires that the migration job tracks its progress (current batch ID, current table, current phase) in a durable location and reads that checkpoint on startup to determine where to resume. The checkpointing granularity determines the worst-case restart overhead: if you checkpoint every 1,000 rows, a crash will cause at most 1,000 rows to be re-processed on restart. If you checkpoint every 1 million rows, a crash could cause up to 1 million rows to be re-processed — which, combined with the idempotency of the operation, is safe but wasteful.

### Consistency Guarantees Across Migration Boundaries

When a migration is in progress and both old and new systems are simultaneously serving reads, the user experience depends critically on which consistency guarantees each system provides and how those guarantees compose across the migration boundary.

Consider a user who updates their email address. The write goes to both the old and new databases (dual-write). The user then immediately reads their profile. Depending on which system serves the read, they might see the old email address or the new one. If the read goes to the old database, they see the new email address (because the dual-write succeeded synchronously to the old database). If the read goes to the new database, they might see the old email address if the new database's write has not yet been durably committed (perhaps it went through an async queue).

This inconsistency — seeing stale data immediately after writing — is a variant of the "read-your-writes" consistency guarantee, and losing it during a migration period can cause confusing user experiences. The solution is to route reads for recently-written data back to the old system (which has the freshest writes) during the migration period. This is the purpose of the "read old, write both" phase of the dual-write pattern: the old system is the source of truth for reads because all writes go there synchronously. The new system is not trusted for reads until it has demonstrated that it can satisfy read-your-writes consistency, which requires verifying that the write path to the new system is synchronous and that reads from the new system reflect the latest written state.

In systems that use eventual consistency as a design choice (Cassandra, DynamoDB with eventual consistency settings), the migration adds a second layer of eventual consistency on top of the first. The application may already tolerate reading stale data from the same system; during migration, it also tolerates the possibility that the new system is further behind than the old system. This compounding of consistency guarantees needs to be analyzed carefully: what is the maximum staleness that users can observe, and is that acceptable for the data in question? For most user-facing data, staleness of more than a few seconds is not acceptable, and the migration design needs to ensure that the new system's update latency does not significantly exceed the old system's.

### The Thundering Herd Problem in Migration Backfills

When a backfill migration starts and begins processing rows in order (by primary key, by creation date, or by some other column), it often processes the most recently-created records last. These recently-created records are typically the hottest records in the cache — they are the ones most recently accessed by users, and therefore most likely to be cached in your application-layer cache or database buffer pool. When the backfill updates these hot records, it invalidates their cache entries, causing a spike in cache misses and a corresponding spike in database reads for that data.

This is the thundering herd problem in a migration context: the backfill itself generates a wave of cache invalidations that drives an unexpected spike in database load. On a table with a heavily trafficked "latest" partition (social media feeds, recent activity logs, notification records), this can cause the backfill to trigger a cascade of cache misses that overwhelms the database or significantly increases latency for users.

The mitigation strategies are: first, process rows in reverse order (oldest first, most recent last) so that the hot records are processed at the end, after the backfill has been running long enough that the system is stable and the team is confident in the backfill process. Second, throttle the backfill rate more aggressively when it is processing hot records — the monitoring should show a correlation between backfill progress and cache miss rate, and when cache miss rate spikes, the throttle should activate. Third, pre-warm the cache for records that are about to be backfilled by reading them into cache before the backfill updates them, so that the post-update read is served from cache rather than triggering a cache miss. This pre-warming approach is complex but can completely prevent the thundering herd for well-bounded hot record sets.

### Brainstorming Q&A

**Q: How does the choice of database isolation level affect the safety of a migration that uses concurrent batch backfill and production traffic?**

Database isolation levels — Read Uncommitted, Read Committed, Repeatable Read, and Serializable — determine what a transaction can see from other concurrent transactions, and the choice of isolation level for the backfill transactions has meaningful safety implications for a migration. Most production databases use Read Committed as the default isolation level for OLTP transactions, meaning that a transaction sees the committed state of all data at the time each statement executes, not at the time the transaction began. For a backfill transaction that processes a batch of 1,000 rows, this means that rows updated by production traffic after the backfill transaction began but before it reads those rows will be read in their updated state — not the state they were in when the transaction started.

This is actually the desired behavior for a migration backfill: you want the backfill to see the most recent version of each row, so that the backfilled value is computed from current data rather than stale data. If the backfill used Serializable isolation, the backfill transaction would see a snapshot of the data as it was when the transaction began, potentially computing backfilled values from data that production traffic has since updated. The production updates would then not be reflected in the backfill result, and you would have a temporary window where the new column contains stale values.

The more subtle concern is how the isolation level of production traffic transactions interacts with the backfill. If a production transaction that updates a row's existing columns overlaps with the backfill transaction updating that row's new column, do they conflict? Under Read Committed, neither transaction blocks the other (because they touch different columns). Under Serializable, both transactions might be serializable conflict candidates, potentially causing one to abort and retry. For tables with very high update rates, using Serializable isolation for the backfill would cause significant retry overhead. Read Committed is the correct isolation level for backfill transactions, with the caveat that the backfill operation must be idempotent (safe to retry) to handle the case where the backfill itself is interrupted and retried.

**Q: What testing strategy do you use to validate a migration before executing it in production, when the production data characteristics are fundamentally different from your test data?**

This is one of the fundamental challenges in migration testing: the behavior of a migration often depends on data characteristics that are hard to replicate in a test environment. Production databases have real distributions of values, real patterns of null versus non-null, real outliers, and real volumes — none of which are present in synthetic test data. A migration that passes all tests in staging may fail in production because of a data pattern that was not in the test data.

The best mitigation is to test the migration against a copy of production data, not synthetic data. Most organizations have a mechanism for creating anonymized or masked copies of production data for use in test environments. The masking replaces PII (names, emails, phone numbers, SSNs) with synthetic values while preserving the statistical characteristics of the data (the distribution of values, the proportion of nulls, the length of strings, the range of numbers). Running the migration against a masked production copy catches the vast majority of production-specific data issues because the underlying data distribution is real.

For migrations that are too large to copy entirely, a representative sample of the production data can be used. The sample should be stratified to ensure it includes outliers and edge cases: the longest values, the shortest values, records with all optional fields populated, records with all optional fields null, records from the earliest and latest time periods. Random sampling alone may miss rare but important edge cases, so explicit inclusion of boundary conditions in the test data is necessary. The migration should then also include a "pilot run" on a small fraction of real production data — perhaps 0.1% of the table — before the full backfill begins. The pilot run verifies the migration logic against real data at small scale, with the full backfill proceeding only after the pilot run completes without errors and parity verification confirms correct results. This staged approach catches the production-specific edge cases that testing could not.

---

## Part 18: Migration Decision Framework

### How to Choose the Right Migration Pattern

When you are facing a new migration challenge, the number of patterns available can be overwhelming. The decision framework below provides a systematic way to narrow down which patterns apply to your specific situation.

**Step 1: Identify the migration type.** Is this primarily a data migration (changing what is stored), a code migration (changing how the system behaves), or an infrastructure migration (changing the platform)? Most real migrations have elements of all three, but identifying the dominant type helps prioritize the right patterns.

**Step 2: Assess the downtime tolerance.** Can the system tolerate any downtime? If yes, how much? A system that can tolerate 4 hours of downtime per month has fundamentally different options than a system with a 99.99% SLA that tolerates no more than 4 minutes of downtime per month. The downtime tolerance determines whether zero-downtime patterns are required or whether maintenance window approaches are viable.

**Step 3: Assess the rollback complexity.** If the migration fails partway through, what is the rollback cost? For changes that are naturally reversible (adding a column, enabling a feature flag), rollback is cheap. For changes that are hard to reverse (dropping a column, committing to a new database engine after full cutover), rollback is expensive. Higher rollback cost justifies more extensive validation before each step and a longer shadow period.

**Step 4: Assess the blast radius.** How many users, services, or teams are affected if the migration goes wrong? A migration on an internal analytics table has a smaller blast radius than a migration on the primary user authentication table. Higher blast radius justifies slower, more conservative migration execution with smaller ramp increments and longer observation periods at each step.

**Step 5: Assess the data volume and traffic rate.** How much data needs to be moved or transformed, and how many concurrent reads and writes is the affected system handling? Higher data volume means longer backfill times and more potential for replication lag. Higher traffic rate means more potential for race conditions in dual-write and more sensitivity to any performance overhead from migration operations.

Based on these five assessments, the appropriate patterns emerge naturally:

For zero-downtime requirement + data volume > 1M rows + reversible change: use expand-contract with batch backfill (online DDL or gh-ost for schema changes), feature flag ramp for traffic cutover.

For zero-downtime requirement + storage system migration: use dual-write with parity verification, shadow mode read verification, feature flag ramp.

For zero-downtime requirement + service decomposition: use strangler fig with proxy layer, shadow comparison, gradual traffic shift by capability.

For limited downtime acceptable + complex schema change: use blue-green database deployment with a brief write-drain cutover window.

For API migration + external clients: use versioned APIs with deprecation lifecycle and sunset deadline enforcement.

For infrastructure migration + new platform: use lift-and-shift first (minimize risk by changing only location, not behavior), then optimize incrementally.

### The Migration Readiness Checklist

Before executing any migration step that changes production state, use the following checklist to verify readiness.

**Technical readiness:**
- [ ] The rollback procedure for this step has been documented in the runbook
- [ ] The rollback procedure has been tested (drill in staging or dry-run in production with an abort)
- [ ] Rollback triggers have been defined with specific metrics and thresholds
- [ ] The migration dashboard is live and showing current data (not cached/stale)
- [ ] All health metric alerts are configured and routed to the migration team's alert channel
- [ ] Parity verification is running and showing acceptable mismatch rate (< defined threshold)
- [ ] The migration step has been tested in staging against masked production data
- [ ] All affected services have been notified of the migration window

**Organizational readiness:**
- [ ] The migration team is fully staffed and available for the duration of the step (no key person on vacation or unavailable)
- [ ] An escalation path has been communicated: who to call if X goes wrong, who to call if Y goes wrong
- [ ] The incident response team (on-call) is aware that a migration is in progress and may generate unusual alerts
- [ ] Customer support has been briefed on potential user-visible symptoms and response scripts
- [ ] Leadership has confirmed the migration window is acceptable (no major product launches or business events that would make a rollback more costly than usual)

**Data readiness:**
- [ ] Current backups have been taken of all affected data stores within the past 24 hours
- [ ] The backup restore procedure has been verified (not just assumed to work)
- [ ] Replication lag on all replicas is within acceptable bounds (< defined threshold)
- [ ] Disk space on all affected systems is sufficient for the migration (shadow table, temporary storage, WAL growth)

This checklist is not bureaucracy for its own sake — every item represents a failure mode that has caused a real production incident at some organization. A "no" on any item should pause the migration until the item is addressed.

### When to Stop a Migration vs. When to Push Through

One of the hardest judgment calls in migration execution is deciding whether to stop and investigate when a metric looks concerning, or to push through because the metric is within the noise range. This judgment call is particularly hard because the people executing the migration are typically under time pressure (they wanted to complete this phase today), and they are psychologically primed to expect the migration to work (they planned it carefully, after all).

The framework for this decision is: **if in doubt, stop**. The asymmetry of consequences justifies this conservatism. If you stop when you did not need to (the metric was just noise), you lose a few hours of migration time. If you push through when you should have stopped, you may cause a production incident that takes days to recover from. The downside of stopping is always smaller than the downside of proceeding into a real problem.

The practical triggers that always justify an immediate stop are: any data integrity issue detected by parity verification (even a single unexplained mismatch), any user-facing error rate that exceeds the rollback threshold for more than two minutes, any complete loss of visibility into a key migration metric (the dashboard goes dark, the monitoring loses its data source), and any cascading effect on services that were not expected to be affected by the migration.

The triggers that justify a pause-and-evaluate rather than an immediate stop are: a metric that is trending toward the rollback threshold but has not crossed it yet, an alert from a metric that has a high false-positive rate in similar situations, a discrepancy in parity verification that appears in a known-noisy category of records. In these cases, the migration is paused (no further traffic is shifted, no further backfill is run) while the team investigates the specific metric or parity issue. If investigation reveals a real problem, the migration stops and potentially rolls back. If investigation confirms the concern was a false positive, the migration resumes.

The worst outcome is neither stopping nor pausing — continuing to ramp despite concerning metrics because "it's probably fine" and "we're almost done." This is the mindset that produces the incidents. The discipline of taking concerning metrics seriously, even when you really want to be done with the migration, is the most important operational behavior in migration execution.

### Brainstorming Q&A

**Q: How do you design a migration framework that can be reused across different types of migrations — not just one specific migration?**

A reusable migration framework is an investment that pays off most when an organization is running multiple migrations simultaneously or expects many migrations over time. The key design challenge is finding the right level of abstraction: too specific and the framework only applies to one migration type; too abstract and it provides no real value over building from scratch each time.

The core abstractions in a successful migration framework are: a migration state machine (defining the valid states: PENDING, EXPANDING, MIGRATING, CONTRACTING, COMPLETE, ROLLED_BACK, and the valid transitions between them), a checkpoint store (durable storage for migration progress that survives process restarts), a rate limiter (configurable throttling for the migration's impact on production systems), a parity verifier (a pluggable interface for checking that two systems have equivalent data), a migration dashboard (a standard set of metrics and visualizations that are automatically populated for any migration using the framework), and a rollback orchestrator (the ability to invoke a migration's rollback procedure from a single command or button click).

Each specific migration plugs into this framework by implementing the framework's interfaces: a function that executes one batch of the migration, a function that executes one batch of the rollback, a function that checks parity for a batch of records, and configuration that specifies rate limits, parity verification sampling rates, and rollback triggers. The framework handles checkpointing, rate limiting, dashboard population, alert routing, and rollback orchestration automatically. This means that a new migration only needs to implement the domain-specific logic — what to do to each record — and gets operational infrastructure for free.

Building this framework is a staff engineer project: it requires understanding the common patterns across many different migration types, identifying which parts of those patterns are truly common (and should be in the framework) and which are migration-specific (and should be implemented by each migration). It also requires getting buy-in from the engineering organization to use the framework rather than building ad-hoc migration tooling, which is the organizational challenge that the staff engineer is best positioned to address.

---

## Glossary of Migration Terms

Understanding migration terminology is useful both for interviews and for working with other engineers. The following glossary defines the key terms used throughout this chapter.

**Backfill:** The process of populating a new column, table, or field with values derived from existing data. Backfills are typically run as batch jobs after the new storage location is created, to bring historical data up to date.

**Blue-Green Deployment:** A deployment pattern where two identical environments (blue and green) are maintained. One is active (serving production traffic); the other is idle. New deployments go to the idle environment, which is validated before traffic is switched.

**Canary Deployment:** A deployment pattern where a new version is first deployed to a small subset of servers or users (the "canaries") to validate it before deploying broadly.

**CAP Theorem:** The statement that a distributed system can simultaneously guarantee at most two of: Consistency, Availability, and Partition tolerance.

**Contract Phase:** The third phase of expand-contract, in which the old behavior (the behavior added in the expand phase that is now superseded by the new behavior) is removed.

**Dual-Write:** Writing data to both old and new systems simultaneously during a migration transition period.

**Expand Phase:** The first phase of expand-contract, in which new behavior is added alongside old behavior so that both work simultaneously.

**Feature Flag:** A configuration setting that controls which code path or behavior is active, allowing traffic to be gradually shifted or rapidly rolled back.

**gh-ost:** GitHub's Online Schema Transmogrifier, a trigger-free online schema migration tool for MySQL that uses binary log parsing.

**Idempotency:** The property of an operation where executing it multiple times produces the same result as executing it once.

**Migrate Phase:** The second phase of expand-contract, in which traffic is moved from the old behavior to the new behavior, while both behaviors remain active.

**Online DDL:** Schema changes that can be executed without locking the table, allowing normal read and write traffic to continue during the schema change.

**Parity Verification:** Continuous comparison of data between old and new systems to detect divergence.

**pt-osc (pt-online-schema-change):** A MySQL online schema migration tool from the Percona Toolkit that uses database triggers to keep a shadow table synchronized.

**Replication Lag:** The delay between when a write occurs on a primary database and when it is reflected on a replica.

**Rollback:** The process of reverting a migration step to restore the system to its pre-step state.

**Rollback Drill:** A rehearsal of the rollback procedure before a migration starts.

**Rollback Trigger:** A predefined, measurable condition that automatically initiates rollback.

**Shadow Mode:** Running requests against both old and new systems but returning only the old system's response to users, using the new system's response only for comparison.

**Strangler Fig Pattern:** A migration pattern where a new system is built incrementally around a legacy system, with increasing portions of traffic routed to the new system until the legacy system can be decommissioned.

**Sunset Date:** The date on which a deprecated API behavior, feature, or interface will be removed.

**Zero-Downtime Migration:** A migration executed without requiring the system to be taken offline, allowing normal user traffic to continue throughout.

---

## Further Reading and Reference Material

The following resources provide additional depth on the topics covered in this chapter. Each is described with the specific aspect of migration engineering it covers best.

**"Building Evolutionary Architectures" by Ford, Parsons, and Kua** covers the architectural patterns that make systems amenable to evolutionary change, including the fitness functions and structural constraints that prevent migrations from being needed as urgently in the first place. The concept of "appropriate coupling" is particularly relevant to understanding when the strangler fig pattern is needed and when simpler refactoring suffices.

**"Database Reliability Engineering" by Campbell and Majors** is the definitive reference for the operational aspects of database migrations at scale. The chapters on schema change management, replication, and failover procedures are directly applicable to the patterns in Part 3, Part 8, and Part 9 of this chapter.

**"Designing Data-Intensive Applications" by Kleppmann** provides the distributed systems foundations for understanding why dual-write has ordering bugs (Chapter 5, Replication), why replication lag is unavoidable (Chapter 5), and what consistency guarantees your migration can and cannot provide (Chapter 7, Transactions; Chapter 9, Consistency and Consensus).

**The GitHub Engineering Blog** documents several of the specific case studies referenced in this chapter in primary source form: the MySQL to Vitess migration, the gh-ost announcement and rationale, and the 2012 database incident postmortem. Reading these as primary sources rather than through the summary in this chapter provides significant additional depth.

**The Stripe Engineering Blog** covers their API versioning approach in detail, including the internal systems they built to manage backward compatibility across fourteen years of API evolution. The post on API deprecation and the post on their versioning layer design are particularly valuable for the topics in Part 7.

**"The Pragmatic Programmer" by Hunt and Thomas** covers the concept of software entropy and technical debt in a way that directly explains why skipping the contract phase of expand-contract creates compounding problems. The "don't live with broken windows" principle applies directly to the permanent temporary shim anti-pattern described in Part 14.

**"Accelerate" by Forsgren, Humble, and Kim** provides the research basis for why deployment frequency and mean time to recovery (both of which are directly affected by migration discipline) are leading indicators of organizational engineering performance. This provides the business-case grounding for investing in the migration practices described in this chapter.

---

## Part 19: Interview Practice — Worked Examples

This section provides three complete worked interview responses at the L6 level, demonstrating the full pattern of reasoning from problem statement to detailed solution. These are written in the style of a candidate talking through their thinking in an interview, not as final engineering documents.

### Worked Example 1: "How would you migrate our payment processing service from a single PostgreSQL node to a multi-region active-active setup?"

"Before I dive into the migration plan, I want to make sure I understand the constraints. A couple of questions first: what is our current downtime tolerance for payments — are we on a 99.9% SLA, 99.99%, higher? And what is our recovery time objective if one region fails? Those answers will determine how conservative we need to be at the cutover moment.

Assuming we need zero planned downtime and the whole point of active-active is sub-100ms failover — which means we cannot afford the rollback complexity of a traditional primary-replica cutover — let me walk through how I would approach this.

The migration has three distinct layers that need to be addressed in order. The first is the data layer: getting to a state where both regions have the same data, in real time, with conflict resolution defined. The second is the application layer: ensuring our payment service can route writes intelligently between regions and handle the consistency tradeoffs of active-active. The third is the traffic layer: gradually shifting real payment traffic to the multi-region setup.

For the data layer, the key question is what database technology we are moving to. True active-active across regions requires either a database that natively supports multi-master replication with conflict resolution — like CockroachDB, Spanner, or Vitess with multi-master — or building conflict resolution at the application layer on top of a simpler replication setup. For payments specifically, I would lean toward a database that gives us serializable transactions across regions, like CockroachDB or Spanner, rather than trying to build conflict resolution ourselves. Payment conflicts — two regions both accepting a charge on the same account that would together exceed the account limit — are not resolvable by a last-write-wins strategy. We need strong consistency.

The migration starts by standing up the new multi-region database in parallel with the existing single-node PostgreSQL. We set up the existing PostgreSQL as the source of truth and stream all changes to the new database using dual-write at the application layer plus CDC (change data capture) for historical data. This dual-write period is the most complex phase, and it can last weeks — we need parity verification running continuously throughout, sampling payment records and comparing balances between old and new systems. The parity verification for payment data needs to be exact, not approximate: even a one-cent discrepancy between systems is unacceptable. Any parity failure pauses the migration automatically.

Once parity has been clean for a sustained period — I would say at least 72 hours given the criticality of payments — we start shadow reads. Every payment read goes to both the old PostgreSQL and the new multi-region database; we return the PostgreSQL result to the user but log any discrepancy from the new database. We run shadow reads for another week, watching for any cases where the two systems return different payment histories or balances.

The cutover itself for a zero-downtime active-active migration is different from a traditional primary-replica failover. Instead of a hard cutover, we gradually shift write traffic region by region. We designate one region as the initial active writer (equivalent to the old primary) and the other region as active reader only. We shift read traffic to the second region first, then slowly allow writes to both regions, starting with low-stakes writes (like preference updates, not payment authorizations). Payment authorizations stay on the original region until we have significant confidence in the multi-master setup. The final phase is enabling true active-active for all payment writes, which is the moment we are fully migrated.

The rollback plan for this migration is unusual: because active-active is designed to tolerate node failures, we can roll back by simply directing all traffic back to the original region, which never stopped being a valid writer. The old PostgreSQL instance stays in place as a read replica throughout the entire migration period, providing a clean rollback target for at least 30 days after cutover. After 30 days, if all metrics are clean, we decommission the old single-node PostgreSQL.

The things I would specifically monitor throughout this migration: payment authorization success rate, payment authorization latency at p50 and p99, parity mismatch rate between systems, cross-region replication lag, and conflict rate in the new database. Any of those going meaningfully wrong triggers a stop-and-investigate, with automatic rollback if they cross predefined thresholds."

### Worked Example 2: "A junior engineer has just added a column to the users table in production without a migration plan and the column is blocking production writes. How do you fix it?"

"This is a recovery situation, not a migration planning situation, so the immediate priority is stopping the bleeding. Let me first understand exactly what happened.

The most common scenario is that someone ran an ALTER TABLE that acquired a metadata lock, and now that lock is blocking all other write transactions on the users table. The first thing I want to know is: is the ALTER TABLE still running, or has it completed and something else is now locked? I would immediately check `SHOW PROCESSLIST` in MySQL or `pg_stat_activity` in PostgreSQL to see what is currently holding locks on the users table. I would also check if there are any long-running transactions that were started before the ALTER TABLE that the ALTER TABLE is waiting to acquire a lock after — in MySQL, a long-running read transaction can prevent an ALTER TABLE from completing because the ALTER needs an exclusive lock that cannot be granted until all current transactions complete.

If the ALTER TABLE is still running and can be safely killed — meaning we can tolerate the column not being added right now — the fastest fix is to kill the ALTER TABLE process. In MySQL: `KILL process_id`. This should release the lock immediately and allow production writes to resume. The column will not be added, but production is unblocked. We can then plan the migration properly.

If the ALTER TABLE has already completed and something else is now causing blocks, we need to understand what changed. Does the new column have any constraints or defaults that are causing issues on insert? Is there application code that was deployed alongside this column change that is now failing because the column exists but the values are wrong?

Once production is unblocked, the post-mortem conversation with the junior engineer focuses on why the ALTER TABLE caused a lock — this should never have happened in production without using gh-ost or PostgreSQL's online DDL — and the process failures that allowed this to happen: no migration plan, no review, no staging validation, and direct DDL execution in production. The process fix is usually some combination of requiring schema change reviews above a certain table size, restricting who has DDL permissions on production tables, and adding migration tooling to the deployment pipeline.

For adding the column safely going forward, if the users table has more than a few million rows, we use gh-ost (for MySQL) to add the column as nullable first, then backfill, then add constraints. The five-step sequence I described earlier applies here. The column should never have been added with anything other than a nullable default initially."

### Worked Example 3: "How would you design an API to support backward compatibility for the next 10 years?"

"Designing an API for decade-long backward compatibility is primarily a discipline problem, not a technical problem. The technical mechanisms are well-understood. The hard part is building the organizational commitment to maintain the discipline through multiple generations of engineers, changing business requirements, and evolving architectural patterns.

That said, let me start with the technical design, because the right technical choices make the discipline much easier to maintain.

The first principle is: design the API to be additive, not replacement-based. Every field, every endpoint, every parameter in the API should be versioned not by removing the old one but by adding the new one alongside it. The old one never goes away until every client has explicitly migrated away from it and confirmed that they no longer need it. This is the expand phase of expand-contract, applied at API design time.

The second principle is: use version scoping rather than version breaking. Stripe's approach is instructive here: rather than having /v1 and /v2 namespaces where v2 is a wholesale replacement of v1, they use a single API surface where each client declares the behavior version it expects in a header. The server applies version-specific transformations to produce the response that the client's declared version expects. Adding a new API version in this model means adding a new set of transformation rules, not a new set of endpoints. Clients that do not update continue to receive the behavior they have always received.

The third principle is: design for schema evolution from the start. Every response schema should use structures that allow fields to be added without breaking existing parsers. In practice this means using JSON or protocol buffers rather than formats with rigid positional semantics, using object types (which can have new fields added) rather than array types (which cannot), and designing field names that are specific enough that adding a related field does not create ambiguity. `created_at` can be joined by `updated_at` without ambiguity; a field named `date` cannot as easily be extended.

On the operational side, decade-long backward compatibility requires building the tooling to enforce it. This means: automated tests that deploy the API and run all client integration tests from every major version back some number of years, CI checks that flag when a PR removes or changes the semantics of an existing API field, a semantic versioning policy that clearly defines what constitutes a breaking change and requires explicit sign-off for such changes, and client dashboards that show which API version each client is using so you know when a version is truly unused.

The hardest part of decade-long compatibility is organizational succession. The engineer who made the original compatibility commitment will not be there in 10 years to enforce it. The commitment needs to be encoded in process, tooling, and culture rather than individual accountability. Writing down the principles explicitly (as Stripe does in their public documentation), making the automated enforcement robust enough that violations are caught without human vigilance, and onboarding every new API engineer to the compatibility philosophy are what sustain the commitment over a decade. The technical design is the easy part."

---

## Homework Answer Guide: What Strong Answers Look Like

This section provides guidance on what distinguishes a strong homework answer from a weak one for each of the eight homework assignments. Use this to self-evaluate before reviewing your answers with a peer.

**Homework 1 (Migration plan for a real table):** A strong answer includes the exact SQL for each of the five steps, not pseudocode. It specifies the batch size and pause duration for the backfill based on an estimate of the table's size and the write rate it handles. It includes the monitoring queries that run during the migration to check replication lag and backfill progress. A weak answer describes the steps at a high level without specific SQL and does not address the operational details of the backfill.

**Homework 2 (Analyze a real deprecation policy):** A strong answer cites specific clauses or policies from the API provider's documentation and compares them to the specific framework in Part 7 of this chapter. It identifies both strengths (places where the real policy is more rigorous or thoughtful than the framework) and weaknesses (places where the real policy falls short). A weak answer summarizes the deprecation policy without making specific comparisons to the chapter's framework.

**Homework 3 (Design a feature flag system):** A strong answer includes the data model (what tables or data structures store flag definitions and user bucket assignments), the evaluation logic (how a flag's state is determined for a given user ID, including consistent hashing), the change propagation mechanism (how changes reach all servers within seconds), and the automatic rollback mechanism (how the system detects error rate thresholds and reverses flag state). A weak answer describes the high-level design without addressing the key challenges: consistent hashing, fast propagation, and automated rollback.

**Homework 4 (Case study analysis):** A strong answer is structured around the three dimensions specified: patterns used, patterns missing, and the single most important decision. It gives specific examples from the case study for each point rather than generic observations. A weak answer summarizes the case study without analyzing it through the lens of the chapter's frameworks.

**Homework 5 (Migration proposal):** A strong answer writes a complete, professional document that a real engineering organization could use as the basis for a migration review. All seven specified sections are present and substantive. The timeline is specific (specific weeks or dates, not "phase 1" and "phase 2"). The organizational coordination section identifies the specific teams and what each team needs to do. A weak answer covers the sections at a high level without specific operational details.

**Homework 6 (Incident postmortem analysis):** A strong answer identifies specific anti-patterns from Part 14 by name and provides evidence from the incident postmortem that each anti-pattern was present. It identifies the specific early warning signs that were visible in the incident timeline and explains what monitoring would have been needed to detect them. A weak answer describes the incident without connecting it to the chapter's frameworks.

**Homework 7 (Parity verification proof-of-concept):** A strong answer includes working code that demonstrably detects the intentionally introduced bug within a few minutes. It describes what the introduced bug is and shows the output of the parity verification script when the bug is active. A weak answer describes how the code would work without demonstrating that it actually works.

**Homework 8 (API deprecation analysis):** A strong answer evaluates a specific real deprecation notice from a named API provider against specific criteria from Part 7. It makes concrete judgments about what the provider did well and poorly, with specific evidence. A weak answer describes the deprecation notice without specific evaluation against the chapter's criteria.

---

## Part 20: Migration Anti-Pattern Taxonomy — Expanded

The anti-patterns in Part 14 cover the most common failure modes. This section extends the taxonomy to cover five additional anti-patterns that appear less frequently but are equally damaging when they occur.

### Anti-Pattern 7: Over-Migration (Migrating What Does Not Need to Move)

Over-migration is the mistake of including work in a migration scope that does not actually need to be migrated. This inflates the migration's complexity, cost, and risk without any corresponding benefit. The motivation is usually good — "as long as we are touching this area, let's fix these other things too" — but the result is a migration that is harder to execute, harder to validate, and harder to roll back.

The problem is compounded by the interaction between migrated and non-migrated components. When a migration includes unnecessary changes, the parity verification becomes harder because you need to account for intentional differences between old and new systems (introduced by the unnecessary changes) in addition to the unintentional differences you are trying to detect. Each intentional difference is a noise source in the parity verification signal.

The discipline of minimal migration scope — changing only what is strictly necessary to achieve the migration's stated objective — is harder to maintain than it sounds because of organizational dynamics. Teams often want to use migration windows as opportunities for broader refactoring. The migration lead's job is to protect the scope: every proposed addition to the migration scope must be justified by necessity, not by convenience.

Real incident example: A team migrating their user authentication database from MySQL to PostgreSQL decided to also rename twelve columns as part of the migration "since we would need to update all the code anyway." The dual-write logic for the renamed columns was more complex than for the unchanged columns, and a bug in the column-name mapping caused a subset of authentication records to be incorrectly migrated. Detecting this bug through parity verification was more difficult because the verification code had to know which column names mapped to which others. The migration took two weeks longer than projected and required a temporary rollback. Had the column renaming been deferred to a separate migration after the database engine change, the database migration itself would have been simpler and faster.

### Anti-Pattern 8: Migrating Without a Data Dictionary

A data dictionary is a document (or structured metadata store) that describes what each field in a database table means, how it is used, what valid values it can contain, and which application code paths write to it and read from it. Migrations done without a data dictionary — without this knowledge of what the data means and who uses it — are migrations done blind.

The symptom of missing data dictionary knowledge during a migration is discovering unexpected semantics after the migration is underway. The column `status` turns out to have fourteen distinct values, only three of which appear in the API documentation, with the other eleven being internal states used by background jobs that are not represented in any code you found in your initial audit. The column `amount` turns out to sometimes represent a credit and sometimes a debit depending on a flag in a related table that you had not noticed. The column `timestamp` turns out to be stored in the local timezone of the server that wrote it, not UTC, so the same value means different things depending on which data center it was written in.

These semantics discoveries mid-migration are dangerous because they invalidate assumptions baked into the migration plan. The backfill logic was written assuming uniform semantics, and now you discover the semantics are not uniform. The parity verification was written comparing fields directly, and now you discover some fields need timezone normalization before comparison.

The mitigation is to build the data dictionary before writing the migration plan. This means reading the schema definition, reading all the application code that accesses each relevant table, reading the git history for any comments or commit messages that explain unusual values, and talking to engineers who have worked with the system longest. The data dictionary should be written down and reviewed by the team before migration planning begins, and it should be updated as new semantics are discovered during the migration.

### Anti-Pattern 9: Single-Engineer Migration Execution

Running a migration with only one engineer available to execute it is a recipe for disaster. Migrations that change production state — especially migrations that involve a cutover window, a database failover, or a traffic ramp — require at minimum two engineers: one performing the steps and one watching the monitoring dashboards and ready to call a stop or rollback.

The reason for the two-engineer minimum is cognitive load. The engineer executing the migration steps is focused on the specific step they are performing: running the right command, in the right environment, with the right parameters. They cannot simultaneously be watching twelve dashboards for early signs of trouble. The second engineer has no other responsibility during the migration window except to watch the metrics and be ready to interrupt the first engineer if something looks wrong.

For particularly complex migrations — a database failover, a major traffic cutover — a third engineer as an independent observer is valuable. The independent observer's role is to look at the big picture that neither the executor nor the dashboard-watcher might see: is the pace of the cutover matching the plan? Are there dependencies that were not accounted for? Is the monitoring capturing everything it should? The independent observer can also serve as the escalation authority — the person who calls the stop if the executor and dashboard-watcher are disagreeing or both uncertain.

Single-engineer migrations are tempting because they are simpler to coordinate: no need to schedule a second engineer's time, no need to brief them on the plan. But the risk is disproportionate. Two engineers for a two-hour migration window is not a significant resource cost compared to the cost of a migration incident caused by insufficient oversight.

### Anti-Pattern 10: Migrating Caches Without Migrating the Backing Store First

In systems with caches (Redis, Memcached, application-level caches), the cache is a derived representation of data from the backing store. When you migrate the backing store (the database), the cache remains populated with values from the old backing store schema. If the new backing store schema changes the data representation in a way that is incompatible with the cache keys or cache values, cached responses will be stale or incorrect after the backing store migration.

The most dangerous version of this anti-pattern occurs when the cache is warm and the cache hit rate is high. If 95% of reads are served from cache, the impact of incorrect cache entries is not immediately visible — 95% of reads return cached values (which are wrong) and only 5% of reads hit the database (which is correct). Users see a mix of correct and incorrect responses depending on whether their request hits the cache or the database. This inconsistency is confusing and hard to debug.

The mitigation is to treat the cache as a migration dependency that must be explicitly addressed in the migration plan. Before migrating the backing store, ensure that the cache is warmed with values that will remain valid after the migration. If the migration changes the representation of cached values (e.g., changing a JSON response structure), invalidate all cache entries for the affected keys as part of the migration, rather than letting them expire naturally. Use a cache key versioning scheme (e.g., prefix all cache keys with a version number) so that migrating the backing store can be paired with bumping the cache key version, which automatically causes all old cache entries to be ignored and new entries to be populated from the new backing store.

### Anti-Pattern 11: Not Accounting for Read-Only Replicas in Migration Testing

Most production database setups use read replicas to offload read traffic from the primary. Read replicas receive changes via replication, so they are always slightly behind the primary. During a migration, read replicas add complexity that is often not accounted for in testing.

The specific failure mode is this: the migration is tested against the primary database, where the new column or new schema is immediately visible. But production read traffic is served from read replicas, which may not yet have the new schema. If the migration deploys application code that reads from the new column before the read replicas have replicated the schema change, those reads fail on the replicas. The application code — which works correctly against the primary in testing — fails in production because the test environment did not use replicas.

This is particularly common when a migration does the following sequence: add a column (DDL that replicates to replicas), deploy application code that reads the new column (code deployment that goes to app servers immediately), and then experience a window where the column DDL is on the replicas but the code deployment has already happened. In a high-replica-count setup, replication can take several seconds to propagate to all replicas. During those seconds, the application code is trying to read a column that does not yet exist on the replicas that happen to be serving those particular requests.

The mitigation is to design deployments so that the schema change reaches all replicas before the application code that depends on the new column is deployed. In practice, this means deploying the schema change and then waiting for a "replication fully propagated" confirmation before initiating the code deployment. Automated replication lag monitoring in the deployment pipeline can enforce this: the code deployment is gated on all replicas having replication lag below 1 second (or preferably 0 seconds) for the relevant table.

### Brainstorming Q&A: Extended Anti-Patterns

**Q: Of the eleven anti-patterns described in this chapter (six in Part 14 and five in Part 20), which is the hardest to prevent organizationally and why?**

The hardest anti-pattern to prevent organizationally is anti-pattern 2 — skipping the contract phase of expand-contract. All of the other anti-patterns are either detectable during migration execution (the Big Bang Cutover, not testing rollback) or produce visible immediate failures (dual-write ordering bugs, migrating without backing store migration). But skipping the contract phase is invisible in the short term: the system continues to work after the expand and migrate phases. The old code path is still there, still functional, still tested. There is no alert, no failure, no user impact. The damage accumulates silently over months and years, compounding with each subsequent migration that also skips its contract phase.

This invisibility is what makes it hardest to prevent organizationally. Human attention naturally focuses on visible problems. Engineers and managers who have competing priorities will always find urgent, visible problems to address instead of the invisible, long-term cost of un-contracted migrations. The only effective prevention mechanism is automated tracking: every migration must have an explicit contract-phase completion milestone tracked in an engineering management system, with an owner and a deadline. When the deadline passes without completion, an automated notification is sent to the owner's manager. The migration is not marked "complete" in any organizational tracking system until the contract phase is verified. This takes the prevention of the anti-pattern out of the realm of individual engineering judgment (which will fail under time pressure) and into the realm of organizational process (which is at least mechanically enforced). Building this tracking and escalation system is itself a staff-level technical program management task.

**Q: How do you handle the political dimension of migration anti-patterns — specifically, when the anti-pattern was committed by a senior engineer and admitting it was a mistake requires that senior engineer to lose face?**

The political dimension of migration anti-patterns is real and should not be dismissed as unprofessional. Engineers at all levels, including senior ones, have an ego investment in the quality of their work, and being told that a migration they designed or executed has an anti-pattern can feel like personal criticism. The way you handle this conversation significantly affects both the outcome of the specific situation and your ongoing working relationship with the senior engineer.

The most effective approach is to separate the pattern from the person and to lead with curiosity rather than judgment. Instead of "you skipped the contract phase, which is an anti-pattern," the conversation is "I was looking at this migration and I noticed the old column is still present six months after the new one was deployed — do you know if there's a reason we kept it?" This framing invites the senior engineer to explain the situation. Often there is context you did not have: perhaps the contract phase was deliberately deferred because of a dependency that has not been resolved, or perhaps the senior engineer agrees that it needs to be completed but the work has not been prioritized. You learn more by starting with curiosity, and you avoid triggering defensiveness that would make the conversation unproductive. If the honest answer is "we got busy and forgot to clean it up," the senior engineer is more likely to admit this and engage constructively if they do not feel they are being accused rather than asked.

---

## Part 21: The Long View — Why Migration Discipline Compounds

### Why the First Migration Sets the Standard

The first major migration an engineering team executes together sets the cultural and technical standard for all migrations that follow. If the first migration is planned carefully, uses expand-contract, has a documented rollback plan, includes migration-specific monitoring, and completes all three phases including contract, then the team has established a template and a precedent. Future migrations will be planned to the same standard because that is how migrations are done at this company. Engineers who join later will absorb the standard from observing and participating in migrations that follow it.

If the first migration is executed sloppily — done during a maintenance window, without a rollback plan, with the contract phase deferred indefinitely — then that sloppy standard becomes the organization's baseline. Future engineers will plan their migrations to the observed standard, not to the theoretical ideal. The first migration matters disproportionately because of its lasting influence on the team's approach to all future migrations.

This is one of the reasons staff engineers invest significant time and care in migrations that might seem, from a purely technical standpoint, relatively simple. The technical complexity of adding a column to a table is low. The organizational value of doing it correctly — demonstrating the expand-contract pattern, running a rollback drill, executing the contract phase — is high, because it sets the standard for everyone watching.

### The Accumulation of Migration Debt

Migration debt — the accumulation of incomplete migrations, un-contracted expand phases, and compatibility shims — has a compounding effect that is similar to financial compound interest but in reverse. Each piece of migration debt makes future changes slightly more expensive: more code paths to account for, more edge cases to test, more historical context required to understand what is happening. Over years, this compound accumulation of migration debt is one of the primary reasons that systems become progressively harder to change.

The relationship between migration debt and system velocity is captured in this observation from software engineering research: as systems age, the productivity of engineers working on them typically decreases unless active effort is made to pay down technical debt. Migration debt is a specific and particularly insidious form of technical debt because it is invisible to tools like static analysis and is often not recognized as debt by engineers who did not work on the original migration.

The investment required to keep migration debt at zero is significant but predictable. Every migration needs to budget time for the contract phase. Every migration needs to be tracked through to completion. Every compatibility shim needs a removal milestone. The investment is incremental and ongoing — a few hours of cleanup here, a few days of contract-phase work there. The alternative is an increasing investment in understanding, working around, and eventually desperately cleaning up years of accumulated migration debt. The compounding math strongly favors the incremental approach.

### Migration Discipline as a Hiring Signal

Teams that practice rigorous migration discipline attract engineers who care about long-term system quality. The ability to say "we use gh-ost for all schema migrations, we have a migration tracking system, we run rollback drills, and we have never had a migration-related production incident in the past two years" is a powerful signal in engineering hiring. It tells candidates that the team thinks carefully about production risk, that the codebase is maintained rather than just grown, and that engineering standards are taken seriously.

Conversely, teams that are known within an engineering community for migration disasters — the stories of the three-hour outage from an unconstrained ALTER TABLE, the data loss from a dual-write that was never validated — struggle to attract engineers who have the experience and judgment to prevent such incidents. The migration discipline of a team is visible to experienced engineers who interview there: they will ask about how migrations are done and form accurate assessments from the answers.

For an L6 engineer who joins an organization without rigorous migration practices, building that rigor is both an engineering contribution and an organizational one. The engineering contribution is the tooling, the patterns, the standards. The organizational contribution is the cultural shift: making careful migration practice the expectation rather than the exception, making the contract phase a celebrated completion rather than an optional cleanup, making rollback drills a normal part of pre-migration preparation rather than a rare edge case. Both contributions are needed, and the organizational contribution is typically harder and more valuable.

### The Final Word: Migrations as Proof of Engineering Maturity

The ability to change a system safely while it is running is the ultimate proof of engineering maturity. It requires depth in distributed systems (to understand the CAP implications of dual-write), depth in database internals (to understand why ALTER TABLE locks and how to avoid it), depth in organizational engineering (to coordinate a multi-team migration program), and depth in product thinking (to understand what the user experiences during the transition period and why continuity matters).

No other single engineering challenge simultaneously demands this breadth of knowledge and this level of disciplined execution. Designing a system from scratch is, in many ways, easier: you make clean choices, you control all the variables, and if something does not work you can change it. Changing a system that is already running, that real users depend on, that has accumulated years of implicit constraints and dependencies — that requires the full range of an L6 engineer's capability.

When you walk into a system design interview and encounter a migration question, remember that the interviewer is asking this question precisely because it is hard. They want to see whether you reach for the unsafe, simple-sounding solution (maintenance window, big-bang cutover) or the safe, complex-to-explain solution (expand-contract, dual-write, feature flag ramp). They want to see whether you think about rollback before you think about forward progress. They want to see whether you recognize the organizational complexity in addition to the technical complexity.

And if you have internalized the patterns in this chapter — if you can explain not just what expand-contract is but why the contract phase is the hardest phase to get organizations to complete, if you can explain not just what dual-write is but what causes ordering bugs and how to prevent them, if you can explain not just what a rollback trigger is but why it must be defined before the migration begins rather than after something goes wrong — then you are thinking at the level of an L6 engineer. That is the level of thinking that this chapter exists to develop.

---

## Quick-Reference Summary Table: Patterns vs. Problems

```
WHICH PATTERN SOLVES WHICH PROBLEM?

PROBLEM                           | PATTERN TO USE
----------------------------------+----------------------------------------
Need to add a column to huge table| Expand-Contract + Batch Backfill + gh-ost
  without locking production       | (5-step sequence from Part 3)
----------------------------------+----------------------------------------
Need to migrate to a new database | Dual-Write + Shadow Reads + Parity
  while serving live traffic       | Verification + Feature Flag Ramp
----------------------------------+----------------------------------------
Need to break apart a monolith    | Strangler Fig + Proxy Layer + Shadow
  without a big-bang rewrite       | Comparison + Per-capability cutover
----------------------------------+----------------------------------------
Need to change an API that has    | Expand API (add new endpoint/field),
  many existing clients            | Deprecation lifecycle, Sunset enforcement
----------------------------------+----------------------------------------
Need to move infrastructure to    | Lift-and-shift + Blue-Green Deployment
  a new cloud/region               | + Short write-drain cutover window
----------------------------------+----------------------------------------
Need to gradually ramp a risky    | Feature Flag Ramp (1% -> 5% -> 20% ->
  change with fast rollback        | 100%) + pre-defined rollback triggers
----------------------------------+----------------------------------------
Need to make a schema change that | Expand-Contract with backward-compatible
  is backward compatible           | defaults, nullable-first, no forced change
----------------------------------+----------------------------------------
Need to validate new system before| Shadow Mode (read from both, trust old,
  switching user traffic           | compare results, log discrepancies)
----------------------------------+----------------------------------------
Need to prevent data loss during  | Parity Verification (continuous sampling
  dual-write migration period      | + diff + alert on mismatch rate > 0.01%)
----------------------------------+----------------------------------------
Need to handle a failed migration | Rollback Protocol (predefined steps,
  and restore the previous state   | tested in drill, triggers defined upfront)
----------------------------------+----------------------------------------
Need to coordinate migration      | Migration RFC + Multi-team tracking
  across 10+ engineering teams     | dashboard + sunset enforcement + program lead
```

---

## Part 22: Sample Interview Dialogue — Full Conversation

The following is a sample system design interview conversation demonstrating how an L6 candidate would discuss a migration problem. The interviewer's questions appear in bold. The candidate's responses demonstrate the patterns from this chapter applied conversationally.

**"Design a system for migrating 500 million user records from a monolithic MySQL database to a sharded PostgreSQL setup. The migration must complete within six months with zero data loss and no more than five minutes of total downtime."**

"Before I jump into the design, let me ask a few clarifying questions. First, what is driving the move to PostgreSQL — is it cost, features like JSONB support, or the sharding strategy? The answer affects which PostgreSQL features I would lean on. Second, how is the existing MySQL database accessed — through an ORM, raw SQL, or a data access layer that abstracts the database? That determines how much application code needs to change. Third, by 'sharded PostgreSQL,' are we talking about Citus, a custom sharding layer, or something else?

Assuming the answer is: we need sharding for horizontal write scalability, we have a data access layer that abstracts the database, and we are using Citus as the PostgreSQL sharding layer. Let me walk through the migration.

At 500 million records, this is a significant data volume. The six-month timeline is achievable but not comfortable — we will need to execute each phase efficiently. The five-minute total downtime constraint means we are looking at a blue-green style cutover at the very end, not a maintenance window.

I would structure the migration in five phases. The first phase is foundation: set up the Citus cluster, define the sharding key (I would use user_id with consistent hashing across shards, unless there is a geographic or tenant-based access pattern that suggests otherwise), and set up the new PostgreSQL schema in a schema registry so that both databases stay in sync during migration. This phase takes about two weeks and involves no production changes.

The second phase is dual-write: deploy application code that writes to both MySQL and Citus for every write operation. We use an async reconciliation queue for any Citus writes that fail, to ensure they are retried without failing the user's request. During this phase, all reads still come from MySQL. We begin the backfill of historical data from MySQL to Citus — at 500 million records, the backfill will be the longest step. At a batch size of 50,000 records per batch with a 100ms pause (tuned to keep replication lag under 1 second), we can process roughly 500,000 records per minute, meaning the backfill of all records takes approximately 16 hours. But we do not backfill all at once — we backfill gradually over two to three weeks to stay within our write amplification budget. The dual-write phase lasts approximately six weeks.

The third phase is parity verification: we run continuous sampling of records from both MySQL and Citus and compare them. At 500 million records, we sample approximately 10,000 records per hour. We define acceptable mismatch rate at 0.001% (5,000 records out of 500 million). Any mismatch triggers an alert. We run this phase for at least two weeks before advancing to the read migration. This phase overlaps with dual-write.

The fourth phase is read migration: we use a feature flag to shift reads from MySQL to Citus. We start at 1% and ramp to 100% over two weeks, with 24-hour holds at each ramp level and automated rollback if our key metrics (user authentication success rate, profile read error rate, parity mismatch rate) exceed thresholds. At 100% reads on Citus, we stop writes to MySQL (dropping dual-write) and promote Citus as the sole database. This is the five-minute downtime window: we drain writes, let Citus catch up on any pending async reconciliation, confirm zero replication lag, then complete the write cutover. The actual window of zero writes is typically 30-60 seconds for a well-prepared cutover, well within our five-minute budget.

The fifth phase is cleanup: we keep MySQL online as a read-only backup for 30 days. We monitor for any access to MySQL — which would indicate a consumer we missed. After 30 days with zero unexpected MySQL access, we export the MySQL data to cold storage for compliance purposes and decommission the MySQL cluster.

For monitoring, the critical metrics are: Citus write error rate and latency throughout dual-write, replication lag on Citus (measured via heartbeat writes), parity mismatch rate and mismatch categories, and the business metrics of user login success rate and profile completion rate. The migration dashboard is built before any phase starts. The rollback plan for each phase is documented and has been drilled in a staging environment.

The organizational risk I would flag is the team coordination required for the application code changes. If multiple teams own code that touches the user database, they all need to deploy dual-write-aware code within the same two-week window. I would plan a 'dual-write kickoff' event where all teams deploy simultaneously in a coordinated release, verifying that each team's changes are in place before moving forward."

**"What is the biggest risk in your plan, and how would you mitigate it?"**

"The biggest risk is the backfill phase producing silent data quality problems that are not caught by parity verification until after we have ramped reads to a significant percentage. Specifically, if the backfill has a systematic bug — say, a timezone conversion error in a field that stores timestamps — every affected record will fail parity verification, but if the bug is systematic and our parity verification sampling happens to not sample the affected records frequently enough, we could advance to the read migration phase with incorrect data in Citus.

The mitigation is two-part. First, I would add a category-specific parity check in addition to random sampling: instead of just sampling random records, the verification also specifically checks records with timestamps from each timezone the MySQL server might have used, records with the oldest and newest created_at values, and records where optional fields are null versus populated. This targeted sampling catches systematic bugs that random sampling might miss. Second, I would run a 'canary backfill' of 10,000 records before starting the full backfill, manually auditing 100 of those records field by field to confirm correctness before scaling up. The canary gives us early confidence in the backfill logic before we have committed to the full 500-million-record process."

This dialogue demonstrates the L6 pattern: clarifying questions before jumping in, structured multi-phase thinking, specific technical choices with justifications, monitoring and rollback integrated throughout, and the ability to identify and articulate the highest-risk element of the plan with a concrete mitigation.

---

## Final Exercise: Design Your Own Migration

This final exercise is open-ended and should be the capstone of your preparation for migration questions in interviews.

**Exercise Final:** Identify a real system you work with or have worked with that has a migration need — something that needs to change about how data is stored, how an API works, or what infrastructure it runs on. Design the complete migration plan using the patterns in this chapter. Your plan must include:

1. The migration type (data, code, infrastructure) and why that type requires specific patterns
2. The expand, migrate, and contract phases with specific steps in each
3. The monitoring dashboard design with specific metrics for each category (progress, health, parity, business)
4. The rollback plan for each phase, with rollback triggers defined as specific metrics and thresholds
5. The organizational coordination requirements: which teams are affected, what they need to do, and when
6. The estimated timeline for each phase, with an explanation of the key factors that determine that estimate
7. The three highest-risk elements of the plan and a specific mitigation for each

Present this plan to a colleague and defend it under questioning. The ability to defend a migration plan under questioning — including adversarial questions about failure modes, edge cases, and organizational challenges — is the final proof that you have internalized the material in this chapter.

---

*Next chapter: Chapter 98 — Technical Writing for Engineers*
