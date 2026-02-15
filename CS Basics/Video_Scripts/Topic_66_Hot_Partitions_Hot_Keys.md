# What are Hot Partitions and Hot Keys?

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A supermarket. 10 checkout counters. All open. Plenty of capacity. But Counter 7 is next to the exit. Everyone goes to Counter 7. Line of 50 people. Counter 7's cashier is drowning. Counters 1 through 6? Two people each. Counters 8, 9, 10? Empty. The supermarket has capacity. But it's all concentrated at ONE counter. That counter = a hot partition. One overwhelmed piece. The rest idle. Your database can have 100 shards. One gets 80% of the traffic. The whole system performs like ONE server. Here's where it gets worse.

---

## The Story

You've sharded. Beautiful. 10 shards. Even distribution. Hash-based. Should work. Then something happens. A celebrity posts. Justin Bieber. One tweet. Millions of reads. That tweet lives on one shard. One partition. One key. 100,000 requests per second hit that shard. The other 9 shards? Idle. You have 10x capacity. But one key uses it all. That's a **hot key**. One specific key — one row, one partition — getting way more traffic than others.

**Hot partition:** One shard receives WAY more traffic than others. Could be reads. Could be writes. Could be both. The shard's CPU maxes. Memory maxes. Connections max out. Other shards sit at 5% utilization. Wasted.

**Hot key:** One key. A viral tweet. A bestselling product. A celebrity profile. Thousands of accesses per second. That key lives in one partition. That partition = hot. The key IS the hot partition in key-value stores like DynamoDB.

Why does it happen? Skewed data. Some users are popular. Some products sell more. Bad partition key. Timestamp? All writes hit the latest shard. Viral events. World Cup final. One match. Millions watching. One key.

Impact? The hot shard's CPU, memory, connections max out. Queries timeout. Writes fail. Other shards idle. Your system performs like ONE server. You paid for 10. You get 1. Frustration.

---

## Another Way to See It

A highway. 10 lanes. One lane has an accident. Everyone merges to that lane. No. Actually — one lane goes to the popular exit. The mall. The stadium. Everyone wants that exit. That lane is packed. The other 9 lanes? Empty. Same road. Uneven load. One lane = hot. The rest = wasted.

---

## Connecting to Software

**Hot partition:** One shard gets disproportionate traffic. Reads, writes, or both. Becomes bottleneck. Others underused.

**Hot key:** One partition key value. One row. Or one logical partition. In DynamoDB: partition key = partition. Same key = same partition. High access = hot partition.

**Causes:**
- Skewed data: Popular users. Viral content. Natural distribution (Zipf's law).
- Bad partition key: Timestamp = latest partition hot. Low cardinality = clustering.
- Viral events: One item explodes. One key. All traffic.

**Impact:** Hot shard overload → timeouts, errors, crashes. That shard goes down? All data on it unavailable. Users see errors. System "down" for that data. Even though 90% of capacity is idle.

---

## Let's Walk Through the Diagram

```
HOT PARTITION / HOT KEY

10 Shards (even distribution by hash)

Shard 1   Shard 2   Shard 3   Shard 4   Shard 5   ...   Shard 10
   │         │         │         │         │              │
  5%        5%       80% ★      5%        5%             5%
   │         │         │         │         │              │
  Idle     Idle     MELTING    Idle     Idle            Idle
                     │
                     │ Hot key: celebrity_tweet_123
                     │ 100,000 req/sec
                     │ CPU 100%, Mem 100%
                     ▼
              Bottleneck. Rest wasted.
```

Step 1: Even distribution. Step 2: One key goes viral. Step 3: All traffic hits one shard. Step 4: That shard maxes. Others idle. Step 5: System throttles. Timeouts. Failures.

---

## Real-World Examples (2-3)

**1. Twitter during elections:** One politician's tweet. Millions of likes. Comments. Retweets. That tweet = one key. One partition. Hot. Twitter's systems designed for this. Caching. Fan-out. Pre-computation. Without it? That partition melts.

**2. Amazon Prime Day:** One product. Deals. Lightning deal. 10,000 people click "Add to Cart" per second. One product ID. One partition. Hot key. Amazon uses caching. Splitting. Salting. They know. They prepare.

**3. Instagram viral post:** One post. Millions of likes. Comments. That post's data = one partition. Hot. Instagram uses Redis cache. Replicated reads. They monitor key access in real-time. Detect hot keys. Mitigate before meltdown.

---

## Let's Think Together

Your partition key is user_id. Fair. Even. A celebrity with 100 million followers posts. What happens to their shard?

*Let that sink in.*

Every follow. Every like. Every comment. Every "load profile" request. Hits that user's shard. 100M followers. Even 1% active? 1 million concurrent. Their shard gets crushed. Hot key. Not from bad design — from reality. Popular = unequal. The partition key is correct. The traffic is not. You need: caching, read replicas, splitting, salting. We'll cover those next. The key isn't wrong. The world is skewed.

---

## What Could Go Wrong? (Mini Disaster Story)

E-commerce. Product table. Partition by product_id. Fine. Black Friday. One product goes viral. "Deal of the day." 50,000 reads per second. One product. One partition. Hot. The DynamoDB partition throttles. Read limit exceeded. Product page fails. "Can't load product." Other products work. Just that one. Customers frustrated. "Your site is broken!" Engineers: "It's just one product!" Yes. One product. One partition. One bottleneck. Hot key → shard overload → shard errors → users see failures. Fix: cache. Replicate. Salt. Next video.

---

## Surprising Truth / Fun Fact

DynamoDB has adaptive capacity. Automatically redistributes throughput to hot partitions. AWS built it because hot keys were the number one customer complaint. "I'm provisioned for 10,000 reads per second. Why am I throttled?!" One partition hit the limit. Others idle. Adaptive capacity: AWS gives more throughput to hot partitions. From the pool. Helps. Doesn't eliminate. You still need good design. Caching. Splitting. But it's a lifeline. AWS listened. Hot keys are that common.

---

## Quick Recap (5 bullets)

- **Hot partition:** One shard gets way more traffic. Bottleneck. Others idle.
- **Hot key:** One key (row, partition) accessed heavily. Viral content. Celebrity. Bestseller.
- **Causes:** Skewed data, bad partition key, viral events. Zipf's law.
- **Impact:** One shard maxed. Timeouts. Errors. System performs like one server.
- DynamoDB adaptive capacity helps. Not enough alone. Design for hot keys.

---

## One-Liner to Remember

> Ten counters. One by the exit. Everyone goes there. That one = hot. The rest = wasted. Same with shards.

---

## Next Video

Hot keys happen. What do you DO about them? Cache. Split. Salt. Three techniques. The supermarket manager's playbook. Next.
