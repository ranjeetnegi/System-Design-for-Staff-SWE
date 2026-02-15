# Runbooks and Incident Response

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A fire in a building. Without a plan: panic. Chaos. People running in all directions. Blocked exits. Someone pulls the alarm but nobody knows where to go. With a fire drill and evacuation plan: everyone knows which exit. Who calls 911. Who does the headcount. Where to assemble. LIVES saved by preparation. Runbooks are the evacuation plan for software incidents. Step-by-step instructions written BEFORE the fire. When the pager goes off at 3 AM, you're not guessing. You're following the plan.

---

## The Story

Something breaks. The API is slow. The database is down. Payments are failing. It's 3 AM. You're on-call. Your heart races. Your brain is foggy. What do you do first? Second? Third? Without a plan, you waste precious minutes. Maybe hours. With a runbook, you have a checklist. Step 1: Check the database. Step 2: Check replication lag. Step 3: If master is dead, failover to replica. Step 4: Notify the team. The runbook doesn't replace thinking. It guides you when thinking is hard. When stress is high. When every minute matters.

Incident response is the bigger picture. Detect the problem. Triage—how bad is it? Mitigate—stop the bleeding. Root cause—why did it happen? Fix—permanent solution. Postmortem—what do we learn? Runbooks live in the mitigate phase. They're the "how do we stop this right now" playbook.

---

## Another Way to See It

A pilot's checklist. Before takeoff, they don't wing it. They follow a list. Flaps. Fuel. Instruments. Each item checked. When something goes wrong mid-flight, they have another checklist. Engine failure. Loss of cabin pressure. These checklists are runbooks. Written by experts. Tested in simulators. Used when there's no time to improvise. Software operations are the same. Prepare when calm. Execute when stressed.

---

## Connecting to Software

**Runbook:** A document with step-by-step instructions for a specific scenario. "Database is down" → Step 1: SSH to primary, check process. Step 2: Check disk space, memory. Step 3: Check replication status. Step 4: If primary is unrecoverable, run failover script. Step 5: Update DNS/config. Step 6: Notify team in Slack. Step 7: Create incident channel. Each step is concrete. Copy-pasteable commands. Links to dashboards. Contact info. The goal: a new engineer can follow it. You don't want "figure it out" at 3 AM.

**Incident response flow:** Detect (monitoring, alerting) → Triage (severity: SEV1, SEV2, SEV3) → Mitigate (runbooks, rollback, scale up) → Root cause (why?) → Fix (deploy fix, restore service) → Postmortem (what happened, what we'll do differently). Each phase has owners. Incident commander. Communications lead. Technical lead. Structure reduces chaos.

**Severity levels:** SEV1—customer-facing outage. All hands. Page everyone. Fix now. SEV2—degraded service. On-call team. Fix within hours. SEV3—minor issue. Next business day. Document and plan. Severity drives who responds and how fast. Get the severity right early—it shapes the whole response.

---

## Let's Walk Through the Diagram

```
INCIDENT RESPONSE FLOW:

  Alert fires
       |
       v
  DETECT ──► Is it real? Or false positive?
       |
       v
  TRIAGE ──► SEV1? SEV2? SEV3?
       |         |
       |         v
       |    Assign responders, create channel
       |
       v
  MITIGATE ──► Follow RUNBOOK
       |      - Check X
       |      - Run command Y
       |      - Failover if Z
       |
       v
  ROOT CAUSE ──► Why did it happen?
       |
       v
  FIX ──► Deploy, restore, clean up
       |
       v
  POSTMORTEM ──► Blameless. What did we learn?
```

The runbook sits in MITIGATE. It's the tactical response. The rest is strategic—understanding, fixing, learning.

---

## Real-World Examples (2-3)

**Google's SRE book** defines runbooks as a core practice. They have runbooks for every alert. Every "something might be wrong" has a "here's what to do." Engineers practice in game days. Simulated outages. Follow the runbook. Update it when it's wrong. Living documents.

**PagerDuty** (the alerting tool) has runbooks built in. Alert fires → runbook opens. Step by step. Log each action. Handoff to next person with context. The tool and the process work together.

**Netflix's Chaos Engineering**—they break things on purpose. Runbooks get tested. If the runbook is wrong, they find out in a controlled chaos exercise, not during a real outage. Preparation under pressure.

---

## Let's Think Together

**"3 AM. PagerDuty alert: 'API latency 10x normal.' You're on-call. What are your first 3 actions?"**

(1) Acknowledge the alert. Claim ownership. Don't let it bounce. (2) Check if it's real. Look at the dashboard. Is traffic actually up? Is latency actually high? Rule out false positives—deploy, config change, monitoring bug. (3) Open the runbook for "high latency" or "API degradation." Follow the steps. Usually: check dependency health (DB, cache, downstream services), check error rates, check recent deploys. If a deploy went out 10 minutes ago, rollback might be step 1. The runbook should say. The key: don't panic. Follow the plan. Escalate if the runbook doesn't cover it. But start with the plan.

---

## What Could Go Wrong? (Mini Disaster Story)

A database failover runbook said "Run script X." Nobody had run it in a year. The script was written for an old database version. It failed. The runbook didn't have a Plan B. The on-call engineer spent an hour debugging the script instead of failing over. Customers were down. Lesson: runbooks rot. They must be tested. Regularly. Do a failover drill. Run the scripts. Update the runbook when things change. A runbook that hasn't been verified in months is a trap. Test. Test. Test.

---

## Surprising Truth / Fun Fact

The term "runbook" comes from the early days of mainframe operations. Operators had literal books—paper—that told them what to do for each type of failure. They "ran" the book. Today it's mostly digital. But the idea is the same: documented procedures for when things go wrong. Some companies still print critical runbooks and keep them in the office. When the network is down and you can't access the wiki, paper works.

---

## Quick Recap (5 bullets)

- **Runbook** = step-by-step instructions for a specific incident; written before the fire.
- **Incident response** = Detect → Triage → Mitigate (runbooks) → Root cause → Fix → Postmortem.
- **Severity** = SEV1 (all hands), SEV2 (on-call), SEV3 (next day).
- **First actions** = acknowledge, verify it's real, open runbook, follow steps.
- **Runbooks rot** = test them; update when systems change; unverified runbooks are dangerous.

---

## One-Liner to Remember

*Runbooks are the fire evacuation plan for your software—written when calm, followed when chaos hits.*

---

## Next Video

Next: Observability. Logs, metrics, traces. The three pillars. How they work together when you're debugging a slow API. See you there.
