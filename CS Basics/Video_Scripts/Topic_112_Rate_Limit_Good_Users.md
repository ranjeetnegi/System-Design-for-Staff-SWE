# How to Rate Limit Without Hurting Good Users

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A hospital ER. You can't rate-limit a heart attack patient the same as someone with a paper cut. Triage. Critical patients go first. Life or death. Rate limiting should be the same—differentiate between important and less important traffic. Don't treat a paying customer like an anonymous bot. Don't kill a 5-minute file upload because a 60-second limit hit. Good rate limiting is invisible to good users. Bad rate limiting punishes everyone equally. Let me show you how to get it right.

---

## The Story

**Tiered limits**: Free users get 100 requests per minute. Paid users get 10,000. Enterprise gets 100,000. Same API. Different ceilings. Paying customers shouldn't hit limits during normal use. Free tier catches abuse. Fair. If your paid user hits a limit during normal workflow, your limit is too low. Tune it. **Graceful response**: When you return 429, don't just say "Too Many Requests." Include a Retry-After header. "Try again in 30 seconds." Tell the user WHEN. They can implement backoff. They're not left guessing. Better UX. A client that retries immediately will hammer your server. Retry-After tells them to wait. **Rate limit headers**: X-RateLimit-Limit (your max), X-RateLimit-Remaining (how many left), X-RateLimit-Reset (when the window resets). Every response. The client knows. They can slow down before hitting the wall. No surprise 429s. Some clients use these to show users "You have 42 requests left this hour." Transparency builds trust. **Soft vs hard limits**: Soft limit = allow the request, but log a warning. Monitor. Don't block yet. Hard limit = block immediately. Use soft for "approaching limit" detection. Use hard when you must protect. **Whitelist critical paths**: Health checks. Payment confirmations. Webhook receivers. These should NEVER be rate-limited. A load balancer health check every second? Allow it. A payment gateway callback? Allow it. Rate limiting the wrong path can cause outages. Or lost payments. Document your whitelist. So the next developer doesn't accidentally add a critical path to rate limiting.

---

## Another Way to See It

Think of airline boarding. First class boards first. Economy last. Same plane. Different treatment. Rate limiting: paid tier = first class. Free tier = economy. Or a toll road. Trucks pay more. Cars pay less. Different vehicles, different rules. Rate limiting: different users, different limits. Not one-size-fits-all. Or a restaurant. Regulars get a better table. New customers wait. You're not treating everyone the same. You're recognizing value. Rate limiting can do the same.

---

## Connecting to Software

**Implementation**: Store user tier in your auth system. Free, Paid, Enterprise. Rate limiter checks tier before applying limit. Key = user_id + tier. Limit = lookup[tier]. **Headers in response**: Every 200 and 429. X-RateLimit-Limit: 100. X-RateLimit-Remaining: 42. X-RateLimit-Reset: 1640000000 (Unix timestamp). Client reads them. Adjusts. **Retry-After**: On 429, set Retry-After: 60. Client waits 60 seconds. Retries. Standard. **Critical path bypass**: Middleware checks request path. /health, /webhooks/payment, /internal/*. Skip rate limit. Whitelist. Document it. Don't surprise yourself during an incident.

---

## Let's Walk Through the Diagram

```
    RATE LIMIT WITHOUT HURTING GOOD USERS

    ┌─────────────────────────────────────────────────────────┐
    │  TIERED LIMITS                                           │
    │  Free:    100/min   ████                                 │
    │  Paid:    10K/min   ████████████████████████████████     │
    │  Enterprise: 100K   ████████████████████████████████ ...  │
    └─────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────┐
    │  RESPONSE HEADERS (every 200 response)                   │
    │  X-RateLimit-Limit: 100                                  │
    │  X-RateLimit-Remaining: 42                               │
    │  X-RateLimit-Reset: 1640000060                           │
    │  → Client knows when to slow down                        │
    └─────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────┐
    │  ON 429: Retry-After: 60                                 │
    │  → Client knows when to retry                            │
    └─────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────┐
    │  WHITELIST: /health, /webhooks/*, /payment/callback      │
    │  → Critical paths never rate limited                     │
    └─────────────────────────────────────────────────────────┘
```

---

## Real-World Examples (2-3)

**Example 1: GitHub.** Free tier: 5,000 req/hour. Pro: higher. Enterprise: custom. Tiered. Headers in every response. Developers love it. Predictable. **Example 2: Stripe.** Different limits per endpoint. Payment creation: higher limit. List operations: lower. Critical paths protected. Retry-After on 429. Good docs. **Example 3: Twilio.** Per-account limits. Pay more, get more. Webhook endpoints: often whitelisted by customers. Avoid rate limiting payment status callbacks. Real-world consideration.

---

## Let's Think Together

A user is uploading a large file. It takes 5 minutes. Midway through, their rate limit hits. The upload fails. Is this good UX?

No. Terrible. The user did nothing wrong. They started an allowed action. Midway, an unrelated limit (maybe requests per minute) kicked in. Or the upload itself counted as many "requests" in some implementations. Good rate limiting for uploads: (1) Don't count upload bytes against request rate. Use separate bandwidth limits. (2) Or: long-running operations get a longer window. (3) Or: Once an upload starts, don't interrupt it. Rate limit new requests, not in-flight ones. (4) Or: Higher limit for write/upload operations. Read might be 1000/min. Upload might be 10/min but each can be 100MB. Design for the use case. A 429 mid-upload is a UX failure. Fix it.

---

## What Could Go Wrong? (Mini Disaster Story)

A company rate-limits everything. Including their webhook receiver. A payment provider sends a callback: "Payment confirmed." The webhook hits the rate limit. 429. The provider retries. 429 again. After 3 retries, the provider gives up. The company never records the payment. Money arrived. Database says it didn't. Reconciliation nightmare. Customer paid. Company says "unpaid." The fix: whitelist webhook paths. Payment callbacks. OAuth callbacks. Health checks. Never rate limit critical infrastructure. One 429 on a webhook can cost millions. Literally.

---

## Surprising Truth / Fun Fact

Some APIs use "burst allowance" + "sustained rate" for different operations. Burst: allow 10 requests in 1 second. Sustained: 100 per minute. A dashboard that loads 10 widgets at once? Burst allows it. Then user has to wait for sustained refill. Best of both. Protects from sustained abuse. Allows natural bursts. Token bucket does this. But the "tier" can change the bucket size. Paid user: bigger burst. Free user: small burst. Granular control.

---

## Quick Recap (5 bullets)

- **Tiered limits**: Free vs paid vs enterprise. Paying users get higher limits. Fair.
- **Headers**: X-RateLimit-Limit, Remaining, Reset. Help clients avoid surprises.
- **Retry-After** on 429: Tell clients when to retry. Better UX.
- **Whitelist critical paths**: Health checks, webhooks, payment callbacks. Never rate limit these.
- **Long operations**: Don't kill uploads mid-stream. Design for the use case. A 5-minute upload that gets 429 at minute 3 is a support nightmare. Either whitelist upload endpoints, use separate bandwidth limits, or give long operations a larger allowance. Good rate limiting feels invisible to good users. They only notice when they're abusing—or when you've misconfigured it.

---

## One-Liner to Remember

**Rate limit abusers, not good users. Tiered limits, clear headers, whitelist critical paths.**

---

## Next Video

One server is easy. Ten servers? The count gets messy. Next: **Distributed rate limiting**—when the guards don't talk to each other. See you there.
