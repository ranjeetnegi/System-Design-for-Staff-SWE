# What to Build vs What NOT to Build

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

You need to cross a river. Do you build a bridge? Take the ferry? Or swim?

Most engineers jump straight to "build the bridge." Staff engineers ask a different question first: "Should we build anything at all?"

Today: the art of knowing what to build — and what to never touch.

---

## The Story

You need to cross a river. Three options.

**Option A: Build a bridge.** Months of work. Expensive. But once built, durable. You own it. You control it. Great if you're crossing every day for decades.

**Option B: Take the ferry that already exists.** Fast. Cheap. Someone else maintains it. You cross today. But you don't control the schedule. You depend on them. If the ferry stops, you're stuck.

**Option C: Swim.** Free. Risky. Slow. Fine for a one-time crossing. Terrible for daily commute.

L6 engineers don't just ask *how* to build. They ask *whether* to build at all. Use a managed service? Buy a vendor solution? Build custom? Each has trade-offs. The wrong choice costs years.

---

## Another Way to See It

Think of cooking. Making pasta from scratch—flour, eggs, rolling, drying—is rewarding. But for Tuesday dinner? Store-bought pasta is fine. Save the from-scratch for special occasions. Not everything deserves the full effort. A Michelin chef doesn't hand-grind flour for every dish. They focus their craft where it matters. The rest? Quality ingredients, well sourced. Building software is the same. Not every component needs custom engineering. Some things are commodity. Use the commodity. Save your brilliance for what actually differentiates you. The 80/20 rule applies everywhere: 80% of your needs are met by off-the-shelf solutions. That last 20%—the part that makes you unique—is where you build.

---

## Connecting to Software

**Build (custom):**
- Full control. Custom-fit to your exact needs.
- Expensive to build AND maintain. Requires team expertise.
- Use when: it's core to your business, no good solution exists, or you have unusual scale/requirements.

**Buy / Use managed:**
- Fast to adopt. Someone else maintains it. Less operational burden.
- Less control. Vendor lock-in risk. Cost scales differently (per-seat, per-request).
- Use when: it's not differentiator, commodity problem, time-to-market matters.

**Defer:**
- Don't build it yet. Validate the need first. Build the simplest version. Iterate.
- Use when: unclear requirements, unproven demand, or you're not sure it's the right problem.

**The 80/20 rule:** Managed services and vendors often handle 80% of needs. Custom-building that last 20% can cost 5× more. Is the 20% worth it?

---

## Let's Walk Through the Diagram

```
DECISION TREE: Build vs Buy vs Defer

                    ┌─────────────────────┐
                    │  Do we need it?     │
                    │  (Validated need?)  │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │ No             │ Yes            │
              ▼                ▼                │
        ┌──────────┐    ┌──────────────────────┴───┐
        │  DEFER   │    │  Is it our differentiator? │
        │  Don't   │    └──────────────┬─────────────┘
        │  build   │                   │
        └──────────┘        ┌───────────┴───────────┐
                            │ Yes       │ No       │
                            ▼           ▼          │
                    ┌──────────┐  ┌──────────┐    │
                    │  BUILD   │  │  BUY /   │    │
                    │  Custom  │  │  Managed │    │
                    └──────────┘  └──────────┘    │
```

**Narration:** Flow from need to differentiator. No need? Defer. Don't build for hypotheticals. Validate first. Need but not differentiator? Buy or use managed. Time-to-market matters. Let someone else solve the commodity problem. Need AND differentiator? Build. This is where you invest. The diagram isn't just a flowchart—it's a decision framework. Staff engineers run through it before committing to any build. Saves countless wrong investments and years of maintenance burden.

---

## Real-World Examples (2-3)

**Example 1: Stripe.** Payments are their core. They built their own. Full control. Competitive advantage. Meanwhile, they use AWS, Datadog, and other commodity infra. Build what matters. Buy the rest. The lesson: even companies with massive engineering budgets don't build everything. They build their moat. They rent the foundation.

**Example 2: Slack.** Messaging is core. They built it. But search? They started with a vendor. When scale demanded it, they built custom. Defer until you need it. Build when you outgrow. The defer-then-build path is valid. Don't over-build for a problem you might not have. Validate first. Scale later. If you ever need to.

**Example 3: The startup that built everything.** Custom auth, custom queue, custom cache, custom search. 18 months to MVP. Ran out of runway. Competitors who used Auth0, SQS, Redis, Algolia shipped in 3 months. Built themselves into bankruptcy. The tragic part: the custom systems weren't better. They were just different. Different isn't always valuable. Sometimes it's just expensive.

---

## Let's Think Together

**Question:** You need a search engine. Elasticsearch (self-managed), Algolia (SaaS), AWS OpenSearch (managed). Trade-offs?

**Answer:** 
- **Algolia:** Fastest to ship. Zero ops. Great relevance out of the box. Expensive at scale. Less control. Good for: MVP, < 10M docs, time-critical.
- **OpenSearch:** Managed Elasticsearch. Less ops than self-managed. AWS integration. Good middle ground. Good for: AWS-heavy shops, moderate scale.
- **Elasticsearch self-managed:** Full control. Cheapest at massive scale. Requires expertise. Ops burden. Good for: massive scale, unusual requirements, search is your product.

Staff move: Start with Algolia or OpenSearch. Validate. If search becomes a bottleneck or differentiator, migrate to custom. Don't start with the hardest option.

---

## What Could Go Wrong? (Mini Disaster Story)

A company decided to build their own message queue. "Kafka is complex. We'll make something simpler." Two engineers spent a year. They built something that worked — for their scale. Then they scaled 10×. Bugs. Data loss. No replication. No tooling. They spent another year rewriting on Kafka. Two years. One "simple" build decision. They could have used SQS or Kafka from day one. Ego cost them a year.

---

## Surprising Truth / Fun Fact

**Fun fact:** Amazon's "Build vs Buy" culture is famous. They build when it's strategic (AWS, fulfillment, recommendations). They buy when it's not (HR software, office supplies). Jeff Bezos allegedly said: "Your margin is my opportunity." They focus build-energy on margin. Everything else: buy or partner.

---

## Quick Recap (5 bullets)

1. **Ask "whether" before "how"** — Don't assume you need to build.
2. **Build** when it's your differentiator or no good option exists.
3. **Buy/managed** when it's commodity and time-to-market matters.
4. **Defer** when the need isn't validated. Build the simplest version first.
5. **80/20** — Managed handles 80%. Custom for the last 20% costs 5×. Worth it?

---

## One-Liner to Remember

*"The best code is the code you never write. The best system is the one you don't have to maintain."*

---

## Next Video

Next up: How Staff system design interviews are actually evaluated. It's not about the diagram. It's about how you think.
