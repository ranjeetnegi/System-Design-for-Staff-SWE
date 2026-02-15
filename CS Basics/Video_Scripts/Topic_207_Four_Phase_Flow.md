# The 4-Phase Flow: Understand, High-Level, Deep, Wrap-Up

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

You're building a house. Do you start pouring concrete? Or do you first ask: What kind of house? How many rooms? Budget? Climate?

Most candidates rush to the diagram. Staff engineers have a structure. Four phases. Get them right, and the interview flows. Get them wrong, and you're lost at minute 35 with no time for depth.

---

## The Story

Building a house. Four phases.

**Phase 1 — Understand:** "What kind of house? How many rooms? Budget? Location? Climate?" You don't design until you know the constraints. A house in Mumbai needs different things than one in Ladakh. A family of six needs different things than a retiree. Without understanding, you build the wrong house.

**Phase 2 — High-level:** "Here's the floor plan. Main structure. Rooms. Flow." You sketch. You don't detail the plumbing yet. You establish the layout. The interviewer sees the big picture.

**Phase 3 — Deep dive:** "Let me detail the plumbing for the kitchen. The electrical wiring for the living room." You zoom in. You show you can go deep. This is where Staff signals emerge — failure modes, consistency, scaling.

**Phase 4 — Wrap-up:** "Here's the summary. Key trade-offs. What we'd improve in v2." You close cleanly. You don't run out of time mid-sentence. You leave a strong impression.

Same in system design. Phase 1: clarify. Phase 2: sketch. Phase 3: go deep. Phase 4: close.

---

## Another Way to See It

Think of a medical diagnosis. Phase 1: Ask symptoms, history, constraints. Phase 2: Hypothesize the general condition. Phase 3: Run specific tests on the most likely cause. Phase 4: Summarize findings and next steps. You don't skip to phase 3. You'd misdiagnose. Structure saves you.

---

## Connecting to Software

**Phase 1 — Understand (5 min):**
- Clarify requirements. Functional + non-functional. Scale. Constraints.
- State assumptions. "I'm assuming 10M DAU. I'm assuming 99.9% availability."
- Don't over-clarify. 5 minutes. Get enough to design. Move on.

**Phase 2 — High-level (10–15 min):**
- Major components. API, services, data stores, queues.
- Data flow. Request path. Key algorithms (e.g., sharding strategy).
- API design. Key endpoints. Not every field — the shape.

**Phase 3 — Deep dive (15–20 min):**
- Pick 1–2 critical components. Scale, failure modes, data models.
- Where the interesting trade-offs are. Message delivery. Consistency. Sharding.
- This is the bulk of the interview. Don't rush phase 2 to get here — but don't linger so long you never arrive.

**Phase 4 — Wrap-up (5 min):**
- Recap trade-offs. "We chose X over Y because..."
- Future improvements. Monitoring. What you'd change at 100× scale.
- Leave time for interviewer questions.

---

## Let's Walk Through the Diagram

```
THE 45-MINUTE MAP

  0 min                    15 min                    35 min              45 min
   │                          │                          │                  │
   ├──── Phase 1 ────────────┤
   │    UNDERSTAND (5 min)    │
   │    • Requirements       │
   │    • Assumptions         │
   │    • Constraints         │
   │                          │
   ├──── Phase 2 ────────────┼───────────────┤
   │    HIGH-LEVEL (10 min)   │
   │    • Components          │
   │    • Data flow           │
   │    • API shape           │
   │                          │
   │                          ├──── Phase 3 ────────────┼──────────┤
   │                          │    DEEP DIVE (20 min)  │
   │                          │    • 1–2 components    │
   │                          │    • Scale, failures    │
   │                          │    • Trade-offs         │
   │                          │                          │
   │                          │                          ├── Phase 4 ──┤
   │                          │                          │ WRAP-UP (5)  │
   │                          │                          │ • Recap      │
   │                          │                          │ • Trade-offs │
   │                          │                          │ • Q&A        │
   └──────────────────────────┴──────────────────────────┴──────────────┘

   ⚠️ Common trap: Spending 15+ min on Phase 1. Never reaching Phase 3 depth.
```

**Narration:** Visualize the clock. Phase 3 is your money phase. If you're still in Phase 1 at minute 15, you're in trouble. If you hit Phase 3 by minute 15, you're golden. Structure = control.

---

## Real-World Examples

**1. The candidate who aced it** — "I'll use a four-phase approach. Phase 1: I need 2 minutes to clarify. Phase 2: 10 minutes for high-level. Phase 3: bulk of our time on the hard parts. Phase 4: 5 minutes to wrap up." Then they executed. At minute 38, they said: "Let me summarize the key trade-offs." Perfect pacing. Strong hire.

**2. The candidate who ran out of time** — Spent 18 minutes on requirements. Asked about every edge case. "What about offline mode? What about RTL languages? What about..." Great questions. But at minute 30, they'd only drawn four boxes. No deep dive. No wrap-up. Interview ended with "we're out of time." Weak signal. No hire.

**3. The "depth-only" candidate** — Jumped to a component at minute 5. Spent 35 minutes on one database sharding strategy. Never showed the full picture. Interviewer: "What about the API?" "Oh, we can add that." Too narrow. Staff need breadth AND depth. Balance the phases.

---

## Let's Think Together

**Question:** Where do most candidates waste time? (Hint: too long in Phase 1, not enough in Phase 3)

**Answer:** Phase 1. They over-clarify. They ask 20 questions when 5–7 would suffice. They treat it like a product spec session. Meanwhile, Phase 3 — the deep dive — gets squeezed. They spend 5 minutes on "what happens when the queue fails?" when they could spend 15. The fix: cap Phase 1 at 5 minutes. Get the critical unknowns. Move. You can always ask "I'm assuming X, correct?" during design. Don't block.

---

## What Could Go Wrong? (Mini Disaster Story)

A candidate was asked to design a rate limiter. They spent 12 minutes on: "Is this per-user or per-IP? Per second or per minute? What about authenticated vs anonymous? What about different tiers? What about..." They had 10 requirements written. At minute 25, they drew a diagram. At minute 40, they started talking about the algorithm. "Time's up." They never explained token bucket vs sliding window. Never discussed distributed rate limiting. All that clarification — and no depth. The interviewer's note: "Couldn't demonstrate technical depth. Over-invested in requirements." No hire.

---

## Surprising Truth / Fun Fact

**Fun fact:** At some companies, the first 2 minutes of a design interview are scored separately — "Did they clarify before designing?" Skipping Phase 1 entirely is an automatic red flag. But so is never leaving it. The sweet spot: 5 minutes. Enough to show you think. Not so much you never build.

---

## Quick Recap (5 bullets)

1. **Phase 1 (5 min):** Clarify. Assumptions. Constraints. Don't overdo it.
2. **Phase 2 (10 min):** High-level. Components. Data flow. API shape.
3. **Phase 3 (20 min):** Deep dive. 1–2 components. Scale, failures, trade-offs.
4. **Phase 4 (5 min):** Wrap-up. Recap. Trade-offs. Q&A.
5. **Phase 3 is the money phase** — Protect it. Don't let Phase 1 eat it.

---

## One-Liner to Remember

*"Four phases. Five minutes to understand. Twenty minutes to go deep. Protect the middle, or lose the game."*

---

## Next Video

Next up: Stating assumptions out loud. Why detectives do it — and why you should too.
