# Rate Limiter: Single-Region Design

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

One data center. One region. Your API lives here. So does your rate limiter. The goal: every request gets checked in under 5 milliseconds. Allow or reject. No round trip to a distant database. We'll use Redis—in-memory, fast, built for this. Let's design the single-region rate limiter step by step.

---

## The Story

Designing a rate limiter for one region is like installing a water meter in one building. You don't need to coordinate with other cities. You just need a fast counter: how much has flowed this month? Same here. How many requests has this user made this minute? Redis holds the answer. INCR a key. EXPIRE it when the window ends. Atomic. Fast. Done.

---

## Another Way to See It

A parking garage with a counter at the entrance. Car enters: counter +1. Car leaves: counter -1. (Or we use a time window: counter resets every hour.) The guard checks: under 500? Welcome. Over 500? Full, come back later. Redis is that counter. The guard is our API gateway. Simple. The beauty of this design: no database. No disk. Just memory. Redis is built for exactly this pattern. INCR is atomic. EXPIRE sets the TTL. Combine them in a Lua script or use Redis 7's functions for multi-op atomicity. Under 1ms per check. Scales to tens of thousands of requests per second per Redis instance.

---

## Connecting to Software

**Architecture:** Client → API Gateway → Rate Limit Check (Redis) → Backend Service. The gateway intercepts every request. It extracts user_id or IP. It checks Redis: key = "rate_limit:user_123", value = count, TTL = 60 seconds. If count < limit: INCR, allow, pass to backend. If count >= limit: reject with 429. Redis operations: INCR and EXPIRE. Atomic. ~0.5ms per operation. Well under our 5ms budget.

---

## Response Headers

When you allow a request, tell the client how much they have left. **X-RateLimit-Limit:** 100. **X-RateLimit-Remaining:** 73. **X-RateLimit-Reset:** Unix timestamp when the window resets. If you reject: **Retry-After:** seconds until they can try again. These headers turn rate limiting from "mysterious 429" into "I know my usage." Better UX. Fewer support tickets.

---

## Let's Walk Through the Diagram

```
┌─────────┐     ┌──────────────┐     ┌─────────────────────────┐
│ Request │────►│ API Gateway  │────►│ Redis                   │
│ user_123│     │              │     │                         │
└─────────┘     │ 1. Extract   │     │ Key: rate:user_123      │
                │    user_id   │     │ Value: 47 (INCR)        │
                │              │     │ TTL: 45s               │
                │ 2. INCR key  │────►│                         │
                │              │     │ 47 < 100? → Allow       │
                │ 3. Check     │     │ 100+? → 429 Reject      │
                │    count     │     │                         │
                └──────────────┘     └─────────────────────────┘
                              │
                              ▼
                     ┌──────────────┐
                     │ Backend API  │ (if allowed)
                     └──────────────┘
```

For sliding window: use a sorted set. Add timestamp on each request. Remove entries older than window. Count remaining. Slightly more complex but more accurate. For fixed window: INCR + EXPIRE is enough.

---

## Fail Open vs. Fail Closed

Redis goes down. What now? **Fail open:** Allow all requests. Risk: no protection during outage. Your API might get hammered. **Fail closed:** Reject all requests. Risk: your entire API is down. Most systems choose fail open. Why? A temporary overload is better than a total outage. You can add circuit breakers, fallback to a local cache, or degrade gracefully. Document the choice. Test it. Run a chaos experiment: kill Redis. Observe. Does your system fail open? Good. Does it crash? Bad. Does it reject everything? Maybe acceptable for strict compliance. Know your behavior before production.

---

## Real-World Examples

**Vercel** uses Upstash Redis for edge rate limiting—Redis with a REST API, works at the edge. **Kong** ships with a Redis-based rate limiting plugin. **AWS API Gateway** has built-in throttling; behind the scenes, it's a distributed counter. Same pattern: fast key-value store, increment, check, allow or deny.

---

## Let's Think Together

**"Redis is a single point of failure. What happens if it goes down? How do you add redundancy?"**

Redis Sentinel: automatic failover. Primary dies, replica promotes. A few seconds of downtime. Redis Cluster: shards data; one node failure doesn't kill the cluster. For rate limiting, losing a few seconds of counts is usually acceptable. Or: run Redis in read-replica mode; writes go to primary, reads can hit replicas. The critical path is the INCR—must be consistent. Replicas help read scaling, not write redundancy. For true redundancy: multi-node Redis Cluster or accept brief fail-open during failover. Redis Cluster shards data. One node failure does not take down the cluster. Use it when you need high availability. Redis Sentinel gives you automatic failover for a single primary-replica pair. Simpler. For rate limiting, losing counts during a 10-second failover is acceptable. Most systems choose Sentinel or a managed Redis (ElastiCache, Redis Cloud) and accept the risk. Document it. Monitor it. Alert on Redis latency. Alert on memory. Alert on key count. Rate limiting is critical infrastructure. Treat it like your database. Backup config. Run drills. When Redis goes down, you want to know in seconds, not minutes.

---

## What Could Go Wrong? (Mini Disaster Story)

Redis memory fills up. Millions of keys—one per user per window. No TTL set correctly on a code path. Keys never expire. Redis runs out of memory. Crashes. Your rate limiter fails open. Attackers notice. They hammer your API. You're down. Lesson: always set TTL. Monitor key count. Use key eviction policies (volatile-lru) as a safety net. Treat Redis like a precious resource—don't leak keys.

---

## Surprising Truth / Fun Fact

A single Redis instance can handle 100,000+ operations per second. For rate limiting, each check is 1–2 ops (INCR, maybe EXPIRE). One Redis node can serve 50,000+ rate limit checks per second. That's often enough for an entire region. The bottleneck is rarely Redis—it's your gateway and network.

---

## Quick Recap

- Single-region design: API Gateway → Redis → Allow/Reject.
- Redis: key = user_id or IP, value = count, TTL = window; INCR + EXPIRE.
- Response headers: X-RateLimit-Limit, Remaining, Reset, Retry-After.
- Redis failure: usually fail open; use Sentinel or Cluster for redundancy.
- Always set TTL; monitor memory; avoid key leaks.

---

## One-Liner to Remember

*Redis holds the count, the gateway checks it—INCR, compare, allow or 429—and when Redis fails, fail open.*

---

## Next Video

Next: distributed cache. One Redis isn't enough for a global system. How do we scale cache across nodes? Let's explore.
