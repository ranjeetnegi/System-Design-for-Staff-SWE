# Chapter 61f: Leaderboard System — Real-Time Rankings at Scale

> A leaderboard is deceptively simple: sort users by score, show the top 10.
> At 10 million concurrent players, updating scores 10 times per second each,
> you can't sort 10 million numbers on every page load. You need a data structure
> that keeps the ranking pre-computed.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

Leaderboard design is asked at gaming companies (Riot, Epic, Zynga, EA),
social platforms (Duolingo streaks, Strava segment rankings), and any product
with rankings or competitive elements. It teaches Redis sorted sets (ZSET) —
one of the most useful data structures in system design interviews.
Also directly applicable to "design a top-K trending topics" question (Twitter/X).

---

## Planned Content

### Part 1: Requirements and Scale
- Show global top-100 players by score; show a player's own rank and score
- Score updates happen frequently (game events, level completions, purchases)
- Functional: update score, get top-N globally, get rank of a specific player
- Non-functional: < 100ms read latency, < 200ms write latency, eventual consistency OK for display
- Scale: 10M daily active users, 100K score updates/sec, top-100 read 10K times/sec
- Variants: global all-time, weekly, daily, friends-only (scoped leaderboard)

### Part 2: Why a Database Alone Fails
- Naive: SELECT user_id, score FROM users ORDER BY score DESC LIMIT 100
- Problem 1: full table sort on 10M rows on every read — too slow
- Problem 2: getting user's rank requires COUNT(*) WHERE score > user_score — also full scan
- Indexes help but still O(log N) per update and O(1) per read isn't achievable
- The right tool: Redis Sorted Set (ZSET) — O(log N) add, O(log N) rank query

### Part 3: Redis ZSET — The Core Data Structure
- ZADD leaderboard <score> <user_id> — add or update score, O(log N)
- ZREVRANK leaderboard <user_id> — get 0-indexed rank (0 = highest), O(log N)
- ZREVRANGE leaderboard 0 99 WITHSCORES — get top 100 with scores, O(log N + 100)
- ZINCRBY leaderboard <delta> <user_id> — increment score atomically, O(log N)
- Internal structure: skip list + hash map — skip list for ordered rank, hashmap for O(1) score lookup
- Memory: 10M users × ~50 bytes each = 500MB — fits in a Redis instance

### Part 4: System Architecture
- Write path: game event → score-update service → ZINCRBY on Redis ZSET + write to DB
- Read path: top-N request → Redis ZREVRANGE → return; rank request → Redis ZREVRANK → return
- DB (Postgres): source of truth for scores — ZSET is the cache/index layer
- Recovery: if Redis is lost, rebuild ZSET from DB (batch job, takes minutes)
- Pub/sub: score update events published to Kafka → leaderboard service updates Redis asynchronously

### Part 5: Time-Windowed Leaderboards (Daily / Weekly)
- Challenge: need separate rankings for "today" and "this week" in addition to all-time
- Option A: separate ZSET per window key — "leaderboard:daily:2024-01-15"
  - ZADD on score update to all relevant window keys
  - Expire daily keys after 25 hours (Redis TTL)
  - Simple, but 3× write amplification
- Option B: time-series of events → aggregate on read (expensive)
- Option C: scheduled job recalculates window leaderboard every 5 minutes from DB
  - Eventually consistent (up to 5 min stale) — usually fine for daily/weekly
- L5 recommendation: Option A for daily (TTL handles cleanup), Option C for weekly

### Part 6: Scoped Leaderboards (Friends / Regional)
- Friends leaderboard: sorted set per user containing only friend scores — too expensive at scale
- Better: pull friend IDs → batch ZSCORE calls → sort client-side
  - ZSCORE leaderboard <friend_id> for each friend — 100 friends = 100 calls but pipelined
- Regional: separate ZSET per region key "leaderboard:global:us-west"
- Group: separate ZSET per group_id — works at moderate scale

### Part 7: Handling Hot Users and Score Storms
- Hot user problem: one user has 1B writes/sec (bots, rank-farming)
  - Rate limit score updates per user per second
- Score storm: end-of-season event triggers 10× normal score updates
  - Write to Kafka queue, consumer updates Redis at controlled rate
  - Acceptable: slight staleness during event, exact real-time is not required
- Redis throughput: single Redis can handle ~100K ZADD/sec; shard by user_id prefix if needed

### Part 8: Interview Framework
- Clarify: global all-time only, or also daily/weekly/friends? (changes architecture significantly)
- Lead with Redis ZSET — show you know the right tool, explain why SQL alone fails
- Cover the time-window question — interviewers almost always ask this as a follow-up
- L5 bar: ZSET design, time-windowed leaderboards with TTL, rank query approach
- L6 bar: consistency model for multi-region leaderboard, sharding strategy when
  ZSET exceeds single-instance capacity, friends leaderboard without per-user ZSETs

---

## The One-Sentence Summary

> "Leaderboard = Redis ZSET (ZADD for score updates, ZREVRANK for user rank, ZREVRANGE for top-N) with DB as source of truth + time-windowed leaderboards using separate ZSET keys with TTL — the key insight is that a sorted set pre-computes the ranking so reads are O(log N) instead of O(N log N) sort on every request."

---

*Full chapter: ~2,500 lines. Section 5 — L5 / Senior SWE. Pairs with Ch33 (Redis Internals).*
