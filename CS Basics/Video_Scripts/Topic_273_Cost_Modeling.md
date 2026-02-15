# Cost Modeling: Major Drivers

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Moving to a new city. Monthly costs: rent (biggest), electricity, water, internet, groceries, transport. You budget by understanding the MAJOR drivers. Rent is 40%? Optimize there first. Cloud costs work the same. What are the biggest line items? Compute (VMs, containers). Storage (disks, object storage). Network (data transfer). Managed services (databases, caches). You optimize by understanding which driver dominates. A 10% cut on your biggest cost beats a 50% cut on a tiny one. Know your drivers.

---

## The Story

The cloud bill arrives. Five digits. You open it. Hundreds of line items. EC2. S3. RDS. Data transfer. ElastiCache. You're lost. Where do you start? Cost modeling is breaking the bill into categories. Understanding what drives each. And focusing optimization where it matters. The Pareto principle: 80% of cost often comes from 20% of the drivers. Find that 20%. Fix that. Ignore the rest for now. Unless you love spreadsheets, you can't optimize everything. Prioritize by impact. Compute. Storage. Network. Managed services. These four usually cover most of the bill. Let's break them down.

Think of it like a diet. You're trying to lose weight. You track: calories from sugar, from fat, from protein. Sugar is 40% of your calories. Cutting sugar has the biggest impact. Cloud cost modeling is the same. Find your "sugar." Cut that. Don't obsess over the 2% from minor services until the big ones are optimized.

---

## Another Way to See It

A restaurant's costs. Food (ingredients). Labour. Rent. Utilities. If rent is 30% of costs, negotiating rent matters more than switching to cheaper napkins. Cost modeling tells you: food 40%, labour 35%, rent 20%, other 5%. Focus on food and labour first. Cloud: compute 45%, storage 25%, network 20%, other 10%. Focus on compute first. Then storage. Then network. Priority order. Impact order.

---

## Connecting to Software

**Compute:** VMs (EC2, GCE, Azure VMs), containers (EKS, ECS), serverless (Lambda). Charged per hour, per second, or per invocation. Often the biggest line item. Right-sizing matters. Are you running 8-core VMs when 2 cores would do? Reserved instances or savings plans: commit for 1–3 years, save 30–60%. Spot instances: interruptible, 70–90% cheaper for fault-tolerant workloads. Kubernetes: are you over-provisioning? Requests vs limits. Idle pods cost money. Compute is usually the first place to look. Easy wins: turn off dev/staging at night. Downsizing. Reserved capacity.

**Storage:** S3 ($0.023/GB/month for standard). EBS ($0.10/GB/month for gp3). Database storage. Often grows quietly. You add data. You never delete. The bill creeps up. One team had 500GB in S3. They forgot. Two years later: 50TB. The bill shocked them. Storage lifecycle: move old data to colder tiers (S3 Infrequent Access, Glacier). Delete what you don't need. Database storage: are you over-provisioned? Storage often grows until someone notices. Audit. Clean. Tier. Compress.

**Network:** Data transfer between regions ($0.02/GB). Between availability zones ($0.01/GB). Out to the internet ($0.09/GB). THE hidden cost killer. You build a global app. US users hit US servers. EU users hit EU servers. But you're replicating data US ↔ EU. 10TB/month. $0.02/GB = $200/month for cross-region transfer alone. Multi-region architecture has a network cost. Reduce: co-locate data with users. Use CDNs. Compress. Batch. Minimize cross-region calls. Network costs surprise people. Model them early.

**Managed services:** RDS, ElastiCache, MSK, etc. Premium for operational simplicity. You pay 2–5x the cost of self-managed. Worth it for many teams—no DevOps headcount. But know the cost. Sometimes self-managing at scale saves millions. Sometimes the managed service is cheap for your scale. Do the math. Managed services are easy to add. "Let's use ElastiCache." Fine. Add it to the cost model. Track it. Don't let it become invisible.

---

## Let's Walk Through the Diagram

```
TYPICAL CLOUD BILL BREAKDOWN:

Compute    ████████████████████████████████  45%  → Right-size, reserved, spot
Storage    ███████████████████               25%  → Tier, delete, compress
Network    ██████████████                    20%  → Co-locate, CDN, reduce
Managed    ██████                            10%  → Evaluate self-managed vs managed
Other      ███                                5%  → Ignore for now

Total: $50,000/month
Biggest win: Compute. 10% savings = $2,250/month.
Smallest win: Other. 50% savings = $1,250/month.
Order matters. Go for compute first.
```

---

## Real-World Examples (2-3)

**Dropbox** famously saved millions by moving from AWS to their own infrastructure. At their scale, compute and storage costs dominated. Building their own made economic sense. Most companies aren't Dropbox scale. But the lesson: understand your cost drivers. At some scale, the math changes.

**A startup** had a $10K monthly AWS bill. They did a cost model. 60% was EC2—dev/staging running 24/7. They turned off dev at night. Shut down unused environments. Bill dropped to $4K. No architecture change. Just awareness. Cost modeling revealed the waste.

**Netflix** publishes their approach. They use spot instances for batch workloads. Reserved for baseline. Optimize data transfer with regional caches. They've written extensively. Cost is a first-class metric. They model. They optimize. They share. Learn from them.

---

## Let's Think Together

**"Your app transfers 10TB/month between US and EU regions. At $0.02/GB = $200/month for JUST cross-region transfer. How to reduce?"**

Options: (1) Co-locate. EU users read from EU. US users from US. Don't replicate everything. Replicate only what's needed. (2) Compress. 10TB compressed might be 2TB. Same data. 80% less transfer. (3) Batch. Instead of real-time sync, batch hourly. Fewer round-trips. Smaller total data if you're sending deltas. (4) CDN. Static assets—serve from edge. Don't cross oceans for images. (5) Audit. Do you need 10TB? Maybe half is redundant. Logs. Debug data. Old backups. Reduce the data that moves. Network cost scales with bytes. Fewer bytes = lower bill. Often the biggest lever.

---

## What Could Go Wrong? (Mini Disaster Story)

A team built a data pipeline. US → EU. Replicate user data for GDPR. They used Kafka. Cross-region replication. Worked great. Bill came. $50,000 for data transfer. They hadn't modeled it. 50TB/month at $0.02/GB. They thought "Kafka is cheap." The data transfer wasn't. They re-architected: aggregate in US, send only summaries to EU. 5TB instead of 50TB. Bill: $5,000. Lesson: model network cost for multi-region. It's not free. It's often the surprise. Include it in design. Before you build.

---

## Surprising Truth / Fun Fact

AWS (and other clouds) charge for data transfer OUT but not IN. "Data transfer in" is free. "Data transfer out" costs. Why? They want to make it easy to put data in. Hard to take it out. Vendor lock-in. The corollary: moving to another cloud means paying to get your data out. Cost modeling should include "what if we leave?" Egress fees for migration. Plan for it. Know the number. It's part of the total cost of ownership.

---

## Quick Recap (5 bullets)

- **Compute** = VMs, containers; often biggest; right-size, reserved, spot.
- **Storage** = S3, EBS, DB; grows quietly; tier, delete, compress.
- **Network** = data transfer; hidden killer; co-locate, CDN, reduce bytes.
- **Managed** = RDS, ElastiCache; premium for convenience; evaluate.
- **Optimize** = find the 20% that drives 80%; fix that first.

---

## One-Liner to Remember

*Cost modeling is finding the biggest line items—optimize the 40% before you worry about the 2%.*

---

## Next Video

Next: Migration without downtime. Changing the engine of a plane mid-flight. In software: dual-write, CDC, strangler fig. Zero downtime migration. See you there.
