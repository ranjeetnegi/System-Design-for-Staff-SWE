# Load Shedding: Dropping Work to Save the System

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

An overloaded bus. Capacity: 50 people. 100 trying to get on. Option 1: let everyone squeeze in. Bus can't move. Nobody reaches the destination. Option 2: let 50 in. Close the door. 50 people reach their destination. 50 wait for the next bus. Better than zero. Load shedding is that. Rejecting some requests so the rest can succeed. Sacrifice some. Save many.

---

## The Story

Your API can handle 1,000 requests per second. That's the limit. 2,000 requests hit. What happens? Without load shedding: you accept all 2,000. Queue them. Or try to process. Everyone gets slow. 5 seconds. 10 seconds. Timeouts. Errors. Maybe the system crashes. 100% of users get a bad experience. Or worse—nothing.

With load shedding: you accept 1,000. Reject 1,000 immediately. "503 Service Unavailable. Try again in 30 seconds." Those 1,000 rejected users get a fast, clear response. They can retry. Use another service. Come back later. The 1,000 you accepted? They get fast, successful responses. 50% great. 50% "try later." Better than 100% terrible. Better than total crash. Sacrifice some to save the system. And the majority of users.

---

## Another Way to See It

Think of an emergency room. Unlimited patients. One doctor. Everyone waits. Hours. Some die waiting. Load shedding: triage. Critical first. Others get "we're at capacity. Go to another hospital. Or wait." Some get care. Some don't. Harsh. But the alternative is nobody gets good care. Triage is load shedding. Prioritize. Save who you can.

Or a concert. Venue holds 5,000. 10,000 at the door. Option 1: let everyone in. Fire marshal shuts it down. No concert. Option 2: let 5,000 in. Turn away the rest. 5,000 see the show. Load shedding. Reject excess. Protect capacity. Some get in. Some don't. Better than nobody.

---

## Connecting to Software

**Without load shedding:** 100% of requests get slow responses or timeouts. System may crash. **With load shedding:** Some get fast responses. Some get immediate "try later." System stays up. Throughput for accepted requests stays good.

**Strategies:** Random drop—reject random excess. Fair in aggregate. Priority-based—VIP users first. Paying customers over free. Critical paths over nice-to-have. LIFO—drop oldest queued requests. They've probably timed out on the client anyway. Shed the stalest first.

**HTTP 503 Service Unavailable** + **Retry-After** header. Tell the client: we're overloaded. Try again in N seconds. Polite. Clear. Standard.

**Where to shed.** At the edge—API gateway, load balancer. Reject before work starts. Cheapest. Or at the service—when queue is full, reject. Or at the database—connection pool exhausted, reject. Earlier is better. Don't accept, queue for 30 seconds, then reject. That wastes resources. Reject fast. At the door.

---

## Let's Walk Through the Diagram

```
    NO LOAD SHEDDING                    WITH LOAD SHEDDING

    2000 requests/sec                   2000 requests/sec
           │                                     │
           │  Accept all                          │  Accept 1000
           ▼                                     │  Reject 1000 (503)
    [Server capacity: 1000]                      ▼
           │                            [Server capacity: 1000]
           │  Overload. Slow. Crash.             │
           ▼                                     │  Process 1000
    100% bad experience 💥                       ▼
                                         1000 fast ✓ 1000 "try later" ✓
                                         System survives. ✓
```

Left: accept all. Die. Right: reject excess. Survive. Some win. Some retry. System lives.

---

## Real-World Examples (2-3)

**Example 1: Uber surge.** High demand. Not enough drivers. Uber doesn't let everyone book. Some see "no cars available." Or higher prices to reduce demand. Load shedding at the product level. Reject or discourage excess. System stays responsive for those who get through.

**Example 2: Banking during market open.** 9:30 AM. Everyone hits trade. Systems at limit. Banks shed. Non-critical requests get "try again." Trade execution prioritized. Analytics. Reporting. Delayed. Core function protected. Load shedding by priority.

**Example 3: Cloudflare.** DDoS mitigation. Millions of requests. They can't process all. They drop obvious bad traffic. Rate limit. Challenge. Some good traffic might get delayed. But the site stays up. Load shedding at the edge. Protect the origin. Sacrifice some requests. Save the site.

---

## Let's Think Together

**During Black Friday: reject 30% of traffic or let 100% experience 10-second load times? Which is better for business?**

30% rejected: they get instant "try again." Some retry. Some go to competition. Some come back. 70% get fast checkout. 70% convert. 100% slow: carts abandoned. Timeouts. Frustration. Maybe 20% convert. Worse experience. Worse conversion. Load shedding—rejecting 30%—often wins. Clear failure beats slow death. Users can retry. They can't un-wait 10 seconds. Business case: test it. But usually, shed. Don't let everyone suffer.

---

## What Could Go Wrong? (Mini Disaster Story)

A team implemented load shedding. Rejected 20% of traffic when overloaded. Good. But they shed randomly. No priority. Payment requests got rejected as often as "view product image." Customers added to cart. Clicked pay. 503. Retry. 503. Cart abandoned. Revenue lost. Lesson: if you shed, shed by priority. Payment. Login. Critical paths. Never shed those first. Shed "trending now." Shed "recommendations." Shed analytics. Random shed is fair. But stupid. Priority matters. Business matters. Shed the right things.

---

## Surprising Truth / Fun Fact

Netflix uses load shedding in their chaos engineering. They simulate overload. Trigger shedding. Observe. Tune. They've learned: shedding 10% during a spike is often invisible to users. Shedding 50% is noticeable but acceptable. Letting 100% suffer? Unacceptable. The math favors shedding. Counterintuitive. Reject users to save users. But it works.

---

## Quick Recap (5 bullets)

- **Load shedding** = reject some requests so the rest succeed. Sacrifice some to save many.
- **Without:** 100% get slow or timeout. **With:** some get fast success, some get "try later."
- **Strategies:** random, priority-based (VIP first), LIFO (drop oldest queued).
- **HTTP 503** + **Retry-After** = polite rejection. Standard. Clear.
- **Shed by priority** = never shed payment first. Shed non-critical. Protect core.

---

## One-Liner to Remember

**When overloaded, reject some work. The rest will succeed. Load shedding—sometimes saying no saves everyone.**

---

## Next Video

Next: **Deadlock**—when two processes wait for each other forever. And how to avoid it. Stay tuned.
