# Messaging Platform: Scale and WebSockets

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

WhatsApp serves 2 billion users. Each online user has an open WebSocket connection. Picture this: 500 million users online at once. That's 500 MILLION persistent connections. One server might handle 100,000 connections. Do the math. That's 5,000 servers. Just for WebSocket connections. Now imagine User A sends a message to User B. The system must find WHICH of those 5,000 servers holds User B's connection. That's the scale challenge. Let's break it down.

---

## The Story

A single WebSocket connection is simple. Client connects. Server accepts. Messages flow both ways. But scale changes everything. 100 users? One server. 100,000? You need ten. A million? A hundred. Hundreds of millions? Thousands of servers. Each server holds thousands of live connections. Each connection consumes memory, file descriptors, CPU for heartbeats. The numbers are brutal.

When User A sends a message to User B, the magic happens in routing. A's server receives the message. It doesn't know where B is. It must look up: "Which server has B's connection?" A routing table answers that. User B's server_id. Send the message there. B's server pushes to B's WebSocket. Done. But the routing table is massive. Millions of entries. Constantly updating. Users connect. Users disconnect. Servers crash. The table churns. That's the real complexity. Not the WebSocket protocol. The scale layer on top of it.

---

## Another Way to See It

Think of a city's postal system. Millions of addresses. When you mail a letter, the post office doesn't deliver it themselves. They look up which local branch serves that address. Route the letter there. The local branch delivers. Same idea. Your message server is the central sorting facility. The routing table is the address directory. Each WebSocket server is a local post office. The lookup—user_id to server_id—is the heart of the system. Fast lookup. Global consistency. That's what makes it work.

---

## Connecting to Software

**Connection management.** Each server holds tens of thousands of WebSocket connections. In memory. A map: connection_id → WebSocket. When a user connects, they hit a load balancer. LB routes to a server (round-robin, least-connections, consistent hash). Server accepts. Registers the connection. Reports to the routing layer: "User X is now on Server 7." The routing table updates. Redis, ZooKeeper, or a consistent hash ring. Key: user_id. Value: server_id. Fast reads. Fast writes. This table is the nerve center.

**Service discovery.** When a message arrives for User B, the sender's server queries: "Where is B?" Lookup in Redis: server_id = 3. Forward the message to Server 3. Server 3 pushes to B's WebSocket. If B is offline, store in DB. The lookup is O(1) if you design it right. Millions of lookups per second. No bottleneck.

**Horizontal scaling.** Add servers. Capacity grows. New connections land on new servers. But the routing table must be updated for every connect and disconnect. At scale, that's millions of updates per minute. Your storage layer—Redis, for example—must handle that write load. Shard the routing table if needed. Partition by user_id. Consistent hashing keeps it manageable.

**Connection migration.** Server goes down. 100,000 connections drop. All those users? Their clients reconnect. Exponential backoff. Retry. They might land on different servers. The routing table updates with new server_ids. Old entries? Stale. You need TTLs or cleanup. A dead server's entries must be purged. Otherwise, messages route to a dead server. Lost. Design for churn. It's constant.

---

## Let's Walk Through the Diagram

```
MESSAGING SCALE - WEBSOCKETS ACROSS SERVERS
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   USER A                SERVER 1               ROUTING TABLE     │
│   (online)                   │                 (Redis)           │
│       │                      │                      │            │
│       │  Message to B        │  lookup(B) ────────► │            │
│       │─────────────────────►│  server_id = 3      │            │
│       │                      │                      │            │
│       │                      │  forward to Server 3 │            │
│       │                      │─────────────────────┼──────────►  │
│       │                      │                     │   SERVER 3  │
│       │                      │                     │       │     │
│       │                      │                     │       ▼     │
│       │                      │                     │   USER B    │
│       │                      │                     │   (online)  │
│                                                                  │
│   ROUTING: user_id → server_id. Message routes to B's server.    │
│   CONNECTION MIGRATION: Server down → clients reconnect → table  │
│   updates. Heartbeats detect dead servers.                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: A sends a message to B. Server 1 receives it. Looks up B in the routing table. B is on Server 3. Server 1 forwards the message to Server 3. Server 3 pushes to B's WebSocket. The routing table is the glue. Without it, Server 1 has no idea where B is. With it, every message finds its destination across thousands of servers. The diagram is simple. The implementation at 500 million connections is not. But the principle holds.

---

## Real-World Examples (2-3)

**WhatsApp.** Billions of users. Hundreds of millions online at once. Erlang-based servers. Each handles hundreds of thousands of connections. Routing via distributed systems. Proved the model at planetary scale. The gold standard.

**Discord.** Millions of concurrent WebSocket connections. Sharded architecture. Each shard handles a slice of users. Routing table maps user to shard. Real-time at scale. Gaming demands low latency. They deliver.

**Slack.** Similar pattern. WebSocket servers behind load balancers. Redis for presence and routing. Millions of messages per day. The architecture is well-understood. The execution is what separates good from great.

---

## Let's Think Together

**"500 million connections across 5,000 servers. One server crashes. 100,000 connections lost. What happens?"**

Clients detect the disconnect. WebSocket closes. Clients implement reconnect logic. Exponential backoff. Retry. They reconnect to load balancer. LB routes them to healthy servers—possibly different ones. Each reconnecting client registers with the routing table. New server_id. Old entries? Stale. You need a mechanism: when a server dies, mark its entries invalid. Or use short TTLs. Heartbeats from servers: "I'm alive." No heartbeat? Purge that server's users from the table. Meanwhile, messages for those 100,000 users? They hit the old server_id. Dead. They fail. Senders retry. Eventually, users reconnect. Routing table updates. Messages flow again. The window of lost messages? Seconds to minutes. Mitigate with queuing. Store undeliverable messages. Retry when user reconnects. Design for failure. It will happen.

---

## What Could Go Wrong? (Mini Disaster Story)

A messaging platform. 2,000 WebSocket servers. Redis for routing. One day, Redis gets a bad config. Memory limit hit. Eviction starts. Routing table entries get evicted. Random users. Their server_id? Gone. Message arrives for User B. Lookup returns nil. "Where is B?" No idea. Message goes to dead letter. B never gets it. B's friend thinks they're ignoring them. Multiply by millions of evictions. Chaos. Messages lost. Users furious. Fix: routing data is critical. Never evict it. Dedicated Redis for routing. Or use a store that doesn't evict critical data. One config mistake. Millions of ghost messages. The routing table isn't just a cache. It's the system's memory. Treat it that way.

---

## Surprising Truth / Fun Fact

A single WebSocket connection uses about 4KB to 10KB of memory on the server. 100,000 connections? 400MB to 1GB. Per server. Scale to 500 million connections. That's 2 to 5 terabytes of RAM just for connection state. Across 5,000 servers. The numbers are staggering. That's why companies like WhatsApp build custom runtimes. Erlang's lightweight processes. Go's goroutines. The right abstraction makes millions of connections possible. The wrong one? You run out of file descriptors before you run out of users.

---

## Quick Recap (5 bullets)

- **Scale challenge:** Millions of WebSocket connections require thousands of servers. Routing is the hard part.
- **Routing table:** Maps user_id to server_id. Redis or similar. Lookup when message arrives. Forward to correct server.
- **Horizontal scaling:** Add servers for more capacity. Routing table must handle connect/disconnect churn.
- **Connection migration:** Server crash → clients reconnect → table updates. Design for constant churn.
- **Design for failure:** Dead servers, stale entries, lost messages. Queue. Retry. Heartbeats. Never evict routing data.

---

## One-Liner to Remember

**Scaling WebSockets isn't about the connection—it's about the routing table that lets millions of messages find millions of users across thousands of servers.**

---

## Next Video

Next: message ordering, exactly-once delivery, and handling out-of-order arrivals at scale.
