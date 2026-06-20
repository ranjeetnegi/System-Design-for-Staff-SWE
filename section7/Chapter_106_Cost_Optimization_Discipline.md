# Chapter 85: Cost Optimization Discipline — Cloud Spend as Engineering Craft

> At L4, you don't think about cost. At L5, you consider cost in design reviews.
> At L6, you own the cost efficiency of your systems — you know where every
> dollar goes, you review it quarterly, and you treat runaway cloud spend as
> a production incident.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

Cost efficiency appears in system design (Ch38) as a design principle. This chapter
covers the ongoing discipline: how to review costs, how to attribute costs to teams
and features, how to identify savings opportunities, and how to execute cost reduction
without breaking production. Increasingly expected at L6 as cloud bills become
a major engineering concern at every company.

---

## Planned Content

### Part 1: Why Cost is an Engineering Responsibility
- Cloud spend at scale: a mid-size company at $10M/month AWS spend
- The math: 10% waste = $1M/month = $12M/year — the cost of 20 engineers
- Cost as a feature: "we could serve this at 1/10th the cost" is a real product advantage
- The common mistake: treating cost as finance's problem, not engineering's
- L6 framing: "I'm responsible for the reliability AND cost of my systems"

### Part 2: Cloud Cost Attribution
- The problem: a shared account with 50 services → which service costs what?
- Tagging strategy: tag every resource with team, service, environment, cost-center
- AWS Cost Explorer / GCP Cloud Billing: query costs by tag
- Showback vs. chargeback: showback = show teams their costs (no billing);
  chargeback = actually charge team budgets (stronger incentive)
- Per-feature costing: instrument your code to track which feature each request serves,
  then attribute infra cost to features → know what each feature actually costs

### Part 3: The Quarterly Cost Review Process
- Cadence: monthly review of top 10 cost categories; quarterly deep-dive per service
- What to look for: month-over-month growth faster than traffic growth (efficiency degrading),
  resources with low utilization (over-provisioned), orphaned resources (nobody's using this)
- Cost anomaly detection: alert when daily spend exceeds 2x the 7-day average
- The cost review meeting: 30 min, top 5 cost items, owner for each, action item with deadline

### Part 4: Compute Rightsizing
- The common failure: provision for peak, pay for peak 24/7 when traffic is bursty
- Rightsizing: analyze actual CPU/RAM usage → downsize instance type
- AWS Compute Optimizer / GCP Recommender: automated rightsizing suggestions
- Reserved Instances / Committed Use Discounts: commit to 1-3 years → 30-60% savings
  for baseline load; use spot/preemptible for batch jobs (70-90% savings)
- Auto-scaling: scale down at night, scale up during business hours
  → can save 40-60% on compute for workloads with predictable daily patterns

### Part 5: Storage Cost Optimization
- S3/GCS storage classes: Standard → Infrequent Access → Glacier (10x cheaper per TB)
- Lifecycle policies: auto-transition objects to cheaper storage after N days
- Delete what you don't need: log retention policies (90 days is usually enough)
- Compression: compress data before storing (Parquet vs. JSON: 10x smaller for analytics)
- Deduplication: detect and deduplicate identical objects (content-addressed storage)
- Real incident: Dropbox 2020 — implemented custom storage compression, saved $75M/year

### Part 6: Data Transfer and Networking Costs
- The surprise cost: data egress (leaving AWS/GCP) is expensive ($0.08/GB = $80/TB)
- CDN vs. direct egress: CDN costs $0.01/GB (8x cheaper); use CDN for all user-facing content
- Cross-AZ data transfer: often overlooked; $0.01/GB within a region adds up
- Colocation: keep services that talk to each other in the same AZ
- Compression for APIs: gzip/brotli responses → 60-80% less bandwidth → less egress cost

### Part 7: Database Cost Optimization
- Read replicas: add replicas for reads → cheaper than scaling primary for read-heavy workloads
- Caching: every cache hit is a DB query not executed → direct cost saving
- Query optimization: slow queries consume CPU → optimizing queries reduces DB instance cost
- Connection pooling: PgBouncer/RDS Proxy → fewer connections → smaller instance needed
- Archival: move old data to cheap storage (cold tier or S3) → keep hot DB small and fast

### Part 8: Building a Cost Culture
- Make costs visible: dashboard showing cost per service, per team, per feature
- Include cost in design reviews: "what does this cost to operate at 10x traffic?"
- Celebrate savings: a team that cuts costs by $500K/month did something real
- Avoid perverse incentives: don't punish teams that admit waste — reward fixing it
- Cost champions: one engineer per team who owns the cost review process

---

## The One-Sentence Summary

> "Cost optimization discipline = quarterly review (where does money go?) + attribution (which team/feature causes which cost?) + rightsizing (are we over-provisioned?) + storage lifecycle policies + CDN for egress — treating cloud spend as a production metric you own, not a finance problem you ignore, is what separates L5 from L6 on infrastructure ownership."

---

*Full chapter: ~2,500 lines. Pairs with Ch38 (Cost Efficiency in System Design).*
