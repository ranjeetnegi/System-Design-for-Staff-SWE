# How Staff System Design Interviews Are Evaluated

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Two candidates design a chat system. One draws perfect boxes and arrows. Correct architecture. Textbook. The other's diagram is messier—but they drive the conversation. They ask requirements. They state assumptions. They articulate trade-offs. Guess who gets the offer? The second one. At Staff level, it's not about the right answer. It's about HOW you think.

---

## The Story

Two candidates. Same problem: design a chat system. Candidate A draws a beautiful diagram. Load balancer. API servers. WebSocket handlers. Message queue. Database. Sharding. It's correct. Technically sound. Then the interviewer asks: "Why Kafka instead of SQS?" Candidate A stammers. "Kafka is... good for messaging?" They don't know. The diagram was memorized. The thinking wasn't.

Candidate B's diagram is simpler. Fewer boxes. But they lead. "Before I sketch, can I clarify—what's our scale? Real-time or eventual? Do we need message history?" They state assumptions. "I'll assume 10M DAU, sub-second delivery." They make trade-offs explicit. "Kafka here because we need ordering per channel. SQS would be simpler but we'd lose ordering. For chat, order matters." When challenged, they engage. "That's a good point. If we didn't need ordering, SQS would cut our ops burden." Candidate B gets the offer. Not because their diagram was better. Because their THINKING was.

---

## Another Way to See It

Imagine two surgeons. One memorizes the textbook procedure. Cuts in the right places. Follows the steps. The other understands why each cut matters. Adapts when something's different. Explains their reasoning. The first might do fine on routine cases. The second handles the unexpected. Staff interviews test the second. Can you think under ambiguity? Can you drive? Can you defend? The diagram is evidence—not the goal.

---

## Connecting to Software

Staff interviews evaluate five axes. **(1) Problem exploration:** Do you clarify? Ask about scale, consistency, constraints? Or do you assume? **(2) High-level design:** Is your architecture reasonable? Components make sense? Data flows correctly? **(3) Deep dive:** Can you go deep on one or two components? Scale, failure modes, data models? **(4) Trade-off articulation:** Do you explain WHY? Alternatives? Trade-offs? Or do you just pick? **(5) Communication:** Do you lead the conversation? Or wait for prompts? L6 signal: you drive. You identify risks proactively. You discuss alternatives. You acknowledge what you don't know. You don't freeze when challenged.

---

## Let's Walk Through the Diagram

```
STAFF INTERVIEW EVALUATION MATRIX
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   AXIS 1: Problem Exploration          AXIS 2: High-Level Design │
│   ┌─────────────────────────┐         ┌─────────────────────────┐│
│   │ Clarify? Scale? Consist? │         │ Reasonable architecture?││
│   │ State assumptions?       │         │ Components? Data flow?   ││
│   └─────────────────────────┘         └─────────────────────────┘│
│                                                                  │
│   AXIS 3: Deep Dive                    AXIS 4: Trade-offs        │
│   ┌─────────────────────────┐         ┌─────────────────────────┐│
│   │ Go deep on 1-2 parts?   │         │ Explain WHY? Alternativ? ││
│   │ Scale? Failure modes?   │         │ Defend under challenge?  ││
│   └─────────────────────────┘         └─────────────────────────┘│
│                                                                  │
│   AXIS 5: Communication                                         │
│   ┌─────────────────────────────────────────────────────────────┐│
│   │ Lead the conversation? Drive? Signpost? Handle pushback?    ││
│   └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│   Strong diagram + weak thinking = No. Weak diagram + strong      │
│   thinking = Maybe. Strong both = Yes.                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Five axes. Not just "did you get the right answer." Did you explore? Design reasonably? Go deep? Articulate trade-offs? Communicate like a leader? The matrix shows the full picture. A perfect diagram with no depth scores low. A messy diagram with strong reasoning can score high. Interviewers are watching the PROCESS.

---

## Real-World Examples (2-3)

**Example 1: The memorizer.** Draws URL shortener from a YouTube video. Perfect. Then: "What if we need 10 billion URLs per day?" Blank. They never thought about scale. They implemented a pattern. They didn't design. Rejected.

**Example 2: The driver.** Designs notification system. Asks: "Push, email, or both? What's latency? Do we need ordering?" Designs. Goes deep on delivery guarantees. "The hard part here is exactly-once. Let me think through idempotency..." Doesn't need prompts. The interviewer leans back. Strong hire.

**Example 3: The defensive candidate.** Designs well. Interviewer: "Why not use a simpler approach?" Candidate: "This is the standard way." No exploration. No "that's a fair point." Defensive. Even if the design was right, the response was wrong. Staff engineers collaborate. They don't defend territory.

---

## Let's Think Together

"Interviewer says: 'Design a notification system.' What do you do in the FIRST three minutes?"

Don't draw. Don't reach for the marker. ASK. "What's the scale—notifications per second? What channels—push, email, SMS? Do we need ordering? What's the latency requirement? B2B or B2C?" State assumptions: "I'll assume 1M notifications per second, multiple channels, eventual consistency acceptable for most use cases." Then: "I'll start with a high-level design—ingestion, routing, delivery—then we can go deep on the trickiest part." Those three minutes set the tone. You've shown: exploration, structure, leadership. The design comes after. The thinking comes first.

---

## What Could Go Wrong? (Mini Disaster Story)

A senior engineer aces the coding round. Strong resume. Great references. System design: they draw a perfect distributed system. Every box in place. Then: "Walk me through what happens when the primary database fails." Silence. "We... have a replica?" "How does failover work?" "The load balancer... switches?" Vague. Surface-level. The interviewer digs. "What about split-brain? Consistency during failover?" The candidate doesn't know. They drew the boxes. They never thought through the failure modes. Rejected. The diagram was a facade. The thinking wasn't there.

---

## Surprising Truth / Fun Fact

At Google, interviewers are trained to distinguish "pattern matching" from "systems thinking." Pattern matching: you've seen this before, you reproduce it. Systems thinking: you reason from first principles, you adapt, you explore. They want the second. A candidate who says "I haven't seen this exact problem, but here's how I'd approach it" can outperform someone who's memorized ten designs. Thinking beats remembering.

---

## Quick Recap (5 bullets)

- **It's not the diagram—it's the thinking.** Perfect boxes + weak reasoning = no.
- **Five axes:** Problem exploration, high-level design, deep dive, trade-offs, communication.
- **L6 signal:** You drive. You ask. You state assumptions. You defend without being defensive.
- **Memorization fails:** Interviewers probe. "What if scale is 100x?" Memorized answers break.
- **Collaborative, not defensive:** "That's a good point" beats "No, this is right."

---

## One-Liner to Remember

**Staff interviews evaluate HOW you think—not just WHAT you draw. Drive the conversation. Show the reasoning.**

---

## Next Video

Next: how to drive the conversation. The tour guide who leads versus the one who follows—and why it matters.
