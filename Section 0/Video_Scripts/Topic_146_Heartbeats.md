# Heartbeats: Detecting Failures

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

The climber radios base camp. "Base camp, I'm alive. Over." Thirty seconds pass. "Base camp, I'm alive. Over." Again. And again. Then—silence. One minute. Two. Base camp decides: something's wrong. Send rescue. That "I'm alive" signal? A heartbeat. In distributed systems, nodes do the same. Periodic signals. "I'm here. I'm working." Miss too many? Presumed dead. The system reacts. Failover. Restart. Re-election. Let me show you how heartbeats keep systems alive—and what happens when they stop.

---

## The Story

**Heartbeat** = periodic message from a node proving it's alive. Simple. Send "ping" or "I'm here" every N seconds. Recipients expect it. If nothing arrives for M seconds—the **timeout**—the node is presumed dead. Failure detected. Act accordingly.

**Timeout tuning:** Too short? False positives. Node was slow. Network hiccup. You declare it dead when it's fine. Unnecessary failover. Churn. Too long? Slow failure detection. Real failure. You wait. Service degraded. Users suffer. The sweet spot: longer than normal network delay. Shorter than user tolerance for outage. Typical: 5–30 seconds for many systems. Milliseconds for Raft. Depends on context.

**Failure detector:** Can be binary (alive/dead) or probabilistic. "Node A: 80% confidence dead." Some systems use suspicion levels. Accidental disconnect vs. crash. Different responses. Heartbeats are the input. The detector is the logic.

**Asymmetric vs symmetric:** In leader-follower, the leader might heartbeat followers. Or followers might heartbeat the leader. Or both. Raft: leader heartbeats followers. Kafka: brokers heartbeat the controller. Load balancers: active check (LB pings server) or passive (server reports in). Design choice. Active = LB initiates. Passive = server initiates. Both work. Different trade-offs.

---

## Another Way to See It

Think of a friend who texts you daily. Every morning: "Good morning!" One day: nothing. Next day: nothing. You call. No answer. You worry. Maybe they're busy. Maybe something's wrong. After a week, you assume the worst. Heartbeats are like that. Regular check-ins. Absence = concern. After N missing check-ins = assume failure. The interval and threshold define sensitivity. Too sensitive: false alarm. Not sensitive enough: real problem missed. Tune for your world.

---

## Connecting to Software

**Applications:** Leader checks followers. "Are you still replicating?" Followers check leader. "Are you still there?" Load balancer checks servers. "Can I send traffic?" Cluster membership. "Who's in the cluster?" Health checks. Liveness. Readiness. All use heartbeats or heartbeat-like logic.

**Implementation:** TCP keepalive. Application-level ping. HTTP health endpoints. gRPC health checks. Kubernetes liveness probes. Same idea. Different transport. Send periodically. Expect response. Timeout = fail.

**Gossip-based:** Not point-to-point. Nodes gossip about each other. "I haven't heard from A in 3 rounds." Failure info spreads. Amazon's DynamoDB uses this. No single node checks everyone. Distributed failure detection. Scales better.

---

## Let's Walk Through the Diagram

```
    HEARTBEATS: DETECTING FAILURE

    Normal: Leader sends heartbeat every 1 sec
    ┌────────┐  heartbeat   ┌────────┐
    │ Leader │ ───────────► │Follower│
    │        │ ◄── ACK ──── │        │
    └────────┘              └────────┘
    Follower: "Leader alive. Reset timeout."

    Leader crashes: No heartbeats
    ┌────────┐              ┌────────┐
    │ Leader │   X          │Follower│
    └────────┘              │timeout!│
                            │ 3 sec  │
                            │"Leader │
                            │ dead"  │
                            └────────┘
    Follower: Start election. Find new leader.
```

The diagram shows: heartbeats keep the bond. No heartbeats = timeout = assume dead = act. Simple loop. Universal pattern.

---

## Real-World Examples (2-3)

**Example 1: Raft.** Leader sends AppendEntries (or empty entries) as heartbeats. Every 50–150ms typically. Followers reset election timer. No heartbeat = timeout = become candidate. Heartbeat is the core of Raft's liveness.

**Example 2: Kubernetes.** Liveness probe. Kubelet pings the pod. HTTP GET or TCP connect. No response for N failures = restart pod. Readiness probe: similar. But "can accept traffic?" not "is it alive?" Both use heartbeat logic.

**Example 3: Load balancers.** Health check every 5 seconds. Server fails check 3 times = remove from pool. Stop sending traffic. Heartbeats determine routing. Unhealthy = no traffic. Simple. Effective.

**Example 4: Database replication.** Primary pings replicas. Replicas ping primary. Bi-directional. If primary doesn't hear from replica, it might mark it lagging. If replica doesn't hear from primary, it might trigger failover. Heartbeats are the lifeline. Without them, the system doesn't know who's alive.

---

## Let's Think Together

Network is congested. Heartbeats delayed 3 seconds. Timeout is 5 seconds. Is the node dead or just slow?

You can't tell. A heartbeat delayed 3 seconds might arrive at 4 seconds. Or 6. If it arrives before timeout: node seems alive. If it arrives after: you've already declared it dead. False positive. With 5-second timeout and 3-second delays, you're in the danger zone. Solution: make timeout >> expected delay. If network can delay 3 seconds, use 10–15 second timeout. Or use multiple missed heartbeats. 3 missed = dead. Reduces false positives. Trade-off: slower failure detection. Know your network. Measure. Tune.

---

## What Could Go Wrong? (Mini Disaster Story)

A cluster used 2-second heartbeat timeout. "Fast failover." Their network had occasional 5-second delays. Flaky switch. Random congestion. Heartbeats arrived late. Nodes declared each other dead. Cascading failovers. New leader. Old leader came back. Split-brain. Chaos. They increased timeout to 15 seconds. Failover slower. But no more false positives. Lesson: timeout must be larger than worst-case network delay in your environment. Test under load. Simulate failures. Get the numbers right.

---

## Surprising Truth / Fun Fact

Amazon's DynamoDB uses gossip-based heartbeats. Nodes don't ping a central checker. They gossip. "I saw A 10 seconds ago." "I haven't seen B in 30 seconds." Failure information spreads like a rumor. Eventually everyone knows. No single point of failure for failure detection. Scales to huge clusters. Same idea as epidemic protocols. Failure detection, epidemic style. Clever.

---

## Quick Recap (5 bullets)

- **Heartbeat** = periodic "I'm alive" signal. Miss N = presumed dead.
- **Timeout** = how long to wait. Too short = false positives. Too long = slow detection.
- **Uses:** Leader-follower liveness, load balancer health, cluster membership.
- **Implementation:** TCP keepalive, HTTP health, gRPC, custom ping. Same pattern.
- **Tune for network:** Timeout >> expected delay. Measure. Avoid false failover.

---

## One-Liner to Remember

**Heartbeats: Climber radios base camp. "I'm alive." Silence for 2 minutes? Send rescue. Same in systems. No heartbeat = assume dead.**

---

## Next Video

Next: **Gossip Protocol.** A rumor in school. One tells two. Two tell four. Everyone knows. No broadcast. No leader. Just whispers. Epidemic spread of information. See you there.
