# Failover and Failback: Basics

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Picture a plane. Pilot and co-pilot. The pilot passes out. Primary fails. The co-pilot takes over instantly. Failover. The plane keeps flying. Passengers barely notice. Later, the pilot recovers. The co-pilot hands back control. Failback. Smooth. Practiced. No chaos. That's exactly what we do in systems. Failover = switching to backup when primary fails. Failback = switching back to primary when it recovers. Let's see how it works.

---

## The Story

Failover is automatic or manual recovery. When the primary system fails—crash, network partition, overload—traffic switches to a backup. Users might see a brief hiccup. Or nothing. Depends on how well you've designed it.

Failback is the return journey. Primary is healthy again. Do you switch traffic back? Sometimes yes—primary might have better hardware, lower latency, or you prefer it as the "main" node. Sometimes you don't bother immediately. The backup is now serving. No rush.

Types of failover matter. **Automatic**: the system detects failure (heartbeat timeout, health check fail) and switches itself. Fast. No human in the loop. **Manual**: a human decides. "Primary is down. Should we fail over?" Slower, but more control. Useful when failure is ambiguous—maybe it's a network glitch, not a real crash.

**Cold, warm, hot** describe backup readiness. **Cold**: backup is off or idle. To fail over, you start it, load data, then route traffic. Minutes to hours. **Warm**: backup is running, maybe syncing data, but not serving traffic. Failover in seconds to minutes. **Hot**: backup is fully up, replicating in real time, ready to serve instantly. Failover in seconds or less. Cost goes up as you move from cold to hot.

**Testing failover:** Practice. Run chaos drills. Kill the primary. Watch failover. Measure recovery time. Fix gaps. Many outages happen because failover was never tested. "We have hot standby" means nothing until you've failed over under load. Quarterly drills. Document the runbook. Know your RTO (recovery time objective) and RPO (recovery point objective). Failover speed and data loss tolerance. Design to meet them.

---

## Another Way to See It

Think of a spare tire. Cold = tire is in the trunk, not even mounted. Puncture? Jack up the car, swap tires. Slow. Warm = tire is mounted on the rim, in the trunk. Faster. Hot = tire is on a second axle, already rolling. Instant swap. You pay for that readiness—extra hardware, sync, complexity.

Or a backup generator. Cold: stored in a shed. Power out? Unlock, connect, start. Warm: plugged in, fueled, tested monthly. Power out? Flip switch. Hot: always running in parallel, ready to take load. Hospital style. No gap.

---

## Connecting to Software

In software, failover shows up everywhere. Database replication: primary fails, promote a replica. DNS failover: primary IP unreachable, switch to backup IP. Load balancer: mark unhealthy node as down, traffic goes to others. Kubernetes: pod crashes, new one starts. The pattern is the same. Detect failure. Redirect traffic. Recover.

Failback needs care. Don't flip traffic back the moment primary blinks "I'm up." It might be unstable. Use a "drain" period: route a little traffic, watch. Gradual. Or manual approval. Avoid flip-flopping—primary up, fail back, primary down again, fail over. That's thrashing. Give it time.

---

## Let's Walk Through the Diagram

```
    NORMAL STATE                         FAILOVER (Primary Down)

    Client ──► [Primary] ✓                   Client ──► [Primary] ✗
                    │                                (timeout, health fail)
                    │                                │
                    ▼                                ▼
              [Replica] (standby)              [Replica] promoted
                                                    │
    Client ──► [Primary] ✓                   Client ──► [Replica] ✓
                                                    (now serving)
```

Normal: primary serves, replica syncs. Failover: primary dies, replica promoted. Clients now hit replica.

```
    FAILBACK (Primary Recovers)

    Client ──► [Replica] ✓
                    │
              [Primary] back online, catching up
                    │
              Drain traffic back gradually
                    │
    Client ──► [Primary] ✓  (replica demoted)
```

---

## Real-World Examples (2-3)

**Example 1: AWS RDS Multi-AZ.** Primary in one availability zone. Standby replica in another. Automatic failover. If primary fails, RDS promotes the standby. Failover typically 60–120 seconds. You don't touch anything. Failback: when you restore the old primary, it becomes a new standby. Manual failback is possible but less common.

**Example 2: Kafka.** Brokers form a cluster. If the controller (leader) dies, another broker takes over. Automatic. Producers and consumers reconnect. No manual intervention. The "primary" role moves. That's failover. No traditional failback—the new primary stays primary.

**Example 3: Netflix.** Multiple regions. If one region has issues, traffic routes away. DNS or load balancer based. Failover to another region. When the original recovers, they can fail back—often gradually, watching metrics.

---

## Let's Think Together

**Why might you choose manual failover over automatic?**

When failures are ambiguous. Split brain: both nodes think they're primary. Or a network partition: primary is fine, but the monitoring can't reach it. Automatic failover might promote a replica while primary is still running. Two primaries. Data divergence. Disaster. Manual lets a human verify: "Is it really dead?" before switching.

**When is cold backup acceptable?**

Disaster recovery for non-critical systems. Backup DB for analytics. Restore in hours. Fine. For user-facing, transaction-heavy systems? Cold is too slow. You need warm or hot. Pay for readiness when uptime matters.

---

## What Could Go Wrong? (Mini Disaster Story)

A company runs a hot standby. Automatic failover. Primary has a brief network blip. Heartbeat times out. System fails over to replica. Replica promotes. Now primary comes back. Both think they're primary. Split brain. Writes go to both. Data corrupts. Replication breaks. They discover it hours later. Restore from backup. Lost transactions. Lesson: automatic failover needs robust failure detection. Quorum. Witness. Fencing. Don't promote too eagerly.

---

## Surprising Truth / Fun Fact

Some systems never fail back. The "backup" becomes the new primary permanently. The old primary, when fixed, becomes the new backup. Simpler. No flip-flop. You're always in a consistent state. The concept of "primary" and "backup" is fluid—whoever is serving is primary.

---

## Quick Recap (5 bullets)

- **Failover** = switching to backup when primary fails; **failback** = switching back when primary recovers.
- **Automatic** = system switches itself; **manual** = human decides. Use manual when failure is ambiguous.
- **Cold** = backup starts from scratch (slow); **warm** = running but not serving; **hot** = ready instantly.
- Detect failure via heartbeats, health checks; promote replica or route traffic away.
- Failback carefully—avoid thrashing. Drain traffic gradually. Verify stability.

---

## One-Liner to Remember

Failover is "backup takes over." Failback is "primary takes over again." Cold, warm, hot tells you how ready the backup is—and how fast you can switch.

---

## Next Video

Next up: **Monolith**—when one big application is perfect. The Swiss Army knife of software. Don't split it prematurely.
