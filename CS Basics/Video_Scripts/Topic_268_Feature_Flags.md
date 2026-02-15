# Feature Flags: Safe Rollout

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A light switch on your TV remote. You can turn a feature ON or OFF without rebuilding the TV. No screws. No factory trip. Just flip the switch. Feature flags do that for software. You deploy code with the feature hidden behind a flag. Flip the flag ON for 1% of users. Monitor. 10%. Monitor. 100%. If anything breaks at 10%, flip OFF immediately. The code is already deployed—you're just toggling visibility. No deployment needed to roll back. That's the power.

---

## The Story

Traditionally: build feature, test, deploy. If it breaks, you deploy again to fix. Or roll back the whole deployment. Slow. Risky. Feature flags change the game. Deploy the code. But hide it behind a flag. The flag is off. Users see the old experience. You turn the flag on for internal users. Test in production. Real data. Real traffic. Then 1% of customers. Watch. Then 10%. Then 100%. At any point, if things go wrong, you flip the flag off. Rollback without redeploying. The code stays. The feature disappears. Instant.

Think of it like a curtain on a stage. The performers are there—the code is deployed. The curtain is closed—the flag is off. When you're ready, open the curtain. When there's a problem, close it. The performers don't leave. You control visibility.

---

## Another Way to See It

Imagine a restaurant with a new dish. The chef has prepared it. It's in the kitchen. But the manager decides when it appears on the menu. Today: offer it to two tables as a "special." If they like it, add it to the menu. If they get sick, never add it. The dish exists. The decision to expose it is separate. Feature flags are the manager's control.

---

## Connecting to Software

**Implementation:** Simple. `if (featureFlag.isEnabled("new-checkout", userId)) { showNewCheckout(); } else { showOldCheckout(); }` The flag service (LaunchDarkly, Split, Flagsmith, or your own) returns true or false. Based on user ID, percentage, segment, or environment. The decision is made at runtime. No code change. The power is in the split—same deploy, different experience for different users. Test in production without affecting everyone.

**Flag types:** Boolean—on or off for everyone. Percentage—10% of users randomly. User targeting—specific users (by ID, email, plan). Segment—"all premium users," "all users in EU." Environment—on in staging, off in production. Combine them. "10% of premium users in production."

**Flag lifecycle:** Created → tested in staging → rolled out in production (1% → 10% → 100%) → either permanent (remove the flag, delete the old code) or killed (remove the flag and the new code—feature didn't work out). The danger: flag debt. Hundreds of flags. Nobody knows which are active. Dead code paths. Old features still behind flags from 2019. Regular cleanup is essential. Schedule a "flag review" every quarter. Remove what's done. Document what remains. Your future self will thank you.

---

## Let's Walk Through the Diagram

```
                    Feature Flag Service
                    (LaunchDarkly, etc.)
                           |
                           | isEnabled("new-checkout", userId)?
                           |
              ┌────────────┴────────────┐
              |                         |
         userId in 10%              userId not in 10%
              |                         |
              v                         v
    showNewCheckout()           showOldCheckout()
    (new code path)              (old code path)
    
    Both code paths deployed. Flag decides which runs.
    Flip flag → change behavior. No deploy.
```

The key: both branches exist in production. The flag is the switch. Change the switch—behavior changes. No new deployment.

---

## Real-World Examples (2-3)

**Netflix** uses feature flags extensively. A/B tests. Gradual rollouts. Kill switches. When something goes wrong, they disable features in seconds. No global deploy. Their system handles millions of flag evaluations per second.

**Etsy** famously ships to production constantly. Features stay behind flags. "Ship small, ship often" works because flags make each small ship safe. If a deploy breaks something, it's often just a flag that was accidentally turned on. Flip it off. Done.

**Uber** uses flags for driver and rider app features. Roll out to one city first. Then a region. Then globally. Different features for different markets. Flags enable that without maintaining separate codebases. One codebase, many configurations, controlled at runtime.

---

## Let's Think Together

**"You have 20 feature flags. 5 of them interact with each other. How many combinations? How do you test all of them?"**

2^5 = 32 combinations. And that's just those 5. With 20, the full combination space is 2^20 = over a million. You cannot test them all manually. Strategies: (1) Design flags to be independent when possible. (2) Use integration tests that cover critical combinations. (3) Canary rollout—real users hit combinations you didn't think of. (4) Monitor. If a weird combination causes bugs, you'll see it in error rates. (5) Clean up. Remove flags once the feature is fully rolled out. Fewer flags = fewer combinations = saner testing.

---

## What Could Go Wrong? (Mini Disaster Story)

A company had 500 feature flags in production. No documentation. Engineers left. New engineers didn't know what half of them did. One flag—"beta_search"—had been on for 100% of users for two years. The "old" search code path was never executed. Except in one cron job. That cron job had a bug. It only ran when the flag was off. Nobody noticed for months. Then someone "cleaned up" and removed the beta_search flag. The cron job started taking the old path. Bug triggered. Data corruption. Days to fix. Lesson: flag debt is real. Audit. Document. Remove flags when features are permanent. Treat flags as temporary. Not forever.

---

## Surprising Truth / Fun Fact

Martin Fowler wrote about feature flags in 2010. The concept was around before—Flickr, for example, used "bucketing" in the mid-2000s. But the term "feature flags" and the tooling (LaunchDarkly, Split) have made it mainstream. Some companies now have "flag coaches"—people who help teams use flags effectively and avoid flag debt. It's a discipline.

---

## Quick Recap (5 bullets)

- **Feature flags** = deploy code, toggle visibility at runtime; rollback without redeploy.
- **Types** = boolean, percentage, user/segment targeting, environment.
- **Lifecycle** = create → test → rollout → permanent or kill; clean up to avoid debt.
- **Interactions** = 5 flags = 32 combinations; design for independence; test critical paths.
- **Flag debt** = hundreds of stale flags cause confusion and bugs; audit and remove.

---

## One-Liner to Remember

*Feature flags are light switches for code—deploy once, toggle anytime; rollback is a flip, not a redeploy.*

---

## Next Video

Next: Runbooks and incident response. When the fire alarm goes off at 3 AM, what do you do? Step-by-step plans written BEFORE the disaster. See you there.
