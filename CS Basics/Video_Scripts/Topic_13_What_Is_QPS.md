# What Is "QPS" or "Throughput"?

## Video Length: ~4-5 minutes | Level: Beginner

---

## Hook (20-30 seconds)

Picture a highway. Rush hour. Hundreds of cars. Maybe thousands. And there's ONE toll booth. One. One person taking money. One lane. Cars line up. The queue grows. 500 meters. 1 kilometer. 2 kilometers. Horns honking. People angry. Some drivers give up. They take another route. They never come back.

Now add a second booth. Then a third. Then ten. Suddenly cars flow. Less waiting. Less rage. Traffic moves.

That flow? How many cars pass per second? In software, we call it **QPS**—Queries Per Second. And it decides whether your app survives or dies. Let me explain.

---

## The Big Analogy

Let's live in the toll booth story.

**ONE toll booth.** One car passes every 2-3 seconds. Maybe 20-30 cars per minute. Rush hour arrives. 1000 cars need to pass. How long does the queue get? 1000 cars ÷ 30 per minute = 33 minutes of waiting. The queue stretches 2 kilometers. People get angry. They take another route. They use a different app. They leave your product. That's what happens when your QPS is too low.

**Add more booths.** 10 booths = 10 cars at once. 300 cars per minute. 10x more flow! Queue shrinks. 100 booths? Traffic flows like a river. Thousands of cars per minute. No waiting. Happy users.

The number of cars passing through per second? That's **throughput**. How much work gets done in a given time. In software: QPS. Queries per second. How many requests can your system handle per second? That number decides everything.

---

## A Second Way to Think About It

**Supermarket checkout.** One cashier. They scan items. Maybe 10-15 items per minute. That's their throughput. Lunch rush. 100 customers. One cashier. Each customer has 20 items. 100 × 20 = 2000 items. 2000 ÷ 10 per minute = 200 minutes. Over 3 hours of waiting! Nobody has that kind of time. Customers leave. They go to another store.

Add 5 cashiers? 50 items per minute. Queue moves. Add 10? 100 items per minute. Flow is smooth. But here's the thing: you can't add 1000 cashiers. Space is limited. Budget is limited. Same with servers. You can add more—but there's a limit. Cost. Complexity. You optimize. You find the right number.

---

## Now Let's Connect to Software

**QPS = Queries Per Second.** How many requests can your system handle per second? That's QPS. Sometimes we say "RPS" (Requests Per Second) or "TPS" (Transactions Per Second). Same idea. Different words. How many things can pass through per second?

**Throughput** = The total amount of work done. Could be:
- Requests per second (QPS/RPS) — most common
- Bytes per second (network throughput)
- Items processed per minute

**Difference:** QPS is specific. Usually one type of request. "Our API handles 1000 QPS." Throughput can be broader. "Our system throughput is 50 GB per second." Both matter. QPS = capacity for requests. Throughput = capacity for work.

High QPS = your system can serve many users at once. Low QPS = bottleneck. Users wait. Or get errors. Or leave. Simple as that.

---

## Let's Look at the Diagram

```
TOLL BOOTH = SERVER

    1 BOOTH:                    10 BOOTHS:
    Car → [Booth] → Out         Car → [Booth][Booth][Booth]... → Out
    ~1 car / 2 sec              ~10 cars / 2 sec
    Low QPS                      High QPS!
    Queue grows                  Queue shrinks


    ┌─────────────────────────────────────────────┐
    │  QPS = Cars (Requests) passing per second   │
    │                                             │
    │  More booths (servers) = More QPS           │
    │  Bigger bottleneck = Lower QPS              │
    │  Queue too long = Users leave (churn)       │
    └─────────────────────────────────────────────┘
```

One booth: cars pile up. Requests pile up. Same thing. Ten booths: flow increases. Add servers, flow increases. The bottleneck—the slowest part—sets your QPS. Find it. Fix it. Or add more of it.

---

## Real Numbers (Rough)

What can real systems handle?

- **A typical web server:** 1,000 - 10,000 QPS. Simple API, from memory, good code.
- **A database:** 1,000 - 5,000 QPS. Reads. Writes are lower. Complex queries lower.
- **Redis (cache):** 100,000+ QPS. In-memory. Crazy fast. That's why we use caches.
- **A single API with database:** Maybe 500 - 2,000 QPS. Depends on query complexity.

These are ballparks. Your app is different. Measure. Don't guess. But now you have a sense. 100 QPS = small. 10,000 QPS = serious. 100,000 QPS = you need a team, a lot of servers, and good architecture.

---

## Real Examples (2-3)

**Black Friday.** An e-commerce site normally gets 1,000 requests per second. Fine. One server. Maybe two. Works. Then Black Friday. Sales! Discounts! 50,000 requests per second. If the site was built for 1K QPS? Crash. Timeout. "Site unavailable." Lost millions. Embarrassing. If they scaled up? More servers = more "toll booths" = higher QPS. Site stays up. Sales happen. Everyone wins. QPS isn't just a number. It's capacity. Plan for it.

**Netflix.** Peak hours. Millions watching. Their system handles hundreds of thousands of QPS. Maybe more. They need it. One movie streaming = many requests. Recommendations. Thumbnails. Playback. All those requests. They plan for peak. They add capacity before it hits.

---

## Let's Think Together

Here's a question. Pause. Think.

**Your system handles 500 QPS. Black Friday brings 5,000 QPS. What happens?**

Let me walk through it. 5,000 ÷ 500 = 10x. You're getting 10 times more traffic than you can handle. What happens? Queue builds up. Requests wait. And wait. Timeouts. Users get "Connection timed out" or "503 Service Unavailable." Some requests never complete. Users leave. They go to Amazon. They go to Flipkart. You lose the sale. You lose the customer. Maybe forever.

What do you do? Add more servers. 10x more? Now you handle 5,000 QPS. Or use a cache—reduce the load on your database. Or both. Plan for peak. Know your QPS. Scale before you need it. Don't wait for the crash.

---

## What Could Go Wrong? (Mini-Story)

Your app works great. 100 users. Maybe 50 QPS. No problem. One server. Smiling.

You launch. You get featured in the App Store. You go viral. 10,000 users. 5,000 QPS. Your single server? It can maybe do 500 QPS. Tops. What happens? Everything falls over. Database overloaded. CPU at 100%. Memory full. "500 Internal Server Error" for everyone. All at once.

You're debugging at 2 AM. Your phone is blowing up. "App is down!" "Can't login!" "What's wrong?!" You're adding servers. Frantically. Too late. Users already left. Bad reviews. "Unreliable." "Crashes all the time." You didn't plan for QPS. You didn't add "toll booths." Now you're in crisis mode. Don't be that person. Know your QPS. Plan for peak. Add capacity before you need it.

---

## Surprising Truth / Fun Fact

One server can often handle 1,000-10,000 simple requests per second. That sounds like a lot. But 1 million users, each making 10 requests per day? That's 10 million requests per day. 10M ÷ 100,000 seconds ≈ 100 QPS average. Peak 5x = 500 QPS. One server might handle it. But 10 million users? 100M requests per day. 1,000 QPS average. 5,000 QPS peak. Now you need multiple servers. Scale creeps up fast. Small numbers become big numbers. Orders of magnitude. Again.

---

## Quick Recap

- **QPS** = Queries Per Second (how many requests your system handles per second)
- **Throughput** = total work done per unit of time (requests, bytes, items)
- Analogy: Toll booths. More booths = more cars per second = higher QPS
- Low QPS = bottleneck = slow app or crashes. Users leave
- Scale = add more "booths" (servers) to increase QPS. Plan for peak.

---

## One-Liner to Remember

> QPS = how many requests pass through per second. Like cars at a toll booth. More booths = more flow.

---

## Next Video

We can handle lots of requests. But what if the system goes DOWN? How much downtime is "acceptable"? Next: **What does 99.9% Availability mean?**—a shop that's open almost always. Almost. Let's dive in!
