# When to Split a Monolith into Services

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A family-run restaurant. Dad cooks. Mom takes orders. Son washes dishes. Works great for 20 customers a night. Everyone does their part. Then they go viral on Instagram. A food blogger posts. 200 customers the next night. Dad can't cook fast enough. But Mom and Son are busy too—they can't help Dad because they don't know cooking. Everything is entangled. To scale, they hire a separate cooking team, a separate service team, a separate cleaning team. Each team works independently. That's splitting a monolith into services. When do you do it? And when do you NOT? Let me show you.

---

## The Story

Picture the restaurant. Small. Cozy. Dad knows every recipe. Mom knows every customer. Son knows every plate. One unit. One flow. Orders come in. Dad cooks. Son cleans. Works. Then 200 customers. Dad is overwhelmed. The kitchen is chaos. Mom could help—but she doesn't cook. Son could help—but he doesn't cook. The skills are siloed. The work is coupled. Dad is the bottleneck. The only one who can cook. They need more cooking capacity. But "more Dad" isn't an option. They need a cooking team. Separate. Specialized. Scalable. They hire chefs. Now the cooking team can scale independently. The service team scales separately. The cleaning team scales separately. Each unit has its own capacity. Each can grow without blocking the others. That's the monolith-to-services transition. One entangled unit becomes many independent units. Each does one thing. Each scales on its own.

A **monolith** in software is one codebase. One deployment. Everything together. User logic, payment logic, notifications, search—all in one app. Simple. Fast for small teams. Easy to debug. One place to look. Deploy once. It works. Until it doesn't.

**When to split:** Team too big (10+ engineers), deploy too long, one bug crashes all, different scaling needs. You've outgrown the monolith.

**When NOT to split:** Small team, early stage, unclear boundaries. Premature microservices = premature complexity. Conway's Law: systems mirror team structure. Small team? Monolith fits. Don't split too early. Split when it hurts not to.

---

## Another Way to See It

Think of a general store. One building. Groceries, hardware, pharmacy. Everything in one place. Simple. For a small town, it works. For a city? You need separate stores. Grocery store. Hardware store. Pharmacy. Each specialized. Each scales independently. The general store was a monolith. The specialized stores are services.

Or an orchestra. One group, one conductor. For a small piece, fine. For a symphony? Different sections—strings, brass, percussion. Each practiced separately. Each comes together for the performance. Same idea. Scale forces specialization. Specialization forces separation.

---

## Connecting to Software

**Monolith pros:** Simple. One deploy. One codebase. Easy to trace. Easy to refactor across modules. No network latency between "services." No distributed tracing. No service mesh. **Monolith cons:** Can't scale parts independently. One bug can take down everything. Deploy gets slow. Team contention. Big codebase, hard to navigate. One change requires full deployment.

**Microservices pros:** Scale independently. Deploy independently. Team ownership. Fault isolation—one service down, others run. **Microservices cons:** Complexity. Network calls. Distributed tracing. Eventual consistency. More infra. More moving parts. Debugging across services is hard.

**Extract first:** The part that has clear boundaries. The part that needs different scaling. The part that different teams own. Often: payment, notifications, search. User core? Maybe stay in monolith longer. Depends. **Conway's Law:** Your architecture will reflect your team structure. One team? Monolith works. Multiple teams with clear ownership? Services make sense. Split along team boundaries. Not random. Strategic.

---

## Let's Walk Through the Diagram

```
    MONOLITH                          SERVICES

    ┌─────────────────────┐           ┌──────────┐  ┌──────────┐
    │                     │           │  User    │  │ Payment  │
    │  User │ Payment │   │    →      │  Service │  │ Service  │
    │  Notif│ Search  │   │           └────┬─────┘  └────┬─────┘
    │                     │                │              │
    │  All in one app     │           ┌────┴─────┐  ┌────┴─────┐
    │  One deploy         │           │  Notif   │  │  Search  │
    └─────────────────────┘           │  Service │  │ Service  │
                                      └──────────┘  └──────────┘
    Simple. Entangled.                 Complex. Decoupled.
    Scale together.                    Scale independently.
```

One becomes many. Each service: own data, own team, own deploy. Each can scale. Each can fail independently. But complexity grows. Trade-offs. Always.

---

## Real-World Examples (2-3)

**Example 1: Amazon.** Started as a monolith. As they grew, they moved to service-oriented architecture. "Two-pizza teams"—each team owns services small enough to be fed by two pizzas. Order service, cart service, recommendation service—each separate. Scale and ownership drove the split. Conway's Law in action.

**Example 2: Netflix.** Started monolith. Scaling issues. They moved to microservices. Now hundreds of services. Each does one thing. Chaos engineering—they test failure of individual services. The split enabled that. Fault isolation. Independent scaling. They can kill a service and the rest runs.

**Example 3: Shopify.** They stayed largely monolithic for years. "Majestic monolith." They modularized internally—bounded contexts—but didn't split into services until they had to. When they did, they extracted high-value, clear-boundary services first. Not "microservices for the sake of it." Split when it hurt not to. Smart.

---

## Let's Think Together

Your monolith has: user service, payment, notification, search. Which would you extract FIRST and why?

Payment. Why? (1) Clear boundary—payments are isolated. (2) Different scaling—payment might need higher reliability, different compliance. (3) Different team—often a dedicated payments team. (4) Fault isolation—if payment has a bug, you don't want it taking down the whole app. (5) Compliance—PCI, etc. Payment in its own service makes auditing easier. Notifications could be second—often async, easy to decouple. Search third—different tech stack sometimes. User core last—it's the heart, hardest to extract, most coupling. Extract from the edges. Work toward the center. One service at a time. Don't big-bang.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup reads about microservices. "That's what the big companies do." They split their 3-person team's monolith into 15 services. Now every feature touches 5 services. Deployment: 5 pipelines. Debugging: trace across 5 networks. A simple bug fix takes a week. They could have shipped 10 features in that time. They're stuck in distributed systems complexity with startup resources. Three people. Fifteen services. Network failures. Version mismatches. Deployment coordination. Disaster. The lesson: don't split because it's trendy. Split when the monolith hurts. When the team is big. When deploy is slow. When you need independent scaling. Premature microservices is a trap. Monolith first. Split when you have a reason. A good reason.

---

## Surprising Truth / Fun Fact

Amazon's migration from monolith to services took years. They didn't flip a switch. They strangled the monolith—extracted one service at a time, routed traffic gradually, retired the old code. "Strangler fig" pattern. You don't have to do it all at once. Extract one service. Prove it works. Extract another. Incremental. Safer. Most companies that "went microservices" did it this way. Big bang rewrites fail. Gradual extraction wins. Take your time. One service. Then the next.

---

## Quick Recap (5 bullets)

- **Monolith** = one codebase, one deploy. Simple. Good for small teams, early stage.
- **Split when:** team too big, deploy too slow, one bug crashes all, different scaling needs.
- **Don't split when:** small team, early stage, unclear boundaries. Premature = complexity.
- **Extract first:** clear boundaries, different scaling, different ownership. Often: payment, notifications.
- **Strangler pattern:** extract incrementally. One service at a time. Don't big-bang rewrite.

---

## One-Liner to Remember

**Split when it hurts not to. Not when it's fashionable.**

---

## Next Video

Next: **Request flow.** From user tap to database and back. One tap. Ten steps. Let's trace the journey.
