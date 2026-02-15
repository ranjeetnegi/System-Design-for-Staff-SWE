# Rate Limiting: Per User vs Per IP vs Global

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A school cafeteria. Three levels of rules. Rule one: "Each student can take max 3 chapatis." Rule two: "Each class can take max 100 chapatis total." Rule three: "The kitchen makes max 500 chapatis for the whole school." Different scopes. Per-student is fair individually. Per-class prevents one class from hogging. Global protects the kitchen. Your API needs the same layers. Per user. Per IP. Per API key. Global. Each scope solves a different problem. Get it wrong, and you hurt good users—or get crushed by bad ones. Let me break it down.

---

## The Story

**Per user**: Each authenticated user gets N requests per minute. User A gets 100. User B gets 100. Fair. Requires user identity—login, API key, token. Best for logged-in traffic. One user can't monopolize. Even if they try, they hit their personal cap. Others are unaffected. **Per IP**: Works for unauthenticated traffic. You don't know who they are. You have their IP. Limit per IP. 100 requests per minute per IP. Simple. But problems: shared IPs. Office with 500 employees behind one IP. One person uses the API heavily. The whole office gets rate limited. NAT. Coffee shops. Universities. One IP, many users. Innocent people suffer. Also: attackers use VPNs. New IP every time. Per-IP limits are easy to bypass. Still, per-IP is better than nothing for anonymous traffic. **Per API key**: For developer APIs. Each key gets a quota. Free tier: 1000/hour. Paid: 10000/hour. Key identifies the customer. Fair. Billing-aware. You can tie limits to what they pay. **Global**: Total system capacity. "This endpoint handles max 10,000 req/sec. Period." Protects infrastructure. Doesn't matter who. When the total hits 10K, someone gets throttled. Usually the newest or least important traffic. Last line of defense. Without it, even with per-user limits, a viral moment could overwhelm your servers.

---

## Another Way to See It

Think of a theme park. Per person: each guest gets 3 fast passes. Fair. Per family: each family gets 10 total. Stops one family from taking 50. Per ride: each ride has max 100 people per hour. Protects the ride. Global: the park has max 10,000 guests total. Fire code. Different scopes. Different purposes. Or water supply. Per household. Per building. Per city. Layered. Rate limiting is the same.

---

## Connecting to Software

**Layered rate limiting**: Combine scopes. Per-user: 100/min. Per-IP: 500/min. Global: 10,000/sec. A user hits their 100? Blocked. Even if their IP has room. An IP sends 600 from multiple users? Blocked at 500. Even if each user is under 100. Global hits 10K? Block everyone until it drops. Defense in depth. Multiple layers. Abuser can't bypass by switching users if IP is capped. Can't bypass by switching IPs if user is capped (and you have auth). Global catches everything. Implement in order: check user limit. Check IP limit. Check global. First to fail wins. Reject. Some systems check global first—if the whole system is overloaded, no point checking per-user. Order can matter for performance. Think through your failure modes.

---

## Let's Walk Through the Diagram

```
    RATE LIMIT SCOPES

    ┌─────────────────────────────────────────────────────────┐
    │  PER USER: 100 req/min                                    │
    │  Each logged-in user gets their own bucket                │
    │  Fair. Requires authentication.                          │
    ├─────────────────────────────────────────────────────────┤
    │  PER IP: 500 req/min                                      │
    │  Works for anonymous. Shared IP = shared limit.            │
    │  NAT problem: 500 users behind 1 IP share 500.           │
    ├─────────────────────────────────────────────────────────┤
    │  PER API KEY: 10,000 req/hour (paid tier)                  │
    │  Developer/customer level. Billing-aware.                 │
    ├─────────────────────────────────────────────────────────┤
    │  GLOBAL: 10,000 req/sec (entire system)                   │
    │  Protects infrastructure. Last line of defense.           │
    └─────────────────────────────────────────────────────────┘

    Layered: All apply. Hit ANY limit = 429.
```

---

## Real-World Examples (2-3)

**Example 1: GitHub API.** Per-user limits when authenticated. Per-IP when not. Different tiers for different account types. Layered. **Example 2: Twilio.** Per account (API key). Each account has its own quota. Pay more, get more. Global protection on their side. **Example 3: Cloudflare.** Per-IP for DDoS protection. Per-customer for paid plans. Global for their network. Multi-scope. Standard practice.

---

## Let's Think Together

A corporate office has 500 employees. They share one IP—company NAT. Your API has a per-IP limit of 100 requests per minute. What happens?

All 500 employees share that 100. First 100 requests from anyone get through. Request 101? Blocked. For everyone. Even if it's a different employee who hasn't made a single request. One power user could consume the whole limit. Others get 429. "Your API is broken." The fix: per-user limits when possible. Require login or API key. Give each user 100. Then 500 users = 500 × 100 = 50,000 potential. Shared fairly. Or: higher per-IP limit for known corporate IPs. Whitelist. Or: per-user is primary. Per-IP only for anonymous. Authenticated traffic ignores per-IP. Design for the real world. Shared IPs exist.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup rate-limits only globally. 10,000 req/sec. One customer runs a batch job. They have a paid plan. They send 8,000 req/sec. Legitimate. The remaining 2,000 is shared by 10,000 other customers. Each gets 0.2 req/sec. Effectively unusable. "Why did we pay? The API is slow." The fix: per-customer limits. That batch customer gets 8,000. Others get their fair share. Global is a backstop. Per-customer is the real fairness. Scope matters. Global alone punishes everyone when one customer is large.

---

## Surprising Truth / Fun Fact

Some APIs use different limits for different endpoints. Login: 5 per minute (strict—prevent brute force). Read API: 1000 per minute (generous). Write API: 100 per minute (moderate). Expensive endpoint: 10 per minute. Scope can be "per user per endpoint." Granular. Protects critical paths. Allows flexibility elsewhere. Rate limiting isn't one number. It's a policy. Design it. Different endpoints have different costs. Match the limit to the cost. A cheap GET can afford a high limit. A heavy report generation might need a low limit. Think through each path.

---

## Quick Recap (5 bullets)

- **Per user**: Fair. Requires auth. Best for logged-in traffic.
- **Per IP**: Works for anonymous. Shared IP = shared limit. NAT problem.
- **Per API key**: For developer APIs. Quota per customer. Billing-aware.
- **Global**: Total system cap. Protects infrastructure. Last resort.
- **Layered**: Combine all. Per-user + per-IP + global. Defense in depth.

---

## One-Liner to Remember

**Per user = fairness. Per IP = anonymous catch-all. Global = infrastructure protection. Use all three.**

---

## Next Video

Rate limits that hurt good users. How to avoid that? Next: **Rate limiting without hurting good users**—tiers, headers, and triage. Stay tuned.
