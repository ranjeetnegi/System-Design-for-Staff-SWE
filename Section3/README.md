# Section 3 — Distributed Systems Core

The theory behind every large-scale system. You cannot design distributed systems well without understanding why consistency is hard, how replication works, what happens during network partitions, and how consensus algorithms reach agreement.

Read *Designing Data-Intensive Applications* (Kleppmann) alongside this section — chapters 5–9 of DDIA map directly to Ch22–29 here.

---

## Chapters

| Chapter | Title | Key Topic |
|---|---|---|
| [Ch22](Chapter_22_Consistency_Models.md) | Consistency Models | Linearizability, sequential, eventual — what they mean in practice |
| [Ch23](Chapter_23_Replication_and_Sharding.md) | Replication and Sharding | Leader/follower, multi-leader, leaderless; hash vs range sharding |
| [Ch24](Chapter_24_Leader_Election_Coordination_Distributed_Locks.md) | Leader Election, Coordination, Distributed Locks | Zookeeper, etcd, fencing tokens, why locks are hard |
| [Ch25](Chapter_25_Backpressure_Retries_and_Idempotency.md) | Backpressure, Retries, and Idempotency | Preventing cascading failures, safe retry patterns |
| [Ch26](Chapter_26_Queues_Logs_and_Streams.md) | Queues, Logs, and Streams | Kafka internals, exactly-once delivery, stream processing |
| [Ch27](Chapter_27_Failure_Models_and_Partial_Failures.md) | Failure Models and Partial Failures | Byzantine vs crash failures, partial failure isolation |
| [Ch28](Chapter_28_CAP_Theorem_Applied_Case_Studies.md) | CAP Theorem: Applied Case Studies | Why CAP is misunderstood; PACELC as a better model |
| [Ch29](Chapter_29_Advanced_Distributed_Systems.md) | Advanced Distributed Systems | Hybrid logical clocks, CRDTs, vector clocks, gossip protocols |

---

## Core Themes

- **Consistency is a spectrum** — there is no "consistent or not"; there are dozens of models with different guarantees and costs
- **Replication solves availability; sharding solves scale** — don't confuse the two
- **Distributed locks are dangerous** — clock skew, GC pauses, and network delays can all break them; use fencing tokens
- **Idempotency is non-negotiable** — retries are inevitable; your system must handle them safely
- **CAP is a simplification** — PACELC (latency vs consistency during normal operation) is more useful in practice
