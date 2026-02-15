# Global Rate Limiter: Distributed Counting

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Multiple toll booths across a highway. Each counts cars independently. Rule: max 1000 cars per hour total. Booth A counts 400. Booth B counts 400. Booth C counts 400. Total: 1200. Over limit. But each booth thought they were under. The booths don't talk to each other. Distributed counting—that's the core challenge of global rate limiting. Simple when you have one counter. Impossible when you have many. Unless you coordinate. Let's figure out how.

---

## The Story

Single server: easy. One counter. 100 requests? Increment. At 1000? Reject. One place. One source of truth. But you have 10 servers. 100 servers. Each gets a portion of traffic. User hits server 1. Server 1 increments. User hits server 2. Server 2 increments. They don't share. User could make 100 requests to server 1, 100 to server 2, 100 to server 3. Each server says "under limit." Total: 300. Your limit was 100. You're 3× over. Distributed counting breaks naive rate limiting. You need coordination. Shared state. Or clever approximations. This is a staff-level problem. Not "how do I rate limit?" but "how do I rate limit correctly when traffic is scattered across N servers?" The answer shapes your architecture. Get it wrong, and your limit is a suggestion. Get it right, and you have a real guarantee.

---

## Another Way to See It

Multiple bank branches. Each allows withdrawals. Limit: Rs 50,000 per day per customer. Branch A doesn't know what Branch B did. Customer withdraws Rs 50,000 at A. Goes to B. Withdraws another Rs 50,000. Total: Rs 100,000. Limit violated. Branches need a shared ledger. Or a central system. Same for rate limiting. Servers need to agree on the count. No shared truth = no real limit. The analogy is exact. Money. Requests. Same problem. Same need for coordination.

---

## Connecting to Software

**The problem.** N servers. Each enforces a portion of the limit. Without coordination, sum of local counts can exceed the global limit. User rotates through servers. Each allows. Total exceeds. Solution: shared state. Or accept approximation. There's no magic. Physics. Information has to flow. Either every request checks central (latency) or servers approximate (inaccuracy). Choose.

**Solution 1: Centralized counter.** Redis. Key: user_id or IP. Value: count. INCR on each request. EXPIRE for window. Every server checks Redis before allowing. One source of truth. Accurate. But: Redis is a bottleneck. Every request = one Redis round-trip. 100K QPS? 100K Redis ops/sec. Possible with Redis Cluster. But adds 1-5ms latency per request. Trade-off: accuracy for latency. For billing, quota, abuse—you often pay the latency. For general API protection—maybe you don't.

**Solution 2: Local counters with periodic sync.** Each server counts locally. Every 5 seconds, sync to central store. "Server 1 used 50 for user X. Server 2 used 30." Central aggregates. Approximate. Off by up to N × budget_per_sync. If each server can allow 20 per 5 seconds before sync, total over-limit could be 20 × N. Fast. No per-request Redis call. Slightly inaccurate. Acceptable for most cases. DDoS mitigation? Fine. Billing? No.

**Solution 3: Token bucket in Redis with Lua.** Atomic. Check and decrement in one round-trip. Lua script: if tokens > 0, decrement, return allow. Else return deny. Reduces two calls to one. Still centralized. Still Redis dependency. But fewer round-trips. Lua runs on Redis. One network hop. Optimize what you can. Lua is your friend.

**Partitioning.** Limit 1000/min per user. 10 servers. Partition: 100/min per server? Risky. Traffic uneven. Server 1 gets 500 requests. Server 2 gets 50. Server 1 rejects. Server 2 underutilized. Partitioning by user_id hash: user always hits same server. Consistent. But that server becomes hot for that user. Global limit still needs coordination. No free lunch. Partitioning spreads load. It doesn't eliminate the coordination problem. It changes its shape.

---

## Let's Walk Through the Diagram

```
GLOBAL RATE LIMITER - DISTRIBUTED COUNTING
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   OPTION A: CENTRALIZED (Redis)                                  │
│                                                                  │
│   [Server 1]──┐                                                  │
│   [Server 2]──┼──► INCR user_id ──► Redis ──► Count > limit?     │
│   [Server 3]──┘         │                          │             │
│                         │                    Yes → 429            │
│                         └── No → Allow                            │
│   Accurate. One Redis call per request. Latency cost.            │
│                                                                  │
│   OPTION B: LOCAL + SYNC                                         │
│                                                                  │
│   [Server 1] Local count ──┐                                     │
│   [Server 2] Local count ──┼──► Sync every 5s ──► Central       │
│   [Server 3] Local count ──┘         │                           │
│                                     Approximate. Fast.           │
│                                                                  │
│   Traffic: 10 servers. Limit 1000/min. How to partition?         │
│   Hash user_id → same server? Or shared counter?                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Centralized: every request hits Redis. Accurate. Latency. Local sync: count locally, sync periodically. Fast. Approximate. Partition by user? Consistent but hot spots. Global limit needs shared state. No way around it. The diagram shows the options. Your context picks the winner. Staff engineers don't pick by default. They pick by requirement. Measure. Then decide.

---

## Real-World Examples (2-3)

**Stripe.** Global rate limits. Redis-based. Per-request check. They need accuracy for billing. Latency acceptable. Centralized wins. When money is involved, approximate doesn't cut it. They've scaled Redis. You can too.

**Cloudflare.** Rate limiting at the edge. Distributed. Approximate counting. Fast. Slightly over limit sometimes. DDoS protection. Approximate is fine. Block the worst. Don't need exact. Different use case. Different solution.

**Kong.** Plugins for Redis-based rate limiting. Supports multiple strategies. Centralized by default. Open source. You can see how they do it. Learn from the implementation.

---

## Let's Think Together

**"Rate limit: 1000/min per user. 10 servers. How to partition? 100/min per server? What if traffic isn't evenly distributed?"**

100 per server is naive. User makes 200 requests. All hit server 1. Server 1 rejects 100. But global count is 200. Under limit. You're rejecting valid traffic. Unfair. User paid for 1000. They got 100. Better: don't partition the limit. Use centralized counter. Or: hash user to one server. That server owns the full 1000 for that user. Even distribution of users, not requests. Server 1 gets user A, B, C. Server 2 gets D, E, F. Each server enforces 1000 for its users. No cross-server coordination. But: one user's traffic = one server. Burst on that server. Trade-offs. No perfect answer. Context. Load distribution. User behavior. All factor in. Staff engineers hold these trade-offs in their head. They don't memorize answers. They reason from first principles.

---

## What Could Go Wrong? (Mini Disaster Story)

A company uses local counters. No sync. "Rate limit 100/min per user." 10 servers. User sends 100 requests. Load balancer round-robins. 10 per server. Each server: count 10. Under 100. Allow all. User gets 100. Fine. User sends 1000. 100 per server. Each allows. User gets 1000. Limit violated 10×. Attackers discover. Abuse. No central coordination. Local limits only. Global limit was imaginary. Distributed rate limiting without shared state is security theater. You feel safe. You're not. The fix: centralize. Or sync. Or accept that you have a soft limit. But don't claim a hard limit when you don't have one. Honesty in system design. Users and attackers will test it. They'll find the gap.

---

## Surprising Truth / Fun Fact

Redis INCR is atomic. Multiple servers INCR the same key. No lost updates. No race. One operation. That's why Redis dominates rate limiting. Simple. Correct. The challenge isn't the increment—it's the latency of a round-trip for every request. That's why people try local+sync. But Redis is fast. 1ms. For most APIs, acceptable. Don't optimize away Redis until you've measured. Premature optimization is the enemy. Measure. Then optimize. Redis might be fine. It often is.

---

## Quick Recap (5 bullets)

- **Problem:** N servers, each counting. Without coordination, total exceeds limit.
- **Centralized:** Redis INCR. Accurate. 1-5ms per request. Possible bottleneck.
- **Local + sync:** Approximate. Fast. Off by sync period × N servers.
- **Partition by user:** User → one server. That server enforces. No cross-server coordination for that user.
- **No shared state = no global limit.** Local limits only. Attackers can exceed.

---

## One-Liner to Remember

**Global rate limiting is toll booths that need to share a counter—centralized is accurate, distributed is fast but approximate.**

---

## Next Video

Next: consistency vs latency. When accurate matters. When approximate is fine. The trade-offs.
