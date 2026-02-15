# Token Bucket Algorithm (Simple)

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A parking garage has a token dispenser. Every second, one token drops into the bucket. To enter, you need a token. You take one. You drive in. The next car? Same thing. If the bucket has tokens, you're in. If it's empty, you wait. The bucket holds max 10 tokens. So you can have a short burst—10 cars back-to-back—but over time, the steady rate is one per second. That's the **token bucket**. Simple. Elegant. And it handles real-world traffic in a way that fixed limits can't. Let me show you.

---

## The Story

The token bucket has two parameters. **Refill rate**: how many tokens are added per second. One token per second. Ten tokens per second. Your choice. **Bucket size**: the maximum tokens the bucket can hold. Ten. Fifty. A hundred. The refill rate sets the **sustained** rate—the average over time. The bucket size sets the **burst** capacity—how many requests can happen at once after a quiet period. Refill = 10/sec, bucket = 50. In a burst, 50 requests can go through immediately. Then tokens refill at 10/sec. So after the burst, steady rate is 10/sec. Real traffic is bursty. Users click. Pause. Click again. Fixed "one request per second" would feel awful. Token bucket allows bursts. Then enforces the average. Perfect balance.

---

## Another Way to See It

Think of a water bucket with a small hole. Water drips in at a fixed rate (refill). The bucket can hold a certain amount (size). You can scoop out water in bursts—until the bucket is empty. Then you wait for it to refill. Or a coffee machine. It fills a carafe slowly. You can pour multiple cups quickly—burst. Then you wait for the carafe to refill. Token bucket = the same idea. Bursts allowed. Sustained rate controlled.

---

## Connecting to Software

The algorithm. On each request: Check the bucket. Do we have at least one token? If yes: remove one token. Allow the request. If no: reject. Return 429 Too Many Requests. In the background: tokens refill at the refill rate, up to the bucket size. Don't exceed the max. Implementation: store (tokens_in_bucket, last_refill_time). When a request comes, calculate how many tokens should have been added since last_refill. Add them (cap at bucket size). If tokens >= 1, subtract 1 and allow. Else, reject.

Why token bucket over a simple "N requests per second" counter? Bursts. A fixed window might allow 100 requests in second one, then 0 in second two. Token bucket: if you had a quiet period, your bucket fills. You can burst. Then you're limited. Smooth. User experience is better. Systems handle bursts. Token bucket models reality. Consider a dashboard that loads 10 widgets on page load. All 10 API calls happen in the first second. A strict "1 request per second" would make the page load in 10 seconds. Awful. Token bucket with a burst of 10? All 10 load at once. Then the user has to wait for refill before doing more. Natural. The algorithm matches how humans actually use systems.

---

## Let's Walk Through the Diagram

```
    TOKEN BUCKET

    Refill: 1 token/second
    Bucket size: 5

    Time 0:  Bucket full [●●●●●]  (5 tokens)
    Time 1:  3 requests → take 3 [●●___]  (2 left)
    Time 2:  1 refill + 2 requests → [●____]  (1 left, 1 allowed, 1 rejected?)
            Actually: 2 requests arrive. Bucket has 2 (1 refill + 1 from before). Both allowed.
    Time 3:  Quiet. Refill. [●●___]  (2 tokens)
    Time 4:  5 requests burst! Only 2 tokens → 2 allowed, 3 rejected (429)

    ┌─────────────────────────────────────────┐
    │  Bucket: [■■■■■]  max 5                 │
    │           ↑                              │
    │  Tokens refill slowly (1/sec)            │
    │  Requests consume 1 token each           │
    │  Empty bucket = 429 Too Many Requests    │
    └─────────────────────────────────────────┘
```

---

## Real-World Examples (2-3)

**Example 1: Stripe API.** Uses token bucket–style limiting. Bursts allowed for sudden operations. Sustained rate capped. Developers get predictable behavior. **Example 2: AWS API Gateway.** Throttling can be configured with burst and steady-state rates. Token bucket under the hood. **Example 3: Video streaming.** Bursts for quality changes. Buffering uses "tokens." Steady download rate. Token bucket logic in networks and media.

---

## Let's Think Together

Bucket size = 100. Refill rate = 10 per second. The bucket is full. 100 requests arrive at once. What happens? What about request 101?

First 100 requests: each takes one token. All 100 allowed. Bucket is now empty. Request 101: bucket has 0 tokens. Rejected. 429. Now, one second passes. 10 tokens refill. 10 more requests can go through. Then 10 more the next second. Sustained rate = 10/sec. The burst of 100 was allowed because the bucket was full. Request 101 arrived before any refill. Denied. That's token bucket: burst capacity, then steady limit.

---

## What Could Go Wrong? (Mini Disaster Story)

A team implements rate limiting with a fixed 100 req/min. No burst. A dashboard loads. It makes 50 API calls in 2 seconds—charts, tables, user data. All at once. Legitimate. The rate limiter: "50 in 2 seconds? That's 1500/min equivalent. Rejected." Users see half-loaded dashboards. Errors. "Your API is broken." The fix: token bucket. Allow a burst of 50. Refill at 10/sec. Dashboard loads in 2 seconds. Then user has to wait for refill to do more. But the initial load works. Fixed rate punished real users. Token bucket saves the day.

---

## Surprising Truth / Fun Fact

The leaky bucket algorithm is related but different. Leaky bucket: requests go into a queue. They "leak" out at a fixed rate. No burst. Smooth output. Token bucket: tokens accumulate. You can use them in bursts. Same goal—rate control—different behavior. Token bucket is more common in APIs because it's user-friendlier. Bursts happen. Allow them. Then cap the average. Leaky bucket is stricter. Choose based on your needs.

---

## Quick Recap (5 bullets)

- **Token bucket**: Tokens refill at a steady rate. Each request consumes one token. Bucket has max size.
- **Parameters**: Refill rate (tokens/sec) + bucket size (max tokens). Burst = bucket size. Sustained = refill rate.
- **Algorithm**: Token available? Take one, allow. No token? Reject with 429.
- **Why**: Handles bursts. Real traffic is bursty. Fixed rate is too strict.
- **Burst then steady**: Full bucket = burst allowed. Empty = wait for refill.

---

## One-Liner to Remember

**Token bucket: Refill at steady rate, use in bursts. Smooth limit with burst allowance.**

---

## Next Video

What if your "per minute" limit resets at the wrong moment? Next: **Sliding window vs fixed window**—the nightclub rule that breaks at midnight. Stay tuned.
