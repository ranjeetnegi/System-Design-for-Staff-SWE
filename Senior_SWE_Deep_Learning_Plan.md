# Deep Learning Study Plan — Senior SWE (L5)
## 3.5× Slower Than One Read | 1h/Day Cadence

Last updated: March 2026

---

## Senior vs Staff — Key Differences in This Plan

| Dimension | Senior SWE (L5) — This Plan | Staff (L6) — Other Plan |
|-----------|----------------------------|------------------------|
| **Target** | Clear design in 45 min: requirements, capacity, components, trade-offs | Multi-region, cross-team, org impact, migration strategy |
| **Chapters** | ~37 core + ~13 optional = 50 chapters | All 72 chapters |
| **Section 6** | Skip entirely | Full (18 Staff problems) |
| **Section 1** | Only Ch 10 + Ch 12 (skim) | All 6 chapters (deep) |
| **Section 3** | Ch 20, 21, 23, 24, 25 core; Ch 22, 26, 27 optional | All 8 chapters (deep) |
| **Section 4** | Ch 28, 31, 33 core; Ch 40 recommended | All 14 chapters (deep) |
| **Section 5** | 6 must-practice first, then 7 second tier | All 13 as full mocks |
| **Total (core)** | **~288 days @ 1h/day (~10 months)** | ~614 days @ 1h/day (~20 months) |

---

## How This Plan Works

**Deep learning = 3.5× one-read time**, split into 5 activities:

| Activity | Multiplier | What you produce |
|----------|-----------|-----------------|
| **Read** | 1.0× | Section-by-section with pause-and-recall |
| **Exercises** | 0.75× | Written answers cold, then check |
| **Own Diagrams** | 0.75× | Architecture drawn from memory |
| **Mnemonics** | 0.5× | One-liners and acronyms for key choices |
| **Own Mind Map** | 0.5× | Your map of how topics connect |
| **Total** | **3.5×** | |

**Section 1 (skim)** uses **2×** not 3.5× — read + light exercises only. No deep diagrams needed.
**Section 3 optional** and **Section 4 supplements** use **2×** — lighter treatment.

**Reading speed baseline:** ~500 lines/hour for careful technical reading.

**Daily 60-minute structure:**
```
Min  0–05   Recall yesterday — 3 things cold, no files open
Min  5–50   Core work for the day (see schedule column)
Min 50–60   3-bullet memory dump + write tomorrow's exact start point
```

---

## The L5 Interview Target

Before each session, internalize this. Every chapter you study feeds exactly this goal:

```
45-minute interview breakdown:
  Min  0–5   Clarify the problem — scope, users, scale
  Min  5–10  Capacity estimate — QPS, storage, bandwidth
  Min 10–25  High-level design — components + data flow
  Min 25–35  Deep dive — 1–2 components in detail
  Min 35–40  Trade-offs — what you chose and why
  Min 40–45  Failure handling + scale-up discussion
```

You pass L5 by covering all 6 phases with clear reasoning. You fail by running out of time, missing failure cases, or giving "it depends" without a recommendation.

---

## Section 0 — Fundamentals (Ch 1–6) — ALL REQUIRED

*Do these first if fundamentals are rusty. They underpin the framework and every design problem.*

| # | Chapter | Lines | 1× Read | Deep (3.5×) | Days@1h | Day Schedule |
|---|---------|-------|---------|-------------|---------|-------------|
| 1 | Systems, Servers, Clients | 1,384 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |
| 2 | APIs, Frontend, Backend, DB | 1,446 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |
| 3 | OS Fundamentals | 928 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |
| 4 | Networking Foundations | 964 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |
| 5 | Numbers and Estimation | 1,160 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |
| 6 | Core Building Blocks | 1,363 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |

**Section 0 Total: ~21h deep → 24 days**

---

### S0 Session Plans

**Ch 5 (Numbers & Estimation) — focus here, it's used in every interview:**
- Day 1 (R): Read all number tables. Memorize: 1M users → how many QPS? 1TB → how many rows?
- Day 2 (E): Do all estimation exercises cold. Time yourself — you need these under 5 minutes in interviews
- Day 3 (D): Draw your own back-of-envelope template on one page
- Day 4 (M+MM): Build your "number cheat sheet" — QPS/storage/bandwidth formulas you'll use every interview

**Ch 6 (Core Building Blocks) — the most referenced chapter in all design problems:**
- Day 1 (R): Read hash, cache, state, idempotency
- Day 2 (E): All exercises — celebrity post stampede, idempotency across 3 services
- Day 3 (D): Draw cache patterns (cache-aside, write-through, write-behind, read-through) from memory
- Day 4 (M+MM): Mnemonics for each building block + mind map linking to design problems

> **S0 Key Mnemonics:**
> - Back-of-envelope: **"QSB"** — QPS first, Storage second, Bandwidth last
> - Cache patterns: **"CWRRA"** — Cache-aside, Write-through, Read-through, Write-behind (Rear), Write-Around
> - Building blocks: **"HCSIQAS"** — Hash, Cache, State, Idempotency, Queue, Async, Sync

---

## Section 1 — Mindset (Ch 10 + 12 only) — SKIM (2× not 3.5×)

*Just two chapters. Skim for interview presence — how to handle ambiguity and lead the conversation.*

| # | Chapter | Lines | 1× Read | Skim-Deep (2×) | Days@1h | Day Schedule |
|---|---------|-------|---------|----------------|---------|-------------|
| 10 | Staff Mindset — Designing Under Ambiguity | 2,634 | 2.0h | **4h** | **4** | R, R, E, M |
| 12 | Communication and Interview Leadership | 2,430 | 1.5h | **3h** | **3** | R, R, E+M |

**Section 1 Total: ~7h → 7 days**

> **Ch 12 is the single most important chapter for passing L5.** The reason most candidates fail is not missing technical knowledge — it's poor communication structure. Spend your Ch 12 exercise day doing the transition phrases out loud until they feel natural.

> **L5 mindset mnemonic — "CARS":**
> - **C**larify before designing (spend 5 min here, save 20 min of wrong direction)
> - **A**ssume and state (state your assumptions explicitly)
> - **R**ecommend (say "I would choose X because Y" — don't leave trade-offs open)
> - **S**cope aggressively (finish on time — a complete simple design beats an incomplete complex one)

---

## Section 2 — System Design Framework (Ch 13–19) — ALL REQUIRED

*The 5-phase framework is your interview scaffold. By end of S2 it must feel automatic.*

| # | Chapter | Lines | 1× Read | Deep (3.5×) | Days@1h | Day Schedule |
|---|---------|-------|---------|-------------|---------|-------------|
| 13 | System Design Framework | 2,426 | 1.5h | **5h** | **5** | R, R, E, D, M+MM |
| 14 | Phase 1 — Users & Use Cases | 2,041 | 1.5h | **5h** | **5** | R, R, E, D, M+MM |
| 15 | Phase 2 — Functional Requirements | 2,380 | 1.5h | **5h** | **5** | R, R, E, D, M+MM |
| 16 | Phase 3 — Scale & Capacity | 2,206 | 1.5h | **5h** | **5** | R, R, E, D, M+MM |
| 17 | Cost, Efficiency, Sustainable Design | 5,110 | 4.0h | **14h** | **14** | R×4, E×3, D×2, M×2, MM×2, Rev×1 |
| 18 | Phase 4 & 5 — NFRs & Constraints | 2,335 | 1.5h | **5h** | **5** | R, R, E, D, M+MM |
| 19 | End-to-End 5-Phase Walkthrough | 1,842 | 1.5h | **5h** | **5** | Design yourself first, R, E, D+M+MM |

**Section 2 Total: ~44h → 44 days**

---

### Ch 17 Deep Learning Schedule (14 sessions — the hardest S2 chapter)

| Day | Type | Focus |
|-----|------|-------|
| 1 | **R** | Cost modeling concepts, what makes a system expensive |
| 2 | **R** | Cost per component (compute, storage, network egress) |
| 3 | **R** | Cost-vs-reliability trade-offs, capacity planning |
| 4 | **R** | L5 vs L6 table, exercises section overview |
| 5 | **E** | Cost estimation exercises — compute cost for a notification system |
| 6 | **E** | Cost exercises — storage cost for a URL shortener at 1B URLs |
| 7 | **E** | "What If" — traffic doubles, what's the new cost? |
| 8 | **D** | Draw: cost breakdown diagram for a 3-tier web app |
| 9 | **D** | Draw: cost vs reliability curve — where does your system sit? |
| 10 | **M** | Mnemonics: cost driver ranking (compute > storage > network > DB) |
| 11 | **M** | Mnemonics: cost levers you can pull (cache, compress, batch, CDN) |
| 12 | **MM** | Mind map: Ch 17 → Ch 16 (capacity) → Ch 5 (numbers) → S5 problem costs |
| 13 | **MM** | Add: cost-to-reliability mapping for each S5 problem |
| 14 | **Rev** | Review all diagrams + mnemonics from last 13 sessions |

### Ch 19 technique (do this differently):
- **Before reading**: take a blank page and design a URL shortener using only the 5-phase framework (20 min)
- **Then read Ch 19** — compare your structure to the walkthrough
- Note exactly which phases you skipped or did poorly

> **5-Phase mnemonic: "USE-CAD"**
> - **U**sers & use cases → **S**cale & capacity → **E**xact requirements
> - **C**omponents & architecture → **A**ssumptions & NFRs → **D**eep dive + trade-offs

---

## Section 3 — Distributed Systems — CORE (Ch 20, 21, 23, 24, 25)

*Required. These give you the vocabulary to justify every design choice.*

| # | Chapter | Lines | 1× Read | Deep (3.5×) | Days@1h | Day Schedule |
|---|---------|-------|---------|-------------|---------|-------------|
| 20 | Consistency Models | 2,589 | 2.0h | **7h** | **7** | R, R, R, E, D, M, MM |
| 21 | Replication and Sharding | 5,698 | 4.0h | **14h** | **14** | R×4, E×3, D×2, M×2, MM×2, Rev×1 |
| 23 | Backpressure, Retries, Idempotency | 4,790 | 3.5h | **12h** | **12** | R×3, E×2, D×2, M×2, MM×2, Rev×1 |
| 24 | Queues, Logs, and Streams | 3,872 | 2.5h | **9h** | **9** | R×2, E×2, D×2, M, MM, Rev |
| 25 | Failure Models and Partial Failures | 4,622 | 3.5h | **12h** | **12** | R×3, E×2, D×2, M×2, MM×2, Rev×1 |

**Section 3 Core Total: ~54h → 54 days**

---

### S3 Optional Chapters (do if time allows — lighter 2× treatment)

| # | Chapter | Lines | Skim-Deep (2×) | Days@1h | When to do |
|---|---------|-------|----------------|---------|-----------|
| 22 | Leader Election & Distributed Locks | 4,909 | **9h** | 9 | After Ch 21 |
| 26 | CAP Theorem — Applied Case Studies | 3,333 | **6h** | 6 | After Ch 20 |
| 27 | Advanced Distributed Systems | 1,362 | **2.5h** | 3 | Stretch goal |

**S3 Optional Total: ~17.5h → 18 days**

---

### Ch 21 Deep Learning Schedule (14 sessions — the critical S3 chapter)

| Day | Type | Focus |
|-----|------|-------|
| 1 | **R** | Replication fundamentals — leader/follower, sync vs async |
| 2 | **R** | Replication lag, read replicas, failover |
| 3 | **R** | Sharding strategies — hash, range, directory |
| 4 | **R** | Consistent hashing, hot shards, resharding |
| 5 | **E** | Exercises: choose sharding key for a given system |
| 6 | **E** | Exercises: design replication strategy for a payment DB |
| 7 | **E** | "What If" — shard goes down, replication lag grows to 10 minutes |
| 8 | **D** | Draw: consistent hashing ring — adding/removing a node |
| 9 | **D** | Draw: replication topologies (single-leader, multi-leader, leaderless) |
| 10 | **M** | Mnemonic: sharding key selection rules |
| 11 | **M** | Mnemonic: when replication lag becomes a user-visible problem |
| 12 | **MM** | Mind map: Ch 21 → Ch 20 (consistency) → Ch 23 (retries after failover) |
| 13 | **MM** | Add S5 problems that need sharding decisions (URL shortener, cache, rate limiter) |
| 14 | **Rev** | Review all diagrams + mnemonics cold |

> **S3 Core Mnemonics:**
> - Consistency: **"ESC it"** — Eventually consistent for social/likes, Strong for money, Causal for chat
> - Idempotency: **"GSCER"** — Generate key → Store → Check → Execute → Return cached response
> - Retry: **"EBJ"** — Exponential Backoff with Jitter (never linear retry)
> - Failure: **"CSTO"** — Circuit breaker → Shed load → Throttle → Open (let it fail fast)

---

## Section 4 — Data Systems — CORE (Ch 28, 31, 33) + Recommended (Ch 40)

*Don't skip these — L5 interviews expect you to justify every storage and caching choice.*

### Core (full 3.5× treatment)

| # | Chapter | Lines | 1× Read | Deep (3.5×) | Days@1h |
|---|---------|-------|---------|-------------|---------|
| 28 | Databases — Choosing, Using, Evolving | 6,409 | 5.0h | **18h** | **18** |
| 31 | Caching at Scale — Redis, CDN, Edge | 7,056 | 5.0h | **18h** | **18** |
| 33 | Event-Driven — Kafka & Streams | 5,855 | 4.0h | **14h** | **14** |

### Recommended (full 3.5×)

| # | Chapter | Lines | 1× Read | Deep (3.5×) | Days@1h |
|---|---------|-------|---------|-------------|---------|
| 40 | Deployment Strategies and Operations | 1,687 | 1.0h | **3.5h** | **4** |

**Section 4 Core + Recommended Total: ~53.5h → 54 days**

---

### S4 Supplements (2× lighter treatment — use when practicing related S5 problems)

| # | Chapter | Lines | Skim-Deep (2×) | Days@1h | When to use |
|---|---------|-------|----------------|---------|------------|
| 29 | DB Internals Deep Dive | 1,470 | **3h** | 3 | Deep DB questions (B-tree, WAL, MVCC) |
| 30 | Data Encoding & Schema Evolution | 1,213 | **2.5h** | 3 | API contracts, Protobuf vs JSON |
| 32 | Redis Internals | 1,439 | **3h** | 3 | Cache design, eviction, Redis Cluster |
| 34 | Kafka Internals | 1,365 | **2.5h** | 3 | Kafka partitions, consumer lag, ISR |
| 35 | Batch Processing & Data Pipelines | 1,113 | **2.5h** | 3 | Background jobs, ETL design |

**S4 Supplements Total: ~13.5h → 15 days** (do alongside related S5 problems)

---

### Ch 28 Deep Learning Schedule — 18 sessions

| Day | Type | Focus |
|-----|------|-------|
| 1 | **R** | Relational vs NoSQL: when to use which, ACID vs BASE |
| 2 | **R** | Read/write patterns, index types (B-tree vs hash vs full-text) |
| 3 | **R** | Sharding, replication, consistency in each DB type |
| 4 | **R** | Schema design patterns, normalization vs denormalization |
| 5 | **R** | Migration strategies, schema evolution, exercises overview |
| 6 | **E** | DB selection exercises — choose DB for 5 different systems |
| 7 | **E** | Schema design exercises — design the data model for a notification system |
| 8 | **E** | "What If" — traffic grows 10×, DB becomes bottleneck, what do you do? |
| 9 | **E** | Failure exercises — primary DB goes down, what's the failover sequence? |
| 10 | **D** | Draw: DB selection decision tree (SQL? NoSQL? which NoSQL?) |
| 11 | **D** | Draw: B-tree vs LSM write paths (why Cassandra is write-optimized) |
| 12 | **D** | Draw: read replica setup + lag diagram |
| 13 | **M** | Mnemonic: DB pick one-liners (one sentence per DB type) |
| 14 | **M** | Mnemonic: ACID properties — what each letter actually means in a real failure |
| 15 | **M** | Mnemonic: Index types — when B-tree vs hash vs composite |
| 16 | **MM** | Mind map: Ch 28 → Ch 20 (consistency) → Ch 21 (sharding) → S5 problems |
| 17 | **MM** | Add: failure modes per DB type |
| 18 | **Rev** | Review L5 vs L6 table + all diagrams + mnemonics |

### Ch 31 Deep Learning Schedule — 18 sessions

| Day | Type | Focus |
|-----|------|-------|
| 1 | **R** | Cache-aside vs write-through vs read-through vs write-behind |
| 2 | **R** | Cache invalidation strategies, TTL design |
| 3 | **R** | Redis architecture, eviction policies |
| 4 | **R** | CDN caching, edge nodes, cache-control headers |
| 5 | **R** | Hot-key problem, stampede prevention, exercises |
| 6 | **E** | Cache strategy exercises — pick cache pattern for 5 scenarios |
| 7 | **E** | Hot-key problem exercises — celebrity post with 10M followers |
| 8 | **E** | Cache stampede exercises — what breaks, how to fix |
| 9 | **E** | Multi-tier cache exercises — when to use CDN vs Redis vs in-process |
| 10 | **D** | Draw: multi-tier cache (browser → CDN → LB → in-process → Redis → DB) |
| 11 | **D** | Draw: cache stampede — what happens, then the fixed version |
| 12 | **D** | Draw: cache invalidation flows for cache-aside vs write-through |
| 13 | **M** | Mnemonic: cache patterns — CWRRA one-liner per pattern |
| 14 | **M** | Mnemonic: eviction policies — LRU vs LFU vs random, when each |
| 15 | **M** | Mnemonic: cache hit rate math — 95% hit rate = 20× DB load reduction |
| 16 | **MM** | Mind map: Ch 31 → Ch 6 (building blocks) → Ch 28 (DB) → S5 problems |
| 17 | **MM** | Add: failure modes — Redis down, CDN miss storm, cache corruption |
| 18 | **Rev** | Review L5 vs L6 table + all diagrams + mnemonics |

> **S4 Core Mnemonics:**
> - DB pick rule: **"ROAR"** — Read-heavy→cache; OLAP→column; ACID→SQL; Relationships→graph
> - Cache hit rate: **"95 is 20×"** — 95% cache hit rate = only 5% hits DB = 20× less DB load
> - Kafka vs SQS: **"Kafka = replay + fan-out + ordering. SQS = simple + managed + cost-efficient"**
> - Cache invalidity: **"TTL is the last resort"** — prefer explicit invalidation on write

---

## Section 5 — Senior Design Problems (Ch 42–54)

*This is where your score is set. Deep learning technique changes here — design first, then read.*

### Senior Problem Deep Learning Technique

```
Day 1 (Design):   Blank paper, 45 minutes, no notes. Produce a real design.
Day 2-3 (Read):   Read the full chapter. Mark every gap from your Day 1 design.
Day 4 (Exercises): All exercises cold. Do "What If" questions out loud.
Day 5 (D+M+MM):   Draw architecture from memory. Build mnemonics. Mind map.
```

**The Day 1 design is the most important session. Your gaps become your curriculum.**

---

### Must-Practice Problems (do these first, in order)

*High frequency at L5 interviews. Master all 6 before touching second tier.*

| # | Chapter | Lines | Deep (3.5×) | Days@1h | Priority reason |
|---|---------|-------|-------------|---------|----------------|
| 42 | URL Shortener | 4,983 | **12h** | **12** | Classic L5 warm-up — tests all 6 phases |
| 43 | Single-Region Rate Limiter | 3,234 | **7h** | **7** | Tests distributed state, consistency |
| 44 | Distributed Cache | 3,764 | **9h** | **9** | Tests Ch 31 knowledge in practice |
| 45 | Object/File Storage System | 3,861 | **9h** | **9** | Tests chunking, metadata, CDN |
| 46 | Notification System | 3,899 | **9h** | **9** | Tests fan-out, queues, multi-channel |
| 53 | Real-Time Chat | 3,707 | **9h** | **9** | Tests WebSocket, message ordering, presence |

**Must-Practice Total: ~55h → 55 days**

---

### Must-Practice Chapter Schedules

**Ch 42 (URL Shortener) — 12 sessions:**

| Day | Type | Focus |
|-----|------|-------|
| 1 | **Design** | 45 min, blank page. Produce: API, data model, components, scale |
| 2 | **R** | Read: requirements, capacity estimate, data model |
| 3 | **R** | Read: component design, DB choice, cache layer |
| 4 | **R** | Read: scalability, failure modes, exercises section |
| 5 | **E** | All exercises cold — especially capacity math |
| 6 | **E** | "What If" questions — traffic 10×, short URLs must expire |
| 7 | **E** | Failure injection — DB down, cache stampede, hash collision |
| 8 | **D** | Draw: full architecture from memory (API → short→long mapping → cache → DB) |
| 9 | **D** | Draw: hash collision resolution + bloom filter for existence check |
| 10 | **M** | Mnemonic: URL shortener key design choices (base62, length, collision) |
| 11 | **MM** | Mind map: Ch 42 → Ch 5 (estimation), Ch 6 (hash+cache), Ch 28 (DB choice) |
| 12 | **Rev** | Compare Day 1 design vs Day 8 diagram. Score yourself on L5 signals. |

**Ch 43 (Rate Limiter) — 7 sessions:**

| Day | Type | Focus |
|-----|------|-------|
| 1 | **Design** | 45 min blank page: token bucket vs leaky bucket vs sliding window |
| 2 | **R** | Read full chapter |
| 3 | **R** | Read exercises + failure modes |
| 4 | **E** | All exercises + "What If" questions cold |
| 5 | **D** | Draw: token bucket algorithm + Redis storage schema |
| 6 | **M** | Mnemonic: algorithm comparison (token bucket = bursty ok, leaky bucket = smooth) |
| 7 | **MM** | Mind map + compare Day 1 design vs Day 5 diagram |

**Ch 53 (Real-Time Chat) — 9 sessions:**

| Day | Type | Focus |
|-----|------|-------|
| 1 | **Design** | 45 min: WebSocket vs polling, message storage, online presence |
| 2 | **R** | Read: connection management, message delivery |
| 3 | **R** | Read: message ordering, group chat, failure modes |
| 4 | **E** | All exercises cold |
| 5 | **E** | "What If" questions: 10M concurrent users, messages lost, reconnect |
| 6 | **D** | Draw: message flow (sender → server → recipient → ACK) |
| 7 | **D** | Draw: fan-out for group chat with online/offline handling |
| 8 | **M+MM** | Mnemonics + mind map |
| 9 | **Rev** | Score yourself on L5 signals vs Day 1 design |

---

### Second-Tier Problems (do after all 6 must-practice)

| # | Chapter | Lines | Deep (3.5×) | Days@1h | What it tests |
|---|---------|-------|-------------|---------|--------------|
| 47 | Authentication System | 3,442 | **8h** | **8** | JWT, sessions, OAuth, token expiry |
| 48 | Search System | 2,802 | **7h** | **7** | Inverted index, query parsing, ranking |
| 49 | Metrics Collection System | 2,812 | **7h** | **7** | Time-series DB, aggregation, dashboards |
| 50 | Background Job Queue | 3,092 | **7h** | **7** | Job scheduling, retry, DLQ, idempotency |
| 51 | Payment Flow | 3,148 | **7h** | **7** | Exactly-once, saga, reconciliation |
| 52 | API Gateway | 3,649 | **8h** | **8** | Rate limiting, auth, routing, load balancing |
| 54 | Configuration Management | 3,784 | **8h** | **8** | Feature flags, rollout, secret management |

**Second-Tier Total: ~52h → 52 days**

> **For second-tier problems:** Use the same technique but compress to 4 days:
> - Day 1: Design cold (30 min) + read first half
> - Day 2: Read second half + exercises
> - Day 3: Diagrams + mnemonics
> - Day 4: Mind map + gap review

---

## Grand Total — Senior SWE Path

| Section | Chapters | Deep Hours | Days@1h |
|---------|---------|-----------|---------|
| S0 Fundamentals | 6 (all) | 21h | **24** |
| S1 Mindset | 2 (Ch 10, 12) | 7h | **7** |
| S2 Framework | 7 (all) | 44h | **44** |
| S3 Core | 5 (Ch 20, 21, 23, 24, 25) | 54h | **54** |
| S4 Core + Recommended | 4 (Ch 28, 31, 33, 40) | 53.5h | **54** |
| S5 Must-Practice | 6 (Ch 42–46, 53) | 55h | **55** |
| S5 Second Tier | 7 (Ch 47–52, 54) | 52h | **52** |
| **Core Total** | **37 chapters** | **~287h** | **~290 days** |

**At 1h/day: ~290 days ≈ 9–10 months**

| With Optional | Additional chapters | Days added |
|--------------|---------------------|-----------|
| + S3 Optional (Ch 22, 26, 27) | 3 chapters | +18 days |
| + S4 Supplements (Ch 29–35) | 5 chapters | +15 days |
| **Full Optional Total** | **45 chapters** | **~323 days ≈ ~11 months** |

---

## Monthly Milestones at 1h/Day

| Month | Days | Target | Checkpoint Question |
|-------|------|--------|-------------------|
| 1 | 1–30 | S0 complete | Estimate QPS, storage, bandwidth for a system with 10M users in under 3 minutes |
| 1 | 28–35 | S1 complete | State 3 clarifying questions for "Design Twitter" before saying anything else |
| 2–3 | 36–80 | S2 complete | Apply 5-phase framework to any prompt within 2 minutes, just the structure |
| 4–5 | 81–134 | S3 core done | Justify consistency choice for each S5 problem in one sentence |
| 6–7 | 135–188 | S4 core done | Choose DB + cache + queue for any system without hesitation |
| 8 | 189–243 | S5 must-practice done | Design any of Ch 42, 44, 46, 53 in 45 minutes with clear trade-offs |
| 9–10 | 244–290 | S5 second tier done | Mock interview score: covers all 6 phases, has 2 trade-offs, handles 1 follow-up |

---

## The 5 Diagrams Every L5 Engineer Must Draw From Memory

Practice drawing each one weekly until the interview.

### 1. Request Flow (L5 Standard — Single Region)
```
Client → DNS → Load Balancer → API Server → Cache → DB
                                     │
                              (cache miss) → DB → populate cache

Write path: API Server → DB (primary) → async replication → read replicas
```

### 2. Cache Decision Tree
```
Is data read-heavy (>5× more reads than writes)?
  YES → Cache it
        Is consistency critical (payments, inventory)?
          YES → Write-through (cache + DB together)
          NO  → Cache-aside (lazy load on miss)
  NO  → Skip cache, or write-behind for write-heavy (view counts)
```

### 3. Notification Fan-out
```
Event (user A posts) → Kafka topic
         │
         ▼
  Fan-out service
         │
  ┌──────┼──────┐
  ▼      ▼      ▼
Push   Email   SMS
(APNS) (SES)  (Twilio)
```

### 4. Back-of-Envelope Template
```
Users: ___ MAU → ___ DAU (10–20% of MAU)
       DAU × actions/day = ___ requests/day
       requests/day ÷ 86,400 = ___ QPS (avg)
       Peak = avg × 3–5×

Storage: ___ requests/day × ___ bytes/request = ___ bytes/day
         × 365 days × retention years = ___ total storage
```

### 5. Failure Handling Ladder
```
Dependency fails:
  Step 1: Circuit breaker opens (stop hammering failing dep)
  Step 2: Retry with exponential backoff + jitter (for recoverable errors)
  Step 3: DLQ (for async messages that can't be processed now)
  Step 4: Graceful degradation (serve partial response / cached response)
  Step 5: Alert + runbook (for human intervention)
```

---

## Mnemonics Master List — Senior SWE

| Chapter | Topic | Mnemonic |
|---------|-------|----------|
| Ch 5 | Estimation order | **"QSB"** — QPS first, Storage second, Bandwidth last |
| Ch 6 | Cache patterns | **"CWRRA"** — Cache-aside, Write-through, Read-through, Write-behind (Rear), Write-Around |
| Ch 12 | Interview presence | **"CARS"** — Clarify, Assume+state, Recommend, Scope tightly |
| Ch 13 | 5-phase framework | **"USE-CAD"** — Users, Scale, Exact requirements, Components, Assumptions+NFRs, Deep dive |
| Ch 20 | Consistency pick | **"ESC it"** — Eventual for social, Strong for money, Causal for chat |
| Ch 21 | Shard key rule | **"Even + Queryable"** — good shard key distributes evenly AND supports your most common query |
| Ch 23 | Retry rule | **"EBJ"** — Exponential Backoff with Jitter (never retry linearly) |
| Ch 25 | Failure response | **"CSTO"** — Circuit breaker → Shed load → Throttle → Open (fail fast) |
| Ch 28 | DB selection | **"ROAR"** — Read-heavy→cache, OLAP→column, ACID→SQL, Relationships→graph |
| Ch 31 | Cache hit rate | **"95 is 20×"** — 95% hit rate = 20× less DB load |
| Ch 33 | Kafka vs SQS | **"Kafka = replay, SQS = simple"** — Kafka when you need replay, fan-out, or ordering per partition |
| Ch 42 | URL shortener | **"Hash → Store → Redirect"** — generate, persist, serve |
| Ch 43 | Rate limiter pick | **"Token = bursty OK, Leaky = smooth required"** |
| Ch 46 | Notification | **"Push first, poll as backup"** — push for freshness, poll for reliability |
| Ch 53 | Real-time chat | **"WS for active, poll for inactive"** — WebSocket for online users, poll or push notification for offline |
| All | Interview win condition | **"CRDTF"** — Complete design (all 6 phases), Recommend (not hedge), Draw it, Trade-offs named, Failures handled |

---

## Daily Log Template

Fill in before you start and when you finish. Never skip.

```
DATE: ___________
CHAPTER: ___________________ (Ch ____)
PASS TYPE: [ Read ] [ Exercises ] [ Diagrams ] [ Mnemonics ] [ Mind Map ] [ Design-Cold ]
SESSION: ___ of ___

RECALL (before opening anything):
1. _______________________________________________
2. _______________________________________________
3. _______________________________________________

TODAY'S WORK:
Start point: ___________________________________
End point:   ___________________________________

MEMORY DUMP (after closing everything):
1. _______________________________________________
2. _______________________________________________
3. _______________________________________________

TOMORROW: Ch ___, Session ___ of ___, Starting at: _______________
WEAK SPOT flagged: _______________________________

Progress tracker:
[S0 ░░░░░░] [S1 ░░] [S2 ░░░░░░░] [S3-core ░░░░░] [S4-core ░░░░] [S5-must ░░░░░░] [S5-tier2 ░░░░░░░]
```

---

## Chapter Priority Order — If You Run Out of Time

If you have less than 10 months, cut in this order (last to cut = most critical):

| Priority | Chapters | Why critical |
|----------|---------|-------------|
| **Never cut** | Ch 5, 6, 13, 19, 20, 21, 23, 28, 31 | Framework + estimation + DB + cache + consistency |
| **Never cut** | Ch 42, 43, 44, 45, 46, 53 | Must-practice S5 problems |
| **Cut last** | Ch 24, 25, 33, 40 | Queues, failure, Kafka, deployment |
| **Cut if needed** | Ch 1, 2, 3, 4 | Fundamentals (if you know them already) |
| **Cut if needed** | Ch 10, 12 | Mindset (read quickly if time-pressed) |
| **Cut first** | Ch 17, 47–52, 54 | Second-tier problems and deep cost chapter |
| **Cut entirely** | Ch 22, 26, 27, 29–35 | Optional/supplement chapters |

---

*This plan is for 1h/day, 7 days/week. The 5-minute recall and 10-minute memory dump at the start and end of each session are non-negotiable — they are what make 1 hour as effective as 2.*
