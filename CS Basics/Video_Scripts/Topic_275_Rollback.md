# Rollback: When and How

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You paint your room bright orange. Step back. "This is horrible." Option 1: paint over it. Roll back to the previous color. Option 2: live with it. Accept. Option 3: add some design elements to make it work. Fix forward. In deployments, it's the same. The new version is broken. You can rollback—deploy the previous version. Or fix forward—deploy a quick patch. Or accept—if it's minor. Knowing WHEN and HOW to rollback is critical. Get it wrong, and you make things worse. Get it right, and you save the day. Let's see how.

---

## The Story

You deploy. Something goes wrong. Error rate spikes. Critical feature broken. Users complain. Your heart sinks. What do you do? Rollback seems obvious. "Let's go back to the last known good." But rollback isn't always safe. Sometimes the previous version has its own bugs. Sometimes you've made database changes that the old code can't handle. Sometimes rollback takes longer than fixing. You need a decision framework. When to rollback. When to fix forward. And how to do each. Fast. Without panic.

Think of it like driving. You take a wrong turn. Do you reverse? Or find another route? Reversing might be dangerous—traffic, obstacles. Finding a route might be faster. Context matters. In software: error rate 10x? Probably rollback. Typo in a label? Fix forward. Data at risk? Rollback immediately. Schema migration involved? Rollback is risky. Think before you act. But don't freeze. Have a plan. Execute.

---

## Another Way to See It

A chef adds too much salt. Option 1: throw it out, start over (rollback). Option 2: add more ingredients to balance (fix forward). Option 3: serve it—maybe some customers like salt (accept). The dish is your deployment. The chef's decision: start over, fix, or accept. Depends on how bad it is. How easy to fix. How much is at stake. Same logic in software.

---

## Connecting to Software

**When to rollback:** Error rate spiked significantly (2x, 5x, 10x). Critical functionality broken—checkout, login, payments. Data corruption risk. SLO is burning fast—you're consuming error budget rapidly. Security incident—the deploy introduced a vulnerability. In these cases, rollback first. Stop the bleeding. Investigate later. Speed matters. Have a one-command or one-click rollback. Practice it. When the pager fires, you don't want to figure out the process.

**When to fix forward:** The issue is minor—typo, wrong config. Rollback is risky—you've run a schema migration; the old code expects the old schema. Fix is quick and well-understood—you know exactly what's wrong, patch is small. The new version has fixes you need—rolling back would re-introduce a bug you fixed. In these cases, fix forward might be better. Deploy a patch. Don't roll back. Judgment call. Err on the side of rollback when uncertain. Users prefer "working like before" over "broken new."

**How to rollback:** Blue-green—switch traffic back to blue. Instant. Kubernetes—deploy previous image. `kubectl rollout undo`. Or redeploy the last known good revision. Containers make this easy. Old images are still in the registry. Feature flags—toggle the flag off. No deployment. The new code is still there, just disabled. Fast. Different mechanisms for different setups. Know yours. Automate it. One command. One click.

**Database rollbacks—THE hard part:** You deployed new code AND a schema migration. New column. New table. The new code uses it. You rollback the code. The old code doesn't know about the new column. Is that a problem? If the migration only added a nullable column—maybe OK. Old code ignores it. If the migration dropped a column—old code will crash. Rollback code + rollback migration. Migrating backwards is dangerous. Schema migrations are often one-way. Best practice: forward-only migrations. Backward-compatible code. New code works with old schema. Old code works with new schema (during the transition). Then you can rollback code without rolling back schema. Design for it. It's not easy. It's essential.

---

## Let's Walk Through the Diagram

```
ROLLBACK DECISION TREE:

         Deploy broke something
                    |
        ┌───────────┼───────────┐
        |           |           |
   Critical?    Minor?     Rollback risky?
   (errors,     (typo,     (schema migration,
    data)       config)     old code incompatible)
        |           |           |
        v           v           v
   ROLLBACK    FIX FORWARD   FIX FORWARD
   (switch     (patch)       (fix, don't revert
    traffic)                  schema)
        |
        v
   Blue-green? Switch back
   K8s? kubectl rollout undo
   Flag? Toggle off
```

The diagram captures the logic. Critical → rollback. Minor → fix forward. Rollback risky (e.g., schema) → fix forward. And know your rollback mechanism. Practice. Drill.

---

## Real-World Examples (2-3)

**Netflix** has automated rollback. If error rate or latency crosses a threshold, the system can automatically roll back. No human in the loop for the initial response. Humans investigate after. Speed. They've built the tooling. Chaos engineering ensures rollback is tested. When real failure happens, rollback works.

**GitHub** has documented their deployment process. They can roll back in minutes. Deploy and rollback are equally practiced. They've had incidents where rollback saved them. The key: it's not an afterthought. Rollback is a first-class operation. Designed. Tested. Ready.

**A startup** deployed with a schema migration. New column, NOT NULL. They didn't backfill. Rollback time. Old code expected the column to exist (or didn't—actually the new code added it). They rolled back code. The migration had already run. The new column existed. Old code didn't use it. They got lucky. Next time they added a nullable column. Backfilled. Then made it NOT NULL in a second migration. Backward compatible. Rollback-safe. Lesson: design migrations for rollback. It's not automatic. You have to think about it.

---

## Let's Think Together

**"You deployed a new version with a DB migration that adds a column. The new version has a bug. Can you just rollback the code? What about the new column?"**

It depends. If the column is nullable and the old code never touches it—rollback is usually safe. Old code doesn't know about the column. It ignores it. No crash. If the column is NOT NULL and has no default—the migration might have failed anyway. If it succeeded, existing rows have a value. Old code might still work if it doesn't query that column. The risky case: if the new code wrote data the old code can't handle. Or if the migration modified existing columns. Rollback code: OK. Rollback migration: hard. Often you can't. Forward-only migrations. Add column (nullable). Backfill. Make NOT NULL in a second migration. Each step is safe. Rollback code = no problem. The column might be empty or have data. Old code doesn't care. Design for this. Test rollback in staging. With the migration. Does old code work with new schema? Verify. Don't assume.

---

## What Could Go Wrong? (Mini Disaster Story)

A team rolled back. They thought they'd deployed the previous version. But their rollback script had a bug. It deployed an OLDER version—from two weeks ago. That version had a critical security flaw. They'd fixed it last week. Now they'd just re-introduced it. Worse: that old version wasn't compatible with recent database migrations. The app crashed. Double failure. They fixed the rollback script. Deployed the correct "last known good." Took an hour. Lesson: rollback must deploy the RIGHT version. Not "previous" blindly. "Last known good." Tag it. Test the rollback path. Your rollback script is critical infrastructure. Treat it that way. One bug there can make incidents worse. Verify. Test. Document.

---

## Surprising Truth / Fun Fact

The term "rollback" comes from aviation. Rolling back the throttle. Reducing power. Going back to a previous state. Software adopted it. "Rollback the deploy." Same idea. Revert to before. The aviation industry has checklists for everything. Rollback procedures. Software operations learned from that. Checklists. Procedures. Practice. When things go wrong, follow the checklist. Don't improvise. Rollback is your emergency procedure. Have it. Know it. Drill it.

---

## Quick Recap (5 bullets)

- **When to rollback** = error spike, critical break, data risk, SLO burning; when in doubt, rollback.
- **When to fix forward** = minor issue, rollback risky (schema), fix is quick and known.
- **How** = blue-green switch, K8s rollout undo, feature flag toggle; automate; practice.
- **Database** = the hard part; design backward-compatible migrations; forward-only when possible.
- **Rollback script** = must deploy "last known good"; test it; a bug there makes incidents worse.

---

## One-Liner to Remember

*Rollback is painting over the orange—when to do it, how to do it, and why database migrations make it tricky.*

---

## Next Video

That wraps up this series. You've got edge caching, Redis, deployment, observability, SLOs, capacity, cost, migration, and rollback. See you in the next one.
