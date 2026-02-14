# L5 vs L6: What Changes in System Design?

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

You ace every design interview. You know Kafka, caching, load balancing. But something changes when you aim for Staff Engineer. The questions get vaguer. The interviewer pushes back. They want something different—but what exactly? Today we answer: what does L6 system design look like, and how is it different from L5?

---

## The Story

Imagine a soldier and a general. The soldier is excellent. Give them a mission—take that hill, hold that bridge, clear that building—and they execute flawlessly. They're trained, precise, and reliable. The general doesn't fight the battle. The general decides *which* battles to fight. They design the strategy. They make trade-offs that affect the *whole army*—where to commit troops, where to retreat, how to use limited resources.

At L5, you're the soldier. You execute well. You solve assigned problems. You implement designs. Someone says "build a feature" and you build it—cleanly, correctly, on time. Someone says "optimize this query" and you optimize it. You're excellent at *how* to build.

At L6, you're the general. You identify which battles to fight. You design the strategy. You make trade-offs that affect the entire system. L5 designs a feature. L6 designs the *system*. L5 optimizes a query. L6 asks: *is that database even the right choice?* The shift is from "how to build" to "what to build and why."

In interviews, this shows up clearly. L5 candidates give solid designs with good trade-offs. They answer the question. L6 candidates *drive* the conversation. They probe requirements deeply. They reason about cost, scale, and org impact. They challenge the problem itself—"Why are we building this? What's the simplest version?" Key signals interviewers look for: ambiguity tolerance, clear trade-off articulation, business context awareness, and multi-system thinking.

---

## Another Way to See It

Here's a second analogy. L5 is like an excellent chef who can make any dish perfectly. Give them a recipe and they'll nail it. L6 is the restaurant planner. They decide the menu. They design the kitchen layout. They choose the staffing model and the supply chain. They don't just cook—they shape the entire operation.

---

## Connecting to Software

So what does this mean in practice? At L5, your focus is on *component design*. Clean code. Feature delivery. Handling your assigned scope. You own your module. You make it work.

At L6, your focus shifts. System-wide architecture. Cross-team impact. Technical strategy. You identify what *not* to build. You anticipate problems six months ahead. You think in terms of the organization, not just the codebase.

```
L5 MINDset:                    L6 MINDSET:
┌─────────────────┐            ┌─────────────────┐
│  "How do I      │            │  "What should    │
│   build this?"  │            │   we build?"     │
└────────┬────────┘            └────────┬────────┘
         │                              │
         ▼                              ▼
┌─────────────────┐            ┌─────────────────┐
│  Feature scope  │            │  System scope   │
│  Clean design   │            │  Org impact     │
│  Good trade-offs│            │  Challenge the  │
└─────────────────┘            │  problem itself │
                               └─────────────────┘
```

---

## Let's Walk Through the Diagram

On the left, L5 thinks "how do I build this?" They get scope. They design it well. They deliver. On the right, L6 thinks "what should we build?" They question scope. They consider org impact. They challenge whether the problem is worth solving at all. Both are valuable. But L6 operates at a higher level of abstraction and responsibility.

---

## Real-World Examples (2-3)

**Example 1: Recommendation engine.** Someone asks for one. L5 says: "Here's how I'd build it—collaborative filtering, maybe a model, store in Redis for speed." L6 says: "Do we even need one? What's the business impact? What's the simplest version that validates the idea before we invest six months?" L6 probes requirements deeply before touching design.

**Example 2: Database choice.** L5 gets told "we need to scale reads." L5 optimizes. Add replicas. Add caching. L6 asks: "Why are we hitting this database so hard? Is the workload pattern wrong? Should we use a different store entirely?" L6 reasons about cost, scale, and org impact.

**Example 3: Cross-team friction.** L5 notices another team's API is slow. L5 might add timeouts and retries. L6 asks: "Why is this our problem? Can we align on a better contract? Do we need a shared platform?" L6 thinks in multi-system terms.

The diagram above captures the mindset shift. L5 receives well-defined scope and executes. L6 receives vague or no scope and *creates* clarity. They ask "what should we build?" before "how do we build it?" In Staff-level interviews, the bar isn't just technical depth—it's whether you can operate when the problem is fuzzy and the stakeholders are unclear.

---

## Let's Think Together

"You're asked to add a recommendation engine. L5 says 'Here's how I'd build it.' L6 says 'Do we even need one? What's the business impact? What's the simplest version that validates the idea?'"

Pause. Which response would *you* give? If you jump straight to implementation, you're thinking L5. If you pause to question the problem, you're thinking L6. Both matter. But in Staff interviews, they want to see the L6 reflex. The interviewer is testing: can this person operate when the problem is fuzzy? Can they drive the conversation? Can they reason about business impact, not just technical correctness? Those are L6 signals.

---

## What Could Go Wrong? (Mini Disaster Story)

Picture this. A team spends six months building a recommendation system. Beautiful architecture. State-of-the-art models. It ships. Usage? Almost zero. Why? Nobody asked *whether* users wanted recommendations. The problem was assumed. An L5 mindset executed perfectly on the wrong problem. An L6 would have validated the need first—maybe a simple A/B test, maybe a manual curated list. The disaster isn't bad code. It's solving the wrong problem with great code.

---

## Surprising Truth / Fun Fact

At Google, L6 (Staff Engineer) is explicitly expected to have "organizational impact." Your work shapes how *other teams* build. You're not just a great engineer—you're a force multiplier. Your decisions ripple across the org. That's the bar.

---

## Quick Recap (5 bullets)

- **L5 executes.** L6 decides what to execute and why.
- **L5 owns components.** L6 owns system-wide architecture and technical strategy.
- **In interviews:** L5 shows solid design. L6 drives the conversation, probes requirements, challenges the problem.
- **Key signals:** Ambiguity tolerance. Clear trade-off articulation. Business context. Multi-system thinking.
- **Shift:** From "how to build" to "what to build and why."

---

## One-Liner to Remember

**L5 designs the feature. L6 designs the system—and questions whether the feature belongs in it at all.**

---

## Next Video

Next up: Scope. At L6, nobody assigns you work. You *create* it. We'll see how.
