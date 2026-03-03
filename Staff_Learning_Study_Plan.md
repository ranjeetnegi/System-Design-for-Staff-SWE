# Deep Learning Study Plan — All 72 Chapters
## 3.5× Slower Than One Read | 1h/Day Cadence

Last updated: March 2026

---

## How This Plan Works

**Deep learning = 3.5× one-read time**, split into 5 activities per chapter:

| Activity | Multiplier of read time | What you produce |
|----------|------------------------|-----------------|
| **Read** | 1.0× | Annotated reading with pauses |
| **Exercises** | 0.75× | Written answers to all exercises cold |
| **Own Diagrams** | 0.75× | Hand-draw the key architecture/flow from memory |
| **Mnemonics** | 0.5× | Acronyms or memory hooks for the main concepts |
| **Own Mind Map** | 0.5× | Your map of how topics in the chapter connect |
| **Total** | **3.5×** | |

**Reading speed baseline:** ~500 lines/hour for careful first read of technical material.

**At 1h/day:** Each "day" below = one 60-minute session.

**Session structure (every day, no exceptions):**
```
Min  0–05   Recall yesterday — say 3 things cold, no opening files
Min  5–50   Core work (see activity column for the day)
Min 50–60   3-bullet memory dump + write tomorrow's exact start point
```

---

## Deep Learning Activities — What to Actually Do

### Read (Session type: R)
- Read the chapter section by section
- After each major section: pause, close the chapter, say what you just learned
- Mark 2–3 concepts you want to diagram later
- Do NOT do exercises yet

### Exercises (Session type: E)
- Open only the exercise/brainstorming section — not the chapter
- Answer every exercise in writing before checking
- For "What If X Changes?" — answer out loud, time yourself (90 sec)
- Only after finishing: check against the chapter

### Own Diagrams (Session type: D)
- Close the chapter entirely
- On paper or tablet: draw the main architecture from memory
- Include: components, data flows, failure paths, trade-offs
- Compare with the chapter's diagrams — mark what you missed

### Mnemonics (Session type: M)
- Identify the 5–7 most important concepts from the chapter
- Create an acronym, rhyme, story, or visual hook for each
- Write them in your own words in a single-page cheat sheet
- Example: CAP theorem → "Can't Always Predict" (Consistency, Availability, Partition)

### Own Mind Map (Session type: MM)
- On a blank page: chapter title in center
- Branch out: core concepts → sub-concepts → connections to OTHER chapters
- The cross-chapter links are the most valuable part
- Add this to a running master mind map of the whole course

---

## Section 0 — Fundamentals (Ch 1–6)

*These chapters are foundations you likely know. Move faster on familiar concepts.*

| # | Chapter | Lines | 1× Read | Deep (3.5×) | Days@1h | Schedule |
|---|---------|-------|---------|-------------|---------|---------|
| 1 | Systems, Servers, Clients | 1,384 | 1.0h | **3.5h** | **4** | R, R, E+D, M+MM |
| 2 | APIs, Frontend, Backend, DB | 1,446 | 1.0h | **3.5h** | **4** | R, R, E+D, M+MM |
| 3 | OS Fundamentals | 928 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |
| 4 | Networking Foundations | 964 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |
| 5 | Numbers and Estimation | 1,160 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |
| 6 | Core Building Blocks | 1,363 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |

**Section 0 Total: ~6h read → 21h deep → 24 days at 1h/day**

> **Mnemonic for S0:** "SAONBE" — Systems, APIs, OS, Networking, Back-of-envelope, Everything-else (Building Blocks)

---

## Section 1 — Staff Engineer Mindset (Ch 7–12)

*These chapters define your target. Read slowly — every paragraph changes how you approach problems.*

| # | Chapter | Lines | 1× Read | Deep (3.5×) | Days@1h | Schedule |
|---|---------|-------|---------|-------------|---------|---------|
| 7 | How Google Evaluates Staff Engineers | 2,365 | 1.5h | **5h** | **5** | R, R, E, D, M+MM |
| 8 | Scope, Impact, and Ownership | 2,151 | 1.5h | **5h** | **5** | R, R, E, D, M+MM |
| 9 | Designing Systems Across Teams | 2,720 | 2.0h | **7h** | **7** | R, R, R, E, D, M, MM |
| 10 | Staff Mindset — Designing Under Ambiguity | 2,634 | 2.0h | **7h** | **7** | R, R, R, E, D, M, MM |
| 11 | Trade-offs, Constraints, Decision-Making | 2,429 | 1.5h | **5h** | **5** | R, R, E, D, M+MM |
| 12 | Communication and Interview Leadership | 2,430 | 1.5h | **5h** | **5** | R, R, E, D, M+MM |

**Section 1 Total: ~11h read → 34h deep → 34 days at 1h/day**

> **Key diagram to draw (Ch 7):** The 10 L6 evaluation signals as a wheel — draw it from memory every week until the interview.

> **Mnemonic for L6 signals (Ch 7):** **"FAST CORD"**
> - **F**ailure thinking  **A**mbiguity navigation  **S**cope ownership  **T**rade-offs explicit
> - **C**ost awareness  **O**rg impact  **R**eal-world engineering  **D**epth + breadth balance

---

## Section 2 — System Design Framework (Ch 13–19)

*The 5-phase framework is your interview scaffold. By the end of S2 you should apply it automatically.*

| # | Chapter | Lines | 1× Read | Deep (3.5×) | Days@1h | Schedule |
|---|---------|-------|---------|-------------|---------|---------|
| 13 | System Design Framework | 2,426 | 1.5h | **5h** | **5** | R, R, E, D, M+MM |
| 14 | Phase 1 — Users & Use Cases | 2,041 | 1.5h | **5h** | **5** | R, R, E, D, M+MM |
| 15 | Phase 2 — Functional Requirements | 2,380 | 1.5h | **5h** | **5** | R, R, E, D, M+MM |
| 16 | Phase 3 — Scale & Capacity Planning | 2,206 | 1.5h | **5h** | **5** | R, R, E, D, M+MM |
| 17 | Cost, Efficiency, Sustainable Design | 5,110 | 4.0h | **14h** | **14** | R,R,R,R, E,E,E, D,D, M, MM, MM, Review, Review |
| 18 | Phase 4 & 5 — NFRs & Constraints | 2,335 | 1.5h | **5h** | **5** | R, R, E, D, M+MM |
| 19 | End-to-End 5-Phase Walkthrough | 1,842 | 1.5h | **5h** | **5** | R, E (design it yourself), D, M+MM |

**Section 2 Total: ~13h read → 44h deep → 44 days at 1h/day**

> **Ch 17 note:** This is the biggest chapter in S2 (5,110 lines). Spread it across 14 days. Days 1–4: read. Days 5–7: do all cost exercises. Days 8–9: diagram cost models. Day 10: mnemonics. Days 11–12: mind map. Days 13–14: apply to a design problem.

> **5-Phase mnemonic:** **"USE CAD"** — **U**sers, **S**cale, **E**xact requirements, **C**omponents+Architecture, **A**ssumptions+NFRs, **D**epth (trade-offs)

---

## Section 3 — Distributed Systems (Ch 20–27)

*Hardest section intellectually. These are the vocabulary chapters — every S5/S6 problem draws from here.*

| # | Chapter | Lines | 1× Read | Deep (3.5×) | Days@1h | Schedule |
|---|---------|-------|---------|-------------|---------|---------|
| 20 | Consistency Models | 2,589 | 2.0h | **7h** | **7** | R, R, R, E, D, M, MM |
| 21 | Replication and Sharding | 5,698 | 4.0h | **14h** | **14** | R×4, E×3, D×2, M×2, MM×2, Review×1 |
| 22 | Leader Election & Distributed Locks | 4,909 | 3.5h | **12h** | **12** | R×3, E×2, D×2, M×2, MM×2, Review×1 |
| 23 | Backpressure, Retries, Idempotency | 4,790 | 3.5h | **12h** | **12** | R×3, E×2, D×2, M×2, MM×2, Review×1 |
| 24 | Queues, Logs, and Streams | 3,872 | 2.5h | **9h** | **9** | R×2, R+start E, E, D, M, MM, MM |
| 25 | Failure Models and Partial Failures | 4,622 | 3.5h | **12h** | **12** | R×3, E×2, D×2, M×2, MM×2, Review×1 |
| 26 | CAP Theorem — Applied Case Studies | 3,333 | 2.5h | **9h** | **9** | R×2, E×2, D, M, MM, MM |
| 27 | Advanced Distributed Systems | 1,362 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |

**Section 3 Total: ~23h read → 78.5h deep → 79 days at 1h/day**

> **Ch 21 (5,698 lines) is the longest in S3.** Give it 14 sessions:
> - Days 1–4: Read (split into 4 roughly equal segments: leader/follower basics → multi-leader → leaderless → sharding strategies)
> - Days 5–7: All exercises, cold
> - Days 8–9: Draw from memory: replication lag diagram, consistent hashing ring, sharding decision tree
> - Days 10–11: Mnemonics for replication lag scenarios and shard key selection rules
> - Days 12–13: Mind map connecting Ch 21 → Ch 20 (consistency) → Ch 22 (leader election)
> - Day 14: Review all diagrams and mnemonics from the past 13 sessions

> **Consistency model mnemonic — LCSEC (weakest → strongest):**
> **"Let Cows Sip Every Creek"**
> - **L**ethal (Eventual) → **C**ausal → **S**ession → **E**ventual → **C**onsistent (Linearizable)

> **CAP mnemonic:** During a **P**artition, you **C**hoose between **C**onsistency or **A**vailability — you can't have both. "**P**ick **C**arefully **A**fter partition."

---

## Section 4 — Data Systems & Global Scale (Ch 28–41)

*The two heaviest chapters in the entire guide are here: Ch 28 (6,409 lines) and Ch 31 (7,056 lines). Each needs ~18h of deep work.*

| # | Chapter | Lines | 1× Read | Deep (3.5×) | Days@1h | Schedule |
|---|---------|-------|---------|-------------|---------|---------|
| 28 | Databases — Choosing, Using, Evolving | 6,409 | 5.0h | **18h** | **18** | R×5, E×4, D×3, M×3, MM×2, Rev×1 |
| 29 | Database Internals Deep Dive | 1,470 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |
| 30 | Data Encoding and Schema Evolution | 1,213 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |
| 31 | Caching at Scale — Redis, CDN, Edge | 7,056 | 5.0h | **18h** | **18** | R×5, E×4, D×3, M×3, MM×2, Rev×1 |
| 32 | Redis and Cache Internals | 1,439 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |
| 33 | Event-Driven — Kafka & Streams | 5,855 | 4.0h | **14h** | **14** | R×4, E×3, D×2, M×2, MM×2, Rev×1 |
| 34 | Kafka Internals | 1,365 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |
| 35 | Batch Processing and Data Pipelines | 1,113 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |
| 36 | Multi-Region Systems | 4,942 | 3.5h | **12h** | **12** | R×3, E×2, D×2, M×2, MM×2, Rev×1 |
| 37 | Data Locality, Compliance, Evolution | 3,779 | 2.5h | **9h** | **9** | R×2, E×2, D, M, MM, Rev, Rev |
| 38 | Cost, Efficiency, Sustainable Design | 4,492 | 3.0h | **10.5h** | **11** | R×3, E×2, D×2, M×2, MM×1, Rev×1 |
| 39 | System Evolution, Migration, Risk | 5,293 | 4.0h | **14h** | **14** | R×4, E×3, D×2, M×2, MM×2, Rev×1 |
| 40 | Deployment Strategies and Operations | 1,687 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |
| 41 | Service Mesh — When, Why, Trade-offs | 1,219 | 1.0h | **3.5h** | **4** | R, E, D, M+MM |

**Section 4 Total: ~34h read → 119h deep → 124 days at 1h/day**

---

### Ch 28 Deep Learning Schedule (18 sessions)

| Day | Activity | Focus |
|-----|---------|-------|
| 1 | **R** | Read: Relational vs NoSQL decision framework, ACID vs BASE |
| 2 | **R** | Read: Write patterns, read patterns, index types |
| 3 | **R** | Read: Sharding, replication, consistency in each DB type |
| 4 | **R** | Read: Migration strategies, schema evolution |
| 5 | **R** | Read: L5 vs L6 table, cost models, exercises section |
| 6 | **E** | Exercises: DB selection scenarios (cold, no peeking) |
| 7 | **E** | Exercises: Schema evolution + migration exercises |
| 8 | **E** | Exercises: "What If X Changes?" — answer 5 aloud |
| 9 | **E** | Exercises: Failure injection scenarios |
| 10 | **D** | Draw: DB selection decision tree from memory |
| 11 | **D** | Draw: Write path for each DB type (SQL, Cassandra, Redis, S3) |
| 12 | **D** | Draw: Index structures (B-tree, LSM, hash) with access patterns |
| 13 | **M** | Mnemonics: ACID properties, CAP position of each DB type |
| 14 | **M** | Mnemonics: When to choose each DB (create a one-liner per DB) |
| 15 | **M** | Mnemonics: Migration steps (the "expand-contract" sequence) |
| 16 | **MM** | Mind map: Ch 28 → branches for each DB type → links to Ch 20, 21, 31 |
| 17 | **MM** | Mind map: Add failure modes, cost drivers, evolution paths |
| 18 | **Rev** | Review: Re-read only the L5 vs L6 table + your diagrams + mnemonics |

---

### Ch 31 Deep Learning Schedule (18 sessions)

| Day | Activity | Focus |
|-----|---------|-------|
| 1 | **R** | Read: Cache fundamentals, cache-aside vs write-through vs read-through |
| 2 | **R** | Read: Cache invalidation strategies, stampede prevention |
| 3 | **R** | Read: Redis architecture, CDN layers |
| 4 | **R** | Read: Edge caching, cache consistency models |
| 5 | **R** | Read: L5 vs L6 table, hot-key problem, exercises |
| 6 | **E** | Exercises: Cache strategy selection (cold) |
| 7 | **E** | Exercises: Hot-key + stampede scenarios |
| 8 | **E** | Exercises: Multi-tier cache decision exercises |
| 9 | **E** | Exercises: "What If" — cache miss storm, Redis down at 3 AM |
| 10 | **D** | Draw: Multi-tier cache hierarchy (L1 in-process → L2 Redis → L3 CDN → origin) |
| 11 | **D** | Draw: Cache stampede — what happens, then the fixed version |
| 12 | **D** | Draw: Cache invalidation flows for each pattern |
| 13 | **M** | Mnemonics: Cache patterns (cache-aside, write-through, write-behind, read-through, write-around) |
| 14 | **M** | Mnemonics: Hit rate formula + what affects it |
| 15 | **M** | Mnemonics: When to use Redis vs Memcached vs CDN vs in-process |
| 16 | **MM** | Mind map: Ch 31 → links to Ch 6 (building blocks), Ch 28 (DB), Ch 36 (multi-region) |
| 17 | **MM** | Mind map: Add failure modes, CDN cache invalidation at global scale |
| 18 | **Rev** | Review: L5 vs L6 table + all your diagrams + mnemonics |

---

## Section 5 — Senior-Level Design Problems (Ch 42–54)

*These are practice problems. The deep learning technique changes here — you design first, then read.*

**Senior problem deep learning technique:**
- **Day 1 (D):** Design it yourself — blank page, 45 minutes. Write it up.
- **Day 2 (R):** Read the full chapter. Mark what you missed.
- **Day 3 (E):** Do all exercises cold.
- **Day 4 (D+M+MM):** Draw the clean architecture from memory + mnemonics + mind map.

| # | Chapter | Lines | 1× Read | Deep (3.5×) | Days@1h | D1 | D2 | D3 | D4 |
|---|---------|-------|---------|-------------|---------|----|----|----|----|
| 42 | URL Shortener | 4,983 | 3.5h | **12h** | **12** | D×2 | R×3 | E×3 | D+M+MM×4 |
| 43 | Single-Region Rate Limiter | 3,234 | 2.0h | **7h** | **7** | D | R×2 | E×2 | D+M+MM×2 |
| 44 | Distributed Cache (Single Cluster) | 3,764 | 2.5h | **9h** | **9** | D | R×2 | E×2 | D+M+MM×4 |
| 45 | Object/File Storage System | 3,861 | 2.5h | **9h** | **9** | D | R×2 | E×2 | D+M+MM×4 |
| 46 | Notification System | 3,899 | 2.5h | **9h** | **9** | D | R×2 | E×2 | D+M+MM×4 |
| 47 | Authentication System | 3,442 | 2.5h | **9h** | **9** | D | R×2 | E×2 | D+M+MM×4 |
| 48 | Search System | 2,802 | 2.0h | **7h** | **7** | D | R×2 | E×2 | D+M+MM×2 |
| 49 | Metrics Collection System | 2,812 | 2.0h | **7h** | **7** | D | R×2 | E×2 | D+M+MM×2 |
| 50 | Background Job Queue | 3,092 | 2.0h | **7h** | **7** | D | R×2 | E×2 | D+M+MM×2 |
| 51 | Payment Flow | 3,148 | 2.0h | **7h** | **7** | D | R×2 | E×2 | D+M+MM×2 |
| 52 | API Gateway | 3,649 | 2.5h | **9h** | **9** | D | R×2 | E×2 | D+M+MM×4 |
| 53 | Real-Time Chat | 3,707 | 2.5h | **9h** | **9** | D | R×2 | E×2 | D+M+MM×4 |
| 54 | Configuration Management | 3,784 | 2.5h | **9h** | **9** | D | R×2 | E×2 | D+M+MM×4 |

**Section 5 Total: ~31.5h read → 109h deep → 109 days at 1h/day**

> **D column = "Design yourself first" session.** This is the most important session for each S5 chapter. You produce a real design document — components, data model, API, failure modes — before reading. The embarrassing gaps in your design become your study targets.

---

## Section 6 — Staff-Level Design Problems (Ch 55–72)

*These are the target. Deep learning here means: design it as if you're in the interview, then use the chapter to find what you missed.*

**Staff problem deep learning technique:**
- **Day 1 (D):** Design it yourself — 45 minutes, no notes, staff-level framing
- **Days 2–3 (R):** Read the full chapter. The chapter is large — take notes on L5 vs L6 differences
- **Day 4 (E):** All exercises cold (especially "What If X Changes?")
- **Day 5 (E):** All failure injection scenarios — narrate what breaks
- **Day 6 (D):** Re-draw architecture from memory — better version than Day 1
- **Day 7+ (M+MM):** Mnemonics for key trade-offs + mind map connecting to prerequisite chapters

| # | Chapter | Lines | 1× Read | Deep (3.5×) | Days@1h |
|---|---------|-------|---------|-------------|---------|
| 55 | Global Rate Limiter | 4,119 | 3.0h | **10.5h** | **11** |
| 56 | Distributed Cache | 4,329 | 3.0h | **10.5h** | **11** |
| 57 | News Feed | 5,085 | 4.0h | **14h** | **14** |
| 58 | Real-Time Collaboration | 4,636 | 3.0h | **10.5h** | **11** |
| 59 | Messaging Platform | 5,295 | 4.0h | **14h** | **14** |
| 60 | Metrics / Observability System | 5,147 | 4.0h | **14h** | **14** |
| 61 | Config, Feature Flags & Secrets | 5,414 | 4.0h | **14h** | **14** |
| 62 | API Gateway / Edge Routing | 5,397 | 4.0h | **14h** | **14** |
| 63 | Search / Indexing System | 4,485 | 3.0h | **10.5h** | **11** |
| 64 | Recommendation / Ranking System | 3,032 | 2.0h | **7h** | **7** |
| 65 | Notification Delivery (Fan-out) | 4,792 | 3.5h | **12h** | **12** |
| 66 | Auth & Authorization System | 4,197 | 3.0h | **10.5h** | **11** |
| 67 | Distributed Scheduler / Orchestration | 4,267 | 3.0h | **10.5h** | **11** |
| 68 | Feature Experimentation / A/B Testing | 4,364 | 3.0h | **10.5h** | **11** |
| 69 | Log Aggregation & Query System | 3,606 | 2.5h | **9h** | **9** |
| 70 | Payment / Transaction Processing | 3,742 | 2.5h | **9h** | **9** |
| 71 | Media Upload & Processing Pipeline | 4,224 | 3.0h | **10.5h** | **11** |
| 72 | Bonus Advanced Topics | 1,008 | 1.0h | **3.5h** | **4** |

**Section 6 Total: ~56h read → 194h deep → 200 days at 1h/day**

---

### Ch 57 (News Feed) — Detailed 14-Session Schedule

| Day | Activity | What you produce |
|-----|---------|-----------------|
| 1 | **Design** | Your own news feed design — blank paper, 45 min, no notes |
| 2 | **R** | Read: Foundations, use cases, fan-out strategies |
| 3 | **R** | Read: Data model, feed storage, content cache, celebrity handling |
| 4 | **R** | Read: Consistency, failure modes, graceful degradation |
| 5 | **R** | Read: Cost, multi-region, security, system evolution |
| 6 | **E** | "What If X Changes?" — 10 questions, 90 sec each, out loud |
| 7 | **E** | Redesign exercises + failure injection scenarios |
| 8 | **E** | Trade-off debates — argue both sides of each debate out loud |
| 9 | **D** | Draw: Full architecture (fan-out worker, feed storage, content cache, celebrity index) |
| 10 | **D** | Draw: Failure propagation diagram — what cascades when each component fails |
| 11 | **M** | Mnemonics: Fan-out decision (push vs pull vs hybrid) one-liner |
| 12 | **M** | Mnemonics: Feed storage design choices (pointer vs full feed) |
| 13 | **MM** | Mind map: Ch 57 → Ch 20 (consistency), Ch 21 (sharding), Ch 31 (caching), Ch 33 (Kafka) |
| 14 | **Rev** | Compare Day 1 design with your Day 9 diagram — score yourself on L6 signals |

---

## Grand Total

| Section | Chapters | Deep Hours | Days at 1h/day |
|---------|---------|-----------|----------------|
| S0 — Fundamentals | 6 | 21h | **24** |
| S1 — Mindset | 6 | 34h | **34** |
| S2 — Framework | 7 | 44h | **44** |
| S3 — Distributed Systems | 8 | 78.5h | **79** |
| S4 — Data Systems | 14 | 119h | **124** |
| S5 — Senior Problems | 13 | 109h | **109** |
| S6 — Staff Problems | 18 | 194h | **200** |
| **TOTAL** | **72** | **~600h** | **~614 days** |

**At 1h/day: ~614 days ≈ 20–21 months**
**At 1.5h/day: ~410 days ≈ 14 months**
**At 2h/day: ~307 days ≈ 10 months**

---

## Monthly Milestones at 1h/Day

| Month | Days | Target | Checkpoint |
|-------|------|--------|-----------|
| 1 | 1–30 | S0 complete | Can explain all 6 building blocks with failure modes |
| 2 | 31–60 | S1 complete | Can name 10 L6 evaluation signals without notes |
| 3–4 | 61–120 | S2 complete | Apply 5-phase framework to any prompt in 2 minutes |
| 5–7 | 121–210 | S3 complete | Answer consistency, CAP, 2PC questions cold in 90 sec |
| 8–12 | 211–360 | S4 complete | Ch 28 + Ch 31 mastered — biggest depth investment |
| 13–16 | 361–480 | S5 complete | Can design all 13 Senior problems in 45 min each |
| 17–21 | 481–614 | S6 complete | Can design all 18 Staff problems at L6 depth |

---

## Quick Reference — Days Per Chapter

*Sorted from most to least time investment. Know your heaviest chapters.*

| Rank | Chapter | Days |
|------|---------|------|
| 1 | Ch 28 Databases | **18** |
| 1 | Ch 31 Caching at Scale | **18** |
| 3 | Ch 57 News Feed | **14** |
| 3 | Ch 59 Messaging Platform | **14** |
| 3 | Ch 60 Metrics System | **14** |
| 3 | Ch 61 Config / Feature Flags | **14** |
| 3 | Ch 62 API Gateway | **14** |
| 3 | Ch 21 Replication & Sharding | **14** |
| 3 | Ch 33 Event-Driven / Kafka | **14** |
| 3 | Ch 39 System Evolution | **14** |
| 11 | Ch 17 Cost & Efficiency | **14** |
| 12 | Ch 22 Leader Election | **12** |
| 12 | Ch 23 Backpressure / Idempotency | **12** |
| 12 | Ch 25 Failure Models | **12** |
| 12 | Ch 36 Multi-Region Systems | **12** |
| 12 | Ch 65 Notification Fan-out | **12** |
| 17 | Ch 55 Global Rate Limiter | **11** |
| 17 | Ch 56 Distributed Cache | **11** |
| ... | Most S6 chapters | **11** |
| ... | Most S5 chapters | **7–9** |
| ... | Short chapters (< 1500 lines) | **4** |

---

## Diagram Templates — Draw These From Memory Weekly

These are the most important diagrams in the course. Make flash cards out of them.

### 1. Consistent Hashing Ring (Ch 6/21)
```
         0
         │
   S3 ●──┼──● S1
      ╲  │  ╱
  K2 ● ╲ │ ╱ ● K1
      ╱  │  ╲
   S4 ●──┼──● S2
         │
       2^32

K1 → clockwise to S1
K2 → clockwise to S3
Add S5 between S3 and S1 → only K1-arc keys move
```

### 2. Fan-out Decision (Ch 57 News Feed)
```
POST CREATED
     │
     ▼
Celebrity? (followers > 10K)
  YES → Fan-out on READ (pull at load time, merge celebrity content)
  NO  → Fan-out on WRITE (push to all follower feed stores)
     │
     ▼
Hybrid: push for normal, pull-merge for celebrities
```

### 3. Consistency Spectrum (Ch 20)
```
WEAK ─────────────────────────────────────── STRONG
  │                                               │
Eventual   Causal   Consistent-Prefix   Session   Linearizable
$0.50/M    $2/M       $5/M              $8/M      $20/M (cross-region)
  │                                               │
Social likes          Chat messages      Bank balance
```

### 4. CAP Triangle (Ch 26)
```
        Consistency
            ▲
           / \
          /   \
         / CA  \      ← No partitions: pick this (traditional RDBMS)
        /       \
       ──────────
      CP       AP
  (Spanner)  (Dynamo)
  HBase      Cassandra
  
During partition: choose CP or AP. You cannot have all three.
```

### 5. Write Path Comparison (Ch 28)
```
PostgreSQL: Write → WAL → Buffer Pool → Disk (B-tree page)
Cassandra:  Write → Commit Log → Memtable → SSTable (LSM)
Redis:      Write → In-memory → AOF log (optional) → RDB snapshot

B-tree: fast reads, slow writes (random I/O)
LSM:    fast writes, slower reads (compaction needed)
```

### 6. SLO Error Budget (Ch 40)
```
SLO: 99.9% → Error budget: 43.8 min/month

Burn rate 1×:   Normal deploys ok
Burn rate 10×:  Only critical fixes
Burn rate 30×:  Feature freeze, all hands on reliability

Formula: remaining_budget = 43.8 - Σ(downtime_minutes × impact_%)
```

---

## Mnemonics Master List

| Chapter | Topic | Mnemonic |
|---------|-------|----------|
| Ch 7 | L6 evaluation signals | **FAST CORD** (Failure, Ambiguity, Scope, Trade-offs, Cost, Org-impact, Real-world, Depth) |
| Ch 6/21 | Consistent hashing ring | "Only **ONE** arc moves when you add a node — **~1/N**" |
| Ch 20 | Consistency models | **"Let Cows Sip Every Creek"** (Lethal=Eventual → Causal → Session → Exact=Linearizable) |
| Ch 23 | Idempotency key lifecycle | **"Generate → Store → Check → Execute → Return"** — GSCER |
| Ch 23 | Retry policies | **"EBJ"** — Exponential Backoff with Jitter (never retry linearly) |
| Ch 25 | Failure cascades | **"CSTO"** — Circuit breaker → Shed load → Throttle → Open circuit |
| Ch 26 | CAP positions | **"CP = Consistent but Paused, AP = Always Partial"** |
| Ch 28 | DB selection rule | **"ROAR"** — Read-heavy → cache; OLAP → column; ACID → SQL; Relationships → Graph |
| Ch 31 | Cache patterns | **"CWRRA"** — Cache-aside, Write-through, Read-through, Write-behind (Rear), Write-Around |
| Ch 40 | Canary decision | **"2× error or 25% p99 → rollback"** |
| Ch 57 | Fan-out strategy | **"Celebs Pull, Normals Push"** |
| Ch 66 | Token design | **"Short Access (5 min), Long Refresh (30 days), Opaque = Revocable"** |
| All S6 | Multi-region trade-off | **"Latency × Consistency = constant"** — you can't minimize both |

---

## Daily Log Template

Use this every single day. Fill in before you start, again when you finish.

```
DATE: ___________
CHAPTER: ___________________ (Ch ____)
PASS: [ P1-Read ] [ P2-Exercises ] [ P2-Diagrams ] [ P2-Mnemonics ] [ P2-MindMap ] [ P3-Mock ]
SESSION: ___ of ___

RECALL (before opening anything — 3 things from yesterday):
1. _______________________________________________
2. _______________________________________________
3. _______________________________________________

TODAY'S WORK:
Start point: ___________________________________
End point:   ___________________________________

MEMORY DUMP (after closing everything — 3 things I learned today):
1. _______________________________________________
2. _______________________________________________
3. _______________________________________________

TOMORROW: Ch ___, Session ___ of ___, Starting at: _______________
WEAK SPOT TO REVISIT: _______________________________

Progress: [S0 ░░░░░░] [S1 ░░░░░░] [S2 ░░░░░░░] [S3 ░░░░░░░░] [S4 ░░░░░░░░░░░░░░] [S5 ░░░░░░░░░░░░░] [S6 ░░░░░░░░░░░░░░░░░░]
```

---

*This plan is designed for 1h/day, 7 days/week. Every day counts. Skipping 1 day is fine. Skipping 3 consecutive days = re-do the recall exercise for the last chapter you touched before resuming.*
