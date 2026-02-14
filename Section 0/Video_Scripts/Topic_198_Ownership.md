# Ownership: Beyond Your Code

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

The system goes down at 2 AM. It's not your service. Do you roll over and go back to sleep? Or do you help? At L6, the answer is obvious: you help. Because ownership isn't about your code. It's about the system's success. Let's explore what "ownership" means at Staff level.

---

## The Story

Imagine a shop owner. They don't just stand at the counter. They check if the roof leaks. They notice the sign is fading. They talk to unhappy customers. They monitor competitors. The shop owner owns *everything* about the shop's success—not just their daily task.

At L6, you're the shop owner. You don't just own your code. You own the system's reliability. The team's technical health. The architecture's evolution. The on-call experience. The migration plan. You own the *outcome* of the system, not just your PRs.

This doesn't mean you do everyone's job. It means you *care* about the result. When something breaks, you don't ask "is it my code?" You ask "can I help?" Ownership expands from your module to your system to—at Staff+—the technical direction of the organization. You become a force multiplier: your decisions and actions improve how others build.

---

## Another Way to See It

Think of it as expanding circles. L5: you own your code. L6: you own your system. Staff+: you own technical direction. Each level expands the sphere of "your problem." A neighboring team's API is a bottleneck for yours? At L5, you might complain. At L6, you propose a solution—and maybe help implement it.

---

## Connecting to Software

Code ownership means "this is my module. I'll maintain it." System ownership means "this system succeeds or fails, and I care about both." If the system goes down at 2 AM and you can help—you help. Even if "it's not my service." Even if the root cause is upstream or downstream. You own the outcome.

```
OWNERSHIP EXPANSION
┌─────────────────────────────────────────────────────────┐
│  L5: "My code"   →   L6: "My system"   →   Staff+:     │
│  My module,           System + neighbors.   Tech dir.   │
│  my PRs.              On-call, migration.   Org-wide.   │
└─────────────────────────────────────────────────────────┘
         │                           │                           │
         ▼                           ▼                           ▼
   "Not my problem"            "Our problem"             "I'll fix it"
   (other teams)               (cross-boundary)           (force multiplier)
```

---

## Let's Walk Through the Diagram

On the left: L5 owns their code. "That's another team's problem." In the middle: L6 owns the system. Cross-boundary issues become "our problem." On the right: Staff+ owns technical direction. They're force multipliers—they fix things across the org. The attitude shifts from "not my problem" to "I'll fix it."

The diagram captures a progression. You don't jump from L5 to Staff+ overnight. You expand ownership gradually. First, you care about your neighbor's service because it affects yours. Then you care about the whole system. Then you care about how the org builds. Each step is a mindset shift—from "my code" to "our outcome."

---

## Real-World Examples (2-3)

**Example 1: Downstream bottleneck.** A downstream team's service causes 30% of your incidents. Whose problem is it? At L5: "Theirs. We need them to fix it." At L6: "Ours. I'll work with them. Maybe we need better contracts. Maybe we need circuit breakers. Maybe I'll contribute to their codebase." L6 expands ownership.

**Example 2: Migration.** Your team uses an old database. Migrating is painful. Nobody wants to own it. L6 says: "I'll own the migration plan. I'll create the runbook. I'll drive the timeline." They don't wait for someone to assign it. Migrations are often orphaned—everyone knows it needs to happen, but no one owns it. L6 sees that gap and fills it. They make it their problem.

**Example 3: On-call.** A page comes in. It's a dependency. At L5, you might say "not our service, escalate." At L6, you check: can I help? Do I understand the system? You might jump in, fix it, then write a post-mortem that improves both teams.

The mindset shift is subtle but powerful. L5 draws a boundary: "this is mine, that is theirs." L6 asks: "what's the best outcome for the user and the system?" Sometimes that means stepping across the boundary. Not to take over—but to help. To align. To fix. That's what ownership at L6 looks like in practice.

---

## Let's Think Together

"A downstream team's service causes 30% of your incidents. Whose problem is it?"

At L5, it's theirs. At L6, it's *ours*. You might not own their code. But you own the *outcome*—your users see the failure. So you work with them. You propose solutions. You might even contribute. Ownership at L6 means caring about the result, not just the boundary of your team.

---

## What Could Go Wrong? (Mini Disaster Story)

A critical outage happens. Root cause: a service you don't own. Your team was impacted. In the post-mortem, everyone points fingers. "That team should have..." "They never..." The L6 in the room stays quiet—they didn't own it either. Six months later, the same outage happens again. The disaster? Nobody expanded ownership. Everyone stayed in their lane. The system suffered. At L6, "not my team" is not an excuse. If you're in the room and you can help, you own it.

A nuance: ownership doesn't mean doing everyone's job. It means *caring* about the outcome and *enabling* fixes—even when you're not the one writing the code. Sometimes ownership is writing the design doc. Sometimes it's unblocking another team. Sometimes it's jumping on a call at 2 AM. The form varies. The mindset doesn't: you own the result.

---

## Surprising Truth / Fun Fact

At Netflix, the culture of "Freedom and Responsibility" means engineers are expected to act like owners—of the whole system, not just their slice. If you see a problem, you fix it. No permission needed. That's L6 ownership in action.

---

## Quick Recap (5 bullets)

- **Code ownership** → **System ownership** → **Technical direction ownership.** Each level expands.
- **At L6:** You own the outcome. Not just your PRs. Reliability. On-call. Migration.
- **Cross-team:** Downstream causes your incidents? It's your problem too. Propose solutions. Help.
- **2 AM page for a dependency?** If you can help, you help. "Not my service" = L5 mindset.
- **Trap:** Staying in your lane. At L6, you expand the lane. Your scope grows with your level.

---

## One-Liner to Remember

**At L6, you own the system's outcome—not just your code. If you can help, you help.**

---

## Next Video

Next: Trade-offs. How to make them explicit. Every design decision has trade-offs. L6 engineers state them clearly.
