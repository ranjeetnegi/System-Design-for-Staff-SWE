# What Interviewers Probe at Staff Level

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Two interviews. Same company. Same question: "Design a URL shortener." L5 interview: they want to see a correct architecture. You draw load balancer, service, database. You mention caching. They nod. You pass. L6 interview: SAME question. But the interviewer probes. "Why not a different database?" "What happens at 100x scale?" "How would you handle a region failure?" "What's the operational cost?" "How does this affect other teams?" At Staff level, the QUESTIONS are harder. And the bar isn't just the design—it's how you handle the probes. Depth. Trade-offs. Failure modes. That's what they're testing.

---

## The Story

Imagine two chess games. Amateur game: you make legal moves. You don't blunder. You might win. Grandmaster game: every move is questioned. "Why not the knight?" "What if they push the pawn?" "How do you handle the endgame?" The same board. Different depth of analysis. At Staff level, the interviewer is the grandmaster. They're not just checking if you know the moves. They're checking if you understand the consequences. The alternatives. The risks. One correct answer isn't enough. You need to show you've thought through the space.

---

## Another Way to See It

Think of a medical exam. Junior doctor: "Patient has fever. Prescribe rest and fluids." Correct. Senior specialist: "Why fever? Infection? Inflammation? Autoimmune? What are the differential diagnoses? What tests rule them out? What's the risk of each treatment?" Same patient. Different depth. The Staff interview is the specialist exam. Surface answers don't pass. You need to show reasoning. Alternatives. Trade-offs.

---

## Connecting to Software

**What interviewers look for at Staff level.** Six dimensions:

**(1) Trade-off articulation.** Not just "we use Redis." But "we use Redis for caching because latency is critical and our read pattern is hot-key. We considered Memcached but rejected it because we need persistence for session data." You name the trade-off. You explain the choice.

**(2) Depth beyond the surface.** "We use a database" becomes "we use PostgreSQL with read replicas. Writes go to primary. Reads can hit replicas with eventual consistency. We'd add sharding by user_id if we exceed 1TB." You go deeper. You show what you'd do at scale.

**(3) Failure mode awareness.** "What breaks at 10x?" "What happens when the database fails?" "What's the blast radius?" They want to hear: timeouts, circuit breakers, fallbacks. They want to know you've thought about what goes wrong.

**(4) Cost consciousness.** "What's the operational cost?" "How many engineers to run this?" "What's the cloud bill at 1M users?" Staff engineers think about total cost. Not just technical correctness.

**(5) Organizational impact.** "How would another team integrate?" "What APIs would you expose?" "What's the contract?" Systems don't exist in isolation. Staff engineers consider the ecosystem.

**(6) Operational readiness.** "How would you monitor this?" "What alerts?" "How do you debug when it breaks?" They want to see you've run systems. Not just designed them.

**Common probes.** "Why this and not that?" "What breaks at 10x scale?" "How would you monitor this?" "What's the blast radius if this fails?" "How would another team integrate with this?" "What's the migration path from the current system?" Each probe tests a dimension. Your job: show you've thought about it. Even if you don't have the perfect answer, show your reasoning.

**The difference.** L5 gets credit for a working design. Correct components. Reasonable flow. L6 gets credit for explaining WHY this design over alternatives. What risks remain. How to evolve it. What you'd do with more time. The bar is reasoning. Not memorization.

---

## Let's Walk Through the Diagram

```
STAFF INTERVIEW: WHAT THEY PROBE
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   YOUR DESIGN                                                     │
│        │                                                         │
│        ├── "Why this DB?"     → Trade-off articulation           │
│        ├── "What at 10x?"    → Depth, scalability thinking      │
│        ├── "What breaks?"    → Failure mode awareness            │
│        ├── "What's the cost?"→ Cost consciousness               │
│        ├── "Other teams?"    → Organizational impact             │
│        └── "How monitor?"    → Operational readiness             │
│                                                                  │
│   L5 BAR: Correct design ✓                                       │
│   L6 BAR: Correct + WHY + Risks + Evolution                      │
│                                                                  │
│   One right answer = L5                                          │
│   Right answer + reasoning + alternatives = L6                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: They probe every dimension. Trade-offs. Scale. Failure. Cost. Org. Ops. Your design is the start. Their questions are the test. L5: design works. L6: you explain why, what could go wrong, how it evolves. The diagram shows the probes. Your response to each probe is the signal.

---

## Real-World Examples (2-3)

**Probe: "Why PostgreSQL and not MongoDB?"** L5 answer: "PostgreSQL is reliable." Staff answer: "We need ACID for financial data. Strong consistency. PostgreSQL gives us that. We considered MongoDB for flexibility but rejected it because our schema is well-defined and we need joins. At scale we might shard by user_id. PostgreSQL supports that. MongoDB would too, but our team has PostgreSQL expertise. Operational fit matters."

**Probe: "What happens when the cache fails?"** L5 answer: "We'd lose performance." Staff answer: "Cache failure means we thump the database. We need a circuit breaker—if cache error rate exceeds 5%, we stop writing to cache, serve from DB. We'd add fallback: maybe a local in-memory cache per instance. We'd alert on cache hit rate. We'd have runbooks. The system degrades, doesn't collapse."

**Probe: "How would the billing team integrate?"** L5 answer: "They'd call our API." Staff answer: "We'd expose an events API. Order created, order fulfilled. They subscribe. Or we'd have a batch sync for historical data. The contract would be versioned. We'd own backward compatibility. We'd document the SLA. They need billing within 24 hours—eventual is fine. We'd design for that."

---

## Let's Think Together

**"You design a chat system. Interviewer asks: 'What happens when your WebSocket servers run out of memory?' How do you respond?"**

Don't panic. Think out loud. "We'd have memory limits per connection. If we approach the limit, we'd stop accepting new connections—return 503. We'd have monitoring on memory usage. Alert at 80%. We might implement connection shedding—drop the least active connections first. We'd also look at the root cause—maybe a message size limit, maybe we need to move to a different architecture like a message queue for heavy payloads. We'd have a runbook. Scale up or scale out. The key is: we don't let one server's OOM take down the cluster. Bulkheads." That's the Staff answer. You don't just say "we'd fix it." You reason through the failure. You name specific mitigations.

---

## What Could Go Wrong? (Mini Disaster Story)

A candidate designed a good system. Clean. Reasonable. The interviewer asked: "What happens when your primary database goes down?" The candidate said: "We'd fail over to the replica." The interviewer: "How long does that take?" Candidate: "A few minutes?" The interviewer: "What do users see during those minutes?" Candidate: "Errors?" The interviewer: "Could you do better?" Silence. The candidate hadn't thought about it. They had the right components. But they didn't have the failure-mode depth. They didn't pass. The fix for the candidate: always ask yourself "what happens when X fails?" before the interview. For every component. Database. Cache. Load balancer. Write the failure scenarios. Practice describing them. Staff bar includes operational awareness. Not just design.

---

## Surprising Truth / Fun Fact

Many Staff-level interviewers say: the best signal isn't the initial design. It's how the candidate handles the first "why" or "what if" question. Do they get defensive? Do they make something up? Or do they think out loud, consider alternatives, and reason from first principles? The probe is designed to stress-test reasoning. There's often no single "right" answer. The right answer is: thoughtful, structured reasoning. Showing you can handle ambiguity. That's the Staff skill.

---

## Quick Recap (5 bullets)

- **Staff probes:** Trade-offs, depth, failure modes, cost, org impact, operational readiness.
- **Common questions:** "Why this not that?" "What at 10x?" "What breaks?" "How monitor?"
- **L5 bar:** Correct design. L6 bar: Correct + WHY + risks + evolution.
- **Respond to probes:** Think out loud. Reason. Name alternatives. Don't freeze.
- **Practice:** For every component, ask "what happens when it fails?"

---

## One-Liner to Remember

**At Staff level, the design is the prompt—the probes are the test; show reasoning, trade-offs, and failure awareness.**

---

## Next Video

Next: rejecting the wrong solution out loud. Why saying what you DIDN'T choose is as valuable as what you chose.
