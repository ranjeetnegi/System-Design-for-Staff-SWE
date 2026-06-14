# Chapter 36: Multi-Region Systems — Part B
## Replication Models and Their Trade-offs

---

## Before You Start: What This Section Is About

Part A of this chapter covered the fundamentals of multi-region architecture: why latency matters, what it costs to cross an ocean, and the difference between RPO and RTO. If you have not read Part A, read it first.

This section goes one level deeper. It covers the three main replication models that actually power multi-region systems at companies like Netflix, GitHub, and Amazon. It also covers the hardest practical problem in multi-region design: what happens when two regions try to write the same data at the same time.

At an L6 interview, you will be asked questions like these:

- "Your system needs 99.99% availability globally. How do you handle a full region outage?" — You need to know failover and how long it actually takes.
- "We want writes from EU users to be fast. Can we put a write-accepting region in EU?" — You need to know active-active and exactly why conflicts happen.
- "You have a shopping cart that needs to work even when regions can't talk to each other. How?" — You need to know CRDTs and how they sidestep conflicts mathematically.
- "When would you NOT use active-active even though it seems better?" — You need to know how to reason about ops complexity and conflict surface area.

This section covers all of those, in depth.

```
+---------------------+    +---------------------------+    +---------------------+
|  MODEL 1            |    |  MODEL 2                  |    |  MODEL 3            |
|  Active-Passive     |    |  Active-Active            |    |  Read-Local         |
|                     |    |                           |    |  Write-Central      |
| One region writes.  |    | All regions write.        |    | Reads: local.       |
| Others read only.   |    | Conflicts must be         |    | Writes: always to   |
| Simple, safe.       |    | resolved.                 |    | one central region. |
+---------------------+    +---------------------------+    +---------------------+
```

No model is universally best. The right choice depends on four things: how much consistency your data requires, how high your write volume is, how much write latency your users will tolerate, and how much operational complexity your team can handle. The sections below explain each model so you can make that decision precisely.

---

## Model 1: Active-Passive (Primary-Replica)

### The Analogy: A Hospital With One Operating Room

Imagine a hospital network with two buildings. Building A has the only operating room. Building B has a fully trained backup surgeon ready to go, watching every procedure on a live video feed.

Patients who need surgery get sent to Building A. The backup surgeon in Building B is watching, learning, staying in sync. If Building A burns down, the backup surgeon in Building B can be promoted: the hospital administrator declares Building B the new operating room, and patients are redirected there.

This is **active-passive replication**. One region — the **primary** — accepts all writes. One or more regions — the **replicas** — receive copies of those writes and serve reads only. There is never any confusion about who is authoritative. Exactly one region is writing at any given time.

### How It Works

The primary region accepts all write traffic. When a write lands on the primary, it applies that write to its local database and then sends that change to every replica via a **replication stream**. Replicas apply changes in the same order they arrived on the primary. Replicas can serve read traffic — they have a copy of all data, just potentially slightly behind.

This design has one enormous advantage: **write conflicts are impossible**. If only one region ever writes, two regions can never write the same record simultaneously. The conflict problem that haunts active-active systems simply does not exist here.

```
                          WRITE TRAFFIC
                               |
                               v
                    +---------------------+
     EU users       |   PRIMARY REGION    |   US users (writes)
     (writes) ----> |     us-east-1       | <----
                    |                     |
                    |  [PostgreSQL primary]|
                    +----------+----------+
                               |
              +----------------+----------------+
              |  replication stream (async/sync)  |
              v                                   v
  +---------------------+           +---------------------+
  |  REPLICA REGION     |           |  REPLICA REGION     |
  |    eu-west-1        |           |    ap-southeast-1   |
  |                     |           |                     |
  |  [PostgreSQL replica]           |  [PostgreSQL replica]
  |  reads only         |           |  reads only         |
  +---------------------+           +---------------------+
       ^                                     ^
       |                                     |
  EU users (reads)                    Asia users (reads)


  DNS: reads -> nearest replica, writes -> primary (always)
```

### Synchronous vs Asynchronous Replication

This is one of the most important L6-level distinctions in the active-passive model. It controls the RPO — how much data you can lose if the primary dies right now.

#### Synchronous (Semi-Sync) Mode

In **synchronous replication**, the primary does not respond to the client until at least one replica has confirmed it received and applied the write. The sequence is:

1. Client sends write to primary.
2. Primary applies write locally.
3. Primary sends write to replica.
4. Replica applies write, sends ACK back to primary.
5. Primary responds to client: "write successful."

The benefit: **RPO = 0**. If the primary dies the instant after step 5, the replica already has the data. No data loss is possible.

The cost: every single write must wait for a cross-region round-trip before the client sees a response. US-East to EU-West is roughly 100-150 ms of round-trip time. For a system that does thousands of writes per second, that added latency per write stacks up fast.

Use synchronous replication when: data loss is genuinely unacceptable. Financial transaction records. User authentication credentials. Anything where a lost write has a legal or monetary consequence.

**GitHub** uses synchronous replication for their Git data layer. When you run `git push`, GitHub does not confirm that push as successful until at least one replica has durably received the objects. From a user's perspective, a push takes slightly longer. From a data safety perspective, a confirmed push is guaranteed to survive a single-region failure.

#### Asynchronous Mode

In **asynchronous replication**, the primary responds to the client immediately after applying the write locally. It then sends the write to replicas in the background — but the client does not wait for that.

The benefit: **near-zero write latency overhead**. Writes complete as fast as the primary's local disk.

The cost: **RPO > 0**. If the primary fails between the moment it responded to the client and the moment the replica received the write, that write is lost forever. In practice, replication lag — the gap between what the primary has written and what the replicas have received — is typically a few hundred milliseconds under normal load, but can stretch to minutes during heavy write traffic or a slow network.

Use asynchronous replication when: some data loss is acceptable. Analytics event streams. Session data. Search indexes. Non-financial user activity logs.

**Instagram's** media replicas across regions were asynchronous for a long time. When you posted a photo, it was immediately confirmed. But if you traveled to a different region's URL and checked within the first few seconds, you might not see the photo yet — it had not replicated there. This was acceptable because the data was not permanently lost, just delayed.

```
SYNCHRONOUS (semi-sync):

  Client                Primary               Replica
    |                      |                      |
    |-- WRITE ------------>|                      |
    |                      |-- replicate -------->|
    |                      |<-- ACK --------------|
    |<-- OK (success) -----|                      |
    |                      |                      |
    Latency: local write + cross-region RTT (100-200ms extra)
    RPO: 0


ASYNCHRONOUS:

  Client                Primary               Replica
    |                      |                      |
    |-- WRITE ------------>|                      |
    |<-- OK (success) -----|                      |
    |                      |-- replicate -------->|  (background)
    |                      |<-- ACK --------------|  (background)
    |                      |                      |
    Latency: local write only (no extra RTT)
    RPO: seconds to minutes of potential data loss
```

### Failover: The Dangerous Part

Failover is when the primary region fails and you promote a replica to become the new primary. It sounds simple. In practice, it is the most dangerous operation in an active-passive system. Multiple major incidents in the history of distributed systems trace back to failover gone wrong.

#### What Happens During Failover

When monitoring detects that the primary is unreachable:

1. Monitoring alerts fire. Automated system or on-call engineer is notified.
2. Decision: is the primary actually dead, or is it just slow/unreachable?
3. If dead: choose which replica to promote. Pick the one with the least replication lag.
4. **Promote** the chosen replica: it stops being read-only and starts accepting writes.
5. Update **DNS** (or a service registry) so all write traffic routes to the new primary.
6. Other replicas reconnect to the new primary and start replicating from it.
7. Old primary, if it recovers, must rejoin as a replica — not as the primary.

```
NORMAL OPERATION:

  writes --> [PRIMARY: us-east-1]  -----> [REPLICA: eu-west-1]
                                   -----> [REPLICA: ap-east-1]

DURING FAILOVER (primary fails):

  [PRIMARY: us-east-1]  X (dead)
                                          eu-west-1 has lag: 0.5s
                                          ap-east-1 has lag: 3.0s

  Step 1: choose eu-west-1 (less lag)
  Step 2: promote eu-west-1 -> new primary

  writes --> [NEW PRIMARY: eu-west-1]
                                  -----> [REPLICA: ap-east-1]
                                          (ap-east-1 reconnects to new primary)

  Step 3: update DNS
  Step 4: old us-east-1, when it recovers, rejoins as replica
```

#### Automated vs Manual Failover

**Automated failover** is fast — typically 30 to 60 seconds from failure detection to replica promotion. But it carries a serious risk: **false positives**. If the primary is merely slow — a network partition, a CPU spike, a thundering herd — the monitoring system might declare it dead and promote a replica. Now both the old primary (still running, just slow) and the newly promoted replica are both accepting writes. This is called **split-brain**.

**Manual failover** is slow — typically 15 to 30 minutes because a human has to be paged, confirm the situation, and execute the steps. But it is much safer: a human can verify the primary is genuinely dead before promoting.

**L6 rule**: default to manual failover unless you have extremely reliable health-checking AND an automated mechanism to prevent split-brain. The famous 2017 GitLab database incident illustrates what happens otherwise. During a manual failover procedure, an engineer accidentally deleted the primary database directory instead of a replica directory. The combination of replication lag, human error under pressure, and incomplete backup procedures resulted in approximately 300 GB of data loss. The lesson is not that humans are unreliable — it is that failover procedures must be practiced, documented, and as automated as possible for the mechanics while keeping humans in the decision loop.

#### Split-Brain in Active-Passive

**Split-brain** is the scenario where both the old primary and the newly promoted replica believe they are the leader and accept writes simultaneously. You end up with two diverging write streams. When the partition heals and they can communicate again, you have two different histories for the same data. Which writes win? There is no automatic answer.

The standard prevention is **STONITH** — Shoot The Other Node In The Head. Before promoting a replica to primary, you send a command to physically power off the old primary (via IPMI, a power distribution unit, or a cloud API that terminates the instance). This guarantees the old primary cannot accept writes because it is not running. Only then do you promote the replica.

An alternative is using **distributed consensus** (Raft or Paxos) as a leadership oracle. A quorum of nodes votes on who is the current leader. A region cannot become primary unless a majority of nodes agree it should be. This prevents split-brain because two regions cannot simultaneously get a majority vote.

#### Replication Lag at Failover

Here is a practical detail that interviewers love to probe: even in an active-passive system with async replication, the **actual RPO at failover time is not predictable**.

Under normal, steady-state conditions, replication lag might be 200 ms. But at the moment of primary failure, the system is likely under high load — otherwise you might not have noticed the failure as quickly. During a write-heavy spike, replication lag can balloon to seconds or minutes. The replica being promoted might be thousands of writes behind the primary at the instant of failure.

This means the real-world RPO for async active-passive systems is often 30 to 120 seconds of data, not zero. The mitigation: use synchronous replication for the critical tables (user accounts, financial records) and async for everything else (activity logs, analytics). This hybrid approach is what most production systems at scale actually use.

### Active-Passive: Strengths and Weaknesses

| Aspect | Active-Passive |
|---|---|
| Write conflicts | Impossible — only one region writes |
| Write latency | Low for async (no cross-region confirmation) |
| Read latency | Low — serve from nearest replica |
| Failover complexity | Medium — requires promotion and DNS change |
| Data loss risk | Medium — async replication lag at failover time |
| Operational complexity | Low to medium |
| Best for | Most relational databases, stateful services, financial systems |

### Real Example: Amazon RDS Multi-Region

Amazon RDS lets you create a read replica in a second region. A common setup: primary PostgreSQL in us-east-1, read replica in eu-west-1.

All writes go to us-east-1. EU users reading data hit eu-west-1, which is fast because the data center is nearby. EU users writing data have their writes routed across the Atlantic to us-east-1 — a 100-150 ms round-trip. For a typical CRUD application where reads outnumber writes by 10:1 or more, this is acceptable.

Promotion to primary — when you want to make the EU replica the new primary after a regional failure — takes 5 to 7 minutes through the AWS console manual process. During those minutes, writes are unavailable. For a business whose users are predominantly in Europe, this RTO of 5-7 minutes might be acceptable. For a trading system, it is not.

### How the Replication Stream Actually Works

At the implementation level, active-passive replication for relational databases works through the **Write-Ahead Log (WAL)**. Every write to a PostgreSQL or MySQL database is first written to the WAL — a sequential, append-only log of every change the database made. This log exists for crash recovery: if the server dies, it replays the WAL to reconstruct state.

Replication hijacks this same log. The primary ships WAL entries to the replica over a persistent TCP connection. The replica applies those entries in order. Because the WAL captures every write at the lowest possible level — individual row inserts, updates, deletes — the replica ends up in an identical state to the primary.

```
  PRIMARY (us-east-1):

    [client write] --> [WAL entry written] --> [table updated]
                              |
                              | WAL streaming replication
                              v
  REPLICA (eu-west-1):

    [WAL entry received] --> [applied to local table]

  Replication lag = time between WAL entry written on primary
                    and WAL entry applied on replica.
  Typical healthy lag: 50-500 ms.
  Lag during heavy write traffic: seconds to minutes.
```

**MySQL uses the binlog** (binary log) instead of WAL for the same purpose. The binlog records SQL statements or row-level changes. MySQL replicas connect to the primary, request binlog events starting from a position, and replay them.

This is important to understand for one specific reason: the replication stream is **ordered**. The replica applies changes in exactly the same order as the primary. This means if a row is inserted and then deleted, the replica will see the insert first and the delete second — even if they arrive together. There is no reordering, no merging, no ambiguity. Ordered replay is what makes active-passive conflict-free.

**Change Data Capture (CDC)** extends this idea to non-database systems. Tools like **Debezium** read the database WAL and publish change events to Kafka. Downstream services — search indexes, caches, analytics pipelines — subscribe to these events and update themselves. This allows you to replicate not just to other databases but to any service that needs to stay in sync.

```
  PRIMARY DB --> WAL --> Debezium --> Kafka topic: "user_changes"
                                           |
                        +------------------+------------------+
                        v                  v                  v
                 Elasticsearch      Redis cache         Analytics DB
                 (search index)     (invalidate)        (data warehouse)
```

At the Staff level, CDC is important because it decouples replication from the database protocol. You can replicate the same data to five different systems, each consuming the change stream at its own pace, without the primary database knowing anything about them. The primary only writes to its WAL. Everything downstream is a subscriber.

---

## Model 2: Active-Active

### The Analogy: Two Post Offices Sharing One Customer Database

Imagine two post offices in different cities. Both post offices can accept package drop-offs — writes to the system — at any time. Both post offices have access to a shared customer database showing which packages belong to which customers.

Now imagine that at 2 PM, customer Alice walks into the Chicago post office and says "I want to update my delivery address to 123 Main Street." Simultaneously, Alice's husband walks into the New York post office and says "I want to update the delivery address to 456 Oak Avenue." Both post offices process these requests immediately. An hour later, when the two databases sync up — what is Alice's address?

There is no automatically correct answer. **Active-active** is powerful because both regions can write, which means both regions can respond fast to local users. But the engineering challenge is almost entirely about answering that question: when two regions write the same data at the same time, what happens?

### How It Works

In **active-active replication**, all participating regions accept write traffic simultaneously. Each region has a full copy of the data. Writes are applied locally and then propagated asynchronously to all other regions. When two regions receive conflicting writes to the same record before replication catches up, the system must detect and resolve that conflict.

```
        EU USERS                         US USERS
            |                                |
            v                                v
  +-----------------------+       +----------------------+
  |  REGION: eu-west-1    |       |  REGION: us-east-1   |
  |  [accepts writes]     |       |  [accepts writes]    |
  |  [accepts reads]      |       |  [accepts reads]     |
  +-----------+-----------+       +----------+-----------+
              |                              |
              |  <-- bidirectional async --> |
              |     replication stream       |
              |                              |
              +----------+  +---------------+
                         |  |
                         v  v
                  +------------------+
                  |  CONFLICT        |
                  |  DETECTION &     |
                  |  RESOLUTION      |
                  |  (per record)    |
                  +------------------+
```

### Why Active-Active Is Hard: The Conflict Problem

#### What a Conflict Looks Like in Practice

Consider a user profile record in a global database. The record starts as: `{name: "Alice", email: "alice@old.com"}`.

At 3:00:00 PM, Alice logs in from London and updates her email. EU region writes: `{name: "Alice", email: "alice@new.com"}`.

At 3:00:01 PM — one second later, before the EU write has replicated to US — Alice's account gets updated by an automated job in the US that normalizes name capitalization. US region writes: `{name: "ALICE", email: "alice@old.com"}`. (The US job saw the old value of `alice@old.com` because the EU write had not arrived yet.)

Now replication runs. EU replicates `{email: "alice@new.com"}` to US. US replicates `{name: "ALICE"}` to EU. Each region now has a conflict: two different versions of the same record, written concurrently, with neither version having seen the other.

What should the final state be?

- **Merge both**: `{name: "ALICE", email: "alice@new.com"}` — logically the right answer here, but requires the system to understand how to merge field-by-field.
- **EU wins**: `{name: "Alice", email: "alice@new.com"}` — last writer by timestamp, EU wrote later. But Alice's name normalization is lost.
- **US wins**: `{name: "ALICE", email: "alice@old.com"}` — last writer by timestamp if US clock is ahead. Alice's email update is silently discarded.

There is no single right answer. The system must pick a resolution strategy, and that strategy must be appropriate for the data type.

### Conflict Resolution Strategies

#### Strategy 1: Last Write Wins (LWW)

**Last Write Wins** is the simplest approach. Every write carries a timestamp. When two conflicting writes are detected, the one with the later timestamp wins. The other write is discarded.

Simple to implement. But fragile in practice because of **clock drift**: different servers have clocks that drift relative to each other by seconds or even minutes. A write from Server A with an artificially fast clock will always "win" against Server B's writes, even if Server B's write was logically later. A retried stale write carrying an old timestamp can overwrite a newer valid write.

**Cassandra** uses LWW by default. **DynamoDB** offers LWW as an option. These are appropriate for data where the occasional wrong resolution is acceptable: user preferences, session data, non-critical settings. They are dangerous for financial data or anything where data loss has a real-world consequence.

#### Strategy 2: Version Vectors (Vector Clocks)

**Version vectors** — sometimes called vector clocks — are a more reliable way to track causality between writes across regions. Instead of a single timestamp, each write carries a vector of logical counters, one per region.

A write that reads `{eu: 5, us: 3}` means: "this version has incorporated 5 writes from EU and 3 writes from US." When two writes conflict, you compare their vectors:

- If vector A dominates vector B (every component of A is >= every component of B), then A is causally after B. B can be discarded.
- If neither vector dominates the other (some components of A are higher, some components of B are higher), these are **truly concurrent writes** — no causal ordering exists. This is a genuine conflict that requires application-level resolution.

**DynamoDB** uses version vectors internally for conflict detection. The key insight: vector clocks tell you precisely whether two writes conflict. LWW tells you nothing about this — it just picks a winner and discards the loser silently.

#### Strategy 3: Application-Level Merge

Some data types have natural merge semantics that make conflict resolution correct and unambiguous.

A shopping cart is a classic example. User adds item A to cart in EU. Simultaneously, user removes item B from cart in US. With LWW, one of these operations is silently discarded. With application-level merge, you apply both: add item A AND remove item B. The final cart contains A and does not contain B. Both user intentions are honored.

**Amazon's shopping cart** uses exactly this approach. The merge logic is: additions and removals are tracked as separate operations, not as a full state replacement. Merging two concurrent versions of the cart replays all operations from both versions.

This requires the application to be designed around **operations** (deltas) rather than **states** (full values). Instead of writing "the cart is now [A, C, D]," you write "add A" and "remove B." Operations that commute (can be applied in any order with the same result) never conflict.

#### Strategy 4: CRDTs (Conflict-free Replicated Data Types)

**CRDTs** — Conflict-free Replicated Data Types — are mathematical data structures designed so that any two versions of the data can always be merged into a consistent result, regardless of the order of operations or the timing of replication. No coordination required. No conflict detection required. Merges are always well-defined.

A **G-Counter** (grow-only counter) is the simplest CRDT. Each region has its own slot in a vector. Regions only increment their own slot — they never touch another region's slot. The global total is the sum of all slots. Two G-Counters can always be merged by taking the maximum of each slot. There is no conflict because no region ever writes to another region's slot.

```
  Region EU counter: [eu: 42, us: 0, ap: 0]   total = 42
  Region US counter: [eu: 0,  us: 17, ap: 0]  total = 17

  Merged (take max per slot):
  [eu: 42, us: 17, ap: 0]                      total = 59
```

A **G-Set** (grow-only set) allows adding items, never removing. An **OR-Set** (observed-remove set) allows both adds and removes, and handles the concurrent add/remove conflict by making "add" win over "remove" in the case of ambiguity.

**Redis** uses CRDTs for cluster-wide counters. **Riak** built its entire data model around CRDTs. Collaborative editing applications like **Google Docs** use a related technique called operational transforms — conceptually similar to CRDTs — to merge concurrent edits character by character.

CRDTs are not magic: they impose constraints on your data model. Not every data type has a natural CRDT encoding. But for the types that do (counters, sets, registers, maps), they eliminate the conflict problem entirely.

### Active-Active Topology Patterns

#### Symmetric Active-Active (Two Regions)

The simplest topology: two regions, each a full mirror of the other, each accepting writes. Replication is bidirectional. Conflicts are possible but limited because there are only two writers.

This is manageable. Most active-active deployments at medium scale are symmetric two-region setups.

```
  us-east-1                          eu-west-1
  +------------------+               +------------------+
  |  [DB primary A]  | <-----------> |  [DB primary B]  |
  |  writes from US  |  bidirec.     |  writes from EU  |
  |  users           |  async repl   |  users           |
  +------------------+               +------------------+

  Conflict rate: low if writes are mostly user-scoped.
  Conflict rate: high if writes touch shared tables.
```

#### Hub-and-Spoke Active-Active

One central **hub** region acts as the conflict resolution authority. Multiple **spoke** regions accept writes locally but replicate to the hub. The hub detects conflicts, resolves them using a defined strategy, and replicates the resolved state back to all spokes.

This adds latency for conflict resolution (the spoke must wait for the hub to process and confirm) but gives you stronger consistency guarantees. **Cloudflare Workers KV** uses a similar architecture: writes go to edge nodes globally, but the global key-value store reconciles through a central system.

```
  SPOKE: eu-west-1          HUB: us-east-1         SPOKE: ap-southeast-1
  +-----------------+       +-------------------+   +-----------------+
  | [local writes]  | ----> | [conflict         | <-| [local writes]  |
  |                 | <---- |  resolution]      | ->|                 |
  +-----------------+       +-------------------+   +-----------------+
                                     |
                             resolves conflicts,
                             broadcasts canonical
                             state to all spokes
```

The hub-and-spoke pattern is a pragmatic middle ground between "active-passive with one writer" (simple, correct, high write latency for spokes) and "symmetric active-active" (fast, complex, hard to resolve conflicts). The hub gives you a single conflict resolution point without requiring all writes to travel to the hub before responding to the user.

### The User-Affinity Solution: Avoid Conflicts by Design

Here is the most important practical insight about active-active systems at large companies: **most "active-active" deployments avoid conflicts by preventing them, not by resolving them**.

The technique is **user affinity routing**: each user's writes always go to one specific region, determined by their user ID. A common implementation: `region = hash(user_id) % num_regions`. User "alice" always routes to US-East. User "bob" always routes to EU-West.

Because a single user's writes always land in the same region, two regions can never conflict on that user's data — the other region never writes it. Conflicts only arise in the rare cases where a user travels internationally, uses a VPN, or where a background job in a different region touches user data.

This is how Netflix, Facebook, and many others actually implement "active-active." It is more accurately described as **multi-primary with user sharding**. Each region is the primary for a subset of users. All regions replicate to all other regions, but conflicts are rare because user-level writes are not concurrent across regions.

```
  user_id hash -> region assignment:
    alice (hash % 2 = 0) -> always routes to us-east-1
    bob   (hash % 2 = 1) -> always routes to eu-west-1

  us-east-1: primary for alice's data, replica for bob's data
  eu-west-1: primary for bob's data, replica for alice's data

  Conflicts: only when alice travels to EU and writes there
             (extremely rare, handled by LWW or application merge)
```

### Active-Active: Strengths and Weaknesses

| Aspect | Active-Active |
|---|---|
| Write conflicts | Possible — must be handled by design |
| Write latency | Low — write to nearest region |
| Read latency | Low |
| Failover | Automatic — reroute traffic to another region |
| Data loss risk | Low to medium depending on conflict strategy |
| Operational complexity | Very high |
| Best for | User-sharded systems, shopping carts, eventual-consistent data |

### Real Example: Netflix Active-Active

Netflix operates active-active across us-east-1, us-west-2, and eu-west-1. Their core design principle for writes: **user session data is sharded by user_id**. Each user's session writes go to one "home" region. Data is replicated globally so any region can serve the data, but writes for a given user land in one place.

During the 2011 AWS us-east-1 outage — one of the most significant cloud outages in history — Netflix maintained service by rerouting users from us-east-1 to us-west-2. Because session state and user data were already replicated to us-west-2, users experienced the service as mostly intact. Watch history might have been a few seconds stale. Some very recent state might have been lost. But the service kept running, which is the whole point.

What Netflix gave up: perfect consistency of watch history across regions. If you watch 30 seconds of a show and the region fails before replication completes, you might be rewound 20 seconds when you reconnect to another region. This is acceptable. Losing your movie progress for 20 seconds is not a financial loss or a data integrity violation.

---

## Model 3: Read-Local, Write-Central

### The Analogy: A Chain of Libraries

Imagine a library system with one headquarters and twenty branch locations. All books are ordered and catalogued at headquarters. Branch libraries receive copies of the catalog and can loan out books locally for fast, convenient reading.

If a patron wants to check out a book, the branch handles it — fast, local, no waiting. If a patron wants to order a new book for the collection, that request goes to headquarters. The patron might wait a few extra days. That is acceptable because ordering a new book is rare compared to checking one out.

This is **read-local, write-central** replication. Reads happen at the nearest region (fast). Writes always travel to one central region (slow for distant users, but writes are rare).

### How It Works

One **central region** receives all writes. It is the authoritative source of truth. Multiple **read regions** hold replicas of the central data and serve reads locally. Replication flows from central to read regions: new writes land at central, then propagate outward.

```
                        ALL WRITES
                             |
                             v
              +--------------------------+
              |   CENTRAL WRITE REGION   |
              |       us-east-1          |
              |   [authoritative DB]     |
              +-----------+--------------+
                          |
             +------------+------------+
             |  replication (async)    |
             v                         v
  +---------------------+   +---------------------+
  |  READ REGION        |   |  READ REGION        |
  |  eu-west-1          |   |  ap-southeast-1     |
  |  [replica, reads]   |   |  [replica, reads]   |
  +---------------------+   +---------------------+
       ^                              ^
       |                              |
  EU reads (fast, local)         Asia reads (fast, local)


  EU user writes:
    EU user --> eu-west-1 --> [forwarded] --> us-east-1 --> write applied
                                              --> replicated back to eu-west-1
```

### The Latency Math

For an EU user:

- **Read**: EU user hits eu-west-1. Round-trip: 20 ms. Fast.
- **Write**: EU user's write is forwarded to us-east-1. EU to US: 100 ms. Processing at US: 10 ms. Response back to EU: 100 ms. Total: **~210 ms round-trip**.

For comparison, in active-passive with the primary in the US, EU writes are the same 210 ms. Read-local write-central is essentially active-passive with explicit language about how reads are served.

This math makes the model's constraint obvious: it works when **reads vastly outnumber writes** — at least a 95:5 ratio, and ideally higher. If your application writes on every user action (a chat app, a collaborative editor), the 200 ms write latency is unacceptable for EU users. If your application writes occasionally (profile updates, settings changes, new blog posts), users will not notice the extra 200 ms on an infrequent action.

### Who Uses Read-Local, Write-Central

**GitHub** serves branch reads and repository browsing globally from replicas. A `git clone` or a web browse of a repository can be served from the nearest point-of-presence. A `git push` goes to the primary. For the typical developer workflow (many reads, occasional pushes), this is the right trade-off.

**Stack Overflow** serves question and answer pages from CDN caches and read replicas globally. When you load a question, you hit a local edge cache. When you post a new answer, the write goes to their primary database. The read:write ratio for Stack Overflow is extreme — hundreds of reads per write. Read-local write-central is a natural fit.

Most **CMS and blog platforms** follow the same pattern. Authors write content centrally. Readers consume that content globally. The write volume is tiny compared to the read volume.

### Strengths and Weaknesses

| Aspect | Read-Local, Write-Central |
|---|---|
| Write latency | High for users far from central region |
| Read latency | Low — served from nearest replica |
| Write conflicts | Impossible — one writer |
| Conflict handling | Not needed |
| Failover complexity | Medium — same as active-passive |
| Operational complexity | Low to medium |
| Best for | Read-heavy workloads, content delivery, global reads with rare writes |

---

## Comparison: When to Use Which Model

### Decision Table

| Factor | Active-Passive | Read-Local Write-Central | Active-Active |
|---|---|---|---|
| Write latency | Low (async) | High for remote users | Low |
| Read latency | Low from replica | Low from replica | Low |
| Consistency | Strong (one writer) | Strong (one writer) | Weak / configurable |
| Failover speed | Medium (manual or auto) | Medium | Fast (automatic reroute) |
| Conflict handling | Not needed | Not needed | Required — core complexity |
| Ops complexity | Medium | Low to medium | Very high |
| Best for | Most OLTP, stateful services | Read-heavy, global content | High-write, user-sharded |

### The L6 Interview Framing: Do Not Default to Active-Active

A very common mistake at L5 and below: when the interviewer says "make it globally available," the candidate immediately says "I'll make it active-active."

Active-active sounds better because every region handles writes, which implies faster writes and no single point of failure. But this reasoning skips the most important question: **what happens to conflicts?**

A better L6 answer sounds like this:

"Active-active is attractive because it removes the single-writer bottleneck and handles regional failures without a failover step. But it introduces conflicts. Before committing to it, I want to understand the write patterns. If writes are user-scoped — each user only writes their own data — I can use user-affinity routing to ensure each user's writes land in one region, which makes active-active practical. If writes touch global shared state — an inventory counter, a financial balance — I cannot use user affinity, and concurrent writes from two regions will conflict. In that case, I would use active-passive and route all writes to the primary, accepting the write latency for correctness."

That answer shows you understand the trade-off, not just the name of the pattern.

---

## Conflict Resolution Deep Dive

This section is for Staff-level depth. The previous sections showed what conflict resolution strategies exist. This section explains how to choose between them and why the naive approaches fail.

### The Conflict Resolution Spectrum

Think of conflict resolution as a spectrum from "prevent conflicts before they happen" to "resolve conflicts after they happen."

```
PREVENT conflicts                                   RESOLVE conflicts
(coordination required)                             (merge required)

+------------------+----------+----------+----------------------+
| Distributed lock | Commute  | Logical  | Application-defined  |
| / 2PC            | ops CRDT | clocks   | merge                |
+------------------+----------+----------+----------------------+
| Safest           |          |          | Most flexible        |
| Highest latency  |          |          | Most complex         |
+------------------+----------+----------+----------------------+
```

#### Coordination: Prevent Conflicts at the Source

The most reliable approach: before any write is applied, acquire a distributed lock or run a two-phase commit across all regions. Only one writer proceeds at a time. Conflicts are impossible.

The cost: every write requires a cross-region round-trip for coordination. US to EU is 100 ms. Every write in your system now has at minimum 100 ms of coordination overhead. For a system doing 10,000 writes per second, this is likely a bottleneck you cannot accept.

Use coordination when: financial correctness is truly non-negotiable. **Stripe** routes all card authorization writes to a single region and uses coordination there. For a write that charges a user's credit card, the 100 ms latency is invisible next to the existing network and bank processing time. And the correctness guarantee is worth everything.

#### Commutative Operations: Design Away Conflicts

If you design your writes as **commutative operations** — operations where the order of application does not matter — then even concurrent writes from two regions produce the same result. Conflicts cannot exist if the order does not matter.

"Increment by 1" is commutative. Whether EU increments first or US increments first, the result is the same. "Set to X" is not commutative — the final value depends on which set operation ran last.

CRDTs formalize this insight into a complete data structure library. They constrain what operations are allowed on a data type specifically to ensure commutativity. This is not a limitation — it is a design discipline that eliminates an entire class of bugs.

#### Logical Clocks: Better Than Wall Clocks

When you must use last-write-wins, use **Lamport clocks** or **vector clocks** to establish ordering, not wall clocks.

A Lamport clock is a monotonically incrementing logical counter attached to each event. Rule: when a write arrives from another region, advance your local counter past theirs. This ensures a global ordering of events that respects causality.

```
  EU logical clock: 10
  US logical clock: 8

  EU sends write to US. US receives write.
  US advances its clock: max(8, 10) + 1 = 11.

  Now US's clock is ahead of EU's.
  Any subsequent US write has logical timestamp 11 or higher.
  Any EU write that happened before this sync has timestamp <= 10.
  Order is unambiguous.
```

The limitation: Lamport clocks give total ordering but do not tell you whether two events are concurrent or causally related. Vector clocks give you that information. For conflict detection, vector clocks are more informative.

#### Application-Defined Merge: Most Flexible, Most Work

When your data has semantic meaning that the database cannot understand, you need to write the merge logic yourself.

**Riak** implements this by returning both conflicting versions to the application with the response and letting the application code decide which to keep. This shifts the complexity to the application developer, who understands the semantics of the data.

**Google Docs** uses operational transforms: every edit is expressed as a delta ("insert character 'A' at position 42"), and a transformation function ensures that any two concurrent deltas can be applied in either order to reach the same result. The merge logic is sophisticated — it took years to get right — but it gives users the experience of seamless concurrent editing across distributed servers.

### The Last-Write-Wins Trap

**LWW appears simple but is fragile.** Two failure modes make it dangerous for anything that matters:

**Problem 1: Wall clock drift.** Server A's clock runs 3 seconds fast. Every write from Server A carries a timestamp 3 seconds ahead of Server B's writes. Server A's writes always "win" in LWW, not because they are logically later but because the clock is wrong. A write that is logically earlier but has a higher wall clock timestamp will silently discard a logically later write from Server B.

**Problem 2: Retry amplification.** A client retries a failed write. The retry carries the original timestamp (as it should, for idempotency). But if a newer write already succeeded between the original attempt and the retry, the retried write — carrying the older timestamp — would lose in LWW. Except that the retry might arrive AFTER the newer write at a different replica, and that replica's version of LWW might apply them in the opposite order.

The rule: **never use wall-clock LWW for data where a lost write has a real consequence.** Use logical clocks (Lamport or vector) for ordering if you must use LWW. Or use application-defined merge for data that matters.

```
WALL CLOCK LWW FAILURE EXAMPLE:

  Server A clock: 3:00:05 PM (5 seconds fast)
  Server B clock: 3:00:00 PM (correct)

  User writes "email = alice@new.com" to Server B at real time 3:00:00.
    Write timestamp: 3:00:00

  User writes "email = alice@broken.com" to Server A at real time 2:59:58 (TWO SECONDS EARLIER).
    Write timestamp (from fast clock): 3:00:03

  Server A's write has timestamp 3:00:03.
  Server B's write has timestamp 3:00:00.

  LWW: Server A wins (higher timestamp).
  Final state: alice@broken.com

  The logically EARLIER write won because the clock was wrong.
  alice@new.com is silently discarded.
```

---

## Putting It All Together: The L6 Mental Model

When you face a multi-region system design question in an interview, work through these questions in order:

**1. What is the read:write ratio?**
If reads heavily dominate (> 90%), read-local write-central may be sufficient. You get global read performance without conflict complexity.

**2. What is the write pattern?**
Are writes user-scoped (each user only writes their own records) or globally shared (inventory, balances, global counters)? User-scoped writes enable user-affinity routing, which makes active-active tractable. Globally shared writes mean true conflicts are possible and you must either serialize them (coordination) or accept some inconsistency.

**3. What is the RPO and RTO requirement?**
RPO = 0 means synchronous replication, which means accepting write latency. RPO = seconds means async replication is fine. RTO of 30 seconds requires automated failover. RTO of 5 minutes allows manual failover.

**4. What is the team's operational capacity?**
Active-active with conflict resolution is significantly more complex to operate than active-passive. If the team does not have on-call engineers who understand distributed systems deeply, active-passive is the safer choice even if it is theoretically lower performance.

```
  DECISION FLOW:

  Start
    |
    v
  reads >> writes (>90% reads)?
    |
    YES --> Read-Local Write-Central. Simple. Done.
    |
    NO
    |
    v
  writes user-scoped (user writes only their own data)?
    |
    YES --> Active-Active with user-affinity routing.
    |       Use CRDT or LWW for the rare cross-region edge case.
    |
    NO
    |
    v
  writes touch shared global state (inventory, balances)?
    |
    YES --> Active-Passive with synchronous replication for critical tables.
    |       Accept write latency for correctness.
    |       Plan failover procedure carefully. Practice it.
    |
    v
  What is RTO requirement?
    |
    < 60 seconds --> Automated failover with split-brain prevention (STONITH).
    |
    > 5 minutes  --> Manual failover. Safer. Simpler. Often correct choice.
```

The most important thing a Staff engineer brings to a multi-region discussion is not knowledge of which model is "best." It is the discipline to ask the right questions before recommending a model, and the ability to articulate exactly what each model costs in terms of consistency, latency, and operational complexity. The models are not ranked. They are tools. Picking the right tool requires understanding the constraints of the problem.

---

*Next: Chapter 37 covers global load balancing and DNS-based traffic routing — the mechanism that actually steers users to the right region and handles failover at the network layer.*
