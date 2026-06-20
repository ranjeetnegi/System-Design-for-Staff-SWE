# System Design Interview Preparation — Senior SWE Roadmap

A condensed study path through the [main repo](README.md) for **Senior SWE** (Google L5 / Senior Engineer) system design interview prep.

---

## Target & Goal

**Target:** Google L5 / Senior Engineer system design interviews.

**Goal:** Ship a clear, scalable design in 45 minutes — requirements, capacity estimate, main components, and key trade-offs.

---

## Section 1 — Fundamentals (Basics)

Systems, servers, clients, APIs, frontend/backend/DB, OS (process/memory/CPU/disk), networking, back-of-envelope numbers, and core building blocks (hash, cache, state, idempotency, queue, sync/async). **Do this first if fundamentals are rusty** — it underpins the framework and design problems.

| Ch | Link |
|----|------|
| 9  | [Ch 9: Systems, Servers, Clients](Section1/Chapter_9_Systems_Servers_Clients.md) |
| 10 | [Ch 10: APIs, Frontend, Backend, DB](Section1/Chapter_10_APIs_Frontend_Backend_DB.md) |
| 11 | [Ch 11: OS Fundamentals](Section1/Chapter_11_OS_Fundamentals.md) |
| 12 | [Ch 12: Networking Foundations](Section1/Chapter_12_Networking_Foundations.md) |
| 13 | [Ch 13: Numbers & Estimation](Section1/Chapter_13_Numbers_Estimation.md) |
| 14 | [Ch 14: Core Building Blocks](Section1/Chapter_14_Core_Building_Blocks.md) |

*When to use:* Before or alongside Section 2. Use for quick reference on request paths, capacity math, API/DB trade-offs, and building-block choices during design.

---

## Section 0 — Mindset (skim)

Skim for interview presence: designing under ambiguity, leading the conversation, and trade-off reasoning.

| Ch | Link |
|----|------|
| 4  | [Ch 4: Staff Engineer Mindset / Designing Under Ambiguity](Section0/Chapter_4_Staff_Engineer_Mindset_Designing_Under_Ambiguity.md) |
| 6  | [Ch 6: Communication and Interview Leadership](Section0/Chapter_6_Communication_and_Interview_Leadership.md) |
| 8  | [Ch 8: Interview Execution Strategy](Section0/Chapter_8_Interview_Execution_Strategy.md) |

*Optional:* Ch 1–3, 5, 7 for full mindset context. Ch 8 is especially valuable — covers the 45-minute time map, clarification art, reading interviewer signals, and two full annotated mock interviews.

---

## Section 2 — System Design Framework

| Ch | Link |
|----|------|
| 15 | [Ch 15: System Design Framework](Section2/Chapter_15_System_Design_Framework.md) |
| 16 | [Ch 16: Phase 1 — Users and Use Cases](Section2/Chapter_16_Phase_1_Users_and_Use_Cases.md) |
| 17 | [Ch 17: Phase 2 — Functional Requirements](Section2/Chapter_17_Phase_2_Functional_Requirements.md) |
| 18 | [Ch 18: Phase 3 — Scale, Capacity, Growth](Section2/Chapter_18_Phase_3_Scale_Capacity_Planning.md) |
| 19 | [Ch 19: Cost Efficiency](Section2/Chapter_19_Cost_Efficiency_and_Sustainable_System_Design.md) |
| 20 | [Ch 20: Phase 4 & 5 — Non-Functional Requirements](Section2/Chapter_20_Phase_4_and_5_Non_Functional_Requirements.md) |
| 21 | [Ch 21: End-to-End 5-Phase Framework](Section2/Chapter_21_End_to_End_5_Phase_Framework.md) |

---

## Section 3 — Distributed Systems (core)

| Ch | Link |
|----|------|
| 22 | [Ch 22: Consistency Models](Section3/Chapter_22_Consistency_Models.md) |
| 23 | [Ch 23: Replication and Sharding](Section3/Chapter_23_Replication_and_Sharding.md) |
| 24 | [Ch 24: Leader Election, Coordination, Locks](Section3/Chapter_24_Leader_Election_Coordination_and_Distributed_Locks.md) *(optional)* |
| 25 | [Ch 25: Backpressure, Retries, Idempotency](Section3/Chapter_25_Backpressure_Retries_and_Idempotency.md) |
| 26 | [Ch 26: Queues, Logs, Streams](Section3/Chapter_26_Queues_Logs_and_Streams.md) |
| 27 | [Ch 27: Failure Models and Partial Failures](Section3/Chapter_27_Failure_Models_and_Partial_Failures.md) |
| 28 | [Ch 28: CAP — Case Studies](Section3/Chapter_28_CAP_Theorem_Applied_Case_Studies.md) *(optional)* |
| 29 | [Ch 29: Advanced Distributed Systems](Section3/Chapter_29_Advanced_Distributed_Systems.md) *(optional)* |

---

## Section 4 — Data Systems (required reference)

Use when practicing problems that need DB, cache, or async flows. Don't skip — L5 interviews expect you to justify storage and caching choices.

| Ch | Link |
|----|------|
| 30 | [Ch 30: Databases](Section4/Chapter_30_Databases_Choosing_Using_and_Evolving_Data_Stores.md) |
| 33 | [Ch 33: Caching at Scale](Section4/Chapter_33_Caching_at_Scale_Redis_CDN_and_Edge_Systems.md) |
| 35 | [Ch 35: Event-Driven Architectures, Kafka](Section4/Chapter_35_Event_Driven_Architectures_Kafka_and_Streams.md) |

### Supplements (use as needed)

| Supplement | Senior (L5) | Staff (L6) | When to use |
|------------|-------------|------------|-------------|
| [Ch 31: DB Internals](Section4/Chapter_31_Database_Internals_Deep_Dive.md) | Optional | Recommended | Deep DB questions (B-tree, WAL, MVCC) |
| [Ch 32: Data Encoding & Schema Evolution](Section4/Chapter_32_Data_Encoding_and_Schema_Evolution.md) | Skim | Full | API contracts, Kafka schema, Protobuf vs JSON |
| [Ch 34: Redis Internals](Section4/Chapter_34_Redis_and_Cache_Internals.md) | Optional | Recommended | Cache design, Redis Cluster, eviction |
| [Ch 36: Kafka Internals](Section4/Chapter_36_Kafka_Internals.md) | Optional | Recommended | Kafka partitions, consumer lag, ISR |
| [Ch 37: Batch Processing](Section4/Chapter_37_Batch_Processing_and_Data_Pipelines.md) | Reference | Full | Background Jobs, ETL, batch vs stream |
| [Ch 42: Deployment & Ops](Section4/Chapter_42_Deployment_Strategies_and_Operations.md) | **Recommended** | **Required** | SLO/error budget, runbooks, observability, rollback |
| [Ch 43: Service Mesh](Section4/Chapter_43_Service_Mesh_When_Why_and_Trade_offs.md) | Skip | **Recommended** | 50+ services, mTLS, retry consistency |

*Full section also includes:* Ch 38 (Multi-Region), Ch 39 (Data Locality), Ch 40 (Cost Efficiency), Ch 41 (System Evolution).

---

## Section 5 — Senior-Level Design Problems

Practice end-to-end with these 13 problems. Each has a full walkthrough: requirements, scale, architecture, failure handling.

**Priority:** Do **6–8 problems in depth** (timed, out loud, with diagrams). Quality beats covering all 13. Start with the must-practice set.

### Must practice (high frequency at L5)

| Ch | Link |
|----|------|
| 49 | [Ch 49: URL Shortener](Section5/Chapter_49_URL_Shortener.md) |
| 50 | [Ch 50: Single-Region Rate Limiter](Section5/Chapter_50_Single_Region_Rate_Limiter.md) |
| 51 | [Ch 51: Distributed Cache](Section5/Chapter_51_Distributed_Cache_Single_Cluster.md) |
| 52 | [Ch 52: Object and File Storage](Section5/Chapter_52_Object_and_File_Storage_System.md) |
| 53 | [Ch 53: Notification System](Section5/Chapter_53_Notification_System.md) |
| 60 | [Ch 60: Real-Time Chat](Section5/Chapter_60_Real_Time_Chat.md) |

### Second tier

| Ch | Link |
|----|------|
| 54 | [Ch 54: Authentication System](Section5/Chapter_54_Authentication_System.md) |
| 55 | [Ch 55: Search System](Section5/Chapter_55_Search_System.md) |
| 56 | [Ch 56: Metrics Collection](Section5/Chapter_56_Metrics_Collection_System.md) |
| 57 | [Ch 57: Background Job Queue](Section5/Chapter_57_Background_Job_Queue.md) |
| 58 | [Ch 58: Payment Flow](Section5/Chapter_58_Payment_Flow.md) |
| 59 | [Ch 59: API Gateway](Section5/Chapter_59_API_Gateway.md) |
| 61 | [Ch 61: Configuration Management](Section5/Chapter_61_Configuration_Management.md) |

---

## Practice strategy

- **Timebox:** 45 minutes end-to-end. Roughly: clarify & requirements (5–8 min), scale/capacity (5 min), high-level design (15–20 min), deep dive 1–2 components (10–15 min), trade-offs & wrap-up (5 min).
- **Practice out loud:** Talk through reasoning, state assumptions, draw the diagram as you go.
- **Use the framework:** Follow the 5-phase flow (Section 2) every time.
- **Reference as needed:** When a problem needs DB choice, caching, or events, open the relevant Section 4 chapter and Section 3 (e.g. sharding, consistency).

---

## Roadmap Summary

| Section | Chapters | Notes |
|---------|----------|-------|
| 1 | Ch 9–14 (fundamentals; do first if rusty) | — |
| 0 | Skim Ch 4, 6, 8 | Ch 8 especially valuable for interview execution |
| 2 | Ch 15–21 (full) | Core design framework |
| 3 | Ch 22–27 (Ch 28–29 optional) | Distributed systems essentials |
| 4 | Ch 30, 33, 35 (core); supplements as needed | Ch 42 (Deployment & Ops) **recommended** |
| 5 | Ch 49–61; prioritize 6–8 in depth | Must-practice first |
| 6 | Skip for Senior | Staff-level case studies |

---

## Staff Path Additions (L6)

If preparing for **Staff Engineer (L6)** interviews, add:

| Section | Additional material |
|---------|---------------------|
| **0** | All of Section 0 (Ch 1–8) — Staff mindset, scope/impact, trade-off reasoning |
| **4** | All supplements; especially Ch 43 (Service Mesh), Ch 32 (Data Encoding), Ch 37 (Batch Processing) |
| **6** | Full Section 6 (Ch 62–93) — Staff-level design problems + Google foundational systems (GFS, Bigtable, MapReduce, Chubby, Spanner, Borg) |
| **7** | Section 7 (Ch 94–106) — Engineering craft (debugging, on-call, migrations, code review) |

See [README](README.md) and [TODO_MASTER_PLAN.md](TODO_MASTER_PLAN.md) for the full Staff path and chapter status.
