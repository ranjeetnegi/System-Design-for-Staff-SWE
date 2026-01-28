# Chapter 11: End-to-End System Design Using the 5-Phase Framework

### A Staff-Level Walkthrough: The News Feed System

---

# Quick Visual: The 5-Phase Interview Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     THE 5-PHASE SYSTEM DESIGN FLOW                          │
│                                                                             │
│   ┌──────────────┐                                                          │
│   │   PROMPT     │  "Design a news feed system"                             │
│   └──────┬───────┘                                                          │
│          ▼                                                                  │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                      │
│   │ PHASE 1:     │  │ PHASE 2:     │  │ PHASE 3:     │                      │
│   │ Users &      │→ │ Functional   │→ │ Scale        │                      │
│   │ Use Cases    │  │ Requirements │  │              │                      │
│   │ (5-7 min)    │  │ (5-7 min)    │  │ (5 min)      │                      │
│   └──────────────┘  └──────────────┘  └──────────────┘                      │
│          │                                  │                               │
│          ▼                                  ▼                               │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                      │
│   │ PHASE 4:     │  │ PHASE 5:     │  │ ARCHITECTURE │                      │
│   │ NFRs &       │→ │ Assumptions  │→ │ DESIGN       │                      │
│   │ Trade-offs   │  │ & Constraints│  │              │                      │
│   │ (5 min)      │  │ (3 min)      │  │ (15-20 min)  │                      │
│   └──────────────┘  └──────────────┘  └──────────────┘                      │
│                                                                             │
│   KEY: Each phase INFORMS the next. Architecture EMERGES from requirements. │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Interview Timeline: 45-Minute Breakdown

| Time | Phase | What You Do | What Interviewer Sees |
|------|-------|-------------|----------------------|
| **0-2 min** | Opening | Acknowledge, state approach | Structured, confident |
| **2-9 min** | Phase 1: Users | Identify users, use cases, scope | Thorough understanding |
| **9-16 min** | Phase 2: Functional | Define core/supporting/edge | Precise requirements |
| **16-21 min** | Phase 3: Scale | Derive numbers, identify bottlenecks | Quantitative thinking |
| **21-26 min** | Phase 4: NFRs | Quantify quality, state trade-offs | Trade-off awareness |
| **26-29 min** | Phase 5: Assumptions | State explicitly, invite correction | Professional maturity |
| **29-42 min** | Architecture | Design, explain, trace back | Technical depth |
| **42-45 min** | Wrap-up | Summarize, discuss evolution | Big-picture thinking |

---

# Introduction

This section demonstrates the complete application of the 5-Phase Framework to a real system design problem. We'll walk through the design of a **News Feed System** as a Staff Engineer would approach it in an interview—methodically, with explicit reasoning at each step.

This is not a reference architecture to memorize. It's a demonstration of *how to think* through a complex system design. Pay attention to:

- How each phase builds on the previous
- How decisions are made explicit and justified
- Where an L5 candidate might stop, and how L6 goes further
- How trade-offs are surfaced and resolved
- The interview narration style that communicates your thinking

Let's begin.

---

# The Prompt

**Interviewer**: "Design a news feed system for a social media platform."

*At this point, I would take a breath, acknowledge the prompt, and signal that I'm going to approach this systematically.*

**My response**: "A news feed system—that's a rich problem with interesting challenges. Before I start designing, I'd like to work through this systematically. I'll spend a few minutes understanding the users and use cases, then define requirements, establish scale, clarify non-functional requirements, and state my assumptions. That will give us a solid foundation for the architecture discussion. Does that approach work for you?"

*This signals to the interviewer that I have a structured approach and I'm taking ownership of the conversation.*

---

# Phase 1: Users & Use Cases

## Identifying Users

**My narration**: "Let me start by understanding who the users of this system are. I see several types:"

### Human Users

1. **Feed Consumers** (Primary)
   - End users who open the app and view their personalized feed
   - They scroll, interact, and expect immediate content
   - This is the primary use case—the feed exists for them

2. **Content Creators** (Secondary)
   - Users who create posts that appear in others' feeds
   - They care about reach—who sees their content
   - Overlap with consumers (same people, different mode)

3. **Advertisers** (Secondary)
   - Businesses whose ads appear in feeds
   - They care about targeting, placement, and performance

### System Users

4. **Content Service**
   - Internal service that stores and serves posts
   - Provides content when we build the feed

5. **Social Graph Service**
   - Provides follow relationships
   - Tells us whose content should appear in whose feed

6. **Ranking/ML Service**
   - Provides relevance scores for content
   - Helps personalize the feed

7. **Analytics Service**
   - Consumes feed events (loads, scrolls, interactions)
   - Used for metrics and ML training

### Operational Users

8. **SRE/Operations Team**
   - Monitors feed health
   - Needs visibility into latency, errors, queue depths

*At this point, I would pause and check alignment.*

**My narration**: "I've identified consumers as the primary user—feed generation and loading is optimized for them. Content creators and advertisers are secondary; their needs inform the design but don't drive core decisions. The system users tell me what services I'm integrating with. Does this user landscape match what you had in mind?"

---

## Identifying Use Cases

**My narration**: "Now let me map out the use cases, starting with core use cases and then edge cases."

### Core Use Cases

| Use Case | User | Description | Priority |
|----------|------|-------------|----------|
| Load home feed | Consumer | User opens app, sees personalized content | P0 (Critical) |
| Scroll for more | Consumer | User scrolls, more content loads seamlessly | P0 |
| Refresh feed | Consumer | User pulls to refresh for new content | P0 |
| Publish content | Creator | User posts, content appears in followers' feeds | P0 |
| Interact with content | Consumer | Like, comment, share, hide | P1 |

### Supporting Use Cases

| Use Case | User | Description | Priority |
|----------|------|-------------|----------|
| Control feed preferences | Consumer | Mute accounts, snooze, "see less" | P1 |
| View content performance | Creator | See reach and engagement metrics | P2 |
| Inject ads | Ad service | Insert ads at appropriate positions | P1 |
| Monitor feed health | Ops | View latency, error rates, throughput | P1 |

### Edge Cases

| Edge Case | Handling Approach |
|-----------|-------------------|
| New user (no follows) | Show trending/recommended content |
| User follows 50,000 accounts | Limit sources considered; prioritize |
| Celebrity posts (10M+ followers) | Pull model for fan-out; don't push |
| User inactive for 1 year | Fall back to trending + re-engagement signals |
| Post deleted after loaded in feed | Show placeholder or filter on scroll |
| User in poor connectivity | Aggressive caching, smaller payloads |

---

## Scope Control

*This is where Staff engineers distinguish themselves. I'm going to explicitly state what's in and out of scope.*

**My narration**: "Let me be explicit about scope. For this design session, I'm focusing on:"

### In Scope

- Home feed generation and serving for logged-in users
- Basic ranking (combining recency and engagement signals)
- Pagination (infinite scroll)
- Content from followed accounts
- Basic personalization

### Out of Scope (Explicitly)

- **Content storage and creation** — separate content service; I'll assume it exists
- **Social graph management** — separate service; I'll integrate with it
- **Search and discovery feeds** — different system, different ranking
- **Sophisticated ML ranking** — I'll treat ranking as a service that returns scores
- **Ad selection and targeting** — separate system; I'll leave slots for ad injection
- **Notifications** — separate system
- **Stories/ephemeral content** — separate feature
- **Video feed (like TikTok)** — different interaction model

**My narration**: "I'm scoping to the core feed experience: load, scroll, refresh. The most interesting challenges are feed generation at scale and the freshness/latency trade-off. Is this scope appropriate, or should I adjust?"

---

## Where L5 Stops vs. L6 Goes Further

*An L5 candidate might identify "users viewing feed" and "users posting content" but miss:*

- System users (what services exist? what do we integrate with?)
- Operational users (how is this thing monitored?)
- The celebrity edge case (which drives major architectural decisions)
- Explicit scope control (what we're NOT designing)

*A Staff engineer explicitly surfaces all of these, demonstrating awareness of the full ecosystem.*

---

# Phase 2: Functional Requirements

## Defining Core Functionality

**My narration**: "Based on the use cases, let me define the functional requirements. I'll organize these by flow type: read, write, and control."

### Read Flows

**F1: Generate Feed**
- Given a user ID, generate a personalized list of content items
- Content comes from followed accounts
- Content is ranked by relevance and recency
- Support pagination (cursor-based, not offset-based)

**F2: Load Feed Page**
- Return a page of feed items (e.g., 20 items per page)
- Include necessary metadata for rendering (author, content, interaction counts)
- Return next-page cursor for continued scrolling

**F3: Detect New Content**
- Allow client to check if new content is available
- Support "pull to refresh" with count of new items

### Write Flows

**F4: Publish Content**
- When a user publishes, make content available to their followers' feeds
- Content should appear in follower feeds within 1 minute (freshness target)

**F5: Record Interaction**
- When a user likes/comments/shares, record for ranking signals
- Update interaction counts (eventually consistent is fine)

**F6: Hide/Mute**
- When a user hides content or mutes an account, reflect in future feeds
- Should take effect within the current session

### Control Flows

**F7: Manage Feed Preferences**
- Operators can adjust global ranking parameters
- Support A/B testing of ranking algorithms

**F8: Manage Celebrity Thresholds**
- Configure thresholds for push vs. pull model
- Adjust based on system performance

---

## Avoiding Over-Specification

**My narration**: "Notice I'm specifying *what* happens, not *how*. For example, 'content should appear in follower feeds within 1 minute'—I'm not specifying whether that's push or pull, synchronous or async. That's an architecture decision I'll make based on scale and NFRs."

---

## Handling Edge Cases Explicitly

**My narration**: "Let me explicitly address the edge cases I identified earlier."

| Edge Case | Functional Handling |
|-----------|---------------------|
| New user (cold start) | F1 falls back to trending content + onboarding recommendations |
| Massive followee list | F1 limits sources to top N by engagement history |
| Celebrity posts | F4 uses pull model—content stored once, pulled into feeds at read time |
| Deleted content | F2 filters deleted content; may show placeholder |
| Stale user | F1 uses trending as primary signal, reduces personalization weight |

---

## Where L5 Stops vs. L6 Goes Further

*An L5 candidate might define:*
- "Users can view their feed"
- "Users can post content"

*A Staff engineer:*
- Separates flows by type (read/write/control)
- Specifies behaviors precisely ("within 1 minute")
- Addresses edge cases explicitly
- Avoids implementation details in requirements
- Considers operational flows (not just user flows)

---

# Phase 3: Scale

## Establishing Scale

**My narration**: "Let me establish the scale we're designing for. I'll make some assumptions and check if they're in the right ballpark."

### User Scale

| Metric | Value | Rationale |
|--------|-------|-----------|
| MAU | 500 million | Major social platform |
| DAU | 200 million | 40% DAU/MAU ratio (good engagement) |
| Concurrent users (peak) | 20 million | ~10% of DAU online at peak |

### Activity Scale

| Metric | Value | Derivation |
|--------|-------|------------|
| Feed loads per day | 1 billion | 200M DAU × 5 sessions/day |
| Feed loads per second (avg) | ~12,000 | 1B / 86,400 |
| Feed loads per second (peak) | ~50,000 | 4x average at peak hours |
| New posts per day | 100 million | 50% of DAU posts once |
| New posts per second (avg) | ~1,200 | 100M / 86,400 |
| New posts per second (peak) | ~5,000 | 4x average |

### Read/Write Ratio

**Feed loads : Posts = 1B : 100M = 10:1**

*But that's external requests. The interesting ratio is internal:*

**Feed generation reads : Post fan-out writes**

If average user has 500 followers:
- 100M posts × 500 followers = 50 billion fan-out writes per day (if push model)
- vs. 1 billion feed reads

This is why we need to think carefully about push vs. pull.

---

## Peak vs. Average Load

**My narration**: "I need to design for peak, not average. Let me think about what drives peak."

| Factor | Peak Multiplier | Notes |
|--------|-----------------|-------|
| Time of day (primetime) | 3-4x | Evening hours in major markets |
| Day of week | 1.2x | Weekends slightly higher |
| Special events | 5-10x | Breaking news, major sports events |

**Design target**: 50K feed loads/second sustained, ability to handle 100K+ with graceful degradation.

---

## Identifying Bottlenecks

**My narration**: "At this scale, where are the bottlenecks?"

1. **Feed Generation** — Computing a personalized feed at 50K/second is non-trivial
2. **Fan-Out** — If we push updates to followers, celebrity posts create massive write amplification
3. **Ranking** — ML-based ranking at this scale requires careful design
4. **Database I/O** — 50K reads/second from user's content is significant

---

## How Scale Influences Architecture

**My narration**: "Scale is driving several key architecture decisions:"

1. **Precomputation vs. Real-time**
   - At 50K/second, we can't compute feeds from scratch each time
   - Need some form of precomputation or caching

2. **Push vs. Pull**
   - For normal users (< 10K followers): Push is efficient
   - For celebrities (> 10K followers): Pull is necessary
   - Hybrid model required

3. **Caching**
   - Feed cache is essential
   - Content cache reduces database load
   - User preference cache avoids repeated lookups

4. **Sharding**
   - User data sharded by user_id
   - Content data sharded by author_id
   - Feed data sharded by owner_id

---

## Where L5 Stops vs. L6 Goes Further

*An L5 candidate might say:*
- "It's a large system, millions of users"
- "We'll need to scale horizontally"

*A Staff engineer:*
- Derives specific numbers from first principles
- Shows the math: "200M DAU × 5 sessions = 1B feed loads"
- Calculates internal amplification (fan-out)
- Identifies specific bottlenecks
- Connects scale to architecture decisions

---

# Phase 4: Non-Functional Requirements

## Establishing NFRs

**My narration**: "Now let me establish the quality requirements that will drive architecture decisions."

### Latency

| Operation | Target | Rationale |
|-----------|--------|-----------|
| Feed load (initial) | <300ms P99 | User waiting, app launch |
| Feed scroll (next page) | <200ms P99 | Seamless scrolling experience |
| Refresh (new content check) | <100ms P99 | Pull-to-refresh responsiveness |
| Content publish to feed | <60 seconds P95 | Tolerable delay for new posts |

**My narration**: "I'm prioritizing read latency over write latency. Users are actively waiting for feed loads. A 60-second delay for new posts appearing is acceptable—users don't usually check immediately if their post is in followers' feeds."

### Availability

| Component | Target | Rationale |
|-----------|--------|-----------|
| Feed serving | 99.9% | Core product experience |
| Feed generation | 99.9% | Required for fresh feeds |
| Content ingestion | 99.99% | Can't lose posts |

**My narration**: "99.9% is about 8 hours of downtime per year. For the feed, that's our target. For content ingestion, we need higher availability—losing user content is unacceptable."

### Consistency

| Aspect | Model | Rationale |
|--------|-------|-----------|
| Feed content | Eventual (30-60 sec) | Acceptable for new posts to appear with delay |
| Interaction counts | Eventual | Likes/comments can lag |
| User preferences | Read-your-writes | User expects mute to take effect immediately |
| Content existence | Strong | Deleted content should disappear quickly |

**My narration**: "I'm accepting eventual consistency for most things. The feed isn't a real-time system—nobody expects their post to appear in followers' feeds within milliseconds. But user preferences (like muting an account) should take effect immediately for that user."

### Reliability

- **No content loss**: Once a post is acknowledged, it cannot be lost
- **No feed corruption**: Feed should never show duplicate or broken content
- **Idempotent operations**: Retries should be safe

### Security

- **Authentication**: All feed requests from authenticated users
- **Authorization**: Users only see content they have access to
- **Rate limiting**: Protect against abuse
- **Content safety**: Integration with content moderation (out of scope for this design)

---

## Explicit Trade-Offs

**My narration**: "Let me be explicit about the trade-offs I'm making."

| Trade-Off | Choice | What We Sacrifice | Why |
|-----------|--------|-------------------|-----|
| Freshness vs. Latency | Latency | Tolerate 60-second staleness | Users expect instant app launch |
| Consistency vs. Availability | Availability | Eventual consistency for most data | Feed doesn't need strong consistency |
| Personalization vs. Simplicity | Moderate personalization | Full ML optimization | Can iterate; start simpler |
| Push vs. Pull | Hybrid | Complexity | Neither alone works at scale |

---

## Where L5 Stops vs. L6 Goes Further

*An L5 candidate might say:*
- "The system should be fast and reliable"
- "We need caching for performance"

*A Staff engineer:*
- Quantifies every NFR: "P99 <300ms, 99.9% availability"
- Distinguishes requirements by component
- Makes trade-offs explicit: "I'm choosing X over Y because..."
- Connects NFRs to architecture: "Because we need <300ms, we need precomputation"

---

# Phase 5: Assumptions & Constraints

## Assumptions

**My narration**: "Let me state my assumptions explicitly. If any of these are wrong, the design might need adjustment."

### Infrastructure Assumptions

1. **Cloud infrastructure** with auto-scaling, load balancing, managed databases
2. **CDN** for static content delivery (images, videos)
3. **Distributed caching** (Redis cluster or equivalent)
4. **Message queue** for async processing (Kafka or equivalent)
5. **Monitoring/alerting** infrastructure exists

### Service Assumptions

1. **Content service** exists and provides content by ID
2. **Social graph service** exists and provides follow relationships
3. **User service** exists with authentication/profile data
4. **Ranking service** exists and can score content for a user
5. **Analytics pipeline** exists to consume events

### Behavioral Assumptions

1. **Traffic follows typical patterns**: 3-4x peak during primetime
2. **Power-law distribution**: 1% of users create 50% of content
3. **Celebrity accounts**: ~0.1% have 1M+ followers
4. **Typical follow count**: Median ~200, mean ~500 (heavy tail)

### Environmental Assumptions

1. **Network latency** within region is <5ms
2. **Third-party services** (CDN, push) have 99.9% availability
3. **Database replication lag** is <100ms for read replicas

---

## Constraints (Given by Problem)

1. **Scale**: 200M DAU, 50K feed loads/second peak
2. **Latency**: <300ms P99 for feed load
3. **Freshness**: New posts appear within 60 seconds
4. **Platform**: Existing microservice ecosystem

---

## Simplifications

**My narration**: "I'm making some simplifications to focus on the core challenges. I'll note what I'm simplifying so we can discuss if needed."

1. **Single region**: Designing for single region first; global adds complexity
2. **Text focus**: Not designing media delivery in detail (CDN handles it)
3. **Simple ranking**: Treating ranking as a black box that returns scores
4. **No ads**: Leaving slots for ads but not designing ad selection
5. **No Stories**: Ephemeral content is a separate feature

---

## Why These Are Reasonable

**My narration**: "These simplifications are reasonable because:
- Single region captures the core complexity; multi-region is an extension
- Media delivery is a solved problem (CDN)
- Ranking is a deep topic worthy of its own design
- Ad selection is typically a separate team's domain
- Stories have different access patterns and would complicate this design"

---

## Where L5 Stops vs. L6 Goes Further

*An L5 candidate might:*
- Not state assumptions (they're implicit)
- Design without acknowledging constraints
- Simplify without saying so (looks like oversight)

*A Staff engineer:*
- States all assumptions explicitly
- Categorizes: assumptions vs. constraints vs. simplifications
- Explains why simplifications are reasonable
- Invites correction: "Is this assumption valid?"

---

# Architecture Design

**My narration**: "Now I have a solid foundation. Let me design the architecture that meets these requirements."

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Clients (Mobile/Web)                       │
└────────────────────────────────────┬────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                            API Gateway                               │
│                    (Auth, Rate Limiting, Routing)                    │
└────────────────────────────────────┬────────────────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
              ▼                      ▼                      ▼
     ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
     │  Feed Service   │    │ Content Service │    │  Publish Flow   │
     │                 │    │   (Existing)    │    │    Service      │
     └────────┬────────┘    └────────┬────────┘    └────────┬────────┘
              │                      │                      │
              ▼                      │                      │
     ┌─────────────────┐             │                      │
     │   Feed Cache    │◄────────────┘                      │
     │    (Redis)      │                                    │
     └────────┬────────┘                                    │
              │                                             │
              ▼                                             ▼
     ┌─────────────────┐                          ┌─────────────────┐
     │  Feed Storage   │                          │   Fan-Out       │
     │   (Sharded)     │◄─────────────────────────│   Service       │
     └────────┬────────┘                          └────────┬────────┘
              │                                            │
              │                      ┌─────────────────────┘
              ▼                      ▼
     ┌─────────────────┐    ┌─────────────────┐
     │  Ranking        │    │  Message Queue  │
     │  Service        │    │    (Kafka)      │
     └─────────────────┘    └─────────────────┘
```

---

## Component Design

### Feed Service

**Responsibility**: Generate and serve personalized feeds

**Design decisions**:

1. **Feed Construction Strategy**: Hybrid push-pull
   - For users with <10K followers: Pre-materialized feeds (push at publish time)
   - For celebrities (>10K followers): Merge at read time (pull)
   
2. **Feed Cache**:
   - Cache generated feeds in Redis
   - Cache key: `feed:{user_id}:{page}`
   - TTL: 5 minutes (balance freshness vs. load)
   - On cache miss: Generate from feed storage + celebrity pull

3. **Pagination**:
   - Cursor-based, not offset-based
   - Cursor encodes: timestamp + last_item_id
   - Prevents duplicate/missed items across pages

**Why this design**:
"At 50K requests/second, we can't compute feeds from scratch. Precomputation (push) works for most users. But celebrities have millions of followers—pushing to all of them would be 50B writes/day for just the top 1000 accounts. That's untenable. So we pull celebrity content at read time and merge it with the pre-materialized feed."

---

### Fan-Out Service

**Responsibility**: Distribute new content to followers' feeds

**Design decisions**:

1. **Fan-Out Logic**:
   ```
   if author.follower_count < 10,000:
       push_to_followers(content)  # Write to each follower's feed
   else:
       store_for_pull(content)      # Just store; pulled at read time
   ```

2. **Async Processing**:
   - Content publish → Kafka message
   - Fan-out workers consume and distribute
   - Decouples publish latency from fan-out completion

3. **Prioritization**:
   - Fan-out workers prioritize active users
   - Inactive users' feeds updated with lower priority

**Why this design**:
"The fan-out service handles the write amplification. For a user with 500 followers, one post becomes 500 writes to follower feeds. We do this asynchronously so publish latency stays low. The 10K threshold for push vs. pull is tunable based on observed system performance."

---

### Feed Storage

**Responsibility**: Store materialized feeds

**Design decisions**:

1. **Data Model**:
   ```
   feed_items table:
     user_id (partition key)
     timestamp (sort key)
     content_id
     author_id
     ranking_score
   ```

2. **Sharding**:
   - Shard by user_id
   - Each user's feed is on one shard
   - No cross-shard queries for feed read

3. **Storage Choice**:
   - Key-value store (Cassandra or DynamoDB)
   - Optimized for write throughput (fan-out)
   - Optimized for range queries (feed read)

4. **Retention**:
   - Keep 7 days of feed items per user
   - Background job cleans older items
   - Reduces storage, feed stays fresh

**Why this design**:
"Sharding by user_id means each feed read hits exactly one shard—no scatter-gather. Cassandra handles the write throughput for fan-out. 7-day retention keeps storage bounded."

---

### Content Merging (Read Path)

**My narration**: "Let me trace through what happens when a user loads their feed."

**Read Path (Detailed)**:

1. **Request arrives**: Client requests feed for user_id
2. **Cache check**: Look for `feed:{user_id}:1` in Redis
3. **Cache hit**: Return cached feed (most requests)
4. **Cache miss**:
   a. Fetch pre-materialized feed items from Feed Storage (500 items)
   b. Fetch celebrity content IDs (from users they follow with >10K followers)
   c. Fetch content details from Content Service
   d. Merge and rank using Ranking Service
   e. Return top 20, store in cache
5. **Pagination**: Subsequent pages use cursor to fetch next batch

**Latency breakdown**:

| Step | Target | Notes |
|------|--------|-------|
| Cache lookup | <5ms | Redis is fast |
| Feed Storage query | <50ms | Single shard |
| Celebrity content fetch | <50ms | Parallel fetches |
| Content Service calls | <50ms | Parallel, batched |
| Ranking | <50ms | Pre-loaded model |
| Merge & serialize | <10ms | In-memory |
| **Total (cache miss)** | **<215ms** | Within 300ms budget |

---

## Alternative Architectures Considered

**My narration**: "Before settling on this design, I considered two alternatives."

### Alternative 1: Pure Push (Rejected)

**Description**: Push every post to every follower's feed at publish time.

**Why rejected**:
- Celebrity with 50M followers → 50M writes per post
- Top 1000 celebrities posting once/day = 50B writes/day
- Storage cost: ~50B × 100 bytes = 5TB/day just for celebrity posts
- Not sustainable

**When it would work**: Platforms where max follower count is limited (like private social networks).

### Alternative 2: Pure Pull (Rejected)

**Description**: No precomputation; compute feed entirely at read time.

**Why rejected**:
- 50K feeds/second, each requiring:
  - Fetch 500 followee IDs
  - Fetch recent content from each (500 queries)
  - Rank 5000+ items
- Total: 25M content queries/second
- Latency would exceed 1 second

**When it would work**: Very small scale (< 100K users) or with aggressive caching.

### Chosen: Hybrid Push-Pull

**Why**: Best of both worlds. Push handles 99% of users efficiently. Pull handles the 1% that would explode the push model.

## Quick Visual: Push vs Pull vs Hybrid

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PUSH vs PULL vs HYBRID                                  │
│                                                                             │
│   PURE PUSH (Rejected)                 PURE PULL (Rejected)                 │
│   ┌────────────────────┐               ┌────────────────────┐               │
│   │ User posts         │               │ User opens feed    │               │
│   │      │             │               │      │             │               │
│   │      ▼             │               │      ▼             │               │
│   │ Write to EVERY     │               │ Fetch ALL followee │               │
│   │ follower's feed    │               │ content & merge    │               │
│   │      │             │               │      │             │               │
│   │      ▼             │               │      ▼             │               │
│   │ 50M writes for     │               │ 500 queries per    │               │
│   │ celebrity post!    │               │ feed load!         │               │
│   └────────────────────┘               └────────────────────┘               │
│   Problem: Write explosion             Problem: Read explosion              │
│                                                                             │
│   HYBRID (Chosen) ✓                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Regular User Posts (<10K followers)    Celebrity Posts (>10K)     │   │
│   │   ┌─────────────────────────────┐        ┌─────────────────────┐    │   │
│   │   │ PUSH to follower feeds      │        │ STORE once          │    │   │
│   │   │ (manageable writes)         │        │ PULL at read time   │    │   │
│   │   └─────────────────────────────┘        └─────────────────────┘    │   │
│   │                                                                     │   │
│   │   At read time: Merge pre-materialized feed + celebrity content     │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Failure Scenarios and Degradation

**My narration**: "Let me address what happens when things go wrong."

### Feed Cache Failure (Redis Down)

**Impact**: All requests hit Feed Storage and Content Service
**Degradation**:
- Latency increases from ~50ms to ~200ms
- Still within 300ms budget
- **Action**: Auto-scale Feed Storage reads, alert on-call

### Feed Storage Failure (Shard Down)

**Impact**: Users on that shard can't load feeds
**Degradation**:
- Return cached feed if available (stale but functional)
- If no cache, return trending content as fallback
- **Action**: Failover to replica, page on-call

### Content Service Failure

**Impact**: Can't fetch content details for feed items
**Degradation**:
- Return feed with basic metadata (titles only)
- Disable rich content (images, videos)
- **Action**: Alert, activate fallback rendering

### Fan-Out Service Failure

**Impact**: New posts don't appear in feeds
**Degradation**:
- Posts still stored (durability preserved)
- Feeds become stale but still functional
- **Action**: Queue builds up in Kafka, workers catch up when restored

### Ranking Service Failure

**Impact**: Can't personalize feeds
**Degradation**:
- Fall back to chronological ordering
- Reduced engagement but functional
- **Action**: Alert, monitor engagement metrics

---

## Evolution Over 1-2 Years

**My narration**: "Systems evolve. Here's how I'd expect this to change."

### Year 1: Optimization and Scaling

1. **Improved ranking**: Move from simple heuristics to ML-based ranking
2. **Global expansion**: Multi-region deployment with regional feeds
3. **Real-time signals**: Incorporate trending topics, breaking news
4. **Ad integration**: Full ad injection with pacing

### Year 2: Advanced Features

1. **Interest-based content**: Content from non-followed accounts based on interests
2. **Video-first feed**: Optimization for video consumption
3. **Stories integration**: Ephemeral content in feed
4. **Explore feed**: Separate discovery feed with different ranking

### Architecture Evolution

| Phase | Change | Impact |
|-------|--------|--------|
| 6 months | Multi-region | Replicated Feed Storage per region |
| 1 year | ML ranking | Add feature store, model serving infrastructure |
| 18 months | Video | Add video-specific caching, CDN optimization |
| 2 years | Interest graph | New signals, content expansion beyond follows |

---

## Complete Phase Summary

**My narration**: "Let me summarize how the phases connected."

| Phase | Key Decisions | Impact on Design |
|-------|---------------|------------------|
| Phase 1: Users | Consumers are primary; celebrity edge case | Hybrid push-pull for celebrities |
| Phase 2: Functional | 60-second freshness; infinite scroll | Async fan-out; cursor-based pagination |
| Phase 3: Scale | 50K feeds/sec; 10:1 read/write | Precomputation; heavy caching |
| Phase 4: NFRs | <300ms latency; eventual consistency | Cache-first; async updates acceptable |
| Phase 5: Assumptions | Social graph exists; ranking service exists | Integration design; not building from scratch |

**Each phase informed the next, and the final architecture addresses all the requirements we established.**

---

# Where L5 Stops vs. L6 Goes Further: Summary

Throughout this design, I've highlighted where a Staff engineer goes beyond Senior-level thinking. Let me summarize:

| Aspect | L5 Approach | L6 Approach |
|--------|-------------|-------------|
| Users | "Users view feeds" | Identifies 8+ user types, distinguishes primary/secondary |
| Use Cases | Lists happy path | Addresses edge cases explicitly (celebrity, cold start) |
| Scale | "Large scale" | Derives: "200M DAU × 5 sessions = 1B loads/day = 12K/sec" |
| NFRs | "Fast and reliable" | Quantifies: "P99 <300ms, 99.9% availability" |
| Trade-offs | Implicit | Explicit: "Choosing latency over freshness because..." |
| Assumptions | Implicit | Stated and categorized |
| Alternatives | One design | Considers and rejects alternatives with reasoning |
| Failures | Not addressed | Degradation strategy for each failure mode |
| Evolution | Not addressed | 1-2 year roadmap |

---

# Quick Reference Card

## 5-Phase Summary: News Feed System

| Phase | Key Question | Answer for Feed System |
|-------|-------------|------------------------|
| **Phase 1** | Who are the users? | Consumers (primary), creators, advertisers, ops |
| **Phase 2** | What must it do? | Generate feed, serve pages, handle refresh |
| **Phase 3** | How big is it? | 200M DAU, 50K feeds/sec, 10:1 read/write |
| **Phase 4** | How well must it work? | <300ms P99, 99.9% availability, eventual consistency |
| **Phase 5** | What are we assuming? | Existing services, cloud infra, single region |

---

## Key Numbers to Remember

| Metric | Value | How Derived |
|--------|-------|-------------|
| **DAU** | 200 million | Given/assumed for major platform |
| **Feed loads/day** | 1 billion | 200M DAU × 5 sessions |
| **Feed loads/sec** | 12K avg, 50K peak | 1B / 86,400, × 4 for peak |
| **Posts/day** | 100 million | 50% DAU posts once |
| **Fan-out writes/day** | 50 billion | 100M posts × 500 avg followers |
| **Storage (7 days)** | ~350 GB | 50B items × 100 bytes / 7 days |

---

## Trade-Offs Made

| Trade-Off | Choice Made | Why |
|-----------|------------|-----|
| Freshness vs Latency | Latency (60s stale OK) | Users expect instant app launch |
| Consistency vs Availability | Availability (eventual OK) | Feed doesn't need strong consistency |
| Push vs Pull | Hybrid | Neither alone works at scale |
| Personalization vs Simplicity | Moderate | Can iterate; start simpler |

---

## L5 vs L6: Quick Comparison

| Aspect | L5 Says | L6 Says |
|--------|---------|---------|
| **Users** | "Users view feeds" | "8 user types: consumers, creators, ops..." |
| **Scale** | "Large scale" | "200M DAU × 5 = 1B loads = 12K/sec" |
| **NFRs** | "Fast and reliable" | "P99 <300ms, 99.9% availability" |
| **Trade-offs** | Implicit | "Choosing X over Y because..." |
| **Celebrities** | Not addressed | "Hybrid push-pull: threshold at 10K" |
| **Failures** | Not addressed | "Redis down → latency increases to 200ms" |

---

## Failure Scenarios Quick Reference

| Component | Impact | Degradation Strategy |
|-----------|--------|---------------------|
| **Feed Cache (Redis)** | Latency ↑ | Still within budget; auto-scale storage |
| **Feed Storage (Shard)** | Users can't load | Return cached/trending; failover |
| **Content Service** | No rich content | Basic metadata only |
| **Fan-Out Service** | Feeds stale | Queue builds; catch up when restored |
| **Ranking Service** | No personalization | Fall back to chronological |

---

## Key Phrases for This Design

**Phase 1:**
- "I see consumers as primary; creators and advertisers are secondary"
- "The celebrity edge case drives a key architectural decision"

**Phase 2:**
- "I'm specifying what happens, not how"
- "Content should appear within 60 seconds—this gives flexibility for async"

**Phase 3:**
- "200M DAU × 5 sessions = 1B loads/day = 12K/sec average"
- "Celebrity with 50M followers → 50M writes per post is untenable"

**Phase 4:**
- "I'm prioritizing read latency over write latency"
- "Eventual consistency is acceptable; users don't expect instant propagation"

**Phase 5:**
- "I'm assuming social graph and ranking services exist"
- "Single region is a simplification; multi-region is an extension"

---

# Part 7: Blast Radius and Dependency Analysis — Staff-Level Depth

Staff engineers don't just list failure scenarios—they quantify blast radius and trace dependency cascades. Let me extend the failure analysis.

## Blast Radius Quantification

For each failure scenario, Staff engineers calculate impact:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BLAST RADIUS ANALYSIS: NEWS FEED                         │
│                                                                             │
│   Component              Users Affected    Duration    Revenue Impact       │
│   ─────────────────────────────────────────────────────────────────────     │
│                                                                             │
│   Feed Cache (1 node)    ~5% of users     Until restart   Low               │
│                          (shard affinity)  (~2 min)                         │
│                                                                             │
│   Feed Cache (cluster)   100% of users    Degraded,       Medium            │
│                                           not down                          │
│                                                                             │
│   Feed Storage (1 shard) ~5% of users     Until failover  Low               │
│                                           (~30 sec)                         │
│                                                                             │
│   Feed Storage (all)     100% of users    Major outage    Critical          │
│                                                                             │
│   Fan-Out Service        0% immediately   Freshness       Low               │
│                          (feeds stale)    degrades                          │
│                                                                             │
│   Content Service        100% of users    Rich content    High              │
│                                           missing                           │
│                                                                             │
│   Social Graph Service   100% of users    Can't compute   Critical          │
│                                           new feeds                         │
│                                                                             │
│   Ranking Service        100% of users    No              Medium            │
│                                           personalization                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Dependency Cascade Analysis

**What happens when the Social Graph Service fails?**

This is a critical dependency often overlooked:

```
Social Graph Service DOWN
         │
         ├──► Feed Generation BLOCKED (can't get followee list)
         │         │
         │         └──► New feed requests CAN'T be served
         │                    │
         │                    └──► But cached feeds still work! 
         │
         ├──► Fan-Out BLOCKED (can't get follower list)
         │         │
         │         └──► New posts queued but not distributed
         │
         └──► Celebrity detection BLOCKED (can't count followers)
                   │
                   └──► Fall back to stored celebrity list
```

**Mitigation strategies:**

| Dependency | Failure Mode | Mitigation |
|------------|-------------|------------|
| Social Graph | Complete outage | Cache follow relationships locally (1-hour TTL) |
| Social Graph | Slow response | Timeout at 100ms, use cached data |
| Social Graph | Partial data | Accept incomplete followee list, note in metrics |

**Staff-Level Statement:**

"The Social Graph Service is a critical dependency. If it's down, we can't compute new feeds or fan out posts. My mitigation: cache the social graph locally with 1-hour TTL. Stale follow relationships are acceptable—users don't frequently add/remove follows. For fan-out, we queue posts and replay when the service recovers."

## Cascading Failure Prevention

At Staff level, you design to prevent cascades:

| Pattern | How Applied | Why |
|---------|-------------|-----|
| **Circuit breaker** | Each external service call | Prevent slow dependency from blocking all requests |
| **Bulkhead** | Separate thread pools per dependency | Content Service issues don't affect Ranking Service |
| **Timeout** | 100ms for all service calls | Bound worst-case latency |
| **Fallback** | Every service call has fallback behavior | Degraded > down |
| **Retry budget** | 10% of requests can retry | Prevent retry storms |

---

# Part 8: Operational Readiness — Built-In from Day One

Staff engineers design for operability, not just functionality. Here's what's built into this design:

## Observability Design

**Metrics emission at every boundary:**

| Component | Key Metrics | Alert Threshold |
|-----------|-------------|-----------------|
| API Gateway | Request rate, error rate, latency P50/P99 | Error rate > 1%, P99 > 500ms |
| Feed Service | Cache hit rate, generation latency | Hit rate < 80%, latency > 250ms |
| Feed Cache | Memory usage, eviction rate | Memory > 80%, evictions > 10K/min |
| Feed Storage | Read latency, write latency, queue depth | P99 > 100ms, queue > 10K |
| Fan-Out Service | Processing rate, lag, failure rate | Lag > 10min, failures > 1% |

**Distributed tracing:**

Every request includes trace context:
- `trace_id`: Unique per user request
- `span_id`: Unique per operation
- `parent_span_id`: Links operations

**Structured logging:**

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "service": "feed-service",
  "trace_id": "abc123",
  "user_id": "user_456",
  "operation": "generate_feed",
  "duration_ms": 45,
  "cache_hit": true,
  "items_returned": 20,
  "celebrity_items": 3
}
```

## Deployment Safety

| Requirement | Implementation |
|-------------|----------------|
| Zero-downtime deploys | Rolling deployment, connection draining |
| Canary releases | 1% → 10% → 50% → 100% over 4 hours |
| Instant rollback | Previous version retained, <1 min rollback |
| Feature flags | New ranking algorithms behind flags |

## Runbooks (On-Call Reference)

**Runbook: Feed Latency Spike**

```
SYMPTOM: P99 latency > 300ms for 5+ minutes

DIAGNOSIS:
1. Check cache hit rate (Grafana: feed-cache-hits)
   - If < 80%: Cache issue, go to step 2
   - If > 80%: Backend issue, go to step 3

2. Cache issue:
   a. Check Redis cluster health
   b. Check for hot keys (celebrity feeds)
   c. Consider cache warm-up for affected users

3. Backend issue:
   a. Check Feed Storage latency
   b. Check Content Service latency  
   c. Check Ranking Service latency
   d. Identify slowest component, check its metrics

MITIGATION:
- If cache: Add cache nodes or increase TTL
- If Content Service: Enable basic-metadata-only mode
- If Ranking Service: Enable chronological fallback
- If Fan-Out backed up: Pause fan-out for low-priority users

ESCALATION:
- If not resolved in 15 min: Page secondary on-call
- If availability < 99.5%: Initiate incident
```

---

# Part 9: Multi-Region Evolution — Technical Deep Dive

The architecture section mentioned multi-region as a future evolution. Here's the Staff-level technical detail:

## What Changes for Multi-Region

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-REGION ARCHITECTURE EVOLUTION                       │
│                                                                             │
│   SINGLE REGION (Current)              MULTI-REGION (Year 1)                │
│   ─────────────────────────            ─────────────────────                │
│                                                                             │
│   ┌─────────────────┐                  ┌─────────────────┐                  │
│   │  US-West        │                  │  US-West        │  ◄─── Primary    │
│   │  (All users)    │        →         │  (US users)     │       for US     │
│   └─────────────────┘                  └────────┬────────┘                  │
│                                                 │                           │
│                                          Async replication                  │
│                                                 │                           │
│                                        ┌────────┴────────┐                  │
│                                        │                 │                  │
│                                   ┌────▼────┐       ┌────▼────┐             │
│                                   │ EU      │       │ APAC    │             │
│                                   │ (EU     │       │ (APAC   │             │
│                                   │  users) │       │  users) │             │
│                                   └─────────┘       └─────────┘             │
│                                                                             │
│   KEY CHANGES:                                                              │
│   • Feed Storage replicated per region                                      │
│   • Fan-Out writes to local region first, async to others                   │
│   • User reads from nearest region                                          │
│   • Cross-region follows require eventual consistency                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Technical Changes Required

| Component | Single Region | Multi-Region Change |
|-----------|---------------|---------------------|
| **Feed Storage** | Single cluster | Per-region cluster + async replication |
| **Feed Cache** | Single Redis cluster | Per-region Redis + cache invalidation |
| **Fan-Out** | Single Kafka | Per-region Kafka + cross-region connectors |
| **User routing** | N/A | GeoDNS + region-aware load balancing |
| **Content IDs** | Simple UUIDs | Region-prefixed IDs for routing |

## Cross-Region Consistency Challenges

| Scenario | Challenge | Resolution |
|----------|-----------|------------|
| User follows account in different region | Follower list needs cross-region sync | Async sync with 30-second lag acceptable |
| Celebrity posts to global audience | Fan-out must reach all regions | Post stored once per region, pulled at read time |
| User travels to different region | Their feed needs to be accessible | Feed cache miss in new region, fetch from home region |

## Migration Path

| Phase | Action | Risk | Rollback |
|-------|--------|------|----------|
| 1 | Deploy read replicas in EU/APAC | Low | Remove replicas |
| 2 | Route EU/APAC reads to local replicas | Medium | Route back to US |
| 3 | Enable local writes for EU/APAC users | High | Route writes to US |
| 4 | Enable cross-region fan-out | High | Disable, use pull-only |

---

# Part 10: Interview Calibration for End-to-End Design

## Common Timing Mistakes

| Mistake | What Happens | Fix |
|---------|--------------|-----|
| **Too long on Phase 1** | Run out of time for architecture | Cap at 7 min; scope early |
| **Skip to architecture** | Design without foundation | "Let me establish requirements first" |
| **Over-detail Phase 3** | Calculate everything | Pick 3-5 key numbers, derive rest |
| **Shallow architecture** | Draw boxes without explaining | Trace a request through, explain decisions |
| **No failure discussion** | Miss Staff-level signal | Proactively raise: "What if X fails?" |

## Interviewer Signals Throughout the Design

| Phase | Positive Signal | Concerning Signal |
|-------|-----------------|-------------------|
| **Phase 1** | Identifies celebrity edge case unprompted | "Users view feeds" (too simple) |
| **Phase 2** | Specifies behavior, not implementation | "Store in Cassandra" (too early) |
| **Phase 3** | Derives numbers from first principles | "It's large scale" (too vague) |
| **Phase 4** | Quantifies and makes trade-offs | "Fast and reliable" (not quantified) |
| **Phase 5** | States assumptions, invites correction | Implicit assumptions (risky) |
| **Architecture** | Explains why, not just what | Draws boxes without reasoning |
| **Failures** | Proactively discusses degradation | Only addresses when asked |

## L6 Phrases for Each Phase

| Phase | L6 Phrase |
|-------|-----------|
| **Opening** | "Let me work through this systematically—users, requirements, scale, NFRs, then architecture" |
| **Phase 1** | "The celebrity edge case is interesting—it will drive a key architecture decision" |
| **Phase 2** | "I'm specifying what happens, not how. That's an architecture decision for later" |
| **Phase 3** | "Let me derive: 200M DAU × 5 sessions = 1B loads/day. That's 12K/sec average, 50K peak" |
| **Phase 4** | "I'm prioritizing read latency over freshness because users wait for feed load" |
| **Phase 5** | "I'm assuming social graph service exists. If not, that changes scope significantly" |
| **Architecture** | "I considered pure push and pure pull. Here's why hybrid is the right choice" |
| **Failures** | "Let me trace through what happens when each component fails" |
| **Evolution** | "In year 1, we'd add multi-region. Here's the migration path" |

## Self-Check: Did I Cover Everything?

Before wrapping up, Staff engineers mentally check:

☐ Did I identify multiple user types including ops?
☐ Did I address the celebrity/hot key problem?
☐ Did I derive scale numbers, not guess?
☐ Did I quantify NFRs with specific targets?
☐ Did I make trade-offs explicit?
☐ Did I state assumptions and invite correction?
☐ Did I explain why for each architecture decision?
☐ Did I consider alternatives and explain why rejected?
☐ Did I discuss failure scenarios and degradation?
☐ Did I mention how the system evolves?

---

# Part 11: Final Verification — L6 Readiness Checklist

## Does This End-to-End Walkthrough Meet L6 Expectations?

| L6 Criterion | Coverage | Notes |
|-------------|----------|-------|
| **Judgment & Decision-Making** | ✅ Strong | Trade-offs explicit, alternatives considered, decisions justified |
| **Failure & Degradation Thinking** | ✅ Strong | Blast radius, cascade analysis, degradation strategies |
| **Scale & Evolution** | ✅ Strong | Derived numbers, multi-region evolution, migration path |
| **Staff-Level Signals** | ✅ Strong | L5 vs L6 throughout, interview calibration |
| **Real-World Grounding** | ✅ Strong | News Feed with concrete numbers and components |
| **Interview Calibration** | ✅ Strong | Timing, phrases, interviewer signals, self-check |

## Staff-Level Signals Demonstrated

✅ Structured approach announced upfront
✅ Multiple user types identified including operational
✅ Celebrity edge case surfaced and addressed
✅ Scale derived from first principles with math shown
✅ NFRs quantified with specific targets
✅ Trade-offs made explicit with reasoning
✅ Assumptions stated and categorized
✅ Architecture decisions explained with alternatives
✅ Failure scenarios with blast radius and degradation
✅ Evolution roadmap with technical migration path
✅ Operational readiness (observability, deployment, runbooks)

---

# Brainstorming Questions

## Phase 1: Users & Use Cases

1. What other edge cases might we have missed? How would each affect the design?

2. If we were designing for a professional network (like LinkedIn) instead of a social network, how would the users and use cases differ?

3. How would the design change if we prioritized content creators over content consumers?

## Phase 2: Functional Requirements

4. If we required content to appear in feeds within 5 seconds (instead of 60), what would change?

5. What if we needed to support "undo" for published content? How would that affect the functional requirements?

6. How would the requirements differ for an algorithmic feed vs. a chronological feed?

## Phase 3: Scale

7. At 10x this scale (2 billion DAU), what breaks first? How would you address it?

8. If the read/write ratio were reversed (10 writes per read), how would the architecture change?

9. What if 10% of users were celebrities (instead of 0.1%)? How would that affect push vs. pull?

## Phase 4: NFRs

10. If we needed strong consistency for the feed, what would we sacrifice and what would we change?

11. What if we targeted 99.99% availability instead of 99.9%? What would that cost?

12. How would the design change for a market with poor network connectivity (high latency, packet loss)?

## Phase 5: Assumptions

13. What if we couldn't use a managed cache (Redis)? How would we handle caching?

14. What if the ranking service had 1-second latency instead of 50ms?

15. Which assumption, if wrong, would most invalidate this design?

---

# Reflection Prompts

Set aside 15-20 minutes for each of these reflection exercises.

## Reflection 1: Your End-to-End Coherence

Think about how you connect phases in system design.

- When you design, do you trace decisions back to requirements?
- Can you explain why each component exists in terms of user needs or NFRs?
- Do your later design decisions contradict earlier ones?
- How do you ensure your design tells a coherent story?

For a design you've done, trace 3 component choices back to the requirements that justified them.

## Reflection 2: Your Failure Resilience Design

Consider how you design for failure.

- Do you explicitly design degradation strategies?
- Can you describe what happens when each dependency fails?
- Have you defined blast radius for failures in your systems?
- Do you design recovery before you design happy paths?

For your current system, write a failure mode matrix covering all dependencies.

## Reflection 3: Your Interview Presentation

Examine how you present designs in interviews.

- Do you maintain a clear structure throughout?
- How do you balance depth and breadth in 45 minutes?
- Do you check in with the interviewer regularly?
- Can you articulate why your design is Staff-level vs. Senior-level?

Record yourself presenting a design for 35 minutes. Watch it and note three improvements.

---

# Homework Exercises

## Exercise 1: Redesign Under Different Constraints

Redesign the news feed system under these constraints:

**Scenario A**: Latency target is 100ms instead of 300ms
- What changes?
- What do you sacrifice?

**Scenario B**: Freshness target is 5 seconds instead of 60 seconds
- What changes?
- Is pure push now required?

**Scenario C**: 99.99% availability instead of 99.9%
- What redundancy is needed?
- How does cost change?

Write a 1-page summary of how the design changes for each scenario.

## Exercise 2: Identify the Riskiest Assumption

Review all the assumptions made in this design:

1. Rank them by risk (likelihood of being wrong × impact if wrong)
2. For the top 3 riskiest assumptions:
   - How would you validate them?
   - What's the contingency plan if they're wrong?
   - How would the design change?

## Exercise 3: Simplify the Design Further

The current design has:
- Feed Service
- Fan-Out Service
- Feed Storage
- Feed Cache
- Integration with 4 external services

Simplify it for a startup with:
- 100K DAU (not 200M)
- 3-person engineering team
- 3-month timeline

What components do you eliminate? What complexity do you remove? How does the simplified design differ?

## Exercise 4: Apply to a Different System

Apply the same 5-phase framework to design a **Rate Limiter** system.

For each phase:
- What are the key questions?
- What are the key decisions?
- How does each phase influence the next?

Compare the complexity of Rate Limiter vs. News Feed. Which phases are more important for each?

## Exercise 5: Failure Mode Expansion

For each failure scenario discussed:

1. Define the monitoring/alerting that would detect it
2. Define the runbook for on-call response
3. Design an automated mitigation (if possible)
4. Estimate the blast radius (how many users affected)

## Exercise 6: Interview Practice

Practice presenting this design in 35 minutes:

- 5 minutes: Phase 1 (Users & Use Cases)
- 5 minutes: Phase 2 (Functional Requirements)
- 5 minutes: Phase 3 (Scale)
- 5 minutes: Phase 4 (NFRs)
- 3 minutes: Phase 5 (Assumptions & Constraints)
- 10 minutes: Architecture walkthrough
- 2 minutes: Summary and questions

Record yourself. Watch for:
- Did you maintain the structure?
- Did you explain trade-offs?
- Did you check in with the "interviewer"?
- Was your pacing appropriate?

---

# Conclusion

This walkthrough demonstrated how a Staff Engineer approaches system design:

**Structured, not chaotic**: Five clear phases, each building on the previous.

**Explicit, not implicit**: Assumptions stated, trade-offs acknowledged, scope controlled.

**Quantified, not vague**: Specific numbers for scale, latency, availability.

**Trade-off aware**: Every design choice comes with sacrifices; we name them.

**Failure-minded**: Systems break; we plan for it.

**Evolution-aware**: Today's design is tomorrow's legacy; we plan for change.

The news feed system is complex, but by working through the framework systematically, it becomes tractable. Each phase reduces uncertainty until the architecture emerges naturally from the requirements.

This is Staff-level thinking: not just building systems that work, but building systems that work well, with explicit reasoning that can be challenged, defended, and evolved.

Practice this framework until it's second nature. Then in the interview room, you won't be wondering what to do next—you'll be leading a design discussion with confidence.

---