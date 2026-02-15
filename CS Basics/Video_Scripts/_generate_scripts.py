#!/usr/bin/env python3
"""Generate Topic 233 expansion and Topics 234-238 video scripts."""

import os

BASE = "/Users/ranjeetnegi/Documents/Notes/SysDesignL6/Section 0/Video_Scripts"

# Topic 233 - Add ~120 words to meet 1100+
TOPIC_233_ADDITION = """

**Choosing your stance.** Staff engineers make this decision explicitly. Document it. "Our rate limiter allows up to 5% over the stated limit for availability. For billing endpoints, we use strict consistency." Everyone on the team should know. New engineers should read it. The choice has implications for cost, latency, and fairness. There is no free lunch. Only informed trade-offs. Embrace the nuance.
"""

# Topic 234
TOPIC_234 = """# Distributed Cache at Scale: Multi-Region

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A restaurant chain with locations in Mumbai, Delhi, and Bangalore. Each kitchen caches popular recipes locally. But the HEAD CHEF at Mumbai updates a recipe. Delhi and Bangalore are still using the old recipe. For 30 seconds, different restaurants serve different food. Multi-region cache—keeping caches consistent across geographically separated locations. It's harder than it looks.

---

## The Story

Your app runs in three regions: US-East, EU-West, Asia-Pacific. A user in San Francisco updates their profile photo. A user in London views that profile 100 milliseconds later. Which cache do they hit? EU cache. Does it have the new photo? Probably not. The update landed in US. EU hasn't heard yet. Cross-region latency: 50-200ms. Synchronizing cache across that distance adds delay to every write. Or you accept staleness. Freshness vs consistency. You can't have both at zero cost. Staff engineers navigate this trade-off daily.

The challenge: users expect instant updates. "I changed my name. Why does my friend in another country still see the old one?" The answer: caches. Multiple of them. Far apart. Updating one doesn't update the others. Not instantly. Physics wins. Your job: minimize the gap. Make it acceptable. Document the behavior. Set expectations.

---

## Another Way to See It

Think of a library with branches. Main branch gets a new bestseller. Branch A and Branch B don't have it yet. Customers at Branch A ask. "We'll get it in the next delivery." That's cache replication with delay. Or: Main branch calls each branch. "We have a new book. Invalidate your 'bestsellers' list." Branches update. Eventually consistent. The call takes time. Some branches might be slow to answer. Multi-region cache is that phone tree—at internet scale, with millions of "books."

---

## Connecting to Software

**The challenge.** Cross-region latency: 50-200ms. Synchronizing cache on every write = added latency. Users wait. Or you write async. But then there's a window where caches disagree. How long? Depends on your sync strategy.

**Approach 1: Invalidation-based.** Write happens in US. Invalidate cache keys in EU and Asia. Send invalidation messages. Simple. But: invalidation is not update. After invalidation, next read = cache miss. Fetch from origin DB. Extra latency for that read. And: what if invalidation fails? Retry? Give up? Stale data until TTL expires. Invalidation is simple but creates thundering herds if many regions miss at once.

**Approach 2: Replication-based.** Write happens. Replicate the new value to all regions. Pro: next read is a hit. No extra fetch. Con: more bandwidth. Every write = N copies across N regions. And: replication is async. There's still a window. Smaller than invalidation? Often. But not zero.

**Approach 3: Tiered cache.** Local L1 cache (very short TTL, e.g., 5 seconds). Regional L2 cache (longer TTL, e.g., 60 seconds). Origin DB. L1 is fast but stale quickly. L2 is shared in region. Origin is truth. Most reads hit L1. Stale for a few seconds. Acceptable for profile photos. Not acceptable for stock prices. Choose TTL by use case.

---

## Let's Walk Through the Diagram

```
MULTI-REGION CACHE - CONSISTENCY
+-----------------------------------------------------------------+
|                                                                  |
|   US-EAST           EU-WEST           ASIA-PACIFIC                |
|                                                                  |
|   [User writes]     [Cache]           [Cache]                    |
|        |                |                 |                       |
|        v                |                 |                       |
|   Origin DB <----------+-----------------+                       |
|        |                |         (50-200ms lag)                   |
|        +-- invalidate -->|                                             |
|        +-- replicate -->+--> [Cache updated]                        |
|        |                                                           |
|   Options: Invalidate (simple, miss on next read)                  |
|            Replicate (bandwidth, faster next read)                |
|            Tiered L1+L2 (TTL-based freshness)                     |
|                                                                  |
+-----------------------------------------------------------------+
```

Narrate it: User in US updates. Origin DB writes. Now: invalidate EU and Asia caches? Or replicate new value? Invalidation: caches drop the key. Next read fetches from origin. Replication: send the new value. Next read hits cache. Both have latency. Both have windows of inconsistency. The diagram shows the flow. The real work is choosing the right strategy for your data type. Profile photo? Few seconds stale is fine. Payment balance? Not fine.

---

## Real-World Examples (2-3)

**Facebook's TAO.** Distributed graph store. Caches in every region. Writes propagate. Read-your-writes consistency in home region. Cross-region: eventual. They've published on it. Billions of users. The scale demands clever caching.

**Netflix.** Regional caches for video metadata. Catalog updates propagate. Viewing history: eventually consistent. Users rarely notice. The content itself is CDN-cached. Different problem. Same multi-region story.

**Stripe.** Payment data: strict consistency. No cache for balance. Profile, config: cached with TTL. They segment by consistency requirement. Not everything needs the same SLA.

---

## Let's Think Together

**"User in US updates profile. User in EU reads profile 100ms later. EU cache still has old data. How long until they see the update?"**

Depends on strategy. Invalidation: next read after invalidation arrives = fetch from origin. So: invalidation latency + read. 100-300ms total. Replication: replication latency. 50-200ms. So: 100-200ms. Tiered with 5s L1 TTL: up to 5 seconds in worst case. Best case: invalidation hits before their read. ~100ms. Set expectations. "Profile updates may take a few seconds to appear globally." Most users accept it. Power users might complain. Document it. Build for the common case. Optimize the critical path.

---

## What Could Go Wrong? (Mini Disaster Story)

A social app. Multi-region. User A in US blocks User B. A's request hits US servers. Block recorded. User B in EU tries to view A's profile. EU cache has old data. No block. B sees the profile. A thinks they're safe. B harasses. Trust broken. The fix: critical operations like block must bypass cache or use strict consistency. Not all data can be eventually consistent. Security and safety: synchronous. Profile photo: eventual. Know the difference. One bug. Real harm. Design for it.

---

## Surprising Truth / Fun Fact

Some companies run active-active multi-region with synchronous replication for critical data. Every write goes to two regions before returning. Latency: 100ms+. They accept it for financial transactions. For social features? Async. The same company, different consistency for different data. There's no one answer. There's a matrix. Data type x consistency need x latency budget. Staff engineers fill that matrix for their system.

---

## Quick Recap (5 bullets)

- **Multi-region cache = consistency across distance.** Physics limits speed of light. Latency is real.
- **Strategies:** Invalidate (simple, cache miss), Replicate (bandwidth, faster reads), Tiered (TTL-based).
- **Trade-off:** Freshness vs latency vs bandwidth. Pick two.
- **Segment by data type:** Critical (block, payment) = strict. Nice-to-have (profile photo) = eventual.
- **Document propagation delay.** Set user expectations. "Updates may take a few seconds globally."

---

## One-Liner to Remember

**Multi-region cache is a restaurant chain with one head chef—every kitchen has a copy of the recipe, but the newest version takes time to reach all locations.**

---

## Next Video

Next: news feed design. Fan-out. When one tweet reaches millions. Different kind of scale.
"""

# Topic 235
TOPIC_235 = """# News Feed: Fan-out, Ranking, Scale

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

```
NEWS FEED - FAN-OUT STRATEGIES
+-----------------------------------------------------------------+
|                                                                  |
|   FAN-OUT-ON-WRITE          FAN-OUT-ON-READ                      |
|                                                                  |
|   User posts --> Get followers --> Insert into each feed         |
|        |                    |                                     |
|        |              [F1 feed][F2 feed][F3 feed]...              |
|        |                    |                                     |
|   Read: Just read MY feed (pre-computed)                         |
|                                                                  |
|   User opens app --> Get followees --> Query each --> Merge      |
|        |                    |                                     |
|        |              [Query A][Query B][Query C]...               |
|        v                    v                                     |
|   Return merged, ranked feed                                     |
|                                                                  |
|   HYBRID: Push for small accounts. Pull for celebrities. Merge.  |
|                                                                  |
+-----------------------------------------------------------------+
```

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
"""

# Topic 236
TOPIC_236 = """# News Feed: Backpressure and Load Shedding

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

World Cup final. Everyone tweets at the same time. 500K tweets per second instead of the usual 50K. The fan-out pipeline can't keep up. Queue grows. Memory fills. Options: (1) Let it crash. Bad. (2) Slow down ingestion—backpressure. Better. (3) Drop non-critical fan-outs—load shedding. Best. "Sorry, your tweet's fan-out is delayed by 30 seconds" is better than "Twitter is down." Let's see how.

---

## The Story

Normal day: 50K tweets/sec. Fan-out pipeline handles it. Queue depth: steady. Then: goal. Penalty. Viral moment. 500K tweets/sec. 10x spike. The pipeline processes 100K/sec. Queue grows. 400K/sec excess. In 10 seconds: 4 million tweets in the queue. Memory? Disk? How much do you have? At some point: OOM. Crash. Nobody gets anything. Total failure.

The alternative: backpressure. Downstream says "I'm full. Slow down." Upstream stops accepting. Or: load shedding. "We'll fan-out to active users first. Inactive users? Delayed." Or: "We'll skip fan-out to users who haven't logged in for 30 days." Drop the work that matters least. Keep the system up. Degraded is better than dead. Staff engineers design for this. "What do we drop when we must?" Answer before the crisis.

---

## Another Way to See It

A buffet during rush hour. Too many people. Line out the door. Option 1: Keep letting people in. Kitchen can't keep up. Everyone waits. Food runs out. Chaos. Option 2: Slow the line. "One person every 30 seconds." Backpressure. Option 3: Serve full plates to premium guests first. Others get smaller portions. Load shedding. The buffet stays open. Nobody gets everything. Everyone gets something. Same for systems. When demand exceeds capacity, you must choose what to protect. Plan it. Don't improvise during the flood.

---

## Connecting to Software

**Backpressure.** Downstream signals upstream to slow down. Queue has max size. When full: reject. Or: apply backpressure to the producer. "Wait before sending more." Kafka: consumer lag. If lag grows, producers slow. Or: API returns 503. "Try again later." Client retries. With backoff. The key: the system communicates "I'm overwhelmed." Upstream responds. Without backpressure, producers keep pushing. Queue explodes. cascade failure.

**Load shedding.** Drop low-priority work. Fan-out to inactive users? Skip. Or delay. Fan-out to power users? Priority. Criteria: last active, engagement score, tier. "Free users get delayed feed. Premium gets real-time." Or: "Users who haven't opened the app in 7 days—skip their fan-out." The work is still in the queue. But we process it last. Or never if the queue never drains. Harsh? Yes. But it keeps the system up. Document it. Users may not notice. Inactive users rarely check. Active users get the experience. Fair? Debatable. Survivable? Yes.

**Graceful degradation.** Show stale feed with "Updating..." instead of error page. "Your feed is a few minutes behind. We're catching up." Better than 503. Users understand delays. They don't understand "something went wrong." Psychologically, delay is acceptable. Failure is not. Design for degradation. Have a "degraded mode" that still works. Slower. Stale. But works.

---

## Let's Walk Through the Diagram

```
BACKPRESSURE AND LOAD SHEDDING
+-----------------------------------------------------------------+
|                                                                  |
|   INGESTION (500K/sec)     QUEUE (max 1M)     FAN-OUT (100K/sec) |
|                                                                  |
|   Tweets --> [Gate] --> [====Queue====] --> [Workers] --> Feeds  |
|                |              |                   |              |
|           Backpressure    FULL?              Load Shed:        |
|           Close gate     Reject new         Priority order     |
|                |              |                   |              |
|           Slow producers  Return 503        Active users first  |
|                           "Try later"       Inactive: skip      |
|                                                                  |
|   Key: Communicate overload. Drop low-value work. Stay up.       |
|                                                                  |
+-----------------------------------------------------------------+
```

Narrate it: Tweets pour in. Queue fills. Backpressure: close the gate. Reject or slow. Load shedding: process high-priority first. Active users. Premium. Inactive? Skip. Queue drains. System survives. The diagram shows the flow. The decision: what is high priority? Define it. Implement it. Test it. Before the spike. Not during.

---

## Real-World Examples (2-3)

**Twitter.** Spike during events. They've built for it. Backpressure. Load shedding. Stale feeds with "show more" to catch up. They've been through elections, World Cups, viral moments. The system holds. Most of the time. When it doesn't, they learn. Iterate.

**Facebook.** Similar. Feed pipeline has priority lanes. Hot content first. Long-tail later. They've published on it. The infrastructure is battle-tested. Scale teaches hard lessons. They learned.

**Uber.** Surge pricing is a form of load shedding. "Too many requests? Raise price. Reduce demand." Economic backpressure. Same idea. Different lever. Creative systems use many tools.

---

## Let's Think Together

**"Feed pipeline is 10 min behind. Should you prioritize catching up or serving current requests?"**

Serve current. New requests get fresh merge: old feed + latest from pull path. Catching up: process backlog. If you prioritize backlog, new requests wait. User opens app. Blank. "Loading." 10 seconds. Terrible. Better: serve new requests with "feed is delayed" notice. Process backlog in background. User sees something. Backlog drains eventually. Prioritize user-facing latency. Backlog is internal. Users care about "when I open the app, what do I see?" See something. Quickly. Even if stale. Then update. Catching up is secondary. Current experience is primary. Always.

---

## What Could Go Wrong? (Mini Disaster Story)

A company has no load shedding. Queue grows. They add more workers. Queue grows faster. They add more. Infinite loop. More workers = more reads from queue = more downstream pressure. Database overloads. Everything slows. The fix: cap queue size. Reject when full. Backpressure at the source. "We're at capacity. Please retry." Better than slow death. They learned the hard way. One midnight. Three hours of outage. Postmortem: "We needed backpressure." Add it before you need it. Not after.

---

## Surprising Truth / Fun Fact

Some systems use "circuit breakers" as backpressure. Downstream failing? Open circuit. Stop sending. Let it recover. Closed circuit: resume. The breaker is a signal. "I'm unhealthy. Don't send more." Same idea as backpressure. Different implementation. Netflix popularized it. Now it's standard. Resilience patterns are reusable. Learn them. Apply them. Your system will thank you.

---

## Quick Recap (5 bullets)

- **Backpressure:** Downstream signals "slow down." Queue full = reject or throttle. Prevent cascade failure.
- **Load shedding:** Drop low-priority work. Active users first. Inactive: skip or delay.
- **Graceful degradation:** Stale feed with "Updating..." beats error page. Users accept delay.
- **Prioritize current requests over backlog.** User opens app = serve something. Fast. Backlog can wait.
- **Plan before the spike.** Define priority. Implement. Test. Don't improvise at 3 AM.

---

## One-Liner to Remember

**Backpressure says slow down. Load shedding says drop the rest. Together they keep the system up when the world goes viral.**

---

## Next Video

Next: real-time collaboration. Google Docs. Two people typing at once. How do you merge without conflicts? CRDTs. Operational transformation.
"""

# Topic 237
TOPIC_237 = """# Real-Time Collaboration: CRDTs and Ordering

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Google Docs. Two people typing in the same document simultaneously. Person A types "Hello" at position 5. Person B deletes position 3. Both changes happen at the "same time" on different devices. How do you merge them without conflicts? Without one overwriting the other? This is one of the hardest problems in distributed systems. And we've solved it. Two main approaches. Let's see.

---

## The Story

Concurrent edits. No central coordinator. Each client has its own view. They must converge to the SAME final document. If A inserts "X" at position 5 and B deletes position 3, what's the result? Depends on order. If A's insert happens first, B's delete might remove something different. If B's delete happens first, positions shift. A's "position 5" is now wrong. The challenge: no global clock. No single source of truth at write time. Each client operates independently. Merge must be deterministic. Everyone must end up with the same document. No conflicts. No data loss. This is the collaborative editing problem.

Two main solutions: Operational Transformation (OT) and CRDTs. OT: transform operations against each other. Complex. Google Docs uses it. CRDTs: Conflict-Free Replicated Data Types. Data structures that automatically merge. Mathematically guaranteed to converge. Figma uses it. Both work. Different trade-offs. Staff engineers choose based on product needs.

---

## Another Way to See It

Two chefs editing the same recipe. Chef A adds "cumin" at step 3. Chef B removes step 2. Do they conflict? If we track "steps" by number, yes. Step 3 moved. "Cumin" might land in the wrong place. If we use unique IDs for each step—step_abc, step_def—then "add after step_abc" and "remove step_def" don't conflict. We merge by identity, not position. CRDTs do this. Operations reference stable identities. Merge is automatic. OT: the chefs send edits. A central system transforms them. "Chef B's delete—apply it to Chef A's insert." Adjusted. Complex. But works. Both kitchens end up with the same recipe. Different paths.

---

## Connecting to Software

**Operational Transformation (OT).** Each edit is an operation. Insert(c, pos). Delete(pos). To merge: transform operations against each other. A inserts at 5. B deletes at 3. Transform B's delete against A's insert. "If A's insert happened first, B's delete position shifts." Rules get complex. Edge cases many. But: Google Docs. Proven. Works. Central server often required to serialize transforms. Conflict resolution is algorithmic. Not automatic. Requires careful design.

**CRDTs.** Conflict-Free Replicated Data Types. Data structures with merge rules. Example: G-Counter. Each node has its own counter. To get total: sum all. No conflicts. For text: RGA (Replicated Growable Array) or LSEQ. Each character has a unique ID. Insert "X" after ID abc. Delete character with ID xyz. Merging: apply all inserts and deletes. Same IDs. Same order (via causal ordering). Everyone converges. No central server needed. Peer-to-peer possible. Figma uses CRDTs for their design tool. Real-time. No conflicts. Math guarantees it.

**Example: G-Counter CRDT.** Three nodes. Node A increments: A=1, B=0, C=0. Node B increments: A=1, B=1, C=0. Merge: take max per node. A=1, B=1, C=0. Total=2. Correct. No coordination. Merge is commutative. Associative. Idempotent. Math works. For text, it's more complex. But the principle holds. Structure your data so merge is deterministic. CRDTs are that structure.

---

## Let's Walk Through the Diagram

```
REAL-TIME COLLABORATION - MERGE
+-----------------------------------------------------------------+
|                                                                  |
|   USER A                    USER B                    MERGE      |
|                                                                  |
|   Insert "X" at 5    |    Delete char at 3    |                  |
|        |             |         |               |                  |
|        v             |         v               |   OT: Transform |
|   [Local doc]        |    [Local doc]          |   ops against   |
|        |             |         |               |   each other    |
|        +-------------+---------+               |                  |
|        |             |         |               |   CRDT: Merge   |
|        v             v         v               |   by structure  |
|            [SERVER or P2P]                     |   (commutative) |
|                    |                            |                  |
|                    v                            |                  |
|            [Same document]                      |                  |
|                                                                  |
|   Key: No conflicts. Deterministic. Everyone converges.          |
|                                                                  |
+-----------------------------------------------------------------+
```

Narrate it: A and B edit. Operations flow to merge point. OT: transform. Adjust positions. Apply. CRDT: merge by structure. Same IDs. Same result. Both paths yield one document. No overwrites. No data loss. The diagram simplifies. Implementation is hard. But the concept is clear. Concurrency without coordination. That's the dream. Both OT and CRDTs achieve it. Differently.

---

## Real-World Examples (2-3)

**Google Docs.** OT. Central server. They've published papers. Real-time. Billions of edits. The gold standard for collaborative docs. Complex. But it works. They've refined it for years.

**Figma.** CRDTs. Design tool. Multiple designers. Same file. Real-time. No central bottleneck for merge. Peer sync possible. They've blogged about it. CRDTs fit their model. Your product may differ. Choose the tool for the job.

**Notion.** Collaborative. Likely OT or similar. They don't publish details. But the pattern is the same. Real-time collaboration is a product expectation now. Users demand it. Build it. Learn the approaches.

---

## Let's Think Together

**"Two users simultaneously: User A inserts 'X' at position 5. User B deletes character at position 3. Final document?"**

With OT: depends on transform rules. Typically: apply both. If delete happens first, positions shift. A's insert at "5" might now be at 4. Transform adjusts. Result: document with X in the right logical place, delete applied. With CRDT: characters have IDs. A inserts X with id_x after char_5. B deletes char_3. Merge: X is in. char_3 is out. Order determined by causal metadata (lamport clocks, vector clocks). Result: same. The exact characters depend on the original document. But the principle: both operations apply. No conflict. Merge produces one result. Deterministic. Everyone agrees. That's the goal. Achievable. With care.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup builds collaborative editing. No OT. No CRDT. Just "last write wins." User A types "Hello." User B types "World" in the same place. Last write wins. A's "Hello" gone. User A: "Where did my text go?!" Chaos. They rebuild with OT. Complex. Bugs. They eventually get it right. The lesson: don't wing it. Collaborative editing has established solutions. Use them. OT or CRDT. Don't invent. Adopt. Adapt. Implement. "Last write wins" is not collaboration. It's conflict. Users will hate it.

---

## Surprising Truth / Fun Fact

CRDTs were first formalized in 2011. The theory existed before. But the paper "Conflict-free Replicated Data Types" brought it together. Now they're in Riak, Redis (with modules), and many collaboration tools. The math is elegant. Merge functions that are commutative, associative, idempotent. Three properties. Guarantee convergence. No coordination. Distributed systems often need coordination. CRDTs show: sometimes you don't. Structure beats coordination. A profound idea. It changed how we build collaborative systems.

---

## Quick Recap (5 bullets)

- **Problem:** Concurrent edits. No central coordinator. Must converge to same document.
- **OT:** Transform operations. Central server often needed. Google Docs. Complex but proven.
- **CRDTs:** Structure data for automatic merge. No conflicts. Figma. Math guarantees convergence.
- **G-Counter example:** Each node has counter. Merge = sum. No coordination. Principle scales.
- **Choose by product:** OT for docs with central server. CRDTs for P2P or when you want structure.

---

## One-Liner to Remember

**Real-time collaboration needs merge without conflict—OT transforms operations, CRDTs structure data. Both work. Pick one. Don't use "last write wins."**

---

## Next Video

Next: messaging platform. WhatsApp. Delivery guarantees. Gray ticks. Blue ticks. How does it work?
"""

# Topic 238
TOPIC_238 = """# Messaging Platform: Delivery and Presence

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

WhatsApp. You send "Happy Birthday!" to your friend. One gray tick (sent). Two gray ticks (delivered). Two blue ticks (read). Behind the scenes: message sent to server, server stores in DB, server pushes to recipient's device, device ACKs, server updates status, sender sees double tick. If recipient is offline—message stored, pushed when they reconnect. Simple to use. Complex to build. Let's see how.

---

## The Story

User sends a message. It must arrive. At least once. Ideally exactly once. The flow: client sends to server. Server persists. Server pushes to recipient. Recipient ACKs. Server updates delivery status. Sender sees "delivered." If recipient opens the app: read receipt. Blue ticks. The status pipeline: sent -> delivered -> read. Each step requires coordination. Server is the hub. Client never talks to client directly. Always through server. Offline? Message waits in DB. When recipient connects: server pushes. Bulk. "You have 15 messages." Client fetches. Marks delivered. Replies to server. Server updates sender. The sync protocol is critical. Message IDs. Deduplication. Ordering. Get it right or users lose messages. Trust is everything in messaging.

Presence: "Is she online?" Server tracks connections. WebSocket alive = online. Disconnect = offline. Grace period: 30 seconds. Don't flip to offline on a momentary blip. "Last seen 2 min ago." Privacy: users can hide last seen. Configurable. Presence is a feature. Users care. Build it in. Scale it. Millions of connections. Server tracks them all. Efficiently.

---

## Another Way to See It

Post office. You mail a letter. Post office receives. Stores. Tries to deliver. Recipient home? Letter delivered. Receipt. Recipient away? Letter held. When they return, delivery. You can track: "In transit." "Delivered." "Picked up." Same for messaging. Server is the post office. Messages are letters. Delivery status is tracking. Offline is "recipient away." Reconnect is "recipient returned." The metaphor holds. Persistence. Retry. Status. All there.

---

## Connecting to Software

**Delivery guarantees.** At-least-once. Retry until ACK. Message might arrive twice. Deduplication on recipient: message ID. "Already have msg_123? Ignore." Exactly-once is at-least-once + dedup. Design for idempotency. Same message ID = process once. Critical for messaging. Users expect "I sent it. They got it." Not "maybe." Guarantee it.

**Message flow.** Sender -> Server -> DB (persist) -> Recipient (push via WebSocket or push notification). Always persist first. Then push. If push fails, message is in DB. Sync will deliver. Never push without persist. Never. One bug. Lost messages. User trust gone. Flow is simple. The discipline is strict. Persist. Push. ACK. Update status. In that order.

**Offline handling.** Messages queue on server. Per recipient. When they connect: "Last message ID you have?" Recipient sends. Server: "Messages after that." Returns list. Bulk deliver. Client renders. Marks delivered. ACKs. Server updates senders. Sync protocol. Define it. Version it. Clients must implement it. Old clients: graceful degradation. New clients: full sync. Compatibility matters.

**Presence.** "Online/offline/last seen." WebSocket heartbeats. Ping every 30s. No ping for 90s? Disconnect. Mark offline. "Last seen" = last activity timestamp. Update on message send/receive. Privacy: user can hide. "Nobody" or "Contacts only." Server enforces. Presence is real-time. Push to contacts when someone comes online. "Sarah is online." Exciting for social apps. Implement it well.

---

## Let's Walk Through the Diagram

```
MESSAGING - DELIVERY AND PRESENCE
+-----------------------------------------------------------------+
|                                                                  |
|   SENDER              SERVER                 RECIPIENT           |
|                                                                  |
|   [Send msg] --> Persist DB --> Push (if online) --> [Receive]  |
|        |              |                  |              |        |
|        |              |              Offline?          |        |
|        |              |                  |              |        |
|        |              v                  v              |        |
|        |         [Queue for recipient]   Reconnect     |        |
|        |              |                  |              |        |
|        |              +-----------------> Sync ---------+        |
|        |              |                  |              |        |
|        <-- Status update (delivered/read) <-------------+        |
|                                                                  |
|   PRESENCE: WebSocket = online. Disconnect = offline. Heartbeat. |
|   DELIVERY: At-least-once. Dedup by msg ID. Persist before push. |
|                                                                  |
+-----------------------------------------------------------------+
```

Narrate it: Sender sends. Server persists. Recipient online? Push. Offline? Queue. Reconnect? Sync. Bulk deliver. Status flows back. Delivered. Read. Presence: connection state. Heartbeats. Online. Offline. Last seen. The diagram shows the flow. The details: retries, ordering, idempotency. All matter. Build for production. Millions of messages. No lost. No duplicate. Users trust you. Honor it.

---

## Real-World Examples (2-3)

**WhatsApp.** Billions of users. E2E encryption. But delivery flow is the same. Persist. Push. Sync. Ticks. They scale it. The principles are universal. Encryption adds a layer. Delivery is foundational. They got it right.

**Slack.** Similar. Messages. Presence. Read receipts. Threads. Richer model. Same delivery guarantees. At-least-once. Dedup. Sync on reconnect. They've scaled to millions. The pattern works.

**Telegram.** Fast. Sync across devices. Messages persist. delivered. Read. Same architecture. Different polish. The core is identical. Learn it once. Apply everywhere.

---

## Let's Think Together

**"Group chat: 500 members. You send a message. How does the server deliver to 500 people efficiently?"**

Options. 1) Fan-out: For each member, push. 500 pushes. Per message. At 100 msg/sec = 50K pushes/sec. Doable. 2) Fan-out with batching: Don't push to each. Put message in each member's "mailbox" (queue or inbox). Workers push from mailboxes. Spread load. 3) Recipients pull: "Any new messages?" Poll or long poll. Less push load. More read load. 4) Hybrid: Online members get push. Offline: store in mailbox. On connect: sync. Most systems use fan-out to online + mailbox for offline. Scale: 500 is small. 50,000 member groups? Different. Shard. Partition. The principle: don't send 50K individual connections. Batch. Queue. Distribute. Efficient delivery is an engineering problem. Solve it. The math will guide you.

---

## What Could Go Wrong? (Mini Disaster Story)

A messaging app. No persistence. Push only. User A sends to B. B's phone is off. Message never stored. B turns on phone. No message. A: "Did you get it?" B: "No." Ghost message. User trust broken. "Your app loses messages." Fix: persist first. Always. Then push. Sync on reconnect. Every production messaging system does this. No exceptions. One shortcut. Thousands of lost messages. Support nightmare. Build it right. From day one.

---

## Surprising Truth / Fun Fact

WhatsApp's "last seen" was controversial. Users wanted to hide it. "I don't want people to know when I'm online." They added privacy settings. "Nobody." "Contacts only." "Everyone." Product decision. Technical implementation: server tracks. Client sends privacy preference. Server filters. "Can user X see user Y's last seen?" Logic in the server. Simple to describe. Complex at scale. Billions of user pairs. Cached. Optimized. The feature seems small. The engineering is not. Never underestimate "simple" features in messaging. They're rarely simple.

---

## Quick Recap (5 bullets)

- **Delivery:** At-least-once. Retry until ACK. Dedup by message ID on recipient.
- **Flow:** Sender -> Server -> Persist -> Push (or queue) -> Recipient -> ACK -> Status update.
- **Offline:** Message in DB. Sync on reconnect. Bulk deliver. Never lose a message.
- **Presence:** WebSocket = online. Heartbeats. Disconnect = offline. Last seen. Privacy options.
- **Group chat:** Fan-out to online. Mailbox for offline. Scale with batching and sharding.

---

## One-Liner to Remember

**Messaging is a post office—persist, push, retry until delivered. Presence is the front porch light—on when connected, off when not.**

---

## Next Video

Next: we've covered pipelines, queues, payments, gateways, chat, config, rate limiters, cache, feeds, collaboration, and messaging. What's next? Deep dives. Case studies. Staff-level trade-offs. The journey continues.
"""

def main():
    # Expand Topic 233
    t233_path = os.path.join(BASE, "Topic_233_Global_Rate_Limiter_Tradeoffs.md")
    with open(t233_path, "r") as f:
        t233_content = f.read()
    if "Choosing your stance" not in t233_content:
        # Add before "---" before Quick Recap
        t233_content = t233_content.replace(
            "Tolerance is a product decision. Document it. Enforce it consistently.\n\n---\n\n## What Could Go Wrong",
            "Tolerance is a product decision. Document it. Enforce it consistently." + TOPIC_233_ADDITION + "\n\n---\n\n## What Could Go Wrong"
        )
        with open(t233_path, "w") as f:
            f.write(t233_content)
        print("Expanded Topic 233")
    else:
        print("Topic 233 already expanded")

    # Create Topics 234-238
    topics = [
        ("Topic_234_Distributed_Cache_Multi_Region.md", TOPIC_234),
        ("Topic_235_News_Feed_Design.md", TOPIC_235),
        ("Topic_236_News_Feed_Backpressure.md", TOPIC_236),
        ("Topic_237_Realtime_Collaboration.md", TOPIC_237),
        ("Topic_238_Messaging_Platform_Delivery.md", TOPIC_238),
    ]
    for name, content in topics:
        path = os.path.join(BASE, name)
        with open(path, "w") as f:
            f.write(content)
        print(f"Created {name}")

if __name__ == "__main__":
    main()
