# Chapter 73: News Feed — Design Instagram / Twitter Timeline (L5)

> "Design a social media news feed" is one of the ten most common L5 interview questions.
> It tests your understanding of a deceptively simple problem: when a user logs in,
> they should see recent posts from people they follow. The hard part is the scale —
> millions of users, billions of posts, each user expecting their feed in under 500ms.
> The core design decision is fan-out strategy: do you push posts to follower feeds
> on write, or pull and assemble the feed on read? This chapter teaches you to choose
> correctly, defend the decision, and handle the edge cases.

---

## AT A GLANCE

```
╔══════════════════════════════════════════════════════════════════════════════╗
║               CHAPTER 73 — NEWS FEED (L5) AT A GLANCE                      ║
╠═══════════════════════════╦══════════════════════════════════════════════════╣
║  System                   ║  Core Design Choices                            ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Feed generation          ║  Fan-out on write (push model) for most users  ║
║                           ║  Fan-out on read for celebrities (> 5K followers)║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Feed storage             ║  Redis sorted set per user, key=user_id        ║
║                           ║  Score = timestamp. Top 200 posts per user.    ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Post persistence         ║  PostgreSQL: posts table, follows table        ║
║                           ║  Blob storage (S3) for media                   ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Pagination               ║  Cursor-based (last_seen_post_id + timestamp)  ║
║                           ║  NOT offset pagination (breaks at scale)       ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Feed read path           ║  API → Redis (feed cache) → merge celebrity   ║
║                           ║  posts at read time → return top 20            ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Fan-out worker           ║  Async: post published → Kafka → fan-out worker║
║                           ║  → write post_id to each follower's Redis feed ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Scale targets            ║  10M daily active users                        ║
║                           ║  100M total users, 500M posts stored           ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Scope OUT (L5)           ║  Multi-region, algorithmic ML ranking,         ║
║                           ║  ads insertion, story/reel prioritization      ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Staff level (Ch78)       ║  Celebrity index, ranking service, consistency ║
║                           ║  guarantees, partial failure handling, sharding ║
╚═══════════════════════════╩══════════════════════════════════════════════════╝
```

**Parts in this chapter:**
- Part 1: The Problem — What a News Feed Actually Is
- Part 2: Requirements
- Part 3: High-Level Design
- Part 4: API Design
- Part 5: Database Schema
- Part 6: Fan-Out on Write (Push Model)
- Part 7: Fan-Out on Read (Pull Model)
- Part 8: The Hybrid Approach
- Part 9: Timeline Storage Design
- Part 10: Cursor-Based Pagination
- Part 11: Basic Feed Ranking
- Part 12: Media Handling
- Part 13: Scaling
- Part 14: Interview Application
- Part 15: Pre-Interview Drill

---

## Why This Chapter Matters

"Design a news feed" appears in interviews at Meta (Facebook/Instagram), Twitter/X,
LinkedIn, TikTok, Pinterest, and Snap. It is a high-frequency question because it
tests multiple skills simultaneously: data modeling, caching strategy, async processing,
pagination, and the ability to reason about write vs. read trade-offs at scale.

The question is deceptively simple to answer superficially ("fetch recent posts from
people I follow and show them") but has genuine technical depth: at 100M users with
500M posts, naively fetching from the database on every feed load would be catastrophically
slow. Getting this question right requires understanding fan-out.

---

## Part 1: The Problem — What a News Feed Is

### 1.1 The Core Requirement

A user opens the app. Within 500ms, they see the 20 most recent posts from people
they follow, in reverse-chronological order (newest first). As they scroll down, more
posts appear. This sounds simple. The challenge is doing it at scale.

```
THE NAIVE APPROACH (and why it fails)
======================================

  SELECT p.*
  FROM posts p
  JOIN follows f ON p.user_id = f.followed_id
  WHERE f.follower_id = :current_user_id
  ORDER BY p.created_at DESC
  LIMIT 20;

  WHAT'S WRONG WITH THIS:
  - User follows 500 people
  - Each of those people has made 1,000 posts over time
  - This query touches: 500 × 1,000 = 500,000 rows before limiting to 20
  - With 10M DAU all loading their feeds at morning rush hour:
    10M queries × 500K rows scanned = 5 × 10^12 row scans per hour
  - Your database dies.
```

The solution to this performance problem is the entire chapter.

### 1.2 The Fan-Out Problem

When User A (who has 500 followers) publishes a post, there are two strategies:

**Push (fan-out on write)**: At the moment A posts, immediately write A's new post
into each of A's 500 followers' pre-computed feed caches. When a follower loads
their feed, it reads from the pre-computed cache — instant, O(1).

**Pull (fan-out on read)**: When a follower loads their feed, query all the people
they follow and collect their recent posts. Slower per-read, but no work at write time.

The trade-off:
- Push is fast on read, expensive on write (500 cache writes per post)
- Pull is slow on read, cheap on write (0 extra work per post, all happens at read)
- Push breaks for celebrities: Justin Bieber has 100M followers. One post = 100M
  cache writes. That is the "celebrity problem."

### 1.3 Scale to Understand

For a medium-sized social platform (our L5 scope):

| Metric | Number | Implication |
|--------|--------|-------------|
| Total users | 100M | Size of user/follow tables |
| Daily active users | 10M | Read traffic (feed loads) |
| Posts per day | 5M | Write traffic (fan-out load) |
| Average follows per user | 200 | Fan-out multiplier |
| Max followers (celebrities) | 5M | Determines push/pull threshold |
| Feed fetch latency target | < 500ms | Drives cache architecture |
| Posts retained in feed cache | 200 most recent | Redis memory bound |

### 1.4 The User Journey

**Posting (write path)**:
1. User creates a post (text + optional image/video)
2. Post is saved to the posts database
3. Media uploaded to object storage (S3)
4. A fan-out event is published to Kafka
5. Fan-out workers consume the event and write the post ID to each follower's feed cache
6. The post becomes visible in followers' feeds (within a few seconds)

**Reading (read path)**:
1. User opens the app or pulls to refresh
2. Client sends: GET /api/v1/feed
3. API server fetches the pre-computed feed from Redis (user's sorted set)
4. For any followed celebrities (> threshold), merge their recent posts at read time
5. Return top 20 posts with pagination cursor
6. Client renders the feed

### 1.5 Brainstorming Q&A — Part 1

**Q: How long should posts stay in the feed cache?**

The feed cache holds the most recent N posts for each user, not posts from a specific
time window. A user's feed cache always contains their freshest 200 posts (or however
many are available). Older posts are evicted when newer posts push them out. The Redis
sorted set makes this natural: ZADD adds new posts with a timestamp score; if the set
grows beyond 200, ZREMRANGEBYRANK removes the oldest. The cache is bounded by count,
not by time.

**Q: What if a user has zero followers and makes a post?**

Fan-out for zero followers means zero writes to follower feeds. The post is still saved
to the posts database. If someone later follows this user, the fan-out worker processes
a "follow" event and backfills recent posts from the newly followed user into the
follower's feed. Backfill limit: last 20 posts (to avoid overwhelming the feed with
old content from a new follow).

---

## Part 2: Requirements

### 2.1 Functional Requirements

- Users can create posts (text, optional image/video)
- Users can follow / unfollow other users
- When a user loads their feed, they see recent posts from people they follow
- Posts appear in reverse-chronological order (newest first)
- Users can like posts and add comments (simplified — just counts, no threading)
- Feed is paginated (load 20 at a time, scroll to load more)
- Posts can contain text (2,200 chars max), images, and short videos

### 2.2 Non-Functional Requirements

| Requirement | Target | Why |
|-------------|--------|-----|
| Feed load latency | < 500ms p99 | Users immediately see content on open |
| Post publish to visible | < 5 seconds | Near-real-time (fan-out must be fast) |
| Read availability | 99.9% | Feed outage directly impacts engagement |
| Write availability | 99.5% | Post failure is worse UX than feed failure |
| Storage (posts) | Petabytes (with media) | Long-term post retention |
| Feed consistency | Eventual | OK if a new post takes seconds to appear |

### 2.3 Clarifying Questions for the Interview

1. "Instagram-style (public + private accounts) or Twitter-style (all public)?"
2. "Reverse-chronological only, or with ranking/algorithm?"
3. "What is the maximum number of followers per user? (celebrity threshold)"
4. "Do we need to handle post deletion updating already-built feeds?"
5. "Multi-region or single-region?"

At L5: public posts only, reverse-chronological, max 5,000 followers for push model
(handle > 5K as celebrities), single-region.

### 2.4 What We Are NOT Building

- **Not in scope**: Algorithmic feed ranking (ML models), Stories/Reels, DM/messaging,
  notifications, advertising insertion, multi-region geo-routing
- **Simplified**: Comments are just a count. Likes are just a count.
  Post deletion is acknowledged but not fully designed in this version.

---

## Part 3: High-Level Design

### 3.1 The Key Systems

```
HIGH-LEVEL ARCHITECTURE
=========================

  WRITE PATH:

  User creates post
       │
       ▼
  [Post Service]  → Save to PostgreSQL (posts table)
       │           → Upload media to S3 (if image/video)
       │           → Publish event to Kafka: "new_post"
       │
       ▼
  [Kafka: new_post topic]
       │
       ▼
  [Fan-out Worker Pool]
       │ For each follower of this user (up to threshold):
       │   ZADD feed:{follower_id} {timestamp_epoch} {post_id}
       │   ZREMRANGEBYRANK feed:{follower_id} 0 -201  (keep top 200)
       ▼
  [Redis Feed Cache]  ← pre-computed feed per user


  READ PATH:

  User loads feed
       │
       ▼
  [Feed Service]
       │ → ZREVRANGE feed:{user_id} 0 19  (top 20 post IDs from Redis)
       │ → Fetch post details from Post Cache (Redis hash)
       │   ← on cache miss: fetch from PostgreSQL, populate cache
       │ → Merge celebrity posts (fetch recent N posts per followed celebrity)
       ▼
  JSON response: [{post_id, author, text, media_url, created_at, like_count}, ...]

  SHARED COMPONENTS:
  [PostgreSQL]  — posts, users, follows tables (source of truth)
  [Redis]       — feed cache per user (ZSET), post detail cache (Hash)
  [S3]          — media object storage
  [CDN]         — serves media files to users via edge
```

### 3.2 Component Responsibilities

| Component | Responsibility | Technology |
|-----------|---------------|------------|
| Post Service | Accept posts, validate, store, trigger fan-out | Go / Node.js |
| Fan-out Workers | Write post IDs to follower feed caches | Kafka consumers |
| Feed Service | Serve pre-computed feeds, handle celebrity merge | Go / Node.js |
| PostgreSQL | Store posts, users, follows (source of truth) | PostgreSQL + read replicas |
| Redis | Feed cache per user, post detail cache | Redis Cluster |
| S3 | Durable media object storage | S3 / GCS |
| CDN | Serve media files globally | CloudFront / Fastly |

---

## Part 4: API Design

### 4.1 Post APIs

**Create Post**
```
POST /api/v1/posts
Auth: required
Request:
{
  "text": "Just had the best coffee!",
  "media_ids": ["media_abc123"],  ← pre-uploaded media IDs
  "visibility": "public"
}
Response: {
  "post_id": "post_xyz789",
  "created_at": "2026-06-25T10:30:00Z",
  "status": "published"
}
Errors: 400 (text > 2,200 chars), 413 (too many media items > 10), 401
```

**Get Post**
```
GET /api/v1/posts/{post_id}
Response: {
  "post_id", "text",
  "author": { "user_id", "username", "avatar_url" },
  "media_urls": ["https://cdn.example.com/..."],
  "like_count", "comment_count",
  "created_at",
  "liked_by_me": false
}
Errors: 404 (not found), 403 (private post, not a follower)
```

**Like / Unlike Post**
```
POST   /api/v1/posts/{post_id}/like   → 204 No Content (idempotent)
DELETE /api/v1/posts/{post_id}/like   → 204 No Content (idempotent)
```

### 4.2 Feed API

**Get Feed**
```
GET /api/v1/feed?limit=20&cursor={cursor}

Response:
{
  "posts": [
    {
      "post_id": "post_xyz789",
      "text": "Just had the best coffee!",
      "author": { "user_id": "u_abc", "username": "alice", "avatar_url": "..." },
      "media_urls": [...],
      "like_count": 42,
      "comment_count": 7,
      "created_at": "2026-06-25T10:30:00Z",
      "liked_by_me": false
    },
    ...20 posts total...
  ],
  "next_cursor": "eyJsYXN0X3Bvc3RfaWQiOiJwb3N0XzEyMyJ9",
  "has_more": true
}

Errors:
  401 — not authenticated
  400 — invalid cursor format
```

### 4.3 Social Graph APIs

**Follow User**
```
POST /api/v1/users/{user_id}/follow
Response: 204 No Content
Side effect: triggers backfill of recently followed user's last 20 posts into follower's feed
Errors: 404 (user not found), 409 (already following), 422 (cannot follow yourself)
```

**Unfollow User**
```
DELETE /api/v1/users/{user_id}/follow
Response: 204 No Content
Note: does NOT immediately remove their posts from feed (cleaned lazily via natural expiry)
```

**Get Following List**
```
GET /api/v1/users/{user_id}/following?limit=50&cursor={cursor}
Response: { "users": [{ "user_id", "username", "avatar_url" }], "next_cursor" }
```

---

## Part 5: Database Schema

### 5.1 Users Table

```sql
CREATE TABLE users (
  user_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username         VARCHAR(30) UNIQUE NOT NULL,
  email            VARCHAR(255) UNIQUE NOT NULL,
  display_name     VARCHAR(100),
  bio              TEXT,
  avatar_url       VARCHAR(500),
  follower_count   INT NOT NULL DEFAULT 0,
  following_count  INT NOT NULL DEFAULT 0,
  is_celebrity     BOOLEAN NOT NULL DEFAULT FALSE,
                   -- TRUE when follower_count > 5,000 (fan-out threshold)
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_username ON users(username);
```

### 5.2 Posts Table

```sql
CREATE TABLE posts (
  post_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL REFERENCES users(user_id),
  text          TEXT CHECK (char_length(text) <= 2200),
  visibility    VARCHAR(20) NOT NULL DEFAULT 'public',
                -- 'public' | 'followers_only' | 'deleted'
  like_count    BIGINT NOT NULL DEFAULT 0,
  comment_count BIGINT NOT NULL DEFAULT 0,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at    TIMESTAMPTZ   -- soft delete; NULL = not deleted
);

-- Critical index for fan-out worker: "who posted this and when?"
CREATE INDEX idx_posts_user_created ON posts(user_id, created_at DESC)
  WHERE deleted_at IS NULL;

-- For celebrity pull: recent posts by a specific user
CREATE INDEX idx_posts_created ON posts(created_at DESC)
  WHERE deleted_at IS NULL AND visibility = 'public';

-- Full-text search on post text (optional, future use)
CREATE INDEX idx_posts_text_fts ON posts
  USING gin(to_tsvector('english', COALESCE(text, '')));
```

### 5.3 Post Media Table

```sql
CREATE TABLE post_media (
  media_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  post_id       UUID REFERENCES posts(post_id),
  user_id       UUID NOT NULL REFERENCES users(user_id),
  media_type    VARCHAR(10) NOT NULL CHECK (media_type IN ('image', 'video')),
  storage_key   VARCHAR(500) NOT NULL,  -- S3 object key (internal)
  cdn_url       VARCHAR(500),           -- CDN URL for client access
  width         INT,
  height        INT,
  duration_secs INT,                    -- for video
  sort_order    INT NOT NULL DEFAULT 0,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_media_post ON post_media(post_id, sort_order);
```

### 5.4 Follows Table

```sql
CREATE TABLE follows (
  follower_id  UUID NOT NULL REFERENCES users(user_id),
  followed_id  UUID NOT NULL REFERENCES users(user_id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (follower_id, followed_id),
  CHECK (follower_id != followed_id)
);

-- Critical index for fan-out: "who are the followers of user X?"
CREATE INDEX idx_follows_followed ON follows(followed_id);

-- For reading "who does user X follow?"
CREATE INDEX idx_follows_follower ON follows(follower_id);
```

### 5.5 Likes Table

```sql
CREATE TABLE post_likes (
  post_id    UUID NOT NULL REFERENCES posts(post_id),
  user_id    UUID NOT NULL REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (post_id, user_id)
);
-- Like count is tracked in posts.like_count via Redis batch updates.
-- This table is the durable source of truth but NOT queried on the hot path.
```

---

## Part 6: Fan-Out on Write (Push Model)

### 6.1 What Fan-Out on Write Means

When User A posts, immediately write that post's ID into every follower's pre-computed
feed cache. By the time followers load their feed, all the work is done.

```
FAN-OUT ON WRITE FLOW
======================

  User A posts "Hello world" (has 500 followers, is NOT a celebrity)
       │
       ▼
  1. Post Service saves post_id="post_abc" to PostgreSQL
  
  2. Post Service publishes to Kafka:
     { event: "new_post", post_id: "post_abc", user_id: "u_A",
       created_at_epoch: 1719310800000 }
  
  3. Fan-out Worker picks up the Kafka message:
     
     a. Fetch A's follower list:
        SELECT follower_id FROM follows WHERE followed_id = 'u_A'
        (returns 500 follower IDs)
     
     b. For each follower_id in the list:
        pipeline:
          ZADD feed:{follower_id} 1719310800000 "post_abc"
          ZREMRANGEBYRANK feed:{follower_id} 0 -201  ← trim to 200
     
     c. Pipeline all 500 ZADDs in one Redis round-trip batch
  
  4. Total writes: 500 Redis writes
     Time: ~5ms (pipeline batch)
  
  Result: all 500 followers now have "post_abc" at the top of their feed cache.
```

### 6.2 Why Push Works for Normal Users

For a user with 500 followers:
- Post triggers 500 Redis ZADD commands (pipelined: ~5ms)
- Feed reads: O(1) — ZREVRANGE on pre-computed sorted set
- No database involvement on the read hot path

This is the architecture Instagram uses for the vast majority of accounts.

### 6.3 The Celebrity Problem

User B has 10 million followers. They post one photo.

- Fan-out: 10M Redis writes
- At 100,000 Redis writes/second: 100 seconds of fan-out work
- All 10M followers are loading their feeds and not seeing the post yet
- The fan-out queue backs up; posts from other users also get delayed

Fan-out on write breaks for celebrities. The solution is in Part 8 (hybrid model).

### 6.4 Brainstorming Q&A — Part 6

**Q: What if the fan-out worker crashes midway through fanning out a post?**

The Kafka message remains unacknowledged. After the visibility timeout, another
worker picks it up and fans out again. ZADD is idempotent: posting the same post_id
at the same timestamp to a follower who already received it just updates the score
to the same value — no effect. For followers who hadn't received it yet, they get it
now. At-least-once Kafka delivery + idempotent ZADD = safe, correct recovery.

**Q: The fan-out of a single very popular post takes 100 seconds. Does this block
other posts from being fanned out during that time?**

No — the Kafka topic has many partitions, and there are many fan-out workers. Each
worker handles one Kafka partition. While one worker is busy fanning out the celebrity
post, other workers handle fan-out for other posts on other partitions. The queue depth
for that celebrity's partition grows temporarily, but normal users' posts (on other
partitions) are unaffected. This is exactly why we use a queue + worker pool rather
than inline synchronous fan-out.

---

## Part 7: Fan-Out on Read (Pull Model)

### 7.1 What Fan-Out on Read Means

No pre-computation. When User C loads their feed, query all the users they follow
and collect their recent posts at read time.

```
FAN-OUT ON READ QUERY
======================

  User C loads feed:

  SELECT p.post_id, p.user_id, p.text, p.created_at
  FROM posts p
  WHERE p.user_id = ANY(
    SELECT followed_id FROM follows WHERE follower_id = 'u_C'
  )
  AND p.created_at > NOW() - INTERVAL '7 days'
  ORDER BY p.created_at DESC
  LIMIT 20;
```

### 7.2 When Pull Is Better: Celebrity Accounts

Celebrity A has 10M followers. When they post:
- Pull model: 0 writes at post time
- When a follower reads their feed: fetch celebrity A's last 20 posts from DB

This is the read-time cost: one small query per celebrity followed. If a viewer
follows 3 celebrities, that's 3 extra queries at read time — manageable.

Pull is expensive for regular users following hundreds of people, but cheap for
celebrities (their data flows to follower feeds only at read time, not write time).

### 7.3 Why Pure Pull Fails for Regular Users

For a user following 500 normal people, pure pull:
- 500 separate queries or one large IN clause
- Sort + merge from 500 sources
- This hits the database on every feed load for every DAU

With 10M DAU × 20 feed loads/day = 200M such queries per day on peak PostgreSQL —
far too many. This is the "query that kills the database" from Part 1.1.

---

## Part 8: The Hybrid Approach (The Correct L5 Answer)

### 8.1 Combine Push and Pull

The correct architecture: a hybrid model keyed on follower count.

```
HYBRID FAN-OUT DECISION TREE
==============================

  CELEBRITY_THRESHOLD = 5,000 followers (configurable)

  WHEN A POST IS CREATED:
  
  if author.follower_count <= CELEBRITY_THRESHOLD:
    → Fan-out on WRITE: Kafka → worker → ZADD to each follower's Redis feed
  else (author is a celebrity):
    → Skip fan-out. Save post to DB only.
    → Update celebrity post cache: LPUSH celeb_posts:{user_id} {post_id}
                                   LTRIM celeb_posts:{user_id} 0 99  (keep 100)

  WHEN FEED IS READ:
  
  1. Load pre-computed feed from Redis (covers all non-celebrity posts):
     ZREVRANGE feed:{user_id} 0 199  → up to 200 post IDs
  
  2. Identify followed celebrities (cached per viewer, TTL 1 hour):
     Key: viewer_celebrities:{user_id}
     Value: [celebrity_user_id_1, celebrity_user_id_2, ...]
  
  3. For each followed celebrity: fetch their recent posts
     LRANGE celeb_posts:{celeb_user_id} 0 19  → last 20 post IDs
  
  4. Merge: interleave celebrity + pre-computed posts by timestamp
     (sort a combined list of up to 200 + N*20 items, return top 20)
  
  5. Fetch post details for the top 20 post IDs → serve response
```

### 8.2 Why This Works

- **Regular users** (99.9% of accounts): push fan-out, O(1) feed reads
- **Celebrity accounts**: no fan-out cost, posts fetched at read time
- **Merge cost**: bounded — if viewer follows 5 celebrities × 20 posts = 100 extra posts
  to merge with 200 pre-computed posts. O(300 log 300) sort — negligible, < 1ms.
- **Celebrity identification cache**: the list of "which users I follow are celebrities"
  is cached per viewer. Rebuilding it (on miss) requires one small DB query. TTL 1 hour
  since celebrity status changes rarely.

### 8.3 Intern → Staff Progression: Fan-Out

**Intern**: "When someone posts, update all their followers' feeds."

**L3**: "Fan-out on write: when a post is published, push the post ID to each follower's
Redis sorted set via an async Kafka worker. Feed reads are O(1)."

**L4**: "Fan-out on write breaks for celebrities — 10M followers = 10M Redis writes per
post. Use fan-out on read for high-follower accounts: don't push, fetch at read time.
Regular users get push; celebrities get pull."

**L5**: "Hybrid model. Regular users (≤ 5K followers) get push fan-out via async Kafka
workers. Celebrities skip fan-out — their posts go to a dedicated celebrity post cache
(Redis list, capped at 100). At feed read time, the serving layer identifies followed
celebrities (cached per viewer, TTL 1h), fetches their recent posts, and merges with the
pre-computed feed. Merge is bounded: typical user follows ≤ 5 celebrities × 20 posts
= 100 additional items to sort — O(300 log 300), negligible. The celebrity threshold
(5,000 followers) is configurable — tune based on fan-out worker capacity and read
latency budget."

---

## Part 9: Timeline Storage Design

### 9.1 Redis Sorted Set per User

The feed cache for each user is a Redis Sorted Set (ZSET):

```
REDIS DATA MODEL
=================

  Key:    feed:{user_id}
  Type:   ZSET (Sorted Set)
  Score:  Unix timestamp in milliseconds (post.created_at as epoch ms)
  Member: post_id string

  Example (most recent post has highest score):
  feed:user_alice → {
    "post_ghi": 1719310800000,   ← 2026-06-25 10:00:00 UTC
    "post_def": 1719307200000,   ← 2026-06-25 09:00:00 UTC
    "post_abc": 1719303600000,   ← 2026-06-25 08:00:00 UTC
    ...up to 200 entries...
  }

  Key Redis commands:
  Add new post:    ZADD feed:user_alice 1719310800000 "post_ghi"
  Trim to 200:     ZREMRANGEBYRANK feed:user_alice 0 -201
  Read top 20:     ZREVRANGE feed:user_alice 0 19
  Paginate:        ZREVRANGEBYSCORE feed:user_alice {cursor_ts} -inf LIMIT 0 20
```

### 9.2 Post Detail Cache (Separate from Feed Cache)

The feed cache only stores post IDs. Post content (text, author, like count) is cached
separately by post ID:

```
REDIS POST DETAIL CACHE
=========================

  Key:   post:{post_id}
  Type:  Hash (HSET)
  TTL:   1 hour (refresh on read to extend TTL)
  
  Fields:
    user_id        - author's user ID
    username       - author's username (denormalized for fast serving)
    avatar_url     - author's avatar CDN URL
    text           - post text
    media_urls     - JSON array of CDN URLs
    like_count     - current like count (may be stale by up to 1 min)
    comment_count  - current comment count
    created_at     - ISO 8601 timestamp

  Lookup flow:
  1. Get 20 post IDs from ZREVRANGE
  2. Pipeline 20 HGETALL post:{post_id} commands to Redis
  3. For any cache miss: SELECT from PostgreSQL, HSET into cache
  4. Return the hydrated post objects
```

**Why store author info in the post cache (denormalization)?**
Fetching the author's username and avatar for each of 20 posts would require 20 extra
reads (or a JOIN). Denormalizing username and avatar_url into the post cache avoids
this. The downside: if a user changes their username, the post cache shows stale names
until TTL expires (1 hour). This is acceptable — users change usernames rarely.

### 9.3 Why 200 Posts Per Feed Cache

200 posts per user covers approximately 3-7 days of feed for most active users.

Storage estimate:
- 100M users × 200 entries × 60 bytes/entry (post_id string + score + ZSET overhead)
- = 100M × 200 × 60 = 1.2 TB of Redis memory
- Across a Redis Cluster of 10 nodes × 128 GB RAM = 1.28 TB capacity
- This fits, but is tight — tune down to 100 posts if memory is constrained

Users who scroll past their 200 cached posts (rare — most users don't scroll that far)
fall back to a direct database query. This is an infrequent code path that doesn't need
to be fast.

### 9.4 Brainstorming Q&A — Part 9

**Q: Should you store full post content in the feed cache rather than just post IDs?**

No. Storing full post objects in each follower's feed cache creates a serious update
problem: when a post's like count changes (every few seconds for popular posts), you'd
need to update it in every follower's feed cache entry — potentially millions of writes.
Storing only the post ID means: like count changes update one place (the post detail
cache at `post:{post_id}`). The feed cache holds stable, immutable IDs. The post detail
cache holds mutable content with its own TTL. This separation is the key design insight.

**Q: What happens when a user comes back after 2 weeks away?**

Their Redis feed cache has expired or is stale. The fan-out worker was writing to their
feed the whole time they were away, so the cache may still have recent posts (Redis TTL
is not set on feed caches in our design — they live indefinitely, bounded only by entry
count). If their feed cache is empty (account was inactive, Redis evicted the key),
fall back: query PostgreSQL directly for recent posts from followed users. This is the
"cold start" path — slower but handles returning users correctly.

---

## Part 10: Cursor-Based Pagination

### 10.1 Why Offset Pagination Fails at Scale

The naive approach: `LIMIT 20 OFFSET 40` for page 3.

**Problem 1 — Skipped rows at scale**: The database must count 40 rows before
returning anything. At OFFSET 10,000: scan 10,000 rows, return 20. O(N) scan.

**Problem 2 — Duplicate content on scroll**: Between page 1 and page 2 loads,
3 new posts arrive at the top of the feed. All existing posts shift down by 3 positions.
Page 2 (OFFSET 20) now starts 3 posts early — the user sees 3 posts they already saw
at the bottom of page 1. Broken user experience.

Cursor-based pagination solves both problems.

### 10.2 Cursor Design

A cursor encodes the exact position in the sorted set:

```
CURSOR-BASED PAGINATION DESIGN
================================

  Cursor = { ts: <timestamp_of_last_seen_post>,
             pid: <post_id_of_last_seen_post> }
  
  Encoded: base64(JSON.stringify(cursor))
  
  FIRST PAGE REQUEST:
  GET /api/v1/feed?limit=20
  
  Server: ZREVRANGE feed:{user_id} 0 19
  → Returns 20 post IDs
  → Last post in the page: post_abc, ts=1719303600000
  → Encode cursor: base64('{"ts":1719303600000,"pid":"post_abc"}')
  → Return posts + next_cursor
  
  SECOND PAGE REQUEST:
  GET /api/v1/feed?limit=20&cursor=eyJ0cyI6MTcx...
  
  Server: decode cursor → {ts: 1719303600000, pid: "post_abc"}
  Server: ZREVRANGEBYSCORE feed:{user_id} (1719303600000 -inf LIMIT 0 20
          (the "(" means exclusive — don't include the cursor's own timestamp)
  → Returns next 20 post IDs with score < cursor_ts
  
  ADVANTAGE:
  New posts arriving at the top of the feed don't affect the cursor position.
  Page 2 always starts exactly where page 1 ended, regardless of new arrivals.
  
  DISADVANTAGE:
  Cannot jump directly to "page 10" — must paginate sequentially.
  This is fine for infinite scroll (the dominant mobile UX pattern).
```

### 10.3 Handling Timestamp Ties

Two posts with the same millisecond timestamp (rare but possible in a distributed
system). The cursor must be unambiguous even if scores tie.

Solution: use (timestamp, post_id) as a compound cursor. On the next page fetch:
```
ZREVRANGEBYSCORE feed:{user_id} {cursor_ts} -inf LIMIT 0 {limit+10}
→ Filter out post_id <= cursor_pid for entries with score == cursor_ts
→ Trim to requested limit
```

At L5: mentioning "handle timestamp ties by including post_id in cursor" is sufficient
depth.

---

## Part 11: Basic Feed Ranking

### 11.1 Reverse-Chronological Is the L5 Default

For L5: implement reverse-chronological order (newest post first). This is correct,
produces a well-understood feed, and maps directly to the Redis ZSET with timestamp
as score.

State this explicitly in the interview: "I'm designing reverse-chronological. If ranking
is needed, that requires a separate scoring service — I'll scope it out but can describe
it if you want."

### 11.2 Simple Engagement Boost (If Asked)

If the interviewer asks "how would you add basic ranking?":

```
SIMPLE ENGAGEMENT SCORE
========================

  effective_timestamp = created_at_epoch
                      + (like_count × LIKE_WEIGHT)
                      + (comment_count × COMMENT_WEIGHT)

  LIKE_WEIGHT    = 10 seconds  (one like = post appears 10s newer in rankings)
  COMMENT_WEIGHT = 30 seconds  (one comment = post appears 30s newer)

  The score stored in the ZSET = effective_timestamp, not raw created_at.
  
  Limitation: the score is computed at fan-out time (write time). Like counts
  change after fan-out. The cached ZSET score becomes stale.
  
  Simple fix: re-score top posts periodically (every hour, a background job
  fetches like counts for posts in feed caches and updates their ZADD scores).
  This is "eventual ranking" — scores drift to correct values over time.
```

### 11.3 ML Ranking (Out of L5 Scope, Mention Briefly)

Real Instagram/TikTok ranking uses a multi-stage ML pipeline:
1. Retrieval: get 200 candidate posts per user
2. Feature extraction: user features + post features + contextual features
3. Scoring: ML model predicts probability of engagement (like, comment, share, video watch)
4. Reranking: sort 200 candidates by predicted engagement, return top 20

At L5: "ML ranking is the production answer for maximizing engagement. It requires a
feature store, model training pipeline, and online serving infrastructure. I'd design
the feed serving layer to support a pluggable ranking function — initially returning
reverse-chronological order, later calling a ranking service."

---

## Part 12: Media Handling

### 12.1 Pre-Upload Flow

Clients upload media directly to S3 using presigned URLs — not through your API servers.

```
MEDIA UPLOAD FLOW
==================

  1. Client: POST /api/v1/media/upload-url
     Request: { media_type: "image", file_size_bytes: 2048000 }
     Response: {
       media_id: "media_abc123",
       upload_url: "https://bucket.s3.amazonaws.com/uploads/media_abc123?X-Amz-Signature=...",
       expires_in_seconds: 3600
     }
  
  2. Client uploads directly to S3:
     PUT {upload_url}   [binary image data]
  
  3. Client creates post with media reference:
     POST /api/v1/posts
     { text: "...", media_ids: ["media_abc123"] }
  
  4. Post Service validates:
     - media_abc123 exists in S3
     - media_abc123 belongs to this user (not someone else's upload)
     Then saves post + media record to DB.
  
  5. Background job (triggered by S3 event or post creation):
     - Resize image: original → 1080px, 540px (thumbnail), 270px (microthumbnail)
     - Store at deterministic CDN paths
     - Update post_media.cdn_url
```

### 12.2 Why Presigned URLs

Routing upload bytes through your API servers:
- Uses your API server bandwidth (expensive at scale)
- Requires API servers to buffer gigabytes of video uploads
- Creates a single bottleneck for all media uploads

Direct S3 uploads:
- Bytes go directly client → S3 (bypassing your servers)
- Your servers only handle metadata (media_id, URL generation, validation)
- S3 can receive uploads at any throughput without affecting your API servers

---

## Part 13: Scaling

### 13.1 Daily Write Volume

```
FAN-OUT WRITE SIZING
=====================

  5M posts/day × average 200 followers × 1 ZADD = 1B Redis writes/day
  = ~11,600 Redis writes/second average
  Peak (morning rush, 5× average): 58,000 writes/second

  Redis pipeline efficiency: 1,000 ZADDs per pipeline = 58 pipeline calls/second
  at peak. Each pipeline call < 5ms. Well within single Redis instance capacity.

  Fan-out workers:
  Each worker fans out at ~5,000 ZADDs/second (pipelined, 200 followers × 25 posts/sec)
  At peak 58,000 writes/second: ~12 workers needed
  Provision 20-30 workers for headroom + failover
```

### 13.2 Daily Read Volume

```
FEED READ SIZING
=================

  10M DAU × 20 feed loads/day = 200M feed reads/day = 2,315 feed reads/second avg
  Peak: ~10,000 feed reads/second

  Per feed read:
    ZREVRANGE (1 Redis call): < 1ms
    HGETALL × 20 post details (pipelined): < 5ms
    Celebrity merge (optional, < 100ms for 5 celebrities × 20 posts): < 3ms
    JSON serialization: < 1ms
    Total server-side: < 10ms

  API servers: 10,000 RPS / 2,000 RPS per server = 5 servers (provision 8-10)

  Redis total ops: 10,000 RPS × 21 commands (1 ZREVRANGE + 20 HGETALL) = 210,000 ops/sec
  Redis Cluster: 3-5 shards handles this comfortably
```

### 13.3 Database Scaling

At L5 (100M users, 500M posts):
- PostgreSQL with proper indexes on (user_id, created_at) handles the fan-out worker reads
  (fetching follower lists) and celebrity post fetches
- Read replicas absorb profile page / history queries
- The feed serving hot path does NOT hit PostgreSQL (Redis only) — this is the key
- PostgreSQL is only on the path for: cold starts, cache misses, writes, admin

When sharding becomes necessary (> 1B users):
- Shard posts and follows by user_id (same shard = local queries)
- Cross-shard fan-out is handled by the fan-out worker routing layer

---

## Part 14: Interview Application

### 14.1 The 45-Minute Framework

```
TIMING FOR "DESIGN A NEWS FEED"
=================================

  0-5 min:   Clarify requirements
             "Instagram-style or Twitter-style? Ranked or reverse-chron?
              Max followers? Single region? Stories/reels in scope?"
             
  5-10 min:  Scale estimation
             "100M users, 10M DAU, 5M posts/day, avg 200 followers..."
             "1B ZADD/day, 200M feed reads/day"
             
  10-20 min: High-level design
             "Two paths: write (fan-out workers → Redis) and read (Redis → serve)"
             Draw the architecture diagram with both paths labeled.
             
  20-30 min: Deep dive — fan-out strategy
             Explain push vs. pull. Introduce the celebrity problem.
             Describe the hybrid: threshold, push for regular, pull for celebrity.
             
  30-38 min: Deep dive — data model + pagination
             Redis ZSET for feed cache. Post ID only (not full content).
             Cursor pagination vs. offset — why cursor wins.
             
  38-45 min: Scaling + failure handling + open questions
             Fan-out worker failure (Kafka retry, idempotent ZADD).
             Memory estimate for Redis feed cache.
             "If more time: algorithmic ranking, multi-region, post deletion cleanup."
```

### 14.2 Common Mistakes

**Mistake 1: Not knowing the fan-out problem**
"Just query followed users' posts when loading the feed" — naive approach. An interviewer
asks "what's the latency if a user follows 500 people each with 1,000 posts?" Will expose
the O(500K) scan immediately. Always pre-compute the feed.

**Mistake 2: Forgetting the celebrity problem**
"Fan-out on write for everyone" — misses the celebrity storm (10M followers = 10M writes).
This is one of the most famous problems in news feed design. Interviewers at Meta/Twitter
specifically probe for it.

**Mistake 3: Using offset pagination**
`LIMIT 20 OFFSET 40` — O(N) scans and duplicate posts on scroll. Always use cursor-based
pagination for feeds.

**Mistake 4: Storing full post content in each follower's feed cache**
Means one like update triggers thousands of cache updates. Store post IDs only; keep
mutable content in a shared post detail cache.

**Mistake 5: Not stating eventual consistency**
The hybrid fan-out model has eventual consistency for celebrity posts. Say it explicitly:
"Celebrity posts appear in follower feeds within seconds of the next feed load, not
instantly. This is eventual consistency, which is acceptable for a social feed."

---

## Part 15: Pre-Interview Drill

### 15.1 Four Concepts to Explain in 60 Seconds Each

**1. Fan-out on write vs. fan-out on read:**
"Fan-out on write: when User A posts, immediately push A's post ID to every follower's
Redis feed cache. Feed reads are O(1). Drawback: a user with 10M followers triggers 10M
Redis writes per post — the fan-out storm. Fan-out on read: no write-time work; when a
follower loads their feed, fetch followed users' recent posts on demand. Cheaper to write,
slower to read. Production systems use hybrid: fan-out on write for users below a follower
threshold, fan-out on read for celebrities above it."

**2. Redis ZSET feed cache:**
"Each user has a Redis sorted set as their pre-computed feed. Key: `feed:{user_id}`.
Score: post creation timestamp in epoch milliseconds. Members: post IDs. To add a new
post: ZADD with timestamp as score. To read the feed: ZREVRANGE returns the top N most
recent post IDs. The set is capped at 200 entries — ZREMRANGEBYRANK evicts the oldest
post when a new one arrives. This gives O(log 200) inserts and O(20) page reads."

**3. Cursor-based pagination:**
"Offset pagination (`LIMIT 20 OFFSET 40`) has two problems: O(N) database scans at large
offsets, and duplicate posts when new items arrive between page requests. Cursor pagination
uses the last seen item as the position marker: cursor = {timestamp, post_id} of the last
post on the current page. The next page fetches posts with score strictly less than the
cursor timestamp. O(log N) Redis query, stable under concurrent inserts, natural fit for
infinite scroll."

**4. The celebrity threshold:**
"Define a threshold (e.g., 5,000 followers). When a user's follower count exceeds this,
they are flagged as a celebrity in the database. The fan-out worker checks this flag: if
celebrity, skip fan-out. The feed serving layer caches each viewer's list of followed
celebrities (TTL: 1 hour). At read time, celebrity posts are fetched from a celebrity
post cache and merged with the pre-computed feed by timestamp. The threshold controls the
trade-off between write cost (fan-out) and read cost (merge). Higher threshold = more
fan-out writes; lower threshold = more merge work at read time."

### 15.2 Self-Check

**Architecture:**
- [ ] Draw the write path: post → Kafka → fan-out worker → Redis ZADD
- [ ] Draw the read path: API → Redis ZREVRANGE → hydrate post details → merge celebrity → response
- [ ] Explain the two-path hybrid (push for regular users, pull for celebrities)

**Data model:**
- [ ] What Redis data type stores each user's feed? Key pattern? Score? Member type?
- [ ] Why store only post IDs (not full content) in the feed cache?
- [ ] What Redis command caps the feed at 200 entries?
- [ ] What is the post detail cache key pattern and TTL?

**Pagination:**
- [ ] Two problems with offset pagination for feeds?
- [ ] What fields does a feed cursor contain?
- [ ] What Redis command executes cursor-based pagination?

**Trade-offs:**
- [ ] What is the fan-out storm and when does it occur?
- [ ] Is feed consistency strong or eventual? Is that acceptable?
- [ ] How do you handle post deletion from feed caches?
- [ ] What is the Redis memory cost for 100M users × 200 posts × 60 bytes?

---

## Part 16: Capacity Estimation Deep Dive

### 16.1 Write Volume: Fan-Out Worker Sizing (Walk-Through)

The fan-out worker is the most write-intensive component. Size it carefully.

```
FAN-OUT WRITE ESTIMATION
=========================

  INPUTS:
  - 5M new posts per day
  - Average followers per non-celebrity poster: 200
  - 95% of posters are non-celebrities (below threshold)

  DAILY ZADD WRITES:
  5M posts × 0.95 × 200 followers = 950M ZADD operations per day
  + ZREMRANGEBYRANK calls (same count as ZADDs, for trimming): 950M
  Total Redis writes: ~1.9B per day

  AVERAGE RATE:
  1.9B / 86,400 seconds = ~22,000 Redis writes/second average

  PEAK RATE (morning rush: 5× average, lasting 2 hours):
  22,000 × 5 = 110,000 Redis writes/second at peak

  REDIS CAPACITY:
  Single Redis instance: ~200,000 ops/second
  With pipelining (batch 1,000 ZADDs per pipeline): effective throughput triples
  → 2-3 Redis instances handle peak fan-out comfortably

  FAN-OUT WORKER COUNT:
  Each worker fans out one Kafka message at a time.
  Time per message (200 followers): 200 ZADDs × 0.1ms + Redis pipeline RTT ≈ 5ms
  Messages per second per worker: 1000ms / 5ms = 200 messages/sec
  Messages at peak: 5M posts/day × 0.95 / 86,400 × 5 (peak) ≈ 275 messages/sec
  Workers needed: 275 / 200 = 2 workers (minimum)
  Provision 10-20 for redundancy and burst headroom.
```

### 16.2 Read Volume: Feed Serving Sizing

```
FEED READ ESTIMATION
=====================

  INPUTS:
  - 10M DAU
  - Average feed loads per user per day: 20 (open app 5x/day, 4 pages each)
  - Posts per page: 20

  DAILY READ OPERATIONS:
  10M × 20 = 200M feed page loads per day
  Each page: 1 ZREVRANGE + 20 HGETALL = 21 Redis ops
  Total Redis reads: 200M × 21 = 4.2B Redis read ops per day

  AVERAGE RATE:
  4.2B / 86,400 = ~48,600 Redis read ops/second

  PEAK RATE (morning: 4× average):
  ~195,000 Redis read ops/second

  REDIS READ CAPACITY:
  Single Redis instance with read replica: ~300,000 read ops/sec
  With pipeline grouping: handle peak on 2-3 nodes

  API SERVER CAPACITY:
  Each feed request: ~10ms server processing (cache lookups + serialization)
  Each server: 1000ms / 10ms = 100 concurrent requests
  With 8 cores × 100 concurrent = 800 RPS per server
  At peak 10,000 RPS: 13 servers → provision 15-20

  TOTAL REDIS CLUSTER SIZE:
  Write ops peak: 110,000 ops/sec
  Read ops peak:  195,000 ops/sec
  Total: ~305,000 ops/sec
  Redis Cluster with 5 primary + 5 replica nodes handles this comfortably.
```

### 16.3 Storage Estimation

```
STORAGE ESTIMATE
=================

  POSTS TABLE (PostgreSQL):
  500M posts × 300 bytes average (text + metadata, no media)
  = 150 GB raw
  With 3× replication (1 primary + 2 replicas): 450 GB
  10 years of growth at 5M posts/day: 500M/year × 300B = 150 GB/year → ~1.5 TB after 10 years
  Fits on well-provisioned PostgreSQL with periodic archival of old posts.

  FOLLOWS TABLE (PostgreSQL):
  100M users × average 200 follows = 20B follow relationships
  Each row: ~40 bytes (follower_id + followed_id + created_at)
  Total: 20B × 40B = 800 GB
  Index on followed_id doubles storage: ~1.6 TB
  This is large — consider a dedicated graph store or denormalized follower count caching.

  FEED CACHE (Redis):
  100M users × 200 posts × 60 bytes/entry = 1.2 TB
  Redis Cluster: 10 nodes × 128 GB RAM = 1.28 TB capacity
  Utilization: ~94% — tight. Use 12 nodes for comfortable headroom, or reduce to 100 entries/user.

  POST DETAIL CACHE (Redis):
  Popular posts (top 10M) × 500 bytes/post = 5 GB
  Not all posts need to be in detail cache — only recently accessed ones.
  An LRU-based Redis with 10 GB allocated handles this well.

  MEDIA (S3):
  5M posts/day × 30% have images × 500 KB average processed size × 3 versions
  = 1.5M × 1.5 MB = 2.25 TB/day
  Annual: ~820 TB/year
  After 3 years: ~2.5 PB of media storage.
  
  KEY INSIGHT:
  Media storage dominates every other storage category by 100×.
  This is why media is always in object storage (S3/GCS), not a database.
  Apply lifecycle policies: hot media (< 30 days old) in S3 Standard,
  older media in S3 Infrequent Access or Glacier.
```

---

## Part 17: Operational Considerations

### 17.1 Monitoring the Feed System

```
KEY METRICS TO WATCH
=====================

  WRITE PATH:
  ┌────────────────────────────────────────────────────────────────┐
  │ Kafka consumer lag (fan-out topic): target < 100 messages      │
  │   Alert: if lag > 10,000, fan-out workers are falling behind  │
  │ Fan-out worker error rate: target < 0.01%                     │
  │ ZADD latency p99: target < 2ms                                │
  └────────────────────────────────────────────────────────────────┘

  READ PATH:
  ┌────────────────────────────────────────────────────────────────┐
  │ Feed API p50/p95/p99 latency: target p99 < 500ms              │
  │ Feed cache hit rate: target > 95%                              │
  │   Miss means: serving from DB (cold start or deleted key)     │
  │ Post detail cache hit rate: target > 90%                       │
  └────────────────────────────────────────────────────────────────┘

  DATA FRESHNESS:
  ┌────────────────────────────────────────────────────────────────┐
  │ Fan-out lag: time from post creation to visible in feed        │
  │   Target: < 5 seconds for p99                                 │
  │ Celebrity post merge lag: near-zero (read-time fetch)          │
  └────────────────────────────────────────────────────────────────┘

  REDIS HEALTH:
  ┌────────────────────────────────────────────────────────────────┐
  │ Redis memory utilization per node: alert at > 80%             │
  │ Redis keyspace stats: monitor ZSET count and avg length        │
  │ Eviction events: alert if Redis evicts feed cache keys        │
  │   (means out-of-memory; feeds for users degrade to DB fallback)│
  └────────────────────────────────────────────────────────────────┘
```

### 17.2 What Happens When Redis Goes Down

If the Redis cluster becomes unavailable:
1. Feed reads fall back to direct PostgreSQL queries (the naive approach from Part 1)
2. PostgreSQL is suddenly handling 10,000 feed queries/second — it will struggle
3. Circuit breaker: if Redis is down, return an empty feed or serve cached CDN static
   HTML of trending posts rather than hammering PostgreSQL

Mitigation before Redis outage: replicate Redis to a standby cluster. Most cloud
Redis services (ElastiCache, Redis Cloud) provide automatic failover in < 60 seconds.
Design for 60 seconds of degraded performance, not total failure.

### 17.3 Handling the Follow/Unfollow Event

**Follow event** triggers backfill:
```
When User C follows User A:
1. INSERT INTO follows (C, A)
2. Publish to Kafka: { event: "follow", follower: C, followed: A }
3. Fan-out worker:
   a. Fetch A's last 20 posts from PostgreSQL
   b. ZADD feed:{C} {post_ts} {post_id} for each of A's 20 posts
   Purpose: C immediately sees A's recent content without waiting for new posts
```

**Unfollow event** does NOT purge immediately:
- A's posts remain in C's feed cache
- They naturally age out as newer posts from others push them below the 200-entry limit
- If C explicitly says "I want to stop seeing this immediately": an async job scans
  C's Redis feed for A's post IDs and removes them (expensive, do only on explicit request)

### 17.4 Like Count Updates

Likes are high-throughput write operations on popular posts. Avoid direct DB updates.

```
LIKE COUNT UPDATE FLOW
=======================

  User clicks Like on post_xyz:
  
  1. POST /api/v1/posts/post_xyz/like → 204 immediately
  
  2. Redis INCR like_count:{post_xyz}  ← increment counter in Redis (< 1ms)
  
  3. Background job (every 60 seconds):
     For each modified post:
       count = GET like_count:{post_xyz}
       UPDATE posts SET like_count = {count} WHERE post_id = 'post_xyz'
       DEL like_count:{post_xyz}
  
  Result: PostgreSQL sees 1 UPDATE per post per minute regardless of like volume.
  Redis counter absorbs bursts (a post getting 10K likes in a minute = 10K Redis INCs,
  not 10K PostgreSQL UPDATEs).
  
  Consistency: displayed like count may lag by up to 60 seconds. Acceptable.
  The post detail cache also refreshes from Redis, so the lag is visible to all users
  simultaneously (not inconsistent across users).
```

---

## Part 18: More Brainstorming Q&A

**Q: How do you handle a user deleting their account?**

Soft delete the user record (`deleted_at`). Posts authored by the deleted user remain
in other users' feed caches (by post_id). When the feed is served and post details are
fetched, deleted-user posts return a 404 from the post detail cache. The feed service
skips those and returns the remaining posts. Hard deletion (actual data removal) runs
asynchronously: delete the user's posts, remove their entries from follower feeds,
remove from follows table. This is a background job that completes over hours/days,
not in the foreground.

**Q: How do you prevent a spammy account from flooding everyone's feeds?**

Three layers:
1. **Rate limiting at post creation**: cap posts per user per hour (e.g., 20 posts/hour
   for regular users). Implemented with a Redis counter per user per hour.
2. **Content moderation**: a separate ML model or human review queue flags high-velocity
   posts from accounts with no engagement history.
3. **Feed-level filtering**: the feed service can check a blocklist per user (users they
   have muted/blocked). Posts from muted accounts are filtered out at serve time.

**Q: What if a user follows 10,000 people (a "super fan")? Does the hybrid model work?**

Yes — the hybrid model is about the author's follower count, not the viewer's following
count. A super fan who follows 10,000 people gets all those posts pushed into their
Redis feed cache (from the 10,000 authors' fan-out workers). Their feed cache fills up
quickly — the 200-post cap means the feed only shows the most recent 200 posts across all
10,000 accounts. This may mean missing posts from infrequently-posting accounts.

For a super fan, an alternative: at read time, query PostgreSQL for recent posts from
followed accounts (the naive approach), but limit to last 1 hour. This is a "catch-up
query" for users following many accounts — cache the result for 5 minutes. The first
load after 5 minutes is slow; subsequent loads within the window are cached.

**Q: How do you handle a post going viral (getting 100K likes in 10 minutes)?**

The viral post's like count is in Redis (`like_count:{post_xyz}`). 100K INCR operations
in 10 minutes = ~167 INCR/second — well within Redis capacity. The post detail cache at
`post:{post_xyz}` shows the like_count from the last Redis flush (up to 60 seconds stale).
All viewers see the same stale count simultaneously (not inconsistent, just delayed).

The feed cache is not affected — it stores post IDs, not like counts. The viral post was
already fanned out to followers when it was published. The only change is the displayed
like count on the post detail, which updates through the batch flush.

**Q: What is the fan-out delay for a post? How do you measure it?**

Fan-out delay = time from post creation to the post appearing in all non-celebrity followers'
feeds. Measure with a synthetic probe: create a test post from a test account with 1,000
test follower accounts. Measure when each test follower's Redis feed first contains the
post ID. P50 delay target: < 1 second. P99 delay target: < 5 seconds.

This metric is critical — if the fan-out queue is backing up, users experience stale feeds.
Monitor Kafka consumer lag for the fan-out topic. If lag grows (fan-out workers can't keep
up), alert and auto-scale workers.

---

## Part 19: Interview One-Liners Cheat Sheet

When the interviewer asks a pointed question, having a crisp one-liner followed by one
sentence of reasoning signals calibration. Memorize these before your interview.

```
TOPIC → ONE-LINER + REASON
============================

FEED STORAGE MODEL
"I'd store post IDs in a Redis sorted set per user, scored by timestamp."
Why: IDs are 8 bytes each; storing full post content wastes 100× space and makes
updates (likes, edits) require invalidating every follower's cache.

FAN-OUT DECISION
"Push for regular users, pull for celebrities above ~5K followers."
Why: Pushing a new Beyoncé post to 80M followers fills Kafka and takes hours.
Pulling at read time adds only one extra DB query, acceptable for celebrities.

CURSOR PAGINATION
"Cursor = (timestamp, post_id) pair, not an OFFSET."
Why: OFFSET skips rows after sorting — O(n) and unstable under concurrent inserts.
A cursor uses ZREVRANGEBYSCORE with an exclusive lower bound — O(log n) and stable.

TIMELINE FANOUT COMPLEXITY
"Fan-out writes are O(followers) per post, not O(1)."
Why: This is the core scalability constraint. A user with 1M followers triggers 1M
ZADD operations. The hybrid model caps worst-case fan-out cost.

CONSISTENCY GUARANTEE
"News feeds are eventually consistent — a few seconds lag is acceptable."
Why: There's no semantic reason feeds must be real-time; users don't notice sub-5-second
lag. This lets us use async Kafka fan-out rather than synchronous distributed writes.

RANKING VS. REVERSE-CHRONOLOGICAL
"Default reverse-chronological; add ranking only after explicit PM ask."
Why: Ranking requires engagement signals, which requires separate infrastructure.
In an interview, scope to reverse-chron unless the interviewer probes ranking.

WHY REDIS SORTED SET
"ZSETs give O(log n) insert, O(log n) range query, and natural cap-by-rank."
Why: ZREMRANGEBYRANK is a single command that trims the set to N entries after each
insert — no separate TTL or eviction policy needed.

FOLLOW BACKFILL
"On follow, backfill the last N=20 posts from the followed user into the follower's feed."
Why: Without backfill, a new follower sees an empty feed until the followed user posts,
which looks broken. 20 posts is enough to feel populated without being expensive.
```

---

## Part 20: L5 vs L6 Calibration Table

At an L5 interview, the interviewer expects you to nail the core design. At L6, they expect
you to proactively identify second-order problems and tradeoffs the interviewer hasn't asked about.

```
DIMENSION        L5 EXPECTATION                   L6 EXPECTATION
─────────────────────────────────────────────────────────────────────────────
Core design      Fan-out hybrid + Redis ZSET        Fan-out hybrid + Redis ZSET
                 cursor pagination                  cursor pagination (same)

Tradeoff depth   Can explain why fan-out on          Quantifies the tradeoff: "A
                 write is better than read           celebrity with 50M followers
                                                     would queue 50M ZADDs/post; at
                                                     22,000 ZADDs/sec that's 37 mins
                                                     of fanout lag → unacceptable."

Failure handling Knows Redis can go down;           Has a plan: degraded mode falls
                 mentions DB fallback               back to DB with circuit breaker;
                                                     describes 60s failover window
                                                     and user impact

Observability    Can list 2-3 metrics               Defines SLOs: "Feed load p99 <
                                                     500ms, fan-out lag p99 < 5s,
                                                     cache hit rate > 95%; alert on
                                                     Kafka lag > 10K messages"

Capacity         Rough: "~200M reads/day, need       Structured: separate write vs
                 Redis cluster"                     read paths, size independently,
                                                     name specific node counts with
                                                     justification

Like count       Increments DB counter              Redis INCR pattern with 60s
                                                     batch flush to DB; explains why
                                                     direct DB hits are dangerous

Unfollow         "Remove posts from the feed"       Notes immediate purge is O(n);
                                                     chooses natural age-out strategy
                                                     with explicit purge on demand

Celebrity detect "Check follower count at write     Caches celebrity list in Redis
                 time"                              with 1h TTL; invalidates on
                                                     threshold-crossing events; async
                                                     re-classification job
─────────────────────────────────────────────────────────────────────────────
```

---

## Part 21: Stress Test Questions

These are the hardest questions an interviewer can ask about a news feed system. If you
can answer all of them, you are well-calibrated for L5.

**"What happens if the fan-out worker crashes mid-fan-out for a post with 10,000 followers?
Say it fanned out to 6,000 followers and then died."**

Answer: The Kafka message is re-processed because the consumer never committed the offset.
The fan-out worker will push to all 10,000 followers again — meaning 6,000 get the post ID
twice. Redis ZADD is idempotent when the same (score, member) pair is added: if the post
already exists at that timestamp score, ZADD just overwrites with the same value. No
duplicate posts appear in the feed. This is why we use (timestamp, post_id) as the ZADD
arguments rather than auto-incrementing IDs — idempotency falls out naturally.

**"How do you handle the case where a user's Redis feed key doesn't exist (cache miss)?"**

Answer: The feed service detects a ZRANGE on a key that returns zero results and flags it
as a cold-start miss (different from an empty feed). It falls back to querying PostgreSQL:
join the follows table with the posts table, ORDER BY created_at DESC, LIMIT 200. It then
populates the Redis ZSET with those 200 posts and sets a 7-day TTL. Subsequent reads hit
Redis. Cost: a single cold-start DB query for an infrequent user is acceptable.

**"Two posts are created at exactly the same millisecond timestamp. How does your cursor
pagination handle this without skipping or repeating either post?"**

Answer: The cursor is (timestamp, post_id), not just timestamp. The ZREVRANGEBYSCORE
query uses `LIMIT offset count` where offset skips the first N posts at the cursor
timestamp. Alternatively, store post IDs as the sort key with timestamp as a tie-breaker
in the post ID generation (use a snowflake-style ID where the high bits are timestamp and
the low bits are random). Then ZREVRANGEBYSCORE with exclusive lexicographic bound handles
exact timestamp ties correctly.

**"What if a celebrity changes status — they cross the 5,000 follower threshold? Their posts
are already in 4,999 feeds. Now they have 5,001 followers. What do you do?"**

Answer: The fan-out worker checks celebrity status at fan-out time via a cached Redis lookup
(`is_celebrity:{user_id}` with 1h TTL). When a user crosses the threshold, an async job
invalidates that key. The next post from this user will be treated as celebrity (pull model).
The previous posts already in the 4,999 feeds remain there — no need to remove them. The
transition is not atomic, but feeds are eventually consistent so this is acceptable. The
edge case of the threshold-crossing post (the one created during the transition window)
might get pushed to some followers and pulled for others. This inconsistency resolves
within 1 TTL cycle (1 hour).

---

## Part 22: Frequently Misunderstood Concepts

### 22.1 "Why Not Just Use a Database Index?"

A common mistake is to think that the right SQL index makes the naive query fast enough.

```sql
-- Naive query with index:
SELECT posts.* FROM follows
JOIN posts ON posts.author_id = follows.followed_id
WHERE follows.follower_id = {user_id}
ORDER BY posts.created_at DESC
LIMIT 20;
```

Even with an index on `follows(follower_id)` and `posts(author_id, created_at)`, this
query involves:
1. A scan of the follows table for all accounts this user follows (~200 rows)
2. For each followed account, a lookup of their recent posts (~20 rows each)
3. A merge-sort across all 4,000 candidate rows to find the top 20

At 10M DAU with 20 feed loads/day = 200M queries/day = ~2,300 QPS average, peaking at
~10,000 QPS. PostgreSQL typically handles 5,000-10,000 simple queries/second. This is at
the edge of feasibility for a single DB — and any join with a table scan will be much
slower. The result: query tail latency spikes, which means user-visible lag.

The pre-computed Redis feed avoids the join entirely. Feed read = one ZREVRANGE + N HGETALL
(pipelined). No join, no cross-user merge. That's why Redis is the correct answer, not "a
better index."

### 22.2 "What's the Difference Between Fan-Out on Write and Write-Through Cache?"

They're related but different:
- **Write-through cache**: update the cache when you update the DB, keeping them in sync.
  Used for single-entity caches (e.g., `post:{id}` is updated when post content changes).
- **Fan-out on write**: on a single write (one post), proactively populate N separate caches
  (one per follower). A 1-to-N amplification, not a 1-to-1 sync.

Fan-out on write is more aggressive and expensive. The cost is justified because the read
path (serving a feed) is far more frequent than the write path (publishing a post).

### 22.3 "Why Not Push Everything Including Celebrity Posts?"

Tempting shortcut: push all posts regardless of follower count, just add more fan-out workers.

The math kills this idea. 1M follower celebrity, posting 5 times/day:
- 5M ZADDs/day from one celebrity
- Platform has 100 such celebrities: 500M ZADDs/day from celebrities alone
- At 22,000 ZADDs/second peak capacity: 500M / 86,400 / 22,000 ≈ still feasible mathematically
- BUT: the Kafka queue would have huge bursts. If a celebrity posts during a traffic spike,
  the fan-out backlog could grow to hours.

The real problem: if you push to 80M followers simultaneously, the fan-out takes:
80M ZADDs / 22,000 per second = 3,636 seconds = ~1 hour of fan-out delay.

1-hour delay for a celebrity post to appear in follower feeds is unacceptable.
Pull-at-read-time adds < 5ms per celebrity. That's why the hybrid model exists.

---

## Part 23: Glossary of Terms Used in This Chapter

**Celebrity threshold** — The follower count above which a user switches from fan-out on
write (push model) to fan-out on read (pull model). Typical value: 5,000–100,000 followers.
Configurable via a feature flag stored in Redis; no code deploy required to change.

**Cursor-based pagination** — A pagination method where the client sends the (timestamp,
post_id) of the last item it received. The server returns items strictly before that point.
Contrast with OFFSET-based pagination, which uses a numeric offset into sorted results.

**Fan-out on read (pull model)** — The feed is not pre-computed. When a user requests
their feed, the server queries all followed accounts for recent posts and merges them at
read time. Read cost = O(following_count). Write cost = O(1). Used for celebrities.

**Fan-out on write (push model)** — When a user publishes a post, the post ID is pushed
into every follower's feed cache. Write cost = O(followers). Read cost = O(1) (just read
from cache). Used for regular users below the celebrity threshold.

**Feed cache** — A Redis Sorted Set per user (`feed:{user_id}`) containing post IDs scored
by creation timestamp. Capped at 200 entries. Trimmed after each insert via ZREMRANGEBYRANK.

**Hybrid fan-out** — The production model. Regular users (< threshold followers) use push;
celebrities (> threshold) use pull. The feed service merges both at read time.

**Post detail cache** — A Redis Hash per post (`post:{post_id}`) storing text, author,
like_count, and media URLs. TTL: 1 hour. Separates mutable content from stable feed structure.

**Soft delete** — Marking a record as deleted via a `deleted_at` timestamp rather than
removing it from the database. Allows for audit history, undo operations, and asynchronous
cleanup jobs. Used for posts and user accounts.

**ZADD** — Redis command. `ZADD key score member`. Adds a member with a score to a sorted
set. If the member already exists, updates its score. O(log N) where N = set cardinality.
Idempotent when called with the same (score, member) pair.

**ZREMRANGEBYRANK** — Redis command. `ZREMRANGEBYRANK key 0 0` removes the lowest-scoring
element. Used to cap a feed ZSET at MAX_FEED_ENTRIES after each ZADD.

**ZREVRANGEBYSCORE** — Redis command. `ZREVRANGEBYSCORE key max min LIMIT offset count`
returns members with scores between min and max, in descending order, with optional paging.
Used for cursor-based feed pagination.

---

## Part 24: SSE Brainstorming Reference

The SSE (Senior Software Engineer) framework for news feed: scope → estimate → design →
deep-dive → wrap-up. This section gives you the internal monologue and decision tree to
run during the interview.

### 22.1 Scope Clarification (First 5 Minutes)

Before drawing a single box, ask these questions. The answers determine every architectural
decision.

```
CLARIFYING QUESTION → WHY IT MATTERS
=======================================

"Is this Instagram/Facebook-style (social graph), or Twitter-style (one-directional follow)?"
  → Facebook: mutual follow. Twitter: follow without approval.
  → Affects: privacy model, whether to show posts only to mutual followers.

"How many users? What's the DAU?"
  → 10M DAU vs 100M DAU changes whether you need sharding on day one.
  → Rule of thumb: if DAU > 50M, discuss Redis Cluster with 10+ nodes upfront.

"What counts as a post? Text only, or images/videos too?"
  → Images/videos → presigned S3 URLs, CDN, no media in the DB.
  → Text only → simpler schema, smaller post sizes.

"Does the feed need to be ranked, or reverse-chronological?"
  → Ranked → defer to the end ("out of scope, we'd add a ranking service").
  → Reverse-chron → simpler, appropriate for L5.

"What's the follow scale? Do any users have millions of followers?"
  → This is the celebrity threshold question.
  → If yes: hybrid fan-out is required.
  → If no: pure fan-out on write is fine.

"What are the consistency requirements? Can a user's post take 10 seconds to appear?"
  → Strong consistency → synchronous fan-out (expensive, avoid).
  → Eventual consistency → async Kafka fan-out (the correct answer).
```

### 22.2 The Decision Tree (What to Push vs Pull)

```
NEW POST PUBLISHED
      │
      ▼
Is author's follower count > CELEBRITY_THRESHOLD?
      │
  YES │                NO
      ▼                ▼
PULL MODEL         PUSH MODEL
(fan-out on read)  (fan-out on write)
      │                │
      │                ▼
      │         For each follower:
      │           ZADD feed:{follower_id} {timestamp} {post_id}
      │           if ZCARD > MAX_FEED_ENTRIES:
      │             ZREMRANGEBYRANK feed:{follower_id} 0 0
      │
      │         Done in background via Kafka fan-out workers
      ▼
Celebrity's posts are NOT pre-pushed.
At read time: fetch celebrity's last 20 posts from post DB,
merge with Redis ZSET, re-sort by timestamp, serve unified feed.
```

### 22.3 The 45-Minute Interview Allocation

```
MINUTE 0-5:   Clarifying questions (scope above)
MINUTE 5-10:  Requirements statement + constraints summary
MINUTE 10-20: High-level design (boxes: Post Service → Kafka → Fan-out Workers → Redis)
MINUTE 20-30: Deep-dive into fan-out models + hybrid decision
MINUTE 30-37: Redis data model (ZSET), cursor pagination, post detail cache
MINUTE 37-42: Scaling + capacity rough estimates
MINUTE 42-45: Failure modes, monitoring, wrap-up

COMMON TIME SINKS TO AVOID:
- Don't spend > 5 minutes on the DB schema. List the tables, move on.
- Don't get drawn into ML ranking unless explicitly asked. Say "out of scope for L5."
- Don't explain what Redis is. Assume the interviewer knows.
- Don't debate SQL vs NoSQL for posts. Just pick PostgreSQL and justify in one sentence.
```

### 22.4 Intern → Senior Progression on This Problem

This table shows how answers to the same question should evolve with seniority. If you
find yourself giving intern-level answers in a Senior interview, you will be flagged.

```
QUESTION: "How do you build the news feed?"

INTERN ANSWER:
  "Query all posts from people the user follows, sort by time."
  Problem: Identifies the naive approach but misses the scale problem.

JUNIOR ANSWER:
  "Cache the query results so you don't hit the DB every time."
  Problem: Doesn't know what to cache or how to update the cache.

MID-LEVEL ANSWER:
  "Fan-out on write: when a post is created, push it to each follower's feed cache."
  Problem: Ignores the celebrity problem.

SENIOR (L5) ANSWER:
  "Hybrid fan-out: push for regular users (< 5K followers), pull and merge at
  read time for celebrities. Store post IDs in Redis ZSETs, scored by timestamp.
  Cursor pagination for stable infinite scroll."
  ✓ This is what an L5 is expected to produce.

STAFF (L6) ANSWER:
  Same as L5, plus: quantify the threshold, explain dynamic re-classification,
  describe the celebrity index service, handle the consistency window during
  high-fanout (Kafka lag), multi-region read path, monitoring SLOs.
```

---

## Exercises

**Exercise 1 — Threshold Sensitivity**
CELEBRITY_THRESHOLD is set to 5,000. What happens if you set it too low (500)?
What if too high (500,000)? Describe the effect on write path load and read latency.
What mechanism would you use to tune this threshold in production without a code deploy?

**Exercise 2 — Cold Start Feed**
A brand-new user signs up and follows 10 accounts. Describe the complete flow for their
first feed page: which components are hit in order, what Redis looks like after.

**Exercise 3 — Double Post Bug**
Network timeout causes a mobile client to retry `POST /posts` after it already succeeded.
How do you make post creation idempotent? Show the specific API change and DB mechanism.

**Exercise 4 — Pagination Edge Case**
A user is on page 2 of their feed (cursor = post_abc). Before they request page 3, three
new posts fan out to their Redis ZSET. Does the user skip any posts? Does any post appear
twice? Explain why cursor pagination handles this correctly while OFFSET would not.

**Exercise 5 — Cascade Delete**
User A with 100,000 followers deletes their account. Their 500 posts need to be removed
from 100,000 feeds. Describe the async job. How long does it take? What do followers
see while it runs?

**Exercise 6 — Fan-Out Queue Backup**
The fan-out Kafka topic accumulates 500,000 messages of lag. Name three possible root
causes, how to diagnose each, and recovery steps without losing messages.

**Exercise 7 — Engagement Ranking**
Add a ranked feed that promotes posts with high engagement in the first 15 minutes.
Where is the engagement signal captured? How does it reach the ranking component?
What changes to the Redis ZSET structure support this? What is the tradeoff vs. reverse-chron?

---

## Homework

**Homework 1 — Notification Service**
When User A posts, followers should receive a push notification. Design the notification
service: what event triggers it, how is the device token stored, how do you handle a user
with 50 devices across platforms? How do you prevent duplicate notifications on retry?

**Homework 2 — Multi-Region Feed**
Expand to 3 regions (US, EU, APAC). Is the follows table replicated synchronously or
asynchronously? Where does fan-out write happen? When a US user follows an APAC celebrity,
how does the fan-out work across regions? What consistency tradeoffs do you accept?

---

## KEY TAKEAWAYS

```
╔═══════════════════════════════════════════════════════════════════════════╗
║              CHAPTER 73: NEWS FEED (L5) KEY TAKEAWAYS                    ║
╠═══════════════════════════════════════════════════════════════════════════╣
║                                                                           ║
║  1. PRE-COMPUTE THE FEED — NEVER QUERY AT READ TIME                      ║
║     SELECT posts FROM following on every load kills the DB.              ║
║     Pre-compute via fan-out workers writing post IDs to Redis.            ║
║                                                                           ║
║  2. HYBRID FAN-OUT: PUSH FOR REGULAR, PULL FOR CELEBRITIES               ║
║     Push (fan-out on write): O(1) reads, O(followers) writes.            ║
║     Pull (fan-out on read): O(1) writes, O(following) reads.             ║
║     Hybrid threshold (e.g., 5K followers) handles both cases.            ║
║                                                                           ║
║  3. REDIS SORTED SET = FEED CACHE PER USER                               ║
║     Key: feed:{user_id}. Score: timestamp. Member: post_id.             ║
║     ZADD to add. ZREVRANGE to read. ZREMRANGEBYRANK to cap at 200.       ║
║     Store post IDs only — not full content.                              ║
║                                                                           ║
║  4. CURSOR PAGINATION, NOT OFFSET                                        ║
║     Offset: O(N) scans + duplicate posts on scroll.                      ║
║     Cursor = (timestamp, post_id) of last seen post.                     ║
║     O(log N), stable, infinite scroll compatible.                        ║
║                                                                           ║
║  5. ASYNC FAN-OUT VIA KAFKA                                              ║
║     Post creation returns immediately. Fan-out in background.            ║
║     Eventual consistency: new posts visible within a few seconds.        ║
║     Kafka retry + idempotent ZADD = safe failure recovery.              ║
║                                                                           ║
║  6. CELEBRITY MERGE AT READ TIME                                         ║
║     Skip fan-out for accounts > threshold.                               ║
║     Fetch celebrity posts + merge at read time. O(1) per celebrity.     ║
║     Cache viewer's celebrity list (TTL 1h) to avoid repeated DB queries.║
║                                                                           ║
║  7. POST IDs ONLY IN FEED CACHE — CONTENT IN SEPARATE CACHE             ║
║     post:{post_id} Redis hash stores text/author/like_count (TTL 1h).   ║
║     Separates mutable content from stable feed structure.                ║
║                                                                           ║
║  ONE-SENTENCE SUMMARY:                                                    ║
║  "A news feed = async fan-out workers pushing post IDs to per-user Redis ║
║   sorted sets on write, with celebrity posts merged at read time, served ║
║   via cursor-based pagination in under 500ms."                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

---

### Quantitative Problem Set

**Quantitative Exercise 1 — Fan-Out Math**
User A has 3,000 followers and posts 5 times per day. Each ZADD takes 0.1ms.
(a) How many Redis writes per day does User A's activity cause?
(b) A bug promotes User A to celebrity incorrectly. They are now on the pull model.
    How many Redis writes per day do they cause?
(c) Your platform has 500 users with > 1,000 followers and 2M with < 100 followers,
    all posting 5 times per day. Which group causes more fan-out writes?

**Quantitative Exercise 2 — Redis Memory**
100M users. 200 posts per feed. Each ZSET entry (post_id string + score) uses 60 bytes.
(a) Total Redis memory needed?
(b) Redis Cluster node size: 64 GB. How many nodes needed (at 75% utilization)?
(c) Reducing to 50 posts per user: how much memory is saved?

**Quantitative Exercise 3 — Cursor Pagination Simulation**
A feed ZSET contains: post_e:1000, post_d:900, post_c:800, post_b:700, post_a:600.
First page request (limit=2) returns: [post_e, post_d].
(a) What is the cursor value?
(b) A new post arrives with score 950 after page 1 is served. Does the user see
    it on page 2 using cursor pagination? What about with OFFSET 2?
(c) Write the ZREVRANGEBYSCORE Redis command for the second page.

**Quantitative Exercise 4 — Celebrity Threshold Trade-off**
Threshold = 5,000. Your platform has 50 users with > 5,000 followers, 500 with > 500.
For a viewer following 3 celebrities (10K, 50K, 1M followers respectively), each posting
5 times/day:
(a) Without the hybrid model (pure push): how many fan-out writes do these 3 celebrities
    cause per day across all their followers?
(b) With the hybrid model: how many writes do they cause?
(c) At read time, the viewer merges celebrity posts. Each celebrity has 20 recent posts.
    What is the total sort operation size for the merge?

---

### Implementation Homework

**Implementation Task 1 — Observe Real Feed Behavior**
Open Instagram or Twitter in a browser with developer tools open (Network tab).
Scroll through your feed.
- What API endpoint is called for the initial feed load?
- What is called when you scroll to the bottom?
- Is there a cursor / next_page_token in the response?
- How many posts come back per request?
Write a paragraph describing what you infer about their pagination strategy.

**Implementation Task 2 — Build Mini Fan-Out**
In Python or Go, simulate a simplified fan-out system:
- Data: `feed = {}` (dict of user_id → sorted list of (timestamp, post_id))
- `def post(author_id, followers, post_id, ts)`: pushes post_id to each follower's feed
  (sorted by ts desc, max 10 entries)
- `def get_feed(user_id, limit=5)`: returns top 5 entries
- Test: 5 users, each following 3 others, each making 4 posts
- Print each user's feed. Then simulate celebrity mode for user_0 (> threshold):
  skip push, merge at get_feed time instead.

---

## What to Read Next

- **Ch78 — News Feed (Staff)**: The same system at full L6 depth. Adds celebrity index
  service, ML ranking pipeline, consistency guarantees (what happens when the fan-out
  worker is lagging), partial failure handling, and multi-region synchronization.
- **Ch72 — Video Streaming (L5)**: Media upload (presigned URLs, S3, CDN) in detail.
  The upload pipeline (chunked S3 uploads, transcoding) pairs naturally with media-heavy
  feed posts.
- **Ch75 — Typeahead (L5)**: The search box that helps users find content to post.
  Redis ZSET patterns from Ch75 (prefix lookup) are the same data structure used here
  for feed storage — the difference is only in the key schema and query pattern.
- **Ch47 — Consistent Hashing**: How the Redis Cluster shards feed keys across nodes.
  Understanding the consistent hashing ring explains which node stores `feed:{user_id}`
  and what happens during a node failure.
- **Ch48 — Consensus Deep Dive**: Kafka uses a Raft-based replication protocol. If the
  fan-out Kafka topic loses messages, understanding consensus helps diagnose what went wrong.
- **Ch45 — Replication**: PostgreSQL replication for the posts and follows tables.
  Single-region read replicas offload read traffic (follower lookups, post fetches) from
  the primary PostgreSQL instance during high-traffic fan-out events.

---

*Chapter 73 — Section 5: Senior SWE L5 Case Studies.*
*Pairs with: Ch78 (News Feed Staff), Ch72 (Video Streaming L5), Ch75 (Typeahead L5).*
*Target depth: L5 single-region. Out of scope: ML ranking, multi-region, ads personalization.*
*Core concepts: fan-out on write vs read, celebrity threshold, hybrid model, Redis ZSET,*
*cursor pagination (timestamp + post_id), Kafka async fan-out, like count INCR pattern.*
*Capacity: 10M DAU, 5M posts/day, ~950M ZADDs/day at peak, 200M feed reads/day.*
*Last updated: 2026-06-25.*

## Interview Simulation — News Feed L5

*45-minute system design interview. Phases follow the Section 2 framework: Requirements → Estimation → API → Data Model → HLD + Deep Dive.*

---

### Phase 1: Requirements (8 min)

> **Interviewer:** Design a social media news feed — something like Instagram or Twitter's home timeline. Walk me through how you'd approach this.

**Candidate:** Before I draw anything, I need to narrow the scope. A few questions. Is this a follow-based feed (I see posts from people I follow) or a recommendation-based feed (TikTok-style, algorithmically ranked)?

> **Interviewer:** Follow-based for now. Keep it straightforward.

**Candidate:** Good. What's the scale — DAU and rough post volume?

> **Interviewer:** 10 million DAU. About 5 million posts per day.

**Candidate:** What's the read-to-write ratio — how often does a typical user read their feed vs post?

> **Interviewer:** Mostly reads. Assume 20 feed loads per DAU per day.

**Candidate:** Are there any celebrity accounts — users with millions of followers? That changes fan-out behavior significantly.

> **Interviewer:** Yes. Some users have up to 10 million followers. Handle that case.

**Candidate:** SLO for feed load?

> **Interviewer:** Feed should load in under 500ms p99.

**Candidate:** Scope confirmed: follow-based feed, 10M DAU, hybrid fan-out to handle celebrities, Redis ZSET for feed storage, cursor-based pagination, 500ms p99. Skipping ML ranking, ads, multi-region. Good?

> **Interviewer:** Perfect.

*(Cross-question: scope clarity)* Calling out the celebrity case early shows you know where the hard problem is. Interviewers reward candidates who identify non-obvious edge cases before the design starts.

---

### Phase 2: Estimation (4 min)

> **Interviewer:** What are the key numbers?

**Candidate:** Posts written: 5M posts/day = ~58 posts/sec average. Peaking at 3× = ~175 posts/sec.

Fan-out writes: each post fans out to all followers. Average follower count — assume a power-law distribution, mean is about 200 followers. 5M posts/day × 200 followers = 1 billion ZADD operations/day = ~11,600 ZADDs/sec average, peaking around 35,000/sec. That's the write pressure on Redis.

Feed reads: 10M DAU × 20 reads/day = 200M feed reads/day = ~2,300 reads/sec. Much lower than writes — classic fan-out-on-write asymmetry.

Redis memory for feed storage: keep 200 posts per user. Each ZSET entry = post_id (8 bytes) + score/timestamp (8 bytes) + overhead ≈ 50 bytes. 10M users × 200 entries × 50 bytes = 100 GB. Comfortably fits in a 6-node Redis Cluster with 20 GB RAM per node, with room for growth.

> **Interviewer:** Why keep only 200 posts per user?

**Candidate:** Users rarely scroll more than 200 posts between sessions. Storing the full history in Redis wastes memory with zero user-visible benefit. Trim with `ZREMRANGEBYRANK feed:{user_id} 0 -201` after each write — keeps only the newest 200 entries. If a user wants to go back further, fall through to PostgreSQL for historical pagination.

*(Cross-question: estimation rationale)* The 35K ZADDs/sec peak is the scary number. That's what justifies the celebrity exclusion from synchronous fan-out.

---

### Phase 3: API Design (4 min)

> **Interviewer:** Show me the feed API.

**Candidate:** Two endpoints matter most: post creation and feed retrieval.

**Create a post:**
```
POST /posts
Authorization: Bearer {token}
Body: { text, media_url? }
Response: { post_id, created_at }
```

**Get feed (cursor pagination):**
```
GET /feed?limit=20&cursor={cursor}
Authorization: Bearer {token}
Response: {
  posts: [ { post_id, author_id, text, media_url, like_count, created_at } ],
  next_cursor: "1719360000_a3f9b2c1",
  has_more: true
}
```

The cursor is `{unix_timestamp}_{post_id}` — a composite cursor. Timestamp gives the ZSET score range, post_id breaks ties when two posts have the same timestamp (unlikely but possible at high volume).

On the client side: pass `cursor=null` for first load, pass `next_cursor` from the previous response for subsequent pages.

> **Interviewer:** Why not use offset-based pagination like `?page=2&per_page=20`?

**Candidate:** Offset pagination breaks under concurrent writes. If 3 new posts appear between page 1 and page 2 loads, every item shifts down in the offset index — the user skips 3 posts and never sees them. Cursor pagination uses an absolute position (the timestamp+id of the last seen post), so new inserts don't affect subsequent page loads. Critical for feeds where the underlying sorted set is live.

---

### Phase 4: Data Model (4 min)

> **Interviewer:** Walk me through the data model.

**Candidate:** Three tiers: PostgreSQL for durable source-of-truth, Redis for hot feed caches, Kafka for async fan-out.

**PostgreSQL — `posts` table:**
```
post_id      UUID PRIMARY KEY
author_id    UUID NOT NULL REFERENCES users(user_id)
text         TEXT
media_url    TEXT
like_count   INT DEFAULT 0
created_at   TIMESTAMPTZ NOT NULL
deleted_at   TIMESTAMPTZ   -- soft delete
INDEX (author_id, created_at DESC)
```

**PostgreSQL — `follows` table:**
```
follower_id  UUID NOT NULL
followee_id  UUID NOT NULL
created_at   TIMESTAMPTZ
PRIMARY KEY (follower_id, followee_id)
INDEX (followee_id)  ← used during fan-out to find all followers of a poster
```

**Redis — feed ZSET (per user):**
```
Key:   feed:{user_id}
Type:  Sorted Set
Score: unix timestamp of the post (float, for range queries)
Value: post_id (UUID string)
TTL:   7 days (evict inactive user feeds)
```

**Redis — post content cache (per post):**
```
Key:   post:{post_id}
Type:  Hash
Fields: author_id, text, media_url, like_count, created_at
TTL:   24 hours
```

> **Interviewer:** Why cache post content separately from the feed ZSET?

**Candidate:** Separation of concerns and memory efficiency. The ZSET stores 200 post IDs — it's tiny (50 bytes per entry). Post content can be 1 KB+ with text and URLs. If you store full post content inside the ZSET score payload, you balloon Redis memory by 20×. Separate keys let you cache content independently and expire them on different schedules. Feed page load: one `ZREVRANGEBYSCORE` to get 20 post IDs, then 20 `HGETALL` calls pipelined — Redis pipeline round-trip, sub-millisecond total.

---

### Phase 5: HLD + Deep Dive (20 min)

> **Interviewer:** Draw the full system.

**Candidate:**

```
  Creator
    │
    ▼
  API Server ──► POST /posts ──► PostgreSQL (insert post)
                                      │
                                      ▼
                               Kafka topic: post.created
                                      │
                          ┌───────────┴────────────┐
                          │     Fan-out Service     │
                          │  (Kafka consumer group) │
                          └───────────┬─────────────┘
                                      │
                    ┌─────────────────┼──────────────────┐
                    │                 │                  │
               Normal user       Celebrity poster    Celeb follower
               (< 10K followers) (≥ 10K followers)  (reads feed)
                    │                 │                  │
              ZADD to all        Skip fan-out    Fan-out-on-read:
              follower feeds      Redis feeds    merge ZSET feed +
              in Redis           (async write)   author's post list
                    │
                    ▼
              Redis Cluster
              feed:{user_id} ZSET

  Viewer
    │
    ▼
  API Server ──► GET /feed
                    │
                    ├─ ZREVRANGEBYSCORE feed:{user_id} (Redis)
                    │
                    ├─ For celebrity followees: ZREVRANGEBYSCORE
                    │  post_index:{celeb_id} (real-time merge)
                    │
                    ├─ HGETALL post:{post_id} × 20 (Redis, pipelined)
                    │
                    └─ Response: sorted, deduplicated feed posts
```

**Candidate:** The key design decision is the hybrid fan-out threshold. I set the threshold at 10,000 followers.

For normal users (< 10K followers): fan-out-on-write. The Kafka consumer reads the `post.created` event, queries `follows` for all follower IDs, and issues `ZADD feed:{follower_id} {timestamp} {post_id}` for each one. At 10K followers × 58 posts/sec, this generates 580K ZADDs/sec, which Redis Cluster handles fine.

For celebrities (≥ 10K followers): we skip writing to individual feeds. Instead, we maintain a `post_index:{user_id}` ZSET with the celebrity's own posts in chronological order. At read time, the feed service fetches this ZSET for each celebrity the viewer follows and merges the results with the viewer's regular feed ZSET. The merge is a sorted merge of N sorted lists — O(N × K) where N is the number of celebrity followees and K is the page size (20). For users following 5 celebrities, that's at most 100 Redis reads, sub-millisecond pipelined.

> **Interviewer:** How do you find the celebrity threshold efficiently at write time?

**Candidate:** Fan-out Service reads follower count from a `user_stats` Redis Hash keyed by `user:{user_id}` with a `follower_count` field. This is updated asynchronously by the Follow Service whenever a follow/unfollow happens. The Fan-out Service does: `HGET user:{poster_id} follower_count` before deciding the fan-out strategy. One extra Redis read per fan-out event — negligible cost.

> **Interviewer:** What about like counts — how do you handle high-frequency increments?

**Candidate:** Like counts are the classic write-amplification problem. A viral post can receive thousands of likes per second. If you do `UPDATE posts SET like_count = like_count + 1 WHERE post_id = ?` in PostgreSQL for each like, you create a hot row with lock contention.

Solution: `INCR post:{post_id}:likes` in Redis for the hot counter. Asynchronously flush to PostgreSQL every 30 seconds with a background job: `UPDATE posts SET like_count = $redis_count WHERE post_id = ?`. Feed reads serve the `like_count` from the Redis Hash, which reflects near-real-time counts. If a post's Redis cache expires before the flush, the PostgreSQL value is at most 30 seconds stale — acceptable for a like counter.

> **Interviewer:** What's your cache invalidation strategy when a post is deleted?

**Candidate:** Soft delete in PostgreSQL: set `deleted_at = now()`. Then: (1) delete `post:{post_id}` from Redis immediately, (2) publish a `post.deleted` Kafka event, (3) a cleanup consumer removes the post_id from all feed ZSETs using `ZREM feed:{follower_id} {post_id}` — but only for feeds that are warm (i.e., have been accessed in the last 7 days). For cold feeds (TTL expired), no action needed. At feed read time, if `HGETALL post:{post_id}` returns nil (cache miss) and PostgreSQL returns a soft-deleted record, the API layer skips that entry silently.

---

### Common Cross-Questions and Strong Answers

*(Cross-question: fan-out lag)*
> **Interviewer:** The fan-out Kafka consumer can lag during traffic spikes. A user posts and their friends don't see it for 5 minutes. Is that acceptable?

**Candidate:** For most social feeds, yes — eventual consistency within 5 seconds p99 is the norm. If you need lower latency for the poster's own followers, you can fast-path: after writing to PostgreSQL, synchronously fan-out to followers who are online right now (check presence service). All other followers get the async Kafka path. This limits synchronous fan-out to a small set (maybe 5% of followers are concurrently online), keeping p99 write latency under 100ms.

*(Cross-question: Redis failure)*
> **Interviewer:** What happens if the Redis Cluster goes down?

**Candidate:** Feed reads fall back to PostgreSQL. The feed service has a fallback query: `SELECT p.* FROM posts p JOIN follows f ON p.author_id = f.followee_id WHERE f.follower_id = ? ORDER BY p.created_at DESC LIMIT 20`. This is slower (100-300ms vs 5ms for Redis) but correct. PostgreSQL has indexes on `(followee_id)` and `(author_id, created_at DESC)` to make this feasible. Graceful degradation: Redis down → slower feed, not broken feed.

*(Cross-question: ZSET ordering)*
> **Interviewer:** You use timestamp as the ZSET score. What if two posts have the exact same timestamp?

**Candidate:** Redis ZSET with equal scores orders by lexicographic key (the post_id value). This is deterministic but arbitrary — which is fine. Users don't notice 1ms ordering differences. If you want strict ordering, use a composite score: `timestamp * 1e6 + sequence_number`, where sequence_number is a per-user monotonic counter from PostgreSQL. This guarantees uniqueness and chronological order at millisecond granularity.

*(Cross-question: cold start)*
> **Interviewer:** A user signs up and follows 50 accounts. Their feed ZSET is empty. How do you populate it?

**Candidate:** Backfill job triggered on first feed load: for each of the 50 followees, fetch the latest 10 posts from PostgreSQL and ZADD them to `feed:{user_id}`. That's 50 × 10 = 500 ZADD operations — sub-second in Redis. Trim to 200 entries. Mark the feed as initialized with a `feed_initialized:{user_id}` Redis key so the backfill only runs once. The first feed load is slightly slower (backfill is synchronous), but all subsequent loads are fast from cache.

*(Cross-question: cursor stability)*
> **Interviewer:** What if a post is deleted between page 1 and page 2 of the same feed session?

**Candidate:** The cursor points to a timestamp+post_id. On page 2, the backend queries `ZREVRANGEBYSCORE feed:{user_id} {cursor_timestamp} -inf LIMIT 20`. If the next post in that range was deleted, `HGETALL post:{post_id}` returns nil, and the API layer skips it and fetches the next one. In the worst case, a full page of deletions means fetching page 3 data to fill page 2 — the API handles this with a retry loop up to 3 depths before returning a partial page. Practically, deletions are rare enough that this edge case never triggers.

---

<!-- END OF CHAPTER 73 -->
<!--
  Scope: L5 single-region. Fan-out hybrid model. Skip: ML ranking, multi-region, ads.
  Key concepts: fan-out on write vs read, celebrity threshold, Redis ZSET, cursor pagination.
  Core data structures: Redis ZSET (feed:{user_id}), Redis Hash (post:{post_id}).
  Core commands: ZADD, ZREVRANGEBYSCORE, ZREMRANGEBYRANK, HGETALL, INCR.
  Core infra: Kafka fan-out topic, PostgreSQL (users/posts/follows), Redis Cluster.
  SLOs: feed load p99 < 500ms, fan-out lag p99 < 5s, cache hit rate > 95%.
  Capacity: 10M DAU / 5M posts/day / 950M ZADDs/day / 200M feed reads/day / 1.2TB Redis.
  L5 interview target: nail hybrid fan-out + ZSET model + cursor pagination in 45 minutes.
  Written for: Google L5 / Senior SWE system design interview preparation, single-region scope.
-->
