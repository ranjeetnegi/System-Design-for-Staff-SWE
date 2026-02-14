# Capacity Estimation: Users, QPS, Storage

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You're catering a wedding. How much food do you order? Step 1: How many guests? Step 2: How many will actually eat? Step 3: How many plates per person? Step 4: Total plates per hour? Step 5: How much food storage do you need? Get these wrong—not enough food, guests hungry. Or massive waste. Same with software. Users, requests, storage. Get the numbers wrong, and your system collapses—or you overpay for nothing. Let me show you the formula.

---

## The Story

Picture the wedding. 200 guests. But not everyone eats the full meal. Maybe 80% have the main course. 160 plates. Plus appetizers. Plus dessert. Plus 20% buffer—people take seconds. Now you know: order for 200, plan for 240 servings. Storage? Where do you keep it? Refrigerated truck? How big? The numbers drive everything. Too few: disaster. Too many: waste. Just right: success.

Capacity estimation in software is the same. It's the math before the design. You need to know: how many requests per second? How much storage? How much bandwidth? Without these numbers, you're guessing. You might build for 1,000 users when you have 1 million. Or build for 10 million when you have 10,000. Both are costly mistakes. The first: your system collapses on launch. The second: you burn money on over-provisioned servers. The formula chain: Total users → Daily Active Users (DAU) → Requests per user per day → Total requests per day → Average QPS (divide by 86,400 seconds) → Peak QPS (multiply by 2–5 for spikes). Storage: data per request × requests per day × retention period. Bandwidth: data per response × QPS = bytes per second. Simple. Systematic. Essential. Do the math. Then design.

---

## Another Way to See It

Think of a stadium. How many seats? How many exits? How many bathrooms? The capacity drives the design. 10,000 fans need 10,000 seats. They need enough exits so everyone can leave in 30 minutes. They need enough bathrooms. Count first. Build second. Get the count wrong—stampede. Or a highway. How many lanes? Based on cars per day. Peak hours. Rush hour doubles the load. Capacity estimation. Then construction. Same in software. Estimate. Then architect.

---

## Connecting to Software

Let's walk through a full example: Design Instagram. 1 billion total users. 500 million DAU (50% active—typical for social apps). Each user views 5 photos per day. Total requests: 500M × 5 = 2.5 billion per day. Average QPS: 2.5B ÷ 86,400 ≈ 29,000. Peak QPS (assume 3x for spikes): ~87,000. Round to ~100K for safety. Now you know: your system must handle 100K QPS at peak. That number drives everything. Database? Sized to 100K. Cache? Sized to 100K. CDN? Sized to 100K.

**Storage:** 2.5B photos per day. Assume 1MB per photo (compressed). 2.5 PB per day. Retention? 5 years? 5 × 365 × 2.5 PB ≈ 4.5 PB. Petabyte scale. That's why they use object storage. Sharded. Cheap. **Bandwidth:** 100K QPS × 1MB = 100 GB/sec at peak. That's huge. Hence CDN. Cache. Reduce origin load. The numbers tell the story. The numbers drive the design.

---

## Let's Walk Through the Diagram

```
    CAPACITY ESTIMATION CHAIN

    Total Users (1B)
          │
          ▼
    DAU (500M)  ←  ~50% active typically
          │
          ▼
    Requests/user/day (5)
          │
          ▼
    Total requests/day (2.5B)
          │
          ▼
    Average QPS = 2.5B ÷ 86,400 ≈ 29K
          │
          ▼
    Peak QPS = 29K × 3 = ~87K → round to 100K

    STORAGE = data/request × requests/day × retention
             1 MB × 2.5B × 1825 days ≈ 4.5 PB

    BANDWIDTH = data/response × QPS
               1 MB × 100K = 100 GB/sec (peak)
```

One chain. Clear numbers. Storage. Bandwidth. Design follows. Trace each step. Do the math out loud in an interview. It shows you think.

---

## Real-World Examples (2-3)

**Example 1: Twitter.** Billions of tweets per day. DAU ~200M. Each user sees ~100 tweets. That's 20B reads/day. Writes? ~500M tweets/day. Read-heavy. Cache everything. Different QPS for reads vs writes. Design reflects that. Estimate each. Design for the sum.

**Example 2: Netflix.** 200M+ subscribers. Peak evening: maybe 50% streaming. 100M concurrent streams. Each stream: 5 Mbps average. 100M × 5 Mbps = 500 Gbps total. That's why they have CDNs everywhere. Capacity drove the architecture. The numbers dictated the design.

**Example 3: Uber.** Millions of rides per day. Each ride: location updates (high frequency), payment (one per ride), matching (real-time). Different operations, different QPS. Estimate each. Design each. Capacity estimation isn't one number. It's many. Get each right.

---

## Let's Think Together

WhatsApp: 2 billion users, 100 million DAU, 50 messages per user per day. Calculate QPS and daily storage.

**QPS:** 100M × 50 = 5 billion messages per day. 5B ÷ 86,400 ≈ 58,000 average QPS. Peak (3x): ~175K QPS. **Storage:** Assume 100 bytes per message (text). 5B × 100 = 500 GB per day. But add metadata. Media. Backup. Maybe 1–2 TB per day. Retention 5 years? 5 × 365 × 2 TB ≈ 3.6 PB. Now you know why WhatsApp needs distributed storage. Sharding. Multiple regions. The numbers tell the story. The math is simple. The implications are huge.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup launches a voting app for a reality show. They estimate: 1 million viewers, 10 votes each. 10 million votes total. They build for 100K QPS. "Plenty of headroom," they say. Finale night. 20 million viewers. 5 votes each. 100 million votes in 2 hours. That's 14,000 QPS average, 50K peak. Their database? Designed for 10K. It crashes. Votes lost. Show chaos. Legal threats. Reputation destroyed. The fix? They should have estimated for peak. Finals always spike. Capacity estimation isn't "average case." It's "worst reasonable case." Plan for the spike. Plan for the viral moment. When the stakes are highest, your system must hold.

---

## Surprising Truth / Fun Fact

Google's first big challenge was capacity. Early search: a few thousand queries per day. Then millions. The original architecture couldn't scale. They had to redesign. Now they handle billions. The lesson: estimate early. Overestimate if unsure. It's cheaper to have headroom than to rebuild under load. Fermi was right: "There are two kinds of errors. Type 1: thinking something is impossible when it's possible. Type 2: thinking something is possible when it's impossible." In capacity estimation, err on the side of "we need more."

---

## Quick Recap (5 bullets)

- **Formula chain**: Users → DAU → requests/user/day → total requests → QPS (÷86,400) → peak QPS (×2–5).
- **Storage** = data per request × requests per day × retention.
- **Bandwidth** = data per response × QPS.
- **Estimate for peak**, not average. Finals, launches, viral moments—always spike.
- **Wrong numbers = wrong design.** Get capacity right first. Architecture follows.

---

## One-Liner to Remember

**Cater the wedding for the guests you'll have. Build the system for the traffic you'll get. Count first. Build second.**

---

## Next Video

Next: **Back-of-the-envelope math.** How many piano tuners in Chicago? You don't Google. You estimate. The Fermi way. See you there.
