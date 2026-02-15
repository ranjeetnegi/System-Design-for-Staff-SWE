# Recommendation System: Data and Ranking

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Netflix homepage. "Because you watched Breaking Bad: Better Call Saul, Ozark, Narcos." How does Netflix KNOW? They track everything. What you watched. How long. When you paused. What you searched. What you skipped. Then an ML model scores every show: "probability this user will watch this." Top scores = your recommendations. Data plus ranking. That's the recipe. Let's break it down.

---

## The Story

Recommendation systems seem like magic. "How did they know I'd like that?" It's not magic. It's data. Implicit signals: watch time, clicks, skips, search queries. You didn't say "I like thrillers." You watched 5 thrillers to the end. Skipped the romantic comedy in 2 minutes. The system infers. Explicit signals: ratings, likes, "not interested." Direct feedback. Both matter. Collaborative filtering: "users like you also watched X." Content-based: "you liked action movies, this is an action movie." Hybrid: combine both. Then ranking. You have 100,000 titles. You can't score all 100,000 in real-time. Too slow. Two stages: candidate generation (narrow to 1,000) and ranking (score those 1,000, pick top 10). Data feeds both. More data, better recommendations. It's a virtuous cycle. Or a creepy one. Depends on your perspective.

---

## Another Way to See It

Think of a sommelier. You tell them what you've enjoyed. They remember. "You liked the Cabernet. This Malbec has similar notes." That's collaborative filtering—similar tastes. Or: "You prefer bold reds. This is a bold red." Content-based—similar attributes. The sommelier doesn't suggest every wine in the cellar. They narrow. "From these 20, which 3 for you?" Candidate generation. Then they pick the best 3. Ranking. Same logic. Software just does it at scale. Millions of users. Millions of items. The math is bigger. The idea is the same.

---

## Connecting to Software

**Data.** Implicit: watch time (positive—longer = more interest), clicks, pauses, replays, skips (negative—quick skip = dislike), search queries (intent). Explicit: ratings, likes, "add to list," "not interested." Store everything. Every interaction. Build user vectors. Item vectors. Embeddings. "User 12345 is similar to users who liked X, Y, Z." "Item 67890 is similar to items 11111, 22222." Matrix factorization. Neural networks. Many techniques. All need data. Cold start: new user, no history. What do you recommend? Popular items. Demographic defaults. Ask them. "What do you like?" Onboarding matters. New item, no plays? Content features. Genre, cast, description. Content-based until you have behavioral data.

**Ranking pipeline.** Stage 1: Candidate generation. 100K items → 1,000 candidates. Fast. Collaborative filtering. "Users like you watched these." Or content-based. "Similar to what you watched." Or simple: "trending now." Stage 2: Scoring. ML model. Deep neural network. Input: user features, item features, context. Output: score. Probability of engagement. Stage 3: Re-ranking. Diversity. "Don't show 10 similar thrillers." Mix genres. Freshness. "Don't show the same thing for a week." Business rules. "Promote this new release." Slots. "Position 1 gets 50% of clicks." Optimize. The pipeline is sequential. Each stage refines.

**Real-time vs batch.** Batch: train model nightly. Update user vectors. Scores from yesterday's data. Good enough for many use cases. Real-time: user just watched something. Adjust recommendations immediately. "Because you just watched X"—that's real-time. Requires streaming. Fast feature computation. More complex. More impactful. Modern systems do both. Batch for baseline. Real-time for session-based adjustments.

---

## Let's Walk Through the Diagram

```
RECOMMENDATION PIPELINE
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   DATA LAYER                                                      │
│   Watches, clicks, skips, ratings ──► User/Item embeddings       │
│                                                                  │
│   STAGE 1: CANDIDATE GENERATION                                   │
│   100K items ──► CF + Content-based ──► 1,000 candidates          │
│                                                                  │
│   STAGE 2: RANKING (ML Model)                                     │
│   1,000 candidates ──► Neural network ──► Scores                   │
│                                                                  │
│   STAGE 3: RE-RANKING                                             │
│   Top 100 ──► Diversity, freshness, biz rules ──► Top 10         │
│                                                                  │
│   COLD START: New user? Popular items. New item? Content features.│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Data flows in. Watches, clicks, ratings. Build user and item representations. Candidate generation narrows 100K to 1K. Fast filters. Ranking model scores each. Picks top 100. Re-ranking adds diversity, freshness. Final top 10 to the user. Each stage has a role. Candidate generation: don't waste compute on bad items. Ranking: personalized score. Re-ranking: UX polish. The diagram shows the flow. Simple in concept. Complex in implementation. Netflix, YouTube, Amazon—all use some version of this.

---

## Real-World Examples (2-3)

**Netflix.** 200+ million users. Millions of titles. Collaborative filtering. Content-based. A/B testing everything. They've written papers. The recommendation engine is their moat. "Because you watched" is famous. Proven at scale.

**YouTube.** Similar. Watch history. Click history. Recommendation shelf. "Up next." Billion users. Real-time updates. You watch one video. Next recommendations change. Session-based. The data flywheel: more watches, better model, better recommendations, more watches.

**Amazon.** "Customers who bought this also bought." Classic collaborative filtering. Product features. "You viewed X." Real-time. Hybrid approach. E-commerce recommendations are different—purchase intent. But the pipeline is the same. Candidates. Rank. Display.

---

## Let's Think Together

**"New user. No history. Cold start problem. How do you recommend anything?"**

No behavioral data. Can't do collaborative filtering. Options: popular items. "Trending now." "Most watched this week." Everyone gets the same. Not personalized. But something. Or: ask. Onboarding. "Pick 3 genres you like." "Rate 5 movies." Gets explicit signals. Fast. Or: demographic. "Users in your region, your age group, liked X." Proxy for taste. Weak but better than random. Or: content diversity. Show a mix. Something for everyone. Eventually, they interact. One click. One watch. Now you have data. Adjust. Cold start is temporary. Design for the first session. Optimize for the long term. The first recommendation matters. Don't leave it to chance.

---

## What Could Go Wrong? (Mini Disaster Story)

A streaming platform. Recommendation model. Trained on historical data. Worked well. Then COVID. Usage patterns shifted. People watched different things. At different times. The model wasn't retrained. Recommendations got stale. "Because you watched" suggested things from 6 months ago. Irrelevant. Engagement dropped. Churn increased. The team retrained. Weekly. Then daily. Problem improved. Lesson: recommendation models decay. Distribution shift. User behavior changes. Retrain. Continuously. Monitor engagement. When click-through rate drops, investigate. Model might be stale. Data might have shifted. Recommendations are not "set and forget." They're living systems. Evolve or die.

---

## Surprising Truth / Fun Fact

Netflix offered a $1 million prize in 2006 for a 10% improvement in their recommendation algorithm. The winner: an ensemble of hundreds of models. No single technique won. Combinations. Clever feature engineering. The lesson: recommendation is an engineering problem. No silver bullet. Try many things. Combine. A/B test. Iterate. The prize was discontinued—implementing the winning solution was too complex. But the insight remains: recommendations are hard. Improve incrementally. Ship often. Measure everything.

---

## Quick Recap (5 bullets)

- **Data:** Implicit (watches, clicks, skips) + explicit (ratings, likes). Both feed the model.
- **Pipeline:** Candidate generation (100K→1K) → Ranking (ML score) → Re-ranking (diversity, rules).
- **Collaborative filtering:** "Users like you also liked." Content-based: "Similar attributes."
- **Cold start:** New user = popular items or onboarding. New item = content features.
- **Retrain:** Models decay. User behavior shifts. Retrain regularly. Monitor engagement.

---

## One-Liner to Remember

**Recommendations are data plus ranking—the more you watch, the more they know, and the better they get (or the creepier it feels).**

---

## Next Video

Next: notification fan-out, sending one event to millions, and deduplication at scale.
