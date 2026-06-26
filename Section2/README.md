# Section 2 — Design Framework

The 5-phase framework that structures every system design answer in this course. Learn this section before starting the case studies — every interview simulation in Sections 5 and 6 follows this template.

---

## Chapters

| Chapter | Title | Key Topic |
|---|---|---|
| [Ch15](Chapter_15_System_Design_Framework.md) | System Design Framework | Overview of the 5-phase approach |
| [Ch16](Chapter_16_Phase_1_Users_and_Use_Cases.md) | Phase 1: Users and Use Cases | Clarifying requirements without annoying the interviewer |
| [Ch17](Chapter_17_Phase_2_Functional_Requirements.md) | Phase 2: Functional Requirements | Pinning down what the system must do |
| [Ch18](Chapter_18_Phase_3_Scale_and_Capacity_Planning.md) | Phase 3: Scale & Capacity Planning | Estimation, QPS, storage, bandwidth |
| [Ch19](Chapter_19_Cost_Efficiency_and_Sustainable_System_Design.md) | Cost Efficiency and Sustainable System Design | Building systems that don't bankrupt you |
| [Ch20](Chapter_20_Phase_4_and_5_Non_Functional_Requirements.md) | Phase 4 & 5: Non-Functional Requirements | Availability, latency, consistency, durability |
| [Ch21](Chapter_21_End_to_End_5_Phase_Framework.md) | End-to-End 5-Phase Framework | Full walkthrough of a complete design |

---

## The 5-Phase Framework

```
Phase 1 — Requirements        (8 min)
  Clarify scope, users, scale, consistency needs

Phase 2 — Estimation          (4 min)
  QPS, storage, bandwidth, peak vs average

Phase 3 — API Design          (4 min)
  Endpoints, request/response shapes, versioning

Phase 4 — Data Model          (4 min)
  Schema, storage choice, access patterns

Phase 5 — HLD + Deep Dive    (20 min)
  Architecture diagram + bottleneck discussion
```

---

## Why This Framework

Interviewers evaluate *how* you think, not just what you build. Jumping straight to the architecture diagram — the most common mistake — skips the parts that reveal Staff-level thinking: requirement disambiguation, trade-off articulation, and constraint-driven design. The 5 phases force the right order.
