# Back-of-the-Envelope Math: Orders of Magnitude

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A friend asks: "How many piano tuners are in Chicago?" You don't Google it. You ESTIMATE. Chicago has about 2.7 million people. Maybe 1 million households. Ten percent have pianos? 100,000 pianos. Each tuned once a year. A tuner does 4 per day, 250 days a year—1,000 per year. 100,000 ÷ 1,000 = 100 tuners. Is it exact? No. Is it useful? Yes. This is Fermi estimation. Breaking big unknowns into small, knowable pieces. System designers use it every day. Let me show you how.

---

## The Story

Enrico Fermi—the physicist—loved this. He could estimate anything. The yield of a bomb. The number of grains of sand on a beach. How? He broke big unknowns into small, knowable pieces. Chicago's population: you can look up or guess. Pianos per household: rough guess. Tunings per year: industry knowledge. Multiply. Divide. Ballpark. Done. Back-of-the-envelope math is quick, approximate, and powerful. You round aggressively. You use orders of magnitude. Being off by 2x is fine. Being off by 100x is not. The goal: get to a ballpark. "Is this 1 million or 1 billion?" That difference changes everything. In an interview, you won't have a calculator. You'll have 45 minutes. You need to estimate: storage, QPS, bandwidth. Fast. Rough. Right enough. Right enough to choose the right architecture. Right enough to know: single server or distributed? Gigabytes or petabytes?

---

## Another Way to See It

Think of a farmer estimating harvest. How many apples? Trees × apples per tree. Rough. Could be 10% off. But they know: thousands or millions? That's enough to plan storage and trucks. Or a chef: how much rice for 100 people? A cup per person? 100 cups. Rough. Enough to order. Back-of-the-envelope: good enough to decide. Perfect is the enemy of fast. In system design, you need the right order of magnitude. Not the right number. 100 tuners or 200? Fine. 10 or 10,000? Problem. Get the magnitude right. The rest follows.

---

## Connecting to Software

**Key numbers to memorize:** 86,400 seconds per day (round to 100,000 for easy math). 2.5 million seconds per month. 1 million = 10^6. 1 billion = 10^9. 1 TB = 10^12 bytes. 1 character = 1 byte. 1 photo ≈ 1 MB. 1 video minute ≈ 50 MB. 1 video hour ≈ 1–5 GB (compressed). With these, you can estimate anything. In an interview, state these as you use them. It shows you've practiced. Practice: "How much storage does YouTube need per day?"

---

## Let's Walk Through the Diagram

```
    FERMI ESTIMATION: BREAK IT DOWN

    "How much storage does YouTube need per day?"

    Unknown: Storage/day
          │
          ▼
    Break into: (Upload rate) × (Video size) × (Time)
          │
          ▼
    Upload rate: 500 hours/min (known fact)
    Time: 60 min × 24 hr = 1440 min/day
    Video size: ~1 GB/hour (compressed)
          │
          ▼
    500 × 1440 × 1 GB = 720,000 GB ≈ 700 TB ≈ 1 PB/day

    Result: Petabyte scale. Not gigabyte. Not exabyte.
```

Round. Simplify. Get the order of magnitude. Done. Practice problem: YouTube storage. Solution: ~1 PB per day. Architecture: distributed object storage. Sharded. Multi-region. The estimate drove the design.

---

## Real-World Examples (2-3)

**Example 1: Instagram storage.** 2.5B photos per day. 1 MB each. 2.5 PB/day. 1 PB = 1000 TB. That's why they use object storage. Sharded. Cheap. Capacity estimation told them: petabyte scale. Single server? Impossible. Distributed? Required.

**Example 2: Uber rides.** 20M rides per day. Each ride: 10 location updates, 1 payment, 1 match. 200M location events. 20M payments. Different scale for each. Estimate each. Design each. The numbers tell you where to focus.

**Example 3: Twitter tweets.** 500M tweets/day. 280 bytes each. 500M × 280 = 140 GB/day. Text is tiny. But add retweets, likes, timelines—the read amplification is huge. 100x? 140 GB × 100 = 14 TB/day for timeline builds. Ballpark. Architecture follows. Cache. Shard. Distribute.

---

## Let's Think Together

How many messages does Slack process per day across all companies?

Break it down. How many Slack users? 50M+ DAU. How many messages per user per day? 30–50. Call it 40. 50M × 40 = 2 billion messages. Each message: text (200 bytes) + metadata (300 bytes) = 500 bytes. 2B × 500 = 1 TB per day. Storage. For processing (sending, receiving, indexing): multiply by 2 (each message touched multiple times). 2 TB processed. Ballpark. You didn't need exact numbers. You needed: "Is it GB or TB or PB?" TB. That's the answer. Architecture: distributed. Sharded. Not a single server. The estimate told you. One number. Big implication.

---

## What Could Go Wrong? (Mini Disaster Story)

A team designs a log aggregation system. They estimate: 10 GB per day. They build for 100 GB. "Plenty of headroom." Launch. Reality: 2 TB per day. Why? They estimated "log lines" but forgot: stack traces. Full request bodies. Debug dumps. Their estimate was off by 20x. The system filled in a week. Emergency scaling. Data loss. Angry customers. The lesson: when estimating, list ALL the data. Don't forget metadata. Don't forget peaks. Round up. 2x wrong is okay. 20x wrong is disaster. When in doubt, overestimate. Under-provisioning kills. Over-provisioning costs. Choose the lesser evil.

---

## Surprising Truth / Fun Fact

Enrico Fermi used this to estimate the yield of the first atomic bomb. He dropped paper scraps when the blast wave hit. Watched how far they traveled. Estimated the energy. He was remarkably close. No instruments. Just physics and rough math. Back-of-the-envelope saved lives—told them how far to stand. In software, it saves projects. "Is this feasible?" Estimate. Fast. Decide. You don't need a spreadsheet. You need a napkin and 5 minutes.

---

## Quick Recap (5 bullets)

- **Back-of-the-envelope** = quick, rough, order-of-magnitude estimates. Good enough to decide.
- **Memorize**: 86,400 sec/day ≈ 100K, 1M = 10^6, 1B = 10^9, 1 photo ≈ 1 MB, 1 video min ≈ 50 MB.
- **Round aggressively.** Off by 2x is fine. Off by 100x is not.
- **Break unknowns into knowable pieces.** Fermi estimation. YouTube storage = upload rate × size × time.
- **Get the order of magnitude right.** GB vs TB vs PB. That drives architecture.

---

## One-Liner to Remember

**You don't need the right number. You need the right magnitude. 100 tuners or 200? Fine. 10 or 10,000? Problem.**

---

## Next Video

Next: **What breaks first at 2x, 10x, 100x scale?** The rope bridge. 10 people? Fine. 1000? Collapse. Different parts fail at different scales. Let's trace it.
