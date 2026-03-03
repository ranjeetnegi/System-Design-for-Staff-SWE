# System Design Interview Preparation for Google Staff Engineer

A comprehensive, structured guide for experienced backend engineers preparing for Staff Engineer (L6) system design interviews at Google and equivalent roles at top technology companies.

---

## At a Glance

| | |
|---|---|
| **Target Role** | Google Staff Engineer (L6) / equivalent |
| **Audience** | Senior Engineers (8+ years) preparing for Staff-level interviews |
| **Chapters** | 72 across 7 sections |
| **Coverage** | Fundamentals, Mindset, Framework, Distributed Systems, Data Systems, Senior-level Problems, Staff-level Problems |
| **Progress** | All 7 sections complete (72 chapters) |

---

## What This Is

This is not a collection of templates to memorize. It is a deep, opinionated guide that takes you from **Staff Engineer mindset** through **repeatable frameworks** and **distributed systems fundamentals** to **30 complete system design problems** at both Senior and Staff levels.

Every chapter emphasizes:
- **Trade-off reasoning** over pattern matching
- **Ambiguity navigation** over memorized steps
- **Judgment under uncertainty** over "correct" answers
- **Holistic systems thinking** over component-level knowledge

---

## Who This Is For

Experienced backend engineers — typically 8+ years — who are:

- Senior at another major tech company, seeking to level-match at Google
- Senior at Google, preparing for internal promotion to Staff
- Technical leaders at startups, seeking formal recognition of that scope
- Engineers at companies where "Staff" means something different, needing to calibrate to Google's bar

You are not learning system design from scratch. You are learning how to **demonstrate your existing capabilities** in the specific context of a Staff-level interview.

---

## Repository Structure

```
System-Design/
├── README.md                  ← You are here
├── Section0/                  ← Fundamentals — Building Blocks of System Design (Ch. 1–6)
│   ├── README.md
│   └── Chapter_1_* … Chapter_6_* (chapter names)
├── Section1/                  ← Staff Engineer Mindset & Evaluation (Ch. 7–12)
│   ├── README.md
│   └── Chapter_7_* … Chapter_12_* (chapter names)
├── Section2/                  ← System Design Framework — 5 Phases (Ch. 13–19)
│   ├── README.md
│   └── Chapter_13_* … Chapter_19_* (chapter names)
├── Section3/                  ← Distributed Systems (Ch. 20–27)
│   ├── README.md
│   └── Chapter_20_* … Chapter_27_* (chapter names)
├── Section4/                  ← Data Systems & Global Scale (Ch. 28–41)
│   ├── README.md
│   └── Chapter_28_* … Chapter_41_* (chapter names)
├── Section5/                  ← Senior-Level Design Problems (Ch. 42–54)
│   ├── README.md
│   └── Chapter_42_* … Chapter_54_* (chapter names)
└── Section6/                  ← Staff-Level Design Problems (Ch. 55–72)
    ├── README.md
    └── Chapter_55_* … Chapter_72_* (chapter names)
```

Each section has its own `README.md` with an overview, learning objectives, and reading guidance.

---

## Table of Contents

### Section 0 — Fundamentals: Building Blocks of System Design

Covers the foundational concepts all system design builds upon — systems, APIs, OS fundamentals, networking, estimation, and core building blocks.

| # | Chapter | Link |
|---|---------|------|
| 1 | Systems, Servers, and Clients | [Chapter 1](Section0/Chapter_1_Systems_Servers_Clients.md) |
| 2 | APIs, Frontend, Backend, and Databases | [Chapter 2](Section0/Chapter_2_APIs_Frontend_Backend_DB.md) |
| 3 | OS Fundamentals | [Chapter 3](Section0/Chapter_3_OS_Fundamentals.md) |
| 4 | Networking Foundations | [Chapter 4](Section0/Chapter_4_Networking_Foundations.md) |
| 5 | Numbers and Estimation | [Chapter 5](Section0/Chapter_5_Numbers_Estimation.md) |
| 6 | Core Building Blocks | [Chapter 6](Section0/Chapter_6_Core_Building_Blocks.md) |

---

### Section 1 — Staff Engineer Mindset & Evaluation

Establishes the foundational mindset: how Google evaluates Staff Engineers and what distinguishes L6 thinking from L5.

| # | Chapter | Link |
|---|---------|------|
| 7 | How Google Evaluates Staff Engineers in System Design Interviews | [Chapter 7](Section1/Chapter_7_How_Google_Evaluates_Staff_Engineers.md) |
| 8 | Scope, Impact, and Ownership at Google Staff Engineer Level | [Chapter 8](Section1/Chapter_8_Scope_Impact_and_Ownership.md) |
| 9 | Designing Systems That Scale Across Teams (Staff Perspective) | [Chapter 9](Section1/Chapter_9_Designing_Systems_That_Scale_Across_Teams.md) |
| 10 | Staff Engineer Mindset — Designing Under Ambiguity | [Chapter 10](Section1/Chapter_10_Staff_Engineer_Mindset_Designing_Under_Ambiguity.md) |
| 11 | Trade-offs, Constraints, and Decision-Making at Staff Level | [Chapter 11](Section1/Chapter_11_Trade_offs_Constraints_and_Decision_Making.md) |
| 12 | Communication and Interview Leadership for Google Staff Engineers | [Chapter 12](Section1/Chapter_12_Communication_and_Interview_Leadership.md) |

---

### Section 2 — System Design Framework (5 Phases)

A repeatable methodology for approaching any system design problem — from vague prompt to justified architecture.

| # | Chapter | Link |
|---|---------|------|
| 13 | System Design Framework | [Chapter 13](Section2/Chapter_13_System_Design_Framework.md) |
| 14 | Phase 1 — Users & Use Cases | [Chapter 14](Section2/Chapter_14_Phase_1_Users_and_Use_Cases.md) |
| 15 | Phase 2 — Functional Requirements | [Chapter 15](Section2/Chapter_15_Phase_2_Functional_Requirements.md) |
| 16 | Phase 3 — Scale: Capacity Planning and Growth | [Chapter 16](Section2/Chapter_16_Phase_3_Scale_Capacity_Planning_and_Growth.md) |
| 17 | Cost, Efficiency, and Sustainable Design | [Chapter 17](Section2/Chapter_17_Cost_Efficiency_and_Sustainable_System_Design.md) |
| 18 | Phase 4 & Phase 5 — NFRs, Assumptions, Constraints | [Chapter 18](Section2/Chapter_18_Phase_4_and_5_Non_Functional_Requirements.md) |
| 19 | End-to-End System Design Using the 5-Phase Framework | [Chapter 19](Section2/Chapter_19_End_to_End_System_Design_5_Phase_Framework.md) |

---

### Section 3 — Distributed Systems

The technical bedrock — deep vocabulary for designing systems that actually work at scale.

| # | Chapter | Link |
|---|---------|------|
| 20 | Consistency Models — Guarantees, Trade-offs, and Failure Behavior | [Chapter 20](Section3/Chapter_20_Consistency_Models.md) |
| 21 | Replication and Sharding — Scaling Without Losing Control | [Chapter 21](Section3/Chapter_21_Replication_and_Sharding.md) |
| 22 | Leader Election, Coordination, and Distributed Locks | [Chapter 22](Section3/Chapter_22_Leader_Election_Coordination_and_Distributed_Locks.md) |
| 23 | Backpressure, Retries, and Idempotency | [Chapter 23](Section3/Chapter_23_Backpressure_Retries_and_Idempotency.md) |
| 24 | Queues, Logs, and Streams — Choosing the Right Asynchronous Model | [Chapter 24](Section3/Chapter_24_Queues_Logs_and_Streams.md) |
| 25 | Failure Models and Partial Failures — Designing for Reality at Staff Level | [Chapter 25](Section3/Chapter_25_Failure_Models_and_Partial_Failures.md) |
| 26 | CAP Theorem — Behavior Under Partition (Applied Case Studies) | [Chapter 26](Section3/Chapter_26_CAP_Theorem_Applied_Case_Studies.md) |
| 27 | Advanced Distributed Systems | [Chapter 27](Section3/Chapter_27_Advanced_Distributed_Systems.md) |

---

### Section 4 — Data Systems & Global Scale

Bridges theory and practice — databases, caches, event pipelines, multi-region architectures, and long-term system concerns.

| # | Chapter | Link |
|---|---------|------|
| 28 | Databases — Choosing, Using, and Evolving Data Stores | [Chapter 28](Section4/Chapter_28_Databases_Choosing_Using_and_Evolving_Data_Stores.md) |
| 29 | Database Internals Deep Dive | [Chapter 29](Section4/Chapter_29_Database_Internals_Deep_Dive.md) |
| 30 | Data Encoding and Schema Evolution | [Chapter 30](Section4/Chapter_30_Data_Encoding_and_Schema_Evolution.md) |
| 31 | Caching at Scale — Redis, CDN, and Edge Systems | [Chapter 31](Section4/Chapter_31_Caching_at_Scale_Redis_CDN_and_Edge_Systems.md) |
| 32 | Redis and Cache Internals | [Chapter 32](Section4/Chapter_32_Redis_and_Cache_Internals.md) |
| 33 | Event-Driven Architectures — Kafka, Streams, and Staff-Level Trade-offs | [Chapter 33](Section4/Chapter_33_Event_Driven_Architectures_Kafka_and_Streams.md) |
| 34 | Kafka Internals | [Chapter 34](Section4/Chapter_34_Kafka_Internals.md) |
| 35 | Batch Processing and Data Pipelines | [Chapter 35](Section4/Chapter_35_Batch_Processing_and_Data_Pipelines.md) |
| 36 | Multi-Region Systems — Geo-Replication, Latency, and Failure | [Chapter 36](Section4/Chapter_36_Multi_Region_Systems.md) |
| 37 | Data Locality, Compliance, and System Evolution | [Chapter 37](Section4/Chapter_37_Data_Locality_Compliance_and_System_Evolution.md) |
| 38 | Cost, Efficiency, and Sustainable System Design | [Chapter 38](Section4/Chapter_38_Cost_Efficiency_and_Sustainable_System_Design.md) |
| 39 | System Evolution, Migration, and Risk Management | [Chapter 39](Section4/Chapter_39_System_Evolution_Migration_and_Risk_Management.md) |
| 40 | Deployment Strategies and Operations | [Chapter 40](Section4/Chapter_40_Deployment_Strategies_and_Operations.md) |
| 41 | Service Mesh — When, Why, and Trade-offs | [Chapter 41](Section4/Chapter_41_Service_Mesh_When_Why_and_Trade_offs.md) |

---

### Section 5 — Senior-Level Design Problems

13 complete system design problems at the Senior Engineer level — production-grade designs with explicit trade-offs.

| # | Chapter | Link |
|---|---------|------|
| 42 | URL Shortener | [Chapter 42](Section5/Chapter_42_URL_Shortener.md) |
| 43 | Single-Region Rate Limiter | [Chapter 43](Section5/Chapter_43_Single_Region_Rate_Limiter.md) |
| 44 | Distributed Cache (Single Cluster) | [Chapter 44](Section5/Chapter_44_Distributed_Cache_Single_Cluster.md) |
| 45 | Object / File Storage System | [Chapter 45](Section5/Chapter_45_Object_and_File_Storage_System.md) |
| 46 | Notification System | [Chapter 46](Section5/Chapter_46_Notification_System.md) |
| 47 | Authentication System (AuthN) | [Chapter 47](Section5/Chapter_47_Authentication_System.md) |
| 48 | Search System | [Chapter 48](Section5/Chapter_48_Search_System.md) |
| 49 | Metrics Collection System | [Chapter 49](Section5/Chapter_49_Metrics_Collection_System.md) |
| 50 | Background Job Queue | [Chapter 50](Section5/Chapter_50_Background_Job_Queue.md) |
| 51 | Payment Flow | [Chapter 51](Section5/Chapter_51_Payment_Flow.md) |
| 52 | API Gateway | [Chapter 52](Section5/Chapter_52_API_Gateway.md) |
| 53 | Real-Time Chat | [Chapter 53](Section5/Chapter_53_Real_Time_Chat.md) |
| 54 | Configuration Management | [Chapter 54](Section5/Chapter_54_Configuration_Management.md) |

---

### Section 6 — Staff-Level Design Problems

17 system design problems at the Staff Engineer level — multi-region, cross-team, production-grade architectures with deep trade-off analysis.

Each Staff-level chapter elevates a Senior problem to global scale, introducing multi-region consistency, cross-team ownership, migration strategy, and organizational impact.

| # | Chapter | Status | Link |
|---|---------|--------|------|
| 55 | Global Rate Limiter | Done | [Chapter 55](Section6/Chapter_55_Global_Rate_Limiter.md) |
| 56 | Distributed Cache | Done | [Chapter 56](Section6/Chapter_56_Distributed_Cache.md) |
| 57 | News Feed | Done | [Chapter 57](Section6/Chapter_57_News_Feed.md) |
| 58 | Real-Time Collaboration | Done | [Chapter 58](Section6/Chapter_58_Real_Time_Collaboration.md) |
| 59 | Messaging Platform | Done | [Chapter 59](Section6/Chapter_59_Messaging_Platform.md) |
| 60 | Metrics / Observability System | Done | [Chapter 60](Section6/Chapter_60_Metrics_and_Observability_System.md) |
| 61 | Configuration, Feature Flags & Secrets Management | Done | [Chapter 61](Section6/Chapter_61_Configuration_Feature_Flags_and_Secrets_Management.md) |
| 62 | API Gateway / Edge Request Routing System | Done | [Chapter 62](Section6/Chapter_62_API_Gateway_and_Edge_Request_Routing.md) |
| 63 | Search / Indexing System (Read-heavy, Latency-sensitive) | Done | [Chapter 63](Section6/Chapter_63_Search_and_Indexing_System.md) |
| 64 | Recommendation / Ranking System (Simplified) | Done | [Chapter 64](Section6/Chapter_64_Recommendation_and_Ranking_System.md) |
| 65 | Notification Delivery System (Fan-out at Scale) | Done | [Chapter 65](Section6/Chapter_65_Notification_Delivery_System_Fan_out_at_Scale.md) |
| 66 | Authentication & Authorization System | Done | [Chapter 66](Section6/Chapter_66_Authentication_and_Authorization_System.md) |
| 67 | Distributed Scheduler / Job Orchestration System | Done | [Chapter 67](Section6/Chapter_67_Distributed_Scheduler_and_Job_Orchestration.md) |
| 68 | Feature Experimentation / A/B Testing Platform | Done | [Chapter 68](Section6/Chapter_68_Feature_Experimentation_and_AB_Testing_Platform.md) |
| 69 | Log Aggregation & Query System | Done | [Chapter 69](Section6/Chapter_69_Log_Aggregation_and_Query_System.md) |
| 70 | Payment / Transaction Processing System | Done | [Chapter 70](Section6/Chapter_70_Payment_and_Transaction_Processing_System.md) |
| 71 | Media Upload & Processing Pipeline | Done | [Chapter 71](Section6/Chapter_71_Media_Upload_and_Processing_Pipeline.md) |
| 72 | Bonus Advanced Topics | Done | [Chapter 72](Section6/Chapter_72_Bonus_Advanced_Topics.md) |

---

## How to Read This Material

This is designed to be read in order, but you can adapt the path to your needs.

**Recommended reading order:**

1. **Section 0** — Ground yourself in the fundamentals: systems, APIs, networking, estimation, and core building blocks
2. **Section 1** — Internalize the Staff mindset before touching architecture
3. **Section 2** — Learn the 5-Phase Framework you will use in every design
4. **Section 3** — Build the distributed systems vocabulary for trade-off reasoning
5. **Section 4** — Connect theory to concrete data systems and global-scale concerns
6. **Section 5** — Practice Senior-level problems to build fluency with the framework
7. **Section 6** — Tackle Staff-level problems that add multi-region scale, cross-team impact, and migration strategy

**If you are short on time:**

- Sections 1 + 2 give you the mindset and framework (essential, ~2 hours)
- Section 3 chapters 20, 23, 25 cover the highest-impact distributed systems concepts
- Section 5 gives you 13 ready-to-practice problems at Senior level
- Section 6 gives you Staff-level versions with elevated scope and complexity

**Principles for effective study:**

- **Read actively.** Pause after each concept and connect it to systems you have built.
- **Practice deliberately.** Reading about system design is not the same as doing it. Practice with a partner who can ask probing questions.
- **Revisit and refine.** First pass plants seeds. Subsequent passes — especially after practice — deepen understanding.
- **Focus on understanding, not coverage.** Deep understanding of a few concepts beats shallow coverage of everything.

---

## Key Concepts

Throughout this guide, these themes recur at every level:

| Concept | What It Means |
|---------|---------------|
| **Ambiguity Navigation** | Turning vague prompts into scoped, justified requirements before designing |
| **Trade-off Reasoning** | Explicitly stating alternatives and why one choice fits this context |
| **Assumptions as First-Class Citizens** | Stating, validating, and designing around what you don't know |
| **Scope Definition** | Deciding what to build, what not to build, and why — the Staff differentiator |
| **Systems Thinking** | Reasoning about interactions, failure propagation, and future constraints |
| **Interview Leadership** | Driving the conversation like a senior technical leader, not answering like a student |

---

## Section 5 vs Section 6 — Senior vs Staff

A central design choice of this guide: every Staff-level problem in Section 6 has a Senior-level counterpart in Section 5. This lets you see exactly what changes when you elevate scope.

| Dimension | Senior (Section 5) | Staff (Section 6) |
|-----------|--------------------|--------------------|
| **Scale** | Single region, single cluster | Multi-region, global |
| **Scope** | One team owns the system | Cross-team ownership boundaries |
| **Trade-offs** | Component-level choices | System-wide and organizational trade-offs |
| **Failure** | Handle errors gracefully | Design for partial failures, cascading failures, regional outages |
| **Evolution** | Build it right | Migrate from the existing system without downtime |
| **Cost** | Implicit | Explicit cost modeling and efficiency targets |

---

## License

Personal study notes. Not affiliated with Google.
