# Chapter 92: Ad Serving & Real-Time Bidding — Google / Meta / Amazon

> Ad serving is one of the most latency-sensitive, highest-throughput distributed
> systems ever built. A single page load triggers 50ms auctions involving hundreds
> of bidders, targeting billions of attributes, with real money changing hands
> on every single request.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

Ad systems are the revenue engine at Google ($175B/year), Meta ($115B/year), and
Amazon ($40B/year). Understanding ad serving is expected at L6 at these companies.
The system design combines: sub-50ms latency at 10M+ QPS, real-time auctions,
ML-driven targeting, frequency capping across devices, and attribution/measurement.

---

## Planned Content

### Part 1: The Ad Ecosystem — Publishers, Advertisers, DSPs, SSPs
- Publisher: website/app with ad slots (NYT, YouTube, mobile apps)
- Advertiser: company buying ads (Nike, Apple, a local restaurant)
- DSP (Demand-Side Platform): aggregates advertisers, bids on their behalf
- SSP (Supply-Side Platform): aggregates publishers, sells their inventory
- Ad Exchange: the marketplace where DSPs and SSPs meet (Google Ad Exchange)
- The flow: user loads page → SSP sends bid request → DSPs respond → auction → ad shown

### Part 2: Real-Time Bidding (RTB) Architecture
- Timeline: page load event → bid request → 50ms auction window → winning ad returned
- Bid request: user ID, page URL, ad slot dimensions, user signals, floor price
- DSP decision: is this user in my target audience? what's the expected conversion rate?
  what should I bid?
- Second-price auction: winner pays second-highest bid + $0.01 (honest bidding incentive)
- Winner notification: win notice to winning DSP, loss notices (optional) to others
- ASCII diagram: RTB flow with latency budget breakdown (50ms total)

### Part 3: User Targeting
- Demographic targeting: age, gender, location (from registration or inferred)
- Behavioral targeting: browsing history, purchase intent, interest categories
- Contextual targeting: keywords on the current page (no user data needed)
- Retargeting: user visited Nike.com → Nike shows ads on NYT
  - Tracking pixels + cookie matching across domains
  - Post-iOS 14.5 (app tracking transparency): fingerprinting alternatives
- Lookalike audiences: find users similar to an advertiser's existing customers
- Real-time user profile lookup: 10ms budget for user data fetch from Bigtable/Redis

### Part 4: Frequency Capping
- Problem: don't show the same user the same ad 100 times (annoying + wasteful)
- Cap types: per-day, per-week, per-flight (campaign duration)
- Implementation challenge: user sees ads across 5 devices, 3 browsers, 2 apps
- Centralized counter: Redis INCR with TTL per (user, campaign) key
  - Problem: 10M+ active users × 10K active campaigns = 100B potential keys
  - Optimization: probabilistic data structures (Count-Min Sketch, HyperLogLog)
- Cross-device: identity graph to link devices to one user (cookie + email + mobile ID)
- Real incident: Meta 2021 — frequency cap bug caused same ad to show 10x/day for
  a week, causing advertiser trust crisis and $50M in make-good credits

### Part 5: Ad Ranking and Auction Mechanics
- Not just highest bid wins: quality score matters
  - Expected CTR: probability the user will click (ML model)
  - Relevance score: how relevant is this ad to this user/page?
  - Ad rank = bid × quality score
- Vickrey auction vs. Generalized Second Price (GSP)
- Reserve price: publisher's minimum acceptable bid
- Programmatic Guaranteed: pre-negotiated deals bypass the open auction
- Floor price optimization: dynamic floor prices to maximize publisher revenue

### Part 6: Measurement and Attribution
- Did the ad cause the purchase? The attribution problem.
- Last-click attribution: simplest but wrong (ignores the assist)
- Multi-touch attribution: weight each touchpoint in the conversion funnel
- View-through attribution: user saw the ad but didn't click; did it influence them?
- Incrementality testing: A/B test — users who saw ad vs. holdout group
- Privacy-safe measurement: Google Privacy Sandbox, Apple SKAdNetwork — aggregate
  conversion signals without individual-level tracking

### Part 7: Ad Fraud Detection
- Click fraud: bots clicking ads to drain advertiser budget
- Impression fraud: bots loading pages to generate CPM revenue for fake publishers
- Detection signals: click velocity, mouse movement patterns, user agent analysis,
  IP reputation, traffic pattern anomalies
- Invalid Traffic (IVT) filtering: subtract fraudulent impressions from billing
- Real incident: 2017 Methbot fraud — $3-5M/day in fake video ad impressions
  from a botnet mimicking human browser behavior

### Part 8: Budget Pacing
- Problem: spend advertiser budget evenly across the day, not all in the first hour
- Standard pacing: throttle bid participation rate (bid on 10% of auctions if 10% of
  budget remains for 90% of day)
- ASAP pacing: spend as fast as possible (for time-sensitive promotions)
- Smooth pacing: ML model predicts traffic patterns, adjusts bid rate proactively
- Cross-timezone budgets: global campaigns with per-timezone budgets

### Part 9: Interview Framework
- Always separate: the auction (RTB) from targeting from measurement from fraud
- Key latency question: where does the 50ms go?
  - 5ms: bid request transmission
  - 10ms: user profile lookup (Bigtable/Redis)
  - 15ms: ML scoring (expected CTR)
  - 5ms: auction computation
  - 15ms: ad creative retrieval + transmission
- L5 vs. L6: L5 draws a bidding flow; L6 discusses the quality score formula,
  why second-price auction is used, how frequency caps work at scale with Count-Min Sketch

---

## Key Numbers to Memorize

| Metric | Value |
|--------|-------|
| Google ad revenue | $175B/year |
| RTB auction window | 50–100ms |
| Google Display Network QPS | ~10M/second |
| Typical auction participants | 20–200 DSPs per auction |
| CTR for display ads | 0.05–0.3% |
| CTR for search ads | 2–10% |
| Frequency cap (typical) | 3–5 impressions/day |
| Ad fraud rate (industry) | 10–30% of display impressions |

---

## The One-Sentence Summary

> "Ad serving = RTB auction (50ms, second-price, quality score × bid) + real-time targeting (user profile lookup → ML CTR prediction) + frequency capping (Count-Min Sketch per user/campaign) + measurement (attribution, incrementality testing) — the system makes $500M/day, so every millisecond and every fraud vector costs real money."

---

*Full chapter: ~2,500 lines. Pairs with Ch64 (Recommendation/Ranking) for ML scoring models.*
