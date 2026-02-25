# What is Sharding?

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

One notebook. 500 pages. School notes. Personal diary. Contacts. Shopping lists. Birthday reminders. Everything. You flip. And flip. Looking for your friend's number from three months ago. Takes forever. The notebook is heavy. Falling apart. And here's the crazy part — you CAN'T find anything because everything is crammed into ONE place. So you buy three notebooks. Notebook A-H. Notebook I-P. Notebook Q-Z. Split by first letter. Now finding anything is three times faster. Each notebook is smaller. Lighter. Manageable. That moment — that split — is sharding. Let that sink in.

---

## The Story

You write everything in one book. At first it's perfect. Easy. One place. But it fills up. 500 pages. You can't find anything. Flipping through takes forever. The book becomes a burden. So you make a decision. You buy three notebooks. You split by topic. Notebook A-H: names starting with A through H. Notebook I-P: I through P. Notebook Q-Z: Q through Z. Now when you want "Priya's number"? You go straight to Notebook 3. When you want "Arjun's address"? Notebook 1. Each notebook is smaller. Easier to carry. Easier to search. That's exactly what sharding does to a database.

A **shard** is a piece of the whole database. Each shard holds a SUBSET of the data. Not a copy — a piece. Shard 1 has users A-H. Shard 2 has I-P. Shard 3 has Q-Z. Together they form the complete dataset. But each runs independently. Can be on a different machine. Different disk. Different CPU. One massive database becomes many smaller ones.

Why shard? Because one database can't handle the volume. Disk full. CPU maxed. Queries too slow. Connections exhausted. You've hit the ceiling. Sharding is the way out. Split the data. Spread the load. Scale horizontally.

But here's where things go WRONG. Cross-shard queries are HARD. "Find all orders above Rs 1000" — you have to ask EVERY shard. Joins across shards? Nearly impossible. User on Shard 1. Orders on Shard 2. To combine them? You fetch from both. Merge in your application. It gets messy. Fast.

---

## Another Way to See It

A restaurant with one kitchen. Orders pile up. One chef. One oven. Can't keep up. So you open two more kitchens. Kitchen 1 handles tables 1-10. Kitchen 2 handles 11-20. Kitchen 3 handles 21-30. Each kitchen is independent. Its own orders. Its own capacity. The total capacity tripled. But "give me a summary of ALL orders today" — now you must ask all three kitchens. Merge the data. That's the trade-off. Split for scale. Pay with query complexity.

---

## Connecting to Software

**Shard =** a piece of the whole. Each shard is an independent database. Subset of rows. Subset of tables. Usually on a different machine. Different disk. Different network.

**Why shard:** One DB cannot handle the volume. Disk full. CPU maxed. Queries too slow. Connections exhausted. Replication helps reads — but writes still bottleneck on one machine. Sharding splits the data. Writes go to different shards. Load distributes.

**Each shard:** Runs its own database instance. MySQL. PostgreSQL. Whatever you use. It just holds a fraction of the data. The application layer routes: "This user? Shard 2. That user? Shard 1."

**The cost:** Cross-shard queries. Aggregations. JOINs. "Find all users who spent more than Rs 5000" — query every shard. Merge results. Expensive. Complex. Sometimes you just can't do it elegantly.

---

## Let's Walk Through the Diagram

```
SHARDING: ONE DATABASE → MANY

Before:                         After:
┌─────────────────────┐        ┌──────────┐ ┌──────────┐ ┌──────────┐
│   Single Database   │        │ Shard 1  │ │ Shard 2  │ │ Shard 3  │
│   ALL users        │   →    │ Users   │ │ Users   │ │ Users   │
│   ALL orders       │        │ A-H     │ │ I-P     │ │ Q-Z     │
│   One machine      │        │ Orders  │ │ Orders  │ │ Orders  │
│   Bottleneck       │        │ A-H     │ │ I-P     │ │ Q-Z     │
└─────────────────────┘        └──────────┘ └──────────┘ └──────────┘
                                        │         │         │
                                        └─────────┴─────────┘
                                        App routes by partition key
```

Step 1: You have one database. Too big. Too slow. Step 2: Pick a partition key. User ID. Name. Region. Step 3: Split. Shard 1 gets its range. Shard 2 gets its range. Step 4: Application routes each request to the right shard. Step 5: Scale. Add more shards when needed. The logic lives in your code.

---

## Real-World Examples (2-3)

**1. Instagram:** PostgreSQL. Billions of photos. One database? Impossible. They sharded. Each shard handles a range of user IDs. User 1-10 million → Shard 1. 10-20 million → Shard 2. And so on. The architecture that scaled them to a billion users.

**2. Uber:** Trip data. Millions of rides per day. Sharded by city. By region. By time. Each shard manages its slice. Queries like "all trips in Mumbai last week" — hit one shard. Fast. "All trips globally" — hit all. Expensive. Trade-off.

**3. Flipkart:** Product catalog. Orders. Sharded by user ID for personalization. By order ID for order lookup. Different tables. Different keys. The right partition key per use case.

---

## Let's Think Together

You shard users by first letter of name. Shard A-H gets users whose names start with A through H. Shard I-P gets I through P. Shard Q-Z gets Q through Z. Simple. But what if 60% of your users have names starting A through H?

*Pause. Think about that.*

Shard A-H is MASSIVE. Three times the size of the others. It gets 60% of the traffic. It becomes the bottleneck. The other shards sit idle. You've created a hot shard. The partition key matters. A lot. Names? Skewed. User IDs? Usually better. Region? Depends on your data. Choose wisely. We'll dive into partition keys next.

---

## What Could Go Wrong? (Mini Disaster Story)

Black Friday. E-commerce site. Sharded by user_id. Great. Until someone runs: "Find all orders above Rs 1000 for our loyalty report." The query hits every shard. All 50 of them. Each shard scans millions of rows. The merge takes forever. Database connections exhausted. The site slows. Checkout times out. Engineers didn't think about cross-shard queries. They optimized for "get user X's orders" — fast. But "get all high-value orders" — killed the system. Lesson: know your query patterns BEFORE you shard. Design for how you'll actually use the data.

---

## Surprising Truth / Fun Fact

Instagram sharded their PostgreSQL database to handle billions of photos. Each shard handles a range of user IDs. The migration was massive. They ran both systems in parallel. Dual-wrote. Verified. Gradually shifted reads. Then writes. Took months. But it worked. Sharding is not a quick fix. It's a fundamental architectural decision. And when done right — it scales.

---

## Quick Recap (5 bullets)

- **Shard** = a piece of the whole database. Each holds a subset. Independent. Often on different machines.
- **Why shard:** One DB can't handle volume — disk, CPU, queries, connections. Scale horizontally.
- **Cost:** Cross-shard queries are hard. "Find all X" means query every shard. JOINs across shards? Nearly impossible.
- **Partition key** = how you decide which shard gets which row. Choose wrong → hot shards, skew, pain.
- Real systems: Instagram, Uber, Flipkart — all shard. The pattern that scales the internet.

---

## One-Liner to Remember

> One notebook fills up. Split into three. Each holds a piece. Finding things gets faster. That's sharding — one database becomes many.

---

## Next Video

You've decided to shard. But HOW do you decide which shard gets which row? The partition key. Split by user_id? By date? By region? The wrong choice fills one shard and empties the rest. The library analogy will show you why. That's next.
