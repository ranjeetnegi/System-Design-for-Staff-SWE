# Partial Failure: Why Things Fail in Pieces

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A 10-person relay race. Runner 1 finishes fine. Runner 2 finishes fine. Runner 3 trips and falls. Runners 4 through 10 are standing there, ready. Strong. Eager. But the race is stuck. Not everything failed. *Part* of the system failed. In distributed systems, your app runs fine. Database is fine. But the payment service is down. 90% of features work. 10% are broken. That's partial failure. And it's the norm. Not the exception.

---

## The Story

In a single machine, failure is often total. CPU dies. Power goes. The whole system is down. Binary. In distributed systems, failures are *partial* and *independent*. One server fails. Others run. One network link breaks. Others work. One datacenter loses power. Others serve traffic. The system is never uniformly up or down. It's a mix. Always.

This is tricky. The failing component doesn't always *tell* you it's failing. Request times out. Is the service dead? Or just slow? Network partition? Or packet loss? You don't know. Ambiguity. And that ambiguity forces every distributed system to assume: *anything can break at any time*. Every RPC can fail. Every call can hang. Every dependency can go dark. Design for it.

---

## Another Way to See It

Think of a city's power grid. One neighborhood has an outage. The rest of the city has power. Partial failure. The grocery store in that neighborhood is dark. The one two blocks away is lit. Same system. Different state. Distributed systems are like that. One region. One service. One pod. Fails. Others don't.

Or an office building. One elevator breaks. Others work. One floor floods. Others are dry. You can't assume "building is up" means "everything works." You have to handle "this elevator is out" while the rest functions. Partial. Always partial.

---

## Connecting to Software

**Design for partial failure:** Every call can fail. Add timeouts—don't wait forever. Add retries—transient failures happen. Add fallbacks—if payment service is down, show "pay later." Add circuit breakers—stop hammering failing services. Assume anything can break at any time. Plan for it.

**The failing component often doesn't announce itself.** You get a timeout. A connection refused. A 500. You don't get "I am dead." You infer. And inference is hard. Slow vs. dead? Retry or fail? These decisions define resilient systems.

**Partial failure forces explicit handling.** In a monolith, one process. It fails, everything fails. Simple. In distributed systems, you must decide: if service A is down, does feature X work? Degrade? Fail? Every dependency is a decision point.

**The ambiguity problem.** You get a timeout. Was the request lost? Or slow? Did the server receive it? Processing? You don't know. This ambiguity drives idempotency—safe to retry. Drives status checks—"did my payment go through?" Drives fallbacks—"if unclear, show this." Partial failure isn't just "things break." It's "you often can't tell what broke." Design for ambiguity.

---

## Let's Walk Through the Diagram

```
    MONOLITH (Total Failure)              DISTRIBUTED (Partial Failure)

         [One Process]                    [App] ──► [DB] ✓
                │                         [App] ──► [Payment] ✗ timeout
                │                         [App] ──► [Inventory] ✓
         Fails? Everything fails.         [App] ──► [Notification] ✓
                💥                               │
                                         Cart: works. Checkout: broken.
                                         ％ failure, not 100％ failure.
```

Left: all or nothing. Right: mixed state. Some components up. Some down. Handle the mix.

---

## Real-World Examples (2-3)

**Example 1: E-commerce checkout.** User adds to cart. Inventory service: OK. User clicks pay. Payment service: timeout. Notification service: OK. Order status? Ambiguous. Did we charge? Did we reserve inventory? Partial failure in the middle of a workflow. Systems must handle: idempotency, compensation, clear user feedback.

**Example 2: Netflix.** Recommendation service down? Show popular titles. Video playback? Different service. Works. Search slow? Show cached results. Each component can fail independently. The product degrades. Doesn't die.

**Example 3: Uber.** Map loading fails? Show last known location. Pricing service slow? Show estimate. Ride matching works? Different service. Partial failure everywhere. Design for it. Users get a degraded but functional experience.

---

## Let's Think Together

**User checks out. Inventory service: OK. Payment service: timeout. Notification: OK. What's the order status?**

You don't know. Payment might have succeeded. Might have failed. Might be in progress. Best: design for this. Idempotent payment—retry safe. Check payment status before fulfilling. Don't ship if payment unclear. Show user "processing" or "try again." Never guess. Never assume. Partial failure in the middle of a flow = ambiguity. Handle it explicitly.

---

## What Could Go Wrong? (Mini Disaster Story)

A travel booking site. User books flight. Flight service: OK. Hotel service: OK. Payment: timeout. System assumed failure. Didn't charge. But payment gateway had actually processed it. Double-charge on retry. User charged twice. Refund hell. Lesson: partial failure in payment flows is dangerous. Never assume. Verify. Idempotency keys. Status checks. Partial failure demands extra care in money flows.

---

## Surprising Truth / Fun Fact

Leslie Lamport—Turing Award winner—said: "A distributed system is one in which the failure of a computer you didn't even know existed can render your own computer unusable." Partial failure isn't a bug. It's a defining characteristic. If you're building distributed systems, you're building for partial failure. Always.

---

## Quick Recap (5 bullets)

- **Partial failure** = some components fail, others work. The norm in distributed systems.
- **Independent** = one server, one link, one service fails without others failing.
- **Ambiguity** = timeout. Dead or slow? Failing component doesn't always announce.
- **Design for it** = timeouts, retries, fallbacks. Assume anything can break.
- **Every dependency is a decision point** = what happens when it's down?

---

## One-Liner to Remember

**In distributed systems, things don't fail all at once. They fail in pieces. Design for the pieces.**

---

## Next Video

Next: **Cascading Failure**—how one small failure can take down an entire system. The domino effect. Stay tuned.
