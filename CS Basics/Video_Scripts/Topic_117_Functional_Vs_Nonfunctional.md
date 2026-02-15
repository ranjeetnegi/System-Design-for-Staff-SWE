# Functional vs. Non-Functional Requirements

## Video Length: ~4-5 minutes | Level: Beginner

---

## The Hook (20-30 seconds)

A car. Functional: it drives. It has brakes. It has headlights. It plays music. Non-functional: it goes 0 to 100 in 6 seconds. It survives a crash at 60 kmph. It runs 15 km per liter. It lasts 10 years. Functional = WHAT it does. Non-functional = HOW WELL it does it. Both are essential. A car that drives but crashes at 20 kmph? Useless. In software, we have the same split. And if you ignore non-functional requirements, your system will fail when it matters most. Let me show you.

---

## The Story

Picture two cars. Same features. Both drive. Both have brakes. Both have air conditioning. Car A: 0 to 100 in 6 seconds. Survives a crash. Lasts 15 years. Car B: 0 to 100 in 30 seconds. Crumples at 20 kmph. Dies in 3 years. Which would you buy? Same functional requirements. Different non-functional. The difference between success and failure. The difference between life and death.

Functional requirements are the features. The use cases. The "user can do X" list. User can send a message. User can search products. User can add to cart. User can checkout. These define WHAT the system does. Without them, you don't know what to build. Non-functional requirements are the quality attributes. Performance. Scalability. Availability. Durability. Security. Cost. These define HOW WELL the system does it. Two chat apps can have identical features. One handles 1 million users. The other crashes at 10,000. Same features. Different non-functionals. That's the difference between success and failure. That's the difference between a product that works in demo and a product that works in production.

---

## Another Way to See It

Think of a restaurant. Functional: they serve food. They take orders. They provide menus. Non-functional: food arrives in 15 minutes. Restaurant seats 100 people. Kitchen doesn't catch fire. Ingredients are fresh. You can have a restaurant that serves food (functional) but takes 2 hours (bad non-functional). Or one that's fast, safe, and scalable. Same features. Different quality.

Or a phone. Functional: makes calls, sends texts, takes photos. Non-functional: battery lasts 24 hours, survives drops, loads apps in under 2 seconds, doesn't overheat. Two phones. Same features. One has a 2-hour battery. One explodes when charging. Functional? Yes. Usable? No. Non-functionals decide. Every time.

---

## Connecting to Software

**Functional examples:** User can send message. User can read messages. User can see online status. User can create group. User can search chat history. These are the capabilities. The what.

**Non-functional examples—with detail:** **Latency**—message delivery under 100ms. **Throughput**—10K QPS. **Availability**—99.9% uptime. **Durability**—no data loss. **Security**—end-to-end encryption. **Scalability**—handle 1M concurrent users. **Cost**—under $X per user. **Maintainability**—new feature in 2 weeks. Each type drives different design. "Handle 1M users" means horizontal scaling. "99.9% availability" means redundancy, failover. "No data loss" means durability, replication. "Under 100ms" means caching, optimization. The non-functionals drive the design. Ignore them, and you build something that works in demo but fails in production. In an interview, when you hear "design a chat app," ask: "What's our latency target? Scale? Availability?" The answers change everything.

---

## Let's Walk Through the Diagram

```
    FUNCTIONAL vs NON-FUNCTIONAL

    ┌────────────────────────────┐    ┌────────────────────────────┐
    │   FUNCTIONAL               │    │   NON-FUNCTIONAL            │
    │   (WHAT it does)           │    │   (HOW WELL it does it)    │
    │                             │    │                             │
    │   • Send message            │    │   • Latency: < 100ms        │
    │   • Read messages           │    │   • Throughput: 10K QPS     │
    │   • Online status           │    │   • Availability: 99.9%     │
    │   • Create group            │    │   • Durability: no data loss │
    │   • Search history          │    │   • Security: encrypted      │
    │                             │    │   • Cost: $X per user       │
    └────────────────────────────┘    └────────────────────────────┘
                    │                                   │
                    └───────────┬───────────────────────┘
                                │
                    Both define the system.
                    Miss one = wrong build.
```

Two columns. Two sides of the same coin. Functional: the features. Non-functional: the quality. You need both. Design for both.

---

## Real-World Examples (2-3)

**Example 1: Chat app.** Functional: send, read, group, search. Non-functional: real-time (< 100ms), 1B users, 99.99% uptime, messages never lost. WhatsApp's non-functionals—scale, reliability—are why their architecture is complex. Same features, simpler non-functionals = simpler design. Ask: what are the non-functionals? They dictate the architecture.

**Example 2: Payment system.** Functional: charge card, refund, subscription. Non-functional: correct (no double charge), fast (< 2 sec), compliant (PCI), auditable. The non-functionals here are life-or-death. Wrong charge? Lawsuit. Slow? Lost sale. Non-functionals drive the design. They're not nice-to-have. They're must-have.

**Example 3: Search engine.** Functional: user types query, gets results. Non-functional: results in < 200ms, 10B documents indexed, relevant ranking. Google's non-functionals—speed, scale—define their infrastructure. The feature is simple. The non-functionals are not. Same pattern everywhere.

---

## Let's Think Together

Chat app. Functional: send message, read messages, show online status. What are the non-functional requirements? Push yourself. List them.

Consider: **Latency**—how fast must messages arrive? Real-time = < 100ms. **Scale**—how many users? 1K vs 1B changes everything. **Availability**—99.9%? 99.99%? **Durability**—can we lose a message? Never? **Ordering**—must messages appear in order? **Persistence**—how long do we keep history? 7 days? Forever? **Security**—encrypted? **Cost**—what's the budget? **Consistency**—eventual or strong? Each non-functional narrows the design. Don't skip them. They're not "nice to have." They're "will this work in production?" In an interview, after listing functional requirements, say: "Now for non-functionals. What's our latency budget? Scale? Availability?" Show you think about both. Show you think about production.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup builds a social app. They nail the functional requirements. Post. Like. Comment. Share. All working. Beautiful UI. Smooth animations. Launch day. Viral. 500,000 users in one hour. The app crashes. Why? They never specified non-functionals. No scale target. No load testing. The database couldn't handle the connections. The cache was too small. Everything timed out. They had to take the app offline. Fix it. Relaunch. Lost momentum. Lost users. Lost investors. The features were perfect. The system wasn't. Non-functional requirements aren't optional. They're the difference between "it works" and "it works when it matters." They're the difference between demo and production. Specify them. Test for them. Design for them.

---

## Surprising Truth / Fun Fact

In 1999, NASA lost a $125 million Mars orbiter because of a units mismatch. One team used metric. Another used imperial. The orbiter burned up in the Martian atmosphere. That's a non-functional requirement: consistency. Correctness. They had the functional requirement: "Orbit Mars." They failed on a non-functional: "Use consistent units." Non-functionals kill projects. Literally. In software, we don't often kill people. But we lose money. Reputation. Users. Same lesson. Both matter. Functional tells you what. Non-functional tells you how well. Miss either. Pay the price.

---

## Quick Recap (5 bullets)

- **Functional** = WHAT the system does (features, use cases). **Non-functional** = HOW WELL (performance, scale, reliability).
- **Both are essential.** A system with perfect features that crashes at scale is useless.
- **Non-functionals drive architecture.** Scale, latency, availability—they define your design choices.
- **Examples**: latency, throughput, availability, durability, security, cost.
- **Always specify both** before designing. Missing non-functionals = production failure.

---

## One-Liner to Remember

**Functional: it drives. Non-functional: it survives a crash. You need both.**

---

## Next Video

Next: **Capacity estimation.** Users, QPS, storage. The wedding catering formula. How much food? How much data? Let's do the math.
