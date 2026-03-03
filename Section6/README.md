# Section 6: Staff Engineer — Design Problems

---

## Overview

This section contains **17 system design problems** at the **Staff Engineer (L6)** level. Each chapter takes a problem that might appear in a Senior (L5) interview and elevates it to global scale, cross-team ownership, migration strategy, and organizational impact.

Staff-level chapters go beyond “make it work at scale.” They demand:

- **Multi-region and global scale** — consistency, latency, and failure across regions
- **Cross-team ownership** — who owns what, conflict resolution, on-call playbooks
- **Evolution and migration** — how to change a live system without downtime
- **Compound and cascading failures** — what breaks when several things fail at once
- **Cost and efficiency** — explicit cost modeling and optimization levers
- **Organizational stress tests** — key person risk, vendor changes, regulatory shifts

Every chapter follows the same deep structure: foundations, requirements, scale modeling, architecture, component design, data model, consistency and concurrency, **failure modes (including multi-component and deployment failures)**, performance, cost, multi-region, security, **evolution and migration**, alternatives, interview calibration, diagrams, and exercises.

---

## Who This Section Is For

- **Staff Engineers (L6)** or Senior Engineers preparing for Staff-level system design interviews at Google or equivalent companies
- Engineers who have completed Section 5 and want the same problems elevated to L6 scope
- Anyone designing or operating systems that span multiple teams and regions

**Prerequisites**: Sections 1–4 (mindset, framework, distributed systems, data systems) and ideally practice with Section 5 (Senior-level problems) first.

---

## Section Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SECTION 6: STAFF-LEVEL DESIGN PROBLEMS                   │
│                                                                             │
│   ┌── Infrastructure & Scale ───────────────────────────────────────────┐   │
│   │  Ch 55: Global Rate Limiter                                         │   │
│   │  Ch 56: Distributed Cache                                           │   │
│   │  Ch 60: Metrics / Observability System                              │   │
│   │  Ch 61: Configuration, Feature Flags & Secrets Management           │   │
│   │  Ch 62: API Gateway / Edge Request Routing System                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│   ┌── Application & User-Facing Systems ────────────────────────────────┐   │
│   │  Ch 57: News Feed                                                   │   │
│   │  Ch 58: Real-Time Collaboration                                    │   │
│   │  Ch 59: Messaging Platform                                          │   │
│   │  Ch 63: Search / Indexing System (Read-heavy, Latency-sensitive)      │   │
│   │  Ch 64: Recommendation / Ranking System (Simplified)                │   │
│   │  Ch 65: Notification Delivery System (Fan-out at Scale)              │   │
│   │  Ch 66: Authentication & Authorization System                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│   ┌── Platforms & Pipelines ────────────────────────────────────────────┐   │
│   │  Ch 67: Distributed Scheduler / Job Orchestration System             │   │
│   │  Ch 68: Feature Experimentation / A/B Testing Platform               │   │
│   │  Ch 69: Log Aggregation & Query System                              │   │
│   │  Ch 70: Payment / Transaction Processing System                      │   │
│   │  Ch 71: Media Upload & Processing Pipeline                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Chapter Index

| # | Chapter | Link |
|---|---------|------|
| 55 | Global Rate Limiter | [Chapter 55](Chapter_55_Global_Rate_Limiter.md) |
| 56 | Distributed Cache | [Chapter 56](Chapter_56_Distributed_Cache.md) |
| 57 | News Feed | [Chapter 57](Chapter_57_News_Feed.md) |
| 58 | Real-Time Collaboration | [Chapter 58](Chapter_58_Real_Time_Collaboration.md) |
| 59 | Messaging Platform | [Chapter 59](Chapter_59_Messaging_Platform.md) |
| 60 | Metrics / Observability System | [Chapter 60](Chapter_60_Metrics_and_Observability_System.md) |
| 61 | Configuration, Feature Flags & Secrets Management | [Chapter 61](Chapter_61_Configuration_Feature_Flags_and_Secrets_Management.md) |
| 62 | API Gateway / Edge Request Routing System | [Chapter 62](Chapter_62_API_Gateway_and_Edge_Request_Routing.md) |
| 63 | Search / Indexing System (Read-Heavy, Latency-Sensitive) | [Chapter 63](Chapter_63_Search_and_Indexing_System.md) |
| 64 | Recommendation / Ranking System (Simplified) | [Chapter 64](Chapter_64_Recommendation_and_Ranking_System.md) |
| 65 | Notification Delivery System (Fan-out at Scale) | [Chapter 65](Chapter_65_Notification_Delivery_System_Fan_out_at_Scale.md) |
| 66 | Authentication & Authorization System | [Chapter 66](Chapter_66_Authentication_and_Authorization_System.md) |
| 67 | Distributed Scheduler / Job Orchestration System | [Chapter 67](Chapter_67_Distributed_Scheduler_and_Job_Orchestration.md) |
| 68 | Feature Experimentation / A/B Testing Platform | [Chapter 68](Chapter_68_Feature_Experimentation_and_AB_Testing_Platform.md) |
| 69 | Log Aggregation & Query System | [Chapter 69](Chapter_69_Log_Aggregation_and_Query_System.md) |
| 70 | Payment / Transaction Processing System | [Chapter 70](Chapter_70_Payment_and_Transaction_Processing_System.md) |
| 71 | Media Upload & Processing Pipeline | [Chapter 71](Chapter_71_Media_Upload_and_Processing_Pipeline.md) |
| 72 | Bonus Advanced Topics | [Chapter 72](Chapter_72_Bonus_Advanced_Topics.md) |

---

## What Makes a Chapter “Staff-Level”

Each chapter includes (at minimum):

1. **L5 vs L6 comparison** — How a Senior answer differs from a Staff answer for the same prompt
2. **Concrete scale** — QPS, storage, growth, and “what breaks first” modeling
3. **Deep failure treatment** — Partial failures, slow dependencies, retry storms, data corruption, blast radius, and at least one **cascading or multi-component failure** and one **deployment/operational failure**
4. **Cost breakdown** — Major cost drivers in $ and optimization levers
5. **Data model and consistency** — Partitioning, schema evolution, race conditions, idempotency
6. **Evolution over time** — V1 → V2 → V3 and how incidents drive redesign; where applicable, **migration strategy** (e.g. dual-write, canary, cutover)
7. **Team ownership and operations** — Who owns what, on-call playbooks, cross-team conflicts
8. **Organizational stress tests** — Key person attrition, vendor/regulatory changes, competitor pressure
9. **Alternatives and explicit rejections** — Why other approaches were considered and rejected
10. **Interview calibration** — How interviewers probe, common L5 mistakes, Staff-level answers and phrases
11. **Diagrams** — At least four: flow, architecture, evolution, and one domain-specific
12. **Exercises and trade-off debates** — “What if X changes?”, failure injection, explicit trade-off discussions

Chapters that have been **L6-reviewed** (e.g. with MASTER_REVIEWER) also include a **Google L6 Review Verification** checklist at the end.

---

## How to Use This Section

- **Interview prep**: Pick 3–5 chapters in domains you know well and 2–3 in domains you don’t. Practice explaining the design and defending trade-offs; use the “Interview Calibration” and “Common L5 Mistakes” sections to self-check.
- **Deep dives**: Use a chapter as a reference when designing or reviewing a similar system (rate limiting, payments, media pipeline, etc.).
- **Reading order**: You can read in any order. Ch 55–56, 59–60, 62–63, 65–67, 70 map most directly to Section 5 counterparts; Ch 57–58, 64, 68–69, 71–72 are more platform/infra-focused and stand alone.

---

## Progress

**17 / 17 chapters** — Section 6 complete.

All chapters are written to Staff depth. Selected chapters (e.g. Ch 64, 65) have been augmented with MASTER_REVIEWER for cascading failures, migration strategy, team ownership, and organizational stress tests; others can be reviewed the same way for consistency.

---

[← Back to main README](../README.md)
