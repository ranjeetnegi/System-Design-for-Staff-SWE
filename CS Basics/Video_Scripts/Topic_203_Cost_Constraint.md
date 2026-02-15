# Cost as a First-Class Constraint

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

You design a beautiful system. Multi-region. Synchronous replication. 99.999% uptime. Perfect. Then finance asks: "What's the bill?" You haven't thought about it. The design is technically flawless—and financially impossible. At Staff level, cost isn't an afterthought. It's a constraint. From day one.

---

## The Story

You hire an architect. "Design my dream house." Marble floors. Gold faucets. Infinity pool. Home theater. They deliver stunning blueprints. You love it. Then you say: "Budget is ten lakhs." The architect stares. "That won't cover the marble for one room." The design was beautiful. It was also useless. An architect who ignores cost is not an architect—they're an artist. Clients need both: vision and viability.

In system design, cost is the same. Multi-region? Expensive. Synchronous replication? Very expensive. 99.999% uptime? Extremely expensive. L6 engineers consider cost from the START. Not as a cleanup task. Not as "we'll optimize later." As a first-class constraint alongside latency, availability, and correctness.

---

## Another Way to See It

Imagine planning a road trip. You could design the perfect route: scenic highways, five-star hotels, gourmet restaurants. Or you could design a route that fits your budget: efficient mileage, reasonable hotels, good enough food. Both get you there. One empties your wallet. The other gets you there and back. System design is the same trip. Cost is the fuel. Run out and the journey stops.

---

## Connecting to Software

Cloud costs add up fast. **Compute** (EC2, Lambda): per second, per instance. **Storage** (S3, EBS): per GB, per month. **Network** (data transfer): often the hidden killer—egress fees, cross-region transfer. **Managed services** (RDS, Kafka, DynamoDB): convenience has a price. Each has unit economics. Staff engineers know them.

**Cost thinking:** "Do we NEED 99.99%? 99.9% is ten times cheaper. Is 52 minutes of downtime per year worth $500K extra?" Right-sizing: don't run ten c5.4xlarge instances when five c5.2xlarge would suffice. Auto-scaling. Spot instances for non-critical work. Reserved capacity for predictable load. The questions never stop: "What happens to cost at 10x scale? 100x?" Cost modeling isn't a one-time exercise—it's iterative. As traffic grows, unit economics shift. What was cheap at 1x might be expensive at 10x. Staff engineers revisit the numbers quarterly. It's part of the job.

---

## Let's Walk Through the Diagram

```
COST LAYERS IN A TYPICAL SYSTEM
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   USER REQUEST                                                    │
│        │                                                         │
│        ▼                                                         │
│   ┌─────────────┐   CDN/Data Transfer    $$$ (egress)            │
│   │    CDN      │ ───────────────────►                           │
│   └─────────────┘                                                 │
│        │                                                         │
│        ▼                                                         │
│   ┌─────────────┐   Compute (EC2/Lambda) $$$$ (per second)       │
│   │  App Tier   │ ───────────────────►                           │
│   └─────────────┘                                                 │
│        │                                                         │
│        ▼                                                         │
│   ┌─────────────┐   Database (RDS/DynamoDB) $$$$ (instance + IO) │
│   │  Data Tier  │ ───────────────────►                           │
│   └─────────────┘                                                 │
│        │                                                         │
│        ▼                                                         │
│   ┌─────────────┐   Storage (S3/EBS)  $$ (per GB-month)          │
│   │   Storage   │ ───────────────────►                           │
│   └─────────────┘                                                 │
│                                                                  │
│   Each layer has unit economics. Model them. Right-size them.     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Walk through it: Every layer costs money. CDN egress. Compute time. Database IOPS. Storage. Staff engineers model these. "At 1M requests/day, our Lambda bill is X. Our RDS is Y. Our S3 is Z." They don't guess. They calculate. And they ask: "Where can we trim without breaking the system?"

---

## Real-World Examples (2-3)

**Example 1: Dropbox.** They saved millions by building their own storage infrastructure instead of pure S3. At their scale, the unit economics flipped. Building was cheaper than buying. But that's at massive scale. For most teams, S3 is cheaper. Know your scale.

**Example 2: Spotify.** They moved from Google Cloud to a hybrid model. Some workloads on-prem. Some on cloud. Why? Cost. At their scale, certain workloads were cheaper to run themselves. The decision was economic, not just technical.

**Example 3: Startups.** Many burn cash on over-provisioned infrastructure. "We might need 100 instances." They run 100. Peak load is 20. Right-sizing and auto-scaling could cut the bill by 80%. Staff engineers demand the numbers before signing off. They model cost at launch, at 10x, at 100x. They ask: "What's our burn rate if we 10x? Can we afford it?" Cost isn't a finance problem. It's an architecture constraint. Design for it from day one.

---

## Let's Think Together

"Your system processes 1M events per day via Kafka plus Lambda. Alternative: SQS plus EC2. Estimate which is cheaper."

**Kafka + Lambda:** Kafka has fixed infrastructure cost (brokers). Lambda scales per invocation. At 1M/day ≈ 12 invocations/second. Lambda: cheap at low volume. Kafka: always-on cost. SQS + EC2: SQS is pay-per-request, very cheap. EC2: you can right-size. Run a few small instances. Often SQS + EC2 wins at this scale—simpler, fewer moving parts, lower baseline cost. Kafka shines at high throughput (100K+ events/sec). At 1M/day, you might be overpaying. The exercise: model both. Don't assume. Calculate.

---

## What Could Go Wrong? (Mini Disaster Story)

A team launches a video platform. Brilliant architecture. Multi-region. Real-time transcoding. Global CDN. Ships. Month one: $50K cloud bill. Month two: $200K. Traffic grew. They never modeled cost at scale. The CFO is in the room. "We're spending more on infrastructure than revenue." Panic. They scramble: reduce regions, cut CDN, compress more aggressively. But the architecture wasn't built for cost. Retrofitting is painful. Feature velocity tanks. The lesson: cost from day one. Model at 1x, 10x, 100x. Know where the money goes before it goes there.

---

## Surprising Truth / Fun Fact

AWS made more money from data transfer (egress) in some years than from compute. Engineers often forget: moving data costs money. In-region is cheap. Cross-region is expensive. To the internet? Very expensive. A single "dump our database to a backup in another region" job can cost thousands. Staff engineers know: data has a price tag. Move it wisely.

---

## Quick Recap (5 bullets)

- **Cost is a first-class constraint.** Consider it alongside latency, availability, correctness.
- **Model unit economics:** Compute, storage, network, managed services. Each has a price.
- **Right-size:** Don't over-provision. Auto-scale. Use spot for non-critical. Reserved for predictable.
- **Ask the hard question:** "Do we need 99.99%? What's the business impact of 99.9%?"
- **Model at scale:** What happens at 10x? 100x? Cost scales non-linearly. Plan for it.

---

## One-Liner to Remember

**The best design fits the budget. Cost from day one—not as an afterthought.**

---

## Next Video

Next: what to build versus what not to build. The bridge, the ferry, and the swim—and when to choose each.
