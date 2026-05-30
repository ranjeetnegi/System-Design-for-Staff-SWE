# Chapter 5: Numbers Every Engineer Must Know — Estimation and Scale

---

## 1. Learning Goal

After reading this chapter, you will be able to:

- Convert between DAU (daily active users), requests per day, and QPS (queries per second)
- Estimate storage requirements for a given system
- Calculate the number of servers needed for a given load
- Explain what availability percentages mean in real downtime hours per year
- Do back-of-envelope calculations confidently in 60 seconds
- Know when an architecture is too small or too large for a given scale

---

## 2. Why This Matters

Imagine an interviewer says: "Design a system for 100 million daily active users." 

A junior engineer starts drawing boxes. A Staff engineer pauses and says: "100 million DAU, at 20 requests per user per day, gives us about 23,000 QPS average and 90,000 QPS at peak. We need cache — no single database handles 90K QPS. Let me show you why."

That pause — where you convert a vague requirement into real numbers — is a **Staff-level signal**. Numbers validate your design. They tell you if a single database will work, if you need sharding, if your caching strategy is correct.

The goal is not to memorize exact numbers. The goal is to derive them quickly enough to guide design decisions. Being off by 2x does not matter. Being off by 1000x means you built the wrong architecture.

---

## 3. Core Concepts

### Orders of Magnitude: Thinking in Powers of 10

Before doing detailed calculations, you need to be comfortable thinking in powers of 10.

| Number | Written | Real meaning |
|--------|---------|-------------|
| 1 thousand | 1K | Small startup scale |
| 1 million | 1M | Meaningful startup, tens of servers |
| 1 billion | 1B | Large company, thousands of servers |
| 1 trillion | 1T | Hyperscale: Google, Amazon level |

**Practice converting instantly:**
- "1 billion requests per day" → 1B ÷ 86,400 ≈ **11,500 QPS**
- "100 million users, 10 requests each per day" → 1B requests/day → **11,500 QPS average**
- "50 million MAU" → Daily: 50M ÷ 30 ≈ **1.7M DAU**

---

### Data Sizes: From Bytes to Petabytes

| Size | Bytes | Real example |
|------|-------|-------------|
| 1 Byte | 1 | One character |
| 1 KB | ~1,000 | A short text message |
| 1 MB | ~1,000,000 | One high-quality photo |
| 1 GB | ~1 billion | One HD movie |
| 1 TB | ~1 trillion | A small database |
| 1 PB | ~1 quadrillion | Large company's total data |

**Common object sizes (use these in calculations):**

| Item | Typical size |
|------|-------------|
| Tweet (text only) | ~280 bytes |
| User profile (name, email, bio) | ~1 KB |
| JSON API response | 1–10 KB |
| Photo (compressed) | 200 KB – 2 MB |
| Song (MP3) | 4–8 MB |
| Short video (1 min) | 10–50 MB |
| Feature-length movie | 2–10 GB |

---

### The Core Formula: From Users to QPS

**The formula** (memorize this):

```
Average QPS = DAU × actions per user per day ÷ 86,400

Peak QPS = Average QPS × 3 to 5
```

86,400 = number of seconds in a day (60 × 60 × 24)

**Why 3–5x for peak?** Traffic is not uniform. People use services more during evenings and lunch. During events (big news, product launches, sports), traffic spikes. Plan for peak, not average.

**Worked example:**

You are designing a social media feed for 10 million DAU. Each user views 20 posts per day on average.

```
Daily requests = 10,000,000 users × 20 requests = 200,000,000 requests/day
Average QPS    = 200,000,000 ÷ 86,400 ≈ 2,300 QPS
Peak QPS       = 2,300 × 4 ≈ 9,200 QPS
```

At 9,200 peak QPS, a single database (handles ~5,000 simple QPS) is under stress. You need a cache layer and read replicas.

---

### The Scale Mental Map

Once you know QPS, you can quickly judge what architecture you need:

| QPS | What you likely need |
|-----|---------------------|
| < 100 | 1 server, 1 database. No complexity needed. |
| 100 – 1,000 | Add caching. Consider read replica. |
| 1,000 – 10,000 | Load balancer + multiple app servers. Cache is essential. Read replicas needed. |
| 10,000 – 100,000 | Sharding or specialized databases. Message queues for async work. |
| 100,000+ | Multi-region. Custom infrastructure. Careful optimization everywhere. |

This is not a precise rule — it depends heavily on what each request does. But it is a fast starting point.

---

### Storage Estimation Formula

```
Storage = entities per day × size per entity × retention days
```

**Example: Estimating storage for Twitter-like posts**

Assumptions:
- 100 million DAU
- 5% of users post per day = 5 million posts per day
- Each post: 280 bytes text + 100 bytes metadata = ~400 bytes
- Retention: keep posts for 5 years = 1,825 days

```
Storage = 5,000,000 posts/day × 400 bytes × 1,825 days
        = 3.65 trillion bytes
        ≈ 3.65 TB
```

This fits on a few hard drives. But if each post includes one image (200 KB average):

```
Image storage = 5,000,000 × 200,000 bytes × 1,825 days
              = 1.8 × 10^15 bytes
              = 1.8 PB
```

This requires distributed object storage (like Amazon S3) and a CDN. The architecture changes completely based on whether you include images.

**Lesson:** Always separate text metadata from media files. They need different storage systems and have very different sizes.

---

### Estimating Number of Servers

```
Number of servers = Peak QPS ÷ QPS per server × 2 (for redundancy)
```

**Typical QPS per server** (rough estimates — vary widely by workload):

| Workload type | QPS per server |
|---------------|---------------|
| Serving static files from disk | 10,000 – 100,000 |
| Simple stateless API (no DB) | 5,000 – 20,000 |
| API with one database query per request | 500 – 2,000 |
| API with 3 database queries per request | 100 – 500 |
| Heavy computation (ML inference, video processing) | 10 – 100 |

**Example:**

You need to handle 50,000 peak QPS. Each request does one database query. Assume 1,000 QPS per server.

```
Servers needed = 50,000 ÷ 1,000 × 2 = 100 servers
```

Include the ×2 because you always want redundancy. If one server fails or is restarted for deployment, you should have capacity to absorb that traffic.

---

### Latency Numbers You Must Know

These numbers come from Jeff Dean (Google) and are essential reference points:

| Operation | Latency |
|-----------|---------|
| L1 CPU cache access | 0.5 nanoseconds |
| RAM access | 100 nanoseconds |
| SSD random read | 16,000 nanoseconds (16 μs) |
| HDD seek (spinning disk) | 2,000,000 nanoseconds (2 ms) |
| Network within same datacenter | 500,000 nanoseconds (0.5 ms) |
| Network within same region (US) | 40 ms |
| Network cross-continent | 100–200 ms |

**The ratios that matter:**
- RAM is **200x faster** than SSD
- SSD is **125x faster** than HDD
- Same-datacenter network is **1 ms** → design services to live in the same datacenter if they need to call each other frequently

---

### p50, p95, p99: Why Percentiles Matter

**Average latency hides problems.**

Imagine your API response times: 99 requests take 10 ms, but 1 request takes 500 ms. The average is 14.9 ms — looks fine. But 1% of users are experiencing 500 ms — unacceptable.

**Percentiles tell the real story:**

| Percentile | Meaning | Example |
|------------|---------|---------|
| p50 (median) | Half of requests are faster | "50% of users see under 15 ms" |
| p95 | 95% are faster | "95% of users see under 50 ms" |
| p99 | 99% are faster | "99% of users see under 200 ms" |
| p99.9 | 99.9% are faster | "The worst 0.1% see under 2 seconds" |

**At 1 million QPS, 1% is still 10,000 users per second** having a bad experience. That is why Staff engineers optimize for p99, not p50.

**Tail latency amplification:** If your service calls three downstream services in sequence, and each has p99 = 100 ms:
- Combined p99 ≈ 100 + 100 + 100 = **300 ms** (not 100 ms)

If three services are called in parallel, and each has p99 = 100 ms:
- Combined p99 is **worse than any individual p99** because the probability that at least one hits its tail is higher than the probability of one alone doing so.

**Lesson:** Every downstream call adds to your latency. Parallelize when possible (to reduce total time to the slowest call's time). Set timeouts on every downstream call.

---

### Availability: What the "Nines" Mean

**Availability** is the fraction of time the system is working correctly.

| Availability | Downtime per year | Downtime per month |
|-------------|-------------------|--------------------|
| 99% (two nines) | 3.65 days | 7.3 hours |
| 99.9% (three nines) | 8.76 hours | 43 minutes |
| 99.99% (four nines) | 52.6 minutes | 4.4 minutes |
| 99.999% (five nines) | 5.3 minutes | 26 seconds |

**Practical meanings:**
- 99% → Users notice. Multiple hours of downtime per month.
- 99.9% → Acceptable for most consumer products. About 43 minutes per month.
- 99.99% → Enterprise grade. Requires redundancy, failover automation, rehearsed runbooks.
- 99.999% → Telecom, financial systems. Extremely expensive to achieve. Requires multiple regions, zero single points of failure.

---

### Availability Multiplies When Services Depend on Each Other

If service A depends on service B, and both must be up for users to succeed:

```
Combined availability = A availability × B availability
```

**Example:** 10 services, each at 99.9% availability:

```
0.999 × 0.999 × 0.999 × ... (10 times) = 0.999^10 ≈ 0.990 = 99.0%
```

**You lost an entire nine** by chaining 10 services together! Each service is 99.9% but the combined system is only 99%.

**Implications:**
1. Keep dependency chains short where possible
2. Make non-critical downstream calls optional (fail gracefully if they are down)
3. Build in fallbacks for critical dependencies

---

### How to Improve Availability

**Redundancy (parallel components):**

If service A has two independent instances, both must fail for users to see an outage:

```
P(both fail) = (1 - 0.999) × (1 - 0.999) = 0.001 × 0.001 = 0.000001
Availability = 1 - 0.000001 = 99.9999%
```

**Caveat:** "Independent" means truly separate failure domains — different machines, different data centers, different power supplies. If both instances share the same underlying database or the same cloud availability zone, a failure can affect both at once. **Correlated failures defeat redundancy.**

---

### Error Budgets

An **error budget** is the allowed downtime in a given period.

- 99.9% availability = 8.76 hours of downtime per year = error budget
- If you have already used 8 hours, you have only 44 minutes left for the year

Teams use error budgets to make decisions: "We have used 80% of our error budget this month. We should freeze risky deployments and focus on reliability before introducing new features."

This creates a shared language between engineers and product managers about the cost of reliability vs. velocity.

---

## 4. Mental Models

### The "Scale Staircase" Mental Model

Each 10x increase in scale requires a different architecture:

```
10,000 users:    → 1 server, 1 database
100,000 users:   → Add cache, read replica
1,000,000 users: → Load balancer, multiple app servers, CDN
10,000,000 users:→ Sharding, queues, async processing
100,000,000+:    → Multi-region, custom infrastructure
```

This is not precise, but it gives you a fast way to judge if a design is appropriate.

### The "Show Your Work" Mental Model

In an interview or design review, showing your arithmetic signals Staff-level thinking:

```
Assumption: 10M DAU, 20 requests per user per day
Calculation: 10M × 20 = 200M requests/day
Convert: 200M ÷ 86,400 ≈ 2,300 QPS average
Peak: 2,300 × 4 = ~9,200 peak QPS
→ This tells me: cache is essential, one DB primary won't hold this
```

"We'll need a few servers" is not Staff level. "We need ~5 app servers and 2 read replicas for 9,200 peak QPS, with Redis cache assuming 95% hit rate" is.

---

## 5. Real-World Examples

### Example 1: Estimating a Chat System (like WhatsApp)

**Assumptions:** 
- 50 million DAU
- Each user sends 40 messages per day
- Each user reads 100 messages per day
- Each message: 100 bytes metadata + 200 bytes content = 300 bytes

**Writes (messages sent):**
```
50M × 40 = 2B messages/day ÷ 86,400 ≈ 23,000 write QPS average
Peak: 23,000 × 4 ≈ 92,000 write QPS
```

**Reads:**
```
50M × 100 = 5B reads/day ÷ 86,400 ≈ 58,000 read QPS average
Peak: 58,000 × 4 ≈ 230,000 read QPS
```

**Storage (1 year):**
```
2B messages/day × 365 days × 300 bytes ≈ 219 TB
```

**What this tells you:**
- 92K write QPS → cannot use a single SQL database → need to shard by conversation_id or user_id
- 230K read QPS → need aggressive caching of recent messages
- 219 TB / year → need distributed storage, archiving old messages to cold storage
- Real-time delivery to recipients → need WebSocket connections or push notifications, which means stateful connection servers

### Example 2: Estimating a URL Shortener (like bit.ly)

**Assumptions:**
- 100 million DAU
- 5 new short URLs created per user per day (writes)
- 20 redirects per user per day (reads)
- Peak factor: 4x

**Writes:**
```
100M × 5 = 500M shortens/day ÷ 86,400 ≈ 5,800 write QPS
Peak: 5,800 × 4 ≈ 23,000 write QPS
```

**Reads:**
```
100M × 20 = 2B redirects/day ÷ 86,400 ≈ 23,000 read QPS
Peak: 23,000 × 4 ≈ 92,000 read QPS
```

Read/write ratio ≈ 4:1. Read-heavy but not extreme.

**Storage (5 years):**
```
500M × 365 × 5 = 913B short links
Each: 6-byte code + 100-byte URL + 50-byte metadata ≈ 156 bytes
Total: 913B × 156 bytes ≈ 142 TB
```

**What this tells you:**
- 92K read QPS → Redis cache for popular short codes (most URLs are requested frequently shortly after creation, then rarely)
- 142 TB → needs sharding by short code hash
- Reads dominate → optimize for fast redirect (cache hit in <1 ms)

---

## 6. Design Trade-offs

### Over-provisioning vs Under-provisioning

**Under-provisioning:** System handles average load but crashes at peak. Users see errors during your busiest hours — the worst possible time.

**Over-provisioning:** System always handles peak but costs much more. During off-peak, you are paying for idle servers.

**The balance:** Most systems provision for peak × 1.5 (50% headroom). This provides safety margin during traffic spikes while not being wasteful. Autoscaling (adding servers automatically when load increases) helps, but it has a delay of 1–5 minutes for the new servers to start.

### Availability vs Cost

Each additional "nine" of availability costs roughly 10x more than the previous:

| Availability | Relative cost | What is needed |
|-------------|--------------|----------------|
| 99% | $1 | Basic setup |
| 99.9% | $3 | Redundancy, health checks |
| 99.99% | $10 | Multi-region, auto-failover |
| 99.999% | $30+ | Custom infrastructure, everything redundant |

**Beginner mistake:** Saying "we need 99.99% availability" without understanding the cost and complexity. First ask: what is the business cost of 1 hour of downtime? If it is $1,000, then 99.9% (43 min/month) may be acceptable. If it is $1 million, 99.99% may be required.

---

## 7. Common Interview Questions

1. **"Design a system for 100 million daily active users."**
   Expected: Immediately convert to QPS (about 11,500 average QPS at 10 actions/user/day). State peak is 4x higher. Use QPS to justify cache layer, read replicas, and number of servers needed.

2. **"How much storage do you need for 5 years of user activity?"**
   Expected: Identify entity (user actions), estimate size per entity, multiply by volume × retention. Separate text data from media. Arrive at a number and discuss if it fits on one machine or needs distributed storage.

3. **"We have 10 services each with 99.9% uptime. What is our system's uptime?"**
   Expected: 0.999^10 ≈ 99.0%. We lost a full "nine" by chaining 10 services. To improve: make some downstream calls optional, add fallbacks, or improve individual service availability.

4. **"How many servers do you need to handle 50,000 peak QPS of an API that does 3 database queries per request?"**
   Expected: At 3 DB queries per request, each request takes longer. Estimate 500 QPS per server. 50,000 ÷ 500 × 2 (redundancy) = 200 servers. Also note 50K × 3 = 150K DB QPS → definitely need caching and read replicas.

5. **"What does 99.99% availability mean in minutes per month?"**
   Expected: 99.99% → 0.01% downtime. 30 days × 24 hours × 60 min × 0.0001 ≈ 4.3 minutes per month. Or remember: 52 minutes per year.

---

## 8. Key Takeaways

**The estimation formula:** DAU × actions/day ÷ 86,400 = average QPS. Peak = average × 3–5.

**Show your work.** Numbers justify architecture. "We need a cache" is weak. "We need a cache because peak QPS is 90,000 and our database handles 5,000 QPS — without a 95% cache hit rate, the database will be overwhelmed" is Staff level.

**Order of magnitude matters more than precision.** Being off by 2x is fine. Being off by 100x means a wrong architecture. The goal is to determine: do we need 1 server or 100? That question has a right answer.

**99.9% availability = 8.76 hours downtime per year.** Know these numbers. Going from 99.9% to 99.99% is 10x harder and more expensive.

**Availability multiplies in serial.** 10 services at 99.9% = 99.0% combined. Every service in your dependency chain reduces total reliability.

**Error budgets make reliability a shared decision.** Once the error budget is spent, new risky deployments stop until the budget resets. This aligns engineers and product managers on reliability goals.

**The scale staircase:** Design your system for the scale you expect in 12–18 months. Build infrastructure that can grow to 10x your current scale. Design data models that can grow to 100x (especially shard keys).

**L5 vs L6 thinking:**
- L5: "We have 10 million users. We'll need more servers."
- L6: "10M DAU × 20 requests/day = 200M requests/day = 2,300 QPS average, 9,200 peak. At 500 QPS per server (each request makes 2 DB queries), we need 20 servers for peak. We also need Redis cache at 95% hit rate to keep DB reads under 460 QPS — within a single primary's capacity. Here is the diagram."
