# Master Plan — SysDesign L6 Guide
# Status dump as of 2026-06-20 (chapters renumbered to clean sequential)

Legend:
  ✅ DONE      — 2,500+ lines, full depth
  🟡 THIN      — exists but under 2,500 lines, needs expansion
  📄 STUB      — outline/plan only (< 200 lines), needs full write
  ❌ MISSING   — not created yet

Gold standard: Ch94 Debugging = 3,182 lines. Target for all chapters: 2,500+.
Total chapters: 109 (Ch1–Ch109)

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
  🟡 Ch10  APIs, Frontend, Backend, DB                           2,258 lines  ← expand
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
  🟡 Ch20  Phase 4 & 5: Non-Functional Requirements              2,434 lines  ← expand
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
  📄 Ch46  Data Warehouse / OLAP                                  ~100 lines  ← full write needed
  📄 Ch47  Kubernetes Internals                                   ~100 lines  ← full write needed
  📄 Ch48  Consensus Deep Dive (Raft & Paxos)                    ~100 lines  ← full write needed

---

## SECTION 5 — Single-Region Case Studies (Ch49–61)

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

---

## SECTION 6 — Staff-Level Case Studies + Google Systems (Ch62–93)

  ### Staff Case Studies (Ch62–79)
  ✅ Ch62  Global Rate Limiter                                    4,119 lines
  ✅ Ch63  Distributed Cache                                      4,329 lines
  ✅ Ch64  News Feed                                              5,085 lines
  ✅ Ch65  Real-Time Collaboration                                4,636 lines
  ✅ Ch66  Messaging Platform                                     5,295 lines
  ✅ Ch67  Metrics and Observability System                       5,147 lines
  ✅ Ch68  Configuration, Feature Flags, Secrets                  5,414 lines
  ✅ Ch69  API Gateway and Edge Request Routing                   5,397 lines
  ✅ Ch70  Search and Indexing System                             4,485 lines
  🟡 Ch71  Recommendation and Ranking System                     3,032 lines  ← expand
  ✅ Ch72  Notification Delivery: Fan-out at Scale               4,792 lines
  ✅ Ch73  Authentication and Authorization System                4,197 lines
  ✅ Ch74  Distributed Scheduler and Job Orchestration            4,267 lines
  ✅ Ch75  Feature Experimentation and A/B Testing                4,364 lines
  ✅ Ch76  Log Aggregation and Query System                       3,606 lines
  ✅ Ch77  Payment and Transaction Processing                     3,742 lines
  ✅ Ch78  Media Upload and Processing Pipeline                   4,224 lines
  🟡 Ch79  Bonus Advanced Topics                                 1,008 lines  ← expand or integrate

  ### Google Foundational Systems (Ch80–85)
  ✅ Ch80  GFS — Google File System                              2,501 lines
  ✅ Ch81  Bigtable                                              2,501 lines
  ✅ Ch82  MapReduce                                             2,502 lines
  📄 Ch83  Chubby — Distributed Lock Service                     ~110 lines  ← full write needed
  📄 Ch84  Spanner — Globally Distributed Database               ~130 lines  ← full write needed
  📄 Ch85  Borg — Cluster Manager                                ~155 lines  ← full write needed

  ### Gap Case Studies (Ch86–93)
  📄 Ch86  Video Streaming (YouTube/Netflix/TikTok)              ~120 lines  ← full write needed
  📄 Ch87  Location & Mapping (Uber/Google Maps)                 ~120 lines  ← full write needed
  📄 Ch88  Typeahead / Autocomplete                              ~90 lines   ← full write needed
  📄 Ch89  Ad Serving & Real-Time Bidding                        ~133 lines  ← full write needed
  📄 Ch90  Social Graph (Instagram/Twitter/LinkedIn)             ~108 lines  ← full write needed
  📄 Ch91  Fraud Detection (Stripe/PayPal)                       ~119 lines  ← full write needed
  📄 Ch92  E-commerce / Inventory (flash sales, catalog, cart)   ~110 lines  ← full write needed
  📄 Ch93  CDN Architecture (PoPs, anycast, cache hierarchy)     ~100 lines  ← full write needed

---

## SECTION 7 — Engineering Craft (Ch94–106)

  ✅ Ch94  Debugging as a Discipline                             3,182 lines
  📄 Ch95  On-Call Engineering                                   68 lines    ← full write needed
  📄 Ch96  Code Review as a Discipline                           66 lines    ← full write needed
  📄 Ch97  Migrations and Safe Changes                           71 lines    ← full write needed
  📄 Ch98  Technical Writing                                     68 lines    ← full write needed
  📄 Ch99  Testing as a Discipline                               71 lines    ← full write needed
  📄 Ch100 API Design as a Discipline                            74 lines    ← full write needed
  📄 Ch101 Security Mindset                                      59 lines    ← full write needed
  📄 Ch102 Refactoring Large Systems                             58 lines    ← full write needed
  📄 Ch103 Capacity Planning                                     65 lines    ← full write needed
  📄 Ch104 Reading Unfamiliar Code                               ~90 lines   ← full write needed
  📄 Ch105 Promotion & Career Navigation                         ~100 lines  ← full write needed
  📄 Ch106 Cost Optimization Discipline                          ~90 lines   ← full write needed

---

## SECTION 8 — Interview Execution (Ch107–109)

  📄 Ch107 Interview Execution Meta-Skills                       ~100 lines  ← full write needed
  📄 Ch108 Behavioral / Leadership Interview                     ~100 lines  ← full write needed
  📄 Ch109 Offer Negotiation                                     ~100 lines  ← full write needed

---

## PRIORITY ORDER (suggested)

  ### Tier 1 — Highest interview ROI
  1.  Ch95  On-Call Engineering          (Section 7 — every L6 role)
  2.  Ch83  Chubby                       (Section 6 — pairs with GFS/Bigtable/MapReduce)
  3.  Ch84  Spanner                      (Section 6 — most cited in Google interviews)
  4.  Ch86  Video Streaming              (Section 6 — top 5 interview question)
  5.  Ch87  Location & Mapping           (Section 6 — top 5, Uber/Google Maps)
  6.  Ch46  Data Warehouse / OLAP        (Section 4 — growing fast in L6 interviews)
  7.  Ch107 Interview Execution          (Section 8 — meta-skill that multiplies everything)

  ### Tier 2 — High value
  8.  Ch85  Borg                         (Section 6 — Kubernetes prerequisite)
  9.  Ch88  Typeahead / Autocomplete     (Section 6 — asked constantly)
  10. Ch96  Code Review                  (Section 7 — craft)
  11. Ch97  Migrations                   (Section 7 — craft)
  12. Ch99  Testing                      (Section 7 — craft)
  13. Ch100 API Design                   (Section 7 — craft)
  14. Ch47  Kubernetes Internals         (Section 4 — platform/infra interviews)
  15. Ch48  Consensus Deep Dive          (Section 4 — deep technical)

  ### Tier 3 — Nice to have
  16. Ch89  Ad Serving / RTB             (Section 6 — Google/Meta specific)
  17. Ch90  Social Graph                 (Section 6 — Meta/LinkedIn)
  18. Ch91  Fraud Detection              (Section 6 — fintech)
  19. Ch92  E-commerce / Inventory       (Section 6 — Amazon interviews)
  20. Ch93  CDN Architecture             (Section 6 — rare but deep)
  21. Ch101 Security Mindset             (Section 7)
  22. Ch102 Refactoring Large Systems    (Section 7)
  23. Ch103 Capacity Planning            (Section 7)
  24. Ch98  Technical Writing            (Section 7)
  25. Ch108 Behavioral Interview         (Section 8)
  26. Ch109 Offer Negotiation            (Section 8)
  27. Ch104 Reading Unfamiliar Code      (Section 7)
  28. Ch105 Promotion & Career Nav       (Section 7)
  29. Ch106 Cost Optimization Discipline (Section 7)

  ### Expansions needed (thin chapters)
  - ~~Ch8   Interview Execution Strategy~~     ✅ DONE (2,501 lines)
  - Ch10  APIs, Frontend, Backend, DB         2,258 → 2,500+
  - Ch11  OS Fundamentals                     2,325 → 2,500+
  - Ch20  Non-Functional Requirements         2,434 → 2,500+
  - Ch21  End-to-End 5-Phase Framework        2,483 → 2,500+
  - Ch55  Search System                       2,802 → expand
  - Ch56  Metrics Collection System           2,812 → expand
  - Ch71  Recommendation and Ranking         3,032 → expand
  - Ch79  Bonus Advanced Topics              1,008 → expand or integrate

---

## TOTALS

  Total chapters:              109 (Ch1–Ch109, fully sequential, no gaps)
  ✅ Done (2,500+ lines):      ~70 chapters
  🟡 Thin (needs expansion):   ~9 chapters
  📄 Stub (needs full write):  ~30 chapters

  Total lines written:         ~353,580
  Estimated remaining:         ~67,000 lines to reach full depth on all stubs

---

*Last updated: 2026-06-20*
