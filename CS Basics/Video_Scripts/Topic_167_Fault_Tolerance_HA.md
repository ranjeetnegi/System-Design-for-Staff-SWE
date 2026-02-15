# Fault Tolerance vs High Availability

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A car with a spare tire: high availability. Tire pops, you pull over, change it, drive on. Short downtime. Maybe 15 minutes. A plane with four engines: fault tolerant. One engine fails. The other three keep flying. No downtime. No stopping. Passengers don't even notice. HA means quick recovery. Fault tolerance means no impact. Different strategies. Different costs.

---

## The Story

**High Availability (HA):** The system recovers quickly from failure. Brief disruption is acceptable. You have redundancy—backup servers, standby databases. When the primary fails, failover kicks in. Maybe 30 seconds. Maybe a few minutes. Users might see an error. A refresh. Then it works. The goal: minimize downtime. Not eliminate it.

**Fault Tolerance (FT):** The system continues operating *without interruption* despite failure. No downtime. No errors. No "please wait." The failure happens. Users don't notice. Redundancy is active. Not standby. Multiple components working in parallel. One fails. Others absorb the load. Seamless.

HA is cheaper. One primary. One standby. Standby does nothing until failover. Fault tolerance is more expensive. Multiple active components. All working. All the time. Double or more the cost. But zero interruption.

**The spectrum:** It's not binary. HA can be "5-minute failover" or "30-second failover." FT can be "survive one failure" or "survive two simultaneous failures." N+1 vs. N+2. Cost scales. Choose based on what downtime costs you. A few minutes of "try again" might be fine. Or it might mean millions lost. Know your number.

---

## Another Way to See It

Think of a hospital. HA: one surgeon. Surgeon gets sick. Another surgeon is on call. 30-minute delay. Surgeries resume. Fault tolerant: two surgeons in the OR. One faints. The other continues. Surgery never stops. Different designs. Different costs.

Or a bridge with a detour. HA: main bridge closes for repair. Detour adds 20 minutes. Traffic flows. Fault tolerant: two parallel bridges. One closed. All traffic uses the other. No delay. No detour. Just more infrastructure.

---

## Connecting to Software

**HA example:** Database with primary and replica. Primary handles all writes. Replica is standby. Primary fails. Replica promoted. 30-second switchover. Applications reconnect. Brief outage. Brief errors. Then normal. HA achieved.

**FT example:** RAID storage. Multiple disks. One fails. Others continue. No data loss. No pause. Applications keep running. Or: load-balanced stateless servers. One dies. Load balancer stops sending traffic. Other servers handle everything. Users might not notice the failed server. FT at the app layer.

**When HA:** Acceptable to have brief downtime. Budget conscious. Most web apps, internal tools. **When FT:** Zero-downtime requirement. Banking transactions, critical infrastructure. Pay the extra cost.

**Testing matters.** HA: you must test failover. Regularly. Chaos engineering. Kill the primary. Does standby take over? How long? What breaks? FT: test failure absorption. Kill a node. Does traffic shift? Any errors? Many teams have standby that's never been tested. First real failover? Disaster. Test. Practice. Know your recovery.

---

## Let's Walk Through the Diagram

```
    HIGH AVAILABILITY                    FAULT TOLERANCE

    [Primary] ── handles all traffic     [Server A] ──┐
                                                        ├── Load balanced
    [Standby]  ── idle, ready           [Server B] ──┤    All active
         │                                          │
         │  Primary fails                            │  One fails
         ▼                                          ▼
    Failover (30 sec)                        Others absorb. No stop.
    Brief disruption ✓                      Zero disruption ✓
```

Left: standby waits. Failover takes time. Right: all active. Failure absorbed. No stop.

---

## Real-World Examples (2-3)

**Example 1: Netflix.** HA for most services. A recommendation engine down? Show cached. Brief degradation. User refreshes. Fine. For video delivery: more fault tolerant. CDN, multiple regions. One node fails. Others serve. Seamless playback.

**Example 2: Banking core.** Often fault tolerant for critical paths. Multiple active database nodes. Transaction processing continues if one fails. Downtime = lost money. Reputation. Regulatory issues. Worth the cost.

**Example 3: Slack.** HA for most features. Database failover. Brief "reconnecting" sometimes. Acceptable. For real-time messaging layer: closer to fault tolerant. Multiple nodes. Failure absorbed. Messages keep flowing.

---

## Let's Think Together

**Banking system: HA or fault tolerant? Social media feed: HA or fault tolerant?**

Banking: ideally fault tolerant for core transaction processing. Money can't wait. But many banks still use HA—brief failover acceptable. Depends on implementation. Social media feed: HA is fine. A few seconds of "something went wrong" is acceptable. Users refresh. Not critical. The key: what's the cost of 30 seconds of downtime? Money? Lives? Or just annoyance? That decides.

---

## What Could Go Wrong? (Mini Disaster Story)

A company built their system for HA. Primary database. Standby. Tested failover. 45 seconds. Acceptable. One day: primary failed. But the standby had a replication lag. 2 minutes of data not yet replicated. Failover happened. 2 minutes of transactions lost. Orders. Payments. Chaos. Lesson: HA is not just "we have a standby." It's "we have a standby *and* we've thought through data loss, replication lag, split-brain." HA done wrong is worse than no HA.

---

## Surprising Truth / Fun Fact

Airplanes are fault tolerant by regulation. Commercial jets need to fly with one engine out. Some with two engines out (ETOPS). The redundancy is mandatory. Software has no such regulation. We choose. And we often under-invest in redundancy until the first big outage. Then we learn. The hard way.

---

## Quick Recap (5 bullets)

- **High Availability** = quick recovery. Brief disruption acceptable. Redundancy + failover.
- **Fault Tolerance** = no interruption. Failure absorbed. No user impact.
- **HA** = standby, failover. Cheaper. **FT** = active redundancy. More expensive.
- **HA example:** DB failover (30-second switch). **FT example:** RAID, load-balanced servers.
- **Choose based on** cost of downtime. Critical systems: FT. Most apps: HA.

---

## One-Liner to Remember

**HA: we recover fast. FT: we never stop. Different promises. Different prices.**

---

## Next Video

Next: **Partial Failure**—why things fail in pieces, not all at once. The reality of distributed systems. Stay tuned.
