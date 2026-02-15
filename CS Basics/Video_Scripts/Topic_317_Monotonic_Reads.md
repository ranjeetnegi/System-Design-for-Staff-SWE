# Monotonic Reads and Consistent Prefix
## Video Length: ~4-5 minutes | Level: Staff
---
## The Hook (20-30 seconds)

You're reading a live cricket score. Refresh: "India 250/3." Refresh again: "India 230/2." Wait — the score went BACKWARDS? That shouldn't happen. You refresh again: "India 260/4." Scores jumping back and forth. That's a violation of monotonic reads. Once you've seen data at a certain point in time, you should NEVER see OLDER data on a subsequent read. Time doesn't go backward. Your view of the data shouldn't either.

---

## The Story

You have multiple database replicas. Load balancer distributes reads across them. Replica A is fully up to date. Replica B is lagging. Replica C is somewhere in between. You read from A. You get "score = 250." You read again. This time the load balancer sends you to B. B has "score = 230." You just went backward in time. You saw 250. Now you see 230. That's impossible in the real world. A cricket score doesn't decrease (well, it can in rare cases, but you get the idea). The point is: your READS shouldn't show you older data than you've already seen. Monotonic reads prevents that.

---

## Another Way to See It

Imagine reading a book. Page 10. Page 20. Page 30. You're moving forward. Now imagine the book randomly sends you back to page 15. Then forward to page 35. Then back to page 25. You'd be confused. Monotonic reads means: once you've read page 30, you never see page 20 again. Your read sequence only moves forward. No backtracking.

---

## Connecting to Software

**Monotonic reads.** If you read value V at time T, every subsequent read should return V or something NEWER. Never older. Prevents "time travel." Your view of the system only progresses forward.

**How it breaks.** Load balancer routes reads to different replicas. Replica A = time 100. Replica B = time 90. You read from A → get time 100 data. Next read goes to B → get time 90 data. You went backward. Violation.

**Fix.** Sticky routing. Always route a user's reads to the same replica. That replica might lag, but it never goes backward. Same replica = same progression of state. Or: version-aware reads. Client tracks highest version seen. Server rejects or delays responses older than that. Ensures monotonicity. The key is: one user's view must be consistent. Even if it's eventually consistent globally, locally (for that user) it should never backtrack.

**Consistent prefix.** Related but different. Reads see writes in the ORDER they were applied. If write A happened before write B, you never see B without A. Important for causal relationships. Example: Alice asks "What time is the meeting?" Bob replies "3 PM." Without consistent prefix, you might see "3 PM" before the question. Nonsense. Consistent prefix preserves order.

---

## Let's Walk Through the Diagram

```
    VIOLATION: Load balancer sends to different replicas
    
    Read 1 ──▶ Replica A (up to date) ──▶ "India 250/3" ✓
    Read 2 ──▶ Replica B (lagging)   ──▶ "India 230/2" ✗ (went backward!)
    Read 3 ──▶ Replica A             ──▶ "India 260/4" ✓
    
    User experience: Score jumps around. Confusing.
    
    FIX: Sticky routing (same user → same replica)
    
    Read 1 ──▶ Replica A ──▶ "250/3"
    Read 2 ──▶ Replica A ──▶ "255/3" (same replica, moved forward)
    Read 3 ──▶ Replica A ──▶ "260/4" (monotonic ✓)
```

Sticky routing = same user, same replica. No jumping. No going backward.

---

## Real-World Examples (2-3)

**Chat applications** need consistent prefix. Messages must appear in order. Alice: "Meeting at 3?" Bob: "Yes." You can't see Bob's reply before Alice's question. That would make no sense. Consistent prefix ensures causal order.

**Collaborative documents** (Google Docs) use monotonic reads. You see edits in order. You never see version 5 and then version 3. That would be confusing. Sticky routing to the same replica or version vector solves it.

**Banking** statements. Your balance over time. You see $100. Then $150. Then $80 (after a withdrawal). The $80 is newer — that's fine. But you should never see $150 again after seeing $80 (unless another deposit). Monotonic reads for your session. Imagine checking your balance and it jumps from $80 back to $150. You'd think something was wrong. Monotonic reads prevent that confusion.

---

## Let's Think Together

Chat: Alice says "What time is the meeting?" Bob replies "3 PM." Without consistent prefix, you might see "3 PM" before the question. How confusing! Why does consistent prefix matter here?

**Answer:** Causality. Bob's reply is a RESPONSE to Alice's question. The question must be seen first. If you see "3 PM" without the question, you have no context. "3 PM" what? Consistent prefix ensures: if A happened before B (causally), you never see B without A. Writes are applied in order. Reads reflect that order. Essential for chat, comments, any causally linked data.

---

## What Could Go Wrong? (Mini Disaster Story)

A trading platform displayed portfolio values. Load balancer sent reads to different replicas. User refreshed. Saw $50,000. Refreshed again. Saw $45,000. Panicked. Sold in fear. Refreshed again. $52,000. The $45,000 was from a lagging replica. Stale. User lost money on a bad trade driven by stale data. Monotonic reads would have prevented the confusing backward jump. Lesson: For financial UIs, monotonic reads aren't a nice-to-have. They prevent user confusion and bad decisions.

---

## Surprising Truth / Fun Fact

Monotonic reads don't guarantee you see the latest data. You might be stuck on a lagging replica. But you'll never see OLDER data than you've already seen. It's a weaker guarantee than strong consistency, but stronger than "anything goes." A useful middle ground for many apps. Strong consistency is expensive. "Anything goes" is confusing. Monotonic reads: cheap and sane.

---

## Quick Recap (5 bullets)

- Monotonic reads: once you've seen V, you never see older data. No time travel. Your view only moves forward.
- Breaks when: load balancer sends you to different replicas with different lag.
- Fix: sticky routing (same user → same replica) or version-aware reads.
- Consistent prefix: see writes in order. Never see B without A if A happened first.
- Critical for: chat, collaborative docs, any causally linked data. Get it wrong and users see nonsensical ordering.

---

## One-Liner to Remember

**Monotonic reads: your view only moves forward. Consistent prefix: you see cause before effect. Both prevent confusion.**

---

## Next Video

Next up: **Hybrid Logical Clocks** — two clocks. One real. One logical. Combine them. Get ordering AND real time. How? Physical clocks drift. Logical clocks lack real time. HLC gives you both. Staff-level distributed systems thinking.
