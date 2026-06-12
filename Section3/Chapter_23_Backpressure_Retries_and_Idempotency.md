# Chapter 23: Backpressure, Retries, and Idempotency — Keeping Systems Alive Under Pressure

*(Note to reader: This chapter is about a fundamental truth in distributed systems — the systems that stay alive under pressure are not the ones with the most servers. They are the ones that know how to say "slow down," how to try again carefully, and how to make sure that trying again does not cause double trouble. Every concept here comes from real production outages at real companies. Netflix lost customers for hours because of retry storms. Amazon has caused double charges because of missing idempotency. Stripe built one of the most elegant idempotency systems in the industry. We will learn all of it. No jargon without explanation. No concept without an analogy you have already lived.)*

---

## The Big Opening Story — Friday Night at the Restaurant

Imagine a restaurant called "The Golden Plate." On a normal Friday night, it serves 100 customers per hour. The kitchen has 10 chefs, 20 tables, and a system that works smoothly. The waiters know every customer. The chefs know every dish. Orders go in, food comes out, everyone is happy.

Now imagine a food blogger with 2 million followers posts a five-star review on a Tuesday. By Friday, the entire city wants to eat at The Golden Plate. Four hundred customers show up in the first hour.

The restaurant has three choices. What it does next determines whether Friday night is a triumph or a disaster.

---

### Option 1: Seat Everyone Immediately

The manager, desperate not to turn anyone away, seats all 400 customers at once.

Twenty tables. Four hundred people. Tables are crammed together. Extra chairs are dragged in from storage. The kitchen gets 400 orders at once. The 10 chefs, who can handle 100 orders per hour, are now staring down 400 orders. They start rushing. When you rush a chef, mistakes happen.

Order number 47: "medium-rare steak" gets cooked to well-done because the chef has no time to monitor it.

Order number 83: "no onions" — missed. Customer is allergic. This is now a medical situation.

Order number 119: belongs to Table 7. Gets delivered to Table 11. Table 11 eats it because they have been waiting so long they are not checking anymore.

The waiters, running between 20 crammed tables, start colliding with each other. One drops a tray. Another loses their notepad. Orders get duplicated, skipped, scrambled.

Four hours later: half the customers have left in frustration. The other half ate something but are unhappy. The Yelp review that originally brought them in is now buried under 200 one-star reviews about chaos and bad food. The restaurant's reputation, built over years, is damaged in one night.

This is what happens when a computer server tries to handle every request that arrives, no matter how many arrive. The server keeps accepting connections. Memory fills up. CPU is maxed. Responses start taking 30 seconds instead of 300 milliseconds. Errors multiply. Everything is slow, wrong, or broken — for everyone.

---

### Option 2: The Greeter Manages the Flow

The manager does something different. She positions a greeter — let's call her Maria — at the front door.

Maria greets every arriving group with warmth. She checks the current state of the restaurant. "We have 20 tables. 16 are full. We have 4 open right now. After that, the wait is about 30 minutes. Would you like to wait, or would you prefer to come back later?"

Some groups say "30 minutes is fine, we will wait at the bar." They wait. They get seated when a table opens. They receive full attention from the kitchen. Their food is prepared correctly and delivered at the right temperature.

Other groups say "30 minutes is too long, we will try somewhere else." They leave. That is okay. The restaurant cannot serve them well right now anyway. Better they leave than they stay, have a terrible experience, and leave a bad review.

Inside the restaurant: 20 tables. 100 customers per hour. Kitchen operating at 80% capacity — comfortable, sustainable, accurate. Chefs have time to care. Waiters have time to double-check orders. Every dish that goes out is correct.

That Friday night: the 120 customers who got seated had excellent experiences. The 280 who left went to other restaurants. The Golden Plate gets 120 five-star reviews and maintains its reputation.

This is backpressure. A system that controls its input rate to match its processing capacity. The load balancer (Maria the greeter) signals to incoming requests: "Wait," "Come back later," or "We are full." The service operates within its comfortable capacity and delivers quality results for those it accepts.

---

### Option 3: The Greeter Quotes the Worst Possible Wait

What if Maria, trying to be accurate, quotes the absolute maximum wait time under the worst scenario?

"Four hundred people are trying to eat here tonight. If you join the queue, the wait is approximately 90 minutes."

Nobody wants to wait 90 minutes for dinner. Every group turns around and leaves. The restaurant, which could comfortably serve 100 customers per hour, serves zero customers that night. The kitchen sits idle. The chefs are paid to do nothing. Revenue: zero. An entirely wasted night.

This is a system with too-aggressive backpressure — one that rejects so much work that it wastes its own capacity. The right answer is not "reject everything" any more than it is "accept everything." It is calibrate carefully: accept what you can handle well, turn away what you cannot.

---

### Now Extend the Story: The Retry Problem

You were seated. You are at Table 7. Your waiter takes your order: grilled salmon, medium, with asparagus. You are excited. Twenty minutes pass. The waiter brings a plate. You look at it.

It is chicken. Not salmon.

The waiter, mortified, takes it back. He tells the kitchen: wrong dish for Table 7, need the salmon.

Here is where the retry problem begins.

The kitchen is slammed. It is Friday night and there are 80 other orders ahead of yours. Your salmon is re-queued. The waiter, anxious and wanting to make things right, goes back to the kitchen every 30 seconds to ask: "Is Table 7's salmon ready yet?"

Every time he asks, a chef has to stop what they are doing, look up from the other 80 orders, check the status, say "not yet," and go back to cooking. The waiter is creating extra interruptions in a kitchen that is already at maximum capacity. Your salmon is not coming faster. It is coming slower — because every 30-second check steals 10 seconds of chef attention away from actually cooking.

This is a retry storm. The client (waiter) hammers the server (kitchen) with repeated requests. Each request creates work. That work reduces the server's capacity to actually do the original job. The thing the client wants most — the salmon — is delayed by the very act of repeatedly asking for it.

And now the worst part: the charge. When you ordered, the restaurant's policy is to hold your credit card. When the wrong dish arrived and you sent it back, the card was charged anyway (the kitchen made the dish). When you reordered and the salmon finally arrived, the card was charged again.

You just paid for both the chicken you did not eat and the salmon you did eat.

This is the idempotency problem. Because the order system has no memory of "we already charged this table for this order," it charges again. The retry caused a duplicate effect.

---

### The Three Concepts in One Story

Here is the summary before we go deeper:

**Backpressure** = Maria the greeter managing the front door. Control how much work enters the system so the system can do that work well. Without backpressure, everything degrades for everyone.

**Retries** = The waiter going back to the kitchen every 30 seconds. Retries are supposed to handle situations where something went wrong temporarily. But done wrong — too fast, too often, all at once — retries make the problem dramatically worse.

**Idempotency** = Preventing the double-charge. When you retry an operation (reorder the salmon), the system should recognize "we already started processing this" and not create a duplicate effect (double charge). An idempotent operation can be executed multiple times and only happen once.

Three concepts. One restaurant story. This chapter explains all three, the math behind them, and how to implement them correctly in production systems.

---

## Chapter at a Glance

Before diving into the details, here is the full picture of what we are building toward. Read through this box now. You will not understand everything yet — that is fine. Come back to it after you finish the chapter and it will all make sense.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║         CHAPTER 23: BACKPRESSURE, RETRIES, AND IDEMPOTENCY                 ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║   THE STABILITY TRIANGLE                                                     ║
║   ─────────────────────────────────────────────────────────────────────     ║
║                                                                              ║
║              ┌─────────────────────────────┐                                ║
║              │       BACKPRESSURE          │                                ║
║              │  Controls input rate        │                                ║
║              │  Prevents overload          │                                ║
║              │  Token bucket, rate limit   │                                ║
║              └──────────┬──────────────────┘                                ║
║                         │                                                    ║
║              "Only take │ work you can handle"                               ║
║                         │                                                    ║
║         ┌───────────────┴──────────────────┐                                ║
║         │                                  │                                ║
║ ┌───────┴──────────┐           ┌───────────┴──────┐                         ║
║ │     RETRIES      │           │   IDEMPOTENCY    │                         ║
║ │  Handle transient│           │  Makes retries   │                         ║
║ │  failures safely │           │  safe to do      │                         ║
║ │  Exponential     │           │  Idempotency key │                         ║
║ │  backoff + jitter│           │  Deduplication   │                         ║
║ └──────────────────┘           └──────────────────┘                         ║
║                                                                              ║
║   HOW THEY WORK TOGETHER                                                     ║
║   ─────────────────────────────────────────────────────────────────────     ║
║                                                                              ║
║   Backpressure alone:  System stays healthy, but transient errors            ║
║                        lose requests permanently                             ║
║                                                                              ║
║   Retries alone:       Transient errors are handled, but bad retries         ║
║                        crash the server. And users get double-charged.       ║
║                                                                              ║
║   Idempotency alone:   Retries are safe, but without backpressure,          ║
║                        the server is still overwhelmed                       ║
║                                                                              ║
║   ALL THREE TOGETHER:  Stable. Resilient. Safe. Production-ready.           ║
║                                                                              ║
║   THE CHAIN OF NECESSITY                                                     ║
║   ─────────────────────────────────────────────────────────────────────     ║
║   "No idempotency + retries = double charges"                                ║
║   "No backpressure + retries = retry storm = outage"                         ║
║   "No retries + backpressure = transient errors lost forever"                ║
║                                                                              ║
║   KEY NUMBERS TO KNOW                                                        ║
║   ─────────────────────────────────────────────────────────────────────     ║
║   Exponential backoff:   Starts at 100ms, doubles each attempt               ║
║   Maximum backoff cap:   30 seconds (users won't wait longer)                ║
║   Jitter range:          ±25% of calculated delay                            ║
║   Circuit breaker trips: At 50% error rate over 10-second window            ║
║   Circuit open duration: 30-60 seconds (service restart + warmup)           ║
║   Token bucket rate:     Refills at capacity / second                        ║
║   Max retry attempts:    3-5 (more = problem is not transient)               ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

Let us talk about how these three concepts relate to each other, because the relationship matters as much as the individual concepts.

Think of a restaurant kitchen as a machine. Backpressure is the greeter at the front door. She decides how many customers enter. Without her, the kitchen gets overloaded and everything goes wrong. But even with a perfectly managed front door, things still go wrong inside the kitchen — a dish is dropped, an order is misread, a stove malfunctions. These are transient failures. Retries handle them: try making the dish again.

But here is the catch. If the retry creates a duplicate entry in the kitchen order system, the customer gets charged twice and two dishes are made instead of one. Idempotency is the solution: the kitchen order system checks whether this order has already been processed before starting again. "Did we already start this salmon? Yes? Then do not start it again — just check its current status."

The three concepts form a triangle where each one depends on the others. A system with all three can survive most real-world failure scenarios gracefully. A system missing any one of the three has a specific, predictable failure mode. The rest of this chapter is about understanding each corner of that triangle deeply enough to implement it correctly.

---

## L5 vs L6 on This Topic

Before we go into the mechanics, it is worth understanding how junior engineers (L5) and senior engineers (L6) think differently about these problems. The difference is not about knowing more tools. It is about asking better questions first.

| Scenario | L5 Approach | L6 Approach |
|---|---|---|
| Service is timing out | "Add retries to handle the timeouts" | "First: why is it timing out? Retries on a constantly-overloaded service make the problem worse — this might be a retry storm in the making. Is the error transient (happens sometimes) or permanent (always happening)? If always, retries accomplish nothing." |
| User got double-charged | "Find the bug in the payment code" | "The bug is in the architecture, not the code. Any payment system without idempotency keys will produce double charges under normal network retry conditions. Fix the architecture first." |
| Traffic spike incoming | "Scale up servers before the spike" | "What is the realistic capacity after scaling? Set backpressure thresholds before the spike arrives — decide in advance what you will reject. Scaling during a spike is often too slow to help." |
| Circuit breaker tripping | "Increase the failure threshold so it stops tripping" | "The circuit breaker is telling you something is wrong with the downstream service. Increasing the threshold means ignoring the warning. Fix the underlying issue — the circuit breaker is protecting you, not lying to you." |
| Retry with immediate backoff | "Add a 100ms sleep between retries" | "Fixed interval creates synchronized retry waves. Use exponential backoff with jitter — random variation in timing prevents all clients from hammering the recovering service at the same moment." |

The pattern you see in the L6 column is consistent: they ask "why" before reaching for a tool. When a service times out, adding retries is the obvious tool. But the L6 question is: why is it timing out? If it is timing out because it is overloaded, adding retries is gasoline on the fire. The root cause must be understood before the solution is chosen.

This chapter gives you the vocabulary and understanding to ask those "why" questions. Once you understand what retry storms actually are, circuit breakers make intuitive sense. Once you understand what idempotency actually solves, idempotency keys are obvious. The tools make sense when you understand the problems they solve.

---

# Part 1: Why Retries Cause Outages

## The Retry Paradox

Here is a sentence that sounds wrong until you think about it carefully:

**Retries are supposed to help. But done wrong, retries are how a small problem becomes a complete outage.**

Let us understand why.

A transient failure is a temporary problem that goes away on its own. Examples:

- A database server had a brief spike in memory usage, and your request arrived at the worst possible moment. Try again in 500ms and it works fine.
- A network packet was dropped between two servers. Try again immediately and the second packet goes through.
- A service was restarting and was unavailable for 3 seconds. Try again after 5 seconds and it is fully operational.

Retries are designed for these scenarios. They are genuinely useful for transient failures. The problem is that most engineers implement retries without thinking carefully about timing, volume, or what to do when the retries themselves become the problem.

---

## The Traffic Jam Analogy

Think about a freeway during rush hour. Traffic is moving at 10 miles per hour instead of the usual 65. Some impatient drivers decide to take surface streets instead.

Here is what happens. Those surface streets normally carry light traffic — maybe 100 cars per hour. Now 500 extra cars are routing through them. The surface streets become gridlocked too. Now both the freeway AND the surface streets are slow. Total traffic in the metro area is worse than if those 500 cars had just stayed on the freeway and waited.

The drivers who left the freeway did not fix anything. They redistributed the problem and amplified it.

Bad retries work exactly the same way. A server is struggling under load — it is at capacity, handling requests slowly. Clients start timing out. They retry. Those retries are additional requests on top of the original load. The server, which was already at 100% capacity, is now receiving 150% of what it can handle. More requests fail. More retries happen. 200% of capacity. Everything fails. The entire service goes down.

The server capacity did not change. The retry behavior turned a "some requests are slow" problem into a "nothing works at all" catastrophe.

---

## The Mathematics of Destruction

Let us make this concrete with numbers. Walk through the spiral step by step.

A service can handle exactly 800 requests per second. One thousand clients each send 1 request per second.

```
T=0: Initial State
─────────────────────────────────────────────────────────
Load Arriving at Server:    1,000 requests/second
Server Capacity:              800 requests/second
Excess (goes to failure):     200 requests/second
Failure Rate:                  20%

200 clients see failures. They retry IMMEDIATELY (bad practice).
```

```
T=1: After First Retry Wave
─────────────────────────────────────────────────────────
Original load:              1,000 requests/second
First-wave retries:           200 requests/second
Total arriving at server:   1,200 requests/second
Server Capacity:              800 requests/second
Failures this second:         400 requests
Failure Rate:                  33%

400 clients are now failing. They all retry.
```

```
T=2: After Second Retry Wave
─────────────────────────────────────────────────────────
Original load:              1,000 requests/second
Second-wave retries:          400 requests/second
Total arriving at server:   1,400 requests/second
Server Capacity:              800 requests/second
Failures this second:         600 requests
Failure Rate:                  43%

600 clients failing. 600 retry.
```

```
T=3: After Third Retry Wave
─────────────────────────────────────────────────────────
Total arriving at server:   1,600 requests/second
Capacity:                     800 requests/second
Failures:                     800 requests
Failure Rate:                  50%
```

```
T=4: Complete Collapse
─────────────────────────────────────────────────────────
Original 1,000 + accumulated retries = 2,000+ requests/second
Server Capacity:              800 requests/second
Failures:                   1,200 requests
Failure Rate:                  60%+

Every new request fails. Every failed request retries.
The system is now in a death spiral.
```

Here is that spiral visualized as a chart:

```
RETRY DEATH SPIRAL — Load vs. Time
─────────────────────────────────────────────────────────────────

Load        ████████████████████████████████████████████████████
(req/sec)   ██    Total Load (original + retries)              ██
            ██                                                  ██
2000 ──────────────────────────────────────────────────────► ████
            │                                               ████
1600 ─────────────────────────────────────────────────── ████
            │                                         ████
1200 ──────────────────────────────────────────── ████
            │                                  ████
  800 ──── ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ ← SERVER CAPACITY (stays flat)
            │                                  ████
  400 ──────────────────────────────────────────────── ████
            │                                              ████
    0  ─────┴──────┬────────┬────────┬────────┬────────►
                  T=0      T=1      T=2      T=3      T=4
                                                    ▲
                                              FULL OUTAGE

Failure     ████
Rate        ██    Failure Rate                                   ██
            ██                                                  ██
 100% ──────────────────────────────────────────────────────► ████
            │                                               ████
  60% ──────────────────────────────────────────────── ████
            │                                       ████
  43% ────────────────────────────────────────── ████
            │                               ████
  33% ──────────────────────────────── ████
            │                     ████
  20% ─────────────────────── ████
            │            ████
   0% ──────┴──────┬────────┬────────┬────────┬────────►
                  T=0      T=1      T=2      T=3      T=4
```

Read that chart carefully. The server capacity — the flat line at 800 requests/second — never changed. Not by a single request. The server did not get slower. The server did not get worse. The only thing that changed was client retry behavior. Bad retries transformed a "20% of requests are slow" situation into "100% of requests are failing."

This is the retry paradox. The retries that were supposed to help each individual client make their request succeed ended up ensuring that no request could succeed. When every client retries simultaneously and immediately, the collective behavior is catastrophic even though each individual behavior seemed reasonable.

This is why retry implementation is not a trivial detail. It is one of the most consequential engineering decisions in a distributed system.

---

## The Five Deadly Retry Sins

Real outages happen because engineers commit one or more of these five mistakes. Each one has a name, an analogy, a technical explanation, and a fix.

---

### Sin 1: Immediate Retry

**The analogy:** You walk up to an ATM. You insert your card, enter your PIN, request $200. The machine thinks for a moment, then displays: "Unable to process request." You immediately press the "Try Again" button. The machine displays: "Unable to process request." You press again. Again. Again.

The ATM is down because its connection to the bank's network is congested. That congestion does not clear in the 200 milliseconds between your button presses. Hammering the button does not unclog the network. It adds noise to an already struggling system and, if enough people do it simultaneously, can actually make the congestion worse.

**The technical reality:** A server that timed out because it was under heavy load is still under heavy load 10 milliseconds later. An immediate retry adds one more request to an already-overwhelmed queue. The chance of success is essentially zero. The cost is adding more load at the worst possible moment.

**The fix:** At minimum, add a wait before retrying. Even 100 milliseconds makes a meaningful difference. But a fixed wait introduces its own problem, which brings us to the second sin.

---

### Sin 2: Fixed-Interval Retry

**The analogy:** Imagine 1,000 people setting their alarm clocks to wake up at exactly 7:00:00 AM. Not 6:58. Not 7:02. Exactly 7:00:00. They all wake up at the same second. They all reach for their phones at 7:00:02. They all try to check their news app at 7:00:05.

The app's servers receive 1,000 simultaneous requests at 7:00:05. Maybe that is fine — the app is designed for it. But now imagine instead that 1,000 customers are waiting for a slow service to come back online. The service went down at 6:59:00. All 1,000 clients are set to retry exactly 60 seconds after failure. So at 7:00:00, all 1,000 clients retry simultaneously.

If the service has just barely recovered and can handle 200 requests per second, it receives 1,000 requests in the same instant. 800 of them fail. Those 800 retry again at T+60 seconds. Another retry wave. The service never gets a chance to stabilize because every 60 seconds it is hit by a synchronized wall of traffic.

**The technical name for this:** A "retry wave" or "thundering herd." When all clients use the same fixed retry interval, they stay synchronized. They fail together. They retry together. They fail together again.

**The fix:** Jitter. Add randomness to your retry intervals. Instead of all clients waiting exactly 1,000ms, have each client wait a random time between 750ms and 1,250ms. The retry attempts are now spread over a 500ms window instead of all hitting at exactly the same millisecond.

Here is the visual difference:

```
FIXED RETRY — All clients retry at T=1000ms
─────────────────────────────────────────────────────────────────
Requests
per 100ms

 200 │                          ████
     │                          ████
 150 │                          ████
     │                          ████
 100 │                          ████
     │                          ████
  50 │                          ████
     │                          ████
   0 ├────────────────────────────────────────────────────────►
     T=0     T=200    T=400    T=600    T=800   T=1000   T=1200

     200 clients all retry at exactly T=1000ms.
     Server receives a spike of 200 requests in 1 millisecond.
     This spike likely causes more failures.


JITTERED RETRY — Clients retry between T=750ms and T=1250ms
─────────────────────────────────────────────────────────────────
Requests
per 100ms

  50 │
     │
  40 │                     ████  ████  ████  ████  ████
     │                     ████  ████  ████  ████  ████
  30 │                     ████  ████  ████  ████  ████
     │                     ████  ████  ████  ████  ████
  20 │                     ████  ████  ████  ████  ████
     │                     ████  ████  ████  ████  ████
  10 │                     ████  ████  ████  ████  ████
     │                     ████  ████  ████  ████  ████
   0 ├────────────────────────────────────────────────────────►
     T=0     T=200    T=400    T=600    T=800   T=1000   T=1200
                                         ↑                  ↑
                                       T=750              T=1250

     Same 200 clients, but spread across a 500ms window.
     Server receives ~40 requests per 100ms — smooth, manageable.
     Service has a real chance to recover.
```

The total number of retry requests is identical in both scenarios. The difference is timing. Spreading the retries across time gives the recovering service a chance to handle them. Concentrating them in a single instant guarantees failure.

---

### Sin 3: Unbounded Retries

**The analogy:** You are trying to reach a friend on the phone. You call. No answer. You call again. No answer. You call again. An hour later, you have called 47 times. You have spent an hour of your life on this. You could have left a voicemail after the second try and moved on. At some point, accept that they are genuinely unavailable and stop.

**The technical reality:** A service that retries forever is a service that never returns to the caller. The calling code is stuck in an infinite retry loop. Memory fills with pending retry state. From the outside, the system appears completely frozen. Users see no response. Timeouts cascade upward through the call chain.

Worse: if you have multiple layers of services all retrying forever, you have a retry explosion. Service A calls Service B which calls Service C. C is down. B retries C forever. A retries B forever. Now B is getting hammered by A's retries while it itself is hammering C. Three layers of infinite retries create a geometric explosion of requests.

**The fix:** Always set a maximum number of attempts (3-5 is typical) and a maximum total time budget for retrying. Example: "Try up to 4 times. But if we have spent more than 30 seconds total on retries, give up immediately regardless of attempt count." Return an error to the caller. Let the caller decide what to do. Fail fast rather than fail slowly.

---

### Sin 4: Retrying Non-Retryable Errors

**The analogy:** A student sends an email to a professor: "Here is my assignment. Attachment: homework.docx." The professor replies: "I do not see any attachment."

The student sends the exact same email again. With no attachment. The professor replies: "I do not see any attachment."

The student sends the exact same email a third time. Frustrated now.

No number of retries will fix this. The attachment is missing from the email. The email needs to be corrected, not resent. Retrying the wrong email is wasted effort.

**The technical reality:** HTTP responses come with status codes that tell you exactly what went wrong. Some errors are worth retrying. Others are not.

| HTTP Code | What It Means | Worth Retrying? |
|---|---|---|
| 400 Bad Request | Your request is malformed or missing required fields | NO — the request has a bug, fix the request |
| 401 Unauthorized | Wrong or missing authentication credentials | NO — fix the credentials, not the retry count |
| 403 Forbidden | You are authenticated but not allowed to do this | NO — you need different permissions, not more retries |
| 404 Not Found | The resource does not exist at this URL | NO — it is not coming back, the URL or ID is wrong |
| 408 Request Timeout | Server gave up waiting for your request | YES — try again, the server was temporarily busy |
| 429 Too Many Requests | You are sending too fast, slow down | YES — but wait for the "Retry-After" duration first |
| 500 Internal Server Error | The server crashed or had an unexpected error | MAYBE — try once, if it fails again, stop |
| 502 Bad Gateway | A proxy between you and the server had a problem | YES — network issues are typically transient |
| 503 Service Unavailable | The server is temporarily overloaded | YES — wait, then retry with backoff |
| 504 Gateway Timeout | The upstream server took too long | YES — with exponential backoff |

The key distinction is: errors in the 400-range are "your fault" errors — your request is wrong, and retrying the same wrong request accomplishes nothing. Errors in the 500-range are "server's fault" errors — the server had a problem, and it might not have that problem on the next attempt.

A common mistake: blindly retrying all errors regardless of type. This means retrying 401 errors (wrong password), which is not only useless but can trigger account lockouts on some systems. It means retrying 404 errors, which can look like polling a resource into existence (it will never exist). It means retrying 400 errors when the client's code has a bug — the engineer sees "it retried 5 times" and thinks the system is resilient, when actually it just wasted 5 attempts on an unfixable request.

---

### Sin 5: Ignoring Retry-After Headers

**The analogy:** You call a restaurant to make a reservation. The host says: "We are fully booked right now. Try calling back at 6pm, we should have availability then." You hang up and immediately call back. The host, slightly annoyed, says "I just told you — call back at 6pm." You hang up and call back again.

The host gave you specific information. Ignoring it and calling back immediately is both useless and rude. The same logic applies in server communication.

**The technical reality:** When a server returns a 429 (Too Many Requests) response, it often includes a header like:

```
Retry-After: 30
```

This means: "Wait 30 seconds before trying again. That is how long I need." It is not a suggestion. It is the server's actual assessment of when it will be ready to accept more requests.

Clients that ignore this header and retry in 1 second or 5 seconds are ignoring explicit, accurate information. They will fail again (the server is still at capacity). They are adding unnecessary load to a struggling server. They are being rude to a server that is trying to help them.

**The fix:** Always inspect the Retry-After header. If it is present, wait exactly that long (or longer, with jitter). The server knows its own state better than you do.

---

## Correct Retry Implementation

Now that you know the five sins, let us build the correct implementation. The standard is called **Exponential Backoff with Jitter** and it has been battle-tested by Google, Amazon, Netflix, and every serious distributed systems company.

**The concept in plain English:**

Imagine you knock on a neighbor's door. No answer. You wait 30 seconds. Knock again. No answer. You wait a minute. Knock again. No answer. You wait 2 minutes. Knock again.

Each time you try and fail, you double your patience. You are being respectful of the fact that your neighbor might be busy. If they are not home, more knocking does not help. If they are temporarily occupied, giving them more time is the right response.

**The numbers:**

```
EXPONENTIAL BACKOFF SCHEDULE
─────────────────────────────────────────────────────────────────
Attempt │ Wait Before Retry  │ Wait With Jitter (±25%)
────────┼────────────────────┼─────────────────────────────────
  1st   │ (try immediately)  │ (no wait — first attempt)
  2nd   │ 100ms              │ 75ms to 125ms
  3rd   │ 200ms              │ 150ms to 250ms
  4th   │ 400ms              │ 300ms to 500ms
  5th   │ 800ms              │ 600ms to 1,000ms
  6th   │ 1,600ms            │ 1,200ms to 2,000ms
  7th   │ 3,200ms            │ 2,400ms to 4,000ms
  8th   │ 6,400ms            │ 4,800ms to 8,000ms
  9th   │ 12,800ms           │ 9,600ms to 16,000ms
 10th   │ 30,000ms (capped)  │ 22,500ms to 30,000ms (capped)
        │                    │
        ← doubles each time  ← random within range
        
Note: Most systems stop at attempt 3-5. The table shows more
attempts only to illustrate the doubling pattern.
```

Why cap at 30 seconds? Because no reasonable user will wait more than 30 seconds for a response. If the retry wait is longer than 30 seconds, the user has already given up. There is no point in continuing to retry in the background for a user who has closed the browser tab or abandoned the app.

---

### The Production Code

Here is a real implementation with plain-English comments on every line:

```python
import random
import time

# These two exceptions let us distinguish between
# "try again, it might work" vs "don't bother, it won't work"
class TransientError(Exception):
    """A temporary problem. Worth retrying. Examples: 503, 429, 408"""
    pass

class PermanentError(Exception):
    """A permanent problem. Not worth retrying. Examples: 400, 401, 404"""
    pass

def retry_with_backoff(
    operation,           # The function we want to call (e.g., make_payment)
    max_attempts=5,      # Stop after this many tries (don't retry forever)
    base_delay_ms=100,   # Start with 100ms wait after first failure
    max_delay_ms=30000   # Never wait longer than 30 seconds
):
    """
    Call `operation` with exponential backoff and jitter.
    Returns the result if any attempt succeeds.
    Raises the last exception if all attempts fail.
    """
    
    for attempt in range(max_attempts):
        # attempt=0 is the first try (not a retry)
        # attempt=1 is the first retry
        # attempt=4 is the fifth and final try (if max_attempts=5)
        
        try:
            result = operation()  # Try the operation
            return result         # It worked! Return the result immediately.
            
        except TransientError as e:
            # A transient error — maybe worth retrying
            
            if attempt == max_attempts - 1:
                # This was our last allowed attempt. Give up.
                # Re-raise the error so the caller knows what happened.
                raise e
            
            # Calculate how long to wait before the next attempt.
            # 2 ** attempt gives us: 1, 2, 4, 8, 16 ... (doubles each time)
            # Multiply by base_delay_ms (100ms) gives us: 100, 200, 400, 800, 1600...
            # min(..., max_delay_ms) caps it at 30,000ms (30 seconds)
            raw_delay = min(base_delay_ms * (2 ** attempt), max_delay_ms)
            
            # Add jitter: pick a random value between 75% and 125% of raw_delay
            # This prevents synchronized retry waves from multiple clients
            jitter_multiplier = random.uniform(0.75, 1.25)
            actual_delay_ms = raw_delay * jitter_multiplier
            
            # Wait the calculated time (convert milliseconds to seconds for sleep)
            time.sleep(actual_delay_ms / 1000.0)
            
            # Loop back to the top and try again
            
        except PermanentError as e:
            # A permanent error — retrying is pointless
            # Raise immediately without any more attempts
            raise e
```

Let us trace through an example. Suppose `operation` is a function that calls a payment API. The API is temporarily overloaded (503 error).

```
Attempt 0 (first try):
  - Calls the API
  - API returns 503 (Service Unavailable) → TransientError raised
  - attempt == 0, max_attempts - 1 == 4, so not the last attempt
  - raw_delay = min(100 * (2**0), 30000) = min(100 * 1, 30000) = 100ms
  - jitter: random between 75ms and 125ms, say 91ms
  - Sleeps 91ms
  - Loops back

Attempt 1 (first retry):
  - Calls the API
  - API returns 503 → TransientError again
  - attempt == 1, not the last attempt
  - raw_delay = min(100 * (2**1), 30000) = min(100 * 2, 30000) = 200ms
  - jitter: random between 150ms and 250ms, say 187ms
  - Sleeps 187ms
  - Loops back

Attempt 2 (second retry):
  - Calls the API
  - API returns 200 (OK) — the service recovered!
  - Returns the result immediately
  - Total time spent: 91ms + 187ms + a few ms for the successful call
  - About 280ms total. Perfectly acceptable.
```

Now let us trace a failure path — the API never recovers:

```
Attempt 0: 503 → sleep 91ms
Attempt 1: 503 → sleep 187ms
Attempt 2: 503 → sleep 392ms (jittered 400ms)
Attempt 3: 503 → sleep 798ms (jittered 800ms)
Attempt 4: 503 → attempt == max_attempts - 1, so raise the error

Total time: ~1.5 seconds before giving up and returning an error.
This is called "fail fast" — do not leave the caller waiting forever.
```

The key insight in the code: `2 ** attempt` is the source of the exponential growth. When `attempt = 0`, `2 ** 0 = 1`. When `attempt = 1`, `2 ** 1 = 2`. When `attempt = 2`, `2 ** 2 = 4`. When `attempt = 3`, `2 ** 3 = 8`. It doubles each time. That is what "exponential" means — the growth is driven by a power (exponent), not linear addition.

---

### The Retry Budget — Thinking at the Service Level

Individual retry logic protects one request. But what about the whole service?

Imagine your payment service makes 10,000 requests per second to the bank's API. The bank's API has a 1% error rate (100 failed requests per second). Each failed request retries up to 3 times. In a normal scenario, this is fine — 100 retries per second is trivial overhead on a 10,000 RPS service.

Now the bank's API has an incident. Error rate spikes to 30% (3,000 failed requests per second). Each of those retries 3 times. Retry load: 9,000 extra requests per second. Total load on the bank's API: 10,000 + 9,000 = 19,000 requests per second. If the bank's API capacity is 12,000 RPS, you have now pushed it past capacity — making the outage worse.

The retry budget approach says: "Retries should never consume more than X% of total capacity." Example: set the retry budget at 10% of total request capacity. If retries are consuming more than 10% of your service's outbound capacity, stop retrying and return errors.

**The gas station analogy:** During a fuel shortage, a gas station limits each car to 10 gallons instead of the usual 20. This means more cars get some fuel rather than fewer cars getting full tanks. The total available fuel is unchanged. The policy ensures the shortage is distributed fairly rather than concentrated.

A retry budget is the same idea: when the system is under stress (high error rate = fuel shortage), limit how much of your capacity goes to retries so that original requests still get resources.

---

## Circuit Breakers — Knowing When to Stop Trying Completely

### The Electrical Analogy

When your home has a problem with electrical wiring — maybe a short circuit, maybe a device drawing too much power — the circuit breaker trips. The circuit breaker is a physical switch that breaks the connection. Power to that circuit is completely cut.

The reason you want this: running electricity through a damaged circuit does not fix the damage. It makes it worse. It generates heat. It can cause a fire. The right response is to cut power, find the damage, fix it, then restore power.

A software circuit breaker works on the same principle. If a downstream service is failing repeatedly, continuing to send it requests is counterproductive. Each request that arrives at the failing service consumes its struggling resources. The service cannot recover under load. The right response is to stop sending requests, let the service recover, then cautiously resume.

---

### The Three States

A circuit breaker has exactly three states. Understanding these states and the transitions between them is the key to understanding how circuit breakers work.

**State 1: CLOSED**

"Closed" in electrical terms means the circuit is complete — electricity flows normally. In software terms: requests pass through to the downstream service normally.

While in the CLOSED state, the circuit breaker tracks outcomes. Every request that succeeds or fails is counted. The breaker calculates a rolling failure rate: "Of the last N requests in the past T seconds, what percentage failed?"

If the failure rate exceeds the threshold (typically 50%), the breaker transitions to OPEN.

**State 2: OPEN**

"Open" in electrical terms means the circuit is broken — electricity cannot flow. In software terms: ALL requests to the downstream service are immediately rejected without even making a network call.

This is the key mechanism. In the OPEN state, when your code calls `call_payment_api()`, the circuit breaker does not actually call the API. It immediately raises `CircuitOpenError("Service unavailable")`. No network request is made. The failure is instant (microseconds) rather than slow (30-second timeout).

Why is instant failure better than slow failure? Because slow failure blocks threads. If your service uses 100 threads to handle incoming requests, and each thread is waiting 30 seconds for a failing downstream service, all 100 threads are stuck. New requests cannot be handled. Your service appears dead.

With a circuit breaker in OPEN state: failures are instant. Threads are freed immediately. Your service can continue handling other requests (perhaps ones that don't require the failing dependency). The failure is contained.

The OPEN state lasts for a configured period — typically 30-60 seconds. This gives the downstream service time to recover.

**State 3: HALF-OPEN**

After the open period expires, the circuit breaker allows exactly ONE test request through. Just one.

If that request succeeds: the downstream service has recovered. The circuit breaker transitions back to CLOSED. Normal traffic resumes.

If that request fails: the downstream service is still struggling. The circuit breaker transitions back to OPEN for another 30-60 seconds.

Half-open is a "probe" state. You are testing reality with minimal risk. One request cannot overwhelm a recovering service. If it fails, you have lost very little. If it succeeds, you have confirmed recovery and can safely restore full traffic.

---

### The State Machine Diagram

```
╔════════════════════════════════════════════════════════════════╗
║            CIRCUIT BREAKER STATE MACHINE                       ║
╚════════════════════════════════════════════════════════════════╝

                    ┌─────────────────────────────────────┐
                    │                                     │
                    ▼                                     │
            ┌───────────────┐                            │
            │               │  ← Requests pass through   │
            │    CLOSED     │    normally                 │
            │               │                            │
            │  Counting     │                            │
            │  successes    │                            │
            │  and failures │                            │
            └───────┬───────┘                            │
                    │                                     │
                    │  Failure rate exceeds 50%           │
                    │  (e.g., 50 of last 100 failed)      │
                    │                                     │
                    ▼                                     │
            ┌───────────────┐                            │
            │               │  ← ALL requests instantly  │
            │     OPEN      │    rejected (no network     │
            │               │    call made)               │
            │  Failing fast │                            │
            │  No requests  │                            │
            │  to downstream│                            │
            └───────┬───────┘                            │
                    │                                     │
                    │  Timeout expires                    │
                    │  (e.g., 60 seconds passed)          │
                    │                                     │
                    ▼                                     │
            ┌───────────────┐                            │
            │               │  ← Allows ONE test         │
            │  HALF-OPEN    │    request through          │
            │               │                            │
            │  Probing for  │                            │
            │  recovery     │                            │
            └───────┬───────┘                            │
                    │                                     │
          ┌─────────┴──────────┐                         │
          │                    │                         │
          ▼                    ▼                         │
   Test succeeds!        Test fails!                     │
          │                    │                         │
          │                    └──────────────► OPEN     │
          │                        (reset timer,         │
          │                         try again in 60s)    │
          │                                              │
          └──────────────────────────────────────────────┘
                 Transition back to CLOSED
                 (normal operation resumes)


WHAT EACH STATE MEANS FOR A REQUEST ARRIVING RIGHT NOW:
─────────────────────────────────────────────────────────────────
CLOSED:    Request goes through to the downstream service.
           Network call is made. We wait for a response.

OPEN:      Request is instantly rejected. No network call.
           Caller gets an error in microseconds, not 30 seconds.

HALF-OPEN: If this is the test request, it goes through.
           If another request arrives, it is rejected.
           Only one request may pass during HALF-OPEN.
```

The transition arrows tell you the logic. CLOSED becomes OPEN when failures pile up. OPEN becomes HALF-OPEN when time passes. HALF-OPEN goes back to CLOSED on success or back to OPEN on failure.

After looking at this diagram, consider what life looks like without a circuit breaker during an outage. Every request to the downstream service waits 30 seconds for a timeout. Your service has 100 threads. After 100 slow requests, all 100 threads are stuck waiting. New requests cannot be handled at all. Your service is down — not because of the downstream service, but because of how you handle the downstream service's failure.

With a circuit breaker: the first few requests fail slowly (waiting for timeout). The breaker opens. Every subsequent request fails instantly. Threads are freed. Your service continues operating. Users get clear error messages ("payment service temporarily unavailable") instead of infinite loading spinners. The failure is contained, named, and fast.

---

### The Production Code

```python
import time

class CircuitOpenError(Exception):
    """Raised when the circuit is open and we refuse to attempt the call."""
    pass

class CircuitBreaker:
    def __init__(self, failure_threshold=0.5, timeout_seconds=60):
        # failure_threshold: if 50% of requests fail, trip the breaker
        self.failure_threshold = failure_threshold
        
        # timeout_seconds: how long to stay OPEN before trying again
        self.timeout_seconds = timeout_seconds
        
        # Start in normal (CLOSED) state
        self.state = "CLOSED"
        
        # Track counts in the current window
        self.failure_count = 0
        self.success_count = 0
        
        # When did the last failure happen? Used to calculate OPEN duration.
        self.last_failure_time = None
    
    def call(self, operation):
        """
        Try to call `operation`. The circuit breaker wraps the call and
        decides whether to allow it based on current state.
        """
        
        if self.state == "OPEN":
            # We are in OPEN state. Check if enough time has passed.
            time_since_failure = time.time() - self.last_failure_time
            
            if time_since_failure > self.timeout_seconds:
                # Enough time has passed. Transition to HALF-OPEN.
                # Allow one test request through.
                self.state = "HALF-OPEN"
                # Fall through to actually make the call
            else:
                # Still within the OPEN period. Fail fast.
                raise CircuitOpenError(
                    f"Circuit is OPEN. Service unavailable. "
                    f"Try again in {self.timeout_seconds - time_since_failure:.0f} seconds."
                )
        
        # State is either CLOSED or HALF-OPEN. Try the operation.
        try:
            result = operation()          # Make the actual call
            self._record_success()        # It worked — update counts
            return result
            
        except Exception as e:
            self._record_failure()        # It failed — update counts
            raise e                       # Re-raise so the caller sees the error
    
    def _record_success(self):
        """Called when a request succeeds."""
        self.success_count += 1
        
        if self.state == "HALF-OPEN":
            # The test request succeeded! Service has recovered.
            # Return to normal CLOSED state and reset counters.
            self.state = "CLOSED"
            self.failure_count = 0
            self.success_count = 0
    
    def _record_failure(self):
        """Called when a request fails."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == "HALF-OPEN":
            # The test request failed. Service is still struggling.
            # Go back to OPEN state.
            self.state = "OPEN"
            return
        
        # Calculate current failure rate
        total_requests = self.failure_count + self.success_count
        if total_requests == 0:
            return  # No requests yet, nothing to calculate
        
        failure_rate = self.failure_count / total_requests
        
        if failure_rate > self.failure_threshold:
            # Too many failures. Trip the breaker.
            self.state = "OPEN"
```

Let us trace through a real scenario:

```
Scenario: Payment API starts failing due to database overload

T=0: 100 requests → 50 succeed, 50 fail
     failure_rate = 50/100 = 0.50 = exactly at threshold
     Breaker trips. State: OPEN

T=0 to T=60: All incoming requests hit the OPEN state.
     CircuitOpenError raised immediately.
     No network calls made. Threads freed instantly.
     Your service handles other requests fine.

T=60: First request after timeout arrives.
      Breaker transitions to HALF-OPEN.
      This request is allowed through.

     Case A: Payment API has recovered. Request succeeds.
             Breaker transitions to CLOSED.
             Normal traffic resumes at T=60.

     Case B: Payment API still struggling. Request fails.
             Breaker transitions back to OPEN.
             Reset the 60-second timer. Try again at T=120.
```

The circuit breaker is not magic. It does not fix the downstream service. What it does is protect your service from being dragged down by the downstream service's failure, give the downstream service time to recover without being hammered by traffic, and give your users fast, clear errors instead of slow, mysterious timeouts.

---

### What Circuit Breakers Protect Against: Cascading Failures

Here is the scariest scenario in distributed systems: a failure in one service causes failures in other services, which cause failures in yet more services, until a small problem becomes a total system collapse. This is called a cascading failure.

Consider a typical e-commerce architecture: the web server calls the order service, which calls the inventory service, which calls the database.

```
Web Server → Order Service → Inventory Service → Database
    ↑                                               ↓
    └────────────────────────────────────────────── ┘
                (database becomes slow)

Without circuit breakers:
─────────────────────────────────────────────────────────────────
1. Database becomes slow (maybe due to a maintenance operation)
2. Inventory Service: requests to DB take 30 seconds each
3. Inventory Service threads: 100 threads × 30 seconds = stuck
4. Inventory Service: cannot handle new requests (all threads busy)
5. Order Service: calls to Inventory Service now time out (30 seconds)
6. Order Service threads: 100 threads × 30 seconds = stuck
7. Order Service: cannot handle new requests
8. Web Server: calls to Order Service now time out (30 seconds)
9. Web Server threads: 100 threads × 30 seconds = stuck
10. Web Server: cannot handle new user requests
11. Users: website appears completely down

The database was slow. The website went down.
A single slow component cascaded through 3 layers.


With circuit breakers:
─────────────────────────────────────────────────────────────────
1. Database becomes slow
2. Inventory Service: requests to DB start failing/timing out
3. Circuit breaker in Inventory Service trips (50% failure rate)
4. Subsequent requests to DB: instantly rejected by the breaker
5. Inventory Service threads: freed immediately (no 30s waits)
6. Inventory Service: returns "inventory service unavailable" quickly
7. Order Service: sees Inventory Service errors
8. Circuit breaker in Order Service trips
9. Order Service: returns "order service temporarily unavailable" quickly
10. Web Server: displays "Some features temporarily unavailable"
11. Users: see a degraded experience, not a completely broken site

The database was slow. The website degraded gracefully, not crashed.
Each circuit breaker contained the failure to its own layer.
```

This difference — full crash vs. graceful degradation — is what circuit breakers exist to create. They are one of the most important resilience tools in distributed systems.

---

## The Failure Decision Tree

When a request fails, you need a consistent process for deciding what to do. This decision tree, used universally in production engineering, walks you through the logic:

```
╔══════════════════════════════════════════════════════════════════╗
║              FAILURE DECISION TREE                               ║
╚══════════════════════════════════════════════════════════════════╝

                        ┌─────────────────┐
                        │  Request Failed  │
                        └────────┬────────┘
                                 │
                                 ▼
                   ┌─────────────────────────────┐
                   │  Is the error code          │
                   │  retryable?                 │
                   │                             │
                   │  NOT retryable:             │
                   │  400 Bad Request            │
                   │  401 Unauthorized           │
                   │  403 Forbidden              │
                   │  404 Not Found              │
                   └──────┬──────────────────────┘
                          │
              ┌───────────┴────────────┐
              │                        │
              ▼                        ▼
         NOT retryable            Retryable
              │               (408, 429, 500,
              │                502, 503, 504)
              │                        │
              ▼                        ▼
    Return error to            Is the circuit
    client immediately         breaker OPEN?
    (no retry)                      │
                            ┌───────┴────────┐
                            │                │
                            ▼                ▼
                         OPEN            CLOSED or
                            │            HALF-OPEN
                            │                │
                            ▼                ▼
                  Return "service     Have I exceeded
                  unavailable" fast   max retry attempts?
                  (circuit open)           │
                                  ┌────────┴────────┐
                                  │                  │
                                  ▼                  ▼
                            YES — exceeded     NO — attempts
                                  │            remain
                                  ▼                  │
                         Return error to             ▼
                         caller (fail fast)  Wait (exponential
                                             backoff + jitter)
                                                      │
                                                      ▼
                                               Retry request
                                               (go back to top)
```

This tree is not just a diagram. It should be implemented as a library that every service in your system uses. Writing this logic once and correctly is far better than having 50 different services each implement their own version with subtle bugs.

Netflix built a library called Hystrix that implemented this exact logic. It was one of the most important open-source releases in distributed systems engineering (now deprecated in favor of Resilience4j, which does the same thing more efficiently). The point: this is not simple enough to re-implement from scratch in every service. Use a battle-tested library.

---

## Real Numbers to Know

These numbers represent the accumulated experience of production engineering at large-scale companies. Memorize them. They will come up in every system design interview and every production incident review.

| Configuration | Typical Value | Why This Value |
|---|---|---|
| Max retry attempts | 3 to 5 | More than 5 means the problem is probably not transient |
| Base backoff delay | 100ms | Short enough to not hurt user experience, long enough to matter |
| Max backoff delay | 30 seconds | Users abandon anything that takes longer than 30 seconds |
| Jitter range | ±25% of calculated delay | Wide enough to spread retries, narrow enough to stay predictable |
| Circuit breaker failure threshold | 50% error rate | Half of requests failing means something is seriously wrong |
| Circuit breaker measurement window | 10 seconds of recent requests | Enough history to be meaningful, recent enough to respond quickly |
| Circuit open duration | 30 to 60 seconds | Typical service restart is 15-30s, plus warmup time |
| Half-open test requests | 1 | Enough to verify recovery without overwhelming the recovering service |
| Retry budget (whole service) | ≤ 10% of total capacity | Retries should be overhead, not the dominant traffic pattern |

A common mistake is treating these as one-size-fits-all. They are starting points. A payment processing service might use 3 retries with 30-second open duration (caution: double charges are catastrophic). An image resizing service might use 5 retries with 10-second open duration (failures are cheaper). Calibrate based on the cost of failure and the expected recovery time.

---

## Retry Storms — When Everyone Retries at Once

We saw the math earlier: bad retries turn a 20% failure rate into a 100% outage. Now let us look at the specific phenomenon called a retry storm, understand the amplification math in detail, and learn the strategies for breaking one.

---

### The Emergency Room Story

A hospital emergency room is overwhelmed on a Saturday night. Patients are waiting 4 hours to be seen. Some patients, after waiting 2 hours, leave and drive to a different hospital. That hospital is also overwhelmed (same Saturday night, same region). They wait another 2 hours there. Meanwhile, the first hospital calls their registered number: "We have a bed ready for you." But the patient is already at hospital two. The first hospital has wasted a staff member's time, a phone call, and a prepared bed.

At hospital two, more patients are arriving — including patients from hospital one. Hospital two is now handling its own patients plus the overflow from hospital one. Its wait time jumps from 2 hours to 5 hours. More patients leave hospital two. They go to hospital three.

This is a retry storm. The "patients" (client requests) are moving between "hospitals" (service replicas or clusters) in response to slow service. Each move brings the new destination closer to its own overload point. The aggregate medical system (your distributed service) is consuming far more resources than the actual medical need (actual user requests) warrants.

---

### The Amplification Math

Let us calculate exactly how many requests a retry storm generates. This math comes up in system design interviews and capacity planning discussions.

**Setup:** A service is experiencing failures. Each failed request retries N times. The failure rate is R (a number between 0 and 1, so 50% = 0.5).

**Formula for total requests per original request:**
`Total = 1 + R + R² + R³ + ... + R^N`

This is a geometric series. Let us plug in real numbers.

```
SCENARIO A: 3 retries, 50% failure rate
─────────────────────────────────────────────────────────────────
Original 1,000 requests:                           1,000
First retry (50% of 1,000 fail):                     500
Second retry (50% of 500 fail):                      250
Third retry (50% of 250 fail):                       125
Total requests to the server:                      1,875
Amplification factor:                              1.875×

The server handles 1,875 requests to serve 1,000 users.
Overhead: 875 extra requests (87.5% overhead)


SCENARIO B: 3 retries, 80% failure rate
─────────────────────────────────────────────────────────────────
Original 1,000 requests:                           1,000
First retry (80% of 1,000 fail):                     800
Second retry (80% of 800 fail):                      640
Third retry (80% of 640 fail):                       512
Total requests to the server:                      2,952
Amplification factor:                              2.95×

Nearly 3× the original load on a server that is already failing at 80%.


SCENARIO C: 5 retries, 99% failure rate (near-complete outage)
─────────────────────────────────────────────────────────────────
Original 1,000 requests:                           1,000
First retry (99% of 1,000 fail):                     990
Second retry (99% of 990 fail):                      980
Third retry (99% of 980 fail):                       970
Fourth retry (99% of 970 fail):                      960
Fifth retry (99% of 960 fail):                       950
Total requests to the server:                      5,850
Amplification factor:                              5.85×

A server that is already failing 99% of the time
is receiving ALMOST 6× the original request load.
This is why retry storms are self-reinforcing.
```

Here is the amplification factor visualized across failure rates:

```
RETRY AMPLIFICATION — How Much Extra Load Do Retries Add?
─────────────────────────────────────────────────────────────────
Amplification
Factor
(total load /    ·
original load) ·
               ·     (5 retries, 99% failure rate = 5.85×)
  6.0 ────────────────────────────────────────────────────────●
               ·
  5.0 ─────────────────────────────────────────────────────·
               ·                                         ·
  4.0 ──────────────────────────────────────────────── ·
               ·                              (5 retries)
  3.0 ───────────────────────────────────────·
               ·                          ·
  2.0 ────────────────────────────────── ●  ← (3 retries, 80% = 2.95×)
               ·                      ·
  1.5 ──────────────────────────────·
               ·            (3 retries)
  1.0 ─────── ●  ← (no retries = 1.0×, baseline)
               │─────────────────────────────────────────────►
              0%    20%    40%    50%    60%    80%    99%
                           Failure Rate

KEY INSIGHT: Amplification is worst when failures are worst.
When a service is barely working (high failure rate),
retries make it work even less.
```

The counter-intuitive truth: retries hurt the most exactly when you need them the most. When a service is at 99% failure rate, it desperately needs fewer requests, not more. But retries guarantee it gets more. This is why circuit breakers exist — to cut off retries completely when the service is clearly too broken to help.

---

### Breaking the Retry Storm — Four Strategies

**Strategy 1: The Retry Budget**

Already covered: set a maximum percentage of capacity that can go to retries. When the budget is exhausted, stop retrying and return errors. This keeps retry overhead bounded.

**Strategy 2: Circuit Breaker**

Already covered: when the failure rate is too high, stop sending requests entirely. No retries = no amplification. The circuit breaker is the most important defense against retry storms.

**Strategy 3: Token Bucket for Retries**

This is a rate-limiting mechanism applied specifically to retry attempts. Here is how it works:

Imagine you have a physical bucket that starts with 10 tokens in it. Each token represents permission to make one retry attempt.

```
TOKEN BUCKET FOR RETRIES
─────────────────────────────────────────────────────────────────

Start:  [●●●●●●●●●●]  10 tokens available

Request 1 fails. You want to retry.
Take a token: [●●●●●●●●●]   9 tokens left. Retry granted.

Request 2 fails. Take a token: [●●●●●●●●]   8 tokens left. Retry granted.
Request 3 fails. Take a token: [●●●●●●●]    7 tokens left. Retry granted.
Request 4 fails. Take a token: [●●●●●●]     6 tokens left. Retry granted.
Request 5 fails. Take a token: [●●●●●]      5 tokens left. Retry granted.
Request 6 fails. Take a token: [●●●●]       4 tokens left. Retry granted.
Request 7 fails. Take a token: [●●●]        3 tokens left. Retry granted.
Request 8 fails. Take a token: [●●]         2 tokens left. Retry granted.
Request 9 fails. Take a token: [●]          1 token left.  Retry granted.
Request 10 fails. Take a token: []          0 tokens left. Retry granted.

Request 11 fails. No tokens left.           Retry DENIED. Return error.
Request 12 fails. No tokens left.           Retry DENIED. Return error.

After 1 minute: bucket refills with 1 token.  [●]
Request 13 fails. Take the 1 token: []      Retry granted.

After another minute: [●]                   1 more retry available.
```

The token bucket forces retry pacing. You cannot retry faster than the bucket refills. This prevents a single client from flooding the server with retries, even if that client is experiencing very high failure rates.

The refill rate is the key parameter. Set it based on how many retries per minute you consider "acceptable overhead." A service that handles 1,000 requests/second might allow 100 retries/second (10% retry budget), so the token bucket refills at 100 tokens/second.

**Strategy 4: Exponential Backoff (already covered)**

The backoff itself reduces retry frequency over time. The longer a service has been unavailable, the longer the wait between retries. This means the amplification factor decreases over time as backoff intervals grow.

---

## The Metastable Failure State

This is one of the most important concepts in production systems engineering, and one of the least taught. It has its own technical name: metastability. But the underlying idea is deeply intuitive once you see the right analogy.

---

### The Traffic Standing Wave Analogy

Have you ever driven on a highway, hit heavy traffic, crawled for 20 minutes, then suddenly the traffic clears and you are back to normal speed — and there is no accident, no construction, no obvious cause? Just open road ahead?

This is a traffic standing wave. It is a real phenomenon studied by traffic scientists. Here is what causes it:

One car slows down slightly — maybe the driver glanced at their phone, or saw something at the roadside. The car behind has to brake more sharply (reaction time means you always brake harder than the car ahead). The car behind that brakes harder still. Backward propagation turns a tiny slowdown into a complete traffic jam. The original car is now miles ahead, moving at full speed. But the "jam" — a wave of braking — propagates backward through traffic like a sound wave.

The jam is self-sustaining. New cars continuously drive into it and feed it. It does not need the original cause anymore. The original cause is gone. The jam persists.

A metastable failure state in a computer system works exactly the same way. The original trigger disappears. The failure persists because the failure itself is now generating the conditions that sustain the failure.

---

### A Real Metastable Failure Story

Here is a realistic timeline. Read it carefully because this sequence has caused multi-hour outages at major companies.

```
T=0:00
Database has a routine garbage collection pause.
(Garbage collection = the database's internal cleanup process.
Normal. Expected. Lasts about 500 milliseconds.)

During those 500ms, all database queries are paused.
```

```
T=0:00 to T=0:00.5
Application servers are waiting for database responses.
1,000 threads are blocked on database calls.
The GC pause is 500ms. This is expected to be fine.
```

```
T=0:00.5
GC pause ends. Database is fully operational again.
HOWEVER: 1,000 threads have been waiting for 500ms.
They all resume simultaneously.
1,000 simultaneous requests arrive at the now-awake database.
```

```
T=0:01
Database is overwhelmed by the 1,000 simultaneous queries.
Response times spike to 2 seconds per query.
New application requests are still arriving.
Thread pool: 1,000 threads busy (still waiting from T=0:00.5 request flood)
No threads available for new requests.
New requests queue up. Queue fills. Requests time out.
```

```
T=0:05
Timed-out requests are being retried by clients.
Retry load: 500 additional requests per second.
Database: still handling the T=0:01 flood + new retries.
Thread pool: exhausted. Service appears down to users.
```

```
T=0:10 to T=4:00 (3 hours and 50 minutes later)
The original GC pause lasted 500 milliseconds. It ended at T=0:00.5.
But the system is still in a broken state at T=4:00 because:
  - Retry load keeps the database busy
  - Busy database means threads are always waiting
  - Threads always waiting means new requests time out
  - Timed-out requests retry
  - The loop feeds itself
```

```
The GC pause triggered the failure. The retry storm sustains it.
This is a metastable failure state.
```

---

### What Breaks the Metastable Failure State

The core problem: retries are generating more load than the system can recover from. Breaking the load is the solution.

**Circuit breakers break the loop** by stopping retries when the failure rate is too high. With a circuit breaker tripped, no retries are made. The database gets a chance to drain its request queue. Once it catches up, the circuit closes. Traffic resumes carefully.

**Timeouts on thread pools** break the exhaustion part of the loop. Instead of threads waiting forever for a database response, they time out after (say) 2 seconds. The thread is freed. New requests can use it. The pool does not fully exhaust.

**Jitter prevents synchronized restarts.** When a service restarts after an outage, all the clients that were retrying will attempt to reconnect simultaneously. Without jitter, this synchronized reconnection is its own mini-flood. With jitter, reconnection attempts spread over time and the restarting service can handle them.

**Load shedding** (covered in Part B of this chapter) is the final defense: the service explicitly rejects excess requests rather than queuing them. Rejected requests fail fast. They retry less. The queue never fills.

The metastable failure state is what makes production incidents so hard to handle under pressure. The system looks like it is down. Restarting it helps briefly. Then it crashes again. Restarting does not fix anything if the retry loop immediately reloads the server faster than it can warm up. Understanding metastability means you know to look for the retry-storm loop and break it at the source.

---

## Summary of Part 1

Before we move to Part 2 (Backpressure mechanisms and how to implement them) and Part 3 (Idempotency — making retries safe), let us consolidate what Part 1 established.

```
╔══════════════════════════════════════════════════════════════════════╗
║                  PART 1 SUMMARY: RETRIES                            ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  THE CORE INSIGHT                                                    ║
║  Retries are useful for transient failures. But bad retries          ║
║  turn small problems into complete outages.                          ║
║                                                                      ║
║  THE FIVE SINS                                                       ║
║  1. Immediate retry — adds load at the worst moment                  ║
║  2. Fixed-interval retry — creates synchronized retry waves          ║
║  3. Unbounded retries — never returns to the caller                  ║
║  4. Retrying non-retryable errors — pointless, can cause harm        ║
║  5. Ignoring Retry-After headers — ignores explicit server guidance  ║
║                                                                      ║
║  THE CORRECT APPROACH                                                ║
║  Exponential backoff: 100ms → 200ms → 400ms → 800ms → 1600ms        ║
║  Cap at 30 seconds maximum wait                                      ║
║  Add ±25% jitter to prevent synchronized retry waves                 ║
║  Maximum 3-5 attempts total                                          ║
║  Only retry retryable error codes (408, 429, 500, 502, 503, 504)    ║
║  Always honor Retry-After headers                                    ║
║                                                                      ║
║  CIRCUIT BREAKERS                                                    ║
║  Three states: CLOSED → OPEN → HALF-OPEN → CLOSED                   ║
║  Trip at 50% failure rate. Stay open 30-60 seconds.                 ║
║  Test with one request in HALF-OPEN before resuming normal traffic. ║
║  Prevent cascading failures by containing failure to one layer.     ║
║                                                                      ║
║  RETRY STORMS                                                        ║
║  Amplification factor = 1 + R + R² + ... + R^N                      ║
║  At 80% failure rate with 3 retries: 2.95× amplification           ║
║  Self-reinforcing: more retries → more load → more failures          ║
║  Break with: circuit breakers, retry budgets, token buckets         ║
║                                                                      ║
║  METASTABLE FAILURE STATES                                           ║
║  When the original trigger is gone but the failure persists         ║
║  because the failure itself generates the conditions that           ║
║  sustain it. Break the loop: circuit breakers + timeouts + jitter.  ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
```

Part 1 gave you the tools to handle failures gracefully — retry correctly, know when to stop retrying, protect yourself from downstream failures with circuit breakers, and recognize when you are in a retry storm or metastable state.

Part 2 (in the full chapter) covers backpressure: how to control the rate of incoming work before it overwhelms your system. This is the "Maria at the front door" half of the story.

Part 3 covers idempotency: how to make retries safe so that retrying a payment does not charge the user twice. This is the "double charge prevention" half of the story.

All three parts together give you the complete toolkit for building systems that stay alive under pressure — not just under normal conditions, but when things go wrong in the specific, predictable ways that real production systems fail.

---

## Interlude: Seeing These Concepts in the Real World

Before moving on, it helps to see these concepts appear in real products you probably use every day. This is not trivia. It is evidence that these problems are universal — every company that builds distributed systems has to solve them.

---

### How Stripe Handles Retries

Stripe processes billions of dollars of payments. A wrong retry can mean a merchant gets double-paid or a customer gets double-charged. Stripe's engineering blog describes their retry system in detail.

When a Stripe API call fails with a 500 or 503, Stripe recommends a specific retry strategy: start with a 200ms wait, double it each attempt, cap at 2 seconds, maximum 3 retries. Note the cap is 2 seconds — lower than our general 30-second recommendation — because payment UX requires faster feedback. If a payment has not gone through in 8 seconds total, users assume it failed and try again manually.

Stripe also handles the idempotency problem (covered in Part 3) by requiring clients to send an "Idempotency-Key" header with every payment request. This is their solution to the double-charge problem. If you retry with the same key, Stripe returns the cached result of the first attempt rather than running the payment again.

The key lesson from Stripe: retry parameters are not universal. They depend on the specific user expectation for your service. A payment has different timing constraints than a file upload or a search query.

---

### How AWS S3 Handles Retry Storms

Amazon S3 (Simple Storage Service) is one of the most-used infrastructure services in the world. At their scale, retry storms are a serious threat — if millions of clients simultaneously retry a failed operation, S3 faces billions of extra requests in seconds.

AWS publishes specific retry recommendations for S3 clients:
- Exponential backoff with full jitter (random between 0 and the calculated delay, not ±25%)
- Base delay of 200ms
- Maximum delay of 20 seconds
- Maximum 10 retry attempts for large file operations

The "full jitter" approach (random between 0 and calculated delay) is more aggressive than ±25% jitter and better at preventing synchronized retry waves at very large scales. When you have 10 million clients, even ±25% jitter can still create meaningful spikes. Full jitter spreads retries across the entire window.

---

### How Netflix Uses Circuit Breakers

Netflix engineers wrote the original Hystrix circuit breaker library and open-sourced it. Their blog posts describe the problem they were solving: Netflix's streaming service makes hundreds of service-to-service calls per user request. If even one downstream service slows down, it can hold threads across the entire call chain.

Their circuit breaker (Hystrix, now Resilience4j) wraps every external call. When a service starts failing:
1. Hystrix trips the circuit breaker
2. Subsequent calls immediately return a fallback (for example: "show popular movies from cache" instead of "load personalized recommendations from the recommendation engine")
3. Users see a degraded but functional experience rather than an error
4. The recommendation engine gets time to recover

The fallback is key to the Netflix approach. A circuit breaker that just returns an error is useful. A circuit breaker with a pre-built fallback that keeps the user experience functional is the gold standard. Users watching Netflix during a recommendation engine outage do not see an error page — they see "Top Picks" (a cached list) instead of "Recommended for You" (a personalized list). The distinction is invisible to most users.

---

### How Google Handles Retry Budgets

Google's Site Reliability Engineering book (the "SRE Book" — available free online) describes a technique called "retry budgets" in detail. Google services track what percentage of total outbound requests are retries. If retries exceed 10% of total traffic for any downstream service, the retry budget is exhausted and the service stops retrying for a period.

This number — 10% — is a rule of thumb that Google found effective across many services. It means: retries are overhead, not the primary workload. When retries become more than a small fraction of total traffic, something is seriously wrong with the downstream service and retrying is unlikely to help.

The SRE Book also discusses "load shedding" — dropping excess requests rather than queuing them — which connects directly to the backpressure mechanisms in Part 2.

---

## The Six Things To Remember About Retries Forever

This is a condensed reference — the six insights that will serve you in every system design interview and every production incident for the rest of your engineering career.

**1. Retries are load amplifiers.**
Every retry is an extra request. At high failure rates, retries multiply load. The formula is `1 + R + R² + ... + R^N`. At 80% failure rate with 3 retries, you are serving 2.95× the original request volume on an already-failing service.

**2. Synchronization is the enemy.**
Fixed retry intervals create retry waves. All clients retry at the same moment and re-overload the recovering service. Jitter (randomness in timing) breaks synchronization. Always add jitter. Always.

**3. Not all errors are worth retrying.**
400 Bad Request means your request is wrong. Retrying a wrong request is pointless. Only retry errors that represent temporary conditions: 408, 429, 500, 502, 503, 504. Build a clear retryable/non-retryable error classification at the start of every project.

**4. Circuit breakers stop the spiral.**
When failure rate is too high, retries make everything worse. A circuit breaker cuts off retries entirely and lets the downstream service recover. This is the most important mechanism for preventing retry storms from becoming full outages.

**5. Retries require idempotency.**
If you retry a payment without idempotency, you double-charge the customer. If you retry a database write without idempotency, you write duplicate records. Retries are only safe when the underlying operation is designed to handle being called multiple times. This is idempotency — the topic of Part 3.

**6. Metastable failures are self-sustaining.**
When the original failure trigger is gone but the system is still broken because retry load is sustaining the failure, you are in a metastable state. Recognize the pattern (high retry rate + high failure rate + no apparent trigger). Break it by cutting retries (circuit breaker or retry budget), not by restarting services.

---

## A Note on Testing Retry Logic

One of the most common mistakes in software development: engineers implement retry logic and never test it. The code looks correct. The unit tests pass. But in production, it behaves differently because:

- The test environment never actually delays responses by 30 seconds
- The test environment has one client, not 10,000 simultaneous clients
- The test environment does not simulate partial failures (some requests succeed, some fail)
- The test environment does not simulate recovery (service comes back online mid-test)

Testing retry logic properly requires chaos engineering. This means intentionally breaking things in production-like environments to see how the retry system responds. Netflix famously runs "Chaos Monkey" — a tool that randomly kills production servers to test that Netflix's retry and failover logic actually works.

You do not need Chaos Monkey to test your retry logic. But you do need:

- A staging environment that can simulate slow and failing dependencies
- Tests that send concurrent requests (not one-at-a-time)
- Tests that verify jitter is working (if all retries happen at the same millisecond, your jitter is broken)
- Tests that verify circuit breakers trip and reset correctly
- Load tests that measure amplification factor at different failure rates

Write these tests before you ship. Finding out your retry logic creates a retry storm in production is a bad Friday night for everyone involved.

---

## Quick-Reference Cheatsheet: Retry Decision Guide

```
╔══════════════════════════════════════════════════════════════════════╗
║              RETRY QUICK-REFERENCE                                   ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  BEFORE YOU ADD RETRIES, ASK:                                        ║
║  ● Is the failure transient? (sometimes fails, or always fails?)     ║
║  ● Is retrying safe? (could it double-charge, double-write?)         ║
║  ● Is the circuit breaker already open? (if yes, don't retry)        ║
║  ● Is this a retryable HTTP code? (400s = no, 500s = maybe)         ║
║                                                                      ║
║  BACKOFF FORMULA:                                                    ║
║  delay = min(base_ms × 2^attempt, max_ms) × random(0.75, 1.25)     ║
║                                                                      ║
║  WITH NUMBERS:                                                       ║
║  Attempt 1 → try immediately                                         ║
║  Attempt 2 → ~100ms (75-125ms after jitter)                          ║
║  Attempt 3 → ~200ms (150-250ms)                                      ║
║  Attempt 4 → ~400ms (300-500ms)                                      ║
║  Attempt 5 → ~800ms (600-1000ms)                                     ║
║  → After 5 attempts, give up and return the error                    ║
║                                                                      ║
║  CIRCUIT BREAKER THRESHOLDS:                                         ║
║  Trip at:    50% failure rate over a 10-second window               ║
║  Stay open:  30 to 60 seconds                                        ║
║  Test with:  1 request in HALF-OPEN state                            ║
║                                                                      ║
║  RETRY CODES — ALWAYS RETRY:                                         ║
║  408 Request Timeout                                                  ║
║  429 Too Many Requests (wait for Retry-After first)                  ║
║  502 Bad Gateway                                                      ║
║  503 Service Unavailable                                              ║
║  504 Gateway Timeout                                                  ║
║                                                                      ║
║  RETRY CODES — NEVER RETRY:                                          ║
║  400 Bad Request (fix the request)                                   ║
║  401 Unauthorized (fix the credentials)                              ║
║  403 Forbidden (you don't have permission)                           ║
║  404 Not Found (it doesn't exist)                                    ║
║                                                                      ║
║  RETRY CODES — RETRY ONCE ONLY:                                      ║
║  500 Internal Server Error (might be transient, might not be)        ║
║                                                                      ║
║  AMPLIFICATION AT DIFFERENT FAILURE RATES (3 retries):              ║
║  20% failure rate → 1.25× amplification (safe)                      ║
║  50% failure rate → 1.88× amplification (concerning)                ║
║  80% failure rate → 2.95× amplification (dangerous)                 ║
║  99% failure rate → 3.96× amplification (catastrophic)              ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Putting It All Together: A Complete Walkthrough

Let us walk through a single end-to-end scenario that combines everything from Part 1. This is the kind of walkthrough you should be able to do in a system design interview to demonstrate mastery.

**The scenario:** You are building an e-commerce checkout service. When a user clicks "Place Order," your service:
1. Calls the inventory service (reserve the items)
2. Calls the payment service (charge the card)
3. Calls the notification service (send confirmation email)
4. Writes to the orders database (record the order)

Your job: make this resilient using what you learned in Part 1.

---

### Step 1: Classify Each Call by Its Failure Characteristics

Before writing any retry code, classify each dependency:

```
DEPENDENCY CLASSIFICATION TABLE
─────────────────────────────────────────────────────────────────
Dependency         │ Retryable? │ Idempotent? │ Max Latency
───────────────────┼────────────┼─────────────┼──────────────
Inventory Service  │ YES        │ YES         │ 200ms
                   │ (503 when  │ (reserving  │ (user waiting)
                   │  overload) │  same item  │
                   │            │  twice is OK│
                   │            │  if deduped)│
───────────────────┼────────────┼─────────────┼──────────────
Payment Service    │ YES        │ MUST BE     │ 3,000ms
                   │ (network   │ (CRITICAL — │ (user will wait
                   │  errors)   │  NO double  │  for payment)
                   │            │  charges)   │
───────────────────┼────────────┼─────────────┼──────────────
Notification       │ YES        │ EVENTUALLY  │ 10,000ms
Service            │ (email     │ (duplicate  │ (async — don't
                   │  servers   │  email is   │  make user wait)
                   │  are flaky)│  acceptable)│
───────────────────┼────────────┼─────────────┼──────────────
Orders Database    │ YES        │ MUST BE     │ 100ms
                   │ (transient │ (NO double  │ (low latency
                   │  DB errors)│  records)   │  expected)
```

This table tells you what retry strategy and parameters each call needs. Payment and database writes are the most critical — they must be idempotent. Notification is the most lenient — a duplicate email is annoying but not catastrophic.

---

### Step 2: Wrap Each Call with a Circuit Breaker

Each of the four dependencies gets its own circuit breaker. They are independent. The inventory service being down should not trip the payment service circuit breaker.

```python
# Initialize one circuit breaker per dependency
inventory_breaker  = CircuitBreaker(failure_threshold=0.5, timeout_seconds=30)
payment_breaker    = CircuitBreaker(failure_threshold=0.3, timeout_seconds=60)  # more sensitive
notification_breaker = CircuitBreaker(failure_threshold=0.7, timeout_seconds=15)  # more lenient
database_breaker   = CircuitBreaker(failure_threshold=0.5, timeout_seconds=30)
```

Notice the different thresholds. Payment is more sensitive (trips at 30% failure) because a malfunctioning payment service is high-stakes. Notification is more lenient (trips at 70% failure) because the notification service being flaky is not user-facing.

---

### Step 3: Apply Retry Logic to Each Call

```python
def place_order(user_id, cart, payment_method):
    
    # Step 1: Reserve inventory
    # Retryable: yes. Max 3 attempts. Backoff: 100ms base.
    try:
        reservation = retry_with_backoff(
            operation=lambda: inventory_breaker.call(
                lambda: inventory_service.reserve(cart)
            ),
            max_attempts=3,
            base_delay_ms=100
        )
    except CircuitOpenError:
        return error("Inventory service temporarily unavailable. Try again in a moment.")
    except Exception:
        return error("Could not reserve items. They may be out of stock.")
    
    # Step 2: Charge payment
    # Critical: must use idempotency key to prevent double charge
    # Retryable: yes, but more cautious (max 2 attempts, longer backoff)
    order_id = generate_unique_order_id()  # This becomes the idempotency key
    
    try:
        charge = retry_with_backoff(
            operation=lambda: payment_breaker.call(
                lambda: payment_service.charge(
                    user_id=user_id,
                    amount=cart.total,
                    idempotency_key=order_id   # KEY: prevents double charge on retry
                )
            ),
            max_attempts=2,           # fewer attempts for payment
            base_delay_ms=500         # longer base delay for payment
        )
    except CircuitOpenError:
        # Release the inventory reservation before returning error
        inventory_service.release(reservation)
        return error("Payment service temporarily unavailable.")
    except Exception as e:
        inventory_service.release(reservation)
        return error(f"Payment failed: {e}")
    
    # Step 3: Write to database (synchronous — user waits for confirmation)
    try:
        order_record = retry_with_backoff(
            operation=lambda: database_breaker.call(
                lambda: orders_db.insert(
                    order_id=order_id,    # idempotency: same order_id = no duplicate
                    user_id=user_id,
                    cart=cart,
                    charge_id=charge.id
                )
            ),
            max_attempts=3,
            base_delay_ms=50
        )
    except Exception:
        # Payment succeeded but we couldn't record it — log urgently for manual review
        alert_oncall(f"CRITICAL: Payment {charge.id} succeeded but order not recorded")
        return error("Order partially processed. Our team will follow up.")
    
    # Step 4: Send notification (asynchronous — don't make user wait)
    # Fire and forget. If it fails, retry in background. User is already done.
    send_async(lambda: retry_with_backoff(
        operation=lambda: notification_breaker.call(
            lambda: notification_service.send_confirmation(user_id, order_record)
        ),
        max_attempts=5,    # more attempts OK — email is lower stakes
        base_delay_ms=1000 # longer delays OK — email is not time-critical
    ))
    
    return success(order_id=order_id)
```

This is not perfect production code — it is simplified for illustration. But it demonstrates the key principles:

- Each dependency has its own circuit breaker with appropriate thresholds
- Each retry call has appropriate `max_attempts` and `base_delay_ms` based on the stakes
- The payment step uses an `idempotency_key` (the `order_id`) to prevent double charges
- Steps are ordered by importance: reserve before charge, charge before record
- Failure at each step triggers appropriate cleanup (release inventory) or alerting
- Notification is asynchronous — user gets a response immediately, email sends in background

---

### Step 4: Think About What Happens During a Partial Outage

A good engineer walks through failure scenarios before going to production. Here are the four most likely failures and how this code handles them:

**Scenario A: Inventory service returns 503 (overloaded)**

Retry 1 at ~100ms: probably still failing (service still busy)
Retry 2 at ~200ms: possibly recovered (service had 300ms to breathe)
If retry 2 succeeds: order proceeds normally, user sees ~300ms delay
If retry 2 also fails: circuit breaker counts the failures
After enough failures: circuit trips, future requests immediately return "inventory temporarily unavailable"
User experience: slightly slower on first few failures, then fast errors with clear message

**Scenario B: Payment service is slow (taking 8 seconds per request)**

Attempt 1: starts. 8-second wait. This exceeds our configured timeout (3,000ms). Timeout fires.
retry_with_backoff catches the timeout (treated as TransientError).
Wait ~500ms. Attempt 2. Another 8-second request starts. Timeout fires again.
After 2 attempts: give up. Return payment error.
Circuit breaker: 2 failures recorded. If this is happening to many users, the 30% threshold trips quickly. Circuit opens. Future payment attempts immediately return fast errors.
User experience: 6 seconds of waiting (two 3-second timeouts) then an error. Not great, but bounded.

**Scenario C: Database write fails but payment succeeded**

This is the scary scenario. Money was taken, order was not recorded.
The code above logs an urgent alert and returns an error to the user.
On-call engineer gets paged. They find the orphaned charge and manually create the order record.
This is not automated — it is a manual recovery process. But it is caught immediately and bounded in scope.
The user gets an error message saying "our team will follow up" rather than a confusing hang.

**Scenario D: All three services simultaneously have elevated error rates (widespread incident)**

Circuit breakers for inventory, payment, and database all trip at roughly the same time.
New requests immediately return fast errors across the board.
The services are not hammered with retry traffic during the incident.
They have space to recover.
When services recover, circuit breakers transition to HALF-OPEN, test with one request each, and reopen on success.
Traffic resumes gradually. No retry storm.

---

### What This Walkthrough Demonstrates

The four steps — classify, circuit-break, apply retry logic, think through failure scenarios — are the right order of operations. Most engineers jump straight to step 3 (write retry code) without doing steps 1 and 2. The result is retry code that works in normal conditions and fails catastrophically in outage conditions.

The classification step forces you to think about idempotency (Part 3) before you write a single line of retry code. The circuit breaker step forces you to think about isolation — each dependency failing independently rather than one failure cascading through the entire checkout process. The failure scenario walkthrough forces you to find the edge cases before users do.

This is what L6 engineering looks like in practice. Not "add retries here." But: "classify the dependencies, set appropriate circuit breakers, write idempotency-safe retry logic, then walk through the four most likely failure scenarios to verify the behavior is correct."

---

## Vocabulary Glossary: Part 1

Here are all the technical terms introduced in Part 1, defined simply, in the order they appeared.

**Transient failure** — A temporary problem that goes away on its own. Examples: brief network packet loss, a server that was momentarily busy. Worth retrying.

**Permanent failure** — A problem that will not go away without intervention. Examples: invalid credentials, a resource that does not exist. Not worth retrying.

**Retry storm** — When many clients all retry at the same time, creating more load on an already-failing service, making the failure worse. Self-reinforcing cycle.

**Exponential backoff** — A retry strategy where the wait time between retries doubles with each attempt (100ms, 200ms, 400ms, 800ms...). Prevents hammering a recovering service.

**Jitter** — Randomness added to retry wait times to prevent all clients from retrying at exactly the same moment. Typically ±25% or fully random within the backoff window.

**Circuit breaker** — A component that monitors failure rates and temporarily stops all requests to a failing service. Has three states: CLOSED (normal), OPEN (all requests fail fast), HALF-OPEN (testing recovery with one request).

**CLOSED state** — Normal circuit breaker state. Requests pass through. Failures are counted.

**OPEN state** — Circuit breaker tripped. All requests immediately fail without network calls. Saves resources, allows service recovery.

**HALF-OPEN state** — Circuit breaker testing state. One request allowed through. If it succeeds, return to CLOSED. If it fails, return to OPEN.

**Cascading failure** — When one service's failure causes other services to fail, which cause more services to fail, until a small problem becomes a total outage. Circuit breakers prevent this.

**Retry budget** — A limit on how much capacity can be spent on retries. Typically expressed as a percentage (10% of total requests). When exhausted, retries stop regardless of failure rate.

**Token bucket** — A rate-limiting mechanism. Each retry costs a token. Tokens replenish at a fixed rate. When tokens run out, retries are denied until the bucket refills.

**Amplification factor** — How many total requests are sent for each original request, accounting for retries. Formula: `1 + R + R² + ... + R^N` where R is failure rate and N is max retries.

**Metastable failure state** — A self-sustaining failure where the original trigger is gone but the system remains broken because the failure itself (typically retry load) is generating the conditions that sustain the failure.

**Retry-After header** — An HTTP response header that tells clients how long to wait before retrying. Always honor it. It represents the server's own assessment of when it will be ready.

**HTTP 429 Too Many Requests** — The HTTP status code for "you are sending too fast." Always retryable, but only after waiting the duration specified in the Retry-After header.

**Fail fast** — Returning an error immediately rather than queuing a request that will eventually time out. Better for users (they get a clear error quickly) and better for services (threads are not blocked waiting).

**Graceful degradation** — A system continuing to operate in a reduced capacity rather than failing completely. Example: showing cached results when the live data service is down instead of showing an error page.

---

*End of Part A — Chapter 23: Backpressure, Retries, and Idempotency*

---

**What to remember from Part A:**

The restaurant on Friday night is not just an analogy. It is a precise model. Every distributed system faces the same choices the manager faced: let everyone in and collapse, manage the flow and maintain quality, or be so restrictive that you waste capacity. The right answer — carefully managed flow, clear communication, and graceful degradation — is the same in both cases.

Retries feel like the obviously correct solution to failures. Of course you should try again when something fails. But "try again" without careful thought about timing, volume, error types, and downstream impact is how companies have lost millions of dollars and millions of users in a single bad Friday night.

The circuit breaker, exponential backoff with jitter, retry budgets, and understanding of metastable failure states are not academic concepts. They are the difference between a system that handles a traffic spike gracefully and a system that turns a 500-millisecond database hiccup into a 4-hour outage. Every serious engineer who has been on-call for a production incident at a high-scale company has encountered at least one of these failure modes in the wild. Now you know what to call them, how they work, and how to prevent them.
# Chapter 23 — Part B: Idempotency and Backpressure

*(Note to reader: Part A covered retries and circuit breakers — how your system handles failure gracefully. Part B covers two more essential survival tools. First: idempotency — how to make it safe to retry operations that would normally cause problems if run twice. Second: backpressure — how your system tells upstream callers "slow down" before it collapses under too much traffic. These two topics work hand in hand with retries. Without idempotency, retries cause disasters. Without backpressure, no amount of clever retry logic prevents a total meltdown. Everything is explained from scratch. You do not need any prior knowledge beyond a basic sense of how apps talk to each other over a network.)*

---

# Part 2: Idempotency — Making Operations Safe to Repeat

---

## What Does "Idempotent" Mean?

The word "idempotent" sounds like it belongs in a math textbook. It does, actually — but the idea is shockingly simple once you see a good example. Let's start with an elevator.

---

### The Elevator Button Analogy

You step into an elevator. You press the button for the 3rd floor. It lights up. You press it again. Still lit. You press it five more times because you are impatient. You press it ten more times because you are very impatient.

What happens? You go to the 3rd floor. Once. Pressing the button ten times does not take you to the 3rd floor ten times. The elevator does not go up, come back to the lobby, go back up, come back, and loop ten times. It just goes up once and stays there.

**That button is idempotent.** Pressing it one time has the same effect as pressing it one hundred times. After the first press, all additional presses do absolutely nothing new.

Now think about a calculator. You type 5, then press "+" ten times with "1" each time. What happens? You get 15. Each press of "+" changes the result. Pressing it ten times has a completely different outcome than pressing it once.

**That "+" button is NOT idempotent.** Each press adds a new effect.

---

### The Technical Definition

Here it is in plain English: **an operation is idempotent if calling it multiple times produces the same result as calling it once.**

After the first call, all additional identical calls change nothing. The result is the same regardless of whether you called it once or a thousand times.

This does not mean the operation always gives the same output regardless of input — it just means that REPEATING the same operation does not create new effects.

---

### Examples Table

Here are common operations and whether they are idempotent:

```
╔══════════════════════════════════╦═══════════════╦══════════════════════════════════════════════╗
║ Operation                        ║ Idempotent?   ║ Why                                          ║
╠══════════════════════════════════╬═══════════════╬══════════════════════════════════════════════╣
║ SET x = 5                        ║ YES           ║ Run it 10 times: x is still 5. No            ║
║                                  ║               ║ matter how many times you set x to 5,        ║
║                                  ║               ║ x is 5.                                      ║
╠══════════════════════════════════╬═══════════════╬══════════════════════════════════════════════╣
║ INCREMENT x by 1                 ║ NO            ║ Run it 10 times: x increases 10 times.       ║
║                                  ║               ║ Each call creates a new effect.              ║
╠══════════════════════════════════╬═══════════════╬══════════════════════════════════════════════╣
║ DELETE record #5                 ║ YES           ║ After the first delete, record #5 is gone.   ║
║                                  ║               ║ Deleting it again does nothing — it is       ║
║                                  ║               ║ already gone. No new effect.                 ║
╠══════════════════════════════════╬═══════════════╬══════════════════════════════════════════════╣
║ INSERT a new record              ║ NO            ║ Each insert creates a new row. Run it        ║
║                                  ║               ║ 10 times: 10 new rows.                       ║
╠══════════════════════════════════╬═══════════════╬══════════════════════════════════════════════╣
║ Send an email                    ║ NO            ║ Each call sends another email. Run it        ║
║                                  ║               ║ 10 times: the recipient gets 10 emails.      ║
╠══════════════════════════════════╬═══════════════╬══════════════════════════════════════════════╣
║ Update username to "alice"       ║ YES           ║ After the first update, the username is      ║
║                                  ║               ║ "alice." Updating it to "alice" again does   ║
║                                  ║               ║ nothing new. It is already "alice."          ║
╚══════════════════════════════════╩═══════════════╩══════════════════════════════════════════════╝
```

---

### Why This Matters for Retries

Here is the critical connection to Part A of this chapter: **idempotent operations are safe to retry. Non-idempotent operations are dangerous to retry.**

Think about what a retry means. You called an operation. Something went wrong — maybe the network hiccupped, maybe the server was slow. You are not sure if the operation completed. So you try again.

If the operation is idempotent (like SET x = 5), retrying is totally fine. If the first call completed successfully, calling it again does nothing new. If the first call failed, the retry fixes the problem. Either way: no disaster.

If the operation is NOT idempotent (like "send an email" or "charge a credit card"), retrying is dangerous. If the first call completed but the response was lost, retrying sends ANOTHER email or charges the customer TWICE. The customer gets spammed. The customer gets double-charged. Your customer service inbox explodes.

This is why retry logic alone is not enough. You also need to think about whether your operations are safe to retry. And for operations that are NOT naturally safe — like sending emails or charging payments — you need a technique called **idempotency keys** to make them behave as if they are idempotent.

That is what the next several sections cover.

---

## The Network Uncertainty Problem

Before we get to the solution, we need to really feel the problem. Because the problem is weirder than it first appears.

---

### The Certified Mail Analogy

You send a package via certified mail — the kind where the recipient has to sign for it, and you get a confirmation slip back once they have. You drop the package at the post office.

Now you wait. And wait. No confirmation slip arrives.

From where you are standing, you face a genuinely impossible question: did the package arrive?

Here are the two possible realities:

**Reality A:** The package never arrived. It was lost in transit. You should send another one.

**Reality B:** The package arrived and the recipient signed for it, but the confirmation slip got lost on the way back to you. The package is already there. If you send another one, they get two packages and you paid twice.

You cannot tell the difference between Reality A and Reality B just by looking at your mailbox. Both look identical from your perspective: no confirmation slip. The only way to know would be to somehow peek into the recipient's world.

This is not a weird edge case. This is fundamental to how mail works. And it is fundamental to how networks work.

---

### The Network Uncertainty Problem in Distributed Systems

Here is the same problem in a system design context. Your app makes an API call:

```
Your App: "Charge this credit card $100 for order #789."
```

Here is the full sequence of what happens:

```
╔═══════════════════════════════════════════════════════════════╗
║              WHAT HAPPENS INSIDE THE NETWORK                  ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  Step 1:  Your app sends the request                          ║
║           Client ──────────────────────────────────► Server  ║
║                                                               ║
║  Step 2:  Request arrives at server                           ║
║           Client                                    Server ✓  ║
║                                                               ║
║  Step 3:  Server processes the charge                         ║
║           Client                            Server charges ✓  ║
║                                                               ║
║  Step 4:  Server sends "200 OK, success" response             ║
║           Client                ◄──────────────────  Server  ║
║                                                               ║
║  Step 5:  Response gets LOST somewhere in the network         ║
║           Client     ← (packet dropped here) ✗               ║
║                                                               ║
║  Step 6:  Your app's connection times out                     ║
║           Client sees: TIMEOUT ERROR                          ║
║                                                               ║
╠═══════════════════════════════════════════════════════════════╣
║  What your app knows: "something went wrong"                  ║
║  What actually happened: the charge went through              ║
╚═══════════════════════════════════════════════════════════════╝
```

Your app gets a timeout error. From your app's perspective, this is indistinguishable from the case where the request never reached the server at all.

Your app cannot know whether the charge happened or not. If it retries:

```
Your App (retrying): "Charge this credit card $100 for order #789."
Server: *charges again*
Customer: CHARGED TWICE
```

This is not a bug in your code. This is not bad luck. This is a **fundamental property of networks**: you cannot know whether a response was lost versus whether the operation never completed. The difference lives entirely on the server's side, invisible to you.

This is the problem idempotency keys solve.

---

## How Idempotency Keys Work

### The Tracking Number Analogy

When you ship a package with a carrier like UPS or FedEx, your package gets a unique tracking number — something like `1Z999AA10123456784`. This number is yours. It is tied to this specific shipment.

Now, suppose you worry the package did not arrive. You call FedEx. They look up `1Z999AA10123456784` in their system and say: "Yes, it was delivered on Tuesday at 2:14pm, signed by J. Smith." You know not to send another package.

More importantly: if you somehow accidentally tried to ship the SAME box a second time (same contents, same destination), and you put the same tracking number on it, FedEx's system would see "this tracking number was already processed and delivered" and refuse to process it again. The tracking number acts as a deduplication tool.

Idempotency keys work exactly like this.

---

### The Idempotency Key Protocol

Here is the step-by-step protocol:

**Step 1:** Before making the request, the client generates a unique key for this specific operation. This is like getting a tracking number before you drop off the package.

**Step 2:** The client includes the key in the request header: something like `Idempotency-Key: order-789-attempt-1`.

**Step 3:** When the server receives the request, it first checks its database: "Have I ever seen this key before?"

- If NO: process the operation normally, then store the result linked to this key.
- If YES: do NOT process the operation again. Just look up and return the stored result.

This is the entire mechanism. Simple in concept. The devil is in the details, which we will get to.

---

### The Full Flow Diagram

Let's walk through the credit card charge scenario from before, but now with an idempotency key:

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║           FIRST ATTEMPT (idempotency_key = "charge-456-789-1")               ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  Client → Server:  "Charge $100" + Idempotency-Key: charge-456-789-1         ║
║                                                                               ║
║  Server checks DB: SELECT * WHERE key = 'charge-456-789-1'                   ║
║                    → NOT FOUND                                                ║
║                                                                               ║
║  Server processes: charge credit card → SUCCESS, charge_id = "ch_xyz99"      ║
║                                                                               ║
║  Server stores:    { key: "charge-456-789-1",                                ║
║                      status: 200,                                             ║
║                      result: { charge_id: "ch_xyz99" },                      ║
║                      created_at: "2024-01-01 12:00:00" }                     ║
║                                                                               ║
║  Server → Client:  200 OK, { charge_id: "ch_xyz99" }                         ║
║                                                                               ║
║  ← Response LOST in network ✗                                                ║
║                                                                               ║
║  Client sees: TIMEOUT                                                         ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║           SECOND ATTEMPT (SAME idempotency_key = "charge-456-789-1")         ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  Client → Server:  "Charge $100" + Idempotency-Key: charge-456-789-1         ║
║                                                                               ║
║  Server checks DB: SELECT * WHERE key = 'charge-456-789-1'                   ║
║                    → FOUND! Stored result: { charge_id: "ch_xyz99" }         ║
║                                                                               ║
║  Server does NOT charge the card again                                        ║
║                                                                               ║
║  Server → Client:  200 OK, { charge_id: "ch_xyz99" }   (cached result)       ║
║                    + Idempotency-Replayed: true          (tells client this   ║
║                                                           was a cached reply) ║
║                                                                               ║
║  Client receives: SUCCESS ✓                                                   ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

The key insight: **the customer is charged exactly once**, even though the client made two attempts. The second attempt returned the exact same result as the first — the same `charge_id`, the same success status — without triggering a second charge.

The non-idempotent "charge a credit card" operation now BEHAVES idempotently. Not because we changed the operation itself, but because we wrapped it with a deduplication layer.

---

## Designing Good Idempotency Keys

Not all idempotency keys are equal. A badly designed key defeats the purpose. Here are the properties a good key needs — with analogies for each.

---

### Property 1: Unique Per Intent

The key `order-12345-attempt-1` is tied to one specific business decision: "charge $100 for order #12345, first try." A different order gets a different key: `order-12346-attempt-1`. A different user's order does not accidentally share keys with yours.

This is like FedEx tracking numbers being globally unique. If two packages shared a tracking number, the system would refuse to ship one of them — even if they are completely different packages going to completely different addresses. Uniqueness is what makes the deduplication work.

---

### Property 2: Deterministic (Same Inputs, Same Key, Always)

This is subtle and very important. Here is a trap:

```python
# BAD: generates a random key each time
import uuid
key = str(uuid.uuid4())  # "a7f3b2c1-..." — different every time
```

If the client crashes after generating this key but before getting a response, and then restarts and generates a NEW random key, the server sees a completely new operation. The original charge might have gone through, and now the retry charges again.

The key must be **deterministic**: the same inputs always produce the same key. That way, even if the client crashes and restarts, it can regenerate the exact same key and the server correctly recognizes "I already handled this."

```python
# GOOD: deterministic, based on stable business data
key = f"charge-{user_id}-{order_id}-{attempt_number}"
# If user_id=456, order_id=789, attempt_number=1:
# Always produces: "charge-456-789-1"
```

The analogy: a package tracking number that is derived from your customer account number + the order number. Even if the shipping label printer jams mid-print, you can reprint the same label with the same number, because it was calculated, not randomly assigned.

---

### Property 3: Scoped Appropriately

`payment-789` is a bad key. What if user Alice and user Bob both have payment #789 in your system? They share a key and one of their payments gets deduplicated away as a duplicate of the other.

`user-456-payment-789` is better. It includes who the payment belongs to, preventing collisions between different users' operations.

Think of it like a social security number (SSN). Your SSN is unique within a country (scoped to the US). But a SSN from the US and a national ID number from Canada might accidentally have the same digits — they live in different namespaces.

---

### Property 4: Has a TTL (Expiry Time)

Idempotency key records should not live forever in your database. Here is why: if a client sends request on January 1st and gives up after a timeout, and then the same client tries again on February 1st with the same key, should the February 1st attempt be treated as a duplicate of the January 1st one?

Probably not. A month has passed. The business context has clearly changed. The client has clearly abandoned the original attempt. Treating the new attempt as a duplicate of a month-old attempt would be wrong.

The solution: set a TTL (Time To Live) on idempotency keys — a maximum age after which they expire and new attempts with the same key are treated as fresh operations. Typical TTLs range from **24 hours to 7 days**.

---

### The Idempotency Key Cheat Sheet

```
╔══════════════════════════════════════════════════════════════════════════════╗
║               IDEMPOTENCY KEY DESIGN — DO'S AND DON'TS                      ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  DO:                                                                         ║
║  ✓  Use stable business IDs: order_id, user_id, transaction_id              ║
║  ✓  Include an attempt identifier: "...-attempt-1"                          ║
║  ✓  Generate the key BEFORE making the attempt                              ║
║     (so you can reuse the same key on retry)                                ║
║  ✓  Store the key alongside your request data in your own DB first          ║
║  ✓  Set a TTL: 24 hours to 7 days is typical                               ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  DON'T:                                                                      ║
║  ✗  Use random UUIDs that you haven't persisted first                       ║
║     (if your process crashes, you can't regenerate the same key)            ║
║  ✗  Use timestamps as keys                                                   ║
║     (two requests can arrive within the same millisecond)                   ║
║  ✗  Use data that might change between retries                              ║
║     (e.g., "current cart contents" — the user might have edited their cart) ║
║  ✗  Use keys that are too generic                                            ║
║     (e.g., just "payment-789" without user scoping)                         ║
║  ✗  Store keys forever (they will bloat your database)                      ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

### Key Generation in Practice

Here is a clean, safe key generation pattern:

```python
def generate_idempotency_key(user_id, order_id, attempt_number):
    # This is DETERMINISTIC — same inputs always produce the same key.
    # If you retry, you call this with the same arguments and get the same key.
    return f"charge-{user_id}-{order_id}-{attempt_number}"


# --- FIRST ATTEMPT ---
attempt = 1
key = generate_idempotency_key(user_id=456, order_id=789, attempt_number=attempt)
# key = "charge-456-789-1"

response = payment_api.charge(amount=100, idempotency_key=key)

if response.timed_out:
    # The network failed. Did the charge go through? We don't know.
    # Retry with THE SAME KEY. Server will deduplicate if charge already happened.
    response = payment_api.charge(amount=100, idempotency_key=key)
    # Safe — same key means server checks before charging.


# --- USER EXPLICITLY RETRIES (e.g., user clicks "Try Again" button) ---
# This is a NEW attempt, not a retry of the same attempt.
# The user knows the previous attempt failed or they chose to retry explicitly.
# Use a NEW attempt number — this is genuinely a new operation.
attempt = 2
key = generate_idempotency_key(user_id=456, order_id=789, attempt_number=attempt)
# key = "charge-456-789-2"

response = payment_api.charge(amount=100, idempotency_key=key)
```

The distinction between attempt 1 and attempt 2 here matters: `attempt_number=1` is a *retry of a possibly-completed operation* (use same key). `attempt_number=2` is a *new business decision to try again after confirmed failure* (new key). The first case deduplicates. The second case does not.

---

## Implementing Idempotency in Your API

Now let's look at the server side. How do you actually build an endpoint that respects idempotency keys?

---

### The Basic Server-Side Pattern

```python
def charge_credit_card(request):
    # --- Step 0: Require the idempotency key ---
    # Some endpoints are non-idempotent and MUST have a key.
    # If the client forgot to include one, refuse the request.
    idempotency_key = request.headers.get("Idempotency-Key")

    if not idempotency_key:
        return Response(
            status=400,
            body={"error": "Idempotency-Key header is required for payment endpoints."}
        )

    # --- Step 1: Check if we have seen this key before ---
    # Look up in the database: has this exact key been used?
    cached = db.get(f"idempotency:{idempotency_key}")

    if cached:
        # We already processed this request. Return the same result.
        # Include a special header so the client knows this was a cached reply.
        return Response(
            status=cached["status_code"],
            body=cached["response_body"],
            headers={
                "Idempotency-Key": idempotency_key,
                "Idempotency-Replayed": "true"   # <-- tells client this is cached
            }
        )

    # --- Step 2: Process the actual charge (runs only once per key) ---
    result = payment_processor.charge(
        card_token=request.card_token,
        amount=request.amount
    )

    # --- Step 3: Store the result linked to the idempotency key ---
    # CRITICAL: do this AFTER the operation completes.
    # Set a 7-day TTL so old keys expire and don't bloat the DB forever.
    db.set(
        key=f"idempotency:{idempotency_key}",
        value={
            "status_code": 200,
            "response_body": result.to_json(),
            "created_at": now()
        },
        expires_in=7 * 24 * 60 * 60  # 7 days in seconds
    )

    # --- Step 4: Return the result ---
    return Response(status=200, body=result.to_json())
```

Let's walk through each step in plain English:

**Step 0** (require the key): If a client forgets to send an idempotency key for a non-idempotent operation, the correct response is a 400 error — not "sure, we'll charge anyway." Forcing clients to include the key prevents accidental double-charges from clients who forgot to implement idempotency support.

**Step 1** (check the cache): Every request hits the database first. "Have I seen this key?" If yes: skip all the business logic and just return the stored result. This is the deduplication step.

**Step 2** (process): Only runs if Step 1 found nothing. The actual charge happens here. This code path is only reachable once per unique key.

**Step 3** (store): After the charge succeeds, store the result. We store the entire HTTP response — status code and body — so we can replay it exactly on future requests with the same key.

**Step 4** (return): Send the response back to the client.

The `Idempotency-Replayed: true` header is a nice touch. It tells the client: "Hey, I recognized your key — you already did this. Here is the cached result." The client can log this for debugging or monitoring. It also lets clients distinguish between "the operation completed" and "the operation was replayed" — which can be useful for analytics.

---

### The Race Condition Problem (and How to Fix It)

There is a subtle bug in the implementation above. What if two requests with the SAME idempotency key arrive at the server at exactly the same moment?

Here is the timeline of the bug:

```
╔════════════════════════════════════════════════════════════════════╗
║           THE RACE CONDITION TIMELINE                              ║
╠════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  Thread A:  Check DB for key → NOT FOUND                          ║
║  Thread B:  Check DB for key → NOT FOUND  (same millisecond!)     ║
║                                                                    ║
║  Thread A:  Process charge → $100 charged ✓                       ║
║  Thread B:  Process charge → $100 charged ✓ (DUPLICATE!)          ║
║                                                                    ║
║  Thread A:  Store result in DB                                     ║
║  Thread B:  Store result in DB (overwrites A's result)             ║
║                                                                    ║
║  Customer: CHARGED TWICE despite using idempotency keys            ║
╚════════════════════════════════════════════════════════════════════╝
```

This can happen if the client has two processes retrying simultaneously, or if a load balancer sends the same request to two different servers at the same time.

The fix: instead of "check, then set," use an **atomic "set if not exists"** operation. This is a single database operation that cannot be split by another request sneaking in between.

```python
def charge_credit_card(request):
    idempotency_key = request.headers.get("Idempotency-Key")

    if not idempotency_key:
        return Response(status=400, body={"error": "Idempotency-Key required"})

    # --- Atomic claim: set the key ONLY if it does not already exist ---
    # NX = "only set if Not eXists"
    # This is a single atomic database operation — no race condition possible.
    claimed = db.set(
        key=f"idempotency:{idempotency_key}",
        value="in_progress",    # Placeholder while we process
        nx=True,                # Only set if this key does NOT already exist
        expires_in=120          # 2-minute safety lock: expires if server crashes mid-process
    )

    if not claimed:
        # Another thread/server is already processing this key (or already finished).
        # Wait briefly, then check for the final result.
        result = wait_for_result(idempotency_key, timeout=30)
        if result:
            return Response(status=result["status_code"], body=result["response_body"],
                            headers={"Idempotency-Replayed": "true"})
        else:
            # The other process is taking a long time or crashed.
            return Response(status=503, body={"error": "Request in progress. Try again."})

    # --- We claimed the key. Now process the charge. ---
    result = payment_processor.charge(
        card_token=request.card_token,
        amount=request.amount
    )

    # --- Store the final result (replace "in_progress" with the real result) ---
    db.set(
        key=f"idempotency:{idempotency_key}",
        value={
            "status_code": 200,
            "response_body": result.to_json(),
            "created_at": now()
        },
        expires_in=7 * 24 * 60 * 60
    )

    return Response(status=200, body=result.to_json())
```

The key change: `db.set(..., nx=True)`. This tells the database "set this key to 'in_progress', but ONLY if the key does not already exist." The database executes this as a single atomic operation. Only one thread wins the race. The loser sees `claimed = False` and waits.

The 2-minute TTL on the "in_progress" placeholder is a safety net: if the server crashes mid-processing (after claiming the key but before writing the final result), the placeholder expires after 2 minutes so a future retry can try again rather than being permanently locked out.

This is exactly the distributed lock pattern from Chapter 22 applied here.

---

## What Idempotency Does NOT Guarantee

This is as important as what idempotency DOES guarantee. People often over-rely on idempotency keys as a magic solution that prevents all double-action bugs. It is not. Here are the gaps.

---

### Gap 1: Idempotency Does Not Guarantee Ordering

**The parking ticket vs. parking violation analogy:**

Suppose you get two parking tickets — one on Monday, one on Tuesday. Paying the Monday ticket twice is idempotent (the city's system rejects the duplicate payment). But paying the Monday ticket once and the Tuesday ticket once are TWO different payments for TWO different violations. Idempotency deduplicated the REPLAY. It did nothing about the fact that you have two separate obligations.

Here is the same issue in a system:

```
Timeline:
1. Client sends: "Transfer $100 from Account A → Account B"
   Key: "transfer-001"

2. Network delays this request.

3. Client sends: "Transfer $100 from Account B → Account A" (to reverse it)
   Key: "transfer-002"

4. "transfer-002" arrives at the server FIRST and executes.
   (B sends $100 to A)

5. "transfer-001" arrives SECOND and executes.
   (A sends $100 to B)

Net result: B sent $100 to A, then A sent $100 back to B.
Money moved twice but ended up in the same place. ✓ (in this case)

But the ACCOUNTING TRAIL is wrong.
And the ORDER matters for overdraft checks:
  - If A had $100 and B had $0:
    - Correct order: A→B succeeds (A now $0, B now $100), B→A succeeds (B now $0, A now $100)
    - Wrong order: B→A fails (B has $0, cannot send), A→B succeeds (A now $0, B now $100). A ends up with $0. B ends up with $100.
    - BOTH requests have different keys, so idempotency does not help.
```

Ordering requires causal ordering mechanisms (covered in Chapter 20). Idempotency only prevents the SAME operation from running twice. It cannot control WHICH ORDER different operations run in.

---

### Gap 2: Idempotency Key Does Not Equal a Business Constraint

The scenario: a user tries to buy 1 concert ticket. They get a timeout. They retry with the same idempotency key. The server correctly deduplicates. The user gets exactly 1 ticket. Idempotency works perfectly here.

But: the same user opens a second browser tab and tries to buy another ticket from there. That tab generates a COMPLETELY DIFFERENT idempotency key (it is a new request from a new session). The server does not recognize any duplicate — because there is none. Two separate requests, two separate keys. The user ends up with 2 tickets.

Idempotency only prevents **retries of the same request**. It does not prevent **separate requests that happen to want the same thing**.

If your business rule is "one ticket per user," you need a **database-level unique constraint**, not just idempotency:

```sql
CREATE UNIQUE INDEX one_ticket_per_user_per_event
ON ticket_purchases (user_id, event_id);
```

This would reject the second purchase regardless of whether it came from the same request or a completely different one. That is a business constraint — idempotency is a network reliability tool. They solve different problems.

---

### Gap 3: Only Store Results After the Full Operation Completes

Suppose your operation involves two steps: create an order record, then charge the payment card. The order creation succeeds. The payment fails. Your server returns a 500 error.

The client retries with the same idempotency key.

What does the server return?

If you stored the idempotency result **after the order was created** (before the payment was attempted), the stored result is "order created" — even though the full operation failed. The retry sees the key in the database, assumes success, and returns the stored result. The user gets an order confirmation with no payment charged. You just gave something away for free.

The rule: **only store the idempotency result AFTER the entire operation either fully succeeds or fully fails**. Never store partial states.

```python
# BAD — stores after first step completes (partial state)
order = create_order(user_id, items)
db.set(idempotency_key, {"status": "order_created"})  # WRONG! Stored partial result
payment = charge_card(card_token, total)               # This might fail

# GOOD — stores only after the whole thing completes
order = create_order(user_id, items)
payment = charge_card(card_token, total)  # Both steps must complete first
# Only store after BOTH succeed:
db.set(idempotency_key, {"status": "complete", "order": order, "payment": payment})
```

If the second step fails, the entire operation is treated as failed — no idempotency result stored. The next retry starts fresh (the key is not in the database).

---

### Gap 4: Idempotency Does Not Fix Non-Deterministic Operations

If your server's behavior varies between calls — for example, it picks a random replica to process the job — then two calls with the same idempotency key might attempt to use different replicas, with different state, and produce different outcomes.

Idempotency keys prevent DUPLICATE EFFECTS. They do not ensure IDENTICAL PROCESSING. If Replica A charges a card and stores the result, and Replica B independently processes the same key (due to a race condition before the lock was acquired), you could get different behaviors on each.

This is a subtle edge case, but it matters for operations where "which server handled it" determines the outcome — like processing that depends on locally cached state. The fix is to ensure that idempotency key storage is centralized (all servers share the same idempotency key database) and that the lock is held properly.

---

### A Quick Summary of the Four Gaps

This is a lot to remember. Here is a condensed reference:

```
╔═══════════════════════════════════════╦══════════════════════════════════════════════════════════════╗
║ Gap                                   ║ What to Use Instead                                          ║
╠═══════════════════════════════════════╬══════════════════════════════════════════════════════════════╣
║ Ordering of different operations      ║ Causal ordering / sequence numbers (Chapter 20)              ║
╠═══════════════════════════════════════╬══════════════════════════════════════════════════════════════╣
║ Business constraint (1 ticket/user)   ║ Database unique constraint scoped to (user_id, event_id)    ║
╠═══════════════════════════════════════╬══════════════════════════════════════════════════════════════╣
║ Partial operation state               ║ Only store idempotency result after FULL completion          ║
╠═══════════════════════════════════════╬══════════════════════════════════════════════════════════════╣
║ Non-deterministic server behavior     ║ Centralized idempotency key storage + proper locking         ║
╚═══════════════════════════════════════╩══════════════════════════════════════════════════════════════╝
```

Idempotency is a precise tool. It prevents one specific problem: a duplicate network request causing a duplicate real-world effect. For everything else, you need the specific tool designed for that specific problem.

---

## Real-World Idempotency: How Stripe Does It

It is worth looking at how a real company implements this, because the patterns we have described are exactly what major payment companies like Stripe use in production.

Stripe's API requires an `Idempotency-Key` header for all POST requests. Here is what their documentation says (paraphrased):

- The key can be any string up to 255 characters. Stripe recommends version 4 UUIDs.
- Keys expire after 24 hours. After 24 hours, a new request with the same key is treated as a fresh request.
- If a request is still in progress (the "in_progress" state) and a second request arrives with the same key, Stripe returns a 409 Conflict error — "a request with this key is already being processed."
- If a completed request is replayed, Stripe returns the original response with a `Idempotency-Replayed: true` header.
- If you send a request with an existing key but DIFFERENT request parameters (different amount, different card), Stripe returns a 422 error — "idempotency key already used for a different request."

That last point is clever and worth noting separately.

---

### Validating Request Parameters Against Stored Keys

When a retry arrives with an existing idempotency key, you should not just blindly return the cached result. You should verify that the new request is asking for the SAME thing as the original.

If the original request said "charge $100" and the retry says "charge $200" with the same key, something has gone wrong on the client side. Either there is a bug, or the client is trying to abuse the idempotency system to get a $100 charge recorded for what is actually a $200 charge.

The correct behavior: reject the request with an error like "Idempotency key already used for a different payload."

```python
def charge_credit_card(request):
    idempotency_key = request.headers.get("Idempotency-Key")

    cached = db.get(f"idempotency:{idempotency_key}")
    if cached:
        # Before returning cached result: verify the request matches
        if cached["request_fingerprint"] != compute_fingerprint(request):
            return Response(
                status=422,
                body={"error": "This idempotency key was used for a different request. "
                               "Use a new key for a different operation."}
            )
        # Fingerprints match — this is a genuine retry
        return Response(
            status=cached["status_code"],
            body=cached["response_body"],
            headers={"Idempotency-Replayed": "true"}
        )

    # ... rest of the processing ...

def compute_fingerprint(request):
    # Hash the key parameters to detect if the request payload changed
    import hashlib, json
    payload = {
        "amount": request.amount,
        "card_token": request.card_token,
        "currency": request.currency
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
```

A fingerprint is like a seal on an envelope. When you store the idempotency result, you also seal the envelope (store a hash of the request). On retry, you verify the seal has not been broken (the hash still matches). If someone tried to swap the contents, the seal reveals it.

---

## Database-Level Idempotency Patterns

Beyond API-level idempotency keys, there are database-native patterns that enforce idempotency directly at the data layer. These are often simpler and more robust.

---

### Pattern 1: Unique Constraint (Simplest and Most Robust)

If your operation has a natural unique identifier, just add a UNIQUE constraint to the database. Duplicate inserts fail silently.

```sql
-- When you create the table, declare idempotency_key as UNIQUE:
CREATE TABLE orders (
    order_id     UUID         PRIMARY KEY,
    user_id      BIGINT       NOT NULL,
    amount       DECIMAL      NOT NULL,
    idempotency_key VARCHAR(255) UNIQUE,   -- Only one row per key. Ever.
    created_at   TIMESTAMP    DEFAULT NOW()
);

-- When inserting, use ON CONFLICT DO NOTHING:
INSERT INTO orders (order_id, user_id, amount, idempotency_key)
VALUES ('uuid-123', 456, 100.00, 'order-456-789-1')
ON CONFLICT (idempotency_key) DO NOTHING;
-- If this key was used before: silently skip. No error. No duplicate row.
-- If this key is new: insert the row normally.
```

This is the most bulletproof pattern. The database engine itself enforces uniqueness at the storage layer. No application-level race conditions possible — the database handles the concurrency internally.

**When to use it:** operations with a clear natural unique identifier. Order creation (idempotency key = order ID), payment processing (idempotency key = payment reference number), event logging (idempotency key = event UUID). If there is a natural unique key, put it in the database constraint.

---

### Pattern 2: Conditional Update (Check Before Acting)

When you want to update data only if it has not already been updated by this specific operation:

```sql
-- Only deduct the balance if this exact transaction has NOT already been applied.
-- "last_transaction_id" tracks the most recent transaction that touched this account.

UPDATE accounts
SET
    balance = balance - 100,
    last_transaction_id = 'txn-abc123'   -- Record that this transaction happened
WHERE
    user_id = 456
    AND last_transaction_id != 'txn-abc123'   -- Skip if already applied!
    AND balance >= 100;                        -- Business rule: sufficient funds

-- Check how many rows were updated:
-- 0 rows updated = either already applied (idempotency worked) or insufficient funds
-- 1 row updated = success
```

The `last_transaction_id != 'txn-abc123'` condition is the idempotency check. If the transaction was already applied, the WHERE clause fails and no update happens. The operation becomes idempotent.

**When to use it:** updates where you need to check a precondition AND track which transaction caused the update. Common in financial systems, inventory management, and any system that needs an audit trail.

---

### Pattern 3: Version Numbers (Optimistic Concurrency)

This pattern is for situations where multiple writers might be updating the same record simultaneously, and you want to ensure each writer works with the data they originally read — not data that someone else changed while they were working.

```sql
-- Step 1: Read the current state, including a version number
SELECT balance, version FROM accounts WHERE user_id = 456;
-- Returns: balance = 500, version = 7

-- (Your application does some work based on this data)

-- Step 2: Update ONLY if the version still matches what you read
-- If someone else updated the record between your read and your write,
-- the version will have changed, and 0 rows will be updated.
UPDATE accounts
SET
    balance = 400,       -- $500 - $100 = $400
    version = 8          -- Increment the version
WHERE
    user_id = 456
    AND version = 7;     -- Only update if nobody else changed it since we read it

-- Check rows affected:
-- 0 rows = someone else updated between our read and write → retry with fresh data
-- 1 row = success
```

The version number acts like a seal on an envelope. When you open the envelope (read the data), you know what version it was. When you try to close it again (update), you check the seal. If someone else opened it and resealed it while you were reading (version changed), you know — and you start over with the new version.

**When to use it:** scenarios where multiple users or processes might update the same record simultaneously. Profile edits, collaborative document editing, inventory updates from multiple warehouses. This is also called "optimistic locking" — you optimistically assume no conflict, then check at write time.

---

### Choosing the Right Database Pattern

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║           WHICH DATABASE IDEMPOTENCY PATTERN TO USE?                         ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  UNIQUE CONSTRAINT                                                            ║
║  Use when: operation has a clear natural unique key (order ID, payment ref)  ║
║  Best for: inserts (creating new records)                                    ║
║  Complexity: LOW — just add UNIQUE to the column                             ║
║                                                                               ║
║  CONDITIONAL UPDATE                                                           ║
║  Use when: you need to check preconditions AND track last operation           ║
║  Best for: financial ledger updates, state machine transitions                ║
║  Complexity: MEDIUM — requires tracking last_transaction_id                  ║
║                                                                               ║
║  VERSION NUMBERS (Optimistic Concurrency)                                    ║
║  Use when: multiple concurrent writers are likely                             ║
║  Best for: user profile updates, collaborative editing, inventory             ║
║  Complexity: MEDIUM — requires version column and retry logic                ║
║                                                                               ╟
║  RULE OF THUMB:                                                               ║
║  Start with Unique Constraint. If that doesn't fit, try Conditional Update.  ║
║  Use Version Numbers when you genuinely expect concurrent conflicting writes. ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

---

# Part 3: Backpressure — Controlling the Flow

---

## What Is Backpressure?

Let's start with a garden hose.

---

### The Garden Hose Analogy

A garden hose delivers water at a comfortable flow rate — say, enough to fill a bucket in 30 seconds. Now put your thumb over the end of the hose. Water pressure builds up behind your thumb. That built-up pressure is the hose "pushing back" against the source.

If the hose is connected to a smart pump with a pressure sensor, the pump detects the high pressure and automatically slows down its output. The pressure signal travels backward through the hose to the source. The source adapts.

This is backpressure: **a signal that travels upstream (toward the sender) to tell the sender to slow down, because the receiver is full**.

In distributed systems, backpressure is how a slow or overwhelmed downstream service tells upstream callers "you are sending too fast — slow down." Instead of accepting everything and collapsing under the load, the downstream service pushes back.

---

### Without Backpressure: The Fire Hose Problem

Imagine you are very thirsty. A firefighter arrives and offers you water. But they connect a fire hose. The fire hose delivers 50 gallons per second. You can drink about 0.001 gallons per second.

The fire hose does not care about your drinking rate. It blasts at 50 gallons per second regardless. The result: you are soaked, overwhelmed, and possibly in the hospital. The water does not magically slow down because you cannot handle it.

This is what happens to a server with no backpressure mechanism. The requests arrive at whatever rate the clients send them. The server cannot handle more than, say, 100 requests per second. If 1,000 requests per second arrive:

```
WITHOUT BACKPRESSURE:

Clients → → → → → → → → → → → → → → → → → → → → Server
(1,000 req/sec)                                   (capacity: 100 req/sec)
                                                  Queue fills up
                                                  Memory runs out
                                                  Response times spike to 30 seconds
                                                  Server crashes
                                                  TOTAL OUTAGE
```

The clients do not stop sending just because the server is struggling. They keep sending. The server keeps accepting (until it runs out of memory for the queue). Then it falls over.

---

### With Backpressure: The Valve Solution

A fire hose with a valve. You signal "full" and the valve closes. Flow rate matches your capacity.

```
WITH BACKPRESSURE:

Clients ← ← ← ← ← "SLOW DOWN" signal ← ← ← ← Server
(100 req/sec, matching server capacity)          (handling 100 req/sec)
                                                  Sustainable. Stable. Alive.
```

The key insight: **a server that can handle 100 requests per second will fail if given 1,000 requests per second, no matter how good your code is**. There is no such thing as infinitely fast software. At some point, hardware limits kick in. Backpressure prevents the gap between arrival rate and processing rate from widening until the system breaks.

It is not about making the server faster. It is about making the system honest: "here is what I can handle — please do not send more."

---

## Strategy 1: Blocking Backpressure (The Simplest Approach)

### The Single-Lane Bridge Analogy

Picture a single-lane bridge over a river. One car can cross at a time. When a car is on the bridge, a gate at the toll booth stays closed. New cars arriving queue up at the toll booth. They wait. When the bridge clears, the gate opens and the next car proceeds. The gate is the backpressure mechanism: it refuses to let cars enter faster than the bridge can handle them.

Blocking backpressure works the same way: when the server's processing capacity is fully occupied, new incoming requests WAIT (block) in a queue until capacity frees up. The server does not accept and crash — it just makes callers wait.

---

### How Thread Pools Create Blocking Backpressure

Most web servers use a thread pool — a fixed number of worker threads that handle requests. If there are 50 threads and 50 requests are being processed simultaneously, a 51st request must wait for one of the threads to finish before it can begin processing.

```python
import concurrent.futures

# This server has 50 threads. It can process 50 requests simultaneously.
# A 51st request blocks here until one of the 50 threads finishes.
executor = concurrent.futures.ThreadPoolExecutor(max_workers=50)

def handle_request(request):
    # If all 50 threads are busy, this line BLOCKS the caller.
    # The caller waits here, unable to proceed, until a thread frees up.
    future = executor.submit(process_request, request)

    # Wait for result, but give up after 30 seconds.
    result = future.result(timeout=30)
    return result
```

The thread pool itself IS the backpressure mechanism. The 51st caller waits. The 100th caller waits longer. If the wait queue fills up too (because wait times are growing faster than threads are finishing), the server returns an error to new callers rather than letting them wait forever.

---

### When Blocking Works (and When It Fails)

**Blocking works well when:**
- The workload is synchronous and latency-tolerant. A batch job that processes files can wait a few seconds.
- Wait times are short relative to the total acceptable latency. If the server processes requests in 10ms and you wait 20ms in queue, total is 30ms — maybe acceptable.

**Blocking fails when:**
- Users are waiting in real time. If 50 threads are busy and a user waits 30 seconds for a thread... the user has already given up and left. The thread finally processes an abandoned request.
- The arrival rate consistently exceeds capacity. If you can process 500 requests/second (50 threads × 10 per thread per second) but 600 requests/second arrive, the queue grows by 100 requests every second. After 60 seconds, 6,000 requests are waiting. After 10 minutes, it is unworkable. Blocking buys time but does not solve the underlying mismatch.

---

### Queuing Theory Note (No Math Required)

Here is an intuition about wait times:

- If your server is at 50% capacity (half the threads are free), wait times are nearly zero.
- If your server is at 80% capacity, wait times start to grow noticeably.
- If your server is at 95% capacity, wait times are long and variable.
- If your server is at 100% capacity (threads always full), wait times grow without bound.

This is why you should never run a server at 100% CPU or thread utilization. Even at 90%, you are one traffic spike away from runaway wait times. The backpressure mechanisms we discuss next are designed to kick in well before you hit the wall.

---

## Strategy 2: Token Bucket — The Industry Standard for Rate Limiting

### The Bucket of Tokens Analogy

You have a bucket that holds 100 tokens. Every second, 100 new tokens are added to the bucket — but the bucket has a maximum capacity of 100, so if it is already full, new tokens are discarded.

Every time a request arrives, it must take 1 token from the bucket. If there is at least 1 token available: take it, process the request. If the bucket is empty: the request must wait until a token arrives in the next refill, or be rejected immediately with a "slow down" signal.

Why this is clever:

1. **You can burst.** If the bucket is full (100 tokens) and 100 requests arrive at once, all 100 are served instantly. Short traffic spikes are handled gracefully.

2. **You cannot sustain above the refill rate.** No matter how many requests try to arrive, the sustained throughput is capped at 100 per second (the refill rate). After spending the burst, you must wait for refills.

3. **Smooth recovery.** After a burst empties the bucket, the bucket gradually refills over the next second. The system recovers on its own.

```
╔════════════════════════════════════════════════════════════════╗
║               TOKEN BUCKET IN ACTION                           ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  t=0s:  Bucket full:  [●●●●●●●●●●] 10 tokens (capacity = 10) ║
║                                                                ║
║  t=0s:  10 requests arrive simultaneously                      ║
║         Each takes 1 token: [          ] 0 tokens left         ║
║         All 10 requests: ALLOWED immediately                   ║
║                                                                ║
║  t=0.1s: 5 more requests arrive. Bucket empty.                 ║
║          These requests: DENIED (429 Too Many Requests)        ║
║          Retry-After header: "0.9 seconds"                     ║
║                                                                ║
║  t=1s:  Refill! Bucket: [●●●●●●●●●●] 10 tokens again          ║
║                                                                ║
║  t=1s:  Next batch of 10 requests: ALLOWED                     ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
```

---

### The Implementation

```python
import time

class TokenBucket:
    def __init__(self, capacity, refill_rate):
        """
        capacity:    Maximum tokens the bucket can hold (burst limit).
                     Example: 1000 — can serve up to 1000 requests at once.
        refill_rate: Tokens added per second (sustained rate limit).
                     Example: 100 — can sustain 100 requests/second long-term.
        """
        self.capacity = capacity            # Max tokens (burst size)
        self.tokens = capacity              # Start full
        self.refill_rate = refill_rate      # Tokens added per second
        self.last_refill_time = time.time() # When did we last add tokens?

    def consume(self, tokens_needed=1):
        """
        Try to consume tokens_needed tokens.
        Returns True if allowed, False if rate limited.
        """
        # --- Step 1: Add tokens based on elapsed time ---
        # How much time has passed since the last refill?
        now = time.time()
        elapsed = now - self.last_refill_time

        # Add tokens proportional to elapsed time.
        # (If 0.5 seconds passed and rate is 100/s, add 50 tokens)
        new_tokens = elapsed * self.refill_rate

        # Update the bucket — but never exceed max capacity.
        self.tokens = min(
            self.capacity,           # Don't overflow the bucket
            self.tokens + new_tokens # Add what time has earned us
        )
        self.last_refill_time = now  # Reset the timer

        # --- Step 2: Check if we have enough tokens ---
        if self.tokens >= tokens_needed:
            self.tokens -= tokens_needed  # Spend the tokens
            return True                   # ALLOWED
        else:
            return False                  # RATE LIMITED — bucket empty
```

Each piece explained simply:

- `capacity` is the burst limit — how many requests can hit all at once before the bucket empties. Like a reservoir that absorbs sudden surges.
- `refill_rate` is the sustained throughput. Tokens trickle in at this rate. Sustained request rate above this means the bucket eventually empties and clients start getting rejected.
- `elapsed * self.refill_rate` calculates how many tokens have "earned themselves" since the last check. If 2 seconds have passed and the rate is 100/second, 200 tokens have accumulated (up to the max).

**An important note about distribution:** this implementation is local to one server. In a system with 10 servers, each server has its own separate bucket, allowing 10× the intended rate limit. For a shared rate limit across a whole cluster, you store the token count in Redis — a centralized shared database — so all servers draw from the same bucket.

---

### Using Token Bucket for Backpressure

```python
# Create one bucket: capacity = 1000 tokens, refill at 100/second
# Effect: can burst to 1000 req/sec, sustained max is 100 req/sec
bucket = TokenBucket(capacity=1000, refill_rate=100)

def handle_request(request):
    if not bucket.consume():
        # Bucket is empty — tell the client to wait and try again
        return Response(
            status=429,              # HTTP 429 = "Too Many Requests"
            body={"error": "Rate limit exceeded. Please slow down."},
            headers={
                "Retry-After": "1",  # Tell client: try again in 1 second
                "X-RateLimit-Limit": "100",
                "X-RateLimit-Reset": str(int(time.time()) + 1)
            }
        )

    # Token successfully consumed — proceed with the request
    return process(request)
```

The `Retry-After` header is a key kindness: you are not just rejecting the request, you are telling the client when to try again. A well-behaved client reads this header and waits the specified number of seconds before retrying. This is the backpressure signal traveling from server back to client.

---

## Strategy 3: Adaptive Concurrency Limits (AIMD)

### The Car Cruise Control Analogy

A car's cruise control is set to 60 mph. But the car is not stupid — it does not just dump the same amount of fuel into the engine regardless of conditions. When you hit a hill (more resistance), the engine throttles up to maintain 60 mph. When you crest the hill and start going downhill (less resistance), it throttles back.

The cruise control ADAPTS to what the road is doing, trying to maintain a target despite changing conditions.

AIMD (Additive Increase / Multiplicative Decrease) is a technique that adapts the concurrency limit — how many requests you allow to be in-flight simultaneously — based on observed system health.

- When things are going well (low latency, low error rate): SLOWLY increase the limit. +1 per time period.
- When things are going badly (latency spikes, errors increasing): QUICKLY decrease the limit. ×0.5 (cut in half).

---

### Why the Asymmetry?

The "increase slowly, decrease quickly" asymmetry is intentional, and the reason is risk:

**Slow increase when recovering:** A recovering server might seem healthy before it fully is. If you immediately ramp back up to the previous load as soon as latency drops, you might re-overwhelm the still-fragile service. Go slow. Let the server breathe. If it stays healthy, gradually add more load.

**Fast decrease when struggling:** When a server is overwhelmed, every additional request makes things worse. Each extra request adds to the queue, adds to memory pressure, makes response times longer for everyone else. Cut load immediately and dramatically. Do not nibble at the problem — halve your load right now.

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║              AIMD CONCURRENCY LIMIT OVER TIME (Sawtooth Pattern)             ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  Concurrency                                                                  ║
║  Limit                                                                        ║
║    50 ┤                              ████                                     ║
║    45 ┤                         █████  █                                      ║
║    40 ┤                    █████       █                                      ║
║    35 ┤               █████            █                                      ║
║    30 ┤          █████                 █                                      ║
║    25 ┤     █████                      █████                                  ║
║    20 ┤█████                                █                                 ║
║    15 ┤  "things going well,                █                                 ║
║    10 ┤   slowly +1 each minute"            ████                              ║
║     5 ┤                                         "latency spiked!              ║
║     0 ┤─────────────────────────────────────     cut by half"                ║
║       └────────────────────────────────────────────────────────── Time        ║
║                                                                               ║
║  Pattern: Slow climb (each step = +1)  →  Sudden drop (×0.5)                ║
║           Then slow climb again from the lower baseline.                     ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

This "sawtooth" pattern is natural and expected. It looks chaotic on a chart but it represents a self-regulating system that continuously probes for the maximum safe load without exceeding it.

---

### AIMD in Practice

```python
class AdaptiveConcurrencyLimiter:
    def __init__(self, initial_limit=20):
        self.limit = initial_limit           # Start conservative
        self.in_flight = 0                   # Currently processing
        self.success_count = 0               # Successes since last adjustment
        self.last_adjustment = time.time()

    def check_and_adjust(self, response_time_ms, success):
        now = time.time()
        if now - self.last_adjustment < 60:  # Adjust every 60 seconds
            return

        self.last_adjustment = now

        if success and response_time_ms < 200:  # Things are healthy
            self.limit += 1                     # Additive Increase: cautious
            print(f"Healthy: increased limit to {self.limit}")

        elif not success or response_time_ms > 500:  # Things are struggling
            self.limit = max(1, int(self.limit * 0.5))  # Multiplicative Decrease: aggressive
            print(f"Struggling: decreased limit to {self.limit}")

    def try_acquire(self):
        if self.in_flight < self.limit:
            self.in_flight += 1
            return True       # Allowed: one more in-flight slot available
        return False          # Rejected: at concurrency limit

    def release(self):
        self.in_flight -= 1  # Request finished, free the slot
```

Real-world implementations of this idea: Netflix's "Concurrency Limiter" library, AWS's client-side throttling, and Envoy proxy's adaptive concurrency filter. The specific formulas vary, but the principle is the same: watch the health signals, loosen the limit cautiously when healthy, tighten it aggressively when struggling.

---

## Choosing a Backpressure Strategy: Decision Guide

We now have three main strategies. In a system design interview — or in a real design meeting — someone will eventually ask: "which one do we use?" Here is how to think through that choice.

---

### The Question to Ask First: Who Controls the Rate?

There are two fundamentally different situations:

**Situation A: You control both sides.** Your own service is calling your own downstream service. You wrote both sides. You can add whatever mechanism you want.

**Situation B: You are a public API.** External developers call your service. They wrote their own client code. You cannot change their clients. You can only control what YOU respond with.

For Situation A (internal, you own both sides): **adaptive concurrency limits (AIMD)** are often the best choice. They self-regulate based on actual health signals. You do not need to guess the right rate limit number — the system figures it out.

For Situation B (external API, clients you do not control): **token bucket rate limiting** is the standard choice. It gives you a fixed, predictable limit you can document and publish ("our API allows 100 requests/second per API key"). External clients can code against a known limit.

---

### The Decision Flowchart

```
╔═══════════════════════════════════════════════════════════════════╗
║         BACKPRESSURE STRATEGY DECISION GUIDE                      ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║  Is this a public API (external clients)?                         ║
║    ├── YES → Use TOKEN BUCKET                                     ║
║    │         - Publish your rate limits in documentation          ║
║    │         - Return 429 with Retry-After header                 ║
║    │         - Consider per-client buckets (by API key)           ║
║    │                                                              ║
║    └── NO (internal service) → Continue below                    ║
║                                                                   ║
║  Does load vary significantly and unpredictably?                  ║
║    ├── YES → Use AIMD (Adaptive Concurrency)                      ║
║    │         - Self-regulates without a fixed number to tune      ║
║    │         - Great for services with variable downstream speed  ║
║    │                                                              ║
║    └── NO (load is steady or predictable) → Continue below       ║
║                                                                   ║
║  Is this a batch/background job (not user-facing)?                ║
║    ├── YES → Use BLOCKING (thread pool)                           ║
║    │         - Simple. No extra code needed.                      ║
║    │         - Fine if users are not waiting.                     ║
║    │                                                              ║
║    └── NO (user-facing, latency matters) → Use TOKEN BUCKET       ║
║          - Reject immediately, do not queue                       ║
║          - Tell client when to retry                              ║
╚═══════════════════════════════════════════════════════════════════╝
```

---

### Per-Client Rate Limiting vs. Global Rate Limiting

There is one more dimension token buckets unlock: you can have a bucket per client instead of one global bucket.

**Global bucket:**
```python
# One bucket for ALL clients combined
global_bucket = TokenBucket(capacity=10000, refill_rate=1000)

def handle_request(request):
    if not global_bucket.consume():
        return Response(429, "Global rate limit reached")
    return process(request)
```

**Per-client bucket:**
```python
# One bucket PER API KEY — each client gets their own allowance
client_buckets = {}  # In practice, stored in Redis so all servers share it

def handle_request(request):
    api_key = request.headers.get("X-API-Key")
    
    # Create a bucket for this client if we've never seen them before
    if api_key not in client_buckets:
        client_buckets[api_key] = TokenBucket(capacity=1000, refill_rate=100)
    
    if not client_buckets[api_key].consume():
        return Response(
            429,
            f"Rate limit exceeded for API key {api_key}. "
            f"Your limit: 100 req/sec. Retry after 1 second."
        )
    return process(request)
```

**Why per-client matters:** with a global bucket, one misbehaving client (sending too many requests, possibly a bug in their code) can exhaust the entire bucket and block all other clients. Per-client buckets isolate bad actors. A buggy client that sends 10,000 requests/second only drains their OWN bucket. Every other client's bucket is unaffected.

This is the model most public APIs use: Stripe, GitHub, Twitter, Twilio all rate-limit per API key, not globally.

---

## Push vs. Pull Backpressure

So far we have discussed the server pushing back against callers. But there is another dimension to backpressure: who controls the flow of data — the sender (pushing data) or the receiver (pulling data when ready)?

---

### The Broadcast vs. On-Demand Analogy

**PUSH: the radio station model.**

A radio station broadcasts on a frequency 24 hours a day. Every listener gets every broadcast, at the station's pace, whether or not they are ready for it. The station does not know if any particular listener is tuned in, paused, confused, or has fallen asleep. It just broadcasts.

If you are a listener who is a slow note-taker, you will miss things. The broadcast does not wait for you. There is no "slow down, I'm not keeping up" signal you can send to the station.

**PULL: the Netflix model.**

Netflix does not beam your entire movie to you the moment you click play. It sends a chunk. Your device decodes and plays that chunk. When your device is ready for the next chunk, it requests it. Netflix sends the next chunk. Your device is always in control of the data flow — it only receives what it has asked for.

If your internet slows down, Netflix detects that your device is requesting chunks more slowly (because it is taking longer to decode them or the network is slow). Netflix adapts — sends smaller chunks, lower resolution. Your device's request rate is the backpressure signal.

---

### Push Backpressure — How It Works

In the push model, the producer sends data as fast as it can. The consumer must signal "STOP" when it is full, and "READY" when it has caught up.

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                    PUSH BACKPRESSURE FLOW                                    ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  Producer ──────────────────────────────────────────────────► Consumer       ║
║           "here's data, here's data, here's data, here's data"               ║
║                                                                               ║
║  Consumer buffer fills up                                                     ║
║                                                                               ║
║  Consumer ◄──────────────────────────────────────────────────── Producer     ║
║           "STOP! I'm full! Please stop sending!"                             ║
║                                                                               ║
║  Producer pauses. Consumer drains its buffer.                                ║
║                                                                               ║
║  Consumer ──────────────────────────────────────────────────► Producer       ║
║           "OK I've caught up. You can send again."                           ║
║                                                                               ║
║  Producer resumes sending.                                                   ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

Pros: low latency when the consumer is fast — data arrives immediately without waiting for a request.

Cons: requires a feedback channel (the "STOP" signal must travel back to the producer). If the "STOP" signal is slow or lost, the buffer overflows before the producer pauses.

---

### Pull Backpressure — How It Works

In the pull model, the consumer requests data only when it is ready for more. The producer only sends what has been requested.

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                    PULL BACKPRESSURE FLOW                                    ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  Consumer ──────────────────────────────────────────────────► Producer       ║
║           "I'm ready. Please send me 10 items."                              ║
║                                                                               ║
║  Producer ──────────────────────────────────────────────────► Consumer       ║
║           *sends 10 items*                                                   ║
║                                                                               ║
║  Consumer processes all 10 items.                                             ║
║                                                                               ║
║  Consumer ──────────────────────────────────────────────────► Producer       ║
║           "Done! Send me 10 more."                                           ║
║                                                                               ║
║  Producer sends 10 more. And so on.                                          ║
║                                                                               ║
║  If consumer is slow: it simply requests less often. Producer waits.         ║
║  No overflow possible. Consumer always in control.                           ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

Pros: consumer is always in control. Overflow is essentially impossible — the consumer only receives what it explicitly asked for. Natural flow control.

Cons: higher latency — there is always a round-trip request before new data arrives. Slightly wasteful when the consumer is fast and could have handled more without asking.

---

### Comparison Table

```
╔══════════════════════════════╦════════════════════════════════╦═════════════════════════════════╗
║ Factor                       ║ PUSH                           ║ PULL                            ║
╠══════════════════════════════╬════════════════════════════════╬═════════════════════════════════╣
║ Latency                      ║ Lower — data flows immediately ║ Higher — must request each batch║
║                              ║ without waiting for a request  ║ before receiving it             ║
╠══════════════════════════════╬════════════════════════════════╬═════════════════════════════════╣
║ Overflow risk                ║ Moderate — depends on buffer   ║ Very low — consumer controls    ║
║                              ║ size and signal speed          ║ exactly how much it receives    ║
╠══════════════════════════════╬════════════════════════════════╬═════════════════════════════════╣
║ Consumer control             ║ Limited — must signal "stop"   ║ Full — never receives more than ║
║                              ║ after the fact                 ║ it requested                    ║
╠══════════════════════════════╬════════════════════════════════╬═════════════════════════════════╣
║ Feedback channel needed?     ║ YES — "stop" and "ready"       ║ NO — requests are the signal   ║
║                              ║ signals must travel upstream   ║                                 ║
╠══════════════════════════════╬════════════════════════════════╬═════════════════════════════════╣
║ Best for                     ║ Streaming, real-time feeds,    ║ Batch processing, queue workers,║
║                              ║ low-latency data pipelines     ║ file processing, safe loading   ║
╠══════════════════════════════╬════════════════════════════════╬═════════════════════════════════╣
║ Real-world examples          ║ gRPC streaming, WebSockets,    ║ SQS/RabbitMQ queue workers,     ║
║                              ║ Kafka producers, TCP streams   ║ REST pagination, S3 downloads   ║
╚══════════════════════════════╩════════════════════════════════╩═════════════════════════════════╝
```

---

### Reactive Streams: The Industry Standard Push Model

The software industry settled on a standard protocol for push-based backpressure called **Reactive Streams** (also the basis of the ReactiveX / RxJava / RxJS libraries). The central idea is elegant:

The consumer calls `request(N)` — asking the producer to send at most N items. The producer sends at most N items. When the consumer is ready for more, it calls `request(N)` again.

```
Consumer calls:  request(5)        request(5)         request(5)
Producer sends:  ← item item item  ← item item item   ← item item item
                   item item           item item           item item

Consumer processes each batch before requesting more.
```

This is like a waiter bringing food in rounds: "Bring me 5 dishes." You eat them. "Bring me 5 more." Instead of the kitchen piling all 100 dishes on your table the moment you sit down.

Reactive Streams gives you the low latency of push (data arrives continuously without waiting for full round trips) while giving the consumer control via N-at-a-time requests (no overflow).

The key libraries that implement this standard: **RxJava** (Android/Java), **RxJS** (JavaScript/browser), **Project Reactor** (Spring/Java backend), **Akka Streams** (Scala). If you see any of these in a codebase, you are looking at reactive/push-based backpressure.

---

## Backpressure Across Service Boundaries

Everything we have discussed so far has been about backpressure between a client and a single server. But real systems are chains of services calling each other. Backpressure needs to propagate through the entire chain — or the chain breaks.

---

### The Water Pipe Network Analogy

Imagine the plumbing system in a tall building. Water pressure is managed at every junction — the main building supply line, the pipes that branch to each floor, the pipes on each floor, the faucet. If any section is too narrow to carry the required flow, it creates a bottleneck. The pressure differential at that bottleneck is the backpressure signal — it travels upstream to the building's main valve.

In a microservices system, every service is a section of pipe. If Service C (the deepest in the chain) is overloaded:

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║              BACKPRESSURE PROPAGATION THROUGH A SERVICE CHAIN                ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  Client  →  Service A  →  Service B  →  Service C                           ║
║                                                                               ║
║  Normal operation:                                                            ║
║  Client sends 100/s → A processes and calls B → B calls C at 100/s          ║
║  C processes at 100/s. Everyone happy.                                       ║
║                                                                               ║
║  Service C gets overwhelmed (database backup running, etc.):                 ║
║                                                                               ║
║  C overwhelmed → C returns errors/slow responses to B                        ║
║  B's threads fill up waiting for C → B starts returning errors to A          ║
║  A's threads fill up waiting for B → A starts returning errors to Client     ║
║  Client sees errors/timeouts                                                  ║
║                                                                               ║
║  WITH proper backpressure (each service propagates the signal):              ║
║  C signals "slow down" → B reduces its call rate to C                        ║
║  B signals "slow down" → A reduces its call rate to B                        ║
║  A signals "slow down" → Client reduces its request rate                    ║
║                                                                               ║
║  WITHOUT backpressure propagation:                                           ║
║  C overwhelmed → fills up → crashes                                          ║
║  B's pending requests to C all fail → B fills up → crashes                  ║
║  A's pending requests to B all fail → A fills up → crashes                  ║
║  Client sees: total outage across all three services                         ║
║  This is called a CASCADING FAILURE.                                         ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

The lesson: backpressure is not a one-service problem. Every service in the chain must be able to detect when its downstream dependencies are struggling and propagate that signal upstream. A service that silently absorbs downstream pressure and keeps accepting new requests from upstream is a ticking bomb.

---

### Timeout Cascades (Deadline Propagation)

One practical technique for propagating backpressure through a chain: **deadline propagation**. Instead of each service using its own fixed timeout, the remaining time budget is passed from service to service.

Here is the idea. A client sends a request to Service A and is willing to wait at most 500 milliseconds for a response.

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                        DEADLINE PROPAGATION                                  ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  Client → Service A: "I'll wait 500ms total"                                 ║
║                                                                               ║
║  Service A receives request. Has 500ms budget.                                ║
║  A reserves ~100ms for its own processing.                                   ║
║  A calls Service B: "I'll wait 400ms" (500 - 100 = 400)                      ║
║                                                                               ║
║  Service B receives request. Has 400ms budget.                               ║
║  B reserves ~100ms for its own processing.                                   ║
║  B calls Service C: "I'll wait 300ms" (400 - 100 = 300)                      ║
║                                                                               ║
║  Service C receives request. Has 300ms budget.                               ║
║                                                                               ║
║  SCENARIO: C takes 350ms to respond (over budget!)                           ║
║                                                                               ║
║  B's timeout fires at 300ms. B returns an error to A immediately.            ║
║  A gets the error. Returns an error to Client immediately.                   ║
║                                                                               ║
║  Total client wait: ~300ms (not the full 500ms)                              ║
║  The cascade "fails fast" rather than hanging.                               ║
║                                                                               ║
║  WITHOUT deadline propagation:                                                ║
║  B waits its own fixed timeout (say, 10 seconds) for C.                      ║
║  A waits its own fixed timeout (say, 10 seconds) for B.                      ║
║  Client waits 10+ seconds for a service that is clearly failing.             ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

Deadline propagation converts a "hang for the maximum timeout of every service" scenario into "fail as fast as the slowest step in the chain." The client gets an answer (even if it is an error) quickly, rather than waiting through multiple timeout windows stacked on top of each other.

In practice, deadlines are often passed in request headers. gRPC has native deadline propagation built in. For HTTP APIs, you can pass a `X-Request-Deadline` header with a Unix timestamp and have every service respect it.

---

## L5 vs. L6 Thinking on Backpressure

This section is about how senior engineers think about these problems versus junior engineers. Both groups know the basic techniques. The difference is in the questions they ask first.

```
╔═══════════════════════════════════════════╦══════════════════════════════════════╦══════════════════════════════════════════════════════════════════════════╗
║ Scenario                                  ║ L5 Response                          ║ L6 Response                                                              ║
╠═══════════════════════════════════════════╬══════════════════════════════════════╬══════════════════════════════════════════════════════════════════════════╣
║ "Our service is slow."                    ║ "Scale up — add more servers."       ║ "What's the bottleneck? If it's a downstream dependency (DB, external    ║
║                                           ║                                      ║ API), adding more servers just creates more load on the bottleneck.       ║
║                                           ║                                      ║ You need backpressure to the upstream caller so they stop sending         ║
║                                           ║                                      ║ faster than the bottleneck can handle."                                  ║
╠═══════════════════════════════════════════╬══════════════════════════════════════╬══════════════════════════════════════════════════════════════════════════╣
║ "Our queue depth is growing."             ║ "Add more consumers to drain it."    ║ "Is the queue growing because producers are too fast, or consumers are   ║
║                                           ║                                      ║ too slow? Growing producers → apply rate limits upstream. Slow           ║
║                                           ║                                      ║ consumers → find the bottleneck in the consumer (CPU? DB? External API?) ║
║                                           ║                                      ║ and fix that. These are different problems with different solutions."     ║
╠═══════════════════════════════════════════╬══════════════════════════════════════╬══════════════════════════════════════════════════════════════════════════╣
║ "Rate limit is 1,000 req/sec."            ║ "That's our SLA limit. Enforce it."  ║ "Does 1,000 req/sec mean sustained throughput or peak burst? A token     ║
║                                           ║                                      ║ bucket with 1,000 capacity and a 200 refill rate supports 200/s sustained ║
║                                           ║                                      ║ with 1,000 burst. If you need 1,000 sustained, the bucket fill rate must  ║
║                                           ║                                      ║ be 1,000 — which means you need servers that can genuinely handle 1,000/s."║
╠═══════════════════════════════════════════╬══════════════════════════════════════╬══════════════════════════════════════════════════════════════════════════╣
║ "Client retries are overwhelming us."     ║ "Block the retries."                 ║ "Why are clients retrying so much? If our error rate is 30%, clients      ║
║                                           ║                                      ║ SHOULD retry — we are failing them. Blocking retries treats the symptom. ║
║                                           ║                                      ║ Fix the error rate. If retries are still too aggressive, tell clients to  ║
║                                           ║                                      ║ add exponential backoff. But start with: why are we failing 30% of        ║
║                                           ║                                      ║ requests in the first place?"                                            ║
╠═══════════════════════════════════════════╬══════════════════════════════════════╬══════════════════════════════════════════════════════════════════════════╣
║ "Backpressure is causing client           ║ "Increase the client timeout."       ║ "The backpressure is working correctly — the client is being told to      ║
║  timeouts."                               ║                                      ║ slow down, and it is experiencing the cost of not slowing down. Increasing║
║                                           ║                                      ║ the timeout makes the client wait longer before it retries, which creates  ║
║                                           ║                                      ║ even more load. Investigate why the client is sending faster than we can   ║
║                                           ║                                      ║ process. The timeout is the correct signal — the client should back off."  ║
╚═══════════════════════════════════════════╩══════════════════════════════════════╩══════════════════════════════════════════════════════════════════════════╝
```

The L6 pattern is consistent: ask "WHY is this happening?" before asking "HOW do we respond?" The response to a symptom is often the wrong lever. Finding the root cause leads to solutions that actually fix the system rather than hiding the problem.

---

## Real Incident: How Backpressure Saved (and Failed to Save) a System

Sometimes the best way to understand a concept is to see what happens when a system has it — and what happens when a system does not. Here are two stories from the same fictional e-commerce company on the same Black Friday.

---

### Story 1 — When Backpressure Worked: The Recommendation Service

It is 6:00 AM on Black Friday. A marketing email goes out to 10 million customers: "SALE STARTS NOW." Within minutes, traffic spikes to 10× the normal level.

The company's recommendation service — the system that decides which products to show each customer — normally handles 5,000 requests per second. Now it is receiving 50,000 requests per second.

Six months earlier, an engineer had added a token bucket rate limiter to the recommendation service:
- Bucket capacity: 50,000 tokens (large burst buffer)
- Refill rate: 5,000 tokens per second (the actual sustainable rate)
- Response when limited: HTTP 429 with `Retry-After: 1`

At 10× traffic, the bucket empties in 1 second. Subsequent requests receive immediate 429 responses. No waiting. No pile-up.

The main product page had been designed with this in mind: if the recommendation service returns 429, fall back to "Featured Items" — a static list of popular products that needs no recommendation call.

Result: customers on the first wave of traffic (before the bucket empties) see personalized recommendations. Customers on subsequent requests see "Featured Items." From the customer's perspective, both experiences look perfectly normal — featured items is a common e-commerce pattern. Nobody notices the degradation. 

Zero customer-facing errors. Zero service downtime. The recommendation service runs at exactly 5,000 requests per second all morning — the rate it can actually handle — and the rest of the traffic gracefully falls back.

The token bucket was the valve. The fallback was the contingency plan. Together they made the system resilient to a 10× traffic spike.

---

### Story 2 — When No Backpressure Failed: The Inventory Service

Same Black Friday. Same 10× traffic spike. Same morning. But a different part of the system.

The inventory service — which checks whether a product is in stock before allowing a customer to add it to their cart — has no backpressure mechanism. No rate limit. No circuit breaker. No fallback.

Normally, each inventory check takes 50ms. The service handles it fine.

Under 10× load, the database powering the inventory service starts to struggle. Each check now takes 800ms (16× slower). The service has a thread pool of 200 threads. Each thread is now tied up for 800ms instead of 50ms.

At 800ms per request and 200 threads, maximum throughput is 200 / 0.8 = 250 requests per second. Before the traffic spike, it was handling 5,000 requests per second. Now it can only handle 250.

The 4,750 excess requests per second need to go somewhere. They queue in front of the inventory service. The queue grows by 4,750 requests every second. Memory fills up holding pending requests. New requests that arrive cannot even get into the queue — they time out immediately at the load balancer.

Within 4 minutes, the inventory service is completely unresponsive. Every product page returns an error because the cart system cannot check inventory. Checkout is impossible. Customers see blank error pages.

The cascading failure spreads: the recommendation service (which had just survived via its rate limiter) now takes calls from the product page — calls that include "check inventory before showing add-to-cart button." Those calls go to the dead inventory service, time out after 10 seconds, and now the product page itself starts timing out.

Within 8 minutes, the entire shopping experience is down.

Total cost: estimated $4M in lost sales, $1.2M in refunded delivery charges (some orders that DID go through before the outage could not be confirmed), and a very bad news cycle.

---

### The Contrast

```
╔═════════════════════════════════════════╦═════════════════════════════════════════════╗
║ Recommendation Service (Survived)       ║ Inventory Service (Failed)                  ║
╠═════════════════════════════════════════╬═════════════════════════════════════════════╣
║ Had a rate limiter (token bucket)       ║ No rate limiter                             ║
║ Had a fallback behavior                 ║ No fallback — all or nothing                ║
║ Rejected excess traffic immediately     ║ Accepted all traffic, queued until crash    ║
║ Failed gracefully with degraded UX      ║ Failed catastrophically with total outage   ║
╠═════════════════════════════════════════╬═════════════════════════════════════════════╣
║ Same 10× traffic spike                  ║ Same 10× traffic spike                      ║
║ Result: survived                        ║ Result: total outage, cascading failure      ║
╚═════════════════════════════════════════╩═════════════════════════════════════════════╝
```

Same event. Same company. Same traffic. Completely different outcomes — because one service had a plan and the other did not.

The difference was not engineering skill. It was whether someone had asked, six months earlier, "what happens to this service when it receives 10× its normal load?" For the recommendation service, someone had. For the inventory service, nobody had.

Backpressure is not a complicated system to build. A token bucket is 30 lines of code. A fallback behavior is a 5-line if-else in the caller. The hard part is remembering to think about it before the Black Friday that tests you.

---

## Common Mistakes (And How to Avoid Them)

Before the summary, here is a list of the most common errors engineers make when implementing idempotency and backpressure — collected from real incident postmortems.

---

### Idempotency Mistakes

**Mistake 1: Storing the idempotency key result before the operation completes.**

The symptom: retries return "success" even though the original operation failed partway through. Orders are created without payments. Records are partially written.

The fix: store the result as the LAST step, after the complete operation finishes.

---

**Mistake 2: Using a random UUID as the idempotency key without persisting it first.**

The symptom: client crashes mid-request. On restart, it generates a new random UUID. The server sees a new key and processes the operation again. Double charge.

The fix: either persist the key to durable storage before the request, or derive the key deterministically from stable business data (order_id, user_id, attempt_number).

---

**Mistake 3: Not setting a TTL on stored keys.**

The symptom: the idempotency keys table in the database grows forever. After a year, it has millions of rows for operations nobody will ever retry. Queries slow down. Disk fills up.

The fix: always set an expiry on stored idempotency keys. 24 hours to 7 days is typical for payment systems.

---

**Mistake 4: Not validating that the retry matches the original request.**

The symptom: a client bug sends a retry with the same key but a different amount. The server returns the cached result from the ORIGINAL amount. An incorrect charge is recorded as correct.

The fix: store a fingerprint (hash) of the original request parameters alongside the cached result. On retry, verify the fingerprint matches.

---

### Backpressure Mistakes

**Mistake 5: Setting a rate limit but having no fallback behavior.**

The symptom: the service correctly rate-limits to 100 requests/second, but the callers receive 429 errors and have no way to fall back to a degraded experience. Users see error pages instead of slightly worse pages.

The fix: design fallbacks BEFORE you add rate limits. What should the caller do when it gets a 429? Can it use cached data? Can it show a simpler page? Can it queue the request for later? The rate limit is only half the solution.

---

**Mistake 6: One global token bucket for all clients.**

The symptom: a single misbehaving client (maybe a bug causing a retry storm) exhausts the shared bucket and causes 429 errors for all other clients. Healthy clients are penalized for one client's bad behavior.

The fix: use per-client buckets (keyed by API key, user ID, or IP address). Isolate the blast radius of a misbehaving client to that client only.

---

**Mistake 7: Adding backpressure at the edge but not at internal service boundaries.**

The symptom: the public-facing API rate-limits external traffic correctly. But internally, Service A calls Service B which calls Service C with no limits between them. When B slows down, A keeps sending at full speed. B's queue fills up. Cascading failure.

The fix: every service-to-service call needs its own backpressure mechanism. Internal calls are not safer than external calls — they are often FASTER and can generate MORE load in less time.

---

**Mistake 8: Treating backpressure as a permanent fix for an undersized system.**

The symptom: the service rate-limits clients to 100/second but the actual demand is 10,000/second. The rate limit is set so low that it is a constant pain point, not an emergency safety valve. Customers are permanently frustrated.

The fix: backpressure is a safety valve for traffic spikes and service protection, not a substitute for scaling. If sustained demand consistently exceeds capacity, scale up. Rate limits should protect you from anomalies, not constrain normal usage.

---

## Chapter Summary — Part B

Let's step back and collect what we learned.

**Idempotency** solves the network uncertainty problem: you cannot know if a response was lost, so retrying is sometimes unavoidable, but retrying non-idempotent operations (like charging a credit card) causes disasters. Idempotency keys give every operation a unique tracking number. The server uses the key to deduplicate retries — processing the operation exactly once, no matter how many times the client retries.

Good idempotency keys are: derived from stable business identifiers (not random), generated before the attempt (so they survive crashes), scoped to the right user/operation, and given a TTL so they expire.

Idempotency does not prevent ordering problems, does not replace business constraints like "one ticket per user," does not work if you store partial states, and does not help when different requests for the same resource have different keys.

**Backpressure** solves the flow rate mismatch problem: clients send faster than servers can process, servers queue up, queues overflow, systems crash. Backpressure is the server saying "slow down" before that happens.

The three main strategies: blocking (requests wait their turn — simple but fragile at high rates), token bucket (burst-then-throttle — the industry standard for rate limiting), and AIMD adaptive limits (slowly loosen when healthy, aggressively tighten when struggling — self-regulating).

Push vs. pull determines who controls flow: push is faster but needs explicit "stop" signals, pull is safer because the consumer requests only what it can handle. Reactive Streams is the industry standard for push-with-controlled-flow.

Across service chains, backpressure must propagate. A service that absorbs downstream pressure silently is a single-point-of-failure waiting to happen. Deadline propagation ensures that the entire chain fails fast rather than hanging through every service's timeout window individually.

The L6 insight threading through all of this: **ask "why" before "how."** Why is traffic high? Why are errors high? Why is the queue growing? The answer to "why" points to the real fix. The "how" only matters once you know what you are actually fixing.

---

## The Full Picture: How Idempotency and Backpressure Work Together

One more thing before we close Part B. These two topics are not independent. They are designed to work as a team.

Here is the scenario that ties them together:

A client sends a request. The server is under load and rate-limits it (backpressure: 429, Retry-After: 2 seconds). The client waits 2 seconds and retries. This time the request gets through. The server processes it. The response is lost (network uncertainty). The client retries again — but now with an idempotency key, so the server recognizes the duplicate and returns the cached result without double-processing.

Each mechanism covers a gap the other cannot:

- **Backpressure** prevents the server from being overwhelmed in the first place.
- **Retries with exponential backoff** (from Part A) handle temporary failures gracefully.
- **Idempotency keys** make those retries safe even for non-idempotent operations.
- **Circuit breakers** (from Part A) stop retries when a service is completely down, preventing retry storms.

Together, they form a complete reliability layer around any API call:

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║          THE COMPLETE RELIABILITY LAYER AROUND AN API CALL                   ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  1. Client generates idempotency key BEFORE the request.                     ║
║     (So retries can be safe)                                                  ║
║                                                                               ║
║  2. Circuit breaker checks: is the server known to be down?                  ║
║     YES → fail fast, do not even try. (From Part A)                          ║
║     NO  → proceed.                                                            ║
║                                                                               ║
║  3. Client sends request + idempotency key.                                  ║
║                                                                               ║
║  4. Server checks backpressure: is the token bucket empty?                   ║
║     YES → return 429 with Retry-After: N                                     ║
║     NO  → proceed to check idempotency key.                                  ║
║                                                                               ║
║  5. Server checks idempotency key: seen before?                               ║
║     YES → return cached result (no re-processing).                           ║
║     NO  → process the request, store result, return it.                      ║
║                                                                               ║
║  6. If client got 429: wait Retry-After seconds, then retry from step 2.     ║
║     If client got timeout: retry from step 2 with SAME idempotency key.      ║
║     If client got success: done. Key can be discarded.                        ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

This is what "production-grade reliability" means in practice. Not any one of these techniques in isolation — all of them together, each covering the failure modes the others cannot.

When you are designing a system and you identify an API call that: (1) must not be duplicated (payment, order creation), (2) must be retried on failure, and (3) might receive traffic spikes — you need all four mechanisms: idempotency keys, retries with backoff, circuit breakers, and backpressure. Leaving any one out creates a gap that will eventually cause an incident.

---

*End of Part B. Part C covers the interaction between backpressure, retries, and idempotency in combined system designs — and how to reason about failure scenarios that involve all three.*
# Chapter 23: Backpressure, Retries, and Idempotency
## Part C: Load Shedding, Cascading Failures, Design Evolution, and Real Incidents

*(Note to reader: Parts A and B of this chapter covered retries, circuit breakers, idempotency, and backpressure — the tools that help your system stay stable when things go wrong. This part goes further. We cover load shedding — how to deliberately drop some work so you can finish the rest. We cover cascading failures — how one small problem turns into a total outage. We look at real incidents with timelines you can follow step by step. And we trace how a system grows from "works when everything is fine" to "stays alive even when half of it is on fire." Every concept is explained from scratch. No jargon is left unexplained. Analogies come first, code comes second.)*

---

# Part 4: Load Shedding — Choosing What to Drop

---

## What is Load Shedding?

Here is a safety rule you have probably heard on an airplane.

Before every flight, the flight attendant stands in the aisle and runs through the safety demonstration. At one point, they say something that sounds a little cold:

*"In the event of a loss of cabin pressure, oxygen masks will drop from the compartment above your seat. Please put on your own mask before assisting others — including children."*

The first time you hear that, it might feel selfish. Put on YOUR mask before helping a child? What kind of rule is that?

But think about what happens if you do it the other way. You try to help the child first. It takes ten seconds. In low-oxygen air, you start feeling dizzy at fifteen seconds. At thirty seconds, you pass out. Now there is a confused, panicking child AND an unconscious adult. Two problems instead of one. Nobody is getting helped.

By protecting yourself first — spending five seconds on your own mask — you stay conscious. You can then help the child calmly and effectively. You can help the person in the next row. You can help four people instead of zero.

**Load shedding is the same philosophy applied to computer systems.**

When a system is getting more requests than it can handle — say, ten times its normal load — it faces a choice. It can try to handle every single request. Or it can deliberately refuse some requests so it can handle the rest well.

If it tries to handle everything, it usually ends up handling nothing. The server runs out of memory. Threads pile up waiting for each other. Response times balloon from 50 milliseconds to 30 seconds. Every user experiences a slow, broken, degraded system. The server crashes. Now nobody gets served.

If it instead refuses 20 percent of requests immediately — with a clear, fast error message — then the remaining 80 percent get handled quickly and correctly. Eighty percent of users get good service. Twenty percent get a fast error they can retry in a moment. Total users served well: 80 percent. Compare that to the alternative: zero.

This is the counterintuitive truth of load shedding: **by serving fewer requests, you serve more users.**

---

### The Explicit vs. Implicit Trade-Off

Without load shedding, an overloaded system does something worse than dropping requests. It slows ALL requests equally.

Imagine a restaurant with four chefs. Normally they handle forty tables. On a crazy Friday night, eighty tables show up. The restaurant tries to seat everyone. Now all eighty tables wait. Each table waits twice as long. The kitchen is confused, orders are getting mixed up, waiters are stressed. Every single customer has a bad experience.

The alternative: seat forty tables. Tell the other forty: "We are fully booked tonight, we are so sorry." Forty people are disappointed but know where they stand. Forty people have a wonderful meal.

Without load shedding: eighty people have a miserable experience.
With load shedding: forty people have a great experience, forty people get a clear answer and can make other plans.

Load shedding makes the trade-off explicit. Some requests succeed perfectly. Some fail immediately with a clear error code (503 Service Unavailable). Nobody hangs in an indefinite slow limbo.

```
WITHOUT LOAD SHEDDING:
┌─────────────────────────────────────────────────────────────────┐
│  100 requests/sec arrive. System can handle 50/sec.             │
│                                                                  │
│  Result: ALL 100 requests slow down                             │
│  ├── Request 1 → 8,000ms response   (should be 80ms)           │
│  ├── Request 2 → 9,200ms response                               │
│  ├── Request 3 → 11,000ms response                              │
│  └── ... all 100 users angry, most requests timeout, system crashes│
│                                                                  │
│  Users served well: 0 out of 100                                │
└─────────────────────────────────────────────────────────────────┘

WITH LOAD SHEDDING:
┌─────────────────────────────────────────────────────────────────┐
│  100 requests/sec arrive. System can handle 50/sec.             │
│  System sheds 50 requests immediately with 503.                 │
│                                                                  │
│  Result: 50 requests handled at normal speed                    │
│  ├── Request 1  → 82ms response  ✓ (fast, correct)             │
│  ├── Request 2  → 79ms response  ✓                              │
│  ├── Request 51 → 503 error immediately  (retry in 5 seconds)  │
│  └── ... 50 users happy, 50 users get a fast clear signal       │
│                                                                  │
│  Users served well: 50 out of 100 (vs. 0 without shedding)     │
└─────────────────────────────────────────────────────────────────┘
```

The on-call engineer looking at these two scenarios sees something important: the system WITH load shedding is actually healthier. Error rates are high but they are 503 errors — controlled rejections. The system itself is stable. The system WITHOUT load shedding eventually crashes — now you get zero service instead of partial service.

---

## Strategy 1: Queue-Based Load Shedding

### The Nightclub Bouncer

Picture a popular nightclub on a Saturday night. The club has a maximum legal capacity of 200 people. There is a bouncer at the door.

When the club is below capacity, the bouncer lets everyone in. When the club hits 200 people, the bouncer stops letting new people enter. Some people wait in line outside (the queue). If the line is very long — say, a hundred people waiting — the bouncer walks down the line and tells people: "It is going to be more than an hour wait. You might want to try somewhere else tonight." Some people leave. Some stay.

The bouncer does NOT let the crowd grow forever. If people kept queueing indefinitely, the line would stretch around the block. People would wait three hours. Some would wait only to find out the club is closing. That is a terrible experience AND it creates a mob situation outside.

Queue-based load shedding works the same way:

- Incoming requests go into a queue (the line outside the club)
- Workers process requests from the queue at a fixed rate (bouncers let people in at a fixed rate)
- If the queue exceeds a maximum length, new requests are rejected immediately (bouncer tells you "too long, come back another time")
- Clients get a fast "503 Service Unavailable" response rather than an indefinitely long wait

```
QUEUE-BASED LOAD SHEDDING:

New requests arrive:                Workers process:
        │                                  │
        ▼                                  ▼
┌──────────────────────────────────────────────────────────┐
│                      QUEUE                               │
│  [req1][req2][req3][req4][req5]...[req999][req1000]      │
│   oldest                              newest             │
│                     max = 1,000 items                    │
└──────────────────────────────────────────────────────────┘
        │                                  │
        ▼                                  ▼
  If queue < 1,000:              Workers pull from front,
  accept request,                process, send response
  add to back of queue

  If queue ≥ 1,000:
  REJECT immediately
  → 503 "Queue full, retry later"
```

### How Long Will People Wait?

Queue sizing requires a simple calculation. Before you pick a maximum queue size, ask: "If a request sits at the very back of this queue, how long will it wait before a worker gets to it?"

The formula:

```
Maximum wait time = queue size ÷ processing rate

Example:
- Workers process 100 requests per second
- Maximum queue size = 1,000 requests
- Maximum wait = 1,000 ÷ 100 = 10 seconds

If clients timeout after 3 seconds, a 10-second max wait is terrible.
Most requests at the back of the queue will timeout before they are processed.
You are doing work for nothing.

Better choice:
- Client timeout = 3 seconds
- Processing rate = 100 req/sec
- Maximum useful queue size = 3 × 100 = 300 requests
```

This calculation is important. A queue that is "too large" gives you false comfort. You think requests are queued and will be served. But if they have been waiting longer than the client timeout, the client has given up. You will process those requests and send responses to nobody. Pure waste.

A tight queue that matches client timeout expectations forces you to reject clearly rather than pretend you will serve requests you never will.

```python
# Queue-based load shedding implementation

MAX_QUEUE_SIZE = 300          # Calculated based on timeout × processing_rate
request_queue = Queue(maxsize=MAX_QUEUE_SIZE)

def handle_incoming_request(request):
    """Called for every incoming request"""
    try:
        # Try to add to queue (non-blocking — fails immediately if full)
        request_queue.put_nowait(request)
        return "QUEUED"
    except QueueFull:
        # Queue is at capacity — reject immediately
        metrics.increment("requests.rejected.queue_full")
        return Response(
            status=503,
            body="Service is at capacity. Please retry in a few seconds.",
            headers={"Retry-After": "3"}  # Tell client when to retry
        )

def worker_loop():
    """Each worker runs this loop"""
    while True:
        request = request_queue.get(timeout=1.0)  # Wait up to 1s for work
        result = process(request)
        send_response(request.client, result)
```

The `put_nowait()` call is the key: it fails immediately if the queue is full. The worker does NOT block waiting for space. This makes the rejection fast — the client gets their 503 in milliseconds, not seconds.

---

## Strategy 2: Random Early Detection (RED)

### The Early Warning System

Queue-based shedding has a problem: it is a cliff. Below 1,000 items, you accept everything. At 1,001 items, you start rejecting everything. This "cliff edge" creates instability. Here is what happens:

1. Queue reaches 1,000. You reject everything.
2. Queue drains quickly (no new arrivals getting in).
3. Queue drops to 800. You accept everything again.
4. Queue fills back to 1,000.
5. You reject everything. Cycle repeats.

The system oscillates. Clients have a terrible experience — some requests get through, some do not, in a jagged pattern.

**Random Early Detection (RED)** solves this by starting to reject SOME requests before the queue is full, and gradually rejecting more as the queue fills up. No cliff. A smooth slope.

The analogy: instead of the bouncer waiting until the club is 100% full to start turning people away, they start occasionally (and randomly) turning people away at 80% capacity. As the club gets more full, more people are turned away. By the time it hits 100%, almost everyone is being turned away.

Why random? Because random rejection is fair. Everyone in line has an equal chance of being rejected at any given utilization level. And because a gradual increase in rejection keeps the queue in a stable zone — you never hit the cliff.

```
RED REJECTION PROBABILITY:

Queue 0-50% full:    reject 0%  of requests (accept all)
Queue 50-60% full:   reject ~3% of requests
Queue 60-70% full:   reject ~6% of requests
Queue 70-80% full:   reject ~10% of requests
Queue 80-90% full:   reject ~55% of requests
Queue 90-100% full:  reject ~100% of requests

The S-curve keeps the queue stable around 70-80% utilization.
```

Here is the RED algorithm written out:

```python
def should_reject_request(current_queue_size, max_queue_size):
    """
    Returns True if this request should be rejected.
    Probability of rejection increases as queue fills.
    """
    # What fraction of the queue is used?
    utilization = current_queue_size / max_queue_size

    if utilization < 0.5:
        # Queue less than half full — accept everything
        reject_probability = 0.0

    elif utilization < 0.8:
        # 50% to 80% full — gently start rejecting
        # At 50% full: 0% rejection
        # At 80% full: 10% rejection
        # Linear increase between these two points
        fraction_through_range = (utilization - 0.5) / 0.3  # 0.0 to 1.0
        reject_probability = fraction_through_range * 0.10

    else:
        # 80% to 100% full — rejection ramps up fast
        # At 80% full: 10% rejection
        # At 100% full: 100% rejection
        fraction_through_range = (utilization - 0.8) / 0.2  # 0.0 to 1.0
        reject_probability = 0.10 + (fraction_through_range * 0.90)

    # Roll the dice
    return random.random() < reject_probability

def handle_incoming_request(request):
    """Called for every incoming request"""
    queue_size = request_queue.qsize()

    if should_reject_request(queue_size, MAX_QUEUE_SIZE):
        # Probabilistic rejection — this request lost the lottery
        metrics.increment("requests.rejected.red")
        return Response(503, "High load — please retry with backoff")

    request_queue.put(request)
    return "QUEUED"
```

The resulting behavior is much smoother:

```
Queue utilization over time:

WITH CLIFF-BASED REJECTION:           WITH RED:
                                       
100% ─── accept ─── CLIFF ───reject   100%  ─────────────────────────
                                              slightly increasing
 80%                                    80%  rejection rate here     
                                              keeps system stable    
 50%                                    50%  
                                              gentle rejection        
  0%                                     0%  starts here            
                                              
Result: oscillation, spiky behavior    Result: smooth, stable at ~75%
```

RED is a staple algorithm in networking and load balancing. It was originally designed for network routers. The same idea works just as well in application-level load shedding.

---

## Strategy 3: Priority-Based Load Shedding

### The Hospital Emergency Room

Picture a hospital emergency room on a busy Saturday night. There are more patients than the ER can handle. What does the ER do?

They do not turn away patients randomly. They do not close the doors until things calm down. They do triage.

A nurse or doctor quickly evaluates each incoming patient and assigns a priority:
- **Critical:** Heart attack, stroke, severe trauma. Seen immediately.
- **Urgent:** Broken bone, high fever in an infant. Seen within an hour.
- **Less urgent:** Sprained ankle, minor cut needing stitches. Seen within a few hours.
- **Non-urgent:** Mild sore throat, asking for a prescription refill. Might be redirected to urgent care.

When the ER is overwhelmed, they do not slow down care for the heart attack patient to be "fair" to the sprained ankle patient. They protect the most critical cases and let the less critical ones wait or go elsewhere.

Priority-based load shedding works exactly the same way. You assign a priority to every type of request. When load is high, you drop low-priority requests first. High-priority requests are protected.

```
PRIORITY TIERS (example for an e-commerce system):

CRITICAL    Payment processing, user authentication, health checks
            → NEVER dropped. System would rather crash than drop these.

HIGH        Product search, browse, add to cart, order status
            → Dropped only if system is near total failure

MEDIUM      Product recommendations, "customers also bought"
            Wishlist sync, review fetching
            → Dropped when system load > 80%

LOW         Analytics event logging, browsing history sync
            Non-essential notification triggers
            Personalization model updates
            → Dropped when system load > 60%
```

The thresholds look like this:

```
System Load    Action
──────────────────────────────────────────────────────────
0% – 60%       All tiers served normally
60% – 80%      LOW priority requests start being shed
80% – 90%      MEDIUM priority also shed
90% – 95%      HIGH priority shed selectively
95% – 100%     Only CRITICAL requests served
```

Implementation:

```python
def classify_priority(request):
    """
    Look at the request and decide its priority tier.
    Returns: "CRITICAL", "HIGH", "MEDIUM", or "LOW"
    """
    path = request.path

    # Payment and auth — always critical
    if path.startswith("/payment") or path.startswith("/auth"):
        return "CRITICAL"

    # Core shopping flows
    if path in ["/search", "/product", "/cart", "/checkout", "/order"]:
        return "HIGH"

    # Nice-to-have features
    if path in ["/recommendations", "/wishlist", "/reviews"]:
        return "MEDIUM"

    # Background / analytics
    if path.startswith("/analytics") or path.startswith("/sync"):
        return "LOW"

    return "MEDIUM"  # Default if unsure


def handle_request(request):
    """Entry point for all incoming requests"""
    current_load = get_current_load_percentage()  # 0.0 to 1.0
    priority = classify_priority(request)

    # Check if this priority tier should be shed at current load
    if current_load > 0.95 and priority == "HIGH":
        return shed(request, "System near capacity")

    if current_load > 0.80 and priority == "MEDIUM":
        return shed(request, "High load — non-critical features paused")

    if current_load > 0.60 and priority == "LOW":
        return shed(request, "High load — background sync paused")

    # This request gets through
    return process(request)


def shed(request, reason):
    """Reject a request with a helpful message"""
    metrics.increment(f"requests.shed.{request.priority}")
    return Response(
        status=503,
        body=f"Service temporarily reduced: {reason}",
        headers={"Retry-After": "10"}
    )
```

### The Business Challenge: Who Decides What's LOW Priority?

Here is the hard part that no engineering textbook tells you: priority assignment is NOT purely a technical decision. It is a business and product decision.

If you tell the recommendations team "your feature gets dropped during high load," they will want to know:
- Why?
- How often will this happen?
- Will users notice?
- Is this permanent or temporary?

If their feature is dropped 40 percent of the time during peak hours, their product metrics look terrible — not because their code is bad, but because it is being deliberately shedded. They need to know. They need to agree.

Priority-based load shedding requires a meeting across teams. Someone with authority (usually an engineering director or VP of engineering) needs to sign off on the priority tiers. The tiers need to be documented. And they need to be reviewed after incidents to confirm the decisions still make sense.

Without this alignment, priority shedding causes politics, not just code. Get the conversation done before the incident, not during it.

---

## Strategy 4: Deadline-Based Load Shedding

### The Stale Food Problem

A restaurant prepared one hundred salads at noon. By 2pm, the salads are still sitting in the kitchen. At 3pm, a customer orders a salad. Should the kitchen serve a three-hour-old salad?

Of course not. The salad is past its useful life. Serving it anyway does not help the customer — it makes things worse (food safety risk, unhappy customer). The right move: throw the old salads out and make a fresh one, or tell the customer "we are out of salads today."

Requests have the same "freshness" problem. A request is useful only if the client is still waiting for a response. If a user clicked "Search" and your server queues that request but does not process it for 10 seconds... and the user's browser has a 3-second timeout... then the user has already seen an error and moved on. Processing that queued request at the 10-second mark sends a response to nobody. Pure waste.

**Deadline-based load shedding** means: every request carries a deadline ("I am willing to wait until time T"). When workers pull requests from the queue, they check whether the deadline has passed. If it has, they skip the request without processing it.

```
DEADLINE-BASED SHEDDING:

T = 0.0s   User clicks Search. Request sent to server with deadline = T+3.0s
T = 0.1s   Server receives request, adds to queue. 
           Queue has 800 items ahead of it. At 100 req/sec processing rate,
           this request will not be processed until T = 8.1 seconds.
T = 3.0s   Client timeout fires. User sees "Search timed out." User refreshes.
           (New request generated — old one still in queue.)
T = 8.1s   Worker pulls original request from queue.
           Checks deadline: T=8.1s > deadline=3.0s. EXPIRED.
           Worker discards request WITHOUT processing it.
           Response would go to nobody anyway.

Savings: one database query, one search engine call, one compute slot.
Multiply by thousands of queued expired requests during overload.
```

```python
import time

def process_queue(queue):
    """Worker loop — processes requests from the queue"""
    while True:
        if queue.empty():
            time.sleep(0.01)  # Brief sleep when nothing to do
            continue

        request = queue.dequeue()

        # Check: is the client still waiting?
        if time.now() > request.deadline:
            # Client has already timed out. Processing is pointless.
            metrics.increment("requests.discarded.expired")
            metrics.histogram("request.age_at_discard",
                              time.now() - request.received_at)
            continue  # Skip to next request

        # Client is still waiting — process this request
        start = time.now()
        result = do_work(request)
        latency = time.now() - start

        # Send the response
        send_response(request.client_connection, result)
        metrics.histogram("request.processing_latency", latency)
```

### Why Deadlines Should Flow Through the Whole System

Here is a subtlety that catches teams off guard.

Suppose Service A receives a request from a user with a 10-second timeout. Service A calls Service B to do part of the work. Service B calls Service C for part of ITS work.

If each service has its own independent timeout (say, each waits up to 10 seconds), the total wait time can be up to 30 seconds — even though the user will give up after 10 seconds.

The right approach: pass the original deadline through the whole chain.

```
User timeout: 10 seconds. Request arrives at T=0. Deadline = T+10s.

Service A receives request.
├── Remaining time until user gives up: 10 seconds
├── Calls Service B with deadline = T+10s (pass the same deadline through)
│   ├── Service B calculates: 9.8 seconds remain
│   ├── Calls Service C with deadline = T+10s
│   │   └── Service C calculates: 9.5 seconds remain
│   └── Service B will not wait longer than 9.8 seconds for Service C
└── Service A will not wait longer than 10 seconds for Service B

Result: nobody wastes time after the user has already given up.
```

This is called "context propagation" or "deadline propagation." In practice, you pass the deadline as a request header or in the RPC metadata. Each service reads it and uses it as its own timeout for downstream calls.

---

## Graceful Degradation — Having a Plan B (and a Plan C)

### The Swiss Army Knife vs. The Butter Knife

A Swiss Army knife has many tools packed into one handle: blade, scissors, can opener, screwdriver, toothpick. If the scissors break, you still have the blade. If the can opener breaks, you still have the screwdriver. The knife is resilient because it has alternatives.

A simple butter knife has one job. If it breaks, you have nothing.

Your system can be built like a Swiss Army knife. Instead of one way to serve every request, you build a ladder of fallbacks. The primary way is the best. The first fallback is a bit worse. The second fallback is noticeably worse. The emergency fallback is far worse. But each rung of the ladder is better than nothing — better than a 500 error.

This is called **graceful degradation**: when the best option is unavailable, you gracefully fall back to a lesser option, rather than failing completely.

---

### The Degradation Ladder for a Search Feature

Here is a concrete example. An e-commerce site has a product search feature. Under normal conditions, search is fast and smart. But what happens as parts of the system fail?

```
╔══════════════════════════════════════════════════════════════════════╗
║         SEARCH FEATURE — DEGRADATION LADDER                         ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  TIER 0 — Fully Healthy (Normal Operation)                          ║
║  ─────────────────────────────────────────────────────────────────  ║
║  What happens: Real-time personalized search. Your search history   ║
║  shapes results. Spell correction. Category filters. Sorting.       ║
║  Latency: ~50ms                                                      ║
║  What users see: Beautiful, relevant, personalized results          ║
║                                                                      ║
║  TIER 1 — Search Backend Slow (Degraded)                            ║
║  ─────────────────────────────────────────────────────────────────  ║
║  What happens: Serve cached search results from Redis.              ║
║  Cache is up to 30 minutes old. Most popular queries are the same   ║
║  from hour to hour. 95% of users never notice the cache.            ║
║  Latency: ~5ms (from cache, no backend call)                        ║
║  What users see: Results look the same. Slightly stale. Rare edge   ║
║  cases get wrong results.                                           ║
║                                                                      ║
║  TIER 2 — Search Backend Down (Worse Degradation)                   ║
║  ─────────────────────────────────────────────────────────────────  ║
║  What happens: Show the top 100 most-popular items for every search.║
║  No personalization. No query matching. Just "here are things       ║
║  people often buy." User can still browse and find something.       ║
║  Latency: ~1ms (pre-computed list)                                  ║
║  What users see: Results are generic. Search feels broken.          ║
║  But they can still use the site.                                   ║
║                                                                      ║
║  TIER 3 — Database Slow or Down (Severe Degradation)               ║
║  ─────────────────────────────────────────────────────────────────  ║
║  What happens: Show a completely static "Featured Products" page.   ║
║  This is a pre-rendered HTML file that needs NO backend call.       ║
║  No search at all. Just a curated list of products that were        ║
║  manually chosen last week.                                         ║
║  Latency: 0ms (static file served by CDN)                           ║
║  What users see: A catalog-style page. No search box at all.        ║
║  Strange but functional.                                            ║
║                                                                      ║
║  TIER 4 — Everything Down (Emergency Fallback)                      ║
║  ─────────────────────────────────────────────────────────────────  ║
║  What happens: Maintenance page with estimated return time.         ║
║  A single static HTML page. Served by a completely separate,        ║
║  tiny CDN. Needs NOTHING from your backend to render.               ║
║  What users see: "We are experiencing technical difficulties.       ║
║  Our team is aware and working on it. Estimated return: 2 hours."   ║
║  Angry, but informed.                                               ║
╚══════════════════════════════════════════════════════════════════════╝
```

The key insight: the key is pre-planning each tier. During an incident at 3am is not the time to ask "what should we show instead of search results?" The exhausted on-call engineer should not be making product decisions about fallback content. Have the answer decided, implemented, and TESTED before the outage. Every tier should be reachable and working before you ever need it.

### Implementing Graceful Degradation with Feature Flags

A feature flag is a configuration setting that controls whether a feature is on or off. Instead of deploying new code to disable a feature, you flip a flag in a database or config system. The change takes effect immediately, without a deployment.

Feature flags are your manual override switches during incidents.

```python
def get_search_results(query, user_id):
    """
    Try to get search results, falling through tiers as needed.
    Feature flags let engineers manually force lower tiers during incidents.
    Circuit breakers auto-force lower tiers when upstream is broken.
    """

    # TIER 0: Full personalized search
    # Active if: feature flag on AND circuit breaker for search is closed (healthy)
    if (feature_flags.is_enabled("search.full")
            and not circuit_breaker.is_open("search-backend")):
        try:
            results = search_service.search(query, user_id, personalized=True)
            metrics.increment("search.tier", tags={"tier": "0"})
            return results
        except Exception as e:
            # search_service failed — log it and fall through
            log.warning(f"Search tier 0 failed: {e}. Falling to tier 1.")

    # TIER 1: Cached search results (up to 30 minutes stale)
    if feature_flags.is_enabled("search.cache"):
        cached = search_cache.get(query)
        if cached:
            metrics.increment("search.tier", tags={"tier": "1"})
            return cached
        # Cache miss — fall through

    # TIER 2: Popular items list
    if feature_flags.is_enabled("search.popular"):
        try:
            popular = popular_items_service.get_top_100()
            metrics.increment("search.tier", tags={"tier": "2"})
            return popular
        except Exception:
            pass  # Fall through

    # TIER 3: Static featured products (no backend needed)
    metrics.increment("search.tier", tags={"tier": "3"})
    return static_featured_products  # A pre-loaded list in memory


# During an incident, on-call engineer runs:
#   feature_flags.disable("search.full")    # Forces tier 0 to skip
#   feature_flags.disable("search.cache")   # Forces tier 1 to skip
# This pins the system at tier 2 while the search backend is fixed.
# No code changes. No deployment. Instant effect.
```

The monitoring dashboard during an incident shows you which tier most searches are being served from. If tier 0 drops from 99% to 0% and tier 1 jumps to 98%, you know the search backend is unhealthy but the cache is saving you. When the backend recovers, tier 0 automatically starts taking over again.

---

# Part 5: Cascading Failures — When One Problem Becomes Many

---

## Anatomy of a Cascading Failure

### The Northeastern US Power Grid Blackout of 2003

On August 14, 2003, at 2:02pm Eastern Time, a software alarm system in Ohio stopped working. A specific monitoring alarm had silently failed due to a race condition in the energy management software. Nobody noticed.

At 2:14pm, a high-voltage power line in northern Ohio sagged into an overgrown tree and tripped — an automatic safety mechanism that disconnects a line when it detects a fault. This happens occasionally. It is routine. The line's load would normally be redistributed automatically to neighboring lines.

But the failed alarm system meant the Ohio control room did not know the line had tripped.

At 3:05pm, a second line tripped. Still no alarm. The control room had no idea.

As each line went down, its load transferred to neighboring lines. Those lines were now carrying more current than they were designed for. They sagged. More trees. More trips. Each trip made the remaining lines carry more load. Each remaining line was now closer to tripping.

At 4:05pm — less than two hours after the first tree contact — the cascade reached critical mass. Power plants began automatic shutdown (they cannot operate safely in an uncontrolled grid). Within nine seconds, 256 power plants went offline. 55 million people in the northeastern United States and Canada lost power.

The root cause: one tree contact. The duration of the root cause: seconds.
The outage: 55 million people. Duration: up to four days.

Software cascading failures follow this exact pattern. One small fault goes undetected. Load redistributes to neighboring components. They become overloaded. They fail. More load redistributes. More components fail. The cascade reaches critical mass and the entire system collapses — long after the original fault has resolved itself.

---

### The Anatomy of a Software Cascade: Service A, B, C

Here is how a cascading failure plays out in a typical distributed system with three services. Follow the timestamps carefully.

```
NORMAL OPERATION:

User → Service A (frontend API)
         │
         ▼
       Service B (business logic)
         │
         ▼
       Service C (database / data layer)

Each service handles its load. Response times are fast.
A: 80ms per request,  handling 10,000 req/sec
B: 50ms per request,  handling 10,000 req/sec (called once per A request)
C: 10ms per query,    handling 20,000 queries/sec (called twice per B request)
```

Now something goes wrong in Service C.

---

**T = 0 seconds: The Trigger**

Service C (the database) has a garbage collection pause. This is a routine event in many languages — the language runtime stops all threads briefly to clean up memory. Normally this takes 10-20 milliseconds. Today, the garbage collector encounters a particularly large memory heap and takes 2 full seconds.

During those 2 seconds, Service C is not processing queries. They are queuing up.

---

**T = 2 seconds: Slowdown Begins**

GC pause ends. Service C resumes. But it has a backlog of 2 seconds × 20,000 queries/sec = 40,000 queued queries. Processing these takes time. Service C's response time climbs from 10ms to 500ms. Not dead — just slow.

---

**T = 3 seconds: Service B Starts Struggling**

Service B calls Service C for every request. Calls now take 500ms instead of 10ms. How does this affect Service B?

Service B has 50 worker threads. Each thread can normally handle one request every 50ms (its own processing time) + 2 × 10ms (two database calls) = 70ms total. That is 14 requests per thread per second. 50 threads × 14 = 700 requests per second handled.

Wait — Service B was handling 10,000 req/sec before. That means Service B had about 10,000 ÷ 14 ≈ 714 threads normally. Let us say it has 1,000 threads.

Now: each database call takes 500ms. Total time per request = 50ms + 2 × 500ms = 1,050ms. One thread handles 1,000ms ÷ 1,050ms ≈ 0.95 requests per second. 1,000 threads × 0.95 = 950 req/sec.

Service B can now only handle 950 requests per second, down from 10,000. It has 9,050 requests per second it cannot process. They queue.

---

**T = 5 seconds: Service B's Queue Overflows**

Service B's request queue fills up in seconds. New requests from Service A start receiving 503 errors from Service B.

---

**T = 6 seconds: Retries Make It Worse**

Service A is calling Service B and getting 503s. Service A was configured with a naive retry policy: retry immediately, 3 times, on any 5xx error. No backoff. No jitter.

Every request that fails at Service B immediately generates 3 more requests to Service B. Service A is now sending 4× the original traffic to Service B: 10,000 original × 4 = 40,000 requests per second.

Service B, already at capacity, now receives four times the load. Its queue does not just overflow — it fills so fast that even requests that WOULD have been processed in time are delayed. The average wait time in B's queue jumps from seconds to minutes.

---

**T = 8 seconds: Service B Crashes**

Service B allocated more and more memory to hold the expanding queue. The operating system's virtual memory fills. The JVM (or Python process, or Node.js process) is killed by the OS. Service B is down.

---

**T = 9 seconds: Service A Spirals**

Service A now cannot reach Service B at all. Connections to Service B time out. Service A's threads are stuck waiting for Service B responses. Service A's thread pool fills with threads in a "waiting for B to respond" state. New requests arrive but there are no available threads to handle them. Service A crashes.

---

**T = 10 seconds: Total Outage**

User requests reach Service A and receive connection refused errors (the server is down). Complete outage.

---

**T = 65 seconds: Root Cause Resolves**

Service C's GC pause ended at T=2. By T=65, it has worked through its backlog of queued queries. Service C is healthy. But Service A and Service B are crashed. Service C being healthy is irrelevant. The cascade has completed.

```
TIMELINE VISUALIZATION:

Service C:  ══════╔══════════╗══════════════════════════════════════════
                  │GC pause  │→ high latency → backlog clear → healthy
                  T=0        T=2                               T=65s
                                    │
                                    ▼ slowness propagates

Service B:  ════════════════════╔═══════════╗══════════════╦══╗ CRASH
                                │queue fills│503 errors     │    │
                                T=3         T=5             T=6  T=8s

                                               │ retries × 4 amplify load
                                               ▼

Service A:  ═══════════════════════════════════════════════════╦══╗ CRASH
                                                               T=9 T=10s

USER:       ════════════════════════════════════════════════════════ ERROR
                                                                   T=10s+
```

**What would have prevented this?**

1. **Circuit breaker in Service A (on calls to B):** after B started returning 503s, A's circuit breaker should have opened. A would stop calling B entirely and return a fallback response to users. This stops the retry storm.

2. **No immediate retries:** if A's retry policy included backoff and a maximum retry budget, it would not have quadrupled the load on B. The right policy: retry once after 1 second. Not three times immediately.

3. **Queue depth limit in B:** if B's queue was limited to 500 items and new requests were rejected immediately when the queue was full, B would have stayed responsive (rejecting with 503) instead of accumulating a memory-killing queue and crashing.

4. **Circuit breaker in B (on calls to C):** after C slowed down, B's circuit breaker on C should have opened. B would return cached data or a fallback response rather than waiting 500ms per query and exhausting all its threads.

All of these tools were covered in Parts A and B of this chapter. The cascade happened because none of them were in place.

---

## Real Incident 1: The Retry Storm That Charged Customers Twice

This is a composite based on real incidents reported by multiple e-commerce companies. The details are representative of a common class of production failure.

---

**Background:**

A mid-sized e-commerce platform processes payments through an internal Payment Processing Service (PPS). The checkout flow calls PPS once per order. Normal payment latency: 200ms. Normal daily volume: 100,000 orders.

The day: Cyber Monday. Traffic is 5× normal.

---

**9:15am — The Trigger**

PPS latency begins climbing. The cause: the database backing PPS is experiencing high lock contention as thousands of concurrent transactions try to update account balances simultaneously. Latency climbs from the normal 200ms to 800ms.

---

**9:16am — Timeouts Begin**

The checkout service has a 500ms timeout for payment calls (configured 18 months ago when PPS latency was reliably under 200ms). With PPS now averaging 800ms, nearly every payment call times out.

The checkout service's retry configuration: 3 immediate retries on any timeout, no backoff, no delay.

For each order:
- Checkout calls PPS → timeout at 500ms
- Checkout retries → timeout at 500ms
- Checkout retries → timeout at 500ms
- Checkout retries → timeout at 500ms
- Checkout gives up → order fails

PPS is receiving 4× the original volume of payment requests. PPS latency climbs to 2,000ms.

---

**9:17am — Requests Are Going Through, Just Slowly**

Here is the dangerous part that nobody on the checkout team realized: the 800ms latency does not mean PPS is failing. It means PPS is slow. Many payment requests ARE going through — they are committing to the database, charging the customer's card — but they take 800ms to respond, which is past checkout's 500ms timeout.

So the sequence is:
1. Checkout calls PPS at T=0ms
2. PPS begins processing payment at T=1ms
3. PPS commits the charge to the database at T=400ms (payment is real, money moved)
4. PPS sends response at T=800ms
5. Checkout times out at T=500ms, declares failure
6. Checkout retries — PPS processes the retry as a brand new payment
7. Customer is charged twice

**There are no idempotency keys.** Each call to PPS, including retries, is treated as a new, independent payment request. PPS has no way to know that "this is a retry of an order it already processed."

---

**9:18am — The Retry Storm Compounds**

PPS is now receiving 4× traffic. Most of this traffic is retries of payments that may or may not have already gone through. PPS's database is now severely overloaded. Lock contention is extreme. Latency reaches 5,000ms.

Every retry also times out. Retries of retries generate more retries. The feedback loop is complete.

---

**9:20am — First Detection**

An engineer monitoring the support queue notices an unusual volume of customer complaints: "I was charged twice." She checks the payments database. She sees double entries for thousands of orders.

She calls the on-call engineering lead.

---

**9:22am — The Hard Decision**

Engineering and finance get on a call. Options:

- Option 1: Do nothing, let orders complete. Risk: more double charges.
- Option 2: Disable retries on payment. Risk: some legitimate failures do not get retried, some orders fail.
- Option 3: Shut down checkout entirely. Risk: zero revenue during Cyber Monday.
- Option 4: Accept only cash-equivalent payments (gift cards). Too complex to implement quickly.

Decision: shut down checkout. Zero revenue is better than double charges — double charges create regulatory liability, chargeback costs, and severe customer trust damage.

9:22am: checkout is disabled. A maintenance page is shown to users attempting to check out.

---

**9:35am — Fix Deployed**

A quick fix: retries disabled entirely on payment calls. Every payment attempt is one try. If it fails, the order fails cleanly and the customer is told to try again.

This is not ideal (some legitimate transient failures will not be retried) but it stops the double-charge hemorrhage.

---

**9:40am — Checkout Re-Enabled**

PPS has been receiving no new traffic for 18 minutes. Its queue is drained. Latency returns to 200ms. Checkout is re-enabled.

---

**Damage Assessment:**

- Duration of double-charge incident: approximately 18 minutes
- Orders affected: 1,247
- Each had a duplicate charge that needed to be refunded
- Average order value: $87
- Total refunds issued: approximately $108,000
- Refund processing time: 3 days (bank processing times)
- Customer service contacts: 2,300 (many customers contacted support before their refund arrived)
- Regulatory: filing required under payment card industry rules for the duplicate charge event
- Cyber Monday revenue lost during shutdown: approximately $85,000 (22 minutes × estimated order rate)
- Total estimated cost of the incident: over $250,000 including engineering time, customer service, and relationship damage

---

**Root Causes Identified:**

1. **No idempotency keys on payment calls.** Each retry was treated as a new payment. The database had no way to detect "this charge already happened."

2. **Immediate retries with no backoff.** Three retries fired at T=500ms, T=1000ms, T=1500ms. All hit PPS simultaneously, amplifying its load rather than giving it time to recover.

3. **Retry on timeout (wrong behavior for payments).** A timeout on a payment call does NOT mean the payment failed. It means the response was slow. Retrying a slow payment call risks charging twice.

4. **No circuit breaker on PPS.** Checkout kept hammering PPS with 4× traffic even as PPS was clearly struggling. A circuit breaker would have opened and stopped the retry storm.

5. **Timeout configuration stale.** The 500ms timeout was set when PPS latency was 200ms. It was never updated as the system grew. It should have been 1,500ms or 2,000ms with current load patterns.

---

**What Was Fixed:**

```python
# BEFORE (broken):
def charge_customer(order_id, amount, card_token):
    for attempt in range(4):  # 1 original + 3 retries
        try:
            response = pps_client.charge(amount, card_token, timeout=0.5)
            return response
        except TimeoutError:
            continue  # Retry immediately
    raise PaymentFailed("All attempts timed out")


# AFTER (production-grade):
import uuid

def charge_customer(order_id, amount, card_token):
    # Generate idempotency key from the order — same order always = same key
    # This key is the same across retries. PPS deduplicates on it.
    idempotency_key = f"charge-{order_id}"

    for attempt in range(3):  # Max 3 attempts total
        try:
            response = pps_client.charge(
                amount=amount,
                card_token=card_token,
                idempotency_key=idempotency_key,  # Key added
                timeout=2.0  # Timeout updated to match real PPS latency
            )
            return response

        except TimeoutError:
            # Timeout ≠ failure. PPS may have processed this.
            # Retry with SAME idempotency key — PPS will deduplicate.
            if attempt < 2:
                # Exponential backoff: wait 1s, then 2s, then give up
                wait = 2 ** attempt  # 1s, 2s
                time.sleep(wait)
            else:
                raise PaymentUnknown(
                    "Payment status unknown after timeout. "
                    "Do NOT retry without checking payment status first."
                )

        except PermanentFailure as e:
            # 4xx errors — do NOT retry. Card declined, invalid details, etc.
            raise PaymentFailed(str(e))

    # This line should not be reached, but just in case:
    raise PaymentFailed("All attempts exhausted")
```

PPS was updated to deduplicate requests by idempotency key:

```python
# Inside Payment Processing Service:
def charge(amount, card_token, idempotency_key, **kwargs):
    # Check if we have already processed this key
    existing = idempotency_store.get(idempotency_key)
    if existing:
        # We processed this before — return the cached result
        # No second charge happens. The stored result is returned.
        log.info(f"Idempotency hit for key {idempotency_key} — returning cached result")
        return existing.result

    # First time we have seen this key — process it
    result = process_charge(amount, card_token)

    # Store the result so future retries get this cached response
    idempotency_store.set(
        key=idempotency_key,
        value=result,
        ttl=86400  # Keep for 24 hours
    )
    return result
```

The circuit breaker was added:

```python
# Checkout service now wraps PPS calls with a circuit breaker
pps_breaker = CircuitBreaker(
    name="payment-processing-service",
    failure_threshold=10,       # Open if 10 failures in a window
    failure_window=10,          # 10-second window
    open_duration=60,           # Stay open 60 seconds before trying again
    # Fallback: show "Payment temporarily unavailable, try again in 1 minute"
    fallback=lambda: PaymentTemporarilyUnavailable()
)

def charge_customer(order_id, amount, card_token):
    idempotency_key = f"charge-{order_id}"
    return pps_breaker.call(pps_client.charge,
                             amount=amount,
                             card_token=card_token,
                             idempotency_key=idempotency_key,
                             timeout=2.0)
```

After these fixes: a subsequent load test simulated PPS slowness at 5× Cyber Monday traffic. The circuit breaker opened after 10 failures. Checkout returned a friendly "payment service temporarily slow" message. PPS received no retry amplification. When PPS recovered, the circuit breaker tested with one request, saw success, closed, and full traffic resumed. Total simulated downtime: 60 seconds. Zero duplicate charges.

---

## Real Incident 2: The Thundering Herd After a Cache Flush

### The Setup

A media company runs one of the most popular news sites in the country. At peak, they handle 50,000 requests per second. Their architecture looks like this:

```
Users → Load Balancer → Web Servers (×200) → Redis Cache → Database
                                               (hit rate: 99%)
```

The Redis cache holds every article. When an article is requested:
- If it is in Redis: return immediately (~2ms). This happens 99% of the time.
- If it is NOT in Redis: fetch from database (~20ms), store in Redis, return.

The database can comfortably handle 2,000 queries per second. Thanks to the 99% cache hit rate, it only receives about 500 queries per second (1% of 50,000).

---

**The Trigger: Scheduled Redis Maintenance**

The infrastructure team scheduled a Redis cluster upgrade for 2am on a Tuesday — historically the quietest time. Traffic at 2am: about 12,000 requests per second. They expected a brief 30-second outage while Redis restarted.

What they did not account for: when Redis restarts, it starts completely empty. All cached articles are gone.

---

**T = 0 seconds: Redis Starts Restarting**

Redis goes offline. The restart process begins.

---

**T = 1 second: All Requests Miss Cache**

Every incoming request checks Redis. Redis is down. The web servers treat a Redis failure as a cache miss (they were configured to fail open — when cache is unavailable, go to database). All 12,000 requests per second now query the database directly.

The database receives 12,000 queries/second. Its maximum is 2,000. It is instantly at 600% capacity.

---

**T = 3 seconds: Database Overwhelmed**

Database latency spikes from 20ms to 8,000ms. It is not dead — it is just buried under six times its designed load. Connections are queuing. Lock waits are growing.

---

**T = 4 seconds: Web Servers Begin Timing Out**

Web servers have a 5-second timeout for database queries. Queries are taking 8 seconds. Timeouts fire. Web servers log errors and return 500 to users.

Users see errors. Most immediately click refresh (this is news — users want to read their article).

---

**T = 5 seconds: Retry Storm**

12,000 original requests per second, most of which timed out, are now retrying. Plus new incoming traffic. Database receives approximately 25,000 queries per second.

---

**T = 7 seconds: Database Crashes**

The database cannot hold 25,000 connections. Its connection limit is 5,000. It begins rejecting connections. Web servers can no longer connect at all. Every request returns a 500 error.

---

**T = 30 seconds: Redis Is Back Up**

Redis finishes restarting. It is empty but healthy. But the database is crashed. There is nothing to populate Redis from.

---

**T = 45 seconds: Database Is Restarted**

Database restarts. It accepts connections. But it still has 25,000 web server connections trying to reconnect simultaneously. It is immediately overwhelmed again. It crashes again.

---

**T = 6 minutes: Traffic Throttling Applied**

Engineers wake up (pages fired at T=4 seconds but on-call took time to get online and assess). They implement an emergency rate limit: web servers will make at most 2,000 database queries per second total across the fleet. Additional requests return a cached "service degraded" page.

---

**T = 8 minutes: Database Stabilizes**

With traffic throttled to 2,000 queries/second, the database stabilizes. Redis begins being populated as articles are fetched. Cache hit rate slowly climbs: 20%... 40%... 60%...

---

**T = 25 minutes: Normal Operation Resumes**

Redis is 90% populated for popular articles. Database load drops to normal. Traffic throttle is removed.

**Total outage duration: 25 minutes.**
**Root cause that triggered the cascade: a planned 30-second Redis maintenance window.**

---

### The Four Solutions

**Solution 1: Cache Warming Before Restart**

Before restarting Redis, pre-load the new instance with the most popular articles. A separate process reads the top 10,000 articles from the database and writes them to the new Redis instance before the old one is shut down.

```python
def safe_redis_restart(old_redis, new_redis):
    """
    Migrate popular content to new Redis before switching traffic.
    """
    print("Starting cache warm-up...")

    # Get the top 10,000 most-viewed articles from analytics
    popular_article_ids = analytics.get_top_articles(limit=10_000)

    # Load each into the new Redis instance
    for article_id in popular_article_ids:
        # Read from database
        article = database.get_article(article_id)
        # Write to new Redis (not the old one)
        new_redis.set(f"article:{article_id}", article, ex=300)

    print(f"Cache warm-up complete. {len(popular_article_ids)} articles pre-loaded.")

    # NOW switch traffic to new Redis
    traffic_router.switch_redis(old_redis, new_redis)

    # NOW shut down old Redis
    old_redis.shutdown()
    print("Migration complete. Zero cache-cold requests.")
```

With a warm cache, the transition is invisible. Redis restarts in the background. The new Redis already has popular content. The database sees no unusual load.

**Solution 2: Staggered TTL (Jitter)**

Every cached article has a Time-To-Live — a timer after which Redis automatically deletes it. If all articles are cached with a TTL of exactly 5 minutes, they all expire at the same moment. Every 5 minutes there is a wave of cache misses hitting the database simultaneously. This is called a "thundering herd."

Fix: add random jitter to the TTL. Instead of exactly 300 seconds, use 300 ± 30 seconds (randomly chosen per item). Articles expire at different times instead of all at once.

```python
import random

def cache_article(article_id, article_data):
    # Without jitter: all articles expire at the same time
    # redis.set(f"article:{article_id}", article_data, ex=300)

    # With jitter: articles expire within a 1-minute window, not at a single instant
    jitter = random.randint(-30, 30)   # Between -30 and +30 seconds
    ttl = 300 + jitter                  # Between 270 and 330 seconds

    redis.set(f"article:{article_id}", article_data, ex=ttl)
```

With jitter, the expiration wave is spread across a 60-second window instead of a single instant. The database sees a manageable drizzle instead of a flood.

**Solution 3: Dog-Pile Prevention (The Cache Fill Lock)**

The thundering herd also occurs at the individual article level. If an article expires from cache, and 500 web servers all notice the miss simultaneously, all 500 call the database at the same time. One database query would suffice. 500 is waste.

Solution: when an article is not in cache, only ONE server fetches it. The others wait briefly and then get the cached result.

```python
import time

def get_article(article_id):
    """
    Get an article. Only one server fetches from DB if cache misses.
    Others wait for the first server to populate the cache.
    """

    cache_key = f"article:{article_id}"
    lock_key = f"fetching:{article_id}"

    # Check cache first (the happy path — 99% of requests end here)
    cached = redis.get(cache_key)
    if cached:
        return cached   # Cache hit — done in ~2ms

    # Cache miss. Try to claim the right to fetch from DB.
    # nx=True means "only set this key if it does NOT already exist"
    # ex=5 means "this lock expires in 5 seconds even if we crash"
    claimed_lock = redis.set(lock_key, "1", nx=True, ex=5)

    if claimed_lock:
        # I won the race — I will fetch from the database
        try:
            article = database.get_article(article_id)

            # Store in cache for the next 5 minutes (with jitter)
            jitter = random.randint(-30, 30)
            redis.set(cache_key, article, ex=300 + jitter)

            return article
        finally:
            # Always release the lock, even if something went wrong
            redis.delete(lock_key)

    else:
        # Another server is already fetching this article.
        # Wait a moment and check the cache — it should be populated soon.
        time.sleep(0.1)  # 100ms — the other server should finish in this time
        result = redis.get(cache_key)

        if result:
            return result   # Got it from cache after the wait

        # Still not there — fetch from DB directly (fallback)
        # This handles the edge case where the other server crashed mid-fetch
        return database.get_article(article_id)
```

With this lock: 500 servers simultaneously notice a cache miss. One wins the lock. The other 499 wait 100ms. The winner fetches from DB, stores in cache. The 499 waiters find the article in cache. Total DB queries: 1. Not 500.

**Solution 4: Circuit Breaker on the Database**

When the database is overwhelmed, stop querying it. Return the last known cached value — even if it is technically "expired" — rather than hammering a struggling database.

```python
db_circuit_breaker = CircuitBreaker(
    name="database",
    failure_threshold=50,   # 50 failures in 10 seconds → open
    failure_window=10,
    open_duration=30,       # Try again after 30 seconds
)

def get_article_with_fallback(article_id):
    cache_key = f"article:{article_id}"

    # Try cache first
    cached = redis.get(cache_key)
    if cached:
        return cached

    # Try database (through circuit breaker)
    try:
        article = db_circuit_breaker.call(database.get_article, article_id)
        redis.set(cache_key, article, ex=300)
        return article
    except CircuitOpenError:
        # DB circuit is open — it is struggling. Do NOT add more load.
        # Return stale cached data if we have any (even if technically expired)
        stale = redis.get(cache_key, ignore_ttl=True)  # Hypothetical flag
        if stale:
            return stale  # Stale is better than an error

        # No stale data either — return a generic error or placeholder
        return ArticleUnavailable("Article temporarily unavailable")
```

A stale article (e.g., 7 minutes old when the TTL was 5 minutes) is almost always acceptable for a news site. A 500 error is not.

---

## Real Incident 3: The Partial Deployment Cascade

### Background

A financial technology company processes payments through a validation service. They deploy using "canary releases" — instead of deploying new code to all servers at once (risky), they deploy to a small fraction first, watch for errors, and expand gradually.

Deployment plan:
- Deploy to 5% of servers → watch for 10 minutes
- If healthy: 25% → watch for 10 minutes
- If healthy: 50% → watch for 10 minutes
- If healthy: 100% → done

This is a best practice. In this case, it was almost enough — but not quite.

---

**The Bug**

The new version of the payment validation service contained a bug: when it received a payment request with a new optional field called `loyalty_points_applied`, it threw an unhandled exception and returned a 500 error. The old version simply ignored fields it did not know about.

The `loyalty_points_applied` field was added three weeks ago by the mobile app team to support a new rewards feature. They had told the payments team, but the payments team's test suite had not been updated to include requests containing this field.

---

**T = 2:00pm: Deployment Begins**

5% of payment validation servers are upgraded to the new version.

Traffic to new version: 5% of all payments.
Mobile app users: approximately 30% of all payment traffic.
Payments from mobile that hit the new version: 5% × 30% = 1.5% of all payments.
Each of these fails with 500.

Overall error rate = 1.5%.

The alert threshold: overall payment error rate > 5%. No alert fires.

---

**T = 2:10pm: Rollout Continues**

No errors detected. Rollout expands to 25% of servers.

Traffic to new version: 25% of all payments.
Mobile payments hitting new version: 25% × 30% = 7.5% of all payments.
Each of these fails.

Overall error rate = 7.5%.

Alert threshold: 5%. Alert FIRES. Pager goes off.

But it has been 10 minutes since the failures started.

---

**T = 2:11pm: Engineer Wakes Up and Starts Investigating**

The alert says "payment error rate elevated." The on-call engineer starts looking at dashboards. She notices the error rate jumped exactly when the deployment expanded to 25%.

---

**T = 2:15pm: Root Cause Identified**

She sees 500 errors only on the new version. She looks at error logs: `Unhandled field: loyalty_points_applied`. She finds the field was added by the mobile app team. She cross-references: mobile app traffic is the only traffic with this field.

---

**T = 2:18pm: Rollback**

Rollback command issued. All servers revert to the old version. Takes 3 minutes.

---

**T = 2:21pm: Rollback Complete**

Payment error rate drops to normal.

---

**Damage Assessment:**

- Duration of elevated errors: 21 minutes
- Percentage of time alert was silent: 10 of those 21 minutes (47%)
- Failed payments during elevated error period: ~8,400 payments
- Of those: some users retried successfully later, some did not
- Estimated failed transactions not recovered: ~1,200
- Revenue impact: approximately $104,000 (average transaction $87)
- Customer trust impact: unknown but significant (payment failures are highly visible to users)

---

**What Was Learned:**

**Lesson 1: Monitor version-level error rates during canary deployments, not just overall error rates.**

An overall error rate of 1.5% looks healthy. A per-version error rate of 30% on the new version is a screaming emergency. The monitoring system should have been configured to alert on NEW VERSION error rate independently.

```python
# Alert configuration that would have caught this:

alert("payment.validation.new_version.error_rate") {
    condition: rate("payment.errors", version="canary") > 0.05  # 5%
    window: "2 minutes"
    severity: "critical"
    message: "Canary deployment has elevated error rate — investigate before expanding"
}

# This would have fired at T=2:02pm, within 2 minutes of deployment start.
# Rollback would have happened at T=2:05pm.
# Affected payments: approximately 400, not 8,400.
```

**Lesson 2: Communicate new fields to all consumers before the mobile app ships.**

The mobile app team added `loyalty_points_applied` three weeks earlier. They told the payments team in a Slack message. The payments team acknowledged but did not update their test fixtures. The new code was not tested with the new field.

Fix: API changes require a formal compatibility review. Any new field in a request must be tested with all validation services before the mobile app ships the field.

**Lesson 3: New code should be safe to deploy even with unknown fields.**

The new validation service threw an exception on an unknown field. The old one silently ignored it. Defensive programming: treat unknown fields as something to log and ignore, not crash on.

```python
# Fragile (what they had):
def validate_payment(request):
    amount = request["amount"]
    card_token = request["card_token"]
    loyalty_points = request["loyalty_points_applied"]  # KeyError if missing
    # ...

# Defensive (what they should have had):
def validate_payment(request):
    amount = request["amount"]
    card_token = request["card_token"]
    loyalty_points = request.get("loyalty_points_applied", 0)  # Default if missing

    # Log any unrecognized fields — don't crash on them
    known_fields = {"amount", "card_token", "loyalty_points_applied", "currency"}
    unknown_fields = set(request.keys()) - known_fields
    if unknown_fields:
        log.warning(f"Unknown fields in payment request: {unknown_fields}. Ignoring.")
    # ...
```

**Lesson 4: Test contracts between services, not just services in isolation.**

Unit tests for the payment validator were 100% passing. None of them included `loyalty_points_applied` because the test was written before the field existed. Contract testing — where Service A's test suite includes real examples of payloads from Service B — would have caught this.

---

# Part 6: Design Evolution — How Systems Mature

---

## The Three Stages of System Resilience

Every system starts fragile and (ideally) grows more resilient over time. There are three recognizable stages. Most real systems live somewhere between stages, with pockets of strength and pockets of fragility.

---

### Stage 1: Happy Path Engineering

This is where every system starts. The code works when everything goes right. When things go wrong, users see errors. The engineers deal with it manually.

It is not a failure to be at Stage 1. For a new product with five users, building elaborate resilience infrastructure is a waste of time. Move fast. Get customers. Then strengthen the foundation.

**What it looks like:**

```python
# Stage 1: No timeouts, no retries, no circuit breakers
def process_order(order):
    payment_result = payment_api.charge(order.amount)  # No timeout
    inventory_result = inventory.decrement(order.item)  # No timeout
    email_result = email.send_confirmation(order.user)  # No timeout
    return "Order complete"

# If payment_api hangs: process_order hangs forever
# If inventory crashes: process_order returns 500
# If email crashes: order shows failed even though payment went through
# If payment goes through but email takes 5 seconds: user waits 5 seconds
```

**Signs you are at Stage 1:**
- Retries are in the "TODO" list
- One slow dependency brings down the whole server
- Double-charging is possible (no idempotency)
- Outages require manual intervention and full attention of the on-call engineer
- There is no runbook ("what do you do when X breaks?")

**The existential risk of Stage 1:** as traffic grows, the probability of a dependency failure in any given hour increases. A system that is fine at 1,000 requests per day may have daily outages at 1,000,000 requests per day — simply because more traffic means more chances for a downstream service to have a bad moment.

---

### Stage 2: Resilience Theater

Stage 2 is tricky, because it looks like Stage 3 from the outside. Someone has added retries. They have added timeouts. There might even be a circuit breaker. But the implementation has gaps that make the resilience surface-level — it is theater.

**What it looks like:**

```python
# Stage 2: Retries added, but with critical gaps

def process_order(order):
    # Retries added — but no idempotency!
    for attempt in range(3):
        try:
            payment_result = payment_api.charge(
                order.amount,
                timeout=5.0
                # No idempotency_key — retries may double-charge
            )
            break
        except TimeoutError:
            if attempt == 2:
                raise
            # Immediate retry with no backoff — amplifies load
            continue

    # Circuit breaker exists — but threshold is set to 50% error rate
    # In practice, 50% error rate means the service is basically dead already
    # Circuit never trips in practice (threshold too high)
    with circuit_breaker(threshold=0.5):
        inventory.decrement(order.item)

    # Email is synchronous — order "fails" if email is down,
    # even though payment already went through
    email.send_confirmation(order.user)
```

**Signs you are at Stage 2:**
- Retries exist but occasionally cause duplicate orders or charges
- "We added retries" but the retry logic retries on errors that should not be retried (like 400 Bad Request)
- Circuit breakers exist but never actually trip (thresholds configured too high)
- Monitoring exists but alerts fire constantly ("alert fatigue" — engineers ignore them) or never fire
- Outages happen and the root cause always turns out to be "the resilience mechanism was there but not tuned"

Stage 2 is the most dangerous stage. It gives a false sense of security. The system LOOKS resilient. Documentation says "we have circuit breakers and retries." But in production, those mechanisms do not work as intended. Engineers trust them. The trust is unearned.

---

### Stage 3: Production-Grade Resilience

Stage 3 systems do not just have resilience mechanisms — they have tuned, tested, end-to-end resilience. Every piece works together. Failures are expected, detected quickly, and handled automatically.

**What it looks like:**

```python
# Stage 3: Everything working together

import uuid

def process_order(order):
    # Unique key for this order — same key used on retries
    idempotency_key = f"order-{order.id}-{order.user_id}"

    # Payment: exponential backoff, idempotency, circuit breaker, correct retry policy
    try:
        payment_result = payment_circuit_breaker.call(
            payment_api.charge,
            amount=order.amount,
            idempotency_key=idempotency_key,
            timeout=2.0
        )
    except CircuitOpenError:
        # Payment service is struggling — tell user to try again in 1 minute
        return PaymentUnavailable("Please try again in a minute")
    except PermanentFailure:
        # Card declined, etc — do NOT retry
        return PaymentFailed("Payment declined")

    # Inventory: optimistic locking to handle race conditions
    try:
        inventory_result = inventory.decrement(
            item_id=order.item_id,
            expected_count=order.expected_stock  # Fails if stock changed
        )
    except StockChanged:
        # Refund the payment (idempotency means this is safe)
        payment_api.refund(idempotency_key)
        return OutOfStock("Item sold out — payment refunded")

    # Email: asynchronous, decoupled from the order completion
    # If email fails, it retries in the background. Order is NOT failed.
    email_queue.enqueue(
        task="send_order_confirmation",
        user=order.user,
        order_id=order.id,
        retry_policy=ExponentialBackoff(max_attempts=5)
    )

    # Order is complete — email will arrive eventually
    return OrderComplete(order.id)
```

**Signs you are at Stage 3:**
- Double-charges are impossible (idempotency is comprehensive, tested)
- Partial outages degrade gracefully (one component fails, the rest continue)
- On-call engineers know exactly what to do (runbooks are written, tested, and current)
- Alerts fire when they should and not when they should not (tuned thresholds)
- Post-mortems result in actual fixes that prevent recurrence (not just "we'll be more careful")
- New engineers can understand the resilience architecture from documentation
- Chaos engineering is practiced (intentional failures in production reveal weak spots)

The progression from Stage 1 to Stage 3 is not a single project. It is continuous improvement over years. Large companies with decades-old systems still have Stage 1 pockets in obscure corners. The goal is to shrink those pockets over time, and to ensure the most critical paths — the ones that touch money, user data, and user-facing experience — are firmly at Stage 3.

---

## Concrete Evolution: Order Service, Version 1.0 to Version 3.0

Let us trace a specific order processing service through three versions, showing exactly what was added and why.

---

### Version 1.0 — Launch Day

**Architecture:**
```
User
  │
  ▼
Order Service
  ├──► Payment API  (external, third-party)
  ├──► Inventory DB (internal database)
  └──► Email Service (internal microservice)
```

**Code:**
```python
# Version 1.0 — works when everything is healthy

def place_order(user_id, item_id, card_token):
    # Charge the card
    payment = payment_api.charge(card_token, price_lookup(item_id))
    # Decrement stock
    inventory_db.update(f"UPDATE items SET stock = stock - 1 WHERE id = {item_id}")
    # Send email
    email_service.send(user_id, "Your order is confirmed!")
    return {"status": "success", "payment_id": payment.id}
```

**What breaks under which conditions:**

| Scenario | What Happens | Impact |
|---|---|---|
| Payment API takes 30 seconds | User's browser hangs 30 seconds then shows error | Very bad UX |
| Payment API hangs forever | Server thread blocked forever. Eventually server runs out of threads | Outage |
| Payment goes through but inventory update fails | User charged, item stock not decremented. Overselling | Data inconsistency |
| Payment goes through but email crashes | User charged, order processed, user never gets confirmation email. They email support | Poor UX, support cost |
| User clicks "Buy" twice very fast | Two orders placed, user charged twice | Critical bug |

---

### Version 2.0 — After the First Major Outage

The outage: payment API hung for 10 minutes. All order service threads blocked. New orders could not be placed. Urgent Slack messages, an engineer woke up at 3am, manually killed the hung threads.

**What was added:**
- 5-second timeouts on all external calls
- Retries: 3 attempts, no backoff, on any failure

**Code:**
```python
# Version 2.0 — timeouts and retries added (but gaps remain)

def place_order(user_id, item_id, card_token):
    # ADDED: retries and timeout
    # MISSING: idempotency key — retries may double-charge
    for attempt in range(3):
        try:
            payment = payment_api.charge(
                card_token,
                price_lookup(item_id),
                timeout=5.0  # No longer hangs forever
            )
            break
        except (TimeoutError, ServerError):
            if attempt == 2:
                return {"status": "error", "message": "Payment failed"}
            # Immediate retry — no backoff

    inventory_db.update(
        f"UPDATE items SET stock = stock - 1 WHERE id = {item_id}",
        timeout=5.0  # ADDED: timeout
    )

    for attempt in range(3):
        try:
            email_service.send(user_id, "Your order is confirmed!", timeout=5.0)
            break
        except (TimeoutError, ServerError):
            if attempt == 2:
                pass  # IMPROVEMENT: email failure no longer fails the order
                      # But this means the user gets no confirmation ever

    return {"status": "success", "payment_id": payment.id}
```

**What improved:**
- Hanging orders are gone (timeout at 5 seconds)
- The server no longer runs out of threads during payment API slowness
- Email failure no longer fails the order (user is charged correctly)

**What is still broken:**

Scenario: user clicks "Buy." Payment API takes 6 seconds. Server times out at 5 seconds. Server retries. During the retry window, the original payment from the first attempt has actually gone through (it just responded slowly). The retry also goes through. User is charged twice.

This is the same bug that caused the Cyber Monday incident above. Timeouts were added but idempotency was not. The classic Stage 2 trap.

Also: email failures are silently ignored. The code has `pass` on email failure. The user never gets a confirmation. They think their order failed. They call support. "Did my order go through?" Support looks it up. Yes it did. User is relieved but frustrated.

---

### Version 3.0 — Production-Grade

**Architecture:**
```
User
  │
  ▼
Order Service
  │  (generates idempotency key for this order)
  │
  ├──► Payment API
  │    - idempotency key passed
  │    - exponential backoff retry (backoff: 1s, 2s)
  │    - circuit breaker (opens at 10% error rate in 30s window)
  │    - timeout: 3 seconds per attempt
  │
  ├──► Inventory DB
  │    - optimistic locking (prevents overselling under race conditions)
  │    - timeout: 2 seconds
  │    - no retries (write operations must be carefully idempotent first)
  │
  ├──► Email Queue (async)
  │    - fire-and-forget: order service does not wait for email
  │    - email worker retries up to 5 times with exponential backoff
  │    - if all retries fail: alerts on-call, email is manually resent
  │
  └──► Monitoring
       - payment latency (p50, p95, p99)
       - payment error rate (by error type)
       - retry rate (what % of orders required a retry?)
       - circuit breaker state (open/closed)
       - inventory conflict rate (how often does optimistic locking conflict?)
       - email delivery rate (what % of confirmation emails delivered?)
```

**Walk-through of the happy path:**

```
T=0ms    User clicks "Buy"
T=1ms    Order Service receives request
T=2ms    Generates idempotency key: "order-usr123-itm456-sess789"
         (session token ensures different browsing sessions create different keys,
          so if user genuinely re-orders after a session ends, it processes correctly)
T=3ms    Checks circuit breaker state for Payment API: CLOSED (healthy)
T=4ms    Calls Payment API with idempotency key and 3-second timeout
T=187ms  Payment API responds: success. Charge ID: "ch_abc123"
T=188ms  Records payment result in order database
T=190ms  Calls Inventory DB with optimistic lock:
         "Decrement stock for item 456, current stock must be 14"
T=195ms  Inventory responds: stock decremented to 13. Success.
T=196ms  Enqueues email task: "send confirmation to user 123 for order xyz"
         (Does NOT wait for email — returns immediately)
T=197ms  Returns to user: {"status": "success", "order_id": "ord789"}
T=1,200ms Email worker picks up the task, sends email
T=1,400ms User receives confirmation email in inbox
```

Total user wait: 197ms. Clean. Fast.

**Walk-through of the retry path (payment slow):**

```
T=0ms    User clicks "Buy"
T=2ms    Generates idempotency key: "order-usr123-itm456-sess789"
T=4ms    Calls Payment API — timeout at 3,000ms

T=3,004ms Payment API timed out (but actually processed the charge at T=2,800ms
           — slow response due to load, but charge committed)

T=3,005ms Order Service's retry logic kicks in
           Calculates backoff: 1 second delay before retry
           
T=4,005ms Calls Payment API again — SAME idempotency key: "order-usr123-itm456-sess789"
           Payment API checks its idempotency store:
           "Have I seen key order-usr123-itm456-sess789 before? YES — at T=2,800ms"
           "Returning cached result: charge ID ch_abc123"
           Does NOT charge the card again.

T=4,092ms Payment API returns cached result: charge ID ch_abc123
T=4,093ms Order Service proceeds: inventory, email queue, return success

User is charged EXACTLY ONCE. The duplicate was caught by the idempotency key.
```

**Walk-through of the circuit breaker path (payment API struggling):**

```
T=0ms    Normal operation. Circuit breaker: CLOSED.

T=5min   Payment API starts struggling. Error rate climbs to 15%.
T=5min+30s  Circuit breaker threshold reached: 10% error rate in 30 seconds.
            Circuit breaker opens.

T=5min+31s  New order comes in.
            Order Service checks circuit breaker: OPEN.
            Does NOT call Payment API (would fail anyway and amplify its load).
            Immediately returns fallback response:
            {"status": "payment_unavailable",
             "message": "Payment service temporarily unavailable. Please try again in 60 seconds.",
             "retry_after": 60}

T=6min+30s  Circuit breaker enters HALF-OPEN state. Allows one test request.
T=6min+31s  Test request to Payment API: succeeds in 210ms.
            Circuit breaker closes. Normal operation resumes.
            Queue of pending orders begins processing.
```

The user experience during the 90-second circuit-open window: they see a clear message with a specific retry time. They wait. They retry. It works. They are slightly annoyed but not confused.

Compare to Version 1.0: user sees a 30-second spinning wait, then a cryptic error, with no guidance on when to try again.

---

## Observability — How Do You Know If It's Working?

### The Vital Signs Monitor

A hospital patient is connected to a monitoring system: heart rate, blood pressure, oxygen saturation, respiratory rate, temperature. Each vital sign has a normal range. Alarms fire when any vital leaves its normal range. The nurse can glance at the dashboard and know in seconds whether the patient is stable or in trouble.

Your system needs the same: vital signs (metrics) with normal ranges and alarms. Without them, you only learn about problems when users call you (too late) or when the system crashes (much too late).

Here are the core metrics for a resilient system. For each one: what it measures, what is normal, when to alert, and what the alert means.

---

### Metric 1: Error Rate (Per Service, Per Endpoint)

**What it measures:** the percentage of requests that return a 5xx error (server-side failure, as opposed to 4xx which are client mistakes).

**Normal value:** less than 0.5% for most production APIs. Some error rate is always expected — misconfigurations, rare edge cases, clients sending malformed requests.

**Alert threshold:** more than 2%. Something is wrong.
**Page threshold:** more than 10%. Something is very wrong. Wake someone up.

**What a spike tells you:** a dependency is failing, a deployment introduced a bug, or the system is under unexpected load.

**Important subtlety:** measure error rate per endpoint, not just overall. A 10% error rate on `/search` is much less critical than a 10% error rate on `/checkout`. One affects convenience; the other affects revenue.

---

### Metric 2: Retry Rate

**What it measures:** what percentage of all requests required at least one retry before succeeding.

**Normal value:** less than 5%. Some retries are expected — occasional network hiccups, brief DB query delays.

**Alert threshold:** more than 15%. Something upstream is unstable. Retries are adding load on top of normal load.

**What a spike tells you:** a dependency is degraded. The system is burning extra capacity on retries instead of original requests. This is often a leading indicator — the error rate might still be acceptable (retries are succeeding) but the retry rate shows something is wrong before errors become user-visible.

**Especially watch:** if retry rate spikes but error rate stays low, your retry logic is working but you are hiding a problem that will eventually get worse.

---

### Metric 3: Circuit Breaker State

**What it measures:** whether each circuit breaker is Closed (healthy), Half-Open (testing recovery), or Open (blocking calls to a broken dependency).

**Normal value:** all circuits Closed.

**Alert threshold:** any circuit enters Open state.

**What it tells you:** a dependency has failed enough times in a short window to trip the circuit breaker. Look at the dependency's health dashboard. The circuit breaker is protecting you, but the underlying problem needs to be fixed.

**Do not ignore this.** A circuit that is Open means a feature of your system is silently failing. Users may be getting fallback responses. Every open circuit needs a story: "why is it open, what is the fallback experience, when will it close?"

---

### Metric 4: Queue Depth

**What it measures:** the number of requests currently waiting in each queue (pending processing).

**Normal value:** depends on your system, but typically well under 20% of maximum capacity during normal operation.

**Alert threshold:** queue depth exceeds 50% of maximum. Demand is outpacing supply.
**Page threshold:** queue depth exceeds 90% of maximum. Load shedding is about to kick in or is already happening.

**What a spike tells you:** either traffic has spiked unexpectedly, or processing has slowed (a downstream dependency is slow). Check both.

**Watch the trend, not just the value.** A queue at 80% that is stable is better than a queue at 50% that is growing. A growing queue is a queue that will eventually overflow.

---

### Metric 5: P99 Latency

**What it measures:** the 99th percentile request latency. This is the response time that 99% of requests are FASTER than. Put another way: the slowest 1% of requests take at least this long.

**Why P99 instead of average?** Average latency hides the tail. Imagine 100 requests: 99 take 100ms, one takes 10,000ms. Average: 199ms — looks healthy. P99: 10,000ms — very unhealthy. That one slow request might be a paying customer.

**Normal value:** less than 200ms for most user-facing APIs.

**Alert threshold:** P99 exceeds 1,000ms (1 second). Your slowest users are having a bad experience.
**Page threshold:** P99 exceeds 5,000ms. Something is seriously wrong.

**What a P99 spike tells you:** even if most requests are fast, something is causing some requests to be very slow. Common causes: a slow database query for a specific query pattern, a dependency with occasional slow responses, garbage collection pauses.

---

### Metric 6: Idempotency Key Hit Rate

**What it measures:** what percentage of requests used a cached idempotency result (meaning the server recognized it as a duplicate and returned a stored response instead of processing again).

**Normal value:** very low, under 1%. You expect a small number of retries on your most important endpoints.

**Alert threshold:** more than 5% hit rate. Either:
(a) There is a retry storm — clients are retrying excessively.
(b) A client has a bug and is sending the same request repeatedly with the same key.
(c) Something else is causing clients to believe they need to retry when they do not.

**What a spike tells you:** investigate which endpoint is seeing the hits, and which client IDs are sending them. Is it a specific deployment of the mobile app? A buggy automated script?

---

### Metric 7: Retry Budget Consumption

**What it measures:** what percentage of your total compute is being spent on retries (as opposed to original requests).

Think of it as: you have a factory. Your factory can produce 100 cars per day. Normally, 5 of those factory hours go to rework (fixing cars that had small defects). If rework suddenly takes 40 hours out of your 100, you only produce 60 cars. Customers wait longer. The factory is running hot.

**Normal value:** retries consume less than 5% of capacity.

**Alert threshold:** retries consume more than 15% of capacity. A significant portion of your resources is being spent on work that ideally should not need to happen.

**What it tells you:** at 15%+ retry budget, even if retries are succeeding, you are heading toward a dangerous zone. If the instability causing retries worsens, your retry load and your original request load will compete. Retries will interfere with original requests. The cascade begins.

---

### The Monitoring Dashboard

Here is what a healthy system's monitoring dashboard looks like, and then what it looks like during the Cyber Monday incident we studied earlier:

```
╔══════════════════════════════════════════════════════════════════════════╗
║                   PAYMENT SYSTEM — LIVE DASHBOARD                       ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  HEALTHY (Normal Monday):                                               ║
║  ────────────────────────                                               ║
║  Request rate:         8,200 req/min    ████████░░░░░░░░  (normal)     ║
║  Error rate:           0.3%             █░░░░░░░░░░░░░░░  (great)      ║
║  Retry rate:           1.2%             █░░░░░░░░░░░░░░░  (great)      ║
║  P99 latency:          210ms            ██░░░░░░░░░░░░░░  (good)       ║
║  Queue depth:          12/300           █░░░░░░░░░░░░░░░  (low)        ║
║  Circuit breakers:     ALL CLOSED       ✓                               ║
║  Idempotency hit rate: 0.8%             ░░░░░░░░░░░░░░░░  (normal)     ║
║  Retry budget used:    3%               ░░░░░░░░░░░░░░░░  (fine)       ║
║                                                                          ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  INCIDENT (Cyber Monday 9:16am):                                        ║
║  ───────────────────────────────                                        ║
║  Request rate:         48,000 req/min   ████████████████  (5× traffic)  ║
║  Error rate:           34% !!!          █████████████░░░  ← ALERT       ║
║  Retry rate:           87% !!!          ████████████████  ← PAGE        ║
║  P99 latency:          6,800ms !!!      ████████████████  ← PAGE        ║
║  Queue depth:          298/300 !!!      ████████████████  ← PAGE        ║
║  Circuit breakers:     PPS: OPEN !!!    ← ALERT (if configured)        ║
║  Idempotency hit rate: 0% (none!)       ← The problem: no idempotency  ║
║  Retry budget used:    76% !!!          ████████████░░░░  ← ALERT       ║
║                                                                          ║
║  ⚠ Idempotency hit rate = 0% during high retry rate means              ║
║    duplicate requests are NOT being deduplicated. Duplicate charges     ║
║    are likely.                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
```

Notice: if the monitoring dashboard had been fully configured before the incident, an engineer would have had ALL of this information at a glance the moment the incident started. The idempotency hit rate of 0% combined with a retry rate of 87% is a very specific signal: clients are retrying heavily, but idempotency is not deduplicating anything. The risk of double-processing is immediate and obvious.

With good observability, the time from "incident starts" to "engineer understands what is happening" drops from 15 minutes to 2 minutes. That is 13 minutes less damage.

---

## The Resilience Checklist — Before You Ship

Think of this as a pre-flight checklist. Pilots go through a checklist before every flight — not because they forget how to fly, but because checklists prevent the specific class of errors that happen when you are rushed, stressed, or distracted. Releasing new code is the same.

Go through this checklist for every service before it handles production traffic.

---

**Timeouts**

```
□ All external API calls have timeouts
  (No call should be able to wait forever for a response)

□ Timeout values are based on actual observed latency, not guesses
  (If the API normally responds in 200ms, a 5-second timeout is too loose.
   If the API sometimes legitimately takes 2,000ms, a 500ms timeout is too tight.)

□ Timeout values are reviewed every 6 months
  (APIs change over time. Timeout from 18 months ago may no longer be appropriate.)
```

**Idempotency**

```
□ All operations with side effects have idempotency keys
  (Side effects = anything that changes state: charges, writes, sends)

□ Idempotency keys are generated from stable business identifiers
  (Not random UUIDs generated fresh on each retry — same order = same key always)

□ Idempotency is tested: call the endpoint twice with the same key.
  Verify that one operation happens, not two.

□ Idempotency store has appropriate TTL
  (How long do you need to deduplicate? 24 hours? 7 days? Match your retry window.)
```

**Retries**

```
□ Retries use exponential backoff with jitter
  (Not immediate retries, not fixed-interval retries)

□ Retries have a maximum attempt count
  (Infinite retries are not retries — they are a crash waiting to happen)

□ Retries only happen on appropriate errors
  (Retry: 503, 504, timeout. Do NOT retry: 400, 401, 403, 404, 409, 500 with
   certain meanings like "payment declined")

□ Retry budget is tracked
  (If retries consume >X% of capacity, stop retrying and fail fast instead)
```

**Circuit Breakers**

```
□ Circuit breakers on all external dependencies
  (Every third-party API, every microservice you call)

□ Circuit breaker thresholds are based on observed error rates
  (Not arbitrary numbers — review the service's normal and bad-day error rates)

□ Circuit breaker fallbacks are implemented and tested
  (What does the user see when the circuit is open? Is it acceptable?)

□ Circuit breaker state is monitored and alerted on
  (An open circuit should never go unnoticed)
```

**Load Shedding**

```
□ All request queues have depth limits
  (No unbounded queues. A queue that grows forever is a memory leak.)

□ Priority tiers are defined for all request types
  (Know what you will drop first in an overload situation)

□ Priority tier decisions are documented and cross-team approved
  (The product teams need to know and agree)

□ Deadline propagation is implemented for multi-service calls
  (The deadline from the user's request flows through all downstream calls)
```

**Graceful Degradation**

```
□ Fallback tiers are defined for all critical features
  (If feature X is down, what do users see? Is it pre-built and working?)

□ Each fallback tier is tested regularly
  (Kill the primary — does the fallback actually work? Test this before an incident.)

□ Feature flags are available to manually force a lower tier
  (During an incident, engineers should be able to degrade gracefully with one command)
```

**Monitoring and Alerting**

```
□ Error rate is tracked per service and per endpoint
  (Not just "overall system error rate")

□ Retry rate is tracked
□ P99 latency is tracked (not just average)
□ Queue depth is tracked for all queues
□ Circuit breaker state changes trigger alerts
□ Idempotency key hit rate is tracked
□ Retry budget consumption is tracked

□ All alerts have been TESTED
  (Inject artificial errors in staging. Confirm the alert fires.
   An untested alert may have a configuration bug and may never fire.)

□ Alerts have runbooks attached
  (When an alert fires at 3am, the on-call engineer should know immediately
   what to do. Write the runbook before the incident, not during it.)
```

**Operational Readiness**

```
□ Runbooks are written for each major failure scenario
  (What to do when payment service is down. What to do when database is slow.
   What to do when queue depth is maxed. Each gets its own runbook.)

□ Runbooks are tested in incident drills or game days
  (Read a runbook before a crisis. Find the gaps when stakes are low.)

□ Graceful degradation is tested intentionally
  (Turn off Service X. Observe that the system degrades gracefully.
   Fix any cases where it does not.)

□ Idempotency is tested in a chaos scenario
  (Inject random duplicate requests. Verify zero duplicate state changes.)

□ Postmortems from past incidents are reviewed before shipping
  (What did previous incidents teach you? Is the new code vulnerable to the same patterns?)
```

---

## A Note on What You Cannot Checklist

The checklist above is necessary. It is not sufficient.

Resilience is also about culture and habits. The best monitoring dashboard fails if nobody looks at it. The best runbook fails if it is not updated after the system changes. The best circuit breaker fails if its fallback serves stale data that is now wrong.

The engineers who build the most reliable systems share a few habits:

**They expect things to fail.** Not pessimistically — just honestly. "This downstream API will be slow someday. What happens when it is?" They ask this during design, not during incidents.

**They treat incidents as learning, not punishment.** When something breaks, the first question is "what can we learn?" not "who is to blame?" Blame culture causes engineers to hide problems. Learning culture causes engineers to surface problems before they become incidents.

**They test their failure paths.** "We have a circuit breaker" is meaningless until you have confirmed the circuit breaker actually trips and actually serves the fallback when the dependency fails. Testing failure paths requires deliberately breaking things in a controlled environment.

**They revisit configurations.** Thresholds that were right 18 months ago may be wrong today. Traffic has changed. Dependencies have changed. Retry and circuit breaker configurations should be reviewed regularly — not just during incidents.

**They write runbooks for 3am.** Not for themselves — for their half-asleep, adrenaline-filled self who wakes up to a pager at 3am after only four hours of sleep. That person needs step-by-step instructions, not architectural wisdom. Write the runbook imagining your least rested, most stressed state.

---

## Summary of Part C

This part covered a lot of ground. Here is a map of everything we walked through.

**Load Shedding** is the philosophy of deliberately dropping some requests in order to serve the rest well. We covered four strategies: queue-based shedding (limit the waiting room), Random Early Detection (start rejecting gradually before you hit the wall), priority-based shedding (drop low-value requests first), and deadline-based shedding (do not process requests whose clients have already given up).

**Graceful Degradation** is having a ladder of fallback options for every critical feature. When the best option fails, you drop to the next tier. You never drop to zero if you can help it. Pre-plan every tier. Test every tier. Have feature flags to manually select a tier during incidents.

**Cascading Failures** follow a pattern: one small fault redistributes load to neighboring components, they become overloaded, they fail, more load redistributes, the cascade reaches critical mass and the system collapses — long after the original fault has resolved. Prevention requires circuit breakers (stop the load redistribution), backpressure (signal overload up the chain), and no immediate retries (avoid amplifying the load).

**Real Incidents** illustrate that the gaps between theory and practice are where outages live. The Cyber Monday double-charge incident happened because retries existed without idempotency. The thundering herd happened because a maintenance window was not paired with cache warming. The partial deployment cascade happened because monitoring was configured for the whole system but not per version.

**Design Evolution** is a journey from Stage 1 (works on the happy path only) through Stage 2 (resilience mechanisms present but misconfigured) to Stage 3 (end-to-end tested, tuned, and trusted resilience). Most systems are somewhere between stages, and the work of resilience engineering is continuously moving critical paths toward Stage 3.

**Observability** is how you know whether it is working. Track error rate, retry rate, P99 latency, queue depth, circuit breaker state, idempotency hit rate, and retry budget. Alert on meaningful thresholds. Test that alerts actually fire. Attach runbooks to alerts.

**The Checklist** is the tool that prevents the specific class of errors that happen when you are moving fast, shipping frequently, and thinking about ten things at once.

Part D continues with how these concepts appear in real system design interview answers — and what separates a strong answer from a weak one.

---

*End of Part C*
# Chapter 23: Backpressure, Retries, and Idempotency — Part D
## Interview Calibration, Brainstorming Questions, Exercises, and Quick Reference

*(This is Part D — the final part of Chapter 23. Parts A, B, and C covered all the core concepts, real-world incidents, and design patterns. This part is about applying what you learned: how to talk about it in interviews, how to practice thinking through hard scenarios, and how to have a cheat-sheet you can actually use.)*

---

# Part 7: Staff-Level Interview Calibration

## How Interviews Actually Test This Topic

Here is a secret about system design interviews: interviewers almost never ask "explain backpressure to me." That would be too easy to study for. Instead, they hide the topic inside a scenario question.

The five most common disguises look like this:

**Disguise 1: "How would you handle the case where the payment service is down?"**
What they are really asking: do you know about circuit breakers? Do you know about fallbacks? Do you know what "down" means (is it down forever, or intermittently flaky)?

**Disguise 2: "What happens if the email notification fails after the order is created?"**
What they are really asking: do you understand that different operations have different criticality? Do you know how to decouple failures so an email glitch does not roll back an order?

**Disguise 3: "How do you prevent duplicate orders if the client retries?"**
What they are really asking: do you know what idempotency is? Can you design an idempotency key? Do you know the difference between making an operation safe to retry versus hoping it does not get called twice?

**Disguise 4: "How would you handle a sudden 10× traffic spike?"**
What they are really asking: do you know that auto-scaling takes several minutes? What keeps the service alive during those minutes? Do you know about token buckets, queue-based backpressure, and load shedding?

**Disguise 5: "Walk me through what happens during a cascading failure in your design."**
What they are really asking: can you trace a failure through a dependency chain? Do you understand amplification? Do you see how a small problem becomes a full outage?

### What the Interviewer Is Actually Grading

The interviewer is not grading whether you know the vocabulary words. They are grading whether you **think about failure from the start**.

There are two types of candidates:

**Type 1 — Reactive:** Designs the happy path. When the interviewer asks "what if the payment service is down?" they pause, think, and add a retry. One problem at a time, prompted by the interviewer.

**Type 2 — Proactive:** During the initial design, says things like: "I'll add an idempotency key here because clients will retry on timeout. I'll put a circuit breaker on the payment call because I don't want a Stripe outage to take down the entire checkout. Email notifications will be async — order success doesn't depend on email."

Type 2 is the L6 signal. Proactively mentioning retries, idempotency, circuit breakers, and degradation **without being asked**.

---

## L5 vs L6 Contrast Table

This table shows the same scenario answered at two different levels. The L5 answer is not wrong — it just does not go far enough.

| Scenario | L5 Approach | L6 Approach |
|---|---|---|
| "Payment service times out" | "Add retry with 3 attempts" | "Retry with exponential backoff AND an idempotency key so the retry cannot double-charge. Plus a circuit breaker — if Stripe's error rate hits 20% in the last 30 seconds, stop retrying altogether and fail fast with a clear error to the user." |
| "We need to handle 10× traffic spike" | "Auto-scale the servers" | "Auto-scaling takes 3-5 minutes. What happens in the first 5 minutes? Implement a token bucket so the service stays alive during scale-up rather than collapsing. Define exactly what degrades gracefully — recommendations shed first, search second, checkout never." |
| "Email notification sometimes fails" | "Retry the email send" | "Email goes into an async queue. Order confirmation does not wait for email. The queue retries with exponential backoff. After 5 failures, message goes to a dead-letter queue for manual review. The order is never failed because of an email." |
| "Retry rate is 20%" | "That seems high, keep an eye on it" | "20% retry rate means 1 in 5 requests is failing on first try. That is the actual problem you need to fix. High retry rate is a symptom of a broken dependency — find the root cause. Tuning the retry config is not the answer." |
| "User sees duplicate order" | "Find the bug in the retry code" | "This is an architecture bug, not a code bug. Retries on non-idempotent operations will always produce duplicates eventually. Idempotency keys at the API level prevent this structurally — it does not matter what the retry code does." |
| "Service degraded — some requests slow" | "Scale up" | "Slow is often worse than down. Slow requests hold threads open. Thread pool exhaustion crashes the entire service. Set aggressive timeouts and fail fast. A 2-second timeout that returns a clear error is better than a 30-second wait that hangs everything." |
| "Circuit breaker is open" | "Increase the threshold so it stops opening" | "The circuit breaker is working — it is protecting you from a broken dependency. Do not silence it. Find out why the dependency is failing. The open state is the feature doing its job correctly." |
| "Need 99.9% uptime for this endpoint" | "Add redundancy and monitoring" | "99.9% means 8.7 hours of downtime per year — about 43 minutes per incident if you have one per month. Your MTTR must be under 43 minutes. That means: monitoring alert latency + on-call response time + fix and deploy time must all fit in that window. Work backwards from the SLA to the requirements." |

### The L6 Pattern

L6 engineers answer the question "what happens when X fails?" during the design phase, not during the interviewer's follow-up questions. If you find yourself saying "oh, good point, I should add a retry there" in response to the interviewer's prompting, you are at L5. If you say "I am putting a circuit breaker here because if this dependency flakes, I do not want it to take down the whole service," you are at L6.

The mental model is simple: **every external call is a promise that might be broken**. Design for the broken promise from the start.

---

## The L6 Sample Answer: "Design a Payment Processing API"

*This is a full 8-minute answer. Read it like a script. Notice: it starts with clarifying questions, covers failure modes during the design (not after), and ends with a specific failure scenario walkthrough.*

---

**Opening (Minutes 0-2): Clarify before designing**

"Before I start drawing boxes, I want to make sure I understand the constraints. A few questions:

What is the expected volume — transactions per second at peak?

Does this need to be exact-once (meaning: charging twice is worse than not charging at all, like a financial transaction), or is approximate-once okay?

Are there regulatory requirements I need to be aware of — PCI-DSS, SOX?

What is downstream — are we integrating with Stripe, a bank, an internal ledger?

*[Assume interviewer answers: 10,000 transactions per second at peak, exact-once mandatory because this is financial, downstream is Stripe's API.]*

Great. The key challenge with a payment API is three things working together: it must be **idempotent** (charging twice is catastrophic), **resilient** (network failures cannot leave us in unclear state), and **auditable** (every attempt and its outcome must be logged, permanently)."

---

**Core Design (Minutes 2-7)**

"Let me walk through the design in layers.

**Layer 1: Idempotency at the edge**

Every charge request from the client must include an `idempotency_key`. We generate this key from: the user ID, the order ID, and a hash of the attempt number. Something like:

```
idempotency_key = "charge-{user_id}-{order_id}-{attempt_hash}"
```

Before processing any charge, we check a dedicated `idempotency_keys` table in our database. If the key already exists and has a stored result, we return that cached result immediately without touching Stripe. No second charge.

We store results for 7 days — long enough for any reasonable client retry scenario, short enough to not grow forever. This table is separate from our main payments table because it gets hit on every single request and we want to optimize its read performance.

**Layer 2: The payment state machine**

Each payment moves through states: `PENDING → PROCESSING → COMPLETED` or `FAILED` or `REFUNDED`.

State transitions are atomic — we use a database transaction with a row lock. The transition from PENDING to PROCESSING can only happen once, which prevents two workers from picking up the same payment simultaneously. If two servers race to process the same payment, one gets the lock and the other sees `PROCESSING` already and backs off.

**Layer 3: Calling Stripe**

When we call Stripe, four things happen:

First: we set a 10-second timeout. Stripe's P99 latency is around 2 seconds, so 10 seconds is generous but bounded. Without a timeout, a slow Stripe response holds our thread forever.

Second: we retry up to 3 times with exponential backoff — 100ms, 200ms, 400ms — with ±25% jitter so a batch of simultaneous failures do not all retry at the exact same moment.

Third: we pass OUR idempotency key to Stripe. Stripe supports this natively. This means even if we call Stripe twice with the same key, Stripe will process the charge exactly once and return the cached result on the second call. Our idempotency protection flows all the way through to the payment processor.

Fourth: a circuit breaker monitors Stripe's error rate over a 30-second rolling window. If the error rate exceeds 20%, the circuit opens for 60 seconds. No new requests reach Stripe. This gives Stripe time to recover and prevents a Stripe outage from consuming all our threads.

**Layer 4: When the circuit opens**

When Stripe's circuit is open, we have a choice of fallbacks:

Option A: queue the payment for processing once the circuit closes, tell the user "payment processing — please wait."

Option B: fail immediately with a clear user-facing message: "Payment temporarily unavailable, please try again in a moment."

Option C: if we have a backup payment processor configured, route there.

For a financial application, I would lean toward Option A or B — queuing is safer than routing to an untested fallback processor without rigorous testing of that path.

**Layer 5: Monitoring**

Five metrics I am alerting on:

Payment success rate — should be above 99.9%. Alert at 99.5%.

Payment latency P99 — should be under 3 seconds. Alert at 5 seconds.

Idempotency key hit rate — normally under 1% of requests. A spike means a client is in a retry storm or has a bug where it is generating duplicate requests.

Circuit breaker state — alert immediately when the Stripe circuit opens. This is an incident.

Retry rate per attempt — first-attempt failures should be under 5%. Higher than that means Stripe is having a sustained problem."

---

**Failure Scenario Walkthrough (Minute 7-8)**

"Let me walk through the trickiest failure scenario: user clicks Pay, the request flows through, Stripe processes the charge successfully, but our database update times out before we can save the result. Our server crashes.

The user retries with the same idempotency key.

We check our idempotency table — the key is not there (we crashed before saving it).

We call Stripe with the same idempotency key — Stripe returns the cached result from the first charge. No second charge occurs at Stripe.

We save the result to our DB.

We return success to the user.

No double charge. The idempotency key flowing through both our system and Stripe's system protected us even through a complete server crash. This is why idempotency keys need to be consistent across retries — not randomly generated each time."

---

## Common Mistakes in Interviews

These are the six things interviewers see most often. Knowing them helps you avoid them.

---

**Mistake 1: "I'll retry on all errors"**

What the interviewer hears: "This person does not know which errors are retryable."

The problem: a `400 Bad Request` means your request is wrong. Retrying it 5 times will return the same `400` five times — it will never fix itself. A `500 Internal Server Error` might be caused by your request hitting a bug in the server — retrying could trigger the bug 5 times.

The right answer: specify exactly which codes you retry on. Safe retries: `408 Request Timeout`, `429 Too Many Requests` (after the Retry-After delay), `502 Bad Gateway`, `503 Service Unavailable`, `504 Gateway Timeout`. Do not retry: `400`, `401`, `403`, `404`, `422`.

---

**Mistake 2: "Exponential backoff" without mentioning jitter**

What the interviewer hears: "Close, but not production-ready."

The problem: without jitter, if 1,000 clients all experience the same timeout at time T=0, they all wait exactly 1 second, and they all retry at T=1000ms simultaneously. You have just created a synchronized retry wave — the second spike is as bad as the first.

Jitter adds a random offset, typically ±25% of the backoff duration. Instead of all 1,000 clients retrying at exactly T=1000ms, they retry in a spread window between T=750ms and T=1250ms. The wave becomes a drizzle.

---

**Mistake 3: "Use a queue to handle the spike"**

What the interviewer hears: "Queues help, but this person has not thought about queue behavior under sustained load."

The problem: a queue is a buffer, not a capacity increase. If traffic is consistently 10× your processing capacity, the queue fills. Once it fills, you are rejecting requests — but now with added latency for the requests that did get through (they had to wait in the queue). A queue buys time for auto-scaling to kick in. It does not solve sustained overload.

The complete answer: queue + load shedding + capacity planning. Know when to start shedding requests so the queue never fills completely.

---

**Mistake 4: "Add a circuit breaker" without specifying the fallback**

What the interviewer hears: "They know what a circuit breaker is but not how to use it in practice."

A circuit breaker without a fallback is a feature that turns your service into an error machine. When the circuit opens, what does your service return to the caller? An HTTP 503? A cached result from 5 minutes ago? A simplified response that skips the failing dependency? The fallback is where 90% of the design value is. The circuit breaker just triggers it.

---

**Mistake 5: Solving exactly-once delivery with "check then write" without atomicity**

```python
# THIS IS BROKEN — race condition
if not already_processed(order_id):    # Two servers check simultaneously
    process_payment(order_id)           # Both see "not processed"
    mark_processed(order_id)            # Both process — double charge
```

Two servers check simultaneously, both see "not processed," both process the payment, and you have a double charge. The window between check and mark is the race condition.

The fix is atomic check-and-insert. In PostgreSQL, use a UNIQUE constraint on the idempotency key and an `INSERT ... ON CONFLICT` statement. In Redis, use `SETNX` (Set if Not eXists). The database or cache enforces atomicity — only one writer wins.

---

**Mistake 6: Timeout longer than the caller's timeout**

If your API sets a 30-second timeout when calling the payment service, but the user's browser has a 10-second timeout, here is what happens: the user's browser gives up at 10 seconds and shows an error. The user may retry or leave. Your API server is still sitting there, thread held open, waiting for the payment service to respond at second 30. The thread served nobody. The resource was consumed for zero benefit.

Timeouts must be set relative to the caller's timeout. Your downstream timeout must always be shorter than your own service's timeout, which must be shorter than your caller's timeout. This is called timeout budget propagation, and it is the correct way to configure timeouts in a chain of services.

---

## Key Numbers to Know for Interviews

Memorize these. Interviewers will notice if your numbers are wildly off — "10 retries with 5-second backoff" signals you have not operated a real production system.

| Metric | Typical Value | Why It Matters |
|---|---|---|
| Max retry attempts | 3-5 | More than 5 retries means the error is probably not transient |
| Base backoff duration | 100ms | Minimum time for a service to breathe and recover |
| Max backoff duration | 30 seconds | Users will not wait longer; beyond this, the problem is not transient |
| Jitter range | ±25% of backoff | Enough to spread retry waves without making backoff unpredictable |
| Circuit breaker error threshold | 50% error rate | If half your requests are failing, something is clearly broken |
| Circuit open duration | 30-60 seconds | Time for a service to restart and warm up |
| Token bucket burst capacity | 2-10× sustained rate | Allows normal bursts; stops traffic spikes from overwhelming |
| Token refill rate | Your actual measured sustained req/sec | Match to what you have actually measured, not what you hope for |
| P99 latency alert threshold | 3-5× your normal P99 | "Something is slow" without being a full crisis |
| Idempotency key TTL | 24 hours to 7 days | Long enough for any reasonable retry scenario |
| Thread pool size (I/O-heavy) | CPU cores × 10 | Most time is spent waiting on I/O, so more threads than cores is fine |
| Thread pool size (CPU-heavy) | CPU cores × 2 | CPU-bound work does not benefit from more threads than cores |

---

# Part 8: Brainstorming Questions

*These 30 questions are designed to be worked through, not just read. For each one, write your answer before looking for hints in the question structure. The best use of this section: treat each question as a 10-minute practice problem.*

---

## Section A: Retry Fundamentals (Questions 1-6)

---

**Question 1: The Thread Pool Math**

Your checkout service calls the payment API. Normally, the payment API responds in 50ms. Today it is having issues and takes 3,000ms (3 seconds) per call — 60× its normal latency. You have 50 threads in your checkout service's thread pool. Checkout requests arrive at 10 per second.

**Part A:** How quickly does your 50-thread pool fill up? Show the math.

*Hint: Each thread is held for 3 seconds instead of 0.05 seconds. At 10 requests/second arriving, how many threads are "in use" at any given moment?*

At normal latency: 10 requests/sec × 0.05 sec/request = 0.5 threads in use on average. Plenty of headroom.

At degraded latency: 10 requests/sec × 3 sec/request = 30 threads in use on average.

But arrivals are not perfectly spread — after 5 seconds, you have processed 50 requests, and all 50 threads are tied up waiting for the payment API. New requests find no available threads.

Time to fill the pool: approximately 5 seconds.

**Part B:** When the thread pool is full, what happens to new checkout requests? What do users see?

**Part C:** How does a circuit breaker prevent this specific failure? Write the sequence: what does the circuit breaker detect, what does it do, and what does the checkout service return when the circuit is open?

---

**Question 2: The "Idempotent Email" Myth**

You are reviewing code that retries an email send 5 times with 1-second fixed intervals. The developer says "it is fine, emails are idempotent."

**Part A:** Are email sends truly idempotent in this implementation? Describe the specific scenario where retrying an "idempotent email send" 5 times still causes a user to receive 5 copies of the same email.

*Think about: what does "idempotent" actually require? Is the email-sending operation checking anything before sending?*

**Part B:** How do you make email sends actually idempotent? What does the email service need to track, and what does it check before sending each email?

*Think about: what would be a good "idempotency key" for an email? Something like `{user_id}-{template_id}-{order_id}-{date}` — specific enough that the same email to the same user for the same event on the same day is only sent once.*

---

**Question 3: Retry Budget Math**

Your service has a "retry budget" policy: retries can consume at most 10% of total request capacity.

Current situation:
- Traffic: 10,000 requests/second
- Error rate: 5% (500 failures/second)
- Retry policy: 3 retries per failure

**Part A:** How many retry requests per second does your current policy generate? Does this exceed your 10% budget?

*Math: 500 failures × 3 retries = 1,500 retry requests/second. Your 10% budget = 1,000 requests/second. You are over budget.*

**Part B:** At what error rate does a 3-retry policy start consuming more than 10% of your 10,000 req/sec capacity?

*Set up the equation: (error_rate × 10,000) × 3 retries = 1,000 (your budget). Solve for error_rate.*

**Part C:** Given your answer to Part B, what should you do if the error rate exceeds that threshold? List two options beyond "just retry fewer times."

---

**Question 4: The Aggressive Client**

A client library has this retry logic: "On timeout: retry immediately with no delay. On error: no retry at all."

Your service experiences a latency spike: 90% of requests time out.

**Part A:** What is the effective request amplification factor hitting your service? If you were receiving 1,000 req/sec before the spike, how many total requests does your service receive now?

*Think: every request that times out is immediately retried. If 90% time out, and those retries also time out, and those retries also time out... this continues until the client gives up.*

**Part B:** You cannot change the client library (it is a third-party SDK). What server-side protection mechanisms do you add to survive this client's behavior?

---

**Question 5: Config Comparison**

You are choosing between two retry configurations for a service with 1% normal error rate:

**Config A:** 5 retries, 100ms fixed backoff, no jitter
**Config B:** 3 retries, exponential backoff (100ms → 200ms → 400ms), ±25% jitter

Under **normal conditions** (1% error rate): which configuration gives better user experience? Compare total retry time in the worst case for each.

Under **overload conditions** (30% error rate, 500 servers all retrying simultaneously): which configuration is safer for the overall system? Explain what happens with Config A when 500 servers all retry simultaneously.

---

**Question 6: Timeout vs. Circuit Breaker — Different Problems**

A common interview mistake is saying "I'll use a timeout AND a circuit breaker" without explaining why you need both. They solve different problems.

**Part A:** Describe a scenario where a timeout alone is insufficient — where the timeout fires correctly but the system still degrades. 

*Hint: think about what happens when timeouts fire repeatedly, one after another, without the system learning from the pattern.*

**Part B:** Describe a scenario where a circuit breaker alone is insufficient — where the circuit breaker does exactly what it is designed to do, but you still need a timeout.

*Hint: think about what happens before the circuit breaker has seen enough failures to trip.*

---

## Section B: Idempotency Deep Dives (Questions 7-12)

---

**Question 7: Subscription Billing Idempotency**

You are building a monthly subscription billing system. Every month, each subscriber's card is charged exactly once.

**Part A:** Design the idempotency key. It must prevent:
- The same subscriber being billed twice in the same month (billing job runs twice due to a bug)
- Last month's billing key being reused for this month's billing

*What fields should compose the key? Think about: subscriber ID, billing period (year + month), attempt number.*

**Part B:** The January billing job runs, succeeds for 80% of subscribers, then crashes. You restart the job. How do you ensure you only bill the 20% who were not yet charged, and not re-bill the 80% who were already charged?

*Think about: how does the idempotency key check help here? What does the billing job need to do differently from a simple "charge everyone" loop?*

---

**Question 8: Edge Cases in Idempotency Key Storage**

An idempotency key is stored with a 7-day TTL. What happens in each of these scenarios?

**Scenario A:** A client retries after 8 days with the same idempotency key. The TTL has expired and the key is gone.

Is this safe? What should the server do — reject the request, process it fresh, or something else? What is the risk?

**Scenario B:** Two different users both happen to send a request with the idempotency key value `"purchase-123"` (they both chose this key independently).

What happens? Is this a real risk? How do you prevent key collisions across users?

**Scenario C:** The server processes a request completely (the operation succeeds), but crashes before it can write the idempotency result to storage. The client retries with the same key.

Walk through what happens. Is this safe? What is the worst-case outcome?

---

**Question 9: The Multi-Step Operation**

An order placement involves four steps executed in sequence:
1. Reserve inventory
2. Charge payment
3. Create order record
4. Send confirmation email

The idempotency check happens at the very start. If the server crashes after step 2 but before step 3, what happens on the client's retry?

**Part A:** If you stored the idempotency key (as "in progress") after step 1 only, what does the retry see? What is the behavior?

**Part B:** If you stored the idempotency key (as "complete") only after all 4 steps succeed, what does the retry see? What is the behavior? What is the risk?

**Part C:** What is the correct approach? When should the idempotency key be stored, and with what status?

*Think about: you need to store it early enough to prevent duplicate processing, but with a status that tells the retry what happened — was it completed? was it in progress and maybe completed?*

---

**Question 10: Idempotency vs. Business Rules**

Idempotency keys prevent replay of the same request. But they do not prevent a client from making two slightly different requests that achieve the same business effect.

Example: a client sends "transfer $100 from Account A to Account B" with key=`txn-001`, succeeds. Then sends "transfer $100 from Account A to Account B" with key=`txn-002`. This is a different idempotency key, so it processes as a new transfer.

**Part A:** Is this an idempotency problem or a business logic problem? Where in the system does this belong?

**Part B:** What mechanism enforces business constraints like "Account A can only transfer $500 per day to Account B"? This is separate from idempotency — what is it called, and where does it live?

---

**Question 11: The Credit Transfer**

You are building a "transfer credits between users" feature. The operation debits User A and credits User B. Both must succeed or neither should — this is a transaction.

**Part A:** Design the idempotency key for this transfer.

**Part B:** This failure scenario occurs: the transfer completes successfully (A debited, B credited), but the server crashes before writing the idempotency result. The client retries with the same key. The idempotency check finds no stored result. The system reprocesses: A is debited again. B now has double credits.

Walk through why this is a problem and what went wrong.

**Part C:** Write the correct sequence of operations to prevent this. What must happen atomically, and in what order must the idempotency result be stored relative to the actual transfer?

*Hint: the idempotency result and the transfer operation should happen in the same database transaction. If the DB transaction commits, both happen. If it rolls back, neither happens.*

---

**Question 12: Explaining Idempotency-Replayed to a Client**

Your API returns an `Idempotency-Replayed: true` header when it returns a cached result from a previous identical request.

A client developer sends you this message: "I got `Idempotency-Replayed: true` on my payment request. Does this mean my original payment failed and you are showing me a cached error? Should I try again with a new key?"

Write the explanation you would give this developer. Cover:
- What the header actually means
- Whether the original request succeeded or failed
- When they should expect to see this header
- What action (if any) they should take in response to this header

---

## Section C: Backpressure and Load Shedding (Questions 13-18)

---

**Question 13: Little's Law in Practice**

Little's Law states: average number of requests in the system = arrival rate × average time in system. Written as: `L = λ × W`.

Your API currently:
- Serves 5,000 requests/second (λ = 5,000)
- Has 20ms average latency (W = 0.020 seconds)
- Average concurrent requests in flight: L = 5,000 × 0.020 = 100

You add a new feature that doubles latency to 40ms. You do not change server capacity.

**Part A:** What is the new average number of concurrent requests in the system?

**Part B:** Your servers have a 100-thread thread pool. At 20ms latency, you had 100 concurrent requests — exactly at the limit. What happens at 40ms latency?

**Part C:** At what average latency does the system start dropping requests? (Use Little's Law and your thread pool size to find the maximum W before L exceeds 100.)

---

**Question 14: Token Bucket Walkthrough**

A token bucket has: `capacity = 1,000 tokens`, `refill_rate = 100 tokens/second`.

The bucket starts full (1,000 tokens).

**Client A** sends 1,000 requests in the first second (uses all 1,000 tokens). Then sends 100 requests/second for the next 60 seconds.

**Part A:** How many of Client A's requests get through in the first second?
**Part B:** In the second second, the bucket has refilled 100 tokens. How many of Client A's 100 requests get through?
**Part C:** In the third second? What is the pattern?

**Client B** sends 50 requests every 5 seconds (same average rate as Client A: 10 requests/second). Client B's requests arrive at the start of each 5-second window.

**Part D:** How many of Client B's 50 requests get through in the first window (seconds 0-5)?
**Part E:** How many get through in the second window (seconds 5-10)?
**Part F:** Which client has better throughput, and why? What does this tell you about burst behavior and token buckets?

---

**Question 15: The Unhappy Product Team**

Your load shedding strategy drops LOW priority requests when queue depth exceeds 80% of maximum capacity. The "search recommendations" feature is classified as LOW priority.

A competitor writes a blog post showing their app always displays recommendations. Your app frequently shows "Recommendations unavailable." Your product team is unhappy.

**Part A:** Explain to a non-technical product manager (in plain language, no jargon) why this is the correct trade-off. What would happen if you kept showing recommendations but stopped shedding?

**Part B:** The product team says "recommendations must always work — this is a business requirement." What are the two changes you could make to honor this requirement? What does each cost?

*Hint: you can either reclassify the priority (with consequences) or increase capacity so you never need to shed this tier.*

---

**Question 16: Video Upload Backpressure Design**

Users upload videos at variable rates. Your transcoding service can process 100 concurrent videos. You cannot add more transcoding capacity.

**Part A:** When transcoding is at capacity (100 videos in progress), what should happen to a new upload? Evaluate these three options:

Option A: Accept the upload, buffer it in a queue, start transcoding when a slot opens.
Option B: Reject the upload immediately with a clear error message.
Option C: Accept the upload into the upload step, but slow down the upload data rate (actual byte transfer rate, not just response time).

For each: what is the user experience? What are the risks? Which do you choose and why?

**Part B:** A user has been uploading a 4GB video for 35 minutes. The upload completes. They get an error: "Transcoding queue full, please try again later." The user is furious — they spent 35 minutes uploading and now they have nothing.

How should the system have been designed differently to prevent this specific situation? What information should the user have seen during the upload, and when?

---

**Question 17: Deadline Propagation in HTTP**

Your microservices use HTTP/REST. Service A calls Service B, which calls Service C.

You want to implement deadline propagation: if Service A has 500ms left before its own deadline, it should tell Service B "you only have 450ms" (leaving 50ms buffer). Service B, after its own 100ms of processing, should tell Service C "you only have 350ms."

**Part A:** HTTP has no built-in deadline propagation header. Design a header-based convention. What header name do you use? What format is the value (absolute timestamp? relative milliseconds remaining?)? What are the trade-offs of each format?

**Part B:** Service B spends 100ms on its own processing before calling Service C. How does this change the deadline B passes to C? Write the formula.

**Part C:** Service C receives a request with 20ms remaining on the deadline. Service C's minimum processing time is 50ms. What should Service C do immediately upon receiving this request?

---

**Question 18: Three Mechanisms, Three Use Cases**

Explain the difference between these three backpressure mechanisms and when you would use each:

**Rate limiting:** controlling requests per unit of time (e.g., 100 requests per second per user)

**Concurrency limiting:** controlling the number of simultaneous in-flight requests (e.g., at most 50 simultaneous DB queries)

**Queue-based backpressure:** using queue depth as the signal to accept or reject work (e.g., reject when queue is above 80% full)

For each mechanism:
1. What signal triggers the limiting?
2. What type of abuse or overload does it protect against?
3. Give one specific real-world use case where this is the right choice.

---

## Section D: Cascading Failure Analysis (Questions 19-24)

---

**Question 19: The 2am Database Maintenance**

A database runs a full table scan maintenance job (`ANALYZE TABLE`) at 2am during low traffic. The table lock it acquires causes all write operations to block for 60 seconds. Your architecture: application servers → write-through cache → database. The cache has no read fallback when writes fail.

Map out the cascading failure:

**Part A:** In the first 60 seconds, what fails in what order? Be specific about which services are affected and how.

*Walk through it step by step: at T=0 the lock is acquired. At T=1, the first write request hits the database and blocks. At T=5, 5 seconds × (write req/sec) requests are queued on the database, all holding connections. At T=30, your application server's thread pool is filling up because threads are waiting for database responses that are not coming. At T=60, the lock releases — but now what?*

**Part B:** After the lock releases (60 seconds later), what happens next? Does everything recover immediately or is there a "recovery failure"?

*Think about: 60 seconds of queued writes now all try to execute simultaneously. What does that look like for the database's CPU and I/O? Is this a gradual recovery or a second spike?*

**Part C:** What survives throughout this incident? Is there any part of your system that still works during the 60-second lock?

*Hint: the architecture is write-through cache. What about reads? If writes are failing but the cache has fresh data, can reads succeed?*

**Part D:** Name three specific architectural changes that would prevent this incident or dramatically reduce its impact.

*Think across three layers: the maintenance job scheduling, the cache architecture, and the application server configuration.*

---

**Question 20: The Timeout Chain**

You have this dependency chain: Mobile app → API Gateway → Order Service → Inventory Service → Database. Every service has a 30-second timeout. A single database query takes 35 seconds (one bad query, then it resolves).

**Part A:** How long does the user's mobile app wait before seeing an error? Walk through the timeout chain.

**Part B:** During the worst moment (just before all timeouts fire), how many threads are "stuck" across all services? Assume: 100 simultaneous users hitting this flow.

**Part C:** How does proper deadline propagation (as described in Question 17) change the user experience for this same scenario? What is the user's wait time with propagation vs. without?

---

**Question 21: Retry Math for Slow Dependencies**

Your service retries 3 times with exponential backoff: attempt 1 immediately, then wait 100ms, attempt 2, wait 200ms, attempt 3, wait 400ms.

The downstream service consistently responds in 600ms (it is slow but not failing).

**Part A:** Calculate the total elapsed time for all 3 attempts. (Remember: each attempt waits 600ms for the response, PLUS the backoff between attempts.)

**Part B:** You are retrying a service that responds in 600ms — but it is responding successfully on the first attempt. It is just slow. Are retries helping or hurting? Explain.

**Part C:** At what downstream response latency does retrying start being genuinely harmful? (Hint: consider what happens to your own service's response time, and how many threads are tied up during a retry sequence.)

**Part D:** How does your answer change your timeout setting? What is the right timeout for a dependency that normally responds in 50ms but occasionally spikes to 600ms?

---

**Question 22: Circular Dependencies Under Load**

Two microservices have a subtle circular dependency: Service A calls Service B for some operations, and Service B calls Service A for other operations. Under normal conditions, these are different code paths — there is no infinite loop.

Under high load, Service A's circuit breaker opens (Service B is struggling). Service A starts returning its fallback response... which happens to trigger Service B to call Service A for additional data... which returns the fallback... which triggers Service B to call Service A again...

**Part A:** Describe what happens in this situation. Does it resolve on its own?

**Part B:** Beyond this specific bug, explain why circular service dependencies are dangerous architecturally. What general principle do they violate?

**Part C:** How do you break circular dependencies? List two specific architectural patterns that eliminate them.

---

**Question 23: CDN Failure**

A CDN serves 95% of your traffic. Your origin servers handle the remaining 5%. The CDN goes completely down.

**Part A:** Walk through the failure sequence. Immediately after CDN failure, what is the traffic load on your origin servers? What fails first on the origin side, and in what order?

*The math is stark: if origin normally serves 5% of traffic, and 100% of traffic suddenly hits origin, origin receives 20× its normal load instantaneously. Unlike auto-scaling (which takes minutes), this happens in the same second the CDN goes down. Work through the cascade: web servers fill their thread pools, database connection pools exhaust, cache hit rates stay the same (cache is fine) — but can the application even get to the cache when it has no threads? In what order does each layer fall over?*

**Part B:** Design the "CDN failure playbook." What do you do in the first 5 minutes? Your answer should include: who is notified, what technical actions are taken, and what user-facing communication goes out.

*A good playbook has time-stamps. "Minute 0: alert fires. Minute 1: on-call engineer acknowledges, checks CDN status page. Minute 2: if CDN confirms outage, page the CDN vendor AND begin internal mitigation. Minute 3: ..." — write at least 5 specific steps.*

**Part C:** What should have been in place before this incident that would either prevent the outage or dramatically reduce the time to recovery?

*Think about: multi-CDN setup, origin auto-scaling pre-triggered by CDN health, static asset fallback (S3 directly), and pre-negotiated SLA with CDN vendor for priority support during outages.*

---

**Question 24: The Cache Stampede**

You added Redis as a cache in front of your database. Cache hit rate: 95%. Redis has a planned maintenance restart — the restart takes 5 minutes.

Walk through the complete incident timeline:

**Immediately (T=0, Redis restarts):** What happens to your application's request handling? What does the cache miss rate become?

**T=0 to T=30 seconds:** What happens to your database query load? If your database normally receives 500 queries/second (the 5% cache misses), what does it receive now?

**T=30 seconds to T=2 minutes:** Your database is under 10,000 queries/second (where it normally sees 500). Describe the database behavior. What does query latency look like? What happens to your application's response times?

**T=2-5 minutes (Redis comes back online):** Does traffic immediately return to normal? Or is there a second problem? Describe the "thundering herd" re-caching behavior.

**Recovery:** After Redis is fully warmed (5-15 minutes post-restart), what does normal look like again? Is there a risk that the database remains degraded even after Redis is healthy?

**What should have been in place:** Name three specific mechanisms that would have prevented this incident or dramatically shortened it.

*Think about: cache warming before the restart (pre-populate Redis with hot keys before the maintenance window starts), database connection pooling and rate limiting so the burst cannot overwhelm the DB, and a gradual traffic migration strategy (redirect 10% of traffic to miss the cache, see if DB handles it, then proceed) rather than a sudden full restart. Also consider: should a "planned maintenance" restart ever happen during business hours without a detailed rollback plan and a database team member on standby?*

---

## Section E: System Design Questions (Questions 25-30)

---

**Question 25: Push Notification Resilience**

Design the retry and error handling for a push notification service. Context: push notifications are sent to iOS and Android devices. Characteristics:
- Delivery is not guaranteed (device might be offline, user might have uninstalled the app)
- The platform's own infrastructure (APNs for iOS, FCM for Android) can deliver duplicates under some failure conditions
- Notifications are time-sensitive — a "your order has shipped" notification sent 3 days later is confusing and useless

**Part A:** Should push notification sends be idempotent? Define what "idempotent push notification" means in this context. Given the time-sensitivity constraint, what is the appropriate idempotency window (TTL)?

**Part B:** Design the retry strategy. What is the maximum retry window before you give up on a notification? How does the time-sensitivity constraint affect your backoff timing? What do you do with notifications that could not be delivered within the window?

**Part C:** The APNs (Apple Push Notification service) sometimes returns a "DeviceTokenNotForTopic" error — meaning this device token is no longer registered for your app. Should you retry this? What should you do instead?

---

**Question 26: Async File Processing**

You are designing an API for processing uploaded files — images, documents, spreadsheets. Processing takes 30 seconds to 5 minutes depending on file size.

**Part A:** Explain specifically why synchronous HTTP (client sends request, waits for response, response contains the result) is wrong for this use case. What are the failure modes that make it unsuitable?

**Part B:** Design the async polling pattern:
- What does the initial upload response look like? (What does the client receive immediately?)
- How does the client check on progress?
- What does the "completed" response look like?
- What does the "failed" response look like?

**Part C:** The processing server crashes mid-job. The file is half-processed. The job record shows "IN_PROGRESS" but no worker is actually processing it. How do you ensure the file eventually gets processed? Design the job recovery mechanism, including: how you detect stuck jobs, how long you wait before declaring them stuck, and what happens when you restart them.

---

**Question 27: E-Commerce Order Processing**

Design the order processing pipeline for an e-commerce platform with these requirements:
- Orders must be processed exactly once (no duplicate charges, no duplicate fulfillments)
- Payment must succeed before fulfillment begins
- Confirmation email must be sent, but the order must not fail if email fails
- Customer must know immediately (within 2 seconds) whether their order was accepted

**Part A:** Where does idempotency live in this design? Identify every place an idempotency key is needed and what that key should be.

**Part B:** How do you decouple email failure from order success? Design the async email architecture. What happens to the order record when email fails? What happens to the customer's experience?

**Part C:** You have a two-second response time requirement. But payment processing takes 0-3 seconds (Stripe P99 is 2 seconds). How do you meet the two-second requirement? (Hint: rethink what "order accepted" means.)

---

**Question 28: Production Diagnosis**

Your services report these metrics right now:

- API error rate: 2% (normal: 0.1%)
- Retry rate: 15% (normal: 2%)
- Circuit breaker entering "half-open" state: 3 times per hour (normal: 0 times)
- P99 latency: 800ms (normal: 150ms)

Diagnose what is happening. Write your diagnosis in order of investigation:

**Step 1:** What is the most likely root cause based on these metrics together?
**Step 2:** What do you look at first to confirm or deny your hypothesis?
**Step 3:** The circuit breaker going half-open 3 times per hour means it is not staying closed. What does this tell you about the downstream service?
**Step 4:** The 15% retry rate combined with 2% error rate — what math does not add up, and what does that tell you?
**Step 5:** What is your recommended immediate action while you investigate?

---

**Question 29: Cost-Optimized Geocoding**

A third-party geocoding API converts addresses to latitude/longitude coordinates. It charges $0.005 per request. Your app calls it when users update their address. Current usage: 1,000 geocoding requests/day. Cost: $5/day, $1,825/year. Goal: reduce cost by 80% while maintaining accuracy.

**Part A:** Design the caching strategy. What is a good cache key for geocoding? What is an appropriate TTL (addresses change over time, but not often)? Where does the cache live?

**Part B:** The idempotency challenge: User types their address as "123 Main St" — you geocode it and cache the result. User then updates to "123 Main St, Apt 4" — this is a different string, so it would miss the cache and trigger a new geocoding request. But the coordinates are identical (apartment numbers do not affect lat/long). How do you handle this without paying for a geocoding call?

**Part C:** Design the "address normalization" layer. Before geocoding (or cache lookup), normalize the address string. What normalizations make sense? (Case, whitespace, common abbreviations like "St" vs "Street".) How does this interact with the cache key?

---

**Question 30: Resilience Feature Prioritization**

You are building a new payments service from scratch. You have 6 months and a team of 4 engineers. You need to implement:

1. Idempotency keys on the payment endpoint
2. Circuit breaker on the payment gateway (Stripe)
3. Retry with exponential backoff and jitter
4. Token bucket rate limiting per merchant
5. Priority-based load shedding (shed analytics before payment operations)
6. Dead letter queue for failed payments that need manual review
7. Automatic failover to a backup payment processor

Prioritize these in the order you would implement them over 6 months. For each item, write one sentence explaining why it is in that position in the list.

*There is no single correct answer — but your reasoning should reflect real understanding of which failures are most dangerous, which protections are prerequisites for others, and which problems require operational experience to configure correctly.*

---

# Homework Exercises (10 Exercises)

*These exercises are designed to be done, not just read. Set a timer. Write actual answers. The goal is fluency — you should be able to talk through these answers comfortably in a 45-minute interview.*

---

## Exercise 1: Retry Strategy Design

Your service calls three external APIs in sequence to build a single response:

- **Auth API:** average 5ms latency, P99 10ms, fails less than 0.1% of requests
- **Product API:** average 50ms latency, P99 200ms, fails 2% of requests  
- **Recommendation API:** average 200ms latency, P99 2,000ms, fails 15% of requests (this is non-critical — users can see the page without recommendations)

**Part A:** For each API, specify:
- Maximum retry attempts
- Initial backoff duration
- Maximum backoff duration
- Which HTTP error codes trigger a retry
- Which HTTP error codes do NOT trigger a retry

**Part B:** What is the correct timeout for each API call? Consider: what is the maximum time you are willing to wait before giving up, and how does the P99 latency inform this number?

**Part C:** The Recommendation API fails 15% of the time and has a 2-second P99. You do not want its failures to delay your response time. Redesign the call structure. How do you call the Recommendation API in a way that:
- Does not block your main response
- Does not fail your main request if recommendations are unavailable
- Still returns recommendations when they are available quickly (under 100ms)

---

## Exercise 2: Idempotency Key System in PostgreSQL

Design the full idempotency key system for a payment API.

**Part A:** Write the SQL schema for the `idempotency_keys` table. Include:
- The key itself (string, unique)
- The stored response (what you return on a replay)
- Status (pending, complete, failed)
- Created timestamp
- Expires timestamp
- The user or tenant who owns this key (to prevent cross-user key collisions)

**Part B:** Write pseudocode for two functions:

`check_and_claim_idempotency_key(key, user_id, ttl)`:
- If the key exists for this user: return the stored result
- If the key does not exist: atomically insert it with status "pending" and return "new request — proceed"
- Handle the race condition: two requests with the same key arrive simultaneously

`store_idempotency_result(key, user_id, result, status)`:
- Update the stored result after the operation completes
- Mark status as "complete" or "failed"

**Part C:** Write pseudocode for the TTL cleanup job that deletes expired keys. Requirements:
- Must not lock the entire table
- Must not delete keys mid-request (race condition with active requests)
- Should run regularly without impacting production query performance

---

## Exercise 3: Circuit Breaker State Machine Walkthrough

A circuit breaker is configured with:
- `failure_threshold`: 50% error rate over the window
- `window`: 10 seconds
- `open_duration`: 30 seconds
- `half_open_test`: 1 test request

Here is the event log for 60 seconds:

| Time Period | Requests | Failures | Error Rate |
|---|---|---|---|
| T=0 to T=10 | 100 | 10 | 10% |
| T=10 to T=20 | 100 | 60 | 60% |
| T=20 to T=50 | — | — | (circuit is open — no requests pass through) |
| T=50 | 1 test request | 0 (success) | 0% |
| T=50 to T=60 | 100 | 5 | 5% |

**Part A:** Walk through each time period. State the circuit breaker state at the END of each period and explain why it changed (or did not change).

**Part B:** During the OPEN period (T=20 to T=50), all client requests receive an immediate error without hitting the downstream service. Compare two scenarios:

Scenario 1: Without a circuit breaker — all requests pass through to the failing service, which is responding with 60% errors and 3-second latency on the failures.

Scenario 2: With the circuit breaker open — all requests receive an immediate error (< 1ms).

For each scenario: what is the average response time for clients? How many threads are tied up at peak? Which is better for the overall system?

---

## Exercise 4: Load Shedding Design

Your service handles these request types:

| Request Type | Business Priority | % of Traffic |
|---|---|---|
| `POST /checkout` | Revenue-critical | 10% |
| `GET /product_search` | Revenue-important | 30% |
| `GET /recommendations` | Nice-to-have | 40% |
| `POST /analytics_events` | Internal logging | 15% |
| `GET /health_check` | Infrastructure | 5% |

Your service can handle **5,000 requests/second** at full capacity. Current traffic: **7,000 requests/second**.

**Part A:** Assign a priority tier (1 = highest, 4 = lowest) to each request type. Design the shedding thresholds: at what capacity utilization percentage does each tier start being shed?

**Part B:** At 7,000 requests/second (40% over capacity), apply your priority system. How many requests of each type get through per second? Show the math.

**Part C:** The recommendation team's manager comes to you and says: "Our team's work is being completely blocked by your load shedding. Recommendations never work during peak hours and our metrics look terrible." 

Write the response you would give. Include: why this is the right trade-off, what the alternative would have cost, and what options exist if recommendations truly must be protected.

---

## Exercise 5: Post-Mortem Analysis

Write a post-mortem for this incident:

**Incident Timeline:**
- Monday 9:00am: Traffic nominal (5,000 req/sec)
- 9:15am: Redis cache restarts (planned maintenance, expected 2-minute restart)
- 9:15am: Cache miss rate goes from 5% to 100% — database receives 10× normal query load
- 9:16am: Database latency climbs from 10ms to 2,000ms
- 9:17am: API server threads fill up (all 100 threads waiting for slow database responses)
- 9:17am: Clients begin retrying (configured for 3 retries, no backoff delay)
- 9:18am: Database receiving approximately 30× normal query load from client retries amplified by application retries
- 9:18am: Database crashes (OOM — out of memory)
- 9:18am: Complete site outage begins
- 9:45am: Database restarted and stabilized
- 9:50am: Redis re-populated with warm cache data
- 10:00am: Normal traffic and latency restored

**Total outage duration: 42 minutes**

**Part A: Root Cause Analysis (5 Whys)**
Starting with "The site went completely down," apply the 5 Whys technique to trace back to the actual root cause.

**Part B: Contributing Factors**
List at least 4 things that turned a 2-minute Redis restart into a 42-minute outage. For each factor, explain specifically how it made the situation worse.

**Part C: Action Items**
Write 5 specific, implementable action items. Each should name: what exactly is being implemented, who owns it, and what failure mode it prevents.

**Part D: Self-Recovery Analysis**
If engineers had done nothing at all — no intervention — how long would the site have taken to recover on its own? Walk through the sequence of events that would have led to recovery (or would it have stayed down indefinitely?).

---

## Exercise 6: Video Transcoding Pipeline

Design backpressure for a video transcoding service:
- Users upload videos (variable rate: typically 0-500/hour, peaks at 2,000/hour)
- Transcoding takes 5-30 minutes per video
- You have 20 transcoding workers
- Budget constraint: you cannot add more than 5 additional workers

**Part A:** What is the maximum sustained upload rate this system can support?

*Hint: with 20 workers and minimum 5 minutes per video, at most 20 videos can be transcoding simultaneously. How many can complete per hour?*

**Part B:** During a 2,000 uploads/hour peak (lasting 3 hours), design:
- The queue structure (what information is stored per job? what is the maximum queue size before you start rejecting uploads?)
- The user communication (what do you tell users whose videos are queued? how do you set expectations?)
- The priority system (which videos get transcoded first — newest, oldest, or users with premium accounts?)

**Part C:** A user uploads a video during peak. Write the exact API response they receive when their upload is accepted but queued. Include: HTTP status code, key response fields, what the user should expect, and when they should check back.

---

## Exercise 7: Multi-Tenant Token Bucket Rate Limiter

Build a token bucket rate limiter for a multi-tenant API:
- Each tenant has their own rate limit (range: 100 to 10,000 requests/minute based on subscription plan)
- Rate limits are stored in a configuration service
- The rate limiter must work correctly across 10 API servers (shared state required)
- Redis is available for shared state

**Part A:** Design the Redis data structure for storing token bucket state per tenant. Specify: key name format, data type (string, hash, sorted set?), and exactly what fields are stored.

**Part B:** Write the rate check pseudocode. Your algorithm must handle:
- Concurrent requests from different API servers hitting the same tenant simultaneously
- Burst allowance: allow up to 2× the sustained rate for up to 30 seconds
- Rate limit changes: when a tenant upgrades their plan mid-month, the new limit takes effect immediately

*Pay special attention to atomicity — this must be a single atomic operation to prevent race conditions across 10 servers.*

**Part C:** Redis goes down completely. What happens to your API's rate limiting? Design the degraded behavior: 
- Option A: fail open (allow all requests, no rate limiting)
- Option B: fail closed (reject all requests)
- Option C: fall back to per-server in-memory limits

For each option: what are the risks? Which would you choose and why?

---

## Exercise 8: Timed Interview Practice

Set a 25-minute timer. No notes. Answer this question as if you are in a real interview:

**"Design the resilience layer for an e-commerce checkout API. The API calls three services: a payment service, an inventory service, and a shipping rate calculator service."**

Follow this structure:

**Minutes 0-3:** Clarify requirements. Ask 3-4 specific questions about volume, consistency requirements, and which failures are tolerable.

**Minutes 3-10:** Design the core flow with resilience built in. For each of the three downstream calls, specify: timeout, retry policy, idempotency approach, and circuit breaker configuration.

**Minutes 10-17:** Walk through failure scenarios. What happens when: the payment service is down? the inventory service is slow? the shipping calculator returns wrong data?

**Minutes 17-22:** Design the degraded modes. What does checkout look like when payment is down (queue + delayed processing)? When inventory is down (optimistic reservation)? When shipping calculator is down (show flat-rate estimate)?

**Minutes 22-25:** Design the monitoring. List the 5 most important metrics you are tracking and what the alert threshold is for each.

After the timer: review your own answer. What did you not cover? What would you change? Write the 3 things you would add with 10 more minutes.

---

## Exercise 9: Real-World Cascade Analysis

Read this scenario:

*"A major cloud provider experienced a cascading failure when a metadata service (which provides authentication credentials to virtual machines) had a performance degradation. Virtual machine instances, which refresh credentials every few minutes, began experiencing timeouts when calling the metadata service. Their retry logic kicked in — each VM retried the credential refresh 3 times immediately, with no backoff. This 3× amplification on an already-struggling service caused further degradation. New virtual machines could not start because they could not retrieve their initial credentials. The metadata service, receiving 3× normal load from retries plus new-machine requests, became completely unavailable. The outage lasted 4 hours before the retry storm subsided enough for the service to stabilize."*

**Part A:** Draw (or describe in text) the dependency graph that caused this cascade. Label each node with: what it does, what it depends on, and how it behaves when the dependency is slow.

**Part B:** At what specific point in the sequence could a circuit breaker have interrupted the cascade? Would the circuit breaker have prevented the outage entirely, or just shortened it? Explain your reasoning.

**Part C:** Design an alternative credential architecture that eliminates the synchronous dependency on the metadata service for credential refresh. Hint: think about how credentials could be refreshed proactively (before they expire) rather than reactively (when a request fails because credentials are expired).

---

## Exercise 10: Full Resilience Design — Fintech Transfer

You are designing a money transfer feature from scratch. Users can transfer money between accounts.

Requirements:
- Transfers must be exact-once (accidental double-debit is a regulatory and user-trust catastrophe)
- Transfers must complete or cleanly fail within 10 seconds
- System must support 1,000 transfers per second at peak
- Your bank integration API (the thing that actually moves money) has a P99 of 3 seconds

Design the complete resilience story across all five layers:

**Part A: Idempotency Key Design**
- What composes the key? (Which fields?)
- What is the TTL?
- Where is it stored and why?
- How do you handle the race condition when two transfer requests arrive simultaneously with the same key?

**Part B: Retry Strategy**
- How many attempts maximum?
- What is the backoff sequence (show the actual millisecond values)?
- Which error codes from the bank API do you retry on?
- Which error codes do you NOT retry on, and what do you return to the user instead?

**Part C: Circuit Breaker Configuration**
- What is the failure rate threshold that opens the circuit?
- What is the measurement window?
- How long does the circuit stay open before attempting half-open?
- What is your fallback behavior when the circuit is open? (You cannot just return an error — what do you tell the user and what do you do with their transfer request?)

**Part D: Backpressure Mechanism**
- What rate limiting mechanism do you use at the API gateway level?
- What are the token bucket parameters (capacity and refill rate)?
- What is your burst allowance?
- At what point do you start returning 429 errors vs. queuing requests?

**Part E: Monitoring — 5 Most Important Metrics**

For each metric: what is it measuring, what is the normal range, and at what value does the alert fire?

**Part F: Runbook — "Transfer Success Rate Below 95%"**

Write the first 10 steps of the on-call runbook for this alert. Steps should be specific and actionable — not "investigate the issue" but "go to dashboard X, check metric Y, if value is Z then do W."

---

# Putting It All Together: A Complete Resilience Design Walkthrough

Before you get to the Quick Reference Card, here is one complete worked example that ties every concept in the chapter together. Think of this as the template you carry into any system design interview.

**Scenario: A ride-sharing app's "Request a Ride" endpoint.**

This endpoint does a lot of work: it authenticates the user, finds nearby drivers, charges the user's payment method on file, creates a trip record, and sends a push notification to the assigned driver. Multiple external services are involved. Every step can fail.

---

## Step 1: Map the Dependencies

Before designing anything, list every external call:

1. Auth Service — validates the user's session token
2. Driver Location Service — finds drivers within 2 miles
3. Payment Service — charges the saved card
4. Trip Database — creates the trip record
5. Driver Notification Service — sends push to the driver's phone

Each of these is a promise that can be broken. Designing the happy path without designing the failure path for each of these is incomplete.

---

## Step 2: Classify Each Dependency by Criticality

Not every dependency has the same importance to the user. Classify them:

| Dependency | Can the ride happen without it? | Classification |
|---|---|---|
| Auth Service | No — we cannot serve an unauthenticated user | Critical — hard fail if unavailable |
| Driver Location Service | No — we cannot match a driver without location data | Critical — hard fail if unavailable |
| Payment Service | No — ride cannot proceed without payment authorization | Critical — hard fail if unavailable |
| Trip Database | No — we need a record of the trip for both parties | Critical — hard fail if unavailable |
| Driver Notification Service | Yes — driver has the app open anyway, they will see the match | Non-critical — degrade gracefully |

This classification drives every resilience decision that follows.

---

## Step 3: Apply the 5-Point Checklist to Each Dependency

**Auth Service:**
- Timeout: 200ms (auth is fast; if it takes longer than 200ms something is wrong)
- Retry: 2 attempts, 50ms backoff. Only retry on 503/504. Do NOT retry on 401 (bad token).
- Idempotency: auth checks are read-only, no idempotency key needed
- Circuit breaker: threshold 30% error rate, open for 30 seconds. Fallback: return 503 to user with "service temporarily unavailable"
- Monitoring: error rate, P99 latency, circuit state

**Driver Location Service:**
- Timeout: 500ms (location lookup involves geo-spatial queries)
- Retry: 2 attempts, 100ms backoff. Retry on 502/503/504.
- Idempotency: read-only, no idempotency key needed
- Circuit breaker: threshold 50% error rate, open for 60 seconds. Fallback: use last-known driver locations from cache (may be up to 30 seconds stale — acceptable)
- Monitoring: error rate, P99 latency, cache staleness

**Payment Service:**
- Timeout: 8 seconds (payment gateways are slower; 8s is below the user's browser timeout of ~10s)
- Retry: 3 attempts, exponential backoff (200ms, 400ms, 800ms), ±25% jitter. Retry on 408/502/503/504 ONLY. Do NOT retry on 400/402/422.
- Idempotency: **YES — critical.** Key: `ride-request-{user_id}-{request_timestamp_minute}`. Stored in a dedicated idempotency table. TTL: 24 hours. Passed to payment gateway as well.
- Circuit breaker: threshold 20% error rate (payment is too important to tolerate high error rates), open for 60 seconds. Fallback: queue the payment attempt, show user "payment processing — your ride will start shortly"
- Monitoring: success rate, P99 latency, idempotency hit rate (spike = client bug), circuit state

**Trip Database:**
- Timeout: 1 second (database writes should be fast)
- Retry: 3 attempts, 100ms/200ms/400ms backoff. Retry on connection errors and deadlocks.
- Idempotency: YES — the trip record uses the same idempotency key as the payment. If the server crashes after creating the payment but before creating the trip, the retry will find the payment already processed (via idempotency) and create only the trip record.
- Circuit breaker: threshold 40% error rate, open for 30 seconds. Fallback: queue the write to a separate durable log, apply asynchronously. Alert immediately — this is a data integrity risk.
- Monitoring: write success rate, P99 write latency, queue depth (if using async fallback)

**Driver Notification Service:**
- Timeout: 2 seconds
- Retry: 2 attempts, 500ms backoff. Retry on 503/504.
- Idempotency: YES, but for a different reason — duplicate push notifications (driver receives "new ride!" twice) are confusing. Key: `driver-notif-{trip_id}-{driver_id}`. TTL: 10 minutes.
- Circuit breaker: threshold 50% error rate, open for 30 seconds. **Fallback: do nothing.** The driver's app polls for assignments every 5 seconds — they will see the ride without the push.
- Monitoring: delivery rate, P99 latency, circuit state. NOTE: circuit breaker being open here should NOT page the on-call engineer — it should only log. This is non-critical.

---

## Step 4: Design the Backpressure Layer

"Request a ride" is an expensive operation. Even before touching any external service, you need to decide how many of these you can handle simultaneously.

Token bucket at the API gateway:
- Per-user rate limit: 3 ride requests per minute (prevents rapid-fire button taps)
- Per-city rate limit: 10,000 requests per minute (prevents a single city event from taking down other cities)
- Global rate limit: 100,000 requests per minute (platform-wide ceiling)

Concurrency limit at the payment service call:
- Maximum 500 simultaneous payment calls in flight across all servers
- Beyond 500: queue the request for up to 5 seconds, then fail with a friendly "service busy" message

Load shedding priority:
- ALWAYS serve: in-progress ride status checks (drivers need these to navigate)
- HIGH: new ride requests (revenue)
- MEDIUM: driver location browsing (pre-request map view)
- LOW: historical trip receipts, rating submissions
- SHED FIRST: analytics events, recommendation calls

---

## Step 5: Design the Monitoring Dashboard

Five panels on the dashboard, in order of importance:

**Panel 1: Ride Request Success Rate**
Normal: 99.5%+. Alert at 99%. Page at 98%.
Formula: successful_ride_creations / ride_request_attempts

**Panel 2: Payment Success Rate**
Normal: 99.8%+. Alert at 99.5%. Page at 99%.
This is separate from ride success rate — a payment failure is more severe than a driver matching failure.

**Panel 3: P99 End-to-End Latency**
Normal: under 3 seconds. Alert at 5 seconds. Page at 8 seconds.
This is the full time from "user taps Request" to "driver is matched and notified."

**Panel 4: Retry Rate by Service**
Normal: under 3% for any individual service. Alert at 10%. Page at 20%.
A spike here is an early warning of a dependency problem before it shows up in the success rate.

**Panel 5: Circuit Breaker State**
Any circuit opening on a CRITICAL service = immediate page.
Circuit opening on a NON-CRITICAL service = log + Slack notification, no page.

---

This walkthrough is the template. Every system design interview answer should have: dependency classification, the 5-point checklist applied per dependency, a backpressure layer, and a monitoring plan. The specific numbers change. The structure does not.

---

# Quick Reference Card

*Cut out or screenshot this section. It is designed to fit in your mental model before an interview.*

---

## Retry Decision Table

The single most common interview mistake: "I'll retry on any error." Here is the correct table:

| HTTP Error Code | Retry? | Reasoning |
|---|---|---|
| `429 Too Many Requests` | YES — after `Retry-After` delay | The server is explicitly telling you to try later |
| `503 Service Unavailable` | YES | Server temporarily down or overloaded |
| `502 Bad Gateway` | YES | Proxy or load balancer lost connection to backend |
| `504 Gateway Timeout` | YES | Proxy timed out waiting for backend |
| `408 Request Timeout` | YES | Request timed out — likely transient |
| `500 Internal Server Error` | MAYBE (once, with caution) | Could be a transient crash — but could also be your request triggering a bug. Retry once only. |
| `400 Bad Request` | NO | Your request is malformed. Retrying returns the same `400`. |
| `401 Unauthorized` | NO | Wrong credentials. Credentials do not fix themselves by retrying. |
| `403 Forbidden` | NO | Correct credentials, insufficient permissions. |
| `404 Not Found` | NO | Resource does not exist. It will not appear by retrying. |
| `422 Unprocessable Entity` | NO | Request format is valid but content is wrong. |

**Key rule:** If the error is about YOUR request being wrong (4xx), retrying will not help. If the error is about the SERVER being unavailable (5xx, timeouts), retrying might help.

---

## Backpressure Mechanism Selection Guide

When you need to limit load, choose the right mechanism for the situation:

| Situation | Right Mechanism | How It Works |
|---|---|---|
| Limit requests per user/tenant | **Token Bucket** | Each user has a bucket of tokens. Requests consume tokens. Bucket refills at the sustained rate. Burst is allowed until the bucket empties. |
| Limit simultaneous in-flight requests | **Semaphore / Concurrency Limiter** | A counter tracks active requests. New requests wait or fail if counter is at max. Thread pool is a common implementation. |
| Queue-based systems with variable processing time | **Queue Depth Threshold** | Monitor queue depth. Start shedding when depth exceeds 80% of max capacity. |
| Streaming data (bytes, not requests) | **Reactive Streams / Pull-based** | Consumer pulls data at the rate it can process. Producer does not push faster than consumer pulls. |
| Adaptive control that adjusts to load | **AIMD (Additive Increase, Multiplicative Decrease)** | Slowly increase sending rate when things are good. Cut rate in half immediately when congestion detected. Same algorithm as TCP. |

---

## Idempotency Implementation Checklist

Use this before shipping any API endpoint that changes state:

```
□ Every state-changing endpoint requires an Idempotency-Key header
□ Keys are stored in a database with TTL (7 days is a good default)
□ The idempotency result is stored ATOMICALLY with the operation
  (same DB transaction, not a separate write after the fact)
□ "Check then claim" is implemented as an atomic INSERT with
  unique constraint — not a read followed by a write
□ Replay responses include Idempotency-Replayed: true header
□ Keys are namespaced by user/tenant to prevent cross-user collisions
□ A TTL cleanup job runs regularly (daily) without table locks
□ The system is tested for the crash-between-steps scenario
```

---

## Circuit Breaker State Reference

```
┌─────────────────────────────────────────────────────┐
│                    CLOSED (normal)                   │
│  • All requests pass through to downstream          │
│  • Failures are counted in rolling window           │
│  • Transition to OPEN when error rate > threshold   │
└──────────────────────┬──────────────────────────────┘
                       │ error rate > 50%
                       ▼
┌─────────────────────────────────────────────────────┐
│                     OPEN (tripped)                   │
│  • NO requests reach downstream service             │
│  • All requests fail immediately (< 1ms)            │
│  • Fallback behavior executes                       │
│  • Wait for open_duration (30-60 seconds)           │
└──────────────────────┬──────────────────────────────┘
                       │ after open_duration
                       ▼
┌─────────────────────────────────────────────────────┐
│                  HALF-OPEN (testing)                 │
│  • ONE test request allowed through                 │
│  • Success → transition back to CLOSED              │
│  • Failure → return to OPEN (reset timer)           │
└─────────────────────────────────────────────────────┘
```

**When the circuit is OPEN, the fallback is everything.** Common fallbacks:
- Return cached data from the last successful response
- Return a simplified/degraded response (omit the feature that needs the dependency)
- Queue the operation for later processing
- Return a clear error with estimated recovery time

A circuit breaker with no fallback just converts "downstream error" to "our error" — it does not help users.

---

## The 5-Point Resilience Checklist

For every external service call in your system, verify all five points:

**1. Timeout**
- Is a timeout set?
- Is it shorter than the caller's timeout?
- Is it based on the actual P99 of the dependency (not a round number you guessed)?

**2. Retry**
- Is backoff exponential (not fixed)?
- Is jitter added (±25%)?
- Is there a maximum retry count (3-5)?
- Are retries only on the right error codes (not 400s)?
- Is the retry budget considered (what % of capacity do retries consume)?

**3. Idempotency**
- Does every state-changing call have an idempotency key?
- Is the key consistent across retries (not randomly generated each time)?
- Is the key stored with the operation atomically?

**4. Circuit Breaker**
- Is there a circuit breaker on the call?
- Is there a meaningful fallback when the circuit opens?
- Is the threshold set based on real error rate data (not a guess)?

**5. Monitoring**
- Is error rate for this call being tracked?
- Is P99 latency for this call being tracked?
- Is the retry rate for this call being tracked?
- Is circuit breaker state being tracked and alerting?
- Are the alerts actually going to someone who will act on them?

If you cannot check all 5 boxes for an external call, you have a gap in your resilience design.

---

## Key Numbers at a Glance

| Parameter | Typical Value | Warning if... |
|---|---|---|
| Max retry attempts | 3-5 | You set more than 5 |
| Initial backoff | 100ms | You set less than 50ms |
| Max backoff | 30 seconds | You set more than 60 seconds |
| Jitter range | ±25% | You have no jitter at all |
| Circuit error threshold | 50% | You set above 80% (too slow to trip) |
| Circuit open duration | 30-60 seconds | You set less than 15 seconds |
| Idempotency key TTL | 24 hours to 7 days | You set less than 1 hour |
| Rate limit burst | 2-10× sustained rate | Your burst equals your sustained rate |
| P99 alert threshold | 3-5× normal P99 | Your alert never fires OR fires constantly |
| Thread pool (I/O heavy) | CPU cores × 10 | You guessed without measuring |
| Thread pool (CPU heavy) | CPU cores × 2 | You set it the same as I/O heavy |

---

# Conclusion

## Three Concepts, One Complete Story

Retries, idempotency, and backpressure are not three separate topics that happen to appear in the same chapter. They are one complete story about how systems stay alive and correct under pressure.

Retries handle the reality that distributed systems have transient failures — network hiccups, brief overloads, momentary outages. Without retries, every transient failure becomes a user-visible error. With retries, most transient failures are invisible to the user.

Idempotency makes retries safe. Without idempotency, retries on state-changing operations cause double-charges, duplicate orders, and corrupted data. With idempotency keys, retrying a payment is no more dangerous than trying it once. The key links the attempt to its result, regardless of how many times the attempt is made.

Backpressure prevents retries from becoming the cause of the next failure. Without backpressure, a wave of retries during an overload creates a retry storm that amplifies the original problem into a full outage. With backpressure — token buckets, load shedding, circuit breakers — the system stays alive at degraded capacity instead of collapsing entirely.

You need all three. Missing any one breaks the chain. Retries without idempotency cause data corruption. Idempotency without retries means every transient failure reaches the user. Retries and idempotency without backpressure means your protective mechanism can become the thing that takes you down.

## Seeing the Problem Before It Happens

The hardest part of resilience engineering is not implementing any of these patterns — it is recognizing when you have missed one. Double-charges are invisible in your metrics until a customer calls. Retry storms look like "high traffic" in your dashboards until you check the retry rate breakdown. Cascading failures look like "Service X is having issues" until you trace the full dependency chain and see that Service X was actually fine — it was Service Y's slowness that filled X's thread pool that blocked X's callers.

Building the monitoring to see these problems is as important as implementing the solutions. A 20% retry rate on a service is a symptom that demands investigation, not a configuration value to tune. A circuit breaker opening three times per hour is telling you something is wrong, not a threshold to raise. An idempotency key hit rate of 5% (normally below 1%) is a client bug hiding in your metrics.

The patterns in this chapter give you both the solutions and the measurements you need to know when those solutions are working.

## The Three Questions

Every engineer who has survived a 3am double-charge incident, a retry storm taking down production, or a cascading failure that started with one slow database query carries permanent intuition about these patterns. That intuition says: I will never ship a payment endpoint without an idempotency key. I will never configure retries without checking the amplification math. I will never design a service without asking what happens when each of its dependencies gets slow.

This chapter gives you the intellectual foundation for that intuition before you need the hard-won production experience. When you are next designing a system, carry three questions into every design session:

**"What happens if this call fails?"** — the answer should include: retry policy, circuit breaker threshold, and fallback behavior. If you find yourself saying "we'll add error handling later," that is the gap.

**"What happens if this call succeeds but we never find out?"** — the answer should include: idempotency key design, state machine transitions, and crash recovery behavior. If you find yourself saying "that probably won't happen," that is the gap.

**"What happens if we receive 10× traffic right now?"** — the answer should include: which features degrade first, what the token bucket parameters are, and how long the system stays alive while auto-scaling catches up. If you find yourself saying "we'll scale up," that is the gap.

Answering these three questions before you write the first line of code is the difference between a system that survives its first real incident and one that teaches you these patterns the hard way.

## A Final Note on Intuition vs. Knowledge

There is a difference between knowing these patterns and having intuition for them. Knowledge is what you have after reading this chapter — you can define a token bucket, explain what jitter does, describe the circuit breaker state machine. That knowledge is necessary but not sufficient.

Intuition is what you have after you have designed a system, watched it fail in production in a way you did not predict, traced the cascade back to a missing idempotency key or a retry policy with no jitter, fixed it at 3am, and then spent the next month explaining what happened to everyone who asked. Intuition means the question "what happens when this call fails?" is not a checklist item — it is an automatic reflex that fires before you have finished drawing the box on the whiteboard.

You build intuition through practice: through the 30 questions, the 10 exercises, the timed mock interviews, the habit of tracing failure paths before happy paths. Each practice session is a low-stakes version of the 3am incident. The goal is to have the reflex so firmly established that when you sit across from an interviewer and they say "walk me through what happens during a cascading failure in your design," you already know — because you designed for it before they had to ask.

---

## Bonus: Common Interview Phrases That Signal L6 Thinking

In an interview, the words you choose matter. Here is a list of phrases that signal you have thought carefully about resilience — and the phrases that signal you have not.

### Phrases That Signal Strong Thinking

**"Before I design the happy path, let me note the failure modes I need to handle..."**
This signals you think about failure proactively, not reactively. You say this before drawing any boxes.

**"I would put an idempotency key here because the client will retry on timeout, and without one we risk double-processing."**
This signals you understand WHY idempotency exists, not just what it is.

**"The timeout I set here needs to be shorter than my caller's timeout. If the caller gives up before my timeout fires, I am holding a thread for no reason."**
This signals you think about timeouts in context, not in isolation.

**"A circuit breaker is only useful if I have a fallback. Let me design the fallback first, then configure the breaker."**
This is a rare signal — most candidates describe circuit breakers without mentioning fallbacks.

**"A 15% retry rate is not something to tune around — it is a signal that 15% of my first-attempt requests are failing. The real question is why."**
This signals you treat metrics as symptoms to investigate, not parameters to configure.

**"This queue helps during a spike, but it does not increase capacity. If traffic is sustainably 3× my throughput, the queue just delays the rejection. I need load shedding too."**
This signals you understand the limits of queuing.

**"Let me trace through what happens if THIS service calls THAT service and that service is slow..."**
Actually tracing the cascade in your own design, unprompted, is a strong signal.

---

### Phrases That Signal Gaps

**"I'll add retry logic."**
Without specifying which errors, how many attempts, what backoff, whether idempotency is needed — this is incomplete.

**"We can handle spikes by auto-scaling."**
Auto-scaling takes minutes. This does not address what happens in the first 3 minutes.

**"The queue will absorb the load."**
A queue absorbs bursts. It does not absorb sustained overload. This shows the candidate has not thought about queue saturation.

**"I'll use a circuit breaker."**
Without saying what the fallback is, this is not a complete answer.

**"That's unlikely to happen."**
Any time you dismiss a failure scenario as unlikely, the interviewer hears: "I have not thought about this."

**"We'll add monitoring later."**
Monitoring is not optional — it is how you know whether any of your other choices are working.

---

## Bonus: Interview Calibration Self-Assessment

After your next mock interview (or after reading through a system design problem), score yourself on this rubric. Be honest.

| Dimension | L4 Signal | L5 Signal | L6 Signal |
|---|---|---|---|
| Failure mode awareness | Mentions failure modes only when prompted | Mentions a few failure modes without prompting | Identifies all major failure modes during initial design, before drawing boxes |
| Retry design | "Add retries" | Specifies attempts and backoff | Specifies attempts, backoff, jitter, which error codes, retry budget, and interaction with idempotency |
| Idempotency | Not mentioned | Mentions "make it idempotent" | Designs the specific key, storage, atomicity, and TTL |
| Circuit breaker | Not mentioned | Mentions circuit breaker | Designs threshold, recovery time, AND fallback behavior |
| Backpressure | Not mentioned | Mentions "rate limiting" | Designs the specific mechanism (token bucket vs. concurrency limiter), parameters, and what happens when limits are hit |
| Monitoring | "Add alerts" | Lists a few metrics | Lists specific metrics with specific thresholds and explains what each one diagnoses |
| Degraded modes | Not considered | Brief mention | Explicitly designs what works when each dependency fails |
| Cascading failures | Not considered | Mentions "dependency can fail" | Actually traces the failure through the system, names which services fail in which order |

If you score mostly L5 with one or two L4s: you are close. Focus your practice on the dimensions where you dropped.

If you score mostly L4-L5: practice talking through failure modes out loud before describing the happy path. The habit of "let me think about failure first" is what separates the levels.

---

## Bonus: Worked Example for Question 3 (Retry Budget Math)

Many candidates struggle with the math portion of retry budget questions. Here is a fully worked example so you know what the expected level of detail looks like.

**Setup (from Question 3):**
- Traffic: 10,000 requests/second
- Error rate: 5%
- Retry policy: up to 3 retries per failure
- Retry budget: 10% of total request capacity

**Part A: How many retry requests per second?**

First calculate failures per second:
10,000 req/sec × 5% error rate = 500 failures/second

Each failure gets up to 3 retries. In the worst case (all retries also fail), you send:
500 (original failures) × 3 retries = 1,500 retry requests/second

Your 10% retry budget:
10,000 req/sec × 10% = 1,000 retry requests/second allowed

Verdict: 1,500 retry req/sec exceeds your 1,000 req/sec budget. You are over budget.

**Part B: At what error rate does the budget tip?**

Set up the equation. You want: (error_rate × 10,000) × 3 retries ≤ 1,000

Rearranging:
error_rate × 30,000 ≤ 1,000
error_rate ≤ 1,000 / 30,000
error_rate ≤ 3.33%

Answer: if your error rate exceeds 3.33%, a 3-retry policy generates more than 10% retry overhead.

**What does this mean in practice?**

It means your retry policy is designed for a world where your error rate is below 3.33%. At 5% error rate, you have two options:

Option 1: Reduce retries to 2 (instead of 3). New math: 500 × 2 = 1,000 — exactly at budget.

Option 2: Fix the root cause. Why is your error rate 5%? That is the real problem. Tuning retries is the wrong answer when the right answer is "stop failing 500 requests per second."

This is the L6 answer to retry budget questions: the math tells you what your retry policy can sustain, and the result tells you whether you need to fix your retry config or fix your system.

---

## Bonus: Worked Example for Exercise 3 (Circuit Breaker Walkthrough)

**Circuit breaker configuration:**
- failure_threshold: 50% error rate
- window: 10 seconds
- open_duration: 30 seconds
- half_open_test: 1 request

**T=0 to T=10 (10% error rate):**
100 requests, 10 failures. Error rate = 10%. Threshold is 50%. Circuit stays CLOSED. Everything passes through normally. The 10 failures are counted but do not trigger the breaker.

State at T=10: **CLOSED**

**T=10 to T=20 (60% error rate):**
100 requests, 60 failures. Error rate = 60%. This exceeds the 50% threshold. The circuit OPENS.

The exact moment depends on implementation — most circuit breakers trip mid-window when the threshold is crossed, not at the end. By T=20, the circuit is definitely open.

State at T=20: **OPEN**

**T=20 to T=50 (open period, 30 seconds):**
No requests reach the downstream service. All client requests receive an immediate failure response (under 1ms). The circuit breaker is waiting out its open_duration of 30 seconds.

State throughout: **OPEN**

**T=50 (one test request):**
The 30-second open period is over. The circuit enters HALF-OPEN. One test request is sent to the downstream service. The test succeeds. The circuit closes.

State at T=50 (after test): **CLOSED**

**T=50 to T=60 (5% error rate):**
100 requests, 5 failures. Error rate = 5%, well below 50% threshold. Circuit stays CLOSED.

State at T=60: **CLOSED**

**Part B — Comparing with vs. without circuit breaker:**

During the OPEN period (T=20 to T=50), 30 seconds of traffic is being served.

Assume 100 concurrent users. Without a circuit breaker, those users hit the failing downstream service. That service is responding with 60% errors and — this is key — the errors take 3 seconds to arrive (the service is timing out, not immediately failing). 

Without circuit breaker:
- Average response time: 0.4 × (fast response, maybe 100ms) + 0.6 × (3,000ms timeout) = 40ms + 1,800ms = 1,840ms average
- Threads held per second: 100 users × 3 seconds per failure = up to 300 threads held simultaneously (if thread pool is 100, you have thread exhaustion and all requests start queueing)

With circuit breaker open:
- Average response time: < 1ms (immediate failure, no network call made)
- Threads held: 0 (the failure is returned before acquiring any downstream connection)
- Thread pool: fully available for other work

The circuit breaker's OPEN state is strictly better for the system during a dependency outage. The cost is that 100% of requests fail instead of 40% — but they fail instantly and free resources instead of failing slowly and holding resources.

This is the counterintuitive insight: **more errors, faster, is better than fewer errors, slower**, during an outage. The fast failures preserve your thread pool, which lets other parts of your system keep functioning.

---

## Bonus: How to Use These Questions in Self-Study

The 30 questions and 10 exercises are designed to be worked in a specific order depending on your experience level.

**If you are new to distributed systems (Part A and B of this chapter are still fresh):**
Start with Section A (Questions 1-6) and Section B (Questions 7-12). These build the foundational math and mental models. Do not try to answer from memory — work through each calculation explicitly. The habit of showing math in interviews is itself a signal of rigor.

**If you have some experience but interviews are uncomfortable:**
Section C (Questions 13-18) and the Exercises are your focus. These require synthesizing multiple concepts in one answer. Practice saying your answer out loud — the words matter as much as the logic. Most technical candidates know the answer but cannot articulate it under pressure.

**If you are preparing for L6/staff-level interviews specifically:**
Section D (Questions 19-24) and Section E (Questions 25-30) are where L5 and L6 candidates diverge. L5 answers correctly but incompletely. L6 answers include the second-order effects, the monitoring, the degraded modes, and the "what I would have done differently" analysis. Practice adding one more layer of depth to each answer than feels comfortable.

**For all levels:**
Exercise 8 (the timed interview practice) should be done multiple times — ideally weekly. The first time will feel rough. The third time will feel natural. The fifth time you will be filling in details you did not think to mention in the first four attempts. Fluency under time pressure is a skill that only comes from practice, not from reading.

---

*End of Chapter 23, Part D.*

*Chapter 23 complete: Part A (Core Concepts and Analogies), Part B (Deep Dives and Real Incidents), Part C (Design Patterns and Production Implementation), Part D (Interview Calibration, Practice Questions, and Quick Reference).*
