# What is Consistent Hashing? (Simple Version)

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Musical chairs. 100 kids. 10 chairs arranged in a circle. Each kid walks clockwise until they find a chair. Simple. Now we REMOVE one chair. What happens? In normal hashing — hash mod 10 becomes hash mod 9 — everyone reshuffles. Chaos. In musical chairs? Only the kids who were sitting in that chair need to move. They walk to the next chair. Everyone else? Stays put. Minimal disruption. Add a new chair? Only nearby kids shift. That's consistent hashing. When servers change, only a SMALL portion of data moves. Not everything. Here's the crazy part — it was invented for web caching in 1997. Now it runs the internet.

---

## The Story

Imagine a circle. All possible hash values — 0 to 2^32 — arranged around it. Like a clock. Now place your servers at random points on the circle. Server A at position 100. Server B at 5000. Server C at 20000. Server D at 35000. They're spread around. Not evenly — random. That's okay. We'll fix that in a moment.

Data comes in. user_id 12345. Hash it. You get 15234. That's a point on the circle. Now walk clockwise. Which server do you hit first? Server B at 5000? No. Server C at 20000? Yes. The data goes to Server C. That's the rule: hash the key. Find the point. Walk clockwise. First server you reach owns it.

**Adding a server:** New server E goes at position 18000. Between C and D. Now some data that used to go to C — because C was the next clockwise — now goes to E. Only the data between the previous server and E moves. Everything else? Untouched. Add one server. Move ~1/N of data. Minimal.

**Removing a server:** Server C crashes. Its data? Goes to the next server clockwise. Server D. Only C's data moves. Everyone else stays. Remove one server. Move 1/N of data. Clean.

Compare to hash mod N. Add one shard? Move (N-1)/N. Remove one? Move everything. Consistent hashing? Move 1/N. Game changer.

**Virtual nodes:** One problem. Servers placed randomly might cluster. Server A and B next to each other. Uneven. Solution: each physical server gets multiple points on the ring. Virtual nodes. Server A: positions 100, 5000, 12000. Server B: 3000, 8000, 25000. Spread out. Better distribution.

---

## Another Way to See It

A round table. 10 seats. People sit. You remove one seat. Only the person in that seat moves. They take the next available. Everyone else stays. Add a seat? Only the person now "between" two others might shift. Minimal movement. That's the idea. Change the topology. Minimize the disruption.

---

## Connecting to Software

**The ring:** 0 to 2^32 (or 2^64). Wraps around. Circle. Servers = points on the ring. Data = points on the ring. Assignment = next server clockwise.

**Adding server:** Place on ring. Data between its position and the previous server's position moves. ~1/N. Rest unchanged.

**Removing server:** That server's data moves to next clockwise. ~1/N moves.

**Virtual nodes (vnodes):** Each physical server has K points on ring. K=100, K=256. Better distribution. Fewer hot spots. Cassandra. DynamoDB. All use this.

**Used by:** DynamoDB, Cassandra, Memcached, Redis Cluster, Varnish, CDNs. Everywhere.

---

## Let's Walk Through the Diagram

```
CONSISTENT HASHING RING

           0
           │
     D ●───┼───● A
      (35k)│    (100)
           │
           │   Key hash = 15234
           │        │
           │        ▼
           │   ┌─────────┐
           │   │  Point  │
           │   │ 15234   │
           │   └────┬────┘
           │        │
           │   Walk clockwise
           │        │
     C ●───┴────────┴───► Assign to C (first server reached)
      (20k)
           │
           │
     B ●───┘
      (5k)

Add server E at 18k: Only data 15234-20k moves from C to E. Rest stays.
```

Step 1: Hash key → point on ring. Step 2: Walk clockwise. Step 3: First server owns it. Step 4: Add/remove server? Only nearby data moves. Elegant.

---

## Real-World Examples (2-3)

**1. DynamoDB:** Partition key hashed. Partition key space mapped to partitions. Partitions assigned to nodes. Add node? Reassign some partitions. Minimal movement. Consistent hashing under the hood.

**2. Cassandra:** Token ring. Nodes have tokens. Data hashes to token. Assigned to node owning that token range. Add node? Add token. Only that range moves. Cassandra 3.0+ uses vnodes. 256 per node. Even better.

**3. Memcached:** Original use case. Cache servers. Add one? Only 1/N of keys moves. Client libraries handle it. Akamai. CDNs. Caching. Everywhere.

---

## Let's Think Together

You have 4 servers on the ring. One crashes. What fraction of data needs to move? Compare to simple hash mod 4.

*Think about that.*

**Consistent hashing:** Only that server's data. 1/4. 25%. Moves to the next server clockwise. Clean.

**Simple hash mod 4:** Now you have 3 servers. hash mod 3. Every key's remainder changes. 2/3 of data maps somewhere new. 67% moves. Chaos. Consistent hashing wins. Minimal disruption. That's why it exists.

---

## What Could Go Wrong? (Mini Disaster Story)

No virtual nodes. Four servers. Random placement on ring. By bad luck, two servers land close together. Small arc. One server gets 40% of the data. The other gets 5%. Uneven. Hot partition. The ring works. But random placement can create skew. Virtual nodes fix it. Each server gets 100 points. Spread around. Average out. Always use vnodes in production. Always.

---

## Surprising Truth / Fun Fact

Consistent hashing was invented in 1997. By Karger et al. For web caching. Akamai. The paper: "Consistent Hashing and Random Trees." Distributed caching. Load balancing. The problem: caches get added and removed. Rehashing everything? Expensive. Consistent hashing: minimal movement. Simple idea. Massive impact. Now used by DynamoDB, Cassandra, Memcached, Redis Cluster, CDNs. It runs the internet.

---

## Quick Recap (5 bullets)

- **Ring:** 0 to 2^32. Servers = points. Data hashes to point. Assign to next server clockwise.
- **Add server:** Only data between new and previous server moves. ~1/N. Minimal.
- **Remove server:** Only that server's data moves. ~1/N. Clean.
- **Virtual nodes:** Multiple points per server. Better distribution. Use always.
- Invented 1997. For caching. Now everywhere. DynamoDB. Cassandra. Memcached.

---

## One-Liner to Remember

> Musical chairs on a ring. Add a chair — few move. Remove one — few move. Not everyone. That's consistent hashing.

---

## Next Video

Servers balanced. Data distributed. But one key gets 10,000 requests per second. One partition. Melting. Hot keys. Hot partitions. What happens when traffic isn't even? Next.
