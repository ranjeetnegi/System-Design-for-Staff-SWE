# Rejecting the Wrong Solution (Out Loud)

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A doctor. Patient has a headache. "Let's do brain surgery!" Wait. First: check simpler causes. Dehydration? Stress? Eye strain? A good doctor REJECTS expensive solutions before reaching for them. "I considered surgery but rejected it because the symptoms suggest a simpler cause." Saying this OUT LOUD shows expertise. In system design interviews: showing what you REJECTED and WHY is as valuable as showing what you chose. Anyone can pick the right answer. Explaining why you didn't pick the wrong ones—that shows depth.

---

## The Story

Imagine you're buying a car. The salesperson shows you a sports car. You say: "I considered it but rejected it. I have three kids. I need space. A minivan fits my use case." That's a mature decision. You didn't just pick the minivan. You considered alternatives. You rejected them for stated reasons. In an interview, when you say "I considered a message queue but rejected it because our volume is low and latency requirements are strict—a direct RPC is simpler"—you're doing the same thing. You're showing your reasoning process. Not just your conclusion. Interviewers love that. It separates Staff from Senior. Seniors know the right answer. Staff can explain why the wrong answers are wrong.

---

## Another Way to See It

Think of a chef choosing ingredients. They don't just grab the first thing. "I considered truffle but rejected it—too strong for this dish. The mushrooms will add earthiness without overpowering." The rejection shows culinary judgment. In system design, your rejections show engineering judgment. "I considered Kafka but rejected it—we need 5ms latency and Kafka adds at least 10ms. For 1000 events per second, a simple queue is sufficient." You're demonstrating that you match the solution to the problem. Not the other way around.

---

## Connecting to Software

**Why it matters.** Anyone can memorize "use Redis for caching." But can you say: "I considered Memcached—simpler, faster for pure cache—but rejected it because we need to persist session state and Redis supports that. I also considered an in-memory cache per instance—rejected because we'd have cache inconsistency across instances. Centralized Redis gives us a single source of truth." That's Staff-level reasoning. You're not just choosing. You're eliminating. The elimination process is the signal.

**How to do it.** Use the phrase: "I considered X but rejected it because Y." Or: "We could use Z, but given [constraint], we'll use W instead." Make the rejection explicit. State the alternative. State why it doesn't fit. Then state your choice.

**Common rejections.** "We don't need sharding yet—the data fits in one node. We'll add it when we hit 80% capacity." "Kafka is overkill for 100 events per second—SQS is simpler and sufficient." "Strong consistency isn't needed for a news feed—eventual is fine, lower latency." "Microservices would add operational overhead—for our team size, a modular monolith is better." Each rejection shows you've considered scale, complexity, and fit.

**The pattern.** For every major choice, mentally ask: "What's the alternative? Why am I not choosing it?" Say it out loud. The interviewer wants to hear your reasoning. They can't read your mind.

---

## Let's Walk Through the Diagram

```
REJECTING OUT LOUD - THE PATTERN
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   CHOICE: Use PostgreSQL                                         │
│                                                                  │
│   Alternatives considered and REJECTED:                          │
│                                                                  │
│   MongoDB    → Rejected: need ACID, joins, team expertise        │
│   Cassandra → Rejected: our workload is not write-heavy         │
│   MySQL      → Rejected: PostgreSQL has better JSON support     │
│                                                                  │
│   CHOSEN: PostgreSQL                                             │
│   Reason: ACID, schema flexibility, team fit                      │
│                                                                  │
│   The rejection shows: you didn't default. You reasoned.         │
│                                                                  │
│   Format: "I considered X but rejected it because Y"              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: For every major choice, show the alternatives you rejected. State why. Then state what you chose. The diagram is the script. Use it. The interviewer learns more from your rejections than from your selections. Rejections prove you evaluated. Selections alone could be luck.

---

## Real-World Examples (2-3)

**Example: Caching.** "I considered an in-process cache—rejected because we have multiple service instances and we'd have inconsistency. I considered Memcached—rejected because we need TTL and some persistence for session recovery. I'm choosing Redis—centralized, supports our use case, the team knows it." Three rejections. One choice. Clear reasoning.

**Example: Message queue.** "I considered Kafka—rejected because we need exactly-once delivery and our volume is 500 events per second. Kafka adds complexity we don't need. I considered RabbitMQ—rejected because we want managed infra. I'm choosing SQS—managed, sufficient throughput, simpler operations." Alternatives. Rejections. Choice.

**Example: Database.** "I considered NoSQL for flexibility—rejected because our schema is stable and we need strong consistency for payments. I considered NewSQL like Cockroach—rejected because we're single-region for now and PostgreSQL is sufficient. I'm choosing PostgreSQL with read replicas." Scale-appropriate. Not over-engineered.

---

## Let's Think Together

**"Design a notification system. You choose SQS over Kafka. How do you explain the rejection of Kafka?"**

"I considered Kafka. It gives us exactly-once semantics, replay, and high throughput. But rejected it for our use case because: (1) We're sending 10,000 notifications per second, not millions. SQS handles that. (2) We don't need replay—notifications are ephemeral. (3) Kafka adds operational complexity—partitions, consumer groups, ZooKeeper or KRaft. For our scale, SQS is managed, simpler, and sufficient. If we hit 100x scale or need replay, we'd revisit Kafka. Right now, YAGNI—we're not gonna need it." That's the Staff answer. You name Kafka. You acknowledge its strengths. You reject it for stated, contextual reasons. You show you're not avoiding Kafka out of ignorance. You're choosing SQS out of fit.

---

## What Could Go Wrong? (Mini Disaster Story)

A candidate designed a URL shortener. Used a distributed database. Sharding. Read replicas. The interviewer asked: "Why this complexity?" The candidate said: "For scale." The interviewer: "What's your scale?" Candidate: "1000 URLs per day." The interviewer: "Could you simplify?" The candidate froze. They hadn't considered that 1000 URLs per day could run on a single PostgreSQL instance. A Raspberry Pi, almost. They over-engineered. And they didn't reject the complex solution. They defaulted to it. The fix: always ask about scale first. Then match the solution. "At 1000/day, I'd reject sharding—unnecessary. A single database. Maybe add Redis for hot URLs if read traffic grows. Start simple. Add complexity when we need it." Rejecting over-engineering is just as important as rejecting under-engineering.

---

## Surprising Truth / Fun Fact

In machine learning, there's a concept: the model that performs best is often the one that correctly rejects bad features. Feature selection matters. The same in system design. The best designs often come from engineers who correctly reject unnecessary complexity. "We don't need that" is a valid and valuable sentence. Staff engineers have the confidence to say it. They've seen systems over-engineered. They know the cost. Rejecting the wrong solution is a sign of experience. Say it out loud.

---

## Quick Recap (5 bullets)

- **Rejecting out loud** shows reasoning. As valuable as stating your choice.
- **Format:** "I considered X but rejected it because Y."
- **Common rejections:** Kafka (overkill for low volume), sharding (data fits in one node), strong consistency (not needed for feeds).
- **For every choice:** Ask "what's the alternative? Why not that?"
- **Match solution to problem:** Reject over-engineering. Reject under-engineering.

---

## One-Liner to Remember

**Saying what you rejected and why proves you evaluated—Staff-level thinking is visible in your eliminations, not just your selections.**

---

## Next Video

Next: scope creep in interviews. You have 45 minutes. If you try to design everything, you design nothing well. How to stay focused.
