# Chapter 33 Supplement: Deployment Strategies, Operations, and Reliability Engineering

---

# Introduction

Chapter 27 covers System Evolution—how systems change over time, migration strategies, and technical debt. But the video series (Topics 267–275) requires operational topics that existing chapters don't cover as standalone subjects: deployment strategies, runbooks, observability, SLO/error budgets, capacity planning, cost modeling, and rollback tactics. This supplement fills that gap.

These are not theoretical topics. At Staff level, you're asked to choose the right deployment strategy for a given risk profile, design incident response that scales, explain why SLOs and error budgets matter for velocity, and make cost-reliability trade-offs that align with business goals. This supplement gives you the operational depth needed to answer those questions with precision.

**The Staff Engineer's Ops Principle**: Deployment, observability, and reliability are not "someone else's job." They are first-class design decisions. The deployment strategy affects how fast you can ship and how quickly you can recover. Observability determines whether you can debug. SLOs and error budgets determine whether you ship features or fight fires.

**Topic mapping** (Video Topics 267–275):

| Topic | Covered In |
|-------|------------|
| 267 | Blue-Green, Canary (Parts 1–2) |
| 268 | Canary automation, feature flags (Part 2) |
| 269 | Runbooks, Incident Response (Part 3) |
| 270 | Observability — Logs, Metrics, Traces (Part 4) |
| 271 | SLO, SLI, Error Budget (Part 5) |
| 272 | Capacity Planning (Part 6) |
| 273 | Cost Modeling (Part 7) |
| 274 | (Resilience/chaos—covered in other chapters) |
| 275 | Rollback Strategies (Part 8) |

**How to use this supplement**: Read it alongside Chapter 27. For interview prep, focus on the L5 vs L6 tables, the ASCII diagrams, the incident response lifecycle, the SLO/error budget math, and the rollback decision tree. For practical use, work through the runbook template, the observability correlation flow, and the capacity-planning checklist. The goal is not to memorize tools but to build intuition—so you can reason about deployment, ops, and reliability when the interviewer asks "how" or "what happens when."

---

## Quick Visual: Deployment & Ops at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│     DEPLOYMENT, OPS & RELIABILITY: THE LAYERS AT STAFF LEVEL                │
│                                                                             │
│   L5 Framing: "We deploy with blue-green; we have metrics and logs"         │
│   L6 Framing: "Deployment strategy is a risk/cost trade-off; observability  │
│                is logs + metrics + traces with correlation; SLOs drive      │
│                velocity via error budgets; capacity planning prevents       │
│                outages before they happen—and cost modeling informs         │
│                reliability decisions"                                      │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  DEPLOYMENT (Topics 267–268):                                        │   │
│   │  • Blue-green: instant rollback, double cost, schema trickiness       │   │
│   │  • Canary: small blast radius, gradual rollout, complex routing      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  INCIDENT RESPONSE (Topic 269):                                      │   │
│   │  • Runbooks BEFORE incidents; Detect → Triage → Mitigate → Postmortem │   │
│   │  • Blameless postmortems; action items with owners                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  OBSERVABILITY (Topic 270):                                           │   │
│   │  • Logs: what happened? Metrics: how bad? Traces: where's the slow?  │   │
│   │  • Request ID links all three                                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  SLO / ERROR BUDGET (Topic 271):                                      │   │
│   │  • SLI = measurement; SLO = target; SLA = contract                   │   │
│   │  • Error budget = permission to fail; drives velocity vs stability   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  CAPACITY & COST (Topics 272–273):                                    │   │
│   │  • Capacity: measure → model → scale before limits                   │   │
│   │  • Cost: know drivers; Staff asks "is $X for 99.99% worth it?"        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  ROLLBACK (Topic 275):                                                │   │
│   │  • When to roll back vs fix forward                                  │   │
│   │  • Schema = the hard part; always backward-compatible migrations     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Deployment & Ops Thinking

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Choosing deployment strategy** | "We use blue-green for zero downtime" | "Blue-green for high-risk changes (double cost, instant rollback). Canary for gradual rollout when we want small blast radius. Feature flags when we need user-level control without per-server deployment. Match strategy to risk profile and infrastructure." |
| **Incident response** | "We have on-call and they fix things" | "Runbooks written *before* incidents. Incident Commander coordinates. Severity drives who gets paged. Blameless postmortems with action items and owners. Detect → Triage → Mitigate → Root Cause → Fix → Postmortem." |
| **Observability** | "We have logs and Grafana" | "Three pillars: Logs (what happened—debugging), Metrics (how bad—alerts, dashboards), Traces (where's the bottleneck—microservices). Request ID correlates all three. 'System slow' → metrics (which spike?) → traces (which hop?) → logs (what query/error?)." |
| **SLOs and velocity** | "We aim for 99.9% uptime" | "SLO = target. Error budget = 100% - SLO = permission to fail. 99.9% = 43 min/month. If budget healthy → ship faster. If burning → slow down, fix reliability. Error budget balances innovation vs stability." |
| **Capacity planning** | "We add servers when we're full" | "Measure current usage. Model growth. Identify which component hits limits first. Scale at 70–80% utilization—before 100%. Load test before peak. Staff question: what's the cheapest/safest mitigation for the *actual* bottleneck?" |
| **Cost vs reliability** | "We need 99.99% availability" | "99.99% costs more than 99.9%. Staff asks: 99.99% = 43 min/year downtime vs 99.9% = 8.7 hours/year. Is the extra cost ($450K/month?) worth 8 hours less downtime? Business decides." |
| **Rollback decision** | "If it breaks, we roll back" | "Roll back when: error spike, critical break, data corruption risk, SLO burning. Fix forward when: minor issue, rollback risky (schema migration), fix is quick. Schema: always backward-compatible. Add column → deploy code → remove old column later." |

**Key Difference**: L6 engineers connect operational mechanics to business and velocity outcomes. They know when to roll back vs fix forward, how error budgets drive behavior, and what the cost of reliability actually is.

---

# Part 1: Blue-Green Deployment (Topic 267)

## What It Is

**Blue-Green deployment** uses two identical production environments: **Blue** (current version) and **Green** (new version). You deploy the new version to Green, test it, then switch traffic from Blue to Green. Rollback means switching traffic back to Blue.

## How It Works

1. **Deploy** new version to Green environment (servers, containers, or infrastructure).
2. **Test** Green in production—it's live but receives no user traffic yet.
3. **Switch** traffic from Blue to Green via DNS flip, load balancer config change, or router update.
4. **Rollback** (if needed): switch traffic back to Blue. Instant.

## ASCII Diagram: Blue-Green Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BLUE-GREEN DEPLOYMENT ARCHITECTURE                        │
│                                                                             │
│                         ┌─────────────────┐                                  │
│                         │  DNS / Load     │                                  │
│                         │  Balancer       │                                  │
│                         │  (Traffic       │                                  │
│                         │   Director)     │                                  │
│                         └────────┬────────┘                                  │
│                                  │                                           │
│                    Traffic switch: Blue ←→ Green                              │
│                                  │                                           │
│              ┌───────────────────┴───────────────────┐                       │
│              │                                       │                       │
│              ▼                                       ▼                       │
│   ┌─────────────────────┐               ┌─────────────────────┐           │
│   │       BLUE           │               │       GREEN          │           │
│   │   (Current v1)       │               │   (New v2)           │           │
│   │                     │               │                     │           │
│   │   ┌───┐ ┌───┐ ┌───┐ │               │   ┌───┐ ┌───┐ ┌───┐ │           │
│   │   │ A │ │ B │ │ C │ │   Idle or     │   │ A │ │ B │ │ C │ │           │
│   │   └───┘ └───┘ └───┘ │   Decommissioned  └───┘ └───┘ └───┘ │           │
│   │                     │               │                     │           │
│   └──────────┬──────────┘               └──────────┬──────────┘           │
│              │                                       │                       │
│              └───────────────────┬───────────────────┘                       │
│                                  │                                           │
│                                  ▼                                           │
│                         ┌─────────────────┐                                  │
│                         │   Shared DB      │                                  │
│                         │   (Schema v1/v2  │                                  │
│                         │   must coexist)  │                                  │
│                         └─────────────────┘                                  │
│                                                                             │
│   BEFORE SWITCH: 100% → Blue   |  AFTER SWITCH: 100% → Green                 │
│   ROLLBACK:      Switch back to Blue (instant)                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Advantages

| Advantage | Why It Matters |
|-----------|----------------|
| **Instant rollback** | Flip traffic back to Blue. No redeploy. Seconds, not minutes. |
| **Zero-downtime deploy** | Users never see "maintenance" or failed requests during the switch. |
| **Production testing** | Green runs against real DB, real infra. Test in prod before serving traffic. |
| **Simple mental model** | Two environments. One has traffic. Switch when ready. |

## Disadvantages

| Disadvantage | Mitigation |
|--------------|------------|
| **Double infrastructure cost** | During deploy, both Blue and Green run. For large fleets, expensive. Consider for high-risk changes only. |
| **Database schema challenge** | Both Blue and Green point to the same database. If v2 needs a new column, v1 must not break. |
| **Stateful services** | Sticky sessions, in-memory state—switching may disconnect users. Design for stateless or session affinity. |

## The Database Challenge: Schema Migrations

**The problem**: Blue runs schema v1. Green needs schema v2. Both share the same database. If you deploy schema v2 (add column, drop column), Blue's code may break.

**Solution: Backward-compatible schema migrations**

```
Phase 1: Add column (nullable or with default)
  • Schema: ADD COLUMN new_field VARCHAR(255) NULL;
  • Blue and Green both work. Blue ignores it. Green doesn't use it yet.

Phase 2: Deploy Green code that READS new_column
  • Green uses new_column. Blue still ignores. Both work.

Phase 3: Deploy Green code that WRITES new_column
  • Green populates new_column. Blue still ignores.

Phase 4: Deploy Green that stops using old_column
  • Now both use new_column. Blue (old) may still read old_column—keep it.

Phase 5: (Later, separate deploy) Remove old_column
  • Only when NO code reads old_column. Safe to DROP.
```

**Concrete SQL example** (renaming `email` to `email_address`):

```sql
-- Phase 1: Add new column
ALTER TABLE users ADD COLUMN email_address VARCHAR(255) NULL;

-- Phases 2–3: Backfill (run as batch job)
UPDATE users SET email_address = email WHERE email_address IS NULL;

-- Phase 4: Deploy code that reads/writes email_address only
-- Phase 5 (weeks later): Drop old column
ALTER TABLE users DROP COLUMN email;
```

**Never**: Drop a column in the same deploy as code that stops using it. If rollback happens, code expects the column—it's gone. **Always** separate schema changes from code changes when possible, and make schema forward- and backward-compatible.

## Blue-Green: Practical Considerations

### Traffic Switching Mechanisms

| Mechanism | How It Works | Latency | Use Case |
|-----------|--------------|---------|----------|
| **DNS flip** | Change A record from Blue IP to Green IP | Minutes (TTL propagation) | When instant switch not critical |
| **Load balancer** | Update LB pool to point to Green | Seconds | Most common. Instant. |
| **Router / service mesh** | Update routing rules | Seconds | Kubernetes, Istio, Envoy |
| **Feature flag at LB** | Toggle which pool gets traffic | Instant | When combined with feature management |

### Stateful Considerations

Blue-Green assumes **stateless** application servers. If servers hold:

- **In-memory sessions**: Users get disconnected when switching. Mitigation: store sessions in Redis/DB, or use sticky sessions with same-pool affinity.
- **WebSocket connections**: All connections to Blue break when traffic switches. Clients must reconnect. Acceptable for short-lived connections; problematic for long-lived chat/gaming.
- **Local caches**: Green starts with cold cache. First requests after switch may be slow. Mitigation: warm cache on Green before switch, or accept brief latency spike.

### Cost Optimization

When double infra cost is prohibitive:

- **Blue-green for critical services only**: Use for payment, auth. Use rolling or canary for less critical.
- **Reduce Green size initially**: Deploy Green with 50% of Blue's capacity for testing; scale up right before switch.
- **Quick switch + decommission**: Minimize time both run. Switch within minutes of Green validation, then tear down Blue immediately.

## L5 vs L6: Blue-Green

| Aspect | L5 | L6 |
|--------|-----|-----|
| **When to use** | "For zero downtime" | "When instant rollback is critical and double cost is acceptable. High-risk changes, major version upgrades." |
| **Schema** | "We run migrations" | "Schema migrations must be backward-compatible. Add → use → deprecate → remove. Never drop in same deploy as code change." |
| **Stateful** | "We have two envs" | "Sessions in external store. WebSockets: expect reconnect. Cache: warm or accept cold start." |

---

# Part 2: Canary Deployment (Topic 267)

## What It Is

**Canary deployment** routes a small percentage of traffic (1–5%) to the new version. Monitor error rates, latency, and metrics. If good → increase to 25% → 50% → 100%. If bad → roll back the canary (stop routing traffic to it).

The name comes from coal miners using canary birds to detect toxic gas—the canary fails first, small blast radius.

## How It Works

1. **Deploy** new version to a subset of servers (or a canary pool).
2. **Route** 1–5% of traffic to canary via load balancer or service mesh.
3. **Monitor** error rate, latency (p50, p99), CPU/memory, business metrics.
4. **Promote** if metrics good: 25% → 50% → 100%.
5. **Roll back** if metrics bad: route 0% to canary, drain and decommission.

## ASCII Diagram: Canary Traffic Split

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CANARY DEPLOYMENT — TRAFFIC SPLIT                         │
│                                                                             │
│                         ┌─────────────────┐                                  │
│                         │  Load Balancer   │                                  │
│                         │  / Router       │                                  │
│                         └────────┬────────┘                                  │
│                                  │                                           │
│              ┌───────────────────┼───────────────────┐                       │
│              │                   │                   │                       │
│        95% traffic          5% traffic                │                       │
│              │                   │                   │                       │
│              ▼                   ▼                   │                       │
│   ┌─────────────────────┐   ┌─────────────────────┐  │                       │
│   │   BASELINE (v1)     │   │   CANARY (v2)       │  │                       │
│   │   Pool of N servers │   │   Pool of M servers │  │                       │
│   │                     │   │   (M << N)          │  │                       │
│   │   ┌───┐ ┌───┐ ┌───┐ │   │   ┌───┐ ┌───┐       │  │                       │
│   │   │ 1 │ │ 2 │ │...│ │   │   │ C1│ │ C2│       │  │                       │
│   │   └───┘ └───┘ └───┘ │   │   └───┘ └───┘       │  │                       │
│   └──────────┬──────────┘   └──────────┬──────────┘  │                       │
│              │                         │             │                       │
│              │     Metrics Comparison  │             │                       │
│              │     Canary vs Baseline  │             │                       │
│              └─────────────┬───────────┘             │                       │
│                            │                         │                       │
│                            ▼                         │                       │
│                   ┌─────────────────┐                │                       │
│                   │  Canary Analysis │                │                       │
│                   │  • Error rate OK?│                │                       │
│                   │  • Latency OK?   │                │                       │
│                   │  • Promote or    │                │                       │
│                   │    Rollback?     │                │                       │
│                   └─────────────────┘                │                       │
│                                                                             │
│   PROMOTE: Increase canary % (5% → 25% → 50% → 100%)                        │
│   ROLLBACK: Route 0% to canary; canary servers drained                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Metrics to Watch

| Metric | Why It Matters |
|--------|----------------|
| **Error rate (5xx)** | Spike = bug or misconfiguration. Usually the first signal. |
| **Latency (p50, p99)** | Regression = performance bug or N+1 query. |
| **CPU / memory** | Resource leak or inefficient code. |
| **Business metrics** | Conversion rate, sign-up success—code can be "correct" but behavior wrong. |
| **Custom metrics** | Cache hit rate, DB query count—domain-specific. |

## Automated Canary Analysis

Tools like **Kayenta** (Netflix/Google) compare canary metrics to baseline and automatically promote or roll back:

- **Pass**: Canary error rate and latency within tolerance → promote.
- **Fail**: Canary worse than baseline → roll back and alert.
- **Manual**: Inconclusive → hold and alert human.

Reduces human toil and speeds up safe rollouts.

## Feature Flags + Canary

**Alternative approach**: Deploy new code to *all* servers, but use a **feature flag** to enable it only for X% of users (or user IDs). No separate canary server pool.

- **Pro**: Simpler infrastructure. One codebase. User-level control.
- **Con**: Bug affects *all* servers (e.g., memory leak) but only X% of users see the feature. May still affect system-wide resources.

**When to use**: User-visible behavior changes, A/B tests. **When not**: Performance changes, infra changes—those need real canary servers.

## Advantages and Disadvantages

| Advantages | Disadvantages |
|------------|---------------|
| Small blast radius (1–5% of users) | More complex routing (per-server or %-based) |
| Gradual confidence building | Need per-pool monitoring |
| Can catch bugs before 100% | Slower rollout than blue-green |
| No double full-infra cost | Automated analysis adds tooling complexity |

## Canary: Gradual Rollout Stages

A typical progression:

| Stage | Traffic % | Duration | Goal |
|-------|-----------|----------|------|
| **Initial** | 1–5% | 15–30 min | Catch catastrophic bugs |
| **Ramp 1** | 10–25% | 30–60 min | Validate under moderate load |
| **Ramp 2** | 50% | 30–60 min | Half of users on new version |
| **Full** | 100% | — | Canary becomes baseline |
| **Cleanup** | — | — | Decommission old version |

Duration depends on risk. High-risk: longer at each stage. Low-risk: faster progression.

## Canary: User Segmentation Strategies

| Strategy | How It Works | Pro | Con |
|----------|--------------|-----|-----|
| **Random %** | Hash user_id or request_id, route X% to canary | Simple, representative | No control over who gets canary |
| **Region-based** | One region gets canary first | Blast radius contained | Region may not be representative |
| **Internal users** | Employees / beta testers first | Safe, easy feedback | Traffic pattern may differ |
| **Sticky canary** | Same user always gets canary (or baseline) | Consistent UX per user | Need session/user affinity |

## L5 vs L6: Canary

| Aspect | L5 | L6 |
|--------|-----|-----|
| **When to use** | "For safer deploys" | "When blast radius matters and we can accept gradual rollout. Use for risky changes. Use feature flags when user-level control is enough." |
| **Metrics** | "Watch error rate" | "Error rate, latency percentiles, resource usage, business metrics. Automated canary analysis for speed and consistency." |
| **Stages** | "We do 5% then 100%" | "1–5% → 25% → 50% → 100%. Duration per stage depends on risk. High risk = longer." |

---

# Part 3: Runbooks and Incident Response (Topic 269)

## What Is a Runbook?

A **runbook** is step-by-step instructions for handling a specific operational scenario. It is written **before** the incident—so when the alert fires at 3 AM, the on-call engineer has a playbook instead of guessing.

## Types of Runbooks

| Type | Purpose | Example |
|------|---------|---------|
| **Diagnostic** | How to investigate | "High latency on Order Service: check DB connections, cache hit rate, downstream calls" |
| **Remediation** | How to fix | "Cache stampede: enable request coalescing, warm cache, or temporarily increase TTL" |
| **Escalation** | Who to call when | "If DB connection pool exhausted: page DBA on-call, ticket #123" |

## Good Runbook Structure

```
1. TRIGGER
   • Which alert or symptom invokes this runbook?
   • Example: "Alert: order-service error rate > 1% for 5 min"

2. QUICK CHECKS (30–60 seconds)
   • Is the monitoring dashboard correct?
   • Recent deploys?
   • External dependency status?

3. COMMON CAUSES & SOLUTIONS
   • Cause A → Do X
   • Cause B → Do Y
   • Cause C → Escalate to Z

4. ESCALATION PATH
   • When to escalate, who to page, how to hand off

5. POST-INCIDENT
   • What to do after mitigation (update runbook, postmortem)
```

## Incident Response Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    INCIDENT RESPONSE LIFECYCLE                               │
│                                                                             │
│   DETECT          TRIAGE         MITIGATE        ROOT CAUSE     FIX         │
│     │                │               │               │            │          │
│     ▼                ▼               ▼               ▼            ▼          │
│  Alert fires    Assess impact   Stop bleeding   Find why it    Deploy fix    │
│  or user        Who affected?   Restore service  happened       or rollback  │
│  report         Severity?       ASAP             (may be       (may be      │
│                 Assign IC       (rollback,       later)         same as      │
│                                 scale up,                            │
│                                 disable feature)                    │
│     │                │               │               │            │          │
│     └────────────────┴───────────────┴───────────────┴────────────┘          │
│                                        │                                      │
│                                        ▼                                      │
│                               POSTMORTEM                                     │
│                               • What happened?                                │
│                               • Why?                                          │
│                               • What will we do to prevent?                    │
│                               • Action items (owner, deadline)                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Severity Levels

| Severity | Definition | Response | Example |
|----------|------------|----------|---------|
| **SEV1** | Customer-facing outage. Core product down. | Page everyone. All-hands. IC. Fix immediately. | Payment down. Login broken. Entire site unreachable. |
| **SEV2** | Degraded service. Some users affected. | On-call team. Fix within hours. May need escalation. | One region slow. Search failing for 10% of queries. |
| **SEV3** | Minor. Workaround exists. | Next business day. Ticket. No immediate page. | Dashboard widget wrong. Non-critical API slow. |
| **SEV4** | Cosmetic or very limited impact. | Backlog. Fix when convenient. | Typo on help page. Minor UI glitch. |

**Upgrading severity**: If SEV2 isn't resolved in N hours, or impact worsens, upgrade to SEV1. Define escalation rules in advance.

## Incident Commander (IC) Role

- **One person** coordinates the response.
- Makes decisions when there's no consensus.
- Communicates status to stakeholders (leadership, support, users).
- Ensures someone is doing diagnostics, someone is mitigating, someone is documenting.
- Does **not** have to be the person fixing—they orchestrate.

## Postmortem: Blameless and Actionable

**Blameless**: Focus on systems and process, not individuals. "The deploy pipeline allowed X" not "Bob broke it."

**Structure**:

1. **Summary**: One paragraph. What happened?
2. **Timeline**: Key events with timestamps.
3. **Root cause**: Why did it happen? (Often multiple contributing factors.)
4. **Impact**: Users affected, duration, revenue/customer impact if known.
5. **Action items**: Specific, with owner and deadline. Prevent recurrence.
6. **Lessons learned**: What would we do differently?

**Action items** must be tracked. Postmortem without follow-through is theater.

## Incident Response Playbook Checklist

| Phase | Checklist |
|-------|-----------|
| **Detect** | Alert configured? Runbook linked to alert? On-call notified? |
| **Triage** | Severity assigned? IC designated? Status page updated? |
| **Mitigate** | Rollback considered? Scaling considered? Feature flag to disable? |
| **Root cause** | Logs/traces reviewed? Correlated with deploys/config? |
| **Fix** | Deploy fix or rollback? Verify mitigation? |
| **Postmortem** | Scheduled within 48 hours? Blameless? Action items with owners? |

## Example Runbook: High Error Rate on Order Service

```
TRIGGER: Alert "order-service-5xx-rate" > 1% for 5 minutes

QUICK CHECKS:
1. Grafana: order-service dashboard - which endpoint? Which error?
2. Deploy history: any deploy in last 2 hours?
3. Dependencies: RDS, Redis, payment-gateway status?

COMMON CAUSES:
| Cause                    | Check                    | Fix                              |
|--------------------------|--------------------------|----------------------------------|
| DB connection pool full  | DB connections metric    | Scale DB pool or add replicas   |
| Downstream timeout       | Trace: which call times out? | Increase timeout or fix downstream |
| Bad deploy               | Compare error rate to deploy time | Rollback                      |
| Redis unavailable        | Redis health              | Failover Redis; check network   |

ESCALATION: If unresolved in 15 min, page tech lead. SEV1: page Incident Commander.
```

This structure ensures the on-call engineer has a path even when tired at 3 AM.

## War Room Best Practices

When multiple people are engaged:

- **One channel** (Slack, Zoom) for coordination.
- **IC owns communication**; others focus on diagnostics/fix.
- **Avoid parallel firefighting**: coordinate. Two people rolling back in different ways = chaos.
- **Document in real time**: timeline, decisions, actions. Feeds postmortem.

## L5 vs L6: Incident Response

| Aspect | L5 | L6 |
|--------|-----|-----|
| **Runbooks** | "We have some docs" | "Runbooks exist for every alert. Structure: trigger, quick checks, causes, escalation. Updated after incidents." |
| **Postmortem** | "We discuss what happened" | "Blameless. Timeline, root cause, impact, action items with owners. Action items tracked to completion." |
| **IC role** | "Whoever is on-call" | "Explicit IC role. Coordinates. Communicates. Doesn't have to fix—orchestrates." |

---

# Part 4: Observability — Logs, Metrics, Traces (Topic 270)

## The Three Pillars

Observability answers: *What is the system doing, and why?* Three pillars, each answering different questions:

| Pillar | Answers | Characteristics |
|--------|---------|-----------------|
| **Logs** | What happened? (Event-level detail) | Text, high volume, expensive at scale |
| **Metrics** | How bad? (Aggregated over time) | Numbers, low cardinality, cheap |
| **Traces** | Where is the bottleneck? (Request flow) | Request-scoped, cross-service |

## Logs

- **What**: Detailed event records. "At 14:32:05, user 123 got NullPointerException at line 42."
- **Use case**: Debugging a specific incident. "What exactly went wrong for request X?"
- **Trade-off**: High volume. Storing and searching logs at scale is expensive. Use sampling for high-throughput paths.
- **Tools**: Elasticsearch/ELK, Loki, Splunk, CloudWatch Logs.

## Metrics

- **What**: Aggregated numbers over time. Request count/sec, p99 latency, error rate.
- **Use case**: Dashboards, alerts, capacity planning. "Is the system healthy?"
- **Trade-off**: Low cardinality. Don't use user_id as a metric dimension—cardinality explosion.
- **Tools**: Prometheus, Grafana, Datadog, CloudWatch Metrics.

## Traces

- **What**: Follow a single request through multiple services. "Request abc → API Gateway (5ms) → Auth (10ms) → Order Service (50ms) → DB (200ms)."
- **Use case**: Finding bottlenecks in microservices. "Which hop is slow?"
- **Tools**: Jaeger, Zipkin, OpenTelemetry.

## When to Use Which

```
"System is slow"
    │
    ▼
Check METRICS: Which metric spiked? (Latency? Error rate? CPU?)
    │
    ▼
Found the service (e.g., Order Service)
    │
    ▼
Check TRACES: Which hop is slow? (DB? Downstream API?)
    │
    ▼
Found the slow call (e.g., DB query taking 2 seconds)
    │
    ▼
Check LOGS: What query? What error? (Request ID = correlation)
```

## ASCII Diagram: Three Pillars and Correlation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    OBSERVABILITY: THREE PILLARS + CORRELATION                 │
│                                                                             │
│   REQUEST (request_id: abc-123)                                             │
│                                                                             │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│   │ API Gateway │───▶│ Auth Svc    │───▶│ Order Svc   │───▶│ Database    │  │
│   │ 5ms         │    │ 10ms        │    │ 50ms        │    │ 200ms       │  │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘  │
│          │                  │                  │                  │          │
│          │  request_id: abc-123 (propagated via header)           │          │
│          │                  │                  │                  │          │
│          ▼                  ▼                  ▼                  ▼          │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                         LOGS (what happened)                          │  │
│   │  [abc-123] API Gateway: received POST /orders                        │  │
│   │  [abc-123] Auth: user 456 authenticated                              │  │
│   │  [abc-123] Order Svc: DB query slow: SELECT * FROM orders WHERE...   │  │
│   │  [abc-123] DB: query took 200ms                                      │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│          │                  │                  │                  │          │
│          ▼                  ▼                  ▼                  ▼          │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                         METRICS (how bad)                             │  │
│   │  order_svc_latency_p99: 500ms  │  order_svc_error_rate: 0.1%         │  │
│   │  db_connection_pool_used: 95% │  request_count: 10,000/min            │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│          │                  │                  │                  │          │
│          ▼                  ▼                  ▼                  ▼          │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                         TRACES (where's the slow part)                │  │
│   │  abc-123: API(5ms) → Auth(10ms) → Order(50ms) → DB(200ms)             │  │
│   │                        ↑___________________________________________  │  │
│   │                        DB is the bottleneck (200ms of 265ms total)   │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   CORRELATION: Same request_id links logs + traces. Full picture.            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Request ID: The Correlation Key

Propagate **Request ID** (or Trace ID) in headers across all services. Every log line and trace span includes it. When debugging, search logs by request_id → see the full path. Traces already do this; ensure logs use the same ID.

**Header names**: `X-Request-ID`, `X-Trace-ID`, or `traceparent` (W3C Trace Context). Consistent naming across services.

## Metrics: Cardinality and Cost

**Cardinality** = number of unique label combinations. High cardinality = expensive.

| Low cardinality (good) | High cardinality (bad) |
|------------------------|-------------------------|
| `method`, `status`, `service` | `user_id`, `request_id`, `timestamp` |
| 10 × 5 × 20 = 1,000 series | 1M users × 1K requests = 1B series |

**Rule**: Never put user_id, request_id, or unbounded values in metric labels. Use logs for that. Metrics are for aggregates.

## Log Sampling at Scale

At 100K RPS, logging every request = 100K log lines/sec. Expensive. Strategies:

- **Sample**: Log 1% of requests. Or log all errors + 0.1% of success.
- **Tiered**: Full logs for canary; sampled for baseline.
- **On-demand**: Log fully only when request_id is in a "debug" set (e.g., specific user, trace_id).

## L5 vs L6: Observability

| Aspect | L5 | L6 |
|--------|-----|-----|
| **Debugging "system slow"** | "Check the logs" | "Metrics first (which metric?). Then traces (which hop?). Then logs for that request_id (what query/error?)." |
| **Log vs metric** | "We have both" | "Logs = event detail, expensive. Metrics = aggregates, cheap. Don't put high-cardinality (user_id) in metrics." |
| **Correlation** | "We search logs" | "Request ID in every service. One ID = full request path across logs and traces." |

---

# Part 5: SLO, SLI, and Error Budget (Topic 271)

## Definitions

| Term | Definition | Example |
|------|------------|---------|
| **SLI** (Service Level Indicator) | The measurement. A metric. | "Percentage of requests that return in under 200ms" |
| **SLO** (Service Level Objective) | The target. A goal. | "99.9% of requests should return in under 200ms" |
| **SLA** (Service Level Agreement) | The legal contract. | "If availability < 99.9% in a month, customer gets 10% credit" |

**SLI** = what we measure. **SLO** = what we aim for. **SLA** = what we promise (and pay for if we miss).

## SLI Examples: What to Measure

Common SLIs by service type:

| SLI Type | Good Count | Bad Count | Formula |
|----------|------------|-----------|---------|
| **Availability** | Successful requests (2xx, 3xx) | Failed (5xx, timeout) | good / (good + bad) |
| **Latency** | Requests under threshold (e.g., 200ms) | Requests over threshold | good / total |
| **Throughput** | Requests served | — | Raw count (for capacity) |
| **Freshness** | Data updated within N seconds | Stale data | good / total |
| **Correctness** | Correct results (hard to measure) | Incorrect results | good / total |

**Availability SLI**: "Percentage of requests that return HTTP 2xx or 3xx (or don't timeout)." Exclude 4xx (client errors) from bad count—they're often user error, not system failure.

**Latency SLI**: "Percentage of requests completing in under 200ms." Often use p50, p99, or threshold-based. Choose threshold that matches user expectation.

## Error Budget

**Error budget** = 100% − SLO = the "permission to fail."

| SLO | Error Budget | Interpretation |
|-----|--------------|----------------|
| 99.9% | 0.1% | 43.2 minutes of downtime per month |
| 99.99% | 0.01% | 4.32 minutes per month |
| 99% | 1% | 7.2 hours per month |

**Formula** (for availability): `downtime = (1 - SLO) × time_period`

- 99.9% over 30 days: 0.001 × 30 × 24 × 60 = **43.2 minutes**

## How to Use Error Budgets

| Error Budget Status | Implication |
|---------------------|-------------|
| **Healthy** (budget remaining) | Ship features. Take calculated risks. Deploy. |
| **Burning** (budget exhausted or near) | Slow down. Focus on reliability. No risky deploys. Fix before adding features. |

**Purpose**: Balances **innovation** (shipping) vs **stability** (reliability). Prevents "we can never deploy" and "we only do reliability" extremes.

## Choosing SLOs

| SLO Too Tight (e.g., 99.99%) | SLO Too Loose (e.g., 99%) |
|------------------------------|----------------------------|
| Team spends all time on reliability | Users unhappy. Frequent outages. |
| Can't ship features. Paralyzed. | May be acceptable for internal tools. |
| Match to user expectations | Match to user expectations |

**Guideline**: Start with user expectations. What does "good enough" mean? 99.9% is common for customer-facing. 99.99% for payment, auth. 99% for internal dashboards.

## Error Budget Math: Quick Reference

| SLO | Error Budget | Per Month (30 days) | Per Year |
|-----|--------------|---------------------|----------|
| 99% | 1% | 7.2 hours | 3.65 days |
| 99.9% | 0.1% | 43.2 min | 8.76 hours |
| 99.95% | 0.05% | 21.6 min | 4.38 hours |
| 99.99% | 0.01% | 4.32 min | 52.6 min |
| 99.999% | 0.001% | 25.9 sec | 5.26 min |

**Formula**: `downtime_minutes = (1 - SLO_decimal) × period_minutes`

Example: 99.9% over 30 days = 0.001 × (30 × 24 × 60) = 43.2 minutes.

## Error Budget Policy Examples

| Budget Status | Policy |
|---------------|--------|
| **> 50% remaining** | Normal velocity. Deploy. Feature work. |
| **< 50% remaining** | Reduce deploy frequency. Focus on reliability. |
| **Exhausted** | Freeze. No new features. Only reliability work until budget recovers. |
| **Recovered** | Resume normal. Postmortem: what burned it? |

Some orgs tie budget to release gates: "Can't release if budget < 10%."

## Multiple SLOs per Service

A service often has several SLOs:

| SLO Type | Example |
|----------|---------|
| **Availability** | 99.9% of requests succeed (non-5xx) |
| **Latency** | p99 < 500ms |
| **Error rate** | < 0.1% 5xx |

Each has its own error budget. Burning one (e.g., latency) may require different actions than burning another (availability).

## Composite SLOs

If your service depends on 3 backends, each with 99.9% availability, your **theoretical max** availability is:

`0.999 × 0.999 × 0.999 ≈ 99.7%`

Failures in any backend can cause your service to fail. Composite SLOs help set realistic targets and error budgets.

## L5 vs L6: SLO and Error Budget

| Aspect | L5 | L6 |
|--------|-----|-----|
| **SLO** | "We want 99.9%" | "SLO = target. Error budget = permission to fail. When healthy → ship. When burning → focus on reliability." |
| **Choosing SLO** | "As high as possible" | "Match user expectations. 99.99% costs more than 99.9%. Too tight = paralyzed. Too loose = unhappy users." |
| **Composite** | "Each service has SLO" | "Service with 3 backends at 99.9% each → max ~99.7%. Set targets accordingly." |

---

# Part 6: Capacity Planning (Topic 272)

## Steps

1. **Measure** current usage (CPU, memory, disk, network, DB connections, queue depth).
2. **Model** growth (historical trends + known events: Black Friday, product launch).
3. **Identify** when you hit limits (which component first?).
4. **Scale** before hitting limits. Don't wait for 100%.

## Key Metrics

| Metric | What to Watch |
|--------|---------------|
| **CPU utilization** | Sustained > 70–80% = plan to scale |
| **Memory usage** | OOM risk when approaching limit |
| **Disk I/O** | Throughput and IOPS limits |
| **Network bandwidth** | Saturation under load |
| **DB connections** | Pool exhaustion |
| **Queue depth** | Consumer lag; backpressure |

## Scaling Triggers

**Don't wait until 100%.** Scale at **70–80%** utilization. Headroom absorbs:

- Traffic spikes
- Failure of a replica (traffic shifts to survivors)
- Deployments (temporary load)

## Growth Modeling

- **Historical**: "Traffic grew 10%/month for 6 months."
- **Events**: Black Friday 2× normal. Product launch +50% for 2 weeks.
- **Formula**: `capacity_needed = current × (1 + growth_rate)^months × peak_multiplier`

**Example**: Current peak = 1,000 RPS. Growth = 15%/month. Need capacity for 6 months. Black Friday = 3× normal.

`capacity = 1000 × (1.15)^6 × 3 ≈ 1000 × 2.31 × 3 ≈ 6,930 RPS`

Plan for ~7K RPS in 6 months.

## Capacity Planning: Which Component First?

Different components hit limits at different scales:

| Component | Typical Limit | Symptom | Mitigation |
|-----------|---------------|---------|------------|
| **Application CPU** | 70–80% sustained | Slow responses | Horizontal scaling, optimize code |
| **Memory** | OOM | Crashes, restarts | Increase heap, fix leaks, scale |
| **DB connections** | Pool size | "Too many connections" | Connection pooling, read replicas |
| **DB disk I/O** | IOPS limit | Slow queries | SSD, read replicas, optimize queries |
| **Network** | Bandwidth | Packet loss, latency | Bigger NICs, more nodes |
| **Message queue** | Consumer lag | Delayed processing | More consumers, partition |

Staff question: "If we 2× traffic tomorrow, what breaks first?" That's the component to focus on.

## Load Testing

Simulate expected peak load **before** it happens. Tools: k6, Locust, Gatling.

- Run at 2× expected peak.
- Identify bottlenecks (which component fails first?).
- Tune or scale that component.

## Staff-Level Capacity Planning

Not just "add more servers." Staff asks:

- **Which component** hits its limit first?
- **What is the cheapest/safest mitigation?** (Scale? Optimize? Cache? Queue?)
- **When** do we need it? (Lead time for hardware, reserved capacity.)

## Capacity Planning Checklist

| Step | Checklist |
|------|-----------|
| **Measure** | Dashboards for CPU, memory, disk, network, DB, queues? |
| **Baseline** | Current peak load documented? |
| **Model** | Growth rate and known events documented? |
| **Bottleneck** | Which component limits scale identified? |
| **Trigger** | Scale at 70–80%, not 100%? |
| **Load test** | Peak simulated before it happens? |
| **Lead time** | Enough time to procure/scale before need? |

## L5 vs L6: Capacity Planning

| Aspect | L5 | L6 |
|--------|-----|-----|
| **Approach** | "Add servers when we're full" | "Measure → model → identify bottleneck → scale at 70–80%. Load test before peak." |
| **Bottleneck** | "We need more compute" | "Which component fails first? DB? Network? Cache? Sizing that component is the fix." |

---

# Part 7: Cost Modeling (Topic 273)

## Major Cloud Cost Drivers

| Driver | Examples |
|--------|----------|
| **Compute** | EC2, VMs, Lambda invocations |
| **Storage** | S3, EBS, managed DB storage |
| **Network** | Data transfer (especially cross-region) |
| **Managed services** | RDS, ElastiCache, managed Kafka |

## Hidden Costs

| Cost | Often Overlooked |
|------|------------------|
| **Cross-region data transfer** | $0.02/GB+ (can exceed compute cost) |
| **NAT Gateway** | Per-hour + per-GB |
| **CloudWatch / monitoring** | Logs, metrics, alarms |
| **DNS queries** | At scale, Route 53 costs add up |
| **API calls** | S3 PUT/GET, DynamoDB read/write units |

## Cost Optimization Strategies

| Strategy | Example |
|----------|---------|
| **Right-sizing** | Smaller instance types. Don't over-provision. |
| **Reserved instances / Savings Plans** | Commit for 1–3 years; 30–70% discount |
| **Spot instances** | For fault-tolerant, interruptible workloads |
| **Auto-scaling** | Scale down when idle. Don't run 100 servers 24/7 for 9–5 load. |
| **Data tiering** | Hot (SSD) / warm (standard) / cold (Glacier). Move old data. |

## Cost Allocation and Chargebacks

For multi-team orgs:

- **Chargeback**: Each team pays for its cloud usage. Encourages optimization.
- **Showback**: Teams see their cost but don't pay directly. Visibility without penalty.
- **Shared vs dedicated**: Shared infra (DB, cache) vs team-dedicated (compute). Allocation rules matter.

## Unit Economics: Cost per Request

Understand the cost to serve one request:

```
Cost per request = (Compute + Storage + Network + Managed services) / Request count
```

Useful for: "If we grow 10×, what happens to our bill?" If linear, you have a problem. Aim for sub-linear (caching, batching, efficiency).

## The Staff-Level Cost Conversation

> "We can achieve 99.99% availability for $500K/month, or 99.9% for $50K/month. The difference is 43 minutes vs 8.7 hours of downtime per year. Is the extra $450K/month worth 8 hours less downtime?"

**Staff** connects cost to business impact. Presents options. Lets the business decide.

## Cost vs Reliability Trade-off Table

| Availability | Downtime/Year | Typical Cost | When to Choose |
|--------------|---------------|--------------|----------------|
| 99% | 3.65 days | Lower | Internal tools, non-critical |
| 99.9% | 8.76 hours | Medium | Most customer-facing |
| 99.99% | 52.6 minutes | High | Payment, auth, critical path |
| 99.999% | 5.26 minutes | Very high | Regulated, life-safety |

## L5 vs L6: Cost Modeling

| Aspect | L5 | L6 |
|--------|-----|-----|
| **Cost** | "We optimize costs" | "Know the drivers. Hidden costs (cross-region, NAT). Present cost vs reliability trade-offs to business." |
| **Reliability cost** | "We need 99.99%" | "99.99% costs more than 99.9%. Is the incremental cost worth the incremental uptime? Business decides." |

---

# Part 8: Rollback Strategies (Topic 275)

## When to Roll Back

| Condition | Action |
|-----------|--------|
| Error rate spiked | Roll back |
| Critical functionality broken | Roll back |
| Data corruption risk | Roll back immediately |
| SLO burning (error budget exhausted) | Roll back |
| Security vulnerability introduced | Roll back |

## When to Fix Forward

| Condition | Action |
|-----------|--------|
| Issue is minor | Fix forward may be faster |
| Rollback is risky (e.g., schema migration) | Fix forward |
| Fix is quick (config change, hotfix) | Fix forward |
| Rollback would cause more damage | Fix forward |

## Rollback Mechanisms

| Mechanism | How It Works | Use Case |
|-----------|--------------|----------|
| **Blue-green** | Switch traffic back to Blue | Instant. Best when you have blue-green. |
| **Container / previous image** | Deploy previous image tag | Kubernetes, ECS. Revert to last known good. |
| **Feature flag** | Toggle feature off | No redeploy. Instant. Best for user-visible features. |
| **Configuration revert** | Revert config to previous | Config change caused issue. |
| **Git revert + deploy** | Revert commit, redeploy | When no simpler mechanism. Slower. |

## The Database Rollback Problem

**The hard part**: Schema migrations are **forward-only**. If you deploy:

1. New code that uses new column
2. New schema with new column

Rolling back code is easy—deploy previous code. Rolling back schema (DROP COLUMN) is **dangerous**—old code expects the column. If you already dropped it, rollback breaks.

**Strategy**: **Always** make schema migrations backward-compatible.

```
SAFE SEQUENCE:
1. Add column (nullable or default)     → Old and new code both work
2. Deploy new code that uses column     → New code uses it; old ignores
3. Backfill if needed
4. (Later) Remove old column            → Only when no code reads it
```

**Never**: Drop a column in the same deploy as code that stops using it.

## ASCII Diagram: Rollback Decision Tree

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ROLLBACK DECISION TREE                                    │
│                                                                             │
│                         Incident detected                                    │
│                                │                                             │
│                                ▼                                             │
│                    ┌───────────────────────┐                                │
│                    │ Data corruption risk?  │                                │
│                    │ Security vuln?         │                                │
│                    └───────────┬───────────┘                                │
│                           Yes  │  No                                         │
│                    ┌───────────┴───────────┐                                │
│                    ▼                       ▼                                │
│             ROLL BACK              ┌───────────────────────┐                 │
│             Immediately            │ Critical functionality │                │
│                                    │ broken? SLO burning?   │                │
│                                    └───────────┬───────────┘                 │
│                                           Yes  │  No                         │
│                                    ┌──────────┴──────────┐                   │
│                                    ▼                     ▼                   │
│                             ROLL BACK            ┌───────────────────────┐   │
│                             (use fastest         │ Rollback risky?       │   │
│                              mechanism)          │ (schema migration)     │   │
│                                                   └───────────┬───────────┘   │
│                                                          Yes  │  No          │
│                                                   ┌──────────┴──────────┐    │
│                                                   ▼                     ▼    │
│                                            FIX FORWARD            ROLL BACK  │
│                                            (don't roll back      or FIX      │
│                                             schema)              FORWARD    │
│                                                                   (pick      │
│                                                                   fastest)  │
│                                                                             │
│   MECHANISMS (fastest first):                                                │
│   1. Feature flag off                                                        │
│   2. Blue-green traffic switch                                               │
│   3. Config revert                                                           │
│   4. Previous container image                                                │
│   5. Git revert + redeploy                                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Rollback Checklist

| Step | Checklist |
|------|-----------|
| **Assess** | Roll back or fix forward? Use decision tree. |
| **Mechanism** | Fastest available? Feature flag > blue-green > config > image > git revert. |
| **Schema** | Did this deploy include schema change? If yes, rollback is tricky. Prefer fix forward for schema. |
| **Verify** | After rollback, confirm error rate/latency recovered. |
| **Postmortem** | Schedule. Why did we need to roll back? How do we prevent? |

## Rolling Deployment: When to Use Instead of Blue-Green or Canary

**Rolling deployment** updates servers in batches: take 10% offline, deploy new version, bring back; repeat for next 10%. No double infra. Simpler than canary. But:

- **Rollback** = redeploy previous version across all batches. Slower than blue-green.
- **Blast radius** = one batch at a time. If new version has a bug, that batch's users see it before you complete the rollout.
- **Use when**: Low-risk changes, high deploy frequency, cost-sensitive. Many teams use rolling for 90% of deploys and blue-green/canary for high-risk ones.

## L5 vs L6: Rollback

| Aspect | L5 | L6 |
|--------|-----|-----|
| **Decision** | "If it breaks, roll back" | "Roll back when: error spike, critical break, data corruption, SLO burning. Fix forward when: rollback risky (schema), fix is quick." |
| **Schema** | "We run migrations" | "Schema migrations backward-compatible. Add → use → remove. Never drop column in same deploy as code change." |
| **Mechanism** | "Redeploy previous" | "Fastest first: feature flag, blue-green switch, config revert, previous image, git revert." |

---

# Appendix: Incident Response Playbook Template

```
## [ALERT NAME] Runbook

### Trigger
- Alert: [alert name]
- Symptom: [what users/stakeholders might see]

### Quick Checks (30–60 sec)
1. [ ] Check status page / dependency status
2. [ ] Recent deploys in last 2 hours?
3. [ ] Any config changes?

### Common Causes & Solutions

| Cause | Solution |
|-------|----------|
| [Cause 1] | [Steps to fix] |
| [Cause 2] | [Steps to fix] |
| [Cause 3] | Escalate to [team/person] |

### Escalation
- If not resolved in 15 min: page [role]
- If SEV1: page [Incident Commander], create [status update channel]

### Post-Incident
- [ ] Update this runbook if new learning
- [ ] Schedule postmortem within 48 hours
- [ ] Create action items with owners
```

---

# Appendix: Postmortem Template

```
## Postmortem: [Incident Title]
Date: [YYYY-MM-DD]
Authors: [names]

### Summary
[1–2 paragraphs. What happened? Impact?]

### Timeline
| Time (UTC) | Event |
|------------|-------|
| HH:MM | [Event] |
| HH:MM | [Event] |
| ... | ... |

### Root Cause
[Why did it happen? Contributing factors.]

### Impact
- Users affected: [estimate]
- Duration: [X minutes/hours]
- [Revenue/customer impact if known]

### Action Items
| Action | Owner | Deadline |
|--------|-------|----------|
| [Action 1] | [Name] | [Date] |
| [Action 2] | [Name] | [Date] |
| ... | ... | ... |

### Lessons Learned
[What would we do differently?]
```

---

# Summary: Deployment & Ops at Staff Level

| Topic | Key Takeaway |
|-------|--------------|
| **Blue-green** | Instant rollback, double cost. Schema must be backward-compatible. |
| **Canary** | Small blast radius. Metrics: error rate, latency, resources. Automated analysis speeds rollout. |
| **Runbooks** | Written before incidents. Trigger, quick checks, causes, escalation. |
| **Incident response** | Detect → Triage → Mitigate → Root cause → Fix → Postmortem. IC coordinates. Blameless postmortems. |
| **Observability** | Logs (what?), Metrics (how bad?), Traces (where?). Request ID correlates. |
| **SLO / Error budget** | SLO = target. Error budget = permission to fail. Healthy budget → ship. Burning → fix reliability. |
| **Capacity planning** | Measure → model → scale at 70–80%. Load test before peak. Know the bottleneck. |
| **Cost modeling** | Know drivers. Hidden costs. Cost vs reliability: "Is $X for 99.99% worth it?" |
| **Rollback** | Roll back when: error spike, critical break, data risk, SLO burning. Fix forward when: schema involved, fix quick. Schema: always backward-compatible. |

**The Staff mindset**: Deployment, observability, and reliability are design decisions. They affect velocity, cost, and user trust. Choose strategies that match risk, cost, and business goals—and document the trade-offs.

---

# Appendix: Deployment Strategy Comparison

| Strategy | Rollback Speed | Blast Radius | Infra Cost | Complexity | Best For |
|----------|----------------|--------------|------------|------------|----------|
| **Blue-green** | Instant | 0% (all or nothing) | 2× during deploy | Low | High-risk, need instant rollback |
| **Canary** | Minutes | 1–5% initially | 1× (+ small canary pool) | Medium | Gradual rollout, reduce risk |
| **Rolling** | Slow (redeploy) | Per-batch | 1× | Low | Low-risk, stateless |
| **Feature flag** | Instant | User % | 1× | Low (if already have flags) | A/B tests, user-level control |
| **Recreate** | Slow | 100% (downtime) | 1× | Very low | Dev/staging only |

---

# Appendix: Observability Tools Quick Reference

| Pillar | Open Source | Managed / Commercial |
|--------|-------------|----------------------|
| **Metrics** | Prometheus, Grafana | Datadog, New Relic, CloudWatch |
| **Logs** | ELK, Loki, Fluentd | Datadog, Splunk, CloudWatch Logs |
| **Traces** | Jaeger, Zipkin, OpenTelemetry | Datadog, Honeycomb, X-Ray |
| **Unified** | Grafana (LGTM stack) | Datadog, New Relic |

**OpenTelemetry**: Vendor-neutral standard for traces, metrics, logs. Instrument once, export to multiple backends.

---

# Appendix: Deployment Strategy Selection Guide

Use this when deciding which strategy to use:

```
                    Is instant rollback critical?
                              │
                    Yes ──────┼────── No
                    │                  │
                    ▼                  ▼
            Can you afford     Is blast radius a concern?
            double infra?      (risky change?)
                    │                  │
            Yes ────┼─── No     Yes ───┼─── No
            │           │            │       │
            ▼           ▼            ▼       ▼
        Blue-Green   Canary      Canary   Rolling
        or           (small %)   or       deploy
        Canary                   Feature
                                 flag
```

**Rolling deploy**: Update servers in batches (e.g., 10% at a time). Simpler than canary, but rollback requires redeploying previous version—slower. Good for low-risk, frequent deploys.

**When to combine strategies**: Blue-green for infra switch + feature flag for code path. Deploy both versions to Green; flag controls which code runs. Maximum flexibility.

---

# Appendix: Deployment Pre-Flight Checklist

Before any production deploy:

| Category | Checklist |
|----------|-----------|
| **Code** | Tests passing? Linting clean? No known critical bugs? |
| **Config** | Feature flags set correctly? Environment variables correct? |
| **Schema** | Migration backward-compatible? Tested on staging? |
| **Rollback** | Rollback tested? Previous image/version available? Runbook updated? |
| **Monitoring** | Dashboards open? Alerts configured? Canary metrics (if canary) ready? |
| **Communications** | Deploy window communicated? On-call aware? Status page ready if needed? |
| **Risk** | High-risk? Use canary or blue-green. Low-risk? Rolling may suffice. |

**Staff addition**: "What's the rollback path if this breaks in production?" If you can't answer in 30 seconds, don't deploy.

---

# Appendix: Reliability Engineering — The Big Picture

```
                    RELIABILITY ENGINEERING STACK
                    (What Staff engineers think about)

    ┌─────────────────────────────────────────────────────────────┐
    │  PREVENT      │  DETECT        │  RESPOND      │  IMPROVE   │
    ├───────────────┼───────────────┼───────────────┼─────────────┤
    │  • Deploy     │  • Observability│  • Runbooks   │  • Postmortem│
    │    strategies │  • SLO/SLI/   │  • Incident    │  • Action   │
    │  • Schema     │    alerts      │    response    │    items   │
    │    discipline │  • Dashboards  │  • Rollback   │  • Error   │
    │  • Capacity   │  • Traces     │    decision    │    budget  │
    │    planning   │  • Logs       │    tree        │    policy  │
    │  • Cost vs    │               │               │            │
    │    reliability│               │               │            │
    └───────────────┴───────────────┴───────────────┴─────────────┘
```

**Prevent**: Deployment strategy, schema migrations, capacity planning, cost-reliability trade-offs.
**Detect**: Logs, metrics, traces, SLO-based alerts.
**Respond**: Runbooks, incident lifecycle, rollback decision tree.
**Improve**: Blameless postmortems, action items, error budget policy.

---

# Appendix: Real-World Deployment Scenarios

## Scenario 1: High-Risk Payment Service Change

**Context**: Upgrading payment gateway integration. Failure = money at risk.

**Strategy**: Blue-green. Deploy new integration to Green. Run shadow traffic (duplicate requests to both, compare responses). Validate in production. Switch 100% to Green. Keep Blue warm for 24 hours. If any anomaly, switch back.

**Schema**: Payment service is stateless; no DB migration. Pure code change.

## Scenario 2: New Recommendation Algorithm

**Context**: A/B testing new algo. Want gradual rollout. User experience may vary.

**Strategy**: Feature flag + canary. Deploy code to all servers with flag OFF. Enable for 5% of users (by user_id hash). Monitor: click-through rate, conversion, latency. Ramp to 25%, 50%, 100%. Rollback = flag OFF (no redeploy).

## Scenario 3: Database Schema Migration (Add Index)

**Context**: Adding index to improve query performance. Index creation can lock table or cause load.

**Strategy**: Expand-contract. (1) Add index with `CREATE INDEX CONCURRENTLY` (PostgreSQL) to avoid lock. (2) Deploy code that uses new index. (3) No column drop—index addition is usually safe to roll back (drop index) if needed. Test index creation on staging with production-sized data first.

## Scenario 4: Microservice with 50 Dependencies

**Context**: Order service calls 50 downstream services. Deploy could break any integration.

**Strategy**: Canary. 1% traffic to canary. Automated canary analysis (Kayenta or similar) compares error rate, latency. If canary worse than baseline, auto-rollback. Manual ramp to 100% only after 1% stage passes for 30 minutes. Runbooks for "canary failed" and "downstream timeout" ready.

---

# Appendix: SLO-Based Alerting

**Principle**: Alert on SLO burn rate, not raw metrics. "Error rate is 1%" is noisy. "We're burning error budget 10× faster than we can afford" is actionable.

**Burn rate**: How fast are we consuming error budget?

- **Fast burn**: 1% of monthly budget in 1 hour = page immediately.
- **Slow burn**: 10% of monthly budget in 6 hours = alert, investigate.

**Multi-window, multi-burn-rate alerts** (Google SRE book pattern):

- Alert if error budget burn rate over 14.4× (would exhaust budget in 2 hours) for 2 minutes.
- Alert if burn rate over 1× (on track to exhaust) for 1 hour.

**Action**: Fast burn → page. Slow burn → ticket, fix within hours. Prevents "alert fatigue" from threshold-based alerts that fire too often.

---

# Appendix: Staff-Level Interview Talking Points

When discussing deployment and ops in an interview:

1. **"How would you deploy a breaking API change?"** — Expand-contract: v2 endpoint alongside v1. Migrate clients. Deprecate v1. Never big-bang.

2. **"How do you handle database migrations?"** — Backward-compatible. Add column first. Deploy code. Remove old column later. Never drop in same deploy as code change.

3. **"How do you balance shipping features vs reliability?"** — Error budgets. Healthy budget → ship. Burning → focus on reliability. SLOs set the target; budget sets the pace.

4. **"How would you debug a slow system?"** — Metrics first (which metric spiked?). Traces next (which hop?). Logs last (request_id for that trace). Correlation is key.

5. **"How do you decide when to roll back vs fix forward?"** — Roll back when: error spike, critical break, data risk, SLO burning. Fix forward when: schema involved, fix is quick, rollback causes more damage.

---

# Appendix: Operational Readiness Checklist (Staff Perspective)

Before a system is "production-ready" from an ops perspective:

| Area | Checklist |
|------|-----------|
| **Deployment** | Strategy chosen (blue-green/canary/rolling). Rollback tested. Schema migrations backward-compatible. |
| **Observability** | Request ID propagated. Logs, metrics, traces instrumented. Dashboards for key SLIs. |
| **Alerting** | SLO-based or threshold-based alerts. Runbooks linked to alerts. On-call rotation defined. |
| **Incident response** | Runbooks for top 5 failure modes. Postmortem process. Severity definitions. IC role clear. |
| **SLO/Error budget** | SLIs defined. SLOs set. Error budget policy (when to slow down). |
| **Capacity** | Baseline documented. Growth model. Scaling triggers. Load test before peak. |
| **Cost** | Major cost drivers understood. Cost vs reliability trade-off discussed with business. |

**Staff question**: "If this system has a SEV1 at 3 AM, do we have everything we need to detect, diagnose, and fix it?" If not, it's not ready.

---

# Appendix: Golden Signals and RED/USE Methodologies

## Golden Signals (Google SRE)

Four signals that broadly indicate system health:

| Signal | Meaning | Example |
|--------|---------|---------|
| **Latency** | Time to serve requests | p50, p99, p999 |
| **Traffic** | Demand on the system | Requests/sec, QPS |
| **Errors** | Rate of failed requests | 5xx rate, timeout rate |
| **Saturation** | How "full" the system is | CPU %, memory %, queue depth |

**Use**: If you can only have four dashboards, these are them. Most incidents manifest in one or more of these.

## RED Method (Request-Driven Services)

For services that handle requests (APIs, web servers):

| Metric | What to Measure |
|--------|-----------------|
| **Rate** | Requests per second |
| **Errors** | Failed requests per second |
| **Duration** | Latency distribution (p50, p95, p99) |

## USE Method (Resource-Focused)

For infrastructure (CPU, disk, network):

| Metric | What to Measure |
|--------|-----------------|
| **Utilization** | % of resource busy (e.g., CPU 70%) |
| **Saturation** | Degree of queuing (e.g., run queue length) |
| **Errors** | Error counts (e.g., disk read errors) |

**Staff application**: When capacity planning, USE helps identify which resource is the bottleneck. When debugging latency, RED plus traces narrows the fault domain.

---

# Appendix: Topic 268 — Feature Flags and Progressive Delivery

**Topic 268** extends deployment strategies with **progressive delivery**: controlling rollout at the level of users, not just servers. Key concepts:

| Concept | Purpose |
|---------|---------|
| **Feature flag** | Toggle feature on/off without deploy. Per-environment, per-user, or percentage. |
| **A/B testing** | Route different user segments to different code paths. Measure which performs better. |
| **Progressive delivery** | Gradually expose feature: internal → beta → 5% → 25% → 100%. Same deploy, different exposure. |

**Feature flag services**: LaunchDarkly, Split, Unleash, or in-house (DB + config service). Requirements: low latency (milliseconds), high availability (flags must work when rest of system is degraded).

**Staff consideration**: Feature flags add complexity—flag debt. Old flags must be removed when features are fully rolled out. Otherwise: hundreds of flags, unclear which are active, risk of misconfiguration. Define flag lifecycle: create → use → cleanup within 30–90 days.

---

# Appendix: Further Reading and References

| Topic | Reference |
|-------|-----------|
| **SRE / SLO / Error Budget** | *Site Reliability Engineering* (O'Reilly), *The Site Reliability Workbook* — Google SRE team |
| **Incident response** | *Incident Management for Operations* (O'Reilly), PagerDuty Incident Response Guide |
| **Deployment** | *Continuous Delivery* (Humble & Farley), *Release It!* (Nygard) |
| **Observability** | *Distributed Systems Observability* (O'Reilly), OpenTelemetry docs |
| **Capacity planning** | *Designing Data-Intensive Applications* (Kleppmann) — scaling chapters |

---

# Appendix: Common Operational Pitfalls

| Pitfall | Why It's Bad | Fix |
|---------|--------------|-----|
| **No runbook for alerts** | On-call guesses at 3 AM. Slow resolution. | Write runbook before enabling alert. Link runbook to alert. |
| **Dropping columns in same deploy** | Rollback breaks—old code expects column. | Add column → deploy → remove column in separate deploy. |
| **Scaling at 100% utilization** | No headroom for spikes. Cascading failures. | Scale at 70–80%. Leave buffer. |
| **Alerting on raw thresholds only** | Alert fatigue. Miss SLO burn. | Add SLO-based burn-rate alerts. Reduce noise. |
| **SLO too tight (99.99%)** | Team paralyzed. Can't ship. | Match SLO to user expectations. 99.9% is often enough. |
| **No request ID propagation** | Can't correlate logs across services. Debugging is guesswork. | Add X-Request-ID header. Propagate everywhere. Log it. |
| **Feature flags never cleaned up** | Hundreds of flags. Unclear what's active. | Define lifecycle. Remove flag within 30–90 days of full rollout. |

**Staff-level takeaway**: These pitfalls are symptoms of treating ops as an afterthought. When deployment, observability, and reliability are designed in from the start—with runbooks, SLOs, and rollback paths—teams ship faster and sleep better. The upfront investment pays off in reduced incidents and faster recovery.

---

# Appendix: Key Terms Glossary

| Term | Definition |
|------|-------------|
| **Blue-green** | Two identical prod envs; switch traffic between them for zero-downtime deploy and instant rollback. |
| **Canary** | Deploy to small % of traffic; monitor; promote or roll back. |
| **Error budget** | 100% − SLO. Permission to fail. When exhausted, focus on reliability. |
| **Expand-contract** | Schema migration pattern: add → use → remove. Backward-compatible. |
| **Incident Commander (IC)** | One person who coordinates incident response. Orchestrates; doesn't have to fix. |
| **Postmortem** | Blameless review after incident. Timeline, root cause, action items. |
| **Request ID** | Unique ID per request, propagated across services. Correlates logs and traces. |
| **Runbook** | Step-by-step instructions for handling a specific alert or scenario. Written before the incident. |
| **SLI** | Service Level Indicator. The measurement (e.g., % of requests < 200ms). |
| **SLO** | Service Level Objective. The target (e.g., 99.9% of requests < 200ms). |
| **SLA** | Service Level Agreement. Legal contract with customers. Financial penalties for missing SLO. |
