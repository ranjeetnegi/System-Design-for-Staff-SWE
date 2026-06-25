# Chapter 83: GFS — Google File System

> In 2003, Google engineers published a paper that described how they stored petabytes of data on thousands of cheap machines that broke all the time. That paper quietly changed how the entire industry thinks about distributed storage. This chapter explains exactly how GFS works, why it was designed the way it was, and how to talk about it in a Google Staff Engineer interview.

---

## Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CHAPTER 83 AT A GLANCE                           │
│                                                                     │
│  Part 1:  The Problem GFS Solved       — why it was built           │
│  Part 2:  The Three Players            — Master, ChunkServers,      │
│                                          Client                     │
│  Part 3:  Files and Chunks             — the storage model          │
│  Part 4:  The Master in Depth          — what it knows, what it     │
│                                          doesn't                    │
│  Part 5:  The Write Path               — how data gets in           │
│  Part 6:  The Read Path                — how data gets out          │
│  Part 7:  Fault Tolerance              — how GFS survives failure    │
│  Part 8:  Consistency Model            — what GFS does NOT          │
│                                          guarantee                  │
│  Part 9:  Limitations and What         — the single-master          │
│           Came After                     bottleneck, Colossus,      │
│                                          HDFS                       │
│  Part 10: Interview Application        — how to use GFS in an       │
│                                          interview                  │
│  Part 11: GFS vs Modern Object Storage — S3, GCS comparison         │
│                                                                     │
│  Real Life Incidents, Exercises, Homework at the end                │
└─────────────────────────────────────────────────────────────────────┘
```

**The one thing to remember:** GFS separated the metadata (who knows where everything is) from the actual data (where the bytes live). The Master only handles metadata. It never touches your actual data. That single separation is what made GFS work at scale.

---

## Part 1: The Problem GFS Solved

### The situation in 2003

Google was crawling the entire web and building a search index. Every day, they were processing tens of terabytes of web pages, link graphs, and index data. They needed to store it somewhere.

The obvious solution — buy expensive, reliable servers with RAID arrays and enterprise storage — was too expensive and too slow to scale. Google needed a storage system that could hold petabytes of data and handle thousands of read/write requests per second, at a cost they could actually afford.

**The key insight:** instead of spending money on hardware that doesn't fail, accept that hardware WILL fail and build software that handles it gracefully.

### The analogy

Imagine you are managing a library, but instead of solid bookshelves, you have IKEA bookshelves that break every few weeks. Individually, each shelf is unreliable. But if you make three copies of every book and spread them across different shelves in different rooms, then even when a shelf collapses, you still have two other copies of every book on that shelf. Your library stays open.

GFS is that copying system. It runs on thousands of cheap commodity machines (the IKEA bookshelves) and ensures every piece of data has copies on multiple machines so that individual machine failures don't cause data loss.

### What Google's workload looked like

GFS was designed for a very specific workload — Google's workload, in 2003:

```
┌─────────────────────────────────────────────────────────────────────┐
│                  GOOGLE'S 2003 STORAGE WORKLOAD                     │
│                                                                     │
│  Files:       Large (hundreds of MB to TB). Not millions of        │
│               small files. A web crawl produces big files.         │
│                                                                     │
│  Writes:      Mostly append-only. Nobody edits a web crawl file.  │
│               New data is added at the end.                        │
│                                                                     │
│  Reads:       Sequential, large. Programs scan entire files.       │
│               Nobody reads a random 4KB from the middle of a       │
│               web crawl.                                            │
│                                                                     │
│  Failures:    Expected and frequent. At thousands of machines,     │
│               at least one machine fails every day.                │
│                                                                     │
│  NOT in workload:                                                   │
│  ✗ Millions of tiny files (photos, emails)                         │
│  ✗ Random writes to middle of files                                │
│  ✗ Low-latency reads (GFS is optimized for throughput)             │
│  ✗ POSIX compliance (no atomic rename, no file locking)            │
└─────────────────────────────────────────────────────────────────────┘
```

This workload shaped every design decision in GFS. If you understand the workload, you understand why GFS looks the way it does.

### Intern → Staff Progression (Part 1)

| Level | How they think about the GFS problem |
|-------|--------------------------------------|
| **Intern** | "Use S3 or HDFS." Does not think about why GFS existed before those things. |
| **L3** | Knows GFS stores large files. Cannot explain what made GFS different from a standard filesystem. |
| **L4** | Understands the workload: large files, sequential reads, append-only writes. Connects workload to design. |
| **L5** | Can explain the core trade-off: reliability through software replication instead of hardware reliability. Can contrast GFS with a RAID array. |
| **L6** | Can explain WHY every design decision in GFS follows from the workload assumptions. Knows exactly which workloads GFS handles well and which it handles poorly. Can identify when a system they're designing is "GFS-shaped" and apply the same patterns. |

### Brainstorming Questions — Part 1

**Q: Why didn't Google just buy expensive, reliable storage hardware instead of building GFS?**

The scaling argument is simple math. At the scale Google was operating in 2003, enterprise-grade storage would have cost tens of millions of dollars per year and still wouldn't have kept up with Google's growth rate. Enterprise storage arrays scale vertically (you buy a bigger, more expensive unit) while GFS scales horizontally (you add more cheap machines). At petabyte scale, horizontal scaling is not just cheaper — it's the only option that works.

But there's a deeper point that matters for system design interviews: buying reliable hardware doesn't eliminate failures, it just makes them less frequent. At the scale of thousands of machines, even a 0.1% monthly failure rate means multiple machines fail every day. Enterprise hardware might have a 0.01% failure rate, but at Google's scale, that's still daily failures. You cannot design away failures at scale — you must design for them. GFS embraced this reality explicitly. This is the fundamental insight that shaped every subsequent large-scale distributed storage system.

The third argument is operational. Enterprise storage arrays are proprietary, hard to debug, and hard to operate at Google's pace of infrastructure change. Google needed a storage system they understood completely and could modify as their needs evolved. You cannot modify a vendor storage array's firmware. You can modify a system you wrote yourself.

---

### The Analogy Extended: GFS as a Library System

The library analogy introduced earlier can be extended to cover the entire GFS architecture precisely:

- **The library catalog (Master):** A single librarian keeps the complete catalog — which shelf holds which book, and how many copies exist. The librarian never carries books; they only look things up.
- **The books (chunks):** Each book is stored on a shelf. There are 3 copies of every book, on shelves in different sections of the library.
- **The shelves (ChunkServers):** The physical shelves that hold the books. Shelves can collapse (ChunkServer failure), and when one does, the librarian notes which books are now down to 2 copies and arranges for new copies to be made.
- **Library patrons (clients):** When a patron wants a book, they ask the librarian where it is (metadata lookup), then go directly to the shelf to pick it up (data read). The librarian doesn't walk with the patron to get the book.
- **The stamp card system (leases):** When someone wants to write in (annotate) a book, the librarian gives them a 60-minute "annotating pass" for that specific copy. Only one person can annotate a given copy at a time. If the annotator doesn't return the pass within 60 minutes, the librarian issues a new pass to someone else.
- **The catalog log (operation log):** Every time the librarian updates the catalog (new book added, book removed, copy moved), they write it in a log book first. If the librarian has a memory lapse, they can reconstruct the catalog by replaying the log.

This extended analogy maps every GFS component to something familiar, making it easy to explain GFS to a non-specialist without losing accuracy on any component.

### Common Interview Mistakes — Part 1

**Mistake 1: Saying "GFS is just HDFS with a different name."**
GFS and HDFS are siblings, not copies. They share the same high-level idea (single metadata node, many data nodes, large chunks) but differ in critical ways: GFS uses 60-second renewable leases to designate a primary ChunkServer, HDFS uses a single-writer model where only the client that opened a file for write can write to it. GFS's append semantics are more permissive (concurrent appends by multiple clients, with padding allowed). HDFS has stricter append semantics but adds block-level checksums and a block report protocol that differs from GFS heartbeats. Saying they are the same signals you haven't read either paper.

**Mistake 2: Assuming GFS was the only option in 2003.**
Candidates sometimes say "Google had to build GFS because nothing existed." NFS (Network File System) and SAN (Storage Area Network) systems existed in 2003. The reason Google built GFS was not absence of alternatives — it was that existing alternatives couldn't scale to Google's volume at Google's cost. Enterprise SAN systems with petabyte capacity would have cost tens of millions of dollars. NFS had no concept of fault-tolerant replication across hundreds of machines. Understanding WHY Google built something new (not just THAT they built it) is what L5+ answers sound like.

**Mistake 3: Saying the problem was "reliability" without being specific.**
"Commodity machines are unreliable" is too vague. The more precise claim is: at Google's scale in 2003, at least one machine failed per week per cluster. At 1,000 machines, even a 99.9% monthly uptime means 1 machine is down every day. The design principle is that the failure rate, multiplied by the cluster size, always produces a nonzero expected daily failure count. Hardware reliability improvements help but cannot reach zero failures at scale. The software must assume failures will happen and recover from them automatically without human intervention.

**Mistake 4: Not knowing the historical context.**
GFS was not just a technical paper — it was the first public description of a practical petabyte-scale distributed storage system. Before GFS, the industry had database storage, NFS mounts, and tape archives. GFS's publication in 2003 directly spawned HDFS (2006), which powered Hadoop, which drove the entire big data industry. When an interviewer asks about GFS, they are often testing whether you understand this lineage.

### The Origin Story: Why GFS Was Actually Built

In 2003, Google's web crawler was generating terabytes of data every day — HTML pages, link graphs, anchor text, metadata for every URL the crawler visited. Before GFS, Google stored this on a combination of raw disk partitions and a homegrown system sometimes called "BigFiles." Here is what that environment looked like:

**Daily machine failures.** Google's 2003 infrastructure was commodity x86 machines in cheap racks. These machines had ~5% annual failure rates — meaning in a cluster of 1,000 machines, about 50 machines would fail in a year. That's roughly one machine per week. When a machine holding crawl data failed, that data had to be recovered from backup tape, which was manual, slow, and unreliable.

**No automated recovery.** When a machine died, a human had to notice, diagnose whether the machine was really dead (or just temporarily unresponsive), identify what data it held, and coordinate restoration. This was operationally unsustainable at scale.

**Crawl throughput was constrained by storage.** The crawlers could download web pages faster than the storage system could reliably accept them. Storage was the bottleneck on the indexing pipeline — not network bandwidth, not CPU.

Google's engineers, led by Sanjay Ghemawat and Howard Gobioff, built GFS to solve this specific operational pain: automated failure detection, automated re-replication, and throughput-optimized storage for large sequential writes. Every design decision traces back to this concrete pain in 2003. When you understand the origin, you understand why GFS looks the way it does.

**The real incident:** In early 2003, before GFS was deployed cluster-wide, Google's crawling pipeline was limited to working on smaller batches of data specifically because large crawl runs would cause storage system failures mid-job that required manual intervention to recover. The crawlers were essentially working in a mode where they'd start a crawl, wait to see if storage held up, and manually rescue jobs that failed. This was the pain that made building GFS worth the engineering investment.

---

**Q: Google published the GFS paper publicly in 2003. Why would a company give away the design of a system this valuable? What did Google gain from publishing it?**

Publishing the GFS paper was a deliberate strategic decision, not an accident. By 2003, Google had already built GFS and deployed it internally — the competitive advantage came from HAVING a working petabyte-scale storage system, not from the DESIGN being secret. Competitors couldn't simply read the GFS paper and immediately build an equivalent system; they still needed the engineering effort, the operational experience, and the hardware investment. Publishing the design gave competitors the blueprint but not the execution capability.

What Google gained from publishing was significant. First, it established Google as the intellectual leader in distributed systems. The GFS paper was widely read and cited — it defined the vocabulary and conceptual framework that the entire distributed systems community now uses. This reputation helps Google recruit the best distributed systems engineers in the world. An engineer who wants to work at the frontier of distributed systems knows that Google is where that work happens.

Second, publishing created an ecosystem of open-source systems (HDFS, which powered Hadoop) that Google could benefit from indirectly. When universities and companies built on HDFS to process large datasets, they were validating the GFS model and producing engineers who thought in GFS terms. Those engineers were easier to onboard at Google. Third, published research gives Google engineers a way to receive external feedback on their designs through peer review and conference discussions — which can surface design issues that internal review might miss. Publishing is not charity; it's a calculated exchange of design for reputation, recruiting, and intellectual feedback.

---

**Q: GFS was designed in 2003. How would you design it differently today using cloud-native primitives?**

The biggest change would be to eliminate the single Master entirely and replace it with a distributed metadata service. In 2003, Google didn't have a battle-tested distributed metadata store they could use as a component — they built GFS first, and Bigtable (which could have served as the metadata store) was being built in parallel. Today, you have Bigtable, DynamoDB, Spanner, or even a well-configured Cassandra or TiKV cluster that can store metadata with strong consistency and horizontal scalability. Colossus (GFS2) did exactly this: stored chunk metadata in Bigtable, eliminating the single-Master memory ceiling. If you were designing GFS from scratch today, the metadata tier would be a distributed key-value store from day one, not a single in-memory server.

The second major change would be to use erasure coding instead of 3x replication. 3x replication costs 300% of raw storage — for every 1TB of actual data, you use 3TB of disk. In 2003, this was acceptable because disks were cheap and erasure coding was computationally expensive (requiring significant CPU for encoding and decoding). Today, with modern CPUs and hardware erasure coding support, systems like Colossus and Ceph use Reed-Solomon codes (typically RS(6,3) or RS(10,4)) that achieve the same durability as 3x replication with only 150% overhead. For a petabyte-scale system, the storage cost savings from erasure coding are significant enough to justify the CPU overhead.

The third change would be to rethink the API entirely. GFS's API is POSIX-adjacent: open a file, read at an offset, append to a file. This API maps naturally to sequential access patterns but creates challenges for object storage patterns (upload a file atomically, access by URL). If you were designing for 2024 workloads, which include not just batch MapReduce but also serving ML models, storing training datasets, and backing web applications, you'd design a hybrid API: object storage semantics (atomic PUT/GET with strong consistency) as the primary interface, with an optional streaming/append interface for pipeline use cases. This is essentially what Google Cloud Storage (GCS) and Amazon S3 provide today — they learned from GFS's limitations and built more flexible APIs.

---

**Q: GFS was designed for large sequential files. What breaks if you use it for millions of small files?**

The chunk size is the problem. GFS breaks every file into 64MB chunks. If your file is 1KB, it still occupies one full 64MB chunk — wasting 99.99% of that chunk's capacity. Scale this to millions of small files and you have millions of 64MB chunks, almost all of them nearly empty. Storage utilization collapses. A cluster that could hold 10PB of actual data might only hold 100GB of small files efficiently.

The second problem is Master memory. The Master keeps the metadata for every chunk in memory: what chunk, which chunkservers hold it, what the lease status is. For a petabyte of large files, there might be 16 million chunks — each entry is a few hundred bytes, so that's a few GB of master memory. For a petabyte of 1KB files, there would be a trillion chunks — millions of times more metadata than the Master can possibly hold in memory. The Master would run out of memory before the cluster ran out of storage.

This is why Google later built dedicated systems for small-file storage: Colossus (GFS2) with a distributed metadata tier, and even more specialized systems for serving billions of small images and thumbnails. GFS was not the wrong tool — it was the right tool for the right problem. The mistake would be using it for a problem it wasn't designed for. In interviews, this teaches a crucial lesson: always understand the workload assumptions behind a technology before choosing it.

---

## Part 2: The Three Players

### The architecture in one sentence

GFS has three components: a single **Master** that knows where everything is, many **ChunkServers** that actually store the data, and a **Client** library that applications use to read and write files.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    GFS ARCHITECTURE OVERVIEW                        │
│                                                                     │
│                      ┌──────────────┐                              │
│                      │    MASTER    │                              │
│                      │              │                              │
│                      │ • File→chunk │                              │
│                      │   mapping    │                              │
│                      │ • Chunk→CS   │                              │
│                      │   mapping    │                              │
│                      │ • Access     │                              │
│                      │   control    │                              │
│                      └──────┬───────┘                              │
│                             │                                       │
│           ┌─────────────────┼─────────────────┐                   │
│           │  metadata only  │                  │                   │
│     ┌─────▼──────┐          │           ┌──────▼──────┐            │
│     │   CLIENT   │          │           │   CLIENT    │            │
│     │  (library) │          │           │  (library)  │            │
│     └─────┬──────┘          │           └──────┬──────┘            │
│           │                 │                  │                   │
│           │   data directly │                  │ data directly     │
│           └──────┬──────────┘──────────────────┘                   │
│                  │                                                  │
│     ┌────────────┼────────────────────────────┐                   │
│     │            │                            │                   │
│  ┌──▼────┐   ┌───▼───┐   ┌────────┐   ┌──────▼──┐                │
│  │  CS-1 │   │  CS-2 │   │  CS-3  │   │  CS-4   │  ...           │
│  │(chunk │   │(chunk │   │(chunk  │   │(chunk   │                │
│  │server)│   │server)│   │server) │   │server)  │                │
│  └───────┘   └───────┘   └────────┘   └─────────┘                │
│                                                                     │
│  KEY: Master handles metadata. ChunkServers handle data.           │
│       Client talks to Master for metadata, ChunkServers for data.  │
│       Master NEVER handles data. This is the core design.          │
└─────────────────────────────────────────────────────────────────────┘
```

### The Master

The Master is a single machine (there is exactly one Master per GFS cluster) that stores all the metadata:

- **File namespace**: the directory tree of filenames
- **Access control**: who can read/write each file
- **File-to-chunk mapping**: file X is made up of chunks C1, C2, C3...
- **Chunk-to-chunkserver mapping**: chunk C1 is on ChunkServers 12, 47, and 89

The Master does NOT store actual data. It never sees the bytes of your files. It only sees the map of where those bytes live.

Everything in Master's memory is also written to an operation log on disk (more on this in Part 4). If the Master crashes, it can replay the log to recover.

### The ChunkServers

ChunkServers are regular Linux machines with large hard drives. Each ChunkServer stores chunks as plain files on its local filesystem. It does not have any special knowledge of what those chunks contain — a chunk is just a blob of bytes to the ChunkServer. The ChunkServer does not know which GFS file a chunk belongs to.

There are typically hundreds to thousands of ChunkServers in a GFS cluster. They communicate with the Master via heartbeats (regular check-in signals) and respond to data requests from Clients.

### The Client

The GFS Client is a library that applications link against. When your program says "open file /crawl/2024-01-15/shard-001", the Client library handles the GFS protocol: talking to the Master for metadata, talking to ChunkServers for data. The application code doesn't need to know anything about chunks or chunkservers.

The Client caches metadata from the Master to avoid talking to the Master on every operation. If the Client knows that file X's first chunk lives on ChunkServer 12, it talks directly to CS-12 on the next read — no Master involved.

### The crucial separation

**The Master knows where data is. ChunkServers hold the data. These two things are completely separate.**

This separation is the most important architectural decision in GFS. It means:
1. The Master is never a data bottleneck — it handles only tiny metadata messages, not file data.
2. ChunkServers can scale independently — add more ChunkServers for more storage.
3. A ChunkServer can crash without involving the Master — the Master just re-replicates that chunk from another copy.

### Intern → Staff Progression (Part 2)

| Level | Understanding of the three-player architecture |
|-------|------------------------------------------------|
| **Intern** | "There's a server that stores files." |
| **L3** | Knows there's a master and multiple storage servers. Cannot explain what each is responsible for. |
| **L4** | Understands the metadata/data separation. Can draw the diagram. May not know the Client is a library, not a separate server. |
| **L5** | Can explain why the separation exists (Master out of data path = no bottleneck). Can explain the implications of a single Master (single point of failure for metadata). |
| **L6** | Can design a system that uses the GFS pattern. Can explain what breaks if you put the Master in the data path. Can explain the implications of the Master's in-memory data structure for scaling. Knows what questions to ask when choosing this pattern. |

### Detailed Message Sequence: File Open + First Read

The following diagram shows the exact numbered sequence of messages between Client, Master, and ChunkServer during a file open followed by the first read. This is the sequence you should be able to narrate in an interview without looking at notes.

```
CLIENT                     MASTER                    CHUNKSERVER (CS-55)
  |                          |                              |
  |  1. OPEN /crawl/shard-001|                              |
  |  (filename + mode=READ)  |                              |
  |------------------------->|                              |
  |                          |                              |
  |  2. METADATA RESPONSE    |                              |
  |  file exists             |                              |
  |  chunks: [C4a91b2f,      |                              |
  |           C7d23e8c,      |                              |
  |           C1f98a3d,      |                              |
  |           Cb72c5e1]      |                              |
  |  (access control passed) |                              |
  |<-------------------------|                              |
  |                          |                              |
  | [Client stores chunk list in memory. No chunk           |
  |  locations yet — fetched lazily on first access]        |
  |                          |                              |
  |  3. WHERE IS CHUNK 0?    |                              |
  |  (chunk handle C4a91b2f) |                              |
  |------------------------->|                              |
  |                          |                              |
  |  4. CHUNK LOCATIONS      |                              |
  |  C4a91b2f:               |                              |
  |    CS-12 (same rack)     |                              |
  |    CS-47 (rack B)        |                              |
  |    CS-55 (rack C)        |                              |
  |  version: 42             |                              |
  |<-------------------------|                              |
  |                          |                              |
  | [Client caches {C4a91b2f -> [CS-12, CS-47, CS-55]}     |
  |  Client picks CS-55 (assume same rack for this example] |
  |                          |                              |
  |  5. READ REQUEST         |                              |
  |  chunk=C4a91b2f          |                              |
  |  offset=0, length=1MB   |---------------------------->|
  |                          |                              |
  |                          |              [CS-55 reads    |
  |                          |               chunk file     |
  |                          |               from local FS] |
  |                          |              [CS-55 verifies |
  |                          |               checksums for  |
  |                          |               each 64KB block|
  |                          |               in the range]  |
  |                          |                              |
  |  6. DATA RESPONSE        |                              |
  |  [1MB of bytes]          |<----------------------------|
  |<-------------------------|                              |
  |                          |                              |
  | [For subsequent reads of the same chunk: steps 5-6     |
  |  only. Steps 3-4 are skipped until cache TTL expires]  |
  |                          |                              |
  | [For reads on chunk 1 (C7d23e8c): if still in cache    |
  |  from step 2 metadata response, skip to step 5.        |
  |  If not in cache: repeat steps 3-4 for C7d23e8c]       |
```

Key observations from this diagram that interviewers probe:
- The Master is involved in steps 1-2 (file open, gets chunk list) and steps 3-4 (first access to each chunk). After that, the Master is completely out of the picture.
- The Client decides which ChunkServer to read from (closest/fastest). The Master does not assign the ChunkServer — it just provides the list.
- Checksum verification (step 5/6) happens on the ChunkServer, invisible to the Client unless it fails.
- The Client's cache of chunk locations (from step 4) has a TTL. After the TTL, step 3-4 are repeated to get fresh locations.

### Common Interview Mistakes — Part 2

**Mistake 1: Thinking the Master is in the data path.**
This is the single most common GFS interview error. Candidates say things like "the client reads from the Master, which forwards to the ChunkServer." The Master does NOT forward data. It only answers "where is this chunk?" and then steps aside. After the metadata exchange, the client talks directly to ChunkServers. The Master never sees a single byte of file data.

**Mistake 2: Thinking the GFS Client is a separate server process.**
The GFS Client is a library — a `.so` file (shared object) or `.a` file (static library) that applications link against. When a Google MapReduce job accesses a GFS file, the MapReduce worker process itself IS the GFS client — the library is linked into the worker binary. There is no separate "GFS client server" running as an independent process on each machine. This matters because it means the GFS client's cache is per-process, not shared across processes on the same machine.

**Mistake 3: Assuming the Master knows real-time chunk locations with perfect accuracy.**
The Master's chunk-to-ChunkServer mapping is built from ChunkServer heartbeat reports and is rebuilt from scratch on restart. Between heartbeats, the Master's view of chunk locations can be slightly stale. If a ChunkServer just went down 20 seconds ago and the heartbeat timeout is 30 seconds, the Master still thinks that ChunkServer is alive. The Client might try to read from the dead ChunkServer, fail, and then retry with another replica. The GFS design accepts this brief inconsistency as a trade-off for the simplicity of heartbeat-based detection.

**Mistake 4: Confusing "shadow master" with "standby master."**
The shadow master in GFS is explicitly read-only — it serves only cached metadata reads (file namespace, chunk lists) when the primary Master is down. It does NOT take over as the primary Master automatically. There is no automatic failover in the original GFS design. The primary Master is restarted and replays its operation log. The shadow master is there to keep reads working during the recovery window. Many modern systems (like ZooKeeper-based NameNode in HDFS HA) do have automatic failover — but that's a later design, not GFS's original design.

### Brainstorming Questions — Part 2 (Additional)

**Q: The GFS client caches chunk locations with a TTL. What is the right TTL value, and what are the trade-offs of a longer vs. shorter TTL?**

The TTL controls how often the client refreshes its chunk location cache from the Master. A longer TTL means fewer Master roundtrips (better scalability, less Master load) but also means the client holds stale data for longer after a ChunkServer change (failure, re-replication, decommission). A shorter TTL means fresher data but more Master load.

For GFS's workload (large sequential batch reads), the right TTL is longer — on the order of minutes rather than seconds. Here is the reasoning: in a 30-minute MapReduce job that reads 100 chunks sequentially, each chunk's TTL only matters at the start when the chunk location is first fetched. After the first fetch, the client reads each chunk completely and moves to the next — it doesn't re-read the same chunk, so the TTL never expires within the job for chunks already read. The TTL only matters for very long-running jobs or hot chunks that are accessed many times over a long period.

The practical recommendation from the GFS paper is to set the TTL based on the lease duration. Since ChunkServer primary designations change at most every 60 seconds (the lease duration), there's no point in having a client TTL shorter than 60 seconds. A TTL of 2-5 minutes is a reasonable balance: fresh enough to detect ChunkServer failures within a few minutes, long enough to drastically reduce Master load in large clusters. For the failure case where a cached ChunkServer is down, the client handles it by trying another cached location, not by re-fetching from Master — so even a "stale" cache entry is handled gracefully.

### Brainstorming Questions — Part 2

**Q: Why is there only one Master? Why not multiple Masters for redundancy?**

Having a single Master makes the design dramatically simpler. With one Master, there is exactly one authoritative source of truth for where every chunk lives. A client that asks "where is chunk C1?" gets one answer. If you had multiple Masters, you would need to keep them synchronized — and that is the hard distributed systems problem of distributed consensus (how do you ensure all Masters agree on the same metadata state?). Google deliberately chose simplicity over redundancy for the Master's active role.

But the single Master is not a single point of failure for data. The data lives on ChunkServers, which are replicated. If the Master crashes, all the data is safe on ChunkServers. What you lose temporarily is the ability to do metadata operations — you cannot open new files, you cannot get chunk locations you don't already have cached. GFS mitigates this with a "shadow master": a read-only replica of the Master that serves cached metadata even when the primary Master is down. Clients can still read files they have cached metadata for.

For Google's batch processing workload, brief metadata unavailability was acceptable. A MapReduce job would wait a few minutes for the Master to recover and resume. This trade-off — simplicity and correctness for metadata over constant availability — was explicitly chosen by the GFS designers based on their workload.

---

**Q: How does the GFS client library know that a ChunkServer has failed and the metadata is stale?**

The GFS client library learns about ChunkServer failures the hard way: it tries to connect and gets an error. There is no push notification from the Master to clients saying "hey, CS-55 just went down." The client has a cached chunk location saying chunk C7d23e8c is on CS-55. It tries to open a TCP connection to CS-55. CS-55 doesn't respond (connection refused, connection timeout, or RST packet). The client library detects this at the TCP level — the connection fails.

At this point, the client library knows the cached location is stale for CS-55 specifically. It has two copies of this chunk on CS-12 and CS-47 (also from the cached metadata). It tries CS-12 next. If CS-12 responds, the read succeeds. The failed CS-55 location is removed from the client's in-memory cache for this chunk. The client continues without any communication with the Master at all — because it has two other valid cached locations.

The client only goes back to the Master when ALL cached locations for a chunk fail (all three replicas appear down), or when the cache TTL expires and the client needs fresh locations for a new operation. This design keeps the Master completely out of the read path for failure recovery when alternatives exist in the cache. The Master learns about CS-55's failure independently via missing heartbeats. There is no coordination between the client's failure detection and the Master's failure detection — they run independently, and that's intentional.

---

**Q: A ChunkServer doesn't know which GFS files its chunks belong to. How does the Master know which chunks are orphaned (no longer referenced by any file)?**

The Master tracks file-to-chunk mappings. When a file is deleted, the Master marks those chunks as deletable. But it doesn't delete them immediately — GFS uses lazy deletion (garbage collection). The Master periodically scans its chunk metadata and identifies chunks that are not referenced by any live file. These orphaned chunks are then garbage collected by sending delete commands to the ChunkServers that hold them.

This lazy deletion design has an important side effect: disk space is not immediately reclaimed when you delete a file. The disk space is reclaimed at the next garbage collection cycle, which might run every few hours. This surprises engineers used to filesystems where deleting a file immediately frees its space. In exchange, lazy deletion gives GFS nice properties: accidental deletes can be reversed for a window of time (the chunk is still on disk, just marked deletable), and the delete operation itself is fast (just a metadata update on the Master, no disk I/O).

In interviews, this is an interesting design pattern to reference: garbage collection as a first-class architectural decision, not just a language runtime feature. Many distributed systems use lazy cleanup for similar reasons.

---

## Part 3: Files and Chunks

### What is a chunk?

A chunk is a fixed-size piece of a file. In GFS, every chunk is 64 megabytes.

Think of it like a moving company. When you move a large piece of furniture (a file), the movers don't carry it as one giant awkward piece. They take it apart into manageable boxes (chunks), label each box, and transport them separately. At the destination, they reassemble the furniture by putting the boxes back in order.

GFS does the same thing: every file is broken into 64MB boxes (chunks). Each box has a label (a 64-bit chunk handle). The boxes are stored separately on different machines. The Master knows which boxes make up each piece of furniture (file) and in what order.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    FILE-TO-CHUNK MAPPING                            │
│                                                                     │
│  File: /crawl/2024-01-15/shard-001  (200MB total)                  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Chunk 0 (bytes 0–64MB)       Handle: C4a91b2f               │   │
│  │ Chunk 1 (bytes 64–128MB)     Handle: C7d23e8c               │   │
│  │ Chunk 2 (bytes 128–192MB)    Handle: C1f98a3d               │   │
│  │ Chunk 3 (bytes 192–200MB)    Handle: Cb72c5e1 [partial]     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  The Master stores this mapping.                                    │
│  Each chunk is stored on 3 ChunkServers (replicated).              │
│  The client reads byte range → converts to chunk index → fetches.  │
└─────────────────────────────────────────────────────────────────────┘
```

### Why 64MB?

64MB is a deliberate choice based on Google's workload. The design reasoning:

**Larger chunks = fewer metadata lookups.** A 1GB file needs only 16 chunks. The client fetches chunk locations from the Master once and then reads all 16 chunks directly from ChunkServers. If chunks were 1MB, the same file would need 1,024 chunks — more Master interactions, more TCP connections, more overhead.

**Larger chunks = more persistent connections.** When a client reads a chunk, it keeps the TCP connection to that ChunkServer open. With large chunks, one connection is reused for a long time. With tiny chunks, you'd be constantly opening and closing connections — each with its own setup overhead.

**The downside:** internal fragmentation. A 1KB file wastes 63.999MB of its chunk. GFS accepted this because its workload had large files, not small ones.

**Concrete numbers:**
- A 1TB file = 16,384 chunks (64MB each)
- Master metadata per chunk ≈ 64 bytes (handle + CS locations + version)
- Master memory for 1TB file ≈ 16,384 × 64 bytes ≈ 1MB
- Master can hold metadata for ~1 petabyte in ~1GB of memory

### Replication: three copies by default

Every chunk is stored on three ChunkServers by default. The three ChunkServers are chosen to be:
- On different machines (so one machine failure doesn't lose the chunk)
- On different racks (so one rack power failure doesn't lose the chunk)
- Geographically on the same network (to keep replication fast)

```
┌─────────────────────────────────────────────────────────────────────┐
│                      CHUNK REPLICATION                              │
│                                                                     │
│  Chunk C4a91b2f lives on:                                          │
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                       │
│  │  CS-12   │   │  CS-47   │   │  CS-89   │                       │
│  │ Rack A   │   │ Rack B   │   │ Rack C   │                       │
│  │ PRIMARY  │   │ secondary│   │ secondary│                       │
│  └──────────┘   └──────────┘   └──────────┘                       │
│                                                                     │
│  CS-12 crashes → Master re-replicates from CS-47 to CS-99          │
│  Rack A loses power → Master re-replicates from CS-47, CS-89       │
│                                                                     │
│  At 3x replication: survives any 2 simultaneous failures           │
└─────────────────────────────────────────────────────────────────────┘
```

### Chunk version numbers

Every chunk has a version number. When the Master grants a write lease to a ChunkServer, it increments the version number. If a ChunkServer was offline during a write, it will have the old version number for that chunk. When it comes back online and reports its chunks to the Master, the Master detects the stale replica (old version number) and marks it for garbage collection. This is how GFS detects and removes stale replicas automatically.

### Intern → Staff Progression (Part 3)

| Level | Understanding of chunks and replication |
|-------|----------------------------------------|
| **Intern** | "Files are split into pieces and stored on multiple machines." |
| **L3** | Knows chunks are 64MB. Cannot explain why. Cannot explain version numbers. |
| **L4** | Understands 64MB choice (fewer metadata lookups). Understands 3-way replication for fault tolerance. |
| **L5** | Understands cross-rack placement. Understands version numbers for stale replica detection. Can calculate Master memory usage from chunk count. |
| **L6** | Can explain the full trade-off: chunk size, replication factor, placement policy as a design space. Can calculate when the Master runs out of memory. Can redesign the chunk layer for a different workload (e.g., small files require very different chunk sizing strategy or a separate metadata tier). |

### Chunk Placement Policy: Rack-Awareness

GFS does not place the three replicas of a chunk randomly. It uses a rack-aware placement policy with the following rules:

1. **No two replicas of the same chunk on the same machine.** (Obvious — machine failure would lose both.)
2. **At most one replica per rack for the first two replicas.** The first replica goes on a ChunkServer in the rack the client is writing from (or any rack if the client has no rack affinity). The second replica goes to a ChunkServer on a DIFFERENT rack.
3. **The third replica goes on the same rack as the second replica, but a different machine.** This is a deliberate choice: it means only two racks need to be involved in most writes (reducing cross-rack bandwidth), while still surviving a full rack failure (because one replica is on a different rack entirely).

Why does this matter? Cross-rack bandwidth in a datacenter is usually a shared bottleneck — all traffic between racks goes through the top-of-rack switches and the core switches. Putting all three replicas on different racks would use 3x more cross-rack bandwidth than putting two replicas on the same rack. GFS's placement policy is a deliberate optimization: minimize cross-rack bandwidth usage while maintaining fault tolerance against rack-level failures.

```
RACK-AWARE PLACEMENT FOR CHUNK C4a91b2f

                     DATACENTER
    ┌──────────────────────────────────────────────────┐
    │                                                  │
    │  RACK A             RACK B             RACK C    │
    │  ┌────────┐         ┌────────┐         ┌──────┐  │
    │  │ CS-12  │◄──────  │ CS-47  │         │CS-89 │  │
    │  │REPLICA │  cross  │REPLICA │         │      │  │
    │  │  #1    │  rack   │  #2    │         │      │  │
    │  ├────────┤         ├────────┤         ├──────┤  │
    │  │ CS-13  │         │ CS-55  │◄──────  │CS-91 │  │
    │  │        │   same  │REPLICA │  same   │      │  │
    │  ├────────┤   rack  │  #3    │  rack   ├──────┤  │
    │  │ CS-14  │         ├────────┤         │CS-93 │  │
    │  │        │         │ CS-56  │         │      │  │
    │  └────────┘         └────────┘         └──────┘  │
    │                                                  │
    │  Replica #1: Rack A (CS-12) — writer's rack      │
    │  Replica #2: Rack B (CS-47) — different rack     │
    │  Replica #3: Rack B (CS-55) — same rack as #2,   │
    │              different machine                   │
    │                                                  │
    │  Result: Survives loss of Rack A (replicas 2,3   │
    │  on Rack B). Survives loss of any single machine. │
    │  Cross-rack traffic: only 1 replica crossing     │
    │  (from Rack A to Rack B for replica #2).         │
    │  Replica #3 copies from #2 within Rack B.        │
    └──────────────────────────────────────────────────┘
```

### A 500MB File Mapped Across 24 ChunkServers on 3 Racks

Let's trace exactly how a 500MB file gets mapped to chunks and distributed across a cluster. This is the kind of concrete example that turns an abstract explanation into something you can draw on a whiteboard.

A 500MB file produces 8 chunks (7 full chunks of 64MB + 1 partial chunk of 500 - 7×64 = 500 - 448 = 52MB).

```
FILE: /ml/training/dataset-v3.tfrecord  (500MB)

CHUNK MAPPING (stored on Master):
┌──────┬───────────────┬───────────────┬──────────────────┐
│Chunk │ Handle        │ Byte Range    │ Size             │
├──────┼───────────────┼───────────────┼──────────────────┤
│  0   │ Ca1b2c3d      │   0 -  64MB   │ 64MB (full)      │
│  1   │ Ce4f5a6b      │  64 - 128MB   │ 64MB (full)      │
│  2   │ C7890abc      │ 128 - 192MB   │ 64MB (full)      │
│  3   │ Cdef0123      │ 192 - 256MB   │ 64MB (full)      │
│  4   │ C4567890      │ 256 - 320MB   │ 64MB (full)      │
│  5   │ Cabcdef0      │ 320 - 384MB   │ 64MB (full)      │
│  6   │ C1234567      │ 384 - 448MB   │ 64MB (full)      │
│  7   │ C89abcde      │ 448 - 500MB   │ 52MB (partial)   │
└──────┴───────────────┴───────────────┴──────────────────┘

REPLICA PLACEMENT across 3 racks, 24 ChunkServers (8 per rack):

         RACK A              RACK B              RACK C
     (CS-01 to CS-08)   (CS-09 to CS-16)   (CS-17 to CS-24)

Chunk 0:  CS-01 [P]       CS-09              CS-10
Chunk 1:  CS-11 [P]       CS-02              CS-03
Chunk 2:  CS-19 [P]       CS-20              CS-07
Chunk 3:  CS-04 [P]       CS-13              CS-14
Chunk 4:  CS-21 [P]       CS-22              CS-08
Chunk 5:  CS-06 [P]       CS-15              CS-16
Chunk 6:  CS-23 [P]       CS-24              CS-05
Chunk 7:  CS-12 [P]       CS-17              CS-18

[P] = primary replica (holds the current lease for writes)

KEY OBSERVATION: No ChunkServer holds more than 1 chunk of this file.
Each chunk is spread across at least 2 different racks.
A full rack failure loses at most 1 replica per chunk — still 2 replicas left.
```

Why does this distribution matter in a real interview? If a MapReduce job reads this 500MB file in parallel — 8 mapper tasks, one per chunk — each task reads from a different ChunkServer. The reads happen completely in parallel with zero contention between tasks. This is why GFS achieves high aggregate throughput even though each individual ChunkServer has limited disk throughput.

### Common Interview Mistakes — Part 3

**Mistake 1: Assuming chunk = file.**
A 500MB file is NOT one chunk. It is 8 chunks of 64MB each (with the last one being partial). A 1TB file is 16,384 chunks. When you say "the client reads the chunk for this file," you mean "the client reads one specific chunk of this file's many chunks." This distinction matters when discussing parallelism (multiple chunks can be read simultaneously) and metadata (the Master stores a separate entry for each chunk, not one entry per file).

**Mistake 2: Thinking the partial last chunk wastes an entire 64MB slot.**
The partial chunk (52MB in our example) physically stores only 52MB on disk. The ChunkServer does not allocate a full 64MB file for a partial chunk — it stores exactly as many bytes as the chunk contains. What "wastes" space is if you have millions of tiny files (each with a 64MB chunk that's nearly empty), not when a large file's last chunk is partial.

**Mistake 3: Not knowing about rack-awareness.**
Saying "GFS just places replicas on three random ChunkServers" is wrong and sounds unsophisticated to a system design interviewer. GFS's rack-aware placement (two replicas on one rack, one on a different rack) is an explicit design choice that balances fault tolerance against cross-rack bandwidth usage. Not knowing this detail signals you've only read a high-level summary, not the actual GFS paper.

**Mistake 4: Assuming writes always go to all three replicas simultaneously from the client.**
The pipeline replication (covered in Part 5) means the client sends data to ONE ChunkServer, which forwards to the next, which forwards to the third. The client does not broadcast to all three. Missing this detail when explaining the write path suggests a shallow understanding of GFS's network optimization.

### The Internals of a ChunkServer: What Runs on Each Machine

A ChunkServer is a regular Linux machine, but its software has several components working together. Understanding this helps explain how GFS's various guarantees are implemented at the machine level.

```
CHUNKSERVER INTERNAL ARCHITECTURE

┌─────────────────────────────────────────────────────────────────┐
│                      CHUNKSERVER PROCESS                        │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ MASTER COMMUNICATION THREAD                               │  │
│  │ - Sends heartbeats to Master every few seconds            │  │
│  │ - Reports chunk inventory (handle + version per chunk)    │  │
│  │ - Receives re-replication instructions from Master        │  │
│  │ - Receives lease grants and revocations                   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ CLIENT REQUEST HANDLER (multi-threaded)                   │  │
│  │ - Accepts TCP connections from GFS client libraries       │  │
│  │ - Handles READ: verifies checksum, returns data           │  │
│  │ - Handles WRITE: buffers data, applies when told          │  │
│  │ - Handles PIPELINE: forwards data to next CS in chain     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ LOCAL CHUNK STORAGE                                       │  │
│  │ - Each chunk = one file in /gfs/chunks/ directory         │  │
│  │ - Checksum file alongside each chunk                      │  │
│  │ - Uses ext3/ext4 filesystem (not a custom FS)             │  │
│  │ - Chunk metadata (version, lease status) in memory        │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ BACKGROUND TASKS                                          │  │
│  │ - Checksum verification (background scrubbing)            │  │
│  │ - Garbage collection (deleting stale/orphaned chunks)     │  │
│  │ - Replication source (copying chunks to other CSes)       │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘

LOCAL DISK LAYOUT (simplified):
/gfs/
  chunks/
    Ca1b2c3d        ← 64MB chunk file
    Ce4f5a6b        ← 64MB chunk file
    ...
  checksums/
    Ca1b2c3d.crc    ← 4KB checksum file (1024 × 4-byte CRC32s)
    Ce4f5a6b.crc
    ...
  tmp/
    write-buffer-xyz  ← data buffered during pipeline phase
```

The key insight from this layout: the ChunkServer uses the OS's local filesystem (ext3/ext4) to store chunks as ordinary files. It does NOT implement its own disk layout. This makes the implementation simpler and lets the ChunkServer benefit from OS-level optimizations (page cache, readahead, filesystem journaling). The trade-off is that the ChunkServer relies on the OS filesystem for durability, which means it inherits the OS filesystem's failure modes (including filesystem corruption if the machine loses power mid-write without a UPS).

### Brainstorming Questions — Part 3

**Q: What happens if two ChunkServers holding the same chunk return different data? How does GFS detect corruption?**

GFS handles this with checksums. Every chunk is divided into 64KB blocks, and each block has a 32-bit checksum. The ChunkServer stores these checksums separately from the data. When a client reads a block, the ChunkServer recomputes the checksum for that block and compares it to the stored checksum. If they don't match, the data is corrupted — the ChunkServer does NOT return the data to the client. Instead, it reports the corruption to the Master and asks for a good replica from another ChunkServer.

The Master, upon learning about a corrupted replica, triggers re-replication: it instructs another ChunkServer that holds a good replica to copy the chunk to a different ChunkServer, restoring the replication factor to 3. The corrupted replica is deleted. The client that originally requested the data gets it from the healthy replica — the corruption is invisible to the client.

This means GFS detects corruption lazily (at read time, not at write time). A bit-flip that occurred years ago won't be detected until someone reads that block. For Google's workload, this was acceptable. Background scrubbing — periodically reading and verifying all chunks — can make detection proactive. Many modern storage systems (ZFS, Ceph) do this automatically.

---

**Q: You're adding a petabyte of data per day. How does GFS handle the constant creation of new chunks?**

At a petabyte per day, you're creating roughly 15 million new chunks per day (1PB / 64MB ≈ 15.6M chunks). Each new chunk requires the Master to allocate a new chunk handle (a random 64-bit number), record the chunk-to-ChunkServer assignment, and write the allocation to the operation log. Let's work through whether this is actually feasible.

15 million chunk allocations per day = about 175 chunk allocations per second. Each allocation is a single write to the Master's in-memory data structure and one append to the operation log. The operation log write is the bottleneck — it's a disk fsync in the worst case. On a good disk, an fsync takes about 1ms. That means the Master can do about 1,000 log flushes per second. GFS batches multiple log entries into a single fsync to handle higher rates — if you have 175 allocations per second and batch up to 10ms of log entries, each fsync covers 1-2 seconds of entries, reducing the fsync rate to roughly 1 per second. This is entirely feasible.

But the bigger challenge is ChunkServer selection. When allocating 15 million new chunks per day, the Master needs to spread those chunks across ChunkServers to avoid hotspots. The Master tracks how many recently-created chunks each ChunkServer holds and avoids placing too many new chunks on the same server. The reasoning: new chunks are immediately written to (they were just allocated for a write), so a server with many new chunks has high write load. The balancing algorithm is simple — prefer servers with below-average new-chunk count — but it requires the Master to maintain this count in memory, updating it on every chunk creation. At 175 allocations per second, this is negligible CPU load.

The real limit of petabyte-per-day writes is not the Master's allocation logic — it's the aggregate write bandwidth across all ChunkServers. At 3x replication, writing 1PB/day means physically writing 3PB/day to ChunkServer disks. At 100MB/s per disk (spinning disk), you need at least 350 disks of sustained write capacity, or roughly 35+ ChunkServers each with 10 disks. A large GFS cluster has hundreds to thousands of ChunkServers, so 1PB/day is achievable. The Master is not the bottleneck.

---

**Q: A file is deleted. When is the disk space actually freed on the ChunkServers?**

The disk space is freed lazily, not immediately. When you delete a file in GFS, the Master renames it to a hidden name with a timestamp (like `.trash/original-name.timestamp`). The file is now "deleted" from the user's perspective — it no longer appears in directory listings. But the chunks are still physically on the ChunkServers.

The Master runs a background garbage collection scan every few hours. During this scan, it identifies chunks that are not referenced by any live file (including trash files that are older than 3 days — the default retention window). The Master sends delete commands to the ChunkServers holding those chunks. The ChunkServers delete the chunk files. Disk space is now reclaimed.

This 3-day grace period is not a bug — it's a feature. If someone accidentally deletes a critical file, there's a 3-day window to recover it by looking in the trash. This behavior is familiar from operating system trash folders but implemented at the distributed storage level.

The downside: if a cluster is near full capacity and you delete a large file, the capacity doesn't immediately recover. The cleanup will happen within hours, but if you're trying to free space urgently (a cluster is 99% full and you're trying to make room), the lazy deletion creates a problem. GFS allowed operators to force immediate cleanup, but this was a manual override.

---

## Part 4: The Master in Depth

### What the Master stores in memory

The Master keeps three types of metadata in memory — all three must be fast to access:

**1. File and directory namespace**
The complete directory tree of all files and directories, stored as a prefix-compressed trie. When you call `open("/crawl/2024-01-15/shard-001")`, the Master looks up this path in the namespace.

**2. File-to-chunk mapping**
For every file, an ordered list of chunk handles: "file /crawl/shard-001 is made of chunks [C4a91b2f, C7d23e8c, C1f98a3d, Cb72c5e1] in that order."

**3. Chunk-to-ChunkServer mapping (NOT persisted)**
For every chunk, which ChunkServers hold it right now. This is rebuilt from scratch on every Master restart by asking all ChunkServers to report what chunks they hold.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    MASTER'S IN-MEMORY DATA                          │
│                                                                     │
│  Namespace (persisted to disk):                                     │
│  /crawl/                                                            │
│    2024-01-15/                                                      │
│      shard-001  →  [C4a91b2f, C7d23e8c, C1f98a3d, Cb72c5e1]       │
│      shard-002  →  [C9b34d2a, Ce81f7c3, ...]                       │
│    2024-01-16/                                                      │
│      ...                                                            │
│                                                                     │
│  Chunk locations (rebuilt on restart from ChunkServer reports):     │
│  C4a91b2f  →  [CS-12 (primary), CS-47, CS-89]  version=42          │
│  C7d23e8c  →  [CS-03, CS-55, CS-71]  version=18                    │
│  C1f98a3d  →  [CS-22, CS-41, CS-67]  version=7                     │
│                                                                     │
│  PERSISTED: namespace + file→chunk mapping                          │
│  NOT PERSISTED: chunk→ChunkServer (rebuilt from heartbeats)         │
└─────────────────────────────────────────────────────────────────────┘
```

### The operation log — GFS's write-ahead log

Every metadata change (create file, delete file, create chunk, rename) is first written to the operation log on disk before it is applied to the in-memory state. The log is also replicated to a few remote machines.

Why? If the Master crashes after applying a change to memory but before writing it to disk, the change is lost on recovery. The operation log ensures that every committed change survives a crash: on recovery, the Master replays the log from the last checkpoint.

This is the same pattern as a database WAL (Write-Ahead Log). The pattern is: write to the log → acknowledge the operation → apply to memory. If you crash between the log write and the memory apply, you just replay the log on recovery.

### Checkpoints — speeding up recovery

Replaying an operation log from the beginning would be slow if the log is years old. GFS solves this with checkpoints: periodic snapshots of the Master's complete in-memory state, written to disk. On recovery, the Master loads the most recent checkpoint (which covers all operations up to that point) and then replays only the log entries that occurred after the checkpoint.

```
OPERATION LOG TIMELINE

  checkpoint1 ──────── log entries ──── checkpoint2 ─── log entries ─── CRASH
  │                                     │               │
  └─────────── can be deleted ──────────┘               │
                                                         └─ replay these on recovery
```

A new checkpoint is written in a background thread so it doesn't block normal Master operations. GFS checkpoints are B-tree format, compact and fast to load — typically recovery from a checkpoint takes under a minute even for a large cluster.

### Master background tasks

The Master continuously runs background tasks to maintain cluster health:

- **Heartbeat processing**: every ChunkServer sends a heartbeat every few seconds. The Master uses heartbeats to detect failures (no heartbeat for 30 seconds → ChunkServer is down) and to receive chunk inventory reports.
- **Re-replication**: when a ChunkServer goes down, some chunks now have only 2 replicas. Master instructs another ChunkServer to copy those chunks and restore 3 replicas.
- **Rebalancing**: when a new ChunkServer is added, the Master gradually moves chunks to it to balance disk usage across the cluster.
- **Garbage collection**: periodically scans for orphaned chunks and stale replicas, sends delete commands to ChunkServers.
- **Stale replica detection**: when a ChunkServer rejoins after a crash, it reports its chunk versions. The Master compares these to the current versions and marks any outdated chunks as stale.

### What the Operation Log Actually Looks Like

The operation log is a sequential file of log entries. Each entry is a record of one metadata mutation. Here is what a realistic sequence of log entries looks like (in pseudocode — the actual encoding is binary, but the semantics are these):

```
OPERATION LOG — SAMPLE ENTRIES (pseudocode representation)

Entry #1000042:
  type: FILE_CREATE
  path: /crawl/2024-01-15/shard-001
  mode: 0644
  owner: mapreduce-user
  timestamp: 2024-01-15T08:42:11.394Z
  checksum: 0xA3F2C891

Entry #1000043:
  type: CHUNK_ALLOCATE
  file_path: /crawl/2024-01-15/shard-001
  chunk_index: 0
  chunk_handle: Ca1b2c3d
  version: 1
  primary: CS-12
  secondaries: [CS-47, CS-55]
  timestamp: 2024-01-15T08:42:11.401Z
  checksum: 0x7B81D234

Entry #1000044:
  type: CHUNK_VERSION_INC
  chunk_handle: Ca1b2c3d
  new_version: 2
  reason: LEASE_GRANTED
  lease_holder: CS-12
  lease_expires: 2024-01-15T08:43:11.402Z
  timestamp: 2024-01-15T08:42:11.402Z
  checksum: 0x9C44E567

Entry #1000045:
  type: CHUNK_ALLOCATE
  file_path: /crawl/2024-01-15/shard-001
  chunk_index: 1
  chunk_handle: Ce4f5a6b
  version: 1
  primary: CS-11
  secondaries: [CS-02, CS-03]
  timestamp: 2024-01-15T08:42:18.777Z
  checksum: 0x2D91F023

Entry #1000046:
  type: FILE_DELETE
  path: /crawl/2024-01-14/shard-001
  delete_type: SOFT  (rename to .trash, not immediate removal)
  trash_path: /.trash/crawl-2024-01-14-shard-001.1705312938
  timestamp: 2024-01-15T08:42:22.104Z
  checksum: 0xE5B72A19

Entry #1000047:
  type: CHECKPOINT_REF
  checkpoint_id: 7829
  checkpoint_lsn: 1000000
  checkpoint_path: /meta/checkpoint-7829.bin
  timestamp: 2024-01-15T08:45:00.001Z
  checksum: 0x1F88C3D2
```

Key things to notice:
- Every entry has a type, data, timestamp, and checksum. The checksum lets the Master detect corruption during log replay.
- CHUNK_ALLOCATE entries record which ChunkServers the chunk was placed on. This is how the Master recovers chunk location information if ChunkServers fail to report in during restart.
- CHUNK_VERSION_INC entries happen every time a lease is granted. This is how the Master tracks version numbers — by counting how many times a lease was granted for each chunk.
- FILE_DELETE does a soft rename, not an immediate purge. The actual chunk deletion happens later via garbage collection, NOT via a log entry at delete time.
- CHECKPOINT_REF entries mark where the latest checkpoint is. On recovery, the Master reads this entry to find the checkpoint file, loads it, then replays only log entries after the checkpoint's LSN (log sequence number).

### The Master Recovery Timeline

Here is the full sequence of events when a Master restarts after a crash:

```
MASTER RECOVERY TIMELINE

  T=0        Master process crashes (power failure, OOM kill, panic, etc.)
             All in-memory state is lost. Operation log on disk is intact.

  T+0s       Monitoring system detects Master is down.
             Shadow master begins serving read-only metadata requests.

  T+5s       Master process is restarted (by systemd or equivalent).

  T+5s       Master reads checkpoint file (compact snapshot of namespace
             + file→chunk mapping up to log entry #1000000).
             Loading a 4GB checkpoint takes about 30-60 seconds.

  T+60s      Master has full namespace and file→chunk mapping from checkpoint.
             chunk→ChunkServer mapping is NOT in the checkpoint — empty.

  T+60s      Master begins replaying operation log from entry #1000001.
             For each CHUNK_ALLOCATE entry: updates file→chunk mapping
             (some already in checkpoint, some new since checkpoint).
             For each FILE_DELETE: marks chunks as deletable.
             Replaying 50,000 log entries takes a few seconds.

  T+65s      Log replay complete. Master's namespace + file→chunk mapping
             is fully up to date. chunk→ChunkServer mapping is still empty.

  T+65s      Master begins listening for ChunkServer heartbeats.
             Each ChunkServer, on its next heartbeat cycle, sends:
             "CS-12 reporting: I hold chunks [Ca1b2c3d v2, Ce4f5a6b v1, ...]"
             Master updates chunk→ChunkServer mapping from these reports.

  T+120s     (2 minutes after restart): ~80% of ChunkServers have reported.
             Master can serve most read requests with fresh chunk locations.

  T+180s     (3 minutes after restart): ~99% of ChunkServers have reported.
             Master is fully operational. Shadow master is demoted.

  T+180s+    Any ChunkServer that reported a chunk with version != Master's
             recorded version is marked stale and scheduled for GC.
             Any chunk that no ChunkServer reported (all replicas lost during
             the crash window) is marked as lost — data loss, logged as error.
```

The total recovery time — from crash to fully operational — is typically 2-5 minutes for a large cluster. The dominant time cost is waiting for ChunkServer heartbeat reports, not the log replay (which is fast).

### Common Interview Mistakes — Part 4

**Mistake 1: Thinking the Master persists chunk-to-ChunkServer mappings.**
This is one of the most frequently missed details in GFS interviews. The Master does NOT save "chunk C1 is on CS-12, CS-47, CS-89" to disk. This information is rebuilt from ChunkServer heartbeat reports on every restart. The reasoning is that ChunkServers are the ground truth — what matters is what they actually hold right now, not what the Master thought they held before the crash. Persisting this would add complexity without improving correctness.

**Mistake 2: Confusing operation log entries with chunk data.**
The operation log records metadata mutations — file creation, deletion, chunk allocation. It does NOT record the actual bytes of file data. File data lives on ChunkServer disks, managed by the ChunkServers independently. The operation log is purely about the Master's namespace and chunk assignment state.

**Mistake 3: Not knowing the difference between a checkpoint and the operation log.**
The operation log grows without bound unless checkpointing happens. A checkpoint is a complete snapshot of the Master's in-memory state at a point in time, written to disk as a compact binary file. After a checkpoint is complete, all log entries before the checkpoint's log sequence number can be deleted — the checkpoint supersedes them. Recovery requires: load checkpoint + replay log entries since checkpoint. Without checkpointing, recovery would require replaying the entire history from day one.

**Mistake 4: Saying "the Master uses a database."**
The Master does NOT use a relational database (PostgreSQL, MySQL) as its storage backend. It uses a custom write-ahead log + checkpoint format, kept entirely in memory with periodic disk persistence. The decision to not use a database avoids the overhead and complexity of a database engine for data that can be represented more efficiently as in-memory data structures. The operation log is simpler than a database WAL and the checkpoint is simpler than a database snapshot — and that simplicity is a feature, not a compromise.

### Intern → Staff Progression (Part 4)

| Level | Understanding of the Master |
|-------|----------------------------|
| **Intern** | "The master keeps track of where files are." |
| **L3** | Knows the Master stores metadata. Cannot explain the operation log or why chunk locations are not persisted. |
| **L4** | Understands the operation log pattern (write-ahead log). Understands why chunk locations are rebuilt from ChunkServer reports (avoids persistence complexity). |
| **L5** | Can explain checkpoints and why they exist. Can explain the background tasks (re-replication, garbage collection). Understands the implications of all metadata being in memory (limits number of chunks). |
| **L6** | Can calculate the memory limit: at ~64 bytes per chunk, 1GB of master memory holds metadata for ~16 million chunks = ~1PB of data at 64MB chunks. Can articulate when this ceiling is hit and what the next-level design (Colossus) looks like. Can design the Master's failure recovery protocol from scratch. |

### Brainstorming Questions — Part 4

**Q: The Master runs in memory with periodic disk persistence. How does GFS handle a scenario where both the Master AND its disk fail simultaneously?**

This is a tail-risk scenario that GFS handles through remote replication of the operation log. The operation log is not just written to the Master's local disk — it's replicated to one or more remote machines (called "log replicas") before the Master acknowledges any metadata mutation. "Remote" here means a different physical machine, ideally in a different rack or different power domain.

If both the Master process and its local disk fail (say, the entire machine catches fire), the remote log replicas still have a complete copy of the operation log. The Master can be rebuilt on a new machine by loading the latest checkpoint (which was also replicated remotely) and replaying the remote log. The recovery process is identical to a normal crash recovery — the fact that the failure destroyed local disk rather than just crashing the process doesn't matter, because local disk was never the only copy.

The key insight is that "durability" in GFS means "written to at least two machines in different failure domains before acknowledging." The Master's local disk write and the remote log replica write are done synchronously — the Master does not respond to the client until both writes complete. This is exactly the same durability pattern used by database WALs with remote replication (like PostgreSQL streaming replication or MySQL semi-synchronous replication). In an interview, if you say "I'll use a write-ahead log for durability," the follow-up question is always "and what does the WAL itself replicate to?" GFS's answer is: at least one remote machine.

---

**Q: Why doesn't the Master persist chunk-to-ChunkServer locations? Persisting them would make recovery faster.**

At first glance, not persisting chunk locations seems like an obvious mistake — you have to ask every ChunkServer on every restart, which takes time proportional to the number of ChunkServers. But the designers made a deliberate trade-off.

ChunkServer membership is inherently dynamic. ChunkServers crash, get replaced, get decommissioned, and get added. If the Master persisted chunk locations and a ChunkServer was permanently replaced (different hardware, different hostname), the Master's persisted mapping would be wrong. The Master would think chunk C4a91b2f is on CS-12, but CS-12 no longer exists. Persisted locations require a protocol to keep them in sync with reality — which is as complex as just asking ChunkServers on startup.

More importantly, the ChunkServers are the authoritative source of truth for what chunks they actually hold. No matter what the Master's persisted records say, what actually matters is what chunks are physically on each ChunkServer's disk right now. Asking ChunkServers on startup gives you the true current state, not a potentially stale persisted state. The designers reasoned that the startup latency of asking all ChunkServers (a few minutes for a large cluster) was a small, acceptable cost for the correctness and simplicity it provided.

---

**Q: What happens if the Master's operation log gets very long (millions of entries)? How is this bounded?**

If you never took a checkpoint, the operation log would grow forever and recovery time would grow proportionally — replaying 100 million log entries would take hours. GFS bounds the log length through periodic checkpointing. The Master takes a new checkpoint whenever the log size exceeds a threshold (or on a time schedule). Once a checkpoint completes, all log entries before that checkpoint can be safely deleted from disk.

The checkpointing process is clever: the Master forks a background thread (or uses copy-on-write if the OS supports it) to write the checkpoint. The background thread takes a snapshot of the current in-memory state and writes it to disk as a compact binary file. During checkpoint writing, the Master continues accepting new operations — new log entries go to a new log file. When the checkpoint is complete, the Master atomically switches to the new checkpoint: it updates a "latest checkpoint" pointer, deletes the old checkpoint file, and truncates the old log file. The new log file (which contains only entries since the checkpoint started) becomes the current log.

The result: the operation log is bounded to the number of entries since the last checkpoint. If you checkpoint every 5 minutes and generate 10,000 log entries per minute, the log grows to at most 50,000 entries between checkpoints — tiny. Recovery time is bounded too: load a 5-minute-old checkpoint, replay at most 50,000 entries, then wait for ChunkServer heartbeats. The checkpoint itself might take a few minutes to write (depending on how much metadata exists), but since it's done in a background thread, normal Master operations continue uninterrupted during checkpointing.

---

**Q: The operation log is the source of truth for the Master's state. What happens if the log gets corrupted?**

If the operation log is corrupted, the Master cannot safely replay it — it might apply incorrect operations and end up in an inconsistent state. GFS handles this at three levels.

First, each log entry has a checksum. The Master verifies checksums when replaying the log. If a checksum fails, the Master knows the log is corrupted at that point and stops replaying. Second, the log is replicated to a few remote machines. If the primary log is corrupted, the Master can recover from a remote replica. Third, checkpoints provide recovery points. If the log is corrupted starting at position N, and the latest checkpoint covers operations through position N-1000, you lose at most 1000 log entries (the operations between the checkpoint and the corruption point). For a storage system, losing a few minutes of metadata operations is usually acceptable.

The lesson for system design interviews: write-ahead logs are not a silver bullet. They need their own redundancy (replication, checksums) and the recovery story must be designed. When you say "I'll use a WAL for durability," an L6 interviewer will ask "and what happens if the WAL itself fails?"

---

## Part 5: The Write Path

### Two types of writes

GFS has two write modes: **random write** (write at any byte offset in the file) and **append** (add data at the end of the file).

Random writes in GFS are allowed but have complex consistency semantics (see Part 8). Most GFS applications used appends because the consistency semantics are much simpler — an append either succeeds (and the data is at some offset you're told about) or fails (and you retry).

We'll walk through the append path, since that's what Google's workload primarily used.

### The lease: who is the primary?

Before a client can write a chunk, one ChunkServer must be designated the **primary** for that chunk. The primary serializes all writes — it decides the order in which concurrent writes are applied. The other replicas are **secondaries** — they apply writes in the same order the primary dictates.

The Master grants a **lease** to one ChunkServer, designating it as the primary for that chunk. The lease lasts 60 seconds and can be renewed. If the primary doesn't renew its lease (because it crashed), the lease expires and the Master can grant it to a different ChunkServer.

### Step-by-step: how a write flows through GFS

Let's trace a client appending 10MB to file `/crawl/shard-001`. The last chunk of that file is C4a91b2f, held by CS-12 (primary), CS-47, and CS-89.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    GFS WRITE PATH (DETAILED)                        │
│                                                                     │
│  Step 1: Client asks Master for write info                          │
│  ─────────────────────────────────────────                          │
│  Client → Master: "I want to append to /crawl/shard-001"           │
│  Master → Client: "Last chunk is C4a91b2f.                         │
│                    Primary=CS-12. Secondaries=CS-47, CS-89.        │
│                    Lease expires in 45 seconds."                    │
│                                                                     │
│  Step 2: Client pushes data to ALL replicas (pipeline)             │
│  ──────────────────────────────────────────────────────             │
│  Client → CS-12: "Here is 10MB of data" (buffered, not committed)  │
│  CS-12  → CS-47: "Here is 10MB of data" (forwarded)               │
│  CS-47  → CS-89: "Here is 10MB of data" (forwarded)               │
│                                                                     │
│  WHY PIPELINE? Each node sends to the next as it receives.         │
│  Total data transferred = 10MB × 3 = 30MB.                        │
│  If client sent to all 3 directly = 30MB from client.              │
│  With pipeline = 10MB from client + 20MB between CSes.             │
│  Client's upload bandwidth is saved.                               │
│                                                                     │
│  Step 3: Client sends WRITE command to primary                      │
│  ─────────────────────────────────────────────                      │
│  Client → CS-12: "WRITE the data I just pushed"                    │
│                                                                     │
│  Step 4: Primary serializes and commits                             │
│  ──────────────────────────────────────                             │
│  CS-12: assigns an offset to this append (e.g., byte 192MB)        │
│  CS-12: writes data to its own disk at that offset                  │
│  CS-12 → CS-47: "WRITE at offset 192MB"                           │
│  CS-12 → CS-89: "WRITE at offset 192MB"                           │
│                                                                     │
│  Step 5: Secondaries acknowledge                                    │
│  ─────────────────────────────────                                  │
│  CS-47 → CS-12: "ACK"                                              │
│  CS-89 → CS-12: "ACK"                                              │
│                                                                     │
│  Step 6: Primary responds to client                                 │
│  ───────────────────────────────────                                │
│  CS-12 → Client: "SUCCESS. Data written at offset 192MB."          │
│                                                                     │
│  FAILURE SCENARIO: CS-47 crashes during step 2                     │
│  ─────────────────────────────────────────────                      │
│  CS-12 does not get ACK from CS-47 in step 5                       │
│  CS-12 → Client: "FAILURE"                                         │
│  Client retries the entire operation from step 1                    │
│  Master detects CS-47 is down via missing heartbeat                │
│  Master triggers re-replication of C4a91b2f from CS-12 to CS-99   │
└─────────────────────────────────────────────────────────────────────┘
```

### Why separate data flow from control flow?

Notice that in step 2, the client pushes data to all three ChunkServers (data flow), and then in step 3, the client tells only the primary to commit (control flow). Data flows in a chain (client → CS-12 → CS-47 → CS-89). Control flows from client to primary only (client → CS-12), then from primary to secondaries (CS-12 → CS-47, CS-89).

This separation has a key benefit: the client's network bandwidth is used efficiently. The client only sends 10MB (to CS-12), not 30MB (to all three ChunkServers). The remaining replication happens between ChunkServers, which are typically on high-bandwidth internal network links.

### Three Failure Scenarios: Step-by-Step

Understanding GFS fault tolerance means being able to trace exactly what happens in each failure mode. Here are three concrete scenarios. The setup for all three: a client is appending 10MB to chunk C4a91b2f. CS-12 is the primary, CS-47 and CS-89 are secondaries. The client has pushed data to all three (step 2 of the write path) and has sent the WRITE command to CS-12 (step 3).

#### Failure Scenario A: A Secondary ChunkServer Fails Before Write Commits

```
Situation: CS-47 crashes after receiving the data push (step 2) but
before CS-12 sends the WRITE command to it (step 4).

  CLIENT          CS-12 (primary)    CS-47 (crashed)   CS-89
    |                  |                   |               |
    |--- WRITE CMD --->|                   |               |
    |                  |--- WRITE CMD ---->|               |
    |                  |   [CS-47 is dead. No response]    |
    |                  |   [timeout after 5-10 seconds]    |
    |                  |--- WRITE CMD ---------------------->|
    |                  |<-- ACK ----------------------------||
    |                  |                                   |
    |                  | [CS-47 did not ACK]               |
    |                  | [Write considered FAILED]         |
    |<-- FAILURE -------|                                   |
    |                  |                                   |
    | [Client retries from step 1: asks Master for new     |
    |  chunk metadata]                                     |
    |-------- WHERE IS C4a91b2f? -------> MASTER           |
    |         MASTER detects CS-47 missing heartbeat       |
    |         MASTER: "C4a91b2f is on CS-12 (primary),     |
    |                  CS-89, and CS-99 (new replica)"     |
    |         [Master triggered re-replication:            |
    |          CS-89 copied chunk to CS-99]                |
    | [Client pushes data to CS-12, CS-89, CS-99]          |
    | [Client sends WRITE to CS-12]                        |
    | [All three ACK. Write SUCCEEDS]                      |
```

**What the client sees:** A temporary failure and retry. The write eventually succeeds, at the same offset the primary would have chosen. There is no data duplication — the failed write never committed, so there's nothing to undo.

#### Failure Scenario B: The Primary Fails Mid-Write (After Receiving WRITE, Before ACKing Secondaries)

```
Situation: CS-12 receives the WRITE command, commits locally, sends
WRITE to CS-47 and CS-89 — then crashes before getting ACKs.

  CLIENT          CS-12 (primary)    CS-47              CS-89
    |                  |               |                  |
    |--- WRITE CMD --->|               |                  |
    |                  | [writes local]|                  |
    |                  |--- WRITE ---->|                  |
    |                  |--- WRITE ----------------------->|
    |                  | [CRASH]       |                  |
    |                  X               |                  |
    |                                  | [CS-47 writes]   |
    |                                  |                  | [CS-89 writes]
    |                                  |                  |
    | [Client gets no response. Timeout.]                 |
    | [Client asks Master: where is C4a91b2f?]            |
    |------------- Master: lease expired for CS-12 ------>|
    |------------- Master grants new lease to CS-47 ----->|
    |                                                     |
    | [Client pushes data again to CS-47 (new primary),  |
    |  CS-89, and CS-99 (re-replicated)]                  |
    | [CS-47 gets WRITE command]                          |
    | [CS-47 already has the data from the first attempt]|
    | [CS-47 checks: is this a duplicate? Assigns same   |
    |  offset (idempotent append via chunk version)]      |
    | [Write commits. Client gets SUCCESS]                |
```

**What the client sees:** A failure and retry. The data ends up written exactly once at a specific offset. CS-12's local write is stale (wrong version number) — when CS-12 recovers, the Master rejects its replica of C4a91b2f as stale (old version) and instructs CS-12 to delete it.

**The subtle case:** CS-12 crashed after CS-47 and CS-89 both received and wrote the data. So the data WAS successfully written to two of the three replicas — but the client doesn't know this. The retry will try to write again. The secondaries (now CS-47 as primary + CS-89) will receive a duplicate write request. This is where GFS's "consistent but undefined" consistency model becomes real: the retry might succeed at the same offset (making the data correct) or at a new offset (creating a duplicate). This is the core reason GFS's consistency model is complex and why application-level deduplication or idempotent operations matter.

#### Failure Scenario C: Primary Fails After Write but Before Client ACK

```
Situation: CS-12 commits the write, secondaries ACK, but CS-12 crashes
before sending SUCCESS to the client.

  CLIENT          CS-12 (primary)    CS-47              CS-89
    |                  |               |                  |
    |--- WRITE CMD --->|               |                  |
    |                  | [writes local]|                  |
    |                  |--- WRITE ---->|                  |
    |                  |--- WRITE ----------------------->|
    |                  |<-- ACK --------|                  |
    |                  |<-- ACK -------------------------||
    |                  | [ALL 3 replicas have the data]   |
    |                  | [CRASH before sending to client] |
    |                  X               |                  |
    |                                  |                  |
    | [Client timeout. No SUCCESS.]    |                  |
    | [Client does NOT know if write   |                  |
    |  succeeded or failed]            |                  |
    | [Client retries from step 1]     |                  |
    | [Master grants lease to CS-47]   |                  |
    | [Client pushes data again]       |                  |
    | [CS-47 assigns a NEW offset for  |                  |
    |  this append — it doesn't know  |                  |
    |  this is a retry of an already  |                  |
    |  committed write]                |                  |
    | [WRITE SUCCESS at new offset]    |                  |
```

**What the client sees:** A retry that appears to succeed. But now the data has been written TWICE — once at the original offset (by CS-12 before it crashed, replicated to CS-47 and CS-89) and once at a new offset (by the retry). The file now contains a duplicate record.

**How GFS applications handle this:** This is why GFS applications that use record append must be built to tolerate duplicates. A MapReduce job reading this file might process the same record twice. Google's MapReduce framework included a deduplication step (tracking which records had already been processed using a record ID). This is not a bug in GFS — it's a documented behavior that applications must handle. The GFS paper explicitly states that clients should be prepared for duplicate records in the append case.

### Common Interview Mistakes — Part 5

**Mistake 1: Confusing data flow with control flow.**
Data flows in a pipeline: Client → CS-12 → CS-47 → CS-89 (linear chain). Control flows separately: Client → CS-12 (WRITE command), CS-12 → CS-47 and CS-89 (WRITE commands), CS-47 and CS-89 → CS-12 (ACKs), CS-12 → Client (SUCCESS or FAILURE). Many candidates say "the client sends data to all three ChunkServers simultaneously" — this is wrong. The client sends data to only the primary (or the first in the pipeline chain), and the primary forwards to the secondaries.

**Mistake 2: Not knowing what a lease is.**
A lease is a time-limited grant of authority. The Master grants a 60-second lease to a ChunkServer, making it the primary for that chunk for that duration. During the lease period, the primary can commit writes without asking the Master for permission on each write. The lease can be extended (renewed before expiration) if the primary sends a heartbeat with a renewal request. The lease expires if the primary crashes — after 60 seconds, the Master knows the old primary's lease is gone and can safely grant a new lease to a different ChunkServer.

Without leases, the Master would need to be involved in every write to ensure there's only one primary. With leases, the Master is involved only in lease grants (once per 60 seconds per active chunk), not in individual writes. This dramatically reduces Master load.

**Mistake 3: Saying "GFS uses two-phase commit for writes."**
GFS does NOT use two-phase commit. 2PC requires a coordinator (the Master in this case) to coordinate the commit across all participants. GFS's write protocol uses the primary ChunkServer as the coordinator, not the Master. The Master is not in the write path at all — it only grants the lease. The primary runs the commit protocol with its secondaries. This is simpler and faster than 2PC (no Master roundtrip per write), at the cost of weaker consistency guarantees (the "inconsistent" state for failed writes in the consistency table).

**Mistake 4: Not addressing what happens to in-flight data on primary crash.**
When an interviewer asks "what happens if the primary crashes during a write?", a shallow answer is "the client retries." The complete answer must address: (a) what the Master does (lets lease expire, grants new lease), (b) what state the data is in on the secondaries (may have partial writes), (c) what the client does (full retry, possibly causing duplicate data), (d) what happens to the crashed primary when it recovers (its replica is stale, gets garbage collected). Missing any of these shows incomplete understanding of the failure path.

### Intern → Staff Progression (Part 5)

| Level | Understanding of the write path |
|-------|--------------------------------|
| **Intern** | "The client writes to the server." |
| **L3** | Knows data goes to multiple replicas. Cannot explain ordering or the primary/secondary role. |
| **L4** | Understands the primary serializes writes. Understands why this is needed (concurrent writes would cause inconsistency without serialization). |
| **L5** | Can explain the pipeline replication optimization. Understands lease expiration and why it's needed (prevents split-brain between old and new primary). |
| **L6** | Can trace the complete write path including failure scenarios. Understands the consistency implications of the primary/secondary model. Can explain how the lease timeout prevents a crashed-primary from causing data inconsistency. Can redesign this for different consistency requirements. |

### Brainstorming Questions — Part 5

**Q: Why does GFS pipeline data through ChunkServers (CS-12 → CS-47 → CS-89) instead of the client sending to all three simultaneously?**

The pipeline model saves the CLIENT's outbound network bandwidth, which is often the scarce resource. In a typical Google datacenter circa 2003, each server had a 1 Gbps NIC (network interface card). If the client had to send 10MB to three ChunkServers simultaneously, it would use 30MB of outbound bandwidth (sending three copies of 10MB). With a 1 Gbps NIC (≈ 125 MB/s), sending 30MB takes about 240ms.

With pipeline replication, the client sends 10MB to CS-12 only (10MB outbound from client). CS-12 forwards to CS-47 as it receives (10MB over the inter-ChunkServer link). CS-47 forwards to CS-89 (10MB over another inter-ChunkServer link). The client's outbound usage is only 10MB — a 3x reduction. The client's 1 Gbps link sends 10MB in about 80ms instead of 240ms.

The tradeoff: total time to replicate is the pipeline depth (3 hops) × hop transfer time, not just 1 hop. But within a datacenter, inter-server links are at the same speed or faster than client NICs (often 10 Gbps by 2003-2006 for internal links). So the pipeline time is 3 × (10MB / 125 MB/s) = 240ms sequential, vs. 1 × 80ms for the client + 2 × 80ms forwarding = 240ms anyway. The time isn't worse, but the client's bandwidth cost is 3x lower. At a datacenter scale where the client bandwidth is shared across many applications, this matters enormously.

---

**Q: What happens if the primary ChunkServer crashes after it has committed a write locally but before it sends the WRITE command to the secondaries?**

This is a partial write scenario — the primary has the data and the secondaries don't. When the client doesn't receive a success acknowledgment (because the primary crashed before responding), it retries the write from step 1. The Master detects the primary is down (missing heartbeat), lets the lease expire, and grants the lease to one of the secondaries (say CS-47). Now CS-47 is the new primary.

The client retries the write by pushing the data to CS-47 (new primary), CS-89, and CS-99 (a new third replica). This write succeeds. Now you have: CS-47 and CS-89 have the data at offset 192MB (from the retry). CS-12 (the crashed primary, when it eventually recovers) also has the data at offset 192MB — it wrote it locally before crashing. But CS-12's chunk might have an old version number. When CS-12 comes back online, it reports its chunks to the Master. The Master sees CS-12's version of C4a91b2f is stale (version doesn't match the current version). CS-12's copy is marked as stale and garbage collected.

The key lesson: GFS tolerates partial writes through retry, not through distributed transactions. The client retries, the Master coordinates the new primary, and stale replicas are eventually cleaned up. This is eventually consistent coordination, not atomic distributed commit.

---

**Q: The lease is 60 seconds. What happens if the network is slow and a write takes more than 60 seconds?**

The primary can request a lease extension from the Master at any time while it holds the lease. The primary sends a heartbeat to the Master that includes a lease extension request. The Master grants the extension as long as there's no reason to revoke the lease (no one is trying to take the primary role away from this ChunkServer). The lease is typically extended before it expires, so writes that take longer than 60 seconds are handled transparently — the client doesn't even know the lease was extended.

The 60-second default is set conservatively large to give the primary plenty of time to handle writes even under high load. The key property the lease enforces is this: there cannot be two active primaries simultaneously. If the Master wants to revoke a lease (perhaps it suspects the current primary is dead), it waits for the current lease to expire before granting a new lease to a different ChunkServer. This 60-second window is the price of simplicity — after 60 seconds, you're guaranteed the old primary has given up its lease (because the lease expired), and you can safely grant a new one.

---

## Part 6: The Read Path

### How GFS reads data

The read path is much simpler than the write path. There is no lease, no primary, no serialization needed. Any replica can serve a read.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    GFS READ PATH                                    │
│                                                                     │
│  Application wants to read bytes 70MB–80MB from /crawl/shard-001   │
│                                                                     │
│  Step 1: Client translates byte range to chunk+offset               │
│  ─────────────────────────────────────────────────────              │
│  Byte 70MB is in chunk index 1 (chunks are 64MB)                   │
│  Offset within chunk 1: 70MB - 64MB = 6MB                          │
│  Length: 10MB                                                       │
│                                                                     │
│  Step 2: Client checks its local cache                              │
│  ─────────────────────────────────────                              │
│  "Do I already know where chunk C7d23e8c is?"                      │
│  Cache HIT → go to step 4                                          │
│  Cache MISS → go to step 3                                         │
│                                                                     │
│  Step 3: Client asks Master for chunk locations                     │
│  ──────────────────────────────────────────────                     │
│  Client → Master: "Where is chunk C7d23e8c?"                       │
│  Master → Client: "CS-03, CS-55, CS-71. Version 18."               │
│  Client caches this (with a TTL of a few minutes)                  │
│                                                                     │
│  Step 4: Client reads from nearest ChunkServer                      │
│  ──────────────────────────────────────────────                     │
│  Client → CS-55: "Give me chunk C7d23e8c, offset 6MB, length 10MB" │
│  CS-55: verifies checksum for the relevant blocks                  │
│  CS-55 → Client: [10MB of data]                                    │
│                                                                     │
│  FAILURE: CS-55 returns checksum error                             │
│  CS-55 → Master: "C7d23e8c is corrupted on CS-55"                 │
│  Client retries with CS-03 (another replica)                       │
└─────────────────────────────────────────────────────────────────────┘
```

### Client cache behavior

The client caches chunk locations with a time-to-live (TTL). This means:
- After the TTL expires, the client re-fetches chunk locations from the Master.
- If a ChunkServer goes down, the client's cache might point to the dead server. The client will get a connection error, then contact the Master to get fresh locations.
- The Master does not push updates to clients — it only responds to queries. This simplifies the Master but means clients might briefly try a dead ChunkServer before getting fresh locations.

### Load balancing reads

Since any replica can serve reads, the client can choose which ChunkServer to read from. The standard heuristic is "choose the closest replica" (same rack if possible, then same datacenter, then remote). This reduces network traffic and read latency.

### The Client-Side Cache Lifecycle

The GFS client library maintains a local cache of chunk locations (which ChunkServers hold each chunk). Understanding the exact lifecycle of this cache is important for interviews because it directly explains how the client handles stale metadata, ChunkServer failures, and repeated reads.

```
CLIENT-SIDE CHUNK LOCATION CACHE LIFECYCLE

┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  STATE 1: CACHE EMPTY (cold start or TTL expired)               │
│                                                                  │
│  Client needs to read chunk C7d23e8c.                           │
│  Cache entry for C7d23e8c: MISSING.                             │
│  → Go to Master: "where is C7d23e8c?"                          │
│  ↓                                                              │
│                                                                  │
│  STATE 2: CACHE POPULATED (after Master response)               │
│                                                                  │
│  Cache entry: {                                                  │
│    chunk: C7d23e8c,                                             │
│    locations: [CS-03, CS-55, CS-71],                            │
│    version: 18,                                                 │
│    fetched_at: 14:23:07,                                        │
│    ttl: 60 seconds  ← expires at 14:24:07                      │
│  }                                                              │
│  → Read directly from CS-55 (closest)                          │
│  ↓                                                              │
│                                                                  │
│  STATE 3: CACHE HIT (within TTL, ChunkServer alive)             │
│                                                                  │
│  Same chunk needed at 14:23:45 (38 seconds later).              │
│  Cache entry still valid (TTL not expired).                     │
│  → Read directly from CS-55. No Master contact. Fast.          │
│  ↓                                                              │
│                                                                  │
│  STATE 4a: STALE CACHE — ChunkServer Failed                     │
│                                                                  │
│  At 14:24:00, CS-55 crashes.                                    │
│  Client tries to read C7d23e8c from CS-55 at 14:24:05.         │
│  TCP connection to CS-55: REFUSED (machine is down).           │
│  → Client tries next cached location: CS-03.                   │
│  → CS-03 responds. Read succeeds.                              │
│  → Client updates cache: remove CS-55, add CS-03 as primary.  │
│  (Client does NOT contact Master — has other valid locations)   │
│  ↓                                                              │
│                                                                  │
│  STATE 4b: STALE CACHE — ALL Locations Dead                     │
│                                                                  │
│  All three cached locations (CS-03, CS-55, CS-71) fail.        │
│  Client cannot read from any cached location.                  │
│  → Client MUST go to Master: "fresh locations for C7d23e8c?"  │
│  → Master responds with new locations (CS-07, CS-44, CS-88).  │
│  → Client reads from CS-07. Cache updated.                     │
│  ↓                                                              │
│                                                                  │
│  STATE 5: TTL EXPIRY (normal refresh)                           │
│                                                                  │
│  At 14:24:07, TTL expires. Cache entry for C7d23e8c deleted.   │
│  Next read of C7d23e8c → back to STATE 1 (cache empty).        │
│  Client contacts Master to get fresh locations.                │
│                                                                 │
└──────────────────────────────────────────────────────────────────┘
```

**Key insight from this lifecycle:** The Master is involved only in two cases: (1) initial cache population (cache miss / TTL expiry), and (2) all cached locations have failed simultaneously. In all other cases (cache hit, single ChunkServer failure with other replicas available), the client reads without touching the Master. This is how GFS keeps the Master out of the data path even during partial failures.

### Hot Chunks: The 1000-Reader Problem

GFS was designed for batch sequential reads where different MapReduce tasks read different chunks. What happens when 1,000 tasks all need to read the SAME chunk simultaneously?

This scenario arises when:
- A very popular dataset is shared across many simultaneous jobs.
- All MapReduce tasks need to read the same "index" or "mapping" file before processing their partition.
- A new product launch causes sudden read demand on a specific file.

```
HOT CHUNK SCENARIO

  1,000 MapReduce worker tasks all want to read chunk Ca1b2c3d
  of file /shared/city-population-index.data.

  Ca1b2c3d is on CS-12, CS-47, CS-89.

  Requests per second to each ChunkServer:
  ┌───────┬──────────────────────────────────────────┐
  │  CS   │  Disk throughput                         │
  │  CS-12│  ████████████████████ 100 MB/s [MAXED]  │
  │  CS-47│  ████████████████████ 100 MB/s [MAXED]  │
  │  CS-89│  ████████████████████ 100 MB/s [MAXED]  │
  └───────┴──────────────────────────────────────────┘

  All 3 ChunkServers are saturated.
  Remaining 700 tasks are queued, waiting.

  Other chunks on CS-12, CS-47, CS-89 are now SLOW
  (hot chunk consumes all disk I/O on those servers)

  SOLUTIONS GFS OPERATORS USED:
  1. Increase replication factor: 3 → 10 replicas
     (spreads load across 10 ChunkServers instead of 3)
  2. Stagger task start times (scheduler-level fix)
  3. Use caching: tasks that have read Ca1b2c3d cache it
     in memory and share via a local cache service
     (not a GFS feature — application-level fix)
```

This is a real problem that Google encountered. The GFS paper acknowledges that hot spots can form when many clients concurrently access the same chunk. The temporary fix (increasing replication) works but requires operator intervention. The structural fix is to design access patterns so different tasks read different data — which is exactly how good MapReduce job design works (partition the input so each task reads a distinct subset).

For a system design interview, this is an important nuance: GFS achieves high aggregate throughput by parallelizing reads across many chunks, not by making individual chunk reads faster. A workload that concentrates all readers on a small number of chunks defeats GFS's parallelism advantage.

### How GFS Handles Large Parallel Reads: The MapReduce Pattern

MapReduce is the canonical GFS consumer. Understanding how MapReduce reads data from GFS helps illustrate why GFS was designed the way it was.

A MapReduce job with 1,000 mapper tasks reading a 64TB input file works like this:

The input file has 1,024 chunks (64TB / 64MB per chunk). The MapReduce scheduler assigns chunks to mapper tasks: mapper task 0 reads chunk 0, task 1 reads chunk 1, etc. Each mapper gets a specific chunk to read — there is no global coordination between mappers at read time. Each mapper independently:
1. Asks the Master (or checks its cache) for the ChunkServer locations for its assigned chunk.
2. Reads its 64MB chunk from the nearest replica.
3. Processes the data and produces output.

The aggregate read throughput is approximately: (number of mapper tasks reading simultaneously) × (per-ChunkServer read throughput). With 1,000 mappers reading 1,000 different chunks from potentially 1,000 different ChunkServers (since each chunk has 3 replicas spread across many ChunkServers), the aggregate throughput is enormous — potentially 100+ GB/s across the cluster.

This is why GFS's design (many ChunkServers, parallel direct client reads) produces such high aggregate throughput for batch workloads: the workload is embarrassingly parallel across chunks, and the architecture provides a separate data path for each chunk (no single bottleneck). The Master handles 1,000 metadata lookups (one per mapper task) — a tiny fraction of its capacity — and then steps completely aside.

### Common Interview Mistakes — Part 6

**Mistake 1: Saying "reads go through the Master."**
The Master handles chunk location queries (cache misses). It does NOT participate in actual reads. The data flows directly from ChunkServer to Client. If an interviewer asks "how does a read work?" and you say "the client sends the data through the master" — that's a disqualifying mistake for L5/L6 discussions.

**Mistake 2: Not knowing that the client picks the ChunkServer.**
The client chooses which ChunkServer to read from (based on network proximity). The Master does not assign a ChunkServer for reads — it just gives the list of servers holding the chunk. This distinction matters: it means the client can implement its own load balancing strategy (always read from the closest server, or round-robin across replicas, or prefer servers that have responded quickly recently).

**Mistake 3: Saying "GFS supports random reads with low latency."**
GFS was explicitly NOT optimized for random access or low latency. It is a throughput-optimized system. Reading 1MB sequentially from a chunk is fast. Reading a single 4KB block from a random offset in a chunk involves a disk seek and is slow. Applications built on GFS that need random access (like Bigtable) implement their own in-memory caching and SSTable format to avoid individual small reads from GFS. Saying "GFS handles low-latency random reads" signals a misunderstanding of the design.

**Mistake 4: Confusing per-chunk parallelism with per-file parallelism.**
GFS achieves high aggregate throughput by distributing different chunks of the same file across different ChunkServers. A 500MB file has 8 chunks on 8+ different ChunkServers. Reading all 8 chunks in parallel uses 8 ChunkServers' worth of disk bandwidth. This is per-file parallelism. Per-chunk parallelism is limited to the replication factor (3) — you can read the same chunk from at most 3 places simultaneously. Understanding this distinction helps explain why large files are better than small files in GFS: large files have more chunks, enabling more parallelism.

### Intern → Staff Progression (Part 6)

| Level | Understanding of the read path |
|-------|-------------------------------|
| **Intern** | "The client reads from the server." |
| **L3** | Knows reads go to ChunkServers, not through the Master. Cannot explain client caching. |
| **L4** | Understands client caching of chunk locations. Understands why any replica can serve reads (no write serialization needed for reads). |
| **L5** | Can explain the read path completely, including the cache TTL and staleness window. Understands checksum verification per block. |
| **L6** | Can analyze the read path for scalability: Master load for reads is minimal (just cache misses). ChunkServer read throughput scales linearly with the number of ChunkServers. Can calculate theoretical aggregate throughput. Can reason about when to replicate more aggressively (hot chunks that are read constantly). |

### Brainstorming Questions — Part 6

**Q: A client reads the same 64MB chunk 100 times. Does GFS do 100 round-trips to the Master?**

No — and understanding why is key to understanding GFS's scalability. The client caches chunk locations after the first Master roundtrip. The cache entry has a TTL (time-to-live), typically on the order of minutes. For the next 99 reads of the same chunk (assuming they happen within the TTL window), the client uses the cached locations and contacts the ChunkServer directly — no Master involved.

The Master is only consulted on (1) the very first read of a chunk (cache cold), (2) when the TTL expires and the client needs fresh locations, or (3) when all cached locations fail. In a typical MapReduce workload where each chunk is read once sequentially, every chunk read involves exactly one Master roundtrip (the cache miss on first access) followed by one ChunkServer read. The Master's load is proportional to the number of DISTINCT chunks accessed, not the total bytes read. For a 1TB file with 16,384 chunks, reading it once from start to finish requires 16,384 Master roundtrips — spread across time as each chunk is first encountered. For a cluster with hundreds of MapReduce jobs running simultaneously, the Master handles thousands of cache-miss queries per second — which is entirely feasible for an in-memory lookup server.

---

**Q: GFS doesn't use a read cache at the ChunkServer level. Why not, and what does that imply?**

GFS workloads involve sequential reads of large files. A cache is most beneficial when the same data is read repeatedly from a hot set. For Google's batch processing jobs (MapReduce tasks reading web crawl data), each datum is typically read once — the job processes it and moves on. A cache wouldn't help because there's no repetition to exploit.

The flip side: if you built a system on GFS that had hot data (the same chunk read by thousands of clients simultaneously), GFS would struggle. Every read request goes to a ChunkServer, and that ChunkServer's disk throughput is the bottleneck. For hot read workloads, you'd want a caching layer in front of GFS — which is exactly what systems like Memcached and Redis provide when layered on top of storage systems. GFS is a good building block but not a complete solution for all read patterns.

This also has implications for how you design systems on top of GFS. If your MapReduce job has 1,000 mapper tasks that all start reading the same input file simultaneously, all 1,000 tasks will hit the ChunkServers holding that file's chunks. The per-chunk parallelism limit is the replication factor (3 replicas = at most 3 concurrent readers per chunk). Designing your job to have good chunk-to-task affinity (each task reads different chunks) is important for performance.

---

## Part 7: Fault Tolerance

### The failure scenarios GFS must handle

GFS was designed assuming failures are the normal operating condition, not the exception. At a cluster of 1,000 ChunkServers, at least one machine fails per week. At 10,000 ChunkServers, multiple machines fail per day. The fault tolerance mechanisms must handle this continuously.

```
┌─────────────────────────────────────────────────────────────────────┐
│              FAILURE SCENARIOS AND GFS RESPONSES                    │
│                                                                     │
│  FAILURE: ChunkServer goes down (most common)                       │
│  ─────────────────────────────────────────────                      │
│  Detection: Master gets no heartbeat for 30+ seconds               │
│  Response: Master identifies all chunks on that CS with             │
│            fewer than 3 replicas. Prioritizes chunks with           │
│            only 1 replica (most urgent). Instructs other            │
│            CSes to replicate until all chunks have 3 again.        │
│  Time to detect: ~30-60 seconds                                    │
│  Time to re-replicate: minutes to hours (depends on data volume)   │
│                                                                     │
│  FAILURE: Master crashes                                            │
│  ────────────────────────                                           │
│  Detection: Monitoring system, external watchdog                   │
│  Response: Shadow master (read-only) takes over for reads.         │
│            New master starts, replays operation log from            │
│            last checkpoint. ChunkServers report their chunks.      │
│  Time to recover: seconds to minutes (log replay)                  │
│                                                                     │
│  FAILURE: Data corruption on disk                                   │
│  ────────────────────────────────                                   │
│  Detection: Checksum failure on read                               │
│  Response: ChunkServer reports to Master. Master re-replicates     │
│            from healthy replica. Corrupted replica deleted.        │
│  Time to detect: at read time (lazy)                               │
│                                                                     │
│  FAILURE: Network partition                                         │
│  ──────────────────────────                                         │
│  Detection: Master loses contact with subset of CSes               │
│  Response: Those CSes' leases eventually expire. Master can        │
│            grant new leases to reachable CSes.                     │
│  Time: lease expiration time (60s default)                         │
└─────────────────────────────────────────────────────────────────────┘
```

### Re-replication prioritization

When ChunkServers go down, the Master may have many chunks that need re-replication. It prioritizes them:

1. **Chunks with only 1 replica** (most urgent — one more failure loses the data)
2. **Chunks with 2 replicas** (medium urgency)
3. **Chunks with 3 replicas that lost a replica due to a scheduled decommission** (lowest urgency — still have 2 replicas)

This prioritization ensures that chunks at risk of data loss are re-replicated first.

### The shadow master

The shadow master is a read-only replica of the Master that applies the same operation log in real time. It lags slightly behind the primary Master (a few seconds at most). If the primary Master crashes:

- Read-only operations (list directory, get chunk locations for cached files) continue via the shadow master
- Write operations (create file, delete file, modify chunk metadata) are blocked until the primary Master recovers

For Google's batch processing workload, temporary write unavailability was acceptable. Running MapReduce jobs are paused and resume when the Master recovers.

### Detailed Re-Replication Priority Diagram

When ChunkServers fail, the Master needs to prioritize which chunks to re-replicate first. Here is how that priority queue works:

```
RE-REPLICATION PRIORITY QUEUE (maintained by Master)

  SCENARIO: CS-12, CS-47, and CS-89 all fail simultaneously.

  The Master identifies all chunks affected:
  - Chunks that were on CS-12 only (lost all replicas): CRITICAL
  - Chunks on CS-12 + CS-47 (lost 2 of 3 replicas): URGENT
  - Chunks on CS-12 only (lost 1 of 3 replicas): NORMAL

  Priority Queue:
  ┌─────────────────────────────────────────────────────┐
  │ PRIORITY 1 (CRITICAL): 0 replicas remain            │
  │   → Chunk C_xyz: was on CS-12, CS-47, CS-89.        │
  │   → ALL 3 failed simultaneously.                    │
  │   → DATA LOST. Cannot re-replicate (no source).     │
  │   → Master logs this as a permanent data loss event │
  │     and notifies operators.                         │
  │                                                     │
  │ PRIORITY 2 (URGENT): 1 replica remains              │
  │   Chunk Ca1b2c3d: was on CS-12 (down), CS-47 (down),│
  │                   CS-55 (alive). Only 1 copy left!  │
  │   → IMMEDIATELY start re-replication               │
  │   → CS-55 copies Ca1b2c3d to CS-99 and CS-101      │
  │   → Do this before anything else                   │
  │                                                     │
  │ PRIORITY 3 (HIGH): 2 replicas remain (was 3)        │
  │   Chunk Ce4f5a6b: was on CS-12 (down), CS-03 (alive)│
  │                   CS-71 (alive). 2 copies left.     │
  │   → Re-replicate soon (1 more failure = PRIORITY 2) │
  │   → CS-03 copies Ce4f5a6b to CS-88                 │
  │                                                     │
  │ PRIORITY 4 (NORMAL): re-balancing after recovery    │
  │   → Distribute chunks evenly after cluster heals   │
  └─────────────────────────────────────────────────────┘

  The Master processes priority 2 chunks first,
  then priority 3, and so on. Re-replication bandwidth
  is throttled to not overwhelm the network:
  typically capped at 1-2 MB/s per ChunkServer pair
  for background re-replication.
```

**The throttling detail matters:** GFS throttles background re-replication so it doesn't consume all network bandwidth and slow down actual client reads/writes. This means that after a large failure (100 ChunkServers down), full re-replication might take hours or even days. During that window, the cluster operates with reduced redundancy. Operators monitor this metric closely.

### Real Incident: Datacenter Network Switch Failure

Imagine a top-of-rack switch in a Google datacenter fails and takes down the network connectivity for 200 ChunkServers simultaneously. What does the Master see and how does it react?

From the Master's perspective, 200 ChunkServers suddenly stop sending heartbeats at the same time. After 30 seconds of silence, the Master's heartbeat detection logic triggers for all 200. The Master now sees:
- 200 ChunkServers marked as "probably down"
- Thousands of chunks that had replicas on those 200 servers now appear under-replicated
- A re-replication queue with potentially tens of thousands of items

**The critical question: is this a real failure or a network partition?**

If the switch is truly dead, those 200 ChunkServers are inaccessible to clients AND to the Master — re-replication to other servers makes sense. But if this is a network partition (the ChunkServers are still running, just temporarily unable to reach the Master), then: (a) those ChunkServers still have valid data, (b) aggressively re-replicating their chunks to other servers wastes bandwidth and disk I/O, and (c) when the partition heals, the Master will have created extra replicas that need to be garbage-collected.

**GFS's response:**

The original GFS design did not have a sophisticated partition detection mechanism. The Master would start the re-replication process, but it would throttle the re-replication rate. If the network partition was brief (switch recovered in 5 minutes), the Master would have re-replicated only a small number of the highest-priority chunks before the ChunkServers came back online. When they came back, the Master would mark the re-replicated chunks as having 4 replicas instead of 3, and schedule the extras for deletion.

This is an elegant property of the lazy, throttled approach: a brief partition causes minimal disruption because re-replication proceeds slowly and can be paused/reversed when the servers come back. An aggressive immediate re-replication policy would waste enormous bandwidth on false alarms. The cost of the throttled approach: chunks in the PRIORITY 2 state (only 1 replica reachable) might remain under-protected for longer, which is a real risk during a prolonged outage.

### Phantom Failures: The Slow ChunkServer Problem

A ChunkServer that has crashed is easy to detect — it stops sending heartbeats and stops responding to requests. But what about a ChunkServer that is still running, still sending heartbeats, but is extremely slow? This is a "phantom failure" — from the system's perspective, the server is alive, but from the user's perspective, it's as bad as dead.

```
PHANTOM FAILURE SCENARIO

  CS-77 has a failing disk. Disk I/O takes 5-10 seconds
  instead of the normal 10-100ms.

  CS-77 status from Master's perspective:
  ✓ Sending heartbeats (still alive — disk failure doesn't
    stop the networking stack)
  ✓ Chunk inventory reports arriving
  ✓ Version numbers current

  CS-77 status from client's perspective:
  ✗ Read requests timeout (5s+ for a 64MB chunk read)
  ✗ Write requests timeout (holding up whole write pipeline)
  ✗ GFS client retries to other replicas after timeout

  Result:
  - CS-77 looks healthy to the Master
  - CS-77 looks broken to every client
  - Clients avoid CS-77 after enough failures
  - CS-77 stays in the cluster, receiving no client traffic,
    but the Master still thinks it's fully operational
  - Chunks on CS-77 are not re-replicated (Master sees 3 replicas)
  - The cluster has less effective redundancy than it appears
```

**How GFS handled this:** The original GFS design did not have a built-in mechanism to detect slow ChunkServers specifically. The client-side timeout and retry logic would handle individual reads (the client retries with another replica), but the Master would not demote or remove a slow ChunkServer based on read latency alone. Operators monitored per-ChunkServer latency metrics externally and manually decommissioned slow servers.

Modern storage systems handle this more gracefully. Ceph has "slow ops" detection that automatically throttles or marks OSD (Object Storage Daemon) nodes as slow. HDFS has a similar mechanism for DataNodes. The GFS paper's design was ahead of its time in many ways but did not solve phantom failures elegantly — that lesson was learned operationally and incorporated into later systems.

### Brainstorming Questions — Part 7

**Q: GFS uses heartbeats to detect failures. What is the minimum possible downtime a GFS cluster experiences when a primary ChunkServer for an active write dies?**

The minimum downtime has several components, each with a floor:

First, heartbeat detection: the Master detects a dead ChunkServer when it misses a heartbeat. With 30-second heartbeat intervals and a 2-missed-heartbeat policy (common), detection takes at minimum 30-60 seconds. You can lower this by reducing the heartbeat interval, but sub-second heartbeat intervals at 1,000+ ChunkServers creates significant Master processing overhead (1,000 heartbeats/second continuously).

Second, lease expiration: even after detecting the primary is dead, the Master must wait for the dead primary's lease to expire before granting a new lease to another ChunkServer. The lease was designed to last 60 seconds specifically to ensure the dead primary can no longer be active — you need the lease expiration as a hard guarantee that there are no two simultaneous primaries. If the primary crashed 45 seconds into its lease, the Master must wait 15 more seconds before granting a new lease. Worst case (primary dies 1 second into a new lease): wait 59 more seconds.

Third, new primary onboarding: after the new lease is granted, the new primary must synchronize its state with the secondaries (checking that all have the same version of the chunk). This takes a few seconds of coordination.

**Total minimum downtime for writes to an affected chunk: 30-120 seconds.** During this window, writes to that chunk are blocked. Reads continue from any surviving replica. For Google's batch workload, a 30-120 second pause per affected chunk was acceptable — a MapReduce job would simply wait and resume. For a low-latency online service, this would be unacceptable, which is why GFS was explicitly not designed for online serving workloads.

---

### Real Incident (Part 7): The 2011 GFS Availability Challenge

As Google's infrastructure scaled from 2003 to 2010, the single-Master GFS design began to show cracks. The Master's memory was approaching its practical limit as file counts grew into the hundreds of millions. More critically, Master recovery from a crash took longer as the operation log grew — in some cases, recovery took 15-20 minutes, during which the entire cluster was unavailable for writes.

Google's response was to build Colossus (internally called GFS2), which distributed the metadata tier across many nodes using a Bigtable-backed metadata service. Colossus eliminated the single-master bottleneck entirely. There is no single node whose crash causes cluster-wide write unavailability. The lesson for the industry: GFS's single-master design was the right simplification for 2003, with the implicit understanding that the design would need to evolve. Publishing the GFS paper in 2003 gave the industry the pattern; Colossus shows what the next level looks like when you've scaled past that pattern's limits.

---

## Part 8: Consistency Model

### What GFS guarantees — and what it doesn't

This is the hardest part of GFS and the part most candidates skip. Understanding the consistency model is what separates L5 from L6 understanding of GFS.

GFS defines two states for regions of a file after a mutation:

**Defined:** All clients will see what the mutation wrote, and the region is consistent across all replicas.

**Consistent but undefined:** All clients see the same data, but the data might be a mix of multiple concurrent mutations interleaved in an arbitrary order.

**Inconsistent:** Different replicas might show different data. This happens when a write partially failed.

```
┌─────────────────────────────────────────────────────────────────────┐
│                   GFS CONSISTENCY TABLE                             │
│                                                                     │
│  Write type              │ Success        │ Failure                 │
│  ──────────────────────────────────────────────────────────         │
│  Serial write            │ defined        │ inconsistent            │
│  Concurrent writes       │ consistent,    │ inconsistent            │
│                          │ undefined      │                         │
│  Serial record append    │ defined*       │ inconsistent at         │
│                          │ (*interspersed │ some replicas           │
│                          │ with padding)  │                         │
│  Concurrent record append│ defined*       │ inconsistent at         │
│                          │ (*may have     │ some replicas           │
│                          │ padding/dups)  │                         │
└─────────────────────────────────────────────────────────────────────┘
```

### Why concurrent writes are undefined

If two clients write to the same offset simultaneously, GFS's primary will serialize them — one goes first, one goes second. But the clients don't know which order the primary chose. Client A might think it wrote "HELLO" at offset 100, and Client B might think it wrote "WORLD" at offset 100. The primary wrote "HELLO" then "WORLD" — so offset 100 now contains "WORLD" and "HELLO" was overwritten. Client A is surprised.

This is the "consistent but undefined" state: all replicas agree the data at offset 100 is "WORLD", but the outcome was undefined from the clients' perspective.

### Why GFS applications use appends, not writes

The atomic record append solves this problem. When Client A and Client B both try to append, GFS guarantees that each append succeeds atomically — Client A's data ends up at some offset, Client B's data ends up at a different offset, they don't overlap. Both clients are told their offset and can verify their data is there. This is "defined": the client knows exactly what was written and where.

Google's MapReduce, Bigtable, and other systems were all built around atomic record appends, not random writes, specifically because of GFS's consistency model.

### Concurrent Append: Step-by-Step Trace

Let's trace two clients simultaneously appending to the same chunk. This is the scenario that trips up most candidates. Understanding it precisely is the difference between L4 and L5 GFS knowledge.

**Setup:** Chunk C4a91b2f currently has 100MB of data (it's a 64MB chunk that was extended by a previous concurrent append that allowed it to grow slightly past 64MB — GFS allows chunks to grow up to 64MB + the size of the largest single append). CS-12 is the primary. Clients A and B both want to append 10MB each.

```
TIME 0: Both clients have gotten metadata from Master.
        Both know CS-12 is primary for C4a91b2f.

CLIENT A              CS-12 (primary)          CLIENT B
    |                      |                       |
    |-- push 10MB data --->|<-- push 10MB data ---|
    |   (pipeline: A's     |   (pipeline: B's     |
    |    data to CS-47,    |    data to CS-47,    |
    |    CS-89)            |    CS-89)             |
    |                      |                       |
    |-- APPEND cmd ------->|                       |
    |                      |                       |
    |              CS-12 SERIALIZES:               |
    |              Client A's append goes first    |
    |              (arbitrary ordering)            |
    |                      |                       |
    |              [Current end = 100MB]            |
    |              [A's data goes at offset 100MB] |
    |              [New end after A = 110MB]        |
    |                      |                       |
    |              CS-12 -> CS-47: "WRITE A's data |
    |                               at offset 100" |
    |              CS-12 -> CS-89: "WRITE A's data |
    |                               at offset 100" |
    |              Both ACK.                       |
    |<-- SUCCESS (offset 100MB) -------------------|
    |                      |                       |
    |                      |<-- APPEND cmd --------|
    |                      |                       |
    |              [Current end = 110MB]            |
    |              [B's data goes at offset 110MB] |
    |              [New end after B = 120MB]        |
    |                      |                       |
    |              CS-12 -> CS-47: "WRITE B's data |
    |                               at offset 110" |
    |              CS-12 -> CS-89: "WRITE B's data |
    |                               at offset 110" |
    |              Both ACK.                       |
    |                      |<-- SUCCESS (110MB) ---|
    |                      |                       |
RESULT: Chunk C4a91b2f now has:
  Bytes 0-100MB:   original data
  Bytes 100-110MB: Client A's 10MB (at offset returned to A)
  Bytes 110-120MB: Client B's 10MB (at offset returned to B)
No overlap. Both clients know their exact offsets. DEFINED state.
```

### Partial Success: When One Secondary Fails Mid-Append

Now let's trace the more complex case: Client A's append partially succeeds (commits on primary CS-12 and one secondary CS-47, but fails on CS-89).

```
CLIENT A              CS-12 (primary)   CS-47         CS-89
    |                      |              |              |
    |-- push 10MB -------->|              |              |
    |   (pipeline)         |-- 10MB ----->|              |
    |                      |              |-- 10MB ----->|
    |                      |              |  [CS-89 disk |
    |                      |              |   error!     |
    |                      |              |   write fails|
    |-- APPEND cmd ------->|              |              |
    |                      |              |              |
    |              [CS-12 assigns offset 100MB]          |
    |              CS-12 writes at offset 100MB locally  |
    |              CS-12 -> CS-47: "WRITE at offset 100"|
    |              CS-47 writes successfully            |
    |              CS-12 -> CS-89: "WRITE at offset 100"|
    |              CS-89 fails (disk error)             |
    |<-- FAILURE --------- |                            |
    |                                                   |
NOW: CS-12 has data at 100-110MB ✓
     CS-47 has data at 100-110MB ✓
     CS-89 does NOT have data at 100-110MB ✗

STATE: INCONSISTENT
  CS-89's chunk content at offset 100MB is whatever was
  there before (possibly zeros from a previous partial write,
  possibly garbage). CS-09 disagrees with CS-12 and CS-47.

CLIENT A RETRIES:
    |-- push 10MB again -> CS-12, CS-47, CS-89 (fresh push) ---|
    |-- APPEND cmd to CS-12 -----------------------------------|
    |   [CS-12 now assigns NEW offset: 110MB]                  |
    |   [CS-12 writes at 110MB. CS-47 writes at 110MB.         |
    |    CS-89 writes at 110MB. All ACK.]                      |
    |<-- SUCCESS (offset 110MB) -------------------------------|

FINAL STATE OF C4a91b2f:
  Bytes 0-100MB:   original data          (consistent)
  Bytes 100-110MB: INCONSISTENT REGION    ← !!
                   CS-12 has Client A's first attempt
                   CS-47 has Client A's first attempt
                   CS-89 has garbage/zeros
  Bytes 110-120MB: Client A's retry       (defined, consistent)

Client A sees SUCCESS at offset 110MB and trusts that data.
The inconsistent region (100-110MB) is an orphaned partial write.
```

**What does a reader see when it reads the inconsistent region?**

If a MapReduce task reads bytes 100-110MB of this chunk from CS-12, it sees Client A's first attempt data. If it reads from CS-89, it sees garbage. This is the "inconsistent" state in GFS's consistency table — different replicas show different data.

**How does GFS prevent this from causing application-level corruption?**

GFS applications that use record append don't read by byte offset — they scan the chunk sequentially and use application-level record markers (like record length prefixes or magic bytes) to identify valid records. The inconsistent region at 100-110MB has no valid record header (it's either a partial record or zeros), so the scanner skips it or identifies it as padding. Client A's retry at 110-120MB has a valid record header (Client A wrote it completely), so the scanner reads it.

This is why GFS's design document says "applications should be designed to tolerate occasional padding and duplicate records." It's not an error case to be avoided — it's an expected, documented behavior that applications must handle.

### The Consistency State Space: A Concrete Map

```
CONSISTENCY STATE SPACE WITH EXAMPLES

┌──────────────────────┬──────────────────────────────────────────────┐
│     STATE            │  CONCRETE EXAMPLE                           │
├──────────────────────┼──────────────────────────────────────────────┤
│ DEFINED              │ Client A appends 10MB. Primary assigns       │
│                      │ offset 100MB. All 3 replicas write. Client   │
│ All replicas agree.  │ gets SUCCESS at offset 100MB. Any reader     │
│ Client knows exactly │ of bytes 100-110MB from any replica sees     │
│ what was written     │ exactly Client A's data. Perfect.            │
│ and where.           │                                              │
├──────────────────────┼──────────────────────────────────────────────┤
│ CONSISTENT but       │ Client A and Client B both do random writes  │
│ UNDEFINED            │ to offset 50MB simultaneously. Primary       │
│                      │ serializes them: A goes first, B goes        │
│ All replicas agree.  │ second. All replicas show B's data at 50MB. │
│ But the data is a    │ But Client A thought it wrote there and       │
│ mix of concurrent    │ Client B thought it wrote there. Both got    │
│ mutations.           │ a success response (if the primary is using  │
│                      │ the overwrite model, not append). The data   │
│                      │ is consistent across replicas but undefined  │
│                      │ from the clients' perspective (neither knows │
│                      │ whether their write "won").                  │
├──────────────────────┼──────────────────────────────────────────────┤
│ INCONSISTENT         │ Partial write failure scenario above:        │
│                      │ CS-12 and CS-47 have Client A's data at      │
│ Replicas disagree.   │ 100-110MB. CS-89 has garbage. Reading the   │
│ Different clients    │ same byte range from different replicas      │
│ reading from         │ returns different bytes.                     │
│ different replicas   │                                              │
│ see different data.  │ Also: a ChunkServer that missed a write due  │
│                      │ to being temporarily partitioned has an      │
│                      │ older version. Client reads stale data       │
│                      │ until Master detects the stale replica.      │
└──────────────────────┴──────────────────────────────────────────────┘
```

### Common Interview Mistakes — Part 8

**Mistake 1: Saying "GFS is eventually consistent."**
This is too imprecise. GFS's consistency model is NOT a simple spectrum from "strong" to "eventual." It has three distinct states (defined, consistent-but-undefined, inconsistent) that apply to different operation types. Serial appends give you "defined" — which is stronger than eventual consistency. Concurrent writes give you "consistent-but-undefined" — which is a specific, well-defined state. Failed writes give you "inconsistent" — which is the dangerous case. Saying "eventually consistent" erases all these distinctions and signals you haven't read the GFS paper carefully.

**Mistake 2: Assuming atomic record append guarantees no duplicates.**
Atomic record append guarantees that each successful append is written to a specific, non-overlapping offset and that offset is returned to the client. It does NOT guarantee that retried appends won't create duplicates. As shown in Failure Scenario C above, if the client retries an append that actually succeeded but whose ACK was lost, the data gets written twice at different offsets. Applications must handle duplicates using sequence numbers, checksums, or deduplication logic at the application layer.

**Mistake 3: Thinking concurrent reads have consistency problems.**
GFS's consistency issues are entirely about WRITES, not reads. Reads in GFS are straightforward: you read a chunk from a replica, the replica verifies its checksum, you get the data (or a checksum error and retry with another replica). There is no "read uncommitted" problem, no dirty reads, no phantom reads. The consistency complexity only arises when multiple clients are writing the same chunk concurrently.

**Mistake 4: Not knowing what "padding" means in GFS appends.**
When an atomic record append would cause a chunk to exceed 64MB, GFS doesn't split the record across chunks. Instead, it pads the current chunk to 64MB with zeros and starts a new chunk. The client is told to retry the append on the new chunk. The padding (zeros) will appear when a reader scans the chunk sequentially. Readers must be written to recognize and skip padding. This is another example of GFS pushing complexity to the application layer in exchange for a simpler storage layer.

### Intern → Staff Progression (Part 8)

| Level | Understanding of GFS consistency |
|-------|----------------------------------|
| **Intern** | Doesn't know GFS has a consistency model. Assumes writes are always atomic. |
| **L3** | Knows GFS is "eventually consistent." Cannot explain the specific guarantees. |
| **L4** | Knows concurrent writes can cause undefined regions. Knows record append is the solution. |
| **L5** | Can explain the full consistency table. Can explain why applications use appends. Can explain padding in concurrent appends. |
| **L6** | Can design an application layer on top of GFS's consistency model (e.g., how Bigtable builds strong consistency on top of GFS's weaker guarantees). Can explain when the undefined consistency is acceptable (batch analytics) vs. unacceptable (financial data). |

---

## Part 8b: Advanced Fault Tolerance Topics

### How the Master Decides When a ChunkServer Is Really Dead

The Master uses a simple but effective policy: if a ChunkServer sends no heartbeat for 60 seconds (configurable), it is considered dead. But "dead" in this context means "temporarily unreachable" — the Master distinguishes between this soft state and a permanently failed machine.

When a ChunkServer misses its heartbeat deadline:
- Its chunks are flagged as potentially under-replicated (1 fewer replica available)
- Re-replication is scheduled based on priority (see the priority diagram above)
- The ChunkServer's lease grants are revoked (it can no longer be a primary)

But the Master does NOT immediately delete the chunks or assume they are lost. If the ChunkServer reconnects within a grace period (say, 5-10 minutes), the Master reconciles: it compares the ChunkServer's current chunk versions against its records. Up-to-date chunks are restored to full replication status (canceling any in-progress re-replication). Stale chunks are marked for deletion.

This reconciliation behavior means GFS handles "flapping" ChunkServers (machines that briefly lose connectivity and reconnect) gracefully. A machine that goes offline for 3 minutes during a network maintenance window doesn't trigger a full re-replication of all its chunks — only chunks that were actively being written during the downtime might be stale.

### The Role of Checksums in End-to-End Integrity

GFS uses checksums at two distinct levels, and understanding both is important for interview depth:

**Block-level checksums (within a chunk):** Each 64KB block of a chunk has a 32-bit CRC32 checksum stored in a separate file alongside the chunk data on the ChunkServer's local disk. When reading a block, the ChunkServer recomputes the CRC and compares it to the stored value. This catches bit rot and disk corruption.

**Chunk-level version numbers (at the Master):** Each chunk has a version number that is incremented every time a write lease is granted. When a ChunkServer reports its chunks to the Master, the Master compares reported versions to current versions. A ChunkServer reporting version 5 for a chunk that the Master knows is at version 7 means that ChunkServer missed two lease grants — its replica is stale.

These two mechanisms catch different failure modes:
- CRC catches data corruption without mutation (bit rot, disk errors, network bit flips)
- Version numbers catch mutation divergence (missed writes due to ChunkServer being offline)

An end-to-end integrity check in GFS would be: (a) ChunkServer verifies CRC when serving reads, (b) Client gets correct version from Master before reading (so it doesn't read from a stale replica), (c) ChunkServer can optionally do background scrubbing by reading and verifying all its chunk blocks periodically.

```
CHECKSUM STORAGE LAYOUT ON A CHUNKSERVER

Chunk file on disk: /gfs/chunks/Ca1b2c3d
┌────────────────────────────────────────────────────────────────┐
│ Block 0  (64KB of data)                                        │
│ Block 1  (64KB of data)                                        │
│ ...                                                            │
│ Block N  (up to 64KB of data)                                  │
└────────────────────────────────────────────────────────────────┘

Checksum file: /gfs/checksums/Ca1b2c3d.crc
┌────────────────────────────────────────────────────────────────┐
│ Block 0 checksum: 0xA3F291BC  (4 bytes CRC32)                  │
│ Block 1 checksum: 0x7B21E489  (4 bytes CRC32)                  │
│ ...                                                            │
│ Block N checksum: 0xC98D3F01  (4 bytes CRC32)                  │
└────────────────────────────────────────────────────────────────┘

At 64MB chunk size with 64KB blocks: 1024 blocks per chunk.
Checksum file size: 1024 × 4 bytes = 4KB per chunk.
Overhead: 4KB / 64MB = 0.006%. Negligible.
```

### What Happens During a Scheduled ChunkServer Decommission

When a ChunkServer is being retired (disk life exceeded, hardware upgrade, datacenter decommission), the process is not an abrupt shutdown — it's a graceful drain:

1. Operator marks CS-12 as "decommissioning" in the Master's admin interface.
2. Master stops assigning new chunks or lease grants to CS-12.
3. Master begins migrating all of CS-12's chunks to other ChunkServers — one at a time, throttled, using spare capacity on healthy servers.
4. As each chunk is migrated, the Master updates its metadata to remove CS-12 from the replica list for that chunk.
5. When CS-12 holds no more chunks that have fewer than 3 total replicas elsewhere, it can be safely shut down.

Step 5 is the key: a chunk on CS-12 that has 3 copies on OTHER ChunkServers is already fully replicated without CS-12. The migration priority focuses on chunks where CS-12 holds the only "safe" copy (e.g., a chunk where CS-12 is the third replica and the other two are also at risk).

In a cluster with 1,000 ChunkServers each holding 10TB, decommissioning one server means migrating 10TB of data. At 100 MB/s per ChunkServer replication rate, moving 10TB takes about 28 hours. This is why decommissions are planned operations, not emergency procedures.

---

## Part 9: Limitations and What Came After

### The single-Master memory ceiling

The Master stores all chunk metadata in memory. At ~64 bytes per chunk entry:

```
┌─────────────────────────────────────────────────────────────────────┐
│                   MASTER MEMORY MATH                                │
│                                                                     │
│  Chunk size: 64MB                                                   │
│  Metadata per chunk: ~64 bytes (handle + locations + version)       │
│                                                                     │
│  Master RAM   │  Max chunks    │  Max data capacity                 │
│  ─────────────┼────────────────┼──────────────────                  │
│  1 GB         │  16M chunks    │  1 PB                             │
│  4 GB         │  64M chunks    │  4 PB                             │
│  16 GB        │  256M chunks   │  16 PB                            │
│  64 GB        │  1B chunks     │  64 PB                            │
│                                                                     │
│  Google in 2010: hundreds of petabytes, billions of files           │
│  → Master memory ceiling was real                                   │
└─────────────────────────────────────────────────────────────────────┘
```

By 2009-2010, Google's storage needs exceeded what a single Master with even the largest available RAM could handle. The single-Master design had hit its ceiling.

### The small-file problem

A 1-byte file still occupies a 64MB chunk, wasting almost the entire chunk. Billions of small files (email attachments, user-uploaded thumbnails, configuration files) would waste enormous amounts of storage. GFS was explicitly not designed for this use case, but as Google's products grew, the pressure for small-file support grew too.

### What GFS cannot do

- **Random writes** with strong consistency (the consistency model only defines appends)
- **POSIX compliance** (no atomic rename, no file locking, no permissions that other POSIX tools expect)
- **Low-latency reads** (GFS optimizes for throughput, not sub-millisecond latency)
- **Billions of small files** (chunk overhead makes it impractical)

### Brainstorming: GFS Limitations in Interview Context

**Q: GFS has a single Master. What would you change to make GFS scale to 10x its 2003 capacity without rebuilding everything?**

The most surgical change — without a complete redesign — would be to split the Master's responsibilities. In the original GFS, the Master handles three things: namespace operations (create, delete, rename files and directories), chunk metadata (which chunks make up each file), and chunk location management (which ChunkServers hold each chunk). You could split these into three separate in-memory services: a namespace server, a chunk-metadata server, and a location server. Each can be scaled independently — the namespace server might have 1/10th the memory pressure of the chunk-metadata server for a crawl workload where each file has many chunks.

This "role splitting" approach is less complete than Colossus's distributed-metadata approach but far less invasive. It's the kind of incremental architectural improvement that a real engineering team might implement as a stopgap: identify the hottest single bottleneck (which one of the three Master functions is running hottest?), split that out first, and measure whether it buys enough headroom to delay a full redesign. In a system design interview, proposing this incremental approach — rather than immediately jumping to "replace the Master with Bigtable" — signals that you understand how to evolve systems pragmatically.

The more fundamental limitation is that even after splitting, each of the three sub-Masters is still a single in-memory node with a finite memory ceiling. The correct long-term answer is what Colossus did: use a distributed, sharded metadata store. But the interview question is about 10x, not 100x — and role splitting might get you 10x without requiring a complete architectural overhaul.

---

**Q: If you were asked to add POSIX-compliant atomic rename to GFS (like renaming a directory with millions of files), how would you do it?**

Atomic rename of a large directory in a POSIX filesystem means: the operation completes as a single atomic event — from any other process's perspective, the directory either has the old name or the new name, never anything in between, and no partial state where some files have the new name and others have the old name.

In GFS, directory renames are operations on the Master's namespace trie. A rename of `/old/path` to `/new/path` requires atomically updating all the path-to-chunk mappings for every file under `/old/path`. If the directory has a million files, that's a million metadata updates. In the operation log, you could log a single "directory_rename" entry that, on replay, triggers updating all the sub-paths. The atomicity from the log's perspective is fine — either the entire "directory_rename" entry is replayed or it isn't.

The problem is consistency during the operation on a live system. While the Master is updating a million metadata entries in memory (which takes real time), other clients might be accessing files under the old or new path. GFS's original namespace locking model uses per-path locks (read locks for all path components, write lock on the target). A directory rename would need an exclusive write lock on the entire subtree being renamed — essentially preventing any access to those files during the rename. For a million-file directory, that lock might be held for seconds or minutes, causing a large availability impact. This is why GFS (and HDFS, and most distributed filesystems) do NOT support atomic rename of large directories — the implementation is technically possible but operationally unacceptable due to the lock contention it creates.

### Colossus (GFS2): the successor

Google built Colossus around 2010 to address GFS's scaling limits:

- **Distributed metadata**: instead of one Master with all metadata in memory, Colossus stores metadata in Bigtable — a distributed, scalable key-value store. There is no single-machine memory limit.
- **No single point of failure for metadata**: Bigtable is itself distributed and fault-tolerant.
- **Reed-Solomon encoding**: instead of 3x replication (300% storage overhead), Colossus uses erasure coding (like RAID-6) — roughly 150% storage overhead for equivalent durability.

HDFS (Hadoop Distributed File System) took a different path: it kept the single-NameNode design but added NameNode Federation (multiple NameNodes, each responsible for a subset of the namespace) to scale past the single-node limit.

```
┌─────────────────────────────────────────────────────────────────────┐
│               GFS → COLOSSUS → MODERN STORAGE                      │
│                                                                     │
│  GFS (2003):     Single Master, 3x replication, append-optimized   │
│     ↓                                                               │
│  Colossus (2010):Bigtable metadata, erasure coding, still chunked  │
│     ↓                                                               │
│  Cloud Storage:  Managed, no single master concern, object storage  │
│                                                                     │
│  Open source parallel:                                              │
│  GFS (2003) → HDFS (2006) → HDFS Federation (2012) → Ozone (2019) │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Part 10: Interview Application

### The one-sentence summary

> "GFS separates metadata from data: a single Master tracks where everything is, but never touches the data itself. Data flows directly between clients and ChunkServers. Reliability comes from software replication, not hardware reliability."

### When to reference GFS in an interview

**You're designing distributed file storage.** Reference GFS when the interviewer asks you to design large-file storage at petabyte scale. Say: "This is the GFS model — the key insight is separating the metadata tier from the data tier so the metadata service is never in the data path."

**You're discussing metadata scaling.** If someone challenges your single-metadata-server design: "That's the GFS trade-off — single master for simplicity and consistency, with the known ceiling that you hit when chunk count reaches a few hundred million. The next level is Colossus: distributing the metadata tier itself using Bigtable."

**You're discussing replication and fault tolerance.** Reference GFS's heartbeat-based failure detection and re-replication as the standard pattern.

**You're discussing consistency models.** Reference GFS when the interviewer asks about consistency in storage systems — it's a clean example of a deliberately weakened consistency model that works for its specific workload.

### How to Structure a GFS Discussion in 10 Minutes

The typical system design interview slot for discussing GFS or a GFS-like system is 8-12 minutes. Here is how a Staff-level candidate should structure that time:

```
MINUTES 0-2: REQUIREMENTS CLARIFICATION
  Ask about workload, not architecture.
  - What file sizes? (Large = GFS-appropriate. Small = bad fit)
  - Read/write ratio? (Mostly reads = easy. Heavy writes = need lease model)
  - Access pattern? (Sequential = GFS. Random = need something else)
  - Consistency requirements? (Strong = rethink GFS. Eventual = GFS okay)
  - Scale? (How much data? How many files?)

MINUTES 2-5: HIGH-LEVEL ARCHITECTURE
  Draw the three-component diagram: Master, ChunkServers, Clients.
  Explain the key separation: metadata vs. data.
  Explain why Master is NOT in the data path.
  Give concrete numbers: 64MB chunks, 3x replication, 60s leases.

MINUTES 5-8: WRITE AND READ PATHS
  Walk through the write path quickly (5 steps: metadata → data push
  → primary commit → secondary commit → ACK).
  Walk through the read path (cache → Master if miss → ChunkServer).
  Mention the lease and why it exists.

MINUTES 8-10: FAILURE SCENARIOS
  Pick ONE failure scenario and trace it completely.
  "If the primary crashes mid-write, the client retries after the
   lease expires, and the Master grants a new lease to a secondary."
  Mention re-replication and how the Master detects failures via heartbeats.

MINUTES 10-12: LIMITATIONS AND EVOLUTION
  Name the single-master ceiling.
  Calculate it: ~64 bytes/chunk × N chunks = M GB RAM needed.
  Say what comes next: distribute the metadata (Colossus pattern).
  Mention erasure coding as the next efficiency gain.
```

This structure works whether the interviewer wants a deep GFS discussion or is using GFS as a reference for a custom system design. You demonstrate knowledge of GFS while keeping the discussion anchored to engineering trade-offs, not trivia.

### L5 vs L6 calibration

**L5 says:** "I'd use HDFS or GFS for distributed file storage. It replicates data 3x for fault tolerance and has a master that tracks metadata."

**L6 says:** "This access pattern — large sequential reads, append-only writes at petabyte scale — is exactly what GFS was designed for. The key architectural decision is keeping the master out of the data path: clients get chunk locations from the master and then read/write directly to chunkservers. The main scaling ceiling is the master's memory — at ~64 bytes per chunk, a master with 64GB of RAM handles about 64PB of data. For larger scales you need a distributed metadata tier like Colossus. For this use case, the single-master design gives us simplicity and strong metadata consistency, which is the right trade-off."

### Common interview mistakes when referencing GFS

❌ "GFS is eventually consistent" — imprecise. GFS is **defined** for serial appends, **undefined** for concurrent writes, **inconsistent** for failed writes. The consistency model is nuanced.

❌ "Just use GFS for this" — name-dropping without explanation. Say WHY GFS fits: the workload, the trade-offs, the limitations.

❌ "GFS is basically like HDFS" — they're similar but the differences matter. GFS has a 60-second lease model. HDFS has a single-writer model. GFS's append semantics are more permissive. Saying they're "basically the same" signals you haven't read either paper carefully.

✅ "The GFS design principle here is X, which solves problem Y at the cost of Z."

---

## Part 11: GFS vs Modern Object Storage (S3, GCS)

### Why This Comparison Matters

GFS was designed in 2003 for batch processing of large sequential files. Amazon S3 was launched in 2006 with a fundamentally different design philosophy: object storage with a REST API, strong eventual consistency, and a billing model based on requests and bytes transferred. Today's engineers almost never build on raw GFS — they use S3, GCS, Azure Blob Storage, or Colossus. Understanding the difference between GFS and modern object storage is what allows you to choose the right tool and explain your choice in a Staff-level interview.

### Side-by-Side Comparison

```
┌──────────────────────┬──────────────────────────┬──────────────────────────┐
│  DIMENSION           │  GFS                     │  S3 / GCS                │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Metadata model       │ Single Master (one node  │ No exposed master.       │
│                      │ in memory) for namespace │ Metadata distributed     │
│                      │ + chunk locations        │ internally. No single    │
│                      │                          │ node memory ceiling.     │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Consistency model    │ Defined for serial        │ S3: strong consistency   │
│                      │ appends. Undefined for   │ since 2020 (read-after- │
│                      │ concurrent writes.       │ write for all ops).      │
│                      │ Inconsistent on partial  │ GCS: strong consistency  │
│                      │ write failures.          │ always.                  │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Chunk / Object model │ Fixed 64MB chunks.       │ Objects of any size      │
│                      │ File is sequence of      │ (0 bytes to 5TB in S3).  │
│                      │ chunks. Client assembles │ An object is atomic —    │
│                      │ chunks into file view.   │ you PUT the whole thing. │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Access patterns      │ Optimized for sequential │ Optimized for random     │
│                      │ large reads and appends. │ GET/PUT by key. Any      │
│                      │ Random small reads are   │ object accessible in     │
│                      │ slow (disk seek).        │ ~10-100ms. Both large    │
│                      │                          │ and small objects fine.  │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Durability model     │ 3x replication.          │ Erasure coding (RS-based)│
│                      │ 300% storage overhead.   │ 11 nines durability.     │
│                      │ Survives 2 simultaneous  │ ~150% storage overhead.  │
│                      │ replica failures.        │ Durability > GFS at      │
│                      │                          │ lower storage cost.      │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ API style            │ POSIX-adjacent: open,    │ REST HTTP API: PUT,      │
│                      │ read, write, append,     │ GET, DELETE, HEAD,       │
│                      │ close. Requires GFS      │ LIST. Works from any     │
│                      │ client library. Not      │ HTTP client. No special  │
│                      │ accessible over HTTP.    │ library required.        │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ File mutability      │ Append-only in practice. │ Objects are immutable    │
│                      │ Random writes supported  │ once written. Overwrite  │
│                      │ but with weak semantics. │ = upload new version.    │
│                      │                          │ S3 has versioning API.   │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Namespace model      │ Hierarchical filesystem: │ Flat keyspace: bucket +  │
│                      │ /path/to/file with       │ key string. "/" in key   │
│                      │ directories, renames,    │ is just a convention,    │
│                      │ and directory listings.  │ not a real directory.    │
│                      │                          │ No atomic rename.        │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Latency profile      │ First read: 100-200ms    │ First GET: 10-100ms      │
│                      │ (Master roundtrip +      │ (no metadata roundtrip   │
│                      │ ChunkServer read).       │ from client perspective) │
│                      │ Sustained: high          │ Sustained: high          │
│                      │ throughput, not low      │ throughput via multipart │
│                      │ latency.                 │ download.                │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ Who operates it      │ You operate the cluster: │ Managed service.         │
│                      │ hardware, Master, CS     │ No infrastructure to     │
│                      │ processes, monitoring.   │ operate. Pay per use.    │
└──────────────────────┴──────────────────────────┴──────────────────────────┘
```

### When GFS-style is Better Than S3-style

Despite S3's many advantages (managed, REST API, strong consistency, erasure coding), there are workloads where a GFS-style design is the better choice:

**Extremely high-throughput sequential writes (pipeline appends):** When a stream of data is being continuously appended by many concurrent producers (log aggregation, sensor telemetry, web crawling output), GFS's append model is simpler than S3's write-once object model. S3 doesn't support true append — you'd need to buffer data, then do a multipart upload, which has minimum part sizes and complexity.

**Large-scale batch processing with data locality:** MapReduce jobs scheduled by a system that knows where each chunk lives (data locality scheduling) can process data with zero network I/O by running the compute on the same machine as the data. S3 decouples compute from storage entirely — you always have network I/O when processing S3 data. For petabyte-scale batch jobs, this network I/O cost is significant.

**Internal Google-scale systems with dedicated hardware:** Colossus (GFS2) is operated at Google's scale on dedicated hardware with extremely high internal network bandwidth. At that scale, a managed service like S3 isn't an option (it's Google's own infrastructure). The GFS design pattern — metadata separate from data, client talks directly to data servers — remains the right approach for internal large-scale storage even in 2024.

### The Migration Pattern: GFS-style to Object Storage

Many companies built their data infrastructure on HDFS (the open-source GFS analog) during the 2010s and are now migrating to object storage (S3, GCS). Understanding why they're migrating — and what the migration challenges are — is valuable interview context.

**Why migrate from HDFS to S3:**
1. Operational simplicity: HDFS requires running NameNodes, DataNodes, ZooKeeper quorums for HA. S3 is zero ops.
2. Cost: HDFS requires dedicated machines running 24/7. S3 charges per byte stored and per request. For data that's written once and read infrequently, S3 is far cheaper.
3. Separation of compute and storage: HDFS ties data locality to compute. S3 lets you scale compute (EC2 instances, Spark clusters) and storage independently. You spin up 1000 Spark nodes for a job, then terminate them — the data stays in S3.
4. Durability: S3's 11-nines durability exceeds HDFS's 3x replication durability at equivalent cost.

**Migration challenges:**
1. Data locality: HDFS compute jobs (Spark, MapReduce) run on DataNodes that hold the data — zero network I/O for local reads. With S3, ALL reads cross the network. For large-scale batch jobs, this is a real throughput bottleneck.
2. Rename semantics: Spark and MapReduce output to a temp directory and rename it atomically to the final path when done. HDFS supports atomic rename. S3 does not have true atomic rename (it's a copy+delete, which is not atomic). Many S3 migration projects required rewriting job output protocols to avoid rename.
3. Consistency (pre-2020): Before AWS added strong consistency to S3 in December 2020, S3 had eventual consistency for overwrite and delete operations. Many HDFS-to-S3 migrations hit subtle bugs where a job would delete and recreate a partition, and a subsequent job would briefly see the old version.

Understanding this migration story is useful for interviews because it illustrates that architectural choices (HDFS vs. S3) have long-term migration costs that aren't visible at design time.

### When S3 is Better Than GFS-style

**Small and variable-size objects:** S3 handles 1KB objects and 1TB objects with the same API and the same efficiency. GFS's 64MB chunk size means tiny objects waste enormous space. S3's object model is workload-agnostic.

**REST API compatibility:** Everything in the modern cloud ecosystem can talk to S3-compatible APIs (AWS S3, GCS, MinIO, Ceph RadosGW). Client libraries exist in every language. You can access objects from a web browser. GFS requires a specialized client library — unavailable outside of Google's internal infrastructure.

**Strong consistency with simple semantics:** Pre-2020 S3 had eventual consistency for overwrite/delete operations. Post-2020 S3 has strong read-after-write consistency for all operations. GCS has always had strong consistency. This makes object storage much easier to reason about than GFS's complex consistency model.

**Zero operational overhead:** S3 and GCS are fully managed. You pay for storage and requests but don't manage ChunkServers, don't worry about Master memory limits, don't respond to on-call pages when a rack fails. This operational advantage is enormous for teams without dedicated storage infrastructure engineers.

### Intern → Staff Progression (Part 11)

| Level | Understanding of GFS vs modern object storage |
|-------|----------------------------------------------|
| **Intern** | "S3 is like GFS but hosted in the cloud." No understanding of the architectural differences. |
| **L3** | Knows S3 uses REST API, GFS uses a custom protocol. Cannot explain consistency differences or when to choose one over the other. |
| **L4** | Understands the object model (S3) vs chunk+namespace model (GFS). Can explain the consistency model difference (S3 strong, GFS complex). |
| **L5** | Can articulate when GFS-style is better (streaming appends, data locality for batch compute) vs S3-style (REST access, small objects, managed operations). Understands erasure coding vs replication trade-offs. |
| **L6** | Can design a system that uses object storage (S3/GCS) as the durability layer while solving for the cases where S3's model is insufficient (e.g., streaming writes via a write-ahead buffer + periodic object uploads). Can explain Colossus's design as GFS evolved to use S3-like durability primitives internally. Can evaluate a specific workload and give a precise recommendation with quantitative reasoning (storage overhead, throughput, latency). |

### Common Interview Mistakes — Part 11

**Mistake 1: Saying "GFS and S3 are basically the same because they both store large files."**
This misses the fundamental architectural difference: GFS has a client library that talks a custom protocol and gets chunk-level metadata, while S3 has a REST API where every object is accessed by a single URL with no concept of chunks exposed to the client. The access model, the metadata model, the mutability model, and the consistency model are all different. Saying they're "basically the same" signals you haven't thought carefully about either system.

**Mistake 2: Not knowing that S3 now has strong consistency.**
Before December 2020, S3 had eventual consistency for overwrite and delete operations. Many candidates (and many engineers) still believe S3 is eventually consistent. As of December 2020, S3 provides strong read-after-write consistency for all operations including overwrite and delete. When comparing GFS's consistency model to S3's, the current answer is that S3's consistency is STRONGER than GFS's — not weaker. GFS has the complex "defined/undefined/inconsistent" model; S3 just has strong consistency.

**Mistake 3: Treating "managed vs. self-hosted" as a minor operational detail.**
At Staff level, the decision to use a managed service like S3 vs. running your own distributed storage is a major engineering strategy decision, not a minor ops detail. Managed services cost more per GB but eliminate the need for dedicated storage infrastructure engineers. Self-hosted systems (HDFS, Ceph) are cheaper per GB at large scale but require significant expertise to operate reliably. For most product engineering teams, the correct answer is managed services. For infrastructure-scale teams at Google/Meta/Netflix, self-hosted is justified. Knowing WHEN to use each — and being able to articulate the break-even economics — is what L6 looks like.

### Brainstorming Questions — Part 11

**Q: An engineer on your team wants to build a new system that stores ML training datasets. They suggest using S3. You know the access pattern is sequential reads of large files by hundreds of GPU machines simultaneously. Do you agree or push back?**

The first question to ask is what "simultaneously" means quantitatively. If hundreds of GPU machines all start reading the same training dataset at the same time for a single training run, each reading at, say, 1GB/s (a fast modern NVLink/PCIe-attached GPU's I/O rate), that's potentially hundreds of GB/s of aggregate read throughput from a single dataset. S3 can handle very high aggregate throughput but has per-prefix and per-bucket request rate limits. If all GPUs are reading the same S3 path and hitting the same object, S3 prefix-level throttling can become a real bottleneck. S3's architecture shards traffic by object key prefix, so the solution is often to shard the dataset across many key prefixes — but that requires careful data layout design, not just "put the files in S3."

The second consideration is latency and throughput per reader. S3 GET latency is typically 10-100ms for the first byte, then streaming throughput of 100-300 MB/s per connection from a well-peered region. A GPU machine that needs data at 1+ GB/s would need multiple parallel S3 connections, which is possible but adds client-side complexity. By contrast, a GFS/HDFS-style system with data locality would deliver data from local disk at 200-500 MB/s per disk with essentially zero network latency. For training jobs that run for hours on thousands of GPUs, the aggregate I/O throughput at the start of each training epoch (when data is loaded) can be the bottleneck — and object storage's per-connection throughput limits matter.

My recommendation: push back slightly, not on using S3 entirely, but on using S3 naively. For ML training data at this scale, the production-grade approach is to use S3 as the durable storage layer but cache data locally on training machines or in a distributed cache (like Alluxio or a custom NFS-mounted SSD tier) for the duration of the training run. The first epoch reads from S3 (warming the cache), subsequent epochs read from the local cache at disk speed. This pattern — "S3 as truth, local cache for hot access" — is how companies like OpenAI and Databricks run large-scale ML training. Pure S3 reads for every epoch of a multi-day training run would create both throughput and cost problems at scale.

---

## Real Life Product Incidents

### Incident 1: The Master Memory Ceiling (Google, 2009–2010)

By 2009, Google was running GFS clusters with hundreds of millions of files. The Master's memory was approaching practical limits — not just RAM capacity, but the performance degradation that comes from large in-memory data structures. Master operations that used to take microseconds were taking milliseconds as the metadata grew. Background tasks like garbage collection and re-replication were taking longer, competing for Master CPU with client requests.

The initial mitigation was to run many smaller GFS clusters instead of one giant one — different product teams used different clusters, keeping each cluster's file count manageable. But this created operational complexity (which cluster is this file in?) and made it hard to share storage across teams. Google eventually built Colossus to solve this at the architectural level: distributing the metadata tier using Bigtable eliminated the per-cluster memory ceiling entirely. The lesson: a design that was "right for now" in 2003 needed architectural evolution by 2010 — and Google planned for this by publishing the GFS paper (creating the intellectual foundation for the next generation) while simultaneously building the next generation internally.

### Incident 2: The Hotspot ChunkServer Problem

When Google launched a new product or ran a new batch job that accessed a small number of very popular files, all the client machines in the MapReduce job would try to read the same chunks simultaneously. At 3 replicas per chunk, only 3 ChunkServers held each chunk — so at most 3 machines could read from each chunk simultaneously. If 1,000 MapReduce tasks all wanted to read the same 10 chunks at once, the 30 ChunkServers holding those chunks became extremely hot while the rest of the cluster sat idle.

Google addressed this in two ways. First, for particularly hot data, they temporarily increased the replication factor above 3 (to 6, 10, or even more replicas) during the period of high demand, then let it decay back to 3 afterward. Second, they changed how MapReduce scheduled tasks: instead of assigning all tasks to read the same input files simultaneously, the scheduler staggered the start times, spreading the read load over a longer window. Neither solution was perfect — they were both workarounds for a design that wasn't optimized for hot-spot workloads. The lesson: GFS was designed for batch sequential reads, not for bursty hot-read patterns. Using it for the latter requires operational workarounds.

### Incident 3: The Shadow Master Wasn't Actually Read-Only

In the original GFS deployment, the shadow master was described as "read-only" and was supposed to only serve cached metadata reads when the primary Master was down. In practice, engineers discovered that some clients were misconfigured and sending write requests to the shadow master. The shadow master would happily accept the metadata changes in memory but not apply them to the operation log (since it was supposed to be read-only). When the primary Master recovered and resumed leadership, there was a period of inconsistency where the shadow master's state diverged from the primary's. Google had to add explicit write rejection to the shadow master's code — something that "obviously should have been there" but wasn't in the initial implementation. The lesson: "read-only" is a policy, not an enforcement mechanism. If you rely on callers to respect a read-only designation, eventually something will violate it. Enforce it in the code.

---

## Exercises

**Exercise 1: Trace the read path**
A client wants to read bytes 150MB–160MB from a 500MB file. The client has no cached metadata. Walk through every step of the read: what the client does, what the Master responds, which ChunkServer is contacted, and what happens if that ChunkServer has a corrupted block for those bytes.

**Exercise 2: Design the Master's data structures**
Sketch the data structures the Master uses in memory to store: (1) the file namespace, (2) the file-to-chunk mapping, and (3) the chunk-to-chunkserver mapping. Which of these are stored in the operation log and which are not? Why?

**Exercise 3: Calculate Master memory capacity**
A GFS cluster has 2,000 ChunkServers, each with 10TB of storage. Files average 500MB in size. How many chunks exist in the cluster? How much memory does the Master need to store the chunk-to-chunkserver mapping? Is this feasible on a single machine?

**Exercise 4: Design the re-replication algorithm**
Two ChunkServers fail simultaneously. Describe the Master's re-replication process: how does it detect the failures, how does it identify affected chunks, how does it prioritize which chunks to re-replicate first, and how does it instruct ChunkServers to perform the replication? What happens if a third ChunkServer fails during re-replication?

**Exercise 5: Failure scenario analysis**
For each of the following scenarios, describe what GFS does and what the impact on availability is:
a) The Master crashes and recovers in 5 minutes.
b) A network switch fails, cutting off 100 ChunkServers from the Master.
c) 10% of ChunkServers fail simultaneously (disaster scenario).
d) A ChunkServer has disk corruption on 1 of its 500 stored chunks.

**Exercise 6: Interview practice**
The interviewer says: "Design a distributed file system for storing machine learning training datasets. Datasets are typically 100GB–10TB each, written once and read many times by many machines simultaneously." Give a 5-minute verbal answer that references GFS appropriately, explains the chunk-based architecture, and identifies the one key design challenge (hot-read bottleneck when many machines read the same dataset simultaneously) and how to address it.

**Exercise 7: Compare GFS and S3**
GFS and Amazon S3 both store large files across many machines. What are the three most important architectural differences between them? For each difference, explain why S3 made a different choice than GFS and what workloads that choice is optimized for.

**Exercise 8: Design for small files**
GFS handles large files efficiently but breaks down for billions of small files. Design a small-file storage system that sits on top of GFS (using GFS as the underlying durable storage layer but adding a new layer for small files). Specifically: (a) how do you pack many small files into a single GFS file to avoid the chunk waste problem? (b) how do you maintain an index of which small file is at which offset in which GFS file? (c) how do you handle deletes and updates? This is essentially how Facebook's Haystack (for photos) and Google's internal small-file systems work.

**Exercise 9: Consistency analysis**
You're building a distributed counter on top of GFS (e.g., counting page views). Each write increments the counter by 1. Explain why you CANNOT implement a correct counter using GFS random writes. Then propose two alternative implementations that DO work correctly on GFS: (a) an append-only log approach, and (b) a client-side coordination approach. For each, explain the trade-offs.

**Exercise 10: Scale calculation**
Your company is building a petabyte-scale data lake. Requirements: 5PB of data, 50TB added per day, files average 500MB, retention is 3 years, 3x replication. Answer the following: (a) How many chunks does the Master need to track? (b) How much Master RAM is needed? (c) How many ChunkServers are needed to hold all the data? (d) What is the daily ChunkServer write load in MB/s? (e) At what point (what total data volume) does the Master's memory become the binding constraint for a single-master GFS deployment?

**Exercise 11: Failure probability math**
You have 500 ChunkServers, each with a 1% monthly failure probability. (a) What is the expected number of ChunkServer failures per month? (b) What is the probability that, in a given day, at least two ChunkServers fail? (Hint: model as Poisson distribution.) (c) If a chunk has 3 replicas on independently-failing ChunkServers, what is the probability the chunk loses all 3 replicas in a single month? (d) With 1 million chunks in the cluster, how many chunks do you expect to lose data for per year (assuming 3x replication and the failure probability above)?

**Exercise 12: Design the Master's namespace lock**
GFS uses per-path read/write locks for namespace operations. Describe the locking protocol for: (a) creating a file at `/a/b/c.txt`, (b) renaming `/a/b/c.txt` to `/a/b/d.txt`, (c) deleting the directory `/a/b/` (which contains 1,000 files). For each operation, identify which paths need read locks and which need write locks, and explain why this protocol prevents concurrent operation conflicts.

---

## Homework

**Homework 1: Read the original paper.**
Read the GFS paper (Ghemawat, Gobioff, Leung, 2003 — available free online). Focus on Sections 2 (Design Overview), 3 (Master Operation), and 4 (Fault Tolerance). For each section, write one paragraph: what was the key design decision, what trade-off was made, and what modern system uses the same or a different approach.

**Homework 2: HDFS comparison.**
Read the HDFS architecture guide (Apache documentation). List five specific differences between GFS and HDFS. For each difference, explain: why GFS was designed one way, why HDFS made a different choice, and which choice is better for what workload.

**Homework 3: Design Colossus.**
Based on what you know about GFS's limitations (single-master memory ceiling, no erasure coding), and using your knowledge of Bigtable, design a high-level architecture for Colossus (GFS2). What does the metadata tier look like? How do reads work differently? How does erasure coding change the write path? Write a 1-2 page design doc.

**Homework 4: Mock interview drill.**
Ask a friend to be your interviewer. Have them say: "Design a storage system for storing the output of large MapReduce jobs — outputs are typically 10GB–1TB, written once, read sequentially by downstream jobs." Practice giving a 15-minute answer that: (1) clarifies requirements, (2) proposes a GFS-style architecture with the right naming, (3) explains the master/chunkserver split, (4) explains fault tolerance, and (5) identifies the scaling limit and next-level solution. Record yourself and watch the recording.

**Homework 5: Apply to a different domain.**
The GFS design pattern (single metadata server + many data servers, data flows directly between clients and data servers) appears in many systems beyond file storage. Identify two other systems that use this pattern and explain: what serves the "master" role, what serves the "chunkserver" role, and what are the equivalent of "chunks" in that system. (Hint: think about distributed databases, CDNs, and distributed caches.)

**Homework 6: Failure mode enumeration.**
Create a complete failure mode table for GFS. For each of the following components, list every failure mode, how GFS detects it, what GFS does in response, and what the client experiences: (a) ChunkServer disk failure, (b) ChunkServer process crash, (c) ChunkServer network card failure, (d) Master process crash, (e) Master disk failure, (f) Master + shadow master simultaneous crash, (g) network partition isolating 1 ChunkServer, (h) network partition isolating 100 ChunkServers, (i) clock skew between ChunkServer and Master. For each, classify the outcome as: no impact, degraded performance, temporary unavailability, or permanent data loss.

**Homework 7: Implement a simplified GFS client.**
Write a Python class `GFSClient` that simulates GFS client behavior. It should: (a) maintain a chunk location cache with TTL, (b) implement `read(file, offset, length)` that fetches chunk metadata from a simulated Master, reads from a simulated ChunkServer, and handles cache hits/misses, (c) implement `append(file, data)` that follows the 6-step write protocol, (d) simulate ChunkServer failure by having the simulated ChunkServer randomly reject requests, and (e) implement the retry logic for failed reads and writes. This exercise forces you to understand the exact protocol at a code level, which is what a Staff Engineer should be able to do.

---

## Advanced Interview Q&A Drill

This section contains additional interview questions with full answers — the kind that distinguish L5 from L6 in a Google-style system design interview. Each question targets a specific depth of GFS knowledge that shallow preparation misses.

---

**Q: A new engineer proposes storing GFS chunk metadata in a SQL database (like MySQL) instead of the Master's custom in-memory format. Evaluate this proposal.**

This is a classic "use off-the-shelf tools vs. custom solution" trade-off question. The proposal has merit at small scale but misses key requirements at GFS's operational scale.

The case FOR using MySQL: you get ACID transactions on metadata updates, a well-understood query language, easy debugging with SQL queries, and existing tooling for backups and replication. If GFS were managing millions of files instead of hundreds of millions, MySQL would be entirely adequate. Many small distributed storage systems successfully use PostgreSQL or MySQL as their metadata store.

The case AGAINST: GFS's metadata access pattern is not well-suited to SQL. The primary operations are: (1) look up chunk handles for a file by index (array lookup, not SQL JOIN), (2) look up ChunkServer list for a chunk handle (hash map lookup), (3) update a chunk's version number atomically (memory write). All three are sub-millisecond operations on in-memory data structures. A MySQL lookup involves parsing SQL, planning a query, executing it against B-tree indexes, returning results — even with indexes, this is 10-100x slower than an in-memory hash map lookup. At a Master handling thousands of metadata requests per second, this latency difference is significant.

More importantly, MySQL's transaction overhead is designed for general-purpose ACID transactions. GFS's metadata updates are simpler: they need durability (write-ahead log) but not general serializability (each metadata operation modifies well-defined, independent data structures). The custom operation log + checkpoint design is a specialized write-ahead log that omits the general-purpose overhead. The recommendation: use MySQL for systems with less than a few million files where operational simplicity outweighs raw performance. For GFS-scale deployments, the custom in-memory + WAL approach is the right design.

---

**Q: How would you design a monitoring system for a GFS cluster? What metrics would you collect, what alerts would you set, and what would your on-call runbook say for the top 3 alerts?**

A GFS monitoring system needs metrics at three levels: cluster-level health, per-Master health, and per-ChunkServer health.

**Cluster-level metrics:** (1) Total storage capacity vs. used — alert at 80% used. (2) Under-replicated chunk count — how many chunks have fewer than 3 replicas? Alert at any non-zero value; page on-call if >1000 chunks under-replicated. (3) Re-replication rate (chunks restored to 3 replicas per hour) — falling re-replication rate with rising under-replication count signals a cascading failure (more ChunkServers dying than re-replication can keep up with). (4) Aggregate read/write throughput — sudden drops signal a problem. Sudden spikes might signal an unanticipated load event.

**Master-level metrics:** (1) Master request latency (p50, p99, p999) — alert if p99 > 100ms. (2) Operation log size since last checkpoint — alert if growing faster than expected (might indicate checkpointing is failing). (3) Master memory usage — alert at 75% of available RAM. (4) Heartbeat processing rate — how many ChunkServer heartbeats per second is the Master processing? (5) Number of ChunkServers considered dead — sudden spikes indicate a network event.

**ChunkServer-level metrics:** (1) Disk usage per server. (2) Read/write error rate per server — alert if checksum failures exceed threshold. (3) Heartbeat latency per server — high latency might indicate a dying server. (4) Outstanding re-replication tasks per server.

**Top 3 on-call runbooks:**
- Alert: Under-replicated chunk count > 10,000. Runbook: check for recently dead ChunkServers in the Master's status page. Identify which machines are down. Determine if it's a rack issue (many machines from one rack) or scattered failures. If a rack is down, the re-replication should handle itself; monitor the re-replication rate. If re-replication rate is zero, check network connectivity between surviving ChunkServers.
- Alert: Master memory > 90%. Runbook: check file count growth rate. If it's a sudden spike, identify which directory is growing fastest (new product launch? runaway crawler?). Immediate mitigation: increase the master's memory limit or migrate some files to a different GFS cluster. Long-term: plan for metadata tier expansion.
- Alert: Master p99 request latency > 500ms. Runbook: check Master CPU utilization (might be under heavy garbage collection or background task load). Check if checkpointing is currently running (temporarily high latency during checkpoint). Check the operation log replay rate — if the log is very long, the Master might be recovering from a recent crash. If latency is sustained and unexplained, consider restarting the Master (it will replay its log and recover in a few minutes, with shadow master serving reads during that time).

---

**Q: The GFS paper was published in 2003. A new engineer reads it and says "this design is 20 years old, we shouldn't base our new system on it." How do you respond?**

The engineer is half right and half wrong, and knowing the difference is what senior engineers do.

The half that's wrong: the fundamental architectural pattern in GFS — separating metadata from data, keeping metadata in a fast in-memory service, having clients talk directly to data servers — is NOT obsolete. This pattern is used in virtually every large-scale distributed storage system built since 2003. HDFS uses it. Ceph uses it (with the Monitor playing the Master role for metadata). Azure Data Lake Storage uses it internally. Google Cloud Storage's Colossus uses it. AWS S3 uses it internally. The insight that metadata should never be in the data path is a timeless architectural principle, not a 2003-specific artifact. Any new system that doesn't separate metadata from data will hit the same scaling problems that motivated GFS in the first place.

The half that's right: specific implementation choices in GFS are genuinely obsolete for new systems. 3x replication (instead of erasure coding) wastes too much storage at modern scale. A single in-memory Master is a ceiling that modern systems hit quickly. The custom client library (instead of a REST API) creates unnecessary coupling. The lack of strong consistency for concurrent writes is a trade-off that modern systems avoid (S3 and GCS both provide strong consistency). And the assumption that files are large and sequential is wrong for many modern workloads (ML training on many small checkpoint files, serving billions of user-uploaded images).

The right response to the engineer: "Don't copy GFS's implementation. Do internalize GFS's architectural principles. When you design our new system, explain how you've applied the metadata-from-data separation, how your metadata layer scales, and what consistency model you're providing — using GFS as the reference point to show you understand the design space. GFS is a teaching tool, not a blueprint."

---

**Q: If you had to pick the single most important lesson from GFS for a modern large-scale system designer, what would it be?**

Design for your actual workload, not for a hypothetical general-purpose one.

GFS's creators studied Google's actual workload in 2003: files were large, writes were mostly appends, reads were sequential, failures were daily. Every design decision in GFS — the 64MB chunk size, the single master, the append-optimized consistency model, the lack of POSIX compliance — followed from these specific workload characteristics. The designers did not try to build a general-purpose filesystem that could handle all possible workloads. They built the right filesystem for their workload, and they documented the trade-offs explicitly.

This is the pattern that separates great system design from mediocre system design. Mediocre system design tries to be all things to all use cases ("we'll support small files AND large files AND random writes AND sequential reads AND strong consistency AND high throughput"). Great system design identifies the 20% of features that serve 80% of the actual workload, implements those excellently, and explicitly says no to the rest. GFS said no to small files, no to POSIX compliance, no to strong consistency for concurrent writes — and because of those explicit nos, it could say yes to petabyte-scale throughput at commodity hardware costs.

When you're designing a new system, the most important question is: what does our actual workload look like, and what design decisions does that drive? The GFS paper is as much a lesson in requirements analysis as it is a lesson in distributed systems implementation. The two go together — you cannot design a distributed system correctly without understanding the workload it will serve.

---

## Chapter Summary

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CHAPTER 83: KEY TAKEAWAYS                        │
│                                                                     │
│  1. GFS was designed for a specific workload:                       │
│     large files, sequential reads, append-only writes.             │
│     Every design decision follows from this.                       │
│                                                                     │
│  2. The core architecture: ONE Master (metadata only)              │
│     + MANY ChunkServers (data only) + Client (library).           │
│     The Master is NEVER in the data path.                          │
│                                                                     │
│  3. Files → 64MB chunks → 3 replicas on different racks.           │
│     The 64MB chunk size minimizes Master metadata load.            │
│                                                                     │
│  4. Write path: data flows in a pipeline (client→CS1→CS2→CS3).    │
│     Control flows through the primary only.                        │
│     The lease ensures exactly one primary at a time.               │
│                                                                     │
│  5. Read path: Client caches chunk locations from Master.          │
│     Reads go directly to any replica. No primary needed.           │
│                                                                     │
│  6. Fault tolerance: heartbeats detect failures.                   │
│     Master re-replicates to maintain 3 replicas.                   │
│     Operation log + checkpoints enable Master recovery.            │
│                                                                     │
│  7. Consistency: defined for serial appends, undefined for         │
│     concurrent writes. Use appends for safe concurrent access.     │
│                                                                     │
│  8. Limits: single-master memory ceiling (~1PB per 16GB RAM).      │
│     Not designed for small files or random writes.                 │
│     Colossus solves the metadata scaling problem.                  │
│                                                                     │
│  9. Interview one-liner: "GFS's key insight is keeping the         │
│     master out of the data path. Metadata at the master,           │
│     data directly between clients and chunkservers."               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## What a Staff Engineer Says vs. What a Junior Engineer Says

This table shows verbatim how different levels answer the same interviewer prompt: "Tell me about GFS." If your answer sounds like the Intern or L3 column, you know exactly what to work on.

| Level | Response to "Tell me about GFS" |
|-------|---------------------------------|
| **Intern** | "GFS is a distributed file system. It stores data across many machines." |
| **L3** | "GFS has a master node and a bunch of data nodes. Files are split into 64MB chunks, each stored on 3 machines. If a machine fails, the data is still on the other two." |
| **L4** | "GFS separates metadata from data. The Master stores the namespace and chunk locations, but data flows directly between clients and ChunkServers — the Master is never in the data path. Chunks are 64MB because that minimizes the number of Master interactions for sequential reads. 3-way replication across different racks provides fault tolerance." |
| **L5** | "GFS was designed for Google's 2003 workload: large files, sequential reads, append-only writes. The key insight is separating metadata (Master) from data (ChunkServers). Writes use a lease to designate a primary ChunkServer that serializes concurrent writes. The consistency model is complex: serial appends give you defined regions, concurrent writes give you consistent-but-undefined, failed writes can leave inconsistent regions. Applications were designed around this — they use atomic record appends rather than random writes, and handle potential duplicate records from retried appends." |
| **L6** | [Everything above, plus:] "The single-Master design has a memory ceiling: at 64 bytes per chunk entry, a 64GB Master handles about 64PB of data. Google hit this ceiling by 2010 and built Colossus, which uses Bigtable as a distributed metadata store — no single-machine ceiling. The trade-off they made choosing a single Master was simplicity and strong metadata consistency; the trade-off they accepted was the memory ceiling and recovery downtime during Master restart. For a new system today, I'd separate the 'is this the right architectural pattern?' (yes, for batch sequential large-file workloads) from 'should I implement it as designed?' (no — use erasure coding instead of 3x replication, and distribute the metadata tier from day one using an existing scalable KV store). The pattern is timeless; the specific implementation choices reflect 2003 constraints that no longer apply." |

---

## GFS Quick Reference Card

This card contains every number you should know cold for a GFS interview. If someone says "GFS" in a design discussion, these numbers should be in your head without looking anything up.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    GFS NUMBERS TO MEMORIZE                          │
│                                                                     │
│  CHUNK SIZE                                                         │
│  ─────────                                                          │
│  Chunk size:               64 MB                                    │
│  Why 64MB:                 minimize Master metadata + TCP overhead   │
│  Chunks per 1TB file:      16,384                                   │
│  Chunks per 1PB cluster:   ~16 million                              │
│                                                                     │
│  REPLICATION                                                        │
│  ───────────                                                        │
│  Default replication:      3 copies                                 │
│  Placement:                2 replicas same rack, 1 on another rack  │
│  Durability:               survives any 2 simultaneous failures     │
│  Storage overhead:         3× (300%)                                │
│  Erasure coding (Colossus):~1.5× (150%)                             │
│                                                                     │
│  MASTER CAPACITY                                                    │
│  ───────────────                                                    │
│  Metadata per chunk:       ~64 bytes (handle + locations + version) │
│  1 GB Master RAM:          16M chunks = 1 PB capacity               │
│  16 GB Master RAM:         256M chunks = 16 PB capacity             │
│  64 GB Master RAM:         1B chunks = 64 PB capacity               │
│                                                                     │
│  TIMING                                                             │
│  ──────                                                             │
│  Lease duration:           60 seconds                               │
│  Heartbeat interval:       ~seconds (configurable)                  │
│  Failure detection:        30-60 seconds (2 missed heartbeats)      │
│  Master recovery time:     2-5 minutes (checkpoint + log + CS rpts) │
│  GC grace period:          3 days (trash retention)                 │
│                                                                     │
│  CHECKSUMS                                                          │
│  ──────────                                                         │
│  Checksum granularity:     64 KB blocks (within a chunk)            │
│  Checksum type:            CRC32                                    │
│  Checksum overhead:        4 KB per 64 MB chunk (0.006%)            │
│                                                                     │
│  CONSISTENCY                                                        │
│  ───────────                                                        │
│  Serial appends:           DEFINED (strong, offset returned)        │
│  Concurrent writes:        CONSISTENT but UNDEFINED                 │
│  Failed writes:            INCONSISTENT (replicas may disagree)     │
│  Duplicate records:        possible on retry after crash            │
│                                                                     │
│  KEY DESIGN PRINCIPLES                                              │
│  ─────────────────────                                              │
│  1. Master out of data path                                         │
│  2. 3× replication for fault tolerance                              │
│  3. Heartbeat-based failure detection + automatic re-replication    │
│  4. Write-ahead log + checkpoint for Master durability              │
│  5. Append-optimized consistency model                              │
│  6. Lazy deletion (garbage collection, 3-day grace)                 │
│  7. Chunk locations NOT persisted (rebuilt from CS reports)         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## GFS Glossary: Key Terms

**Chunk:** A fixed-size (64MB) piece of a GFS file. Every file is split into one or more chunks. Each chunk is stored on multiple ChunkServers (typically 3).

**Chunk handle:** A globally unique 64-bit identifier for a chunk, assigned by the Master when the chunk is created. Used as the key in all chunk-related operations.

**ChunkServer:** A standard Linux machine with large disks that stores chunk data as plain files on its local filesystem. Does not know which GFS files its chunks belong to.

**Client library:** The GFS client is a library (not a separate server) that applications link against. It manages the GFS protocol: talking to the Master for metadata, talking to ChunkServers for data.

**Lease:** A time-limited grant (60 seconds) from the Master to a ChunkServer, designating it as the primary for a specific chunk. The primary serializes all writes to that chunk during the lease period.

**Master:** The single node in a GFS cluster that stores all metadata: the file namespace, file-to-chunk mappings, and chunk-to-ChunkServer mappings. Never touches actual file data.

**Operation log:** The Master's write-ahead log. Every metadata mutation (file create, delete, chunk allocate) is appended to this log before being applied to memory. Enables crash recovery by replaying the log.

**Checkpoint:** A compact binary snapshot of the Master's complete in-memory state at a specific point in time. Used to speed up recovery: load checkpoint, then replay only log entries since the checkpoint.

**Shadow master:** A read-only replica of the Master that applies the same operation log in near-real-time. Serves read-only metadata requests when the primary Master is down.

**Re-replication:** The process by which the Master detects that a chunk has fewer than 3 replicas (due to ChunkServer failure) and instructs another ChunkServer to copy the chunk, restoring the replica count.

**Stale replica:** A chunk replica whose version number is older than the Master's current version for that chunk. Occurs when a ChunkServer was offline during one or more write leases. Stale replicas are garbage collected.

**Garbage collection:** GFS's lazy deletion mechanism. Deleted files are renamed to a trash directory. Orphaned chunks (not referenced by any live file) are periodically identified by the Master and deleted from ChunkServers.

**Atomic record append:** A GFS write operation that atomically appends data to the end of a file at an offset chosen by the primary ChunkServer. Returns the offset to the client. Guarantees the appended region is defined (not overlapping with other concurrent appends).

**Defined:** A GFS consistency state where all replicas agree and the client knows exactly what data is at a given region. Achieved by successful serial appends.

**Consistent but undefined:** All replicas agree but the data might be an arbitrary interleaving of concurrent writes. Clients cannot predict what they'll see in this region.

**Inconsistent:** Different replicas show different data for the same region. Occurs after partial write failures.

**Pipeline replication:** The data forwarding scheme where the client sends data to one ChunkServer, which forwards to the next, which forwards to the third — a chain. Reduces client outbound bandwidth from 3× data size to 1× data size.

**Heartbeat:** A periodic signal (every few seconds) sent from each ChunkServer to the Master, reporting the ChunkServer is alive and providing chunk inventory summaries. Missing heartbeats trigger failure detection.

**Rack-aware placement:** GFS's policy for placing chunk replicas across ChunkServers: at most one replica per rack for the first two replicas, then the third on the same rack as the second but a different machine. Balances fault tolerance against cross-rack bandwidth usage.

---

---

### Connecting GFS to Other Chapters

- **Chapter 84 (Bigtable):** Bigtable is built on top of GFS. Bigtable stores its SSTable files in GFS. Understanding GFS's consistency model explains why Bigtable has to implement its own locking (the Chubby lock service) rather than relying on GFS — GFS's consistency guarantees are not strong enough for Bigtable's transactional semantics.
- **Chapter 41b (Google Systems Overview):** GFS is the storage layer for the entire Google foundational stack. MapReduce reads/writes GFS. Bigtable reads/writes GFS. Colossus is GFS2. Every Google large-scale system touches GFS.
- **Chapter 28 (Databases and Data Stores):** The decision between a distributed filesystem (GFS), an object store (S3), and a distributed database (Spanner) depends on access pattern, consistency requirements, and operational constraints — exactly the decision framework in Ch28.

*Chapter 83 complete. Next in the Google Foundational Systems series: Chapter 84 — Bigtable. Pairs with Ch41b (overview of all Google systems) and Ch28 (databases, choosing and evolving data stores).*

---

## Interview Simulation — GFS (Google File System)

*45-minute deep-dive interview on Google's GFS paper (Ghemawat et al., SOSP 2003). Interviewers expect you to have read the paper and understand why Google made non-standard choices — especially the single master, relaxed consistency, and 64MB chunk size.*

### Phase 1: System Overview and Motivation (10 min)

> **Interviewer:** Why did Google build GFS instead of using an existing distributed filesystem like NFS or AFS?

**Candidate:** Google's workload in 2003 violated every assumption those systems were built on. NFS and AFS were designed for workloads dominated by small random reads and writes — the typical file server pattern. Google had three fundamentally different properties. First, file sizes: GFS files were tens to hundreds of gigabytes, not kilobytes. The overhead of tracking millions of small blocks didn't make sense. Second, access pattern: Google's jobs were almost entirely large sequential reads and appends, not random writes. The correctness guarantees NFS provides for random writes are expensive and unnecessary for append-only workloads. Third, failure model: Google ran on commodity machines in warehouse-scale deployments where hardware failures were expected daily, not exceptional events.

The most important design insight: "optimize for what your workload actually does, not for what a general-purpose system does." GFS chose 64MB chunks to minimize master metadata overhead, appended-optimized consistency to simplify the common case, and a single master because distributed coordination is expensive and a single master with good monitoring is good enough for their failure rates.

> **Interviewer:** What does "relaxed consistency" mean in GFS specifically?

**Candidate:** GFS defines three states for file regions after a mutation: consistent (all clients see the same data), defined (consistent AND clients see the complete mutation), and undefined (consistent but may reflect interleaved mutations from concurrent writers). Defined is the strongest — what you get after a successful serial write. Undefined-but-consistent is what you get after concurrent writes complete successfully — all replicas agree on the bytes, but the bytes may be an interleaving of the concurrent writes. Inconsistent is what you get after a failed mutation — different replicas may show different data.

The key practical implication: GFS makes record append (atomic append-at-least-once) the primary write primitive rather than arbitrary overwrites. Append gives you defined regions at the boundaries where GFS picks the offset. An append may succeed on some chunkservers and fail on others; GFS retries, potentially writing the same record twice. Applications must handle duplicates — typically via checksums or sequence numbers embedded in records.

---

### Phase 2: Key Design Decisions (15 min)

> **Interviewer:** Why is the master a single node? How does that not become a bottleneck?

**Candidate:** The master stores only metadata: namespace (directory tree), file-to-chunk mapping, and chunk locations. It does NOT store file data. The key insight is that GFS keeps the master out of the data path entirely.

```
GFS Architecture
================

Client
  |
  |--[1. filename + offset]-->  Master
  |<--[2. chunk handle + CS list]--
  |
  |--[3. data + chunk handle]-->  Primary ChunkServer
                                    |--[4. forward data]--> Secondary CS1
                                    |--[4. forward data]--> Secondary CS2
                                    |--[5. ACK chain back to Primary]
  |<--[6. write complete]--

Master stores: namespace tree, file→chunk map, chunk→CS locations
Master does NOT touch data flow: steps 3-6 bypass master entirely
Chunk size = 64MB → 1TB file = ~16K chunks → master metadata fits in RAM
```

Master handles: open/create/delete/rename (namespace operations), chunk lease management, garbage collection, rebalancing. These are control-plane operations — they happen once per file open, not once per block read. With 64MB chunks, a client handles hundreds of MB of I/O per master interaction. The master's metadata fits entirely in RAM (~50 bytes per chunk → 1PB of data = ~1GB of metadata), so every operation is an in-memory lookup.

Shadow masters provide read-only replication of master state for read availability during master failure — they're slightly stale (lag the master by seconds) but sufficient for reads.

*(Cross-question: what happens during master failure?)* Shadow masters continue serving reads. Writes stall until the master recovers or a new master is promoted. GFS accepted this: master failover takes minutes, which is tolerable for batch jobs but unacceptable for interactive workloads — which is why Colossus (GFS2) moved to a distributed master.

> **Interviewer:** Explain how the lease mechanism works for writes.

**Candidate:** GFS uses leases to designate a primary chunkserver for each chunk. The master grants a 60-second lease to one chunkserver; that chunkserver is the primary and serializes all mutations to that chunk during the lease period. This gives you a single serialization point without the master being in the data path.

The write flow: client asks master for primary chunkserver → master returns primary and secondary locations → client pushes data to all chunkservers (they buffer it) → client sends write request to primary → primary serializes, writes locally, sends to secondaries → secondaries apply in same order → primary responds to client.

The lease renewal is the clever part: the primary can extend its lease from the master before it expires without any coordination overhead for ongoing writes. If the master can't reach the primary (network partition), it simply waits for the lease to expire (60 seconds) before granting a new lease to another chunkserver. This prevents split-brain without requiring explicit revocation.

---

### Phase 3: Trade-offs and Alternatives (10 min)

> **Interviewer:** GFS's relaxed consistency causes applications to see duplicate records. Is that acceptable? What would you have to give up to get exactly-once semantics?

**Candidate:** For Google's 2003 use cases — MapReduce inputs, web crawl logs, index build pipelines — duplicate records were acceptable because every pipeline could be made idempotent. A MapReduce job processes the same record twice and produces the same output; the reducer sees the duplicate and handles it. The engineering cost of idempotent application logic is much lower than the engineering cost of exactly-once storage semantics.

To get exactly-once semantics you need either: (a) a distributed transaction protocol (2PC) coordinated by the master on every write, which puts the master in the data path and kills throughput at scale, or (b) a per-record unique ID system with deduplication at read time, which requires persistent state tracking unique IDs. Option (b) is what Kafka does for exactly-once producer semantics — it's achievable but adds significant complexity. GFS made the right call for 2003 batch workloads. For streaming or transactional workloads, you'd need stronger guarantees.

> **Interviewer:** Why 64MB chunks specifically?

**Candidate:** 64MB balances three competing forces. Larger chunks mean fewer chunks, which means less master metadata and fewer master round trips for large sequential reads. Smaller chunks would have required more entries in the master's chunk location table, eventually overflowing RAM. But 64MB is large enough that a small file (say, 10MB) wastes 54MB of reserved space and creates a "hot spot" problem: if many clients access a small file simultaneously, they all go to the same few chunkservers (since the file fits in one chunk). GFS mitigated this for small executables by increasing their replication factor, but it's a known limitation.

The other constraint: network bandwidth. In 2003, GFS was designed for 100Mbps networks. Streaming 64MB in one RPC takes about 5 seconds — long enough that connection overhead is negligible. At 1Gbps (modern networks), you might go larger. At 10Gbps, smaller chunks with parallel streaming might be better.

---

### Phase 4: Modern Application (10 min)

> **Interviewer:** How would you design a GFS successor for today's infrastructure — assume 10Gbps networks, NVMe SSDs, and a need for sub-second latency?

**Candidate:** Colossus (Google's actual GFS successor) and HDFS 3.x moved in exactly this direction. The key changes I'd make: replace the single master with a distributed metadata service (like etcd or a purpose-built Paxos cluster) to eliminate the single point of failure and scale metadata operations. Reduce chunk size from 64MB to 1-4MB to enable finer-grained placement and reduce write amplification on NVMe SSDs. Add a small-file optimization layer — the GFS assumption of large files breaks for billions of small objects (think Cloud Storage / S3 patterns); you need a separate codepath for objects < 1MB. Finally, stronger consistency: at 10Gbps, 2PC adds ~1ms per write, which is acceptable for transactional workloads — modern systems (Spanner, CockroachDB) prove this.

*(Cross-question: how does Amazon S3 differ from GFS architecturally?)* S3 is an object store (flat namespace, key→blob), GFS is a POSIX-like filesystem (hierarchical namespace, files with append/seek semantics). S3's consistency model was eventually consistent until 2020 when AWS announced strong consistency for all operations. GFS's single-master metadata scales to petabytes; S3's metadata is distributed across multiple storage nodes using a proprietary B-tree-like system. S3 supports objects from bytes to 5TB with multipart upload; GFS assumes sequentially-appended large files.

> **Interviewer:** Your team is migrating a large batch analytics pipeline from HDFS to cloud object storage. What GFS concepts transfer, and what breaks?

**Candidate:** What transfers: the large-sequential-read optimization — both HDFS and S3 perform well for 128MB+ sequential reads. The failure tolerance model — assume hardware fails, design for retry. The data locality insight — in HDFS, MapReduce schedulers placed tasks near data. In cloud, you've lost data locality (compute and storage are separate), which adds 1-5ms per read vs local disk. For most analytics jobs that's fine; for latency-sensitive jobs you may want a caching tier (Alluxio, S3 Select).

What breaks: HDFS supports append (like GFS); S3 does not — S3 objects are immutable, overwritten atomically. This breaks any pipeline that relied on appending to a file. Solution: use staging (write a temp file, rename/copy to final destination). HDFS has file-level locking semantics; S3 has eventually-consistent list operations (list after put may not immediately reflect the new object). Pipelines that relied on directory listing as a completion signal need to switch to explicit marker files or job completion APIs.

---

### Common Cross-Questions and Strong Answers

**Q: What is the role of checksums in GFS?**

A: Each 64KB block within a chunk has a 32-bit checksum stored separately in memory (and persisted by chunkservers). On every read, the chunkserver verifies the checksum before returning data. On mismatch, it returns an error; the client retries from another replica; the master re-replicates the chunk from a healthy replica and schedules deletion of the corrupted one. Checksums detect silent data corruption — bit rot, bad RAID controllers, cosmic rays. The GFS paper reported that disk corruption was rare but not rare enough to ignore at Google's scale (thousands of disks). Without checksums you'd silently return corrupt data to applications.

**Q: How does GFS handle concurrent appends from multiple writers?**

A: GFS's "record append" operation picks the offset on your behalf: it appends your record to the chunk and returns the actual offset. If the append would exceed 64MB, GFS pads the current chunk and starts a new one. Concurrent appenders each get distinct offsets if their appends are serialized by the primary. If an append fails partway through (some replicas succeed, some fail), GFS retries — so replicas may contain the record at different offsets. Readers may see duplicate records across replicas at different offsets, but within a single replica's region, each record appears exactly once after the last successful append. Applications must handle cross-replica duplicates.

**Q: GFS was designed in 2003. What has changed that makes its design choices outdated?**

A: Three things. First, the single-master bottleneck: at 2003's scale (tens of PB), master metadata fit in RAM. At modern Google scale (exabytes), it doesn't. Colossus replaced the single master with a distributed metadata system. Second, the assumption of large sequential files: Google's workload shifted to include billions of small objects (YouTube videos, photos, user data). GFS's 64MB chunk size is wasteful for small files. Third, network speed: 100Mbps networks made data-local processing (MapReduce reading local chunks) essential. At 10-100Gbps, remote reads are cheap enough that compute-storage separation (Borg/Kubernetes + Colossus/S3) is often better than colocation.

---

*Chapter 83 complete. Next in the Google Foundational Systems series: Chapter 84 — Bigtable. Pairs with Ch41b (overview of all Google systems) and Ch28 (databases, choosing and evolving data stores).*
