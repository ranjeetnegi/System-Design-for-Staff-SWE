# Chapter 85: MapReduce — Google's Batch Processing Framework

> In 2004, Google engineers Dean and Ghemawat published a paper describing MapReduce: a programming model for processing large datasets across thousands of machines. The paper wasn't about a clever algorithm. It was about a *framework* — a way to hide all the complexity of distributed computing (parallelization, fault tolerance, data shuffling, load balancing) behind two simple function calls: `map` and `reduce`. Every distributed batch processing system built since — Hadoop, Spark, Flink, Dataflow — owes its design to this paper.

---

## Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CHAPTER 85 AT A GLANCE                           │
│                                                                     │
│  Part 1:  The Problem MapReduce Solved — batch at planetary scale   │
│  Part 2:  The Programming Model        — map, shuffle, reduce       │
│  Part 3:  Architecture                 — Master, workers, GFS       │
│  Part 4:  The Execution Flow           — step-by-step walkthrough   │
│  Part 5:  Fault Tolerance              — re-execution, not logging  │
│  Part 6:  Performance Optimizations    — combiners, locality,       │
│                                          backup tasks               │
│  Part 7:  Real-World Applications      — web index, PageRank,       │
│                                          log analysis               │
│  Part 8:  Limitations and What         — Spark, Flink, Dataflow,   │
│           Came After                     streaming                  │
│  Part 9:  Interview Application        — how to apply MapReduce     │
│                                          thinking                   │
│                                                                     │
│  Real Life Incidents, Exercises, Homework at the end                │
└─────────────────────────────────────────────────────────────────────┘
```

**The one thing to remember:** MapReduce hides distributed systems complexity behind two functions. The programmer writes `map` (process one input record, emit key-value pairs) and `reduce` (aggregate all values for one key). The framework handles everything else: distributing work across thousands of machines, moving data between map and reduce workers, retrying failed tasks, monitoring progress. This separation — programmer writes logic, framework handles distribution — is the idea that launched the big data industry.

---

## Part 1: The Problem MapReduce Solved

### The situation in 2003

Google was processing the entire web. Every night, the web crawler dumped hundreds of terabytes of raw HTML pages into GFS. Every day, the indexing pipeline had to:

1. Parse every page (extract text, links, metadata)
2. Compute PageRank across the entire link graph (billions of nodes)
3. Build an inverted index (for every word in the web, which URLs contain it)
4. Detect duplicate or near-duplicate pages
5. Classify pages by language, topic, spam probability

Each of these tasks needed to process terabytes of data in parallel across hundreds or thousands of machines. And Google engineers were spending most of their time NOT on the actual logic of these tasks — they were spending their time on the infrastructure: how to split the data, how to distribute it, how to handle machine failures mid-job, how to merge results at the end.

The same boilerplate code appeared in dozens of different processing jobs:
- "Split input into 1,000 pieces and distribute to 1,000 workers"
- "If worker 47 fails, restart that piece on a different machine"
- "Collect and sort the intermediate results before the final step"
- "Merge partial results from all workers into one final output"

MapReduce was built to eliminate this boilerplate. Write the logic (map and reduce), let the framework handle the distribution.

### The analogy

Imagine you need to count all the words in 10,000 books. You have 1,000 assistants.

**Without a framework:** You'd have to figure out how to divide the books among assistants, decide what to do when an assistant calls in sick, collect all partial counts, add them up, and handle the case where two assistants counted the same book by mistake.

**With MapReduce:**
- You tell each assistant: "For every word you see, write it on a slip of paper with the number 1" (this is `map`)
- The framework collects all slips and sorts them by word (this is `shuffle`)
- You tell each assistant: "Take all the slips for one word and add up the numbers" (this is `reduce`)
- The framework handles sick assistants (re-assigns their books to someone else)

The programmer wrote two simple rules. The framework handled everything else.

### Why existing tools couldn't scale

In 2003, the alternatives for large-scale data processing were:

**Custom scripts with manual distribution:** Engineers wrote Python/shell scripts, manually split input files, ran jobs on many machines via SSH, and manually collected results. One machine failure meant manual restart of that piece. Completely unmaintainable at scale.

**Database parallel query (MPP):** Systems like Teradata could run SQL across multiple nodes. But loading terabytes of new data into a relational database every night was too slow. SQL schemas were too rigid for evolving web data. And these systems cost millions of dollars per cluster.

**Custom distributed systems:** Each team that needed to process data at scale built their own mini-distributed-system. This worked but was expensive — each team needed distributed systems expertise that should have been centralized.

MapReduce centralized the distributed systems expertise in one framework and let application engineers focus on their actual problem.

### Intern → Staff Progression (Part 1)

| Level | Understanding of the MapReduce problem |
|-------|----------------------------------------|
| **Intern** | "It's for big data processing." Cannot explain what problem it solved. |
| **L3** | Knows MapReduce processes data in parallel across many machines. Cannot explain what the framework does vs. what the programmer does. |
| **L4** | Understands the programmer-writes-logic, framework-handles-distribution separation. Knows the boilerplate that MapReduce eliminated. |
| **L5** | Can articulate why existing solutions (MPP databases, custom scripts) didn't work at Google's scale and cost. Can explain the trade-offs of the MapReduce approach. |
| **L6** | Can identify when a new processing problem is "MapReduce-shaped" vs. when it requires a different model (streaming, graph processing, iterative algorithms). Can explain why MapReduce's model is both its strength (simplicity, fault tolerance) and its weakness (no iteration, no streaming). |

### Common Interview Mistakes — Part 1

**Mistake 1: Saying "MapReduce is Hadoop."**
MapReduce is the programming model and execution framework. Hadoop is an open-source implementation of MapReduce (plus HDFS, the open-source GFS). They are not synonyms. You can run MapReduce on systems other than Hadoop. You can run many things on Hadoop that aren't MapReduce. Confusing them signals you know the brand but not the concept.

**Mistake 2: Thinking MapReduce is for real-time processing.**
MapReduce is a batch processing framework. You submit a job, it runs for minutes to hours, it produces output. There is no concept of "streaming" or "sub-second latency" in MapReduce. For real-time processing, you need different tools (Kafka Streams, Flink, Spark Streaming). Saying "use MapReduce for this real-time dashboard" is a category error.

**Mistake 3: Not knowing what problem MapReduce DOESN'T solve.**
MapReduce doesn't naturally support iterative algorithms (like machine learning training, which needs many passes over the data) or graph algorithms (like PageRank, which technically CAN be done in MapReduce but requires many rounds). Each MapReduce job is a single pass over the data. Multi-pass algorithms require chaining multiple jobs, which is slow and awkward. This limitation is exactly why Spark (which supports in-memory iterative processing) was built.

### Brainstorming Questions — Part 1

**Q: Why did Google build MapReduce instead of buying or adapting existing tools like Oracle Parallel Server or MPI?**

Google's scale in 2003 was genuinely unprecedented in commercial software. Oracle Parallel Server (OPS) could run SQL queries across multiple nodes, but it was designed for structured relational data — rows and columns with fixed schemas. Google's web data didn't fit that model. A web page is a blob of HTML with embedded links, metadata, and varying structure. You can't load billions of web pages into a relational schema and run SQL joins over it. The licensing cost was also a practical barrier: Oracle OPS licenses were priced for tens to hundreds of nodes, not for the thousands of commodity servers Google was using. Google's infrastructure philosophy was always "thousands of cheap commodity machines, not a few expensive machines."

MPI (Message Passing Interface) was the academic high-performance computing standard for distributed computation. MPI programs can be extraordinarily efficient — they give the programmer explicit control over exactly which machine sends what message to which other machine. But this power comes at a cost: MPI programs are notoriously difficult to make fault-tolerant. In an MPI computation with 5,000 processes, if one process crashes, the standard behavior is that the entire computation fails. Restarting it from scratch could mean re-running hours of work. Google was operating on commodity hardware where machine failures happened daily at cluster scale. Building a MapReduce job that would lose all progress when one machine crashed was not acceptable — Google needed automatic recovery. MapReduce's model — where each task is stateless and can be re-run independently — was purpose-built for this failure environment.

The deeper reason was organizational. Google wanted engineers who specialized in web search, advertising, or email to be able to write large-scale data processing jobs without becoming distributed systems experts. MPI requires understanding of message routing, deadlock avoidance, process synchronization, and manual checkpoint design. A junior engineer working on ad click analysis should not need to know these things. MapReduce's abstraction — "write two functions, we handle the rest" — was an organizational tool as much as a technical one. The framework encoded Google's distributed systems expertise in reusable infrastructure, making that expertise available to every engineer who needed it.

---

### Real Incident (Part 1): The Pre-MapReduce Pain at Google

Before MapReduce, Google's indexing pipeline was a collection of custom C++ programs that each engineer wrote and maintained. When an engineer left the team, the distributed-systems knowledge embedded in their program often left with them. In 2002, a critical indexing stage crashed on a machine failure and the engineer who wrote it had moved to a different team. The on-call engineer spent three days recovering the job manually — exporting partial results, restarting on new machines, re-merging outputs. Three days of delayed indexing meant stale search results for Google users.

MapReduce was partly motivated by this operational pain: jobs that are expressed in the MapReduce model can be automatically recovered from machine failures by re-executing the failed task. No human intervention, no three-day recovery, no tribal knowledge needed. The framework knows enough about the job structure to restart just the failed piece.

### Real Incident (Part 1b): The 2003 Web Crawl Volume Crisis

By mid-2003, Google's web crawler was producing approximately 20TB of new raw HTML per day — every day, a fresh dump of the crawled web loaded into GFS. The processing scripts that had worked fine at 1TB/day were now completely overwhelmed. The manual shell-script pipeline that parsed pages, extracted links, and fed the indexer was written to run on a single machine with extra output split across five others. At 20TB/day of input, this pipeline ran slower than real-time: it took 26 hours to process a single day's crawl, meaning the pipeline was perpetually falling behind.

The team's response was to manually shard the work — they split the 20TB into 20 chunks of 1TB each and had 20 engineers each "own" one chunk, running a copy of the script on their assigned servers. This worked for about three weeks until one engineer went on vacation, their servers were rebooted for a maintenance window, and their chunk of the crawl was simply never processed. The search index silently missed 1TB of new pages — users saw stale results for a subset of the web, and the problem wasn't discovered for six days because there was no monitoring for "which portion of the crawl was processed."

This incident — invisible data loss because there was no framework tracking which data had been processed — was a direct design input to MapReduce's task-tracking model. In MapReduce, the master maintains the state of every input split: idle, in-progress, or completed. There is no way for a chunk of the input to be silently dropped. If the worker processing a given split fails, the master knows it's no longer in-progress and re-assigns it. The 2003 crawl crisis taught Google that at web scale, invisible data loss is worse than visible failure — and that a framework must track every unit of work.

---

## Part 2: The Programming Model

### The two functions every programmer writes

**Map:** Takes one input key-value pair, produces zero or more intermediate key-value pairs.

```python
def map(key, value):
    # key: input record identifier (e.g., filename or offset)
    # value: input record content (e.g., one line of text)
    
    # Programmer writes this:
    for word in value.split():
        emit(word, 1)   # emit intermediate key-value pair
```

**Reduce:** Takes one intermediate key and ALL values associated with it, produces zero or more output key-value pairs.

```python
def reduce(key, values):
    # key: one intermediate key (e.g., one word)
    # values: all values emitted by map for this key (e.g., [1,1,1,1,...])
    
    # Programmer writes this:
    emit(key, sum(values))   # output: (word, total_count)
```

That's it. The programmer writes two functions. The framework handles all the distribution.

### The three phases: Map → Shuffle → Reduce

```
┌─────────────────────────────────────────────────────────────────────┐
│                    MAPREDUCE PHASES                                 │
│                                                                     │
│  INPUT (in GFS)                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ File: "the quick brown fox\nthe fox jumped\nfox is quick"   │   │
│  │ Split into 64MB input splits (one per Map task)             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                     │                                               │
│                     ▼ PHASE 1: MAP                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                          │
│  │  Map-1   │  │  Map-2   │  │  Map-3   │  (one per input split)  │
│  │          │  │          │  │          │                          │
│  │ (the,1)  │  │ (the,1)  │  │ (fox,1)  │                          │
│  │ (quick,1)│  │ (fox,1)  │  │ (is,1)   │                          │
│  │ (brown,1)│  │ (jumped,1│  │ (quick,1)│                          │
│  │ (fox,1)  │  │          │  │          │                          │
│  └──────────┘  └──────────┘  └──────────┘                          │
│                     │                                               │
│                     ▼ PHASE 2: SHUFFLE (framework does this)        │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Group by intermediate key. Sort. Send to correct reducer.   │   │
│  │                                                             │   │
│  │ (brown, [1])                    → Reducer A                 │   │
│  │ (fox, [1, 1, 1])                → Reducer B                 │   │
│  │ (is, [1])                       → Reducer A                 │   │
│  │ (jumped, [1])                   → Reducer B                 │   │
│  │ (quick, [1, 1])                 → Reducer A                 │   │
│  │ (the, [1, 1])                   → Reducer B                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                     │                                               │
│                     ▼ PHASE 3: REDUCE                               │
│  ┌───────────────────────┐   ┌───────────────────────┐             │
│  │  Reducer A            │   │  Reducer B            │             │
│  │                       │   │                       │             │
│  │  (brown, 1)           │   │  (fox, 3)             │             │
│  │  (is, 1)              │   │  (jumped, 1)          │             │
│  │  (quick, 2)           │   │  (the, 2)             │             │
│  └───────────────────────┘   └───────────────────────┘             │
│                                                                     │
│  OUTPUT (written to GFS, one file per reducer)                     │
└─────────────────────────────────────────────────────────────────────┘
```

### The shuffle: what the framework does

The shuffle phase is the most complex part of MapReduce — and the programmer doesn't write a single line of it. The framework:

1. **Partitions** the map output by intermediate key. Each key is assigned to exactly one reducer (using a partition function, typically `hash(key) % num_reducers`).
2. **Sorts** the intermediate data by key. Each reducer receives its keys in sorted order, which enables efficient grouping (all values for the same key arrive consecutively).
3. **Transfers** data from map workers to reduce workers over the network (the "shuffle" step is often the network bottleneck).

The shuffle is why MapReduce jobs have a characteristic bathtub latency profile: fast at the start (maps run in parallel), then a long pause (shuffle transfers data), then fast at the end (reduces run in parallel).

### Data types in MapReduce

Everything in MapReduce is expressed as (key, value) pairs. The key and value can be any type that can be serialized: strings, integers, custom objects, protocol buffers. The framework only requires that keys be comparable (for sorting during shuffle) and serializable (for transferring over the network).

Google's MapReduce used Protocol Buffers for all data types. Hadoop's open-source implementation uses Writable types (Java serializable objects).

### Intern → Staff Progression (Part 2)

| Level | Understanding of the programming model |
|-------|----------------------------------------|
| **Intern** | "map transforms data, reduce aggregates data." Correct but shallow. |
| **L3** | Can write a word count. Cannot explain the shuffle phase or why sorting is required. |
| **L4** | Understands all three phases (map, shuffle, reduce). Can write map and reduce functions for moderately complex tasks. |
| **L5** | Understands that the shuffle is often the bottleneck (network bound). Knows about combiners (mini-reducers that run on each map machine to reduce shuffle data). Can reason about which problems fit MapReduce naturally and which don't. |
| **L6** | Can express complex algorithms in MapReduce (multi-step PageRank, join operations, inverted index). Can reason about performance: how many reducers to use, how to minimize shuffle size, when to use combiners, when to use secondary sort. Can explain MapReduce's limitations and when to use Spark/Flink instead. |

### Common Interview Mistakes — Part 2

**Mistake 1: Thinking the programmer controls the shuffle.**
The shuffle is entirely managed by the framework. The programmer specifies how many reducers to use and can optionally write a custom partition function (to change how keys are assigned to reducers). But the sorting, data transfer, and grouping are all framework responsibilities.

**Mistake 2: Forgetting that reduce receives ALL values for a key sorted.**
A key property of the reduce call: all values for a given key are presented to the reduce function in a single call. The programmer doesn't have to handle the aggregation across multiple machines — the framework has already gathered and grouped all values for that key. This is why reduce is called "reduce" — it reduces a list of values to a single output.

**Mistake 3: Confusing map output with the final output.**
Map output is intermediate data written to local disk on each map worker. It is NOT the final output. Only reduce output is the final output, written to GFS. If you say "map workers write their output to GFS," you're describing the wrong step — maps write to local disk, and the shuffle then moves this local data to reducers.

### Brainstorming Questions — Part 2

**Q: What is secondary sort in MapReduce, and how do you sort by BOTH the key and the value?**

In basic MapReduce, the shuffle sorts output by the intermediate key only. All values for the same key arrive at the reducer in an undefined order. This is fine for word count (the order of the 1s doesn't matter) but breaks down for problems where value order matters. Consider a job that computes the sequence of events per user session: you emit (user_id, (timestamp, event_type)). The reducer receives all events for a user, but in random order — not timestamp order. You'd have to buffer all events in memory and sort them, which is expensive for users with millions of events.

Secondary sort solves this by encoding the sort key into the intermediate key itself, then using a custom partitioner to ensure all records with the same primary key still land on the same reducer. For our example: instead of emitting (user_id, (timestamp, event)), emit a composite key ((user_id, timestamp), event). The shuffle sorts all keys — which means records are sorted first by user_id, then by timestamp within the same user_id. The custom partitioner uses only the user_id component to assign records to reducers (so all events for user_id=42 go to the same reducer, regardless of timestamp). The custom grouping function tells the reducer "a new reduce call starts when user_id changes" — not when the full composite key changes. The result: the reducer receives all events for each user in timestamp order, streaming through them one at a time without buffering.

This technique is used heavily in log processing pipelines where you need to reconstruct ordered sequences per entity. It shows up in every major MapReduce tutorial but is rarely explained clearly in interviews. The key insight is that the framework's sort is "free" — you're just paying the same shuffle cost you'd always pay — but you get sorted values without any in-reducer buffering. The practical constraint: your composite key must be serializable and comparable. The practical benefit: reducers for users with millions of events can stream through the sorted sequence without ever holding the full list in memory, which can be the difference between a job that completes and one that OOM-kills every reducer.

---

### ASCII Diagram: Combiner Position in Execution Flow

```
COMBINER POSITION IN MAPREDUCE EXECUTION FLOW

  MAP MACHINE                           REDUCE MACHINE
  ──────────────────────────────        ──────────────────────────────
  INPUT SPLIT (from GFS, 64MB)
        │
        ▼
  ┌─────────────┐
  │  MAP TASK   │
  │  (user code)│
  │             │
  │  Reads each │
  │  input line,│
  │  emits      │
  │  (key, val) │
  └──────┬──────┘
         │  raw (key, val) pairs
         │  e.g., (the,1),(fox,1),(the,1),(fox,1),(the,1)
         ▼
  ┌─────────────┐   ◄─── COMBINER runs HERE, on map machine, BEFORE shuffle
  │  COMBINER   │        (optional, user-provided, must be assoc+commutative)
  │  (mini-     │
  │  reducer)   │
  │             │
  │  (the,1)×3  │──► (the,3)      ← 3 pairs → 1 pair: 3x reduction
  │  (fox,1)×2  │──► (fox,2)      ← 2 pairs → 1 pair: 2x reduction
  └──────┬──────┘
         │  pre-aggregated (key, val) pairs
         │  e.g., (the,3),(fox,2)
         │
         │  PARTITIONER splits by hash(key) % num_reducers
         │  writes to LOCAL DISK (one file per reducer partition)
         │
         ▼
  ┌─────────────────────────────┐
  │  LOCAL DISK (map output)    │
  │  partition-0: [(fox,2),...]  │
  │  partition-1: [(the,3),...]  │
  │  partition-2: [(...)   ...]  │
  └──────────────┬──────────────┘
                 │  SHUFFLE: reducer fetches its partition via HTTP
                 │  (across the network — this is the expensive step)
                 ▼
         ┌─────────────┐
         │  REDUCER    │
         │  (user code)│
         │             │
         │  Merges all │
         │  fetched    │
         │  partitions,│
         │  calls      │
         │  reduce() on│
         │  each key   │
         └──────┬──────┘
                │
                ▼
         OUTPUT → GFS

WITHOUT COMBINER: map emits raw pairs → all 10M (the,1) pairs cross network
WITH COMBINER:    combiner pre-aggs  → only ~10K (the,count) pairs cross network
                  Typical reduction: 100x-1000x for skewed keys
```

### Code Example: Top-N Items by Count Using a Combiner

```python
# Problem: Given a 1TB log file of (user_id, product_id) events,
# find the top 10 products by total click count.
#
# Naive approach: count all products, sort at end.
# Smart approach: use combiner to reduce shuffle data.

# ─── MAP FUNCTION ────────────────────────────────────────────────
def map(key, value):
    """
    key: byte offset in file (ignored)
    value: one log line "user_id=42 product_id=SHOE_001 action=click"
    """
    parts = parse_log_line(value)
    if parts['action'] == 'click':
        emit(parts['product_id'], 1)
    # emit: (product_id, 1) for every click event

# ─── COMBINER FUNCTION (runs on map machine before shuffle) ──────
def combiner(key, values):
    """
    key: product_id (e.g., "SHOE_001")
    values: iterator of counts from local map output [1, 1, 1, 1, ...]
    
    Note: combiner can use SUM because SUM is commutative and associative.
    combiner(sum(A), sum(B)) == sum(A + B) ✓
    """
    emit(key, sum(values))
    # One (product_id, local_count) per product per map machine
    # vs. N individual (product_id, 1) pairs
    # For "SHOE_001" appearing 10,000 times on one map machine:
    #   without combiner: 10,000 pairs cross the network
    #   with combiner: 1 pair crosses the network → 10,000x savings

# ─── REDUCE FUNCTION ─────────────────────────────────────────────
def reduce(key, values):
    """
    key: product_id (e.g., "SHOE_001")  
    values: partial counts from all map machines [10000, 8500, 12300, ...]
    
    Because combiner pre-aggregated per machine, values is much smaller:
    one count per map machine, not one count per event.
    """
    total = sum(values)
    emit(key, total)
    # Output: (product_id, global_total_clicks) for all products

# ─── POST-PROCESSING: Get Top-N ──────────────────────────────────
# The reduce job above produces ALL (product_id, count) pairs.
# To get TOP-10, we need a second MapReduce job:

def map_top10(key, value):
    """
    key: product_id
    value: total_click_count
    Send EVERYTHING to a single reducer (constant key) so one
    reducer sees all counts and can pick the top 10.
    """
    emit("TOP10", (value, key))  # single key forces single reducer
    # CAUTION: single reducer is a bottleneck — OK for final aggregation,
    #          not OK for main job

def reduce_top10(key, values):
    """
    key: "TOP10"
    values: all (count, product_id) pairs from all reducers
    """
    import heapq
    top10 = heapq.nlargest(10, values, key=lambda x: x[0])
    for count, product_id in top10:
        emit(product_id, count)

# ─── ALTERNATIVE: Combiner-based Top-N optimization ──────────────
# If we want to avoid the single-reducer bottleneck for top-N:
# Use combiner to keep only top-N locally, then reducer merges.

def combiner_top_n(key, values, n=100):
    """
    Instead of passing all products to reducer, each map machine
    keeps only its local top-100. Reducer then merges 1000 top-100
    lists (one per map machine) to find global top-10.
    This is valid ONLY because top-N is monotone: any global top-10
    item must appear in at least one machine's local top-100.
    """
    # Note: this combiner outputs DIFFERENT key-value than reducer input!
    # Technically this is a custom combiner, not the same as reduce function.
    top_n_local = sorted(values, reverse=True)[:n]
    for count in top_n_local:
        emit(key, count)

# Usage pattern: 2-job pipeline
# Job 1: Map=(emit product_id,1), Combiner=(sum per product), Reduce=(global sum)
# Job 2: Map=(emit "TOP10",count), Combiner=(keep top 100), Reduce=(pick top 10)
```

---

**Q: How would you implement a database JOIN in MapReduce?**

Joins in MapReduce require careful design because there's no concept of joining two tables with a shared key like in SQL. The standard approach is the "reduce-side join": both tables emit their records with the join key as the intermediate key. The reducer receives all records from both tables for a given join key and performs the join logic itself.

For a join of table A (user_id → user_info) and table B (user_id → purchase_history): Map over table A, emit `(user_id, ("A", user_info))`. Map over table B, emit `(user_id, ("B", purchase_data))`. The reducer for each user_id receives a list of records tagged with "A" or "B." It separates them, matches them up, and emits the joined record.

The performance challenge: the reducer must buffer records from one table while processing the other. If table A has one record per user but table B has millions of purchases per user, the reducer holds all of table A's record for that user in memory while streaming table B's records. Memory pressure and data skew (one user with vastly more purchases than others) are the main problems. The "map-side join" is an optimization for when one table fits entirely in memory on each map machine — the map function loads the small table into memory and joins each record of the large table against it directly, avoiding the shuffle entirely.

---

**Q: Word count is the "Hello World" of MapReduce. What's a problem that LOOKS like it fits MapReduce but actually doesn't?**

PageRank is the famous example of a problem that fits MapReduce awkwardly. One round of PageRank (distributing rank scores along links) can be expressed as a MapReduce job. But PageRank requires many rounds — typically 20-30 — to converge. Each round is one MapReduce job, which means you need 20-30 sequential MapReduce jobs. Each job writes its output to GFS and the next job reads it back. At petabyte scale, this means writing and reading terabytes from disk 40-60 times (20-30 rounds × write + read per round).

Google used iterative MapReduce for PageRank in 2003-2006 and it worked, but was slow: the PageRank computation that should take hours took days because of disk I/O between rounds. This is exactly the problem Spark solved in 2010: Spark keeps intermediate data in memory across iterations, reducing disk I/O by 10-100x for iterative algorithms. The Spark paper's benchmark headline was "20 machine learning iterations in 20 seconds with Spark vs. 200 seconds with Hadoop MapReduce" — because Spark didn't write to disk between iterations. If you're designing a system that needs iterative processing (ML training, graph algorithms), MapReduce is the wrong tool.

---

## Part 3: Architecture

### The master-worker model

MapReduce uses a Master process that coordinates all workers (Map workers and Reduce workers).

```
┌─────────────────────────────────────────────────────────────────────┐
│                    MAPREDUCE ARCHITECTURE                           │
│                                                                     │
│                    ┌────────────────┐                               │
│                    │     MASTER     │                               │
│                    │                │                               │
│                    │ • Assigns tasks│                               │
│                    │ • Monitors     │                               │
│                    │   worker health│                               │
│                    │ • Re-assigns   │                               │
│                    │   failed tasks │                               │
│                    │ • Tracks       │                               │
│                    │   progress     │                               │
│                    └────────┬───────┘                               │
│                             │ assigns tasks                         │
│              ┌──────────────┼──────────────┐                       │
│              │              │              │                        │
│        ┌─────▼──┐      ┌────▼───┐    ┌────▼───┐                   │
│        │ Map-1  │      │ Map-2  │    │ Map-3  │  ... Map workers  │
│        │        │      │        │    │        │                    │
│        │ Reads  │      │ Reads  │    │ Reads  │                    │
│        │ input  │      │ input  │    │ input  │                    │
│        │ from   │      │ from   │    │ from   │                    │
│        │ GFS    │      │ GFS    │    │ GFS    │                    │
│        │        │      │        │    │        │                    │
│        │ Writes │      │ Writes │    │ Writes │                    │
│        │ inter- │      │ inter- │    │ inter- │                    │
│        │ mediate│      │ mediate│    │ mediate│                    │
│        │ to     │      │ to     │    │ to     │                    │
│        │ LOCAL  │      │ LOCAL  │    │ LOCAL  │                    │
│        │ DISK   │      │ DISK   │    │ DISK   │                    │
│        └────────┘      └────────┘    └────────┘                    │
│                                                                     │
│        ┌────────────┐              ┌────────────┐                   │
│        │ Reduce-1   │              │ Reduce-2   │  ... Reducers    │
│        │            │              │            │                   │
│        │ Fetches    │              │ Fetches    │                   │
│        │ map output │              │ map output │                   │
│        │ from map   │              │ from map   │                   │
│        │ workers'   │              │ workers'   │                   │
│        │ local disks│              │ local disks│                   │
│        │            │              │            │                   │
│        │ Writes     │              │ Writes     │                   │
│        │ output to  │              │ output to  │                   │
│        │ GFS        │              │ GFS        │                   │
│        └────────────┘              └────────────┘                   │
│                                                                     │
│  KEY: Map intermediate output → local disk (NOT GFS)               │
│       Reduce final output → GFS                                    │
│       Reducers PULL map output (not pushed by master)              │
└─────────────────────────────────────────────────────────────────────┘
```

### Master state machine in detail

The Master is not just a coordinator — it's a stateful process that manages a complete lifecycle for every task. Understanding the state machine is critical for reasoning about fault recovery.

```
MAPREDUCE TASK STATE MACHINE

  ┌─────────┐
  │  IDLE   │  Task has been created, not yet assigned to any worker
  └────┬────┘
       │ Master assigns task to worker W
       │ (worker must be idle, preferably with data locality)
       ▼
  ┌──────────────┐
  │ IN-PROGRESS  │  Task is running on worker W
  │              │  Master expects heartbeats from W
  │              │  Master records: (task_id → worker_id, start_time)
  └──────┬───────┘
         │
    ┌────┴─────────────────────────────────────┐
    │                                          │
    │ Worker W completes task                  │ Worker W fails
    │ W sends: task_id + output locations      │ (no heartbeat for 60s)
    ▼                                          ▼
  ┌───────────┐                          ┌─────────┐
  │ COMPLETED │                          │  IDLE   │ (re-queued for assignment)
  │           │                          │         │
  │ Map task: │                          │ If MAP task was completed:
  │ output    │                          │   → ALSO reset to IDLE
  │ location  │                          │   (local disk is gone)
  │ stored in │                          │
  │ master    │                          │ If REDUCE task was completed:
  │           │                          │   → stays COMPLETED
  │ Reduce:   │                          │   (output on GFS is safe)
  │ output    │                          └─────────┘
  │ in GFS    │
  └───────────┘

  BACKUP TASK TRIGGER (near end of job):
    When > 95% of tasks are COMPLETED and some remain IN-PROGRESS:
    Master creates backup copy of in-progress task → assigned to new worker
    Two copies run simultaneously (original + backup)
    First to complete → its output is used, other is killed
```

**Master memory usage:** For a job with M map tasks and R reduce tasks, the master stores O(M + R) task state records. At 10,000 map tasks and 1,000 reduce tasks: 11,000 records, each holding a task ID, state enum, worker ID, and a list of output file locations. This is kilobytes — the master's memory usage is negligible even for very large jobs.

**Master heartbeat protocol:** Each worker sends a heartbeat to the master every few seconds (typically every 5 seconds). The heartbeat carries: (1) the list of in-progress tasks on that worker, (2) any task completions since the last heartbeat, (3) a "still alive" signal. The master updates its task state table on each heartbeat. If a worker misses heartbeats for 60 seconds, the master marks it as dead and re-queues all its tasks.

### What the Master tracks

For every map and reduce task, the Master tracks:
- **State**: idle (not yet assigned), in-progress (assigned to a worker), completed
- **Worker assignment**: which machine is running this task
- **Output location**: for completed map tasks, where on each map worker's local disk the intermediate output is stored (this is what reducers need to fetch)

The Master also acts as a conduit: when a map task completes, it sends its output location to the Master, which then tells the reducers where to find the map output when they're ready to start.

### Input splits

Before the job starts, the input data (in GFS) is divided into **input splits**, typically 64MB (matching GFS chunk size). Each input split becomes the input to exactly one Map task. The number of Map tasks equals the number of input splits. For a 640GB input, there are 10,000 Map tasks.

The split-to-chunk correspondence is intentional. GFS stores data in 64MB chunks across ChunkServers. If the Map task for a split runs on the same machine that holds that chunk (data locality), the map task reads from local disk instead of over the network — dramatically faster.

**Choosing the right number of map tasks**

More map tasks means more parallelism, but also more overhead:
- Too few (1,000 tasks for 1TB): each map task reads 1GB, tasks may be I/O bottlenecked, and task startup overhead is amortized well. But if 1% of tasks are slow stragglers, 10 tasks hold up the job.
- Too many (1,000,000 tasks for 1TB): each map task reads 1MB, but task startup overhead (1-5 seconds per task) dominates. 1,000,000 tasks × 1 second overhead = 277 hours just in startup. This is the "small files problem" in Hadoop — too many small input files create too many map tasks.
- The sweet spot: map task duration should be 30 seconds to 5 minutes. Shorter tasks have too much overhead; longer tasks delay straggler detection. For 1TB input at 200MB/s read speed, 64MB split takes 0.3 seconds to read — too small. In practice, many production jobs use 128MB or 256MB splits to increase per-task duration.

**The small files problem in practice**

A common anti-pattern: 1 million separate 1MB log files in HDFS. The naive MapReduce configuration creates 1 million map tasks (one per file). This overwhelms the master's scheduling capacity and creates enormous overhead. The fix: combine small files into larger "sequence files" before running MapReduce (HDFS's CombineFileInputFormat merges multiple small files into one map task's input). This is a real operational problem that every data engineering team encounters when ingesting per-minute log files.

**Choosing the right number of reduce tasks**

The number of reducers (R) affects:
- **Parallelism**: more reducers = faster reduce phase (more tasks run in parallel)
- **Output files**: the job produces exactly R output files. Too many reduce tasks = thousands of tiny output files, which is slow to read in the next job.
- **Per-reducer memory**: each reducer holds intermediate data for `total_shuffle_data / R`. If R is too small, reducers OOM. If R is too large, each reducer has little data — overhead dominates.
- **Rule of thumb**: R = 3 × (number of worker machines). This gives each worker ~3 reduce task slots to fill, ensuring all workers stay busy during the reduce phase without too much overhead.

### The single-master design: why it works and when it breaks

The master is a single machine with no replication in the original 2004 design. Distributed systems textbooks will tell you this is a "single point of failure" — and they're right. But Google consciously accepted this trade-off. Why?

First: master failures are extremely rare at the single-machine level. A cluster of 1,800 machines will typically see 2-5 machine failures per day (commodity hardware, full-disk failures, memory errors). But the master is one specific machine. The probability that the specific master machine fails during any given job is roughly 1/1800 of the machine-level failure rate — meaning the master fails on perhaps 0.1% of jobs. At that rate, the operational cost of "client retries failed job" is much lower than the engineering cost of building a replicated, consensus-based master.

Second: the master's state is small (kilobytes) and reconstruction is fast. GFS chunk locations are fetched at job start. Map output locations are re-reported by workers when re-assigned. If you checkpoint the master state to GFS every 30 seconds, recovery from a master crash means: restart master process, load last checkpoint, ask all workers to report their current status, and resume scheduling. This approach (lightweight checkpointing + worker-reported status) was added in later versions of Google's MapReduce and in Apache Hadoop YARN. But the original didn't have it — and still worked fine in practice because master failures were so rare.

### Intern → Staff Progression (Part 3)

| Level | Understanding of MapReduce architecture |
|-------|------------------------------------------|
| **Intern** | "There are workers that process data." Cannot explain the master's role. |
| **L3** | Knows there's a master and workers. Cannot explain task state tracking or output location management. |
| **L4** | Understands the master-worker model. Understands that map output goes to local disk, not GFS. |
| **L5** | Understands data locality (running map tasks near their input chunks). Understands why map output isn't written to GFS (performance: GFS write is slower than local disk for intermediate data). |
| **L6** | Can reason about the performance impact of the number of map tasks vs. reduce tasks. Understands speculative execution (backup tasks). Can explain the failure recovery protocol at the task level. Can articulate when the single-master design is a bottleneck and what the alternatives are. |

### Common Interview Mistakes — Part 3

**Mistake 1: Saying map output goes to GFS.**
Map tasks write their intermediate output to the **local disk** of the map worker, not to GFS. This is a deliberate performance optimization — writing to GFS requires the replication overhead (3 copies), whereas intermediate data doesn't need that durability (if a map worker fails, the task is just re-executed). Only the FINAL output (from reduce tasks) goes to GFS.

**Mistake 2: Not knowing that reducers PULL map output.**
Reducers pull map output from map workers' local disks. The master tells each reducer which map workers have output for it. The reducer opens HTTP connections to those map workers and fetches the relevant partition of the map output. The master does not push data — it only coordinates.

**Mistake 3: Thinking the master processes data.**
The master is a pure control plane. It assigns tasks, tracks state, and re-assigns failed tasks. It never reads or writes any actual data (neither input, intermediate, nor output).

### Task Scheduling and Data Locality

Data locality is the single biggest free performance optimization in MapReduce — and it happens invisibly inside the scheduler. Understanding it separates engineers who have read about MapReduce from engineers who have thought deeply about it.

**The three-tier scheduling hierarchy**

When the master assigns a map task to a worker, it consults the GFS chunk locations for that task's input split and tries to find a worker that is "close" to the data:

```
RACK-AWARE TASK SCHEDULING — ASCII DIAGRAM

  DATACENTER
  ┌─────────────────────────────────────────────────────────────────┐
  │                                                                 │
  │   RACK A (48 machines)              RACK B (48 machines)        │
  │   ┌─────────────────────┐           ┌─────────────────────┐    │
  │   │ [M1] [M2] [M3] ...  │           │ [M49] [M50] ...     │    │
  │   │  ▲                  │           │                     │    │
  │   │  └─ GFS chunk       │           │                     │    │
  │   │     (input split 7) │           │                     │    │
  │   └──────────┬──────────┘           └──────────┬──────────┘    │
  │              │ 1Gbps (intra-rack)               │               │
  │         ToR Switch A                       ToR Switch B         │
  │              │                                  │               │
  │              └──────────────┬───────────────────┘               │
  │                          Core Switch                            │
  │                    (10Gbps, SHARED across all racks)            │
  └─────────────────────────────────────────────────────────────────┘

  TIER 1: Same machine as GFS chunk
    - Read speed: ~300 MB/s (local disk, dedicated)
    - Network cost: ZERO
    - Availability: limited (chunk is on 3 machines; worker must be one of them)
    - Master assigns here FIRST if any of the 3 chunk replicas are on
      an idle worker

  TIER 2: Same rack as GFS chunk
    - Read speed: ~125 MB/s (1Gbps intra-rack switch, shared by 48 machines)
    - Network cost: intra-rack only (does not cross core switch)
    - Availability: moderate (any idle machine on same rack as any replica)
    - Master assigns here SECOND if Tier 1 not available

  TIER 3: Remote rack (any worker)
    - Read speed: ~25 MB/s (shared core network bandwidth)
    - Network cost: traverses core switch — competes with ALL other jobs
    - Availability: any idle machine anywhere
    - Master assigns here LAST RESORT

  ACTUAL NUMBERS (from 2004 MapReduce paper):
    Job with 1,800 machines, 1TB input:
    - 35% of data reads: local (Tier 1)  — 300 MB/s per task
    - 40% of data reads: same rack (Tier 2) — 125 MB/s per task
    - 25% of data reads: remote rack (Tier 3) — 25 MB/s per task
    
    Weighted average: 0.35×300 + 0.40×125 + 0.25×25 = 161 MB/s
    Without locality (all remote): 25 MB/s
    Locality improvement: 6.4x faster input reads
```

**Why does this matter in practice?**

At 1,800 machines with 1TB of input, each map task reads ~600MB of data (1TB / 1666 map tasks). At 25MB/s (all remote), that's 24 seconds per task just for reading input. At 161MB/s (with locality), it's 3.7 seconds. The map phase on 1,800 machines: 1,666 tasks / 1,800 workers ≈ all run in parallel. Map phase time: 3.7 seconds vs. 24 seconds — an 85% reduction, just from scheduling. No code change. No hardware change. Pure scheduler intelligence.

**How the master makes the locality decision**

The master maintains a complete map of "which GFS chunks are on which ChunkServers" (this information comes from the GFS master at job start). When a worker heartbeats and says "I'm idle," the master checks: are there any unassigned map tasks whose input chunks reside on THIS specific machine? If yes, assign those first (Tier 1). If no Tier 1 tasks available, are there tasks whose chunks reside on machines IN THE SAME RACK as this worker? If yes, assign those (Tier 2). Otherwise, assign whatever is available (Tier 3). This logic runs in milliseconds using a precomputed mapping from chunk → machine → rack.

### Brainstorming Questions — Part 3

**Q: How does the master decide which worker to assign a map task to? Walk through the full decision algorithm.**

The master's scheduling decision is a constraint satisfaction problem with multiple objectives. Understanding it shows you think like a framework designer, not just a framework user. The master's inputs are: (a) a list of idle workers with their machine IDs and rack IDs, (b) a list of unassigned map tasks with the GFS locations of their input chunks (each chunk has 3 replicas on 3 different machines), and (c) a priority ordering: local > same-rack > remote.

The algorithm is essentially: for each idle worker that sends a heartbeat, find the highest-priority unassigned map task that that worker can execute locally. The master precomputes an inverted index: for each GFS chunk, the list of workers that have a local copy. When a worker asks for a task, the master looks up that worker in the inverted index to find all tasks it can run locally. If that list is non-empty, it picks the first (or highest-priority) task from the list. If the local list is empty, it does the same for same-rack. If both are empty, it picks any unassigned task.

The subtle complexity comes from race conditions: two workers might both be eligible to run a map task locally, and both send heartbeats simultaneously. The master must handle this with locking — whichever worker's heartbeat is processed first gets the task assignment; the second worker gets a different task (or waits if no local task is available). This is why the master is single-threaded in Google's original implementation — avoiding lock contention simplifies the scheduling logic at the cost of single-threaded throughput. At 200 task assignments per second (1,800 workers × heartbeat every 9 seconds), single-threaded scheduling is completely adequate. This is a recurring theme in distributed systems: when a component handles control traffic (not data traffic), simple single-threaded designs often outperform complex concurrent designs because they avoid synchronization overhead.

---

Yes, local disk storage for intermediate data is less durable than GFS. If a map worker fails while a reducer is trying to fetch its output, the reducer can't get the data. But this is recoverable: the master re-executes the failed map task on a different worker, which re-produces the intermediate output. The reducer retries fetching from the new location. The total cost is one map task re-execution — typically a few minutes. Compare this to the alternative: writing map output to GFS (3x replication overhead). For a job with 10,000 map tasks producing 1TB of intermediate data, GFS replication would write 3TB vs. 1TB — a 3x increase in I/O for data that exists for only a few hours. The trade-off is correct: accept the re-execution risk (which is handled by the framework anyway) in exchange for 3x less I/O.

The deeper principle: not all data needs the same durability. Input data needs full GFS durability (it's the source of truth). Final output needs full GFS durability (it's the result of expensive computation). But intermediate data is reproducible (just re-run the map task), so it only needs local disk durability. This "tiered durability" design — persisting only what you can't reconstruct — is a pattern that appears in many storage systems.

---

## Part 4: The Execution Flow

### Step-by-step: a complete MapReduce job

Let's trace a MapReduce word count job over a 1.28GB input file, using 20 Map tasks and 5 Reduce tasks.

```
MAPREDUCE EXECUTION FLOW — COMPLETE TRACE

Job config:
  Input: /crawl/2024-01-15/shard-001 (1.28GB in GFS, 20 chunks of 64MB)
  Map tasks: 20 (one per 64MB input split)
  Reduce tasks: 5
  Combiner: yes (mini-reducer on each map machine)

────────────────────────────────────────────────────────────────────
PHASE 1: JOB SUBMISSION

  Client program → Master: "run this MapReduce job"
  Master: creates 20 map task records (state=idle) in memory
  Master: creates 5 reduce task records (state=idle) in memory
  Master: asks GFS for chunk locations of /crawl/2024-01-15/shard-001

────────────────────────────────────────────────────────────────────
PHASE 2: MAP TASKS

  Master polls idle workers (it has a pool of 100 idle machines)
  Master → Worker-7:  "Run Map task 1: input split = bytes 0–64MB"
  Master → Worker-12: "Run Map task 2: input split = bytes 64–128MB"
  ...  (all 20 map tasks assigned to workers)

  Worker-7 execution:
    1. Read 64MB from GFS (or local disk if chunk is colocated)
    2. For each line, call map(line_number, line_content)
    3. map() emits (word, 1) for each word
    4. Combiner (optional): locally aggregate by key
       (the, 1), (the, 1), (the, 1) → (the, 3)  [reduces shuffle data]
    5. Write output to local disk, partitioned into 5 files
       (partition 0 = words starting a-e, partition 1 = f-j, etc.)
       by hash(word) % 5
    6. Worker-7 → Master: "Map task 1 complete. Output locations:
       partition-0: worker7:8080/map1/part-0
       partition-1: worker7:8080/map1/part-1
       ...
       partition-4: worker7:8080/map1/part-4"
  
  Master records all output locations for Map task 1.
  All 20 map tasks complete. Total intermediate data: ~80MB
  (most words are duplicates, combiner reduced 1.28GB → 80MB)

────────────────────────────────────────────────────────────────────
PHASE 3: SHUFFLE (starts when all maps complete, or pipelined)

  Master → Reducer-1: "Start reducing. Fetch partition-0 from:
    worker7:8080, worker12:8080, worker3:8080, ... (all 20 map workers)"

  Reducer-1:
    1. HTTP GET partition-0 from worker7 (16MB)
    2. HTTP GET partition-0 from worker12 (16MB)
    ...  (fetch from all 20 map workers)
    Total fetched: 20 × ~4MB = ~80MB of a-e words across all 20 maps
    3. Merge-sort all fetched data (now sorted by key)
       (brown,1),(brown,1),(brown,1) → sorted, grouped

────────────────────────────────────────────────────────────────────
PHASE 4: REDUCE TASKS

  Reducer-1:
    Calls reduce("brown", [1,1,1,1,...])  → emits ("brown", 47)
    Calls reduce("cat", [1,1,...])        → emits ("cat", 12)
    ...
    Writes output to GFS: /output/part-r-00000

  All 5 reducers complete.
  Final output: /output/part-r-00000 through /output/part-r-00004
  Concatenated: the complete word count for the entire 1.28GB file.

────────────────────────────────────────────────────────────────────
TIMING (approximate for this example):

  Map phase:     5 minutes  (1.28GB / 20 workers reading at 50MB/s)
  Shuffle phase: 2 minutes  (80MB / 5 reducers fetching from 20 workers)
  Reduce phase:  1 minute   (sorting + counting)
  Total:         ~8 minutes (plus job overhead)
```

### Shuffle in Depth

The shuffle is the phase most MapReduce tutorials gloss over in one sentence — "data moves from maps to reduces" — but it's the most complex and performance-critical phase of the entire execution. Understanding the shuffle in depth is what separates L4 from L5 MapReduce knowledge.

**Phase 1: Sorting during the map (before data leaves the machine)**

The map worker does not simply write raw (key, value) pairs to local disk and call it done. It performs a three-step process: emit, buffer in memory, then sort and spill. As the map function emits pairs, they go into an in-memory buffer (typically 100-200MB). When the buffer is 80% full, a background thread sorts the buffer contents by key, then spills them to disk (writing a sorted run file). At the end of the map task, all spill files are merge-sorted into a single sorted file per partition (one partition per reducer). The result: each map worker's disk holds R files (one per reducer), each file is sorted by key.

Why sort at the map phase? Because sorting many small sorted files (one per map task) is much cheaper than sorting one giant unsorted file at the reducer. Merge-sorting K sorted files of size N takes O(N × log K) comparisons. Sorting one giant file of size K×N takes O(K×N × log(K×N)) comparisons. The pre-sort on each map machine distributes the sort work across thousands of machines, leaving the reducer only needing to do a K-way merge.

**Phase 2: The reducer merge-sorts from N map workers**

```
REDUCER MERGING SORTED STREAMS FROM N MAP WORKERS

  Map-1 sorted output (partition 3):  [(apple,3),(banana,7),(cherry,2),...]
  Map-2 sorted output (partition 3):  [(apple,1),(avocado,5),(cherry,8),...]
  Map-3 sorted output (partition 3):  [(banana,4),(cherry,1),(date,9),...]
  ...
  Map-N sorted output (partition 3):  [(avocado,2),(banana,6),(date,3),...]

  REDUCER receives all N sorted streams via HTTP fetch, then:

  ┌─────────────────────────────────────────────────────────────────┐
  │  MERGE SORT (N-way merge using a min-heap)                      │
  │                                                                 │
  │  Heap: peek at the first element of each of the N streams.      │
  │  Take the smallest key. Advance that stream. Repeat.            │
  │                                                                 │
  │  Result: a single sorted stream of all (key, value) pairs       │
  │  Time: O(total_pairs × log N)  — N = number of map workers      │
  │                                                                 │
  │  AFTER MERGE: consecutive pairs with same key → grouped for     │
  │  reduce() call. No additional grouping step needed.             │
  └─────────────────────────────────────────────────────────────────┘

  EXAMPLE (N=3 for clarity, real jobs have N=1000-10000):
  
  Stream 1: (apple,3) → (banana,7) → ...
  Stream 2: (apple,1) → (avocado,5) → ...
  Stream 3: (banana,4) → (cherry,1) → ...
  
  Min-heap: {(apple,3 from S1), (apple,1 from S2), (banana,4 from S3)}
  
  Step 1: pop (apple,1) from S2. Advance S2 → (avocado,5).
          Heap: {(apple,3 from S1), (avocado,5 from S2), (banana,4 from S3)}
  Step 2: pop (apple,3) from S1. Advance S1 → (banana,7).
          Heap: {(avocado,5 from S2), (banana,7 from S1), (banana,4 from S3)}
  Step 3: reducer sees consecutive (apple,1),(apple,3) → calls reduce("apple",[1,3])
  
  And so on. The merge naturally groups consecutive equal keys.
```

**Phase 3: Memory management and spilling to disk**

A reducer fetching from 10,000 map workers cannot hold all 10,000 streams in memory simultaneously — each stream might be gigabytes. The reducer uses a configurable in-memory merge buffer (typically 200-400MB). As data is fetched, it fills the buffer. When the buffer is 80% full, the contents are sorted and spilled to a temporary disk file (a sorted run). At the end of fetching, all in-memory data and all disk spill files are merge-sorted in a final pass.

The implication: reducer performance depends heavily on whether the merge fits in memory. If the shuffle data for one reducer is 100MB (fits easily), the merge is purely in-memory — fast. If the shuffle data is 50GB (does not fit), the reducer spills many sorted runs to disk and does multi-pass merge-sort — slow. Tuning the number of reducers (R) is partly about keeping per-reducer shuffle data manageable in memory.

**Typical numbers for a mid-sized job**

```
Example: 10TB input log file, word count with no combiner
  Map tasks:  10,000 (10TB / 1GB per split)
  Reduce tasks: 200
  
  Map phase output:  10TB → most words are short, emit (word, 1):
                     ~20TB of raw pairs (each pair: 10-50 bytes)
  
  After combiner (if used):
                     ~200GB (100x reduction for common words)
  
  Shuffle data in-flight: 200GB across 200 reducers
    Each reducer fetches: 200GB / 200 = 1GB from 10,000 map workers
    Each map worker sends: 200GB / 10,000 = 20MB per map worker
    
  Network bandwidth: 200GB transferred in shuffle
    At 100MB/s per reducer × 200 reducers = 20GB/s aggregate needed
    Typical datacenter bandwidth: 10GB/s core switch capacity
    → Shuffle takes ~20 seconds at full bandwidth (with combiner)
    → Without combiner: 20TB, 2000 seconds (33 minutes) for shuffle alone
  
  WITHOUT COMBINER: shuffle = 20TB in-flight, saturates network for 30+ min
  WITH COMBINER:    shuffle = 200GB in-flight, completes in <1 min
  → Combiner matters 100x for this workload
```

### The pipeline overlap

MapReduce doesn't strictly wait for all map tasks to finish before starting reducers. As soon as a map task completes, the master can notify a reducer, which immediately starts fetching that map's output. The reduce's shuffle phase can overlap with the map phase — reducers are fetching while maps are still running. This overlap reduces total job wall-clock time by typically 20-30%.

### Intern → Staff Progression (Part 4)

| Level | Understanding of the execution flow |
|-------|--------------------------------------|
| **Intern** | "Maps run first, then reduces." |
| **L3** | Knows the three phases. Cannot explain where data lives at each phase or how the master tracks task completion. |
| **L4** | Can trace the complete execution flow. Understands the master's role in coordinating task assignment and output location tracking. |
| **L5** | Understands the combiner optimization. Understands that shuffle can overlap with map. Can reason about the performance impact of skewed data (one reducer gets 10x more data than others). |
| **L6** | Can calculate job latency from first principles: input size, map task throughput, shuffle data size, reduce task throughput. Can identify the bottleneck in a given job (CPU-bound map? network-bound shuffle? I/O-bound reduce?). Can optimize job configuration (number of map/reduce tasks, use of combiners) for a given workload. |

### Data skew: the silent job killer

Data skew is the most common performance problem in production MapReduce jobs, and it's one that textbooks rarely cover well. Skew occurs when the data distribution is uneven — some keys appear vastly more often than others.

**Map-side skew:** One input split has 10x more data than others (e.g., GFS chunks that store compressed data — one 64MB compressed chunk unpacks to 640MB while others unpack to 64MB). Result: one map task takes 10x longer than others. Fix: use a splittable compression format (LZO-indexed) so the framework can split within compressed files.

**Reduce-side skew:** One key has 10x (or 1,000x) more values than others. The "hot key" problem. Example: counting clicks per URL, but the URL `google.com` appears in 10% of all records while the average URL appears in 0.001% of records. One reducer handles all `google.com` records — it takes 1,000x longer than all other reducers. Result: the entire reduce phase is dominated by the one hot-key reducer. Fix: randomize the hot key. Split `google.com` into `google.com#0` through `google.com#99` by appending a random suffix in the map function. Now 100 reducers each handle 1% of the `google.com` records. In a second MapReduce job, sum the 100 partial counts back into one `google.com` count.

**Detecting skew:** Monitor the completion time distribution across reduce tasks. If 199 reducers finish in 5 minutes and 1 reducer takes 2 hours, you have skew. The MapReduce job monitoring UI (Google's internal "Planner" tool, or Hadoop's JobTracker UI) shows per-task progress — look for one task that never advances past a certain progress point.

```
SKEW VISUALIZATION — REDUCE TASK COMPLETION TIMES

Ideal (no skew):         Actual (hot key):
  ████████████████  R1     ████████████████  R1
  ███████████████   R2     ██████████████    R2
  ████████████████  R3     ████████████████  R3
  █████████████████ R4     ████████████████████████████████  R4 ← HOT KEY
  ████████████████  R5     ████████████████  R5
  ← 1 hour →               ← 4 hours →
  
  Job completes in 1 hr    Job completes in 4 hrs (bottlenecked by R4)
  
  Fix for R4: split "hot key" → 10 sub-keys → each sub-reducer
              takes 24 min → job completes in ~90 min
```

### Common Interview Mistakes — Part 4

**Mistake 1: Not knowing about combiners.**
A combiner is a mini-reducer that runs locally on each map worker, immediately after the map phase. It reduces the amount of data that needs to be shuffled. For word count, the combiner turns 1,000 occurrences of (the, 1) from one map worker into a single (the, 1000) — 1,000x less data to shuffle. Not all reduce functions can be used as combiners (only commutative and associative ones can), but when applicable, combiners dramatically reduce shuffle cost.

**Mistake 2: Saying the shuffle phase is fast.**
The shuffle is almost always the bottleneck in a MapReduce job. All map workers are sending data to all reduce workers simultaneously — this is a many-to-many data transfer that saturates the network. At Google's scale, moving terabytes of intermediate data across thousands of machines is the dominant cost of many jobs. Minimizing shuffle data (via combiners, choosing the right key, filtering before emitting) is the primary MapReduce performance optimization.

**Mistake 3: Not knowing the number of output files.**
The final output of a MapReduce job is always exactly R files, where R is the number of reducers. Each reducer writes one output file. If you want a single output file, you use 1 reducer (bottleneck: all reduces are sequential). If you want distributed output for the next job, you use many reducers. The choice of R is a trade-off between parallelism and output file count.

---

## Part 5: Fault Tolerance

### The core principle: re-execution, not logging

MapReduce's fault tolerance model is based on a simple idea: **deterministic re-execution**. If a map or reduce task fails, just run it again on a different machine. Because map and reduce functions are deterministic (same input always produces same output) and side-effect-free (they don't modify external state), re-running a failed task produces exactly the same output as if it had succeeded the first time.

This is in contrast to database fault tolerance, which uses write-ahead logs and UNDO/REDO recovery — complex mechanisms that require carefully tracking every intermediate state change. MapReduce avoids all that complexity by ensuring tasks are stateless and deterministic.

### Worker failure

**Map worker failure:**
- The Master detects the failure via missing heartbeats (same pattern as GFS chunkserver failure detection).
- All map tasks that were running on the failed worker (state=in-progress) are reset to idle and re-assigned to other workers.
- All map tasks that were previously COMPLETED on the failed worker are ALSO reset to idle. Why? The completed map tasks wrote their output to the failed worker's local disk — that output is now inaccessible. The tasks must be re-run on a different worker.
- Reducers that have already fetched a failed map's output are not affected — they already have the data.

**Reduce worker failure:**
- The Master detects the failure via missing heartbeats.
- All reduce tasks running on the failed worker are reset to idle and re-assigned.
- Completed reduce tasks are NOT re-run — their output was written to GFS (not local disk), so it's safe even if the reduce worker is gone.

```
FAULT TOLERANCE SCENARIOS

Case 1: Map worker fails mid-task (task was in-progress)
  ─────────────────────────────────────────────────────
  Master detects: Map task 7 on Worker-12 has no heartbeat for 60s
  Master: reset Map task 7 → idle
  Master: assign Map task 7 → Worker-34
  Worker-34: re-reads input split 7 from GFS, runs map function
  Worker-34 → Master: "Map task 7 complete. New output locations: ..."
  Reducers: if they were waiting for Worker-12's output, they now
            fetch from Worker-34 instead.
  User sees: ~2 minute delay (time to re-run one map task)

Case 2: Map worker fails after task completed (output now inaccessible)
  ─────────────────────────────────────────────────────────────────────
  Master detects: Worker-12 is gone
  Master: all in-progress tasks on Worker-12 → idle (re-run)
  Master: all COMPLETED tasks on Worker-12 → idle (re-run, local disk gone)
  Reducers: told to fetch from new workers after re-run completes

Case 3: Reduce worker fails mid-task
  ────────────────────────────────────
  Master detects: Worker-89 (running Reduce task 3) is gone
  Master: reset Reduce task 3 → idle
  Master: assign Reduce task 3 → Worker-54
  Worker-54: re-fetches map output from all map workers
  Worker-54: re-runs reduce function
  Worker-54 → GFS: writes output to /output/part-r-00002
  User sees: ~5 minute delay (reduce tasks take longer than map tasks)

Case 4: Master failure
  ─────────────────────
  In the original 2004 MapReduce: the job fails. Client retries.
  The master is a single point of failure. Google accepted this because
  master failures are rare (one machine) and jobs can be re-submitted.
  Modern MapReduce-like systems use replicated coordinators.
```

### Handling stragglers: backup tasks

A classic MapReduce problem: one slow machine (straggler) causes the entire job to take 3x longer than necessary. The straggler might be slow because of a failing disk, network congestion, or simply being an older, slower machine. With 10,000 Map tasks, one slow map task holds up the entire shuffle and reduce phase.

**Backup tasks** (speculative execution) solve this: near the end of the job (when most tasks are complete), the Master schedules **backup** copies of the remaining in-progress tasks on additional workers. Whichever copy finishes first — the original or the backup — is used. The other copy is killed. The overhead is small (a few percent more total computation) and the benefit is large (stragglers no longer dictate the job's completion time).

Real numbers from the 2004 MapReduce paper: running the TeraSort benchmark (1TB sort) without backup tasks took 1,283 seconds. WITH backup tasks, 960 seconds — 25% faster. One straggler can add 33% to total job time.

### The precise fault tolerance boundary

There are two classes of faults in MapReduce, and their recovery mechanisms are different:

**Class 1: Task failure (worker crashes mid-task).** Recovery is automatic and transparent. The master re-queues the task, assigns it to a new worker, and the job continues. The user sees a delay but no error. This is the most common fault — machine failures happen daily at cluster scale.

**Class 2: Slow task (straggler).** Recovery is via speculative execution (backup tasks). Not a failure in the traditional sense, but equally damaging to job completion time. The master detects stragglers via timing heuristics and launches duplicate tasks.

**Class 3: Master failure.** Recovery requires job restart (in the original design). Rare but unrecoverable without client intervention. Modern systems add master HA (hot standby) to eliminate this class.

**Class 4: GFS failure.** In theory, GFS can lose data if all 3 replicas of a chunk are destroyed simultaneously (e.g., entire rack failure with 3 replicas co-located — which rack-aware placement is designed to prevent). If input data is lost, the MapReduce job cannot recover — the input data is gone. This is exceptionally rare (GFS's durability is the foundation) but represents the true "unrecoverable" failure class.

**Class 5: Data corruption (silent errors).** MapReduce does not validate data integrity. If a GFS chunk is silently corrupted (flipped bits from cosmic ray, disk error without ECC), the map function receives corrupted input and produces corrupted output. This can silently propagate into the final result. Production systems add checksums at the GFS chunk level (GFS already has this) AND optional application-level checksums in the map function to detect corruption early.

### Intern → Staff Progression (Part 5)

| Level | Understanding of fault tolerance |
|-------|----------------------------------|
| **Intern** | "It's fault tolerant." Cannot explain how. |
| **L3** | Knows failed tasks are re-run. Cannot explain why only map tasks that completed on failed workers need re-running (vs. reduce tasks that completed). |
| **L4** | Understands why completed map tasks must be re-run on worker failure (local disk gone) but completed reduce tasks don't (GFS). Understands speculative execution. |
| **L5** | Can trace through all four failure scenarios. Can explain why deterministic, side-effect-free functions are required for re-execution-based fault tolerance. |
| **L6** | Can explain the trade-off between re-execution-based fault tolerance (simple, requires determinism) and checkpoint-based fault tolerance (complex, doesn't require determinism). Can reason about when to use each. Can identify problems where non-determinism would break MapReduce's fault tolerance model. |

### Common Interview Mistakes — Part 5

**Mistake 1: Not distinguishing in-progress vs. completed map tasks on a failed worker.**
When a map worker fails, ALL map tasks that ran on it (whether in-progress OR completed) must be re-run. In-progress tasks are obviously incomplete. COMPLETED tasks wrote to local disk, which is now gone. This detail matters: a job that's 99% complete with one failed map worker might look like it should be nearly done, but it actually has to re-run all completed tasks from that worker — potentially setting back a large fraction of the work.

**Mistake 2: Not knowing about speculative execution.**
Speculative execution (backup tasks) is one of MapReduce's most important practical optimizations. In a large cluster, there is almost always at least one slow machine. Without speculative execution, every large job is dominated by its slowest task. With speculative execution, the framework aggressively duplicates slow tasks and uses the faster copy. Not knowing this signals you've only read the paper's abstract.

### Atomic Output Commits

One subtle but critical aspect of MapReduce's correctness is how it handles output writes — especially when backup tasks (speculative execution) mean that two copies of the same task might complete successfully.

**Map task atomic commits**

When a map task finishes, it has written its partitioned output to several temporary files on local disk — one per reducer partition. Instead of the map worker immediately registering these as "the canonical output," it sends the file paths to the master as part of its completion notification. The master records these paths only if the task is still "in-progress" (not already recorded as complete from a backup task). If a backup task completed first, the master ignores the slower task's completion message and its temp files are eventually garbage-collected. The temporary file naming includes the task ID and attempt number, ensuring files from different attempts don't collide.

**Reduce task atomic commits**

Reduce tasks write output to temporary files in GFS (named with a random suffix), then atomically rename the temp file to the final output path when the task completes. GFS supports atomic rename — a rename either succeeds completely or doesn't happen at all. If two backup reduce tasks complete simultaneously, the second rename is a no-op (the file already exists at the destination). Both produce the same output (deterministic function + same input), so either copy's output is correct. The user sees exactly one complete output file, regardless of how many copies of the task ran.

```
ATOMIC REDUCE COMMIT — HOW DUPLICATE TASK SAFETY WORKS

  Scenario: Reduce task 7 has a primary and a backup copy both finishing.

  Primary (Worker-45):                  Backup (Worker-89):
  ─────────────────────────────         ─────────────────────────────
  Compute reduce output...              Compute reduce output...
  Write to GFS temp file:               Write to GFS temp file:
    /output/tmp/r-07-pid-45-xyz           /output/tmp/r-07-pid-89-abc
  
  Both files contain IDENTICAL data     (because reduce is deterministic)
  
  Worker-45 finishes first:
  GFS atomic rename:
    /output/tmp/r-07-pid-45-xyz  →  /output/part-r-00007
  ✓ Rename succeeds. File now at canonical location.
  
  Worker-89 finishes 30 seconds later:
  GFS atomic rename:
    /output/tmp/r-07-pid-89-abc  →  /output/part-r-00007
  ✗ Rename fails (file already exists at /output/part-r-00007).
    GFS rename is atomic and returns error if destination exists.
    Worker-89 ignores the error. Its temp file is deleted by cleanup.
  
  RESULT: Exactly one copy of reduce 7's output in GFS. ✓
  No duplicate data, no partial writes, no corruption.
  
  KEY REQUIREMENT: Both copies must produce IDENTICAL output.
  This is guaranteed by determinism: same input → same output.
  If reduce function were non-deterministic, both copies might produce
  different outputs, and the "winner" would be arbitrary.
```

**Why atomicity matters beyond just correctness**

The atomic commit protocol is what makes MapReduce safe to use in pipelines. If a MapReduce job's output is fed into a downstream system (another MapReduce job, or a Bigtable loader), that downstream system can only start reading after the upstream job has completely committed all output. Because reduce output is written atomically to GFS paths, the downstream system can check "does /output/part-r-00000 through /output/part-r-00199 exist?" and if yes, all files are complete and valid — no partially-written files, no in-progress files at canonical paths. This convention — write to temp, rename when complete — is now standard practice in data pipeline design far beyond MapReduce.

### Brainstorming Questions — Part 5

**Q: What happens if two backup task copies of the same reduce task both complete at the same time? Walk through the atomic rename sequence.**

This is a classic "edge case" interview question that reveals whether you understand the atomicity guarantee. The scenario: reduce task 7 is running on Worker-45 (the original assignment) and Worker-89 (the backup, launched 2 minutes later). Both workers independently compute the same output. Worker-45 finishes at time T. Worker-89 finishes at time T+0.3 seconds (the network was slightly slower for Worker-89). Both workers, at roughly the same time, attempt to rename their temp output file to the canonical destination `/output/part-r-00007`.

GFS atomic rename has the property that only one rename can succeed when both target the same destination path. The rename is implemented at the GFS master: the GFS master serializes rename operations and the first one to arrive succeeds; subsequent renames to the same destination return an error ("file already exists") or are silently ignored. Worker-45's rename succeeds first (assuming it arrives at the GFS master first). Worker-89's rename fails. Worker-89 receives the failure, logs it, and discards its temp file. The MapReduce master sees two "task completed" messages for task 7 but records the completion only once (the first message). The second completion message is discarded.

The correctness argument rests entirely on determinism: since both copies of the reduce task ran the same deterministic function on the same input, they produced identical output. It doesn't matter which copy's output survives — they're the same. If the reduce function were non-deterministic (say, it included the current timestamp in the output), the surviving copy would be chosen arbitrarily, which might be acceptable or might cause subtle data errors depending on downstream expectations. This is the concrete reason why MapReduce's official documentation warns against non-deterministic reduce functions: they undermine the atomic commit safety guarantee.

---

### Brainstorming Questions — Part 5 (original)

**Q: MapReduce's fault tolerance relies on tasks being deterministic. What happens if a map function is non-deterministic (e.g., it generates a random sample of the input)?**

Non-determinism breaks re-execution-based fault tolerance in a subtle way. If a map task is re-run after failure, it might produce different output than the first run. Reducers that already fetched output from the first run have data that's inconsistent with the output from the second run. The final result might combine data from two different random samples — producing output that doesn't correspond to any single valid execution.

In practice, Google's MapReduce handled this by providing a weaker guarantee for non-deterministic functions: the output is guaranteed to be equivalent to SOME serial execution of the map and reduce functions. The output from any completed map task is used, even if other copies of the same task produced different outputs. For non-deterministic but "equivalent" operations (like random sampling where any sample is equally valid), this is acceptable. For operations where only one specific output is correct (like deduplication), non-determinism is genuinely dangerous and must be avoided.

The practical advice: write map and reduce functions that are deterministic whenever possible. If you need randomness, use a deterministic PRNG seeded from the input key — then the same input always produces the same output, restoring determinism.

---

## Part 6: Performance Optimizations

### Optimization 1: Data locality (reducing network reads)

The best MapReduce optimization is one that requires no code change: run map tasks on the same machine that holds the input data in GFS.

GFS stores data in 64MB chunks across many ChunkServers. MapReduce's input splits are also 64MB. If the Master assigns a map task to a worker that also runs a GFS ChunkServer holding that task's input chunk, the map task reads from local disk instead of over the network. Local disk reads are typically 10-100x faster than network reads (100MB/s local vs. 1GB/s network — but network is shared while local disk is dedicated).

The Master implements a "rack-aware scheduling" policy:
1. First, try to assign the map task to a worker on the same machine as the GFS chunk.
2. If that's not possible, try to assign to a worker on the same rack (single switch hop).
3. As a last resort, assign to any available worker.

In practice, Google found that a large fraction of map task data was read from local disk or same-rack machines, significantly reducing the load on the datacenter core network.

### Optimization 2: Combiners (mini-reducers on map machines)

For reduce functions that are commutative and associative (like SUM, COUNT, MAX, MIN), a combiner can run on each map machine immediately after mapping to pre-aggregate the output before the shuffle.

```
WITHOUT COMBINER: Map machine with "the" appearing 500 times
  Sends to reducer: (the,1),(the,1),(the,1),...  500 pairs  = 500 bytes

WITH COMBINER: Same map machine
  Combiner locally aggregates: (the, 500)
  Sends to reducer: (the,500)                               = 10 bytes

Shuffle data reduction: 50x for common words!
```

For web-scale word count, common words ("the", "a", "of") can appear millions of times per map task. Without a combiner, the shuffle moves millions of `(the, 1)` pairs. With a combiner, it moves one `(the, count)` pair per map task. The combiner can reduce shuffle data by 100-1000x for skewed word distributions.

The constraint: the combiner function must produce output that can be passed to the same reducer function. `SUM` works: `reduce(sum(partial_sums)) == sum(all_values)`. `AVERAGE` doesn't work: `average(partial_averages) != average(all_values)`. For average, you'd need to emit (sum, count) and compute average in the reducer.

### Optimization 3: Backup tasks (speculative execution)

Covered in Part 5. Near the end of the job, the Master duplicates slow tasks to eliminate straggler effects.

**The straggler detection algorithm in detail**

The master does not immediately launch a backup task the moment a task runs long. The algorithm has two phases: (1) wait until the vast majority of tasks have completed (the original MapReduce paper uses 95% completion as the threshold), then (2) for any still-in-progress tasks, launch a backup copy if the task has been running for more than the median task time × some multiplier (typically 2x the median). This two-phase approach avoids spamming the cluster with backup tasks for tasks that are simply running in the normal distribution of task durations. Launching backup tasks for all tasks from the moment the first task completes would double the cluster's resource usage.

**Interaction with data locality**

Backup tasks by definition run on machines other than the one originally assigned to the task (since the original machine is already running it, presumably slowly). This means backup tasks almost always read input from GFS over the network (no data locality). The trade-off is explicit and intentional: accept a network-bound read (slower input, but normal compute speed) to avoid being bottlenecked by the original machine's slow disk or CPU. In practice, a network-bound map task reading 64MB takes ~3 seconds (at ~20MB/s network) vs. a straggler map task that might take 30+ minutes. The backup task's network cost is trivially small compared to the time saved.

### Optimization 4: Input compression

Large input files can be stored in compressed format (gzip, LZO, Snappy) in GFS. Map tasks decompress on-the-fly while reading. For text data that compresses at 5-10x, this means:
- 5-10x less network traffic reading input from GFS
- 5-10x less GFS storage for input data
- Cost: CPU for decompression (usually cheap)

For intermediate data (map output), LZO (fast compression) is often used to compress the shuffle data — faster to compress and transmit than to send uncompressed over the network.

### Optimization 5: Custom partitioners

The default partition function is `hash(key) % num_reducers`. This distributes keys uniformly across reducers — good for most cases. But sometimes you want control over which reducer handles which keys.

Example: for a web crawl job, you might want all URLs from the same domain to go to the same reducer (so the reducer can compute per-domain statistics). The default hash might spread `com.google.*` URLs across all reducers. A custom partitioner can ensure all `com.google.*` URLs go to reducer 3, all `com.facebook.*` URLs go to reducer 7, etc.

**Range partitioning for sorted output**

The default hash partitioner produces output that is sorted within each reducer's file but not sorted globally across all output files. For jobs that need globally sorted output (like TeraSort), you need a range partitioner: pre-sample the key space to find percentile boundaries, then assign keys to reducers based on which range they fall in.

```
RANGE PARTITIONING SETUP (TeraSort approach)

Step 1: Sample 0.1% of records from input to estimate key distribution
  Run a small MapReduce job (sampling job) to collect ~10,000 sample keys

Step 2: Sort sample keys and find reducer boundaries
  With 1,000 reducers:
    reducer 0:   keys in range [key_at_0th_percentile, key_at_0.1th_percentile)
    reducer 1:   keys in range [key_at_0.1th_percentile, key_at_0.2th_percentile)
    ...
    reducer 999: keys in range [key_at_99.9th_percentile, max_key]
  
  Save boundaries to a file distributed to all map workers.

Step 3: Main sort job uses range partitioner
  Each map worker loads the boundaries file.
  Custom partitioner: binary search to find which reducer the key belongs to.
  
  Result: output files are globally sorted.
    /output/part-r-00000: all keys from 0th to 0.1th percentile
    /output/part-r-00001: all keys from 0.1th to 0.2th percentile
    ...
    Concatenating all files in order produces a globally sorted file.
```

### Optimization 6: Output compression

Map output can be compressed before writing to local disk using fast codecs (LZO, Snappy). This reduces:
- Local disk I/O during map output write (write 400MB instead of 1GB)
- Shuffle network transfer (send 400MB instead of 1GB)
- Reducer's disk read during fetch (read 400MB instead of 1GB)

The cost: CPU for compression and decompression. For text data (compresses 5-10x with LZO) on a CPU-idle map phase, this is a clear win. For binary data (compresses 1.1-1.5x) or a CPU-saturated map phase, the benefit may not justify the CPU cost. Snappy is the typical choice when CPU budget is tight: it compresses 2-3x with very fast decompression (500MB/s vs. LZO's 350MB/s and gzip's 100MB/s).

### Intern → Staff Progression (Part 6)

| Level | Understanding of optimizations |
|-------|-------------------------------|
| **Intern** | "It's optimized." No knowledge of specific techniques. |
| **L3** | Knows about combiners. Cannot explain when they're applicable or why. |
| **L4** | Can apply combiners correctly (knows the commutative/associative requirement). Knows about data locality. |
| **L5** | Can reason about the shuffle as the bottleneck and apply multiple optimizations (combiner + compression + custom partitioner) to minimize it. Can estimate the performance impact of each. |
| **L6** | Can design a complete optimization strategy for a given MapReduce job: what combiners to use, what compression format, how many reducers, what partitioning strategy, when to use speculative execution aggressively. Can reason about the interactions between optimizations. |

### Performance Numbers from the 2004 Paper

Google published actual benchmark data in the original MapReduce paper. These are real numbers, not estimates. Knowing them demonstrates you've read the primary source — a signal that sets L6 candidates apart.

**Benchmark 1: Grep (100GB input)**

```
┌────────────────────────────────────────────────────────────────────┐
│  GREP BENCHMARK — Find rare 3-character pattern in 100GB of data   │
│  Hardware: 1,800 machines, 2GHz Intel Xeon, 4GB RAM, 100Mbps NIC  │
│                                                                    │
│  Phase          Duration   Notes                                   │
│  ─────────────  ─────────  ───────────────────────────────────────  │
│  Startup/init   60s        Binary distribution, GFS prefetch       │
│  Map phase      91s        1800 workers, each reading ~57MB input  │
│  Shuffle        27s        Tiny: grep emits very few matches        │
│  Reduce phase   35s        1 reducer aggregating all matches        │
│  Total          ~213s      (with overhead)                         │
│                                                                    │
│  Input throughput:  100GB / 91s = ~1.1 GB/s aggregate             │
│  Per-machine:       1.1 GB/s / 1800 = ~630 KB/s per machine       │
│  (Local disk reads dominate — data locality in effect)             │
│                                                                    │
│  Why shuffle is only 27s: grep is "filter heavy" — most input      │
│  records produce zero output. Intermediate data << input data.     │
└────────────────────────────────────────────────────────────────────┘
```

**Benchmark 2: Sort (1TB input — the TeraSort benchmark)**

```
┌────────────────────────────────────────────────────────────────────┐
│  SORT BENCHMARK — Sort 1TB of 100-byte records                     │
│  (Industry standard: TeraSort, won the 2004 Sort Benchmark)        │
│  Hardware: 1,800 machines (same cluster as above)                  │
│                                                                    │
│  Phase          Duration   Notes                                   │
│  ─────────────  ─────────  ───────────────────────────────────────  │
│  Startup/init   ~30s       Binary + metadata setup                 │
│  Map phase      200s       Parse records, emit (sort_key, record)   │
│  Shuffle        600s       1TB moves from 1800 map workers to       │
│                            1800 reduce workers (all-to-all)        │
│  Reduce phase   91s        Merge-sort within each reducer           │
│  Total          891s       (14.8 minutes for 1 terabyte)           │
│                                                                    │
│  Aggregate shuffle throughput: 1TB / 600s = 1.67 GB/s             │
│  Per-machine:  1.67 GB/s / 1800 = ~950 KB/s per machine outbound  │
│                                                                    │
│  Note: Sort has NO intermediate data reduction possible —          │
│  every input record must reach a reducer. Shuffle = 100% of data.  │
│  This is the WORST CASE for shuffle. Most real jobs do much better. │
│                                                                    │
│  WITHOUT backup tasks: 1283s (43 minutes)                          │
│  WITH backup tasks:     891s (14.8 minutes) = 30% improvement      │
│  One straggler = 43% slower without backup tasks.                   │
└────────────────────────────────────────────────────────────────────┘
```

**Benchmark 3: Web index construction (10TB)**

The web index pipeline is a chain of 5 MapReduce jobs:
```
Job 1: Parse raw HTML → extract (word, url) pairs
       Input: 10TB HTML, Output: ~50TB intermediate (many words per page)
       Map tasks: 10,000; Reduce tasks: 1,000; Runtime: ~3 hours

Job 2: Compute word frequency per URL
       Input: 50TB pairs, Output: ~20TB (compressed word freq data)
       Runtime: ~2 hours

Job 3: Build raw inverted index (word → list of (url, freq) pairs)
       Input: 20TB, Output: ~15TB raw index
       Runtime: ~4 hours

Job 4: Join with PageRank scores, sort each word's URL list by score
       Input: 15TB raw index + 5TB PageRank, Output: ~10TB scored index
       Runtime: ~3 hours

Job 5: Load scored index into Bigtable for serving
       Input: 10TB, Output: Bigtable writes
       Runtime: ~2 hours

Total pipeline: ~14 hours, processes 10TB of raw HTML
Resulting index: ~10TB served from Bigtable for search queries
```

**Brainstorming Q: Given the TeraSort numbers, what is the effective network bandwidth used during the shuffle? Walk through the math.**

The TeraSort benchmark sorts 1TB in 891 seconds on 1,800 machines, with 600 seconds spent in the shuffle phase. The shuffle moves essentially the entire 1TB of data — every input record must be shipped to a reducer. So: 1TB = 1,000 GB transferred in 600 seconds. That's 1,000 GB / 600 s ≈ 1.67 GB/s aggregate network throughput across the entire cluster.

Each machine participates as both a sender (map output, shipping to reducers) and a receiver (reducer fetching map output). With 1,800 machines: sender side = 1.67 GB/s / 1,800 machines ≈ 0.93 MB/s per machine outbound. This seems surprisingly low — the machines have 100 Mbps (12.5 MB/s) NICs. Why only 0.93 MB/s per machine? The core network was the bottleneck, not the NICs. With 1,800 machines each sending to 1,800 destinations simultaneously, the traffic pattern is an all-to-all broadcast. The core switch capacity — say 200 GB/s for a 2004-era cluster — limits the aggregate throughput. Additionally, network scheduling (TCP connection setup, congestion control, retransmission) adds overhead. A useful rule of thumb from this data: MapReduce shuffle utilizes roughly 7-10% of NIC bandwidth at the per-machine level, with the core network being the real bottleneck. Modern jobs (using 10GbE or 25GbE NICs with smarter scheduling) can hit 40-60% NIC utilization during shuffle.

### Real Incident (Part 6): The Shuffle Bottleneck at Yahoo

When Yahoo! adopted Hadoop MapReduce to process their search log data (tens of terabytes per day), the initial jobs were dramatically slower than expected. The root cause: no combiners were used, and the shuffle was overwhelming the network. A job that processed 10TB of logs was generating 8TB of intermediate data — nearly all of it duplicate (word, 1) pairs for common log tokens.

After adding combiners (which pre-aggregated per-map-machine before shuffle), intermediate data dropped to 400GB — a 20x reduction. Job time dropped from 8 hours to 23 minutes. This incident became a case study in MapReduce performance: the combiner is not an optional optimization — for aggregation workloads, it's often the difference between a job that finishes and one that doesn't. Yahoo's experience also drove improvements in Hadoop's combiner API, making it easier to plug in and monitor.

---

## Part 7: Real-World Applications

### Application 1: Inverted index (the web search index)

The core of Google's web search index is an inverted index: for every word on the web, a list of URLs that contain that word.

```
INVERTED INDEX CONSTRUCTION IN MAPREDUCE

Input: GFS files with (URL, page_content) pairs

MAP:
  for word in tokenize(page_content):
      emit(word, url)

SHUFFLE: groups all (word, url) pairs by word

REDUCE:
  for (word, list_of_urls):
      sorted_urls = sort(list_of_urls, by=pagerank)
      emit(word, sorted_urls[:top_1000])  # keep top 1000 results per word

Output: For each word → list of top 1000 URLs, sorted by relevance
Stored in Bigtable for serving Google Search queries.
```

This is a two-step pipeline: the MapReduce job builds the index, then the index is served from Bigtable. The MapReduce runs nightly to incorporate newly crawled pages.

### Application 2: PageRank computation

PageRank is computed iteratively. Each iteration is one MapReduce job:

```
PAGERANK ITERATION IN MAPREDUCE

Input: (url, current_pagerank, list_of_outlinks)

MAP:
  for link in outlinks:
      emit(link, current_pagerank / len(outlinks))  # distribute rank
  emit(url, "STRUCTURE:" + outlinks)  # preserve the graph structure

REDUCE:
  for (url, values):
      new_rank = 0
      for value in values:
          if value starts with "STRUCTURE:":
              outlinks = parse(value)  # preserve for next iteration
          else:
              new_rank += value  # accumulate incoming rank
      emit(url, new_rank, outlinks)

Run this job 20-30 times until PageRank converges.
```

The limitation: each iteration writes all data back to GFS, then the next iteration reads it again. For the web graph (50+ billion URLs), this is terabytes of I/O per iteration. PageRank with MapReduce took days. Spark later reduced this to hours by keeping the graph in memory.

### Application 2b: Duplicate Detection at Web Scale

Google's web crawler frequently encounters the same page at multiple URLs (mirrors, syndicated content, A/B test variants). Indexing duplicates wastes storage and dilutes PageRank signals. MapReduce is used to detect near-duplicate pages across the entire crawled web.

```
NEAR-DUPLICATE DETECTION IN MAPREDUCE

Input: (url, page_content) pairs — full web crawl

Step 1: Compute SimHash fingerprint per page
  MAP:
    simhash = compute_simhash(page_content)  # 64-bit fingerprint
    # SimHash: similar pages have similar fingerprints (small Hamming distance)
    # Group pages by fingerprint prefix to find candidates
    for bit_prefix in sample_bit_prefixes(simhash, k=4):
        emit(bit_prefix, (simhash, url))

  REDUCE for bit_prefix:
    # All pages with the same bit prefix land here
    pages = sort_by_simhash(values)
    # Adjacent pages in sorted order have high SimHash similarity
    for i in range(len(pages) - 1):
        if hamming_distance(pages[i].simhash, pages[i+1].simhash) <= 3:
            emit("DUPLICATE", (pages[i].url, pages[i+1].url))

Step 2: Build canonical URL clusters
  (Use the output of Step 1 as a graph and apply connected-components
   algorithm via another MapReduce job — e.g., star-expansion algorithm)

Output: For each cluster of duplicate pages, one canonical URL.
The inverted index then indexes only the canonical URL.
```

This is a three-job pipeline: (1) compute SimHash per page, (2) find near-duplicate pairs using band-based locality-sensitive hashing, (3) union-find to cluster duplicates. At web scale, this pipeline runs nightly on hundreds of billions of pages. The key insight: you can't compare every pair of pages (O(n²) pairs), so you use locality-sensitive hashing to group candidate duplicates first, then only compare within candidate groups.

### Application 3: Log analysis

Google's production systems generate enormous log files. MapReduce jobs process logs to compute:
- Error rate per service per hour
- Latency percentiles (p50, p95, p99) per endpoint
- User session funnel analysis (how many users complete each step)

```
LATENCY PERCENTILE IN MAPREDUCE

Input: (timestamp, endpoint, latency_ms) from log files

MAP:
  emit((endpoint, hour_bucket), latency_ms)

REDUCE:
  for (endpoint_hour, latencies):
      sorted_latencies = sort(latencies)
      p50 = percentile(sorted_latencies, 50)
      p95 = percentile(sorted_latencies, 95)
      p99 = percentile(sorted_latencies, 99)
      emit(endpoint_hour, p50, p95, p99)
```

The challenge: for high-traffic endpoints, one reducer might receive millions of latency values. Sorting millions of values in a single reducer is memory-intensive. The optimization: use approximate percentile algorithms (like reservoir sampling or t-digest) in the combiner to pre-aggregate before the shuffle.

### The GFS + Bigtable + MapReduce pipeline

These three systems form Google's data processing stack:

```
┌─────────────────────────────────────────────────────────────────────┐
│              THE GOOGLE DATA STACK (2004–2012)                      │
│                                                                     │
│  Raw data (web crawl, logs, user events)                           │
│           │                                                         │
│           ▼                                                         │
│        GFS (raw storage: HTML pages, logs, images)                  │
│           │                                                         │
│           │  MapReduce reads from GFS                              │
│           ▼                                                         │
│     MapReduce (batch processing: parse, transform, aggregate)       │
│           │                                                         │
│           │  MapReduce writes to GFS (intermediate) or Bigtable    │
│           ▼                                                         │
│     Bigtable (structured storage: web index, user data, metrics)    │
│           │                                                         │
│           │  Online applications read from Bigtable                │
│           ▼                                                         │
│     Google Search / Gmail / Analytics / Ads (user-facing)           │
└─────────────────────────────────────────────────────────────────────┘
```

Understanding this stack end-to-end — not just individual components — is what separates an L5 answer from an L6 answer in a Google system design interview.

### Application 4: A/B Test Analysis at Scale

A/B testing infrastructure at Google required processing hundreds of millions of user events per day to compute statistical significance across thousands of simultaneous experiments. Each user might be in hundreds of experiments simultaneously (different features, different UI variants, different ranking algorithms).

```
A/B TEST ANALYSIS IN MAPREDUCE

Input: (user_id, experiment_id, variant, metric_value, timestamp)
Goal: For each experiment, compute per-variant statistics (mean, variance,
      sample size) for significance testing.

MAP:
  emit((experiment_id, variant), metric_value)
  # Natural grouping: all metrics for one experiment+variant in one reducer

COMBINER (statistics are partially combinable):
  # Can pre-aggregate count, sum, and sum-of-squares locally
  # These three values are sufficient to reconstruct mean and variance:
  #   mean = sum / count
  #   variance = (sum_of_squares / count) - mean²
  local_count = count(values)
  local_sum = sum(values)
  local_sum_sq = sum(v*v for v in values)
  emit((experiment_id, variant), (local_count, local_sum, local_sum_sq))

REDUCE:
  total_count = sum(c for c, s, ss in values)
  total_sum = sum(s for c, s, ss in values)
  total_sum_sq = sum(ss for c, s, ss in values)
  mean = total_sum / total_count
  variance = (total_sum_sq / total_count) - mean**2
  stderr = sqrt(variance / total_count)
  emit((experiment_id, variant), (total_count, mean, variance, stderr))

OUTPUT: Each row is one (experiment, variant) pair with sufficient statistics
        for a t-test to compute statistical significance against the control.
        One MapReduce job per day. Results used to make launch decisions.

SCALE: 10,000 experiments × 2-5 variants × ~1M users per experiment
       = up to 50 billion emit pairs per day (with combiner: ~1B pairs)
```

The A/B test analysis job was one of Google's most critical daily MapReduce jobs — it drove product launch decisions for Search, Ads, Gmail, and YouTube. The key design insight: always emit sufficient statistics (count, sum, sum-of-squares) rather than final statistics (mean, variance), because sufficient statistics are combinable and final statistics are not.

---

### Monitoring and Observability

Production MapReduce jobs need monitoring beyond "did it finish?" Key signals to track:

```
MAPREDUCE MONITORING CHECKLIST

Job-level metrics:
  ✓ Total wall-clock time (track over time — increasing duration = data growth)
  ✓ Input records processed vs. expected (catch missing data partitions)
  ✓ Output records written vs. expected (catch silent data loss)
  ✓ Shuffle bytes transferred (detect combiner regression)
  ✓ Number of task failures (baseline vs. spike = hardware issues)
  ✓ Number of speculative executions (high rate = cluster health problem)

Per-phase metrics:
  ✓ Map phase: records/sec, bytes/sec input, task duration distribution
  ✓ Shuffle phase: bytes transferred, fetch failures, retry count
  ✓ Reduce phase: input groups processed, output records, task duration distribution

Alerting thresholds (tune to job-specific baselines):
  ✗ Job duration > 2× historical median → SLA alert
  ✗ Input records processed < 95% of expected → data completeness alert
  ✗ Any task attempts > 10 (10 retries for one task → sick machine) → ops alert
  ✗ Shuffle bytes > 200% of recent average → combiner regression alert
```

---

## Part 8: Limitations and What Came After

### MapReduce's fundamental limitations

```
┌─────────────────────────────────────────────────────────────────────┐
│              MAPREDUCE LIMITATIONS                                  │
│                                                                     │
│  1. NO ITERATION                                                    │
│     Each job is one pass. Iterative algorithms (ML training,        │
│     PageRank, graph clustering) need many chained jobs.            │
│     Each job writes/reads from GFS = slow.                         │
│                                                                     │
│  2. NO STREAMING                                                    │
│     Jobs take minutes to hours. No sub-second processing.          │
│     Cannot process events in real-time as they arrive.             │
│                                                                     │
│  3. SHUFFLE IS SLOW                                                 │
│     All-to-all data transfer is the bottleneck.                    │
│     Unavoidable in the current architecture.                        │
│                                                                     │
│  4. DISK I/O BETWEEN STAGES                                         │
│     Every job reads from disk and writes to disk.                  │
│     No concept of keeping intermediate data in memory.             │
│                                                                     │
│  5. TWO-STAGE ONLY (map then reduce)                               │
│     Complex pipelines require chaining many jobs.                  │
│     No native support for multiple join stages in one job.         │
│                                                                     │
│  6. LOW-LEVEL API                                                   │
│     Must write map and reduce functions explicitly.                │
│     SQL-like queries require many map/reduce functions.             │
└─────────────────────────────────────────────────────────────────────┘
```

### What came after — the family tree

**Apache Hadoop (2006):** Open-source implementation of MapReduce + GFS (as HDFS). Drove the big data industry. Pig (scripting language on Hadoop) and Hive (SQL on Hadoop) made Hadoop accessible to data analysts who couldn't write Java MapReduce jobs.

**Apache Spark (2010, AMPLab Berkeley):** In-memory batch processing. Key innovation: Resilient Distributed Datasets (RDDs) — distributed collections that stay in memory across multiple operations. Spark iterates over data 10-100x faster than Hadoop for ML and graph workloads because it avoids disk I/O between iterations. Also supports SQL (SparkSQL), streaming (Spark Streaming), and ML (MLlib). Largely replaced Hadoop MapReduce for new workloads.

**Google Dataflow (2014) / Apache Beam (2016):** Google's unified batch + streaming model. A single API describes a data pipeline that can run in batch mode (over historical data) or streaming mode (over live data). Beam abstracts away the execution engine — the same pipeline code runs on Dataflow, Spark, or Flink.

**Apache Flink (2014):** Native streaming first, batch as a special case. Low latency (milliseconds to seconds), stateful streaming, exactly-once semantics. The go-to for real-time stream processing at scale.

```
┌─────────────────────────────────────────────────────────────────────┐
│              BATCH/STREAM PROCESSING FAMILY TREE                    │
│                                                                     │
│  MapReduce (2004, Google) ─────────────────────────────────────────┐│
│       │                                                             ││
│       ├── Hadoop (2006, Apache)                                     ││
│       │      ├── Pig (scripting)                                    ││
│       │      ├── Hive (SQL)                                         ││
│       │      └── YARN (cluster manager, successor to MR master)     ││
│       │                                                             ││
│       ├── Spark (2010, AMPLab) → in-memory, RDDs                   ││
│       │      ├── SparkSQL                                           ││
│       │      ├── Spark Streaming                                    ││
│       │      └── MLlib                                              ││
│       │                                                             ││
│       └── Dataflow/Beam (2014, Google)                              ││
│              └── Apache Beam (2016, open source)                    ││
│                                                                     ││
│  Separate streaming lineage:                                        ││
│  Storm (2011) → Flink (2014) → Kafka Streams (2016)               ││
└─────────────────────────────────────────────────────────────────────┘
```

### Common Interview Mistakes — Part 8

**Mistake 1: Saying "just use Spark" without understanding when MapReduce is still correct.**
For single-pass ETL jobs (read from HDFS, transform, write to HDFS), Spark's in-memory advantage disappears if the data doesn't fit in RAM. If you're transforming 500TB of data with a simple format conversion, Spark and Hadoop MapReduce have nearly identical throughput — both are I/O bound. In this scenario, MapReduce's simpler operational model (no memory tuning, no GC issues) makes it preferable.

**Mistake 2: Confusing Spark Streaming with true streaming.**
Spark Streaming (older) and Spark Structured Streaming use micro-batching: they collect events for a configurable time window (typically 0.5-10 seconds), then process each micro-batch as a small Spark job. This gives latency of seconds, not milliseconds. True streaming (Flink, Kafka Streams) processes each event individually as it arrives, giving millisecond latency. Saying "use Spark Streaming" when the requirement is sub-second latency is incorrect. This distinction matters in fraud detection, where 500ms is the difference between blocking a transaction and letting it through.

**Mistake 3: Not knowing that Apache Beam is the abstraction, not an execution engine.**
Beam is a programming model and API. It does not execute jobs itself. A Beam pipeline must run on a runner: Apache Flink, Apache Spark, or Google Dataflow (managed cloud service). Saying "we'll use Apache Beam" in an interview answer must be followed by "running on the Dataflow runner" or "running on our existing Flink cluster." Beam without a specified runner is like "we'll use SQL" without specifying the database.

### When MapReduce (or Hadoop) is still the right choice

Despite Spark's advantages, MapReduce/Hadoop remains appropriate when:
- The data fits on disk but NOT in memory (Spark's in-memory advantage disappears if you have to spill to disk anyway)
- The workload is a single-pass transformation (no iteration, no complex state) — MapReduce is simpler to operate
- The team has strong Hadoop operational expertise and migration cost is high
- The job reads from HDFS and writes to HDFS (no network overhead for GFS-native jobs)

### Intern → Staff Progression (Part 8)

| Level | Knowledge of the MapReduce ecosystem |
|-------|--------------------------------------|
| **Intern** | "MapReduce = Hadoop." Cannot explain why Spark was built. |
| **L3** | Knows Spark is faster than Hadoop. Cannot explain why. |
| **L4** | Understands the key difference: Spark keeps data in memory across iterations, MapReduce writes to disk. |
| **L5** | Can explain when MapReduce is appropriate vs. Spark vs. Flink. Knows the full ecosystem (Pig, Hive, Beam). |
| **L6** | Can design a complete data processing architecture: what uses MapReduce/Spark for batch, what uses Flink for streaming, how Bigtable/GFS fits in as the storage layer. Can calculate when in-memory processing is worthwhile vs. when disk is unavoidable. Can reason about the operational complexity trade-offs between Hadoop and Spark. |

---

## Part 9: Interview Application

### The complete mental model for interviews

MapReduce is best understood through three lenses, each relevant to a different type of interview question:

**Lens 1: The programmer model** (for "how does MapReduce work" questions). Two functions: `map(k,v) → [(k2,v2)]` and `reduce(k2,[v2]) → v3`. The framework handles distribution, shuffling, sorting, fault recovery. The programmer writes pure logic; the framework handles pure infrastructure.

**Lens 2: The execution model** (for "design a batch pipeline" questions). Input from GFS → parallel map tasks (local disk output) → shuffle (sort + network transfer) → parallel reduce tasks (GFS output). Each phase is a potential bottleneck: CPU-bound maps → profile and optimize map logic. Shuffle-bound → use combiners, compression, fewer emitted pairs. Reduce-bound → increase reducer count or use more efficient aggregation.

**Lens 3: The failure model** (for "how does fault tolerance work" questions). Deterministic + stateless tasks = safe to re-execute on failure. Backup tasks = safe to run duplicates because only one output is committed (atomic rename). Master = single point of failure, accepted because master failures are rare and job restart is simple.

### The one-sentence summary

> "MapReduce hides distributed complexity behind two functions: map transforms individual records, reduce aggregates across records. The framework handles distribution, fault tolerance, and data movement. Know when to use it vs. Spark vs. streaming."

### When to reference MapReduce in an interview

**You're designing a batch data pipeline.** When asked "how do you process 1PB of log data per day to compute analytics," reference MapReduce (or Spark, with an explanation of the difference): "This is a batch processing problem — the classic pattern is map (parse each log line, emit (key, value) pairs) then reduce (aggregate by key). At Google, this is MapReduce; in open-source, Spark. I'd choose Spark here because..."

**You're explaining the GFS/Bigtable ecosystem.** MapReduce is the processing glue between GFS and Bigtable. GFS stores raw data → MapReduce processes it → Bigtable stores the structured result → online applications serve from Bigtable. Knowing this pipeline shows systems-level thinking.

**You're asked about distributed fault tolerance.** MapReduce's re-execution model is a clean example of fault tolerance through stateless, deterministic tasks. Reference it when discussing: "why don't you need distributed transactions for batch processing" (because you can re-run failed tasks) and "how do you handle stragglers" (speculative execution).

**You're asked about trade-offs of different processing models.** MapReduce (batch, disk-based, high latency) vs. Spark (batch/iterative, memory-based, lower latency) vs. Flink (streaming, sub-second latency, stateful). Knowing the right model for a given problem is L5/L6 thinking.

### How to frame MapReduce answers at L6

An L6 system design answer about MapReduce has five components: (1) identify that the problem is batch-shaped (not streaming, not iterative), (2) specify the map function with exact key-value types, (3) specify whether a combiner applies and why (cite commutativity/associativity), (4) specify the reduce function and its output format, (5) estimate the data volumes at each stage and identify the bottleneck. An answer that misses any of these five is L5 or below.

Example of the progression for "compute daily click counts per product from 1TB of logs":

**L4:** "Map emits (product_id, 1). Reduce sums them. Use a combiner for efficiency."

**L5:** "Map: parse each log line, if action=click emit (product_id, 1). Combiner: sum counts per product per map machine (SUM is commutative+associative). Reduce: sum all counts across all map machines. Output: (product_id, daily_click_count). The combiner reduces shuffle from 1TB (one pair per log line) to roughly 1GB (one pair per product per map machine). Shuffle is the bottleneck without the combiner."

**L6:** "Map: parse log line, validate timestamp is within target day (filter), emit (product_id, 1). Combiner: partial sum, emit (product_id, local_count). With 1,000 map tasks and 10,000 products, combiner produces at most 10,000,000 pairs vs. 10 billion raw pairs — 1,000x shuffle reduction. Reduce: global sum, emit (product_id, global_daily_count). Output: 10,000 rows written to GFS as Parquet for the downstream analytics dashboard. Number of reducers: 100 — at 10,000 products / 100 reducers = 100 products per reducer, each holding ~100 counts in memory, trivial. Total job time estimate: map phase 5 min (1TB / 1000 workers at ~200MB/s local), shuffle 30s (1GB at 30MB/s), reduce 1 min. Bottleneck: map phase (CPU parsing). If faster needed, pre-parse logs at ingestion time and write structured Parquet to GFS — reduces map CPU by 10x."

### L5 vs L6 calibration

**L5 says:** "For batch processing of large datasets, I'd use Hadoop MapReduce or Spark. Map the data to key-value pairs, reduce to aggregate. Fault tolerant because failed tasks are re-executed."

**L6 says:** "This is batch analytics over 1PB/day of logs — MapReduce-shaped but with a few nuances. I'd use Spark over Hadoop because the analytics pipeline likely has iterative steps (daily aggregations feed into weekly/monthly rollups) and Spark avoids re-reading from disk between steps. The map phase: parse log lines, emit (endpoint, hour_bucket, latency). The combiner: approximate percentile using t-digest to reduce shuffle data by 100x (percentiles can't be computed exactly with combiners, but t-digest gives 99th percentile within 1% error). The reduce phase: merge t-digests, extract percentiles. Output written to Bigtable keyed by (endpoint, hour_bucket) for online dashboards. The main operational risk is shuffle bottleneck if the combiner doesn't pre-aggregate enough — I'd add Bloom-filter-based deduplication in the map phase to drop known-duplicate log lines before emitting."

### The full 8-minute MapReduce answer template

In a Staff-level system design interview, when MapReduce is the right tool, structure your answer in four parts (approximately 2 minutes each):

**Part A: Problem framing (30 seconds)**
"This is a batch processing problem — we need to process [X TB] of [data type] to produce [output]. The data is already in GFS/HDFS. MapReduce (or Spark) is the right abstraction. I'll use Spark here because [single-pass ETL → either works; iterative → Spark; very large and disk-only → MapReduce]."

**Part B: Map function specification (90 seconds)**
"The map function: input is a [format] record with [fields]. For each record, I emit [(key_type, value_type)] because [reason the grouping is correct]. The key choice is important: [explain why this key ensures the right records land on the same reducer]. I'll add a combiner that [operation, if applicable] to reduce shuffle data by approximately [X]x."

**Part C: Reduce function specification (90 seconds)**
"The reduce function receives all [value_type] values for a given [key_type]. It [aggregation logic]. The output is [(key, value)] written to GFS as [format: Parquet, sequence file, plain text]. I'll use [R] reducers: with [estimated total shuffle data], each reducer handles approximately [per-reducer data], which [fits/doesn't fit] in memory."

**Part D: Performance and edge cases (2 minutes)**
"Estimated timeline: map phase [X minutes], shuffle [Y minutes], reduce [Z minutes]. Bottleneck: [map/shuffle/reduce] because [reason]. Main edge case: data skew — [top key] may account for [X]% of records. I'll handle this by [random suffix + second job / using a custom partitioner / increasing reducer count]. For fault tolerance: speculative execution is enabled by default; on a 2,000-machine cluster, I'd expect [N] task failures during this job, all automatically recovered."

### Common interview mistakes — Part 9

**Mistake 1: Using MapReduce where streaming is needed.**
"Design a real-time fraud detection system" is NOT a MapReduce problem. MapReduce processes historical data in batch. Fraud detection needs to evaluate each transaction in milliseconds as it happens — use Flink or Kafka Streams, not MapReduce. Proposing MapReduce for real-time use cases signals a fundamental misunderstanding of the tool.

**Mistake 2: Not explaining what map and reduce functions do.**
"I'd use Spark MapReduce" without explaining the map/reduce functions is meaningless. An L6 answer specifies exactly what the map function emits and what the reduce function aggregates. This concreteness shows you actually know how to use the tool, not just that it exists.

**Mistake 3: Forgetting about the shuffle bottleneck.**
Any MapReduce design must include an analysis of intermediate data size. If your map emits raw values for every input record and your reduce aggregates them, the shuffle is probably your bottleneck. L6 answers always include "and we reduce shuffle data by using a combiner / by pre-filtering in the map / by choosing the aggregation key carefully."

---

## Real Life Product Incidents

### Incident 1: The Straggler That Delayed Google's Daily Index (2005)

Google's nightly indexing pipeline used a chain of MapReduce jobs to process the daily web crawl and update the search index. One night, a single map task in the inverted index construction job ran on a machine with a failing disk — reads took 50x longer than normal. This one straggler caused the entire 10-hour job to take 24 hours because the shuffle couldn't start until all map tasks completed.

The incident directly motivated the speculative execution (backup tasks) feature in MapReduce. Engineers noticed from the job monitoring dashboard that 9,999 map tasks had completed in 8 hours and one map task had been running for 16 hours. The fix: 30 minutes after the normal job completion time, automatically launch backup copies of any in-progress tasks. The backup task ran on a healthy machine and finished in 20 minutes. Total extra cost: one additional map task execution. Total time saved: ~8 hours. After this incident, backup tasks were enabled by default in all Google MapReduce jobs.

### Incident 2: The Shuffle That Brought Down the Network (2006)

A MapReduce job at Google ran a join between two datasets: web page content (10TB) and the link graph (2TB). The job had 2,000 map tasks and 200 reduce tasks. During the shuffle phase, all 2,000 map workers simultaneously started sending data to all 200 reduce workers — a 2,000 × 200 = 400,000 concurrent connections, each transferring data at full speed.

The combined network traffic (2000 × 100MB/s) saturated the datacenter's top-of-rack switches. Other jobs running in the same datacenter — including user-facing serving jobs — experienced severe network degradation. The search serving latency spiked from 50ms to 2 seconds for 15 minutes until the MapReduce job's shuffle phase completed.

The fix was multi-part: (1) add network rate limiting for MapReduce shuffle traffic; (2) add scheduler-level isolation between batch and serving jobs (different physical networks); (3) run large MapReduce jobs in dedicated batch clusters separate from serving infrastructure. This incident shaped Google's cluster architecture: batch processing and serving have separate physical infrastructure, connected by rate-limited links. The lesson: network saturation from batch jobs is a production incident, not just a performance issue.

### Incident 3: The Non-Deterministic Map Function (2007)

A Google team wrote a MapReduce job that sampled web pages for a quality evaluation study. The map function used Python's `random.random()` to decide whether to include each page in the sample. The job ran correctly the first time and produced a 5% sample of the web.

When one map worker failed mid-job, its task was re-run on a different machine. But the re-run used a different random seed (seeded from the system clock), producing a different sample. Some pages that WERE in the first run's sample were NOT in the re-run's sample, and vice versa. The final "sample" was actually a mix of two different samples — with some pages appearing twice (from a reducer that fetched both the original and the re-run output).

The team discovered the problem when the sample's statistics didn't match expected baselines (sampling rate was 6.3% instead of 5%, with visible duplicates). The fix: seed the random number generator with the map task ID (deterministic per task), ensuring re-runs always produce the same sample. The lesson: non-deterministic map functions silently break MapReduce's fault tolerance model. Determinism must be enforced at the function level, not assumed.

---

---

## Part 12: Extended Interview Scenarios and Design Patterns

### Design Pattern 1: Multi-Input MapReduce (Union of Heterogeneous Sources)

Real pipelines often process data from multiple sources with different formats. MapReduce supports multiple input paths with different map functions for each:

```
MULTI-INPUT MAPREDUCE: User profile enrichment

Sources:
  - /data/profiles/   (format: user_id, name, signup_date)
  - /data/purchases/  (format: user_id, product_id, amount, timestamp)
  - /data/sessions/   (format: user_id, session_start, session_end, pages)

Goal: Create one enriched user record per user_id combining all sources.

MAP for profiles:
  emit(user_id, Tag("PROFILE", name, signup_date))

MAP for purchases:
  emit(user_id, Tag("PURCHASE", product_id, amount))

MAP for sessions:
  emit(user_id, Tag("SESSION", duration=(session_end - session_start)))

SHUFFLE: all records for user_id=42 land on the same reducer

REDUCE for user_id:
  profile = None; purchases = []; total_session_time = 0
  for record in values:
      if record.tag == "PROFILE":    profile = record
      if record.tag == "PURCHASE":   purchases.append(record)
      if record.tag == "SESSION":    total_session_time += record.duration
  
  if profile:  # only emit if user has a profile record
      emit(user_id, {
          "name": profile.name,
          "signup_date": profile.signup_date,
          "total_purchases": len(purchases),
          "total_spend": sum(p.amount for p in purchases),
          "total_session_hours": total_session_time / 3600
      })

OUTPUT: One enriched row per user, combining three data sources.

HADOOP CONFIGURATION:
  MultipleInputs.addInputPath(job, profilePath, TextInputFormat, ProfileMapper.class)
  MultipleInputs.addInputPath(job, purchasePath, TextInputFormat, PurchaseMapper.class)
  MultipleInputs.addInputPath(job, sessionPath, TextInputFormat, SessionMapper.class)
```

**Memory consideration:** The reducer buffers all purchases for one user before writing output. If a single user has 10 million purchase records (unlikely but possible for accounts like Amazon's test accounts), the reducer OOMs. Mitigation: use secondary sort — sort records by tag first within each user_id, so PROFILE comes first, then PURCHASES stream through, then SESSIONS. The reducer emits as it streams without buffering all purchases.

---

### Design Pattern 2: Iterative MapReduce with Convergence Detection

For algorithms that need multiple rounds (PageRank, k-means, connected components), each round is a MapReduce job. The driver program loops until convergence:

```python
# DRIVER PROGRAM: Iterative MapReduce

iteration = 0
max_iterations = 50
delta = float('inf')
CONVERGENCE_THRESHOLD = 0.001

while delta > CONVERGENCE_THRESHOLD and iteration < max_iterations:
    # Run one iteration
    job = MapReduceJob(
        input=f"/pagerank/iter_{iteration}/",
        output=f"/pagerank/iter_{iteration+1}/",
        mapper=PageRankMapper,
        reducer=PageRankReducer,
        num_reducers=1000
    )
    job.run()
    
    # Read convergence metric from job counters
    # (MapReduce supports custom counters that are accumulated across all tasks)
    delta = job.counters["max_rank_change"]
    
    iteration += 1
    print(f"Iteration {iteration}: max rank change = {delta:.6f}")

# After convergence, index is in /pagerank/iter_{iteration}/
print(f"PageRank converged in {iteration} iterations")

# CUSTOM COUNTER IN REDUCER:
def reduce(url, values):
    old_rank = state.get(url, 1.0 / total_urls)
    new_rank = 0.85 * sum_incoming_rank + 0.15 / total_urls
    
    # Custom counter: accumulate max change across all keys
    rank_change = abs(new_rank - old_rank)
    context.increment_counter("max_rank_change", rank_change)  # NOT correct for max
    # Note: counters are summed (not maxed) — need a separate job to compute max delta
    # Or: use an approximation — if sum of all changes < threshold, we've converged
    
    emit(url, new_rank)
```

**MapReduce counters:** A useful but little-known feature. Each task can increment named counters. The master aggregates counters across all tasks (summing them). The final job counters are available to the driver program after the job completes. This enables convergence detection without a separate job to compute statistics: accumulate total rank change, and if total change < threshold, stop iterating.

---

### Design Pattern 3: Joins with Bloom Filter Pre-filtering

A common optimization for large reduce-side joins: use a Bloom filter from the smaller table to pre-filter records from the larger table in the map phase, before the shuffle.

```
BLOOM FILTER JOIN OPTIMIZATION

Scenario: Join 10TB purchase table with 100MB fraud blacklist table.
          For each purchase, check if buyer is on the blacklist.

NAIVE APPROACH (reduce-side join):
  - Shuffle 10TB of purchases + 100MB of blacklist = 10.1TB shuffled
  - Slow: 10TB network transfer during shuffle

BLOOM FILTER APPROACH:
  SETUP (before job):
    Build Bloom filter from 100MB blacklist (1M suspect user_ids).
    Bloom filter size: ~12 bits per element × 1M elements = 1.5MB
    Serialize Bloom filter to GFS: /bloom/fraud_blacklist.bf
    
  MAP phase (purchases):
    # Each map worker loads the 1.5MB Bloom filter into memory at start
    bloom = load_bloom_filter("/bloom/fraud_blacklist.bf")
    
    for each purchase record:
        if bloom.might_contain(purchase.user_id):
            # Only emit records that MIGHT be in blacklist
            # Bloom filter: no false negatives, some false positives
            emit(purchase.user_id, purchase)
        # else: definitely not in blacklist, skip (no false negatives!)
    
  SHUFFLE: only emit records that passed the Bloom filter.
           With 1% false positive rate, shuffle is ~1% of 10TB = 100GB
           Plus: 100MB blacklist records → total ~100GB (vs. 10TB naive)
           100x reduction in shuffle data!

  REDUCE (for surviving purchase records):
    Match against actual blacklist records.
    True positives (actual fraud): emit alert.
    False positives: discard (record passed Bloom filter but not in actual list).

TRADEOFF: Extra preprocessing step (building Bloom filter).
          Works only when one table fits in memory as a Bloom filter.
          Cannot be used when both tables are large.
```

---

### Extended Brainstorming: Designing Around MapReduce's Limitations

**Q: A product team wants to compute real-time recommendations for users while also computing batch analytics on historical behavior. They have 1 billion users and 100 million products. Design the full data architecture.**

At a billion-user scale, this problem cleanly separates into two subsystems that should NOT share an execution engine. The batch analytics layer (computing historical behavior aggregates: what users have purchased, what they've rated, cohort-level preferences) runs on Spark (or MapReduce for simpler aggregations). A nightly Spark job reads the full user-product interaction history from GFS, computes collaborative filtering model parameters (ALS matrix factorization is well-supported in Spark's MLlib), and writes the trained model to GFS. This batch job can take hours — that's fine, because the model doesn't need to change more than daily.

The real-time recommendation layer is architecturally separate. When a user makes a request, the serving layer does not run MapReduce. It reads precomputed user vectors and item vectors from Bigtable (or Redis) — these are the outputs of the batch Spark job. The real-time system computes a dot product between the user vector (128 dimensions, loaded from Bigtable in <5ms) and the top-1000 candidate item vectors (precomputed and cached) to rank recommendations. The "freshness" tradeoff: the model is updated daily (batch), but the real-time serving is instant because it's just vector math against precomputed embeddings.

The data pipeline is: raw interaction events → Kafka → (1) Spark streaming writes events to HDFS in Parquet format for batch layer; (2) Flink reads events and updates a real-time feature store (session-level features like "user clicked product X 3 minutes ago" that are too fresh for the daily model). The recommendation system combines daily model scores with real-time Flink features. This is a concrete example of the lambda architecture: batch for the model (Spark), streaming for fresh signals (Flink), with the serving layer merging both. The key insight for L6: never let the batch job be in the critical path of a user request. The batch job produces artifacts (model parameters, precomputed embeddings) that the real-time system consumes. The real-time system never runs a MapReduce job per request.

---

### Common Patterns That Interviewers Test

```
┌─────────────────────────────────────────────────────────────────────────┐
│  MAPREDUCE PATTERN RECOGNITION CHEAT SHEET                              │
│                                                                         │
│  Problem type          → MapReduce pattern                              │
│  ─────────────────────────────────────────────────────────────────────  │
│  Count occurrences     → Map: emit (key,1). Combiner+Reduce: SUM        │
│  Find maximum/minimum  → Map: emit (key,value). Reduce: MAX/MIN         │
│  Join two tables       → Map both: emit (join_key, tagged_record)       │
│                           Reduce: group by key, perform join logic      │
│  Top-N globally        → Map: emit ("ALL", value). Reduce: heapq.nlargest│
│                           Problem: single reducer bottleneck            │
│                           Better: local top-N in combiner, merge in reducer│
│  Top-N per group       → Map: emit (group, value). Reduce: top-N per group│
│                           Combiner: local top-N per group (valid here!) │
│  Sort entire dataset   → Map: identity (emit k,v as-is). 1 reducer: sort│
│                           Or: use TeraSort approach (range partition)   │
│  Group by + aggregate  → Map: emit (group_key, metric). Reduce: aggregate│
│  Inverted index        → Map: (doc, word) → emit (word, doc).           │
│                           Reduce: collect all docs per word             │
│  Deduplication         → Map: emit (record, null). Reduce: emit first   │
│  Graph iteration       → One MapReduce job per iteration. Chain jobs.   │
│  Session reconstruction→ Map: emit (user_id, event). Secondary sort by  │
│                           timestamp. Reduce: stream events in order.    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### MapReduce Capacity Planning Reference

For an interview where you're asked to estimate job duration from first principles:

```
MAPREDUCE PERFORMANCE REFERENCE NUMBERS (approximate, 2024 hardware)

  Local disk read:    ~500 MB/s (NVMe SSD), ~150 MB/s (HDD)
  Network (intra-rack): ~1 GB/s per machine (1GbE shared)
  Network (cross-rack): ~10 GB/s (10GbE per machine, shared core switch)
  HDFS write (3 replicas): ~100 MB/s effective (limited by slowest replica)
  GFS/HDFS read: ~200 MB/s local, ~100 MB/s remote
  Map CPU (parsing text): ~50-100 MB/s input processed per CPU core
  
  MAP PHASE estimate:
    Input size / (map_tasks × min(disk_read_speed, CPU_parse_speed))
    Example: 10TB, 10000 map tasks, CPU-bound at 100MB/s:
    10TB / (10000 × 100MB/s) = 10s (all tasks fully parallel)
    More realistic: not all 10000 tasks run simultaneously.
    With 2000 worker slots: 5 waves × 10s = 50s map phase

  SHUFFLE estimate:
    Intermediate_data_size / aggregate_network_bandwidth
    Example: 1TB shuffle, 1000 reducers × 100MB/s = 100GB/s
    1TB / 100GB/s = 10s ideal (ignores TCP overhead, ~3x penalty: ~30s actual)

  REDUCE estimate:  
    Depends on computation; typically 10-50% of map phase duration
    Memory-intensive reduces (sorting) add disk spill time if data exceeds buffer

  TOTAL JOB TIME FORMULA (rough):
    T = startup (30-60s) + map_phase + overlap_shuffle + reduce_phase
    Startup dominates for tiny jobs. Shuffle dominates for large aggregations.
    Reduce dominates for complex computations (sort, ML inference).
```

---

## Exercises

**Exercise 1: Write the map and reduce functions**
Write pseudocode map and reduce functions for the following tasks:
a) Count the number of links to each URL on the web (given input: (page_url, [list_of_links_on_page]))
b) Find the maximum temperature per city per day (given input: (station_id, city, date, temperature))
c) Compute the unique visitor count per website per hour (given input: (timestamp, visitor_id, website))

For each, also specify: what does the combiner do (if applicable)?

**Exercise 2: Trace the execution of a join**
Input table A: (user_id → username, email). Input table B: (user_id → purchase_amount).
Goal: produce (username, total_purchases) for each user.
Trace the complete MapReduce execution: what the map functions emit, how the shuffle groups the data, what the reduce function does, and what the output looks like.

**Exercise 3: Straggler analysis**
A MapReduce job has 1,000 map tasks. Each map task normally completes in 2 minutes. One map task runs on a slow machine and takes 30 minutes. The shuffle takes 5 minutes after all maps complete. The reduce phase takes 3 minutes.
a) Total job time WITHOUT backup tasks?
b) If backup tasks are launched after 4 minutes of map completion (when 999/1000 tasks have finished), and the backup for the slow task takes 2 minutes: total job time WITH backup tasks?
c) What is the overhead of backup tasks (extra work performed)?

**Exercise 4: Combiner correctness**
For each of the following reduce functions, determine whether a combiner can be used. If yes, write the combiner function. If no, explain why.
a) SUM of values
b) COUNT of distinct values
c) MAX of values
d) AVERAGE of values
e) MEDIAN of values
f) Top-10 values (by score)

**Exercise 5: PageRank with MapReduce**
Design a MapReduce job for one iteration of PageRank. Assume input format: (url, current_rank, [out_links]).
a) Write the map function.
b) Write the reduce function.
c) How many MapReduce jobs are needed for convergence?
d) What is the total data read and written for 20 iterations on a 10TB web graph?
e) How would Spark reduce this cost?

**Exercise 6: Interview practice — 8-minute answer**
The interviewer says: "We have 1 billion user clickstream events per day (each event is: user_id, product_id, timestamp, action). Design a batch processing pipeline to compute: (1) total clicks per product per day, (2) unique users per product per day, (3) top-10 products by clicks per day. Assume the data is already in GFS."
Design the MapReduce pipeline: number of jobs, map/reduce functions for each, combiner optimizations, and expected data volumes at each stage.

**Exercise 7: Performance optimization**
A MapReduce job processes 100TB of web logs. The shuffle produces 80TB of intermediate data (nearly uncompressed). Job takes 20 hours.
a) What is the expected impact of adding a combiner (assume 10:1 compression ratio for common keys)?
b) What is the expected impact of adding LZO compression for intermediate data (4:1 compression)?
c) If the shuffle is network-bound at 10GB/s aggregate across all reduce workers, what is the minimum possible job time with full optimization?

---

## Homework

**Homework 1: Read the original paper.**
Read the MapReduce paper (Dean & Ghemawat, OSDI 2004 — available free online). Focus on Sections 2 (Programming Model), 3 (Implementation), and 6 (Experience). For each section, write one paragraph: key design decision, trade-off made, and how modern systems handle this differently.

**Homework 2: Implement word count.**
Implement word count in MapReduce using Apache Hadoop (or Apache Spark, if preferred). Run it on a 1GB input file. Measure: total job time, shuffle data size, time spent in each phase (map, shuffle, reduce). Then add a combiner and remeasure. Document the performance difference.

**Homework 3: Design a MapReduce pipeline.**
Design a complete multi-job MapReduce pipeline for building a simple web search index:
- Job 1: Parse HTML, extract (url, word) pairs
- Job 2: Compute word frequencies per URL
- Job 3: Build inverted index (word → list of URLs sorted by frequency)
- Job 4: Join with PageRank scores to sort by relevance
For each job: input format, map function, combiner (if any), reduce function, output format. Estimate data volume at each stage.

**Homework 4: Spark vs MapReduce benchmark.**
Using a public dataset (Wikipedia dump, Common Crawl, or similar), implement the same word count job in both Hadoop MapReduce and Apache Spark. Compare: job completion time, shuffle data volume, CPU utilization, peak memory usage. Document when Spark's advantage is largest (iterative algorithms vs single-pass).

**Homework 5: Mock interview drill.**
Have a friend say: "Design a pipeline to process 1 billion rows of user purchase data to find: (1) top 100 products by revenue for each country, (2) cohort retention (what % of users who purchased in week 1 purchased again in weeks 2-8), (3) cross-sell pairs (products frequently purchased together)." Practice a 15-minute answer covering: which questions can be answered in a single MapReduce job, which require chaining, what the map/reduce functions look like for each, and whether Spark would be better.

---

---

## Part 13: Anti-Patterns and Debugging Guide

### The 5 Most Common MapReduce Bugs

**Bug 1: Mutable state in the map or reduce function**

```python
# WRONG: class-level counter is shared across records within one task
class CountingMapper(Mapper):
    total = 0  # class variable — shared state!
    
    def map(self, key, value):
        self.total += 1
        emit(key, self.total)  # BUG: total keeps incrementing across records

# RIGHT: no shared state; all state is local to one map() call
def map(key, value):
    count = 1  # local to this invocation
    emit(key, count)
```

Shared state breaks both correctness (counts accumulate incorrectly) and fault tolerance (if the task is re-run, the counter starts at zero instead of where it left off — producing different output). Always write map and reduce functions as if they have no memory between calls.

**Bug 2: Forgetting that reduce() receives values as a lazy iterator, not a list**

In Java Hadoop, `values` is an `Iterable<V>` — you can iterate over it once. If you try to iterate twice (once to compute total count, once to normalize), the second iteration is empty. Fix: convert to a list at the start of the reduce function if you need multiple passes. But be aware that converting a very large iterator to a list can cause OOM. Design reducers to do one-pass computations whenever possible.

**Bug 3: Writing to GFS (or HDFS) from inside the map function**

```python
# WRONG: opening GFS files inside map creates N×M GFS connections
def map(key, value):
    result = process(value)
    gfs.write("/output/result_" + key, result)  # BUG: one file per map call!
    # For 1 billion records: 1 billion tiny GFS files. GFS master OOM.
```

Map tasks should emit key-value pairs. GFS writes happen in the reduce phase (framework-managed). Side-effecting GFS writes from map tasks bypass the framework's atomicity guarantees and create thundering-herd load on the GFS master.

**Bug 4: Key ordering assumption in reduce()**

The reducer receives values for a given key, but the order of those values is NOT specified. Do not assume that values arrive in insertion order, time order, or any particular order. If order matters, use secondary sort (encode the sort key into the map output key). This bug is particularly insidious in session reconstruction: if you assume events arrive in timestamp order and they don't, your session logic produces corrupt results with no error message.

**Bug 5: Using reduce() when a combiner would suffice**

This isn't a correctness bug — it's a performance bug. If your reduce function is `sum(values)` and you don't add a combiner that also does `sum(values)`, your shuffle volume is 10-1000x larger than necessary. In a production cluster, this can be the difference between a 10-minute job and a 10-hour job. Always ask: "Is my reduce function associative and commutative? If so, why isn't there a combiner?"

---

### Debugging a Slow MapReduce Job: A Systematic Approach

```
DEBUGGING FLOWCHART: "My MapReduce job is taking 3x longer than expected"

Step 1: Look at the phase breakdown in the job monitoring UI.
  Which phase is slow?
  
  MAP phase is slow:
    → Is one map task much slower than others? (STRAGGLER)
      → Enable backup tasks (speculative execution)
      → Check if slow task is on a machine with high disk latency
    → Are ALL map tasks slow?
      → CPU-bound: profile map function for algorithmic bottleneck
      → I/O-bound: check if reading from remote GFS (no data locality)
                   → increase data locality by rescheduling or resharding
      → Memory-bound: check if map is using excessive heap for buffering

  SHUFFLE phase is slow:
    → How large is the intermediate data?
      → If > 20% of input size: add or improve combiner
      → Check intermediate data compression (enable LZO/Snappy)
    → Is network saturated?
      → Check if other jobs are running simultaneously (contention)
      → Reduce shuffle volume (combiner) or slow down shuffle rate (throttle)
    → Is shuffle fetching failing and retrying?
      → Map workers might be crashing → check GC pressure, disk errors

  REDUCE phase is slow:
    → One reducer taking 10x longer? → HOT KEY / DATA SKEW
      → Add random suffix to hot key, merge in second job
    → All reducers slow?
      → Spilling to disk → increase reducer memory buffer
      → CPU-bound sort → reduce may have too many values per key

Step 2: Check counters in the job UI.
  "map input records" vs "map output records": what's the expansion ratio?
  "shuffle bytes transferred": is it more than expected?
  "reduce input groups": how many distinct keys per reducer?
  Custom counters: any "invalid record" or "skipped record" counters?

Step 3: Look at task attempt logs for the slow tasks.
  Hadoop/YARN provides per-task logs accessible from the job UI.
  Common log signals:
    - "GC overhead limit exceeded" → JVM OOM, reducer needs more memory
    - "Connection refused from worker:X" → map worker died during shuffle
    - "Timeout fetching map output" → map worker too slow to serve output
```

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────────────┐
│                  MAPREDUCE QUICK REFERENCE                          │
│                                                                     │
│  Model:          map(k,v) → [(k2,v2),...]; reduce(k2,[v2,...]) → v3│
│  Phases:         Map → Shuffle (framework) → Reduce                │
│  Input:          GFS (64MB splits = 1 map task per split)           │
│  Map output:     local disk (NOT GFS), partitioned by key hash      │
│  Reduce output:  GFS                                               │
│                                                                     │
│  Fault tolerance:                                                   │
│  • Failed map tasks: re-run (output on local disk is gone)          │
│  • Completed map tasks on failed worker: re-run (disk gone)         │
│  • Failed reduce tasks: re-run (output on GFS is safe)              │
│  • Completed reduce tasks: NOT re-run (output on GFS)               │
│  • Stragglers: speculative execution (backup tasks)                 │
│                                                                     │
│  Key optimizations:                                                 │
│  1. Data locality: run map near GFS chunk                          │
│  2. Combiners: pre-aggregate on map machine (require commutativity) │
│  3. Speculative execution: duplicate slow tasks at end of job       │
│  4. Compression: compress intermediate data for shuffle             │
│  5. Custom partitioner: control which reducer handles which keys    │
│                                                                     │
│  When to use MapReduce (or Spark):                                  │
│  ✓ Single-pass batch transformation                                │
│  ✓ Large-scale aggregation (counts, sums, joins)                    │
│  ✓ Inverted index construction                                      │
│  ✓ ETL pipelines                                                    │
│  ✗ Real-time/streaming (use Flink/Kafka Streams)                    │
│  ✗ Iterative ML (use Spark with in-memory RDDs)                    │
│  ✗ Sub-second latency (batch minimum latency: minutes)              │
│                                                                     │
│  Open-source equivalents:                                           │
│  MapReduce → Hadoop MapReduce                                       │
│  GFS → HDFS                                                         │
│  Modern batch → Spark (10-100x faster for iterative)               │
│  Unified batch+stream → Apache Beam / Google Dataflow               │
│  Streaming → Flink, Kafka Streams                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Chapter Summary

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CHAPTER 85: KEY TAKEAWAYS                        │
│                                                                     │
│  1. MapReduce separates logic (map + reduce functions) from         │
│     distribution (handled by the framework). Programmers write     │
│     business logic; the framework handles fault tolerance.         │
│                                                                     │
│  2. Three phases: Map (transform, write to local disk) →           │
│     Shuffle (sort + transfer to reducers) → Reduce (aggregate,     │
│     write to GFS). The shuffle is always the bottleneck.           │
│                                                                     │
│  3. Fault tolerance via re-execution: deterministic functions      │
│     mean failed tasks can just be run again. Backup tasks          │
│     eliminate straggler effects.                                    │
│                                                                     │
│  4. Key optimization: combiners reduce shuffle data dramatically   │
│     for commutative+associative operations. Always use them.       │
│                                                                     │
│  5. MapReduce = GFS + Bigtable's processing glue: GFS stores raw   │
│     data, MapReduce processes it, Bigtable stores results for      │
│     online serving.                                                │
│                                                                     │
│  6. Limitations: no streaming, no efficient iteration, disk I/O    │
│     between stages. Spark solved iteration; Flink solved streaming. │
│                                                                     │
│  7. Interview one-liner: "MapReduce's fault tolerance comes from   │
│     deterministic re-execution — failed tasks are re-run, not       │
│     logged and rolled back."                                        │
└─────────────────────────────────────────────────────────────────────┘
```

---

---

## Part 10: Staff-Level Q&A Drill

> These ten questions simulate the depth of a Google L6 system design interview. Each answer should take 3-4 minutes to deliver verbally — that's the target length here in text form. Read the question, try to answer it yourself, then compare.

### Q1: Why does MapReduce use pull (reducers fetch map output) instead of push (master pushes data to reducers)?

**The intuitive design** might seem to be: when a map task completes, the master immediately pushes that map's output to the relevant reducers. This would start data movement early and keep reducers busy. But pull has a crucial advantage: it puts the reducer in control of when it fetches, how much it fetches, and from which workers. The reducer can throttle its fetching based on its local memory availability, retry selectively when a specific map worker is slow, and parallelize fetching from multiple map workers simultaneously at its own pace. With push, the master would need to track which reducers have available buffer space, implement flow control for each reducer, and handle backpressure — turning the master into a data-flow controller on top of its scheduling responsibilities.

Pull also makes fault recovery simpler. If a map worker dies after completing its task, the reducer (when it tries to fetch) notices the HTTP connection fails. The reducer informs the master, which schedules a re-run of the failed map task. The reducer then retries fetching from the new location. With push, the master would need to track which reducers had already received which map outputs — a complex state machine. Pull is also more resilient to reducer failures: if a reducer dies mid-fetch, it simply hasn't fetched anything yet (its in-progress fetches were in-memory only), and re-running the reducer task starts fetching fresh.

The deeper engineering principle: in distributed systems, pulling is generally safer than pushing when the receiver has variable capacity and the failure modes are complex. Kafka uses the same pull model for consumer reads. Browser HTTP uses pull (client requests, server responds). The pull model naturally provides backpressure — if the receiver is overwhelmed, it simply stops pulling, which is a natural signal. In contrast, push systems require explicit flow control mechanisms (TCP's receive window, Kafka's consumer offsets, etc.) that add complexity.

---

### Q2: How does MapReduce handle clock skew when identifying stragglers?

**Clock skew** is a real problem in any distributed system that makes decisions based on time — clocks on different machines drift, some machines have clocks that are minutes fast or slow. MapReduce's straggler detection cannot rely on "this task has been running for more than X minutes by the wall clock" because clock skew would cause false positives on machines with slow clocks and false negatives on machines with fast clocks.

MapReduce solves this by using the master's local clock as the single time source for all scheduling decisions. The master records task start time when it assigns the task (using its own clock). The master checks for stragglers by comparing the current time (its own clock) to the recorded start time. Workers do not participate in time calculations — they only report "task complete" or "task in-progress" via heartbeats. Since all time comparisons are between two timestamps on the same machine (the master), clock skew on workers is irrelevant. A worker with a slow clock doesn't affect the master's calculation at all.

The subtlety: heartbeat-based liveness detection (used to detect dead workers) does not need accurate clocks either. The master records the last heartbeat timestamp using its own clock. If the master's clock shows 60 seconds have passed since the last heartbeat, the worker is declared dead — regardless of what the worker's clock says. Again, all comparisons are single-clock (master only), eliminating skew. This pattern — use a single authoritative clock (the coordinator) for all time-dependent decisions — is a recurring pattern in distributed systems: Zookeeper uses it for session timeout, Chubby uses it for lease expiration, and Raft uses it for leader election timeouts.

---

### Q3: If your MapReduce job is CPU-bound in the map phase but network-bound in the shuffle, what do you optimize first?

**Answer the constraint, not the easy part.** The bottleneck is the shuffle — that's what limits total job time. Even if you make the map phase 10x faster (by adding more machines or faster CPUs), the shuffle is unchanged, and the shuffle dominates total job time. You optimize the shuffle first.

Shuffle optimization for a CPU-bound-in-map job specifically: the fact that maps are CPU-bound suggests they're doing complex processing (parsing, joining, computing features) and probably emitting a large number of key-value pairs. The first optimization is a combiner: reduce the number of pairs that leave each map machine before they hit the network. The second optimization is intermediate data compression: compress map output (using LZO or Snappy) before writing to disk and before transmitting during shuffle. CPU for compression is cheap because maps are CPU-bound anyway — the CPUs are spending time on map logic, and adding compression during the brief spill-to-disk phase is usually not the bottleneck. For a 4:1 LZO compression ratio, the shuffle network transfer time drops by 4x.

The third optimization is structural: reconsider your map key. If your shuffle is large because you're emitting high-cardinality keys with many values, consider whether you can use a coarser key (e.g., emitting by (user_id, day) instead of (user_id, event_id)). Coarser keys mean fewer distinct reduce calls, which means the combiner can pre-aggregate more aggressively, which reduces shuffle volume. The rule: optimize the shuffle before optimizing the non-bottleneck. Only after shuffle is optimized should you address the map CPU bottleneck — perhaps by adding more map workers or profiling the map logic for algorithmic inefficiency.

---

### Q4: Design a MapReduce job that computes the 99th percentile latency for 10,000 different API endpoints from 1TB of logs.

**The naive approach** fails because percentiles are not summable: you cannot compute the true 99th percentile from partial percentiles computed on subsets. `p99(p99(A), p99(B)) != p99(A ∪ B)`. So a simple combiner with "compute local p99" is mathematically incorrect.

**The correct approach with exact p99:** Map function: parse each log line, emit `(endpoint_id, latency_ms)`. No combiner possible for true percentile. Reducer: receives all latency values for one endpoint (possibly millions of values), sorts them, returns the value at the 99th percentile index. The problem: for a high-traffic endpoint with 100 million requests per day, the reducer must sort 100 million values in memory — which at 8 bytes each is 800MB. With 10,000 endpoints sharing 200 reducers, each reducer handles ~50 endpoints. Peak memory: 50 endpoints × 800MB = 40GB — OOM. You need to either increase reducers (use 10,000 reducers, one per endpoint) or use an approximate algorithm.

**The practical Staff-level approach: t-digest as a combiner-safe approximation.** The t-digest algorithm maintains a compact sketch of a distribution (typically 10-50KB) that can be merged exactly: `merge(t_digest(A), t_digest(B)) == t_digest(A ∪ B)`. This is the property that makes it combiner-safe. Map function: emit `(endpoint_id, latency_ms)` as before. Combiner: accumulate latency values into a t-digest sketch, emit `(endpoint_id, serialized_t_digest)`. Reducer: merge all received t-digests (one per map machine), extract p99 from the merged sketch. Accuracy: t-digest gives p99 within ±0.5% of the true value, which is acceptable for operational metrics. Memory: each t-digest sketch is ~50KB, so a reducer handling 50 endpoints holds 2.5MB of sketches — trivial. The output is a file with 10,000 rows: `(endpoint_id, p99_latency_ms)`, computed accurately from 1TB of logs in a single MapReduce job.

---

### Q5: What is the difference between a combiner and a reducer? When can a combiner NOT be used?

**They share the same function signature** — both take `(key, [values])` and emit `(key, value)` — which is why many tutorials say "the combiner is a mini-reducer." But their semantic requirements differ fundamentally. The reducer is the final authority: it receives ALL values for a key from across the entire job and produces the final output. The combiner is a pre-aggregation hint: it may receive a SUBSET of values for a key (only those from one map machine) and its output will be further aggregated by the reducer. The framework is allowed to skip the combiner entirely, run it once, or run it multiple times — the job must produce correct output regardless.

This leads to the constraint: a combiner can be used only when the reduce function is both commutative (order of values doesn't matter) and associative (grouping of values doesn't matter). `SUM(a, b, c) == SUM(SUM(a,b), c)` — associative, SUM works. `AVERAGE(a,b,c) != AVERAGE(AVERAGE(a,b), c)` — not associative, AVERAGE breaks. Specifically, `AVERAGE(1,2,3) = 2`, but `AVERAGE(AVERAGE(1,2), 3) = AVERAGE(1.5, 3) = 2.25` — different result.

Functions where combiners cannot be used: (1) AVERAGE, MEAN, STANDARD DEVIATION — non-associative unless you emit (sum, count) and compute in reducer; (2) MEDIAN, PERCENTILE — require all values sorted together; (3) COUNT DISTINCT — you cannot combine partial distinct counts without knowing the exact set (without probabilistic structures like HyperLogLog); (4) any function with state that depends on the order of values; (5) any function that examines relationships between values (e.g., "count runs of consecutive values"). The workaround for non-combinable functions: change what you emit to make the emitted type combinable. For average, emit `(sum, count)` as a composite value. For distinct count, emit HyperLogLog sketches (which ARE mergeably associative). The function itself may not be combinable, but you can often choose an emitted representation that is.

---

### Q6: Google's web index has 50 billion URLs. How many MapReduce tasks would you use to rebuild it from scratch?

**Start with the constraints.** 50 billion URLs at ~4KB of page content each = 200TB of input data. GFS uses 64MB chunks, so 200TB / 64MB = ~3.1 million input chunks. The MapReduce convention is one map task per input chunk, so roughly 3 million map tasks. But 3 million map tasks is too many to run simultaneously — the cluster might have 5,000 machines, each running 2-4 tasks concurrently, giving 10,000-20,000 concurrent map slots. 3 million tasks across 20,000 slots = 150 sequential waves of map tasks. That's fine — the framework handles this automatically (tasks queue up and are assigned as slots free).

For reducers, the question is: what's the desired granularity of the output, and what's the memory constraint per reducer? The web index has ~100 million unique words (including URLs and technical terms). With 200 reduce tasks, each reducer handles 500,000 words on average. If each word has an average of 500 URLs in its posting list at ~50 bytes per URL, that's 25GB per reducer — too large for memory. You'd need more reducers. With 5,000 reducers, each handles 20,000 words × 500 URLs × 50 bytes = 500MB — manageable. So: 3 million map tasks (queued and run in waves), 5,000 reduce tasks (run after map phase, fits in memory per reducer).

The Staff-level nuance: this is a pipeline of jobs, not one job. Job 1 parses HTML and extracts (word, URL) pairs. Job 2 computes TF-IDF (term frequency-inverse document frequency, requires knowing global document frequency). Job 3 joins with PageRank scores. Job 4 builds the final posting lists sorted by score. Each job has different optimal map/reduce task counts. The key insight: choose task counts based on (a) input size divided by chunk size for maps, and (b) desired output granularity and per-reducer memory constraints for reducers.

---

### Q7: How does speculative execution interact with non-idempotent operations?

**Speculative execution (backup tasks) works only if tasks are idempotent.** An idempotent operation produces the same result no matter how many times it runs — the result of running it twice is the same as running it once. MapReduce assumes tasks are idempotent because they are deterministic and write to uniquely-named temp files that are atomically renamed only once. The atomic rename ensures that even if two copies of a task complete, only one copy's output is visible in the final result.

Non-idempotent operations break this guarantee. Example: a map task that, as a side effect, sends an email notification for each processed record. If speculative execution causes the task to run twice on two different machines simultaneously, users receive duplicate emails. The GFS output would be correct (atomic rename handles that), but the side effect (email) happened twice. Another example: a map task that writes to an external database. If run twice, it might insert duplicate rows (if the insert isn't upsert).

**The correct approach for non-idempotent tasks in MapReduce:** avoid non-idempotent side effects entirely in map and reduce functions. Write idempotently: use upsert instead of insert, write to locations that overwrite safely, use idempotency keys for external API calls. If you genuinely cannot avoid non-idempotent effects, disable speculative execution for that job (set `mapreduce.map.speculative = false` and `mapreduce.reduce.speculative = false` in Hadoop). The cost is that you lose straggler protection — one slow machine can hold up the entire job. This is a real trade-off in practice: payment processing jobs that write to external ledgers often run without speculative execution, accepting the performance risk in exchange for exactly-once semantics.

---

### Q8: What happens to a MapReduce job if the master process crashes 90% of the way through?

**In Google's original 2004 MapReduce implementation:** the job fails completely. The master is a single point of failure with no hot standby and no persistent checkpoint of its state. When the client detects that the master is unreachable (via polling), it reports the job as failed and the client must resubmit the entire job from scratch. The justification: master failures are rare (one machine out of thousands), and resubmitting a job is much simpler than building a replicated, consistent master state machine. At 90% completion, resubmitting means re-running 10% of the work (the framework does not checkpoint per-task output beyond what's on GFS).

**Wait, it's more nuanced than "start from scratch."** Completed reduce tasks wrote their output to GFS atomically. If the job is resubmitted, the new master will find that the output files for completed reducers already exist. If the framework is designed to detect this and skip re-running those reducers, then only the incomplete reducers (and any map tasks needed to feed them) need to re-run. However, the original 2004 MapReduce did not implement this optimization — it restarted the entire job. Modern Hadoop/Spark implementations have job-level checkpointing that allows recovery from partial job completion.

**The Staff-level design question:** how would you make the master fault-tolerant without restarting the entire job? The answer: replicate the master state. The master's state is relatively small — it's just a table of (task_id → state, worker, output_location). This table can be replicated to 2 standby masters using Paxos or Raft. On master failure, a standby promotes itself and resumes scheduling using the checkpointed state. The cost: added complexity of consensus protocol for master state updates. The benefit: no job restart on master failure. Google's internal systems (post-2004) moved toward this model. Modern Hadoop YARN uses a ResourceManager with standby failover via ZooKeeper.

---

### Q9: How would you implement a distributed join of two 10TB datasets in MapReduce? What are the memory constraints?

**There are three join strategies in MapReduce, each with different memory requirements.**

**Strategy 1: Reduce-side join (the standard approach).** Both datasets emit records with the join key as the intermediate key, tagged with a dataset identifier. Reducer receives all records for a given join key from both datasets and performs the join. Memory requirement: the reducer must hold in memory all records from one side of the join for a given key before it can start producing output. If one key appears in 1 million rows of dataset A and 1 million rows of dataset B, the reducer needs to hold 1 million rows of A in memory while streaming through 1 million rows of B (or vice versa). At 100 bytes per row, that's 100MB per key — manageable if no single key has too many rows. Data skew (one super-common key) is the main failure mode: one reducer gets gigabytes of data while others get megabytes. Solution: detect skewed keys and process them with a separate, more-parallelized job.

**Strategy 2: Map-side join (broadcast join).** If one dataset is small enough to fit entirely in memory on each map machine (say, under 1GB), you can avoid the shuffle entirely. Load the small dataset into a hash map in the map worker's memory. For each record in the large dataset, look up the join key in the in-memory hash map. Emit the joined record directly. Memory requirement: the entire small dataset must fit in memory on every map machine simultaneously. This is the fastest join strategy — no shuffle at all — but requires one dataset to be small. For 10TB + 10TB, this doesn't apply. For 10TB + 10GB, it's worth considering.

**Strategy 3: Sort-merge join.** Sort both datasets by the join key (using a separate MapReduce job each), then merge the two sorted streams key by key in a reducer. This avoids the memory explosion of the reduce-side join for highly skewed keys because neither side needs to be fully buffered — the merge can stream. Memory requirement: only one record from each stream at a time. But it requires two additional MapReduce jobs (one sort per dataset), adding latency. For 10TB + 10TB with skewed keys, this is the correct approach despite the extra jobs.

---

### Q10: Why did Spark replace Hadoop for iterative ML training, even though both use the same programming model (map and reduce)?

**The shared programming model is a surface-level similarity that obscures a fundamental architectural difference.** Both Spark and Hadoop MapReduce express computation as data transformations — you define operations on distributed datasets. But WHERE data lives between operations is completely different. In Hadoop, after each map-reduce job, all intermediate data is written to HDFS (distributed disk) and read back for the next job. For iterative ML training (10-100 passes over the same training data), this means reading the same training data from disk on every iteration. At 100GB of training data × 50 iterations × 2 (read + write) = 10TB of disk I/O, just for I/O — before any computation.

Spark's Resilient Distributed Datasets (RDDs) are the key innovation. An RDD is a distributed dataset that can be explicitly persisted in memory across multiple operations. After the first iteration, `training_data.cache()` keeps the dataset in the executors' memory. Subsequent iterations read from memory at ~10GB/s (RAM bandwidth) instead of from HDFS at ~100MB/s (disk). The speedup for the I/O-dominated portion: 100x. Spark's original paper (Zaharia et al., NSDI 2012) reported a 20x end-to-end speedup on logistic regression training (20 iterations): Spark in 20 seconds vs. Hadoop in 400 seconds. The speedup was entirely from avoiding disk between iterations.

The architectural lesson: the programming model is not the performance model. Two systems can have equivalent programming models (map, filter, reduce, groupBy) but dramatically different performance characteristics based on where data lives between stages. This is why L6 answers don't just name the tool — they explain the mechanism of the speedup. Spark is faster than Hadoop for iterative algorithms not because of better code or better algorithms, but because of the decision to keep data in RAM between operations. For single-pass jobs (ETL, simple aggregations, large sorts), Spark and Hadoop MapReduce have similar performance because memory persistence between iterations provides no benefit. In those cases, Hadoop may actually be more cost-effective — HDFS is simpler to operate than Spark's memory management.

### Intern → Staff Progression (Part 10 — Q&A Drill)

| Level | Q&A Drill capability |
|-------|----------------------|
| **Intern** | Can answer Q5 (combiner vs. reducer) if they've read the tutorial. Cannot answer Q4, Q7, Q8, or Q9. |
| **L3** | Can answer Q5 and Q10 from surface knowledge. Answers Q1-Q4 with "I think..." hedges and incorrect specifics. |
| **L4** | Can answer Q1, Q5, Q10 confidently. Answers Q4 with "use a combiner" without knowing it breaks for percentiles. Struggles with Q7, Q8. |
| **L5** | Can answer Q1-Q5 accurately. Gives a partial Q4 answer (knows t-digest or HyperLogLog). Can trace Q8 from first principles. Struggles with precise Q6 math and Q9 join strategies. |
| **L6** | Can answer all 10 with quantitative precision. For Q4: specifies t-digest by name, explains why it's combiner-safe, estimates per-reducer memory. For Q6: works through the 3M/5K task sizing from first principles. For Q9: names all three strategies (reduce-side, broadcast, sort-merge) and their respective memory constraints. |

---

## Part 11: MapReduce vs. Alternatives — Decision Framework

### Comparison Table

```
┌──────────────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
│              │  MapReduce   │    Spark     │    Flink     │  Dataflow/   │   SQL MPP    │
│              │  (Hadoop)    │              │              │  Beam        │  (BigQuery,  │
│              │              │              │              │              │  Redshift)   │
├──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ Latency      │ Minutes to   │ Seconds to   │ Milliseconds │ Seconds      │ Seconds to   │
│              │ hours        │ minutes      │ to seconds   │ to minutes   │ minutes      │
├──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ Iterative    │ Poor         │ Excellent    │ Good         │ Good         │ Poor         │
│ algorithms   │ (disk I/O    │ (in-memory   │ (in-memory   │ (depends on  │ (no loop     │
│              │ per iter)    │ RDDs)        │ state)       │ runner)      │ construct)   │
├──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ Streaming    │ No           │ Micro-batch  │ Yes, native  │ Yes, unified │ No (some     │
│ support      │              │ (Spark       │ streaming    │ batch+stream │ support       │
│              │              │ Streaming)   │              │ model        │ via ext)     │
├──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ Fault        │ Re-execute   │ RDD lineage  │ Checkpoints  │ Checkpoints  │ Query        │
│ tolerance    │ failed tasks │ (recompute   │ + state      │ + state      │ restart      │
│              │              │ from source) │ restore      │ restore      │              │
├──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ Operational  │ High         │ High         │ High         │ Low (managed │ Very low     │
│ complexity   │ (Hadoop      │ (memory      │ (stateful    │ service)     │ (serverless  │
│              │ cluster ops) │ tuning)      │ complexity)  │              │ option)      │
├──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ Best for     │ Simple       │ Iterative    │ Real-time    │ Unified      │ Interactive  │
│              │ large-scale  │ ML, graph    │ streaming,   │ batch+stream │ analytics,   │
│              │ ETL, sort,   │ algorithms   │ event proc.  │ pipelines    │ ad hoc SQL   │
│              │ batch ingest │              │              │              │              │
├──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ API level    │ Low          │ Medium       │ Medium       │ Medium-High  │ High (SQL)   │
│              │ (write       │ (RDD/Dataset │ (DataStream  │ (PCollection │              │
│              │ map+reduce)  │ API)         │ API)         │ + transforms)│              │
└──────────────┴──────────────┴──────────────┴──────────────┴──────────────┴──────────────┘
```

### The Google Dataflow / Apache Beam Model

Google published the Dataflow paper in 2015, describing a unified model that handles both batch and streaming with a single programming abstraction. The insight: batch processing is just streaming where the input happens to be bounded (finite). If you build a streaming system that can also handle "replay all events from the beginning" as a special case, you get batch for free.

The key concepts in the Dataflow/Beam model:

**PCollections** (parallel collections): the distributed data abstraction, equivalent to Spark's RDDs but designed from the start for both bounded (batch) and unbounded (streaming) datasets.

**Transforms**: operations applied to PCollections. `ParDo` (parallel do) is the map equivalent — apply a function to each element. `GroupByKey` is the shuffle equivalent — group elements by their key. `Combine` is the reduce equivalent — aggregate grouped elements.

**Windowing**: for streaming, Dataflow introduces the concept of time windows — group events by the time they occurred (not the time they were processed). This handles out-of-order events: a window closes when Dataflow estimates all events within that window's time range have arrived (using watermarks). Batch has no equivalent concept because all data arrives at once.

**Runners**: the same Beam pipeline code can run on different execution engines: Apache Flink, Apache Spark, or Google Dataflow (the managed service). The pipeline is a description of the computation; the runner determines how it's actually executed. This portability was Beam's key contribution — write once, run anywhere.

```
BEAM PIPELINE EXAMPLE (conceptually):

PCollection<LogLine> logs = pipeline.apply(TextIO.read().from("gs://logs/*"));

PCollection<KV<String, Integer>> counts = logs
    .apply(ParDo.of(new ExtractEndpointFn()))  // map: extract (endpoint, 1)
    .apply(GroupByKey.create())                 // shuffle: group by endpoint
    .apply(Combine.perKey(Sum.ofIntegers()));   // reduce: sum counts

counts.apply(BigQueryIO.write().to("project:dataset.table"));

// The SAME code runs on:
//   Spark runner → batch job on existing Spark cluster
//   Flink runner → streaming with event-time windows
//   Dataflow runner → Google's managed autoscaling service
```

### Brainstorming Q: Lambda vs. Kappa Architecture

**Q: A startup is building a feature that processes user activity logs nightly for analytics AND needs real-time fraud alerts within 200ms. How do you architect this? Do you use the same system for both?**

The core tension is latency vs. throughput. Batch systems (MapReduce, Spark) are optimized for high throughput — processing terabytes efficiently by sorting, grouping, and aggregating in bulk. Streaming systems (Flink, Kafka Streams) are optimized for low latency — processing each event in milliseconds by maintaining in-memory state per key. These optimizations are fundamentally at odds: the sort-then-aggregate approach that makes batch efficient would add hundreds of milliseconds of latency per event in a streaming context.

**Lambda architecture** (the traditional approach) uses two separate systems: a "batch layer" for historical, high-accuracy analytics and a "speed layer" for real-time, approximate results. The nightly analytics would run on Spark (batch layer), computing accurate aggregates over the full day's logs. The fraud alerts would run on Flink (speed layer), processing each transaction within milliseconds and comparing against pre-computed features. Users of the analytics dashboard would see accurate batch results (12-24 hour lag). The fraud system would see real-time signals (sub-200ms). The downside of lambda: you maintain two codebases that express the same business logic — one in Spark and one in Flink. They can diverge, causing inconsistencies. Debugging is harder because "the same query" produces different results in batch vs. streaming.

**Kappa architecture** (the modern preferred approach) uses a single streaming system for everything. The idea: if your streaming system can replay historical events from the beginning (Kafka retains events for configurable durations — up to forever), then batch analytics is just "streaming over past events." Your Flink job runs 24/7 as a streaming job. For the nightly report, you run the same Flink job in "catch-up" mode, replaying the last 24 hours of events from Kafka. The fraud alert system is the same Flink job running in real-time mode. This eliminates the dual codebase problem. The practical constraint: the streaming system must be able to replay historical data efficiently (Kafka can, at ~100MB/s per partition), and the streaming job must be stateful (the Flink job maintains per-user state — recent purchases, velocity patterns — that needs to be checkpointed and restored). For a startup, I'd recommend kappa from day one if the team has Flink expertise; if not, start with lambda (Spark for batch, Kafka + simple alerting rules for fraud) and migrate to kappa as the team grows.

### Intern → Staff Progression (Part 11)

| Level | Knowledge of alternatives and decision framework |
|-------|--------------------------------------------------|
| **Intern** | "Use Spark instead of Hadoop." Cannot explain why or in what situations. |
| **L3** | Knows Spark is for iterative, Flink is for streaming. Cannot explain lambda vs. kappa architecture. |
| **L4** | Can choose between MapReduce/Spark/Flink for a given problem. Knows lambda architecture exists. |
| **L5** | Can explain the trade-offs of lambda vs. kappa. Knows the Beam model. Can reason about when SQL MPP (BigQuery) is more appropriate than Spark. |
| **L6** | Can design a complete data architecture for mixed batch+streaming requirements. Can explain WHY the unified model (Beam/Dataflow) works for both. Can identify when a seemingly streaming problem is actually batch in disguise and vice versa. |

---

## Real Incidents (Additional)

### Incident 4: 2008 Hadoop at Facebook — HDFS Namenode Single Point of Failure

Facebook was one of the first companies outside Google to deploy MapReduce at scale. By 2008, they were running a Hadoop cluster to process their growing social graph data — tracking which users were friends with which other users, what content they posted, and how they interacted. The cluster grew to several hundred machines, processing tens of terabytes of data daily.

The first major crisis: a planned maintenance window on the HDFS Namenode (the single master of the open-source GFS equivalent) turned into a 14-hour outage when the Namenode failed to restart after a JVM upgrade. The Namenode stored all filesystem metadata in memory — every file, every block, every chunk location — and persisting and reloading this metadata on restart was slow (20 minutes) and error-prone (in one case, corrupted metadata meant some files were permanently lost). During the 14-hour window, all MapReduce jobs were stuck — they could not read from or write to HDFS at all. Facebook's data warehouse was completely offline. Analytics that advertisers and product teams depended on were unavailable.

This incident directly motivated two major Hadoop improvements: (1) HDFS NameNode High Availability (NameNode HA), which replicated the Namenode to a standby using shared NFS storage, allowing failover in under 60 seconds. (2) HDFS Federation, which split the single Namenode into multiple independent Namenodes, each managing a subset of the filesystem namespace, eliminating the single-master bottleneck for very large clusters. Facebook also built their own HDFS monitoring stack (HDFS RAID for erasure coding, custom Namenode metrics) that eventually became the foundation for open-source contributions back to the Hadoop project.

The second crisis in the same 2008 period: Hadoop had no concept of rack-aware data placement. When the cluster was initially set up, HDFS placed chunk replicas randomly across all machines — without considering which machines were on the same rack. During the shuffle phase of large MapReduce jobs, the all-to-all data transfer pattern caused the top-of-rack switches to saturate, creating network hotspots that caused jobs to time out. Facebook's engineers traced the problem to rack bandwidth exhaustion and implemented rack-aware replica placement (similar to what Google's GFS already had): the first replica goes to the writer's machine, the second to a machine on a different rack, the third to a different machine on the second rack. This ensures that if one rack's switch fails, data is still accessible from the other rack.

### Incident 5: 2012 Google Transition from MapReduce to Flume/Dataflow

By 2010-2012, Google's internal MapReduce pipelines had grown to thousands of jobs — some running continuously in chains, some running on tight schedules. The limitations of raw MapReduce had become painful at this scale. The most common complaint from Google engineers: writing a complex multi-stage pipeline (parse → join → aggregate → filter → transform → output) required writing and debugging 8-10 separate MapReduce jobs, each with its own map/reduce functions, its own configuration, and its own monitoring. The jobs ran sequentially (each writing to GFS and the next reading back), meaning a 10-job pipeline did 20 GFS read/write operations even though only the first read and last write were truly necessary.

Google's response was FlumeJava (later Flume, the internal precursor to Dataflow). Flume allowed engineers to express the entire pipeline as a single graph of transformations — `PTable.parallelDo(fn).groupByKey().combineValues(fn)` — without explicitly writing map and reduce functions or managing intermediate GFS files. The Flume optimizer analyzed the computation graph and automatically fused adjacent operations: if a map step was immediately followed by another map step with no shuffle in between, Flume combined them into a single MapReduce job, eliminating the intermediate GFS write. A 10-step pipeline that previously required 8 MapReduce jobs might become 2 MapReduce jobs after Flume's optimizer ran. This fusion optimization alone reduced infrastructure costs by an estimated 30-40% for typical pipelines (30-40% fewer GFS writes, fewer MapReduce job overheads, less scheduling latency).

The deeper lesson from this transition: MapReduce's low-level API caused engineers to write suboptimal pipelines by default. When you're writing individual MapReduce jobs, you naturally chain them in the most straightforward way — one job per logical step — without thinking about job fusion or shared computation. A higher-level abstraction (Flume, Spark, Beam) can see the whole computation graph and apply optimizations that no individual engineer would implement manually. This is the same principle that makes SQL query optimizers (which reorder joins and push filters down) more efficient than manually written nested loops. The framework that sees the full computation can optimize globally; the programmer who writes one step at a time can only optimize locally.

---

## Glossary

**Input split**: A logical subdivision of the input data, typically 64MB, corresponding to one GFS chunk. Each input split becomes the input to exactly one Map task. The number of map tasks equals the number of input splits.

**Map task**: The unit of work in the map phase. A map task reads one input split, applies the user-defined map function to each record, and writes partitioned, sorted intermediate output to the local disk of the map worker machine.

**Reduce task**: The unit of work in the reduce phase. A reduce task fetches map output from all map workers (for its assigned partition), merge-sorts the fetched data, and calls the user-defined reduce function for each unique key, writing output to GFS.

**Shuffle**: The data movement phase between map and reduce. During shuffle, each reduce task fetches its partition of the map output from all map workers over the network. The shuffle is typically the network bottleneck of a MapReduce job.

**Intermediate key-value pair**: Output of the map function — a (key, value) pair written to the map worker's local disk. Intermediate key-value pairs are not the final output; they are transported via shuffle to reducers for aggregation.

**Combiner**: An optional optimization function that runs on each map machine immediately after the map phase, performing partial aggregation of intermediate key-value pairs before they are shuffled. Combiners reduce the volume of data transferred during shuffle. Must be commutative and associative to be safe.

**Partitioner**: A function that determines which reduce task receives a given intermediate key. The default partitioner is `hash(key) % num_reducers`. Custom partitioners allow control over key-to-reducer assignment — e.g., routing all URLs from the same domain to the same reducer.

**Backup task (speculative execution)**: A duplicate copy of a slow (straggler) map or reduce task, launched near the end of a job on a different worker. Whichever copy completes first — original or backup — is used. The other copy is killed. Eliminates the straggler effect on job completion time.

**Data locality**: The scheduling optimization of running a map task on the same machine (or same rack) as the GFS chunk holding that task's input data. Avoids network reads for input data. Implemented by the master's rack-aware task assignment algorithm.

**Rack-aware scheduling**: The master's three-tier policy for assigning map tasks to workers: (1) same machine as GFS chunk (local disk read, fastest), (2) same rack (intra-rack network), (3) any machine (cross-rack network, slowest). Maximizes data locality across the cluster.

**Deterministic function**: A function that always produces the same output for the same input, regardless of when or where it runs. MapReduce's fault tolerance model requires map and reduce functions to be deterministic, enabling safe re-execution of failed tasks.

**Idempotent task**: A task that can be executed multiple times with the same result as executing it once. MapReduce achieves idempotency through atomic output commits: duplicate task completions are detected and only the first commit is used.

**Merge sort (in shuffle context)**: The algorithm used by reducers to combine sorted intermediate data from multiple map workers into a single sorted stream. Each map worker produces a sorted output file; the reducer performs a K-way merge (using a min-heap) to produce a single sorted stream for the reduce function.

**SSTable (Sorted String Table)**: A file format used in Bigtable (and many other storage systems) where key-value pairs are stored in sorted key order. Map output in MapReduce is sorted by key — essentially producing SSTable-format files — enabling efficient merge operations during shuffle.

**RDD (Resilient Distributed Dataset)**: Spark's fundamental distributed data abstraction. An RDD is an immutable, partitioned collection of elements that can be reconstructed from its lineage (the sequence of transformations that created it) if a partition is lost. RDDs can be persisted in memory across operations, enabling efficient iterative algorithms.

**Beam model**: Google's unified programming model for batch and streaming, implemented in Apache Beam. Key concepts: PCollections (distributed datasets, bounded or unbounded), Transforms (ParDo for element-wise operations, GroupByKey for shuffle, Combine for aggregation), Windowing (grouping events by time), and Watermarks (tracking completeness of event-time windows for out-of-order event handling).

**Lambda architecture**: A data processing architecture that maintains two separate systems: a batch layer (Hadoop, Spark) for accurate historical computation and a speed layer (Flink, Kafka Streams) for real-time approximate computation. Results are merged from both layers. Criticized for code duplication between layers.

**Kappa architecture**: A simplification of lambda architecture that uses only a streaming system (Flink, Kafka Streams). Batch analytics are expressed as streaming jobs replaying historical events from Kafka. Eliminates the dual-codebase problem of lambda architecture at the cost of requiring the streaming system to support efficient historical replay.

**GFS chunk**: The fundamental storage unit in Google File System (GFS). Files are divided into 64MB chunks; each chunk is stored on three different ChunkServers for redundancy. MapReduce input splits are sized to match chunk size (64MB), enabling data-local map task assignment.

**Task slot**: A unit of computational capacity on a worker machine — the ability to run one map or reduce task concurrently. A machine with 4 CPUs might offer 4 map task slots and 2 reduce task slots. The master assigns tasks to machines by allocating their task slots. Total cluster capacity = sum of all task slots.

---

*Chapter 85 complete. Next in the Google Foundational Systems series: Chapter 86 — Chubby (distributed lock service). Pairs with Ch41b (overview of all Google systems) and Ch83 (GFS, which also uses Chubby for master election).*
