# System Design Interview Preparation for Google Staff Engineer (L6)

## Volume 3, Part 1: Consistency Models — How Staff Engineers Choose the Right Guarantees

---

# Introduction

Consistency is one of the most misunderstood concepts in distributed systems. Engineers often treat it as a binary choice—"consistent or inconsistent"—when in reality, it's a spectrum with profound implications for user experience, system complexity, and operational cost.

When a Staff Engineer is asked to design a distributed system, one of the first architectural questions is: *What consistency guarantees does this system need?* Get this wrong, and you'll either build something too slow and expensive, or something that confuses and frustrates users.

This section demystifies consistency models. We'll start with intuition—what does each model *feel like* to users?—before diving into technical details. We'll explore why Google, Facebook, Twitter, and virtually every large-scale system accepts some form of inconsistency. We'll see how Staff Engineers reason about the trade-offs, and we'll apply this thinking to real systems: rate limiters, news feeds, and messaging.

By the end, you'll have practical heuristics for choosing consistency models, and you'll be able to explain your choices in interviews with the confidence that comes from genuine understanding.

---

# Part 1: Consistency Models — Intuition First

Before we define consistency models formally, let's understand them through user experience. What does each model *feel like*?

## Strong Consistency: "What I Write, Everyone Sees Immediately"

**The experience**: You post a comment. Your friend, sitting next to you, refreshes the page. They see your comment. Always. Instantly. No exceptions.

**The mental model**: There's one true state of the data, and everyone sees it. It's as if there's a single database that everyone reads from and writes to, even though the system might be distributed across many servers.

**Real-world analogy**: A shared Google Doc. When you type a character, everyone else in the document sees it within a second. There's no "my version" vs. "your version"—there's just *the* document.

**Technical reality**: Strong consistency is expensive. It requires coordination between servers. Before a write is acknowledged, all replicas must agree. This takes time (latency) and requires all replicas to be reachable (availability risk).

## Eventual Consistency: "What I Write, Everyone Sees... Eventually"

**The experience**: You post a photo on social media. You see it immediately. Your friend, also on their phone, doesn't see it yet. A few seconds later, they do. The delay is usually unnoticeable, occasionally a few seconds, rarely a few minutes.

**The mental model**: Writes propagate through the system over time. Different observers might see different states temporarily, but given enough time (and no new writes), everyone converges to the same state.

**Real-world analogy**: Email. You send an email. The recipient doesn't see it instantly—it takes seconds to minutes to propagate through mail servers. But eventually, it arrives.

**Technical reality**: Eventual consistency is cheaper and more available. Writes can be acknowledged immediately (to one replica), and propagation happens asynchronously. But users might see stale data.

## Causal Consistency: "Cause Always Precedes Effect"

**The experience**: Alice posts "I'm getting married!" Bob comments "Congratulations!" Anyone who sees Bob's comment will definitely see Alice's original post first. You'll never see a reply without its parent.

**The mental model**: If action B was caused by action A, then anyone who sees B will also see A. Causally related events maintain their order. Unrelated events might appear in different orders to different observers.

**Real-world analogy**: A threaded email conversation. You always see the original email before the reply. But two unrelated email threads might load in different orders.

**Technical reality**: Causal consistency is a middle ground. It's cheaper than strong consistency (no global coordination) but provides more guarantees than eventual consistency (no confusing out-of-order effects).

---

## The Spectrum in Practice

These three models aren't the only options—they're points on a spectrum:

```
Strongest ←────────────────────────────────────────→ Weakest

Linearizability → Sequential → Causal → Read-your-writes → Eventual → None
     │                                        │                   │
     └── Single correct global order          │                   └── Anything goes
                                              │
                                              └── You see your own writes
```

**Linearizability (Strongest)**: All operations appear to happen atomically at a single point in time, and that order is consistent with real-time order. The gold standard, but expensive.

**Sequential Consistency**: All operations appear in some order that's consistent across all observers, but that order doesn't need to match real-time.

**Causal Consistency**: Operations that are causally related appear in order. Concurrent (unrelated) operations might appear in different orders to different observers.

**Read-Your-Writes**: You always see your own writes, but others might not see them yet. A practical middle ground.

**Eventual Consistency**: Given enough time, all replicas converge. No guarantees about what you see in the meantime.

---

## A Thought Experiment

Imagine you're at a coffee shop. You post "At my favorite coffee shop!" to social media.

| Consistency Model | What Happens |
|-------------------|--------------|
| **Strong** | You post. The app shows "Posted!" only after every data center worldwide has the post. Takes 500ms-2s. If any data center is unreachable, posting fails. |
| **Causal** | You post. Your app shows the post instantly. Others see it within seconds. If someone comments, viewers always see your post before the comment. |
| **Read-your-writes** | You post. Your app shows the post instantly. Others might not see it for a few seconds. If you refresh, you always see your post. |
| **Eventual** | You post. Your app shows "Posted!" You refresh... and the post isn't there. You panic. Refresh again, there it is. (This is bad UX.) |

Notice: The "worst" model (eventual) isn't abstractly bad—it's just wrong for this use case. For other use cases, it's perfectly fine.

---

# Part 2: What User Experience Each Consistency Model Creates

Let's get specific about how consistency models affect users.

## Strong Consistency UX

**Positive effects**:
- Users never see confusing states
- "What you see is what everyone sees"
- No refresh-to-update patterns
- Simple mental model for users

**Negative effects**:
- Higher latency on writes (waiting for coordination)
- Reduced availability (if replicas unreachable, operations fail)
- More expensive infrastructure

**Users notice when**:
- Operations feel slow
- Operations fail during network issues
- "Try again later" errors increase

**Best for**:
- Financial transactions (bank transfers)
- Inventory systems (last item in stock)
- Access control (revoking permissions)
- Anything where inconsistency = real harm

## Eventual Consistency UX

**Positive effects**:
- Low latency on writes
- High availability (can operate despite network partitions)
- Lower infrastructure cost
- Scales easily

**Negative effects**:
- Users might see stale data
- "Where did my post go?" confusion
- Different users see different states
- Need UI patterns to hide inconsistency

**Users notice when**:
- They post something and don't see it
- They and a friend see different counts (likes, comments)
- Edits seem to "disappear" then reappear

**Best for**:
- Social media feeds
- View counts and like counts
- Analytics dashboards
- Caching layers

## Causal Consistency UX

**Positive effects**:
- Cause always precedes effect (no confusing inversions)
- Lower latency than strong consistency
- Higher availability than strong consistency
- Intuitive for conversational flows

**Negative effects**:
- More complex to implement
- Unrelated items might appear out of order
- Still some "stale data" scenarios

**Users notice when**:
- (Rarely—causal consistency matches human intuition well)
- Unrelated content appears in unexpected order

**Best for**:
- Messaging and chat systems
- Comment threads
- Collaborative editing
- Order-dependent workflows

## Read-Your-Writes Consistency UX

**Positive effects**:
- Your own actions are always visible to you
- Eliminates the "where did my post go?" problem
- Lower latency than strong consistency
- Simple to implement with sticky sessions

**Negative effects**:
- Others might not see your writes yet
- Switching devices might show stale state

**Users notice when**:
- They switch devices and don't see recent actions
- Friends don't see their updates yet

**Best for**:
- User-generated content
- Profile updates
- Settings changes
- Most consumer applications

---

# Part 3: Why Large-Scale Systems Accept Inconsistency

## The CAP Theorem Reality

The CAP theorem states that during a network partition, a distributed system must choose between:

- **Consistency (C)**: Every read returns the most recent write
- **Availability (A)**: Every request receives a response (not an error)

You can't have both during a partition. And partitions happen—networks are unreliable.

**What this means in practice**:

If you choose **consistency**: During a partition, some users get errors. "Service temporarily unavailable."

If you choose **availability**: During a partition, some users get stale data. They might not notice.

For most consumer applications, occasional stale data is preferable to frequent errors. Users can tolerate seeing a like count that's 5 seconds behind. They cannot tolerate the app refusing to load.

## The Latency Trade-off

Even without partitions, strong consistency is slow.

**Why?** Before acknowledging a write, a strongly consistent system must ensure all (or a quorum of) replicas have the write. This requires:

1. Write to primary
2. Replicate to secondaries
3. Wait for acknowledgments
4. Then respond to client

**Latency math**:
- Cross-datacenter network latency: 50-200ms
- If you require acknowledgment from datacenters on multiple continents: 300-500ms minimum

For a social media "like" button, waiting 500ms is unacceptable. Users expect instant feedback.

**Eventual consistency** acknowledges immediately (write to one replica), replicates in background. Response time: 10-50ms.

## The Availability Trade-off

Strong consistency requires replicas to be reachable. If they're not:

**Option A**: Wait (potentially forever) until they're reachable
**Option B**: Return an error

Neither is good for user experience.

With eventual consistency, you write to available replicas and propagate when you can. Availability stays high even during partial outages.

## The Cost Trade-off

Strong consistency requires:
- More network bandwidth (synchronous replication)
- More powerful infrastructure (lower tolerance for delays)
- More sophisticated consensus protocols (Paxos, Raft)
- More operational expertise

This translates directly to higher infrastructure costs.

At Google/Facebook scale, the difference between strong and eventual consistency might be hundreds of millions of dollars per year.

## What Big Companies Actually Do

| Company | System | Consistency Model | Why |
|---------|--------|-------------------|-----|
| Google | Spanner (DB) | Strong (linearizable) | Worth the cost for critical data |
| Google | YouTube view counts | Eventual | Counts don't need to be exact |
| Facebook | News Feed | Eventual | Latency matters more than precision |
| Facebook | Payments | Strong | Financial accuracy is mandatory |
| Twitter | Tweet posting | Eventually consistent | Speed of posting matters |
| Twitter | User blocking | Strong | Security requires immediate effect |
| Amazon | Shopping cart | Eventually consistent | Availability > perfect state |
| Amazon | Order placement | Strong | Can't lose or duplicate orders |

**Pattern**: Use strong consistency where inconsistency causes real harm. Accept eventual consistency everywhere else.

---

# Part 4: How Staff Engineers Reason About Consistency

## The Core Question

The fundamental question is:

**"What's the cost of showing stale or inconsistent data?"**

If the cost is high (money lost, security breached, user harmed), lean toward stronger consistency.

If the cost is low (slight user confusion, eventually self-correcting), accept weaker consistency.

## Decision Heuristics

### Heuristic 1: Follow the Money

**If real money is involved, use strong consistency.**

- Bank transfers: Strong
- Payment processing: Strong
- Inventory for purchase: Strong (at checkout moment)
- Like counts: Eventual (no money involved)

### Heuristic 2: Follow the Security

**If security or access control is involved, use strong consistency.**

- Revoking user access: Strong (must be immediate)
- Permission changes: Strong
- Blocking a user: Strong
- Notification preferences: Read-your-writes (personal impact)

### Heuristic 3: User Expectation Test

**Would users be confused or upset if they saw stale data?**

- "I just posted but can't see my post" → Confusing → At least read-your-writes
- "Like count shows 42 vs 43" → Not confusing → Eventual is fine
- "I see a reply but not the original post" → Confusing → Causal needed

### Heuristic 4: The "Would They Notice?" Test

**Would the user notice the inconsistency?**

- View counts lagging by 5 seconds: Won't notice
- Their own post disappearing: Will definitely notice
- Comments appearing before posts: Will notice and be confused
- Two friends seeing different feed order: Won't notice (each person sees one version)

### Heuristic 5: Correctability Test

**Can the user or system easily correct the issue?**

- Stale view count: Self-corrects on next refresh
- Duplicate message: User confused, needs UI to dedupe
- Lost bank transfer: Cannot easily correct, catastrophic

**If self-correcting, eventual consistency is likely acceptable.**

### Heuristic 6: Read-Heavy vs. Write-Heavy

**Read-heavy operations often tolerate eventual consistency better.**

- Reads from cache: Eventual (cache might be stale)
- Writes that must be durable: Need at least local confirmation
- Read-modify-write operations: May need strong consistency to avoid lost updates

---

## Interview Articulation

When explaining consistency choices in an interview, use this structure:

1. **State the choice**: "For this data, I'm choosing eventual consistency."
2. **State the rationale**: "Because inconsistency here doesn't cause harm—users won't notice if like counts are a few seconds behind."
3. **Acknowledge the trade-off**: "This gives us better latency and availability at the cost of occasional staleness."
4. **Describe the user experience**: "In practice, a user might see 42 likes while their friend sees 43. Neither is wrong; they're both recent values."
5. **Contrast with alternatives**: "If we used strong consistency here, writes would be 500ms slower, which would feel sluggish when liking content."

---

# Part 5: Common Mistakes When Choosing Strong Consistency

## Mistake 1: Defaulting to Strong "Because It's Safer"

**The thinking**: "I don't want data issues, so I'll use strong consistency everywhere."

**The problem**: You're paying latency, availability, and cost penalties for safety you don't need.

**Example**: Using strongly consistent database for website analytics. Analytics are approximations anyway—nobody cares if pageview counts are off by 0.1%.

**Staff-level thinking**: Strong consistency is a tool, not a default. Use it where the cost of inconsistency exceeds the cost of consistency.

## Mistake 2: Not Understanding What "Strong" Actually Means

**The thinking**: "I'll use a replicated database, so it's consistent."

**The problem**: Replication ≠ consistency. Async replication is eventually consistent. Sync replication to all replicas is strongly consistent. Many databases default to async.

**Example**: Assuming PostgreSQL with streaming replication is strongly consistent. By default, it's not—reads from replicas might be behind.

**Staff-level thinking**: Know exactly what consistency your infrastructure provides. Configure it explicitly.

## Mistake 3: Ignoring Read Paths

**The thinking**: "Writes go to a single primary, so we're consistent."

**The problem**: If reads go to replicas, and replicas lag, you're eventually consistent for reads even with single-writer.

**Example**: Writing to primary PostgreSQL, reading from replica. User writes, then reads from replica, doesn't see their write.

**Staff-level thinking**: Trace the full read and write paths. Consistency depends on both.

## Mistake 4: Using Strong Consistency and Accepting High Latency

**The thinking**: "Consistency is important, so we'll accept 2-second writes."

**The problem**: Users will hate the experience. 2-second delays feel broken.

**Better approach**: Reconsider whether strong consistency is actually needed. Or use techniques like optimistic UI (show the change immediately, reconcile later).

**Staff-level thinking**: Never accept user-hostile latency without questioning the underlying requirement.

## Mistake 5: Ignoring Partial Failure Scenarios

**The thinking**: "Our strongly consistent system will never show stale data."

**The problem**: During network partitions or high load, strongly consistent systems often return errors. Users might cache or retry, leading to stale client state.

**Example**: Strongly consistent checkout fails during partition. User retries with stale cart data. Order is wrong.

**Staff-level thinking**: Plan for failures. Strongly consistent systems fail "safely" (with errors), but you still need to handle those errors gracefully.

## Mistake 6: Mixing Consistency Requirements in One Request

**The thinking**: "This API returns user profile and like counts, so we need strong consistency for both."

**The problem**: Profile might need strong; like counts don't. You're paying for strong consistency on data that doesn't need it.

**Better approach**: Separate the data by consistency requirement. Fetch profile from primary; fetch counts from cache.

**Staff-level thinking**: Design APIs around consistency boundaries, not arbitrary data groupings.

---

# Part 6: Applying Consistency Choices to Real Systems

Let's apply this thinking to three systems: rate limiter, news feed, and messaging.

## System 1: Rate Limiter

### The System

A rate limiter controls how many requests a client can make in a time window. At scale:
- 1M+ requests/second
- Distributed across many servers
- Each request must check and increment a counter

### Consistency Question

When a request arrives, we check if the client is within limits. This requires:
1. Read current counter
2. Check against limit
3. Increment counter

**Should this be strongly consistent?**

### Analysis

**If strongly consistent**:
- Every server agrees on exact count
- Never allows a single request over limit
- Requires distributed consensus on every request
- Latency: 10-100ms per check (unacceptable—rate limiter must be <1ms)
- Availability: If coordination fails, rate limiting fails

**If eventually consistent**:
- Servers have local counters, sync periodically
- Might allow 5-10% over limit during sync windows
- Latency: <1ms (local operation)
- Availability: Works even during partitions

### The Right Choice

**Eventual consistency is the right choice.**

**Reasoning**:
1. Rate limiting is approximate by nature—the goal is preventing abuse, not exact enforcement
2. Being 5% over limit occasionally is acceptable; 100ms latency is not
3. Availability matters more—if rate limiter fails, we should fail open (allow requests) rather than block everything

### What Breaks with Strong Consistency

If we insisted on strong consistency:
- Rate check adds 50-100ms to every request
- During network partitions, rate limiter errors, affecting all requests
- System becomes the bottleneck it was meant to prevent

### Interview Articulation

"For the rate limiter, I'm choosing eventual consistency. Rate limiting is inherently approximate—we're protecting against abuse, not implementing a billing system. I'm accepting that limits might be slightly exceeded during counter synchronization. The alternative—strong consistency—would add unacceptable latency to every request and create an availability risk. The trade-off of ~5% over-limit occasionally is worth the <1ms check latency."

---

## System 2: News Feed

### The System

A news feed shows personalized content:
- User follows accounts, sees their posts
- Posts are ranked by relevance and recency
- Feed loads must be fast (<300ms)

### Consistency Questions

Several consistency questions arise:

1. **When a user posts, when should followers see it?**
2. **When a post is deleted, how quickly should it disappear?**
3. **What about like/comment counts?**
4. **What about user preferences (muting an account)?**

### Analysis

**Post visibility (eventual is fine)**:
- Delay of 30-60 seconds is unnoticeable
- Strong consistency would require synchronous fan-out to millions of followers
- Users don't expect instant appearance in others' feeds

**Post deletion (needs to be faster)**:
- User expects deleted content to disappear "quickly"
- Eventual with short window (5-10 seconds) is acceptable
- Strong consistency is overkill—users tolerate brief visibility

**Like/comment counts (eventual is fine)**:
- Counts are approximate anyway (rounding, display)
- Users don't compare counts in real-time
- No harm from 5-second staleness

**User preferences (needs read-your-writes)**:
- If I mute an account, I expect it to take effect immediately
- I should not see posts from that account after muting
- But others don't see my preferences at all, so no global consistency needed

### The Right Choice

| Data | Consistency Model | Latency Target |
|------|-------------------|----------------|
| Post in followers' feeds | Eventual | < 60 seconds |
| Post deletion | Eventual (fast) | < 10 seconds |
| Like/comment counts | Eventual | < 5 seconds |
| User preferences | Read-your-writes | Immediate |

### What Breaks with Strong Consistency

If we insisted on strong consistency for post visibility:
- Publishing a post requires writing to millions of feeds synchronously
- A user with 10M followers → 10M synchronous writes → minutes to publish
- During any network issue, publishing fails completely

**Specific failure scenario**:
- Celebrity tweets "Breaking news!"
- Strong consistency: System attempts synchronous fan-out to 50M followers
- One data center is slow
- Tweet is not acknowledged for 30+ seconds
- Celebrity sees "Posting..." spinner
- Celebrity rage-quits to competitor platform

### Interview Articulation

"The news feed has different consistency needs for different data. For post visibility in followers' feeds, I'm using eventual consistency with ~60 second target. The alternative—synchronous fan-out—would make posting take minutes for users with many followers.

For user preferences like muting, I need read-your-writes consistency. If a user mutes an account, they must stop seeing posts from it immediately. But this is session-local—I just need to ensure the user's own session sees the update, not global consistency.

For engagement counts, eventual consistency is fine. Users don't notice if like counts are a few seconds behind."

---

## System 3: Messaging System

### The System

A real-time messaging system:
- 1:1 and group conversations
- Messages should appear in order
- Delivery should be reliable

### Consistency Questions

1. **What order should messages appear in?**
2. **What if sender and receiver see different orders?**
3. **What about read receipts?**
4. **What about message delivery guarantees?**

### Analysis

**Message ordering (causal consistency needed)**:
- If Alice says "Want to get dinner?" and Bob replies "Sure!", everyone must see these in order
- Showing reply before question is confusing
- Causal consistency ensures cause precedes effect

**Cross-conversation ordering (eventual is fine)**:
- Messages in different conversations don't need to be ordered relative to each other
- Alice's chat with Bob and Alice's chat with Carol are independent

**Read receipts (eventual is fine)**:
- "Seen" status can lag by seconds
- Users don't expect instantaneous read receipts
- Strong consistency would complicate multi-device sync

**Message delivery (at-least-once, not exactly-once)**:
- Losing messages is unacceptable
- Occasional duplicates are tolerable (UI can dedupe)
- Exactly-once requires distributed transactions—too expensive

### The Right Choice

| Data | Consistency Model | Notes |
|------|-------------------|-------|
| Messages within conversation | Causal | Replies after originals |
| Messages across conversations | Eventual | No ordering required |
| Read receipts | Eventual | 1-5 second lag acceptable |
| Delivery | At-least-once | Durability over exactly-once |

### What Breaks with Wrong Choice

**If we used eventual consistency for message ordering**:
- Bob's "Sure!" might appear before Alice's "Want to get dinner?"
- Conversation is confusing
- Users lose trust in the system

**If we used strong consistency for everything**:
- Every message requires global coordination
- Latency increases from 50ms to 500ms
- Messaging feels sluggish
- During partitions, messages fail to send

**Specific failure scenario (eventual ordering)**:
- Alice: "I'm breaking up with you."
- Bob: "I love you too!" (sent before seeing Alice's message)
- Alice sees Bob's "I love you too!" first, then her own message
- Disaster. The UI shows an impossible conversation.

### Interview Articulation

"For the messaging system, I'm using causal consistency within conversations. Messages must appear in causal order—a reply after its parent, an acknowledgment after the original. Without this, conversations become nonsensical.

Across conversations, I'm using eventual consistency. There's no need for global ordering between unrelated chats.

For read receipts, I'm using eventual consistency. Users don't expect 'seen' status to be instantaneous, and the complexity of strong consistency isn't worth it for this data.

For delivery, I'm guaranteeing at-least-once. I'd rather have occasional duplicates (which the UI can hide) than ever lose a message. Exactly-once would require distributed transactions that would hurt latency."

---

# Part 7: What Breaks When the Wrong Model Is Chosen

Let's explore specific failure scenarios when systems choose the wrong consistency model.

## Scenario 1: Strong Consistency for High-Throughput Writes

**System**: Rate limiter with strong consistency

**What happens**:
1. Rate limiter uses Raft consensus for counter updates
2. Each request requires quorum agreement: 50-100ms
3. At 1M requests/second, each rate check takes 50ms
4. Total added latency: 50ms × requests = unusable system
5. During leader election (few seconds), all rate checks fail
6. Either system blocks all requests or allows all (fail-open)

**The lesson**: High-throughput, low-latency systems cannot use strong consistency on the hot path.

## Scenario 2: Eventual Consistency for Financial Data

**System**: Payment processor with eventual consistency

**What happens**:
1. User initiates transfer of $1000
2. Write is accepted to local replica
3. User checks balance on different replica—still shows $1000
4. User initiates another transfer of $1000
5. Both transfers complete
6. User overdrafts by $1000

**The lesson**: Financial data requires strong consistency (or careful application-level compensation).

## Scenario 3: No Causal Consistency in Messaging

**System**: Chat application with plain eventual consistency

**What happens**:
1. In a group chat, Alice asks "Who wants pizza?"
2. Bob replies "Me!"
3. Carol sees: "Me!" then "Who wants pizza?"
4. Carol is confused—who is "me" and what do they want?
5. Over time, users lose trust in the app
6. Users switch to competitors

**The lesson**: Conversations require causal ordering.

## Scenario 4: Strong Consistency for Non-Critical Data

**System**: Social media platform using strong consistency for like counts

**What happens**:
1. Every like requires distributed consensus
2. Like button has 300ms delay
3. Users perceive the app as slow
4. During network issues, likes fail entirely
5. Users complain about "buggy" like button
6. Engagement metrics tank

**The lesson**: Don't use strong consistency for data that doesn't need it.

## Scenario 5: Eventual Consistency Without Read-Your-Writes

**System**: User profile updates with pure eventual consistency

**What happens**:
1. User updates profile picture
2. User refreshes profile page
3. Old picture still shows
4. User confused—"Did my update fail?"
5. User uploads again
6. Eventually sees doubled updates or gives up
7. Support tickets about "broken" profile updates

**The lesson**: User-initiated changes need at least read-your-writes consistency.

---

# Part 8: Decision Framework Summary

## The Complete Heuristic

When choosing a consistency model, work through this decision tree:

```
1. Does inconsistency cause financial harm?
   YES → Strong consistency
   NO → Continue

2. Does inconsistency cause security/access control issues?
   YES → Strong consistency (for security data)
   NO → Continue

3. Would users notice and be confused by inconsistency?
   YES, significantly → Consider causal or read-your-writes
   YES, slightly → Eventual with short windows
   NO → Eventual consistency

4. Is this data causally related (replies, reactions to content)?
   YES → Causal consistency
   NO → Continue

5. Is this data the user's own actions?
   YES → At least read-your-writes
   NO → Eventual consistency

6. Is latency critical (user waiting)?
   YES → Lean toward eventual consistency
   NO → Can afford stronger consistency
```

## Quick Reference Table

| Use Case | Recommended Model | Key Reason |
|----------|-------------------|------------|
| Bank transfers | Strong | Money at stake |
| Access control changes | Strong | Security at stake |
| Message ordering in chat | Causal | Conversations must make sense |
| User's own posts/updates | Read-your-writes | Avoid "where did it go?" |
| Social engagement counts | Eventual | Not critical, high volume |
| View counters | Eventual | Approximate is fine |
| News feed content | Eventual | Staleness acceptable |
| Rate limit counters | Eventual | Approximate enforcement ok |
| User preferences | Read-your-writes | User expects immediate effect |
| Comment threads | Causal | Replies after parents |
| Inventory at browse | Eventual | Exact count not critical |
| Inventory at checkout | Strong | Prevent overselling |

---

# Brainstorming Questions

## Understanding Consistency

1. You're designing a collaborative document editor (like Google Docs). What consistency model do you need for keystrokes? For cursor positions? For document history?

2. A social network shows "3 of your friends liked this." Does this need strong consistency? What's the user impact of slight inaccuracy?

3. You're building a ride-sharing app. What consistency is needed for driver location? For trip assignment? For payment processing?

4. Consider a recommendation system ("Users who bought X also bought Y"). Does this need real-time consistency? Why or why not?

5. You're designing a leaderboard for a mobile game. What consistency model is appropriate? Does it change for top-10 vs. full leaderboard?

## Reasoning About Trade-offs

6. A product manager asks for "real-time" like counts. How do you push back? What questions do you ask?

7. You're building a system that's eventually consistent. How do you test it? How do you verify the "eventual" part works?

8. When would you choose causal consistency over read-your-writes? When would you choose the opposite?

9. You have a globally distributed system with data centers on 5 continents. What's the minimum latency for strongly consistent writes? How does this inform your consistency choice?

10. Your eventually consistent system has a bug where data occasionally never converges. How would you detect this? How would you fix it?

## System-Specific

11. For a messaging system, what's more important: guaranteed delivery or guaranteed ordering? Can you have both?

12. In a news feed, you show "Posted 5 minutes ago." The actual time was 5 minutes and 30 seconds. Is this a consistency issue? Does it matter?

13. For a rate limiter, you allow 5% over-limit during distributed counter sync. A client exploits this by rapidly switching between servers. How do you handle it?

14. Your eventually consistent system sometimes shows deleted content. How do you minimize this? What's the trade-off?

15. You're migrating from strong to eventual consistency for a system. What do you need to change in the application layer? What might break?

---

# Homework Exercises

## Exercise 1: Redesign Under Stricter Consistency

Take the news feed system designed with eventual consistency.

Redesign it with the constraint: **Posts must appear in followers' feeds within 1 second with strong consistency guarantees.**

Address:
- How does the architecture change?
- What's the impact on latency?
- What's the impact on availability during partitions?
- What's the infrastructure cost difference?
- Is this even feasible at 200M DAU?

Write a 2-page design document with your analysis.

## Exercise 2: Identify Consistency Requirements

For each system, identify the consistency model needed for each type of data:

**System A: E-commerce Platform**
- Product catalog
- Shopping cart
- Inventory counts
- Order placement
- Order history
- Reviews and ratings

**System B: Online Multiplayer Game**
- Player position in game world
- Player inventory
- Match results
- Leaderboards
- Chat messages
- Friend list

Create a table for each system with data type, consistency model, and justification.

## Exercise 3: Failure Scenario Analysis

For the messaging system with causal consistency:

1. Describe 3 specific failure scenarios that could cause messages to appear out of order
2. For each, explain how the system should detect and recover
3. What monitoring/alerting would you implement?
4. What's the user experience during each failure?

## Exercise 4: Consistency Migration

You're inheriting a system that uses strong consistency everywhere. The system is slow and expensive, and you've been asked to optimize.

1. How do you identify which data can use weaker consistency?
2. What questions do you ask stakeholders?
3. How do you validate that weaker consistency is acceptable?
4. How do you migrate without breaking existing functionality?
5. What tests do you write?

Create a migration plan outline.

## Exercise 5: Interview Practice

Practice explaining consistency trade-offs for 3 different systems:

For each system, practice a 3-minute explanation that covers:
- What consistency model you chose
- Why (with specific reasoning)
- What you're trading off
- What user experience this creates

Systems:
1. A banking application
2. A social media platform
3. A real-time collaborative whiteboard

Record yourself or practice with a partner. Focus on clarity and structure.

---

# Conclusion

Consistency is not a binary choice—it's a spectrum of trade-offs. Staff Engineers understand this spectrum deeply and make intentional choices based on:

- **User experience**: What does each model feel like to users?
- **Business requirements**: Where does inconsistency cause real harm?
- **Technical constraints**: What's the latency and availability cost of stronger consistency?
- **Operational complexity**: How hard is each model to implement and debug?

The key insights from this section:

1. **Strong consistency is expensive.** Don't use it where you don't need it.

2. **Eventual consistency is usually acceptable.** Most data tolerates brief staleness.

3. **Causal consistency is underrated.** It prevents confusing user experiences without the full cost of strong consistency.

4. **Read-your-writes is often the sweet spot.** Users see their own actions immediately; propagation to others can be eventual.

5. **Match consistency to data, not to systems.** Different data in the same system can have different consistency requirements.

6. **Always ask: "What breaks if this data is stale?"** The answer guides your choice.

In interviews, demonstrate this nuanced understanding. Don't just choose a consistency model—explain *why* you chose it, what you're trading off, and what the user experience will be. That's Staff-level thinking.

---

*End of Volume 3, Part 1*


# Volume 3, Part 2: Replication and Sharding — Scaling Without Losing Control

## A Staff Engineer's Field Guide to Distributed Data

---

# Table of Contents

1. [Introduction: The Uncomfortable Truth About Scale](#introduction)
2. [Replication: Beyond Just Availability](#replication-beyond-availability)
3. [Leader-Follower Replication: The Workhorse Model](#leader-follower-replication)
4. [Multi-Leader Replication: Power and Peril](#multi-leader-replication)
5. [Read Replicas: The Hidden Complexity](#read-replicas)
6. [Sharding Fundamentals](#sharding-fundamentals)
7. [Hash-Based Sharding](#hash-based-sharding)
8. [Range-Based Sharding](#range-based-sharding)
9. [Hybrid Sharding Strategies](#hybrid-sharding)
10. [Hot Partitions and Skew: The Silent Killers](#hot-partitions)
11. [Re-sharding and Migration: Walking on a Tightrope](#resharding)
12. [Case Study: Evolving a User Data Store](#case-study-user-data)
13. [Case Study: Rate Limiter Counters at Scale](#case-study-rate-limiter)
14. [Case Study: Feed Storage Architecture](#case-study-feed-storage)
15. [Failure Modes Encyclopedia](#failure-modes)
16. [Staff-Level Trade-offs: The Decision Framework](#staff-tradeoffs)
17. [Brainstorming Questions](#brainstorming)
18. [Homework: Design and Defend](#homework)

---

<a name="introduction"></a>
# 1. Introduction: The Uncomfortable Truth About Scale

There's a moment in every engineer's career when they realize that the elegant single-node database they lovingly deployed is becoming the bottleneck that wakes them up at 3 AM. The uncomfortable truth? Scaling data stores is not about adding more machines—it's about **fundamentally restructuring how you think about data**.

I've seen this movie play out hundreds of times at Google. A team starts with a simple PostgreSQL instance. It works beautifully for months, maybe years. Then traffic doubles. Then it doubles again. Suddenly, you're not sleeping, your on-call rotation is a nightmare, and someone proposes "let's just add replicas."

**That's when things get interesting.**

Replication and sharding are not features you bolt on. They are **architectural decisions that ripple through every layer of your system**. Get them wrong, and you'll spend the next two years untangling the mess. Get them right, and you'll wonder why you ever worried about scale.

This document is about getting them right. Not the theoretical right—the **production right**. The kind of right that survives:
- Traffic spikes on Black Friday
- An engineer accidentally deleting a shard
- A network partition during your product launch
- The chaos of re-sharding while serving millions of requests per second

Let's begin.

---

<a name="replication-beyond-availability"></a>
# 2. Replication: Beyond Just Availability

Ask a junior engineer why we replicate data, and they'll tell you: "For availability. If one machine dies, we have copies."

That's true. But it's the tip of the iceberg.

## The Five Purposes of Replication

### 1. High Availability (The Obvious One)
When your primary node fails, a replica can take over. This is table stakes for any production system.

### 2. Geographic Distribution
Users in Tokyo shouldn't wait for a round-trip to Virginia. Replicas placed strategically reduce latency dramatically.

```
User Request Latency (Read):
┌─────────────────────────────────────────────────────────────┐
│ Tokyo User → Virginia Primary:        ~150ms                │
│ Tokyo User → Tokyo Replica:           ~5ms                  │
│                                                             │
│ Difference: 30x improvement                                 │
└─────────────────────────────────────────────────────────────┘
```

### 3. Read Scaling
A single node can only serve so many queries per second. Five replicas? That's potentially 5x read throughput (with caveats we'll discuss).

### 4. Workload Isolation
Your analytics team wants to run expensive queries. Do you want them competing with your production traffic? Dedicated replicas solve this.

```
┌─────────────────┐     ┌─────────────────┐
│  OLTP Primary   │────▶│  OLAP Replica   │
│  (User Traffic) │     │  (Analytics)    │
└─────────────────┘     └─────────────────┘
        │
        ▼
┌─────────────────┐
│  Read Replica   │
│  (API Traffic)  │
└─────────────────┘
```

### 5. Disaster Recovery
Your entire datacenter catches fire. (This has happened.) Replicas in other regions mean you're not looking for a new job tomorrow.

## The Replication Tax

Nothing is free. For every benefit, you pay a cost:

| Benefit | Cost |
|---------|------|
| Availability | Complexity in failover logic |
| Geo-distribution | Consistency challenges across WAN |
| Read scaling | Stale reads, replication lag |
| Workload isolation | Infrastructure cost, sync overhead |
| Disaster recovery | Cross-region bandwidth, data residency concerns |

**Staff Engineer Insight:** The question is never "should we replicate?" It's "what trade-offs are acceptable for our use case?" Document these trade-offs explicitly. Future you will thank present you.

---

<a name="leader-follower-replication"></a>
# 3. Leader-Follower Replication: The Workhorse Model

The most common replication topology is leader-follower (also called master-slave, primary-replica, or master-standby). Its prevalence is not accidental—it provides a clear mental model with well-understood trade-offs.

## How It Works

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          LEADER-FOLLOWER TOPOLOGY                        │
└──────────────────────────────────────────────────────────────────────────┘

                            ┌─────────────┐
                  Writes───▶│   LEADER    │
                            │  (Primary)  │
                            └──────┬──────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
                    ▼              ▼              ▼
              ┌──────────┐  ┌──────────┐   ┌──────────┐
              │ Follower │  │ Follower │   │ Follower │
              │    #1    │  │    #2    │   │    #3    │
              └──────────┘  └──────────┘   └──────────┘
                    │              │              │
                    └──────────────┼──────────────┘
                                   │
                                   ▼
                            [Read Traffic]
```

1. **All writes go to the leader**. This is the single source of truth.
2. **The leader streams changes to followers**. This can be synchronous or asynchronous.
3. **Reads can go to any node**. Typically followers handle read traffic.

## Synchronous vs. Asynchronous Replication

This is where it gets interesting.

### Synchronous Replication

```
Client          Leader         Follower
   │               │               │
   │──── Write ───▶│               │
   │               │── Replicate ─▶│
   │               │               │
   │               │◀── ACK ───────│
   │◀── Success ───│               │
   │               │               │
```

**Guarantees:** If the write succeeds, at least one follower has the data.

**Cost:** Latency. Every write waits for at least one follower to confirm. If that follower is across the world? Your writes are slow.

**Use when:** Data loss is absolutely unacceptable. Financial transactions. Critical user data.

### Asynchronous Replication

```
Client          Leader         Follower
   │               │               │
   │──── Write ───▶│               │
   │◀── Success ───│               │
   │               │               │
   │               │── Replicate ─▶│ (happens later)
   │               │               │
```

**Guarantees:** The leader accepted your write. That's it.

**Cost:** If the leader fails before replication completes, data is lost.

**Use when:** Performance matters more than durability for recent writes. Social media posts. Analytics data.

### Semi-Synchronous (The Practical Middle Ground)

Most production systems use semi-synchronous replication:
- Wait for **at least one** follower to confirm
- Other followers can replicate asynchronously

This gives you durability without waiting for your slowest replica.

```python
# Conceptual model of semi-synchronous commit
class ReplicationManager:
    def commit_write(self, data):
        # Write to leader's log
        self.leader.write(data)
        
        # Wait for at least one follower
        acks = []
        for follower in self.followers:
            try:
                acks.append(follower.replicate(data, timeout=50ms))
                if len(acks) >= 1:
                    break  # Got our guarantee
            except TimeoutError:
                continue
        
        if len(acks) == 0:
            raise ReplicationFailure("No followers acknowledged")
        
        # Async replicate to remaining followers
        for follower in self.remaining_followers:
            schedule_async(follower.replicate, data)
        
        return Success
```

## Failover: Where Things Get Real

The leader dies. Now what?

### Automatic Failover

```
┌────────────────────────────────────────────────────────────────────────┐
│                         FAILOVER SEQUENCE                              │
└────────────────────────────────────────────────────────────────────────┘

Time T0: Leader failure detected
         ┌─────────┐                   
         │ LEADER  │ ✖ (failed)        
         └─────────┘                   
              │                        
    ┌─────────┴─────────┐              
    ▼                   ▼              
┌──────────┐     ┌──────────┐          
│ Follower │     │ Follower │          
│    #1    │     │    #2    │          
└──────────┘     └──────────┘          

Time T1: Election begins
         - Followers compare replication positions
         - Most up-to-date follower wins

Time T2: New leader elected
              ┌──────────┐             
              │  NEW     │             
              │ LEADER   │ (was Follower #1)
              └──────────┘             
                   │                   
                   ▼                   
              ┌──────────┐             
              │ Follower │ (was #2)    
              └──────────┘             

Time T3: Clients redirected to new leader
```

### The Split-Brain Problem

What if the leader didn't actually die—it's just network-partitioned?

```
┌────────────────────────────────────────────────────────────────────────┐
│                         SPLIT BRAIN SCENARIO                           │
└────────────────────────────────────────────────────────────────────────┘

           Network Partition
                  ║
    Zone A        ║        Zone B
                  ║
  ┌─────────┐     ║     ┌─────────┐
  │ LEADER  │     ║     │ "NEW"   │
  │ (thinks │     ║     │ LEADER  │
  │  it's   │     ║     │ (elected│
  │  alive) │     ║     │  during │
  └─────────┘     ║     │ partition)
       │          ║     └─────────┘
       ▼          ║          │
   [Writes]       ║          ▼
                  ║      [Writes]

   DANGER: Two sources of truth!
```

**Solutions:**
1. **Fencing:** The old leader must be forcibly shut down before the new one accepts writes (STONITH - "Shoot The Other Node In The Head")
2. **Quorum-based writes:** Require acknowledgment from majority of nodes
3. **Lease-based leadership:** Leaders hold time-limited leases that must be renewed

**Staff Engineer Insight:** I've seen split-brain incidents corrupt years of data. Always test your failover. Never assume it works. Run chaos engineering exercises quarterly.

---

<a name="multi-leader-replication"></a>
# 4. Multi-Leader Replication: Power and Peril

Sometimes leader-follower isn't enough. If you have:
- Users distributed globally who need low-latency writes
- Multiple datacenters that need to operate independently
- Offline-capable applications (mobile apps, for instance)

You might consider multi-leader replication.

## The Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                      MULTI-LEADER TOPOLOGY                             │
└────────────────────────────────────────────────────────────────────────┘

      US-WEST                                      EU-WEST
   ┌───────────┐                               ┌───────────┐
   │  LEADER   │◀══════════════════════════════│  LEADER   │
   │     A     │                               │     B     │
   │           │══════════════════════════════▶│           │
   └─────┬─────┘                               └─────┬─────┘
         │                                           │
    ┌────┴────┐                                 ┌────┴────┐
    ▼         ▼                                 ▼         ▼
┌───────┐ ┌───────┐                        ┌───────┐ ┌───────┐
│Follow-│ │Follow-│                        │Follow-│ │Follow-│
│ er A1 │ │ er A2 │                        │ er B1 │ │ er B2 │
└───────┘ └───────┘                        └───────┘ └───────┘

         US Users write here         EU Users write here
```

Each datacenter has its own leader. Leaders replicate to each other asynchronously.

## The Conflict Problem

This is where multi-leader becomes terrifying.

```
Timeline of Conflict:
─────────────────────────────────────────────────────────────────────────
Time    US-WEST Leader              EU-WEST Leader
─────────────────────────────────────────────────────────────────────────
T1      User sets name = "Alice"    
T2                                  Same user sets name = "Alicia"
T3      Replicates to EU ──────────▶ Receives: name = "Alice"
T4      Receives: name = "Alicia" ◀────────── Replicates to US

        CONFLICT: Which value wins?
─────────────────────────────────────────────────────────────────────────
```

### Conflict Resolution Strategies

#### 1. Last-Write-Wins (LWW)
Attach a timestamp to each write. Higher timestamp wins.

```python
def resolve_lww(local_write, remote_write):
    if remote_write.timestamp > local_write.timestamp:
        return remote_write
    return local_write
```

**Problem:** Timestamps can be skewed. Clock synchronization is hard. You can lose writes silently.

#### 2. Merge Function
Define custom logic to merge conflicts.

```python
def resolve_merge(local_write, remote_write):
    # For a shopping cart, merge items
    merged_cart = set(local_write.items) | set(remote_write.items)
    return Cart(items=merged_cart)
```

**Problem:** Not all data has meaningful merge semantics.

#### 3. Record All Versions (Application Resolution)
Keep both versions, let the application or user decide.

```python
def resolve_multi_value(local_write, remote_write):
    return ConflictedValue(
        versions=[local_write, remote_write],
        requires_resolution=True
    )
```

**Problem:** Complexity pushed to application layer. Users hate resolving conflicts.

#### 4. CRDTs (Conflict-free Replicated Data Types)
Mathematical structures designed to merge without conflicts.

```
Examples of CRDTs:
─────────────────────────────────────────────────────────────────────────
Type                    Use Case                    Merge Strategy
─────────────────────────────────────────────────────────────────────────
G-Counter              Page views, likes            Sum all increments
PN-Counter             Inventory levels             Track add/remove
G-Set                  Tag collections              Union of elements
OR-Set                 Mutable sets                 Track adds with IDs
LWW-Register           Single values                Timestamp-based
─────────────────────────────────────────────────────────────────────────
```

**Staff Engineer Insight:** Multi-leader replication is a Pandora's box. Open it only when you must. I've seen teams spend years debugging conflict resolution bugs. If you go this route, invest heavily in conflict monitoring and alerting.

---

<a name="read-replicas"></a>
# 5. Read Replicas: The Hidden Complexity

"Just add read replicas" is the siren song of scaling. It sounds simple. It's not.

## The Replication Lag Problem

```
┌────────────────────────────────────────────────────────────────────────┐
│                       REPLICATION LAG TIMELINE                         │
└────────────────────────────────────────────────────────────────────────┘

Time  │  Leader              Replica              User Experience
──────┼──────────────────────────────────────────────────────────────────
T0    │  Write: balance=100                       
T1    │                                           User: Update balance to 50
T2    │  balance=50                               
T3    │                                           User: Refresh page (hits replica)
T4    │                       balance=100         User sees: balance=100 (!!)
T5    │                       balance=50          (replication catches up)

User thinks the update failed. Submits again. Chaos ensues.
```

## Consistency Models with Replicas

### Read-Your-Writes Consistency
Users always see their own writes. Critical for user-facing applications.

```python
class ReadYourWritesRouter:
    def __init__(self):
        self.user_last_write = {}  # user_id -> (timestamp, leader_id)
    
    def route_read(self, user_id, query):
        last_write = self.user_last_write.get(user_id)
        
        if last_write:
            timestamp, leader_id = last_write
            
            # Option 1: Route to leader for recent writes
            if time.now() - timestamp < CONSISTENCY_WINDOW:
                return self.leader.execute(query)
            
            # Option 2: Wait for replica to catch up
            replica = self.select_replica()
            if replica.replication_position < timestamp:
                wait_for_replication(replica, timestamp)
        
        return self.any_replica.execute(query)
```

### Monotonic Reads
Users never see time go backwards. Each subsequent read returns the same or newer data.

```python
class MonotonicReadsRouter:
    def __init__(self):
        self.user_read_position = {}  # user_id -> last_seen_position
    
    def route_read(self, user_id, query):
        last_position = self.user_read_position.get(user_id, 0)
        
        # Find a replica that's caught up to user's last read
        for replica in self.replicas:
            if replica.replication_position >= last_position:
                result = replica.execute(query)
                self.user_read_position[user_id] = replica.replication_position
                return result
        
        # Fallback to leader if no replica is caught up
        return self.leader.execute(query)
```

### Causal Consistency
If operation A happened before operation B, everyone sees A before B.

```
Causal Dependency Example:
─────────────────────────────────────────────────────────────────────────
User A posts: "I'm getting married!"        (Post ID: 100)
User B comments: "Congratulations!"          (Comment on Post 100)

Without causal consistency, some users might see the comment
before the post, which makes no sense.
─────────────────────────────────────────────────────────────────────────
```

## Read Replica Anti-Patterns

### Anti-Pattern 1: Using Replicas for Write-After-Read

```
BAD:
1. Read user balance from replica: $100
2. Calculate new balance: $100 - $50 = $50
3. Write new balance to leader: $50

PROBLEM: Replica might be stale. User might have $200 by now.
         You just wrote incorrect data.
```

### Anti-Pattern 2: Caching Stale Data from Replicas

```
BAD:
1. Read product price from replica: $19.99
2. Cache for 1 hour
3. Price changed to $24.99 on leader
4. Users buy at wrong price for up to 1 hour

SOLUTION: Include replication position in cache key
          or use cache invalidation from leader
```

### Anti-Pattern 3: Load Balancing Without Awareness

```
BAD:
Request 1 → Replica A (position: 1000)  → sees balance: $100
Request 2 → Replica B (position: 900)   → sees balance: $150 (old!)

SOLUTION: Sticky sessions or position-aware routing
```

---

<a name="sharding-fundamentals"></a>
# 6. Sharding Fundamentals

When replication isn't enough—when you've added all the read replicas you can and you're still hitting write throughput limits—you need to shard.

Sharding (also called partitioning) splits your data across multiple independent databases. Each shard holds a subset of the data.

## Why Shard?

```
Single Node Limits:
─────────────────────────────────────────────────────────────────────────
Resource          Typical Limit       Symptom
─────────────────────────────────────────────────────────────────────────
Disk IOPS         50,000/sec          Query latency spikes
Write throughput  10,000 TPS          Write queue grows
Data size         10TB                Backup takes 12+ hours
Memory            512GB               Indexes don't fit
CPU               64 cores            Background jobs starve
─────────────────────────────────────────────────────────────────────────
```

Sharding breaks these limits by distributing load.

## The Sharding Decision Framework

```
┌────────────────────────────────────────────────────────────────────────┐
│                    SHOULD YOU SHARD? DECISION TREE                     │
└────────────────────────────────────────────────────────────────────────┘

                        ┌─────────────────┐
                        │ Hitting single  │
                        │ node limits?    │
                        └────────┬────────┘
                                 │
              ┌──────────────────┴──────────────────┐
              ▼                                      ▼
        ┌─────────┐                            ┌─────────┐
        │   No    │                            │   Yes   │
        └────┬────┘                            └────┬────┘
             │                                      │
             ▼                                      ▼
┌─────────────────────────┐              ┌──────────────────┐
│ Consider:               │              │ Can you optimize │
│ - Query optimization    │              │ queries first?   │
│ - Caching              │              └────────┬─────────┘
│ - Read replicas        │                       │
│ - Vertical scaling     │            ┌──────────┴──────────┐
└─────────────────────────┘            ▼                    ▼
                               ┌─────────────┐      ┌─────────────┐
                               │     Yes     │      │     No      │
                               └──────┬──────┘      └──────┬──────┘
                                      │                    │
                                      ▼                    ▼
                               ┌─────────────┐    ┌─────────────────┐
                               │ Do that     │    │ Sharding is     │
                               │ first       │    │ likely necessary│
                               └─────────────┘    └─────────────────┘
```

## Shard Key Selection: The Critical Decision

The shard key determines how data is distributed. Choose poorly, and you'll suffer for years.

### Properties of a Good Shard Key

1. **High Cardinality:** Many unique values = better distribution
2. **Even Distribution:** Values appear with similar frequency
3. **Query Alignment:** Most queries include the shard key
4. **Stable:** Key doesn't change after record creation
5. **Not Sequential:** Auto-increment IDs create hot spots

### Examples

```
Good Shard Keys:
─────────────────────────────────────────────────────────────────────────
Data Type           Shard Key              Reason
─────────────────────────────────────────────────────────────────────────
User profiles       user_id                High cardinality, stable
E-commerce orders   customer_id            Queries filter by customer
IoT events          device_id              Natural partitioning
Game state          player_id              Isolated player data
─────────────────────────────────────────────────────────────────────────

Bad Shard Keys:
─────────────────────────────────────────────────────────────────────────
Data Type           Shard Key              Problem
─────────────────────────────────────────────────────────────────────────
User profiles       country                Uneven (US >> Andorra)
Log events          timestamp              Hot partition (current time)
Orders              order_status           Only 5 values, uneven
User profiles       registration_date      Hot partition, sequential
─────────────────────────────────────────────────────────────────────────
```

---

<a name="hash-based-sharding"></a>
# 7. Hash-Based Sharding

The most common sharding strategy: hash the shard key and use modulo to determine the shard.

## How It Works

```python
def get_shard(key, num_shards):
    hash_value = hash(key)
    return hash_value % num_shards

# Example
num_shards = 4
user_ids = ["user_001", "user_002", "user_003", "user_004", "user_005"]

for user_id in user_ids:
    shard = get_shard(user_id, num_shards)
    print(f"{user_id} → Shard {shard}")

# Output:
# user_001 → Shard 2
# user_002 → Shard 0
# user_003 → Shard 1
# user_004 → Shard 3
# user_005 → Shard 2
```

```
┌────────────────────────────────────────────────────────────────────────┐
│                      HASH-BASED SHARDING                               │
└────────────────────────────────────────────────────────────────────────┘

    user_id="abc123"
           │
           ▼
    ┌──────────────┐
    │  hash(key)   │
    │  = 7829341   │
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │  7829341 % 4 │
    │  = 1         │
    └──────┬───────┘
           │
           ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                                                              │
    │    ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
    │    │ Shard 0 │  │ Shard 1 │  │ Shard 2 │  │ Shard 3 │       │
    │    │         │  │   ◄──   │  │         │  │         │       │
    │    └─────────┘  └─────────┘  └─────────┘  └─────────┘       │
    │                                                              │
    └──────────────────────────────────────────────────────────────┘
```

## Advantages

1. **Even Distribution:** Good hash functions spread data uniformly
2. **Simple Logic:** Easy to implement and understand
3. **Predictable:** Same key always maps to same shard

## Disadvantages

### The Resharding Problem

When you add shards, everything breaks.

```
Before: 4 shards
  hash("user_001") % 4 = 2  →  Shard 2

After: 5 shards (added one)
  hash("user_001") % 5 = 3  →  Shard 3

Problem: ~80% of data is now on the wrong shard!
```

### Solution: Consistent Hashing

Instead of modulo, use a hash ring.

```
┌────────────────────────────────────────────────────────────────────────┐
│                       CONSISTENT HASH RING                             │
└────────────────────────────────────────────────────────────────────────┘

                         0°
                         │
                    S1 ──●
                   ╱     │╲
                 ╱       │  ╲
               ╱         │    ╲
       270° ──●          │      ●── 90°
              S4         │      S2
               ╲         │    ╱
                 ╲       │  ╱
                   ╲     │╱
                    S3 ──●
                         │
                        180°

Keys are hashed to a position on the ring.
Walk clockwise to find the responsible shard.

Adding/removing a shard only affects neighbors, not entire dataset.
```

```python
import hashlib
import bisect

class ConsistentHashRing:
    def __init__(self, nodes, virtual_nodes=100):
        self.ring = {}
        self.sorted_keys = []
        self.virtual_nodes = virtual_nodes
        
        for node in nodes:
            self.add_node(node)
    
    def _hash(self, key):
        return int(hashlib.md5(key.encode()).hexdigest(), 16)
    
    def add_node(self, node):
        for i in range(self.virtual_nodes):
            virtual_key = f"{node}:{i}"
            hash_val = self._hash(virtual_key)
            self.ring[hash_val] = node
            bisect.insort(self.sorted_keys, hash_val)
    
    def remove_node(self, node):
        for i in range(self.virtual_nodes):
            virtual_key = f"{node}:{i}"
            hash_val = self._hash(virtual_key)
            del self.ring[hash_val]
            self.sorted_keys.remove(hash_val)
    
    def get_node(self, key):
        if not self.ring:
            return None
        
        hash_val = self._hash(key)
        idx = bisect.bisect(self.sorted_keys, hash_val)
        
        if idx == len(self.sorted_keys):
            idx = 0  # Wrap around
        
        return self.ring[self.sorted_keys[idx]]
```

### Range Queries Don't Work

Hash-based sharding destroys data ordering.

```
Query: SELECT * FROM users WHERE created_at BETWEEN '2024-01-01' AND '2024-01-31'

Problem: Users from this date range are scattered across ALL shards.
         Must query every shard and merge results.
         
         Shard 0: [user_005, user_019, user_033, ...]
         Shard 1: [user_002, user_011, user_024, ...]
         Shard 2: [user_001, user_008, user_017, ...]
         Shard 3: [user_004, user_012, user_029, ...]
         
         All four shards might have users from January!
```

---

<a name="range-based-sharding"></a>
# 8. Range-Based Sharding

Range-based sharding assigns continuous ranges of keys to each shard.

## How It Works

```
┌────────────────────────────────────────────────────────────────────────┐
│                      RANGE-BASED SHARDING                              │
└────────────────────────────────────────────────────────────────────────┘

    Shard Key: user_id (alphabetical)
    
    ┌────────────────┬────────────────┬────────────────┬────────────────┐
    │    Shard 0     │    Shard 1     │    Shard 2     │    Shard 3     │
    │    A - F       │    G - M       │    N - S       │    T - Z       │
    ├────────────────┼────────────────┼────────────────┼────────────────┤
    │ Alice          │ George         │ Nancy          │ Tom            │
    │ Bob            │ Helen          │ Oscar          │ Uma            │
    │ Carol          │ Ivan           │ Patricia       │ Victor         │
    │ David          │ Julia          │ Quentin        │ Walter         │
    │ Eve            │ Kevin          │ Rachel         │ Xavier         │
    │ Frank          │ Lisa           │ Steve          │ Yolanda        │
    │                │ Mike           │                │ Zack           │
    └────────────────┴────────────────┴────────────────┴────────────────┘
```

```python
class RangeShardRouter:
    def __init__(self):
        # Sorted list of (upper_bound, shard_id)
        self.ranges = [
            ("F", "shard_0"),
            ("M", "shard_1"),
            ("S", "shard_2"),
            ("Z", "shard_3"),
        ]
    
    def get_shard(self, key):
        for upper_bound, shard_id in self.ranges:
            if key <= upper_bound:
                return shard_id
        return self.ranges[-1][1]  # Last shard
    
    def get_shards_for_range(self, start_key, end_key):
        """Efficient range query - only hit relevant shards"""
        shards = []
        in_range = False
        
        for upper_bound, shard_id in self.ranges:
            if start_key <= upper_bound:
                in_range = True
            if in_range:
                shards.append(shard_id)
            if end_key <= upper_bound:
                break
        
        return shards
```

## Advantages

1. **Range Queries Work:** Adjacent keys are on the same shard
2. **Efficient Scans:** Date ranges, alphabetical sorting, numeric ranges
3. **Predictable Location:** Easy to reason about data placement

## Disadvantages

### Hot Spots from Temporal Keys

```
Shard Key: timestamp

┌────────────────────────────────────────────────────────────────────────┐
│              HOT SPOT: ALL WRITES GO TO CURRENT TIME SHARD             │
└────────────────────────────────────────────────────────────────────────┘

    Shard 0          Shard 1          Shard 2          Shard 3
    Jan 2023         Apr 2023         Jul 2023         Oct 2023
    (cold)           (cold)           (cold)           (HOT!! 🔥)
    
    0% writes        0% writes        0% writes        100% writes
```

### Uneven Distribution

```
Name distribution (English names):
─────────────────────────────────────────────────────────────────────────
Range       % of Names      Shard Load
─────────────────────────────────────────────────────────────────────────
A - F       ~30%            Overloaded
G - M       ~25%            Normal
N - S       ~25%            Normal  
T - Z       ~20%            Underutilized
─────────────────────────────────────────────────────────────────────────
```

### Solution: Dynamic Range Boundaries

Monitor shard sizes and split/merge ranges.

```python
class DynamicRangeShardManager:
    def __init__(self, target_size_gb=100):
        self.target_size = target_size_gb
        self.ranges = {}  # range -> (shard, current_size)
    
    def monitor_and_rebalance(self):
        for range_key, (shard, size) in self.ranges.items():
            if size > self.target_size * 1.5:
                self.split_range(range_key)
            elif size < self.target_size * 0.3:
                self.merge_with_neighbor(range_key)
    
    def split_range(self, range_key):
        """Split oversized range into two"""
        start, end = range_key
        midpoint = self.find_median_key(start, end)
        
        new_range_1 = (start, midpoint)
        new_range_2 = (midpoint + 1, end)
        
        # Migrate data to new shard
        self.migrate_range(new_range_2, new_shard=self.allocate_shard())
```

---

<a name="hybrid-sharding"></a>
# 9. Hybrid Sharding Strategies

Real systems rarely use pure hash or range sharding. Hybrid approaches combine benefits of both.

## Compound Shard Keys

Use multiple fields to determine shard placement.

```
Example: Chat Messages
─────────────────────────────────────────────────────────────────────────
Naive approach: Shard by message_id (hash)
Problem: Messages for one conversation are scattered everywhere

Better approach: Compound key (conversation_id, message_id)
- First level: Hash conversation_id → determines shard
- Second level: Order by message_id within shard

Result: All messages for a conversation are co-located AND ordered
─────────────────────────────────────────────────────────────────────────
```

```python
class CompoundShardRouter:
    def __init__(self, num_shards):
        self.num_shards = num_shards
    
    def get_shard(self, conversation_id, message_id):
        # Hash on conversation_id for co-location
        shard = hash(conversation_id) % self.num_shards
        return shard
    
    def get_sort_key(self, message_id):
        # Use message_id for ordering within shard
        return message_id
```

## Two-Level Sharding

Shard by one dimension, then sub-shard by another.

```
┌────────────────────────────────────────────────────────────────────────┐
│                      TWO-LEVEL SHARDING                                │
└────────────────────────────────────────────────────────────────────────┘

Level 1: Shard by tenant_id (hash)

    ┌─────────────────────────────────────────────────────────────┐
    │               Tenant A → Shard Group 0                       │
    │  ┌───────────────┬───────────────┬───────────────┐          │
    │  │  Sub-shard 0  │  Sub-shard 1  │  Sub-shard 2  │          │
    │  │  Jan-Apr      │  May-Aug      │  Sep-Dec      │          │
    │  └───────────────┴───────────────┴───────────────┘          │
    └─────────────────────────────────────────────────────────────┘
    
    ┌─────────────────────────────────────────────────────────────┐
    │               Tenant B → Shard Group 1                       │
    │  ┌───────────────┬───────────────┬───────────────┐          │
    │  │  Sub-shard 0  │  Sub-shard 1  │  Sub-shard 2  │          │
    │  │  Jan-Apr      │  May-Aug      │  Sep-Dec      │          │
    │  └───────────────┴───────────────┴───────────────┘          │
    └─────────────────────────────────────────────────────────────┘

Level 2: Range shard by date within tenant
```

## Directory-Based Sharding

Maintain a lookup table for shard assignment.

```
┌────────────────────────────────────────────────────────────────────────┐
│                    DIRECTORY-BASED SHARDING                            │
└────────────────────────────────────────────────────────────────────────┘

                      ┌───────────────────────┐
                      │   SHARD DIRECTORY     │
                      │   (Lookup Service)    │
                      ├───────────────────────┤
                      │ user_001 → Shard 2    │
                      │ user_002 → Shard 0    │
                      │ user_003 → Shard 1    │
                      │ user_004 → Shard 2    │
                      │ user_005 → Shard 0    │
                      └───────────┬───────────┘
                                  │
           ┌──────────────────────┼──────────────────────┐
           ▼                      ▼                      ▼
      ┌─────────┐           ┌─────────┐           ┌─────────┐
      │ Shard 0 │           │ Shard 1 │           │ Shard 2 │
      └─────────┘           └─────────┘           └─────────┘
```

**Advantages:**
- Complete flexibility in placement
- Easy migration: just update directory
- Can place related data together regardless of key

**Disadvantages:**
- Directory becomes SPOF and bottleneck
- Extra lookup on every request
- Must be cached heavily

```python
class DirectoryBasedRouter:
    def __init__(self, directory_service, cache):
        self.directory = directory_service
        self.cache = cache
    
    def get_shard(self, key):
        # Check cache first
        cached = self.cache.get(f"shard:{key}")
        if cached:
            return cached
        
        # Lookup in directory
        shard = self.directory.lookup(key)
        
        # Cache the result
        self.cache.set(f"shard:{key}", shard, ttl=3600)
        
        return shard
    
    def migrate_key(self, key, old_shard, new_shard):
        # 1. Copy data to new shard
        data = old_shard.read(key)
        new_shard.write(key, data)
        
        # 2. Update directory
        self.directory.update(key, new_shard.id)
        
        # 3. Invalidate cache
        self.cache.delete(f"shard:{key}")
        
        # 4. Delete from old shard (after grace period)
        schedule_deletion(old_shard, key, delay=24*3600)
```

---

<a name="hot-partitions"></a>
# 10. Hot Partitions and Skew: The Silent Killers

No matter how clever your sharding strategy, hot partitions will find you.

## What Creates Hot Partitions?

### 1. Celebrity Problem
```
Twitter-like system sharded by user_id:
─────────────────────────────────────────────────────────────────────────
Regular user:     10 reads/minute
Celebrity user:   1,000,000 reads/minute

One shard (the celebrity's) is melting while others are idle.
─────────────────────────────────────────────────────────────────────────
```

### 2. Temporal Skew
```
E-commerce system sharded by order_id:
─────────────────────────────────────────────────────────────────────────
Normal day:       100 orders/minute, distributed evenly
Black Friday:     10,000 orders/minute, all hitting "today's" range
─────────────────────────────────────────────────────────────────────────
```

### 3. Natural Skew
```
Geo-based sharding:
─────────────────────────────────────────────────────────────────────────
Shard: California      → 40 million users
Shard: Wyoming         → 500,000 users

California shard is 80x more loaded.
─────────────────────────────────────────────────────────────────────────
```

## Detection Strategies

```python
class HotPartitionDetector:
    def __init__(self, alert_threshold_ratio=5.0):
        self.threshold = alert_threshold_ratio
        self.shard_metrics = {}
    
    def record_request(self, shard_id):
        if shard_id not in self.shard_metrics:
            self.shard_metrics[shard_id] = 0
        self.shard_metrics[shard_id] += 1
    
    def check_for_hotspots(self):
        if not self.shard_metrics:
            return []
        
        avg_load = sum(self.shard_metrics.values()) / len(self.shard_metrics)
        hot_shards = []
        
        for shard_id, load in self.shard_metrics.items():
            ratio = load / avg_load
            if ratio > self.threshold:
                hot_shards.append({
                    'shard': shard_id,
                    'load': load,
                    'ratio': ratio,
                    'severity': 'critical' if ratio > 10 else 'warning'
                })
        
        return hot_shards
```

## Mitigation Strategies

### Strategy 1: Key Salting

Add randomness to spread hot keys across shards.

```python
class SaltedShardRouter:
    def __init__(self, num_shards, salt_range=10):
        self.num_shards = num_shards
        self.salt_range = salt_range
    
    def get_shard_for_write(self, key):
        salt = random.randint(0, self.salt_range - 1)
        salted_key = f"{key}:{salt}"
        return hash(salted_key) % self.num_shards
    
    def get_shards_for_read(self, key):
        # Must read from ALL possible salted locations
        shards = set()
        for salt in range(self.salt_range):
            salted_key = f"{key}:{salt}"
            shards.add(hash(salted_key) % self.num_shards)
        return shards

# Example usage:
# Celebrity post: written to random salt, read from all salts
# Normal user: no salting needed
```

**Trade-off:** Writes are distributed, but reads become scatter-gather operations. Use sparingly and only for genuinely hot keys.

### Strategy 2: Caching Layer for Hot Keys

```python
class HotKeyCacheRouter:
    def __init__(self, cache, db_shards, hot_key_threshold=1000):
        self.cache = cache
        self.db_shards = db_shards
        self.request_counter = defaultdict(int)
        self.hot_keys = set()
        self.threshold = hot_key_threshold
    
    def get(self, key):
        # Track access frequency
        self.request_counter[key] += 1
        
        if self.request_counter[key] > self.threshold:
            self.hot_keys.add(key)
        
        # Hot keys go to cache first
        if key in self.hot_keys:
            cached = self.cache.get(key)
            if cached:
                return cached
        
        # Fall through to database
        shard = self.get_shard(key)
        value = shard.get(key)
        
        # Cache hot keys
        if key in self.hot_keys:
            self.cache.set(key, value, ttl=60)
        
        return value
```

### Strategy 3: Dedicated Hot Partition Infrastructure

For extreme cases, route hot keys to dedicated, beefier infrastructure with aggressive caching and replication.

---

**Note:** The remainder of this volume continues with detailed case studies, failure mode analysis, and the homework assignment. The content below provides an alternative framing and additional depth on the same topics covered above.

---




# Volume 3, Part 2: Replication and Sharding — Scaling Without Losing Control

---

## Preamble: The Moment You Realize One Server Isn't Enough

You've built a beautiful system. Clean schemas, proper indexes, query patterns optimized. Your single PostgreSQL instance handles 50,000 queries per second. Life is good.

Then your product goes viral. Or your company acquires three competitors. Or December happens and everyone decides to use your e-commerce platform simultaneously.

Suddenly you're staring at graphs that look like hockey sticks, and not the good kind.

**This is the inflection point where junior engineers panic and senior engineers get excited.** It's where you stop thinking about code and start thinking about systems. Where the word "distributed" stops being theoretical and becomes your daily reality.

This section is about what happens next—and more importantly, how to do it without losing your mind, your data, or your job.

---

## Part 1: Replication — More Than Just "Don't Lose My Data"

### 1.1 The Naive Understanding of Replication

Ask a junior engineer why we replicate data, and you'll get: *"So we don't lose it if a server dies."*

That's true. But it's like saying we have fire departments because fires are hot. It misses the strategic value.

**Replication serves four distinct purposes:**

| Purpose | What It Means | When It Matters |
|---------|---------------|-----------------|
| **Durability** | Data survives hardware failure | Always |
| **Availability** | System stays up when nodes fail | High-SLA systems |
| **Read Scaling** | Distribute read load across copies | Read-heavy workloads |
| **Latency Reduction** | Place data closer to users | Global systems |

The first two are about not dying. The second two are about thriving. Staff engineers think about all four simultaneously.

---

### 1.2 Leader-Follower Replication: The Workhorse

This is where 90% of production systems start, and where many stay forever.

```
┌─────────────────────────────────────────────────────────┐
│                     CLIENTS                              │
│                                                          │
│        ┌─────────┐                    ┌─────────┐       │
│        │  Writes │                    │  Reads  │       │
│        └────┬────┘                    └────┬────┘       │
│             │                              │            │
│             ▼                              ▼            │
│       ┌──────────┐              ┌─────────────────┐    │
│       │  LEADER  │──────────────▶│   FOLLOWERS    │    │
│       │ (Primary)│  Replication  │ (Read Replicas)│    │
│       └──────────┘    Stream     └─────────────────┘    │
│             │                              │            │
│             ▼                              ▼            │
│       ┌──────────┐              ┌─────────────────┐    │
│       │  Disk    │              │   Disk  Disk    │    │
│       └──────────┘              └─────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

**How it works:**
1. All writes go to a single leader node
2. Leader writes to its local storage
3. Leader streams changes to follower nodes
4. Followers apply changes in the same order
5. Reads can go to leader OR followers (with caveats)

**Why this model dominates:**
- Simple to reason about (one source of truth)
- No write conflicts possible
- Easy to implement correctly
- Matches most application read/write ratios (90%+ reads)

#### The Critical Decision: Synchronous vs Asynchronous Replication

This is where things get interesting—and where many teams make decisions they later regret.

**Synchronous Replication:**
```
Client ──▶ Leader ──▶ Follower(s) ──▶ ACK ──▶ Leader ──▶ Client
                         │
                   Must succeed
                   before response
```

- Write isn't acknowledged until at least one follower confirms
- Guarantees durability: if leader dies immediately after ACK, data exists elsewhere
- Cost: every write pays network latency to follower
- Risk: if follower is slow/dead, writes block

**Asynchronous Replication:**
```
Client ──▶ Leader ──▶ Client (ACK)
              │
              └──────▶ Follower(s) (eventually)
```

- Write acknowledged as soon as leader persists locally
- Fast: only local disk latency
- Risk: if leader dies before replication, data is lost
- Reality: this is what most systems actually use

**The Pragmatic Middle Ground: Semi-Synchronous**

Most production systems I've worked on use semi-synchronous:
- Wait for ACK from ONE follower before responding to client
- Other followers replicate asynchronously
- Balance between durability and performance

```python
# Conceptual configuration (PostgreSQL-style)
synchronous_standby_names = 'FIRST 1 (replica1, replica2, replica3)'
# Wait for first one to respond, others are async
```

**Staff-Level Insight:** The choice between sync and async isn't about which is "better." It's about understanding your data's durability requirements per use case. User authentication tokens? Maybe async is fine—worst case, user logs in again. Financial transactions? You want synchronous. The same database can have both behaviors for different tables.

---

### 1.3 The Replication Lag Problem

Here's where junior engineers get bitten:

```
Timeline:
─────────────────────────────────────────────────────────────▶
   0ms         10ms        20ms        30ms        40ms

Leader:    [Write X=1]
                          [Write X=2]
                                      [Write X=3]

Follower:              [Apply X=1]
                                               [Apply X=2]
                                                          ... X=3 coming

Client reads from follower at 35ms: sees X=1 (stale!)
```

**Replication lag** is the delay between when data is written to the leader and when it appears on followers. This delay is usually milliseconds but can spike to seconds or minutes during:
- Network partitions
- Follower disk I/O pressure  
- Large transactions
- Schema migrations
- Follower restarts

**Real Production Scenario:**

User updates profile picture:
1. `POST /profile/picture` → hits leader → returns 200 OK
2. User immediately refreshes page
3. `GET /profile` → hits follower → returns OLD picture
4. User files support ticket: "Your website is broken"

This is called **read-your-own-writes inconsistency**, and it's one of the most common bugs in distributed systems.

**Solutions:**

| Approach | How It Works | Trade-off |
|----------|--------------|-----------|
| **Sticky sessions** | Route user to same replica for a time window | Uneven load distribution |
| **Read from leader** | After write, force reads to leader for N seconds | Leader becomes bottleneck |
| **Causal consistency** | Track write timestamps, ensure reads see them | Complexity, latency |
| **Version vectors** | Client carries version, reject stale responses | Client complexity |

**What We Actually Do at Scale:**

```python
# User service with read-your-writes guarantee
class UserService:
    def update_profile(self, user_id, data):
        result = self.leader_db.update(user_id, data)
        write_ts = result.timestamp
        
        # Store the write timestamp in user's session
        self.session.set(f"last_write:{user_id}", write_ts, ttl=30)
        return result
    
    def get_profile(self, user_id):
        last_write = self.session.get(f"last_write:{user_id}")
        
        if last_write:
            # User recently wrote, read from leader
            return self.leader_db.get(user_id)
        else:
            # No recent writes, followers are fine
            return self.follower_db.get(user_id)
```

This pattern—**write-flag routing**—is simple, effective, and handles 99% of read-your-writes scenarios.

---

### 1.4 Multi-Leader Replication: When You Need It (And When You Don't)

Multi-leader (or multi-master) replication allows writes to multiple nodes:

```
┌─────────────────────────────────────────────────────────────┐
│                                                              │
│     ┌──────────┐                    ┌──────────┐            │
│     │ Leader A │◀────────────────▶│ Leader B │            │
│     │  (US)    │   Bi-directional  │  (EU)    │            │
│     └──────────┘    Replication    └──────────┘            │
│          ▲                              ▲                   │
│          │                              │                   │
│     US Users                       EU Users                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Why would you want this?**

1. **Geographic latency**: Users in Europe write to Europe; users in US write to US
2. **Datacenter resilience**: Either datacenter can accept writes independently
3. **Offline operation**: Think mobile apps that sync when connectivity returns

**Why it's terrifying:**

CONFLICTS. When two leaders accept concurrent writes to the same data, you have a conflict.

```
Timeline:
─────────────────────────────────────────────────────────────▶

Leader A:    User.name = "Alice"
                    │
Leader B:    User.name = "Alicia"
                    │
                    ▼
             CONFLICT: Which value is correct?
```

**Conflict Resolution Strategies:**

| Strategy | How It Works | When to Use |
|----------|--------------|-------------|
| **Last-write-wins (LWW)** | Higher timestamp wins | Simple, accepts data loss |
| **First-write-wins** | Lower timestamp wins | Rare, specific use cases |
| **Merge** | Combine both values somehow | CRDTs, text editing |
| **Custom logic** | Application-specific resolution | Complex business rules |
| **Conflict flagging** | Mark for human resolution | Can't automate |

**The Dirty Secret:** Last-write-wins "works" but silently loses data. If Alice and Bob both edit the same document, one of their changes vanishes. Most systems using LWW don't realize how much data they're losing.

**Staff-Level Guidance:**

Multi-leader replication is the right choice when:
- You have genuine multi-region write requirements
- Latency for writes is unacceptable across regions
- You can design your data model to avoid conflicts

Multi-leader replication is the WRONG choice when:
- You're just trying to "scale writes" (sharding is usually better)
- Your data model has significant conflict potential
- You don't have the engineering capacity to handle conflict resolution properly

**Real Example: Why Google Spanner Exists**

Google built Spanner because they needed multi-region writes with strong consistency. Instead of traditional multi-leader with conflict resolution, Spanner uses globally synchronized clocks (TrueTime) to achieve serializable transactions across regions.

This is a $100M+ engineering investment. Unless you're at Google/Amazon/Microsoft scale, you probably don't need this. Accept the limitations of leader-follower or carefully constrained multi-leader.

---

### 1.5 Read Replicas: The Practical Scaling Tool

While the theory of replication is fascinating, the practical application in 90% of systems is simple: **read replicas for read scaling**.

```
┌───────────────────────────────────────────────────────────────┐
│                         LOAD BALANCER                          │
│                                                                │
│    Writes (5%)                             Reads (95%)        │
│        │                                       │               │
│        ▼                                       ▼               │
│  ┌──────────┐                    ┌─────────────────────┐      │
│  │  LEADER  │────replication────▶│     FOLLOWERS       │      │
│  │          │                    │  ┌─────┐ ┌─────┐   │      │
│  │          │                    │  │ F1  │ │ F2  │   │      │
│  │          │                    │  └─────┘ └─────┘   │      │
│  │          │                    │  ┌─────┐ ┌─────┐   │      │
│  │          │                    │  │ F3  │ │ F4  │   │      │
│  └──────────┘                    │  └─────┘ └─────┘   │      │
│                                  └─────────────────────┘      │
└───────────────────────────────────────────────────────────────┘
```

**Capacity Planning for Read Replicas:**

```
Given:
- Current: 10,000 QPS total
- Leader capacity: 15,000 QPS
- Write ratio: 5%
- Expected growth: 3x in 12 months

Calculation:
- Current writes: 500 QPS (must all go to leader)
- Current reads: 9,500 QPS
- Projected writes: 1,500 QPS (still fits on leader)
- Projected reads: 28,500 QPS

With 4 followers @ 10,000 QPS each:
- Total read capacity: 40,000 QPS
- Headroom for projected reads: ✓ 
```

**Read Replica Pitfalls:**

1. **Connection pool exhaustion**: Each replica needs its own connection pool. 4 replicas × 100 connections = 400 connections from your application tier.

2. **Uneven replica health**: One slow replica can become a latency trap. Use active health checking, not just TCP liveness.

3. **Replication lag variance**: Not all replicas are equally caught up. Critical reads might need lag-aware routing.

```python
# Lag-aware replica selection
class ReplicaRouter:
    def get_replica(self, max_acceptable_lag_ms=1000):
        healthy_replicas = []
        
        for replica in self.replicas:
            lag = replica.get_replication_lag_ms()
            if lag < max_acceptable_lag_ms:
                healthy_replicas.append((replica, lag))
        
        if not healthy_replicas:
            # All replicas too laggy, fall back to leader
            return self.leader
        
        # Return least-laggy replica
        return min(healthy_replicas, key=lambda x: x[1])[0]
```

---

## Part 2: Sharding — Cutting Your Data Into Manageable Pieces

### 2.1 When Replication Isn't Enough

Replication scales **reads**. It does nothing for **writes**.

If you have:
- 100,000 write operations per second
- A leader that maxes out at 20,000 WPS
- Already optimized everything possible

Replication cannot help you. Every write must still go through that single leader.

**This is where sharding enters the picture.**

Sharding (also called partitioning) splits your data across multiple independent databases, each handling a subset of the data:

```
┌─────────────────────────────────────────────────────────────────┐
│                       TOTAL DATASET                              │
│                                                                  │
│   ┌────────────┐    ┌────────────┐    ┌────────────┐           │
│   │  Shard 0   │    │  Shard 1   │    │  Shard 2   │           │
│   │            │    │            │    │            │           │
│   │ Users A-H  │    │ Users I-P  │    │ Users Q-Z  │           │
│   │            │    │            │    │            │           │
│   │  Leader    │    │  Leader    │    │  Leader    │           │
│   │     +      │    │     +      │    │     +      │           │
│   │ Followers  │    │ Followers  │    │ Followers  │           │
│   └────────────┘    └────────────┘    └────────────┘           │
│                                                                  │
│   Each shard is an independent replicated database              │
└─────────────────────────────────────────────────────────────────┘
```

**What sharding gives you:**
- Horizontal write scaling (each shard has its own leader)
- Larger total data capacity (sum of all shards)
- Independent failure domains (shard failures are partial)

**What sharding costs you:**
- Massive operational complexity
- Loss of cross-shard operations
- Potential for hot spots and imbalanced load
- Complicated application logic

---

### 2.2 The Evolution: From Single Node to Sharded System

Let me walk you through how this actually happens in the real world, because it's never a clean "let's redesign from scratch."

#### Stage 1: The Happy Single Node

```
┌─────────────────────────────────────┐
│           PostgreSQL                 │
│                                      │
│  Users: 100K                         │
│  Writes: 500/sec                     │
│  Reads: 5,000/sec                    │
│  Storage: 20GB                       │
│                                      │
│  Status: Fine. Go home.              │
└─────────────────────────────────────┘
```

Everything fits on one machine. Queries are fast. Backups are simple. Life is good.

#### Stage 2: Read Scaling with Replicas

Growth happened. Reads are now at 50,000/sec, and your single node can only handle 15,000.

```
┌────────────────────────────────────────────────────────┐
│                                                         │
│         ┌───────────┐                                  │
│         │  Primary  │◄── All writes (2,000/sec)       │
│         └─────┬─────┘                                  │
│               │                                        │
│      ┌────────┼────────┐                              │
│      ▼        ▼        ▼                              │
│  ┌───────┐┌───────┐┌───────┐                         │
│  │Replica││Replica││Replica│◄── Reads distributed    │
│  └───────┘└───────┘└───────┘    (16K/sec each)       │
│                                                         │
│  Status: Stable. Can scale reads by adding replicas.  │
└────────────────────────────────────────────────────────┘
```

This works until writes become the bottleneck or storage exceeds single-node capacity.

#### Stage 3: The Uncomfortable Middle

Your primary is now handling 15,000 writes/sec (its limit), and your dataset is 2TB (getting large for a single machine). You have options:

**Option A: Vertical Scaling (Buy Bigger Machine)**
- Move to a machine with more CPU, RAM, faster disks
- Simple, no code changes
- Limits: eventually there's no bigger machine to buy

**Option B: Functional Partitioning**
- Separate different tables onto different databases
- Users on one database, Orders on another, Analytics on a third
- Works until single tables become too large

**Option C: Sharding (Horizontal Partitioning)**
- Split single tables across multiple databases
- Users 0-1M on shard 0, Users 1M-2M on shard 1, etc.
- Most complex, but truly scalable

Most teams try A, then B, then finally accept C is necessary.

#### Stage 4: Application-Level Sharding

You've decided to shard. Now the fun begins.

```
┌─────────────────────────────────────────────────────────────────┐
│                        APPLICATION                               │
│                                                                  │
│    ┌─────────────────────────────────────────────────────┐      │
│    │              SHARD ROUTER                            │      │
│    │                                                      │      │
│    │   user_id = 12345                                   │      │
│    │   shard = hash(user_id) % num_shards               │      │
│    │   shard = 12345 % 4 = 1                            │      │
│    │                                                      │      │
│    │   Route to Shard 1                                  │      │
│    └─────────────────────────────────────────────────────┘      │
│                            │                                     │
│         ┌──────────────────┼──────────────────┐                 │
│         ▼                  ▼                  ▼                 │
│    ┌─────────┐       ┌─────────┐       ┌─────────┐             │
│    │ Shard 0 │       │ Shard 1 │       │ Shard 2 │             │
│    └─────────┘       └─────────┘       └─────────┘             │
│                            ▲                                     │
│                            │                                     │
│                     user 12345 lives here                       │
└─────────────────────────────────────────────────────────────────┘
```

**The routing layer becomes critical infrastructure.** Every query must know which shard to hit. This is typically embedded in your application or abstracted into a proxy layer.

---

### 2.3 Sharding Strategies: The Big Three

#### Strategy 1: Hash-Based Sharding

```python
def get_shard(key, num_shards):
    return hash(key) % num_shards
```

**How it works:**
- Hash the partition key (e.g., user_id)
- Modulo by number of shards
- Deterministically routes to a shard

**Pros:**
- Even distribution (if hash is good)
- No lookup table needed
- Simple to implement

**Cons:**
- Range queries require scatter-gather (hit all shards)
- Adding shards requires massive data movement
- Hash collisions in the algorithm aren't hash collisions in data—it's about distribution

**When to use:**
- Point queries are dominant (get user by ID)
- Data doesn't need to be queried by range
- You want simplicity over optimization

**Critical Detail: Consistent Hashing**

Simple modulo hashing has a fatal flaw. When you add a shard:

```
Before: hash(key) % 3 = 0, 1, or 2
After:  hash(key) % 4 = 0, 1, 2, or 3

Key "user_123" might have been on shard 0, now goes to shard 3.
Most keys move to different shards!
```

**Consistent hashing** solves this by only moving ~1/N keys when adding a shard:

```
┌───────────────────────────────────────────────────────────┐
│                     HASH RING                              │
│                                                            │
│                         0°                                 │
│                         │                                  │
│                    Shard 0                                │
│                   /         \                              │
│                  /           \                             │
│           270° ─┤   Keys     ├─ 90°                       │
│                  \  mapped   /  Shard 1                   │
│                   \ to ring /                              │
│                    Shard 2                                │
│                         │                                  │
│                       180°                                 │
│                                                            │
│   Key placement: walk clockwise to find owning shard      │
└───────────────────────────────────────────────────────────┘
```

Adding a shard only affects keys between it and its neighbor, not the entire keyspace.

---

#### Strategy 2: Range-Based Sharding

```python
SHARD_RANGES = [
    (0, 1000000, "shard_0"),
    (1000001, 2000000, "shard_1"),
    (2000001, 3000000, "shard_2"),
]

def get_shard(user_id):
    for (start, end, shard) in SHARD_RANGES:
        if start <= user_id <= end:
            return shard
```

**How it works:**
- Divide keyspace into ranges
- Each shard owns a contiguous range
- Lookup table maps ranges to shards

**Pros:**
- Range queries are efficient (only hit relevant shards)
- Easy to split hot shards (divide range)
- Intuitive for ordered data

**Cons:**
- Prone to hot spots (recent users on one shard)
- Requires maintaining range mapping
- Uneven distribution if access patterns are skewed

**When to use:**
- Range queries are common
- Data has natural ordering (time, alphabetical)
- You can monitor and rebalance as needed

**Example: Time-Based Range Sharding**

```
┌────────────────────────────────────────────────────────────┐
│                   EVENTS TABLE                              │
│                                                             │
│  Shard 0: events from 2023-01 to 2023-04                  │
│  Shard 1: events from 2023-05 to 2023-08                  │
│  Shard 2: events from 2023-09 to 2023-12                  │
│  Shard 3: events from 2024-01 onwards (ACTIVE)            │
│                                                             │
│  Query: "events from last week"                            │
│  → Only hits Shard 3 ✓                                     │
│                                                             │
│  Query: "events from March 2023"                           │
│  → Only hits Shard 0 ✓                                     │
│                                                             │
│  Problem: Shard 3 gets ALL current writes                  │
│           (hot spot)                                        │
└────────────────────────────────────────────────────────────┘
```

---

#### Strategy 3: Hybrid (Directory-Based) Sharding

```python
class ShardDirectory:
    def __init__(self):
        self.mapping = {}  # Loaded from database/cache
    
    def get_shard(self, key):
        return self.mapping.get(key)
    
    def set_shard(self, key, shard):
        self.mapping[key] = shard
```

**How it works:**
- Maintain explicit mapping of keys to shards
- Lookup table stored in fast storage (Redis, dedicated DB)
- Complete flexibility in placement

**Pros:**
- Total control over data placement
- Easy to move individual keys between shards
- Can implement custom balancing logic

**Cons:**
- Lookup table is critical dependency
- Additional latency for directory lookup
- Complexity in maintaining directory

**When to use:**
- Highly variable data sizes (large tenants need dedicated shards)
- Complex placement requirements
- VIP tenant isolation

**Real Example: Multi-Tenant SaaS**

```
┌────────────────────────────────────────────────────────────┐
│                  SHARD DIRECTORY                            │
│                                                             │
│  Tenant "small_co_1"     → Shard 0 (shared)               │
│  Tenant "small_co_2"     → Shard 0 (shared)               │
│  Tenant "small_co_3"     → Shard 0 (shared)               │
│  Tenant "medium_corp"    → Shard 1 (shared)               │
│  Tenant "enterprise_inc" → Shard 2 (DEDICATED)            │
│  Tenant "whale_co"       → Shard 3 (DEDICATED)            │
│                                                             │
│  Enterprise and Whale get dedicated shards for:            │
│  - Performance isolation                                    │
│  - Compliance requirements                                  │
│  - Custom SLAs                                              │
└────────────────────────────────────────────────────────────┘
```

---

### 2.4 Hot Partitions and Skew: When Theory Meets Reality

You've carefully designed your sharding scheme. You launch. And then:

```
Shard Utilization After 1 Month:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Shard 0:  ████████████░░░░░░░░  60%
Shard 1:  ██████████████████░░  90%  ← HOT
Shard 2:  ████████░░░░░░░░░░░░  40%
Shard 3:  ████░░░░░░░░░░░░░░░░  20%

Shard 1 is dying. The others are bored.
```

**Why does this happen?**

1. **Data skew**: Some partition keys have way more data than others
2. **Access skew**: Some partition keys are accessed way more frequently
3. **Temporal skew**: Recent data is always hotter than old data
4. **Popularity skew**: Celebrity accounts, viral content, etc.

**The Celebrity Problem:**

```python
# User ID 1234 is a celebrity with 50 million followers
# Every post creates 50 million fan-out events
# All targeting shard = hash(1234) % 4 = 2

# Shard 2 is now processing 50M events
# while other shards process thousands

# Your "evenly distributed" system is now 99% focused on shard 2
```

**Solutions to Hot Partitions:**

| Approach | Description | Trade-off |
|----------|-------------|-----------|
| **Salting** | Add random suffix to hot keys | Scatter-gather for reads |
| **Split hot shards** | Subdivide overloaded shards | Operational complexity |
| **Rate limiting** | Throttle hot keys | User experience impact |
| **Caching** | Cache hot key responses | Cache invalidation |
| **Dedicated infrastructure** | Hot keys get special handling | Cost, complexity |

**Salting Implementation:**

```python
# Without salting
def get_shard(user_id):
    return hash(user_id) % num_shards  # Always same shard

# With salting for hot keys
def get_shard_salted(user_id, is_celebrity=False):
    if is_celebrity:
        # Distribute across shards
        salt = random.randint(0, 9)
        return hash(f"{user_id}_{salt}") % num_shards
    return hash(user_id) % num_shards

# Reading requires scatter-gather for celebrities
def get_all_data_for_celebrity(user_id):
    results = []
    for salt in range(10):
        shard = hash(f"{user_id}_{salt}") % num_shards
        results.extend(query_shard(shard, user_id, salt))
    return results
```

**Staff-Level Insight:** The best solution to hot partitions is often domain-specific. Don't reach for generic solutions immediately. Understand WHY your partition is hot and design accordingly.

For example: If celebrity posts are hot because of fan-out, maybe the answer isn't better sharding—it's redesigning fan-out to be pull-based instead of push-based.

---

### 2.5 Re-Sharding: The Migration Everyone Dreads

The day will come when your sharding scheme no longer works:
- You need more shards (growth)
- You need fewer shards (consolidation)
- Your partition key was wrong (design error)
- Hot spots require rebalancing

**The Challenge:**

```
Current: 4 shards
Target:  8 shards

During migration:
- System must stay online
- Reads must return correct data
- Writes must not be lost
- Consistency must be maintained
```

**Migration Strategies:**

#### Strategy 1: Double-Write Migration

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: Start double-writing                              │
│                                                              │
│     Write ──┬──▶ Old shard (source of truth)               │
│             └──▶ New shard (building up)                    │
│                                                              │
│  Phase 2: Backfill historical data                          │
│                                                              │
│     Old shard ──copy──▶ New shard                          │
│                                                              │
│  Phase 3: Verify parity                                     │
│                                                              │
│     Compare old and new shards                              │
│                                                              │
│  Phase 4: Switch reads                                      │
│                                                              │
│     Reads ──▶ New shard                                     │
│                                                              │
│  Phase 5: Stop old writes, decommission old shards         │
└─────────────────────────────────────────────────────────────┘
```

**Pros:** Zero downtime, can rollback easily
**Cons:** 2x write load, 2x storage during migration, complex coordination

#### Strategy 2: Ghost Tables (Online Schema Change Pattern)

```python
# Inspired by GitHub's gh-ost

class OnlineResharding:
    def migrate(self):
        # 1. Create new shard structure
        self.create_new_shards()
        
        # 2. Start capturing changes (binlog/CDC)
        self.start_change_capture()
        
        # 3. Copy existing data in batches
        for batch in self.get_batches():
            self.copy_batch(batch)
            self.apply_captured_changes()  # Keep up with writes
        
        # 4. Final sync and cutover
        self.pause_writes()  # Brief pause
        self.apply_remaining_changes()
        self.switch_traffic()
        self.resume_writes()
```

**Pros:** Minimal downtime (seconds), battle-tested pattern
**Cons:** Requires change data capture, complex implementation

#### Strategy 3: Gradual Migration with Read-Through

```
┌─────────────────────────────────────────────────────────────┐
│                                                              │
│   Read Request                                               │
│        │                                                     │
│        ▼                                                     │
│   ┌─────────────────────────────────────────────┐           │
│   │           MIGRATION PROXY                    │           │
│   │                                              │           │
│   │  1. Check new shard                          │           │
│   │     - Found? Return it                       │           │
│   │     - Not found? Continue                    │           │
│   │                                              │           │
│   │  2. Check old shard                          │           │
│   │     - Found? Migrate to new, return it       │           │
│   │     - Not found? Return 404                  │           │
│   │                                              │           │
│   └─────────────────────────────────────────────┘           │
│        │                   │                                 │
│        ▼                   ▼                                 │
│   ┌─────────┐        ┌─────────┐                            │
│   │   New   │◀─copy──│   Old   │                            │
│   │ Shards  │        │ Shards  │                            │
│   └─────────┘        └─────────┘                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Pros:** Lazy migration, no big-bang cutover
**Cons:** Extended migration period, read latency penalty

---

## Part 3: Applied Scenarios

### 3.1 Scenario: User Data Store Evolution

Let's trace the evolution of a user data store from startup to scale.

#### Phase 1: Early Days (0-100K Users)

```python
# Simple PostgreSQL setup
# users table with all user data

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255),
    profile JSONB,
    created_at TIMESTAMP
);

# Everything on one server. ~50ms queries. Life is good.
```

#### Phase 2: Growth Pains (100K-10M Users)

```python
# Add read replicas for scaling reads

                    ┌──────────┐
    Writes ────────▶│ Primary  │
                    └────┬─────┘
                         │ replication
            ┌────────────┼────────────┐
            ▼            ▼            ▼
       ┌────────┐   ┌────────┐   ┌────────┐
       │Replica1│   │Replica2│   │Replica3│
       └────────┘   └────────┘   └────────┘
            ▲            ▲            ▲
            └────────────┴────────────┘
                    Reads (load balanced)
```

**Issues Encountered:**
- Read-your-writes inconsistency for profile updates
- Primary becoming bottleneck for writes
- Connection pool exhaustion

**Solutions Applied:**
```python
# Sticky sessions for recently-updated users
def get_user(user_id):
    if cache.get(f"recently_updated:{user_id}"):
        return primary.get_user(user_id)
    return load_balanced_replica.get_user(user_id)

def update_user(user_id, data):
    result = primary.update_user(user_id, data)
    cache.set(f"recently_updated:{user_id}", True, ttl=30)
    return result
```

#### Phase 3: Sharding Required (10M+ Users)

```python
# Hash-based sharding on user_id

SHARD_COUNT = 16

def get_user_shard(user_id):
    # Consistent hashing for future expansion
    return consistent_hash(user_id, SHARD_COUNT)

# Each shard has primary + replicas
# Shard 0: users whose hash maps to 0
# Shard 1: users whose hash maps to 1
# ... etc
```

**Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                    USER SERVICE                              │
│                                                              │
│    ┌──────────────────────────────────────────────┐         │
│    │            SHARD ROUTER                       │         │
│    │                                               │         │
│    │   shard_id = consistent_hash(user_id) % 16   │         │
│    └──────────────────────────────────────────────┘         │
│                          │                                   │
│    ┌─────────┬─────────┬─┴───────┬─────────┬─────────┐     │
│    ▼         ▼         ▼         ▼         ▼         ▼     │
│ ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐     │
│ │Sh 0 │  │Sh 1 │  │Sh 2 │  │ ... │  │Sh 14│  │Sh 15│     │
│ │     │  │     │  │     │  │     │  │     │  │     │     │
│ │P + R│  │P + R│  │P + R│  │     │  │P + R│  │P + R│     │
│ └─────┘  └─────┘  └─────┘  └─────┘  └─────┘  └─────┘     │
│                                                              │
│ P = Primary, R = Replicas                                   │
└─────────────────────────────────────────────────────────────┘
```

**Challenge: Email Lookups**

Users log in by email, not user_id. But we sharded by user_id.

```python
# Problem: 
# login(email) → which shard?

# Solution: Secondary index
# Separate lookup table: email → user_id
# This table is small (just the mapping) and can be replicated

CREATE TABLE email_to_user (
    email VARCHAR(255) PRIMARY KEY,
    user_id BIGINT
);

def login(email, password):
    # 1. Lookup user_id from email (this table is small, unsharded)
    user_id = email_lookup.get(email)
    
    # 2. Route to correct shard
    shard = get_user_shard(user_id)
    
    # 3. Verify password
    user = shard.get_user(user_id)
    return verify_password(user, password)
```

**Failure Modes to Handle:**

| Failure | Impact | Mitigation |
|---------|--------|------------|
| Single shard down | ~6% of users affected | Failover to replica, alerting |
| Router failure | All requests fail | Multiple router instances |
| Email lookup down | No logins possible | Replicate heavily, cache aggressively |
| Shard split-brain | Data inconsistency | Fencing, leader election |

---

### 3.2 Scenario: Rate Limiter Counters

Rate limiting looks simple until you try to do it at scale. Let's design a distributed rate limiter.

**Requirements:**
- 100M users
- Limit: 100 requests per minute per user
- Sub-millisecond latency
- Globally consistent-ish (eventually consistent OK for slight over-limit)

#### Naive Approach (Won't Scale)

```python
# Single Redis instance
def check_rate_limit(user_id):
    key = f"rate:{user_id}"
    count = redis.incr(key)
    if count == 1:
        redis.expire(key, 60)
    return count <= 100
```

**Why it fails:**
- Single Redis is SPOF
- Can't handle 100K+ QPS
- Memory limited for 100M keys

#### Sharded Rate Limiter

```python
# Shard by user_id

class ShardedRateLimiter:
    def __init__(self, num_shards=64):
        self.shards = [Redis(host=f"ratelimit-{i}") for i in range(num_shards)]
        self.num_shards = num_shards
    
    def get_shard(self, user_id):
        return self.shards[hash(user_id) % self.num_shards]
    
    def check_rate_limit(self, user_id, limit=100, window=60):
        shard = self.get_shard(user_id)
        key = f"rate:{user_id}"
        
        # Atomic increment with TTL
        pipe = shard.pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        count, _ = pipe.execute()
        
        return count <= limit
```

**Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                   RATE LIMITER SERVICE                       │
│                                                              │
│   Request ─▶ hash(user_id) % 64 ─▶ Redis Shard              │
│                                                              │
│   ┌───────────────────────────────────────────────────┐     │
│   │                 64 Redis Shards                    │     │
│   │                                                    │     │
│   │   Shard 0    Shard 1    Shard 2    ...   Shard 63 │     │
│   │   ┌─────┐    ┌─────┐    ┌─────┐         ┌─────┐  │     │
│   │   │Redis│    │Redis│    │Redis│         │Redis│  │     │
│   │   │     │    │     │    │     │         │     │  │     │
│   │   │ P+R │    │ P+R │    │ P+R │         │ P+R │  │     │
│   │   └─────┘    └─────┘    └─────┘         └─────┘  │     │
│   │                                                    │     │
│   │   Each shard: Primary + 1 Replica (async)         │     │
│   └───────────────────────────────────────────────────┘     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Trade-offs Made:**

1. **Async replication**: We accept that on failover, some counts might reset. Users might get a few extra requests through. This is acceptable for rate limiting.

2. **No cross-shard queries**: Each user's count is on exactly one shard. No aggregation needed.

3. **Hot user handling**: For viral users, their shard might become hot. Solution: monitor per-shard load and be prepared to split.

**Failure Mode Analysis:**

```
Scenario: Shard 15 goes down

Impact:
- Users mapped to shard 15 (~1.5M users) have no rate limiting
- They can burst traffic
- This lasts until failover completes (~30 seconds)

Mitigation:
- Fail fast to replica
- Apply aggressive local rate limiting at API gateway
- Alert on-call immediately

Scenario: Network partition between shards

Impact:
- Split-brain: users counted in two places
- Effectively 2x limit during partition
- Resolves when partition heals

Mitigation:
- Accept this as tolerable for rate limiting
- Alternative: use consensus (Raft) but pay latency cost
```

---

### 3.3 Scenario: Feed Storage (Complex Multi-Tenant Data)

Feed systems (Twitter timeline, Facebook News Feed, Instagram home) are among the most complex sharding challenges.

**The Problem:**
- Each user has a feed
- Feed contains posts from users they follow
- Posts must be ordered by time
- Feeds must be fast to read (p99 < 50ms)
- Writes happen constantly (new posts, deletes, edits)

#### Approach 1: Fan-Out on Write

```
When User A posts:

┌─────────────────────────────────────────────────────────────┐
│                                                              │
│  User A posts "Hello World"                                 │
│       │                                                      │
│       ▼                                                      │
│  ┌─────────────────────┐                                    │
│  │   POST SERVICE      │                                    │
│  │                     │                                    │
│  │   1. Store post     │                                    │
│  │   2. Get followers  │─────▶ 10,000 followers            │
│  │   3. Fan out        │                                    │
│  └─────────────────────┘                                    │
│           │                                                  │
│           ▼                                                  │
│  Write to 10,000 user feeds                                 │
│                                                              │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐     ┌─────────┐       │
│  │ Feed 1  │ │ Feed 2  │ │ Feed 3  │ ... │Feed 10K │       │
│  │ +post   │ │ +post   │ │ +post   │     │ +post   │       │
│  └─────────┘ └─────────┘ └─────────┘     └─────────┘       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Sharding for Fan-Out on Write:**

```python
# Shard feeds by user_id (feed owner)

class FeedStore:
    def __init__(self, num_shards=256):
        self.shards = [FeedShard(i) for i in range(num_shards)]
    
    def get_shard(self, user_id):
        return self.shards[consistent_hash(user_id) % len(self.shards)]
    
    def add_to_feed(self, user_id, post):
        shard = self.get_shard(user_id)
        shard.add_post(user_id, post)
    
    def get_feed(self, user_id, limit=20):
        shard = self.get_shard(user_id)
        return shard.get_posts(user_id, limit)
```

**Pros:**
- Reads are FAST (single shard, pre-computed)
- Scales reads horizontally

**Cons:**
- Writes are expensive (celebrity with 50M followers = 50M writes)
- Storage explosion (same post stored 50M times)
- Deletes are nightmares

#### Approach 2: Fan-Out on Read

```
When User B reads their feed:

┌─────────────────────────────────────────────────────────────┐
│                                                              │
│  User B requests feed                                       │
│       │                                                      │
│       ▼                                                      │
│  ┌─────────────────────────────────┐                        │
│  │        FEED SERVICE             │                        │
│  │                                 │                        │
│  │  1. Get B's following list      │                        │
│  │     (follows 500 users)         │                        │
│  │                                 │                        │
│  │  2. Fetch recent posts from     │                        │
│  │     each followed user          │                        │
│  │                                 │                        │
│  │  3. Merge and sort              │                        │
│  │                                 │                        │
│  │  4. Return top 20               │                        │
│  └─────────────────────────────────┘                        │
│           │                                                  │
│    Scatter-gather to many shards                            │
│           │                                                  │
│  ┌───┬───┬───┬───┬───┬───┬───┐                             │
│  │S1 │S2 │S3 │S4 │S5 │...│Sn │                             │
│  └───┴───┴───┴───┴───┴───┴───┘                             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Sharding for Fan-Out on Read:**

```python
# Shard posts by author_id

class PostStore:
    def get_recent_posts(self, author_id, since, limit):
        shard = self.get_shard(author_id)
        return shard.query_posts(author_id, since, limit)

class FeedService:
    def get_feed(self, user_id, limit=20):
        following = self.social_graph.get_following(user_id)
        
        # Parallel fetch from all followed users
        futures = []
        for author_id in following:
            futures.append(
                self.executor.submit(
                    self.post_store.get_recent_posts,
                    author_id, since=one_day_ago, limit=5
                )
            )
        
        # Gather and merge
        all_posts = []
        for future in futures:
            all_posts.extend(future.result())
        
        # Sort by time, return top N
        all_posts.sort(key=lambda p: p.created_at, reverse=True)
        return all_posts[:limit]
```

**Pros:**
- Writes are cheap (single write for a post)
- Storage efficient (post stored once)
- Deletes are easy

**Cons:**
- Reads are expensive (scatter-gather)
- Read latency depends on following count
- Harder to scale reads

#### Approach 3: Hybrid (What Twitter Actually Does)

```
┌─────────────────────────────────────────────────────────────┐
│                     HYBRID APPROACH                          │
│                                                              │
│  For regular users (< 10K followers):                       │
│  ────────────────────────────────                           │
│     Fan-out on write                                        │
│     Pre-computed feeds                                       │
│     Fast reads                                              │
│                                                              │
│  For celebrities (> 10K followers):                         │
│  ─────────────────────────────────                          │
│     Fan-out on read                                         │
│     Posts stored once                                        │
│     Merged at read time                                     │
│                                                              │
│  Read Path:                                                  │
│  ┌──────────────────────────────────────────────┐           │
│  │                                               │           │
│  │   1. Fetch pre-computed feed (regular posts)  │           │
│  │   2. Fetch celebrity posts (on-demand)        │           │
│  │   3. Merge and rank                           │           │
│  │   4. Return                                   │           │
│  │                                               │           │
│  └──────────────────────────────────────────────┘           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Sharding Strategy for Hybrid:**

```python
class HybridFeedSystem:
    CELEBRITY_THRESHOLD = 10_000
    
    def __init__(self, num_feed_shards=256, num_post_shards=64):
        # Feeds: sharded by feed owner
        self.feed_shards = [FeedShard(i) for i in range(num_feed_shards)]
        
        # Posts: sharded by author (for celebrity lookup)
        self.post_shards = [PostShard(i) for i in range(num_post_shards)]
        
        # Celebrity registry
        self.celebrities = set()
    
    def on_new_post(self, author_id, post):
        # Store the post
        self.store_post(author_id, post)
        
        # Fan out only if not celebrity
        if author_id not in self.celebrities:
            followers = self.get_followers(author_id)
            for follower_id in followers:
                self.add_to_feed(follower_id, post.id)
    
    def get_feed(self, user_id):
        # Get pre-computed feed (non-celebrity posts)
        precomputed = self.get_precomputed_feed(user_id)
        
        # Get celebrity posts user follows
        celebrity_posts = self.get_celebrity_posts_for_user(user_id)
        
        # Merge
        return self.merge_and_rank(precomputed, celebrity_posts)
```

---

## Part 4: Failure Modes and Operational Reality

### 4.1 Replication Failure Modes

| Failure | Symptoms | Detection | Recovery |
|---------|----------|-----------|----------|
| **Leader crash** | Writes fail, replication stops | Health check, heartbeat | Promote replica, redirect traffic |
| **Follower crash** | Reduced read capacity | Health check | Restart, catch up from binlog |
| **Replication lag** | Stale reads | Lag monitoring | Investigate root cause, maybe skip to head |
| **Split brain** | Two nodes think they're leader | Fencing, consensus | Forcibly fence one, reconcile data |
| **Network partition** | Timeouts, partial failures | Connectivity monitoring | Wait for heal, or force one side down |

**Split Brain Deep Dive:**

This is the scariest failure mode. Two nodes accept writes independently.

```
Normal:
┌────────┐         ┌────────┐
│ Leader │────────▶│Follower│
│   ✓    │         │        │
└────────┘         └────────┘

Network Partition:
┌────────┐    X    ┌────────┐
│ Leader │    X    │Follower│
│ (real) │    X    │(thinks │
│        │    X    │it's    │
└────────┘         │leader) │
                   └────────┘

Both accepting writes = DATA DIVERGENCE
```

**Prevention:**
- Quorum-based leader election
- Fencing tokens (STONITH: Shoot The Other Node In The Head)
- Lease-based leadership with strict timeouts

```python
# Fencing token example
class FencingLeader:
    def acquire_leadership(self):
        # Atomically increment and get fencing token
        token = self.consensus.increment_and_get("leader_token")
        self.current_token = token
        return token
    
    def write(self, data):
        # Storage rejects writes with old tokens
        self.storage.write(data, fencing_token=self.current_token)

# Storage side
class FencedStorage:
    def write(self, data, fencing_token):
        if fencing_token < self.highest_seen_token:
            raise StaleLeaderError("You've been fenced")
        self.highest_seen_token = fencing_token
        # Proceed with write
```

---

### 4.2 Sharding Failure Modes

| Failure | Symptoms | Detection | Recovery |
|---------|----------|-----------|----------|
| **Shard unavailable** | Partial outage (subset of users) | Health checks | Failover or wait |
| **Hot shard** | Latency spike on one shard | Latency monitoring | Rebalance, split |
| **Routing failure** | Wrong data returned, 404s | Consistency checks | Fix routing logic |
| **Cross-shard corruption** | Data appears in wrong shard | Periodic audits | Manual migration |
| **Resharding gone wrong** | Mixed data, missing data | Verification scripts | Rollback, retry |

**Hot Shard Runbook:**

```
1. DETECT
   - Alert fires: shard_latency_p99 > threshold
   - Check metrics dashboard for shard distribution

2. DIAGNOSE
   - Identify hot keys: query slow_log, trace requests
   - Determine cause: data skew? access skew? viral content?

3. MITIGATE (short term)
   - Enable caching for hot keys
   - Apply rate limiting to hot keys
   - Shift traffic from affected shard if possible

4. REMEDIATE (long term)
   - Split the hot shard
   - Redesign partitioning for hot keys
   - Add dedicated infrastructure for VIP keys

5. POST-MORTEM
   - Why wasn't this predicted?
   - How can we detect earlier next time?
   - Update capacity planning models
```

---

### 4.3 Staff-Level Trade-offs Matrix

| Dimension | Choice A | Choice B | How to Decide |
|-----------|----------|----------|---------------|
| **Consistency** | Strong (sync replication) | Eventual (async) | Data sensitivity, latency budget |
| **Availability** | Fail closed (reject if uncertain) | Fail open (best effort) | Safety vs. user experience |
| **Partition tolerance** | Favor consistency (CP) | Favor availability (AP) | Business requirements |
| **Complexity** | Simple (fewer shards) | Complex (more shards) | Team capacity, growth rate |
| **Cost** | Over-provision (headroom) | Right-size (efficiency) | Budget, scaling speed needed |

**The Hard Questions You'll Face:**

1. **"Should we shard now or wait?"**
   - Early: Pay complexity cost longer, but smoother scaling
   - Late: Simpler for now, but painful migration later
   - Answer: Shard when write bottlenecks are 6-12 months away

2. **"How many shards?"**
   - Too few: You'll need to reshard soon
   - Too many: Operational overhead, underutilized resources
   - Answer: 2-4x your current needs, with consistent hashing for easy expansion

3. **"Synchronous or asynchronous replication?"**
   - Sync: Pay latency for durability
   - Async: Fast but risk data loss
   - Answer: Semi-sync for critical data, async for everything else

4. **"Should we build or buy?"**
   - Build: Control, customization, learning
   - Buy: Speed, reliability, focus on business logic
   - Answer: Buy unless you have genuine unique requirements AND capacity

---

## Part 5: Brainstorming Questions

Before diving into your homework, reflect on these questions. They don't have clean answers—that's the point.

### On Replication

1. **Your multi-leader setup has 0.1% conflict rate. Is that acceptable?**
   - What does 0.1% mean in absolute numbers for your system?
   - Are all conflicts equal, or are some catastrophic?
   - How would you even detect silent data loss from LWW?

2. **Replication lag is normally 50ms but spikes to 30 seconds during daily batch jobs. What do you do?**
   - Is this lag causing user-visible problems?
   - Can you reschedule the batch job?
   - Should you route reads away from laggy replicas?
   - Is this a hardware problem or a query problem?

3. **Your follower promotion took 3 minutes during the last outage. How do you get to 30 seconds?**
   - What took the time: detection, decision, or execution?
   - Can you pre-warm standby replicas?
   - Is your health check interval too long?
   - Do you have automation, or was it manual?

### On Sharding

4. **You sharded by user_id, but now your most important query is "all orders from yesterday." What now?**
   - This query requires scatter-gather to all shards
   - Options: secondary index, materialized view, CQRS pattern
   - How did this query become important? Could you have predicted it?

5. **One customer is 40% of your traffic. They want dedicated infrastructure. How do you deliver this without rebuilding everything?**
   - Can you route them to specific shards?
   - Can you create a "VIP shard" just for them?
   - What isolation guarantees do they actually need?
   - How do you charge for this?

6. **A resharding migration is stuck at 95% for 3 hours. Rollback or push forward?**
   - What's blocking the last 5%?
   - Is the system functional in this state?
   - What's the risk of rollback vs. forward?
   - Who's available to help, and what's their expertise?

### On Trade-offs

7. **Your consistency requirements differ by data type. Users are OK with eventual consistency for likes count but need strong consistency for payments. How do you architect this?**
   - Same database with different replication settings?
   - Different databases for different data types?
   - Application-level routing logic?

8. **Adding a shard takes your team 2 weeks of work. Growth requires adding 2 shards per quarter. Is this sustainable?**
   - 4 weeks per quarter = 1/3 of your team's capacity on sharding
   - When does automation investment pay off?
   - Can you automate partially? Fully?

---

## Part 6: Homework Assignment

### Assignment: Design and Defend a Sharding Strategy

**Scenario:**

You're building a ride-sharing platform (like Uber/Lyft). You have three main data stores:

1. **User Profiles**: 50M users, 10KB average size, read-heavy (100:1 read:write)
2. **Ride History**: 500M rides, 5KB average size, time-series access patterns
3. **Real-time Location**: 2M active drivers, updated every 5 seconds, read by nearby riders

**Requirements:**
- 99.9% availability
- Read latency p99 < 100ms
- Write latency p99 < 200ms
- Data must survive single datacenter failure

**Your Task:**

**Part A: Design** (2-3 pages)

For EACH data store, specify:
1. Sharding strategy (hash, range, hybrid) with justification
2. Partition key with rationale
3. Replication approach (sync/async, leader-follower/multi-leader)
4. Number of shards and how you arrived at that number
5. How you'll handle growth (resharding approach)

**Part B: Failure Analysis** (1-2 pages)

For the data store of your choice:
1. List the top 5 failure modes
2. For each failure mode, describe:
   - Detection mechanism
   - Impact to users
   - Recovery procedure
   - Prevention measures

**Part C: Defend** (1 page)

Write a brief document addressing:
1. The trade-off you're least comfortable with
2. What would make you change your design
3. What you'd do differently with unlimited budget
4. What you'd do if you had to launch in 2 weeks instead of 2 months

---

### Evaluation Criteria

**Strong Answer Characteristics:**
- Clear reasoning for each decision
- Awareness of alternatives not chosen
- Specific numbers with justification
- Realistic failure mode analysis
- Acknowledges uncertainty and trade-offs

**Red Flags:**
- "Just use Cassandra/DynamoDB/etc." without justification
- Ignoring operational complexity
- Over-engineering for hypothetical scale
- Under-engineering for stated requirements
- Not addressing the failure modes

---

## Conclusion: The Art of Scaling

Replication and sharding are not just technical patterns—they're organizational decisions with long-term consequences.

**What I've learned after scaling multiple systems:**

1. **Start simple, evolve deliberately.** Most systems don't need sharding. Most that do can start with 4-8 shards, not 256.

2. **The partition key is forever.** Changing it is a full migration. Spend the time to get it right.

3. **Replication lag will bite you.** Build for eventual consistency from the start, even if you don't think you need it.

4. **Hot partitions will happen.** Design monitoring to catch them early, and have a playbook ready.

5. **Automate operations.** Manual resharding, failover, and recovery don't scale. Automate or die.

6. **The team matters.** A complex sharding setup requires on-call engineers who understand it. Staff for the complexity you're creating.

Your job as a Staff Engineer isn't to build the most sophisticated distributed system. It's to build the simplest system that meets requirements—and to know when requirements change enough to warrant increased complexity.

Scale is not a goal. Serving users is. Keep that in focus, and the sharding decisions become clearer.

---

*End of Volume 3, Part 2*

---

## Quick Reference Card

### Replication Decision Tree

```
Need to scale reads?
    YES → Add read replicas
        Need strong consistency?
            YES → Route reads to leader after writes
            NO  → Load balance across replicas

Need to survive datacenter failure?
    YES → Cross-region replication
        Can tolerate async replication lag?
            YES → Async (faster, cheaper)
            NO  → Sync (slower, durable)

Need low-latency writes in multiple regions?
    YES → Multi-leader replication
        Can your data model handle conflicts?
            YES → Implement conflict resolution
            NO  → Reconsider, or accept data loss
```

### Sharding Decision Tree

```
Hitting single-node limits?
    NO → Don't shard. Go home.
    YES → Can you optimize queries first?
        YES → Do that first.
        NO  → Proceed to sharding...

What's your primary access pattern?
    Point queries (by ID) → Hash-based sharding
    Range queries (by time/range) → Range-based sharding
    Both → Compound key or hybrid

How will you handle growth?
    Predictable growth → Plan shard count for 2-3 years
    Unpredictable growth → Use consistent hashing
```

### Capacity Planning Formula

```
Required Shards = max(
    Total Data Size / Target Shard Size,
    Total Write QPS / Per-Shard Write Capacity,
    Total Read QPS / (Per-Shard Read Capacity × Replicas)
)

Add 50% headroom for safety.
Round up to power of 2 for consistent hashing.
```

### Common Failure Modes Quick Reference

| Failure | Symptom | First Response |
|---------|---------|----------------|
| Leader crash | Writes fail | Promote replica |
| Replication lag spike | Stale reads | Route to leader |
| Hot shard | Latency spike | Enable caching |
| Split brain | Data divergence | Fence one side |
| Shard unavailable | Partial outage | Failover or wait |

### Migration Checklist

```
□ Backups verified and tested
□ Rollback plan documented
□ Monitoring dashboards ready
□ On-call team briefed
□ Customer communication prepared
□ Maintenance window scheduled
□ Double-write enabled and verified
□ Backfill progress tracking in place
□ Verification queries ready
□ Cutover runbook reviewed
```

### Key Metrics to Monitor

**Replication:**
- Replication lag (seconds behind leader)
- Replication throughput (bytes/second)
- Failover time (time to promote replica)

**Sharding:**
- Per-shard QPS and latency
- Shard size distribution
- Cross-shard query percentage
- Hot key detection

**Operations:**
- Migration progress percentage
- Data verification checksums
- Capacity utilization per shard

---

*End of Volume 3, Part 2: Replication and Sharding — Scaling Without Losing Control*

---
