# Time Management in a 45-Minute Design

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Forty-five minutes. Some candidates spend thirty on requirements and fifteen rushing through the design. Others dive in immediately and realize at minute forty they forgot the main course. The difference? Time management. Intentional split. Mental checkpoints. The winning candidate knows where they should be—and when.

---

## The Story

A chef in a cooking competition. Forty-five minutes on the clock. Some chefs spend thirty minutes choosing ingredients—inspecting every vegetable, debating every spice. Then fifteen minutes rushing to cook. The dish is raw. Presentation is a mess. Others dive in immediately. Chop. Fry. Plate. At minute forty they realize they forgot the main course. They only made sides. The winning chef? Five minutes planning. Ten minutes prep. Twenty-five minutes cooking. Five minutes plating. Balanced. Intentional. They know the clock. They have a plan. They execute it.

System design is the same. Forty-five minutes. No more. The candidate who wanders runs out of time. The one who plans—and checks the clock—finishes. Time management isn't optional. It's part of the design.

---

## Another Way to See It

Think of a triathlon. Swim, bike, run. If you spend two hours swimming, you never bike or run. You're disqualified. Each leg has a time budget. System design has legs too: understand, design, go deep, wrap up. Spend too long on one leg—you never finish the race. Pace yourself. Check your splits. Cross the line with something complete.

---

## Connecting to Software

**Suggested split:** Requirements (5 min) → High-level (10 min) → Deep dive (20 min) → Wrap-up (5 min). Leave 5 min buffer. That's 40 minutes of structured work. The extra 5 handles tangents, follow-up questions, or a slightly longer deep dive. The key: each phase has a limit. Stick to it.

**Common traps.** Spending 15+ minutes on requirements—over-clarifying. You never get to the design. Never going deep—staying surface-level the whole time. The interviewer never sees your depth. No wrap-up—running out of time mid-sentence. The design feels incomplete. No closure. Bad impression. Trap: getting stuck on one component. You drill into database design for 25 minutes. You never cover scaling. Never cover failure modes. One deep dive is good. Only one deep dive for the whole interview is not. Vary. Cover breadth and depth.

**Tip: set mental checkpoints.** "At 10 minutes, I should be done with requirements and starting high-level." "At 25 minutes, I should be in deep dive." "At 40 minutes, I should be wrapping up." Glance at the clock. Not obsessively. But enough to stay on track. If you're behind, adjust. "We've spent more time on requirements than I planned—let me quickly sketch the high-level so we have time for the deep dive." Recovery is possible. Drifting forever is not.

---

## Let's Walk Through the Diagram

```
THE 45-MINUTE CLOCK: MENTAL CHECKPOINTS
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   0    5    10   15   20   25   30   35   40   45               │
│   |----|----|----|----|----|----|----|----|----|                │
│   │ RQ │ HL │    D E E P   D I V E       │ WRAP│                │
│   │ 5  │ 10 │          20 min            │  5  │                │
│   └────┴────┴───────────────────────────┴─────┘                │
│                                                                  │
│   CHECKPOINTS:                                                    │
│   • 5 min  → "Done clarifying. Moving to design."               │
│   • 15 min → "High-level done. Picking deep-dive topic."         │
│   • 25 min → "Deep in component 1. Will do 2nd or wrap."         │
│   • 35 min → "Wrapping up soon. Summarize trade-offs."           │
│   • 40 min → "Final recap. Land the plane."                      │
│                                                                  │
│   BEHIND?  → "We've spent extra on X. I'll compress Y to catch   │
│              up. The deep dive is critical—I'll protect that."    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: The clock. 0–5: requirements. 5–15: high-level. 15–35: deep. 35–45: wrap. Checkpoints at 5, 15, 25, 35, 40. If you're behind at 15—you spent 12 minutes on requirements—don't panic. Compress high-level. Protect deep dive. Say it: "I'll sketch the high-level quickly so we have time to go deep." Recovery. The diagram is your map. Use it.

---

## Real-World Examples (2-3)

**Example 1: The over-clarifier.** At 20 minutes, still asking questions. "What about this edge case? And that?" The design hasn't started. The interviewer is restless. Fix: at 5 minutes, force yourself to move. "I have enough to get started. I'll make assumptions and we can refine." Protect the design time. Requirements are necessary—but bounded.

**Example 2: The surface-skimmer.** At 35 minutes, beautiful diagram. But nothing deep. Interviewer: "Can you go deeper on the database?" Candidate has 10 minutes. They rush. Shallow. The fix: at 15 minutes, proactively transition. "Let me go deep on the database design—that's where the interesting trade-offs are." Create time for depth. Don't wait for the prompt.

**Example 3: The recovery.** At 25 minutes, candidate realizes they're behind. They've only done high-level. "We're at 25 minutes—I want to use our time well. I'll spend the next 15 minutes going deep on the two critical components: scaling and failure modes. Then we'll wrap up." They recover. They communicate. They finish. Strong. Recovery beats denial.

---

## Let's Think Together

"You're at minute 30. You've covered high-level but haven't gone deep on anything. What do you do?"

First: acknowledge. "We're at 30 minutes—I notice we've stayed high-level. I'd like to go deep on at least one area." Then: choose. Pick the most critical component. "The hardest part here is the ranking service. Let me spend the next 10–12 minutes detailing that—data model, scaling, failure modes." Execute. Go deep. At 40 minutes: "We have a few minutes left. Let me summarize: we chose X because Y. At scale we'd need to revisit Z." Wrap up. You've recovered. You've shown depth. You've landed. The key: don't pretend you have more time. Don't rush through five topics shallowly. Go deep on one. One strong deep dive + wrap-up beats five weak ones. Prioritize. Execute. Close.

---

## What Could Go Wrong? (Mini Disaster Story)

A candidate designs a notification system. Great energy. Lots of ideas. At 20 minutes they're still adding features. "And we could add batching. And we could add priority queues. And we could add A/B testing for delivery." The interviewer tries to redirect. "Can you go deeper on delivery guarantees?" The candidate nods and keeps listing features. At 42 minutes: "Oh, we're almost out of time. Let me quickly..." They never went deep. They never wrapped up. The design was a mile wide and an inch deep. Time management failure. The lesson: more isn't better. Depth on one thing beats breadth on everything. The clock is real. Respect it.

---

## Surprising Truth / Fun Fact

At Google, interviewers are trained to give one time check—around the 30-minute mark. "We have about 15 minutes left." That's the only hint. Candidates who need it often haven't been tracking. Candidates who say "I know—I'll wrap up in the next five" show they've been managing. The time check is a test. Did you notice? Are you in control? Time awareness is part of the evaluation.

---

## Quick Recap (5 bullets)

- **Split: 5 + 10 + 20 + 5.** Requirements, high-level, deep, wrap-up. Buffer 5 min.
- **Mental checkpoints:** 5 min → design. 15 min → deep dive. 35 min → wrap. 40 min → done.
- **Traps:** Over-clarifying. Never going deep. No wrap-up. Stuck on one thing.
- **Recovery:** "We've spent extra on X. I'll compress Y. Protecting deep dive." Say it. Do it.
- **Prioritize:** One strong deep dive beats five weak ones. Depth over breadth.

---

## One-Liner to Remember

**Forty-five minutes. Plan the split. Check the clock. Protect the deep dive. Land the plane.**

---

## Next Video

Coming up: phrases that signal Staff-level thinking. Why "I'd use Kafka" sounds different when a Staff engineer says it.
