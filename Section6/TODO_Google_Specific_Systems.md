# TODO: Google-Specific Systems Chapter

## The Gap

Google-specific systems (Bigtable, Spanner, Borg, GFS, Chubby, MapReduce) come up
frequently in Google Staff interviews as reference points. They are referenced across
existing chapters but there is no dedicated chapter on them.

Understanding the underlying concepts deeply (which this course already covers) is more
important than memorizing product names — but being able to say "this is similar to
how Spanner uses TrueTime" or "this is the Bigtable row-key design pattern" signals
genuine Google familiarity to interviewers.

## Suggested Chapter: "Google's Foundational Systems"

Cover each system at concept level (not implementation detail):

### GFS — Google File System (2003)
- Problem: store petabytes of data reliably across commodity hardware
- Key ideas: 64MB chunks, single master + many chunkservers, append-only writes
- Why it matters: influenced HDFS, distributed storage design everywhere
- Interview hook: "How would you design a distributed file system?"

### Bigtable (2006)
- Problem: scalable structured storage for web-scale data
- Key ideas: sorted key-value store, SSTable + memtable (LSM-tree), column families
- Why it matters: invented the NoSQL wide-column model (HBase, Cassandra follow this)
- Interview hook: "Design a time-series storage system at Google scale"

### MapReduce (2004)
- Problem: process terabytes of data across thousands of machines
- Key ideas: map phase (parallel transform) + reduce phase (aggregate), fault tolerance via re-execution
- Why it matters: every batch processing system (Spark, Flink) builds on this mental model
- Interview hook: "How would you compute word counts across 1TB of logs?"

### Chubby — Distributed Lock Service (2006)
- Problem: coarse-grained distributed locking and small-file storage for coordination
- Key ideas: Paxos-based, lock service, used for leader election across Google
- Why it matters: inspired ZooKeeper, etcd — any coordinator/leader election discussion
- Interview hook: "How does GFS elect its master?" → Chubby

### Spanner (2012)
- Problem: globally distributed, externally consistent relational database
- Key ideas: TrueTime API (atomic clocks + GPS), Paxos per shard, true external consistency
- Why it matters: the gold standard for global CP databases; often contrasted with CockroachDB
- Interview hook: "How would you build a globally consistent database?" (Ch27 covers HLC vs TrueTime)

### Borg — Cluster Manager (precursor to Kubernetes)
- Problem: run hundreds of thousands of jobs across Google's fleet efficiently
- Key ideas: resource packing, health monitoring, declarative job specs, quota management
- Why it matters: Kubernetes is open-source Borg; every container orchestration discussion
- Interview hook: "How would you schedule 10,000 jobs across 1,000 machines?"

## Suggested Format

Same style as existing chapters:
- College freshman level, analogies first
- ASCII diagrams for each system's architecture
- "How it maps to modern equivalents" table (GFS→HDFS, Bigtable→Cassandra, etc.)
- Interview one-liners (when to name-drop each system)
- L5 vs L6 calibration: L5 says "use Cassandra", L6 says "this is the Bigtable model because..."
- Brainstorming questions + exercises

## Priority

Medium. The existing chapters cover the underlying concepts deeply enough to pass.
This chapter adds Google fluency and name-dropping confidence — useful for interviewers
who are themselves Google engineers and will appreciate the reference.
