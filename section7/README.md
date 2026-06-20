# Section 7: Engineering Craft

> Skills that apply across every technical domain. Not tied to any single system or architecture — these are the disciplines that separate engineers who build things from engineers who build things *well*.

---

## Chapters

| Chapter | Title | Status |
|---------|-------|--------|
| 73 | [Debugging as a Discipline](Chapter_73_Debugging_as_a_Discipline.md) | ✅ Complete |
| 74 | [On-Call Engineering](Chapter_74_On_Call_Engineering.md) | 📝 TODO |
| 75 | [Code Review as a Discipline](Chapter_75_Code_Review_as_a_Discipline.md) | 📝 TODO |
| 76 | [Migrations and Safe Changes](Chapter_76_Migrations_and_Safe_Changes.md) | 📝 TODO |
| 77 | [Technical Writing](Chapter_77_Technical_Writing.md) | 📝 TODO |
| 78 | [Testing as a Discipline](Chapter_78_Testing_as_a_Discipline.md) | 📝 TODO |
| 79 | [API Design as a Discipline](Chapter_79_API_Design_as_a_Discipline.md) | 📝 TODO |
| 80 | [Security Mindset](Chapter_80_Security_Mindset.md) | 📝 TODO |
| 81 | [Refactoring Large Systems](Chapter_81_Refactoring_Large_Systems.md) | 📝 TODO |
| 82 | [Capacity Planning](Chapter_82_Capacity_Planning.md) | 📝 TODO |

---

## Priority Order (when writing)

**Tier 1 — Write these first (direct L6 eval impact):**
- Ch 74: On-Call Engineering — operational excellence, incident command, SLOs
- Ch 75: Code Review — explicitly in promotion criteria, teaches vs corrects
- Ch 76: Migrations — "how do you migrate live?" is in every SSE interview

**Tier 2 — High value:**
- Ch 77: Technical Writing — design docs, RFCs, ADRs, post-mortems
- Ch 78: Testing — test strategy, chaos engineering, load testing
- Ch 79: API Design — contracts, versioning, error design, REST vs gRPC

**Tier 3 — Nice to have:**
- Ch 80: Security Mindset — threat modeling, OWASP, auth patterns
- Ch 81: Refactoring — seam-based extraction, managing technical debt
- Ch 82: Capacity Planning — load testing, right-sizing, SLO-driven headroom

---

## What belongs in Section 7

A chapter belongs here if:
1. It applies regardless of which technical domain you are in (databases, messaging, storage, etc.)
2. It is a *discipline* — a learnable method, not just a concept
3. It is not covered adequately in Sections 1–6

A chapter does NOT belong here if it is tightly coupled to a specific technology (e.g., "how Kafka works" belongs in Section 4).
