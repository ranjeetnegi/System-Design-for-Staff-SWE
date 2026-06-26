# Section 4 — Data Systems & Infrastructure

The practical infrastructure layer — databases, caches, event streams, batch pipelines, multi-region deployments, and platform internals. This is the largest section because most real system design interviews live here.

---

## Chapters

| Chapter | Title | Key Topic |
|---|---|---|
| [Ch30](Chapter_30_Databases_Choosing_Using_and_Evolving.md) | Databases: Choosing, Using, and Evolving | SQL vs NoSQL, when to use what, schema evolution |
| [Ch31](Chapter_31_Database_Internals_Deep_Dive.md) | Database Internals Deep Dive | B-trees, LSM trees, WAL, MVCC, vacuum |
| [Ch32](Chapter_32_Data_Encoding_and_Schema_Evolution.md) | Data Encoding & Schema Evolution | Avro, Protobuf, Thrift, backward/forward compatibility |
| [Ch33](Chapter_33_Caching_at_Scale.md) | Caching at Scale: Redis, CDN, Edge | Cache patterns, eviction, consistency, CDN strategies |
| [Ch34](Chapter_34_Redis_and_Cache_Internals.md) | Redis & Cache Internals | Redis data structures, persistence, cluster, Lua scripts |
| [Ch35](Chapter_35_Event_Driven_Architectures.md) | Event-Driven Architectures: Kafka, Streams | Kafka architecture, consumer groups, stream processing |
| [Ch36](Chapter_36_Kafka_Internals.md) | Kafka Internals | Log segments, ISR, controller, exactly-once semantics |
| [Ch37](Chapter_37_Batch_Processing_and_Data_Pipelines.md) | Batch Processing and Data Pipelines | MapReduce, Spark, ETL, data warehouse loading |
| [Ch38](Chapter_38_Multi_Region_Systems.md) | Multi-Region Systems | Active-active vs active-passive, cross-region replication |
| [Ch39](Chapter_39_Data_Locality_Compliance_System_Evolution.md) | Data Locality, Compliance, System Evolution | GDPR, data residency, regulatory constraints |
| [Ch40](Chapter_40_Cost_Efficiency_and_Sustainable_System_Design.md) | Cost Efficiency and Sustainable System Design | Cloud cost optimization, tiered storage, rightsizing |
| [Ch41](Chapter_41_System_Evolution_Migration_Risk_Management.md) | System Evolution, Migration, Risk Management | Strangler fig, dual-write, zero-downtime migration |
| [Ch42](Chapter_42_Deployment_Strategies_and_Operations.md) | Deployment Strategies and Operations | Blue/green, canary, feature flags, rollback |
| [Ch43](Chapter_43_Service_Mesh.md) | Service Mesh: When, Why, Trade-offs | Istio/Envoy, mTLS, observability, when not to use a mesh |
| [Ch44](Chapter_44_ML_System_Design.md) | ML System Design | Feature stores, training pipelines, model serving, drift |
| [Ch45](Chapter_45_Googles_Foundational_Systems.md) | Google's Foundational Systems (overview) | GFS, Bigtable, MapReduce, Spanner, Borg — quick overview |
| [Ch46](Chapter_46_Data_Warehouse_OLAP.md) | Data Warehouse / OLAP | BigQuery, columnar storage, OLAP vs OLTP |
| [Ch47](Chapter_47_Kubernetes_Internals.md) | Kubernetes Internals | etcd, scheduler, kubelet, reconciliation loop |
| [Ch48](Chapter_48_Consensus_Deep_Dive.md) | Consensus Deep Dive (Raft & Paxos) | Raft leader election, log replication; Paxos comparison |

---

## Core Themes

- **Database choice is a trade-off, not a preference** — use access patterns, consistency needs, scale, and operational cost to decide
- **Caching has failure modes** — cache stampede, thundering herd, inconsistency windows; know them before you recommend caching
- **Kafka is a log, not a queue** — retention, compaction, and consumer group semantics are what make it powerful
- **Multi-region is a consistency trade-off** — latency wins, consistency loses; be explicit about this in designs
- **Migration is the hardest part** — most interview answers skip "how do we get there"; Ch41 covers this gap and differentiates Staff answers

---

## Priority Reading Order

If time is limited, read in this order:
1. Ch30 — database choice comes up in every interview
2. Ch33 — caching comes up in every interview
3. Ch38 — multi-region is expected in Staff interviews
4. Ch35 — Kafka appears in all event-driven designs
5. Ch41 — migrations differentiate L5 from L6 answers
