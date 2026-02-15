# Retries and Exponential Backoff

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You call a friend. Busy. You wait one second. Call again. Busy. Wait two seconds. Call again. Busy. Wait four seconds. Eight seconds. Sixteen seconds. Each time you wait *longer*. You don't spam-call every second—that's annoying and useless. That's exponential backoff. And it saves systems from destroying themselves when things go wrong.

---

## The Story

Transient failures happen all the time in distributed systems. A network blip. A server momentarily overloaded. A database connection that dropped. Most of these clear up in seconds. Retrying often succeeds. So you retry.

But here's the trap. You retry immediately. Again. Again. Again. A thousand clients. All retrying. Every millisecond. The server was already struggling. Now it's drowning in retries. You made it *worse*. The failure spreads. The system collapses. Your "fix" killed the patient.

Exponential backoff changes the game. Retry 1: wait 1 second. Retry 2: wait 2 seconds. Retry 3: wait 4 seconds. Retry 4: wait 8 seconds. Each wait grows exponentially. 1, 2, 4, 8, 16, 32... The server gets breathing room. Time to recover. And when it does, your next retry succeeds. You helped. You didn't hammer.

Add jitter—a random delay on top. Why? Without it, all clients retry at the same instant. 1,000 clients. All wait 4 seconds. All retry at second 4. Thundering herd. Same spike. Same problem. Jitter spreads them out. "Wait 4 seconds plus random 0 to 2 seconds." Retries scatter. No synchronized stampede.

---

## Another Way to See It

Think of a crowded elevator. Door opens. Everyone rushes in at once. Nobody fits. Door closes. Opens again. Same rush. Chaos. Now: one person waits 1 second. Another waits 2. Another 4. Staggered. The elevator fills smoothly. Everyone gets in. Exponential backoff is that stagger. Don't all rush at once.

Or a restaurant kitchen on fire. Fire alarm. Everyone runs to the exit at the same second. Bottleneck. Trampling. If people exited in waves—a few now, more in 5 seconds, more in 10—everyone escapes. Spreading the load saves lives. Spreading retries saves systems.

---

## Connecting to Software

**Why retry?** Transient failures are temporary. Network hiccups. Service restarting. Load spikes. Retrying gives the system a second chance. Often it works. Retry on 5xx, timeouts, connection refused. Don't retry on 4xx (bad request—won't change). Don't retry on 401 (auth—fix credentials first).

**Why backoff?** Immediate retries flood the already-struggling service. You become part of the problem. Backoff gives recovery time. Exponential is standard: doubles each attempt. Linear (1s, 2s, 3s, 4s) is gentler but slower to space out.

**Jitter:** Add randomness. `base * 2^attempt + random(0, jitter)`. Prevents thundering herd when many clients retry together. Essential in distributed systems.

**Max retries:** Don't retry forever. 3 to 5 retries with backoff. Then fail gracefully. Return error to user. Log. Alert. Let the system recover without you hammering it.

**Idempotency matters.** If you retry a write, could it execute twice? Payment charged twice? Order created twice? Make operations idempotent. Idempotency keys. Or design so retries are safe. Retries + non-idempotent operations = double charges, duplicate records. Fix the operation. Then retry with confidence.

---

## Let's Walk Through the Diagram

```
    RETRY WITHOUT BACKOFF                    RETRY WITH EXPONENTIAL BACKOFF

    Client ──► Server (fails)
    Client ──► Server (fails)                Client ──► Server (fails)
    Client ──► Server (fails)                [wait 1s]
    Client ──► Server (fails)                Client ──► Server (fails)
    Client ──► Server (fails)                [wait 2s]
    Client ──► Server (fails)                Client ──► Server (fails)
    ...                                      [wait 4s]
    Server DROWNING in requests              Client ──► Server (OK!)
         💥                                       ✓
```

Left: hammering. Server never recovers. Right: backoff gives breathing room. Server recovers. Retry succeeds.

---

## Real-World Examples (2-3)

**Example 1: AWS SDK.** Every AWS SDK uses exponential backoff by default. S3, DynamoDB, API calls. Service returns 5xx or throttles (429)? Backoff. Retry. You don't configure it—it's built in. Amazon learned the hard way: clients hammering failing services caused cascading outages.

**Example 2: Kafka consumers.** Consumer fetches messages. Broker busy. Consumer backs off. Retries with increasing delay. Prevents one slow consumer from overwhelming the broker. The whole cluster stays healthy.

**Example 3: Mobile app sync.** App syncs with backend. Network flaky. Immediate retries drain battery and annoy users. Backoff: retry in 1s, 2s, 5s, 10s. When network stabilizes, sync succeeds. User doesn't notice. Battery lasts.

**Example 4: gRPC and HTTP clients.** Many libraries have retry built in. With configurable backoff. gRPC: exponential backoff with jitter by default. Respect server's retry-after. HTTP clients: same. Configure. Don't rely on "maybe it works." Retries are table stakes. Backoff is non-negotiable.

---

## Let's Think Together

**Service returns 500. Should you retry? What about 400? What about 429?**

500: Server error. Transient. Retry with backoff. 400: Bad request. Your fault. Fix the request. Don't retry—same error. 429: Too many requests. Rate limited. *Definitely* retry with backoff. The server is telling you to slow down. Backoff gives it time. Respect Retry-After header if present.

---

## What Could Go Wrong? (Mini Disaster Story)

A payment gateway had a 30-second outage. Minor blip. But their 10,000 merchant integrations all retried immediately. No backoff. No jitter. 10,000 requests per second. All hitting the same recovering endpoint. The gateway—which was almost back—collapsed again. Outage extended to 2 hours. Engineers added exponential backoff to every integration. Next blip? A few retries. Scattered. Gateway recovered in 45 seconds. Lesson: your retry strategy doesn't just affect you. It affects everyone. Backoff is etiquette. Jitter is kindness.

---

## Surprising Truth / Fun Fact

The idea of exponential backoff came from Ethernet. In the 1970s, when two stations transmitted at once, they collided. Station would wait 1 slot, retry. Collide again? Wait 2 slots. Then 4. Then 8. Spread out. Find a gap. Computer networks learned this 50 years ago. Distributed systems are still learning it today.

---

## Quick Recap (5 bullets)

- **Retry** on transient failures (5xx, timeouts)—they often clear up.
- **Exponential backoff** = wait 1s, 2s, 4s, 8s... each retry waits longer.
- **Jitter** = add random delay to prevent all clients retrying at once (thundering herd).
- **Max retries** = 3-5 attempts, then fail gracefully. Don't retry forever.
- **Don't retry** on 4xx (client error)—fix the request instead.

---

## One-Liner to Remember

**Retry when things fail. But wait longer each time. Exponential backoff—because hammering a struggling server only makes it deader.**

---

## Next Video

Next: **Circuit Breaker**—when to stop retrying entirely. One switch that saves entire systems. Stay tuned.
