# Read-Your-Writes Consistency
## Video Length: ~4-5 minutes | Level: Staff
---
## The Hook (20-30 seconds)

You update your social media bio to "Software Engineer." You refresh the page. It still shows "Student." You refresh again. Still "Student." Panic. "Did it save?!" Ten seconds later: "Software Engineer." What happened? You WROTE to the primary database. You READ from a replica that hadn't caught up yet. Your own write was invisible to you. Read-your-writes consistency means: after YOU write something, YOUR subsequent reads should always see that write. Others may see a delay. But YOU should always see YOUR changes.

---

## The Story

You have a leader-follower database. Writes go to the leader. Reads can go to followers (replicas) for scalability. Great. Lower load on the leader. Fast reads from nearby replicas. But here's the trap: replication is asynchronous. There's lag. 100ms. 500ms. Sometimes seconds. You write "bio = Software Engineer" to the leader. Immediately you read. Your read goes to a replica. The replica hasn't replicated that write yet. You get "bio = Student." Your own update is invisible. Confusing. Frustrating. Users think the app is broken.

---

## Another Way to See It

Imagine a classroom. Teacher writes on the blackboard. "2 + 2 = 4." You're in the front row. You see it immediately. Someone in the back row hasn't seen it yet — their view is blocked. A moment later, they see it. In a database, the "front row" is the leader. The "back row" is the replica. When YOU write, you're at the front. Your next read should come from the front — where you just wrote. Not from the back, where your write hasn't arrived.

---

## Connecting to Software

**The problem.** Leader-follower replication. Writes → leader. Reads → follower (or load-balanced across followers). Follower lags. You write. You read from follower. Stale. Your own write is invisible.

**Solution 1: Route recent writers to leader.** Track "last write timestamp" per user/session. If the user wrote within the last N seconds (e.g., 5 seconds), route their reads to the leader. After N seconds, safe to send to replicas. Small percentage of reads hit leader. Worth it for consistency.

**Solution 2: Sticky sessions.** Route the user's reads to the same replica that received their write. But wait — writes go to leader. So: for a user who recently wrote, route ALL their traffic (reads and writes) to the leader. Sticky to leader for writers.

**Solution 3: Client-side version tracking.** Client tracks its last write version. On read, client sends "I need at least version X." Server ensures response is at least that fresh. May need to read from leader or wait for replica to catch up. More complex to implement but works across any topology. Some databases expose this natively.

**Trade-off.** Routing reads to leader for recent writers increases leader load. But it's a small fraction of total reads. Most users aren't writing constantly. A user who just posted might reload the feed — that read goes to leader. Everyone else reads from replicas. Acceptable trade-off for correctness. Get it wrong and users think the app is broken. "I just saved that. Where is it?" Never a good support ticket.

---

## Let's Walk Through the Diagram

```
    WITHOUT Read-Your-Writes
    
    User: "Update bio to Engineer"
              │
              ▼
    ┌─────────┴─────────┐
    │     LEADER        │  ← Write goes here (saved!)
    │  bio = Engineer   │
    └─────────┬─────────┘
              │ replicate (500ms lag)
              ▼
    ┌─────────────────┐
    │    REPLICA      │  ← Read goes here (stale!)
    │  bio = Student  │  User sees OLD data. Confusion!
    └─────────────────┘
    
    WITH Read-Your-Writes
    
    User: "Update bio" + "Read bio" (within 5 sec)
              │
              ▼
    ┌─────────────────┐
    │     LEADER      │  ← BOTH go to leader
    │  bio = Engineer │  User sees their own write. ✓
    └─────────────────┘
```

Key insight: same user, recent write → read from leader. No replica for that user until lag has passed.

---

## Real-World Examples (2-3)

**Facebook** uses read-your-writes. Post something. Refresh. You see it. They route your reads to the primary (or a sufficiently fresh replica) when you've recently written. They can't show you a stale version of your own post.

**Twitter** after tweeting: your tweet appears immediately. That's read-your-writes. Your write is reflected in your next read. They don't send that read to a lagging replica.

**E-commerce** checkout: place order, see confirmation. If the confirmation read hit a stale replica and said "no order," user would panic. "Did my payment go through?!" Read-your-writes ensures the confirmation matches the write. User sees what they just did. Trust. No support tickets.

---

## Let's Think Together

User updates profile. 100ms later, reads from replica. Replica lag: 500ms. What do they see? How do you fix it?

**Answer:** They see old data. Their write arrived at the leader 100ms ago. Replica hasn't replicated it yet (needs 500ms). Fix: route their read to the leader. They wrote recently — within the lag window. So their read must go to the leader. Implementation: track last_write_time per session. If now - last_write_time < replica_lag, read from leader. Simple. Effective.

---

## What Could Go Wrong? (Mini Disaster Story)

A bank allowed reads from replicas for all users. User transfers $100. Immediately checks balance. Read went to a lagging replica. Balance showed pre-transfer amount. User thought transfer failed. Tried again. Double transfer. $200 gone. Read-your-writes isn't just UX — for financial systems, it's correctness. Lesson: For critical flows (payments, balance), never read from stale replicas for the actor who just wrote.

---

## Surprising Truth / Fun Fact

Some systems use "session consistency" — same as read-your-writes but scoped to a session. If you're in the same session (same cookie, same connection), you see your writes. Different session? Eventual consistency is fine. One user's view is consistent. Across users, eventually consistent.

---

## Quick Recap (5 bullets)

- Read-your-writes: after you write, your reads must see that write. Your updates should never be invisible to you.
- Problem: reads from replicas can be stale; your write might not have replicated yet.
- Fix: route reads to leader for users who wrote recently (within lag window).
- Alternative: sticky sessions (same replica) or client-side version tracking.
- Trade-off: more leader load for recent writers, but usually acceptable.

---

## One-Liner to Remember

**Your writes should be visible to you. Route recent writers' reads to the leader. Don't let replicas hide your own updates.**

---

## Next Video

Next up: **Monotonic Reads** — you refresh a cricket score. It goes backwards. 250 then 230? That shouldn't happen. Let's fix time travel. Read-your-writes fixes "my own updates." Monotonic reads fixes "my view never goes backward."
