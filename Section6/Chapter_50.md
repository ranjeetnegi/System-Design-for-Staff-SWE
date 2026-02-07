# Chapter 50. Recommendation / Ranking System (Simplified)

---

# Introduction

A recommendation system decides what to show a user when they haven't explicitly asked for anything. Search responds to intent; recommendations create it. I've built and operated recommendation systems that served 500 million ranked feeds per day, and I'll be direct: the hard part isn't training a model that predicts clicks—any ML engineer can get a reasonable model in a week. The hard part is serving personalized results for 100 million users in under 100 milliseconds, re-ranking in real time as user behavior changes within a session, keeping the system from collapsing into a filter bubble where users only see content that confirms their existing preferences, and evolving the architecture from a batch-computed daily export into a real-time, multi-stage ranking pipeline that powers every surface of the product—home feed, notifications, related items, "you might also like"—without one surface's model update breaking another's metrics.

This chapter covers a **simplified** recommendation and ranking system at Staff Engineer depth. We focus on the infrastructure: how candidates are generated, how they're scored, how the system serves at scale, how it fails gracefully, and how it evolves. We deliberately simplify the ML model internals (feature engineering, training pipelines, model architectures) because those are ML platform concerns, not system design concerns. The Staff Engineer's job is designing the serving infrastructure that makes recommendations fast, reliable, and evolvable.

**The Staff Engineer's First Law of Recommendations**: A recommendation system that returns irrelevant results is worse than one that returns nothing. Users tolerate "no recommendations available" once; they don't tolerate a feed full of garbage. Relevance is the product—latency and availability are constraints.

---

## Quick Visual: Recommendation / Ranking System at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│     RECOMMENDATION SYSTEM: THE STAFF ENGINEER VIEW                          │
│                                                                             │
│   WRONG Framing: "An ML model that predicts what users want"                │
│   RIGHT Framing: "A multi-stage pipeline that retrieves thousands of        │
│                   candidates from billions of items, scores them with       │
│                   multiple models, applies business rules and diversity     │
│                   constraints, and serves a personalized ranked list—       │
│                   all in under 100ms, for every user, on every page load"   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Before designing, understand:                                      │   │
│   │                                                                     │   │
│   │  1. What is the item corpus? (Products? Posts? Videos? Ads?)        │   │
│   │  2. How many items? (Thousands? Millions? Billions?)                │   │
│   │  3. What user signals exist? (Views? Clicks? Purchases? Dwell?)     │   │
│   │  4. Is this a new product (cold start) or mature (rich signals)?    │   │
│   │  5. What are the business constraints? (Diversity? Freshness?       │   │
│   │     Fairness? Monetization?)                                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   THE UNCOMFORTABLE TRUTH:                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  The recommendation model gets all the attention, but it's only     │   │
│   │  5% of the system. The other 95% is: candidate generation at        │   │
│   │  scale, feature storage and serving, real-time signal ingestion,    │   │
│   │  serving infrastructure, A/B testing, and the feedback loop that    │   │
│   │  connects user behavior back to model training. A brilliant model   │   │
│   │  in a bad infrastructure serves stale, slow, or no results.         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Recommendation System Decisions

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Candidate generation** | "Query the item database, filter by category, return top items by popularity" | "Multi-source retrieval: collaborative filtering for personalization, content-based for coverage, trending for recency, editorial for curation. Each source returns hundreds of candidates independently. Union them. The retrieval stage determines the CEILING of recommendation quality—if a good item isn't retrieved, no ranker can surface it." |
| **Ranking** | "Score items with a single ML model, sort by score" | "Multi-stage ranking: lightweight pre-filter (thousands → hundreds), full ranking model (hundreds → dozens), business-rule re-ranking (diversity, freshness, monetization). Each stage has its own latency budget. The full model is expensive—apply it to hundreds, not millions." |
| **Feature serving** | "Look up user profile and item metadata from the database" | "Pre-computed feature store with dual read paths: batch features (user long-term preferences, item popularity) from offline pipelines, near-real-time features (session clicks, last 5 minutes of behavior) from streaming pipelines. Feature freshness directly impacts recommendation quality—stale features = stale recommendations." |
| **Feedback loop** | "Log clicks, retrain model weekly" | "Real-time event streaming: clicks, views, dwell time, skips, purchases all logged with millisecond precision. Events flow to both the feature store (real-time signal update) and the training pipeline (model improvement). Feedback delay = how long the system takes to learn from user behavior. Shorter delay = more relevant recommendations." |
| **Cold start** | "Show popular items for new users" | "Progressive personalization: Popular items → category-based recommendations (from onboarding signals) → content-based (from first few interactions) → collaborative filtering (after enough interactions). Each stage uses different models with different feature requirements. The system must gracefully transition between stages without the user noticing." |
| **Failure handling** | "If the model is down, show popular items" | "Graceful degradation stack: Full personalized ranking (normal) → Cached recent recommendations (model slow) → Pre-computed popular items per segment (model down) → Global popular items (everything down). Each fallback level is pre-computed and ready to serve. Users should always see SOMETHING—never an empty page." |

**Key Difference**: L6 engineers design the recommendation system as an infrastructure platform with multiple ranking surfaces, not a single model endpoint. They think about the feedback loop as a first-class component, treat cold start as a staged migration problem, and design fallback layers that ensure users always see reasonable content.

---

# Part 1: Foundations — What a Recommendation System Is and Why It Exists

## What Is a Recommendation System?

A recommendation system selects and ranks items from a large corpus to show specific users content they're likely to find valuable. Unlike search, where the user provides intent via a query, recommendation systems must infer intent from user behavior, context, and profile data. The system answers the question: "Given everything we know about this user, what should we show them right now?"

### The Simplest Mental Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE SIMPLEST MENTAL MODEL                                │
│                                                                             │
│   A recommendation system is a PERSONAL SHOPPER:                            │
│                                                                             │
│   OBSERVE: Watch what the customer browses, buys, and ignores               │
│   → "They looked at running shoes for 5 minutes"                            │
│   → "They bought a fitness tracker last week"                               │
│   → "They skipped all fashion items quickly"                                │
│                                                                             │
│   RETRIEVE: Go to the warehouse and pull candidate items                    │
│   → Items similar to what they've bought (collaborative filtering)          │
│   → Items related to what they're browsing (content-based)                  │
│   → Items that are popular right now (trending)                             │
│   → Items the store wants to promote (business rules)                       │
│                                                                             │
│   RANK: Arrange items on the display shelf in order of predicted value      │
│   → "Running shoes first — high purchase probability"                       │
│   → "Fitness apparel second — category affinity"                            │
│   → "New arrivals third — freshness bonus"                                  │
│   → "Electronics last — low signal for this user"                           │
│                                                                             │
│   SERVE: Present the shelf to the customer immediately                      │
│   → The customer sees a personalized storefront                             │
│   → Response must be instant (< 100ms) — they'll walk away otherwise        │
│                                                                             │
│   LEARN: Watch what they pick up and put down                               │
│   → "They clicked running shoes — increase sports affinity"                 │
│   → "They ignored fitness apparel — maybe not interested after all"         │
│   → Update the model for next time                                          │
│                                                                             │
│   SCALE: Do this for 100 million customers simultaneously                   │
│   → Each customer gets a different shelf                                    │
│   → Each shelf is built from a 10-million-item warehouse                    │
│   → Each shelf must be ready in 100ms                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### What the System Does on Every Request

```
FOR each recommendation request (e.g., home page load):

  1. USER CONTEXT ASSEMBLY
     Identify user → Load user profile + recent behavior
     → User 12345: Sports enthusiast, browsed shoes 2 min ago, 
       purchased fitness tracker last week
     Cost: ~5ms (feature store lookup)

  2. CANDIDATE RETRIEVAL (multi-source, parallel)
     Source A — Collaborative filtering: "Users like you bought..."
     → 500 candidates based on similar users' behavior
     Source B — Content-based: "Items similar to your recent views..."
     → 300 candidates based on item attribute similarity
     Source C — Trending: "Popular items in your region right now"
     → 200 candidates from trending pipeline
     Source D — Editorial / Business: Promoted items, new arrivals
     → 100 candidates from business rules
     Union: ~1,000 unique candidates (after deduplication)
     Cost: ~15ms (parallel retrieval from multiple indices)

  3. FEATURE ASSEMBLY
     For each of the 1,000 candidates, assemble features:
     → Item features: price, category, rating, freshness, popularity
     → User features: age cohort, location, purchase history summary
     → Cross features: user-item affinity, category match, price range fit
     Cost: ~10ms (batch feature lookup from feature store)

  4. SCORING (ML model inference)
     Apply ranking model to each candidate:
     → Input: Feature vector (50-200 features per candidate)
     → Output: P(engagement) — probability user will click/buy/watch
     → Score 1,000 candidates in one batch inference call
     Cost: ~20ms (GPU/TPU inference, or optimized CPU model)

  5. RE-RANKING (business rules + diversity)
     Sort by model score, then apply:
     → Diversity: No more than 3 items from same category in top 10
     → Freshness: Boost items added in last 24 hours
     → Monetization: Blend in sponsored items at defined positions
     → De-duplication: Remove items user has already seen/purchased
     → Filtering: Remove out-of-stock, age-restricted, policy-violating items
     Cost: ~3ms

  6. RESPONSE
     Return top-N ranked items with metadata for rendering
     → Include: item_id, title, image_url, price, reason ("Because you bought X")
     Cost: ~1ms

  TOTAL: ~55ms (P50), ~100ms (P95), ~200ms (P99)
  BUDGET: Must complete within 150ms to feel instant on page load.
```

## Why a Recommendation System Exists

### 1. The Paradox of Choice

```
PROBLEM: Too many items, not enough attention.

An e-commerce platform with 10 million products:
  → A user can realistically browse 50 items per session
  → That's 0.0005% of the catalog
  → Without recommendations, users see a random or popularity-biased sample
  → They miss items they'd love and waste time on items they don't care about

A content platform with 500 million posts per day:
  → A user can consume ~200 posts per day
  → That's 0.00004% of daily content
  → Without recommendations, the feed is chronological or random
  → Users see noise instead of signal

RECOMMENDATIONS SOLVE THIS:
  → Narrow 10 million items to 50 relevant ones — per user
  → Transform a fire hose of content into a curated experience
  → Each user sees a DIFFERENT set of items, optimized for THEIR interests
```

### 2. Revenue and Engagement Impact

```
BUSINESS IMPACT OF RECOMMENDATIONS:

  E-commerce:
  → 35% of purchases come from recommendation surfaces
  → Recommended items have 2× higher conversion rate than browsed items
  → Average order value is 20% higher when recommendations are shown

  Content platforms:
  → 70% of watch time comes from recommended content (not search)
  → Users who engage with recommendations retain 3× better
  → Time-on-platform increases 40% with good recommendations

  Advertising:
  → Ad recommendations (targeting) drive 80% of ad revenue
  → Better targeting = higher click-through = higher advertiser ROI

  STAFF INSIGHT:
  Recommendations are not a "nice to have" feature. For most large platforms,
  the recommendation system IS the product. The home feed, the "for you" page,
  the "you might also like" widget — these surfaces powered by recommendations
  drive the majority of engagement and revenue. A 1% improvement in
  recommendation quality translates to millions in revenue.
```

### 3. Discovery and Long-Tail Value

```
WITHOUT RECOMMENDATIONS:
  → Users only find items they already know to search for
  → Popular items get all the traffic (rich-get-richer)
  → Long-tail items (niche products, new creators) never get discovered
  → The catalog is underutilized — 80% of items get < 1% of views

WITH RECOMMENDATIONS:
  → Users discover items they didn't know existed
  → Long-tail items surface to the right users
  → New creators / sellers get initial exposure
  → Catalog utilization improves — value is extracted from the full inventory

STAFF INSIGHT:
  A good recommendation system doesn't just show users what they want.
  It shows them what they WOULD want if they knew it existed.
  The difference between "relevance" and "discovery" is the difference
  between a competent system and a great one.
```

## What Happens If the Recommendation System Does NOT Exist (or Fails)

```
SCENARIO 1: No recommendation system — show everyone the same content

  Impact:
  → Home page shows the same popular items to all users
  → No personalization → low engagement
  → Cold start for new items → they never get discovered
  → User retention drops → users move to platforms that personalize
  → Revenue impact: 30-50% drop in key engagement metrics

SCENARIO 2: Recommendation system returns irrelevant results

  Impact (silent failure — the worst kind):
  → Users see items they have no interest in
  → Click-through rate drops
  → Users lose trust in the platform's ability to understand them
  → Users stop browsing recommendations → navigate directly instead
  → Revenue from recommendation surfaces declines

  This is WORSE than no recommendations:
  → No recommendations → users don't expect personalization
  → Bad recommendations → users feel misunderstood, actively annoyed

SCENARIO 3: Recommendation system is slow (> 500ms)

  Impact:
  → Home page renders with empty recommendation slots
  → Users see a loading spinner where recommendations should be
  → If recommendations load after initial render → layout shifts → poor UX
  → If recommendations are waited for → entire page is slow

  Mitigation:
  → Serve cached/pre-computed recommendations on timeout
  → Asynchronously load recommendations after initial page render
  → Pre-compute recommendations for likely next-page-loads

SCENARIO 4: Recommendation system has a feedback loop failure

  Impact:
  → Model continues serving based on old behavior data
  → Recommendations become stale over days/weeks
  → New user interests are not captured
  → Trending items are not surfaced
  → Users gradually disengage as recommendations feel "stuck"

  Staff insight: This is the sneakiest failure because everything
  looks healthy — the system serves fast, returns results, no errors.
  But the feedback loop is broken and results are slowly degrading.
  You MUST monitor feedback loop freshness as a first-class metric.
```

## One Intuitive Mental Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MENTAL MODEL: THE FUNNEL                                 │
│                                                                             │
│   ITEM CORPUS: 10 million items                                             │
│         │                                                                   │
│         ▼                                                                   │
│   ┌────────────────────────────────-─┐                                      │
│   │  RETRIEVAL (cheap, broad)        │  10M → 1,000 candidates              │
│   │  "Which items COULD be relevant?"│  Cost: ~15ms                         │
│   │  Multiple sources in parallel    │  Goal: High recall                   │
│   └─────────────┬───────────────────-┘                                      │
│                 ▼                                                           │
│   ┌──────────────────────────────────┐                                      │
│   │  SCORING (expensive, precise)    │  1,000 → 50 ranked items             │
│   │  "Which items ARE relevant?"     │  Cost: ~20ms                         │
│   │  ML model with rich features     │  Goal: High precision                │
│   └─────────────┬────────────────────┘                                      │
│                 ▼                                                           │
│   ┌──────────────────────────────────┐                                      │
│   │  RE-RANKING (rules, diversity)   │  50 → 20 final items                 │
│   │  "What should the user SEE?"     │  Cost: ~3ms                          │
│   │  Business constraints applied    │  Goal: Balanced feed                 │
│   └─────────────┬────────────────────┘                                      │
│                 ▼                                                           │
│         20 personalized items served to user                                │
│                                                                             │
│   WHY A FUNNEL:                                                             │
│   → You can't score 10M items with an expensive model (10M × 20µs = 200s)   │
│   → You can't retrieve only 20 items (too few → poor diversity, recall)     │
│   → The funnel lets you apply cheap operations broadly and expensive        │
│     operations narrowly — the fundamental cost-quality trade-off            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 2: Functional Requirements (Deep Enumeration)

## Core Use Cases

### 1. Personalized Feed / Home Page Recommendations

```
FUNCTION get_recommendations(user_id, context, page_size, surface):

  INPUT:
    user_id: "user_12345"
    context: {device: "mobile", time: "evening", session_clicks: ["item_A", "item_B"]}
    page_size: 20
    surface: "home_feed"  // Which product surface is requesting

  OUTPUT:
    {
      items: [
        {item_id: "item_789", score: 0.94, reason: "Similar to items you've purchased",
         position: 1, is_sponsored: false},
        {item_id: "item_234", score: 0.89, reason: "Trending in your category",
         position: 2, is_sponsored: false},
        {item_id: "item_567", score: 0.85, reason: "Sponsored",
         position: 3, is_sponsored: true},
        ...
      ],
      metadata: {
        request_id: "req_abc123",
        latency_ms: 62,
        model_version: "ranking_v3.2",
        candidates_retrieved: 1200,
        candidates_scored: 1200,
        fallback_used: false
      }
    }

  BEHAVIOR:
  → Personalized for user_id based on their behavior history
  → Context-aware: Time of day, device, session activity affect ranking
  → Diverse: No single category dominates the feed
  → Fresh: Recently added items are boosted
  → Filtered: Items already viewed, purchased, or blocked are excluded
```

### 2. "Related Items" / "You Might Also Like"

```
FUNCTION get_related_items(item_id, user_id, page_size):

  INPUT:
    item_id: "item_789"  // The item the user is currently viewing
    user_id: "user_12345"  // For personalization (optional)
    page_size: 10

  OUTPUT:
    {
      items: [
        {item_id: "item_456", score: 0.91, relation: "frequently_bought_together"},
        {item_id: "item_123", score: 0.87, relation: "similar_attributes"},
        ...
      ]
    }

  BEHAVIOR:
  → Items related to the anchor item (content similarity + co-interaction)
  → Optionally personalized: If user_id provided, prefer items matching user profile
  → Used on: Product detail pages, video watch pages, article sidebars
```

### 3. Event Ingestion (User Behavior Logging)

```
FUNCTION log_event(event):

  INPUT:
    event: {
      user_id: "user_12345",
      event_type: "click" | "view" | "purchase" | "skip" | "dwell" | "share",
      item_id: "item_789",
      surface: "home_feed",
      position: 3,
      timestamp: "2025-06-20T14:30:00.123Z",
      context: {device: "mobile", session_id: "sess_abc"}
    }

  BEHAVIOR:
  → Events are ingested in real time (< 1 second from user action to event store)
  → Events update the near-real-time feature store (within seconds)
  → Events feed the training pipeline (batch, hours to daily)
  → Events are immutable and append-only (never modified after logging)
  → Events power A/B test analysis (which model variant drove this click?)
```

### 4. Model Deployment

```
FUNCTION deploy_model(model_artifact, surface, rollout_config):

  INPUT:
    model_artifact: {
      model_id: "ranking_v3.2",
      format: "serialized_model",
      features_required: ["user_category_affinity", "item_popularity", ...],
      size_mb: 500
    }
    surface: "home_feed"
    rollout_config: {
      canary_percent: 5,
      ramp_schedule: [5, 25, 50, 100],
      ramp_interval_hours: 24,
      rollback_on: {ctr_drop_percent: 10, latency_increase_ms: 50}
    }

  BEHAVIOR:
  → Model loaded onto serving infrastructure without restart
  → Canary: 5% of traffic uses new model, 95% uses current
  → Metrics monitored: CTR, latency, error rate, diversity
  → Auto-rollback if guardrail metrics violated
  → Ramp: Progressive increase to 100% over days
```

## Read Paths

```
READ PATH 1: Home feed recommendations
  Client → API Gateway → Recommendation Service → Candidate Retrieval
  → Feature Assembly → Model Scoring → Re-ranking → Response

READ PATH 2: Related items
  Client → API Gateway → Related Items Service → Item-to-Item Index
  → Feature Assembly → Model Scoring → Re-ranking → Response

READ PATH 3: Pre-computed recommendations (fallback)
  Client → API Gateway → Cache/Pre-computed Store → Response
  (Used when real-time scoring is slow or unavailable)
```

## Write Paths

```
WRITE PATH 1: User event ingestion
  Client → Event Collector → Event Stream (message queue)
  → Fan-out to: Feature Store (real-time update), Event Archive (batch),
    A/B Test Analyzer, Real-time Signal Processor

WRITE PATH 2: Item catalog update
  Item Service → Item Event Stream → Item Feature Extractor
  → Item Index Update, Feature Store Update

WRITE PATH 3: Model training output
  Training Pipeline → Model Registry → Model Serving Infrastructure
  (Batch process, runs daily or weekly)

WRITE PATH 4: Feature pipeline output
  Batch Feature Pipeline → Feature Store (daily)
  Streaming Feature Pipeline → Feature Store (real-time)
```

## Control / Admin Paths

```
ADMIN PATH 1: A/B experiment configuration
  Admin → Experiment Platform → Traffic splitting configuration
  → Define: Model variants, traffic allocation, success metrics, guardrails

ADMIN PATH 2: Business rule configuration
  Admin → Rules Engine → Diversity rules, boost/bury rules, position constraints
  → Rules apply at re-ranking stage, per surface

ADMIN PATH 3: Feature pipeline monitoring
  Admin → Pipeline Dashboard → Feature freshness, pipeline lag, data quality

ADMIN PATH 4: Model performance monitoring
  Admin → Metrics Dashboard → CTR, NDCG, diversity, latency per model version
```

## Edge Cases

```
EDGE CASE 1: New user with zero history (cold start)
  → No collaborative filtering possible (no interaction history)
  → Fall back to: Popular items → Demographic-based → Content-based
    (as interactions accumulate)
  → Transition: After 5-10 interactions, begin collaborative filtering blend

EDGE CASE 2: New item with zero interactions (item cold start)
  → No co-interaction data available
  → Use content-based features: Category, attributes, description embedding
  → Exploration: Inject new items into recommendation slots at low rate
    to collect initial interaction data
  → The "exploration-exploitation" trade-off: Show known-good items
    (exploit) vs show new items to learn about them (explore)

EDGE CASE 3: User behavior changes rapidly (intent shift)
  → User browsed electronics all week, now browsing baby products
  → Batch features (updated daily) still reflect electronics preference
  → Real-time features (session-level) detect baby product browsing
  → System must blend: Real-time session signals + long-term preferences
  → Real-time features should override long-term preferences for current session

EDGE CASE 4: Items go out of stock during recommendation generation
  → Item retrieved and scored, but sold out before user clicks
  → Post-scoring filter removes out-of-stock items
  → Alternative: Inventory check at retrieval time (adds latency)
  → Trade-off: Accept occasional out-of-stock recommendations (frustrating but rare)
    vs real-time inventory integration (complex, adds latency)

EDGE CASE 5: User has blocked/hidden an item or category
  → Block list stored per user in profile
  → Applied as hard filter during candidate retrieval
  → Items from blocked categories never enter the scoring stage

EDGE CASE 6: Recommendation request during model deployment rollout
  → Some serving instances have new model, some have old
  → Routing ensures a single user consistently gets the same model version
    (sticky routing by user_id hash) to avoid result instability
  → If both models are loaded, A/B test framework selects model per user
```

## What Is Intentionally OUT of Scope

```
OUT OF SCOPE:
1. ML model architecture and training
   → How the ranking model is built (neural net, gradient boosting, etc.)
   → Feature engineering (which features to create)
   → Training pipeline infrastructure (distributed training, GPUs)
   → This is ML platform scope, not recommendation system scope

2. Ad targeting and auction
   → Recommendation for ads involves auction mechanics, bid optimization
   → Significantly different system design (real-time auction, pricing)
   → Covered separately as an ad system design

3. Content moderation and safety
   → Filtering harmful/illegal content from recommendations
   → Trust & Safety is a separate system that provides signals
   → Recommendation system consumes moderation decisions, doesn't make them

4. Natural language explanation generation
   → "Why was this recommended?" — generating explanations
   → Important for user trust, but a separate NLP/generation problem

WHY SCOPE IS LIMITED:
Each excluded item is a Staff-level system in its own right.
This chapter focuses on the SERVING INFRASTRUCTURE — how recommendations
are generated, scored, and delivered at scale with low latency.
```

---

# Part 3: Non-Functional Requirements (Reality-Based)

## Latency Expectations

```
RECOMMENDATION SERVING LATENCY:
  P50:  < 50ms    (most requests use cached features, fast model inference)
  P95:  < 100ms   (complex feature assembly, large candidate sets)
  P99:  < 200ms   (cold cache, slow feature store, large model)

  WHY THESE NUMBERS:
  → Recommendations are on the critical path of page load
  → Users perceive delays > 200ms as "the page is slow"
  → Mobile users on poor networks already add 100-200ms RTT
  → The recommendation system gets 100ms of a 300ms total budget

  LATENCY BREAKDOWN BUDGET:
  → Feature assembly: 10ms
  → Candidate retrieval: 15ms (parallel across sources)
  → Model scoring: 20ms
  → Re-ranking: 3ms
  → Overhead (serialization, network): 7ms
  → Total: ~55ms (P50)

FEEDBACK LOOP LATENCY:
  → User action to feature update: < 5 seconds
    (A click right now should influence recommendations within seconds)
  → User action to model update: Hours to days (batch training)
  → WHY: Real-time feature updates provide session-level adaptation.
    Model retraining provides long-term learning. Both are needed.
```

## Availability Expectations

```
TARGET: 99.95% availability (< 4.4 hours downtime/year)

WHY NOT 99.99%:
  → Recommendations have graceful fallback: If real-time ranking fails,
    serve pre-computed or popular items
  → Users can still browse, search, and navigate without recommendations
  → 99.99% for a system that depends on ML inference, feature stores,
    and multiple retrieval sources is very expensive to achieve

AVAILABILITY DEFINITION:
  Available = Returns a non-empty list of items within timeout
  Degraded = Returns pre-computed/cached items (not personalized)
  Unavailable = Returns empty or error

GRACEFUL DEGRADATION LEVELS:
  Level 0: Full real-time personalized ranking (normal operation)
  Level 1: Cached recent recommendations for this user (< 1 hour old)
  Level 2: Pre-computed segment-based recommendations (updated daily)
  Level 3: Global popular items (always available, no personalization)

  STAFF INSIGHT:
  The recommendation system should NEVER return empty results.
  Even during a complete outage, pre-computed fallbacks should serve
  reasonable content. An empty recommendation slot is a lost
  engagement opportunity — worse than showing popular items.
```

## Consistency Needs

```
CONSISTENCY MODEL: EVENTUAL CONSISTENCY (by design)

  User clicks item at T=0:
  → T=0: Click event sent to event stream
  → T+500ms: Real-time feature store updated (user's recent clicks)
  → T+1s: Next recommendation request uses updated features
  → T+6h: Batch training pipeline incorporates click into model update
  → T+12h: New model deployed, recommendations reflect learned patterns

  IMPLICATIONS:
  → A user's behavior takes seconds to affect real-time features
  → A user's behavior takes hours to affect the model
  → Two recommendation requests at the same time may return different results
    (different feature store replicas, different model instances)

  WHY EVENTUAL CONSISTENCY IS ACCEPTABLE:
  → Recommendations are inherently approximate — "best guess" not "exact answer"
  → Users don't expect deterministic results (feeds change on every refresh)
  → The value is in aggregate quality, not per-request precision
  → Strong consistency would require coordinating feature reads across
    multiple stores → massive latency penalty for negligible quality gain

  WHERE STRONGER GUARANTEES ARE NEEDED:
  → Item filtering: If an item is deleted or marked unsafe, it MUST be
    removed from recommendations within minutes (not hours)
  → User block list: If a user blocks a category, that filter MUST be
    applied immediately (hard filter at retrieval)
  → These are SAFETY constraints, not relevance constraints — different SLO
```

## Durability

```
DURABILITY: EVENTS ARE SACRED, FEATURES AND SCORES ARE DERIVED

  WHAT MUST BE DURABLE:
  → User interaction events: The raw log of every click, view, purchase
    → This is the ground truth for model training and analysis
    → Replicated, retained for years
  → Item catalog: The source of truth for what items exist
    → Lives in the item service's database

  WHAT IS EPHEMERAL:
  → Feature store values: Derived from events, rebuildable
  → Model artifacts: Regenerated by training pipeline
  → Cached recommendations: Stale after hours, replaced on next request
  → Candidate indices: Rebuilt periodically from catalog + events

  STAFF INSIGHT:
  The event stream is the single most important data asset in the
  recommendation system. Every model, every feature, every evaluation
  metric is derived from events. Losing events = losing the ability
  to train, debug, and improve the system.
```

## Correctness vs User Experience Trade-offs

```
TRADE-OFF 1: Exploration vs exploitation
  EXPLOIT: Show items the model is confident the user will like
  → High short-term engagement
  → Risk: Filter bubble — user only sees narrow content
  EXPLORE: Show items the system is uncertain about to learn user preferences
  → Lower short-term engagement (some shown items won't be liked)
  → Benefit: Better long-term model, helps new items get discovered
  CHOICE: 90% exploit / 10% explore, adjustable per surface

TRADE-OFF 2: Personalization vs diversity
  PURE PERSONALIZATION: Show only items matching user's strongest signals
  → User sees: 20 running shoes (because they browsed running shoes)
  → High relevance per item, terrible experience (no variety)
  DIVERSITY: Ensure variety in categories, price ranges, content types
  → User sees: 5 running shoes, 3 fitness accessories, 2 apparel, ...
  → Lower per-item relevance, much better overall experience
  CHOICE: Enforce diversity constraints at re-ranking stage

TRADE-OFF 3: Freshness vs proven quality
  FRESH: Prioritize newly added items
  → Good for: Marketplaces, news, social content
  → Risk: New items have no quality signals → may be low quality
  PROVEN: Prioritize items with strong engagement history
  → Good for: E-commerce (proven sellers), video (high-rated content)
  → Risk: New items never get discovered (cold start)
  CHOICE: Per-surface configuration. News feed: heavy freshness.
  Product recommendations: moderate freshness boost for first 48 hours.

TRADE-OFF 4: Latency vs ranking quality
  FULL MODEL: Score all 2,000 candidates with the most accurate model
  → Better ranking, higher latency (30ms for large model)
  LIGHTWEIGHT MODEL: Score with a distilled/smaller model
  → Slightly worse ranking, much lower latency (5ms)
  CHOICE: Multi-stage: Lightweight model filters 2,000 → 200,
  full model scores 200 → 20. Best of both worlds.
```

## Security Implications

```
USER PRIVACY:
  → Recommendation systems know intimate details about user preferences
  → Behavior logs contain: What users look at, how long, what they buy
  → These are HIGH-VALUE targets for data breaches
  → GDPR/CCPA: Users can request deletion of all their behavior data
    → Must cascade: Events, features, model training data, cached recommendations

DATA MINIMIZATION:
  → Store only behavior data needed for recommendation quality
  → Aggregate or anonymize where possible
  → Avoid storing raw behavioral data longer than necessary
  → Use user ID hashing in logs shared across teams

MANIPULATION:
  → Fake accounts can generate fake interactions to boost items
  → Click farms can manipulate collaborative filtering signals
  → Sellers can game the system by self-purchasing their own items
  → Mitigation: Anomaly detection on interaction patterns,
    rate limiting on feedback events, trust scoring for users
```

## SLO/SLI Framework

```
SLI 1: Recommendation Latency
  Measurement: P99 of end-to-end recommendation serving latency
  SLO: P99 < 200ms

SLI 2: Recommendation Availability
  Measurement: % of requests returning a non-empty item list
  SLO: > 99.95% (including fallback responses)

SLI 3: Feature Freshness
  Measurement: P95 lag between user event and feature store update
  SLO: < 10 seconds

SLI 4: Model Freshness
  Measurement: Age of the currently serving model
  SLO: < 48 hours (model retrained and deployed at least daily)

SLI 5: Recommendation Quality (online)
  Measurement: Click-through rate on recommendation surface
  SLO: CTR > baseline threshold (varies by surface)
  Alert: CTR drops > 10% vs 7-day rolling average

ERROR BUDGET:
  99.95% availability = 21.6 minutes of downtime per month
  Budget management: Freeze non-critical deployments if > 50% consumed
```

---

# Part 4: Scale & Load Modeling (Concrete Numbers)

## Users and Traffic

```
SCALE ASSUMPTIONS (large platform):

  Users:
    Total registered users:       500 million
    Daily active users (DAU):     100 million
    Average sessions per user:    3 / day
    Recommendation requests per session: 5 (feed loads, pagination, related items)

  RECOMMENDATION QPS:
    Average: 100M × 3 × 5 / 86,400 = ~17,000 QPS
    Peak (2× average):            ~35,000 QPS
    Spike (product launch event):  ~100,000 QPS

  Item corpus:
    Total items:                  10 million
    New items per day:            50,000
    Updated items per day:        500,000
    Deleted items per day:        10,000

  Event volume:
    Events per user per day:      50 (views, clicks, purchases, scrolls)
    Total events per day:         5 billion
    Events per second (avg):      ~58,000 events/sec
    Events per second (peak):     ~200,000 events/sec

  READ:WRITE RATIO:
    Recommendation requests : Events = 17,000 : 58,000 ≈ 1:3.4
    
    UNUSUAL: This is WRITE-HEAVY for a serving system.
    The event stream (writes) is 3× the recommendation serving (reads).
    But writes are cheap (append to log), reads are expensive (ML inference).
    CPU cost is dominated by reads; storage cost is dominated by writes.
```

## Capacity Planning

```
FEATURE STORE SIZING:

  User features: 500M users × 2KB per user = 1 TB
  Item features: 10M items × 1KB per item = 10 GB
  Cross features: Precomputed for active users × engaged categories
    → 100M DAU × 20 categories × 50 bytes = 100 GB
  Total feature store: ~1.2 TB (fits in a few hundred GB per replica with compression)

  Feature store reads:
    17,000 QPS × 1,000 candidates × 1 KB = 17 GB/sec aggregate reads
    → Requires: High-throughput, low-latency KV store
    → Solution: In-memory feature store with SSD backing, replicated

MODEL SERVING:

  Model size: 500 MB (serialized ranking model)
  Inference: Score 1,000 candidates per request
  Inference time: 20ms per batch of 1,000
  GPU serving: 1 GPU handles ~1,000 inference requests/sec
  CPU serving: 1 16-core node handles ~200 inference requests/sec
  
  Capacity needed:
  → GPU: 35,000 peak QPS / 1,000 = 35 GPUs
  → CPU (fallback): 35,000 / 200 = 175 CPU nodes
  → CHOICE: GPU for primary serving (lower cost per inference at scale),
    CPU as fallback (available, cheaper to provision)

CANDIDATE INDEX SIZING:

  Collaborative filtering index: 500M users × top 1,000 similar items per user
    → Too large to store fully; use approximate nearest neighbor (ANN)
    → ANN index: 10M items × 128-dim embedding × 4 bytes = 5 GB
    → Replicated on each retrieval node

  Content-based index: 10M items × 128-dim embedding × 4 bytes = 5 GB
  Trending index: 100K trending items with scores = < 10 MB

EVENT PIPELINE:

  Event throughput: 200K events/sec peak × 500 bytes avg = 100 MB/sec
  Storage: 5B events/day × 500 bytes = 2.5 TB/day
  Retention: 90 days raw, 2 years aggregated
  Raw storage: 2.5 TB × 90 = 225 TB
```

## Growth Assumptions

```
GROWTH MODEL:
  Year 1: 100M DAU, 10M items, 35K peak QPS
  Year 2: 200M DAU, 30M items, 70K peak QPS (international expansion)
  Year 3: 500M DAU, 100M items, 150K peak QPS (new surfaces added)

WHAT THIS MEANS FOR ARCHITECTURE:
  → Feature store must scale horizontally (sharded by user_id)
  → Model serving must auto-scale with QPS
  → Candidate retrieval must handle 100M items without full scan
  → Event pipeline must handle 500K events/sec at Year 3
  → Multi-region becomes essential at Year 2 (latency for global users)
```

## Burst Behavior and What Breaks First

```
BURST SCENARIOS:

SCENARIO 1: Product launch event (10× QPS for 1 hour)
  → 10× recommendation QPS = 10× model inference load
  → GPU/CPU saturated → latency spikes → timeout
  → Mitigation: Auto-scale serving nodes, serve cached results during ramp-up

SCENARIO 2: Viral content creates hot-item effect
  → One item appears in 80% of all recommendation requests
  → Feature lookup for that item: 80% of 35K QPS = 28K reads/sec for ONE item
  → Feature store hot key → single-shard overload
  → Mitigation: Hot-key caching in retrieval service, replicate popular item features

SCENARIO 3: Model deployment with cold cache
  → New model deployed → feature cache is cold for new model's features
  → Cache miss rate jumps from 5% to 80% → feature store overloaded
  → Mitigation: Pre-warm feature cache before model switch, shadow scoring

WHAT BREAKS FIRST AT SCALE:
  1. Feature store read throughput (17 GB/sec at peak)
  2. Model inference latency under load (GPU saturation)
  3. Candidate retrieval from ANN index (memory-bound at 100M items)
  4. Event pipeline throughput (500K events/sec)
  5. Feature freshness lag (real-time pipeline falls behind under burst writes)

MOST DANGEROUS ASSUMPTIONS:
  1. "Feature reads are uniform" — Reality: Popular items are read 1000× more
     than tail items. Hot keys will dominate.
  2. "Model inference is constant time" — Reality: Inference time varies with
     feature sparsity, batch size, and GPU contention. Under load, inference
     latency increases non-linearly.
  3. "Candidates are independent" — Reality: Some candidate sources share
     underlying infrastructure. If the collaborative filtering index is slow,
     the content-based index may be on the same nodes.
```

---

# Part 5: High-Level Architecture (First Working Design)

## Core Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                RECOMMENDATION SYSTEM ARCHITECTURE                           │
│                                                                             │
│   ┌──────────────┐                                                          │
│   │   Clients    │  (Mobile apps, web frontend, internal services)          │
│   └──────┬───────┘                                                          │
│          │                                                                  │
│          ▼                                                                  │
│   ┌──────────────────────────────────────────────────────────────────┐      │
│   │                    API GATEWAY                                   │      │
│   │  (Auth, rate limit, A/B traffic split, surface routing)          │      │
│   └──────┬───────────────────────────────────┬───────────────────────┘      │
│          │                                   │                              │
│   ┌──────▼──────────────┐             ┌──────▼──────────────┐               │
│   │ RECOMMENDATION      │             │ EVENT INGESTION     │               │
│   │ SERVING PATH        │             │ PATH                │               │
│   └──────┬──────────────┘             └──────┬──────────────┘               │
│          │                                   │                              │
│   ┌──────▼──────────────┐             ┌──────▼──────────────┐               │
│   │ CANDIDATE RETRIEVAL │             │ EVENT STREAM        │               │
│   │ (Multi-source)      │             │ (Message Queue)     │               │
│   │                     │             └──────┬──────────────┘               │
│   │ ┌─────────────────┐ │                    │                              │
│   │ │ Collab Filtering│ │     ┌──────────────┼──────────────┐               │
│   │ │ Content-Based   │ │     │              │              │               │
│   │ │ Trending        │ │     ▼              ▼              ▼               │
│   │ │ Editorial/Rules │ │   ┌───────┐  ┌───────────┐  ┌──────────┐          │
│   │ └─────────────────┘ │   │Real-  │  │ Event     │  │ Training │          │
│   └──────┬──────────────┘   │time   │  │ Archive   │  │ Pipeline │          │
│          │                  │Feature│  │ (Storage) │  │ (Batch)  │          │
│          ▼                  │Update │  └───────────┘  └──────────┘          │
│   ┌───────────────────────┐ └───┬───┘                      │                │
│   │ FEATURE ASSEMBLY      │     │                          │                │
│   │ (Batch + Real-time)   │◄────┘                          │                │
│   └──────┬────────────────┘                                │                │
│          │                                                 │                │
│          ▼                                                 ▼                │
│   ┌──────────────────────┐              ┌──────────────────────┐            │
│   │ MODEL SCORING        │              │ MODEL REGISTRY       │            │
│   │ (GPU/CPU inference)  │◄─────────────│ (Versioned models)   │            │
│   └──────┬───────────────┘              └──────────────────────┘            │
│          │                                                                  │
│          ▼                                                                  │
│   ┌──────────────────────┐                                                  │
│   │ RE-RANKING           │                                                  │
│   │ (Business rules,     │                                                  │
│   │ diversity, filtering)│                                                  │
│   └──────┬───────────────┘                                                  │
│          │                                                                  │
│          ▼                                                                  │
│   Response to Client                                                        │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                    FEATURE STORE                                      │ │
│   │  (User features + Item features + Cross features)                     │ │
│   │  Batch pipeline (daily) + Streaming pipeline (real-time)              │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   ┌──────────────────────┐  ┌──────────────────────┐                        │
│   │ EXPERIMENT PLATFORM  │  │ FALLBACK STORE       │                        │
│   │ (A/B test config)    │  │ (Pre-computed recs)  │                        │
│   └──────────────────────┘  └──────────────────────┘                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

```
API GATEWAY:
  → Authenticate request, identify user
  → Determine A/B test bucket for this user
  → Route to correct model serving instance
  → Rate limit per-surface, per-client
  → Log request metadata for monitoring

CANDIDATE RETRIEVAL (stateless, reads from indices):
  → Retrieve candidates from multiple sources in PARALLEL
  → Each source is an independent index optimized for its retrieval strategy
  → Collaborative filtering: User embedding → ANN index → similar items
  → Content-based: Item embedding → ANN index → similar items to recent views
  → Trending: Sliding-window popularity index → top items by region/category
  → Editorial: Pre-configured item lists by business team
  → Deduplicate union of all candidates
  → Apply hard filters: Out-of-stock, blocked, already seen

FEATURE ASSEMBLY (stateless, reads from feature store):
  → For each candidate, batch-lookup features from feature store
  → User features: Long-term preferences, demographics, activity level
  → Item features: Price, category, rating, popularity, freshness
  → Cross features: User-item affinity (pre-computed), price range match
  → Real-time features: Session clicks, recency of last interaction
  → Output: Feature matrix [num_candidates × num_features]

MODEL SCORING (stateless, loads model from registry):
  → Load serialized ranking model into memory (or GPU)
  → Apply model to feature matrix → vector of scores
  → Score = P(engagement) for each candidate
  → Batch inference: Score all candidates in one forward pass

RE-RANKING (stateless, reads rules from config):
  → Sort candidates by model score (descending)
  → Apply business rules:
    - Diversity: Spread categories, price ranges
    - Freshness boost: New items get temporary score boost
    - Monetization: Insert sponsored items at defined positions
    - De-duplication: Remove items already shown in this session
    - Content policy: Remove flagged items
  → Output: Final ordered list of N items

EVENT INGESTION:
  → Receive user events (clicks, views, purchases) in real time
  → Write to durable event stream (message queue)
  → Fan out to consumers: Feature store updater, event archive, 
    A/B test analyzer, real-time signal processor

FEATURE STORE:
  → Serves features for scoring at read time
  → Two update paths:
    - Batch: Daily pipeline computes aggregated features from event archive
    - Streaming: Real-time pipeline updates session-level features from event stream
  → Access pattern: Point lookups by user_id or item_id
  → Replicated for read throughput, sharded by key

MODEL REGISTRY:
  → Stores versioned model artifacts
  → Manages model lifecycle: Training → Validation → Canary → Production
  → Supports rollback to previous version

EXPERIMENT PLATFORM:
  → Assigns users to A/B test buckets (deterministic by user_id hash)
  → Routes recommendation requests to appropriate model version
  → Collects metrics per experiment variant
  → Provides statistical analysis of experiment results

FALLBACK STORE:
  → Pre-computed recommendation lists (popular items, segment-based)
  → Updated daily by batch pipeline
  → Served when real-time ranking is unavailable or slow
```

## Stateless vs Stateful Decisions

```
STATELESS:
  → Candidate retrieval service: Reads from indices, no session state
  → Feature assembly: Batch reads from feature store, no local state
  → Model scoring: Loads model into memory, but model is read-only shared state
  → Re-ranking: Pure function of scores + rules

STATEFUL:
  → Feature store: Holds user and item features (primary state)
  → Candidate indices: ANN index, trending index (derived state, rebuildable)
  → Event stream: Durable log of all user events
  → Model registry: Versioned model artifacts

STAFF INSIGHT:
  Keep the hot path (retrieval → features → scoring → re-ranking) STATELESS.
  All state lives in the feature store and candidate indices, which are
  read-only from the serving path's perspective. This enables:
  → Horizontal scaling of serving nodes
  → Independent deployment without draining
  → Instant failover (no session state to migrate)
  → Per-request load balancing
```

---

# Part 6: Deep Component Design (NO SKIPPING)

## Component 1: Candidate Retrieval

### Internal Design

```
CANDIDATE RETRIEVAL IS THE RECALL STAGE — IT DETERMINES THE CEILING.

If a good item is not retrieved, no ranking model can surface it.
Retrieval must be broad (high recall) and fast (< 15ms).

MULTI-SOURCE ARCHITECTURE:

  Source 1: COLLABORATIVE FILTERING (personalized)
    How: User embedding → ANN (Approximate Nearest Neighbor) search
    → Find items whose embeddings are closest to user's embedding
    
    User embedding: Dense vector (128 dimensions) computed from user's
    interaction history using matrix factorization or deep learning.
    
    Item embedding: Dense vector (128 dimensions) computed from item's
    interaction patterns (which users engaged with it).
    
    ANN search: HNSW (Hierarchical Navigable Small World) graph index
    → Query: Find top-500 items closest to user embedding
    → Time: ~5ms for 10M items
    → Accuracy: Approximate — may miss 5-10% of true nearest neighbors
    → Trade-off: Exact NN search would take 100ms (too slow)
    
    Output: 500 candidates with similarity scores

  Source 2: CONTENT-BASED (item similarity)
    How: Item embedding → ANN search for similar items
    → Based on user's recent interactions, find similar items
    
    Input: User's last 10 viewed/clicked items
    For each: Find top-50 similar items by content embedding
    Union: ~300 unique candidates (overlaps across seed items)
    
    Content embedding: Computed from item attributes (title, category,
    description, image features). NOT based on user interactions.
    
    WHY BOTH: Collaborative filtering captures "users like you bought X"
    Content-based captures "this item is similar to what you're viewing"
    They surface different items — union increases recall.

  Source 3: TRENDING (recency + popularity)
    How: Sliding-window popularity score per region/category
    → Items with highest engagement in last 4 hours
    → Filtered by user's active categories
    
    Index: Pre-computed, updated every 5 minutes
    → Category → ranked list of trending items
    Output: 200 candidates

  Source 4: EDITORIAL / BUSINESS (curated)
    How: Pre-configured lists by business team
    → New arrivals, seasonal promotions, sponsored placements
    Output: 100 candidates

  MERGE AND DEDUPLICATE:
    Union of all sources: ~1,100 candidates
    After deduplication: ~1,000 unique candidates
    Apply hard filters: Remove out-of-stock, blocked, already purchased
    After filtering: ~800-1,000 candidates pass to scoring

ALL FOUR SOURCES RUN IN PARALLEL:
  Wall-clock time: max(source_latency) ≈ 10-15ms
  Not sequential: 5ms + 8ms + 2ms + 1ms = 16ms sequential, 8ms parallel
```

### Why Simpler Alternatives Fail

```
ALTERNATIVE: Single source (collaborative filtering only)
  PROBLEM: Cold start — new users have no embedding, new items have no interactions
  → 100% of new users get zero results
  → 10% of items (new arrivals) are never surfaced
  → Content-based fills the cold start gap

ALTERNATIVE: Score ALL items with the ranking model (no retrieval stage)
  PROBLEM: 10M items × 20µs per scoring = 200 seconds per request
  → Physically impossible to serve in 100ms
  → The retrieval stage exists to reduce the candidate set to a tractable size

ALTERNATIVE: Pre-compute recommendations for all users (no real-time retrieval)
  PROBLEM: 500M users × 20 items × 4 bytes per item_id = 40 GB of pre-computed lists
  → Stale within hours (user behavior changes)
  → Can't incorporate real-time session signals
  → Acceptable as FALLBACK, not as primary serving path
```

## Component 2: Feature Store

### Internal Design

```
THE FEATURE STORE IS THE MEMORY OF THE RECOMMENDATION SYSTEM.

It stores everything the model needs to score a candidate:
  → Who is this user? (User features)
  → What is this item? (Item features)
  → How does this user relate to this item? (Cross features)

DATA MODEL:
  Key: (entity_type, entity_id, feature_group)
  Value: Serialized feature vector

  Examples:
  → (user, user_12345, profile): {age_bucket: "25-34", gender: "M", country: "US"}
  → (user, user_12345, behavior): {clicks_7d: 45, purchases_7d: 3, categories: [1,5,7]}
  → (user, user_12345, session): {last_click_item: "item_789", session_clicks: 5,
                                    session_duration_sec: 120}
  → (item, item_789, static): {category: "shoes", price: 49.99, brand: "Nike"}
  → (item, item_789, dynamic): {views_7d: 15000, ctr_7d: 0.03, avg_rating: 4.2}

DUAL-PATH UPDATES:

  BATCH PATH (daily, comprehensive):
    → Full computation of all features from event archive
    → User behavior aggregates: 7-day clicks, 30-day purchases, category affinities
    → Item aggregates: Popularity, CTR, conversion rate
    → Cross features: User-category affinity scores
    → Output: Full feature snapshot overwriting previous values
    → Advantage: Comprehensive, consistent, handles all features
    → Disadvantage: Stale by up to 24 hours

  STREAMING PATH (real-time, incremental):
    → Processes events as they arrive from event stream
    → Updates: Session-level features (last click, session duration)
    → Updates: Real-time counters (clicks in last hour, trending score)
    → Advantage: Fresh within seconds
    → Disadvantage: Limited to features that can be incrementally updated
      (e.g., counters, latest values — NOT complex aggregations)

  MERGE STRATEGY:
    → Batch features are the BASELINE (comprehensive, daily)
    → Streaming features OVERLAY batch features (real-time, session-level)
    → At read time: Merge batch + streaming features
    → If streaming value exists, it overrides batch value for that feature
    → If streaming pipeline is down, batch features still serve (degraded freshness)

ACCESS PATTERN:
  → Point lookup: get_features(user_id, feature_group) → feature vector
  → Batch lookup: get_features_batch([user_12345, user_67890, ...]) → batch of vectors
  → Read throughput: 17K QPS × 1,000 candidates × 3 lookups ≈ 50M reads/sec
    → This is the HIGHEST throughput component in the system
    → Must be: In-memory, replicated, sharded

STORAGE:
  → In-memory hash map (primary serving layer)
  → SSD-backed for overflow (features that don't fit in memory)
  → Sharded by entity_id (user_id or item_id)
  → Replicated 3× for read throughput and availability
  → Total memory: ~1.2 TB across all replicas (fits in 10-20 high-memory nodes)
```

### Failure Behavior

```
FAILURE: Feature store read timeout
  → Impact: Cannot assemble features → cannot score
  → Mitigation: Return cached features from local cache (TTL: 1 hour)
  → If cache miss: Use default feature values (population averages)
  → Quality degradation: Recommendations are less personalized but functional

FAILURE: Streaming pipeline down (batch features still available)
  → Impact: Real-time features are stale (session signals not updated)
  → Mitigation: Serve from batch features only — 6-24 hours stale
  → Quality degradation: Recommendations don't adapt to current session
    but still reflect user's long-term preferences

FAILURE: Batch pipeline down (streaming features still available)
  → Impact: Aggregated features (7-day trends) become stale
  → Mitigation: Continue serving — batch features age but don't expire
  → Quality degradation: Slowly increasing staleness over days
  → Alert: If batch pipeline hasn't run in 48 hours → PAGE

STAFF INSIGHT:
  The feature store has the most complex failure behavior because
  it has two independent update paths. The system must function
  with either path down, both paths down (serve from cache/defaults),
  or both paths healthy. This creates 4 operating modes that must
  all be tested and monitored.
```

## Component 3: Model Scoring Service

### Internal Design

```
THE SCORING SERVICE APPLIES ML MODELS TO FEATURE VECTORS.

ARCHITECTURE:
  → Model loaded into memory (GPU or CPU) at startup
  → Receives: Batch of (candidate_id, feature_vector) pairs
  → Returns: Batch of (candidate_id, score) pairs
  → Stateless: Model is read-only shared state

BATCH INFERENCE:
  → Score all ~1,000 candidates in a single batch inference call
  → GPU: 1,000 candidates × 200 features → 1,000 scores in ~20ms
  → CPU: Same batch → ~50ms (2.5× slower, acceptable for fallback)
  → WHY BATCH: Individual inference has fixed overhead per call.
    Batching amortizes overhead across candidates. 1,000 individual
    calls = 1,000 × 1ms = 1 second. 1 batch call = 20ms.

MODEL LOADING:
  → Model stored in model registry (versioned blob store)
  → At deployment: Model downloaded to serving node, loaded into GPU memory
  → Hot-swap: New model loaded alongside old model, traffic switched atomically
  → Rollback: Switch traffic back to previous model (< 1 second)

MULTI-MODEL SERVING:
  → Different surfaces may use different models:
    - home_feed: Full ranking model (500 MB, complex neural net)
    - related_items: Lightweight model (50 MB, gradient-boosted tree)
    - notifications: Simplified model (10 MB, logistic regression)
  → Each surface's model loaded independently
  → Resource isolation: home_feed model doesn't compete with related_items

SCORING PIPELINE PSEUDO-CODE:
  FUNCTION score_candidates(candidates, user_features, model_id):
    model = model_cache.get(model_id)
    
    // Assemble feature matrix
    feature_matrix = []
    FOR candidate IN candidates:
      item_features = feature_store.get(candidate.item_id)
      cross_features = compute_cross_features(user_features, item_features)
      feature_vector = concat(user_features, item_features, cross_features)
      feature_matrix.append(feature_vector)
    
    // Batch inference
    scores = model.predict(feature_matrix)  // One call, all candidates
    
    RETURN zip(candidates, scores)
```

### Failure Behavior

```
FAILURE: GPU out of memory (model too large or too many concurrent requests)
  → Detection: CUDA OOM error during inference
  → Impact: Scoring fails for that request
  → Mitigation: Fall back to CPU scoring (slower but available)
  → Prevention: Load testing to determine max concurrent batches per GPU

FAILURE: Model returns NaN or extreme scores
  → Detection: Score validation after inference (NaN check, range check)
  → Impact: If uncaught, items with NaN may sort unpredictably
  → Mitigation: Replace NaN scores with 0.0 (item drops to bottom of ranking)
  → Alert: NaN rate > 0.1% → PAGE (model is producing garbage)

FAILURE: Model version mismatch with feature schema
  → Cause: New model expects feature X, but feature store doesn't have it
  → Detection: Feature vector has wrong dimensionality
  → Impact: Model crashes or produces meaningless scores
  → Prevention: Model + feature schema deployed as atomic pair
    Model metadata declares required features; serving validates at load time.
```

## Component 4: Re-Ranking Engine

### Internal Design

```
RE-RANKING APPLIES BUSINESS CONSTRAINTS THAT THE ML MODEL CANNOT LEARN.

The model optimizes for a single objective (e.g., P(click)).
But the business has multi-objective requirements:
  → Diversity: Don't show 20 running shoes
  → Freshness: Surface new items
  → Monetization: Insert ads/sponsored items
  → Fairness: Don't under-represent certain sellers/creators
  → Compliance: Remove flagged content

RE-RANKING ALGORITHM:
  FUNCTION rerank(scored_candidates, rules, context):
    // Sort by model score
    sorted = scored_candidates.sort_by(score, descending)
    
    // Apply diversity constraint
    final_list = []
    category_counts = {}
    FOR candidate IN sorted:
      cat = candidate.category
      IF category_counts.get(cat, 0) >= rules.max_per_category:
        CONTINUE  // Skip — too many from this category
      final_list.append(candidate)
      category_counts[cat] = category_counts.get(cat, 0) + 1
      IF len(final_list) >= context.page_size:
        BREAK
    
    // Apply freshness boost
    FOR i, candidate IN final_list:
      IF candidate.age_hours < 24:
        // Move fresh items up by N positions (capped)
        boost_positions = min(3, i)
        move_up(final_list, i, boost_positions)
    
    // Insert sponsored items at defined positions
    FOR slot IN rules.sponsored_positions:
      IF slot.position < len(final_list):
        sponsored_item = get_sponsored_item(context.user_id, context.surface)
        IF sponsored_item:
          final_list.insert(slot.position, sponsored_item)
    
    // Final filter: Remove already-seen items
    final_list = filter_seen(final_list, context.session_seen_items)
    
    RETURN final_list

WHY RULES AT RE-RANKING (NOT IN THE MODEL):
  → Business rules change frequently (daily/weekly)
  → Model retraining takes days — too slow for rule changes
  → Rules are explicit and auditable — model behavior is opaque
  → Different surfaces have different rules — one model, many rule sets
  → Rules are the CONTROL LAYER that business teams can adjust
    without touching the ML pipeline
```

---

# Part 7: Data Model & Storage Decisions

## What Data Is Stored

```
DATA CATEGORY 1: User Interaction Events (source of truth)
  → Every click, view, purchase, skip, dwell, share
  → Schema: {user_id, item_id, event_type, timestamp, context}
  → Size: 5B events/day × 500 bytes = 2.5 TB/day
  → Retention: 90 days raw, 2 years aggregated
  → Access: Write-heavy (append only), read by training/feature pipelines

DATA CATEGORY 2: User Features (derived)
  → Profile: Age bucket, country, language, account age
  → Behavioral: Category affinities, price preferences, activity level
  → Session: Recent clicks, session duration, current browsing context
  → Size: 500M users × 2 KB = 1 TB
  → Access: Read-heavy (feature store lookups during scoring)

DATA CATEGORY 3: Item Features (derived)
  → Static: Title, category, price, brand, description embedding
  → Dynamic: Popularity (7-day views), CTR, conversion rate, avg rating
  → Size: 10M items × 1 KB = 10 GB
  → Access: Read-heavy (feature store lookups during scoring)

DATA CATEGORY 4: Embeddings / Indices (derived)
  → User embeddings: 500M × 128 dims × 4 bytes = 256 GB
  → Item embeddings: 10M × 128 dims × 4 bytes = 5 GB
  → ANN indices: HNSW graph over item embeddings (~10 GB with overhead)
  → Access: Read-heavy (ANN search during candidate retrieval)

DATA CATEGORY 5: Model Artifacts (derived)
  → Serialized ranking models (100 MB – 1 GB each)
  → Multiple versions stored for rollback
  → Size: ~10 GB total (10 versions × 1 GB)
  → Access: Read once per deployment, held in memory during serving

DATA CATEGORY 6: Pre-computed Recommendations (derived, fallback)
  → Per-user: Top 100 recommendations, refreshed daily
  → Per-segment: Top 100 per demographic segment
  → Global: Top 100 popular items
  → Size: 100M DAU × 100 items × 8 bytes = 80 GB
  → Access: Read on fallback, written daily by batch pipeline
```

## How Data Is Keyed and Partitioned

```
FEATURE STORE:
  Key: (entity_type, entity_id)
  → User features: Shard by user_id (hash-based)
  → Item features: Shard by item_id (hash-based)
  → Sharding ensures even distribution and parallel reads

EVENT STREAM:
  Key: user_id (for event ordering within a user)
  Partition: Hash of user_id → ensures per-user ordering
  → All events for one user go to the same partition
  → Enables: Sequential processing of a user's event history

PRE-COMPUTED RECOMMENDATIONS:
  Key: user_id
  Shard: Hash of user_id
  → Simple KV lookup: user_id → list of item_ids with scores

ANN INDEX:
  Not partitioned in the simple case (10M items fits in memory on one node)
  At scale (100M items): Shard by item_id range, each shard holds a sub-index
  → Query fans out to all shards, merges top-K results (like search scatter-gather)
```

## Retention Policies

```
RAW EVENTS:
  → 90 days: Full fidelity, used for model retraining and debugging
  → After 90 days: Aggregated into daily/weekly summaries, raw deleted
  → 2 years: Aggregated summaries retained for long-term analysis

USER FEATURES:
  → No explicit retention — continuously updated by pipelines
  → Deleted users: Features purged within 30 days (GDPR/CCPA compliance)

ITEM FEATURES:
  → Deleted items: Features purged within 24 hours
  → Active items: Continuously updated

MODEL ARTIFACTS:
  → Keep last 10 versions for rollback
  → Older versions archived to cold storage for audit

PRE-COMPUTED RECOMMENDATIONS:
  → Refreshed daily, previous version overwritten
  → No long-term retention (derived, rebuildable)
```

## Schema Evolution

```
FEATURE SCHEMA CHANGES:

  ADDING A FEATURE:
  → New feature added to feature pipeline (batch or streaming)
  → Feature store schema extended (backward compatible — new field, nullable)
  → Model trained with new feature
  → Model deployed — reads new feature from store
  → Old model versions continue working (ignore new feature)
  
  REMOVING A FEATURE:
  → Verify no active model uses the feature
  → Stop computing the feature in pipeline
  → Feature ages out of store (TTL or next full refresh)
  → Backward compatible — models that don't need it are unaffected

  CHANGING A FEATURE:
  → Change is effectively: Add new feature + deprecate old feature
  → Both coexist during transition
  → New model uses new feature, old model uses old feature
  → After old model is decommissioned, remove old feature

STAFF INSIGHT:
  Feature schema changes are the most dangerous operational activity
  in a recommendation system (more dangerous than model changes).
  A model change is self-contained — it reads features and produces scores.
  A feature change affects ALL models that use that feature.
  Always use additive changes, never in-place modifications.
```

## Why Other Data Models Were Rejected

```
REJECTED: Relational database for feature storage
  → WHY ATTRACTIVE: ACID guarantees, familiar SQL
  → WHY REJECTED: 50M reads/sec point lookups. Relational databases
    optimize for complex queries, not ultra-high-throughput KV access.
    Overhead of SQL parsing, query planning for simple key lookups is waste.

REJECTED: Graph database for recommendation
  → WHY ATTRACTIVE: User-item interactions are naturally a graph
  → WHY REJECTED: Graph traversal for recommendation is O(depth × branching).
    At 500M users and 10M items, random walks are slow and unpredictable.
    ANN search on dense embeddings is more efficient and predictable.
    Graph databases excel at relationship queries, not bulk scoring.

REJECTED: Single monolithic model instead of multi-stage pipeline
  → WHY ATTRACTIVE: Simpler architecture, one model to maintain
  → WHY REJECTED: One model scoring 10M items = 200 seconds.
    The funnel architecture exists because scoring is expensive.
    Retrieval (cheap) reduces the set; scoring (expensive) ranks it.
```

---

# Part 8: Consistency, Concurrency & Ordering

## Strong vs Eventual Consistency

```
RECOMMENDATION SYSTEMS ARE EVENTUAL BY NATURE.

The system serves approximate, probabilistic results. Exact consistency
adds latency without measurable quality improvement.

WHAT IS EVENTUALLY CONSISTENT:
  → User features: Updated seconds (streaming) to hours (batch) after events
  → Item features: Updated seconds (streaming) to hours (batch) after changes
  → Model: Updated hours to days after new training data is available
  → Candidate index: Updated every few hours (ANN index rebuild)

WHAT IS STRONGLY CONSISTENT:
  → Item availability: If an item is deleted, it MUST be removed from
    recommendations within minutes (safety/compliance)
  → User block lists: If a user blocks a category, the filter MUST be
    applied on the NEXT request (user expectation)
  → These are implemented as hard filters in the re-ranking stage,
    reading from a strongly consistent filter store, NOT from the
    eventually consistent feature store.
```

## Race Conditions

```
RACE CONDITION 1: User purchases item while recommendation is in flight
  → T=0: User requests recommendations → system retrieves item_789 as candidate
  → T=50ms: User purchases item_789 in a separate request
  → T=80ms: Recommendation response includes item_789
  → User sees: An item they just purchased recommended to them

  MITIGATION:
  → Real-time filter: Before responding, check against user's very-recent
    purchases (maintained in a fast cache updated on purchase events)
  → Acceptable: This race is narrow (50ms window) and impacts < 0.01% of requests
  → Over-engineering: Distributed transaction between recommendation and
    purchase systems would add 50ms latency to ALL requests for a 0.01% case

RACE CONDITION 2: Model deployment during scoring
  → T=0: Scoring starts with model_v3.1
  → T=10ms: Model hot-swap occurs → model_v3.2 loaded
  → T=20ms: Scoring completes — used v3.1 for first half, v3.2 for second?

  MITIGATION:
  → Model reference is captured at request start (snapshot semantics)
  → All candidates in one request scored with the SAME model version
  → Hot-swap only affects NEW requests, not in-flight ones

RACE CONDITION 3: Feature update during feature assembly
  → T=0: Feature assembly starts, reads user_12345's features
  → T=5ms: Streaming pipeline updates user_12345's session features
  → T=10ms: Feature assembly for remaining candidates reads updated features
  → Some candidates scored with old features, some with new

  MITIGATION:
  → Batch read: All features for one request fetched in one batch call
  → Feature snapshot consistency per request (read from same replica)
  → Acceptable: Feature staleness of a few milliseconds is negligible
```

## Idempotency

```
EVENT INGESTION:
  → Events may be delivered more than once (at-least-once delivery)
  → Deduplication: (user_id, item_id, event_type, timestamp) as dedup key
  → Duplicate events: Counted once in feature aggregations
  → WHY AT-LEAST-ONCE: Losing events degrades model quality.
    Duplicate events are cheap to filter; lost events are unrecoverable.

RECOMMENDATION SERVING:
  → Naturally idempotent: Same request → same features → same scores
  → Not EXACTLY the same (feature store may update between requests)
  → But deterministic within a single request execution

MODEL DEPLOYMENT:
  → Idempotent: Deploying the same model version twice → no-op
  → Model version is the idempotency key
```

## Ordering Guarantees

```
EVENT ORDERING:
  → Events for the SAME user are ordered (same partition in event stream)
  → Events for DIFFERENT users are NOT ordered (different partitions)
  → This is sufficient: We need to know user_12345's click sequence,
    but we don't need global ordering across all users

FEATURE UPDATE ORDERING:
  → Batch features: Full snapshot replace (no ordering needed)
  → Streaming features: Applied in event order per user
  → Cross-user ordering not needed (features are per-entity)

RECOMMENDATION ORDERING:
  → Items within a response are strictly ordered by final ranking score
  → Across requests: No ordering guarantee (features may change)
  → Users expect feeds to change on refresh — this is a feature, not a bug
```

---

# Part 9: Failure Modes & Degradation (MANDATORY)

## Partial Failures

```
FAILURE 1: One candidate source fails (e.g., collaborative filtering index down)
  CAUSE: ANN index node failure, network partition
  SYMPTOMS: Fewer candidates retrieved (1,000 → 500)
  USER IMPACT: Slightly less diverse recommendations (missing one signal source)
  DEGRADATION:
  → Other sources still return candidates
  → Scoring and re-ranking proceed normally on smaller candidate set
  → Quality degradation is measurable but not catastrophic
  → Log: "candidate_source_cf: unavailable" for monitoring

FAILURE 2: Feature store partially unavailable (some user features missing)
  CAUSE: Feature store shard failure, replication lag
  SYMPTOMS: Feature assembly returns default values for missing features
  USER IMPACT: Recommendations less personalized (using population defaults)
  DEGRADATION:
  → Model receives default feature values → scores are less accurate
  → Results are biased toward popular items (population defaults favor popularity)
  → Acceptable for short periods (< 1 hour)
  → Alert if sustained: Feature store shard failure needs immediate attention

FAILURE 3: Model scoring timeout
  CAUSE: GPU overload, model inference too slow
  SYMPTOMS: Scoring exceeds latency budget
  USER IMPACT: Varies by fallback strategy
  DEGRADATION:
  → Level 1: Score with lightweight CPU model (less accurate, faster)
  → Level 2: Return cached recent recommendations for this user
  → Level 3: Return pre-computed segment-based recommendations
  → Level 4: Return global popular items
  → Users ALWAYS see recommendations — never an empty slot
```

## Slow Dependencies

```
SLOW DEPENDENCY 1: Feature store reads slow (50ms instead of 5ms)
  CAUSE: Feature store overload, hot key, GC pause
  SYMPTOMS: Total latency exceeds SLO
  USER IMPACT: Slow page load or fallback to cached recommendations
  DEGRADATION:
  → Reduce candidate set (score 200 instead of 1,000)
  → Fewer feature lookups → lower feature store load
  → Quality slightly lower, latency within budget
  → Circuit breaker: If feature store P99 > 20ms for 1 minute,
    switch to cached features only

SLOW DEPENDENCY 2: Event pipeline lagging (features not updating)
  CAUSE: Burst event volume, consumer processing slow
  SYMPTOMS: Feature freshness exceeds SLO
  USER IMPACT: Recommendations don't reflect recent behavior
  DEGRADATION:
  → Serving continues normally (stale features, not missing features)
  → Session-level personalization degrades
  → Alert: Feature freshness > 5 minutes → WARN
  → Alert: Feature freshness > 30 minutes → PAGE
```

## Feedback Loop Failure

```
THE MOST INSIDIOUS FAILURE MODE IN RECOMMENDATION SYSTEMS.

FAILURE: Training pipeline stops, model stops learning

  T=0:    Training pipeline fails (data corruption, infra issue)
  T+1d:   Model is 1 day old — still reasonable
  T+3d:   Model is 3 days old — missing recent trends
  T+7d:   New items from the last week have no model signal
          Trending topics have shifted but model doesn't know
          Users who changed preferences are getting stale recommendations
  T+14d:  Significant engagement metric decline (CTR down 5-10%)
          User complaints: "My feed isn't relevant anymore"
  T+30d:  Major revenue impact, user retention declining

  WHY THIS IS HARD TO DETECT:
  → System looks healthy: Serving fast, no errors, returning results
  → Quality degradation is gradual, not sudden
  → No single metric has a clear "model is stale" signal
  → The failure is in the ABSENCE of something (new learning) not the
    PRESENCE of something (errors)

  DETECTION:
  → Monitor model deployment frequency: Alert if no new model deployed in 48 hours
  → Monitor training pipeline completion: Alert if last training run was > 24 hours ago
  → Monitor online metrics trend: Alert if CTR shows downward trend for 3+ days
  → Canary metric: Train a fresh model on last 24h of data, compare against
    production model on a held-out set. If fresh model is significantly better,
    the production model is stale.

  MITIGATION:
  → Automated training pipeline with health monitoring
  → Pipeline failure → PAGE (not WARN — this is critical)
  → Keep last known-good training data snapshot for emergency retrain
  → Multiple independent pipeline paths (daily full retrain + incremental updates)
```

## Failure Timeline Walkthrough

```
T=0:00  GPU serving cluster node fails
        → 2 of 10 GPU nodes go offline
        → Capacity drops 20% → some requests queue

T=0:01  Load balancer detects unhealthy nodes
        → Routes traffic to remaining 8 GPU nodes
        → Per-node load increases 25%
        → P99 latency rises from 100ms → 180ms

T=0:05  Latency SLO violated (P99 > 200ms)
        → Auto-scaler triggered → provisioning additional GPU nodes
        → Meanwhile: Requests exceeding 200ms timeout switch to CPU fallback

T=0:10  CPU fallback handles overflow traffic
        → 20% of requests scored on CPU (50ms inference vs 20ms GPU)
        → Quality: Same model, same features — identical scores, just slower
        → User impact: Slight latency increase, no quality degradation

T=0:15  Auto-scaler brings 2 new GPU nodes online
        → Model loaded, warmup inference complete
        → Traffic gradually shifted to new nodes

T=0:20  Full GPU capacity restored
        → P99 latency returns to normal (100ms)
        → CPU fallback traffic drops to 0%

TOTAL USER IMPACT: 15 minutes of slightly elevated latency
                   0 empty recommendation responses
                   0 quality degradation (same model on CPU and GPU)
```

## Cascading Failure: Feature Store Overload

```
T=0:00  TRIGGER: Popular item goes viral, becomes hot key in feature store
        → item_999 requested in 80% of recommendation requests
        → Feature store shard holding item_999 receives 28K reads/sec (hot key)

T=0:05  Hot shard overloaded
        → P99 feature read latency: 5ms → 100ms
        → Recommendation requests that need item_999 features slow down

T=0:10  Recommendation service timeout cascade
        → 80% of requests time out waiting for feature store
        → Clients retry → 1.6× request volume
        → Remaining feature store shards now also under pressure

T=0:15  Circuit breaker activates
        → Feature store circuit breaker opens for hot shard
        → Requests for item_999 features return default values
        → Other items continue normal feature serving

T=0:20  Quality degrades but system stays up
        → item_999 scored with default features → likely ranked lower than deserved
        → Other items scored normally → overall quality acceptable
        → Users see recommendations — some less personalized than ideal

T=0:25  Hot key mitigation kicks in
        → Local cache for item_999 features populated from last successful read
        → Cache serves item_999 features for all subsequent requests
        → Feature store hot shard pressure drops

T=0:30  System recovers
        → Hot key cache warm
        → All shards back to normal load
        → P99 latency returns to normal

PREVENTION:
  → Hot key detection: Monitor per-key read rate
  → Popular item cache: Cache top-1,000 items' features locally on serving nodes
  → Feature store replication: Extra replicas for popular key ranges
  → Rate limiting per-key: No single key can consume > 10% of shard capacity
```

---

# Part 10: Performance Optimization & Hot Paths

## Critical Paths

```
THE HOTTEST PATH: Feature Assembly → Model Scoring

  Feature Assembly:
  → 1,000 candidates × 3 feature lookups × 1 KB = 3 MB of data read per request
  → At 35K QPS: 3 MB × 35K = 105 GB/sec aggregate feature reads
  → This is the I/O BOTTLENECK of the entire system

  Model Scoring:
  → 1,000 candidates × 200 features × 4 bytes = 800 KB input tensor
  → GPU forward pass: ~20ms
  → At 35K QPS on 35 GPUs: Each GPU handles 1,000 inferences/sec
  → This is the COMPUTE BOTTLENECK of the entire system
```

## Caching Strategies

```
CACHE LAYER 1: Feature cache (serving node level)
  WHAT: Recently accessed user and item features
  HIT RATE: 60-80% for item features (popular items repeat), 
            30-50% for user features (users revisit within session)
  TTL: 5 minutes (balance freshness vs cache benefit)
  SIZE: 10 GB per serving node

CACHE LAYER 2: Recommendation result cache (API gateway level)
  WHAT: Full recommendation response cached by (user_id, surface, context_hash)
  HIT RATE: 10-20% (users reload pages, same session)
  TTL: 60 seconds (very short — recommendations should feel fresh)
  SIZE: 1 GB per gateway node

CACHE LAYER 3: Pre-computed recommendations (fallback)
  WHAT: Pre-computed per-user recommendation lists from daily batch pipeline
  HIT RATE: 100% (pre-computed for all active users)
  TTL: 24 hours (refreshed daily)
  SIZE: 80 GB (100M users × 100 items × 8 bytes)

CACHE ANTI-PATTERN: Long TTL on user features
  → Stale user features = stale recommendations
  → A user who changed behavior 1 hour ago still sees old recommendations
  → Maximum feature cache TTL: 5 minutes for batch features
  → Session features: Never cached (must be real-time)
```

## Precomputation vs Runtime

```
PRECOMPUTED (offline pipelines):
  → User embeddings: Batch-computed daily from interaction history
  → Item embeddings: Batch-computed on item catalog changes
  → ANN index: Rebuilt every few hours from latest embeddings
  → Trending items: Updated every 5 minutes from sliding-window counts
  → Pre-computed recommendations: Daily batch for all active users

RUNTIME (per-request):
  → Feature assembly: Must be per-request (features are user+item specific)
  → Model scoring: Must be per-request (personalized per user)
  → Re-ranking: Must be per-request (session-aware, rule-dependent)
  → Candidate retrieval: Per-request ANN search on precomputed index

WHAT WE INTENTIONALLY DO NOT PRECOMPUTE:
  → Full ranking for all users × all items
    10M items × 500M users = 5 × 10^15 pairs. Impossible.
  → Session-aware re-ranking: Depends on what user has seen THIS session
  → Cross-feature computation: User-item cross features are pair-specific
```

## Load Shedding

```
PRIORITY TIERS:
  Tier 1 (never shed): Home feed recommendations (primary engagement surface)
  Tier 2 (shed at 80%): Related items on product pages
  Tier 3 (shed at 60%): Email/notification recommendations
  Tier 4 (shed at 40%): Background pre-computation jobs

PER-REQUEST COST MANAGEMENT:
  → Under load, reduce candidate set: 1,000 → 200 candidates
  → Fewer feature lookups, less scoring work
  → Quality degrades gracefully, latency stays within budget
  → Auto-scale threshold: If shedding active for > 5 minutes → add capacity
```

---

# Part 11: Cost & Efficiency

## Major Cost Drivers

```
COST BREAKDOWN:

  1. GPU COMPUTE (40% of total cost):
     → 35 GPUs for model inference at peak
     → GPUs are expensive: ~$2-3/hour each = ~$70K/month
     → This is the dominant cost driver

  2. FEATURE STORE (25% of total cost):
     → 20 high-memory nodes (128 GB+ RAM each) for in-memory serving
     → SSD-backed overflow storage
     → 3× replication for availability and read throughput
     → ~$40K/month

  3. EVENT PIPELINE & STORAGE (20% of total cost):
     → 2.5 TB/day × 90 days retention = 225 TB raw event storage
     → Stream processing infrastructure for real-time features
     → Batch processing infrastructure for daily feature computation
     → ~$30K/month

  4. CANDIDATE INDICES & SERVING (10% of total cost):
     → ANN index nodes (in-memory, replicated)
     → API gateway and routing infrastructure
     → ~$15K/month

  5. TRAINING INFRASTRUCTURE (5% of total cost):
     → GPU cluster for model training (used periodically, not 24/7)
     → Data processing for training data preparation
     → ~$8K/month

  TOTAL: ~$160K/month at the assumed scale
```

## How Cost Scales

```
SCALING DIMENSION → COST DRIVER:
  More QPS → More GPU nodes (linear), more feature store replicas
  More users → More feature store storage (linear)
  More items → Larger ANN index (sub-linear, ANN scales well)
  More events → More storage, more streaming pipeline capacity
  Better model → Larger model → more GPU memory → more expensive GPUs

COST PER RECOMMENDATION:
  $160K/month / (17K QPS × 86,400 sec × 30 days) = ~$0.000004 per recommendation
  → Extremely cheap per request, expensive in aggregate
```

## Cost-Aware Redesign

```
SCENARIO: Reduce recommendation infrastructure cost by 50%

APPROACH:
  1. DISTILL MODEL (saves 30% GPU cost)
     → Train a smaller "student" model that mimics the large "teacher" model
     → Student model: 50 MB instead of 500 MB
     → Inference: 5ms instead of 20ms → 4× throughput per GPU
     → Quality loss: 1-2% lower CTR (acceptable for most surfaces)

  2. REDUCE CANDIDATE SET (saves 15%)
     → Score 300 candidates instead of 1,000
     → 70% fewer feature lookups, 70% less scoring work
     → Quality impact: Top-10 results almost identical,
       diversity slightly lower in positions 10-20

  3. INCREASE PRE-COMPUTATION (saves 10%)
     → Pre-compute recommendations for top 10M most active users
     → Serve pre-computed results for 80% of requests
     → Real-time scoring only for 20% of requests (cold cache, new users)
     → Trade: 6-24 hour staleness for pre-computed users

  4. REDUCE EVENT RETENTION (saves 5%)
     → 90 days → 30 days raw retention
     → Model quality impact: Minimal (most signal is in recent 30 days)

  RESULT: 50% cost reduction with ~2% quality degradation
```

---

# Part 12: Multi-Region & Global Considerations

## Why Multi-Region for Recommendations

```
REASONS:
  1. LATENCY: Global users need < 100ms response.
     Cross-region RTT: 80-150ms → exceeds entire latency budget.
  2. AVAILABILITY: Regional failure shouldn't disable recommendations globally.
  3. DATA LOCALITY: User behavior data may have residency requirements.
```

## Replication Strategy

```
RECOMMENDED: LEADER-FOLLOWER WITH REGIONAL SERVING

  ┌──────────┐     ┌──────────┐     ┌──────────┐
  │ US-East  │     │ US-West  │     │ EU-West  │
  │          │     │          │     │          │
  │ Feature  │     │ Feature  │     │ Feature  │
  │ Store    │────→│ Store    │     │ Store    │
  │ (Leader) │     │(Follower)│     │(Follower)│
  │          │     │          │     │          │
  │ Scoring  │     │ Scoring  │     │ Scoring  │
  │ Nodes    │     │ Nodes    │     │ Nodes    │
  └──────────┘     └──────────┘     └──────────┘
       ↑                ↑                ↑
       │                │                │
  Events from      Events from      Events from
  US users         US users         EU users

  → Events ingested at nearest region
  → Feature updates computed centrally (or per-region)
  → Feature store replicated to all regions
  → Model served identically in all regions
  → Replication lag: < 5 seconds for feature updates

  WHY LEADER-FOLLOWER:
  → Recommendations tolerate eventual consistency
  → Feature staleness of seconds is acceptable
  → Avoids multi-leader conflict resolution complexity
  → Central training pipeline produces one model deployed globally
```

## When Multi-Region Is NOT Worth It

```
SKIP MULTI-REGION WHEN:
  → All users in one geography
  → Recommendation latency budget is generous (> 300ms)
  → Event volume is low enough for single-region processing
  → Cost of 3× infrastructure exceeds recommendation revenue impact
```

---

# Part 13: Security & Abuse Considerations

## Abuse Vectors

```
ABUSE 1: Click fraud / fake engagement
  → Fake accounts generate clicks to boost certain items
  → Collaborative filtering learns from fake signal → recommends boosted items
  → Mitigation: Click quality scoring, velocity-based anomaly detection,
    trust scoring per user (new/low-trust accounts weighted less)

ABUSE 2: Recommendation manipulation by sellers
  → Sellers create fake accounts to self-buy/self-review their items
  → Items appear "popular" and get recommended more
  → Mitigation: Network analysis (detect buyer-seller rings),
    unusual conversion rate patterns, manual review for flagged items

ABUSE 3: Data harvesting through recommendation API
  → Competitor scrapes recommendations to map item relationships
  → Rate limiting per user, require authentication, monitor access patterns

ABUSE 4: Privacy attack via recommendation inference
  → Attacker infers user's preferences by observing recommendation changes
  → "If I follow this user and see their public recommendations change after
    they view an item, I can infer what they viewed"
  → Mitigation: Don't expose recommendation reasoning to other users,
    add noise to recommendation explanations
```

## Privilege Boundaries

```
SERVING API: Authenticated, per-user scoped recommendations only
ADMIN API: Role-based access for A/B test config, business rules
TRAINING PIPELINE: Access to anonymized/aggregated events only
EVENT STORE: Strict access control, audit logging, encryption at rest

GDPR/CCPA:
  → Right to deletion: Delete user events + features + pre-computed recommendations
  → Right to explanation: "Why was this recommended?" must be answerable
  → Opt-out: Users can disable personalization → receive non-personalized popular items
```

---

# Part 14: Evolution Over Time (CRITICAL FOR STAFF)

## V1: Naive Design

```
V1: POPULARITY-BASED RECOMMENDATIONS

  Architecture:
  → Batch job computes top-100 items by sales/clicks per category
  → Results stored in database
  → On request: Look up user's preferred categories → return popular items
  → No personalization beyond category preferences
  → Updated daily

  Works for:
  → < 1M items
  → < 1K QPS
  → Early product stage (not enough user data for personalization)

  Limitations:
  → Same recommendations for all users in same category
  → No long-tail discovery
  → Stale (daily refresh)
```

## What Breaks First

```
BREAK POINT 1: Users want personalization (~10K DAU)
  → Popular items bore returning users → engagement drops
  → SOLUTION: Collaborative filtering (users like you bought X)

BREAK POINT 2: Latency too high for real-time scoring (~50K QPS)
  → Scoring all items per request: Too slow
  → SOLUTION: Multi-stage funnel (cheap retrieval, expensive scoring)

BREAK POINT 3: Model takes days to reflect new behavior
  → Batch pipeline → stale features → stale recommendations
  → SOLUTION: Streaming feature pipeline for real-time signals

BREAK POINT 4: Single model can't serve multiple surfaces
  → Home feed, related items, notifications all need different ranking
  → SOLUTION: Multi-model serving with per-surface configuration

BREAK POINT 5: No way to measure if changes improve recommendations
  → Deploy new model → hope it's better → check metrics days later
  → SOLUTION: A/B testing platform with real-time experiment analysis
```

## V2: Personalized, Single-Region

```
V2: MULTI-STAGE RANKING WITH COLLABORATIVE FILTERING

  Architecture:
  → Candidate retrieval: Collaborative filtering + content-based
  → Feature store: Batch-computed daily features
  → Model scoring: Single ranking model per surface
  → Re-ranking: Basic diversity and freshness rules
  → A/B testing: Simple traffic splitting

  Handles:
  → 10M items
  → 35K peak QPS
  → 100M DAU
  → Daily model retraining
  → Basic personalization

  Limitations:
  → Single region → high latency for global users
  → Daily features → slow adaptation to behavior changes
  → No real-time session signals
  → Limited exploration → filter bubble risk
```

## V3: Long-Term Stable Architecture

```
V3: MULTI-REGION, REAL-TIME, MULTI-SURFACE PLATFORM

  Architecture:
  → Multi-source candidate retrieval (CF + content + trending + editorial)
  → Dual-path feature store (batch + streaming)
  → Multi-model scoring (per-surface, GPU primary, CPU fallback)
  → Sophisticated re-ranking (diversity, fairness, monetization)
  → Full A/B testing platform with guardrail metrics
  → Multi-region serving with leader-follower replication
  → Pre-computed fallback recommendations at every degradation level
  → Automated model deployment with canary + rollback

  Handles:
  → 100M items
  → 150K peak QPS
  → 500M DAU
  → Real-time feature updates (seconds)
  → Multiple surfaces with independent models
  → Multi-region with < 100ms latency globally
```

## How Incidents Drive Redesign

```
INCIDENT 1: "The Filter Bubble" (V1 → V2)
  What: Users only saw items from 2-3 categories, engagement plateaued
  Root cause: Popularity-based recommendations reinforce existing patterns
  Redesign: Add collaborative filtering for cross-category discovery,
  add exploration slots for diverse content

INCIDENT 2: "The Stale Feed" (V2 → V3)
  What: User bought a gift for their child, got baby product recommendations for weeks
  Root cause: Batch features (daily) made one purchase dominant signal
  Redesign: Streaming feature pipeline for real-time signal decay,
  session-level context to distinguish gift purchases from self-purchases

INCIDENT 3: "The Viral Collapse" (V2 → V3)
  What: Viral product created hot key in feature store, 30% of requests timed out
  Root cause: No hot-key mitigation in feature store
  Redesign: Local feature cache for popular items, hot-key detection and replication,
  circuit breaker on feature store reads

INCIDENT 4: "The Silent Model Rot" (ongoing)
  What: CTR dropped 5% over 2 weeks, no one noticed until quarterly review
  Root cause: Training pipeline had silently failed, model wasn't retraining
  Redesign: Model freshness SLO, automated alerts on training pipeline health,
  canary metrics comparing production model vs freshly-trained model
```

## Deployment Strategy

```
MODEL DEPLOYMENT (most frequent change):
  → Canary: 5% of traffic for 24 hours
  → Guardrails: CTR, latency, diversity must not regress > 5%
  → Ramp: 5% → 25% → 50% → 100% over 4 days
  → Rollback: Config change, < 1 minute

FEATURE PIPELINE DEPLOYMENT (medium risk):
  → Shadow mode: New pipeline runs alongside old, outputs compared
  → Cutover: Switch feature store reads to new pipeline output
  → Rollback: Point feature store back to old pipeline

SERVING INFRASTRUCTURE DEPLOYMENT (low risk):
  → Rolling restart of stateless serving nodes
  → Canary: 1 node → 10% → 50% → 100%
  → Rollback: Standard blue-green deployment
```

---

# Part 15: Alternatives & Explicit Rejections

## Alternative 1: Pre-Compute All Recommendations Offline

```
WHY ATTRACTIVE:
  → O(1) serving latency — just look up pre-computed list
  → No GPU inference at serving time
  → Simple architecture

WHY A STAFF ENGINEER REJECTS IT:
  → Stale within hours (user behavior changes within sessions)
  → Can't incorporate real-time context (time of day, device, session)
  → Storage: 500M users × 100 items × 8 bytes = 400 GB — feasible but wasteful
  → No session-level personalization
  → ACCEPTABLE AS FALLBACK: Pre-compute for cache misses and degradation
  → UNACCEPTABLE AS PRIMARY: Users expect fresh, session-aware recommendations
```

## Alternative 2: Single-Model End-to-End (No Retrieval Stage)

```
WHY ATTRACTIVE:
  → Simpler architecture — one model does everything
  → No candidate retrieval / scoring split to maintain
  → The model can learn the "retrieval" function

WHY A STAFF ENGINEER REJECTS IT:
  → SCALE: 10M items × 200 features × 20µs = 200 seconds per request
  → Physically impossible to score all items in real time
  → The funnel exists because ML inference is expensive
  → Even with optimization, scoring > 10K items per request exceeds latency budget
  → EXCEPTION: For small catalogs (< 10K items), single-stage is fine
```

## Alternative 3: Rule-Based Recommendations (No ML)

```
WHY ATTRACTIVE:
  → Explainable: "Recommended because you bought X"
  → Deterministic: Same input → same output
  → No training pipeline, no model serving infrastructure
  → Fast to implement

WHY A STAFF ENGINEER REJECTS IT:
  → Can't capture complex patterns (users who buy diapers also buy beer)
  → Doesn't scale with feature dimensionality (100 hand-written rules vs
    200-feature model that learns automatically)
  → Relevance quality plateaus quickly
  → ACCEPTABLE FOR: Cold start (first recommendations for new users)
  → ACCEPTABLE FOR: Business rule layer (on top of ML ranking)
  → UNACCEPTABLE AS: Primary ranking strategy at scale
```

---

# Part 16: Interview Calibration (Staff Signal)

## How Interviewers Probe This System

```
PROBE 1: "How do you generate candidates from a catalog of 10 million items?"
  Testing: Understanding of the funnel architecture, why you can't score all items

PROBE 2: "What happens when a user's behavior changes mid-session?"
  Testing: Real-time features, streaming pipeline, session-level personalization

PROBE 3: "How do you prevent the system from only recommending popular items?"
  Testing: Exploration/exploitation, diversity constraints, long-tail coverage

PROBE 4: "How do you know if a model change improved recommendations?"
  Testing: A/B testing, online vs offline metrics, guardrail metrics, statistical significance

PROBE 5: "What's your fallback if model scoring is too slow?"
  Testing: Graceful degradation stack, pre-computed recommendations, fallback hierarchy

PROBE 6: "How do you handle cold start for new users and new items?"
  Testing: Progressive personalization, content-based fallback, exploration strategy
```

## Common L5 Mistakes

```
MISTAKE 1: "We train a model and serve it"
  → Skipping the funnel: Can't score 10M items per request
  → Missing: Candidate retrieval, feature store, re-ranking

MISTAKE 2: Ignoring the feedback loop
  → Treating the system as "model + serving" without discussing
    how user events flow back to improve the model
  → The feedback loop IS the system — without it, recommendations are static

MISTAKE 3: "Use a single source for candidates"
  → Single source (e.g., only collaborative filtering) has blind spots
  → Cold start users get nothing, cold start items never surface
  → Multi-source retrieval is the Staff-level answer

MISTAKE 4: No fallback strategy
  → "If the model is down, we return an error"
  → Staff answer: Degradation stack — cached → pre-computed → popular → never empty

MISTAKE 5: Not addressing diversity
  → "The model scores items, we return the top ones"
  → Without diversity constraints, users get 20 nearly-identical items
  → Re-ranking with business rules is essential
```

## Staff-Level Answers

```
STAFF ANSWER 1: "The system is a funnel: Retrieval narrows 10M items to 1,000
  candidates cheaply, scoring ranks 1,000 to 50 precisely, and re-ranking
  applies business constraints. Each stage has its own latency budget and
  quality role."

STAFF ANSWER 2: "The feedback loop is a first-class component, not an afterthought.
  Events flow in real-time to the feature store for session-level adaptation,
  and in batch to the training pipeline for model improvement. If the feedback
  loop breaks, the system looks healthy but slowly degrades."

STAFF ANSWER 3: "Cold start is a staged migration problem. New users start
  with popular items, transition to content-based after a few interactions,
  and reach collaborative filtering after sufficient history. The system
  must gracefully blend these strategies without the user noticing transitions."

STAFF ANSWER 4: "I'd design the system with four fallback levels: real-time
  personalized → cached recent → segment-based → global popular. Users should
  always see recommendations — the question is how personalized they are,
  not whether they exist."
```

## Example Phrases a Staff Engineer Uses

```
"Let me start with the funnel architecture, because you can't score
10 million items per request."

"The candidate retrieval stage determines the CEILING of recommendation quality.
If a relevant item isn't retrieved, no amount of ranking can surface it."

"I need a dual-path feature store: batch features for long-term signals,
streaming features for session-level adaptation."

"The feedback loop is the most critical component to monitor. A broken
training pipeline is invisible for days but causes 10% CTR decline."

"Diversity isn't just a nice-to-have. Without it, the feed converges
to a filter bubble and engagement drops long-term."

"I'd instrument the fallback stack and measure how often each level is used.
If Level 3 (popular items) triggers more than 0.1% of the time, we have
an infrastructure reliability problem."
```

---

# Part 17: Diagrams (MANDATORY)

## Diagram 1: Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                RECOMMENDATION SYSTEM: FULL ARCHITECTURE                     │
│                                                                             │
│   ┌──────────┐                                                              │
│   │  Client  │                                                              │
│   └────┬─────┘                                                              │
│        │                                                                    │
│        ▼                                                                    │
│   ┌──────────────────────────────────────────────────────┐                  │
│   │              API GATEWAY + A/B TEST ROUTING          │                  │
│   └────┬────────────────────────────────────┬────────────┘                  │
│        │  SERVING PATH (read)               │  EVENT PATH (write)           │
│        ▼                                    ▼                               │
│   ┌────────────────┐                   ┌────────────────┐                   │
│   │  Candidate     │                   │  Event Stream  │                   │
│   │  Retrieval     │                   │(Message Queue) │                   │
│   │  ┌──────────┐  │                   └────┬───────────┘                   │
│   │  │CF │CB│T│E│  │                        │                               │
│   │  └──────────┘  │        ┌───────────────┼────────────┐                  │
│   └────┬───────────┘        │               │            │                  │
│        ▼                    ▼               ▼            ▼                  │
│   ┌────────────────┐   ┌──────────┐   ┌──────────┐ ┌──────────┐             │
│   │  Feature       │   │ Streaming│   │  Event   │ │ Training │             │
│   │  Assembly      │◄──│ Feature  │   │ Archive  │ │ Pipeline │             │
│   │                │   │ Pipeline │   │(Storage) │ │ (Batch)  │             │
│   └────┬───────────┘   └──────────┘   └──────────┘ └────┬─────┘             │
│        ▼                                                │                   │
│   ┌────────────────┐                             ┌──────▼─────┐             │
│   │  Model Scoring │◄────────────────────────────│   Model    │             │
│   │  (GPU/CPU)     │                             │  Registry  │             │
│   └────┬───────────┘                             └────────────┘             │
│        ▼                                                                    │
│   ┌────────────────┐                                                        │
│   │  Re-Ranking    │                                                        │
│   │ (Rules+Diverse)│                                                        │
│   └────┬───────────┘                                                        │
│        ▼                                                                    │
│   ┌────────────┐   ┌────────────────────────────────────────────┐           │
│   │  Response  │   │           FEATURE STORE                    │           │
│   └────────────┘   │  ┌────────────┐    ┌────────────────┐      │           │
│                    │  │ Batch Layer│    │ Streaming Layer│      │           │
│                    │  │ (daily)    │    │ (real-time)    │      │           │
│                    │  └────────────┘    └────────────────┘      │           │
│                    └────────────────────────────────────────────┘           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 2: The Multi-Stage Ranking Funnel

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE RECOMMENDATION FUNNEL                                │
│                                                                             │
│   10,000,000 items in catalog                                               │
│        │                                                                    │
│        ▼                                                                    │
│   ┌──────────────────────────────────────────────────────┐                  │
│   │  RETRIEVAL (cheap, parallel, high recall)            │    ~15ms         │
│   │                                                      │                  │
│   │  Collaborative Filtering → 500 candidates            │                  │
│   │  Content-Based          → 300 candidates             │                  │
│   │  Trending               → 200 candidates             │                  │
│   │  Editorial              → 100 candidates             │                  │
│   │  Union + Dedup          → 1,000 candidates           │                  │
│   └──────────────────────────────┬───────────────────────┘                  │
│                                  │                                          │
│                          1,000 candidates                                   │
│                                  │                                          │
│                                  ▼                                          │
│   ┌──────────────────────────────────────────────────────┐                  │
│   │  SCORING (expensive, precise, high precision)        │    ~20ms         │
│   │                                                      │                  │
│   │  Feature Assembly: User + Item + Cross features      │                  │
│   │  ML Model Inference: P(engagement) per candidate     │                  │
│   │  Sort by score → Top 50                              │                  │
│   └──────────────────────────────┬───────────────────────┘                  │
│                                  │                                          │
│                            50 scored items                                  │
│                                  │                                          │
│                                  ▼                                          │
│   ┌──────────────────────────────────────────────────────┐                  │
│   │  RE-RANKING (rules, diversity, business)             │    ~3ms          │
│   │                                                      │                  │
│   │  Diversity enforcement (max 3 per category)          │                  │
│   │  Freshness boost (new items moved up)                │                  │
│   │  Sponsored insertion (defined positions)             │                  │
│   │  Already-seen filter (session dedup)                 │                  │
│   │  → Final 20 items                                    │                  │
│   └──────────────────────────────┬───────────────────────┘                  │
│                                  │                                          │
│                       20 personalized items                                 │
│                       served to user (~55ms total)                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 3: Failure Degradation Stack

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    GRACEFUL DEGRADATION STACK                               │
│                                                                             │
│   Level 0: FULL PERSONALIZED RANKING (normal)                               │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │ Multi-source retrieval → Real-time features → GPU scoring       │       │
│   │ → Business rules re-ranking                                     │       │
│   │ Quality: ★★★★★   Latency: 55ms   Personalization: Full          │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│        │ IF: Model slow or GPU overloaded                                   │
│        ▼                                                                    │
│   Level 1: CPU SCORING WITH REDUCED CANDIDATES                              │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │ Reduced retrieval (300 candidates) → Cached features → CPU      │       │
│   │ Quality: ★★★★☆   Latency: 80ms   Personalization: Good          │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│        │ IF: Feature store unavailable                                      │
│        ▼                                                                    │
│   Level 2: CACHED RECENT RECOMMENDATIONS                                    │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │ Return last successful recommendations for this user (< 1hr)    │       │
│   │ Quality: ★★★☆☆   Latency: 5ms    Personalization: Stale         │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│        │ IF: No cached results (new user, cache expired)                    │
│        ▼                                                                    │
│   Level 3: PRE-COMPUTED SEGMENT RECOMMENDATIONS                             │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │ Pre-computed lists by demographic segment (updated daily)       │       │
│   │ Quality: ★★☆☆☆   Latency: 3ms    Personalization: Segment       │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│        │ IF: Segment lookup fails                                           │
│        ▼                                                                    │
│   Level 4: GLOBAL POPULAR ITEMS                                             │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │ Static list of globally popular items (always in memory)        │       │
│   │ Quality: ★☆☆☆☆   Latency: 1ms    Personalization: None          │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                             │
│   INVARIANT: User ALWAYS sees recommendations. Never an empty slot.         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 4: Evolution Over Time

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RECOMMENDATION SYSTEM EVOLUTION                          │
│                                                                             │
│   V1: POPULARITY-BASED              │  LIMITS:                              │
│   ┌──────────────────────┐          │  No personalization                   │
│   │Batch: Compute popular│          │  < 1K QPS                             │
│   │items per category    │          │  Daily refresh only                   │
│   │Serve: Lookup by      │          │                                       │
│   │category              │          │  BREAKS: Users bore of same items,    │
│   └──────────────────────┘          │  engagement plateaus                  │
│         │                                                                   │
│         ▼                                                                   │
│   V2: PERSONALIZED, SINGLE-REGION   │  LIMITS:                              │
│   ┌──────────────────────┐          │  Single region latency                │
│   │ Retrieval: CF + CB   │          │  Daily features (stale)               │
│   │ Scoring: ML model    │          │  No session adaptation                │
│   │ Features: Batch daily│          │  < 35K QPS                            │
│   │ A/B testing: Basic   │          │                                       │
│   └──────────────────────┘          │  BREAKS: Global latency,              │
│         │                           │  stale recommendations                │
│         ▼                                                                   │
│   V3: MULTI-REGION PLATFORM         │  HANDLES:                             │
│   ┌──────────────────────┐          │  500M DAU, 150K QPS                   │
│   │Multi-source retrieval│          │  Real-time features                   │
│   │Dual-path features    │          │  Multi-surface models                 │
│   │GPU scoring + fallback│          │  Multi-region < 100ms                 │
│   │Full A/B platform     │          │  Automated deployment                 │
│   │Fallback stack        │          │  Per-surface re-ranking               │
│   └──────────────────────┘          │                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 18: Brainstorming, Exercises & Redesigns

## "What If X Changes?" Questions

```
1. What if item catalog grows from 10M to 1B?
   → ANN index must be distributed (sharded across nodes)
   → Retrieval fans out to multiple index shards → scatter-gather
   → Pre-filtering at retrieval stage becomes critical (reduce search space)
   → Embedding dimensionality reduction to manage memory

2. What if you need sub-10ms recommendation latency (edge serving)?
   → Pre-compute recommendations at edge nodes for active users
   → Lightweight re-ranking on edge (session filters, already-seen)
   → Full ranking only for cache misses
   → Trade: Staleness at edge (minutes) vs latency improvement

3. What if the model must incorporate real-time social signals?
   → "Your friend just liked this item" → boost in your recommendations
   → Requires: Real-time social graph integration at scoring time
   → Feature: friend_interactions_last_hour for each candidate
   → Challenge: Social graph lookup adds 10-20ms → tight latency budget

4. What if fairness requirements mandate equal exposure for all sellers?
   → Re-ranking must enforce fairness constraints (min exposure per seller)
   → Conflicts with: Relevance optimization (popular sellers are more relevant)
   → Multi-objective optimization: Relevance + fairness as joint objective
   → Monitoring: Track exposure distribution across sellers

5. What if you need to support conversational recommendations?
   → "Show me something like X but cheaper and in blue"
   → Requires: Query understanding + recommendation fusion
   → Architecture: Parse intent → extract constraints → filter candidates → rank
   → Hybrid system: Search (explicit constraints) + recommendation (preferences)

6. What if you need explainability for every recommendation?
   → "Why was this recommended?" must be answerable
   → Feature attribution: SHAP/LIME on model features
   → Template-based: "Because you purchased {item} in {category}"
   → Trade-off: Explanations add ~5ms latency and storage per recommendation
```

## Redesign Under New Constraints

```
CONSTRAINT 1: Zero GPU budget (CPU only)
  → Distill model to gradient-boosted tree (fast CPU inference)
  → Reduce candidate set to 300 (less scoring work)
  → Increase pre-computation (score top users offline, serve from cache)
  → Accept ~5% CTR degradation vs GPU model

CONSTRAINT 2: Privacy-preserving recommendations (no user tracking)
  → No user features, no behavioral history
  → Content-based only: Recommend based on current item being viewed
  → Session-based: Anonymous session behavior (no cross-session persistence)
  → Contextual: Time of day, device, location-based popularity
  → Significant quality reduction but privacy-compliant

CONSTRAINT 3: Real-time model updates (learn from every click immediately)
  → Online learning: Model updates weights after each interaction
  → Challenge: Model serving and training are coupled (complex)
  → Risk: Model instability (one bad interaction can skew weights)
  → Approach: Bandit algorithms for exploration, online regression for exploitation
  → Reserved for: High-frequency recommendation surfaces (news feed)
```

## Failure Injection Exercises

```
EXERCISE 1: Kill 50% of GPU serving nodes during peak traffic
  OBSERVE: Does fallback to CPU work? What's the latency impact?
  Does auto-scaling respond? How long until recovery?

EXERCISE 2: Inject 100ms latency on all feature store reads
  OBSERVE: Do circuit breakers activate? Do cached features serve?
  What's the quality impact of stale features?

EXERCISE 3: Stop the training pipeline for 7 days
  OBSERVE: When does CTR start declining? How quickly is it detected?
  What's the magnitude of quality degradation?

EXERCISE 4: Make one item appear as a candidate in 90% of requests
  OBSERVE: Does hot-key caching activate? Does the feature store
  hot shard degrade? What's the blast radius?

EXERCISE 5: Deploy a model that assigns random scores to all items
  OBSERVE: Does canary detection catch it? How quickly?
  What's the user impact before rollback?
```

## Trade-Off Debates

```
DEBATE 1: Real-time scoring vs pre-computed recommendations
  REAL-TIME:
  → Fresh, session-aware, context-aware
  → Expensive (GPU, feature store, complex serving)
  → Latency risk (dependent on multiple services)
  
  PRE-COMPUTED:
  → Cheap to serve (KV lookup), always available
  → Stale (hours), no session context
  → Simple infrastructure
  
  STAFF DECISION: Hybrid — real-time primary, pre-computed fallback.
  Most requests served real-time; fallback kicks in automatically on timeout.

DEBATE 2: One global model vs per-surface models
  GLOBAL MODEL:
  → One model to train, validate, deploy
  → More training data (all surfaces contribute)
  → Can't optimize for surface-specific objectives
  
  PER-SURFACE MODELS:
  → Each surface optimized for its context
  → More models to maintain (N models × deployments × monitoring)
  → Less training data per model
  
  STAFF DECISION: Shared base model with per-surface fine-tuning.
  Base model captures general preferences; surface-specific heads
  optimize for surface context. One training pipeline, N output heads.

DEBATE 3: Exploration in the main feed vs separate "discovery" section
  MAIN FEED EXPLORATION:
  → Users naturally encounter new items
  → May degrade engagement (some explored items are bad)
  → Natural, seamless experience
  
  SEPARATE DISCOVERY:
  → Clear user expectation ("I'm exploring")
  → Main feed stays high-quality
  → Lower engagement on discovery section (users skip it)
  
  STAFF DECISION: Both. 90/10 explore-exploit in main feed
  (subtle, 2 slots out of 20 for exploration) + dedicated "Discover" tab.
```

---

# Summary

This chapter has covered the design of a Recommendation / Ranking System at Staff Engineer depth, from the foundational funnel architecture through multi-region serving, feedback loops, and system evolution.

### Key Staff-Level Takeaways

```
1. The funnel is the architecture.
   Retrieval (cheap, broad) → Scoring (expensive, precise) → Re-ranking (rules).
   Each stage has its own latency budget and quality role.

2. The model is 5% of the system.
   Feature store, candidate retrieval, event pipeline, A/B testing,
   serving infrastructure, and fallback stack are the other 95%.

3. The feedback loop is the most critical component to monitor.
   A broken training pipeline is invisible for days but causes major
   quality degradation. Monitor model freshness as a first-class SLO.

4. Cold start is a staged migration, not a binary state.
   Popular → Content-based → Collaborative filtering, blended smoothly.

5. Users should NEVER see an empty recommendation slot.
   The degradation stack ensures content at every failure level:
   Real-time → Cached → Segment → Popular.

6. Diversity is not optional.
   Without diversity constraints, the feed converges to a filter bubble.
   Re-ranking rules are the business team's control surface.

7. Evolution is driven by engagement plateaus and incidents.
   V1 popularity → V2 personalized → V3 real-time multi-surface platform.
   Each evolution is triggered by a measurable quality ceiling.
```

### How to Use This Chapter in an Interview

```
OPENING (0-5 min):
  → Clarify: What's the item corpus? How many users? What surfaces?
  → State: "I'll design this as a multi-stage funnel: retrieval narrows
    millions of items to thousands, scoring ranks them, re-ranking
    applies business constraints."

FRAMEWORK (5-15 min):
  → Requirements: Personalized feed, related items, < 100ms latency
  → Scale: 100M DAU, 10M items, 35K peak QPS
  → NFRs: P99 < 200ms, eventual consistency, graceful degradation

ARCHITECTURE (15-30 min):
  → Draw the funnel: Retrieval → Features → Scoring → Re-ranking
  → Draw the feedback loop: Events → Feature Store → Training → Model
  → Explain: Multi-source retrieval, dual-path feature store, GPU scoring

DEEP DIVES (30-45 min):
  → When asked about failure: 4-level degradation stack
  → When asked about scale: Feature store hot keys, GPU auto-scaling
  → When asked about quality: A/B testing, exploration, diversity
  → When asked about cold start: Staged migration strategy
```
