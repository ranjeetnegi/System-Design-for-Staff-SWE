# Deprecation and Migration of APIs

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A city decides to replace an old bridge with a new one. They can't just demolish the old bridge—10,000 cars use it every day. So they: build the new bridge next to the old one. Announce: "Old bridge closing in 6 months." Add signs redirecting to the new bridge. Gradually close lanes on the old bridge. After 6 months, when traffic has shifted, they demolish the old one. API deprecation works the same way. You don't flip a switch. You migrate. You give time. You support both until the old one is empty. Then you remove. Anything else is chaos.

---

## The Story

Imagine a library. They're moving to a new building. They don't close the old library on Friday and open the new one on Monday. They run both. They put up signs: "New library opening. Same books. Better space." They give borrowers time to learn the new location. They move books gradually. Some shelves stay in the old building during the transition. Eventually, the old building is empty. They close it. API deprecation is the same. You don't break existing users. You add the new API. You tell users: "Use the new one. The old one will stop working on this date." You give them months. You help them migrate. When traffic to the old API is near zero, you turn it off. Graceful. Predictable. Professional.

---

## Another Way to See It

Think of a phone company retiring 3G. They don't switch it off tomorrow. They announce: "3G will be discontinued in 2025." That gives everyone 2-3 years. Phone makers stop selling 3G-only phones. Users upgrade. Carriers migrate towers. When the day comes, few users are affected. The ones who didn't upgrade? They had years of warning. API deprecation: same principle. Long lead time. Clear communication. No surprises.

---

## Connecting to Software

**Deprecation lifecycle.** Five stages. Don't skip them.

**(1) Announce.** 6+ months ahead. Blog post. Email to API consumers. "We're deprecating v1. Use v2. Sunset date: [date]." Give people time. 6 months minimum for external APIs. 3 months for internal. Large enterprises need 12-24 months.

**(2) Warn.** Add deprecation headers to responses. `X-API-Deprecation: true`. `X-API-Sunset: 2026-06-01`. `X-API-Replacement: /v2/users`. Every response reminds consumers. Log who's still using the old API. Reach out to heavy users. Help them migrate.

**(3) Sunset date.** Block new consumers. "New integrations must use v2." Existing consumers keep working. But no new signups for v1. Reduces the migration surface over time.

**(4) Migration support.** Documentation. Migration guides. Code samples. Support channel. Tools. "Here's how your v1 call maps to v2." Make migration easy. The harder you make it, the longer they stay on v1.

**(5) Remove.** When v1 traffic drops below a threshold—say 0.1%—turn it off. Return 410 Gone. Or redirect to deprecation notice. Archive the old code. Done.

**Backward compatibility during migration.** Old API and new API both work. Old returns deprecation warnings. New is the recommended path. You maintain both. That's the cost. Two code paths. Two test suites. Until sunset. It's temporary. Plan for it.

**Version management.** v1 (deprecated), v2 (current). Keep v1 running. Don't remove fields from v1. Add to v2. When you need breaking changes, create v3. v2 gets deprecated. v3 is current. Linear progression. Never break in place.

---

## Let's Walk Through the Diagram

```
API DEPRECATION LIFECYCLE
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   Timeline:                                                      │
│                                                                  │
│   Month 0      Month 3      Month 6      Month 9      Month 12   │
│   |            |            |            |            |         │
│   ANNOUNCE     WARN         SUNSET       MIGRATE      REMOVE    │
│   v2 ready     Headers      No new       Support      v1 off    │
│   v1 deprecated  in response  v1 users    existing    410 Gone   │
│                                                                  │
│   BOTH RUN SIMULTANEOUSLY                                        │
│                                                                  │
│   [v1 API] ──► Deprecation header ◄── Still works               │
│   [v2 API] ──► Recommended          ◄── New consumers only     │
│                                                                  │
│   v1 traffic ─────────────────────────► 0%                       │
│   Then: remove.                                                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Announce first. Give time. Add warnings to every response. Set a sunset date for new consumers. Support migration. Monitor traffic. When v1 drops to zero, remove. The diagram shows the runway. Deprecation is a process. Not an event. Staff engineers plan the timeline. They never break without warning.

---

## Real-World Examples (2-3)

**Stripe.** They've deprecated many API versions. Each gets years of support. They add `Stripe-Version` header. Old versions keep working. New features go to new versions. When they sunset a version, they give 12+ months notice. Enterprise customers with contracts get even more. They've built a business on trust. Breaking without notice would destroy that.

**Twitter API v1 to v2.** v1 deprecated. v2 launched. Both ran for years. Developers migrated gradually. Twitter provided migration guides. Many endpoints had direct v1-to-v2 mapping. The transition was messy in places—v2 had different rate limits, different data shapes—but they didn't shut off v1 overnight. They gave time. That's the standard.

**AWS.** Legendary for never breaking. When they need to change behavior, they add new parameters. Old parameters stay. "We're adding a new optional parameter. Default behavior unchanged." Deprecation is rare. When they do it, it's with years of notice. Their philosophy: once published, forever supported. Or at least, a very long time.

---

## Let's Think Together

**"Your API v1 has 500 active consumers. You want to remove a field. How do you migrate them safely?"**

Don't remove. Add a deprecation notice. "Field X is deprecated. Use field Y. Sunset: 12 months." Make Y available. Document the mapping. Email the 500 consumers. Identify the top 50 by traffic. Reach out personally. Offer migration support. Add monitoring: who's still using field X? As usage drops, you'll see. Maybe 50 consumers never migrate. Chase them. Maybe 10 have abandoned the integration. Remove those from the count. When you're down to 5 holdouts, consider extended sunset or force migration. The key: never remove without a deprecation period. Never remove without monitoring who's affected. Staff engineers treat consumers as customers. You don't surprise them.

---

## What Could Go Wrong? (Mini Disaster Story)

A company needed to "clean up" their API. Removed a deprecated field. No notice. Just removed. "We sent an email 2 years ago." The email went to a distribution list that half the teams didn't use. One critical partner—a payment processor—had built their integration 3 years ago. They never got the email. Or they ignored it. The field removal triggered a bug in their system. Payments failed. For hours. The partner escalated. Angry calls. The company had to emergency-patch. Re-add the field. Apologize. The "cleanup" cost more than maintaining the field forever. The lesson: deprecation without confirmed migration is dangerous. Track who uses what. Verify before you remove. "We sent an email" is not enough. Staff engineers verify. They don't assume.

---

## Surprising Truth / Fun Fact

Many companies run deprecated API versions for a decade or more. Not because they want to. Because they have to. Enterprise contracts. Government clients. Legacy systems that no one maintains but someone still uses. When you deprecate, plan for the long tail. Some consumers will migrate in a month. Some will take 5 years. Or never. Have a policy: "We support deprecated versions for X years after sunset. After that, best effort." And budget for it. Deprecation has ongoing cost. Old code paths. Old documentation. Old support. It's not free. Plan for it.

---

## Quick Recap (5 bullets)

- **Deprecation lifecycle:** Announce (6+ months) → Warn (headers) → Sunset (block new) → Migrate (support) → Remove.
- **Backward compatibility:** Old and new API run simultaneously. Old returns deprecation warnings.
- **Version management:** v1 deprecated, v2 current. Never break in place.
- **Migration support:** Documentation, guides, tools. Make migration easy.
- **Verify before remove:** Track who uses what. Don't assume they got the email.

---

## One-Liner to Remember

**API deprecation is bridge replacement—build new, announce closure, redirect traffic, support both until old is empty, then remove.**

---

## Next Video

Next: what interviewers probe at Staff level. Same question as L5. Different bar. How they test depth.
