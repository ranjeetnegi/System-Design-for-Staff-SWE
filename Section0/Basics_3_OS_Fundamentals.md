# Basics Chapter 3: OS Fundamentals — Process, Thread, Memory, CPU, and Disk

---

# Introduction

Every server you deploy—every container, every VM, every microservice—runs on an operating system. The OS manages **processes**, **threads**, **memory (RAM)**, **CPU**, and **disk I/O**. At first glance, these feel like Computer Science 101. And yet, Staff-level system design interviews repeatedly surface a gap: candidates who can architect distributed systems struggle to articulate *why* Java services consume more memory than Go services, *why* their p99 latency shows periodic spikes, or *when* to add CPU versus when to optimize I/O.

This chapter grounds you in operating system fundamentals from a **server and system design perspective**. We don't aim to make you an OS kernel engineer. We aim to give you the mental models to reason about capacity, bottlenecks, and trade-offs when designing and operating production systems. By the end, you'll understand how process and thread models shape concurrency strategies, why memory and disk hierarchies dictate caching decisions, and when CPU—often the least of your concerns—actually becomes the bottleneck.

---

# Quick Visual: The Four Pillars

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    OS FUNDAMENTALS: WHERE TIME IS SPENT                     │
│                                                                             │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│   │   PROCESS   │  │   MEMORY    │  │     CPU     │  │   DISK I/O  │       │
│   │   & THREAD  │  │    (RAM)    │  │             │  │             │       │
│   │             │  │             │  │             │  │             │       │
│   │ Concurrency │  │ ~100 ns     │  │ Execute     │  │ ~100 µs-10ms│       │
│   │ model       │  │ access      │  │ instructions│  │ access      │       │
│   │ C10K, pools │  │ Heap/Stack   │  │ I/O vs      │  │ HDD vs SSD  │       │
│   │             │  │ GC pauses    │  │ CPU-bound   │  │ WAL, B-tree │       │
│   └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘       │
│                                                                             │
│   Most web servers: I/O-bound (waiting on DB, network). CPU often idle.   │
│   Bottleneck varies by workload: profile first, then optimize.             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 1: Processes and Threads

## Why OS Fundamentals Matter for System Design

At first glance, process and thread models seem like implementation details. "We just run our service; the OS handles it." But the choices your runtime makes—thread-per-request vs event loop, blocking vs non-blocking I/O, stack size per unit of concurrency—directly affect how many requests one instance can handle, how much memory it uses, and where your bottlenecks appear. When you're designing for 10K QPS or 100K concurrent connections, these fundamentals become the constraint. Staff engineers understand them because they determine the shape of every scaling decision.

## A Process Is an Instance of a Running Program with Its Own Memory Space

A **process** is the OS's representation of a running program. When you start your API server, the OS creates a process. That process gets:

- **Its own virtual address space** — memory that is isolated from other processes. Process A cannot directly read or write Process B's memory.
- **Its own file descriptor table** — handles to open files, sockets, pipes.
- **Its own resource limits** — CPU time, memory limits, number of open files.

Think of a process as a **kitchen**: its own stove, fridge, and counter. If one kitchen catches fire, the others might not notice. Isolation is the key benefit. When a process crashes, it typically doesn't take down other processes.

## A Thread Is a Lightweight Execution Unit Within a Process, Sharing Memory

A **thread** is a unit of execution *inside* a process. Multiple threads share the same process's memory space—the same heap, the same code, the same global variables. They each have their own stack for local variables and call frames.

Think of threads as **chefs in the same kitchen**: they share the stove, fridge, and counter. They can work in parallel. But they can also conflict—two chefs grabbing the same ingredient at once. That's a race condition. Threads require coordination (locks, mutexes) when accessing shared data.

| Aspect | Process | Thread |
|--------|---------|--------|
| **Memory** | Isolated (own address space) | Shared (same heap, same globals) |
| **Creation cost** | High (OS allocates new address space) | Lower (shared resources) |
| **Communication** | IPC (pipes, sockets, shared memory) | Direct (shared variables) |
| **Crash isolation** | One process crash ≠ others | One thread crash often kills process |
| **Typical use** | Isolation, security, fault containment | Parallelism within one program |

## Multi-Processing vs Multi-Threading: Trade-Offs

**Multi-processing** (e.g., one process per request, or multiple worker processes): Strong isolation. One process crash doesn't kill others. Good for security (one compromised process doesn't leak another's data). But: high overhead. Each process needs its own memory. Creating a process is expensive. Context switching between processes is heavier than between threads.

**Multi-threading** (e.g., thread pool serving requests): Lower overhead. Threads share memory, so you can have many more threads than processes for the same RAM. But: no isolation. A bug in one thread can corrupt shared state and crash the whole process. Race conditions. Debugging is harder.

**Staff-Level Insight**: The choice between processes and threads is often dictated by your language and runtime. Java, C#, Go use threads (or goroutines, which are lightweight threads). Python's GIL makes true parallelism with threads limited for CPU-bound work—multiprocessing is often used instead. Node.js uses a single-threaded event loop. Understanding your runtime's concurrency model is essential for capacity planning.

## Context Switching: The Hidden Cost

When the CPU switches from one thread (or process) to another, it must:

1. **Save the current thread's state** — registers, program counter, stack pointer.
2. **Restore the new thread's state** — load its registers, program counter.
3. **Invalidate caches** — the new thread may need different data. L1/L2/L3 caches may have been holding the old thread's working set. Cache misses spike.

This is **context switching**. It has real cost: typically **1–10 microseconds** per switch, plus cache effects that can add **10–100+ microseconds** of indirect cost. At 10,000 context switches per second, you might spend 10–100 ms per second just switching—10–100% of a core. Too many threads → thrashing → the CPU spends more time switching than working.

```
    CONTEXT SWITCH OVERHEAD (simplified)

    Thread A running  ──►  [SAVE state] ──► [RESTORE Thread B state] ──► Thread B runs
                                │
                                ├── Register save/restore: ~1 µs
                                ├── Cache invalidation: variable (10-100 µs possible)
                                └── Scheduler overhead: ~1 µs

    More threads than cores = more context switches = more overhead
```

## Why This Matters for Servers: Request Handling Models

Every incoming HTTP request must be handled. Two dominant models:

### Thread-per-Request (e.g., Java/Spring, traditional servlet containers)

```
    ┌─────────────────────────────────────────────────────────────────┐
    │                    THREAD-PER-REQUEST MODEL                     │
    │                                                                 │
    │   Request 1 ──► Thread 1 ──► [Process] ──► Response 1           │
    │   Request 2 ──► Thread 2 ──► [Process] ──► Response 2           │
    │   Request 3 ──► Thread 3 ──► [Process] ──► Response 3           │
    │       ...                                                       │
    │   Request N ──► Thread N ──► [Process] ──► Response N           │
    │                                                                 │
    │   Each request gets a dedicated thread. Thread blocks on I/O.  │
    │   Thread pool size = max concurrent requests (e.g., 200-500).  │
    └─────────────────────────────────────────────────────────────────┘
```

- One thread per request. Thread blocks while waiting for DB, network, etc.
- **Pros**: Simple mental model. Each request has its own stack. Easy to debug (thread dumps show request state).
- **Cons**: Each thread has stack memory (~1 MB default in Java). 1000 threads ≈ 1 GB just for stacks. Thread creation and context switching overhead. Limited concurrency by thread count.

### Event-Loop Model (e.g., Node.js, Nginx, async Python)

```
    ┌─────────────────────────────────────────────────────────────────┐
    │                    EVENT-LOOP MODEL                             │
    │                                                                 │
    │   Single thread. Non-blocking I/O.                              │
    │                                                                 │
    │   Request 1 ──► [Register callback] ──► Yield (wait for I/O)     │
    │   Request 2 ──► [Register callback] ──► Yield (wait for I/O)     │
    │   Request 3 ──► [Register callback] ──► Yield (wait for I/O)    │
    │       ...                                                       │
    │   [I/O ready] ──► Resume Request 1 ──► Response 1               │
    │   [I/O ready] ──► Resume Request 2 ──► Response 2                │
    │                                                                 │
    │   One thread handles 10K+ concurrent connections via async I/O.  │
    └─────────────────────────────────────────────────────────────────┘
```

- Single thread (or few threads) + non-blocking I/O. When a request waits for DB, the thread serves other requests. Callbacks or promises resume when I/O completes.
- **Pros**: Very high concurrency with low memory. 10,000 connections on one thread is feasible. No thread context switching.
- **Cons**: CPU-bound work blocks the whole loop. Must not do heavy computation on the main thread. Callback hell or async/await complexity.

### Goroutines (Go): Lightweight Threads

Go uses **goroutines** — user-space threads (M:N scheduling). Thousands of goroutines map onto a small number of OS threads. Each goroutine has a small stack (~2 KB initially, grows as needed). Blocking a goroutine doesn't block the whole process; the scheduler runs other goroutines.

- **Why Go services use less memory than Java**: Goroutines are lightweight. A Go service might run 10,000 goroutines with ~20–50 MB stack total. A Java service with 1,000 threads might use 1 GB just for thread stacks. Plus, Go's GC is designed for low latency; Java's GC can have larger heap and longer pauses.

## Process Isolation → Containers → Microservices

**Process isolation** is the foundation of **containers**. A container is essentially a process (or group of processes) with:

- Its own view of the filesystem (via namespaces and union mounts).
- Its own network namespace.
- Resource limits (cgroups: CPU, memory).

Containers provide process-level isolation without the overhead of full VMs. Each microservice runs in its own container = its own process (or process group). Crash isolation: one service OOM-killed doesn't kill others. Deployment isolation: you can scale or restart one service independently.

**Staff-Level Insight**: The progression from "one process per server" to "many containers per host" is an organizational and isolation story as much as a technical one. Containers make it natural to deploy one service per container, which aligns with team ownership and independent scaling.

### From Monolith to Microservices: The Process Connection

A **monolith** runs as one (or few) processes. All components share the same memory. A bug in one module can crash the whole process. Scaling means replicating the entire process—you can't scale "just the auth part."

**Microservices** run as many small processes (or containers). Each service is isolated. A crash in the auth service doesn't kill the checkout service. You scale each service independently based on its load. The cost: more processes, more network hops, more operational complexity. The benefit: fault isolation, independent scaling, team ownership boundaries.

The process boundary is the foundation of this trade-off. Staff engineers design service boundaries so that each process has a clear, cohesive responsibility—and so that communication across boundaries (network, serialization, failure handling) is explicit and manageable.

## The C10K Problem: Handling 10,000 Concurrent Connections

The **C10K problem** (circa 1999): how do you design a server to handle 10,000 concurrent connections?

- **Thread-per-connection**: 10,000 threads. On old systems: 10,000 × 1 MB stack = 10 GB. Impossible. Context switching nightmare.
- **Solution**: Event-driven, non-blocking I/O. `select`, `poll`, `epoll` (Linux), `kqueue` (BSD). One thread monitors many file descriptors. When any is ready, process it. This is how Nginx, Node.js, and modern async runtimes achieve high concurrency.

Today we talk about **C100K** and **C1M** — same idea, bigger numbers. The solutions: kernel tuning (e.g., `net.core.somaxconn`), efficient event loops, connection pooling, and careful memory management.

## ASCII Diagram: Process with Threads vs Event Loop

```
    PROCESS WITH THREADS (e.g., Java Tomcat)          EVENT LOOP (e.g., Node.js)

    ┌─────────────────────────────────────────┐       ┌─────────────────────────────────────────┐
    │              PROCESS                     │       │              PROCESS                     │
    │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐        │       │  ┌─────────────────────────────────────┐ │
    │  │Thd 1│ │Thd 2│ │Thd 3│ │Thd N│        │       │  │      SINGLE THREAD + EVENT LOOP     │ │
    │  │Req A│ │Req B│ │Req C│ │ ... │        │       │  │                                     │ │
    │  └──┬──┘ └──┬──┘ └──┬──┘ └─────┘        │       │  │  Req A ──► [wait I/O] ──► callback  │ │
    │     │       │       │                    │       │  │  Req B ──► [wait I/O] ──► callback  │ │
    │     └───────┼───────┘                    │       │  │  Req C ──► [wait I/O] ──► callback  │ │
    │         SHARED HEAP                       │       │  │  ... 10K+ requests                  │ │
    │         (connection pool, cache)         │       │  └─────────────────────────────────────┘ │
    └─────────────────────────────────────────┘       └─────────────────────────────────────────┘

    N threads = N concurrent blocking operations       1 thread = many concurrent non-blocking ops
    Memory: ~1 MB/thread                               Memory: ~few KB per connection (buffers)
```

## Green Threads, Coroutines, and User-Space Scheduling

**Green threads** (or *user-space threads*) are threads scheduled by the runtime or library, not the OS. The OS sees one thread; the runtime multiplexes many logical threads onto it. **Coroutines** (async/await, goroutines, Kotlin coroutines) are a form of this: lightweight, cooperative, often stackful or stackless.

**Why they matter**: OS threads have ~1 MB stack. Creating 10,000 OS threads = 10 GB. Green threads or coroutines might use 2–8 KB each. 10,000 coroutines = 20–80 MB. You can have orders of magnitude more logical concurrency without exhausting memory. Go's goroutines, Erlang's processes, and async/await in Rust/JS/Python follow this pattern.

**Staff-Level Insight**: When comparing languages for a high-concurrency workload, ask: "How many logical concurrent operations can one process handle?" Go and Erlang excel because their runtime schedules millions of lightweight units. Java's threads are OS threads; you're limited by stack size and context-switch overhead unless you use virtual threads (Project Loom).

### Coroutines and Async/Await: The Modern Alternative

**Async/await** (JavaScript, Python, C#, Rust) and **coroutines** (Kotlin) provide a programming model where you write sequential-looking code that yields at I/O points. The runtime schedules many such "coroutines" on a small thread pool. When one awaits a DB call, the thread serves another coroutine. Effectively: cooperative multitasking with a familiar syntax.

**Comparison**: Thread-per-request blocks a full OS thread. Coroutines/async share threads. One thread can run thousands of logical "tasks." Memory per task: kilobytes, not megabytes. The trade-off: you must use non-blocking I/O everywhere. Blocking calls (e.g., synchronous DB driver) defeat the purpose—they block the whole thread.

## Practical Example: Thread Pool Sizing

**Rule of thumb for I/O-bound**: `threads ≈ (target latency / DB latency) × target QPS`. If DB p99 is 50 ms and you want 2K QPS with 100 ms target latency: you need enough threads to have ~100 concurrent in-flight requests. 100 ms / 50 ms ≈ 2 "rounds" of DB calls per request, so rough order 100–200 threads. Exact formula depends on your request pattern.

**Rule of thumb for CPU-bound**: `threads ≈ number of CPU cores` (or slightly more with hyper-threading). More threads than cores just adds context switching.

**Why This Matters at Scale**: Mis-sized thread pools cause either (a) requests queuing and timing out, or (b) excessive memory and context switching. Staff engineers tune based on measured latency and load, not guesses.

## L5 vs L6: Concurrency Model

| Aspect | L5 Thinking | L6 Thinking |
|--------|-------------|-------------|
| **Concurrency** | "We use a thread pool of 200" | "We use 200 threads because our p99 DB latency is 50ms; 200 × 20 QPS/thread ≈ 4K QPS. Beyond that we need more instances or async." |
| **Blocking I/O** | "Threads block on DB, that's fine" | "Blocking threads limit our max QPS per instance. At 500 threads we're at 2GB stack; we're considering async client" |
| **Memory** | "Our Java service uses 4GB" | "4GB = 2GB heap + 500 threads × 1MB stack + metaspace. Go equivalent would be ~512MB for same load" |
| **Scaling** | "Add more instances" | "Add instances, but also: connection pooling, async I/O, or switch runtime if CPU-bound" |

---

# Part 2: Memory (RAM) and Why It Matters for Servers

## RAM = Fast, Volatile Storage

**RAM (Random Access Memory)** is where your application's code and data live while running. It's orders of magnitude faster than disk. It's also **volatile** — when power is lost, RAM contents are gone. That's why we persist important data to disk.

Typical latency: **~100 nanoseconds** for a RAM access. Compare to **~100 microseconds** for SSD and **~10 milliseconds** for HDD. The gap is 1,000–100,000x.

## Heap vs Stack Memory

- **Stack**: Used for function call frames, local variables. Grows and shrinks with calls and returns. Fast. Limited size (often 1–8 MB per thread). Stack overflow = recursion too deep or too large locals.
- **Heap**: Used for dynamically allocated data (objects, arrays, caches). Shared across threads. Managed manually (C/C++) or by a garbage collector (Java, Go, Node with V8). Can grow to gigabytes.

For servers: most of your memory lives on the heap — cached data, connection buffers, request/response objects, in-memory indexes.

## Why Memory Matters for Servers

- **More memory = more data cached in-process** — reduce DB and disk reads.
- **More memory = more concurrent connections** — each connection has buffers (e.g., 4–64 KB per connection for TCP). 10,000 connections × 32 KB = 320 MB just for socket buffers.
- **Larger working sets** — if your app frequently touches 8 GB of data, you want at least 8–16 GB RAM to avoid swapping.

## Memory Limits per Container/VM

Typical ranges:

| Workload | Typical RAM | Notes |
|----------|-------------|-------|
| Stateless API server | 512 MB – 2 GB | Light footprint, connection pools |
| API server (Java/Spring) | 2 – 8 GB | JVM heap + metaspace + thread stacks |
| Database (PostgreSQL, MySQL) | 16 – 64 GB | Buffer pool, query cache |
| In-memory cache (Redis) | 4 – 256 GB | Data lives entirely in RAM |
| ML inference | 8 – 64 GB | Model weights in RAM |

**Staff-Level Insight**: Sizing is workload-dependent. A stateless Go API might run in 256 MB. The same logic in Java might need 2 GB. Know your runtime's memory profile.

## Garbage Collection (GC): Automatic Memory Management

Languages like Java, Go, C#, Node (V8) use **garbage collection** — the runtime automatically reclaims memory that is no longer reachable. No manual `free()`.

**GC pauses** = times when the GC stops your application to scan and collect. These cause **latency spikes**. In Java, a full GC can pause the application for 100 ms – 1+ seconds. Your p99 latency jumps. Users see timeouts.

**Why Java apps have periodic latency hiccups**: The JVM's GC (e.g., G1GC, ZGC) runs periodically. Even with low-pause collectors, there are moments when the application is paused. ZGC and Shenandoah aim for sub-millisecond pauses; older collectors (e.g., Parallel GC) can pause for hundreds of milliseconds.

**Mitigation**: Tune heap size. Use low-pause collectors. Reduce allocation rate. Offload work to background threads. Consider Go or Rust for latency-sensitive services if GC pauses are unacceptable.

### GC Collectors: A Quick Reference

| Collector | Pause Goal | Throughput | When to Use |
|-----------|------------|------------|-------------|
| **Parallel / Throughput** | Long pauses (100ms+) | High | Batch jobs, non-latency-sensitive |
| **G1GC** | Reasonable (10-50ms) | Good | Default for many Java 11+ apps |
| **ZGC / Shenandoah** | Sub-ms | Slightly lower | Latency-sensitive, large heaps |
| **Go GC** | Sub-ms | Good | Low-latency by design |
| **V8 (Node)** | Incremental | Good | Event loop helps hide pauses |

**Staff-Level Insight**: If your p99 latency has a "sawtooth" pattern—smooth, then a spike, then smooth—you're likely seeing GC. The spike is the pause. Profile with GC logs. If pauses are too long, switch collector or reduce allocation.

## Memory Leaks: Allocated but Never Freed

A **memory leak** occurs when memory is allocated but never released. The process's memory usage grows over time. Eventually: **OOM (Out Of Memory) kill**. The OS or container runtime kills the process.

Common causes in servers:

- Unbounded caches that never evict.
- Event listeners or callbacks that are never removed.
- Growing collections (lists, maps) that accumulate entries.
- Thread-local storage that grows per request.

**Staff-Level Insight**: In managed runtimes, "leaks" are often "unintended retention" — you're holding references to objects you don't need. Profiling (heap dumps, `pprof`) reveals what's retaining memory. Fix: clear caches, remove listeners, cap collection sizes.

## Redis Is Fast Because All Data Is in RAM

Redis holds its dataset entirely in RAM. Every read is a memory access — no disk. That's why Redis can serve 100,000+ ops/sec with sub-millisecond latency.

**Trade-off**: Limited by RAM size. Redis clusters shard data across nodes to scale. Cost: RAM is more expensive than disk. Durability: by default, Redis can lose data on crash. Persistence (RDB, AOF) trades some performance for durability.

## Off-Heap vs On-Heap in JVM Applications

- **On-heap**: Objects in the JVM heap. Managed by GC. Subject to GC pauses.
- **Off-heap**: Memory allocated outside the JVM heap (e.g., via `ByteBuffer.allocateDirect()` or native libraries). Not scanned by GC. No GC pause from this memory. Used for large caches, buffers, ML model weights.

**Trade-off**: Off-heap reduces GC pressure but you must manage it manually (or use libraries that do). Risk of native memory leaks.

## NUMA: Memory Locality on Multi-Socket Servers

On machines with multiple CPU sockets, memory is **NUMA (Non-Uniform Memory Access)**. Memory attached to the CPU you're running on is faster to access than memory attached to another socket. Accessing remote NUMA memory can be ~1.5–2x slower.

**Why it matters**: For latency-sensitive, high-throughput services, binding threads to specific cores and ensuring they allocate from local NUMA nodes can reduce latency variance. Most applications don't tune for this; databases and high-frequency trading systems do.

## Memory Hierarchy: Latency Numbers

```
    MEMORY HIERARCHY (approximate latency, single access)

    Registers     ████                           ~0.3 ns (1 cycle)
    L1 cache      ██████                         ~1 ns
    L2 cache      ██████████                     ~3 ns
    L3 cache      ████████████████               ~12 ns
    RAM           ████████████████████████████   ~100 ns
    SSD           (very long bar)                 ~100 µs   (1,000x slower than RAM)
    HDD           (extremely long bar)            ~10 ms    (100,000x slower than RAM)

    Each level is roughly 3-10x slower than the one above.
    Caching is about keeping data as high in this hierarchy as possible.
```

## How Much RAM Does a Typical Web Server Need?

| Server Type | RAM | Rationale |
|-------------|-----|-----------|
| Stateless API (Go, Node) | 512 MB – 2 GB | Code, connection buffers, minimal in-process cache |
| Stateless API (Java) | 2 – 8 GB | JVM heap, metaspace, thread stacks (1 MB × threads) |
| Database (Postgres, MySQL) | 16 – 64 GB | Buffer pool caches disk pages; more RAM = fewer disk reads |
| Redis / Memcached | 4 – 256 GB | Entire dataset in RAM |
| Search engine (Elasticsearch) | 32 – 256 GB | Index segments, field data cache |

**Why This Matters at Scale**: Under-provisioning RAM leads to swapping (thrashing) or OOM kills. Over-provisioning wastes money. Staff engineers profile memory usage, set limits (containers, JVM `-Xmx`), and monitor for growth (leaks) and limits (headroom).

### Debugging Memory Issues: A Staff-Level Checklist

When memory grows or OOM occurs:

1. **Heap dump analysis**: Capture heap dump at high watermark. Use Eclipse MAT or similar to find retained objects. Look for unintended references (listeners, caches, thread locals).
2. **GC logs**: Enable GC logging. Check pause times, frequency, allocation rate. Long pauses = latency spikes; high allocation = GC churn.
3. **Container limits**: Ensure `-Xmx` is below container limit (e.g., leave 256–512 MB for metaspace, threads, native). OOM kill often means process exceeded cgroup limit.
4. **Native memory**: JVM uses native memory for threads, GC, direct buffers. `pmap` or `Native Memory Tracking` can show leaks outside heap.

### Real-World Scenario: Java vs Go Memory

A team migrated a stateless API from Java (Spring Boot) to Go. Same functionality, same load. Java: 4 GB per pod, 8 pods. Go: 512 MB per pod, 4 pods. Total: 32 GB → 2 GB. The difference: (1) Go goroutines use ~2 KB stack vs Java's 1 MB; (2) Go's GC has lower overhead; (3) Go has no JIT warmup or metaspace. For greenfield services where memory density matters, the language choice affects infrastructure cost directly.

---

# Part 3: CPU and When It Becomes a Bottleneck

## CPU Executes Instructions

The **CPU (Central Processing Unit)** executes the instructions of your program. Fetch, decode, execute. It's the "brain" of the machine. For many servers, it's also the resource that's *least often* the bottleneck.

## Most Web Servers Are I/O-Bound, Not CPU-Bound

**I/O-bound**: The server spends most of its time waiting—for the database, for the network, for disk. The CPU is often idle. Adding more CPU cores doesn't help much. Fix: faster I/O, connection pooling, caching, async I/O.

**CPU-bound**: The server spends most of its time executing instructions. Encoding video, running ML inference, compressing data, doing heavy computation. Adding more CPU cores (or faster cores) helps.

| Workload Type | Example | Bottleneck | Mitigation |
|---------------|---------|------------|------------|
| **I/O-bound** | API server waiting for DB | DB latency, network | Connection pool, cache, async |
| **I/O-bound** | Web server serving static files | Disk, network | CDN, in-memory cache |
| **CPU-bound** | Video transcoding | CPU | More cores, GPU, offload to workers |
| **CPU-bound** | ML inference | CPU/GPU | More cores, specialized HW |
| **CPU-bound** | Encryption (TLS) | CPU | Hardware crypto, offload |

## CPU-Bound Workloads

- **Video transcoding**: Decode, transform, encode. Heavy math.
- **Image processing**: Resize, compress, filters.
- **ML inference**: Matrix multiplication, neural network forward pass.
- **Encryption/decryption**: TLS termination, bulk crypto.
- **Compression**: gzip, brotli, snappy.

## I/O-Bound Workloads

- **API servers**: Wait for DB query (often 1–50 ms). CPU does a few microseconds of work.
- **Web servers**: Wait for disk or upstream. nginx serving files spends most time waiting.
- **Proxy/load balancer**: Waiting for backend response.

**Staff-Level Insight**: Before adding CPU, ask: "Is our CPU actually busy?" If `top` shows 10% CPU and high latency, the bottleneck is elsewhere—likely I/O.

## CPU Cores: How Many Do You Have?

Modern servers: **8 – 96 cores** (and more for specialized instances). Each core can run one thread at a time (ignoring hyper-threading). More cores = more parallel work.

**Hyper-threading** (Intel) / **SMT** (AMD): Each physical core presents 2 logical cores. Helps when threads often wait (cache miss, branch mispredict). Typically 10–30% throughput improvement, not 2x.

**Not all applications use all cores efficiently**: A single-threaded process uses one core. A process with a thread pool of 8 threads on a 64-core machine underutilizes the CPU. Design for parallelism—or accept that you're leaving capacity on the table.

## CPU Throttling in Containers

Containers use **cgroups** to limit CPU. You can specify:

- **CPU shares** (relative weight)
- **CPU quota** (e.g., 0.5 CPU = 50% of one core)
- **CPU set** (pin to specific cores)

If your container is throttled, it may show low CPU usage (because it's capped) but still have high latency—the process is being slowed by the kernel. Check for throttle counters in `container_spec` metrics.

## When CPU Becomes the Bottleneck at Staff Level

Even "I/O-bound" services can hit CPU limits in specific places:

| Scenario | Why CPU Matters |
|----------|-----------------|
| **Serialization** | JSON encode/decode is CPU-heavy. Protobuf is faster. At high QPS, serialization can dominate. |
| **TLS termination** | Crypto is CPU-intensive. Terminating TLS at the load balancer vs application server changes where CPU is spent. |
| **Compression** | gzip/brotli for responses. High QPS + large responses = CPU-bound. |
| **Regex, parsing** | Complex regex or XML/HTML parsing. Can spike CPU. |
| **Logging** | Excessive logging, especially with serialization. |

## ASCII Diagram: CPU-Bound vs I/O-Bound

```
    CPU-BOUND REQUEST                         I/O-BOUND REQUEST

    ┌─────────────┐                           ┌─────────────┐
    │   Client    │                           │   Client    │
    └──────┬──────┘                           └──────┬──────┘
           │                                         │
           ▼                                         ▼
    ┌─────────────┐                           ┌─────────────┐
    │   Server    │                           │   Server    │
    │             │                           │             │
    │  ████████   │  CPU busy 90%              │  ██         │  CPU busy 10%
    │  (compute)  │                           │  (wait)     │
    │             │                           │      │      │
    └─────────────┘                           └──────┼──────┘
           │                                         │
           │  Response                               │  DB/Network
           ▼                                         ▼
    [Done quickly if                               ┌─────────────┐
     enough cores]                                 │  Database   │
                                                  └──────┬──────┘
                                                         │
                                                  [Wait dominates;
                                                   more CPUs don't help]
```

### Profiling CPU: What Staff Engineers Actually Do

- **Sampling profilers**: `perf`, `pprof`, `async-profiler`. Sample the call stack every N ms. Find where CPU time is spent. Don't guess—measure.
- **Flame graphs**: Visualize profiler output. Wide bars = hot code paths. Often reveals serialization, regex, or logging as the culprit.
- **CPU throttling detection**: In containers, `cpu_throttled` or similar metrics. If throttled often, you're capped; add CPU quota or reduce load.

### When "I/O-Bound" Services Become CPU-Bound

An API that mostly waits on DB can still hit CPU limits if:

- **JSON parsing**: Parsing 100 KB request bodies at 10K QPS = significant CPU.
- **Compression**: Enabling gzip for 50 KB responses at 5K QPS can saturate a core.
- **TLS**: If TLS is terminated on the app server, crypto consumes CPU. Offload to load balancer.
- **Logging**: Structured logging with serialization (e.g., JSON logs) at high QPS adds up.

**Mitigation**: Profile. Swap JSON for protobuf. Offload compression or TLS. Reduce log volume or use async logging.

## L5 vs L6: CPU and I/O

| Aspect | L5 Thinking | L6 Thinking |
|--------|-------------|-------------|
| **Slowness** | "Add more CPU" | "Profile first. If CPU < 50%, we're I/O-bound. Optimize DB, add cache, connection pool." |
| **Scale** | "We need 16 cores" | "We're I/O-bound; 4 cores per instance is enough. Scale horizontally. Save cost." |
| **Serialization** | "We use JSON" | "At 50K QPS, JSON is 20% of CPU. Evaluating protobuf or MessagePack" |
| **TLS** | "HTTPS is on" | "TLS termination at LB vs app: LB offloads crypto from app servers" |

---

# Part 4: Disk I/O and Why It's Slow

## HDD vs SSD: The Performance Gap

**HDD (Hard Disk Drive)**: Mechanical. Spinning platters, moving read/write heads. 

- **Sequential reads**: ~100–200 MB/s
- **Random reads**: ~100–200 IOPS (0.1–0.2 MB/s for 4 KB reads)
- **Latency**: ~5–10 ms per random I/O

**SSD (Solid State Drive)**: No moving parts. Electronic.

- **Sequential reads**: ~500 MB/s – 3 GB/s (NVMe)
- **Random reads**: ~100,000 – 500,000 IOPS (NVMe)
- **Latency**: ~100 µs – 1 ms

**The gap**: SSD is 100–1000x faster for random I/O. For databases (random reads), HDD is often the bottleneck. SSD changes the game.

## The Massive Hierarchy: RAM vs SSD vs HDD

| Storage | Latency | Throughput | Relative |
|---------|---------|------------|----------|
| **RAM** | ~100 ns | 10–50 GB/s | 1x |
| **SSD (NVMe)** | ~100 µs | 1–3 GB/s | ~1,000x slower than RAM |
| **SSD (SATA)** | ~100 µs | 500 MB/s | ~1,000x slower |
| **HDD** | ~10 ms | 100–200 MB/s seq, 0.1 MB/s random | ~100,000x slower than RAM |

**Why this matters**: Caching exists because of this gap. Keep hot data in RAM. Use SSD for warm data. Use HDD (or object storage) for cold data.

## Why Databases Are I/O-Bound

Databases read and write pages (e.g., 8–16 KB) to/from disk. A query might need to read many pages (index traversals, table scans). Each disk read takes 100 µs – 10 ms. A query touching 100 disk pages: 10 ms – 1 second, just for I/O. The CPU does minimal work per page.

**Buffer pool / page cache**: Databases keep frequently accessed pages in RAM. A cache hit = no disk I/O. Cache miss = disk read. More RAM = larger buffer pool = fewer disk reads = faster queries.

## B-Tree Indexes Minimize Disk Reads

A **B-tree** keeps data sorted. For 1 billion rows, a B-tree of order 100 might have depth 3–4. Finding a row by primary key = 3–4 disk reads (or cache hits). Without an index: full table scan = millions of reads.

**Staff-Level Insight**: Index design directly affects disk I/O. Poor indexing = excessive random reads = slow queries. Good indexing = few reads per query.

## WAL (Write-Ahead Log): Sequential Writes Are Fast

**Random writes** on HDD are very slow (seek time for each write). **Sequential writes** are much faster (no seek, just stream).

Databases use a **Write-Ahead Log (WAL)**: before modifying a page in place, append the change to a log file. Sequential append is fast. Later, the log is replayed or merged. This pattern—sequential log, random reads for recovery—is fundamental to many storage systems.

**Why WAL works**: On HDD, random write might be 100 IOPS (10 ms each). Sequential write can be 200 MB/s. Writing 1 MB sequentially: 5 ms. Writing 1 MB as 256 random 4 KB writes: 2.5 seconds. The WAL batches changes into a sequential stream. During recovery, the log is replayed in order—sequential reads. This is why databases can sustain high write throughput even on mechanical disks: they convert random writes into sequential ones.

### Understanding IOPS vs Throughput

**IOPS** (I/O operations per second) measures how many discrete read/write operations you can do. For small random reads (4 KB), IOPS is the limit. 1000 IOPS × 4 KB = 4 MB/s.

**Throughput** (MB/s or GB/s) measures how much data flows. For sequential reads, throughput is the limit. One big sequential read can achieve 500 MB/s on SSD.

**Why both matter**: A workload that does 10K random 4 KB reads/sec needs 10K IOPS. A workload that streams one 1 GB file needs high throughput. EBS gp3 might give you 3,000 IOPS and 125 MB/s. If your DB does 5K random reads/sec, you're IOPS-bound. If it does large sequential scans, you might be throughput-bound.

## Disk I/O in the Cloud

| Storage Type | Example | Performance | Use Case |
|--------------|---------|-------------|----------|
| **EBS (network-attached)** | AWS EBS gp3, io2 | 3–256K IOPS, 125–1000 MB/s | Databases, boot volumes |
| **Instance store (local SSD)** | AWS Nitro SSD | 100K–1M IOPS, 1–10 GB/s | Ephemeral, cache, temp data |
| **Object storage** | S3, GCS | High throughput, high latency (100–500 ms first byte) | Large files, backups, archives |

**EBS** is network-attached: traffic goes over the network. Slight latency and throughput limits vs local SSD. **Instance store** is physically attached: faster, but data is lost when instance stops. **S3** is optimized for large objects, not random small reads.

## RAID: Combining Disks

**RAID** combines multiple disks for:

- **Performance**: Striping (RAID 0) spreads I/O across disks. 4 disks ≈ 4x throughput.
- **Redundancy**: Mirroring (RAID 1) or parity (RAID 5, 6) survive disk failures.

Trade-offs: RAID 0 = no redundancy. RAID 5/6 = write penalty (parity calculation). In cloud, you often use managed storage (EBS, managed DB) instead of raw RAID.

## Why This Matters at Staff Level: Choosing Storage

| Decision | Impact |
|----------|--------|
| **Database on HDD vs SSD** | SSD can be 100x faster for random I/O. Often worth the cost. |
| **EBS vs instance store** | EBS persists. Instance store is faster but ephemeral. |
| **S3 for frequently accessed data** | S3 has high first-byte latency. Use for infrequent access, or cache in front. |
| **RAID vs single disk** | RAID for redundancy and sometimes throughput. Cloud often abstracts this. |

## ASCII Diagram: Storage Hierarchy with Numbers

```
    STORAGE HIERARCHY: Latency and Throughput

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  TIER        │  TYPICAL LATENCY   │  TYPICAL THROUGHPUT  │  COST        │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  RAM         │  ~100 ns          │  10-50 GB/s           │  $$/GB        │
    │  NVMe SSD    │  ~100 µs          │  1-3 GB/s seq        │  $/GB         │
    │  SATA SSD    │  ~100 µs          │  500 MB/s             │  $/GB         │
    │  HDD         │  ~10 ms           │  100 MB/s seq         │  ¢/GB         │
    │  Object      │  100-500 ms       │  High (bulk)          │  ¢/GB         │
    └─────────────────────────────────────────────────────────────────────────┘

    Rule: Keep hot data as high as possible. Cold data can be lower.
```

## Sequential vs Random I/O: Why It Matters

**Sequential I/O**: Reading or writing contiguous blocks. Disk head moves in one direction. HDD: ~100–200 MB/s. SSD: 500 MB/s – 3 GB/s. Very efficient.

**Random I/O**: Reading/writing non-contiguous blocks. Each operation may require a seek (HDD) or a new flash page (SSD). HDD: ~100–200 IOPS (terrible). SSD: 100K+ IOPS (good).

**Why databases care**: B-tree lookups cause random reads. Full table scans cause sequential reads. Index design and query patterns determine which dominates. OLTP workloads are often random; analytics (scanning large tables) is sequential. Choosing HDD vs SSD depends on this mix.

### Cloud Storage Tiers: When to Use What

| Use Case | Recommendation | Rationale |
|----------|-----------------|------------|
| Database data directory | EBS gp3 or io2 | Need consistent IOPS, low latency, persistence |
| Redis / Memcached data | Instance store (if ephemeral OK) or EBS | Speed matters; instance store is fastest |
| Logs, temp files | Instance store or ephemeral | Can lose on reboot; prioritize throughput |
| Backups, archives | S3 / object storage | Cost-effective, durable, higher latency OK |
| ML training data | Local SSD or high-throughput EBS | Large sequential reads |

**Staff-Level Insight**: Don't default to the most expensive option. Match storage tier to access pattern. A cache can use instance store; a primary database cannot.

## L5 vs L6: Disk and Storage

| Aspect | L5 Thinking | L6 Thinking |
|--------|-------------|-------------|
| **DB slow** | "Add more RAM" | "Add RAM for buffer pool, but also check: index usage, query patterns, disk IOPS limits" |
| **Storage choice** | "Use default" | "EBS gp3 vs io2: we need 16K IOPS for our DB; gp3 caps at 16K, io2 scales higher" |
| **Caching** | "We have a cache" | "Cache hit rate is 60%; 40% hits DB. At 10K QPS that's 4K DB reads/sec. Can our disk handle it?" |
| **Instance store** | "We use EBS" | "Our cache node uses instance store for speed; we accept data loss on instance failure" |

---

# Part 5: Troubleshooting — Connecting the Four Pillars

When a server is slow or failing, work through the four pillars systematically:

| Symptom | Check | Likely Cause |
|---------|-------|--------------|
| **High latency, low CPU** | I/O wait, DB latency | I/O-bound; optimize DB, add cache, connection pool |
| **High latency, high CPU** | Profiler, flame graph | CPU-bound; optimize hot paths, add cores, or offload |
| **OOM kill** | Memory usage, heap dump | Leak, too-small limits, or genuine need for more RAM |
| **GC pauses** | GC logs, pause times | Heap size, allocation rate, collector choice |
| **Context switch storm** | `vmstat`, `pidstat` | Too many threads; reduce pool or switch to async |
| **Disk at 100%** | `iostat`, IOPS | Too many random reads; add index, increase cache, or upgrade to SSD |
| **Container throttled** | cgroup metrics | CPU or memory limit hit; increase or optimize |

**Staff-Level Insight**: The fastest path to resolution is to **measure first**. Don't add CPU because "it might help"—check if CPU is actually saturated. Don't add RAM blindly—check if you're swapping or hitting limits. Profiling and metrics beat intuition.

---

# Part 6: Capacity Planning — Back-of-Envelope with the Four Pillars

When designing a new service or scaling an existing one, Staff engineers use the four pillars to estimate:

**Process/Thread**: How many concurrent requests? Thread-per-request: `concurrent = QPS × latency`. If 2K QPS and 50 ms latency, you need ~100 threads. Event-loop or goroutines: one process can handle 10K+ with minimal threads.

**Memory**: Per-request memory × concurrent + baseline. Java: ~1 MB/thread for stacks + heap for objects. Go: ~few KB/goroutine. Connection buffers: 32 KB × connections. Cache: size your working set.

**CPU**: I/O-bound: 2–4 cores often enough. CPU-bound: cores ≈ (QPS × CPU_ms_per_request) / 1000. Example: 1K QPS, 10 ms CPU each = 10 cores worth of work.

**Disk**: Read IOPS: cache miss rate × QPS. Write IOPS: write rate. Compare to disk capability (HDD ~100 IOPS random, SSD 100K+). If over, add cache or upgrade storage.

**Example**: API service, 5K QPS, 30 ms p99 (mostly DB wait). Thread pool: 5K × 0.03 = 150 concurrent → 200 threads. Memory: 200 × 1 MB = 200 MB stacks + 1 GB heap ≈ 2 GB. CPU: I/O-bound, 4 cores. Disk: Minimal (stateless). Result: 4-core, 4 GB instance, 200-thread pool. Scale horizontally for more QPS.

---

# Example in Depth: Why Our Java Service OOM'd (and How We Fixed It)

A real-world pattern: a **Java API service** (thread-per-request, 4 GB heap) was OOM-killed under load. Post-mortem showed how the four pillars (process/thread, memory, CPU, disk) interact.

**What happened**: Traffic grew; p99 latency went from 50 ms to 2+ seconds. Then OOM. Heap dump showed: **millions of `byte[]` and `String`** in old gen, and **thread count** at 800 (default stack 1 MB → 800 MB just for stacks). Root cause: (1) **Thread pool** was unbounded under a legacy config—each request got a thread; under burst, thread count exploded. (2) Each request parsed a large JSON body and held references in thread-local caches "for performance"—so **per-request memory** was high and not released until GC, and with 800 threads the heap was dominated by request buffers and thread stacks.

**Fix**: (1) **Cap thread pool** (e.g. 200) so concurrent requests are bounded; queue the rest or return 503. (2) **Reduce per-request retention**: stop caching parsed payloads in thread-locals; use a bounded pool of buffers and return them immediately. (3) **Tune GC**: move to G1 or ZGC for large heaps and lower pause times. (4) **Add limits**: container memory limit slightly below host so OOM killer hits the process, not the host; alert on thread count and heap usage.

**Takeaway**: OOM is rarely "need more RAM." It's usually **too many threads**, **per-request memory** not released, or **leaks**. Staff engineers size threads and heap from QPS × latency and profile before scaling.

## Breadth: Concurrency, Memory, and Disk Edge Cases

| Area | Edge case | What happens | Mitigation |
|------|-----------|---------------|------------|
| **Threads** | Unbounded pool under burst | Thread count and memory explode; OOM or context switch storm | Bounded pool + queue; backpressure or 503 |
| **Memory** | GC pressure from many short-lived objects | Long GC pauses; latency spikes | Reduce allocation; tune heap/collector; consider off-heap for caches |
| **Memory** | One huge allocation (e.g. load a 500 MB file) | Single request can dominate heap; risk OOM | Stream or chunk; cap request body size; separate process for big jobs |
| **CPU** | No timeout on CPU-bound path | One request can monopolize a core | Timeouts; isolate CPU-heavy work (queue, worker pool) |
| **Disk** | Log or temp file fills disk | Writes fail; process or node dies | Rotate logs; cap temp size; monitor disk; alert on usage |
| **Disk** | Many small random reads (no cache) | IOPS saturation; high latency | Cache hot data; batch; use SSD or better storage tier |

**Anti-patterns**: "Just add more memory" without profiling; unbounded thread pools; ignoring GC in latency SLOs; no per-request or per-connection memory budget. Staff-level practice: **model concurrency and memory from load**, then **validate with metrics and profiles**.

---

# Summary: Connecting OS Fundamentals to System Design

The four pillars—**process/thread**, **memory**, **CPU**, and **disk**—determine how your servers behave under load. Staff engineers:

1. **Choose the right concurrency model**: Thread-per-request vs event-loop vs goroutines, based on language, workload, and memory constraints.
2. **Size memory correctly**: Heap, stacks, buffers. Monitor GC pauses. Avoid leaks.
3. **Profile before scaling CPU**: Most servers are I/O-bound. Add CPU when profiles show it, not by default.
4. **Understand the storage hierarchy**: RAM > SSD > HDD. Cache aggressively. Choose storage tier for access patterns.
5. **Connect fundamentals to scale**: C10K, connection pooling, GC tuning, NUMA—these aren't theoretical. They show up in production.

Use this foundation when designing systems. When latency spikes, think: process (context switch?), memory (GC? leak?), CPU (throttled? serialization?), disk (IOPS? cache miss?). The answers will guide your next move.

---

# Appendix: Quick Reference — OS Fundamentals for System Design

## Concurrency Models at a Glance

| Model | Best For | Memory/10K Connections | Typical Use |
|-------|----------|------------------------|-------------|
| Thread-per-request | Predictable, debuggable | ~10 GB (1 MB/thread) | Java, C#, traditional |
| Event loop | I/O-bound, high concurrency | ~100 MB | Node.js, Nginx |
| Goroutines | I/O-bound, high concurrency | ~50 MB | Go |
| Async/await | I/O-bound, modern syntax | ~50–100 MB | Python, JS, Rust |

## Memory Sizing Cheat Sheet

| Component | Typical Size |
|-----------|--------------|
| Java thread stack | 1 MB default |
| Goroutine stack | 2–8 KB initial |
| TCP connection buffer | 4–64 KB per connection |
| JVM heap (stateless API) | 512 MB – 4 GB |
| Redis (in-memory) | Entire dataset in RAM |
| Postgres shared_buffers | 25% of RAM, often 4–16 GB |

## Bottleneck Quick Check

- **High CPU, high latency** → CPU-bound; profile, add cores, optimize.
- **Low CPU, high latency** → I/O-bound; DB, network, disk.
- **Memory growing** → Leak or insufficient; heap dump, increase limit.
- **OOM kill** → Over limit or leak; check cgroup, heap dump.
- **Disk at 100%** → IOPS or throughput limit; cache, index, or SSD.

## Staff-Level Questions to Ask

1. "What's our concurrency model, and does it match our workload?"
2. "Where does our p99 latency come from—GC, I/O, or CPU?"
3. "What's our cache hit rate, and what happens on a miss?"
4. "If we 10x traffic, what breaks first—threads, memory, DB, or disk?"
