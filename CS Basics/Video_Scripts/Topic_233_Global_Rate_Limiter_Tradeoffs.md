# Global Rate Limiter: Consistency vs Latency

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Strict vs lenient traffic police. Strict: every car checked against the GLOBAL count before allowed. Accurate. But checking takes time—traffic jams. Lenient: each officer estimates locally. Fast. But some roads get more traffic than allowed. Consistency vs latency. The fundamental trade-off. You can't have perfect both. Choose.

---

## The Story

You want a global rate limit. 1000 requests per minute per user. Two goals: accuracy (never exceed 1000) and speed (don't add latency). They conflict. To be accurate, every request must check a shared counter. That's a network round-trip. Redis. 1-5ms. Multiply by requests. At 100K QPS, that's 100K Redis operations per second. Doable. But expensive. And latency adds up. To be fast, each server allows based on local info. No round-trip. Sub-millisecond. But local info is stale. Approximate. You might allow 5% over. Or 10%. Depends on sync frequency and traffic patterns.

Most systems choose approximate. "Allow up to 1050 instead of 1000" is acceptable for API protection. "Allow 1001" for billing? Not acceptable. Context matters. Staff engineers make this call deliberately.

---

## Another Way to See It

A concert with 1000 tickets. Strict: every entry, guard checks central system. "Tickets left?" Accurate. Slow. Long line. Lenient: each gate has a local count. "We've let in 200. Assume 800 left." Fast. But what if all gates think 800 left? You oversell. Strict = accuracy, queue. Lenient = speed, risk. Same trade-off.

---

## Connecting to Software

**Strict consistency.** Centralized check per request. Redis GET, INCR, EXPIRE. Or Lua script: check-and-increment atomically. Every request waits for Redis. Accurate. Adds 1-5ms. At 100K QPS, 100K Redis ops/sec. Redis can do 100K. But it's one more dependency. One more point of failure. Redis down? Fail-open (allow) or fail-closed (reject all)? Usually fail-open for availability. But then you have no rate limiting when Redis is down. Trade-offs.

**Approximate counting.** Local counters. Sync every 5 seconds. Or: each server gets a budget. "You can allow 100/min. When you've used 80, request more from central." Token distribution. Central dispenses tokens in batches. Servers use locally. Fewer round-trips. Approximate. Off by one batch size. Fast. No per-request latency.

**When strict?** Billing. Abuse prevention. Compliance. "This user must not exceed 1000 API calls. Ever." Accuracy required. Pay the latency. When approximate? General API protection. "We don't want any user to overwhelm us." 5% over is fine. DDoS mitigation. "Block obvious attacks." Approximate is enough. Choose by use case.

**Tolerance.** "100/min with 5% tolerance" = allow up to 105. User sends 105. All get through. Is that acceptable? For API fairness, usually yes. For quota billing, no. Document your tolerance. Users should know.

---

## Let's Walk Through the Diagram

```
CONSISTENCY VS LATENCY TRADEOFF
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   STRICT (Consistency)              APPROXIMATE (Latency)         │
│                                                                  │
│   Request ──► Redis ──► Allow/Deny   Request ──► Local ──► Allow │
│        │         │                         │        │           │
│        └─ 1-5ms ─┘                         └─ &lt;1ms ─┘           │
│                                                                  │
│   ✓ Accurate                       ✓ Fast                        │
│   ✓ Never over limit               ✓ No per-request RTT         │
│   ✗ Latency                        ✗ May over-allow              │
│   ✗ Redis bottleneck               ✗ Sync lag                   │
│                                                                  │
│   DECISION MATRIX:                                                │
│   Billing / Quota → Strict                                        │
│   API protection → Approximate                                    │
│   Abuse prevention → Depends on cost of over-allowing             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Strict: every request hits Redis. Accurate. Slower. Approximate: local decision. Fast. May over-allow. Billing needs strict. API protection often fine with approximate. Know your requirements.

---

## Real-World Examples (2-3)

**Stripe billing.** Strict. Every API call counts toward quota. Can't over-count. Can't under-count. Latency acceptable. Centralized.

**Twitter API.** Tiered limits. Approximate for free tier. Strict for enterprise. Pay more, get accuracy.

**AWS API Gateway.** Rate limits per account. Approximate. Protects from runaway costs. Slightly over? Acceptable. Billing is separate.

---

## Let's Think Together

**"A user is rate-limited at 100/min. Your system has 5% tolerance. They send 105. Is this acceptable? When is it NOT?"**

For API protection: acceptable. 105 vs 100. Marginal. User didn't crash your system. For quota billing: not acceptable. User pays for 100. You allowed 105. You eat the cost. Or you overcharge. Both bad. For abuse: depends. 105 requests from one user? Probably fine. 105 from a bot that would have sent 10,000? You blocked 99%. Tolerance is a product decision. Document it. Enforce it consistently.
**Choosing your stance.** Staff engineers make this decision explicitly. Document it. Our rate limiter allows up to 5% over the stated limit for availability. For billing endpoints, we use strict consistency. Everyone on the team should know. New engineers should read it. The choice has implications for cost, latency, and fairness. There is no free lunch. Only informed trade-offs. Embrace the nuance.


---

## What Could Go Wrong? (Mini Disaster Story)

A company uses approximate rate limiting. Fine for years. They add a paid tier. "1000 API calls per month." Same rate limiter. Approximate. User gets 1050. Complains. "I paid for 1000." Support: "Our system has tolerance." User: "I was charged for 1000." Legal gets involved. The rate limiter was built for protection. Not billing. Billing needs strict. They had to build a second, accurate system for quota. Two rate limiters. Complexity. Lesson: match the implementation to the use case. Don't reuse "close enough" for "exact."

---

## Surprising Truth / Fun Fact

Some rate limiters fail open. Redis down? Allow all requests. Better to stay up than to block everyone. Others fail closed. Redis down? Reject all. Better to be unavailable than to let attackers in. The choice depends on threat model. Consumer app? Fail open. Security-critical? Fail closed. There's no universal answer. Staff engineers decide based on context. When in doubt, default to fail-open for user-facing APIs. Blocking all traffic is worse than allowing some extra. But for billing or security boundaries, fail-closed protects the business. Document your choice. Put it in the runbook.

---

## Quick Recap (5 bullets)

- **Strict:** Centralized check. Accurate. 1-5ms latency. Redis dependency.
- **Approximate:** Local counters, sync. Fast. May over-allow 5-10%.
- **When strict:** Billing, quota, compliance.
- **When approximate:** API protection, DDoS mitigation.
- **Tolerance:** Document it. 5% over for protection is often OK. Never for billing.

---

## One-Liner to Remember

**Consistency vs latency: strict is accurate but slow, approximate is fast but fuzzy—choose by use case.**

---

## Next Video

Next: distributed cache across regions. Same "consistency vs speed" story at global scale.
