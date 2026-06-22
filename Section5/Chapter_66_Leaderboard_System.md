# Chapter 61f: Leaderboard System — Real-Time Rankings at Scale

> A leaderboard is deceptively simple: sort users by score, show the top 10.
> At 10 million concurrent players updating scores 10 times per second,
> you cannot sort 10 million numbers on every page load. You need a data
> structure that keeps the ranking pre-computed and updates it in O(log N).

---

```
+------------------------------------------------------------------+
|  INTERVIEW OVERVIEW — Leaderboard System                         |
|  Time: 45 minutes                                                |
|                                                                  |
|  Min 0-2:   Clarify scope (global only? daily/weekly? friends?) |
|  Min 2-8:   Users and use cases                                 |
|  Min 8-14:  Functional + Non-functional requirements            |
|  Min 14-19: Scale math                                           |
|  Min 19-23: Assumptions                                          |
|  Min 23-42: Architecture + deep dives                           |
|  Min 42-45: Failure modes, extensions                            |
|                                                                  |
|  The clarifying question that changes everything:                |
|  "Do you need time-windowed leaderboards (daily/weekly/monthly)  |
|   or just all-time global?" Answer changes write amplification   |
|   and architecture significantly.                                |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
|  L5 vs L6 AT A GLANCE                                           |
|                                                                  |
|  L5 (Senior SWE):                                               |
|  - Redis ZSET: ZADD, ZREVRANK, ZREVRANGE, ZINCRBY               |
|  - Why SQL alone fails (full table sort on every read)           |
|  - Time-windowed leaderboards with TTL-keyed ZSETs              |
|  - DB as source of truth, ZSET as pre-computed index            |
|  - Friends leaderboard via batch ZSCORE                          |
|                                                                  |
|  L6 (Staff):                                                     |
|  - ZSET skip list internals (why O(log N) for all ops)          |
|  - Sharding when ZSET exceeds single-instance RAM (300+ GB)     |
|  - Multi-region consistency: which region owns the ZSET?        |
|  - Score storm handling: Kafka buffering + controlled drain      |
|  - Approximate top-K for massive scale (Count-Min Sketch)       |
+------------------------------------------------------------------+
```

---

## Why This Chapter Matters

Leaderboard design is a direct depth probe into Redis sorted sets — the most useful Redis data structure in system design. Interviewers at gaming companies (Riot, Epic, EA, Zynga), social platforms (Duolingo language streaks, Strava segment rankings, LinkedIn skill badges), and any product with competitive elements ask this question.

A correct answer demonstrates: you know when SQL is the wrong tool, you know Redis ZSET semantics precisely, and you can reason about time-windowed data (daily vs weekly vs all-time) without re-sorting from scratch.

This question also generalizes to: "Design Twitter trending topics" (top-K by retweet count), "Design a live sports standings board," and "Design a real-time gaming tournament bracket."

---

## Phase 1: Users and Use Cases (Minutes 2-8)

### Clarify first — the answer changes the architecture

Ask before drawing anything:

1. "Is this global all-time only, or do you also need daily, weekly, or seasonal leaderboards?"
2. "Do you need a friends-only leaderboard (show where I rank among my friends)?"
3. "Is the ranking by a single score or a composite (kills + assists - deaths in a game)?"
4. "Does rank need to be exact or approximate? (exact: hard at 1B users, approximate: Count-Min Sketch)"

For this chapter: global all-time + daily + weekly leaderboards, with friends-only as an extension. Single score value. Exact rank required (not approximate).

### Who uses a leaderboard system?

**End users:**
- Gamers checking their global rank in a battle royale game
- Students checking where they rank on a Duolingo language streak leaderboard
- Athletes checking their Strava segment ranking (fastest mile in a city)
- Sales reps checking their quota attainment ranking vs. teammates

**Downstream systems:**
- Game event service: sends score update events (kills, level completions, purchases)
- Notification service: "You just entered the top 100!" trigger
- Analytics service: reads rank distribution for product insights
- Rewards service: reads top-N to distribute prizes (top 1,000 players get rewards)

### Core use cases

**P0 — Must have:**
- UC1: Update a player's score (add delta on game event)
- UC2: Get global top-N (top 100 players with names and scores)
- UC3: Get a specific player's rank and score
- UC4: Get players ranked around me (player's neighborhood: rank 495-505)

**P1 — Important:**
- UC5: Daily leaderboard (reset at midnight UTC)
- UC6: Weekly leaderboard (reset Monday 00:00 UTC)
- UC7: Friends leaderboard (rank among my friends)

**Out of scope for L5:**
- Seasonal leaderboards with complex tiebreaking rules
- Anti-cheat detection for score manipulation
- Tournament bracket (different problem — knockout vs ranking)
- Real-time push of rank changes to all visible players

---

## Phase 2: Functional Requirements (Minutes 8-14)

### Write operations

- **F1:** `update_score(user_id, delta)` — increment user's score by delta. Delta can be negative (score deductions). Idempotent if called with the same event_id.
- **F2:** `set_score(user_id, absolute_score)` — set absolute score (used for score corrections, imports).

### Read operations

- **F3:** `get_top_n(n=100) -> [(rank, user_id, score), ...]` — global top N players.
- **F4:** `get_rank(user_id) -> (rank, score)` — specific player's rank (1-indexed) and score.
- **F5:** `get_neighborhood(user_id, window=5) -> [(rank, user_id, score), ...]` — players ranked ±window around this player.
- **F6:** `get_friends_leaderboard(user_id, friend_ids) -> [(rank_among_friends, user_id, score), ...]`

### Time-windowed variants

- **F7:** All of F3-F5 applied to `daily` and `weekly` windows in addition to `all_time`.

### What makes this different from a simple sort

```
The deceptive simplicity:

GET top-100: SELECT user_id, score FROM scores ORDER BY score DESC LIMIT 100
  - At 10M users: full table scan -> sort -> limit = O(N log N) on every read
  - Even with an index on score: B-tree range scan O(100) for top-100
  - But GET rank of user X: SELECT COUNT(*) FROM scores WHERE score > X
    This is a full index scan to count all scores above X -> O(N)
  - At 10K rank reads/sec: 10K * O(N) = catastrophic

The right tool: Redis ZSET
  - ZADD: O(log N) - add/update score
  - ZREVRANK: O(log N) - get rank
  - ZREVRANGE: O(log N + M) - get top M
  - Pre-computed ranking: no sort at read time, ever
```

---

## Phase 3: Scale and Capacity (Minutes 14-19)

### Traffic numbers

```
Daily Active Users (DAU): 10 million
Peak concurrent players: 2 million (weekend evening)

Score update rate:
  Each active player: 1 score update every 10 seconds on average
  2M concurrent * 1 update/10s = 200,000 score updates/sec (peak)
  Average: 10M DAU * 5 updates/hour / 3600s = 13,888 updates/sec

Read rates:
  Top-100 page: 10,000 reads/sec (homepage leaderboard)
  Rank queries: 50,000 reads/sec (each player checks their rank)
  Neighborhood queries: 20,000 reads/sec

Read/write ratio: (10K + 50K + 20K) / (200K) = 80K / 200K = ~0.4:1 (write-heavy)
  This is unusual — most systems are read-heavy. Leaderboards can be write-heavy during events.
```

### Memory math for Redis ZSET

```
Redis ZSET internal structure: skip list + hash map
  Per element: ~50 bytes
    - Skip list node: ~32 bytes (forward pointers + score)
    - Hash map entry: ~16 bytes (key pointer + score)
    - User ID string: ~8 bytes (if stored as integer)

10M users * 50 bytes = 500 MB for global all-time ZSET
  (Fits comfortably in a Redis instance with 8 GB RAM)

Time-windowed ZSETs:
  Daily leaderboard: only active users that day = 2M users * 50 bytes = 100 MB
  Weekly leaderboard: 7M users * 50 bytes = 350 MB
  Total across all three ZSETs: 500 + 100 + 350 = 950 MB

Multiple leaderboards (100 game modes):
  100 * 500 MB = 50 GB total -> need Redis Cluster sharding
```

### Score update write math

```
200K ZADD/sec at peak
Redis single-threaded throughput: ~500K simple ops/sec
ZADD is O(log N): for N=10M, log(10M) = ~23 operations per ZADD
  Effective throughput: ~100K ZADD/sec on a single Redis instance

At 200K ZADD/sec: need 2 Redis instances (one primary per ZSET, or sharding)
Actually: separate ZSETs are independent. Each ZSET on its own Redis instance:
  - all_time ZSET: Redis instance 1 (500 MB)
  - daily ZSET: Redis instance 2 (100 MB)
  - weekly ZSET: Redis instance 3 (350 MB)
  Each instance handles 200K ZADDs/sec -> each at 40% capacity. Fine.
```

### What breaks first at 10x scale

```
10x users = 100M users, 10x updates = 2M updates/sec

1. Redis ZSET memory:
   100M users * 50 bytes = 5 GB per ZSET -> still fits in one Redis instance (64 GB RAM)
   But: with 100 game modes -> 500 GB -> Redis Cluster needed (shard by game_id)

2. Write throughput:
   2M ZADDs/sec per ZSET -> single Redis saturates at 100-500K ops/sec
   Fix: write buffering via Kafka -> batch ZADD (Redis pipeline) -> 10x throughput improvement
   Redis ZADD pipeline: 100 ZADDs in one network round trip = 100x fewer RTTs

3. Read fan-out for friends leaderboard:
   Each friends query: pipeline 200 ZSCORE calls -> 200 * 50 bytes = 10 KB response
   At 100K friends reads/sec: 1 GB/sec of Redis reads -> Redis becomes bottleneck
   Fix: cache friends scores for 30s, or serve from read replica
```

---

## Phase 4: Non-Functional Requirements (Minutes 14-19)

### Latency

- Top-N read: p99 < 50ms (served from Redis, fast)
- Rank query: p99 < 50ms (single ZREVRANK, O(log N))
- Score update: p99 < 100ms end-to-end (write to Redis + async write to DB)

### Consistency

- Score updates: **eventual consistency** acceptable. If a score update takes 500ms to appear in the leaderboard display, users do not notice.
- Rank reads: **stale by up to 1 second** is acceptable for display. The leaderboard is refreshed on page load, not real-time pushed.
- Source of truth: **DB is authoritative**. ZSET is the pre-computed ranking index. If Redis is lost, the ZSET is rebuilt from DB.

### Availability

- 99.9% for reads (leaderboard display). A brief outage (1-2 min) where leaderboard shows stale data is acceptable.
- Score writes: 99.9%. Missed score writes are worse than missed reads (user progression lost).

### Durability

- Score data must not be lost. Scores are written to PostgreSQL durably before Redis.
- Redis persistence: RDB snapshot every 5 minutes + AOF (append-only file) for crash recovery. If Redis crashes: at most 5 minutes of score updates to replay from DB.

---

## Phase 5: Assumptions and Constraints

- A1: Score is a non-negative integer. No negative total scores (deductions cannot push below 0).
- A2: Tiebreaking: if two players have the same score, earlier achiever ranks higher (lower timestamp = higher rank). Implemented via composite score: `rank_score = score * 10^9 + (MAX_TS - timestamp)`.
- A3: Maximum score per user is bounded (no overflow): max 2^53 - 1 (JavaScript safe integer, fits in Redis double).
- A4: User IDs are strings (UUIDs or integers stored as strings in Redis).
- A5: Leaderboard display only shows top 10,000 ranks explicitly. Beyond rank 10,000, user sees their rank number but not surrounding players.

---

## Architecture Design — HLD

### Opening analogy

Imagine a running race where 10 million runners are on the track simultaneously. How does the scoreboard know in real time who is in 1st, 2nd, and 3rd place?

Option 1: After every second, count all 10 million runners and sort them. Too slow — sorting 10 million takes 2 seconds.

Option 2: Have a special board that automatically maintains the order. As each runner crosses a marker, the board updates only that runner's position — and since the board is already sorted, inserting one runner takes just 23 steps (log2 of 10 million). That board is the Redis Sorted Set.

### Full HLD diagram

```
[Game Client / Mobile App]
        |
        | score update event
        v
+---------------------+
|    API GATEWAY      |
|  Auth, rate limit   |
+---------------------+
        |
   +----+----+
   |         |
   v         v
+--------+  +----------+
| SCORE  |  | LEADERBD |
| UPDATE |  | READ SVC |
| SVC    |  |          |
|        |  | Stateless|
|Stateless|  +----------+
+--------+        |
   |    |         |
   |    |   +-----+------+
   |    |   |    REDIS   |
   |    +-->| ZSET LAYER |
   |        |            |
   |        | all_time   |
   |        | daily      |
   |        | weekly     |
   v        +------------+
+----------+      |
| Postgres |      | rebuild on crash
| (source  |<-----+
|  of      |
|  truth)  |
+----------+
   |
   | score_updates stream
   v
+----------+
| Kafka    |
| Topic    |
| score-   |
| events   |
+----------+
   |
   +-> Analytics, Notification, Rewards services
```

### Component responsibilities

```
+-------------------+------------------------------------+----------+------------------+
| Component         | Responsibility                     | Stateful?| Scale target     |
+-------------------+------------------------------------+----------+------------------+
| Score Update Svc  | Validates event, writes to Redis   | NO       | 200K writes/sec  |
|                   | ZSET (ZINCRBY) + Postgres + Kafka  |          | 5 instances      |
+-------------------+------------------------------------+----------+------------------+
| Leaderboard Read  | Serves ZREVRANGE, ZREVRANK,        | NO       | 80K reads/sec    |
| Service           | ZRANGEBYSCORE from Redis           |          | 5 instances      |
+-------------------+------------------------------------+----------+------------------+
| Redis (all_time)  | Global all-time ZSET               | YES      | 500 MB, 200K     |
|                   | ZADD/ZREVRANK/ZREVRANGE            |          | ops/sec          |
+-------------------+------------------------------------+----------+------------------+
| Redis (daily)     | Daily window ZSET, TTL 25h         | YES      | 100 MB           |
+-------------------+------------------------------------+----------+------------------+
| Redis (weekly)    | Weekly window ZSET, TTL 8 days     | YES      | 350 MB           |
+-------------------+------------------------------------+----------+------------------+
| PostgreSQL        | Authoritative score store          | YES      | 200K writes/sec  |
|                   | user_id, score, updated_at, events |          | (batch insert)   |
+-------------------+------------------------------------+----------+------------------+
| Kafka             | Score event stream (async)         | YES      | 200K events/sec  |
|                   | Decouples write from notification  |          | RF=3             |
+-------------------+------------------------------------+----------+------------------+
```

### Write path: score update

```
Step 1: Game client sends score event
  POST /scores/update
  {user_id: "u123", delta: +50, event_id: "evt_abc", event_type: "kill"}

Step 2: Score Update Service validates and deduplicates
  Check Redis: GET dedupe:{event_id}
  If exists: return 200 (already processed, idempotent)
  If not: SET dedupe:{event_id} 1 EX 86400  (expire after 24h)

Step 3: Update Redis ZSETs atomically (Lua script or pipeline)
  ZINCRBY leaderboard:all_time 50 "u123"
  ZINCRBY leaderboard:daily:{date} 50 "u123"
  ZINCRBY leaderboard:weekly:{week} 50 "u123"
  (Three ZINCRBY calls in a pipeline: one round trip)

Step 4: Write to Postgres (async, via Kafka or direct async write)
  INSERT INTO score_events (user_id, delta, event_id, event_type, ts)
  VALUES ('u123', 50, 'evt_abc', 'kill', NOW())
  ON CONFLICT (event_id) DO NOTHING  -- idempotent

Step 5: Publish to Kafka
  Topic: score-events
  Message: {user_id, new_score, old_score, new_rank, event_type, ts}

Step 6: Return to client
  HTTP 200 {new_score: 1050, rank: 4521}
  (Rank from ZREVRANK call in step 3)
```

### Read path: top-N leaderboard

```
Step 1: Client requests top 100
  GET /leaderboard/global?limit=100&window=all_time

Step 2: Leaderboard Read Service queries Redis
  ZREVRANGE leaderboard:all_time 0 99 WITHSCORES
  Returns: [(user_id, score), (user_id, score), ...] in rank order (rank 1 first)
  O(log N + 100) = effectively O(100) since log(10M) = 23 is small

Step 3: Enrich with user display data (username, avatar)
  Batch lookup user profiles by user_id list
  Redis GET user_profile:{user_id} for each (pipeline)
  Cache hit: sub-millisecond
  Cache miss: query Postgres user table, cache for 5 minutes

Step 4: Return enriched response
  [{rank: 1, user_id: "u999", username: "DragonSlayer", score: 9999000, avatar_url: "..."},
   {rank: 2, ...}, ...]
  Total time: 5-20ms (Redis + profile cache)
```

### Read path: player rank query

```
Step 1: Client requests own rank
  GET /leaderboard/rank?user_id=u123&window=all_time

Step 2: Leaderboard Read Service
  ZREVRANK leaderboard:all_time "u123"
  Returns: 4520 (0-indexed)
  Rank (1-indexed): 4520 + 1 = 4521

  ZSCORE leaderboard:all_time "u123"
  Returns: 1050.0

Step 3: Return
  {rank: 4521, score: 1050, total_players: 10000000}
  Total time: 2-5ms (two Redis calls, pipelined)
```

---

## API Design

### Submit Score
```
POST /v1/leaderboard/{leaderboard_id}/scores
Request:  { user_id: string, score: int, event_id: string (idempotency) }
Response: { rank: int, previous_rank: int, score: int }
Errors:   400 invalid score, 409 duplicate event_id, 429 rate limited
```

**Design notes:**
- `event_id` is the idempotency key. The Score Update Service does `SET dedupe:{event_id} 1 NX EX 300` before
  processing. If the key already exists, return 200 with the original response (no double-write).
- `score` is a delta (positive or negative), not an absolute value. The service issues ZINCRBY, not ZADD.
- `previous_rank` requires a ZREVRANK call before the ZINCRBY. Pipeline both in one round trip:
  `[ZREVRANK key user_id, ZINCRBY key delta user_id, ZREVRANK key user_id]`.
- 429 rate limit: enforce max 10 score submissions per user per second at the API gateway level (token bucket).
  This defends against bots and synthetic score inflation.
- HTTP 409 on duplicate event_id rather than silently returning 200: lets clients distinguish "already processed"
  from "new success" in their retry logic.

### Get Rank
```
GET /v1/leaderboard/{leaderboard_id}/rank/{user_id}
Response: { user_id: string, rank: int, score: int, total_users: int }
Errors:   404 user not on leaderboard
```

**Design notes:**
- Issues two pipelined Redis calls: `ZREVRANK` (rank) and `ZSCORE` (score). One network round trip.
- `total_users` comes from `ZCARD leaderboard:{leaderboard_id}:all_time` — also pipelined. Three calls, one RTT.
- 404 if user not in the ZSET (ZREVRANK returns nil). Do NOT default to "rank = last" — that is misleading.
- Rank is 1-indexed in the response (`ZREVRANK` returns 0-indexed; add 1 before returning).

### Get Top-N
```
GET /v1/leaderboard/{leaderboard_id}/top?limit=100&offset=0
Response: { entries: [{rank, user_id, score, display_name}], total: int }
Notes:    max limit=1000; uses ZREVRANGE + ZSCORE pipeline
```

**Design notes:**
- `offset` maps directly to ZREVRANGE start index: `ZREVRANGE key offset (offset+limit-1) WITHSCORES`.
  No penalty for deep offsets in Redis (unlike SQL OFFSET). Page 1000 costs the same as page 1.
- Max `limit=1000` prevents a client from requesting the full 10M-entry ZSET in one call.
- `display_name` enrichment: after fetching (user_id, score) pairs from ZSET, pipeline `GET user_profile:{user_id}`
  for each. Cache profiles with 5-minute TTL. Profile cache miss falls back to Postgres.
- CDN-cache the top-100 response with a 5-second TTL. On any ZINCRBY that moves a player into the top-100
  (detected post-update via ZREVRANK < 100), publish a `top100_changed` event to invalidate the CDN key.
- Pagination note: for cursor-based pagination instead of offset, use the last entry's score as the cursor:
  `ZREVRANGEBYSCORE key (last_score -inf LIMIT 0 limit`. Avoids duplicate results when scores change mid-page.

### Get Friends Leaderboard
```
POST /v1/leaderboard/{leaderboard_id}/friends
Request:  { user_id: string, friend_ids: [string] (max 500) }
Response: { entries: [{rank_among_friends, global_rank, user_id, score}] }
Notes:    batch ZSCORE pipeline, not per-friend ZSETs (write amplification trap)
```

**Design notes:**
- POST (not GET) because friend_ids list can be large (up to 500 IDs). Query params would exceed URL length limits.
- Pipeline `ZSCORE leaderboard:{id}:all_time friend_id` for all 500 friends in ONE Redis round trip (~1ms).
  Sort the returned scores client-side (O(500 log 500) = microseconds). Insert the requesting user into the sorted
  list to derive `rank_among_friends`.
- `global_rank` for each friend: pipeline ZREVRANK for all 500 friends (second round trip). This is optional;
  omit if latency budget is tight. Cache the full result with a 30-second TTL keyed by user_id.
- Never create per-friend ZSETs. The write amplification is O(F) per score event: at 200K events/sec with
  500 friends each, that is 100M Redis ops/sec vs Redis's 500K limit. One global ZSET queried at read time.
- Error handling: filter out friend_ids not present in the ZSET (ZSCORE returns nil). These users have never
  scored and should not appear in the friends leaderboard.

### Time-Windowed Leaderboard
```
GET /v1/leaderboard/{leaderboard_id}/weekly?week=2024-W03
Response: { entries: [...], window_start: timestamp, window_end: timestamp }
Notes:    separate ZSET per window with 25-hour TTL (24h + 1h late-event buffer)
```

**Design notes:**
- Key schema: `leaderboard:{leaderboard_id}:daily:{YYYY-MM-DD}` and `leaderboard:{leaderboard_id}:weekly:{YYYY-Www}`.
- `week=2024-W03` is an ISO 8601 week designator. Server resolves to Monday 2024-01-15 00:00 UTC through
  Sunday 2024-01-21 23:59 UTC. `window_start` and `window_end` are returned as Unix timestamps.
- Weekly ZSET TTL = 8 days + 1 hour. The extra day covers users who played on Sunday and whose events
  arrive with up to 24 hours of delivery lag (mobile apps with offline sync).
- If the requested week is in the past and the ZSET has expired, fall back to the `leaderboard_snapshots`
  table in Postgres (historical top-1000 snapshot stored at week end by the cron job).
- Rate limit: weekly leaderboard reads are more expensive than all-time reads because the weekly ZSET is
  rebuilt from DB every 5 minutes (batch recalculation). Cache the weekly top-100 for 60 seconds in the
  CDN — staleness is acceptable for weekly windows.

---

## Component 1: Redis ZSET Internals — Why O(log N) for Everything

**This is the core technical depth that separates L4 from L5.**

### What is a Skip List?

A skip list is a layered linked list. Each element appears in multiple layers with decreasing probability (typically 50% per level). The bottom layer contains all elements in sorted order. Higher layers are "express lanes" that skip over many elements.

```
Finding rank 500 in a 10M element skip list:

Level 4 (spans millions):
  head -> [rank 1M] -> [rank 5M] -> [rank 9M] -> tail

Level 3 (spans 100K):
  ... -> [rank 400K] -> [rank 600K] -> ...

Level 2 (spans 10K):
  ... -> [rank 490K] -> [rank 500K] -> [rank 510K] -> ...

Level 1 (spans 1K):
  ... -> [499K] -> [499.5K] -> [500K] -> ...

Level 0 (every element):
  ... -> [499999] -> [500000] -> [500001] -> ...

To find position 500,000: start at top level, jump right in big steps,
descend when overshoot. Total comparisons: O(log N) = ~23 for N=10M.
```

### ZSET in Redis is skip list + hash map

```
Two internal structures per ZSET:

1. Skip list (ordered by score):
   Purpose: ZREVRANGE (top-N), ZREVRANK (rank of user), ZRANGEBYSCORE
   Operations: O(log N) for insert/update/delete, O(log N + M) for range query

2. Hash map (key = member, value = score):
   Purpose: ZSCORE (get score of a member), O(1) lookup
   Also used by ZADD to find existing score before updating skip list

When you call ZADD leaderboard 1000 "u123":
  a) Hash map: look up "u123" -> old_score = 950
  b) Skip list: find position of old_score (950), remove node
  c) Skip list: insert at new position (1000)
  d) Hash map: update "u123" -> 1000
  Total: O(1) hash lookup + O(log N) skip list update = O(log N)

When you call ZREVRANK leaderboard "u123":
  a) Hash map: look up "u123" -> score = 1000
  b) Skip list: count all nodes with score > 1000
     (skip list maintains augmented counts for this)
  Total: O(log N)

When you call ZREVRANGE leaderboard 0 99:
  a) Find rank-0 node in skip list: O(log N)
  b) Walk forward 100 nodes: O(100)
  Total: O(log N + 100)
```

### Memory layout per element

```
Redis ZSET element memory (for member "user:12345678"):
  Skip list node:
    Score (double):          8 bytes
    Level pointers (avg 2): 16 bytes (2 × 8 bytes per pointer)
    Backward pointer:        8 bytes
    Member string pointer:   8 bytes
    Subtotal:               40 bytes

  Hash map entry:
    Hash table slot:         8 bytes (pointer to entry)
    Entry struct:           16 bytes (key pointer + value pointer + hash)
    Subtotal:               24 bytes

  Member string:
    Redis SDS (simple dynamic string):
      Header: 8 bytes
      Content "user:12345678": 17 bytes
      Null terminator: 1 byte
    Total: 26 bytes

Total per element: 40 + 24 + 26 = 90 bytes
For 10M users: 90 bytes * 10M = 900 MB

In practice Redis reports ~50-70 bytes with integer compression:
  If member is a pure integer (user_id = 12345): Redis uses int encoding = 8 bytes
  Integer-encoded: 40 + 24 + 8 = 72 bytes -> 72 * 10M = 720 MB
  Typical estimate used: 50 bytes with ziplist for small ZSETs, 70-90 bytes for large
```

---

## Component 2: Time-Windowed Leaderboards

**Interviewers almost always ask this as a follow-up. Know all three options.**

### The problem

Global all-time leaderboard: straightforward, one ZSET. But users want to compete in shorter windows: "Who has the highest score TODAY?" or "Who had the best WEEK?"

All-time and daily/weekly have completely different top-10 lists — someone who played heavily last week might be in the daily top-10 while someone who played years ago leads all-time.

### Option A: Separate ZSET per window (recommended for daily)

```
Key naming:
  all_time:   leaderboard:all_time
  daily:      leaderboard:daily:2024-12-24
  weekly:     leaderboard:weekly:2024-W52

On every score update:
  ZINCRBY leaderboard:all_time {delta} {user_id}
  ZINCRBY leaderboard:daily:{today} {delta} {user_id}
  ZINCRBY leaderboard:weekly:{this_week} {delta} {user_id}

TTL management:
  Daily ZSET: SET leaderboard:daily:{today} TTL = 25 hours
    (25h not 24h: gives a 1h buffer to avoid race at midnight)
  Weekly ZSET: SET leaderboard:weekly:{week} TTL = 8 days + 1h

Key transitions:
  At midnight UTC: the daily key rolls over automatically
  New ZSET leaderboard:daily:{tomorrow} starts fresh
  Old ZSET expires after 25 hours

Advantages:
  - O(log N) reads and writes (same as all-time)
  - Redis TTL handles cleanup automatically
  - Each ZSET is independent (different user distributions)

Disadvantages:
  - 3x write amplification (3 ZINCRBY per event instead of 1)
  - 3 ZSET instances in Redis memory (but sizes are small)
  - At midnight: brief "empty ZSET" period if first event hasn't arrived yet
    Fix: pre-populate daily ZSET from DB at midnight as a seed job

Memory for 100 days of daily ZSETs (before TTL expires):
  Only 2 daily ZSETs live at any time (today + yesterday expiring)
  2 * 100 MB = 200 MB extra. Trivial.
```

### Option B: Event log + aggregate on read (NOT recommended)

```
Store: every score event with timestamp
Read: aggregate all events in [window_start, now) per user, sort by sum

SELECT user_id, SUM(delta) as window_score
FROM score_events
WHERE ts >= '2024-12-24 00:00:00'
GROUP BY user_id
ORDER BY window_score DESC
LIMIT 100

Problem:
  At 200K events/sec: 200K * 86400 seconds = 17.28B events per day
  Aggregating 17B rows for every top-100 request: impossible
  Even with database: O(N) scan of the day's events for every read
  
Only viable for:
  Low-frequency updates (e.g., weekly game submissions, not real-time)
  Small user counts (under 100K) where aggregation is fast
```

### Option C: Batch recalculation (recommended for weekly/monthly)

```
Tradeoff: weekly leaderboard does not need to be real-time.
A 5-minute stale weekly leaderboard is completely acceptable.

Architecture:
  Scheduler (cron job) runs every 5 minutes:
    SELECT user_id, SUM(delta) AS week_score
    FROM score_events
    WHERE ts >= '2024-12-23 00:00:00'  -- start of current week
    GROUP BY user_id
    ORDER BY week_score DESC

  Takes the result and rebuilds the weekly ZSET:
    ZADD leaderboard:weekly:2024-W52 {score} {user_id} (for all users)
  Or atomically swap:
    Build new ZSET in temp key -> RENAME to production key
    RENAME leaderboard:weekly:new leaderboard:weekly:2024-W52

Advantages:
  - Weekly ZSET reads are still O(log N) from Redis (no DB reads)
  - Reduced write amplification: no live ZINCRBY for weekly during events
  - Rebuilding from DB is the correct source of truth
  
Disadvantages:
  - Up to 5 minutes stale (acceptable for weekly leaderboard)
  - Background job complexity
  - The batch rebuild must complete before the next run (job overlap detection needed)

When to use:
  Daily: Option A (real-time, simple TTL)
  Weekly: Option C (batch rebuild every 5 min, acceptable staleness)
  Monthly: Option C (rebuild hourly or daily — staleness doesn't matter)
  All-time: Option A (live ZINCRBY)
```

---

## Component 3: Friends Leaderboard

**The hardest variant. Know the naive approach and its cost, then the correct approach.**

### Why "one ZSET per user" is wrong

```
Naive approach: maintain a separate ZSET per user containing their friends' scores
  leaderboard:friends:{user_id} -> ZSET of friend scores

On every score update for user X:
  Find all of X's friends who have X in their friends list
  For each friend F: ZINCRBY leaderboard:friends:{F} {delta} X

Problem:
  If user X has 500 friends: 500 ZINCRBY calls on every score event
  At 200K score updates/sec: 200K * 500 = 100M Redis ops/sec
  Redis: ~500K ops/sec max -> 200x over capacity

  Also: 10M users * 200 avg friends = 2B ZSET entries -> 200 GB memory for friend ZSETs alone
  This does not scale.
```

### The correct approach: query-time computation

```
Friends leaderboard algorithm:
  1. Get user's friend list: friend_ids = [f1, f2, f3, ..., f200]
  2. Batch ZSCORE from global all_time ZSET:
     scores = ZSCORE leaderboard:all_time f1
              ZSCORE leaderboard:all_time f2
              ...  (all in one pipeline: one network round trip)
  3. Sort the scores client-side: sort(friend_scores) -> friends_ranked
  4. Find user's own score: ZSCORE leaderboard:all_time user_id
  5. Insert user into the sorted list
  6. Return [(rank_among_friends, user_id, score), ...]

Performance:
  Pipeline 200 ZSCORE calls = one Redis round trip = ~1ms
  Client-side sort of 200 elements = microseconds
  Total: ~5ms including network

Cost: only one Redis call (pipelined) per friends leaderboard request.
No extra Redis ZSETs. No write amplification.

Cache friends leaderboard:
  Cache result with key: friends_leaderboard:{user_id}
  TTL: 30 seconds (friends' scores change infrequently on human timescales)
  On friend's score update: DEL friends_leaderboard:{user_id} for each of their friends
  Write amplification of invalidation: same as naive approach (one DEL per friend)
  But: DEL is O(1) and does not hold a ZSET, so 100M DELs/sec is feasible
  In practice: do not invalidate immediately; rely on 30s TTL (acceptable staleness)
```

### Alternative: Redis ZINTERSTORE / ZUNIONSTORE

```
Redis has native set intersection/union for ZSETs:

ZUNIONSTORE leaderboard:friends:u123 N f1 f2 f3 ... fN
  Creates a new ZSET containing the union of N ZSETs' members
  But our friends' scores are NOT in separate ZSETs — they're in the global ZSET

ZINTERSTORE works when you have per-user ZSETs (the naive approach we rejected)

Alternative: use sorted sets per friend group only for small N
  For a user with 10 friends: ZUNIONSTORE with 10 ZSETs
  Each ZSET contains only that friend's score (1-element ZSET)
  Too many 1-element ZSETs -> same memory problem

Conclusion: batch ZSCORE pipeline is the right approach for friends leaderboard.
No per-user ZSET. Query-time computation from the global ZSET.
```

---

## Component 4: Score Storm Handling

**The write-heavy event scenario that breaks naive designs.**

### What is a score storm?

```
Normal operation: 200K score updates/sec
Score storm scenarios:
  - End-of-season event: all players rush to accumulate points before reset
    Peak: 10x normal = 2M updates/sec
  - Flash event: "double points for the next 60 minutes"
    Peak: 3-5x normal = 600K-1M updates/sec
  - New player influx: game goes viral, 5M new accounts in 24 hours
    Peak: varies

Redis ZINCRBY throughput: ~100-500K ops/sec per instance (single-threaded)
At 2M updates/sec: Redis is 4-20x over capacity -> write latency spikes -> game events backed up
```

### Solution: Kafka buffering with controlled drain

```
Normal path (< 200K/sec):
  Score event -> Score Update Service -> ZINCRBY Redis directly -> Return

Storm path (> 200K/sec):
  Score event -> Score Update Service -> Kafka topic (score-updates)
  Consumer group (leaderboard-updater): reads Kafka, batches updates, writes to Redis

Kafka consumer batch processing:
  Consumer reads 1000 events from Kafka in one poll
  Group events by user_id:
    u123: [+50, +30, +20] -> net: +100
    u456: [+10, +10]      -> net: +20
  Issue batched ZINCRBY calls (pipeline):
    ZINCRBY leaderboard:all_time 100 "u123"
    ZINCRBY leaderboard:all_time 20 "u456"
    ... (up to 1000 ZINCs in one pipeline, one network round trip)
  Redis effective throughput: 1000 ZINCs per RTT = much higher than 1 ZINC per RTT

Staleness introduced by Kafka buffering:
  Kafka consumer lag: 0.5-2 seconds under normal load
  During storm: lag increases to 5-30 seconds
  User sees: "my score updated 10 seconds ago" -- acceptable for most games

How to implement transparently (user gets immediate feedback):
  Write to Redis optimistically in the Score Update Service (best-effort direct write)
  AND write to Kafka for durability
  If direct Redis write fails (timeout/overload): Kafka is the guaranteed path
  Users see their own score updated immediately (direct path) even if the leaderboard
  lags slightly (Kafka path for others' scores)
```

### Score deduplication

```
Score events must be idempotent: if the same event is processed twice (Kafka at-least-once),
the score is updated twice (ZINCRBY is additive).

Fix: use event_id deduplication
  Before processing event {event_id, delta}:
    SET dedupe:{event_id} 1 NX EX 86400
    (NX = only set if not exists, EX 86400 = expire in 24 hours)
  If SET returns nil (key already existed): skip this event (duplicate)
  If SET returns OK: process the event

Memory for deduplication:
  200K events/sec * 86400 seconds = 17.28B events per day
  But: we only need to deduplicate events within the retry window (typically 30 minutes)
  200K/sec * 1800s = 360M dedup keys * ~20 bytes = 7.2 GB
  Too much. Alternative:
    Keep dedup window = 5 minutes (300s): 200K * 300 = 60M * 20 bytes = 1.2 GB
    Most retries happen within 30 seconds. 5-minute window covers 99.9% of retries.
```

---

## Component 5: Database Schema

### PostgreSQL schema

```
Table: users
+------------------+----------+-----------+
| Column           | Type     | Notes     |
+------------------+----------+-----------+
| user_id          | UUID     | PK        |
| username         | TEXT     | NOT NULL  |
| avatar_url       | TEXT     |           |
| created_at       | TIMESTMP |           |
+------------------+----------+-----------+

Table: user_scores (the aggregated score per user per game mode)
+------------------+----------+-------------------------------------+
| Column           | Type     | Notes                               |
+------------------+----------+-------------------------------------+
| user_id          | UUID     | FK users                            |
| game_mode        | TEXT     | 'default', 'ranked', 'seasonal_s1'  |
| all_time_score   | BIGINT   | Running total. Source of truth.     |
| updated_at       | TIMESTMP | Last score update time              |
+------------------+----------+-------------------------------------+
Primary Key: (user_id, game_mode)
Index: (game_mode, all_time_score DESC) -- for rebuilding ZSET

Table: score_events (event log for auditing and window calculations)
+------------------+----------+-------------------------------------+
| Column           | Type     | Notes                               |
+------------------+----------+-------------------------------------+
| event_id         | UUID     | PK. Idempotency key.                |
| user_id          | UUID     | FK users                            |
| game_mode        | TEXT     |                                     |
| delta            | INT      | Score change (positive or negative) |
| event_type       | TEXT     | 'kill', 'level_up', 'bonus'         |
| ts               | TIMESTMP | When event occurred (game time)     |
+------------------+----------+-------------------------------------+
Index: (game_mode, ts) -- for window leaderboard recalculation
Partition: by ts (monthly partitions -- old months can be archived)

Table: leaderboard_snapshots (optional: store top-1000 for fast read)
+------------------+----------+-------------------------------------+
| Column           | Type     | Notes                               |
+------------------+----------+-------------------------------------+
| snapshot_id      | BIGSERIAL| PK                                  |
| game_mode        | TEXT     |                                     |
| window           | TEXT     | 'all_time', 'daily', 'weekly'       |
| snapshot_date    | DATE     |                                     |
| rank             | INT      |                                     |
| user_id          | UUID     |                                     |
| score            | BIGINT   |                                     |
+------------------+----------+-------------------------------------+
Purpose: historical snapshot for "last week's top 100" queries
Updated: once daily by batch job
```

### Redis ZSET rebuild from DB

```
Trigger: Redis crash, ZSET corruption, or cold start

Rebuild script (run as a background job):
  Step 1: Acquire distributed lock to prevent concurrent rebuilds
    SET rebuild_lock:all_time 1 NX EX 600  (10 minute lock)

  Step 2: Load scores from DB in batches
    SELECT user_id, all_time_score FROM user_scores
    WHERE game_mode = 'default' ORDER BY all_time_score DESC
    FETCH 10000 ROWS AT A TIME

  Step 3: For each batch, pipeline ZADD into a temp ZSET
    ZADD leaderboard:all_time:rebuilding {score} {user_id}  (for each user in batch)
    Use ZADD NX (only add, not update) to avoid overwriting live updates

  Step 4: Atomically swap temp ZSET to production key
    RENAME leaderboard:all_time:rebuilding leaderboard:all_time

  Step 5: Release lock
    DEL rebuild_lock:all_time

Rebuild time estimate:
  10M users / 10K batch = 1000 batches
  Each batch: 10K ZADD in pipeline = ~10ms
  Total: 1000 * 10ms = 10 seconds to rebuild 10M-user ZSET

During rebuild: serve stale data (old Redis data or cached responses)
After rebuild: traffic continues normally
```

---

## DB Schema (Extended)

This section presents the production-grade Postgres schema used as the durable source of truth. Redis is the live
read path; Postgres is the fallback for rebuilds and historical queries.

```sql
-- Persistent score log: every individual score event. Source of truth for rebuilds.
CREATE TABLE score_events (
  id             BIGSERIAL    PRIMARY KEY,
  user_id        VARCHAR(36)  NOT NULL,
  leaderboard_id VARCHAR(36)  NOT NULL,
  score_delta    INT          NOT NULL,
  event_id       VARCHAR(64)  UNIQUE NOT NULL,  -- idempotency key; prevents double-write
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_score_events_user ON score_events(leaderboard_id, user_id);
-- Used for: window recalculation (SELECT SUM(score_delta) WHERE leaderboard_id=? AND created_at >= window_start)
CREATE INDEX idx_score_events_time ON score_events(leaderboard_id, created_at);
-- Partition by created_at monthly so old partitions can be archived without affecting current queries.
-- Example: PARTITION BY RANGE (created_at)
```

**Index choice rationale:**
- `idx_score_events_user (leaderboard_id, user_id)`: supports per-user total score aggregation during ZSET rebuild
  (`SELECT SUM(score_delta) ... GROUP BY user_id`). The composite index avoids a full table scan per leaderboard.
- `idx_score_events_time (leaderboard_id, created_at)`: supports time-window aggregation (daily/weekly batch
  recalculation job). Without this index, the GROUP BY would scan the full events table for every 5-minute rebuild.
- `event_id UNIQUE`: enforced at the DB level as a second deduplication line of defence. The application-level
  Redis NX check handles the fast path (avoids a DB write). The UNIQUE constraint catches any race that slips through.

```sql
-- Materialized snapshot: pre-aggregated total score per user. Used to rebuild Redis ZSET after crash.
CREATE TABLE leaderboard_snapshots (
  leaderboard_id VARCHAR(36)  NOT NULL,
  user_id        VARCHAR(36)  NOT NULL,
  total_score    BIGINT       NOT NULL,
  last_updated   TIMESTAMPTZ  NOT NULL,
  PRIMARY KEY (leaderboard_id, user_id)
);
-- No secondary index needed: the PK covers point lookups and the full-table read for rebuild
-- is a sequential scan ordered by total_score DESC (planner will choose SeqScan over IndexScan here).
```

**How the rebuild uses this table:**
```sql
-- Step 1: Score Update Service upserts on every event (not on every read)
INSERT INTO leaderboard_snapshots (leaderboard_id, user_id, total_score, last_updated)
VALUES (?, ?, ?, NOW())
ON CONFLICT (leaderboard_id, user_id)
DO UPDATE SET
  total_score  = leaderboard_snapshots.total_score + EXCLUDED.total_score,
  last_updated = EXCLUDED.last_updated;

-- Step 2: Rebuild script reads in batches and pipelined-ZADDs to Redis
SELECT user_id, total_score
FROM   leaderboard_snapshots
WHERE  leaderboard_id = ?
ORDER  BY total_score DESC;
-- Then in the rebuild script: ZADD leaderboard:{id}:all_time NX {total_score} {user_id}
-- NX ensures live events already in Redis are not overwritten by the stale snapshot values.
```

**Pagination in rebuild:** the rebuild script fetches 10,000 rows at a time using `LIMIT / OFFSET` or keyset
pagination (`WHERE total_score < last_batch_max_score`). Keyset pagination avoids the O(offset) scan cost and
is safe here because scores are monotonically ordered.

**Error handling rationale:**
- The `score_delta` column is INT (not BIGINT) because individual event deltas are bounded by game rules (max
  +10,000 per event). The aggregated `total_score` in snapshots is BIGINT to handle years of accumulated deltas.
- `event_id VARCHAR(64)` accommodates both UUIDs (36 chars) and short hashes (8-16 chars). Using a shorter hash
  of the UUID (e.g., SHA-256 first 16 bytes, hex-encoded = 32 chars) halves index storage on the UNIQUE constraint.
- `created_at DEFAULT NOW()` uses the DB server clock, not the application clock. This prevents clock-skew issues
  where a game client's local timestamp is ahead of the DB. For window-boundary routing, use the application-provided
  `event_ts` field (stored separately) rather than `created_at`.

```
+-------------------------+-------------------------------------------+
| Table                   | Role                                      |
+-------------------------+-------------------------------------------+
| score_events            | Append-only event log. Never mutated.     |
|                         | Used for: audit, ZSET rebuild, windowed   |
|                         | recalculation (daily/weekly batch job).   |
+-------------------------+-------------------------------------------+
| leaderboard_snapshots   | Pre-aggregated total per user. Updated    |
|                         | on each score event (UPSERT). Optimized   |
|                         | for fast ZSET rebuild after crash.        |
|                         | Avoids full aggregation of score_events   |
|                         | on every rebuild.                         |
+-------------------------+-------------------------------------------+
| Redis ZSET              | Live read path. Pre-computed ranking.     |
|                         | Source: rebuilt from leaderboard_snapshots|
|                         | + score_events since last snapshot.       |
+-------------------------+-------------------------------------------+
```

---

## Component 6: Tiebreaking

**Interviewers often probe this. Know the composite score trick.**

### The tiebreaking problem

```
Standard ZSET: two users with score = 1000 are both rank X.
ZREVRANK returns the same 0-indexed position for same-score members.
Redis ZSET sorts by score, then by member lexicographically (for ties).
Lexicographic tiebreaking: "z_user" ranks below "a_user" -- not fair.

Real requirement: if two users have the same score, the user who achieved
that score FIRST ranks higher ("first to reach the milestone wins the tiebreak").
```

### Composite score approach

```
Encode the tiebreak INTO the score itself:

composite_score = all_time_score * 10^9 + (MAX_TIMESTAMP - event_timestamp)

Where:
  all_time_score:  the actual game score (e.g., 1000)
  MAX_TIMESTAMP:   a large constant (e.g., 9999999999)
  event_timestamp: Unix timestamp when the score was last updated (e.g., 1735000000)

Example:
  User A: score=1000, last update at T=1735000000
    composite = 1000 * 10^9 + (9999999999 - 1735000000)
             = 1000000000000 + 8264999999
             = 1008264999999

  User B: score=1000, last update at T=1735010000 (10000 seconds later)
    composite = 1000 * 10^9 + (9999999999 - 1735010000)
             = 1000000000000 + 8264989999
             = 1008264989999

  User A's composite (1008264999999) > User B's composite (1008264989999)
  User A ranks higher (achieved 1000 first). Correct tiebreaking.

Extracting actual score from composite:
  actual_score = composite_score // 10^9
  (Integer division strips off the tiebreak portion)

Redis double precision limit:
  Redis ZSET score is stored as IEEE 754 double (53 bits of mantissa)
  Max safe integer: 2^53 = 9,007,199,254,740,992 (~9 * 10^15)
  Our composite: ~10^12 to ~10^15 -- safely within range

ZADD call:
  ZADD leaderboard:all_time {composite_score} {user_id}
  Not ZINCRBY (composite score cannot be additively incremented)
  Each update: compute new composite from current DB score + new timestamp, then ZADD
```

---

## Failure Scenarios

### Failure 1: Redis instance crashes (ZSET data lost)

```
Impact:
  - All ZREVRANGE and ZREVRANK calls fail immediately
  - Leaderboard read endpoints return errors
  - Score writes: if writing to Redis + DB separately, DB still works
  - Score writes if Redis is the only write target: backed up in Kafka (if async path)

Detection: Redis ping fails, connection refused. Alert within 5 seconds.

Recovery:
  1. Redis restarts from RDB snapshot (5-minute-old data) + AOF replay
     RDB: 500 MB dump, load time ~10 seconds
     AOF: replay events after last RDB = up to 5 minutes of events, ~5M events
     Total restart time: ~30-60 seconds
  
  2. If AOF is corrupted or too large: rebuild from DB
     Trigger rebuild script (10 seconds for 10M users)
     During rebuild: serve empty leaderboard or cached responses (CDN stale)

  3. During outage: Score Update Service writes to Kafka only (skips Redis)
     After Redis recovery: drain Kafka backlog into Redis
     Resume normal operation

Blast radius: leaderboard reads fail for 30-120 seconds. Score writes still work via Kafka.
```

### Failure 2: Score storm overwhelms Redis

```
Impact:
  - Redis ZADD latency spikes from 1ms to 100ms+
  - Score Update Service threads all blocked waiting for Redis
  - Game events backed up, user score updates delayed

Detection: Redis latency p99 > 10ms (alert threshold). Write error rate > 1%.

Immediate mitigation:
  - Switch to async path: Score Update Service writes to Kafka only, stops direct Redis writes
  - Redis gets relief: queue drains at controlled rate via Kafka consumer
  - User score display: serve from cache (stale up to 30 seconds) during storm
  
Recovery:
  - Redis catches up as write rate normalizes
  - Kafka consumer drains the accumulated backlog
  - Return to direct write path once Redis p99 < 5ms

Prevention:
  - Pre-scale Redis to 3 instances before known storm events (end of season, flash events)
  - Rate limit score updates per user: max 10 updates/sec per user (catches bots)
  - Circuit breaker on Score Update Service: if Redis error rate > 5%, auto-switch to Kafka path
```

### Failure 3: DB is down (score events lost)

```
Impact:
  - score_events table writes fail
  - all_time_score in user_scores not updated
  - Redis ZSET still works (it is independent of DB for reads)
  - Leaderboard reads: unaffected
  - Score writes: ZINCRBY to Redis succeeds, DB write fails

Risk: Redis score updates are not durable. If Redis crashes while DB is down,
both sources of truth have lost data.

Mitigation:
  - Score events written to Kafka durably (RF=3) regardless of DB status
  - Kafka is the "backup DB" during DB outage
  - After DB recovers: replay Kafka topic from the last committed DB offset
  - Redis ZSET and DB re-synchronized via the Kafka replay

Blast radius: temporary data loss risk if both Redis AND DB are down simultaneously.
Resolution: Kafka as the durable backbone — as long as Kafka survives, no data is lost.
```

### Failure 4: Leaderboard shows wrong rank (ZSET inconsistency)

```
Scenario: due to a bug, ZINCRBY was called twice for the same event (dedup failure).
User's score in ZSET is 200 higher than in DB.

Detection:
  Canary check (runs every 10 minutes):
  For top-100 users: compare ZSCORE with DB all_time_score.
  Alert if any discrepancy > 100 points.

  Spot check: SELECT user_id, all_time_score FROM user_scores
  FOR each user in top-100: compare with ZSCORE leaderboard:all_time user_id

Remediation:
  Identify the affected users (discrepancy between Redis and DB)
  Correct their ZSET score to match DB: ZADD leaderboard:all_time {db_score} {user_id}
  ZADD overwrites the existing score (not additive)
```

### Blast radius table

```
Component failure   | Impact                                  | Recovery time
--------------------|------------------------------------------|---------------
Redis crash         | Leaderboard reads fail                  | 30-120s
Redis slow          | Score writes delayed, reads slow         | Auto-Kafka path
DB down             | Score events not persisted (Kafka backup)| Auto on DB recovery
Score Update Svc    | Score updates fail; reads still work     | 1-2min (autoscale)
Leaderboard Rd Svc  | Reads fail; score writes still work     | 1-2min
Kafka down          | Async path fails; direct path works     | 5-30min
ZSET inconsistency  | Wrong ranks displayed                    | Manual fix via canary
```

---

## Deep Concept Explanations

### Concept 1: Why Redis ZSET over a Sorted Table?

An interviewer might ask: "Why not just use a PostgreSQL table with an index on score and do ORDER BY score DESC LIMIT 100?"

```
PostgreSQL with index (B-tree on score column):

Top-100 query:
  SELECT user_id, score FROM leaderboard ORDER BY score DESC LIMIT 100
  With index: B-tree range scan from max score. O(100) index lookups.
  Actually fast for top-N. BUT:

Rank of a specific user:
  SELECT COUNT(*) FROM leaderboard WHERE score > (SELECT score FROM leaderboard WHERE user_id = ?)
  This counts all users with score higher than the given user.
  With index: O(log N) to find the user's score + O(K) to count users above them
  K = number of users with higher score (could be millions)
  At 10K rank queries/sec: 10K * O(K) = catastrophic for popular ranks (rank #5M)

Score update:
  UPDATE leaderboard SET score = score + delta WHERE user_id = ?
  With index: B-tree update = O(log N) + potential page splits + WAL write
  At 200K/sec: 200K B-tree updates/sec on a 10M row table -> high disk I/O

Redis ZSET:
  Top-100: ZREVRANGE O(log N + 100) = effectively constant
  Rank:    ZREVRANK  O(log N) for ANY rank, not O(K)
  Update:  ZINCRBY   O(log N), in-memory, no disk I/O
  
The critical difference: ZREVRANK is O(log N) regardless of rank.
PostgreSQL COUNT(*) WHERE score > X is O(K) where K grows with rank depth.
For the median user (rank 5M out of 10M): K = 5M -> catastrophic.
Redis ZSET skip list maintains augmented counts per node -> O(log N) always.
```

### Concept 2: The Approximate Top-K Problem (L6)

At 1 billion users, even Redis ZSET cannot hold the full leaderboard in memory (1B * 90 bytes = 90 GB per ZSET). What do you do?

```
Option 1: Shard the ZSET by user_id prefix (hash-based sharding)
  16 Redis shards: ZSET shard = hash(user_id) % 16
  Each shard: 1B / 16 = 62.5M users * 90 bytes = 5.6 GB per shard. Manageable.
  
  Problem: finding global top-100 requires querying all 16 shards:
    Each shard: ZREVRANGE top-100
    Merge 16 * 100 = 1600 candidates, take global top-100
    This works! O(16 * log N + 1600 merge) = fast.
  
  Problem: ZREVRANK for a specific user requires:
    Query user's own shard for user's score
    Query all 16 shards to count users with higher scores: ZCOUNT shard:X {user_score} +inf
    Sum the counts across all shards
    This requires 16 + 16 = 32 Redis calls per rank query. Still fast (pipelined).

Option 2: Approximate top-K with Count-Min Sketch (L6 depth)
  For truly massive scale (1B users, only need approximate top-1000):
  Count-Min Sketch: probabilistic frequency counting
    Width W = 10000 counters, Depth D = 5 hash functions
    Memory: W * D * 4 bytes = 200 KB (vs 90 GB for exact ZSET)
    
  Process: on score update, increment the user's counter in each of D rows
  Query: top-K estimation via heap of current estimates
  
  Error bound: with W=10000, error < total_sum / W = 0.01% of total score events
  For a gaming leaderboard: 0.01% rank error is invisible to users
  
  Trade-off: not exact. Cannot give rank 4,521 precisely -- gives rank ~4500-4550.
  Use case: huge scale (1B+ users) where exact rank is impossible to compute economically.
```

### Concept 3: Leaderboard Pagination

An interviewer will ask: "How do you show users ranked 1,001-1,100 (page 11 of 10-per-page leaderboard)?"

```
ZREVRANGE leaderboard:all_time {start} {stop} WITHSCORES

For page P with page_size S:
  start = (P - 1) * S
  stop = P * S - 1

Page 1 (rank 1-10):   ZREVRANGE leaderboard:all_time 0 9 WITHSCORES
Page 2 (rank 11-20):  ZREVRANGE leaderboard:all_time 10 19 WITHSCORES
Page 11 (rank 101-110): ZREVRANGE leaderboard:all_time 100 109 WITHSCORES

All are O(log N + page_size). Extremely efficient — no offset penalty.

This is a major advantage over SQL:
  SQL: SELECT ... ORDER BY score DESC LIMIT 10 OFFSET 1000
  MySQL OFFSET 1000: reads and discards 1000 rows. O(1000).
  At page 1000 (rank 9991-10000): OFFSET 9990, reads 9990 rows. Slow.
  
  Redis: ZREVRANGE ... 9990 9999: O(log N + 10) regardless of page number.
  Deep pagination is free in Redis ZSET.

User's neighborhood (±5 around rank 4521):
  rank = ZREVRANK leaderboard:all_time "u123"  -- returns 4520 (0-indexed)
  start = max(0, rank - 5) = 4515
  stop = rank + 5 = 4525
  ZREVRANGE leaderboard:all_time 4515 4525 WITHSCORES
  Returns 11 users centered on u123. O(log N + 11). Instant.
```

---

## L5 vs L6 Calibration Table

```
+---------------------+---------------------------+--------------------------------+
| Dimension           | L5 (Senior SWE)            | L6 (Staff)                     |
+---------------------+---------------------------+--------------------------------+
| Core data structure | Redis ZSET: ZADD,          | Explains skip list internals   |
|                     | ZREVRANK, ZREVRANGE,       | (O(log N) augmented counts),   |
|                     | ZINCRBY — correct O(log N) | knows double precision limit   |
|                     | for all operations         | for composite scores           |
+---------------------+---------------------------+--------------------------------+
| Why not SQL         | "Full table sort on every  | Precisely: ZREVRANK is O(log N)|
|                     | read" -- correct direction | for any rank; SQL COUNT(*) >   |
|                     |                            | score is O(K) growing with rank|
+---------------------+---------------------------+--------------------------------+
| Time windows        | Separate ZSET per day with | Compares all 3 options with    |
|                     | TTL, mentions weekly batch | cost/staleness/complexity.     |
|                     | recalculation             | Recommends Option A for daily, |
|                     |                            | Option C for weekly, explains  |
|                     |                            | RENAME atomicity for rebuild.  |
+---------------------+---------------------------+--------------------------------+
| Friends leaderboard | "Batch ZSCORE pipeline"    | Explains why per-user ZSET     |
|                     | -- correct                 | is O(N*F) writes and rejects   |
|                     |                            | it. Knows ZUNIONSTORE but      |
|                     |                            | explains why it doesn't apply. |
+---------------------+---------------------------+--------------------------------+
| Score storm         | Mentions Kafka for          | Designs full storm path:       |
|                     | buffering                  | circuit breaker, dual write    |
|                     |                            | (direct + Kafka), controlled   |
|                     |                            | drain rate, staleness budget   |
+---------------------+---------------------------+--------------------------------+
| Tiebreaking         | "First to reach score      | Composite score formula:       |
|                     | ranks higher"              | score * 10^9 + (MAX_TS - ts)  |
|                     |                            | Verifies within double         |
|                     |                            | precision limit (2^53)         |
+---------------------+---------------------------+--------------------------------+
| Scale beyond 1 ZSET | Mentions sharding needed   | Hash-shard by user_id,         |
|                     | for 100M+ users            | merge top-K from all shards,   |
|                     |                            | O(shards) rank query via       |
|                     |                            | ZCOUNT pipeline. Or approximate|
|                     |                            | top-K via Count-Min Sketch.    |
+---------------------+---------------------------+--------------------------------+
| DB relationship     | "DB is source of truth,    | Rebuild script design:         |
|                     | Redis is cache"            | ZADD NX into temp key, RENAME  |
|                     |                            | to production atomically,      |
|                     |                            | distributed lock to prevent    |
|                     |                            | concurrent rebuilds            |
+---------------------+---------------------------+--------------------------------+
| Monitoring          | Error rate, latency        | Per-ZSET size monitoring,      |
|                     | percentiles               | ZSET vs DB score consistency   |
|                     |                            | canary, Kafka consumer lag     |
|                     |                            | as write depth metric          |
+---------------------+---------------------------+--------------------------------+
```

---

## Production Incidents

### Incident 1: Riot Games Leaderboard ZADD Overflow During Season End (2019)

**Company:** Riot Games (League of Legends)  
**What happened:** At the end of the competitive season, Riot's ranking system sent thousands of "Elo recalculation" events per second as it finalized end-of-season ratings. The Score Update Service issued ZINCRBY calls directly to Redis for each Elo recalculation event. Redis ZADD latency climbed from 1ms to 800ms under 50x normal write load. The ZADD backlog grew faster than Redis could process. After 40 minutes, Redis memory usage hit the limit (OOM). Redis evicted 2 million player scores from the ZSET (LRU eviction on the ZSET keys). Players who were evicted from the ZSET showed rank "N/A" for 2 hours until the ZSET was rebuilt.

**Root cause:** No write buffering between the Score Update Service and Redis. Direct ZINCRBY at peak storm load saturated Redis. Redis eviction policy was set to `allkeys-lru` — it evicted ZSET members it thought were "least recently used" (which were the lower-ranked players who had not been accessed recently).

**Fix:**
- Changed Redis eviction policy to `noeviction` (fail writes when full, never evict data)
- Added Kafka buffer between Score Update Service and Redis
- Pre-scaled Redis to 3x normal capacity before season-end events
- Added monitoring: alert when Kafka consumer lag > 10,000 messages

**Staff lesson:** Never use `allkeys-lru` for a leaderboard ZSET. LRU eviction in a game leaderboard evicts the data for low-ranked players — precisely the data you cannot afford to lose (it corrupts the ranking). Use `noeviction` and handle the full-memory case explicitly (add more RAM, shard the ZSET).

---

### Incident 2: Duolingo Friends Leaderboard Per-User ZSET Memory Explosion (2020)

**Company:** Duolingo  
**What happened:** Duolingo launched a "Friends Leaderboard" feature that maintained a separate Redis ZSET per user containing that user's friends' XP scores. The ZSET was updated whenever any friend's score changed. Within 48 hours: 50M users × 50 friends average × 50 bytes/entry = 125 GB of Redis memory. Redis memory on their largest instance was 64 GB. Redis ran out of memory and began evicting ZSET data. Friends leaderboard showed incorrect or empty results for millions of users.

**Root cause:** The per-user ZSET approach has O(F) write amplification (one ZINCRBY per friend per score update). With 50M users averaging 50 friends and 1 XP update every 5 minutes per user: 50M × 50 = 2.5B ZINCRBY calls per 5 minutes = 8.3M ZINCRBY/sec. Redis cannot handle this.

**Fix:**
- Removed per-user friend ZSETs entirely
- Implemented query-time computation: pipeline ZSCORE from global ZSET for friend IDs
- Cache result with 30-second TTL per user
- Memory savings: 125 GB (per-user ZSETs) → ~2 GB (global ZSET + profile cache)

**Staff lesson:** Per-user ZSETs for friends leaderboards are a classic trap that looks simple and is catastrophically wrong at scale. The correct design is O(1) extra Redis memory — just the global ZSET, queried at request time for each user's friend list.

---

### Incident 3: Strava Segment Ranking Inconsistency After Redis Failover (2018)

**Company:** Strava  
**What happened:** Strava's Redis primary for segment rankings failed. The replica promoted to primary. The replica was 45 seconds behind the primary at the time of failure (replication lag). 45 seconds of score updates (from users who completed segment runs in that window) were lost from the ZSET. Users who had just completed runs and seen their "new rank" on the app saw a different (worse) rank after reconnecting — their score update had been lost. 8,000 users were affected.

**Root cause:** Redis replica replication is asynchronous. A 45-second replication lag means 45 seconds of writes can be lost on failover. The ranking ZSET was not rebuilt from the authoritative DB after failover.

**Fix:**
- After failover: automatically trigger ZSET rebuild from DB (within 5 minutes of failover detection)
- Reduce replica lag target to < 5 seconds (tune repl-backlog-size, add bandwidth)
- Write score events to DB FIRST (synchronously) before ZINCRBY to Redis
  - If Redis write fails: it is recoverable from DB at any time
  - If DB write fails: score event is lost regardless of Redis state

**Staff lesson:** Redis replication lag means "Redis is not a durable store for critical data." Always treat Redis ZSET as a cache layer that can be rebuilt from the DB. Write to DB first, Redis second. After any Redis failover: rebuild the ZSET from DB before serving traffic.

---

### Incident 4: EA Sports Tiebreaking Bug Caused Rank Swaps (2021)

**Company:** EA Sports (FIFA Ultimate Team ratings)  
**What happened:** EA's leaderboard sorted by `rating DESC`. For two players with the same rating, Redis ZSET used lexicographic order of the member string (user_id). User IDs were UUIDs. Lexicographic order of UUIDs is arbitrary — it has nothing to do with who achieved the rating first. When a 10,000-XP prize was distributed to the "top 1,000" players, users at rank 999 and rank 1001 (who had the same rating) received different prizes based on the lexicographic order of their UUID — which they had no control over. Users complained about arbitrary prize distribution. EA received thousands of support tickets.

**Root cause:** Tiebreaking by lexicographic UUID order is non-deterministic from the user's perspective. Users rightfully expected "first to reach that rating wins."

**Fix:**
- Implemented composite score: `composite = rating * 10^9 + (MAX_TS - achieved_at_timestamp)`
- Re-ran the prize distribution using the corrected ranking
- Issued an apology and compensation to the ~200 users who received the wrong prize tier

**Staff lesson:** Tiebreaking is a product decision, not an implementation detail. Always ask "what is the tiebreaking rule?" in requirements. The composite score trick (embed tiebreak into the score numeric value) is the canonical Redis solution — it uses the ZSET's natural score ordering, not the member string ordering.

---

### Incident 5: Zynga Daily Leaderboard TTL Race Condition at Midnight (2017)

**Company:** Zynga (FarmVille 2)  
**What happened:** Zynga used daily leaderboards with Redis keys named `leaderboard:daily:{date}` and TTL of 24 hours. At exactly midnight UTC, the day's key expired (TTL fired). A burst of score update requests for the new day all missed the ZSET (key did not exist yet) and were dropped. The first 3-4 seconds after midnight showed an empty leaderboard. Worse: some score events at 23:59:59 that arrived slightly late (due to network latency) were applied to the new day's ZSET after the midnight reset, artificially inflating the new day's scores for those users.

**Root cause:** (1) TTL of exactly 24 hours instead of 25 hours — no buffer for boundary. (2) ZINCRBY on a non-existent key in Redis creates the key (Redis auto-creates ZSETs on ZINCRBY). Late-arriving events for the previous day were applied to the new day's ZSET.

**Fix:**
- Extended daily key TTL to 25 hours (1-hour buffer past midnight)
- Events stamped with `event_ts` (when the game action happened, not when it was received)
- Score Update Service routes event to the ZSET key for `event_ts`'s date, not `now()`'s date
- Added a "seed job" at 00:01:00 UTC that initializes the new day's ZSET from the previous day's top-1000 (empty ZSET serves for 1 minute maximum)

**Staff lesson:** Clock boundaries (midnight, week start, season reset) are the hardest edge cases in time-windowed leaderboards. Always use event timestamp, not processing timestamp, for window assignment. Use TTLs longer than the window to provide a buffer. Pre-initialize new windows at boundary time to avoid empty-ZSET issues.

---

## Exercises

### Exercise 1: ZSET Rank Query

**Problem:** A leaderboard has 10 million users. User "u12345" has score 8,450. There are 24,999 users with a higher score. Write the Redis commands to: (a) add u12345 with score 8450, (b) increment u12345's score by 100, (c) get u12345's rank, (d) get the top 10 players.

**Solution:**

```
(a) Add user with score 8450:
  ZADD leaderboard:all_time 8450 "u12345"
  Returns: 1 (new element added) or 0 (element updated)

(b) Increment score by 100:
  ZINCRBY leaderboard:all_time 100 "u12345"
  New score: 8550
  Returns: "8550" (new score as string)

(c) Get rank (1-indexed):
  ZREVRANK leaderboard:all_time "u12345"
  Returns: 24999 (0-indexed, because 24999 users have higher score)
  1-indexed rank: 24999 + 1 = 25000
  
  So ZREVRANK returns 0-indexed rank (0 = first place).
  Always add 1 to convert to human-readable rank.

(d) Get top 10 players:
  ZREVRANGE leaderboard:all_time 0 9 WITHSCORES
  Returns:
    1) "u999"  2) "9999000"
    3) "u888"  4) "9998000"
    ...
    19) "u777" 20) "9990000"
  
  10 players, each with their user_id and score as strings.
  The results are in rank order: index 0 is rank 1, index 9 is rank 10.

Pipeline all 3 read operations (b through d) in one round trip:
  pipeline = redis.pipeline()
  pipeline.zincrby("leaderboard:all_time", 100, "u12345")
  pipeline.zrevrank("leaderboard:all_time", "u12345")
  pipeline.zrevrange("leaderboard:all_time", 0, 9, withscores=True)
  results = pipeline.execute()
  new_score = results[0]
  rank_0indexed = results[1]
  top10 = results[2]
```

---

### Exercise 2: Daily Leaderboard Design

**Problem:** Design the Redis key structure and commands for a daily leaderboard that resets at midnight UTC. What happens to score updates that arrive at 00:00:05 but were generated at 23:59:58 (5-second network lag)?

**Solution:**

```
Key structure:
  leaderboard:daily:2024-12-24  (today)
  leaderboard:daily:2024-12-25  (tomorrow)

TTL: set to 25 hours on creation (not 24)
  EXPIRE leaderboard:daily:2024-12-24 90000  (25 * 3600 = 90000 seconds)

Score update routing:
  Each score event includes event_ts (when the game action happened)
  Route to the ZSET for event_ts's date, not the current server time:
    event_date = date(event_ts)  # "2024-12-24" even if server_now = "2024-12-25 00:00:05"
    ZINCRBY leaderboard:daily:{event_date} {delta} {user_id}

Late-arriving event scenario:
  event_ts = 2024-12-24 23:59:58
  server_now = 2024-12-25 00:00:05 (arrived 7 seconds late)
  event_date = "2024-12-24"
  ZINCRBY leaderboard:daily:2024-12-24 {delta} {user_id}
  
  The 2024-12-24 ZSET still exists (TTL = 25 hours, not expired yet).
  The event is correctly applied to December 24's leaderboard.
  If the ZSET had a 24-hour TTL, it would have expired at exactly midnight.
  A 7-second late arrival would miss the window entirely.
  The 25-hour TTL buffer handles up to 1 hour of network lag.

What if the 2024-12-24 ZSET doesn't exist yet when the first update arrives?
  Redis auto-creates ZSETs on ZINCRBY if they don't exist.
  Set TTL immediately after the first write:
    ZINCRBY leaderboard:daily:2024-12-24 {delta} {user_id}
    EXPIRE leaderboard:daily:2024-12-24 90000  (set TTL if not already set)
  Use EXPIREX (expire only if not set) to avoid resetting TTL on every event:
    EXPIRE leaderboard:daily:2024-12-24 90000 NX  (Redis 7.0+)
    (NX = set only if no TTL exists. Prevents TTL reset on every ZINCRBY.)
```

---

### Exercise 3: Friends Leaderboard Benchmark

**Problem:** A user has 500 friends. Compare the Redis operations required for: (a) per-user ZSET approach, (b) batch ZSCORE pipeline approach. Calculate the total Redis ops/sec for 10M DAU, each requesting their friends leaderboard once per session, using approach (a) vs (b).

**Solution:**

```
Setup:
  10M DAU, 500 friends each, 1 friends leaderboard request per session
  Additionally: each user generates 5 score updates per hour (every 720 seconds)

(a) Per-user ZSET approach:

  For reads (friends leaderboard request):
    ZREVRANGE friends_leaderboard:u123 0 499 WITHSCORES
    = 1 Redis command per request
    10M requests/day / 86400s = 115.7 reads/sec. Cheap for reads.

  For writes (score update):
    On each of user X's score updates: ZINCRBY friends_leaderboard:{friend} delta X
    For each of X's 500 friends: 500 ZINCRBY commands
    10M users * 5 updates/hour / 3600s = 13,888 score updates/sec
    13,888 * 500 friends = 6,944,000 ZINCRBY/sec

  Total: 6,944,000 write ops/sec + 116 read ops/sec
  Redis capacity: 500,000 ops/sec (single instance)
  Required instances: 6,944,000 / 500,000 = 13.9 instances
  Plus: 10M ZSETs * 500 entries * 50 bytes = 250 GB memory
  FAILS: memory alone kills this approach.

(b) Batch ZSCORE pipeline approach:

  For reads (friends leaderboard request):
    Pipeline 500 ZSCORE commands from global ZSET
    = 500 Redis commands, but ONE round trip (pipeline)
    Effective: 1 network round trip per request, but Redis processes 500 simple lookups
    Redis throughput: 500K ops/sec. 10M requests / 86400s = 116 read RTTs/sec.
    Redis ops from reads: 116 * 500 = 58,000 ZSCORE/sec. Fine.

  For writes (score update):
    ZINCRBY leaderboard:all_time delta user_id
    = 1 ZINCRBY per score update
    13,888 ZINCRBY/sec. Easily within Redis capacity.

  Total: 13,888 + 58,000 = 71,888 ops/sec
  Redis capacity: 500,000 ops/sec. 14% utilization. Comfortable.
  Memory: 10M users * 90 bytes = 900 MB. Trivial.

Winner: approach (b) uses 97x fewer Redis ops and 277x less memory.
```

---

### Exercise 4: Composite Score Tiebreaking

**Problem:** Two users both have a score of 50,000. User A achieved score 50,000 at Unix timestamp 1735000000. User B achieved it at 1735086400 (1 day later). Compute their composite scores using `score * 10^9 + (9999999999 - timestamp)`. Which user ranks higher?

**Solution:**

```
User A:
  score = 50,000
  timestamp = 1,735,000,000
  composite = 50,000 * 10^9 + (9,999,999,999 - 1,735,000,000)
  composite = 50,000,000,000,000 + 8,264,999,999
  composite = 50,008,264,999,999

User B:
  score = 50,000
  timestamp = 1,735,086,400
  composite = 50,000 * 10^9 + (9,999,999,999 - 1,735,086,400)
  composite = 50,000,000,000,000 + 8,264,913,599
  composite = 50,008,264,913,599

Comparison:
  User A composite: 50,008,264,999,999
  User B composite: 50,008,264,913,599
  User A > User B -> User A ranks HIGHER

Correct: User A achieved 50,000 one day before User B.
User A ranks higher — "first to reach the milestone" wins the tiebreak.

Extracting actual score from composite:
  actual_score = composite // 10^9
  User A: 50,008,264,999,999 // 10^9 = 50,008
  Wait -- this gives 50,008, not 50,000.

Problem! The tiebreak portion (8,264,999,999) is nearly 10^10, which overflows the 10^9 multiplier.

Correct formula: ensure tiebreak portion < 10^9 (not up to 10^10):
  MAX_TS = 9,999,999,999 is too large. Unix timestamps are ~1.7 * 10^9.
  Tiebreak portion = MAX_TS - timestamp = up to ~10^10. Overflows 10^9.

Fix: use a smaller MAX_TS. Timestamps in 2024 are ~1.73 * 10^9.
  MAX_TS = 2,000,000,000 (year 2033 -- far future)
  Tiebreak = 2,000,000,000 - timestamp (always positive until 2033)
  Tiebreak range: 2B - 1.73B = 0 to 270,000,000 (< 10^9, safe)

Corrected composite:
  User A: 50,000 * 10^9 + (2,000,000,000 - 1,735,000,000)
        = 50,000,000,000,000 + 265,000,000
        = 50,000,265,000,000

  Extracting: 50,000,265,000,000 // 10^9 = 50,000. Correct!
  Tiebreak:   50,000,265,000,000 % 10^9 = 265,000,000 -> timestamp = 2B - 265M = 1.735B. Correct.

Within double precision: 50,000,265,000,000 < 2^53 (9 * 10^15). Safe.
```

---

### Exercise 5: Leaderboard Memory Sizing

**Problem:** You are launching a game with 10 million users. You need: (1) global all-time leaderboard, (2) daily leaderboard, (3) weekly leaderboard, (4) friends leaderboard (batch ZSCORE, no per-user ZSETs). How much Redis RAM do you need? Include user profile cache (username + avatar_url per user, 200 bytes average, 30-minute TTL, 20% cache hit rate assumed, 10% of users active at any time).

**Solution:**

```
1. Global all-time ZSET:
   10M users * 70 bytes/entry = 700 MB
   (70 bytes: integer user_id optimization)

2. Daily ZSET (only active users that day):
   Active users per day: 10M * 30% DAU ratio = 3M users
   3M * 70 bytes = 210 MB
   Two daily ZSETs live simultaneously (today + yesterday expiring): 420 MB

3. Weekly ZSET (users active in last 7 days):
   7 * 3M daily * de-dup factor = ~7M unique weekly actives
   7M * 70 bytes = 490 MB

4. Friends leaderboard cache:
   Active at any time: 10M * 10% = 1M concurrent users
   Each user's friends leaderboard result: 500 friends * (8 bytes user_id + 8 bytes score) = 8 KB
   But TTL is 30 min, so only users who checked their friends leaderboard recently are cached
   Assume 20% of active users have fresh cached result: 1M * 20% = 200K entries
   200K * 8 KB = 1.6 GB

5. User profile cache:
   Total users: 10M
   Active at any time: 10M * 10% = 1M
   Cached profiles (30-min TTL): 1M * 80% cache hit = 800K profiles
   800K * 200 bytes = 160 MB

6. Deduplication cache (event IDs, 5-min window):
   Peak: 200K events/sec * 300s = 60M entries
   Each: event_id (UUID string 36 bytes) + value (1 byte) + Redis overhead (~30 bytes) = 67 bytes
   60M * 67 bytes = 4 GB  [this is the surprise -- dedup cache is the largest item!]
   
   Optimization: use short event IDs (8-byte hash of the UUID): 60M * (8+30+1) = 2.34 GB

Total Redis RAM needed:
  All-time ZSET:    700 MB
  Daily ZSETs:      420 MB
  Weekly ZSET:      490 MB
  Friends cache:   1,600 MB
  Profile cache:    160 MB
  Dedup cache:    2,340 MB
  Overhead (20%):   942 MB
  --------------------------------
  Total:          ~6.65 GB

Recommendation: provision a 16 GB Redis instance with 8 GB usable data
(Redis recommends not exceeding 50% of system RAM for stability).
Or: 2 Redis instances (8 GB each): one for leaderboard ZSETs, one for caches.
```

---

## Homework

### Short homework

**Short 1:** Open a Redis CLI (install Redis locally or use `redis.io/try` online). Create a leaderboard with 10 users (ZADD). Perform: (a) ZREVRANGE to get top 5, (b) ZREVRANK for a specific user, (c) ZINCRBY to update a score, (d) ZREVRANGE again to see the updated ordering. Observe how rank updates happen in O(log N) without re-sorting.

**Short 2:** Look at Duolingo's leaderboard feature in their app. Observe: (a) Is the leaderboard real-time or batched (does it update while you watch)? (b) What time window does it show (weekly? daily?)? (c) Is it friends-only or global? What does this tell you about their architecture choice?

**Short 3:** The ZSET composite score uses `score * 10^9 + tiebreak`. What is the maximum score your game can support before the composite overflows IEEE 754 double precision (2^53)? Show the math. If your game has scores up to 100 million, does the composite fit?

### Deep homework

**Deep 1:** Build a mini leaderboard in Python using Redis:
- ZADD for score updates, ZREVRANK for rank, ZREVRANGE for top-10
- Add time-windowed support: daily leaderboard with TTL
- Simulate a score storm: 10 threads each issuing 1000 ZINCRBY calls simultaneously
- Measure: what is the p99 latency of ZINCRBY under this load?
- Add a Kafka buffer: write to Kafka first, consumer drains at 5000 ops/sec max
- Measure: does the p99 latency stabilize?

**Deep 2:** Implement friends leaderboard both ways (per-user ZSET and batch ZSCORE) for 1000 simulated users with 50 friends each. Benchmark:
- Memory usage (Redis INFO memory)
- Write throughput (score updates) 
- Read latency (friends leaderboard request)
- Compare the results. Do they match the theoretical analysis in this chapter?

**Deep 3:** Read about Count-Min Sketch (search: "Count-Min Sketch approximate top-K"). Design a leaderboard for 1 billion users using Count-Min Sketch. What is the memory cost? What rank error does your design have? At what user count does Count-Min Sketch become necessary over exact ZSET (where ZSET RAM exceeds $10K/month at cloud pricing)?

---

## Glossary

**Redis ZSET (Sorted Set):** A Redis data structure that stores members with associated floating-point scores, sorted by score. Supports O(log N) operations for add, remove, rank query, and range query. Internally implemented as a skip list + hash map.

**ZADD:** Redis command to add or update a member in a ZSET with a score. If the member already exists, its score is replaced. O(log N).

**ZINCRBY:** Redis command to atomically increment a member's score by a delta. O(log N). Returns the new score.

**ZREVRANK:** Redis command to get the 0-indexed rank of a member in descending score order (rank 0 = highest score). O(log N).

**ZREVRANGE:** Redis command to get members in a range of rank positions (0-indexed), in descending score order. O(log N + M) where M is the range size.

**ZSCORE:** Redis command to get the score of a specific member. O(1) (uses the hash map component of ZSET).

**Skip list:** A probabilistic ordered data structure where elements are connected at multiple levels, with each higher level skipping over more elements. Allows O(log N) search, insertion, and deletion. Redis ZSET uses a skip list to maintain sorted order and enable O(log N) rank queries.

**Time-windowed leaderboard:** A leaderboard that resets or applies only to a specific time window (daily, weekly, monthly). Implemented in Redis as separate ZSET keys per window period with TTL for automatic cleanup.

**Write amplification:** In the context of leaderboards, the ratio of Redis write operations to user score events. The per-user ZSET approach has O(F) write amplification (F = friend count). The global ZSET approach has O(W) amplification where W = number of active time windows (typically 2-3).

**Score storm:** A sudden spike in score update volume, typically at end-of-season events or flash events. Can overwhelm Redis direct write path, requiring Kafka buffering and controlled drain.

**Composite score:** A technique to embed tiebreaking information into the score value itself, so that Redis ZSET's natural score ordering handles tiebreaking without any application logic. `composite = score * 10^N + tiebreak`, where N is chosen so the tiebreak fits in the remaining precision.

**Friends leaderboard:** A leaderboard showing a user's rank relative to their friends only (not global). Implemented via batch ZSCORE pipeline from the global ZSET, not per-user ZSETs, to avoid O(F) write amplification.

**ZSET rebuild:** The process of reconstructing a Redis ZSET from the authoritative database after a Redis crash or data loss. Queries the DB for all user scores and batch-inserts into Redis via pipelined ZADD.

**Count-Min Sketch:** A probabilistic data structure for approximate frequency counting. Used for top-K approximation at massive scale (1B+ users) where exact ZSET rank is too memory-expensive. Trades rank precision (~1% error) for O(1) memory complexity.

---

## The One-Sentence Summary

> "Leaderboard = Redis ZSET (ZADD for O(log N) score updates, ZREVRANK for O(log N) rank of any player, ZREVRANGE for O(log N + M) top-M display) as the pre-computed ranking index on top of PostgreSQL as the source of truth, with time-windowed variants using TTL-keyed ZSET-per-window for daily (real-time) and batch-rebuild from DB for weekly (5-minute stale), and friends leaderboard via pipelined ZSCORE batch (NOT per-user ZSETs) — the core insight is that ZREVRANK is O(log N) for any rank, while SQL COUNT(*) WHERE score > X is O(K) growing with rank depth, making Redis ZSET the only viable data structure for rank queries at scale."

---

## Interview Q&A — Most Common Cross-Questions

These are the follow-up questions interviewers ask immediately after your design. Each answer is meant to be said out loud in under 60 seconds.

---

**Q1: Why not just use SQL ORDER BY score DESC LIMIT 100 for the top-100 leaderboard?**

Top-100 with SQL is actually fine — a B-tree index on score makes it O(100) with no full table scan. The real problem is getting a specific player's rank. That requires `SELECT COUNT(*) WHERE score > user_score`, which scans all users with a higher score. For the median player at rank 5 million out of 10 million, that is 5 million rows counted. At 50,000 rank queries per second, the database melts. Redis ZSET's ZREVRANK is O(log N) for any rank, not O(K) growing with rank depth. That is the fundamental reason SQL cannot replace Redis here.

---

**Q2: What is a Redis ZSET and how does it keep elements sorted?**

A Redis Sorted Set (ZSET) is a data structure that stores unique members each associated with a floating-point score. It is sorted by score at all times. Internally it uses two structures: a skip list (a layered linked list that allows O(log N) sorted access) and a hash map (for O(1) score lookup by member). The skip list maintains augmented counts at each node so that finding the rank of any element takes O(log N) comparisons — no full scan needed. Every ZADD, ZINCRBY, and ZREVRANK is O(log N) where N is the number of members.

---

**Q3: What is the difference between ZADD and ZINCRBY? When do you use each?**

ZADD sets a member's score to an absolute value. If the member exists, the score is replaced. ZINCRBY adds a delta to the member's current score (atomic increment). For a leaderboard where users earn points incrementally (e.g., +50 per kill, +100 per level-up), use ZINCRBY — it is atomic, meaning two concurrent ZINCRBY calls for the same user both apply correctly without race conditions. Use ZADD only when you know the absolute final score, such as when rebuilding the ZSET from the database or when using composite scores for tiebreaking (since composite scores cannot be additively incremented).

---

**Q4: How do you implement a daily leaderboard that resets at midnight?**

Use a separate ZSET per day: `leaderboard:daily:2024-12-24`. On every score update, issue ZINCRBY to both the all-time ZSET and the current day's ZSET. Set a 25-hour TTL (not 24 hours) on the daily key — the extra hour is a buffer for score events that arrive slightly after midnight due to network lag. At midnight UTC, the next day's key starts accumulating events. Redis automatically expires the old key after 25 hours. Route events to the ZSET for the event's timestamp, not the server's current time, so late-arriving events land in the correct day's bucket.

---

**Q5: How do you build a friends leaderboard efficiently?**

The naive approach — maintaining a separate ZSET per user containing their friends' scores — requires one ZINCRBY per friend per score event, which is O(F * N) writes at scale (F friends, N score updates per second). At 50M users with 50 friends each, that is billions of Redis writes per minute. The correct approach: when a user requests their friends leaderboard, pipeline 200-500 ZSCORE calls to the global all-time ZSET (one call per friend), sort the results client-side, and return. This is one network round trip regardless of friend count. Cache the result with a 30-second TTL. No per-user ZSETs, no write amplification.

---

**Q6: How do you handle two users with the same score for tiebreaking?**

Redis ZSET sorts by score, then lexicographically by member string for ties — which is arbitrary and unfair. The canonical fix is a composite score that encodes the tiebreak into the score value: `composite = game_score * 10^9 + (2,000,000,000 - achieved_timestamp)`. Users with the same game score have different composites: the one who achieved it earlier has a higher composite (because their timestamp is smaller, making the tiebreak term larger). Redis naturally sorts them correctly. To extract the actual score from a composite: `score = composite // 10^9`. The composite fits within IEEE 754 double precision (2^53) as long as game scores are below ~9 quadrillion.

---

**Q7: How do you handle score updates at 200,000 per second — can Redis handle that?**

A single Redis instance handles approximately 100,000-500,000 ZADD operations per second (single-threaded, O(log N) per ZADD for N=10M). At 200K/sec peak, a single Redis instance is near its limit. For multiple time-window ZSETs (all-time + daily + weekly = 3 ZINCs per event): 600K ops/sec — needs sharding. Fix: place each ZSET on its own Redis instance (they are independent). Each handles 200K ZADDs/sec at 40-60% capacity. For storm peaks (10x events): add Kafka buffering — events queue in Kafka, a consumer batch-processes them at a controlled rate using Redis pipelines (1000 ZINCs in one network round trip = 10x throughput improvement).

---

**Q8: What happens if Redis crashes and the ZSET is lost?**

The database is the source of truth. Scores are written to PostgreSQL first (or concurrently via Kafka), so no score data is permanently lost when Redis crashes. On Redis restart: (1) Redis auto-recovers from its RDB snapshot (up to 5 minutes old) plus AOF (append-only file) for events after the last snapshot — typically restores within 60 seconds. (2) If the AOF is missing or corrupt, run a rebuild script: query the DB for all user scores and batch-insert via pipelined ZADD. With 10 million users at 10,000 ZADDs per pipeline, rebuild takes approximately 10 seconds. During the outage, serve the cached leaderboard (CDN or application cache) with a staleness warning.

---

**Q9: How do you implement the "players around me" feature — show rank 4,995 to 5,005?**

Use ZREVRANK to get the user's 0-indexed rank, then ZREVRANGE with a window around that rank:

```
rank = ZREVRANK leaderboard:all_time user_id  -- e.g., returns 4999 (0-indexed)
start = max(0, rank - 5)                       -- 4994
stop  = rank + 5                               -- 5004
ZREVRANGE leaderboard:all_time 4994 5004 WITHSCORES
```

This returns 11 players centered on the user. ZREVRANGE is O(log N + 11) regardless of how deep in the leaderboard the user is. This is the "neighborhood" query — showing users a slice of context around their rank. Deep pagination has no cost in Redis (unlike SQL OFFSET which reads and discards rows).

---

**Q10: How do you handle the score storm at end of season when 10x normal score updates arrive?**

Switch to a Kafka-buffered write path before the event. Instead of Score Update Service writing directly to Redis (which would saturate it), it publishes events to a Kafka topic. A leaderboard updater consumer reads Kafka, groups events by user_id (collapsing multiple events into a net delta), and issues batch-pipelined ZINCRBY calls to Redis at a controlled rate. This decouples the write rate from the Redis throughput. Users' own scores update immediately (direct write path for their own client), while the leaderboard display for others may lag by 10-30 seconds during the storm — acceptable. Pre-scale Redis instances before known storm events (end of season, flash point events).

---

**Q11: Your daily leaderboard needs to "reset" at midnight. What exactly does "reset" mean technically?**

There is no reset operation. The daily ZSET for yesterday expires via TTL (set to 25 hours). A new ZSET for today starts accumulating events from midnight onward. The ZSET key carries the date: `leaderboard:daily:2024-12-25` starts empty at midnight and fills as today's events arrive. If no events arrive in the first few seconds of a new day (unlikely but possible for low-traffic periods), the daily leaderboard is temporarily empty — handle this by pre-seeding the new day's ZSET with the top-1000 from the previous day at 00:00:30 UTC via a cron job. Users who logged in right at midnight see a brief "loading" state, not an error.

---

**Q12: How would you shard the ZSET if the user base grows to 1 billion users?**

1 billion users * 90 bytes = 90 GB per ZSET — too large for one Redis instance. Shard by user_id hash: `shard_id = hash(user_id) % 16`. Each shard has 62.5M users * 90 bytes = 5.6 GB. For reads: ZREVRANGE top-100 from each shard (16 parallel calls), merge results (1600 candidates), take global top-100. For ZREVRANK: query the user's own shard for their score, then ZCOUNT across all 16 shards (count users with higher score), sum the counts. 16 ZCOUNT calls in parallel pipeline — fast. The key trade-off: each rank query requires 16 Redis calls instead of 1, adding ~1ms latency for the parallel fan-out.

---

**Q13: What is the difference between ZADD and ZADD NX?**

ZADD (without NX) adds a new member or updates an existing member's score. If the member exists, its score is replaced with the new value. ZADD NX (NX = "only if Not eXists") only adds the member if it does not already exist — it does not update existing members. ZADD NX is used during ZSET rebuild from DB: you batch-insert from the database, but live score updates may have already landed in Redis for some users. ZADD NX ensures live updates are not overwritten by the stale DB values being inserted during rebuild. After rebuild completes, resume normal ZINCRBY for live updates.

---

**Q14: How do you make score updates idempotent to prevent double-counting?**

Each score event has an `event_id` (UUID or hash). Before processing: `SET dedupe:{event_id} 1 NX EX 300` (NX = only if not exists, EX 300 = expire in 5 minutes). If SET returns nil, the event was already processed — skip it. If SET returns OK, process the event and issue ZINCRBY. The 5-minute TTL covers almost all retry windows (network timeouts are typically under 30 seconds). Memory cost: 200K events/sec * 300 seconds * 40 bytes per key = 2.4 GB — budget for this in your Redis memory plan. For Kafka-based async processing, Kafka's consumer offset acts as an additional deduplication layer (each event processed exactly once per partition).

---

**Q15: What if a leaderboard has 100 different game modes — 100 separate ZSETs?**

100 ZSETs * 500 MB each = 50 GB total Redis memory. This requires Redis Cluster (multiple Redis nodes, data sharded by key hash). Route each game mode's ZSET to a specific cluster shard using a hash tag: `leaderboard:{mode_id}:all_time`. Redis Cluster hashes the content inside `{}` for slot assignment — all keys for the same `mode_id` land on the same slot, ensuring that a ZREVRANGE for one mode does not require cross-slot queries. Monitor per-mode traffic: some game modes may be 100x more popular (hot slots). For hot modes, replicate the ZSET to read replicas and route reads round-robin.

---

*Section 5 — L5 / Senior SWE. High frequency at gaming companies (Riot, EA, Zynga), social platforms (Duolingo, Strava), and any product with competitive ranking. Pairs with Ch33 (Caching at Scale) and Ch34 (Redis Internals).*

---

## Monitoring and Observability

### Key Metrics

**ZSET operations:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `zincrby_latency_p99_ms` | < 1ms | > 5ms (Redis memory pressure or CPU bottleneck) |
| `zrevrank_latency_p99_ms` | < 1ms | > 3ms (ZSET too large for one instance — consider sharding) |
| `zset_cardinality` | < 50M members | > 100M (single ZSET too large — shard across instances) |
| `redis_used_memory_pct` | < 80% | > 90% (eviction imminent — add capacity or prune old ZSETs) |

**Score update pipeline:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `score_update_rate_per_sec` | 0–200K | > 400K (approaching Redis single-instance ceiling) |
| `kafka_consumer_lag_messages` | < 10,000 | > 100,000 (storm event — updater can't keep up) |
| `dedup_cache_hit_rate_%` | < 10% | > 30% (high duplicate event rate — investigate producer) |
| `event_processing_latency_p99_ms` | < 100ms | > 1,000ms (leaderboard growing stale) |

**Leaderboard reads:**

| Metric | Healthy | Alert |
|--------|---------|-------|
| `top_N_read_latency_p99_ms` | < 2ms | > 10ms (shard fan-out slow or CDN miss) |
| `rank_query_latency_p99_ms` | < 1ms | > 5ms |
| `friends_leaderboard_p99_ms` | < 10ms | > 50ms (too many friends, ZSCORE pipeline slow) |
| `cdn_top100_cache_hit_rate_%` | > 95% | < 80% (top-100 changing faster than TTL — lower TTL or push invalidation) |

### Distributed Trace: Score Update → Rank Visible

```
Trace: score_update (event_id = uuid)
  ├─ Span 1: api_gateway (POST /score_events)         2ms
  ├─ Span 2: kafka_publish                            5ms
  ├─ Span 3: kafka_consume + dedup_check              15ms  ← dedup Redis SET NX EX
  ├─ Span 4: redis_zincrby (all-time ZSET)            0.8ms
  ├─ Span 5: redis_zincrby (daily ZSET)               0.8ms
  └─ Span 6: db_insert (events table, rebuild anchor)  8ms
```

End-to-end: ~32ms from score event to Redis updated. Alert on Span 3 > 50ms (dedup slow), Span 4/5 > 5ms (Redis spike).

---

## Common Anti-Patterns

**Anti-pattern 1: Per-user friend ZSET (write amplification)**
```python
# WRONG: maintain a separate ZSET per user for their friends
def on_score_event(user_id, delta):
    for friend_id in get_friends(user_id):   # 500 friends
        redis.zincrby(f"leaderboard:friends:{friend_id}", delta, user_id)
# 500 ZINCRBYs per event. At 100K events/sec → 50M Redis ops/sec. Impossible.
```
Fix: one global ZSET. Friends leaderboard reads pipeline ZSCORE for each friend at request time (one round trip, 200-500 ZSCORE calls). Cache result for 30 seconds.

**Anti-pattern 2: SQL rank queries (O(K) scan)**
```sql
-- WRONG: counting rows to find rank
SELECT COUNT(*) + 1 FROM users WHERE score > (
    SELECT score FROM users WHERE user_id = ?
);
-- Rank 5,000,000: scans 5M rows per call. At 50K calls/sec → 250B row reads/sec. Impossible.
```
Fix: `ZREVRANK leaderboard:all_time user_id` — O(log N) regardless of rank depth.

**Anti-pattern 3: Rebuilding with ZADD (not ZADD NX) while live events arrive**
```python
# WRONG: live ZINCRBY can be overwritten by slower rebuild batch
for user_id, score in db.query("SELECT user_id, score FROM scores"):
    redis.zadd("leaderboard", {user_id: score})  # overwrites live increments!
```
Fix: `redis.zadd("leaderboard", {user_id: score}, nx=True)`. NX ensures live events (already in Redis) are never overwritten by the stale DB batch.

**Anti-pattern 4: TTL shorter than leaderboard time window (late events lost)**
```
EXPIRE leaderboard:daily:2024-12-24 86400  -- exactly 24 hours
# Events timestamped Dec 24 but arriving at 00:01 Dec 25 (network lag)
# The Dec 24 ZSET has already expired — events discarded
```
Fix: TTL = window duration + 1-hour buffer. Route events to the ZSET for the event's timestamp, not arrival time. Late events for yesterday still land in yesterday's ZSET.

**Anti-pattern 5: Top-100 CDN cache with no update trigger**
```python
# WRONG: CDN serves top-100 with 60-second TTL, no invalidation
# If a score storm puts a new player into top-100, viewers see stale list for 60 seconds
# Worse: two adjacent requests may see different top-100 (cache hit vs miss)
```
Fix: on each ZINCRBY that moves a player into or out of the top-100 (detected by ZREVRANK == 0-99 after update), publish a "top100_changed" event. The CDN key is purged via CDN API. The next request re-fetches the fresh list. Average freshness: < 1 second, not 60 seconds.

**Anti-pattern 6: Composite score integer overflow**
```python
# WRONG: using Unix timestamps directly as tiebreak multiplier
composite = score * 10**9 + timestamp  # timestamp = 1,735,000,000 > 10^9!
# actual_score = composite // 10^9 = score * 1 + 1 (wrong!)
# The tiebreak overflows into the score portion
```
Fix: tiebreak = (MAX_TS - timestamp) where MAX_TS = 2,000,000,000 (year 2033). Tiebreak range: 0 to ~265M (always < 10^9). Composite = score × 10^9 + tiebreak. Verify composite < 2^53 (IEEE 754 safe range).

---

## Production Incident Deep Dives (Extended)

### Incident 6: Duolingo Weekly Reset Race Condition (2022)

**What happened:** Every Sunday at midnight UTC, Duolingo resets weekly XP leagues. The reset process ran a cron job on a single server: (1) create new ZSET key `leaderboard:weekly:W52`, (2) delete old ZSET `leaderboard:weekly:W51`. The cron server crashed between steps 1 and 2 (network partition). A second cron server detected the first as dead and ran the same job. Step 1 ran again — but used `ZADD` (not `ZADD NX`), overwriting 3 minutes of XP events that had already been written to `leaderboard:weekly:W52` by users earning XP after midnight. Users lost their early-week XP.

**Root cause:** Non-idempotent cron (ZADD instead of ZADD NX) + no distributed lock preventing the second cron from overriding in-flight data.

**Fix:**
```redis
# Step 1: Acquire distributed lock (only one cron can run reset)
SET weekly_reset_lock:W52 1 NX EX 3600  -- NX: only if not exists
# Returns nil on second cron → abort

# Step 2: Create staging key
# (Events that arrive during the reset window land in the live key,
#  not the staging key -- staging is only for the initial empty state)
ZADD leaderboard:weekly:W52:staging 0 "__init__"  NX

# Step 3: Atomic rename (swap staging → live)
RENAME leaderboard:weekly:W52:staging leaderboard:weekly:W52
# If W52 already exists as live (second cron run): RENAME would overwrite it!
# Safer: use a Lua script to check existence before rename

# Step 4: Archive old week
RENAME leaderboard:weekly:W51 leaderboard:weekly:W51:archive
EXPIRE leaderboard:weekly:W51:archive 604800  -- keep 7 days
```

**Lesson:** Any reset/rotation job that touches live Redis data must: (1) use a distributed lock (NX) so only one instance runs, (2) use ZADD NX during rebuild so live events are never overwritten, (3) use RENAME for atomic key swaps.

---

## Additional Exercise

### Exercise 6: Approximate Leaderboard with Count-Min Sketch (1 Billion Users)

**Problem:** Your game grows to 1 billion users. Exact Redis ZSET requires 90 GB RAM (unaffordable). Design an approximate leaderboard for 1 billion users using Count-Min Sketch that fits in 1 GB, with rank error under 1% of total users (within ±10M positions).

**Solution:**

```
Core insight: you can't store exact rank for 1B users in affordable RAM.
Trade-off: rank queries for non-top users return an approximate rank (±1% of N).

Hybrid design:
  Tier 1 — Exact: top 1,000,000 users in a full Redis ZSET
    1M users × 90 bytes = 90 MB
    All top-1M users get exact rank (ZREVRANK)
    
  Tier 2 — Approximate: scores for all 1B users in a score-histogram
    100 buckets, each covering a score range (e.g., bucket 0: scores 0-100, bucket 1: 101-200)
    Each bucket: user count + min/max score
    Memory: 100 × 3 × 8 bytes = 2.4 KB (essentially free)
    
  Tier 3 — Individual score cache: Redis hash for active users
    50M daily active users × 8 bytes score = 400 MB
    
Rank algorithm:
  def get_rank(user_id):
      if user_id in top_1M_zset:
          return redis.zrevrank("top_1M", user_id) + 1  # exact
      
      user_score = redis.hget("scores", user_id)  # from Tier 3 cache
      if not user_score:
          user_score = db.query("SELECT score FROM users WHERE user_id=?")
      
      # Count users with higher score using histogram
      users_above = 0
      for bucket in histogram:
          if bucket.min_score > user_score:
              users_above += bucket.user_count  # all users in this bucket rank higher
          elif bucket.min_score <= user_score <= bucket.max_score:
              # Assume uniform distribution within bucket
              users_above += bucket.user_count * (bucket.max_score - user_score) / bucket.range
      
      return int(users_above) + 1  # approximate rank

Memory budget:
  Tier 1 (exact ZSET):   90 MB
  Tier 2 (histogram):    2.4 KB  
  Tier 3 (score cache):  400 MB
  Redis overhead (20%):  98 MB
  Total:                 ~590 MB → fits in 1 GB Redis instance with 40% headroom

Error analysis:
  For users outside top 1M: rank error ≤ ±(N/buckets) = ±(1B/100) = ±10M positions
  Display: "Your rank is approximately 45,000,000 — top 4.5% of players"
  
When to upgrade to exact:
  At $0.018/GB/hr for Redis, 90 GB = $1.62/hr = $1,166/month
  If your game revenue exceeds ~$2,000/month, exact ZSET for all 1B users is affordable
  Approximate leaderboard is a cost-optimization for earlier stages
```

---

## Key Interview Signals — What L5 Looks Like In the Room

The interviewer is not just grading your design — they're grading your reasoning. These are the specific signals that distinguish an L5 leaderboard design from a weaker one.

**Signal 1: You call out the SQL rank problem unprompted.**
The most common trap in leaderboard interviews is saying "I'll use a database with an index on score." An L5 candidate proactively explains *why* SQL fails for rank queries (O(K) COUNT scan), *why* it works fine for top-N queries (B-tree index), and *why* Redis ZSET is the correct tool for per-user rank at scale. If you wait for the interviewer to ask "why not SQL?", you've missed the chance to demonstrate proactive technical judgment.

**Signal 2: You distinguish ZADD vs ZINCRBY correctly.**
A candidate who uses ZADD for incremental score updates reveals they don't understand atomic increments. The follow-up question ("what if two score events arrive simultaneously?") exposes the race condition. L5 uses ZINCRBY because it is atomic: two concurrent ZINCRBYs for the same user both apply correctly without coordination.

**Signal 3: You think about write amplification for friends leaderboard before being asked.**
The trap design (per-user ZSET) sounds intuitive. The L5 design (batch ZSCORE pipeline at read time) sounds clever. The L5 candidate explains both, explains why the trap is a trap (O(F) writes per score event), and proposes the correct design with its trade-off (slightly higher read latency, easily mitigated with caching).

**Signal 4: You address Redis recovery without prompting.**
Every interviewer at a company that uses Redis has had a Redis outage. The question "what if Redis goes down?" is practically guaranteed. Answering it before being asked — by mentioning that the database is the source of truth, that the ZSET is rebuilt in < 60 seconds, and that a CDN-cached top-100 serves users during the rebuild — signals that you've thought about production, not just happy-path design.

**Signal 5: You give numbers, not adjectives.**
"Redis is fast" is an adjective. "A Redis ZSET with 10 million members handles ZINCRBY at sub-millisecond latency, and a single instance can sustain 200,000 operations per second" is a number. L5 candidates anchor designs in real figures — ZSET entry size, Redis instance throughput, pipeline batch sizes — not vague superlatives.

---

## Related Topics to Review After This Chapter

- **Ch34 (Redis Internals):** Understand the skip list internals that make ZREVRANK O(log N). Redis uses an augmented skip list where each node stores a span count — the number of elements skipped at that level. This allows rank queries without traversing all elements. Understanding this makes you more credible when explaining why ZREVRANK is O(log N) rather than O(N).
- **Ch33 (Caching at Scale):** The top-100 leaderboard is a perfect candidate for multi-tier caching: Redis ZREVRANGE (first tier, ~1ms), then CDN-cached JSON response (second tier, ~0ms). The cache-invalidation strategy — invalidate the CDN key when any top-100 member changes score — is a classic cache coherence problem covered in detail in Ch33.
- **Ch61h (Ride Sharing):** Uber's driver leaderboard (driver rating, earnings rank) uses the same Redis ZSET architecture described here. The friends leaderboard batch-ZSCORE pipeline maps directly to Uber's "nearby driver" batch GEOSEARCH pipeline — the pattern of batching multiple lookups into one round trip appears in both.
- **Ch60 (Real-Time Chat / WebSocket):** If your leaderboard updates in real time (user's rank changes are pushed to the user), the WebSocket fan-out architecture from Ch60 handles that delivery. The leaderboard service publishes rank-change events to Kafka; the WebSocket tier consumes and pushes to connected clients. Same fan-out pattern, different event payload.
- **Duolingo Engineering Blog (external reading):** Duolingo has published extensively about their leaderboard architecture (weekly leagues, streak shields, XP system). Searching "Duolingo leaderboard engineering blog" gives real production context for the daily/weekly ZSET architecture described in this chapter. Reading it before a gaming company interview is high signal.

---

## Quick Reference: Redis ZSET Command Cheat Sheet

| Goal | Command | Complexity | Notes |
|------|---------|------------|-------|
| Add/update score (absolute) | `ZADD key score member` | O(log N) | Replaces existing score |
| Add/update score (incremental) | `ZINCRBY key delta member` | O(log N) | Atomic increment; use for score updates |
| Get rank (0-indexed, top=0) | `ZREVRANK key member` | O(log N) | Returns nil if member absent |
| Get top-N members + scores | `ZREVRANGE key 0 N-1 WITHSCORES` | O(log N + N) | |
| Get score of one member | `ZSCORE key member` | O(1) | Uses hash map component |
| Get count in score range | `ZCOUNT key min max` | O(log N) | Fast cardinality check |
| Get members in score range | `ZRANGEBYSCORE key min max` | O(log N + M) | M = results |
| Bulk score lookup (pipeline) | `PIPELINE [ZSCORE key member1, ...]` | O(1) per + 1 RTT | For friends leaderboard |
| Add NX (rebuild safe) | `ZADD key NX score member` | O(log N) | Skip if member already exists |
| Delete member | `ZREM key member` | O(log N) | |
| ZSET size | `ZCARD key` | O(1) | |
| Arbitrary rank window | `ZREVRANGE key start stop` | O(log N + range) | For "players around me" |

**Memory formula:** ZSET entry ≈ 70-90 bytes for integer member_ids. For string member_ids (UUIDs): 36 bytes for the string + 50 bytes overhead = ~90-100 bytes per entry. For 10M users: 700 MB-1 GB.

**Pipeline rule:** batch all ZSCORE calls for the friends leaderboard into one pipeline call. A pipeline of 500 ZSCORE commands takes ~1ms (one network round trip) vs 500 individual calls taking ~500ms (500 round trips at 1ms each). Always pipeline when making multiple independent Redis calls.

**Encoding optimization:** for leaderboards where all member IDs are integers (user_ids), Redis stores them as integers in the skip list node — no string allocation. This is the source of the 70-byte-per-entry figure. If your member IDs are UUIDs or strings, store them as integer mappings (`user_id BIGSERIAL` in the DB, use the integer as the Redis member) and keep a separate mapping table. The memory savings at 10M users scale (700 MB vs 900 MB) justify this optimization for large-scale deployments.

**Ziplist encoding for small ZSETs:** Redis uses a compact "ziplist" encoding (contiguous memory block) when a ZSET has fewer than 128 members AND all members are strings under 64 bytes. At this size, the ziplist is more memory-efficient than a skip list. Once either limit is exceeded, Redis automatically converts to the full skip list + hash map encoding. This encoding detail is relevant when designing per-event ZSETs (e.g., a specific game session leaderboard with 50 players): a ziplist ZSET for 50 players uses ~2 KB vs ~7 KB for the full encoding. Configure `zset-max-ziplist-entries` and `zset-max-ziplist-value` in redis.conf to tune these thresholds.
