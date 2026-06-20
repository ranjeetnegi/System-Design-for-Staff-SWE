# Chapter 88: Borg — Google's Cluster Manager

> "Borg manages the lifecycle of all of Google's production workloads. It is the
> system that decides which machine runs Gmail, which runs Search, and which runs
> your MapReduce job — simultaneously, across a fleet of hundreds of thousands of
> machines, without human intervention."
> — Verma et al., "Large-scale cluster management at Google with Borg" (EuroSys 2015)

---

## STATUS: STUB — Full chapter coming

This chapter covers Borg, Google's cluster manager and the direct precursor to
Kubernetes. Understanding Borg's design is essential because Kubernetes is
essentially open-source Borg — every concept maps directly, and interviewers
at Google frequently reference Borg when discussing container orchestration.

---

## Why This Chapter Matters

Every senior engineering interview that touches "how do you run 10,000 jobs
across 1,000 machines" is a Borg question. Kubernetes is the industry standard
and Borg is its blueprint. Knowing Borg — desired state, reconciliation loop,
resource packing, preemption — lets you speak fluently about Kubernetes design
decisions and explain WHY Kubernetes works the way it does, not just HOW.

---

## Planned Content

### Part 1: The Problem — Cluster Management at Google Scale
- Google runs hundreds of thousands of machines in datacenters
- Two kinds of workloads: long-running services (Gmail, Search, Ads) and
  batch jobs (MapReduce, data pipelines)
- Before Borg: teams manually specified machines, over-provisioned, wasted 30-40%
  of cluster capacity
- The core insight: treat the cluster as a single computer, not a collection of machines
- Real incident: 2005 Search frontend overload during Super Bowl — no automatic
  rescheduling, on-call engineers manually moved jobs for 2 hours

### Part 2: The Programming Model — Jobs, Tasks, and Allocs
- Job: a collection of identical tasks (e.g., 1000 tasks of "web server replica")
- Task: a single instance of a job, maps to a container on one machine
- Alloc: a reserved set of resources on one machine (shared by multiple tasks)
- Priority: production tasks preempt batch tasks; within production, strict ordering
- Quota: a machine-hours budget allocated to each team
- How teams specify jobs: a Borg config file (BCL — Borg Configuration Language)
  precursor to Kubernetes YAML

### Part 3: Architecture — BorgMaster, Borglets, and the Scheduler
- BorgMaster: 5-replica Paxos-elected leader; all API calls go here
- Borglet: agent running on every machine; reports state, executes tasks
- Scheduler: runs in BorgMaster; assigns tasks to machines
  - Two-phase scheduling: feasibility (which machines CAN run this task?) →
    scoring (which machine SHOULD run this task?)
  - Scoring criteria: bin-packing, data locality, reducing failure correlation
- ASCII diagram: BorgMaster + Borglets + Scheduler interaction

### Part 4: Desired State and the Reconciliation Loop
- The key abstraction: you declare WHAT you want, Borg figures out HOW
- Desired state: "I want 100 replicas of this web server, each with 2 CPUs and 4GB RAM"
- Actual state: what's currently running on the cluster
- Reconciliation loop: BorgMaster continuously diffs desired vs. actual state
  and takes actions to close the gap
- This is exactly the Kubernetes control loop — same concept, different names
- Why reconciliation beats imperative commands: idempotent, handles failures
  automatically, self-healing

### Part 5: Resource Management and Bin Packing
- Resources: CPU (millicores), RAM (MB), disk, network bandwidth
- The bin-packing problem: fit as many tasks as possible onto as few machines as possible
- Resource request vs. limit vs. actual usage
- Compressible resources (CPU — can be throttled) vs. non-compressible (RAM — OOM kill)
- The "borglet quota" idea: tasks request a guaranteed minimum + a burstable maximum
- How Borg achieves ~80% machine utilization (vs. 30-40% without it)
- ASCII diagram: bin-packing 5 tasks onto 3 machines

### Part 6: Fault Tolerance and Health Monitoring
- Task failure: Borglet reports failure → BorgMaster reschedules on a different machine
- Machine failure: all tasks on failed machine are rescheduled
- Network partition: BorgMaster uses Paxos; a minority of replicas going offline doesn't stop it
- Eviction: high-priority production tasks can preempt lower-priority batch tasks
- Health checks: each task exposes an HTTP health endpoint; BorgMaster polls it
- Rate limits on rescheduling: prevents cascade restarts from overwhelming the cluster
- Real incident: 2011 network partition in a Google datacenter — Borg rescheduled
  10,000 tasks in 4 minutes, Search availability unaffected

### Part 7: Borg vs. Kubernetes — The Direct Mapping
| Borg Concept | Kubernetes Equivalent |
|---|---|
| Job | Deployment / StatefulSet |
| Task | Pod |
| Alloc | ResourceQuota |
| BorgMaster | kube-apiserver + etcd + controllers |
| Borglet | kubelet |
| Scheduler | kube-scheduler |
| BCL config file | YAML manifest |
| Priority | PriorityClass |
| Desired state / reconciliation | Controller loop |

- What Kubernetes improved over Borg: open API, pluggable scheduler, namespaces,
  better multi-tenancy, pod abstraction (multiple containers per unit)
- What Borg did better: tighter resource accounting, more sophisticated bin-packing,
  decades of operational tuning

### Part 8: Limitations and Modern Alternatives
- Borg is internal to Google (not open-source)
- Kubernetes is the industry standard open-source Borg
- AWS ECS / Fargate: simpler but less powerful scheduling
- Nomad (HashiCorp): lighter-weight cluster manager
- Why Kubernetes won: ecosystem, open-source community, CNCF backing

### Part 9: Interview Application
- When to mention Borg/Kubernetes: any job scheduling, cluster management, or
  container orchestration question
- The desired-state / reconciliation-loop concept applies beyond cluster management:
  use it to describe any self-healing system
- L5 vs. L6 calibration: L5 says "use Kubernetes"; L6 explains the reconciliation loop,
  bin-packing algorithms, preemption policy, and resource compressibility distinction
- Common interview mistakes: thinking Kubernetes invented these ideas (it inherited
  them from Borg); not knowing the difference between CPU throttling and OOM kill

---

## Key Terms to Know

| Term | Meaning |
|------|---------|
| BorgMaster | Paxos-elected 5-replica control plane; the brain of the cluster |
| Borglet | Agent on every machine; executes tasks, reports state |
| Job | A collection of identical tasks (e.g., 100 replicas of a service) |
| Task | A single containerized workload on one machine (= Kubernetes Pod) |
| Alloc | Reserved resource pool on one machine, shared by co-located tasks |
| Reconciliation loop | Continuous diff of desired vs. actual state; takes actions to close the gap |
| Bin-packing | Fitting tasks onto machines to maximize utilization |
| Preemption | A high-priority task evicts a lower-priority task to get its resources |
| Compressible resource | CPU — can be throttled without killing the task |
| Non-compressible resource | RAM — task is killed (OOM) if it exceeds limit |
| BCL | Borg Configuration Language — the precursor to Kubernetes YAML |
| Priority | Determines which tasks can preempt which; production > monitoring > batch |

---

## The One-Sentence Summary

> "Borg is Google's cluster manager: you declare desired state (100 replicas, 2 CPUs each),
> and Borg's reconciliation loop continuously makes the cluster match it — handling
> machine failures, packing tasks efficiently, and preempting batch jobs for production
> traffic — Kubernetes is its open-source descendant."

---

*Full chapter: ~2,500 lines. Pairs with Ch86 (Chubby, used for BorgMaster election)
and Ch85 (MapReduce, the canonical Borg batch workload).*
