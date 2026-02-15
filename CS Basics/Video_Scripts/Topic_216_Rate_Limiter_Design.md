# Rate Limiter: Problem and Algorithms

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Picture a water tap. Turn it on full blast, and the tank empties. Everyone's dry. A rate limiter is a *valve*—it controls how much water flows. In APIs, it controls how many requests a user or IP can make per time window. Protect from abuse. Protect from overload. We've covered algorithms before—token bucket, sliding window. Now let's design the *system*. Where does it sit? How does it scale? Let's build it together.

---

## The Story

You run an API. A developer integrates it. Great. Then a bug in their code triggers a loop. 10,000 requests per second. Your servers melt. Or worse: a malicious actor probes for weaknesses, scraping every endpoint. Your database screams. Your bill spikes. A rate limiter says: "You get 100 requests per minute. After that, wait." It's not punishment. It's protection—for you and for fair users. Everyone gets a fair share of the tap.

---

## Another Way to See It

Like a nightclub bouncer. The club has a capacity. The bouncer counts: 50 inside, 50 waiting. One person leaves, one enters. No stampede. No fire hazard. The rate limiter is the bouncer—it enforces capacity. Not to be mean. To keep the system safe.

---

## Connecting to Software

**What we need:** Check if a request is within the limit. If yes, allow it. If no, return 429 Too Many Requests. Low latency: the check must add under 5 milliseconds. Support per-user limits (authenticated) and per-IP limits (anonymous). Global limits too—total API capacity.

**Algorithm recap:** **Token bucket**—tokens refill at a rate; burst-friendly. **Sliding window**—counts requests in a rolling window; accurate. **Fixed window**—counts per calendar window (e.g., per minute); simple but can double-count at boundary. Pick based on accuracy vs. simplicity. Token bucket: good for APIs with bursty traffic. Sliding window: when you need strict fairness. Fixed window: when you want the simplest implementation. Many systems start with fixed window and upgrade later. The placement decision matters more than the algorithm in early stages.

---

## Let's Walk Through the Diagram

```
┌─────────┐                    ┌─────────────────────┐
│ Client  │───────────────────►│   API Gateway       │
│ Request │                    │                     │
└─────────┘                    │  ┌───────────────┐  │
                               │  │ Rate Limiter  │  │
                               │  │ Check         │  │
                               │  └───────┬───────┘  │
                               │          │          │
                               │    Allow │ Reject   │
                               │          │ (429)    │
                               │          ▼          │
                               │  ┌───────────────┐  │
                               │  │ Backend API   │  │
                               │  └───────────────┘  │
                               └─────────────────────┘
```

The rate limiter sits at the edge. Before your backend sees the request. Fast path: check → allow/reject. No request reaches your app if it's over limit. That saves CPU, DB, everything. Rejecting at the edge means the attacker never touches your application servers. Your database never sees the request. Your billing stays under control. Rate limiting is not just protection; it is cost control and fairness. Every legitimate user gets their fair share.

---

## Real-World Examples

**Stripe** limits by endpoint: 100 reads per second per API key. **Twitter** limits tweets, API calls, and DMs per account. **GitHub** limits unauthenticated requests to 60/hour and authenticated to 5,000/hour. Each tunes limits to their product. The mechanism is the same: count, compare to limit, allow or deny. Implement at the API gateway for maximum efficiency. Reject before the request hits your application. Saves resources. Protects downstream services. Rate limiting is defense in depth: even if an attacker bypasses one layer, the gateway is the first line. Low latency is critical: the check must complete in under 5ms. Redis or similar in-memory store. No disk. No network round-trip to a remote database. Local or same-datacenter Redis. Fast.

---

## Let's Think Together

**"Where does the rate limiter sit? Before your API? As middleware? At the API gateway?"**

All valid. **Edge (API gateway):** Best. Rejects before traffic hits your servers. Cloudflare, AWS API Gateway, Kong—all support it. **Middleware in app:** Works. Request hits your app, middleware checks, then passes or rejects. Slightly more load than edge. **Separate service:** Microservice that other services call. More flexible but adds latency. For most systems: gateway-level is ideal. Reject early, save everything downstream. The rate limiter should be stateless per request: given user_id and limit, return allow or deny. State lives in Redis or similar. The gateway is the natural place: it sees every request first. Middleware works if you do not have a gateway. A separate service adds network hops. Start at the gateway. Evolve if needed. Different limits for different tiers: free users get 10 requests per minute, paid users get 1000. Store limits in a config service or database. The rate limiter checks: user tier, current count, limit. Allow or deny. Support both IP-based (anonymous) and user-based (authenticated) limits. Anonymous: use IP. Authenticated: use user_id. Prefer user_id when available—more accurate, harder to spoof. Global limits: cap total API load. Even if every user is under their limit, the sum might overwhelm your servers. A second-level rate limit: 100K requests per minute across all users. Protects your infrastructure. Implement in the gateway or a shared Redis. Sliding window gives fairest behavior at window boundaries. Fixed window can double-count. Token bucket allows bursts. Choose consciously.

---

## What Could Go Wrong? (Mini Disaster Story)

You deploy a rate limiter. One customer—a big enterprise—runs batch jobs at 2 AM. Your limit: 100 requests/minute. Their job: 10,000 requests. It gets 100. Then 429. Then 100. Then 429. Job runs for hours. They're furious. Lesson: allow burst limits or higher limits for known partners. Rate limiters need flexibility—not one size fits all.

---

## Surprising Truth / Fun Fact

The HTTP 429 status code was officially added in 2012 (RFC 6585). Before that, some APIs returned 503 (Service Unavailable) or 403 (Forbidden). 429 says exactly what it means: "Too Many Requests." It also suggests Retry-After headers—telling the client when to try again. A small HTTP addition that made rate limiting first-class.

---

## Quick Recap

- Rate limiter controls request flow; protects from abuse and overload.
- Requirements: check per request, return 429 if over limit, <5ms overhead, per-user and global limits.
- Algorithms: token bucket (bursty), sliding window (accurate), fixed window (simple).
- Placement: API gateway = best (reject early); middleware or separate service = alternatives.
- Design for flexibility: different limits for different customer tiers.

---

## One-Liner to Remember

*A rate limiter is a valve on the tap—count requests, enforce limits, reject with 429 when over—and do it at the edge.*

---

## Next Video

Next, we design the single-region rate limiter: Redis, counters, TTLs, and what happens when Redis goes down. Let's get into the details.
