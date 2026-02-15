# Distributed Cache: Sharding and Consistent Hashing

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Five cache nodes on a hash ring. Your data key hashes to a point on the ring. It goes to the *next* node clockwise. Node 3 crashes—only Node 3's data needs to move. To Node 4. Node 6 gets added—only the data between Node 5 and Node 6 moves. Minimal disruption. That's consistent hashing. Let's see how it works and why it matters.

---

## The Story

Imagine a circular track with runners. Each runner has a position. You throw a ball—it lands at a point. The next runner clockwise catches it. Remove one runner? Only that runner's segment goes to the next runner. Add a runner? Only the segment between the previous and new runner moves. The circle is the hash ring. Runners are nodes. The ball is your data key. Consistent hashing minimizes reshuffling when the topology changes.

---

## Another Way to See It

A clock face. 12 positions. Nodes sit at 3, 6, 9, 12. A key hashes to 4—it goes to node at 6 (next clockwise). Node at 5 is added. Keys that hashed between 3 and 5 now go to 5 instead of 6. Only that slice moves. The rest stay put. That's the elegance—O(1/N) data movement when you add one node, not O(1) like simple modulus.

---

## Connecting to Software

**Consistent hashing ring:** Hash nodes to positions on a 0–2^32 circle. Hash keys to positions. Key goes to first node clockwise. **Virtual nodes (vnodes):** Each physical node gets 100–200 virtual positions. Balances load—without vnodes, one node might get a huge contiguous chunk. With vnodes, load spreads.

**Client-side routing:** Client library (Jedis, Lettuce) knows the ring. Hashes key, finds node, connects directly. No proxy. **Proxy-based:** Twemproxy, Envoy—client talks to proxy, proxy routes. Centralized routing, simpler clients.

---

## Replication

Each key stored on N consecutive nodes (e.g., N=2). Primary holds it; replica is next clockwise. Node 3 dies? Node 4 has the replica. Reads can hit primary or replica. Writes go to primary, replicate async or sync. Trade-off: more nodes, more durability, more write amplification. Replication adds write cost: every set goes to N nodes. But reads can fan out. Read from replica for lower latency on the primary. The diagram shows the ring. Five nodes. Key hashes. Next clockwise. Add Node 6. Only the arc between Node 5 and Node 6 moves. Elegant.

---

## Let's Walk Through the Diagram

```
                 CONSISTENT HASH RING
                         
                    Node 1
                       ●
                  /         \
             Node 4           Node 2
                ●               ●
                 \             /
                  \           /
                   \         /
                    ●       ●
                   Node 3  Node 5
                   
    Key "user_123" hashes to point K
    → Goes to Node 2 (next clockwise)
    
    Node 3 dies → only Node 3's keys
    move to Node 4
    
    Node 6 added between 5 and 1
    → only keys in that arc move to Node 6
```

---

## Real-World Examples

**Amazon DynamoDB** uses consistent hashing for partition routing. **Redis Cluster** uses hash slots (16384) assigned to nodes—similar idea. **Cassandra** uses a token ring. **Voldemort** (LinkedIn) pioneered consistent hashing for distributed storage. The pattern is everywhere: minimize data movement on topology change. When Node 3 dies, only Node 3's keys need to be served from somewhere else. If you have replication (N=2), Node 4 already has a copy. Promotions happen. Failover is smooth. Without consistent hashing, a node failure would require a full rebalance. With it, only the failed node's slice moves. Recovery is fast. Virtual nodes (vnodes) solve the load imbalance problem. Without vnodes, one physical node might get 40% of the ring by chance. With 150 vnodes per physical node, the distribution smooths out. Each vnode is a point on the ring. Data spreads more evenly. Add vnodes when you see uneven load. Redis Cluster uses 16384 hash slots—similar idea. Slots distribute across nodes. Rebalance when adding or removing nodes.

---

## Let's Think Together

**"You have 10 cache nodes. One gets 5x more traffic due to hot keys. How do you rebalance?"**

Hot keys break the hash. One key gets millions of requests; it lives on one node; that node is overloaded. Solutions: (1) Replicate hot keys—copy to multiple nodes, read from any. (2) Split the key—shard it (e.g., user_123_shard_0, user_123_shard_1) so load spreads. (3) Add more vnodes for that key's hash range—requires custom logic. (4) Local cache in front—each app server caches the hot key; fewer requests hit the cluster. Often: replication for known hot keys, local cache for the hottest. If you know certain keys are hot (e.g., global config), replicate them explicitly. Add read replicas for those keys. Or shard the key: config:0, config:1. Each shard gets its own node. Load spreads. Start simple; add complexity when you measure the problem.

---

## What Could Go Wrong? (Mini Disaster Story)

You add 5 nodes to a 5-node cluster. Double the size. With consistent hashing, ~50% of keys move. Cache misses spike. Database gets hammered. Your p99 latency goes from 10ms to 2 seconds. Lesson: add nodes gradually. Or warm the new nodes—preload hot keys before switching traffic. Big topology changes need a migration plan, not a big-bang cutover.

---

## Surprising Truth / Fun Fact

Consistent hashing was introduced in a 1997 paper for distributed caching (Akamai, Karger et al.). It solved the "all keys move when you add a server" problem of simple hashing. Twenty-five years later, it's still the default for distributed caches and databases. Elegant algorithms last.

---

## Quick Recap

- Consistent hashing: keys hash to ring, go to next node clockwise; minimal movement on add/remove.
- Virtual nodes: balance load; prevent one node from getting a huge segment.
- Routing: client-side (library knows ring) or proxy-based (Twemproxy, Envoy).
- Replication: store key on N consecutive nodes; survive single-node failure.
- Hot keys: replicate or shard the key; use local cache for hottest. The hash ring distributes keys. But it cannot distribute a single hot key. That key will always live on one node. Plan for it. Replicate. Shard. Or cache locally. Know your access patterns.

---

## One-Liner to Remember

*Consistent hashing: the ring, the next node clockwise—add or remove a node, only a slice of data moves.*

---

## Next Video

Next: object storage. How does S3 achieve 11 nines of durability? Let's explore the architecture behind "your data will never be lost."
