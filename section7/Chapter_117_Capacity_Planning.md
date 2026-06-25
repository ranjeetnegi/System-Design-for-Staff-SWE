# Chapter 117: Capacity Planning

```
┌─────────────────────────────────────────────────────────────────────┐
│                 CAPACITY PLANNING — AT A GLANCE                     │
│                                                                     │
│  Core thesis: Capacity planning is not predicting the future.       │
│  It is understanding your system's limits before users find them,   │
│  maintaining safe headroom, and reducing mean time to provision      │
│  so that growth never causes an outage.                             │
│                                                                     │
│  L5 signal: "We need more servers before the holiday."              │
│  L6 signal: Builds the capacity model from first principles,        │
│             instruments the utilization signals, defines the        │
│             alert thresholds, owns the lead time for provisioning,  │
│             and makes the cost vs reliability tradeoff explicit.    │
│                                                                     │
│  Key numbers:                                                       │
│    70% CPU utilization → latency starts degrading                  │
│    80% disk utilization → alert; 90% → emergency                   │
│    2× safety margin → survive a sudden 2× traffic spike            │
│    Little's Law: L = λW (queue depth = arrival rate × wait time)   │
└─────────────────────────────────────────────────────────────────────┘
```

> "Capacity planning is the art of being wrong in a direction that doesn't hurt you." — SRE maxim

---

## Overview

Every system has limits. CPUs saturate. Memory fills. Databases hit connection ceilings. Disks run out. The question is not whether your system will hit a limit — it is whether you will hit it during a planned growth phase that you controlled, or during a production incident that you didn't.

Capacity planning is the discipline that makes the difference. Done well, it means your system degrades gracefully under unexpected load and scales smoothly under expected growth. Done poorly, it means your site goes down on Black Friday, your database runs out of disk on a Tuesday morning, or you spend three times too much on infrastructure for years because no one ever right-sized the fleet.

This chapter covers the full discipline: the theory (queuing, bottlenecks, utilization), the practice (load testing, the 5-step model, database planning), and the Staff engineer's role (defining SLOs, building cost models, coordinating provisioning across teams).

---

## Part 1: Why Capacity Planning Fails

Before building the model, understand the two ways capacity planning fails in practice.

**Failure mode 1: Under-provisioning (the outage)**

The system runs at 90% CPU utilization in steady state. A new feature ships; traffic increases 20%. The system saturates. Latency spikes. The queue grows faster than it drains. Users see errors. Incident declared.

The root cause was not the new feature — it was operating with no headroom. A system at 90% utilization has no buffer for spikes, traffic ramps, or unexpected workload.

**Failure mode 2: Over-provisioning (the waste)**

The team is scared of outages, so they provision 10× their peak traffic. The system runs at 3% utilization in steady state. Cloud costs are $500K/year for a service that should cost $50K. The waste is invisible on no individual bill but enormous in aggregate.

Google's SRE practice documented this problem: teams routinely over-provision by 2–5× because the cost of over-provisioning is diffuse (it shows up on a cloud bill) while the cost of under-provisioning is immediate (it shows up as a P0 incident at 3 AM).

**The "we'll scale when we need to" trap**

Some teams skip capacity planning with the argument that cloud infrastructure can scale elastically. This works for CPU and memory (autoscaling provisions new instances in 60-120 seconds). It does not work for:
- Database connections (connection pools are bounded; new pods mean new connections; the DB hits its connection limit)
- Disk (a full disk is immediate, not gradual; you cannot autoscale disk without a migration)
- Stateful components generally (caches, message queues, coordinators)
- Anything with long provisioning lead times (bare metal, GPU clusters, network capacity)

**Why linear extrapolation fails**

"We're at 100K QPS now; next quarter we'll be at 200K QPS; so we need twice the servers." This fails because:
1. Systems have non-linear breaking points. At 70% utilization, latency starts to grow non-linearly. Doubling traffic doesn't double latency — it can increase it 5-10×.
2. New features add workload per request. 200K QPS of a heavier workload is not 2× the current load.
3. Correlated spikes. Multiple users doing the same thing at the same time (viral moment, product launch, TV ad) creates 10× spikes that linear extrapolation misses.

---

## Part 2: Queuing Theory — The Math Behind Capacity

You don't need a PhD in operations research to do capacity planning. But one formula explains almost everything about why systems break: **Little's Law**.

### Little's Law

**L = λW**

- **L** = average number of requests in the system (queue depth + in-flight)
- **λ** = average arrival rate (requests per second)
- **W** = average time a request spends in the system (latency)

The law is deceptively simple and universally applicable. It applies to any stable queue: HTTP request queues, database connection pools, Kafka consumer lag, even the checkout line at a grocery store.

**Example:**
- Your service receives 1,000 req/sec (λ = 1,000)
- Average latency is 50ms (W = 0.05 seconds)
- Average queue depth: L = 1,000 × 0.05 = **50 requests in flight at any time**

Now your latency degrades to 500ms under load:
- L = 1,000 × 0.5 = **500 requests in flight**
- If your thread pool is 100, you're now overloaded. Requests queue. Latency grows further.

### The Utilization Cliff

The relationship between utilization and latency is not linear. It follows a curve that is nearly flat from 0-60% utilization, then rises steeply, becoming nearly vertical at 100%.

```
Latency
  │
  │                                          ╱
  │                                        ╱
  │                                      ╱
  │                                    ╱
  │                                  ╱
  │                           ______╱
  │_________________________╱
  └────────────────────────────────────── Utilization
  0%        30%       60%      80%  90% 100%
```

At 70% CPU utilization: latency begins to noticeably increase.
At 80%: latency grows rapidly; small traffic increases cause large latency spikes.
At 90%+: requests queue; the queue grows faster than it drains; latency becomes unbounded.

**The practical rule:** Design for 50-60% utilization in steady state. This gives you headroom for a 2× spike (bringing you to 100-120%) before the system breaks. Operating above 70% in steady state means you are one incident away from the cliff.

### M/M/1 Queue Intuition

For a system with one server, Poisson arrivals, and exponential service times, the average queue length is:

**L = ρ / (1 - ρ)**, where ρ = utilization (λ/μ)

| Utilization (ρ) | Queue depth (L) |
|-----------------|-----------------|
| 50% | 1.0 |
| 70% | 2.3 |
| 80% | 4.0 |
| 90% | 9.0 |
| 95% | 19.0 |
| 99% | 99.0 |

The jump from 80% to 90% doubles the queue depth. From 90% to 95% it doubles again. This is why the utilization cliff feels sudden in production — the degradation accelerates as you approach saturation.

---

## Part 3: The Three Bottlenecks

Every system has one primary bottleneck. Finding it is the first step of capacity planning.

**CPU-bound:** The service spends most of its time computing (encryption, compression, JSON parsing, ML inference, regex). Symptoms: CPU at near 100% under load; adding more RAM or faster disk doesn't help; latency scales with CPU load.

**Memory-bound:** The service needs more working memory than it has. Symptoms: high GC pause frequency (JVM, Python); swap usage; OOM kills; cache eviction rate rising. Common in caching services, in-memory databases, JVM applications with large heaps.

**I/O-bound:** The service waits on network or disk. Symptoms: CPU is low but latency is high; throughput limited by network bandwidth or disk IOPS; most time spent waiting for responses from downstream services or database.

**Determining your bottleneck:**

```bash
# CPU
top -bn1 | grep "Cpu(s)"
# or in K8s: kubectl top pods

# Memory
free -m
# or: watch RSS growth under load

# Disk I/O
iostat -x 1
# look at %util column; >70% means I/O bound

# Network
sar -n DEV 1
# look at rxkB/s, txkB/s vs interface capacity

# Application-level: most time spent where?
# Use profiler (py-spy, async-profiler, pprof)
```

**Why this matters for capacity planning:** A CPU-bound service scales horizontally (more pods). A memory-bound service may need larger instance types, not more instances. An I/O-bound service scales until the downstream becomes the bottleneck. You must identify the constraint before you can plan for it.

### USE Method (Utilization, Saturation, Errors)

Brendan Gregg's USE method is the systematic approach for finding the bottleneck:

For every resource (CPU, memory, network, disk, GPU):
- **Utilization:** What % of capacity is being used?
- **Saturation:** Is there a queue building? (run queues, request queues, disk I/O wait)
- **Errors:** Are there error counts increasing? (disk errors, network drops, OOM events)

High utilization + high saturation + zero errors = capacity problem.
High errors at low utilization = bug or misconfiguration.

---

## Part 4: Load Testing — Finding the Real Limits

**The cardinal rule:** Never find out your system's limit from a production outage. Find it from a load test.

### Types of Load Tests

**Baseline test:** Run the system at expected production load (e.g., current peak). Measure: CPU/memory utilization, latency percentiles (p50, p95, p99), error rate. This establishes the current baseline.

**Stress test:** Gradually increase load beyond expected peak until the system breaks. Find: the saturation point (where latency goes non-linear), the breaking point (where error rate spikes), and which component breaks first.

**Soak test:** Run at expected load for an extended period (12-24 hours). Find: memory leaks, connection pool exhaustion, disk growth, GC degradation over time.

**Spike test:** Apply a sudden 10× traffic increase for a short period. Find: how the system behaves under a viral moment or failed-open upstream.

### Load Test Design

```python
# Example: k6 load test for an API endpoint
import http from 'k6/http';
import { check, sleep } from 'k6';

export let options = {
  stages: [
    { duration: '2m', target: 100 },   // ramp up to 100 users
    { duration: '5m', target: 100 },   // hold at 100
    { duration: '2m', target: 500 },   // ramp up to 500 (stress)
    { duration: '5m', target: 500 },   // hold
    { duration: '2m', target: 1000 },  // ramp up to 1000 (near-break)
    { duration: '5m', target: 1000 },  // hold
    { duration: '2m', target: 0 },     // ramp down
  ],
};

export default function () {
  let res = http.get('https://api.example.com/v1/items');
  check(res, { 'status was 200': (r) => r.status == 200 });
  sleep(1);
}
```

**What to measure during the test:**
- Latency: p50, p95, p99 at each load level
- Error rate: should be < 0.1% at target load
- CPU and memory utilization of each component
- Database: connection count, query latency, lock waits
- Which component saturates first (the bottleneck)

**Pitfalls in load testing:**
- **Testing from one client machine:** The client becomes the bottleneck, not the server. Use a distributed load testing tool (k6 cloud, Gatling, Locust in distributed mode).
- **Unrealistic traffic patterns:** Test with realistic request distributions. If 80% of traffic hits 20% of URLs, test that distribution — don't spread evenly.
- **Not testing the database:** Many load tests hit the API layer with cached responses. Test the full path including DB writes.
- **Not testing with production data volume:** A database with 1,000 rows behaves differently than one with 1 billion rows. Load test with representative data.

---

## Part 5: The Five-Step Capacity Planning Model

**Step 1: Measure current capacity**

For each service, establish:
- Current peak QPS (from dashboards, last 30 days)
- Current resource utilization at peak (CPU %, memory %, connection count)
- Current P99 latency at peak
- Confirmed headroom: what is the maximum QPS the service can sustain below 80% CPU?

The last number requires a load test or historical data from a traffic spike.

**Step 2: Project future demand**

Sources:
- **Traffic growth rate:** Historical month-over-month traffic growth. If traffic grows 15% MoM, in 6 months you will have 2.3× current traffic.
- **Feature roadmap:** New features change workload per request. A new ML-powered recommendation in the search path might 3× CPU per request.
- **Seasonal patterns:** B2C companies see 3-5× traffic on Black Friday. Gaming companies see 2× traffic on weekends.
- **External drivers:** New market launch, major partnership, viral moment (impossible to predict, must plan headroom for).

```
Projected QPS = Current QPS × (1 + monthly_growth_rate)^months_ahead × seasonal_multiplier
```

Example: 50K QPS today, 15% MoM growth, 6 months out, 2× Black Friday multiplier:
```
= 50,000 × (1.15)^6 × 2 = 50,000 × 2.31 × 2 = 231,000 QPS on peak Black Friday
```

**Step 3: Calculate headroom needed**

Standard headroom targets:
- **2× headroom above expected peak:** Can survive a 2× unexpected traffic spike
- **N+1 redundancy:** Can lose one datacenter/zone and still serve peak traffic
- **Black Friday / launch day:** Pre-provision to 3× expected load for planned peaks

Combined requirement:
```
Required capacity = Projected peak × 2 (headroom) × N+1 factor
```

**Step 4: Plan provisioning with lead time**

Different resources have different lead times:
- Cloud VMs (spot/on-demand): 60-120 seconds
- Cloud VMs (reserved): minutes
- Bare metal: 4-16 weeks
- GPU clusters: 6-12 months
- Network capacity increases: 2-8 weeks (depending on provider)
- Database disk: hours to days (depending on storage type)

**The provisioning calendar:**
- 12 months out: decide on bare metal vs cloud for next fiscal year
- 3 months out: reserve cloud instances for known peak events
- 4 weeks out: final pre-scaling for product launches
- 1 week out: validate auto-scaling configuration; run a pre-flight load test
- Day of: monitor closely; have rollback plan ready

**Step 5: Set alert thresholds**

Thresholds should give you enough time to act before the system breaks:

| Threshold | Action |
|-----------|--------|
| 60% CPU utilization | Watch — trending toward capacity limit |
| 70% CPU utilization | Investigate — why is utilization growing? |
| 80% CPU utilization | Alert — scale or reduce load within hours |
| 90% CPU utilization | Page on-call — imminent degradation |
| Disk > 80% full | Alert — provision more disk within 24h |
| DB connections > 80% of pool | Alert — risk of connection exhaustion |
| Error rate > 0.1% | Alert — may indicate capacity-related failures |

---

## Part 6: Database Capacity Planning

Database capacity is the hardest to plan for and the most expensive to get wrong. Unlike stateless application servers, databases cannot be horizontally scaled in seconds.

### Connection Pool Planning

Every database server has a maximum connection limit. PostgreSQL defaults to 100; MySQL to 151; many managed services allow configuration to 500-1,000.

Each application pod consumes connections from its pool:
```
Total connections = pods × connections_per_pod
```

Example:
- 50 application pods
- Each pod has a connection pool of 20
- Total connections consumed: 50 × 20 = **1,000 connections**

If your PostgreSQL is configured for `max_connections = 200`, you have just exhausted it. Every new pod that starts will fail to acquire connections. This is a capacity failure that no amount of horizontal autoscaling can fix — adding more pods makes it worse.

**PgBouncer / ProxySQL as the fix:** A connection pooler sits between the application and the database. It maintains a small pool of real database connections (e.g., 50) and multiplexes thousands of application connections onto them.

```
[50 App Pods × 20 conns = 1,000 app connections]
           ↓
      [PgBouncer]
      (50 real DB connections)
           ↓
      [PostgreSQL max_connections = 100]
```

**Connection planning formula:**
```
Max sustainable pods = (DB max_connections × 0.8) / connections_per_pod
```
80% ceiling leaves headroom for admin connections and replication.

### Disk Growth Planning

Databases grow. If you don't plan for disk growth, you will hit disk full at 3 AM.

**Measure:**
- Current database size (bytes)
- Monthly growth rate (from monitoring or `du -sh` over time)

**Project:**
```
Months until full = (Disk capacity - current size) / monthly_growth_rate
```

If current size is 2TB, disk is 3TB, and growth rate is 100GB/month:
```
Months until full = (3,000 - 2,000) / 100 = 10 months
```

Alert when < 6 months of runway remain. This gives enough time for a disk expansion or migration before an emergency.

**Common growth accelerators engineers forget:**
- Write-ahead logs (WAL) accumulate rapidly during high-write periods
- Replication slots hold WAL until the replica catches up — if a replica falls behind, WAL fills disk
- Indexes grow proportionally to the data they index
- MVCC dead tuples (PostgreSQL) accumulate until VACUUM runs

### Read Replica Planning

Read replicas offload read traffic from the primary. Capacity planning for replicas:
- How much of your traffic is reads vs writes?
- What is the replication lag at current write volume? (If lag > 1 second, you may have stale reads)
- If the primary fails and you promote a replica, can it handle 100% of traffic?

**The single-primary bottleneck:** Most relational databases are write-to-primary only. Write capacity does not scale horizontally with read replicas. If writes are the bottleneck, you need sharding or a different data model.

### Sharding Lead Time

Sharding a database that was not designed for sharding takes months. By the time you realize you need it, it is already too late for the immediate problem. Capacity planning forces you to ask "when will we need sharding?" 18 months before the answer becomes urgent.

**Signals that sharding is approaching:**
- Write throughput > 70% of single-node capacity
- Individual table size > 100GB (queries slow down on large tables)
- `pg_stat_activity` shows most connections waiting on lock

---

## Part 7: Autoscaling — What It Solves and What It Doesn't

Cloud autoscaling is powerful but widely misunderstood. It is not a substitute for capacity planning.

**What autoscaling solves:**
- Gradual traffic growth within the headroom of your instance type
- Daily traffic cycles (low at night, high during business hours)
- Unexpected short spikes (traffic doubles for 5 minutes, then returns to normal)

**What autoscaling does not solve:**

**Cold start latency:** When autoscaling adds a new pod, it takes 30-120 seconds for the pod to start, pass health checks, and receive traffic. During a spike, those 120 seconds of cold start mean the existing pods absorb 100% of the spike. If the spike is large enough, existing pods saturate before new ones are ready.

**Database connection exhaustion:** New pods mean new database connections. If you autoscale from 50 to 200 pods and each pod uses 20 connections, you've just tried to open 4,000 DB connections. If your DB limit is 1,000, the autoscale event makes things worse.

**Stateful workloads:** Caches, coordination services, and databases cannot be autoscaled like stateless APIs.

**Very large spikes:** A 10× traffic spike from a viral event cannot be absorbed by autoscaling alone. By the time autoscaling provisions enough pods, users have already seen errors.

**The right model:** Autoscaling handles smooth variation within a range. Manual pre-scaling handles known peaks (Black Friday, product launch). Capacity planning defines the range and the pre-scale targets.

```python
# Kubernetes HPA example with sensible thresholds
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: payment-service-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: payment-service
  minReplicas: 10        # never go below 10 — cold start risk
  maxReplicas: 100       # cap; above this, scale DB connections manually
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60   # scale at 60%, not 80% — leave headroom
```

Key: `averageUtilization: 60` not 80. Autoscaling at 60% means new pods are provisioned before the existing ones hit the latency cliff at 70%.

---

## Part 8: Right-Sizing Services

Right-sizing is the practice of matching instance/container resources to actual workload requirements. Under-sizing causes outages; over-sizing causes waste.

**The right-sizing process:**

1. Run the service in production at expected peak load
2. Measure actual CPU and memory usage at peak (p95, not average)
3. Set resource requests at p95 peak usage
4. Set resource limits at 1.5× requests (headroom for spikes)
5. Measure again after 2 weeks; adjust

```yaml
# Container resources after right-sizing measurement
resources:
  requests:
    cpu: "500m"        # measured p95 at peak: 450m → round up to 500m
    memory: "512Mi"    # measured p95 at peak: 480Mi → round up to 512Mi
  limits:
    cpu: "750m"        # 1.5× request
    memory: "768Mi"    # 1.5× request
```

**Common right-sizing mistakes:**

- **Default requests:** Teams copy-paste 100m CPU / 128Mi memory from a template and never revisit. The service may actually need 10× that — or 1/10.
- **No limits set:** Without CPU limits, a misbehaving pod can starve other pods on the same node. Without memory limits, an OOM kill takes down the pod.
- **Memory requests too low:** Unlike CPU, memory cannot be throttled. If a pod exceeds its memory limit, it is killed immediately. Set memory limits conservatively above your p99.

**Instance type selection:** For the cloud instance type (EC2 type, GKE machine type):
- CPU-bound workloads: compute-optimized instances (c5, c6g)
- Memory-bound workloads: memory-optimized (r5, r6g)
- I/O-bound workloads: storage-optimized (i3, i4i) or high-network instances
- General purpose (m5, m6g): default for most application services

**Spot / preemptible instances:** For stateless, fault-tolerant workloads, spot instances cost 60-90% less than on-demand. Capacity plan for N+1 redundancy across availability zones to handle spot preemption.

---

## Part 9: SLOs as Capacity Signals

An SLO (Service Level Objective) is a commitment to a level of service quality. It is also the definition of "enough capacity" for your service.

**Capacity planning in terms of SLOs:**

If your SLO is "P99 latency < 200ms at 99.9% availability," then your capacity is sufficient if and only if that SLO is being met. If P99 latency is 180ms at current traffic levels, you have 10% headroom before you breach the SLO. If traffic grows 10%, you may breach.

**Error budget as a capacity signal:**

An error budget is the amount of downtime/errors permitted under the SLO. If your availability SLO is 99.9%, you have 43.8 minutes/month of error budget.

- If you are burning error budget at 2× the expected rate, you are under-capacity for your SLO.
- If you have burned < 10% of your error budget, you may be over-provisioned.

**Using error budget for capacity decisions:**

| Error Budget Remaining | Implication | Action |
|------------------------|-------------|--------|
| > 90% | Comfortably under SLO | Normal operations; safe to do risky changes |
| 50-90% | On track | Monitor; confirm growth projections |
| 20-50% | At risk | Freeze risky changes; investigate capacity |
| < 20% | Danger | Scale immediately; root cause investigation |
| 0% | SLO breached | Incident; all hands on capacity |

---

## Part 10: Planning for Peak Events

Some capacity problems are predictable: Black Friday, product launches, marketing campaigns, Super Bowl ads. These require proactive planning, not reactive autoscaling.

**The peak event planning checklist:**

**4 weeks out:**
- [ ] Estimate expected traffic multiplier (e.g., "3× normal daily peak based on last year's data")
- [ ] Calculate required pod count: `pods_needed = (current_pods × multiplier) / current_CPU_util_target`
- [ ] Validate DB can handle the connection count from those pods
- [ ] Check if any downstream dependencies (payment provider, CDN, email service) have capacity limits
- [ ] Reserve cloud capacity (pre-warm reserved instances; notify cloud provider for very large events)

**1 week out:**
- [ ] Run a pre-flight load test at expected peak traffic
- [ ] Validate autoscaling configuration and limits
- [ ] Pre-scale to the target pod count in staging; validate it starts correctly
- [ ] Confirm monitoring and alerting are configured correctly for peak thresholds
- [ ] Designate on-call engineers for the event window

**Day of:**
- [ ] Pre-scale to target pod count before traffic starts (don't wait for autoscaling to kick in)
- [ ] Watch error rate, P99 latency, and DB utilization dashboards
- [ ] Have runbook ready for: scale-up emergency, DB connection exhaustion, disk alert
- [ ] Define the decision threshold for a degraded-mode response (e.g., "If error rate > 1%, disable non-critical features")

**Post-event:**
- [ ] Scale down pre-scaled resources after the event
- [ ] Document actual vs projected traffic (improve the model for next year)
- [ ] Post-mortem any capacity-related issues

---

## Part 11: The Cost Model for Capacity Decisions

Capacity planning is not just a reliability concern — it is a cost concern. Staff engineers must be able to reason about both sides of the tradeoff.

**Cloud cost model for a service:**

```
Monthly cost = (instance_count × hourly_rate × 730 hours)
             + (storage_GB × GB_rate)
             + (data_transfer_GB × transfer_rate)
             + (database_instance_count × db_hourly_rate × 730)
```

Example for a service with 20 m5.xlarge instances (4 vCPU, 16GB, $0.192/hr):
```
Compute = 20 × $0.192 × 730 = $2,803/month
```

At 3× over-provisioning: you are paying $2,803/month for the work of $934/month of compute.

**The reliability vs cost tradeoff:**

| Headroom | Monthly cost | Tolerance to unexpected spikes |
|----------|-------------|-------------------------------|
| 1.2× | Minimum | Any 20% spike causes degradation |
| 1.5× | Moderate | Handles routine spikes safely |
| 2× | Standard | Industry-standard headroom |
| 3× | Conservative | Used for payment systems, healthcare |
| 5× | Very conservative | Rare; justified only for life-safety systems |

The right headroom depends on the cost of an outage. For a payment service, 5 minutes of downtime may cost $500K in lost transactions. For an internal admin tool, 5 minutes of downtime costs $0 directly. The headroom should reflect the cost of failure.

**Capacity planning ROI model:**

Cost of an outage = revenue at risk × probability of outage × duration
Cost of headroom = extra instance cost per month

If an outage costs $100K and probability without headroom is 5%/month:
```
Expected monthly outage cost = $100K × 0.05 = $5,000/month
Extra headroom cost = $1,000/month
ROI of extra headroom = 5:1
```

This is the calculation that justifies capacity investment to finance and product.

---

## Part 12: War Stories

### Netflix — Capacity Planning for a New Country Launch

When Netflix launched in a new country, the capacity planning challenge was: how much traffic will there be on launch day? No historical data exists for a new market.

Netflix's approach: model the new country as a comparable existing country (similar population, broadband penetration, market position). Provision at 3× the model's estimate for the first week. Monitor closely. Scale down if the model overshot.

The result: some launches slightly over-provisioned (wasted some cloud spend for a week). No launches under-provisioned. The cost of 1 week of over-provisioning was trivially small compared to the cost of a degraded launch day.

**Lesson:** When historical data is unavailable, use comparable baselines and provision conservatively. The cost of over-provisioning for a short period is lower than the cost of a degraded launch.

### Slack — COVID Remote Work Surge (March 2020)

In March 2020, when companies worldwide switched to remote work, Slack's traffic increased 300% in a single week. Their capacity planning had modeled gradual growth; it had not modeled a global pandemic.

Slack's infrastructure team spent the weeks following the surge scaling aggressively while maintaining availability. Several ancillary services (presence updates, notification delivery) were temporarily throttled to protect core messaging.

**Lesson:** You cannot plan for black swan events. You can plan for headroom that absorbs the initial shock while you respond. Slack's 2× headroom gave them enough time to manually scale before the surge fully hit.

### Amazon — Black Friday Infrastructure

Amazon's Black Friday planning starts in January of the same year. The process:
1. Traffic modeling based on last year's actuals and projected growth
2. Capacity reservation with AWS (Amazon is its own largest cloud customer)
3. Load testing at projected Black Friday traffic in October
4. Pre-scaling on the Wednesday before Thanksgiving
5. 24/7 monitoring during the peak period (Thursday-Monday)

The scale: Amazon processes millions of orders per minute at peak. A 1-minute outage during Black Friday costs more than a typical day's revenue.

**Lesson:** At sufficient scale, Black Friday planning is a yearlong project, not a week's work.

### Google SRE — The 70% Rule

Google's SRE book documents a practice: no service is allowed to run above 70% resource utilization in steady state. This is enforced programmatically — if a service consistently runs above 70%, it is automatically flagged for capacity review.

The 70% ceiling provides:
- 1.43× headroom for unexpected traffic
- N+1 redundancy (losing one instance increases others to 87.5%, still under 90%)
- Time for the on-call to respond before the system saturates

**Lesson:** Operational discipline around utilization thresholds prevents the "we'll scale when we need to" failure mode.

---

## Part 13: L5 vs L6 Calibration Table

| Dimension | L5 (Senior SWE) | L6 (Staff SWE) |
|-----------|----------------|----------------|
| **Scope** | Plans capacity for one service they own | Plans capacity across multiple services and their dependencies |
| **Tooling** | Uses dashboards to monitor current utilization | Builds the capacity model; defines what gets measured and how |
| **Bottleneck analysis** | Identifies the bottleneck after symptoms appear | Identifies the bottleneck before it appears via load testing |
| **Database planning** | Aware of connection limits; asks DBA | Designs the connection pooling architecture; owns the DB growth projection |
| **Cost awareness** | Knows the service costs money | Quantifies the cost of headroom vs cost of outage; makes the tradeoff explicit |
| **Peak events** | Participates in pre-scaling for Black Friday | Owns the Black Friday capacity plan; coordinates across all dependent teams |
| **Autoscaling** | Configures HPA; sets reasonable thresholds | Identifies the services where autoscaling doesn't work; designs the manual scaling runbook for those |
| **SLOs** | Monitors SLO compliance | Uses SLO burn rate as a leading indicator for capacity problems |
| **Communication** | Reports capacity status when asked | Proactively communicates capacity risks to leadership 6 weeks out |
| **Process** | Follows the capacity planning process | Owns the capacity planning process for the team; improves it annually |

The L6 signal is not technical depth alone — it is the combination of proactive ownership (not waiting to be asked), cross-service scope (dependencies, not just my service), and business-language translation (cost model, not just "we need more servers").

---

## Part 14: Anti-Patterns in Capacity Planning

**1. The "we have autoscaling" fallacy.** Autoscaling is real and valuable, but it does not eliminate capacity planning. It eliminates the need to plan for smooth, gradual growth. It does not help with database connections, cold start latency, stateful services, or very large sudden spikes. Teams that outsource all capacity thinking to autoscaling discover this at 3 AM on Black Friday.

**2. Planning from average, not peak.** "Our service uses 20% CPU on average." Average is useless for capacity planning. If you have daily peaks at 70% and occasional spikes to 90%, your system is regularly near saturation. Always plan from P95 or P99 utilization, not average.

**3. Forgetting to model dependencies.** You plan for your service to handle 10× traffic. You forget that your service calls a downstream payment API with a rate limit of 1,000 req/sec. Your 10× traffic sends 8,000 req/sec to the payment API. The payment API is the bottleneck and you didn't model it.

**4. No lead time awareness.** "We'll provision when we need it." Bare metal takes 6 weeks. GPU clusters take 6 months. Some managed database sizes require 2-day migrations. If you don't know the lead time for your critical resources, you will be caught waiting when growth outpaces provisioning speed.

**5. Ignoring disk.** Application engineers think about CPU and memory because those cause latency. Disk is invisible until it's full. Then it's catastrophic (database stops accepting writes; Kafka stops accepting messages; logs stop writing, which hides errors). Disk capacity planning is the most commonly neglected.

**6. The "test on production" pattern.** Running without load tests because "we'll scale if we need to." The first real load test is the Black Friday traffic surge. This is how you discover your connection pool is insufficient after it fails in production.

**7. Not right-sizing after initial launch.** Services are often over-provisioned at launch ("we don't know what the load will be"). Then traffic stabilizes at 10% of provisioned capacity. No one revisits the provisioning. 2 years later the service costs 10× what it should.

---

## Part 15: Exercises

**Exercise 1:** Your service currently handles 50,000 QPS at 55% CPU utilization with 30 pods. Traffic is growing at 12% month-over-month. In how many months will you hit 80% CPU utilization? How many pods will you need at that point?

*Expected approach:*
```
Current QPS per pod = 50,000 / 30 = 1,667 QPS/pod
CPU/QPS = 55% / 50,000 = 0.0011% per QPS
80% CPU reached at QPS = 80 / 0.0011 = 72,727 QPS
Months to reach: 72,727 = 50,000 × (1.12)^n → n ≈ 3.4 months
Pods needed: 72,727 / 1,667 = 44 pods
```

**Exercise 2:** Your PostgreSQL primary has `max_connections = 300`. You have 40 application pods, each with a connection pool of 10. You're planning to scale to 100 pods for Black Friday. What problem will you hit? What is the solution?

*Expected approach:*
```
Current connections: 40 × 10 = 400 → already exceeding max_connections of 300
Solution: Add PgBouncer with pool_size = 250 (leaves 50 for admin/replication)
Application connects to PgBouncer; PgBouncer manages 250 real DB connections
Now 100 pods × 10 app connections = 1,000 app connections → PgBouncer → 250 DB connections → safe
```

**Exercise 3:** Your database disk is currently 800GB with a 2TB disk. Data grows at 80GB/month. You also have a replica that sometimes falls 2 hours behind, causing WAL accumulation of ~20GB per hour of lag. When should you alert on disk? What is the safe disk expansion timeline?

*Expected approach:*
```
Normal runway: (2,000 - 800) / 80 = 15 months
Worst case (2-hour replica lag adds 40GB): (2,000 - 840) / 80 = 14.5 months
Alert at 6 months runway = when disk reaches 2,000 - (6 × 80) = 1,520 GB
Alert threshold: 1,520 / 2,000 = 76% disk utilization
Expand to 4TB when disk reaches 1,520GB
```

**Exercise 4:** Design the capacity planning process for a startup launching a new consumer app. You have no historical data. Traffic is completely unknown. What is your approach for the first 90 days?

*Expected answer:*
- Start highly over-provisioned (3-5×) based on comparable apps in the same category
- Instrument everything: QPS, CPU, memory, DB connections, error rate, latency per endpoint
- Review utilization weekly for first 4 weeks; monthly after that
- Right-size after 4 weeks of stable production data
- Set up autoscaling with conservative targets (scale at 60% CPU, not 80%)
- Define the "viral moment" scenario: if you get mentioned on national news, what breaks first? Pre-test it.

---

## Part 16: Brainstorming Q&A

**Q: Your database suddenly has 5,000 connections when it normally has 200. The app is throwing "too many connections" errors. Walk through your diagnosis and immediate fix.**

The immediate cause is connection exhaustion. Diagnosis:

1. **Find where the connections are coming from:** `SELECT client_addr, count(*) FROM pg_stat_activity GROUP BY client_addr ORDER BY count DESC;`. This shows which application servers are holding the most connections.

2. **Check for idle connections:** `SELECT count(*) FROM pg_stat_activity WHERE state = 'idle';`. A large number of idle connections means the connection pool is not properly releasing connections. Often caused by a code path that opens a connection but fails to close it (exception thrown before `close()` is called).

3. **Check for waiting connections:** `SELECT count(*) FROM pg_stat_activity WHERE wait_event IS NOT NULL;`. Connections waiting on locks indicate a different problem — a long-running transaction is blocking others.

**Immediate fix options:**

A. If idle connections are the problem: restart the application pods to force connection pool reset. Implement a connection pool maximum idle time configuration.

B. If a rogue pod is holding connections: identify and restart or cordon that pod.

C. If it's a legitimate traffic spike: add PgBouncer immediately (can be done without restarting the database). Configure `pool_mode = transaction` (connections are returned to pool after each transaction, not held for the session lifetime).

**Permanent fix:** Add connection pooler (PgBouncer) in front of all databases. Set `max_connections` in the application pool to (DB max_connections × 0.8) / number_of_pods. Add a dashboard alert on DB connection count > 80% of max.

---

**Q: A team comes to you and says "we need 10× more servers for our upcoming launch." How do you respond?**

"Let's validate that with data before provisioning. Here's what I need to know:

1. What is the current P95 CPU and memory utilization at peak traffic?
2. What is your traffic projection for the launch — how did you arrive at 10×?
3. What is the query volume to your database at current peak, and what is the connection count?
4. Have you run a load test at the expected launch traffic level?
5. Are there any downstream dependencies with their own rate limits?

Once I have those answers, I can calculate whether 10× servers is right. If you're currently at 20% CPU utilization and 10× traffic puts you at 200% CPU, you'll need roughly 10× the pods. But if you're already at 60% utilization, 10× traffic needs more like 6× the pods to stay under 80%."

The pattern: challenge assumptions, ask for data, validate with a load test. "We need 10×" is an intuition, not a calculation. Your job is to replace the intuition with the math.

---

## Part 17: Code Examples — Monitoring Capacity Signals

### Prometheus Queries for Capacity Planning

```python
# CPU utilization per pod (want < 70%)
100 - (avg by(pod) (rate(container_cpu_usage_seconds_total[5m])) / container_spec_cpu_quota) * 100

# Memory utilization per pod (want < 80%)
container_memory_usage_bytes / container_spec_memory_limit_bytes * 100

# DB connection count vs limit
pg_stat_database_numbackends / pg_settings_max_connections * 100

# Disk utilization (alert > 80%)
(node_filesystem_size_bytes - node_filesystem_free_bytes) / node_filesystem_size_bytes * 100

# Request queue depth (Little's Law: L = λW)
# Approximation: rate × avg latency
rate(http_requests_total[1m]) * histogram_quantile(0.5, rate(http_request_duration_seconds_bucket[1m]))
```

### Capacity Planning Script

```python
# capacity_projection.py
from dataclasses import dataclass
from typing import List
import math

@dataclass
class ServiceMetrics:
    name: str
    current_qps: float
    cpu_utilization: float  # 0.0 to 1.0
    pod_count: int
    target_cpu_utilization: float = 0.70  # 70% target

@dataclass
class GrowthProjection:
    monthly_growth_rate: float
    months_ahead: int
    seasonal_multiplier: float = 1.0

def project_capacity(metrics: ServiceMetrics, growth: GrowthProjection) -> dict:
    # Project future QPS
    future_qps = (
        metrics.current_qps
        * (1 + growth.monthly_growth_rate) ** growth.months_ahead
        * growth.seasonal_multiplier
    )
    
    # Current QPS per pod
    qps_per_pod = metrics.current_qps / metrics.pod_count
    
    # Current CPU per QPS
    cpu_per_qps = metrics.cpu_utilization / metrics.current_qps
    
    # Future CPU at current pod count
    future_cpu_utilization = cpu_per_qps * future_qps
    
    # Pods needed to stay under target utilization
    pods_needed = math.ceil(
        future_qps / (qps_per_pod * (metrics.target_cpu_utilization / metrics.cpu_utilization))
    )
    
    return {
        "future_qps": future_qps,
        "future_cpu_without_scaling": future_cpu_utilization,
        "pods_needed": pods_needed,
        "pods_to_add": max(0, pods_needed - metrics.pod_count),
        "months_until_alert": months_until_threshold(
            metrics.current_qps, metrics.cpu_utilization,
            0.80, growth.monthly_growth_rate
        )
    }

def months_until_threshold(
    current_qps: float, current_cpu: float,
    threshold: float, monthly_growth_rate: float
) -> float:
    if current_cpu >= threshold:
        return 0
    qps_at_threshold = current_qps * (threshold / current_cpu)
    if monthly_growth_rate <= 0:
        return float('inf')
    return math.log(qps_at_threshold / current_qps) / math.log(1 + monthly_growth_rate)

# Example usage
metrics = ServiceMetrics(
    name="checkout-service",
    current_qps=50_000,
    cpu_utilization=0.55,
    pod_count=30,
)
growth = GrowthProjection(
    monthly_growth_rate=0.12,
    months_ahead=6,
    seasonal_multiplier=3.0,  # Black Friday
)
result = project_capacity(metrics, growth)
print(f"Black Friday peak QPS: {result['future_qps']:,.0f}")
print(f"Pods needed: {result['pods_needed']}")
print(f"Pods to add: {result['pods_to_add']}")
print(f"Months until CPU > 80%: {result['months_until_alert']:.1f}")
```

---

## Part 18: Five-Level Progression

**L1 (Junior SWE):** Monitors dashboards. Aware when CPU or memory is high. Escalates to senior when things look wrong. Does not yet own capacity decisions.

**L2 (SWE):** Configures autoscaling for their service. Knows the CPU and memory utilization of their pods. Understands that databases have connection limits.

**L3 (Senior SWE I):** Runs load tests before major launches. Identifies the primary bottleneck for their service. Understands Little's Law and the utilization cliff. Sets alert thresholds.

**L4 (Senior SWE II / L5):** Builds and maintains the capacity model for their service. Projects demand based on growth rate and seasonal patterns. Owns the peak event planning for their service. Knows the DB disk runway and connection pool headroom.

**L5 (Staff / L6):** Owns capacity planning across multiple services and their dependencies. Builds the cost model for the team's infrastructure. Defines the capacity planning process and ensures it is followed. Makes the reliability vs cost tradeoff visible to leadership. Identifies systemic capacity risks (shared databases near limit, shared message queues approaching throughput ceiling) before any individual service owner notices.

---

## Part 19: One-Liners for Recall

1. "Capacity planning is not guessing the future — it is understanding your limits before users find them."
2. "Little's Law: L = λW. If latency doubles at the same arrival rate, queue depth doubles."
3. "The utilization cliff: 70% CPU is where latency starts to grow non-linearly. 90% is where it becomes unbounded."
4. "Design for 50-60% utilization in steady state. That's your headroom for a 2× spike."
5. "Autoscaling handles smooth variation. It does not handle cold start latency, DB connection limits, or disk."
6. "DB connections = pods × pool_size. If that number exceeds max_connections, your autoscale event breaks the database."
7. "Disk is invisible until it's full. Then it's catastrophic. 80% disk = alert; 90% = emergency."
8. "Right-size after 4 weeks of stable production data. Not before launch, not never — after."
9. "Your SLO IS your capacity requirement. If you're burning error budget, you're under-provisioned."
10. "The cost of over-provisioning is diffuse (monthly bill). The cost of under-provisioning is immediate (P0 incident). Budget for the latter explicitly."
11. "Bare metal takes 6 weeks. GPU clusters take 6 months. Know your provisioning lead times."
12. "Black Friday capacity planning starts in January, not November."

---

## Part 20: Quick Reference — Capacity Signals by Component

| Component | Metric to Watch | Alert Threshold | Action |
|-----------|-----------------|-----------------|--------|
| Application CPU | CPU utilization % | > 70% | Investigate; scale if trending |
| Application Memory | Memory utilization % | > 80% | Check for leaks; increase limits |
| HTTP server | P99 latency | SLO threshold | Scale pods; check downstream |
| Database (primary) | CPU utilization | > 70% | Check for slow queries; scale read to replicas |
| Database | Connection count | > 80% of max_connections | Add PgBouncer; reduce pool sizes |
| Database | Disk utilization | > 75% | Plan expansion; schedule migration |
| Database | Replication lag | > 5 seconds | Check replica health; may need more I/O |
| Redis | Memory utilization | > 75% | Increase maxmemory or add shards |
| Kafka | Consumer lag | > 5 minutes | Scale consumers; check processing bottleneck |
| Load balancer | Connections per second | > 70% of limit | Scale load balancer instances |
| CDN | Origin hit rate | > 20% | Cache-miss storm; investigate TTL or invalidation |

---

## Part 21: Capacity Planning for Specific Architectures

### Microservices Capacity Planning

In a microservices architecture, every service has its own capacity model — but the models are not independent. Service A's capacity depends on service B's throughput limit. A cascade starts when B's latency increases: A's threads wait longer on B's responses, A's thread pool fills, A's queue backs up, and now A appears to be the bottleneck when B is the real one.

**Practical approach for microservices:**
1. Draw the dependency graph for your critical paths (checkout flow, authentication flow, etc.)
2. For each service in the critical path, document: max QPS, CPU at current peak, latency SLO
3. Calculate the chain: if the slowest service in the path takes 200ms, all upstream services need thread pools large enough to hold in-flight requests during that 200ms
4. Load test the full path end-to-end, not just individual services

**The dependency capacity constraint:**
```
Max throughput of the path = min(max throughput of each service in the path)
```

The chain is only as strong as its weakest link.

### Kafka / Message Queue Capacity Planning

Kafka capacity has three dimensions:

**Producer throughput:** How fast can producers write? Measured in MB/sec. Limited by: network bandwidth into brokers, disk write speed, replication factor (3× write amplification for RF=3).

**Consumer throughput:** How fast can consumers process? Measured by: consumer lag trend. If lag is growing, consumers cannot keep up with producers. Solution: increase partition count → enables more parallel consumers.

**Storage retention:** How long to retain messages? Storage = producer throughput × retention period. 100 MB/sec × 7 days = 60TB of storage. At 3× replication = 180TB.

```
Partitions needed = desired_throughput / throughput_per_partition
Consumer groups needed = partitions / max_consumers_per_group
Storage needed = throughput_MB_sec × retention_seconds × replication_factor
```

### Cache (Redis) Capacity Planning

Redis is memory-limited. Once memory is exhausted, it evicts keys (if `maxmemory-policy` is set) or rejects writes. Either way, cache effectiveness degrades.

**Memory projection:**
```
Memory needed = avg_key_size_bytes × number_of_keys × overhead_factor (typically 1.5-2×)
```

Redis overhead: each key has ~60 bytes of overhead beyond the value. A million 100-byte values = 160MB of values + 60MB of overhead = 220MB minimum.

**The cache capacity planning cycle:**
- Monitor `used_memory` trend over 4 weeks
- Project when `used_memory` will hit `maxmemory`
- Increase `maxmemory` before hitting the ceiling (requires a Redis restart or config reload)
- If per-instance limit is reached, migrate to a Redis Cluster (sharded)

---

## Part 22: Capacity Planning During a Product Launch

A new product launch has different capacity planning challenges from ongoing scaling:
- No historical data for the specific product
- Traffic may ramp rapidly (viral loop) or slowly (organic adoption)
- Feature flag rollout means traffic is partially on new code paths

**The launch capacity planning process:**

**Step 1: Model from comparables.** Find the most similar existing feature/product. Use its launch traffic curve as the baseline. Adjust for factors: audience size, virality, marketing budget.

**Step 2: Define the traffic scenarios.**
- Conservative: 20th percentile outcome (launch goes okay)
- Base: 50th percentile (expected launch)
- Optimistic: 80th percentile (launch goes better than expected)
- Viral: 95th percentile (gets featured on TechCrunch, goes viral)

Provision for the optimistic scenario. Have a runbook for the viral scenario (manual scaling steps, feature flags to disable non-critical paths).

**Step 3: Identify the new bottlenecks.** New code often has different hot paths than existing code. Profile the new feature at expected traffic. Find: is there a new database query that's expensive? A new external API call? A new computation that's CPU-heavy?

**Step 4: Test the launch path.** Load test the specific user journey (signup → activate feature → use feature) at expected launch traffic. Do not test only the existing paths.

**Step 5: Define the abort criteria.** "If P99 latency exceeds 2× SLO during the launch ramp, pause the rollout and investigate." Having the abort criteria defined before launch means the on-call doesn't have to make a judgment call under pressure.

---

## Part 23: Interview Application

**When asked "How would you plan capacity for this system?":**

Template (30-second answer that signals Staff-level thinking):

"I'd start by understanding the current state: what's the peak QPS, what's CPU and memory utilization at peak, and what's the primary bottleneck — CPU, memory, or I/O? Then I'd model the growth curve: what's the monthly traffic growth rate, are there seasonal patterns, are there any planned product launches that will spike traffic? With that, I can project when we hit the 70% CPU threshold and how many pods we'd need. The database is often the real constraint, so I'd separately model connection count growth and disk runway. For a known peak event like Black Friday, I'd provision to 3× the projected peak and validate with a load test 4 weeks out."

**The signal interviewers look for:**
- Do they mention the bottleneck question (CPU vs memory vs I/O)?
- Do they think about databases separately from application servers?
- Do they mention load testing?
- Do they understand the utilization cliff and why 70% matters?
- Do they think about lead time for provisioning?

---

## Part 24: Pre-Interview Drill

1. What is Little's Law? Give a concrete example of applying it.
2. Why does the relationship between CPU utilization and latency become non-linear above 70%?
3. You have 50 pods, each with a connection pool of 20. Your PostgreSQL allows 200 connections. What happens when you scale to 100 pods? What's the fix?
4. What are the three things autoscaling cannot solve?
5. What is the difference between a stress test and a soak test? What does each find?
6. Your disk is 80% full. How do you calculate when it will be 100% full?
7. What is the USE method? Name the three components.
8. How do you make the business case for 2× capacity headroom to a finance team?
9. What is the SLO-based definition of "enough capacity"?
10. You're planning capacity for a viral consumer app launch. No historical data exists. What's your approach?
11. How does connection pool planning differ between a service with 10 pods vs 200 pods?
12. What is the "provisioning lead time" for bare metal servers vs cloud VMs vs disk expansion?

---

## Part 25: KEY TAKEAWAYS

```
╔═══════════════════════════════════════════════════════════════════╗
║              KEY TAKEAWAYS: CAPACITY PLANNING                    ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║  1. Two failure modes: outage (under-provisioned) and waste       ║
║     (over-provisioned). Capacity planning minimizes both.         ║
║                                                                   ║
║  2. Little's Law: L = λW. Queue depth = arrival rate × latency.  ║
║     Latency growth means queue growth means more latency.        ║
║                                                                   ║
║  3. The utilization cliff: operate at 50-60% for steady state.   ║
║     70% = latency starts growing. 90% = unbounded queue.         ║
║                                                                   ║
║  4. Find the bottleneck first (CPU, memory, I/O) before          ║
║     planning. Scaling the wrong resource wastes money.            ║
║                                                                   ║
║  5. Autoscaling handles smooth variation. It does NOT handle:    ║
║     cold start, DB connections, stateful services, 10× spikes.   ║
║                                                                   ║
║  6. DB connection planning: pods × pool_size < max_connections.  ║
║     Fix: PgBouncer. Know this cold.                              ║
║                                                                   ║
║  7. Disk is catastrophic when full. Alert at 75%. Plan at 6-mo   ║
║     runway. Never let disk growth go unmonitored.                ║
║                                                                   ║
║  8. The 5-step model: Measure → Project → Headroom → Provision   ║
║     timeline → Alert thresholds.                                 ║
║                                                                   ║
║  9. SLO burn rate is a leading indicator for capacity problems.  ║
║     Fast burn = under-provisioned.                               ║
║                                                                   ║
║ 10. Black Friday planning starts in January. Know your lead      ║
║     times: cloud = minutes; bare metal = 6 weeks; GPU = months.  ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
```

---

## Part 26: Homework

**Assignment 1:** For a service you own or know well: measure its current peak CPU utilization (from dashboards or logs). Calculate the QPS it can handle at 80% CPU. How much headroom do you have? Calculate when it will hit the 80% threshold given the observed traffic growth rate.

**Assignment 2:** Design the capacity plan for a payment service (like Stripe checkout) handling Black Friday for a large retailer. Inputs: currently handles 5,000 QPS at 45% CPU with 20 pods, PostgreSQL with max_connections=500 and 30 pods × pool_size=15, disk at 60% of 2TB growing at 50GB/month. Expected Black Friday traffic: 5× normal. Write the full plan: connection pool check, pre-scale target, alert thresholds, post-event scale-down.

**Assignment 3:** Read Brendan Gregg's "Systems Performance" chapters 1-3 (free excerpts available). Write a one-page summary of: the USE method, the tool to use for each resource on Linux, and one surprising finding from the examples.

---

## Part 27: Additional War Story — Twitter's Fail Whale (2008-2010)

Between 2008 and 2010, Twitter's famous "fail whale" error page appeared so often it became a cultural meme. The root cause was a repeated under-capacity failure pattern.

Twitter was growing faster than anyone had predicted. Their Ruby on Rails monolith was not designed for the load. Specific incidents:

**The Super Bowl problem:** Every time a major public event occurred (Super Bowl, Oscars, elections), Twitter's traffic spiked 5-10× in seconds. Their infrastructure could not absorb sudden spikes of that magnitude. The system went down for minutes at a time on major event nights.

**The re-tweet cascade:** When a highly followed account tweeted, the fan-out to followers' timelines created a write storm. Their architecture (fan-out on write) meant a tweet from a celebrity with 1M followers created 1M write operations simultaneously.

**What they learned:**
1. Sudden spikes cannot be handled reactively — you need pre-scaled headroom
2. Fan-out on write architecture has non-linear capacity properties (a viral tweet creates quadratic load)
3. Caching is not optional at this scale — their database could not handle fan-out without Redis/Memcache

The engineering changes: fan-out on read for large accounts; aggressive caching; horizontal sharding of MySQL; pre-scaling for known events. By 2012, the fail whale was largely retired.

**Lesson for capacity planning:** Traffic patterns at consumer scale are inherently bursty and correlated. Individual users trigger in response to the same event simultaneously. Any capacity model that assumes Poisson arrivals will fail on event nights. Plan for 5-10× spikes, not 2×.

---

## Part 28: Capacity and the Error Budget Burn Rate

The SRE concept of "error budget burn rate" is one of the most powerful capacity planning signals available. It translates SLO compliance into a leading indicator rather than a lagging one.

**Error budget burn rate definition:**

A burn rate of 1 means you are consuming your error budget at exactly the expected rate (you will use 100% of your budget by the end of the window, nothing more). A burn rate of 2 means you will use your entire error budget in half the window. A burn rate of 14.4 means you will exhaust your budget in 5 days (one-month SLO window × 1/14.4 = 2 days... the Google formula).

**The capacity connection:**

A high burn rate often has a capacity root cause:
- P99 latency is elevated → the service is near saturation → burn rate rises
- Error rate is elevated → requests are failing → burn rate rises
- DB availability events → connection pool exhausted → burn rate rises

By monitoring burn rate, you see capacity problems BEFORE they become SLO breaches.

**Alert thresholds for burn rate:**

| Burn Rate | Meaning | Response |
|-----------|---------|----------|
| > 14.4 | Budget exhausted in 2 days | Page immediately; capacity emergency |
| > 6 | Budget exhausted in 5 days | Alert within 1 hour; investigate |
| > 3 | Budget exhausted in 10 days | Alert within 4 hours; schedule investigation |
| > 1 | Budget will be exhausted this month | Watch; plan capacity action |
| < 1 | On track or under-burning | May be over-provisioned |

This framework lets you prioritize capacity investment by SLO burn rate, not by engineer intuition about which service is "probably" capacity constrained.

---

## Part 29: Graceful Degradation Under Capacity Pressure

When capacity is exceeded, the worst outcome is total failure. The best outcome is graceful degradation — the system continues serving the most critical functions while shedding non-critical load.

**Degradation patterns:**

**Load shedding:** Reject requests above a threshold with a 503 response (or a specific retry-after header). The remaining 80% of requests succeed. Users see "service temporarily unavailable" rather than timeouts.

```python
# Simple token bucket rate limiter at the service level
class ServiceRateLimiter:
    def __init__(self, max_qps: int):
        self.tokens = max_qps
        self.max_tokens = max_qps
        self.last_refill = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.max_tokens)
        self.last_refill = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False  # shed this request
```

**Feature flags for degradation:** Use feature flags to disable non-critical features under capacity pressure:
- Disable recommendation engine (expensive ML computation)
- Disable activity feed (expensive fan-out read)
- Serve cached search results instead of real-time (avoid search index write under load)
- Disable analytics event logging (writes)

**Circuit breakers for downstream pressure:** If a downstream service is slow or failing, circuit breakers prevent your service from waiting indefinitely on its responses, freeing threads for requests that can succeed.

```python
# Circuit breaker states: CLOSED → OPEN → HALF-OPEN
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = "CLOSED"  # CLOSED = normal; OPEN = failing fast
        self.last_failure_time = 0

    def call(self, fn, *args, fallback=None):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                return fallback() if fallback else None  # fail fast

        try:
            result = fn(*args)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
            return result
        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
            raise
```

**The degradation plan:** Define before the event which features will be disabled at which thresholds. "If CPU > 85%: disable ML recommendations. If CPU > 90%: disable activity feed. If error rate > 2%: disable new user registrations." The plan is reviewed before the peak event and tested during the pre-flight load test.

---

## Part 30: Capacity Planning Process Template

A repeatable process for teams to follow quarterly:

**Quarterly Capacity Review Agenda (60 minutes):**

1. **Current state** (10 min): Review utilization metrics for the last 90 days across all services. Flag any services above 70% CPU or 80% disk.

2. **Trend analysis** (10 min): Calculate month-over-month growth rate for QPS, storage, and connection count. Project each to the next 6 months.

3. **Known events** (10 min): What product launches, marketing campaigns, or seasonal events are scheduled in the next 6 months? Estimate traffic multiplier for each.

4. **Bottleneck review** (10 min): Which service or component is most likely to hit capacity first? What is the specific limit?

5. **Action items** (10 min): For each capacity risk identified, assign an owner and deadline. Actions fall into: right-size over-provisioned services; provision additional capacity; instrument missing metrics; run a load test.

6. **Cost review** (10 min): What is the monthly infrastructure cost? What is the cost per unit (cost per 1,000 API calls, cost per user)? Is this trending in the right direction?

**Output:** A capacity document updated quarterly with: current state, 6-month projection, identified risks, and action items with owners and dates.

---

## Part 31: Capacity Metrics Reference Table

| Metric | Source | Normal | Alert | Emergency |
|--------|--------|--------|-------|-----------|
| CPU utilization | Prometheus/CloudWatch | < 60% | > 70% | > 85% |
| Memory utilization | Prometheus/CloudWatch | < 70% | > 80% | > 90% |
| P99 HTTP latency | APM (Datadog/New Relic) | < SLO × 0.7 | > SLO | > SLO × 1.5 |
| Error rate | APM | < 0.1% | > 0.5% | > 1% |
| DB CPU | DB monitoring | < 60% | > 70% | > 85% |
| DB connections | pg_stat_activity | < 60% of max | > 80% of max | > 90% of max |
| DB disk utilization | Disk monitoring | < 70% | > 80% | > 90% |
| DB replication lag | pg_stat_replication | < 1 second | > 10 seconds | > 60 seconds |
| Redis memory | Redis INFO | < 70% of maxmemory | > 80% | > 90% |
| Kafka consumer lag | Kafka metrics | < 30 seconds | > 5 minutes | > 30 minutes |
| SLO burn rate | SLO dashboard | < 1 | > 3 | > 14.4 |

---

## Part 32: Network Capacity Planning

Network capacity is often the forgotten dimension. Most engineers think about CPU and memory; few think about bandwidth until they're in a production incident.

**Key network metrics to track:**
- **Ingress/egress bandwidth per service** (in MB/sec or Gbps)
- **Network interface utilization** (% of NIC capacity used)
- **Cross-AZ data transfer** (costs money; unexpected spikes are expensive)
- **CDN bandwidth** (if serving static assets or media)

**Calculating network requirements:**
```
Network bandwidth = QPS × avg_request_size_bytes + QPS × avg_response_size_bytes
```

Example: 10,000 QPS, 1KB requests, 5KB responses:
```
= 10,000 × (1,024 + 5,120) = 61,440,000 bytes/sec ≈ 59 MB/sec ≈ 0.5 Gbps
```

A standard cloud VM has 10Gbps network capacity. This service uses 5% — not a concern. But if responses are 500KB (e.g., API returning full document bodies), you'd need 4.77 GB/sec = 38 Gbps — well above a single VM's capacity.

**Cross-AZ traffic:** Cloud providers charge for data transfer between availability zones (typically $0.01-0.02/GB). A high-throughput service that makes cross-AZ calls can generate thousands of dollars per month in unexpected network costs. Design to route within AZ for latency-sensitive calls; use cross-AZ for replication and durability.

**Network capacity alert:** If your NIC is > 70% utilized, latency increases and packet drops become likely. Monitor `sar -n DEV 1` (Linux) or CloudWatch `NetworkIn/NetworkOut`.

---

## Part 33: Capacity Planning and System Design Interviews

Capacity planning knowledge appears directly in system design interviews in several ways.

**When the interviewer asks for "back-of-envelope estimates"** — this is a micro capacity planning exercise. They want to see:
1. You start from first principles (users → daily active → actions per user → QPS)
2. You identify the primary bottleneck (storage? CPU? bandwidth?)
3. You size the infrastructure (how many servers, what kind of DB, how big a cache?)
4. You validate the numbers are reasonable (sanity check: does this match what you know about real systems?)

**Standard estimation framework:**
```
DAU (daily active users) = X
Actions per user per day = Y
QPS = (X × Y) / 86,400 seconds
Peak QPS ≈ average QPS × 3 (peak is ~3× average for most consumer apps)
```

**Storage estimation:**
```
Storage per day = QPS × avg_write_size × 86,400 seconds
Storage per year = Storage per day × 365
Add 20% overhead for indexes, replication, WAL
```

**Server count:**
```
Single server capacity (rule of thumb for a typical API): 10,000-50,000 QPS
Servers needed = Peak QPS / QPS_per_server
```

**Example — URL shortener:**
```
DAU = 100M users
1% create a new URL per day → 1M new URLs/day
100 URL creations/sec (write QPS)
10% redirect per URL per day → 10M redirects/day
115 redirects/sec (read QPS)
Read:write ratio = 115:1 ≈ 100:1

Storage per URL: ~500 bytes (URL + metadata)
Storage per day: 1M × 500 = 500MB/day
Storage per year: 500MB × 365 = 182GB/year
After 5 years: ~1TB → one medium SSD is fine for 5 years

Cache: cache top 20% of URLs that generate 80% of traffic
= 20% × 5 years × 1M URLs/day × 365 × 0.2 = 73M cached URLs
= 73M × 500 bytes = 36.5GB → fits in Redis on one large instance
```

This level of structured estimation signals capacity planning fluency to the interviewer.

---

## Part 34: Capacity Planning in Different Lifecycle Stages

**Pre-launch (0 users):**
- Provision conservatively for the first 90 days
- Instrument everything before launch (you need baseline data for future planning)
- Run a load test at expected launch traffic before going live
- Cost: over-provision intentionally; right-size after 4 weeks of data

**Hypergrowth (50%+ annual growth):**
- Lead time for provisioning is now a competitive advantage
- The capacity planning cycle shortens: monthly review instead of quarterly
- Automation becomes critical: manual right-sizing cannot keep up
- Staff capacity planners spend most of their time 3-6 months ahead

**Scale (stable growth, 10-20% annual):**
- Quarterly capacity review is sufficient
- Focus shifts to cost optimization (right-sizing, spot instances, reserved instances)
- The capacity planning model is mature; incremental improvements

**Decline (traffic declining):**
- Capacity planning becomes cost optimization: scale down aggressively
- Watch for cost-per-user metric increasing (fixed costs don't scale down automatically)
- Reserved instance purchases need to be re-evaluated

---

## Part 35: Capacity and Reliability Together — The Staff Engineer's View

Reliability and capacity are not separate disciplines — they are two sides of the same coin. Every reliability incident has a capacity component; every capacity decision has a reliability implication.

**The reliability-capacity matrix:**

| Scenario | Reliability Impact | Capacity Action |
|----------|-------------------|-----------------|
| Service at 90% CPU | P99 latency elevated; approaching SLO breach | Scale pods immediately |
| DB connections at 95% | New connections failing; cascading 500 errors | Add connection pooler; reduce pool sizes |
| Disk at 95% | Database stopped accepting writes; data loss risk | Emergency disk expansion |
| Kafka lag > 30 min | Event processing delayed; eventual consistency violated | Scale consumers; check for slow consumers |
| Redis evicting keys | Cache miss rate elevated; traffic hitting DB | Increase Redis maxmemory or add shards |

A Staff engineer sees these as one problem, not two. The reliability symptom is the signal; the capacity action is the fix. The capacity model is the tool that surfaces these problems before the reliability incident happens.

**The Staff engineer's ownership statement:**

"I own the capacity model for our team's services. I will review it quarterly, update it after major product changes, and surface risks to leadership when I see them. I will not wait for an on-call incident to discover we're over capacity."

This is a concrete, actionable commitment. It is what separates a Staff engineer's ownership of reliability from a Senior engineer's execution of reliability tasks.

---

## Part 36: Common Interview Questions with Signal Analysis

**"Tell me about a time you prevented an outage through capacity planning."**

Signal: Specific and proactive. The candidate identified a risk before it became an incident. They did the math (specific numbers, not vague). They communicated to stakeholders. The outcome was measurable (avoided outage, or reduced incident severity).

Weak answer: "I noticed the CPU was high and added more servers."
Strong answer: "I noticed our checkout service's CPU utilization was growing 8% per month. Projecting forward, we would hit 85% CPU 6 weeks before our Q4 holiday campaign, which historically drives 4× traffic. I ran a load test that confirmed we'd saturate at 2.5× current traffic. I presented the capacity plan to the team: provision 3× current pod count 2 weeks before the campaign, and add PgBouncer to handle the connection scaling. We pre-scaled as planned. During the holiday campaign, peak CPU was 72% — within headroom. No outage."

**"How do you decide between scaling vertically vs horizontally?"**

Signal: The candidate understands the tradeoffs, not just a rule of thumb.

Answer framework: Vertical (bigger instance) when: the service is memory-bound and memory cannot be distributed (Redis, in-memory caches); the service has high per-connection overhead (some databases); the workload has a single CPU-intensive critical path. Horizontal (more instances) when: the service is stateless; CPU is the bottleneck; the service can be load-balanced. In practice, most application services scale horizontally; most databases require a combination.

---

## Part 37: Capacity Planning Vocabulary

| Term | Definition |
|------|-----------|
| Little's Law | L = λW: queue depth = arrival rate × wait time |
| Utilization | % of a resource's capacity currently in use |
| Saturation | Queue building up because service rate < arrival rate |
| Throughput | Rate of successful request completions (requests/sec) |
| Headroom | Spare capacity above current utilization |
| Right-sizing | Matching resource allocation to actual workload requirements |
| Lead time | Time from decision to capacity being available |
| Error budget | Allowed failures/downtime under an SLO |
| Burn rate | Rate at which error budget is being consumed |
| Cold start | Latency for a new instance to become ready to serve traffic |
| Connection pool | Fixed set of pre-created database connections reused by application |
| Soak test | Load test run for an extended period to find slow resource leaks |
| Stress test | Load test that increases load past the breaking point |
| Pre-scaling | Provisioning in advance of a known peak event |
| USE method | Utilization, Saturation, Errors — systematic bottleneck analysis |

---

## Part 38: Capacity Planning Quick Math Reference

**QPS estimation:**
```
QPS = (DAU × actions_per_user_per_day) / 86,400
Peak QPS ≈ QPS × 3  (consumer apps)
Peak QPS ≈ QPS × 2  (B2B/enterprise apps)
```

**Storage estimation:**
```
Daily storage = QPS × avg_write_size_bytes × 86,400
Annual storage = daily × 365 × replication_factor
```

**Connection pool capacity:**
```
Safe max pods = (db_max_connections × 0.8) / pool_size_per_pod
```

**Headroom calculation:**
```
Safe max QPS at current pod count = current_QPS × (target_utilization / current_utilization)
e.g.: 50K QPS at 55% CPU → safe max = 50K × (70/55) = 63.6K QPS
```

**Months until capacity threshold:**
```
months = log(threshold_QPS / current_QPS) / log(1 + monthly_growth_rate)
```

**Disk runway:**
```
months_remaining = (total_disk - used_disk) / monthly_growth_GB
```

**Cache sizing:**
```
Cache size = number_of_hot_keys × avg_value_size × Redis_overhead_factor(1.5)
Hot keys ≈ top 20% of keys by access frequency
```

**Black Friday pod count:**
```
bf_pods = ceil(current_pods × bf_multiplier × (current_CPU_util / target_CPU_util))
```

---

## Part 39: The Capacity Planning Mindset for Staff Engineers

Capacity planning requires a mental shift that many engineers struggle with: thinking about *systems* rather than *services*, thinking *months* ahead rather than *today*, and thinking in *probabilities* rather than *certainties*.

**Systems thinking:** Your service's capacity is bounded by the weakest link in its dependency chain. A 10× scaled application server that calls a database at 90% capacity is not 10× better — it is worse. Staff engineers think about the full dependency graph, not individual components.

**Long-horizon thinking:** The time to discover a capacity problem is not when users are hitting errors. It is 3-6 months before, when you still have time to provision, migrate, or re-architect. The capacity model is a 6-12 month forward-looking tool, not a current-state dashboard.

**Probabilistic thinking:** Traffic is not deterministic. It has expected patterns and unexpected spikes. Capacity planning is not about predicting the future exactly — it is about choosing a confidence interval (e.g., "provision for 95th percentile traffic") and being explicit about what happens in the tail (the viral moment, the DDoS, the misrouted traffic).

**The Staff engineer's question:** "What will break first, and how long do we have?" Not "are we okay?" (almost always yes in the short term) but "where is the first cliff and when do we reach it?"

---

## Part 40: Building the Capacity Model Document

The capacity model is a living document, updated quarterly. Here is the standard structure:

**Service:** payment-service
**Last updated:** [date]
**Owner:** [engineer name]

**Current state:**
| Metric | Value | At peak QPS |
|--------|-------|-------------|
| Average QPS | 8,000 | 24,000 |
| P99 latency | 45ms | 120ms |
| CPU utilization | 35% | 65% |
| Memory utilization | 52% | 65% |
| Pod count | 20 | 20 |
| DB connections | 160 (of 500 max) | 300 |
| DB CPU | 30% | 55% |
| Disk used/total | 800GB / 2TB (40%) | — |
| Disk growth rate | 60GB/month | — |

**Projections:**
| Horizon | Expected QPS | CPU at current pods | Pods needed (70% target) |
|---------|-------------|---------------------|--------------------------|
| 3 months | 28,000 | 76% | 22 |
| 6 months | 33,000 | 89% | 26 |
| 12 months | 46,000 | >100% | 37 |
| Black Friday (×4) | 96,000 | >100% | 78 |

**Identified risks:**
1. DB connections at Black Friday: 78 pods × 10 pool_size = 780 connections > 500 max_connections. **Action: Add PgBouncer by 2026-10-01. Owner: @jane.**
2. Disk runway: (2,000 - 800) / 60 = 20 months. **No immediate action. Revisit in Q3.**
3. Pod count: need 26 pods in 6 months. Autoscaling covers this. **No action needed.**

**Cost model:**
| Resource | Monthly cost | Notes |
|----------|-------------|-------|
| Application pods (20 × m5.xlarge) | $2,803 | At reserved pricing |
| RDS PostgreSQL (db.r5.2xlarge) | $1,456 | Multi-AZ |
| Storage (2TB EBS) | $200 | gp3 |
| **Total** | **$4,459/month** | |

---

## Part 41: Further Reading and Study

**Books:**
- **"Systems Performance"** — Brendan Gregg. The definitive reference for system performance analysis. Chapters 1-3 cover the USE method and methodology. Read before your next capacity investigation.
- **"The Google SRE Book"** — Free online (sre.google). Chapter 17 ("Testing for Reliability") covers capacity testing; Chapter 21 ("Handling Overload") covers load shedding.
- **"Database Reliability Engineering"** — Laine Campbell, Charity Majors. Chapter on capacity planning for databases specifically.

**Tools:**
- **k6** — Load testing tool (free, open source). Write load tests in JavaScript. Cloud version for distributed testing.
- **Locust** — Python-based load testing. Good for complex scenarios with custom logic.
- **Prometheus + Grafana** — Industry-standard metrics stack. Capacity planning dashboards built on top.
- **Datadog** — Commercial APM with excellent capacity planning dashboards (forecast feature).

**Practice:**
- Set up Prometheus + Grafana locally; instrument a simple Python service; run a k6 load test; watch the metrics
- Calculate the capacity model for a well-known system (Twitter, Instagram, YouTube) from public data (scale estimates, engineering blog posts)
- Read the Slack COVID capacity post-mortem (public); identify what the capacity model would have told them 6 months earlier

---

## Part 42: Chapter Statistics

| Category | Count |
|----------|-------|
| Parts | 42 major sections |
| Frameworks | Little's Law, USE Method, 5-step model, error budget burn rate, graceful degradation |
| Code examples | Load test (k6), HPA configuration, capacity projection script (Python), circuit breaker, rate limiter, Prometheus queries |
| War stories | Netflix new country launch, Slack COVID surge, Amazon Black Friday, Google SRE 70% rule, Twitter fail whale |
| Exercises | 4 fully worked |
| Homework | 3 assignments |
| Pre-interview drill | 12 questions |
| One-liners | 12 recall anchors |

**Chapter in one sentence:** Capacity planning is the discipline of understanding your system's limits before users find them — using Little's Law, utilization metrics, load tests, and 6-month forward projections to maintain safe headroom while avoiding the cost of over-provisioning.

---

## Part 43: The Capacity Planning Anti-Pattern Gallery

**"The Dashboard Lie":** A team has a dashboard showing average CPU at 35%. They feel safe. The p99 CPU is 88% for a 15-minute window every day at 9 AM when the batch jobs run. Averages hide the spikes. Always look at percentiles.

**"The Dev/Prod Gap":** Load testing is performed in a dev environment with 5% of production data volume. The test passes. Production has a 500M-row table with 50 indexes. Index scans that take 2ms on dev take 800ms on prod. The load test was useless because it wasn't representative.

**"The Dependency Blind Spot":** A service can handle 100K QPS. It calls a shared user service that can handle 20K QPS total. The team's capacity plan is technically correct for their service and completely wrong for the system. Capacity planning without dependency mapping is incomplete.

**"The Reservation Trap":** A team reserved cloud instances for 1 year at a discount. Traffic declined after a feature sunset. They are now locked into paying for 3× their needed capacity for 11 more months. Reserved instance purchases should be made after the traffic pattern is stable, not as a speculative bet.

**"The Slow Leak":** Memory utilization grows 0.5% per day. No alert fires. After 6 months, the service is at 90% memory and starts OOM-killing under any traffic spike. Memory leaks are caught by soak tests (run the service for 24 hours at load; watch for non-monotonic memory growth).

---

## Part 44: Thirty-Day Capacity Planning Study Schedule

| Days | Focus | Activity |
|------|-------|----------|
| 1–5 | Little's Law and queuing | Prove Little's Law applies to your current service; calculate L at peak |
| 6–10 | Load testing | Set up k6; write a load test for a critical endpoint; find the breaking point |
| 11–15 | Database capacity | Calculate your DB connection headroom; project disk runway; measure replication lag |
| 16–20 | Cost model | Calculate monthly infra cost for one service; identify the highest-cost component |
| 21–25 | System design practice | Do 3 system design exercises where you complete back-of-envelope calculations |
| 26–30 | Interview prep | Drill the 12 pre-interview questions; practice the capacity planning story for a STAR question |

---

## Part 45: Capacity Planning and Architecture Decisions

Capacity constraints often surface the need for architectural changes. Recognizing when a capacity problem is actually an architecture problem is a Staff-level skill.

**When to re-architect vs when to scale:**

| Problem | Scale (add resources) | Re-architect |
|---------|----------------------|--------------|
| CPU-bound stateless API | Add more pods | Only if CPU/req is growing (algorithm problem) |
| Write-bound primary DB | Cannot scale writes horizontally | Shard, use event sourcing, denormalize |
| Fan-out writes at scale | Cache fan-out targets | Fan-out on read for high-follower accounts |
| Hot partition in DynamoDB | Scale DynamoDB | Redesign partition key to distribute load |
| Single-threaded bottleneck | N/A | Parallelize the computation |
| Linear scan on large table | N/A | Add index; partition the table |
| N+1 query problem | N/A | Fix the query pattern |

The pattern: if the problem grows faster than linearly with traffic (write amplification, hot partitions, quadratic queries), adding resources does not fix it — it just delays the inevitable. Capacity planning surfaces these problems; architecture changes fix them.

---

## Part 46: Wrap-Up — The Three Questions

Before finishing any capacity planning review, answer these three questions:

**1. What breaks first?**  
Identify the specific component (database, a specific service, disk on a specific server) that will hit its capacity limit first under projected growth. Name it. Quantify when.

**2. How long do we have?**  
Calculate the timeline: weeks? months? quarters? This sets the urgency level for the action plan.

**3. What is the action and who owns it?**  
Every identified risk must have: a concrete action (add PgBouncer, provision 20 more pods, migrate to larger disk), an owner (specific engineer), and a deadline (specific date before the problem occurs).

No capacity planning document is complete until all three questions are answered with specific, actionable responses.

---

## Part 47: The Capacity Mindset in One Paragraph

A system at 90% CPU utilization is not "running efficiently." It is one incident away from an outage. The engineers who built it may see a resource utilization dashboard and feel proud — "look how efficiently we use our infrastructure." But the 10% headroom is not safe headroom; it is borrowed time. At 90% utilization, Little's Law tells us the queue depth is 9× the queue depth at 50%. A small increase in traffic — a viral tweet, a marketing campaign, a partner integration going live — tips the system into saturation. The queue grows faster than it drains. Latency spikes. Users see errors.

The discipline of capacity planning is the discipline of saying, before anyone asks: "We are approaching our limit. Here is when. Here is what breaks. Here is what we're doing about it." That is what Staff engineers do. It is unglamorous, invisible when it works, and catastrophic when it doesn't. Do it.

---

> "An ounce of capacity is worth a pound of incident response." — Adapted from SRE practices

> "The time to find out your capacity limit is during a load test on a Tuesday afternoon, not during a production incident on a Friday night."

---

## Part 48: Capacity Planning for Messaging Systems

Async messaging (Kafka, SQS, RabbitMQ) has its own capacity dimensions that differ from synchronous services.

**The key metric: consumer lag.** If producers write faster than consumers read, lag grows. Growing lag means event processing is falling behind real time. For systems where freshness matters (notifications, recommendations, fraud detection), lag directly translates to degraded user experience.

**Capacity model for a Kafka consumer:**

```
Required consumer throughput (records/sec) = producer throughput × (1 + safety margin)
Required partitions = required throughput / throughput_per_partition
Required consumer instances = partitions (one consumer per partition maximum)
```

If a topic has 10 partitions and you have 20 consumer pods, 10 pods will be idle. You cannot process faster than the partition count allows. **Partition count sets the parallelism ceiling.**

**Planning partition count:**
- Set partitions at 10× your current consumer throughput requirement
- More partitions = more parallelism available in the future
- Caveat: partitions cannot be reduced; only increased (and increasing can be complex for key-ordered topics)

**Disk capacity for Kafka:**
```
Disk needed = producer_throughput_MB_sec × retention_seconds × replication_factor
```
Example: 100 MB/sec × (7 days × 86,400 sec) × 3 (replication) = 181 TB

This is why Kafka disk planning is non-negotiable — underestimating leads to a broker running out of disk and the cluster becoming unavailable.

---

## Part 49: Capacity Planning Templates

### Monthly Capacity Snapshot (one-pager format)

```
SERVICE: checkout-api        DATE: 2026-06-25        OWNER: @alice

CURRENT STATE:
  QPS (peak):      24,000      CPU (peak):   65%      Pods: 20
  P99 latency:     120ms       Memory:       62%      DB connections: 280/500
  Disk used:       800GB/2TB   Disk growth:  60GB/mo

PROJECTIONS:
  3-month QPS:  28,500   CPU: 77%  → ACTION NEEDED (>70%)
  6-month QPS:  33,500   CPU: 91%  → CRITICAL
  Black Friday: 96,000   CPU: ---  → MUST PRE-SCALE

RISKS:
  [HIGH] Black Friday DB connections: 78 pods × 10 = 780 > 500 max
         Action: Add PgBouncer by 2026-10-01. Owner: @bob
  [MED]  CPU at 77% in 3 months. Add 5 pods by 2026-09-01. Owner: @alice
  [LOW]  Disk runway: 20 months. Monitor; no action now.

COST THIS MONTH: $4,459
COST TREND: +3% MoM (aligned with traffic growth)
```

### Pre-Launch Capacity Checklist

```
PRE-LAUNCH CAPACITY REVIEW: [Product Name]   Date: [date]

TRAFFIC MODEL:
  [ ] Comparable product identified: [name]
  [ ] Conservative / Base / Optimistic traffic scenarios documented
  [ ] Viral scenario documented with manual scaling runbook

LOAD TEST:
  [ ] Load test run at Base traffic scenario
  [ ] Load test run at Optimistic traffic scenario
  [ ] Bottleneck identified and validated

SERVICES:
  [ ] All services in the critical path at < 60% CPU at Optimistic load
  [ ] DB connections validated at Optimistic pod count
  [ ] Downstream dependencies capacity-checked (rate limits, etc.)

MONITORING:
  [ ] Alerts configured for all capacity thresholds
  [ ] Dashboards available to on-call
  [ ] Degradation runbook written (which features to disable first)

CONTINGENCY:
  [ ] Abort criteria defined ("if P99 > [X]ms, pause rollout")
  [ ] Scale-up runbook written (manual steps if autoscaling insufficient)
  [ ] On-call coverage confirmed for launch window
```

---

## Part 50: Ten Things Staff Engineers Know About Capacity

1. **The utilization cliff is not theoretical.** Every production service that has run at 90% CPU has the latency spikes and P99 degradation to prove it. The curve is real.

2. **Little's Law is the most useful formula in distributed systems.** It applies to every queue — HTTP request queues, DB connection pools, Kafka consumer lag, task queues. Whenever latency grows, L = λW tells you why.

3. **Disk failures are catastrophic; disk planning is trivial.** The effort to monitor disk utilization and project runway is 30 minutes per quarter. The cost of a full disk is hours of downtime and potential data loss. This is the highest-ROI monitoring investment you can make.

4. **DB connection exhaustion is the most common autoscaling failure mode.** More pods = more connections. When connections exceed `max_connections`, all new connections fail. Autoscaling makes this worse, not better. PgBouncer (or equivalent) is the fix.

5. **Load tests must use production-representative data.** A test with 1,000 rows finds zero issues. The same test with 500M rows finds query plan regressions, missing indexes, and lock contention. The test environment must mirror production data volume.

6. **Reserved instances are a commitment, not just a discount.** Buying 1-year reservations for a service that might sunset or be resized is a trap. Buy reserved instances only for stable, predictable workloads.

7. **Capacity planning is a forcing function for understanding your system.** You cannot plan capacity for a system you don't understand. The exercise of building a capacity model forces you to answer: what is the primary bottleneck? What is the per-request cost? What are the downstream dependencies? This understanding has value beyond the plan itself.

8. **Pre-scaling for known peaks is always cheaper than reactive scaling.** The cost of running 50 extra pods for a week is trivial compared to the cost of a 30-minute Black Friday outage.

9. **The SLO is the definition of "enough."** "Enough capacity" means "the SLO is being met with acceptable error budget burn." Not "the CPU is at 50%." Define enough in terms of user experience, not resource utilization.

10. **Every capacity failure is a planning failure, not a traffic failure.** Traffic is not the cause of outages. Insufficient planning for known and unknown traffic growth is. Capacity failures are preventable. They are not acts of nature.

---

## Part 51: Extended Practice Scenarios

**Scenario A:** You're on-call at 2 AM. Alert fires: "DB connections at 95% of max_connections." The service is healthy; latency is normal. What do you do right now, and what do you fix tomorrow?

*Right now:* Check `pg_stat_activity` for idle connections being held unnecessarily. If possible, reduce pool_size config and rolling-restart a few pods to free connections. Open runbook for "connection exhaustion" — likely involves: identify rogue pods holding idle connections; restart them; verify connection count drops.

*Tomorrow:* Add PgBouncer. Reduce per-pod pool_size. Set up an alert that fires at 80% (not 95%) to give earlier warning.

**Scenario B:** Your service has been running smoothly at 40% CPU for 6 months. A new ML feature is added to the recommendation path. Two weeks later, CPU is at 78%. No traffic increase. Diagnose and fix.

*Diagnose:* The ML inference is CPU-intensive. Profile the new code path: what fraction of requests now hit the ML path? What is the CPU cost per ML inference? Calculate: if X% of traffic goes to ML path and ML uses Nms of CPU, what is the aggregate CPU impact?

*Fix options:*
1. Cache ML predictions (if user preferences are stable, cache the recommendation for 5 minutes)
2. Move ML inference to a separate service with dedicated GPU instances
3. Optimize the model (quantization, pruning)
4. Roll out the feature more slowly until CPU is right-sized

**Scenario C:** Your startup is planning its first Black Friday. You've been live for 8 months. Last year's traffic (before you): none. This year's projection: 3× your current peak. You have 3 weeks. What do you do?

*Three weeks out:*
1. Run a load test at 3× current peak now. Find what breaks.
2. Fix the identified bottleneck (likely DB connections or a specific slow query)
3. Pre-scale manually to 3× pod count 24 hours before Black Friday
4. Configure autoscaling with a minimum floor equal to the pre-scaled count
5. Write the degradation runbook: if CPU > 85%, disable non-critical features X and Y
6. Confirm the on-call rotation and runbook access

---

## Part 52: Capacity Planning Reference Card

| Situation | Formula / Rule |
|-----------|---------------|
| When does utilization become a problem? | > 70% CPU → latency grows; > 90% → catastrophic |
| How much headroom? | Design for 50-60% steady state → 2× spike headroom |
| How many pods for target QPS? | pods = (target_QPS / QPS_per_pod) × (current_CPU / target_CPU) |
| When to alert on disk? | > 75% used OR < 6 months runway |
| Connection pool max pods? | pods ≤ (db_max_connections × 0.8) / pool_size |
| Months until capacity threshold? | log(threshold_QPS / current_QPS) / log(1 + monthly_growth_rate) |
| Queue depth estimate? | L = λW (Little's Law) |
| Black Friday pod count? | ceil(current_pods × bf_multiplier × (cpu_util / target_cpu)) |
| Cache sizing? | hot_keys × avg_value_bytes × 1.5 (Redis overhead factor) |
| Kafka disk? | throughput_MB_sec × retention_sec × replication_factor |
| Safe autoscaling CPU target? | 60% (not 80%) — provision before the cliff |
| Reserved instance timing? | Buy after 3-4 months of stable traffic; not at launch |

---

> "Capacity planning done well is invisible. You never see the outage that didn't happen." — The reason it's worth doing.

---

## Part 53: Capacity Planning at Different Company Sizes

**Startup (1-50 engineers):**
- Capacity planning is informal: "does it work right now?"
- The right approach: instrument early, right-size after 4 weeks of real data, use autoscaling with conservative targets
- Common mistake: over-provision at launch (expensive) or under-provision and fix reactively (risky)
- One engineer owns capacity awareness across all services

**Mid-size (50-500 engineers):**
- Capacity planning is emerging: quarterly reviews, first dedicated SRE or platform team
- The right approach: formalize the capacity model document; define standard alert thresholds; run load tests before major launches
- Common mistake: each team plans independently with no cross-team view; shared resources (shared DB, shared message bus) hit limits no individual team planned for
- A designated capacity planning owner per major service area

**Large (500+ engineers):**
- Capacity planning is a discipline with tooling: automated capacity projections, dedicated capacity engineering teams, budget forecasting tied to capacity models
- The right approach: automated capacity review triggered by utilization trends; reserved instance management automation; cross-team capacity reviews for shared infrastructure
- Common mistake: capacity planning becomes bureaucratic and disconnected from engineering reality; teams optimize for the capacity model rather than actual reliability

The discipline scales with the organization. At any size, the fundamentals remain: measure, project, headroom, provision, alert.

---

## Part 54: Capacity Planning Checklist for Every Quarter

```
QUARTERLY CAPACITY REVIEW CHECKLIST

Services:
[ ] Every service's peak CPU, memory utilization reviewed
[ ] Any service > 70% CPU flagged for action
[ ] Any service with < 6 months disk runway flagged

Database:
[ ] DB connection count at peak < 80% of max_connections
[ ] DB disk growth projected; runway > 9 months
[ ] Read replica lag within SLO

Growth projections:
[ ] Traffic growth rate calculated (MoM)
[ ] Known product launches / seasonal events identified
[ ] 6-month QPS projection documented

Actions:
[ ] Every identified risk has an owner and deadline
[ ] Reserved instances reviewed for cost optimization
[ ] Over-provisioned services right-sized

Cost:
[ ] Monthly infra cost documented
[ ] Cost per unit metric calculated and trending correctly
[ ] Any unexpected cost spikes investigated

Load testing:
[ ] Critical paths tested at 2× current peak
[ ] Any services with upcoming launches tested at launch load
[ ] Autoscaling validated (test by manually scaling down; watch autoscaler recover)
```

---

## Part 55: Final Summary

Capacity planning is the practice of owning the future of your system's health — not waiting for users to find the limit, but finding it yourself, in a controlled way, with enough lead time to act.

The technical foundations:
- **Little's Law** explains why queue depth grows faster than traffic
- **The utilization cliff** explains why 90% utilization is catastrophic, not just "full"
- **The USE method** gives a systematic way to find the bottleneck
- **Load testing** finds the empirical limit, which is always more reliable than the theoretical one

The operational practices:
- The **5-step model** (measure → project → headroom → provision timeline → alert thresholds) is the core loop
- **Database capacity** needs its own model: connections, disk, replication lag
- **Autoscaling** handles smooth variation; manual planning handles known peaks and stateful components
- **SLO burn rate** is the best leading indicator for capacity problems

The Staff engineer's contribution:
- Own the cross-service capacity view, not just your own service
- Make the cost/reliability tradeoff explicit in numbers
- Communicate risks proactively, 6-12 weeks before they become incidents
- Ensure every capacity risk has an owner, an action, and a deadline

> "The engineers who prevent outages are rarely celebrated. The engineers who respond to outages are always celebrated. Be the former anyway."

---

## Companion Resources

- **"Systems Performance"** — Brendan Gregg (USE method, bottleneck analysis, Linux performance tools)
- **"Site Reliability Engineering"** — Google SRE Book, free at sre.google (Chapter 17: Testing for Reliability; Chapter 21: Handling Overload)
- **"Database Reliability Engineering"** — Laine Campbell & Charity Majors (database-specific capacity planning)
- **Brendan Gregg's blog** — brendangregg.com — flame graphs, Linux performance analysis, USE method examples
- **k6 documentation** — k6.io — load testing tool reference
- **Google SRE Workbook** — Chapter on SLO implementation (error budget burn rate formulas)

## Vocabulary Quick Reference

| Term | One-line definition |
|------|---------------------|
| Little's Law | L = λW: queue depth = arrival rate × latency |
| Utilization cliff | Non-linear latency growth above 70% CPU utilization |
| USE method | Utilization + Saturation + Errors — systematic bottleneck analysis |
| Headroom | Capacity above current utilization; buffer for unexpected spikes |
| PgBouncer | Connection pooler that multiplexes application connections onto fewer DB connections |
| Cold start | Delay for new pod/instance to become ready to serve traffic |
| Error budget burn rate | Rate of SLO error budget consumption; leading indicator of capacity problems |
| Soak test | Extended load test to find slow resource leaks |
| Pre-scaling | Provisioning in advance of a known peak event |
| Disk runway | Time until disk is full at current growth rate |

---

## Part 56: Interview Cheat Sheet

**If asked "how would you capacity plan this system?" — answer in this order:**

```
1. MEASURE — baseline QPS, p99 latency, CPU%, memory%, DB connections
   "First I'd want to know current utilization vs. theoretical limits."

2. HEADROOM — current vs. limits, safety margin target
   "We should be operating at no more than 70% CPU — where are we?"

3. GROWTH — MoM growth rate, seasonal multipliers, known events
   "Traffic typically grows 8% MoM with a 3× peak at end-of-quarter."

4. PROJECT — when do we hit the cliff?
   "At current growth, we hit 70% CPU in ~3 months."

5. PROVISION — lead time to act
   "Kubernetes can add nodes in 5 minutes; DB sharding takes 6 months."

6. ALERT — set SLO burn rate thresholds before it's urgent
   "Alert at 50% CPU so we have runway to provision without a fire drill."
```

**Three numbers to know cold:**
- 70% — CPU utilization where latency starts degrading non-linearly
- 2× — minimum safety margin for peak events above daily peak
- 6 months — minimum lead time for any major infrastructure change (sharding, new region, hardware)

**The one-sentence answer for any capacity question:**
> "Measure the bottleneck, project growth, and ensure your provision lead time is shorter than your runway."

---

## Part 57: Closing Principles

1. **Boring is the goal.** A capacity planning process that runs weekly with no surprises is a success. An outage from unexpected growth is a failure.

2. **Utilization is a lagging indicator.** By the time CPU hits 90%, users are already experiencing latency spikes. Use error budget burn rate as the leading indicator.

3. **Every estimate has an owner.** A capacity projection that no one is accountable for is not a plan — it is a spreadsheet.

4. **Seasonal patterns are predictable; engineer them.** Black Friday, fiscal year-end, product launches — these are not surprises. Pre-scale before the event, not during.

5. **The system that scales the hardest is often not the one you think.** Measure everything; assume nothing. The bottleneck is almost never where you expect.

6. **Graceful degradation is the last line of defense, not the first.** Load shedding keeps the service alive, but the real goal is to never need it.

---

## Memorable Quotes

> *"Everyone has a plan until they get punched in the face."* — Mike Tyson (applies to capacity plans that were never load tested)

> *"The goal of capacity planning is to be boring."* — Google SRE team

> *"You can't manage what you can't measure."* — Peter Drucker

> *"Our job is not to predict the future. Our job is to make the future predictable."* — paraphrase, Netflix SRE

> *"A 6-month lead time is not a constraint — it's a deadline you give yourself today."* — database sharding war story

---

## Final Checklist Before You Ship

- [ ] Load test at 2× expected peak QPS
- [ ] Confirm HPA is configured at 60% CPU (not 80%)
- [ ] DB connection pool formula validated: `pods × pool_size ≤ max_connections × 0.8`
- [ ] Disk runway > 6 months at current growth rate
- [ ] SLO burn rate alert fires before humans notice degradation
- [ ] Runbook for graceful degradation (circuit breaker thresholds, rate limits, shedding order)
- [ ] Quarterly review meeting scheduled with owner assigned

---

*Pairs with Chapter 109 (On-Call Engineering) for incident response when capacity fails, Chapter 120 (Cost Optimization) for the cost side of the capacity equation, and Chapter 56 (Metrics Collection System) for instrumenting the signals capacity planning depends on.*

`Chapter 117 | Section 7: Engineering Excellence | Capacity Planning` (On-Call Engineering) for incident response when capacity fails, Chapter 120 (Cost Optimization) for the cost side of the capacity equation, and Chapter 56 (Metrics Collection System) for instrumenting the signals capacity planning depends on.*

`Chapter 117 | Section 7: Engineering Excellence | Capacity Planning`
