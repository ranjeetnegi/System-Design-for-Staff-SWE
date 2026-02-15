# Cross-Region Consistency: The Real Trade-Offs

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Two bank branches. Mumbai and Delhi. A customer has Rs 1,00,000. They withdraw Rs 80,000 in Mumbai. At the exact same moment, they try to withdraw Rs 80,000 in Delhi. If both branches don't INSTANTLY know about each other's transactions, they both approve. The customer walks away with Rs 1,60,000 from a Rs 1,00,000 account. That's not magic. That's a bug. Cross-region consistency is about preventing exactly this—and the trade-offs are brutal. You can't cheat physics. You can only choose your pain.

---

## The Story

Imagine a restaurant chain. Mumbai serves biryani. Delhi serves biryani. Both use the same recipe. But the chef in Delhi doesn't know the chef in Mumbai just used the last bit of saffron. Both think they have saffron. Both start cooking. One dish has saffron. One doesn't. The experience is inconsistent. In software: your data lives in multiple regions for speed and disaster recovery. A user updates their profile in US-East. Seconds later, they read from EU-West. What do they see? The old profile? The new one? The answer depends on how fast your data traveled across the ocean. And here's the cruel part: the ocean doesn't care. Data crossing 7,000 miles takes 50 to 200 milliseconds. That's physics. You cannot make light travel faster. Every write that waits for confirmation from another region waits that long. That's the cost of strong consistency across regions.

---

## Another Way to See It

Think of it like a family WhatsApp group. Mom posts: "Dinner at 7." Dad reads it instantly—he's on fast WiFi. Grandma reads it 2 minutes later—her phone was in her bag. Everyone eventually sees the same message. That's eventual consistency. Now imagine a different rule: no one can eat until Grandma has read AND acknowledged the message. Dinner waits. Maybe 2 minutes. Maybe 10. That's synchronous replication. Strong consistency. Everyone is in sync. But you pay with time. In distributed systems, "Grandma" might be a server 200ms away. Every operation waits for her. Every. Single. One.

---

## Connecting to Software

**The problem.** Cross-region latency is 50–200ms. That's the speed of light. You can't reduce it. If every write must wait for confirmation from another region before returning success—that's synchronous replication—every write adds 50–200ms. Your API that could respond in 5ms now takes 205ms. Users feel it. Systems slow down. Throughput drops. Strong consistency across regions has a real, measurable cost.

**Option 1: Synchronous.** Every write goes to primary. Primary replicates to secondary in another region. Write doesn't complete until secondary acknowledges. Strong consistency. Both regions have the same data before you return. But: every write waits. 50–200ms per write. Kills performance. Acceptable for critical things like payments. Unacceptable for most everything else.

**Option 2: Asynchronous.** Write to primary. Return immediately. Replicate in the background. Fast. Low latency. But: if user reads from the other region 50ms later, replication might not have finished. Stale read. Conflicts possible. Two users edit the same document in different regions? Both write. Replication converges. Who wins? You need conflict resolution. Eventually consistent. Fine for social feeds. Dangerous for money.

**Option 3: Partial or hybrid.** Critical data—payments, inventory, account balance—synchronous. Non-critical—user preferences, analytics, recommendations—asynchronous. You pay the latency cost only where it matters. Most systems do this. Stripe: payment data strongly consistent. Dashboard metrics: eventually consistent.

**Google Spanner.** They use TrueTime—GPS and atomic clocks—to assign globally monotonic timestamps. Enables global consistency with bounded staleness. Amazing. Also: expensive. Complex. Requires custom hardware. Most companies don't need it. Most companies use PostgreSQL with read replicas and accept eventual consistency for reads.

---

## Let's Walk Through the Diagram

```
CROSS-REGION CONSISTENCY OPTIONS
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   SYNCHRONOUS (Strong Consistency)                               │
│                                                                  │
│   [User Write] ──► [US Primary] ──┬──► Replicate ──► [EU Replica]│
│                        │          │         │                    │
│                        │          └── Wait for ACK ──┘            │
│                        │                      │                  │
│                        └── Return success ONLY after ACK         │
│                        Latency: +50-200ms per write              │
│                                                                  │
│   ASYNCHRONOUS (Eventual Consistency)                           │
│                                                                  │
│   [User Write] ──► [US Primary] ──► Return immediately ✅         │
│                        │                                          │
│                        └── Replicate in background (no wait)     │
│                        Latency: fast. Risk: stale reads.          │
│                                                                  │
│   HYBRID (Best of both?)                                         │
│                                                                  │
│   Payments ──► Sync   (must be consistent)                       │
│   Profile   ──► Async (ok if stale for 200ms)                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Synchronous—every write waits for the other region. Strong guarantee. Slow. Asynchronous—write and return. Fast. Stale reads possible. Hybrid—pay the cost only where it matters. The diagram shows the trade-off. There's no free lunch. Physics decides. You choose which pain to accept.

---

## Real-World Examples (2-3)

**Stripe.** Payments are synchronous across regions. When you charge a card, that transaction is committed in multiple regions before you get confirmation. Why? Double charges, refunds, disputes—all require exact consistency. They pay the latency. They get the guarantee. For billing dashboards and analytics? Eventually consistent. Different requirements. Different choices.

**Netflix.** Your "Continue Watching" list. You finish an episode in the US. Fly to Europe. Open Netflix. Does it show the next episode? Usually. Sometimes there's a few seconds of lag. They use eventual consistency for watch history. The trade-off: occasional lag is acceptable. Strong consistency across continents would slow every playback interaction. Not worth it for their use case.

**Uber.** Your ride status. When a driver accepts, that needs to propagate. But exact millisecond consistency? Not required. A few hundred milliseconds of lag between regions is fine. They use a hybrid model. Critical path: ride state, payment. Stronger consistency. Everything else: eventual.

---

## Let's Think Together

**"User updates profile in US. Reads from EU 50ms later. Async replication lag is 200ms. What do they see?"**

They see the old profile. Their update hasn't replicated yet. To them, it looks like the update failed. Confusing. Frustrating. Solutions: (1) Route reads to the same region as writes for that user (session stickiness). (2) Show a "syncing" state. (3) Accept it for non-critical data. (4) Use synchronous replication and pay the 200ms. Staff engineers choose based on the user impact. Profile picture? Maybe show "syncing." Payment status? Never show stale. The question forces you to think about what "eventually" means to a real user. And what happens in those 200ms.

---

## What Could Go Wrong? (Mini Disaster Story)

An e-commerce company runs promotions. "First 100 orders get 50% off." Database in US. Read replica in EU for European customers. Async replication. At 9:00:00, 50 US customers order. Inventory shows 50 claimed. Replication starts. At 9:00:01, 60 EU customers order. Their reads hit the EU replica. Replication lag: 500ms. EU replica still shows 100 available. All 60 orders go through. Total: 110 orders. They promised 100. Inventory oversold. Refunds. Angry customers. Blog posts: "Company X can't count." The fix: for inventory and promotions, use strong consistency. Or: don't show exact counts. "Limited quantity" without a number. Or: accept over-delivery as a cost. But don't promise exactly 100 and deliver 110. Eventually consistent inventory is a recipe for overselling. The disaster is predictable. So is the fix.

---

## Surprising Truth / Fun Fact

The speed of light in a fiber cable is about two-thirds the speed of light in vacuum. Data from New York to London—roughly 3,500 miles—cannot arrive in less than about 28 milliseconds one way. Round trip: 56ms minimum. Add routing, switches, processing: 80–120ms typical. When someone says "we have 50ms cross-region latency," they're either very close (same continent) or measuring something different. Physics is the floor. You can't optimize below it. Every cross-region consistency design starts with that number. It never goes away.

---

## Quick Recap (5 bullets)

- **Cross-region latency is 50–200ms.** Physics. Synchronous replication = every write waits. Kills performance.
- **Options:** Synchronous (strong, slow), Asynchronous (fast, stale), Hybrid (critical sync, rest async).
- **Google Spanner** uses TrueTime for global consistency. Expensive. Complex. Not for everyone.
- **Most systems use hybrid:** payments sync, profiles async. Pay latency cost only where it matters.
- **Replication lag causes stale reads.** User updates in one region, reads from another—might see old data.

---

## One-Liner to Remember

**Cross-region consistency trades latency for truth—synchronous waits, asynchronous lies; pick your poison.**

---

## Next Video

Next: when "eventually consistent" is not OK. Some things cannot wait for "eventually." Bank balances. Access control. What happens when you get it wrong.
