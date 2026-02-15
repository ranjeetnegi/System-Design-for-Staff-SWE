# When Does a Single Database "Run Out"?

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

One notebook. Homework. Friends' numbers. Shopping lists. Diary. Everything in one place. Easy. Simple. Then it fills up. You buy a bigger one. Fills up again. Even bigger. Now it's heavy. Hard to flip. Finding anything takes forever. At some point — one notebook isn't enough. You need a system. School notebook. Personal notebook. Work notebook. That moment? That's when your database outgrows itself. Let that sink in.

---

## The Story

You have a notebook. You write everything in it. At first, it's perfect. One place. Everything you need. Easy to carry. Easy to find. But the notebook fills up. You buy a bigger one. 200 pages. 400 pages. It fills up again. You get an even bigger one. 1000 pages. Now it's heavy. Hard to flip through. Finding a phone number from six months ago? Good luck. The notebook has become a burden. At some point, one notebook ISN'T ENOUGH. You need a system. One notebook for school. One for personal. One for work. Separated. Organized. That's exactly what happens to databases.

A single database works brilliantly — until it doesn't. The limits creep up. Disk space. CPU. RAM. Connections. Write throughput. One machine can only do so much. And when you hit those limits? Queries slow down. Timeouts. Crashes. The biggest day of the year — flash sale, product launch — and your database dies. Here's where things go wrong.

---

## Another Way to See It

A restaurant. One chef. One kitchen. Small restaurant? Fine. The chef handles ten orders an hour. But the restaurant gets famous. Fifty orders an hour. A hundred. The chef can't keep up. Orders pile up. Customers wait. Food gets cold. One kitchen isn't enough. You need more chefs. More stations. More ovens. That's database scaling. One machine → many machines.

---

## Connecting to Software

**Single DB limits:**

**Disk space:** Your data grows. 10 GB. 100 GB. 1 TB. The disk fills. You can't add more rows. Out of space.

**CPU:** Too many queries. Complex JOINs. Aggregations. One CPU (or a few cores) gets maxed. Queries queue. Response time explodes.

**RAM:** The database caches hot data in memory. RAM fills. Can't cache enough. More disk reads. Slower everything.

**Connections:** Each client holds a connection. 100 users? Fine. 10,000? Connection pool exhausted. "Too many connections" error. New users can't even connect.

**Write throughput:** One machine can only write so fast. Disks have limits. Replication has limits. Writes per second cap out. A single SSD might handle 10,000 writes per second. Your app needs 50,000. One machine can't do it.

**Signs your DB is dying:** Queries getting slower. Disk usage at 90%+. CPU constantly at 100%. Connection pool exhausted. Replication lag growing. Timeouts. Errors. "Database overloaded." Alerts firing. On-call engineers paged. The writing is on the wall — act before it's too late.

---

## Let's Walk Through the Diagram

```
THE SCALING JOURNEY:

Single DB                    Read Replica              Sharding
   |                              |                        |
   |  All reads + writes          |  Writes → Primary       |  Data SPLIT
   |  on one machine              |  Reads → Replicas       |  across machines
   |                              |  (5x read capacity)     |  (horizontal scale)
   |                              |                        |
   |  Limit: 1 machine            |  Limit: Write            |  Limit: Complexity
   |  does everything             |  bottleneck remains      |  JOINs harder
   |                              |                        |
   ↓                              ↓                        ↓
 "Queries slow"           "Reads fast, writes           "Millions of rows
  "Disk full"              still limited"                per shard, scalable"
```

You don't jump to sharding on day one. You grow. Single → Replica → Vertical scaling (bigger machine) → Sharding. Each step buys you time.

---

## Real-World Examples (2-3)

**1. Flipkart Big Billion Days:** Millions of users. Flash sales. One database? It would die. They scale: read replicas for product browsing, caching for hot items, sharding for orders. The preparation matters. Ignore it? Chaos.

**2. Twitter (early days):** "Fail whale." Too many users. Single database. Couldn't keep up. They rebuilt. Sharding. Caching. Multiple databases. The fail whale disappeared.

**3. Startup growth:** Month 1: 100 users. One database. Fine. Month 12: 100,000 users. Queries slowing. Month 18: 1,000,000 users. Database on fire. The migration begins. Read replicas. Then sharding. The journey every growing app takes.

---

## Let's Think Together

Your app has 10 million users. Database handles 1,000 queries per second. During a flash sale, you expect 10,000 queries per second. What do you do?

*Pause. Think about it.*

You need 10x capacity. Options: (1) Read replicas — split reads across multiple machines. Writes still go to primary. (2) Caching — put hot product data in Redis. Reduce database hits. (3) Vertical scaling — bigger machine. Quick fix. Limited ceiling. (4) Connection pooling — reuse connections. Support more concurrent users. Often you combine: replicas + cache + pooling. Buy time. Plan for sharding when writes become the bottleneck. The key: anticipate. Don't wait for the crash.

---

## What Could Go Wrong? (Mini Disaster Story)

Ignore the signs. A startup. Big sale planned. Black Friday. Engineers see the metrics. CPU trending up. Disk at 85%. "We'll be fine." Sale starts. 10x traffic. Database melts. Queries timeout. Checkout fails. Cart fails. Homepage fails. Customers angry. "Your site is down!" Sales lost. Competitors win. Engineers scramble at 2 AM. Restart the database. Add a replica. Too late. The day is lost. Trust damaged. "Why didn't we scale earlier?!" Because they ignored the signs. One database. One point of failure. The biggest day. The biggest crash. Don't be that team.

---

## Surprising Truth / Fun Fact

Stack Overflow — one of the biggest programming sites on the internet — serves 1.3 billion page views per month with just 2 SQL Servers. Two. Not two thousand. Two. Sometimes one database (or two) IS enough. Longer than you'd think. Optimize first. Scale when you need to. Don't over-engineer on day one. But when the limits hit? Be ready. Know the signs. Plan the journey.

---

## Quick Recap (5 bullets)

- Single DB limits: **disk**, **CPU**, **RAM**, **connections**, **write throughput**
- Signs of trouble: slow queries, high disk/CPU, connection pool exhausted, replication lag
- Scaling path: Single DB → Read replica → Vertical scaling → Sharding
- Solutions preview: replicas (split reads), sharding (split data), caching (reduce load), archival (move old data)
- Plan ahead. Don't wait for the crash. Stack Overflow runs on 2 servers — but when you need more, be ready.

---

## One-Liner to Remember

> One notebook works until it doesn't. Know the limits. Know the signs. Scale before you break.

---

## Next Video

So you need more than one database. But what KIND? Tables and rows and JOINs? Or something different? SQL vs NoSQL. Two philosophies. Two ways to organize data. The closet analogy will change how you think. That's next.
