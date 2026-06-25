# Chapter 85: Borg — Google's Cluster Manager

> "Borg manages the lifecycle of all of Google's production workloads. It is the
> system that decides which machine runs Gmail, which runs Search, and which runs
> your MapReduce job — simultaneously, across a fleet of hundreds of thousands of
> machines, without human intervention."
> — Verma et al., "Large-scale cluster management at Google with Borg" (EuroSys 2015)

---

## Why This Chapter Matters

Every senior engineering interview that touches "how do you run 10,000 jobs across
1,000 machines" is a Borg question in disguise. Kubernetes — the system that runs
most of the world's containerized workloads today — is essentially open-source Borg.
Every concept maps directly. Knowing Borg lets you speak fluently about why Kubernetes
works the way it does, not just how.

This chapter is also a masterclass in distributed systems thinking. Borg solved problems
that most engineers still get wrong: how to pack workloads efficiently, how to build a
self-healing system without writing explicit failure handlers, how to maintain availability
when your control plane itself fails. These are L6 ideas regardless of which company
you are interviewing at.

**The 2015 EuroSys paper** "Large-scale cluster management at Google with Borg" by
Verma, Pedrosa, Korupolu, Oppenheimer, Tune, and Wilkes is the primary source for
this chapter. It is one of the most cited systems papers of the decade and is explicitly
referenced in Google system design interviews.

---

## The One-Sentence Summary

> Borg is Google's cluster manager: you declare desired state (100 replicas, 2 CPUs each),
> and Borg's reconciliation loop continuously makes the cluster match that state —
> handling machine failures, packing tasks efficiently, and preempting batch jobs for
> production traffic — making Kubernetes its open-source descendant.

---

## Key Numbers from the 2015 Paper (Memorize These)

| Metric | Value |
|--------|-------|
| Machines managed per cell | Tens of thousands (median cell ~10k machines) |
| Number of cells at Google | Tens of cells |
| Utilization improvement over naive assignment | ~20 percentage points (60-70% vs 40-50%) |
| BorgMaster replicas | 5 (Paxos-elected) |
| BorgMaster failover time | ~10 seconds |
| Priority levels | 0–450 scale |
| Task scheduling latency (median) | < 25 seconds |
| Borglet poll interval | A few seconds |

---

## Part 1: The Cluster Management Problem — Before Borg

### 1.1 What Was Life Like Without a Cluster Manager?

Imagine you work at Google in 2003. Your team just wrote a new feature for Gmail.
You need to deploy it. Here is the process:

Step 1: Email the infrastructure team and ask for machines.
Step 2: Wait a week for the machines to be assigned.
Step 3: SSH into each machine and manually start your program.
Step 4: Write a cron job on each machine to restart your program if it crashes.
Step 5: Monitor each machine yourself.
Step 6: If a machine dies, notice it, SSH to a new machine, and manually restart there.

This is not a joke. This is roughly how things worked before cluster managers existed.

The problems were enormous. First, every team over-provisioned. If you needed 100
machines on your busiest day, you reserved 150 "just in case." You never gave those
50 machines back. Across thousands of teams, this wasted 30-40% of Google's entire
datacenter capacity — hundreds of millions of dollars of hardware sitting idle.

Second, there was no isolation between teams. If the team next door had a runaway
process eating memory, it slowed down your service. Nobody knew whose code caused
the problem.

Third, failure recovery was entirely manual. When a machine died at 3 AM, a human
had to wake up, figure out which jobs were on it, and restart them elsewhere. Google
was running hundreds of thousands of machines. Machines fail every single day at
that scale. This was completely unsustainable.

### 1.2 The Scale of the Problem

To understand why Google needed Borg, you need to understand the scale. By the
mid-2000s, Google was running:

- Multiple datacenters (called "cells" in Borg terminology) each with tens of
  thousands of machines
- Two fundamentally different types of workloads sharing the same machines:
  **long-running services** (Gmail, Google Search, Google Ads — must be online 24/7)
  and **batch jobs** (MapReduce data processing pipelines — can tolerate being paused
  or rescheduled)
- Thousands of engineering teams each with their own software they wanted to run

The insight that created Borg was simple but powerful: instead of thinking about
"which team owns which machine," think about "the whole datacenter is one big
computer." Your code doesn't care which physical machine it runs on. So why should
you have to specify one?

### 1.3 The Core Vision — A Sea of Compute

Borg's founders wanted engineers to think about compute the way we think about
electricity. When you plug in a lamp, you don't care which power plant generates
the electricity. You just get power. Borg wanted engineers to say "I need 100 units
of compute" and have the system figure out where to run it.

This vision had three concrete goals:

**Goal 1: Hide machine management.** Engineers should never SSH to individual machines.
They should describe what they want to run, and Borg runs it.

**Goal 2: Maximize utilization.** Mix long-running services (high priority, always on)
with batch jobs (lower priority, can be interrupted) on the same machines. When the
services are idle at night, the batch jobs use that spare capacity. Utilization goes
from 40% to 60-70%.

**Goal 3: Self-healing.** When machines fail — and at scale, they fail every day —
jobs automatically restart elsewhere without human intervention.

### 1.4 Real Incident: The Pre-Borg Super Bowl

In February 2005, Google's Search frontend experienced a traffic spike during the
Super Bowl. Without automatic rescheduling, on-call engineers scrambled manually.
They had to identify which machines had spare capacity, SSH to those machines, start
new replicas of the search frontend, and update load balancers by hand — all while
the traffic surge was actively happening.

The process took almost two hours. Search availability degraded. Engineers were
exhausted. After the incident, the infrastructure team wrote a post-mortem that
began: "We need a system that handles this automatically." That post-mortem was one
of the motivating documents that led to Borg.

With Borg, the same scenario plays out differently: traffic spikes, Borg detects that
desired capacity (say, 500 replicas) is not enough, engineers increase the desired
count to 700, and Borg automatically finds machines, starts new replicas, and
registers them with the load balancer — all within minutes, without anyone SSHing
to anything.

---

### Brainstorming: Part 1 Questions

**Q1: Why couldn't Google just buy more machines to solve the utilization problem?**

Buying more machines does not solve the utilization problem — it makes it worse. If
every team over-provisions by 30%, adding more machines means more over-provisioning.
The waste scales linearly with the fleet size. At Google's scale in 2005, 30%
utilization waste meant hundreds of millions of dollars of hardware sitting idle per
year. The problem is not lack of hardware — it is lack of a mechanism to share
hardware efficiently across teams. Borg's contribution is precisely that mechanism.
More hardware without better scheduling just means more expensive waste.

There is also a power and cooling dimension. Datacenters have fixed power budgets.
You cannot just add unlimited machines — you run out of power capacity long before
you run out of physical space. Higher utilization means more work done per watt,
which is a hard physical constraint that money cannot easily solve.

**Q2: Why is mixing long-running services with batch jobs the key to high utilization?**

Long-running services like Gmail have diurnal (daily) traffic patterns. During peak
hours — say, 9 AM to 9 PM in a given timezone — they use most of their reserved
capacity. But at 3 AM, they might use only 20% of their reserved machines while
still holding reservations on 100% "just in case" traffic spikes. Without batch jobs,
those machines sit idle at 3 AM.

Batch jobs, by contrast, don't care what time it is. A MapReduce job processing last
night's ad click logs is perfectly happy running at 3 AM when the serving machines
are idle. Borg exploits this complementarity: serving jobs hold the long-term
reservations, and batch jobs fill in the gaps when serving load is low. This is
exactly why Google could achieve 60-70% overall utilization — the batch jobs mop
up the slack that serving jobs leave behind.

**Q3: What does "treating the cluster as a single computer" actually mean technically?**

It means the API you interact with is at the level of the cluster, not individual
machines. When you write a traditional program for a single computer, you say "run
this function." You don't say "run this function on CPU core 3 of socket 2." The OS
handles placement. Borg brings that same abstraction up to the datacenter level.
You say "run this job with 100 tasks, each needing 2 CPUs and 4 GB RAM." Borg is
the OS — it handles which physical machines those tasks land on.

Technically, this requires Borg to maintain a global view of all resources in the
cluster, a scheduling algorithm that maps tasks to machines, and agents on every
machine that execute Borg's decisions. The programming model needs to be location-
agnostic — your code cannot assume it's on machine X, because Borg may move it to
machine Y if X fails.

---

## Part 2: The Programming Model — Jobs, Tasks, Allocs, Priority, and Quota

### 2.1 Jobs

A **Job** in Borg is a collection of identical tasks. Think of a job like a job listing:
"We need 100 copies of this web server binary, each with 2 CPUs and 4 GB RAM."

Every task in a job runs the same binary with the same configuration. They are
interchangeable replicas. If you are running the Gmail frontend, you might have
a job with 500 tasks — 500 identical web servers all handling Gmail traffic.

Jobs have properties:
- **Name**: human-readable (e.g., "gmail-frontend-prod")
- **Owner**: which team owns this job
- **Number of tasks**: how many replicas
- **Resource requirements per task**: CPUs, RAM, disk
- **Priority**: determines preemption behavior
- **Constraints**: "only run on machines with SSDs" or "spread tasks across racks"

### 2.2 Tasks

A **Task** is a single instance of a job — one running process on one machine. A job
with 100 tasks has 100 tasks, each on a (potentially different) machine.

Each task maps roughly to what Kubernetes calls a **Pod**. It is the unit of
scheduling — the smallest thing Borg places on a machine.

Tasks have a lifecycle:
```
PENDING → RUNNING → SUCCEEDED/FAILED/KILLED
```

- **PENDING**: Borg knows about the task but hasn't placed it on a machine yet
- **RUNNING**: task is placed and actively running
- **SUCCEEDED**: task exited with code 0 (batch job finished successfully)
- **FAILED**: task crashed or exited with nonzero code
- **KILLED**: task was explicitly stopped or preempted by a higher-priority task

### 2.3 Allocs

An **Alloc** (short for "allocation") is a reserved set of resources on one machine
that can be shared by multiple tasks. Think of an Alloc as renting a studio apartment:
you pay for the space, and multiple people can live in it.

Why allocs? Suppose you have a web server task that needs 2 CPUs. You also have a
logging agent that ships its logs to a central system, and it needs 0.1 CPUs. Both
tasks should run on the same machine because the logging agent is specifically
shipping that web server's logs. An Alloc lets you say "reserve 2.1 CPUs on machine X
for this web server + its logging sidecar."

This is exactly the origin of the Kubernetes **Pod** concept: a Pod is multiple
containers sharing the same network namespace and potentially the same volumes —
directly derived from Borg's Alloc idea.

### 2.4 Priority — The 0-450 Scale

Priority determines who gets resources when there isn't enough for everyone. Borg
uses a numeric scale from 0 to 450, grouped into named tiers:

```
450  ┌─────────────────────────────────────────────┐
     │  MONITORING TIER                            │
     │  (Borg's own health monitoring)             │
400  ├─────────────────────────────────────────────┤
     │  PRODUCTION TIER                            │
     │  (Gmail, Search, Ads, Maps)                 │
     │  These tasks CANNOT be preempted except     │
     │  by monitoring tasks.                       │
200  ├─────────────────────────────────────────────┤
     │  BATCH TIER                                 │
     │  (MapReduce, data pipelines)                │
     │  Can be preempted by production tasks.      │
     │  Preemption is expected and handled.        │
 0   ├─────────────────────────────────────────────┤
     │  BEST-EFFORT / FREE TIER                    │
     │  (experimental, dev workloads)              │
     │  Can be preempted by anyone.                │
     └─────────────────────────────────────────────┘
```

**Preemption** means: if machine X is full and a high-priority task needs to go there,
Borg kills a lower-priority task on machine X to make room. The killed task is
rescheduled elsewhere. This is expected behavior — batch jobs are written to be
restartable. Production tasks are not killed except in extreme circumstances.

This maps directly to Kubernetes `PriorityClass`.

### 2.5 Quota

**Quota** is a budget system. Each team has a quota — a maximum amount of resources
they are allowed to use. Think of quota as a credit card limit. You can have 100 tasks
running, but if you hit your CPU quota, you can't start more tasks until you either
reduce usage or get more quota approved.

Quota is bought in advance (like cloud billing commitments) and enforced at admission
time — before a task is even scheduled, Borg checks whether the submitting team has
enough quota. If not, the task is rejected immediately.

This prevents any single team from accidentally (or intentionally) monopolizing the
entire cluster.

### 2.6 BCL — The Borg Configuration Language

Engineers specify jobs using a configuration language called BCL (Borg Configuration
Language). Think of BCL as the grandfather of Kubernetes YAML:

```
# Example BCL config (simplified/illustrative)
job gmail_frontend {
  owner       = "gmail-team"
  num_tasks   = 500
  priority    = 300  # production tier

  task {
    binary    = "/usr/local/bin/gmail-frontend"
    args      = "--port=8080 --config=/etc/gmail/config.pb"
    cpu       = 2.0        # 2 CPUs
    memory    = 4096 MB    # 4 GB RAM
    disk      = 10 GB
  }

  constraint {
    attribute = "machine_type"
    value     = "highcpu"
  }
}
```

BCL was an internal Google language with full programming constructs — variables,
loops, conditionals. This made configs complex and hard to audit. Kubernetes YAML
is simpler (but more verbose) and this was a deliberate design improvement.

---

### Brainstorming: Part 2 Questions

**Q1: Why does Borg use a numeric priority scale (0-450) instead of just named tiers?**

Named tiers like "production" and "batch" seem simpler, but they break down in
practice when you need ordering within a tier. Suppose you have two production jobs —
Gmail and Google Docs. If both need the last few CPUs on a machine, which one wins?
With named tiers, you cannot express this. With a numeric scale, Gmail can be priority
320 and Docs can be priority 310, so Gmail always wins ties. The numeric scale gives
fine-grained control within tiers.

There is also an important safety property: tasks in the production tier cannot
preempt each other (Borg enforces that production tasks only preempt tasks in lower
tiers). This prevents a runaway production job from cascading — it cannot take
resources from other critical production services, only from batch work. The
monitoring tier (350+) is reserved exclusively for Borg's own health-monitoring
infrastructure, ensuring it always has resources to tell you whether things are broken.

**Q2: How does the Alloc concept lead directly to the Kubernetes Pod?**

The Alloc was Borg's solution to a very concrete operational problem: sidecar
containers need to co-locate with the main container. A logging agent needs to run
on the same machine as the app it is logging. A Prometheus metric scraper needs to
run on the same machine as the app it is scraping. Before allocs, these sidecars were
scheduled independently and might end up on different machines — making them useless.

An Alloc says "reserve resources on one specific machine and let multiple tasks share
that reservation." Kubernetes formalized this as the Pod: a group of containers that
share the same network namespace (same IP address and localhost) and can share storage
volumes. The Pod boundary is exactly the Alloc boundary. The key insight the Borg
paper credits is that treating co-located containers as a unit rather than independent
tasks dramatically simplifies service mesh, logging, and monitoring architectures.

**Q3: What happens to a batch task that gets preempted — does all its work get lost?**

In the original Borg era, yes — many batch tasks lost partial work when preempted.
This is why Google's MapReduce was designed from the beginning to be fault-tolerant:
each map task writes its intermediate output to local disk, and if the task is killed,
the MapReduce framework reschedules just that map task on another machine without
re-running the whole job.

Modern batch frameworks handle preemption via checkpointing: the task periodically
saves its progress to distributed storage (GFS/Colossus), and when rescheduled, it
resumes from the last checkpoint rather than from scratch. This is the "graceful
preemption" model — Borg sends the task a SIGTERM signal, gives it a few seconds to
checkpoint, then sends SIGKILL. Well-written batch tasks use that window to save
state. This is why writing batch jobs to be preemption-aware is a standard engineering
practice at companies that use cluster managers.

---

## Part 3: BorgMaster Architecture — The Brain of the Cluster

### 3.1 Overview: What BorgMaster Does

BorgMaster is the central control plane of Borg. It is the equivalent of Kubernetes'
control plane (kube-apiserver + etcd + controller-manager + scheduler combined).
Everything goes through BorgMaster:

- Engineers submit new jobs to BorgMaster via the Borg CLI or API
- BorgMaster makes scheduling decisions (which task goes to which machine)
- BorgMaster receives status reports from every machine in the cluster
- BorgMaster takes corrective actions when things go wrong

### 3.2 The 5-Replica Paxos Architecture

BorgMaster does not run as a single server. It runs as 5 replicas using Paxos
consensus to elect a leader and replicate state.

Here is why this matters: if BorgMaster ran as a single server and that server died,
the entire cluster would stop making progress. No new tasks could be scheduled.
Failed tasks would not be rescheduled. The cluster would be a zombie — machines
still running existing tasks, but nothing new happening and nothing broken getting
fixed.

With 5 Paxos replicas, up to 2 replicas can fail and the cluster keeps working (Paxos
requires a majority — 3 out of 5 — to make decisions). Failover takes about 10 seconds:
the 5 replicas detect that the leader is gone, hold a Paxos election, and a new
leader takes over.

```
BorgMaster Architecture (5-Replica Paxos)
==========================================

    Engineers / Tools                 Borglets (on each machine)
          │                                    │
          ▼                                    │
  ┌──────────────────────────────────────────────────────────┐
  │                   BorgMaster Cluster                     │
  │                                                          │
  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    │
  │  │Replica 1│  │Replica 2│  │Replica 3│  │Replica 4│    │
  │  │(LEADER) │  │(follower│  │(follower│  │(follower│    │
  │  │         │◄─┤         ├──►         ├──►         │    │
  │  │All API  │  │Paxos    │  │Paxos    │  │Paxos    │    │
  │  │calls go │  │log sync │  │log sync │  │log sync │    │
  │  │here     │  │         │  │         │  │         │    │
  │  └────┬────┘  └─────────┘  └─────────┘  └─────────┘    │
  │       │                                     ▲            │
  │       │        ┌─────────┐                  │            │
  │       │        │Replica 5│                  │            │
  │       │        │(follower│◄─────────────────┘            │
  │       │        │         │                               │
  │       │        └─────────┘                               │
  │       │                                                  │
  │  ┌────▼───────────────────────────────────────────┐      │
  │  │              In-Memory State                   │      │
  │  │  • All machine states and their resources      │      │
  │  │  • All task states (pending/running/failed)    │      │
  │  │  • All job specifications (desired state)      │      │
  │  │  • Scheduler queue                             │      │
  │  └───────────────────────┬────────────────────────┘      │
  │                          │                               │
  │  ┌───────────────────────▼────────────────────────┐      │
  │  │              Paxos Log + Checkpoints           │      │
  │  │  (persistent on-disk; survives restarts)       │      │
  │  └────────────────────────────────────────────────┘      │
  └──────────────────────────────────────────────────────────┘
                             │
                             │  Borglet polls every few seconds
                             ▼
          ┌──────────────────────────────────────┐
          │  Machine 1   Machine 2   Machine 3   │
          │  [Borglet]   [Borglet]   [Borglet]   │
          │  [Task A]    [Task C]    [Task A]    │
          │  [Task B]    [Task D]    [Task E]    │
          └──────────────────────────────────────┘
```

### 3.3 In-Memory State for Speed

A critical design decision: BorgMaster keeps ALL cluster state in memory.
This is unusual — most databases persist data to disk and read it back on queries.
BorgMaster keeps everything in RAM:

- Current state of every machine (CPUs free, RAM free, what tasks are running)
- Desired state of every job (how many tasks, their resource requirements)
- Pending scheduling decisions
- Health check results

Why? Because making scheduling decisions requires reading from this state constantly.
If state were on disk, scheduling would be bottlenecked by disk I/O. With in-memory
state, BorgMaster can evaluate thousands of scheduling decisions per second.

But in-memory state is lost if the process crashes. This is where the Paxos log
comes in: every state change is written to the Paxos log (on disk, replicated to all
5 replicas) before being applied to in-memory state. If BorgMaster crashes and
restarts, it replays the Paxos log to reconstruct in-memory state. Additionally,
periodic **checkpoint files** are written to disk — a snapshot of the entire in-memory
state — so that log replay starts from a recent checkpoint rather than the beginning
of time.

### 3.4 Borglets — The Agents on Every Machine

Every machine in a Borg cell runs a **Borglet** — a local agent that:

1. Receives task assignments from BorgMaster
2. Starts and stops containers on that machine
3. Monitors resource usage (CPU, RAM, disk) of every task
4. Reports machine and task state back to BorgMaster
5. Enforces resource limits (kills tasks that exceed RAM limits)

Borglet maps directly to the Kubernetes **kubelet**.

Importantly, BorgMaster does NOT push state to Borglets — Borglets **poll**
BorgMaster every few seconds. This is pull-based communication. This design choice
makes the system more resilient: if BorgMaster is temporarily unavailable, Borglets
keep running existing tasks (they don't stop everything because they can't reach
the master). They just can't get new assignments or report state until connectivity
is restored.

### 3.5 The Fauxmaster — Testing Your Scheduler

BorgMaster includes a component called **Fauxmaster** — a high-fidelity simulator
of the entire cluster. You feed Fauxmaster a checkpoint file (a snapshot of real
cluster state) and it simulates scheduling decisions without actually affecting real
machines.

Fauxmaster is used for:
- **Capacity planning**: "If I add 1,000 machines, how many more tasks can I fit?"
- **Scheduler algorithm development**: "If I change the scoring function, does
  utilization improve or degrade?"
- **Debugging**: "Why did Borg not schedule my task? Let me simulate it in Fauxmaster
  to see which constraints are blocking it."

This idea — a simulator that can replay real cluster state — was genuinely novel in
2015 and is a great example of operational tooling that makes a complex system
manageable. Kubernetes does not have a direct equivalent (though tools like
`kube-scheduler-simulator` have been built by the community).

---

### Brainstorming: Part 3 Questions

**Q1: Why does BorgMaster use 5 replicas specifically? Why not 3 or 7?**

The number of replicas in a Paxos system determines the fault tolerance: with N
replicas, you can tolerate (N-1)/2 failures. With 3 replicas, you tolerate 1 failure.
With 5 replicas, you tolerate 2 failures. With 7 replicas, you tolerate 3 failures.

Five is the sweet spot for Google's operational requirements. One failure at a time
is almost certain to happen — a machine can fail or be taken down for maintenance
at any moment. Two simultaneous failures is possible but unlikely. Three simultaneous
failures is rare enough that tolerating 2 is sufficient. Seven replicas would tolerate
3 failures but at the cost of extra coordination overhead — every write must be
acknowledged by 4 replicas instead of 3, adding latency to every state change.
Five replicas gives a good balance: tolerates realistic failure scenarios without
excessive overhead. It is also the standard choice for Paxos deployments at Google
(Chubby, the lock service, also uses 5 replicas).

**Q2: What happens to running tasks when BorgMaster fails over to a new leader?**

Running tasks are completely unaffected by a BorgMaster failover. Remember: Borglets
are running tasks locally on each machine. The task processes don't know or care
whether BorgMaster is available. They are just Linux processes running in containers.
They keep running.

What stops during failover is the ability to make NEW scheduling decisions. For roughly
10 seconds while Paxos elects a new leader, no new tasks can be scheduled and failed
tasks cannot be rescheduled. In practice, 10 seconds is acceptable: production tasks
are long-running and don't fail that frequently, and batch tasks can wait a few
seconds. After the new leader takes over, it reads the Paxos log and checkpoint to
reconstruct state, then resumes scheduling normally. This design — separating the
control plane from the data plane — is a fundamental distributed systems pattern.
The data plane (actual task execution) continues even when the control plane is unavailable.

**Q3: Why does Borglet use pull (polling) instead of push (event-driven) communication?**

Push-based communication seems more efficient — why wait for Borglets to poll when
BorgMaster could just push updates immediately? But push has a fatal flaw at scale:
BorgMaster has to maintain persistent connections to tens of thousands of Borglets.
If BorgMaster restarts, it has to re-establish tens of thousands of connections
simultaneously. This creates a massive thundering herd: all Borglets trying to
reconnect at the same instant can overwhelm BorgMaster right when it is most vulnerable
(just after a failover).

Pull-based polling naturally load-distributes the reconnection. Borglets poll on
independent schedules — they don't all hit BorgMaster at the same microsecond. When
BorgMaster restarts, Borglets gradually reconnect over many seconds. The cost of
pull is slightly higher latency between when BorgMaster makes a decision and when
the Borglet learns about it — but this latency is just a few seconds, which is
acceptable for a cluster scheduler. Kubernetes kubelet uses the same pull-based model.

---

## Part 4: Two-Phase Scheduling — Finding the Right Machine

### 4.1 The Scheduling Problem

When a new task needs to be placed, Borg's scheduler has to answer one question:
which machine should run this task? In a cluster with tens of thousands of machines,
this is not trivial. You need to:

1. Filter out machines that CAN'T run this task
2. Among the remaining machines, pick the BEST one

Borg does this in two phases.

### 4.2 Phase 1: Feasibility Filtering

In the first phase, the scheduler scans every machine in the cell and discards any
machine that CANNOT run the task. A machine is infeasible if:

**Not enough free resources**: The task needs 2 CPUs and 4 GB RAM. If the machine
only has 1.5 CPUs free, it fails this check. (But wait — Borg can preempt lower-
priority tasks to make room. So "free resources" includes "resources I could free
by killing batch tasks." If the machine has 1 CPU free and 1 CPU tied up in a
batch job that could be preempted, it might still be feasible for a production task.)

**Hard constraint violations**: The task's configuration specifies "only run on
machines in datacenter us-east-1" or "only run on machines with GPUs." If the machine
doesn't satisfy these constraints, it's infeasible.

**Forbidden list**: The task says "do NOT run on machines X, Y, Z." (Used to spread
tasks across racks for fault isolation — you don't want all 100 replicas on the same
rack that shares a power circuit.)

**Maintenance/exclusion**: The machine is being taken down for hardware maintenance.

After Phase 1, we have a list of feasible machines. For a typical task in a large
cell, this might still be thousands of machines. We need to pick the best one.

### 4.3 Phase 2: Scoring

In the second phase, the scheduler assigns a score to each feasible machine and
picks the highest-scoring one. The score is a weighted combination of several factors:

**Bin-packing score**: How well does this task "fit" on this machine? We want to
maximize machine utilization by packing tasks tightly (we'll cover this in detail
in Part 8). A machine that is mostly full but has exactly the right amount of space
left for this task gets a high bin-packing score.

**Data locality**: Is the input data for this task stored locally on this machine
or a nearby machine? A batch job that reads 1 TB of data prefers a machine where
that data is stored locally (avoiding 1 TB of network transfer). BorgMaster knows
where data lives via integration with GFS (Google File System).

**Task spreading**: For reliability, we want a job's tasks spread across different
racks, power circuits, and availability zones. If tasks A1 through A50 are already
on rack 7, we probably want A51 on a different rack, so a rack failure doesn't take
out more than half the job. The scoring function penalizes machines that would
concentrate too many tasks of the same job in one failure domain.

**Preemption cost**: If the only feasible machines require preempting batch tasks,
we prefer the machine where preemption costs the least — measured as amount of
work that would be lost.

```
Two-Phase Scheduling Flow
==========================

New Task Arrives
     │
     ▼
┌──────────────────────────────────────────────────────┐
│  PHASE 1: FEASIBILITY FILTERING                       │
│                                                      │
│  For each machine M in the cell:                     │
│  ┌────────────────────────────────────┐              │
│  │ Check 1: M has enough free CPUs?  │              │
│  │ Check 2: M has enough free RAM?   │              │
│  │ Check 3: M satisfies constraints? │              │
│  │ Check 4: M not on forbidden list? │              │
│  │ Check 5: M not in maintenance?    │              │
│  │ Check 6: Can preemption help?     │              │
│  └──────────────┬─────────────────────┘              │
│                 │                                    │
│      YES → FEASIBLE SET                              │
│      NO  → Discard machine                           │
└──────────────────────────────────────────────────────┘
     │
     │  Feasible Set: [M3, M7, M12, M15, M42, ...]
     ▼
┌──────────────────────────────────────────────────────┐
│  PHASE 2: SCORING                                     │
│                                                      │
│  For each machine in Feasible Set:                   │
│                                                      │
│  Score(M) = w1 * BinPackingScore(M)                  │
│           + w2 * DataLocalityScore(M)                │
│           + w3 * SpreadScore(M)                      │
│           - w4 * PreemptionCost(M)                   │
│                                                      │
│  M3:  0.85  ← highest score → WINNER                │
│  M7:  0.72                                          │
│  M12: 0.68                                          │
│  M15: 0.61                                          │
│  M42: 0.54                                          │
└──────────────────────────────────────────────────────┘
     │
     │  Selected machine: M3
     ▼
┌──────────────────────────────────────────────────────┐
│  BINDING                                             │
│  • Record: "Task T47 → Machine M3" in Paxos log     │
│  • If preemption needed: send kill signal to victims │
│  • Borglet on M3 polls BorgMaster, gets assignment  │
│  • Borglet starts the task container on M3           │
└──────────────────────────────────────────────────────┘
```

### 4.4 Randomized Subset Scoring (Scalability Optimization)

In a cell with 50,000 machines, scoring every feasible machine would be expensive.
Borg uses a practical optimization: after feasibility filtering, it scores a random
subset of the feasible machines (a few hundred) rather than all of them. This makes
scheduling fast while still finding a good (if not always optimal) machine.

This is a classic systems tradeoff: perfect is the enemy of fast. A near-optimal
placement decided in 1 millisecond is far more valuable than a globally-optimal
placement decided in 5 seconds (during which the task is waiting and the queue is
backing up).

### 4.5 The Intern-to-Staff Progression on Scheduling

| Level | How They Explain Borg Scheduling |
|-------|----------------------------------|
| **Intern** | "Borg picks a machine with enough CPU and RAM" |
| **Junior** | "Borg filters machines by resource fit and constraints, then picks the best one" |
| **Mid** | "Two-phase scheduling: feasibility filters infeasible machines, scoring ranks feasible ones using bin-packing, data locality, and spreading criteria" |
| **Senior (L5)** | All of the above plus: "preemption expands the feasible set for production tasks; Borg uses a random subset of feasible machines for scoring to keep latency low" |
| **Staff (L6)** | All of the above plus: "the scorer weights can be tuned per-workload type; Borg tracks 'utilization under reclamation' — resources reclaimed from tasks using less than they requested; Fauxmaster lets you test scoring changes against real cluster traces before production deployment" |

---

### Brainstorming: Part 4 Questions

**Q1: How does Borg handle the case where no machine is feasible for a new task?**

When no machine can run the task, Borg puts the task in a pending queue and retries
periodically. This is the correct behavior — not an error. It means the cluster is
at capacity for that resource type at that priority level. The task will eventually
be placed when machines free up (running tasks finish or are preempted for higher
priority work elsewhere, freeing up capacity).

In practice, when a cluster is consistently turning away tasks, it triggers a capacity
alarm. The infrastructure team either acquires more machines or asks teams to reduce
their resource requests. Teams can also look at their utilization: if a team reserved
2 CPUs per task but is only using 0.5 CPUs on average, Borg will flag this and suggest
reducing the reservation. This is the quota system working as intended — tasks that
are over-reserving are wasting capacity that other tasks could use.

**Q2: What makes bin-packing the right scoring objective — wouldn't spreading tasks
evenly across machines be better?**

Even spreading (giving every machine roughly the same load) sounds fair but is
actually terrible for utilization. If you spread 100 tasks across 100 machines,
each machine is at 50% utilization. Now you need a machine with 60% free to run
a new large task — but no machine has 60% free, they all have 50%. You're stuck
even though the cluster is only half full.

Bin-packing avoids this by keeping some machines full and others empty. A new large
task can always land on an empty machine. The tradeoff: bin-packing concentrates
failure risk. If a machine fails and it's packed full of tasks, many tasks get
rescheduled at once. Borg addresses this with the spreading score in the scoring
function — it penalizes placing tasks that would create correlated failure risk
(many tasks of the same job on the same rack). So in practice Borg does both:
pack tasks tightly for utilization, but not so tightly that a single rack failure
takes out a whole service.

**Q3: In a two-phase scheduling system, how do you handle new tasks arriving faster
than the scheduler can process them?**

The scheduler maintains a queue of pending tasks. Tasks are pulled from the queue
and processed one by one (or in small batches). If tasks arrive faster than the
scheduler processes them, the queue grows. To scale, Borg's scheduler runs as a
separate goroutine in BorgMaster and does the two phases concurrently with BorgMaster
handling API calls from Borglets and engineers.

For extreme scale, Borg uses an "optimistic concurrency" trick: multiple scheduling
threads can run in parallel, each working with a snapshot of cluster state. Two threads
might both decide to place tasks on the same machine. When they try to commit, one
wins and the other must retry with fresh state. This is similar to how database
optimistic locking works. It allows throughput to scale with scheduler threads without
requiring global locking during the expensive scoring phase.

---

## Part 5: Desired State and the Reconciliation Loop — Self-Healing by Design

### 5.1 The Most Important Concept in This Chapter

If you only remember one thing from this chapter for your interviews, let it be this:

**Borg uses "desired state" + "reconciliation loop" instead of "imperative commands."**

This single design decision is what makes the entire system self-healing. It is the
same idea that makes Kubernetes self-healing. It is the concept you should reach for
whenever an interviewer asks "how do you handle failures in a distributed system?"

### 5.2 Imperative vs. Declarative — The Analogy

**Imperative (bad, old way):**
You tell the system exactly what actions to take.
- "Start task on machine 12"
- "If machine 12 fails, start task on machine 47"
- "If machine 47 also fails, start task on machine 8"
- "Keep checking every minute..."

Problems: You have to enumerate every possible failure. You have to keep track of
state yourself. You have to write code for every possible transition. It's like
driving a car by explicitly controlling every muscle: "left quadricep, contract 30%;
right quadricep, contract 15%; left shoulder..."

**Declarative (good, Borg way):**
You tell the system what the end state should look like.
- "I want 100 replicas of this task running at all times."

Then you walk away. Borg figures out HOW to achieve that state and keeps it achieved
indefinitely. This is like telling a thermostat "I want the room at 72°F." The
thermostat figures out whether to run heating or cooling, for how long, adjusting
to external temperature changes — without you specifying any of that.

### 5.3 The Reconciliation Loop in Detail

BorgMaster runs a continuous reconciliation loop:

```
Borg Reconciliation Loop (Runs Continuously, Every Few Seconds)
================================================================

        ┌─────────────────────────────────────────┐
        │         OBSERVE                         │
        │  Poll all Borglets for current state:   │
        │  • Which tasks are actually running?    │
        │  • What resources are consumed?         │
        │  • Any task failures or OOM kills?      │
        └────────────────┬────────────────────────┘
                         │
                         ▼
        ┌─────────────────────────────────────────┐
        │         DIFF                            │
        │  Compare actual state vs desired state: │
        │                                         │
        │  Desired: 100 tasks of job X running    │
        │  Actual:  97 tasks of job X running     │
        │  Diff:    3 tasks need to be started    │
        │                                         │
        │  Desired: task T47 on machine M3        │
        │  Actual:  machine M3 is DOWN            │
        │  Diff:    T47 needs to be rescheduled   │
        └────────────────┬────────────────────────┘
                         │
                         ▼
        ┌─────────────────────────────────────────┐
        │         ACT                             │
        │  Take actions to close the gap:         │
        │  • Schedule 3 new tasks                 │
        │  • Reschedule T47 to a healthy machine  │
        │  • Kill tasks that shouldn't be running │
        └────────────────┬────────────────────────┘
                         │
                         └──────────────────────────┐
                                                    │
                         ┌──────────────────────────┘
                         │ (repeat forever)
                         ▼
                    [OBSERVE again]
```

Notice what is beautiful about this design: **there is no special failure-handling
code.** The reconciliation loop handles failures automatically because the loop
doesn't know or care WHY actual state differs from desired state. Whether the task
failed because of a software crash, a machine failure, or a network partition — the
diff step sees "actual != desired" and the act step takes corrective action.

This is a profound insight that Borg engineers discovered through operational
experience: the right way to build a self-healing system is not to enumerate failure
scenarios and handle each one. It is to define desired state and continuously reconcile
toward it.

### 5.4 The Real Incident: The 2011 Datacenter Reconciliation Story

In 2011, a Google datacenter in the US experienced a power distribution failure.
Approximately 1,800 machines went offline simultaneously — their Borglets stopped
responding.

Here is what happened from BorgMaster's perspective:

- **T+0s**: BorgMaster starts noticing that ~1,800 machines are not responding to polls.
- **T+30s**: BorgMaster marks the machines as dead (after a grace period to
  distinguish a network hiccup from a true failure).
- **T+30s**: The reconciliation loop fires. Diff shows ~15,000 tasks that were running
  on those machines are now absent. Desired state says those tasks should be running.
- **T+30s onward**: BorgMaster begins scheduling those 15,000 tasks onto healthy
  machines in other parts of the datacenter. It processes scheduling in priority order —
  production tasks first, then batch.
- **T+3 minutes**: All production tasks (Gmail, Search replicas) have been rescheduled
  and are back online. Engineers observing the production dashboards see a brief dip
  but no outage — the services had enough redundancy in other datacenters that the
  affected datacenter's outage was partially absorbed.
- **T+10 minutes**: Batch tasks are rescheduled. Some batch jobs that were in the
  middle of processing checkpoint their state and resume from their last checkpoint
  on new machines.

The key: **no human took any action to cause those 15,000 tasks to be rescheduled.
Borg did it automatically.** Engineers were in the war room watching dashboards, but
they did not type a single command. The reconciliation loop just... worked.

### 5.5 The Intern-to-Staff Progression on Desired State

| Level | What They Say |
|-------|---------------|
| **Intern** | "Kubernetes restarts crashed containers automatically" |
| **Junior** | "Kubernetes uses a control loop to detect and fix drift between desired and actual state" |
| **Mid** | "The reconciliation loop (observe-diff-act) is the core self-healing mechanism. Desired state is specified declaratively; Borg continuously reconciles actual state toward it, regardless of why they diverged." |
| **Senior (L5)** | All of the above plus: "The loop handles not just task failures but machine failures, network partitions, and even accidental manual interventions — all as the same 'actual != desired' condition. Rate limiting prevents reconciliation from causing cascades." |
| **Staff (L6)** | All of the above plus: "The reconciliation model has failure modes too — if desired state itself is wrong (misconfigured), the loop will relentlessly drive the cluster into that wrong state. This is why configuration validation, dry-run modes (Fauxmaster), and canary deployments are critical complements to the reconciliation model. The loop is powerful precisely because it doesn't question the desired state — so desired state must be correct." |

---

### Brainstorming: Part 5 Questions

**Q1: Can the reconciliation loop itself cause problems? What if it acts too aggressively?**

Yes, this is a real risk called a "reconciliation storm." Imagine 10,000 tasks fail
simultaneously (e.g., due to a software bug in a new deployment). The reconciliation
loop sees 10,000 tasks to reschedule and immediately tries to start them all. This
can overwhelm the cluster: all 10,000 tasks are competing for the same machines,
all starting simultaneously, all pulling their binary from the same artifact storage.
This thundering herd can make things worse.

Borg addresses this with rate limiting on the act phase: the number of new scheduling
actions per second is capped. Priority ordering ensures production tasks get through
first. Exponential backoff is applied to tasks that fail repeatedly — if a task fails
5 times in a row, there is probably a bug in the task, and rescheduling it rapidly
does not help; it just wastes resources. These rate limits and backoffs are essential
operational knobs that make the reconciliation loop practical at scale.

**Q2: How does the reconciliation loop handle the case where desired state is impossible
to achieve?**

If desired state cannot be achieved — for example, you want 10,000 tasks but the
cluster only has capacity for 8,000 — the loop does its best (schedules 8,000 tasks)
and leaves 2,000 tasks in the PENDING state. It continues retrying the pending tasks
every reconciliation cycle, but they won't be scheduled until capacity is available.

BorgMaster exposes metrics and alerts for "pending tasks" — a dashboard that shows
how many tasks are waiting to be placed and why they are infeasible. This is how
operators know the cluster is at capacity and needs more machines. The loop never
gives up on pending tasks — it keeps trying indefinitely. This is by design: a task
that is infeasible today (cluster is at capacity) might become feasible tomorrow
when other jobs finish.

**Q3: How does the reconciliation model compare to the traditional "orchestration scripts"
approach to managing distributed systems?**

Traditional orchestration scripts (runbooks, Ansible playbooks, Chef recipes) are
imperative: they take a sequence of steps and assume the system starts in a known
state. "Step 1: SSH to machine X and run this command." The problem is that real
systems are rarely in the state you assumed. If step 3 of your 10-step playbook
fails halfway through, the system is now in an intermediate state that no script
handles. Human operators must diagnose and recover manually.

The reconciliation model eliminates this class of problem entirely. Because desired
state is always the target and the loop always drives toward it, there is no concept
of "the system is in an intermediate state." At any point in time, the system is
simply "closer to or farther from desired state." The loop will find its way from
wherever the system currently is. The only requirement is that desired state be
reachable from any actual state — which is a much weaker condition than "the system
must be in exactly this state before we start."

---

## Part 6: Resource Management — Compressible vs. Non-Compressible Resources

### 6.1 The Resource Taxonomy

Every task in Borg requests and uses resources. Borg tracks several resource types,
but they divide into two fundamentally different categories with different enforcement
semantics:

**Compressible Resources** (primarily CPU):
- Can be throttled without killing the task
- If a task is using more CPU than it requested, Borg simply slows it down
- The task keeps running — it just runs slower
- Analogy: a car speed limiter. The car still works; it just can't go over 70 mph.

**Non-Compressible Resources** (primarily RAM, also disk):
- Cannot be throttled — a process either has its memory or it doesn't
- If a task is using more RAM than its limit, the Linux OOM (Out of Memory) killer
  terminates the task immediately
- There is no "throttle RAM" — you can't tell a process "use your memory more slowly"
- Analogy: a parking space. A car either fits in the space or it doesn't. You can't
  "throttle" how much space the car uses.

### 6.2 Resource Request vs. Limit vs. Actual

Borg tracks three distinct resource values for each task:

```
Resource Accounting in Borg
=============================

  ┌──────────────────────────────────────────────────────────┐
  │                     CPU (Compressible)                   │
  │                                                          │
  │  LIMIT    ████████████████████████████████  4.0 CPUs     │
  │           ← scheduler sees this as "reserved" →          │
  │                                                          │
  │  REQUEST  ████████████████████  2.0 CPUs                 │
  │           ← what you asked for (for scheduling) →        │
  │                                                          │
  │  ACTUAL   ████████████  1.2 CPUs                         │
  │           ← what you're actually using right now →       │
  │                                                          │
  │  RECLAIMED CAPACITY: 2.0 - 1.2 = 0.8 CPUs               │
  │  ← Borg can lend this to batch jobs →                    │
  └──────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────┐
  │                     RAM (Non-Compressible)               │
  │                                                          │
  │  LIMIT    ████████████████████████████████  8 GB         │
  │           ← task is KILLED if actual exceeds this →      │
  │                                                          │
  │  REQUEST  ████████████████████  4 GB                     │
  │           ← what you asked for (for scheduling) →        │
  │                                                          │
  │  ACTUAL   ████████████████  3.5 GB                       │
  │           ← what you're actually using right now →       │
  │                                                          │
  │  RECLAIMED CAPACITY: 4.0 - 3.5 = 0.5 GB                 │
  │  ← Borg can lend this to batch jobs →                    │
  └──────────────────────────────────────────────────────────┘
```

**Request**: The amount you say you need. Used for scheduling decisions.
**Limit**: The maximum you're allowed to use. Enforced hard.
**Actual**: How much you're really using right now.

The gap between Request and Actual is **reclaimed capacity** — resources that are
reserved but not being used. Borg can safely lend these to low-priority batch tasks.
If the production task suddenly needs more resources (traffic spike), Borg takes
back the reclaimed capacity by throttling or killing the batch tasks that were using it.

### 6.3 Utilization Statistics from the 2015 Paper

The Borg paper reported real utilization numbers from Google's production cells.
These numbers are frequently cited in system design discussions:

- **With naive reservation (no Borg-style reclamation)**: cells would be at roughly
  40-50% utilization if every task always used what it reserved.
- **With reclamation and mixed workloads**: cells achieved 60-70%+ utilization.
- **The key driver**: production tasks typically use only 40-60% of what they reserve
  (they over-provision for traffic spikes). This slack is reclaimed and given to batch
  tasks, dramatically improving overall utilization.

The paper also showed that CPU is typically over-reserved by a factor of 2-3x, while
RAM is over-reserved by a factor of 1.5-2x. This has a practical implication:
under-requesting RAM is more dangerous than under-requesting CPU. If you under-request
CPU, you get throttled (your task runs slow). If you under-request RAM, you get OOM
killed (your task dies). Engineers over-provision RAM as a safety margin, creating
the reclamation opportunity Borg exploits.

### 6.4 The Intern-to-Staff Progression on Resource Management

| Level | Understanding |
|-------|---------------|
| **Intern** | "You specify CPU and memory for each container" |
| **Junior** | "CPU and memory have different limits; going over memory causes the container to be killed" |
| **Mid** | "CPU is compressible (throttled if over limit); RAM is non-compressible (OOM killed). Request is used for scheduling; limit is enforced at runtime. The gap between request and actual is potential reclaimed capacity." |
| **Senior (L5)** | All of the above plus: "Borg reclaims unused reserved capacity and lends it to batch jobs. Production tasks can reclaim their capacity back on demand by preempting the batch jobs using it. This is the mechanism that takes utilization from 40% to 60-70%." |
| **Staff (L6)** | All of the above plus: "The reclamation model creates second-order effects. Batch jobs depend on reclaimed capacity, so their runtime is variable — they run fast when production is idle, slow when production is busy. This makes batch job SLAs hard to predict. Google addressed this with 'autopilot' — a system that observes actual usage and automatically recommends adjusted resource requests, closing the over-reservation gap without requiring manual tuning." |

---

### Brainstorming: Part 6 Questions

**Q1: If a production task usually uses only 1 CPU but might spike to 4 CPUs during
peak traffic, how should it set its request and limit?**

This is the classic resource sizing dilemma. The request should reflect what you
need for scheduling — the amount Borg reserves on your behalf. The limit is your
safety ceiling.

A good practice: set request to the 90th percentile of actual usage (the level at
or below which you operate 90% of the time). Set limit to the 99.9th percentile
(what you need during the worst spikes you expect). In this example: request = 1.2
CPUs (typical peak), limit = 4 CPUs (extreme spike).

With this configuration, Borg schedules the task on a machine with 1.2 CPUs free,
and the task can burst to 4 CPUs if that capacity is available. Because CPU is
compressible, if 4 CPUs aren't available during a spike, the task is throttled to
available capacity rather than killed. Your service runs slower during extreme spikes
but does not fail. This is usually acceptable for web serving. For latency-critical
applications, you might set request = limit = 4 CPUs to guarantee never being throttled.

**Q2: How does Borglet enforce CPU throttling and RAM limits technically?**

Both mechanisms use Linux kernel features. For CPU throttling, Borglet uses Linux
**cgroups** (control groups) to set CPU quota and period: for example, "this container
can use 2 CPU-seconds out of every 10 seconds" for a 2-CPU limit. The kernel scheduler
enforces this automatically by throttling the container's processes when they exceed
the quota.

For RAM limits, Borglet sets the cgroup memory limit. When a process in the cgroup
tries to allocate more memory than the limit, the kernel's OOM killer fires and kills
the most memory-hungry process in the cgroup — which is usually the task process
itself. Borglet detects the OOM kill event, reports it to BorgMaster as a task failure,
and BorgMaster's reconciliation loop schedules the task on a new machine. This is
exactly the same mechanism Kubernetes uses — Kubernetes kubelet is essentially a
Borglet implementation using the same Linux kernel primitives.

**Q3: What is "resource reclamation" and why doesn't it work for RAM the same way
it works for CPU?**

Resource reclamation is Borg's mechanism for lending unused reserved resources to
batch jobs. If a production task reserved 4 CPUs but is only using 2, Borg can lend
those 2 CPUs to a batch task running on the same machine. If the production task
suddenly needs all 4 CPUs, Borg takes them back by CPU-throttling the batch task.
The batch task gets slower but doesn't die.

For RAM, this works differently. Borg does attempt RAM reclamation — lending unused
reserved RAM to batch tasks. But the risk is much higher. When RAM is reclaimed from
a batch task, Borg must either ask the batch task to release it voluntarily (requiring
batch task cooperation) or kill the batch task to free the RAM. There is no "slow
down" option for memory. This is why RAM reclamation is more conservative than CPU
reclamation: Borg reclaims CPU aggressively but RAM conservatively, keeping a larger
safety buffer to absorb sudden production spikes without having to OOM-kill batch tasks.

---

## Part 7: Fault Tolerance — How Borg Handles Everything Breaking

### 7.1 Taxonomy of Failures in a Large Cluster

In a cluster of tens of thousands of machines, failure is not exceptional — it is
routine. At 10,000 machines with 1% annual failure rate, you expect 100 machine
failures per year, or roughly 1 failure every 3-4 days. In reality, Borg manages
much larger clusters and the effective failure rate (including planned maintenance,
network issues, firmware updates) means something is broken every hour.

Borg handles several distinct categories of failures:

**Task failure**: A single task crashes (software bug, out-of-memory, segfault).
**Machine failure**: The physical machine dies (hardware failure, kernel panic, power).
**Network failure**: The machine is alive but BorgMaster can't reach it (network partition).
**Datacenter failure**: Multiple machines fail simultaneously (power circuit, cooling).
**BorgMaster failure**: The cluster control plane is unavailable.

### 7.2 Task-Level Fault Tolerance

When a task fails, the Borglet on that machine detects it immediately (the task process
exits). The Borglet reports the failure to BorgMaster on its next poll. BorgMaster's
reconciliation loop sees that actual task count (say, 99) is below desired (100) and
schedules a new task.

Key design decision: Borg does NOT automatically restart a task on the same machine
where it just failed. The heuristic is that if a task just crashed on machine X,
machine X might be unhealthy. Better to schedule on a different machine and only return
to X after it has been declared healthy.

**Repeated failures and backoff**: If a task fails immediately after starting, repeatedly,
Borg applies exponential backoff before rescheduling it. A task that crashes 5 times
in a row within 10 minutes is probably broken — rescheduling it every 30 seconds just
wastes resources and fills logs. Borg's backoff gives engineers time to notice the
repeated failure and fix the underlying issue.

### 7.3 Machine-Level Fault Tolerance

When a machine dies, its Borglet stops responding to BorgMaster polls. BorgMaster
waits for a grace period (to distinguish transient connectivity issues from true failure)
before declaring the machine dead. Once declared dead, all tasks on that machine are
rescheduled.

The grace period is a tricky operational parameter. Too short: you falsely declare
machines dead during network blips, causing unnecessary rescheduling churn (task
stops, restarts elsewhere, original machine recovers — now you have a task running
in two places momentarily). Too long: truly dead machines' tasks remain unrecovered
for too long. Borg's grace period is typically on the order of a few minutes.

### 7.4 BorgMaster Fault Tolerance — Paxos Failover

When the BorgMaster leader fails, the 5-replica Paxos cluster detects the failure
(via heartbeat timeout), holds an election, and a new leader is elected in ~10 seconds.
The new leader reads the Paxos log and checkpoint to reconstruct in-memory state,
then resumes normal operation.

During the ~10 seconds of failover, no new scheduling decisions are made and Borglets
cannot report state. But all running tasks continue running — they are just running
their task containers, which don't need BorgMaster to stay up.

### 7.5 Preemption as Fault Tolerance

An underappreciated form of "fault tolerance" in Borg is preemption itself. When a
production task needs resources and the only way to get them is to evict batch tasks,
Borg does so without hesitation. This is not really a failure scenario — it is an
intended behavior. But from the batch task's perspective, it looks exactly like a
failure: the task is suddenly killed and rescheduled elsewhere.

The design lesson: tasks should be written to handle being killed at any time. This is
why Borg encourages (and batch frameworks require) checkpointing. Any task that writes
precious state only to local memory — without ever checkpointing — is fragile. The
cluster can always kill and reschedule it.

### 7.6 Health Checks

Borg monitors task health via health check endpoints. Each task can expose an HTTP
URL (e.g., `/healthz`) that Borg polls periodically. A healthy task returns HTTP 200.
An unhealthy task might return 500, or fail to respond at all.

If a task fails health checks for too long, Borg treats it as dead and reschedules it —
even if the process is technically still running. This handles the "zombie" case: a
task that is running (from the OS perspective) but not serving traffic (application-
level failure, deadlock, infinite loop).

This is exactly the Kubernetes **liveness probe** concept — directly inherited from Borg.

### 7.7 Real Incident: The Preemption Cascade of 2012

In early 2012, a Google team pushed a configuration change that accidentally set their
batch MapReduce jobs to "production" priority. The jobs were large — they needed many
thousands of CPUs. Borg's scheduler, seeing these now-"production" jobs waiting for
resources, began preempting actual production jobs to make room.

Production jobs being preempted triggered alerts. On-call engineers got paged at 2 AM.
Initially, they couldn't figure out why production tasks were being killed — the affected
machines looked healthy. It took about 20 minutes to trace the preemption back to the
misconfigured priority.

The fix was simple: revert the priority to "batch." But the recovery was not instant —
after reverting, the preempted production tasks needed to be rescheduled, which took
several minutes. Google Search showed a brief degradation in some regions.

The lesson Borg engineers took from this incident: priority changes should require
a higher level of access control than ordinary job configuration. Today, Borg (and
Kubernetes PriorityClass) restrict who can submit tasks at production priority. Not
everyone can create a "PriorityClass" in Kubernetes — it requires cluster admin
permissions.

---

### Brainstorming: Part 7 Questions

**Q1: Why does Borg wait before declaring a machine dead instead of acting immediately?**

Network issues are common and transient. A machine might be temporarily unreachable
because a top-of-rack switch is congested, a cable was briefly disconnected and
reconnected, or there is a brief kernel hiccup. If BorgMaster declared every temporarily
unreachable machine "dead" immediately, it would constantly reschedule tasks unnecessarily.

The cost of unnecessary rescheduling is significant. The task has to stop, start
elsewhere, warm up its caches, reconnect to dependencies — all of which takes time
and resources. If the original machine was actually fine, you've incurred all this
cost for nothing. A grace period absorbs the noise of transient connectivity issues.
The tradeoff is that true machine failures have a delay before recovery begins, but
for most services, a 2-3 minute delay before recovery is acceptable. Services have
enough replicas that losing one machine's tasks for 2-3 minutes is not an outage.

**Q2: How does Borg prevent a single machine failure from causing an outage if that
machine had many tasks from the same job?**

Borg's spreading score in Phase 2 scoring penalizes placing many tasks of the same
job on the same machine, same rack, or same network domain. If tasks A1-A50 of job
X are spread across 10 different racks, losing one rack takes out at most 5 of 50
tasks — 10% of the job's capacity. The job degrades gracefully instead of failing
completely.

However, spreading has a cost: it can increase scheduling latency (harder to find
machines that satisfy spreading constraints when the cluster is nearly full). Borg
lets job owners tune the spreading weight — jobs that can tolerate some co-location
for better scheduling performance can relax the constraint. Jobs that are deeply
latency-critical (like Search) apply strict spreading constraints and pay the
scheduling cost. This is a deliberate tradeoff exposed to job owners as a knob.

**Q3: What happens to a job's tasks when BorgMaster is unavailable for an extended period?**

Running tasks continue to run — Borglets execute tasks independently and only need
BorgMaster for new assignments. A task that is already running on machine M will
keep running on machine M even if BorgMaster is gone for hours.

What stops working during an extended BorgMaster outage is self-healing. If machine
M fails while BorgMaster is down, the tasks on M cannot be rescheduled — they simply
stop running and nobody schedules replacements. For a short outage (seconds to minutes),
this is acceptable given the redundancy of most production services. For a long outage
(hours), it would be a serious incident because the cluster is no longer self-healing.

This is why BorgMaster's 5-replica Paxos design is so critical. The expected availability
of a 5-replica Paxos system where any 3 replicas must be healthy is very high. In
practice, Google has never experienced a BorgMaster outage lasting more than minutes.
The Paxos replication across geographically distributed racks ensures that even a
partial datacenter failure doesn't take down BorgMaster.

---

## Part 8: Bin-Packing and Utilization — The Tetris Analogy

### 8.1 The Bin-Packing Problem

Bin-packing is a famous computer science problem: given a set of items with sizes,
pack them into the fewest possible bins (each of limited capacity).

In Borg's case: items are tasks (each needing some CPUs and RAM), and bins are
machines (each with finite CPUs and RAM). The goal is to pack as many tasks as
possible onto as few machines as possible, leaving some machines empty so they
can be powered down or used for large future tasks.

This is why it's called "bin-packing" — you're packing tasks (items) into machines (bins).

### 8.2 The Tetris Analogy

Imagine playing Tetris. Pieces come in different shapes (L-shaped, square, line).
You need to fit them into the playing field with as few gaps as possible. A bad Tetris
player leaves holes everywhere — pieces don't fit, the stack builds up, and you lose.
A good Tetris player rotates pieces to fill gaps efficiently — the stack stays low and
every row gets filled.

Borg is a Tetris player for your datacenter. Each task is a Tetris piece with a
2D shape defined by (CPU requirement, RAM requirement). Each machine is a column in
the Tetris field with capacity (total CPUs, total RAM). Borg tries to place tasks so
that machine utilization is high and "holes" (wasted capacity) are minimized.

```
Bin-Packing: Tasks Onto Machines
==================================

Tasks to schedule:
  Task A: 2 CPUs, 4 GB RAM
  Task B: 4 CPUs, 2 GB RAM
  Task C: 1 CPU,  6 GB RAM
  Task D: 3 CPUs, 2 GB RAM
  Task E: 2 CPUs, 4 GB RAM

Machine capacity: 8 CPUs, 16 GB RAM each

STRATEGY 1 (Naive — spread evenly):
  Machine 1: [Task A] + [Task B] = 6 CPUs, 6 GB RAM used
             Remaining: 2 CPU, 10 GB RAM (wasted!)
  Machine 2: [Task C] + [Task D] = 4 CPUs, 8 GB RAM used
             Remaining: 4 CPU, 8 GB RAM (wasted!)
  Machine 3: [Task E]            = 2 CPUs, 4 GB RAM used
             Remaining: 6 CPU, 12 GB RAM (mostly empty!)
  Utilization: 3 machines, ~46% utilized.

STRATEGY 2 (Borg Bin-Packing — pack tightly):
  Machine 1: [Task A]+[Task B]+[Task E] = 8 CPUs, 10 GB RAM used
             Remaining: 0 CPU, 6 GB RAM (CPU full!)
  Machine 2: [Task C]+[Task D]          = 4 CPUs, 8 GB RAM used
             Remaining: 4 CPU, 8 GB RAM
             → Fits 2 more Task-A-sized tasks
  Machine 3: EMPTY — can be powered down or used for future big jobs

  Utilization: 2+ machines actively used. Machine 3 freed.
  CPU utilization: ~90%. Machine count: 2 vs 3. Win!

LESSON: Tight packing reduces machine count for the same workload.
```

### 8.3 The Mixed-Workload Insight

The Borg paper's most impactful finding: mixing **long-running serving jobs**
(production, always on, diurnal traffic patterns) with **batch jobs** (flexible,
interruptible, time-insensitive) dramatically improves utilization.

Why? Serving jobs have resource peaks and valleys:

```
Serving Job CPU Usage Over 24 Hours
======================================

  CPU
  Usage
  │
4 │                    ████████████████
  │               █████                ████
3 │          ██████                        ████
  │       ████                                 ██
2 │    ████                                      ████
  │  ██                                              ██
1 │                                                    ██
  │
  └────────────────────────────────────────────────────── Time
  12am   3am   6am   9am   12pm  3pm   6pm   9pm   12am

          Reserved capacity (production reserved): 4 CPUs
          ↑ Always kept reserved for peak

  SLACK (unused reserved capacity) = Reserved - Actual
  The gray area above the usage line is CPU slack.
  At 3am, slack = 3 CPUs of reserved-but-unused capacity.
```

Without batch jobs, that 3 CPUs of slack at 3 AM is wasted. With Borg's reclamation,
batch MapReduce jobs run on that slack. During the day when serving jobs need all 4 CPUs,
the batch jobs are throttled or preempted. The machines are busy 24 hours a day instead
of 12. This is the fundamental reason Borg achieves 60-70% utilization.

### 8.4 Utilization Numbers That Matter for Interviews

From the 2015 Borg paper:

- Without reclamation and batch mixing: cells would be ~40-50% utilized
- With Borg's full machinery: 60-70%+ utilization
- CPU is typically requested at 2-3x actual usage (over-provisioning)
- RAM is typically requested at 1.5-2x actual usage
- A significant fraction of tasks (the paper notes a non-trivial percentage) are
  smaller than the machine they occupy — meaning single-machine fit is not the
  bottleneck; packing is

### 8.5 The Intern-to-Staff Progression on Bin-Packing

| Level | Understanding |
|-------|---------------|
| **Intern** | "Borg puts tasks on machines with enough resources" |
| **Junior** | "Borg tries to maximize machine utilization by fitting tasks together efficiently" |
| **Mid** | "Bin-packing: score feasible machines by how well the task fills them. The scoring function balances packing density vs. spreading for fault tolerance." |
| **Senior (L5)** | All of the above plus: "The key utilization insight is mixed workloads — batch jobs consume slack left by serving jobs, taking overall utilization from 40% to 60-70%. Borg's reclamation mechanism is the implementation." |
| **Staff (L6)** | All of the above plus: "The bin-packing scoring function has subtle pathologies. Greedy first-fit-decreasing (classic algorithm) doesn't optimize for 2D packing (both CPU and RAM). Borg uses a more sophisticated multi-dimensional packing score that penalizes creating machines with wasted RAM but free CPU (or vice versa) — 'stranded' resources that can't be used by any realistic task." |

---

### Brainstorming: Part 8 Questions

**Q1: Why is 60-70% utilization considered excellent for a datacenter? Why not 90%+?**

Running at 90%+ utilization sounds great on paper but is operationally dangerous.
At 90% utilization, the cluster has very little headroom. If a machine fails, its
tasks need to be rescheduled — but there is almost nowhere for them to go. If traffic
spikes, there is no capacity to absorb the spike. If you want to do a rolling upgrade
of a service (take down 10% of tasks at a time, bring up new versions), you need
10% extra headroom — which you don't have at 90%.

The practical upper bound for stable cluster operation is around 70-80%. Above that,
scheduling latency increases (fewer feasible machines means the scheduler runs longer),
preemption cascades become more likely (many tasks competing for scarce resources),
and failure recovery takes longer (no free machines to absorb rescheduled tasks). Google's
60-70% target is not a lack of ambition — it is a careful operational choice that
leaves enough slack for failure recovery, traffic spikes, and maintenance operations.

**Q2: How does bin-packing interact with the machine heterogeneity in a real datacenter?**

Google's datacenter is not all identical machines. Over years of hardware procurement,
there are machines with different CPU architectures, amounts of RAM, presence or absence
of GPUs, different local disk sizes, and different network bandwidth. This heterogeneity
makes bin-packing harder because you cannot treat all bins as identical.

Borg handles heterogeneity through the constraint and scoring system. Tasks can express
preferences ("prefer machines with >= 32 GB RAM") or hard requirements ("require GPU").
The scoring function can account for different machine capabilities. In practice, Borg
tracks machine properties as key-value attributes and tasks express constraints as
logical predicates over those attributes. This is the direct precursor to Kubernetes
node selectors, taints/tolerations, and affinity rules — the same concept, more
expressive API.

**Q3: How does Google decide how many machines to provision for a cell? Is there a
formula?**

The provisioning decision is based on target utilization, expected growth rate, and
failure reserve. The rough mental model: provision enough machines so that at your
target utilization (say, 65%), you have 35% headroom. The headroom must be large
enough to absorb the worst-case simultaneous failure scenario you plan to tolerate.

If you plan to tolerate any single rack failing (say, 500 machines out of 10,000),
you need enough headroom to reschedule those 500 machines' tasks — so at least 5%
extra headroom. Rolling upgrades might need another 10% headroom at any given time.
Emergency traffic spikes might need 10-15%. Add these up and you get the minimum
headroom, which determines the maximum utilization target. In practice, Google uses
a planning model that projects cell capacity requirements 12-18 months out, accounting
for expected traffic growth, new service launches, and planned hardware refresh cycles.

---

## Part 9: The Borg → Kubernetes Concept Mapping

### 9.1 Why This Mapping Matters

Kubernetes was designed by ex-Google engineers who built Borg. They consciously ported
Borg's best ideas to an open-source platform with a cleaner API. Understanding the
mapping tells you WHY Kubernetes works the way it does — not just that it does.

At a Level 6 interview at Google (or any FAANG+), being able to say "Kubernetes' X is
Borg's Y, and here's the specific design difference and why Google made that choice"
signals deep systems knowledge.

### 9.2 The Concept Mapping Table

```
Borg → Kubernetes Concept Mapping
====================================

┌───────────────────────┬─────────────────────────────────┬────────────────────────────────────────────────┐
│ Borg Concept          │ Kubernetes Equivalent           │ Key Difference                                 │
├───────────────────────┼─────────────────────────────────┼────────────────────────────────────────────────┤
│ Job (homogeneous      │ Deployment (stateless) or       │ K8s separated stateless vs stateful. Borg Job  │
│ task group)           │ StatefulSet (stateful)          │ was one concept; K8s has two with different    │
│                       │                                 │ semantics (persistent identity in StatefulSet) │
├───────────────────────┼─────────────────────────────────┼────────────────────────────────────────────────┤
│ Task (one process on  │ Pod (one or more containers     │ Pod is an Alloc+Task fusion: multiple          │
│ one machine)          │ on one machine)                 │ containers share network/volumes. Borg tasks   │
│                       │                                 │ and Allocs were separate concepts.             │
├───────────────────────┼─────────────────────────────────┼────────────────────────────────────────────────┤
│ Alloc (resource       │ Pod (multi-container) /         │ K8s baked Alloc into Pod. Borg Allocs were     │
│ reservation shared    │ Init containers                 │ a scheduling concept; K8s makes them a         │
│ by multiple tasks)    │                                 │ deployment concept.                            │
├───────────────────────┼─────────────────────────────────┼────────────────────────────────────────────────┤
│ Priority (0-450       │ PriorityClass (named,           │ K8s added named classes for human              │
│ numeric scale)        │ mapped to numeric values)       │ readability. Borg's raw numbers were           │
│                       │                                 │ opaque to operators.                           │
├───────────────────────┼─────────────────────────────────┼────────────────────────────────────────────────┤
│ Quota (team-level     │ ResourceQuota (namespace-       │ K8s uses namespaces (not teams) as the         │
│ resource budget)      │ level resource budget)          │ unit of quotas. More flexible multi-tenancy.   │
├───────────────────────┼─────────────────────────────────┼────────────────────────────────────────────────┤
│ BorgMaster            │ kube-apiserver (API) +          │ K8s decomposed BorgMaster into separate        │
│ (monolithic control   │ etcd (state) +                  │ components. More modular; pluggable            │
│ plane)                │ kube-scheduler +                │ schedulers possible.                           │
│                       │ controller-manager              │                                                │
├───────────────────────┼─────────────────────────────────┼────────────────────────────────────────────────┤
│ Borglet               │ kubelet                         │ Very close 1:1. kubelet also manages           │
│ (agent on machine)    │ (agent on node)                 │ CNI/CSI plugins (network + storage)            │
│                       │                                 │ that Borglet did not.                          │
├───────────────────────┼─────────────────────────────────┼────────────────────────────────────────────────┤
│ BCL config file       │ YAML manifests /                │ YAML is more verbose but simpler. Helm         │
│ (Borg Config Lang)    │ Helm charts                     │ adds templating that BCL had natively.         │
├───────────────────────┼─────────────────────────────────┼────────────────────────────────────────────────┤
│ Named Jobs            │ Label Selectors                 │ MAJOR improvement. Borg jobs had fixed names;  │
│ (job names as         │ (arbitrary key-value tags,      │ K8s labels are flexible. Services select Pods  │
│ identifiers)          │ select subsets dynamically)     │ by label, not name.                            │
├───────────────────────┼─────────────────────────────────┼────────────────────────────────────────────────┤
│ Port-per-task         │ IP-per-pod                      │ MAJOR improvement. Borg assigned each task     │
│ (task shares machine  │ (each pod has own IP)           │ a unique port on the machine IP. K8s gives     │
│ IP, unique port)      │                                 │ each pod its own IP — no port conflicts,       │
│                       │                                 │ simpler networking model.                      │
├───────────────────────┼─────────────────────────────────┼────────────────────────────────────────────────┤
│ Reconciliation loop   │ Controller loops                │ K8s made the reconciliation loop a first-      │
│ (in BorgMaster)       │ (controller-manager runs        │ class extensibility point. Anyone can write     │
│                       │ many independent loops)         │ a custom controller (CRD + controller).        │
├───────────────────────┼─────────────────────────────────┼────────────────────────────────────────────────┤
│ Health checks         │ Liveness probes /               │ K8s added readiness (don't send traffic yet)   │
│ (HTTP endpoint poll)  │ Readiness probes /              │ and startup (allow slow starts) — more         │
│                       │ Startup probes                  │ nuanced than Borg's single health check.       │
├───────────────────────┼─────────────────────────────────┼────────────────────────────────────────────────┤
│ Fauxmaster            │ (no direct equivalent)          │ K8s has kube-scheduler-simulator in the        │
│ (cluster simulator)   │                                 │ community, but it's not first-party.           │
└───────────────────────┴─────────────────────────────────┴────────────────────────────────────────────────┘
```

### 9.3 The Port-per-Task vs. IP-per-Pod Story

This difference is worth understanding deeply because it reveals a fundamental
networking design choice.

**Borg's approach (port-per-task)**: Each machine has one IP address. Multiple tasks
on the same machine share that IP. Each task gets assigned a unique port. So if machine
10.1.2.3 has three tasks — Gmail, Docs, and Sheets — they might listen on ports
8001, 8002, and 8003 respectively. To reach Gmail on that machine, you connect to
10.1.2.3:8001.

This works, but it is operationally painful. Every task must be configured with its
assigned port number. Services need to know not just the IP of a task but also its
port. Debugging becomes harder. Load balancers are more complex. Port assignments
can conflict.

**Kubernetes' approach (IP-per-pod)**: Each pod gets its own IP address from the
cluster's pod CIDR range. Gmail's pod might be at 192.168.1.5, Docs' pod at
192.168.1.6, Sheets' pod at 192.168.1.7. Each pod can listen on port 8080 without
conflict because they have different IPs. Services just know "Gmail is at 192.168.1.5:8080."

This is dramatically simpler from a networking model perspective. The tradeoff is
that it requires more complex network infrastructure (pod CIDR routing, overlay
networks like Flannel or Calico, or sophisticated SDN). Kubernetes chose to absorb
this complexity in the infrastructure layer to simplify the application layer.
This was the right tradeoff: application developers are far more numerous than
infrastructure engineers, and simplifying their experience is worth infrastructure complexity.

---

### Brainstorming: Part 9 Questions

**Q1: Why did Kubernetes decompose BorgMaster into separate components instead of
keeping it monolithic?**

Decomposing BorgMaster into kube-apiserver, etcd, kube-scheduler, and controller-
manager enables a critical property: pluggability. In Borg, the scheduler is baked
into BorgMaster and cannot be replaced without modifying BorgMaster's code. In
Kubernetes, you can run a completely custom scheduler by implementing the scheduler
interface and replacing kube-scheduler. Many organizations do this — for example,
to implement GPU-aware scheduling or specialized batch scheduling policies.

Similarly, the controller-manager is just a collection of control loops, and anyone
can write additional control loops via Custom Resource Definitions (CRDs) and custom
controllers. This is how the Kubernetes ecosystem produces operators for databases
(StatefulSet + custom controller), ML training jobs (Kubeflow), and many other
workload types that Borg could only support by modifying Google's internal codebase.
The extensibility model was deliberately designed to allow the open-source community
to build the functionality that Google engineers would otherwise have to build internally.

**Q2: What does Borg still do better than Kubernetes in 2025?**

Despite Kubernetes' improvements, Borg retains advantages in a few areas. First,
Borg has decades of production tuning at Google scale — its scheduling algorithms,
resource reclamation heuristics, and operational tooling are calibrated to Google's
actual workload patterns in ways no external system can match. Second, Borg is deeply
integrated with Google's internal infrastructure: GFS/Colossus for data locality,
Chubby for distributed locking, Borgmon/Monarch for monitoring. This tight integration
enables optimizations (like data-locality-aware scheduling) that require custom
integrations in Kubernetes.

Third, Borg's Fauxmaster simulator is a genuinely more advanced operational tool than
anything in the Kubernetes ecosystem. Being able to replay a snapshot of real cluster
state against a new scheduler algorithm without affecting production is invaluable for
large-scale scheduling research. Google has published multiple papers using Fauxmaster
to evaluate scheduling improvements — this kind of rapid experimentation is harder
in Kubernetes.

**Q3: If Kubernetes is essentially open-source Borg, why did Google open-source it
instead of Borg itself?**

Borg is deeply entangled with Google's internal infrastructure. BCL (Borg Configuration
Language) assumes the existence of internal build systems, binary artifact storage,
network configurations, and monitoring systems that don't exist outside Google. Borg
cannot be run outside of Google's internal environment — it is not a standalone system.

Kubernetes was designed from scratch as a standalone system usable by any organization.
It uses standard open protocols (HTTP, gRPC), external state storage (etcd, which is
also open source), and standard Linux container primitives (Docker, containerd). The
Kubernetes founders took Borg's ideas and re-implemented them with portability as a
primary design goal. This required significant redesign work — especially in networking
(IP-per-pod instead of port-per-task) and configuration (YAML instead of BCL) — to
make the system work in environments without Google's internal infrastructure.

---

## Part 10: What Kubernetes Improved and What Borg Does Better

### 10.1 Kubernetes' Genuine Improvements Over Borg

The Borg paper itself acknowledges several things that Borg got wrong, which Kubernetes
fixed. These are not marketing claims — they are from Google's own post-mortem analysis
of Borg's design.

**1. Label Selectors over Named Jobs**

In Borg, a job has a fixed name. To route traffic to a job, you use that name. This
creates rigidity. If you want to do a blue-green deployment (run old version and new
version simultaneously), you need two job names. If you want to route 10% of traffic
to the new version, you need to configure that routing based on job names, which are
not flexible.

Kubernetes labels are arbitrary key-value pairs. A pod can have labels like:
`app=gmail, version=v2.3, tier=frontend, region=us-east-1`. Services select pods
using label queries: "give me all pods where `app=gmail` and `tier=frontend`." This
is powerful and flexible. Blue-green deployments, canary releases, A/B testing, and
traffic splitting are all natural expressions of label selectors.

**2. IP-per-Pod over Port-per-Task**

Covered in detail in Part 9. The networking model simplification is real and significant.

**3. Multiple Containers per Unit of Scheduling**

Borg's Job/Task model assumes one container per task. Allocs allow co-location but
require explicit management. Kubernetes' Pod natively supports multiple containers
sharing the same network namespace and volumes. This makes sidecar patterns (logging
agents, proxies, monitoring collectors) first-class citizens.

**4. Better Multi-Tenancy**

Borg's multi-tenancy is team-based (teams own jobs, teams have quotas). Kubernetes
introduces namespaces — logical clusters within a cluster — each with their own
resource quotas, network policies, and RBAC rules. This enables more fine-grained
isolation between tenants without requiring separate physical clusters.

**5. Open Ecosystem**

Kubernetes has a massive open-source ecosystem: Helm for package management, Istio
for service mesh, Prometheus for monitoring, ArgoCD for GitOps. Borg has none of
this because it is internal to Google. The ecosystem is arguably Kubernetes' biggest
advantage — it means any problem you encounter has likely been solved by someone
else, and that solution is available as an open-source project.

### 10.2 What Borg Does Better

**1. Resource Accounting Sophistication**

Borg's understanding of actual vs. requested resource usage, reclamation, and multi-
dimensional packing has been refined over 15+ years of production operation at Google
scale. Kubernetes' equivalent features (vertical pod autoscaler, resource quotas,
LimitRanges) are newer and less battle-tested. Google's Autopilot system (which
automatically sets resource requests based on observed usage) is more advanced than
anything in open-source Kubernetes today.

**2. Scale**

Borg manages Google-scale infrastructure: multiple cells each with tens of thousands
of machines. A single Kubernetes cluster is typically limited to around 5,000 nodes
before control plane scaling issues appear. Google manages much larger deployments
internally and has optimizations in Borg (and in their internal Kubernetes fork) that
the open-source project hasn't fully absorbed.

**3. Operational Depth**

Borg's operational tooling — Fauxmaster for simulation, sophisticated quota management,
deep integration with internal monitoring (Borgmon/Monarch), the Borg Name Service for
service discovery — represents years of accumulated operational wisdom. Kubernetes
tooling has improved dramatically but is younger.

**4. Performance**

Borg's in-memory state store and highly optimized scheduling code is tuned for
maximum throughput at Google's scale. Kubernetes' use of etcd as a general-purpose
distributed store introduces bottlenecks at very high scale (many API objects, frequent
updates). For 99% of users, Kubernetes is fast enough. At Google scale, those
bottlenecks matter.

---

### Brainstorming: Part 10 Questions

**Q1: How do label selectors enable deployment patterns that Borg's named jobs cannot?**

Consider a canary deployment: you want to deploy a new version of your web server to
5% of your pods while 95% run the old version. With Borg's named jobs, you create
two jobs: "gmail-v1" with 950 tasks and "gmail-v2" with 50 tasks. Your load balancer
must be explicitly configured to split traffic 95/5 between these two named jobs.
If you decide to promote v2 to 20%, you reconfigure both the job task counts AND the
load balancer split — two separate changes that must be coordinated.

With Kubernetes labels and a service that selects `app=gmail` (which matches both
v1 and v2 pods), the canary is simply: change the ratio of v1 vs v2 pods. The service
automatically routes traffic proportional to the number of pods of each version. To
promote v2, just scale up v2 Deployment and scale down v1 Deployment. The service
selection requires no reconfiguration. This is not just more convenient — it is less
error-prone because there are fewer configuration changes to coordinate.

**Q2: Is there a scenario where you would choose Borg's scheduling model over
Kubernetes' model for a new system?**

If you are building a cluster manager for a single large organization (not open
source), you might prefer Borg's tighter integration model. Borg's BCL, though
complex, is a full programming language that allows expressing complex configurations
that Kubernetes YAML cannot without Helm or Kustomize preprocessing. Borg's deep
integration with Google's binary build system means the configuration system knows
about code dependencies, test coverage, and artifact storage — context that Kubernetes
YAML manifests don't have.

For a private cloud with uniform infrastructure and centralized engineering teams,
Borg's monolithic architecture is also simpler to operate. You have one team
responsible for the whole system, not a distributed ecosystem of independently versioned
components. The pluggability that makes Kubernetes powerful also makes it operationally
complex — you have to choose and configure a CNI plugin, a CSI plugin, a scheduler,
a monitoring system, and many other components. Borg's prescriptive architecture
eliminates those choices.

**Q3: Given Kubernetes' improvements, do you think Google will ever migrate fully
off Borg to Kubernetes?**

Google runs Kubernetes internally — their cloud product (GKE) runs on Kubernetes, and
many internal teams use internal Kubernetes clusters. However, Borg remains the
underlying cluster manager for Google's most critical workloads: Gmail, Search, Ads.
Migrating these workloads to Kubernetes would be one of the largest software migrations
in history, and the risk/reward is questionable.

The likely long-term equilibrium is coexistence: Borg for legacy Google-scale critical
workloads, Kubernetes for new projects and cloud customers. Google's engineering teams
working on Kubernetes contribute Borg learnings to Kubernetes, gradually raising
Kubernetes' capabilities. Some Borg features have already been ported: the vertical
pod autoscaler, PriorityClass, preemption — all came from Borg. This knowledge transfer
means Kubernetes is converging toward Borg, rather than Borg being replaced by Kubernetes.

---

## Part 11: Interview Application — How to Use This in Practice

### 11.1 When Borg Concepts Appear in Interviews

Borg-derived concepts appear in four common interview scenarios:

**Scenario 1: "Design a job scheduling system"**
This is literally Borg. Your answer should reference: desired state + reconciliation
loop, two-phase scheduling (feasibility + scoring), priority-based preemption, bin-packing
for utilization, Paxos-replicated control plane.

**Scenario 2: "Design a container orchestration system"**
Kubernetes is open-source Borg. Explain Jobs/Tasks/Allocs → Deployments/Pods, control
loops, bin-packing, and the key improvements (IP-per-pod, label selectors).

**Scenario 3: "How does Kubernetes work internally?"**
Walk through: kube-apiserver receives YAML → stores in etcd → controller-manager
runs reconciliation loop → kube-scheduler runs two-phase scheduling → kubelet starts
container. Every component maps to a Borg component.

**Scenario 4: "How do you handle machine failures at scale?"**
Answer: desired state + reconciliation loop. The loop doesn't know or care WHY actual
state differs from desired. Machine failure, software crash, network partition — all
produce the same "actual != desired" condition. The loop reschedules automatically.

### 11.2 L5 vs. L6 Calibration

| Dimension | L5 Answer | L6 Answer |
|-----------|-----------|-----------|
| **Framing** | "We use Kubernetes for orchestration" | "The core abstraction is desired state + reconciliation loop. Kubernetes inherited this from Borg." |
| **Scheduling** | "The scheduler finds a node with enough resources" | "Two-phase: feasibility filter (constraints, resource fit, preemption potential) then scoring (bin-packing, data locality, spreading). Random subset for performance." |
| **Resource model** | "CPU and memory limits" | "CPU is compressible (throttle), RAM is non-compressible (OOM kill). Request for scheduling, limit for enforcement. Reclamation bridges the gap for batch jobs." |
| **Fault tolerance** | "Kubernetes restarts crashed pods on healthy nodes" | "The reconciliation loop handles all failure modes uniformly. Rate limiting prevents cascade restarts. Exponential backoff for repeated failures. BorgMaster failover in ~10 seconds via Paxos." |
| **Utilization** | "We pack tasks tightly to reduce machine count" | "Mixed workloads are the key. Serving jobs have diurnal patterns; batch jobs consume their slack. Borg takes utilization from 40% to 60-70%. The reclamation mechanism is the implementation." |
| **Improvements** | "Kubernetes is better than older systems" | "Kubernetes fixed Borg's specific shortcomings: named jobs → label selectors, port-per-task → IP-per-pod, monolithic BorgMaster → pluggable components, BCL → YAML + Helm." |

### 11.3 Common Interview Mistakes

**Mistake 1: Thinking Kubernetes invented desired state**

Many candidates describe desired state and reconciliation loops as "Kubernetes
concepts" without knowing they came from Borg. An interviewer at Google will immediately
recognize this and ask "where does Kubernetes get this from?" The correct answer is
Borg (2003-2004 internally, paper published 2015). More broadly, the control loop
pattern traces to control theory and systems like Omega and YARN, but Borg is the
direct precursor to Kubernetes.

**Mistake 2: Conflating CPU throttling and OOM killing**

Candidates often say "if a task uses too many resources, it gets killed." This is
only true for RAM (non-compressible). For CPU (compressible), the task is throttled —
it runs slower but stays alive. This distinction matters for system design: if you
over-limit CPU, your task is slow but recoverable. If you over-limit RAM (set limit
too low), your task randomly dies. Engineers should be much more careful about RAM
limits than CPU limits.

**Mistake 3: Not knowing what BorgMaster/kube-scheduler actually does**

Candidates say "Kubernetes schedules pods on nodes" without being able to explain
the two phases: feasibility filtering (which nodes CAN host this pod?) and scoring
(which node SHOULD host this pod?). The scoring function and its components (bin-
packing, spreading, data locality) are what distinguish a thoughtful L6 candidate
from an L5 who "knows Kubernetes."

**Mistake 4: Describing fault tolerance as explicit failure handlers**

A common L5 mistake: "When a machine fails, Kubernetes detects the failure and
reschedules the pods." While technically true, this description implies explicit
failure handling code. The L6 insight is that there IS no failure-specific code —
the reconciliation loop handles machine failures the same way it handles any other
"actual != desired" discrepancy. Emphasizing this makes your answer sound architecturally
principled rather than just procedural.

**Mistake 5: Not knowing the utilization numbers**

When asked "how much does Borg improve utilization," many candidates say "a lot" or
"significantly." The 2015 paper gives specific numbers: ~20 percentage point improvement
(from 40-50% to 60-70%) attributed primarily to mixed workloads and resource reclamation.
Having specific numbers signals that you have actually read the primary literature.

**Mistake 6: Saying "just use Kubernetes" without design depth**

At the L5 level, "use Kubernetes" is an acceptable answer. At L6, you need to explain:
which Kubernetes components handle which aspects of the problem, what the tradeoffs are,
what the failure modes are, and how you would tune the system for your specific workload.
"Use Kubernetes" is the start of an L6 answer, not the end of one.

### 11.4 Key Numbers to Cite in Interviews

| Number | Source |
|--------|--------|
| ~10,000 machines per cell (median) | EuroSys 2015 paper |
| ~20% utilization improvement over naive allocation | EuroSys 2015 paper |
| ~10 seconds BorgMaster failover time | EuroSys 2015 paper |
| 5 replicas in BorgMaster's Paxos group | EuroSys 2015 paper |
| 0-450 priority scale (production at ~300-400) | EuroSys 2015 paper |
| CPU over-reservation: 2-3x actual usage | EuroSys 2015 paper |
| RAM over-reservation: 1.5-2x actual usage | EuroSys 2015 paper |

### 11.5 The Concept That Transfers Everywhere

The desired state + reconciliation loop is not just a cluster management pattern.
It is a general pattern for any self-managing distributed system:

- **Database replication**: "Desired state: all replicas have the same data. Loop: detect
  divergence, replicate missing writes."
- **Load balancer health**: "Desired state: only healthy backends receive traffic. Loop:
  health check backends, remove unhealthy ones."
- **Autoscaling**: "Desired state: N replicas when CPU > 70%. Loop: check metrics,
  scale up or down."
- **GitOps (ArgoCD/Flux)**: "Desired state: what's in the Git repo. Loop: detect drift
  between cluster and repo, apply changes."

Whenever an interviewer asks "how does your system handle failures or drift?", your
answer should start with "we use a desired state model with a reconciliation loop —
here's how it works in this context..."

---

### Brainstorming: Part 11 Questions

**Q1: How would you apply the Borg architecture to design a distributed task queue
system (like a job scheduler for a data pipeline platform)?**

A data pipeline task queue system maps onto Borg's architecture naturally. The
"BorgMaster" becomes a scheduler service with a Paxos-replicated control plane that
stores all job and task state. Jobs in the task queue are the Borg Jobs: collections
of tasks (data pipeline stages) with resource requirements (CPU for the worker, RAM
for intermediate data). The Borg scheduler's two-phase design applies directly:
feasibility filters workers that cannot handle the task (wrong environment, insufficient
resources, incompatible dependencies), and scoring selects the best worker (least loaded,
closest to input data, most cache warmth for this type of job).

The reconciliation loop handles failures: if a worker process dies mid-task, the loop
sees "task T was running but is no longer" and reschedules it to another worker. If a
task fails repeatedly, exponential backoff prevents thundering herd restarts. Priority
enables SLA differentiation: interactive pipeline tasks (triggered by user actions) get
high priority and preempt long-running batch jobs during business hours.

One difference from Borg: pipeline tasks typically need to track intermediate state
(which tasks have completed, what their outputs are). This requires a task dependency
graph, which Borg's job model doesn't natively support. You would add a DAG scheduler
layer on top of the Borg-style resource scheduler — Apache Airflow and Google Cloud
Composer do exactly this.

**Q2: An interviewer asks: "What's the hardest part of building a cluster scheduler
at scale?" What's the L6 answer?**

The technically honest L6 answer is: the hardest part is the interaction between
scheduling decisions and cluster dynamics. Scheduling looks simple in textbooks:
filter feasible machines, pick the best one. But at scale, multiple schedulers run
concurrently and may make conflicting decisions. Machine states change faster than
the scheduler can observe. Tasks fail between the scheduling decision and the actual
placement. The feasible set in the scheduler's view may be stale.

The solution is optimistic concurrency: schedulers work with a snapshot of state,
make decisions, and commit them with a conflict check. If another scheduler placed
a task on the same machine first, the current scheduler retries with fresh state.
This is the same model as database optimistic locking. The key insight is that
scheduling conflicts are relatively rare (the cluster is rarely so full that multiple
schedulers compete for the exact same machine), so optimistic concurrency has low
retry rates in practice. This is why Borg can run multiple concurrent scheduling
threads without global locking.

The second hardest part is the interaction between desired state and operational
reality. Desired state is a powerful abstraction, but it can be wrong. An engineer
sets desired replicas to 0 accidentally — the reconciliation loop faithfully kills
all replicas. An engineer pushes a broken binary — the reconciliation loop faithfully
reschedules it 100 times, each failing. The loop is only as good as the desired state
it is given. Building safeguards (config validation, dry-run modes, change rate limits,
automatic rollback on error signals) around the reconciliation loop is as much work
as building the loop itself.

**Q3: How would you convince a skeptical interviewer that the desired state model is
better than a traditional state machine model for cluster management?**

The skeptic's objection is usually: "State machines are rigorous. You know exactly
what state you're in and what transitions are valid. Desired state is vague — what
if the system is in an intermediate state you didn't anticipate?"

The counter-argument: at scale, state machines become intractable. A cluster with
10,000 machines and 100,000 tasks has an astronomical number of possible states.
Enumerating all states and transitions is impossible. You would need to write explicit
handlers for: task crashes, machine failures, network partitions, power failures,
partial deployments, scheduler bugs, clock skew, and their combinations. The state
machine would have millions of states.

The desired state model replaces this with a single invariant: "actual state should
equal desired state." The reconciliation loop enforces this invariant regardless of
what caused the divergence. The loop doesn't need to know which of the millions of
possible failure scenarios caused the divergence — it just detects that divergence
exists and acts to reduce it. This is a profound simplification that makes the system
manageable at scale. The tradeoff — the loop acts on any divergence, including
unintended ones caused by configuration errors — is addressed by operational tooling
(Fauxmaster, dry-run, change rate limits) rather than by abandoning the model.

---

## Part 12: Borg → Omega → Kubernetes — The Evolution Arc

### 12.1 Why Google Built Three Cluster Managers

Google did not stop at Borg. They built Omega as a research successor, and then
contributed Kubernetes as the open-source successor. Understanding WHY each system
was built reveals the genuine limitations of the prior system.

```
THE EVOLUTION TIMELINE
=======================

  2003-2004: Borg designed and deployed internally at Google
    Core insight: cluster-as-computer, desired state, two-phase scheduling
    Limitation: monolithic BorgMaster, single scheduler, BCL/Protobuf configs
    
  2010-2013: Omega research project (Google Research)
    Problem Omega solved: monolithic scheduler is a bottleneck for very large clusters
    Approach: shared-state scheduling — multiple schedulers, optimistic concurrency
    Key paper: "Omega: flexible, scalable schedulers for large compute clusters"
              (EuroSys 2013, Schwarzkopf et al.)
    Outcome: research system, informed Kubernetes design; not deployed at Google scale
    
  2013-2014: Kubernetes designed (Google engineers, announced 2014)
    Problem K8s solved: Borg is internal-only, BCL is proprietary, not developer-friendly
    Key improvements: label selectors (not string names), IP-per-pod, YAML/REST API,
                     open-source, pluggable components
    Outcome: became the industry-standard container orchestrator
```

### 12.2 Omega's Key Idea: Shared-State Scheduling

Borg's BorgMaster is a single scheduler that processes one job at a time. This
creates a throughput bottleneck for very large clusters (50,000+ machines).

Omega's answer: multiple concurrent schedulers, each with a full replica of cluster
state (the "cell state"). Each scheduler makes decisions independently, using
optimistic concurrency to commit placements:

```
OMEGA SHARED-STATE MODEL
=========================

  Cell State (full replica in each scheduler):
  ┌─────────────────────────────────────────────────────┐
  │  Machine A: 6/8 CPU used, 12/32 GB RAM used         │
  │  Machine B: 2/8 CPU used, 8/32 GB RAM used          │
  │  Machine C: 8/8 CPU used, 32/32 GB RAM (full)       │
  │  ...                                                 │
  └─────────────────────────────────────────────────────┘
         │                      │
         ▼                      ▼
  Scheduler A              Scheduler B
  (working on job X)       (working on job Y)
  "Place task on B"        "Place task on B"
         │                      │
         └──────────┬───────────┘
                    ▼
              Commit to cell state
              CONFLICT DETECTED (both chose machine B)
              One wins, one retries with fresh state

  KEY INSIGHT: conflicts are rare in practice (cluster is rarely so full
  that multiple schedulers compete for the exact same machine).
  Optimistic concurrency has low retry rates → high throughput.
```

**Omega vs Borg scheduling**: Borg = pessimistic (one scheduler at a time, no conflicts).
Omega = optimistic (multiple schedulers, rare conflicts, retry on conflict).

### 12.3 What Kubernetes Took from Each

| Feature | Origin | Kubernetes Implementation |
|---------|--------|--------------------------|
| Desired state + reconciliation | Borg | Controller manager with multiple controllers |
| Two-phase scheduling | Borg | kube-scheduler: filter + score plugins |
| IP-per-workload | Kubernetes original (over Borg's port-per-task) | Pod networking |
| Label selectors | Kubernetes original (over Borg's string names) | Label + selector throughout |
| Optimistic concurrency | Omega | ResourceVersion in etcd / API server |
| Pluggable schedulers | Omega | Scheduler framework with extension points |
| Open-source REST API | Kubernetes original | kubectl / API server |

### 12.4 Brainstorming Q&A — Part 12

**Q: If Borg already solved cluster management, why build Kubernetes?**

Three reasons. First, Borg's BCL configuration language is proprietary — developers
had to learn Google's internal language. Kubernetes uses YAML over a standard REST API;
any HTTP client can manage it. Second, Borg gives each task a port on the host machine
(port-per-task), which requires all application code to accept dynamic port assignments.
Kubernetes gives each pod its own IP address (IP-per-pod), letting applications listen
on standard ports. Third, Borg is a monolith — you cannot swap out the scheduler or
extend it easily. Kubernetes is built from composable, replaceable components. These
three changes made container orchestration practical for teams outside Google.

---

## Part 13: Gang Scheduling and ML Training Workloads

### 13.1 What Gang Scheduling Is

Gang scheduling: starting all tasks of a job simultaneously, or not at all.
This is critical for distributed ML training (TensorFlow, PyTorch distributed):

```
ML TRAINING: WHY ALL-OR-NOTHING MATTERS
=========================================

  A distributed training job needs:
  - 64 worker tasks (gradient computation)
  - 8 parameter server tasks (gradient aggregation)
  
  WITHOUT gang scheduling:
  Workers 1-60 start immediately.
  Workers 61-64 wait because machines are busy.
  Workers 1-60 idle, waiting for all workers to reach the first synchronization point.
  The cluster is paying for 60 idle workers for 10+ minutes.
  
  WITH gang scheduling:
  Schedule all 72 tasks atomically: wait until all 72 can start simultaneously.
  All tasks begin together, reach sync points together, no idle waiting.
  
  TRADE-OFF:
  Gang scheduling reduces wasted work but increases scheduling delay (must find
  72 free slots simultaneously, harder than finding them one at a time).
```

### 13.2 Does Borg Support Gang Scheduling?

Natively: no. Borg was designed for long-running services and MapReduce-style batch
jobs, where individual task independence is assumed. Gang scheduling was added as an
operational practice on top of Borg (using quota reservation and careful job submission
timing) but is not a first-class feature.

This is one reason Google later built dedicated ML infrastructure (Pathways, etc.)
and why Kubernetes has TFJob and PyTorchJob operators: gang scheduling for ML training
requires special handling that general-purpose cluster schedulers don't provide.

### 13.3 Interview One-Liner on Gang Scheduling

"Borg does not natively support gang scheduling. For ML training workloads where all
workers must start simultaneously, you need a higher-level operator (like TFJob) that
holds quota in reserve and submits all tasks atomically. This is a known gap between
general cluster schedulers and ML-specific infrastructure."

### 13.4 Checkpointing and Preemption Tolerance

Because Borg can preempt batch tasks at any time, batch jobs must be written to tolerate
sudden death. The standard technique is checkpointing: periodically write the current
computation state to durable storage (GFS/Colossus). When the task is rescheduled,
it reads the latest checkpoint and resumes from there rather than starting from scratch.

For ML training: checkpoint the model weights and optimizer state every N steps.
If preempted at step 10,000, the next run reads the checkpoint from step 9,500 and
resumes. Only 500 steps of work are lost.

For MapReduce: each Map and Reduce task is independently idempotent (running it twice
produces the same output). Preemption just means rerunning the affected task. No
checkpointing needed — idempotence is the simpler property.

This is why Borg can aggressively preempt batch jobs without requiring complex
recovery logic at the cluster level: the application itself handles restartability.
The cluster manager's job is to reschedule; the application's job is to be restartable.

---

## Part 14: Interview One-Liners Quick Reference

A rapid-fire reference for recalling precise Borg concepts in an interview.
Each statement is calibrated to be exactly right — not oversimplified, not too long.

**On desired state:**
"Borg's core model: declare what you want (desired state) rather than what to do
(imperative commands). A reconciliation loop continuously compares actual to desired
and acts to close the gap. This is why the system is self-healing — no failure-specific
code needed."

**On two-phase scheduling:**
"Borg's scheduler runs feasibility filtering first (removes machines that cannot
physically run the task) and then scoring (ranks feasible machines by bin-packing,
spreading, data locality). A random subset of feasible machines is scored rather than
all of them — a scalability optimization from the 2015 paper."

**On CPU vs. RAM:**
"CPU is compressible: throttle a task's CPU usage and it slows down but stays running.
RAM is not compressible: if a task needs more RAM than its limit, the OS kills it
(OOM kill). This is why RAM limits must be set more conservatively than CPU limits."

**On Borg vs. Kubernetes:**
"Kubernetes is Borg made open-source and developer-friendly. Every core concept maps
directly. Three genuine improvements: label selectors (more flexible than string job
names), IP-per-pod (vs. port-per-task — simplifies networking), and pluggable components
(scheduler, runtime, networking are replaceable)."

**On BorgMaster:**
"The BorgMaster is a five-replica Paxos group. One replica is the leader and does
scheduling; the others replicate all state changes. Failover takes about 10 seconds.
All cluster state is kept in memory for performance; the Paxos log provides durability."

**On utilization:**
"Borg achieves 60-70% cluster utilization (vs. ~40-50% without it). The key mechanisms:
mixing serving jobs (diurnal traffic pattern — low at 3 AM) with batch jobs (fill the
slack at night), and resource reclamation (tasks that consistently use less than their
reservation get their slack lent to lower-priority tasks)."

**On Borglet:**
"The Borglet is an agent running on every machine. It starts and stops tasks, manages
resources, and reports state to BorgMaster. The Borglet polls BorgMaster rather than
receiving push notifications — pull-based polling means one dead Borglet is a local
problem, not a broadcast failure."

**Decision tree — when to cite Borg in an interview:**
"Any time the interviewer asks about: cluster management, container orchestration,
resource scheduling, self-healing systems, or how Kubernetes works — Borg is the
historical foundation worth mentioning. Don't just say 'use Kubernetes'; explain which
Borg/Kubernetes concepts address the specific requirement."

---

## Part 15: Pre-Interview Drill

### 15.1 Five Concepts to Explain in 60 Seconds Each

Practice these until you can say each one clearly, without notes, in under 60 seconds.

**1. Desired state and reconciliation:**
"Borg uses a desired state model: engineers declare the target configuration (10 replicas
of service X, each needing 2 CPU and 4 GB RAM). A reconciliation loop continuously
compares the actual cluster state to the desired state and acts to close any gap. If a
machine fails and 3 replicas die, the loop sees 'actual=7, desired=10' and schedules 3
new replicas. If an engineer accidentally sets desired to 0, the loop kills all replicas.
The loop doesn't know why the states diverged — it just acts. This is why Kubernetes
is self-healing without explicit failure-handling code."

**2. Two-phase scheduling:**
"Borg uses two-phase scheduling. Phase 1 (feasibility filtering) removes every machine
that cannot possibly run the task: not enough CPU, not enough RAM, wrong hardware,
maintenance mode. Phase 2 (scoring) ranks the remaining feasible machines on multiple
criteria: bin-packing score (pack tasks tightly to free up full machines), spreading
score (don't put all tasks on one rack), and data locality (run tasks near their input
data). A random subset of feasible machines is scored rather than all of them — too
many feasible machines to score exhaustively at scale."

**3. CPU is compressible, RAM is not:**
"CPU overuse causes throttling: the kernel limits how much CPU time the container gets.
The task slows down but keeps running. RAM overuse causes an OOM kill: the kernel
terminates the process immediately. The operational implication: you can set CPU limits
aggressively (a task using more CPU than expected just runs slower) but RAM limits must
be set conservatively (a task hitting the RAM limit dies and loses all in-flight work).
Always pad RAM limits by 20-30% to account for GC pressure and memory spikes."

**4. BorgMaster Paxos architecture:**
"The BorgMaster is a five-node Paxos group. One node is the leader and processes all
scheduling decisions and state changes. Every state change is written to the Paxos log
before acting on it. The other four replicas replay the log and stay ready to take over.
All state is kept in memory for speed — the log provides durability. If the leader fails,
Paxos elects a new leader within ~10 seconds, and the new leader reconstructs in-memory
state by replaying the log. Borglets (on each machine) poll the BorgMaster for work —
this pull model means a single dead machine doesn't cause cascading BorgMaster load."

**5. The Borg → Kubernetes mapping:**
"Every Kubernetes concept has a direct Borg equivalent. Kubernetes Deployment = Borg
Job. Kubernetes Pod = Borg Task (with a key improvement: one Pod can have multiple
containers sharing a network namespace — equivalent to Borg's Alloc). kubelet = Borglet.
The Kubernetes control plane = BorgMaster. YAML spec = BCL config. The three genuine
Kubernetes improvements over Borg: (1) label selectors replace string name coupling,
(2) IP-per-pod replaces port-per-task for cleaner networking, (3) open-source with REST
API replaces internal-only with proprietary BCL."

### 15.1a Interview Self-Check — Borg

Before your interview, run through this checklist cold (without looking at notes):

**Architecture:**
- [ ] What does BorgMaster do? How many replicas? Why Paxos?
- [ ] What does a Borglet do? Pull or push communication?
- [ ] What is the Fauxmaster? Why is it useful?
- [ ] How does BorgMaster recover from a leader failure?

**Scheduling:**
- [ ] What are the two phases of Borg scheduling?
- [ ] What does feasibility filtering check?
- [ ] What criteria are used in the scoring phase?
- [ ] Why score a random subset rather than all feasible machines?

**Resources:**
- [ ] What is a compressible resource? Give an example.
- [ ] What is a non-compressible resource? What happens when you exceed its limit?
- [ ] What is the difference between resource request and resource limit?
- [ ] What is resource reclamation?

**Desired state:**
- [ ] What does the reconciliation loop do?
- [ ] Why is desired state better than explicit failure handlers for cluster management?
- [ ] What is a limitation of the desired state model? How does Borg mitigate it?

**Numbers:**
- [ ] What utilization does Borg achieve? What was utilization without Borg?
- [ ] How long does BorgMaster failover take?
- [ ] How many priority tiers does Borg have (approximately)?
- [ ] What is the publication date of the Borg paper?

**Kubernetes mapping:**
- [ ] Borg Job → Kubernetes ___?
- [ ] Borg Task → Kubernetes ___?
- [ ] Borglet → Kubernetes ___?
- [ ] BCL → Kubernetes ___?
- [ ] Name the three genuine Kubernetes improvements over Borg.

If you can answer all of these without hesitation, you are ready for any Borg question.

### 15.2 Three Questions That Expose Depth

**Q: "Borg uses a reconciliation loop. What are the failure modes of this approach?"**

Answer: Three main failure modes. First, the loop acts on any divergence including
operator error — accidentally setting desired replicas to 0 immediately kills all
replicas with no confirmation. Mitigation: change rate limits, Fauxmaster dry-run,
validation webhooks. Second, the loop is not instantaneous — between a failure and
the loop's next iteration, the system is diverged. This "reconciliation lag" means
brief periods where desired ≠ actual. For sub-second SLAs, this lag matters. Third,
the loop can thrash: if a task consistently fails to start (bad binary, insufficient
resources), the loop keeps rescheduling it. Exponential backoff (CrashLoopBackOff in
Kubernetes) prevents thrashing.

**Q: "How does Borg handle a scheduling decision that takes longer than the task's
startup window?"**

Answer: Borg's scheduler is asynchronous and non-blocking. While the scheduler is
working on task placement, other tasks continue to be processed. The BorgMaster
maintains a work queue; the scheduler pulls from it and commits placements as it
completes them. If a single very large job (10,000 tasks) were processed sequentially,
it would block all other scheduling. Borg avoids this by processing jobs concurrently
(multiple scheduling goroutines) and by randomizing the subset of machines scored
rather than waiting for a full cluster scan.

**Q: "What happens when two resource-intensive batch jobs are submitted simultaneously
and there isn't enough capacity for both?"**

Answer: Borg uses quota and priority to resolve this. Each job has a declared priority
and the team has an allocated quota (maximum resource units they can consume). If both
jobs together exceed the team's quota, one is rejected or queued. If they belong to
different teams with different priority levels, the higher-priority job's tasks proceed;
the lower-priority job's tasks wait in the queue (or are preempted if already running).
If both are the same priority and total within quota, they share the available capacity
proportionally based on scheduling order. No job is silently starved — the quota and
priority system makes resource contention explicit and auditable.

---

## Common Interview Mistakes — Reference Table

| Mistake | What the Candidate Says | What They Should Say |
|---------|------------------------|----------------------|
| **Attributing desired state to Kubernetes** | "Kubernetes invented the declarative reconciliation model" | "Borg introduced desired state and the reconciliation loop; Kubernetes inherited and extended it" |
| **Conflating CPU and RAM enforcement** | "If a task uses too many resources, it gets killed" | "CPU is throttled (compressible); RAM causes OOM kill (non-compressible). Different enforcement, different operational risk." |
| **Shallow scheduling description** | "The scheduler finds a node with enough resources" | "Two-phase scheduling: feasibility filtering removes infeasible machines, scoring ranks feasible ones by bin-packing, data locality, and spreading. Random subset for performance at scale." |
| **Explicit failure handling framing** | "When a machine fails, Kubernetes detects the failure and reschedules pods" | "There is no failure-specific code. The reconciliation loop handles machine failures the same as any other 'actual != desired' condition." |
| **Missing utilization numbers** | "Borg significantly improves utilization" | "~20 percentage point improvement (40-50% → 60-70%), primarily from mixing serving jobs (diurnal) with batch jobs (fills their slack) and resource reclamation." |
| **"Just use Kubernetes" without depth** | "I'd use Kubernetes for this" | Explain which K8s components map to which design requirements, the failure modes, the scaling limits, and the tuning decisions relevant to the specific problem. |

---

## Exercises

These exercises help you internalize Borg's concepts through active practice.

**Exercise 1: Draw the reconciliation loop for a specific scenario.**
Consider: you have a Kubernetes Deployment with 10 replicas. 3 nodes fail
simultaneously. Draw the observe-diff-act loop step by step, including: what the
controller observes, what the diff produces, what actions it takes, and what happens
if the replacement pods keep failing (hint: think about exponential backoff).

**Exercise 2: Priority analysis.**
Your cluster has a machine with 8 CPUs. Running on it: Task A (production, 4 CPUs),
Task B (batch, 3 CPUs), Task C (batch, 1 CPU). A new task arrives: Task D (production,
needs 5 CPUs). What does Borg do? Which tasks are preempted? What if Task D needed
10 CPUs? Draw the before and after machine state.

**Exercise 3: Design the scoring function.**
You are designing a scoring function for a cluster scheduler. You care about:
(1) high machine utilization, (2) spreading job tasks across racks, (3) data locality.
These three objectives conflict. Define the scoring function as a weighted sum. What
happens if you set the bin-packing weight to 10x the spreading weight? What workloads
break? How would you tune it differently for serving jobs vs. batch jobs?

**Exercise 4: Resource request sizing.**
A web server process has the following observed CPU usage (sampled every minute over
24 hours): median 0.8 CPU, 90th percentile 1.5 CPU, 99th percentile 3.2 CPU, max 4.8 CPU.
What should you set as (a) the CPU request, (b) the CPU limit? Justify your answer
considering both utilization efficiency and serving reliability. What are the failure
modes if you get each wrong?

**Exercise 5: BorgMaster failover analysis.**
Draw a timeline of what happens when the BorgMaster leader fails while scheduling a
task. Include: which replicas are affected, the Paxos election process, state
reconstruction from the Paxos log, and the first scheduling decision the new leader
makes. What is the minimum time from failure to first new scheduling decision?

**Exercise 6: Bin-packing problem.**
You have 5 tasks with (CPU, RAM) requirements: A(2,8), B(4,4), C(1,2), D(3,6), E(2,4).
You have machines with capacity (8 CPU, 16 GB RAM). Using a first-fit-decreasing
algorithm for CPU and RAM, what is the minimum number of machines needed? Show your
placement. Now find a placement that uses fewer machines (if possible). What is the
theoretical minimum?

**Exercise 7: The preemption cascade.**
A team accidentally assigns their 500-task MapReduce job to "production" priority instead
of "batch." The cluster is at 75% utilization. Trace through what happens: which tasks
are preempted, in what order, and what the recovery looks like when the priority is
corrected. How would you prevent this accident in the first place?

**Exercise 8: Kubernetes component mapping.**
A new pod is submitted to a Kubernetes cluster via `kubectl apply`. Trace its journey
from kubectl to running container: which component receives the YAML, where it is stored,
which component schedules it, which component starts it, and which loops are running
at each step. Map each Kubernetes component to its Borg equivalent.

---

## Homework

**Homework 1: Read the Primary Source**
Read the EuroSys 2015 Borg paper: "Large-scale cluster management at Google with Borg"
by Verma et al. Focus on Sections 2 (user perspective), 3 (architecture), 5 (utilization),
and 8 (lessons learned). Take notes on: (a) one design decision you disagree with,
(b) one design decision you would copy in your own systems, and (c) one open question
the paper raises but doesn't answer.

**Homework 2: Trace a Kubernetes Reconciliation Loop**
Set up a local Kubernetes cluster (minikube or kind). Create a Deployment with 5 replicas.
Manually delete 2 pods with `kubectl delete pod`. Observe using `kubectl get pods -w`
as the reconciliation loop detects the missing pods and creates replacements. Then look
at the Deployment controller source code in the Kubernetes repository (find
`pkg/controller/deployment/deployment_controller.go`). Identify the observe-diff-act
pattern in the code.

**Homework 3: Implement a Mini Reconciliation Loop**
Write a program (any language) that implements a simplified reconciliation loop for
a hypothetical service. Define: (a) a desired state struct (e.g., `{name: "web-server",
replicas: 5}`), (b) an actual state that starts correct, (c) a loop that checks actual
vs desired every 5 seconds and logs when they differ. Then simulate failures by
randomly removing replicas from actual state. The loop should detect and "repair" the
discrepancy by adding replicas back. Extend it to add exponential backoff when a
replica fails to start.

**Homework 4: Utilization Analysis**
Take any production system you have access to (or use a cloud provider's metrics for
a VM you control). Measure CPU and RAM utilization at the process level over 24 hours.
Calculate: (a) the ratio of average utilization to reserved capacity, (b) the ratio
of peak utilization to reserved capacity, (c) how much capacity could theoretically
be reclaimed without violating the 99th percentile utilization. What would you set
as the Kubernetes resource request and limit for this process?

**Homework 5: Design Review — Priority Preemption Policy**
You are designing the priority preemption policy for a multi-tenant cluster scheduler.
Write a 1-2 page design doc covering: (a) how many priority tiers you would have and
what each represents, (b) which tiers can preempt which other tiers, (c) how to
prevent priority abuse (teams inflating their priorities), (d) what happens when a
preemption cascade begins and how to detect and stop it, (e) how to ensure the
preemption policy is auditable (you can always answer "who preempted my task and why").

---

## KEY TAKEAWAYS

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    CHAPTER 99: BORG — KEY TAKEAWAYS                        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  1. DESIRED STATE + RECONCILIATION LOOP is the core insight.                ║
║     Declare what you want. Borg continuously makes the cluster match it.     ║
║     This is WHY Kubernetes is self-healing — not magic, just a loop.        ║
║                                                                              ║
║  2. TWO-PHASE SCHEDULING: Feasibility filtering removes machines that        ║
║     cannot run the task. Scoring ranks feasible machines by bin-packing,     ║
║     data locality, and spreading. A random subset is scored for performance. ║
║                                                                              ║
║  3. CPU IS COMPRESSIBLE (throttle); RAM IS NOT (OOM kill).                  ║
║     Under-limiting CPU → task runs slow.                                    ║
║     Under-limiting RAM → task dies. Be more careful with RAM limits.        ║
║                                                                              ║
║  4. UTILIZATION: ~60-70% achieved (vs 40-50% without Borg) by mixing        ║
║     serving jobs (diurnal traffic) with batch jobs (fill the slack at 3 AM).║
║     Resource reclamation is the mechanism.                                  ║
║                                                                              ║
║  5. BORGMASTER is 5-replica Paxos, in-memory state, ~10s failover.          ║
║     Borglets poll BorgMaster. Pull-based, not push, for resilience.         ║
║                                                                              ║
║  6. KUBERNETES IS BORG: every concept maps directly.                        ║
║     Job→Deployment, Task→Pod, Alloc→Pod (multi-container), Borglet→kubelet, ║
║     BorgMaster→control plane, BCL→YAML. Three key improvements:             ║
║     label selectors (not named jobs), IP-per-pod (not port-per-task),       ║
║     pluggable/open-source components (not monolithic internal system).      ║
║                                                                              ║
║  7. PREEMPTION by design: higher-priority tasks evict lower-priority ones.  ║
║     Tasks must be written to handle sudden death at any time → checkpoint.  ║
║                                                                              ║
║  8. THE RECONCILIATION MODEL APPLIES EVERYWHERE: database replication,      ║
║     autoscaling, GitOps, load balancer health management. Any self-healing  ║
║     system should start with desired state + reconciliation loop.           ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  THE PAPER: Verma et al., "Large-scale cluster management at Google         ║
║  with Borg," EuroSys 2015. READ IT. Memorize the numbers.                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## Pairs With

- **Chapter 86: Chubby** — Google's distributed lock service, used for BorgMaster
  leader election (the "Paxos election" in Borg uses Chubby under the hood)
- **Chapter 84: MapReduce** — the canonical Borg batch workload; understanding
  MapReduce's fault tolerance model (task-level retries) explains why Borg's
  preemption model works for batch jobs
- **Chapter 87: GFS/Colossus** — Google's distributed file system, the storage layer
  that Borg's data-locality-aware scheduling interacts with
- **Chapter 88: Kubernetes Internals** — the open-source implementation of these
  ideas, covered in depth with current API and implementation details

---

---

## What to Read Next

- **Ch47 — Kubernetes Internals**: The open-source descendant of Borg, covered in depth.
  Every concept from this chapter maps to a Kubernetes equivalent; Ch47 shows the actual
  implementation, API design, and operational patterns.

- **Ch100 — Video Streaming (Staff)**: Demonstrates Borg/Kubernetes concepts in context
  — a real system where transcoder worker pools, auto-scaling, and preemptible spot
  instances directly apply Borg's resource management principles.

- **Ch45 — Google's Foundational Systems**: Overview of how Borg fits alongside GFS,
  Bigtable, Chubby, and MapReduce in Google's infrastructure stack. Read to understand
  the broader ecosystem Borg operates in.

- **Ch48 — Consensus Deep Dive**: The Paxos algorithm that powers BorgMaster's five-replica
  replicated state machine. Understanding Paxos clarifies why BorgMaster achieves ~10s
  failover and why it needs exactly 5 replicas (not 3, not 7).

---

*Chapter 99: Borg — Google's Cluster Manager*
*Primary source: Verma et al., EuroSys 2015 | Section 6: Google Systems Papers*
*Parts: 1-15 + Common Interview Mistakes + Exercises + Homework + Key Takeaways*
*Last updated: 2026-06-25*

---

## Interview Simulation — Borg (Google's Cluster Manager)

*45-minute deep-dive interview on Google's Borg paper (Verma et al., EuroSys 2015). Interviewers expect you to understand the desired-state reconciliation loop, two-level scheduling, resource compressibility, and how Kubernetes inherited and diverged from Borg's design.*

### Phase 1: System Overview and Motivation (10 min)

> **Interviewer:** What is Borg and what problem was Google solving in the early 2000s?

**Candidate:** Borg is Google's internal cluster management system — it runs all of Google's workloads across hundreds of thousands of machines in multiple datacenters. Before Borg, Google ran two separate management systems: one for long-running services (like web serving) and one for batch jobs (like MapReduce). The problem was cluster fragmentation: the service cluster was over-provisioned to handle peak traffic, sitting mostly idle at night; the batch cluster was a separate pool that couldn't use the unused service capacity. Borg unified these two workload types into one system, letting batch jobs use the slack capacity in service machines. This is the "utilization win" the paper reports: mixing latency-sensitive production workloads with best-effort batch workloads on the same machines raises average utilization from ~40% to ~60%+ while keeping service tail latency acceptable.

The key design insight: not all resources are equal. CPU is compressible — if a batch job uses too much CPU, you can throttle it without killing it. Memory is non-compressible — if a process uses too much memory, there's no graceful throttle; you must kill it. This distinction drives Borg's entire resource management philosophy.

> **Interviewer:** Explain the desired-state reconciliation loop at the heart of Borg.

**Candidate:** Borg is a control loop system. The desired state — "run 10 replicas of this service with these resource requirements" — is stored in BorgMaster's in-memory state (backed by Paxos). The actual state — what's actually running on Borglets — is observed continuously. The reconciliation loop continuously computes the delta between desired and actual and takes actions to close it: scheduling new tasks, restarting failed tasks, preempting low-priority tasks to make room for high-priority ones.

This is fundamentally different from imperative scheduling ("deploy task X to machine Y"). With desired-state reconciliation, you never need to track what commands you sent — you only track the goal state. If a machine crashes and three tasks die, the loop automatically schedules three replacements. If a network partition causes the master to lose contact with some tasks, the loop reconciles when contact is restored. Kubernetes inherited this exact architecture — the controller manager runs reconciliation loops for Deployments, ReplicaSets, Services, etc.

---

### Phase 2: Key Design Decisions (15 min)

> **Interviewer:** Describe the two-level scheduling in Borg.

**Candidate:** Borg uses a two-level architecture: BorgMaster handles job and task state, while Borglets handle local resource management on each machine.

```
Borg Two-Level Scheduling Architecture
========================================

                    [BorgMaster]
                   /      |      \
            [Scheduler]  [State]  [Paxos replicas x5]
                  |
    [Feasibility check: which machines can run this task?]
    [Scoring: which of those machines is best?]
                  |
    Assigns task → specific machine
                  |
           [Borglet] on each machine
                  |
    Accepts/rejects task assignment
    Reports actual resource usage to BorgMaster every ~5s
    Can kill tasks that exceed non-compressible resource limits
    Manages cgroups for CPU/memory enforcement

Score components:
  - E-PVM (spreading tasks across failure domains)
  - Minimizing stranded resources (don't leave machines with tiny unusable slices)
  - Pack to empty machines when possible (save spread-out machines for large tasks)
```

The scoring function is where most of Borg's operational complexity lives. "Best fit" (pack tasks densely) minimizes the number of active machines but leaves machines with small resource fragments that can't fit any new task. "Worst fit" (spread tasks evenly) wastes more machines but keeps resource fragmentation low. Borg uses a hybrid: pack small tasks, spread large ones. The paper reports that the scoring function accounts for most of the system's engineering iteration over a decade.

*(Cross-question: what is the difference between BorgMaster and Borglet?)* BorgMaster is the cluster-level brain: it stores desired state, runs the scheduler, and exposes the API. Borglet is the per-machine agent: it runs on every machine, receives task assignments from BorgMaster, manages actual process lifecycle, and reports resource usage back. Borglet has limited intelligence — it follows orders and reports status. BorgMaster has the full picture and makes all scheduling decisions.

> **Interviewer:** How does Borg handle priority and preemption?

**Candidate:** Borg uses a global priority scale from 0 to ~450. Production workloads (serving traffic) typically run at priority 330+. Batch jobs run at 0-115. Monitoring infrastructure runs at 360+. A task can only preempt tasks with strictly lower priority — never same or higher.

Preemption mechanics: when BorgMaster needs to schedule a high-priority task and no machine has sufficient free resources, it identifies machines where evicting low-priority tasks would create enough space. It sends SIGTERM to the low-priority tasks (giving them time to checkpoint if they support it), waits for graceful shutdown, then assigns the machine to the high-priority task. The evicted tasks are re-queued and will be scheduled elsewhere when capacity is available.

The non-compressible resource protection: if a production task and a batch task are co-located and the production task's memory usage spikes, Borglet kills the batch task immediately (SIGKILL) to free memory for production. Memory over-limit kills are instantaneous — there's no negotiation. CPU over-limit just throttles the task (compressible). This is exactly why Kubernetes has separate CPU limits (throttled) and memory limits (OOM-killed) with these different behaviors.

---

### Phase 3: Trade-offs and Alternatives (10 min)

> **Interviewer:** The Borg paper reports high machine utilization. What's the catch?

**Candidate:** The utilization numbers are real but come with several hidden costs. First, tail latency interference: batch jobs running on service machines can cause cache pollution and memory bandwidth contention, increasing p99 latency for production services. Borg mitigates this with CPU throttling and memory limits, but co-location interference is real and hard to fully eliminate. Google invested heavily in hardware (cache partitioning, NUMA-aware scheduling) and software (resource isolation via cgroups) to make co-location practical. At other companies without that investment, co-location risks are higher.

Second, the "credits" problem: high utilization means low slack. When a large batch job (e.g., a model training run) submits thousands of tasks simultaneously, there may not be enough idle capacity to schedule them without preempting other batch work. Borg uses gang scheduling for tasks with hard co-scheduling requirements (all-or-nothing placement) which can reduce effective utilization when the cluster is nearly full.

Third, operational complexity: running production services and batch jobs on the same machines requires extremely tight resource enforcement. A bug in Borglet's cgroup enforcement has caused production incidents at Google where a batch job ate production service memory.

> **Interviewer:** How does Kubernetes differ from Borg, and what was deliberately left out of Kubernetes?

**Candidate:** Kubernetes was designed by ex-Googlers who knew what they'd do differently. Key differences: Kubernetes uses Pods (groups of co-scheduled containers sharing a network namespace) as the scheduling unit; Borg uses Tasks (single binaries). Kubernetes externalizes everything as API resources — Deployments, Services, ConfigMaps — making it extensible via the API server; Borg's API is internal and monolithic. Kubernetes uses etcd (open-source Raft-based storage) instead of a custom Paxos implementation.

What was deliberately left out of Kubernetes v1: the sophisticated scoring function (Borg has 10+ years of tuning; Kubernetes started simple and added the scheduler framework over time), gang scheduling for tightly-coupled jobs (Kubernetes initially had no concept of "schedule all of these pods together or not at all" — added later via gang plugins), and resource over-commitment (Kubernetes requests/limits exist but the sophisticated batch-vs-service mixing with preemption took years to mature). The design philosophy shift: Kubernetes prioritized extensibility and open-source adoption over replicating every Borg optimization on day one.

---

### Phase 4: Modern Application (10 min)

> **Interviewer:** Your company is migrating from a bespoke deployment system to Kubernetes. What Borg concepts should you map explicitly, and where will the migration be hardest?

**Candidate:** The easy mappings: Jobs → Deployments or StatefulSets. Task priority → Kubernetes PriorityClasses. Borglet → kubelet. BorgMaster → kube-apiserver + kube-scheduler + controller-manager. Alloc sets (resource reservations) → ResourceQuotas and LimitRanges.

The hard mappings: Borg's gang scheduling (required for distributed training jobs) → Kubernetes doesn't support this natively; you need a scheduler plugin like Volcano or the Coscheduler. Borg's resource reclamation (lending unused reserved resources to batch jobs) → Kubernetes has this via VPA (Vertical Pod Autoscaler) and the resource over-commitment via requests vs. limits, but it requires careful tuning to avoid OOM cascades. Borg's cell architecture (cells of ~10,000 machines) → Kubernetes clusters of this size are operationally complex; many companies run multiple smaller clusters with federation rather than one Borg-sized cluster.

The hardest migration: operational muscle memory. Borg teams debug issues using Borg-specific tools (borgcfg, dremel queries on Borg logs). Kubernetes tooling (kubectl, Prometheus, Grafana) is different enough that the operational team needs retraining, and institutional knowledge about "why did task X get preempted at 3am" is rebuilt from scratch.

> **Interviewer:** If you had to add one feature from Borg to Kubernetes today, what would it be and why?

**Candidate:** Resource reclamation. Borg can observe that a task requested 8GB of memory but is actually using 3GB, and lend the unused 5GB to batch jobs — reclaiming it immediately if the production task's usage rises. Kubernetes has a weaker version (requests vs. limits), but it doesn't do dynamic reclamation based on observed usage. The result: Kubernetes clusters are typically run at 60-70% reservation utilization (not actual utilization) to leave headroom for bursts, because there's no safe way to temporarily use the slack.

Adding proper reclamation (with guaranteed eviction of batch tasks the moment production needs the resources) would let Kubernetes clusters operate at Borg-like utilization ratios. This would meaningfully reduce cloud costs for large deployments. The Kubernetes SIG-Node has open proposals for this ("in-place resource resize" and "memory-backed batch scheduling") but they're incomplete as of 2026. The engineering challenge is getting the eviction latency low enough that production services don't notice the resource take-back.

---

### Common Cross-Questions and Strong Answers

**Q: What is a Borg "alloc" and how does it relate to Kubernetes namespaces?**

A: An alloc (allocation) in Borg is a reserved set of resources on a machine — a slice of that machine's CPU and memory that tasks can be placed into. Allocs were used to reserve capacity for future tasks or to group related tasks together. They don't map directly to Kubernetes namespaces; namespaces are organizational (multi-tenancy, RBAC boundaries) not resource reservations. The closer Kubernetes analog is a ResourceQuota (limits total resources within a namespace) combined with a Pod requesting specific resources. The concept of "reserved capacity" in Kubernetes is handled at the node level via allocatable resources and at the cluster level via resource pools and node affinity.

**Q: How does BorgMaster achieve high availability?**

A: BorgMaster runs as five Paxos-replicated replicas. One replica is elected master (using the Paxos leader election); all writes go to the master, which replicates them to a majority of replicas before acknowledging. If the master crashes, a new leader is elected (Paxos leader election takes ~10 seconds). During those 10 seconds, Borglets continue running their assigned tasks without interruption — the cluster doesn't stop because the master is unavailable. New task scheduling and preemption decisions pause. This "fail local, not global" property is critical: a BorgMaster failure is invisible to end users of the services Borg is running.

**Q: What is the difference between a Borg Job and a Borg Task?**

A: A Job is the unit of submission — it contains a task specification and a count (e.g., "run 100 copies of this binary with these resource requirements"). A Task is one instantiation of that specification — one process on one machine. Jobs represent the desired state; Tasks are the actual running instances. The scheduler's job is to map Tasks to Borglets. When a Task fails (machine crash, OOM kill), BorgMaster creates a replacement Task from the Job specification and schedules it on an available machine. Kubernetes's equivalent: a Deployment (Job) and a Pod (Task). The ReplicaSet controller continuously reconciles the Deployment's replica count against the number of running Pods — exactly the Borg reconciliation loop.

---

<!-- END OF CHAPTER 99 -->
<!-- Additions over base 2,125 lines: Parts 12-15 (Omega evolution, gang scheduling,
     interview one-liners, pre-interview drill), fixed chapter number in KEY TAKEAWAYS,
     added What to Read Next section, added interview self-check checklist. -->
<!-- Key concepts: desired state, reconciliation loop, two-phase scheduling,
     compressible vs non-compressible resources, Paxos BorgMaster, Borg→K8s mapping -->
*Pairs with: Ch84 (MapReduce), Ch86 (Chubby), Ch87 (GFS), Ch88 (Kubernetes)*
