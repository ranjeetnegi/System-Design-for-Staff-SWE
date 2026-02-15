# APIs as Long-Term Contracts

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

You build an API. You ship it. A hundred apps integrate. Then a thousand. Then ten thousand. Now product wants to change a field name. Simple, right? Wrong. Ten thousand developers wrote code that depends on that field. Change it and you break them all. An API isn't code—it's a promise. And that promise lasts years.

---

## The Story

You build a road. A wide, well-designed highway. Ten thousand houses connect to it. Driveways. Garages. Delivery routes. Everything depends on that road's width, its exits, its lanes. Now someone says: "Let's narrow it. Add a toll booth. Change the exit numbers." Sounds reasonable. But ten thousand homes have garages sized for the current road. Driveways angled for current exits. Delivery trucks scheduled around current traffic patterns. Changing the road breaks everything downstream.

An API is the same. Once published, thousands of apps depend on it. Every field. Every endpoint. Every response format. It's a CONTRACT. Not a suggestion. Not a draft. A contract. Breaking it breaks your customers. Staff engineers design APIs like they're building infrastructure that will last decades.

---

## Another Way to See It

Think of an API as a handshake. You're not just exchanging data—you're making a promise. "I will return this shape. I will support this endpoint. I will behave this way." The moment someone integrates, that handshake becomes binding. Rename a field? You've broken the handshake. Remove an endpoint? You've broken the handshake. Change a type? Broken. At scale, an API is less like code and more like a treaty between nations. Treaties don't get rewritten casually.

---

## Connecting to Software

APIs are public promises. Internal or external—someone depends on them. Changing field names, removing endpoints, changing types: these are breaking changes. They break your customers. They break your internal teams. They create support tickets, angry developers, and lost trust.

**Backward compatibility** is the rule: always ADD, never remove. Want a new field? Add it as optional. Old clients ignore it. New clients use it. Want to rename something? Add an alias. Support both. Deprecate the old one. Give clients time to migrate. Removing a field without notice? That's not engineering—that's sabotage.

**Semantic versioning** for APIs: v1, v2, v3. When you make breaking changes, release a new version. Keep v1 running. Announce deprecation. Give six months. Then sunset. The deprecation lifecycle: announce, warn, sunset. Never break in place.

---

## Let's Walk Through the Diagram

```
THE API CONTRACT LIFECYCLE
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   PUBLISHED API ─────────────────────────────────────────────►  │
│        │                                                         │
│        │  Thousands of clients depend on:                        │
│        │  • Field names (user_id, not userId)                    │
│        │  • Response shape (array vs object)                     │
│        │  • Endpoint paths (/v1/users not /users)                │
│        │  • Status codes (200 vs 201)                            │
│        │                                                         │
│        ▼                                                         │
│   CHANGE REQUESTED: "Rename age → date_of_birth"                 │
│        │                                                         │
│        ├─ BREAKING: Remove age, add date_of_birth  ❌             │
│        │                                                         │
│        └─ SAFE: Add date_of_birth (optional)     ✅              │
│           Keep age (deprecated). Sunset in 12 months.            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

The diagram shows the tension. You publish. Dependencies grow. Change requests arrive. The breaking path—remove and replace—destroys trust. The safe path—add, deprecate, sunset—preserves the contract. Every field you add is a commitment. Every field you remove is a breach. Design accordingly.

---

## Real-World Examples (2-3)

**Example 1: Stripe.** Their API has evolved for over a decade. How? They never remove. They add. They deprecate with long lead times. When they introduced idempotency keys, they didn't change existing behavior—they added optional support. Old integrations kept working. New integrations got the benefit.

**Example 2: Twitter API v1 to v2.** The migration took years. Why? Millions of apps depended on v1. They couldn't flip a switch. v2 launched. v1 stayed. Developers migrated at their pace. Breaking v1 overnight would have destroyed ecosystems.

**Example 3: AWS.** They're legendary for backward compatibility. S3's API from 2006 still works. New features get new parameters. Old parameters stay. It's not pretty—it's durable. That's the trade-off. Engineers joining AWS learn early: never break a published API. The bar for deprecation is high. The bar for removal is even higher. They treat APIs like legal contracts—because to their customers, that's exactly what they are.

---

## Let's Think Together

"Your API returns age as an integer. Product needs date_of_birth instead. Five hundred clients use age. How do you migrate?"

**Option A:** Remove age, add date_of_birth. Breaks 500 clients. Bad.

**Option B:** Add date_of_birth as optional. Keep age. Deprecate age with a header: `X-Deprecation: age field deprecated, use date_of_birth by 2026`. Give clients 12–18 months. Monitor adoption. Sunset age when usage drops below 1%. This is the Staff answer: backward compatible migration with a clear path.

The key: you never break in place. You extend. You signal. You sunset with notice. Migration is a process, not an event.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup ships an API. Fast growth. Hundreds of integrations. One day, an engineer "cleans up" the code. Renames `created_at` to `createdAt` for consistency. Ships it. Within hours: support floods. "Our app is broken." "The API returns different field names." The engineer reverts. But the damage is done. Trust eroded. Blog posts written. "Don't integrate with Company X—they break things." The fix took one commit. The reputation repair took years. At Staff level, you never touch a published field without a migration plan.

---

## Surprising Truth / Fun Fact

Google's AdWords API has endpoints that have been deprecated for over five years—and they're still running. Why? Enterprise customers move slowly. Some have contracts that specify exact API versions. Google keeps the lights on. That's what long-term contracts mean. When you publish an API, you're committing to maintain it. Possibly forever.

---

## Quick Recap (5 bullets)

- **APIs are contracts.** Every field, endpoint, and format is a promise. Breaking it breaks your customers.
- **Backward compatibility:** Always ADD, never remove. New optional fields = safe. Renaming = breaking.
- **Semantic versioning:** v1, v2 for breaking changes. Deprecation lifecycle: announce, warn, sunset.
- **Design for decades.** Internal or external—someone depends on it. Treat it like infrastructure.
- **Migration is a process.** Add new, deprecate old, give time, sunset when safe.

---

## One-Liner to Remember

**An API is a long-term contract. Add, never remove. Deprecate with notice. Design like it will outlive you.**

---

## Next Video

Next up: when to version your API versus when to split it into separate services. The restaurant menu analogy is coming.
