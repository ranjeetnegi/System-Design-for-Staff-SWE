# Config and Feature Flags: Propagation and Safety

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A light switch in your house. Flip it: light turns on. Instant. Flip again: off. Simple. Feature flags are light switches for software. "Enable the new checkout flow for 10% of users." Flip. "It's causing errors!" Flip off. Instant rollback. No deployment needed. But what if the switch is broken? What if it takes 30 seconds to propagate? What if 10% means 10% in one region but 0% in another? Propagation and safety matter. Let's dive in.

---

## The Story

Feature flags let you ship code without activating it. Deploy the new UI. Flag off. Nobody sees it. Test in staging. Turn on for 1% of users. Monitor. Increase to 10%. Then 50%. Then 100%. Gradual. Safe. If something breaks, flip off. Rollback without redeploying. The power is real. Companies like LaunchDarkly, Split, and Optimizely built businesses on this. But flags have a dark side. Bad config causes outages. Slow propagation means inconsistency. A flag that says "10%" but takes 60 seconds to reach all servers? Some users see the new feature. Some don't. Random. Confusing. And if the flag service goes down? Do all flags default to off? To on? Chaos. Design for failure. Design for speed. Design for safety.

---

## Another Way to See It

Think of a PA system in a stadium. You announce: "Evacuate." Ideal: everyone hears it instantly. Reality: sound travels. Front row hears first. Back row, a second later. In a crisis, that delay matters. Feature flag propagation is the same. Push to all servers at once? Good. Poll every 60 seconds? Back row might not hear for a minute. Your "10% rollout" might be 15% on fast servers, 5% on slow. Inconsistent. The goal: propagation so fast it feels instant. Or accept the delay and design for it. But never assume "everyone has the same config right now." They might not.

---

## Connecting to Software

**Config propagation.** Two models: push and pull. Push: flag service pushes updates to servers. WebSocket or long poll. Server gets new config. Instant. Or near-instant. Pull: servers poll the flag service. "Any changes?" Every 30 seconds. Or 60. Or 5 minutes. Delay = poll interval. Push is faster. Pull is simpler. At scale, push needs infrastructure. Message bus. Or flag service pushes to CDN. Servers fetch from CDN. Cached. Fast. Choose based on your tolerance for staleness. "10% rollout" with 60-second poll: expect 1-2 minutes before all servers agree. Document it. Don't surprise yourself.

**Safety.** Bad config causes outages. Mitigate: gradual rollout. 1% → 5% → 25% → 100%. Watch error rates. Watch latency. If p99 spikes, roll back. Automate it. "If error rate > 2%, disable flag." Automatic rollback. No human in the loop. Or require human approval for 100%. Reduces blast radius. Also: kill switch. Emergency "turn off everything" button. When things go wrong, one click. All flags off. Or critical flags off. Design the worst-case path. Hope you never use it.

**Sticky assignment.** User sees the same variant consistently. hash(user_id + experiment_id) mod 100. If < threshold, they're in. If >= threshold, they're out. Deterministic. Same user, same result. Every time. Every server. Critical for A/B tests. If assignment changes mid-session, you're measuring noise. Sticky = reliable experiments. Implement it. Test it. Verify the same user gets the same value across requests.

---

## Let's Walk Through the Diagram

```
FEATURE FLAG PROPAGATION
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   FLAG SERVICE              PUSH              SERVERS            │
│   (LaunchDarkly)               │                                 │
│        │                       │                                │
│        │  "checkout_v2=10%"     │     Server 1 ──► 10% (instant) │
│        │───────────────────────┼────► Server 2 ──► 10% (instant)│
│        │                       │     Server 3 ──► 10% (instant)  │
│        │  PULL (alternative)    │                                │
│        │  Servers poll every 60s│     Server 4 ──► 10% (+ 0-60s)│
│        │                       │     Server 5 ──► 10% (+ 0-60s)  │
│                                                                  │
│   STICKY: hash(user_id + flag) mod 100 < 10 → user in 10%       │
│   SAFETY: Gradual rollout, auto-rollback on error spike.        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Flag service holds the config. Push: all servers get it fast. Pull: servers ask periodically. Delay possible. Either way, when a server evaluates a flag for a user, it uses sticky hashing. Same user, same result. The diagram shows both paths. Push = consistency. Pull = eventual consistency. Choose based on your needs. And always design for rollback. Because you will need it.

---

## Real-World Examples (2-3)

**Netflix.** Feature flags everywhere. Gradual rollouts. New UI? 1% first. Monitor. Scale up. If something breaks, instant rollback. No deploy. They've talked about this publicly. Flags are first-class. Part of their culture.

**Uber.** Similar. Flags for every feature. Push-based propagation. Low latency. Critical when you're running real-time systems. Config changes in seconds, not minutes. The infrastructure cost is worth it.

**LaunchDarkly.** SaaS feature flags. Used by thousands of companies. Push and pull modes. SDKs for every language. They solved the hard problems: propagation, sticky assignment, analytics. If you don't want to build it, buy it. The pattern is proven.

---

## Let's Think Together

**"You enable a flag for 5%. Error rate jumps 3x. How fast can you roll back? What if propagation takes 60 seconds?"**

Rollback speed = propagation speed. Push-based: flip the flag. Servers get it in seconds. Error rate drops. Pull-based: flip the flag. Some servers get it in 1 second. Some in 60. During that window, 5% of traffic still hits the bad code. 60 seconds of elevated errors. Mitigation: shorter poll interval. 5 seconds instead of 60. Trade: more requests to flag service. Or: push. Eliminate the delay. Best practice: push for critical flags. Pull for non-critical. And always have a kill switch that bypasses propagation—emergency override. Some systems support "force this value" at the load balancer. Instant. Use it when it matters.

---

## What Could Go Wrong? (Mini Disaster Story)

A team ships a new payment flow. Flag: 5% of users. They use a third-party flag service. Pull mode. 30-second poll. Launch. Error rate climbs. They flip the flag off. Wait. 30 seconds. Error rate still high. 60 seconds. Still high. 90 seconds. Finally dropping. 2 minutes to recover. During that time, 5% of payment attempts failed. Refunds. Support tickets. Lost trust. Postmortem: "Why did rollback take 2 minutes?" Propagation. They switched to push. Next time: 10 seconds. The difference between "minor blip" and "incident" is often propagation speed. Don't learn this in production. Design for fast rollback from day one.

---

## Surprising Truth / Fun Fact

Netflix runs the same code in production for weeks. New features? All behind flags. They don't deploy to "release" features. They flip flags. Deployments are for code. Flags are for control. That separation changed how they ship. No more "big bang" releases. Continuous deployment of code. Gradual activation of features. It's a mindset. And it scales. Thousands of engineers. Thousands of flags. All coordinated. The flag system is as critical as the app itself.

---

## Quick Recap (5 bullets)

- **Propagation:** Push = fast. Pull = delayed by poll interval. Choose based on rollback speed needs.
- **Safety:** Gradual rollout (1% → 100%). Auto-rollback on error spikes. Kill switch for emergencies.
- **Sticky assignment:** hash(user_id + flag) mod 100. Same user, same variant. Every time.
- **Design for rollback:** How fast can you turn off a bad flag? Propagation determines that.
- **Bad config causes outages:** Treat flags as production-critical. Audit. Test. Monitor.

---

## One-Liner to Remember

**Feature flags are light switches—but only if propagation is fast enough that flipping the switch actually turns off the light.**

---

## Next Video

Next: A/B test assignment, statistical significance, and when flags meet experimentation.
