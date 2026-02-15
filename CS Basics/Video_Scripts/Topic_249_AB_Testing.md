# A/B Testing: Assignment and Consistency

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A restaurant. Testing a new menu. Half the tables get the old menu. Half get the new. At month's end: which had higher orders? A/B testing. But imagine a customer. Monday: table 5, new menu. Tuesday: table 12, old menu. They see different menus on different days. Inconsistent. Their behavior is polluted. You can't measure true impact. Assignment must be STICKY. Same user, same variant. Every time. Let's see how.

---

## The Story

A/B testing is simple in concept. Control vs experiment. Measure. Compare. Decide. The devil is in assignment. Random assignment? User gets control. Next request? Different server. Different "random." Experiment. User flickers. Confused. Data useless. Sticky assignment: hash(user_id + experiment_id) mod 100. Under 50? Control. Over 50? Experiment. Deterministic. Same user, same bucket. Every request. Every server. No coordination needed. Stateless. Perfect. Implement it. Test it. Verify. "User 12345 in experiment X always gets variant B." Critical. Without stickiness, your A/B test is garbage. With it, you can trust the results. Mostly. Statistical significance still matters. More on that later.

---

## Another Way to See It

Think of a clinical trial. Patient gets drug A or placebo. They stay in that group. For the whole trial. You don't switch them mid-study. "Monday you had placebo. Tuesday you get the drug." That would contaminate the data. Same with A/B tests. User in control stays in control. User in experiment stays in experiment. Sticky. The assignment is a commitment. For the duration of the experiment. Treat it that way. Your analytics depend on it.

---

## Connecting to Software

**Assignment algorithm.** hash(user_id + experiment_id) mod 100. Result 0-99. If < threshold (e.g., 50), control. Else, experiment. Deterministic. Same inputs, same output. Any server can compute. No shared state. No database lookup. Fast. Consistent. The hash distributes users evenly. 50/50 with threshold 50. 10/90 with threshold 10. Adjust threshold for traffic allocation. Multiple experiments? Different experiment_id. User can be in control for experiment A, experiment for B. Independent. No collision. Hash quality matters. Use a good hash. SHA-256. Or MurmurHash. Even distribution. Avoid MD5 for new code. Weak. But for assignment, even MD5 works. Not security. Just distribution.

**Why sticky matters.** If assignment changes mid-experiment, you're measuring noise. User sees control Monday. Clicks. Sees experiment Tuesday. Different behavior. Is the difference from the variant? Or from the change? Unknown. Contaminated. Sticky assignment: user sees one variant. Entire experiment. Clean comparison. Control users behave like control users. Experiment users behave like experiment users. Signal, not noise. Implement stickiness. It's non-negotiable.

**Statistical significance.** 1,000 users. 500 control, 500 experiment. Experiment: 5% conversion. Control: 4%. Is 5% really better? Or luck? Need enough sample size. Need enough time. Run power analysis before the test. "To detect 1% lift with 80% power, we need N users." Run until N. Don't stop early. Stopping when you see "winner" = bias. P-hacking. Run pre-defined duration. Or use sequential analysis. Know the rules. Stick to them. Premature conclusion = wrong decision. Costly.

**Interaction effects.** User in experiment A (new checkout) AND experiment B (new header). Do they interact? Maybe. New checkout + old header = one experience. New checkout + new header = different. Interaction. Hard to isolate. Options: segment experiments. Don't overlap. Or: include interaction in analysis. "A and B together." More complex. Or: run one at a time. Serial. Slower. But cleaner. Know your options. Choose consciously.

---

## Let's Walk Through the Diagram

```
A/B TEST ASSIGNMENT
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   USER REQUEST                                                    │
│   user_id=12345, experiment_id="checkout_v2"                     │
│        │                                                         │
│        ▼                                                         │
│   hash("12345" + "checkout_v2") mod 100 = 73                     │
│        │                                                         │
│        ├── 73 < 50? NO                                           │
│        │                                                         │
│        └──► ASSIGNMENT: EXPERIMENT (variant B)                    │
│                                                                  │
│   SAME USER + SAME EXPERIMENT = SAME RESULT. ALWAYS.             │
│   Server 1, Server 2, Monday, Friday: hash is deterministic.     │
│                                                                  │
│   THRESHOLD: 50 = 50/50 split. 10 = 10% experiment, 90% control.│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Request arrives. user_id, experiment_id. Hash them. Mod 100. Compare to threshold. 73 >= 50? Experiment. Store the result? No. Compute every time. Same result. Deterministic. Any server. Any time. Sticky. The diagram shows the flow. One formula. Every request. No state. No coordination. Elegant. Implement it. Verify with tests. "User X always gets Y." Assert it. Ship it.

---

## Real-World Examples (2-3)

**Netflix.** A/B tests everything. Thumbnails. Recommendation algorithms. UI. Sticky assignment. They've written about it. Statistically rigorous. Run until significance. Or predetermined duration. No peeking. The culture is data-driven. Assignment is the foundation. Get it right.

**Amazon.** Same. Every button. Every layout. Tested. Sticky assignment. They pioneered online A/B testing. The 1% improvement compound. Many small wins = big impact. Assignment consistency is table stakes. They do it at scale. Billions of requests.

**Optimizely / Split / LaunchDarkly.** Feature flag + A/B testing platforms. They handle assignment. Sticky. Consistent. If you use them, you get it for free. If you build your own, implement the hash. It's 10 lines of code. Don't skip it.

---

## Let's Think Together

**"You run an A/B test for 1 week. Results: new variant is 2% better. Is this statistically significant? How do you know?"**

Calculate. Sample size: how many users? 10,000? 100,000? Conversion rate: control 4%, experiment 6%? Standard error. Confidence interval. P-value. Or use a calculator. E.g., Evan Miller's. Input: control conversions, control sample, experiment conversions, experiment sample. Output: p-value, confidence. P < 0.05? Significant. P > 0.05? Could be luck. 2% lift with 10K users might be significant. With 1K users? Probably not. Run power analysis before: "To detect 2% lift with 80% power, 5% alpha, we need ~5,000 per variant." Run until you hit that. Or use sequential testing. Stop when confidence interval excludes zero. Tools exist. Use them. Don't guess. "It looks better" is not a valid conclusion. Statistics. Learn the basics. Or work with someone who has. Wrong conclusions cost money. Right conclusions make it.

---

## What Could Go Wrong? (Mini Disaster Story)

A team. A/B test. New landing page. They use "random" assignment. Literally random. rand() < 0.5. Each request. User loads page. 5 API calls. Each gets "random" assignment. 3 say control. 2 say experiment. Page is broken. Half control, half experiment. Franken-page. User sees both. Confused. Bounces. Experiment shows terrible results. "New design is worse!" No. Assignment was broken. Sticky assignment would have given consistent experience. One variant per user. Clean data. They fixed it. Re-ran. Results flipped. New design was better. One bug. Wrong decision. Lost revenue. Lesson: assignment is foundational. Get it right. Test it. Verify. "Same user, same variant" — assert it in your test suite. Don't discover it in production. Too late.

---

## Surprising Truth / Fun Fact

Microsoft ran an A/B test on the Bing homepage. One pixel. Literally. Moved an element one pixel. Measured engagement. One pixel. 2% revenue increase. Millions of dollars. From one pixel. A/B testing finds what you'd never guess. The assignment has to be right. Or you miss it. Or worse, you "find" something that's not there. P-hacking. False positives. Sticky assignment + proper statistics. That's how you find the one pixel that matters.

---

## Quick Recap (5 bullets)

- **Sticky assignment:** hash(user_id + experiment_id) mod 100. Same user, same variant. Always.
- **Why:** Changing assignment mid-experiment contaminates data. Can't measure true impact.
- **Deterministic:** Any server can compute. No shared state. Stateless. Fast.
- **Statistical significance:** Need enough sample. Run power analysis. Don't stop early. Avoid p-hacking.
- **Interaction:** User in multiple experiments? Effects can interact. Segment or analyze together.

---

## One-Liner to Remember

**A/B testing without sticky assignment is like a clinical trial that switches your medication every day—the data is useless.**

---

## Next Video

Next: log aggregation, tiering, compression, and how to keep a year of logs without going bankrupt.
