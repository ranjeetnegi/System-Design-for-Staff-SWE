# Multi-Region Failover: Decision Process
## Video Length: ~4-5 minutes | Level: Staff
---
## The Hook (20-30 seconds)

An airline. Primary hub: Delhi. Backup hub: Mumbai. Delhi airport floods. Decision time. WHEN do you failover? WHO decides? HOW do you switch? It's not just "flip a switch." You need: detection (is Delhi really down or just slow?), decision (is the cost of failover worth it?), execution (route all flights to Mumbai), and verification (is Mumbai handling the load?). Multi-region failover in software is the same high-stakes decision. One wrong move and you make things worse instead of better.

---

## The Story

Your app runs in us-east-1. Millions of users. Revenue pouring in. Then — health checks start failing. 30 seconds. 60 seconds. Is it a blip? A bad deployment? Or is the region actually down? Your backup is in us-west-2. It's ready. But flipping the switch means: DNS changes, connection reroutes, potential data loss, and a massive operational event. Get it wrong and you either: (a) failover too late and users suffer for minutes, or (b) failover on a false alarm and create chaos, confusion, and maybe a second outage. There's no easy answer. That's why staff-level engineers think deeply about this.

---

## Another Way to See It

Imagine a fire alarm. Too sensitive: it goes off when someone burns toast. Everyone evacuates. Annoying. False alarm. Too insensitive: real fire, alarm doesn't trigger. People get hurt. Failover detection is the same calibration. Too fast: every network hiccup triggers failover. You're constantly flipping. Too slow: real outage, users down for minutes. You need the right threshold. And you need to test it before the emergency.

---

## Connecting to Software

**Detection.** Automated health checks. But: how long do you wait? 30 seconds of failures? 5 minutes? Too quick = false failover, unnecessary chaos, potential data inconsistency. Too slow = prolonged outage, angry users, lost revenue. Most systems use: 3–5 consecutive failures over 30–60 seconds. Some add: check multiple endpoints, different availability zones. Correlate signals before deciding. One failing endpoint might be a bad server. Five failing across AZs? Probably regional.

**Decision.** Automated vs manual. Automated: system detects failure, fails over immediately. Fast. But risky for catastrophic failover — false positives are expensive. Manual: human decides. Slower but safer. Many companies: auto-failover for non-primary (read replicas), manual for primary (write traffic). The big flip — moving all writes to another region — is often human-approved. Runbooks. Phone calls. Deliberate.

**Execution.** How do you actually switch? DNS change (slow propagation, 5–30 minutes, eventually consistent — users may hit old region for a while). Load balancer switch (fast, seconds, traffic goes to new region immediately). Application-level routing (instant but complex, each service must support it). Your mechanism determines your failover speed. Choose wisely.

**Verification.** After failover — is the secondary region healthy? Handling load? Data consistent? Don't assume. Check. Monitor. Validate. I've seen teams fail over and then discover the secondary wasn't sized for full load. Cascading failure. Both regions down. Verify before you celebrate.

**Failback.** When primary recovers, how do you go BACK? Fail back immediately? Wait for data sync? Catch up replication? Failback is its own decision. Rushing it can cause another outage. Sometimes you stay on the secondary for hours or days.

---

## Let's Walk Through the Diagram

```
                    NORMAL OPERATION
    ┌──────────┐         │         ┌──────────┐
    │  Primary │◀────────┼────────▶│  Users   │
    │  Region  │   All   │   All   │          │
    │  Delhi   │  traffic│ traffic │          │
    └────┬─────┘         │         └──────────┘
         │ replicate    │
         ▼              │
    ┌──────────┐        │
    │ Secondary│        │
    │  Mumbai  │   (standby, ready)
    └──────────┘

                    FAILOVER
    Primary DOWN    →    Detect (30-60 sec)
                     →    Decide (auto or manual)
                     →    Execute (DNS/LB switch)
                     →    Verify (secondary healthy?)
                     →    Users now hit Mumbai
```

The diagram shows: normal state, failure, detection, decision, execution. Each step has trade-offs. Each step can go wrong if you haven't thought it through.

---

## Real-World Examples (2-3)

**AWS** Multi-AZ is automatic. But cross-region failover? Often manual. They document runbooks. Human in the loop for the big switch. They've seen too many false alarms to automate blindly.

**Netflix** runs in multiple regions. Chaos Engineering (Simian Army) intentionally kills regions to test failover. They practice. They know exactly how long it takes and what breaks. When a real outage happens, they're ready. No panic. Just execution.

**Stripe** has strict financial consistency requirements. Their failover isn't just "switch regions." They have to ensure no double-charges, no lost payments. Failover for them includes data consistency checks. The decision process is longer. But correctness matters more than speed for payments.

---

## Let's Think Together

Primary region has 10 seconds of errors. Do you failover? What if it's a brief network blip?

**Answer:** Probably not. 10 seconds is short. Could be a blip. A deployment. A transient issue. A router hiccup. Most failover thresholds are 30–60 seconds or more. You want to avoid "failover thrashing" — failing over, primary recovers, fail back, primary fails again. That's worse than a short outage. Better: wait. Monitor. If errors persist past your threshold, then failover. Have a runbook. Know your number. And test it.

---

## What Could Go Wrong? (Mini Disaster Story)

A company set failover threshold to 15 seconds. One day, a deployment caused 20 seconds of elevated latency. Automatic failover triggered. Traffic slammed the secondary region. Secondary wasn't sized for full load. It had been built for read replicas, not primary traffic. It collapsed. Cascading failure. Both regions down. The "recovery" made things worse. They had to manually bring primary back and pray. Lesson: Secondary must handle full load. Test it. Load test. And consider: maybe 15 seconds was too aggressive. Know your secondary's capacity before you depend on it.

---

## Surprising Truth / Fun Fact

The median time to detect an outage is often longer than the median time to recover — if you're prepared. Companies that practice failover recover in minutes. Companies that don't: hours. Drills matter. Run them quarterly. Know your numbers. When the real thing happens, muscle memory kicks in.

---

## Quick Recap (5 bullets)

- Detection: How long do you wait? Too fast = false failover. Too slow = prolonged outage.
- Decision: Automated (fast, risky) vs manual (slower, safer). Often hybrid.
- Execution: DNS (slow), load balancer (fast), or app-level routing (instant but complex).
- Verification: After failover, confirm secondary is healthy and handling load.
- Failback: When primary recovers, plan the return. Don't rush.

---

## One-Liner to Remember

**Failover isn't a flip. It's detection, decision, execution, and verification. Get the thresholds right. Test the secondary. Know your runbook.**

---

## Next Video

Next up: **Cold Start** — your car on a freezing morning. Engine sputters. Slow to warm up. Same with serverless. First request? Painfully slow. Let's fix that.
