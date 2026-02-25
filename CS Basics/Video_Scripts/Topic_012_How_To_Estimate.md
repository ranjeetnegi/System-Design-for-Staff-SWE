# How to Estimate: Users, Requests Per Second

## Video Length: ~4-5 minutes | Level: Beginner

---

## Hook (20-30 seconds)

You're planning a birthday party. Your kid is turning 7. You need to buy cake. How much? You guess "enough for 10 people." Easy.

But what if 50 people show up? Disaster. No cake. Angry guests. Kids crying. Your reputation ruined.

Now imagine this in software. You build a system for 100 users. Simple. Clean. Works great in testing. Launch day comes. 100,000 users show up. Your server melts. Your app crashes. Your boss is furious. Your investors are asking questions.

This is why estimation matters. You don't need to be exact. You don't need the perfect number. You just need to be in the RIGHT ballpark. Close enough to not crash. Close enough to not waste millions on over-provisioning. Let me show you how.

---

## The Big Analogy

Let's live in the birthday party for a minute. Your kid is turning 7. You need to plan.

**How many friends?** 10? 50? 200? This changes EVERYTHING. If you plan for 10 and 200 show up? No cake. No chairs. No space. Disaster. If you plan for 200 and only 10 come? Waste of money. Huge cake. Empty chairs. Awkward.

**How much cake?** 10 friends = 1 cake. 50 = 3 cakes. 200 = you need a bakery. You need to ORDER in advance. You can't guess on the day.

**How many chairs?** 10 friends = living room. Push the couch. Fine. 50 = rent a hall. 200 = rent a park. Different world.

**How many plates?** Same idea. Cups. Forks. Napkins.

**What about food?** 10 = sandwiches and chips. 50 = need proper catering. 200 = food trucks. Different scale.

**Drinks?** 10 = a few bottles. 50 = coolers. 200 = you need a drinks vendor.

**Parking?** 10 = street is fine. 50 = need to warn neighbors. 200 = need a parking lot.

**Music?** 10 = Bluetooth speaker. 200 = DJ. Sound system.

**Neighbors complaining?** 10 = no problem. 200 = you need to tell them. Maybe get permission.

See? One number—how many guests—changes EVERYTHING. You don't need the exact count. But you need the right ballpark. 10 vs 50 vs 200. Completely different planning.

**The goal is to get close enough.** Not exact. Just the right ballpark. In software? Same thing.

---

## A Second Way to Think About It

Replace "friends" with "users." Replace "cake" with "servers." Replace "chairs" with "database connections." Replace "food" with "bandwidth." Same logic. One number changes everything.

---

## Now Let's Connect to Software

When building a system, ask these questions:

1. **How many users do we have?** (Total registered users)
2. **How many are active daily?** (DAU - Daily Active Users)
3. **How many requests per second?** (QPS)
4. **How much data per day/month/year?** (Storage)

Here's a simple trick. Round to powers of 10. Don't calculate 86,400 seconds in a day. Use 100,000. Close enough. Easier math. Your estimates will be in the right ballpark. That's what matters.

Example:
- 10M total users
- 10% active daily = 1M DAU
- Each user makes 10 requests/day = 10M requests/day
- 10M requests ÷ 100,000 seconds ≈ 100 requests/second
- Peak time (2x to 5x average) = 200-500 requests/second

Simple math. No calculator needed. Just rough numbers. Ballpark.

---

## Step-by-Step: Estimate Twitter

Let's walk through a real example. Twitter-level scale.

- **300M total users** (rough, for the example)
- **50M DAU** — about 15-20% use it daily
- **Reads vs Writes:** People read way more than they write. Say each user reads 5 tweets and writes 0.5 tweets per day on average.

**Reads:**
- 50M × 5 = 250M reads per day
- 250M ÷ 100,000 sec ≈ 2,500 reads per second average
- Peak (lunch, evening) = 5x = ~12,500 reads per second

**Writes:**
- 50M × 0.5 = 25M writes per day
- 25M ÷ 100,000 ≈ 250 writes per second average
- Peak = 5x = ~1,250 writes per second

See? We treated reads and writes separately. They're different. Reads are 10x more. Your architecture needs to handle that. Caching for reads. Different scaling for writes. Estimation tells you what to build for.

---

## Let's Look at the Diagram

```
ESTIMATION FLOW (Birthday Party → Software)

Party:                          Software:
┌───────────────┐               ┌────────────────────┐
│ How many       │               │ Total users?        │
│ friends?       │───────────►   │ 10 million          │
├───────────────┤               ├────────────────────┤
│ How many       │               │ Daily active users?  │
│ will come?     │───────────►   │ 10% = 1 million     │
├───────────────┤               ├────────────────────┤
│ How much       │               │ Requests per second? │
│ cake?          │───────────►   │ ~100-500 QPS        │
├───────────────┤               ├────────────────────┤
│ How many       │               │ How much storage?    │
│ chairs?        │───────────►   │ ~1 TB/month?        │
└───────────────┘               └────────────────────┘

QUICK MATH CHEAT SHEET:
┌─────────────────────────────────────┐
│ 1 day   = ~100,000 seconds (round!) │
│ 1 month = ~2.5 million seconds      │
│ 1 year  = ~30 million seconds       │
│                                     │
│ Rule: daily_requests ÷ 100,000      │
│       ≈ average QPS                 │
│ Peak QPS ≈ 2x to 5x of average     │
└─────────────────────────────────────┘
```

Left side: party planning. Right side: software. Same flow. How many? How active? How much capacity? How much storage? Map it. Step by step.

---

## Real Examples (2-3)

**Food delivery app (Zomato/Swiggy):**
- India has ~50M food delivery users
- Maybe 20% order on a busy day = 10M orders/day
- Each order: search (5 queries) + place order (1) + track (10 checks) ≈ 16 requests
- 10M × 16 = 160M requests/day
- 160M ÷ 100,000 ≈ 1,600 QPS average
- Peak (lunch/dinner) = 5x ≈ 8,000 QPS

Now you know: you need servers for ~8,000 requests/second at peak. Very different from building for 100 QPS!

---

## Let's Think Together

Here's a question. Pause. Think.

**Estimate storage for WhatsApp messages in India for one year.**

Let's walk through it. India has about 500M WhatsApp users. Say each user sends 20 messages per day. 500M × 20 = 10 billion messages per day. Per day!

Each message: maybe 100 bytes on average (text). 10 billion × 100 = 1 trillion bytes = 1 TB per day. Per DAY. For just India. For one year? 365 TB. That's a lot. You need to think about storage. Compression. Archival. Deletion policies. Estimation tells you the problem is huge. Now you plan for it.

---

## What Could Go Wrong? (Mini-Story)

**Healthcare.gov.** The US government health insurance website. Launch day. 2013. They expected a few thousand users. Maybe 10,000. Maybe 50,000.

Millions showed up. Day one. The site crashed. For weeks. People couldn't sign up. News everywhere. Embarrassing. Expensive. Politicians were angry. Engineers were debugging at 3 AM. Why? Bad estimation. They built for the wrong ballpark. Off by 100x. Maybe 1000x.

**Your startup.** You estimate 100 QPS. Reality: 10,000 QPS. Your system crumbles. Database overloaded. "502 Bad Gateway" for everyone. Users leave. Same story. Different scale.

**Tip:** Always estimate. Then ask: "What if I'm wrong by 10x? Can my system survive?" Plan for that. Have headroom. Don't build exactly for your estimate. Build for 2x. Or 5x. Give yourself buffer.

---

## Surprising Truth / Fun Fact

Most engineers are scared of estimation. "I need exact numbers!" No. You don't. Amazon doesn't have exact numbers for Black Friday. They estimate. They provision for 2-3x. Sometimes they're wrong. They scale up or down. The goal is ballpark. Order of magnitude. "Are we building for 100 or 10,000 or 100,000?" That's the question. Get that right, and you're 80% there.

---

## Quick Recap

- Estimation = planning for the right ballpark (not exact numbers)
- Like planning a party: how many guests → how much food → how many chairs
- In software: total users → active users → QPS → storage
- Round to powers of 10: use 100,000 seconds per day, not 86,400
- Always think: "What if I'm off by 10x?" Build with headroom

---

## One-Liner to Remember

> **Estimation is not about being exact. It's about not being WRONG by 100x. Plan for 10 and 1,000 shows up? That's a crash, not a party.**

---

## Next Video

You've heard me say "QPS" a few times now. What exactly IS QPS? And what's "throughput"? These are words you'll hear in EVERY system design discussion. Let's break them down simply. Next video: What is QPS?
