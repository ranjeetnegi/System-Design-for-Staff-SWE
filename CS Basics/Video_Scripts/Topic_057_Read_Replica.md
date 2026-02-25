# What is a Read Replica? Why Separate Read and Write?

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A famous street food stall. ONE cook. He takes orders. He cooks. He answers questions. "What is in the biryani?" "How spicy is the paneer?" 10 customers — fine. 50 — he sweats. 100 — he is drowning. Then he notices something. 80% of people just want to SEE the menu. Just ASK. Only 20% actually order. So he hires an assistant. She stands outside with a COPY of the menu. She answers all the questions. He handles only the orders. Suddenly both are relaxed. Customers are happy. That assistant? That is a read replica. And it changes everything.

---

## The Story

One cook. One person. He does EVERYTHING. Takes the order. Cooks the food. Answers "What ingredients do you use?" "Is it vegetarian?" "How much for a half plate?" Every question hits him. Every order hits him. The line grows. He cannot keep up. Frustration. Burnout. Collapse.

But here is the insight. Most people are just LOOKING. Browsing. Reading. "What do you have?" "How much does it cost?" They are not buying yet. Maybe 80% of interactions are reads. Questions. Only 20% are writes. Actual orders.

So the cook thinks: what if someone else handled the questions? He hires an assistant. She has a COPY of the menu. Same prices. Same items. She stands outside. "What is in the biryani?" — She answers. "How spicy?" — She answers. The cook NEVER hears those questions. He only gets the orders. The real writes. The actual work that changes things.

Now both are relaxed. The assistant handles the crowd. The cook focuses on cooking. Throughput? Doubled. Tripled. Same stall. Same cook. One copy. That assistant? That is a **read replica**. A copy of the data that serves reads. Only reads. The cook is the **primary**. He handles writes. The replica handles reads.

---

## Another Way to See It

A teacher writes on the whiteboard. The primary source. 30 students need to see it. They could all crowd the whiteboard. Block the teacher. Slow everything down. Or — each student takes a PHOTO of the whiteboard. Now they check their photo. "What did the teacher write?" They look at their copy. The teacher keeps writing. Students read from their photos. The whiteboard is the primary. The photos are read replicas. Same information. Distributed. No crowding.

---

## Connecting to Software

**The pattern:** Most apps are 80–90% reads, 10–20% writes. Reads dominate. So we split the load.

**Primary (leader)** database: Handles ALL writes. Insert, update, delete. One source of truth. The cook. The whiteboard.

**Read replicas:** COPIES of the primary. They receive data through **replication**. They serve reads. SELECT queries. "Show me the menu." "List products." "Get user profile." Multiple replicas = scale reads horizontally. Add a 2nd replica. 3rd. 4th. More read capacity.

**Writes?** Still go to ONE primary. You cannot have 5 people taking orders and updating the menu independently. Chaos. One primary. Many replicas. That is the rule.

**Routing:** Your application code — or a proxy like PgBouncer, or your cloud provider — decides: "Is this a read? Send to a replica. Is this a write? Send to the primary."

---

## Let's Walk Through the Diagram

```
                    [User: Write Order]
                            |
                            v
                    +---------------+
                    |  PRIMARY DB   |  <-- All writes come here
                    |  (The Cook)   |
                    +---------------+
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
       +-----------+ +-----------+ +-----------+
       | REPLICA 1 | | REPLICA 2 | | REPLICA 3 |  <-- Copies, serve reads only
       +-----------+ +-----------+ +-----------+
              ^             ^             ^
              |             |             |
       [User: Read Menu] [User: Read] [User: Read]

Writes → Primary. Reads → Replicas. Scale reads by adding more replicas.
```

---

## Real-World Examples (2-3)

**1. E-commerce product listing** — Millions of users browse products. Reads. Few actually buy. Writes. The product catalog is read from replicas. The checkout, the order insert? Goes to the primary. Same data. Split load.

**2. Social media feed** — Scrolling through posts? Read from a replica. Posting a new photo? Write to the primary. 90% of traffic is reads. Replicas absorb it.

**3. Netflix** — Browsing titles, watching (streaming reads)? Replicas. Adding to your list, updating profile? Primary. The pattern is everywhere.

---

## Let's Think Together

**Question:** You add a 4th read replica. Does write performance improve?

**Pause. Think.**

**Answer:** No. Write performance does NOT improve. Writes still go to ONE primary. Adding replicas only helps reads. More replicas = more capacity for SELECT queries. But inserts, updates, deletes? Still one primary. One bottleneck. If writes are slow, replicas will not fix it. You need something else — partitioning, caching, a different strategy. Replicas solve the READ problem. Not the write problem.

---

## What Could Go Wrong? (Mini Disaster Story)

**Replication lag.** User writes a comment. Clicks Submit. The write goes to the primary. Success! The user refreshes the page. The page loads from a REPLICA. But the replica has not received that comment yet. It is a few hundred milliseconds behind. The user sees... nothing. "Where did my comment go?!" Panic. Confusion. They post it again. Duplicate. The problem? Read-your-own-writes. You wrote to primary. You read from replica. Replica was lagging. We will fix this in the next video. For now — know this: replicas are behind. Sometimes by a little. Sometimes by a lot.

---

## Surprising Truth / Fun Fact

Amazon RDS — their managed database service — supports up to **15 read replicas** per primary. One primary. Fifteen copies. That is 15x read throughput with minimal effort. Add a replica. Point reads at it. Done. No code change for basic setup. The cloud made this pattern trivial. Every startup uses it.

---

## Quick Recap (5 bullets)

- **Most apps:** 80–90% reads, 10–20% writes. Reads dominate.
- **Primary** handles ALL writes. **Read replicas** are copies that handle reads only.
- **Replication** = primary copies data to replicas. Add more replicas = scale reads.
- **Writes** still go to ONE primary. Replicas do NOT improve write performance.
- **Replication lag** = replicas are behind. Can cause "read your own write" issues. More on that next.

---

## One-Liner to Remember

> One cook takes orders. Many assistants hold the menu. Same data. Split the work.

---

## Next Video

So you have replicas. Reads are fast. But wait — how does that COPY actually get to the replica? How does the primary tell the replica "here is the new data"? And what happens when the replica is BEHIND? When your comment does not show up after you post it? Next: **Database Replication** — how the leader talks to the followers. And why that conversation can go wrong.
