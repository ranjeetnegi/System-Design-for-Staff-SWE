# Distributed Cache: What and When

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

One refrigerator in a restaurant kitchen. Fine for a small restaurant. But a hotel with 20 kitchens? One fridge cannot serve all. You need multiple fridges, each storing different items, connected by a system that knows which fridge has what. That is a distributed cache—multiple cache nodes working together as one logical cache. Let us design this system together. We will cover when you need it, how it works, and the key trade-offs.

---

## The Story

A single Redis instance is powerful. In-memory, sub-millisecond latency, simple. But it has limits. Memory: 50GB, maybe 100GB per node. Throughput: tens of thousands of ops per second. What when you need 500GB? Or a million ops per second? You scale out. Add more nodes. Distribute the data. Now you have a distributed cache.

Think of it like a chain of libraries. One library holds fiction. Another holds history. Another holds science. You want a book—you go to the right library. The catalog tells you where. A distributed cache does the same: each node holds a slice of the keyspace. The client or a proxy routes your request to the right node.

---

## Another Way to See It

Imagine a postal system. One post office cannot handle all mail for a country. So you have thousands of post offices. Each serves a region. Your letter goes to the post office for your ZIP code. The system knows the mapping: ZIP 10001 to Office 42. A distributed cache partitions keys the same way. Key hash to node. Simple in concept. Tricky in practice.

---

## Connecting to Software

**When do you need it?** Three triggers. (1) Memory: single node cannot hold all data. Your working set exceeds 50 to 100GB. (2) Throughput: single node cannot handle request volume. You need hundreds of thousands of ops per second. (3) Fault tolerance: one node dies, others continue. No single point of failure.

**How does it work?** Partition data across nodes using consistent hashing. Each key hashes to a point on a ring. The key goes to the next node clockwise. Add or remove a node—only a fraction of keys move. Minimal disruption.

**Distributed vs local cache.** Distributed equals shared across servers (Redis Cluster). All app servers see the same data. Local equals per-server (in-memory HashMap). Each server has its own copy. Use distributed when you need shared state. Use local when you need maximum speed and can tolerate staleness or duplication.
**Routing options.** Client-side routing: the application library (Jedis for Java, Lettuce, redis-py-cluster) knows the hash ring. It hashes the key, determines the node, and connects directly. No proxy. Low latency. Proxy-based: Twemproxy or Envoy sits in front. Client talks to proxy. Proxy routes to the right node. Simpler clients. Single connection. Trade-off: proxy adds a hop. For high throughput, client-side often wins. For simplicity, proxy works.

**When to use local cache instead.** If your data is read-heavy and can be slightly stale, a local cache (per application server) avoids network calls entirely. Each server caches a copy. Invalidate on write. Use when: data changes infrequently, or you have a pub/sub invalidation path. Distributed cache: when you need consistency across servers, or the working set is too large for each server to hold.


---

## Let's Walk Through the Diagram

```
         App Server
              |
              | key="user:123"
              v
         Client Library
         (knows hash ring)
              |
              | hash(key) -> Node 2
              v
    Node 0      Node 1      Node 2
    Keys A-M    Keys N-S    user:123
         |          |          |
         +----------+----------+
         Consistent Hash Ring
```

The client hashes the key, finds the node on the ring, sends the request directly. No central coordinator. Each node owns a slice of the key space. When you add Node 4, only the keys that now hash closer to Node 4 move. Perhaps 25 percent of keys. The rest stay put. That is the power of consistent hashing: minimal data movement on topology change. Add or remove nodes without reshuffling everything.

---

## Real-World Examples

**Redis Cluster** is the canonical distributed cache. 16,384 hash slots. Keys map to slots. Slots map to nodes. Add a node—rebalance slots. **Memcached** with consistent hashing: clients partition keys across pool of nodes. **Hazelcast** offers a distributed cache with replication and partitioning. Each scales by adding nodes. **Amazon ElastiCache** for Redis supports cluster mode: automatic sharding, replication, failover. **Twemproxy** (Twitter) was an early proxy for Memcached and Redis, routing traffic across a pool. The pattern is everywhere: when one node is not enough, partition by hash and scale horizontally.

---

## Let's Think Together

**"Your cache needs 100GB. One Redis node supports 50GB max. How many nodes? How do you split data?"**

Two nodes minimum for 100GB. But plan for growth and fault tolerance. Use 4 to 6 nodes. Split by hash: each key maps to one node. Consistent hashing means adding a node only moves about 1/N of keys. No full reshard. Use virtual nodes (vnodes) for smoother distribution so one node does not get a hot slice.

---

## What Could Go Wrong? (Mini Disaster Story)

You deploy a 3-node Redis cluster. All good. One node gets 80 percent of traffic—hot keys. That node overheats. Latency spikes. You discover: a few keys (e.g., global:config) are hit millions of times per second. One node holds them. Your P99 latency goes from 2ms to 500ms. Users complain. Lesson: hot keys break distribution. Use replication for hot keys, or split the hot key into shards (e.g., global:config:0, global:config:1) and load balance. Design for hot keys from the start. Monitor per-node traffic. React before users complain.

---

## Surprising Truth / Fun Fact

Facebook's Memcached deployment at scale runs thousands of nodes. They built custom software (mcrouter) to route requests, handle failures, and manage replication. A simple cache at internet scale becomes its own distributed system. The principles stay the same; the engineering does not. Start with one node. Add when you hit limits. Distributed cache is an evolution, not a starting point.

---

## Quick Recap

- Distributed cache equals multiple nodes, one logical cache.
- When: memory limit, throughput limit, fault tolerance.
- How: partition by consistent hashing; key to node.
- Distributed vs local: shared vs per-server.
- Hot keys can break distribution; design for them. Monitor and react early.

---

## One-Liner to Remember

*A distributed cache is many fridges with a shared map: partition by hash, scale by adding nodes.*

---

## Next Video

Next: sharding and consistent hashing in depth. The hash ring, virtual nodes, and what happens when a node dies. See you there.
