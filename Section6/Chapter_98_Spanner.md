# Chapter 84: Spanner — Google's Globally Distributed Database

> "Spanner is the first system to distribute data at global scale and support
> externally-consistent distributed transactions. The key enabler is TrueTime,
> a globally synchronized clock API with bounded uncertainty."
> — Corbett et al., "Spanner: Google's Globally-Distributed Database" (OSDI 2012)

---

## Why This Chapter Matters

Imagine you are shopping on an e-commerce site. You pay for an item. The payment
goes through. Two seconds later, you refresh the order page and it still says
"payment pending." That is a consistency failure — and in a world where servers
are spread across continents, making it impossible is one of the hardest problems
in computer science.

Google Spanner is the system that solved this at planetary scale. Not with clever
hacks or relaxed guarantees, but with atomic clocks, GPS receivers, and a brilliant
mathematical insight about time. It runs Google's most critical services — Google
Ads (a $200+ billion/year business), Google Play, Google Finance, and many internal
systems. When Google engineers needed something that could never lose data, never
show stale reads, and span the entire planet, they built Spanner.

For senior software engineering interviews (L5/L6 at Google, Meta, Amazon), Spanner
comes up constantly in questions about:
- "Design a globally consistent payment system"
- "How would you implement cross-region ACID transactions?"
- "What is external consistency and how is it different from serializability?"
- "Why would you choose CockroachDB over Spanner?"

This chapter will teach you not just what Spanner is, but how it works at a level
where you can discuss the trade-offs confidently. We will build from first principles,
using simple analogies, then progressively deepen the technical detail. By the end,
you will understand TrueTime, commit-wait, Paxos groups, and interleaved tables well
enough to whiteboard a Spanner-inspired design from scratch.

---

## Prerequisites

Before reading this chapter, make sure you understand:
- Basic ACID properties (Chapter 18)
- Paxos/Raft consensus (Chapter 26)
- Hybrid Logical Clocks (Chapter 27)
- The CAP theorem (Chapter 10)
- Two-phase commit (Chapter 20)

If any of those feel fuzzy, skim those chapters first. Spanner builds on all of them.

---

## Part 1: The Problem — Why Global Consistency is Hard

### 1.1 Starting with Something Simple

Let's start with a question that sounds easy: can two computers agree on what time
it is, right now?

Your instinct might be "yes, just sync them to a time server." And you are not wrong.
NTP (Network Time Protocol) does exactly that. But here is the problem: NTP is not
perfectly accurate. Depending on network conditions, two servers synced via NTP might
have clocks that differ by anywhere from a few milliseconds to hundreds of milliseconds.
That gap is called clock skew.

Now: why does clock skew matter for databases?

Imagine two transactions happening simultaneously across two datacenters:

- Server A (in Virginia): "Transfer $1,000 from Alice's account to Bob's account"
  This commits at wall clock time 10:00:00.005 AM (5 ms past midnight)

- Server B (in Oregon): "Alice checks her balance"
  This starts at wall clock time 10:00:00.003 AM (3 ms past midnight)

The transfer happened AFTER Alice started checking her balance (5ms > 3ms). But
if Oregon's clock is running 10ms slow relative to Virginia's, Oregon might think
the balance check happened at 10:00:00.013 AM — which is AFTER the transfer.
Oregon would then think: "Alice must see the deducted balance," even though Alice's
check logically started before the transfer committed.

This is the fundamental problem: in a distributed system, wall-clock time is not
trustworthy enough to determine which event happened first.

### 1.2 The Single-Datacenter Case is Solved

Before we tackle the hard case, note that single-datacenter ACID is effectively
a solved problem. Databases like PostgreSQL, MySQL, and Oracle manage transactions
within one datacenter using:
- A single authoritative clock (the server clock)
- Two-phase locking or MVCC
- Write-ahead logging for durability

When everything lives in one building with one primary clock, you do not need TrueTime.
The problems start when you want data in multiple geographic regions.

### 1.3 Why Do You Even Want Global Distribution?

Three main reasons:
1. **Disaster recovery**: If your single datacenter burns down, you lose everything.
   With three datacenters on three continents, one can fail and the system keeps running.
2. **Low latency for global users**: A user in Tokyo reading data from Virginia waits
   ~150ms for the round-trip. If there's a replica in Tokyo, they wait 5ms.
3. **Compliance**: Some countries require user data to be stored within their borders.
   A globally distributed database lets you place data in the right regions.

But the moment you replicate data across multiple datacenters, you face a choice
described by the CAP theorem: you cannot have both perfect consistency and perfect
availability when the network partitions. Most systems (Cassandra, DynamoDB) chose
availability. Spanner chose consistency.

### 1.4 External Consistency: The Strongest Guarantee

Let's define the guarantee Spanner provides, because it is stronger than what most
databases offer.

**Serializability** (what PostgreSQL gives you): transactions execute as if they
happened one at a time, in some order. But that order doesn't have to match
real-world time. Two transactions could commit at the same real-world second,
and the database picks an order arbitrarily.

**External consistency** (what Spanner gives you): if Transaction T1 commits before
Transaction T2 even starts (in real wall-clock time), then T2 is guaranteed to see
all of T1's writes. The order the database picks MUST respect real-world time.

This sounds like a subtle difference, but it matters enormously in practice.

Example: In a financial system, a wire transfer T1 commits at 3:00:00.000 PM.
At 3:00:00.001 PM, a fraud detection job T2 starts scanning recent transactions.
With external consistency, T2 is guaranteed to see the wire transfer. Without it,
T2 might run based on a snapshot from before T1 committed — missing the fraud.

External consistency is sometimes called "linearizability for transactions" or
"strong external consistency." It is the gold standard, and it requires solving
the clock problem.

### 1.5 The Clock Problem in Depth

Here is the core issue, stated precisely:

To implement external consistency, you need to assign each transaction a commit
timestamp such that the timestamps respect real-world order. If T1 commits before
T2 starts, T1's commit timestamp must be numerically less than T2's commit timestamp.

But to do that, you need to know the real current time with certainty. And no
off-the-shelf hardware gives you that. Clocks drift, networks delay NTP packets,
and even within a datacenter, server clocks can be tens of milliseconds apart.

The approaches before Spanner were:
1. **Lamport clocks**: logical clocks that track causality but not wall-clock time.
   They give you ordering but not external consistency.
2. **Vector clocks**: track per-process causality. Good for tracking "happened-before"
   but don't map to real time.
3. **Two-phase commit with versioned timestamps**: approximately correct but could
   violate external consistency under clock skew.
4. **Serializability with locks**: correct within a datacenter, but cross-datacenter
   2PC is extremely slow (hundreds of milliseconds per transaction).

Google's insight: what if instead of pretending clocks are accurate, you quantify
exactly how inaccurate they are, and build your protocol around that uncertainty?
That insight became TrueTime.

### 1.6 Real Story: Before Spanner — Google Ads and the Pain of Manual Sharding

Before 2012, Google's advertising system used a custom-built database called F1
(later renamed when it moved to Spanner). F1 was built on sharded MySQL with
manual cross-shard transaction management. Each shard was a master MySQL instance
with read replicas. Cross-shard operations required careful application-level
coordination.

The engineering team estimated they spent roughly 30% of their time managing
consistency edge cases — what happens if the master crashes mid-transaction, what
happens if a shard rebalance races with a write, how to ensure a campaign budget
update is visible globally before ad serving continues. They experienced about three
consistency-related outages per year, each requiring manual intervention.

When the F1/Spanner migration completed (announced in the 2013 F1 paper), they
reported: zero consistency-related outages, global ACID transactions with sub-50ms
latency, and developers no longer worrying about cross-shard coordination. The
trade-off was slightly higher latency for individual writes — but the elimination
of an entire category of bugs was worth it.

---

### Part 1 Brainstorming Q&A

**Q1: Why not just use NTP more carefully? Can't you just keep clocks in sync within
1ms and call it good?**

NTP synchronization to within 1ms is theoretically achievable in a stable data-center
network, but it is fragile in practice. NTP accuracy degrades during network congestion,
during failovers, when nodes restart, and under packet loss. More importantly, the
uncertainty is not bounded — you cannot prove that two servers are within 1ms of each
other, you can only estimate it. For a financial database, "usually within 1ms" is not
acceptable because even rare violations can cause money to disappear or consistency to
be silently broken.

Additionally, even if you achieve 1ms accuracy, your transaction protocol still has to
account for that 1ms gap. You either add a 1ms stall (similar to TrueTime's commit-wait)
or you risk violations. Google's insight was to make the uncertainty explicit and build
a correct protocol around it, rather than hoping it stays small.

**Q2: What does "external consistency is stronger than serializability" actually mean
in a concrete scenario?**

Here's a concrete example. Suppose Alice and Bob are using a collaborative document.
Alice saves a change (T1 commits). She then texts Bob: "I just saved, refresh the page."
Bob refreshes (T2 starts after receiving the text, which is after T1 committed).

With only serializability, the database could assign T1 and T2 an ordering that doesn't
match reality — T2 might read a snapshot from before T1 committed. Bob would refresh and
not see Alice's change. With external consistency, since T1 committed before T2 started
in real wall-clock time, T2 is guaranteed to see T1's change. Bob's refresh will always
show Alice's update. This "real-time ordering" guarantee is what external consistency adds
on top of serializability.

**Q3: Couldn't you just put all transactions through a single global sequencer? Give
every transaction a sequence number from a single machine?**

A single global sequencer is actually used by some systems (like Google's older Megastore
and Chubby-based designs). The problem is throughput and availability. A single sequencer
is a bottleneck: every transaction on the planet must touch it, limiting you to maybe
100,000 sequences/second. If the sequencer goes down, everything stops. You can't shard
the sequencer without recreating the original problem. Spanner's TrueTime approach avoids
this bottleneck entirely: each Paxos leader independently assigns timestamps using the
local TrueTime API, with no global coordination required. The GPS and atomic clock
infrastructure does the coordination implicitly through the laws of physics.

---

## Part 2: TrueTime — The Clock That Makes It Possible

### 2.1 The Big Idea: Embrace Uncertainty

Most systems treat clock uncertainty as a bug — something to minimize and hope doesn't
cause problems. TrueTime treats it as a feature. TrueTime is an API that tells you not
just the current time, but how uncertain it is. Instead of returning "it is 10:00:00.005,"
TrueTime returns "the current time is somewhere between 10:00:00.002 and 10:00:00.008."

That range — the gap between earliest and latest — is called the uncertainty interval,
denoted by the Greek letter epsilon (ε). In Google's production system, ε is typically
between 1ms and 7ms. Google's goal is to keep it under 10ms.

### 2.2 The TrueTime API

TrueTime exposes three methods:

```
TT.now()   → returns TTinterval [earliest, latest]
TT.after(t) → returns true if t has definitely passed (TT.now().earliest > t)
TT.before(t) → returns true if t has definitely not happened (TT.now().latest < t)
```

The `TTinterval` is a pair of timestamps `[t_earliest, t_latest]` where the actual
current time is guaranteed to be somewhere in that interval. The interval width is 2ε.

This is the crucial guarantee: the API never lies. If TrueTime says the current time
is between 10:00:00.002 and 10:00:00.008, the actual current time is definitely in
that range. It might be 10:00:00.003, or 10:00:00.007, but it is NOT 10:00:00.001
and it is NOT 10:00:00.009.

```
                    TRUETIME UNCERTAINTY WINDOW
                    ===========================

   ACTUAL TIME IS GUARANTEED TO BE IN HERE
        |                               |
        v                               v
   ─────[══════════════════════════════]─────────────────▶ time
        ▲                               ▲
     t_earliest                      t_latest
        (TT.now().earliest)          (TT.now().latest)

        |<────────── 2ε ────────────>|

        Typical ε: 1ms to 7ms
        Typical 2ε: 2ms to 14ms

   WHAT THIS MEANS:
   If I call TT.now() and get [002, 008]:
   - The real time might be 002 (the moment after I called)
   - The real time might be 008 (clock is running a little slow)
   - But the real time is NOT outside [002, 008]
```

### 2.3 The Hardware Behind TrueTime

TrueTime works because Google installed special hardware in every datacenter:
- **GPS receivers**: These receive timing signals from GPS satellites, accurate to
  within ~100 nanoseconds of UTC.
- **Atomic clocks (cesium or rubidium)**: These keep extremely accurate time even
  when GPS signals are unavailable.

Each datacenter has multiple "time master" machines with GPS antennas or atomic clocks.
Other machines query these time masters frequently and apply statistical algorithms
to compute their best estimate of current time and the uncertainty of that estimate.

The time masters cross-check each other. If one time master disagrees significantly
with the others, it is assumed to be faulty and excluded. This is similar to a voting
system: you believe the majority.

The uncertainty interval ε grows when:
- A machine has not recently synced with a time master
- Time masters disagree with each other
- GPS signal is temporarily lost (rare, usually < 30 seconds)

Under normal conditions (all time masters healthy, GPS signals good), ε is around 1-4ms.
Under degraded conditions, it might reach 7ms. Google's protocol design keeps the system
correct even when ε = 10ms.

### 2.4 An Analogy: The Referee's Flag

Think of TrueTime like a football referee with a slightly imprecise flag.

When a player steps out of bounds, the referee throws the flag. The player might say:
"I stepped out at exactly second 47.3." But the referee says: "Based on what I saw,
it was somewhere between second 47.1 and second 47.5." The referee doesn't know exactly,
but they know the bounds.

Now imagine two referees at different ends of the field. Each has slightly different
clocks. But both use the GPS system synchronized to the same satellite, so they know
their clocks agree within 10ms. If they both throw flags, they can order events
correctly as long as events are at least 10ms apart.

TrueTime is the referee system. The GPS satellite is the atomic clock. The 10ms gap
between events is enforced by the commit-wait protocol (coming in Part 3).

### 2.5 Why GPS + Atomic Clocks, Not Just GPS?

GPS alone gives you accurate time, but GPS receivers can temporarily lose satellite
signals (atmospheric interference, equipment failure, urban canyons blocking signal).
If that happens and you are only relying on GPS, your clock drifts immediately.

Atomic clocks are extremely stable. A cesium atomic clock drifts less than 1 nanosecond
per day. But they drift — just very slowly. Without external correction (GPS sync),
an atomic clock would be off by microseconds per year, which is fine for most things
but accumulates.

The combination is perfect: GPS provides the absolute reference when available. The
atomic clock holds the fort when GPS is temporarily unavailable, drifting so slowly
that even a 30-minute GPS outage adds only nanoseconds of error. This combination keeps
ε small and bounded even during hardware failures.

### 2.6 How TrueTime Uncertainty Stays Bounded

Here is the algorithm each machine uses:

1. **Query time masters**: Every 30 seconds (or less), query multiple time masters
   in the datacenter for their time estimate.
2. **Filter and average**: Use Marzullo's algorithm (a statistical technique) to
   compute the intersection of all time master responses, excluding outliers.
3. **Compute uncertainty**: The uncertainty ε is the spread of that intersection
   plus the maximum expected clock drift since the last sync.
4. **Update local time**: Set local clock and track drift rate.

Between syncs, the local clock drifts. The drift rate of typical server hardware
is at most 200 microseconds per second (200 ppm). Over 30 seconds between syncs,
that's at most 6ms of drift. Adding some margin, you get ε ≈ 7ms as a worst case.

### 2.7 TrueTime vs. Hybrid Logical Clocks

If you read Chapter 27 on HLC, you know that CockroachDB uses Hybrid Logical Clocks
instead of TrueTime. Here is the comparison:

**TrueTime (Spanner)**:
- Requires GPS + atomic clock hardware in every datacenter
- Uncertainty interval ε is bounded and small (1-7ms)
- Commit-wait stall is deterministic: wait ε ms then commit
- Works even when machines are completely isolated
- Cannot be run outside Google's datacenters (no GPS hardware)

**Hybrid Logical Clocks (CockroachDB)**:
- Pure software solution, no special hardware
- Uncertainty is bounded but larger (up to 500ms in production)
- No commit-wait stall (uses causality tracking instead)
- Slightly weaker guarantee: "causally consistent" rather than externally consistent
- Runs on any hardware, including AWS or your laptop

For most companies, HLC is the practical choice because you cannot install GPS
receivers in AWS. But for Google, TrueTime enables a stronger guarantee at lower
latency cost.

---

### Part 2 Brainstorming Q&A

**Q1: If TrueTime uncertainty is 1-7ms, doesn't that mean all transactions are at
least 1-7ms slower than they would be otherwise? Is that a lot?**

Yes, TrueTime's commit-wait adds 1-7ms to every write transaction's commit phase.
Whether that is "a lot" depends on the use case. For global transactions that are
already paying 50-150ms of cross-continent latency for Paxos replication, adding
7ms is a small overhead — roughly 5-10%. For local single-datacenter transactions
where the baseline is 5ms, adding 7ms doubles the latency.

Google reports that in their production workload (F1/Google Ads), the average
commit-wait was around 5ms and the overall P99 write latency was acceptable (under
50ms for cross-region). The engineers decided the correctness guarantee was worth
the latency cost. If you need sub-millisecond writes and can tolerate slightly weaker
consistency, a single-region database without commit-wait is the better choice.

**Q2: What happens if a GPS receiver in a datacenter fails? Does Spanner stop working?**

No — and this is important for Spanner's design. Each datacenter has multiple time
masters with independent GPS receivers and atomic clocks. If one GPS receiver fails,
the time master using that receiver recognizes the problem (GPS data becomes stale),
marks itself as uncertain, and widens its uncertainty estimate. Other time masters
continue providing accurate time. The overall ε for machines in that datacenter might
increase slightly (because they have fewer healthy masters to sync with), but the
system remains correct. If all GPS receivers in a datacenter fail simultaneously
(extremely rare), the atomic clocks hold the fort with their very low drift rate until
GPS is restored. Spanner has never had a TrueTime-related correctness failure in
production.

**Q3: Can I use TrueTime for my own application? Can CockroachDB or YugabyteDB use it?**

TrueTime is a Google-internal API. The underlying GPS and atomic clock infrastructure
is Google's private hardware, deployed in Google-owned datacenters. External users
of Google Cloud Spanner benefit from TrueTime indirectly (Cloud Spanner provides
external consistency), but they cannot call the TrueTime API themselves.

CockroachDB and YugabyteDB cannot use TrueTime because they run on commodity hardware
on AWS, Azure, or GCP — none of which have the GPS hardware. This is why they use HLC:
it provides a software-only bounded uncertainty estimate. AWS has been working on
a similar concept (Amazon Time Sync Service with sub-millisecond accuracy), but it
does not have the same guarantees as TrueTime. If you are designing a new database
for Google Cloud, you can use Cloud Spanner which uses TrueTime internally. If you
are designing for AWS, CockroachDB or YugabyteDB are the pragmatic alternatives.

---

## Part 3: Commit-Wait — How TrueTime Enables External Consistency

### 3.1 The Commit-Wait Protocol Explained Simply

Imagine you are writing a timestamp on a check. You want every check you write today
to have a higher number than every check you wrote yesterday. But your pen sometimes
skips, and you are not sure exactly what time it is. TrueTime's solution: after you
decide the check's timestamp, wait until you are absolutely sure that time has passed
before letting anyone see the check. Then no future check can ever have an earlier
timestamp, because by the time they get processed, more time has passed.

That is commit-wait in one paragraph.

Here is the formal protocol, step by step:

### 3.2 Step-by-Step: What Happens During a Write Transaction

Let's say you are buying concert tickets (transaction T1). Here is exactly what
Spanner does:

**Step 1: Acquire locks**
The Paxos leader for each data shard involved acquires write locks on the relevant
rows. (This is the "2PL" phase — two-phase locking).

**Step 2: Prepare phase (2PC prepare)**
The transaction coordinator sends "prepare" messages to all participating Paxos
groups (if the transaction touches multiple shards). Each group logs the prepare
request to Paxos (durably). Each participant responds "I am prepared to commit."

**Step 3: Choose a commit timestamp**
The transaction coordinator calls `TT.now()` and gets back `[t_earliest, t_latest]`.
It picks the commit timestamp `s = t_latest`. This is the key step: by picking the
highest end of the uncertainty window, the coordinator ensures that `s` is at least
as large as the real current time.

```
CHOOSING THE COMMIT TIMESTAMP
==============================

  TT.now() returns [002, 008]
  (actual time is somewhere in this range)

  Coordinator picks: s = 008  (t_latest)

  WHY? Because s ≥ actual_current_time
  (since actual_current_time ≤ t_latest = 008)
```

**Step 4: Commit-wait — the crucial stall**
The coordinator does NOT commit yet. It waits until `TT.now().earliest > s`.
In other words, it waits until it is absolutely sure that real time has passed `s`.

```
COMMIT-WAIT TIMELINE
====================

t=000ms: Transaction starts
t=010ms: Locks acquired
t=020ms: Prepare phase complete
t=021ms: TT.now() called → [021, 027]
          Commit timestamp s = 027 chosen

t=021ms: COMMIT-WAIT BEGINS
          "Wait until TT.now().earliest > 027"

t=022ms: TT.now() = [022, 028] → earliest=022, 022 < 027, keep waiting
t=024ms: TT.now() = [024, 030] → earliest=024, 024 < 027, keep waiting
t=027ms: TT.now() = [027, 033] → earliest=027, 027 = 027... still wait
t=028ms: TT.now() = [028, 034] → earliest=028, 028 > 027 ✓ DONE!

t=028ms: COMMIT ACTUALLY HAPPENS
          Locks released, writes visible to other transactions

Total commit-wait stall: ~7ms (≈ ε)
```

**Step 5: Commit and release locks**
After the commit-wait, the coordinator sends "commit" to all participants. They
apply the writes, log to Paxos, and release locks.

**Step 6: Acknowledge to client**
The client receives a success response. The transaction is now complete.

### 3.3 Why Commit-Wait Enables External Consistency

Let's prove that commit-wait works. Suppose T1 commits before T2 starts in real
wall-clock time. We want to show that T2's timestamp > T1's timestamp.

**T1's commit timestamp**: s1 = t_latest when T1 called TT.now() before committing.
After commit-wait, we know real time > s1.

**T2 starts after T1 commits**: In real wall-clock time, T2 starts after T1 committed.
Since T1 committed (real time > s1), and T2 starts after that, real time when T2
starts is > s1.

**T2's commit timestamp**: When T2 calls TT.now(), it gets [t_earliest, t_latest].
Since TrueTime is correct, t_earliest ≤ real time. And real time > s1. So T2 picks
s2 = t_latest ≥ t_earliest > s1. Therefore s2 > s1. QED.

The commit-wait is what makes step 3 work. Without the stall, real time might still
be ≤ s1 when T1 "commits," and a concurrent T2 might pick a timestamp ≤ s1.

```
EXTERNAL CONSISTENCY PROOF (SIMPLIFIED)
=========================================

T1:  [──── work ────][WAIT until real_time > s1][COMMIT at s1]──────────
                                                              ↑
                                              T1 commits here (real time > s1)
                                                              ↓
T2:  ─────────────────────────────────────────────[starts here]──────────
                                                  real_time > s1
                                                  T2.TT.now().earliest > s1
                                                  So T2 picks s2 > s1 ✓

     RESULT: s2 > s1 → T2 sees T1's writes → External Consistency!
```

### 3.4 The Cost of Commit-Wait

Commit-wait adds ε milliseconds to every write transaction. You cannot avoid this
if you want external consistency. This is the fundamental latency tax Spanner pays
for its guarantee.

The Google Spanner team measured this and found:
- Typical commit-wait: 5ms (ε ≈ 2.5ms average)
- Worst-case commit-wait: ~14ms (when ε is at its maximum)
- Cross-datacenter Paxos replication: ~14ms (one-way) or ~28ms (round-trip)

So for a typical cross-datacenter write:
- Paxos replication: ~28ms
- Commit-wait: ~5ms
- Total write latency: ~33-50ms

For a single-datacenter write:
- Paxos replication: ~2ms (fast intra-DC network)
- Commit-wait: ~5ms
- Total write latency: ~7-10ms

Interestingly, commit-wait dominates in the single-datacenter case. This is why
Spanner's write latency is often higher than a single-datacenter database like
Postgres, even for "local" transactions.

### 3.5 Read-Only Transactions: No Commit-Wait Needed

Here is one of Spanner's cleverest optimizations: read-only transactions do not
need commit-wait and do not need locks.

Why? Because a read-only transaction does not change any data. It just reads a
consistent snapshot at some timestamp. Spanner picks a timestamp `s` for the read,
then reads the most recent version of each row whose timestamp ≤ s. Since the
data is not changing, there are no conflicts. No locks needed.

The timestamp for a snapshot read is chosen as `s = TT.now().latest`. This guarantees
that any previously committed transaction (which committed at some s' ≤ actual_current_time
≤ TT.now().latest) is included in the snapshot. The reader sees a complete, consistent
snapshot of the database as of time s.

This is called a **snapshot read** or **stale read**. It is globally consistent
(you see a consistent view of the entire database, not a patchwork of different timestamps)
but it is not "latest" — it reflects the database state at some recent past time.

For applications that can tolerate reading data from a few seconds ago (analytics,
dashboards, reporting), snapshot reads are extremely fast because they require no
coordination, no locking, and can be served by any replica.

### 3.6 Calibration: Intern → Staff

**Intern**: "Commit-wait means the transaction waits before committing."

**Junior (L3)**: "Commit-wait stalls the commit until TrueTime confirms real time has
passed the chosen commit timestamp, preventing timestamp ordering violations."

**Mid-level (L4)**: "After picking s = TT.now().latest, the coordinator waits until
TT.now().earliest > s. This ensures any future transaction's TrueTime query will
start with earliest > s, forcing their timestamp to be > s and preserving ordering."

**Senior (L5)**: "The commit-wait protocol ensures that the real-world commit time is
provably after the commit timestamp, closing the uncertainty window. This, combined
with the guarantee that any subsequent transaction's TT.now() starts after this real
time, gives us the external consistency property: s_T2 > s_T1 whenever T2 starts
after T1 commits. The latency cost is exactly ε (the clock uncertainty interval)."

**Staff (L6)**: "Commit-wait is the key insight that lets each Paxos leader assign
globally ordered timestamps independently, without any centralized sequencer. The GPS
and atomic clock infrastructure does the coordination through physics rather than
software. The cost (ε ≈ 5ms average) is a fixed tax on write latency that is
independent of the number of participants, unlike 2PC coordination which scales
with participant count. For read-only transactions, we use snapshot timestamps with
no commit-wait and no locking — globally consistent reads at the cost of reading
data that may be a few milliseconds old. The trade-off is optimal: writes pay ε,
reads pay nothing extra."

---

### Part 3 Brainstorming Q&A

**Q1: What if the commit-wait timeout is in progress and the Paxos leader crashes?
Does the transaction need to restart?**

Yes, and this is an important recovery case. If the Paxos leader crashes during
commit-wait, the other Paxos replicas elect a new leader. The new leader can recover
the transaction's state from the Paxos log — it knows the prepare phase completed
and the chosen commit timestamp s. The new leader resumes the commit-wait from where
it left off (checking TT.after(s)). If enough time has passed, it commits immediately.
If not, it continues waiting. The client will time out and retry, but since the write
is logged in Paxos, the retry is safe — the server can detect the duplicate and return
the same result. This is the "at-least-once" delivery model, protected by idempotency
keys.

**Q2: Can Spanner's commit-wait be parallelized? Can I commit multiple transactions
simultaneously to amortize the cost?**

The commit-wait for each transaction is a function of when that transaction called
TT.now(), so it cannot be shared across transactions. However, in practice, many
transactions are in flight simultaneously, each in their own commit-wait phase. The
Paxos leader handles many transactions concurrently, so the commit-wait periods of
different transactions overlap. From a throughput perspective, this means the system
is not "stuck" waiting — it just adds ε to the latency of each individual transaction.
Additionally, Spanner batches writes where possible: if many small writes come in
around the same time, they can share a single Paxos round and commit together, sharing
one commit-wait among them. This is one of the techniques that lets Spanner achieve
millions of transactions per second across a global deployment.

**Q3: Why does TrueTime pick s = t_latest rather than the midpoint of [t_earliest, t_latest]?
Wouldn't picking the midpoint reduce the commit-wait time?**

Picking the midpoint would give incorrect results. The commit-wait needs to wait until
TT.now().earliest > s, meaning real time is definitely past s. If you pick s = midpoint,
then s < t_latest = actual upper bound on current time. Real time might still be as
high as t_latest, which is > s. A future transaction calling TT.now() might get an
earliest value < t_latest, meaning its earliest could be ≤ s. That would allow a
future timestamp ≤ s, violating ordering. By picking s = t_latest, we ensure that
after commit-wait, real time > s, and any future TT.now() call must return an earliest
value ≥ real time > s. The math only works with s = t_latest. You cannot save time
by picking a smaller s — you would trade correctness for speed, and Spanner is
designed to never make that trade.

---

## Part 4: Architecture — Zones, Spanservers, Paxos Groups

### 4.1 The Three-Level Hierarchy

Spanner's architecture has three main levels. Think of it like a company hierarchy:
- **Universe**: The entire Spanner deployment (like the whole company)
- **Zones**: Individual datacenters or availability zones (like regional offices)
- **Spanservers**: Individual server machines within a zone (like employees)

```
SPANNER ZONE ARCHITECTURE
==========================

                    SPANNER UNIVERSE
         ┌──────────────────────────────────────┐
         │                                      │
    ┌────┴────────┐  ┌─────────────┐  ┌────────┴────┐
    │   Zone A    │  │   Zone B    │  │   Zone C    │
    │  (Virginia) │  │  (Oregon)   │  │  (Tokyo)    │
    │             │  │             │  │             │
    │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │
    │ │Spansvr 1│ │  │ │Spansvr 1│ │  │ │Spansvr 1│ │
    │ │[T1][T2] │ │  │ │[T1][T2] │ │  │ │[T1][T2] │ │
    │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │
    │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │
    │ │Spansvr 2│ │  │ │Spansvr 2│ │  │ │Spansvr 2│ │
    │ │[T3][T4] │ │  │ │[T3][T4] │ │  │ │[T3][T4] │ │
    │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │
    │             │  │             │  │             │
    │  Zonemaster │  │  Zonemaster │  │  Zonemaster │
    │  (manages   │  │  (manages   │  │  (manages   │
    │   tablets)  │  │   tablets)  │  │   tablets)  │
    └─────────────┘  └─────────────┘  └─────────────┘
                             │
                      Universe Master
                      (metadata only,
                       not on critical
                           path)

    T1, T2, T3, T4 = Tablet replicas
    Each tablet has 3-5 replicas across zones
```

### 4.2 Zones

A **zone** is the basic unit of physical isolation. Each zone is typically one
datacenter or one availability zone within a region. Google's production Spanner
spans many zones across multiple continents.

Each zone contains:
- **A Zonemaster**: Manages the assignment of data (tablets) to spanservers within
  the zone. Handles rebalancing and failure recovery.
- **Hundreds to thousands of Spanservers**: The actual data-serving machines.
- **Location proxies**: Used by clients to discover which spanserver holds a
  particular piece of data.

Zones are added and removed dynamically as Google's infrastructure needs change.
Adding a new zone (new datacenter) is an online operation — data migrates gradually.

### 4.3 Spanservers

A **spanserver** is an individual server process (running on a machine) that holds
100 to 1,000 tablets. Tablets are the fundamental storage unit — a range of rows
from a table, stored in a sorted map (implemented using a log-structured merge tree
similar to LevelDB, called SSTable).

Each spanserver:
- Manages a set of tablets
- Runs a **Paxos state machine** for each tablet it serves as leader
- Handles client requests (reads and writes) for those tablets
- Participates in cross-shard 2PC for distributed transactions

The spanserver is where the "interesting" computation happens: TrueTime queries,
lock management, transaction coordination.

### 4.4 Paxos Groups Per Tablet

This is one of Spanner's most important architectural decisions: **each tablet has
its own Paxos group**.

Remember from Chapter 26: Paxos is a consensus algorithm. A Paxos group has 3-5
replicas. Every write must be agreed upon by a majority. The Paxos leader handles
all writes for its group.

In Spanner:
- Each tablet has 3 or 5 replicas, each in a different zone
- One replica is the Paxos leader for that tablet
- All writes to that tablet go to the Paxos leader
- The leader replicates to the other replicas
- Reads can happen at any replica (for snapshot reads) or at the leader (for fresh reads)

The leader is not permanent — it has a lease (typically 10 seconds). If the leader
dies, Paxos elects a new leader within that group. This happens independently for
each tablet's group, so a leader failure for one tablet doesn't affect others.

```
PAXOS GROUP FOR ONE TABLET
============================

         CLIENT
            │
            ▼
    ┌───────────────┐
    │  PAXOS LEADER │ ← Zone A (Virginia)
    │  (Spanserver) │
    └───────┬───────┘
            │  Replicate to followers
            │  (Paxos protocol)
       ┌────┴────┐
       ▼         ▼
  ┌─────────┐  ┌─────────┐
  │Follower │  │Follower │
  │Zone B   │  │Zone C   │
  │(Oregon) │  │(Tokyo)  │
  └─────────┘  └─────────┘

  WRITE PATH:
  1. Client sends write to leader
  2. Leader assigns timestamp, replicates via Paxos
  3. Majority (2 of 3) must acknowledge
  4. Leader commits (after commit-wait)
  5. Client receives success

  READ PATH (snapshot):
  1. Client sends read to any replica
  2. Replica checks: is my data up-to-date enough for this timestamp?
  3. If yes, serve the read directly (no leader contact)
  4. If no, wait for replication to catch up
```

### 4.5 The Directory: Unit of Data Movement

Between tablets and rows, Spanner has a concept called a **directory** (also called
a "bucket" in some documentation). A directory is a group of contiguous rows that
share a common prefix in their primary key.

Directories are important because they are the unit of:
- **Data placement**: You can configure a directory to be in specific zones (e.g.,
  "keep this user's data in Europe for GDPR compliance").
- **Data movement**: When Spanner rebalances load, it moves directories between
  spanservers. Moving a directory (rather than individual rows) is more efficient.
- **Colocation**: Related data (parent and child tables, using interleaving) lives
  in the same directory and is thus physically colocated.

Think of a directory as a folder in a file system. Files (rows) are organized into
folders (directories), which are stored in cabinets (tablets) in offices (spanservers)
in buildings (zones).

### 4.6 How a Write Request Flows Through Spanner

Let's trace a single write: "Update user Alice's balance from $100 to $50."

1. **Client finds the tablet**: The client consults metadata (stored in a special
   root tablet) to find which spanserver is the Paxos leader for Alice's row.

2. **Client sends write to leader**: The write goes to the Paxos leader for Alice's
   tablet, somewhere in (let's say) Virginia.

3. **Leader acquires lock**: The leader acquires a write lock on Alice's row.
   If another transaction holds the lock, this transaction waits.

4. **If single-shard**: The leader runs the write locally, replicates via Paxos,
   and after commit-wait, commits. Done.

5. **If multi-shard**: Say this transaction also updates Bob's balance (different tablet).
   The leader for Alice's tablet acts as the transaction coordinator. It runs 2PC:
   - Sends "prepare" to Bob's tablet's Paxos leader
   - Bob's leader acquires its lock, replicates the prepare log, and responds "ready"
   - Alice's coordinator calls TT.now(), picks timestamp s = t_latest
   - Alice's coordinator commits its local change via Paxos
   - Alice's coordinator sends "commit at timestamp s" to Bob's leader
   - Bob's leader commits via Paxos
   - After commit-wait on Alice's side, the transaction is complete

6. **Client receives success** and the balance is updated globally and consistently.

```
MULTI-SHARD TRANSACTION FLOW (2PC + TrueTime)
===============================================

  CLIENT
    │
    ├──→  ALICE'S PAXOS LEADER (Coordinator)
    │          │
    │          ├── Acquire lock on Alice's row
    │          │
    │          ├──→ BOB'S PAXOS LEADER (Participant)
    │          │         │
    │          │         ├── Acquire lock on Bob's row
    │          │         ├── Replicate PREPARE to Bob's replicas
    │          │         └──→ "PREPARED" ack
    │          │
    │          ├── TT.now() → [021, 027], pick s = 027
    │          ├── Replicate COMMIT(s=027) to Alice's replicas
    │          ├── COMMIT-WAIT until TT.after(027)
    │          │
    │          ├──→ BOB'S LEADER: "COMMIT at s=027"
    │          │         └── Replicate COMMIT to Bob's replicas
    │          │
    │          └── Release Alice's lock
    │
    └──→ Client: SUCCESS
```

---

### Part 4 Brainstorming Q&A

**Q1: What happens if the 2PC coordinator crashes during a distributed transaction?
Can the participants ever unblock?**

This is the classic 2PC "coordinator failure" problem, and Spanner solves it through
the Paxos layer. The coordinator is not a single machine — it is a Paxos leader for
a tablet. If that machine crashes, the other replicas in the same Paxos group elect
a new leader. The new leader can read the transaction log from Paxos to determine
the state: was the commit decision logged before the crash? If yes, the new leader
completes the commit. If no, the new leader aborts the transaction and releases
locks. Participants have a timeout: if they don't hear from the coordinator within
a few seconds, they query the coordinator's Paxos group for the transaction status.
This is called "cooperative termination" and it means participants can always unblock
as long as a majority of the coordinator's replicas are alive.

**Q2: Can a Paxos leader be far away from the user, adding latency?**

Yes, and this is a real trade-off. Spanner's write latency to a Paxos leader is
determined by the distance to that leader. If your user is in Tokyo but the leader
is in Virginia, every write pays ~150ms of network latency. Spanner provides
**leader placement** controls: you can configure which regions should be preferred
for leadership. For a product with mostly Japanese users, you would configure leaders
to prefer the Tokyo zone. For a global product, you might accept slightly higher
write latency in exchange for lower read latency (reads can be served locally).
Cloud Spanner (the managed service) provides regional and multi-region configurations
that let you optimize leader placement for your use case.

**Q3: What is the zonemaster's role and is it a single point of failure?**

The zonemaster manages tablet-to-spanserver assignment within a zone. It is similar
to Bigtable's master or HDFS's NameNode. It is not on the critical path for reads
or writes — once a client knows which spanserver holds a tablet (through location
proxies), it communicates directly with the spanserver without involving the
zonemaster. The zonemaster is only involved in rebalancing (moving tablets between
spanservers) and failure recovery (reassigning tablets when a spanserver fails).
The zonemaster itself is made highly available using a Paxos group (or Chubby locks)
to ensure it can fail over without data loss. Even if the zonemaster is temporarily
unavailable, existing tablet assignments continue working — clients only see issues
when they need to discover a new tablet location, which is rare (they cache tablet
assignments).

---

## Part 5: Transaction Types — Read-Write, Read-Only, Schema Changes

### 5.1 Three Types of Transactions

Spanner supports three kinds of transactions, each designed for a different use case:

1. **Read-Write Transactions**: Full ACID, use 2PC + TrueTime commit-wait. Most
   expensive but fully consistent.
2. **Read-Only Transactions**: No locks, no commit-wait, globally consistent snapshot
   reads. Fast and scalable.
3. **Schema Change Transactions**: Special mechanism for changing table schema without
   blocking reads or writes.

Understanding which type applies when is crucial for interview discussions.

### 5.2 Read-Write Transactions in Detail

A read-write transaction looks like this to the application:

```sql
BEGIN TRANSACTION;
  SELECT balance FROM accounts WHERE user_id = 'alice';  -- reads
  UPDATE accounts SET balance = balance - 50 WHERE user_id = 'alice';
  UPDATE accounts SET balance = balance + 50 WHERE user_id = 'bob';
COMMIT;
```

Internally, Spanner uses **wound-wait** (a variant of 2PL) for deadlock prevention.
If Transaction T2 needs a lock held by older Transaction T1:
- T1 is older, T2 waits (T2 is "wound")
- If T2 is older and T1 is younger, T1 aborts (T1 is "killed")

Reads within a read-write transaction are not simple snapshot reads — they read
at the latest version and hold read locks, ensuring the data doesn't change before
the transaction commits. This is different from read-only transactions.

The commit path is exactly what we described in Part 3: prepare → choose timestamp
→ commit-wait → commit. Total latency for a cross-region read-write transaction
is typically 30-80ms.

### 5.3 Read-Only Transactions: The Performance Win

Read-only transactions are declared by the client:

```sql
BEGIN READ ONLY TRANSACTION;
  SELECT SUM(balance) FROM accounts;
  SELECT COUNT(*) FROM users WHERE region = 'US';
COMMIT;
```

For a read-only transaction:
1. Spanner picks a timestamp `s = TT.now().latest`
2. All reads in the transaction use this same timestamp `s`
3. Each spanserver checks: do I have all data up to timestamp s?
   - If yes: serve the read immediately
   - If no: wait for Paxos replication to catch up to s
4. No locks acquired. No 2PC. No commit-wait.

The "wait for replication to catch up" step is usually very fast — Paxos replication
is typically within a few milliseconds. A follower replica that is 3ms behind the
leader will only wait 3ms before it can serve the read.

This means read-only transactions can be served by any replica, anywhere in the world,
without talking to the leader. A user in Tokyo can read from the Tokyo replica without
a round-trip to Virginia. This is massive for global read scalability.

### 5.4 Snapshot Reads: Even Faster

A snapshot read is like a read-only transaction but at a specific past timestamp:

```sql
SELECT * FROM orders WHERE user_id = 'alice'
  AS OF SYSTEM TIME '-5s';  -- Read data from 5 seconds ago
```

Since all replicas are typically within 5 seconds of the leader, every replica can
serve this read immediately without any waiting. No coordination. No latency. Pure
local data serving.

Snapshot reads are perfect for:
- Analytics queries that don't need the absolute latest data
- Backup and export operations
- Detecting trends (where a few seconds of staleness is acceptable)
- Reducing load on the Paxos leader

### 5.5 Schema Change Transactions

Changing a table schema (adding a column, adding an index) in a distributed database
is notoriously painful. If you lock the entire table during a schema change, no one
can read or write during the migration — unacceptable for a global system serving
millions of users.

Spanner's schema change mechanism:
1. A schema change is registered with a future timestamp `t_future`
2. Until `t_future`, the old schema is in effect
3. After `t_future`, the new schema is in effect
4. Writes before `t_future` follow the old schema
5. Writes after `t_future` follow the new schema
6. Reads can consistently use either schema by specifying a timestamp

This means schema changes are **non-blocking**: reads and writes continue normally
throughout the migration. The "cutover" is atomic (it happens at one timestamp),
but there's no downtime. Data migration for existing rows (e.g., setting a default
value for a new column) happens asynchronously.

This is a major operational advantage over MySQL or Postgres, where `ALTER TABLE` can
lock a large table for hours.

### 5.6 Calibration: Intern → Staff

**Read-Write Transactions:**

*Intern*: "Read-write transactions are like regular database transactions with locking."

*Junior (L3)*: "Spanner uses 2PL for locking and 2PC for cross-shard coordination.
The TrueTime commit-wait adds latency but ensures correctness."

*Mid-level (L4)*: "Read-write transactions use wound-wait for deadlock prevention,
2PC for multi-shard coordination, and commit-wait at the end. The coordinator is
the Paxos leader of the first-involved tablet. Latency is dominated by Paxos
replication and commit-wait (ε)."

*Senior (L5)*: "The key implementation detail is that reads within a read-write
transaction are not snapshot reads — they acquire shared locks and must read the
latest version. This prevents other writers from modifying the read-set before
commit, maintaining isolation. The write-lock acquisition and 2PC prepare phase
can be pipelined with Paxos replication, reducing the sequential steps."

*Staff (L6)*: "For single-shard write transactions, the 2PC can be optimized away —
the leader directly runs the prepare and commit as a single Paxos round. This is
the common case for simple key-value updates. Multi-shard transactions (the less
common case) pay the full 2PC overhead. Schema changes use a timestamp-based
visibility mechanism that amortizes migration cost over all future transactions,
enabling zero-downtime schema evolution at global scale."

---

### Part 5 Brainstorming Q&A

**Q1: If I do a read inside a read-write transaction, does that read hold a lock?
What kind of lock?**

Yes. Reads inside a read-write transaction acquire **shared (read) locks** on the
rows they read. These locks prevent other transactions from writing to those rows
until the read-write transaction commits or aborts. This is necessary for correctness:
without read locks, another transaction could modify a row between when you read it
and when you commit, violating the atomicity guarantee. (This is the phantom read
problem in ANSI SQL isolation levels.) The lock is held until the end of the
transaction (strict 2PL). This is more conservative than some systems (e.g.,
Postgres's MVCC does not hold read locks in read committed mode), but it is
required for Spanner's serializability guarantee.

**Q2: Can I use a read-only transaction for a banking transfer? What if I need to
check a balance and then debit?**

No. The "check then debit" pattern requires a read-write transaction. Here's why:
with a read-only transaction, you read the balance (e.g., $100), but you do not
hold any lock. Between your read and your write, another transaction could also
read $100 and initiate a debit. Both succeed, and Alice is overdrawn. This is the
classic TOCTOU (time-of-check time-of-use) race condition. For banking operations,
you must use a read-write transaction that holds a write lock on Alice's row from
the moment you read the balance until the debit commits. Read-only transactions
are only appropriate when your operation is truly read-only — you are observing
data, not making decisions that depend on it being unchanged.

**Q3: How does Spanner handle schema migrations that require backfilling existing rows?
For example, adding a NOT NULL column with no default?**

Spanner handles backfills asynchronously. When you add a column, Spanner internally
schedules a background job to iterate over existing rows and fill in the new column's
value (or mark it as null/default). During this backfill period, new writes include
the new column. Reads before the backfill timestamps use the old schema (column appears
null or absent). Reads after the cutover timestamp use the new schema (column is present,
backfilled rows show the filled value). The application must handle the intermediate
state where some rows have the new column filled and others don't (for the backfill
duration). For NOT NULL constraints, Spanner typically requires a default value or
rejects NOT NULL until the backfill completes and all rows are verified. This is
similar to how online schema change tools like gh-ost or pt-online-schema-change work
for MySQL, but it is built into the database engine itself.

---

## Part 6: Data Model — SQL Interface, Interleaved Tables, and Sharding

### 6.1 Spanner is a Relational Database (With Some Twists)

Spanner provides a full relational data model with SQL. This is surprising to many
people who think "distributed database" means "NoSQL." Spanner has:
- Tables with strongly-typed columns
- Primary keys (mandatory — every table must have one)
- Secondary indexes
- Full SQL queries (SELECT, JOIN, aggregations)
- Foreign key constraints
- Check constraints

This puts Spanner squarely in the "NewSQL" category: SQL interface with NoSQL-scale
distributed architecture underneath.

### 6.2 Mandatory Primary Keys

Every Spanner table must have a primary key. This is not optional. The primary key
determines how rows are physically stored and how they are sharded across spanservers.

The primary key can be:
- A single column: `(user_id INT64)`
- A composite key: `(user_id INT64, post_id INT64)`
- A string: `(email STRING(100))`

Choosing the primary key carefully is critical for performance. A bad primary key
leads to:
- **Hot spots**: If you use an auto-incrementing integer, all new rows go to the
  same tablet (the "end" of the key space), overloading one spanserver.
- **Cross-shard joins**: If related rows have different key prefixes, joining them
  requires crossing shard boundaries.

Google's recommended practice: use a **UUID** or **hash prefix** if you want
uniform distribution, or use a **natural composite key** (e.g., `(user_id, timestamp)`)
to keep a user's rows together.

### 6.3 Interleaved Tables: Colocation for Performance

Interleaved tables are one of Spanner's most innovative data modeling features.
An interleaved table is a child table that is physically stored within the parent
table's row.

Think of it like this: imagine a filing cabinet where every folder for a customer
also contains all that customer's orders inside the folder itself. When you pull
out the customer folder, you automatically have all their orders. No need to go
looking in a separate orders cabinet.

```
INTERLEAVED TABLE STORAGE (ON DISK)
=====================================

  Without interleaving:
  
  USERS table         ORDERS table (separate tablet)
  ─────────────       ──────────────────────────────
  user1               order1 (user1)
  user2               order2 (user1)
  user3               order3 (user2)
                      order4 (user3)
  
  Joining user1 + orders requires cross-tablet lookup → slow

  With interleaving:
  
  USERS + ORDERS (same tablet, interleaved)
  ──────────────────────────────────────────
  user1
    └─ order1 (user1)
    └─ order2 (user1)
  user2
    └─ order3 (user2)
  user3
    └─ order4 (user3)
  
  Joining user1 + orders is a LOCAL scan → fast!
```

The SQL to define interleaving:

```sql
CREATE TABLE Users (
  user_id  INT64 NOT NULL,
  username STRING(100),
  email    STRING(100),
) PRIMARY KEY (user_id);

CREATE TABLE Orders (
  user_id   INT64 NOT NULL,
  order_id  INT64 NOT NULL,
  amount    FLOAT64,
  status    STRING(20),
) PRIMARY KEY (user_id, order_id),
  INTERLEAVE IN PARENT Users ON DELETE CASCADE;
```

The `INTERLEAVE IN PARENT Users` clause tells Spanner to store each Order row
physically adjacent to its parent User row. The child's primary key must start with
the parent's primary key — that's how Spanner knows which parent row each child belongs to.

### 6.4 Automatic Sharding

Spanner automatically splits tablets when they grow too large (typically above 4-8 GB).
When a tablet splits:
1. Spanner picks a split point in the middle of the key range
2. Creates two new tablets from one old tablet
3. Migrates one half to a different spanserver (if needed for load balancing)

This process is transparent to the application. Queries that span the old range now
transparently span two tablets. The Paxos leader for the new tablets is elected
automatically.

Spanner can also **merge** tablets that have become too small (due to data deletion)
back together. And it can split tablets proactively if it detects a hot key (one
key getting far more traffic than others).

### 6.5 Secondary Indexes

Spanner supports both:
- **Local indexes**: Co-located with the base table data. Index entries are interleaved
  alongside the base table, so index lookups are fast but can only filter on data within
  the same tablet.
- **Global indexes**: Stored separately from the base table. Index entries can point to
  any row in the base table. Supports queries that filter on non-primary-key columns
  across the entire table.

Global indexes are powerful but expensive to update. An update to an indexed column
requires updating the index entry (which might be on a different spanserver), making
it effectively a distributed transaction. Google recommends using global indexes
sparingly for very frequently queried columns.

### 6.6 Calibration: Intern → Staff

**Interleaved Tables:**

*Intern*: "Interleaved tables store related data together."

*Junior (L3)*: "Interleaving tells Spanner to store child rows physically adjacent to
parent rows, making parent-child joins fast because they're local."

*Mid-level (L4)*: "Interleaving maps to the directory structure in Spanner's storage:
a user's row and all their orders form a single directory, ensuring they're in the
same tablet. This eliminates cross-shard lookups for the common query pattern
'get user with all their orders.'"

*Senior (L5)*: "The key design insight is that Spanner's key space is a sorted map.
Interleaving enforces a prefix-sharing constraint: child keys must start with the
parent key. Because the key space is sorted, all children for one parent are
contiguous. The tablet split logic respects directory boundaries, so a parent and its
children stay together even after splits. When designing a schema for Spanner, the
question is: 'what is my most common access pattern?' If it's 'user + their data,'
interleave the user's data tables. If it's 'cross-user analytics,' use global indexes
or a separate analytics table."

*Staff (L6)*: "Interleaving is Spanner's answer to the fundamental tension in
distributed database design: normalization (good for consistency, bad for colocation)
vs. denormalization (good for colocation, bad for consistency). Interleaving gives you
both: data is normalized (separate parent and child tables, foreign key relationship),
but physically stored as if denormalized. The trade-off is that the access pattern must
be hierarchical — queries that cut across the hierarchy (e.g., 'find all orders for
a product ID across all users') still require global index scans. Schema design for
Spanner should start with the dominant query pattern and design the interleaving hierarchy
around it, accepting that other access patterns will be slower."

---

### Part 6 Brainstorming Q&A

**Q1: Why is an auto-incrementing primary key bad for Spanner? What should I use instead?**

An auto-incrementing primary key (like `id SERIAL` in Postgres) creates a hot spot
in Spanner. Since Spanner stores rows sorted by primary key, new rows always go to
the highest key value, which means they always go to the last tablet. All inserts
hammer one tablet/spanserver. You lose the distributed benefit of Spanner for writes.

The solution is to use a key that distributes writes evenly. Options include:
1. **UUID**: Universally unique IDs are random and distribute evenly across the key
   space. Downside: harder to sort by insertion order.
2. **Hash prefix + timestamp**: Prepend a hash of the user ID (giving random distribution)
   then append a timestamp (preserving time order within each bucket). Common pattern:
   `(hash(user_id) % N, user_id, timestamp)` where N is the number of desired shards.
3. **Natural composite key**: If your data has a natural distribution (e.g., user_id
   is random enough), use `(user_id, timestamp)`. This distributes writes across users
   and keeps each user's data together.

**Q2: Can I have a Spanner table without any indexes, only a primary key? Is that ever a good idea?**

Yes, and for certain access patterns it is the right choice. If your entire application
accesses data through the primary key (e.g., a cache-like lookup by user_id), you do
not need secondary indexes. Secondary indexes add write overhead (every write to the
base table also updates the index) and storage. For a high-throughput write system
where reads always use the primary key, skip secondary indexes entirely and use
Spanner's efficient primary-key lookups. This is similar to how HBase/Bigtable users
design their row keys to encode the access pattern — the "index" is implicit in the
key structure. The difference is that Spanner's SQL engine can still do full scans
if needed (just slowly for large tables without indexes), whereas Bigtable/HBase
would require a separate index table.

**Q3: How does Spanner handle large objects (BLOBs)? Can I store a 100MB image in a Spanner row?**

Spanner is not designed for large binary objects. The practical limit is around 10MB
per cell (column value) and Spanner's performance degrades significantly with large
values. For BLOBs, the recommended pattern is:
1. Store the BLOB in Google Cloud Storage (GCS)
2. Store a reference (GCS URI) and metadata in Spanner
3. The application fetches the BLOB from GCS separately

This is the standard pattern for any relational database (Postgres, MySQL) as well —
BLOBs belong in object storage, not row-oriented databases. Spanner's storage engine
(SSTable/LSM-tree) is optimized for small-to-medium values (bytes to kilobytes) and
random-access reads. Large BLOBs would cause write amplification problems in the
LSM-tree and poor utilization of Spanner's computational resources.

---

## Part 7: Performance Numbers — What Does Spanner Actually Achieve?

### 7.1 Why Performance Numbers Matter in Interviews

At L5/L6 interviews, you will be expected to give ballpark numbers when designing
systems. "Spanner gives you global consistency" is incomplete — the follow-up is
always "at what cost?" Having the right order-of-magnitude numbers in your head
makes your design discussions more credible.

### 7.2 Latency Numbers from the 2012 Paper

The original Corbett et al. (OSDI 2012) paper reported these latency numbers for
their experimental setup (across multiple US datacenters):

**Read latency (snapshot reads)**:
- Single datacenter read: 1-10ms
- Cross-datacenter read (reading from a replica in another zone): 7-14ms

**Write latency (read-write transactions)**:
- Single-shard, two-zone replication: ~5-10ms
- Single-shard, five-zone replication: ~100ms (cross-continent)
- The paper notes commit-wait contributes ~5ms in their deployment

**From the F1 paper (2013)** — Google's Ads database running on Spanner:
- Average read latency: 8.7ms (at P50), 14.1ms (at P99)
- Average SQL query latency: 12.6ms (P50), 21.3ms (P99)
- Average commit latency: 30.6ms (P50) for a distributed transaction

These numbers include network latency and Paxos replication across US datacenters.

### 7.3 Latency Breakdown for a Typical Write

Let's decompose where time goes in a distributed write transaction:

```
WRITE LATENCY BREAKDOWN (Cross-Region Transaction)
====================================================

  Timeline (milliseconds):
  
  t=0ms:   Client sends write to Paxos leader (Virginia)
  t=2ms:   Leader acquires lock (fast, local)
  t=4ms:   Leader sends PREPARE to Oregon participant
  t=18ms:  Oregon participant receives PREPARE (+14ms network)
  t=20ms:  Oregon replicates PREPARE to its replicas (~2ms)
  t=20ms:  Oregon sends PREPARED ack back to Virginia
  t=34ms:  Virginia receives PREPARED (+14ms network)
  t=35ms:  Virginia calls TT.now() → picks s = 35+6 = 41ms
  t=35ms:  COMMIT-WAIT begins (wait until TT.after(41ms))
  t=41ms:  COMMIT-WAIT ends (6ms stall)
  t=41ms:  Virginia commits locally via Paxos (~2ms)
  t=43ms:  Virginia sends COMMIT(s=41) to Oregon
  t=57ms:  Oregon receives COMMIT, commits locally
  t=57ms:  Virginia sends SUCCESS to client
  
  TOTAL: ~57ms for a cross-US-region distributed write
  
  BREAKDOWN:
  Network latency (VA→OR, OR→VA): 2 × 14ms = 28ms
  Paxos replication (local):        2 × 2ms  =  4ms
  Lock acquisition + processing:             =  3ms
  Commit-wait (ε):                           =  6ms
  ─────────────────────────────────────────────────
  Total:                                     ~41ms
  (plus client→server round-trip not shown)
```

### 7.4 Throughput Numbers

The 2012 paper reported throughput for different Spanner configurations:

**Read throughput**:
- Scales linearly with the number of Paxos followers (each follower serves reads)
- 1x configuration: baseline
- 5 replicas: ~5x read throughput (each replica handles reads)
- Adding more zones linearly increases read capacity

**Write throughput**:
- Scales with the number of Paxos groups (shards)
- Each Paxos group handles its own writes independently
- Adding more tables/shards increases write throughput linearly
- A single Paxos group: ~10,000 transactions/second (limited by leader)
- Production Spanner: millions of transactions/second across all groups

**Google Ads (F1) numbers** (from the 2013 paper):
- Total database size: ~100 TB (at migration time)
- Number of servers: hundreds of spanservers
- Daily queries: billions
- Peak QPS: millions of queries/second

### 7.5 The Commit-Wait Latency in Practice

Google reported that their average TrueTime ε was about 4ms in 2012. This means
commit-wait adds ~4ms to every write. How does this compare to what commit-wait
eliminates?

Without commit-wait (but with TrueTime for timestamp assignment), you might need
a second round of 2PC messages to verify timestamp ordering — adding another
network round-trip (~14ms cross-datacenter). Commit-wait (4ms) is cheaper than
that additional round-trip.

Alternatively, without TrueTime at all (using HLC like CockroachDB), you need to
handle timestamp uncertainty at read time, adding latency to reads. Spanner's
approach pays latency once at commit time (commit-wait) to make reads fast.

### 7.6 Throughput vs. Latency Trade-offs

Spanner optimizes for **correctness** first, **throughput** second, and accepts
**latency** as a necessary cost. The latency profile:

| Operation | Typical Latency | Notes |
|-----------|----------------|-------|
| Single-row read (primary key) | 1-3ms | Local replica, no lock |
| Snapshot read (complex query) | 10-30ms | Any replica |
| Single-shard write | 5-15ms | Local Paxos + commit-wait |
| Cross-shard write (1 region) | 10-30ms | Local 2PC + commit-wait |
| Cross-region write (2 regions) | 30-80ms | Network dominant |
| Cross-continent write | 100-300ms | Network dominant |

For comparison:
- Postgres single-node write: 1-5ms
- DynamoDB single-region write: 5-15ms (eventually consistent)
- MySQL cross-datacenter replication lag: unpredictable, minutes possible

### 7.7 When Is Spanner's Latency Acceptable?

Spanner's latency is acceptable for:
- Global financial transactions (banks accept 100ms for SWIFT)
- E-commerce (50-100ms for checkout is fine)
- Advertising (30-50ms per impression decision)
- Configuration stores (read-heavy, occasional writes)
- User profile stores (globally consistent user data)

Spanner's latency is NOT acceptable for:
- High-frequency trading (sub-millisecond required)
- Gaming leaderboards (thousands of updates/second per key)
- IoT sensor streams (millions of writes/second, eventual consistency fine)
- Real-time bidding at microsecond speed

---

### Part 7 Brainstorming Q&A

**Q1: Spanner's cross-region write is 30-80ms. How does Google Ads handle ad serving
with this latency? Ads must be served in milliseconds.**

Great question — and this is exactly the kind of nuance that impresses L6 interviewers.
Google Ads does NOT use Spanner for the real-time ad serving path. Ad serving must
respond in under 100ms total, with the database lookup under 10ms. For real-time
serving, Google uses Bigtable (for campaign data) and in-memory caches. Spanner is used
for the **management plane**: campaign creation, budget updates, advertiser account
changes. These operations happen minutes to days before ad serving and can tolerate
50-100ms latency. The data flows: advertiser updates campaign on Spanner (100ms write)
→ asynchronously propagated to Bigtable (seconds delay) → ad server reads from Bigtable
(1ms read). Spanner ensures consistency in the management plane. Bigtable handles serving
throughput. This is the "write to Spanner, serve from cache/Bigtable" pattern used
throughout Google.

**Q2: The F1 paper says P99 commit latency is 30ms. What's at the P99.9 or P99.99?
Could there be tail latency problems?**

The Corbett paper doesn't publish P99.9 numbers, but tail latency is a real concern for
Spanner. Sources of tail latency include: ε spikes when GPS signal degrades temporarily
(increasing commit-wait), Paxos leader elections when a spanserver fails (causing
a brief unavailability on that shard), cross-shard transactions that involve a slow
participant, and Java garbage collection pauses (early Spanner was Java; later versions
moved to C++). Google mitigates tail latency through: hedged requests (send to multiple
replicas, take the first response), timeout-and-retry protocols, and minimizing the
number of shards touched per transaction (colocating related data using interleaving).
For latency-sensitive paths, Google engineers deliberately avoid multi-shard transactions.

**Q3: How does Spanner scale writes? If I have 10,000 rows all with the same primary
key prefix, do they all go to one spanserver?**

Yes — that's the hot-spot problem. If your write pattern concentrates on a small key
range, all those writes go to the single Paxos leader for that tablet. Spanner can
detect hot spots and split the hot tablet, but splitting doesn't help if the entire
write load is on a single key. This is why Spanner's documentation strongly recommends
against sequential primary keys. The fix is key design: add a hash prefix or use UUIDs
to distribute writes. If you genuinely need a "hot key" (e.g., a global counter),
Spanner recommends sharding it manually: instead of one row with a counter, use N rows
each representing 1/N of the total, and aggregate at read time. This is the same
technique used in Cassandra, Bigtable, and virtually every distributed write-heavy system.

---

## Part 8: Spanner vs. Alternatives

### 8.1 The Landscape of Globally Distributed Databases

Since Spanner's publication in 2012, the database landscape has changed dramatically.
Several systems now claim to offer "global consistency" or "Spanner-like" properties.
In interviews, you will be expected to know the differences.

### 8.2 Spanner vs. CockroachDB

CockroachDB (CRDB) is the closest open-source equivalent to Spanner. It was explicitly
designed as an open-source Spanner and shares many architectural ideas.

**Similarities:**
- SQL interface with ACID transactions
- Multi-region replication with Raft consensus (similar to Paxos)
- Serializable isolation (and stronger)
- Automatic sharding and rebalancing
- Secondary indexes

**Key Difference: HLC vs. TrueTime**
CockroachDB cannot use TrueTime (no GPS hardware on AWS/GCP). Instead, it uses
Hybrid Logical Clocks (HLC). HLC tracks both physical time and logical counters.
When a transaction observes a timestamp higher than its local clock, it advances its
clock to match.

The consequence: HLC uncertainty is larger and more variable than TrueTime. CockroachDB
handles this by passing "uncertainty intervals" around with each transaction. When a
read might see a value from within the uncertainty interval, CockroachDB restarts the
transaction with a higher timestamp. This is called "clock uncertainty restart" and
it adds occasional extra latency when clocks are skewed.

```
SPANNER vs. COCKROACHDB
=========================

Feature              Spanner               CockroachDB
────────────────────────────────────────────────────────
Consistency          External consistency   Serializable
                     (stronger)            (slightly weaker)
Clock mechanism      TrueTime (GPS+atomic) HLC (software)
Clock uncertainty    1-7ms (bounded,       up to 500ms
                      guaranteed)          (varies)
Commit-wait          Yes (~5ms)            No (uses restarts)
Infrastructure       Requires GPS HW       Commodity hardware
Deployment           Google Cloud only     Any cloud/on-prem
Open source          No (Cloud Spanner     Yes
                      is SaaS only)
SQL compatibility    Google Spanner SQL    PostgreSQL wire
                                          protocol
Performance          Similar throughput    Similar throughput
                     Lower tail latency    Higher tail latency
                                          (HLC restarts)
```

**When to choose CockroachDB over Spanner:**
- You need on-premises or multi-cloud deployment
- You need PostgreSQL wire protocol compatibility
- You want open-source with no vendor lock-in
- Your consistency requirements are "serializable" (not "external consistency")

**When to choose Spanner over CockroachDB:**
- You are on Google Cloud and need the strongest possible consistency guarantee
- Tail latency from HLC restarts is unacceptable
- You need Google's operational support and SLA

### 8.3 Real Incident: CockroachDB Production Consistency Bug (2019)

In 2019, the CockroachDB team disclosed a consistency bug related to HLC and clock
skew. When two nodes had clocks that were skewed by more than the expected bound
(due to a time master failure), some transactions could observe non-serializable
behavior. Specifically:

- Transaction T1 wrote value X on Node A at HLC time 100
- Node B's clock was skewed forward to HLC time 110
- Transaction T2 read from Node B at HLC time 108 — before T1's write
- But in real wall-clock time, T2 started after T1 committed
- Result: T2 didn't see T1's write (violated external consistency; technically
  also violated serializability in the edge case)

The fix: CockroachDB added automatic clock skew detection and a "skew detector" that
restarts the node when its clock diverges too far from other nodes' clocks. They also
tightened the default max clock skew from 500ms to 500ms (same bound but with stricter
enforcement).

The lesson: HLC without TrueTime cannot bound clock skew mathematically — you must
rely on external monitoring and detection. This is a production engineering challenge
that Spanner's TrueTime hardware eliminates by construction.

### 8.4 Spanner vs. YugabyteDB

YugabyteDB is another distributed SQL database, inspired by both Spanner and Google's
F1. Key differences from Spanner:

- Uses Raft consensus (not Paxos) — similar guarantees, different implementation
- Supports both Cassandra (CQL) and PostgreSQL (YSQL) APIs
- No TrueTime; uses HLC like CockroachDB
- Open source (Apache 2.0 license)
- Runs on any cloud

YugabyteDB's "clock skew" tolerance is configurable. It defaults to 500ms max skew.
Like CockroachDB, it relies on monitoring to detect clock skew problems, not hardware
guarantees.

**When to choose YugabyteDB:**
- Need open-source with on-prem option
- Need Cassandra API compatibility
- Multi-cloud deployment (AWS + GCP + on-prem)
- Smaller team, want managed operational complexity

### 8.5 Spanner vs. Amazon Aurora Global Database / AlloyDB

**Aurora Global Database**: Amazon's managed globally distributed relational database.
- Uses a different consistency model: the primary region is strongly consistent,
  cross-region replicas have up to ~1 second lag
- Not external consistency — this is multi-master with some relaxation
- Lower latency for single-region writes (no commit-wait)
- Much more operational maturity (Aurora has been around since 2015)
- Uses storage-level replication (not Paxos at the application level)

**AlloyDB (Google Cloud)**: Google's PostgreSQL-compatible database.
- Runs on Google's infrastructure but uses different consistency than Spanner
- PostgreSQL wire-protocol compatible (Spanner requires a special driver)
- Single-region primary with cross-region replicas (like Aurora)
- Lower operational complexity than Spanner (simpler schema design, no interleaving)

**Cloud Spanner (Google's managed Spanner)**:
- Fully managed, serverless scaling
- External consistency guaranteed
- Pay-per-processing-unit model
- No need to manage spanservers or zones
- Schema design and TrueTime considerations remain

```
CONSISTENCY HIERARCHY
=======================

   STRONGEST
       │
       ▼
  External Consistency      (Spanner, Cloud Spanner)
  "Real-time serializability"
  
  Serializable              (CockroachDB, YugabyteDB, PostgreSQL)
  "Transactions appear serial, order may not match real time"
  
  Snapshot Isolation        (MySQL REPEATABLE READ, many MVCC DBs)
  "Consistent snapshot per transaction, but write anomalies possible"
  
  Read Committed            (PostgreSQL default, MySQL default)
  "Each statement sees latest committed data"
  
  Eventual Consistency      (DynamoDB default, Cassandra default)
  "Data will eventually match, but no ordering guarantee"
       │
       ▼
   WEAKEST
```

### 8.6 Spanner vs. Bigtable — The Most Confused Google Database Pair

Many candidates who can explain Spanner fluently will still mix up Spanner and Bigtable
under pressure. They are both Google databases, both globally distributed, both used
in critical Google systems — but they are fundamentally different tools.

**What Bigtable is**:
Bigtable (covered in Chapter 29) is Google's wide-column NoSQL store, open-sourced as
Apache HBase. It stores data as rows indexed by a single string key, with columns
grouped into column families. Think of it as a massively scalable, distributed
sorted map: `(row_key, column_family, column, timestamp) → value`.

Bigtable provides:
- Atomic writes at the **single-row level only** — one row can be written atomically
- No cross-row transactions — two rows cannot be updated atomically
- No SQL — you query by row key prefix, column range, or time range
- No commit-wait, no TrueTime-based consistency
- Eventual consistency across replicas (though within a cluster, single-master is strongly consistent)
- Extremely high write throughput (millions of writes/second per cluster)
- Write latency: ~1-5ms (no commit-wait overhead)

**The fundamental split**:

```
SPANNER vs. BIGTABLE: WHAT EACH SOLVES
=========================================

  BIGTABLE: "I need to write 10M sensor readings per second"
  
  Row key: "sensor_001/2024-01-15T12:00:00Z"
  Columns: {temperature: 98.6, humidity: 42, pressure: 1013}
  
  → No ACID, no SQL, no cross-row atomicity
  → Just: write fast, read by key range, never lose a byte

  SPANNER: "I need to transfer $100 from Alice to Bob, globally, atomically"
  
  Account(alice, balance=500)   →   Account(alice, balance=400)
  Account(bob,   balance=300)   →   Account(bob,   balance=400)
  
  Both rows change together, or neither does. Across any two datacenters.
  
  → Full ACID, SQL, cross-row 2PC, commit-wait, TrueTime
  → Just: never show an inconsistent state, ever
```

**Bigtable's storage layer is what Spanner uses underneath**:
An important nuance: Spanner's storage engine is based on the same concepts as
Bigtable's — SSTable files, compaction, log-structured storage on Google's Colossus
file system. Spanner adds the Paxos replication layer, the transaction coordinator,
and TrueTime on top of Bigtable-like storage primitives. In a sense, Spanner is
"what if Bigtable had ACID transactions and SQL?"

**When to choose Bigtable over Spanner**:
1. Write throughput is paramount (10M+ writes/second): Bigtable's leader-per-cluster
   model avoids per-write commit-wait overhead entirely.
2. Data is time-series or IoT: single-row atomicity is sufficient; key is compression
   and scan speed, not cross-row consistency.
3. Access pattern is always by row key: no JOINs, no complex queries, pure
   key-value or key-range lookups.
4. You already have Bigtable operational expertise and don't need SQL.

**Interview rule**: If someone says "Google uses Bigtable for Gmail," that's accurate
(Gmail stores individual emails as rows). If they say "Google uses Bigtable for
Google Ads," that's partially true (ad serving reads from Bigtable) but the source of
truth for ad campaign budgets and advertiser accounts is Spanner. The two systems
complement each other: Spanner manages correctness, Bigtable handles throughput.

---

### 8.8 When NOT to Use Spanner

Spanner is not the right answer for every problem. Common cases where you should
choose something else:

**Don't use Spanner when:**
1. **Ultra-low write latency is required** (< 5ms): Spanner's commit-wait alone is
   5ms. Use single-region Postgres or MySQL.
2. **You are not on Google Cloud**: Spanner is Google-only. Use CockroachDB or
   YugabyteDB for multi-cloud.
3. **Your data is mostly read and can be slightly stale**: Use Cassandra or DynamoDB
   with eventual consistency. Much cheaper, lower latency, higher throughput.
4. **Your schema is highly unpredictable**: Spanner's schema design (interleaving,
   mandatory primary keys) requires upfront thought. Schemaless document stores
   (Firestore, MongoDB) are more flexible for rapidly changing data models.
5. **You need full-text search**: Spanner is not a search engine. Use Elasticsearch
   or Cloud Search alongside Spanner for full-text queries.
6. **You are on a budget**: Cloud Spanner is expensive compared to self-managed
   Postgres. For a startup, Postgres with logical replication is usually sufficient.
7. **High write throughput on a single key**: Hot spots are Spanner's weakness.
   For time-series or IoT data, use Bigtable or InfluxDB.

### 8.9 Real Story: The F1 Migration to Spanner

The F1 paper (2013, by Shute et al.) describes Google's migration from a sharded
MySQL system to Spanner for Google Ads. This is one of the most significant database
migrations ever completed.

**Before Spanner (sharded MySQL with F1 application layer)**:
- ~100s of MySQL shards
- Cross-shard transactions required complex application logic
- Schema changes required taking database offline or complex rolling migrations
- ~3 outages/year from cross-shard consistency bugs
- 20+ engineers dedicated to shard management and consistency tooling

**The migration**:
- Over 2 years, the team gradually moved tables from MySQL shards to Spanner
- They could run Spanner and MySQL in parallel and compare results
- They migrated least-used tables first, most-critical tables last
- Zero customer-facing outages during migration

**After Spanner**:
- All cross-shard complexity eliminated from application code
- Schema changes done online, no downtime
- Zero consistency-related outages (in the first year post-migration)
- 20+ engineers redeployed to product development instead of database management

The F1 paper is notable for honestly reporting what they lost: Spanner's write latency
was higher than MySQL's (50ms vs. 5ms for writes). But they concluded the engineering
productivity gain (eliminating a whole category of bugs) and the operational simplicity
(no shard management) was worth the latency cost for their use case.

---

### Part 8 Brainstorming Q&A

**Q1: If CockroachDB is open-source and runs on AWS, why would anyone choose the
more expensive, more restricted Cloud Spanner?**

There are three main reasons to choose Cloud Spanner over CockroachDB. First, external
consistency vs. serializability: Cloud Spanner provides a strictly stronger guarantee.
For financial applications where "if T1 commits before T2 starts, T2 sees T1's writes"
must hold with mathematical certainty, Spanner's TrueTime-backed guarantee is better than
CockroachDB's HLC approximation. Second, tail latency: CockroachDB's clock uncertainty
restarts add unpredictable tail latency (P99.9 might be 5x higher than P50). For
latency-sensitive applications (e.g., ad serving, payments), Spanner's deterministic
commit-wait is preferable. Third, operational simplicity on Google Cloud: if you are
already on GCP, Cloud Spanner is fully managed, auto-scaling, and integrated with Google
IAM, Cloud Monitoring, etc. No Kubernetes deployment, no capacity planning, no version
upgrades. For teams without deep database expertise, the managed service is worth the
premium.

**Q2: Could Amazon or Microsoft build their own version of Spanner? What would it take?**

Technically yes — the Spanner paper is public and the algorithms are known. The bottleneck
is infrastructure. To replicate TrueTime, you need GPS receivers and atomic clocks in every
datacenter. Amazon has begun this with the "Amazon Time Sync Service" which uses GPS-synchronized
time on AWS infrastructure, achieving sub-millisecond accuracy for NTP. This is better than
generic NTP but still not as bounded as TrueTime (Amazon doesn't publish the formal ε bound).
Microsoft Research has published papers on similar systems ("HT" / "Clock-SI"). The key
challenge is not the algorithms — it's the operational discipline to maintain GPS/atomic clock
hardware in every datacenter globally, the culture of treating time accuracy as a first-class
reliability concern, and the years needed to harden the system. Google has had TrueTime in
production since ~2010. Getting to that level of maturity takes a decade.

**Q3: Are there cases where DynamoDB with transactions is a better choice than Spanner?**

Yes. DynamoDB transactions (added in 2018) provide serializable isolation within a single
DynamoDB region for transactions touching up to 100 items. If your use case is: single-region
AWS deployment, key-value access pattern, scale to millions of requests per second, and you
do not need cross-continent consistency — DynamoDB with transactions is often the right choice.
DynamoDB's P99 latency is 5-15ms (single region), lower than Spanner's 30-80ms for comparable
transactions. DynamoDB's pricing model (pay per request) is also often cheaper at variable
workloads. Choose Spanner when: you need SQL JOINs, you need cross-region ACID, you need
external consistency, or your access patterns are complex and relational. Choose DynamoDB when:
you are on AWS, you need maximum write throughput with simple key-value access, and
eventual/regional consistency is sufficient.

---

## Part 9: Interview Application

### 9.1 When to Cite Spanner in an Interview

Spanner is the right answer to reach for when an interview question involves one or more of:
- **Global distribution**: "Design a system for users on 5 continents"
- **Cross-shard ACID transactions**: "How do you ensure a payment deducting from one
  account and crediting another is atomic?"
- **Consistency guarantees**: "What consistency level does your system provide?"
- **External consistency**: "After a user updates their profile, how do you ensure
  all other systems see the update?"
- **Database selection for critical data**: "What database would you use for financial
  transactions?"

### 9.2 L5 vs. L6 Answer Quality

Here is the same interview question answered at different levels:

**Question**: "You're designing a global payment system. How would you ensure that
if a payment commits, all subsequent balance checks show the deducted amount?"

---

**L3 Answer** (too vague):
"I would use a consistent database like Spanner or CockroachDB. They guarantee
ACID transactions so the balance would be correct."

*Problem*: Does not explain the mechanism. Does not address what "consistent" means
precisely. Does not address the cross-region latency trade-off.

---

**L4 Answer** (better, but incomplete):
"I would use Spanner for this. Spanner provides external consistency, meaning if
the payment commits before the balance check starts, the balance check is guaranteed
to see the deducted amount. This is because Spanner uses TrueTime, a GPS-synchronized
clock API, to assign commit timestamps. After committing, Spanner waits until real
time has passed the commit timestamp (commit-wait), ensuring any subsequent transaction
picks a higher timestamp."

*Problem*: Correct overview, but does not address the latency cost, does not mention
when Spanner would NOT be the right choice, and does not discuss what happens during
failures.

---

**L5 Answer** (solid):
"For global external consistency on payment data, Spanner is the right tool.
Spanner's TrueTime mechanism assigns commit timestamps with bounded uncertainty ε
(1-7ms), then stalls the commit (commit-wait) until TrueTime confirms real time
has passed the commit timestamp. This mathematically ensures any subsequent
transaction starts with a higher timestamp, giving external consistency.

The latency cost is real: cross-region writes take 30-80ms. For payments, this
is acceptable — users expect a 1-2 second confirmation. The balance check after
payment can use a snapshot read at a specific timestamp, which requires no locking
and can be served by any replica.

Trade-offs to consider: If we need sub-10ms writes (e.g., high-frequency trading),
Spanner is too slow. If we're on AWS, we'd use CockroachDB instead (HLC-based,
similar guarantees, slightly weaker). If global consistency is not required (e.g.,
a regional payment system), a single-region Postgres cluster is simpler and faster."

*Why this is L5*: Correctly explains the mechanism, addresses latency, discusses
alternatives, and discusses when NOT to use Spanner.

---

**L6 Answer** (exceptional):
"For a global payment system, I'd use Spanner and reason through the consistency
requirements explicitly.

External consistency is necessary here: if payment T1 commits before balance check T2
starts, T2 must see the deducted balance. This is stronger than serializability (which
doesn't need to match wall-clock order). TrueTime makes this provable: after T1's
commit-wait, real time > s1. Any future transaction T2 calls TT.now() and gets an
earliest value > s1 (since real time > s1 and TrueTime is correct), forcing s2 > s1.
T2 reads a snapshot at s2 > s1, which includes T1's write. The proof is complete.

For the data model, I'd interleave account and transaction tables:
- `Accounts` table: primary key (account_id)
- `Transactions` table: interleaved in parent Accounts, key (account_id, transaction_id)
- Balance reads: snapshot read on the account row (single-shard, no leader needed)
- Payment write: read-write transaction on two account rows (2PC if different tablets)

Latency expectations: cross-region payment ~50ms, balance check ~5ms (snapshot read
from local replica). For the balance check, I'd use `AS OF SYSTEM TIME '-5s'` to
ensure it hits a local replica, trading 5 seconds of potential staleness for sub-5ms
latency — acceptable because the payment gateway already enforces the ordering.

Failure modes: if the Paxos leader fails mid-commit-wait, the new leader recovers
from the Paxos log and completes or aborts. The client retries with idempotency keys
(payment_id) to prevent double charges.

At 10x scale, the hot-spot to watch is account rows for very active merchants (Stripe,
Amazon). I'd shard high-traffic accounts across N virtual shards (balance_shard_0 through
balance_shard_N-1) and aggregate at read time. This is the same technique used in
Bigtable for counter sharding."

*Why this is L6*: Provides the mathematical proof, discusses specific data model
choices with interleaving, gives concrete latency numbers, addresses failure modes,
and proactively identifies scale challenges with solutions.

### 9.3 Common Interview Mistakes

**Mistake 1: Confusing Spanner with Bigtable**
Bigtable (Chapter 29) is Google's wide-column, eventually-consistent key-value store.
Spanner is Google's strongly consistent relational SQL database. They are completely
different. Bigtable has no SQL, no ACID transactions, and no external consistency.
Spanner has all three. If an interviewer asks about Google's global databases, you must
know which is which.

*Correct answer*: "Bigtable is Google's NoSQL wide-column store optimized for high
write throughput, similar to HBase. Spanner is Google's globally distributed SQL
database with external consistency, used for financial data and critical records.
They are not interchangeable."

**Mistake 2: Saying TrueTime "eliminates" clock skew**
TrueTime does not eliminate clock skew. It quantifies it. The uncertainty interval ε
IS the clock skew — TrueTime tells you how large it is at any given moment. The
commit-wait protocol works WITH the clock skew, not by eliminating it.

*Correct framing*: "TrueTime doesn't sync clocks perfectly — it measures the maximum
current clock uncertainty and lets you reason about it precisely."

**Mistake 3: Claiming snapshot reads are free**
Snapshot reads are much cheaper than read-write reads (no locks, no commit-wait), but
they are not free. They may need to wait for a replica to catch up to the requested
timestamp. If a replica is 5ms behind the leader, a snapshot read at "now" will wait
~5ms. For snapshot reads with a staleness bound (e.g., `-5s`), any replica within
5 seconds can serve them immediately — which is usually all replicas.

*Correct answer*: "Snapshot reads are nearly free if you allow some staleness. For
exact-now reads, you might wait a few milliseconds for the replica to catch up."

**Mistake 4: Not knowing when Spanner is the wrong answer**
Saying "use Spanner" for every global database question is a red flag. Spanner is
expensive, has minimum latency costs, and is Google-Cloud-only. An L6 engineer knows
the alternatives and when to use them.

*Correct approach*: Always qualify Spanner recommendations with latency trade-offs,
cost, and cloud portability considerations.

**Mistake 5: Describing commit-wait as "waiting for the replica to catch up"**
Commit-wait has nothing to do with replica lag. It is the coordinator waiting until
TrueTime confirms that real time has passed the commit timestamp. The purpose is to
ensure future transactions pick higher timestamps. Replica lag is a separate issue.

*Correct description*: "Commit-wait is the transaction coordinator stalling after
choosing a commit timestamp s, waiting until TT.now().earliest > s. This ensures
real time has passed s, so any future TT.now() call returns an earliest > s, forcing
future timestamps to be > s."

**Mistake 6: Assuming 2PC means Spanner has the "2PC liveness problem"**
Traditional 2PC can block indefinitely if the coordinator fails. Spanner avoids this
because the coordinator is a Paxos group, not a single machine. If the leader fails,
Paxos elects a new leader that can recover the commit decision from the Paxos log
and complete or abort the transaction. Participants have a timeout and will query
the coordinator's Paxos group, eliminating the blocking problem.

*Correct answer*: "Spanner uses 2PC but avoids the classic 2PC liveness problem
because the coordinator is a Paxos group. Participants can always determine the
commit/abort outcome by consulting the coordinator's Paxos group."

### 9.4 Sample Interview Questions and Hints

**Q: Design a distributed bank ledger that guarantees no double-spends globally.**
*Hint*: Use Spanner. Explain read-write transactions with 2PL. Address how the
account balance row is locked during the transaction. Discuss commit-wait. Mention
idempotency keys for retry safety.

**Q: Why can't you use Cassandra for a payment system?**
*Hint*: Cassandra is eventually consistent by default. Even with LOCAL_QUORUM or
QUORUM, it doesn't provide ACID transactions or external consistency. Two concurrent
"check balance, then debit" operations can both succeed, causing a race condition.

**Q: What's the difference between external consistency and linearizability?**
*Hint*: Linearizability is for single objects (reads and writes on one key).
External consistency is linearizability extended to transactions (multi-key operations).
Spanner provides external consistency, which implies linearizability for all operations.

**Q: How would you reduce Spanner's write latency if it's too high?**
*Hint*: You cannot reduce commit-wait (it is bounded by ε, which is physics).
You CAN: (1) move Paxos leaders closer to users, (2) minimize cross-shard transactions
by using interleaving, (3) batch writes together, (4) use read-only transactions when
possible, (5) accept that write latency is a fundamental cost of external consistency.

---

### Part 9 Brainstorming Q&A

**Q1: In an interview, the interviewer asks "what consistency does Spanner provide?"
Should I say serializable or externally consistent?**

Say "externally consistent," and then explain the difference if asked. External
consistency is a specific, stronger guarantee than serializability. Serializable
means transactions appear to execute in some serial order; external consistency means
that serial order must match real wall-clock time. Spanner provides both (external
consistency implies serializability). If you say "serializable," a knowledgeable
interviewer might follow up with "is that all?" and you should clarify to external
consistency. Saying "externally consistent" first demonstrates that you know the
precise terminology. Most candidates at L5/L6 know "serializable" but the truly
senior candidates know "external consistency" and can explain the difference.

**Q2: I'm designing a system and I think I might need Spanner, but I'm not sure.
How do I reason about this in an interview?**

Ask yourself four questions. First: do I need transactions across multiple rows or
tables? If all operations touch a single row/entity and eventual consistency is OK,
you don't need Spanner. Second: do I need cross-region consistency? If all data
lives in one region, single-region Postgres is simpler and faster. Third: can I
tolerate 30-80ms write latency? If not, Spanner is not the right choice. Fourth:
am I on Google Cloud? If not, Spanner is not available; consider CockroachDB.
If the answers to all four are "yes, yes, yes, yes," Spanner is probably the right
tool. If any answer is "no," there's likely a simpler or faster alternative. Share
this reasoning out loud in the interview — it demonstrates structured thinking.

**Q3: How detailed should my TrueTime explanation be in an interview? Should I
derive the proof that commit-wait ensures external consistency?**

It depends on the level you're interviewing for and the interviewer's signal. For L5,
explain the intuition clearly: "TrueTime returns an uncertainty window [earliest, latest].
By waiting until real time has passed the commit timestamp (which is at most t_latest),
we ensure future transactions see a higher timestamp." This is usually sufficient.
For L6 (especially at Google, where Spanner was built), you should be ready to derive
the proof: "T1 commits at real time R1 > s1. T2 starts at real time R2 > R1. T2 calls
TT.now(), getting [t_e2, t_l2] where t_e2 ≤ R2. T2 picks s2 = t_l2 ≥ t_e2 ≤ R2 > R1 > s1.
Wait — this isn't quite right, let me re-derive..." If the interviewer pushes you on
the proof, engage with the math, but don't make it a lecture. Show that you can reason
precisely, then step back to the high level.

---

## Part 10: Real Incidents and Limitations

### 10.1 Production Limitation: Write Hot Spots in Advertising

Shortly after F1 migrated to Spanner (2012-2013), the Ads team encountered a real
hot-spot problem. Google's most-advertised product at the time was YouTube Premium.
YouTube Premium's ad campaigns had extremely high traffic — thousands of ad auctions
per second, each potentially updating campaign budget counters.

The campaign budget row became a write hot spot. Every time a user saw a YouTube Premium
ad, the system would try to decrement the remaining daily budget. All these writes went
to the Paxos leader for the campaign budget row, overloading a single spanserver.

The fix was the "distributed counter" pattern, which the F1 team calls "sharded counters":
- Instead of one row `(campaign_id, remaining_budget)`, use N rows:
  `(campaign_id, shard_id, remaining_budget)` where shard_id is 0 to N-1.
- Each ad serving machine writes to a randomly selected shard.
- To check total budget, sum across all N shards.
- To reset daily budget, update all N shards (one write per shard, batched).

With N=64, the write throughput for a single campaign was 64x the single-row limit.
The trade-off: reads are now aggregation queries (64 row reads instead of 1), and
"is there budget left?" is now approximate (might overcount by up to N transactions'
worth). They accepted this approximation — a few extra ad deliveries per day was
acceptable.

This pattern is now documented in Cloud Spanner's best practices guide as the
standard approach for high-throughput counters.

### 10.2 Production Incident: TrueTime Spanner Unavailability (Hypothetical)

Google has not publicly disclosed TrueTime-related outages (their operational
transparency is limited compared to, say, AWS's service health dashboard). However,
we can reason about what would happen and what mitigations exist.

**Scenario**: All GPS receivers in a zone simultaneously lose signal (imagine severe
solar storm affecting GPS satellites).

**What happens**: Time masters in that zone cannot sync to GPS. Their uncertainty
estimates start growing as atomic clocks drift. After 30 seconds, ε might be 10ms.
After 5 minutes, ε might be 50ms.

**Spanner's response**:
- The time masters widen their ε estimates continuously.
- Paxos leaders check ε before accepting writes. If ε exceeds a threshold, they
  refuse new writes and wait for GPS restoration.
- Read-only transactions continue (they don't need commit-wait, just a timestamp).
- Write transactions queue up during the GPS outage.
- Once GPS is restored (typically within minutes), ε shrinks, and writes resume.

**Why this is safe**: Spanner prefers stopping writes over giving incorrect results.
This is a consistency-over-availability trade-off — exactly what Spanner's design
philosophy requires (CP from CAP theorem). In practice, GPS outages affecting all
receivers in a datacenter are extremely rare (GPS has multiple redundant satellite
constellations: GPS, GLONASS, Galileo). Google's time masters use multiple constellations.

### 10.3 Real Limitation: Spanner's Cost in Multi-Region Configuration

A common complaint from Cloud Spanner users (from public Google Cloud forums and
engineering blogs):

Multi-region Cloud Spanner configurations cost significantly more than single-region.
A `nam6` (6-region North America) configuration costs roughly 3-6x the compute and
storage of a single-region instance. For a startup with a global product, this can
be $10,000-50,000/month before considering actual query volume.

Companies have reported:
- Moving from multi-region Spanner back to single-region Spanner + async replication
  for cost savings, accepting slightly weaker consistency.
- Using Cloud Spanner only for "critical" tables (financial records) while keeping
  less-critical tables in Cloud SQL (Postgres) or Firestore.
- Designing their systems to minimize cross-region transactions by partitioning
  users by region (user in Europe → European Spanner instance).

The lesson for interviews: always address cost when recommending Spanner. It is not
a commodity database. For a startup or a non-critical system, "use Postgres with
logical replication" is often the right recommendation, even if it means slightly
weaker consistency.

### 10.4 Limitation: Spanner is Not a Drop-In Replacement for MySQL/Postgres

Several teams have tried to migrate from MySQL or PostgreSQL to Spanner and hit
unexpected challenges:

1. **Different SQL dialect**: Spanner's SQL is a Google-specific dialect. Features
   like stored procedures, triggers, sequences, and some JOIN syntax differ from
   standard SQL. ORM frameworks (Hibernate, SQLAlchemy) need special Spanner drivers.

2. **Mandatory primary keys**: Many MySQL tables use `AUTO_INCREMENT` without thinking
   about distribution. Migrating to Spanner requires redesigning primary keys.

3. **Interleaving requires upfront design**: You can't easily add interleaving after
   the fact. Moving from flat tables to interleaved tables requires data migration.

4. **No foreign key support initially**: Early Spanner had no foreign key constraints.
   They were added in 2020. But the enforcement is weaker than Postgres (no
   `ON DELETE CASCADE` in the same way; it's supported but with constraints).

5. **Transaction size limits**: Spanner limits transactions to 80,000 mutations and
   5GB of data. Very large batch operations must be split.

These are all solvable problems, but they make Spanner migrations non-trivial.
Teams often underestimate the schema redesign work required.

### 10.5 Limitation: Spanner's Query Planner for Complex SQL

Spanner's SQL query planner, while functional, is not as mature as Postgres's or
Oracle's. Complex analytical queries with many JOINs, correlated subqueries, and
window functions may not be optimized as well as in a single-node database.

For complex analytics, Google recommends:
- Use Spanner for OLTP (online transaction processing) — point lookups, small queries
- Stream data from Spanner to BigQuery for analytics (using Spanner's Dataflow connectors)
- BigQuery handles the OLAP workload (big scans, complex aggregations)

This two-tier approach (Spanner for OLTP, BigQuery for OLAP) is the standard
Google-recommended pattern and aligns with how Google Ads itself is run.

### 10.6 Spanner Internals: What Was Omitted

To keep this chapter accessible, we skipped some advanced internals. For L6 interviews
at Google (where Spanner was built), these may come up:

**Paxos leader leases**: Leaders hold a time-based lease to avoid re-election overhead.
A leader can serve reads without checking in with followers as long as the lease is
valid. Lease duration must be less than the Paxos leader election timeout.

**Safe time**: Each Paxos follower maintains a "safe time" — the highest timestamp at
which it has a complete log. Reads at a timestamp ≤ safe time can be served without
waiting. This is how replicas know when they're "caught up enough" to serve a read.

**Long-lived transactions and deadlock**: Spanner uses wound-wait for deadlock
prevention (younger transactions abort), but very long-running transactions that hold
many locks can cause cascading aborts of younger transactions. The recommendation is
to keep transactions short.

**Partitioned DML**: For large-scale updates (like batch deleting old records), Spanner
provides "Partitioned DML" — a special mode that splits a large mutation into many
smaller transactions, each touching a subset of rows. This avoids the 80,000-mutation
limit but provides only "at-least-once" semantics (rows might be processed multiple
times if a shard fails and retries).

---

### Part 10 Brainstorming Q&A

**Q1: Google never discloses outages, but if Spanner had a consistency failure, how
would they detect it? Is it even detectable after the fact?**

Detecting consistency violations in a live system is harder than preventing them, but
Google has monitoring for this. They use "read-your-writes" consistency checks: after
a write commits, a monitoring system immediately reads the written data and verifies
it is visible. If a read returns stale data after a committed write, it is a consistency
anomaly. They also run periodic database audits comparing checksums across all replicas
for every tablet — if replicas disagree, it's a bug. For external consistency specifically,
they run automated tests that commit transaction T1, record the real-world completion time,
then start T2 immediately and verify T2 sees T1's writes. These tests run continuously
in production on test databases. Google has also published mathematical proofs of
Spanner's correctness, so in theory, if the implementation matches the specification,
correctness violations cannot occur. The remaining risk is implementation bugs (bugs in
TrueTime's uncertainty calculation, bugs in commit-wait logic), which are caught by the
monitoring above.

**Q2: What's the realistic scenario where Spanner gives you the wrong answer? Can it
actually fail?**

In theory, Spanner cannot fail its external consistency guarantee if: (1) TrueTime's
guarantee holds (ε is correctly bounded), (2) the implementation correctly computes
commit timestamps and enforces commit-wait, and (3) there are no software bugs. All
three conditions are believed to hold in Google's production system. A realistic failure
scenario: a bug in the TrueTime client library underestimates ε, causing commit-wait
to be shorter than required. This could allow a future transaction to pick a timestamp
≤ a recently committed timestamp, violating external consistency. Such a bug would
likely affect only a small fraction of transactions and be detectable by the monitoring
systems described above. Google's track record (no publicly known external consistency
failures in Spanner since 2010) suggests the system is well-hardened. But no system
is perfectly bug-free — the honest answer is "extremely unlikely but not impossible."

**Q3: Will Spanner-like systems become more common as GPS hardware gets cheaper? Could
every cloud provider eventually have TrueTime?**

The hardware is not the main barrier — GPS modules cost $10-50 for consumer-grade units.
The challenge is the operational discipline: every datacenter needs GPS antennas installed
on the roof, every time master machine needs maintenance, the software for computing ε
and the TrueTime API needs to be reliable. Amazon has invested in this with their Time
Sync Service (using GPS receivers in AWS datacenters) and is progressively improving its
accuracy. If sub-millisecond NTP becomes standard at cloud providers, the external
consistency story becomes possible at AWS/Azure scale. The trend is clearly toward
tighter clock synchronization across cloud infrastructure. In 5-10 years, we may see
HLC uncertainty bounds shrink to 1-5ms on commodity cloud infrastructure, making the
performance gap between HLC systems (CockroachDB, YugabyteDB) and TrueTime systems
(Spanner) much smaller. At that point, the architectural difference between Spanner
and its open-source alternatives becomes mainly an engineering maturity and feature-set
question rather than a fundamental capability gap.

---

## Part 11: Interview One-Liners and Quick Decision Guide

### 11.1 The Sentences That Signal You Know Spanner

These are the exact phrasings that distinguish an L5 answer from a generic one.
Memorize the concept, not the words — then adapt in the interview.

**Defining external consistency in one breath:**
> "External consistency means: if T1 commits before T2 even starts in real wall-clock
> time, T2 is guaranteed to see all of T1's writes. It's serializability where the
> serial order must match real-world time — a stronger guarantee."

**Defining TrueTime in one breath:**
> "TrueTime is Google's clock API that returns an interval [earliest, latest] rather
> than a single timestamp. The actual current time is guaranteed to be inside that
> interval. The interval width — called ε — is 1 to 7ms, backed by GPS receivers and
> atomic clocks in every Google datacenter."

**Defining commit-wait in one breath:**
> "Commit-wait is the stall that makes external consistency provable. After choosing
> commit timestamp s = TT.now().latest, the coordinator waits until TT.now().earliest > s —
> meaning real time has definitely passed s. Any future transaction then picks a
> timestamp greater than s. That's the ordering guarantee."

**Distinguishing Spanner from CockroachDB in one breath:**
> "CockroachDB uses Hybrid Logical Clocks instead of TrueTime — no GPS hardware needed,
> runs anywhere. But the uncertainty is larger and variable, so instead of commit-wait,
> it restarts transactions when timestamps might conflict. Same goal, different trade-off:
> Spanner pays ε ms at commit; CockroachDB occasionally retries."

**Distinguishing Spanner from Bigtable in one breath:**
> "Bigtable is a wide-column NoSQL store with row-level atomicity only — no SQL, no
> cross-row transactions. Spanner adds ACID, SQL, and TrueTime-backed external
> consistency on top of similar storage primitives. They complement each other:
> Spanner for correctness, Bigtable for throughput."

---

### 11.2 The Decision Tree: When to Say "I'd Use the Spanner Model"

```
  DO YOU NEED CROSS-ROW ATOMIC TRANSACTIONS?
  ─────────────────────────────────────────────
  No  → Use Bigtable, DynamoDB, or Cassandra
  Yes ↓

  DO YOU NEED CROSS-REGION CONSISTENCY?
  ─────────────────────────────────────────────
  No  → Single-region Postgres or MySQL (simpler, faster, cheaper)
  Yes ↓

  CAN YOU TOLERATE 30-80ms WRITE LATENCY?
  ─────────────────────────────────────────────
  No  → You cannot use Spanner. Re-examine the requirement.
  Yes ↓

  ARE YOU ON GOOGLE CLOUD?
  ─────────────────────────────────────────────
  No  → CockroachDB (serializable, HLC, open-source)
         or YugabyteDB (Cassandra + PostgreSQL APIs)
  Yes ↓

  → USE CLOUD SPANNER
    (External consistency, SQL, interleaved tables,
     automatic sharding, no operational overhead)
```

---

### 11.3 When NOT to Drop the "Spanner" Name

Interviewers at non-Google companies will sometimes view "Spanner" as a crutch answer —
a name drop without understanding. These situations call for caution:

**Don't say Spanner when:**
- The system is a single-region internal service. An L5 saying "I'd use Spanner for
  our internal config store" sounds over-engineered. Say "Postgres, with logical
  replication if we later need a read replica."
- Write latency below 10ms is a real requirement. Saying "Spanner" when you need
  sub-10ms commits shows you don't understand Spanner's commit-wait overhead.
- The interviewer works at AWS or Azure, and you haven't qualified cloud portability.
  Say "CockroachDB if we need multi-cloud, or Cloud Spanner if we're committed to GCP."
- The access pattern is key-value with high write throughput. Say "DynamoDB" or
  "Bigtable" — Spanner's overhead is unnecessary.

**Do say Spanner (or "the Spanner model") when:**
- The question involves global financial transactions, ledgers, or payments.
- The phrase "external consistency" or "cross-region ACID" appears anywhere.
- The interviewer asks "what does Google use for this?" — Spanner is the correct answer
  for critical transactional data at Google.
- You're designing the source-of-truth store for a system that uses Bigtable or Redis
  as a cache — Spanner is the write-through target.

---

### 11.4 The One Calibration Signal Interviewers Look For

When a candidate says "I'd use Spanner," most L6 interviewers at companies that use
distributed databases will probe with one of two questions:

1. **"How does Spanner ensure global consistency?"** — They want: TrueTime, commit-wait,
   the timestamp ordering proof. If you can explain commit-wait in two sentences, you
   pass this signal.

2. **"What's the latency cost?"** — They want: 30-80ms for cross-region writes, 1-15ms
   for snapshot reads, ε (~5ms) for commit-wait. If you can give order-of-magnitude
   numbers, you pass this signal.

If you can answer both in under 60 seconds, you have demonstrated L5-level Spanner
fluency. The difference between L5 and L6 is whether you also proactively mention
when Spanner is the wrong choice and what you'd use instead.

---

## Key Takeaways

```
╔══════════════════════════════════════════════════════════════════════╗
║                    CHAPTER 84: KEY TAKEAWAYS                        ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  WHAT SPANNER IS                                                     ║
║  • Google's globally distributed SQL database with ACID transactions ║
║  • Provides EXTERNAL CONSISTENCY — the strongest consistency         ║
║    guarantee: if T1 commits before T2 starts (real wall time),       ║
║    T2 is guaranteed to see T1's writes                               ║
║  • Runs Google Ads ($200B/year), Google Finance, Google Play         ║
║                                                                      ║
║  TRUETIME                                                            ║
║  • API returning [t_earliest, t_latest] with guaranteed correct      ║
║    interval (actual time is definitely in range)                     ║
║  • Backed by GPS receivers + atomic clocks in every Google DC        ║
║  • Uncertainty interval ε ≈ 1-7ms in production                      ║
║  • Key property: the interval is NEVER wrong (cannot underestimate)  ║
║                                                                      ║
║  COMMIT-WAIT                                                         ║
║  • Protocol: pick s = TT.now().latest, wait until TT.after(s)       ║
║  • After commit-wait: real time > s (mathematically proven)          ║
║  • Future transactions: TT.now().earliest > s, so s2 > s1           ║
║  • Latency cost: ε milliseconds per write transaction               ║
║  • Proof: this gives external consistency. No other system does this ║
║    at global scale without hardware clocks.                          ║
║                                                                      ║
║  ARCHITECTURE                                                        ║
║  • Universe → Zones (datacenters) → Spanservers → Tablets           ║
║  • Each tablet has a Paxos group (3-5 replicas across zones)        ║
║  • Writes go to Paxos leader; snapshot reads go to any replica      ║
║  • Directory = unit of data movement; group of contiguous rows      ║
║                                                                      ║
║  TRANSACTION TYPES                                                   ║
║  • Read-write: 2PL + 2PC + commit-wait. 30-80ms cross-region       ║
║  • Read-only: snapshot timestamp, no locks, no commit-wait.         ║
║    1-15ms. Can be served by any replica anywhere.                   ║
║  • Schema changes: timestamp-based, online, no downtime             ║
║                                                                      ║
║  DATA MODEL                                                          ║
║  • Full SQL, mandatory primary keys, automatic sharding             ║
║  • Interleaved tables: store child rows inside parent row           ║
║    physically → eliminates cross-shard joins for common patterns    ║
║  • Avoid sequential primary keys (hot spot risk)                    ║
║                                                                      ║
║  PERFORMANCE                                                         ║
║  • Write latency: 30-80ms (cross-region), 7-15ms (local)           ║
║  • Read latency: 1-15ms (snapshot reads from any replica)           ║
║  • Throughput: millions of TPS across all Paxos groups              ║
║                                                                      ║
║  ALTERNATIVES                                                        ║
║  • CockroachDB: open-source, HLC, serializable (not ext consistent) ║
║  • YugabyteDB: open-source, Raft, PostgreSQL/Cassandra APIs        ║
║  • Aurora Global DB: AWS, storage-level replication, ~1s lag        ║
║  • Cloud Spanner: managed Spanner (what you can actually use)      ║
║                                                                      ║
║  WHEN TO USE SPANNER                                                 ║
║  ✓ Global financial transactions (payments, ledgers)                ║
║  ✓ Multi-region ACID with external consistency required             ║
║  ✓ Complex relational queries globally                              ║
║  ✓ Google Cloud environment                                         ║
║                                                                      ║
║  WHEN NOT TO USE SPANNER                                             ║
║  ✗ Sub-5ms write latency required (use single-region Postgres)     ║
║  ✗ AWS or Azure deployment (use CockroachDB)                        ║
║  ✗ High write throughput on a single key (hot-spot problem)        ║
║  ✗ Budget-conscious startups (Cloud Spanner is expensive)          ║
║  ✗ Analytics workloads (use BigQuery alongside Spanner)            ║
║                                                                      ║
║  THE ONE SENTENCE THAT MATTERS                                       ║
║  "Spanner achieves external consistency by using TrueTime (GPS +    ║
║   atomic clocks) to bound clock uncertainty, then stalling commits   ║
║   until that uncertainty window closes — making each commit          ║
║   timestamp provably older than any future transaction's timestamp." ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Exercises

**Exercise 1: TrueTime Math**
TrueTime returns [T, T+2ε] where ε = 5ms. A transaction calls TrueTime and picks
commit timestamp s = T+10ms (the latest bound). How long does commit-wait last?
Hint: commit-wait ends when TT.now().earliest > s. Draw a timeline.

**Exercise 2: External Consistency Proof**
Write out, in your own words, the proof that commit-wait enables external consistency.
Use symbolic notation: let s1 be T1's commit timestamp, s2 be T2's commit timestamp.
Show that if T2 starts after T1 commits in real time, then s2 > s1.

**Exercise 3: Interleaving Design**
You are building a social network with three tables: Users, Posts, and Comments.
Each post belongs to one user. Each comment belongs to one post.
Design the Spanner schema with interleaving to optimize for "get user + all their
posts + all comments on each post." What are the primary keys? What is the interleaving
hierarchy? What queries become slow with this design?

**Exercise 4: Hot Spot Identification and Fix**
You have a Spanner table `Events (event_id INT64, timestamp TIMESTAMP, user_id INT64, data STRING)` 
with primary key `(event_id)` where event_id is auto-incrementing. After launch, you
see one spanserver at 100% CPU while others are idle. Explain the problem and propose
two different fixes with trade-offs.

**Exercise 5: Transaction Type Selection**
For each of the following operations, decide: read-write transaction, read-only
transaction, or snapshot read? Justify your choice.
(a) Transfer $100 from Alice to Bob
(b) Generate a monthly account statement
(c) Check if a username is available before registration
(d) Count total registered users for a dashboard
(e) Update a user's email address
(f) Get a consistent snapshot of all account balances for audit

**Exercise 6: Spanner vs. Cassandra**
A startup is building a ride-sharing app. They need to record rides globally, match
drivers to riders, and process payments. They are considering Spanner vs. Cassandra.
Write a 2-paragraph comparison. For what parts of this system would you use each?

**Exercise 7: Failure Mode Analysis**
In a Spanner deployment with 3 zones (A, B, C), each tablet has 3 replicas (one per
zone). Answer these questions:
(a) Zone B loses power. What happens to reads? What happens to writes?
(b) The Paxos leader in Zone A for tablet T1 crashes during commit-wait. What happens?
(c) All GPS receivers in Zone C lose signal for 30 seconds. What happens to ε?
    What happens to writes from Zone C's spanservers?

**Exercise 8: Performance Estimation**
Your service makes 10,000 write transactions/second globally. Each transaction touches
2 shards in 2 different US regions (Virginia and Oregon). Network latency VA→OR is
14ms one-way. TrueTime ε is 5ms.
(a) Estimate the minimum possible P50 write latency.
(b) What is the throughput per Paxos group, given that each group handles equal load?
(c) If you reduce cross-region transactions by 80% (through better data modeling),
    how does P50 latency change?

---

## Homework

**Homework 1: Read the Original Papers**
Read these two papers (both free online):
- Corbett et al., "Spanner: Google's Globally-Distributed Database," OSDI 2012
- Shute et al., "F1: A Distributed SQL Database That Scales," VLDB 2013

For each paper, write 5 bullet points of things you learned that were NOT covered
in this chapter.

**Homework 2: Cloud Spanner Hands-On**
Sign up for a Google Cloud trial (free $300 credit). Create a Cloud Spanner instance
with a multi-region configuration (nam6). Create the Users+Orders schema using
interleaving. Insert 1,000 rows and run both read-write and read-only transactions.
Measure the latency for each type. Write up your observations.

**Homework 3: CockroachDB Comparison**
Download CockroachDB and run it locally with 3 nodes (simulating 3 zones). Create
the same Users+Orders schema. Run a distributed write transaction that touches two
nodes. Use `SHOW TRACE FOR SESSION` to see the clock uncertainty handling. Compare
this to what Spanner would do.

**Homework 4: Design Exercise — Global Inventory System**
Design a globally distributed inventory system for an e-commerce company with users
in US, Europe, and Asia. Requirements: no item can be oversold (ACID guarantee),
users see consistent inventory counts, updates propagate globally within 1 second.
Your design doc should cover: data model (with Spanner schema), transaction types used,
how you handle the hot-spot problem for popular items, failure mode analysis, and
latency estimates for purchase transactions.

**Homework 5: Interview Simulation**
Have a friend ask you: "How would you design a global bank ledger with no
double-spends?" Give a 10-minute answer. Record yourself. Review and identify:
(a) Did you explain TrueTime accurately?
(b) Did you mention commit-wait and why it's necessary?
(c) Did you discuss alternatives and when NOT to use Spanner?
(d) Did you give concrete latency numbers?
(e) Did you address failure modes and how the system recovers?

---

## References and Further Reading

**Primary Sources:**
- Corbett et al., "Spanner: Google's Globally-Distributed Database," OSDI 2012
  — The original paper. Read Section 4 (TrueTime) and Section 5 (Concurrency Control).
- Shute et al., "F1: A Distributed SQL Database That Scales," VLDB 2013
  — The migration story and real-world performance numbers.
- Google Cloud Spanner Documentation — Schema design best practices, interleaving guide

**Related Chapters in This Book:**
- Chapter 10: CAP Theorem
- Chapter 18: ACID Transactions
- Chapter 20: Two-Phase Commit
- Chapter 26: Paxos and Raft Consensus
- Chapter 27: Hybrid Logical Clocks (CockroachDB's alternative to TrueTime)
- Chapter 29: Bigtable (Google's other global database — NOT the same as Spanner)
- Chapter 85: CockroachDB — Spanner for the rest of us

**For Deep Dives:**
- CockroachDB's blog posts on "Living Without Atomic Clocks" — excellent explanation
  of why TrueTime is hard to replicate
- "Consistency in Non-Transactional Distributed Storage Systems" (survey paper) —
  covers the full consistency model landscape
- Amazon's "Time Sync Service" announcements — shows AWS moving toward TrueTime-like
  accuracy

---

*Chapter 84 complete. Pairs with Chapter 27 (HLC/CockroachDB), Chapter 29 (Bigtable),
and Chapter 85 (CockroachDB in depth). Section 6 concludes with Chapter 86: NewSQL
and the Future of Distributed Databases.*
