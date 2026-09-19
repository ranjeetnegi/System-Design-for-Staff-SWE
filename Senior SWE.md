# Google Senior SWE (L5) — Interview Prep
> Target: Google India (Bangalore / Hyderabad) | Pace: deep reader, ~2× time estimates

---

## What Google Tests at L5

| Round | Goal |
|-------|------|
| Coding × 2 | Done ✅ |
| System Design × 1–2 | Design one system clearly, explain trade-offs, drive 45 min |
| Behavioral / Googleyness × 1 | Team-level impact, good judgment, collaboration |

---

## L5 Reading Plan — Optimized for Senior SWE

> **Total: ~50 chapters** | **Reading time: 120-140 hours at normal pace**
> 
> This plan includes ONLY L5-scoped content. All L6 chapters are excluded.

---

### Phase 1: Foundations (Must Read — 3 chapters, ~8 hours)

Read first, before anything else.

| Chapter | What it covers | Priority |
|---------|---------------|----------|
| [Ch13 — Numbers & Estimation](Section1/Chapter_13_Numbers_Estimation.md) | QPS, storage, bandwidth math — do this fluently | 🔴 Critical |
| [Ch9 — Systems, Servers, Clients](Section1/Chapter_9_Systems_Servers_Clients.md) | HTTP, TCP, DNS, load balancers — fill any gaps | 🔴 Critical |
| [Ch14 — Core Building Blocks](Section1/Chapter_14_Core_Building_Blocks.md) | Cache, queue, CDN, blob storage — know when to use each | 🔴 Critical |

---

### Phase 2: Interview Framework (Must Read — 5 chapters, ~12 hours)

How to structure 45 minutes. Memorize this before doing any case studies.

| Chapter | What it covers | Priority |
|---------|---------------|----------|
| [Ch15 — System Design Framework](Section2/Chapter_15_System_Design_Framework.md) | The 5-phase structure — this is your template | 🔴 Critical |
| [Ch16 — Phase 1: Users & Use Cases](Section2/Chapter_16_Phase_1_Users_and_Use_Cases.md) | How to clarify requirements in the first 5 min | 🔴 Critical |
| [Ch17 — Phase 2: Functional Requirements](Section2/Chapter_17_Phase_2_Functional_Requirements.md) | Scoping without going in circles | 🔴 Critical |
| [Ch18 — Phase 3: Scale & Capacity Planning](Section2/Chapter_18_Phase_3_Scale_Capacity_Planning.md) | Back-of-envelope math, live in the interview | 🔴 Critical |
| [Ch20 — Phase 4&5: Non-Functional Requirements](Section2/Chapter_20_Phase_4_and_5_Non_Functional_Requirements.md) | Availability, consistency, latency targets | 🔴 Critical |

---

### Phase 3: Distributed Systems Core (Must Read — 4 chapters, ~16 hours)

What interviewers probe on follow-ups. These concepts appear in every L5 interview.

| Chapter | What it covers | Priority |
|---------|---------------|----------|
| [Ch22 — Consistency Models](Section3/Chapter_22_Consistency_Models.md) | Strong vs eventual — when each matters and what breaks | 🔴 Critical |
| [Ch23 — Replication & Sharding](Section3/Chapter_23_Replication_and_Sharding.md) | Leader-follower, consistent hashing, hot shards | 🔴 Critical |
| [Ch25 — Backpressure, Retries, Idempotency](Section3/Chapter_25_Backpressure_Retries_and_Idempotency.md) | Circuit breakers, exponential backoff, exactly-once | 🔴 Critical |
| [Ch28 — CAP Theorem: Applied](Section3/Chapter_28_CAP_Theorem_Applied_Case_Studies.md) | Apply CAP to a real system — don't just recite it | 🔴 Critical |

---

### Phase 4: Data Systems Core (Must Read — 5 chapters, ~24 hours)

**Critical Foundation:** These are the building blocks for 90% of L5 designs. Read BEFORE doing Section 5 case studies.

| Chapter | Why it's critical | Priority |
|---------|------------------|----------|
| [Ch30 — Databases](Section4/Chapter_30_Databases_Choosing_Using_and_Evolving_Data_Stores.md) | SQL vs NoSQL, indexing, sharding — every design needs this | 🔴 Critical |
| [Ch31 — Database Internals](Section4/Chapter_31_Database_Internals_Deep_Dive.md) | B-tree, WAL, MVCC — interviewers probe this | 🔴 Critical |
| [Ch33 — Caching at Scale](Section4/Chapter_33_Caching_at_Scale_Redis_CDN_and_Edge_Systems.md) | Redis, eviction, cache stampede — 80% of L5 designs | 🔴 Critical |
| [Ch34 — Redis Internals](Section4/Chapter_34_Redis_and_Cache_Internals.md) | Single-thread model, persistence, atomic operations | 🔴 Critical |
| [Ch35 — Event-Driven / Kafka](Section4/Chapter_35_Event_Driven_Architectures_Kafka_and_Streams.md) | Topics, partitions, consumer groups — async designs | 🔴 Critical |

---

### Phase 5: Optional Data Systems (Read if Time — 3 chapters, ~9 hours)

| Chapter | What it adds | Priority |
|---------|-------------|----------|
| [Ch32 — Data Encoding](Section4/Chapter_32_Data_Encoding_and_Schema_Evolution.md) | Protobuf, schema evolution — API versioning | 🟡 Optional |
| [Ch36 — Kafka Internals](Section4/Chapter_36_Kafka_Internals.md) | ISR, log compaction, consumer lag | 🟡 Optional |
| [Ch42 — Deployment Strategies](Section4/Chapter_42_Deployment_Strategies_and_Operations.md) | Blue/green, canary, rollback | 🟡 Optional |

---

### Phase 6: Case Studies — PICK 12 OF 27 (~48 hours)

**Strategy:** Do each as a 45-minute timed mock BEFORE reading the chapter. Then read to fill gaps.

**Core 12 (covers all major patterns):**

| Chapter | Core concept | Why this one |
|---------|-------------|--------------|
| [Ch49 — URL Shortener](Section5/Chapter_49_URL_Shortener.md) | Hashing, redirect, analytics | Warmup — easiest |
| [Ch50 — Rate Limiter](Section5/Chapter_50_Single_Region_Rate_Limiter.md) | Token bucket, sliding window | Most common L5 question |
| [Ch51 — Distributed Cache](Section5/Chapter_51_Distributed_Cache_Single_Cluster.md) | Eviction, stampede, TTL | Cache in every interview |
| [Ch53 — Notification System](Section5/Chapter_53_Notification_System.md) | Push/pull, fan-out | Tests async thinking |
| [Ch57 — Background Job Queue](Section5/Chapter_57_Background_Job_Queue.md) | Retry, dead-letter queue | Async processing pattern |
| [Ch58 — Payment Flow](Section5/Chapter_58_Payment_Flow.md) | Idempotency, double-charge | Critical correctness |
| [Ch60 — Real-Time Chat](Section5/Chapter_60_Real_Time_Chat.md) | WebSocket, presence | Real-time pattern |
| [Ch62 — Web Crawler](Section5/Chapter_62_Web_Crawler.md) | URL frontier, Bloom filter | Deduplication at scale |
| [Ch63 — Proximity Service](Section5/Chapter_63_Proximity_Service.md) | GeoHash, QuadTree | Geo/location pattern |
| [Ch65 — Key-Value Store](Section5/Chapter_65_Key_Value_Store.md) | LSM tree, consistent hashing | Storage fundamentals |
| [Ch68 — Ride Sharing](Section5/Chapter_68_Ride_Sharing.md) | Matching, state machine | Complex state |
| [Ch70 — Ticketing System](Section5/Chapter_70_Ticketing_System.md) | Flash sale, atomic operations | High concurrency |

**Skip these 15 for L5 (do only if extra time):**

Ch52, 54, 55, 56, 59, 61, 64, 66, 67, 69, 71, 72, 73, 74, 75

---

### Phase 7: Google Systems (6 chapters, ~18 hours)

**Critical for Google loops.** Reference these naturally in interviews.

| Chapter | What to know | Priority |
|---------|-------------|----------|
| [Ch45 — Google Systems Overview](Section4/Chapter_45_Google_Foundational_Systems.md) | Read FIRST — how they fit together | 🔴 Critical |
| [Ch94 — GFS](Section6/Chapter_94_GFS_Google_File_System.md) | Chunk servers, master, fault tolerance | 🔴 Critical |
| [Ch95 — Bigtable](Section6/Chapter_95_Bigtable.md) | Wide-column, SSTable, row key design | 🔴 Critical |
| [Ch96 — MapReduce](Section6/Chapter_96_MapReduce.md) | Map/reduce phases, compare to Spark | 🔴 Critical |
| [Ch97 — Chubby](Section6/Chapter_97_Chubby.md) | Distributed locking vs ZooKeeper | 🟡 Optional |
| [Ch98 — Spanner](Section6/Chapter_98_Spanner.md) | TrueTime, global SQL — skim high-level only | 🟡 Optional |

**Skip for L5:** Ch47 (Kubernetes) — unless applying for infra/platform role

---

### Phase 8: Behavioral + Offer (2 chapters, ~8 hours)

Do in final 2 weeks before interview.

| Chapter | What it covers | Priority |
|---------|---------------|----------|
| [Ch126 — Behavioral Interview](Section8/Chapter_126_Behavioral_Leadership_Interview.md) | STAR stories, Googleyness, team-level scope | 🔴 Critical |
| [Ch127 — Offer Negotiation](Section8/Chapter_127_Offer_Negotiation.md) | RSU, joining bonus, notice period buyout | 🔴 Critical |

---

## ❌ L6 Chapters — SKIP for L5

These are explicitly excluded from the L5 plan. Read only if targeting L6 or have extra time.

### Section 0 — Staff Mindset (L6 Only)
- Ch1-8: Staff Engineer evaluation, cross-team scope, ambiguity handling

### Section 3 — Advanced Distributed (L6 Only)
- Ch24: Leader Election & Distributed Locks
- Ch27: Failure Models
- Ch29: Advanced Distributed Systems (CRDTs, vector clocks)

### Section 4 — Advanced Infra (L6 Only)
- Ch37: Batch Processing
- Ch38: Multi-Region Systems
- Ch39: Data Locality & Compliance
- Ch40: Cost Efficiency
- Ch41: System Evolution & Migrations
- Ch43: Service Mesh
- Ch44: ML System Design
- Ch46: Data Warehouse / OLAP
- Ch47: Kubernetes Internals
- Ch48: Consensus Deep Dive

### Section 6 — L6 Case Studies (L6 Only)
- Ch76-93: Staff-level case studies (all Section 6)
- Ch99: Borg
- Ch100-107: Advanced case studies

### Section 7 — Engineering Craft (L6 Only)
- Ch108-124: All Section 7 chapters (debugging, migrations, code review, etc.)

---

---

## Time Estimates by Reading Speed

| Phase | Chapters | 1X (normal) | 0.5X (slow) |
|-------|----------|-------------|-------------|
| Foundations | 3 | 8h | 16h |
| Framework | 5 | 12h | 24h |
| Distributed Core | 4 | 16h | 32h |
| Data Systems (must) | 5 | 24h | 48h |
| Data Systems (opt) | 3 | 9h | 18h |
| **12 Case Studies** | 12 | 24h | 48h |
| Google Systems | 6 | 18h | 36h |
| Behavioral + Offer | 2 | 8h | 16h |
| **Reading Total** | **40** | **119h** | **238h** |
| **Mocks + Practice** | — | **40h** | **40h** |
| **GRAND TOTAL** | **40** | **159h** | **278h** |

### At 7 hours/week
- **Normal reader (1X):** 23 weeks (~5.5 months)
- **Slow reader (0.5X):** 40 weeks (~9 months)

**Recommendation for slow readers:** Focus on exercises > reading. Cut optional chapters. Budget 6 months minimum.

---

## Behavioral — 5 Stories to Prepare

Build one story for each type. 2–3 minutes each, said out loud.

| Story type | What Google wants to see |
|-----------|--------------------------|
| Challenging project you led | You drove it, made decisions, unblocked people |
| Disagreement with teammate / manager | Data-driven, respectful, committed either way |
| Project that failed or went wrong | Self-awareness, no blaming, what changed |
| Helped someone on your team grow | Genuine, specific — mentoring, pairing, reviews |
| Went beyond what was asked | Proactive ownership, noticed a gap and fixed it |

---

## Reading Order Summary (L5 Only)

**Week 1-2:** Foundations (Ch13, 9, 14)  
**Week 3-4:** Framework (Ch15-20)  
**Week 5-7:** Distributed Systems (Ch22, 23, 25, 28)  
**Week 8-11:** Data Systems (Ch30-35)  
**Week 12-23:** 12 Case Studies + 8-10 timed mocks  
**Week 24-26:** Google Systems (Ch45, 94-98)  
**Week 27-28:** Behavioral (Ch126, 127)  
**Week 29-30:** Final polish + 5 more mocks  

**Total: 30 weeks for slow readers at 7h/week**

---

## Which Level to Target — L5 or L6?

With 11 years total / 8 years backend, you are at the L5/L6 boundary. Use this to decide:

| Signal | Level |
|--------|-------|
| Current title: Senior Engineer, led projects your team executed | **L5** |
| Current title: Staff / Principal / Architect, or designed systems adopted across teams | **L6** |
| Mentored senior engineers, influenced technical direction beyond your team | **L6** |
| Strong backend depth but scope mostly within one team | **L5** |

**Practical approach:** Interview targeting L5, but perform at L6 depth in system design and behavioral rounds. Google's Hiring Committee can bump you up one level — a strong L5 loop regularly becomes an L6 offer. The reverse doesn't work: a missed L6 loop is a No Hire, not a fallback L5.

---

## Salary — Google India (with 11 years experience)

Your experience puts you at the upper end of the band. These are realistic 2025 numbers:

### L5 (Senior SWE) — upper band for experienced hire

| Component | Range | Notes |
|-----------|-------|-------|
| Fixed (base) | ₹55–75 LPA | Paid monthly in INR |
| RSU / year | ₹25–42 LPA equiv. | $120–200K 4-yr grant in USD; vests 25%/year |
| Variable pay | ₹8–14 LPA | ~15–20% of base, paid annually |
| **Total CTC** | **₹90–131 LPA** | Year 1; grows if stock appreciates |

### L6 (Staff SWE) — if you land at this level

| Component | Range | Notes |
|-----------|-------|-------|
| Fixed (base) | ₹70–100 LPA | |
| RSU / year | ₹42–84 LPA equiv. | $200–400K 4-yr grant in USD |
| Variable pay | ₹12–20 LPA | |
| **Total CTC** | **₹124–204 LPA** | |

> Verify on [levels.fyi](https://www.levels.fyi) → India → Google → filter by your YOE before negotiating. Numbers shift with USD/INR rate and stock price.

**Why earlier numbers looked low:** RSU at Google is denominated in USD. At current USD/INR (~₹84), a $150K grant = ₹1.26 Cr total = ₹31.5 LPA/year — that alone beats most Paytm senior engineering packages.

---

## Negotiation — 4 Levers (India)

1. **RSU grant** — biggest lever. Negotiate the total 4-year grant, not the per-year number. Every $10K extra grant = ₹2.1 LPA more per year.
2. **Joining bonus** — your 90-day notice period costs you ~3 months salary + variable payout. Google should cover this. Always ask.
3. **Notice period buyout** — Google sometimes pays your current employer so you can join in 30 days instead of 90.
4. **Base salary** — tighter band, but worth one ask.

**Scripts:**

```
After offer — never accept on the call:
"Thank you — can I have 2–3 days to review with my family?"

On RSU — lead with this:
"The fixed pay looks fair. I was hoping the total RSU grant
could be closer to $X (4-year). Is there flexibility there?"

On joining bonus:
"I have a 90-day notice period and will forfeit my variable
payout in [month]. A joining bonus of ₹Y would cover that gap."

With a competing offer:
"I have an offer from [company] at ₹X LPA total.
I prefer Google — can we close the gap on RSU or joining bonus?"
```

---

## Google India Process

```
Loop (5 rounds, often virtual)
    ↓
Hiring Committee review (1–3 weeks)
    ↓
Team matching — Bangalore / Hyderabad
    ↓
Background verification (BGV) — 2–4 weeks, prepare documents
    ↓
Offer call → negotiate → sign
```

**Bangalore teams:** Google Pay, Maps, Search infra, Cloud, YouTube, Ads
**Tell recruiter your notice period upfront** — they plan joining date around it.

---

## Summary: What Changed in This L5-Only Plan

### ✅ Kept (40 chapters)
- All foundations, framework, distributed systems core
- All data systems (databases, Redis, Kafka)
- **12 of 27** Section 5 case studies (removed 15)
- Google systems (GFS, Bigtable, MapReduce, Chubby, Spanner basics)
- Behavioral + offer chapters

### ❌ Removed (88 chapters)
- **Section 0:** All 8 Staff mindset chapters (L6 only)
- **Section 3:** 3 advanced chapters (leader election, failure models, CRDTs)
- **Section 4:** 10 advanced infra chapters (multi-region, migrations, service mesh, etc.)
- **Section 5:** 15 case studies (kept only 12 with diverse patterns)
- **Section 6:** All 32 Staff case studies + 7 advanced Google systems
- **Section 7:** All 17 engineering craft chapters (L6 only)

### Result
- **Before:** 128 chapters, 960K lines, 300+ hours
- **After:** 40 chapters, ~160K lines, 160 hours (normal) / 280 hours (0.5X)
- **Time saved:** 50-60% for slow readers

---

*Google L5 | India (Bangalore / Hyderabad) | L5-scoped only | Updated 2026-09-17*
