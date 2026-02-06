# System Design Interview Preparation — Senior SWE Roadmap

A condensed study path through the [main repo](README.md) for **Senior SWE** (Google L5 / Senior Engineer) system design interview prep.

---

## Target & Goal

**Target:** Google L5 / Senior Engineer system design interviews.

**Goal:** Ship a clear, scalable design in 45 minutes — requirements, capacity estimate, main components, and key trade-offs.

---

## Section 2 — System Design Framework

| Chapter | Topic | Link |
|---------|--------|------|
| 7 | The Staff-Level System Design Framework | [Chapter 7](Section2/Chapter_7.md) |
| 8 | Phase 1 — Users & Use Cases | [Chapter 8](Section2/Chapter_8.md) |
| 9 | Phase 2 — Functional Requirements | [Chapter 9](Section2/Chapter_9.md) |
| 10 | Phase 3 — Scale & Capacity Planning | [Chapter 10](Section2/Chapter_10.md) |
| 11 | Cost, Efficiency, and Sustainable Design | [Chapter 11](Section2/Chapter_11.md) |
| 12 | Phase 4 & Phase 5 — NFRs, Assumptions, Constraints | [Chapter 12](Section2/Chapter_12.md) |
| 13 | End-to-End System Design Using the 5-Phase Framework | [Chapter 13](Section2/Chapter_13.md) |

---

## Section 3 — Distributed Systems (high-signal chapters)

| Chapter | Topic | Link |
|---------|--------|------|
| 14 | Consistency Models — Guarantees, Trade-offs, and Failure Behavior | [Chapter 14](Section3/Chapter_14.md) |
| 17 | Backpressure, Retries, and Idempotency | [Chapter 17](Section3/Chapter_17.md) |
| 18 | Queues, Logs, and Streams — Choosing the Right Asynchronous Model | [Chapter 18](Section3/Chapter_18.md) |
| 19 | Failure Models and Partial Failures — Designing for Reality | [Chapter 19](Section3/Chapter_19.md) |

*Optional for depth:* Ch 15 (Replication & Sharding), Ch 16 (Leader Election & Locks), Ch 20 (CAP Theorem).

---

## Section 4 — Data Systems & Global Scale

| Chapter | Topic | Link |
|---------|--------|------|
| 21 | Databases | [Chapter 21](Section4/Chapter_21.md) |
| 22 | Caching at Scale | [Chapter 22](Section4/Chapter_22.md) |
| 23 | Event-Driven Architectures | [Chapter 23](Section4/Chapter_23.md) |

---

## Section 5 — Senior-Level Design Problems

Practice end-to-end with these 13 problems. Each has a full walkthrough: requirements, scale, architecture, failure handling.

| # | Chapter | Link |
|---|---------|------|
| 28 | URL Shortener | [Chapter 28](Section5/Chapter_28.md) |
| 29 | Single-Region Rate Limiter | [Chapter 29](Section5/Chapter_29.md) |
| 30 | Distributed Cache (Single Cluster) | [Chapter 30](Section5/Chapter_30.md) |
| 31 | Object / File Storage System | [Chapter 31](Section5/Chapter_31.md) |
| 32 | Notification System | [Chapter 32](Section5/Chapter_32.md) |
| 33 | Authentication System (AuthN) | [Chapter 33](Section5/Chapter_33.md) |
| 34 | Search System | [Chapter 34](Section5/Chapter_34.md) |
| 35 | Metrics Collection System | [Chapter 35](Section5/Chapter_35.md) |
| 36 | Background Job Queue | [Chapter 36](Section5/Chapter_36.md) |
| 37 | Payment Flow | [Chapter 37](Section5/Chapter_37.md) |
| 38 | API Gateway | [Chapter 38](Section5/Chapter_38.md) |
| 39 | Real-Time Chat | [Chapter 39](Section5/Chapter_39.md) |
| 40 | Configuration Management | [Chapter 40](Section5/Chapter_40.md) |

---

## Roadmap Summary

```
Section 1          [Optional — skim for mindset]
Section 2          ✅ Full (Ch 7–13) — Framework
Section 3          ✅ Ch 14, 17, 18, 19 — Distributed systems core
Section 4          [Optional — skim / reference]
Section 5          ✅ Full (Ch 28–40) — 13 design problems
Section 6          [Skip for Senior]
```
