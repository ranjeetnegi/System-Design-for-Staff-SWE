# When Kafka Is Overkill: Pick the Right Tool

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You need to send a package across the street. Two options. Option A: hire a moving truck, two drivers, GPS tracking, and insurance. Option B: walk across the street and hand it over. Sometimes we choose the truck. For a package that fits in your hand. Kafka is the moving truck. It's powerful. It's durable. It handles millions of events per second. But if your problem is "send 10 notifications per minute," Kafka might be overkill. A simple queue. A direct API call. Even a database poll. Might be enough. Let's talk about when Kafka is the right tool—and when it's not.

---

## The Story

Kafka shines when you need: high throughput (100K+ events per second), event replay (read from any point in time), multiple consumer groups (many services reading the same stream), event sourcing (full history of changes), stream processing (Kafka Streams, Flink), or a durable event log (audit, compliance). If you have those needs, Kafka earns its complexity.

But Kafka is overkill when: throughput is low (under 100 events per second), you don't need replay (process once, forget), you have one consumer (simple queue pattern), the team has no Kafka expertise (operational burden is real), or the problem is simple (fanout, notification, request-response). In those cases, simpler tools win. Faster to build. Easier to run. Lower cost.

Think of it like tools in a toolbox. A hammer for nails. A screwdriver for screws. You don't use a power drill for every screw. Kafka is the power drill. Use it when you need it. Not when a screwdriver works.

---

## Another Way to See It

A bicycle vs a sports car. For a trip to the grocery store a mile away, the bicycle is better. Cheap. Simple. No parking hassle. The sports car is overkill. But for a 500-mile road trip, the car wins. Kafka is the sports car. Understand the distance you're traveling. Match the tool to the journey.

---

## Connecting to Software

**Simpler alternatives:** SQS (managed queue, zero ops, pay per message), Redis lists (simple queue, in-memory, fast), database polling (good enough for small scale—workers poll a jobs table), direct HTTP calls (synchronous, simple, no queue at all). Each has a place.

**Kafka shines when:** high throughput, replay, multi-consumer, event sourcing, stream processing, durable log. If you tick multiple boxes, Kafka earns its place.

**The cost of Kafka:** operational complexity (brokers, ZooKeeper/KRaft, monitoring), expertise (partitions, consumer groups, retention, compaction), and often over-provisioning (you might run a 3-broker cluster for 10 messages per second). That's waste.

**The hidden costs nobody talks about:** (1) Disk management — Kafka stores everything to disk. Even a quiet topic uses disk that grows over time. (2) Monitoring — you need to monitor consumer lag, partition skew, broker health, ISR (in-sync replicas), under-replicated partitions. That's a DASHBOARD of metrics before you've processed a single business event. (3) Upgrades — Kafka version upgrades require rolling restarts. In a small team, that's a Saturday project. (4) Schema management — once you have Kafka, you need a Schema Registry to manage event formats. Another service to run. Another thing to learn.

**Decision framework:** Ask yourself three questions: (A) Do I need replay? (B) Do I have multiple consumers for the same stream? (C) Is my throughput above 1,000 events/sec? If all three are "no," skip Kafka. Use SQS, Redis, or even a simple database table with a "processed" column. You'll ship faster, sleep better, and your on-call rotation will thank you.

---

## Let's Walk Through the Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│              KAFKA vs SIMPLER: WHEN WHICH?                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   Low throughput, 1 consumer, no replay:                                 │
│   ┌─────────┐                    ┌─────────┐                            │
│   │  App    │ ─── HTTP/SQS ────► │ Consumer│   Simple. Done.             │
│   └─────────┘                    └─────────┘                            │
│                                                                          │
│   High throughput, replay, multi-consumer:                               │
│   ┌─────────┐     ┌─────────┐    ┌─────────┐  ┌─────────┐                │
│   │Producer │ ──► │ Kafka   │ ──►│Consumer │  │Consumer│  Kafka earns it│
│   │         │     │ (durable│    │ Group A │  │ Group B│                │
│   └─────────┘     │  log)   │    └─────────┘  └─────────┘                │
│                   └─────────┘         │              │                    │
│                       ▲               └──────────────┘                   │
│                       │  Replay from any offset                          │
└─────────────────────────────────────────────────────────────────────────┘
```

Left: simple path. Right: Kafka path. Choose based on requirements, not resume buzzwords.

---

## Real-World Examples

**Startup, 1000 users, 10 events/sec:** SQS or Redis. Maybe even a cron job that processes a "pending_notifications" table. Kafka adds no value. Adds ops. Adds cost. Say no.

**Netflix, billions of events:** Kafka. Replay. Multiple teams. Stream processing. Event sourcing. Kafka is essential. The complexity pays off.

**Mid-size SaaS, 100K events/day:** Maybe SQS. Or Kafka if you're planning for 10x and have team capacity. Trade-off. Don't default to Kafka "because it's what the big boys use."

---

## Let's Think Together

**"Startup with 3 engineers, 1000 users, 10 events/sec. CTO wants Kafka. What do you say?"**

Answer: "Let's use SQS first. Or Redis. We can process 10 events per second with a single worker. Kafka adds brokers, partitions, consumer groups, monitoring. We don't have the ops bandwidth. If we hit 10,000 events per second, or need replay, or have 5 teams consuming the same stream—we'll migrate. Premature Kafka is technical debt. Start simple. Add complexity when we need it." The CTO might still say Kafka. But you've made the case. Data beats opinions. Show the numbers: 10/sec vs Kafka's sweet spot at 100K+/sec.

---

## What Could Go Wrong? (Mini Disaster Story)

A team adopted Kafka for a "notification service." Send an email when a user signs up. Ten signups per minute. They ran a 3-broker cluster. Spent weeks tuning partitions, consumer groups, retention. One engineer left. No one knew how to debug lag. Alerts fired. They couldn't interpret them. They migrated to SQS. Ten lines of code. Zero brokers. Problem gone. The lesson: match infrastructure to team size and problem size. Kafka is a commitment. Make it when the problem demands it.

---

## Surprising Truth / Fun Fact

Kafka was built at LinkedIn for activity streams and metrics. They had a real problem: billions of events, multiple consumers, replay needs. It wasn't built for "send a welcome email." The origin story tells you the use case. If your use case is "send a welcome email," you're not in Kafka's origin story. That's okay. Use the right tool.

---

## Quick Recap (5 bullets)

- **Kafka overkill when:** low throughput (<100/sec), no replay, single consumer, simple queue, no team expertise.
- **Simpler options:** SQS, Redis, database polling, direct HTTP—each fits smaller problems.
- **Kafka shines when:** high throughput, replay, multi-consumer, event sourcing, stream processing.
- **Cost of Kafka:** ops complexity, expertise, over-provisioning for small workloads.
- **Rule:** start simple; add Kafka when the problem demands it, not when the resume demands it.

---

## One-Liner to Remember

*"Kafka is for when you need a freight train. If you're moving a suitcase, use a trolley."*

---

## Next Video

Up next: **Pub/Sub vs Kafka: When Which?**—the radio broadcast that disappears versus the newspaper archive that lasts. We'll compare two different models of messaging and when to use each.
