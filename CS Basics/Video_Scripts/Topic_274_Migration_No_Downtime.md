# Migration Without Downtime: Strategies

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Changing the engine of a plane mid-flight. Passengers don't notice. The plane keeps flying. Impossible? In software, it's real. You migrate from an old database to a new database while the application keeps serving traffic. Zero downtime. No "maintenance window." No "we'll be back at 6 AM." It's one of the hardest things in engineering—and one of the most impressive when you pull it off. Let's see how.

---

## The Story

You're on MySQL. You need to move to PostgreSQL. Or you're on one datacenter. You need to move to another. Or you're on a monolith. You're extracting a service. The data has to move. The traffic can't stop. Migrations without downtime require careful orchestration. You can't just "turn off the old, turn on the new." Users are active. Writes are happening. You need strategies that keep both systems in sync until the moment you cut over. Three main approaches: dual-write, CDC (Change Data Capture), and the strangler fig pattern. Each has trade-offs. Each solves a different problem. Master these, and you can migrate anything. Almost.

Think of it like moving to a new house. You don't abandon the old house on moving day. You move things gradually. Or you have two houses for a while—sleep in the new one, grab things from the old. Eventually the old is empty. You hand over the keys. Software migration is the same. Overlap. Sync. Cut over. Clean up. The overlap period is the tricky part. That's where the strategies matter.

---

## Another Way to See It

A restaurant is renovating. They can't close. So they renovate one section at a time. Or they open a second location. Same menu. Same staff. Gradually move customers. Old location gets quieter. New location gets busier. One day: old location closes. Strangler fig—that gradual replacement—or dual-operation during transition. The business never stops. That's zero-downtime migration.

---

## Connecting to Software

**Strategy 1: Dual-write.** Write to BOTH the old and new system. Read from the old. New system is a shadow. It catches up. Once the new system has all historical data (backfill) plus all new writes (dual-write), you verify. Compare. Fix drift. Then: switch reads to the new system. Now you read and write from new. Finally: stop writing to the old. Done. Risk: during dual-write, if you have a bug, you might write differently to old vs new. Drift. Validate. Monitor. The cutover from read-old to read-new is the critical moment. Do it gradually (canary) or all at once. Depends on your tolerance.

**Strategy 2: CDC (Change Data Capture).** Stream changes from the old system to the new. Database binlog. Or Debezium. Or Kafka Connect. Every insert, update, delete flows to the new system in real-time. No application changes for the write path—you're still writing to the old system. The new system receives a copy. Catch up on history (bulk load). Then turn on CDC. Once in sync, switch reads to new. Stop writes to old. Replicate final changes. Cut over. CDC avoids dual-write bugs—one source of truth, the old DB. But it requires the old system to support CDC (binlog, WAL, etc.). And schema mapping—old schema to new—can be complex. CDC is powerful for DB-to-DB migration. Or DB-to-data-lake. Or DB-to-search-index.

**Strategy 3: Strangler fig.** Don't migrate everything at once. New features use the new system. Old features stay on the old system. Gradually, you migrate old features one by one. The old system is "strangled"—it shrinks. Eventually it's gone. Good for extracting services from a monolith. Or migrating a large system in chunks. Slow. But low risk. No big-bang cutover. Each migration is small. Incremental. Martin Fowler named this. The strangler fig is a tree that grows around another, eventually replacing it. Software analog: new wraps old, old fades away.

**Verification: Shadow reads.** Before switching reads to the new system, read from BOTH. Compare results. Serve from old. Log discrepancies. Fix the new system until they match. Build confidence. Shadow reads catch bugs. "New system returns different data for this query." Fix it. Then cut over. Shadow reads are your safety net.

---

## Let's Walk Through the Diagram

```
DUAL-WRITE MIGRATION:

Phase 1: Backfill          Phase 2: Dual-write        Phase 3: Cutover
         
  App ──► Old DB            App ──► Old DB            App ──► New DB
   │                         │   ╲                     │
   │                         │    ╲                    │
   │                         │     ╲► New DB           │
   │                         │        (sync)          │
   │                         │                         │
   │  Copy historical data   │  Write to both          │  Read/write new only
   │  to New DB             │  Read from old          │  Stop old
   │                         │                         │
   ▼                         ▼                         ▼
  Old DB                    Both in sync              New DB only
```

The diagram shows the phases. Backfill gets history. Dual-write keeps them in sync. Cutover switches traffic. Each phase has validation. Don't skip verification. Drift is subtle. Catch it before users do.

---

## Real-World Examples (2-3)

**Stripe** has written about their migration from a single PostgreSQL primary to a distributed setup. Dual-write. Verification. Gradual cutover. They run money. Zero tolerance for data loss. Their process is a masterclass. Read their engineering blog.

**LinkedIn** migrated from MySQL to Espresso (their distributed DB) at massive scale. Used custom CDC. Binlog streaming. Backfill. Sync. Cutover per table or per partition. Took years for some migrations. But no downtime. Users never noticed.

**Netflix** uses the strangler fig for extracting services from their monolith. New features in microservices. Old features migrated one domain at a time. No big rewrite. Incremental. Their famous "we're not a microservices company, we're a microservices migration company" (or similar)—they're always migrating. Strangler fig is the pattern.

---

## Let's Think Together

**"Migrating from MySQL to PostgreSQL. 500GB of data. 10K writes/sec. How do you ensure zero data loss during migration?"**

Dual-write or CDC. For 10K writes/sec, CDC is often cleaner—no application changes to write path. Use Debezium or similar. Stream MySQL binlog to Kafka. Consumer writes to PostgreSQL. Backfill: bulk load 500GB. Mark the position. CDC catches up from that position. Verify: checksums, row counts, sample queries. Shadow reads: read from both, compare. Fix discrepancies. When confident: switch reads to PostgreSQL. Application now reads from PostgreSQL, still dual-writes (or CDC from MySQL) until you're sure. Then stop MySQL writes. Zero loss: every write either goes to both (dual-write) or flows through CDC. Validate. Re-validate. Data migration bugs are catastrophic. Take your time. Automate verification. Don't trust "it looks good." Prove it.

---

## What Could Go Wrong? (Mini Disaster Story)

A team did dual-write. They had a subtle bug: under a race condition, sometimes they wrote to old but not new. Rare. One in 10,000. They didn't notice during testing. Cutover day. They switched reads to new. A fraction of data was missing. User accounts. Orders. Chaos. Rollback was impossible—they'd stopped writing to old. They had to reconcile. Manually. For days. Customers impacted. Lesson: verification must be thorough. Not just "row counts match." Checksums. Sampling. Load testing that exercises races. And: consider keeping dual-write a bit longer after cutover. Write to both. Read from new. If you find drift, you still have old. Gradual decommission of old. Safety buffer. Migrations are high-stakes. Over-invest in verification.

---

## Surprising Truth / Fun Fact

The strangler fig pattern is named after a real tree. Strangler figs grow from seeds dropped by birds in the branches of host trees. They send roots down. Gradually envelop the host. The host dies. The fig remains—a hollow structure that was once another tree. Creepy? Maybe. But the software pattern is elegant. Gradual replacement. No big bang. Nature figured it out. We copied it.

---

## Quick Recap (5 bullets)

- **Dual-write** = write to both; read from old; sync; switch reads to new; stop old.
- **CDC** = stream changes from old to new; one write path; no dual-write bugs; requires binlog/WAL.
- **Strangler fig** = new features on new system; migrate old features gradually; no big cutover.
- **Verification** = shadow reads, checksums, sampling; never skip; drift is subtle.
- **Zero data loss** = every write must reach new system; validate obsessively.

---

## One-Liner to Remember

*Zero-downtime migration is changing the engine mid-flight—dual-write, CDC, or strangler fig; verify obsessively; cut over when you're sure.*

---

## Next Video

Next: Rollback. When do you roll back? When do you fix forward? And the nightmare: database migrations. See you there.
