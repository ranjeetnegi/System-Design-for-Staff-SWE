# Chapter 49. News feed

---

# Introduction

The news feed is one of the most deceptively complex systems in modern software. On the surface, it seems trivial: show users content from people they follow, sorted by some relevance criteria. In reality, building a news feed at scale requires solving some of the hardest problems in distributed systems: fan-out at write time vs read time, ranking billions of items in real-time, maintaining consistency across replicas, and doing all of this within strict latency budgets—all while costs don't spiral out of control.

I've designed and operated news feed systems serving hundreds of millions of users. The lessons in this chapter come from real production incidents, painful scaling challenges, and the hard-won understanding that the "obvious" solutions often fail catastrophically at scale.

**The Staff Engineer's First Law of News Feeds**: A news feed that is perfectly accurate but takes 5 seconds to load has failed. Users don't want perfection—they want the illusion of freshness with the speed of a cache hit.

---

## Quick Visual: News Feed at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NEWS FEED: THE STAFF ENGINEER VIEW                       │
│                                                                             │
│   WRONG Framing: "Fetch all posts from followed users, sort, return"        │
│   RIGHT Framing: "Serve pre-computed personalized content with              │
│                   real-time updates and graceful staleness"                 │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Before designing, understand:                                      │   │
│   │                                                                     │   │
│   │  1. Who creates content? (Few users, many posts? Many users, few?)  │   │
│   │  2. Who consumes content? (Active vs passive users)                 │   │
│   │  3. How stale can feed be? (Seconds? Minutes? Hours?)               │   │
│   │  4. How personalized? (Same for everyone? ML-ranked?)               │   │
│   │  5. What's the fanout profile? (Celebrities vs normal users?)       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   THE UNCOMFORTABLE TRUTH:                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Pure fan-out-on-write doesn't scale for celebrities.               │   │
│   │  Pure fan-out-on-read doesn't meet latency requirements.            │   │
│   │  Every real system is a hybrid—the Staff question is WHERE          │   │
│   │  to draw the line and WHY.                                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 News Feed Decisions

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Fan-out strategy** | "Use fan-out-on-write for speed, it's simpler" | "What's the follower distribution? Celebrities need fan-out-on-read. Hybrid for everyone else. Show me the P99 follower count." |
| **Ranking** | "Sort by timestamp, most recent first" | "Chronological is simple but engagement suffers. What's the product goal? Recency? Engagement? Blend with ML ranking, but with explainable fallbacks." |
| **Staleness tolerance** | "Feed should be real-time, always fresh" | "Users don't notice 30-second staleness. This relaxation enables massive caching wins. Where do we actually need real-time?" |
| **Feed storage** | "Store full feed per user" | "Store feed pointers (post IDs), not denormalized content. Content changes; duplicating it is a consistency nightmare." |
| **Celebrity handling** | "Same system for everyone" | "Celebrities break fan-out-on-write. Hybrid: fan-out for normal users, pull-based merge for celebrity content at read time." |

**Key Difference**: L6 engineers recognize that news feed is fundamentally about trade-offs between freshness, latency, and cost—and they design hybrid systems that optimize for the common case while handling edge cases gracefully.

---

# Part 1: Foundations — What a News Feed Is and Why It Exists

## What Is a News Feed?

A news feed is a personalized, time-ordered (or relevance-ordered) stream of content items aggregated from sources a user has chosen to follow. It answers the question: "What's new from people/entities I care about?"

### The Simplest Mental Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NEWS FEED: THE MAILBOX ANALOGY                           │
│                                                                             │
│   Imagine a shared apartment building with individual mailboxes.            │
│                                                                             │
│   NAIVE APPROACH (Fan-out-on-read):                                         │
│   • Every time you check your mailbox, a worker runs to every               │
│     person you follow and collects their latest letters                     │
│   • Worker sorts them and puts them in your mailbox                         │
│   • Problem: If you follow 500 people, this takes forever                   │
│                                                                             │
│   PRECOMPUTED APPROACH (Fan-out-on-write):                                  │
│   • When someone sends a letter, copies go to ALL followers' mailboxes      │
│   • Your mailbox is always ready to read                                    │
│   • Problem: Celebrity with 10M followers → 10M copies per letter           │
│                                                                             │
│   HYBRID APPROACH (Staff-level):                                            │
│   • Normal people: copies go to followers' mailboxes (precomputed)          │
│   • Celebrities: you check their "public bulletin board" when reading       │
│   • Your mailbox contains regular mail + pointer to check bulletin boards   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Why News Feeds Exist

News feeds solve a fundamental information overload problem:

1. **Aggregation**: Users follow many sources; manually checking each is impractical
2. **Personalization**: Each user sees different content based on who they follow
3. **Relevance**: The feed presents content in an order that maximizes user value
4. **Discovery**: Surface content users might miss if checking sources individually

## What Happens Without a News Feed

Without a news feed, users must:
- Visit each followed account individually
- Manually track which content they've already seen
- Miss time-sensitive content if they don't check frequently enough
- Spend cognitive effort deciding what to check next

The result: decreased engagement, user fatigue, and eventual platform abandonment.

## Why This Matters at Staff Level

News feed is a canonical Staff-level design problem because:

1. **Scale spans orders of magnitude**: From users with 10 followers to celebrities with 100M
2. **Multiple valid architectures exist**: Fan-out-on-write, fan-out-on-read, hybrid—all are defensible
3. **Trade-offs are everywhere**: Latency vs freshness, consistency vs availability, cost vs quality
4. **Failure modes are subtle**: Stale feeds, missing posts, duplicate posts, ordering anomalies
5. **Evolution is inevitable**: Systems grow from chronological to ranked, from single-region to global

A Staff engineer must navigate these trade-offs with clear reasoning, not just implement a textbook solution.

---

# Part 2: Functional Requirements

## Core Use Cases

```
USE CASE 1: View Feed
Actor: User
Action: Open app, see feed
Expected: Personalized content from followed sources, ordered by relevance/time
Latency: < 200ms P50, < 500ms P99

USE CASE 2: Publish Post
Actor: User (content creator)
Action: Create and publish new post
Expected: Post appears in followers' feeds
Latency: < 5 minutes for full propagation (P99)

USE CASE 3: Refresh Feed
Actor: User
Action: Pull-to-refresh or auto-refresh
Expected: New content since last view appears at top
Latency: < 300ms P50

USE CASE 4: Scroll/Paginate Feed
Actor: User
Action: Scroll to load more content
Expected: Older content loads seamlessly
Latency: < 200ms per page

USE CASE 5: React to Content
Actor: User
Action: Like, comment, share
Expected: Counts update, may affect ranking
Latency: < 100ms for acknowledgment
```

## Read Paths

```
PRIMARY READ PATH: Load Feed
┌──────────────────────────────────────────────────────────────────────────┐
│  1. User requests feed (with optional cursor for pagination)             │
│  2. System retrieves precomputed feed (list of post IDs)                 │
│  3. System hydrates post IDs with content (from cache or store)          │
│  4. System merges real-time updates (celebrity posts, breaking content)  │
│  5. System applies final ranking/filtering                               │
│  6. System returns hydrated, ranked feed to user                         │
└──────────────────────────────────────────────────────────────────────────┘

SECONDARY READ PATHS:
• Load specific post (deep link from notification)
• Load user's own posts (profile view)
• Load engagement metrics (like counts, comment counts)
```

## Write Paths

```
PRIMARY WRITE PATH: Publish Post
┌──────────────────────────────────────────────────────────────────────────┐
│  1. User submits post content                                            │
│  2. System validates and stores post                                     │
│  3. System triggers fan-out (async):                                     │
│     a. For normal users: Write post ID to all followers' feed storage    │
│     b. For celebrities: Write to celebrity post index only               │
│  4. System updates user's own post list                                  │
│  5. System acknowledges post creation to user                            │
└──────────────────────────────────────────────────────────────────────────┘

SECONDARY WRITE PATHS:
• Follow/unfollow user (affects future feed composition)
• Delete post (must remove from all feeds)
• Edit post (content update, feed structure unchanged)
• Engage with post (affects ranking signals)
```

## Control/Admin Paths

```
CONTROL PATHS:
• Moderation: Remove policy-violating content from all feeds
• Account actions: Suspend user, hide their content system-wide
• Feature flags: Enable/disable ranking experiments
• Backfill: Recompute feeds after algorithm change
• Emergency: Disable fan-out during incidents
```

## Edge Cases

```
EDGE CASE 1: Celebrity posts to 100M followers
• Cannot fan-out synchronously (hours to complete)
• Solution: Don't fan-out; pull at read time, merge with precomputed feed

EDGE CASE 2: User follows someone, expects immediate feed update
• New follow should affect next refresh, not retroactively populate feed
• Historical posts from new follow: Debatable product decision

EDGE CASE 3: Post deleted after fan-out
• Feed contains post ID that no longer exists
• Solution: Hydration step gracefully handles missing posts

EDGE CASE 4: User unfollows someone
• Should posts from unfollowed user disappear from feed?
• Product decision: Usually yes on next refresh, not retroactively

EDGE CASE 5: Private account goes public (or vice versa)
• Content accessibility changes; feeds may need recomputation
• Solution: Check access at hydration time, not fan-out time
```

## Out of Scope

```
INTENTIONALLY EXCLUDED:

1. DIRECT MESSAGING
   • Different access patterns (1:1, not 1:N)
   • Different privacy model
   • Different latency requirements (real-time)

2. SEARCH
   • Query-based, not subscription-based
   • Full-text indexing is separate concern
   
3. NOTIFICATIONS
   • Push-based, not pull-based
   • Different delivery guarantees
   
4. STORIES/EPHEMERAL CONTENT
   • Time-limited visibility adds complexity
   • Can be layered on later

5. ADS INJECTION
   • Business logic, not core feed mechanics
   • Ranking integration is separate concern

WHY EXCLUDED:
Each adds significant complexity without changing core feed mechanics.
Staff engineers scope aggressively to demonstrate depth, not breadth.
```

---

# Part 3: Non-Functional Requirements

## Latency Expectations

```
LATENCY TARGETS:

Feed Load (P50):     < 200ms
Feed Load (P99):     < 500ms
Feed Refresh (P50):  < 300ms
Feed Refresh (P99):  < 800ms
Pagination (P50):    < 150ms
Pagination (P99):    < 400ms

WHY THESE NUMBERS:
• 200ms is "instant" to users
• 500ms is noticeable but acceptable
• 1000ms+ causes user abandonment

LATENCY BREAKDOWN (200ms budget):
┌────────────────────────────────────────────────────────────────────────┐
│  Network RTT to edge:           20ms                                   │
│  Edge processing:               10ms                                   │
│  Feed retrieval (cache hit):    15ms                                   │
│  Content hydration (batched):   80ms                                   │
│  Ranking/filtering:             30ms                                   │
│  Response serialization:        15ms                                   │
│  Network RTT back:              20ms                                   │
│  Buffer:                        10ms                                   │
│  ─────────────────────────────────────                                 │
│  Total:                         200ms                                  │
└────────────────────────────────────────────────────────────────────────┘

IMPLICATION:
Every component must be FAST. Cache hits required for feed retrieval.
No synchronous external calls in hot path.
```

## Availability Expectations

```
AVAILABILITY TARGET: 99.9% (Three 9s)

This means:
• ~8.7 hours downtime per year
• ~43 minutes per month
• Feed is CRITICAL path—unavailable feed = unusable app

DEGRADATION HIERARCHY:
1. FULL AVAILABILITY: Ranked, personalized, fresh feed
2. DEGRADED (Level 1): Cached feed (slightly stale, still personalized)
3. DEGRADED (Level 2): Cached feed without real-time updates
4. DEGRADED (Level 3): Generic "popular" content (not personalized)
5. UNAVAILABLE: Error page

DESIGN IMPLICATION:
Feed must work with:
• Cache only (database down)
• Stale data (ranking service down)
• Generic content (personalization service down)
```

## Consistency Needs

```
CONSISTENCY MODEL: Eventual with bounded staleness

ACCEPTABLE:
• User posts; post appears in own feed: < 1 second
• User posts; post appears in close friends' feeds: < 5 seconds
• User posts; post appears in all followers' feeds: < 5 minutes
• User deletes post; post disappears: < 1 minute (best effort)

NOT ACCEPTABLE:
• Post appears, disappears, reappears (flickering)
• Post appears in different order on refresh (except for ranking changes)
• User never sees certain posts (silent failure)

IMPLICATION:
• Feed can be stale, but must be consistent with itself
• Monotonic read: Once you see a post, you always see it (until deleted)
• No strong consistency required across users (your feed ≠ my feed)

CONSISTENCY MATRIX (L6 Relevance):
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│  DATA TYPE              │  CONSISTENCY MODEL    │  STAFF RATIONALE                         │
├──────────────────────────┼──────────────────────┼──────────────────────────────────────────┤
│  Post content            │  Strong (source)     │  Authoritative; edits must propagate      │
│  Feed structure (IDs)    │  Eventual (< 5 min)  │  Precomputed; staleness acceptable        │
│  Engagement counts       │  Eventual (< 5 min)   │  Approximate; users don't need exact     │
│  Own post visibility     │  Read-your-writes    │  Author must see own post immediately      │
│  Follow/unfollow         │  Eventual (< 1 min)   │  Affects next refresh, not retroactive     │
│  Deletion propagation    │  Best-effort (< 1h)  │  Soft delete + TTL; hard delete async       │
└──────────────────────────┴──────────────────────┴──────────────────────────────────────────┘
```

## Durability

```
DURABILITY REQUIREMENTS:

POST CONTENT: DURABLE
• Posts are user-generated content; loss is unacceptable
• Replicated, backed up, never lost

FEED STATE: RECONSTRUCTIBLE
• Pre-computed feeds can be rebuilt from posts + follow graph
• Loss of feed cache is inconvenient, not catastrophic
• Trade durability for speed (in-memory caching acceptable)

RANKING SIGNALS: BEST-EFFORT
• Engagement counts, view counts can be approximate
• Loss of signals affects quality, not correctness

IMPLICATION:
Feed storage is a cache, not the source of truth.
Source of truth: Post store + Social graph
```

## Correctness vs User Experience Trade-offs

```
TRADE-OFF 1: Fresh vs Fast
• Correct: Show exactly what's happened in real-time
• Fast: Show cached version, slightly stale
• CHOICE: Fast wins. Users prefer quick stale over slow fresh.

TRADE-OFF 2: Complete vs Available
• Correct: Show all posts or show error
• Available: Show what we have, even if incomplete
• CHOICE: Available wins. Partial feed > no feed.

TRADE-OFF 3: Accurate counts vs Low latency
• Correct: Show exact like count (requires database query)
• Fast: Show cached count (might be minutes old)
• CHOICE: Fast wins. "1.2M likes" doesn't need to be "1,234,567 likes".

STAFF INSIGHT:
Users rarely notice or care about small inconsistencies.
They absolutely notice and leave over slow loads.
Optimize for perceived performance, not correctness.
```

## Security Implications

```
SECURITY CONCERNS:

1. PRIVACY
   • Private accounts: Content only visible to approved followers
   • Blocked users: Should not see blocker's content
   • Enforcement: At hydration time, not fan-out time

2. ACCESS CONTROL
   • Feed requests must be authenticated
   • Cannot enumerate other users' feeds
   
3. CONTENT INTEGRITY
   • Posts cannot be tampered with after creation
   • Signing/verification for high-value accounts

4. RATE LIMITING
   • Prevent feed scraping (bulk enumeration)
   • Limit refresh frequency per user
```

## Conflicting Requirements

```
CONFLICTS:

FRESHNESS vs LATENCY
• Fresher = more real-time processing = slower
• Resolution: Bounded staleness (30 seconds acceptable)

PERSONALIZATION vs CACHEABILITY
• More personalized = less cacheable = higher cost
• Resolution: Cache feed structure, personalize ranking

CONSISTENCY vs AVAILABILITY
• Stronger consistency = more coordination = less available
• Resolution: Eventual consistency, accept temporary inconsistency

COST vs QUALITY
• Better ranking = more ML inference = higher cost
• Resolution: Tiered ranking (simple for most, ML for engaged users)
```

---

# Part 4: Scale & Load Modeling

## Concrete Numbers (Large Social Platform)

```
USER SCALE:
• Total registered users:    500 million
• Daily active users (DAU):  200 million (40% of total)
• Monthly active users:      350 million
• Content creators (weekly): 50 million (25% of DAU post)

FOLLOW GRAPH:
• Average followers per user:         150
• Median followers per user:          50
• P99 followers (top 1%):             10,000
• Max followers (celebrities):        100 million
• Average following per user:         200

CONTENT VOLUME:
• Posts per day:                      100 million
• Posts per second (average):         1,150
• Posts per second (peak):            5,000
• Average post size:                  5 KB (including media references)

FEED READS:
• Feed loads per DAU per day:         10
• Total feed loads per day:           2 billion
• Feed loads per second (average):    23,000
• Feed loads per second (peak):       100,000
• Feed items per load:                50
```

## QPS Analysis

```
WRITE QPS (Posts):
Average: 1,150 posts/sec
Peak:    5,000 posts/sec (events, breaking news)

FAN-OUT WRITE QPS:
If pure fan-out-on-write:
• 1,150 posts/sec × 150 avg followers = 172,500 fan-out writes/sec (average)
• 5,000 posts/sec × 150 avg followers = 750,000 fan-out writes/sec (peak)

PROBLEM: Celebrity post with 100M followers
• 1 post = 100M writes
• At 100K writes/sec capacity = 1,000 seconds = 17 minutes per post
• Celebrities post multiple times per day = System never catches up

READ QPS:
Average: 23,000 feed loads/sec
Peak:    100,000 feed loads/sec

PER-REQUEST WORK:
• Retrieve 50-100 post IDs from feed storage
• Hydrate with content (batched read, 50-100 keys)
• Merge celebrity content (additional 5-10 reads)
• Apply ranking

TOTAL READ AMPLIFICATION:
23,000 feed loads/sec × ~100 hydration reads = 2.3M reads/sec from content store
```

## Storage Requirements

```
FEED STORAGE (Pre-computed feeds):
• 200M active users × 1000 post IDs stored × 8 bytes = 1.6 TB
• With replication (3x): 4.8 TB
• Memory-resident for latency: EXPENSIVE but doable

POST STORAGE:
• 100M posts/day × 5KB = 500 GB/day
• 30-day retention for hot storage: 15 TB
• Longer retention in cold storage

FOLLOW GRAPH:
• 500M users × 200 following × 8 bytes = 800 GB
• Must be memory-resident for fan-out decisions

ENGAGEMENT COUNTERS:
• 100M posts/day × 30 days × 100 bytes (counts) = 300 GB
```

## What Breaks First at Scale

```
BOTTLENECK 1: Celebrity fan-out
• First to break
• 1 celebrity post → 100M writes
• Solution: Hybrid fan-out (don't fan-out for celebrities)

BOTTLENECK 2: Feed storage size
• 1000 post IDs × 200M users = 1.6 TB
• Need memory-resident for P99 latency
• Solution: Tiered storage, only active users in memory

BOTTLENECK 3: Content hydration
• 2.3M reads/sec to content store
• Even with batching, this is massive
• Solution: Heavy caching of content

BOTTLENECK 4: Social graph lookups
• Fan-out needs follower lists
• 1,150 posts/sec × follower list lookups
• Solution: Cache follower lists, pre-compute for celebrities

BOTTLENECK 5: Ranking computation
• ML models for 100K feeds/sec?
• Solution: Pre-score posts, simple ranking at request time
```

## Dangerous Assumptions

```
DANGEROUS ASSUMPTION 1: "Average case is representative"
Reality: Power law distribution
• 1% of users create 50% of content
• 0.01% of users have 50% of followers
• System must handle P99, not P50

DANGEROUS ASSUMPTION 2: "Fan-out time is bounded"
Reality: Celebrity posts can take hours
• Product impact: User posts, followers don't see for hours
• Must design for async propagation

DANGEROUS ASSUMPTION 3: "All users are equal"
Reality: Hot/cold user split
• Most users load feed 1-2x/day
• Power users load feed 50x/day
• 10% of users = 50% of read traffic

DANGEROUS ASSUMPTION 4: "Read/write ratio is stable"
Reality: Varies by time of day and events
• Breaking news: Write spike, then read spike
• Viral content: Massive read amplification
• Peak can be 10x average
```

---

# Part 5: High-Level Architecture

## Core Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NEWS FEED: HIGH-LEVEL ARCHITECTURE                       │
│                                                                             │
│  ┌─────────────┐    ┌─────────────────────────────────────────────────┐     │
│  │   Client    │───▶│               API Gateway                       │     │
│  └─────────────┘    └───────────────────┬─────────────────────────────┘     │
│                                         │                                   │
│         ┌───────────────────────────────┼───────────────────────────────┐   │
│         │                               │                               │   │
│         ▼                               ▼                               │   │
│  ┌─────────────────┐           ┌─────────────────┐                      │   │
│  │  Feed Service   │           │  Post Service   │                      │   │
│  │  (Read Path)    │           │  (Write Path)   │                      │   │
│  └────────┬────────┘           └────────┬────────┘                      │   │
│           │                             │                               │   │
│           ▼                             ▼                               │   │
│  ┌─────────────────┐           ┌─────────────────┐                      │   │
│  │  Feed Storage   │◀──────────│  Fan-out Worker │                      │   │
│  │  (Per-user)     │           │  (Async)        │                      │   │
│  └────────┬────────┘           └────────┬────────┘                      │   │
│           │                             │                               │   │
│           │      ┌─────────────────┐    │                               │   │
│           ├─────▶│  Content Cache  │◀───┤                               │   │
│           │      └────────┬────────┘    │                               │   │
│           │               │             │                               │   │
│           │               ▼             │                               │   │
│           │      ┌─────────────────┐    │                               │   │
│           │      │   Post Store    │◀───┘                               │   │
│           │      │  (Source of     │                                    │   │
│           │      │   Truth)        │                                    │   │
│           │      └─────────────────┘                                    │   │
│           │                                                             │   │
│           │      ┌─────────────────┐                                    │   │
│           └─────▶│  Social Graph   │                                    │   │
│                  │  (Follow data)  │                                    │   │
│                  └─────────────────┘                                    │   │
│                                                                         │   │
│  ┌─────────────────┐    ┌─────────────────┐                             │   │
│  │ Ranking Service │    │ Celebrity Index │                             │   │
│  │ (Optional ML)   │    │ (Hot content)   │                             │   │
│  └─────────────────┘    └─────────────────┘                             │   │
│                                                                         │   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

```
FEED SERVICE (Read Path):
• Accepts feed requests from users
• Retrieves pre-computed feed from Feed Storage
• Hydrates post IDs with content from cache/store
• Merges celebrity content at read time
• Applies final ranking
• Handles pagination (cursor-based)

POST SERVICE (Write Path):
• Accepts new posts from users
• Validates content (size, format, policy)
• Persists to Post Store (durable)
• Triggers Fan-out Worker (async)
• Returns success to user immediately

FAN-OUT WORKER:
• Consumes post events from queue
• Determines fanout strategy (write vs hybrid)
• For normal users: Writes to followers' Feed Storage
• For celebrities: Writes to Celebrity Index only
• Handles retries and failures

FEED STORAGE:
• Per-user storage of post IDs (not content)
• Ordered by timestamp (or ranking score)
• Fast point-lookup by user ID
• Memory-resident for active users

POST STORE:
• Source of truth for all posts
• Content, metadata, timestamps
• Durable, replicated storage
• Supports batch reads (hydration)

CONTENT CACHE:
• In-memory cache of post content
• Very high hit rate (popular posts read many times)
• Write-through on post creation
• TTL-based expiration

SOCIAL GRAPH:
• Follow relationships
• Used by Fan-out Worker to get follower lists
• Used by Feed Service for access control
• Must support efficient "get followers" query

CELEBRITY INDEX:
• Recent posts from celebrities (high-follower users)
• Merged at read time instead of fan-out
• Much smaller than per-user fan-out

RANKING SERVICE:
• ML-based ranking (optional)
• Pre-computes scores for posts
• Or: Simple scoring at request time
```

## Stateless vs Stateful Decisions

```
STATELESS COMPONENTS:
• Feed Service: Request → Fetch → Compute → Response
• Post Service: Validation and routing only
• API Gateway: Load balancing, auth

WHY STATELESS:
• Horizontal scaling
• Easy failover
• No sticky sessions needed

STATEFUL COMPONENTS:
• Feed Storage: Per-user feed data
• Post Store: All content
• Social Graph: Relationships
• Content Cache: Hot content

WHY STATEFUL:
• Data must live somewhere
• Memory-resident for latency
• Sharded for scale
```

## Data Flow: Read Path

```
USER LOADS FEED:

1. Request: GET /feed?cursor=xxx
   │
2. API Gateway: Auth, rate limit, route
   │
3. Feed Service: 
   │   a. Get user ID from auth context
   │   b. Fetch feed from Feed Storage (list of post IDs)
   │   c. Fetch celebrity posts from Celebrity Index
   │   d. Merge and deduplicate
   │   e. Batch-fetch content from Content Cache (fallback to Post Store)
   │   f. Apply ranking/filtering
   │   g. Return paginated response with new cursor
   │
4. Response: { posts: [...], cursor: "yyy" }

LATENCY BREAKDOWN:
• Feed Storage lookup: 10-20ms
• Celebrity Index lookup: 5-10ms  
• Content hydration (cached): 20-50ms
• Ranking: 10-30ms
• Total: 50-100ms (P50)
```

## Data Flow: Write Path

```
USER PUBLISHES POST:

1. Request: POST /posts { content: "..." }
   │
2. API Gateway: Auth, rate limit, route
   │
3. Post Service:
   │   a. Validate content
   │   b. Generate post ID
   │   c. Write to Post Store (sync)
   │   d. Write to Content Cache (sync)
   │   e. Publish to Fan-out Queue (async)
   │   f. Return post ID to user
   │
4. Fan-out Worker (async, seconds later):
   │   a. Consume event from queue
   │   b. Lookup follower count
   │   c. If < threshold: Fan-out to all followers' Feed Storage
   │   d. If ≥ threshold: Write to Celebrity Index only
   │   e. Mark event complete
   │
5. Response to user: { post_id: "abc123" }

NOTE:
User gets response BEFORE fan-out completes.
Fan-out is eventually consistent (seconds to minutes).
```

---

# Part 6: Deep Component Design

## Feed Storage Design

```
STRUCTURE: Per-user ordered list of post IDs

KEY: user_id
VALUE: List of (post_id, timestamp, score) tuples
ORDERING: By timestamp descending (or score)
SIZE LIMIT: 1000 entries per user (older entries evicted)

DATA STRUCTURE OPTIONS:

OPTION 1: Sorted Set (Redis ZSET)
• Members: post_id
• Scores: timestamp (or ranking score)
• Operations: ZADD, ZRANGE, ZREMRANGEBYRANK
• Pros: Built-in ordering, efficient range queries
• Cons: Redis cluster complexity, memory cost

OPTION 2: Append-only log per user
• File/blob per user, append new post IDs
• Read: Load file, parse, sort
• Pros: Simple, cheap storage
• Cons: Read cost scales with history size

OPTION 3: Pre-sorted list in memory
• In-memory sorted list per active user
• Persist to disk periodically
• Pros: Fastest reads, controllable
• Cons: Custom implementation, memory management

STAFF CHOICE: Sorted Set (Redis-like) for active users
• Memory-resident for active users
• Disk-backed for inactive users
• Hybrid: Hot/cold tiering
```

```
// Pseudocode: Feed Storage operations

CLASS FeedStorage:
    hot_tier = {}      // In-memory for active users
    cold_tier = DiskStore()
    max_entries = 1000
    hot_ttl = 7 days
    
    FUNCTION append(user_id, post_id, timestamp):
        // Add to user's feed
        IF user_id IN hot_tier:
            feed = hot_tier[user_id]
        ELSE:
            feed = load_from_cold(user_id)
            hot_tier[user_id] = feed
        
        feed.add(post_id, timestamp)
        
        // Trim to max size
        IF feed.size() > max_entries:
            feed.remove_oldest(feed.size() - max_entries)
        
        // Mark for persistence
        schedule_persist(user_id)
    
    FUNCTION get_feed(user_id, cursor, limit):
        IF user_id IN hot_tier:
            feed = hot_tier[user_id]
        ELSE:
            feed = load_from_cold(user_id)
            // Optionally promote to hot tier based on access pattern
        
        // Return page starting from cursor
        RETURN feed.range(cursor, limit)
```

## Content Cache Design

```
PURPOSE: Cache post content to avoid Post Store reads on every hydration

STRUCTURE: Key-value store
KEY: post_id
VALUE: Serialized post content (text, media URLs, metadata)
TTL: 24 hours (posts rarely edited)
SIZE: ~5KB per post

CACHING STRATEGY:

WRITE-THROUGH:
• On post creation: Write to Post Store AND Content Cache
• Guarantees cache is populated for new posts
• No cold-start problem for viral posts

READ-THROUGH (fallback):
• On cache miss: Read from Post Store, populate cache
• Handles cache eviction/restart

CACHE WARMING:
• Pre-fetch content for trending posts
• Pre-fetch content for celebrity posts (always in cache)

INVALIDATION:
• On post edit: Invalidate cache entry
• On post delete: Invalidate cache entry
• TTL handles eventual eviction
```

```
// Pseudocode: Content hydration with batching

CLASS ContentHydrator:
    cache = ContentCache()
    store = PostStore()
    batch_size = 100
    
    FUNCTION hydrate(post_ids):
        // Try cache first
        cached = cache.multi_get(post_ids)
        found = {pid: content for pid, content in cached if content != null}
        missing = [pid for pid in post_ids if pid not in found]
        
        IF missing:
            // Batch fetch from store
            from_store = store.multi_get(missing)
            
            // Populate cache for next time
            cache.multi_set(from_store)
            
            found.update(from_store)
        
        // Preserve order
        result = [found.get(pid) for pid in post_ids if pid in found]
        RETURN result
```

## Fan-out Worker Design

```
PURPOSE: Distribute new posts to followers' feeds

STRATEGY: Hybrid fan-out
• Normal users (< 10K followers): Fan-out-on-write
• Celebrities (≥ 10K followers): Fan-out-on-read (via Celebrity Index)

THRESHOLD SELECTION:
• 10K followers × 1,150 posts/sec = 11.5M fan-out writes/sec (worst case)
• At 10K threshold, ~1% of users are celebrities
• Those 1% have ~50% of followers
• Hybrid saves ~50% of fan-out writes
```

```
// Pseudocode: Hybrid fan-out

CLASS FanOutWorker:
    celebrity_threshold = 10000
    
    FUNCTION process_post(post_event):
        author_id = post_event.author_id
        post_id = post_event.post_id
        timestamp = post_event.timestamp
        
        follower_count = social_graph.get_follower_count(author_id)
        
        IF follower_count >= celebrity_threshold:
            // Celebrity path: Don't fan out, add to celebrity index
            celebrity_index.add(author_id, post_id, timestamp)
            log("Celebrity post, skipping fan-out", author_id, post_id)
        ELSE:
            // Normal path: Fan out to all followers
            followers = social_graph.get_followers(author_id)
            
            FOR batch IN chunk(followers, 1000):
                // Batch write to feed storage
                FOR follower_id IN batch:
                    feed_storage.append(follower_id, post_id, timestamp)
            
            log("Fan-out complete", author_id, post_id, follower_count)
```

## Celebrity Index Design

```
PURPOSE: Store recent posts from celebrities for read-time merge

STRUCTURE:
KEY: celebrity_user_id
VALUE: List of (post_id, timestamp) tuples
SIZE LIMIT: 100 posts per celebrity (recent only)

WHY SEPARATE:
• Celebrity posts are read by millions
• Storing in Celebrity Index: 1 write
• Fan-out to followers: Millions of writes
• Read-time merge adds ~10ms, saves hours of write time
```

```
// Pseudocode: Read-time celebrity merge

CLASS FeedService:
    
    FUNCTION get_feed(user_id, cursor, limit):
        // Step 1: Get precomputed feed
        base_feed = feed_storage.get_feed(user_id, cursor, limit * 2)
        
        // Step 2: Get followed celebrities
        following = social_graph.get_following(user_id)
        celebrity_following = [u for u in following 
                               if is_celebrity(u)]
        
        // Step 3: Get celebrity posts
        celebrity_posts = []
        FOR celeb_id IN celebrity_following:
            posts = celebrity_index.get_recent(celeb_id, limit=10)
            celebrity_posts.extend(posts)
        
        // Step 4: Merge and sort
        merged = merge_by_timestamp(base_feed, celebrity_posts)
        deduplicated = dedupe_by_post_id(merged)
        
        // Step 5: Trim to limit
        RETURN deduplicated[:limit]
```

## Ranking Service Design

```
PURPOSE: Order feed by relevance, not just timestamp

RANKING FACTORS:
• Recency: Newer posts ranked higher
• Engagement: Posts with more likes/comments ranked higher
• Affinity: Posts from close connections ranked higher
• Content type: Video, photos, text weighted differently
• Author activity: Posts from active authors ranked higher

RANKING APPROACHES:

APPROACH 1: Pre-computed scores (simple)
• At fan-out time, compute score for each post
• Store (post_id, score) in feed storage
• Read-time: Already sorted by score
• Pros: Fast reads
• Cons: Stale scores (engagement changes)

APPROACH 2: Request-time ranking (complex)
• Store only post_ids in feed storage
• At read time, fetch features and compute score
• Pros: Fresh scores
• Cons: Latency, CPU cost

APPROACH 3: Hybrid (Staff choice)
• Pre-compute coarse score at fan-out
• Apply lightweight recency boost at read time
• Full ML ranking for engaged users only
```

```
// Pseudocode: Lightweight request-time ranking

CLASS RankingService:
    
    FUNCTION rank_feed(posts, user_context):
        scored_posts = []
        
        FOR post IN posts:
            base_score = post.precomputed_score
            
            // Recency boost
            age_hours = (now() - post.timestamp).hours
            recency_boost = max(0, 1 - (age_hours / 24))
            
            // Engagement boost (cached)
            engagement = get_cached_engagement(post.id)
            engagement_boost = log(engagement + 1) / 10
            
            // Affinity boost (if available)
            affinity = user_context.get_affinity(post.author_id, default=0.5)
            
            final_score = base_score + recency_boost + engagement_boost + affinity
            scored_posts.append((post, final_score))
        
        // Sort by score descending
        scored_posts.sort(key=lambda x: -x[1])
        
        RETURN [post for post, score in scored_posts]
```

## Why Simpler Alternatives Fail

```
ALTERNATIVE 1: Pure fan-out-on-write for everyone
Problem: Celebrity with 100M followers
• 1 post = 100M writes
• At 100K writes/sec = 17 minutes per post
• System never catches up during high-activity periods
Why it seems attractive: Simple, fast reads
Why Staff rejects: Doesn't scale for power-law distribution

ALTERNATIVE 2: Pure fan-out-on-read
Problem: Reading feed requires fetching from all followed users
• User follows 500 people
• Fetching 500 users' posts + sorting = 500+ reads
• P99 latency: Seconds, not milliseconds
Why it seems attractive: No write amplification
Why Staff rejects: Unacceptable read latency

ALTERNATIVE 3: Store full post content in feed storage
Problem: Content duplication nightmare
• Post with 1M readers = 1M copies of content
• Post edit requires 1M updates
• Storage cost multiplied by read count
Why it seems attractive: Single read per feed item
Why Staff rejects: Consistency, storage, update cost

ALTERNATIVE 4: Single ranking algorithm for everyone
Problem: Engaged users need personalization, casual users don't
• Full ML ranking: 50ms added latency
• Casual users: Don't engage enough to justify cost
Why it seems attractive: Simpler to implement
Why Staff rejects: Cost/benefit mismatch
```

---

# Part 7: Data Model & Storage Decisions

## What Data Is Stored

```
DATA ENTITY 1: Post
┌──────────────────────────────────────────────────────────────────────────┐
│  post_id:        UUID (globally unique)                                  │
│  author_id:      User ID (foreign key)                                   │
│  content:        Text content (max 10KB)                                 │
│  media_refs:     Array of media URLs                                     │
│  created_at:     Timestamp                                               │
│  updated_at:     Timestamp (for edits)                                   │
│  visibility:     Enum (public, followers_only, private)                  │
│  is_deleted:     Boolean (soft delete)                                   │
│  engagement:     {likes: int, comments: int, shares: int}                │
└──────────────────────────────────────────────────────────────────────────┘

DATA ENTITY 2: Feed Entry (per user)
┌──────────────────────────────────────────────────────────────────────────┐
│  user_id:        User whose feed this belongs to                         │
│  post_id:        Reference to Post                                       │
│  source_user_id: Who created the post (for filtering)                    │
│  timestamp:      When post was added to feed                             │
│  score:          Pre-computed ranking score                              │
└──────────────────────────────────────────────────────────────────────────┘

DATA ENTITY 3: Follow Relationship
┌──────────────────────────────────────────────────────────────────────────┐
│  follower_id:    User who follows                                        │
│  followee_id:    User being followed                                     │
│  created_at:     When follow happened                                    │
│  is_close_friend: Boolean (for affinity ranking)                         │
└──────────────────────────────────────────────────────────────────────────┘

DATA ENTITY 4: Celebrity Index Entry
┌──────────────────────────────────────────────────────────────────────────┐
│  celebrity_id:   User ID of celebrity                                    │
│  post_id:        Recent post                                             │
│  timestamp:      Post creation time                                      │
└──────────────────────────────────────────────────────────────────────────┘
```

## How Data Is Keyed

```
POST STORE:
Primary key: post_id
Secondary index: author_id + created_at (for profile views)

FEED STORAGE:
Primary key: user_id
Value: Sorted set of (post_id, timestamp)
Access pattern: Point lookup by user_id, range scan by timestamp

SOCIAL GRAPH:
Key 1: followee_id → Set of follower_ids (for fan-out)
Key 2: follower_id → Set of followee_ids (for feed merge)

CELEBRITY INDEX:
Primary key: celebrity_id
Value: List of recent (post_id, timestamp)
```

## How Data Is Partitioned

```
POST STORE:
Partition key: post_id (hash partitioning)
• Even distribution
• No hot spots (random distribution)
• Efficient batch reads

FEED STORAGE:
Partition key: user_id (hash partitioning)
• Each user's feed on one shard
• No cross-shard queries for feed read
• Hot users might create hot shards (mitigate with consistent hashing)

SOCIAL GRAPH:
Partition key: user_id (hash partitioning)
• Followers and following on same shard
• Fan-out reads are single-shard

WHY NOT TIME-BASED PARTITIONING:
• Would require reading from multiple partitions for feed
• Recent data more accessed (hot partition)
• User-based partitioning aligns with access patterns
```

## Retention Policies

```
POSTS:
• Active: Indefinite (user-generated content is permanent)
• Deleted: Soft delete, hard delete after 30 days
• Archived: Move to cold storage after 1 year

FEED STORAGE:
• Per-user: Keep last 1000 entries only
• Older entries evicted automatically
• If user wants older content: Re-compute or fetch from source

CELEBRITY INDEX:
• Keep last 100 posts per celebrity
• Older posts fetched directly if needed (rare)

ENGAGEMENT COUNTERS:
• Real-time: Last 24 hours
• Aggregated: Rolled up daily, kept for 90 days
• Archived: Monthly aggregates kept indefinitely
```

## Schema Evolution

```
EVOLUTION 1: Adding new post field (e.g., "thread_id")
Strategy: Additive schema
• Add field to write path
• Default null for existing posts
• Readers handle missing field gracefully
• No migration required

EVOLUTION 2: Changing feed storage structure
Strategy: Dual-write during migration
• Write to both old and new format
• Gradually migrate reads to new format
• Backfill historical data
• Remove old format after verification

EVOLUTION 3: Adding engagement types (e.g., "reaction_types")
Strategy: Flexible schema
• Store engagement as JSON object
• Add new keys as needed
• Readers handle unknown keys gracefully
```

## Why Other Data Models Were Rejected

```
REJECTED: Graph database for social graph
Reason: Overkill for simple follow relationships
• Graph DBs excel at multi-hop queries (friends of friends)
• Feed only needs 1-hop: "who do I follow?"
• Simple key-value store sufficient and faster
• Graph DB adds operational complexity

REJECTED: Time-series database for feed storage
Reason: Wrong access pattern
• Time-series optimized for "all data for time range"
• Feed needs "all data for one user, any time"
• User-keyed storage matches access pattern

REJECTED: Single monolithic database
Reason: Different components have different needs
• Post store: Durable, consistent
• Feed storage: Fast, eventually consistent, can be rebuilt
• Content cache: In-memory, ephemeral
• Mixing requirements compromises all
```

---

# Part 8: Consistency, Concurrency & Ordering

## Strong vs Eventual Consistency

```
CONSISTENCY REQUIREMENTS BY DATA TYPE:

POST CONTENT: Strong consistency for author
• Author creates post, must see it immediately in own feed
• Other users: Eventual consistency (seconds) is acceptable

FEED STATE: Eventual consistency
• New post appears in followers' feeds within seconds to minutes
• No strong consistency required across users
• Users tolerate their feed being slightly different from "reality"

ENGAGEMENT COUNTS: Eventual consistency
• Counts can lag by seconds/minutes
• "1.2M likes" vs "1,234,567 likes" doesn't matter

FOLLOW GRAPH: Eventual consistency
• New follow affects future posts, not immediately
• Slight delay (seconds) is acceptable

DELETIONS: Eventually consistent, best-effort
• Deleted post should disappear from feeds eventually
• May appear briefly after deletion (acceptable)
```

## Race Conditions

```
RACE CONDITION 1: Follow and post simultaneously
Scenario:
• T0: User A follows User B
• T0: User B posts (fan-out happening)
• Question: Does User A see the post?

Resolution:
• If fan-out started before follow: A doesn't see post
• If follow before fan-out: A sees post
• Acceptable inconsistency—next post will be correct

RACE CONDITION 2: Post and delete quickly
Scenario:
• T0: User posts
• T1: Fan-out starts
• T2: User deletes post
• T3: Fan-out completes

Resolution:
• Post ID written to feeds points to deleted content
• Hydration returns null for deleted post
• Frontend filters null posts gracefully

RACE CONDITION 3: Concurrent engagement updates
Scenario:
• 1000 users like post simultaneously
• All incrementing same counter

Resolution:
• Use atomic increment (INCR in Redis)
• Or: Approximate counting with eventual merge
• Exact count not required
```

## Idempotency

```
IDEMPOTENT OPERATIONS:

POST CREATION:
• Client generates post_id (UUID)
• Same post_id → same post
• Retry-safe: Multiple submits create one post

FAN-OUT:
• Writing same (user_id, post_id) twice is idempotent
• Feed storage deduplicates by post_id
• Retry-safe: Multiple fan-outs don't duplicate

FEED READ:
• Inherently idempotent (no state change)
• Pagination cursor enables exactly-once semantics

NON-IDEMPOTENT (with mitigation):
ENGAGEMENT ACTIONS:
• Like button: Must be idempotent per user
• Track (user_id, post_id, action) to prevent double-counting
• Backend enforces at-most-once per user
```

## Ordering Guarantees

```
ORDERING REQUIREMENTS:

WITHIN A USER'S FEED:
• Posts ordered by timestamp (or score)
• Order is stable across refreshes (unless ranking changes)
• New posts appear at top

ACROSS USERS:
• No ordering guarantee
• User A might see post before User B
• Acceptable: Different users, different feeds

POST CREATION ORDER:
• Author's posts maintain creation order in their profile
• In others' feeds: Order may differ due to fan-out timing

ORDERING ANOMALIES (Acceptable):
• Post from 5 minutes ago appears after post from 10 minutes ago
  (Due to fan-out delay differences)
• Solution: Client-side sort by timestamp, not arrival order
```

## Clock Assumptions

```
CLOCK REQUIREMENTS:

POST TIMESTAMPS:
• Server-assigned at creation
• NTP-synchronized servers (±100ms)
• Sufficient for feed ordering

FAN-OUT TIMING:
• Wall clock acceptable
• Slight skew between workers doesn't affect correctness
• Ordering based on post timestamp, not fan-out time

CACHE TTL:
• Wall clock with ±1 second tolerance
• If cache expires slightly early/late: No user impact

PAGINATION CURSORS:
• Encode timestamp, not position
• Cursor = "posts before timestamp X"
• Clock skew handled by timestamp comparison
```

## What Bugs Appear If Mishandled

```
BUG 1: Non-atomic post creation
Symptom: Post in store but not in author's feed
Cause: Crash between post store write and feed append
Detection: Author doesn't see own post
Fix: Transactional or compensating action

BUG 2: Duplicate posts in feed
Symptom: Same post appears twice
Cause: Fan-out retry without deduplication
Detection: User complaint, visual bug
Fix: Dedupe by post_id at storage layer

BUG 3: Stale engagement counts displayed
Symptom: Like count shows 100, user already liked (should be 101)
Cause: Cached count not invalidated on action
Detection: User confusion
Fix: Optimistic UI update + eventual consistency

BUG 4: Feed pagination skips posts
Symptom: User scrolls, misses posts
Cause: New posts inserted, cursor offset shifts
Detection: User complaint about missing content
Fix: Cursor based on timestamp, not offset

BUG 5: Deleted post content still visible
Symptom: Post shows "This post was deleted" in some feeds, shows content in others
Cause: Inconsistent cache invalidation
Detection: User complaint
Fix: Check deletion status at hydration time
```

---

# Part 9: Failure Modes & Degradation

## Partial Failures

### Failure 1: Feed Storage Node Down

```
SCENARIO: One of 16 feed storage nodes fails

IMPACT:
• 1/16 of users (6.25%) cannot load their feeds
• Other users unaffected

DETECTION:
• Health checks fail
• Error rate spikes for that shard
• Latency increases (timeouts)

MITIGATION:
• Feed storage replicated (2-3 replicas per shard)
• Failover to replica (seconds)
• If all replicas down: Serve cached/stale feed or degrade gracefully

USER EXPERIENCE:
• Most users: Normal
• Affected users: See stale feed or error
```

### Failure 2: Post Store Unavailable

```
SCENARIO: Post store database cluster is down

IMPACT:
• Feed reads fail at hydration step
• No post content can be fetched
• New posts cannot be created

DETECTION:
• Connection failures to database
• Write failures
• Hydration returning errors

MITIGATION:
• Content cache contains most recent posts
• Serve feed with cached content only
• New posts queued for later persistence

USER EXPERIENCE:
• Feed loads with cached content
• Very new posts (last 5 minutes) might be missing
• New posts appear to succeed (queued)
```

### Failure 3: Fan-out Worker Backlog

```
SCENARIO: Fan-out workers overwhelmed (queue depth growing)

IMPACT:
• New posts visible to author only
• Followers don't see posts (increasing staleness)
• Queue grows, risk of message loss

DETECTION:
• Queue depth metrics
• Fan-out latency metrics (time from post to feed appearance)
• Worker lag alerts

MITIGATION:
• Scale up workers (auto-scaling)
• Prioritize: Celebrities first (Celebrity Index is fast)
• Degrade: Skip fan-out for inactive users

USER EXPERIENCE:
• Posts take longer to appear in feeds
• Feeds feel "stale"
• Active users affected more than passive users
```

### Failure 4: Content Cache Miss Storm

```
SCENARIO: Content cache restart, all entries evicted

IMPACT:
• Every feed request hits Post Store
• Post Store overwhelmed
• Latency spikes for everyone

DETECTION:
• Cache hit rate drops to 0%
• Post Store QPS spikes
• Latency increases

MITIGATION:
• Cache warming: Pre-populate with trending/popular posts
• Gradual traffic ramp after restart
• Circuit breaker: If Post Store latency > threshold, serve partial feed

USER EXPERIENCE:
• Slow feed loads (seconds instead of milliseconds)
• Potential errors if Post Store overwhelmed
```

## Slow Dependencies

```
SLOW DEPENDENCY: Ranking Service

SYMPTOM: Ranking service P99 latency increases from 30ms to 500ms

IMPACT: Feed load P99 increases by 500ms

MITIGATION:
• Timeout ranking at 50ms
• If timeout: Return chronologically sorted feed
• Users get fast but less relevant feed
• Better than slow but relevant feed

SLOW DEPENDENCY: Social Graph

SYMPTOM: Social graph lookups slow (for celebrity list)

IMPACT: Celebrity merge step slow

MITIGATION:
• Cache celebrity following list per user (high TTL)
• If cache miss: Skip celebrity merge
• Slightly less complete feed, but fast
```

## Retry Storms

```
SCENARIO: Feed service returns errors, clients retry aggressively

TIMELINE:
T+0:    Feed service: 10% error rate (partial outage)
T+10s:  Clients retry failed requests
T+20s:  Error rate unchanged, but QPS increases 30%
T+30s:  More retries pile up
T+60s:  QPS 2x normal, system overloaded, error rate increases
T+90s:  Full outage from retry amplification

MITIGATION:
• Exponential backoff with jitter (client-side)
• 429 responses with Retry-After header (server-side)
• Load shedding: Reject excess requests early
• Circuit breaker: Stop retrying after N failures
```

## Data Corruption

```
SCENARIO: Bug in fan-out worker writes invalid post IDs to feeds

IMPACT:
• Feeds contain garbage post IDs
• Hydration fails or returns nulls
• Users see empty spots or errors in feed

DETECTION:
• Hydration error rate increases
• Users report missing content
• Data validation checks fail

MITIGATION:
• Hydration gracefully handles missing posts (filter out nulls)
• Background job to repair feeds (re-compute from source)
• Rollback fan-out worker to previous version

RECOVERY:
• Identify affected feeds
• Re-run fan-out for affected time window
• Or: Rebuild feeds from scratch (expensive but correct)
```

## Control-Plane Failures

```
SCENARIO: Configuration service (feature flags, ranking config) unavailable

IMPACT:
• Can't change ranking algorithm
• Can't roll out new features
• Can't disable problematic code paths

MITIGATION:
• Cache configuration locally with long TTL
• Default to safe configuration if unavailable
• Continue operating with stale config
• Alert and page on-call for manual intervention

USER EXPERIENCE:
• No impact (system runs on cached config)
• New features delayed
```

## Graceful Degradation Ladder

```
DEGRADATION LEVELS:

LEVEL 0: FULL SERVICE
• Ranked, personalized, real-time feed
• All features enabled

LEVEL 1: REDUCED RANKING
• Chronological instead of ML-ranked
• Still personalized, still real-time
• Trigger: Ranking service slow/down

LEVEL 2: CACHED FEEDS
• Serve last successful feed from cache
• May be minutes old
• Trigger: Feed storage slow/down

LEVEL 3: NO CELEBRITY MERGE
• Skip celebrity posts at read time
• Feed missing some content
• Trigger: Celebrity index slow/down

LEVEL 4: GENERIC CONTENT
• Show popular/trending posts (same for everyone)
• Not personalized
• Trigger: Personalization completely broken

LEVEL 5: ERROR PAGE
• Service unavailable
• Trigger: All systems down, no safe fallback

BLAST RADIUS SUMMARY (L6 Relevance):
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│  COMPONENT FAILURE       │  BLAST RADIUS           │  MITIGATION                            │
├──────────────────────────┼─────────────────────────┼─────────────────────────────────────────┤
│  Feed Storage shard      │  1/N users (e.g. 6.25%) │  Replica promotion; cached fallback   │
│  Content Cache node      │  Affected keys only     │  Request coalescing; Post Store fallback│
│  Fan-out queue full      │  New posts delayed      │  Priority queue; defer inactive        │
│  Ranking service down    │  All users (degraded)   │  Chronological fallback                │
│  Post Store down         │  All users              │  Cached content only; read replica    │
│  Celebrity index down    │  Celebrity posts missing │  Graceful omission; partial feed      │
└──────────────────────────┴─────────────────────────┴─────────────────────────────────────────┘

STAFF INSIGHT: "Blast radius is a design choice. Shard Feed Storage so one
failure affects <7% of users. Isolate celebrity path so celebrity bugs
don't affect normal-user latency."
```

## Failure Timeline Walkthrough

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    INCIDENT: POST STORE DEGRADATION                         │
│                                                                             │
│   T+0:00  Post Store P99 latency increases from 10ms to 500ms               │
│           └─ Cause: Slow query from batch job, lock contention              │
│                                                                             │
│   T+0:30  Content hydration latency increases                               │
│           └─ Feed load P99: 200ms → 700ms                                   │
│           └─ Users notice slow feeds                                        │
│                                                                             │
│   T+1:00  Cache hit rate drops (new posts not in cache yet)                 │
│           └─ More requests hit slow Post Store                              │
│           └─ Feed load P99: 700ms → 1500ms                                  │
│                                                                             │
│   T+1:30  ALERT: Feed latency SLO breach                                    │
│           └─ On-call paged                                                  │
│                                                                             │
│   T+2:00  On-call investigates                                              │
│           └─ Identifies batch job as root cause                             │
│           └─ Kills batch job                                                │
│                                                                             │
│   T+2:30  Post Store latency recovering                                     │
│           └─ Cache refilling                                                │
│           └─ Feed latency dropping                                          │
│                                                                             │
│   T+5:00  Full recovery                                                     │
│           └─ Feed load P99 back to 200ms                                    │
│                                                                             │
│   BLAST RADIUS: All users (feed load degraded)                              │
│   USER IMPACT: Slow feeds for ~5 minutes                                    │
│   DATA LOSS: None                                                           │
│                                                                             │
│   POST-INCIDENT:                                                            │
│   • Add batch job isolation (separate read replica)                         │
│   • Add Post Store latency circuit breaker                                  │
│   • Add degradation to cached-only mode when store slow                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 10: Performance Optimization & Hot Paths

## Critical Paths

```
CRITICAL PATH 1: Feed Load
Frequency: 23,000/sec (average), 100,000/sec (peak)
Budget: 200ms P50, 500ms P99
Components: Feed Storage → Content Cache → Ranking

Optimizations:
• Feed Storage: Memory-resident, single-shard lookup
• Content Cache: 99%+ hit rate required
• Ranking: Pre-computed scores, lightweight adjustments only

CRITICAL PATH 2: Feed Pagination
Frequency: 2x feed loads (users scroll)
Budget: 150ms P50, 400ms P99
Components: Same as feed load, cursor-based continuation

Optimizations:
• Cursor encodes position efficiently
• Pre-fetch next page in background

CRITICAL PATH 3: Post Creation Acknowledgment
Frequency: 1,150/sec (average)
Budget: 200ms (user feels immediate)
Components: Post Store write only

Optimizations:
• Fan-out is async (not on critical path)
• User gets response before fan-out starts
```

## Caching Strategies

```
CACHE 1: Content Cache
What: Post content (text, media refs, metadata)
Size: 15 TB hot content (30 days × 500GB/day)
Hit rate target: 99%
Strategy: Write-through on create, LRU eviction

Why it works:
• Power law: 20% of posts get 80% of reads
• Viral posts cached and served millions of times
• TTL handles eventual eviction

CACHE 2: Feed Cache
What: Last fetched feed per user
Size: Smaller (just cursors and recent results)
Hit rate: Varies by user activity
Strategy: Cache on first load, invalidate on new content

Why it works:
• Users refresh same feed multiple times
• Cache until new content available
• Push invalidation on new post

CACHE 3: Social Graph Cache
What: Follower/following lists
Size: 800 GB (in-memory)
Hit rate: 95%+
Strategy: Cache on access, TTL-based refresh

Why it works:
• Follow graph changes slowly
• Same lists accessed for fan-out and read-merge
• Stale list (missing new follow) acceptable briefly

CACHE 4: Engagement Counter Cache
What: Like/comment/share counts
Size: 300 GB (30 days)
Hit rate: 99%
Strategy: Write-behind (batch updates to store)

Why it works:
• Approximate counts acceptable
• High write volume (many likes)
• Batch writes to database, serve from cache
```

## Precomputation vs Runtime Work

```
PRECOMPUTED (at write time):
• Fan-out: Write post ID to followers' feeds
• Base ranking score: Computed once, stored with feed entry
• Celebrity detection: Follower count threshold

WHY PRECOMPUTE:
• Read volume >> Write volume (10:1 or higher)
• Amortize write cost across many reads

RUNTIME (at read time):
• Celebrity merge: Pull recent celebrity posts
• Final ranking: Apply recency boost, personalization
• Content hydration: Fetch actual post content

WHY RUNTIME:
• Celebrity content too expensive to fan-out
• Ranking freshness matters (engagement changes)
• Content changes (edits, deletes)

HYBRID EXAMPLE:
Pre-compute: Base score = author_reputation + initial_engagement
Runtime: Final score = base_score + recency_boost + user_affinity
```

## Backpressure

```
BACKPRESSURE POINT 1: Fan-out Queue
Trigger: Queue depth > 1M messages
Response: 
• Alert on-call
• Scale up workers
• If queue full: Drop low-priority fan-outs (inactive users)

BACKPRESSURE POINT 2: Content Cache
Trigger: Cache memory > 90%
Response:
• Aggressive eviction of old entries
• Reduce TTL temporarily
• If still full: Evict based on access frequency

BACKPRESSURE POINT 3: Feed Service
Trigger: Request queue depth growing
Response:
• Reject new requests with 503
• Serve degraded content (cached, unranked)
• Shed load early rather than timeout late
```

## Load Shedding

```
LOAD SHEDDING STRATEGY:

PRIORITY 1 (Never shed): Logged-in users loading feed
PRIORITY 2: Background prefetches
PRIORITY 3: Low-engagement users
PRIORITY 4: Anonymous previews

IMPLEMENTATION:
```

```
// Pseudocode: Load shedding

CLASS FeedLoadShedder:
    current_load = 0
    max_capacity = 100000  // requests per second
    
    FUNCTION should_serve(request):
        current_load = get_current_qps()
        
        IF current_load < max_capacity * 0.8:
            // Normal: Serve all
            RETURN true
        
        IF current_load < max_capacity * 0.9:
            // Elevated: Shed background prefetches
            IF request.type == "prefetch":
                RETURN false
            RETURN true
        
        IF current_load < max_capacity:
            // High: Shed low-engagement users
            IF request.type == "prefetch":
                RETURN false
            IF request.user.engagement_score < 0.2:
                RETURN false
            RETURN true
        
        // Critical: Shed everything except VIP
        IF request.user.is_vip:
            RETURN true
        RETURN false
```

## Why Some Optimizations Are NOT Done

```
OPTIMIZATION NOT DONE: Pre-render complete feed HTML

Why it seems attractive:
• Skip hydration and ranking at request time
• Serve pre-rendered content directly

Why we don't:
• Feed is personalized per user
• Content changes (edits, deletes, engagement counts)
• Pre-rendering 200M personalized feeds is impossible
• Dynamic assembly is necessary

OPTIMIZATION NOT DONE: Global feed ranking cache

Why it seems attractive:
• Same popular posts ranked for many users
• Cache the ranking once

Why we don't:
• Personalized ranking = different for each user
• User affinity changes ranking order
• Cache hit rate would be near 0%

OPTIMIZATION NOT DONE: Push-based feed updates

Why it seems attractive:
• Push new posts to clients in real-time
• No polling, instant updates

Why we don't:
• 200M concurrent connections is massive
• Most users are passive (not actively viewing)
• Polling every 30-60 seconds is sufficient
• Push adds complexity without proportional benefit
• Exception: Real-time apps (messaging) justify push
```

---

# Part 11: Cost & Efficiency

## Major Cost Drivers

```
COST ANALYSIS (at scale):

┌────────────────────────────────────────────────────────────────────────────┐
│  COMPONENT              │  COST DRIVER           │  MONTHLY ESTIMATE       │
├────────────────────────────────────────────────────────────────────────────┤
│  Feed Storage           │  Memory (in-RAM)       │  $150K (10 TB RAM)      │
│  Content Cache          │  Memory (in-RAM)       │  $200K (15 TB RAM)      │
│  Post Store             │  Storage + IOPS        │  $50K (replicated SSD)  │
│  Fan-out Workers        │  Compute               │  $80K (processing)      │
│  Feed Service           │  Compute               │  $120K (request handling│
│  Network (internal)     │  Data transfer         │  $30K (cross-AZ)        │
│  Network (egress)       │  Data transfer         │  $100K (to users)       │
├────────────────────────────────────────────────────────────────────────────┤
│  TOTAL                  │                        │  ~$730K/month           │
└────────────────────────────────────────────────────────────────────────────┘

TOP 2 COST DRIVERS:
1. Memory (Feed Storage + Content Cache): $350K/month (48%)
2. Compute (Workers + Service): $200K/month (27%)
```

## How Cost Scales with Traffic

```
SCALING BEHAVIOR:

FEED STORAGE:
• Scales with DAU (active users need memory-resident feeds)
• Cost = $15/user/year for active users
• 200M active users × $15 = $3B/year... NO, that's wrong
• Actually: $150K/month = $1.8M/year / 200M users = $0.009/user/year
• Memory is shared, not per-user dedicated

CONTENT CACHE:
• Scales with content volume (posts per day)
• 500 GB/day × 30 days = 15 TB hot content
• Cost scales linearly with content retention window

FAN-OUT WORKERS:
• Scales with post volume × average follower count
• 100M posts/day × 150 followers = 15B fan-out writes/day
• Cost scales linearly with write volume

FEED SERVICE:
• Scales with read QPS
• 2B feed loads/day = 23K QPS
• Cost scales linearly with read volume
```

## Cost vs Reliability Trade-offs

```
TRADE-OFF 1: Memory replication factor
Option A: 2x replication ($350K/month)
• One replica failure → Reads continue
• Two replica failures → Data loss, rebuild

Option B: 3x replication ($525K/month)
• Two replica failures → Still serving
• Higher durability

CHOICE: 2x for feed storage (can rebuild)
         3x for post store (cannot rebuild)
         Cost savings: $175K/month on feed storage

TRADE-OFF 2: Cache size vs hit rate
Option A: 15 TB cache, 99% hit rate ($200K/month)
Option B: 10 TB cache, 95% hit rate ($133K/month)
• 5% more misses = 5% more Post Store load
• Post Store can handle it

CHOICE: 10 TB cache is sufficient
         Savings: $67K/month
         Trade-off: Slightly higher Post Store load

TRADE-OFF 3: Hot/cold tiering for feed storage
Option A: All users in memory ($150K/month)
Option B: Active users in memory, inactive on SSD ($80K/month)
• Inactive users: 50% of users, 5% of reads
• SSD latency: 5ms vs 1ms (acceptable for inactive users)

CHOICE: Hot/cold tiering
         Savings: $70K/month
         Trade-off: Inactive users get slower first feed load
```

## What Over-Engineering Looks Like

```
OVER-ENGINEERING 1: ML ranking for all users
Cost: Additional $100K/month in ML inference
Benefit: 5% engagement increase... for engaged users only
Reality: 80% of users are passive; ML doesn't help them

Staff choice: ML ranking only for engaged users (top 20%)
Savings: $80K/month
Same engagement benefit for the users who matter

OVER-ENGINEERING 2: Real-time feed updates via WebSocket
Cost: $200K/month for connection infrastructure
Benefit: Posts appear instantly (push model)
Reality: Users refresh manually anyway; pull-to-refresh is expected behavior

Staff choice: Pull with short polling (30-second TTL)
Savings: $200K/month
Users still see fresh content within seconds

OVER-ENGINEERING 3: Global consistent fan-out
Cost: $150K/month for cross-region synchronization
Benefit: Followers in all regions see posts simultaneously
Reality: 100ms difference between regions is imperceptible

Staff choice: Regional fan-out with async cross-region sync
Savings: $100K/month
Trade-off: Post may appear 200ms later in distant regions

OVER-ENGINEERING 4: Personalized ranking for every refresh
Cost: $180K/month for ML inference on every request
Reality: Feed doesn't change much within 60 seconds

Staff choice: Cache ranking results for 60 seconds
Savings: $150K/month
Same user experience (feed doesn't change within a minute anyway)
```

## Cost-Aware Redesign

```
// Pseudocode: Cost-optimized feed architecture

CLASS CostOptimizedFeedSystem:
    
    FUNCTION design_for_cost():
        // 1. Hot/cold user tiering
        hot_users = users_with_activity_last_7_days  // 50% of users
        cold_users = users_without_activity_7_days    // 50% of users
        
        // Hot users: In-memory feed storage
        hot_storage_cost = hot_user_count * memory_cost_per_user
        
        // Cold users: SSD storage, warm on access
        cold_storage_cost = cold_user_count * ssd_cost_per_user
        
        // Savings: 50% reduction in memory costs
        
        // 2. Tiered caching
        tier_1_cache = recent_24h_content   // 500 GB, $30K/month
        tier_2_cache = recent_7d_content    // 5 TB, $60K/month (SSD)
        post_store = all_content            // Cold storage for old
        
        // 3. Adaptive fan-out
        FOR post IN new_posts:
            IF author.follower_count < 10000:
                // Small creator: Full push
                push_to_all_followers(post)
            ELSE:
                // Large creator: Hybrid
                push_to_active_followers(post)  // 20% of followers
                mark_for_pull(post, remaining_followers)
        
        // 4. Batch processing for non-urgent operations
        // Aggregate read counts every 5 minutes (not real-time)
        // Update engagement scores hourly (not per-interaction)
        
        // 5. Regional optimization
        // Process posts in region of origin
        // Sync to other regions async (< 500ms)
        // Avoid cross-region data transfer for reads
        
        RETURN CostOptimizedConfig(
            memory_savings = "50% ($75K/month)",
            compute_savings = "40% ($80K/month)",
            total_savings = "$155K/month (21% reduction)"
        )
```

---

# Part 12: Multi-Region & Global Considerations

## Data Locality

```
┌──────────────────────────────────────────────────────────────────────────--───┐
│                    MULTI-REGION FEED ARCHITECTURE                             │
│                                                                               │
│   REGION: US-EAST              REGION: EU-WEST             REGION: AP-EAST    │
│   ┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐ │
│   │  Feed Service   │         │  Feed Service   │         │  Feed Service   │ │
│   │  Feed Storage   │◄───────►│  Feed Storage   │◄───────►│  Feed Storage   │ │
│   │  Content Cache  │         │  Content Cache  │         │  Content Cache  │ │
│   │  Post Store     │         │  Post Store     │         │  Post Store     │ │
│   └────────┬────────┘         └────────┬────────┘         └────────┬────────┘ │
│            │                           │                           │          │
│            └───────────────────────────┴───────────────────────────┘          │
│                              ASYNC REPLICATION                                │
│                                                                               │
│   DATA LOCALITY RULES:                                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐     │
│   │  • User's feed: Stored in user's home region                        │     │
│   │  • Post content: Replicated to all regions (read-heavy)             │     │
│   │  • User metadata: Replicated to all regions (needed for rendering)  │     │
│   │  • Fan-out: Happens in each follower's home region                  │     │
│   │  • Ranking: Computed locally per region                             │     │
│   └─────────────────────────────────────────────────────────────────────┘     │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────--────┘
```

## Replication Strategies

```
WHAT IS REPLICATED:

POST CONTENT:
• Full replication to all regions
• Async, eventual consistency (< 500ms lag)
• Rationale: Posts are read-heavy, must be low-latency globally
• Size: ~500 GB/day, manageable for full replication

USER METADATA:
• Full replication to all regions
• Async, eventual consistency (< 1s lag)
• Rationale: Needed to render any feed (author name, avatar)

FEED STORAGE:
• NOT replicated between regions
• Each region stores feeds for users homed there
• Rationale: Feeds are user-specific, no benefit to replicating

SOCIAL GRAPH:
• Full replication to all regions
• Async, eventual consistency (< 5s lag)
• Rationale: Needed for fan-out, follow/unfollow can be eventual

ENGAGEMENT DATA:
• Regional aggregation, global merge hourly
• Not real-time (too expensive, not necessary)
• Rationale: Like counts don't need global precision
```

```
// Pseudocode: Cross-region post replication

CLASS CrossRegionReplicator:
    regions = ["us-east", "eu-west", "ap-east"]
    
    FUNCTION replicate_post(post, origin_region):
        // Write to origin first
        origin_store.write(post)
        
        // Async replicate to other regions
        FOR region IN regions:
            IF region != origin_region:
                queue_replication(post, region)
        
        // Don't wait for replication to complete
        RETURN success
    
    FUNCTION process_replication_queue(region):
        WHILE TRUE:
            post = replication_queue[region].pop()
            
            TRY:
                regional_store[region].write(post)
                confirm_replication(post.id, region)
            CATCH:
                // Retry with backoff
                replication_queue[region].push_with_delay(post, 5 seconds)
    
    FUNCTION handle_replication_lag():
        // If user requests post not yet replicated:
        // 1. Check if post exists in origin region
        // 2. If yes, fetch from origin (cross-region read)
        // 3. This is rare (< 0.1% of reads)
        
        IF post not in local_region:
            post = fetch_from_origin(post.id)
            // Also write to local for future reads
            async_write_local(post)
            RETURN post
```

## Traffic Routing

```
ROUTING STRATEGY:

GEO-DNS:
• Route users to nearest region based on IP
• 99% of users hit correct region on first request
• Edge case: VPN users may hit wrong region (acceptable latency penalty)

STICKY SESSIONS:
• Not required for feeds (stateless reads)
• User can hit any server in their region
• Feed storage is sharded, consistent hashing finds correct shard

DATA AFFINITY:
• User's feed always in home region
• Cross-region reads only for:
  - Post content not yet replicated (< 0.1%)
  - User traveling to different region (< 5% of requests)

USER TRAVELING:
When user in EU-WEST accesses feed from AP-EAST:
Option A: Serve from EU-WEST (home region) - 200ms latency
Option B: Migrate feed to AP-EAST temporarily - Complex
Option C: Serve with higher latency, prefetch popular content - Simple

CHOICE: Option A with CDN edge caching for content
• Feed structure from home region (200ms)
• Content from local CDN (10ms)
• Acceptable experience for occasional travel
```

## Failure Across Regions

```
SCENARIO 1: US-EAST region goes down

IMPACT:
• US users: ~100M affected
• Feed reads: Fail for US users
• Posts from US authors: Stop appearing globally (temporarily)

MITIGATION:
• Feed Storage: Cannot failover (user data not replicated)
• Posts: Available from other regions (replicated)
• Fan-out: Delayed for posts from US authors

USER EXPERIENCE:
• US users see error or cached feed
• Non-US users miss new posts from US authors (< 500ms old is fine)

RECOVERY:
• When US-EAST recovers, resume normal operation
• No data loss (feeds rebuild from social graph + posts)
• May take hours for all feeds to catch up
```

```
SCENARIO 2: Cross-region network partition

IMPACT:
• Regions operate independently
• Replication stops between regions
• Posts from one region don't appear in others

BEHAVIOR:
• Each region continues serving local users
• New posts only visible in origin region
• Follows/unfollows don't propagate

DETECTION:
• Replication lag alerts (> 5s triggers warning)
• Cross-region health checks fail

RESOLUTION:
• When partition heals, catch up replication
• Merge any conflicts (rare, use LWW for social graph)
• Posts have globally unique IDs, no conflicts possible
```

## When Multi-Region Is NOT Worth It

```
CASES WHERE SINGLE-REGION IS BETTER:

CASE 1: Small user base (< 10M users)
• Most users in one geography
• Multi-region adds complexity without benefit
• Exception: Regulatory requirements (GDPR)

CASE 2: Internal tools / enterprise products
• Users are employees, mostly in one location
• Occasional high latency is acceptable
• Operational simplicity trumps latency

CASE 3: Early-stage startup
• Focus on product-market fit, not global scale
• Multi-region is premature optimization
• Can add later when scale demands it

FOR NEWS FEED SPECIFICALLY:
• Multi-region is almost always required
• Users expect low-latency feeds globally
• Social products have inherently global user bases
• Exception: Regional social networks (e.g., country-specific)
```

---

# Part 13: Security & Abuse Considerations

## Abuse Vectors

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FEED SYSTEM ABUSE VECTORS                                │
│                                                                             │
│   ABUSE TYPE              │  ATTACK                │  SYSTEM IMPACT         │
│   ────────────────────────┼────────────────────────┼────────────────────────│
│   Spam Posting            │  Create millions of    │  Fills all feeds,      │
│                           │  spam posts            │  degrades UX           │
│   ────────────────────────┼────────────────────────┼────────────────────────│
│   Follow Bomb             │  Follow millions of    │  Fan-out explosion,    │
│                           │  accounts              │  storage bloat         │
│   ────────────────────────┼────────────────────────┼────────────────────────│
│   Feed Scraping           │  Automated reading     │  Load on Feed Service, │
│                           │  of all public feeds   │  data harvesting       │
│   ────────────────────────┼────────────────────────┼────────────────────────│
│   Engagement Fraud        │  Fake likes/comments   │  Corrupts ranking,     │
│                           │  via bot networks      │  unfair promotion      │
│   ────────────────────────┼────────────────────────┼────────────────────────│
│   Content Injection       │  XSS/malicious         │  Security breach,      │
│                           │  content in posts      │  user compromise       │
│   ────────────────────────┼────────────────────────┼────────────────────────│
│   Privacy Leakage         │  Infer private info    │  User trust erosion,   │
│                           │  from public feeds     │  regulatory issues     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Rate Abuse Patterns

```
SPAM POSTING DETECTION:

Signals:
• Post velocity: > 10 posts/hour from single account
• Content similarity: High cosine similarity between posts
• Link patterns: Same URL in multiple posts
• Account age: New accounts posting heavily
• Follow/follower ratio: Many follows, few followers

Mitigation:
• Rate limit: 10 posts/hour per account
• New account restrictions: 5 posts/day for first week
• Content hashing: Detect duplicate/near-duplicate posts
• ML classifier: Spam score on each post
• Manual review queue: High-spam-score posts held

FOLLOW BOMBING DETECTION:

Signals:
• Follow velocity: > 100 follows/hour
• Follow patterns: Following accounts sequentially (by ID)
• Unfollow rate: High follow + high unfollow = churn attack

Mitigation:
• Rate limit: 100 follows/day per account
• Cooldown: 1 follow/minute sustained
• Pattern detection: Flag sequential following
• Soft limits: Allow occasional bursts, block sustained abuse
```

```
// Pseudocode: Abuse detection system

CLASS AbuseDetector:
    
    FUNCTION check_post(post, author):
        signals = []
        
        // Velocity check
        recent_posts = get_posts_last_hour(author)
        IF len(recent_posts) > 10:
            signals.append(("high_velocity", 0.8))
        
        // Content similarity
        FOR recent IN recent_posts:
            similarity = cosine_similarity(post.content, recent.content)
            IF similarity > 0.9:
                signals.append(("duplicate_content", 0.9))
                BREAK
        
        // Account age
        IF author.age_days < 7:
            signals.append(("new_account", 0.3))
        
        // ML spam score
        spam_score = ml_spam_classifier.predict(post)
        IF spam_score > 0.7:
            signals.append(("ml_spam", spam_score))
        
        // Aggregate decision
        total_score = weighted_sum(signals)
        
        IF total_score > 0.9:
            RETURN BLOCK
        ELSE IF total_score > 0.7:
            RETURN REVIEW_QUEUE
        ELSE:
            RETURN ALLOW
    
    FUNCTION check_follow(follower, followee):
        // Rate limit
        follows_today = get_follows_today(follower)
        IF follows_today > 100:
            RETURN BLOCK
        
        // Velocity limit
        follows_last_minute = get_follows_last_minute(follower)
        IF follows_last_minute > 1:
            RETURN COOLDOWN(60 seconds)
        
        // Pattern detection
        IF is_sequential_following(follower):
            RETURN BLOCK
        
        RETURN ALLOW
```

## Data Exposure Risks

```
PRIVACY CONSIDERATIONS:

PUBLIC FEEDS:
• Anyone can see public posts
• Aggregating public posts reveals patterns
• "What you follow" reveals interests

PRIVATE FEEDS:
• Only approved followers see posts
• Implementation must be bulletproof
• Cache invalidation on follower removal

METADATA EXPOSURE:
• Like counts reveal popularity
• Timestamps reveal activity patterns
• Follower/following lists reveal relationships

MITIGATIONS:
• Rate limit API access (prevent bulk scraping)
• Require authentication for detailed data
• Aggregate public metrics (don't expose exact counts)
• Allow users to hide followers/following lists
• Audit logs for suspicious access patterns

COMPLIANCE CHECKLIST (L6 Relevance):
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│  REGULATION/REQUIREMENT   │  NEWS FEED IMPACT           │  DESIGN IMPLICATION              │
├───────────────────────────┼────────────────────────────┼──────────────────────────────────┤
│  GDPR (right to erasure)   │  Delete user's posts from   │  Post IDs in feeds; soft delete  │
│                            │  all followers' feeds      │  + propagation manifest          │
├───────────────────────────┼────────────────────────────┼──────────────────────────────────┤
│  Data minimization         │  Feed stores only IDs      │  No content duplication in feed  │
│                            │  Content fetched by ref    │  storage; single source of truth  │
├───────────────────────────┼────────────────────────────┼──────────────────────────────────┤
│  Cross-border transfer     │  EU users, US creators      │  Regional storage; replication   │
│                            │  (EU data in EU)            │  paths respect jurisdiction       │
├───────────────────────────┼────────────────────────────┼──────────────────────────────────┤
│  Audit trail               │  Moderation, deletion      │  Deletion log; data lineage       │
│                            │  must be traceable         │  for compliance verification     │
└───────────────────────────┴────────────────────────────┴──────────────────────────────────┘
```

## Privilege Boundaries

```
ACCESS CONTROL MODEL:

USER LEVEL:
• Can see own feed
• Can see public posts from anyone
• Can see private posts from approved followees
• Can post (subject to rate limits)
• Can follow/unfollow (subject to rate limits)

MODERATOR LEVEL:
• All user permissions
• Can remove posts (with audit log)
• Can restrict accounts (temporary)
• Cannot see private posts of others

ADMIN LEVEL:
• All moderator permissions
• Can see any post (for investigation)
• Can permanently ban accounts
• Can modify rate limits
• Full audit trail required

SYSTEM LEVEL:
• Internal services only
• No human access without justification
• All access logged and reviewed

SEPARATION OF CONCERNS:
• Feed generation: No access to private user data
• Ranking: Uses engagement signals, not content
• Abuse detection: Accesses content only for flagged posts
```

## Why Perfect Security Is Impossible

```
REALITY OF ABUSE PREVENTION:

1. Determined attackers will find ways
   • Distributed attacks across many accounts
   • Slow-and-low attacks under rate limits
   • Purchased aged accounts bypass new-account limits

2. False positives hurt legitimate users
   • Too aggressive → Users can't post/follow normally
   • Too permissive → Abuse gets through
   • No perfect threshold exists

3. Cat-and-mouse game
   • We build detector, attackers adapt
   • We detect new pattern, attackers change
   • Continuous investment required

4. Scale makes manual review impossible
   • 100M posts/day → 1.1K posts/second
   • Can't review even 0.1% manually
   • ML must do heavy lifting

STAFF APPROACH:
• Accept that some abuse will get through
• Optimize for quick detection and removal (not prevention)
• Make abuse expensive for attackers (rate limits, account aging)
• Focus on worst-case harm reduction (not perfection)
• Invest in user reporting + fast response
```

---

# Part 14: Evolution Over Time

## V1: Naive Design

```
INITIAL IMPLEMENTATION (startup scale):

Components:
• Single MySQL database
• Simple "posts" table
• Web server with feed endpoint

Feed Generation:
SELECT posts.* 
FROM posts 
JOIN follows ON posts.author_id = follows.followee_id 
WHERE follows.follower_id = :user_id 
ORDER BY posts.created_at DESC 
LIMIT 50

Characteristics:
• Simple to build (1 engineer, 1 week)
• Works perfectly for < 10K users
• No caching, no sharding, no ranking
• Feed generated on every request

SCALE LIMITS:
• 10K users: Works fine
• 100K users: Queries getting slow (100ms → 500ms)
• 1M users: Database becoming bottleneck
• 10M users: Complete failure without redesign
```

## What Breaks First

```
FAILURE PROGRESSION:

STAGE 1: Database read latency (100K users)
Symptom: Feed load time increases from 100ms to 500ms
Cause: Fan-out JOIN across follows + posts tables
Detection: Slow query logs, P95 latency alerts
Quick fix: Add indexes, read replicas

STAGE 2: Database write throughput (1M users)
Symptom: Post creation becomes slow, timeouts
Cause: Single primary cannot handle write volume
Detection: Write queue backup, replication lag
Quick fix: Write batching, queue posts for async processing

STAGE 3: Fan-out latency (10M users)
Symptom: Followers don't see new posts for minutes
Cause: Generating feeds on-read doesn't scale
Detection: "I posted but followers can't see it" complaints
Fundamental fix required: Precomputed feeds

STAGE 4: Celebrity problem (50M users)
Symptom: Celebrity post causes system-wide slowdown
Cause: Single post triggers 10M feed updates
Detection: Correlated spikes in latency + celebrity posts
Fundamental fix required: Hybrid push-pull model

STAGE 5: Global latency (100M+ users)
Symptom: Users in distant regions experience high latency
Cause: Single-region deployment, cross-world round trips
Detection: Latency split by geography
Fundamental fix required: Multi-region deployment
```

## V2: Intermediate Design

```
V2 IMPROVEMENTS (10M → 100M users):

CHANGE 1: Precomputed feeds
Before: Generate feed on each request
After: Precompute and store feeds, serve from cache

Implementation:
• Fan-out workers process new posts
• Write post ID to each follower's feed storage
• Feed reads are simple lookups

Result: Read latency drops from 500ms to 10ms

CHANGE 2: Sharded storage
Before: Single database for all data
After: Sharded by user ID

Implementation:
• Consistent hashing for user → shard mapping
• Each shard handles 1/N of users
• Cross-shard operations avoided by design

Result: Linear scalability for storage

CHANGE 3: Content caching
Before: Fetch post content from database
After: Hot posts cached in Redis/Memcached

Implementation:
• Cache post content by post ID
• TTL: 24 hours for recent posts
• LRU eviction for older content

Result: 99% cache hit rate for content reads

CHANGE 4: Async processing
Before: Synchronous post creation
After: Queue-based async fan-out

Implementation:
• Post creation writes to queue
• Fan-out workers process queue
• Decouples post creation from fan-out

Result: Post creation latency < 100ms regardless of follower count
```

## Long-Term Stable Architecture

```
V3 MATURE ARCHITECTURE (100M+ users):

┌─────────────────────────────────────────────────────────────────────────────┐
│                         PRODUCTION-READY FEED SYSTEM                        │
│                                                                             │
│   INGESTION LAYER:                                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Post Service → Event Queue → Fan-out Workers → Feed Storage        │   │
│   │       ↓                                                             │   │
│   │  Post Store (durable storage of all posts)                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   SERVING LAYER:                                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  CDN → Load Balancer → Feed Service → Feed Storage                  │   │
│   │                              ↓                                      │   │
│   │                        Content Cache → Post Store                   │   │
│   │                              ↓                                      │   │
│   │                        Ranking Service (optional)                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   SUPPORT SYSTEMS:                                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Social Graph Service (follows/followers)                           │   │
│   │  User Metadata Service (profiles, settings)                         │   │
│   │  Abuse Detection System                                             │   │
│   │  Metrics & Monitoring                                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CHARACTERISTICS:                                                          │
│   • Hybrid push-pull for celebrity handling                                 │
│   • Multi-region with async replication                                     │
│   • Hot/cold tiering for cost optimization                                  │
│   • ML ranking for engaged users only                                       │
│   • Graceful degradation at all layers                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## How Incidents Drive Redesign

```
INCIDENT 1: The Celebrity Cascade (Year 2)

What happened:
• Celebrity with 50M followers posts
• Fan-out workers process 50M writes
• Fan-out queue backs up to 2 hours
• All users' feeds become stale

Root cause:
• Pure push model doesn't scale for celebrities
• No priority separation between celebrities and normal users

Redesign:
• Hybrid push-pull model introduced
• Celebrity posts pulled on-read, not pushed
• Priority queues for fan-out (VIP users first)

---

INCIDENT 2: The Thundering Herd (Year 3)

What happened:
• Feed Storage leader node fails
• All reads to that shard fail
• Clients retry immediately
• Retry storm overwhelms cluster

Root cause:
• No client-side backoff
• No load shedding on server side
• Single point of failure for shard

Redesign:
• Read replicas for Feed Storage
• Client retry with exponential backoff
• Server-side load shedding at 80% capacity
• Circuit breakers on Feed Service

---

INCIDENT 3: The Cache Stampede (Year 4)

What happened:
• Cache TTL expires for popular content
• 100K simultaneous requests hit Post Store
• Post Store overwhelmed, latency spikes to 10s
• Cascading failures across system

Root cause:
• Synchronized cache expiration
• No stampede protection

Redesign:
• Staggered TTLs (jitter)
• Cache "early refresh" before expiration
• Request coalescing for same key
• Background cache warming

---

INCIDENT 4: The Compliance Crisis (Year 5)

What happened:
• GDPR "right to be forgotten" request
• User's posts in 200M followers' feeds
• Deletion takes 72 hours
• Regulatory fine threatened

Root cause:
• No data lineage tracking
• Deletion not designed into system
• Fan-out writes created data sprawl

Redesign:
• Post content stored by reference (ID only in feeds)
• Soft delete with TTL propagation
• Deletion manifest for compliance tracking
• Regular audit of data locations
```

## Structured Incident Table (L6 Review Format)

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                    REAL INCIDENT: THE CELEBRITY CASCADE (Year 2)                             │
│                    Structured format for post-mortem and design review                        │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│  DIMENSION           │  CONTENT                                                              │
├───────────────────────┼──────────────────────────────────────────────────────────────────────┤
│  CONTEXT              │  Platform at 80M DAU. Pure push fan-out. Celebrity accounts (1M+      │
│                       │  followers) treated like normal users. No threshold logic.           │
├───────────────────────┼──────────────────────────────────────────────────────────────────────┤
│  TRIGGER              │  Top celebrity (50M followers) posted breaking news. Single post      │
│                       │  enqueued 50M fan-out tasks.                                          │
├───────────────────────┼──────────────────────────────────────────────────────────────────────┤
│  PROPAGATION          │  Fan-out queue depth grew 0 → 50M in 2 minutes. Workers saturated.   │
│                       │  Queue processing fell behind. Normal users' posts stalled. All       │
│                       │  feeds became stale (no new content for 30+ minutes).                │
├───────────────────────┼──────────────────────────────────────────────────────────────────────┤
│  USER IMPACT          │  80M users saw no new posts for 30-45 minutes. Engagement dropped     │
│                       │  40%. Support tickets spiked. Revenue impact: ~$2M (estimated).      │
├───────────────────────┼──────────────────────────────────────────────────────────────────────┤
│  ENGINEER RESPONSE    │  T+15m: Scaled workers 4x. Queue still growing.                      │
│                       │  T+25m: Disabled fan-out for celebrity, served from read-merge.      │
│                       │  T+45m: Queue began draining. T+2h: Full recovery.                   │
├───────────────────────┼──────────────────────────────────────────────────────────────────────┤
│  ROOT CAUSE           │  Design assumed fan-out time bounded. Power-law follower distribution│
│                       │  not modeled. No tiering by author size.                             │
├───────────────────────┼──────────────────────────────────────────────────────────────────────┤
│  DESIGN CHANGE        │  Hybrid push-pull: threshold 10K (push) / 1M (pull). Celebrity       │
│                       │  Index for pull-at-read. Priority queues (active users first).       │
│                       │  Celebrity posts never enter fan-out queue.                          │
├───────────────────────┼──────────────────────────────────────────────────────────────────────┤
│  LESSON               │  "Design for the tail, not the median." Staff insight: One celebrity │
│                       │  can saturate a system built for averages. Threshold-based routing   │
│                       │  is non-negotiable at scale.                                          │
└───────────────────────┴──────────────────────────────────────────────────────────────────────┘
```

---

# Part 15: Alternatives & Explicit Rejections

## Alternative 1: Pure Push Model (Fan-Out on Write)

```
DESCRIPTION:
Every post is written to every follower's feed immediately.

WHY IT SEEMS ATTRACTIVE:
• Simple conceptual model
• Read path is trivially fast (just fetch precomputed feed)
• Consistency: Everyone sees same feed

WHY A STAFF ENGINEER REJECTS IT:
• Celebrity problem: 50M follower post = 50M writes
  - Takes hours to complete
  - Blocks queue for everyone
  - Cost scales with follower count × post volume

• Write amplification:
  - 100M posts/day × 150 avg followers = 15B writes/day
  - For 200M DAU, could be 200B writes/day
  - Storage costs explode

• Wasted work:
  - Many users never log in
  - Writing to inactive users' feeds is pure waste
  - 50%+ of writes are never read

VERDICT: Works for small scale, breaks catastrophically at large scale
```

## Alternative 2: Pure Pull Model (Fan-In on Read)

```
DESCRIPTION:
No precomputation. Generate feed on every request by querying all followees' posts.

WHY IT SEEMS ATTRACTIVE:
• No write amplification
• No storage for feeds
• Always fresh (no staleness)
• Simpler to implement initially

WHY A STAFF ENGINEER REJECTS IT:
• Read latency explosion:
  - User follows 500 people
  - Need to query 500 users' recent posts
  - Even with indexes: 500 queries × 5ms = 2.5 seconds
  - Unacceptable for social product

• Database load:
  - Every feed load = 500 queries
  - 2B feed loads/day × 500 = 1T queries/day
  - No database can handle this

• No room for ranking:
  - Must fetch all posts before ranking
  - ML ranking impossible at read time
  - Stuck with chronological order

• Inconsistent latency:
  - Heavy follower = slow feed
  - Light follower = fast feed
  - Unpredictable user experience

VERDICT: Only works for very small scale or products with few follows per user
```

## Alternative 3: Event Sourcing with CQRS

```
DESCRIPTION:
Store all events (posts, likes, follows) in event log.
Build read-optimized views asynchronously.

WHY IT SEEMS ATTRACTIVE:
• Complete audit trail
• Easy to add new views
• Rebuild views from events
• Academically elegant

WHY A STAFF ENGINEER REJECTS IT:
• Operational complexity:
  - Event log grows forever (100M posts/day = 36B posts/year)
  - View rebuilding takes hours/days
  - More infrastructure to operate

• Over-engineering for feeds:
  - We don't need complete audit trail for every post
  - View rebuilding is rare (not worth optimizing)
  - Simpler model achieves same goals

• Latency penalty:
  - Async view building adds latency
  - Events → Views → Reads adds hops
  - Direct writes are faster

• Skills mismatch:
  - Team needs CQRS expertise
  - Debugging is harder
  - Oncall burden increases

VERDICT: Adds complexity without proportional benefit for feed use case
```

---

# Part 16: Interview Calibration

## How Interviewers Probe This System

```
DIRECT PROBES:
• "Design a news feed system"
• "How would you build Twitter's home timeline?"
• "Design Instagram's feed"

INDIRECT PROBES (embedded in other questions):
• "How do you handle the celebrity problem?"
  → Tests hybrid push-pull understanding
• "What happens when a user has 10M followers?"
  → Tests scaling intuition
• "How do you ensure fresh content?"
  → Tests caching and staleness thinking

DEEP DIVE AREAS:
1. Fan-out strategy (push vs pull vs hybrid)
2. Storage choices (in-memory vs disk)
3. Ranking approach (chronological vs ML)
4. Failure handling (degradation strategy)
5. Scale numbers (can you estimate QPS, storage?)

RED FLAG QUESTIONS:
• "What database would you use?"
  → Interviewer suspects candidate is pattern-matching
• "How would you make this globally consistent?"
  → Testing if candidate over-engineers
• "Can you estimate the storage requirements?"
  → Testing if candidate can do back-of-envelope
```

## Common L5 Mistakes

```
MISTAKE 1: Choosing pure push without considering celebrities
L5: "We'll fan out every post to all followers"
Staff: "Pure push fails for large followings. At 10M followers, 
       fan-out takes hours. We need hybrid: push for normal 
       users, pull for celebrities."

MISTAKE 2: Over-engineering consistency
L5: "We need strong consistency so everyone sees the same feed"
Staff: "Eventual consistency is fine for feeds. Users don't 
       compare feeds. 100ms staleness is invisible. Strong 
       consistency would add 50ms latency for no benefit."

MISTAKE 3: Ignoring hot/cold data patterns
L5: "Store all feeds in Redis for fast access"
Staff: "50% of users are inactive. Keeping their feeds in 
       memory is wasted cost. Hot/cold tiering: active users 
       in memory, inactive on SSD, rebuild on access."

MISTAKE 4: Under-estimating storage needs
L5: "We'll store 100 posts per feed, that's 100 × 200M = 20B IDs"
Staff: "That's 20B × 8 bytes = 160 GB just for IDs. Add metadata, 
       replication, buffer... We need 500GB-1TB for feed storage 
       alone, plus 10TB+ for content cache."

MISTAKE 5: Forgetting about abuse
L5: "Users can post and follow freely"
Staff: "Without rate limits, a single spammer can fill millions 
       of feeds. We need: post rate limits, follow rate limits, 
       spam detection, and abuse reporting."
```

## Staff-Level Answers

```
QUESTION: "How would you design the fan-out?"

L5 ANSWER:
"When a user posts, we add the post ID to each follower's feed 
in Redis. We use a list data structure and push to the front."

STAFF ANSWER:
"Fan-out strategy depends on the author's follower count. For 
users with < 10K followers, we do synchronous push—it's fast 
and keeps feeds fresh. For users with 10K-1M followers, we do 
async push with priority queuing. For celebrities with 1M+ 
followers, we don't push at all—we fetch their posts at read 
time and merge with the precomputed feed. This hybrid approach 
balances latency, freshness, and infrastructure cost. The 
threshold values are tunable based on our capacity and SLOs."

---

QUESTION: "How do you handle ranking?"

L5 ANSWER:
"We use an ML model to score each post and sort by score."

STAFF ANSWER:
"Ranking adds latency and cost, so we're selective about who 
gets it. For casual users (80% of base), chronological order 
is fine—they scroll infrequently and ML doesn't measurably 
improve engagement. For engaged users (top 20%), we run ML 
ranking because they're worth the cost. The model is simple: 
engagement probability based on recency, author relationship, 
and content type. We cache ranking results for 60 seconds 
because feeds don't change that fast. Full re-ranking happens 
on meaningful signals: user interacts, new high-priority 
post arrives, or cache expires."
```

## Example Phrases Staff Engineers Use

```
TRADE-OFF ARTICULATION:
• "The trade-off here is freshness vs infrastructure cost..."
• "We're accepting eventual consistency because..."
• "This adds latency, but it's worth it because..."

SCALE AWARENESS:
• "At 200M DAU, that's roughly 2.3K QPS..."
• "If average follow count is 150, that's 15B fan-out writes per day..."
• "Memory for this is approximately..."

FAILURE THINKING:
• "When the cache fails, we fall back to..."
• "If fan-out is delayed, users see slightly stale feeds, which is acceptable..."
• "The blast radius of this failure is limited to..."

SIMPLICITY BIAS:
• "We could add ML ranking, but for 80% of users it doesn't help..."
• "This is simpler and achieves the same goal..."
• "Let's start with the simple approach and evolve if needed..."

EXPERIENCE SIGNALS:
• "I've seen this fail when..."
• "In practice, users don't notice..."
• "The operational burden of this approach is..."
```

## Leadership Explanation (How to Teach This System)

```
WHEN EXPLAINING TO STAKEHOLDERS:

ONE-LINER:
"News feed is a hybrid push-pull system: we precompute feeds for normal users
so reads are fast, and we fetch celebrity content at read time so writes
never block. The Staff judgment is where to draw the line."

ELEVATOR PITCH (30 sec):
"We optimize for the common case—most users follow 150 people, most creators
have < 10K followers. For that 99%, push works great. The 1% of celebrities
would break pure push, so we pull their content when you load your feed.
Trade-off: celebrity posts may be a few seconds behind, but the system stays
fast for everyone."

HOW TO TEACH A SENIOR:
• Start with the mailbox analogy (Part 1)
• Have them compute: 1 post × 100M followers = how long to fan out?
• Then ask: "What if we didn't fan out for that user?" (pull at read)
• Walk through degradation hierarchy (Part 9)—what happens when each piece fails
• End with: "The Staff question is always: what's the blast radius of this
  decision?"

COMMON SENIOR MISTAKE TO FLAG:
Optimizing for perfection. Seniors often propose "we need strong consistency"
or "we need real-time for everyone." The Staff response: "Users don't notice
5-minute staleness. They absolutely notice 500ms latency."
```

---

# Part 17: Diagrams

## Diagram 1: High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       NEWS FEED SYSTEM ARCHITECTURE                         │
│                                                                             │
│   ┌─────────┐    ┌─────────────┐    ┌─────────────┐     ┌─────────────┐     │
│   │  Users  │───►│  CDN/Edge   │───►│ API Gateway │───-►│Load Balancer│     │
│   └─────────┘    └─────────────┘    └─────────────┘     └──────┬──────┘     │
│                                                                │            │
│                          ┌─────────────────────────────────────┼──────┐     │
│                          │                                     ▼      │     │
│   WRITE PATH:            │              ┌───────────────────────────┐ │     │
│   ┌─────────────┐        │              │       FEED SERVICE        │ │     │
│   │ Post Service│        │              │  • Assemble feeds         │ │     │
│   │ • Validate  │        │              │  • Handle ranking         │ │     │
│   │ • Store     │        │              │  • Manage pagination      │ │     │
│   └──────┬──────┘        │              └───────────┬───────────────┘ │     │
│          │               │                          │                 │     │
│          ▼               │                          ▼                 │     │
│   ┌─────────────┐        │              ┌───────────────────────────┐ │     │
│   │ Post Store  │◄───────┼──────────────│     CONTENT CACHE         │ │     │
│   │ (Durable)   │        │              │  • Post content           │ │     │
│   └──────┬──────┘        │              │  • User metadata          │ │     │
│          │               │              └───────────────────────────┘ │     │
│          ▼               │                          │                 │     │
│   ┌─────────────┐        │                          ▼                 │     │
│   │ Event Queue │        │              ┌───────────────────────────┐ │     │
│   └──────┬──────┘        │              │      FEED STORAGE         │ │     │
│          │               │              │  • Precomputed feeds      │ │     │
│          ▼               │              │  • Sharded by user        │ │     │
│   ┌─────────────┐        │              └───────────────────────────┘ │     │
│   │ Fan-out     │        │                                            │     │
│   │ Workers     │────────┘                                            │     │
│   └─────────────┘                                                     │     │
│                                                                       │     │
│   SUPPORT SERVICES:                                                   │     │
│   ┌─────────────────────────────────────────────────────────────────┐ │     │
│   │  Social Graph │  User Service │  Ranking Service │  Abuse Det.  │ │     │
│   └─────────────────────────────────────────────────────────────────┘ │     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 2: Fan-Out Decision Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      FAN-OUT STRATEGY DECISION TREE                         │
│                                                                             │
│                           NEW POST CREATED                                  │
│                                 │                                           │
│                                 ▼                                           │
│                    ┌────────────────────────┐                               │
│                    │  Get Author's Follower │                               │
│                    │       Count            │                               │
│                    └───────────┬────────────┘                               │
│                                │                                            │
│              ┌─────────────────┼─────────────────┐                          │
│              │                 │                 │                          │
│              ▼                 ▼                 ▼                          │
│     ┌────────────────┐ ┌────────────────┐ ┌────────────────┐                │
│     │  < 10K         │ │  10K - 1M      │ │  > 1M          │                │
│     │  SMALL CREATOR │ │  MEDIUM        │ │  CELEBRITY     │                │
│     └───────┬────────┘ └───────┬────────┘ └───────┬────────┘                │
│             │                  │                  │                         │
│             ▼                  ▼                  ▼                         │
│     ┌────────────────┐ ┌────────────────┐ ┌────────────────┐                │
│     │  FULL PUSH     │ │  ASYNC PUSH    │ │  NO PUSH       │                │
│     │  Synchronous   │ │  Queue-based   │ │  Pull on read  │                │
│     │  Immediate     │ │  Prioritized   │ │  Merge at      │                │
│     │  delivery      │ │  delivery      │ │  serve time    │                │
│     └───────┬────────┘ └───────┬────────┘ └───────┬────────┘                │
│             │                  │                  │                         │
│             ▼                  ▼                  ▼                         │
│     ┌────────────────┐ ┌────────────────┐ ┌────────────────┐                │
│     │ Write to all   │ │ Write to       │ │ Mark post as   │                │
│     │ followers'     │ │ active         │ │ "celebrity"    │                │
│     │ feeds now      │ │ followers'     │ │ in Post Store  │                │
│     │                │ │ feeds          │ │                │                │
│     │ Latency: 0     │ │ Latency: <1min │ │ Latency: 0     │                │
│     │ Fan-out: Full  │ │ Fan-out: 80%   │ │ Fan-out: 0%    │                │
│     └────────────────┘ └────────────────┘ └────────────────┘                │
│                                                                             │
│   AT READ TIME:                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Fetch precomputed feed (small + medium creators' posts)         │   │
│   │  2. Fetch celebrity posts (separate query)                          │   │
│   │  3. Merge and rank                                                  │   │
│   │  4. Return combined feed                                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 3: Failure Propagation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       FAILURE PROPAGATION PATHS                             │
│                                                                             │
│   SCENARIO: Feed Storage Shard Failure                                      │
│                                                                             │
│   T+0s: Shard 7 (1/16 of users) becomes unavailable                         │
│         │                                                                   │
│         ▼                                                                   │
│   T+1s: Feed Service receives errors for shard 7 requests                   │
│         │                                                                   │
│         ├──► WITHOUT MITIGATION:                                            │
│         │    • 6.25% of feed requests fail                                  │
│         │    • Users see error page                                         │
│         │    • No cascade (other shards unaffected)                         │
│         │                                                                   │
│         └──► WITH MITIGATION (graceful degradation):                        │
│              │                                                              │
│              ▼                                                              │
│         ┌─────────────────────────────────────────────────────────────┐     │
│         │  DEGRADED MODE:                                             │     │
│         │  1. Return cached feed if available (stale OK)              │     │
│         │  2. If no cache, build minimal feed from Post Store         │     │
│         │     (recent posts from top followees)                       │     │
│         │  3. Show "Feed may be incomplete" banner                    │     │
│         │  4. Disable feed ranking (too slow in degraded mode)        │     │
│         └─────────────────────────────────────────────────────────────┘     │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────     │
│                                                                             │
│   SCENARIO: Content Cache Stampede                                          │
│                                                                             │
│   T+0s: Popular post's cache entry expires                                  │
│         │                                                                   │
│         ▼                                                                   │
│   T+0.1s: 10K concurrent requests hit Post Store for same post              │
│         │                                                                   │
│         ├──► WITHOUT MITIGATION:                                            │
│         │    • Post Store overwhelmed                                       │
│         │    • Latency spikes to 10s                                        │
│         │    • Cascading timeouts across system                             │
│         │    • All feeds slow, not just affected post                       │
│         │                                                                   │
│         └──► WITH MITIGATION (request coalescing):                          │
│              │                                                              │
│              ▼                                                              │
│         ┌─────────────────────────────────────────────────────────────┐     │
│         │  REQUEST COALESCING:                                        │     │
│         │  1. First request triggers Post Store fetch                 │     │
│         │  2. Subsequent requests wait on in-flight fetch             │     │
│         │  3. Single Post Store query serves all 10K requests         │     │
│         │  4. Result cached, future requests served from cache        │     │
│         │                                                             │     │
│         │  RESULT: 1 Post Store query instead of 10K                  │     │
│         └─────────────────────────────────────────────────────────────┘     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 4: System Evolution Timeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NEWS FEED SYSTEM EVOLUTION                               │
│                                                                             │
│   YEAR 1                YEAR 2                YEAR 3              YEAR 4+   │
│   10K users            1M users              100M users           500M+     │
│      │                    │                     │                   │       │
│      ▼                    ▼                     ▼                   ▼       │
│   ┌────────┐          ┌────────┐           ┌────────┐          ┌────────┐   │
│   │  V1    │          │  V2    │           │  V3    │          │  V4    │   │
│   │        │          │        │           │        │          │        │   │
│   │ Single │   ──►    │Sharded │    ──►    │Hybrid  │   ──►    │Multi-  │   │
│   │ MySQL  │          │ + Cache│           │Push/   │          │Region  │   │
│   │        │          │        │           │Pull    │          │        │   │
│   └────────┘          └────────┘           └────────┘          └────────┘   │
│                                                                             │
│   TRIGGERS:           TRIGGERS:            TRIGGERS:           TRIGGERS:    │
│   • Works fine        • DB read latency    • Celebrity post    • EU users   │
│   • Simple ops        • Write throughput   • Fan-out queues    • Asia       │
│   • 1 engineer        • Feed staleness     • Storage costs     • Latency    │
│                                                                             │
│   CHANGES:            CHANGES:             CHANGES:            CHANGES:     │
│   • None needed       • Read replicas      • Celebrity detect  • Regional   │
│                       • Redis cache        • Pull-on-read      │ deploy     │
│                       • User sharding      • Hot/cold tier     • Async      │
│                       • Async fan-out      • ML ranking        │ repl.      │
│                                            • Abuse detection   • Geo-DNS    │
│                                                                             │
│   TEAM:               TEAM:                TEAM:               TEAM:        │
│   1 engineer          3 engineers          10 engineers        20+ eng      │
│   No oncall           Weekly oncall        Daily oncall        24/7 oncall  │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────     │
│                                                                             │
│   KEY INSIGHT: Each stage solves the PREVIOUS stage's problem.              │
│   Don't build V3 when V1 problems haven't appeared yet.                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 18: Brainstorming, Exercises & Redesigns

## "What If X Changes?" Questions

```
QUESTION 1: What if average follower count doubles?
Impact:
• Fan-out volume doubles (15B → 30B writes/day)
• Celebrity threshold may need adjustment
• Storage costs increase proportionally

Redesign considerations:
• Lower celebrity threshold (10K → 5K)
• More aggressive pull model
• Consider local-only fan-out with cross-region pull

---

QUESTION 2: What if we add video posts?
Impact:
• Content size increases 100x (1KB → 100KB)
• CDN costs dominate
• Transcoding needed

Redesign considerations:
• Separate video pipeline
• Aggressive CDN caching
• Adaptive bitrate streaming
• Video preview in feed, full video separate

---

QUESTION 3: What if feed must be real-time (< 1 second)?
Impact:
• Async fan-out no longer acceptable
• Push model required for all users
• Celebrity problem becomes critical

Redesign considerations:
• Hybrid with aggressive push
• WebSocket for engaged users
• Accept higher cost for lower latency
• Limit celebrity post frequency

---

QUESTION 4: What if we must support "unsend" (delete within 5 minutes)?
Impact:
• Post IDs in feeds must be checked against deletion list
• Can't rely on precomputed feeds alone
• Deletion must propagate quickly

Redesign considerations:
• Deletion bloom filter (fast check)
• Soft delete with TTL
• Pull-on-read for deletion freshness
• Accept 5-minute window for propagation

---

QUESTION 5: What if storage costs double?
Impact:
• Current $730K → $1.4M monthly
• Hot/cold tiering becomes critical
• Some features may become uneconomical

Redesign considerations:
• Aggressive tiering (active = 7 days → 3 days)
• Smaller feed size (500 posts → 200 posts)
• More pull, less push
• Compression for stored feeds
```

## Redesign Exercises

```
EXERCISE 1: Design for 10% of current cost

Constraints:
• Budget: $73K/month (was $730K)
• Must maintain core functionality
• Latency can increase to 500ms P50

Approach:
1. Eliminate in-memory feed storage → All disk-based
2. No ranking → Chronological only
3. Pure pull model → No fan-out infrastructure
4. Aggressive caching → Only popular content
5. Single region → Accept higher latency globally

Trade-offs:
• 10x latency increase (50ms → 500ms)
• No personalization
• Global users experience 200-500ms extra latency

---

EXERCISE 2: Design for 10x scale (2B DAU)

Constraints:
• 2B daily active users
• 230K feed requests/second
• 1B posts/day

Approach:
1. Regionalized architecture → Independent regions
2. Celebrity threshold → 100K (not 1M)
3. Feed storage → Tiered by activity (daily/weekly/monthly)
4. Content → CDN-first, origin only for misses
5. Ranking → Batch-precomputed, not real-time

New costs:
• ~$7M/month (10x scale, ~10x cost)
• 200+ engineers
• Multiple oncall rotations

---

EXERCISE 3: Design for compliance-first (GDPR strict mode)

Constraints:
• User data must be deletable within 24 hours
• No data leaves user's declared region
• Full audit trail for all data access

Approach:
1. Regional data isolation → No cross-region replication of user data
2. Content references only → Store post IDs, not content
3. Deletion manifest → Track all data locations
4. Access logging → Every read logged with purpose
5. Consent-based features → Ranking only with consent

Trade-offs:
• 30% higher latency (no global caching)
• 20% higher cost (audit infrastructure)
• Slower feature velocity (privacy review required)
```

## Failure Injection Exercises

```
EXERCISE 1: Simulate celebrity post with full push

Setup:
• Create test celebrity with 10M followers
• Post from celebrity account
• Observe fan-out behavior

Expected behavior (without hybrid):
• Fan-out queue grows rapidly
• Other posts delayed
• Feed staleness increases globally

Validate mitigation:
• Celebrity detection should trigger
• Post should be marked for pull-on-read
• Fan-out queue should remain stable

---

EXERCISE 2: Kill random Feed Storage shard

Setup:
• Identify one of 16 Feed Storage shards
• Terminate all replicas of that shard
• Observe system behavior

Expected behavior:
• 6.25% of feed requests fail initially
• Graceful degradation should activate
• Degraded feeds should be served

Validate:
• Error rate drops after degradation activates
• Users see "limited feed" rather than errors
• Shard recovery restores full functionality

---

EXERCISE 3: Cache stampede simulation

Setup:
• Insert popular post with 1-second TTL
• Generate 10K concurrent requests when TTL expires
• Measure Post Store load

Expected behavior (without coalescing):
• 10K queries hit Post Store
• Latency spikes

Validate mitigation:
• Request coalescing should activate
• Post Store sees ~1 query, not 10K
• Latency remains stable
```

## Trade-off Debates

```
DEBATE 1: Chronological vs Algorithmic Ranking

POSITION A: Chronological is simpler and users prefer it
• No ML infrastructure needed
• Transparent (users understand ordering)
• Lower cost
• Avoids filter bubble

POSITION B: Algorithmic ranking increases engagement
• Users see relevant content first
• Reduces information overload
• Higher engagement metrics
• Competitive necessity

STAFF RESOLUTION:
Offer both. Default to chronological for simplicity.
Algorithmic ranking for users who opt in or show engagement.
Don't force ML on users who don't benefit.

---

DEBATE 2: Freshness vs Efficiency

POSITION A: Minimize staleness, users expect real-time
• Push all posts immediately
• Higher infrastructure cost
• Better user experience

POSITION B: Accept staleness, optimize for cost
• Async fan-out with minutes of delay
• Lower cost
• Most users don't notice

STAFF RESOLUTION:
Tiered staleness. VIP users (verified, paying) get
sub-second freshness. Regular users get <5 minute
freshness. Staleness is invisible for 95% of users.

---

DEBATE 3: Single Global Feed vs Regional Feeds

POSITION A: Single global feed, consistent worldwide
• Users traveling see same feed
• Simpler mental model
• Higher latency for distant regions

POSITION B: Regional feeds, optimized per region
• Lower latency
• Regional content prioritization
• Inconsistent experience when traveling

STAFF RESOLUTION:
Feed structure is global (same follows, same posts).
Content serving is regional (local CDN, local cache).
Balance: consistent experience with regional optimization.
```

---

# Part 19: Additional Staff-Level Depth (Reviewer Additions)

## Retry Storm Handling for Feed Systems

Feed systems are particularly vulnerable to retry storms because users have a natural "pull-to-refresh" behavior when feeds fail to load.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FEED RETRY STORM ANATOMY                                 │
│                                                                             │
│   SCENARIO: Feed Storage shard becomes slow (not down)                      │
│                                                                             │
│   T+0:    Shard latency increases from 10ms to 500ms                        │
│   T+1s:   User sees spinner, pulls to refresh (natural behavior)            │
│   T+2s:   First request still pending, second request starts                │
│   T+3s:   Both requests timeout, user refreshes again                       │
│   T+5s:   3 concurrent requests per affected user                           │
│   T+10s:  Cascade: 6.25% of users × 3x requests = 18.75% extra load         │
│   T+15s:  Extra load spreads to healthy shards via Content Cache            │
│   T+20s:  System-wide latency degradation                                   │
│                                                                             │
│   ROOT CAUSE: Slow shard, not failed shard (harder to detect)               │
│                                                                             │
│   MITIGATIONS:                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. CLIENT-SIDE DEBOUNCE                                            │   │
│   │     • Disable refresh button for 2 seconds after tap                │   │
│   │     • Show "still loading" instead of allowing retry                │   │
│   │     • Reduces user-initiated retry storms                           │   │
│   │                                                                     │   │
│   │  2. REQUEST DEDUPLICATION                                           │   │
│   │     • Server tracks in-flight requests per user                     │   │
│   │     • Second request waits on first (request coalescing)            │   │
│   │     • Returns same result to both requests                          │   │
│   │                                                                     │   │
│   │  3. ADAPTIVE TIMEOUT                                                │   │
│   │     • If shard is slow, reduce timeout and fail fast                │   │
│   │     • Return degraded feed (cached) instead of waiting              │   │
│   │     • User gets something instead of spinner                        │   │
│   │                                                                     │   │
│   │  4. LOAD SHEDDING BASED ON SHARD HEALTH                             │   │
│   │     • If shard > 80% latency SLO, start shedding new requests       │   │
│   │     • Serve from cache only for that shard                          │   │
│   │     • Better: 6.25% users get stale feeds than 100% get slow feeds  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

```
// Pseudocode: Request deduplication for feed loads

CLASS FeedRequestCoalescer:
    in_flight = {}  // user_id -> Future
    lock = Lock()
    
    FUNCTION load_feed(user_id):
        WITH lock:
            IF user_id IN in_flight:
                // Request already in progress, wait on it
                RETURN in_flight[user_id].await()
            
            // First request for this user, create future
            future = Future()
            in_flight[user_id] = future
        
        TRY:
            result = actually_load_feed(user_id)
            future.complete(result)
            RETURN result
        CATCH error:
            future.fail(error)
            RAISE error
        FINALLY:
            WITH lock:
                del in_flight[user_id]
```

---

## Slow Ranking Service Degradation

Ranking is a non-essential enhancement. When it's slow, the system must degrade gracefully rather than fail entirely.

```
RANKING SERVICE DEGRADATION LEVELS:

LEVEL 0: NORMAL (Ranking P99 < 30ms)
• Full ML ranking for all feed requests
• Personalized ordering based on engagement prediction
• All features enabled

LEVEL 1: REDUCED FEATURES (Ranking P99 30-100ms)
• Skip expensive features (e.g., cross-user affinity)
• Use cached user embeddings instead of computing fresh
• Ranking still runs but faster
• User impact: Slightly less personalized

LEVEL 2: CACHED RANKINGS (Ranking P99 100-500ms)
• Return cached ranking from last successful computation
• Cache TTL: 5 minutes for active users, 1 hour for others
• User impact: Rankings may be 5 minutes stale

LEVEL 3: CHRONOLOGICAL FALLBACK (Ranking unavailable)
• Skip ranking entirely
• Return posts in reverse chronological order
• User impact: No personalization, but feed loads fast

LEVEL 4: EMERGENCY (Everything degraded)
• Return cached feed (if available)
• If no cache: Return empty feed with "try again later"
• User impact: May see stale or empty feed
```

```
// Pseudocode: Ranking with degradation

CLASS RankingWithDegradation:
    ranking_service = RankingService()
    ranking_cache = RankingCache()
    
    FUNCTION rank_feed(user_id, posts):
        // Check ranking service health
        health = ranking_service.get_health()
        
        IF health.p99_latency < 30:
            // Level 0: Normal
            RETURN ranking_service.rank(user_id, posts, full_features=TRUE)
        
        ELSE IF health.p99_latency < 100:
            // Level 1: Reduced features
            RETURN ranking_service.rank(user_id, posts, full_features=FALSE)
        
        ELSE IF health.p99_latency < 500:
            // Level 2: Cached rankings
            cached = ranking_cache.get(user_id)
            IF cached AND cached.age < 5 minutes:
                RETURN apply_cached_order(posts, cached.order)
            ELSE:
                RETURN sort_by_timestamp(posts)  // Fallback to chrono
        
        ELSE:
            // Level 3: Chronological
            log_metric("ranking_degraded_to_chronological")
            RETURN sort_by_timestamp(posts)
```

---

## Split-Brain During Multi-Region Partition

When regions become partitioned, each continues operating independently. This creates split-brain scenarios specific to news feeds.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              MULTI-REGION SPLIT-BRAIN SCENARIO                              │
│                                                                             │
│   SETUP:                                                                    │
│   • User A (home: US-EAST) follows User B (home: EU-WEST)                   │
│   • Network partition isolates US-EAST from EU-WEST                         │
│                                                                             │
│   DURING PARTITION:                                                         │
│                                                                             │
│   US-EAST PERSPECTIVE:               EU-WEST PERSPECTIVE:                   │
│   ┌─────────────────────┐           ┌─────────────────────┐                 │
│   │ User A loads feed   │           │ User B posts new    │                 │
│   │ User B's posts from │           │ content             │                 │
│   │ BEFORE partition    │           │ Post stored locally │                 │
│   │ shown (stale)       │           │ Cannot replicate to │                 │
│   │                     │           │ US-EAST             │                 │
│   └─────────────────────┘           └─────────────────────┘                 │
│                                                                             │
│   CONFLICT SCENARIOS:                                                       │
│                                                                             │
│   1. POST ORDERING:                                                         │
│      • User B posts in EU-WEST at T1                                        │
│      • User C (US-EAST) posts at T2                                         │
│      • When partition heals: Which order does A see?                        │
│      • Resolution: Global timestamp ordering (wall clock)                   │
│                                                                             │
│   2. FOLLOW/UNFOLLOW DURING PARTITION:                                      │
│      • User A unfollows User B during partition                             │
│      • User B's posts still replicated after heal                           │
│      • Resolution: Check follow status at read time, filter posts           │
│                                                                             │
│   3. ENGAGEMENT COUNT DIVERGENCE:                                           │
│      • Post liked in both regions independently                             │
│      • Each region has partial count                                        │
│      • Resolution: Merge counts (additive CRDT)                             │
│                                                                             │
│   POST-PARTITION HEALING:                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Posts replicated with timestamps (merge by time)                │   │
│   │  2. Follow graph changes replayed (LWW for conflicts)               │   │
│   │  3. Engagement counts merged (add all increments)                   │   │
│   │  4. Feeds rebuilt/updated with new posts                            │   │
│   │  5. Celebrity index synchronized                                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

```
// Pseudocode: Post-partition healing

CLASS PartitionHealingOrchestrator:
    
    FUNCTION heal_after_partition(local_region, remote_region):
        // Step 1: Sync posts (no conflicts, append-only)
        missing_posts = remote_region.get_posts_since(last_sync_time)
        FOR post IN missing_posts:
            local_store.write_if_not_exists(post)
            content_cache.warm(post)
        
        // Step 2: Merge follow graph (LWW per edge)
        follow_changes = remote_region.get_follow_changes_since(last_sync_time)
        FOR change IN follow_changes:
            local_change = local_graph.get_edge(change.follower, change.followee)
            IF change.timestamp > local_change.timestamp:
                local_graph.apply(change)
        
        // Step 3: Merge engagement counts (additive)
        engagement_deltas = remote_region.get_engagement_deltas_since(last_sync_time)
        FOR delta IN engagement_deltas:
            local_engagement.add(delta.post_id, delta.increment)
        
        // Step 4: Trigger feed updates for affected users
        affected_users = get_users_with_new_content(missing_posts)
        FOR user IN affected_users:
            queue_feed_update(user, missing_posts)
        
        // Step 5: Update celebrity index
        new_celebrity_posts = filter_celebrity_posts(missing_posts)
        celebrity_index.merge(new_celebrity_posts)
        
        log_metric("partition_healed", {
            posts_synced: len(missing_posts),
            follow_changes: len(follow_changes),
            affected_users: len(affected_users)
        })
```

---

## Hot User Handling (Users Following 10K+ Accounts)

Power users who follow thousands of accounts create unique scaling challenges.

```
PROBLEM: User following 10,000 accounts

NAIVE FEED LOAD:
• Fetch 10,000 followees from social graph
• For each followee: Check for posts in celebrity index
• Merge 10,000 sources into one feed
• Result: Feed load takes 5-10 seconds (unacceptable)

STAFF SOLUTION: Tiered feed construction

TIER 1: CLOSE CONNECTIONS (top 100)
• Users the hot user interacts with most
• Precomputed and stored in hot user's feed storage
• Full fan-out from these sources

TIER 2: MEDIUM CONNECTIONS (next 1000)
• Users hot user follows but rarely interacts with
• Pull-based at read time, cached aggressively
• Merged in batches (100 at a time)

TIER 3: DISTANT CONNECTIONS (remaining 8900)
• Users hot user follows but never interacts with
• Sampled at read time (random 10% shown)
• User can explicitly request "show all from X"

RESULT:
• Feed load: 100 (precomputed) + 1000 (batched pull) + 890 (sampled)
• Latency: < 500ms for hot users (vs 10s naive)
• Trade-off: Some posts from distant connections may be missed
```

```
// Pseudocode: Hot user feed assembly

CLASS HotUserFeedBuilder:
    interaction_threshold_close = 5    // interactions in last 30 days
    interaction_threshold_medium = 1   // interactions in last 90 days
    sample_rate_distant = 0.1          // 10% of distant connections
    
    FUNCTION build_feed(user_id):
        followees = social_graph.get_followees(user_id)
        
        IF len(followees) < 500:
            // Normal user, use standard flow
            RETURN standard_feed_builder.build(user_id)
        
        // Hot user path
        interaction_scores = get_interaction_scores(user_id, followees)
        
        close = [f for f in followees if interaction_scores[f] >= 5]
        medium = [f for f in followees if 1 <= interaction_scores[f] < 5]
        distant = [f for f in followees if interaction_scores[f] < 1]
        
        // Tier 1: Precomputed (from feed storage)
        feed = feed_storage.get(user_id)  // Already contains close connection posts
        
        // Tier 2: Batched pull for medium connections
        medium_posts = batch_fetch_recent_posts(medium, limit_per_user=5)
        feed.merge(medium_posts)
        
        // Tier 3: Sampled pull for distant connections
        sampled_distant = random.sample(distant, int(len(distant) * 0.1))
        distant_posts = batch_fetch_recent_posts(sampled_distant, limit_per_user=2)
        feed.merge(distant_posts)
        
        // Rank and return
        RETURN ranker.rank(feed, user_id)
```

---

## AWS-Specific Cost Optimization

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AWS COST OPTIMIZATION FOR NEWS FEED                      │
│                                                                             │
│   COMPONENT          │  AWS SERVICE      │  OPTIMIZATION                    │
│   ───────────────────┼───────────────────┼───────────────────────────────── │
│   Feed Storage       │  ElastiCache      │  Reserved nodes (40% savings)    │
│   (In-memory)        │  Redis            │  Graviton (20% cheaper)          │
│                      │                   │  Hot/cold tier with S3           │
│   ───────────────────┼───────────────────┼───────────────────────────────── │
│   Content Cache      │  ElastiCache      │  Reserved capacity               │
│                      │  Memcached        │  Tiered: recent in RAM,          │
│                      │                   │  older in S3 + CloudFront        │
│   ───────────────────┼───────────────────┼───────────────────────────────── │
│   Post Store         │  DynamoDB         │  On-demand for variable load     │
│                      │                   │  Reserved for baseline           │
│                      │                   │  DAX for hot reads               │
│   ───────────────────┼───────────────────┼───────────────────────────────── │
│   Fan-out Workers    │  Lambda           │  ARM (Graviton2, 20% cheaper)    │
│                      │  + SQS            │  Batch processing (500 at once)  │
│                      │                   │  Reserved concurrency            │
│   ───────────────────┼───────────────────┼───────────────────────────────── │
│   Feed Service       │  ECS Fargate      │  Spot for non-critical           │
│                      │  or EKS           │  Graviton instances              │
│                      │                   │  Right-size based on metrics     │
│   ───────────────────┼───────────────────┼───────────────────────────────── │
│   CDN / Edge         │  CloudFront       │  Reserved capacity pricing       │
│                      │                   │  Origin shield (reduce origin)   │
│                      │                   │  Compress responses (40% less)   │
│   ───────────────────┼───────────────────┼───────────────────────────────── │
│   Cross-Region       │  Direct Connect   │  Reduces transfer costs          │
│   Replication        │  or VPC Peering   │  vs public internet              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

```
// Pseudocode: AWS cost estimation and optimization

CLASS AWSCostOptimizer:
    
    FUNCTION estimate_monthly_cost(scale):
        // Feed Storage (ElastiCache Redis)
        feed_storage_gb = scale.dau * 0.5 / 1000  // 0.5 KB per user average
        feed_storage_cost = feed_storage_gb * 0.125 * 24 * 30  // per GB-hour
        // With Reserved: 40% discount
        feed_storage_cost_optimized = feed_storage_cost * 0.6
        
        // Content Cache (ElastiCache + S3)
        hot_cache_gb = 15000  // 15 TB for 30 days
        cold_cache_gb = 50000  // Older content in S3
        hot_cache_cost = hot_cache_gb * 0.125 * 24 * 30 * 0.6  // Reserved
        cold_cache_cost = cold_cache_gb * 0.023  // S3 Standard-IA
        
        // Post Store (DynamoDB)
        writes_per_sec = scale.posts_per_day / 86400 * 150  // Fan-out writes
        reads_per_sec = scale.feed_loads_per_day / 86400 * 5  // Hydration reads
        dynamo_cost = (writes_per_sec * 1.25 + reads_per_sec * 0.25) * 24 * 30
        // With DAX: Reduce read cost by 90%
        dynamo_cost_optimized = (writes_per_sec * 1.25 + reads_per_sec * 0.025) * 24 * 30
        
        // Fan-out Workers (Lambda)
        fan_out_invocations = scale.posts_per_day * 150 / 500  // Batch of 500
        lambda_cost = fan_out_invocations * 30 * 0.0000002 + (fan_out_invocations * 256 * 100 / 1000 * 0.0000166667)
        // With Graviton: 20% cheaper
        lambda_cost_optimized = lambda_cost * 0.8
        
        // Network (Cross-region replication)
        cross_region_gb = scale.posts_per_day * 30 * 10 / 1000  // 10 KB per post, 30 days
        network_cost = cross_region_gb * 0.02  // Cross-region transfer
        // With Direct Connect: Reduce by 50%
        network_cost_optimized = network_cost * 0.5
        
        RETURN {
            baseline: sum([feed_storage_cost, hot_cache_cost, cold_cache_cost, 
                          dynamo_cost, lambda_cost, network_cost]),
            optimized: sum([feed_storage_cost_optimized, hot_cache_cost, cold_cache_cost,
                           dynamo_cost_optimized, lambda_cost_optimized, network_cost_optimized]),
            savings_percent: ...
        }
```

---

## Per-Request Cost Breakdown

```
COST PER FEED LOAD (at 200M DAU, 2B loads/day):

┌───────────────────────────────────────────────────────────────────────────────┐
│  OPERATION                    │  COST/REQUEST  │  MONTHLY (2B/day)            │
├───────────────────────────────┼────────────────┼──────────────────────────────┤
│  API Gateway / Load Balancer  │  $0.0000003    │  $18,000                     │
│  Feed Service compute         │  $0.0000020    │  $120,000                    │
│  Feed Storage read            │  $0.0000005    │  $30,000                     │
│  Content Cache read (avg 20)  │  $0.0000010    │  $60,000                     │
│  Ranking Service (if used)    │  $0.0000015    │  $90,000                     │
│  Network egress (1 KB avg)    │  $0.0000001    │  $6,000                      │
├───────────────────────────────┼────────────────┼──────────────────────────────┤
│  TOTAL PER FEED LOAD          │  $0.0000054    │  ~$324,000/month             │
└───────────────────────────────┴────────────────┴──────────────────────────────┘

COST PER POST CREATION (at 100M posts/day):

┌───────────────────────────────────────────────────────────────────────────────┐
│  OPERATION                    │  COST/REQUEST  │  MONTHLY (100M/day)          │
├───────────────────────────────┼────────────────┼──────────────────────────────┤
│  Post Store write             │  $0.000001     │  $3,000                      │
│  Content Cache write          │  $0.0000005    │  $1,500                      │
│  Queue publish                │  $0.0000004    │  $1,200                      │
│  Fan-out (avg 150 followers)  │  $0.000015     │  $45,000                     │
│  Feed Storage writes (150)    │  $0.0000075    │  $22,500                     │
├───────────────────────────────┼────────────────┼──────────────────────────────┤
│  TOTAL PER POST               │  $0.000024     │  ~$73,200/month              │
└───────────────────────────────┴────────────────┴──────────────────────────────┘

INSIGHT: Feed loads dominate cost (82% of total)
         Fan-out is the largest single operation cost per post
         
OPTIMIZATION PRIORITY:
1. Reduce feed loads (better caching, longer TTL)
2. Reduce fan-out (more pull-based for high followers)
3. Reduce content hydration (better cache hit rate)

COST-SLO TRADE-OFF TABLE (L6 Decision Framework):
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│  SLO RELAXATION          │  COST SAVINGS      │  USER IMPACT         │  WHEN TO ACCEPT      │
├──────────────────────────┼────────────────────┼──────────────────────┼──────────────────────┤
│  P99 500ms → 800ms       │  ~15% (less cache) │  Noticeable to few   │  Cost crisis, canary │
│  Post visibility 5m→15m  │  ~25% (less push)   │  Inactive users only │  Scale event         │
│  No ML ranking           │  ~20% (no model)   │  Chronological only  │  MVP, cost cut       │
│  Single region           │  ~30% (no replica) │  +200ms for remote   │  Early stage only    │
│  Hot tier 7d → 3d        │  ~10% (mem)        │  Cold users slower   │  Capacity pressure   │
└──────────────────────────┴────────────────────┴──────────────────────┴──────────────────────┘

STAFF INSIGHT: "Every SLO has a cost. The Staff question is: which relaxation
hurts the fewest users for the most savings? Document the trade-off explicitly."
```

---

## Zero-Downtime Fan-out Strategy Migration

Migrating from pure push to hybrid push-pull requires careful orchestration.

```
// Pseudocode: Fan-out strategy migration

CLASS FanoutStrategyMigration:
    
    FUNCTION migrate_to_hybrid():
        // Phase 1: Shadow Mode (1 week)
        // Run new strategy in parallel, compare results
        
        FOR post IN new_posts:
            // Old strategy (pure push)
            old_result = pure_push_fanout(post)
            
            // New strategy (hybrid)
            new_result = hybrid_fanout(post)
            
            // Log differences for analysis
            log_comparison(post.id, old_result, new_result)
            
            // Use old result for actual writes
            RETURN old_result
        
        // Analyze: Are feeds equivalent? Any missing posts?
        // If discrepancies > 0.1%, investigate and fix
        
        // Phase 2: Canary (3 days)
        // 5% of users get hybrid strategy
        
        FOR post IN new_posts:
            IF hash(post.author_id) % 100 < 5:
                RETURN hybrid_fanout(post)
            ELSE:
                RETURN pure_push_fanout(post)
        
        // Monitor: Feed load latency, post visibility latency, user complaints
        
        // Phase 3: Gradual Rollout (2 weeks)
        // 5% → 25% → 50% → 75% → 100%
        
        // Phase 4: Cleanup
        // Remove pure push code path
        // Archive migration logs
        
    FUNCTION rollback_hybrid():
        // If issues detected, immediate rollback
        // Set canary percentage to 0
        // Users on hybrid continue to work (celebrity posts still visible via pull)
        // New posts go back to pure push
        
        // No data loss possible:
        // - Posts always in Post Store
        // - Celebrity Index still populated
        // - Only fan-out strategy changes
```

---

## On-Call Runbook for News Feed

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NEWS FEED ON-CALL RUNBOOK                                │
│                                                                             │
│   ALERT: Feed Load Latency High (P99 > 500ms)                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. CHECK: Which component is slow?                                 │   │
│   │     • Feed Storage: Check shard health, replica lag                 │   │
│   │     • Content Cache: Check hit rate, eviction rate                  │   │
│   │     • Ranking Service: Check ML model latency                       │   │
│   │     • Post Store: Check database latency                            │   │
│   │                                                                     │   │
│   │  2. IMMEDIATE MITIGATION:                                           │   │
│   │     • If Ranking slow: Enable chronological fallback                │   │
│   │     • If Content Cache miss: Enable cached-only mode                │   │
│   │     • If Feed Storage slow: Enable load shedding for that shard     │   │
│   │                                                                     │   │
│   │  3. ESCALATE if:                                                    │   │
│   │     • Multiple components affected                                  │   │
│   │     • Mitigation doesn't help within 5 minutes                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ALERT: Fan-out Queue Depth Growing                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. CHECK: Queue depth growth rate                                  │   │
│   │     • Slow growth (< 1000/sec): Monitor, may self-heal              │   │
│   │     • Fast growth (> 10000/sec): Immediate action needed            │   │
│   │                                                                     │   │
│   │  2. IDENTIFY ROOT CAUSE:                                            │   │
│   │     • Celebrity post? (Check Celebrity Index writes)                │   │
│   │     • Worker failure? (Check worker health)                         │   │
│   │     • Feed Storage slow? (Check write latency)                      │   │
│   │                                                                     │   │
│   │  3. IMMEDIATE MITIGATION:                                           │   │
│   │     • Scale up workers (2x, 4x if needed)                           │   │
│   │     • Enable priority mode (active users first)                     │   │
│   │     • Defer inactive user fan-out (acceptable staleness)            │   │
│   │                                                                     │   │
│   │  4. POST-RECOVERY:                                                  │   │
│   │     • Let queue drain naturally                                     │   │
│   │     • Scale workers back after queue < 1000                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ALERT: Cache Hit Rate Low (< 95%)                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. CHECK: What changed?                                            │   │
│   │     • Cache restart? (Memory spike, then low)                       │   │
│   │     • Traffic pattern change? (New content type)                    │   │
│   │     • Cache size? (OOM, eviction spike)                             │   │
│   │                                                                     │   │
│   │  2. IMMEDIATE MITIGATION:                                           │   │
│   │     • Enable Post Store read replicas                               │   │
│   │     • Enable request coalescing for cache misses                    │   │
│   │     • Increase cache capacity if possible                           │   │
│   │                                                                     │   │
│   │  3. WAIT: Cache will warm naturally over 10-30 minutes              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ESCALATION MATRIX:                                                        │
│   • P1 (Complete outage): Page team lead + oncall manager                   │
│   • P2 (Degraded, >10% users): Page secondary oncall                        │
│   • P3 (Degraded, <10% users): Slack alert, continue monitoring             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Monitoring Dashboard Design

```
FEED SYSTEM MONITORING: KEY METRICS

┌─────────────────────────────────────────────────────────────────────────────┐
│  SECTION 1: USER EXPERIENCE (TOP ROW, BIGGEST GRAPHS)                       │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  Feed Load Latency P50/P95/P99    │  Feed Error Rate (%)                ││
│  │  Target: <200ms P50, <500ms P99   │  Target: <0.1%                      ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  SECTION 2: THROUGHPUT (SECOND ROW)                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  Feed Loads QPS     │  Posts Created QPS  │  Fan-out Writes QPS         ││
│  │  Current vs Avg     │  Current vs Avg     │  Current vs Avg             ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  SECTION 3: DEPENDENCIES (THIRD ROW)                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  Feed Storage       │  Content Cache      │  Post Store                 ││
│  │  • Read latency     │  • Hit rate (%)     │  • Read latency             ││
│  │  • Shard health     │  • Memory usage     │  • Write latency            ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  SECTION 4: QUEUES AND WORKERS (FOURTH ROW)                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  Fan-out Queue      │  Worker Health      │  Ranking Service            ││
│  │  • Depth            │  • Active count     │  • Latency P99              ││
│  │  • Age of oldest    │  • Error rate       │  • Degradation level        ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  SECTION 5: BUSINESS METRICS (BOTTOM ROW)                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  Feed Freshness     │  Post Visibility    │  Celebrity Index            ││
│  │  (avg age of top    │  (time from post    │  (posts per celebrity,      ││
│  │   post in feed)     │   to in feeds)      │   query latency)            ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  ALERT THRESHOLDS (displayed as colored indicators):                        │
│  🟢 Green: Within SLO    🟡 Yellow: Warning    🔴 Red: Breaching SLO         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

SLO-TO-ALERT MAPPING (Observability Completeness):
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│  SLO                           │  ALERT TRIGGER        │  ACTION                            │
├────────────────────────────────┼───────────────────────┼──────────────────────────────────┤
│  Feed load P99 < 500ms         │  P99 > 500ms (1 min)  │  Runbook: Latency High             │
│  Feed availability > 99.9%    │  Error rate > 0.1%    │  Runbook: Error Rate High          │
│  Post visibility P95 < 5 min   │  P95 > 10 min         │  Check fan-out queue, worker health │
│  Content freshness <1% stale   │  >1% feeds >5 min    │  Check replication lag, fan-out    │
│  Cache hit rate > 95%         │  Hit rate < 90%      │  Runbook: Cache Hit Low            │
└────────────────────────────────┴───────────────────────┴──────────────────────────────────┘
```

---

## Google L6 Interview Follow-Ups This Design Must Survive

### Follow-Up 1: "A celebrity with 100M followers posts. Walk me through exactly what happens."

**Design Answer:**
- Post written to Post Store (10ms)
- Post ID added to Celebrity Index (5ms, async)
- NO fan-out to 100M followers (this is the key insight)
- When followers load feed: Fetch precomputed feed + merge Celebrity Index posts
- Celebrity post appears in all feeds within seconds (read-merge, not write-fan-out)
- Total cost: O(1) writes instead of O(100M) writes

### Follow-Up 2: "How do you ensure a user sees their own post immediately after publishing?"

**Design Answer:**
- Write-through to author's own feed (synchronous, before response)
- Author's feed stored in same shard as post creation
- Alternatively: Optimistic UI (client adds post locally before server confirms)
- Fan-out to followers is async, but author doesn't wait for it

### Follow-Up 3: "What if Feed Storage loses data for a shard?"

**Design Answer:**
- Feeds are reconstructable from Social Graph + Post Store + Celebrity Index
- Rebuild process: Get followees → Fetch recent posts → Merge → Store
- Rebuild is expensive but possible (unlike post content loss)
- During rebuild: Serve degraded feed from Post Store directly
- This is why we store post IDs, not content—content loss is unrecoverable

### Follow-Up 4: "How do you handle users who follow 50,000 accounts?"

**Design Answer:**
- Tiered feed assembly (explained in Hot User section)
- Close connections (top 100 by interaction): Full fan-out
- Medium connections (next 1000): Batched pull at read time
- Distant connections (remaining): Sampled (10%)
- Latency still within SLO because most reads hit cached tiers
- Trade-off: Some distant content may be missed

### Follow-Up 5: "A user claims they're missing posts from someone they follow. How do you debug?"

**Design Answer:**
1. Check: Is follow relationship active? (Social Graph query)
2. Check: Did post fan-out complete? (Fan-out worker logs)
3. Check: Is post in user's Feed Storage? (Direct query)
4. Check: Is post marked as deleted/hidden? (Post Store status)
5. Check: Was post filtered by ranking/abuse? (Ranking logs)
6. Common causes: Fan-out lag, abuse filter, ranking deprioritization, follow not synced

---

## Additional Brainstorming Questions (L6 Depth)

```
QUESTION 36: How would you handle a flash mob event where 10M users 
             simultaneously post about the same topic?

Consider:
• Fan-out queue explosion
• Content Cache thrashing (all new content)
• Ranking service overload
• Trending/discovery implications

---

QUESTION 37: Design a "Close Friends" feature where posts are 
             visible only to a selected subset of followers.

Consider:
• Fan-out becomes access-controlled
• Feed Storage needs visibility filtering
• Privacy implications if leaked
• Performance impact of additional checks

---

QUESTION 38: How would you implement "Undo Post" that works 
             even after fan-out has completed?

Consider:
• Feed Storage already has post IDs
• Deletion must propagate to all feeds
• Caching invalidation at scale
• User sees "This post is no longer available"

---

QUESTION 39: Design feed for a user who follows 1M accounts 
             (extreme power user or aggregator account).

Consider:
• Current hot user solution may not scale
• May need dedicated infrastructure
• May need to treat as special case
• May need to limit follow count

---

QUESTION 40: How do you handle timezone-based content 
             (e.g., "Good Morning" posts)?

Consider:
• Author posts at their morning
• Followers in different timezones
• Should timezone affect ranking?
• "Stale" morning post at night
```

---

## Additional Exercises (L6 Depth)

```
EXERCISE 9: Design for 0.1% of current cost

Constraints:
• Budget: $730/month (was $730K)
• Must serve 1000 users with core functionality

Approach:
• Single server, SQLite database
• Pure fan-out-on-read
• No caching infrastructure
• No ranking
• No multi-region

What this teaches: Minimum viable architecture, scaling from scratch

---

EXERCISE 10: Design for real-time collaborative feed

Constraints:
• Multiple users see same feed
• All see updates simultaneously
• Cursor positions shared
• Like a "watch party" for a news feed

Approach:
• WebSocket connections
• Shared feed state
• Operational transforms for ordering
• This is closer to collaborative document than traditional feed

---

EXERCISE 11: Design feed with complete audit trail

Constraints:
• Every feed view logged
• Every ranking decision explainable
• Regulatory requirement (financial news)

Approach:
• Feed snapshots stored
• Ranking explanations stored
• Significant storage cost increase
• Affects retention policies

---

EXERCISE 12: Migrate from monolith to microservices

Constraints:
• Existing monolith serves 50M users
• Zero downtime during migration
• Team of 5 engineers over 6 months

Approach:
• Strangler pattern
• Extract Feed Storage first (read path)
• Extract Post Store second (write path)
• Extract Ranking last (most coupled)
• Feature flags throughout
```

---

## Component-Specific Brainstorming Questions

```
FEED STORAGE:

QUESTION 41: What happens when a Feed Storage shard experiences 
             memory pressure and must evict entries?

Consider:
• Which users' feeds get evicted first?
• How do you prevent evicting active users?
• What's the cost of rebuilding evicted feeds?
• How do you handle "cold start" when evicted user returns?

Staff answer: LRU by last access time, not by user ID. Active users 
never evicted. Cold users rebuilt on-demand (acceptable latency hit 
for users who haven't opened app in weeks).

---

QUESTION 42: Design a Feed Storage migration from Redis to 
             a custom in-memory store.

Consider:
• Zero downtime requirement
• Data consistency during migration
• Rollback strategy
• Performance comparison validation

---

CONTENT CACHE:

QUESTION 43: Content Cache achieves 99% hit rate. What causes 
             the 1% misses and how do you reduce them?

Consider:
• New posts (cold start)
• Edited posts (invalidation)
• Long-tail content (rarely accessed old posts)
• Cache restarts

Staff answer: 1% misses dominated by new posts (<1 minute old) and 
long-tail historical content. Reduce by: write-through on creation, 
extended TTL for popular content, accept higher miss rate for 
content older than 7 days.

---

QUESTION 44: How do you handle a cache poisoning attack where 
             an attacker stores malicious content under valid post IDs?

Consider:
• How could this happen?
• Detection mechanisms
• Invalidation strategy
• Prevention at write time

---

FAN-OUT WORKERS:

QUESTION 45: Fan-out queue has 10M messages backed up. 
             Which messages do you process first?

Consider:
• Active users vs inactive users
• Recent posts vs older posts
• Celebrity posts vs normal posts
• First-in-first-out vs priority queue

Staff answer: Priority queue with: (1) Posts to active users, 
(2) Celebrity posts (already in Celebrity Index), (3) Posts to 
inactive users. Never FIFO—user importance matters more than 
message age.

---

QUESTION 46: A fan-out worker consistently fails on specific 
             users' feeds. How do you handle poison messages?

Consider:
• Dead letter queue
• Retry limits
• Manual investigation queue
• Impact on affected users

---

RANKING SERVICE:

QUESTION 47: Ranking model accuracy degrades over time 
             (concept drift). How do you detect and handle this?

Consider:
• What metrics indicate drift?
• Automatic vs manual retraining
• A/B testing new models
• Rollback strategy

Staff answer: Monitor CTR prediction vs actual CTR. If gap exceeds 
threshold, trigger model retraining pipeline. Always have fallback 
to previous model. A/B test new model on 5% before full rollout.

---

QUESTION 48: Users complain "I'm not seeing posts from my 
             best friend." How do you debug ranking issues?

Consider:
• Friend's posts in feed but ranked low
• Friend's posts not in feed at all
• Ranking explanation/transparency
• Balancing engagement vs user preferences

---

SOCIAL GRAPH:

QUESTION 49: A user follows 10,000 accounts in 1 minute. 
             Is this abuse or legitimate behavior?

Consider:
• Import from another platform
• Bot/automated behavior
• Rate limiting implications
• Impact on system

Staff answer: Could be either. Check: account age, follow pattern 
(sequential IDs = bot), source (API vs UI). Rate limit to 100/hour 
with burst allowance for imports. Queue excess for later processing.

---

QUESTION 50: Social graph becomes inconsistent between regions 
             after a long partition. How do you reconcile?

Consider:
• Conflicting follow/unfollow operations
• Which version wins?
• User notification of changes
• Prevention strategies

---

ABUSE DETECTION:

QUESTION 51: How do you distinguish between viral organic content 
             and coordinated inauthentic behavior (fake virality)?

Consider:
• Similar engagement patterns
• Account network analysis
• Timing analysis
• False positive cost

---

QUESTION 52: An abuse detection rule has 5% false positive rate. 
             Is this acceptable?

Consider:
• 5% of 100M posts/day = 5M legitimate posts blocked
• User experience impact
• Appeal process load
• Balance with true positive rate

Staff answer: Depends on action severity. For hiding posts: 5% too 
high (use 0.1% threshold). For flagging for review: 5% acceptable. 
For permanent ban: require human review, no automated action.

---

MULTI-REGION:

QUESTION 53: EU users complain their feeds are 30 minutes stale 
             after US-EU network restored. Why?

Consider:
• Replication backlog during partition
• Priority of catch-up traffic
• Impact on real-time traffic
• User-facing mitigation

Staff answer: Backlog flooding forward path. Solution: separate 
queues for catch-up vs real-time, rate limit catch-up to not 
impact real-time. Accept temporary staleness for non-active users, 
prioritize catch-up for users currently online.

---

QUESTION 54: Regulations require EU user data to never leave EU. 
             How does this affect feed design?

Consider:
• EU users following US users
• Content replication
• Metadata vs content separation
• Compliance verification

---

MONITORING & OPERATIONS:

QUESTION 55: Define the top 5 SLOs for the news feed system.

Consider:
• User-facing vs internal metrics
• Latency vs availability vs correctness
• How to measure each
• Error budget calculation

Staff answer:
1. Feed load latency P99 < 500ms (99.9% of requests)
2. Feed availability > 99.9%
3. Post visibility latency P95 < 5 minutes
4. Content freshness: <1% feeds older than 5 minutes
5. Error rate < 0.1%

---

QUESTION 56: You need to reduce on-call burden by 50%. 
             What changes do you prioritize?

Consider:
• Most frequent alert types
• Automation opportunities
• Self-healing mechanisms
• Alert fatigue reduction
```

---

## Component-Specific Exercises

```
EXERCISE 13: Feed Storage Hot/Cold Tiering Implementation

Scenario:
• 200M users, 50% active in last 7 days
• Memory budget: 500 GB (not enough for all)
• SSD tier for cold users

Design:
• Access pattern tracking
• Promotion/demotion criteria
• Rebuild latency for cold users
• Memory management

Deliverables:
• Pseudocode for tiering logic
• Latency SLOs per tier
• Cost analysis

---

EXERCISE 14: Content Cache Stampede Prevention

Scenario:
• Celebrity with 50M followers posts
• Post TTL expires after 24 hours
• 50M users refresh feeds simultaneously
• All requests miss cache for that post

Design:
• Request coalescing implementation
• Staggered TTL strategy
• Background refresh mechanism
• Fallback during stampede

Deliverables:
• Pseudocode for stampede prevention
• Latency impact analysis
• Comparison: with vs without mitigation

---

EXERCISE 15: Fan-out Worker Priority Queue Design

Scenario:
• 100M posts/day
• 15B fan-out writes/day
• Celebrity post: 10M fan-outs
• Normal post: 150 fan-outs

Design:
• Priority levels and criteria
• Queue partitioning strategy
• Worker allocation per priority
• Starvation prevention

Deliverables:
• Priority queue architecture diagram
• Pseudocode for priority assignment
• Latency SLOs per priority level

---

EXERCISE 16: Ranking Service A/B Testing Framework

Scenario:
• Current model: 10% engagement improvement
• New model: Claims 15% improvement
• Need to validate safely

Design:
• Traffic splitting mechanism
• Metrics collection
• Statistical significance calculation
• Rollback triggers

Deliverables:
• A/B test design document
• Pseudocode for traffic routing
• Success/failure criteria

---

EXERCISE 17: Abuse Detection False Positive Reduction

Scenario:
• Current false positive rate: 2%
• 2M legitimate posts incorrectly flagged daily
• User complaints increasing

Design:
• Multi-stage detection (warn → review → block)
• Appeal process integration
• Model improvement feedback loop
• False positive monitoring

Deliverables:
• Detection pipeline redesign
• Pseudocode for staged enforcement
• Target false positive rate and timeline

---

EXERCISE 18: Multi-Region Failover Drill

Scenario:
• 3 regions: US-EAST, EU-WEST, AP-EAST
• Need to simulate US-EAST complete outage
• No data loss, minimal user impact

Design:
• Traffic rerouting mechanism
• Data consistency during failover
• User experience during transition
• Recovery procedure

Deliverables:
• Runbook for failover drill
• Expected user impact per phase
• Success criteria

---

EXERCISE 19: Feed System Cost Reduction by 30%

Scenario:
• Current cost: $730K/month
• Target: $511K/month
• Cannot reduce DAU or functionality

Design:
• Cost breakdown by component
• Optimization opportunities
• Trade-offs accepted
• Implementation priority

Deliverables:
• Cost reduction plan with specific changes
• Risk assessment for each change
• Timeline for implementation

---

EXERCISE 20: Zero-Downtime Database Migration

Scenario:
• Current: Post Store on MySQL
• Target: Post Store on distributed database
• 10B posts, 500GB writes/day
• Cannot lose any data

Design:
• Dual-write strategy
• Read migration phases
• Verification mechanism
• Rollback plan

Deliverables:
• Migration architecture diagram
• Pseudocode for dual-write
• Verification queries
• Rollback criteria
```

---

## Trade-off Debates (Additional)

```
DEBATE 4: Client-side Feed Assembly vs Server-side

POSITION A: Server assembles complete feed
• Single request from client
• Server does all work
• Consistent experience

POSITION B: Client assembles from multiple APIs
• Feed structure API, content API, ranking API
• Client has more control
• Can cache components independently

Staff resolution:
Server-side for mobile (bandwidth matters).
Hybrid for web (can parallelize requests).
Never full client-side (too many round trips on mobile).

---

DEBATE 5: Per-Post Engagement vs Aggregated

POSITION A: Real-time per-post engagement counts
• Every like updates counter
• Users see current count
• High write volume

POSITION B: Aggregated engagement (updated every 5 minutes)
• Batch counter updates
• Users see slightly stale counts
• Much lower write volume

Staff resolution:
Aggregated for display (users don't notice 5-minute lag).
Real-time for own actions (I liked, count should increment).
Hybrid: Local optimistic update + eventual server sync.

---

DEBATE 6: Separate Celebrity Service vs Integrated

POSITION A: Dedicated Celebrity Service
• Separate infrastructure for celebrities
• Specialized handling
• Different SLOs

POSITION B: Integrated with special handling
• Same infrastructure, different code paths
• Simpler operations
• Risk of celebrity impact on regular users

Staff resolution:
Integrated with isolation. Celebrity Index is separate data 
structure, but runs in same service. Avoids operational 
complexity of separate service while limiting blast radius.

---

DEBATE 7: Feed Correctness vs Speed

POSITION A: Correct feed always (strong consistency)
• Never show stale data
• Never miss posts
• Higher latency acceptable

POSITION B: Fast feed always (eventual consistency)
• Sub-100ms always
• May miss recent posts
• May show slightly stale data

Staff resolution:
Speed for most cases (users don't notice small inconsistencies).
Correctness for "own posts" (author must see their post immediately).
Never sacrifice speed for correctness that users can't perceive.
```

---

## Failure Injection Exercises (Additional)

```
FAILURE INJECTION 4: Ranking Service Latency Spike

Setup:
• Inject 500ms latency into ranking service
• Maintain normal traffic

Expected behavior:
• Degradation to Level 2 or 3
• Feed loads continue with cached/chronological ranking
• Alert fires within 1 minute

Validate:
• Feed latency SLO maintained
• Degradation properly logged
• Recovery when latency returns to normal

---

FAILURE INJECTION 5: Social Graph Corruption

Setup:
• Corrupt 1% of follow edges (wrong direction)
• Don't notify users

Expected behavior:
• Affected users see wrong posts in feed
• Detection via user complaints or anomaly detection
• Rollback mechanism exists

Validate:
• Corruption detected within X minutes
• Rollback completes without data loss
• Affected users' feeds correct after rollback

---

FAILURE INJECTION 6: Content Cache Full Eviction

Setup:
• Flush entire Content Cache
• Maintain normal traffic

Expected behavior:
• Cache hit rate drops to 0%
• Post Store handles increased load
• Cache warms over 10-30 minutes

Validate:
• No user-facing errors during warming
• Post Store doesn't exceed capacity
• Full recovery within target time

---

FAILURE INJECTION 7: Cross-Region Replication Delay

Setup:
• Inject 5-minute delay in US-EAST to EU-WEST replication
• Users in EU following US creators

Expected behavior:
• EU users see 5-minute stale US content
• No errors, just staleness
• Monitoring detects replication lag

Validate:
• Lag metric accurately reflects delay
• Alert fires at appropriate threshold
• Recovery when delay removed
```

---

---

# Quick Reference

## Key Numbers

| Metric | Value |
|--------|-------|
| DAU | 200M |
| Feed loads/day | 2B |
| QPS (feed reads) | 23K |
| Posts/day | 100M |
| Avg followers | 150 |
| Fan-out writes/day | 15B |
| Feed storage | 500 GB - 1 TB |
| Content cache | 10-15 TB |

## Algorithm Selection

| Scenario | Strategy |
|----------|----------|
| Small creator (< 10K followers) | Full push |
| Medium creator (10K-1M) | Async push |
| Celebrity (> 1M) | Pull on read |
| Inactive user feed | Disk, warm on access |
| Active user feed | Memory resident |

## Failure Responses

| Failure | Response |
|---------|----------|
| Feed Storage shard down | Serve degraded feed from cache/Post Store |
| Content Cache miss spike | Request coalescing, fetch once |
| Fan-out queue backup | Prioritize active users, defer inactive |
| Ranking service down | Serve chronological (skip ranking) |
| Post Store down | Serve cached content only, show "limited" |

---

# Conclusion

The news feed is a masterclass in distributed systems trade-offs. What appears simple—show users posts from people they follow—requires navigating tensions between push and pull, freshness and cost, simplicity and personalization.

The key insights for Staff Engineers:

**Hybrid strategies beat pure approaches.** Pure push fails for celebrities. Pure pull fails for latency. Hybrid push-pull with intelligent thresholds handles both cases elegantly.

**Hot/cold tiering is essential.** Half of users are inactive. Treating all users equally wastes resources. Tier by activity and right-size infrastructure for actual usage patterns.

**Ranking is optional.** Most users don't benefit from ML ranking. Apply expensive operations only where they provide measurable value.

**Design for the celebrity problem from day one.** Every social platform eventually has celebrities. Baking in pull-on-read for high-follower accounts avoids painful rewrites later.

**Accept eventual consistency.** Feeds don't need real-time precision. Users don't compare feeds. 100ms-5 minute staleness is invisible and saves enormous infrastructure cost.

The news feed teaches that Staff Engineering isn't about building the most sophisticated system—it's about building the right system for the context, with awareness of how that context will evolve.

---