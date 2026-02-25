# Distributed Cache: Redis Cluster Basics

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

One shopkeeper handles all customers. A hundred? Fine. Ten thousand? He collapses. Solution: open six shops across the city. Each shop handles customers from their neighborhood. A directory tells you which shop to go to. Data is split across shops—sharding. If one shop burns down, its backup shop takes over—replication. That's Redis Cluster. Let's see how it works.

---

## The Story

Imagine one shopkeeper in a city. He sells everything. A hundred customers per day? He manages. A thousand? He's tired. Ten thousand? Impossible. He collapses.

The solution: don't have one shop. Have six. Spread across the city. Each shop handles customers from its neighborhood. A directory at the entrance: "Looking for X? Go to Shop 3." You go to Shop 3. Get your data. Done.

That's sharding. Data split across nodes by some rule. Each node holds a slice.

Now: Shop 3 catches fire. What about its customers? Each shop has a backup. A replica. When Shop 3 burns, Backup 3 opens next door. Same data. Customers don't lose anything. That's replication. Redis Cluster gives you both.

---

## Another Way to See It

A library. One building. Millions of books. Too many. So the city opens branch libraries. Downtown. North. South. East. West. Each branch holds a portion of the collection. A central catalog tells you: "This book is at the North branch." You go there. If the North branch closes for renovation, a backup location has a copy. You still get your book. Sharding plus replication.

---

## Connecting to Software

**Redis Cluster** = multiple Redis nodes working together.

**Sharding:** Data is split across nodes using hash slots. When you add a key, Redis hashes the key name, maps it to a slot (0 to 16383), and sends it to the node that owns that slot. No manual routing. The cluster handles it. As you add nodes, you can reshard—move slots between nodes to rebalance. But usually you size the cluster right from the start. Redis Cluster has 16,384 slots. Each key is hashed to a slot. Each node owns a range of slots. Key `user:123` → hash → slot 5234 → Node B owns slots 0–5460. Request goes to Node B.

**Replication:** Each master node has one or more replicas. Master holds the data. Replica mirrors it. Master dies? Replica is promoted. Cluster is self-healing. Automatic failover.

**Limits:**
- Multi-key operations (e.g., MGET across keys) must target the same node. Keys on different nodes can't be queried together in one command. Use hash tags: `user:{123}:profile` and `user:{123}:settings`. The part in curly braces is used for hashing. Both keys hash to the same slot. Same node. Multi-key ops work.
- No cross-node transactions. One node, one transaction.
- Client must know the cluster topology. Requests are routed to the right node.

---

## Let's Walk Through the Diagram

```
Redis Cluster: 3 Masters + 3 Replicas

  Master 1 (slots 0-5460)     Master 2 (slots 5461-10922)   Master 3 (slots 10923-16383)
        │                              │                              │
        │ replicate                    │ replicate                    │ replicate
        ▼                              ▼                              ▼
  Replica 1                      Replica 2                      Replica 3

  Client request: GET user:123
       │
       ▼  Hash("user:123") → slot 5234
       │
       ▼  Slot 5234 ∈ Master 1's range
       │
  Request sent to Master 1 → Response
```

---

## Real-World Examples

**1. Twitter**  
Redis Cluster for timelines, sessions, counters. Millions of users. Billions of keys. Sharded across hundreds of nodes. Replication for durability. When a node fails, traffic shifts to replicas. Users never notice.

**2. GitHub**  
Redis Cluster for Rails cache, session storage, job queues. Large scale. Multiple data centers. Cluster spans regions. Replication handles failures.

**3. E-commerce product catalog**  
Products sharded by ID. Popular products spread across nodes. No single node holds all hot keys. Replicas for read scaling and failover. When Black Friday hits, traffic spikes. Cluster spreads the load. If one node fails mid-sale, replicas take over. Customers don't notice. That's the power of distributed cache at scale.

---

## Let's Think Together

You have 3 Redis masters. One crashes. What happens to its data? How long until recovery?

Think. Pause.

The crashed master's replica detects the failure. Cluster nodes agree: promote the replica to master. Typically 10–30 seconds. Data? Already on the replica. No data loss (if replication was caught up). Clients reconnect to the new topology. Requests resume. The failed node can be replaced. Add a new replica. Rebalance if needed. Recovery is automatic. You don't lose data. You might have a brief window of higher latency.

---

## What Could Go Wrong? (Mini Disaster Story)

A company ran Redis Cluster. One master and its replica in the same rack. Rack power failure. Both down. Slot range 5461–10922—unavailable. All keys in that range? Unreachable. Application errors. "Cache unreachable." Users saw failures. The fix: place master and replica in different failure domains. Different racks. Different availability zones. Never colocate them. Redis Cluster can't help if both die together.

---

## Surprising Truth / Fun Fact

Redis can handle 1 million+ operations per second in cluster mode. Companies like Twitter and GitHub use Redis Cluster to serve millions of users. A single Redis instance might do 80K–100K ops/sec. A cluster of 10 nodes? Ten times that. And it keeps going. That's why distributed cache matters at scale.

---

## Quick Recap (5 bullets)

- Redis Cluster = multiple Redis nodes; data sharded by hash slots (16,384 slots).
- Each master has replicas; master dies, replica promotes. Self-healing.
- Multi-key ops need same node—use hash tags: `user:{123}:x`.
- Place master and replica in different failure domains (different racks/AZs).
- Client must support cluster protocol for routing. Most Redis clients (redis-py, Jedis, ioredis) support Cluster mode out of the box. They fetch the cluster topology on connect, then route each request to the correct node. You don't have to implement hashing yourself. The client does it. When a node fails and a replica promotes, the client gets the new topology. Reconnects. Keeps going. Redis Cluster is designed for high availability and horizontal scale. Understand it before you need it. Many teams start with a single Redis instance—fine for small scale. But when you grow, Cluster is the path. Sharding and replication are built in. You're not reinventing the wheel. Configure, connect, and scale.

---

## One-Liner to Remember

*Redis Cluster = sharding for scale, replication for durability—data spread across nodes, backups ready when a node fails.*

---

## Next Video

Next: CDN deep dive. How content gets to users from the nearest edge. Topic 95: CDN—How It Works and When to Use It.
