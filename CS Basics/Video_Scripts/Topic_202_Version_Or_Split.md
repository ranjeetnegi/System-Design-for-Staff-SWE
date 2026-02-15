# When to Version, When to Split Services

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Your service started small. Users. Profiles. Auth. Preferences. Now it does everything. New features keep getting crammed in. Do you version? v1, v2, v3? Or do you split? Separate services for different concerns? The wrong choice costs you years. The right one? It scales with your org.

---

## The Story

A restaurant opens with ten items on the menu. Burger, fries, salad. Simple. As they grow, they add more. Pizza. Pasta. Breakfast items. Cocktails. Soon the menu has 200 items. At some point, you don't just update the menu—you SPLIT. Breakfast menu. Lunch menu. Dinner menu. Bar menu. Separate pieces of paper. Different sections of the kitchen. Different waitstaff. The single menu has become four. Not because of versioning—because the responsibility became too broad.

An API or service is the same. It grows. Version when the *contract* changes. Split when the *responsibility* becomes too broad. Version says: "We're evolving the interface." Split says: "We're dividing the work." Two different tools. Two different problems.

---

## Another Way to See It

Think of a library. One building, many sections. Fiction. Nonfiction. Reference. Kids. You could "version" the library—Library 2.0 with a new floor plan. Or you could split—separate buildings for different sections. Versioning is remodeling. Splitting is building new structures. When the single building can't hold the load, or when different sections need different rules, you split. When you're just changing how people find books, you version.

---

## Connecting to Software

**Version** means: same service, new API version. v1, v2, v3. Use when: adding or changing fields, evolving response format, backward-incompatible changes. The service still does the same *thing*—auth, or users, or payments. You're just changing the *interface*.

**Split** means: new service entirely. Use when: the service does too many things (violates single responsibility), different scaling needs, different teams own different features, deploy frequency differs. Splitting is organizational as much as technical. Conway's Law: your org structure becomes your system structure. If two teams own different features in one service, that service will become a bottleneck. Split it.

---

## Let's Walk Through the Diagram

```
VERSION vs SPLIT DECISION TREE
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   Service doing: Users + Auth + Preferences + Address Book       │
│                        │                                         │
│                        ▼                                         │
│   QUESTION: "Is the problem the CONTRACT or the RESPONSIBILITY?" │
│                        │                                         │
│          ┌─────────────┴─────────────┐                           │
│          ▼                           ▼                           │
│   CONTRACT changing           RESPONSIBILITY too broad           │
│   (new fields, new format)     (too many unrelated things)        │
│          │                           │                           │
│          ▼                           ▼                           │
│   VERSION: v1 → v2              SPLIT: 4 services                 │
│   Same service, new API          User Service                     │
│   /v1/users, /v2/users          Auth Service                    │
│                                  Preferences Service             │
│                                  Address Book Service            │
│                                                                  │
│   Version = evolving interface. Split = dividing responsibility. │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Start with a bloated service. Ask the key question: contract or responsibility? If the interface is the problem—new fields, new shapes—version. If the scope is the problem—too many unrelated concerns—split. The diagram makes the decision visible. Staff engineers apply this filter constantly.

---

## Real-World Examples (2-3)

**Example 1: Stripe API.** They version. v1, v2, v3. Same company, same domain. Evolving the payment API contract. They didn't split payments into 50 microservices. They versioned the interface. Contract evolution = version.

**Example 2: Amazon.** They split. Order service. Inventory service. Shipping service. Each does one thing. Different teams. Different scaling. Recommendation service scales with traffic. Inventory service scales with SKU count. Responsibility divided = split. When a new feature doesn't fit an existing service, they don't force it. They ask: does this belong, or does this need a new service? The question is part of their culture. Split when the responsibility explodes—not when the code gets long.

**Example 3: Netflix.** They split their API layer from their backend services. The API gateway is one thing. The microservices behind it are many. Different concerns. Different lifecycles. Split. The gateway handles routing and aggregation. The services handle domain logic. They version the gateway API when the contract changes. They split when a new domain emerges that doesn't fit existing services. Two tools. Used at the right time.

---

## Let's Think Together

"User service handles: profiles, preferences, auth, address book. Should this be one service or four?"

**Consider:** Who owns what? If one team owns all four—maybe one service is fine for now. If auth is owned by platform, preferences by product, address book by shipping—split. Different scaling? Auth needs high throughput, low latency. Address book might be batch-heavy. Split. Different deploy cadence? Auth changes rarely. Preferences change weekly. Split. Conway's Law wins: if the org is split, the system should follow. One service with four owners becomes a coordination nightmare. Split into four. The litmus test: can you deploy one feature without touching the others? If deploying preferences risks breaking auth, you've outgrown the single service. Split before the coupling becomes permanent.

---

## What Could Go Wrong? (Mini Disaster Story)

A company has a "platform" service. It does: user management, billing, notifications, analytics, feature flags. One team. One deploy. One monolith. They version the API—v1, v2—hoping that solves the complexity. It doesn't. Deploying a billing change risks breaking notifications. Scaling for analytics spikes wastes resources on user management. The team is paralyzed. Every change touches everything. The fix? Split. Four services. Four teams. Clear boundaries. They delayed the split for two years. Those two years cost them velocity, talent, and sleep. Version when the contract changes. Split when the responsibility explodes.

---

## Surprising Truth / Fun Fact

Amazon's famous "two-pizza team" rule—teams small enough to be fed by two pizzas—directly influenced their microservice architecture. Small teams can't own giant services. So they split services to match team size. Conway's Law in action: org structure drove system structure. The rule wasn't arbitrary—it was architectural.

---

## Quick Recap (5 bullets)

- **Version** when the contract changes (new fields, new format, breaking changes). Same service, new interface.
- **Split** when responsibility is too broad. Different scaling, different teams, different deploy frequency.
- **Conway's Law:** Org structure → system structure. If teams are split, services should follow.
- **Wrong choice:** Versioning a bloated service doesn't fix bloat. Splitting for contract changes adds complexity.
- **Right question:** "Is the problem the interface or the scope?" Interface → version. Scope → split.

---

## One-Liner to Remember

**Version when the contract evolves. Split when the responsibility explodes. Know which problem you're solving.**

---

## Next Video

Up next: cost as a first-class constraint. Why the architect who ignores the budget designs houses nobody can afford.
