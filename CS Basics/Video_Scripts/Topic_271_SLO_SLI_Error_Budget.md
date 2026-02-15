# SLO, SLI, Error Budget: The Basics

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A bus company promises: "99% of buses arrive within 5 minutes of schedule." That's an SLO—a Service Level Objective. How do they measure it? They track actual arrival times. "This month: 98.5% on time." That's the SLI—the Service Level Indicator. The real number. They promised 99%. They're half a percent under. They've used up their error budget. No more room for delays. Time to focus on reliability over new features. That's the error budget. Let's break it down.

---

## The Story

You can't improve what you don't measure. And you can't set targets you don't track. SLOs give you a target. SLIs give you the measurement. Error budget is what's left when you miss—and it drives decisions. Should we ship this risky feature? Or fix reliability first? The error budget tells you. If you have budget left—ship. If you've exhausted it—freeze features, focus on reliability. It's a simple idea. Powerful when used right.

Think of it like a diet. Your SLO: "lose 2 kg this month." Your SLI: you step on the scale. 1.5 kg lost. You're under target. Your "error budget"—the 0.5 kg you didn't lose—means you need to adjust. More gym. Fewer treats. The measurement drives the behavior. SLOs work the same way. Measure. Compare to target. Act on the gap.

---

## Another Way to See It

A speedometer in a car. The speed limit is 100 km/h—that's your SLO. The speedometer shows 95—that's your SLI. You're under. Good. If you're at 110, you've "used" your margin. Error budget: how much "bad" you can have before you've broken your promise. For availability, it's the allowed downtime. For latency, it's the allowed slow requests. Finite. Use it wisely.

---

## Connecting to Software

**SLI (Service Level Indicator):** The MEASUREMENT. A quantitative measure of service level. "What percentage of requests return successfully?" "What percentage of requests complete in under 200ms?" "What percentage of time is the service up?" Examples: availability = successful requests / total requests. Latency = percentage of requests under threshold. Freshness = how old is the data. You pick SLIs that matter for your users. For an API: availability and latency. For a dashboard: freshness. For a video stream: buffer ratio.

**SLO (Service Level Objective):** The TARGET. A goal for the SLI. "99.9% of requests should succeed." "99% of requests should complete in under 200ms." "99.95% availability." You set the number. It should be achievable but not trivial. 100% is impossible. 99% might be too loose. 99.9% (three nines) is common for many services. 99.99% (four nines) for critical systems. The SLO is an internal target. Not a promise to customers. That's the SLA.

**Error budget:** 100% − SLO = error budget. If SLO is 99.9%, error budget is 0.1%. Over a month (43,200 minutes), 0.1% = 43 minutes of allowed downtime. Or 0.1% of requests can fail. Or 0.1% can be slow. You "spend" the budget when things go wrong. When it's exhausted, you stop shipping features and fix reliability. The budget forces trade-offs. No infinite "we'll fix it later." Finite budget. Use it or protect it.

**SLA (Service Level Agreement):** The LEGAL CONTRACT with customers. "We promise 99.9% uptime. If we miss, you get a refund." SLAs have financial consequences. SLOs are internal. You set SLOs tighter than SLAs—maybe 99.95% SLO when SLA is 99.9%—so you have buffer before you owe customers money.

---

## Let's Walk Through the Diagram

```
SLO: 99.9% availability
Error budget: 0.1% = 43 min/month (of 43,200 min)

Month timeline:
|------------------------------------------------------------------|
0 min                    21,600 min                    43,200 min
                                               ▲
                                    Downtime: 15 min used
                                    Budget remaining: 43 - 15 = 28 min
                                    Status: Can still ship (budget left)

If downtime = 50 min:
                                    Budget: 43 - 50 = -7 min
                                    Status: EXHAUSTED. No new features.
                                    Focus: Reliability only.
```

The diagram shows: you "spend" the budget with every outage. When it's gone, you stop. Simple rule. Hard to follow when product wants to ship. But it works. Google SRE made this famous. Error budgets create balance between feature velocity and reliability.

---

## Real-World Examples (2-3)

**Google** invented the error budget concept. Teams have SLOs. When they exhaust the budget, feature work stops. Reliability work begins. No exceptions. It's written into their SRE book. The idea spread. Now it's industry standard for mature engineering orgs.

**Stripe** has strict SLOs for their payment APIs. Downtime means lost revenue for merchants. They track availability, latency, error rates. Error budget drives release decisions. Risky deploy? Check the budget. Low budget—wait. High budget—maybe ship, but carefully.

**Netflix** uses SLOs for their streaming service. Buffer ratio. Start time. Playback quality. Their chaos engineering (breaking things on purpose) helps them understand their error budget. How much can they afford to lose? They test the limits.

---

## Let's Think Together

**"SLO is 99.95%. This month you've had 15 minutes of downtime. How much error budget remains? (Month = 43,200 minutes)"**

99.95% availability = 0.05% error budget. 43,200 × 0.05% = 21.6 minutes allowed. You've used 15. Remaining: 21.6 − 15 = 6.6 minutes. You have about 6 minutes left. One more incident could exhaust it. Be careful. Maybe postpone that risky deploy. Or do it during low-traffic hours with extra monitoring. The math is simple. The discipline is using it to make decisions.

---

## What Could Go Wrong? (Mini Disaster Story)

A team had a 99.9% SLO. They ignored it. Shipped features. Had incidents. Used 60 minutes of downtime in a month—error budget was 43. They were 17 minutes over. Nobody noticed. Customers complained. The CEO asked: "Why is our service so unreliable?" The team had no answer. They had no process. No error budget reviews. No "stop shipping" rule. They implemented SLOs properly. Error budget reviews every week. When budget was low, features waited. Reliability improved. Lesson: SLOs only work if you USE them. Track. Review. Enforce. Otherwise they're just numbers on a dashboard nobody looks at.

---

## Surprising Truth / Fun Fact

"Five nines" (99.999%) sounds impressive. But it's only 26 seconds of downtime per month. Achieving it is expensive. Redundancy. Failover. Testing. Most services don't need it. 99.9% (43 minutes/month) is fine for many. 99.95% (22 minutes) for critical. Choose based on user impact. Don't chase nines for ego. Chase them for the right reasons. A blog doesn't need five nines. A payment API might.

---

## Quick Recap (5 bullets)

- **SLI** = the measurement (e.g., % success, % under 200ms).
- **SLO** = the target (e.g., 99.9% availability).
- **Error budget** = 100% − SLO; finite; when exhausted, stop features, fix reliability.
- **SLA** = legal contract with customers; SLO should be tighter than SLA.
- **Use it** = track, review, enforce; error budget only works if it drives decisions.

---

## One-Liner to Remember

*SLI is what you measure. SLO is what you promise yourself. Error budget is what's left—and when it's gone, you fix, not ship.*

---

## Next Video

Next: Capacity planning. 10 servers at 60% CPU. Traffic grows 15% monthly. When do you need more? See you there.
