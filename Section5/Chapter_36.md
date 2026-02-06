# Chapter 36: Background Job Queue

---

# Introduction

Every production system has work that shouldn't block the user: sending a welcome email after signup, resizing an uploaded image, generating a PDF invoice, recalculating recommendation scores, or syncing data to a third-party API. A background job queue is the infrastructure that accepts this work, persists it, distributes it to workers, and ensures it completes reliably—even when workers crash, dependencies fail, or traffic spikes 10×.

I've built job queues that processed 50,000 jobs per minute across dozens of worker instances, debugged incidents where a poison-pill job crashed every worker that touched it (bringing the entire queue to a halt for 45 minutes), and designed retry policies that prevented a flaky third-party API from turning a 2-minute email delay into a 48-hour backlog. The lesson: a job queue that loses jobs or silently stops processing is worse than having no queue at all, because engineers assume the work is happening.

This chapter covers a background job queue as a Senior Engineer owns it: enqueueing, persistence, dispatching, execution, retry, monitoring, and the operational reality of keeping deferred work reliable at scale.

**The Senior Engineer's First Law of Job Queues**: A job queue must never silently lose work. If a job fails, that failure must be visible, retriable, and debuggable. Invisible failure is the worst kind of failure.

---

# Part 1: Problem Definition & Motivation

## What Is a Background Job Queue?

A background job queue accepts units of work (jobs) from producers, persists them durably, dispatches them to worker processes for execution, handles retries on failure, and provides visibility into job status. It decouples "requesting work" from "performing work" so that user-facing operations remain fast and the heavy lifting happens asynchronously.

### Simple Example

```
BACKGROUND JOB QUEUE OPERATIONS:

    ENQUEUE:
        User uploads a profile photo
        → API handler saves raw image to object storage
        → Enqueues job: {type: "resize_image", payload: {image_id: "abc123", sizes: [64, 256, 1024]}}
        → Returns 200 OK to user immediately (< 100ms)

    DISPATCH:
        Worker polls queue → receives job
        → Marks job as "processing" (leased)
        → Downloads raw image from object storage
        → Resizes to 3 sizes, uploads results
        → Marks job as "completed"
        → ACKs job (removed from queue)

    RETRY:
        Worker crashes mid-resize
        → Lease expires after 5 minutes
        → Job becomes visible again
        → Another worker picks it up
        → Resizes from scratch (idempotent: overwrites same output path)

    DEAD-LETTER:
        Job fails 5 times (e.g., corrupt image that crashes decoder)
        → Moved to dead-letter queue
        → Alert fires: "DLQ depth > 0"
        → Engineer investigates, fixes or discards
```

## Why Background Job Queues Exist

You cannot do everything in the request path. Some work is slow, unreliable, or not time-critical—and forcing it into a synchronous request degrades the user experience and couples your system's reliability to every downstream dependency.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WHY BUILD A BACKGROUND JOB QUEUE?                        │
│                                                                             │
│   WITHOUT A JOB QUEUE:                                                      │
│   ├── User waits while email sends (2-5 seconds, SMTP timeout)              │
│   ├── If email service is down, signup fails (unnecessary coupling)         │
│   ├── Image resize in request path: 3-10 second response times              │
│   ├── PDF generation blocks the API thread (resource starvation)            │
│   ├── Retry logic embedded in request handlers (complex, fragile)           │
│   └── No visibility: "Did the invoice get generated?" (nobody knows)        │
│                                                                             │
│   WITH A JOB QUEUE:                                                         │
│   ├── Request returns immediately; work happens in background               │
│   ├── Decoupled: Email service down? Jobs queue up, process when it's back  │
│   ├── Controlled concurrency: 10 workers, not 10,000 threads                │
│   ├── Built-in retry with backoff (no ad-hoc retry logic everywhere)        │
│   ├── Visibility: Job status, queue depth, processing rate (dashboards)     │
│   └── Prioritization: Urgent jobs before batch jobs                         │
│                                                                             │
│   KEY INSIGHT:                                                              │
│   A job queue is NOT a message broker (Kafka/RabbitMQ are different).       │
│   A message broker delivers messages; a job queue ensures work completes.   │
│   Job queues need: persistence, retry, dead-letter, status tracking,        │
│   and at-least-once execution guarantees.                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Problem 1: Synchronous Work Blocks User Experience

```
CHALLENGE:

User signs up for an account. After signup, the system must:
    1. Create database record (5ms)
    2. Send welcome email via SMTP (2 seconds, sometimes 30 seconds)
    3. Resize avatar (3 seconds)
    4. Sync to CRM (500ms, but flaky—times out 5% of the time)
    5. Generate onboarding PDF (4 seconds)

SYNCHRONOUS APPROACH:
    Total response time: 5ms + 2s + 3s + 500ms + 4s = ~10 seconds
    If CRM times out (5% of the time): 10s + 30s timeout = 40 seconds
    If SMTP is down: Signup fails entirely (user can't register)

    User experience: Terrible. 10-second signup, 5% chance of 40 seconds,
    and occasional total failure for reasons unrelated to account creation.

ASYNC APPROACH (Job Queue):
    Request: Create database record → enqueue 4 jobs → return 200 OK (15ms)
    Background: Workers process email, resize, CRM sync, PDF independently
    
    User experience: 15ms signup. Email arrives in 30 seconds. Avatar ready
    in 1 minute. CRM syncs within 5 minutes (with retries). PDF in 2 minutes.
    
    CRM down? Jobs retry with backoff. User never notices.
```

### Problem 2: Reliability Coupling

```
COUPLING PROBLEM:

Without a queue, your system's availability = product of all dependencies:
    API (99.9%) × SMTP (99.5%) × Image Service (99.9%) × CRM (99.0%)
    = 99.3% availability for signup

    0.7% failure rate = 7 out of every 1,000 signups fail
    At 10,000 signups/day = 70 failed signups/day

With a queue:
    Signup availability = API (99.9%) × DB (99.99%) = 99.89%
    Background work: Retried until successful
    
    Failed signups/day: ~11 (only real failures, not dependency flakiness)
```

### Problem 3: Resource Contention

```
RESOURCE PROBLEM:

100 concurrent image resize requests each use 200MB RAM:
    Peak memory: 100 × 200MB = 20 GB (OOM kill likely)
    
With a queue and 5 workers:
    Concurrent resizes: 5 × 200MB = 1 GB (bounded)
    Remaining 95 jobs: Queued, processed in ~2 minutes
    
    Job queue acts as a natural throttle on expensive operations.
    Without it, every traffic spike becomes a resource exhaustion incident.
```

---

# Part 2: Users & Use Cases

## User Categories

| Category | Who | How They Use the Job Queue |
|----------|-----|---------------------------|
| **Application services** | Backend services producing async work | Enqueue jobs via API/SDK |
| **Workers** | Processes consuming and executing jobs | Poll queue, process, report status |
| **Product engineers** | Developers defining job types and handlers | Define job schemas, write handler code |
| **On-call/SRE** | Reliability engineers | Monitor queue depth, DLQ, processing latency |
| **Operations/Support** | Internal staff investigating issues | Query job status, retry stuck jobs, inspect DLQ |

## Core Use Cases

```
USE CASE 1: DEFERRED WORK
    Trigger: User action (signup, upload, purchase)
    Jobs: Send email, resize image, generate receipt
    Expectation: Complete within seconds to minutes
    Priority: Normal (user expects eventual completion, not real-time)

USE CASE 2: SCHEDULED/PERIODIC WORK
    Trigger: Cron-like schedule (daily report, hourly aggregation)
    Jobs: Generate daily invoice summary, clean up expired sessions
    Expectation: Complete within the scheduled window
    Priority: Low (batch work, flexible timing)

USE CASE 3: FAN-OUT PROCESSING
    Trigger: Single event produces many jobs
    Jobs: "New product added" → update 50 search indexes, notify 1,000 subscribers
    Expectation: All sub-jobs complete; partial completion is visible
    Priority: Varies (notifications high, analytics low)

USE CASE 4: RETRY-SENSITIVE EXTERNAL CALLS
    Trigger: Need to call flaky external APIs
    Jobs: Sync to payment processor, push to third-party webhook
    Expectation: Eventually succeeds with exponential backoff
    Priority: High (money or contract obligations involved)

USE CASE 5: RATE-LIMITED EXTERNAL API CALLS
    Trigger: External API with rate limits (e.g., 100 requests/minute)
    Jobs: Batch of 5,000 webhook deliveries
    Expectation: Processed at controlled rate without exceeding API limits
    Priority: Normal (rate-limited, not latency-sensitive)
```

## Non-Goals

```
NON-GOALS (Explicitly Out of Scope):

1. REAL-TIME EVENT STREAMING
   This is NOT Kafka. Job queues process discrete units of work with
   completion tracking. Streaming is continuous, unbounded data flow.
   Different problem, different system.

2. WORKFLOW ORCHESTRATION
   Multi-step, branching workflows with dependencies (step A → if success,
   step B; else step C). That's an orchestration engine (Temporal, Airflow).
   V1: Each job is independent. Chaining jobs = enqueue next job on completion.

3. CRON SCHEDULER
   Job queue executes work; it doesn't own scheduling. A separate scheduler
   enqueues periodic jobs. The queue doesn't know or care about schedules.

4. EXACTLY-ONCE PROCESSING
   At-least-once with idempotent handlers. Exactly-once is impractical in
   distributed systems without enormous complexity. Handlers must be safe
   to re-execute.

5. MULTI-REGION / GLOBAL QUEUE
   V1: Single-region. Cross-region job routing adds latency, consistency
   headaches, and operational complexity.
```

---

# Part 3: Functional Requirements

## Write Flows (Enqueueing Jobs)

```
FLOW 1: SYNCHRONOUS ENQUEUE

    Producer (API Server) → Job Queue API → Persistent Store → ACK

    Steps:
    1. Producer creates job payload: {type, payload, priority, max_retries}
    2. Producer calls enqueue API (HTTP or SDK)
    3. Job Queue assigns unique job_id (UUID)
    4. Job written to persistent store (status: "pending")
    5. ACK returned to producer with job_id
    6. Producer returns response to user (includes job_id for status polling)

    Latency target: < 10ms for enqueue (must not slow down request path)

FLOW 2: BATCH ENQUEUE

    Producer → Job Queue API (batch) → Persistent Store → ACK

    Steps:
    1. Producer creates batch: [{job1}, {job2}, ..., {job_n}] (max 100)
    2. Single API call with batch payload
    3. Job Queue assigns IDs, writes batch atomically
    4. ACK with list of job_ids

    Use case: Fan-out ("notify 1,000 subscribers" → 1,000 jobs)
    Latency target: < 50ms for batch of 100
```

## Processing Flows (Dispatch & Execution)

```
FLOW 3: JOB DISPATCH AND EXECUTION

    Worker → Poll Queue → Receive Job → Execute → ACK

    Steps:
    1. Worker polls: "Give me up to 10 pending jobs"
    2. Queue atomically marks jobs as "processing" with lease_expiry (now + 5 min)
    3. Worker receives jobs
    4. Worker executes handler for each job
    5. On success: Worker ACKs job → status set to "completed"
    6. On failure: Worker NACKs job with error → status set to "failed", retry scheduled
    7. If worker crashes (no ACK/NACK before lease expires):
       → Job becomes visible again (status: "pending")
       → Another worker picks it up

    CRITICAL: Lease-based visibility prevents lost jobs. No ACK within
    lease period = job is assumed abandoned and re-dispatched.
```

## Read Flows (Status & Monitoring)

```
FLOW 4: JOB STATUS QUERY

    Client → Job Queue API → Persistent Store → Status Response

    Steps:
    1. Client queries: GET /jobs/{job_id}
    2. Returns: {job_id, type, status, created_at, started_at, completed_at, attempts, error}
    3. Status: pending | processing | completed | failed | dead

    Use case: User polls "Is my invoice ready?" or engineer debugs "What happened to job X?"

FLOW 5: QUEUE HEALTH METRICS

    Monitoring → Job Queue Metrics Endpoint → Dashboard

    Exposed metrics:
    - queue_depth (by job type, by priority)
    - jobs_enqueued_total, jobs_completed_total, jobs_failed_total
    - processing_duration_seconds (histogram)
    - oldest_pending_job_age_seconds (staleness signal)
    - dlq_depth (dead-letter queue size)
    - active_workers_count
```

## Error Handling & Retry

```
FLOW 6: RETRY WITH EXPONENTIAL BACKOFF

    Job fails → Schedule retry → Delay → Re-dispatch

    Steps:
    1. Worker NACKs job with error
    2. Queue increments attempt_count
    3. If attempt_count < max_retries:
       a. Compute next_retry_at = now + base_delay × 2^(attempt - 1) + jitter
       b. Set status = "pending", visible_after = next_retry_at
       c. Job invisible until next_retry_at
    4. If attempt_count >= max_retries:
       a. Move to dead-letter queue
       b. Set status = "dead"
       c. Increment dlq_depth metric

    Retry schedule (base = 30s):
    Attempt 1: 30s  + jitter
    Attempt 2: 60s  + jitter
    Attempt 3: 120s + jitter
    Attempt 4: 240s + jitter
    Attempt 5: DLQ (total elapsed: ~8 minutes)

FLOW 7: DEAD-LETTER QUEUE (DLQ)

    Failed job (exhausted retries) → DLQ → Alert → Manual investigation

    Steps:
    1. Job moved to DLQ table/partition
    2. Alert: "DLQ depth > 0 for job type X"
    3. On-call investigates: Reads job payload, error message, stack trace
    4. Options:
       a. Fix bug, redeploy, replay job from DLQ
       b. Discard job (known bad input, not worth retrying)
       c. Modify payload and re-enqueue (data fix)
```

## Behavior Under Partial Failure

```
PARTIAL FAILURE: Database (job store) write latency elevated

    Behavior:
    - Enqueue latency increases (10ms → 500ms)
    - Producers: May timeout; enqueue call fails
    - Workers: Continue processing already-leased jobs normally
    - New jobs: Queued slower; queue depth may grow

    Recovery:
    - Database recovers → enqueue latency normalizes
    - Producers retry failed enqueues (application-level retry)

PARTIAL FAILURE: Workers crashing (OOM on specific job type)

    Behavior:
    - Worker picks up job, OOMs, crashes
    - Lease expires → job re-dispatched → another worker OOMs
    - Cycle repeats until max_retries exhausted → DLQ
    - Meanwhile: Other job types unaffected (only specific type is poison)
    
    KEY ISSUE: Poison-pill jobs. One bad job can churn through all workers.
    
    Recovery:
    - DLQ captures the job
    - Alert fires → engineer investigates
    - Fix: Deploy handler fix, or add payload validation to reject oversized inputs

PARTIAL FAILURE: Worker pool partially down (3 of 10 workers lost)

    Behavior:
    - Processing capacity: 70% of normal
    - Queue depth grows (enqueue rate > processing rate)
    - Processing latency: Jobs wait longer before being picked up
    - No data loss (jobs are in persistent store)

    Recovery:
    - Replace failed workers (autoscaling or manual)
    - Backlog drains (workers catch up)
    - Queue depth returns to near-zero
```

---

# Part 4: Non-Functional Requirements (Senior Bar)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NON-FUNCTIONAL REQUIREMENTS                              │
│                                                                             │
│   LATENCY:                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Enqueue: P50 < 5ms, P99 < 50ms (must not slow request path)        │   │
│   │  Dispatch (poll-to-receive): P50 < 100ms, P99 < 500ms               │   │
│   │  End-to-end (enqueue-to-start-processing): P50 < 2s, P99 < 30s      │   │
│   │  End-to-end under load: P99 < 5 minutes (backlog scenario)          │   │
│   │                                                                     │   │
│   │  WHY these targets:                                                 │   │
│   │  Enqueue is on the hot path (user-facing request). Must be fast.    │   │
│   │  Processing latency is less critical—"background" means seconds     │   │
│   │  to minutes is acceptable, not milliseconds.                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   AVAILABILITY:                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Enqueue path: 99.95% (enqueue failure = lost work request)         │   │
│   │  Processing path: 99.9% (brief processing delays acceptable)        │   │
│   │  Job status API: 99.9% (non-critical, informational)                │   │
│   │                                                                     │   │
│   │  WHY 99.95% for enqueue:                                            │   │
│   │  If enqueue fails and the producer doesn't retry, the work is       │   │
│   │  silently lost. The enqueue path is the durability boundary—once    │   │
│   │  a job is persisted, it's safe. Before that, it's at risk.          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CONSISTENCY:                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  At-least-once delivery (guaranteed)                                │   │
│   │  - Every enqueued job will be delivered to a worker at least once   │   │
│   │  - Duplicates possible (lease expiry + late ACK = double delivery)  │   │
│   │  - Handlers MUST be idempotent                                      │   │
│   │                                                                     │   │
│   │  WHY not exactly-once:                                              │   │
│   │  Exactly-once requires distributed transactions between the queue   │   │
│   │  and the handler's side effects. Impractical. At-least-once +       │   │
│   │  idempotent handlers achieves the same user-visible result.         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   DURABILITY:                                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Zero job loss after successful enqueue ACK                         │   │
│   │  - Jobs persisted to durable storage before ACK                     │   │
│   │  - Storage: Replicated database (not in-memory)                     │   │
│   │                                                                     │   │
│   │  WHY strict durability:                                             │   │
│   │  Unlike metrics (best-effort), jobs represent committed work.       │   │
│   │  "Send invoice" lost = customer never gets invoice = revenue risk.  │   │
│   │  "Resize image" lost = broken user profile forever.                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ORDERING:                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Best-effort FIFO within a priority level                           │   │
│   │  - No strict ordering guarantee                                     │   │
│   │  - Jobs of equal priority: approximately FIFO                       │   │
│   │  - Higher priority jobs dispatched before lower priority            │   │
│   │                                                                     │   │
│   │  WHY no strict ordering:                                            │   │
│   │  Strict FIFO requires single-consumer dispatch (no parallelism)     │   │
│   │  or complex partitioning. Most job types don't need ordering—       │   │
│   │  "send email A" and "resize image B" are independent.               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   TRADE-OFFS ACCEPTED:                                                      │
│   - At-least-once over exactly-once (simpler, requires idempotent handlers) │
│   - Best-effort FIFO over strict ordering (enables parallelism)             │
│   - Higher enqueue availability over processing availability                │
│   - Processing latency in seconds (not milliseconds)                        │
│                                                                             │
│   TRADE-OFFS NOT ACCEPTED:                                                  │
│   - Job loss after ACK (non-negotiable)                                     │
│   - Silent failure (must be visible in DLQ, metrics, or alerts)             │
│   - Unbounded retry (must exhaust to DLQ; no infinite retry loops)          │
│   - Head-of-line blocking (one slow job type must not block others)         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 5: Scale & Capacity Planning

## Scale Estimates

```
ASSUMPTIONS:

    Applications: 20 backend services producing jobs
    Job types: 30 distinct types (email, resize, sync, report, etc.)
    Average enqueue rate: 500 jobs/second (normal)
    Peak enqueue rate: 5,000 jobs/second (flash sale, batch import)
    Average processing time per job: 2 seconds
    
    WORKER SIZING:
    At 500 jobs/sec, each taking 2 seconds:
        Concurrent jobs needed: 500 × 2 = 1,000
        Workers (10 threads each): 1,000 / 10 = 100 worker threads
        Instances (10 threads/instance): 10 worker instances
    
    At peak (5,000 jobs/sec):
        Concurrent jobs: 5,000 × 2 = 10,000
        Workers needed: 1,000 threads → 100 instances
        OR: Accept backlog, drain over ~20 minutes with 10 instances
        (10 instances × 10 threads × 0.5 jobs/sec/thread = 50 jobs/sec processing;
         wait, let me recalculate)
        
        10 instances × 10 threads = 100 concurrent slots
        Each slot processes 1 job per 2 seconds = 0.5 jobs/sec/slot
        Throughput: 100 × 0.5 = 50 jobs/sec sustained
        
        At 5,000 jobs/sec incoming: Backlog grows at 4,950 jobs/sec
        10× spike lasting 5 minutes = 5,000 × 300 = 1.5M jobs queued
        Drain time at 50 jobs/sec = 30,000 seconds = 8.3 hours (too slow!)
        
        REAL PLAN: Autoscale workers during peaks.
        Target: 100 instances during peak → 5,000 concurrent → 2,500 jobs/sec
        Remaining 2,500 jobs/sec backlog drains in ~10 minutes after spike
    
    STORAGE:
    Job record size: ~500 bytes (metadata + serialized payload)
    Daily jobs: 500/sec × 86,400 = 43.2M jobs/day
    Daily storage: 43.2M × 500B = ~21.6 GB/day
    
    Retention: 7 days for completed jobs, 30 days for failed/DLQ
    Active storage: 21.6 GB × 7 = ~150 GB
    
    Index overhead: ~30% for (status, type, scheduled_at) indexes
    Total storage: ~200 GB

READ LOAD:
    Worker polling: 10 instances, poll every 1 second = 10 QPS
    Status queries: ~5 QPS (internal tools, user-facing status checks)
    Monitoring queries: ~2 QPS (dashboards)
    Total read QPS: ~17 QPS

WRITE LOAD:
    Enqueue: 500 writes/sec (normal), 5,000 writes/sec (peak)
    Status updates: 500 writes/sec (processing → completed)
    Total write QPS: ~1,000 writes/sec (normal), ~10,000 writes/sec (peak)

WRITE:READ RATIO: ~60:1 (write-dominant system)
```

## What Breaks First

```
SCALE GROWTH:

| Scale  | Jobs/sec | Workers | What Changes              | What Breaks First          |
|--------|----------|---------|---------------------------|----------------------------|
| 1×     | 500      | 10      | Baseline                  | Nothing                    |
| 3×     | 1,500    | 30      | More workers              | DB write throughput        |
| 10×    | 5,000    | 100     | Autoscaling, read replicas| Polling contention         |
| 30×    | 15,000   | 300     | Partitioned queue         | Single DB as bottleneck    |

MOST FRAGILE ASSUMPTION: Single database as the job store.

At 1× (500 jobs/sec): PostgreSQL handles this easily.
At 10× (5,000 jobs/sec): Write throughput + row-level locking under
    concurrent polling becomes the bottleneck.

    Symptoms:
    - Enqueue latency increases (write contention)
    - Worker poll queries slow down (index scan contention)
    - "oldest_pending_job_age" increases (jobs sitting longer)
    
    Mitigation (10×):
    - Partition jobs table by type (reduce lock contention per partition)
    - Workers poll specific partitions (less contention)
    - Read replica for status queries (offload reads)
    
    Mitigation (30×):
    - Separate database per job category (email, image, sync)
    - Or: Move to purpose-built queue (Redis-backed with persistence)
    - Architecture change required at this scale
```

---

# Part 6: High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BACKGROUND JOB QUEUE ARCHITECTURE                        │
│                                                                             │
│   PRODUCERS (API servers, services, schedulers)                             │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│   │ API Svc  │    │ User Svc │    │ Billing  │    │Scheduler │              │
│   └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘              │
│        │               │               │               │                    │
│        └───────────────┼───────────────┼───────────────┘                    │
│                        ▼               ▼                                    │
│               ┌─────────────────────────────────┐                           │
│               │        ENQUEUE API              │                           │
│               │  (Stateless, load-balanced)     │                           │
│               │  - Validate payload             │                           │
│               │  - Assign job_id                │                           │
│               │  - Write to job store           │                           │
│               │  - Return ACK with job_id       │                           │
│               └──────────────┬──────────────────┘                           │
│                              │                                              │
│                              ▼                                              │
│               ┌─────────────────────────────────┐                           │
│               │         JOB STORE               │                           │
│               │     (PostgreSQL)                │                           │
│               │                                 │                           │
│               │  ┌───────────┐  ┌───────────┐   │                           │
│               │  │  Pending  │  │ Processing│   │                           │
│               │  │   Jobs    │  │   Jobs    │   │                           │
│               │  └───────────┘  └───────────┘   │                           │
│               │  ┌───────────┐  ┌───────────┐   │                           │
│               │  │ Completed │  │   DLQ     │   │                           │
│               │  │   Jobs    │  │   Jobs    │   │                           │
│               │  └───────────┘  └───────────┘   │                           │
│               └──────────────┬──────────────────┘                           │
│                              │                                              │
│                              ▼                                              │
│               ┌─────────────────────────────────┐                           │
│               │       DISPATCHER                │                           │
│               │  (Embedded in worker process)   │                           │
│               │  - Polls job store for pending  │                           │
│               │  - Claims jobs via atomic UPDATE│                           │
│               │  - Routes to handler by job type│                           │
│               └──────────────┬──────────────────┘                           │
│                              │                                              │
│                   ┌──────────┼──────────┐                                   │
│                   ▼          ▼          ▼                                   │
│              ┌────────┐ ┌────────┐ ┌────────┐                               │
│              │Worker 1│ │Worker 2│ │Worker N│                               │
│              │        │ │        │ │        │                               │
│              │Handlers│ │Handlers│ │Handlers│                               │
│              │- email │ │- email │ │- email │                               │
│              │- resize│ │- resize│ │- resize│                               │
│              │- sync  │ │- sync  │ │- sync  │                               │
│              └────────┘ └────────┘ └────────┘                               │
│                                                                             │
│   MONITORING:                                                               │
│   ┌──────────────────────────┐     ┌──────────────────────┐                 │
│   │   Queue Metrics Exporter │────→│  Dashboard / Alerts  │                 │
│   │   - queue_depth          │     │  - Grafana           │                 │
│   │   - processing_rate      │     │  - PagerDuty         │                 │
│   │   - dlq_depth            │     └──────────────────────┘                 │
│   └──────────────────────────┘                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

REQUEST FLOW (numbered steps):

1. Producer calls Enqueue API: POST /jobs {type: "send_email", payload: {...}}
2. Enqueue API validates, assigns job_id, writes to PostgreSQL (status: "pending")
3. Returns ACK: {job_id: "abc-123", status: "pending"}
4. Worker polls: SELECT ... FROM jobs WHERE status='pending' ... FOR UPDATE SKIP LOCKED
5. Atomic UPDATE: status → "processing", lease_expiry → now + 5min
6. Worker executes handler (e.g., calls SMTP to send email)
7a. Success: UPDATE status → "completed", completed_at → now
7b. Failure: UPDATE status → "pending", attempt_count++, visible_after → retry time
7c. Max retries exceeded: UPDATE status → "dead" (moved to DLQ partition)
```

### Architecture Decisions

```
DECISIONS AND JUSTIFICATIONS:

1. PostgreSQL as job store (not Redis, not Kafka)
   WHY: Jobs require durability (no data loss after ACK). PostgreSQL provides
   ACID, replication, and battle-tested durability. Redis is faster but
   risks data loss on crash. Kafka is a message broker, not a job store
   (no per-job status, no selective retry, no DLQ per job).
   
   At V1 scale (500 jobs/sec), PostgreSQL handles this comfortably.

2. Polling (not push/notification)
   WHY: Polling is simpler to implement, debug, and reason about. Workers
   pull work at their own pace (natural backpressure). Push requires
   persistent connections, load awareness, and reconnection logic.
   
   Polling cost: 10 workers × 1 poll/sec = 10 QPS (negligible).

3. Embedded dispatcher (in worker process, not separate service)
   WHY: Fewer moving parts. Each worker polls, claims, and processes.
   Separate dispatcher adds a network hop, another service to manage,
   and a potential single point of failure. At V1 scale, not needed.

4. Lease-based visibility (not ACK-required)
   WHY: Workers crash. If ACK is required to release a job, a crashed
   worker means a stuck job forever. Lease expiry makes job re-visible
   automatically. Simple, robust, no stuck jobs.

5. Stateless Enqueue API (load-balanced)
   WHY: Enqueue is on the critical path. Must scale horizontally and
   survive instance failures without job loss. All state in database.
```

---

# Part 7: Component-Level Design

## Enqueue API

```
COMPONENT: ENQUEUE API

Purpose: Accept job submissions from producers, validate, persist

Key data structures:
    JobRequest {
        type: string             // "send_email", "resize_image"
        payload: JSON            // Job-specific data
        priority: int            // 0 (low) to 9 (high), default 5
        max_retries: int         // Default 5
        idempotency_key: string  // Optional: Prevent duplicate enqueue
        delay_seconds: int       // Optional: Don't process before this delay
    }

Validation:
    - type: Must be in registered job types (reject unknown)
    - payload: Must be valid JSON, < 64KB
    - priority: 0-9 range
    - max_retries: 1-20 range
    - idempotency_key: If provided, check for existing job with same key

Idempotency:
    If idempotency_key provided:
        1. Check: SELECT job_id FROM jobs WHERE idempotency_key = ?
        2. If exists: Return existing job_id (200 OK, not 201 Created)
        3. If not: Insert normally
    
    WHY: Producers may retry enqueue calls on timeout. Without idempotency,
    the same email gets sent twice. With idempotency_key, retry is safe.

State management:
    Stateless. All state in PostgreSQL. Any API instance can serve any request.

Concurrency:
    Multiple API instances behind load balancer. No coordination needed.
    Database handles write concurrency (INSERT is append-only, no contention).

Failure behavior:
    - DB write fails: Return 503 to producer; producer retries
    - Validation fails: Return 400 with error details
    - API instance crashes: Load balancer routes to other instances
```

## Worker / Dispatcher

```
COMPONENT: WORKER (with embedded dispatcher)

Purpose: Poll for pending jobs, execute handlers, report results

Key data structures:
    WorkerConfig {
        poll_interval_ms: 1000      // Poll every 1 second
        batch_size: 10              // Fetch up to 10 jobs per poll
        lease_duration_sec: 300     // 5-minute lease
        job_types: ["*"]            // Which job types to process ("*" = all)
        max_concurrent: 10          // Thread pool size
    }

Polling mechanism:
    Every poll_interval_ms:
        1. Check available capacity: max_concurrent - active_jobs
        2. If capacity > 0:
           Query: SELECT id, type, payload FROM jobs
                  WHERE status = 'pending'
                    AND visible_after <= NOW()
                  ORDER BY priority DESC, created_at ASC
                  LIMIT $batch_size
                  FOR UPDATE SKIP LOCKED;
           
           Update: SET status = 'processing',
                       lease_expiry = NOW() + $lease_duration,
                       started_at = NOW(),
                       worker_id = $my_worker_id
           
           (SELECT + UPDATE in single transaction)
        3. Dispatch each claimed job to handler thread

    WHY "FOR UPDATE SKIP LOCKED":
        Multiple workers polling concurrently. Without SKIP LOCKED,
        they'd all try to claim the same jobs → deadlocks. SKIP LOCKED
        tells each worker: "Skip rows already locked by another worker."
        No contention, no deadlocks, workers naturally load-balance.

Handler execution:
    handler_registry = {
        "send_email": EmailHandler,
        "resize_image": ImageResizeHandler,
        "sync_crm": CRMSyncHandler,
        ...
    }
    
    handler = handler_registry[job.type]
    try:
        handler.execute(job.payload)
        mark_completed(job.id)
    except RetryableError as e:
        schedule_retry(job.id, e)
    except FatalError as e:
        send_to_dlq(job.id, e)

Lease heartbeat:
    For long-running jobs (> 1 minute):
        - Handler calls job.extend_lease() periodically
        - Updates lease_expiry = NOW() + lease_duration
        - Prevents re-dispatch while job is legitimately in progress
    
    WHY: A 30-minute report generation job would have its 5-minute
    lease expire mid-processing. Without heartbeat, it gets re-dispatched
    and two workers run the same report.

Concurrency:
    Thread pool per worker instance. Each thread processes one job.
    No shared mutable state between threads (each job is independent).

Failure behavior:
    Worker crash:
    - All leased jobs become re-visible after lease expiry
    - No data loss, no stuck jobs
    
    Handler exception:
    - Caught by worker framework
    - Job status updated (retry or DLQ)
    - Worker continues processing other jobs
    
    Database unreachable:
    - Poll fails → retry with backoff
    - Already-executing jobs continue to completion
    - Results cached locally, written when DB recovers
```

## Dead-Letter Queue (DLQ) Manager

```
COMPONENT: DLQ MANAGER

Purpose: Store and manage permanently failed jobs

Behavior:
    - Jobs arrive when max_retries exhausted
    - Status set to "dead"
    - Original payload, all error messages, and attempt history preserved
    - Alert triggered on DLQ depth increase

Operations:
    list_dlq(type, limit, offset)      → Browse DLQ jobs
    inspect_dlq(job_id)                → Full details + error history
    replay_dlq(job_id)                 → Re-enqueue as new pending job
    replay_dlq_batch(type, count)      → Re-enqueue N jobs (after fix deployed)
    discard_dlq(job_id)                → Mark as "discarded" (intentional deletion)

WHY DLQ matters:
    Without DLQ, failed jobs disappear. Engineer never knows why 50 invoices
    didn't get generated. With DLQ, the failures are preserved, inspectable,
    and replayable. This is the difference between "we lost work" and "we
    recovered from a bug."
```

---

# Part 8: Data Model & Storage

## Schema

```sql
CREATE TABLE jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type            VARCHAR(128) NOT NULL,
    payload         JSONB NOT NULL,
    priority        SMALLINT NOT NULL DEFAULT 5,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
        -- Values: 'pending', 'processing', 'completed', 'failed', 'dead'
    
    idempotency_key VARCHAR(256),
    
    -- Scheduling
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    visible_after   TIMESTAMP NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    
    -- Lease management
    lease_expiry    TIMESTAMP,
    worker_id       VARCHAR(128),
    
    -- Retry tracking
    attempt_count   SMALLINT NOT NULL DEFAULT 0,
    max_retries     SMALLINT NOT NULL DEFAULT 5,
    last_error      TEXT,
    
    -- Constraints
    CONSTRAINT valid_status CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'dead')),
    CONSTRAINT valid_priority CHECK (priority BETWEEN 0 AND 9)
);

-- Primary index for worker polling (THE critical query)
CREATE INDEX idx_jobs_dispatch 
    ON jobs (priority DESC, created_at ASC)
    WHERE status = 'pending' AND visible_after <= NOW();

-- Idempotency lookup
CREATE UNIQUE INDEX idx_jobs_idempotency 
    ON jobs (idempotency_key) 
    WHERE idempotency_key IS NOT NULL;

-- Status + type for monitoring and admin queries
CREATE INDEX idx_jobs_status_type 
    ON jobs (status, type);

-- Lease expiry for stale lease detection (reaper process)
CREATE INDEX idx_jobs_lease 
    ON jobs (lease_expiry) 
    WHERE status = 'processing';

-- Completed job cleanup (retention policy)
CREATE INDEX idx_jobs_completed_at 
    ON jobs (completed_at) 
    WHERE status = 'completed';
```

## Key Design Decisions

```
SCHEMA DECISIONS:

1. JSONB for payload (not separate columns per job type)
   WHY: 30+ job types, each with different payload shape. Separate tables
   per job type = 30 tables to manage. JSONB is flexible, queryable, and
   PostgreSQL optimizes it well. Trade-off: No schema enforcement on payload
   (handled in application-level validation).

2. Partial indexes (WHERE clause on indexes)
   WHY: Only pending jobs need the dispatch index. Completed jobs (90%+ of rows)
   don't need to be in the index. Partial indexes keep the dispatch index small
   and fast even with millions of total rows.
   
   Without partial index: Index scans all 43M rows/day
   With partial index: Index only covers pending jobs (~1,000 at any time)

3. UUID primary key (not auto-increment)
   WHY: UUIDs allow producers to pre-generate IDs (for idempotency), don't
   leak information (can't guess job_id = 42), and work across multiple
   database instances if we ever shard.

4. visible_after for delayed jobs and retries
   WHY: Single mechanism for both "delay this job 60 seconds" (producer request)
   and "retry in 120 seconds" (retry backoff). Workers simply filter:
   WHERE visible_after <= NOW(). Clean, unified.

5. Soft status transitions (not separate tables)
   WHY: A job's lifecycle is a linear state machine:
   pending → processing → completed (or → pending again for retry → dead)
   Single table with status column is simpler than moving rows between tables.
   Partial indexes keep queries fast despite mixed statuses.
```

## Retention & Cleanup

```
RETENTION POLICY:

    Completed jobs: 7 days (for debugging and audit)
    Dead/DLQ jobs: 30 days (longer for investigation)
    Failed→retried→completed jobs: 7 days
    
    Cleanup process: Nightly cron job
        DELETE FROM jobs 
        WHERE status = 'completed' AND completed_at < NOW() - INTERVAL '7 days';
        
        DELETE FROM jobs 
        WHERE status = 'dead' AND completed_at < NOW() - INTERVAL '30 days';
    
    Batch delete: 10,000 rows per transaction (avoid long locks)
    
    Daily deletion: ~43M rows × 500 bytes = ~21 GB reclaimed/day
    
    WHY not immediate deletion on completion:
    Engineers need to inspect recent job history. "Did invoice #4567 get
    generated? When? How long did it take?" Retention enables this.
    
SCHEMA EVOLUTION:
    Adding a field: Add nullable column, deploy code that writes it,
    backfill if needed, then make NOT NULL if required.
    
    Removing a field: Stop writing, deploy code that ignores it,
    remove column later (after retention period clears old rows).
    
    Changing payload schema: Versioned payloads.
    payload: {"version": 2, "data": {...}}
    Handler reads version, processes accordingly.
    Old-version jobs in queue? Still processed by old handler code
    until drained.
```

---

# Part 9: Consistency, Concurrency & Idempotency

## Consistency Guarantees

```
CONSISTENCY MODEL: At-least-once delivery with idempotent handlers

GUARANTEE:
    Every successfully enqueued job will be executed at least once.
    Duplicate execution is possible. Handlers must be idempotent.

SCENARIOS WHERE DUPLICATES OCCUR:

    Scenario 1: Slow worker + lease expiry
        T=0: Worker A claims job, lease expires at T=300s
        T=290: Worker A still processing (long job)
        T=300: Lease expires. Job becomes visible.
        T=301: Worker B claims same job, starts processing
        T=310: Worker A finishes, ACKs → UPDATE status = 'completed'
        T=320: Worker B finishes, ACKs → UPDATE status = 'completed' (no-op)
        
        Result: Job executed twice. Both workers did the work.
        
    Scenario 2: Network partition during ACK
        T=0: Worker claims job
        T=5: Worker completes successfully
        T=5: Worker sends ACK → network timeout → ACK lost
        T=6: Worker retries ACK → still fails
        T=300: Lease expires → job re-dispatched
        T=301: Another worker executes it again
        
        Result: Job executed twice.

IDEMPOTENCY IS NON-NEGOTIABLE.
```

## Idempotency Implementation

```pseudo
// EXAMPLE: Send welcome email handler

function handleSendEmail(job):
    // Step 1: Idempotency check
    idempotency_key = "welcome_email:" + job.payload.user_id
    
    if already_sent(idempotency_key):
        log("Email already sent for user " + job.payload.user_id + ", skipping")
        return SUCCESS  // Idempotent: no duplicate email
    
    // Step 2: Perform work
    result = smtp.send(
        to: job.payload.email,
        template: "welcome",
        data: job.payload
    )
    
    // Step 3: Record completion (BEFORE acknowledging job)
    mark_sent(idempotency_key, ttl=7_days)
    
    return SUCCESS


// EXAMPLE: Resize image handler (naturally idempotent)

function handleResizeImage(job):
    image_id = job.payload.image_id
    sizes = job.payload.sizes  // [64, 256, 1024]
    
    raw_image = storage.download("raw/" + image_id)
    
    for size in sizes:
        resized = resize(raw_image, size)
        // Overwrites same path = idempotent (same input → same output)
        storage.upload("resized/" + image_id + "/" + size, resized)
    
    return SUCCESS
    // If executed twice: Same files overwritten with same content. Safe.
```

## Race Conditions

```
RACE CONDITION 1: Two workers claim the same job

    Prevention: FOR UPDATE SKIP LOCKED
    
    Worker A: SELECT ... FOR UPDATE SKIP LOCKED → Gets job 42
    Worker B: SELECT ... FOR UPDATE SKIP LOCKED → Skips job 42 (locked), gets job 43
    
    No race. PostgreSQL row-level locking handles this atomically.

RACE CONDITION 2: Enqueue duplicate (producer retries)

    Prevention: Idempotency key with unique index
    
    Producer: POST /jobs {idempotency_key: "signup-user-789"}
    Timeout → retries → POST /jobs {idempotency_key: "signup-user-789"}
    
    Second INSERT: Unique constraint violation
    → Catch, return existing job_id
    → No duplicate job created

RACE CONDITION 3: Job completed + lease expiry race

    Worker A finishes job at T=299. Lease expires at T=300.
    Worker A sends ACK at T=299.5.
    
    ACK query: UPDATE jobs SET status = 'completed' 
               WHERE id = $job_id AND worker_id = $my_worker_id;
    
    If another worker already reclaimed it:
    → worker_id no longer matches → UPDATE affects 0 rows
    → Worker A logs warning: "Job already reclaimed, my work was duplicate"
    → No corruption.
    
    WHY worker_id in WHERE clause: Prevents stale workers from overwriting
    the status of a job that's been re-dispatched to another worker.

RACE CONDITION 4: Reaper reclaims job while worker is processing

    Lease reaper: UPDATE jobs SET status = 'pending'
                  WHERE status = 'processing' AND lease_expiry < NOW();
    
    Worker is still processing (slow, but not dead):
    → Job becomes pending → another worker claims it
    → Two workers process same job
    
    Mitigation: Lease heartbeat. Long-running jobs extend lease.
    If no heartbeat and lease expires: Reaper correctly assumes worker is dead.
```

## Clock Assumptions

```
CLOCK HANDLING:

    All timestamps: Database server clock (NOW() in PostgreSQL)
    NOT application server clock.
    
    WHY: Multiple API servers and workers. If each uses its own clock,
    clock skew between servers causes:
    - Jobs scheduled in the "past" (immediately visible)
    - Jobs scheduled in the "future" (invisible longer than expected)
    - Lease expiry off by seconds
    
    SINGLE AUTHORITY: Database clock. All time comparisons done in SQL.
    Worker calculates nothing with local time.
    
    Exception: Lease heartbeat sends "extend by X seconds" not "extend to T."
    Relative durations are clock-skew-safe.
```

---

# Part 10: Failure Handling & Reliability (Ownership-Focused)

## Failure Mode Table

| Failure Type | Handling Strategy |
|--------------|-------------------|
| **Worker crash** | Lease expiry → auto re-dispatch (no manual intervention) |
| **Database unavailable** | Enqueue returns 503; workers pause polling; buffer locally |
| **Poison-pill job** | Crashes worker → retries → DLQ. Alert on rapid DLQ growth |
| **Slow dependency** | Job timeout → retry with backoff. Circuit breaker for chronic slowness |
| **Queue backlog** | Autoscale workers. Alert on queue depth growth rate |
| **DLQ overflow** | Alert → engineer investigates → fix and replay or discard |

## Detailed Failure Strategies

```
RETRY POLICY:

    Exponential backoff with jitter:
    
    delay = min(base_delay × 2^(attempt-1), max_delay) + random(0, jitter)
    
    base_delay: 30 seconds
    max_delay: 3600 seconds (1 hour)
    jitter: random 0-15 seconds
    max_retries: 5 (configurable per job type)
    
    Schedule:
    Attempt 1: 30s  + jitter  (total elapsed: ~30s)
    Attempt 2: 60s  + jitter  (total elapsed: ~90s)
    Attempt 3: 120s + jitter  (total elapsed: ~210s)
    Attempt 4: 240s + jitter  (total elapsed: ~450s)
    Attempt 5: 480s + jitter  (total elapsed: ~930s = ~15 minutes)
    → DLQ
    
    WHY jitter:
    Without jitter, 1,000 jobs that failed at the same time all retry
    at the exact same time → thundering herd → dependency overwhelmed again.
    Jitter spreads retries over a window.

TIMEOUT POLICY:
    
    Job execution timeout: 5 minutes (default, configurable per type)
    
    If handler doesn't complete in 5 minutes:
    → Worker kills the handler thread
    → NACKs the job with "execution_timeout" error
    → Retry scheduled
    
    WHY per-type timeouts:
    "send_email": 30 seconds (SMTP should respond quickly)
    "generate_report": 10 minutes (legitimately slow)
    "resize_image": 2 minutes (should be fast; if not, image is corrupt)

CIRCUIT BREAKER (per job type):

    If error_rate for job type > 80% over last 5 minutes:
    → Stop dispatching that job type
    → Jobs accumulate in queue (safe, they're persisted)
    → Alert: "Circuit breaker open for job type X"
    → Check every 60 seconds: Try 1 job. If succeeds → close breaker.
    
    WHY: If SMTP is completely down, retrying 500 email jobs/second
    burns resources and generates noise. Better to pause, wait for
    recovery, then resume.
```

## Production Failure Scenario: Poison-Pill Job Takes Down Processing

```
SCENARIO: A user uploads a 500MB image. The resize handler loads it into 
memory (2GB after decode), causing every worker that touches it to OOM.

1. TRIGGER:
   - Enqueued: {type: "resize_image", payload: {image_id: "huge-abc"}}
   - Worker 1 picks it up → allocates 2GB → OOM killed
   - Process restarts, job lease expires → re-dispatched
   - Worker 3 picks it up → OOM killed
   - Cycle repeats for all 5 retry attempts

2. IMPACT:
   - Each OOM crash kills the worker process, not just the one job
   - All other jobs being processed by that worker instance are interrupted
   - Worker restart takes 15 seconds → 15 seconds of reduced capacity
   - Across 5 retries × multiple workers: 5-10 worker crashes over 15 minutes
   - Other job types experience delays during worker restarts

3. DETECTION:
   - Alert: "Worker instance restart count > 3 in 10 minutes"
   - Alert: "OOM kill events on worker pod"
   - Metrics: Processing rate drops; queue depth increases
   - After 5 retries: DLQ alert "New job in DLQ: resize_image"

4. TRIAGE:
   - Check DLQ: job payload shows image_id "huge-abc"
   - Check worker logs (before OOM): "Allocating memory for image decode..."
   - Correlate: OOM events coincide with this specific job being claimed
   - Root cause: No input validation on image size

5. MITIGATION (immediate):
   - Job is already in DLQ (retries exhausted). No more crashes.
   - If still in retry cycle: Manually move to DLQ via admin API
   - Verify worker processes have stabilized
   - Check for similar large images in pending queue:
     SELECT id FROM jobs WHERE type='resize_image' 
       AND (payload->>'file_size')::bigint > 100000000;

6. RESOLUTION:
   - Add payload validation in resize handler:
     if file_size > 50MB: reject with FatalError (skip retry, go to DLQ)
   - Add per-job memory limit (cgroup or container memory limit per thread)
   - Deploy fix, verify with test image

7. POST-MORTEM:
   - Action item: Add input validation for ALL job types (size, format, etc.)
   - Action item: Per-job resource limits (memory, CPU time)
   - Action item: Separate worker pools by resource profile
     (lightweight email workers vs heavyweight image workers)
   - Process change: New job types require resource profile estimation
```

---

# Part 11: Performance & Optimization

## Hot Paths

```
HOT PATH 1: ENQUEUE (on user-facing request path)

    Producer → Enqueue API → INSERT into PostgreSQL → ACK
    
    Target: < 10ms P99
    
    Optimizations applied:
    - Connection pooling (PgBouncer or application-level pool)
    - Prepared statements for INSERT (skip query parsing)
    - No unnecessary indexes on INSERT path (partial indexes help)
    
    Optimizations NOT applied:
    - Async/batched writes (risk: crash before write = lost job)
    - In-memory queue before DB (same risk)
    - Write-ahead to faster store (Redis) then sync to DB
      (adds complexity, split-brain risk, not needed at 500 jobs/sec)

HOT PATH 2: WORKER POLL (determines processing latency)

    Worker → SELECT ... FOR UPDATE SKIP LOCKED → Claim batch
    
    Target: < 100ms P99
    
    Optimizations applied:
    - Partial index on (status='pending', visible_after <= NOW())
    - SKIP LOCKED eliminates contention between workers
    - Batch fetch (10 jobs per poll, not 1)
    
    Optimizations NOT applied:
    - Push-based dispatch (WebSocket/gRPC stream from dispatcher)
      WHY NOT: Adds persistent connection management, reconnection
      logic, and load-balancing complexity. Polling is simple, sufficient.
    - Notification-triggered polling (LISTEN/NOTIFY in PostgreSQL)
      WHY NOT: Would reduce empty polls. But at 10 QPS polling cost,
      the benefit doesn't justify the complexity. Consider at 100+ workers.
```

## Caching

```
CACHING STRATEGY:

    Enqueue path: NO CACHE (every write goes to DB; durability non-negotiable)
    
    Job status queries: NO CACHE (V1)
        Status changes frequently (pending → processing → completed in seconds).
        Caching would serve stale status. At 5 QPS, DB handles this easily.
    
    Idempotency check: DB index lookup (unique index on idempotency_key)
        Fast enough at V1 scale. No external cache needed.
        At 10× scale: Consider Bloom filter or Redis for idempotency lookups.
    
    WHY minimal caching:
        Job queues are write-heavy. Most data is transient (created,
        processed, deleted within minutes). Caching transient data adds
        complexity (invalidation) for minimal benefit.
        
        A mid-level engineer might add Redis caching for job status.
        A Senior engineer recognizes that the access pattern doesn't
        justify it: writes dominate, reads are infrequent, data is short-lived.
```

## Bottleneck Analysis

```
BOTTLENECKS AND PREVENTION:

1. DATABASE WRITE THROUGHPUT
   At 500 writes/sec: Fine (PostgreSQL handles 10K+ simple INSERTs/sec)
   At 5,000 writes/sec (peak): Approaching limit with indexes
   Prevention: Connection pooling, batch inserts for fan-out scenarios
   
2. POLLING CONTENTION
   10 workers polling: Fine (SKIP LOCKED eliminates contention)
   100 workers polling: SELECT scans overlap; index lock contention
   Prevention: Workers poll different partitions (by job type)
   
3. LONG-RUNNING JOBS BLOCKING WORKERS
   1 report generation (30 min) occupies 1 of 10 thread slots
   10 concurrent reports = entire worker blocked
   Prevention: Separate worker pools for long-running vs short jobs
   
4. BACKLOG DURING SPIKE
   5,000 jobs/sec enqueue, 50 jobs/sec processing = massive backlog
   Prevention: Worker autoscaling (scale on queue_depth metric)
   Alert: "queue_depth > 10,000" → "queue_depth_rate > 100/min"

OPTIMIZATIONS INTENTIONALLY NOT DONE:

1. In-memory queue with async persistence
   WHY NOT: Risk of data loss. Not acceptable for job queues.
   A mid-level engineer might suggest this for performance.
   A Senior engineer knows durability > latency for background work.

2. Separate priority queues (different tables per priority)
   WHY NOT: Adds schema complexity, migration pain, and operational
   burden. Priority handled by ORDER BY in single query. Sufficient.

3. Job result storage in queue
   WHY NOT: Results belong in the domain service, not the queue.
   Email handler writes to email_log table. Image handler writes to
   image_storage. Queue just tracks status, not results.
```

## Backpressure

```
BACKPRESSURE HANDLING:

    Producer → Queue:
        Queue depth > 100,000 → Enqueue API returns 429 (Too Many Requests)
        Producer must back off or fail gracefully to user
        
        WHY: Unbounded queue growth = unbounded storage growth = eventual OOM
        or disk full. Better to signal "slow down" than silently accumulate.

    Queue → Workers:
        Natural backpressure: Workers pull at their own capacity.
        If workers are full, jobs wait in queue (intended behavior).
        Autoscaling adds workers when queue_depth is sustained.

    Workers → External Dependencies:
        Dependency slow → handler takes longer → fewer jobs/sec processed
        → queue depth grows → autoscale workers
        → MORE workers hit slow dependency → dependency even slower
        
        FIX: Circuit breaker per dependency. If slow, stop sending.
        Jobs queue up safely (persisted). Resume when dependency recovers.
```

---

# Part 12: Cost & Operational Considerations

## Cost Breakdown

```
COST ESTIMATE (V1: 500 jobs/sec, AWS us-east-1):

    Enqueue API (2 instances, stateless):
        2 × t3.medium ($30/mo) = $60/month
    
    Worker instances (10 instances, compute-heavy):
        10 × c5.large ($62/mo) = $620/month
    
    PostgreSQL (primary + replica):
        db.r5.large ($175/mo × 2) = $350/month
        Storage (200 GB × $0.115/GB) = $23/month
    
    Monitoring (metrics, dashboards, alerts):
        CloudWatch or Datadog agent = $100/month
    
    TOTAL: ~$1,150/month
    
    Cost per million jobs: $1,150 / (500 × 86,400 × 30 / 1,000,000)
                        = $1,150 / 1,296M ≈ $0.89 per million jobs
```

## Cost Scaling

```
COST AT SCALE:

| Scale | Jobs/sec | Workers | DB           | Monthly Cost| Cost/M jobs|
|-------|----------|---------|--------------|-------------|-------------|
| 1×    | 500      | 10      | r5.large     | $1,150      | $0.89       |
| 3×    | 1,500    | 30      | r5.xlarge    | $2,600      | $0.67       |
| 10×   | 5,000    | 100     | r5.2xlarge   | $8,500      | $0.66       |
| 30×   | 15,000   | 300     | Sharded      | $28,000     | $0.72       |

Cost is approximately linear with scale (workers dominate).
Database cost sub-linear (bigger instance, not more instances until sharding).
At 30×, sharding DB adds operational cost, bringing per-job cost up slightly.

BIGGEST COST DRIVER: Worker compute (54% of total at 1×, ~70% at 10×).
    Workers must be sized for peak processing, but idle during off-peak.
    Optimization: Autoscaling based on queue_depth → reduce off-peak workers to 3.
    Savings: ~$350/month at 1× scale (30% reduction).
```

## Cost vs Operability (Senior Trade-off Table)

```
DECISION TRADE-OFFS — COST, OPERABILITY, ON-CALL:

| Decision                   | Cost Impact    | Operability Impact       | On-Call Impact                     |
|----------------------------|----------------|--------------------------|------------------------------------|
| More worker instances      | +$62/instance  | Higher throughput        | Fewer "queue_depth" pages          |
| Separate worker pools      | +$200/mo       | Isolate failure by type  | Clearer blame (email vs image)     |
| Read replica for status    | +$175/mo       | Offload read load        | Status API stays up during writes  |
| Simpler architecture (1 DB)| -$350/mo       | Single place to debug    | One failover to understand         |
| Autoscale workers          | -$350 off-peak | Variable capacity        | Must tune scale-up/scale-down      |
| DLQ retention 30 days      | +$50/mo        | Full failure history     | Replay after fix without repro     |

L5 RELEVANCE: A Senior engineer explicitly weighs cost against operability.
Cutting cost by removing the read replica saves $175/mo but makes status
queries compete with worker polls during peak—harder to debug. Acceptable
at V1; revisit when status QPS grows.
```

## Operational Considerations

```
OPERATIONAL BURDEN:

    Daily:
    - Check DLQ depth (should be near-zero; non-zero = investigate)
    - Verify queue_depth within normal range
    - No action needed if dashboards green
    
    Weekly:
    - Review job processing duration trends (regressions?)
    - Check retention cleanup ran successfully
    - Verify worker autoscaling responded to last week's peak
    
    On-call:
    - Alert: "queue_depth > 10,000 for 5 minutes" → Check if workers healthy
    - Alert: "dlq_depth > 0" → Investigate failed job type
    - Alert: "oldest_pending_job > 10 minutes" → Workers stuck or capacity issue
    - Alert: "enqueue_error_rate > 1%" → DB health issue
    
    WHAT NOT TO BUILD (saves operational cost):
    - Job scheduling UI (V1: enqueue via API only, no admin UI)
    - Per-job progress tracking (handler writes progress to own domain)
    - Cross-job dependency graphs (that's a workflow engine, not V1)
    - Real-time job logs (workers write to standard logging, not queue)
```

## Misleading Signals & Debugging Reality (MANDATORY)

```
THE FALSE CONFIDENCE PROBLEM:

| Metric              | Looks Healthy        | Actually Broken                                                        |
|---------------------|----------------------|------------------------------------------------------------------------|
| queue_depth         | 0                    | Jobs enqueued but never dispatched (bug in visible_after or index)     |
| processing_rate     | 1000/sec             | Jobs "completed" but handler failed after ACK (wrong status)           |
| dlq_depth           | 0                    | Failures going to wrong partition; DLQ counter not incremented         |
| jobs_completed_total| Steady increase      | Duplicate executions (lease expiry + slow ACK); business double-charged|
| enqueue_error_rate  | 0%                   | Producers retrying; idempotency saving you; one 503 = lost job         |
| oldest_pending_job  | 30s                  | One priority band starved; high-priority fine, low-priority stuck      |

THE ACTUAL SIGNAL (Job Queue):

HEALTHY-LOOKING:
- queue_depth = 0, processing_rate = 1000/sec

ACTUAL PROBLEM:
- Jobs marked "completed" but downstream never received (e.g. email handler
  returns success before SMTP commit; SMTP fails after; job ACKed).
- Or: Handler writes to local cache, ACKs, then crash before flushing—work lost.

REAL SIGNALS:
- End-to-end success rate: "emails_actually_delivered / emails_enqueued" (business metric)
- Downstream acknowledgment: If downstream can confirm (webhook 200), track that
- Idempotency table check: "How many jobs re-executed due to duplicate delivery?"
  (Spike = lease/ACK races; handlers must be idempotent.)

SENIOR APPROACH:
- Don't trust "completed" count alone. Add a post-completion verification
  sample (e.g. 1% of send_email jobs: verify delivery via mail provider API).
- Dashboard: Place "oldest_pending_job by priority" next to "queue_depth by type"
  so starvation of one band is visible.
- Alert on "processing_duration" spike before "queue_depth" — slow workers
  often the leading indicator of dependency or poison-pill issues.
```

---

# Part 13: Security Basics & Abuse Prevention

## Authentication & Authorization

```
AUTHENTICATION:

    Enqueue API:
    - Internal service-to-service auth (mTLS or API key per service)
    - No external access (job queue is internal infrastructure)
    - Each service identified by its API key/certificate
    
    Admin API (DLQ management, job inspection):
    - Restricted to on-call / platform team
    - RBAC: "job_queue_admin" role required
    - Audit log: All DLQ operations logged (who replayed/discarded what)

AUTHORIZATION:

    Per-service job type restrictions:
    - Service "user-api" can enqueue: ["send_email", "resize_image"]
    - Service "billing" can enqueue: ["generate_invoice", "sync_payment"]
    - Unknown type or unauthorized service: 403 Forbidden
    
    WHY restrict:
    Without restrictions, any service can enqueue any job type. A bug in
    one service could flood the queue with millions of wrong job types.
    Type restrictions act as a safety net.
```

## Abuse Vectors

```
ABUSE VECTORS AND PREVENTION:

1. QUEUE FLOODING
   Attacker/buggy service enqueues millions of jobs
   Prevention:
   - Rate limit per service: 1,000 enqueues/sec max (configurable)
   - Queue depth limit: Reject enqueue if queue_depth > 500,000
   - Alert: Enqueue rate anomaly detection
   
2. PAYLOAD INJECTION
   Malicious payload triggers unintended behavior in handler
   Prevention:
   - Payload size limit: 64KB max
   - Payload schema validation per job type (strict whitelist)
   - Handlers never eval/exec payload content
   - Sanitize before passing to external systems (email templates, etc.)

3. DLQ REPLAY ABUSE
   Replaying DLQ jobs that should not be re-executed (e.g., duplicate payments)
   Prevention:
   - Idempotent handlers (replay is safe by design)
   - Audit log on all DLQ operations
   - Replay requires explicit confirmation for sensitive job types

4. RESOURCE EXHAUSTION VIA LARGE PAYLOADS
   Enqueue jobs with max-size payloads to exhaust DB storage
   Prevention:
   - 64KB payload limit × 500K queue depth limit = 32 GB max queue storage
   - Bounded and predictable

V1 SECURITY NON-NEGOTIABLES:
    - Service authentication on enqueue
    - Payload size limits
    - Rate limiting per service
    - Audit log on admin operations

V1 SECURITY ACCEPTABLE RISKS:
    - No encryption of payload at rest (internal system, trusted network)
    - No per-field PII masking in job payloads (handled by handlers)
```

---

# Part 14: System Evolution (Senior Scope)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EVOLUTION PATH                                           │
│                                                                             │
│   V1 (Initial):                                                             │
│   - PostgreSQL-backed job store                                             │
│   - Polling workers with FOR UPDATE SKIP LOCKED                             │
│   - Exponential backoff retry, DLQ                                          │
│   - Single job table, priority support                                      │
│   - Manual DLQ management via admin API                                     │
│   - Autoscaling workers on queue_depth                                      │
│   Scale: 500 jobs/sec, 10 workers, 30 job types                             │
│                                                                             │
│   V1.1 (First Issues — triggered by growth):                                │
│   - TRIGGER: Queue depth spikes during daily batch imports (3× normal)      │
│   - FIX: Separate worker pools by job category                              │
│     Pool A: email/notification workers (latency-sensitive, lightweight)     │
│     Pool B: image/video workers (CPU-heavy, memory-heavy)                   │
│     Pool C: batch/sync workers (long-running, external APIs)                │
│   - BENEFIT: Heavy image resize jobs no longer delay email delivery         │
│   - TRIGGER: Polling contention at 50 workers                               │
│   - FIX: Workers poll by job type partition (not entire table)              │
│                                                                             │
│   V2 (Incremental — triggered by 5× growth):                                │
│   - TRIGGER: PostgreSQL write throughput at limit (5,000 jobs/sec peak)     │
│   - FIX: LISTEN/NOTIFY for instant dispatch (reduce empty polls)            │
│   - FIX: Connection pooling optimization (PgBouncer in transaction mode)    │
│   - TRIGGER: Retention cleanup causing table bloat and vacuuming overhead   │
│   - FIX: Table partitioning by created_at (drop old partitions instead      │
│     of DELETE)                                                              │
│   - TRIGGER: Need for priority queues with strict isolation                 │
│   - FIX: Separate tables per priority tier (high/normal/low)                │
│                                                                             │
│   NOT IN SCOPE (would be V3, Staff-level):                                  │
│   - Migrate from PostgreSQL to purpose-built store                          │
│   - Multi-region job routing                                                │
│   - Workflow orchestration (job chains, DAGs)                               │
│   - Job queue as a platform (self-service for all teams)                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 15: Alternatives & Trade-offs

## Alternative 1: Redis-Backed Queue (e.g., Sidekiq, Bull)

```
ALTERNATIVE: Use Redis as the job store instead of PostgreSQL

WHAT IT IS:
    Redis lists or sorted sets as the queue. Workers BRPOP for jobs.
    Frameworks: Sidekiq (Ruby), Bull (Node.js), Celery with Redis (Python).

WHY CONSIDERED:
    - Much faster enqueue/dequeue (sub-millisecond)
    - Built-in blocking pop (no polling needed)
    - Simpler code (mature frameworks handle everything)
    - Lower latency for dispatch (push-based, not poll-based)

WHY REJECTED FOR V1:
    - Durability risk: Redis persistence (RDB/AOF) can lose seconds of data
      on crash. Even with AOF fsync=always, Redis is not designed for
      durable transactional workloads.
    - No ACID: No transactions, no complex queries on job state.
    - Operational risk: Redis OOM = lost data (eviction or crash).
    - At V1 scale (500 jobs/sec), PostgreSQL is fast enough and provides
      durability guarantees that Redis does not.

TRADE-OFF:
    Redis: 10× faster, but non-zero data loss risk
    PostgreSQL: Sufficient speed, zero data loss after ACK
    
    DECISION: Durability wins. Background jobs represent committed work
    (invoices, emails, payments). Losing a job = losing customer trust.
    
WHEN TO RECONSIDER:
    If enqueue latency (< 1ms needed) becomes critical, or at 30×+ scale
    where PostgreSQL write throughput is insufficient, consider Redis
    with WAL-backed persistence or a hybrid approach.
```

## Alternative 2: Message Broker (Kafka / RabbitMQ)

```
ALTERNATIVE: Use Kafka or RabbitMQ as the job queue

WHAT IT IS:
    Kafka: Distributed log with consumer groups. Jobs are messages on a topic.
    RabbitMQ: Message broker with queues, exchanges, and acknowledgments.

WHY CONSIDERED:
    - Battle-tested at massive scale (millions of messages/sec)
    - Built-in consumer groups (multiple workers)
    - Kafka: Durable, replicated, partitioned
    - RabbitMQ: Mature, feature-rich, supports delayed messages

WHY REJECTED FOR V1:
    - Kafka: No per-message status tracking, no DLQ per job, no selective
      retry (can't retry job #42 without replaying the whole partition).
      Kafka is a log, not a task manager.
    - RabbitMQ: Adds an external system to operate (clustering, monitoring,
      upgrades). At 500 jobs/sec, PostgreSQL handles everything in one system.
    - Both: Separate infrastructure to manage, monitor, and maintain.
      PostgreSQL is already in the stack. Adding Kafka/RabbitMQ for 500 jobs/sec
      is over-engineering.

TRADE-OFF:
    Kafka/RabbitMQ: Higher throughput, but additional infrastructure + no
    native per-job status tracking
    PostgreSQL: Lower throughput ceiling, but zero additional infrastructure
    and full SQL querying of job state

WHEN TO RECONSIDER:
    If job volume exceeds 10,000/sec sustained, or if the system needs
    event streaming capabilities (not just task execution), Kafka becomes
    a more natural fit—but you'd still need a job status layer on top.
```

---

# Part 16: Interview Calibration (L5 Focus)

## What Interviewers Evaluate

| Signal | How It's Assessed |
|--------|-------------------|
| **Scope management** | Do they ask clarifying questions (enqueue rate, job types, ordering needs)? |
| **Trade-off reasoning** | Do they justify PostgreSQL vs Redis, at-least-once vs exactly-once? |
| **Failure thinking** | Do they proactively discuss poison-pill, lease expiry, DLQ? |
| **Scale awareness** | Do they reason about 500 vs 5,000 jobs/sec and what breaks first? |
| **Ownership mindset** | Do they discuss rollout, rollback, alerts, and on-call response? |

## How Google Interviews Probe This

```
COMMON FOLLOW-UP QUESTIONS:

1. "What happens if a worker crashes mid-job?"
   → Tests: Understanding of lease-based dispatch, at-least-once semantics

2. "How do you prevent duplicate execution?"
   → Tests: Idempotency thinking, awareness of distributed system realities

3. "What if the queue gets backed up?"
   → Tests: Backpressure thinking, scaling strategy, priority handling

4. "How would you handle a poison-pill job?"
   → Tests: Failure isolation, DLQ design, operational awareness

5. "Why not just use Kafka/Redis for this?"
   → Tests: Technology selection judgment, durability vs speed trade-off

6. "How do you monitor this system?"
   → Tests: Operational maturity, ownership mentality
```

## Common L4 Mistakes

```
L4 MISTAKE 1: No durability guarantee

    L4: "Workers fetch jobs from an in-memory queue"
    WHY IT'S L4: If the queue process crashes, all pending jobs are lost.
    L5 FIX: Persist to durable storage before ACK. Jobs survive restarts.

L4 MISTAKE 2: No retry mechanism

    L4: "If the job fails, we log the error"
    WHY IT'S L4: Transient failures (network timeout, dependency restart)
    are the norm, not the exception. Most failures are retriable.
    L5 FIX: Exponential backoff retry with max attempts → DLQ.

L4 MISTAKE 3: No idempotency awareness

    L4: "Workers process each job exactly once"
    WHY IT'S L4: In distributed systems, exactly-once is a myth without
    distributed transactions. Lease expiry, network partitions, and slow
    workers all cause duplicate delivery.
    L5 FIX: Design handlers to be idempotent. Expect duplicates. Handle them.

L4 MISTAKE 4: Ignoring the enqueue path

    L4: Focuses entirely on processing, ignores enqueue latency
    WHY IT'S L4: Enqueue is on the user-facing hot path. A 500ms enqueue
    adds 500ms to every user request that triggers background work.
    L5 FIX: Enqueue must be < 10ms. Design for it explicitly.
```

## Borderline L5 Mistakes

```
BORDERLINE L5 MISTAKE 1: No failure isolation between job types

    ALMOST L5: Good retry + DLQ, but all job types share one worker pool
    WHY BORDERLINE: A CPU-heavy image resize starves lightweight email
    delivery. One job type's failures affect all others.
    STRONG L5: Discuss worker pool separation by job category or resource profile.

BORDERLINE L5 MISTAKE 2: No discussion of backpressure

    ALMOST L5: Good architecture, good retry, but no mention of what happens
    when enqueue rate >> processing rate
    WHY BORDERLINE: Queue grows unbounded → storage fills → system fails.
    STRONG L5: Proactively discuss queue depth limits, autoscaling triggers,
    and producer-facing backpressure (429 responses).

BORDERLINE L5 MISTAKE 3: Over-engineering with Kafka for simple job queue

    ALMOST L5: Chooses Kafka "because it's distributed and scalable"
    WHY BORDERLINE: Kafka adds operational complexity without solving the
    core problem better. At V1 scale, PostgreSQL is sufficient and simpler.
    STRONG L5: Choose the simplest solution that meets requirements. Discuss
    when you'd migrate to Kafka (at what scale, triggered by what signal).
```

## Example Strong L5 Phrases

```
- "Before I dive in, let me clarify the enqueue rate and job types we're designing for."
- "I'm intentionally NOT building workflow orchestration in V1 because..."
- "The main failure mode I'm worried about is a poison-pill job crashing workers repeatedly."
- "At 10× scale, the first thing that breaks is PostgreSQL write throughput."
- "For V1, I'd accept at-least-once with idempotent handlers because exactly-once isn't worth the complexity."
```

## Common L4 Mistake (Template)

```
MISTAKE: Jumping straight to solution (e.g. "we'll use Redis for the queue") without requirements.
WHY IT'S L4: Shows execution focus over design thinking; misses durability vs speed trade-off.
L5 APPROACH: Spend 5–10 minutes on requirements: enqueue rate, job types, durability guarantee, ordering needs.
```

## Borderline L5 Mistake (Template)

```
MISTAKE: Good design (PostgreSQL, retry, DLQ) but no failure mode discussion.
WHY IT'S BORDERLINE: Shows skill but not ownership mentality; interviewer can't assess on-call readiness.
L5 FIX: Proactively discuss "what happens when a worker crashes / DB is slow / one job type OOMs."
```

## What Distinguishes Solid L5

```
- Proactive failure discussion (poison-pill, lease expiry, DLQ, circuit breaker)
- Quantified scale reasoning (500 vs 5,000 jobs/sec, what breaks first)
- Explicit non-goals (no workflow engine, no exactly-once, single region V1)
- Trade-off articulation (PostgreSQL vs Redis, polling vs push, durability vs latency)
- Operational awareness (rollout stages, rollback trigger, misleading metrics, cost vs operability)
```

## Strong Senior Answer Signals

```
STRONG L5 SIGNALS:

1. "Jobs must be durable after enqueue ACK. This is the durability boundary."
   → Shows: Understanding of the system's core contract

2. "Handlers must be idempotent because at-least-once delivery is the only
   practical guarantee in a distributed system."
   → Shows: First-principles reasoning about distributed systems

3. "I'd use PostgreSQL for V1. It's already in our stack, provides ACID,
   and handles 500 jobs/sec easily. I'd consider Redis or Kafka at 10×."
   → Shows: Pragmatic technology selection, not resume-driven development

4. "The most dangerous failure is a poison-pill job that crashes workers
   repeatedly. Lease-based dispatch + max retries + DLQ handles this."
   → Shows: Production awareness, failure-mode thinking

5. "Queue depth is the key metric. If it's growing, either workers are
   failing or we need more capacity. I'd autoscale on this signal."
   → Shows: Operational maturity, metric-driven decisions

6. "I'd separate worker pools for heavy jobs (image resize) and light jobs
   (email send) to prevent head-of-line blocking across job types."
   → Shows: Failure isolation thinking, resource-aware design
```

---

# Part 17: Diagrams

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    JOB QUEUE SYSTEM ARCHITECTURE                            │
│                                                                             │
│                                                                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐                  │
│  │ API Svc  │   │ User Svc │   │ Billing  │   │Scheduler │                  │
│  │ (enqueue)│   │ (enqueue)│   │ (enqueue)│   │ (enqueue)│                  │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘                  │
│       │              │              │              │                        │
│       └──────────────┴──────┬───────┴──────────────┘                        │
│                             ▼                                               │
│              ┌──────────────────────────────┐                               │
│              │       ENQUEUE API (×2)       │  ← Stateless, LB'd            │
│              │   Validate → Assign ID →     │                               │
│              │   Persist → ACK              │                               │
│              └─────────────┬────────────────┘                               │
│                            │                                                │
│                            ▼                                                │
│              ┌──────────────────────────────┐                               │
│              │    POSTGRESQL (Primary)      │  ← Single source of truth     │
│              │                              │                               │
│              │  jobs table:                 │                               │
│              │  ┌────────────────────────┐  │                               │
│              │  │ pending (visible)      │──┤──→ Workers poll here          │
│              │  │ processing (leased)    │  │                               │
│              │  │ completed              │  │                               │
│              │  │ dead (DLQ)             │  │                               │
│              │  └────────────────────────┘  │                               │
│              │                              │                               │
│              │  Replica ──→ Status queries  │                               │
│              └──────────────┬───────────────┘                               │
│                             │                                               │
│              ┌──────────────┼──────────────┐                                │
│              ▼              ▼              ▼                                │
│     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                      │
│     │ Worker Pool A│ │ Worker Pool B│ │ Worker Pool C│                      │
│     │ (Email/Notif)│ │ (Image/Video)│ │ (Sync/Batch) │                      │
│     │  ×5 light    │ │  ×3 heavy    │ │  ×2 medium   │                      │
│     │              │ │              │ │              │                      │
│     │ Poll → Claim │ │ Poll → Claim │ │ Poll → Claim │                      │
│     │ → Execute    │ │ → Execute    │ │ → Execute    │                      │
│     │ → ACK/NACK   │ │ → ACK/NACK   │ │ → ACK/NACK   │                      │
│     └──────┬───────┘ └──────┬───────┘ └──────┬───────┘                      │
│            │                │                │                              │
│            ▼                ▼                ▼                              │
│     ┌──────────┐     ┌──────────┐     ┌──────────┐                          │
│     │   SMTP   │     │  Object  │     │ External │                          │
│     │  Server  │     │ Storage  │     │   APIs   │                          │
│     └──────────┘     └──────────┘     └──────────┘                          │
│                                                                             │
│   MONITORING:                                                               │
│   ┌────────────────────────────┐    ┌───────────────────────┐               │
│   │ Metrics: queue_depth,      │───→│ Grafana + PagerDuty   │               │
│   │ processing_rate, dlq_depth │    │ Dashboards + Alerts   │               │
│   └────────────────────────────┘    └───────────────────────┘               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Job Lifecycle (State Machine)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    JOB LIFECYCLE STATE MACHINE                              │
│                                                                             │
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────┐          │
│   │                                                              │          │
│   │  ENQUEUE                                                     │          │
│   │  ┌─────────┐                                                 │          │
│   │  │ pending │ ← initial state after INSERT                    │          │
│   │  └────┬────┘                                                 │          │
│   │       │                                                      │          │
│   │       │ Worker polls + claims (FOR UPDATE SKIP LOCKED)       │          │
│   │       ▼                                                      │          │
│   │  ┌────────────┐                                              │          │
│   │  │ processing │ ← lease_expiry set, worker_id assigned       │          │
│   │  └─────┬──────┘                                              │          │
│   │        │                                                     │          │
│   │        ├─── SUCCESS ──→ ┌───────────┐                        │          │
│   │        │                │ completed  │ → Retained 7 days     │          │
│   │        │                └───────────┘   → then deleted       │          │
│   │        │                                                     │          │
│   │        ├─── FAILURE (retriable, attempts < max) ─────-┐      │          │
│   │        │                                              │      │          │
│   │        │    ┌──────────────────────────────────┐      │      │          │
│   │        │    │ visible_after = now + backoff    │      │      │          │
│   │        │    │ attempt_count++                  │      │      │          │
│   │        │    │ status = 'pending'               │◄─────┘      │          │
│   │        │    └──────────────────────────────────┘             │          │
│   │        │         │                                           │          │
│   │        │         └── (back to pending, waits for             │          │
│   │        │              visible_after before re-dispatch)      │          │
│   │        │                                                     │          │
│   │        ├─── FAILURE (attempts >= max_retries) ─-──┐          │          │
│   │        │                                          ▼          │          │
│   │        │                                    ┌─────────┐      │          │
│   │        │                                    │  dead   │      │          │
│   │        │                                    │  (DLQ)  │      │          │
│   │        │                                    └────┬────┘      │          │
│   │        │                                         │           │          │
│   │        │                              Replay ────┘→ pending  │          │
│   │        │                              Discard ──→ deleted    │          │
│   │        │                                                     │          │
│   │        └─── LEASE EXPIRED (no ACK/NACK) ──→ pending          │          │
│   │             (worker presumed dead)                           │          │
│   │                                                              │          │
│   └──────────────────────────────────────────────────────────────┘          │
│                                                                             │
│   TRANSITIONS:                                                              │
│   pending → processing     Worker claims job                                │
│   processing → completed   Handler succeeds                                 │
│   processing → pending     Handler fails (retry)  OR  lease expires         │
│   processing → dead        Handler fails (max retries exhausted)            │
│   dead → pending           Admin replays from DLQ                           │
│   dead → (deleted)         Admin discards                                   │
│   completed → (deleted)    Retention cleanup (7 days)                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 18: Brainstorming & Senior-Level Exercises

---

## A. Scale & Load Thought Experiments

### Experiment A1: Traffic Spike (10× Burst)

```
SCENARIO: Flash sale triggers 10× job enqueue rate for 30 minutes

AT 10× (5,000 jobs/sec for 30 minutes):
    Total jobs queued: 5,000 × 1,800 = 9 million jobs
    With 10 workers (50 jobs/sec): Backlog grows at 4,950 jobs/sec
    After 30 minutes: 8.9 million job backlog
    Drain time at 50 jobs/sec: 178,000 seconds = 49 hours (UNACCEPTABLE)

REQUIRED RESPONSE:
    Autoscale workers: 10 → 100 instances within 5 minutes
    At 100 workers (500 jobs/sec): Backlog grows at 4,500 jobs/sec
    Still insufficient during spike, but drain time after spike:
    8.1M / 500 = 16,200s = 4.5 hours (still long)
    
    REAL FIX: Autoscale to 200 instances during spike
    At 200 workers (1,000 jobs/sec): Backlog grows at 4,000 jobs/sec
    Spike ends: 7.2M backlog. Drain at 1,000/sec = 2 hours.
    
    ALTERNATIVE: Accept that batch jobs (reports, analytics) wait.
    Priority: High-priority jobs (email, payment) processed first.
    Low-priority jobs drain over hours—acceptable for batch work.

MOST FRAGILE ASSUMPTION: Worker autoscaling responds fast enough.
    If container startup takes 5 minutes and spike lasts 10 minutes,
    autoscaling only helps for the second half. Pre-warm strategy:
    Keep 30% headroom (13 workers instead of 10) to absorb initial burst.
```

### Experiment A2: Which Component Fails First at 10×

```
AT 10× SUSTAINED:

1. POSTGRESQL WRITE THROUGHPUT (FAILS FIRST)
   - 10,000 writes/sec (enqueue + status updates)
   - Single PostgreSQL instance: Can handle ~15,000 simple writes/sec
   - BUT: With indexes, WAL sync, replication: Effective limit ~8,000/sec
   - SYMPTOM: Enqueue latency increases (5ms → 200ms)
   - FIX: Connection pooling, batch inserts, table partitioning

2. POLLING CONTENTION (FAILS SECOND)
   - 100 workers, each polling 1/sec = 100 SELECT ... FOR UPDATE/sec
   - SKIP LOCKED helps but index scan still runs 100 times
   - SYMPTOM: Poll latency increases (100ms → 500ms)
   - FIX: Workers poll specific job types (partition the work)

3. WORKER MEMORY (FAILS THIRD for heavy job types)
   - 100 workers processing image resize simultaneously
   - Memory: 100 × 200MB = 20GB peak (manageable with right instance size)
   - But: If images are 10× larger during flash sale: OOM risk
   - FIX: Per-job memory limits, queue-based throttling for heavy types
```

### Experiment A3: Vertical vs Horizontal Scaling

```
WHAT SCALES VERTICALLY:
    - PostgreSQL: Bigger instance (more CPU, RAM, IOPS)
    - Effect: 2× capacity for ~3× cost
    - Limit: Single-instance ceiling (~30,000 writes/sec)

WHAT SCALES HORIZONTALLY:
    - Enqueue API: Add instances behind load balancer (stateless)
    - Workers: Add instances (stateless, poll from same queue)
    - Effect: Linear capacity increase
    - Limit: PostgreSQL becomes the bottleneck

SCALING STRATEGY:
    1×-5×: Scale workers horizontally, PostgreSQL vertically
    5×-15×: Partition job table, read replicas, optimize queries
    15×-50×: Shard PostgreSQL or migrate to purpose-built store
    50×+: Architecture change (separate queue per team/domain)
```

---

## B. Failure Injection Scenarios

### Scenario B1: Slow Dependency (Third-Party API 10× Latency)

```
SITUATION: CRM sync API response time increases from 200ms to 2 seconds

IMMEDIATE BEHAVIOR:
- sync_crm jobs take 10× longer to complete
- Worker threads occupied longer → fewer slots for other jobs
- If shared worker pool: Email and image jobs also delayed
- Queue depth for sync_crm grows

USER SYMPTOMS:
- CRM sync delayed (minutes → hours)
- If shared pool: Email delivery delayed too (collateral damage)

DETECTION:
- job_processing_duration{type="sync_crm"} P99 spike: 200ms → 2s
- queue_depth{type="sync_crm"} increasing
- If shared pool: queue_depth for other types increasing too

MITIGATION:
1. If separate worker pools: Only sync_crm affected. Other types unaffected.
2. If shared pool: Temporarily reduce sync_crm concurrency (1 thread/worker)
3. Circuit breaker: If error rate > 80%, pause sync_crm dispatch
4. Let jobs queue up (they're persisted, they'll process when CRM recovers)

PERMANENT FIX:
- Separate worker pools (V1.1)
- Per-job-type concurrency limits
- Timeout per job type: sync_crm = 5s (not 5 minutes default)
```

### Scenario B2: Repeated Worker Crashes (OOM)

```
SITUATION: New job type "generate_report" uses 1GB RAM per job.
Worker instances have 2GB RAM. 2 concurrent report jobs = OOM.

IMMEDIATE BEHAVIOR:
- Worker picks up report job → allocates 1GB
- Second report job on same worker → 2GB → OOM kill
- All in-flight jobs on that worker lost (leases will expire)
- Kubernetes restarts pod → same thing happens

USER SYMPTOMS:
- Reports never complete
- Other job types delayed (worker restarts interrupt them)
- DLQ fills with report jobs (if they make it through retries)

DETECTION:
- OOM kill events in container orchestrator logs
- Worker restart count increasing
- processing_rate dropping
- DLQ depth for "generate_report" increasing

MITIGATION:
1. Limit report concurrency to 1 per worker (--max-concurrent-reports=1)
2. Use larger instances for report workers (4GB RAM)
3. Emergency: Pause report job dispatch (circuit breaker)

PERMANENT FIX:
- Separate worker pool for heavy jobs (sized appropriately)
- Per-job memory estimation and resource-aware scheduling
- Job type registration includes resource requirements
```

### Scenario B3: Cache Unavailability (Redis Down)

```
SITUATION: V1 uses no Redis cache (PostgreSQL only). No impact.

IF V2 ADDED Redis for idempotency checks:

IMMEDIATE BEHAVIOR:
- Idempotency check fails → falls through to DB unique index check
- Slightly slower (10ms → 20ms) but functionally correct
- No job loss, no duplicate processing

USER SYMPTOMS:
- Slightly higher enqueue latency (barely noticeable)
- No functional impact

DETECTION:
- Redis connection error in Enqueue API logs
- idempotency_cache_miss_rate = 100%
- Enqueue P99 slightly elevated

MITIGATION:
- Automatic: Fall through to DB check (Redis is optimization, not requirement)
- Fix Redis (restart, replace node)

PERMANENT FIX: Redis cache is advisory. DB unique index is the true guard.
Never depend solely on cache for correctness.
```

### Scenario B4: Intermittent Network Latency (Packet Loss)

```
SITUATION: 5% packet loss between workers and PostgreSQL

IMMEDIATE BEHAVIOR:
- Poll queries intermittently fail or timeout
- Job ACKs intermittently fail
- Worker retries poll → eventually succeeds
- Failed ACK → job lease expires → re-dispatched (duplicate)
- Processing rate: ~70% of normal (30% lost to retries/timeouts)

USER SYMPTOMS:
- Background work slower (minutes instead of seconds)
- Occasional duplicate execution (email sent twice)

DETECTION:
- database_connection_error_rate increasing
- poll_timeout_rate increasing
- processing_rate decreasing
- Duplicate job detection (if tracked)

MITIGATION:
1. Workers retry with short backoff (1s, 2s, 4s)
2. Idempotent handlers absorb duplicates
3. If persistent: Network team investigates (NIC, switch, routing)

PERMANENT FIX:
- Connection pooler (PgBouncer) between workers and DB (handles reconnection)
- Idempotent handlers (already designed in)
- Health check: Worker marks itself unhealthy if DB unreachable for 30s
```

### Scenario B5: Database Failover During Peak Traffic

```
SITUATION: PostgreSQL primary fails; automatic failover to replica (15-second gap)

IMMEDIATE BEHAVIOR:
- Writes (enqueue): Fail for 15 seconds → producers get 503
- Reads (poll): Fail for 15 seconds → workers idle
- In-flight jobs: Continue executing (handler already has payload in memory)
- In-flight ACKs: Fail → lease will expire → re-dispatch after failover

USER SYMPTOMS:
- Background work pauses for 15-30 seconds
- Some jobs execute twice (ACK lost during failover)
- No jobs lost (persisted before failover)

DETECTION:
- Database health check fails → alert fires
- Failover event in database orchestrator logs
- Enqueue error rate spike → recovery
- Worker poll errors → recovery

MITIGATION:
1. Automatic: Replica promoted, connection strings updated (managed PostgreSQL)
2. Producers: Retry enqueue for 30 seconds (brief outage)
3. Workers: Retry polls → reconnect to new primary

PERMANENT FIX:
- Managed PostgreSQL with automatic failover (< 15s switchover)
- Connection pooler with automatic rerouting (PgBouncer, PgPool)
- Enqueue API: Client-side retry for 503 responses
```

### Scenario B6: Backlog Spiral (Enqueue Rate Exceeds Processing Rate for Hours)

```
SITUATION: Batch import job enqueues 2M jobs. Normal rate: 500/sec.
Processing rate: 50 jobs/sec. Time to drain: 2M / 50 = 40,000s = 11 hours.

IMMEDIATE BEHAVIOR:
- Queue depth: 0 → 2,000,000
- Oldest pending job age: 0 → increasing by 1s every second
- Normal priority jobs (emails, notifications) queued behind batch jobs
- Alert: "oldest_pending_job > 10 minutes"

USER SYMPTOMS:
- All background work delayed by hours
- Welcome emails arrive 6 hours after signup (terrible UX)

DETECTION:
- queue_depth alert fires immediately
- oldest_pending_job_age growing continuously
- Batch import identified as source (job type = "import_row")

MITIGATION:
1. Batch import jobs: Priority 1 (lowest). Normal jobs: Priority 5.
   → Normal jobs dispatched first. Batch import drains in background.
2. Autoscale workers: 10 → 50 instances
3. If needed: Rate-limit batch enqueue (100 jobs/sec instead of all-at-once)

PERMANENT FIX:
- Batch imports enqueue with low priority (always)
- Batch import API: Accepts "enqueue at most N per second" parameter
- Separate worker pool for batch jobs (isolated from time-sensitive jobs)
- Queue depth alert by priority: "high-priority queue depth > 100"
```

---

## C. Cost & Operability Trade-offs

### Exercise C1: Biggest Cost Driver

```
BIGGEST COST DRIVER: Worker compute ($620/month, 54% of total)

WHY:
- Workers run continuously, whether jobs exist or not
- Workers must be sized for job processing (CPU, memory)
- Worker count determined by peak load, not average

OPTIMIZATION:
- Autoscaling: Scale down to 3 workers during off-peak (saves $440/month)
- Spot/preemptible instances for non-critical job types (saves 60-70%)
- Right-sizing: If most jobs are I/O-bound (waiting for SMTP, APIs),
  smaller instances with more threads may be cheaper
```

### Exercise C2: Cost at 10× Scale

```
CURRENT: $1,150/month (500 jobs/sec)

AT 10× (5,000 jobs/sec):
    Enqueue API: 2 → 4 instances ($60 → $120)
    Workers: 10 → 100 instances ($620 → $6,200)
    PostgreSQL: r5.large → r5.2xlarge ($350 → $700)
    Storage: 200GB → 2TB ($23 → $230)
    Monitoring: $100 → $200
    
    TOTAL: ~$7,450/month (6.5× cost for 10× scale)
    
    WHY sub-linear: Database scales vertically (not 10×), monitoring
    grows slowly, Enqueue API is lightweight.

    Main driver: Workers (83% of cost at 10×)
```

### Exercise C3: 30% Cost Reduction

```
CURRENT: $1,150/month. TARGET: $805/month (-$345)

OPTION A: Autoscale workers (night/weekend scale-down) → Save $350/month
    Trade-off: Higher processing latency during scale-up (1-2 min)
    Risk: Low (jobs queue safely during scale-up delay)
    Recommendation: YES

OPTION B: Spot instances for workers → Save $400/month
    Trade-off: Workers preempted occasionally (2-5% of time)
    Risk: Medium (in-flight jobs interrupted, leases expire, re-dispatch)
    Recommendation: YES for non-critical job types (reports, analytics)
    NO for critical job types (payment sync, email)

OPTION C: Smaller PostgreSQL instance (r5.large → r5.medium) → Save $90/month
    Trade-off: Less headroom for peak writes
    Risk: Medium-high (if peak writes exceed capacity, enqueue fails)
    Recommendation: NO (database is the durability boundary, don't pinch here)

OPTION D: Reduce job retention (7 days → 3 days) → Save $10/month
    Trade-off: Less debugging history
    Risk: Low (most debugging within 24 hours)
    Recommendation: YES

SENIOR RECOMMENDATION:
    Option A + D = ~$360 savings (31%)
    If needed: Add spot instances for batch workers (Option B partial) = $500+ savings
```

### Exercise C4: Cost of an Hour of Downtime

```
COST OF JOB QUEUE DOWNTIME:

Direct cost:
    - Jobs not processing → user-facing async work stalled
    - Welcome emails: Not sent → poor first impression
    - Invoice generation: Delayed → customer complaints
    - Payment sync: Delayed → accounting discrepancies
    
    If jobs are LOST (not just delayed):
    - Invoices never generated → revenue leak
    - Payment confirmations never sent → support tickets
    
Indirect cost:
    - All services that depend on async processing are degraded
    - Engineering time: 2-4 engineers × 1 hour investigating = 2-4 hours
    - Customer support tickets from delayed actions
    
    Estimate: 1 hour of queue downtime = $5-20K
    (depending on job types: payment sync downtime is expensive,
    image resize downtime is annoying but not costly)

THIS IS WHY:
    - Enqueue path availability is 99.95% (durability boundary)
    - Jobs persist in PostgreSQL (survive restarts)
    - DLQ captures failures (nothing silently lost)
```

---

## D. Correctness & Data Integrity

### Exercise D1: Idempotency Under Retries

```
QUESTION: Job "send_invoice" retried 3 times. How do you ensure the
customer doesn't receive 3 invoices?

ANSWER:
    Option 1: Idempotency key in handler
        idempotency_key = "invoice:" + order_id
        Before sending: Check sent_invoices table for this key
        If exists: Skip (already sent)
        If not: Send, then record in sent_invoices table
        
        Race condition: Two workers check simultaneously, both see "not sent"
        Fix: INSERT ... ON CONFLICT DO NOTHING on unique (idempotency_key)
        First INSERT wins. Second is a no-op.
    
    Option 2: External system deduplication
        SMTP service accepts idempotency_key
        Sends email only if key not seen before
        (Pushes dedup responsibility to SMTP layer)
    
    PREFERRED: Option 1. Handler owns its own idempotency. Don't depend
    on downstream systems being idempotent—they often aren't.
```

### Exercise D2: Handling Duplicate Requests

```
QUESTION: Producer retries enqueue due to network timeout. How do you
prevent two identical jobs?

ANSWER:
    Producer provides idempotency_key with enqueue request.
    
    Enqueue API:
    1. INSERT INTO jobs (..., idempotency_key) VALUES (..., $key)
    2. ON CONFLICT (idempotency_key) DO NOTHING
    3. If conflict: SELECT job_id WHERE idempotency_key = $key
    4. Return existing job_id to producer (200, not 201)
    
    NET EFFECT: No matter how many times producer retries, only one job exists.
    
    IMPORTANT: idempotency_key should be producer-generated, scoped to
    the business operation. Example: "signup:user:789" not "random-uuid"
    (random UUID would be different on each retry, defeating the purpose).
```

### Exercise D3: Preventing Data Corruption During Partial Failure

```
QUESTION: Worker completes job, updates external system, then crashes
before ACK. What happens?

ANSWER:
    Timeline:
    T=0: Worker processes job (sends email)
    T=1: Email sent successfully (side effect committed)
    T=2: Worker crashes before updating job status to "completed"
    T=300: Lease expires → job re-dispatched
    T=301: New worker processes job → sends email again (duplicate)
    
    THIS IS AT-LEAST-ONCE DELIVERY IN ACTION.
    
    Prevention: Idempotent handler.
    - Before sending email: Check idempotency table
    - If already sent: Skip
    - This is why idempotency is non-negotiable

    ALTERNATIVE: Two-phase commit between job queue and email service
    → Impractical. Distributed transactions across different systems
    are fragile, slow, and often not supported.
```

### Exercise D4: Data Validation Strategy

```
VALIDATION LAYERS:

Layer 1: Enqueue API
    - Job type: Must be registered
    - Payload size: < 64KB
    - Payload schema: Valid JSON
    - Required fields present for job type
    - Priority and max_retries in valid range
    
    Reject invalid jobs at enqueue (fail fast, don't waste queue space)

Layer 2: Handler (at execution time)
    - Payload semantic validation (e.g., email address format)
    - Dependency reachability (can I connect to SMTP?)
    - Resource availability (is there enough memory for this image?)
    
    If validation fails: FatalError → DLQ (no retry, bad input)
    If dependency fails: RetryableError → retry with backoff

WHY two layers:
    Layer 1: Cheap, fast, catches obvious problems before persistence
    Layer 2: Expensive, catches runtime issues that can't be known at enqueue time
```

---

## E. Incremental Evolution & Ownership

### Exercise E1: Adding Job Priorities Under Tight Timeline (2 Weeks)

```
REQUIRED CHANGES:
- Add priority column to jobs table (SMALLINT, default 5)
- Update dispatch query: ORDER BY priority DESC, created_at ASC
- Update Enqueue API: Accept optional priority field
- Update partial index to include priority in sort order

RISKS:
- Priority inversion: Low-priority jobs starve if high-priority queue always has work
- Schema migration: Adding column to large table may lock table briefly
- Worker behavior change: Different dispatch order may surface latent bugs

DE-RISKING:
- Schema migration: ALTER TABLE ADD COLUMN with DEFAULT is instant in PostgreSQL 11+
- Priority starvation: Add monitoring for oldest_pending_job by priority.
  V1: Accept starvation risk. V1.1: Add minimum throughput per priority tier
- Rollout: Feature flag on enqueue (all jobs get priority=5 initially;
  switch to real priorities after verifying behavior)
- Testing: Replay production job patterns in staging with priorities enabled
```

### Exercise E2: Backward-Compatible Payload Schema Change

```
SCENARIO: resize_image handler needs a new field "quality" (JPEG quality parameter).
Old jobs don't have this field. Queue may contain old-format jobs.

SAFE PROCEDURE:

Phase 1: Handler supports both old and new format
    payload.quality = payload.get("quality", 85)  // Default if missing
    Deploy handler. Old jobs: Use default quality. New jobs: Use specified quality.

Phase 2: Producers start sending "quality" field
    Enqueue API: Accept new field. Old producers still work (field is optional).

Phase 3: After all old jobs drained (7 days retention)
    Optional: Make "quality" required in enqueue validation
    Optional: Remove default fallback in handler (all jobs have the field)

ROLLBACK:
    Phase 1: Rollback handler → old handler ignores "quality" field → safe
    Phase 2: Rollback producer → no "quality" sent → handler uses default → safe

WHY this works: Backward compatibility at every step. No breaking changes.
No flag day. No coordination between producer and handler deployments.
```

### Rushed Decision Scenario (Real-World Application)

```
RUSHED DECISION SCENARIO

CONTEXT:
- Launch deadline in 2 weeks; product requires "welcome email within 60 seconds"
- Ideal: Separate worker pool for email, per-type timeouts, circuit breaker
- Time pressure: Only time to ship one change safely

DECISION MADE:
- Single worker pool; all job types share same workers
- Timeout: 5 minutes for all types (no per-type timeout yet)
- No circuit breaker; rely on retry + DLQ

WHY ACCEPTABLE:
- Email volume at launch ~10/sec; one pool can handle it
- 5-min timeout is safe for email (SMTP usually < 30s); bad for long reports
  but report job type not in launch scope
- DLQ + alerts give visibility if something is wrong

TECHNICAL DEBT INTRODUCED:
- When report job type is added later, long runs will hold slots and delay email
- No circuit breaker: If SMTP is down, workers will churn through retries
  (wasted CPU, possible alert fatigue) until we add circuit breaker
- Fix timeline: Add worker pool separation and per-type timeout in next quarter;
  add circuit breaker when first "dependency down" incident happens

COST OF CARRYING DEBT:
- One incident likely: Report jobs delay email delivery; we fix with pool split
- Acceptable: Launch on time; pay down debt when we have data (actual job mix)
```

### Exercise E3: Safe Schema Rollout with Zero Downtime

```
SCENARIO: Need to add index idx_jobs_type_created for new admin query.
Table has 40 million rows.

SAFE PROCEDURE:

    CREATE INDEX CONCURRENTLY idx_jobs_type_created 
        ON jobs (type, created_at);
    
    CONCURRENTLY: Builds index without locking the table. Reads and writes
    continue normally during index creation. Takes longer (minutes) but
    no downtime.
    
    RISK: CONCURRENTLY can fail if there's a conflicting transaction.
    If it fails: Index is left in INVALID state. Drop and retry.
    
    VERIFICATION:
    1. Run in staging first (same data volume if possible)
    2. Monitor: Table lock wait events during creation
    3. After creation: EXPLAIN ANALYZE the admin query → verify index used
    4. Monitor: INSERT latency (new index adds write overhead)

ROLLBACK:
    DROP INDEX CONCURRENTLY idx_jobs_type_created;
    (Also non-locking)
```

---

## F. Deployment & Rollout Safety

### Rollout Strategy (Stages, Bake Time, Canary Criteria)

```
DEPLOYMENT STRATEGY: Rolling with canary

STAGES:
  1%  → 1 worker instance (canary)
  10% → 2 instances (if 10-worker fleet)
  50% → 5 instances
  100% → All instances

BAKE TIME:
  - After each stage: Wait 10 minutes before proceeding
  - Canary (1%): Wait 15 minutes (capture at least one full poll + process cycle)
  - Success criteria per stage: No error rate increase, no DLQ growth, no latency regression

CANARY CRITERIA (must hold to proceed):
  - job_failure_rate for affected types ≤ baseline (pre-deploy)
  - processing_duration_seconds P99 ≤ baseline + 10%
  - dlq_depth unchanged
  - No new worker restarts (OOM/crash)

ROLLBACK TRIGGER:
  - Error rate for changed job type(s) > 50% after 10 minutes at any stage
  - Worker crash rate increases (e.g. > 2 restarts in 10 min)
  - Processing duration for existing job types regresses > 20%
  - DLQ depth increases during rollout

ROLLBACK MECHANISM:
  - Revert to previous worker image/version (same rolling: 1 → 10% → 50% → 100%)
  - Or: Feature flag to disable new code path; redeploy with flag off
  - Pending jobs for reverted handler: Remain in queue; old code will process them when rolled out
  - Data compatibility: Handlers must be backward-compatible with in-flight payloads (no schema break)

ROLLBACK TIME:
  - Single worker revert: ~2 minutes
  - Full fleet revert (10 workers): ~15 minutes (rolling, with bake)
```

### Deploying a New Job Handler

```
DEPLOYMENT STRATEGY:

1. Deploy new handler code to workers (rolling update)
   - Workers process mix of old and new job types
   - New handler code must not break old job types
   
2. Rolling update: 1 worker at a time
   - Worker drains current jobs (completes in-flight work)
   - Worker restarts with new code
   - Worker begins polling again
   - Verify: No errors in logs, processing rate stable
   - Proceed to next worker

3. Canary: First 1 worker, wait 10 minutes
   - Check: Error rate, processing duration, DLQ for new job type
   - If OK: Roll to remaining workers

ROLLBACK TRIGGER:
- Error rate for new job type > 50% after 10 minutes
- Worker crash rate increases
- Processing duration for existing job types regresses

ROLLBACK:
- Revert deployment (workers restart with old code)
- New job type's pending jobs sit in queue until fix deployed
- No jobs lost
```

### Scenario: Bad Config/Code Deployment

```
SCENARIO: Bad config/code deployment

1. CHANGE DEPLOYED
   - New worker version with bug: resize_image handler uses wrong output path
   - Config change: lease_duration reduced from 300s to 30s (typo)

2. EXPECTED VS ACTUAL
   - Expected: Resized images written to correct path; leases unchanged
   - Actual (path bug): Images written to /wrong/path; downstream 404s
   - Actual (lease bug): Long-running jobs (e.g. report) re-dispatched every 30s;
     duplicate work, DB contention, possible duplicate side effects

3. BREAKAGE TYPE
   - Path bug: Subtle — jobs "succeed", business outcome wrong (broken images)
   - Lease bug: Immediate — spike in "processing" → "pending" transitions,
     duplicate executions, latency spike

4. DETECTION SIGNALS
   - Path bug: Customer reports "images missing"; or canary: sample check output path
   - Lease bug: processing_duration spike; jobs_completed_total >> jobs_enqueued_total
     (duplicates); queue_depth oscillating
   - Both: DLQ may grow if handler starts failing (e.g. disk full on wrong path)

5. ROLLBACK STEPS
   - Halt rollout at current stage
   - Roll back worker version to previous (rolling)
   - If config: Revert config deploy; restart workers to pick up old config
   - Verify: Error rate and processing_duration return to baseline
   - Inspect DLQ for jobs that failed during the bad deploy; replay after fix

6. GUARDRAILS ADDED
   - Config validation at deploy: lease_duration in [60, 3600]; reject invalid
   - Canary: Smoke test one job per handler type and verify outcome (e.g. object exists at path)
   - Runbook: "Rollback worker deployment" with exact commands and verification steps
```

### Emergency: Pausing a Specific Job Type

```
SCENARIO: Job type "sync_crm" is causing cascading failures.
Need to pause it without affecting other job types.

MECHANISM:
    Admin API: POST /admin/job-types/sync_crm/pause
    
    Implementation:
    - Set config flag: paused_job_types = ["sync_crm"]
    - Worker dispatch query adds: AND type NOT IN ($paused_types)
    - sync_crm jobs remain in queue (pending, not lost)
    - Other job types: Unaffected
    
    Resume: POST /admin/job-types/sync_crm/resume
    - Remove from paused list
    - Workers begin dispatching sync_crm again
    - Backlog drains

WHY this exists: Operational control. When a job type is causing damage
(flooding an external API, crashing workers), the fastest mitigation is
to pause it. Jobs are safe in the queue. Fix the issue, then resume.
```

---

## G. Interview-Oriented Thought Prompts

### Prompt G1: Clarifying Questions to Ask First

```
1. "What types of jobs are most common, and what's the expected processing time?"
   → Determines: Worker sizing, timeout values, pool separation

2. "What's the acceptable delay between enqueue and processing?"
   → Determines: Whether real-time dispatch is needed vs polling

3. "What happens if a job fails permanently? Is manual recovery needed?"
   → Determines: DLQ design, admin tooling requirements

4. "How many job types do we expect, and do they have different resource needs?"
   → Determines: Worker pool architecture, resource isolation

5. "What's the peak enqueue rate, and how long do peaks last?"
   → Determines: Queue capacity, autoscaling strategy, backpressure design

6. "Are any job types sensitive to ordering or uniqueness?"
   → Determines: Idempotency requirements, ordering guarantees
```

### Prompt G2: What You Explicitly Don't Build

```
1. WORKFLOW ORCHESTRATION (V1)
   "Each job is independent. If you need A→B→C chains, enqueue the next
   job upon completion of the current one. Full DAG orchestration (Temporal,
   Airflow) is a separate system with different complexity."

2. EXACTLY-ONCE DELIVERY
   "At-least-once with idempotent handlers achieves the same user-visible
   outcome without distributed transactions. Exactly-once is a theoretical
   guarantee that's impractical in production distributed systems."

3. JOB RESULT STORAGE
   "The queue tracks status (pending/completed/dead), not results.
   Results belong in the domain: email handler writes to email_log,
   image handler writes to object storage. The queue is infrastructure."

4. REAL-TIME PROGRESS TRACKING
   "V1: Job is pending, processing, or completed. No 'Step 3 of 7'
   progress. That's handler-specific and belongs in the domain service."

5. MULTI-REGION REPLICATION
   "V1: Single region. Cross-region job routing adds consistency challenges,
   latency for job claiming, and replication lag for status. Not V1."
```

### Prompt G3: Pushing Back on Scope Creep

```
INTERVIEWER: "What if we need to guarantee strict ordering of jobs per user?"

L5 RESPONSE: "I'd push back on strict ordering as a default requirement.
Strict per-user ordering means: only one job for user X can be in-flight
at a time. That serializes processing for each user and dramatically
reduces throughput.

I'd ask: which specific job types need ordering? For most job types
(send email, resize image), order doesn't matter. For the rare case
where it does (e.g., sequential state transitions), I'd implement
per-user locking in the handler, not in the queue. The job queue
stays simple; ordering logic stays in the domain where it belongs.

If we truly need ordered execution across all job types for a user:
That's a workflow engine, not a job queue. Different system, different
design."
```

```
INTERVIEWER: "Can we add real-time job progress updates?"

L5 RESPONSE: "For V1, I'd track job status (pending/processing/completed)
in the queue and leave progress tracking to the handler. If the handler
wants to report 'Step 3 of 7', it writes to its own domain-specific
storage or publishes events.

Adding progress to the queue means: handlers must call the queue API
during processing (coupling), the queue must handle high-frequency
status updates (write amplification), and every poll returns progress
data (read amplification).

The cost outweighs the benefit for V1. I'd revisit if we have a clear
use case where users are actively watching progress bars for background
jobs."
```

---

# Final Verification

```
✓ This chapter MEETS Google Senior Software Engineer (L5) expectations.

SENIOR-LEVEL SIGNALS COVERED:

A. Design Correctness & Clarity:
✓ End-to-end: Enqueue → Persist → Poll → Dispatch → Execute → ACK/Retry → DLQ
✓ Component responsibilities clear (Enqueue API, Job Store, Worker, DLQ Manager)
✓ PostgreSQL vs Redis vs Kafka justified with trade-off reasoning
✓ Lease-based dispatch for crash recovery

B. Trade-offs & Technical Judgment:
✓ At-least-once vs exactly-once (idempotent handlers)
✓ Polling vs push-based dispatch (simplicity wins at V1)
✓ PostgreSQL vs Redis (durability wins for job queues)
✓ Explicit non-goals and deferred features

C. Failure Handling & Reliability:
✓ Poison-pill scenario (realistic production failure, full post-mortem)
✓ Exponential backoff with jitter (thundering herd prevention)
✓ Circuit breaker per job type
✓ DLQ with replay/discard operations
✓ Lease expiry for crashed workers

D. Scale & Performance:
✓ Concrete numbers (500 jobs/sec, 43M jobs/day, 200GB storage)
✓ Scale growth table (1×-30× with breaking points)
✓ Autoscaling strategy for traffic spikes
✓ DB write throughput as most fragile assumption

E. Cost & Operability:
✓ $1,150/month breakdown
✓ Cost at 10× scale ($7,450/month)
✓ 30% cost reduction options with risk analysis
✓ On-call runbook (queue_depth, DLQ, oldest_pending_job alerts)

F. Ownership & On-Call Reality:
✓ Poison-pill production scenario with 7-step response
✓ Emergency job type pause mechanism
✓ Deployment strategy (rolling + canary, stages 1%→10%→50%→100%, bake time)
✓ Bad config/code deployment scenario (6-part template)
✓ Misleading signals & debugging reality (false-confidence table, real signals)
✓ DLQ as primary failure investigation tool
✓ Cost vs operability vs on-call trade-off table

G. Concurrency & Correctness:
✓ FOR UPDATE SKIP LOCKED (no deadlocks, natural load balancing)
✓ Idempotency patterns with code examples
✓ Race conditions enumerated with prevention
✓ Clock handling (database clock as single authority)

H. Interview Calibration:
✓ What Interviewers Evaluate table (signal | how assessed)
✓ Example Strong L5 Phrases; Common L4 / Borderline L5 templates
✓ What Distinguishes Solid L5 (failure, scale, non-goals, trade-offs, ops)
✓ L4 vs L5 mistakes with WHY IT'S L4 / L5 FIX
✓ Strong L5 signals and phrases; clarifying questions and non-goals
✓ Scope creep pushback examples

Brainstorming (Part 18):
✓ Scale: 10× spike analysis, component failure order, vertical vs horizontal
✓ Failure: Slow dependency, OOM, cache down, packet loss, DB failover, backlog spiral
✓ Cost: Biggest driver, 10× estimate, 30% reduction, downtime cost
✓ Correctness: Idempotency, duplicate prevention, partial failure corruption, validation
✓ Evolution: Priority addition, payload schema change, zero-downtime index creation
✓ Rushed Decision Scenario: Single pool for launch, technical debt, paydown plan
✓ Deployment: Rollout stages, bake time, canary criteria; bad config/code scenario; rollback
✓ Interview: Clarifying questions, explicit non-goals, scope creep pushback
```

---

*This chapter provides the foundation for confidently designing and owning a background job queue as a Senior Software Engineer. The core insight: a job queue's primary contract is durability—once a job is acknowledged as enqueued, it must eventually complete or be visibly failed in the DLQ. Every design decision flows from this: PostgreSQL over Redis for persistence, at-least-once delivery with idempotent handlers, lease-based dispatch for crash recovery, and the DLQ as the safety net that turns invisible failures into visible, actionable ones. Master the enqueue-persist-dispatch-retry lifecycle, enforce idempotency in every handler, and you can reliably process background work at any scale.*
