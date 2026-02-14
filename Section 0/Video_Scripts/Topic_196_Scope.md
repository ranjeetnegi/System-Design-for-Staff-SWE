# Scope: Not Assigned, Created by You

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Your manager never asks you to fix the deploy pipeline. Nobody creates a ticket for "reduce cross-team friction." Yet at L6, these become your biggest projects. Why? Because at Staff level, scope isn't assigned. You *create* it. Today we explore how L6 engineers find and define their own work.

---

## The Story

Two architects are hired for the same building project. Architect A waits for the boss. "Design the bathroom." Done. "Now the kitchen." Done. They do great work—on exactly what they're told.

Architect B does something different. They walk through the whole house. They notice: "This hallway wastes space. It creates a safety hazard. The traffic flow is wrong." Nobody asked Architect B to fix this. They *saw* the problem and created their own scope. They went to the boss and said: "I'm redesigning the layout to fix traffic flow and add emergency exits."

Architect A has assigned scope. Architect B has self-generated scope. At L5, you're Architect A. At L6, you're Architect B.

---

## Another Way to See It

L5 is a chef given a recipe. Make this dish. They make it perfectly. L6 is the chef who invents the recipe. They decide the ingredients. They train other chefs. They don't wait for someone to hand them a menu—they create it.

---

## Connecting to Software

At L6, no one tells you what to work on. You identify the most impactful problems yourself. How? Look for repeated incidents. Cross-team friction. Tech debt that blocks progress. Scalability cliffs. Missing infrastructure. The things that make everyone groan but nobody has time to fix.

Scope at L6 is often *ambiguous*. It's not a clear Jira ticket. It's more like: "Our data pipeline can't handle next year's growth." *You* define the project. *You* define the timeline. *You* define the approach. Nobody hands you a spec.

The skill shift is real. At L5, you're evaluated on execution: did you deliver what was asked? At L6, you're evaluated on *problem identification*: did you find the right things to work on? Did you create scope that mattered? This requires observation—listening in meetings, reading incident reports, talking to other teams. You're not waiting for work. You're discovering it.

```
ASSIGNED SCOPE (L5)              SELF-GENERATED SCOPE (L6)
┌──────────────────────┐         ┌──────────────────────┐
│  Boss: "Do X"        │         │  You: "I see problem  │
│  You: "Done"         │         │  Y. I'll fix it."    │
└──────────────────────┘         └──────────────────────┘
         │                                    │
         ▼                                    ▼
┌──────────────────────┐         ┌──────────────────────┐
│  Clear ticket        │         │  Vague problem       │
│  Defined timeline    │         │  YOU define project   │
│  Known success       │         │  YOU define success  │
└──────────────────────┘         └──────────────────────┘
```

---

## Let's Walk Through the Diagram

On the left: someone tells you what to do. You do it well. On the right: you see a problem nobody asked you to fix. The problem is vague—"things are slow" or "deploys are painful." You turn it into a concrete project. You define what success looks like. You own the full loop from problem to solution. The skills differ: L5 excels at execution. L6 excels at *problem identification* and *stakeholder alignment*. You need both. But at Staff, the expectation shifts toward the latter.

Stakeholder alignment is critical. Creating scope doesn't mean working in isolation. You need to convince others this is worth doing. That means data—incident counts, velocity metrics, user impact. It means communication—articulating why this matters. Self-generated scope still requires buy-in. The difference is: *you* identified the need. You're not waiting for someone else to notice.

---

## Real-World Examples (2-3)

**Example 1: Deploy pain.** Your team ships features fine. But deploys take 4 hours. Nobody asked you to fix it. It's not on the roadmap. An L6 sees this as scope. They say: "I'm going to fix our deploy pipeline. It's blocking velocity and morale." They create the project. They get alignment. They execute.

**Example 2: Repeated incidents.** Every quarter, the same type of outage happens. A downstream service times out. Nobody owns it. L6 creates scope: "I'm going to build circuit breakers and improve our resiliency story. Here's the plan." They don't wait for an incident post-mortem to assign it—they *proactively* own it.

**Example 3: Cross-team bottleneck.** Team A's API is a bottleneck for Team B and C. Nobody has time. L6 creates scope: "I'll design a better contract, maybe a shared SDK. I'll work with both teams." They don't complain in meetings—they propose and execute.

---

## Let's Think Together

"Your team ships features fine but deploys take 4 hours. Nobody asked you to fix it. Is this L6 scope?"

Yes. Deploy pain affects the whole team. It blocks velocity. It hurts morale. It's probably causing production incidents. An L6 doesn't wait for a ticket. They see the problem, create the scope, and drive the fix. The ability to spot these opportunities—and the courage to own them—is what separates L5 from L6.

One more thing: creating scope often means saying no to other things. You can't fix everything. L6 scope is also about *prioritization*—choosing which problems to tackle and which to deprioritize. That's part of the skill. Not just finding problems, but picking the right ones.

---

## What Could Go Wrong? (Mini Disaster Story)

Imagine this. A Staff engineer waits for someone to tell them what to do. They're brilliant—when given work. But they never create their own. Six months pass. Their manager thinks: "This person does great work when assigned, but they're not operating at Staff level." The promotion doesn't come. The disaster? Treating L6 like L5. At Staff, you're expected to find and own problems. Waiting for assignment is a career ceiling.

---

## Surprising Truth / Fun Fact

At many tech companies, L6 job descriptions explicitly say "identifies and drives high-impact projects with minimal direction." Translation: we're not going to tell you what to do. You tell us. If you need a Jira ticket to be productive, that's a signal you're thinking at the wrong level.

---

## Quick Recap (5 bullets)

- **L5:** Scope is assigned. You execute. **L6:** Scope is self-generated. You create it.
- **How to find scope:** Repeated incidents, cross-team friction, tech debt, scalability cliffs, missing infra.
- **L6 scope is often ambiguous.** Not a clear ticket. You define the project, timeline, and approach.
- **Example:** Deploy takes 4 hours. Nobody asked you to fix it. L6 creates that scope anyway.
- **Trap:** Waiting for assignment. At L6, that's the ceiling.

---

## One-Liner to Remember

**At L6, nobody assigns you work. You see the problem, create the scope, and own the outcome.**

---

## Next Video

Next: Impact. Output vs outcome. Why being busy isn't the same as being impactful.
