# Configuration Management: Push vs Pull

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Two ways to update house rules for 100 apartment residents. Push: landlord slips a note under every door. Instant. But someone's on vacation—they miss it. Pull: residents check the notice board every morning. They get updates at their own pace. But there's a delay. Push vs pull. Two strategies. Both trade off speed for reliability. Configuration management is the same. Your servers are the residents. The config is the rules. How do you get it to them? Choose wisely.

---

## The Story

Your app has 1000 servers. You need to change a config: "Enable feature X." "Set cache TTL to 300 seconds." How does that config reach every server? Push: you send it. Config server pushes to all servers. Fast. Everyone gets it now. But: server was restarting. Missed the push. Now it has stale config. Pull: servers ask. "What's the config?" Every 30 seconds. They get it when they poll. Slower. But: server was down? Next poll, it gets latest. Self-healing. No server left behind. The choice depends on what matters more: speed or reliability. Push = fast, but you need retries and acknowledgments. Pull = delayed, but simple and self-correcting. Many systems use both. Push to notify. Pull to fetch.

---

## Another Way to See It

Radio vs newspaper. Radio: broadcast. Everyone tuned in gets the update now. Missed it? Gone. Push. Newspaper: you go buy one. You get it when you want. Pull. Radio is instant but ephemeral. Newspaper is delayed but you control when you read. Config is similar. Push = broadcast. Pull = fetch when ready. Neither is wrong. Context decides. Breaking change? Maybe push. Routine update? Pull is fine.

---

## Connecting to Software

**Push.** Config change → push to all servers immediately. Fast propagation. Seconds to global update. But: server offline? Miss. Need: retry, acknowledgment, version tracking. If a server doesn't ack, retry. Track which servers have which version. Complex. Push can also overwhelm. 10,000 servers. All get config at once. Thundering herd. Stagger. Or use message bus (Kafka)—servers consume when ready. Push doesn't mean "all at once." It means "server initiates the send." You can still throttle.

**Pull.** Servers poll config service every N seconds. "Give me latest config." Simple. Reliable. Server was down? Next poll, gets latest. Self-healing. No coordination. But: delay. N seconds. Worst case: you change config, server polls 1 second before change. It gets old config. Next poll in N seconds. Staleness = up to N seconds. For most configs, fine. For "kill switch," maybe not. Know your tolerance for staleness.

**Hybrid.** Push notification: "Config changed." Server receives. Immediately pulls new config. Fast + reliable. Push tells you when. Pull gets the data. Best of both. Consul, etcd support this. Watch for changes. On change, fetch. The hybrid is often the sweet spot. You get speed without the complexity of full push reliability.

**Feature flags.** Config-driven. "Enable dark mode for 10% of users." Change config → feature changes. Push = instant rollout. Pull = within N seconds. A/B testing. Gradual rollout. Kill switch. All config. Feature flags are config with product implications. Same push vs pull. Same trade-offs. Rollout strategy is config strategy.

---

## Let's Walk Through the Diagram

```
CONFIG MANAGEMENT - PUSH VS PULL
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   PUSH:                                                          │
│   Config Server ──► Push ──► [S1] [S2] [S3] ... [S1000]         │
│        │              │         │    │    │        │             │
│        │              └─────────┴────┴────┴────────┘             │
│        │                Instant. But: who missed it?             │
│        │                Retry. Ack. Version tracking.            │
│                                                                  │
│   PULL:                                                          │
│   [S1] [S2] [S3] ──► Poll every N sec ──► Config Server         │
│        │                   │                    │                │
│        └────────────────────┴────────────────────┘                │
│                Self-healing. Delay = N seconds.                   │
│                                                                  │
│   HYBRID:                                                        │
│   Config change → Notify "changed" → Servers pull immediately     │
│   Fast propagation + Reliable delivery                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Push: config server sends to all. Fast. Track acks. Retry misses. Pull: servers ask. Simple. Stale for N seconds. Hybrid: notify then pull. Best of both. Choose by needs. The diagram shows the flow. The implementation shows the care. Bad config + push = instant disaster. More on that in "What Could Go Wrong."

---

## Real-World Examples (2-3)

**etcd / Consul.** Key-value stores. Watch for changes. On change, clients get notified. They pull new config. Used by Kubernetes. De facto for distributed config. The infrastructure of infrastructure.

**AWS Systems Manager Parameter Store.** Managed. Servers pull. Or use push with Run Command. Hybrid available. Good for AWS-native. Pay for convenience. No etcd to run.

**LaunchDarkly.** Feature flags as a service. Push or pull. Real-time updates. A/B testing. Gradual rollouts. Config as a product. When config is your business, you do it right. Learn from them.

---

## Let's Think Together

**"You push a bad config that crashes servers. Push = all servers crash simultaneously. Pull = rolling damage. Which is more dangerous?"**

Push is riskier. One bad push, everyone gets it. 10,000 servers. All restart. All crash. Total outage. Pull: servers poll at different times. Staggered. Server 1 gets bad config at T=0. Crashes. Server 2 at T=5. Crashes. Rolling. Some servers still healthy. You notice. Roll back. Push: instant carnage. Mitigation: canary. Push to 1% first. Monitor. Then rest. Or: version config. Servers only apply if version is newer. Rollback by pushing previous version. Config management needs rollback strategy. Always. Before you push. Not after.

---

## What Could Go Wrong? (Mini Disaster Story)

A team pushes a config: "Set connection pool size to 0." Typo. Meant 100. Push goes to all servers. Connection pool = 0. Every server rejects all DB connections. Full outage. 5 minutes to detect. 10 minutes to fix. Push is powerful. Bad config + push = instant disaster. Mitigations: validate config before push. Schema. Bounds. "Pool size must be 1-1000." Or: gradual rollout. 1 server. Then 10. Then all. Config changes need the same care as code deploys. Sometimes more. Code has tests. Config often doesn't. Add validation. Add canary. Add rollback. Your future self will thank you.

---

## Surprising Truth / Fun Fact

Kubernetes uses etcd for config. Every pod's config (ConfigMaps, Secrets) is stored there. When you kubectl apply, it's a push to etcd. Pods watch (pull) for changes. Kubernetes uses both. Push to store. Pull (watch) to consume. The pattern is everywhere once you look. Even the systems we think of as "push" often have pull underneath. The hybrid is the norm at scale.

---

## Quick Recap (5 bullets)

- **Push:** Config → servers. Fast. Needs ack, retry. Risk: bad config = everyone gets it.
- **Pull:** Servers poll. Simple. Self-healing. Delay = poll interval.
- **Hybrid:** Notify on change + pull. Fast and reliable.
- **Feature flags:** Config-driven. Push = instant. Pull = N seconds.
- **Bad config + push = total outage.** Validate. Canary. Rollback plan.

---

## One-Liner to Remember

**Config management is push vs pull: push is fast but risky, pull is slow but self-healing.**

---

## Next Video

Next: secrets management, config versioning, and environment-specific config. Going deeper.
