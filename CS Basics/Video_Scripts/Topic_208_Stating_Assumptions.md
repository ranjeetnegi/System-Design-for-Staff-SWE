# Stating Assumptions Out Loud

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

"I'm assuming the crime happened between 10 PM and 2 AM." The detective says it out loud. Why? So the team can challenge it. If the assumption is wrong, they find out early. Hidden assumptions become hidden risks. In system design, the same rule applies. Say your assumptions. Out loud.

---

## The Story

A detective solves a case. Evidence points to a time window. Instead of silently building a theory, the detective says: "I'm assuming the crime happened between 10 PM and 2 AM based on the evidence. If new evidence shows otherwise, I'll adjust." By stating the assumption, the team can challenge it. "What about the witness who saw the suspect at midnight elsewhere?" Early correction. Better outcome. Hidden assumptions? They drive the whole investigation—and nobody can question what they can't hear.

In system design: "I'm assuming 80% reads, 20% writes." "I'm assuming eventually consistent is acceptable for the feed." "I'm assuming we're targeting 99.9% availability." Say it. Out loud. Assumptions frame every decision you make. Wrong assumption? Wrong design. But UNSTATED assumptions can't be challenged. They silently steer you. And when they're wrong, the design fails. Nobody knew why. Because the assumption was never said.

---

## Another Way to See It

Think of a GPS. It assumes you're in a car. It suggests routes for driving. If you're walking, those routes are wrong. But the GPS doesn't know you're walking—because you never told it. Your design is the same. It assumes things. If those assumptions are wrong, the design fails. Stating assumptions is like telling the GPS you're walking. Now it can route correctly. Unstated assumptions? You get driving directions when you're on foot.

---

## Connecting to Software

**Why state assumptions?** They frame all your decisions. Read-heavy? You'll optimize for caching. Write-heavy? You'll optimize for throughput. Wrong assumption? Wrong optimization. But unstated assumptions can't be challenged. The interviewer can't say "actually it's 50-50" if they don't know you assumed 80-20. You design for the wrong problem. You fail. And you never knew why.

**How to state them.** "Let me assume X. If X isn't true, we'd need to reconsider Y." This shows maturity. You're not just assuming—you're aware of the dependency. You're inviting correction. "I'm assuming 10M DAU. If it's 100M, our sharding strategy would need to change." That sentence does two things: it documents your mental model, and it signals you've thought about scale variance. Staff-level.

**Common assumptions to state:** Read/write ratio. Consistency model (strong vs eventual). Data size and growth. User geography (global vs regional). Peak vs average traffic. Budget constraints. Latency requirements. Failure tolerance. List them. Say them. Let the room correct you.

---

## Let's Walk Through the Diagram

```
ASSUMPTIONS → DESIGN DECISIONS
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   UNSTATED:                        STATED:                        │
│   "I'll use Redis for cache"       "I'm assuming 80% reads.      │
│        │                                 │  So I'll use Redis    │
│        │  Why? Nobody knows.              │  for cache. If it's   │
│        │  Can't be challenged.            │  50-50, we'd need    │
│        ▼                                 │  write-through       │
│   Wrong if write-heavy?             │  strategy instead."       │
│   Design fails. Silent.                  │                       │
│                                         │  Assumption visible.   │
│                                         │  Can be corrected.     │
│                                         ▼                        │
│                                    Design adapts.                │
│                                                                  │
│   KEY: "I'm assuming X. If X isn't true, we'd reconsider Y."     │
│        That's the Staff pattern.                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Unstated assumption leads to a design. Nobody knows the reasoning. Wrong assumption? Wrong design. Nobody can fix it. Stated assumption: "I'm assuming X. So I'm doing Y. If X isn't true, we'd do Z." The chain is visible. The interviewer can say "actually, it's write-heavy" and you pivot. The diagram shows the difference. One path is opaque. One is transparent. Staff engineers choose transparent.

---

## Real-World Examples (2-3)

**Example 1: Feed design.** "I'm assuming mostly reads, eventual consistency OK. So I'll use a read-through cache and eventually consistent writes." Interviewer: "Actually we need strong consistency for the first post." Candidate: "Then we'd need a different approach—sync write to primary, read from replica with consistency token. Let me revise." The assumption was stated. Correction was possible. Design adapted. Strong signal.

**Example 2: Scale assumption.** "I'm assuming 10M DAU. At that scale, a single database with replicas works." Interviewer: "What if it's 100M?" Candidate: "At 100M we'd need sharding. Our user_id-based shard key would distribute load. We'd need to revisit the cache strategy—multi-region cache invalidation gets harder." The candidate had thought about it. Stating the assumption made the follow-up natural. Prepared.

**Example 3: Real project.** "We'll use eventual consistency." Months later: bug. "Users see old data after updates." Root cause: someone assumed strong consistency. The assumption was never written down. The design was wrong for the requirement. Stating it in a design doc would have caught it. Unstated assumptions hide in code. They cause production fires.

---

## Let's Think Together

"You assume 10M DAU. Interviewer says: 'What if it's 100M?' How does your design change?"

Don't freeze. You've set this up by stating the assumption. "At 10M DAU we're fine with a single database cluster and replicas. At 100M we'd need to shard. I'd use user_id as the shard key to distribute load. We'd need to revisit: (1) cross-shard queries—we'd avoid them or use a separate analytics store, (2) cache—we'd need consistent hashing for cache keys, (3) database connections—connection pools per shard." You've shown you've thought about scale. The assumption wasn't a guess—it was a design anchor. When the anchor moves, you move with it. That's the point of stating it: you're ready for the follow-up.

---

## What Could Go Wrong? (Mini Disaster Story)

A team designs a recommendation engine. They assume 100K requests per second. They build for it. Launch. Traffic hits 1M per second. The system collapses. Why? The assumption was in someone's head. It was never written. It was never challenged. "I thought we said 100K?" "I thought we said 1M?" Nobody knows. The design was wrong for the actual scale. Stating "I'm assuming 100K RPS—if it's higher we need to add X" would have triggered a conversation. Maybe someone would have said "we're targeting 1M." Crisis avoided. Unstated assumptions are silent time bombs.

---

## Surprising Truth / Fun Fact

At Amazon, design docs start with an "Assumptions" section. It's required. Before any architecture, engineers list: scale assumptions, consistency assumptions, failure model assumptions. If the doc doesn't have it, the review sends it back. Why? Because assumptions are the foundation. Wrong foundation = wrong building. Making them explicit is policy, not preference.

---

## Quick Recap (5 bullets)

- **Assumptions frame decisions.** Wrong assumption = wrong design. Unstated = can't be challenged.
- **State them:** "I'm assuming X. If X isn't true, we'd reconsider Y."
- **Common ones:** Read/write ratio, consistency, scale, geography, peak vs average, budget.
- **Invite correction:** Stating assumptions shows maturity. You're not hiding. You're collaborating.
- **Document:** In design docs, in interviews. Make the mental model visible.

---

## One-Liner to Remember

**Say your assumptions. Out loud. If they're wrong, you'll find out early. If they're hidden, you'll find out in production.**

---

## Next Video

Next: defending your design under challenge. The lawyer in court—and why pushback is a test, not an attack.
