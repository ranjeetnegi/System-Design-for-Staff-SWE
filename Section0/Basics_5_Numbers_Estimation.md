# Basics Chapter 5: Numbers Every Engineer Must Know — Estimation, QPS, and Availability

---

## Introduction

Staff Engineers make architecture decisions based on rough numbers. When an interviewer says "design a system for 50 million users," the candidate who pauses, does the math, and says "that's roughly 12K QPS average, 50K peak—we'll need a cache layer and read replicas" has already signaled Staff-level thinking. The candidate who draws boxes without numbers has not.

This chapter teaches you to think in numbers. Not memorization—derivation. You'll learn the anchor points (orders of magnitude, data sizes, latency tiers), the formulas (DAU to QPS, availability composition, server capacity), and the mental habits that turn vague requirements into concrete, defensible designs. The goal is fluency: when you hear "100M DAU" or "99.99% availability," you instantly know what that implies for architecture. When someone says "design a URL shortener for 100 million users," the difference between an L5 and L6 response often comes down to one thing: **can you quickly estimate whether your design will work?** This chapter gives you the numerical foundations—orders of magnitude, scale, latency, QPS, availability, and server capacity—that every system designer must internalize.

These aren't numbers to memorize for an exam. They're the raw material for back-of-the-envelope estimation: the 60-second calculation that tells you if a single database will suffice, if you need 10 servers or 1000, and whether your availability target is achievable. By the end of this chapter, you'll be able to derive capacity, estimate cost, and reason about scale with Staff-level fluency.

---

## Part 1: Orders of Magnitude

### The Power of Rough Numbers

Before diving into specific values, understand the mindset: **precision is the enemy of estimation**. When a Staff Engineer estimates, they aim for "right order of magnitude"—is it thousands, millions, or billions? Being off by 2x usually doesn't change the architecture. Being off by 1000x does. Orders of magnitude are your anchor points.

### 1 Thousand (1K), 1 Million (1M), 1 Billion (1B), 1 Trillion (1T)

| Magnitude | Numeric | Rough Intuition |
|-----------|---------|----------------|
| **1K** | 1,000 | Small team, single server, tiny dataset |
| **1M** | 1,000,000 | Startup scale, tens of servers, meaningful data |
| **1B** | 1,000,000,000 | Big tech scale, thousands of servers, serious infrastructure |
| **1T** | 1,000,000,000,000 | Hyperscale: Google, AWS, Facebook-level |

**Why this matters**: When you hear "10 million daily active users," you immediately know you're in the 1M–10M range—not single-server territory, but not yet hyperscale. When you hear "1 billion requests per day," you're in the 10K–20K QPS range (1B ÷ 86,400 seconds ≈ 11,500). These mental conversions are instant for Staff Engineers.

### Data Sizes: From Bytes to Petabytes

| Size | Bytes | Rough Analogy |
|------|-------|---------------|
| **1 KB** | 1,024 | A short text message, a few paragraphs |
| **1 MB** | 1,048,576 | A typical photo, a minute of low-quality audio |
| **1 GB** | ~1 billion | A high-definition movie, a small database |
| **1 TB** | ~1 trillion | A small company's data warehouse, thousands of databases |
| **1 PB** | ~1 quadrillion | A large company's total data, major analytics platforms |

**Practical conversions**:
- 1 KB ≈ 1,000 characters (or ~250 words)
- 1 MB ≈ 1,000 KB ≈ one high-res Instagram photo
- 1 GB ≈ 1,000 MB ≈ one HD movie (compressed)
- 1 TB = 1,000 GB ≈ a small data center's worth of active data

### Common Software Numbers

These numbers show up constantly in system design. Internalize them:

| Item | Typical Size | Notes |
|------|--------------|-------|
| **Tweet** | 280 characters | ~280 bytes (or ~560 bytes UTF-16) |
| **Average web page** | 2–3 MB | HTML + CSS + JS + images |
| **Average JSON API response** | 1–10 KB | User object, feed item, search result |
| **Database row** | 100 B – 10 KB | Depends heavily on schema |
| **Log line** | 100–500 B | Structured logging |
| **Session cookie** | 100–500 B | Session ID + metadata |
| **JWT token** | 200–2 KB | Depends on claims |

**Staff-level implication**: When estimating storage, you multiply these by user count and retention. "10M users, 1 KB profile each, 2 years retention" = 10M × 1 KB × 1 (no growth) ≈ 10 GB. Trivial. "10M users, 100 requests/day, 500 B each, 30 days" = 10M × 100 × 500 × 30 = 15 TB. Very different architecture.

### Powers of 2: Why They Matter

Computers think in binary. Many system limits and designs use powers of 2:

| Power | Value | Common Use |
|-------|-------|------------|
| 2^10 | 1,024 ≈ 1K | Kilobyte (KB), small lookup tables |
| 2^20 | 1,048,576 ≈ 1M | Megabyte (MB), in-memory structures |
| 2^30 | 1,073,741,824 ≈ 1B | Gigabyte (GB), cache sizes |
| 2^40 | ~1.1 trillion | Terabyte (TB), shard counts |
| 2^32 | ~4.3 billion | Max int32, IPv4 address space |
| 2^64 | ~1.8 × 10^19 | Max int64, huge ID spaces |

**Why estimation matters**: Staff Engineers use these to sanity-check. "Can we fit 100M user IDs in memory?" 100M × 8 bytes (int64) = 800 MB. Yes, on a single server. "Can we fit 1B?" 8 GB. Still possible. "10B?" 80 GB. Now we're talking distributed.

### L5 vs L6: Orders of Magnitude

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ORDERS OF MAGNITUDE: L5 vs L6                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   L5: "We have a lot of users"                                          │
│   L6: "10M DAU × 20 requests/day = 200M requests/day ≈ 2.3K QPS avg"    │
│                                                                         │
│   L5: "Our database is getting big"                                      │
│   L6: "100M rows × 1 KB/row = 100 GB; at 10% growth/year we hit 1 TB    │
│        in ~2.5 years—we need a sharding plan"                           │
│                                                                         │
│   L5: "We need to cache more"                                            │
│   L6: "Hot data is ~1% of 100 GB = 1 GB; Redis 8 GB instance can hold   │
│        it with room for replication and overhead"                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Staff-Level Insight**: The ability to go from "a lot" to "roughly X" in seconds is what separates designers who can validate their architecture from those who guess. Every architecture decision—single DB vs sharded, sync vs async, cache or not—depends on numbers. Get the numbers wrong, and the architecture collapses.

### Practical Estimation Drill: Sanity-Check Your Intuition

Before moving on, practice this mental exercise. When someone says:

- "We have 50 million monthly active users" → DAU ≈ 50M/30 ≈ 1.7M. At 20 actions/day: 34M requests/day ≈ 400 QPS average, ~1.5K peak.
- "Our database is 500 GB" → That's half a TB. Single server can hold it. Replication doubles it. At 1 PB you're in distributed territory.
- "We process 10 billion events per day" → 10B/86,400 ≈ 115K QPS. Peak ~350K–575K. You need a queue, workers, and distributed storage.

**Staff-Level Habit**: When you hear a number, immediately convert it to QPS, storage, or whatever dimension matters for your design. The conversion becomes automatic with practice.

---

## Part 2: What is Scale and Why Does It Matter?

### Scale = The Size of the Problem

**Scale** isn't one number. It's the combination of:
- **Users**: How many people use the system?
- **Requests**: How many operations per second (or day)?
- **Data**: How much data do you store and process?
- **Geography**: Single region or global?
- **Team**: How many engineers touch this system?

A system "at scale" is one where these dimensions are large enough that naive solutions break. What breaks at 1K users is different from what breaks at 1M users.

### Vertical vs Horizontal Scaling

| Approach | What It Means | Pros | Cons |
|----------|---------------|------|------|
| **Vertical (scale up)** | Bigger machine: more CPU, RAM, disk | Simple, no distributed complexity | Hit ceiling (biggest instance exists), single point of failure |
| **Horizontal (scale out)** | More machines | No theoretical limit, redundancy | Complexity: coordination, consistency, failure modes |

**The Staff-level reality**: Every system starts vertical. At some point, you hit limits. The question is *when* you need to go horizontal—and whether your architecture allows it. A monolith with in-memory state is hard to scale horizontally. A stateless service behind a load balancer scales easily.

### What Breaks at Different Scales

| Scale | User Count | Typical Challenges | Typical Solutions |
|-------|------------|---------------------|-------------------|
| **Trivial** | 1K | Nothing | Single server, single DB |
| **Small** | 10K–100K | Single DB starts to sweat | Add cache, read replicas |
| **Medium** | 100K–1M | DB is bottleneck, cache helps | Read replicas, connection pooling, CDN |
| **Large** | 1M–10M | Need to shard, replicate | Sharding, queues, async processing |
| **Very Large** | 10M–100M | Multi-region, consistency hard | Multi-region, eventual consistency, specialized stores |
| **Hyperscale** | 100M+ | Everything: data, traffic, team | Custom infrastructure, distributed everything |

**The inflection points**:
- **~100K users**: Single database often still works; add Redis for sessions/cache
- **~1M users**: Read replicas become essential; consider CDN for static content
- **~10M users**: Sharding or partitioning is on the table; queues for async work
- **~100M users**: Multi-region, specialized databases, event-driven architecture

### Scale Is Not Just Traffic

Traffic (QPS) is one dimension. Others matter equally:

| Dimension | Low | High | Impact |
|-----------|-----|------|--------|
| **Data volume** | GB | PB | Storage choice, retention, archival |
| **Data growth rate** | Slow | Fast | Sharding strategy, partition design |
| **Geographic spread** | Single region | Global | Latency, replication, data residency |
| **Team size** | 1–5 | 50+ | API boundaries, ownership, deployment |
| **Feature count** | Few | Many | Monolith vs microservices, coupling |

**Example**: A metrics pipeline might have moderate QPS but massive data volume (billions of data points per minute). A chat system might have high QPS and moderate data. The architecture differs because the bottleneck differs.

### L5 vs L6: Scale Thinking

| Aspect | L5 Thinking | L6 Thinking |
|--------|-------------|-------------|
| **Scale** | "We need to handle growth" | "At 10M DAU we need X; at 100M we need Y—here's the migration path" |
| **Bottleneck** | "The database is slow" | "The database is the bottleneck; read/write ratio is 100:1, so read replicas and cache will buy us 10x" |
| **Inflection** | "We'll scale when we need to" | "We'll need sharding before we hit 50M users; we're designing the schema for it now" |

### Scale and Team Structure

Scale isn't only technical. At 100 engineers, you have 20+ teams. Each team needs clear ownership. API boundaries become team boundaries. A system that "scales" technically but requires 5 teams to ship a feature has scaled wrong. Staff Engineers design for both technical and organizational scale: services that one team can own, APIs that enable parallel work, and boundaries that reduce coordination cost.

### Geographic Scale: Single Region vs Multi-Region

| Scope | Latency | Complexity | When to Use |
|-------|---------|------------|--------------|
| **Single region** | 1–5 ms intra-DC | Low | Most startups, simple systems |
| **Multi-region (same continent)** | 20–50 ms | Medium | Users spread across US, EU |
| **Global** | 100–300 ms | High | Worldwide user base, compliance (data residency) |

Going multi-region introduces: replication lag, conflict resolution, data residency (GDPR), and failover complexity. Don't do it until you need it—but design with it in mind (e.g., partition keys that allow regional sharding).

---

## Part 3: Latency — Why Speed Matters

### Latency Numbers Every Programmer Should Know

Jeff Dean's famous list (approximate, varies by hardware):

| Operation | Latency | Relative to L1 Cache |
|-----------|---------|----------------------|
| L1 cache reference | 0.5 ns | 1x |
| L2 cache reference | 7 ns | 14x |
| Main memory (RAM) | 100 ns | 200x |
| SSD random read | 16 μs (16,000 ns) | 32,000x |
| HDD seek | 2 ms (2,000,000 ns) | 4,000,000x |
| Round-trip same datacenter | 0.5 ms | — |
| Round-trip cross-datacenter (US) | 40 ms | — |
| Round-trip cross-continent | 100–200 ms | — |

**Key insight**: There's a **million-fold** gap between L1 cache and disk. Memory is ~1000x faster than SSD. Network within a datacenter is ~1000x faster than cross-continent. Where you put data and how many network hops you make dominates latency.

### p50 vs p99: Why Averages Lie

Users don't experience average latency. They experience *their* latency. And the worst experiences—the tail—drive perception.

| Percentile | Meaning | Why It Matters |
|------------|---------|----------------|
| **p50 (median)** | Half of requests faster, half slower | Often 2–5x better than mean (mean is skewed by outliers) |
| **p95** | 95% of requests are faster | Catches most users |
| **p99** | 99% of requests are faster | The "worst 1%"—still millions of users at scale |
| **p99.9** | 99.9% faster | The truly awful experiences |

**Example**: If p50 latency is 20 ms and p99 is 500 ms, your "average" might look fine on a dashboard while 1% of users suffer 500 ms—unacceptable for many products. Staff Engineers optimize for p99, not p50.

### Tail Latency Amplification

Here's the subtle trap: **if you make N parallel or sequential calls, the p99 of the *combined* operation is often much worse than any single call's p99**.

**Sequential**: If Service A calls B, C, D in sequence, and each has p99 of 100 ms, the p99 of the total is roughly 300 ms (latencies add).

**Parallel**: If Service A calls B, C, D in parallel and waits for all, the p99 of the total is the p99 of the *slowest*. With 3 services, the chance that at least one is in its tail is higher than for one service. So p99(total) ≈ max(p99(B), p99(C), p99(D))—and in practice, with correlation, it can be worse.

**Rule of thumb**: 10 parallel calls, each with p99 of 100 ms → combined p99 can be 200–400 ms or more. Tail latency amplifies.

### Latency Budgets

**Latency budget**: The total user-visible latency is the sum of all sequential steps. You allocate a "budget" to each.

```
    ┌─────────────────────────────────────────────────────────────────────┐
    │                    TYPICAL 200ms p99 BUDGET                         │
    ├─────────────────────────────────────────────────────────────────────┤
    │                                                                     │
    │   DNS:           0–20 ms   (often cached: 0)                        │
    │   TCP + TLS:     30–80 ms  (1–2 RTT)                                │
    │   Load balancer: 1–2 ms                                              │
    │   API gateway:   2–5 ms                                              │
    │   Service logic: 20–50 ms                                           │
    │   DB/cache:      10–50 ms                                           │
    │   Response:      5–10 ms                                             │
    │   ─────────────────────                                             │
    │   Total:         ~70–217 ms                                         │
    │                                                                     │
    │   To hit 200ms p99, every step must stay within budget.             │
    │   One 100ms DB call can blow the whole budget.                      │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘
```

**Staff-level practice**: Instrument each hop. When p99 degrades, you identify which hop is responsible. "Our p99 went from 150 ms to 400 ms—the user service's p99 went from 50 ms to 300 ms. That's our culprit."

### Latency vs Throughput: Not the Same

Latency = time for one request. Throughput = requests per second. They're related but distinct. A system can have:
- **Low latency, high throughput**: e.g., Redis—sub-millisecond per op, 100K+ ops/sec
- **High latency, high throughput**: e.g., batch job—each item takes 10 seconds, but 1000 parallel workers = 100 items/sec throughput
- **Low latency, low throughput**: e.g., complex query—50 ms each, but DB can only run 100 concurrent = 2K QPS

When you optimize, know which you're optimizing for. User-facing APIs: latency. Batch pipelines: throughput. Don't conflate them.

### Queuing and Latency Degradation

Under load, requests queue. If your service handles 1K QPS and receives 2K QPS, the queue grows. Latency grows linearly with queue depth: each new request waits for all previous ones. Little's Law: Average requests in system = arrival rate × average latency. So if you want to bound latency, you must either increase capacity or reject/load-shed excess traffic.

### L5 vs L6: Latency Thinking

| Aspect | L5 Thinking | L6 Thinking |
|--------|-------------|-------------|
| **Metric** | "We're fast" | "p99 is 180 ms; we're within our 200 ms budget" |
| **Optimization** | "Make it faster" | "DB is 60% of latency; we'll add a cache layer for hot keys" |
| **Debugging** | "Sometimes it's slow" | "p99 spikes correlate with the feed service; we're tracing the slow path" |

---

## Part 4: QPS and Throughput

### QPS: Queries Per Second

**QPS** (sometimes RPS—Requests Per Second) = how many requests your system handles per second. It's the primary metric for capacity planning.

**Throughput** = how much *data* your system processes per second (MB/s, GB/s). A system can have high QPS (many small requests) or high throughput (few large requests). Different bottlenecks.

| Metric | Unit | What It Measures |
|--------|------|-------------------|
| **QPS** | requests/sec | Number of operations |
| **Throughput** | bytes/sec | Volume of data moved |

**Example**: A logging service might have 100K QPS of small log lines (100 B each) = 10 MB/s throughput. A video transcoding service might have 10 QPS of 100 MB files = 1 GB/s throughput. The first is QPS-bound; the second is throughput-bound.

### Estimation Formula: From DAU to QPS

The standard derivation:

```
    Daily Active Users (DAU)
    × Actions per user per day
    ÷ 86,400 seconds
    = Average QPS
```

**Peak QPS** is typically **3–5×** average. Traffic isn't uniform—it peaks during business hours or prime time.

**Worked example**:
- 10M DAU
- 20 requests per user per day
- 200M requests/day
- 200M ÷ 86,400 ≈ **2,300 QPS average**
- Peak (4×): **~9,200 QPS**

### Read vs Write QPS

Most systems are **read-heavy**:

| System Type | Typical Read/Write Ratio | Implication |
|-------------|--------------------------|-------------|
| Social feed | 100:1 to 1000:1 | Cache aggressively, read replicas |
| E-commerce product pages | 50:1 to 100:1 | CDN, cache, replicas |
| Banking (transactional) | 5:1 to 20:1 | Still read-heavy, but writes matter more |
| Metrics/analytics | 1:10 (write-heavy) | Optimize for writes, batch inserts |
| Chat | 2:1 to 5:1 | More balanced |

**Why it matters**: Read-heavy systems can use caches and read replicas. Write-heavy systems need different strategies—batching, append-only logs, column stores. Design changes based on the ratio.

### How to Estimate QPS: Step by Step

1. **Identify DAU** (or MAU → DAU with a ratio, e.g., MAU/30)
2. **Estimate actions per user per day** (page views, API calls, etc.)
3. **Multiply**: DAU × actions = total requests/day
4. **Divide by 86,400**: total ÷ 86,400 = average QPS
5. **Apply peak factor**: average × 3–5 = peak QPS
6. **Split read/write** if relevant: e.g., 90% read, 10% write

**Example: Chat system**
- 1M DAU
- 50 messages sent per user per day (writes)
- 200 messages read per user per day (reads)
- Writes: 1M × 50 = 50M/day ≈ 580 QPS avg, ~2,300 peak
- Reads: 1M × 200 = 200M/day ≈ 2,300 QPS avg, ~9,200 peak

### QPS and Capacity Planning: The Cascade

QPS doesn't stop at the API. A single user request can trigger:
- 1 API call
- 3 internal service calls (auth, user, feed)
- Each service: 2 DB queries, 1 cache lookup
- Total: 1 + 3×3 = 10 operations, or more with fan-out

If you have 10K user-facing QPS and 5× internal amplification, your backend handles 50K internal QPS. Capacity planning must account for this **cascade**. Staff Engineers map the full dependency graph and ensure every node is provisioned for its share.

### Burst Traffic and Peak Estimation

Traffic isn't smooth. A viral post, a flash sale, or a news event can create spikes of 10–100× normal. Your architecture must either:
1. **Over-provision** for peak (expensive, often wasteful)
2. **Auto-scale** (scale up on demand; cold starts can hurt)
3. **Queue and dampen** (absorb spikes in a queue; process at steady rate)
4. **Load-shed** (reject excess traffic; degrade gracefully)

Most systems combine 2 and 3: auto-scale with a queue buffer. Staff Engineers define the expected burst profile and design for it.

---

## Complete Back-of-Envelope Estimation Framework

A systematic methodology turns vague requirements into defensible numbers. Follow these five steps for any system design.

### Step-by-Step Methodology

**Step 1: Identify the Core Entity**

What is the primary thing being created, read, or processed? Examples: users, messages, orders, video uploads, feed views, search queries. Everything flows from this entity.

| System Type | Core Entity | Secondary Entities |
|-------------|-------------|-------------------|
| Social feed | Feed views / posts | Likes, comments, follows |
| Messaging | Messages | Conversations, presence |
| Video streaming | Video plays / uploads | Thumbnails, transcodes, chunks |
| E-commerce | Orders | Products, cart items, reviews |
| Search | Queries | Index entries, results |

**Step 2: Estimate Volume**

Volume = DAU × actions per user per day. Be explicit about assumptions.

```
    Volume = DAU × (primary actions per user per day)
    
    Secondary volumes: DAU × (secondary actions) — e.g., likes, comments
```

**Step 3: Convert to QPS**

```
    Average QPS = Daily Volume ÷ 86,400 seconds
    Peak QPS = Average QPS × (3 to 5)
```

Traffic is not uniform. Peak is typically 4× average; some systems see 10× for events.

**Step 4: Estimate Storage**

```
    Storage = (entities per day × retention days) × size per entity
    
    Size per entity: sum of all fields. Be explicit.
    Retention: how long do you keep it?
```

**Step 5: Estimate Bandwidth**

```
    Bandwidth (bytes/sec) = QPS × average payload size
    
    For reads: QPS × response size
    For writes: write QPS × request size
```

Account for internal fan-out: one user request may trigger 5 internal calls.

### Worked Example 1: Social Media Feed System

**Assumptions**: 200M DAU. Each user views 30 feed items/day. Each feed item fetch = 2 KB average (JSON + metadata). Reads only for this calc.

- **Volume**: 200M × 30 = 6B feed views/day
- **QPS**: 6B ÷ 86,400 ≈ **69,400 QPS average**. Peak (4×): **~278K QPS**
- **Storage**: Assume 6B feed impressions logged for analytics. 100 B per impression × 90 days = 54 TB
- **Bandwidth**: 69,400 × 2 KB ≈ **139 MB/s** average. Peak ~556 MB/s

**Architecture implication**: 278K read QPS → cache layer mandatory. At 95% cache hit, DB sees ~14K QPS. Read replicas + CDN for static assets.

### Worked Example 2: Messaging Platform

**Assumptions**: 50M DAU. 80 messages sent per user per day. 200 messages read per user per day. Message size: 200 B metadata + 500 B body ≈ 700 B.

- **Write volume**: 50M × 80 = 4B messages/day → **46K write QPS average**, ~185K peak
- **Read volume**: 50M × 200 = 10B reads/day → **116K read QPS average**, ~464K peak
- **Storage** (2 years): 4B × 365 × 2 × 700 B ≈ **2 PB**
- **Bandwidth (writes)**: 46K × 700 B ≈ 32 MB/s. Reads: 116K × 700 B ≈ 81 MB/s

**Architecture implication**: Fan-out for delivery (1 message → N recipients). If average 2 recipients, 46K writes → 92K+ delivery operations. Queue-based architecture. WebSocket or long-poll for real-time. Storage sharding by conversation or user.

### Worked Example 3: Video Streaming Platform

**Assumptions**: 100M DAU. 5 video plays per user per day. Average watch: 10 minutes. Video bitrate: 2 Mbps. 10K uploads/day, 500 MB average.

- **Play volume**: 100M × 5 = 500M plays/day → **5,800 QPS** (play start events)
- **Streaming bandwidth**: 500M plays × 10 min × 60 sec × 2 Mbps = 6 × 10^15 bits/day ≈ **69 Tbps-day** → average **800 Gbps** sustained
- **Upload storage** (1 year): 10K × 365 × 500 MB ≈ **1.8 PB**
- **Transcode output** (assume 3 renditions, same total): ~5.4 PB

**Architecture implication**: Bandwidth dominates. CDN is mandatory—99%+ of bytes from edge. Origin only for cache fill. Upload: queue to transcode workers; store in object storage (S3/GCS). Transcode pipeline: parallel workers, multiple output formats.

---

## Part 5: Availability — What Does 99.9% Mean?

### Availability = Uptime / Total Time

**Availability** is the fraction of time a system is operational. Expressed as a percentage:

```
    Availability = (Total Time - Downtime) / Total Time
```

### The Nines

| Availability | Downtime per Year | Downtime per Month | Meaning |
|--------------|-------------------|--------------------|---------|
| 99% | 3.65 days | ~7.2 hours | "Two nines"—unacceptable for most products |
| 99.9% | 8.76 hours | ~43 minutes | "Three nines"—common target |
| 99.99% | 52.6 minutes | ~4.3 minutes | "Four nines"—enterprise grade |
| 99.999% | 5.26 minutes | ~26 seconds | "Five nines"—very expensive |

**Quick math**: Each "nine" multiplies the allowed downtime by ~0.1. Going from 99.9% to 99.99% means 10× less allowed downtime. Going to 99.999% means another 10×.

### Composite Availability: Serial Dependencies

If Service A depends on Service B, and both must be up for the user to succeed, **availability multiplies**:

```
    Availability(A and B) = Availability(A) × Availability(B)
```

**Example**:
- API gateway: 99.9%
- Auth service: 99.9%
- User service: 99.9%
- DB: 99.95%

**Combined** (all serial): 0.999 × 0.999 × 0.999 × 0.9995 ≈ **99.75%**

Each weak link reduces the total. A chain of 10 services at 99.9% each: 0.999^10 ≈ 99.0%. You've lost a nine.

### Redundancy Increases Availability

If you have **redundancy**—multiple independent components, and you only need one to work—availability improves:

```
    Availability(A or B) = 1 - (1 - A)(1 - B)
```

**Example**: Two servers, each 99.9%. Both must fail for outage:
- P(both fail) = 0.001 × 0.001 = 0.000001
- P(at least one up) = 1 - 0.000001 = **99.9999%**

**Caveat**: Only if failures are *independent*. Same datacenter, same bug, shared dependency—failures can correlate. Real redundancy often means different regions, different implementations.

### Why 99.99% is 10× Harder Than 99.9%

To go from 99.9% to 99.99%:
- You need 10× less downtime (52 min vs 8.76 hours per year)
- Requires: redundant everything, automated failover, practiced runbooks, fewer single points of failure
- Cost and complexity grow nonlinearly

**Staff-level reality**: Most products target 99.9%. Some critical systems (payment, auth) aim for 99.99%. Five nines (99.999%) is rare—reserved for telecom, financial critical path.

### SLA, SLO, SLI (Brief Intro)

| Term | Meaning | Example |
|------|---------|---------|
| **SLI** (Service Level Indicator) | What you measure | "Percentage of requests with latency < 200 ms" |
| **SLO** (Service Level Objective) | Target you aim for | "99% of requests complete in < 200 ms" |
| **SLA** (Service Level Agreement) | Contractual commitment, often with penalties | "We guarantee 99.9% uptime or credit" |

**Hierarchy**: You define SLIs (metrics). You set SLOs (targets). For external customers, you may offer SLAs (legal commitments). SLOs are usually stricter than SLAs (you want headroom).

### Planned vs Unplanned Downtime

Not all downtime counts the same. Planned maintenance (e.g., deployments, schema migrations) can be excluded from availability calculations if users are notified. Unplanned (outages, bugs, infrastructure failure) always counts. Many teams achieve 99.9% by excluding planned maintenance; true 99.9% including planned is harder—you need zero-downtime deployments, blue-green, or similar.

### Error Budgets: Availability as a Consumable Resource

An **error budget** = 1 − availability. For 99.9%, budget = 0.1% = 8.76 hours/year. You "spend" the budget on incidents. When the budget is exhausted, you freeze risky changes and focus on reliability. This creates a shared understanding: we're not aiming for perfect; we're managing a finite budget. Staff Engineers use error budgets to balance velocity and reliability.

---

## Part 6: Server Capacity — How Much Can One Server Handle?

### A Single Modern Server: Typical Specs

| Resource | Typical Range | Notes |
|----------|---------------|-------|
| **CPU** | 8–64 cores | Cloud instances: 4–96+ vCPUs |
| **RAM** | 16–256 GB | 32–64 GB common for app servers |
| **Network** | 1–10 Gbps | Often 10 Gbps in modern DCs |
| **Disk** | SSD: 100K–500K IOPS | HDD: 100–200 IOPS |

### Typical Per-Server QPS (Rough)

| Workload | QPS per Server | Notes |
|----------|----------------|-------|
| **Static file (nginx)** | 10K–100K+ | Memory-mapped, minimal logic |
| **Simple JSON API (Go/Node)** | 10K–100K | Stateless, minimal logic, cached |
| **API + DB per request** | 100–1K | DB round-trip dominates |
| **Heavy computation** | 10–100 | CPU-bound |
| **Redis (cache)** | 100K–500K | In-memory, simple ops |
| **Database (OLTP)** | 5K–50K | Depends on query complexity |
| **Database (complex queries)** | 100–1K | Joins, aggregations |

**These vary wildly** with payload size, complexity, and hardware. Use them as starting points, not gospel.

### Back-of-the-Envelope: Number of Servers

```
    Number of servers = Total QPS ÷ QPS per server
    Add redundancy: 2x for active-passive, N+1 for active-active
```

**Example**:
- 100K QPS total
- 10K QPS per server (simple API)
- 100K ÷ 10K = 10 servers
- With 2x redundancy: 20 servers

### Capacity Planning: The Full Picture

Before the worked examples, here's the mental framework Staff Engineers use:

1. **Identify the bottleneck** — Is it CPU, memory, disk I/O, or network? Different bottlenecks need different solutions.
2. **Account for redundancy** — Single points of failure are unacceptable. N+1 or 2x redundancy is typical.
3. **Plan for growth** — Design for 2–3× current scale minimum. Migration is costly; build headroom.
4. **Cost the design** — Rough cost = servers × price. 100 servers × $100/month = $10K/month. Does the business case support it?
5. **Validate with load testing** — Numbers are estimates. Load test to confirm. Staff Engineers never ship at 100% capacity.

### Full Worked Examples

#### Example 1: URL Shortener

**Assumptions**:
- 100M DAU
- 5 shortens per user per day
- 20 redirects per user per day (read-heavy)
- Peak = 4× average

**Estimation**:
- Shortens: 100M × 5 = 500M/day ≈ 5,800 QPS avg → 23K peak writes
- Redirects: 100M × 20 = 2B/day ≈ 23K QPS avg → 92K peak reads
- Read:write ≈ 4:1

**Storage** (5 years):
- 500M × 365 × 5 = 912.5B short links
- Each: short code (6 B) + long URL (100 B) + metadata (50 B) ≈ 160 B
- 912.5B × 160 B ≈ 146 TB (rough)

**Capacity**:
- Write QPS: 23K peak. At 10K per DB write instance → 3 write nodes (with replicas)
- Read QPS: 92K peak. Cache hit rate 95% → 4.6K DB reads. Read replicas: 92K ÷ 50K ≈ 2 replicas for cache misses, plus cache layer (Redis: 100K+ QPS per node, 1–2 nodes)

**Architecture**:
- Load balancer → API servers (stateless, 20–30 for 23K writes + 92K reads with cache)
- Redis cache for hot redirects
- DB: 1 primary (writes), 2–3 replicas (reads)
- Storage: 146 TB over 5 years → sharding by short code hash

#### Example 2: Chat System

**Assumptions**:
- 10M DAU
- 30 messages sent per user per day
- 100 messages received per user per day
- Peak = 5× average

**Estimation**:
- Writes: 10M × 30 = 300M msg/day ≈ 3,500 QPS avg → 17.5K peak
- Reads (fan-out): 10M × 100 = 1B reads/day ≈ 11.6K QPS avg → 58K peak

**Storage** (1 year):
- 300M × 365 = 109.5B messages
- Each message: 50 B metadata + 100 B body ≈ 150 B
- 109.5B × 150 B ≈ 16.5 TB

**Capacity**:
- WebSocket connections: 10M DAU, assume 10% concurrent = 1M connections. 10K connections per server → 100 servers for connections
- Message delivery: 17.5K writes/sec. Queue (Kafka/SQS) absorbs spikes. Workers: 17.5K ÷ 1K per worker ≈ 18 workers
- Read path: Inbox per user. Cache recent messages. DB for history. Read QPS 58K, 90% cache hit → 5.8K DB reads. Read replicas handle it.

**Architecture**:
- API gateway → WebSocket servers (100+ for 1M connections)
- Message queue (Kafka) → Worker pool (20–30 workers)
- DB: Primary + replicas, sharded by user_id when needed
- Redis: Online presence, recent messages cache

**Design decisions justified by numbers**:
- **Why 100+ WebSocket servers?** 1M concurrent connections ÷ 10K per server = 100. Add headroom for uneven distribution.
- **Why Kafka?** 17.5K write QPS with spikes. Kafka handles millions/sec. Queue absorbs bursts; workers process at steady rate.
- **Why Redis for presence?** Frequent updates (user online/offline). Redis handles 100K+ ops/sec. DB would be overwhelmed.

### Example 3: E-Commerce Product Page (Quick Estimation)

**Assumptions**: 5M DAU, 10 page views per user per day, 80% cache hit (CDN + app cache).

**Estimation**:
- 5M × 10 = 50M page views/day ≈ 580 QPS avg → 2.3K peak
- 20% miss cache = 460 QPS to origin
- Each page view: 1 API call (product details), 3–5 DB queries if uncached
- DB: 460 × 4 = 1.8K QPS. Single DB with read replica handles it easily.

**Conclusion**: At this scale, a simple architecture suffices. Cache does the heavy lifting. No sharding needed.

### Example 4: Real-Time Analytics Dashboard

**Assumptions**: 1M DAU, 50 events per user per day, events stored and queried.

**Estimation**:
- 1M × 50 = 50M events/day ≈ 580 events/sec (writes)
- Storage: 50M × 365 = 18.25B events/year. At 200 B/event = 3.65 TB/year.
- Queries: Dashboards, aggregations. Assume 1K QPS of complex analytical queries.

**Architecture**: Write path: Kafka (absorb 580/sec, batch to warehouse). Storage: Columnar DB (ClickHouse, BigQuery) or data warehouse. Query path: Pre-aggregated tables, cache popular dashboards. Different from OLTP—optimized for analytics workload.

### The Estimation Mindset: Show Your Work

In interviews and in practice, estimation is a process, not a guess. A Staff Engineer says: "I'll assume 10M DAU. Typical product: 15–25 requests per user per day. I'll use 20. So 200M requests per day. Dividing by 86,400 gives ~2,300 QPS average. Peak is usually 4×, so ~9,200 QPS. At 10K QPS per server, we need about one server for the average case, but for peak we need ~1. So 2–3 servers with redundancy."

The interviewer sees: assumptions stated, math done, conclusion derived. That's Staff-level. "We'll need a few servers" is not.

---

# Example in Depth: Sizing a Real Feature — "Trending Hashtags"

**Requirement**: Show trending hashtags on a social app; update every 5 minutes; 50M DAU; global.

**Step 1 — Volume**: 50M DAU. Assume 30% open app in a given 5-minute window → 15M views per window. So we need to **compute** trending once per 5 min and **serve** up to 15M reads in 5 min. Reads: 15M / 300 sec ≈ **50K read QPS** peak (if all in same minute). Compute: one batch job per 5 min; scan recent posts (e.g. last 1 hour), aggregate by hashtag, sort, store top 100.

**Step 2 — Storage**: Input: posts in last hour. If 1% of DAU posts per hour → 500K posts/hour; each post ~200 bytes metadata + hashtags → ~100 MB/hour raw. We don't store all—we aggregate. Output: top 100 hashtags per region (or global) → tiny, e.g. 10 KB. Store in **cache (Redis)** or **DB**. So storage is negligible; **read path** dominates.

**Step 3 — Read path**: 50K QPS for a single key or small set (e.g. "trending:global", "trending:us"). One Redis shard can do 100K+ simple gets/sec. So **one Redis instance** (or a small cluster for HA) is enough. If we store in DB, we need a cache in front—same conclusion.

**Step 4 — Write path**: One job every 5 min; writes 10 KB. Trivial. Job can run on a single worker; no distributed compute needed unless we scan petabytes.

**Step 5 — Availability**: If trending is best-effort, 99% is fine. If it's critical (e.g. ads depend on it), replicate Redis or use DB + cache with TTL 5 min so stale data is bounded.

**Takeaway**: Numbers (DAU, 5-min window, 30% open) → read QPS → Redis/cache sizing. One clear calculation chain; no guesswork. Staff engineers do this for every feature they size.

## Breadth: Estimation Edge Cases and Anti-Patterns

| Scenario | Pitfall | Better approach |
|----------|---------|-----------------|
| **Peak vs average** | Sizing for average QPS | Size for peak (often 2–4× average); state assumption (e.g. "peak 3×") |
| **Fan-out** | "1K QPS" but each request does 20 internal calls | Internal RPS = 1K × 20 = 20K; size backends and DB for 20K |
| **Growth** | Sizing for today only | "2× in 12 months"; design so you can scale (sharding, read replicas) without rewrite |
| **Availability** | "We need 99.99%" without cost awareness | 99.99% = 4 nines → multi-region, failover, runbooks; justify with business impact |
| **Latency** | Ignoring p99 | p99 can be 5–10× p50; size and timeouts for p99 so SLO is met |
| **Units** | Mixing QPS and daily volume | Convert: daily → QPS = divide by 86,400; state "peak 4× average" if needed |

**Edge cases**: **Cold start**: First request after deploy may be slow (JIT, lazy init). Don't let one slow request set SLO. **Long tail**: One slow dependency can dominate p99; design timeouts and fallbacks. **Correlated load**: Flash sales or viral events—plan for 10× or more spike; use queues, caching, and backpressure.

---

## Summary: Numbers as Design Inputs

The numbers in this chapter are design inputs. You don't memorize them—you use them to:

1. **Sanity-check**: "Can one server handle this?" → Do the math.
2. **Compare alternatives**: "Cache or more read replicas?" → Estimate cost and latency.
3. **Set targets**: "What availability do we need?" → Derive infrastructure requirements.
4. **Communicate**: "We need ~20 API servers for peak" → Stakeholders understand scope.

**Staff-Level Insight**: When you present an architecture, the numbers should justify it. "We use 10 API servers because peak QPS is 100K and each handles 10K" is Staff-level. "We'll add servers as needed" is not. Master the numbers, and your designs will be credible, defensible, and built on solid ground.

---

## Back-of-the-Envelope Cheat Sheet

Keep this mental model handy during design discussions:

| To Estimate | Formula | Example |
|-------------|---------|---------|
| **Avg QPS** | DAU × actions/day ÷ 86,400 | 10M × 20 ÷ 86,400 ≈ 2.3K |
| **Peak QPS** | Avg QPS × 3–5 | 2.3K × 4 ≈ 9.2K |
| **Storage** | Rows × row size × retention | 1B × 1 KB × 1 = 1 TB |
| **Servers** | Total QPS ÷ per-server QPS | 100K ÷ 10K = 10 |
| **With redundancy** | Servers × 2 (or N+1) | 10 × 2 = 20 |
| **Availability (serial)** | A × B × C | 0.999³ ≈ 99.7% |
| **Availability (redundant)** | 1 − (1−A)(1−B) | 2× 99.9% ≈ 99.9999% |
| **Downtime (99.9%)** | 8.76 hours/year | ~43 min/month |

### Key Constants

- 86,400 = seconds per day
- 1 million = 10^6
- 1 billion = 10^9
- 2^10 ≈ 1K, 2^20 ≈ 1M, 2^30 ≈ 1B
- L1 cache: 0.5 ns; RAM: 100 ns; SSD: 16 μs; HDD seek: 2 ms
- Same-DC RTT: ~0.5 ms; Cross-country: ~40 ms

### From Numbers to Architecture: The Decision Tree

Use your estimates to drive decisions:

- **QPS < 1K**: Single server, maybe two for redundancy. Simple.
- **QPS 1K–10K**: Add cache, read replicas. Stateless app servers behind LB.
- **QPS 10K–100K**: Multiple app server pools, cache layer, DB replicas. Consider queues for async work.
- **QPS 100K+**: Sharding, multi-region, specialized infrastructure. Staff-level problem.

- **Storage < 100 GB**: Single DB. No problem.
- **Storage 100 GB–1 TB**: Single DB or replicas. Monitor growth.
- **Storage 1–10 TB**: Plan sharding. Partition key design matters.
- **Storage 10 TB+**: Distributed storage (S3, GCS, sharded DBs). Archival strategy.

- **Availability 99%**: Single region, best effort. Fine for internal tools.
- **Availability 99.9%**: Redundant components, health checks, runbooks. Standard for user-facing.
- **Availability 99.99%+**: Multi-region, automated failover, practice drills. Reserved for critical path.

### Interview Tips: Showing Your Work

In a system design interview:
1. **State assumptions**: "I'll assume 10M DAU and 20 requests per user per day."
2. **Do the math out loud**: "10M × 20 = 200M requests per day. 200M ÷ 86,400 ≈ 2,300 QPS average."
3. **Apply peak factor**: "Peak is typically 4×, so ~9,200 QPS."
4. **Derive architecture**: "At 9K QPS, with 10K per server, we need about 1 server—plus redundancy, so 2–3."

This demonstrates Staff-level fluency. The interviewer sees that your design is grounded in numbers, not guesswork.

### Estimation Practice Problems: 5 Worked Solutions

#### Problem 1: Twitter — Estimate QPS for Tweet Reads and Writes

**Assumptions**: 400M MAU, 25% DAU = 100M DAU. Each user posts 3 tweets/day (writes). Each user views 80 tweets/day (reads). Peak = 4× average.

**Read QPS**:
- 100M × 80 = 8B reads/day
- 8B ÷ 86,400 ≈ 92,600 QPS average
- Peak: 92,600 × 4 ≈ **370K read QPS**

**Write QPS**:
- 100M × 3 = 300M writes/day
- 300M ÷ 86,400 ≈ 3,470 QPS average
- Peak: 3,470 × 4 ≈ **14K write QPS**

**Read:write ratio**: ~27:1. Heavily read-dominated. Cache and read replicas critical.

---

#### Problem 2: YouTube — Estimate Storage for Video Uploads

**Assumptions**: 500M DAU. 1% upload daily = 5M uploads/day. Average video: 10 minutes at 5 Mbps = 10 × 60 × 5 ÷ 8 ≈ 375 MB. Transcode to 3 renditions (720p, 480p, 360p); total ~2× source = 750 MB stored per video. Retention: 5 years.

**Storage**:
- 5M × 365 × 5 = 9.125B videos over 5 years
- 9.125B × 750 MB ≈ **6.8 EB** (exabytes)

**Refined**: Not all videos watched long-term. Assume 20% "evergreen," 80% low-quality/short. Average stored: 750 MB × 0.2 + 200 MB × 0.8 ≈ 310 MB. 9.125B × 310 MB ≈ **2.8 EB**. Still enormous. Object storage (S3/GCS) with lifecycle policies. Cold tier for old, rarely watched content.

---

#### Problem 3: WhatsApp — Estimate Message Throughput

**Assumptions**: 2B MAU, 50% DAU = 1B DAU. 50 messages sent per user per day. Average message: 100 B (text). Peak = 5× (evening hours).

**Throughput**:
- 1B × 50 = 50B messages/day
- 50B ÷ 86,400 ≈ 579K messages/sec average
- Peak: 579K × 5 ≈ **2.9M messages/sec**

**Fan-out**: Average 2.5 recipients per message (group chats). Delivery operations: 2.9M × 2.5 ≈ **7.25M delivery ops/sec** at peak.

**Architecture**: Write path: message queue (Kafka/Kinesis) to absorb. Workers fan out to recipients. Read path: each recipient fetches inbox. End-to-end encryption adds CPU but not storage for content. Metadata and routing tables scale with conversations and participants.

---

#### Problem 4: Uber — Estimate Ride Request QPS

**Assumptions**: 130M MAU, 20% DAU = 26M DAU. Each user requests 0.5 rides/day on average (some take multiple, many take none). Peak = 3× (rush hour).

**QPS**:
- 26M × 0.5 = 13M ride requests/day
- 13M ÷ 86,400 ≈ 150 QPS average
- Peak: 150 × 3 ≈ **450 ride request QPS**

**Secondary operations**: Each request triggers: matchmaking (find driver), ETA calculation, pricing, notifications. 10× internal amplification → 4.5K internal QPS at peak. Geolocation updates from drivers: continuous, much higher—50 updates/sec per active driver. 1M active drivers × 1 update/10 sec = 100K location updates/sec. That dominates the system.

**Architecture**: Ride requests are modest. Real-time driver location and matching are the heavy paths. Geospatial indexes (Redis, PostGIS), WebSockets for live updates.

---

#### Problem 5: Google Search — Estimate Query Throughput

**Assumptions**: 5B searches/day globally (public estimates vary; use as given). Peak = 2× average (business hours skew). Assume uniform across 86,400 seconds for average.

**QPS**:
- 5B ÷ 86,400 ≈ 57,870 QPS average
- Peak: 57,870 × 2 ≈ **116K QPS**

**Per-query work**: Query parsing, index lookup (distributed), ranking, snippet generation, ads lookup. Multiple backend calls. 20× internal fan-out → 2.3M backend operations/sec at peak.

**Caching**: Search results are heavily cached. Same query from many users (trending) → high cache hit. Unique long-tail queries → index servers. Architecture: query front-end, cache layer, index shards, ranking service. Each layer scales independently.

---

### Practice Exercises (Do These Mentally)

1. **Twitter-like feed**: 500M MAU, 30% DAU. Each user views 50 tweets/day, each tweet 1 KB. Estimate daily read QPS and 1-year storage.
2. **Video upload**: 10M uploads/day, 100 MB average. Estimate storage for 90-day retention.
3. **Payment system**: 1M transactions/day, peak 5×. Each transaction does 3 DB writes. Estimate write QPS.
4. **Multi-region**: 99.99% target. Two regions, each 99.95%. Both must be up—what's combined availability?

*Sanity-check answers*: (1) 150M DAU × 50 = 7.5B reads/day ≈ 87K QPS; 7.5B × 1 KB × 365 ≈ 2.7 PB. (2) 10M × 100 MB × 90 ≈ 90 PB. (3) 1M × 3 ÷ 86,400 ≈ 35 writes/sec avg; 175 peak. (4) 0.9995² ≈ 99.9%.

### Why Orders of Magnitude Matter in Interviews

In a 45-minute system design interview, the numbers you derive in the first 10 minutes shape everything. If you estimate 100 QPS when the real answer is 100K QPS, you'll design a single-server solution when you need hundreds. Getting the order of magnitude right (1K vs 100K vs 1M) is more important than precision. A design for 50K QPS when the real number is 30K is fine. A design for 5K when it's 500K is a fail.

### Common Estimation Mistakes

| Mistake | What Happens | Fix |
|---------|--------------|-----|
| **Ignore peak** | Design for average; peak overwhelms | Use 3–5× peak factor |
| **Forget read/write split** | Assume all traffic is mixed | Separate read and write QPS |
| **Underestimate storage growth** | Plan for 1 year; data grows 10× | Model growth; plan for 2–3 years |
| **Assume linear scaling** | 10 servers = 10× capacity | Overhead; often 7–8× effective |
| **Ignore fan-out** | 10K user QPS = 10K backend QPS | Account for internal calls |

### Cost Estimation: Rough Numbers

Infrastructure cost is often a constraint. Rough cloud pricing: App server (4 vCPU, 16 GB) $50–150/month. Redis (8 GB) $50–200. Database primary $150–500. For 20 app servers + 2 Redis + 1 DB + 2 replicas + 1 LB: roughly $2K–5K/month. At 100K QPS, that's $0.02–0.05 per 1K requests. Staff Engineers do this math to validate the design is affordable.

---

## Appendix: Latency Numbers Deep Dive

Jeff Dean's latency numbers are from a specific era. Modern hardware has improved. The *ratios* matter more than absolute values: RAM is ~100× slower than L1; SSD is ~1000× slower than RAM; network is ~1000× slower than local disk. These ratios drive design: keep hot data in memory, minimize network hops, batch when possible.

### Expanded Jeff Dean's Numbers with Practical Examples

| Operation | Latency | Practical Example |
|-----------|---------|-------------------|
| L1 cache reference | 0.5 ns | Single CPU cycle; in-CPU data |
| L2 cache reference | 7 ns | Small lookup table in L2 |
| Main memory (RAM) | 100 ns | In-process hash map lookup |
| SSD random read | 16 μs | Single row by primary key |
| HDD seek | 2 ms | Legacy disk; avoid for OLTP |
| Round-trip same datacenter | 0.5 ms | Service A → Service B in same AZ |
| Round-trip cross-datacenter (US) | 40 ms | us-east-1 → us-west-2 |
| Round-trip cross-continent | 100–200 ms | US → EU or Asia |

**Practical implication**: A single cross-region call adds 40–100 ms. A request that makes 5 cross-region calls: 200–500 ms just from network. Keep the critical path local.

### Network Latency Between AWS Regions (Approximate RTT)

| From / To | us-east-1 | us-west-2 | eu-west-1 | ap-southeast-1 |
|-----------|-----------|-----------|-----------|----------------|
| **us-east-1** | <1 ms | 70 ms | 75 ms | 200 ms |
| **us-west-2** | 70 ms | <1 ms | 150 ms | 140 ms |
| **eu-west-1** | 75 ms | 150 ms | <1 ms | 130 ms |
| **ap-southeast-1** | 200 ms | 140 ms | 130 ms | <1 ms |

*Values are typical; actual latency varies by path and load.*

**Design implication**: Multi-region active-active adds latency. Route users to nearest region. Replicate data asynchronously; don't make synchronous cross-region reads on the hot path.

### How CDN Reduces Latency

| Scenario | Without CDN | With CDN |
|----------|-------------|----------|
| User in Tokyo, origin in us-east-1 | 200+ ms RTT to origin | 20–50 ms to nearest edge (Tokyo POP) |
| Static asset (JS, CSS, image) | 200 ms × N assets = seconds | Parallel fetch from edge, 20 ms each |
| Cache hit at edge | N/A | 20–50 ms end-to-end |
| Cache miss | Full origin round-trip | Edge fetches from origin once; subsequent requests served from edge |

**Rule of thumb**: CDN typically reduces latency by 5–10× for globally distributed users. For static content, 90%+ of requests hit edge. For dynamic content, edge caching is harder—use edge compute (Cloudflare Workers, Lambda@Edge) for personalized-but-cacheable logic.

### Why p99 Matters More Than p50: A Real Production Incident

**The incident**: A payments API had p50 latency of 80 ms and p99 of 2.5 seconds. Dashboard looked "fine"—median was acceptable. Support tickets piled up: "Payment timed out." "Checkout hung."

**Root cause**: 1% of requests hit a code path that did 6 sequential DB calls (N+1 in disguise). Each DB call: p99 of 200 ms (connection pool exhaustion, cold cache). 6 × 200 ms = 1.2 s from DB alone. Add network, serialization: 2.5 s.

**Impact**: At 10K QPS, 1% = 100 requests/sec in the tail. That's 6,000 users per minute experiencing timeouts. Unacceptable. p50 hid the problem.

**Fix**: Identified the N+1 path. Batched queries. p99 dropped to 150 ms. Incident resolved.

**Staff-level lesson**: Always instrument and alert on p95 and p99. p50 can mask tail latency that affects millions of users at scale.

### Tail Latency Amplification: Worked Math Example

**Setup**: Service A calls B, C, D in parallel. Each has p99 = 100 ms. A waits for all three.

**Naive hope**: p99(total) = 100 ms (max of the three).

**Reality**: To get p99(total) = 100 ms, *all three* must complete in ≤100 ms. Each has 1% chance of exceeding 100 ms. Probability all three ≤100 ms = 0.99³ ≈ 0.97. So 3% of requests exceed 100 ms. p97(total) ≈ 100 ms; p99(total) is higher.

**Worse case**: If B, C, D have *correlated* slow paths (e.g., same DB under load), when one is slow, others might be too. p99(total) can reach 150–200 ms or more.

**Sequential case**: A → B → C → D. p99(total) = p99(B) + p99(C) + p99(D) = 300 ms. Latencies add. One slow dependency blows the budget.

**Mitigation**: Set per-dependency budgets. If total budget is 200 ms, each of 5 dependencies gets ~40 ms p99 budget. Use timeouts. Fail fast on slow dependencies. Consider parallel where possible, but account for tail amplification.

## Appendix: Availability Deep Dive

**Measuring availability**: "99.9% availability" needs a definition. Most use successful_requests / total_requests. Be explicit. **Multi-region**: To achieve 99.99%+, you typically need multi-region. Single region: one datacenter fire can take you down. Multi-region: failures isolated. Trade-off: replication lag, consistency challenges, cost. Staff Engineers weigh the availability gain against complexity.

### Compound Availability Examples

**Example 1: E-Commerce Checkout Chain**

Checkout requires: API gateway → Auth service → Cart service → Payment service → Order service → Inventory service. All must succeed for the user to complete. Serial availability:

```
    A_total = A_gateway × A_auth × A_cart × A_payment × A_order × A_inventory
    A_total = 0.999 × 0.999 × 0.999 × 0.9995 × 0.999 × 0.999
    A_total ≈ 0.9975 ≈ 99.75%
```

Six services at 99.9% each → 99.75% combined. You've lost a quarter of a nine. Add a seventh and you're at 99.65%.

**Example 2: Redundancy Helps**

Payment service has 2 independent replicas (active-active). Both must fail for payment to fail:

```
    P(both fail) = 0.001 × 0.001 = 0.000001
    A_payment = 1 - 0.000001 = 99.9999%
```

Caveat: "Independent" means different failure domains—different AZs, different regions. Same bug or same upstream dependency can correlate failures.

**Example 3: Mixed Serial and Parallel**

User request: API → (Auth AND UserService) → DB. Auth and UserService can be called in parallel. Both must succeed. Then DB.

```
    A_parallel = A_auth × A_user  (both must succeed)
    A_total = A_api × A_parallel × A_db
```

Parallel doesn't help availability when both must succeed—it helps latency. For availability, the weak link in the parallel pair dominates.

### Service Dependency Chains

Map your dependency graph. A chain of 10 services at 99.9% each:

```
    A_chain = 0.999^10 ≈ 0.990
```

You're at 99.0%—one nine lost. Every additional service costs you. Reduce the chain: consolidate services, or make some calls optional (best-effort analytics, etc.).

### How to Improve Availability

| Strategy | How It Works | Example |
|----------|--------------|---------|
| **Redundancy** | Multiple instances; one failing doesn't take down the system | 3 API servers behind LB; 1 can die |
| **Failover** | On failure, promote standby to active | Primary DB fails → replica promotes |
| **Health checks** | LB stops routing to unhealthy instances | HTTP health endpoint; mark unhealthy after 3 fails |
| **Circuit breaker** | Stop calling failing dependency; fail fast | Downstream returns 5xx → open circuit; don't hammer it |
| **Graceful degradation** | Serve reduced functionality when dependency is down | Recommend service down → show cached recommendations or "unavailable" |
| **Timeouts** | Don't wait forever; fail and retry or degrade | 500 ms timeout on DB; return fallback or 503 |

### Error Budget Consumption Tracking Example

**SLO**: 99.9% availability = 8.76 hours downtime per year. Error budget = 8.76 hours.

**Monthly budget**: 8.76 ÷ 12 ≈ 43 minutes per month.

**Tracking**:

| Week | Incident | Downtime | Budget consumed | Remaining |
|------|----------|----------|------------------|-----------|
| 1 | DB replica lag caused 5xx | 12 min | 12 min | 31 min |
| 2 | Deployment bad rollout | 8 min | 8 min | 23 min |
| 3 | No incidents | 0 | 0 | 23 min |
| 4 | Cache stampede | 20 min | 20 min | 3 min |

**Action**: After week 4, budget nearly exhausted. Freeze risky changes. Focus on reliability. Postmortems. Fix root causes. Next month: fresh budget. If you consistently consume 100% of budget, either improve reliability or relax the SLO (and communicate to stakeholders).

**Staff-level practice**: Track budget consumption weekly. Set alerts at 50% and 80%. When budget is low, prioritize reliability work over feature work. Use error budget as a shared language with product: "We've used 80% of our downtime budget—we need to pause risky deployments and focus on stability."
