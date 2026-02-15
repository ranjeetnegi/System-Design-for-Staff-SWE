# Feature Flags and A/B Testing
## Video Length: ~4-5 minutes | Level: Intermediate
---
## The Hook (20-30 seconds)

You're a clothing store manager. You have a question: does a RED "SALE" sign or a BLUE "SALE" sign attract more buyers? You could guess. You could ask your gut. Or you could run an experiment. Put red in the left window. Blue in the right. Same store. Same products. Different treatment. Count purchases from each side. After a week: red = 150 sales. Blue = 200 sales. Blue wins. That's A/B testing. And in software, feature flags are the mechanism that lets you show different experiences to different users — and MEASURE which is better.

---

## The Story

Imagine you're building a new checkout flow. It's sleeker. Faster. You think users will love it. But you're not sure. Rolling it out to everyone is risky. What if it breaks? What if users hate it and bounce?

Here's where feature flags save the day. A feature flag is a simple switch: "For user X, show variant A or variant B?" You control who sees what. And you MEASURE the outcome.

In our clothing store analogy, the window is the "user." The sign color is the "variant." The purchase count is the "metric." Same idea. Different domain.

---

## Another Way to See It

Think of feature flags like a TV remote. One remote. One screen. But you can switch channels instantly. Comedy. News. Sports. The remote doesn't change the content — it changes what you SEE. Feature flags don't change your code — they change what USERS see. The code for both experiences lives in your app. The flag decides which one runs.

A/B testing sits ON TOP of feature flags. Flags give you the mechanism. A/B testing gives you the methodology. Test. Measure. Decide.

---

## Connecting to Software

Here's how it works in code:

```
if flag("checkout_v2", userId) → show new checkout
else → show old checkout
```

Simple. But the magic is in the assignment. How do you decide who gets the new checkout and who gets the old?

**Random assignment.** Hash the user ID plus the experiment name. Mod 100. 0–49 = control (old). 50–99 = experiment (new). Deterministic. Sticky. The same user always sees the same variant. No flickering. No confusion.

**Metrics.** Define success BEFORE the experiment. Conversion rate. Time to checkout. Error rate. Collect for both groups. Compare.

**Statistical significance.** This is critical. Running an experiment for 1 hour with 50 users proves nothing. You need thousands of users over days or weeks. Otherwise, "variant B won by 5%" might just be noise. Random chance. Flip a coin 10 times. You might get 7 heads. Doesn't mean the coin is biased. Same with A/B tests. Sample size matters. Run duration matters. Patience matters.

---

## Let's Walk Through the Diagram

```
                    ┌─────────────────┐
                    │  Feature Flag   │
                    │     Service     │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
        ┌─────────┐    ┌─────────┐    ┌─────────┐
        │ User 1  │    │ User 2  │    │ User 3  │
        │ hash→23 │    │ hash→67 │    │ hash→91 │
        │ CONTROL │    │  EXP    │    │  EXP    │
        └─────────┘    └─────────┘    └─────────┘
              │              │              │
              ▼              ▼              ▼
        Old Checkout   New Checkout   New Checkout
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────▼────────┐
                    │  Metrics DB     │
                    │  Compare rates  │
                    └─────────────────┘
```

Each user hits the flag service. Hash determines variant. They see A or B. Their behavior is tracked. At the end: which group converted better?

---

## Real-World Examples (2-3)

**Netflix** tests thumbnails. Different users see different cover images for the same show. They measure which thumbnail leads to more clicks. A/B testing at massive scale.

**Google** famously ran 41 shades of blue for link colors. Tiny change. Huge impact on click-through. They didn't guess — they measured.

**Shopify** tests checkout flows constantly. One variant might remove a form field. Another might change button text. "Buy now" vs "Add to cart" — which converts better? They run hundreds of experiments. Feature flags make it possible. Without flags, every test would require a deployment. With flags, product managers can toggle, measure, and iterate without engineering bottlenecks.

---

## Let's Think Together

You A/B test a new homepage. After 3 days, variant B shows 5% better conversion. Is that enough to declare a winner?

**Answer:** Probably not. Five percent over 3 days could be random chance. You need to check: How many users were in each group? What's the p-value? Is the difference statistically significant? If you had 10,000 users per group, 5% might be meaningful. If you had 100 per group, it's likely noise. Always ask: "Do I have enough data to trust this?" Tools like Optimizely, LaunchDarkly, or Statsig calculate this for you. But understanding the concept — that small samples lie — protects you from shipping based on flukes.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup runs an A/B test on their signup flow. Variant B wins. They roll it out to 100%. Two weeks later, support tickets spike. Users can't find the "Forgot Password" link. Turns out variant B moved it. The metric they measured was "signup completion." They didn't measure "password reset usage." Variant B got more signups — but created a hidden UX problem. Lesson: Measure more than one thing. Look for unintended consequences.

---

## Surprising Truth / Fun Fact

Amazon runs over 10,000 A/B tests per year. Most fail. Most show no difference. That's okay. The goal isn't to "win" every test — it's to learn. One winning experiment can pay for a hundred that taught you nothing.

---

## Quick Recap (5 bullets)

- Feature flags let you show different experiences to different users. The flag is the switch.
- A/B testing uses flags to randomly assign users to control vs. experiment groups.
- Random assignment is deterministic: hash(user_id + experiment) keeps users sticky.
- Define metrics before the experiment and wait for statistical significance.
- Measure multiple outcomes — don't optimize one metric and break another.

---

## One-Liner to Remember

**Feature flags are the switch; A/B testing is the experiment. Show different things to different users, measure what works, then ship the winner.** Don't guess. Test. Let the data decide. Your gut is wrong more often than you think.

---

## Next Video

Next up: **Data Lineage** — when a health inspector asks "where did this chicken come from?", you'd better have an answer. Same with data. Where did that number in your dashboard come from? We'll trace it back. Trust in your numbers starts with knowing their source.
