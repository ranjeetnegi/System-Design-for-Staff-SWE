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

## Chapters — Basic to Advanced

### 1. Foundations (read first, non-negotiable)

| Chapter | What it covers |
|---------|---------------|
| [Ch13 — Numbers & Estimation](Section1/Chapter_13_Numbers_and_Estimation.md) ✅ | QPS, storage, bandwidth math — do this fluently |
| [Ch9 — Systems, Servers, Clients](Section1/Chapter_09_Systems_Servers_Clients.md) ✅ | HTTP, TCP, DNS, load balancers — fill any gaps |
| [Ch14 — Core Building Blocks](Section1/Chapter_14_Core_Building_Blocks.md) ✅ | Cache, queue, CDN, blob storage — know when to use each |

### 2. The Interview Framework (how to structure 45 minutes)

| Chapter | What it covers |
|---------|---------------|
| [Ch15 — System Design Framework](Section2/Chapter_15_System_Design_Framework.md) ✅ | The 5-phase structure — memorise this |
| [Ch16 — Phase 1: Users & Use Cases](Section2/Chapter_16_Phase_1_Users_and_Use_Cases.md) ✅ | How to clarify requirements in the first 5 min |
| [Ch17 — Phase 2: Functional Requirements](Section2/Chapter_17_Phase_2_Functional_Requirements.md) ✅ | Scoping without going in circles |
| [Ch18 — Phase 3: Scale & Capacity Planning](Section2/Chapter_18_Phase_3_Scale_and_Capacity_Planning.md) ✅ | Back-of-envelope math, live in the interview |
| [Ch20 — Phase 4&5: Non-Functional Requirements](Section2/Chapter_20_Phase_4_and_5_Non_Functional_Requirements.md) ✅ | Availability, consistency, latency targets |

### 3. Distributed Systems Core (what interviewers probe on follow-ups)

| Chapter | What it covers |
|---------|---------------|
| [Ch22 — Consistency Models](Section3/Chapter_22_Consistency_Models.md) ✅ | Strong vs eventual — when each matters and what breaks |
| [Ch23 — Replication & Sharding](Section3/Chapter_23_Replication_and_Sharding.md) ✅ | Leader-follower, consistent hashing, hot shards |
| [Ch25 — Backpressure, Retries, Idempotency](Section3/Chapter_25_Backpressure_Retries_Idempotency.md) ✅ | Circuit breakers, exponential backoff, exactly-once |
| [Ch28 — CAP Theorem: Applied](Section3/Chapter_28_CAP_Theorem_Applied.md) ✅ | Apply CAP to a real system — don't just recite it |

### 4. Data Systems Core (building blocks every L5 design assumes)

These chapters are the hidden prerequisite for Section 5. Redis appears in 80% of L5 designs. Kafka appears in async/notification/payment designs. Databases appear in every single design. Read these before attempting case studies.

**Must-read (do in order):**

| Chapter | Why it's critical |
|---------|-----------------|
| [Ch30 — Databases](Section4/Chapter_30_Databases.md) ✅ | SQL vs NoSQL choice, indexing, sharding basics — every design has a DB |
| [Ch31 — Database Internals](Section4/Chapter_31_Database_Internals.md) ✅ | B-tree, WAL, MVCC — interviewers probe this in follow-ups |
| [Ch33 — Caching at Scale](Section4/Chapter_33_Caching_at_Scale.md) ✅ | Redis, eviction policies, cache stampede — appears in 80% of L5 designs |
| [Ch34 — Redis Internals](Section4/Chapter_34_Redis_Internals.md) ✅ | Single-thread model, persistence, why INCR is atomic |
| [Ch35 — Event-Driven / Kafka](Section4/Chapter_35_Event_Driven_Architecture_Kafka.md) ✅ | Topics, partitions, consumer groups — async designs require this |

**Read if time allows:**

| Chapter | What it adds |
|---------|------------|
| [Ch32 — Data Encoding](Section4/Chapter_32_Data_Encoding_and_Evolution.md) ✅ | Protobuf, schema evolution — relevant for API versioning questions |
| [Ch36 — Kafka Internals](Section4/Chapter_36_Kafka_Internals.md) ✅ | Deeper Kafka: ISR, log compaction, consumer lag |
| [Ch42 — Deployment Strategies](Section4/Chapter_42_Deployment_Strategies.md) ✅ | Blue/green, canary — interviewers ask "how would you roll this out" |

**Skip for L5 (with note why):**

| Chapter | Why skip |
|---------|---------|
| Ch37 — Batch Processing | Only relevant for data engineering roles |
| Ch38 — Multi-Region Architecture | L6 territory — adds complexity L5 interviews don't test |
| Ch39-41 — Advanced Infra | L6 scope |
| Ch43 — Service Mesh | Rarely tested at L5; skip unless infra/platform role |
| Ch44 — ML System Design | Only for ML engineer roles |
| Ch46 — Data Warehouse | Only for data engineering / analytics roles |

### 5. Section 5 Case Studies — L5 Level (core practice problems)

Do each as a 45-minute mock before reading the chapter.

| Chapter | Core concept tested |
|---------|-------------------|
| [Ch49 — URL Shortener](Section5/Chapter_49_URL_Shortener.md) ✅ | Warmup — hashing, redirect, analytics |
| [Ch50 — Rate Limiter](Section5/Chapter_50_Single_Region_Rate_Limiter.md) ✅ | Token bucket, sliding window, Redis |
| [Ch51 — Distributed Cache](Section5/Chapter_51_Distributed_Cache_Single_Cluster.md) ✅ | Eviction, cache stampede, TTL |
| [Ch53 — Notification System](Section5/Chapter_53_Notification_System.md) ✅ | Push/pull, fan-out, delivery guarantees |
| [Ch57 — Background Job Queue](Section5/Chapter_57_Background_Job_Queue.md) ✅ | Async processing, retry, dead-letter queue |
| [Ch58 — Payment Flow](Section5/Chapter_58_Payment_Flow.md) ✅ | Idempotency, double-charge prevention |
| [Ch60 — Real-Time Chat](Section5/Chapter_60_Real_Time_Chat.md) ✅ | WebSocket, presence, message ordering |
| [Ch55 — Search System](Section5/Chapter_55_Search_System.md) 🟡 | Inverted index, ranking basics |
| [Ch56 — Metrics Collection](Section5/Chapter_56_Metrics_Collection_System.md) 🟡 | Time-series, aggregation, push vs pull |
| [Ch52 — Object Storage](Section5/Chapter_52_Object_and_File_Storage_System.md) ✅ | S3-like storage, multipart upload |

### 6. Section 5 New Additions — L5 Level (stubs, expand later)

| Chapter | Core concept tested |
|---------|-------------------|
| [Ch61b — Web Crawler](Section5/Chapter_61b_Web_Crawler.md) 📄 | URL frontier, Bloom filter dedup, politeness |
| [Ch61c — Proximity Service](Section5/Chapter_61c_Proximity_Service.md) 📄 | GeoHash, QuadTree, radius search |
| [Ch61d — Hotel Reservation](Section5/Chapter_61d_Hotel_Reservation_System.md) 📄 | Optimistic locking, seat hold, idempotency |
| [Ch61e — Key-Value Store](Section5/Chapter_61e_Key_Value_Store.md) 📄 | LSM tree, WAL, consistent hashing, quorum |
| [Ch61f — Leaderboard](Section5/Chapter_61f_Leaderboard_System.md) 📄 | Redis ZSET, top-K, time-windowed ranking |
| [Ch61g — File Sync (Dropbox)](Section5/Chapter_61g_File_Sync_Service.md) 📄 | Chunking, delta sync, conflict resolution |
| [Ch61h — Ride Sharing](Section5/Chapter_61h_Ride_Sharing.md) 📄 | Redis GEOADD, driver matching, state machine |
| [Ch61i — Live Streaming](Section5/Chapter_61i_Live_Streaming.md) 📄 | RTMP ingest, real-time transcode, CDN push |
| [Ch61j — Ticketing System](Section5/Chapter_61j_Ticketing_System.md) 📄 | Flash sale, atomic seat hold, virtual queue |
| [Ch61k — Stock / Trading Feed](Section5/Chapter_61k_Stock_Trading_Feed.md) 📄 | Order book, market data fan-out, low latency |

### 7. Google's Own Systems (unique to Google loops)

| Chapter | What to know at L5 |
|---------|-------------------|
| [Ch45 — Google Systems Overview](Section4/Chapter_45_Googles_Foundational_Systems.md) ✅ | Read first — how GFS/Bigtable/Spanner/Borg fit together |
| [Ch80 — GFS](Section6/Chapter_80_GFS.md) ✅ | Chunk servers, master, append-only, fault tolerance |
| [Ch81 — Bigtable](Section6/Chapter_81_Bigtable.md) ✅ | Wide-column, SSTable, memtable, row key design |
| [Ch82 — MapReduce](Section6/Chapter_82_MapReduce.md) ✅ | Map/reduce phases, compare to Spark |
| [Ch83 — Chubby](Section6/Chapter_83_Chubby.md) ✅ | Distributed locking, how it differs from ZooKeeper |
| [Ch84 — Spanner](Section6/Chapter_84_Spanner.md) 🟡 | TrueTime, global SQL — most cited at Google |
| [Ch47 — Kubernetes](Section4/Chapter_47_Kubernetes_Internals.md) ✅ | Control plane, scheduler — for infra/platform roles |

### 8. Advanced — L6 Territory (skip if time is short)

| Chapter | Skip unless... |
|---------|---------------|
| [Ch24 — Leader Election & Locks](Section3/Chapter_24_Leader_Election_Coordination.md) ✅ | You're asked about ZooKeeper/Chubby internals |
| [Ch48 — Consensus Deep Dive](Section4/Chapter_48_Consensus_Deep_Dive.md) 🟡 | You're asked to explain Raft or Paxos in detail |
| [Ch29 — Advanced Distributed Systems](Section3/Chapter_29_Advanced_Distributed_Systems.md) ✅ | You're applying for a distributed systems specialist role |

### 9. Behavioral + Offer (do in final 2 weeks)

| Chapter | What it covers |
|---------|---------------|
| [Ch108 — Behavioral Interview](Section8/Chapter_108_Behavioral_Leadership_Interview.md) ✅ | STAR stories, Googleyness, L5+L6 scope, all FAANG companies |
| [Ch109 — Offer Negotiation](Section8/Chapter_109_Offer_Negotiation.md) 📄 | RSU, joining bonus, notice period buyout |

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

*Google L5 | India (Bangalore / Hyderabad) | Deep reader — 2× pace | Updated 2026-06-21*
