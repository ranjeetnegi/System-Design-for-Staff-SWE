# Graceful Degradation: What to Shed First

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A sinking ship. You can't save everything. You throw heavy cargo overboard first. Non-essential. Keep the lifeboats. The food. The people. The ship stays afloat longer. In software: the system is overloaded. What do you drop first? Recommendation engine? Nice to have. Payment processing? Never. Graceful degradation—intentionally reducing functionality to keep the core alive. Decide before you sink.

---

## The Story

Traffic spike. Black Friday. Viral moment. Your system is at 150% capacity. Every component is sweating. What happens? Option 1: try to do everything. Nothing works. Timeouts. Errors. Total failure. Option 2: shed non-critical features. Recommendations? Gone. Personalized homepage? Static. Search suggestions? Disabled. But checkout works. Login works. Core flows work. You've degraded. Gracefully. Some users get less. All users get something. Better than nobody getting anything.

The key is priority. Before the crisis. Identify critical vs. non-critical. Payment. Login. Core transaction. Critical. Recommendations. Trending. "People also bought." Non-critical. When overloaded, drop non-critical first. Feature flags. Circuit breakers. Fallbacks. Serve cached data. Return static content. Reduce image quality. Do whatever keeps the core alive.

---

## Another Way to See It

Think of a hospital in a disaster. Triage. Critical patients first. Life-threatening. Others wait. Some get minimal care. The hospital can't save everyone perfectly. It saves who it can. Graceful degradation. Prioritize. Some get less. System survives.

Or a news site during a major event. Homepage normally has personalized widgets, ads, recommendations. Traffic 10x. Strip it down. Just the article. Text. One image. Fast. Loads. Everyone gets the news. Features come back when traffic eases. Degrade to survive. Restore when stable.

---

## Connecting to Software

**Techniques:** Feature flags to disable non-critical features. Serve cached or stale data instead of computing fresh. Return static fallback—"recommendations temporarily unavailable." Reduce image quality. Disable search autocomplete. Simpler API responses. Fewer database queries. Trade richness for speed. Trade features for availability.

**Priority matrix:** Before launch, classify. P0: payment, auth, core flows. Never drop. P1: search, cart, key features. Drop only in extreme overload. P2: recommendations, personalization. First to go. P3: analytics, non-critical. Shed early. Document. Practice. When the moment comes, you know what to do.

**Communication.** When you degrade, tell the user. "Recommendations are temporarily simplified." "Some features may be slower." Don't leave them guessing. A clear message beats confusion. And it sets expectations. Graceful degradation isn't just technical. It's UX. How you communicate the reduced experience matters as much as the reduction itself.

---

## Let's Walk Through the Diagram

```
    NORMAL LOAD                    OVERLOAD - GRACEFUL DEGRADATION

    [Full Features]                 [Core Only]
    ✓ Recommendations              ✗ Recommendations (disabled)
    ✓ Personalization               ✗ Personalization (static fallback)
    ✓ High-res images               ✓ Low-res images
    ✓ Search + suggestions          ✓ Search (no suggestions)
    ✓ Payment                       ✓ Payment
    ✓ Login                         ✓ Login

    Everything works.               Core works. Extras shed.
                                          Survival. ✓
```

Left: full experience. Right: overload. Non-critical shed. Core survives. Users get less. Users get something.

---

## Real-World Examples (2-3)

**Example 1: Netflix during traffic spike.** Video streaming: never touched. That's the product. Recommendations? Can degrade. "Because you watched X" — show cached, or generic. Artwork? Lower resolution. Thumbnails? Simplified. Video plays. Always. Everything else can bend. Documented. Practiced. Chaos tested.

**Example 2: Twitter during major events.** Tweet timeline: critical. Loads. Images might be delayed. Or lower quality. "Trending" might be cached. Or disabled. Reply. Post. See timeline. Core works. Extras degraded. Millions get the experience. Degraded but functional.

**Example 3: Amazon Prime Day.** Product listing: works. Add to cart: works. Checkout: works. Recommendations? "Frequently bought together" might be simplified. "Customers also viewed" might load slowly or not at all. They prioritize. Core commerce. Everything else is secondary. Documented in their architecture. Known. Practiced.

---

## Let's Think Together

**Netflix during a traffic spike: what features do they degrade?**

Hint: not video streaming. That's the product. Recommendations can degrade—show popular titles, cached. Artwork can be lower resolution. "Continue watching" might be simplified. Personalization might fall back to generic. The goal: you hit play. Video plays. Everything else is nice-to-have. When overloaded, nice-to-have goes first. Core stays. Always.

---

## What Could Go Wrong? (Mini Disaster Story)

A team designed graceful degradation. Documented. "In overload, disable recommendations." Crisis hit. Team panicked. Disabled the wrong service. Disabled the one that handled session validation. Users got logged out. Chaos. Worse than before. Lesson: degradation must be tested. In staging. In chaos drills. Know exactly what to disable. Verify. Wrong thing disabled = worse outage. Practice. Document. Test. Before the real thing.

---

## Surprising Truth / Fun Fact

Google has a "brownout" mode—intentionally degrading non-essential features under load. They've used it in real outages. Gmail might show a simpler UI. Search might skip some features. The core works. They've run the company on degraded mode. More than once. Graceful degradation isn't theory. It's practiced. At scale. By companies that can't afford to go down.

---

## Quick Recap (5 bullets)

- **Graceful degradation** = reduce functionality to keep the core alive under overload.
- **Priority:** Identify critical vs. non-critical before crisis. Payment > recommendations. Login > personalization.
- **Techniques:** Feature flags, cached/stale data, static fallback, reduced quality.
- **Document and practice:** Know what to shed. Test in chaos drills. Wrong choice = worse outage.
- **Core always works.** Extras bend. Users get less. Users get something. Better than total failure.

---

## One-Liner to Remember

**When the ship is sinking, throw cargo overboard first. When the system is overloaded, shed features first. Keep the core. Survive.**

---

## Next Video

Next: **Load Shedding**—dropping work to save the system. Reject some requests so the rest succeed. Stay tuned.
