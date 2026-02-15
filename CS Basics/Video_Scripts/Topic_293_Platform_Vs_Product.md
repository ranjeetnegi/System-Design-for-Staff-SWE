# Platform vs Product Team Mindset

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Two teams in a car company. Product team: designs the new car model. The features customers see—seats, dashboard, engine, paint color. Product thinks about what the customer wants. Platform team: builds the factory. The assembly line. The robots. The quality testing equipment. Customers never see the factory. But without the factory, no cars get built. In tech: product teams build features users see. Platform teams build the infrastructure, tools, and services that product teams depend on. Both are essential. Both have different goals. And the tension between them—that's where Staff-level judgment lives.

---

## The Story

Imagine a restaurant. The product team is the head chef. They design the menu. The flavors. The presentation. What the customer experiences. The platform team is the one that built the kitchen. The ovens. The refrigeration. The ordering system. The chef doesn't think about how the oven works. They just need it to heat. The platform team made that possible. The customer never thanks the platform team. They compliment the food. But the food doesn't exist without the kitchen. That's the relationship. Product creates value for users. Platform creates the conditions for product to create value. Invisible to the user. Essential to the system.

---

## Another Way to See It

Think of a theater. Product team: the actors, the script, the costumes. What the audience sees. Platform team: the stage, the lights, the sound system, the ticketing. The audience doesn't applaud the lighting technician. They applaud the performance. But the performance happens in the light. On the stage. With sound. Platform enables. Product delivers. Both matter. Different visibility. Different metrics. Different timelines.

---

## Connecting to Software

**Product team.** Focused on user-facing features. Success metrics: user engagement, conversion, revenue, NPS. They answer: "What do users want? What will make them stay? What will make them pay?" They work in sprints. Ship features. A/B test. Iterate. Their customers are end users. Their pressure: ship fast. Meet the roadmap. Hit growth targets.

**Platform team.** Focused on developer productivity, reliability, scalability. Success metrics: deployment frequency, service availability, build time, developer satisfaction. They answer: "How do we make it easier to ship? How do we keep the system up? How do we scale?" Their customers are other engineers. Their pressure: stability. Don't break production. Reduce technical debt.

**The tension.** Product wants fast features. "We need this in 2 weeks." Platform wants stability. "We need to fix the deployment pipeline. Technical debt will slow you down in 3 months." Both are right. Product has user pressure. Platform has system pressure. The conflict is real. The resolution: balance. Explicit trade-offs. "We'll ship this feature, but we commit to platform work next quarter." Or: "We'll do platform work first, then we'll ship faster for 6 months." Staff engineers mediate. They translate. They make the trade-off visible.

---

## Let's Walk Through the Diagram

```
PLATFORM vs PRODUCT
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   PRODUCT TEAM                         PLATFORM TEAM             │
│                                                                  │
│   Builds: User features                Builds: Infrastructure   │
│   • Login, signup                     • CI/CD, deployments      │
│   • Dashboard, reports                • Databases, caches        │
│   • Checkout, payments                • Monitoring, logging      │
│   • Recommendations                  • Auth, API gateway        │
│                                                                  │
│   Customer: End user                  Customer: Product engineers│
│   Metric: Engagement, revenue         Metric: Deploy freq, uptime│
│   Pressure: Ship fast                 Pressure: Don't break      │
│                                                                  │
│   TENSION:                                                       │
│   Product: "We need feature X in 2 weeks"                       │
│   Platform: "We need to fix Y or we'll slow down"               │
│   Both right. Balance required.                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Product builds what users see. Platform builds what product uses. Different customers. Different metrics. The tension: product wants speed, platform wants stability. The resolution: explicit trade-offs. Roadmap includes both. Staff engineers help both sides understand the other. The diagram shows the split. The real work is the dialogue.

---

## Real-World Examples (2-3)

**Netflix.** Product teams build the recommendation algorithms, the UI, the playback experience. Platform teams build Titus (container platform), Spinnaker (deployment), Chaos Engineering tools. When product wants to ship a new feature, they depend on platform for deployment, scaling, monitoring. The platform team's success is measured by: how often can product deploy? How reliable is the system? Product's success: how many users watch? How long? Both need each other.

**Stripe.** Product builds: checkout, subscriptions, invoicing. Platform builds: API infrastructure, rate limiting, idempotency, webhook delivery. Product engineers don't build their own message queues. They use platform services. Platform's job: make it trivial to do the right thing. If product can add idempotency in one line of code, platform succeeded.

**Spotify.** Squad model. Some squads are product—Discover Weekly, Playlists, Social. Some are platform—backend services, data pipeline, developer tools. They had to learn: platform work isn't "less important." It's differently important. They now have "platform allocation" in sprint planning. A percent of capacity for infrastructure. Explicit. Visible.

---

## Let's Think Together

**"Product team says: 'We need this feature in 2 weeks, skip the platform work.' Platform says: 'Technical debt will slow you down in 3 months.' Who's right?"**

Both. Product has real user pressure. Delaying a feature can mean lost revenue, lost users. Platform has real system pressure. Technical debt compounds. In 3 months, every feature takes twice as long. The answer isn't "who's right?" It's "what's the trade-off?" Maybe: ship the feature, but allocate 20% of the next quarter to platform. Maybe: the feature can wait 2 weeks while we fix the deployment pipeline—and then we ship 3 features faster. Maybe: the feature is critical, we ship it, we accept the debt, we plan repayment. Staff engineers don't pick sides. They make the trade-off explicit. They help both sides see the cost. Then they decide together. The goal isn't product OR platform. It's sustainable delivery. Both matter.

---

## What Could Go Wrong? (Mini Disaster Story)

A company had two cultures. Product shipped fast. Platform wanted to refactor. Product won every prioritization battle. "Users need this. Platform work can wait." For 2 years. Then: deployment took 4 hours. Adding a new service took 2 weeks of setup. Every feature required touching shared, fragile code. Velocity collapsed. Product blamed platform. "Why is everything so slow?" Platform said: "We told you. For 2 years." The fix: mandate platform allocation. 30% of engineering time for infrastructure, tooling, debt payoff. No exceptions. Within 6 months, deploy time dropped. Velocity recovered. The lesson: platform work isn't optional. It's deferred. And deferral has interest. Pay it or pay more later. Staff engineers advocate for both. They prevent the collapse before it happens.

---

## Surprising Truth / Fun Fact

Google's Site Reliability Engineering (SRE) model: product teams own their service's reliability. SRE provides tools, practices, consultation. But the product team is on-call. That blurs the line. Product can't ignore platform—they feel the pain of outages. Platform can't ignore product—they need to understand user impact. The ownership model forces collaboration. Not "platform does infrastructure, product does features." But "product owns the service, platform enables." Different from a pure platform team. The trend: embed platform thinking in product. Don't silo. Integrate.

---

## Quick Recap (5 bullets)

- **Product team:** User-facing features. Metrics: engagement, revenue. Customer: end user.
- **Platform team:** Infrastructure, tools. Metrics: deploy frequency, uptime. Customer: engineers.
- **Tension:** Product wants fast features. Platform wants stability. Both right.
- **Balance:** Explicit allocation. 20-30% for platform. Repay technical debt.
- **Staff role:** Mediate. Make trade-offs visible. Don't pick sides—sustain both.

---

## One-Liner to Remember

**Product builds what users see; platform builds what product uses—both essential, different metrics, balance required.**

---

## Next Video

Next: deprecation and migration of APIs. You can't just demolish the old bridge. How to replace systems without breaking 10,000 cars.
