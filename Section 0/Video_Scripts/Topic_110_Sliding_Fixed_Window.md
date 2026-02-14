# Sliding Window and Fixed Window

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A nightclub has a rule: "Max 100 people per hour." Sounds clear. But how do you count "per hour"? Option one: every hour on the dot, the count resets. 11:00—zero. 11:59—95 people inside. 12:00—reset. Now zero. But 90 of those 95 arrived at 11:55. At 12:01, 90 NEW people arrive. Between 11:55 and 12:01—six minutes—you had 185 people. The "per hour" rule was technically followed. The intent was violated. **Fixed window** has a flaw. **Sliding window** fixes it. Let me show you how.

---

## The Story

**Fixed window**: Divide time into fixed periods. Minute 1: 0:00–0:59. Minute 2: 1:00–1:59. Count requests in each window. At the boundary, the count resets. Simple. But the **boundary problem**: a user can send 100 requests at 11:59:30. All allowed—within the 11:00–12:00 window. At 12:00:30, they send 100 more. All allowed—within the 12:00–13:00 window. In 60 seconds, they sent 200 requests. "100 per minute" was the rule. They broke the spirit of it. Fixed window allows double the rate at boundaries. Savvy attackers know this. They time their bursts. Your rate limiter says "OK" while your server melts. Fixed window is easy to implement. But for strict limits, sliding window is safer.

**Sliding window**: Look at the last N seconds from NOW. Not fixed clock hours. At 12:00:30, count requests from 11:59:30 to 12:00:30. That's the last 60 seconds. Always. No boundary. If the user sent 100 at 11:59:30, those are still in the window at 12:00:30. Request 101 at 12:00:31? Denied. Accurate. But more complex to implement.

---

## Another Way to See It

Think of a moving train. Fixed window: you count people in car 1, then car 2, then car 3. Reset each time. Someone could ride the boundary—jump from car 1 to car 2 at the last second—and get counted twice. Sliding window: you look at a 60-foot stretch of the train. As the train moves, that stretch moves. You always see the last 60 feet. No boundary. Same people in view until they pass. Or a rolling average. Fixed = separate buckets. Sliding = one continuously moving view.

---

## Connecting to Software

**Fixed window implementation**: Store a counter and window start time. Request arrives. Is current time in the same window? Yes → increment counter. No → reset counter, new window. Check: counter <= limit? Allow or reject. Simple. Fast. But boundary exploit exists. **Sliding window log**: Store timestamp of every request. Request arrives. Delete timestamps older than N seconds. Count remaining. If count < limit, allow and add timestamp. Accurate. Memory-heavy—every request is stored. At high scale, this can mean millions of timestamps per user. **Sliding window counter**: Hybrid. Use current window counter + weighted previous window. Formula: prev_count * (1 - (elapsed / window_size)) + current_count. Approximate. Efficient. Good balance. Redis has this. Most production systems use it. The approximation is usually within a few percent. For rate limiting, that's acceptable. Perfect accuracy would cost too much.

---

## Let's Walk Through the Diagram

```
    FIXED WINDOW - BOUNDARY PROBLEM

    Window 1: 11:00-12:00     Window 2: 12:00-13:00
    |________________________|________________________|
    11:00              11:59 12:00              12:01
         [100 requests here] [100 requests here]
                   ↑                    ↑
              All allowed!         All allowed!
              (different windows)   (different windows)

    Result: 200 requests in ~60 seconds. Limit was 100/min. Oops.


    SLIDING WINDOW - NO BOUNDARY

    At 12:00:30, "last 60 seconds" = 11:59:30 to 12:00:30
    |<-------- 60 seconds -------->|
              11:59:30          12:00:30
    [100 req at 11:59:30 still in window]
    Request 101 at 12:00:31? DENIED. (100 already in last 60 sec)
```

---

## Real-World Examples (2-3)

**Example 1: Stripe.** Uses sliding-window–style rate limiting. Prevents boundary exploitation. Fair for subscribers. **Example 2: Cloudflare.** Configurable fixed or sliding. Sliding for stricter enforcement. **Example 3: Redis-based limiters.** Redis has sliding window logic with sorted sets or Lua scripts. Store timestamps. Trim old. Count. Production-ready pattern.

---

## Let's Think Together

Your rate limit is 100 requests per minute. At 11:59:30, a user sends 100 requests. Fixed window allows them. At 12:00:30, they send 100 more. Fixed window allows them again. Sliding window?

At 12:00:30, the sliding window is 11:59:30 to 12:00:30. The 100 requests from 11:59:30 are still in that window. They haven't "expired" yet. So the user has already used their 100. The new 100 requests? The first few might get in as the 11:59:30 requests start to age out. But most would be denied. After 60 seconds from the first burst, the oldest requests fall out. Then new ones can come in. Sliding window prevents the "double burst at the boundary" exploit. User gets 100 per minute in a true rolling sense. Fair.

---

## What Could Go Wrong? (Mini Disaster Story)

A company uses fixed window. 1000 req/min. An attacker discovers the boundary. They send 1000 at XX:59:50. All allowed. They send 1000 at XX+1:00:10. All allowed. In 20 seconds, 2000 requests. The rate limiter logs show "within limits." The server struggles. The attacker has doubled the effective rate. Support doesn't understand. "Our rate limiter says it's fine." The fix: switch to sliding window. The exploit disappears. Boundary problem solved. Sometimes the "simple" algorithm has a critical flaw. Sliding window fixes it.

---

## Surprising Truth / Fun Fact

Sliding window log—storing every timestamp—can get expensive. At 10,000 requests per second per user, you're storing 10,000 timestamps per second. Memory explodes. That's why the sliding window counter (approximate, weighted) exists. Redis does it with a clever algorithm. Slight overcounting possible. But for most use cases, "good enough" beats "perfect but expensive." Engineering is trade-offs.

---

## Quick Recap (5 bullets)

- **Fixed window**: Count in fixed periods (e.g., each minute). Simple. Boundary problem: 2x rate at window edge.
- **Sliding window**: Count in the last N seconds from now. No boundary. Accurate.
- **Sliding window log**: Store every timestamp. Accurate but memory-heavy.
- **Sliding window counter**: Weighted previous + current window. Approximate. Efficient. Common in production.
- **Choose**: Fixed for simplicity. Sliding when boundary exploit matters. If your limit is generous—10,000 per minute—the boundary problem might not hurt you. If your limit is strict—10 per minute—a user could get 20 by exploiting the boundary. Know your threat model. Strict limits need sliding window. Relaxed limits can sometimes use fixed. But when in doubt, go sliding. Slightly more complex. Much more accurate.

---

## One-Liner to Remember

**Fixed window: Resets at the clock. Sliding window: Always the last N seconds. Sliding stops the boundary exploit.**

---

## Next Video

Rate limit per user? Per IP? Per API key? Per planet? Next: **Rate limiting scope**—who you limit matters as much as how. Coming up.
