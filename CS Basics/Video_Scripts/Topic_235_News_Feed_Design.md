# News Feed: Fan-out, Ranking, Scale

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

You open Twitter. 300 people you follow posted new tweets. Your feed shows them ranked by relevance and time. Behind the scenes: how did your phone get those 300 tweets so fast? Two approaches: fan-out-on-write (pre-compute your feed when a tweet is posted) or fan-out-on-read (compute your feed when you open the app). Each has massive trade-offs. Let's break it down.

---

## The Story

A celebrity posts a tweet. 100 million followers. If we pushed that tweet to every follower's feed at write time—fan-out-on-write—that's 100 million writes. Per tweet. One tweet. 100M writes. How long does that take? How much does it cost? The math gets scary fast. If we pull at read time—fan-out-on-read—each user opens the app, we query "get latest from everyone I follow." For a user following 300 people, that's 300 queries. Merged. Sorted. Slow. Expensive at read. But no pre-computation. Simple writes.

The real answer: hybrid. Twitter does this. Regular users: fan-out-on-write. Your 500 followers? Push to their feeds. Cheap. Celebrities: fan-out-on-read. Pull their tweets when you load. Merge with pre-computed feed. Best of both. The cut-off matters. 10K followers? 100K? Tune it. Staff engineers make that call. One threshold. Millions of dollars. Billions of writes saved.

---

## Another Way to See It

Imagine a newspaper. Option A: Custom print for every subscriber. 1 million subscribers. 1 million different newspapers. Printed at 6 AM. Expensive. But delivery is instant—hand them their paper. Option B: One newspaper. Everyone gets the same. But you want personalized. So at delivery time, the carrier flips to YOUR section. Slower delivery. Cheaper print. Fan-out-on-write vs fan-out-on-read. Same trade-off. Write cost vs read cost. Scale decides which wins.

---

## Connecting to Software

**Fan-out-on-write.** User posts. System: "Who follows this user?" For each follower, insert into their feed store. Fast reads. User opens app: read their feed. One read. Pre-computed. Con: expensive writes. Celebrity with 100M followers = 100M inserts. Per post. Ouch.

**Fan-out-on-read.** User opens app. System: "Who does this user follow?" Query each followee's latest. Merge. Sort. Return. Simple writes. One insert per post. Con: expensive reads. User following 1000 people = 1000 queries + merge. Slow. Gets worse with more follows.

**Hybrid.** Regular users: fan-out on write. Celebrities: fan-out on read. Merge at read time. Implementation: feed table for regular. When user loads, read feed + pull from celebrity list. Merge. Rank. The threshold: typically 10K-100K followers. Below: push. Above: pull. Tune based on your read/write ratio and cost.

**Ranking.** Not just chronological. ML models score each post. Engagement signals. Personalization. "You'll like this." Ranking adds latency. Caching helps. Pre-compute for hot users. The feed is not just retrieval. It's a recommendation problem. Instagram, Facebook, Twitter: all rank. Chronological is the baseline. Ranking is the product.

---

## Let's Walk Through the Diagram

```NEWS FEED - FAN-OUT STRATEGIES
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
|   FAN-OUT-ON-WRITE          FAN-OUT-ON-READ                      |
│                                                                  │
|   User posts --> Get followers --> Insert into each feed         |
|        |                    |                                     |
|        |              [F1 feed][F2 feed][F3 feed]...              |
|        |                    |                                     |
|   Read: Just read MY feed (pre-computed)                         |
│                                                                  │
|   User opens app --> Get followees --> Query each --> Merge      |
|        |                    |                                     |
|        |              [Query A][Query B][Query C]...               |
|        v                    v                                     |
|   Return merged, ranked feed                                     |
│                                                                  │
|   HYBRID: Push for small accounts. Pull for celebrities. Merge.  |
│                                                                  │
└─────────────────────────────────────────────────────────────────┘```

Narrate it: Fan-out on write: post triggers N inserts. N = followers. Read is one query. Fan-out on read: post triggers 1 insert. Read triggers N queries + merge. Hybrid: push for most, pull for celebrities. Merge at read. The diagram simplifies. The real system has queues, async workers, ranking pipelines. But the core trade-off is here. Write cost vs read cost. Pick your poison. Or hybrid.

---

## Real-World Examples (2-3)

**Twitter.** Hybrid. Regular users get push. Celebrities get pull. They've published on it. The system evolved. Early Twitter: pure pull. Didn't scale. They built push. Then hybrid. Years of iteration. Your first version does not need to be perfect. It needs to work. Optimize later.

**Facebook.** Similar. Feed is pre-computed for most. Edge rank algorithm. ML-driven. Billions of users. The engineering blog has deep dives. They treat feed as a product. Not just a query.

**Instagram.** Same pattern. Push for regular. Pull for big accounts. Merge. Rank. The principles are universal. The implementation varies by scale and product.

---

## Let's Think Together

**"Elon Musk tweets. 150M followers. Fan-out-on-write = 150M writes. How long does this take?"**

At 100K writes/sec: 1500 seconds = 25 minutes. One tweet. 25 minutes to fan out. Users would see it 25 minutes late. Unacceptable. So: don't fan-out on write for celebrities. Pull at read. When you open the app, we fetch Elon's latest. Merge with your pre-computed feed. Fast. The 150M writes never happen. You only fetch when someone actually loads. Maybe 1% of followers check in the next hour. 1.5M reads instead of 150M writes. Order of magnitude better. The hybrid model exists because the math demands it. Do the math. It will guide you.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup builds fan-out-on-write. Works great. 10K users. 100 followers each. User opens app. 100 writes. Fine. They grow. One influencer joins. 2 million followers. They post. 2 million writes. Queue backs up. Database melts. Site down for 2 hours. The fix: detect high-follower accounts. Don't fan-out for them. Pull at read. One code path. One config. Could have saved them. Plan for the power-law. A few users have most of the followers. Design for that. Always.

---

## Surprising Truth / Fun Fact

Twitter's early architecture was entirely pull. "Get tweets from everyone I follow." Simple. Broke at scale. The "fail whale" era. They rebuilt with push. Then hybrid. The evolution of a feed system is a study in scale. Start simple. Hit a wall. Optimize. Hit another wall. Optimize again. Nobody gets it right the first time. Not even Twitter. Iterate. Measure. Learn. That's the job.

---

## Quick Recap (5 bullets)

- **Fan-out-on-write:** Pre-compute feed at post time. Fast reads. Expensive writes. Breaks for celebrities.
- **Fan-out-on-read:** Compute feed at read time. Cheap writes. Expensive reads. Breaks for users following many.
- **Hybrid:** Push for regular users. Pull for celebrities. Merge at read. Industry standard.
- **Ranking:** Not just chronological. ML. Engagement. Personalization. Product differentiator.
- **Threshold:** Typically 10K-100K followers. Below: push. Above: pull. Tune.

---

## One-Liner to Remember

**News feed is push vs pull—write cost vs read cost. Hybrid wins: push for most, pull for celebrities, merge at read.**

---

## Next Video

Next: when the fan-out pipeline can't keep up. Backpressure. Load shedding. World Cup final. 500K tweets/sec.
