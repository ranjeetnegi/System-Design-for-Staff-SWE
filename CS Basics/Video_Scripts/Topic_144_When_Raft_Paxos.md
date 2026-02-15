# When to Use Raft/Paxos (etcd, ZooKeeper)

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

"What's for dinner?" Dad decides. Pasta. Done. Fast. No family vote. But "Should we sell the house?" Everyone gathers. Discussion. Vote. Majority rules. You don't use consensus for everything. Small decisions? One person. Quick. Big decisions? Everyone agrees. Distributed systems work the same way. You don't run Paxos for every database write. Too slow. Too heavy. But for the critical stuff—who's the leader? Is this config approved?—you need consensus. Let me show you when, where, and why.

---

## The Story

Picture a big family. Fifteen people live in the house. Most decisions are small. "What's for breakfast?" Mom decides. "Who takes out the trash?" Dad points. Fast. No meetings. No voting. Life moves on.

But sometimes a BIG decision comes up. "Should we renovate the house? Should grandma move in? Should we sell the car?" Now everyone gathers. Living room. Discussion. Arguments. Voting. Majority rules. These decisions take TIME — sometimes hours. But they MUST be correct. Getting them wrong = disaster.

**Consensus is for critical coordination.** Not for every operation. Use it when: the system must agree on ONE value. Leader election. Config change. Distributed lock. Transaction commit. Metadata. Things that affect the whole cluster. One wrong decision = chaos. Split-brain. Data corruption. For those, you pay the cost. Latency. Complexity. Worth it.

**Don't use consensus for:** Every read. Every write. Application data. Non-critical decisions. High-throughput data path. Why? Consensus is slow. Multiple round-trips. Majority agreement. Adds 5-50 milliseconds. For a database serving millions of reads per second, consensus per read would kill performance. You'd go from microsecond reads to millisecond reads. Throughput drops 100x. Unacceptable.

Use replication for data. Use caching for speed. Use eventual consistency for availability. Reserve consensus for the control plane — the decisions that orchestrate everything else. Think of it this way: the family votes on the house renovation plan. But they don't vote on every nail, every paint color, every light switch. Those details are delegated.

---

## Another Way to See It

Think of a company. Day-to-day tasks? Managers decide. Fast. No board meeting for every email. But hiring a CEO? Board vote. Consensus. Same company. Different decision levels. Consensus is the board meeting. Expensive. Formal. For the big calls. Day-to-day is optimized for speed. Consensus is optimized for correctness on the critical path. Match the tool to the problem.

---

## Connecting to Software

**etcd:** Distributed key-value store. Uses Raft. Stores cluster state. Configuration. Locks. Kubernetes uses it. Every kubectl command touches etcd. Leader election for control plane. Config for pods, services, secrets. Consensus where it matters. Application data? Put it in a database. Not etcd.

**ZooKeeper:** Coordination service. Uses ZAB (Paxos-like). Manages config. Naming. Leader election. Locks. Kafka uses it for broker coordination. HBase for region assignment. Hadoop for coordination. The "source of truth" for who's who and what's what. Small data. Big impact.

**Consul:** Service discovery. Config. Health checks. Raft under the hood. Service registry needs consistency. "Is this service up?" All nodes should agree. Consensus fits.

Here's the key insight: these tools store SMALL amounts of data — kilobytes to megabytes. Configuration. Metadata. Leader identity. They're NOT designed for terabytes of user data. etcd recommends a max database size of 8GB. Compare that to your application database at 500GB+. Different tools for different layers. Consensus is the brain. Databases are the muscles.

---

## Let's Walk Through the Diagram

```
    WHEN TO USE CONSENSUS

    USE CONSENSUS:
    ┌─────────────────────────────────────────┐
    │ Leader election     │ Who's in charge?    │
    │ Config management   │ What's the config?  │
    │ Distributed locks   │ Who has the lock?  │
    │ Metadata coordination │ Cluster topology │
    │ Transaction commit  │ All commit or abort│
    └─────────────────────────────────────────┘

    DON'T USE CONSENSUS:
    ┌─────────────────────────────────────────┐
    │ Every read/write    │ Too slow. Use DB.  │
    │ Application data    │ Use replication.    │
    │ Cache updates       │ Eventually consistent│
    └─────────────────────────────────────────┘

    etcd/ZooKeeper = consensus for COORDINATION
    PostgreSQL/MongoDB = data storage (different layer)
```

The diagram shows: consensus is a layer. Coordination layer. Not the data layer. Use the right tool.

---

## Real-World Examples (2-3)

**Example 1: Kubernetes.** Uses etcd for API server state. Pod specs. Deployments. ConfigMaps. Consensus. But container images? Stored in registries. Application data? In databases. Kubernetes orchestrates. Doesn't store your data. Clear separation.

**Example 2: Kafka.** Uses ZooKeeper (or KRaft) for broker metadata. Partition leaders. Consumer group coordination. Consensus for structure. Message data flows through brokers. No consensus per message. Throughput stays high.

**Example 3: Cassandra.** No consensus for writes. Each node accepts. Eventual consistency. But for cluster membership—who's in the ring?—gossip spreads the info. Different from Raft. Cassandra optimizes for write throughput. Consensus would slow it. Trade-off. Know your priorities.

---

## Let's Think Together

Should you use Raft consensus for every database write in your system? Why or why not?

No. Consensus adds latency. Multiple round-trips. Majority agreement. For high-throughput writes, that's a bottleneck. A single-leader database replicates asynchronously. Fast. Consensus is for: electing that leader. Deciding config. Coordinating. The write path itself uses replication. Leader writes. Followers copy. Consensus decides who the leader is. Not every byte written. Use consensus for control. Use replication for data. Different layers. Different tools.

---

## What Could Go Wrong? (Mini Disaster Story)

A team stored user session data in etcd. "It's consistent." True. But etcd is not designed for high write volume. Thousands of sessions per second. etcd slowed. API calls timed out. Kubernetes itself suffered—etcd was overloaded. They moved session data to Redis. etcd back to cluster state only. Lesson: etcd and ZooKeeper are for coordination. Small data. Critical data. Not your application's high-volume data. Use the right store. Consensus has a purpose. Don't overload it.

---

## Surprising Truth / Fun Fact

Google's Chubby—the inspiration for ZooKeeper—provides a distributed lock service. Nearly every Google service uses it internally. Bigtable. GFS. Spanner. Chubby is the coordination backbone. Locks. Leader election. Config. One service. Critical. Consensus at the core. When Google needed coordination, they built Chubby. When the rest of the world needed it, they built ZooKeeper. Same idea. Open source. The pattern scales from startups to planet-scale.

---

## Quick Recap (5 bullets)

- **Use consensus for:** Leader election, locks, config, metadata, transaction commit.
- **Don't use for:** Every read/write, application data, high-throughput path.
- **etcd:** Raft. Kubernetes. Cluster state. Coordination.
- **ZooKeeper:** ZAB. Kafka, HBase. Config. Naming. Coordination.
- **Consensus = coordination layer.** Not data layer. Match tool to problem.

---

## One-Liner to Remember

**Consensus: Family votes on selling the house, not on dinner. Use Raft/Paxos for big decisions. Use fast replication for the rest.**

---

## Next Video

Next: **Leader Election: Why and How.** A ship in a storm. Captain down. Someone must take charge. The crew votes. First officer wins. Leader election—choosing one node when the current one fails. Methods: bully, Raft, lease-based. When chaos strikes. See you there.
