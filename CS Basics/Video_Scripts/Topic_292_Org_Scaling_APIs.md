# Organizational Scaling: APIs and Ownership

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A small startup. Five people. Everyone knows everything. "Hey, can you change the login flow?" "Sure, I'll just..." Communication is easy. Decisions are fast. They grow to 50. Then 500. Now what? You can't have 500 people making decisions about one codebase. You can't have 500 people in the same meeting. You SPLIT. Each team owns a service. Teams communicate through APIs, not hallway conversations. Conway's Law: your system architecture mirrors your organization structure. If you want better systems, you might need to change how teams are organized. And if you want teams to scale, you need APIs as the contract between them.

---

## The Story

Imagine a small village. Ten houses. Everyone knows everyone. Need milk? Walk to the neighbor. Need help? Yell. It works. The village grows. 100 houses. 1000. You can't yell anymore. You need streets. Addresses. Mail service. Formal ways to request things. "Send a letter to House 42." The letter has a format. An address. A return address. You don't walk over. You use the system.

Software scales the same way. Five engineers: they talk. They change code. Fast. Five hundred engineers: they need contracts. APIs. "My service exposes this endpoint. Your service calls it. Here's the format." No need to know internal implementation. Just the contract. The API is the envelope. The address. The formal handshake. Without it, chaos. With it, scale.

---

## Another Way to See It

Think of a restaurant kitchen. One chef: they do everything. Order comes in, they cook, they plate, they serve. Add chefs. Now you need stations. Grill. Fryer. Salads. Each station has an interface: "Grill receives raw meat, returns cooked meat." The salad station doesn't need to know how the grill works. Just the handoff. Same for services. The Order Service doesn't need to know how the User Service stores passwords. Just: "Give me user by ID. I get back name, email." The API is the handoff. Clean boundaries. Scalable teams.

---

## Connecting to Software

**Conway's Law.** Melvin Conway said it in 1967: "Organizations design systems that mirror their communication structure." Two teams that don't talk? You get two separate systems. Two teams that collaborate heavily? You get a tightly coupled system. The org structure and the system architecture are linked. You can't separate them. Want microservices? You need small teams with clear ownership. Want a monolith? You need a team that can own it. The architecture follows the org. Or the org follows the architecture. They align. Always.

**API as contract.** Team A builds the User Service. They expose an API. "GET /users/{id}, POST /users, PATCH /users/{id}." Team B builds the Order Service. They call the User API. They don't have access to the User database. They don't deploy the User Service. They just call the API. The contract is: "I will return this shape. I will accept this input." Both teams agree. The API is the boundary. Loose coupling. Team A can rewrite their entire database. As long as the API doesn't change, Team B doesn't care.

**Ownership.** Each team owns their service end-to-end. Build. Deploy. Operate. On-call. When the User Service breaks at 3 AM, the User team gets paged. Not the Order team. Full ownership means accountability. No "that's not my job." It's your service. Your responsibility. Ownership scales. When you have 50 services, you have 50 owners. Or teams of owners. No single bottleneck. No "who maintains this?" confusion.

---

## Let's Walk Through the Diagram

```
ORGANIZATIONAL SCALING: TEAMS AND APIS
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   SMALL ORG (5 people)              LARGE ORG (500 people)      │
│                                                                  │
│   [Everyone] ──► Monolith           [Team A] ──► [User API]    │
│   One codebase.                     [Team B] ──► [Order API]   │
│   Hallway convos.                   [Team C] ──► [Payment API] │
│   Fast. Doesn't scale.              APIs = contracts.           │
│                                     Teams own services.          │
│                                                                  │
│   CONWAY'S LAW:                                                    │
│   Org structure  ◄──►  System architecture                       │
│   2 teams       →      2 services                                │
│   Siloed teams  →      Loosely coupled services                  │
│                                                                  │
│   API = Handoff between teams                                    │
│   Ownership = Build + Deploy + Operate + On-call                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Small org—one monolith, everyone in the same room. Large org—teams own services, APIs are the handoffs. Conway's Law: the system mirrors the org. APIs define the boundaries. Ownership defines responsibility. When you scale the org, you scale through clear contracts and clear ownership. No ambiguity.

---

## Real-World Examples (2-3)

**Amazon.** Two-pizza teams. Small enough to feed with two pizzas. Each team owns a service. They communicate through APIs. The infamous "API mandate" from Jeff Bezos: all teams must expose their data and functionality through APIs. No backdoors. No shared databases. APIs only. That forced the architecture. Now AWS has hundreds of services. Each owned. Each with an API. The org structure created the system structure.

**Netflix.** Microservices. Hundreds of them. Each team owns a few. The playback team doesn't touch the billing service. They call its API. When they need a change, they request it. Or they work with the billing team. The API is the contract. Ownership is clear. Scaling to thousands of engineers required this. One monolith would have collapsed under the coordination cost.

**Spotify.** Squads and tribes. Squads own features. Tribes own areas. APIs between squads. They famously struggled with ownership as they grew. Too many squads touching the same code. They had to reorganize. Redraw boundaries. New APIs. The lesson: org and architecture evolve together. You refine both.

---

## Let's Think Together

**"Company has 3 teams sharing one monolithic codebase. Deploys are slow. Conflicts constant. How do you split?"**

First: identify natural boundaries. By domain. User team owns user-related code. Order team owns order-related code. Then: define APIs between them. User service exposes: get user, update user. Order service calls user API. Doesn't touch user database. Extract gradually. Strangler fig pattern. New service handles new traffic. Old code gets deprecated. Don't big-bang rewrite. Incremental extraction. One service at a time. The split follows team boundaries. Conway's Law in reverse: you want better boundaries, so you create teams with clear ownership. The code follows.

---

## What Could Go Wrong? (Mini Disaster Story)

A company grew fast. Hired 10 teams. All worked on the same monolith. Deploy day: everyone pushed to main. Merge conflicts. "Who changed this file?" "I need that feature for my release." "Your change broke my tests." Deploys took 2 weeks. Coordination meetings: 20 people. Nothing shipped. They tried to fix it with process. More approval layers. More meetings. It got worse. The fix: split the monolith. Each team got a service. Defined APIs. Owned their deployment. No more shared codebase. Deploys: daily. Per team. Coordination: through API contracts. The architecture change required the org change. They did both. Took a year. Painful. Necessary. The alternative was paralysis.

---

## Surprising Truth / Fun Fact

Amazon's API-first mandate wasn't just technical. It was organizational. Bezos said: if you want to use another team's data, you use their API. No exceptions. No "I'll just add a quick database query." That forced teams to think in terms of services and contracts. The technical constraint created organizational clarity. Sometimes the best org design comes from a technical rule. APIs aren't just for machines. They're for teams.

---

## Quick Recap (5 bullets)

- **Conway's Law:** System architecture mirrors org structure. Two teams → two services.
- **API as contract:** Teams communicate through APIs. Loose coupling. Clear boundaries.
- **Ownership:** Each team owns their service: build, deploy, operate, on-call.
- **Scaling requires splitting:** Monolith + 500 people = coordination chaos. Services + APIs = scale.
- **Split by domain:** Natural boundaries. User, Order, Payment. APIs between them.

---

## One-Liner to Remember

**APIs are the contracts between teams; ownership is the accountability—scale the org by scaling through clear boundaries.**

---

## Next Video

Next: platform vs product teams. Who builds the factory? Who builds the car? The tension and the balance.
