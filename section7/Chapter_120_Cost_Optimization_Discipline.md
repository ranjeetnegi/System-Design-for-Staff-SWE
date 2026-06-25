# Chapter 120: Cost Optimization Discipline — Cloud Spend as Engineering Craft

> *"At L4, you don't think about cost. At L5, you consider cost in design reviews. At L6, you own the cost efficiency of your systems — you know where every dollar goes, you review it quarterly, and you treat runaway cloud spend as a production incident."*

---

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                AT-A-GLANCE: COST OPTIMIZATION DISCIPLINE                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│  THE MATH         $10M/month AWS spend → 10% waste = $1M/month = $12M/year    │
│                   = the cost of 20 senior engineers                            │
│                   Even 5% savings = 1 additional engineer-equivalent budget    │
│                                                                                 │
│  BIGGEST LEVERS   1. Compute rightsizing + Reserved Instances (30-60% savings)│
│                   2. Storage lifecycle policies (S3 Standard → Glacier: 10x)   │
│                   3. CDN for egress (8x cheaper than direct egress)            │
│                   4. Spot/preemptible for batch jobs (60-90% savings)          │
│                   5. Eliminating orphaned resources (0% utilization)           │
│                                                                                 │
│  PROCESS          Monthly: top 10 cost categories, anomaly check              │
│                   Quarterly: per-service deep-dive, owner + action item        │
│                   Annual: RI/CUD commit review, vendor negotiation             │
│                                                                                 │
│  ATTRIBUTION      Tag every resource: team + service + environment + feature  │
│                   Without attribution: no accountability                       │
│                   With attribution: teams own their costs                      │
│                                                                                 │
│  L5 SIGNAL        Considers cost in design reviews                             │
│  L6 SIGNAL        Owns cost efficiency: reviews quarterly, alerts on anomalies,│
│                   treats $500K savings as real product work                    │
│                                                                                 │
│  WARNING          Cost optimization can break production if not done carefully │
│                   Use Expand and Contract (Ch116) patterns for risky changes   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: Why Cost Is an Engineering Responsibility

Cloud computing made infrastructure accessible. It also made it easy to forget that every resource costs money — because the bill arrives once a month instead of when you click "launch."

**The math at scale:**

```
Company size:        $10M/month AWS spend (medium-large company)
Typical waste:       15-25% of cloud spend is unused or over-provisioned
Waste in dollars:    $1.5M – $2.5M/month = $18M – $30M/year
                     = 30–50 senior engineers' fully-loaded cost

Achievable savings:  A focused 6-month cost optimization effort typically saves
                     20-40% on a historically unoptimized account.
```

**Cost as a feature:**

Engineers who dismiss cost optimization as "finance's problem" are missing a product lever. Cost efficiency directly enables:

- **Faster iteration:** Cheaper services → more can be built with the same budget
- **Competitive pricing:** 1/10th the cost to serve → margin to underprice competitors
- **Engineering headcount:** $5M/year in cloud savings → 8-10 additional engineers
- **Reliability headroom:** Efficient use of resources = more headroom before capacity limits

At companies like Netflix, Dropbox, and Cloudflare, infrastructure efficiency is a **strategic advantage**, not an accounting concern. Netflix's cost per streaming hour has declined while video quality has increased, enabling them to offer lower prices than competitors with similar quality.

**The engineering responsibility framing:**

```
L4 engineer:  "I'll provision what I need for the feature to work."
L5 engineer:  "I'll design this efficiently — let me estimate the cost at 10x scale."
L6 engineer:  "I own the cost efficiency of my domain. I review it quarterly.
               I know our cost per user, cost per request, and cost per feature.
               I treat a 30% MoM cost increase with the same urgency as a 30% error rate increase."
```

**The cost attribution problem:**

Most companies start with a single cloud account (or billing project). All costs appear as one line item. As the company grows, this becomes the problem:

```
AWS bill: $10M/month
Team A says: "Not us — we're efficient"
Team B says: "Not us — we ship carefully"
Team C says: "We use a lot of compute but it's justified"
Nobody is accountable. The bill keeps growing.
```

The solution is attribution — which we cover in Part 2.

---

## Part 2: Cloud Cost Attribution and Tagging

Attribution is the prerequisite for accountability. Before you can optimize cost, you must be able to answer: "Which team, service, feature, or customer is responsible for this cost?"

**The tagging strategy:**

Every cloud resource should carry 4-5 tags:

```
team:         "payments"           Who owns this resource?
service:      "payment-api"        Which service is this?
environment:  "production"         prod / staging / dev
cost-center:  "eng-backend"        Finance's budget code
feature:      "checkout-v2"        (optional) Which feature drove this resource?
```

**Tagging enforcement:**

Tags are only useful if they are consistently applied. Enforcement options:

```
AWS:
  Service Control Policies (SCPs): block resource creation without required tags
  AWS Config Rules: alert on untagged resources
  Tag Policy: define allowed values per tag (e.g., "environment" must be "prod/staging/dev")
  
GCP:
  Labels (equivalent to tags): applied to resources and billing export
  Organization Policy: enforce required labels
  
Terraform / IaC:
  Require tags in all resource modules
  Code review checklist: "Is this resource tagged?"
  
Tip: automate tagging. A Terraform module that automatically applies team and service
tags based on the module caller's context eliminates 80% of tagging debt.
```

**AWS Cost Explorer / GCP Billing by tags:**

Once resources are tagged, you can query costs by dimension:

```bash
# AWS CLI: cost by service tag for the last month
aws ce get-cost-and-usage \
  --time-period Start=2026-05-01,End=2026-06-01 \
  --granularity MONTHLY \
  --filter '{"Tags":{"Key":"service","Values":["payment-api"]}}' \
  --metrics BlendedCost

# GCP: billing export to BigQuery, then SQL
SELECT service.description, sum(cost) as total_cost
FROM `project.billing_export.gcp_billing_export_v1_*`
WHERE labels.key = 'service' AND labels.value = 'payment-api'
AND usage_start_time >= '2026-05-01'
GROUP BY service.description
ORDER BY total_cost DESC
```

**Showback vs. Chargeback:**

```
Showback:    Show each team their cost in a dashboard.
             No financial consequence for over-spending.
             Effect: awareness. Teams know what they cost.
             When to use: early-stage cost culture building.

Chargeback:  Deduct costs from team's engineering budget.
             Financial consequence for over-spending.
             Effect: strong incentive to optimize.
             When to use: mature orgs where teams have explicit budgets.
             Risk: teams game the system to avoid costs instead of genuinely optimizing.
```

**Per-feature costing (advanced):**

The most granular attribution: know what each product feature costs to operate.

```python
# Add a custom header to every request identifying the feature
@app.route('/api/checkout', methods=['POST'])
def checkout():
    with cost_tracking.track_feature("checkout_v2"):
        # ... business logic
        pass

# cost_tracking.py
import time
class cost_tracking:
    @contextmanager
    def track_feature(feature_name: str):
        start = time.time()
        yield
        duration = time.time() - start
        metrics.histogram("feature.request.duration", duration, 
                          tags={"feature": feature_name})
        # Track in a time-series DB → correlate with infra cost
```

This lets you answer: "How much does the checkout feature cost to operate per month?"

---

## Part 3: The Quarterly Cost Review Process

Cost optimization without a recurring review process is a one-time event, not a discipline. The quarterly review creates accountability and momentum.

**The cadence:**

```
Daily:      Automated cost anomaly alerts (see Part 11)
            Alert when daily spend > 2× the 7-day rolling average

Monthly:    15-minute review of top 10 cost categories
            Month-over-month change for each: is it growing faster than traffic?
            Identify any new large cost items

Quarterly:  30-60 minute per-service deep-dive
            Owner for each cost item
            Action item with deadline and projected savings

Annual:     Reserved Instance / Committed Use Discount (CUD) renewal review
            Vendor negotiations (AWS Enterprise Discount Program)
            Architecture review: is this service still the right design?
```

**The monthly cost review format:**

```markdown
## Monthly Cost Review — [Month Year]

### Top 10 Cost Categories
| Category | This Month | Last Month | ΔMoM | Growth vs. Traffic | Owner |
|----------|-----------|-----------|------|-------------------|-------|
| EC2 Compute | $450K | $400K | +12.5% | Traffic +8% → over-proportional | @alice |
| RDS | $180K | $175K | +2.9% | Traffic +8% → efficient | @bob |
| S3 | $95K | $82K | +15.8% | New log retention policy needed | @alice |
| Data Transfer | $75K | $70K | +7.1% | Proportional | @charlie |

### Anomalies This Month
- EC2 Compute grew 12.5% MoM while traffic grew 8% → investigate
- S3 grew 15.8% → no new features justify this, check log retention

### Action Items
- @alice: investigate EC2 compute growth — is it rightsizing opportunity?
  Due: [next month review date], Projected savings: $20K-$50K/month
- @alice: implement S3 lifecycle policy for logs older than 90 days
  Due: [2 weeks], Projected savings: $10K-$15K/month
```

**The quarterly deep-dive format:**

```markdown
## Quarterly Cost Deep-Dive — [Service Name] — [Quarter]

### Current Spend
Total: $[X]/month. YoY growth: [%]. Traffic growth YoY: [%].
Cost efficiency trend: [improving / stable / degrading].

### Cost Breakdown
| Component | Monthly Cost | % of total | Notes |
|-----------|-------------|-----------|-------|
| EC2 (m5.2xlarge × 20) | $14,400 | 45% | Auto-scaling; avg 35% CPU |
| RDS (db.r5.2xlarge) | $6,200 | 19% | Read replicas for reporting |
| ElastiCache | $2,800 | 9% | Redis cache for session data |
| Data transfer | $5,100 | 16% | Mostly cross-AZ (optimization opp) |
| Other | $3,500 | 11% | CloudWatch, KMS, etc. |
| **Total** | **$32,000** | **100%** | |

### Top Optimization Opportunities
1. EC2 rightsizing: avg 35% CPU on m5.2xlarge → try m5.xlarge
   Projected savings: $6,000/month. Risk: low (can revert immediately)
   
2. Reserved Instances: EC2 currently on-demand. Convert 80% to 1-year RIs
   Projected savings: $3,500/month. Risk: low (standard commitment)
   
3. Cross-AZ traffic: services in different AZs cause $5,100/month egress
   Fix: pin payment-api and order-service to same AZ
   Projected savings: $2,500/month. Risk: medium (AZ failure resilience tradeoff)
   
### Total Projected Savings: $12,000/month ($144,000/year)
### Owner: @alice
### Review Date: [next quarter]
```

---

## Part 4: Compute Rightsizing

The single largest source of waste in cloud infrastructure is over-provisioning. Engineers (reasonably) provision for peak load plus safety margin. But "peak plus 50%" often sits idle 90% of the time.

**The rightsizing workflow:**

```
1. MEASURE (2 weeks):
   Collect: CPU utilization (p50, p90, p99), memory utilization, network I/O
   Tool: AWS Compute Optimizer, CloudWatch, GCP Recommender, Datadog

2. IDENTIFY CANDIDATES:
   Flag instances where:
   - p90 CPU < 40% (over-provisioned)
   - p90 memory < 50% (over-provisioned on RAM)
   - Peak CPU < 70% (running below the utilization cliff — Chapter 117)
   
3. CALCULATE SAVINGS:
   m5.2xlarge ($0.384/hr): 8 vCPU, 32GB RAM — avg 35% CPU, 45% RAM
   → m5.xlarge ($0.192/hr): 4 vCPU, 16GB RAM — would run at 70% CPU, 90% RAM
   Savings: 50% per instance. At 20 instances: $3,840/month savings.
   
4. TEST (1 week):
   Migrate 1 instance to smaller type.
   Monitor: error rate, latency p99, CPU utilization under peak.
   
5. ROLL OUT:
   If test passes: migrate remaining instances over 2 weeks.
   Keep 20% as old instance type for 4 weeks (rollback buffer).
```

**AWS Compute Optimizer — automated recommendations:**

```bash
# Get rightsizing recommendations
aws compute-optimizer get-ec2-instance-recommendations \
  --filters "name=Finding,values=Overprovisioned"

# Output example:
{
  "instanceArn": "arn:aws:ec2:us-east-1:123456:instance/i-abc123",
  "currentInstanceType": "m5.2xlarge",
  "finding": "OVERPROVISIONED",
  "recommendationOptions": [
    {
      "instanceType": "m5.xlarge",
      "projectedUtilizationMetrics": [
        {"name": "CPU", "statistic": "MAXIMUM", "value": 68}
      ],
      "estimatedMonthlySavings": {"currency": "USD", "value": 192}
    }
  ]
}
```

**Kubernetes resource rightsizing:**

In Kubernetes, over-provisioning often happens at the pod level — resource requests are set too high, wasting allocatable capacity.

```yaml
# BEFORE: over-provisioned
resources:
  requests:
    cpu: "2000m"    # 2 vCPU requested
    memory: "4Gi"   # 4GB requested
  limits:
    cpu: "4000m"
    memory: "8Gi"
# Actual usage: avg 400m CPU, 800MB RAM
# Waste: 5x on CPU, 5x on RAM

# AFTER: rightsized (after monitoring actual usage for 2 weeks)
resources:
  requests:
    cpu: "500m"     # 0.5 vCPU — leaves headroom for spikes
    memory: "1Gi"   # 1GB — leaves headroom
  limits:
    cpu: "2000m"
    memory: "4Gi"
```

**Vertical Pod Autoscaler (VPA):** Kubernetes tool that automatically adjusts resource requests based on actual usage. Use with caution — it restarts pods to apply new resource limits.

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: payment-api-vpa
spec:
  targetRef:
    apiVersion: "apps/v1"
    kind: Deployment
    name: payment-api
  updatePolicy:
    updateMode: "Off"   # Recommend only, don't auto-apply (safer in production)
```

---

## Part 5: Reserved Instances, Spot, and Committed Use Discounts

Rightsizing is about using the right size. Purchasing strategy is about paying the right price for whatever size you use.

**On-demand vs. Reserved Instances vs. Spot:**

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                  INSTANCE PURCHASING STRATEGY                                  │
├──────────────────┬─────────────────────────────────────────────────────────────┤
│ On-Demand        │ Full price. No commitment. Use for unpredictable workloads. │
│                  │ AWS example: m5.xlarge = $0.192/hr                         │
├──────────────────┼─────────────────────────────────────────────────────────────┤
│ Reserved         │ 30-60% discount. 1-year or 3-year commitment.              │
│ Instances (RI)   │ AWS: m5.xlarge 1yr Standard RI = $0.120/hr (38% savings)  │
│                  │ Use for: steady baseline load (70-80% of normal usage)     │
│                  │ Risk: if you downsize, RIs are partially wasted            │
├──────────────────┼─────────────────────────────────────────────────────────────┤
│ Savings Plans    │ More flexible than RIs. Commit to $/hr across instance     │
│ (AWS)            │ family. 40-60% discount. Recommended over specific RIs.   │
├──────────────────┼─────────────────────────────────────────────────────────────┤
│ Spot Instances   │ 60-90% discount. Can be interrupted with 2-min notice.    │
│ (AWS) /          │ Use for: batch jobs, CI/CD runners, ML training,           │
│ Preemptible (GCP)│ stateless workers that can restart without data loss.      │
│                  │ NOT for: stateful services, databases, user-facing APIs    │
└──────────────────┴─────────────────────────────────────────────────────────────┘
```

**The RI purchasing strategy:**

```
Step 1: Establish baseline usage
        Look at last 3 months of on-demand usage.
        Identify the minimum instances you run 100% of the time.
        Example: 20 EC2 instances minimum; peaks at 35.
        
Step 2: Commit to 80% of baseline (not 100% — leave buffer for rightsizing)
        Buy RIs for 16 of the 20 baseline instances.
        
Step 3: On-demand covers the rest
        4 baseline + 15 peak instances → on-demand or spot.
        
Step 4: Review annually
        RI commitments should be renewed when the underlying instances
        still reflect your actual usage pattern.
        
Expected savings: 30-40% on the 16 committed instances.
At $0.192/hr on-demand → $0.120/hr reserved → $0.072/hr saved × 16 instances × 8760 hrs = $10,091/yr
```

**Spot Instances for batch jobs — code pattern:**

```python
# Worker that handles spot interruption gracefully
import boto3
import time
import requests

def check_spot_interruption():
    """AWS metadata endpoint notifies 2 minutes before interruption."""
    try:
        response = requests.get(
            "http://169.254.169.254/latest/meta-data/spot/instance-action",
            timeout=1
        )
        if response.status_code == 200:
            return True  # Interruption coming in 2 minutes
    except:
        pass
    return False

def process_batch_job(job_id: str, checkpoint_store):
    """Process with checkpoint support for spot interruption."""
    progress = checkpoint_store.load(job_id)
    
    for i, item in enumerate(items[progress.last_index:], start=progress.last_index):
        if i % 100 == 0 and check_spot_interruption():
            # Save progress and exit gracefully
            checkpoint_store.save(job_id, i)
            raise SpotInterruptionException(f"Checkpointed at index {i}")
        
        process_item(item)
        
    checkpoint_store.complete(job_id)
```

**GCP Committed Use Discounts (CUDs):**

Similar to AWS Savings Plans. Commit to a certain number of vCPUs and GB of memory for 1 or 3 years. Up to 57% discount on compute. 1-year CUD is typically 37% discount.

---

## Part 6: Storage Cost Optimization

Storage costs grow monotonically — data is rarely deleted, and teams add new logging without removing old logging. The result: storage costs increase 10-20% per month on unoptimized accounts.

**S3 / GCS storage class hierarchy:**

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                    OBJECT STORAGE COST TIERS (AWS S3, approximate)              │
├─────────────────────────────┬──────────────┬──────────────────────────────────────┤
│ Storage Class               │ Cost/GB/month│ Use for                             │
├─────────────────────────────┼──────────────┼──────────────────────────────────────┤
│ S3 Standard                 │ $0.023       │ Frequently accessed data             │
│                             │              │ (accessed daily/weekly)              │
├─────────────────────────────┼──────────────┼──────────────────────────────────────┤
│ S3 Standard-IA              │ $0.0125      │ Infrequently accessed                │
│ (Infrequent Access)         │ (46% cheaper)│ (accessed 1-2×/month)                │
│                             │              │ Retrieval fee: $0.01/GB              │
├─────────────────────────────┼──────────────┼──────────────────────────────────────┤
│ S3 Glacier Instant          │ $0.004       │ Archive, accessed < once/quarter     │
│ Retrieval                   │ (83% cheaper)│ Retrieval: milliseconds, $0.03/GB   │
├─────────────────────────────┼──────────────┼──────────────────────────────────────┤
│ S3 Glacier Flexible         │ $0.0036      │ Long-term archive, hours retrieval   │
│                             │ (84% cheaper)│ Retrieval time: minutes to hours     │
├─────────────────────────────┼──────────────┼──────────────────────────────────────┤
│ S3 Glacier Deep Archive     │ $0.00099     │ 7-10 year compliance retention       │
│                             │ (96% cheaper)│ Retrieval: 12 hours                  │
└─────────────────────────────┴──────────────┴──────────────────────────────────────┘
```

**Lifecycle policies — automate tier transitions:**

```json
{
  "Rules": [
    {
      "ID": "MoveLogsToGlacier",
      "Status": "Enabled",
      "Filter": {"Prefix": "logs/"},
      "Transitions": [
        {
          "Days": 30,
          "StorageClass": "STANDARD_IA"
        },
        {
          "Days": 90,
          "StorageClass": "GLACIER"
        }
      ],
      "Expiration": {
        "Days": 365
      }
    }
  ]
}
```

This single lifecycle policy:
- Moves logs to Standard-IA after 30 days (46% cheaper)
- Moves logs to Glacier after 90 days (84% cheaper)
- Deletes logs after 365 days

For a team storing 100TB of logs at Standard pricing: $2,300/month → $230/month for the Glacier portion. That's $24,840/year saved from 3 JSON lines.

**Compression — underutilized at massive scale:**

```python
# Before: storing JSON (verbose, uncompressed)
s3.put_object(
    Bucket='analytics-data',
    Key=f'events/{date}/{hour}.json',
    Body=json.dumps(events).encode()
)
# 1 billion events/day × 200 bytes/event = 200GB/day = 6TB/month
# Cost at Standard: $138/month

# After: Parquet with Snappy compression
import pyarrow as pa
import pyarrow.parquet as pq

table = pa.Table.from_pydict({k: [e[k] for e in events] for k in event_keys})
buffer = io.BytesIO()
pq.write_table(table, buffer, compression='snappy')
s3.put_object(Bucket='analytics-data', Key=f'events/{date}/{hour}.parquet', 
              Body=buffer.getvalue())
# Same 1B events: Parquet+Snappy = ~10-20GB/day = 0.5TB/month
# Cost at Standard: $11.5/month — 12× cheaper
# Bonus: columnar format is 100× faster for analytics queries
```

---

## Part 7: Data Transfer and Networking Costs

Networking costs are the most common "surprise" in cloud bills. They are confusing, multi-dimensional, and easy to ignore until the bill arrives.

**The egress pricing model:**

```
Data entering the cloud (ingress):    FREE
Data leaving the cloud (egress):      $0.08-$0.09/GB (AWS, GCP similar)
Data between AZs in the same region:  $0.01/GB each way ($0.02/GB round-trip)
Data between regions:                  $0.02-$0.08/GB
CDN to end users (CloudFront):        $0.0085-$0.02/GB (varies by region)
```

**The CDN math:**

For user-facing content, CDN is almost always cheaper than direct egress:

```
Direct egress (S3 → user):  $0.09/GB
CloudFront CDN:             $0.01/GB (typical average across tiers)
Savings:                    9× cheaper

100TB/month of video content:
  Direct S3 egress:  $9,000/month
  CloudFront:        $1,000/month
  Annual savings:    $96,000
```

CDN also reduces latency (edge caching), improves reliability (DDoS protection), and reduces origin load — the cost saving is almost free additional benefit.

**Cross-AZ traffic optimization:**

This is the most underappreciated egress cost. Services that call each other across Availability Zones pay $0.01/GB each way. For a high-throughput system:

```
payment-api (us-east-1a) → order-service (us-east-1b)
1 billion API calls/day × 2KB response = 2TB/day = 60TB/month
Cross-AZ egress: 60TB × $0.01 = $600/month → $7,200/year

Fix: Pin both services to the same AZ using pod affinity (Kubernetes):
```

```yaml
# Kubernetes pod affinity to co-locate services in the same AZ
spec:
  affinity:
    podAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchExpressions:
            - key: app
              operator: In
              values: ["order-service"]
          topologyKey: topology.kubernetes.io/zone
```

**Trade-off:** Co-locating services in one AZ improves cost but reduces AZ-fault tolerance. Make this decision explicitly, not accidentally.

**API response compression:**

```python
# FastAPI: enable gzip compression
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=1000)  # compress responses > 1KB

# Effect: JSON responses typically compress 60-80%
# 1TB/month JSON egress → 200-400GB after gzip → saves $50-65/month at $0.09/GB
# CPU cost to compress: < 1% — worth it at almost any scale
```

---

## Part 8: Database Cost Optimization

Databases are often the most expensive line item after compute. They're also the riskiest to optimize. Use Chapter 111 (Migrations and Safe Changes) patterns for all database cost work.

**Common database cost drivers:**

```
1. Instance oversizing:    db.r5.4xlarge for a workload that fits in db.r5.xlarge
                           r5.4xlarge: 16 vCPU, 128GB RAM — $2.24/hr
                           r5.xlarge:  4 vCPU, 32GB RAM  — $0.48/hr (4× cheaper)

2. Read replicas not used: Created "for redundancy" but no traffic routes there
                           Each read replica = same cost as primary

3. Multi-AZ not needed:    $5-6K/month for a dev/staging database with Multi-AZ
                           Dev databases don't need Multi-AZ

4. Missing cache:          Every cacheable query hitting the DB = overpaying for DB
                           instances when a $200/month Redis cluster could reduce
                           DB CPU by 30-50%

5. Slow queries:           A 10-second query uses 500× more CPU than a 20ms query
                           Fixing 5 slow queries can reduce DB CPU by 30%
                           → downsize instance by one tier → 50% cost reduction
```

**The caching ROI calculation:**

```
Scenario: high-traffic read-heavy API
DB reads: 100K req/sec, avg 5ms, RDS db.r5.2xlarge ($0.96/hr = $691/month)
Cache hit rate if Redis added: 80% (80K reads served from cache)
New DB reads: 20K req/sec — now fits in db.r5.xlarge ($0.24/hr = $173/month)

Redis ElastiCache cache.r6g.large: $0.166/hr = $120/month

Net savings: $691 - $173 - $120 = $398/month = $4,776/year
Plus: reduced latency (Redis ~0.5ms vs DB ~5ms) and higher throughput headroom
```

**Slow query identification and optimization:**

```sql
-- PostgreSQL: find the 10 most expensive queries
SELECT query,
       calls,
       mean_exec_time,
       total_exec_time,
       stddev_exec_time,
       rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;

-- AWS RDS Performance Insights: visual slow query analysis
-- Enable via Console → RDS → Performance Insights
```

**RDS storage optimization:**

```sql
-- Find tables with bloat (PostgreSQL)
SELECT
  relname,
  pg_size_pretty(pg_total_relation_size(oid)) as total_size,
  pg_size_pretty(pg_relation_size(oid)) as table_size,
  pg_size_pretty(pg_total_relation_size(oid) - pg_relation_size(oid)) as index_size,
  n_live_tup,
  n_dead_tup,
  ROUND(100 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 2) AS dead_tuple_ratio
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(oid) DESC
LIMIT 20;

-- If dead_tuple_ratio > 20%, VACUUM to reclaim space
VACUUM ANALYZE large_table_name;
```

**Archival to reduce hot storage:**

```sql
-- Move old orders to cold storage table
-- Step 1 (expand): create archive table
CREATE TABLE orders_archive (LIKE orders INCLUDING ALL);

-- Step 2: migrate data older than 1 year
INSERT INTO orders_archive
  SELECT * FROM orders WHERE created_at < NOW() - INTERVAL '1 year';

-- Step 3: verify counts match
SELECT COUNT(*) FROM orders WHERE created_at < NOW() - INTERVAL '1 year';
SELECT COUNT(*) FROM orders_archive;  -- should match

-- Step 4 (contract): delete from hot table
DELETE FROM orders WHERE created_at < NOW() - INTERVAL '1 year';

-- Then use pg_dump to export orders_archive to S3/Glacier
-- Drop orders_archive from the hot database
```

Archiving 80% of data from a 2TB database to S3 Glacier: from $200/month to $40/month.

---

## Part 9: Serverless and Container Cost Optimization

Serverless (Lambda, Cloud Functions) and containers (Fargate, Cloud Run) have different cost models than traditional EC2. Misunderstanding the model leads to surprising bills.

**Lambda cost model:**

```
AWS Lambda pricing:
  Invocations:    $0.20 per 1 million requests
  Duration:       $0.0000166667 per GB-second
  
Example: 100M invocations/month, avg 100ms, 512MB memory
  Requests:  100M × $0.20/1M = $20
  Duration:  100M × 0.1s × 0.5GB × $0.0000166667 = $83.33
  Total:     ~$103/month
  
Same traffic on EC2 (1000 req/sec, t3.medium):
  1× t3.medium: $0.0416/hr = $30/month
  BUT: Lambda scales from 0 to 1M concurrent → no idle cost
  EC2 must always be running → minimum 1 instance even at zero traffic
```

**Lambda cost optimization:**

```python
# 1. Right-size memory (memory affects both speed and cost)
# Lambda cost scales with memory; but more memory = faster execution (less duration billed)
# Optimal: run Lambda Power Tuning (open source) to find the sweet spot

# 2. Minimize cold starts (cold starts extend duration)
# Keep Lambda warm with provisioned concurrency for latency-sensitive functions
aws lambda put-provisioned-concurrency-config \
  --function-name payment-processor \
  --qualifier prod \
  --provisioned-concurrent-executions 10
# Cost: $0.000004646 per provisioned-concurrency-second (always running)

# 3. Batch invocations when possible
# Instead of 1 Lambda per SQS message, process 10 messages per Lambda invocation
# SQS batch size: 10 → 10× fewer invocations → 10× lower invocation cost

# 4. Avoid Lambda for long-running tasks
# Lambda max timeout: 15 minutes
# For jobs > 15 min, use ECS Fargate or EC2 Spot
# Lambda billed per 1ms → a 15-minute Lambda is expensive vs. a batch job
```

**Fargate / Cloud Run cost optimization:**

Container-on-demand pricing (Fargate, Cloud Run) is similar to Lambda but charges for running containers rather than invocations:

```
AWS Fargate pricing:
  vCPU: $0.04048 per vCPU-hour
  Memory: $0.004445 per GB-hour
  
0.5 vCPU, 1GB RAM container running 24/7:
  vCPU: 0.5 × $0.04048 × 720 hrs = $14.57/month
  Memory: 1 × $0.004445 × 720 hrs = $3.20/month
  Total: $17.77/month per container

Scale to zero when no traffic:
  Cloud Run: automatically scales to 0 containers with no traffic
             (no traffic → no cost; 30-second cold start on first request)
  
  Savings: if traffic is only present 8 hours/day:
           With scale-to-zero: 8/24 × $17.77 = $5.92/month (67% savings)
```

**The serverless vs. containers vs. EC2 decision matrix:**

```
┌──────────────────────────────────────────────────────────────────────────────┐
│            COMPUTE MODEL COST COMPARISON                                    │
├─────────────────────────┬────────────────────────────────────────────────────┤
│ Model                   │ Best for                                           │
├─────────────────────────┼────────────────────────────────────────────────────┤
│ Lambda / Cloud Function │ Event-driven, variable traffic, short duration    │
│                         │ (<15 min), don't need warm-up                      │
│                         │ Cost: excellent at low/bursty traffic               │
│                         │       expensive at high sustained traffic           │
├─────────────────────────┼────────────────────────────────────────────────────┤
│ Fargate / Cloud Run     │ Variable traffic, don't want to manage servers     │
│                         │ Need more memory/CPU than Lambda allows            │
│                         │ Cost: 2-4× Lambda per unit of compute              │
│                         │       but no management overhead                   │
├─────────────────────────┼────────────────────────────────────────────────────┤
│ EC2 (with HPA)          │ Sustained high traffic, predictable patterns       │
│                         │ Cost: cheapest at sustained workloads              │
│                         │       with RIs; most management overhead           │
├─────────────────────────┼────────────────────────────────────────────────────┤
│ EC2 Spot / Preemptible  │ Batch jobs, ML training, stateless workers         │
│                         │ Cost: cheapest option (60-90% off on-demand)       │
│                         │       requires interruption handling               │
└─────────────────────────┴────────────────────────────────────────────────────┘
```

---

## Part 10: Data Pipeline and Analytics Cost Optimization

For companies with significant data infrastructure (Spark jobs, Snowflake, BigQuery, Kinesis/Pub/Sub), analytics costs often rival production compute.

**Snowflake / BigQuery query cost optimization:**

```sql
-- BigQuery: avoid SELECT * (scans all columns; charges per byte scanned)
-- ❌ EXPENSIVE: scans entire table
SELECT * FROM `project.dataset.events`
WHERE date = '2026-06-25';

-- ✅ CHEAP: only scans the columns you need
SELECT user_id, event_type, timestamp
FROM `project.dataset.events`
WHERE date = '2026-06-25';

-- Use partition pruning (BigQuery charges by bytes scanned)
-- Partition your table by date → queries with WHERE date = '...' only scan that partition

-- Materialize expensive queries as tables (run once nightly, query the table all day)
CREATE OR REPLACE TABLE `project.dataset.daily_active_users`
PARTITION BY date AS
SELECT
  DATE(timestamp) as date,
  COUNT(DISTINCT user_id) as dau
FROM `project.dataset.events`
WHERE DATE(timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY 1;
```

**Spark / EMR cost optimization:**

```python
# 1. Use Spot Instances for all Spark jobs (70% savings)
# AWS EMR: set instance fleets with Spot capacity
# GCP Dataproc: use preemptible workers for task nodes

# 2. Cache DataFrames only when used multiple times
# Every cache = memory cost; uncached read = recomputation
df.cache()  # only if you actually use df 2+ times

# 3. Prefer narrow transformations to wide (reduce shuffles)
# Shuffles = network traffic = cross-node data transfer cost + latency
# Bad: multiple groupBys in a row (multiple shuffles)
# Good: combine into a single groupBy

# 4. Use columnar formats (Parquet > CSV/JSON for analytics)
df.write.parquet("s3://bucket/path/")  # not df.write.csv()
# Parquet: 10× smaller, 100× faster for column scans

# 5. Right-size your Spark cluster per job
# Don't use a 100-node cluster for a job that takes 5 minutes on 20 nodes
# EMR autoscaling: scale task nodes based on YARN queue depth
```

**Kinesis / Pub/Sub cost optimization:**

```
AWS Kinesis Data Streams pricing:
  $0.015/shard-hour (1 shard = 1MB/s ingest, 2MB/s egress)
  Extended data retention ($0.023/GB for >24 hours)
  
  Common waste: provisioned too many shards
  100 shards at 5% utilization: paying for 100 × $0.015 × 720 = $1,080/month
  Should be: 5 shards (95% utilization is target for Kinesis)
  Savings: $972/month
  
  Use Enhanced Fan-Out for multiple consumers (instead of multiple shards):
  $0.015/shard-hr + $0.013/consumer-shard-hr
  (cheaper than provisioning shards for each consumer's throughput)
```

---

## Part 11: Cost Anomaly Detection

A cost anomaly is a sudden unexpected increase in cloud spend. Without automated detection, anomalies are discovered when the monthly bill arrives — often 2-4 weeks after the root cause.

**AWS Cost Anomaly Detection:**

AWS has a native anomaly detection service (Cost Anomaly Detection) that uses ML to identify anomalous spend patterns.

```bash
# Create a cost anomaly monitor
aws ce create-anomaly-monitor \
  --anomaly-monitor '{
    "MonitorName": "ServiceMonitor",
    "MonitorType": "DIMENSIONAL",
    "MonitorDimension": "SERVICE"
  }'

# Create an alert subscription
aws ce create-anomaly-subscription \
  --anomaly-subscription '{
    "SubscriptionName": "AlertOnAnomalies",
    "MonitorArnList": ["arn:aws:ce::123456789012:anomalymonitor/monitor-id"],
    "Subscribers": [{
      "Address": "arn:aws:sns:us-east-1:123456789012:CostAlerts",
      "Type": "SNS"
    }],
    "Threshold": 100,
    "Frequency": "DAILY"
  }'
```

This sends an alert when daily spend exceeds the anomaly threshold by $100. Catches runaway costs in hours, not weeks.

**Custom anomaly detection:**

For more control, build your own anomaly detector:

```python
# Prometheus/CloudWatch metrics → custom anomaly alert
# Check: if today's spend > 2× the 7-day rolling average → alert

import boto3
from datetime import datetime, timedelta

def check_cost_anomaly():
    ce = boto3.client('ce', region_name='us-east-1')
    
    # Get last 8 days of daily spend
    today = datetime.now().date()
    eight_days_ago = today - timedelta(days=8)
    
    response = ce.get_cost_and_usage(
        TimePeriod={
            'Start': eight_days_ago.isoformat(),
            'End': today.isoformat()
        },
        Granularity='DAILY',
        Metrics=['BlendedCost']
    )
    
    costs = [float(day['Total']['BlendedCost']['Amount']) 
             for day in response['ResultsByTime']]
    
    yesterday_cost = costs[-1]
    seven_day_avg = sum(costs[:-1]) / 7
    
    if yesterday_cost > seven_day_avg * 2:
        alert(f"Cost anomaly: yesterday ${yesterday_cost:.0f} vs 7-day avg ${seven_day_avg:.0f}")
        
    return yesterday_cost, seven_day_avg
```

**Common causes of cost anomalies:**

```
1. Misconfigured auto-scaling:   HPA triggers a scale-out that doesn't scale back in
                                  (missing scale-in policy or cooldown period)

2. Test data in production:       Someone ran a load test in prod or left 
                                  test resources running

3. Data pipeline loop:            ETL job goes into an infinite loop, 
                                  reprocessing the same data indefinitely

4. Missing lifecycle policy:      New S3 bucket created without lifecycle rules
                                  → data accumulates indefinitely

5. Accidental large query:        SELECT * on a 100TB BigQuery table 
                                  → $500 in 10 seconds

6. Log verbosity increase:        Someone enabled DEBUG logging in production
                                  → 10× log volume → 10× storage + ingestion cost

7. DDoS / traffic spike:          Legitimate spike (viral event) or malicious 
                                  attack driving Lambda/Fargate costs up
```

**The cost anomaly runbook:**

```markdown
## Cost Anomaly Response Runbook

### Alert: Daily spend > 2× 7-day average

Step 1: Identify the service (use Cost Explorer or tag-based breakdown)
        → Which tag/service drives the anomaly?

Step 2: Identify the resource type
        → Is it compute? Data transfer? Storage? Lambda invocations?

Step 3: Look for recent changes in that service
        → git log --since="48 hours ago" -- [service directory]
        → Was there a recent deploy, config change, or load test?

Step 4: Containment
        → If a data pipeline loop: stop the pipeline immediately
        → If auto-scaling issue: manually set max replicas lower
        → If a load test: stop the test, clean up resources

Step 5: Root cause analysis
        → Add to cost anomaly postmortem doc
        → Add preventive controls (cost budget alerts, lifecycle policies)

Escalate if: spend > $10K above normal and root cause not identified within 1 hour
```

---

## Part 12: Building a Cost Culture

Technical optimizations without organizational culture revert over time. New engineers over-provision. New features add costs without accountability. The optimizations you make today are eroded by next year's feature work.

**What a cost culture looks like:**

```
1. VISIBILITY:       Every team has a cost dashboard showing their spend,
                     month-over-month trend, and cost per request/user.
                     
2. ACCOUNTABILITY:   Every cost item has a named owner.
                     "Unowned" resources are automatically flagged.
                     
3. DESIGN REVIEWS:   Every design review includes a cost estimate:
                     "At 10x current traffic, this design costs $X/month."
                     
4. CELEBRATION:      $500K in annual savings gets announced at the all-hands.
                     Cost optimization is treated as a real engineering achievement.
                     
5. CHAMPIONS:        One engineer per team is designated as the "cost champion."
                     They own the quarterly cost review and the savings roadmap.
                     
6. TOOLING:          Engineers can self-serve cost attribution.
                     No tickets to finance required to see "what does my service cost?"
```

**Cost in design reviews — the right question:**

```
During design review, the reviewer asks:

"What does this cost to operate at our current scale? 
 What does it cost at 10× scale?
 What's the cost per request? Per user per month?
 Is there a cheaper design that meets the same requirements?"

Good answer: "At current scale (~5K req/sec), it costs $8,000/month for compute.
             The main cost driver is the Elasticsearch cluster for search.
             At 10× scale, we'd need to shard the cluster — estimated $60K/month.
             Alternative: use CloudSearch (managed) at $40K/month at 10× but with
             less flexibility. We recommend Elasticsearch for now with a shard
             strategy documented for when we hit 3× current scale."

Bad answer: "We'll figure out cost later. The important thing is it works."
```

**Perverse incentives to avoid:**

```
❌ Punish teams for high costs → teams will hide costs, not fix them
❌ Compare teams by absolute cost → teams with high-revenue products should 
   cost more; compare cost per unit of value (cost per active user, cost per $1 revenue)
❌ Only reward cost reduction → teams will refuse to add features 
   that add cost even when ROI is clearly positive
✅ Reward cost efficiency: cost per unit of value, not cost absolute
✅ Reward identifying waste: finding waste is the first step to fixing it
✅ Celebrate both: cost savings AND cost-efficient new features
```

**Making costs visible — the minimum viable dashboard:**

```
For each team/service, show monthly:
  - Total cost this month ($)
  - Cost last month ($) and MoM change (%)
  - Cost per 1000 requests ($ / 1K req) — efficiency metric
  - Cost per active user ($ / MAU) — business value metric
  - Top 3 cost drivers (service, amount, %)
  - Anomalies this month (days where cost > 2× rolling average)
```

Tools: AWS Cost Explorer + QuickSight, GCP Looker Studio, or Grafana with cloud billing exporters.

---

## Part 13: L5 vs L6 Calibration on Cost Ownership

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│            COST OWNERSHIP: SENIORITY CALIBRATION                                │
├──────────────┬────────────────────────────────────┬──────────────────────────────┤
│ SIGNAL       │ L5                                 │ L6                           │
├──────────────┼────────────────────────────────────┼──────────────────────────────┤
│ Design       │ Considers cost at design time,      │ Includes cost estimate and   │
│ reviews      │ raises concerns if obvious waste    │ cost-at-10x-scale in every   │
│              │                                    │ design doc; blocks designs   │
│              │                                    │ with unacceptably high cost  │
├──────────────┼────────────────────────────────────┼──────────────────────────────┤
│ Monthly      │ Checks costs when asked             │ Owns the monthly review,     │
│ review       │                                    │ has an action item for every │
│              │                                    │ anomaly                       │
├──────────────┼────────────────────────────────────┼──────────────────────────────┤
│ Attribution  │ Knows roughly what their service    │ Knows cost per request, cost │
│              │ costs; cannot attribute to features │ per feature, cost per user;  │
│              │                                    │ has tagging enforced          │
├──────────────┼────────────────────────────────────┼──────────────────────────────┤
│ Cost         │ Executes cost savings when          │ Drives the cost savings      │
│ optimization │ assigned                            │ roadmap; estimates ROI;      │
│              │                                    │ prioritizes savings against   │
│              │                                    │ feature work                 │
├──────────────┼────────────────────────────────────┼──────────────────────────────┤
│ Anomalies    │ Investigates when alerted           │ Has set up automated anomaly  │
│              │                                    │ alerts; has a runbook;       │
│              │                                    │ finds root cause in <1 hour  │
└──────────────┴────────────────────────────────────┴──────────────────────────────┘
```

The L6 signal: cost is treated as a production metric. A 30% cost spike triggers the same urgency as a 30% error rate spike.

---

## Part 14: War Stories — Cost Optimization in Practice

**War Story 1: The Misconfigured Auto-Scaler**

A team at a mid-sized SaaS company deployed a new feature with aggressive auto-scaling configured. They set the scale-out policy but forgot the scale-in policy. When traffic spiked for a product launch, the cluster auto-scaled to 500 instances. Traffic normalized 4 hours later. The instances did not scale back in.

Nobody noticed for 3 weeks — the costs appeared in the monthly bill. By then, the team had paid for 500 instances × 24/7 × 3 weeks = 252,000 instance-hours beyond what was needed.

Cost: approximately $48,000 over the 3 weeks.

Fix: added scale-in policies, added a daily "instances > 150% of expected" alert, added cost anomaly detection.

**Lesson:** Scale-out without scale-in is a silent money drain. Auto-scaling always needs both policies.

---

**War Story 2: The Debug Logging Incident**

A senior engineer at a fintech company was debugging a production issue. They temporarily increased the log verbosity to DEBUG to capture more detail. They fixed the issue in 2 hours and deployed the fix — but forgot to revert the log level.

The service was producing 50× its normal log volume for 4 days. CloudWatch Logs ingestion: $0.50/GB. The service normally produced 2GB/day → 100GB/day at DEBUG. 400GB × $0.50 = $200/day → $800 over 4 days.

Plus: the CloudWatch storage for all those logs: $0.03/GB × 400GB = $12/day.

Total: ~$1,000 in unexpected costs from 4 days of debug logging.

Fix: added log volume anomaly detection; added "DEBUG logging is not allowed in production for > 24 hours" to the runbook; log level is now set via feature flag that auto-expires after 24 hours.

**Lesson:** Every operational change that increases data volume is a cost change. Debug logging in production needs time limits.

---

**War Story 3: The Forgotten Test Cluster**

A machine learning team spun up a GPU cluster (p3.16xlarge instances at $24.48/hour each) for a training run. They used 20 instances for a 3-day training job. The job finished, the model was saved, and the team moved on.

The cluster was not terminated.

The monthly bill arrived 3 weeks later with an unexpected $100K+ line item. The cluster had been running for 4 weeks at 20 × $24.48/hr × 720 hrs = $352,000. A junior engineer had launched the cluster without understanding how to terminate it. A senior engineer had reviewed the training job output but didn't check resource cleanup.

Fix: all GPU clusters now have a maximum lifetime tag (7 days). An automated job terminates any cluster past its lifetime. Engineers must explicitly request an extension. The team added a weekly "orphaned resources" audit.

**Lesson:** GPU instances are expensive enough that even one forgotten cluster is a career event. Automated resource lifecycle management is not optional for expensive instance types.

---

**War Story 4: Dropbox's $75M Storage Savings**

Dropbox publicly documented how they reduced storage costs through custom compression. They built Diskotech, a custom block storage system that replaced traditional disks with custom compression and deduplication algorithms tuned specifically for the kinds of files Dropbox stores (mostly PDFs, Word docs, images).

The result: $75M/year in storage cost savings, and improved performance due to smaller files on disk.

The lesson: at very large scale (exabytes), commodity cloud storage optimization techniques hit diminishing returns. Custom infrastructure becomes economically justified. This is not a lesson to apply at $10M/month cloud spend — but at $100M+/year storage spend, custom compression is worth engineering.

---

## Part 15: Cost Optimization Without Breaking Production

The most dangerous part of cost optimization is making changes to production systems that have real users depending on them. A $5K/month savings is not worth a production outage.

**The risk ladder for cost changes:**

```
LOW RISK (can do immediately):
  - Lifecycle policies on new or clearly-not-accessed data
  - Reserved Instances / CUDs (no production impact, just payment commitment)
  - Right-size dev/staging instances (not production)
  - Delete orphaned resources (confirm they are truly unused first)
  - Add CDN in front of existing origin (additive, can revert)
  - Enable compression in API responses (verify clients accept it first)

MEDIUM RISK (test thoroughly, roll back plan required):
  - Right-size production instances (test on 1 instance first, monitor closely)
  - Switch to Spot Instances for stateless services (handle interruptions first)
  - Storage tier transitions for production data (verify retrieval still works)
  - Database instance downsizing (requires load test at new size first)
  - Co-locate services in one AZ (trade-off with AZ fault tolerance)

HIGH RISK (treat like a production migration):
  - Replace one database technology with another cheaper one
  - Change data storage format (JSON → Parquet) for data other services read
  - Terminate a service and migrate traffic to a cheaper alternative
  - Change Kafka partition count or retention policy
  - Compress existing data in-place (data loss risk if done incorrectly)
```

Use Expand-and-Contract patterns (Chapter 116) for any change that touches data. Use feature flags and gradual rollout for any change that touches production traffic.

---

## Part 16: FinOps — The Organizational Framework

FinOps (Financial Operations) is the practice of bringing financial accountability to cloud spending. It's the organizational framework that makes cost optimization sustainable.

**The three FinOps phases:**

```
Phase 1: INFORM (visibility)
  → Everyone knows what things cost
  → Tag all resources, build cost dashboards, showback to teams

Phase 2: OPTIMIZE (efficiency)
  → Teams act on the visibility to reduce waste
  → Rightsizing, Reserved Instances, lifecycle policies
  → Regular cost reviews, anomaly alerts

Phase 3: OPERATE (continuous improvement)
  → Cost optimization becomes a continuous engineering practice
  → Cost targets in OKRs, cost champions per team
  → Cost efficiency in design reviews and feature planning
```

At companies with $50M+/year cloud spend, a dedicated FinOps team is justified (2-5 people). They negotiate Enterprise Discount Programs (10-20% additional discount), manage the RI portfolio, and drive cross-team cost reviews. At smaller companies, the L6 engineer owns this function for their domain.

---

## Part 17: Pre-Interview Drill — 12 Questions

**1.** Why is cost optimization an engineering responsibility?
> *Engineers make architectural decisions that determine cost. Finance sees the bill; engineers control the levers.*

**2.** How would you attribute cloud costs to individual teams and features?
> *Resource tagging: team + service + environment + feature. Query by tag using Cost Explorer or BigQuery billing export.*

**3.** What is the difference between showback and chargeback?
> *Showback: show costs, no financial consequence. Chargeback: deduct from team budgets. Showback builds awareness; chargeback creates stronger incentives.*

**4.** How do Reserved Instances / Savings Plans work?
> *Commit to using specific compute for 1-3 years in exchange for 30-60% discount. Best for baseline load.*

**5.** When are Spot/preemptible instances appropriate?
> *Batch jobs, ML training, CI/CD runners, stateless workers that can restart. NOT for stateful services or user-facing APIs.*

**6.** What is the S3 storage tier hierarchy?
> *Standard → Standard-IA (46% cheaper) → Glacier Instant (83% cheaper) → Glacier Flexible (84%) → Deep Archive (96%). Use lifecycle policies to auto-transition.*

**7.** Why is cross-AZ data transfer an underappreciated cost?
> *$0.01/GB each way between AZs. At 60TB/month: $600/month just from two services in different AZs.*

**8.** How does CDN compare to direct S3 egress?
> *Direct egress: $0.09/GB. CloudFront: $0.01/GB. ~9× cheaper. Also reduces latency and origin load.*

**9.** How do you detect cost anomalies before the monthly bill?
> *AWS Cost Anomaly Detection or custom: alert when daily spend > 2× 7-day rolling average.*

**10.** What is the "cost per request" metric and why does it matter?
> *Efficiency metric. Absolute cost grows with scale; cost-per-request reveals whether efficiency is improving or degrading.*

**11.** How do you include cost in a design review?
> *Estimate cost at current scale and 10×. Name top cost drivers. Compare alternatives.*

**12.** What's your quarterly cost review process?
> *Monthly: top 10 categories, MoM trends. Quarterly: per-service deep-dive, optimization roadmap with ROI estimates, owners, deadlines.*

---

## Key Takeaways

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│               KEY TAKEAWAYS: COST OPTIMIZATION DISCIPLINE                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  1. OWNERSHIP      Cost is an engineering responsibility at L6.                │
│                    Treat cost spikes like error rate spikes.                   │
│                                                                                 │
│  2. ATTRIBUTION    Tag everything: team + service + env + feature.             │
│                    Without attribution, no accountability.                     │
│                                                                                 │
│  3. BIGGEST LEVERS Rightsizing + RIs (30-60%), S3 lifecycle (60-80%),         │
│                    CDN (80-90% egress), Spot for batch (60-90%).               │
│                                                                                 │
│  4. PROCESS        Monthly top-10 review + quarterly deep-dive.               │
│                    Anomaly detection: daily spend > 2× 7-day average.         │
│                                                                                 │
│  5. CULTURE        Make costs visible. Name owners. Celebrate savings.        │
│                    Include cost estimate in every design review.               │
│                                                                                 │
│  6. SAFETY         Cost optimization can break production.                    │
│                    Use the risk ladder. Test on 1 instance first.             │
│                                                                                 │
│  7. ROI            $5M/year in savings = 8-10 additional engineers.           │
│                    Cost efficiency is a competitive advantage.                 │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### Brainstorming Questions — Part 1: Why Cost Is an Engineering Responsibility

1. A product manager says "don't worry about cost, just ship the feature." When is this the right call? When is it dangerous? What's the threshold where you push back?
2. Your team has never tracked infrastructure cost by service. What's the first thing you'd change? What data would you collect, and how long before it produces useful insights?
3. Intern approach to cost: "it's someone else's job." L5 approach: "I care about the cost of my service." L6 approach: what? What does L6 cost thinking look like that L5 doesn't have?

### Brainstorming Questions — Parts 2–3: Attribution and Quarterly Review

1. You have 50 microservices sharing one AWS account. No cost attribution. How do you retrofit tagging without breaking anything? What's the prioritization (tag the expensive stuff first)?
2. What's the right cadence for a cost review? Weekly? Monthly? Quarterly? What triggers an ad-hoc review outside the regular cadence?
3. In a quarterly cost review, you find that one team's service costs 10x more than the others. What do you say in the meeting? What's the follow-up?

### Brainstorming Questions — Parts 4–6: Compute, Reserved, Storage

1. You're right-sizing instances and reduce a service from 32-core to 16-core instances. Three weeks later, a P1 incident occurs during a traffic spike. How do you decide whether the right-sizing caused the incident?
2. Reserved Instances commit you to 1 or 3 years. Your startup might pivot in 6 months. How do you weigh commitment risk against cost savings?
3. Your S3 storage is growing 10% per month. The data lifecycle policy was "keep everything forever." What's the conversation to have with the business about retention? Who owns the decision?

### Brainstorming Questions — Parts 7–10: Network, Database, Serverless, Pipelines

1. Cross-region data transfer is 10x more expensive than intra-region. Your service makes 100K cross-region calls/day. What architectural changes reduce this, and what's the cost of each change in engineering time?
2. A serverless function runs 1M times/day at 500ms each. A container running 24/7 would be cheaper at that scale. What's the crossover point? How do you calculate it?
3. Your data pipeline costs $50K/month. The team wants to reduce it by 30%. What's the first place you look? What's the one lever that typically has the highest impact?

---

## Exercises

**Exercise 1 — Tag audit.** Audit the tagging of your team's cloud resources. What percentage are correctly tagged (team, service, environment)? For any untagged resources: what are they, and why aren't they tagged? Create a one-sprint plan to reach 100% tagging.

**Exercise 2 — Cost dashboard.** Build a cost dashboard for your team's services: cost per service, cost per environment (prod vs. dev), cost trend over the last 3 months, and cost per request for the top 3 services. What's the most surprising number?

**Exercise 3 — Spot instance migration.** Identify one workload in your system that could use spot/preemptible instances (batch jobs, ML training, dev environments). Design the migration: checkpoint strategy, requeue on interruption, and expected savings.

**Exercise 4 — Storage lifecycle policy.** Find your team's largest S3 bucket or object store. What's the access pattern (use access logs or metadata)? Design a lifecycle policy: Standard → Standard-IA → Glacier. Calculate cost before and after.

**Exercise 5 — Database query cost analysis.** Find the top 5 most expensive database queries by CPU time or I/O. For each: is this query necessary? Can it be optimized (index, query rewrite)? Can the result be cached?

**Exercise 6 — Serverless vs. container break-even.** For any function your team runs: calculate the monthly cost on serverless vs. a right-sized container. At what invocation rate does the container become cheaper?

---

## Homework

**This week:**
1. Open your cloud console and find the top 5 cost categories for your service
2. Check: are all resources tagged with team, service, environment?
3. Look at p90 CPU utilization for your EC2/container instances

**This month:**
4. Implement lifecycle policies for any log buckets retaining data > 90 days
5. Identify over-provisioned instances (p90 CPU < 40%) and right-size one
6. Set up a cost anomaly alert (AWS Cost Anomaly Detection or custom)

**Longer term:**
7. Run a quarterly cost review for your service
8. Add a cost estimate to your next design doc
9. Calculate and track cost per 1000 requests monthly

---

## Vocabulary Quick Reference

| Term | One-line definition |
|------|---------------------|
| Cost attribution | Assigning cloud costs to teams, services, or features using tags |
| Reserved Instance (RI) | AWS pricing commitment for 1-3 years for 30-60% discount |
| Savings Plan | AWS flexible commitment for 40-60% discount across instance families |
| Spot Instance | AWS spare capacity at 60-90% discount; can be interrupted with 2-min notice |
| Committed Use Discount (CUD) | GCP equivalent of Savings Plans |
| Showback | Showing teams their costs without financial consequence |
| Chargeback | Deducting cloud costs from team engineering budgets |
| Rightsizing | Choosing instance sizes matching actual CPU/memory needs |
| S3 Glacier | Cold storage tier; 84% cheaper than Standard; hours to retrieve |
| Data egress | Data leaving the cloud to the internet; billed per GB |
| Cross-AZ traffic | Data transfer between AZs within a region; $0.01/GB each way |
| CDN | Content Delivery Network; caches at edge; 8-9× cheaper than direct egress |
| Cost anomaly | Sudden unexpected spike in cloud spend vs. recent baseline |
| FinOps | Practice of bringing financial accountability to cloud spending |
| Lifecycle policy | Automated rule to move S3 objects to cheaper tiers or delete them |

---

## Companion Resources

- **AWS Cost Management** documentation — Cost Explorer, Compute Optimizer, Cost Anomaly Detection
- **GCP Cost Management** — Billing export to BigQuery, Recommender
- **"Cloud FinOps"** — J.R. Storment & Mike Fuller (the definitive book on the discipline)
- **FinOps Foundation** — finops.org (framework, certifications, best practices)
- **AWS Pricing Calculator** — estimate costs before architecting
- **Infracost** — open-source tool that adds cost estimates to Terraform plans (cost as code)

---

## Part 18: Cost Optimization in System Design Interviews

Cost efficiency appears in system design interviews at L6. Interviewers at Google, Meta, and Amazon explicitly evaluate whether you consider cost in your designs. Here's what "good" looks like:

**The interviewer is asking (implicitly):**
1. Do you know that distributed systems have real operating costs?
2. Can you make cost-aware trade-offs without being asked?
3. Can you estimate rough costs and compare alternatives?

**L5 response in a design interview:**
"I'll use a cache to reduce database load and improve latency."

**L6 response in a design interview:**
"I'll add a Redis cache with a 95% target hit rate. At our estimated 10K reads/sec, that's 9,500 cache hits/sec served from ElastiCache ($0.50/hr for cache.r6g.large) vs. 500 actual DB queries/sec — down from 10K. This lets us downsize the RDS instance by 2 tiers, saving approximately $400/month. The cache adds $120/month (ElastiCache) for a net savings of $280/month and a 5-10× latency improvement on cache hits. Trade-off: cache invalidation complexity and stale reads (acceptable for our use case where data is read-heavy and slightly stale reads are tolerable)."

The L6 answer adds:
- Quantified hit rate assumption
- Dollar amounts for the components
- Net savings calculation
- Acknowledgment of the trade-off

You don't need to be exact — back-of-envelope estimates are fine. The signal is that you think about cost as part of the design, not as an afterthought.

**Common cost trade-offs to mention in design interviews:**

```
CDN vs. serving from origin:
  "We'll serve static assets via CloudFront. At 100TB/month of static content,
   CDN costs $1,000/month vs. $9,000/month for direct S3 egress. The 9× cost
   saving is straightforward since static content is highly cacheable."

Multi-region vs. single-region:
  "Running active-active across 3 regions costs roughly 3× the single-region cost.
   For our use case with 99.99% SLA requirements, this is justified. If the SLA
   were 99.9%, I'd use single-region with read replicas for ~1.5× the cost."

NoSQL vs. RDS:
  "DynamoDB's on-demand pricing is approximately $1.25/million writes + $0.25/million reads.
   At our expected 1M writes/day and 10M reads/day: ~$37.50/day = $1,125/month.
   Compared to RDS Aurora at $800-1,200/month for the instance.
   At this scale, cost is roughly comparable — I'd choose based on query pattern
   requirements, not cost."
```

---

## Part 19: The Cost Efficiency Metrics You Should Track

Just as a service tracks p99 latency and error rate as health signals, it should track cost efficiency metrics. These are the numbers that tell you whether your system is getting cheaper or more expensive per unit of value over time.

**The core cost efficiency metrics:**

```
Cost per 1,000 requests:
  Formula:   monthly_cost / (monthly_request_count / 1000)
  Healthy:   declining or stable over time
  Warning:   increasing faster than can be explained by features added
  
  Example:   $32,000/month service, 500M requests/month
             = $32,000 / (500M / 1000) = $0.064 per 1,000 requests

Cost per monthly active user (MAU):
  Formula:   monthly_cost / MAU
  Healthy:   below your revenue per MAU (you need margin)
  Warning:   approaching your monetization level
  
  Example:   $32,000/month, 100K MAU
             = $0.32/user/month
             If the feature monetizes at $1/user/month → 68% margin on infra

Cost per transaction (for payments, commerce, etc.):
  Formula:   infra_cost_for_service / monthly_transaction_count
  
  Example:   $5,000/month payment service, 2M transactions/month
             = $0.0025/transaction → well within acceptable range

Unit cost trend (most important):
  Track cost per unit monthly for 12 months.
  A healthy, optimized service: cost per unit stays flat or decreases
  as fixed costs are amortized across more volume.
  An optimizing service: cost per unit decreasing as you ship improvements.
  A degrading service: cost per unit increasing — you're adding cost faster
  than you're adding value.
```

**Setting cost efficiency targets:**

```python
# Add to your monitoring dashboard
class CostEfficiencyDashboard:
    def calculate_metrics(self, monthly_data):
        return {
            "cost_per_1k_requests": (
                monthly_data["total_cost"] / 
                (monthly_data["total_requests"] / 1000)
            ),
            "cost_per_mau": (
                monthly_data["total_cost"] / 
                monthly_data["monthly_active_users"]
            ),
            "cost_mom_change_pct": (
                (monthly_data["total_cost"] - monthly_data["prev_month_cost"]) / 
                monthly_data["prev_month_cost"] * 100
            ),
            "cost_per_unit_mom_change": (
                # If cost_per_1k_requests is growing, efficiency is degrading
                (cost_per_1k - prev_month_cost_per_1k) / prev_month_cost_per_1k * 100
            )
        }
```

---

## Part 20: Multi-Cloud and Cost Arbitrage

Some companies use multiple cloud providers to take advantage of price differences. This is advanced and generally not worth the operational complexity unless at very large scale ($50M+/year).

**Where multi-cloud makes cost sense:**

```
ML/GPU training:     GCP's TPUs are significantly cheaper than AWS GPU instances
                     for TensorFlow workloads at scale
                     
Object storage:      Cloudflare R2 charges $0 for egress (vs. $0.09/GB for S3)
                     At 100TB/month egress: $9,000/month saving
                     Trade-off: no native AWS integration, less mature ecosystem
                     
Specialized compute: Azure has advantages for Microsoft-stack workloads
                     (SQL Server, .NET, Active Directory integration)
```

**The operational cost of multi-cloud:**

Before choosing multi-cloud for cost, account for:
- Engineering time to build and maintain cross-cloud abstractions
- Different IAM/security models per cloud
- Different monitoring tools per cloud
- Data transfer costs between clouds ($0.02-$0.08/GB)
- Reduced leverage in vendor negotiations (single cloud = better discounts)

For most companies below $50M/year cloud spend, the operational complexity of multi-cloud exceeds the cost savings. Single-cloud optimization almost always has better ROI.

**Cloudflare R2 as a tactical alternative for egress-heavy workloads:**

```
If you have high egress costs (video, large file downloads, CDN origin):
  S3 Standard: $0.023/GB storage + $0.09/GB egress
  Cloudflare R2: $0.015/GB storage + $0 egress (no egress fees)
  
  At 100TB/month egress:
  S3: $9,000/month egress + $2,300/month storage = $11,300
  R2: $0 egress + $1,500/month storage = $1,500
  Savings: $9,800/month = $117,600/year
  
  Trade-off: Cloudflare-specific API (S3-compatible but minor differences),
  less geographic coverage than S3, newer service (less battle-tested)
```

---

## Part 21: Cost Optimization at the Architecture Level

The highest-leverage cost optimizations happen at architecture design time, not after deployment. The best time to optimize cost is before you write the first line of code.

**Architectural patterns that are naturally cost-efficient:**

```
1. READ-WRITE SEPARATION
   Separate read and write paths.
   Reads → caching layer → only cache misses hit the DB
   Writes → DB directly
   Result: 80-95% of reads served from cache → DB sized for 5-20% of traffic

2. ASYNC PROCESSING
   Move non-user-facing work to queues and workers.
   User-facing API: fast, small instances, scales with user requests
   Background workers: batch processing, cheaper instance types, Spot eligible
   Result: don't pay for heavy compute during interactive user requests

3. EVENT-DRIVEN ARCHITECTURE
   Services communicate via events, not synchronous calls.
   No idle connections between services.
   Kafka/SQS cost: a fraction of the compute cost of maintaining idle connections.
   Result: lower infrastructure coupling, easier to scale independently

4. TIERED STORAGE
   Hot data (accessed daily) → fast, expensive storage
   Warm data (accessed monthly) → cheaper storage, slightly slower
   Cold data (accessed yearly) → cheapest storage, slowest retrieval
   Result: 80% of data at 10% of the cost of all-hot storage

5. APPROXIMATE COMPUTATIONS
   HyperLogLog for cardinality estimation (count distinct users): 1KB per 10B items
   Bloom filters for membership testing: probabilistic but tiny
   Reservoir sampling for analytics: statistically accurate without storing all data
   Result: orders of magnitude cheaper than exact computation at scale
```

**The "cost cliff" in architecture:**

Some architectural decisions create a cost cliff — a point where costs jump dramatically:

```
Example: Single-region → Multi-region
  Before: $100K/month (3 AZs, 1 region)
  After:  $300K/month (3 AZs × 3 regions)
  The jump is sudden and large.
  
  At L6, you design with awareness of the cost cliff:
  "We can serve our 99.9% SLA with single-region for the next 18 months.
   The multi-region architecture doubles our cost.
   We'll design the system so it CAN become multi-region, but we won't
   activate it until our SLA requirements or customer base justifies the cost."
  
  This is the difference between "design for today with upgrade path"
  (L6) vs. "build for 10× scale now because we might need it" (over-engineering).
```

---

## Part 22: Exercises

### Exercise 1: Cost Audit

**Setup:** Access to any cloud account (use a personal AWS Free Tier account if you don't have access to a work account).

**Task:**
1. Find the top 5 cost categories this month
2. Identify any resources with low utilization (< 20% CPU for > 1 week)
3. Calculate cost per 1000 requests for any service you can instrument
4. Find any untagged resources

**Time limit:** 1 hour.

---

### Exercise 2: Lifecycle Policy Design

**Task:** Design an S3 lifecycle policy for a company that:
- Stores application logs (accessed occasionally for debugging, rarely after 30 days)
- Stores user-uploaded images (accessed frequently for the first year, rarely after)
- Stores database backups (must retain for 7 years for compliance, rarely accessed)

For each: write the lifecycle rules (transition at what days, to what tier, expire at what days).

**Expected answer:** 
- Application logs: 30d → Standard-IA, 90d → Glacier, 365d → expire
- User images: 365d → Standard-IA, 730d → Glacier Instant Retrieval, never expire
- DB backups: 30d → Glacier Flexible, 365d → Deep Archive, 2555d (7yr) → expire

---

### Exercise 3: Reserved Instance Decision

**Scenario:** Your service runs 20 EC2 m5.xlarge instances ($0.192/hr each) on-demand. Traffic is steady (no major variation). You're planning this level of usage for at least 18 months.

**Task:** Calculate the cost of:
a) All on-demand for 12 months
b) 80% Reserved Instances (1-year Standard) + 20% on-demand
c) 80% Savings Plans + 20% on-demand

Which is best? What are the risks of each?

**Expected answer:**
a) 20 × $0.192 × 8,760 = $33,638/year
b) 16 RI × $0.120 × 8,760 + 4 OD × $0.192 × 8,760 = $16,819 + $6,727 = $23,547/year (30% savings)
c) Similar to (b). Savings Plans offer more flexibility if you change instance types.
Risk: if you downsize before 12 months, you've committed to RIs you won't fully use.

---

### Exercise 4: Cost in a Design Review

**Scenario:** A teammate proposes a new feature that processes 1 billion events/day. They propose:
- Amazon Kinesis (100 shards) to ingest events: $10,800/month
- Lambda to process each event: $0.20/million × 1B = $200/day = $6,000/month
- DynamoDB to store results: $1.25/million writes × 1B/day = $37.50/day = $1,125/month

Total: ~$18,000/month

**Task:** Review the cost estimate. Are there cheaper alternatives? What questions would you ask? What trade-offs are there?

**Expected response:** Questions: What's the latency requirement? Kinesis at 100 shards seems over-provisioned (1 shard = 1M events/day → only 1 shard needed at 1B events/day, not 100). Can Lambda be batched (10 events per invocation = 10× cheaper)? Can SQS replace Kinesis if ordering isn't required ($0.40/million messages vs. $10,800/month for Kinesis)?

---

## 30-Day Study Schedule

**Week 1: Foundations**
- Day 1: Read Parts 1-3 (why cost matters, attribution, quarterly review)
- Day 2: Read Parts 4-5 (compute rightsizing, Reserved Instances, Spot)
- Day 3: Read Parts 6-8 (storage, networking, database)
- Day 4: Do Exercise 2 (lifecycle policy design)
- Day 5: Do Exercise 3 (Reserved Instance decision)

**Week 2: Tools and Culture**
- Day 6: Read Parts 9-11 (serverless, analytics, anomaly detection)
- Day 7: Read Parts 12-13 (cost culture, L5/L6 calibration)
- Day 8: Read war stories (Part 14)
- Day 9: Do Exercise 1 (cost audit on a real account)
- Day 10: Read Part 15-16 (safe optimization, FinOps framework)

**Week 3: Practice**
- Day 11: Read Parts 17-22 (interview drill, metrics, architecture)
- Day 12: Practice cost estimates for 3 common system designs (chat, URL shortener, video platform)
- Day 13: Do Exercise 4 (cost review of a design)
- Day 14: Write cost estimate section for your most recent design doc

**Week 4: Integration**
- Day 15-21: Apply to a real system you own
  - Day 15: Run a mini cost audit on your service
  - Day 16: Identify top 3 optimization opportunities
  - Day 17: Estimate ROI for each
  - Day 18: Implement the lowest-risk one
  - Day 19: Set up a cost anomaly alert
  - Day 20: Calculate cost per 1000 requests
  - Day 21: Update brag doc with findings and savings

---

## Part 23: The Cost Optimization Impact Story

Cost savings belong in your promo packet (Chapter 119). Here is how to write a cost optimization as an L6 impact story using the SOAR framework:

**Example SOAR bullet for a cost optimization:**

```
Scope:     "Across our entire analytics infrastructure (8 teams, $2M/year spend)"
Obstacle:  "No cost attribution — teams couldn't see their own costs and had
            no incentive to optimize. Data storage was 85% in S3 Standard with
            no lifecycle policies; compute was provisioned for peak 24/7."
Action:    "I designed and implemented the tagging strategy (500+ resources),
            built the attribution dashboard, ran the first 4 quarterly cost reviews,
            implemented lifecycle policies for all log buckets, and coordinated
            Reserved Instance purchases across 6 services."
Result:    "Reduced annual cloud spend by $420K (21%) in 6 months. Cost per DAU
            decreased from $0.45 to $0.36. Zero production incidents from the
            optimization work. The attribution dashboard is now used by all 8 teams."
```

This is a textbook L6 impact story: org-wide scope, cross-team coordination, measurable outcome, lasting artifact (the dashboard), and specific savings attached to a dollar amount.

---

## Part 24: Memorable Quotes

> *"Premature optimization is the root of all evil."* — Donald Knuth
> *(Note: this applies to algorithm optimization, not cloud cost optimization. Cloud bills don't premature-optimize — they grow relentlessly until someone pays attention.)*

> *"The most effective cost optimization is the one you do before launch, not after."*

> *"Cloud egress pricing is the tax on moving data. Architecture for the cloud means minimizing taxes."*

> *"A $500K/year savings is not a 'nice to have.' It's the equivalent of hiring 5 senior engineers without increasing headcount."*

> *"If you don't know what your service costs to operate, you don't own it — you just work on it."*

> *"Cost efficiency is not about being cheap. It's about spending on the things that matter and not spending on things that don't."*

---

## Part 25: The One-Sentence Summary

> *"Cost optimization discipline = quarterly review (where does money go?) + attribution (which team/feature causes which cost?) + rightsizing (are we over-provisioned?) + storage lifecycle policies + CDN for egress — treating cloud spend as a production metric you own, not a finance problem you ignore, is what separates L5 from L6 on infrastructure ownership."*

---

## Part 26: Company-Specific Notes

**Google Cloud / GCP:**
- Recommender (similar to AWS Compute Optimizer): built-in rightsizing recommendations
- Committed Use Discounts: 1-year or 3-year; 37-57% savings
- BigQuery: slot commitments for predictable analytics workloads vs. on-demand pricing
- GKE Autopilot: Kubernetes where Google optimizes node provisioning automatically (you pay only for pod requests, not node capacity)

**AWS-specific:**
- Savings Plans vs. Reserved Instances: Savings Plans are more flexible (apply to any instance family/size in a region); prefer Savings Plans over specific RIs for most use cases
- AWS Graviton instances (ARM): 20% cheaper than x86 equivalents with same or better performance for most workloads; worth testing
- S3 Intelligent-Tiering: automatically moves objects between tiers based on access patterns; monitoring fee $0.0025/1000 objects; worth it for buckets where access patterns are unknown

**Azure:**
- Azure Reserved VM Instances: similar to AWS RIs, 1 or 3 year commitment
- Azure Hybrid Benefit: use existing Windows Server / SQL Server licenses on Azure → 40-55% savings
- Azure Spot VMs: equivalent to AWS Spot, with Azure-specific interruption handling

---

## Part 27: The Cost Review Meeting — Running It Well

A cost review meeting is only as good as the preparation and follow-through. Here is how to run it effectively:

**Before the meeting:**
1. Pull the cost data (AWS Cost Explorer / GCP Billing) for the last month
2. Calculate MoM change for each category
3. Calculate cost per unit metrics (cost/request, cost/MAU)
4. Identify the top 3-5 anomalies or concerns
5. Prepare action items from last month's meeting for status check

**During the meeting (30 minutes, no more):**
```
0-5 min:   Status check on last month's action items
           "Action: implement S3 lifecycle for logs. Status: done. Savings: $12K/month."

5-20 min:  Top 5 cost items review
           For each: current month vs. last month vs. traffic growth
           If cost grows faster than traffic → flag as optimization candidate
           If cost grows slower than traffic → celebrate efficiency

20-27 min: Top 3 optimization opportunities
           For each: projected savings, risk level, owner, deadline
           Do NOT try to solve every problem in the meeting

27-30 min: Action items summary
           Each item: what, who, by when, expected savings
```

**After the meeting:**
- Write up action items in a shared doc
- Send a brief summary to engineering leadership ("this month we saved $X; next month we're targeting $Y")
- Add wins to the brag doc

---

## Part 28: The Cost Optimization Mindset at Scale

Cost optimization thinking changes at different scales. Understanding where you are on the journey helps you prioritize the right activities:

```
STAGE 1: Early startup ($0 - $100K/year cloud spend)
  Focus: move fast, optimize later
  The cost of a developer's time to optimize = far exceeds the savings
  Exception: architectural decisions that are hard to reverse later
  (choose the cheaper database architecture early — changing later is expensive)

STAGE 2: Growth company ($100K - $1M/year cloud spend)
  Focus: attribution and quick wins
  Start tagging resources, identify the biggest waste items
  Implement S3 lifecycle policies, Reserved Instances for baseline
  One engineer can save 15-20% with 2 weeks of work

STAGE 3: Scale-up ($1M - $10M/year cloud spend)
  Focus: systematic optimization
  Quarterly cost reviews, cost champions, anomaly detection
  Rightsizing campaigns, database optimization, CDN strategy
  Dedicated time budget for cost optimization in engineering cycles

STAGE 4: Large company ($10M+/year cloud spend)
  Focus: FinOps as a practice
  Dedicated FinOps team, EDP negotiations with cloud vendors
  Custom tooling for attribution, per-feature costing
  Architecture decisions explicitly modeled with cost trade-offs
  Potentially: custom hardware, multi-cloud arbitrage, colocation
```

The L6 engineer at a Stage 3 company runs Stage 3 activities. Getting caught doing Stage 1 activities ("we'll optimize later") at Stage 3 is a calibration miss.

---

## Final Pre-Interview Checklist

- [ ] Can you explain the top 3 cost levers in cloud infrastructure?
- [ ] Do you know the approximate AWS pricing for EC2 (on-demand vs. RI vs. Spot)?
- [ ] Can you explain S3 storage tiers and when to use each?
- [ ] Do you know what data egress costs and why CDN reduces it?
- [ ] Can you describe the quarterly cost review process?
- [ ] Can you define "showback" vs. "chargeback"?
- [ ] Can you explain the RI/Savings Plan purchasing strategy?
- [ ] Do you know what AWS Cost Anomaly Detection does?
- [ ] Can you estimate the cost of a common system design (chat app, URL shortener)?
- [ ] Can you write a SOAR-format impact bullet for a cost savings project?
- [ ] Do you know the difference between "cost per request" and "absolute cost"?
- [ ] Can you describe 3 architectural patterns that are inherently cost-efficient?

---

## Part 29: The 6-Month Cost Optimization Roadmap

If you inherit a service or team with no cost discipline, here is a pragmatic 6-month plan:

```
Month 1: FOUNDATION — Visibility
  Week 1-2: Audit all cloud resources. Identify untagged resources.
            Key question: "What does each service cost this month?"
  Week 3-4: Implement tagging strategy. Build cost attribution dashboard.
            Output: every resource tagged; cost visible per team.

Month 2: QUICK WINS — Low-risk savings
  Week 1:   Identify and delete orphaned resources (zero traffic, no owner)
  Week 2:   Implement S3 lifecycle policies for log buckets (90-day retention)
  Week 3-4: Purchase Reserved Instances for steady baseline compute
  Expected savings: 10-20% of bill

Month 3: RIGHTSIZING — Medium-risk savings
  Week 1-2: Identify over-provisioned instances (p90 CPU < 40%)
  Week 3-4: Right-size production instances (test on 1 first, monitor)
  Expected additional savings: 10-20% of compute

Month 4: ARCHITECTURE — Deeper savings
  Week 1-2: Identify top data transfer cost drivers; fix the largest
  Week 3-4: Add CDN for user-facing content not yet behind CDN
  Expected additional savings: 10-30% of networking

Month 5: PROCESS — Sustainable culture
  Week 1-2: Set up automated cost anomaly alerts
  Week 3-4: Run first quarterly cost review with team
  Designate cost champion for the team

Month 6: REPORTING — Close the loop
  Week 1-2: Document all savings achieved (for promo packet)
  Week 3-4: Present cost optimization results to skip-level
  Set up monthly recurring cost review

Total expected savings: 25-45% of original bill
Typical ROI: 10-50× the engineering time invested
```

---

## Part 30: The Cost-Reliability Trade-off

Cost optimization is not free. Every cost reduction comes with a trade-off. The L6 engineer makes these trade-offs explicitly, not accidentally.

**Common trade-offs:**

```
CO-LOCATE SERVICES IN SAME AZ (reduces cross-AZ egress):
  Cost saving:   $600/month at medium scale
  Reliability:   AZ failure → full outage instead of partial
  Decision:      Acceptable for internal services; not for user-facing critical path

SPOT INSTANCES (60-90% savings):
  Cost saving:   60-90% per instance
  Reliability:   2-minute interruption warning; stateless services can restart
  Decision:      Acceptable for batch jobs, CI runners; not for payment processing

SINGLE-REGION (vs. multi-region at 3× cost):
  Cost saving:   66% vs. 3-region active-active
  Reliability:   Full outage during region failure
  Decision:      Acceptable at 99.9% SLA; evaluate at 99.99%

GLACIER STORAGE (vs. Standard at 84% more):
  Cost saving:   84% on storage cost
  Reliability:   Retrieval takes hours instead of milliseconds
  Decision:      Acceptable for backups and compliance data; not for hot data

AGGRESSIVE CACHING (reduces DB reads):
  Cost saving:   Can halve DB instance size
  Reliability:   Cache invalidation bugs → stale data served to users
  Decision:      Acceptable for read-heavy data with tolerable staleness
```

Making these trade-offs explicitly is an L6 skill. Making them accidentally (because you didn't check) is a production incident waiting to happen.

---

## Index of Parts

| Part | Title |
|------|-------|
| 1 | Why Cost Is an Engineering Responsibility |
| 2 | Cloud Cost Attribution and Tagging |
| 3 | The Quarterly Cost Review Process |
| 4 | Compute Rightsizing |
| 5 | Reserved Instances, Spot, and Committed Use Discounts |
| 6 | Storage Cost Optimization |
| 7 | Data Transfer and Networking Costs |
| 8 | Database Cost Optimization |
| 9 | Serverless and Container Cost Optimization |
| 10 | Data Pipeline and Analytics Cost Optimization |
| 11 | Cost Anomaly Detection |
| 12 | Building a Cost Culture |
| 13 | L5 vs L6 Calibration on Cost Ownership |
| 14 | War Stories |
| 15 | Cost Optimization Without Breaking Production |
| 16 | FinOps — The Organizational Framework |
| 17 | Pre-Interview Drill |
| 18 | Cost Optimization in System Design Interviews |
| 19 | The Cost Efficiency Metrics You Should Track |
| 20 | Multi-Cloud and Cost Arbitrage |
| 21 | Cost Optimization at the Architecture Level |
| 22 | Exercises |
| 23 | The Cost Optimization Impact Story |
| 24 | Memorable Quotes |
| 25 | The One-Sentence Summary |
| 26 | Company-Specific Notes |
| 27 | Final Pre-Interview Checklist |
| 28 | The Cost Review Meeting |
| 29 | The 6-Month Cost Optimization Roadmap |
| 30 | The Cost-Reliability Trade-off |

---

*Pairs with Chapter 117 (Capacity Planning) for the compute sizing side of the cost equation, Chapter 116 (Refactoring Large Systems) for safe patterns when making cost-motivated architecture changes, and Chapter 56 (Metrics Collection System) for instrumenting the signals cost optimization depends on.*

`Chapter 120 | Section 7: Engineering Excellence | Cost Optimization Discipline` (Capacity Planning) for the compute sizing side of the cost equation, Chapter 116 (Refactoring Large Systems) for safe patterns when making cost-motivated architecture changes, and Chapter 56 (Metrics Collection System) for instrumenting the signals cost optimization depends on.*

`Chapter 120 | Section 7: Engineering Excellence | Cost Optimization Discipline` (Capacity Planning) for the compute sizing side of the cost equation, Chapter 116 (Refactoring Large Systems) for safe patterns when making cost-motivated architecture changes, and Chapter 56 (Metrics Collection System) for instrumenting the signals cost optimization depends on.*

`Chapter 120 | Section 7: Engineering Excellence | Cost Optimization Discipline`



