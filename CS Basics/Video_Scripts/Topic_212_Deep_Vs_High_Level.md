# When to Go Deep vs When to Stay High-Level

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

You have 45 minutes. You could spend it going deep on every component. You'd cover nothing. Or you could stay surface-level everywhere. You'd show no depth. The art is knowing WHERE to go deep. The hardest part. The riskiest part. The most interesting part. Everything else? High-level. Move on.

---

## The Story

A museum guide leads a tour. Some rooms they walk through quickly. "These are landscape paintings from the 1800s. Notice the use of light." Thirty seconds. Move. Other rooms they stop. "This painting has a fascinating story. The technique—impasto—creates texture you can almost touch. The artist hid symbols in the composition. See here? And the backstory—they painted this during a personal crisis. Let me explain." Ten minutes. One room. You can't spend thirty minutes in every room. The tour would last days. You pick the MOST interesting ones. The ones with a story. The ones that reward depth.

System design is the same. Some parts are standard. Load balancer? High-level. "We'd use a load balancer for distribution." Done. CDN? "We'd put static assets on a CDN." Move. But the message delivery guarantees for a chat system? The consistency model for a payment system? The ranking algorithm for a feed? Those deserve depth. Go deep on the HARDEST, RISKIEST, MOST INTERESTING component. Stay high-level on the rest. The skill is choosing.

---

## Another Way to See It

Think of a book. Some chapters are summary. "The war lasted five years. Many died. The economy collapsed." Overview. Other chapters zoom in. "On the night of March 3rd, the general made a decision that would change everything. Here's the conversation. Here's the reasoning. Here's what went wrong." Detail. A book that's all summary is shallow. A book that's all detail never finishes. The best books alternate. So do the best designs. High-level for context. Deep for the critical path.

---

## Connecting to Software

**Go deep on:** The novel part—unique to this problem. The hardest scaling challenge. The consistency or correctness requirement. The failure mode that's non-obvious. The part the interviewer is probing. If they keep asking about it, go deeper. The part where trade-offs are interesting. "We could do X or Y—here's the analysis." That's where depth pays off.

**Stay high-level on:** Standard components. Load balancer. CDN. Basic caching. Well-known patterns. Things the interviewer isn't probing. "We'd use a load balancer to distribute traffic." Don't spend ten minutes on which load balancer. It's not the interesting part. Move. The skill is discrimination. Not everything deserves equal time.

**Signal it.** "I'll keep this at a high level since it's a standard pattern. Let me go deeper on X because that's where the interesting trade-offs are." You're telling the interviewer: I know what matters. I'm allocating my attention accordingly. That's a Staff signal. You're not just designing—you're curating the conversation.

---

## Let's Walk Through the Diagram

```
CHAT SYSTEM: WHERE TO GO DEEP?
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   COMPONENT              DEPTH?         WHY?                     │
│   ─────────────────────────────────────────────────────────     │
│   Load Balancer          High-level    Standard. Move on.       │
│   WebSocket manager      High-level    Well-understood.         │
│   API Gateway            High-level    Off-the-shelf.           │
│                                                                  │
│   Message delivery       DEEP ✓        Hardest: exactly-once,    │
│   guarantees                          ordering, failure.         │
│   Database schema        DEEP ✓        Consistency, sharding.   │
│   (messages, read path)                                           │
│                                                                  │
│   PICK ONE for full depth:                                        │
│   • Message delivery: idempotency, at-least-once vs exactly-once, │
│     partition ordering, dead letter                              │
│   OR                                                              │
│   • Schema: message table, read path, fan-out vs fan-on-write    │
│                                                                  │
│   Don't go deep on both at equal depth. One strong deep dive     │
│   beats two shallow ones. Choose the HARDEST.                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Chat system. Many components. Load balancer, WebSocket, gateway—high-level. Two candidates for deep dive: message delivery guarantees (the correctness problem) or database schema (the scale problem). Pick one. Go deep. Message delivery: idempotency, ordering, exactly-once, failure modes. That's twenty minutes of depth. Or schema: how do we store messages? Read path? Fan-out on write vs on read? Also twenty minutes. Don't do both at full depth—you'll run out of time. Pick the one that's harder, riskier, or more novel. That's the choice. Staff engineers make it explicitly.

---

## Real-World Examples (2-3)

**Example 1: Payment system.** High-level: API, database, audit log. Deep: the distributed transaction. How do we ensure exactly-once? Idempotency keys? Saga? Two-phase commit? What happens when the bank responds but we crash before persisting? That's the hard part. That's where you go deep. The rest is standard. The transaction orchestration is the interview.

**Example 2: Feed ranking.** High-level: ingestion, storage, serving. Deep: the ranking algorithm. Or the offline vs online pipeline. Or the cold-start problem. Pick one. "The interesting part here is ranking—we have real-time signals and batch signals. Let me detail how we'd combine them." That's depth. "We'd use a database" is not. Choose the component where the problem is non-trivial.

**Example 3: Rate limiter.** High-level: where it sits, what it limits. Deep: the algorithm. Token bucket vs sliding window. Distributed rate limiting—how do we sync across instances? Redis? Gossip? That's the hard part. The "we'd put a rate limiter in front" is high-level. The sync strategy is deep. One sentence vs ten minutes. Choose wisely.

---

## Let's Think Together

"Designing a chat system. Deep dive on: message delivery guarantees? WebSocket management? Database schema? Which ONE and why?"

**Message delivery guarantees** is the strongest choice. Why? It's the hardest correctness problem. At-least-once vs exactly-once. Idempotency. Ordering per conversation. What happens when the client disconnects mid-send? When the broker fails? When we have a partition? This is where chat systems go wrong in production. Going deep here shows you understand distributed systems. You'd cover: idempotency keys, deduplication, ordering guarantees, failure modes. Twenty minutes of rich discussion.

WebSocket management is more operational—connection handling, scaling connections. Important but more standard. Database schema is interesting—especially read path, fan-out—but delivery guarantees are the trickier correctness problem. When in doubt, pick the one that touches consistency, correctness, or failure. That's where Staff depth shows. Message delivery. Go deep there.

---

## What Could Go Wrong? (Mini Disaster Story)

A candidate designs a notification system. They go deep on the load balancer. "We'd use round-robin. Or maybe least connections. We could also consider consistent hashing for sticky sessions." Ten minutes. The interviewer's eyes glaze. Then: "What about delivery guarantees? How do you ensure a notification isn't lost?" The candidate: "We'd use a queue." "What kind? What happens if the consumer fails?" Shallow. They went deep on the wrong thing. The load balancer wasn't the hard part. The delivery semantics were. The lesson: going deep on the wrong component is worse than staying high-level everywhere. You've spent your depth budget on something that didn't matter. Choose the component that has the interesting problem. The one that keeps the interviewer engaged. That's the skill.

---

## Surprising Truth / Fun Fact

Interviewers often have a "deep dive" in mind when they give a problem. For "design a chat system," many want to hear about message delivery. For "design a rate limiter," many want to hear about the algorithm and distribution. If you go deep somewhere else—WebSocket scaling for chat, deployment topology for rate limiting—you might miss what they're probing for. How do you know? You can ask. "Is there a particular area you'd like me to go deeper on?" Or you can guess: usually it's the correctness problem, the scale problem, or the failure model. When unsure, pick the one that touches distributed systems fundamentals. That's rarely wrong.

---

## Quick Recap (5 bullets)

- **Go deep on:** The novel part. The hardest scaling challenge. Consistency/correctness. Non-obvious failure modes.
- **Stay high-level on:** Standard components. Load balancer. CDN. Well-known patterns. Things nobody is probing.
- **Pick one or two for depth.** Don't spread thin. One strong deep dive beats five shallow ones.
- **Signal it:** "I'll keep this high-level. Let me go deep on X—that's where the trade-offs are." Curate the conversation.
- **Wrong choice:** Going deep on the load balancer when delivery guarantees are the hard part. Allocate depth where it matters.

---

## One-Liner to Remember

**Go deep on the hardest part. Stay high-level on the rest. The skill is choosing where to invest your depth.**

---

## Next Video

That wraps up our Staff-level interview series. Check the playlist for more on system design at scale.
