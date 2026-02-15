# Impact: Outcomes, Not Output

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

You shipped 10 features this quarter. Your PR count is through the roof. You're always busy. And yet—promotion doesn't come. Why? Because at L6, you're judged on *impact*, not activity. Output is how much you produce. Outcome is what *changes* because of your work. Let's unpack the difference.

---

## The Story

Two builders work on the same street. Builder A lays 500 bricks a day. Impressive! High output. Builder B lays 200 bricks. But Builder B designs the foundation to withstand earthquakes. When the earthquake hits, Builder B's building stands. Builder A's collapses. Who had more impact?

Output = how much you produce. Lines of code. Features shipped. Bugs fixed. PRs merged. It's *activity*.

Outcome = what changes because of your work. User experience improved. System handles 10x scale. Incidents reduced 80%. Team velocity doubled. It's *results*.

At L6, you're judged on outcomes. Not how busy you are. Not how many lines you wrote. What *changed*?

This matters in performance reviews, promotion packets, and everyday prioritization. When you propose a project, the first question should be: what outcome will this create? If you can't answer, you might be optimizing for output instead of impact. The shift from "I did a lot" to "here's what changed because of my work" is fundamental at Staff level.

---

## Another Way to See It

Imagine a salesperson who makes 100 calls a day. Output: high. But they close zero deals. Outcome: zero. Another salesperson makes 20 calls, closes 5 deals. Output: lower. Outcome: higher. Which one would you promote? Same in engineering.

---

## Connecting to Software

The trap is simple: being *busy* is not the same as being *impactful*. Shipping 10 features that nobody uses is wasted output. Fixing 50 bugs in a module you're about to deprecate is wasted output. Refactoring code that never had performance issues—output, not outcome.

How do you think in outcomes? Ask: What problem does this solve? For how many users? What happens if we *don't* build it? What's the measurable improvement? If you can't answer these, you might be producing output without outcome.

Before starting any project, write down the outcome. "When this is done, X will improve by Y." If you can't write that sentence, pause. You might be about to produce output without outcome. Many engineers—especially talented ones—fall into the trap of busy-ness. They feel productive. But productivity without impact doesn't move the needle at L6.

```
OUTPUT (Activity)                 OUTCOME (Results)
┌──────────────────────┐         ┌──────────────────────┐
│  Lines of code       │         │  Users helped        │
│  PRs merged          │         │  Incidents reduced   │
│  Features shipped    │         │  Scale achieved      │
│  Bugs fixed          │         │  Team velocity up    │
└──────────────────────┘         └──────────────────────┘
         │                                    │
         ▼                                    ▼
    "How much?"                          "What changed?"
    Countable                             Measurable
```

---

## Let's Walk Through the Diagram

On the left: output. Countable things. PRs, lines, features. On the right: outcome. Measurable change. Incidents down. Users happier. Scale achieved. L5 is often measured on output—did you ship? L6 is measured on outcome—did it *matter*?

---

## Real-World Examples (2-3)

**Example 1: Caching project.** Output: "I added Redis, wrote 2000 lines of cache logic." Outcome: "Page load time dropped 40%, bounce rate decreased 15%." The second sentence is what Staff-level reviews want to hear.

**Example 2: Migration.** Output: "I migrated 50 services to the new platform." Outcome: "Deploy time went from 4 hours to 20 minutes. On-call pages dropped 60%." Output describes activity. Outcome describes impact.

**Example 3: Refactor.** Output: "I refactored 10K lines. Cleaner code." Outcome: "Hmm. No measurable improvement in performance, reliability, or velocity." Sometimes refactors *are* outcome—if they unblock the team or prevent future bugs. But refactoring for its own sake is output, not outcome.

The diagram makes it clear. Output answers "how much?" Outcome answers "what changed?" In promotion packets and performance reviews, L6 candidates are asked to demonstrate outcome. "I shipped 20 features" is weak. "I reduced P99 latency by 50%, enabling us to support 3x traffic" is strong. When you write your self-review or promotion packet, lead with outcomes. Put the numbers first. "Reduced incident count by 60%" before "Refactored the notification service." Outcome-first communication is a habit that serves you at every level. Start practicing it now.

---

## Let's Think Together

"You refactored the entire codebase. 10K lines changed. No bugs fixed. No performance gained. Was this impactful?"

Probably not. Refactoring can be impactful if it reduces future bugs, improves velocity, or unblocks other work. But "I cleaned the code" without a measurable outcome is often just output. At L6, you'd want to tie it to something: "This refactor reduced onboarding time by 50%" or "This enabled us to ship feature X 2 weeks faster."

---

## What Could Go Wrong? (Mini Disaster Story)

A talented engineer works 60-hour weeks. They ship constantly. Their manager loves their output. But at promotion time, the Staff committee asks: "What's the measurable impact?" The manager struggles. "Well, they ship a lot." That's not enough. The promotion is deferred. The disaster? Mistaking output for impact. You can be incredibly busy and have zero Staff-level impact. The fix: always tie your work to outcomes. Before you start, ask: what will *change* when I'm done?

Another trap: optimizing for visibility instead of impact. "I'll work on the flashy new feature everyone's talking about." But maybe the highest impact is the boring reliability work nobody notices—until it prevents an outage. At L6, you learn to separate "what gets noticed" from "what actually matters." Impact sometimes hides in unglamorous work.

---

## Surprising Truth / Fun Fact

Amazon's leadership principles include "Bias for Action" but also "Deliver Results." They're not the same. Action is output. Results are outcome. You can have bias for action and still fail if those actions don't deliver results. At L6, "deliver results" carries more weight.

---

## Quick Recap (5 bullets)

- **Output:** Activity. Lines, PRs, features. **Outcome:** Results. What changed?
- **Trap:** Being busy ≠ being impactful. 10 features nobody uses = wasted output.
- **Think in outcomes:** What problem does this solve? For how many? What if we don't build it?
- **Refactoring 10K lines with no measurable gain = output, not outcome.**
- **Before you start:** What will change when I'm done? If you can't answer, reconsider the project.

---

## One-Liner to Remember

**Output is how much you do. Outcome is what changes because of it. At L6, outcome wins.**

---

## Next Video

Next: Ownership. It's not just your code. It's the system, the team, and the technical direction.
