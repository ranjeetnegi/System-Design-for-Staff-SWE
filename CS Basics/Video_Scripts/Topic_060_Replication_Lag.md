# What is Replication Lag and Why It Matters?

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You are in a classroom. The teacher writes a math problem on the whiteboard. 30 students copy it into their notebooks. Fast students finish in 2 seconds. Slow students take 10 seconds. During those 10 seconds — the slow student's notebook does NOT match the whiteboard. It is BEHIND. If someone checks that notebook, they see OLD information. Wrong information. That gap? Between the whiteboard and the notebook? That is replication lag. And it is the cause of some of the weirdest bugs in production. "I just posted that! Why don't I see it?!" Let me show you.

---

## The Story

The teacher writes: "Solve for x: 2x + 5 = 13." The whiteboard has the truth. The leader. Student 1 copies fast. 2 seconds. Her notebook matches. Student 2 is daydreaming. 10 seconds. His notebook is blank. Or has the OLD problem. During those 10 seconds, Student 2's notebook is STALE. Behind. Lagging.

Someone asks Student 2: "What is the problem?" He reads his notebook. "Solve for x: x + 2 = 5." Wrong. The teacher already changed it. But Student 2 does not know. He is lagging. That is **replication lag** — the delay between a write on the leader and the same write appearing on the follower.

In databases: Leader has the latest data. Replicas are copying. But copying takes time. Typically milliseconds. Under heavy load? Seconds. Under disaster? Minutes. Hours. During that gap, replicas serve OLD data. Stale reads. And that causes problems.

---

## Another Way to See It

A live sports match. The stadium. The fans see the goal the moment it happens. They celebrate. But the TV broadcast? It is 10 seconds behind. Cable delay. Streaming delay. People at home see the goal 10 seconds later. That delay is lag. The stadium is the leader. The TV broadcast is the replica. Same event. Different time. For 10 seconds, the two realities are different.

---

## Connecting to Software

**Replication lag** = the delay between a write on the leader and that write appearing on the follower. Measured in milliseconds, seconds, or more.

**How to measure:** Compare leader position (WAL offset, log sequence number) vs follower position. The gap = lag. "Leader at position 1000. Follower at 985. Lag = 15."

**Problems caused by lag:**

1. **Read-your-own-writes:** You post a comment. You refresh. The page loads from a replica. The replica has not received your comment yet. You see nothing. "Where did it go?!" Frustration.

2. **Stale reads:** Product price updated from Rs 1000 to Rs 500. Sale. But replicas still show Rs 1000 for 30 seconds. Users see different prices. Confusion. Complaints.

3. **Causal inconsistency:** You see a REPLY to a message. But not the original message. Why? Reply was written to leader. Replicated to your replica. Original was written later. Has not arrived yet. Order is wrong. Mind-bending.

**How to deal with it:**
- **Read-your-own-writes:** Route reads for data you JUST wrote to the leader. "Sticky" session: after a write, read from leader for 1-2 seconds. Then back to replica.
- **Sticky sessions:** Keep a user on the same replica. At least their reads are consistent (even if stale).
- **Monitor lag:** Alert when lag exceeds threshold. 1 second? 5 seconds? Act before users complain.

---

## Let's Walk Through the Diagram

```
TIMELINE OF REPLICATION LAG

Leader:   [write][write][write][write]...  Position: 100
                                              |
Follower 1 (fast):  [write][write][write]...  Position: 99   Lag = 1
                                              |
Follower 2 (slow):  [write][write]...         Position: 85   Lag = 15

User reads from Follower 2. Sees data from position 85.
User expects data from position 100. 15 writes missing.
STALE. LAGGING.
```

---

## Real-World Examples (2-3)

**1. Social media "missing post"** — You post. Refresh. Gone. Classic read-your-own-writes. Your post went to leader. Your refresh hit a lagging replica. Fix: read from leader right after your own writes.

**2. E-commerce price inconsistency** — Sale starts. Price drops. Some users see old price (replica). Some see new (leader or caught-up replica). Same product. Different prices. Chaos.

**3. Multi-region apps** — User in Tokyo writes. Replica in London is 200ms behind. User's friend in London reads. Does not see the write. "Did you get my message?" "No." Lag across distance.

---

## Let's Think Together

**Question:** User updates their profile picture. They immediately refresh the page. They see the OLD picture. Why? How do you fix it?

**Pause. Think.**

**Answer:** Why? The update went to the leader. The refresh was served by a replica. The replica had not received the new picture yet. Replication lag. Fix: For "read your own write" scenarios, route the user's reads to the LEADER for a short window after a write. Or use a session flag: "User just wrote. Next 2 reads go to leader." Or: Return the new profile picture in the write response. Client caches it. No need to read. Multiple solutions. The key: don't read your own write from a lagging replica.

---

## What Could Go Wrong? (Mini Disaster Story)

E-commerce site. Big sale. "All products 50% off!" Marketing updates the database. Prices drop. Leader has the new prices. Replicas? Lagging. 30 seconds behind. User A hits Replica 1. Sees Rs 500. Adds to cart. User B hits Replica 2. Still shows Rs 1000. Same product. Different prices. User B complains. "The site says 50% off but I see full price!" Support does not understand. "Clear your cache?" No. It is replication lag. Same product. Different replicas. Different truths. For 30 seconds, the site was broken. Not down. Just wrong.

---

## Surprising Truth / Fun Fact

At **Amazon**, even a few hundred milliseconds of replication lag can cause inconsistent shopping cart data across regions. Users add an item in the US. Check cart in Europe. Item missing. Or duplicate. That inconsistency — and the engineering to solve it — drove Amazon to build **DynamoDB**. Eventually consistent. But they had to design around lag. They could not eliminate it. So they built for it. Every big company fights this. You are not alone.

---

## Quick Recap (5 bullets)

- **Replication lag** = delay between leader write and follower receiving it. Millisecond to hours.
- **Problems:** Read-your-own-writes (post then refresh, gone). Stale reads (old prices). Causal inconsistency (reply before message).
- **Measure:** Leader position vs follower position. Gap = lag. Monitor it. Alert on it.
- **Fix read-your-own-writes:** Route post-write reads to leader. Or sticky session. Or return data in write response.
- **Reality:** Lag exists. Design for it. Don't assume replicas are instant.

---

## One-Liner to Remember

> The whiteboard has the truth. The notebook has a copy. The gap between them is lag. And lag causes lies.

---

## Next Video

So you understand replication. Sync vs async. Lag. You have a primary. Replicas. Reads scaled. But what happens when the primary DIES? Who takes over? How do you choose? And what if two nodes both think they are the leader? Consensus. Leader election. One of the hardest problems in distributed systems. Coming next.
