# Cold Start: Serverless and Caches
## Video Length: ~4-5 minutes | Level: Intermediate
---
## The Hook (20-30 seconds)

A car on a freezing winter morning. You turn the key. The engine sputters. The heater blows cold air. It takes 30 seconds before the engine warms up and runs smoothly. That's a cold start. The car works — it's just SLOW at the beginning. In serverless: a Lambda function that hasn't been invoked recently gets deallocated. A new request comes in. The system has to provision a container, load the code, initialize the runtime, and THEN run your handler. Those first requests? SLOW. That's the cold start problem.

---

## The Story

You deploy a Lambda function. It works great. 50ms response time. Fast. Then traffic drops. No requests for 15 minutes. AWS spins down your container. Saves money. Makes sense. But the next user? They wait. 500ms. 1 second. Maybe 3 seconds. Just for the function to START. Your user thinks the app is broken. It's not broken. It's cold.

Same with a cache. New Redis node. Or Redis restarted. Empty. Every request misses. Every request hits the database. The database gets hammered. "Cache stampede after restart." The cache isn't broken. It's cold.

---

## Another Way to See It

Think of a library. Books are on the shelf. You want a book. You walk over. Grab it. Fast. Now imagine the library was closed. Lights off. Doors locked. Someone asks for a book. The librarian has to: turn on the lights, unlock the door, find the shelf, grab the book. That first request takes forever. The library works — it just needed to "wake up." Cold start.

---

## Connecting to Software

**Serverless cold start.** AWS Lambda not invoked for a while → container deallocated. New request arrives → provision new container → load your code → initialize runtime (Node, Python, Java) → run your handler. First request: 500ms–5 seconds. Subsequent requests: 10–50ms. Massive difference. Java and .NET: worst cold starts (heavy runtimes). Go, Python, Node: better. Small packages: faster. Large dependencies: slower.

**Cache cold start.** New cache server. Or server restart. Cache is EMPTY. Every request is a miss. Every miss goes to the database. Database gets 100% of the load it was never designed for. Cache stampede. Database can die.

**Mitigation for serverless:** Provisioned concurrency (keep N containers warm — costs money, but predictable latency). Smaller deployment packages. Lighter runtimes — Java and .NET are heavy; Node and Go boot faster. Ping functions periodically (cron every 5 min) to keep them warm. Edge functions (Cloudflare Workers) have faster cold starts because they run on lighter V8 isolates. Choose based on your latency requirements and budget.

**Mitigation for cache:** Pre-warm before routing traffic. Run a script that loads top 10,000 keys from DB into cache. Then switch traffic. Gradual traffic shift: send 10% first, let cache fill, then 100%. Don't dump full traffic on an empty cache. That's how you kill your database. Plan the ramp. Test it in staging. Know your hot keys. Load them first.

---

## Let's Walk Through the Diagram

```
    COLD START (First Request)
    
    User Request ──▶ Lambda (idle, no container)
                           │
                           ▼
              Provision container (200-500ms)
                           │
                           ▼
              Load code + dependencies (100-2000ms)
                           │
                           ▼
              Initialize runtime (50-500ms)
                           │
                           ▼
              Run handler (10-50ms)
                           │
                           ▼
              Response ──▶ User (total: 500ms-5s!)

    WARM REQUEST (Next Request)
    
    User Request ──▶ Lambda (container exists, warm)
                           │
                           ▼
              Run handler (10-50ms)
                           │
                           ▼
              Response ──▶ User (fast!)
```

The diagram tells the story: cold = many steps. Warm = one step. Same code. Different path.

---

## Real-World Examples (2-3)

**Netflix** uses Lambda for video processing. They use provisioned concurrency for critical paths. Cold start on a user-facing API? Unacceptable. They pay to keep functions warm.

**Twilio** had cold start issues with their serverless functions. Users experienced 2–3 second delays on first message. Unacceptable for a communications API. Latency matters when you're sending texts or making calls. They switched to keeping a minimum number of instances warm during peak hours. Paid for the warmth. Got the speed. Trade-off that made sense for their use case.

**E-commerce** sites with Redis: after a deployment that restarts Redis, they run a "cache warmer" script before directing traffic. Load top products, top categories, session data. Then go live. Prevents DB overload. I've seen sites go down because they restarted Redis at peak and the empty cache sent a stampede to the database. A simple warmer script would have saved them. Cheap insurance.

---

## Let's Think Together

New Redis cache deployed. 0% hit rate. All traffic hits the database. How do you prevent the database from dying?

**Answer:** Pre-warm. Before routing production traffic, run a script that: (1) Queries the database for the most frequently accessed keys (e.g., top 10,000 products, popular users). (2) Loads them into Redis. (3) Then switch traffic. Alternative: gradual ramp. Route 1% of traffic. Cache fills. Then 10%. Then 50%. Then 100%. Spread the load. Don't dump 100% traffic on an empty cache.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup moved their API to Lambda. Traffic was steady. Everything fine. Then they went viral. 10x traffic in an hour. Thousands of concurrent Lambda invocations. Each new invocation = cold start. AWS was provisioning thousands of containers. Cold start latency spiked to 5 seconds. Users thought the site was down. The "scaling" created a latency storm. Lesson: For traffic spikes, provisioned concurrency or keep-warm strategies matter. Or use traditional compute for predictable high load.

---

## Surprising Truth / Fun Fact

AWS Lambda cold start varies wildly by runtime. A simple Node.js function: 200ms. A Java Spring Boot function: 5+ seconds. The same logic, different cold start. Choosing the right runtime matters more than you think.

---

## Quick Recap (5 bullets)

- Cold start = first request after idle is slow (container/cache needs to initialize). The system works — it just needs to wake up.
- Serverless: provision container, load code, init runtime — 500ms to 5 seconds.
- Cache cold start: empty cache = all requests hit DB = stampede.
- Mitigation: provisioned concurrency, smaller packages, lighter runtimes, periodic pings.
- Cache: pre-warm before traffic, or gradual traffic shift.

---

## One-Liner to Remember

**Cold start is the price of "scale to zero." First request pays it. Mitigate with warm pools, smaller packages, or pre-warming.**

---

## Next Video

Next up: **Warm Pools and Pre-warming** — firefighters don't wait for the call to get dressed. They're ready. Let's make your systems ready too. Cold start is a solvable problem. Warm pools and pre-warming are the tools.
