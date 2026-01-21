# System Design Interview Preparation for Google Staff Engineer (L6)

## Volume 2, Section 4: Phase 3 — Scale: Capacity Planning and Growth at Staff Level

---

# Introduction

Scale changes everything.

A system serving 1,000 users can run on a single server with a simple database. A system serving 100 million users requires distributed infrastructure, careful capacity planning, and fundamentally different architectural decisions. The same functional requirements lead to completely different designs depending on scale.

This is why Phase 3—Scale—is where Staff engineers spend significant time. Before you can design an architecture, you need to know how big the problem is. Before you can choose technologies, you need to understand the load they'll face. Before you can make trade-offs, you need to quantify what you're trading.

In this section, we'll cover how to think about scale at Staff level. We'll explore the key metrics you need to understand, how to translate vague prompts into concrete numbers, how to reason about growth, and how to identify the patterns—like fan-out and hot keys—that make scale challenging. By the end, you'll approach scale estimation with confidence and precision.

---

# Part 1: Why Scale Is a First-Class Concern at Staff Level

## Scale Determines Architecture

The most fundamental truth in system design: **scale determines architecture**.

At small scale, almost anything works. You can use a monolith, a single database, synchronous processing. Simplicity is a virtue because the overhead of distributed systems isn't justified.

At large scale, you have no choice but to distribute. A single database can't handle a million writes per second. A single server can't maintain 10 million concurrent connections. The laws of physics and the limits of hardware force you into distributed systems.

The transition points—where simple solutions break and complex solutions become necessary—are driven by scale. Knowing where you are relative to these points is essential for making appropriate design choices.

## Scale Reveals Hidden Complexity

Systems that work perfectly at small scale often fail in surprising ways at large scale:

- A database query that takes 10ms becomes a bottleneck when executed 10,000 times per second
- A fan-out that's negligible with 100 followers becomes catastrophic with 10 million followers
- An algorithm that's linear in complexity becomes unusable when N grows by 1000x
- A hot key that's invisible at low load causes cascading failures at high load

Staff engineers anticipate these failure modes. They don't just ask "Will this work?" They ask "Will this work at our expected scale? What about 10x that scale?"

## Scale Affects Cost

Every unit of scale costs money:

- More users = more servers
- More data = more storage
- More requests = more bandwidth
- More complexity = more engineering time

Staff engineers think about cost efficiency at scale. A 10% inefficiency is negligible at 1,000 users but costs millions of dollars at 100 million users. The design decisions you make at the whiteboard translate directly to infrastructure bills.

## Interviewers Test Scale Thinking

In Staff-level interviews, interviewers probe your scale awareness:

- Do you ask about scale before designing?
- Can you translate user numbers into technical metrics?
- Do you recognize when scale changes design choices?
- Can you estimate capacity with reasonable accuracy?
- Do you anticipate scale-related failure modes?

A candidate who designs without establishing scale is showing Senior-level (or below) behavior. A candidate who uses scale to drive every design decision is showing Staff-level thinking.

---

# Part 2: Translating Vague Scale into Concrete Numbers

## The Problem with Vague Scale

Interviewers often provide vague scale hints:

- "Design for a large social network"
- "Assume this is for a major e-commerce platform"
- "Think about Netflix-scale"
- "This should work for millions of users"

These hints are deliberately imprecise. The interviewer wants to see if you can translate vagueness into specificity.

## The Translation Process

Staff engineers translate vague scale into concrete metrics through a systematic process:

### Step 1: Anchor on Users

Start with the user count. This is usually the most grounded number:

- "For a large social network, I'm thinking 500 million monthly active users, 200 million daily active users. Does that match your expectations?"

If the interviewer hasn't given a hint, propose a range:

- "Let me assume we're designing for a significant scale—say 10 million daily active users. I can adjust if you have a different scale in mind."

### Step 2: Derive Activity Metrics

From users, derive activity:

- Average actions per user per day
- Average sessions per day
- Average session length
- Average content consumed/produced per session

"With 200 million DAU, if the average user opens the app 5 times per day and views 20 items per session, that's:
200M × 5 × 20 = 20 billion item views per day"

### Step 3: Convert to Requests

Activity translates to system requests:

- Each item view might require 1-3 API calls
- Each action (like, comment) might require 1-2 API calls
- Background sync might add additional requests

"20 billion item views, let's say 1.5 API calls each = 30 billion API calls per day"

### Step 4: Calculate Rates

Daily totals become per-second rates:

- 30 billion requests per day
- 30B / 86,400 seconds = ~350,000 requests per second average

### Step 5: Account for Peaks

Average is not peak. Systems must handle peak load:

- Peak is typically 2-10x average depending on usage patterns
- Events (sports, news, product launches) can cause spikes

"350K average RPS, but peak during prime time might be 3x, so ~1 million RPS. And during major events, we might see 2-3x peak, so design for 2-3 million RPS burst capacity."

## When Numbers Aren't Given

If the interviewer provides no scale hints, you have two options:

### Option A: Ask Directly

"Before I design, I need to understand scale. How many users are we designing for? Is this a startup MVP or a major platform?"

### Option B: Propose and Confirm

"Let me establish some scale assumptions. I'll design for:
- 50 million daily active users
- 500 requests per second per million users = 25,000 RPS average
- 100,000 RPS peak

If the scale is significantly different, some architectural choices might change. Does this order of magnitude work?"

---

# Part 3: Key Scale Metrics

## DAU and MAU

**DAU (Daily Active Users)**: Unique users who engage with the product each day.

**MAU (Monthly Active Users)**: Unique users who engage at least once per month.

**DAU/MAU Ratio**: Indicates engagement stickiness.
- 10-20%: Low engagement (occasional use apps)
- 30-50%: Moderate engagement (social media, news)
- 50%+: High engagement (messaging, essential tools)

**Why they matter**:
- DAU determines daily load
- MAU determines total data scale (profiles, history)
- DAU/MAU affects caching strategies (active user data is hot)

**Example calculation**:
- MAU: 100 million
- DAU: 30 million (30% DAU/MAU ratio)
- Data for 100M users, but daily load from 30M

## QPS (Queries Per Second)

**QPS**: The number of requests your system handles each second.

**Variants**:
- Read QPS vs Write QPS
- Average QPS vs Peak QPS
- External QPS vs Internal QPS (microservices amplify)

**Calculating QPS**:
```
QPS = (DAU × actions_per_user_per_day) / seconds_per_day
    = (DAU × actions_per_user_per_day) / 86,400
```

**Example**:
- 30 million DAU
- 100 actions per user per day
- QPS = 30M × 100 / 86,400 = ~35,000 QPS average

**Peak multiplier**:
- Apply 2-5x for peak hours
- Apply additional 2-3x for special events
- Peak QPS = 35K × 3 = 105K, event peak = 300K

## Throughput and Bandwidth

**Throughput**: Data volume processed per unit time (bytes/second, records/second).

**Bandwidth**: Network capacity (bits/second or bytes/second).

**Calculating data throughput**:
```
Throughput = QPS × average_payload_size
```

**Example**:
- 35,000 QPS
- Average response size: 5 KB
- Throughput = 35K × 5 KB = 175 MB/second = 1.4 Gbps

**Why it matters**:
- Network capacity planning
- Database I/O sizing
- Cache sizing
- CDN capacity

## Storage

**Types of storage**:
- Hot storage: Frequently accessed, fast (SSD, in-memory)
- Warm storage: Occasional access (regular disk)
- Cold storage: Archive, rarely accessed (object storage)

**Calculating storage**:
```
Total storage = number_of_items × average_item_size × retention_period_factor
```

**Example for messages**:
- 1 billion messages per day
- Average message size: 500 bytes
- Keep 1 year of history
- Storage = 1B × 500 bytes × 365 = 182 TB

**Growth considerations**:
- Data compounds over time
- 182 TB year 1, 364 TB year 2, 546 TB year 3
- Plan for 3-5 years of growth

---

# Part 4: Peak vs. Average Load

## Why Peak Matters

Systems don't fail at average load—they fail at peak load. Designing for average leaves you vulnerable when usage spikes.

**The peak/average ratio** varies by use case:

| System Type | Typical Peak/Average Ratio |
|-------------|---------------------------|
| Messaging apps | 2-3x |
| Social feeds | 3-5x |
| E-commerce | 5-10x (sales, holidays) |
| Streaming video | 3-4x (primetime) |
| Sports/news | 10-50x (events) |

## Understanding Peak Patterns

### Daily Patterns

Most consumer applications follow daily patterns:
- Low: 3 AM - 6 AM local time
- Ramp: 6 AM - 9 AM
- Moderate: 9 AM - 6 PM
- Peak: 6 PM - 11 PM
- Decline: 11 PM - 3 AM

**Global systems** see smoother curves because time zones overlap, but still have patterns.

### Weekly Patterns

- Weekday vs. weekend differences
- Friday/Saturday evenings often highest
- Monday mornings can spike (catch-up behavior)

### Event-Driven Spikes

Unpredictable but significant:
- Breaking news
- Celebrity activity
- Product launches
- Sports events (Super Bowl, World Cup final)
- System failures elsewhere (users flood alternatives)

## Designing for Peak

### Option 1: Provision for Peak

Size your system for maximum expected load.

**Pros**: Always available, simple operations
**Cons**: Expensive, wasted capacity at low load

### Option 2: Auto-Scaling

Dynamically add/remove capacity based on load.

**Pros**: Cost-efficient, handles variability
**Cons**: Scale-up latency, complexity, may not handle sudden spikes

### Option 3: Graceful Degradation

Accept that extreme peaks may receive degraded service.

**Pros**: Practical for extreme events
**Cons**: User experience impact, requires careful design

### Hybrid Approach (Most Common)

- Provision baseline capacity (maybe 2x average)
- Auto-scale for normal peaks (up to 5x average)
- Graceful degradation for extreme events (beyond 5x)

## Articulating Peak in Interviews

"The average load is 50,000 QPS. Peak during primetime is 3x, so 150,000 QPS. During major events—a celebrity announcement or breaking news—we might see 10x average, so 500,000 QPS.

I'll design the system to auto-scale from 50K to 200K smoothly. Beyond that, we'll have graceful degradation: non-critical features (like recommendations) might be disabled, but core functionality (posting, viewing) remains available."

---

# Part 5: Read vs. Write Ratios

## Why the Ratio Matters

Most systems have asymmetric read/write patterns. Understanding this ratio drives fundamental architecture decisions.

**Read-heavy systems** (read/write >> 1):
- Can benefit heavily from caching
- Can use read replicas
- Eventually consistent often acceptable
- Examples: Social feeds, e-commerce product pages, news sites

**Write-heavy systems** (read/write ≈ 1 or < 1):
- Caching provides limited benefit
- Write scaling is the challenge
- Need fast, efficient write path
- Examples: Logging, metrics, IoT data ingestion

**Balanced systems** (read/write ≈ 1-10):
- Need balanced optimization
- Can't ignore either path
- Examples: Messaging, collaborative documents

## Typical Ratios by System Type

| System | Typical Read:Write Ratio |
|--------|--------------------------|
| Social feed | 100:1 to 1000:1 |
| E-commerce catalog | 100:1 to 10,000:1 |
| URL shortener | 100:1 to 1000:1 |
| Messaging | 1:1 to 10:1 |
| Metrics/logging | 1:10 to 1:100 (write-heavy) |
| Collaborative docs | 5:1 to 20:1 |
| User profiles | 50:1 to 500:1 |

## Deriving the Ratio

Calculate from user behavior:

**Example: Social Feed**
- User opens feed: 1 read
- User scrolls: 5-20 more reads
- User posts: Rare (maybe 0.1 posts per session)
- User likes: Maybe 2 per session

Per session: ~15 reads, 2 writes → 7.5:1

But likes affect many users' feeds (fan-out), while reads are singular.

Actual system ratio: Very read-heavy on the database, but write fan-out means significant write processing.

## Impact on Architecture

### For Read-Heavy (100:1+)

- **Caching is essential**: Cache aggressively; cache hits avoid database load
- **Read replicas**: Distribute read load across replicas
- **CDN for static content**: Push content to the edge
- **Precomputation**: Compute results ahead of time
- **Eventually consistent is often fine**: Stale data acceptable for seconds

### For Write-Heavy (1:1 or below)

- **Write optimization is critical**: Fast write path, minimal overhead
- **Append-only designs**: Write ahead, process later
- **Partitioning/sharding**: Distribute writes across nodes
- **Asynchronous processing**: Accept writes quickly, process in background
- **Batching**: Group small writes into larger operations

### For Balanced (10:1)

- **Can't ignore either path**: Need reasonable read and write performance
- **Careful cache invalidation**: Writes must invalidate/update caches correctly
- **Trade-off awareness**: Improving one path might hurt the other

## Articulating in Interviews

"Let me think about the read/write ratio. For a social feed:
- Every time a user opens the app, they read the feed
- They might scroll through 20-30 items
- Occasionally they like or comment—maybe 2-3 times per session
- Rarely they post—maybe once per day if active

This is heavily read-biased—probably 100:1 or more for the feed reads. This tells me caching is essential, read replicas make sense, and eventual consistency is acceptable for the feed. The write path is less frequent but has fan-out implications—when someone posts, it affects many feeds."

---

# Part 6: Fan-Out and Amplification Effects

## What Is Fan-Out?

**Fan-out** occurs when a single action triggers multiple subsequent actions or operations.

**Examples**:
- One post → notify 1000 followers
- One message to group → deliver to 500 members
- One API call → 10 internal service calls
- One database write → updates 50 cache entries

## Why Fan-Out Is Critical

Fan-out multiplies load. What looks like a reasonable operation at the source becomes massive at the destination.

**The math**:
- 1,000 posts per second
- Average 1,000 followers per poster
- Fan-out: 1,000 × 1,000 = 1,000,000 notifications per second

Your "1,000 posts per second" system actually needs to handle a million notifications per second.

## Types of Fan-Out

### Write-Time Fan-Out (Push Model)

When content is created, immediately push to all destinations.

**Pros**:
- Fast reads (data already at destination)
- Simple read path

**Cons**:
- Slow writes (must complete fan-out)
- High storage (duplicated data)
- Wasted work if content never read

**Good for**:
- Users with small follower counts
- Time-sensitive notifications
- Systems with high read/write ratios

### Read-Time Fan-Out (Pull Model)

When content is requested, pull from all sources.

**Pros**:
- Fast writes (minimal work at write time)
- Storage efficient
- No wasted work

**Cons**:
- Slow reads (must aggregate at read time)
- Complex read path
- Repeated work if content read multiple times

**Good for**:
- Users with large follower counts (celebrities)
- Content with uncertain readership
- Systems with lower read/write ratios

### Hybrid Fan-Out

Combine approaches based on characteristics:
- Push for "normal" users (< 10K followers)
- Pull for celebrities (> 10K followers)

This is what Twitter, Facebook, and other major social platforms do.

## Calculating Fan-Out Impact

**Example: Feed system**

Setup:
- 1,000 posts per second
- Users have average 500 followers
- Celebrity accounts (1%) have 5 million followers

Without special handling:
- Regular users: 990 posts × 500 = 495,000 fan-out operations
- Celebrities: 10 posts × 5,000,000 = 50,000,000 fan-out operations

Celebrities (1% of posts) cause 99% of fan-out load!

**Solution**:
- Push for regular users: 495K/second (manageable)
- Pull for celebrities at read time
- Total managed load vs. 50M/second chaos

## Microservice Amplification

In microservice architectures, a single external request often triggers many internal requests:

**Example**:
- 1 feed request → 10 content service calls → 50 user service calls → 5 recommendation calls
- Amplification factor: 65x

**Implications**:
- Internal systems must handle much higher load than external
- Internal latency adds up
- Internal failures can cascade

**Articulating in interviews**:

"I need to consider fan-out. When a user posts, that post needs to appear in all followers' feeds. The average user has 500 followers, so our 1,000 posts/second becomes 500,000 feed updates/second.

But we have celebrity accounts with millions of followers. Pushing to them at write time would be catastrophic—10 million operations for one post. For these accounts, I'll use a pull model: we store the post once and pull it into feeds at read time. The trade-off is slightly slower feed load for users who follow celebrities, but that's acceptable given the alternative."

---

# Part 7: Hot Keys and Skew

## What Are Hot Keys?

**Hot keys** are specific keys (user IDs, product IDs, etc.) that receive disproportionate traffic. They create load imbalance and can overwhelm individual nodes.

**Examples**:
- Celebrity user posting (millions rush to see)
- Viral product (everyone checking the same product page)
- Breaking news article
- Popular hashtag
- Default or example values in systems

## Why Hot Keys Are Dangerous

Distributed systems spread load by partitioning data:

| Partition | Normal Load | With Hot Key |
|-----------|-------------|--------------|
| Partition A | 10,000 QPS | 10,000 QPS |
| Partition B | 10,000 QPS | 500,000 QPS ← Hot key here |
| Partition C | 10,000 QPS | 10,000 QPS |
| Partition D | 10,000 QPS | 10,000 QPS |

Total capacity: 200,000 QPS
Actual capacity limited by Partition B: ~500,000 QPS or failure

A single hot key can bring down a partition, causing cascading failures.

## Types of Skew

### Temporal Skew

Load concentrated in time periods:
- Flash sales
- Event starts (concert tickets on sale)
- Time-zone-aligned activity

### Key Skew

Load concentrated on specific keys:
- Celebrity accounts
- Popular content
- Viral items

### Partition Skew

Uneven data/load distribution across partitions:
- Poor partition key choice
- Natural data distribution (power law)

## Handling Hot Keys

### Strategy 1: Caching

For read-heavy hot keys, cache aggressively:

- Cache at multiple levels (CDN, application cache, database cache)
- Use short TTLs to balance freshness and load reduction
- Pre-warm caches for predictable hot keys

**Example**: Celebrity profile → cached at CDN, 1-minute TTL, serves 99% of requests

### Strategy 2: Replication

Replicate hot data across multiple nodes:

- Read replicas for read-heavy hot keys
- Multiple copies of hot partition
- Route requests across replicas

### Strategy 3: Splitting

Split hot keys into multiple virtual keys:

- user_123 becomes user_123_0, user_123_1, user_123_2
- Distribute across partitions
- Aggregate at read time

**Example**: Celebrity follower list split into 100 shards. Writes distribute. Reads aggregate.

### Strategy 4: Rate Limiting

Accept that hot keys can only be served so fast:

- Rate limit requests to hot keys
- Queue excess requests
- Return cached/stale data for overflow

### Strategy 5: Separate Infrastructure

Route hot keys to dedicated infrastructure:

- Separate cluster for celebrities
- Dedicated cache layer for popular products
- Specialized handling for known hot spots

## Anticipating Hot Keys

In an interview, proactively address hot keys:

"I need to think about hot keys. In a social platform, celebrity accounts are hot keys—one user might have 50 million followers, all trying to see their latest post.

My partitioning strategy puts user data on specific shards. A celebrity's data on one shard would overwhelm it.

I'll handle this three ways:
1. Heavy caching: Celebrity content cached at CDN with 10-second TTL
2. Read replicas: Hot user profiles replicated to multiple read nodes
3. Follower list sharding: Large follower lists split across multiple partitions

For celebrities with over 1 million followers, I'll use the pull model for feed updates rather than push, which avoids the fan-out hot key problem entirely."

---

# Part 8: Short-Term vs. Long-Term Growth Planning

## The Growth Planning Dilemma

You can't design for current scale and ignore growth—you'll constantly be rebuilding. But you also can't design for 100x scale day one—you'll waste time and money on complexity you don't need.

Staff engineers find the balance: design for reasonable growth, with a migration path to higher scale.

## Time Horizons

### Immediate (Launch - 6 months)

- Design for current expected scale
- Include some headroom (2x)
- Focus on shipping and learning

### Near-term (6 months - 2 years)

- Plan for 5-10x growth
- Architecture should handle without major redesign
- May need to add capacity, optimize, tune

### Medium-term (2-5 years)

- Consider 10-50x growth
- Major architectural decisions should support this
- Accept that some components may need redesign

### Long-term (5+ years)

- Plan for 100x+ only if business trajectory supports it
- Focus on extensibility, not specific solutions
- Accept significant uncertainty

## Growth-Aware Architecture

### Design Principles

**Horizontal scaling**: Prefer architectures that scale by adding nodes, not by upgrading nodes.

**Stateless services**: Stateless components scale easily; state should be in dedicated stores.

**Partition-ready data**: Choose partition keys that will work at 10x scale.

**Replaceable components**: Don't couple tightly to specific technologies.

### Migration Paths

For each component, know the migration path:

| Scale | Database Approach | Migration Path |
|-------|-------------------|----------------|
| 10K users | Single PostgreSQL | Add read replicas |
| 100K users | PostgreSQL + replicas | Shard hot tables |
| 1M users | Sharded PostgreSQL | Consider specialized stores |
| 10M users | Distributed database | Evaluate Spanner/CockroachDB |

### Scale Indicators

Know what metrics signal it's time to evolve:

- Database CPU consistently > 70%
- P99 latency degrading
- Storage capacity > 60%
- Write queue growing
- Hot keys emerging

## Articulating Growth in Interviews

"Let me think about growth. We're launching with 1 million users, expecting to grow to 10 million in a year.

For V1, I'll use a single primary database with read replicas. That handles our launch scale with room to grow.

At 5 million users, we'll likely need to shard the messages table—I'll choose user_id as the partition key now so the schema supports this.

At 10+ million users, we might need a distributed database like Spanner for strong consistency at scale, or accept eventual consistency with a sharded MySQL setup.

The key is: my initial design supports 10x growth with operational changes (adding capacity). Beyond 10x requires architectural evolution, which is expected."

---

# Part 9: Step-by-Step Scale Estimation Examples

Let me walk through complete scale estimations for common systems.

## Example 1: URL Shortener

### Given Information
"Design a URL shortener for a major tech company, similar to bit.ly."

### Step 1: Establish User Scale
- Assume 100 million monthly active users
- 10 million daily active users (10% DAU/MAU ratio—utility service)
- Most users only create URLs occasionally

### Step 2: Calculate Operations

**URL Creation (Writes)**:
- Average user creates 1 URL per month
- 100M URLs created per month
- 100M / 30 days / 86,400 seconds = ~40 URL creations per second
- Peak (3x): ~120 creations per second

**URL Resolution (Reads)**:
- Each URL clicked average 100 times over lifetime
- 100M URLs × 100 clicks = 10 billion clicks per month
- 10B / 30 / 86,400 = ~4,000 clicks per second
- Peak (5x): ~20,000 clicks per second

**Read:Write Ratio**: 4,000:40 = 100:1 (heavily read-biased)

### Step 3: Calculate Storage

**URL Storage**:
- 100M new URLs per month
- Average long URL: 200 bytes
- Average short key: 7 bytes
- Metadata: 100 bytes
- Per URL: ~300 bytes
- Monthly: 100M × 300 = 30 GB
- Yearly: 360 GB
- 5 years with growth: ~2-3 TB

**Click Analytics** (if included):
- 10B clicks per month
- 100 bytes per click event
- Monthly: 1 TB
- Much larger than URL storage

### Step 4: Design Implications

- Read-heavy → caching is critical
- URL resolution must be fast (<50ms)
- Can use read replicas extensively
- Creation latency less critical (can be 200-500ms)
- Storage is modest for URLs, large for analytics

### Summary Statement

"For this URL shortener:
- ~40 creates/second, ~4,000 resolves/second average
- Peak: 120 creates/second, 20,000 resolves/second
- 100:1 read:write ratio
- ~2 TB storage for URLs over 5 years
- Caching is essential; resolution path is the priority"

## Example 2: Notification System

### Given Information
"Design a notification system for a social media platform with 200 million DAU."

### Step 1: Establish Scale
- 200 million DAU
- 500 million MAU
- Global platform, 24/7 activity

### Step 2: Calculate Notification Volume

**Notification Generation**:
- Average user generates 5 notifications/day (likes, comments, follows)
- But receives 20 notifications/day (from others' actions)
- Total notifications: 200M × 20 = 4 billion notifications/day
- Per second: 4B / 86,400 = ~46,000 notifications/second
- Peak (3x): ~140,000 notifications/second

**Delivery Operations**:
- Each notification → 1 push delivery attempt
- Each notification → possibly email, SMS
- Average 1.5 deliveries per notification
- 46K × 1.5 = ~70,000 delivery operations/second

### Step 3: Consider Fan-Out

**Celebrity Problem**:
- 1% of users have 100K+ followers
- A celebrity post generates: 1 post → 100K+ notifications
- 200M × 1% = 2M celebrities
- If each posts once/day: 2M × 100K = 200 billion extra notifications

This is infeasible with push. Must use pull model for celebrities.

**Revised with hybrid**:
- Regular users (99%): Push notifications
- Celebrities (1%): Pull at read time
- Manageable: ~46K/second push + pull aggregation

### Step 4: Calculate Storage

**Notification Storage**:
- 4B notifications/day
- Keep 30 days of history
- 120B notifications
- 500 bytes per notification
- Storage: 60 TB
- With celebrity posts stored once (not fanned out): ~10 TB

### Step 5: Design Implications

- High throughput system
- Fan-out is the key challenge
- Hybrid push/pull for celebrities
- Need efficient per-user storage
- Delivery reliability matters (retry logic)

### Summary Statement

"For this notification system:
- 46K notifications/second generated, 140K/second peak
- 70K delivery operations/second average
- Must handle celebrity fan-out with hybrid push/pull
- ~10-60 TB storage for 30-day history
- Delivery latency target: <5 seconds
- Critical path: ingestion → processing → delivery"

## Example 3: Rate Limiter

### Given Information
"Design a rate limiter for an API gateway handling 1 million requests per second."

### Step 1: Understand the Load
- 1 million RPS to the API gateway
- Every request needs rate limit check
- Rate limit check must be extremely fast

### Step 2: Calculate Rate Limiter Load

**Check Operations**:
- 1M checks per second (same as API RPS)
- Each check: lookup client, check counter, maybe increment
- Latency budget: <1ms (to not significantly impact API latency)

**Counter Updates**:
- 1M increments per second
- Distributed across clients (maybe 100K active clients)
- Average 10 RPS per client
- But some clients much higher (power users, scrapers)

### Step 3: Identify Hot Keys

**Client Distribution**:
- Likely power-law: top 1% of clients = 50% of traffic
- Top 1% of 100K = 1K clients causing 500K RPS
- Average: 500 RPS per power client

**Hot Client Risk**:
- A single scrapy client might send 10K+ RPS
- That's 10K increments/second on one counter
- Potential hot key

### Step 4: Calculate Storage

**Counter Storage**:
- 100K active clients
- Per client: client_id (16 bytes) + counter (8 bytes) + window (8 bytes)
- Per client: ~32 bytes
- Total: 3.2 MB
- Trivially fits in memory

**Configuration Storage**:
- Rate limit rules
- Client-specific overrides
- Small: < 1 MB

### Step 5: Design Implications

- Ultra-low latency required (<1ms)
- Must be distributed (single node can't handle 1M/s)
- In-memory storage (Redis or custom)
- Hot key handling for power clients
- Eventual consistency acceptable (slightly over limit OK)

### Summary Statement

"For this rate limiter:
- 1M checks per second
- <1ms latency budget
- 100K clients, power-law distribution
- 3 MB state—fits in memory
- Distributed across nodes with eventual consistency
- Hot key handling for power clients (maybe local counters with periodic sync)"

---

# Part 10: Common Scale-Related Mistakes

## Mistake 1: Not Asking About Scale

**The problem**: Designing without establishing scale, leading to over- or under-engineering.

**Example**: Building a sharded database for a system that will never exceed 10,000 users.

**The fix**: Always ask about scale first. "Before I design, I need to understand scale. How many users? How much data? What's the growth expectation?"

## Mistake 2: Using Average Instead of Peak

**The problem**: Designing for average load and failing during peaks.

**Example**: "We have 10,000 QPS, so one database can handle it." But peak is 50,000 QPS.

**The fix**: Always calculate peak. "Average is 10K QPS, but peak during primetime is 3x, and during events is 10x. I need to design for 100K QPS capacity with graceful degradation beyond."

## Mistake 3: Ignoring Fan-Out

**The problem**: Calculating direct operations without considering multiplication effects.

**Example**: "1,000 posts per second—easy." But each post fans out to 1,000 followers = 1M operations.

**The fix**: Always trace the full path. "1,000 posts/second × 1,000 followers = 1M feed updates. Plus microservice amplification..."

## Mistake 4: Assuming Uniform Distribution

**The problem**: Designing for average case when reality has hot keys and skew.

**Example**: "100,000 clients × 10 RPS each = 1M RPS spread evenly." But actually 1% of clients generate 50% of traffic.

**The fix**: Consider distribution. "Power-law distribution means top 1% generate 500K RPS. Some individual clients might send 10K+ RPS. I need hot key handling."

## Mistake 5: Round Numbers Without Derivation

**The problem**: Throwing out impressive numbers without showing how they're derived.

**Example**: "Let's assume 1 billion QPS." Without explanation, this is meaningless.

**The fix**: Show your work. "200M DAU × 50 actions/day = 10B actions/day = 115K actions/second. Peak at 3x = 350K/second."

## Mistake 6: Over-Engineering for Hypothetical Scale

**The problem**: Building massive infrastructure for scale that may never materialize.

**Example**: Designing for billion-user scale when building an internal tool for 500 people.

**The fix**: Design for current + reasonable growth. "We have 500 users now, expecting 5,000 in a year. I'll design for 10,000 with a migration path to 100,000 if needed."

## Mistake 7: Under-Engineering for Obvious Growth

**The problem**: Ignoring clear growth trajectory and being forced into emergency redesigns.

**Example**: Using a single database for a rapidly growing startup, then scrambling when it can't scale.

**The fix**: Acknowledge growth trajectory. "We're at 100K users but growing 20% monthly. In 18 months, we'll be at 1M. I need to design the schema to support sharding from day one."

## Mistake 8: Forgetting Data Scale

**The problem**: Focusing only on request rate, ignoring storage and data processing needs.

**Example**: "50K QPS—that's fine." But 50K QPS × 1 KB × 1 year = 1.5 PB of data.

**The fix**: Calculate all dimensions. "50K writes/second × 1 KB = 50 MB/second = 4 TB/day = 1.5 PB/year. Storage is actually the primary challenge."

---

# Brainstorming Questions

## Understanding Scale

1. For a system you've built, what was the actual scale vs. what you designed for? Were you over or under?

2. Can you identify a system where scale forced a fundamental architecture change? What was the trigger?

3. Think of a hot key incident you've experienced or heard about. What caused it? How was it handled?

4. What's the read/write ratio of systems you work with? How does it affect the architecture?

5. When have you seen fan-out cause problems? How was it addressed?

## Estimation Practice

6. Estimate the QPS for Gmail. For Google Search. For YouTube. How do they differ?

7. How much storage does Instagram need for photos? What assumptions are you making?

8. What's the bandwidth requirement for Netflix streaming? For Zoom video calls?

9. How many messages per second does WhatsApp need to handle? Show your derivation.

10. What's the fan-out factor for Twitter when a celebrity tweets?

## Growth and Planning

11. For a system you know, what would break first if load increased 10x?

12. How do you decide when to invest in scaling vs. accepting limitations?

13. What's the cost of over-provisioning vs. under-provisioning? How do you balance?

14. How far ahead should you design? 2x? 10x? 100x? What factors influence this?

15. What metrics would tell you it's time to scale before users notice problems?

---

# Homework Exercises

## Exercise 1: Scale Estimation Practice

For each system, estimate:
- DAU/MAU
- QPS (read and write separately)
- Storage requirements
- Peak load factors

Systems:
1. Uber (rides only, not Uber Eats)
2. Slack (for a 10,000-person company)
3. A major bank's mobile app
4. A news website (like BBC or CNN)

Show your derivations.

## Exercise 2: Hot Key Analysis

Take a system you know (or choose: Twitter, DoorDash, Airbnb).

Identify:
- At least 3 potential hot keys
- What causes each to become hot
- How you would handle each

Create a mitigation strategy document.

## Exercise 3: Fan-Out Calculation

For a social media platform:

Calculate the actual operation count for:
- 1,000 posts/second
- Average 500 followers
- 1% of users are "celebrities" with 1M+ followers
- Each post generates 3 notifications (post, like, comment)

Then design a hybrid push/pull strategy with specific thresholds.

## Exercise 4: Read/Write Optimization

For each system, determine:
- Read/write ratio
- Which path is more critical
- Key optimization strategies

Systems:
1. A banking transaction system
2. A social media feed
3. An IoT sensor data platform
4. A multiplayer game leaderboard

## Exercise 5: Growth Modeling

Take a hypothetical startup:
- Launching with 10,000 users
- Growing 15% month-over-month
- Average user creates 50 MB of data per month

Model:
- User count at 6, 12, 24, 36 months
- Storage requirements at each milestone
- When single-database architecture breaks
- When you'd need to migrate to distributed storage

## Exercise 6: Complete Scale Analysis

Pick a system design prompt (notification system, chat app, etc.).

Produce a complete scale analysis document including:
- User scale derivation
- Request rate calculations (read/write/peak)
- Storage calculations
- Fan-out analysis
- Hot key identification
- Growth projections (1 year, 3 years)
- Architecture implications

Present this as you would in an interview (5-10 minutes).

---

# Conclusion

Scale is not a number—it's a lens for understanding your system.

Staff engineers approach scale systematically:

**They quantify before designing.** Before drawing any boxes, they establish: How many users? How many requests? How much data? What's the growth trajectory?

**They derive, not guess.** Numbers come from first principles: users × actions × multipliers. They show their work so it can be validated and adjusted.

**They think in peaks, not averages.** Systems fail at peak, not average. Peak during normal operation, peak during events, peak during failures.

**They consider the hidden multipliers.** Fan-out turns one operation into millions. Microservices turn one external call into dozens of internal calls. Read/write ratios change everything about optimization.

**They anticipate hot keys.** Skew is real. Power users, celebrity accounts, viral content—they all concentrate load. Designs must handle this.

**They plan for growth.** Not infinite growth, but reasonable growth. They know where the current design breaks and what the migration path looks like.

In interviews, scale estimation demonstrates maturity. It shows you've operated real systems at real scale. It shows you understand that the whiteboard design must survive contact with production reality.

Take the time to get scale right. It's the foundation for everything that follows.

---

*End of Volume 2, Section 4*

*Next: Volume 2, Section 5 – "Phase 4: Non-Functional Requirements — Quality Attributes at Staff Level"*
