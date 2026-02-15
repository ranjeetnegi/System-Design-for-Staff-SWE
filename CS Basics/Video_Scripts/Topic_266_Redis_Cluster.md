# Redis Cluster: Slots and Routing

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A post office with 16,384 PO boxes spread across six buildings. Each building manages a RANGE of boxes. Building A: boxes 0 to 2730. Building B: boxes 2731 to 5461. And so on. When you want box number 4000, you go directly to Building B. You don't wander. You don't ask the front desk. You know the map. Redis Cluster works the same way. Data is split into 16,384 hash slots across multiple nodes. Each node owns a range of slots. Your key hashes to a slot. The slot tells you which node. Let's walk through how it works.

---

## The Story

One Redis node is powerful. But it has limits. Memory. Single point of failure. You need to scale out. Redis Cluster is the answer. It's not "many Redis nodes with a proxy." It's a distributed system. Data is partitioned. No single node holds everything. Clients talk to the right node directly. Failover is automatic. Understanding slots and routing is the key to understanding Redis Cluster.

Think of it like a city's postal system. One post office can't handle all mail. So you have many. Each serves a range of ZIP codes. Your letter goes to the right office based on the destination ZIP. Redis Cluster does that with keys. Hash the key. Get a slot number. Slot maps to a node. Direct routing.

---

## Another Way to See It

Imagine a library with 16,384 shelves. Six librarians. Each librarian knows exactly which shelves they manage. You want a book—the catalog gives you a shelf number. You go to the right librarian. No central coordinator. Each librarian is autonomous. That's Redis Cluster. Decentralized. Slot-based. Every node knows the topology.

---

## Connecting to Software

**Hash slots:** Redis uses CRC16 on the key (or the hash tag part) and mod 16384. Result: a number from 0 to 16383. That number is the slot. The slot maps to a node. Example: key `user:123` → CRC16 → mod 16384 → slot 4821 → Node B. Consistent. Deterministic.

**Client routing:** You send a command to any node. If the key is on that node—done. If not, the node replies with `MOVED 4821 192.168.1.42:6379`. "That key is on node 192.168.1.42." The client updates its routing table. Next time, it sends directly to the right node. Smart clients (Jedis, Lettuce, redis-py-cluster) cache this. They learn the cluster topology. After a few requests, most traffic goes directly to the correct node.

**Adding nodes:** You add a fourth master. Slots must be rebalanced. The new node takes some slots from existing nodes. Data migrates. Keys in slot 4000 move from Node A to Node D. Transparent to clients—they get MOVED responses, update routing, retry. The migration happens in the background. No downtime.

**Replication:** Each master has one or more replicas. Master fails? A replica is promoted. Automatic failover. Clients get a redirect to the new master. The cluster keeps running.

---

## Let's Walk Through the Diagram

```
Redis Cluster - 3 Masters, 16,384 slots

     Master A              Master B              Master C
   Slots 0-5460         Slots 5461-10922      Slots 10923-16383
        |                     |                     |
        |  Replica A1         |  Replica B1         |  Replica C1
        |                     |                     |

Client: SET user:123 "John"
        |
        | hash("user:123") % 16384 = 4821
        | 4821 is in Master A's range
        |
        v
    Master A  -->  OK

Client sends to wrong node (Master B):
        |
        v
    Master B  -->  MOVED 4821 192.168.1.10:6379
        |
        | Client caches: slot 4821 → Master A
        | Retries to Master A
        v
    Master A  -->  OK
```

The client learns. First request might hit the wrong node. MOVED response. Client remembers. Second request—direct to the right node. No wasted round-trips.

---

## Real-World Examples (2-3)

**Twitter** runs Redis Cluster at massive scale. Hundreds of nodes. Billions of keys. Timeline data, session data, cached API responses. Slot-based partitioning makes it work. Add nodes as traffic grows. Rebalance. Transparent.

**Gaming leaderboards** use Redis Cluster. Millions of players. Real-time rankings. Data partitioned by player ID hash. Each node handles a slice. Horizontal scale.

**E-commerce product catalog cache**—products sharded by product ID. Hash to slot. Distributed across nodes. No single node is a bottleneck.

---

## Let's Think Together

**"Redis Cluster with 3 masters. You add a 4th. How do slots redistribute? How does data move?"**

Slots rebalance. 16,384 / 4 = 4096 slots per node. The new node needs 4096 slots. Existing nodes each give up roughly 1365 slots (one-third of their 5461). So Master A goes from 0-5460 to maybe 0-4095. Master B, C similarly shrink. The new Master D gets 4096 slots from each. Data migration: Redis uses MIGRATE command. Keys in moving slots get serialized, sent to the new node, deleted from the old. Happens key-by-key or in batches. Clients get ASK redirects during migration (temporary) and MOVED after (permanent). Plan migrations during low traffic. It's CPU and network intensive.

---

## What Could Go Wrong? (Mini Disaster Story)

A team adds a node to their Redis Cluster during peak hours. Rebalancing starts. Thousands of keys migrate per second. Network saturates. Latency spikes from 2ms to 500ms. Applications time out. Customers see errors. The team didn't realize migration would be so heavy. They abort the migration. Cluster is in a weird state. They roll back. Lesson: rebalance during off-peak. Limit migration speed. Use `redis-cli --cluster rebalance` with careful settings. Test in staging first. Migrations are not free.

---

## Surprising Truth / Fun Fact

Why 16,384 slots? It's 2^14. A nice power of two. Enough for fine-grained distribution (can have 16,384 nodes in theory—more than anyone needs). Small enough that the slot-to-node mapping is compact. The number has been unchanged since Redis Cluster was introduced. It works.

---

## Quick Recap (5 bullets)

- **16,384 slots** = every key hashes to a slot; slot maps to a node.
- **Client routing** = MOVED response tells client the right node; smart clients cache and send directly.
- **Adding nodes** = rebalance slots; migrate data; clients get redirects; transparent after routing update.
- **Replication** = each master has replicas; failover is automatic.
- **Hash tags** = `{user}::123` and `{user}::456` go to same slot (same node) for multi-key ops.

---

## One-Liner to Remember

*Redis Cluster is a post office with 16,384 PO boxes—every key knows its slot, every slot knows its node, and clients learn the map.*

---

## Next Video

Next: Blue-green vs canary deployment. Two stages or gradual rollout? When to switch everyone at once, and when to send 5% first. See you there.
