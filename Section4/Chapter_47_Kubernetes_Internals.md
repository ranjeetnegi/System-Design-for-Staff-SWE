# Chapter 41d: Kubernetes Internals — How K8s Actually Works

> Everyone uses Kubernetes. Very few understand what happens between
> `kubectl apply -f deployment.yaml` and the pod running on a node.
> That gap — the control plane, the scheduler, the kubelet, the watch loop —
> is exactly what L6 infrastructure interviews probe.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

Kubernetes is the default compute platform at virtually every company. Deployment
strategies are covered in Ch40. This chapter covers K8s as a distributed system:
how the control plane works, how the scheduler makes decisions, how the reconciliation
loop achieves self-healing, and how networking is wired. Expected at L6 for
platform/infra roles; increasingly asked in backend L6 roles at Google, Meta, Stripe.

Kubernetes is also open-source Borg (Ch88) — understanding K8s informs your answer
to any cluster management question.

---

## Planned Content

### Part 1: The Architecture — Five Control Plane Components
- kube-apiserver: the single entry point; all state changes go through here;
  stateless, horizontally scalable; validates and persists to etcd
- etcd: distributed key-value store (Raft consensus); the source of truth for all
  cluster state; only component that stores data
- kube-scheduler: watches for unscheduled pods; selects a node; writes binding to apiserver
- kube-controller-manager: runs all controllers (Deployment, ReplicaSet, Node, etc.)
  in a single binary; each controller is a goroutine running a reconciliation loop
- cloud-controller-manager: cloud-provider-specific controllers (LoadBalancer, PersistentVolume)
- ASCII diagram: control plane components + data flow

### Part 2: The Watch/Informer Pattern — How Controllers Work
- Every K8s component uses the same pattern: watch the apiserver for changes, react
- Watch API: long-lived HTTP connection; apiserver streams events (ADDED, MODIFIED, DELETED)
- Informer: client-side cache of watched objects + event handlers; avoids hammering apiserver
- Reconciliation loop: for every event, compute desired state vs. actual state → take action
- Example: Deployment controller watches ReplicaSets; if actual replicas < desired → create pod
- This is the same as Borg's reconciliation loop — K8s inherited it directly

### Part 3: The Scheduler — How Pods Get Assigned to Nodes
- Two phases: Filtering (which nodes CAN run this pod?) + Scoring (which node SHOULD?)
- Filtering predicates:
  - NodeResourcesFit: does the node have enough CPU/RAM?
  - NodeAffinity: does the node match required labels?
  - TaintToleration: does the pod tolerate the node's taints?
  - PodAntiAffinity: would placing here violate anti-affinity rules?
- Scoring priorities:
  - LeastAllocated: prefer nodes with most free resources (spread)
  - MostAllocated: prefer fuller nodes (bin-pack, use fewer nodes)
  - ImageLocality: prefer nodes that already have the container image
- Output: the scheduler writes a Binding object to apiserver → kubelet picks it up

### Part 4: The Kubelet — The Node Agent
- Runs on every node; watches apiserver for pods assigned to this node
- Pod lifecycle: pull image → create containers (via CRI) → start → health check → report status
- CRI (Container Runtime Interface): kubelet doesn't care if it's containerd, CRI-O, or Docker
- Health checks: liveness probe (restart if unhealthy), readiness probe (remove from Service endpoints)
- Resource enforcement: uses Linux cgroups to enforce CPU/RAM limits
- Node status: reports node conditions (Ready, MemoryPressure, DiskPressure) to apiserver

### Part 5: Networking — How Pods Talk to Each Other
- Every pod gets its own IP (flat network model — no NAT between pods)
- CNI (Container Network Interface): plugin-based networking (Calico, Flannel, Cilium, Weave)
- How Calico works: each node gets a subnet; routes between nodes via BGP or VXLAN overlay
- Services: stable virtual IP (ClusterIP) that load-balances across pod IPs
- kube-proxy: implements Service routing via iptables or IPVS rules on each node
- DNS: CoreDNS resolves service names to ClusterIPs
- Ingress: external HTTP traffic → Ingress controller (nginx, Traefik) → Services → Pods

### Part 6: Storage — Persistent Volumes
- PersistentVolume (PV): a piece of storage provisioned by admin or dynamically
- PersistentVolumeClaim (PVC): a pod's request for storage (size, access mode, StorageClass)
- StorageClass: defines the provisioner (AWS EBS, GCP PD, Ceph, NFS)
- Dynamic provisioning: PVC created → StorageClass controller provisions PV automatically
- Access modes: ReadWriteOnce (one node), ReadOnlyMany (many nodes), ReadWriteMany (many nodes)
- StatefulSets: pods with stable network identity + per-pod PVCs (for databases, Kafka, etc.)

### Part 7: How `kubectl apply` Works End-to-End
```
kubectl apply -f deployment.yaml
  → apiserver validates + stores Deployment in etcd
  → Deployment controller (in controller-manager) sees new Deployment
  → creates ReplicaSet → creates 3 Pod objects in etcd (state: Pending)
  → scheduler sees 3 unscheduled Pods
  → for each pod: filter nodes → score nodes → write Binding to apiserver
  → Pods now have nodeName set (state: still Pending, now Scheduled)
  → kubelet on each assigned node sees its new Pod
  → pulls image → creates container → starts → reports Running
  → readiness probe passes → pod added to Service endpoint slice
  → traffic flows to new pods
```

### Part 8: Common Failure Modes and Debugging
- CrashLoopBackOff: container keeps crashing; check logs, liveness probe config
- Pending forever: no node passes scheduling filters; check resource requests, taints, affinity
- ImagePullBackOff: image not found or registry credentials missing
- OOMKilled: container exceeded memory limit; increase limit or fix memory leak
- etcd disk pressure: etcd is slow → entire control plane slows down; monitor etcd latency
- Node NotReady: kubelet not reporting; check node agent, disk, network

### Part 9: Interview Framework
- "How does K8s achieve self-healing?" → reconciliation loop (desired vs. actual state)
- "How does the scheduler work?" → filter → score → bind
- "How do pods communicate?" → flat pod network via CNI + Services via kube-proxy/iptables
- "What's in the control plane?" → apiserver + etcd + scheduler + controller-manager
- L5 vs. L6: L5 knows the K8s objects (Pod, Deployment, Service); L6 can trace
  `kubectl apply` through all five control plane components and explain the watch/informer
  pattern that makes the whole system work

---

## The One-Sentence Summary

> "Kubernetes works through a reconciliation loop: every controller watches etcd (via apiserver) for desired state, compares it to actual state, and takes action to close the gap — the scheduler filters + scores nodes for unscheduled pods, the kubelet on each node executes what the scheduler decided, and CNI wires the flat pod network that makes every pod reachable from every other pod."

---

*Full chapter: ~2,500 lines. Pairs with Ch88 (Borg — the conceptual predecessor) and Ch40 (Deployment Strategies).*
