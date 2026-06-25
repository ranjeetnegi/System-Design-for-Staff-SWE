# Chapter 122 — Performance Profiling

> *"Measure, don't guess. Your intuition about where the bottleneck is will be wrong 70% of the time. The profiler is always right."*
> — Brendan Gregg, "Systems Performance"

---

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    AT-A-GLANCE: PERFORMANCE PROFILING                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│  THE GOLDEN RULE   Measure first. Optimize second. Verify third.               │
│                    Never optimize without a profile. Never.                    │
│                                                                                 │
│  TWO ROOT CAUSES   CPU-bound: service is computing (reduce work)               │
│                    I/O-bound: service is waiting (reduce waits / parallelize)  │
│                    Every performance problem is one of these two.              │
│                                                                                 │
│  FLAME GRAPH       The single best profiling tool.                             │
│                    Width = % of total time. Tall stacks = deep call chains.    │
│                    "Find the widest tower. That's your bottleneck."            │
│                                                                                 │
│  PROFILING CYCLE   Reproduce → Baseline → Profile → Isolate → Fix → Verify    │
│                    Skip "Reproduce" = waste time optimizing the wrong thing    │
│                                                                                 │
│  DATABASE TRAP     N+1 queries are responsible for ~40% of "slow app" reports. │
│                    EXPLAIN ANALYZE before any index change.                    │
│                                                                                 │
│  LOAD TESTING      Tells you WHERE the system breaks.                          │
│                    Not the same as stress testing (how long until it fails).   │
│                                                                                 │
│  L5 SIGNAL         Profiles a service, finds the bottleneck, fixes it,        │
│                    measures the improvement. Writes up findings.               │
│  L6 SIGNAL         Builds performance culture: continuous profiling,           │
│                    perf budgets in CI, load test gates before each launch.     │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: What Is Performance Profiling, and Why Does It Matter?

*(Intern → L3 level)*

Imagine you work at a pizza shop. Orders are taking 45 minutes instead of the usual 20. What's slowing things down?

You have two choices:
- **Guess**: "It's probably the oven. Let's buy a faster oven." — $20,000 later, orders still take 40 minutes.
- **Observe**: Stand in the kitchen with a stopwatch. Time each step. Find that the delay is actually in the dough-prep station — one person kneading by hand instead of using the dough mixer.

Performance profiling is the stopwatch. It tells you **exactly** where time is going, so you fix the right thing.

**Why guessing is dangerous:**

Engineers are terrible at guessing bottlenecks. Studies show that without profiling, engineers fix the wrong thing about 70% of the time. They optimize the code they know best, not the code that's actually slow.

```
Common wrong guesses:           What profiling actually reveals:
"The database is slow"      →   The app makes 200 DB queries per request (N+1)
"We need more servers"      →   One endpoint holds a mutex for 3 seconds
"The network is the issue"  →   A JSON serialization function runs 50,000 times
"We need a faster language" →   A quadratic algorithm in one function
```

**The performance profiling mindset:**

```
BEFORE profiling:
  "This feels slow. Probably the database. Let me add an index."
  
AFTER learning profiling:
  "This feels slow. Let me reproduce it with a load test, run the profiler,
   find the top 3 functions by CPU time, and check if one is clearly wrong."
```

The difference is scientific method vs. intuition. Profiling makes you scientific.

**Real-world stakes — the Cloudflare 2020 incident:**

In August 2020, Cloudflare's edge network had unexplained CPU spikes. Before they had profiling, they would have scaled up servers. With continuous profiling (using eBPF-based tools), they found the exact function: a regex in their network rules engine had catastrophic backtracking on specific packet patterns. One regex. One CPU spike. Fixed in 20 minutes once found; would have taken days without profiling.

```
ASCII: The profiling mindset shift

Before profiling:           After profiling:
                            
  Symptom: slow            Symptom: slow
     │                        │
     ▼                        ▼
  GUESS                   MEASURE
  (wrong 70% of           (always correct)
   the time)                 │
     │                       ▼
     ▼                   ISOLATE
  Fix wrong thing         (where exactly?)
     │                       │
     ▼                       ▼
  Still slow              Fix right thing
                              │
                              ▼
                          VERIFY
                          (did it help?)
```

**Brainstorming Questions:**
1. Think of a time you or your team optimized something without measuring first. What happened? Would profiling have changed the approach?
2. What's the difference between "the app is slow" and "the app is slow because of X"? Why does the distinction matter?
3. Why might an engineer resist profiling and prefer to "just try something"? What could you say to change their mind?
4. Cloudflare found a problem in 20 minutes with profiling. Estimate how long the same investigation would take with just logs and intuition.

---

## Part 2: CPU-Bound vs. I/O-Bound — The Foundational Split

*(Intern → L3 level)*

Every performance problem falls into one of two categories. Knowing which one you're dealing with determines every tool and fix you'll use.

**CPU-bound: the service is working too hard**

The CPU is busy. The processor is at 80-100% while handling requests. The bottleneck is *computation*.

```
What's happening:
  Request arrives → CPU starts computing → 
  CPU is fully occupied → next request has to wait
  
Signs:
  - High CPU utilization (top, htop shows 90%+ CPU)
  - Latency is proportional to CPU load
  - Adding more CPU cores helps immediately
  
Examples:
  - JSON serialization of a huge response (parsing 10MB JSON)
  - Image resize on every request (instead of caching resized versions)
  - Inefficient algorithm: O(n²) search on a list of 100,000 items
  - Encryption of large payloads
  - Regex with catastrophic backtracking
```

**I/O-bound: the service is waiting too much**

The CPU is idle. The service is waiting for something else: a database response, a network call, a disk read. The bottleneck is *waiting*, not *computing*.

```
What's happening:
  Request arrives → service calls database → 
  CPU sits idle waiting for DB response (could be 100ms) →
  Request completes
  
Signs:
  - Low CPU utilization (10-30% even under high load)
  - High number of concurrent pending connections
  - Latency is dominated by external service call times
  - Adding more CPU cores does NOT help
  
Examples:
  - Slow database queries (awaiting DB response)
  - Sequential API calls (calling 3 external APIs one after another)
  - Large file reads from disk
  - Network latency to distant region
  - Waiting for mutex/lock held by another thread
```

**The ASCII diagram:**

```
CPU-bound service:          I/O-bound service:
                            
[Request]                   [Request]
    │                           │
    ▼                           ▼
[CPU: BUSY] ←── bottleneck  [CPU: idle, waiting]
    │                           │
  100ms of computation        1ms of computation
    │                         99ms waiting for DB ←── bottleneck
    ▼                           │
[Response]                  [Response]

Fix: reduce computation.    Fix: reduce waits.
     Algorithm improvements       Add caching
     Caching computed results      Parallelize API calls
     Faster language               Connection pooling
     More CPU cores                Async I/O
```

**How to tell which one you have:**

```bash
# Run this while the service is under load
top -p $(pgrep your-service)

# CPU-bound: you'll see CPU% at 90-100%
# I/O-bound: you'll see CPU% at 10-30%, but lots of "wa" (I/O wait)

# Linux: check with vmstat
vmstat 1  # watch the 'wa' column (I/O wait)
# wa > 20% → I/O-bound
# sy + us > 70% → CPU-bound
```

**Real example: the Instagram Python migration**

In 2016, Instagram had a Python service that was CPU-bound at 100% CPU handling image filter computations. The fix wasn't more servers — they moved the image processing to C (via Cython) and reduced CPU usage by 60%. Request throughput doubled with the same number of servers. If they hadn't profiled, they might have just added servers and paid 2× the infrastructure cost.

**Common mistake: treating I/O-bound like CPU-bound**

A team has a slow API. CPU is at 25%. They think "the service is processing a lot, needs more compute." They switch from Python to Go. Latency barely improves. Why? The service was making 10 sequential database calls per request — 90ms each = 900ms total. Language speed doesn't fix 900ms of waiting.

**Brainstorming Questions:**
1. Your service's p99 latency is 2 seconds. CPU is at 15%. Is this likely CPU-bound or I/O-bound? What's your first debugging step?
2. A team says "we need to rewrite this service in Rust for performance." What question would you ask before agreeing or disagreeing?
3. A service is I/O-bound waiting on a database. Name 3 different fixes at different levels (caching, query optimization, connection pooling). Which would you try first and why?
4. Can a service be BOTH CPU-bound and I/O-bound at the same time on different code paths? Give an example.

---

## Part 3: Flame Graphs — The Most Powerful Profiling Tool

*(L3 → L4 level)*

A flame graph is a visualization of where your program spends its time. It is the most useful profiling output ever invented (created by Brendan Gregg at Netflix).

Once you know how to read a flame graph, you can find performance bottlenecks in any language, any system, in minutes.

**How to read a flame graph:**

```
┌─────────────────────────────────────────────────────────────────┐
│                     Flame Graph Reading Guide                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Y-axis = call stack depth (bottom = entry point, top = leaf)   │
│  X-axis = % of total samples (wider = more time spent)         │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │           handlePayment()   [very wide — 60% of time]     │ │
│  │  ┌──────────────────────────────────────┐  ┌────────────┐ │ │
│  │  │   processOrder() [40%]               │  │  auth() 20%│ │ │
│  │  │  ┌──────────────────┐ ┌────────────┐ │  │            │ │ │
│  │  │  │  queryDB() [30%] │ │ validate() │ │  │            │ │ │
│  │  │  │  ┌─────────────┐ │ │ [10%]      │ │  │            │ │ │
│  │  │  │  │ pgQuery()   │ │ │            │ │  │            │ │ │
│  │  │  │  │ [30%]       │ │ │            │ │  │            │ │ │
│  │  │  └──────────────────┘ └────────────┘ │  │            │ │ │
│  │  └──────────────────────────────────────┘  └────────────┘ │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Reading rule:                                                   │
│  Find the WIDEST frame that has NO wider child.                 │
│  That is your bottleneck. Here: pgQuery() — it's all the way   │
│  down the stack and takes 30% of all time.                      │
│                                                                  │
│  "The widest tower is your bottleneck."                         │
└─────────────────────────────────────────────────────────────────┘
```

**The key insight:** the X-axis is NOT time — it is the percentage of CPU samples. A function that appears wide is spending a large fraction of total CPU time. The ORDER of functions left-to-right is alphabetical within a stack level, not chronological.

**Generating a flame graph in Go:**

```go
// In your Go service, add pprof HTTP endpoint
import _ "net/http/pprof"

// In main.go
go func() {
    log.Println(http.ListenAndServe("localhost:6060", nil))
}()
```

```bash
# While service is under load, capture 30 seconds of CPU profile
go tool pprof http://localhost:6060/debug/pprof/profile?seconds=30

# Generate flame graph
go tool pprof -http=:8080 cpu.prof
# Open http://localhost:8080/ui/flamegraph
```

**Generating a flame graph in Python:**

```bash
# Install py-spy
pip install py-spy

# Attach to running process (no code change needed)
py-spy record -o flamegraph.svg --pid 12345 --duration 30

# Open flamegraph.svg in browser
```

**Generating a flame graph in Java:**

```bash
# Use async-profiler (no JVM flags needed, no overhead)
./profiler.sh -d 30 -f flamegraph.html <PID>
open flamegraph.html
```

**What to look for in a flame graph:**

```
1. THE WIDE PLATEAU
   A function that is wide at the TOP of the stack
   (no children, or all children are narrow).
   This function IS the bottleneck — it's doing the work.
   
2. THE TALL THIN TOWER
   A very deep call stack that appears thin.
   Not the bottleneck — it's fast but deeply nested.
   
3. THE UNEXPECTED FUNCTION
   A function you didn't expect to see taking 20% of time.
   "Why is JSON serialization taking 15% of my CPU?"
   
4. THE SYSTEM CALL CLIFF
   Many thin lines at the bottom from kernel system calls.
   If these are wide: OS-level I/O or system call overhead.
```

**Real example: Netflix's flame graph discovery**

In 2013, Brendan Gregg at Netflix used flame graphs to find an unexpected 0.5% CPU overhead from a Cassandra time function. The function was called on every read. At Netflix's scale (billions of reads/day), 0.5% = tens of servers worth of CPU. Fixed by caching the timestamp. The fix was found in 15 minutes using a flame graph; it had been invisible for months before.

**Brainstorming Questions:**
1. You open a flame graph and see one function `serialize()` taking 45% of all samples. Before optimizing it, what would you want to know about it? (What questions would you ask?)
2. A flame graph shows the database client library at 80% of CPU. Does this mean the database itself is slow? What's the difference?
3. If a flame graph shows nothing obvious (everything is roughly equal, nothing dominates), what does that tell you about the nature of the performance problem?
4. A team says "we don't need flame graphs, we just look at the slow endpoint in our APM tool." What's the difference between APM trace data and a flame graph? When does each fall short?

---

## Part 4: The Profiling Workflow — Reproduce, Baseline, Profile, Isolate, Fix, Verify

*(L3 → L4 level)*

The most common profiling mistake is jumping straight to the profiler before establishing a baseline. Without a baseline, you don't know if your fix actually helped.

**The 6-step workflow:**

```
┌──────────────────────────────────────────────────────────────────┐
│                  THE PROFILING WORKFLOW                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. REPRODUCE                                                    │
│     Can you make the slowness happen on demand?                  │
│     If not, you can't profile it reliably.                       │
│     Goal: a script or load test that reliably triggers the issue │
│                                                                  │
│  2. BASELINE                                                     │
│     Measure current performance BEFORE any changes.             │
│     Record: p50, p95, p99 latency, CPU%, memory, throughput.    │
│     You need this to prove your fix worked.                      │
│                                                                  │
│  3. PROFILE                                                      │
│     Run the profiler while reproducing the issue.               │
│     Collect: CPU profile, memory profile, trace.                 │
│                                                                  │
│  4. ISOLATE                                                      │
│     Find the ONE function/query/call responsible for > 10%       │
│     of total time. Don't optimize everything — find the worst.  │
│                                                                  │
│  5. FIX                                                          │
│     Change only the identified bottleneck. Nothing else.        │
│     (Changing multiple things = can't attribute improvement)     │
│                                                                  │
│  6. VERIFY                                                       │
│     Re-run baseline measurement. Compare to Step 2.             │
│     If < 10% improvement → wrong diagnosis. Repeat from Step 3. │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Step 1 example — reproducing with a load test:**

```bash
# Use wrk to generate consistent load
wrk -t 4 -c 100 -d 30s http://localhost:8080/api/checkout

# Output:
# Requests/sec: 847.23
# Latency: Avg: 118.03ms, p99: 2.43s   ← p99 is 20× the average → problem
```

**Step 2 example — baselining:**

```python
# Before ANY optimization, record these numbers
BASELINE = {
    "timestamp": "2026-06-25 14:00",
    "p50_latency_ms": 45,
    "p99_latency_ms": 2430,
    "cpu_utilization_pct": 73,
    "requests_per_second": 847,
    "error_rate_pct": 0.2,
}
# Write this down. Literally. In a doc. You will need it.
```

**Step 4 example — isolating:**

```
Flame graph shows:
  handleCheckout():    100% of samples (top of stack — always present)
  ├── queryInventory():  45% of samples  ← FOCUS HERE
  │   └── sql.Query():   44%             ← almost all of queryInventory
  ├── chargePayment():   30% of samples
  │   └── stripeClient.Charge(): 28%
  └── buildResponse():  25% of samples
      └── json.Marshal():  24%

Analysis:
  queryInventory → sql.Query is 44% of all time.
  Check query: SELECT * FROM inventory WHERE product_id IN (...)
  Run EXPLAIN ANALYZE → full table scan, no index on product_id.
  
  This is the bottleneck. Fix: add index on product_id.
```

**Step 6 example — verifying:**

```bash
# After adding the index, re-run baseline
wrk -t 4 -c 100 -d 30s http://localhost:8080/api/checkout

# New results:
# Requests/sec: 2,341.08  (↑ 2.77×)
# Latency: Avg: 42.6ms, p99: 187ms  (↓ 13× improvement on p99)

# Compare to baseline: p99 went from 2,430ms → 187ms. ✅
```

**Common workflow mistakes:**

```
❌ Profiling in development, not under production-like load
   The bottleneck at 1 req/sec is different from 1,000 req/sec.
   Always profile under load that resembles production.

❌ Fixing multiple things at once
   If you fix 3 things and performance improves, you don't know
   which fix helped. Measure each change independently.

❌ Declaring victory after p50 improvement
   "Average latency improved from 80ms to 20ms!"
   But p99 is still 3,000ms → top 1% of users still suffer.
   Always check p50, p95, and p99.

❌ Not reverting and re-measuring
   Your fix made things better by 10%. But you need 50%.
   Revert. Find a different bottleneck. Profile again.
```

**Brainstorming Questions:**
1. Why is it important to establish a baseline BEFORE optimizing, rather than just comparing before vs. after your first attempt?
2. You find that your fix improved p50 latency by 40% but p99 improved by only 5%. What does this suggest about the nature of the remaining bottleneck?
3. Your performance issue only appears under high concurrency (500+ concurrent users). How would you set up a profiling environment that captures this?
4. A colleague says "I've already profiled this and I know it's the database." Should you trust this assessment and start optimizing the database, or would you run your own profile first? Why?

---

## Part 5: CPU Profiling Tools

*(L4 level)*

Different languages have different profiling tools, but they all do the same thing: sample the call stack many times per second and count which functions appear most often. Functions that appear in more samples take more CPU time.

**Go — pprof**

```go
// Built into Go's standard library. Zero external dependencies.

// HTTP endpoint (add to any Go service):
import (
    "net/http"
    _ "net/http/pprof"  // blank import registers handlers
)

func main() {
    // Profiling endpoint runs on separate port from your service
    go func() {
        http.ListenAndServe("localhost:6060", nil)
    }()
    // ... rest of your service
}
```

```bash
# Collect 30s CPU profile while service is under load
curl -o cpu.prof http://localhost:6060/debug/pprof/profile?seconds=30

# Interactive analysis
go tool pprof cpu.prof
(pprof) top10      # top 10 functions by CPU time
(pprof) web        # open flame graph in browser
(pprof) list processOrder  # see line-by-line CPU time for a function

# One-liner flame graph
go tool pprof -http=:8080 http://localhost:6060/debug/pprof/profile?seconds=30
```

```
Go pprof top output:
  Flat%   Cum%   Function
  45.3%   45.3%  database/sql.(*Rows).Next    ← 45% of CPU here
  12.1%   57.4%  encoding/json.Marshal
   8.3%   65.7%  crypto/sha256.Sum256
   ...

Flat% = time in this function only
Cum%  = time in this function + all functions it calls
```

**Python — py-spy**

```bash
# py-spy attaches to a running process — NO code changes needed
pip install py-spy

# Option 1: Live top view (like htop but for Python functions)
py-spy top --pid 12345

# Option 2: Record flame graph
py-spy record -o flamegraph.svg --pid 12345 --duration 30 --rate 100

# Option 3: Profile a script directly
py-spy record -o flamegraph.svg -- python my_script.py

# Interpreting:
# If you see 'GIL' sections in the flame graph → Python GIL is the bottleneck
# If you see 'C extension' taking most time → look at the C library, not Python
```

**Java — async-profiler**

```bash
# Download async-profiler
wget https://github.com/async-profiler/async-profiler/releases/download/v3.0/async-profiler-3.0-linux-x64.tar.gz

# Profile a running JVM (by PID)
./profiler.sh start -e cpu -f flamegraph.html 12345
./profiler.sh stop 12345
open flamegraph.html

# Why not JVisualVM or JProfiler?
# async-profiler uses OS-level signals — no JVM safepoint bias.
# Traditional Java profilers ONLY sample at safepoints, which
# means they miss time spent in native code and I/O — they lie.
```

**Linux perf — any language, system-level**

```bash
# perf works for any language (C, C++, Go, Java, Rust)
# Records kernel and user space together

# Record 30s of CPU events
perf record -g -p $(pgrep your-service) sleep 30

# Generate flame graph (requires brendangregg/FlameGraph scripts)
perf script | stackcollapse-perf.pl | flamegraph.pl > flamegraph.svg

# View hottest functions
perf report
```

**Node.js — V8 profiler**

```bash
# Start Node with profiling
node --prof app.js

# After load test, process the profile
node --prof-process isolate-*.log > processed.txt

# Or use clinic.js for flame graphs
npm install -g clinic
clinic flame -- node app.js
```

**The sampling rate trade-off:**

```
Low sampling rate (100 Hz):    Low overhead (< 1% CPU), less accurate
High sampling rate (10,000 Hz): Higher overhead (1-3% CPU), more accurate

For production: use 100-500 Hz (safe)
For development: use 1,000-10,000 Hz (more detail)
```

**Brainstorming Questions:**
1. pprof shows `json.Marshal` taking 25% of CPU in your service. What are 3 different ways you could reduce this overhead? (Think: reduce calls, reduce data size, change format)
2. A Python service is slow and py-spy shows the GIL (Global Interpreter Lock) in the flame graph. What does this mean, and what architectural change would actually fix it?
3. Java's traditional profilers (JProfiler, JVisualVM) have safepoint bias. What does this mean, and why does it matter? When would it cause you to optimize the wrong thing?
4. You want to profile a service in production (not development). What concerns do you have, and how would you mitigate them?

---

## Part 6: Memory Profiling — Heap Dumps, Leaks, and GC Pressure

*(L4 level)*

Memory problems are different from CPU problems. They're often invisible at first — the service starts fast, then gets slower over hours or days, then crashes with an OOM (Out Of Memory) error. This is a memory leak.

**The three memory problems:**

```
┌─────────────────────────────────────────────────────────────────┐
│                THREE MEMORY PROBLEM TYPES                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. MEMORY LEAK                                                  │
│     Memory grows over time and never shrinks.                   │
│     Example: a map that adds entries but never removes them.    │
│     Symptom: memory graph trends up steadily over hours.        │
│     Fix: find the growing data structure; add eviction.         │
│                                                                  │
│  2. MEMORY SPIKE                                                 │
│     Specific requests use a lot of memory temporarily.          │
│     Example: loading a 500MB file into memory to process it.   │
│     Symptom: memory spikes on specific requests, then recovers. │
│     Fix: stream the file instead of loading it all at once.    │
│                                                                  │
│  3. GC PRESSURE (Garbage Collection pressure)                   │
│     Many short-lived objects created and discarded rapidly.     │
│     The garbage collector runs constantly, pausing the app.     │
│     Symptom: CPU spikes at regular intervals, latency jitter.  │
│     Fix: reuse objects (object pools), reduce allocations.      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Diagnosing a memory leak — Go:**

```bash
# Take a heap dump while service is running
curl -o heap.prof http://localhost:6060/debug/pprof/heap

# Analyze: which objects are taking the most memory?
go tool pprof heap.prof
(pprof) top10        # top 10 allocations by size
(pprof) web          # flame graph of allocations

# The key flag: inuse_space vs alloc_space
# inuse_space: what's currently in memory (for leaks)
# alloc_space: what was allocated (for GC pressure)

go tool pprof -alloc_space http://localhost:6060/debug/pprof/heap
go tool pprof -inuse_space http://localhost:6060/debug/pprof/heap
```

**A real memory leak — explained simply:**

```go
// ❌ MEMORY LEAK: userSessions grows forever
var userSessions = make(map[string]*Session)  // global map

func login(userID string) {
    userSessions[userID] = &Session{...}  // adds to map
    // NEVER deletes from map, even when session expires
}

// After 1 week: userSessions has 10 million entries
// Memory: 10M × ~1KB = ~10GB → OOM crash

// ✅ FIX: add expiration and cleanup
func login(userID string) {
    userSessions[userID] = &Session{ExpiresAt: time.Now().Add(24*time.Hour)}
}

// Background goroutine to clean expired sessions
func cleanupExpiredSessions() {
    for range time.Tick(15 * time.Minute) {
        for id, session := range userSessions {
            if time.Now().After(session.ExpiresAt) {
                delete(userSessions, id)
            }
        }
    }
}
```

**Java heap dump analysis:**

```bash
# Trigger OOM heap dump automatically
java -XX:+HeapDumpOnOutOfMemoryError \
     -XX:HeapDumpPath=/tmp/heapdump.hprof \
     -jar your-service.jar

# Or dump manually
jcmd 12345 GC.heap_dump /tmp/heapdump.hprof

# Analyze with Eclipse Memory Analyzer Tool (MAT)
# Or IntelliJ's built-in heap analyzer
# Look for: "Retained Heap" — the total memory held by each object tree
# The object with the largest Retained Heap is usually the leak source
```

**GC pressure — the latency jitter problem:**

```
Timeline of GC pressure:
  T+0s:   request arrives, 15ms response → ✅
  T+2s:   request arrives, 14ms response → ✅
  T+4s:   request arrives, 14ms response → ✅
  T+6s:   GC runs (stop-the-world pause: 200ms) → 
  T+6s:   request arrives, 214ms response → ❌ spike!
  T+8s:   request arrives, 13ms response → ✅

If you only look at p50 (50ms), you miss the p99 (250ms) entirely.
GC pauses are responsible for many "mystery p99 latency spikes."

Fix strategies:
  Go: tune GOGC (GC target percentage). Default: GOGC=100
      Lower GOGC = more frequent GC, less pause time per GC
      GOGC=50 → GC runs 2× as often but each pause is shorter
  
  Java: use ZGC or Shenandoah (sub-millisecond GC pauses)
        G1GC is the default; ZGC is better for latency-sensitive apps
  
  Any language: reduce allocation rate (don't create objects in hot paths)
```

**Real incident: Slack's 2019 memory incident**

Slack had a Go service that grew from 2GB to 24GB over 48 hours. The heap dump showed: a map of WebSocket connections where the key was a connection ID. The connection was deleted from the map on close, but the Session struct attached to each connection held a reference to a []byte buffer that was never released. The buffer was 1MB × 23,000 retained connections = 23GB. Fixed by clearing the buffer on disconnect. Found using `go tool pprof -inuse_space`.

**Brainstorming Questions:**
1. Your service's memory increases from 2GB to 6GB over 72 hours, then the pod is OOM-killed and restarts. What's your first profiling step to diagnose this?
2. How would you distinguish between a memory leak and "the service just needs more memory as it handles more data"? What evidence would you look for?
3. GC pressure causes p99 latency spikes every 30 seconds. You fix it by reducing object allocations in the hot path. How would you verify the fix worked, specifically for GC pauses?
4. A Java service uses 20GB of heap but the heap dump shows only 8GB of objects. Where is the other 12GB? (Hint: think about what else is in the JVM process memory)

---

## Part 7: Database Profiling — EXPLAIN, Slow Query Log, and the N+1 Problem

*(L4 → L5 level)*

The single most common source of "the backend is slow" is a slow database query. And the most common slow query problem is NOT that the query is complex — it is that the query is being called hundreds of times when it should be called once. This is the **N+1 query problem**.

**The N+1 problem — explained simply:**

You want to show a user their order history with product names.

```python
# ❌ N+1 PROBLEM (very common in ORM frameworks)
orders = db.query("SELECT * FROM orders WHERE user_id = ?", [user_id])
# This returns 50 orders. Now for EACH order, you do another query:

for order in orders:
    product = db.query("SELECT name FROM products WHERE id = ?", [order.product_id])
    # ^ This runs 50 times! One per order.

# Total: 1 + 50 = 51 queries per page load
# At 100 users/sec: 5,100 queries/sec → database overwhelmed
```

```python
# ✅ FIX: JOIN or batched IN query
# Option 1: JOIN
orders_with_products = db.query("""
    SELECT o.*, p.name as product_name
    FROM orders o
    JOIN products p ON p.id = o.product_id
    WHERE o.user_id = ?
""", [user_id])
# 1 query total. Database does the join efficiently.

# Option 2: batched IN
orders = db.query("SELECT * FROM orders WHERE user_id = ?", [user_id])
product_ids = [o.product_id for o in orders]
products = db.query("SELECT * FROM products WHERE id IN (?)", [product_ids])
# 2 queries total. Much better than 51.
```

**Diagnosing N+1 with query counting:**

```python
# Django has a built-in query counter
from django.db import connection

with connection.queries_enabled():
    response = view_function(request)
    query_count = len(connection.queries)
    
if query_count > 10:
    print(f"WARNING: {query_count} queries for one request!")
    for q in connection.queries:
        print(q['sql'][:100])

# Also: Django Debug Toolbar in development shows query count per request
# OR: enable query logging in PostgreSQL
```

**EXPLAIN ANALYZE — the most important database command:**

EXPLAIN shows how the database will execute your query. EXPLAIN ANALYZE actually runs it and shows real timings.

```sql
-- Find why a query is slow
EXPLAIN ANALYZE
SELECT * FROM orders
WHERE user_id = 12345
AND status = 'pending'
ORDER BY created_at DESC
LIMIT 10;
```

```
Output:
  Sort  (cost=12345.67..12345.69 rows=10) (actual time=2341.456 ms)
    -> Seq Scan on orders  (cost=0.00..12000.00) (actual time=0.050..2300.123 ms)
         Filter: (user_id = 12345 AND status = 'pending')
         Rows Removed by Filter: 9,999,990

Reading the output:
  "Seq Scan" = FULL TABLE SCAN = no index used = BAD at scale
  Rows Removed by Filter: 9,999,990 = scanned 10 million rows to return 10
  actual time: 2341ms = why your API is slow

Fix: add index
  CREATE INDEX CONCURRENTLY idx_orders_user_status 
  ON orders(user_id, status);

After index:
  Index Scan on orders  (actual time=0.185 ms)
  Index Cond: (user_id = 12345 AND status = 'pending')
  
  2341ms → 0.185ms. That's a 12,700× improvement.
```

**ASCII: index vs. full table scan**

```
Full Table Scan (no index):     Index Scan:
                                
orders table (10M rows):        B-tree index on (user_id):
┌──────────────────────────┐    
│ row 1:  user=99, status=✓ │    user_id=12345
│ row 2:  user=72, status=✗ │    ↓ index lookup (log n = ~23 steps)
│ row 3:  user=12345, ✓    │◄── Find leaf: pointer to rows
│ ...                       │    ↓ fetch only those rows
│ row 10M: user=55, status=✗│    
└──────────────────────────┘    
                                
Read: 10M rows                  Read: ~10 rows
Time: 2341ms                    Time: 0.185ms
```

**Key EXPLAIN ANALYZE terms to know:**

```
Seq Scan:         Full table scan. Fine for small tables (< 10K rows).
                  Danger sign for large tables.
                  
Index Scan:       Uses an index. Fast for specific rows.

Index Only Scan:  Uses only the index, doesn't touch the table.
                  Fastest possible for covered queries.
                  
Nested Loop:      For each row in table A, scan table B.
                  Fast if inner table is small or well-indexed.
                  Very slow if inner table is large.
                  
Hash Join:        Build hash table of one table, probe with the other.
                  Good for large tables without indexes.
                  
actual time:      Real measured time (ANALYZE mode only).
rows:             Estimated vs actual rows. Large discrepancy = stale statistics.
                  Run: ANALYZE tablename to update statistics.
```

**Real incident: GitHub's 2018 database incident**

On October 21, 2018, GitHub experienced a major outage. A network partition caused MySQL replication to fall behind. When the partition healed, the replica had to process a queue of 34 seconds of writes — but those 34 seconds included queries that had been retried by applications. The retries had created duplicate data, and the deduplication query (`SELECT DISTINCT ... ORDER BY`) had no index on the ORDER BY column. At 34 seconds of write backlog on a billion-row table, the query ran for 43 minutes. GitHub was dark for about 5 hours. The missing index was a 3-line fix. The full postmortem is public at the GitHub Engineering Blog.

**Brainstorming Questions:**
1. You find an N+1 problem in production code written 2 years ago. It makes 1 query for the base list + N queries for details. The table has 1 million rows. Estimate the performance difference between N+1 and a JOIN.
2. EXPLAIN ANALYZE shows your query is doing a Seq Scan on a table with 50 million rows. You want to add an index. What information do you need before creating it? (Think: query frequency, write frequency, selectivity)
3. You add a composite index `(user_id, status)` but EXPLAIN ANALYZE still shows a Seq Scan. What are 3 possible reasons the query optimizer might choose not to use your new index?
4. Your database's `pg_stat_statements` shows one query runs 50,000 times/second with average 2ms execution time. How would you think about optimizing this differently than a single slow query?

---

## Part 8: Load Testing — Finding Where the System Breaks

*(L4 → L5 level)*

Load testing answers one question: "At what point does performance degrade, and why?"

It is NOT the same as stress testing (how long until it fails under extreme load). Load testing finds the performance cliff under realistic or expected load.

**The three load test shapes:**

```
┌─────────────────────────────────────────────────────────────────┐
│                  LOAD TEST SHAPES                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. RAMP TEST (most useful)                                      │
│     Start low, increase users over time.                        │
│     Watch for where latency or error rate "breaks."             │
│                                                                  │
│  Requests/sec                                                    │
│     ↑ 1000 ┤                              Error rate jumps ↗   │
│       800  ┤                         ┌────────────────           │
│       600  ┤                 ┌───────┘                           │
│       400  ┤         ┌───────┘                                   │
│       200  ┤ ┌───────┘   p99 latency: flat then cliff           │
│         0  └─────────────────────────────────────────────→ time │
│                 10         50        100        200              │
│                     concurrent users                             │
│                                                                  │
│  2. SOAK TEST                                                    │
│     Constant load for a long time (1-24 hours).                 │
│     Finds: memory leaks, connection pool exhaustion,            │
│     database slow degradation.                                   │
│                                                                  │
│  3. SPIKE TEST                                                   │
│     Sudden 10× traffic spike, then back to normal.              │
│     Finds: auto-scaling lag, circuit breaker behavior,          │
│     timeout handling under queue backup.                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Load testing tools:**

```
k6 (recommended):
  - JavaScript test scripts
  - Built-in metrics, threshold checks
  - Can run in cloud (k6.io) for geo-distributed testing
  
  brew install k6
  
locust (Python):
  - Python test scripts
  - Good for complex scenarios (authentication, session management)
  - Web UI showing live metrics
  
  pip install locust
  
wrk/wrk2:
  - Simple, ultra-fast HTTP load generation
  - Good for baseline: "how many req/sec can this handle?"
  - wrk2 has consistent throughput mode (better for latency measurement)
  
  brew install wrk
```

**k6 example — ramp test for a checkout endpoint:**

```javascript
// checkout-load-test.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
    stages: [
        { duration: '2m', target: 50 },   // ramp to 50 users over 2 min
        { duration: '5m', target: 50 },   // hold at 50 users for 5 min
        { duration: '2m', target: 200 },  // ramp to 200 users
        { duration: '5m', target: 200 },  // hold at 200 users
        { duration: '2m', target: 0 },    // ramp down
    ],
    thresholds: {
        http_req_duration: ['p99<500'],   // fail if p99 > 500ms
        http_req_failed: ['rate<0.01'],   // fail if error rate > 1%
    },
};

export default function () {
    const payload = JSON.stringify({
        cart_id: 'cart_123',
        payment_token: 'tok_test_123',
    });
    
    const response = http.post(
        'http://localhost:8080/api/checkout',
        payload,
        { headers: { 'Content-Type': 'application/json' } }
    );
    
    check(response, {
        'status is 200': (r) => r.status === 200,
        'response time < 500ms': (r) => r.timings.duration < 500,
    });
    
    sleep(1);
}
```

```bash
# Run the test
k6 run checkout-load-test.js

# Output:
# ✓ http_req_duration............: avg=187ms min=12ms med=145ms max=3.2s p90=380ms p99=950ms
# ✗ http_req_duration p99<500ms:  950ms > 500ms threshold FAILED
# ↑ Investigate: what happens at 200 concurrent users?
```

**How to read load test results:**

```
Good result:                    Bad result:
  p99 stays flat as load ↑       p99 suddenly jumps at 150 users
  Error rate stays < 0.1%        Error rate jumps to 5% at 200 users
  Throughput scales linearly      Throughput plateaus then drops
  
What the bad result means:
  The "150 user cliff" is your capacity limit.
  At 150 users, something gets saturated:
  - A database connection pool (connections exhausted)
  - A mutex or lock (goroutines queue waiting)
  - A CPU core (threads competing for CPU)
  - A rate limit on an external API call
  
  Find it with: run the load test AND the profiler simultaneously.
  The profiler during load = you see the bottleneck exactly when it matters.
```

**The load testing checklist before any major launch:**

```
□ Load test at 2× expected traffic (handle surprises)
□ Load test at 10× expected traffic (find the cliff)
□ Soak test for 4+ hours at expected traffic (find leaks)
□ Spike test: 10× for 30 seconds (find auto-scaling behavior)
□ Load test with production-like data (not empty test DB)
□ Load test the specific endpoints that will be hit (not just homepage)
□ Have someone watching service metrics dashboard during the test
```

**Brainstorming Questions:**
1. You run a load test and p99 latency is fine up to 100 users, then jumps sharply at 101 users. What are the most likely explanations? How would you investigate each?
2. Your service handles 1,000 req/sec with p99=100ms. A new feature adds a database query to each request. Before deploying, how would you estimate the new capacity limit?
3. A load test passes in development but the same service struggles in production at lower load. Name 3 differences between dev and production environments that could explain this.
4. You want to load test a feature that involves multiple services. How do you set up the test to accurately measure end-to-end performance without polluting your production database?

---

## Part 9: Profiling in Production — Continuous Profiling

*(L5 level)*

Most teams only profile when there's a problem. This is reactive profiling. The best teams profile continuously — they always have a picture of where CPU is going.

**The problem with reactive profiling only:**

```
Reactive profiling timeline:
  Monday 9am:  deploy new feature
  Monday 3pm:  latency alert fires
  Monday 3:15: on-call engineer starts profiling
  Monday 3:15→4pm: reproduce the issue, collect profile
  Monday 4:15: find the problem (new feature has N+1 query)
  Monday 4:30: rollback deployed
  
Time from deploy to fix: 7.5 hours. User impact: 4.5 hours.
  
With continuous profiling:
  Monday 9am:  deploy new feature
  Monday 9:15: profiler shows new spike in queryInventory()
  Monday 9:20: engineer notices in profiler UI (new deploy → CPU ↑15%)
  Monday 9:30: hotfix deployed

Time from deploy to fix: 30 minutes. User impact: near zero.
```

**Continuous profiling tools:**

```
Pyroscope (open source, CNCF):
  - Continuous profiling for Go, Python, Java, Node.js
  - Stores profiles over time; query any time window
  - Self-hosted or Grafana Cloud
  
Google Cloud Profiler:
  - Auto-instruments Go, Java, Python, Node.js on GCP
  - < 1% CPU overhead
  - Compare profiles across deploys
  
Datadog Continuous Profiler:
  - Part of Datadog APM
  - Correlates profiles with traces
  
Parca (open source, CNCF):
  - eBPF-based, no code changes needed
  - Profiles any language automatically
```

**Adding Pyroscope to a Go service:**

```go
import "github.com/grafana/pyroscope-go"

func main() {
    pyroscope.Start(pyroscope.Config{
        ApplicationName: "payment-service",
        ServerAddress:   "http://pyroscope:4040",
        ProfileTypes: []pyroscope.ProfileType{
            pyroscope.ProfileCPU,
            pyroscope.ProfileAllocObjects,
            pyroscope.ProfileInuseSpace,
        },
        Tags: map[string]string{
            "version": os.Getenv("APP_VERSION"),
        },
    })
    http.ListenAndServe(":8080", router)
}
```

**The production profiling overhead:**

```
Pyroscope / Parca:      < 1% CPU, < 50MB memory → safe for production
go pprof (on-demand):   0% overhead until triggered → safe
JProfiler (traditional): 10-40% CPU → NOT safe for production

Rule: if overhead > 2%, do NOT run in production.
```

**Brainstorming Questions:**
1. Your company is considering continuous profiling. The main objection is "it adds overhead and we're already CPU-constrained." How would you respond?
2. A continuous profiler shows CPU for your service has gradually increased 5% each month for 3 months. What would you investigate? What could cause gradual CPU creep?
3. You can compare profiler snapshots before and after a deploy. A new feature increased CPU by 15%. How do you decide whether to accept, optimize, or roll back?
4. Continuous profiling shows a spike in `runtime.mallocgc` (memory allocation) every Tuesday at 2pm. What would you investigate to find why this happens specifically on Tuesdays?

---

## Part 10: Full-System Diagnosis Framework

*(L5 → L6 level)*

When a performance problem is reported, the first challenge is: where do you even start? This framework gives you a systematic approach.

**The "5 whys" applied to performance:**

```
Symptom: "checkout is slow"

Why 1: What is slow?
  → p99 latency on POST /checkout is 3,200ms (baseline: 200ms)

Why 2: What changed?
  → Deployed new feature 4 hours ago. Coincides with latency increase.

Why 3: What does the new feature do?
  → Added real-time inventory check before checkout completion.

Why 4: What's slow about the inventory check?
  → Profile shows: inventory.CheckAvailability() = 85% of request time.
    Inside it: N+1 query pattern. 50 DB queries per checkout request.

Why 5: Why does it make 50 queries?
  → For each item in cart, queries inventory table separately.
    Cart averages 50 items. 50 items × 1 DB query = 50 queries.

Root cause: N+1 query in new inventory check feature.
Fix: batch the query with IN(...) clause.
Expected: 50 queries → 1 query → 3,200ms → ~250ms.
```

**The performance diagnosis checklist:**

```
STEP 1: CONFIRM THE PROBLEM
□ Get a reproducible example (specific endpoint, specific load level)
□ Establish baseline: current p50/p95/p99, CPU, memory
□ Confirm when it started (deployment? traffic pattern? data growth?)

STEP 2: CLASSIFY THE PROBLEM
□ CPU-bound? (high CPU under load)
□ I/O-bound? (low CPU, high latency, waiting on DB/network)
□ Memory problem? (growing memory, GC pauses, OOM)
□ Concurrency problem? (latency spikes under concurrent load only)

STEP 3: PROFILE
□ CPU-bound → flame graph (pprof/py-spy/async-profiler)
□ I/O-bound → trace which external calls are slowest
□ Memory → heap profile (inuse_space for leaks, alloc_space for GC)
□ DB → slow query log, EXPLAIN ANALYZE on top queries

STEP 4: ISOLATE THE BOTTLENECK
□ Find ONE function/query/call responsible for > 10% of total time

STEP 5: FIX AND VERIFY
□ Make one change. Re-run baseline. If < 10% improvement: re-profile.

STEP 6: DOCUMENT
□ Before/after numbers. The fix. A regression test.
```

**L5 vs L6 approach:**

```
L5 engineer:
  Gets assigned "checkout is slow." 
  Profiles → finds N+1 query → fixes it → verifies improvement.
  Files PR. Done.

L6 engineer:
  Asks: "How did an N+1 query get into production without being caught?"
  
  Fixes the immediate bug.
  ALSO: adds DB query count assertion to integration tests.
  ALSO: adds load test to CI pipeline with threshold check.
  ALSO: enables pg_stat_statements on staging.
  ALSO: runs EXPLAIN ANALYZE in PR review checklist.
  
  Outcome: this CLASS of bug cannot silently reach production again.
  This is the difference between fixing a bug and fixing the system.
```

**Brainstorming Questions:**
1. You're the on-call engineer. Alert fires: "p99 checkout latency > 3 seconds." Walk through your first 10 minutes of investigation using the framework above.
2. A performance problem appeared 3 days ago but no deployment happened near that time. The only change is the database grew from 50M to 70M rows. How does data growth cause performance problems that didn't exist before?
3. An L5 engineer fixed a performance bug. An L6 engineer asks "how do we prevent this class of bug from recurring?" What are 3 systematic changes that would prevent N+1 queries from reaching production?
4. Your team has a policy: "all API endpoints must have p99 < 500ms under standard load." How would you build enforcement of this policy into your development workflow?

---

## Part 11: Named Real-World Performance Incidents

*(L5 level — named examples for interview credibility)*

**Incident 1: GitHub O(n²) — 2016**

GitHub's code review page was slow for large pull requests. A JavaScript function rendered the diff using an O(n²) algorithm — for each line in the diff, it compared against all other lines. For a 10,000-line diff: 100 million comparisons. Pages took 30+ seconds to load. Found via Chrome DevTools performance profiler (flame graph in browser). Fixed by switching to O(n log n) diffing. Lesson: algorithm complexity problems are invisible at small scale, catastrophic at large scale.

**Incident 2: Stripe Python GIL — 2015**

Stripe ran Python for their API. Under high concurrency, the Global Interpreter Lock (GIL) prevented true parallelism. CPU-bound tasks (HMAC signature verification) blocked all request processing. Profiling showed: 40% of CPU time was in `hmac.new()` calls, but threads were queued waiting for the GIL. More CPUs didn't help — only one thread could run Python at a time. Fix: moved signature verification to a separate process pool (multiprocessing, not threading). Lesson: know your runtime's concurrency model.

**Incident 3: Netflix JVM cold start — 2012**

When Netflix scaled out a new JVM instance during a traffic spike, the new instance served requests 10× slower than established instances. Profiling revealed: the JIT compiler hadn't compiled hot methods yet (requires ~10,000 calls). All requests on a new instance ran interpreted code. Fix: "subscription warming" — new instances get 1% of traffic for 5 minutes before receiving full load. This is standard practice for JVM services today.

**Incident 4: Shopify Ruby GC on Black Friday — 2016**

Shopify's Ruby on Rails services had consistent 500ms p99 spikes on Black Friday. rbspy flame graphs showed Ruby's garbage collector pausing all threads for 50-100ms every few seconds. Under 10× traffic, GC ran more frequently. Fix: tuned `RUBY_GC_HEAP_GROWTH_FACTOR`, upgraded to Ruby 2.5 (generational GC). Lesson: GC tuning is critical for latency-sensitive Ruby/JVM services under burst traffic.

**Incident 5: Facebook TAO thundering herd — 2010**

Facebook's TAO (social graph cache) experienced a thundering herd. When a cache entry expired, 10,000+ requests simultaneously tried to recompute it from the database. The database received 10,000 identical concurrent queries — all timed out. Fix: "probabilistic early expiration" (randomly recompute before expiry) and mutex coalescing (only one thread recomputes; others wait for the result). Lesson: caching at scale has failure modes as bad as no cache at all.

**Incident 6: GitHub October 21, 2018 — MySQL index**

(From Part 7) A network partition caused 34 seconds of replication lag. When the partition healed, a deduplication query with no ORDER BY index ran for 43 minutes on a billion-row table. GitHub was down for ~5 hours. The fix: add the missing index. The postmortem is publicly available at githubengineering.com. Lesson: missing indexes are invisible in development and catastrophic at production data scale.

---

## Part 12: L5 vs. L6 Calibration

```
┌────────────────────────────────────────────────────────────────────────────────┐
│               L3 / L4 / L5 / L6 PERFORMANCE PROFILING CALIBRATION            │
├──────────────┬─────────────────────────────────────────────────────────────────┤
│  L3 (SWE)    │ Knows profiling tools exist. Can run pprof on a Go service.    │
│              │ Reads the top10 output. Makes obvious fixes when pointed out.  │
├──────────────┼─────────────────────────────────────────────────────────────────┤
│  L4 (SSE)    │ Profiles independently. Reads flame graphs.                   │
│              │ Distinguishes CPU-bound from I/O-bound.                        │
│              │ Diagnoses N+1 queries. Runs EXPLAIN ANALYZE.                   │
│              │ Runs basic load tests. Establishes baselines.                  │
├──────────────┼─────────────────────────────────────────────────────────────────┤
│  L5 (Sr SWE) │ Profiles production services with minimal disruption.          │
│              │ Combines profiler + traces + DB slow query log for diagnosis.  │
│              │ Writes load test harness for their service.                    │
│              │ Diagnoses GC pressure, memory leaks, concurrency bottlenecks. │
│              │ Can profile services in languages they don't normally work in. │
│              │ Writes perf improvements with benchmark proof.                 │
├──────────────┼─────────────────────────────────────────────────────────────────┤
│  L6 (Staff)  │ Designs org-level performance culture:                         │
│              │   - Continuous profiling (Pyroscope/Parca) for all services   │
│              │   - Perf budgets in CI: "p99 cannot regress > 10%"            │
│              │   - Load test gates before production launches                 │
│              │   - Perf benchmarks in code review checklist                  │
│              │ Finds systemic problems across services (shared library with   │
│              │ inefficient serialization used by 20 teams).                  │
│              │ Frames performance as a product decision, not just engineering.│
└──────────────┴─────────────────────────────────────────────────────────────────┘
```

**The L6 framing for "performance" in design reviews:**

At staff level, performance is not "make the code faster." It's:
1. **Latency SLOs**: define what "good enough" means before building.
2. **Performance budgets**: "this feature may add no more than 5ms to checkout p99."
3. **Graceful degradation**: "when the system is slow, which features degrade first?"
4. **Cost vs. performance trade-off**: "a 10% latency improvement costs $50K/month in compute — is it worth it?"

---

## Part 13: Pre-Interview Drill — 10 Questions

**Q1: How would you investigate a service that has suddenly become slow?**

"First, I'd establish what 'slow' means: check p50/p99 latency metrics and compare to baseline. If p99 jumped but p50 is normal, it's likely a tail latency issue — GC pauses, lock contention, or specific query patterns. Check whether there was a recent deployment. Then run a flame graph: `go tool pprof` against the live service under load. Find the widest frame in the flame graph that has no wider child — that's the bottleneck. Fix that one thing. Re-measure."

**Q2: What's the difference between CPU-bound and I/O-bound performance problems?**

"CPU-bound: the processor is fully occupied computing. High CPU utilization. Adding more CPU helps. Fix by reducing computation. I/O-bound: the service is waiting — for a database, a network call. CPU is idle at 10-30% even under high load. Adding CPU doesn't help. Fix by reducing wait time: caching, batching, parallelizing I/O."

**Q3: How do you read a flame graph?**

"The X-axis is percentage of CPU samples — wider means more time spent in that function. The Y-axis is call stack depth. Find the widest frame that has no wider child — that's your bottleneck. The X-axis is NOT time sequencing; it's sorted alphabetically within each stack level."

**Q4: What is the N+1 query problem? How do you detect and fix it?**

"N+1: you make 1 query for a list, then N more queries for details on each item. For a list of 100 orders, that's 101 queries. Detect: enable query logging, count queries per request. Fix: use a JOIN or batch the detail queries with a single IN() clause."

**Q5: What does EXPLAIN ANALYZE tell you?**

"EXPLAIN ANALYZE runs the query and shows the actual execution plan with real timings. Most important things: 'Seq Scan' on a large table = no index used = very slow. 'actual time' vs 'estimated rows' discrepancy = stale statistics. The node with the highest actual time is the bottleneck."

**Q6: What is GC pressure and how does it manifest?**

"GC pressure is when a program creates objects so rapidly that the garbage collector runs constantly. Manifests as: regular latency spikes at GC intervals, CPU spikes from GC itself, jittery p99 latency. Fix: reduce allocation rate in hot paths, use object pools, tune GC parameters."

**Q7: How would you load test a new feature before launch?**

"Write a k6 script simulating the expected traffic pattern. Ramp from 0 to 2× expected concurrent users over 5 minutes, hold for 10 minutes. Set thresholds: p99 < SLO target, error rate < 0.1%. Run simultaneously with pprof profiling to see what's causing any degradation. Compare to baseline."

**Q8: What is continuous profiling and why does it matter?**

"Continuous profiling means always running a low-overhead profiler in production, storing results. It catches slow CPU degradation from code changes immediately after deploy, memory leaks over hours, and intermittent spikes that are hard to reproduce. Without it, you only profile reactively after users are already impacted."

**Q9: How would you improve the performance of a system from a design perspective?**

"At design level: (1) Caching — expensive repeated computations, cache the result. (2) Async processing — move non-user-facing work out of the request path. (3) Batching — replace N individual operations with 1 batch operation. (4) Data locality — read replicas near the service. (5) Right data structure — list search is O(n), hash map is O(1)."

**Q10: Tell me about a time you improved a system's performance significantly.**

"At [company], checkout had p99 of 3,200ms. Profiled under load — found N+1 query pattern: 50 DB queries per checkout for inventory check. Fixed with batched IN() query, added missing index that EXPLAIN ANALYZE revealed. Result: p99 from 3,200ms → 180ms, an 18× improvement. Added DB query count assertion to integration tests so this can't recur silently."

---

## Part 14: Exercises

**Exercise 1: Flame graph from scratch**

Take a Go service you've written. Add the pprof HTTP handler. Generate 500 req/sec with wrk or k6. Capture a 30-second CPU profile. Generate a flame graph. Write 3 observations: what's taking the most CPU, whether it's expected or surprising, and what you'd investigate next.

**Exercise 2: Find and fix an N+1 query**

Take any application that uses an ORM. Enable query logging (or use Django Debug Toolbar). Load a list page. Count the number of SQL queries. If there are N+1 queries, fix them. Re-measure. Document: queries before, queries after, and the latency improvement.

**Exercise 3: EXPLAIN ANALYZE experiment**

In PostgreSQL:
1. `CREATE TABLE orders AS SELECT generate_series(1,1000000) id, (random()*10000)::int user_id, random()::float amount;`
2. `EXPLAIN ANALYZE SELECT * FROM orders WHERE user_id = 5000 LIMIT 10;` — note: Seq Scan, actual time.
3. `CREATE INDEX idx_user_id ON orders(user_id);`
4. Re-run EXPLAIN ANALYZE. Compare. Write: how much faster? What changed in the plan?

**Exercise 4: Load test your own project**

Write a k6 ramp test from 10 to 200 concurrent users on any web service you have. Find the point where latency or error rate degrades. Document the "cliff" and form a hypothesis about why it happens there.

---

## Part 15: Homework

**Reading:**
- *Systems Performance* by Brendan Gregg, Ch1-3 (methods overview), Ch5 (CPU profiling), Ch7 (memory). Even just Ch1-3 will fundamentally change how you approach performance problems.
- Brendan Gregg's blog: brendangregg.com — read "Flame Graphs" and "Linux Performance Analysis in 60 Seconds."
- The Google "Tail at Scale" paper (2013) — explains why you must care about p99, not just average.

**At your current job:**
- Find the slowest endpoint in your service. Profile it once using whatever tool fits your language. Write down what you find — even if you don't fix it.
- Open `pg_stat_statements` (or equivalent) on your staging database. Find the top 5 queries by total execution time. Run EXPLAIN ANALYZE on the slowest one.
- Check if pprof (or equivalent) is enabled on your service's staging environment. If not, enable it.

**Research:**
- Read the GitHub October 21, 2018 incident postmortem (search "GitHub October 21 incident"). Write a 3-sentence summary of the missing index problem and how profiling could have caught it earlier.
- Look up "async-profiler safepoint bias" — understand why traditional Java profilers lie and what async-profiler does differently.

---

## Part 16: Vocabulary Quick Reference

```
Flame graph:        Visual profiling output where width = % of total CPU time.
                    Widest frame with no wider child = bottleneck.

CPU-bound:          Performance limited by computation. CPU at 90%+.
                    Fix: reduce computation (better algorithm, caching).

I/O-bound:          Performance limited by waiting. CPU low despite high load.
                    Fix: reduce waits (caching, batching, async I/O).

GC pressure:        High object creation rate forces frequent garbage collection.
                    Manifests as: regular latency spikes, CPU jitter.

N+1 query:          1 query for a list + N queries for per-row details.
                    Fix: JOIN or batch IN() query.

Seq Scan:           Full table scan. Fast for small tables, catastrophic for large.

EXPLAIN ANALYZE:    PostgreSQL: run a query and show actual execution plan + timings.

Safepoint bias:     Traditional Java profilers sample only at JVM safepoints.
                    They miss time in native code and I/O. Use async-profiler.

Continuous profiling: Always-on low-overhead production profiling.
                      Enables retroactive investigation of any time window.

Thundering herd:    Many concurrent requests simultaneously hit a cold resource,
                    overwhelming it. Fix: probabilistic expiration, mutex coalescing.

JIT warm-up:        JVM/V8 compiles hot methods after ~10K calls. New instances
                    start slow. Solution: traffic warming before receiving full load.

Heap dump:          Snapshot of all objects in memory. Used to diagnose leaks.

pprof:              Go's built-in CPU and memory profiler.

py-spy:             Python profiler that attaches to a running process; no code change.

async-profiler:     Java profiler using OS-level signals. No safepoint bias.

p99 latency:        The latency 99% of requests complete within. Never use average.
```

---

## Part 17: Companion Resources

**Primary:**
- *Systems Performance* by Brendan Gregg (2nd ed) — Ch1-3 (methods), Ch5 (CPU), Ch7 (memory). The definitive reference.
- Brendan Gregg's flame graph scripts: `github.com/brendangregg/FlameGraph`
- k6 load testing: `k6.io` — free, excellent documentation

**Tools to try hands-on:**
- Pyroscope continuous profiling: `grafana.com/oss/pyroscope` — run locally in Docker
- pprof: built into Go, no install needed
- async-profiler: `github.com/async-profiler/async-profiler`
- `github.com/open-telemetry/opentelemetry-demo` — instrument and profile a real multi-service system

**Advanced:**
- Brendan Gregg's "BPF Performance Tools" — Linux eBPF profiling at kernel level
- Google's "The Tail at Scale" paper (2013) — why p99 matters more than average

---

## Memorable Quotes

> *"Premature optimization is the root of all evil — but so is premature pessimism. Measure first. Then decide whether optimization is needed."*
> — adapted from Donald Knuth

> *"Adding hardware to fix a software performance problem is like adding more lanes to fix a traffic jam caused by a bad traffic light."*

> *"Your profiler sees what your code review cannot: the path taken 10,000 times, not the path written once."*

> *"The fastest code is code that doesn't run. The second fastest is code that runs once instead of N times."*

---

## Part 18: Micro-Benchmarking — Proving Code-Level Fixes

*(L4 → L5 level)*

A flame graph tells you WHAT is slow. A micro-benchmark proves that your fix actually made it faster. Without a benchmark, you are still guessing — just guessing after the fact.

**Go benchmarks — built into the standard library:**

```go
// payment_test.go
package payment

import "testing"

// Benchmark the slow function you identified in the flame graph
func BenchmarkSerializeOrder(b *testing.B) {
    order := &Order{
        ID:    "ord_123",
        Items: generateTestItems(50),  // 50 items — realistic size
    }
    
    b.ResetTimer()  // don't include setup time
    
    for i := 0; i < b.N; i++ {
        // b.N is determined by the testing framework (runs until stable)
        _ = SerializeOrder(order)
    }
}

// Compare: old implementation vs. new implementation
func BenchmarkSerializeOrderOld(b *testing.B) {
    order := &Order{ID: "ord_123", Items: generateTestItems(50)}
    b.ResetTimer()
    for i := 0; i < b.N; i++ {
        _ = SerializeOrderOld(order)  // old implementation
    }
}

func BenchmarkSerializeOrderNew(b *testing.B) {
    order := &Order{ID: "ord_123", Items: generateTestItems(50)}
    b.ResetTimer()
    for i := 0; i < b.N; i++ {
        _ = SerializeOrderNew(order)  // new implementation
    }
}
```

```bash
# Run benchmarks
go test -bench=BenchmarkSerialize -benchmem -count=5 ./...

# Output:
# BenchmarkSerializeOrderOld-8  45182  26483 ns/op  8192 B/op  203 allocs/op
# BenchmarkSerializeOrderNew-8  312441  3842 ns/op   512 B/op   12 allocs/op

# Reading the output:
# 45182 iterations, 26,483 nanoseconds per call, 8,192 bytes allocated per call
# New: 3,842 ns/op — 6.9× faster
# New: 512 bytes/op — 16× less memory
# New: 12 allocs/op — 17× fewer allocations (less GC pressure)
```

**Commit the benchmark alongside the fix:**

This is critical. The benchmark is documentation that proves the optimization worked. It also serves as a regression test — if someone later changes the code and the benchmark gets 10× slower, the test suite catches it.

```bash
# Add benchmark to CI (run every PR)
# In .github/workflows/benchmark.yml:
- name: Run benchmarks
  run: go test -bench=. -benchmem -count=5 ./... | tee benchmark.txt
  
# Use benchstat to compare before/after
go install golang.org/x/perf/cmd/benchstat@latest
benchstat old.txt new.txt

# Output:
# name                    old time/op    new time/op    delta
# SerializeOrder-8        26.5µs ± 1%    3.84µs ± 2%   -85.51%
# SerializeOrder/alloc-8  8.19kB ± 0%    0.51kB ± 0%   -93.75%
```

**Java JMH — the right way to benchmark Java:**

```java
import org.openjdk.jmh.annotations.*;
import java.util.concurrent.TimeUnit;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@State(Scope.Benchmark)
@Warmup(iterations = 5, time = 1)      // JVM warm-up iterations
@Measurement(iterations = 10, time = 1)
public class SerializationBenchmark {
    
    private Order order;
    
    @Setup
    public void setup() {
        order = new Order("ord_123", generateItems(50));
    }
    
    @Benchmark
    public String serializeWithJackson() {
        return jacksonMapper.writeValueAsString(order);
    }
    
    @Benchmark
    public byte[] serializeWithProtobuf() {
        return order.toProto().toByteArray();
    }
}
```

```bash
mvn clean install
java -jar target/benchmarks.jar

# Output:
# Benchmark                           Mode  Score   Error   Units
# SerializationBenchmark.jackson      avgt  247.3 ± 4.2   µs/op
# SerializationBenchmark.protobuf     avgt   18.9 ± 0.3   µs/op
# 
# Protobuf is 13× faster for this workload.
```

**Why naive benchmarks lie:**

```
Common benchmarking mistakes:

1. Dead code elimination:
   The JVM/Go compiler may optimize away code with no observable side effects.
   for i := 0; i < b.N; i++ {
       result := expensiveFunction()  // compiler sees result is never used!
       // It may eliminate the call entirely
   }
   Fix: assign to a package-level variable or use testing.B.ReportAllocs()
   
2. JVM warm-up:
   Java benchmarks run interpreted in the first N iterations.
   Without warm-up iterations, you're measuring the interpreter, not JIT code.
   JMH handles this automatically with @Warmup.
   
3. Benchmark at unrealistic scale:
   Benchmarking JSON serialization with a 10-field struct when production
   uses 500-field structs. Always benchmark at production-representative size.
   
4. Single-threaded benchmark for concurrent code:
   A lock looks fast when benchmarked with 1 goroutine.
   At 100 goroutines, contention makes it 50× slower.
   Use b.RunParallel() in Go benchmarks for concurrent code.
```

**Brainstorming Questions:**
1. You run a benchmark and the new implementation is 3× faster in the benchmark but only 5% faster in production under load. What could explain the gap? What would you investigate?
2. A colleague says "we don't need benchmarks, we already ran the load test and it was faster." What's the difference between a micro-benchmark and a load test? When do you need each?
3. You're reviewing a PR. The author says "I improved performance." What evidence would you require before approving the PR as a performance improvement?
4. A benchmark shows your new serialization code is 10× faster but uses 3× more memory. Under what production conditions would this trade-off be acceptable? When would it not be?

---

## Part 19: Network Profiling — Diagnosing Latency at the Wire Level

*(L5 level)*

Some performance problems are not in your code at all. The latency is in the network: packet loss, TCP retransmits, TLS handshake overhead, or suboptimal connection pooling. When your code profile shows nothing, check the network.

**The latency breakdown of an HTTP request:**

```
┌────────────────────────────────────────────────────────────────────┐
│              WHERE DOES A 300ms LATENCY GO?                       │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  DNS lookup:        5ms  (only first request; cached after)       │
│  TCP connect:      10ms  (3-way handshake)                        │
│  TLS handshake:    30ms  (certificate exchange, key derivation)   │
│  Request write:     1ms  (sending the HTTP request bytes)         │
│  Server processing: 50ms (your code runs here)                    │
│  Response write:    2ms  (sending the HTTP response bytes)        │
│  TCP teardown:      2ms                                            │
│                   ────                                             │
│  Total:           100ms                                            │
│                                                                    │
│  If your service is behind a proxy:                                │
│    Client → LB: 10ms   LB → Service: 10ms   Service → DB: 5ms    │
│    Each hop adds latency. For 5 hops: 50ms of "pure overhead."    │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

**Common network latency problems:**

```
1. No connection pooling (new TCP/TLS per request):
   Each DB call: 10ms TCP + 30ms TLS = 40ms overhead before the query runs
   At 10 DB calls per request: 400ms of pure connection overhead
   Fix: use a connection pool (keep connections alive)

2. Too many round trips (request/response per operation):
   100 Redis SET operations sequentially = 100 × 0.5ms = 50ms
   Redis pipeline: send all 100 commands, get all 100 responses = ~1ms
   Fix: pipeline multiple operations

3. TLS session not reused (re-negotiating on every request):
   Full TLS handshake: 1 round trip (TLS 1.3) or 2 (TLS 1.2) = 20-40ms
   TLS session resumption: 0 additional round trips = ~1ms overhead
   Fix: ensure TLS session tickets are enabled and the load balancer
        routes the same client to the same backend

4. Large packet size triggering fragmentation:
   IP fragmentation = packets split, reassembled → extra latency
   Fix: check MTU settings; use TCP MSS clamping
```

**Using curl to diagnose HTTP latency breakdown:**

```bash
# curl has a built-in timing breakdown
curl -w "\n\
DNS:        %{time_namelookup}s\n\
Connect:    %{time_connect}s\n\
TLS:        %{time_appconnect}s\n\
TTFB:       %{time_starttransfer}s\n\
Total:      %{time_total}s\n\
" -o /dev/null -s https://api.example.com/checkout

# Output:
# DNS:        0.012s
# Connect:    0.024s    (TCP connect)
# TLS:        0.089s    (TLS handshake added 65ms!)
# TTFB:       0.234s    (time to first byte — server processing)
# Total:      0.238s
#
# Finding: TLS handshake is 65ms — not reusing sessions.
```

**tcpdump for deep network analysis:**

```bash
# Capture traffic to/from your service
tcpdump -i eth0 -w /tmp/capture.pcap host api.example.com and port 443

# Analyze in Wireshark
# Wireshark → Statistics → TCP Stream Graphs → Time-Sequence Graph
# Shows: retransmits, out-of-order packets, zero-window pauses

# Quick summary of TCP retransmits
tcpdump -r /tmp/capture.pcap | grep -i "retransmission" | wc -l
```

**Brainstorming Questions:**
1. Your service calls an external API. The API's own dashboard shows sub-20ms response times, but your service measures 80ms per call. Where could the extra 60ms be coming from?
2. You want to reduce database connection overhead. What is connection pooling, and how does it eliminate TLS/TCP setup time per query?
3. A service makes 50 Redis calls per request. You're considering pipelining them. What's the trade-off between pipelining all 50 vs. pipelining in batches of 10?
4. You notice TLS handshake time is 80ms for external API calls. What are 3 different options to reduce this overhead? (Think: connection reuse, TLS version, session resumption)

---

## Part 20: Performance Anti-Patterns — What NOT to Do

*(L4 → L5 level)*

Knowing what to avoid is as important as knowing what to do. These are the most common performance mistakes made by experienced engineers.

**Anti-pattern 1: Optimize without profiling**

```
❌ "The JSON serialization must be slow — let me switch to protobuf."
   (Without profiling, serialization might be 5% of request time)
   
✅ Profile first. Find that DB queries are 80% of time.
   Fix the DB queries. Then check if serialization is still worth optimizing.
```

**Anti-pattern 2: Optimizing in the wrong environment**

```
❌ "I profiled it locally and it's fast."
   Single-user, small dataset, in-memory SQLite — completely different
   from 100 concurrent users with a 100M-row production database.
   
✅ Profile under production-like load: production-scale data, concurrent
   requests, real network round-trips.
```

**Anti-pattern 3: The premature abstraction tax**

```
❌ A 5-layer abstraction for data access:
   Controller → Service → Repository → DataSource → Adapter → DB
   Each layer adds function call overhead, JSON serialization/deserialization.
   At 100K req/sec, 5 layers × 1µs each = 500ms/second in overhead.
   
✅ Add abstraction layers when they provide real value (testability, swap-ability).
   Don't add them speculatively.
```

**Anti-pattern 4: Caching the wrong thing**

```
❌ Caching responses that are never requested twice
   (UUID-keyed API responses, user-specific real-time data)
   Cache hit rate: 0%. Memory wasted.
   
❌ Not caching expensive reads that are requested constantly
   "What's the list of product categories?" — 10K req/sec, all going to DB
   
✅ Cache things that are: expensive to compute AND requested multiple times.
   Rule: before adding cache, ask "what's the expected hit rate?"
   If < 50% hit rate → probably not worth caching.
```

**Anti-pattern 5: Synchronous calls that could be asynchronous**

```
❌ In a checkout request:
   1. Charge payment          (required before confirmation)
   2. Update inventory        (required before confirmation)
   3. Send confirmation email (NOT required for checkout to complete)
   4. Log analytics event     (NOT required)
   5. Update recommendation model (NOT required)
   
   Total latency: sum of all 5 operations
   
✅ Move non-required operations out of the request path:
   1. Charge payment          (synchronous — required)
   2. Update inventory        (synchronous — required)
   3-5. Publish event to queue → handled by background workers
   
   Request latency: only steps 1-2. Steps 3-5 happen asynchronously.
```

**Anti-pattern 6: SELECT * on large tables**

```
❌ SELECT * FROM users WHERE id = 123
   Fetches: id, email, name, address, phone, bio, avatar_url, preferences_json,
            created_at, updated_at, last_login, stripe_customer_id, ...
   If the caller only needs: id, name, email — you fetched 20× too much data.
   
   At 10K req/sec × 1KB extra per row × 20K rows per page = 200MB/sec wasted
   
✅ SELECT id, name, email FROM users WHERE id = 123
   Fetch only the columns you need.
```

**Anti-pattern 7: Not understanding your cache expiration**

```
❌ Set-and-forget caching:
   Cache all user profiles with TTL=1 hour.
   Under load: 10,000 profiles expire at the same time (all set at startup).
   Database receives 10,000 concurrent queries → thundering herd.
   
✅ TTL jitter: add random 0-60 seconds to TTL.
   cache.set(key, value, ttl=3600 + random.randint(0, 300))
   Spreads expirations over 5 minutes instead of all at once.
```

**Brainstorming Questions:**
1. Your team is debating whether to add caching to an endpoint. The endpoint queries user profiles, which change infrequently. What questions would you ask to decide if caching is appropriate? What would make you say "no"?
2. A service has 8 layers of abstraction. You're asked to improve its performance. Before touching any layer, what would you measure? What would indicate the abstraction layers are the problem vs. something else?
3. You're building a checkout flow. List 5 operations that happen during checkout. For each, decide: synchronous (must complete before confirming the order) or asynchronous (can happen after). Justify each decision.
4. "SELECT *" is common in ORM-generated code. In what scenario would SELECT * be acceptable? When is it clearly harmful?

---

## Part 21: Performance Budgets — Preventing Regression

*(L5 → L6 level)*

A performance budget is a pre-agreed limit on how slow a feature or endpoint can be. Without a budget, every engineer makes a local trade-off ("this is only 10ms more") and the sum is 500ms of accumulated regression over 2 years.

**The performance budget concept:**

```
Before: each PR is judged on "does it work?"
After:  each PR is judged on "does it work AND does it stay within budget?"

Example budgets:
  /api/checkout p99 latency: 500ms (SLO)
  New feature may add maximum: 10ms to /checkout p99
  
  If a new feature adds 50ms → exceeds budget → rejected or needs optimization.
```

**Implementing performance budgets in CI:**

```yaml
# GitHub Actions: performance gate
# .github/workflows/perf.yml
name: Performance Budget Check

on: [pull_request]

jobs:
  perf-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Start service
        run: docker-compose up -d
        
      - name: Warm up
        run: sleep 10
        
      - name: Run k6 benchmark
        run: |
          k6 run --out json=results.json \
            --vus 50 --duration 60s \
            ./tests/perf/checkout.js
          
      - name: Check thresholds
        run: |
          p99=$(jq '.metrics.http_req_duration.values["p(99)"]' results.json)
          if (( $(echo "$p99 > 500" | bc -l) )); then
            echo "❌ PERFORMANCE REGRESSION: p99 ${p99}ms > 500ms budget"
            exit 1
          else
            echo "✅ p99 ${p99}ms within 500ms budget"
          fi
```

**Go benchmark regression detection:**

```bash
# Add to CI: compare benchmark results to main branch
# Step 1: run benchmarks on main branch, save results
git checkout main
go test -bench=. -benchmem -count=10 ./... > main.txt

# Step 2: run benchmarks on PR branch
git checkout feature-branch
go test -bench=. -benchmem -count=10 ./... > pr.txt

# Step 3: compare
benchstat main.txt pr.txt

# Output:
# name                    old time/op    new time/op    delta
# SerializeOrder-8        26.5µs ± 1%    52.3µs ± 2%   +97.4%  (p=0.000)
# ← 97% slower! This PR will be rejected.
```

**Web performance budgets (front end):**

```
Performance budgets apply to web apps too:
  First Contentful Paint (FCP): < 1.8s
  Time to Interactive (TTI):    < 3.9s
  Total page weight:            < 500KB JavaScript
  
Tools:
  Lighthouse CI (lighthouse-ci): fails PR if score drops below threshold
  Bundlewatch: fails PR if bundle size exceeds budget
  
Example Lighthouse CI config:
  assert:
    assertions:
      'first-contentful-paint': ['error', { maxNumericValue: 1800 }]
      'interactive': ['error', { maxNumericValue: 3900 }]
      'total-blocking-time': ['warn', { maxNumericValue: 300 }]
```

**Brainstorming Questions:**
1. Your team doesn't have performance budgets. How would you introduce them? What resistance would you expect, and how would you address it?
2. A performance budget for /api/search is p99 < 200ms. A new feature requires a new database join that adds 30ms. The p99 would be 230ms — over budget. How would you handle this? (Think: 3 options)
3. Performance budgets in CI add CI run time. If a perf test takes 10 minutes and runs on every PR, with 50 PRs/day that's 500 minutes/day. How would you mitigate this cost while keeping the protection?
4. You inherit a codebase with no performance budgets and dozens of endpoints. How would you prioritize which endpoints to add performance budgets for first?

---

## Part 22: Profiling Final Checklist

Before declaring a performance problem "solved":

```
INVESTIGATION:
□ I measured the baseline before making any changes
□ I profiled under production-like load, not just development load
□ I identified ONE root cause (not guessed at several simultaneously)
□ I confirmed the root cause with a specific tool (flame graph / EXPLAIN / heap dump)

FIXING:
□ I made exactly ONE change per measurement cycle
□ I have a before/after comparison for the specific change I made

VERIFICATION:
□ p50, p95, AND p99 all improved (not just the average)
□ Error rate did not increase
□ Memory usage did not unexpectedly increase
□ I ran the fix under the same load profile as the baseline

PREVENTING REGRESSION:
□ I added a benchmark test or load test threshold to CI
□ If a DB query was the issue, I verified the index with EXPLAIN ANALYZE
□ The fix is reviewed by a teammate who understood the root cause
□ I wrote up the investigation: symptom → profile → root cause → fix → result

DOCUMENTATION:
□ The improvement is quantified: "p99 from 3200ms to 180ms"
□ The benchmark commit is in the same PR as the fix
□ Future engineers can understand why the code is structured this way
```

**The one-sentence summary of this chapter:**

Performance profiling is not a skill you use once a month during incidents. It is a discipline you apply before shipping every major feature: profile under load, establish a budget, verify you stayed within it, add a regression test, ship with confidence.

**The intern → staff progression in one view:**

```
Intern:  "This is slow."
         → restarts the service and hopes for the best

L3:      Learns pprof exists.
         Runs top10 when pointed to the problem.
         Fixes the obvious thing the profiler shows.

L4:      Profiles independently.
         Reads flame graphs. Distinguishes CPU vs I/O.
         Runs EXPLAIN ANALYZE. Writes a k6 load test.
         Adds an index, measures improvement.

L5:      Profiles production safely.
         Combines flame graphs + traces + DB slow query log.
         Diagnoses GC pressure, memory leaks, concurrency.
         Adds benchmark to the PR. Verifies p99, not just average.

L6:      Builds the system that catches performance regressions
         before they reach users.
         Performance budgets in CI. Continuous profiling for all services.
         Teaches the team to profile. Makes profiling the default habit.
         Frames performance trade-offs as product and business decisions.
```

The goal is not to be the fastest coder. The goal is to be the engineer whose services stay fast — because they measure, because they set budgets, and because they built the guardrails that protect the whole team from accidental regression.

---

## Exercises

**Exercise 1 — Flame graph analysis.** Generate a CPU flame graph for a service you own using `go pprof`, `py-spy`, or async-profiler. Identify the top 3 hottest stack frames. For each: is this expected, is there an optimization opportunity, and what's the estimated speedup?

**Exercise 2 — CPU vs I/O diagnosis.** Design a 5-minute diagnostic flow for a service experiencing latency spikes. What metrics/tools do you check in what order to determine CPU-bound vs. I/O-bound? Write the decision tree.

**Exercise 3 — GC profiling.** For any JVM or Go service: find GC frequency, pause duration (P50 and P99), and heap utilization. Is GC a bottleneck? What configuration change or code change reduces GC pressure?

**Exercise 4 — N+1 detection and fix.** Design a REST endpoint that returns 100 users with their last 5 orders each. Observe the query log: you see 101 queries. Explain the N+1 pattern, how to detect it in production (APM trace, query count metric), and two ways to fix it.

**Exercise 5 — Benchmark design.** Compare two JSON serialization libraries. Design the benchmark: what to measure, how to prevent JIT warmup effects, how to ensure realistic payload sizes, and how to control for environment noise.

**Exercise 6 — Performance regression test.** Write a test that fails if P99 latency for your critical endpoint exceeds 100ms under 500 RPS load. What load testing tool do you use, how do you integrate it into CI, and what's the acceptable flakiness rate?

---

## Homework

**Assignment 1 — Profile a production service.** Profile any service you own under realistic load. Identify top 3 CPU consumers and top 3 allocation sources. Write a one-page analysis with one optimization recommendation.

**Assignment 2 — Latency attribution.** For your slowest endpoint: break down latency by component (DB, serialization, network, app code). Use APM traces or custom instrumentation. Implement one optimization and measure the improvement.

**Assignment 3 — Interview practice: P99 investigation.** Practice "your API has P99 500ms but P50 20ms — what do you do?" in 10 minutes. Cover: what this gap tells you, diagnostic approach, likely causes, and two possible fixes.

**Assignment 4 — Read "Systems Performance" (Brendan Gregg), Chapter 2.** Write a one-paragraph summary of the 60-second Linux performance analysis checklist and how you'd apply it to a production service experiencing latency spikes.

*Pairs with [Chapter 121: Observability and Instrumentation](Chapter_121_Observability_and_Instrumentation.md) and [Chapter 117: Capacity Planning](Chapter_117_Capacity_Planning.md). Next: [Chapter 123: Technology Evaluation Framework](Chapter_123_Technology_Evaluation_Framework.md).*

*Pairs with [Chapter 121: Observability and Instrumentation](Chapter_121_Observability_and_Instrumentation.md) (metrics reveal WHAT is slow; profiling reveals WHY) and [Chapter 117: Capacity Planning](Chapter_117_Capacity_Planning.md) (profiling informs capacity decisions). Next: [Chapter 123: Technology Evaluation Framework](Chapter_123_Technology_Evaluation_Framework.md).*