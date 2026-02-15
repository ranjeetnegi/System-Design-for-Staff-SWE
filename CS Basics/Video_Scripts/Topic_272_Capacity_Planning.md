# Capacity Planning: How to Do It

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You're hosting a wedding. 200 guests. You need: tables (20), chairs (200), plates (200), waiters (10), parking spots (100). What if 300 show up? Chaos. Not enough seats. Not enough food. Not enough parking. Fights in the lot. Capacity planning is the same idea. Estimate future demand. Ensure your system has enough resources BEFORE you need them. Don't wait until the wedding to count chairs. Count them now. Add more if needed. Plan ahead.

---

## The Story

Traffic grows. Users multiply. New features launch. Holiday sales. Viral moments. Your system has limits. CPU. Memory. Database connections. Network bandwidth. Disk I/O. Hit those limits unprepared, and everything falls over. Capacity planning is the practice of understanding current usage, projecting growth, and acting before you hit the wall. It's boring when done right—no drama. It's terrifying when ignored—midnight pages, rushed scaling, customer impact.

Think of it like a water tank. You're filling it. The tap is open. You need to know: how fast is it filling? When will it overflow? Do you need a bigger tank? Or a second tank? Capacity planning answers those questions. Measure the fill rate. Project. Plan the upgrade. Don't wait for the overflow.

---

## Another Way to See It

A highway. Rush hour. Traffic builds. Lanes fill. Speed drops. Congestion. Capacity planning is adding lanes—or building alternate routes—BEFORE rush hour becomes a parking lot. You study traffic patterns. You project growth. You build before the crisis. Reactive scaling is adding lanes while cars are stuck. Proactive capacity planning is adding them during the off-season. Different experience. Different outcome.

---

## Connecting to Software

**Steps:** (1) Measure current usage. CPU utilization. Memory. Disk I/O. Network. Database connections. Queue depth. Per server. Per service. Aggregate. (2) Project growth. Historical: "We've grown 10% per month for 6 months." Events: "Black Friday typically 3x traffic." Roadmap: "We're launching in Europe next quarter." Combine. (3) Identify when you hit limits. "At 10% monthly growth, we hit 100% CPU in 4 months." "Database connections max out in 2 months." (4) Plan actions. Add servers. Shard the database. Optimize queries. Add caching. Do it BEFORE you hit the limit. Buffer: don't scale at 100%. Scale at 70–80%. Leave room for spikes. Traffic is lumpy. Plan for peaks.

**Key metrics:** CPU utilization (per core, per server). Memory usage (and swap). Disk I/O (reads, writes, IOPS). Network bandwidth (in/out). Database: connections, query latency, replication lag. Queues: depth, consumer lag. Each has a limit. Know your limits. Know your usage. Know the gap.

**Buffer:** Never plan for 100% utilization. At 100%, any spike causes failure. Target 70–80% under normal load. Spikes (2x, 3x) stay within capacity. Different teams use different thresholds. 70% is conservative. 80% is common. 90% is aggressive. Choose based on predictability of your traffic. Spiky = more buffer. Steady = less.

---

## Let's Walk Through the Diagram

```
CAPACITY TIMELINE:

Usage
  ^
  |                                    ┌── Limit
  |                               ┌────┤
  |                          ┌────┤    │
  |                     ┌────┤    │    │  ▲ Scale HERE
  |                ┌────┤    │    │    │  (at 70-80%)
  |           ┌────┤    │    │    │    │
  |      ┌────┤    │    │    │    │    │
  | ─────┤    │    │    │    │    │    │
  |      │    │    │    │    │    │    │
  +------+----+----+----+----+----+----+------> Time
        Now  1mo  2mo  3mo  4mo  5mo  6mo
              │
              └── Projected growth (10%/month)
              
        Scale at month 3-4, not at month 5 when you're at limit.
```

The diagram shows: plan the scale-up before the line hits the limit. Reactive is when you're already at the limit. Proactive is scaling at 70–80%. No midnight emergencies.

---

## Real-World Examples (2-3)

**Netflix** plans for peak events. New season drops. Millions stream at once. They model load. Add capacity in advance. They've written about "capacity as a service"—predictive scaling. Not "we're at 95%, add servers." But "next week we'll need 2x, add now."

**Amazon** during Prime Day. They know the date. They know the pattern. Months of capacity planning. Adding servers. Testing. Load testing at 2x expected traffic. When the day comes, they're ready. No surprises.

**Startups** often skip capacity planning. "We'll scale when we need to." Then they get a TechCrunch article. Traffic 10x. Everything breaks. Lesson: even small teams should have simple capacity models. "We have 5 servers. Each handles 1000 RPS. We're at 3000 RPS. We need 3 more servers before we hit 5000." Simple. Effective. Do it.

---

## Let's Think Together

**"Current: 10 servers at 60% CPU. Traffic grows 15% monthly. When do you need to add servers?"**

At 60% now, you headroom for about 67% more traffic before you hit 100% (assuming linear scaling). 67% growth at 15%/month: roughly 3.5 months. So you have about 3–4 months. But don't wait until 100%. Scale at 80%. That's 80/60 = 1.33x current traffic. At 15%/month, 1.33x takes about 2 months. So: add servers in roughly 2 months. Or: recalculate each month. Update the projection. Adjust. Capacity planning is iterative. Not a one-time calculation. Revisit. Refine. Act before you need to.

---

## What Could Go Wrong? (Mini Disaster Story)

A gaming company launched a new title. They had 20 servers. Projected 10,000 concurrent players. Launch day: 50,000. Five times the projection. Servers melted. Game unplayable. Angry players. Refunds. What went wrong? They based the projection on their previous game—a different genre, different audience. They didn't stress test. They didn't model "what if we're wrong?" Conservative capacity planning would have said: "Prepare for 2–3x our projection." 30,000 or 40,000. Still might have been tight. But 20,000 would have been closer. Lesson: projections are wrong. Plan for variance. Buffer for uncertainty. And stress test before launch. Know your actual limits. Don't guess.

---

## Surprising Truth / Fun Fact

The "rule of 72" from finance applies to growth. Divide 72 by your growth rate to get doubling time. 10% monthly growth: 72/10 ≈ 7 months to double. 15%: about 5 months. 20%: about 3.6 months. Use it for quick capacity math. "We'll double in 6 months. Do we have 2x capacity?" Simple. Useful. Capacity planning doesn't need complex models to start. Simple math and regular check-ins go far.

---

## Quick Recap (5 bullets)

- **Measure** = CPU, memory, disk, network, DB connections, queue depth.
- **Project** = historical growth, events, roadmap; combine into demand forecast.
- **Identify** = when do we hit limits? 4 months? 6 months?
- **Plan** = add capacity BEFORE the limit; buffer at 70–80%, not 100%.
- **Iterate** = recalculate monthly; projections are wrong; adjust.

---

## One-Liner to Remember

*Capacity planning is counting chairs before the wedding—measure now, project growth, add capacity before the overflow.*

---

## Next Video

Next: Cost modeling. What are the biggest drivers of your cloud bill? Compute. Storage. Network. How to understand and optimize. See you there.
