# Chaos Engineering: Why and How (Intro)

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Fire drills. You don't wait for a real fire to test your evacuation plan. You simulate it. People practice. You find weaknesses: "Exit 3 was locked!" "Floor 7 didn't hear the alarm!" Fix those before a real emergency. Chaos engineering is the same idea. You intentionally break things in production—in a controlled way—to find weaknesses before they cause real outages. Scary? Maybe. Necessary? Absolutely.

## The Story

You *think* your system handles failures. But do you *know*? When was the last time a database node failed? Did failover work? How long did it take? Did anything else break? Most teams never test that. They hope. They document runbooks. They never run the runbook under pressure. Then 2 AM Saturday, something fails. Panic. Chaos.

Chaos engineering says: **don't hope. Test.** Run a fire drill. Kill a server. Add latency. Block the network. See what happens. In a controlled way. During business hours. With people watching. Learn. Fix. Repeat.

## Another Way to See It

Like a vaccine. You inject a small dose of the virus to build immunity. Chaos engineering injects a small dose of failure to build resilience. Controlled exposure. Prepare the system before real disaster strikes. Or like a flight simulator. Pilots train for engine failure in a simulator. They don't wait for a real engine to fail. When it happens for real, they've seen it before. Muscle memory. Calm response. Chaos engineering is the simulator for your distributed system. Train before the real failure. Build the muscle memory. When production breaks at 2 AM, you'll have run that scenario before. You'll know what to do.

## Connecting to Software

How do you do it?

1. **Define steady state**: What does "normal" look like? Latency p99, error rate, throughput. Metrics.
2. **Hypothesize**: "If database primary fails, we expect: read replica promotes in 30 seconds, clients reconnect, no data loss."
3. **Inject failure**: Kill the primary. Or: add 500ms latency to one service. Or: drop 10% of packets to one region.
4. **Observe**: Did the system behave as expected? Did latency spike? Did errors spike? Did we lose data?
5. **Fix**: Found a weakness? Fix it. Improve runbooks. Add alerts. Harden the system.
6. **Repeat**: New failure mode. Test again.

Start small. One instance. One service. Expand over time. And scope it: run during business hours when the team is online. Don't run Chaos Monkey at 3 AM on a Friday unless you have 24/7 coverage. The goal is learning, not suffering. Start with a "game day" — a planned chaos exercise with the whole team watching. Then move to automated, continuous chaos. But only when you're ready.

## Let's Walk Through the Diagram

```
  STEADY STATE:           AFTER CHAOS:

  [LB] → [API] [API] [API]     [LB] → [API] [API] [X]  (killed one)
       ↓                              ↓
  [DB Primary]                       [DB Primary] → failover →
  [DB Replica]                       [DB Replica] (now primary)

  Observe: Did failover work? How long? Any errors?
```

## Real-World Examples (2-3)

- **Netflix Chaos Monkey**: Randomly kills production instances. If the system recovers automatically, it's resilient. If not, you've found a bug. Better to find it Tuesday 2 PM than Saturday 2 AM.
- **AWS Fault Injection Simulator**: Inject failures into EC2, ECS, RDS. Test your architecture.
- **Gremlin, Litmus (Kubernetes)**: Commercial and open-source chaos tools. Kill pods, simulate network partitions, fill disks.
- **Google**: Disks fail. Servers fail. They test it constantly. Chaos is part of their culture. They have entire teams that run fault injection. "Kill 1% of nodes in this cluster. What happens?" The answer shapes the architecture. If the system doesn't recover, it gets redesigned.
- **Amazon**: Similar story. They run GameDays—planned chaos exercises. "What if this AZ goes down?" They actually take it down (in a controlled way) and watch. Runbooks get tested. Gaps get fixed. Real failure is the teacher. Chaos engineering is the rehearsal.

## Let's Think Together

**You kill one of five API servers at 2 PM. The load balancer should route around it. But latency spikes 3x. Why?**

Maybe: the load balancer takes time to detect the failure and remove the instance from the pool. During that window, requests to the dead server timeout. Maybe: the remaining four servers were already near capacity. Lose one, the others are overloaded. Maybe: the dead server had in-memory state. Sessions broke. Clients retried. Double load. Chaos reveals the real behavior. The hypothesis was "LB routes around." Reality was different. Now you know what to fix.

## What Could Go Wrong? (Mini Disaster Story)

You run Chaos Monkey. It kills a critical Redis instance. Your cache is gone. Database gets hammered. Site goes down for an hour. You didn't test Redis failure before. You didn't know the cache was a single point of failure. Oops. The lesson: start with non-critical components. Kill one API server of ten. Not the single database. Not the primary cache. Build confidence. Learn what fails. Fix it. Then expand the blast radius slowly. Chaos engineering done wrong is just chaos. Done right, it's a controlled experiment that makes your system stronger. The goal is not to cause outages. The goal is to find weaknesses when you're ready to fix them.

## Surprising Truth / Fun Fact

Netflix built Chaos Monkey in 2010. They run it in production. Every day. Random instance kills. It forced them to build resilience. No single point of failure. Every service expects to die. Auto-scaling. Stateless. Failover. The result: when AWS us-east-1 had a major outage in 2011, Netflix stayed up. Other companies went down. Netflix designed for failure. Chaos engineering made it real. They didn't hope. They tested. You should too. Start small. Kill one non-critical instance. Learn. Expand. Build a culture where "we break things on purpose" is normal. Your users will never notice the chaos. They'll just enjoy the uptime.

---

## Quick Recap (5 bullets)

- Chaos engineering = intentionally injecting failure to test and improve resilience
- Process: define steady state, hypothesize, inject, observe, fix, repeat—scientific method for failure
- Start small: non-critical components, business hours, with monitoring
- Tools: Chaos Monkey, Gremlin, Litmus, AWS Fault Injection Simulator
- Goal: find weaknesses before real outages; build immunity through controlled exposure; rehearsal beats panic

## One-Liner to Remember

*Break it on purpose, so it doesn't break when you don't.*

Start with game days. Planned chaos. Learn. Fix. Then automate. Chaos engineering builds confidence through practice. Hope is not a strategy.

---

## Next Video

That's it for this batch. More system design deep dives coming. Subscribe so you don't miss them. See you in the next one.
