# Distributed Scheduler: Heartbeats and Guarantees

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

An alarm clock app. You set 7 AM. It MUST ring at 7 AM. Not 7:05. Not twice. Not never. One ring. Right time. Scale that: 100 million alarms. Millions of users. Stored across thousands of servers. A server crashes. Its alarms must be rescheduled. Another server picks them up. That's a distributed scheduler. Let's see how it works.

---

## The Story

Schedulers run jobs at the right time. Cron. "Every day at midnight." Or one-shot. "Run at 3 PM." Simple on one machine. Hard across many. Requirements: execute at the right time (precision), exactly once (no duplicates, no misses), survive failures (durability). One scheduler node crashes. Its jobs? Orphaned. Unless another node picks them up. How? Heartbeats. "I'm alive." No heartbeat? Node is dead. Reassign its jobs. The heartbeat is the signal. The absence of heartbeat is the trigger. Design for it. Monitor it. Get it wrong, and you double-execute. Or never execute. Both are bad. Payment ran twice. Refund never sent. Schedulers are critical infrastructure. Treat them that way.

---

## Another Way to See It

Think of a taxi dispatcher. Drivers call in. "I'm available." Heartbeat. Dispatcher assigns rides. Driver goes quiet. No call. Dispatcher waits. 5 minutes. "Driver 7 is gone." Reassign their pending rides to other drivers. The heartbeat is the "I'm here" call. No heartbeat = assume gone. Reassign. Same with scheduler nodes. "I'm processing job X." Heartbeat. No heartbeat? Job X might be stuck. Another node claims it. Retries. The dispatcher (scheduler) tracks who's alive. Who has what. Reassigns when someone goes quiet. Distributed systems are taxi fleets. Heartbeats are the radio.

---

## Connecting to Software

**Architecture.** Job store: database. job_id, scheduled_time, status (pending/running/completed), claimed_by, claimed_at. Scheduler nodes: processes that poll the store. "Give me jobs due now and not claimed." Claim a job: UPDATE SET status='running', claimed_by='node-3', claimed_at=NOW() WHERE job_id=X AND status='pending'. Atomic. Use row-level lock or compare-and-set. Only one node wins. Others see status='running'. Skip. Node executes. Marks complete. Or fails. Marks failed. Retry logic. The claim is the distributed lock. Whoever wins the claim runs the job.

**Leader vs peer.** Leader-based: one scheduler is leader. Only leader claims jobs. Others standby. Leader dies? Election. New leader. Simple. Single point of execution. Peer-based: all schedulers compete. All try to claim. First to claim wins. No leader. More concurrent. But: thundering herd. Many nodes try to claim the same job. Use random jitter. Or shard jobs by ID. Node 1 claims job_id % 3 == 0. Node 2 claims % 3 == 1. Node 3 claims % 3 == 2. Reduce contention. Both models work. Choose based on scale and simplicity needs.

**Heartbeats.** Scheduler nodes send "I'm alive" periodically. Every 10 seconds. Store: last_heartbeat per node. Background process: "Nodes with last_heartbeat > 30 seconds ago are dead." Reclaim their jobs. UPDATE status='pending', claimed_by=NULL WHERE claimed_by='dead-node'. Now other nodes can claim. Heartbeat interval vs timeout. 10s heartbeat, 30s timeout. Node has 3 missed heartbeats before declared dead. Network blip? One missed. OK. Sustained failure? Declared dead. Reassign. Tune the numbers. Too aggressive: false positives. Reassign jobs from live nodes. Double execution. Too passive: long window. Jobs stuck. No execution. Balance. 3x heartbeat = timeout is a common heuristic.

---

## Let's Walk Through the Diagram

```
DISTRIBUTED SCHEDULER
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   JOB STORE (DB)              SCHEDULER NODES                    │
│   job_id, time, status           │                               │
│        │                         │                               │
│        │  Poll: jobs due?         │  Node 1: heartbeat ──► alive  │
│        │◄────────────────────────┤  Node 2: heartbeat ──► alive  │
│        │                         │  Node 3: no heartbeat ──► DEAD│
│        │  Claim (atomic)         │                               │
│        │  Node 1 wins job X      │  Reclaim Node 3's jobs        │
│        │                         │  status=pending, claimed_by=null│
│        │  Execute ──► Complete   │                               │
│                                                                  │
│   HEARTBEAT: 10s interval. 30s timeout. Dead = reclaim jobs.     │
│   CLAIM: Atomic UPDATE. Only one node wins. No double-exec.     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Job store holds pending jobs. Scheduler nodes poll. "Jobs due now?" Node 1 claims job X. Atomic update. Node 2 sees it claimed. Skips. Node 1 executes. Marks complete. Node 3 stops heartbeating. Timeout. Reclaimer process marks Node 3 dead. Reclaims its jobs. Other nodes can now claim them. The heartbeat is the liveness signal. The claim is the mutual exclusion. Together: exactly-once execution across failures. The diagram captures it. Implementation details vary. The principles hold.

---

## Real-World Examples (2-3)

**Kubernetes CronJobs.** Built-in scheduler. Jobs stored in etcd. Kube-scheduler assigns. Nodes run. Node dies? Pod rescheduled. Heartbeats: node status. Proven. Scale: thousands of nodes. The pattern is standard.

**Celery Beat.** Python. Distributed task scheduling. Redis or DB for state. Workers claim tasks. Heartbeats. Used by many. Django apps. Async task execution. Reliable. Not perfect. But good enough for most.

**Temporal.** Workflow engine. Durable execution. Schedulers built in. Exactly-once semantics. Heartbeats for activity workers. If worker dies mid-activity, activity is retried. Modern. Cloud-native. The future of durable execution. Worth learning.

---

## Let's Think Together

**"Scheduler claims a job, starts executing, but crashes before completion. How does the system know to retry?"**

Heartbeat stops. Node is declared dead (after timeout). Reclaimer process: "Node X hasn't heartbeaten in 30 seconds. Reclaim its jobs." Jobs with claimed_by=Node X: set status= pending, claimed_by=NULL. Now other nodes can claim. Job runs again. Retry. But: what if the job actually completed? Applied side effects. Then node crashed before marking complete. Retry = double execution. Payment runs twice. Problem. Solution: idempotency. Jobs must be safe to retry. Idempotency key. "Payment for order 123." Retry? Check. Already paid? Skip. Or: two-phase. Job does work. Writes to "pending" store. Separate process commits. If node dies after work, before commit, retry does work again. Idempotency handles it. Design jobs for retry. Assume they will retry. Make it safe. Heartbeat tells you when. Idempotency makes retry safe.

---

## What Could Go Wrong? (Mini Disaster Story)

A payment processor. Scheduler. Runs "process refund" jobs. Node claims job. Starts. Connects to bank API. Initiates refund. Node crashes. Before marking job complete. Heartbeat stops. Job reclaimed. Another node claims. Runs again. Connects to bank. Initiates refund. Same refund. Twice. Customer gets double refund. Company loses money. Postmortem: "Why did it run twice?" No idempotency. Refund ID wasn't checked. "Already refunded for this order?" Should have been. Wasn't. Fix: idempotency key. order_id + "refund". Before refund: check. Done? Skip. Not done? Do it. Record. Scheduler retry is guaranteed. Your job logic must handle it. Idempotency. Always. For any job with side effects. Assume retry. Design for it. The heartbeat gives you retries. Idempotency makes them safe.

---

## Surprising Truth / Fun Fact

Google's Borg—the precursor to Kubernetes—had a scheduler that handled millions of tasks. Jobs. Placement. Failover. Heartbeats. The design influenced everything that came after. Kubernetes. Mesos. The patterns are decades old. Proven at planetary scale. Your startup's cron might not need this. But when you scale to thousands of jobs, thousands of nodes, the same problems appear. Heartbeats. Claims. Reclamation. Learn from the giants. The solutions exist. Use them.

---

## Quick Recap (5 bullets)

- **Requirements:** Right time. Exactly once. Survive failures. Heartbeats enable the last.
- **Architecture:** Job store (DB) + scheduler nodes. Poll. Claim (atomic). Execute. Complete.
- **Heartbeats:** Nodes report "alive." No heartbeat = dead. Reclaim their jobs. Retry.
- **Claim:** Atomic UPDATE. Only one node wins. Prevents double execution. Distributed lock.
- **Idempotency:** Jobs will retry. Design for it. Idempotency key. Safe to run twice.

---

## One-Liner to Remember

**A distributed scheduler is an alarm clock that keeps ringing even when the clock breaks—heartbeats detect failures, reclaims trigger retries.**

---

## Next Video

Next: A/B testing, assignment consistency, and why the same user must always see the same variant.
