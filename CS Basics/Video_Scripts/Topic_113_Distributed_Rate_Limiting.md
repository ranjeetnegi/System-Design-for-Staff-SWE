# Distributed Rate Limiting: The Challenge

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

One security guard at one door. Easy. He counts. "47 people in. 100 max. 53 spots left." Simple. But now the club has five doors on five different streets. Each door has its own guard. Same rule: "Max 100 people total." Guard at door 1 lets in 80. Guard at door 5 lets in 80. Total: 160. Over limit. The guards don't talk to each other. They don't share a count. That's **distributed rate limiting**. Multiple servers. Each counts independently. The total is wrong. Solving it is hard. Let me show you how.

---

## The Story

With one server, rate limiting is trivial. In-memory counter. Request arrives. Increment. Check. Allow or deny. With multiple servers behind a load balancer, each server has its own memory. Server 1 gets 50 requests. Counter: 50. Server 2 gets 50 requests. Counter: 50. Server 3 gets 50. Counter: 50. Total: 150. Limit was 100. Each server thought it was fine. The system exceeded the limit. The rate limiter state—the counters—must be **shared** across all servers. But sharing means network calls. Latency. A single point of coordination. The challenge: consistency vs performance. Strict counting = centralized store = slower. Approximate counting = local counters = faster but wrong sometimes. Most systems tolerate slight over-counting. Better to allow a few extra than to block legitimate users with false positives.

---

## Another Way to See It

Think of five cash registers in a store. Rule: "Max 100 discounted items per customer per day." Each register has its own tally. Customer buys 20 at register 1. 20 at register 2. 20 at register 3. 20 at register 4. 20 at register 5. Total: 100. Each register thought 20 was fine. But what if the limit was 50? Each would allow 50. Total: 250. The registers need to share a count. Or think of multiple toll booths. "100 cars per hour from this town." Each booth counts. Without sharing, 5 booths = 500 cars. Central system = one count. Shared. Accurate. Slower. Distributed rate limiting is the toll booth problem at scale.

---

## Connecting to Software

**Solution 1: Centralized counter in Redis.** All servers check and increment the same key. User 123: key = "ratelimit:user:123". INCR. EXPIRE. Check if count > limit. Atomic. Simple. All servers hit Redis. Redis becomes the bottleneck. Single point of failure. If Redis goes down, rate limiting fails. Usually "fail open"—allow traffic when Redis is down. Or "fail closed"—reject. Trade-off.

**Solution 2: Local counters with periodic sync.** Each server counts locally. Every N seconds, sync the count to a central store. Fast—no Redis call per request. But inaccurate. Between syncs, each server might allow 100. Total: 500. Over limit. Good for "approximately 100" use cases. Not for strict limits.

**Solution 3: Sliding window in Redis with Lua.** Redis can run Lua scripts atomically. Multi-key operations. Sliding window logic in one round trip. Accurate. Still centralized. Still Redis. But fewer round trips than naive INCR. Used in production. Redis is fast. For most systems, it's fine.

**Consistency vs performance**: Strict = Redis every request. Slow but correct. Approximate = local + sync. Fast but can exceed. Choose based on how strict your limit must be. Login attempts? Strict. API throughput? Approximate might work.

---

## Let's Walk Through the Diagram

```
    THE DISTRIBUTED PROBLEM

    ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐
    │Server 1 │  │Server 2 │  │Server 3 │  │Server 4 │  │Server 5 │
    │count: 80│  │count: 80│  │count: 80│  │count: 80│  │count: 80│
    └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘
         │            │            │            │            │
         │  Each thinks: "80 < 100, allow"       │            │
         │            │            │            │            │
         └────────────┴────────────┴────────────┴────────────┘
                              │
                     Total: 400. Limit was 100!


    SOLUTION: SHARED STORE (Redis)

    ┌─────────┐  ┌─────────┐  ┌─────────┐
    │Server 1 │  │Server 2 │  │Server 3 │
    └────┬────┘  └────┬────┘  └────┬────┘
         │            │            │
         └────────────┼────────────┘
                      │
                      ▼
              ┌───────────────┐
              │    REDIS     │
              │ user:123 = 95│  ← Single source of truth
              └───────────────┘
              All servers check same counter. Accurate.
              But: Redis = bottleneck + SPOF.
```

---

## Real-World Examples (2-3)

**Example 1: Kong API Gateway.** Rate limiting plugin. Uses Redis for distributed counters. All Kong nodes share state. Production-ready. **Example 2: Envoy proxy.** External rate limit service. Envoy calls a gRPC service. That service uses Redis. Centralized. Scales the service. **Example 3: Custom implementation.** Redis INCR with Lua for sliding window. Key per user per window. Atomic. Used by many companies. Standard pattern.

---

## Let's Think Together

Rate limit: 1000 requests per minute per user. You have 10 servers. Each server allows 100 per minute locally. User sends 100 to each server. Total: 1000. Correct! But what if traffic isn't evenly distributed?

User sends 500 to server 1. 500 to server 2. Zero to others. With local limits of 100 each, server 1 allows 100, rejects 400. Server 2 allows 100, rejects 400. Total allowed: 200. But the user's true total for the minute is 1000. They should get 1000. They only got 200. Uneven distribution + local limits = undercounting. Some servers are "wasted" (they have quota left). Others are maxed. With shared Redis, the total is 1000. First 500 to server 1: all allowed (count goes 0→500). Next 500 to server 2: all allowed (500→1000). Request 1001: denied. Fair. Shared store handles uneven distribution. Local limits don't.

---

## What Could Go Wrong? (Mini Disaster Story)

A company runs 20 API servers. No shared rate limit. Each has local limit: 1000 req/min per user. A user sends 1000 to each server. 20,000 requests total. All allowed. The database gets hammered. Query timeout. Cascade failure. The company thought they had rate limiting. They did—per server. Not globally. The fix: Redis. Shared counter. Now 20,000 requests from one user = 20,000 hits to Redis for that key. Count exceeds 1000. Rest denied. Problem solved. But Redis load went up. They had to scale Redis. Monitor it. Distributed rate limiting adds operational complexity. Worth it. But plan for it.

---

## Surprising Truth / Fun Fact

Cloudflare rate-limits across 300+ data centers worldwide. They can't send every request to a central counter—latency would be huge. They use a combination: local counting at the edge, periodic synchronization to regional aggregators, and eventual consistency. Slight overcounting possible. But for DDoS protection, "approximately 1000" is good enough. Block the attacker. Don't block real users. Engineering at scale means "perfect" sometimes loses to "good enough and fast."

---

## Quick Recap (5 bullets)

- **Problem**: Multiple servers, each with own counter. Total exceeds limit. Guards don't talk.
- **Solution 1**: Redis. Centralized counter. All servers check same key. Accurate. Redis = bottleneck.
- **Solution 2**: Local counters + periodic sync. Fast. Approximate. Can exceed limit between syncs.
- **Solution 3**: Redis + Lua for sliding window. Atomic. Fewer round trips. Production pattern.
- **Trade-off**: Consistency (strict) vs performance (fast). Most tolerate slight over-counting.

---

## One-Liner to Remember

**Distributed rate limiting: Share the count or get it wrong. Redis is the usual answer. Plan for the bottleneck.**

---

## Next Video

We've covered auth, sessions, tokens, OAuth, rate limiting. What's next in system design? Stay tuned for the next section.
