# Chapter 83: Chubby — Google's Distributed Lock Service

> "Chubby is not a high-performance lock service. It is a coarse-grained lock service
> designed for availability and reliability at the cost of throughput. It is the
> coordination backbone of almost every distributed system at Google."
> — Mike Burrows, "The Chubby lock service for loosely-coupled distributed systems" (OSDI 2006)

---

## Why This Chapter Matters

Every time an interviewer asks "how does GFS elect its master?" or "how does Bigtable
know which tablet server owns which data range?" — the answer is Chubby. When someone
asks "how do you implement distributed leader election?" the correct L6 answer traces
back to the exact mechanisms Chubby pioneered.

Chubby is the coordination backbone of Google's infrastructure. GFS uses it to elect
the single master. Bigtable uses it for master election and tablet server liveness.
Borg (the predecessor to Kubernetes) uses it for cluster coordination. MapReduce uses
it for job coordination. Nearly every distributed system at Google that needs a "who
is in charge?" answer queries Chubby.

Beyond Google, Chubby directly inspired ZooKeeper (Apache's open-source equivalent),
which in turn influenced etcd (what Kubernetes uses today). Understanding Chubby means
understanding the DNA of modern distributed coordination.

At L5 you say "use ZooKeeper for leader election." At L6 you explain the Paxos-based
session model, why lease duration matters, what sequencer tokens prevent, how ephemeral
nodes enable service discovery, and what happens during a thundering herd event. That
depth is what this chapter builds.

---

## Prerequisites

- Basic understanding that networks can fail (messages get lost, servers crash)
- Rough idea that databases use locks (row-level locking, transactions)
- Familiarity with the terms "master" and "replica" from earlier chapters
- Chapter 22 (Leader Election and Distributed Locks) recommended but not required

---

## Part 1: Why Distributed Locking is Hard — The Coordination Problem

### 1.1 Start With a Simple Story

Imagine you are running a warehouse with 50 workers and one shared computer terminal
where workers submit orders. Two workers cannot submit at the same time — they would
corrupt the order queue. So you put a single physical key next to the terminal. Whoever
holds the key may use the terminal. When they are done, they put the key back.

This works perfectly in a single warehouse. The key is the lock. It is a physical,
indivisible object. You either hold it or you do not.

Now scale up. Your company grows to 50 warehouses across the country, each with its
own terminal, all connected to one shared order-fulfillment system. You still need the
same guarantee: only one warehouse can be the "master submitter" at a time. But you
cannot have a single physical key anymore — it would need to teleport between warehouses.

This is the distributed locking problem. How do you create the equivalent of that
physical key when every participant is separated by a network that can fail, slow down,
or partition?

### 1.2 The Naive Approach: Just Use a Database Row

The first thing most engineers think of: put a row in a database table. Something like:

```
Table: distributed_locks
  lock_name | owner_server | acquired_at
  gfs_master| server-42    | 2024-01-01 10:00:00
```

Server-42 owns the lock if its name is in that row. When it's done, it deletes the row.
To acquire, you do an atomic `INSERT ... WHERE NOT EXISTS`. Simple!

This breaks in at least three important ways.

**Problem 1: What happens when server-42 crashes?**

The row stays in the database forever. The lock is held by a dead server. No one else
can become master. Your entire system is stuck. You need some timeout mechanism —
maybe the lock expires after 30 seconds if not renewed. Now server-42 must continuously
update the `acquired_at` timestamp to prove it is still alive. This is the keepalive
problem, and it introduces a new failure mode: server-42 is alive but temporarily
slow (maybe doing garbage collection), misses its keepalive deadline, and loses the
lock — even though it is still running and believes it holds the lock.

**Problem 2: Two servers both believe they hold the lock**

This is called split-brain. Here is how it happens:

- Server-42 holds the lock and is actively processing requests as master
- The network partitions: server-42 cannot reach the database for 60 seconds
- The database times out the lock and removes server-42's row
- Server-99 acquires the lock and becomes master
- The network heals: server-42 can reach the database again
- Server-42 checks: the row is gone. But it was already processing writes as master!

For those 60 seconds, two servers thought they were master simultaneously. Both wrote
to the GFS namespace. Both issued commands to chunk servers. The data is now corrupted.
This is the most dangerous failure mode in distributed systems.

**Problem 3: The database itself is a single point of failure**

If you use one database server to store your locks, that database server becomes more
critical than anything else. When it is down, no one can acquire or release locks.
You need the lock service to be more reliable than the services it coordinates. So
you need to replicate the lock service — but how do you coordinate which lock service
replica is authoritative? You have a circular dependency.

### 1.3 The Master Election Problem in Detail

Master election is the most common coordination problem. Every distributed system with
a primary/replica architecture needs to answer: which server is currently the primary?

The requirements sound simple but are contradictory in the presence of failures:

**Safety**: Never have two masters simultaneously. One master writing while another
master also writes causes data corruption that may be unrecoverable.

**Liveness**: Always have a master. If the current master dies, a new one should be
elected promptly so the system keeps serving requests.

The tension: to guarantee safety, you need conservative timeouts (assume a server is
dead only after a long time). To guarantee liveness, you need aggressive timeouts
(detect failures quickly and elect a replacement). These pull in opposite directions.

In the real world, "is this server dead?" is a genuinely hard question. A server might
be dead. It might be in a long garbage collection pause. It might be processing a huge
request. It might be experiencing a network partition where it can reach clients but
not the lock service. You cannot distinguish these cases reliably from the outside.

### 1.4 Why a Simple DB Lock Does Not Work (Concrete Example)

Let's trace through a GFS scenario without Chubby.

GFS needs one master at a time to manage the namespace (which files exist, which chunk
servers hold which chunks). Suppose you use a MySQL lock:

```
Time 0:   Server A acquires MySQL lock, becomes GFS master
Time 10s: Server A heartbeats MySQL to keep lock alive
Time 20s: Server A heartbeats MySQL
Time 30s: Server A is doing a large directory scan, skips heartbeat
Time 35s: MySQL expires the lock (30s timeout)
Time 36s: Server B acquires MySQL lock, becomes GFS master
Time 36s: Server B starts issuing commands: "chunk server 7, replicate chunk X"
Time 37s: Server A finishes its scan, does a heartbeat — fails! A knows it lost lock
Time 37s: BUT: what did A do between time 35 and 37? 2 seconds of dual-master!
```

Two seconds sounds short. But GFS master operations happen in milliseconds. In two
seconds, Server A might have issued hundreds of conflicting commands. The chunk servers
got instructions from two different masters and are now in an inconsistent state.

Chubby's sequencer token mechanism (covered in Part 5) is specifically designed to
prevent this scenario even when the lock service itself has timing uncertainty.

### 1.5 The Three Properties Any Lock Service Must Have

After thinking through these failure modes, the requirements crystallize:

**1. Fault-tolerant consensus**: The lock service must itself be replicated and use
a consensus protocol (like Paxos or Raft) so that losing one replica does not lose
the lock state. The lock service must be more reliable than the systems it serves.

**2. Session-based liveness detection**: Clients must continuously prove they are
alive (keepalives). If a client fails to prove liveness within a deadline, its locks
are automatically released. This prevents dead servers from holding locks forever.

**3. Fencing tokens**: Even with keepalives, there will be edge cases where a client
believes it holds a lock but the lock service has already given the lock to someone
else. A sequencer token (a monotonically increasing number) lets downstream services
reject stale commands from the old lock holder even when both are running.

These three properties define Chubby's design.

---

### Part 1 Brainstorming Questions

**Q: Why can't you just use a single Redis instance as a lock service?**

A single Redis instance is a single point of failure. If Redis crashes, all your locks
are lost and all your services that depend on locks cannot acquire new ones. More
subtly, Redis uses asynchronous replication, which means that if the Redis primary
crashes right after a lock is acquired but before the replica learns about it, the
replica will not know the lock was acquired and will issue it to someone else. This
is the split-brain scenario that distributed lock services specifically exist to prevent.

Redis Cluster and RedLock (Distributed Redis Lock) attempt to solve this, but RedLock
has well-documented design flaws (see Martin Kleppmann's critique): it relies on
synchronized clocks across machines, which are never perfectly reliable. Chubby avoids
clock synchronization assumptions by using Paxos-based consensus and lease-based timing
that is conservative about liveness.

The right mental model: Redis is excellent for high-throughput, low-latency operations
where occasional inconsistency is tolerable (caching, rate limiting). It is not the
right tool for coordination primitives where correctness is mandatory. Chubby optimizes
for correctness at the cost of throughput, which is the opposite tradeoff.

**Q: What is split-brain and why is it so dangerous?**

Split-brain occurs when two nodes in a distributed system both believe they are the
authoritative master simultaneously. It typically happens when there is a network
partition: Node A cannot communicate with the lock service, the lock service times
out A's lock and gives it to Node B, but A does not know this and keeps acting as
master. When the partition heals, both A and B have been acting as master.

The danger is data corruption. In a database context, A might have written records
1-100 and B might have written records 95-150 during the overlap. These records now
conflict. In a GFS context, A might have told chunk servers to delete files while B
told them to replicate those files. There is no automatic way to reconcile this.
The data may be irrecoverably corrupted and require manual intervention.

The fencing token (sequencer) is the key defense. Even if split-brain occurs at the
lock service level, downstream services can reject commands from the stale master
(A) because A's sequencer token is lower than B's. This limits the damage window,
but you still need careful application design to make this work.

**Q: What is the difference between distributed locking and distributed transactions?**

Distributed locking is simpler and narrower. A lock is a binary state: held or not held.
You acquire it before doing something and release it after. The lock service does not
know or care what you are doing while holding the lock.

A distributed transaction is broader. It ensures that a set of operations across
multiple resources either all commit or all abort, atomically. Transactions require
a two-phase commit protocol (or equivalent) and a transaction coordinator. They are
much more complex and much slower than locks.

Chubby provides locking, not transactions. It is intentionally narrow: it answers
"who is allowed to act as master right now?" but does not coordinate the master's
actual work. The master uses Chubby to prove its authority, then uses its own
mechanisms (like GFS's own consistency protocol) to do the work safely.

---

## Part 2: Chubby's Design Philosophy — Coarse-Grained Locking

### 2.1 The Central Design Decision: Coarse vs. Fine Grained

This is the most important design decision in Chubby, and it is the one most candidates
misunderstand in interviews.

**Fine-grained locking** means locking individual data items. In a database, this is
row-level locking: lock row 42 while updating it, release immediately. Locks are held
for milliseconds or microseconds. You might have thousands of lock acquisitions per
second. This is the normal database transaction model.

**Coarse-grained locking** means locking large resources for long periods. Lock "the
GFS master role" for hours or days. Lock "the Bigtable master role" for the entire
time the master is running. You might have one lock acquisition per hour, or per day.

Chubby is explicitly designed for coarse-grained locking. The paper states: "Chubby
is not intended to be used as a high-performance lock service." This is not a bug.
It is a deliberate choice based on how Google actually needed coordination.

### 2.2 Why Coarse-Grained Locking?

Think about what Google actually needs coordination for:

- GFS needs exactly one master server (elected once, runs for hours or days)
- Bigtable needs exactly one master tablet controller (elected once, runs for hours)
- MapReduce needs exactly one job coordinator per job (held for duration of job)
- Configuration files need to be stored somewhere authoritative

None of these are row-level locking scenarios. These are "elect a leader and keep
them elected" scenarios. The lock is held for the lifetime of a process, not the
duration of a database write.

This changes the performance requirements entirely. If a lock is held for hours,
acquiring it once per hour, you do not need microsecond lock acquisition times.
You need the lock acquisition to be correct and the lock state to be durable.
Chubby optimizes heavily for correctness and availability, and explicitly trades
away throughput and latency.

### 2.3 Advisory Locks vs. Mandatory Locks

Chubby uses advisory locks, not mandatory locks. This distinction is subtle but important.

**Mandatory lock**: The system enforces the lock. If Server A holds the lock, the
system literally prevents Server B from accessing the protected resource. The lock is
enforced by the infrastructure.

**Advisory lock**: The lock is a signal that clients voluntarily respect. Chubby tells
you "Server A holds the lock." It is up to Server B to check with Chubby before
acting. Nothing stops a misbehaving Server B from ignoring the lock and acting anyway.

This sounds like a weakness, but it is actually a pragmatic design choice. Mandatory
locks require the lock service to intercept every access to the protected resource.
For something like "who is the GFS master?" — the lock service would need to intercept
every GFS read and write, which would make it a bottleneck for all GFS traffic. That
is not acceptable.

Instead, Chubby provides a reliable answer to "who is the current master?" and trusts
that well-designed clients check this before acting. The sequencer token (Part 5)
provides a way for third parties (like chunk servers) to verify that a command comes
from the current legitimate master, which closes the most dangerous gaps in advisory
locking.

### 2.4 Reliability Over Performance

Chubby is replicated 5 ways and uses Paxos consensus for all writes. This is expensive.
Every lock acquisition requires a Paxos round, which means multiple round trips across
multiple servers. The latency is measured in tens of milliseconds, not microseconds.

Google made this trade-off deliberately. For coarse-grained locking, where you acquire
a lock once and hold it for hours, tens of milliseconds of acquisition latency is
completely acceptable. What is not acceptable is losing lock state because a replica
crashed, or having two replicas disagree about who holds a lock.

Paxos guarantees that even if 2 of the 5 replicas crash simultaneously, the remaining
3 continue to operate correctly and consistently. No lock state is lost. No two
replicas disagree about who holds the current lock. This level of consistency cannot
be achieved without a consensus protocol.

### 2.5 Small Metadata, Not Large Data

Chubby stores small amounts of data: lock state, small configuration files, small
metadata files. The paper recommends keeping files under 256KB. It is not designed
for storing bulk data like GFS chunks.

Think of Chubby as the coordination layer — it stores metadata about your system
(who is the master, what are the current cluster members, what is the current
configuration). The actual data lives in GFS or Bigtable, which uses Chubby only
for coordination.

---

### Part 2 Brainstorming Questions

**Q: If Chubby has high latency, won't it slow down master election during a failure?**

Yes, but it is an acceptable trade-off because master election is not on the critical
path of normal operation. When a GFS master fails, there is already an outage. Taking
an extra 100ms to elect a new master (via Paxos) does not meaningfully worsen an
outage that will be seconds long anyway. The alternative — using a faster but less
correct lock service — risks making the election wrong, which would cause data
corruption far more damaging than a slower recovery.

The Chubby paper describes this explicitly: the engineers made the conscious choice
that it is better to be slow and correct than fast and wrong. For the specific use
case of coordinating master election in large-scale distributed systems, this is
absolutely the right call.

**Q: Why not just use advisory locks everywhere and skip Chubby entirely?**

Without a shared, authoritative source of lock state, you have no way to resolve
disagreements. "Advisory" does not mean "anyone can ignore it." It means "we trust
well-behaved clients to respect it, and the sequencer mechanism catches misbehaving
ones." You still need the lock service to maintain the definitive state.

Consider the alternative: each service keeps its own notion of who is master, and
they gossip to share this information. Gossip is eventually consistent, not immediately
consistent. During the convergence period, different parts of the cluster might believe
different servers are master. Chubby's consensus-based approach means every client
sees the same lock state (with the fencing mechanism handling the edge cases).

**Q: What makes Chubby different from a high-availability database?**

A high-availability database (like MySQL with Paxos replication, or CockroachDB) also
uses consensus and stores persistent state. The key differences are:

First, Chubby's primary abstraction is the lock and session, not the transaction.
The session model — where a client's locks are automatically released if the client
stops sending keepalives — is not a standard database feature. This is essential for
the liveness detection that distributed coordination requires.

Second, Chubby is designed for a specific access pattern: infrequent writes (lock
acquisitions/releases), frequent reads (who holds this lock?), and event notifications
(tell me when this lock is released). Databases optimize for different patterns.

Third, Chubby's file-system API with event notifications enables the service discovery
and leader election patterns that Google relies on. A general-purpose database does
not provide "notify me when this row changes" as a first-class primitive with the
session semantics Chubby requires.

---

## Part 3: The Chubby Cell Architecture

### 3.1 What Is a Chubby Cell?

A Chubby cell is a small cluster of machines — typically five — that collectively
run the Chubby lock service for a datacenter. These five machines run Paxos consensus
to agree on the state of all locks and files. Together, they act as one highly
reliable lock server.

The analogy: imagine a jury of five people who must reach a consensus before making
any decision. Even if one or two jurors are temporarily unreachable, the remaining
majority can still reach a verdict. The Chubby cell works exactly this way.

The number five is not arbitrary. With five replicas, the system tolerates two
simultaneous failures. Paxos requires a majority quorum — (N/2)+1 nodes must agree.
With five nodes, that quorum is three. So two nodes can crash, and the three remaining
nodes can still operate. With only three replicas, you can only tolerate one failure,
which is often not enough. Seven replicas is overkill (tolerates three failures, but
adds latency and cost for marginal benefit).

### 3.2 The Paxos Master Election Within the Cell

Wait — Chubby helps other services elect masters. But how does Chubby itself elect
its internal master? It uses Paxos.

Paxos is a consensus algorithm. Let's explain it concretely rather than mathematically.

Imagine five friends are trying to agree on where to eat dinner. The Paxos protocol
works like this:

**Phase 1 (Prepare)**: One friend (the "proposer") sends a message to all others:
"I want to propose a restaurant. Will you promise to listen to my proposal?"
Each friend responds: "Yes, I promise, and here is the last proposal I heard."

**Phase 2 (Accept)**: The proposer picks a restaurant (taking into account any
previous proposals they learned about), then sends: "I propose we go to Olive Garden.
Please accept this." If a majority of friends accept, the decision is made.

In Chubby's case, the "restaurant" is "which server is the master of this cell?"
The five Chubby replicas run Paxos to elect one of themselves as the master. The
elected master handles all client requests. The other four replicas are passive backups
that receive updates via Paxos to stay in sync.

### 3.3 Master Leases

After Paxos elects a master, the master does not run Paxos for every single read
request. That would be very slow. Instead, the master acquires a "master lease" —
a time-bounded promise from the other replicas.

Think of it like a parking permit. The city (Paxos consensus) grants you a permit
to park for 2 hours. For those 2 hours, you do not need to check in with city hall
for every read operation — you just park. When the 2 hours expire, you must either
renew the permit (run Paxos again) or leave.

Chubby's master lease works the same way. The master holds a lease for a period
(typically 12 seconds for client sessions, shorter for internal lease). During the
lease, the master can serve read requests from memory without running Paxos. Paxos
is only required for writes (lock acquisitions, lock releases, file writes).

The safety guarantee: if the master is serving reads under its lease, no other node
can have been elected master during the lease period. Why? Because electing a new
master requires a Paxos majority, and the replicas will not participate in a new
election until the current lease expires. So the current master is guaranteed to have
fresh data — no newer master has written anything.

### 3.4 Cell Architecture ASCII Diagram

```
                        CHUBBY CELL (1 Datacenter)
                        ===========================

  Clients (GFS master, Bigtable master, etc.)
     |         |         |         |
     |   RPC   |         |         |
     v         v         v         v
  +------------------------------------------+
  |          CHUBBY CLIENT LIBRARY           |
  |  - Caches lock state locally             |
  |  - Handles session keepalives            |
  |  - Delivers event notifications          |
  +------------------------------------------+
           |                    |
           | (1 connection       |
           |  to master)        |
           v                    v
  +----------------+    +----------------+
  |  REPLICA 1     |    |  REPLICA 2     |
  |  (MASTER)      |    |  (follower)    |
  |                |    |                |
  |  Paxos logs    |    |  Paxos logs    |
  |  Lock state DB |    |  Lock state DB |
  |  File storage  |    |  File storage  |
  +----------------+    +----------------+
         |  \                  |
   Paxos |   \-----------+     |
   repl  |               |     |
         v               v     v
  +----------------+    +----------------+   +----------------+
  |  REPLICA 3     |    |  REPLICA 4     |   |  REPLICA 5     |
  |  (follower)    |    |  (follower)    |   |  (follower)    |
  |                |    |                |   |                |
  |  Paxos logs    |    |  Paxos logs    |   |  Paxos logs    |
  |  Lock state DB |    |  Lock state DB |   |  Lock state DB |
  +----------------+    +----------------+   +----------------+

  WRITE OPERATION:
  Client → Master → Paxos round (need 3 of 5 to agree) → Success to Client

  READ OPERATION:
  Client → Master → Master serves from local state (if within lease) → Client

  MASTER FAILURE:
  Replicas detect timeout → Run Paxos election → New master elected
  Old clients reconnect to new master via DNS lookup
```

### 3.5 DNS Registration and Client Discovery

How do Chubby clients find the current master? The Chubby cell registers itself
in DNS. The DNS entry for a Chubby cell (like `chubby-cell-1.datacenter1.google.com`)
points to the current master. When the master changes (due to failure and re-election),
the DNS record is updated.

Chubby clients resolve the DNS name, connect to the master, and start their session.
If they lose connection and cannot reach the master, they wait briefly and then
re-resolve DNS to find the new master. The client library handles this transparently.

There is a subtlety here: DNS TTL (time to live) must be short enough that clients
pick up master changes quickly. Google sets these TTLs very short, typically 30-60
seconds, to ensure quick failover.

### 3.6 What Happens During Master Failover

1. The master replica crashes
2. The other four replicas detect the master is unreachable (they stop receiving heartbeats)
3. After a timeout, the replicas run Paxos to elect a new master from the remaining four
4. The new master runs Paxos to establish its leadership with a majority
5. The new master updates the DNS record to point to itself
6. The new master reads the last committed state from the Paxos log to reconstruct lock state
7. Connected clients see their RPC connection fail (master is dead)
8. Clients re-resolve DNS, connect to the new master
9. The new master restores client sessions (clients send a "reopen" request)

The window of unavailability is typically a few seconds. During this window, lock
service is unavailable but lock state is preserved (nothing is lost, just temporarily
inaccessible). Services that depend on Chubby must be designed to tolerate brief
unavailability during master failover.

---

### Part 3 Brainstorming Questions

**Q: What happens to client sessions during a Chubby master failover?**

Client sessions are preserved across master failover, but there is a brief disruption.
When the old master crashes, clients notice their RPC connections drop. The client
library enters a grace period (the "jeopardy" state, covered in detail in Part 7)
where it waits rather than immediately treating its locks as released. During this
grace period, the client library tries to reconnect — first retrying the old master
address, then re-resolving DNS to find the new master.

When the client reconnects to the new master, it sends a "session reopen" message
proving its identity and the last sequence number it saw. The new master can then
reconstruct whether the client's session is still valid (it has not been expired
during the failover). If the session is still within its lease, the master confirms
it and the client continues holding its locks. If the client took too long to reconnect
and the session expired, the master notifies the client that its locks have been released.

**Q: Why use five replicas instead of three?**

Three replicas tolerate one failure. That might seem sufficient, but in a datacenter
context, failures are correlated. Hardware batches fail together. Network switches
fail in groups. If you are using three replicas and you lose two simultaneously (which
is not uncommon during maintenance, power events, or rolling updates), you lose
quorum. With five replicas, you can lose two simultaneously and still have a quorum
of three. This extra fault tolerance is worth the cost of two additional servers for
a service as critical as the coordination backbone.

There is also an operational consideration: rolling updates. When you update the
Chubby software, you take replicas down one at a time. With three replicas, taking
one down for update leaves you with two replicas — exactly quorum, which means any
failure during the update window is catastrophic. With five replicas, taking one down
leaves four, so you can tolerate one additional failure during maintenance.

**Q: Can a Chubby cell span multiple datacenters for geo-redundancy?**

Chubby cells are typically within a single datacenter. For a cell that spans
datacenters, round-trip latency between replicas becomes a problem. Paxos requires
a majority to acknowledge writes before they are committed. If replicas are in two
different datacenters 50ms apart, every write takes 50ms minimum (one cross-datacenter
round trip). For a lock service, this makes acquisitions painfully slow.

Google's approach is to have one Chubby cell per datacenter. The cell is very reliable
within the datacenter (five replicas, tolerates two failures). For cross-datacenter
coordination, Google's systems are typically designed to operate independently within
each datacenter and use a separate mechanism (like global Spanner transactions) for
cross-datacenter coordination where needed. Chubby stays local to minimize latency.

---

## Part 4: The File System API — Locks, Files, and Nodes

### 4.1 Why a File System API?

Chubby exposes a file system-like API: files, directories, paths. This seems like
an odd choice for a lock service. Why not just have `AcquireLock(name)` and
`ReleaseLock(name)`?

The answer is that the file system API gives you three things in one:

1. **A namespace**: File paths like `/ls/gfs-cell/master` create a natural hierarchy
   for organizing locks and data. (`ls` stands for "lock service.")

2. **Small data storage**: Files can store content. A lock file might contain the
   network address of the current master, so clients can look up both "who is master"
   and "how do I reach them" in one place.

3. **Event notifications**: You can watch a file or directory for changes. When a
   lock is released (file changes state), all watchers are notified. This is more
   efficient than polling.

The file system API is not trying to be a general-purpose file system. It is a thin
abstraction that packages these three related needs into a familiar interface.

### 4.2 The Namespace Structure

Chubby's namespace looks like:

```
/ls/                          (root, always present)
  chubby-cell-name/           (cell identifier)
    gfs/
      master                  (the GFS master lock file)
      chunk-server-42         (ephemeral: chunk server 42 is alive)
      chunk-server-17         (ephemeral: chunk server 17 is alive)
    bigtable/
      master                  (the Bigtable master lock file)
      tablet-server-001       (ephemeral: tablet server 001 is alive)
    my-service/
      config                  (permanent: configuration file)
      leader                  (lock: who is the service leader)
```

The path `/ls/my-cell/gfs/master` is a node in this hierarchy. It can be a lock
(held by the current GFS master), a file (containing the master's address), or both.

### 4.3 Nodes: The Fundamental Primitive

Every path in Chubby's namespace is a "node." Nodes come in two varieties:

**Permanent nodes**: Exist until explicitly deleted. Even if the client that created
them disconnects, permanent nodes persist. Used for configuration files and locks
that should outlast any individual client session.

**Ephemeral nodes**: Exist only as long as the creating client's session is open.
When the client's session ends (either intentionally or because the client died
and the session timed out), the ephemeral node is automatically deleted. Used for
service discovery — a server creates an ephemeral node to say "I am alive," and
when the server crashes, the node vanishes automatically, telling other services
"that server is gone."

### 4.4 Operations on Nodes

The Chubby API provides these operations on nodes:

| Operation | Description |
|-----------|-------------|
| `Open(path, flags)` | Open a handle to a node (creates it if CREATE flag set) |
| `Close(handle)` | Release a handle to a node |
| `Delete(handle)` | Delete a node |
| `Acquire(handle, mode)` | Acquire a lock on a node (SHARED or EXCLUSIVE) |
| `TryAcquire(handle, mode)` | Acquire a lock, return immediately if unavailable |
| `Release(handle)` | Release a lock on a node |
| `GetContentsAndStat(handle)` | Read file contents and metadata |
| `SetContents(handle, data)` | Write file contents |
| `GetACL(handle)` | Read access control list |
| `SetACL(handle, acl)` | Write access control list |
| `GetSequencer(handle)` | Get a sequencer token for the current lock |
| `SetSequencer(handle, seq)` | Check that a sequencer token is still valid |

### 4.5 Lock Modes: Shared and Exclusive

Chubby supports two lock modes, just like read/write locks in regular programming:

**Exclusive lock (write lock)**: Only one client can hold this at a time. Used for
master election — only one server can be master.

**Shared lock (read lock)**: Multiple clients can hold this simultaneously. Used
for read-only access where concurrent readers are safe. For example, multiple clients
might hold a shared lock on a configuration file to indicate "I am currently reading
this config." A writer acquires the exclusive lock to update the config, and must
wait until all readers release their shared locks.

In practice, Chubby's most common use case is exclusive lock for master election,
and shared lock usage is less common.

### 4.6 Event Notifications

Clients can subscribe to events on nodes. When a subscribed event occurs, Chubby
notifies all subscribed clients asynchronously. This is the mechanism by which services
learn about changes without polling.

Event types include:

| Event | Triggered When |
|-------|----------------|
| `FILE_CONTENTS_MODIFIED` | The file's content changed |
| `CHILD_NODE_ADDED` | A new child was created in this directory |
| `CHILD_NODE_REMOVED` | A child was deleted from this directory |
| `CHILD_NODE_MODIFIED` | A child node's metadata changed |
| `HANDLE_INVALID` | The client's handle is no longer valid |
| `LOCK_ACQUIRED` | A lock the client was waiting for has been acquired |
| `CONFLICTING_LOCK` | Someone is requesting a lock this client holds |

The most commonly used event in master election is `CHILD_NODE_REMOVED` on a directory.
When a master's ephemeral node vanishes (because the master crashed), all watchers of
the directory receive this notification and know to attempt a new election.

### 4.7 Access Control Lists

Chubby uses simple ACLs (access control lists) to control who can read, write, and
lock files. ACLs are stored in special ACL files within the Chubby namespace itself.

This is elegant: you use Chubby to store the permissions for Chubby. The ACL files
are just regular Chubby files, which means they can be updated via normal Chubby
writes and protected by their own ACLs. A slight chicken-and-egg problem is avoided
by having the root ACL be world-readable and controlled by Chubby administrators.

---

### Part 4 Brainstorming Questions

**Q: Why store file contents in a lock service? Isn't that scope creep?**

The ability to store small file contents in Chubby is deliberate and extremely useful.
The pattern that emerges in practice is: the client acquires the lock file, then
writes its contact information (IP address, port, protocol version) into the lock
file. Now other clients can look up both "who is the current master?" and "how do
I connect to them?" in a single Chubby read. Without file contents, you would need
a separate lookup mechanism (like DNS or another configuration store) to find the
master's address, which adds complexity and another potential point of failure.

The Chubby paper is explicit that small file storage (under 256KB) is intentional.
Large file storage would require distributed block storage (like GFS), which is a
completely different problem. Chubby deliberately stays small and focused.

**Q: How do event notifications get delivered to clients that are temporarily disconnected?**

Event delivery in Chubby is not guaranteed in the same way as lock state. If a client
is temporarily disconnected and misses events during the disconnection, the client
will not receive those missed events after reconnecting. Instead, the client receives
a special "events may have been missed" notification on reconnection.

This forces clients to re-read the state of anything they care about after reconnecting,
rather than relying on having seen every event. This is the right design: event
notifications are an optimization (avoiding polling), but the client must always be
prepared to re-read state. Reliable event delivery would require complex queueing and
exactly-once semantics, which would complicate the system enormously. The "re-read
after reconnect" approach is simpler and correct.

**Q: What is the difference between a Chubby node and a file in a regular file system?**

Several important differences. First, Chubby nodes are much smaller (256KB limit vs.
gigabytes for regular files) because Chubby stores state in memory and in a replicated
database, not on a local disk filesystem.

Second, Chubby nodes have additional metadata related to locking: the lock state,
the lock mode (shared/exclusive), the lock holder's session ID, and the lock sequence
number. Regular filesystem files have no concept of distributed locks.

Third, Chubby nodes have session-aware behavior: ephemeral nodes are tied to client
sessions. Regular filesystem files persist regardless of which process created them.

Fourth, Chubby nodes participate in the consensus protocol: every write to a Chubby
node goes through Paxos. Regular filesystem writes go to a local disk (or at most
a simple replicated filesystem, not a consensus protocol).

---

## Part 5: Lock Acquisition Step by Step — The Sequencer Token

### 5.1 The Lock Acquisition Flow

Let's trace through a complete lock acquisition from a client's perspective, step by
step. The scenario: a GFS candidate master server is trying to acquire the GFS master
lock.

```
GFS CANDIDATE MASTER LOCK ACQUISITION
======================================

Step 1: Open the lock file
  Client → Chubby master: Open("/ls/my-cell/gfs/master", READ|WRITE|LOCK)
  Chubby master → Client: Handle H1 (success)

Step 2: Attempt to acquire the lock
  Client → Chubby master: Acquire(H1, EXCLUSIVE)
  
  If lock is free:
    Chubby master runs Paxos round:
    [Master → Replicas: "Client session S42 now holds lock on /gfs/master"]
    [Majority acknowledges]
    Chubby master → Client: Lock acquired! Sequence number = 47

  If lock is held by another client:
    Chubby master → Client: Lock busy, queued.
    Client blocks, waiting for notification.

Step 3: Client registers for notifications
  Client → Chubby master: Subscribe to FILE_CONTENTS_MODIFIED on H1
  (So client knows if the lock state changes)

Step 4: Client writes its address to the file
  Client → Chubby master: SetContents(H1, "server-42:7001")
  (Other clients can now find the master's address)

Step 5: Client starts keepalive loop
  Client → Chubby master: KeepAlive(session=S42)
  Chubby master → Client: OK, lease extended to T+12s
  (Client must repeat this before the lease expires)
```

### 5.2 The Sequencer Token: The Key to Safety

The sequencer token is the most important safety mechanism in Chubby, and the one
most often overlooked in interview discussions.

Here is the problem it solves. Imagine:

1. Server A acquires the GFS master lock. Its lock sequence number is 47.
2. Server A starts acting as GFS master, sending commands to chunk servers.
3. Server A's network connection to Chubby becomes slow. It misses a keepalive.
4. Chubby expires A's session. Lock sequence 47 is revoked.
5. Server B acquires the GFS master lock. Its lock sequence number is 48.
6. Server B starts sending commands to chunk servers.
7. Server A's network recovers. It sends old commands to chunk servers.

Now chunk servers are receiving commands from both A (with sequence 47) and B
(with sequence 48). Without the sequencer, they have no way to know that A's
authority has been revoked.

**The sequencer is the solution.**

When Server A acquired the lock, it received a sequencer token: `(lock_name="/gfs/master", mode=EXCLUSIVE, sequence=47)`. This token is signed/verified by Chubby.

Server A includes this sequencer token in every command it sends to chunk servers.
The chunk servers, before executing any command, call Chubby to verify: "Is sequencer
47 for /gfs/master still valid?"

When Server A's lock is revoked and B gets sequence 48, Chubby will respond to
chunk server verifications: "Sequencer 47 for /gfs/master is no longer valid."
The chunk server rejects A's old command. Server A's stale commands are fenced out.

### 5.3 The Sequencer Verification Flow

```
SEQUENCER VERIFICATION FLOW
============================

Server A (current master, sequence=47):
  A → Chunk Server 7: "Replicate chunk X to server 3. My sequencer: (master, EX, 47)"
  Chunk Server 7 → Chubby: "Is sequencer (master, EX, 47) still valid?"
  Chubby → Chunk Server 7: "Yes, valid."
  Chunk Server 7 → Chunk Server 3: [Starts replication]

[Suppose A loses keepalive, lock is revoked, B gets sequence 48]

Server A (STALE, sequence=47):
  A → Chunk Server 9: "Delete chunk Y. My sequencer: (master, EX, 47)"
  Chunk Server 9 → Chubby: "Is sequencer (master, EX, 47) still valid?"
  Chubby → Chunk Server 9: "No. Sequence 47 is revoked. Current sequence is 48."
  Chunk Server 9 → A: "Rejected. Your authority has been revoked."
  [A's stale delete command is safely ignored]

Server B (new master, sequence=48):
  B → Chunk Server 9: "Delete chunk Y. My sequencer: (master, EX, 48)"
  Chunk Server 9 → Chubby: "Is sequencer (master, EX, 48) still valid?"
  Chubby → Chunk Server 9: "Yes, valid."
  Chunk Server 9 executes the delete.
```

### 5.4 Lock Delay: A Safety Buffer

There is a subtle race condition in the basic lock model. When Server A's session
expires, Chubby revokes its lock. But between the moment Chubby decides A's session
has expired and the moment all chunk servers know about this, there is a window where:

- Chunk servers haven't yet verified that A's sequencer is invalid
- A is still sending commands (it doesn't know its session expired yet)
- B has been given the lock

During this window, both A's commands (with old sequencer 47) and B's commands
(with new sequencer 48) are in flight to chunk servers.

Chubby handles this with a "lock delay" — a brief period (default: a few seconds)
after a lock is released before it can be given to another client. During this lock
delay:

- A's sequencer (47) is invalidated immediately (so verifications will fail)
- B cannot acquire the lock yet (it must wait for lock delay to pass)
- After lock delay expires, B acquires the lock with sequencer 48

This ensures that when B starts sending commands, all of A's in-flight commands
have already been rejected by the sequencer check. There is no overlap window.

### 5.5 The Lock Acquisition Flow with All Pieces

```
COMPLETE LOCK ACQUISITION AND RELEASE LIFECYCLE
================================================

Phase 1: Client A acquires lock
  ┌─────────────────────────────────────────────────────────┐
  │  A → Chubby: Acquire("/gfs/master", EXCLUSIVE)          │
  │  Chubby runs Paxos, records A holds lock, seq=47        │
  │  Chubby → A: Acquired! Sequencer token: (master,EX,47)  │
  └─────────────────────────────────────────────────────────┘

Phase 2: A acts as master, includes sequencer in commands
  ┌─────────────────────────────────────────────────────────┐
  │  A → ChunkServer: "Command X". Token: (master,EX,47)    │
  │  ChunkServer → Chubby: "Verify (master,EX,47)"          │
  │  Chubby → ChunkServer: "Valid."                         │
  │  ChunkServer executes command X.                        │
  └─────────────────────────────────────────────────────────┘

Phase 3: A's session expires (missed keepalives)
  ┌─────────────────────────────────────────────────────────┐
  │  Chubby: A's session timed out. Revoke seq=47.          │
  │  Chubby: Lock delay begins (e.g., 2 seconds)            │
  │  Any verification of (master,EX,47) → INVALID           │
  └─────────────────────────────────────────────────────────┘

Phase 4: Lock delay expires, B acquires lock
  ┌─────────────────────────────────────────────────────────┐
  │  B → Chubby: Acquire("/gfs/master", EXCLUSIVE)          │
  │  Chubby runs Paxos, records B holds lock, seq=48        │
  │  Chubby → B: Acquired! Sequencer token: (master,EX,48)  │
  └─────────────────────────────────────────────────────────┘

Phase 5: A's stale commands are rejected
  ┌─────────────────────────────────────────────────────────┐
  │  A → ChunkServer: "Command Y". Token: (master,EX,47)    │
  │  ChunkServer → Chubby: "Verify (master,EX,47)"          │
  │  Chubby → ChunkServer: "INVALID. Current seq=48."       │
  │  ChunkServer → A: "Rejected."                           │
  └─────────────────────────────────────────────────────────┘
```

### 5.6 The 5-Level Intern-to-Staff Progression

**Intern level**: "A lock prevents two things from happening at once. Like a mutex
in programming."

**Junior (L3) level**: "Chubby gives out distributed locks. You call Acquire() and
it gives you exclusive access to a resource. You call Release() when done."

**Mid-level (L4) level**: "Chubby uses Paxos to replicate lock state across five
servers. Clients do keepalives to prove they're alive. If a client crashes, Chubby
expires the session and releases its locks after a timeout."

**Senior (L5) level**: "The sequencer token is critical. It is a monotonically
increasing number tied to each lock acquisition. Even if a client thinks it holds
the lock but the session has actually expired, downstream services verify the
sequencer and reject stale commands. This prevents the split-brain scenario where
a stale master's commands are executed after a new master has taken over."

**Staff (L6) level**: "The sequencer interacts with the lock delay to provide a
complete safety guarantee. When a session expires, Chubby immediately invalidates the
sequencer (so new verifications fail instantly) but delays granting the lock to
a new client by the lock-delay period. This gap ensures all in-flight commands from
the old master have been verified (and rejected) before the new master's sequencer
is issued. The sequencer number is monotonic within a lock's lifetime, so a new
acquisition always gets a strictly higher number, making stale commands trivially
detectable. The system is safe even in the presence of Byzantine delays and clock
skew, because the safety property relies only on sequencer ordering, not on wall
clock time."

---

### Part 5 Brainstorming Questions

**Q: Can a client cache its sequencer to avoid verifying with Chubby on every command?**

Yes, and in practice this caching is essential for performance. If every chunk server
operation requires a Chubby round-trip to verify the sequencer, Chubby becomes a
bottleneck for all GFS traffic. Instead, chunk servers cache valid sequencer tokens
locally. The cache entry expires after a short period (a few seconds), after which
the chunk server re-verifies with Chubby.

This introduces a window of stale cache, but the window is bounded. If a sequencer
is revoked, chunk servers that cached it will continue accepting commands for at most
the cache TTL (time to live). By setting the cache TTL shorter than the lock delay,
you ensure that all chunk server caches expire before the new master starts issuing
commands. The safety guarantee is preserved, with much better performance.

**Q: What happens if Chubby itself is unavailable during a sequencer check?**

Chunk servers face a choice: reject the command (conservative) or accept it
(optimistic). Chubby's recommendation is to reject if the verification cannot be
completed within a reasonable time. This is the conservative choice: it is better
to temporarily stop processing commands (causing a brief unavailability) than to
accept potentially stale commands (causing correctness violations).

In practice, well-designed chunk servers cache recent successful verifications.
If Chubby becomes temporarily unavailable, recent commands with recently-verified
sequencers are still accepted (from cache). Only completely new sequencers or expired
cache entries require a live Chubby verification. This balances safety and availability.

**Q: What is the difference between the sequencer token and a simple version number
on the resource?**

A version number on the resource is an optimistic concurrency control mechanism.
You read the version, do your work, then write only if the version has not changed.
This requires the resource store to enforce the version check, and it fails if two
writers get the same version simultaneously.

The sequencer token is different in two ways. First, it is issued by the lock service,
not the resource. The lock service is the authoritative source of who has authority,
and the sequencer proves lock authority was granted by the authoritative service.
A version number does not prove lock authority.

Second, the sequencer is verified by the resource (chunk server) via a real-time
check with the lock service, rather than a compare-and-swap on stored state. This
means the chunk server does not need to store version numbers — it just asks Chubby
"is this sequencer still valid?" The locking logic stays in Chubby; the resources
stay simple.

---

## Part 6: Ephemeral Nodes — The Service Discovery Mechanism

### 6.1 What Are Ephemeral Nodes?

An ephemeral node is a Chubby node (file or directory) that exists only as long as
the client session that created it. When the session ends — either because the client
explicitly closed it, or because the client died and the session timed out — the
ephemeral node is automatically deleted.

The word "ephemeral" means "short-lived" or "temporary." These nodes are temporary
by design. They are the distributed equivalent of a process's temporary files: they
exist while the process is running and are cleaned up when it exits.

### 6.2 The Service Discovery Pattern

Ephemeral nodes enable a powerful service discovery pattern that Google uses
extensively:

**Registration**: When a server starts up, it creates an ephemeral node in a well-known
Chubby directory. For example, a GFS chunk server might create the node:
`/ls/my-cell/gfs/chunk-servers/server-42`

The node might contain the server's address and capabilities as its file content.

**Discovery**: Any client that wants to know which chunk servers are currently alive
simply lists the directory `/ls/my-cell/gfs/chunk-servers/`. The nodes present in
that directory are exactly the currently-alive chunk servers. The nodes are not stale:
if a chunk server crashes, its session expires, and its ephemeral node vanishes.

**Change notification**: Clients subscribe to `CHILD_NODE_ADDED` and
`CHILD_NODE_REMOVED` events on the directory. They are notified whenever a server
joins or leaves, without polling.

This pattern replaces a much more complex system: previously, you would need a
separate mechanism to register servers, detect failures (via heartbeats), and
deregister dead servers. With Chubby ephemeral nodes, all of this is handled by
the session mechanism.

### 6.3 Ephemeral Node Lifecycle Diagram

```
EPHEMERAL NODE LIFECYCLE
=========================

Server-42 starts up:
  ┌─────────────────────────────────────────────────────────┐
  │  Server-42 → Chubby: Create session S-42                │
  │  Server-42 → Chubby: Create ephemeral node              │
  │               /gfs/chunk-servers/server-42              │
  │               with content: "192.168.1.42:7001"         │
  │  Chubby records: node exists, tied to session S-42      │
  └─────────────────────────────────────────────────────────┘

Normal operation (clients can discover server-42):
  ┌─────────────────────────────────────────────────────────┐
  │  Client → Chubby: List /gfs/chunk-servers/              │
  │  Chubby → Client: [server-41, server-42, server-43, ...] │
  │                                                         │
  │  Server-42 sends keepalives every few seconds:          │
  │  Server-42 → Chubby: KeepAlive(S-42)                   │
  │  Chubby → Server-42: OK, session extended               │
  └─────────────────────────────────────────────────────────┘

Server-42 crashes (no more keepalives):
  ┌─────────────────────────────────────────────────────────┐
  │  Chubby: No keepalive from S-42 for 12 seconds...       │
  │  Chubby: S-42 session has expired!                      │
  │  Chubby: Deleting ephemeral node /gfs/chunk-servers/    │
  │               server-42 (session cleanup)               │
  │  Chubby: Notifying watchers of CHILD_NODE_REMOVED       │
  └─────────────────────────────────────────────────────────┘

GFS Master receives notification:
  ┌─────────────────────────────────────────────────────────┐
  │  GFS Master: Got CHILD_NODE_REMOVED for server-42       │
  │  GFS Master: server-42 is dead! Re-replicate its chunks │
  └─────────────────────────────────────────────────────────┘
```

### 6.4 Master Election Using Ephemeral Nodes

Ephemeral nodes can also be used for master election. Here is an alternative to
explicit lock acquisition:

1. All candidate masters try to create the same ephemeral node:
   `/ls/my-cell/gfs/master` with content = their address

2. Chubby allows only one client to create any given node. The first client to create
   the node wins. Others receive "already exists" errors.

3. All candidates also subscribe to `FILE_CONTENTS_MODIFIED` and `CHILD_NODE_REMOVED`
   on that path.

4. When the current master crashes, its session expires, its ephemeral node is deleted,
   and all watching candidates receive `CHILD_NODE_REMOVED`.

5. All candidates rush to create the node again. Exactly one wins. The new master is elected.

This pattern is elegant: you get master election, address registration, and liveness
detection all in one mechanism. The node existing means a master is elected; the
node content contains the master's address; the node disappearing means the master died.

In practice, Google typically uses explicit lock acquisition (Acquire() on a permanent
node) for master election rather than ephemeral node creation, because the lock
mechanism provides sequencer tokens. But both patterns appear in real systems.

### 6.5 Ephemeral Nodes vs. Permanent Nodes: When to Use Each

| Scenario | Use | Reason |
|----------|-----|--------|
| Service discovery (is server X alive?) | Ephemeral | Auto-cleanup when server dies |
| Master election (who is the leader?) | Either; Acquire() on permanent preferred | Sequencer token only available via Acquire() |
| Configuration storage | Permanent | Config should survive restarts |
| Lock state | Permanent with Acquire() | Lock semantics are separate from node lifecycle |
| Membership tracking (cluster members) | Ephemeral | Auto-removes departed members |

### 6.6 The 5-Level Progression: Ephemeral Nodes

**Intern level**: "It's a file that gets deleted automatically when you disconnect.
Like a temp file."

**Junior (L3) level**: "Ephemeral nodes are tied to client sessions. When the session
ends (client disconnects or crashes), the nodes are deleted automatically. Useful
for tracking which servers are alive."

**Mid-level (L4) level**: "The ephemeral node pattern replaces heartbeat-based health
checking. Instead of pinging servers, you watch a Chubby directory. Nodes present
means alive. Nodes gone means dead. The session timeout is the failure detector."

**Senior (L5) level**: "The key insight is that Chubby's session mechanism is already
a reliable failure detector. Reusing it for service discovery eliminates a separate
heartbeat infrastructure. The CHILD_NODE_REMOVED event gives you push-based
notification of failures instead of polling. The discovery catalog is always consistent
with actual server liveness because the deletion is atomic with the session expiry."

**Staff (L6) level**: "Ephemeral nodes create an implicit two-level architecture:
the session layer detects failures and the node layer represents observed state.
The failure detector (session) and the state store (node) being in the same system
gives you a clean invariant: a node exists if and only if its session is alive. This
invariant breaks down if you use Chubby nodes as a registry but use an external
failure detector — the external detector might not agree with the Chubby session
timeout, creating spurious deletions or stale entries. The co-location is not just
convenience; it is the source of the correctness guarantee."

---

### Part 6 Brainstorming Questions

**Q: What happens to ephemeral nodes during a Chubby master failover?**

During a Chubby master failover, client sessions enter a grace period (jeopardy
state). The ephemeral nodes are NOT deleted immediately during this grace period.
Chubby is conservative: it waits to see if the client can reconnect to the new
master before deciding the session is truly dead.

This is important because you do not want ephemeral nodes flapping (disappearing
and reappearing) during every Chubby master failover, even though client connections
do temporarily drop. The grace period is long enough for a healthy client to
reconnect to the new Chubby master and re-establish its session. Only if the client
fails to reconnect within the grace period does Chubby expire the session and delete
the ephemeral nodes.

The flip side: during the grace period, other clients see ephemeral nodes that might
belong to dead clients. They receive a notification that Chubby is in jeopardy state
and should be cautious about acting on potentially stale liveness information until
the situation resolves.

**Q: Can you create directories as ephemeral nodes?**

Chubby does not support ephemeral directories, only ephemeral file nodes. The reason
is subtle: an ephemeral directory might contain children, and it is unclear what
should happen to those children when the directory's creator's session expires.
Should all children be deleted too (even if they were created by different sessions)?
Or should the directory persist until all its children are gone?

This ambiguity makes ephemeral directories complex to specify and implement correctly.
By restricting ephemeral semantics to leaf nodes (files), the behavior is clear and
unambiguous: the node is deleted when its session ends, period. Services that need
ephemeral namespaces use a permanent directory with ephemeral files inside it.

**Q: How do you handle the thundering herd when many candidates watch for a master election?**

When the current master's ephemeral node is deleted, all watching candidates receive
a `CHILD_NODE_REMOVED` notification simultaneously. Hundreds or thousands of candidates
might all try to acquire the lock at the exact same time. This is the thundering herd
problem, which is covered in detail in Part 8. The short answer: Chubby handles lock
queuing internally, but the load spike is real and clients should add random backoff
before attempting to acquire rather than hammering Chubby simultaneously.

---

## Part 7: Sessions and Keepalives — The Liveness Contract

### 7.1 What Is a Chubby Session?

A session is the long-lived connection between a Chubby client and the Chubby cell.
It is the fundamental relationship that underlies everything: locks, ephemeral nodes,
event subscriptions. All of these are tied to a session.

Think of a session like a rental agreement. When you sign the lease (open the session),
you can use the apartment (acquire locks, create nodes). If you stop paying rent
(sending keepalives), the landlord eventually evicts you (expires the session and
cleans up your stuff).

Sessions are identified by a session ID, which is assigned by the Chubby master when
the session is opened. The session ID persists across Chubby master failovers —
the client uses it when reconnecting to prove its identity to the new master.

### 7.2 The Keepalive Mechanism

Sessions are maintained via periodic keepalive messages. The client library sends
a keepalive RPC to the Chubby master before the session's lease expires. The master
responds, extending the lease.

Default lease duration: 12 seconds. The client must send a keepalive within 12
seconds, or the session expires. In practice, the client sends keepalives much more
frequently (every 1-2 seconds) to provide a large safety buffer.

Why 12 seconds? This is a balance between:
- Short enough that dead clients are detected quickly (you do not want a dead GFS
  master's lock held for minutes)
- Long enough that transient network hiccups or brief CPU spikes do not trigger false
  expirations

The 12-second default is the result of Google's operational experience. You can
configure different values, but 12 seconds is the production-proven default.

### 7.3 The Jeopardy State

This is where it gets interesting, and where most junior engineers' mental model is incomplete.

When a client loses contact with the Chubby master (network partition, Chubby master
failover), it does not immediately lose its session. Instead, it enters the jeopardy
state.

Jeopardy is a grace period. The client library knows its session lease has expired
(or will expire soon), but it has not yet confirmed whether Chubby has expired the
session or not. The client cannot know: it cannot reach Chubby to ask.

During jeopardy, the Chubby client library:

1. Notifies the application that it is in jeopardy (delivers a JEOPARDY event)
2. Blocks all lock acquisition and release operations
3. Continues trying to reconnect to Chubby (re-resolving DNS, trying different replicas)
4. Does NOT release locks or delete ephemeral nodes (it might reconnect in time)

The jeopardy grace period is typically 45 seconds. During these 45 seconds, the client
keeps trying to reconnect. If it reconnects within the grace period, the session might
be saved: Chubby checks if the lease has truly expired or if there is still time.

If the client reconnects and the session is still within the lease window on Chubby's
side (Chubby is also being conservative), the session is restored. Locks are still
held. Ephemeral nodes still exist. All is well.

If the client fails to reconnect within the grace period, or reconnects and Chubby
says the session has expired, the session is terminated. All locks are released. All
ephemeral nodes are deleted. The client receives a SESSION_EXPIRED event.

### 7.4 The Jeopardy Timeline

```
SESSION AND JEOPARDY TIMELINE
==============================

T=0s    Client opens session, lease = 12s
T=2s    Client sends keepalive → lease reset to T+12s (T=14s)
T=4s    Client sends keepalive → lease reset to T+16s
...
T=20s   Network partition! Client cannot reach Chubby.
T=28s   Lease expires on Chubby's side.
         Chubby records session as "expired pending confirmation"
T=20s   Client enters JEOPARDY state (knew lease would expire soon)
         Client library: "In jeopardy. Blocking lock operations."
         Client library: "Trying to reconnect..."

  [If client reconnects by T=65s (20s + 45s grace)]
T=35s   Client reconnects to new Chubby master after failover
         Chubby: "Session S-42 lease expired at T=28s, but within grace period."
         Chubby: "Session restored. Lease extended."
         Client: "Session safe! Resuming normal operations."

  [If client cannot reconnect within grace period]
T=65s   Grace period expires.
         Chubby: "Session S-42 is permanently expired."
         Chubby deletes all of S-42's ephemeral nodes.
         Chubby releases all of S-42's locks.
         Client: "Received SESSION_EXPIRED. Must rebuild all state."
```

### 7.5 What Applications Must Do Upon SESSION_EXPIRED

A SESSION_EXPIRED event is serious. The application must:

1. Stop all operations that assumed it held the master lock
2. Assume it has lost all locks and ephemeral nodes
3. Rebuild from scratch: re-open a session, re-acquire necessary locks, re-create
   ephemeral nodes
4. If it was the GFS master: stop accepting client requests until re-election completes

This is why jeopardy notifications are important. A well-designed application pauses
during jeopardy (blocking new operations) and either resumes normally (session saved)
or rebuilds from scratch (session expired). Poorly designed applications that ignore
jeopardy notifications can act on stale lock state, causing correctness violations.

### 7.6 Real Story: The Service That Forgot Keepalives

A real incident pattern (composite of what the Chubby paper describes) illustrates
the danger of ignoring keepalives.

A team at Google built a service that used Chubby for master election. The service
code called Acquire() to get the master lock, checked that it was held, and then
started processing. The keepalive mechanism was handled by the Chubby client library
automatically — no application code needed.

What the team forgot: the application itself could become a CPU hog. The Chubby
client library runs in a background thread and sends keepalives. But if the main
application thread dominates the CPU and the operating system does not schedule the
background keepalive thread for 15 seconds, the keepalive misses its deadline.

Chubby expires the session. Another server acquires the master lock. The original
server, once it gets CPU time again, is told its session expired via a SESSION_EXPIRED
event. But by then, it had been executing master operations for 15 seconds as a
stale master.

The fix: treat JEOPARDY and SESSION_EXPIRED events as fatal for the application's
master role. Upon receiving JEOPARDY, immediately stop processing and enter a standby
mode. This is aggressive but correct: it is better to briefly stop serving than to
serve incorrectly as a stale master.

The lesson: the Chubby library handles keepalive mechanics, but the application must
handle the consequences of session state changes. Ignoring JEOPARDY events is a
common bug.

---

### Part 7 Brainstorming Questions

**Q: Why is the grace period (45 seconds) so much longer than the lease duration (12 seconds)?**

The lease duration (12 seconds) must be short for fast failure detection: when a
server dies, you want to detect it and elect a new master within roughly 12 seconds.
But the grace period (45 seconds) is about tolerating Chubby's own failures, not
client failures.

During a Chubby master failover, client sessions are temporarily orphaned. The new
Chubby master must be elected (takes a few seconds), DNS must propagate (can take
30+ seconds), and clients must discover the new master and reconnect. The grace period
must cover this entire process.

If the grace period were only 12 seconds, every Chubby master failover would expire
all client sessions, causing all connected services to lose their locks and do a full
re-election. In a large datacenter with hundreds of services depending on Chubby,
this would be catastrophic. The longer grace period (45 seconds) absorbs Chubby's
own recovery time without disrupting client sessions.

**Q: What happens if two clients both enter jeopardy and then both reconnect, both claiming to hold the same lock?**

This cannot happen in a correctly designed system. Only one session can hold a given
exclusive lock at a time. The session ID is the disambiguating factor. If session
S-42 holds the lock and the session expires, the lock is released before session S-99
can acquire it. When S-42 reconnects, it gets a SESSION_EXPIRED event — not a
"you still hold the lock" confirmation. S-42 cannot claim to hold the lock after
its session expires.

The key invariant: lock state is tied to sessions, and session expiry atomically
releases all locks and deletes all ephemeral nodes from that session. There is never
a state where a lock is simultaneously held by two different sessions.

**Q: How does the client library know when to give up reconnecting and declare the session expired?**

The client library tracks the session lease expiry time (the last time it received
a keepalive acknowledgment, plus the lease duration). It also tracks the local clock.
When the lease expiry time passes on the local clock without a successful keepalive,
the library starts the jeopardy period.

During jeopardy, the library continues trying to reconnect. It gives up after the
grace period elapses. The grace period is enforced by the client library locally —
the client does not need to hear from Chubby to know the grace period has expired.
This is important because the client might never hear from Chubby again if there is
a permanent network partition.

The dependency on local clocks means that if a client's clock is drastically wrong
(by more than the grace period), behavior can be incorrect. Chubby clients are expected
to run with NTP and clock drift within normal bounds (milliseconds to seconds, not
minutes). This is a reasonable assumption in a well-operated datacenter.

---

## Part 8: The Thundering Herd Problem

### 8.1 What Is the Thundering Herd?

Imagine a large park with a single ice cream truck. When the truck first arrives,
hundreds of people in the park notice and rush to the truck simultaneously. The truck
operator (and the queue that forms) handles this okay — people line up, everyone gets
served eventually. But imagine instead that the truck leaves and comes back repeatedly.
Every time it returns, all hundreds of people rush over again. The periodic stampede
is much harder to manage than a steady line.

This is the thundering herd problem in distributed systems: a large number of clients
all wait for the same event and then all act simultaneously when that event occurs.

In Chubby's context, the event is "a popular lock is released." When the GFS master
lock is released (because the master crashed), every server that was watching that
lock fires simultaneously. If there are hundreds of candidate servers, they all send
lock acquisition requests to Chubby at the same moment.

### 8.2 Why the Thundering Herd Matters for Chubby

Chubby can typically handle a few hundred lock acquisitions per second (it is not
designed for high throughput). A thundering herd of 500 simultaneous lock acquisition
attempts can easily overwhelm Chubby and make the situation worse:

1. Master crashes
2. 500 candidates simultaneously get `LOCK_RELEASED` notification
3. 500 candidates simultaneously send `Acquire()` requests to Chubby
4. Chubby is flooded with requests — far beyond its capacity
5. Many requests time out
6. 500 candidates retry... simultaneously
7. The flood repeats. Chubby cannot recover.
8. Master election takes minutes instead of seconds.

This is not a theoretical concern. The Chubby paper specifically discusses thundering
herd as a real problem observed in production. Large Google systems had hundreds of
candidate masters watching the master lock, and lock release notifications caused
enough traffic to noticeably degrade Chubby performance.

### 8.3 Solutions to the Thundering Herd

**Solution 1: Random backoff**

The simplest solution: when a client receives a lock release notification, it waits
a random amount of time before attempting to acquire. The randomization spreads the
load across time.

```
Client receives LOCK_RELEASED at time T:
  Wait = random(0, 2000ms)  // Random wait 0-2 seconds
  At time T + Wait: Acquire("/gfs/master")
```

With 500 clients waiting 0-2 seconds randomly, the Chubby load is spread across
a 2-second window instead of a single instant. 500 requests/2s = 250 requests/s,
which Chubby can handle.

**Solution 2: Advisory ordering (Chubby's actual approach)**

Chubby provides a more elegant solution: when multiple clients are waiting to acquire
the same lock, Chubby manages a queue internally. When the lock is released, Chubby
notifies only the next client in the queue, not all waiting clients.

This eliminates the thundering herd entirely for queued waiters. Only one client
receives the notification and attempts acquisition. Others continue waiting in the
queue. When that client acquires and eventually releases the lock, Chubby notifies
the next in the queue.

However, this only works for clients that are blocking on `Acquire()`. Clients that
watch the lock file via event notifications (not using the queue mechanism) still
all get notified simultaneously.

**Solution 3: Limit the number of watchers**

In the GFS master design, only a small number of servers (typically 1-3) are active
candidates for master election at any time. Rather than having all 500 GFS servers
watch the master lock, only the designated candidates watch. If a candidate dies,
another is promoted. This limits the fan-out of any single lock release event.

This is an architectural solution: design systems so that the number of watchers
on critical locks is small and bounded.

**Solution 4: Hierarchical lock structure**

For very large systems, use a two-level structure. A small number of "regional"
candidates hold a coarse-grained lock. Each region has a small number of candidates.
Only the winner of the regional lock competes for the global lock. The thundering
herd at the global level is bounded by the number of regions, not the number of total
candidates.

### 8.4 The Thundering Herd on Chubby Cell Restart

An even more severe thundering herd occurs when the entire Chubby cell is briefly
unavailable (for example, during a software update). All connected clients lose their
sessions simultaneously. When Chubby comes back, hundreds or thousands of clients
all reconnect simultaneously, all try to re-establish sessions, all try to re-acquire
locks, and all try to re-create ephemeral nodes.

The Chubby paper describes this as a "thundering herd on the Chubby cell itself."
When this happened at Google, Chubby would come back up and immediately be so
overwhelmed with reconnection requests that it could not process them fast enough,
causing more timeouts, causing more retries, causing more load — a feedback loop.

The fix at Google: Chubby client libraries implement exponential backoff with jitter
on reconnection after a complete cell outage. Clients do not all reconnect at the
exact moment Chubby becomes available. They stagger their reconnections over tens
of seconds, giving Chubby time to process requests rather than being overwhelmed.

### 8.5 ASCII Diagram: Thundering Herd vs. Orderly Queue

```
WITHOUT BACKOFF (Thundering Herd):
====================================

Lock released at T=0
                     T=0.001s
Client 1 ──────────────────────→ Chubby (ACQUIRE)
Client 2 ──────────────────────→ Chubby (ACQUIRE)
Client 3 ──────────────────────→ Chubby (ACQUIRE)
...
Client 500 ────────────────────→ Chubby (ACQUIRE)
                                 ↑ Overwhelmed!
                                 500 simultaneous requests

WITH RANDOM BACKOFF:
====================

Lock released at T=0

Client 1 waits 200ms  ────────────────→ Chubby (ACQUIRE) at T=200ms
Client 2 waits 450ms  ──────────────────────────→ Chubby at T=450ms
Client 3 waits 1100ms ─────────────────────────────────────────────→ T=1100ms
...
500 clients spread over 2000ms = ~250 requests/second (manageable)

WITH QUEUE (Chubby's Advisory Ordering):
=========================================

Lock released at T=0
Chubby queue: [Client-17, Client-83, Client-209, Client-5, ...]

Chubby notifies only Client-17:
Client-17 ─→ Chubby: ACQUIRE. Response: "Acquired! Seq=48"
Clients 83, 209, 5, ... remain sleeping in queue.

Client-17 finishes, releases lock at T=3600s:
Chubby notifies only Client-83 (next in queue)
Client-83 ─→ Chubby: ACQUIRE. Response: "Acquired! Seq=49"
...
```

---

### Part 8 Brainstorming Questions

**Q: Does the thundering herd happen every time the GFS master changes?**

Yes, every time the GFS master lock is released, all clients watching that lock
receive notification simultaneously. In production GFS, master changes are rare
(the master runs for hours or days), so this is not a frequent event. But when it
does happen, it must be handled correctly.

For GFS, Google limits the number of active master candidates to a small number
(not 500). The full set of GFS servers do not all watch the master lock. Only
designated candidate servers — a handful — watch it. If a candidate fails, another
is promoted. This architectural choice eliminates the thundering herd problem for
master election because the number of watchers is always small.

The thundering herd on Chubby restart is the more serious concern, because that
involves all sessions being simultaneously disrupted regardless of which locks they
hold.

**Q: Could you eliminate the thundering herd by making Chubby stateful about who should get the lock next?**

Chubby does maintain a wait queue for lock requests, which is essentially this. When
a client calls `Acquire()` and the lock is busy, it is added to the queue. When the
lock is released, Chubby notifies the first client in the queue. This prevents the
thundering herd for clients using the blocking `Acquire()` call.

The limitation is that clients watching via event notifications (using `Subscribe()`)
rather than blocking on `Acquire()` all receive the notification simultaneously. For
these clients, client-side backoff is the primary mitigation.

**Q: What is the difference between thundering herd and a DDoS attack on Chubby?**

Both involve sudden overwhelming traffic to Chubby. The key difference is intent and
source. A thundering herd is unintentional: it emerges from normal system design
where many clients legitimately react to a shared event. A DDoS is intentional.

The mitigations also differ. A thundering herd is mitigated by backoff in the clients
(since you control the clients). A DDoS requires authentication, rate limiting, and
traffic filtering at the Chubby level.

However, the defensive techniques overlap. Chubby implements rate limiting per client
IP regardless of intent — this limits the damage from both a thundering herd where
one client is particularly aggressive and from actual DDoS attempts.

---

## Part 9: Chubby vs. ZooKeeper vs. etcd

### 9.1 The Family Tree

Chubby (2006) → ZooKeeper (2008, open-source Chubby equivalent) → etcd (2013, Raft-based)

These three systems solve the same problem: distributed coordination. Understanding
their differences helps you choose the right tool and answer "why didn't they just
use X?" questions in interviews.

### 9.2 Detailed Comparison Table

```
COMPARISON: CHUBBY vs. ZOOKEEPER vs. etcd
==========================================

┌─────────────────────┬──────────────────┬──────────────────┬──────────────────┐
│ Property            │ Chubby           │ ZooKeeper        │ etcd             │
├─────────────────────┼──────────────────┼──────────────────┼──────────────────┤
│ Consensus Protocol  │ Paxos            │ ZAB (Paxos-like) │ Raft             │
│ Primary Use Case    │ Lock service     │ Coordination     │ Config store     │
│ Data Model          │ File tree        │ ZNode tree       │ Key-value store  │
│ Ephemeral Nodes     │ Yes              │ Yes              │ Leases (approx.) │
│ Watch/Notify        │ Yes (events)     │ Yes (watches)    │ Yes (watch API)  │
│ Sessions            │ Yes (keepalives) │ Yes (keepalives) │ Leases           │
│ Sequencer Tokens    │ Yes (built-in)   │ Via zxid         │ Via revisions    │
│ Lock Primitives     │ First-class      │ Via recipes      │ Via leases       │
│ Typical Replicas    │ 5                │ 3 or 5           │ 3 or 5           │
│ Language            │ C++ (internal)   │ Java             │ Go               │
│ Open Source         │ No               │ Yes (Apache)     │ Yes (CNCF)       │
│ Typical Latency     │ 10-30ms          │ 5-15ms           │ 5-15ms           │
│ Typical Throughput  │ ~100K ops/s      │ ~10-50K ops/s    │ ~10-50K ops/s    │
│ Client Caching      │ Yes (lock state) │ Client-side      │ Client-side      │
│ Primary User        │ Google           │ Hadoop/HBase/    │ Kubernetes       │
│                     │                  │ Kafka/etc.       │                  │
│ ACL Model           │ File-based ACLs  │ ZNode ACLs       │ Role-based       │
│ TTL on Keys         │ Session-based    │ Session-based    │ Yes (explicit)   │
│ Transaction Support │ Limited          │ Multi-op atomic  │ Yes (compare-    │
│                     │                  │                  │ and-swap, txn)   │
└─────────────────────┴──────────────────┴──────────────────┴──────────────────┘
```

### 9.3 Why Chubby Uses Paxos, Not Raft

Paxos was invented first (Lamport, 1989/1998). Raft was invented later specifically
to be more understandable (Ongaro & Ousterhout, 2014). Both solve the same consensus
problem with similar performance characteristics.

Chubby predates Raft. In 2006, the choices were Paxos, Viewstamped Replication, or
a proprietary protocol. Google chose Paxos.

ZooKeeper uses ZAB (ZooKeeper Atomic Broadcast), which is similar to Paxos but
optimized for the broadcast pattern (a leader proposes, followers accept).

etcd uses Raft, which became the dominant consensus algorithm for new systems after
2013 because it is much easier to understand, implement, and debug than Paxos.

In terms of correctness and performance, Paxos vs. Raft is not a meaningful distinction
for most practical purposes. The choice of consensus algorithm is less important than
the implementation quality and the operational tooling.

### 9.4 ZooKeeper: The Open-Source Equivalent

ZooKeeper was built at Yahoo and open-sourced via Apache as a direct response to
Chubby: "we need the same thing but open source." Yahoo engineers read the Chubby
paper and implemented a compatible system.

Key similarities with Chubby:
- ZNode tree = Chubby file tree
- Ephemeral ZNodes = Chubby ephemeral nodes
- Session + keepalives (called heartbeats in ZooKeeper)
- Watches (event notifications) = Chubby event subscriptions
- Majority quorum consensus

Key differences:
- ZooKeeper uses ZAB, not Paxos
- ZooKeeper does not have built-in lock primitives — you implement locking using
  ephemeral sequential ZNodes (a recipe on top of the API)
- ZooKeeper's watches are one-shot: after an event fires, you must re-subscribe.
  Chubby's events are persistent subscriptions.
- ZooKeeper is Java; easier to deploy in Java ecosystems

When to use ZooKeeper: when you need Chubby-equivalent coordination in an open-source
stack, especially in the Hadoop/Kafka/HBase ecosystem, which already deeply integrates
ZooKeeper.

### 9.5 etcd: The Kubernetes Coordinator

etcd was built by CoreOS for use in their distributed Linux systems and became the
coordination store for Kubernetes. It presents a simple key-value API (get, put,
delete, watch) rather than a file system API.

Key differences from Chubby and ZooKeeper:
- Key-value store (not a file tree) — simpler but less hierarchical
- Raft consensus (more modern, easier to understand)
- Explicit TTL on keys (rather than session-based expiry)
- Strong compare-and-swap and transactions
- gRPC API (modern)
- Designed for Kubernetes' specific access pattern: frequent reads of small config

etcd uses "leases" as a rough equivalent of Chubby sessions. A key can be associated
with a lease, and when the lease expires (because the client that created the lease
stopped renewing it), the key is deleted. This is similar to ephemeral nodes but
more flexible (any key can be associated with any lease, not just the creating session).

When to use etcd: when deploying Kubernetes or building systems in the Kubernetes
ecosystem. etcd is tightly integrated with Kubernetes API server. For new systems
not using Kubernetes, etcd is a clean and modern choice.

### 9.6 When to Use Which

| Scenario | Recommended | Why |
|----------|-------------|-----|
| Google-internal systems | Chubby | Already integrated, proven at Google scale |
| Hadoop, HBase, Kafka | ZooKeeper | Deep ecosystem integration |
| Kubernetes-based systems | etcd | Already present in every Kubernetes cluster |
| New open-source systems | etcd or ZooKeeper | etcd is newer/cleaner; ZooKeeper has more documentation |
| Simple distributed lock in any stack | etcd with lease-based locking | Simplest API |
| Complex coordination with strict sequencer tokens | ZooKeeper or etcd | Both support monotonic version numbers |

### 9.7 Why Chubby Is Not Paxos vs. Raft vs. ZAB

A common interview mistake: confusing the consensus algorithm with the overall system.
Chubby is not Paxos. Chubby uses Paxos. The consensus algorithm is one component
of the system. The other components — the session model, the file system API, the
ephemeral node mechanism, the sequencer token, the event notification — are what
make Chubby Chubby.

Similarly, etcd is not Raft. etcd uses Raft for consensus but the key-value API,
lease mechanism, and watch system are separate layers on top.

---

### Part 9 Brainstorming Questions

**Q: If ZooKeeper and etcd both work for coordination, which would you choose for a new system?**

For a brand-new system with no existing dependencies, etcd is the cleaner modern
choice. Its API is simpler (key-value vs. tree), Raft is more understandable than
ZAB for debugging purposes, and gRPC is a better transport than ZooKeeper's custom
binary protocol. etcd has excellent documentation, a strong open-source community,
and good client libraries in most languages.

ZooKeeper's main advantage is ecosystem integration with existing systems. If you
are building something that will run alongside Kafka, HBase, or existing Hadoop
infrastructure, ZooKeeper is already there and using it avoids adding a second
coordination system to the stack. Adding etcd alongside ZooKeeper would require
operating two coordination systems, which is extra operational burden.

The "right answer" in an interview is usually "either works for coordination; I would
use etcd for a new system because it has a simpler API and better modern tooling,
unless we already have ZooKeeper in our stack."

**Q: Does Kubernetes really depend on etcd so heavily? What happens if etcd fails?**

Yes, Kubernetes is critically dependent on etcd. etcd is where Kubernetes stores
all cluster state: every pod definition, service, deployment, configmap, secret,
and node status. The Kubernetes API server is essentially a REST API layered on top
of etcd.

If etcd fails, the Kubernetes control plane cannot function. Existing workloads that
are already running continue running (kubelet on each node keeps running pods without
needing etcd), but you cannot schedule new pods, scale deployments, or make any
changes to the cluster configuration. It is essentially a read-only mode for the cluster.

This is why Kubernetes production deployments always run etcd with 3 or 5 replicas,
and why etcd backup and restore procedures are critical operational knowledge. The
Kubernetes ecosystem has invested heavily in making etcd operations easy (etcdctl,
Velero for backup, etc.) precisely because etcd failure means control plane failure.

**Q: Why didn't Google make Chubby open source instead of waiting for Yahoo to build ZooKeeper?**

The Chubby paper (2006) describes an internal Google system tightly integrated with
Google's internal infrastructure — the RPC framework, the naming system, the access
control system, the monitoring infrastructure. Open sourcing it would require either
stripping all of these out (and producing a less functional system) or also open
sourcing all of Google's internal infrastructure (which was not going to happen in 2006).

Google often publishes research papers about internal systems to share the ideas
while keeping the implementation internal. This allows the industry to benefit from
the ideas (ZooKeeper was built from the Chubby paper) without requiring Google to
maintain an open-source version of an internal system.

This is a pattern Google has followed repeatedly: publish the ideas in papers
(MapReduce, GFS, Bigtable, Chubby, Spanner), let the open-source community build
equivalents (Hadoop, HDFS, HBase, ZooKeeper, CockroachDB), and focus Google's
engineering effort on the next generation of internal systems.

---

## Part 10: Interview Application — How Chubby Appears in Design Interviews

### 10.1 When Chubby Appears Without Being Named

In system design interviews, Chubby rarely appears by name in the problem statement.
Instead, it appears through these trigger phrases:

- "How does your system elect a master?" → Chubby or equivalent
- "How does a secondary know when to take over?" → Chubby/ZooKeeper/etcd session timeout
- "How do you store cluster membership?" → Ephemeral nodes in Chubby/ZooKeeper
- "How does component X find component Y?" → Service discovery via Chubby/ZooKeeper
- "How do you prevent two primaries from writing simultaneously?" → Distributed lock + sequencer

Knowing Chubby means you have a ready answer to all of these, with the right level
of depth.

### 10.2 The L5 vs. L6 Answer Difference

**The problem**: "In your BigTable design, how does the master know which tablet
servers are alive?"

**L4 answer**: "The master periodically pings all tablet servers. If a ping fails,
the master marks that server as dead."

This is not wrong but it misses the real design. It also creates a new problem: what
if the master crashes? Now the ping mechanism is gone.

**L5 answer**: "Tablet servers register themselves in ZooKeeper using ephemeral nodes.
The master watches the ZooKeeper directory. When a tablet server crashes, ZooKeeper
deletes its ephemeral node after the session timeout, and the master receives a
notification. The master reassigns the crashed server's tablets."

This is correct and shows understanding of the pattern. A strong L5 answer.

**L6 answer**: "Tablet servers create ephemeral nodes in Chubby under a well-known
path like `/ls/bigtable-cell/tablet-servers/<server-id>`. The file contains the
server's address and last heartbeat time. The Bigtable master watches this directory
with a CHILD_NODE_REMOVED subscription.

When a tablet server crashes, it stops sending Chubby session keepalives. After the
12-second lease expires, Chubby runs a Paxos round to record the session as expired,
then deletes the ephemeral node and sends notifications to all watchers. The Bigtable
master receives CHILD_NODE_REMOVED, identifies which tablets were assigned to the
dead server, and initiates re-replication.

The master itself holds an exclusive lock on `/ls/bigtable-cell/master` with a
sequencer token. When the master issues re-replication commands to surviving tablet
servers, it includes its sequencer token. Tablet servers verify the sequencer with
Chubby before executing commands, preventing a stale former master from interfering
with re-replication after a master failover.

The grace period (45 seconds) means that during a Chubby cell failover, tablet servers
don't immediately appear dead. The system waits for the grace period before concluding
that a server is truly gone rather than just temporarily disconnected from Chubby."

That's the L6 answer: it covers the mechanism, the timing, the sequencer interaction,
and the edge cases.

### 10.3 Chubby in GFS — The Full Picture

```
HOW GFS USES CHUBBY
====================

Chubby namespace for GFS:
/ls/gfs-cell/
  master           ← exclusive lock held by GFS master
  master-addr      ← permanent file: master's IP:port
  chunk-servers/
    cs-001         ← ephemeral: chunk server 001 is alive
    cs-002         ← ephemeral: chunk server 002 is alive
    cs-047         ← ephemeral: chunk server 047 is alive
    ...

GFS Master Election:
1. Candidate masters attempt Acquire("/ls/gfs-cell/master", EXCLUSIVE)
2. Winner gets lock with sequencer (master, EXCLUSIVE, seq=N)
3. Winner writes its address to /ls/gfs-cell/master-addr
4. Winner begins serving as master, including sequencer in all commands

Chunk Server Registration:
1. Chunk server cs-001 starts up
2. cs-001 creates ephemeral node /ls/gfs-cell/chunk-servers/cs-001
3. cs-001 writes its address to the node's content
4. GFS master has CHILD_NODE_ADDED subscription → learns cs-001 is alive

Chunk Server Failure Detection:
1. cs-047 crashes
2. cs-047's Chubby session stops sending keepalives
3. After 12s lease + grace period, Chubby expires the session
4. Chubby deletes /ls/gfs-cell/chunk-servers/cs-047
5. GFS master receives CHILD_NODE_REMOVED notification
6. GFS master knows cs-047 is dead, initiates re-replication of its chunks

Sequencer Verification:
1. GFS master (seq=47) issues: "Chunk server cs-003, add chunk X to cs-007"
2. GFS master includes sequencer token in the RPC
3. cs-003 verifies: "Is (gfs-master, EXCLUSIVE, seq=47) valid?" → Chubby: "Yes"
4. cs-003 executes the command
5. (If stale master with seq=44 tries the same): → Chubby: "No, seq=47 is current"
6. cs-003 rejects the stale command
```

### 10.4 Common Interview Mistakes

**Mistake 1: Confusing Chubby with a database**

"I'll use Chubby to store the user's profile data." Wrong. Chubby stores small
coordination metadata (locks, addresses, small config files). It is not a general
data store. Its 256KB file size limit, Paxos replication overhead, and limited
throughput make it completely unsuitable for application data.

Correct framing: Chubby is for coordination (who is master, which servers are alive,
small config) not for data (user profiles, chat messages, time series).

**Mistake 2: Not mentioning sequencer tokens**

Saying "the GFS master holds a Chubby lock" is incomplete. The dangerous moment
is when the old master's lock is being revoked and the new master's lock is being
established. Without the sequencer, the old master's in-flight commands to chunk
servers could corrupt state. Mentioning the sequencer token shows you understand
the subtle correctness requirement, not just the basic locking pattern.

**Mistake 3: Treating Chubby as always available**

"Services wait for the Chubby lock to be released, then one acquires it." This
ignores the case where Chubby itself is unavailable. Services must handle Chubby
being briefly unavailable (during master failover) without crashing. The jeopardy
state and grace period are the mechanisms for this. A well-designed service enters
read-only or standby mode during Chubby unavailability rather than crashing.

**Mistake 4: Assuming lock release is instantaneous**

When a lock holder crashes, the lock is not immediately released. It takes up to
one full session lease duration (12 seconds) for Chubby to detect the failure and
expire the session. The lock-delay period then adds additional time before the next
client can acquire. Interviewers testing deeper knowledge will ask "how long does
master re-election take?" and the correct answer involves these time bounds.

**Mistake 5: Ignoring the thundering herd on popular locks**

In large systems with many candidate masters, releasing a popular lock can cause
hundreds of simultaneous acquisition attempts. Mentioning that you would limit the
number of active watchers on critical locks (or use random backoff) shows operational
awareness beyond the basic mechanism.

**Mistake 6: Calling ZooKeeper a "Chubby replacement" without explaining the difference**

ZooKeeper is the open-source equivalent of Chubby, but it has differences: ZooKeeper
does not have built-in lock primitives (you implement them using recipes), ZooKeeper's
watches are one-shot, and ZooKeeper uses ZAB instead of Paxos. Saying "just use
ZooKeeper" without acknowledging these differences suggests you have not worked with
either system at depth.

---

### Part 10 Brainstorming Questions

**Q: In an interview, when should you mention Chubby vs. when should you mention ZooKeeper or etcd?**

The choice depends on the context of the system you are designing. If you are
designing a Google-style internal system (inspired by GFS, Bigtable, etc.), reference
Chubby since it is the canonical system for that context. If you are designing an
open-source or cloud-native system (Kafka, Kubernetes, HDFS), reference ZooKeeper
or etcd since those are the real-world systems used.

If you are unsure of the context, use "distributed lock service (Chubby/ZooKeeper/etcd)"
and then say "I will use ZooKeeper in this design since we are building an open-source
stack." The key is to demonstrate understanding of the underlying mechanism, not to
pick a specific product. The interviewer is testing whether you know about consensus-based
distributed coordination, session-based liveness detection, and sequencer tokens —
not whether you know the exact API of Chubby vs. ZooKeeper.

**Q: How do you explain Paxos to an interviewer in 30 seconds without getting bogged down?**

"Paxos is a consensus algorithm. It guarantees that a cluster of N servers can agree
on a single value — in this case, 'who is the current lock holder' — as long as a
majority (N/2 + 1) of servers are reachable. We use Paxos to replicate the lock
state across all five Chubby replicas. Even if two replicas crash simultaneously,
the remaining three can still reach consensus and continue operating. The key property
is that Paxos never lets two servers disagree on the current state — it provides strong
consistency." That is a complete, accurate, 30-second Paxos explanation. Do not go
deeper unless asked.

**Q: If you were designing a new system from scratch today and needed distributed locking, what would you choose?**

For most new systems today, I would use etcd with its lease-based locking. etcd is
well-supported, has clean gRPC APIs, excellent client libraries in all major languages,
and is battle-tested in Kubernetes deployments. Raft is easier to operate and debug
than Paxos.

I would use ZooKeeper if I am integrating with existing Kafka, HBase, or Hadoop
infrastructure where ZooKeeper is already present and well-understood by the team.
Adding etcd alongside ZooKeeper creates operational burden.

I would use a simpler in-process mechanism (like Redis-based distributed locks with
Redlock) only if my locking requirements are not strict — for example, rate limiting
or advisory coordination where occasional split-brain is acceptable. For master
election in critical systems, I would always use etcd or ZooKeeper with proper session
semantics.

---

## Part 11: Real Incidents and Lessons

### 11.1 Incident 1: The Google Datacenter Partition

The Chubby paper (2006) describes real incidents at Google where Chubby's design
choices were validated by production experience. One class of incident: the datacenter
network partition.

**What happened**: A network misconfiguration caused a portion of a Google datacenter
to be partitioned from the rest. Servers in the partitioned segment could reach each
other but could not reach the Chubby cell (which was in the non-partitioned segment).

**The dangerous scenario**: Services in the partitioned segment had acquired Chubby
locks before the partition. Those locks were for things like "I am the Bigtable master
for this cell." When the partition started, those sessions began missing keepalives.
After 12 seconds, Chubby expired their sessions and gave their locks to other servers
outside the partition. Now there were two sets of services acting as masters: the
original set (in the partition, still believing they held the locks) and the new set
(outside the partition, having just acquired the locks).

**How Chubby's design limited the damage**: Because chunk servers verified sequencer
tokens before executing commands, the stale masters' commands were rejected by chunk
servers that could reach Chubby. The stale masters in the partition could not corrupt
data on chunk servers outside the partition. The damage was limited to operations
within the partition (which were eventually rolled back when the partition healed and
the services received SESSION_EXPIRED events).

**What would have happened without sequencer tokens**: The stale masters would have
continued issuing commands to chunk servers. Chunk servers would have executed
commands from both the old and new masters simultaneously, corrupting GFS's namespace
and chunk placement data. Recovery would require manual intervention and potentially
data loss.

**Lesson**: The sequencer token is not just a nice-to-have. It is the critical
correctness guarantee that allows distributed systems to operate safely during the
network partition scenarios that are inevitable in large-scale production.

### 11.2 Incident 2: Thundering Herd on Master Election

**What happened**: A popular internal Google service had hundreds of instances, all
of which were candidates for a specific master role. The master was the coordinator
for a batch processing pipeline. When the current master crashed, the Chubby lock was
released. All hundreds of candidate instances simultaneously received the lock release
event and immediately sent `Acquire()` requests to Chubby.

Chubby, which was handling tens of lock operations per second normally, was suddenly
hit with hundreds of simultaneous requests. The Chubby cell's master became CPU-bound
processing these requests. Responses slowed down. Clients started timing out and
retrying. The retry storm made things worse. For several minutes, no client could
successfully acquire the lock — Chubby was too busy to process any single request
fast enough.

**The result**: The batch pipeline had no master for several minutes. Jobs queued up
and timed out. Downstream systems that expected pipeline outputs began failing.

**The fix**: The team implemented random backoff (0-5 seconds) in their candidates
before attempting Acquire(). They also reduced the number of active candidates from
"all instances" to "a pool of 5 designated candidates," with others becoming candidates
only if needed. These changes eliminated the thundering herd.

**Lesson**: Designing for thundering herd is not just a performance concern — it can
cause complete unavailability of the lock service during exactly the moment you need
it most (when recovering from a failure). Always bound the number of watchers on
critical locks and use backoff in lock acquisition.

### 11.3 Incident 3: A Service That Forgot Keepalives (Session Mismanagement)

**What happened**: A team built a coordination service that used Chubby to elect a
master. The Chubby client library ran in the main process thread (not a dedicated
background thread). The master's main loop occasionally processed large batches of
work that took 20-30 seconds each.

During a large batch, the main thread was busy for 25 seconds without yielding. The
keepalive that should have gone out at 8 seconds and 16 seconds was never sent because
the keepalive code was on the main thread. Chubby expired the session after the 12-second
deadline.

Another candidate acquired the master lock. The new master started issuing commands.
25 seconds later, the original master finished its batch, checked Chubby, got
SESSION_EXPIRED, and stopped. But during those 25 seconds, both masters were issuing
commands.

Because this team's service did not implement sequencer tokens (they thought their
workload was small enough to not need them), the downstream services executed
commands from both masters. Database entries were written twice, some were corrupted,
and a significant data cleanup effort was required.

**The fix**: Move Chubby keepalive to a dedicated background thread with strict
scheduling priority. Implement sequencer tokens. Add health checks that verify the
session is in good standing before executing any master operations (not just at startup).

**Lesson**: The Chubby client library provides the keepalive mechanism, but you must
ensure the library's background operations are not starved by the main application.
And sequencer tokens are not optional for any system where correctness matters.

### 11.4 General Lessons from Chubby Production Experience

The Chubby paper's "Lessons Learned" section is one of the most valuable parts of
the paper. Key lessons:

**1. Coarse-grained locking is the right abstraction for coordination.**
Teams that tried to use Chubby for fine-grained locking (locking individual database
rows) hit Chubby's throughput limits immediately. The system is designed for
infrequent acquisitions, not thousands per second.

**2. The file system API is useful but introduces complexity.**
Developers sometimes forgot that Chubby files are very different from regular files
(consensus-backed, session-tied, 256KB limit). Clear documentation and naming
conventions helped.

**3. Caching is essential.**
The Chubby client library's ability to cache lock state locally (so not every
operation requires an RPC to the Chubby cell) is what makes Chubby practical at
Google's scale. Without caching, Chubby would be a bottleneck. With caching, the
common-case read is served from the local client cache.

**4. Monitor your Chubby load carefully.**
Chubby provides detailed metrics: number of cells, sessions, locks, RPCs per second,
jeopardy events. Teams that hit Chubby limits invariably had not been monitoring
these metrics. Alerting on "lock acquisitions per second approaching limit" provides
early warning.

**5. Design for Chubby unavailability.**
Chubby aims for five nines of availability, but five nines means roughly 5 minutes
of downtime per year. Systems must be designed to tolerate brief Chubby unavailability
gracefully (typically by entering read-only or standby mode) rather than crashing.

---

### Part 11 Brainstorming Questions

**Q: Could the datacenter partition incident have been prevented entirely?**

No network partition can be entirely prevented — it is a fundamental fact of
distributed systems. The question is not how to prevent partitions but how to design
systems that remain correct during partitions. Chubby's design choices (sequencer
tokens, lock delay, jeopardy period) are specifically aimed at this.

What could be improved: the duration of the damage window. With better clock
synchronization and faster lease expiry detection, the period during which a stale
master in a partition believes it holds the lock could be shortened. But there is
always a non-zero window (bounded by the lease duration and session timeout). The
sequencer token ensures this window causes no permanent data corruption, even if it
causes temporary rejection of commands.

**Q: In the thundering herd incident, why didn't Chubby's internal queue prevent the problem?**

Chubby's internal queue only helps clients that are blocked inside `Acquire()`. The
thundering herd in this incident involved clients that had not yet called `Acquire()`
— they received an event notification (all simultaneously), then each independently
called `Acquire()`. The queue forms only after `Acquire()` is called; the flood of
simultaneous `Acquire()` calls is what overwhelmed Chubby before the queue could form.

This is why client-side backoff is necessary in addition to Chubby's server-side
queue. The server-side queue manages orderly dispatch once clients are in the queue;
client-side backoff prevents the initial flood of requests that overwhelms the server
before it can enqueue them.

**Q: Should the team in the third incident have used a different architecture to avoid the problem?**

Yes. The root cause was running Chubby keepalives on the main thread — a design error.
The correct architecture is always to run keepalives in a dedicated high-priority
background thread with an independent timer, completely isolated from the main
application logic. This is what the official Chubby client library does when used
correctly in multi-threaded mode.

Beyond the keepalive issue, the absence of sequencer tokens was a deeper architectural
error. Any system using distributed locking for correctness (not just performance)
must implement sequencer tokens or an equivalent fencing mechanism. The assumption
"our workload is small enough to not need this" is incorrect — the correctness argument
for fencing tokens is about preventing data corruption, not about workload size.

---

## Part 12: Putting It All Together — The Mental Model

### 12.1 The Complete Chubby Mental Model

Here is how to hold the entire Chubby system in your head as one coherent picture:

**The actors**:
- The Chubby cell: five replicas running Paxos, storing all lock state
- Chubby clients: services (GFS master, Bigtable master, etc.) that use Chubby
- Sessions: the long-lived authenticated connection between each client and the cell
- Downstream services: chunk servers, tablet servers that verify sequencer tokens

**The invariants**:
- Every exclusive lock is held by at most one session at a time (Paxos ensures this)
- Every session is alive if and only if it is sending keepalives within the lease deadline
- Every ephemeral node exists if and only if its session is alive
- Every sequencer token is valid if and only if the session that acquired it is still alive
  and holds the lock

**The failure handling chain**:
- Client stops sending keepalives → Session enters expiry countdown
- Session expires → Chubby invalidates all sequencers, releases all locks, deletes ephemeral nodes
- Sequencer invalidated → Downstream services reject stale commands from old lock holder
- Lock released → Next client in queue (or via notification) acquires the lock

This chain is the core of Chubby's safety model. Every component plays its role,
and the system degrades gracefully even when multiple components fail simultaneously.

### 12.2 The Chubby Lock Service Design Principles (Summarized)

1. Use consensus (Paxos) to replicate lock state — correctness requires it
2. Use session-based liveness detection — keepalives are the heartbeat of the system
3. Use sequencer tokens to fence out stale masters — advisory locks need this safety net
4. Use lock delay to create a safe gap between old and new lock holders
5. Use ephemeral nodes to co-locate liveness detection with state representation
6. Cache aggressively at the client level — common reads should never hit the network
7. Design for coarse-grained locking — one lock held for hours, not millions of locks per second
8. Design for Chubby unavailability — clients must survive brief Chubby downtime gracefully

---

## Exercises

**Exercise 1: Session Expiry Calculator**

A Chubby session has a 12-second lease. The client sends keepalives every 4 seconds.
The client's network suffers a 10-second outage at time T=50s. Trace the sequence
of events: when does the lease expire? Does the session enter jeopardy? When is the
keepalive sent after reconnection? Does the session survive?

(Answer: Last keepalive at T=48s, lease valid until T=60s. Network recovers at T=60s.
First keepalive sent at T=52s (would have been sent at T=52s but network is down),
actually sent at T=60s when network recovers. Lease is exactly at boundary — client
should have entered jeopardy at T=60s. This is a timing edge case; in practice,
Chubby adds a small buffer so the session likely survives but the client library
would have delivered a JEOPARDY event.)

**Exercise 2: Sequencer Arithmetic**

Server A acquires a lock and gets sequencer 47. Server A crashes. Server B acquires
the lock and gets sequencer 48. Server A restarts and sends a stale RPC to a chunk
server with sequencer 47. The chunk server's cached sequencer for this lock is 46
(from a previous verification). What happens? What should the chunk server do?

**Exercise 3: Thundering Herd Calculation**

A Chubby cell can handle 500 lock operations per second. A popular lock has 200
watchers, and when it is released, all 200 watchers try to acquire simultaneously.
Each failed acquire attempts a retry after a fixed 100ms delay (no randomization).
How many seconds until the thundering herd resolves (one client acquires the lock)?
Now recalculate with random backoff of 0-2000ms per client.

**Exercise 4: Ephemeral Node Recovery Design**

You are designing the Bigtable tablet server registration system. Tablet servers
create ephemeral nodes in Chubby. The Chubby cell experiences a master failover
that takes 30 seconds. During this 30 seconds, what state are the tablet server
ephemeral nodes in? What does the Bigtable master see? What should the master do?
Design the master's behavior during Chubby jeopardy.

**Exercise 5: Lock vs. Sequencer Decision**

For each of the following, decide: do you need just a lock, or do you need a lock
plus sequencer verification?
(a) Deciding which server is allowed to send emails from a newsletter service
(b) Deciding which server is the primary database writer where replicas check commands
(c) Deciding which job scheduler instance is active in a distributed cron system
(d) Deciding which cache instance is the "master" that rebuilds the cache after invalidation

**Exercise 6: Design a ZooKeeper-Based Lock Service**

ZooKeeper does not have built-in lock primitives. Design a distributed mutex using
ZooKeeper's ZNode API. You may use: create (ephemeral, sequential), delete, exists,
getChildren, watch. Your design must handle: concurrent lock requesters, lock release
on crash, no thundering herd.

(Hint: The standard recipe uses sequential ephemeral ZNodes and each waiter watches
only the immediately preceding node in the sequence, not all nodes.)

**Exercise 7: Chubby Under Load**

Your service uses Chubby for master election. Normally, master changes happen once
per day. One day, due to a flapping network, the master changes 100 times in an hour.
What happens to Chubby load? What happens to your service? Design a "cooldown"
mechanism to prevent rapid master churn.

**Exercise 8: Multi-Cell Chubby Architecture**

Your company has two datacenters. You run one Chubby cell in each datacenter. Service
instances run in both datacenters. Design a lock protocol that ensures global mutual
exclusion (no two instances across both datacenters hold the same lock simultaneously),
tolerates one datacenter being completely unreachable, and handles the case where both
datacenters can operate independently but with network partition between them.

---

## Homework

**Homework 1: Read the Original Paper**

Read Burrows' "The Chubby lock service for loosely-coupled distributed systems" (OSDI
2006). It is freely available online. Focus on Sections 2 (Design), 3 (The lock
service), and 5 (Use, surprises, and mistakes). Write a one-page summary of the
three most surprising things you learned that were not covered in this chapter.

**Homework 2: Run ZooKeeper Locally**

Install ZooKeeper locally and use the zkCli to:
(a) Create a permanent ZNode
(b) Create an ephemeral ZNode (connect as a client, create the node, then disconnect
    and verify the node is deleted)
(c) Implement a basic distributed mutex using sequential ephemeral ZNodes
(d) Observe the thundering herd by creating 10 clients all watching the same ZNode
    and deleting it, measuring how many simultaneous get requests hit ZooKeeper

**Homework 3: Implement Sequencer Token Verification**

Write a simple server (any language) that:
(a) Issues monotonically increasing sequencer tokens (just integers)
(b) Tracks the current valid sequencer for each "lock"
(c) Validates incoming tokens against the current valid token
Test it with two clients: one that gets a token, one that gets a higher token, and
the first client attempting to use its old token.

**Homework 4: Analyze etcd in Kubernetes**

If you have access to a Kubernetes cluster, use `etcdctl` to explore the etcd data
store:
(a) List all keys stored in etcd
(b) Watch a key for changes (e.g., watch a pod's status key and then delete the pod)
(c) Look at the lease mechanism: list leases and which keys are associated with them
(d) Examine what happens to ephemeral keys when you delete their associated lease
Write a comparison of etcd's lease mechanism vs. Chubby's session mechanism.

**Homework 5: Design a Distributed Job Scheduler**

Design a distributed job scheduler where multiple instances run, exactly one is the
scheduler (master) at a time, and jobs must not be run twice even during a master
transition. Use Chubby/ZooKeeper/etcd as the coordination primitive. Write a design
document that covers: master election mechanism, sequencer use in job dispatch,
handling of in-flight jobs during master transition, and recovery from split-brain.

---

## KEY TAKEAWAYS

```
╔═══════════════════════════════════════════════════════════════════════╗
║                    CHUBBY KEY TAKEAWAYS                               ║
╠═══════════════════════════════════════════════════════════════════════╣
║                                                                       ║
║  1. WHAT CHUBBY IS                                                    ║
║     A Paxos-replicated lock service with a file-like API.             ║
║     Five replicas per cell. Tolerates two simultaneous failures.      ║
║     Provides coarse-grained locking, not fine-grained.                ║
║                                                                       ║
║  2. THE THREE CORE MECHANISMS                                         ║
║     Sessions: long-lived authenticated connections, maintained via    ║
║               keepalives every 12 seconds                             ║
║     Sequencer: monotonically increasing token issued per lock         ║
║                acquisition; fences out stale lock holders             ║
║     Ephemeral nodes: auto-deleted when session ends; enables          ║
║                      service discovery                                ║
║                                                                       ║
║  3. THE SAFETY GUARANTEE                                              ║
║     Even if two servers both believe they hold the same lock          ║
║     simultaneously, downstream services verify sequencer tokens       ║
║     and reject the stale one. No data corruption occurs.              ║
║                                                                       ║
║  4. THE JEOPARDY PATTERN                                              ║
║     When a client loses contact with Chubby, it enters jeopardy.     ║
║     It does NOT immediately release locks. It has a 45-second grace  ║
║     period to reconnect. If reconnection succeeds, session is saved.  ║
║     If grace period expires, session is terminated and state rebuilt. ║
║                                                                       ║
║  5. THE THUNDERING HERD                                               ║
║     Releasing a popular lock notifies all watchers simultaneously.   ║
║     Solution: random backoff + limit the number of active watchers.  ║
║                                                                       ║
║  6. THE FAMILY TREE                                                   ║
║     Chubby (2006) → ZooKeeper (2008) → etcd (2013)                   ║
║     All solve the same problem. ZooKeeper = open-source Chubby.       ║
║     etcd = modern Raft-based equivalent used by Kubernetes.           ║
║                                                                       ║
║  7. WHERE CHUBBY APPEARS IN INTERVIEWS                                ║
║     Master election: GFS master, Bigtable master, Borg scheduler      ║
║     Service discovery: tablet server registration, chunk server list  ║
║     Configuration: ACLs, cluster membership, small config files       ║
║                                                                       ║
║  8. L6 vs L5 MARKER                                                   ║
║     L5: "Use ZooKeeper for leader election."                          ║
║     L6: "Use a Paxos-based lock service with session keepalives,      ║
║          ephemeral nodes for liveness, sequencer tokens for fencing,  ║
║          and a lock delay between revocation and re-grant."           ║
║                                                                       ║
║  9. THE THREE INCIDENTS                                               ║
║     Datacenter partition: sequencer tokens prevented corruption.      ║
║     Thundering herd: 500 simultaneous acquires overwhelmed Chubby.   ║
║     Keepalive starvation: main thread blocked keepalive thread;       ║
║                           stale master ran without sequencer fencing. ║
║                                                                       ║
║  10. DESIGN PRINCIPLES                                                ║
║      Correctness > Performance (Paxos, not a simple DB)              ║
║      Coarse-grained locking (held for hours, not milliseconds)        ║
║      Advisory locks + sequencer tokens (not mandatory locks)          ║
║      Client caching (for performance without sacrificing correctness) ║
║      Graceful degradation (services survive brief Chubby downtime)   ║
╚═══════════════════════════════════════════════════════════════════════╝
```

---

## Glossary

| Term | Definition |
|------|------------|
| Advisory lock | A lock that clients voluntarily respect; not enforced by the infrastructure intercepting accesses |
| Chubby cell | A 5-replica Paxos group forming one Chubby deployment; one per datacenter |
| Coarse-grained lock | A lock held for a long time (hours) on a large resource (the master role) vs. a fine-grained lock held for milliseconds on a small resource (one DB row) |
| Ephemeral node | A Chubby file that is automatically deleted when the client session that created it ends |
| Jeopardy state | The period when a Chubby client has lost contact with the cell and does not know if its session is still valid |
| Keepalive | Periodic RPC from client to Chubby cell proving the client is still alive; failure to keepalive within the lease duration expires the session |
| Lease duration | The time window (default 12 seconds) within which a client must send a keepalive to maintain its session |
| Lock delay | A brief period after a lock is released during which no new client can acquire it; allows in-flight commands from the old holder to be rejected before new commands start |
| Master lease | A time-bounded guarantee that allows the Chubby master replica to serve reads from local state without running Paxos |
| Paxos | The consensus algorithm Chubby uses to ensure all five replicas agree on lock state |
| Sequencer token | A monotonically increasing number issued per lock acquisition; downstream services verify it is still valid before executing commands |
| Session | The long-lived authenticated connection between a Chubby client and the cell; all locks and ephemeral nodes belong to a session |
| Split-brain | The dangerous state where two servers simultaneously believe they are the authoritative master |
| Thundering herd | The problem where many clients simultaneously react to a shared event (like a lock release), overwhelming the system |
| ZAB | ZooKeeper Atomic Broadcast; a Paxos-like consensus protocol used by ZooKeeper |

---

---

## Part 12 (Extended): Chubby Client Library Internals

### 12.3 How the Client Library Handles Caching

The Chubby client library is not just a thin RPC wrapper. It contains significant
logic to reduce load on the Chubby cell through caching. This caching is essential
to making Chubby practical at Google's scale — without it, every GFS chunk server
verifying a sequencer token would require an RPC to the Chubby cell, and at Google's
request rates this would be millions of RPCs per second to a service designed to
handle thousands.

The client library caches two categories of data:

**Lock state cache**: The client library caches which locks are currently held and
by which session. When other clients ask "is the GFS master lock held?" the library
can answer from its local cache without going to the Chubby cell. The cache is kept
consistent via invalidation notifications: when the lock state changes, the Chubby
master sends an invalidation to all clients that have that lock state cached. Clients
must acknowledge the invalidation before the Chubby master considers the change
committed.

This creates a two-phase update: (1) Chubby sends invalidations to all caching clients,
(2) clients acknowledge, (3) Chubby commits the change. Only after step 3 is the
change visible. This ensures that all clients see a consistent view — you never have
one client seeing "lock is free" while another sees "lock is held by server-42."

**File content cache**: Small file contents (like the master's address stored in a
lock file) are cached in the client library. Reads of frequently-accessed files are
served from cache. Invalidations work the same way as lock state cache invalidations.

The practical effect: in a large Google deployment, the Chubby cell might be serving
only a few thousand RPCs per second despite tens of thousands of client processes,
because the vast majority of reads hit the local client cache.

### 12.4 The Proxy and Partitioning Architecture

For very large deployments, the direct client-to-cell connection model runs into
scalability limits. Each client maintains a session, which requires memory and
processing on the Chubby master. With tens of thousands of clients, session management
overhead becomes significant.

The Chubby paper describes two techniques for scaling:

**Proxies**: A proxy server sits between clients and the Chubby cell. Multiple clients
connect to the proxy rather than directly to the cell. The proxy maintains a single
session with the Chubby cell on behalf of all its clients. From the Chubby cell's
perspective, it sees one session instead of thousands. The proxy handles client
multiplexing and local caching.

The tradeoff: the proxy becomes a single point of failure for all its clients. If the
proxy crashes, all its clients lose their Chubby connection simultaneously. You need
multiple proxies with client-side load balancing to mitigate this.

**Partitioning**: The Chubby namespace is divided into shards, with different shards
served by different Chubby cells. For example, `/ls/cell-gfs/...` is served by
the GFS Chubby cell and `/ls/cell-bigtable/...` is served by the Bigtable Chubby
cell. Different teams' services use different cells, so one team's traffic does not
affect another's.

The naming convention `ls/<cell-name>/...` in the Chubby path reflects this partitioning.
The cell name in the path tells the client library which Chubby cell to connect to.
This is how Chubby scales from a single shared service to a federated set of
specialized cells.

### 12.5 Monitoring and Operational Considerations

Operating Chubby in production requires monitoring specific metrics that are unique
to lock services:

**Jeopardy events per cell per hour**: If this number spikes, the Chubby cell is
having trouble (network issues, overload, master failover). A healthy cell has near-zero
jeopardy events.

**Lock acquisitions per second**: Should be low (consistent with coarse-grained
locking). Spikes indicate either a thundering herd event or misuse (fine-grained locking).

**Session count**: Should grow slowly as services scale. Sudden drops indicate mass
disconnections (possible Chubby master failover or network event).

**Paxos rounds per second**: Each write (lock acquisition, lock release, file write)
requires a Paxos round. This is the true write throughput of the Chubby cell.

**Cache hit rate**: Should be very high (>99%). A low cache hit rate means clients
are generating more Chubby load than expected, possibly due to incorrect cache
invalidation or clients not using the library correctly.

**Client library version distribution**: Old client library versions may have bugs
in jeopardy handling or session management. Keeping all clients on current versions
is operationally important.

---

### Part 12 Brainstorming Questions

**Q: How does the cache invalidation protocol interact with Paxos? If a client is
slow to acknowledge an invalidation, does it block Paxos?**

Yes, effectively — the Chubby master must collect acknowledgments from all caching
clients before committing a change. A slow client delays the commit. Chubby handles
this by giving clients a limited time window to acknowledge. If a client does not
acknowledge within the window, its cache is forcibly invalidated (the client is told
"your cache is no longer valid, re-read from source"), and the commit proceeds without
waiting for that client.

This is a graceful degradation: the system does not get permanently blocked by a
slow client. The slow client experiences a temporary degradation (must re-read from
Chubby instead of from cache) but does not hold up other clients. In practice,
cache invalidations happen quickly because the client library prioritizes them, and
forced invalidations are rare.

**Q: What happens if the proxy crashes? How do its clients recover?**

Proxy crash is treated like a Chubby cell master failover from the clients' perspective.
Clients lose their connection to the proxy (and through it, their Chubby session).
They enter jeopardy state and try to reconnect. Since multiple proxies exist (for
fault tolerance), clients re-resolve DNS for the proxy address, connect to a different
proxy, and re-establish their Chubby session through the new proxy.

The key difference from direct cell connection: if the proxy crash coincides with a
network partition between the proxy and the cell, clients might reconnect to a new
proxy but that proxy might also be unable to reach the cell. The recovery path is
the same (jeopardy → grace period → session expiry if unreachable), but the failure
mode is more complex. Proxy deployments require careful monitoring of proxy-to-cell
connectivity, not just client-to-proxy connectivity.

**Q: In Chubby's partitioning model, what if a service needs locks from two different
cells simultaneously?**

A client can hold sessions with multiple Chubby cells simultaneously. The client
library supports this — each cell has its own session, its own keepalive thread,
and its own cache. A service that needs locks from cells A and B simply opens sessions
with both cells concurrently.

The complication is transactional consistency across cells. If you need to atomically
acquire a lock in cell A and a lock in cell B (both or neither), Chubby provides
no cross-cell transaction. You must implement two-phase locking manually: acquire A's
lock, then acquire B's lock, and if B's acquisition fails, release A's lock and retry.
This is complex and prone to deadlock (if another process acquires B then A while you
are acquiring A then B). The standard advice: avoid cross-cell locking if possible
by carefully choosing which locks live in which cell.

---

## Appendix: Paxos in Plain Language

### A.1 Why Consensus Is Hard

Consensus sounds simple: "everyone agrees on the same value." But in a distributed
system where messages can be lost, servers can crash, and there is no shared clock,
achieving consensus is provably difficult.

The FLP impossibility result (Fischer, Lynch, Paterson, 1985) proves that in an
asynchronous distributed system (where message delays are unbounded), no deterministic
algorithm can guarantee consensus in the presence of even one faulty process. This
seems to doom all consensus algorithms.

The escape hatch: real networks are not purely asynchronous. Message delays are
usually bounded (within a few seconds), even if not perfectly predictable. Paxos
works correctly in the common case (bounded delays) and degrades gracefully (does
not make incorrect decisions) when delays are unusually large.

### A.2 Paxos Step by Step with a Concrete Example

Let's say five Chubby replicas are trying to agree on who should be the new Chubby
cell master. The replicas are R1, R2, R3, R4, R5. R1 wants to become master.

**Phase 1a (Prepare)**: R1 picks a ballot number N=7 (must be larger than any
previously used ballot). R1 sends "PREPARE(7)" to all replicas.

**Phase 1b (Promise)**: Each replica that receives PREPARE(7) responds with
"PROMISE(7, previous_accepted)" if 7 is the highest ballot they have seen. They
promise not to accept any proposal with a ballot number less than 7. If a replica
has already accepted a value (say, from a previous round), it includes that value
in its promise so R1 knows about it.

**Phase 2a (Accept)**: R1 receives promises from R1, R2, R3 (a majority of 5).
If any promise included a previously accepted value, R1 must propose that value.
Otherwise, R1 proposes its desired value: "I (R1) should be master." R1 sends
"ACCEPT(7, R1-is-master)" to all replicas.

**Phase 2b (Accepted)**: Each replica that receives ACCEPT(7, R1-is-master) and
has not promised a higher ballot accepts it and responds "ACCEPTED(7, R1-is-master)."

**Commit**: R1 receives ACCEPTED from R1, R2, R3 (majority). The value "R1 is master"
is committed. R1 sends COMMIT to all replicas. Consensus achieved.

### A.3 What Paxos Guarantees

**Safety** (never violated, even with arbitrary failures):
No two replicas ever commit different values for the same slot. If "R1 is master" is
committed, no other replica can commit "R2 is master" for the same election slot.

**Liveness** (guaranteed only with eventually stable network):
If a majority of replicas are alive and can communicate, Paxos will eventually reach
a decision. If the network is partitioned indefinitely, Paxos may not terminate
(FLP impossibility applies), but it will never make an incorrect decision.

This asymmetry — safety is unconditional, liveness is conditional — is the right
tradeoff for a lock service. You would rather the lock service occasionally be
unavailable (cannot make a decision) than ever be incorrect (makes two conflicting
decisions).

### A.4 Multi-Paxos: The Optimized Version Chubby Uses

Basic Paxos requires two round trips (Prepare + Accept) for every decision. For a
lock service making thousands of decisions per second, this is expensive.

Multi-Paxos optimizes by electing a stable leader (the Chubby master) who can skip
Phase 1 for multiple consecutive decisions. Once a leader is established with a given
ballot number, it can send ACCEPT directly without PREPARE for as long as it remains
leader. This reduces the common-case cost to one round trip.

The leader's authority is bounded by the master lease (as described in Part 3). As
long as the leader holds the lease, it can serve reads without any Paxos round, and
serve writes with one Paxos round (just Phase 2). The full two-phase protocol is only
needed when a new leader is being elected (which is rare — only on master crash or
deliberate failover).

---

*Chapter 83 complete. Next: Chapter 84 — Spanner: Google's Globally Distributed Database.*
