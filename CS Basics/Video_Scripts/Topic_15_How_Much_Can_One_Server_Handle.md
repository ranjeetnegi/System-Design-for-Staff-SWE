# How Much Can One Server Handle? (Rough Numbers)

## Video Length: ~4-5 minutes | Level: Beginner

---

## Hook (20-30 seconds)

One waiter. 10 tables. They're busy but okay. Smiling. Food arrives on time. Orders are correct. Customers are happy. The waiter is in control.

Same waiter. Add 20 more tables. Now 30 tables. The waiter is running. Sweating. Making mistakes. Forgetting orders. "Where's my biryani?" "I'm sorry, one minute!" "You said that 10 minutes ago!" Quality drops. Fast.

Add 50 tables? The waiter collapses. Mentally. Physically. Customers leave. They don't pay. They write bad reviews. "Worst service ever." The waiter had limits. We ignored them. Disaster.

A server is like that waiter. It has limits. Ignore them, and everything crashes. Know them, and you build systems that actually work. Let me give you the numbers.

---

## The Big Analogy

Let's live in the restaurant. **The Waiter.**

One good waiter can handle maybe 5-10 tables well. They remember orders. They're polite. Food arrives hot. Everyone's happy.

Give them 20 tables? Quality drops. Orders get mixed up. "I asked for no onions!" "Sorry, sorry." The waiter is stressed. Mistakes happen. Some customers leave unhappy.

Give them 50 tables? Collapse. Nobody gets served properly. The waiter can't be everywhere. Can't remember everything. The kitchen gets backed up. The waiter gets backed up. Customers leave. The waiter quits. Or has a breakdown. Limits. We all have them.

**A server is the same.** It has limits. It can only do so much at once. Arms. Memory. Speed. CPU. RAM. Network. Disk. Each one can be the bottleneck. Hit any limit? Slowdown. Errors. Crash. Know the limits. Respect them. Plan for them.

---

## Breaking Down Server Resources

Let me walk you through what a server actually has. Think of it like the waiter's body.

**CPU (the brain)** — How much thinking and computing it can do. Complex calculations? CPU. Parsing JSON? CPU. Business logic? CPU. Hit 100% CPU? Everything slows down. Requests queue up. Timeouts.

**RAM (desk space)** — How much it can hold in its head at once. Active data. Sessions. Cache. Run out of RAM? Server starts swapping to disk. Or crashes. "Out of memory." Game over.

**Network (how fast food can be carried)** — How much data it can send and receive per second. Bandwidth. Too many users? Network saturated. Slow responses. Dropped connections.

**Disk (storage room)** — How fast it can read and write. Database on disk? Disk speed matters. Logs? Disk. File storage? Disk. Slow disk = slow everything that touches it.

EACH can be the bottleneck. Not just one. Any one. The weakest link sets the limit. Often it's the database. Sometimes CPU. Sometimes network. Know all of them.

---

## A Second Way to Think About It

Think of a server as a factory. Raw materials come in (requests). Work happens (processing). Product goes out (responses). The factory has machines. Each machine has a speed. The slowest machine determines how fast the whole factory runs. That's your bottleneck. Find it. Fix it. Or add more of that machine.

---

## Now Let's Connect to Software

**Rough numbers.** Ballpark! Real numbers depend on your app. Your code. Your database. Measure. Don't guess. But here's a starting point:

| Type of request | Rough capacity per server | Why |
|-----------------|---------------------------|-----|
| Simple API (from memory, cached) | ~10,000 req/sec | Almost no work. Just serve from RAM. Fast. |
| API + database query | ~1,000 req/sec | Each request hits DB. DB is slower. Bottleneck. |
| API + heavy computation | ~100 req/sec | CPU-bound. Math. Processing. Takes time. |
| File upload/download | ~50 req/sec | Network and disk bound. Big data. Slow. |

**Why these matter:**
- 1 server, simple API → maybe 5-10K QPS. Need more? Add servers.
- 1 server, database queries → maybe 500-1K QPS. Database is often the limit. Need more? Shard. Replicate. Cache.
- 1 server, heavy computation → maybe 50-200 QPS. CPU is the limit. Need more? Add servers. Or optimize the algorithm.
- Know your limits BEFORE you hit them. Not after. Load test. Measure. Plan.

---

## Let's Look at the Diagram

```
ONE WAITER (SERVER) - LIMITS

    [Waiter]  →  Can serve ~10 tables
                     |
                     v
    Too many tables? OVERLOAD
                     |
                     v
    ┌────────────────────────────────────┐
    │  SERVER RESOURCES:                  │
    │  • CPU: compute power (brain)      │
    │  • RAM: memory (desk space)        │
    │  • Network: bandwidth (speed)      │
    │  • Disk: read/write (storage room) │
    └────────────────────────────────────┘
                     |
    Simple request:  ████░░░░░░  ~10K/sec  (from cache)
    DB query:        ██░░░░░░░░  ~1K/sec   (DB bottleneck)
    Heavy compute:   █░░░░░░░░░  ~100/sec  (CPU bottleneck)
    File transfer:   █░░░░░░░░░  ~50/sec   (network/disk)
```

The waiter has one set of limits. The server has four resources. Each can max out. Simple requests use little of each. Heavy requests use a lot of one. Or many. Find your bottleneck. That's your real limit.

---

## Real Examples (2-3)

**Startup story.** You build an app. One server. Works great in testing. 10 users. Beautiful. Fast. You're proud.

Launch day. 1,000 users hit at once. Server CPU at 100%. Memory full. Site goes down. "502 Bad Gateway." "Service Unavailable." What happened? You never checked: "How many requests can this box handle?" You assumed. Assumption killed you. Next time: load test. Find the limit. Plan for 2x that. Or 10x if you expect growth.

**The database bottleneck.** Your app server can handle 5,000 requests/sec. Great! You're confident. But each request hits the database. Database can only do 500 queries/sec. Your app is fine. Your DB is drowning. Everything slows down. Timeouts. Errors. The app server is bored. The database is the bottleneck. The weakest link. Fix the DB. Or cache. Or add read replicas. Know where the limit is.

---

## Let's Think Together

Here's a question. Pause. Think.

**If one server handles 1,000 QPS and you expect 10,000 QPS, how many servers do you need?**

Let me walk through it. 10,000 ÷ 1,000 = 10. So you need 10 servers. At minimum. But what about peak? Maybe 2x? 20,000 QPS at peak? You need 20 servers. What about headroom? Failover? Maybe one server dies. You want 11 or 12 servers minimum. Don't run at 100% capacity. Run at 60-70%. Leave room. For spikes. For growth. For failures. So 10,000 QPS ÷ 1,000 per server = 10. Add 20% headroom = 12 servers. That's your number. Simple math. But you need to know the "1,000 per server" first. Measure. Load test. Then scale.

---

## What Could Go Wrong? (Mini-Story)

Your app works. One server. 500 QPS. Fine. You add features. More users. 1,000 QPS. Server is at 80%. Okay. 2,000 QPS. Server is at 100%. Sometimes it spikes to 2,500. Timeouts. Errors. "What's wrong?" You check. CPU maxed. Memory maxed. You need to add a server. But you don't have one ready. You scramble. Spin up a new instance. By the time it's ready, the spike is over. But users saw errors. Some left. Next time: plan ahead. Know your limit. Add capacity before you need it. Not during. Not after. Before.

---

## Surprising Truth / Fun Fact

Netflix has 100,000+ servers across the world. 100,000. Think about that. They stream to hundreds of millions of users. Multiple regions. Multiple copies of content. Redundancy. Scale. When we talk about "one server," we're talking about the building block. The unit. Netflix has 100,000 of those units. Your app might need 1. Or 10. Or 100. But the principle is the same. One server has limits. More servers = more capacity. Know the limits of one. Then multiply.

---

## Quick Recap

- One server has limits—CPU, RAM, network, disk. Each can be the bottleneck
- Rough numbers: ~10K simple requests/sec, ~1K with DB, ~100 heavy compute
- The actual number depends on your app—measure, don't guess
- One server = one waiter. Too many "tables" = overload
- The weakest link (often DB) sets your real limit. Find it. Fix it.
- Plan for 2x or more. Add headroom. Don't run at 100%

---

## One-Liner to Remember

> One server is like one waiter. It has limits. Know them before you overload.

---

## Next Video

We know servers have limits. But what's happening INSIDE a server? What's a process? A thread? Next: **Process and Thread**—the kitchen and the chefs. One kitchen, many chefs. Let's go!
