# Chapter 47: Kubernetes Internals — How K8s Actually Works

> Everyone uses Kubernetes. Very few understand what happens between
> `kubectl apply -f deployment.yaml` and the pod running on a node.
> That gap — the control plane, the scheduler, the kubelet, the watch loop —
> is exactly what L6 infrastructure interviews probe.

---

## Why This Chapter Matters

You have probably used `kubectl get pods` and `kubectl apply` many times. You know
what a Deployment is. You know what a Service does. But do you know why a pod stays
`Pending` for 45 seconds after you apply the YAML? Do you know what actually happens
inside the control plane when you scale a Deployment from 3 to 10 replicas? Do you
know why etcd disk latency at 10ms can cause your entire cluster to go haywire?

This chapter answers those questions. Kubernetes is not magic — it is a distributed
system built from well-understood primitives: a consensus store, a watch API, a
reconciliation loop, and a set of controllers. Once you understand those primitives,
the entire system clicks into place.

This matters at interviews for two reasons. First, platform and infra L6 roles
expect you to know K8s as a distributed system, not just as a tool. Second, K8s is
the open-source version of Borg (covered in Chapter 85), and the design decisions —
what K8s inherited, what it improved, what it still gets wrong — are rich interview
discussion territory.

Pairs with: Ch40 (Deployment Strategies), Ch85 (Borg), Ch48 (Consensus Deep Dive).

---

## Part 1: The Architecture — Five Control Plane Components

### 1.1 The Big Picture

Imagine Kubernetes as a company. The company has a headquarters (the control plane)
and a bunch of factory floors (the worker nodes). The headquarters does not actually
do any work — it does not run your containers. It only coordinates: it decides what
should happen, records decisions, and tells the factory floors what to do. The factory
floors actually execute — they pull images, start containers, and report back.

This separation is fundamental. The control plane can be on different machines from
the workers. The control plane can be replicated for high availability. Workers can
join or leave without the control plane caring, as long as they keep reporting in.

Here is the full architecture:

```
+------------------------------------------------------------------+
|                        CONTROL PLANE                             |
|                                                                  |
|  +------------------+     +------------------+                   |
|  |  kube-apiserver  |---->|      etcd        |                   |
|  |  (the front door)|<----|  (the database)  |                   |
|  +--------+---------+     +------------------+                   |
|           |                                                       |
|           |  watch                                                |
|           v                                                       |
|  +------------------+     +---------------------------+          |
|  | kube-scheduler   |     | kube-controller-manager   |          |
|  | (assigns pods    |     | (runs all controllers:    |          |
|  |  to nodes)       |     |  Deployment, Node,        |          |
|  +------------------+     |  ReplicaSet, etc.)        |          |
|                            +---------------------------+          |
|                                                                  |
|  +---------------------------+                                    |
|  | cloud-controller-manager  |                                    |
|  | (AWS/GCP/Azure specific:  |                                    |
|  |  LoadBalancers, PVs, etc) |                                    |
|  +---------------------------+                                    |
+------------------------------------------------------------------+
              |              |              |
              | HTTPS        | HTTPS        | HTTPS
              v              v              v
+-------------+  +----------+-+  +---------+--+
|  WORKER 1   |  |  WORKER 2  |  |  WORKER 3  |
|             |  |            |  |            |
| +--------+  |  | +--------+ |  | +--------+ |
| | kubelet|  |  | | kubelet| |  | | kubelet| |
| +--------+  |  | +--------+ |  | +--------+ |
| +--------+  |  | +--------+ |  | +--------+ |
| |kube-   |  |  | |kube-   | |  | |kube-   | |
| |proxy   |  |  | |proxy   | |  | |proxy   | |
| +--------+  |  | +--------+ |  | +--------+ |
| +--------+  |  | +--------+ |  | +--------+ |
| |contain-|  |  | |contain-| |  | |contain-| |
| |erd/CRI |  |  | |erd/CRI | |  | |erd/CRI | |
| +--------+  |  | +--------+ |  | +--------+ |
| [pod][pod]  |  | [pod][pod] |  | [pod][pod] |
+-------------+  +------------+  +------------+
```

### 1.2 kube-apiserver — The Only Door In

The API server is the single entry point for all cluster state changes. Everything
goes through the apiserver — kubectl, controllers, kubelets, the scheduler. Nothing
writes directly to etcd except the apiserver. This is not a performance decision; it
is a correctness decision. The apiserver is the chokepoint where authentication,
authorization, and admission control happen.

The apiserver is stateless. It does not cache. It does not hold state. It reads from
etcd, validates, writes to etcd, and returns. Because it is stateless, you can run
multiple apiservers behind a load balancer for high availability. In production, most
clusters run three apiservers. Each one is identical and interchangeable.

The apiserver exposes a REST API. Every Kubernetes object — Pod, Deployment, Service,
ConfigMap, Secret — is a REST resource. `kubectl get pods` is just an HTTP GET to
`/api/v1/namespaces/default/pods`. `kubectl apply -f deployment.yaml` is an HTTP
PATCH or PUT to `/apis/apps/v1/namespaces/default/deployments/my-deployment`.

The apiserver handles five steps on every write request:
1. **Authentication** — who is this? (certificates, tokens, OIDC)
2. **Authorization** — are they allowed? (RBAC rules)
3. **Admission control** — should we mutate or reject this? (admission webhooks)
4. **Validation** — is the object well-formed? (schema validation)
5. **Persistence** — write to etcd, return success.

### 1.3 etcd — The Database

etcd is a distributed key-value store. It is the only place in Kubernetes that
actually stores data. Everything else in the control plane is stateless and reads
from etcd. This means etcd is the most important component in the cluster. If etcd
is sick, the entire cluster is sick.

etcd uses the Raft consensus algorithm to stay consistent across multiple etcd nodes
(covered deeply in Part 2). The default production setup is three etcd nodes, which
can tolerate one node failure.

Every Kubernetes object lives in etcd as a key-value pair. The key looks like
`/registry/pods/default/my-pod` and the value is the protobuf-serialized Pod object.
The entire cluster state — every pod, every deployment, every secret, every node
status update — fits in etcd, which is typically sized at 2-8GB.

### 1.4 kube-scheduler — The Assignment Engine

The scheduler watches for pods that have been created but have no `nodeName` set
(meaning: no node has been assigned to run them yet). For each such pod, it runs a
two-phase algorithm: first filter candidate nodes, then score surviving candidates,
then write the assignment back to the apiserver.

The scheduler does not run pods. It does not talk to nodes directly. It just writes
a Binding object to the apiserver that says "put this pod on node-7." Then it moves
on to the next pod. The kubelet on node-7 picks up this information and does the
actual work.

The scheduler is pluggable. You can replace the default scheduler, run multiple
schedulers, or add extension points (scheduling webhooks) that let you inject custom
filtering or scoring logic.

### 1.5 kube-controller-manager — The Keeper of Desired State

The controller manager is a binary that runs dozens of controllers, each in its own
goroutine. A controller is just a loop: watch for a type of object, compare actual
state to desired state, take action to close the gap.

Key controllers running inside kube-controller-manager:
- **Deployment controller** — watches Deployments, creates/updates ReplicaSets
- **ReplicaSet controller** — watches ReplicaSets, creates/deletes Pods to hit replica count
- **Node controller** — watches Node heartbeats; marks nodes NotReady if heartbeats stop
- **Endpoints controller** — watches Pods + Services; maintains the EndpointSlice objects
- **Namespace controller** — handles namespace deletion (cascade-delete all objects)
- **Job controller** — watches Jobs; creates Pods; marks Job complete when done
- **CronJob controller** — watches CronJobs; creates Jobs on schedule

All of these controllers use the same pattern: the watch/informer pattern (Part 3).

### 1.6 cloud-controller-manager — Cloud Integration

The cloud-controller-manager runs cloud-provider-specific controllers that the
core K8s controllers should not know about. It handles things like:
- Provisioning a cloud load balancer when you create a Service of type LoadBalancer
- Attaching/detaching EBS volumes when pods are scheduled/unscheduled
- Updating node metadata from the cloud provider's instance metadata API

This component was split out from kube-controller-manager specifically so that the
core K8s code stays cloud-agnostic. AWS, GCP, and Azure each ship their own
cloud-controller-manager implementation.

### 1.7 Node Components — kubelet, kube-proxy, Container Runtime

On each worker node, three things run:

**kubelet** — the node agent. It watches the apiserver for pods assigned to this node
and makes those pods real: pulls images, creates containers via the container runtime,
runs health checks, and reports pod status back to the apiserver.

**kube-proxy** — the networking agent. It watches the apiserver for Service and
EndpointSlice objects and programs iptables (or IPVS) rules on the node to implement
Service load balancing. When traffic arrives destined for a ClusterIP, kube-proxy's
rules redirect it to one of the backend pod IPs.

**Container runtime** — the thing that actually starts containers. The most common
choices are containerd (default in modern K8s) and CRI-O. Docker used to be the
runtime but was deprecated in K8s 1.20 and removed in 1.24 (containerd was always
the underlying runtime even when Docker was used). The kubelet talks to the runtime
via the Container Runtime Interface (CRI), a gRPC API.

---

### Brainstorming: Part 1

**Q: Why is the apiserver the only component that talks to etcd? Couldn't controllers
read directly from etcd for efficiency?**

Having a single chokepoint — the apiserver — is the right design even though it looks
inefficient. The apiserver is where authentication, authorization, and admission control
happen. If controllers could bypass the apiserver and read etcd directly, you would
need to replicate those security checks in every controller. The design centralizes
policy enforcement: one place to add an audit log, one place to enforce RBAC, one place
to add admission webhooks. The "inefficiency" of having everything go through the
apiserver is more than offset by the simplicity of reasoning about who can access what.

In practice, controllers do not hammer etcd through the apiserver either. They use the
watch/informer pattern (Part 3), which keeps a local cache on the controller side. Once
a controller has done the initial list (which hits etcd), subsequent reads come from
the local cache, not etcd. The watch stream keeps the cache up to date. So controllers
get both correctness (going through apiserver for auth) and efficiency (reading from
local cache). This is one of the most elegant pieces of K8s architecture.

**Q: What happens if the control plane goes down? Do running pods die?**

Running pods keep running. This is a critical property. The control plane going down
does not kill your running workloads. The kubelet on each node runs its own local
reconciliation — it knows what pods were supposed to be running (it caches this
locally) and keeps them running even if it cannot reach the apiserver. New pods cannot
be scheduled, failed pods cannot be restarted (because the scheduler and controllers
are down), and no configuration changes can be applied, but everything that was already
running keeps running.

This is why control plane high availability matters for operations but not necessarily
for availability of running services. A cluster with a single-node control plane is
bad for reliability (one node failure = cannot schedule new work) but does not
immediately take down running pods. At L6, you should be able to explain this nuance:
the control plane manages desired state, but actual state lives on the nodes and persists
through control plane outages.

**Q: Why run all controllers in a single binary instead of separate binaries?**

Running all controllers in one binary (kube-controller-manager) is an operational
simplicity choice. There are dozens of controllers — packaging them separately would
mean dozens of binaries to deploy, monitor, version, and upgrade. The downside is that
a bug in one controller (say, the CronJob controller) can potentially crash the process
and take down all other controllers. In practice, the controllers are goroutines, and
Go panics in one goroutine can be recovered without killing the whole process. The
design also uses leader election: when you run multiple replicas of kube-controller-manager
for HA, only one is the leader at a time, preventing duplicate actions across replicas.

---

## Part 2: etcd Deep Dive — The Cluster's Brain

### 2.1 What Is etcd?

etcd is a strongly consistent, distributed key-value store. "Strongly consistent" means
every read sees the result of the most recent write — unlike eventual-consistent stores
where you might read stale data. In a system like Kubernetes where the controller
managing your deployment needs to see accurate replica counts, eventual consistency would
cause disasters. You need every controller to agree on what state the cluster is in.

etcd achieves strong consistency using the Raft consensus algorithm. Raft ensures that
all etcd nodes agree on every write before that write is considered committed. To commit
a write, a majority of etcd nodes (2 out of 3, or 3 out of 5) must acknowledge it. This
is why K8s recommends running 3 or 5 etcd nodes — so you can lose 1 or 2 nodes and
still make progress.

Think of etcd like a distributed notebook that a team shares. Every time someone writes
something in the notebook, the writing is only confirmed when the majority of team
members have seen and acknowledged it. If three people are keeping copies and two of
them acknowledge your write, the write is committed even if the third person's copy
isn't updated yet — they will catch up.

### 2.2 What Is Stored in etcd?

Everything in Kubernetes. Every object you create is stored as a key-value pair in
etcd. The key structure is:

```
/registry/{resource-type}/{namespace}/{name}

Examples:
/registry/pods/default/frontend-7d4f8b9d6-xkqp2
/registry/deployments/production/payment-service
/registry/services/kube-system/kubernetes
/registry/configmaps/default/app-config
/registry/secrets/default/db-credentials
/registry/nodes/worker-node-3
/registry/namespaces/staging
```

The value is the protobuf-serialized Kubernetes object. The apiserver serializes objects
to protobuf before writing (JSON is supported for the API but protobuf is used internally
for efficiency). This means you cannot read etcd with a regular text tool — you need to
decode the protobuf.

In a medium-sized cluster (100 nodes, 5000 pods), etcd stores on the order of:
- 5,000 Pod objects
- ~500 Deployment/StatefulSet objects
- ~500 Service objects
- Thousands of EndpointSlice objects
- Node status updates arriving every 10 seconds from each of 100 nodes

The total size is typically 2-4 GB. etcd has a default size limit of 2 GB (configurable
to 8 GB), and hitting that limit causes etcd to refuse writes — a cluster-killing event.
Production clusters monitor etcd size carefully.

### 2.3 Raft Consensus — How etcd Agrees on Writes

Raft is a consensus algorithm designed to be understandable (literally — the paper
is titled "In Search of an Understandable Consensus Algorithm"). Here is the core
mechanism at a level you need for interviews:

At any point, one etcd node is the **leader** and the others are **followers**. All
writes go to the leader. The leader appends the write to its log and sends it to all
followers. When a majority of nodes acknowledge the log entry, the leader commits it
and applies it to the state machine (the key-value store). The leader then responds
to the client.

```
CLIENT
  |
  | write: set /registry/pods/default/my-pod = {spec...}
  v
+----------+        AppendEntries RPC        +----------+
| LEADER   |------------------------------->| FOLLOWER1|
| (etcd-0) |<------ ACK (majority met!) ---- +----------+
|          |------------------------------->+----------+
|          |                                | FOLLOWER2|
|          |<----- ACK                      +----------+
|          |
| COMMIT! Write to state machine.
| Respond to client: OK.
```

If the leader dies, followers detect the timeout (no heartbeats received), start an
election, and elect a new leader — typically in 150-300ms. During this window, the
cluster cannot process writes. This is the "leader election latency" in etcd.

Raft uses **log replication**, not just state replication. Every etcd node keeps a
log of all operations. If a follower falls behind, it replays the log to catch up.
This means etcd can handle a follower going down and coming back: it just replays
whatever it missed. What it cannot handle is a majority going down — without majority,
no writes can commit, and the cluster is stuck.

### 2.4 Why etcd Disk Latency Kills the Control Plane

This is one of the most important operational facts about Kubernetes. etcd uses disk
(WAL — write-ahead log) to persist every committed log entry before acknowledging the
commit. If the disk is slow, the leader cannot commit writes fast enough, and the
entire control plane slows to a crawl.

The Raft heartbeat timeout in etcd is typically 100ms. If the leader is too slow
responding to followers (because it is waiting on slow disk I/O), followers think the
leader is dead and start an election. But the "dead" leader is just slow. You get
spurious leader elections, degraded throughput, and often cascading failures.

**Real Incident: etcd on Shared Disk at a Large E-Commerce Company**

A company ran their etcd cluster on VMs that shared local SSDs with other workloads.
During a batch processing job that ran nightly, the shared SSD became I/O saturated.
etcd write latency spiked from 2ms to 80ms. Raft leader elections began happening every
30 seconds. During each election, no writes could be committed for 200-300ms. The
apiserver, unable to write to etcd, started returning 503 errors. Controllers could not
update pod status. The scheduler could not write bindings. Within 5 minutes, the cluster
appeared completely broken — kubectl commands timed out, new deployments stalled, and
node status stopped updating.

The root cause: a noisy neighbor on the SSD. The fix: move etcd to dedicated NVMe SSDs
(never share etcd disks), set etcd's `--quota-backend-bytes` to monitor size, and add
alerts on etcd's `wal_fsync_duration_seconds` Prometheus metric. Production etcd should
have p99 fsync latency under 10ms. If you see it above 25ms, you are heading for trouble.

### 2.5 The etcd Watch API

etcd supports a watch API: clients can subscribe to changes on a key or key prefix
and receive a stream of events (PUT, DELETE) as they happen. This is the foundation
of all Kubernetes reactivity.

When you do `kubectl get pods --watch`, the apiserver opens a watch on etcd for all
pods in the requested namespace. When a pod changes, etcd streams the event to the
apiserver, which formats it as a Kubernetes watch event and streams it to your kubectl.

More importantly, every controller in kube-controller-manager uses this watch API
(through the informer abstraction, covered in Part 3). The Deployment controller is
not polling — it is watching. When a Deployment changes, the controller is notified
within milliseconds.

The watch API has a concept of **resource version**. Every etcd write increments a
global resource version. Watches can start from a specific resource version, meaning
"send me everything that happened after version X." This is how controllers reconnect
after a network blip: they reconnect and resume from where they left off.

---

### Brainstorming: Part 2

**Q: Why does K8s use etcd and not a regular database like Postgres?**

etcd was chosen because it provides strong consistency via Raft with a watch API
built in, and it is designed specifically for distributed coordination — not for
high-throughput OLTP workloads. Postgres is an excellent database for transactional
workloads with complex queries, but it does not have Raft built in (Postgres uses
streaming replication which is eventually consistent), and its change notification
system (LISTEN/NOTIFY) is not well-suited for the event-driven watch patterns Kubernetes
requires at scale. etcd's API is also much simpler (key-value with watch), which makes
it easier to reason about consistency.

That said, the community has discussed replacing etcd. The main complaints are etcd's
relatively low throughput ceiling (around 10,000 write operations per second) and its
size limit. Some large clusters with hundreds of thousands of objects hit these limits.
Projects like kine (which presents a Postgres or SQLite database as an etcd-compatible
API) exist for edge/small-cluster use cases. For standard production clusters, etcd
remains the right choice because its consistency model is exactly what K8s needs.

**Q: What happens when an etcd node loses its data (disk failure)? Can you recover?**

If an etcd node loses its data, you can recover as long as the majority (quorum) of
the other etcd nodes are still healthy. The failed node can be re-added to the cluster,
and it will replay the Raft log from the other nodes to rebuild its state. This typically
takes minutes to hours depending on how much data there is, because etcd does not keep
the full Raft log forever (it takes periodic snapshots), so the new node starts from the
latest snapshot and replays only the delta.

The scary scenario is losing the majority — for example, losing 2 out of 3 etcd nodes
simultaneously. In that case, the cluster cannot make progress (no writes can commit),
and you must restore from a snapshot backup. This is why regular etcd backups are
mandatory in production, and why most teams back up etcd every 30 minutes. The backup
is a etcd snapshot that captures the full cluster state at a point in time. Restoring
involves stopping etcd, restoring the snapshot, and restarting. Any writes between the
snapshot and the failure are lost. For a system managing compute scheduling (not financial
transactions), losing 30 minutes of configuration changes is acceptable if the pods are
still running.

**Q: How many etcd nodes should you run, and why not run more?**

Three etcd nodes is the standard for production. Five is used when you need higher
fault tolerance (can lose 2 nodes instead of 1). More than five is almost never warranted
because every additional etcd node increases write latency — the leader must wait for
majority acknowledgment before committing, and more nodes means more round trips to
collect acknowledgments. With 7 etcd nodes, every write is slower than with 3, and you
are only gaining the ability to lose 3 nodes simultaneously — a scenario that is
extremely unlikely and would indicate a catastrophic infrastructure failure where the
cluster being operational is not your biggest problem. The latency cost of extra etcd
nodes is real: adding nodes goes from N/2+1 nodes needing to ACK a write, which at
network latency of even 1ms per hop, adds up quickly at high write rates.

---

## Part 3: The Watch/Informer Pattern — How Everything Works

### 3.1 The Core Problem

Imagine you have 50 controllers all trying to watch etcd for changes. If each one
opened its own direct connection to etcd and streamed all events, you would have 50
watch connections to etcd, 50 streams of events, and etcd would need to send every
event 50 times. At scale with millions of events per day, this is unsustainable.

Also: what if the apiserver is briefly unavailable? Each controller would need to
handle reconnection, bookmarking where it left off, and replaying missed events.
Building that into every controller is error-prone.

The solution is the **Informer** — a shared cache that any number of controllers
can use. The informer does one List+Watch on the apiserver, maintains a local cache,
and calls registered event handlers when objects change. Controllers register handlers
with the informer rather than watching etcd directly.

### 3.2 How the Informer Works

```
+----------------------------------+
|         kube-controller-manager  |
|                                  |
|  +-----------------------------+ |
|  |        INFORMER             | |
|  |                             | |
|  | 1. LIST all Pods via API    | |
|  |    server (one-time at      | |
|  |    startup)                 | |
|  |         |                   | |
|  |         v                   | |
|  | 2. Populate LOCAL CACHE     | |
|  |    (thread-safe store)      | |
|  |         |                   | |
|  |         v                   | |
|  | 3. WATCH apiserver for new  | |
|  |    events (long-lived HTTP) | |
|  |         |                   | |
|  |         v                   | |
|  | 4. On event → update cache  | |
|  |    + call event handlers    | |
|  +-------|---------------------+ |
|          |                       |
|     ADDED/MODIFIED/DELETED       |
|          |                       |
|     +----v----+  +----------+    |
|     |  Replica|  |Deployment|    |
|     |  Set    |  |Controller|    |
|     |  Ctrl   |  |          |    |
|     +---------+  +----------+    |
+----------------------------------+
              |
              | (reads from local cache, not apiserver)
              v
        reconcile()
```

The List phase gives the controller the initial state of the world. The Watch phase
keeps the local cache up to date. Controllers read from the local cache, not from the
apiserver, for almost all operations — the apiserver is only hit to write changes.
This dramatically reduces apiserver load.

### 3.3 Event Types: ADDED, MODIFIED, DELETED

The watch stream carries three event types:

**ADDED** — a new object appeared. Example: a new Pod was created. The ReplicaSet
controller sees ADDED for each new Pod it created, and uses this to track how many
pods are currently running.

**MODIFIED** — an existing object changed. Example: a pod's status changed from
Pending to Running. The kubelet updates pod status, the apiserver writes to etcd,
etcd notifies watchers, and the watch stream delivers a MODIFIED event to all
interested controllers.

**DELETED** — an object was deleted. Example: a pod was deleted (by kubectl delete
or because the node died). The ReplicaSet controller sees DELETED, counts current
replicas, sees it is below desired, and creates a new pod.

There is also a fourth synthetic event type: **SYNC** (sometimes called a re-sync).
Informers periodically re-list all objects and emit synthetic MODIFIED events for all
of them, even if nothing changed. This is a safety net: if an event was dropped due to
a network blip, the re-sync ensures the controller eventually processes the correct
state.

### 3.4 The Reconciliation Loop

Every controller has a `reconcile(key)` function. The key is typically
`{namespace}/{name}` — identifying which specific object to reconcile. The function:

1. Reads the current desired state from the local cache (what the user specified)
2. Reads the current actual state (what actually exists, from the cache + live queries)
3. Computes the diff
4. Takes action to close the gap (create/update/delete child objects)
5. Updates the object's status in the apiserver

Example — ReplicaSet controller reconciling a ReplicaSet with `replicas: 3`:

```python
def reconcile(replicaset_key):
    rs = cache.get(replicaset_key)      # desired: 3 replicas
    pods = cache.list_pods_for(rs)      # actual: currently 1 pod
    
    needed = rs.spec.replicas - len(pods)  # gap: need 2 more
    
    for _ in range(needed):
        create_pod(rs.spec.template)    # action: create pods
    
    # Update status
    rs.status.readyReplicas = count_ready(pods)
    apiserver.update_status(rs)
```

The key insight: controllers are **edge-triggered** (react to events) but also
**level-based** (they look at current state, not just what changed). This means a
controller does not need to track "I got an event saying +1 pod was deleted, so I
should create 1 pod." It just looks at the current state and closes the gap. This
makes controllers idempotent — running reconcile twice when only one run is needed
is safe, because the second run sees the gap is already closed and does nothing.

### 3.5 Why This Pattern Is Brilliant

The watch/informer/reconciliation pattern has several properties that make it
exactly right for a distributed system:

**Loose coupling**: The scheduler does not call the kubelet. The kubelet does not
call the scheduler. They communicate via objects in etcd (through the apiserver).
This means components can be independently restarted, upgraded, or replaced.

**Self-healing**: If the controller crashes and restarts, it re-lists, rebuilds its
cache, and re-reconciles everything. Any gaps caused during the crash are automatically
fixed. You do not need a recovery path — the normal path is the recovery path.

**Idempotency**: Because reconciliation looks at desired vs. actual state (not at
deltas), running it multiple times is safe. This is essential in a distributed system
where at-most-once delivery is impossible to guarantee.

**Scalability**: Controllers share informers for the same resource type. Even with
dozens of controllers all watching pods, there is only one List+Watch connection to
the apiserver per resource type per process.

---

### Brainstorming: Part 3

**Q: What happens if a controller processes an event but crashes before writing the
result back? Is the change lost?**

No, and this is the key point about level-based reconciliation. Because controllers
look at current desired state (not just the event), a crash-and-restart is safe. When
the controller restarts and re-lists, it will see that the desired state is still not
met (the pods it was supposed to create were not created), and it will create them
during the next reconciliation pass. This is why the watch/informer pattern is sometimes
described as "crash-safe by construction." The controller does not need to implement
a recovery path — the normal reconciliation path handles everything.

This is in contrast to event-sourcing or delta-based approaches where you would need
to implement exactly-once semantics or replay logic. In K8s, you get recovery for free
because reconciliation is fundamentally a function of current state, not of event history.

**Q: How does K8s prevent two controllers from stepping on each other's work?**

The apiserver uses optimistic concurrency via the `resourceVersion` field. Every
object in etcd has a `resourceVersion` (a monotonically increasing integer). When a
controller reads an object and then tries to update it, it includes the `resourceVersion`
it read. The apiserver rejects the update with a 409 Conflict if the `resourceVersion`
no longer matches (meaning someone else updated the object in between). The controller
then re-reads the object (gets the latest version) and tries again.

This is a form of optimistic locking. It works well because conflicts are rare — most
controllers own specific objects and do not compete with other controllers for the same
objects. For example, the ReplicaSet controller owns pods with a specific
`ownerReference`, and no other controller will try to delete those pods. The Deployment
controller owns ReplicaSets with specific labels, and no other controller competes.
The ownership model (via `ownerReferences`) is what gives each controller a clear
domain without needing pessimistic locking.

**Q: The informer keeps a local cache. Could the cache be stale when a controller reads it?**

Yes, and K8s controllers must handle this. The local informer cache can be slightly
behind etcd (by however long it takes for a watch event to travel from etcd → apiserver
→ controller process). This means if you write a pod and immediately read back "how many
pods do I have," you might get the count before your write was reflected in the cache.

Controllers handle this in two ways. First, after writing a change (creating a pod),
they do not immediately try to read that change back — they let the watch event come in
and update the cache. The next reconciliation cycle will see the correct state. Second,
for critical reads where staleness is not acceptable (like checking if a secret exists
before mounting it in a pod), controllers use live reads (hitting the apiserver directly)
rather than the cache. The informer cache is excellent for high-frequency reads where
slight staleness is acceptable; live reads are used when consistency is critical.

---

## Part 4: The Scheduler Deep Dive — Placing Pods on Nodes

### 4.1 The Scheduler's Job

The scheduler has a simple job description: watch for pods with no `nodeName` set,
pick the best node, write the binding. But "pick the best node" hides enormous
complexity. You have to respect resource requests, affinities, anti-affinities, taints,
topology constraints, and custom priorities. You also have to do this fast — in a large
cluster, hundreds of pods might need scheduling simultaneously.

The scheduler is deterministic by design: given the same cluster state and the same
pod, it should always pick the same node. But it also needs randomness in tie-breaking
to achieve even distribution.

### 4.2 Phase 1: Filtering — Which Nodes CAN Run This Pod?

Filtering eliminates nodes that cannot run the pod. It runs a set of **predicates**
(also called filter plugins) against each node. Any node that fails any predicate is
eliminated. The remaining nodes are "feasible" candidates.

```
ALL NODES (100)
      |
      | NodeResourcesFit: eliminate nodes without enough CPU/RAM
      v
  FEASIBLE (60 nodes have enough resources)
      |
      | NodeAffinity: eliminate nodes not matching required labels
      v
  FEASIBLE (40 nodes match zone=us-east-1a label)
      |
      | TaintToleration: eliminate nodes with taints pod doesn't tolerate
      v
  FEASIBLE (35 nodes - 5 tainted "gpu-only" nodes removed)
      |
      | PodAntiAffinity: eliminate nodes already running same pod
      v
  FEASIBLE (30 nodes - 5 already have this pod's anti-affinity match)
      |
      v
  CANDIDATE SET: 30 nodes
```

Key filter plugins:

**NodeResourcesFit**: The pod specifies `resources.requests.cpu` and
`resources.requests.memory`. The node's allocatable capacity minus the sum of all
running pods' requests must be enough to fit this pod's requests. If a node has 8
vCPU available and you request 4 vCPU, it passes. If you request 10 vCPU, it fails.
Note: this is based on requests, not limits — a pod can use more than its request
(up to its limit), but scheduling only considers requests.

**NodeAffinity**: Pods can specify `nodeSelector` (simple key=value match) or
`nodeAffinity` (more expressive: required vs. preferred, In/NotIn/Exists operators).
Required rules are enforced in the filter phase — nodes that don't match are eliminated.

**TaintToleration**: Nodes can have taints — marks that repel pods. A taint looks
like `key=value:NoSchedule` (do not schedule anything here) or `key=value:NoExecute`
(evict running pods too). Pods must have a matching `toleration` to be scheduled on a
tainted node. Example: marking GPU nodes with `gpu=true:NoSchedule` ensures only
GPU-requesting pods land there.

**PodAntiAffinity**: Pods can specify anti-affinity rules: "do not place me on a node
that already has a pod with label `app=frontend`." This is used to spread replicas
across nodes for fault tolerance. Anti-affinity is expensive to compute because it
requires checking every other pod on every node.

**VolumeZoneConstraint**: If the pod needs a PersistentVolume that is bound to a
specific availability zone (AWS EBS is zone-specific), nodes in other zones are
eliminated.

**TopologySpreadConstraint**: A newer mechanism for spreading pods across zones or
regions evenly. More flexible than anti-affinity.

### 4.3 Phase 2: Scoring — Which Node SHOULD Run This Pod?

After filtering, you have a set of feasible nodes. Scoring assigns each node a score
from 0 to 100. The node with the highest total score wins. If there is a tie, the
scheduler breaks it randomly.

Key scoring plugins:

**LeastAllocated (default for most workloads)**: Prefer nodes with the most free
resources. Scores nodes higher the more headroom they have. This spreads pods across
the cluster, which is good for availability: if a node fails, fewer pods are lost.

**MostAllocated (bin-packing mode)**: Prefer nodes that are fuller. Scores nodes
higher the less free space they have. This packs pods tightly, leaving some nodes
empty so they can be scaled down (useful for cost optimization with cloud autoscaling).

**ImageLocality**: Prefer nodes that already have the container image pulled. Pulling
a 500MB image adds 30-60 seconds of startup time. If a node already has the image
cached, starting there is faster. Scores nodes higher if they have the image already.

**NodeAffinityPriority**: If the pod has preferred (not required) node affinity rules,
nodes that match get a score boost.

**InterPodAffinityPriority**: If the pod prefers to be near other pods (soft affinity),
nodes running those other pods get a score boost.

```
CANDIDATE SET (30 nodes)
      |
      | LeastAllocated scoring: nodes with more free resources score higher
      | ImageLocality scoring: nodes with image cached score higher
      | NodeAffinityPriority: preferred zone gets score boost
      v
  SCORED:
    node-12: 85 points  ← has image cached + 40% free resources
    node-07: 72 points  ← 50% free but no image cached
    node-23: 71 points  ← 45% free, no image
    ...
      |
      | Select highest score
      v
  WINNER: node-12
```

### 4.4 Binding — Writing the Decision

After selecting a node, the scheduler writes a **Binding** object to the apiserver:

```json
{
  "apiVersion": "v1",
  "kind": "Binding",
  "metadata": {"name": "my-pod", "namespace": "default"},
  "target": {"apiVersion": "v1", "kind": "Node", "name": "node-12"}
}
```

The apiserver receives this and sets `spec.nodeName = "node-12"` on the Pod object
in etcd. The pod is now "Scheduled" — it has a node assigned. The scheduler moves on.
The kubelet on node-12 will see this change via its watch and begin pulling the image
and creating the container.

### 4.5 Scheduler Extensibility

The default scheduler is designed to be extended without forking. Two extension points:

**Scheduling Profile Plugins**: The scheduler framework has a plugin system with
hooks at each phase (PreFilter, Filter, PostFilter, PreScore, Score, Reserve, Bind).
You can add custom plugins compiled into the scheduler binary to add new filtering
or scoring logic.

**Scheduler Webhook (Extender)**: You can register an HTTP endpoint that the scheduler
calls during filter or score phases. The scheduler sends candidate nodes to your webhook,
and your webhook responds with which nodes to keep or what scores to assign. This
is slower (HTTP round trip per scheduling decision) but works without recompiling.

**Real Incident: Scheduler Bug Causing Pod Starvation at a Gaming Company**

A gaming company deployed a custom scheduling extender that scored nodes based on
real-time game session counts (prefer nodes with fewer sessions for new game server
pods). The extender was fast under normal load but had a bug: when the backend
database it queried was slow, it held the HTTP connection open for up to 30 seconds.

The scheduler processes pods serially through the extension pipeline. With the extender
blocked for 30 seconds per pod, and a sudden burst of 200 pods needing scheduling during
a game launch event, pods were sitting in Pending state for 100+ minutes. Players
couldn't connect to game servers. The fix was to add a 500ms timeout to the extender
call and fall back to default scoring on timeout. The lesson: scheduling extenders are
in the critical path for pod startup — they must be fast or have a fallback.

---

### Brainstorming: Part 4

**Q: What happens when no node passes the filtering phase? The pod stays Pending forever?**

Yes, a pod stays Pending until a node becomes eligible. The scheduler retries
periodically. This is actually intentional — Kubernetes will not force a pod onto an
ineligible node just to get it running. If you asked for 16 vCPU and no node has 16
vCPU free, the pod waits until a node does. This is where the Cluster Autoscaler comes
in: it watches for pods that have been Pending for too long due to insufficient resources
and provisions new nodes to accommodate them.

To debug a Pending pod, `kubectl describe pod {name}` shows the scheduler's events —
specifically why nodes were filtered out. Common messages: "0/10 nodes are available:
10 Insufficient cpu" (every node fails NodeResourcesFit), "0/10 nodes are available:
5 node(s) had taint that the pod didn't tolerate, 5 Insufficient memory" (mixture of
taint and resource failures). These messages are the fastest path to understanding why
a pod is stuck.

**Q: How does the scheduler handle hundreds of pods being created simultaneously (e.g., a deployment scale-up)?**

The scheduler processes pods one at a time through its pipeline, but it uses a priority
queue internally (pods with higher PriorityClass get scheduled first) and runs the
filter/score phases in parallel across nodes using multiple goroutines. For 100 nodes
and 100 pods, the scheduler can typically handle about 100 scheduling decisions per
second, meaning a burst of 100 pods is scheduled in about 1 second in a healthy cluster.

The scheduler also has an optimization called "equivalence caching" — if two pods have
identical specs, the filter results for a given node can be reused rather than
recomputed. For a deployment scale-up where all 10 new replicas have the same spec,
the filter run for the first pod can inform the scheduling of subsequent pods. This
dramatically speeds up bursts of homogeneous pods. At very large scale (1000+ pods in
the pending queue), the scheduler can become a bottleneck, which is why some teams run
multiple schedulers with pod assignment by namespace or label.

**Q: How does descheduling work? Can K8s move running pods to better nodes?**

The default scheduler does not move running pods — once a pod is scheduled, it stays
on that node until it is deleted or evicted. But the cluster can become unbalanced over
time as nodes are added or removed. A separate component, the **Descheduler** (not part
of core K8s, it's a separately deployed tool), periodically identifies pods that violate
scheduling policies on their current node (e.g., too many pods from the same Deployment
on one node after another node was added) and evicts them, letting the scheduler
re-place them on better nodes.

This evict-and-reschedule approach is how K8s achieves eventual balance without complex
pod migration. The tradeoff is that eviction causes a brief disruption (the pod
restarts on the new node). For stateless services, this is acceptable. For stateful
workloads, you would configure PodDisruptionBudgets to limit how many pods can be
evicted simultaneously, ensuring availability during rebalancing.

---

## Part 5: The Kubelet Deep Dive — The Node Agent

### 5.1 What the Kubelet Does

The kubelet is the agent that runs on every worker node. Its job is to take the
"list of pods that should run on this node" and make it real. It watches the apiserver
for PodSpecs assigned to its node and ensures the containers defined in those specs
are running and healthy.

The kubelet is the bridge between the Kubernetes control plane (which works in terms
of abstract objects) and the Linux system (which works in terms of processes, cgroups,
network namespaces). It translates PodSpec → Linux system calls.

### 5.2 Pod Lifecycle on the Kubelet

When the scheduler assigns a pod to a node (sets `spec.nodeName`), the kubelet on
that node sees the change via its watch. It then drives the pod through these phases:

```
ASSIGNED (scheduler set nodeName)
      |
      | Pull image (if not cached)
      | - Pull from registry using imagePullSecrets
      | - Verify image checksum
      v
IMAGE READY
      |
      | Create pod sandbox (pause container)
      | - Set up network namespace via CNI plugin
      | - Assign pod IP
      v
NETWORK READY
      |
      | Init containers run (sequentially, must succeed)
      v
INIT COMPLETE
      |
      | Start app containers (via CRI: gRPC to containerd/CRI-O)
      | - Mount volumes
      | - Set environment variables
      | - Set resource limits via cgroups
      v
RUNNING
      |
      | Run probes:
      |   startupProbe (if defined): wait for app to start
      |   livenessProbe: restart container if unhealthy
      |   readinessProbe: add/remove from Service endpoints
      v
READY (readinessProbe passing)
      |
      | Kubelet reports status to apiserver every 10s
      | (containerStatuses, podPhase, conditions)
```

### 5.3 The Container Runtime Interface (CRI)

The kubelet does not directly call Docker or containerd. It uses the Container Runtime
Interface (CRI), a gRPC API that abstracts the runtime. The kubelet calls
`RunPodSandbox`, `CreateContainer`, `StartContainer`, `StopContainer`, etc. Any
container runtime that implements this gRPC interface can be used.

The major CRI implementations:
- **containerd** (default in most managed K8s clusters) — the CNCF-graduated container
  runtime. Used by Docker under the hood. Most mature and widely deployed.
- **CRI-O** — Red Hat's lightweight CRI implementation, designed specifically for K8s.
  Used in OpenShift. No Docker dependency.
- **cri-dockerd** — an adapter that lets Docker Engine work as a CRI runtime. Needed
  after K8s removed the built-in Docker shim in 1.24.

Why does this matter? Because the kubelet is decoupled from the runtime. You can swap
runtimes without changing kubelet. This also allowed K8s to remove the Docker dependency
without breaking the container ecosystem.

### 5.4 The Three Types of Probes

Probes are one of the most commonly misunderstood parts of K8s. There are three, and
they have different behaviors on failure:

**Liveness Probe**: "Is this container alive?" If the liveness probe fails repeatedly
(exceeds `failureThreshold`, default 3), the kubelet kills the container and restarts
it. The container restart count increments. If the container keeps failing its liveness
probe, it enters **CrashLoopBackOff** — K8s keeps restarting it with exponential
backoff (10s, 20s, 40s, 80s, 160s, 300s max).

```
Liveness probe fails 3 times
    → kubelet kills container
    → kubelet restarts container (restartPolicy applies)
    → if keeps failing: CrashLoopBackOff
    → container NOT removed from Service endpoints while restarting
```

**Readiness Probe**: "Is this container ready to serve traffic?" If the readiness probe
fails, the pod is removed from the Service's EndpointSlice — no more traffic is routed
to it. But the container is NOT killed. The probe keeps running. If it passes again,
the pod is added back to the endpoints. This is used during startup (before the app
is ready) and during graceful degradation (the app says "I'm overloaded, stop sending
me traffic").

```
Readiness probe fails
    → kubelet updates pod condition: Ready=False
    → Endpoints controller removes pod from Service endpoints
    → No traffic routed to this pod
    → Container NOT killed, keeps running
    → When readiness probe passes again → pod added back to endpoints
```

**Startup Probe**: "Has this container finished starting up?" Intended for slow-starting
apps that would fail a liveness probe during startup. The startup probe runs first. If
it succeeds, liveness and readiness probes begin. If it fails for longer than
`failureThreshold × periodSeconds`, the container is killed (same as liveness failure).

```
startupProbe defined:
    → liveness + readiness probes DISABLED until startup probe succeeds
    → startup probe runs (e.g., every 10s, up to 30 failures = 300s max)
    → if startup probe succeeds: enable liveness + readiness
    → if startup probe never succeeds: kill container
```

**Why does this matter?** Mismatching probe types is a common bug. Setting a liveness
probe with too low a timeout on a Java app with long GC pauses causes the pod to
be killed during GC and enter CrashLoopBackOff — even though the app is healthy, just
paused. The right fix: use a startup probe with a long timeout for startup, and use a
liveness probe that is generous about GC pauses.

### 5.5 Resource Enforcement via cgroups

The kubelet uses Linux control groups (cgroups) to enforce the CPU and memory limits
specified in the pod spec. This is how "your container cannot use more than 500m CPU
and 512Mi memory" is actually enforced at the OS level.

**CPU**: cgroups enforce CPU using CFS (Completely Fair Scheduler) bandwidth throttling.
A pod with `limits.cpu: 500m` (500 millicores = 0.5 CPU) gets a CFS quota that allows
it to use at most 50% of one CPU core per scheduling period (typically 100ms). If the
pod tries to use more, it is throttled (CPU is simply not allocated to it for the
remainder of the period). CPU throttling does not kill the process — it just slows it.

**Memory**: Memory limits are enforced via the cgroup memory limit. If a container
tries to allocate more memory than its `limits.memory`, the Linux OOM (Out Of Memory)
killer activates and kills the process. This is reported as **OOMKilled** in `kubectl
describe pod`. The container is restarted (if restartPolicy allows). Memory limits are
hard limits — there is no "slow down" like with CPU; you either have the memory or you die.

### 5.6 Node Status Reporting

Every 10 seconds (configurable via `--node-status-update-frequency`), the kubelet
sends a heartbeat to the apiserver. The heartbeat updates:
- Node conditions: `Ready`, `MemoryPressure`, `DiskPressure`, `PIDPressure`, `NetworkUnavailable`
- Node capacity and allocatable resources
- Pod status for all pods on the node

The Node controller in kube-controller-manager watches these heartbeats. If a node
stops sending heartbeats for `node-monitor-grace-period` (default 40s), the Node
controller marks it `NotReady`. After `pod-eviction-timeout` (default 5 minutes), it
starts evicting pods from the node (by deleting the Pod objects from etcd, which
causes the pod to be rescheduled on another node — assuming the pod is owned by a
Deployment or ReplicaSet).

---

### Brainstorming: Part 5

**Q: What is a pause container (pod sandbox), and why does every pod have one?**

Every pod starts with a special container called the pause container (or infra container)
before any application containers start. The pause container's job is to hold the
network namespace for the pod. All other containers in the pod share this network
namespace — they all see the same network interfaces, the same IP address, and can
communicate with each other via localhost. The pause container essentially "owns" the
network namespace for the lifetime of the pod.

Why a separate container for this? Because if the application container crashes and
restarts, the network namespace (and therefore the pod IP) would normally be destroyed
and recreated — causing the pod to get a new IP address and disrupting any connections.
By keeping the pause container running continuously (it just runs an infinite sleep),
the network namespace persists across application container restarts. The pod IP stays
stable even as app containers crash and restart. This is what makes liveness probe
restarts work correctly — the restarted container gets the same IP and the same
localhost connections as before.

**Q: How does the kubelet handle a node running out of disk space?**

When disk pressure builds up (typically monitored by the kubelet through eviction
thresholds), the kubelet takes proactive action before the OS OOM killer triggers
a chaotic death spiral. The kubelet has two types of eviction thresholds: soft
(exceeded for a grace period before action) and hard (immediate action).

When soft thresholds are crossed (e.g., available disk < 10%), the kubelet sets
the `DiskPressure` node condition to True and stops scheduling new pods on the node
(the scheduler filters out nodes with DiskPressure). If hard thresholds are crossed
(e.g., available disk < 5%), the kubelet begins pod eviction — it kills pods starting
with the ones that are most over their resource requests, using a priority order:
Best Effort pods first (no requests/limits), then Burstable (requests < limits), then
Guaranteed (requests == limits). This ordered eviction protects the most important
workloads longest. Evicted pods get an "evicted" status and their owning Deployment/
ReplicaSet recreates them elsewhere.

**Q: Can two pods on the same node communicate faster than two pods on different nodes?**

Yes, pods on the same node communicate via the virtual ethernet bridge (the veth pair
and the Linux bridge or similar) — no packets leave the physical NIC. Throughput is
effectively memory bandwidth (tens of Gbps), and latency is microseconds. Pods on
different nodes must traverse the physical network: typical latency is 0.1-1ms for
intra-datacenter hops, and throughput is bounded by the NIC speed (10-100 Gbps).

This is why some latency-sensitive systems care about pod co-location, using pod
affinity rules to keep high-traffic pairs of services on the same node. However, K8s
does not expose "pod on same node" as a first-class concept in its traffic routing —
kube-proxy's iptables rules round-robin across all pod IPs regardless of node. If you
want node-local traffic, you need topology-aware routing (a relatively recent K8s
feature) or a service mesh that is aware of pod locality.

---

## Part 6: Networking — The Flat Pod Network

### 6.1 The Fundamental Model: Every Pod Gets an IP

Kubernetes has a simple, elegant networking model: every pod gets its own unique IP
address, and any pod can reach any other pod's IP directly, without NAT. No port
mapping. No "which host is this container on?" You just use the pod IP.

This is called the "flat pod network" or the Kubernetes networking model. It
dramatically simplifies service discovery and communication because pods can just talk
to each other's IPs as if they were on the same LAN — even if they are on different
nodes in different racks.

The implementation of this model is delegated to CNI (Container Network Interface)
plugins. Kubernetes does not include networking code — it specifies the model and lets
plugins implement it.

### 6.2 CNI — Container Network Interface

CNI is a specification for how container runtimes call network plugins. When the kubelet
creates a pod sandbox (the pause container), it calls the configured CNI plugin with
"allocate a network namespace for this pod." The CNI plugin assigns a pod IP, sets up
the veth pair, and programs the routing so that traffic to this pod IP reaches the
correct network namespace on the correct node.

```
NODE A (10.0.1.0/24 pod subnet)          NODE B (10.0.2.0/24 pod subnet)
+----------------------------------+     +----------------------------------+
|                                  |     |                                  |
| pod-A (10.0.1.5)                 |     | pod-B (10.0.2.7)                 |
|    |                             |     |    |                             |
|   veth0   <---> cbr0 (bridge)   |     |   veth0   <---> cbr0 (bridge)   |
|    (pod side)   (node side)      |     |    (pod side)   (node side)      |
|                    |             |     |                    |             |
|                  eth0            |     |                  eth0            |
|              (10.0.0.1)          |     |              (10.0.0.2)          |
+----------------------------------+     +----------------------------------+
                    |                                        |
                    +-------- physical network ---------------+
                    
                    (CNI plugin programs route:
                     "to reach 10.0.2.0/24, send to 10.0.0.2")
```

Major CNI plugins:

**Calico**: Uses BGP (Border Gateway Protocol) to distribute pod routes between nodes.
Each node announces its pod subnet to the BGP mesh, and all other nodes learn the
routes. No overlay network needed — packets travel at native speed using L3 routing.
Calico also provides network policy enforcement (pod-level firewall rules using iptables
or eBPF). Used by many large-scale K8s deployments.

**Cilium**: Uses eBPF (extended Berkeley Packet Filter) — a programmable in-kernel
data plane. Instead of programming iptables rules (which scale poorly beyond thousands
of entries), Cilium compiles eBPF programs that run directly in the kernel for packet
processing. Faster than iptables-based solutions, and provides deep observability
(because eBPF can observe every packet in the kernel without overhead).

**Flannel**: The simplest CNI option. Uses VXLAN to create an overlay network —
pod packets are encapsulated in UDP packets and sent over the existing network.
Slower than native routing (encapsulation/decapsulation overhead) but works on any
network without BGP support. Common in on-premise environments.

**Weave**: Another overlay-based CNI, uses its own protocol. Has multicast support
useful for some legacy application patterns.

### 6.3 How Calico Uses BGP

BGP is the same routing protocol that powers the internet. Calico uses it internally
to distribute pod routes:

1. Each node runs a BGP daemon (BIRD or GoBGP)
2. When a pod is created on node-A, Calico programs a route: "10.0.1.5/32 via veth on node-A"
3. Node-A's BGP daemon announces "I own 10.0.1.0/24" to all other nodes
4. All other nodes add a route: "to reach 10.0.1.0/24, send to node-A's IP"
5. Pod-B on node-B can now reach pod-A's IP directly without any encapsulation

This is why Calico is popular: it is as fast as regular IP routing, because it IS
regular IP routing. No tunnels, no encapsulation overhead.

The limitation: it requires the physical network to allow BGP between nodes. In most
cloud environments, this works because the cloud network is programmable. In some
enterprise environments with restrictive firewall rules, BGP may be blocked, and
Calico falls back to VXLAN.

### 6.4 Services — Stable Virtual IPs

Pods come and go. Their IPs change when they restart. How do you connect to a backend
service when its pods are constantly being created and deleted?

Kubernetes Services solve this with a stable virtual IP called a ClusterIP. A Service
defines a selector (e.g., `app: payment`) and is assigned a stable ClusterIP
(e.g., 10.96.50.100). Traffic sent to 10.96.50.100 is automatically load-balanced
across all pods matching the selector, regardless of their current IPs.

Service types:

**ClusterIP**: Internal only. The ClusterIP is only reachable from within the cluster.
Used for service-to-service communication.

**NodePort**: Exposes the service on a static port (e.g., 30080) on every node's IP.
External clients can reach `any-node-ip:30080`. Used for simple external access.
Limitation: fixed ports, no SSL termination, inefficient routing.

**LoadBalancer**: Requests a cloud load balancer from the cloud provider (via the
cloud-controller-manager). The cloud creates an external load balancer (e.g., AWS NLB)
that forwards traffic to NodePorts. The most common way to expose services externally
in cloud environments.

**ExternalName**: Maps the service to an external DNS name. No proxying; just a CNAME.

### 6.5 kube-proxy — How Services Are Actually Implemented

Every ClusterIP is a virtual IP (VIP) — it does not correspond to any real network
interface. It only exists in iptables rules programmed by kube-proxy. When a pod sends
a packet to 10.96.50.100:80, the Linux kernel runs it through the PREROUTING chain,
hits a kube-proxy-programmed rule, and randomly rewrites the destination to one of
the backend pod IPs.

```
POD sends packet to:
  dst = 10.96.50.100:80 (ClusterIP)

iptables PREROUTING chain:
  MATCH -d 10.96.50.100 -p tcp --dport 80
  → jump to KUBE-SVC-XXXX

KUBE-SVC-XXXX:
  33% probability → KUBE-SEP-POD1  (10.0.1.5:8080)
  50% probability → KUBE-SEP-POD2  (10.0.2.7:8080)
  100% probability → KUBE-SEP-POD3 (10.0.3.3:8080)

KUBE-SEP-POD1:
  DNAT: rewrite dst to 10.0.1.5:8080
  Packet now goes to actual pod IP.
```

kube-proxy watches the apiserver for Service and EndpointSlice changes and keeps
these iptables rules up to date. When a pod becomes ready, its IP is added to the
rules. When it becomes unready or is deleted, it is removed.

**The iptables scalability problem**: iptables rules are linear — the kernel evaluates
them one by one. With 10,000 services and 50,000 pods, iptables has hundreds of
thousands of rules. Updating one service endpoint requires rewriting a large portion
of the rule chain (iptables is not surgical). This causes noticeable CPU spikes and
latency during service updates. This is why **IPVS mode** (kube-proxy can use IPVS
instead of iptables) and **Cilium** (bypasses iptables entirely with eBPF) exist for
large clusters.

### 6.6 CoreDNS — Service Discovery

How does your pod know that 10.96.50.100 is the payment service? It should not have
the IP hardcoded — IPs change between clusters and environments. The answer is DNS.

CoreDNS is a DNS server that runs inside the cluster (as a Deployment in kube-system).
The kubelet configures every pod to use CoreDNS as its DNS resolver. When a pod
does `curl http://payment-service/api`, it resolves `payment-service` via DNS.
CoreDNS has a plugin that watches K8s Services and resolves service names to ClusterIPs.

DNS resolution patterns:
- `payment-service` → resolves within same namespace
- `payment-service.production` → cross-namespace lookup
- `payment-service.production.svc.cluster.local` → fully qualified

CoreDNS scales by running multiple replicas. In large clusters with heavy DNS load
(millions of requests/second), CoreDNS can become a bottleneck. Solutions: NodeLocal
DNSCache (a daemonset that caches DNS responses on each node, avoiding per-pod DNS
traffic hitting the central CoreDNS), or tuning CoreDNS pod resources.

**Real Incident: CNI Misconfiguration at Scale**

A financial services company migrated from Flannel to Calico to get native routing
speed and network policy support. During the migration, they configured Calico with
a pod CIDR that overlapped with an internal company network subnet (10.0.0.0/8 was
the company network; they configured Calico pod CIDR as 10.10.0.0/16, which fell
inside the company range).

The BGP announcements from Calico caused Calico's pod routes to "win" over the
corporate network routes in the node routing table. Any pod-to-corporate-network
traffic was being blackholed because the kernel was routing it toward pod IPs that
did not exist. The production impact: all pods that called internal APIs (databases,
internal microservices) suddenly failed. The fix: reconfigure Calico's pod CIDR to
use a non-overlapping range (172.16.0.0/12) and drain/re-provision all nodes. Total
downtime: 4 hours for the affected services. The lesson: always validate that the pod
CIDR, service CIDR, and node IP ranges are completely non-overlapping with each other
and with any corporate network CIDRs.

---

### Brainstorming: Part 6

**Q: Why does Kubernetes use a flat pod network instead of port mapping like Docker?**

Docker's default mode maps host ports to container ports, meaning two containers on
the same host cannot both listen on port 80 — only one can have the port mapping.
This creates a port management problem at scale: you need to track which ports are
available on which hosts and coordinate port assignments across all containers. This
is complex operational overhead that gets worse as the cluster grows.

The flat pod network eliminates this entirely. Each pod has its own IP, so each pod
can listen on port 80 simultaneously without conflict. Two hundred pods all listening
on port 8080 is perfectly fine — they each have a different IP. Port conflicts only
occur within a pod (since containers in a pod share a network namespace), not between
pods. This simplification is enormous at scale: you can run heterogeneous workloads
with overlapping port requirements without any coordination overhead.

**Q: How does kube-proxy know which pods are ready to receive traffic?**

kube-proxy does not watch pods directly. Instead, it watches EndpointSlice objects.
EndpointSlices are maintained by the EndpointSlice controller (in kube-controller-manager),
which watches pods and their readiness conditions. When a pod's readiness probe passes,
the kubelet sets `pod.status.conditions.ready = true`. The EndpointSlice controller
sees this change and adds the pod's IP and port to the relevant EndpointSlice objects.
kube-proxy watches EndpointSlices and updates iptables accordingly.

This indirection is important: kube-proxy is decoupled from pod liveness. The
EndpointSlice controller is the single source of truth for which pod IPs should
receive traffic. If you want to debug why traffic is not reaching a pod, check:
(1) is the pod in Running state? (2) is the readiness probe passing? (3) is the pod's
IP in the EndpointSlice? (4) are kube-proxy's iptables rules updated? Each of these
can be independently verified with `kubectl get pod -o yaml`, `kubectl describe pod`,
`kubectl get endpointslices`, and `iptables -t nat -L KUBE-SVC-XXX`.

**Q: What is a headless service, and when would you use one?**

A headless service is created by setting `clusterIP: None`. Instead of a single
ClusterIP, CoreDNS returns the individual pod IPs directly. When you DNS-resolve a
headless service, you get multiple A records — one per pod. This means the client is
responsible for load balancing (or picking a specific pod).

Headless services are used for stateful workloads (like databases) where you want to
connect to a specific pod, not a random one. StatefulSets use headless services to
give each pod a stable DNS name: `pod-0.my-statefulset.namespace.svc.cluster.local`
always resolves to the same pod IP, even if the pod restarts (it gets the same IP
back because the StatefulSet preserves the pod name). This is how you run a Kafka
cluster or Postgres cluster in K8s where each node needs a stable identity.

---

## Part 7: Storage — Persistent Volumes and Stateful Workloads

### 7.1 The Problem with Container Storage

Containers are ephemeral. When a container restarts, its filesystem is reset to the
image state. If your database wrote data to its local filesystem, that data is gone
on restart. You need storage that persists beyond the container lifecycle.

Kubernetes solves this with the PersistentVolume (PV) / PersistentVolumeClaim (PVC)
abstraction. The goal is separation of concerns: the cluster administrator provisions
storage (or configures dynamic provisioning), and the developer just requests "I need
50GB of storage" without knowing where it comes from.

### 7.2 PV, PVC, and StorageClass

**PersistentVolume (PV)**: A piece of storage in the cluster. Can be provisioned
manually by an admin (static) or automatically (dynamic). A PV has a capacity, access
modes, and a binding to a specific storage backend (EBS volume, NFS share, Ceph RBD).

**PersistentVolumeClaim (PVC)**: A request for storage by a pod. Specifies size,
access mode, and optionally a StorageClass. The control plane binds a PVC to a matching
PV. Once bound, the PVC is used in a pod spec as a volume reference.

**StorageClass**: Defines the type of storage and the provisioner to use. When a PVC
references a StorageClass, the StorageClass's provisioner automatically creates a PV.
This is dynamic provisioning — no pre-provisioning required.

```
Developer creates PVC:
  apiVersion: v1
  kind: PersistentVolumeClaim
  spec:
    storageClassName: gp3-encrypted    ← references StorageClass
    accessModes: [ReadWriteOnce]
    resources.requests.storage: 50Gi

StorageClass "gp3-encrypted":
  provisioner: ebs.csi.aws.com
  parameters:
    type: gp3
    encrypted: "true"

Flow:
PVC created → StorageClass controller → calls EBS CSI driver → creates EBS volume
→ PV object created in K8s → PV bound to PVC → pod can mount PVC
```

### 7.3 Access Modes

**ReadWriteOnce (RWO)**: The volume can be mounted read-write by a single node.
Most block storage (EBS, GCE PD, Azure Disk) supports only RWO. Two pods on the same
node can share an RWO volume, but you cannot mount an RWO volume on two different nodes
simultaneously.

**ReadOnlyMany (ROX)**: The volume can be mounted read-only by many nodes simultaneously.
Useful for sharing read-only configuration or datasets.

**ReadWriteMany (RWX)**: The volume can be mounted read-write by many nodes simultaneously.
Required for shared storage (e.g., NFS, CephFS, AWS EFS). Block storage (EBS) does NOT
support RWX — you must use a network filesystem.

The access mode is enforced by the control plane and the storage driver — it is not a
soft suggestion. If you try to mount an RWO volume on a second node, the mount will
fail.

### 7.4 StatefulSets — Pods with Identity

StatefulSets manage pods that need stable network identity and stable storage. Unlike
Deployments (where pods are interchangeable), StatefulSet pods have:
- Ordered names: pod-0, pod-1, pod-2 (not random hashes)
- Stable DNS: `pod-0.my-statefulset.namespace.svc.cluster.local` always points to pod-0
- Per-pod PVCs: each pod gets its own PVC (volumeClaimTemplates), so pod-0 always gets
  its own persistent volume, not shared with pod-1

StatefulSets also manage ordered deployment and deletion: pod-0 starts before pod-1,
pod-1 before pod-2. Deletion is reverse order. This is essential for distributed
databases where node order matters for cluster formation (e.g., the Kafka broker with
ID 0 must start first to initialize the cluster metadata).

Used for: Kafka, Elasticsearch, Postgres (in K8s), Cassandra, Redis Cluster, etcd itself.

### 7.5 CSI — Container Storage Interface

Just as CRI abstracts the container runtime, CSI (Container Storage Interface) abstracts
storage drivers. The control plane communicates with storage drivers via a gRPC API.
CSI drivers are shipped as K8s DaemonSets/Deployments by storage providers (AWS,
GCP, Portworx, Ceph). The kubelet calls the node-local CSI driver component to
mount/unmount volumes.

Before CSI, storage driver code was compiled into the K8s binary (in-tree drivers).
This meant adding a new storage provider required a K8s release. CSI allows out-of-tree
drivers: any storage vendor can write a CSI driver without modifying K8s code. This
was a significant plugin architecture improvement.

---

### Brainstorming: Part 7

**Q: What happens to PVCs when a pod is deleted? When a StatefulSet is deleted?**

When a pod is deleted, its PVCs are NOT deleted. The PVC lifecycle is independent of the
pod lifecycle. If you delete a pod (even delete and recreate it via a Deployment rollout),
the PVC remains bound to its PV and will be mounted by the new pod when it starts.
This is intentional — you do not want to lose your database data every time a pod restarts.

When a StatefulSet is deleted, the PVCs it created also survive by default. The
volumeClaimTemplates in a StatefulSet do not follow the StatefulSet's lifecycle. This
means if you delete a StatefulSet and recreate it, the new pods will reattach to the
original PVCs (because they have the same names: `data-pod-0`, `data-pod-1`, etc.) and
pick up where they left off. To actually delete the data, you must explicitly delete
the PVCs. This is a safety feature — inadvertently deleting a StatefulSet should not
wipe your Kafka topic data.

**Q: How do you run a database in K8s properly? Is it recommended?**

Running databases in K8s has become much more common and viable. The key requirements
are: (1) use StatefulSets for stable identity; (2) use PVCs with appropriate StorageClass
(prefer local SSDs for performance-sensitive DBs, networked storage for simpler DBs);
(3) set appropriate resource requests and limits; (4) use PodDisruptionBudgets to
prevent simultaneous eviction of too many DB replicas; (5) use dedicated nodes with
taints for DB pods to prevent noisy neighbors.

The primary concern is that K8s adds operational complexity for stateful workloads that
managed database services (RDS, Cloud SQL) handle for you. If you need point-in-time
recovery, automated failover, cross-region replication, or you do not have deep DB-on-K8s
expertise, managed services are often the right choice. But for teams that want
infrastructure uniformity (everything on K8s) or have specific needs (on-premise, air-gapped,
custom configuration), running databases in K8s with StatefulSets and operators (like
the Postgres Operator, Kafka Operator) is viable and widely deployed at scale.

---

## Part 8: kubectl apply End-to-End Trace

### 8.1 The Full Journey

This is the question that separates L5 and L6 candidates: trace everything that
happens between `kubectl apply -f deployment.yaml` and the pods running.

```
USER RUNS:
kubectl apply -f deployment.yaml
(Deployment: app=frontend, replicas=3, image=nginx:1.25)

STEP 1: kubectl
  - Reads kubeconfig (~/.kube/config) to get apiserver URL + credentials
  - Reads the YAML, converts to internal object
  - Determines operation: does Deployment exist? → PATCH; does not exist? → POST
  - Sends HTTP POST to:
    https://apiserver:6443/apis/apps/v1/namespaces/default/deployments

STEP 2: kube-apiserver receives the request
  - Authentication: checks certificate or token → identity confirmed
  - Authorization: RBAC check: does this user have "create deployments" in "default"?
  - Mutating Admission Webhooks: any registered webhooks run first
    (e.g., auto-inject sidecar, add labels, set default resource limits)
  - Object Validation: is the Deployment spec well-formed? Required fields present?
  - Validating Admission Webhooks: any registered validation webhooks run
    (e.g., reject if no resource limits set, enforce naming conventions)
  - If all pass: serialize to protobuf, write to etcd
  - Respond to kubectl: 201 Created

STEP 3: Deployment Controller (in kube-controller-manager) sees new Deployment
  - Watch stream delivers ADDED event for the new Deployment
  - Reconcile: desired replicas=3, current ReplicaSets=0 → create ReplicaSet
  - Creates ReplicaSet object in apiserver (which writes to etcd)
  - ReplicaSet has spec: replicas=3, selector: app=frontend

STEP 4: ReplicaSet Controller sees new ReplicaSet
  - Watch stream delivers ADDED event for the new ReplicaSet
  - Reconcile: desired replicas=3, current Pods=0 → create 3 Pods
  - Creates 3 Pod objects in apiserver
  - Each Pod has: spec.nodeName="" (not yet scheduled), status.phase=Pending

STEP 5: Scheduler sees 3 unscheduled Pods
  - Watch stream delivers ADDED events for 3 Pods with nodeName=""
  - For each Pod, runs scheduling pipeline:
    a. Filter: run NodeResourcesFit, NodeAffinity, TaintToleration, etc.
    b. Score: run LeastAllocated, ImageLocality, etc.
    c. Select winner node
    d. Write Binding to apiserver: "assign pod-1 to node-7"
  - apiserver sets spec.nodeName = "node-7" on the Pod
  - Pod status.phase is still Pending (assigned but not started)

STEP 6: kubelet on node-7 sees a new Pod assigned to it
  - Watch stream delivers MODIFIED event for the Pod (nodeName just got set)
  - kubelet starts pod lifecycle:
    a. Pull image: nginx:1.25
       - Check local image cache (containerd)
       - If not cached: pull from registry (authenticated via imagePullSecrets)
    b. Create pod sandbox (pause container)
       - Call CNI plugin to set up network namespace
       - CNI plugin assigns pod IP (e.g., 10.0.7.42) and programs routes
    c. Run init containers (if any, sequentially)
    d. Create and start app container via CRI (gRPC to containerd):
       - RunPodSandbox
       - PullImage (if not already done)
       - CreateContainer
       - StartContainer
    e. Set up cgroup limits (CPU throttling, memory limit)

STEP 7: kubelet monitors probes
  - If startupProbe defined: wait for it to pass before enabling other probes
  - livenessProbe: run per periodSeconds, restart container on failure
  - readinessProbe: run per periodSeconds

STEP 8: kubelet reports pod status
  - Updates pod status in apiserver: phase=Running, containerStatuses.ready=true
  - Pod conditions: Ready=True

STEP 9: EndpointSlice controller updates Service endpoints
  - Watches pod Ready condition become True
  - Adds pod IP (10.0.7.42:80) to the EndpointSlice for the frontend Service

STEP 10: kube-proxy updates iptables rules
  - Watches EndpointSlice change
  - Updates iptables rules on node-7 (and all other nodes) to include new pod IP
  - Traffic to ClusterIP 10.96.1.100:80 now randomly directed to 3 pod IPs

PODS ARE NOW RUNNING AND RECEIVING TRAFFIC
Total elapsed time: ~30-60 seconds for first deployment
(15s image pull + 5s container start + 5-10s probe warmup + propagation delays)
```

### 8.2 The Layered Diagram

```
kubectl apply
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  kube-apiserver                                                 │
│  AuthN → AuthZ → Mutating Admission → Validate → ValidAdmission│
│  → serialize → write etcd                                       │
└───────────────────────────┬─────────────────────────────────────┘
                            │ watch
              ┌─────────────┼──────────────┐
              ▼             ▼              ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │  Deployment  │ │  ReplicaSet  │ │  Scheduler   │
    │  Controller  │ │  Controller  │ │              │
    │  (creates RS)│ │  (creates    │ │  (assigns    │
    │              │ │   Pods)      │ │   nodeName)  │
    └──────────────┘ └──────────────┘ └──────────────┘
                                              │
                                              │ watch (by node)
                                              ▼
                                    ┌──────────────────┐
                                    │    kubelet        │
                                    │    (node-7)       │
                                    │  pull → create →  │
                                    │  start → probe →  │
                                    │  report status    │
                                    └──────────────────┘
                                              │
                                              ▼
                                    ┌──────────────────┐
                                    │  containerd/CRI  │
                                    │  (actually runs  │
                                    │   the container) │
                                    └──────────────────┘
```

---

### Brainstorming: Part 8

**Q: How does K8s handle the case where the apiserver receives a request but crashes before writing to etcd?**

The apiserver treats the write to etcd as authoritative. If the apiserver crashes
between receiving the kubectl request and writing to etcd, the write simply does not
happen. kubectl's connection drops (it may see a 500 or a connection reset), and the
object is not created. The caller must retry. This is an at-most-once semantic for
individual API calls, which is correct for resource management — creating a Deployment
twice would create two Deployments, which is wrong. The apiserver does not use a
transaction log for recovery, it relies on the idempotent retry from the client.

For controllers that create child objects (Deployment controller creating ReplicaSets),
a crash between "create ReplicaSet" and "update Deployment status" means on restart,
the controller will reconcile again. It will check if a ReplicaSet exists (it does,
since that write succeeded) and not create a duplicate (because it checks by owner
reference before creating). This idempotent reconcile pattern means controller crashes
are safe — they just retry their work.

**Q: What is the role of Admission Webhooks in the apply flow, and why are they important?**

Admission webhooks are HTTP callbacks that the apiserver calls during the admission
phase of object creation/modification. There are two types: mutating (can modify the
object) and validating (can accept or reject the object). They are important because
they allow platform teams to enforce policies and inject configuration without modifying
the K8s core.

Examples: a mutating webhook can inject a sidecar container into every pod (this is
how Istio service mesh works — it auto-injects the Envoy proxy sidecar by mutating
pod specs on admission). A validating webhook can reject pods without resource limits
(enforcing a policy that all pods must declare their resources for capacity planning).
Webhooks are called synchronously in the request path, so they add latency to every
object creation. They must be fast (under 3 seconds) and highly available (if the
webhook server is down and the webhook is configured as required, all pod creation fails).
This last point is a common production pitfall: a misconfigured or crashed admission
webhook can break all pod scheduling in the cluster.

---

## Part 9: Common Failure Modes — What Goes Wrong and Why

### 9.1 CrashLoopBackOff

**What it is**: The container keeps starting, crashing, being restarted, crashing
again. K8s applies exponential backoff to restarts (10s, 20s, 40s, 80s, 160s, 300s
max), so the pod cycles through these delays.

**Common causes**:
- Application bug causing a crash on startup (check logs for stack trace)
- Missing environment variable or secret causing a panic
- Liveness probe configured too aggressively (probe fails before app is ready →
  container killed → restarted → killed again → CrashLoopBackOff)
- Insufficient memory causing OOMKilled on startup
- Init container failing (blocks the main container from starting)

**Debug commands**:
```bash
kubectl describe pod <name>     # shows events, probe config, restart count
kubectl logs <name>             # current container logs
kubectl logs <name> --previous  # logs from LAST crashed container
kubectl exec -it <name> -- /bin/sh  # if the container is running, exec in
```

### 9.2 Pending Forever

**What it is**: The pod is created but the scheduler cannot find a node for it.

**Common causes**:
- Insufficient resources: every node fails NodeResourcesFit (request 4 CPU, all nodes
  have < 4 CPU available)
- Node taints: nodes are tainted and the pod does not tolerate the taint
- Node affinity/selector: pod requires `zone=us-east-1a` but no nodes have that label
- PVC pending: the pod's PVC has not been provisioned yet (StorageClass provisioner
  issue, or PVC stuck in Pending because no PV matches)
- Too many anti-affinity constraints: pod wants to be spread but cannot fit

**Debug commands**:
```bash
kubectl describe pod <name>     # shows scheduler events: "0/10 nodes available: ..."
kubectl get nodes -o wide       # check node count and status
kubectl describe node <node>    # check taints, allocated resources
kubectl get pvc                 # check if PVCs are bound
```

### 9.3 ImagePullBackOff

**What it is**: The kubelet cannot pull the container image. K8s applies backoff to
pull retries.

**Common causes**:
- Wrong image name or tag (typo)
- Private registry with missing or invalid `imagePullSecrets`
- Registry temporarily unavailable (rate limiting: Docker Hub limits unauthenticated pulls
  to 100 per 6 hours per IP — a K8s cluster's shared NAT IP can hit this easily)
- Image does not exist for the node's architecture (ARM node trying to pull AMD64 image)

**Debug commands**:
```bash
kubectl describe pod <name>     # "Failed to pull image: 404 not found"
kubectl get secret <pull-secret> -o yaml  # check imagePullSecret content
docker pull <image>             # test from outside cluster to verify image exists
```

### 9.4 OOMKilled

**What it is**: The container exceeded its `resources.limits.memory` and was killed
by the Linux OOM killer. `kubectl describe pod` shows the last container state as
`OOMKilled` with exit code 137.

**Root causes**:
- Memory limit too low for the workload
- Memory leak in the application
- JVM heap settings wrong (JVM defaulting to 25% of physical node RAM, not container limit)

**Fix**: Either increase the memory limit, fix the memory leak, or for JVM apps, set
`-XX:MaxRAMPercentage=75.0` so the JVM respects container limits.

### 9.5 etcd Disk Pressure (Cluster-Wide Impact)

Already covered in Part 2. The key symptoms:
- All kubectl operations timing out
- "etcdserver: request timed out" in apiserver logs
- Spurious leader elections in etcd logs
- p99 etcd write latency > 25ms (monitor via `etcd_disk_wal_fsync_duration_seconds`)

### 9.6 Node NotReady

**What it is**: A node is in the cluster but its status is NotReady — the kubelet
is not sending heartbeats.

**Common causes**:
- Node out of disk space (kubelet cannot write logs/state)
- Node out of memory (OOM killer killed the kubelet process)
- Network partition (kubelet running but cannot reach apiserver)
- kubelet process crashed or not running (`systemctl status kubelet` on the node)
- Container runtime crashed (kubelet cannot communicate with containerd)

**What happens to pods**: After 40s NotReady, Node controller marks it NotReady.
After 5 minutes NotReady, Node controller starts evicting pods (deleting them from
etcd). The pods are then rescheduled on healthy nodes (if owned by a Deployment/ReplicaSet).
Pods NOT owned by a controller (bare pods) are stuck Terminating until the node comes
back or they are force-deleted.

**Force-delete stuck Terminating pods**:
```bash
kubectl delete pod <name> --grace-period=0 --force
```
Use with caution — the pod might still be running on the unresponsive node.

---

### Brainstorming: Part 9

**Q: A pod is stuck Terminating and kubectl delete does not work. Why and what do you do?**

A pod stuck in Terminating is usually because the node it was running on is unreachable.
When you delete a pod, the apiserver sets a `deletionTimestamp` on the pod (marking it
for deletion) and the kubelet on the node is responsible for stopping the container and
sending a final update to the apiserver to confirm deletion. If the kubelet is
unreachable (node is down or partitioned), it cannot confirm the deletion, and the pod
stays in Terminating indefinitely.

The resolution depends on the situation. If the node is truly gone (hardware failure,
deleted), you can force-delete with `--grace-period=0 --force`, which removes the pod
from etcd without waiting for kubelet confirmation. This is safe if you know the node is
gone (the container cannot still be running on it). If the node is just partitioned but
might come back, force-deleting is risky for stateful workloads — the pod might be both
"force-deleted and recreated elsewhere" AND "still running on the original node" (a split-brain
scenario for databases). For stateless workloads, force-delete is usually safe.

**Q: How do you debug a pod that is running but returning errors intermittently?**

Intermittent errors are harder than consistent failures. The toolkit: `kubectl logs -f`
for streaming logs; `kubectl exec -it pod -- bash` to execute commands inside the pod
(check if it can reach its dependencies, check its config files); `kubectl top pods`
to see CPU and memory usage (is it being CPU throttled?); check readiness probe config
(is the pod being removed from endpoints intermittently?). Also check the pod's resource
usage against its limits — CPU throttling causes latency spikes rather than crashes, and
is diagnosed by checking `container_cpu_cfs_throttled_seconds_total` in the Prometheus
metrics on the node.

For networking issues, `kubectl exec -it pod -- curl http://dependency-service` tests
connectivity. If DNS is failing, `kubectl exec -it pod -- nslookup kubernetes.default`
tests CoreDNS resolution. For iptables-related issues, `kubectl get endpoints
service-name` shows whether the pod is in the endpoints list — if it keeps flapping in
and out, the readiness probe is intermittently failing.

---

## Part 10: Kubernetes as a Platform — Extension Points

### 10.1 Custom Resource Definitions (CRDs)

Kubernetes has a generic extension mechanism for adding new object types: Custom
Resource Definitions (CRDs). A CRD defines a new API endpoint in the apiserver.
Once a CRD is installed, you can create, get, list, watch, and delete instances of
the new type using kubectl and the apiserver, just like built-in types.

Example: define a CRD for `MySQLCluster`:

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: mysqlclusters.db.example.com
spec:
  group: db.example.com
  versions:
    - name: v1alpha1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              properties:
                replicas: {type: integer}
                version: {type: string}
  scope: Namespaced
  names:
    plural: mysqlclusters
    singular: mysqlcluster
    kind: MySQLCluster
```

After applying this CRD, you can do:
```bash
kubectl apply -f my-mysql-cluster.yaml   # creates a MySQLCluster object in etcd
kubectl get mysqlclusters                # list all MySQLCluster objects
kubectl describe mysqlcluster my-cluster
```

The CRD just defines the type and validates the schema. It does not make anything
happen by itself. To act on the custom resource, you need an Operator.

### 10.2 Operators — The Controller + CRD Pattern

An Operator is a controller that watches a custom resource type and takes real
operational actions to manage complex software. The pattern: someone who knows how
to operate (e.g., a MySQL database) codifies that operational knowledge as a controller.

The MySQL Operator watches `MySQLCluster` objects. When you create a `MySQLCluster`,
the operator:
1. Creates a StatefulSet with the right number of MySQL pods
2. Creates Services for primary and replica access
3. Configures replication between pods
4. Handles failover when the primary fails (promotes a replica to primary)
5. Manages backup schedules
6. Handles version upgrades (rolling restart with schema migration)

All of this happens automatically when you do `kubectl apply -f my-mysql-cluster.yaml`.
The operational complexity is encoded in the operator, not in runbooks.

Well-known operators: Prometheus Operator, Kafka Operator (Strimzi), Postgres Operator,
Elasticsearch Operator (ECK), Cert-Manager (manages TLS certificates), ArgoCD.

The operator pattern is so powerful that it is now the standard way to run complex
stateful systems in K8s. When someone asks "can you run X in K8s?", the answer is
often "yes, if there is an operator for X" or "yes, if you write an operator for X."

### 10.3 Admission Webhooks — Policy Enforcement

Admission webhooks are called during the API request pipeline, allowing you to:
- **Mutate** objects before they are persisted (mutating admission webhooks)
- **Validate** objects and reject invalid ones (validating admission webhooks)

Common uses:
- Auto-inject Istio sidecar proxy into pods (mutating)
- Enforce that all pods have resource requests/limits set (validating)
- Auto-add default labels or annotations (mutating)
- Prevent deployment to production namespace without specific approvals (validating)
- Inject secrets from Vault into pod specs (mutating)

Admission webhooks are implemented as HTTP servers that the apiserver calls. The
apiserver sends an `AdmissionReview` JSON object containing the object being admitted
and receives a response with either a patch (for mutating) or an allowed/denied decision.

**Critical operational concern**: If a mutating or validating webhook is unavailable
and is configured as `failurePolicy: Fail` (the default for most security-focused
webhooks), ALL object creations of the matched type will fail. This means a crashing
admission webhook can prevent any pod from being scheduled. Always ensure admission
webhooks are highly available (multiple replicas) and test your `failurePolicy`
settings. `failurePolicy: Ignore` allows the request through if the webhook is
unavailable (less secure but safer operationally for non-critical webhooks).

### 10.4 When to Use Each Extension Point

```
QUESTION → EXTENSION POINT

"I need a new type of K8s object" → CRD

"I need to manage complex software automatically" → CRD + Operator

"I need to enforce a policy on all object creations" → Validating Admission Webhook

"I need to auto-inject config into pods" → Mutating Admission Webhook

"I need custom scheduling logic" → Scheduler Extender or Scheduler Plugin

"I need custom metrics for HPA" → Custom Metrics API (Prometheus Adapter)

"I need custom storage" → CSI Driver

"I need custom networking" → CNI Plugin
```

---

### Brainstorming: Part 10

**Q: What is the difference between a mutating and a validating admission webhook, and which runs first?**

Mutating admission webhooks run first, then validating admission webhooks. This
ordering is critical: mutating webhooks can modify the object (e.g., adding default
values or injecting sidecars), and then validating webhooks validate the final form
of the object (including any mutations). If validating ran before mutating, the
validator might reject an object that would have been valid after mutation, or pass
an object that mutation would have modified to be invalid.

The practical implication: if you have a mutating webhook that adds a required label
and a validating webhook that checks for that label, the ordering ensures this works
correctly. Mutating webhook adds the label, validating webhook sees the labeled object
and passes it. If the order were reversed, the validating webhook would see the
unlabeled object and reject it, even though it would have been fine after mutation.

**Q: Why would you write an operator instead of just using helm charts and Terraform?**

Helm charts and Terraform are great for initial deployment but lack operational
intelligence. They can deploy a MySQL cluster but cannot handle a failover event —
when the MySQL primary crashes, Helm and Terraform do not know to promote a replica.
An operator does, because it is running continuously and reacting to events.

Think of the difference between declarative configuration (specify desired state once
and provision) and operational control loops (continuously watch and react). An operator
gives you control loops for domain-specific operations that the generic K8s controllers
do not know about. The canonical example is a database: K8s knows how to restart pods,
but it does not know that when a MySQL primary pod restarts, you need to reconfigure
all the replica pods to point to the new primary before it becomes healthy. That
domain-specific knowledge is what an operator encodes as code.

---

## Part 11: Borg → Kubernetes — Lineage and Differences

### 11.1 The Direct Lineage

Kubernetes was created by ex-Googlers who worked on Borg (Craig McLuckie, Joe Beda,
Brendan Burns). They took the ideas from Borg and built an open-source version,
deliberately designing it for a wider audience while keeping the core concepts.
Understanding the lineage explains why K8s was designed the way it was.

### 11.2 Concept Mapping

| Borg Concept       | K8s Equivalent          | Notes                                      |
|--------------------|-------------------------|--------------------------------------------|
| Task               | Container               | Basic unit of work                         |
| Job                | Deployment/StatefulSet  | K8s more explicit about type               |
| Alloc              | Pod                     | Pod = co-located containers (like Borg alloc) |
| BNS (Borg Name Svc)| CoreDNS + Services      | K8s uses standard DNS                      |
| Borgmaster         | kube-apiserver + etcd   | Borg uses Paxos; K8s uses Raft (etcd)     |
| Scheduler          | kube-scheduler          | Nearly identical two-phase approach        |
| Borglet            | kubelet                 | Direct equivalent, same role               |
| Borg ACLs          | RBAC                    | K8s RBAC is more flexible                  |
| Omega              | CRD + Operators         | Omega's multi-scheduler → K8s extensibility|

### 11.3 What K8s Improved Over Borg

**Pod abstraction (co-located containers)**: Borg's "alloc" concept (a set of tasks
that should be placed together) was less first-class than K8s's Pod. K8s made
co-located containers (sidecars, init containers) a central pattern.

**Open ecosystem**: Borg is Google-internal. K8s is open-source with a huge ecosystem
of operators, CNI plugins, CSI drivers, admission webhooks. The extensibility story
(CRDs, operators) did not exist in Borg.

**Networking model**: Borg's networking was Google-internal. K8s standardized the
CNI plugin model, allowing the community to build diverse networking solutions.

**Labels and selectors**: K8s's label system (arbitrary key-value pairs + selectors)
is more flexible than Borg's job-level naming. It enables cross-cutting groupings
that span multiple deployments.

**RBAC and multi-tenancy**: K8s has a well-developed RBAC system and namespace model
for multi-tenancy. Borg was single-tenant (one company) and did not need it.

### 11.4 What Borg Still Does Better

**Efficiency**: Borg runs at much higher cluster utilization rates than typical K8s
deployments. Google runs machines at 60-70% utilization; enterprise K8s is often
at 20-30%. Borg's scheduler has decades of tuning and Google-scale workload data.

**Heterogeneous workloads**: Borg was designed from day one for both long-running
services and batch workloads (MapReduce, Colossus jobs). K8s's batch support
(Jobs, CronJobs) is adequate but less capable than Borg's for large-scale analytics.

**Performance at scale**: Borg runs hundreds of thousands of machines per cluster.
K8s's default apiserver + etcd architecture has practical limits around 5,000 nodes
per cluster (the "5000-node limit"). Very large K8s deployments require federation
or sharding. Borg was built for Google's scale from the beginning.

---

### Brainstorming: Part 11

**Q: Why didn't Google just open-source Borg instead of creating Kubernetes?**

Borg is deeply entangled with Google's internal infrastructure, naming systems,
job configuration language (BCL/Borgcfg, a Python-based DSL), internal file systems
(Colossus), and internal security systems. Open-sourcing it would require either
exposing those systems or ripping out so many dependencies that you would effectively
be building a new system. Additionally, Borg had accumulated 15 years of tech debt
and design decisions that made sense at Google (single tenant, uniform infrastructure)
but would not be appropriate for general use.

Kubernetes was a "clean slate" attempt to take the good ideas from Borg (reconciliation
loop, two-phase scheduling, node agents) and build them into a portable, extensible
system from the ground up. This also let the K8s team fix things they knew were wrong
with Borg — like the per-job configuration model (K8s labels are much more flexible),
and the lack of a plugin ecosystem.

**Q: Is there a K8s competitor that takes a fundamentally different approach?**

Yes. HashiCorp Nomad takes a simpler approach: it schedules not just containers but
arbitrary executables, VMs, and processes. It has a smaller surface area than K8s
(no CRDs, no operators, no admission webhooks) and is significantly easier to operate.
It is popular for teams that find K8s complexity unwarranted for their scale.

AWS ECS (Elastic Container Service) is proprietary but cloud-native and deeply
integrated with AWS services (IAM, ALB, Service Discovery). For teams fully committed
to AWS, ECS removes the operational burden of running K8s while still providing
container orchestration. The tradeoff is portability — ECS is AWS-only.

Mesos was the predecessor and competitor (used by Twitter and Airbnb at scale) but
has been largely displaced by K8s. Fly.io runs a proprietary orchestration system
built on Firecracker VMs. For the near future, K8s has won the orchestration wars
for general-purpose workloads, but the ecosystem continues to evolve.

---

## Part 12: Interview Application — Using K8s Internals Effectively

### 12.1 L5 vs L6 Calibration

The clearest signal of level in K8s questions is whether the candidate explains
mechanisms or just behaviors.

**L5 Answer Pattern**:
"Kubernetes restarts failed pods automatically. The scheduler puts pods on nodes
based on resource requests. Services load balance traffic across pods."

**L6 Answer Pattern**:
"The ReplicaSet controller runs a reconciliation loop watching etcd via the apiserver
informer. When it sees the actual pod count drop below `spec.replicas`, it creates new
Pod objects. The scheduler's filter phase eliminates nodes with insufficient resources
or taint/toleration mismatches; the score phase selects the best remaining node using
LeastAllocated or MostAllocated depending on the scheduling profile. The kubelet on the
selected node pulls the image via the CRI, sets up the network namespace via CNI,
enforces cgroup limits, and runs probes. Services are implemented as DNAT rules in
iptables programmed by kube-proxy, which watches EndpointSlice objects maintained by
the EndpointSlice controller based on pod readiness conditions."

The L6 answer traces the full mechanism, names the components, and shows understanding
of the interactions. Every sentence could be probed further and the candidate could
explain the next level down.

### 12.2 When K8s Architecture Appears in Interviews

**Platform/infra design questions**: "Design the compute platform for our company's
microservices." → K8s control plane, autoscaling, networking model, storage.

**Reliability questions**: "How would you ensure zero-downtime deployments?" →
RollingUpdate strategy (Ch40), PodDisruptionBudgets, readiness probes, preStop hooks.

**Scale questions**: "What are the limits of a Kubernetes cluster?" → etcd size
limits, apiserver throughput, scheduler throughput, 5000-node limit, multi-cluster
federation.

**Debugging questions**: "Walk me through debugging a pod that is stuck Pending." →
Filter phase, resource requests, taints, affinity, PVC binding — all covered here.

**Design extension questions**: "How would you add custom scheduling logic?" →
Scheduler extenders, scheduler plugins, operator pattern.

### 12.3 The 5-Level Progression for K8s Concepts

**Intern**: Kubernetes runs containers. You write YAML, pods appear.

**Junior Engineer**: Pods are created by Deployments. Services load balance traffic.
A scheduler puts pods on nodes based on resource requests. Liveness probes restart
unhealthy containers.

**Mid-Level Engineer**: The control plane has apiserver, etcd, scheduler, and controllers.
The reconciliation loop keeps actual state matching desired state. CrashLoopBackOff
means the container keeps crashing. kubectl describe shows why pods are Pending.

**Senior Engineer**: Controllers use the watch/informer pattern with local cache to avoid
hammering etcd. The scheduler runs filter predicates and scoring plugins in two phases.
The kubelet uses CRI for container runtime abstraction and CNI for network setup.
etcd disk latency cascades into control plane degradation. Admission webhooks can
block all pod creation if misconfigured.

**Staff/Principal Engineer**: Can trace a kubectl apply through all 10 steps. Can
explain why etcd uses Raft and what the operational implications of etcd cluster size
are. Can design extensions using CRDs, operators, and admission webhooks. Can reason
about the scalability limits of the default architecture (etcd throughput, apiserver
QPS, scheduler throughput) and design mitigations. Can compare K8s's design tradeoffs
against Borg, Nomad, or ECS. Can discuss when NOT to use K8s (small teams, simple
workloads, managed services are better).

### 12.4 Common Interview Mistakes

**Mistake 1: Confusing resources.requests and resources.limits**

Candidates say "the scheduler puts the pod on a node with enough memory" without
specifying what "enough" means. The scheduler considers `resources.requests`, NOT
`resources.limits`. A pod with `requests.memory: 100Mi` and `limits.memory: 2Gi`
will be scheduled as if it needs 100Mi. The 2Gi limit is the ceiling but not the
scheduling criterion. Many candidates get this wrong and it signals shallow knowledge.

**Mistake 2: Saying "Docker" when the runtime is containerd**

Since K8s 1.24, Docker as a runtime is gone. The runtime is containerd (or CRI-O).
Saying "Docker pulls the image" or "Docker starts the container" marks a candidate
as out of date. Say "the container runtime" or specifically "containerd."

**Mistake 3: Not knowing the difference between liveness and readiness probes**

Candidates say "liveness probe controls whether the pod gets traffic." Wrong — that is
the readiness probe. The liveness probe controls whether the container is restarted.
These have very different operational behaviors, and confusing them in a design
discussion signals that you have not actually debugged K8s production issues.

**Mistake 4: Thinking the scheduler talks directly to the kubelet**

The scheduler does not call the kubelet. It writes a Binding to the apiserver, which
sets `spec.nodeName` on the Pod. The kubelet discovers the assignment by watching the
apiserver. This indirection is fundamental — components communicate through etcd (via
apiserver), not directly with each other.

**Mistake 5: Underestimating etcd**

Candidates treat etcd as "just the database" and do not understand why it is the most
operationally critical component. Not knowing that etcd disk latency kills the control
plane, that etcd has a size limit, that etcd requires dedicated SSDs and not shared
disks — these gaps signal you have not operated K8s in production.

**Mistake 6: Treating CRDs and operators as the same thing**

A CRD is a type definition — it tells the apiserver about a new object type. An
operator is a controller that watches that type and does work. You need both. A CRD
alone does nothing; an operator alone has no type to watch. Conflating them shows
surface-level understanding of the extension pattern.

---

## Part 13: Scalability, Performance Tuning, and Multi-Cluster

### 13.1 Where K8s Hits Its Limits

Kubernetes has documented scalability thresholds, called the "scalability SLOs." The
key ones for large-scale operation:

- Maximum nodes per cluster: 5,000 nodes
- Maximum pods per cluster: 150,000 pods
- Maximum pods per node: 110 pods (default; can be raised)
- Maximum services: 10,000 services (iptables mode), more with IPVS/eBPF
- API server request throughput: several thousand requests per second

These limits exist because of how the control plane is architected. The apiserver is
stateless and horizontally scalable, but etcd is not — every write goes through one
leader and must achieve quorum. etcd can handle roughly 10,000 writes per second in a
well-tuned cluster. A 5,000-node cluster with all nodes sending heartbeats every 10
seconds generates 500 writes per second to etcd just for node status. Add pod status
updates, controller operations, and user requests, and etcd throughput becomes the
bottleneck.

The apiserver itself becomes a bottleneck for large clusters because every watch event
must be delivered to every interested watcher. With 1,000 controllers and pods all
watching for Pod changes, and 150,000 pods generating status updates, the apiserver
must fan out events to thousands of watchers simultaneously. This causes "apiserver
fan-out" bottlenecks that manifest as high apiserver latency and watch event delivery
delays.

### 13.2 etcd Performance Tuning

Operators of large K8s clusters tune etcd aggressively:

**Dedicated SSDs**: etcd WAL fsync latency must be under 10ms p99. Only NVMe SSDs
reliably achieve this. SATA SSDs are acceptable. Spinning disks are not. Never share
etcd's disk with other workloads.

**etcd compaction**: etcd accumulates historical revisions of every key. Over time
(hours to days), this consumes significant disk space. Compaction removes old revisions
and defragments the database. Run `etcdctl compact` on a schedule (the apiserver can
be configured to do this automatically with `--etcd-compaction-interval`). Without
regular compaction, etcd grows until it hits the size quota and refuses all writes.

**etcd defragmentation**: Even after compaction, etcd does not immediately reclaim
disk space — it retains free pages in its BoltDB file. Defragmentation reclaims this
space. Run `etcdctl defrag` on one node at a time (defrag causes a brief pause on
that node; running it on all nodes simultaneously would take the cluster below quorum).

**etcd metrics to monitor**:
```
etcd_server_leader_changes_seen_total       # should be low; spikes = instability
etcd_disk_wal_fsync_duration_seconds        # p99 should be < 10ms
etcd_disk_backend_commit_duration_seconds   # p99 should be < 25ms
etcd_server_proposals_failed_total          # failed Raft proposals
etcd_mvcc_db_total_size_in_bytes            # approach 2GB = danger zone
etcd_network_peer_round_trip_time_seconds   # inter-node latency
```

### 13.3 apiserver Performance

The apiserver handles all requests synchronously (each request is one goroutine). It
uses object serialization/deserialization (JSON or protobuf) which is CPU-intensive.
For large clusters, it is common to run 3-5 apiserver replicas behind a load balancer.

**List requests are expensive**: `kubectl get pods --all-namespaces` in a cluster with
150,000 pods causes the apiserver to serialize 150,000 Pod objects and send them over
the network. This can take several seconds and cause significant CPU/memory pressure
on the apiserver. The fix: use field selectors, label selectors, and namespace scoping
to narrow list requests. Better: use informers/watches instead of polling.

**Pagination**: The apiserver supports `--limit` and `--continue` for paginated list
requests. Large controllers should use paginated listing during the initial list phase
to avoid OOMing the apiserver with a single massive response.

**Priority and Fairness (APF)**: K8s has an API Priority and Fairness system that
limits how many requests from a given flow (e.g., requests from a specific controller
or namespace) can be in flight simultaneously. Without APF, a misbehaving controller
doing thousands of requests per second could starve other users of the apiserver.
APF is enabled by default since K8s 1.20 and is configured via
`FlowSchema` and `PriorityLevelConfiguration` objects.

### 13.4 The Scheduler Performance

The scheduler processes pods serially (one scheduling decision at a time), but
parallelizes within each decision (filter runs across all nodes in parallel using
goroutines). For very large clusters with complex policies, the scheduler can become
a throughput bottleneck during large-scale burst scheduling.

**Scheduler throughput optimizations**:
- **Percentage of nodes evaluated**: For large clusters, the scheduler does not
  necessarily evaluate all 5,000 nodes. After filtering, if more than `minFeasibleNodesToFind`
  nodes pass (default: max(5, 50% of nodes)), the scheduler stops evaluating more nodes
  and proceeds to scoring with the found candidates. This trades optimality for speed:
  you might not find the absolute best node, but you find a very good node fast.
- **Scheduling queues**: The scheduler uses three internal queues (ActiveQueue for pods
  to try, BackoffQueue for pods that failed scheduling with exponential backoff,
  UnschedulableQueue for pods that are known to be stuck). Understanding these queues
  is essential for debugging scheduling throughput issues.

**Multiple scheduler instances**: For workloads with dramatically different scheduling
requirements (e.g., GPU batch workloads vs. latency-sensitive web services), some teams
run multiple scheduler instances. Each pod can specify `spec.schedulerName` to use a
non-default scheduler. The two schedulers do not coordinate directly — they each see
the same nodes in etcd, and optimistic concurrency handles the rare case where both try
to schedule to the same node simultaneously (one will lose the Binding write and the
pod will be rescheduled).

### 13.5 Multi-Cluster Architecture

When a single K8s cluster is not enough — too many nodes, regulatory data locality
requirements, multi-region deployment, or blast radius reduction — you move to
multi-cluster architectures.

**Why multiple clusters?**
- Scale: beyond 5,000 nodes, you need more than one cluster
- Blast radius: a control plane outage only affects one cluster
- Regulatory: some data must stay in specific geographic regions
- Environment isolation: separate clusters for dev/staging/prod
- Security: strong tenant isolation (different teams cannot share a cluster)

**Cross-cluster communication**:
Pods in different clusters cannot talk to each other via ClusterIP — the Service model
is cluster-local. Cross-cluster communication requires:
- External load balancers (each cluster exposes services via LoadBalancer services)
- Service meshes with multi-cluster support (Istio, Linkerd — they can federate
  service discovery across clusters)
- Dedicated east-west gateways (Istio east-west gateway pattern)
- API gateways (Kong, Ambassador) fronting all inter-cluster traffic

**Federation**: Kubernetes Federation (KubeFed) was an attempt to manage multiple
clusters as one. It proved complex and is less used now. Modern approaches:
- GitOps with ArgoCD/Flux: deploy the same manifests to multiple clusters via Git
- Cluster API: provision and manage cluster lifecycle as K8s objects
- Virtual clusters (vcluster): run lightweight K8s control planes inside a host cluster,
  giving tenant teams an isolated cluster experience without the overhead of full clusters

### 13.6 Horizontal Pod Autoscaler (HPA) — How K8s Scales Itself

The HPA is a controller that watches pod metrics and scales Deployments/StatefulSets
horizontally (changing `spec.replicas`). By default it uses CPU utilization; with
the metrics adapter, it can use custom metrics (HTTP request rate, queue depth, etc.).

```
HPA Controller loop (every 15 seconds):
  1. Query metrics API for current CPU utilization of target pods
     (from kubelet → metrics-server → Metrics API)
  2. Compute desired replicas:
     desiredReplicas = ceil(currentReplicas × (currentMetric / targetMetric))
     e.g.: 3 pods at 80% CPU, target 50% → ceil(3 × 1.6) = 5 pods
  3. If desiredReplicas != currentReplicas:
     Update Deployment.spec.replicas
  4. Deployment controller sees the change → creates/deletes pods
```

The HPA has stabilization windows to prevent flapping (scale-up stabilization: 0s
default; scale-down stabilization: 300s default). A 5-minute stabilization window for
scale-down means the HPA will not reduce replicas until the metric has been below the
threshold for 5 minutes. This prevents the cluster from scaling down during a brief
traffic lull and immediately needing to scale back up.

**Vertical Pod Autoscaler (VPA)**: Automatically adjusts `resources.requests` for pods
based on observed usage. Cannot apply in-place (yet) — it evicts and reschedules pods
with updated requests. Useful for right-sizing initial resource requests.

**Cluster Autoscaler**: Watches for pods stuck Pending due to insufficient resources
and provisions new nodes (via cloud API). Also scales down underutilized nodes.
Works with HPA: HPA creates more pods → pods are Pending → Cluster Autoscaler adds
nodes → pods are scheduled → HPA scales down → nodes become empty → Cluster Autoscaler
removes nodes.

---

### Brainstorming: Part 13

**Q: What is the 5,000 node limit actually caused by, and how do large companies handle it?**

The 5,000-node limit is not a hard wall — it is the point at which the default
architecture starts showing significant degradation. The bottleneck is the combination
of etcd throughput (all node heartbeats + all object changes flowing through one Raft
leader), apiserver fan-out (each watch event delivered to all watchers), and scheduler
throughput (processing a large pending queue). Beyond 5,000 nodes, p99 API latency
tends to exceed K8s's SLOs (1 second for most operations).

Large companies handle this by running multiple clusters. Google's internal Kubernetes
(Borg's successor, which is effectively K8s at Google) runs as multiple clusters.
Uber, Airbnb, and Netflix all run many K8s clusters (tens to hundreds) rather than
one mega-cluster. The clusters are separated by region, environment, or team. The
management complexity of multiple clusters is handled by control planes for clusters
(like Cluster API, Fleet, ArgoCD). Some companies run "virtual clusters" (vcluster)
inside a large host cluster to provide isolation without the overhead of full cluster
provisioning.

**Q: How does the Cluster Autoscaler know which node group to add nodes to?**

The Cluster Autoscaler simulates scheduling for each Pending pod against all registered
node groups (node templates from different auto-scaling groups or instance types). It
picks the node group that would result in the lowest cost (or fewest nodes) while still
being able to schedule the Pending pods. If a pod requires a GPU (via node selector or
taint toleration), the Cluster Autoscaler knows to expand the GPU node group, not the
CPU node group.

The Cluster Autoscaler reads node group configurations from the cloud provider's auto-
scaling API (AWS Auto Scaling Groups, GCP Managed Instance Groups, Azure VMSS). It
does not create individual VMs — it tells the auto-scaling group to increase its desired
count, and the cloud provider handles VM provisioning. The new VM boots, the kubelet
starts, and the node registers with the cluster. This process typically takes 2-5 minutes,
which is why applications must handle cold start delays gracefully (requests will fail
until the new nodes are ready and pods are scheduled on them).

---

## Part 14: Key Concepts Synthesis

### The Central Mechanism in One Diagram

```
DESIRED STATE (etcd)
    │
    │ watch (ListWatch + local cache)
    ▼
CONTROLLER
(desired vs. actual)
    │
    │ if gap exists: take action
    │   - create/delete K8s objects
    │   - or call external systems (cloud API, container runtime)
    ▼
ACTUAL STATE CHANGES
    │
    │ eventually visible in etcd (via kubelet status updates,
    │ cloud provider callbacks, etc.)
    ▼
WATCH EVENT
    │
    │ controller reconciles again
    ▼
CONVERGED STATE (desired == actual)
```

This loop is how EVERYTHING in K8s works: the Deployment controller, the ReplicaSet
controller, the scheduler, the kubelet, the EndpointSlice controller, the cloud
controller manager. Every one of them is an instance of this pattern.

### Why K8s is Resilient

K8s achieves resilience not through complex coordination but through simple,
independent reconciliation loops. Each component only cares about its piece of state.
If a component crashes, it restarts and re-reconciles. If the network is flaky, it
reconnects and re-reconciles. If etcd is briefly unavailable, it waits and retries.
The system converges to desired state as long as the components eventually have
connectivity and the desired state is achievable on the available hardware.

This is fundamentally different from systems that use synchronous coordination
(like a traditional deployment system that calls each server sequentially and fails
if any call fails). K8s's decoupled, eventually-consistent (but strongly monotonically
converging) approach is why it is resilient to partial failures.

---

## Exercises

1. **Trace a pod deletion**: Pick a running pod in a Deployment. Run `kubectl delete pod`
   and trace through every component that acts: what does the apiserver do? What does the
   ReplicaSet controller do? What does the kubelet do? What happens to Service traffic
   during the gap before the replacement pod is ready? (Hint: consider preStop hooks and
   readiness probe propagation delay.)

2. **Debug the Pending pod**: Create a pod with a resource request of `cpu: 100`
   (100 full cores) — guaranteed to not be satisfiable. Observe it in Pending state.
   Run `kubectl describe pod` and read the scheduler's events. What does it tell you?
   Try with a taint: add a taint to a node, create a pod without toleration, observe the
   scheduler event.

3. **Probe behavior experiment**: Write a Deployment with a liveness probe configured with
   `initialDelaySeconds: 5, failureThreshold: 2, periodSeconds: 5` and an app that sleeps
   10 seconds before starting. Watch the pod enter CrashLoopBackOff. Then add a startup
   probe. Observe the difference.

4. **Watch/informer in practice**: Run `kubectl get pods --watch` in one terminal. In
   another, create and delete a pod. Observe the ADDED, MODIFIED (status changes), and
   DELETED events. This is exactly what controllers see via their informer.

5. **Service and iptables**: Create a Service with two backend pods. On the node running
   one of the pods, run `sudo iptables -t nat -L KUBE-SERVICES | grep <service-ClusterIP>`.
   Trace through the KUBE-SVC-XXX and KUBE-SEP-XXX chains. See the DNAT rules that
   implement load balancing.

6. **etcd inspection**: In a local kind cluster, exec into the etcd pod and run:
   `etcdctl get /registry/pods/default --prefix --keys-only`. See all pod keys in etcd.
   Observe the key structure. Try `etcdctl get /registry/pods/default/my-pod` and decode
   the protobuf value (use `kubectl get pod my-pod -o yaml` to compare the content).

7. **Admission webhook**: Write a simple validating admission webhook that rejects pods
   without a `team` label. Deploy it with a ValidatingWebhookConfiguration. Verify that
   pods without the label are rejected at apply time. Then delete the webhook server and
   observe what happens when the webhook is down (depends on failurePolicy).

8. **CRD + simple operator**: Define a CRD for `BestPracticeDeployment` that wraps a
   Deployment but auto-sets resource requests, readiness probes, and PodDisruptionBudget.
   Write a simple controller using the controller-runtime library. Apply a
   BestPracticeDeployment and watch the controller create the underlying Deployment,
   observe it in the logs.

---

## Homework

1. **Read the Kubernetes design docs**: The original design documents for K8s are public
   on GitHub (kubernetes/community/contributors/design-proposals). Read the "Architecture"
   design doc and the "Scheduler" design doc. These explain the rationale behind decisions
   that this chapter describes — knowing the "why" is more memorable than knowing the "what."

2. **Set up a local cluster and break it**: Use kind (Kubernetes in Docker) or minikube.
   Deliberately saturate resources to force a Pending pod. Create a pod with a broken
   liveness probe and watch CrashLoopBackOff. Simulate a node failure by stopping the
   kind worker container and watch what happens to pods on that node (delay: ~5 minutes).
   Recovery is faster when you have broken things intentionally.

3. **Read the etcd operations guide**: The etcd project's documentation has an operations
   guide covering cluster sizing, disk requirements, monitoring, and backup procedures.
   Read it in full. Every claim in Part 2 of this chapter has corresponding operational
   guidance there. The Prometheus metrics to monitor, the WAL fsync latency thresholds —
   these are documented with specific recommendations.

4. **Trace the scheduler source code**: The scheduler source is at
   `kubernetes/pkg/scheduler/framework/` in the kubernetes/kubernetes GitHub repo. Find
   the `NodeResourcesFit` plugin and read its `Filter` method. Find `LeastAllocated` and
   read its `Score` method. These are the actual algorithms — simpler than you expect,
   readable in an afternoon.

5. **Study a production operator**: Pick the Strimzi Kafka Operator or the Prometheus
   Operator. Read its documentation (how you declare a KafkaCluster or Prometheus object)
   and explore its source code (the main reconcile loop). Notice how it translates a
   single high-level custom resource into dozens of K8s objects (StatefulSets, Services,
   ConfigMaps, PodDisruptionBudgets) and handles operational events (rolling upgrades,
   failover). This is the operator pattern at its best.

---

## KEY TAKEAWAYS

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                        KUBERNETES INTERNALS: KEY TAKEAWAYS                  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  THE CENTRAL MECHANISM                                                       ║
║  ─────────────────────                                                       ║
║  Everything in K8s is a reconciliation loop: watch desired state in etcd,   ║
║  compare to actual state, take action to close the gap. This pattern is     ║
║  why K8s is resilient: components crash and restart safely.                  ║
║                                                                              ║
║  CONTROL PLANE COMPONENTS                                                    ║
║  ─────────────────────────                                                   ║
║  • kube-apiserver: the only door to etcd; enforces auth/admission           ║
║  • etcd: the only stateful component; uses Raft consensus; disk latency     ║
║    is the #1 control plane killer; watch API is the foundation of events     ║
║  • kube-scheduler: filter (eliminate ineligible nodes) → score (rank        ║
║    eligible nodes) → bind (write nodeName); no direct kubelet contact       ║
║  • kube-controller-manager: dozens of controllers in one binary; each is   ║
║    a reconcile loop using the watch/informer pattern                         ║
║  • cloud-controller-manager: cloud-specific controllers (LB, PV, nodes)    ║
║                                                                              ║
║  WATCH/INFORMER PATTERN                                                      ║
║  ──────────────────────                                                      ║
║  Controllers do ONE List at startup → build local cache → watch apiserver   ║
║  for ADDED/MODIFIED/DELETED events → update cache → call reconcile loop.    ║
║  Controllers read from cache (not etcd), write to apiserver. Idempotent.   ║
║                                                                              ║
║  SCHEDULER TWO PHASES                                                        ║
║  ─────────────────────                                                       ║
║  Filter: NodeResourcesFit, NodeAffinity, TaintToleration, PodAntiAffinity  ║
║  Score: LeastAllocated (spread), MostAllocated (bin-pack), ImageLocality   ║
║                                                                              ║
║  PROBES — THREE DISTINCT BEHAVIORS                                           ║
║  ──────────────────────────────────                                          ║
║  Liveness: fail → restart container → CrashLoopBackOff if keeps failing    ║
║  Readiness: fail → remove from Service endpoints (NOT restart)              ║
║  Startup: runs first; disables liveness+readiness until app starts          ║
║                                                                              ║
║  NETWORKING                                                                  ║
║  ──────────                                                                  ║
║  Every pod gets unique IP; flat network; no NAT between pods.               ║
║  CNI plugin implements the model (Calico=BGP, Cilium=eBPF, Flannel=VXLAN). ║
║  Services = stable VIPs implemented as iptables DNAT rules by kube-proxy.  ║
║  EndpointSlice controller tracks which pod IPs should receive traffic.      ║
║                                                                              ║
║  ETCD IS THE CRITICAL PATH                                                   ║
║  ──────────────────────────                                                  ║
║  Dedicated NVMe SSD for etcd; p99 fsync < 10ms; monitor etcd latency;     ║
║  size limit 2-8GB; backup every 30 minutes. Slow etcd = broken cluster.    ║
║                                                                              ║
║  EXTENSION POINTS                                                            ║
║  ────────────────                                                            ║
║  CRD = new object type (schema only, no logic)                              ║
║  Operator = CRD + controller (encodes operational knowledge)                ║
║  Mutating webhook = modify objects before persistence (runs first)          ║
║  Validating webhook = reject invalid objects (runs after mutating)          ║
║                                                                              ║
║  L5 vs L6 LINE                                                               ║
║  ────────────                                                                ║
║  L5: knows K8s objects and their behaviors                                  ║
║  L6: can trace kubectl apply through all 10 steps, name every mechanism,   ║
║       explain the watch/informer pattern, reason about failure modes,       ║
║       and design extensions (CRDs, operators, admission webhooks)           ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## One-Sentence Summary

> "Kubernetes works by having every component run a reconciliation loop — watching
> desired state in etcd (via the apiserver's watch/informer pattern), comparing it to
> actual state, and taking action to close the gap — with the scheduler doing two-phase
> filter+score to place pods on nodes, the kubelet on each node using CRI to run
> containers and CNI to wire the flat pod network, and extensions (CRDs, operators,
> admission webhooks) encoding complex operational logic as first-class Kubernetes
> controllers."

---

*Pairs with: Ch40 (Deployment Strategies — rolling updates, blue-green, canary),
Ch85 (Borg — the conceptual ancestor), Ch48 (Consensus — Raft and Paxos in depth),
Ch46 (Data Warehouse — for contrast: stateless compute vs. stateful storage).*
