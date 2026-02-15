# System Design Interview Preparation — Senior SWE Roadmap

A condensed study path through the [main repo](README.md) for **Senior SWE** (Google L5 / Senior Engineer) system design interview prep.

---

## Target & Goal

**Target:** Google L5 / Senior Engineer system design interviews.

**Goal:** Ship a clear, scalable design in 45 minutes — requirements, capacity estimate, main components, and key trade-offs.

---

## Section 0 — Fundamentals (Basics)

Systems, servers, clients, APIs, frontend/backend/DB, OS (process/memory/CPU/disk), networking, back-of-envelope numbers, and core building blocks (hash, cache, state, idempotency, queue, sync/async). **Do this first if fundamentals are rusty** — it underpins the framework and design problems.

| Ch | Link |
|----|------|
| 1 | [Ch 1: Systems, Servers, Clients](Section0/Basics_1_Systems_Servers_Clients.md) |
| 2 | [Ch 2: APIs, Frontend, Backend, DB](Section0/Basics_2_APIs_Frontend_Backend_DB.md) |
| 3 | [Ch 3: OS Fundamentals](Section0/Basics_3_OS_Fundamentals.md) |
| 4 | [Ch 4: Networking Foundations](Section0/Basics_4_Networking_Foundations.md) |
| 5 | [Ch 5: Numbers & Estimation](Section0/Basics_5_Numbers_Estimation.md) |
| 6 | [Ch 6: Core Building Blocks](Section0/Basics_6_Core_Building_Blocks.md) |

*When to use:* Before or alongside Section 2. Use for quick reference on request paths, capacity math, API/DB trade-offs, and building-block choices during design.

---

## Section 1 — Mindset (skim)

Skim for interview presence: designing under ambiguity and leading the conversation.

| Ch | Link |
|----|------|
| 10 | [Ch 10: Staff Engineer Mindset](Section1/Chapter_10_Staff_Engineer_Mindset_Designing_Under_Ambiguity.md) |
| 12 | [Ch 12: Communication and Interview Leadership](Section1/Chapter_12_Communication_and_Interview_Leadership.md) |

*Optional:* Ch 7–9, 11 for full mindset context.

---

## Section 2 — System Design Framework

| Ch | Link |
|----|------|
| 13 | [Ch 13: System Design Framework](Section2/Chapter_13_System_Design_Framework.md) |
| 14 | [Ch 14: Phase 1 — Users and Use Cases](Section2/Chapter_14_Phase_1_Users_and_Use_Cases.md) |
| 15 | [Ch 15: Phase 2 — Functional Requirements](Section2/Chapter_15_Phase_2_Functional_Requirements.md) |
| 16 | [Ch 16: Phase 3 — Scale, Capacity, Growth](Section2/Chapter_16_Phase_3_Scale_Capacity_Planning_and_Growth.md) |
| 17 | [Ch 17: Cost Efficiency](Section2/Chapter_17_Cost_Efficiency_and_Sustainable_System_Design.md) |
| 18 | [Ch 18: Phase 4 & 5 — Non-Functional Requirements](Section2/Chapter_18_Phase_4_and_5_Non_Functional_Requirements.md) |
| 19 | [Ch 19: End-to-End 5-Phase Framework](Section2/Chapter_19_End_to_End_System_Design_5_Phase_Framework.md) |

---

## Section 3 — Distributed Systems (core)

| Ch | Link |
|----|------|
| 20 | [Ch 20: Consistency Models](Section3/Chapter_20_Consistency_Models.md) |
| 21 | [Ch 21: Replication and Sharding](Section3/Chapter_21_Replication_and_Sharding.md) |
| 22 | [Ch 22: Leader Election, Coordination, Locks](Section3/Chapter_22_Leader_Election_Coordination_and_Distributed_Locks.md) *(optional)* |
| 23 | [Ch 23: Backpressure, Retries, Idempotency](Section3/Chapter_23_Backpressure_Retries_and_Idempotency.md) |
| 24 | [Ch 24: Queues, Logs, Streams](Section3/Chapter_24_Queues_Logs_and_Streams.md) |
| 25 | [Ch 25: Failure Models and Partial Failures](Section3/Chapter_25_Failure_Models_and_Partial_Failures.md) |
| 26 | [Ch 26: CAP — Case Studies](Section3/Chapter_26_CAP_Theorem_Applied_Case_Studies.md) *(optional)* |
| 26S | [Ch 26 Supplement: Advanced Distributed Systems](Section3/Chapter_26_Supplement_Advanced_Distributed_Systems.md) *(optional)* |

---

## Section 4 — Data Systems (required reference)

Use when practicing problems that need DB, cache, or async flows. Don't skip — L5 interviews expect you to justify storage and caching choices.

| Ch | Link |
|----|------|
| 27 | [Ch 27: Databases](Section4/Chapter_27_Databases_Choosing_Using_and_Evolving_Data_Stores.md) |
| 28 | [Ch 28: Caching at Scale](Section4/Chapter_28_Caching_at_Scale_Redis_CDN_and_Edge_Systems.md) |
| 29 | [Ch 29: Event-Driven Architectures, Kafka](Section4/Chapter_29_Event_Driven_Architectures_Kafka_and_Streams.md) |

*Full section also includes:* Ch 30 (Multi-Region), 31 (Data Locality), 32 (Cost Efficiency), 33 (System Evolution) + supplements.

---

## Section 5 — Senior-Level Design Problems

Practice end-to-end with these 13 problems. Each has a full walkthrough: requirements, scale, architecture, failure handling.

**Priority:** Do **6–8 problems in depth** (timed, out loud, with diagrams). Quality beats covering all 13. Start with the must-practice set.

### Must practice (high frequency at L5)

| Ch | Link |
|----|------|
| 34 | [Ch 34: URL Shortener](Section5/Chapter_34_URL_Shortener.md) |
| 35 | [Ch 35: Single-Region Rate Limiter](Section5/Chapter_35_Single_Region_Rate_Limiter.md) |
| 36 | [Ch 36: Distributed Cache](Section5/Chapter_36_Distributed_Cache_Single_Cluster.md) |
| 37 | [Ch 37: Object and File Storage](Section5/Chapter_37_Object_and_File_Storage_System.md) |
| 38 | [Ch 38: Notification System](Section5/Chapter_38_Notification_System.md) |
| 45 | [Ch 45: Real-Time Chat](Section5/Chapter_45_Real_Time_Chat.md) |

### Second tier

| Ch | Link |
|----|------|
| 39 | [Ch 39: Authentication System](Section5/Chapter_39_Authentication_System.md) |
| 40 | [Ch 40: Search System](Section5/Chapter_40_Search_System.md) |
| 41 | [Ch 41: Metrics Collection](Section5/Chapter_41_Metrics_Collection_System.md) |
| 42 | [Ch 42: Background Job Queue](Section5/Chapter_42_Background_Job_Queue.md) |
| 43 | [Ch 43: Payment Flow](Section5/Chapter_43_Payment_Flow.md) |
| 44 | [Ch 44: API Gateway](Section5/Chapter_44_API_Gateway.md) |
| 46 | [Ch 46: Configuration Management](Section5/Chapter_46_Configuration_Management.md) |

---

## Practice strategy

- **Timebox:** 45 minutes end-to-end. Roughly: clarify & requirements (5–8 min), scale/capacity (5 min), high-level design (15–20 min), deep dive 1–2 components (10–15 min), trade-offs & wrap-up (5 min).
- **Practice out loud:** Talk through reasoning, state assumptions, draw the diagram as you go.
- **Use the framework:** Follow the 5-phase flow (Section 2) every time.
- **Reference as needed:** When a problem needs DB choice, caching, or events, open the relevant Section 4 chapter and Section 3 (e.g. sharding, consistency).

---

## Roadmap Summary

| Section | Chapters |
|---------|----------|
| 0 | Ch 1–6 (fundamentals; do first if rusty) |
| 1 | Skim Ch 10, 12 |
| 2 | Ch 13–19 (full) |
| 3 | Ch 20–26 |
| 4 | Ch 27–29 (core); full section 27–33 |
| 5 | Ch 34–46; prioritize 6–8 in depth (must-practice first) |
| 6 | Skip for Senior |
