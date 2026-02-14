# Availability vs Reliability vs Durability

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Three shops. Shop A: open 24/7, 365 days. Always there when you need it. But sometimes the products are wrong. Shop B: every product is exactly right, every time. But sometimes the shop is closed. Shop C: once you buy something, it *never* disappears. Receipt kept forever. Purchase recorded permanently. Three different promises. Three different qualities. In distributed systems, we call them availability, reliability, and durability. And they are NOT the same thing.

---

## The Story

**Availability:** Can I reach it right now? Percentage of time the system is up and responding. 99.9% availability = roughly 8.76 hours of downtime per year. 99.99% = 52 minutes. The system is *there*. It answers. That's availability. A system can be highly available and still return wrong data. It's up. It's just wrong.

**Reliability:** Does it produce correct results? When you use it, does it work properly? No bugs. No wrong calculations. No stale data when you asked for fresh. A system can be available 99.99% of the time but return wrong responses 5% of the time. Highly available. Not reliable.

**Durability:** Once data is written, is it safe? Will it survive disk failures? Crashes? Disasters? Durability is about permanence. A system can be fast and available but lose data when the disk dies. Not durable. Or it can be slow—writing to multiple replicas, multiple regions—but once written, that data is there forever. Durable.

You can have availability without reliability. Reliability without availability. Durability without speed. They're independent dimensions. Design for the ones that matter for your use case.

---

## Another Way to See It

Think of a vending machine. Available: it's plugged in, lit up, you can press buttons. Reliable: you pay, you get the right snack. Durable: the machine's records of sales survive a power outage. Three checks. Three different failures. Machine on but gives wrong item? Available, not reliable. Machine accurate but often broken? Reliable, not available.

Or a library. Available: doors open, you can enter. Reliable: catalog matches what's on the shelf. Durable: records of who borrowed what survive fire, flood, system crash. A library can be open (available) but have wrong catalog data (unreliable). Can have perfect records (durable) but be closed for renovations (unavailable).

---

## Connecting to Software

**Availability** = uptime. Measured in nines. SLAs: "99.9% availability." Redundancy, failover, health checks. Goal: system is reachable.

**Reliability** = correctness. Bug-free. Consistent. Accurate. Testing, code review, monitoring error rates. Goal: system does what it should.

**Durability** = data survival. Replication. Backups. Write-ahead logs. Multi-region. Goal: data never lost.

Real systems trade these off. Strong consistency (reliability) can reduce availability during partitions (CAP). Durability often adds latency. Know your priorities. Measure all three. Don't optimize for one while ignoring the others.

---

## Let's Walk Through the Diagram

```
    AVAILABILITY          RELIABILITY           DURABILITY
    "Can I reach it?"     "Is it correct?"      "Will data survive?"

    [User] ──► [System]   [User] ──► [System]   [Write] ──► [Disk]
         │          │          │         │           │        │
         │    200 OK ✓         │    Wrong data ✗     │   Replicated ✓
         │    (up, responding)  │    (bug, stale)     │   (survives crash)
         │                     │                     │
    Measured: uptime %    Measured: error rate   Measured: RPO, RTO
```

Three dimensions. Three different metrics. Don't confuse them.

---

## Real-World Examples (2-3)

**Example 1: Banking core vs. marketing site.** Banking core: must be reliable (correct balances) and durable (transactions never lost). Availability matters but correctness matters more. Marketing site: must be available (always showing the brand). A wrong image for an hour? Annoying but not catastrophic. Different priorities.

**Example 2: S3.** Amazon S3 promises 99.99% availability. And 99.999999999% (11 nines) durability. You can lose *access* for a bit. You will never lose your *objects*. Availability and durability are separate SLAs. Different design. Different guarantees.

**Example 3: Cache vs. database.** Cache: high availability (fast, usually there). Low durability (evicted, restarted—data gone). Database: lower availability sometimes (failover). High durability (replicated, persisted). Different roles. Different trade-offs.

---

## Let's Think Together

**Your system is 99.99% available but 5% of responses have wrong data. Is it reliable?**

No. Availability is high. Reliability is low. Users can reach you. But 1 in 20 responses is wrong. For a social feed, maybe acceptable. For payments, catastrophic. Always separate: "Are we up?" vs. "Are we correct?" Measure both. Fix both. Don't let uptime metrics hide correctness problems.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup bragged about 99.99% uptime. SLA met. Never down. Then users noticed: sometimes their data was wrong. Orders duplicated. Balances incorrect. Investigations revealed: a bug in a code path. Under load, 2% of requests hit it. Wrong data. System was available. It was not reliable. Reputation damaged. Legal issues. Lesson: uptime is not enough. If you're wrong when you're up, you're still failing. Measure reliability. Not just availability.

---

## Surprising Truth / Fun Fact

AWS and GCP publish separate SLAs for availability and durability. S3 durability: 11 nines. That's one object lost per 10 million objects per 10,000 years. Statistically. Availability is different—you might not *reach* S3 for an hour. But your data? Still there. The distinction matters for compliance, contracts, and architecture.

---

## Quick Recap (5 bullets)

- **Availability** = % of time system is up and responding. "Can I reach it?"
- **Reliability** = correctness. "Does it work properly when I use it?"
- **Durability** = data survival. "Will my data survive crashes and disasters?"
- **Independent** = you can be available but unreliable, reliable but unavailable.
- **Design for your use case** = payments need reliability + durability. Marketing needs availability.

---

## One-Liner to Remember

**Availability: can you reach it? Reliability: is it correct? Durability: will your data survive? Three questions. Three different answers.**

---

## Next Video

Next: **Fault Tolerance vs High Availability**—quick recovery vs. no interruption. Two strategies. Different costs. Stay tuned.
