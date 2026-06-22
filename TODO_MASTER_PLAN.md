# Master Plan — SysDesign L6 Guide
# Status as of 2026-06-22

Legend:
  ✅ DONE      — 2,000+ lines, full depth
  🟡 THIN      — exists but under 2,000 lines, needs expansion
  📄 STUB      — outline/plan only (< 200 lines), needs full write
  ❌ MISSING   — not created yet

---

## SECTION 0 — Staff Engineer Mindset (Ch1–8)

  ✅ Ch1   How Google Evaluates Staff Engineers                    4,477 lines
  ✅ Ch2   Scope, Impact, and Ownership                           3,309 lines
  ✅ Ch3   Designing Systems That Scale Across Teams              4,837 lines
  ✅ Ch4   Staff Engineer Mindset / Designing Under Ambiguity     4,520 lines
  ✅ Ch5   Trade-offs, Constraints, and Decision Making           3,103 lines
  ✅ Ch6   Communication and Interview Leadership                 4,006 lines
  ✅ Ch7   Staff Engineer Real-World Skills                       2,880 lines
  ✅ Ch8   Interview Execution Strategy                          2,501 lines

---

## SECTION 1 — Foundations (Ch9–14)

  ✅ Ch9   Systems, Servers, Clients                              2,818 lines
  🟡 Ch10  APIs, Frontend, Backend, DB                           2,379 lines  ← expand
  🟡 Ch11  OS Fundamentals                                       2,325 lines  ← expand
  ✅ Ch12  Networking Foundations                                 2,512 lines
  ✅ Ch13  Numbers & Estimation                                   2,934 lines
  ✅ Ch14  Core Building Blocks                                   3,113 lines

---

## SECTION 2 — Design Framework (Ch15–21)

  ✅ Ch15  System Design Framework                                2,884 lines
  ✅ Ch16  Phase 1: Users and Use Cases                           3,791 lines
  ✅ Ch17  Phase 2: Functional Requirements                       3,075 lines
  ✅ Ch18  Phase 3: Scale & Capacity Planning                     2,693 lines
  ✅ Ch19  Cost Efficiency and Sustainable System Design          4,104 lines
  ✅ Ch20  Phase 4 & 5: Non-Functional Requirements              2,549 lines
  🟡 Ch21  End-to-End 5-Phase Framework                          2,483 lines  ← expand

---

## SECTION 3 — Distributed Systems Core (Ch22–29)

  ✅ Ch22  Consistency Models                                     5,229 lines
  ✅ Ch23  Replication and Sharding                               8,419 lines
  ✅ Ch24  Leader Election, Coordination, Distributed Locks       8,129 lines
  ✅ Ch25  Backpressure, Retries, and Idempotency                 7,962 lines
  ✅ Ch26  Queues, Logs, and Streams                              7,923 lines
  ✅ Ch27  Failure Models and Partial Failures                    7,467 lines
  ✅ Ch28  CAP Theorem: Applied Case Studies                      5,003 lines
  ✅ Ch29  Advanced Distributed Systems (HLC, CRDT, etc.)         6,896 lines

---

## SECTION 4 — Data Systems & Infrastructure (Ch30–48)

  ✅ Ch30  Databases: Choosing, Using, and Evolving               10,372 lines
  ✅ Ch31  Database Internals Deep Dive                           6,128 lines
  ✅ Ch32  Data Encoding & Schema Evolution                       3,911 lines
  ✅ Ch33  Caching at Scale: Redis, CDN, Edge                     8,676 lines
  ✅ Ch34  Redis & Cache Internals                                2,905 lines
  ✅ Ch35  Event-Driven Architectures: Kafka, Streams             7,993 lines
  ✅ Ch36  Kafka Internals                                        5,226 lines
  ✅ Ch37  Batch Processing and Data Pipelines                    4,577 lines
  ✅ Ch38  Multi-Region Systems                                   8,566 lines
  ✅ Ch39  Data Locality, Compliance, System Evolution            6,350 lines
  ✅ Ch40  Cost Efficiency and Sustainable System Design          7,788 lines
  ✅ Ch41  System Evolution, Migration, Risk Management           5,724 lines
  ✅ Ch42  Deployment Strategies and Operations                   3,400 lines
  ✅ Ch43  Service Mesh: When, Why, Trade-offs                    3,235 lines
  ✅ Ch44  ML System Design                                       3,243 lines
  ✅ Ch45  Google's Foundational Systems (overview)               3,384 lines
  ✅ Ch46  Data Warehouse / OLAP                                  2,901 lines
  ✅ Ch47  Kubernetes Internals                                   2,565 lines
  🟡 Ch48  Consensus Deep Dive (Raft & Paxos)                    2,216 lines  ← expand

---

## SECTION 5 — Senior SWE L5 Case Studies (Ch49–75)

  Note: Section 5 = L5 (Senior SWE). Section 6 = L6 (Staff). Keep them separate.

  ### Original Case Studies (Ch49–61)

  ✅ Ch49  URL Shortener                                          5,834 lines
  ✅ Ch50  Single-Region Rate Limiter                             3,234 lines
  ✅ Ch51  Distributed Cache (Single Cluster)                     3,764 lines
  ✅ Ch52  Object and File Storage System                         3,861 lines
  ✅ Ch53  Notification System                                    3,899 lines
  ✅ Ch54  Authentication System                                  3,442 lines
  🟡 Ch55  Search System                                         2,802 lines  ← expand
  🟡 Ch56  Metrics Collection System                             2,812 lines  ← expand
  ✅ Ch57  Background Job Queue                                   3,092 lines
  ✅ Ch58  Payment Flow                                           3,148 lines
  ✅ Ch59  API Gateway                                            3,649 lines
  ✅ Ch60  Real-Time Chat                                         3,707 lines
  ✅ Ch61  Configuration Management                               3,784 lines

  ### New L5 Design Problems (Ch62–71)
  Written 2026-06-22. API design + DB schema included. Pseudocode kept only for algorithms.

  ✅ Ch62  Web Crawler                                            3,730 lines
  ✅ Ch63  Proximity Service (Yelp / Nearby)                     2,685 lines
  ✅ Ch64  Hotel Reservation System                               2,386 lines
  ✅ Ch65  Key-Value Store                                        2,418 lines
  ✅ Ch66  Leaderboard System                                     2,191 lines
  ✅ Ch67  File Sync Service (Dropbox)                            2,124 lines
  ✅ Ch68  Ride Sharing (Uber/Lyft)                               2,035 lines
  ✅ Ch69  Live Streaming (Twitch)                                2,094 lines
  ✅ Ch70  Ticketing System (Ticketmaster)                        2,297 lines
  ✅ Ch71  Stock / Trading Feed                                   2,164 lines

  ### Missing L5 Equivalents (Ch72–75)
  High-frequency L5 questions that currently only have Staff-level (Section 6) versions.

  ❌ Ch72  Video Streaming — L5                  0 lines  ← MISSING — very high freq
             (upload, transcode pipeline, CDN, adaptive bitrate; single-region depth.
              Staff version = Ch100)
  ❌ Ch73  News Feed — L5                        0 lines  ← MISSING — high freq
             (fan-out write vs read, timeline storage, cursor pagination, basic ranking.
              Staff version = Ch78)
  ❌ Ch74  Location-Based Service — L5           0 lines  ← MISSING — high freq
             (driver location tracking, GeoHash, radius search; single-region.
              Staff version = Ch101)
  ❌ Ch75  Typeahead / Autocomplete — L5         0 lines  ← MISSING — very high freq warmup
             (Trie, prefix search, top-K with Redis, sub-100ms latency budget.
              Staff version = Ch102)

---

## SECTION 6 — Staff-Level Case Studies + Google Systems / L6 (Ch76–107)

  ### Staff Case Studies (Ch76–93)
  ✅ Ch76  Global Rate Limiter                                    4,119 lines
  ✅ Ch77  Distributed Cache                                      4,329 lines
  ✅ Ch78  News Feed                                              5,085 lines
  ✅ Ch79  Real-Time Collaboration                                4,636 lines
  ✅ Ch80  Messaging Platform                                     5,295 lines
  ✅ Ch81  Metrics and Observability System                       5,147 lines
  ✅ Ch82  Configuration, Feature Flags, Secrets                  5,414 lines
  ✅ Ch83  API Gateway and Edge Request Routing                   5,397 lines
  ✅ Ch84  Search and Indexing System                             4,485 lines
  🟡 Ch85  Recommendation and Ranking System                     3,032 lines  ← expand
  ✅ Ch86  Notification Delivery: Fan-out at Scale               4,792 lines
  ✅ Ch87  Authentication and Authorization System                4,197 lines
  ✅ Ch88  Distributed Scheduler and Job Orchestration            4,267 lines
  ✅ Ch89  Feature Experimentation and A/B Testing                4,364 lines
  ✅ Ch90  Log Aggregation and Query System                       3,606 lines
  ✅ Ch91  Payment and Transaction Processing                     3,742 lines
  ✅ Ch92  Media Upload and Processing Pipeline                   4,224 lines
  🟡 Ch93  Bonus Advanced Topics                                 1,008 lines  ← expand or integrate

  ### Google Foundational Systems (Ch94–99)
  ✅ Ch94  GFS — Google File System                              2,501 lines
  ✅ Ch95  Bigtable                                              2,501 lines
  ✅ Ch96  MapReduce                                             2,502 lines
  ✅ Ch97  Chubby — Distributed Lock Service                     2,642 lines
  🟡 Ch98  Spanner — Globally Distributed Database               2,407 lines  ← expand
  🟡 Ch99  Borg — Cluster Manager                                2,125 lines  ← expand

  ### Gap Case Studies (Ch100–107)
  ✅ Ch100 Video Streaming (YouTube/Netflix/TikTok)              2,536 lines
  🟡 Ch101 Location & Mapping (Uber/Google Maps)                 2,281 lines  ← expand
  🟡 Ch102 Typeahead / Autocomplete                              2,256 lines  ← expand
  ✅ Ch103 Ad Serving & Real-Time Bidding                        2,531 lines
  🟡 Ch104 Social Graph (Instagram/Twitter/LinkedIn)             1,231 lines  ← expand
  📄 Ch105 Fraud Detection (Stripe/PayPal)                       119 lines   ← full write needed
  📄 Ch106 E-commerce / Inventory (flash sales, catalog, cart)   100 lines   ← full write needed
  📄 Ch107 CDN Architecture (PoPs, anycast, cache hierarchy)     105 lines   ← full write needed

---

## SECTION 7 — Engineering Craft (Ch108–120)

  ✅ Ch108 Debugging as a Discipline                             3,182 lines
  ✅ Ch109 On-Call Engineering                                   2,504 lines
  🟡 Ch110 Code Review as a Discipline                           1,482 lines  ← expand
  🟡 Ch111 Migrations and Safe Changes                           2,478 lines  ← expand
  📄 Ch112 Technical Writing                                     68 lines    ← full write needed
  ✅ Ch113 Testing as a Discipline                               2,502 lines
  🟡 Ch114 API Design as a Discipline                            2,350 lines  ← expand
  📄 Ch115 Security Mindset                                      59 lines    ← full write needed
  📄 Ch116 Refactoring Large Systems                             58 lines    ← full write needed
  📄 Ch117 Capacity Planning                                     65 lines    ← full write needed
  📄 Ch118 Reading Unfamiliar Code                               90 lines    ← full write needed
  📄 Ch119 Promotion & Career Navigation                         107 lines   ← full write needed
  📄 Ch120 Cost Optimization Discipline                          95 lines    ← full write needed

---

## SECTION 8 — Interview Execution (Ch121–124)

  🟡 Ch121 Interview Execution Meta-Skills                       1,471 lines  ← expand
  📄 Ch122 Behavioral / Leadership Interview                     99 lines    ← full write needed
  📄 Ch123 Offer Negotiation                                     106 lines   ← full write needed
  ❌ Ch124 Google Hiring Process Deep Dive                       0 lines     ← NEW: full write needed
             (HC review, leveling rubric, team matching, recruiter strategy,
              how to use the offer call, L5 vs L6 determination)

---

## PRIORITY ORDER (suggested)

  ### Tier 1 — Highest interview ROI
  1.  Ch98  Spanner                      (Section 6 — most cited at Google) 🟡 2,407
  2.  Ch101 Location & Mapping           (Section 6 — top 5, Uber/Google Maps) 🟡 2,281
  3.  Ch121 Interview Execution          (Section 8 — meta-skill) 🟡 1,471
  4.  Ch72  Video Streaming L5           (Section 5 — very high freq, missing) ❌
  5.  Ch75  Typeahead L5                 (Section 5 — very high freq warmup, missing) ❌

  ### Tier 2 — High value
  6.  Ch99  Borg                         (Section 6 — Kubernetes prerequisite) 🟡 2,125
  7.  Ch102 Typeahead / Autocomplete     (Section 6 — asked constantly) 🟡 2,256
  8.  Ch73  News Feed L5                 (Section 5 — high freq, missing) ❌
  9.  Ch74  Location Service L5          (Section 5 — high freq, missing) ❌
  10. Ch110 Code Review                  (Section 7 — craft) 🟡 1,482
  11. Ch111 Migrations                   (Section 7 — craft) 🟡 2,478
  12. Ch114 API Design                   (Section 7 — craft) 🟡 2,350
  13. Ch48  Consensus Deep Dive          (Section 4 — deep technical) 🟡 2,216

  ### Tier 3 — Nice to have
  14. Ch104 Social Graph                 (Section 6) 🟡 1,231
  15. Ch105 Fraud Detection              (Section 6) 📄 stub
  16. Ch106 E-commerce / Inventory       (Section 6) 📄 stub
  17. Ch107 CDN Architecture             (Section 6) 📄 stub
  18. Ch115 Security Mindset             (Section 7) 📄 stub
  19. Ch116 Refactoring Large Systems    (Section 7) 📄 stub
  20. Ch117 Capacity Planning            (Section 7) 📄 stub
  21. Ch112 Technical Writing            (Section 7) 📄 stub
  22. Ch122 Behavioral Interview         (Section 8) 📄 stub
  23. Ch123 Offer Negotiation            (Section 8) 📄 stub
  24. Ch124 Google Hiring Process        (Section 8) ❌ missing
  25. Ch118 Reading Unfamiliar Code      (Section 7) 📄 stub
  26. Ch119 Promotion & Career Nav       (Section 7) 📄 stub
  27. Ch120 Cost Optimization            (Section 7) 📄 stub

  ### Expansions needed (thin chapters 🟡)
  - Ch10  APIs, Frontend, Backend, DB         2,379 → 2,500+
  - Ch11  OS Fundamentals                     2,325 → 2,500+
  - Ch21  End-to-End 5-Phase Framework        2,483 → 2,500+
  - Ch48  Consensus Deep Dive                 2,216 → 2,500+
  - Ch55  Search System                       2,802 → 3,000+
  - Ch56  Metrics Collection System           2,812 → 3,000+
  - Ch85  Recommendation and Ranking         3,032 → 3,500+
  - Ch93  Bonus Advanced Topics              1,008 → expand or integrate into Ch29
  - Ch98  Spanner                             2,407 → 2,500+
  - Ch99  Borg                                2,125 → 2,500+
  - Ch101 Location & Mapping                  2,281 → 2,500+
  - Ch102 Typeahead / Autocomplete            2,256 → 2,500+
  - Ch104 Social Graph                        1,231 → 2,500+
  - Ch110 Code Review                         1,482 → 2,500+
  - Ch111 Migrations and Safe Changes         2,478 → 2,500+
  - Ch114 API Design                          2,350 → 2,500+
  - Ch121 Interview Execution Meta-Skills     1,471 → 2,500+

---

## TOTALS (as of 2026-06-22)

  Total chapters:              124 (Ch1–Ch124)
  ✅ Done (2,000+ lines):      ~89 chapters
  🟡 Thin (needs expansion):   ~17 chapters
  📄 Stub (needs full write):  ~13 chapters
  ❌ Missing (not yet created): 5 chapters (Ch72–Ch75, Ch124)

  Chapter number ranges by section:
    Section 0 (Ch1–8)     = Staff Engineer Mindset
    Section 1 (Ch9–14)    = Foundations
    Section 2 (Ch15–21)   = Design Framework
    Section 3 (Ch22–29)   = Distributed Systems Core
    Section 4 (Ch30–48)   = Data Systems & Infrastructure
    Section 5 (Ch49–75)   = L5 / Senior SWE case studies
    Section 6 (Ch76–107)  = L6 / Staff case studies
    Section 7 (Ch108–120) = Engineering Craft
    Section 8 (Ch121–124) = Interview Execution

  Recently completed:
    Ch62–Ch71: full chapters written (2,000–3,700 lines each), API design + DB schema added

  Chapters needing top-up (🟡): Ch10, Ch11, Ch21, Ch48, Ch55, Ch56, Ch85, Ch93,
    Ch98, Ch99, Ch101, Ch102, Ch104, Ch110, Ch111, Ch114, Ch121

  Stubs remaining (📄): Ch105, Ch106, Ch107, Ch112, Ch115, Ch116, Ch117,
    Ch118, Ch119, Ch120, Ch122, Ch123

  Missing (❌): Ch72 Video Streaming L5, Ch73 News Feed L5,
               Ch74 Location Service L5, Ch75 Typeahead L5,
               Ch124 Google Hiring Process

  Estimated total lines written: ~390,000+

---

*Last updated: 2026-06-22*
