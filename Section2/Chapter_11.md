# Chapter 11: Cost, Efficiency, and Sustainable System Design

---

# Quick Visual: The Cost Translation Process

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 COST: THE HIDDEN DIMENSION OF SYSTEM DESIGN                 │
│                                                                             │
│   What most engineers see:          What Staff engineers see:               │
│                                                                             │
│   ┌─────────────────────┐           ┌─────────────────────┐                 │
│   │  "Does it work?"    │           │  "Does it work?"    │                 │
│   │  "Can it scale?"    │    →      │  "Can it scale?"    │                 │
│   │  "Is it reliable?"  │           │  "Is it reliable?"  │                 │
│   └─────────────────────┘           │  "Can we afford it?"│                 │
│                                     │  "Is it sustainable?"│                │
│                                     └─────────────────────┘                 │
│                                                                             │
│   THE SUSTAINABILITY EQUATION:                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Sustainable System = Correct + Scalable + Affordable + Operable   │   │
│   │                                                                     │   │
│   │   Missing any component → System will eventually fail               │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   KEY INSIGHT: A system can be technically perfect but economically         │
│   unsustainable. Staff engineers design for both.                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Simple Example: Senior vs Staff Cost Thinking

| Aspect | Senior (L5) Approach | Staff (L6) Approach |
|--------|---------------------|---------------------|
| **Design goal** | "Make it work, make it scale" | "Make it work, scale, and remain affordable as it grows" |
| **Resource sizing** | "Provision for peak load" | "Provision for expected + buffer, auto-scale for peaks, degrade gracefully beyond" |
| **Redundancy** | "Three replicas everywhere for safety" | "Three replicas for critical paths, two for others, one for internal tools" |
| **Feature decisions** | "Add all requested features" | "Each feature has a cost. What's the ROI? What can we defer?" |
| **Multi-region** | "Deploy to every region for lowest latency" | "Which regions justify the cost? What's the user distribution?" |
| **Technology choice** | "Use the best tool for each job" | "Use the best tool we can operate efficiently. Consistency reduces overhead." |

---

# Introduction

Systems don't just fail because they're incorrect. They fail because they're unsustainable.

A system can be architecturally elegant, technically sound, and perfectly scaled—and still be shut down because it's too expensive to run. A platform can handle every edge case flawlessly—and still be deprecated because it requires too many engineers to maintain. A service can meet every SLO—and still be replaced because its operational burden crushes the team responsible for it.

This is why cost and efficiency are not afterthoughts at Staff level. They're first-class design constraints, considered from the first whiteboard sketch to the final production deployment. Staff engineers treat "Can we afford this?" with the same seriousness as "Will this work?"

This chapter teaches you how to think about cost the way Staff engineers do: not as a finance problem, but as an architectural input that shapes every decision. We'll cover what cost really means in system design, why it matters at Google Staff level, how to reason about cost trade-offs, and how to demonstrate this thinking in interviews.

By the end, you'll approach cost as a dimension of engineering judgment, not a constraint imposed after the design is complete.

---

# Part 1: Foundations — What Cost Means in System Design

## Beyond Dollars: The True Cost of Systems

When engineers hear "cost," they often think of cloud bills and server expenses. But cost in system design is far broader. It encompasses every resource—human and computational—required to build, run, and evolve a system.

### The Four Dimensions of Cost

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE FOUR DIMENSIONS OF SYSTEM COST                       │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. COMPUTE COST                                                    │   │
│   │     • CPU cycles, memory, GPU time                                  │   │
│   │     • Scales with request volume                                    │   │
│   │     • Often the first cost people think of                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  2. STORAGE COST                                                    │   │
│   │     • Bytes stored (databases, object stores, caches)               │   │
│   │     • Compounds over time (data rarely deleted)                     │   │
│   │     • Varies hugely by storage tier (hot/warm/cold)                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  3. NETWORK COST                                                    │   │
│   │     • Bandwidth between services, regions, users                    │   │
│   │     • Cross-region transfer often most expensive                    │   │
│   │     • Often underestimated in design                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  4. OPERATIONAL COST                                                │   │
│   │     • Engineering time to maintain                                  │   │
│   │     • On-call burden and incident response                          │   │
│   │     • Complexity tax on every future change                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   INSIGHT: Compute is often the smallest cost. Operational cost,            │
│   especially at scale, frequently dominates.                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Compute Cost

CPU, memory, and specialized hardware (GPUs, TPUs). This is what most engineers think of first—servers running code, processing requests.

**Key characteristics:**
- Scales roughly linearly with traffic (more requests = more compute)
- Can be reduced through efficiency improvements (better algorithms, caching)
- Elastic: can scale up and down with demand
- Highly visible: easy to measure and attribute

**Example:** A feed ranking system using ML models might consume significant GPU resources. Each request requires model inference, and inference cost scales with request volume.

### Storage Cost

Every piece of data your system stores has a cost—not just for writing it, but for keeping it forever (or until explicitly deleted).

**Key characteristics:**
- Compounds over time: 1 TB/month becomes 12 TB after a year
- Varies dramatically by tier: in-memory is 100x costlier than cold storage
- Often overlooked until it becomes massive
- Retention policies are cost decisions

**Example:** A metrics system storing per-second data might seem cheap initially. But 100 metrics × 1,000 servers × 86,400 seconds/day × 365 days = 3 trillion data points per year. Storage strategy is an architectural decision.

### Network Cost

Data doesn't move for free. Every byte transferred between services, regions, or to users has a cost.

**Key characteristics:**
- Intra-region transfer is usually cheap or free
- Cross-region transfer is expensive (10-100x intra-region)
- Egress to internet is often the most expensive
- Often invisible until the bill arrives

**Example:** A globally distributed database replicating every write to five regions might be technically elegant but crushingly expensive. A Staff engineer asks: "Do we need synchronous replication to all regions, or can some be async?"

### Operational Cost

The cost that matters most and is measured least: the human effort required to keep a system running.

**Key characteristics:**
- Engineering time is expensive (fully-loaded cost of engineers)
- On-call burden affects team morale and retention
- Complexity creates drag on every future change
- Incidents have direct costs (person-hours) and indirect costs (user trust)

**Example:** A system that pages once a week for issues that take 2 hours to resolve costs ~100 engineering hours per year in incident response alone—plus the cognitive burden on the on-call engineer, the interruption to planned work, and the eventual burnout.

## Why Cost Is Not Just About Money

Cost in system design maps to something deeper: sustainability. An unsustainable system will eventually be replaced, rewritten, or abandoned—regardless of how well it works technically.

### Engineering Time

Every hour spent maintaining System A is an hour not spent building System B. Systems that are expensive to operate create opportunity costs across the organization.

**Questions Staff engineers ask:**
- How many engineers does this require to maintain?
- How often will we need to touch this code?
- Can a junior engineer operate this, or does it require specialists?
- What's the ramp-up time for a new team member?

### Operational Complexity

Complexity is a tax on every future action. Complex systems are harder to debug, slower to modify, and more likely to fail in unexpected ways.

**Questions Staff engineers ask:**
- How many moving parts does this design have?
- How many things need to go right for this to work?
- What's the blast radius when something fails?
- How long does incident diagnosis take?

### On-Call and Incident Cost

On-call burden directly impacts team sustainability. Burned-out engineers leave. Constant firefighting prevents proactive improvement.

**Questions Staff engineers ask:**
- How often will this page?
- What's the remediation playbook?
- Can common incidents be auto-remediated?
- Is the on-call burden proportional to the system's value?

## Why Systems Fail Because They're Unsustainable

Here's a scenario that plays out repeatedly:

**Month 1:** Team builds a system. It works perfectly. Everyone is happy.

**Month 6:** Usage grows. Team adds features, handles edge cases, patches bugs. The system becomes more complex. Still working.

**Year 1:** Original architects have moved on. New team members struggle to understand the system. On-call burden is significant but manageable.

**Year 2:** Technical debt has accumulated. Every change takes longer. On-call is painful—pages are frequent, diagnosis is hard. Team requests headcount for maintenance.

**Year 3:** Leadership asks: "Why do we have 5 engineers just keeping the lights on? Is this the best use of their time?" Someone proposes replacing the system with something simpler.

**Year 4:** The system is deprecated. A new, simpler system takes its place. The original system wasn't wrong—it was unsustainable.

**The lesson:** Correctness is necessary but not sufficient. A system that works but is too expensive to operate is not a successful system. Staff engineers design for the 5-year view, not just launch day.

---

# Part 2: Why Cost Matters at Google Staff Level

## Explicit Cost Reasoning Is Expected

At Google Staff level, you're expected to reason about cost explicitly—not as an afterthought, but as a design input.

This doesn't mean you need to produce exact dollar figures. It means you need to:
- Identify what drives cost in your design
- Make trade-offs that balance cost against other constraints
- Articulate why your design is cost-effective for the use case
- Avoid obvious waste

Interviewers notice when candidates design without cost awareness. Over-provisioned systems, unnecessary redundancy, and "gold-plated" features are signals of Junior/Senior thinking, not Staff thinking.

## How Cost Decisions Affect System Outcomes

### Scale Feasibility

A design that works at 1M users but costs $10M/year at 100M users may not be feasible to scale. Staff engineers think ahead: "If this grows 10x, what happens to cost? Does it scale linearly, or worse?"

**Example:** A system using synchronous cross-region writes adds 200ms latency and 3x storage for consistency. At 1,000 writes/second, maybe acceptable. At 1M writes/second, the cross-region bandwidth alone might be prohibitive.

### Reliability Trade-offs

Higher reliability costs more. Staff engineers know that 99.99% uptime costs significantly more than 99.9%, and 99.999% is dramatically more expensive still. The question is: what reliability does this use case actually require?

**Cost of nines:**

| Availability | Downtime/year | Relative Cost | Use Cases |
|-------------|---------------|---------------|-----------|
| 99% | 3.65 days | 1x | Internal tools |
| 99.9% | 8.7 hours | 2-3x | Most user-facing |
| 99.99% | 52 minutes | 5-10x | Critical services |
| 99.999% | 5 minutes | 20-50x | Payment, auth |

**Staff thinking:** "This is an internal analytics dashboard. 99.9% availability is fine—we don't need the infrastructure complexity and cost of 99.99%."

### Long-Term Velocity

Systems that are expensive to operate are expensive to evolve. Teams spend their time keeping things running, not making them better. Cost efficiency enables velocity; inefficiency creates drag.

**Example:** A team with 30% of their time consumed by operational toil can ship 70% as many features as a team with 10% toil. Over two years, that's a massive difference in delivered value.

## Over-Engineering: A Common Staff-Level Failure Mode

Paradoxically, one of the most common failure modes at Staff level is not under-engineering, but over-engineering. Experienced engineers have seen complex systems solve complex problems, and they reach for that complexity even when it isn't needed.

### Signs of Over-Engineering

- Distributed solutions for problems that don't require distribution
- Multi-region deployments for single-region usage patterns
- Microservices for systems that should be monoliths
- Real-time processing for batch-appropriate workloads
- Excessive redundancy for non-critical paths

### Why Over-Engineering Happens

- Anticipating scale that may never materialize
- Resume-driven development (using cool technology for its own sake)
- Cargo-culting from previous high-scale systems
- Fear of being caught unprepared

### The Staff-Level Response

Staff engineers resist over-engineering by asking:
- "What problem does this complexity solve?"
- "What's the probability we'll need this?"
- "What's the cost of adding it later vs. adding it now?"
- "What's the simplest design that meets our actual requirements?"

## The Contrast: Early-Career vs Staff Thinking

| Dimension | Early-Career Thinking | Staff Thinking |
|-----------|----------------------|----------------|
| **Primary goal** | "Make it work" | "Make it work, efficiently and sustainably" |
| **Cost awareness** | "Someone else's problem" | "Core design constraint" |
| **Scale planning** | "Build for maximum possible scale" | "Build for expected scale + headroom, evolve as needed" |
| **Technology choices** | "Use the best/newest for each component" | "Use what we can operate efficiently; consistency matters" |
| **Redundancy** | "More is safer" | "Right-size for the failure modes that matter" |
| **Features** | "Add everything requested" | "Every feature has a cost. Prioritize ruthlessly." |
| **Simplicity** | "Simplicity is nice to have" | "Simplicity is a feature. Complexity is a cost." |

---

# Part 3: Cost as a First-Class Design Constraint

## Right-Sizing vs Over-Provisioning

Over-provisioning means allocating more resources than needed "just in case." It feels safe but creates waste.

**Over-provisioning mindset:**
- "Let's use the largest instance type to be safe"
- "Add 5x headroom for unexpected growth"
- "Keep data forever in case we need it"

**Right-sizing mindset:**
- "What capacity do we actually need today, with reasonable headroom?"
- "What's our expected growth, and when should we revisit?"
- "What data can we archive or delete, and after how long?"

### The Right-Sizing Framework

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RIGHT-SIZING FRAMEWORK                                   │
│                                                                             │
│   1. MEASURE ACTUAL USAGE                                                   │
│      • What's the current load? (CPU, memory, storage, bandwidth)           │
│      • What's the peak vs average ratio?                                    │
│      • What's the seasonal variation?                                       │
│                                                                             │
│   2. APPLY REASONABLE HEADROOM                                              │
│      • Baseline: 30-50% headroom for normal operation                       │
│      • Handle expected peaks without scaling                                │
│      • Accept that unexpected spikes may require action                     │
│                                                                             │
│   3. PLAN FOR GROWTH                                                        │
│      • What's the expected growth rate?                                     │
│      • At what point will we need to resize?                                │
│      • What's the lead time for adding capacity?                            │
│                                                                             │
│   4. BUILD ELASTICITY                                                       │
│      • Auto-scale for predictable peaks (daily, weekly patterns)            │
│      • Rate limit or degrade for unexpected spikes                          │
│      • Monitor and alert before hitting limits                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Elasticity vs Fixed Capacity

Fixed capacity means provisioning for peak load all the time. Elastic capacity means scaling resources with demand.

| Approach | Pros | Cons | When to Use |
|----------|------|------|-------------|
| **Fixed (provision for peak)** | Simple, no scaling latency | Expensive during low periods | Predictable load, low peak/avg ratio |
| **Elastic (auto-scale)** | Cost-efficient, handles variability | Scaling lag, complexity | Variable load, high peak/avg ratio |
| **Hybrid** | Best of both | More complex | Most production systems |

**Staff-level reasoning:**
"Our system has a 5x peak-to-average ratio. If I provision for peak, I'm paying 5x what I need most of the time. Instead, I'll provision for 2x average (handles normal variation), auto-scale up to 5x for predicted peaks, and implement graceful degradation for anything beyond. This saves 60% on compute while maintaining reliability."

## Simplicity vs Optimization

Sometimes the simplest solution is also the most cost-effective. Other times, optimization is necessary. Staff engineers know the difference.

### When Simplicity Wins

- Early-stage systems where requirements are unclear
- Low-scale systems where optimization overhead exceeds savings
- Rapidly changing systems where optimization becomes obsolete
- Teams lacking expertise to operate complex solutions

### When Optimization Is Worth It

- At scale, small efficiencies multiply: 10% savings at $1M/month = $100K/month
- Hot paths that dominate resource consumption
- Stable systems where optimization persists
- When simplicity has already been maximized

### The Decision Heuristic

"What's the cost of this optimization (engineering time, complexity) vs the savings? At what scale does optimization pay for itself?"

**Example:** A cache optimization that takes 2 weeks of engineering time and saves 5% on database load. At $10K/month database cost, that's $500/month savings—payback in 80 months. Probably not worth it. At $1M/month, that's $50K/month savings—payback in 2 weeks. Obviously worth it.

## When "Good Enough" Is the Right Answer

Staff engineers often choose "good enough" over "optimal." This isn't laziness—it's wisdom.

**"Good enough" criteria:**
- Meets functional requirements
- Meets non-functional requirements (latency, reliability)
- Is within cost budget
- Is maintainable by the team
- Leaves room for evolution

**Why "good enough" is often better:**
- Perfect is the enemy of shipped
- Requirements change; over-optimization becomes waste
- Simple systems are easier to improve later
- Engineering time has opportunity cost

**Example:** "This design uses 20% more storage than optimal, but it's dramatically simpler to implement and operate. At our scale, the storage cost is $5K/year. The engineering time to optimize would cost $50K. Good enough wins."

## How Cost Influences Specific Decisions

### Data Model Choices

| Decision | Cost Implication | Staff Reasoning |
|----------|-----------------|-----------------|
| Normalized vs denormalized | Denormalized = more storage, faster reads | "For read-heavy with stable schema, denormalize. Storage is cheap; joins are expensive at scale." |
| Retention period | Longer = more storage, more indexes | "What's the business value of old data? Archive to cold storage after 90 days." |
| Granularity | Finer = more data points | "Per-second metrics for real-time dashboards; per-minute for historical analysis." |

### Caching Strategies

| Decision | Cost Implication | Staff Reasoning |
|----------|-----------------|-----------------|
| Cache size | More cache = memory cost | "Cache the hot 20% that serves 80% of requests. Diminishing returns beyond." |
| Cache tier | In-memory vs SSD vs disk | "Redis for hot data (ms latency), SSD cache for warm (10ms), origin for cold." |
| TTL strategy | Shorter = more origin hits | "Balance freshness requirements against origin load. 1-minute TTL is often enough." |

### Replication and Redundancy

| Decision | Cost Implication | Staff Reasoning |
|----------|-----------------|-----------------|
| Number of replicas | More = higher cost, better durability | "Three replicas for production data. One for dev environments." |
| Cross-region replication | Network cost, complexity | "Replicate to DR region async. Full multi-region only for global products." |
| Consistency level | Stronger = higher latency, sometimes more cost | "Eventual consistency for social feeds. Strong consistency for payments." |

### Multi-Region Decisions

| Decision | Cost Implication | Staff Reasoning |
|----------|-----------------|-----------------|
| Active-active vs active-passive | Active-active = 2x cost + sync complexity | "Active-passive for DR. Active-active only when latency requires it." |
| Number of regions | Each region = infrastructure + operational cost | "Start with 2 regions. Add only where user base justifies it." |
| What to replicate | Full replication vs partial | "Replicate user-facing data. Keep analytics in primary region." |

---

# Part 4: Applied Examples

## Example 1: News Feed System

### The Design Problem

Design a news feed system for a social platform with 100M daily active users. Users follow other users and see posts from people they follow.

### Major Cost Drivers

1. **Fan-out on write:** Each post must reach all followers. Celebrity accounts with millions of followers create massive write amplification.

2. **Storage:** Every post must be stored. Every feed must be materialized (if using push model). Media attachments dominate storage.

3. **Read path compute:** Every feed request requires assembly—potentially from many sources.

4. **Caching:** Effective caching reduces database load but requires significant memory infrastructure.

### Cost-Conscious Design Choices

**Fan-out strategy:**
- Push model for users with <10K followers (pre-compute feeds)
- Pull model for celebrities (fetch at read time)
- Hybrid reduces write amplification by 90%+ while keeping reads fast

**Storage tiering:**
- Hot storage: Last 7 days of feeds (SSD)
- Warm storage: 7-90 days (disk)
- Cold storage: >90 days (archived, reconstructed on demand)
- Media: CDN for frequently accessed, object storage for archive

**Caching strategy:**
- Cache materialized feeds for active users (last 24 hours of activity)
- Don't cache inactive users (80% of MAU check monthly)
- Short TTL (5 minutes) balances freshness and hit rate

### What Over-Engineering Looks Like

**Over-engineered version:**
- Real-time fanout for all users, regardless of follower count
- Infinite feed retention at full fidelity
- Multi-region active-active with synchronous replication
- Pre-computed feeds for all users, including inactive
- ML-based ranking on every read

**Why a Staff Engineer rejects it:**
- Fanout for celebrities is prohibitively expensive (1 post = 10M writes)
- Storing every feed forever compounds storage cost exponentially
- Synchronous multi-region adds 200ms+ latency and 3x storage cost
- Pre-computing for inactive users wastes 80% of computation
- ML ranking on every read without caching multiplies compute 10-100x

**Staff reasoning:** "This design is technically correct, but the cost scales superlinearly with users. At 100M DAU, we'd be spending $X/month on infrastructure that's 90% waste. Let me redesign with cost as a constraint."

### The Cost Trade-offs

| Choice | Saves | Costs | Trade-off |
|--------|-------|-------|-----------|
| Hybrid fan-out | 90% write operations | Slight latency for celebrity follows | Worth it |
| Feed TTL of 90 days | 75% storage | Older content requires reconstruction | Worth it |
| Inactive user eviction | 80% cache memory | Cache miss on return | Worth it |
| Single-region primary | Cross-region bandwidth | Higher latency for distant users | Maybe worth it |

---

## Example 2: Global Rate Limiter

### The Design Problem

Design a rate limiter for an API gateway handling 1 million requests per second across multiple regions.

### Major Cost Drivers

1. **State management:** Rate limit counters must be stored and accessed for every request.

2. **Cross-region coordination:** Global limits require communication between regions.

3. **Latency budget:** Rate limiting happens on the critical path—every millisecond matters.

4. **Network cost:** Cross-region synchronization means cross-region traffic.

### Cost-Conscious Design Choices

**Local vs global limiting:**
- Local limits per region: No cross-region traffic, eventual consistency
- Global limits: Cross-region coordination, higher latency and cost
- **Choice:** Local limits for most users; global coordination only for enterprise customers who need it

**Counter storage:**
- In-memory on API gateway nodes: Zero network cost, ephemeral
- Redis cluster: Persistence, but network hop per request
- **Choice:** In-memory counters with periodic sync. Lose some accuracy, gain massive cost reduction.

**Synchronization strategy:**
- Synchronous: Accurate, expensive, adds latency
- Asynchronous: Eventually consistent, cheap, no latency
- **Choice:** Async sync every 5 seconds. Accept that rate limits are approximate.

### What Over-Engineering Looks Like

**Over-engineered version:**
- Exactly-once rate limiting with distributed consensus
- Globally synchronized counters using Raft/Paxos
- Every rate limit check goes through central coordination
- Audit log of every rate limit decision

**Why a Staff Engineer rejects it:**
- Distributed consensus adds 10-50ms per request (unacceptable on critical path)
- Central coordination is a single point of failure and a bottleneck
- Audit logging every request at 1M RPS = 86B events/day = massive storage
- Rate limiting doesn't need exactly-once—approximate is fine

**Staff reasoning:** "Rate limiting exists to protect our infrastructure, not to charge customers to the penny. If someone sends 101 requests when their limit is 100, the business impact is zero. I'm choosing approximate local limiting with eventual consistency because it's 10x cheaper and adds no latency."

### The Cost Trade-offs

| Choice | Saves | Costs | Trade-off |
|--------|-------|-------|-----------|
| In-memory counters | Network cost, latency | Counters lost on restart | Acceptable |
| Local-first limiting | Cross-region bandwidth | Not globally exact | Acceptable for most users |
| Async sync | Latency, coordination cost | 5-second staleness | Acceptable |
| No per-request audit | Storage cost | Less visibility | Sample instead |

---

## Example 3: Metrics / Observability Pipeline

### The Design Problem

Design a metrics collection system for 50,000 servers, each emitting 500 metrics at per-second granularity.

### Major Cost Drivers

1. **Ingestion volume:** 50K servers × 500 metrics × 1/second = 25M data points/second.

2. **Storage:** At per-second granularity, storage compounds rapidly. 25M/sec × 86,400 sec/day = 2.16 trillion data points/day.

3. **Query path:** Dashboards and alerts constantly read data. Index and query costs scale with data volume.

4. **Retention:** How long to keep data at each granularity?

### Cost-Conscious Design Choices

**Ingestion aggregation:**
- Don't store per-second at the edge—aggregate to per-minute before shipping
- Reduce ingestion volume by 60x (25M/sec → 420K/min)
- Keep per-second available on the host for 5 minutes for live debugging

**Storage tiering by age:**
- 0-24 hours: Per-minute, hot storage (fast queries)
- 1-7 days: Per-5-minute, warm storage (acceptable query latency)
- 7-90 days: Per-hour, cold storage (slow but accessible)
- >90 days: Per-day, archived (offline, reconstructed on demand)

**Metric cardinality control:**
- High-cardinality metrics (per-request-id) are sampled, not stored completely
- Cap on unique time series per service (prevents cardinality explosion)
- Automatic pruning of unused metrics

### What Over-Engineering Looks Like

**Over-engineered version:**
- Per-second granularity forever
- Every metric stored, no sampling
- Real-time dashboards for all historical data
- Full retention indefinitely

**Why a Staff Engineer rejects it:**
- Per-second × 1 year = 800 trillion data points → petabytes of storage
- No sampling means cardinality explosions crash the system
- Real-time queries on historical data require expensive indexing
- Indefinite retention means storage grows without bound

**Staff reasoning:** "We need per-second data for live debugging, but nobody queries per-second from last month. I'll tier the data: per-second in-memory for 5 minutes, per-minute for a day, then progressively downsample. This reduces storage by 100x while preserving the use cases that matter."

### The Cost Trade-offs

| Choice | Saves | Costs | Trade-off |
|--------|-------|-------|-----------|
| Edge aggregation | 60x ingestion cost | 1-minute minimum granularity centrally | Worth it |
| Progressive downsampling | 100x storage | Lose precision over time | Worth it |
| Cardinality limits | System stability | Sampled high-cardinality data | Worth it |
| Tiered storage | Hot storage cost | Query latency for old data | Worth it |

---

# Part 5: Cost vs Reliability vs Performance Trade-offs

## The Fundamental Reality

Three things are true in system design:

1. **Higher reliability always increases cost.** More redundancy, faster failover, better testing—all require resources.

2. **Lower latency often increases cost.** Edge caching, more replicas, faster hardware—all add expense.

3. **You can't have everything.** Every system exists on a trade-off frontier where improving one dimension typically sacrifices another.

Staff engineers make these trade-offs explicitly, with clear reasoning about what's acceptable for the use case.

## The Trade-off Frontier

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE COST-RELIABILITY-PERFORMANCE FRONTIER                │
│                                                                             │
│   RELIABILITY                                                               │
│       ▲                                                                     │
│       │       ╱╲ You can only operate                                       │
│       │      ╱  ╲ on this frontier                                          │
│       │     ╱    ╲                                                          │
│       │    ╱  A   ╲    A = High reliability, moderate perf, high cost       │
│       │   ╱        ╲   B = High perf, moderate reliability, high cost       │
│       │  ╱    C     ╲  C = Moderate both, moderate cost                     │
│       │ ╱            ╲ D = Low cost, compromise on both                     │
│       │╱   D          ╲                                                     │
│       └───────────────────────────────▶ PERFORMANCE                         │
│                                                                             │
│   Each point on the frontier has a cost. Moving outward (better on both)    │
│   requires spending more. Staff engineers choose the right point.           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Scenario: The 20% Latency Reduction

**The proposal:** "We can reduce P99 latency by 20% (from 250ms to 200ms) by adding edge caching and a second database replica in each region."

**The cost:** Infrastructure cost doubles.

### How a Staff Engineer Reasons Through This

**Step 1: Quantify the benefit.**
- 20% latency reduction sounds good, but what's the actual impact?
- Current 250ms P99—is this causing user complaints? Abandonment? Revenue loss?
- If the system is already "fast enough," improvement may have minimal value.

**Step 2: Quantify the cost.**
- Doubling infrastructure cost: What's the dollar amount? $50K/month? $500K/month?
- Is this within budget? Does it require new budget approval?
- What's the opportunity cost? What else could we build with that money?

**Step 3: Assess the use case.**
- What kind of system is this?
- For a payment system, 50ms matters—faster is worth it.
- For an analytics dashboard, 50ms is imperceptible—not worth it.
- For an ad bidding system, latency directly impacts revenue—worth it.

**Step 4: Explore alternatives.**
- Can we get 80% of the benefit for 20% of the cost?
- Optimize the hot path first (cheaper)
- Add edge caching for static content only (partial improvement)
- Improve database queries rather than adding replicas

**Step 5: Make an explicit decision with reasoning.**

**If reject:** "The current 250ms P99 is acceptable for our analytics dashboard use case. Users don't notice a 50ms improvement. Doubling our infrastructure cost—$200K/year—to make an imperceptible improvement is not a good use of resources. I'd rather invest in features users actually want."

**If accept:** "For our ad bidding system, every millisecond matters. 50ms faster means we can participate in 10% more auctions. At our scale, that's $1M/year in additional revenue. Spending $200K to gain $1M is an obvious yes."

## The Decision Framework

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              COST-BENEFIT DECISION FRAMEWORK                                │
│                                                                             │
│   STEP 1: QUANTIFY THE BENEFIT                                              │
│   ────────────────────────────────────────────────────                      │
│   • What user experience improvement?                                       │
│   • What revenue/engagement impact?                                         │
│   • What operational improvement?                                           │
│   • Is this benefit real or theoretical?                                    │
│                                                                             │
│   STEP 2: QUANTIFY THE COST                                                 │
│   ────────────────────────────────────────────────────────                  │
│   • Infrastructure cost (compute, storage, network)                         │
│   • Engineering cost (build, maintain, operate)                             │
│   • Opportunity cost (what else could we do?)                               │
│   • Complexity cost (ongoing tax on every change)                           │
│                                                                             │
│   STEP 3: COMPARE                                                           │
│   ────────────────────────────────────────────────────────                  │
│   • Benefit > Cost? Proceed.                                                │
│   • Benefit < Cost? Reject or find cheaper alternative.                     │
│   • Uncertain? Prototype/experiment before committing.                      │
│                                                                             │
│   STEP 4: COMMUNICATE                                                       │
│   ────────────────────────────────────────────────────────                  │
│   • Explain the trade-off clearly                                           │
│   • Document the decision for future reference                              │
│   • Set metrics to validate the decision                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 6: Failure Modes Related to Cost

## Over-Provisioning: Wasted Resources

**The pattern:** Provision for maximum imaginable load, pay for resources that sit idle.

**How it happens:**
- Fear of outages leads to 10x headroom
- Nobody re-evaluates after launch
- Auto-scaling not implemented or not trusted
- Easier to ask for resources than to optimize

**The cost:** Money spent on unused infrastructure. At scale, this can be millions of dollars per year.

**Real example:**
A team provisions 100 servers expecting high traffic. Actual peak usage: 15 servers. 85% of spend is waste. But because "we've always had this capacity," nobody questions it until a cost review forces the conversation.

**Staff-level response:**
- Implement proper monitoring of utilization
- Set up auto-scaling with appropriate thresholds
- Review capacity quarterly
- Treat provisioning as a reversible decision

## Under-Provisioning: Outages and Lost Trust

**The pattern:** Under-provision to save money, then experience outages during peak load.

**How it happens:**
- Optimizing for average load, forgetting peaks
- Budget pressure without reliability input
- Slow scaling response to growth

**The cost:** Outages damage user trust, require engineering time to fix, and often cost more than the savings.

**Real example:**
A team saves $50K/year by running with minimal headroom. A traffic spike causes an outage lasting 4 hours, requiring 3 engineers to respond, and generating a customer impact that dwarfs the savings.

**Staff-level response:**
- Provision for peak, not average
- Implement auto-scaling with appropriate headroom
- Calculate the cost of outages, not just infrastructure
- Make cost-reliability trade-offs explicit

## Premature Optimization: Wasted Engineering Time

**The pattern:** Optimize before knowing what to optimize. Spend engineering time on improvements that don't matter.

**How it happens:**
- Intuition about bottlenecks without measurement
- Excitement about clever solutions
- Copying patterns from higher-scale systems

**The cost:** Engineering time is expensive. Premature optimization has opportunity cost—that time could be spent on features or actual bottlenecks.

**Real example:**
A team spends 3 months building a sophisticated caching layer. Turns out the database is not the bottleneck—the API is CPU-bound on JSON serialization. The caching layer is useless, and the real problem remains.

**Staff-level response:**
- Measure before optimizing
- Optimize the actual bottleneck
- Ask "Is this worth the engineering time?"

## Expensive Hot Paths: The 1% That Costs 90%

**The pattern:** A small fraction of requests consumes the vast majority of resources.

**How it happens:**
- Expensive operations not identified or measured
- All requests treated equally
- No tiering of response quality by cost

**The cost:** Massive infrastructure spend on requests that may not justify it.

**Real example:**
1% of API requests are complex analytics queries. Each takes 10 seconds and consumes 100x the resources of a normal request. This 1% of requests drives 60% of infrastructure cost.

**Staff-level response:**
- Identify and measure hot paths
- Consider rate limiting or tiering expensive operations
- Offer different SLOs for different request types
- Make cost visible to the requester

## Incident Example: When Cost Decisions Caused Failure

**The Scenario:**

An e-commerce platform made the following cost-saving decisions:
1. Reduced database replicas from 3 to 2 to save $10K/month
2. Disabled cross-region replication to save $20K/month
3. Set aggressive instance right-sizing with minimal headroom

**What Happened:**

During Black Friday, traffic hit 10x normal. The database couldn't handle the load with only 2 replicas. One replica fell behind on replication; the other couldn't serve all reads. The application started timing out.

With no cross-region failover, there was no backup. The on-call team tried to add replicas, but provisioning took 20 minutes. During that time, the site was effectively down.

**The Damage:**
- 45 minutes of severe degradation during peak shopping
- Estimated $2M in lost sales
- Significant reputation damage
- 3 engineers working through the night

**The Lesson:**

The team saved $30K/month (~$360K/year) in infrastructure. They lost $2M in a single incident, plus engineering time and reputation.

**Staff-level analysis:**
"The cost-saving decisions were individually reasonable but collectively created unacceptable risk. We saved $360K/year but couldn't survive a predictable peak. The correct trade-off was: keep cross-region replication for the checkout path (critical), reduce it for catalog browsing (less critical). Selective reliability based on business impact."

---

# Part 7: Evolution Over Time (Sustainability Thinking)

## How Cost Reasoning Changes with System Maturity

Cost optimization is not static. What makes sense for a new system differs from what makes sense for a mature one.

### Early-Stage System (0-6 months)

**Priorities:**
- Ship quickly
- Validate product-market fit
- Learn what users actually want

**Cost approach:**
- Simplicity over efficiency
- Modest over-provisioning acceptable (insurance against surprises)
- Technical debt is fine if it enables speed
- Don't optimize what might be thrown away

**Staff reasoning:**
"We're not sure if this product will succeed. Spending 3 months optimizing infrastructure for something that might be deprecated in 6 months is not a good investment. Ship it, learn, iterate."

### Growing System (6-24 months)

**Priorities:**
- Handle increasing load
- Identify scaling bottlenecks
- Pay down critical technical debt

**Cost approach:**
- Start measuring and attributing costs
- Identify and address obvious inefficiencies
- Right-size based on actual usage data
- Implement auto-scaling

**Staff reasoning:**
"We have real traffic data now. We know what the hot paths are. Let's optimize the top 3 bottlenecks—they'll give us 80% of the benefit for 20% of the effort."

### Mature System (2+ years)

**Priorities:**
- Operational efficiency
- Predictable costs
- Long-term sustainability

**Cost approach:**
- Regular cost reviews
- Aggressive optimization of stable components
- Investment in automation to reduce operational cost
- Architecture changes to improve efficiency at scale

**Staff reasoning:**
"This system is stable and will run for years. A 10% efficiency improvement saves $500K/year. It's worth investing 2 months of engineering time to achieve that."

## What Changes Staff Engineers Introduce Over Time

### Phase 1: Visibility (First 3 months)

- Implement cost attribution (which features/teams drive cost)
- Set up monitoring for utilization
- Identify top cost drivers

### Phase 2: Quick Wins (3-6 months)

- Right-size obviously over-provisioned resources
- Implement auto-scaling where beneficial
- Set retention policies for data that grows unbounded
- Address the worst hot paths

### Phase 3: Structural Improvements (6-18 months)

- Refactor expensive components
- Migrate to more cost-effective architectures
- Implement tiered storage
- Build cost-aware features (e.g., rate limiting, caching)

### Phase 4: Continuous Optimization (Ongoing)

- Regular cost reviews
- A/B testing of efficiency improvements
- Cost as a feature in design reviews
- Cost targets in team OKRs

## When Optimization Is Necessary vs. Intentionally Delayed

### Optimize Now

- Cost is threatening sustainability (burning budget too fast)
- Inefficiency is blocking scale (can't handle expected growth)
- Simple wins are available (obvious waste)
- System is stable (changes won't be invalidated)

### Delay Intentionally

- Requirements are still changing (optimization may be wasted)
- Engineering time is better spent on product (opportunity cost)
- The cost is acceptable and not growing (no urgency)
- You're about to refactor anyway (optimization will be obsolete)

**Staff judgment:** "We could save 15% on storage costs, but we're planning a major data model change next quarter anyway. I'm intentionally delaying this optimization because it would be thrown away in 3 months."

---

# Part 8: Interview Calibration

## How Interviewers Probe Cost Thinking

Interviewers rarely ask directly about cost. Instead, they probe for cost awareness through indirect questions:

| What They Ask | What They're Assessing |
|--------------|----------------------|
| "How would you handle 10x growth?" | Do you think about cost scaling, or just technical scaling? |
| "What happens if traffic doubles overnight?" | Do you consider the cost of over-provisioning? |
| "Why did you choose this architecture?" | Is cost one of your considerations? |
| "What would you simplify if you had less time?" | Do you understand what's essential vs. nice-to-have? |
| "How would you operate this system?" | Do you consider operational cost? |
| "What would you change if this were a startup?" | Can you adjust cost profile for different contexts? |

## Example Interview Questions Related to Cost

**Direct questions (rare but possible):**
- "How do you think about cost in system design?"
- "What are the major cost drivers in your design?"
- "How would you reduce the cost of this system by 50%?"

**Indirect questions (more common):**
- "This seems like a complex architecture. Why did you choose this?"
- "What trade-offs are you making with this redundancy approach?"
- "How would you prioritize if you had half the engineering resources?"
- "What would you change for an early-stage startup vs. a mature company?"

## Staff-Level Phrases for Discussing Cost

**When introducing cost considerations:**
- "Let me think about the major cost drivers in this design..."
- "Before we add more complexity, let me consider the cost implications..."
- "This design is correct, but I want to assess whether it's cost-effective at our scale..."

**When making trade-offs:**
- "I'm choosing X over Y because the cost of Y scales poorly with traffic..."
- "This adds operational complexity, so let me justify whether the benefit is worth it..."
- "The simplest solution might cost more in compute, but saves significantly in engineering time..."

**When questioning designs:**
- "This would work, but is it cost-effective given our scale and requirements?"
- "Before we gold-plate this, what's the minimum viable reliability we actually need?"
- "I'm concerned this will be expensive to operate—let me think about alternatives..."

**When discussing alternatives:**
- "If cost is a concern, we could do X instead, which trades Y for Z..."
- "At smaller scale, I'd simplify this. At our scale, the optimization pays for itself..."
- "This is the right architecture for a well-funded company. For a startup, I'd recommend..."

## Common Mistakes by Strong Senior Engineers

### Mistake 1: Ignoring Cost Entirely

**What happens:** The candidate produces a technically excellent design without ever mentioning cost implications.

**Interviewer's perception:** "This person builds systems like money is infinite. At Staff level, I need someone who considers the full picture."

**Correction:** Explicitly mention cost as one of your design considerations, even if briefly.

### Mistake 2: Over-Engineering for Scale That May Never Exist

**What happens:** The candidate designs for Google-scale when the problem statement suggests modest scale.

**Interviewer's perception:** "This person can't calibrate complexity to context. They'll over-engineer everything."

**Correction:** Ask about expected scale and design appropriately. Acknowledge trade-offs for different scales.

### Mistake 3: Treating All Requirements as Equally Important

**What happens:** The candidate treats every feature as must-have, never discussing what could be simplified or deferred.

**Interviewer's perception:** "This person can't prioritize. They'll build everything at maximum complexity."

**Correction:** Explicitly prioritize. Say "If we need to simplify, I'd start here because..."

### Mistake 4: Confusing Complex with Sophisticated

**What happens:** The candidate adds complexity (more services, more layers, more redundancy) to demonstrate knowledge.

**Interviewer's perception:** "This person doesn't understand that simplicity is a feature. They'll create operational nightmares."

**Correction:** Justify every component. Ask yourself "What would I remove?" and discuss it.

---

# Part 9: Diagrams

## Diagram 1: Cost Hotspots in System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               COST HOTSPOTS IN A TYPICAL SYSTEM ARCHITECTURE                │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         EXTERNAL TRAFFIC                            │   │
│   │                              │                                      │   │
│   │                              ▼                                      │   │
│   │   ┌─────────────────────────────────────────────────────────────┐   │   │
│   │   │  CDN / EDGE CACHE        [MEDIUM COST]                      │   │   │
│   │   │  • Bandwidth to users (egress)                              │   │   │
│   │   │  • Storage of cached assets                                 │   │   │
│   │   └─────────────────────────────────────────────────────────────┘   │   │
│   │                              │                                      │   │
│   │                              ▼                                      │   │
│   │   ┌─────────────────────────────────────────────────────────────┐   │   │
│   │   │  LOAD BALANCER           [LOW COST]                         │   │   │
│   │   │  • Mostly compute                                           │   │   │
│   │   └─────────────────────────────────────────────────────────────┘   │   │
│   │                              │                                      │   │
│   │                              ▼                                      │   │
│   │   ┌─────────────────────────────────────────────────────────────┐   │   │
│   │   │  APPLICATION SERVERS     [MEDIUM-HIGH COST]                 │   │   │
│   │   │  • Compute for request processing      ◄── HOT PATH         │   │   │
│   │   │  • Scales with traffic                                      │   │   │
│   │   │  • ML inference if applicable          ◄── VERY EXPENSIVE   │   │   │
│   │   └─────────────────────────────────────────────────────────────┘   │   │
│   │                     │                  │                            │   │
│   │                     ▼                  ▼                            │   │
│   │   ┌──────────────────────┐  ┌──────────────────────────────────┐   │   │
│   │   │  CACHE (Redis)       │  │  MESSAGE QUEUE                   │   │   │
│   │   │  [MEDIUM COST]       │  │  [LOW-MEDIUM COST]               │   │   │
│   │   │  • Memory expensive  │  │  • Storage of in-flight messages │   │   │
│   │   │  • Often oversized   │  │  • Often over-retained           │   │   │
│   │   └──────────────────────┘  └──────────────────────────────────┘   │   │
│   │                     │                  │                            │   │
│   │                     ▼                  ▼                            │   │
│   │   ┌─────────────────────────────────────────────────────────────┐   │   │
│   │   │  DATABASE CLUSTER        [HIGH COST]    ◄── #1 COST DRIVER  │   │   │
│   │   │  • High-performance storage                                 │   │   │
│   │   │  • Replication overhead                                     │   │   │
│   │   │  • Grows with data retention                                │   │   │
│   │   └─────────────────────────────────────────────────────────────┘   │   │
│   │                              │                                      │   │
│   │                              ▼                                      │   │
│   │   ┌─────────────────────────────────────────────────────────────┐   │   │
│   │   │  OBJECT STORAGE          [LOW UNIT COST, HIGH TOTAL]        │   │   │
│   │   │  • Cheap per GB, but volume is massive                      │   │   │
│   │   │  • Media/attachments compound over time                     │   │   │
│   │   │  • Often no retention policy                                │   │   │
│   │   └─────────────────────────────────────────────────────────────┘   │   │
│   │                                                                     │   │
│   │   ┌─────────────────────────────────────────────────────────────┐   │   │
│   │   │  CROSS-REGION REPLICATION [HIGH COST]  ◄── OFTEN OVERLOOKED │   │   │
│   │   │  • Network transfer between regions                         │   │   │
│   │   │  • Duplicate storage in each region                         │   │   │
│   │   │  • Duplicate compute for active-active                      │   │   │
│   │   └─────────────────────────────────────────────────────────────┘   │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   TOP COST DRIVERS (in typical order):                                      │
│   1. Database (especially with high replication)                            │
│   2. Cross-region traffic and replication                                   │
│   3. Object storage at scale                                                │
│   4. Compute for hot paths and ML                                           │
│   5. Cache memory                                                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 2: Over-Provisioned vs Right-Sized Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│           OVER-PROVISIONED vs RIGHT-SIZED DESIGN                            │
│                                                                             │
│   OVER-PROVISIONED (Anti-Pattern)                                           │
│   ───────────────────────────────────────────────────────────               │
│                                                                             │
│   Provisioned Capacity                                                      │
│   ▲                                                                         │
│   │  ┌──────────────────────────────────────────────────────────────────    │
│   │  │                                                                      │
│   │  │        WASTED CAPACITY (80%)                                         │
│   │  │                                                                      │
│   │  │  ╭────────╮                   ╭────────╮                             │
│   │  │  │  Peak  │                   │  Peak  │                             │
│   │  │~~│~~~~~~~~│~~~~~~~~~~~~~~~~~~~│~~~~~~~~│~~~  Actual Usage            │
│   │  │  ╰────────╯    Average        ╰────────╯                             │
│   │  │                                                                      │
│   └──┴──────────────────────────────────────────────────────────▶ Time      │
│                                                                             │
│   Problems:                                                                 │
│   • Paying for 5x what you use                                              │
│   • Resources sit idle 90% of the time                                      │
│   • Creates false sense of security (never tested at real limits)           │
│                                                                             │
│   ───────────────────────────────────────────────────────────────────────   │
│                                                                             │
│   RIGHT-SIZED (Staff Pattern)                                               │
│   ───────────────────────────────────────────────────────────               │
│                                                                             │
│   Capacity                                                                  │
│   ▲                                                                         │
│   │           ╭──╮         Auto-scale for peaks   ╭──╮                      │
│   │           │░░│ ←── Max auto-scale capacity    │░░│                      │
│   │        ┌──┴──┴──┐                          ┌──┴──┴──┐                   │
│   │        │ Peak   │                          │ Peak   │                   │
│   │  ══════╪════════╪══════════════════════════╪════════╪══ Baseline        │
│   │  ~~~~~~│~~~~~~~~│~~~  Actual ~~~~~~~~~~~~~~│~~~~~~~~│~~~ (30% headroom) │
│   │        ╰────────╯    Usage                 ╰────────╯                   │
│   │                                                                         │
│   └──────────────────────────────────────────────────────────────▶ Time     │
│                                                                             │
│   Benefits:                                                                 │
│   • Pay for what you use + reasonable buffer                                │
│   • Auto-scale handles peaks without permanent cost                         │
│   • Graceful degradation for extreme events                                 │
│   • 60-80% cost savings vs over-provisioned                                 │
│                                                                             │
│   Implementation:                                                           │
│   • Baseline: Average load + 30-50% headroom                                │
│   • Auto-scale: Up to 3-5x for predicted peaks                              │
│   • Circuit breakers: Graceful degradation beyond                           │
│   • Monitoring: Alert before hitting limits                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 3: Cost vs Reliability Trade-off Curve

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              COST vs RELIABILITY TRADE-OFF CURVE                            │
│                                                                             │
│   Annual Cost                                                               │
│       ▲                                                                     │
│       │                                                        ╭───╮        │
│       │                                                       ╱│5  │        │
│  $10M ┤                                                      ╱ │9s │        │
│       │                                                     ╱  ╰───╯        │
│       │                                               ╭────╯                │
│       │                                              ╱                      │
│   $5M ┤                                        ╭────╯                       │
│       │                                   ╭───╯                             │
│       │                              ╭───╯   ╭───╮                          │
│       │                         ╭───╯        │4  │                          │
│   $1M ┤                    ╭───╯             │9s │                          │
│       │               ╭───╯                  ╰───╯                          │
│       │          ╭───╯                                                      │
│       │     ╭───╯     ╭───╮                                                 │
│ $200K ┤╭───╯          │3  │                                                 │
│       │               │9s │                                                 │
│       │    ╭───╮      ╰───╯                                                 │
│       │    │2  │                                                            │
│  $50K ┤    │9s │                                                            │
│       │    ╰───╯                                                            │
│       └─────┬─────────┬────────────┬────────────┬────────────┬───▶          │
│           99%       99.9%       99.99%       99.999%      99.9999%          │
│                                                                             │
│           AVAILABILITY                                                      │
│                                                                             │
│   KEY INSIGHT: Each additional "9" of availability roughly doubles cost     │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   STAFF QUESTION: "What availability do we actually need?"          │   │
│   │                                                                     │   │
│   │   • Internal tools: 99% (3.6 days downtime/year) - LOW COST         │   │
│   │   • Most user-facing: 99.9% (8.7 hours/year) - MODERATE COST        │   │
│   │   • Critical services: 99.99% (52 min/year) - HIGH COST             │   │
│   │   • Payment/auth: 99.999% (5 min/year) - VERY HIGH COST             │   │
│   │                                                                     │   │
│   │   Don't pay for 99.99% when 99.9% is sufficient.                    │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   THE DIMINISHING RETURNS:                                                  │
│   • 99% → 99.9%: Fix obvious single points of failure                       │
│   • 99.9% → 99.99%: Multi-region, automated failover                        │
│   • 99.99% → 99.999%: Active-active, near-zero RPO, extensive automation    │
│   • 99.999% → 99.9999%: Massive investment, specialized expertise           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 10: Cost Estimation Techniques (Back-of-Envelope)

Staff engineers must estimate costs quickly during design discussions. Here are practical techniques.

## The Cost Estimation Framework

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BACK-OF-ENVELOPE COST ESTIMATION                         │
│                                                                             │
│   STEP 1: IDENTIFY COST CATEGORIES                                         │
│   ───────────────────────────────────────────────────────────               │
│   • Compute: How many servers? How much CPU/memory per request?             │
│   • Storage: How much data? What tier? How long retained?                   │
│   • Network: How much egress? Cross-region traffic?                         │
│   • Operational: How many engineers? On-call burden?                        │
│                                                                             │
│   STEP 2: ESTIMATE QUANTITIES                                               │
│   ───────────────────────────────────────────────────────────               │
│   • Use powers of 10 (don't need exact numbers)                             │
│   • Derive from user counts × activity × data size                          │
│   • Apply multipliers for replication, retention                            │
│                                                                             │
│   STEP 3: APPLY UNIT COSTS (ROUGH ESTIMATES)                                │
│   ───────────────────────────────────────────────────────────               │
│   • Compute: ~$0.05/hour per core (varies by instance type)                 │
│   • Storage: ~$0.02/GB/month (SSD), ~$0.004/GB/month (cold)                 │
│   • Network: ~$0.01/GB intra-region, ~$0.10/GB cross-region                 │
│   • Engineer: ~$200K-400K/year fully loaded                                 │
│                                                                             │
│   STEP 4: CALCULATE AND SANITY CHECK                                        │
│   ───────────────────────────────────────────────────────────               │
│   • Total = Σ (quantity × unit cost)                                        │
│   • Compare to known systems at similar scale                               │
│   • Identify dominant cost (usually 1-2 categories)                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Example: Estimating Cost for a Messaging System

**Given:** 50M DAU, 50 messages sent per user per day, average message 1KB

**Step 1: Compute estimation**

```
// Pseudocode for compute estimation
messages_per_second = 50M users × 50 messages/day ÷ 86400 seconds
                    = 2.5B ÷ 86400
                    ≈ 29,000 messages/second

// Assume each message requires 10ms of CPU time
cpu_seconds_per_second = 29,000 × 0.01 = 290 CPU-seconds/second
servers_needed = 290 ÷ 0.7 utilization ≈ 415 servers

// At ~$50/month per core, 8-core servers
monthly_compute_cost = 415 × 8 × $50 = ~$166K/month
```

**Step 2: Storage estimation**

```
// Pseudocode for storage estimation
daily_data = 50M × 50 messages × 1KB = 2.5TB/day
monthly_data = 2.5TB × 30 = 75TB/month

// Retention: 1 year
total_storage = 75TB × 12 = 900TB

// At $0.02/GB/month for hot storage
monthly_storage_cost = 900,000 GB × $0.02 = ~$18K/month

// But only 90 days hot, rest cold at $0.004/GB
hot_storage = 75TB × 3 months = 225TB × $0.02 = $4.5K
cold_storage = 675TB × $0.004 = $2.7K
monthly_storage_cost ≈ $7K/month
```

**Step 3: Network estimation**

```
// Pseudocode for network estimation
// Each message delivered to recipient (1:1 messaging)
egress_per_day = 2.5TB (same as ingress for 1:1)

// Cross-region replication (3 regions)
cross_region_daily = 2.5TB × 2 regions = 5TB/day

// At $0.10/GB cross-region
monthly_network_cost = 5TB × 30 × $0.10 = ~$15K/month
```

**Total estimated monthly cost: ~$188K/month**
- Compute dominates at 88%
- Storage relatively cheap due to tiering
- Network significant due to cross-region

**Staff insight:** "Compute is the cost driver. I should focus optimization on reducing CPU per message—better serialization, connection pooling, or batching. Storage tiering is working; network is acceptable for global product."

## Quick Reference: Cost Order of Magnitude

| Resource | Cheap | Medium | Expensive |
|----------|-------|--------|-----------|
| **Compute** | <100 servers | 100-1000 servers | >1000 servers |
| **Storage** | <10 TB | 10-100 TB | >100 TB (PB scale) |
| **Network** | Intra-region | Cross-region | Multi-region active-active |
| **Engineering** | 1-2 people | 3-5 people | Dedicated team |

## Common Cost Multipliers

| Factor | Multiplier | When It Applies |
|--------|-----------|-----------------|
| Replication (within region) | 3x storage | High durability requirements |
| Multi-region active-active | 2-3x total | Global low-latency |
| Multi-region DR only | 1.5x storage | Disaster recovery |
| Peak vs average | 2-5x compute | Highly variable traffic |
| ML inference | 10-100x compute | Per-request model serving |
| Real-time vs batch | 5-10x compute | Stream processing |

---

# Part 11: Partial Failure Under Cost Constraints

Staff engineers must reason about what happens when systems hit their cost-based limits.

## Cost Limits Create Failure Modes

When you right-size a system, you're implicitly defining failure boundaries. Understanding these is critical.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              FAILURE MODES AT COST BOUNDARIES                               │
│                                                                             │
│   SCENARIO: System designed for 10K QPS with 50% headroom (15K capacity)    │
│                                                                             │
│   Load Level          System Behavior          User Impact                  │
│   ───────────────────────────────────────────────────────────────────────   │
│   0-10K QPS           Normal operation         None                         │
│   10K-15K QPS         Elevated latency         Slight slowdown              │
│   15K-18K QPS         Queue buildup            Timeouts begin               │
│   18K-20K QPS         Graceful degradation     Features disabled            │
│   >20K QPS            Cascading failure        Outage                       │
│                                                                             │
│   STAFF QUESTION: "Where on this curve have I designed to fail?"            │
│                                                                             │
│   THE DESIGN CHOICE:                                                        │
│   • Gold-plated: Handle 20K+ (expensive, rarely needed)                     │
│   • Right-sized: Handle 15K, degrade gracefully beyond (cost-effective)     │
│   • Under-provisioned: Handle 12K, fail at 15K (risky, cheap)               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Designing for Graceful Degradation

When cost limits are hit, systems should degrade gracefully, not catastrophically.

### Pseudocode: Load Shedding Strategy

```
// Pseudocode for cost-aware load shedding

FUNCTION handle_request(request):
    current_load = get_system_load()
    
    IF current_load < NORMAL_THRESHOLD:
        // Full service
        RETURN process_full_request(request)
    
    ELSE IF current_load < WARNING_THRESHOLD:
        // Reduce non-essential processing
        disable_optional_features(request)
        RETURN process_request(request)
    
    ELSE IF current_load < CRITICAL_THRESHOLD:
        // Aggressive shedding
        IF request.priority == LOW:
            RETURN reject_with_retry_after(request, 30 seconds)
        ELSE:
            disable_all_optional_features(request)
            RETURN process_minimal_request(request)
    
    ELSE:
        // Emergency mode: protect the system
        IF request.priority != CRITICAL:
            RETURN reject_with_503(request)
        ELSE:
            RETURN process_emergency_only(request)

// Thresholds based on cost-capacity design
NORMAL_THRESHOLD = 0.7    // 70% of provisioned capacity
WARNING_THRESHOLD = 0.85  // 85% - start shedding
CRITICAL_THRESHOLD = 0.95 // 95% - aggressive shedding
```

### Feature Degradation Priority

When costs force capacity limits, degrade in this order:

| Priority | Feature Type | Example | Degradation Action |
|----------|-------------|---------|-------------------|
| 1 (first to go) | Analytics/tracking | View counts, recommendations | Disable completely |
| 2 | Personalization | Custom feeds, A/B tests | Use cached/default |
| 3 | Secondary features | Comments, reactions | Rate limit or queue |
| 4 | Primary features | Core content delivery | Serve stale if needed |
| 5 (last resort) | Critical paths | Auth, payments | Never degrade |

## Blast Radius Containment for Cost Failures

When cost-based capacity is exceeded, failures should be contained.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              BLAST RADIUS CONTAINMENT                                       │
│                                                                             │
│   WITHOUT CONTAINMENT:                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Traffic Spike                                                      │   │
│   │       │                                                             │   │
│   │       ▼                                                             │   │
│   │  ┌─────────┐   Overload   ┌─────────┐   Cascade   ┌─────────┐      │   │
│   │  │ Service │ ──────────▶  │ Database│ ──────────▶ │All Users│      │   │
│   │  │    A    │              │ Failure │             │ Affected│      │   │
│   │  └─────────┘              └─────────┘             └─────────┘      │   │
│   │                                                                     │   │
│   │  Result: 100% of users impacted by 10% spike                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WITH CONTAINMENT:                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Traffic Spike                                                      │   │
│   │       │                                                             │   │
│   │       ▼                                                             │   │
│   │  ┌─────────┐              ┌─────────┐                               │   │
│   │  │ Service │──▶ Shed ──▶  │ 10% of  │                               │   │
│   │  │    A    │    Load      │ Users   │ ◀── Polite rejection          │   │
│   │  └────┬────┘              │ Rejected│     with retry-after          │   │
│   │       │                   └─────────┘                               │   │
│   │       ▼                                                             │   │
│   │  ┌─────────┐              ┌─────────┐                               │   │
│   │  │ Database│ ◀── Normal   │ 90% of  │                               │   │
│   │  │ Healthy │    Load      │ Users   │ ◀── Full service              │   │
│   │  └─────────┘              │ Served  │                               │   │
│   │                           └─────────┘                               │   │
│   │                                                                     │   │
│   │  Result: 10% impacted, 90% unaffected                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Pseudocode: Circuit Breaker with Cost Awareness

```
// Pseudocode for cost-aware circuit breaker

CLASS CostAwareCircuitBreaker:
    state = CLOSED
    failure_count = 0
    cost_budget_remaining = DAILY_BUDGET
    
    FUNCTION call(request):
        IF state == OPEN:
            IF time_since_open > RECOVERY_TIMEOUT:
                state = HALF_OPEN
            ELSE:
                RETURN fallback_response(request)
        
        // Check cost budget before expensive operations
        estimated_cost = estimate_request_cost(request)
        IF cost_budget_remaining < estimated_cost:
            // Cost limit reached - degrade
            log_cost_limit_reached()
            RETURN serve_from_cache_or_degrade(request)
        
        TRY:
            result = execute_request(request)
            actual_cost = measure_actual_cost(request)
            cost_budget_remaining -= actual_cost
            reset_failure_count()
            RETURN result
        CATCH Exception:
            failure_count += 1
            IF failure_count > THRESHOLD:
                state = OPEN
                open_time = now()
            RETURN fallback_response(request)
    
    FUNCTION estimate_request_cost(request):
        // Estimate based on request characteristics
        base_cost = COST_PER_REQUEST
        IF request.includes_ml_inference:
            base_cost *= 10
        IF request.crosses_region:
            base_cost *= 5
        RETURN base_cost
```

---

# Part 12: Cost Monitoring and Proactive Management

Staff engineers build systems that surface cost visibility and alert before problems occur.

## Cost Observability Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COST OBSERVABILITY ARCHITECTURE                          │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      APPLICATION LAYER                              │   │
│   │   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐            │   │
│   │   │Service A│   │Service B│   │Service C│   │Service D│            │   │
│   │   └────┬────┘   └────┬────┘   └────┬────┘   └────┬────┘            │   │
│   │        │             │             │             │                  │   │
│   │        └─────────────┼─────────────┼─────────────┘                  │   │
│   │                      │             │                                │   │
│   │                      ▼             ▼                                │   │
│   │              ┌───────────────────────────┐                          │   │
│   │              │   COST METRICS COLLECTOR  │                          │   │
│   │              │   • Request counts        │                          │   │
│   │              │   • Resource utilization  │                          │   │
│   │              │   • Cross-region traffic  │                          │   │
│   │              │   • Storage growth        │                          │   │
│   │              └───────────┬───────────────┘                          │   │
│   │                          │                                          │   │
│   │                          ▼                                          │   │
│   │              ┌───────────────────────────┐                          │   │
│   │              │   COST ATTRIBUTION ENGINE │                          │   │
│   │              │   • By feature            │                          │   │
│   │              │   • By team               │                          │   │
│   │              │   • By customer           │                          │   │
│   │              │   • By request type       │                          │   │
│   │              └───────────┬───────────────┘                          │   │
│   │                          │                                          │   │
│   │            ┌─────────────┼─────────────┐                            │   │
│   │            ▼             ▼             ▼                            │   │
│   │     ┌──────────┐  ┌──────────┐  ┌──────────┐                        │   │
│   │     │Dashboard │  │ Alerts   │  │ Budgets  │                        │   │
│   │     │& Reports │  │& On-call │  │& Limits  │                        │   │
│   │     └──────────┘  └──────────┘  └──────────┘                        │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Key Cost Metrics to Track

| Metric | What It Measures | Alert Threshold | Action |
|--------|-----------------|-----------------|--------|
| **Cost per request** | Efficiency | >2x baseline | Investigate hot paths |
| **Cost per user** | Customer efficiency | >2x average | Review heavy users |
| **Daily burn rate** | Spend velocity | >110% forecast | Review recent changes |
| **Storage growth rate** | Data accumulation | >projected | Check retention policies |
| **Cross-region traffic** | Network spend | >budget | Review replication |
| **Unutilized capacity** | Waste | >30% idle | Right-size or auto-scale |

## Pseudocode: Cost Alerting System

```
// Pseudocode for proactive cost alerting

CLASS CostAlertingSystem:
    
    FUNCTION check_cost_health():
        daily_budget = get_daily_budget()
        current_spend = get_current_daily_spend()
        projected_spend = project_daily_spend(current_spend)
        
        // Check absolute thresholds
        IF current_spend > daily_budget:
            send_alert(CRITICAL, "Daily budget exceeded", 
                       current_spend, daily_budget)
        
        ELSE IF projected_spend > daily_budget * 1.1:
            send_alert(WARNING, "On track to exceed budget by 10%",
                       projected_spend, daily_budget)
        
        // Check rate of change
        yesterday_spend = get_yesterday_spend()
        change_percent = (current_spend - yesterday_spend) / yesterday_spend
        
        IF change_percent > 0.2:  // 20% increase
            send_alert(WARNING, "Cost increased 20% vs yesterday",
                       current_spend, yesterday_spend)
            trigger_cost_investigation()
        
        // Check efficiency metrics
        cost_per_request = current_spend / get_request_count()
        baseline_cpr = get_baseline_cost_per_request()
        
        IF cost_per_request > baseline_cpr * 1.5:
            send_alert(WARNING, "Cost per request 50% above baseline",
                       cost_per_request, baseline_cpr)
            identify_expensive_requests()
    
    FUNCTION trigger_cost_investigation():
        // Automatically gather diagnostic info
        breakdown = get_cost_breakdown_by_service()
        top_changes = identify_recent_deployments()
        traffic_changes = compare_traffic_patterns()
        
        create_investigation_ticket(breakdown, top_changes, traffic_changes)
```

---

# Part 13: Capacity Planning for Cost at Scale

Staff engineers plan capacity with cost as an explicit dimension.

## The Capacity-Cost Planning Matrix

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CAPACITY-COST PLANNING MATRIX                            │
│                                                                             │
│   Scale            Capacity Need        Cost Approach        Staff Action   │
│   ──────────────────────────────────────────────────────────────────────    │
│   v1 (Launch)      Handle 1x           Over-provision OK     Ship fast      │
│                                        (learning phase)      Measure        │
│                                                                             │
│   2-5x Growth      Handle 5x peaks     Right-size + auto     Optimize top   │
│                                        Measure costs         bottlenecks    │
│                                                                             │
│   10x Growth       Handle 10x peaks    Cost-per-X target     Architecture   │
│                    With degradation    Efficiency focus      evolution      │
│                                                                             │
│   100x Growth      Handle 50x          Aggressive optimize   Replatform     │
│                    Degrade beyond      Cost is constraint    if needed      │
│                                                                             │
│   KEY INSIGHT: At each scale, the cost approach changes.                    │
│   What's acceptable at 1x is wasteful at 10x and unsustainable at 100x.     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Projecting Future Costs

### Pseudocode: Cost Projection Model

```
// Pseudocode for cost projection

CLASS CostProjectionModel:
    
    FUNCTION project_cost(current_metrics, growth_assumptions, months_ahead):
        projections = []
        
        FOR month IN range(1, months_ahead + 1):
            // Project traffic
            traffic_multiplier = (1 + growth_assumptions.monthly_traffic_growth) ^ month
            projected_traffic = current_metrics.traffic * traffic_multiplier
            
            // Project storage (compounds - never goes down)
            storage_growth = current_metrics.daily_data_growth * 30 * month
            projected_storage = current_metrics.current_storage + storage_growth
            
            // Calculate costs
            compute_cost = estimate_compute_cost(projected_traffic)
            storage_cost = estimate_storage_cost(projected_storage)
            network_cost = estimate_network_cost(projected_traffic)
            
            // Apply efficiency improvements if planned
            IF month > efficiency_milestone_month:
                compute_cost *= (1 - planned_efficiency_gain)
            
            total = compute_cost + storage_cost + network_cost
            
            projections.append({
                month: month,
                traffic: projected_traffic,
                storage: projected_storage,
                compute_cost: compute_cost,
                storage_cost: storage_cost,
                network_cost: network_cost,
                total_cost: total
            })
        
        RETURN projections
    
    FUNCTION identify_cost_cliffs(projections):
        // Find points where cost jumps significantly
        cliffs = []
        
        FOR i IN range(1, len(projections)):
            current = projections[i]
            previous = projections[i-1]
            
            // Check for storage tier transitions
            IF crosses_storage_tier(previous.storage, current.storage):
                cliffs.append({
                    month: current.month,
                    reason: "Storage tier transition",
                    cost_increase: calculate_tier_cost_jump()
                })
            
            // Check for compute scaling thresholds
            IF requires_additional_shards(previous.traffic, current.traffic):
                cliffs.append({
                    month: current.month,
                    reason: "Database sharding needed",
                    cost_increase: estimate_sharding_cost()
                })
        
        RETURN cliffs
```

## Scale Thresholds That Trigger Cost Redesign

| Threshold | What Happens | Cost Implication | Staff Action |
|-----------|-------------|------------------|--------------|
| **10K → 100K users** | Single DB stressed | Replicas needed (2-3x DB cost) | Add read replicas, optimize queries |
| **100K → 1M users** | Vertical scaling limit | Sharding needed (3-5x complexity) | Shard, may need dedicated DBA |
| **1M → 10M users** | Cache hit rate critical | Cache infra significant | Invest in caching tier |
| **10M → 100M users** | Multi-region needed | 2-3x infrastructure | Active-active or geo-sharding |
| **100M+ users** | Every inefficiency hurts | 10% improvement = $Ms | Dedicated efficiency team |

---

# Part 14: Additional Real-World Applications

## Example 4: Notification System Cost Optimization

### The Design Problem

Push notifications to 100M mobile users. Average 5 notifications per user per day.

### Cost Analysis

```
// Pseudocode for notification system cost breakdown

daily_notifications = 100M users × 5 notifications = 500M notifications/day
per_second = 500M ÷ 86,400 ≈ 5,800 notifications/second

// Push costs (third-party or internal)
push_gateway_cost = 500M × $0.000001 per push = $500/day = $15K/month

// Compute for routing and personalization
servers = 5,800 ÷ 1000 per server = 6 servers
compute_cost = 6 × $100/month = $600/month

// Storage for notification history
daily_storage = 500M × 200 bytes = 100GB/day
monthly_storage = 100GB × 30 days = 3TB
storage_cost = 3TB × $0.02/GB = $60/month

// Wait - what's the REAL cost driver?
// It's the push gateway at $15K/month
```

### Staff-Level Cost Optimization

**Problem identified:** Push gateway cost dominates.

**Optimization strategies:**

```
// Pseudocode for notification batching

// BEFORE: Send immediately (500M pushes/day)
FUNCTION send_notification_immediately(user, notification):
    push_to_device(user.device_token, notification)
    // Cost: $0.000001 per push × 500M = $500/day

// AFTER: Batch and deduplicate (reduces to 200M pushes/day)
FUNCTION send_notification_batched(user, notification):
    add_to_pending_queue(user, notification)
    
FUNCTION process_pending_queue():  // Runs every 5 minutes
    FOR user IN users_with_pending:
        notifications = get_pending(user)
        
        IF len(notifications) > 1:
            // Combine multiple into single push
            combined = combine_notifications(notifications)
            push_to_device(user.device_token, combined)
        ELSE:
            push_to_device(user.device_token, notifications[0])
        
        clear_pending(user)
    
    // Cost: Reduced by 60% through batching
    // $500/day → $200/day = $9K/month savings
```

**Trade-off:** 5-minute delay for non-urgent notifications. Urgent notifications bypass batching.

## Example 5: API Gateway Cost Optimization

### The Design Problem

API gateway handling 100K requests per second with authentication, rate limiting, and request routing.

### Cost Breakdown

```
// Pseudocode for API gateway cost analysis

requests_per_second = 100,000
daily_requests = 100K × 86,400 = 8.64B requests/day

// Compute cost
// Each request: auth check, rate limit check, routing
cpu_per_request = 2ms
cpu_seconds_per_second = 100K × 0.002 = 200 CPU-seconds/second
servers_needed = 200 ÷ 0.7 = 286 servers (8-core each)
compute_cost = 286 × 8 × $50/month = $114K/month

// Auth service calls (external IdP)
auth_calls = 8.64B × $0.00001 = $86K/day ← PROBLEM!
monthly_auth_cost = $2.6M/month

// Total: Compute $114K + Auth $2.6M = $2.7M/month
// Auth is 96% of cost!
```

### Staff-Level Optimization

```
// Pseudocode for auth token caching

// BEFORE: Check auth on every request
FUNCTION handle_request_before(request):
    auth_result = call_external_idp(request.token)  // $0.00001 each
    IF not auth_result.valid:
        RETURN 401
    process_request(request)

// AFTER: Cache auth tokens
FUNCTION handle_request_after(request):
    token_hash = hash(request.token)
    cached = cache.get(token_hash)
    
    IF cached AND cached.expires > now():
        // Cache hit - no external call
        auth_result = cached.result
    ELSE:
        // Cache miss - call IdP
        auth_result = call_external_idp(request.token)
        cache.set(token_hash, {
            result: auth_result,
            expires: now() + 5 minutes
        })
    
    IF not auth_result.valid:
        RETURN 401
    process_request(request)

// Impact analysis:
// Average session: 50 requests over 10 minutes
// Cache hit rate: 98% (only first request calls IdP)
// Auth calls reduced: 8.64B × 0.02 = 173M/day
// New auth cost: 173M × $0.00001 = $1.7K/day = $52K/month
// Savings: $2.6M - $52K = $2.55M/month
```

**Trade-off:** Cached auth means revoked tokens valid for up to 5 minutes. Acceptable for most use cases; critical apps use shorter TTL.

---

# Part 15: L6 Interview Scoring — What Interviewers Actually Evaluate

## How Cost Reasoning Is Scored

| Signal | Not Demonstrated (L5-) | Demonstrated (L5) | Strongly Demonstrated (L6) |
|--------|----------------------|-------------------|---------------------------|
| **Cost awareness** | Ignores cost entirely | Mentions cost exists | Treats cost as design input |
| **Trade-off articulation** | Makes choices without justification | Explains trade-offs when asked | Proactively discusses trade-offs |
| **Right-sizing** | Over-provisions "to be safe" | Sizes for requirements | Sizes + explains growth path |
| **Efficiency focus** | Doesn't consider | Optimizes when prompted | Identifies hot paths unprompted |
| **Operational cost** | Ignores | Acknowledges | Quantifies and designs for |
| **Sustainability** | Designs for today | Mentions future needs | Designs for multi-year evolution |

## Interview Red Flags (Cost-Related)

| Red Flag | What Interviewer Thinks | Better Approach |
|----------|------------------------|-----------------|
| "Let's just use the biggest instance type" | Can't right-size | "Let me estimate load and size appropriately" |
| "We'll optimize later" | Defers hard decisions | "Here's the cost profile; here's when optimization matters" |
| "Add caching everywhere" | Cargo-culting | "Cache hits here because read/write ratio is 100:1" |
| "Active-active in all regions" | Over-engineers | "Let me check if latency requirements justify this" |
| "Store everything forever" | Ignores data economics | "Retention policy: 90 days hot, 1 year cold, archive beyond" |
| No mention of operational cost | Incomplete thinking | "This design has N components; operational cost is..." |

## The L6 Cost Calibration Checklist

During your interview, ensure you:

☐ **Identified cost drivers** - "The main cost drivers are..."
☐ **Made explicit trade-offs** - "I'm choosing X over Y because..."
☐ **Right-sized resources** - "Based on load, I need approximately..."
☐ **Considered operational cost** - "This requires N engineers to operate..."
☐ **Planned for evolution** - "At 10x scale, I would..."
☐ **Discussed degradation** - "If we exceed capacity, we degrade by..."
☐ **Challenged over-engineering** - "We could add X, but the cost doesn't justify..."

---

# Part 16: Failure Propagation in Cost-Constrained Systems

## How Cost Decisions Create Failure Chains

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              FAILURE PROPAGATION: COST-DRIVEN CASCADES                      │
│                                                                             │
│   SCENARIO: Cost-optimized system under unexpected load                     │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  TIME 0: Traffic spike begins (2x normal)                           │   │
│   │                                                                     │   │
│   │  ┌────────────┐                                                     │   │
│   │  │ API Servers│ ← At capacity (right-sized for 1.5x)                │   │
│   │  └─────┬──────┘                                                     │   │
│   │        │ Response times increase                                    │   │
│   │        ▼                                                            │   │
│   │  TIME 5min: Clients retry (making it worse)                         │   │
│   │                                                                     │   │
│   │  ┌────────────┐                                                     │   │
│   │  │ API Servers│ ← 2.5x load now (retries)                           │   │
│   │  └─────┬──────┘                                                     │   │
│   │        │ Queue builds up                                            │   │
│   │        ▼                                                            │   │
│   │  TIME 10min: Database connections exhausted                         │   │
│   │                                                                     │   │
│   │  ┌────────────┐      ┌────────────┐                                 │   │
│   │  │ API Servers│ ───▶ │  Database  │ ← Connection limit (cost opt)   │   │
│   │  └─────┬──────┘      └────────────┘                                 │   │
│   │        │ Errors cascade                                             │   │
│   │        ▼                                                            │   │
│   │  TIME 15min: Health checks fail, cascading restart                  │   │
│   │                                                                     │   │
│   │  ┌────────────┐      ┌────────────┐                                 │   │
│   │  │ API Restart│ ───▶ │ More Load  │ ← Thundering herd               │   │
│   │  │   Storm    │      │ on Survivors│                                │   │
│   │  └────────────┘      └────────────┘                                 │   │
│   │                                                                     │   │
│   │  TIME 20min: Full outage                                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ROOT CAUSE: Right-sizing without circuit breakers                         │
│   LESSON: Cost optimization requires corresponding protection               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Breaking the Cascade: Cost-Aware Resilience

### Pseudocode: Breaking Failure Chains

```
// Pseudocode for cascade prevention in cost-optimized system

CLASS CostAwareLoadManager:
    
    FUNCTION handle_request(request):
        // 1. Admission control BEFORE processing
        IF NOT admit_request(request):
            RETURN 503 with Retry-After header
        
        // 2. Timeout budget prevents queue buildup  
        remaining_budget = request.deadline - now()
        IF remaining_budget < MIN_PROCESSING_TIME:
            RETURN 504 "Deadline exceeded"
        
        // 3. Circuit breaker for downstream
        IF downstream_circuit_breaker.is_open():
            RETURN serve_degraded_response(request)
        
        // 4. Process with resource limits
        TRY with timeout(remaining_budget):
            result = process(request)
            RETURN result
        CATCH TimeoutException:
            RETURN 504 "Processing timeout"
        CATCH DownstreamException:
            downstream_circuit_breaker.record_failure()
            RETURN serve_degraded_response(request)
    
    FUNCTION admit_request(request):
        current_queue_depth = get_queue_depth()
        current_processing = get_in_flight_count()
        
        // Reject early rather than queue forever
        IF current_queue_depth > MAX_QUEUE_DEPTH:
            RETURN false
        
        IF current_processing > MAX_CONCURRENT:
            IF request.priority < HIGH:
                RETURN false
        
        RETURN true
    
    FUNCTION serve_degraded_response(request):
        // Return cached/static/simplified response
        cached = cache.get(request.cache_key)
        IF cached:
            RETURN cached with "X-Degraded: true" header
        ELSE:
            RETURN static_fallback_response()
```

---

# Part 17: Final Verification — L6 Readiness Checklist

## Does This Chapter Meet L6 Expectations?

| L6 Criterion | Coverage | Assessment |
|--------------|----------|------------|
| **Judgment & Decision-Making** | Trade-offs explicit throughout, cost as design input | ✅ Strong |
| **Failure & Degradation Thinking** | Cascade failures, blast radius, graceful degradation | ✅ Strong |
| **Scale & Evolution** | v1 → 10x → 100x, capacity planning, cost cliffs | ✅ Strong |
| **Staff-Level Signals** | L5 vs L6 comparisons, interview scoring guide | ✅ Strong |
| **Real-World Grounding** | 5 detailed examples with pseudocode | ✅ Strong |
| **Interview Calibration** | Scoring criteria, red flags, checklist | ✅ Strong |
| **Diagrams** | 7 conceptual diagrams | ✅ Strong |

## Staff-Level Signals Covered

✅ Cost as first-class design constraint
✅ Back-of-envelope cost estimation
✅ Right-sizing vs over-provisioning reasoning
✅ Trade-off articulation with explicit "why"
✅ Partial failure behavior under cost constraints
✅ Blast radius containment
✅ Graceful degradation strategies
✅ Cost monitoring and alerting
✅ Capacity planning across scale thresholds
✅ Evolution from v1 to mature system
✅ Interview scoring criteria
✅ Common L5 mistakes and L6 corrections

## This chapter now meets Google Staff Engineer (L6) expectations.

---

# Part 18: Cloud-Native Cost Optimization (AWS Perspective)

Staff engineers must understand cloud pricing models deeply. This section covers AWS-specific patterns that apply broadly to cloud cost optimization.

## The AWS Cost Model: What You're Actually Paying For

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AWS COST MODEL: THE HIDDEN DIMENSIONS                    │
│                                                                             │
│   WHAT ENGINEERS SEE:              WHAT ACTUALLY DRIVES COST:               │
│                                                                             │
│   "We need more EC2"               EC2 instance hours                       │
│                                    + EBS storage                            │
│                                    + EBS IOPS (if provisioned)              │
│                                    + Data transfer OUT                      │
│                                    + NAT Gateway charges                    │
│                                    + Load balancer hours + LCU              │
│                                    + CloudWatch metrics & logs              │
│                                                                             │
│   "We need more database"          RDS instance hours                       │
│                                    + Storage (GP3/IO1)                      │
│                                    + IOPS (if provisioned)                  │
│                                    + Backup storage                         │
│                                    + Multi-AZ (2x instance)                 │
│                                    + Cross-region replication               │
│                                    + Data transfer                          │
│                                                                             │
│   THE SURPRISE COSTS:                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • NAT Gateway: $0.045/hour + $0.045/GB processed                   │   │
│   │  • Cross-region: $0.02/GB minimum (often 10-100x intra-region)      │   │
│   │  • CloudWatch Logs: $0.50/GB ingested + $0.03/GB stored             │   │
│   │  • API Gateway: $3.50/million requests (gets expensive fast)        │   │
│   │  • Lambda: Cheap per-request but duration × memory adds up          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Compute Cost Optimization Strategies

### EC2 Pricing Models Deep Dive

| Pricing Model | Discount | Commitment | Best For | Risk |
|--------------|----------|------------|----------|------|
| **On-Demand** | 0% | None | Variable/unpredictable | None |
| **Spot** | 60-90% | None | Fault-tolerant, interruptible | 2-min termination notice |
| **Reserved (1yr)** | 30-40% | 1 year | Predictable baseline | Locked to instance type |
| **Reserved (3yr)** | 50-60% | 3 years | Long-term stable | Highest lock-in |
| **Savings Plans** | 30-60% | 1 or 3 years | Flexible across instance types | Compute commitment |

### Staff-Level EC2 Strategy

```
// Pseudocode for optimal EC2 fleet composition

CLASS EC2FleetOptimizer:
    
    FUNCTION design_fleet(workload_profile):
        baseline_load = workload_profile.p50_load
        peak_load = workload_profile.p99_load
        
        // Layer 1: Reserved/Savings Plan for baseline
        // Cover the load you ALWAYS have
        reserved_capacity = baseline_load * 0.8  // 80% of baseline
        reserved_savings = reserved_capacity * ON_DEMAND_RATE * 0.4  // 40% savings
        
        // Layer 2: Spot for variable but fault-tolerant work
        // Background processing, batch jobs, stateless workers
        spot_capacity = (peak_load - baseline_load) * 0.5
        spot_savings = spot_capacity * ON_DEMAND_RATE * 0.7  // 70% savings
        
        // Layer 3: On-Demand for the rest
        // Peak handling, critical workloads
        on_demand_capacity = peak_load - reserved_capacity - spot_capacity
        
        // Layer 4: Auto-scaling for unexpected
        auto_scale_max = peak_load * 1.5  // 50% headroom for spikes
        
        RETURN FleetConfiguration(
            reserved: reserved_capacity,
            spot: spot_capacity,
            on_demand: on_demand_capacity,
            auto_scale_max: auto_scale_max,
            estimated_monthly_savings: reserved_savings + spot_savings
        )
```

### Graviton (ARM) Instance Optimization

```
// Pseudocode for Graviton migration ROI analysis

FUNCTION analyze_graviton_migration(current_fleet):
    graviton_compatible = []
    savings_estimate = 0
    
    FOR instance IN current_fleet:
        // Check compatibility
        workload = get_workload_type(instance)
        
        IF workload.is_x86_dependent:
            // Some workloads have x86 binary dependencies
            CONTINUE
        
        IF workload.uses_gpu:
            // Graviton doesn't support GPU
            CONTINUE
        
        // Graviton is ~20% cheaper for same performance
        // Often 40% better price-performance
        equivalent_graviton = map_to_graviton(instance.type)
        
        IF equivalent_graviton:
            current_cost = instance.count * instance.hourly_rate * 730
            graviton_cost = instance.count * equivalent_graviton.hourly_rate * 730
            
            savings = current_cost - graviton_cost
            savings_estimate += savings
            
            graviton_compatible.append({
                current: instance,
                target: equivalent_graviton,
                monthly_savings: savings,
                migration_effort: estimate_migration_effort(workload)
            })
    
    // Sort by ROI (savings / migration effort)
    graviton_compatible.sort_by(lambda x: x.monthly_savings / x.migration_effort)
    
    RETURN {
        compatible_instances: graviton_compatible,
        total_monthly_savings: savings_estimate,
        recommended_order: graviton_compatible[:10]  // Top 10 by ROI
    }

// Typical results:
// - Java/Python/Node workloads: Easy migration, 20-40% savings
// - Go workloads: Recompile and test, 20-40% savings  
// - .NET Core: Supported, 20% savings
// - Legacy binaries: May not be compatible
```

## Storage Cost Optimization

### S3 Tier Strategy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    S3 STORAGE TIER DECISION TREE                            │
│                                                                             │
│   Access Pattern                Recommended Tier       Cost/GB/month        │
│   ──────────────────────────────────────────────────────────────────────    │
│   Accessed multiple times/day   S3 Standard            $0.023               │
│   Accessed weekly               S3 Infrequent Access   $0.0125              │
│   Accessed monthly              S3 Glacier Instant     $0.004               │
│   Accessed 1-2x per year        S3 Glacier Flexible    $0.0036              │
│   Regulatory/archive only       S3 Glacier Deep        $0.00099             │
│                                                                             │
│   INTELLIGENT TIERING:                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  For objects with UNKNOWN access patterns:                          │   │
│   │  • $0.0025/1000 objects monitoring fee                              │   │
│   │  • Automatically moves between tiers based on access                │   │
│   │  • No retrieval fees for frequent/infrequent tiers                  │   │
│   │  • Best for: logs, user uploads, mixed-access data                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   RETRIEVAL COSTS (often overlooked):                                       │
│   • Glacier Instant: $0.03/GB retrieved                                     │
│   • Glacier Flexible: $0.03/GB (expedited), $0.01/GB (standard)             │
│   • Glacier Deep: $0.02/GB (standard, 12 hours)                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### S3 Lifecycle Policy Design

```
// Pseudocode for S3 lifecycle cost optimization

FUNCTION design_s3_lifecycle(bucket_type, access_patterns):
    rules = []
    
    IF bucket_type == "application_logs":
        rules.append({
            // Recent logs accessed frequently for debugging
            transition: [
                {days: 30, storage_class: "INTELLIGENT_TIERING"},
                {days: 90, storage_class: "GLACIER_IR"},
                {days: 365, storage_class: "GLACIER_DEEP_ARCHIVE"}
            ],
            expiration: {days: 2555}  // 7 years for compliance
        })
        
        // Cost impact for 100TB logs:
        // Without lifecycle: 100TB × $0.023 = $2,300/month
        // With lifecycle (80% old): 20TB × $0.023 + 80TB × $0.001 = $540/month
        // Savings: 76%
        
    ELSE IF bucket_type == "user_uploads":
        rules.append({
            // User content: unpredictable access
            transition: [
                {days: 0, storage_class: "INTELLIGENT_TIERING"}
            ],
            // No expiration - user data
        })
        
    ELSE IF bucket_type == "backups":
        rules.append({
            // Backups: rarely accessed
            transition: [
                {days: 1, storage_class: "GLACIER_IR"},    // Immediate
                {days: 30, storage_class: "GLACIER_DEEP_ARCHIVE"}
            ],
            expiration: {days: 90}  // Keep 90 days of backups
        })
        
        // Cost impact for 50TB backups:
        // Without lifecycle: 50TB × $0.023 = $1,150/month
        // With lifecycle: 50TB × $0.001 = $50/month
        // Savings: 96%
    
    RETURN rules
```

### EBS Optimization

```
// Pseudocode for EBS cost optimization

FUNCTION optimize_ebs_fleet(volumes):
    recommendations = []
    
    FOR volume IN volumes:
        metrics = get_cloudwatch_metrics(volume, days=30)
        
        // Check for oversized volumes
        used_space = metrics.disk_used_percent
        IF used_space < 50:
            recommendations.append({
                volume: volume,
                action: "RESIZE",
                current_size: volume.size,
                recommended_size: calculate_right_size(volume, used_space),
                monthly_savings: calculate_resize_savings(volume, used_space)
            })
        
        // Check for overprovisioned IOPS
        IF volume.type == "io1" OR volume.type == "io2":
            actual_iops = metrics.p99_iops
            provisioned_iops = volume.iops
            
            IF actual_iops < provisioned_iops * 0.5:
                recommendations.append({
                    volume: volume,
                    action: "REDUCE_IOPS",
                    current_iops: provisioned_iops,
                    recommended_iops: max(actual_iops * 1.3, 3000),
                    monthly_savings: (provisioned_iops - recommended_iops) * 0.065
                })
        
        // Check for GP2 to GP3 migration (free IOPS upgrade)
        IF volume.type == "gp2":
            recommendations.append({
                volume: volume,
                action: "MIGRATE_TO_GP3",
                reason: "GP3 is 20% cheaper with same baseline performance",
                monthly_savings: volume.size * 0.02  // ~20% savings
            })
        
        // Check for unattached volumes
        IF volume.state == "available":
            recommendations.append({
                volume: volume,
                action: "DELETE_OR_SNAPSHOT",
                reason: "Unattached volume incurring cost",
                monthly_cost: volume.size * volume.price_per_gb
            })
    
    RETURN sort_by_savings(recommendations)
```

## Database Cost Optimization

### RDS vs Aurora vs DynamoDB Decision Matrix

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATABASE SELECTION: COST PERSPECTIVE                     │
│                                                                             │
│   Workload                      Recommended           Cost Reasoning        │
│   ──────────────────────────────────────────────────────────────────────    │
│   Small, predictable OLTP       RDS (single-AZ)       Cheapest option       │
│   (< 10K TPS)                                                               │
│                                                                             │
│   Medium OLTP with HA           RDS Multi-AZ          2x instance cost,     │
│   (10-50K TPS)                                        but simpler           │
│                                                                             │
│   Large read-heavy OLTP         Aurora + replicas     Storage-based,        │
│   (> 50K read TPS)                                    scales reads cheaply  │
│                                                                             │
│   Unpredictable/spiky traffic   Aurora Serverless v2  Pay per ACU-second,   │
│                                                        scales to zero       │
│                                                                             │
│   High-volume key-value         DynamoDB On-Demand    Pay per request,      │
│   (simple access patterns)                            no capacity planning  │
│                                                                             │
│   High-volume with predictable  DynamoDB Provisioned  Reserved capacity,    │
│   traffic                       + Reserved Capacity   up to 77% savings     │
│                                                                             │
│   HIDDEN COSTS TO CONSIDER:                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  RDS:                                                               │   │
│   │  • Storage IOPS (io1: $0.065/IOPS/month)                            │   │
│   │  • Backup storage beyond 1x DB size                                 │   │
│   │  • Cross-region read replicas (data transfer + instance)            │   │
│   │                                                                     │   │
│   │  Aurora:                                                            │   │
│   │  • I/O charges: $0.20 per million requests                          │   │
│   │  • Can exceed instance cost for write-heavy workloads!              │   │
│   │                                                                     │   │
│   │  DynamoDB:                                                          │   │
│   │  • Scans are expensive (read entire table)                          │   │
│   │  • Global tables: 2x write cost                                     │   │
│   │  • Streams: $0.02 per 100K reads                                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### DynamoDB Capacity Optimization

```
// Pseudocode for DynamoDB capacity mode selection

FUNCTION optimize_dynamodb_table(table):
    metrics = get_table_metrics(table, days=30)
    
    // Calculate traffic patterns
    avg_wcu = metrics.consumed_wcu.average
    avg_rcu = metrics.consumed_rcu.average
    peak_wcu = metrics.consumed_wcu.p99
    peak_rcu = metrics.consumed_rcu.p99
    
    peak_to_avg_ratio = max(peak_wcu/avg_wcu, peak_rcu/avg_rcu)
    
    // Decision logic
    IF peak_to_avg_ratio > 4:
        // Highly variable - On-Demand is better
        // On-Demand: $1.25 per million WCU, $0.25 per million RCU
        on_demand_cost = calculate_on_demand_cost(metrics)
        RETURN {
            mode: "ON_DEMAND",
            reason: "Peak/avg ratio > 4x makes provisioned inefficient",
            estimated_cost: on_demand_cost
        }
    
    ELSE IF avg_wcu > 1000 OR avg_rcu > 1000:
        // High, steady volume - Provisioned with Reserved
        // Reserved capacity: up to 77% discount
        provisioned_cost = calculate_provisioned_cost(peak_wcu * 1.2, peak_rcu * 1.2)
        reserved_cost = provisioned_cost * 0.23  // 77% discount
        RETURN {
            mode: "PROVISIONED_WITH_RESERVED",
            reason: "High steady volume - reserved capacity optimal",
            wcu: peak_wcu * 1.2,
            rcu: peak_rcu * 1.2,
            estimated_cost: reserved_cost,
            savings_vs_on_demand: calculate_on_demand_cost(metrics) - reserved_cost
        }
    
    ELSE:
        // Low volume - On-Demand simpler
        RETURN {
            mode: "ON_DEMAND",
            reason: "Low volume - On-Demand simplicity worth small premium",
            estimated_cost: calculate_on_demand_cost(metrics)
        }

// Auto-scaling for provisioned mode
FUNCTION design_dynamodb_autoscaling(table, target_utilization=70):
    RETURN {
        read_scaling: {
            min_capacity: metrics.consumed_rcu.p10,
            max_capacity: metrics.consumed_rcu.p99 * 1.5,
            target_utilization: target_utilization
        },
        write_scaling: {
            min_capacity: metrics.consumed_wcu.p10,
            max_capacity: metrics.consumed_wcu.p99 * 1.5,
            target_utilization: target_utilization
        },
        scale_in_cooldown: 300,   // 5 minutes
        scale_out_cooldown: 60    // 1 minute (scale out faster than in)
    }
```

## Network Cost Optimization

### Data Transfer Cost Map

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AWS DATA TRANSFER COSTS                                  │
│                                                                             │
│   Source              Destination           Cost/GB    Notes               │
│   ──────────────────────────────────────────────────────────────────────    │
│   EC2                 Same AZ               $0.00      Free                 │
│   EC2                 Different AZ          $0.01      Each direction       │
│   EC2                 Different Region      $0.02      Egress only          │
│   EC2                 Internet              $0.09      First 10TB, then less│
│                                                                             │
│   S3                  Same Region EC2       $0.00      Free                 │
│   S3                  Different Region      $0.02      Egress               │
│   S3                  Internet              $0.09      Via CloudFront less  │
│   S3                  CloudFront            $0.00      Free origin fetch    │
│   CloudFront          Internet              $0.085     Cheaper than S3 direct│
│                                                                             │
│   NAT Gateway         Internet              $0.045     Per GB processed     │
│   NAT Gateway         (fixed cost)          $0.045/hr  32.85/month per NAT  │
│                                                                             │
│   VPC Endpoints       S3/DynamoDB           $0.00      Free (Gateway type)  │
│   VPC Endpoints       Other services        $0.01      Interface endpoints  │
│                                                                             │
│   COST OPTIMIZATION TACTICS:                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Use VPC Gateway Endpoints for S3/DynamoDB (free vs NAT cost)    │   │
│   │  2. Use CloudFront for S3 content delivery (cheaper than direct)    │   │
│   │  3. Keep chatty services in same AZ                                 │   │
│   │  4. Compress data before cross-region transfer                      │   │
│   │  5. Use AWS PrivateLink instead of public internet                  │   │
│   │  6. Batch API calls to reduce per-request overhead                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### NAT Gateway Cost Optimization

```
// Pseudocode for NAT Gateway cost reduction

FUNCTION analyze_nat_gateway_costs(vpc):
    nat_gateways = get_nat_gateways(vpc)
    total_monthly_cost = 0
    optimizations = []
    
    FOR nat IN nat_gateways:
        // Fixed cost: $0.045/hour = $32.85/month per NAT
        fixed_cost = 32.85
        
        // Processing cost: $0.045/GB
        monthly_bytes = get_nat_processed_bytes(nat, days=30)
        processing_cost = (monthly_bytes / GB) * 0.045
        
        total_cost = fixed_cost + processing_cost
        total_monthly_cost += total_cost
        
        // Analyze traffic through NAT
        traffic_breakdown = analyze_nat_traffic(nat)
        
        // Optimization 1: VPC Endpoints for AWS services
        s3_traffic = traffic_breakdown.to_s3
        dynamodb_traffic = traffic_breakdown.to_dynamodb
        
        IF s3_traffic > 100 * GB:
            optimizations.append({
                type: "ADD_S3_GATEWAY_ENDPOINT",
                current_cost: s3_traffic / GB * 0.045,
                new_cost: 0,  // Gateway endpoints are free
                monthly_savings: s3_traffic / GB * 0.045
            })
        
        IF dynamodb_traffic > 100 * GB:
            optimizations.append({
                type: "ADD_DYNAMODB_GATEWAY_ENDPOINT",
                current_cost: dynamodb_traffic / GB * 0.045,
                new_cost: 0,
                monthly_savings: dynamodb_traffic / GB * 0.045
            })
        
        // Optimization 2: Reduce NAT Gateways
        // Only need NAT per AZ for HA, not per subnet
        IF vpc.has_redundant_nats:
            optimizations.append({
                type: "CONSOLIDATE_NAT_GATEWAYS",
                current_count: len(nat_gateways),
                recommended_count: len(vpc.availability_zones),
                monthly_savings: (len(nat_gateways) - len(vpc.availability_zones)) * 32.85
            })
    
    RETURN {
        current_monthly_cost: total_monthly_cost,
        optimizations: optimizations,
        potential_savings: sum(o.monthly_savings for o in optimizations)
    }
```

## Serverless Cost Optimization

### Lambda Optimization Strategies

```
// Pseudocode for Lambda cost optimization

FUNCTION optimize_lambda_function(function):
    metrics = get_lambda_metrics(function, days=30)
    
    // Current cost calculation
    // Lambda: $0.20 per 1M requests + $0.0000166667 per GB-second
    invocations = metrics.invocations
    avg_duration_ms = metrics.avg_duration
    memory_mb = function.memory
    
    current_gb_seconds = invocations * (avg_duration_ms / 1000) * (memory_mb / 1024)
    current_cost = (invocations / 1_000_000) * 0.20 + current_gb_seconds * 0.0000166667
    
    optimizations = []
    
    // Optimization 1: Right-size memory
    // More memory = faster execution (often), so find optimal point
    memory_tests = run_power_tuning(function)
    optimal_memory = find_cost_optimal_memory(memory_tests)
    
    IF optimal_memory != memory_mb:
        new_duration = memory_tests[optimal_memory].avg_duration
        new_gb_seconds = invocations * (new_duration / 1000) * (optimal_memory / 1024)
        new_cost = (invocations / 1_000_000) * 0.20 + new_gb_seconds * 0.0000166667
        
        optimizations.append({
            type: "RESIZE_MEMORY",
            current_memory: memory_mb,
            optimal_memory: optimal_memory,
            current_cost: current_cost,
            new_cost: new_cost,
            monthly_savings: current_cost - new_cost
        })
    
    // Optimization 2: Arm64 (Graviton)
    // 20% cheaper per GB-second, often faster
    IF function.architecture == "x86_64" AND is_arm_compatible(function):
        graviton_cost = current_cost * 0.80  // 20% cheaper
        optimizations.append({
            type: "MIGRATE_TO_ARM64",
            savings_percent: 20,
            monthly_savings: current_cost * 0.20
        })
    
    // Optimization 3: Provisioned Concurrency analysis
    // Avoid cold starts but costs money even when idle
    cold_starts = metrics.cold_start_count
    cold_start_percent = cold_starts / invocations * 100
    
    IF cold_start_percent > 10 AND function.latency_sensitive:
        // Might benefit from provisioned concurrency
        concurrent_executions = metrics.max_concurrent
        provisioned_cost = concurrent_executions * 0.000004646 * 86400 * 30
        cold_start_latency_cost = estimate_business_impact(cold_starts)
        
        IF cold_start_latency_cost > provisioned_cost:
            optimizations.append({
                type: "ADD_PROVISIONED_CONCURRENCY",
                concurrent_executions: concurrent_executions,
                monthly_cost: provisioned_cost,
                cold_start_reduction: "99%+"
            })
    
    // Optimization 4: Batch processing
    IF function.trigger == "SQS" OR function.trigger == "KINESIS":
        current_batch_size = function.batch_size
        IF current_batch_size < 100:
            // Larger batches = fewer invocations = lower cost
            optimizations.append({
                type: "INCREASE_BATCH_SIZE",
                current_batch_size: current_batch_size,
                recommended_batch_size: min(current_batch_size * 5, 10000),
                reasoning: "Amortize invocation cost across more records"
            })
    
    RETURN optimizations

// Power tuning: test memory/duration trade-off
FUNCTION run_power_tuning(function):
    results = {}
    
    FOR memory IN [128, 256, 512, 1024, 2048, 3008, 10240]:
        // Run test invocations at each memory level
        test_results = invoke_with_memory(function, memory, iterations=100)
        
        avg_duration = test_results.avg_duration
        cost_per_invocation = (avg_duration / 1000) * (memory / 1024) * 0.0000166667
        
        results[memory] = {
            avg_duration: avg_duration,
            cost_per_invocation: cost_per_invocation
        }
    
    RETURN results
```

## Real-World AWS Cost Incident Case Study

### Case Study: The $100K/Month NAT Gateway Surprise

**Background:**
A startup migrated from on-premise to AWS. Their architecture:
- 500 EC2 instances across 3 AZs
- All instances in private subnets
- NAT Gateways for internet access
- Heavy use of S3 for data lake operations

**The Problem:**
First AWS bill: $150K. Expected: $50K.

**Investigation:**

```
// Pseudocode for cost investigation

FUNCTION investigate_unexpected_costs(account, expected, actual):
    variance = actual - expected
    cost_breakdown = get_cost_explorer_breakdown(account)
    
    // Find top contributors to variance
    surprises = []
    FOR service, cost IN cost_breakdown:
        IF cost > expected_by_service[service] * 1.5:
            surprises.append({
                service: service,
                expected: expected_by_service[service],
                actual: cost,
                variance: cost - expected_by_service[service]
            })
    
    RETURN sorted(surprises, by=variance, descending=True)

// Results:
// 1. NAT Gateway: Expected $3K, Actual $45K (15x over!)
// 2. S3 Data Transfer: Expected $5K, Actual $35K
// 3. Data Transfer: Expected $10K, Actual $25K
```

**Root Cause Analysis:**

```
// NAT Gateway breakdown
daily_s3_traffic = 1TB  // Data lake operations
daily_internet_traffic = 500GB  // API calls, updates

// Cost calculation BEFORE optimization:
// NAT fixed: 9 NAT Gateways × $32.85 = $296/month
// NAT processing: 45TB × $0.045 = $2,025/month... wait, that's not $45K

// Deeper investigation:
// 500 instances × average 3GB/day to S3 = 1.5TB/day
// S3 traffic going through NAT = 1.5TB × 30 days × $0.045 = $2,025
// BUT: S3 data transfer also charged separately!
// S3 PUT: 1.5TB/day = 45TB/month
// Actually, they were downloading FROM S3, not just uploading
// Download through NAT: 45TB × $0.045 = $2,025/month NAT processing
// PLUS S3 charges for cross-region (buckets in different region): 45TB × $0.02 = $900/month

// Wait, still doesn't add up to $45K...
// Found: CloudWatch Logs going to internet endpoint via NAT!
// 30TB of logs per month × $0.045 = $1,350/month NAT
// Plus CloudWatch ingestion: 30TB × $0.50/GB = $15K/month

// Total unexpected costs:
// - Logs via NAT instead of VPC endpoint: $1,350
// - CloudWatch ingestion nobody tracked: $15K
// - S3 cross-region instead of same-region: $900
// - Missing S3 VPC Gateway Endpoint: $2,025 NAT processing
```

**Resolution:**

| Issue | Fix | Savings |
|-------|-----|---------|
| S3 traffic through NAT | Added S3 Gateway Endpoint | $2,025/month |
| CloudWatch Logs excessive | Reduced log verbosity, added sampling | $12K/month |
| Cross-region S3 | Moved buckets to same region | $900/month |
| Redundant NAT Gateways | Consolidated from 9 to 3 | $200/month |
| EC2 On-Demand | Added Savings Plans | $15K/month |

**Total Monthly Savings: $30K (from $150K to $120K)**

**Staff-Level Lesson:**
"We assumed AWS networking would work like on-premise—traffic between our servers and AWS services was 'internal.' Wrong. Every byte through NAT costs money. Every byte across regions costs money. AWS charges for everything, and the defaults are expensive. Staff engineers validate cost assumptions before migration."

---

# Part 19: Advanced Cost Optimization Patterns

## Pattern 1: Tiered Architecture for Cost

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TIERED ARCHITECTURE FOR COST                             │
│                                                                             │
│   TIER 1: EDGE (Cheapest per request)                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  CloudFront + Lambda@Edge + S3                                      │   │
│   │  • Static content: $0.085/GB + minimal compute                      │   │
│   │  • Simple API responses: $0.0000006/request                         │   │
│   │  • Cache hits: Near-zero marginal cost                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                        │ Cache miss                                         │
│                        ▼                                                    │
│   TIER 2: API LAYER (Low cost, stateless)                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  API Gateway + Lambda OR ALB + Fargate                              │   │
│   │  • Lambda: $0.20/1M requests + compute                              │   │
│   │  • Fargate: ~$0.04/vCPU/hour                                        │   │
│   │  • Scales to zero (Lambda) or near-zero (Fargate Spot)              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                        │ Needs data                                         │
│                        ▼                                                    │
│   TIER 3: DATA LAYER (Medium cost, stateful)                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  ElastiCache + DynamoDB + RDS                                       │   │
│   │  • Cache hits: $0.00000X per read                                   │   │
│   │  • DynamoDB: $0.25/1M reads, $1.25/1M writes                        │   │
│   │  • RDS: Fixed instance cost + storage + IOPS                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                        │ Needs heavy compute                                │
│                        ▼                                                    │
│   TIER 4: PROCESSING LAYER (High cost, compute-intensive)                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  EC2 Spot + EMR + SageMaker                                         │   │
│   │  • Batch processing: Spot instances (70% cheaper)                   │   │
│   │  • ML inference: SageMaker endpoints or Spot                        │   │
│   │  • Data processing: EMR Spot fleets                                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   PRINCIPLE: Push work to the cheapest tier that can handle it             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Pattern 2: Cost-Aware Request Routing

```
// Pseudocode for cost-aware routing

CLASS CostAwareRouter:
    
    FUNCTION route_request(request):
        // Estimate cost of different processing paths
        paths = [
            {
                name: "cache_hit",
                cost: 0.000001,  // Negligible
                latency: 5,      // ms
                available: check_cache(request)
            },
            {
                name: "lambda",
                cost: 0.0000002 + (estimated_duration * 0.0000166667),
                latency: 50 + cold_start_probability * 200,
                available: true
            },
            {
                name: "fargate",
                cost: 0.00001,   // Amortized container cost
                latency: 20,
                available: fargate_capacity_available()
            },
            {
                name: "ec2_reserved",
                cost: 0.000005,  // Already paid for
                latency: 15,
                available: ec2_reserved_capacity_available()
            },
            {
                name: "ec2_spot",
                cost: 0.000003,  // Cheap but interruptible
                latency: 15,
                available: spot_capacity_available()
            },
            {
                name: "ec2_ondemand",
                cost: 0.00002,   // Most expensive
                latency: 15,
                available: true  // Always available
            }
        ]
        
        // Filter to available paths
        available_paths = filter(paths, lambda p: p.available)
        
        // Choose based on request priority and cost
        IF request.priority == "critical":
            // Minimize latency, ignore cost
            RETURN choose_lowest_latency(available_paths)
        
        ELSE IF request.priority == "batch":
            // Minimize cost, accept higher latency
            RETURN choose_lowest_cost(available_paths)
        
        ELSE:
            // Balance cost and latency
            RETURN choose_best_value(available_paths, 
                                     latency_weight=0.3, 
                                     cost_weight=0.7)
```

## Pattern 3: Spot Instance Management for Production

```
// Pseudocode for production Spot management

CLASS SpotInstanceManager:
    
    FUNCTION maintain_capacity(desired_capacity, critical=false):
        current_spot = get_spot_instances()
        current_od = get_on_demand_instances()
        
        IF critical:
            // Don't use Spot for critical workloads
            RETURN scale_on_demand(desired_capacity)
        
        // Strategy: Diversify across instance types and AZs
        // Reduces chance of simultaneous interruption
        instance_pools = [
            ("m5.large", "us-east-1a"),
            ("m5.large", "us-east-1b"),
            ("m5a.large", "us-east-1a"),
            ("m5a.large", "us-east-1b"),
            ("m5n.large", "us-east-1a"),
            ("m5n.large", "us-east-1b"),
        ]
        
        // Request capacity across pools
        allocation_strategy = "capacity-optimized"  // Least likely to interrupt
        
        target_spot = desired_capacity * 0.8  // 80% Spot
        target_od = desired_capacity * 0.2    // 20% On-Demand baseline
        
        // Launch Spot fleet
        spot_fleet = create_spot_fleet_request(
            target_capacity=target_spot,
            instance_pools=instance_pools,
            allocation_strategy=allocation_strategy,
            on_demand_base_capacity=target_od
        )
        
        RETURN spot_fleet
    
    FUNCTION handle_spot_interruption(instance):
        // 2-minute warning received
        
        // 1. Drain connections
        remove_from_load_balancer(instance)
        
        // 2. Complete in-flight requests (with timeout)
        wait_for_drain(timeout=90 seconds)
        
        // 3. Checkpoint any state
        checkpoint_state(instance)
        
        // 4. Signal replacement needed
        request_replacement_capacity()
        
        // Note: Don't wait for spot to terminate - 
        // start replacement immediately
    
    FUNCTION design_spot_architecture():
        // Key principles for Spot in production:
        RETURN {
            stateless: "Store no local state - use EFS/S3/Redis",
            diversified: "Use multiple instance types and AZs",
            replaceable: "Any instance can die any time",
            observable: "Know when interruptions happen",
            fallback: "Always have On-Demand fallback ready"
        }
```

## Pattern 4: Cost-Aware Caching Strategy

```
// Pseudocode for cost-optimized caching

CLASS CostAwareCacheManager:
    
    FUNCTION should_cache(item, access_pattern):
        // Calculate cost of caching vs not caching
        
        cache_cost_per_month = (item.size_bytes / GB) * cache_price_per_gb
        
        // If not cached, what's the origin cost?
        origin_cost_per_access = estimate_origin_cost(item)
        // DynamoDB read: $0.25/1M = $0.00000025
        // RDS query: ~$0.0001 (amortized instance + IOPS)
        // S3 GET: $0.0004/1000 = $0.0000004
        // External API: $0.001 (varies widely)
        
        expected_accesses_per_month = predict_access_frequency(item, access_pattern)
        
        origin_cost_per_month = origin_cost_per_access * expected_accesses_per_month
        
        // Cache if savings > cost
        net_savings = origin_cost_per_month - cache_cost_per_month
        
        RETURN {
            should_cache: net_savings > 0,
            cache_cost: cache_cost_per_month,
            origin_cost: origin_cost_per_month,
            net_savings: net_savings
        }
    
    FUNCTION optimize_cache_ttl(item, access_pattern):
        // Longer TTL = higher cache hit rate = lower origin cost
        // But also = more memory usage = higher cache cost
        // And = staler data = potential correctness issues
        
        staleness_tolerance = item.staleness_tolerance  // e.g., 60 seconds
        access_frequency = access_pattern.requests_per_minute
        
        IF access_frequency > 100:
            // High frequency: short TTL OK, still good hit rate
            ttl = min(staleness_tolerance, 60)
        ELSE IF access_frequency > 10:
            // Medium frequency: longer TTL for hit rate
            ttl = min(staleness_tolerance, 300)
        ELSE:
            // Low frequency: may not be worth caching
            IF not should_cache(item, access_pattern).should_cache:
                ttl = 0  // Don't cache
            ELSE:
                ttl = staleness_tolerance
        
        RETURN ttl
    
    FUNCTION design_cache_tiers():
        // Multi-tier caching for cost optimization
        RETURN {
            L1: {
                type: "Application memory",
                size: "100MB per instance",
                latency: "<1ms",
                cost: "Free (already paid for EC2)",
                ttl: "10-60 seconds",
                use_for: "Hottest 1000 items"
            },
            L2: {
                type: "ElastiCache Redis",
                size: "10-100GB cluster",
                latency: "1-5ms",
                cost: "$0.017/GB/hour (r6g.large)",
                ttl: "1-10 minutes",
                use_for: "Hot items (top 10%)"
            },
            L3: {
                type: "DynamoDB DAX",
                size: "Auto-managed",
                latency: "1-5ms",
                cost: "$0.269/hour per node",
                ttl: "5 minutes default",
                use_for: "DynamoDB read-heavy patterns"
            },
            L4: {
                type: "CloudFront",
                size: "Unlimited",
                latency: "<50ms global",
                cost: "$0.085/GB transfer",
                ttl: "Minutes to hours",
                use_for: "Static/semi-static content"
            }
        }
```

---

# Part 20: Cost Governance and FinOps Practices

## Building a Cost-Aware Engineering Culture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FINOPS MATURITY MODEL                                    │
│                                                                             │
│   LEVEL 1: REACTIVE (Most organizations start here)                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Monthly surprise when bill arrives                               │   │
│   │  • No cost visibility by team or service                            │   │
│   │  • No budgets or alerts                                             │   │
│   │  • Engineers don't see cost impact of decisions                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   LEVEL 2: INFORMED (Basic visibility)                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Cost Explorer used monthly                                       │   │
│   │  • Basic tagging in place                                           │   │
│   │  • Budget alerts configured                                         │   │
│   │  • Teams aware of their spend (monthly)                             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   LEVEL 3: OPTIMIZED (Active management)                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Real-time cost dashboards                                        │   │
│   │  • Reserved capacity planning                                       │   │
│   │  • Regular optimization reviews                                     │   │
│   │  • Cost targets per team/service                                    │   │
│   │  • Cost in architecture reviews                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   LEVEL 4: OPERATIONALIZED (Cost as code)                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Cost estimates in CI/CD pipelines                                │   │
│   │  • Automated rightsizing recommendations                            │   │
│   │  • Unit economics tracked (cost per user/transaction)               │   │
│   │  • Teams own and optimize their costs                               │   │
│   │  • Cost anomaly detection and auto-remediation                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Staff-Level Cost Governance Practices

### Tagging Strategy for Cost Attribution

```
// Pseudocode for tagging policy

REQUIRED_TAGS = {
    "Environment": ["production", "staging", "development", "sandbox"],
    "Team": validated_team_list,
    "Service": validated_service_list,
    "CostCenter": validated_cost_centers,
    "Owner": email_pattern
}

FUNCTION enforce_tagging_policy(resource):
    missing_tags = []
    invalid_tags = []
    
    FOR tag_key, valid_values IN REQUIRED_TAGS:
        IF tag_key NOT IN resource.tags:
            missing_tags.append(tag_key)
        ELSE IF valid_values AND resource.tags[tag_key] NOT IN valid_values:
            invalid_tags.append({
                key: tag_key,
                value: resource.tags[tag_key],
                valid: valid_values
            })
    
    IF missing_tags OR invalid_tags:
        IF resource.is_new:
            // Block creation
            RETURN deny_with_message(
                "Resource must have required tags: " + missing_tags
            )
        ELSE:
            // Existing resource - notify and schedule remediation
            notify_owner(resource, missing_tags, invalid_tags)
            schedule_auto_tag_remediation(resource)
    
    RETURN allow

// AWS implementation: AWS Organizations SCP + AWS Config rules

FUNCTION calculate_cost_by_tag(tag_key, tag_value, time_range):
    // Use Cost Explorer API
    cost_data = cost_explorer.get_cost_and_usage(
        time_period=time_range,
        granularity="DAILY",
        filter={
            "Tags": {
                "Key": tag_key,
                "Values": [tag_value]
            }
        },
        group_by=[
            {"Type": "DIMENSION", "Key": "SERVICE"}
        ]
    )
    
    RETURN cost_data

// Generate team cost reports
FUNCTION generate_team_cost_report(team, month):
    cost_by_service = calculate_cost_by_tag("Team", team, month)
    cost_by_environment = calculate_cost_by_tag("Team", team, month, 
                                                 group_by="Environment")
    
    // Compare to previous month
    previous_month = month - 1
    previous_cost = calculate_cost_by_tag("Team", team, previous_month)
    
    change_percent = (cost_by_service.total - previous_cost.total) / previous_cost.total
    
    RETURN {
        team: team,
        month: month,
        total_cost: cost_by_service.total,
        by_service: cost_by_service,
        by_environment: cost_by_environment,
        vs_previous_month: change_percent,
        budget: get_team_budget(team),
        budget_remaining: get_team_budget(team) - cost_by_service.total
    }
```

### Cost Anomaly Detection

```
// Pseudocode for cost anomaly detection

CLASS CostAnomalyDetector:
    
    FUNCTION detect_anomalies(cost_data, sensitivity=MEDIUM):
        anomalies = []
        
        FOR service IN cost_data.services:
            // Get historical baseline
            historical = get_historical_cost(service, days=90)
            
            // Calculate expected range
            mean = historical.mean()
            std_dev = historical.std_dev()
            
            // Sensitivity thresholds
            thresholds = {
                HIGH: 2,      // 2 standard deviations
                MEDIUM: 3,    // 3 standard deviations
                LOW: 4        // 4 standard deviations
            }
            
            threshold = thresholds[sensitivity]
            upper_bound = mean + (std_dev * threshold)
            lower_bound = mean - (std_dev * threshold)
            
            current_cost = cost_data.get_cost(service, today)
            
            IF current_cost > upper_bound:
                anomalies.append({
                    service: service,
                    type: "SPIKE",
                    current: current_cost,
                    expected: mean,
                    deviation: (current_cost - mean) / std_dev,
                    severity: classify_severity(current_cost - mean)
                })
            
            ELSE IF current_cost < lower_bound AND lower_bound > 0:
                // Unexpected drop might indicate broken service
                anomalies.append({
                    service: service,
                    type: "DROP",
                    current: current_cost,
                    expected: mean,
                    deviation: (mean - current_cost) / std_dev,
                    severity: "INFO"  // Usually less urgent
                })
        
        RETURN anomalies
    
    FUNCTION investigate_anomaly(anomaly):
        // Automated investigation
        investigation = {
            anomaly: anomaly,
            possible_causes: []
        }
        
        // Check for deployments
        recent_deployments = get_deployments(
            service=anomaly.service,
            time_range=last_24_hours
        )
        IF recent_deployments:
            investigation.possible_causes.append({
                type: "DEPLOYMENT",
                details: recent_deployments,
                likelihood: HIGH
            })
        
        // Check for traffic changes
        traffic = get_traffic_metrics(anomaly.service, last_24_hours)
        IF traffic.change > 50%:
            investigation.possible_causes.append({
                type: "TRAFFIC_CHANGE",
                details: traffic,
                likelihood: HIGH
            })
        
        // Check for resource changes
        resource_changes = get_resource_changes(anomaly.service, last_24_hours)
        IF resource_changes:
            investigation.possible_causes.append({
                type: "RESOURCE_CHANGE",
                details: resource_changes,
                likelihood: HIGH
            })
        
        // Check for AWS pricing changes
        pricing_changes = check_aws_pricing_changes(anomaly.service)
        IF pricing_changes:
            investigation.possible_causes.append({
                type: "PRICING_CHANGE",
                details: pricing_changes,
                likelihood: MEDIUM
            })
        
        RETURN investigation
```

---

# Brainstorming Questions

## Section A: Cost Identification and Awareness

1. For a system you work on, what are the top 3 cost drivers? How do you know?

2. "Which part of this system dominates cost?" — Can you answer this for systems you've built?

3. What costs are invisible in your current work? (Operational burden, on-call, complexity tax)

4. How does cost scale with usage in your system? Linear? Superlinear? Sublinear?

5. What would you remove if your infrastructure budget were cut in half?

6. How would you estimate the cost of a new feature before building it?

7. What's the cost-per-user of your current system? How does it compare to industry benchmarks?

## Section B: Trade-off Reasoning

8. Think of a recent architecture decision. What was the cost trade-off? Was it explicit?

9. When have you seen over-engineering add cost without proportional benefit?

10. When have you seen under-engineering cause expensive incidents?

## Section G: AWS-Specific Cost Questions

36. What percentage of your EC2 fleet could run on Spot instances? What's stopping you?

37. How much of your S3 storage is in Standard tier vs. should be in Glacier?

38. What's your NAT Gateway bill? Could VPC Endpoints eliminate most of it?

39. Are you using GP2 EBS volumes? Have you considered GP3 (20% cheaper)?

40. What's your Reserved Instance / Savings Plan coverage? Is it optimal?

41. How much are you spending on cross-region data transfer? Is it necessary?

42. What's your CloudWatch Logs bill? Are you ingesting logs you never query?

43. Have you evaluated Graviton instances? What's the migration effort vs. savings?

44. Are your Lambda functions right-sized for memory? Have you run power tuning?

45. Is your DynamoDB On-Demand or Provisioned? Which is cheaper for your access pattern?

46. What's the ratio of production to non-production spend? Is it appropriate?

47. How long do your non-production environments run? Do they run 24/7 unnecessarily?

48. What AWS services are you paying for that you're not using?

49. Have you evaluated your data transfer architecture for cost? (Same-AZ vs cross-AZ)

50. What would happen to your bill if traffic doubled? Would cost double, or more?

11. How do you balance "build for the future" vs "don't over-engineer"?

12. What's the most expensive operational burden you've experienced? How could architecture have reduced it?

13. If you had to reduce your system's cost by 50%, what would you sacrifice first? Second? Third?

14. When is it worth paying 2x more for 20% better latency? When is it not?

## Section C: Sustainability and Evolution

15. Which of your systems would you describe as "sustainable"? Why?

16. Which systems are at risk of becoming unsustainable? What would change that?

17. What's the longest-lived system you've worked on? How has its cost evolved?

18. If your team halved in size, which systems would suffer most? What does that tell you?

19. What's the simplest architecture that would meet your current requirements?

20. At what traffic level would your current architecture become unsustainable? What would you change?

## Section D: Failure and Degradation

21. If your system hits its cost-based capacity limit, what happens? Have you tested this?

22. What's the blast radius when a cost-optimized component fails?

23. How would your system degrade under 3x normal load without scaling up?

24. What features would you disable first if you needed to reduce compute by 50% immediately?

25. Have you ever experienced a cascading failure caused by cost optimization? What happened?

## Section E: Estimation and Planning

26. How accurately can you estimate the monthly cost of a system from its architecture diagram?

27. What cost multipliers do you apply for multi-region, high-availability, or ML-based features?

28. How do you project costs 6 months, 1 year, and 2 years out?

29. At what point does it make sense to invest engineering time in optimization vs. just paying more?

30. How do you budget for unexpected traffic spikes?

## Section F: Interview Preparation

31. How would you explain the cost trade-offs in your design during an interview?

32. If an interviewer asked "How would you reduce the cost of this design by 50%?", what would you say?

33. What phrases would signal Staff-level cost thinking to an interviewer?

34. How do you balance discussing cost without seeming like you're cutting corners on reliability?

35. What's an example of a cost decision you made that had unexpected consequences?

---

# Homework Exercises

## Exercise 1: Cost Analysis of Existing System

**Objective:** Practice identifying cost drivers in real systems.

Choose a system you know well (from work or open-source).

**Part A:** Identify the major cost drivers:
- What's the compute cost driven by?
- What's the storage cost driven by?
- What's the network cost driven by?
- What's the operational cost?

**Part B:** Propose 3 ways to reduce cost by 30%:
- What would you trade off for each approach?
- What's the risk of each approach?
- Which would you recommend and why?

**Part C:** Calculate the ROI of each optimization:
- Engineering time required
- Expected savings
- Payback period

**Deliverable:** 2-page analysis with specific recommendations and ROI calculations.

---

## Exercise 2: Back-of-Envelope Cost Estimation

**Objective:** Practice rapid cost estimation during design.

For each of the following systems, estimate monthly infrastructure cost:

**System A: URL Shortener**
- 100M URLs created per month
- 10B redirects per month
- 3-year URL retention

**System B: Chat Application**
- 10M DAU
- 50 messages per user per day
- 1-year message history
- Real-time delivery

**System C: Video Streaming Platform**
- 5M DAU
- 2 hours average watch time
- 720p average quality
- Global CDN distribution

**For each, calculate:**
- Compute cost
- Storage cost
- Network cost
- Total monthly cost
- Cost per user

**Deliverable:** Spreadsheet with calculations and assumptions documented.

---

## Exercise 3: Redesign for Cost Reduction

**Objective:** Practice cost-aware architectural thinking.

Take a system design problem (news feed, rate limiter, notification system, or messaging system).

**Part A:** Design a "gold-plated" version:
- Maximum reliability (99.99%+)
- Maximum features
- Best possible latency
- No cost constraints

**Part B:** Identify the cost drivers:
- Rank components by cost
- Identify which costs scale with traffic vs. data vs. time

**Part C:** Redesign to reduce cost by 50%:
- What features do you simplify or remove?
- What reliability trade-offs do you make?
- What latency trade-offs do you accept?
- Explicitly state each trade-off and justify it

**Part D:** Redesign for a startup with 1/10th the budget:
- What's the minimum viable architecture?
- What would you add as you scale?

**Deliverable:** Four architecture diagrams with cost comparison and trade-off analysis.

---

## Exercise 4: Redundancy Analysis

**Objective:** Practice evaluating whether redundancy is justified.

Review a system architecture (yours or a published case study).

**For each redundant component, complete this table:**

| Component | Failure Mode Protected | Probability of Failure | Cost of Redundancy | Cost of Failure | Justified? |
|-----------|----------------------|----------------------|-------------------|-----------------|------------|
| Example: 3x DB replicas | Single replica failure | 1%/month | $5K/month | $100K revenue loss | Yes |

**Analysis questions:**
- Are there redundant components that aren't justified?
- Are there single points of failure that should have redundancy?
- What's the total cost of redundancy in this system?
- Could you achieve similar reliability at lower cost?

**Deliverable:** Completed table with recommendations.

---

## Exercise 5: Capacity Planning Simulation

**Objective:** Practice projecting costs across growth scenarios.

Given a system with current metrics:
- 1M DAU
- 10K requests/second
- 10TB storage
- $50K/month infrastructure cost

**Scenario A:** 5x growth in 12 months
- Project monthly costs for each month
- Identify when architectural changes are needed
- Calculate total 12-month spend

**Scenario B:** 10x growth in 18 months
- Same analysis
- Identify cost cliffs (points where cost jumps significantly)

**Scenario C:** Flat growth but 30% cost reduction mandate
- Propose optimization plan
- Quantify savings from each optimization
- Identify risks

**Deliverable:** Spreadsheet with projections and written analysis.

---

## Exercise 6: Cost-Aware Interview Practice

**Objective:** Practice demonstrating cost awareness in interview settings.

**Part A:** Practice a system design problem (45 minutes):
- Pick: Design a news feed, messaging system, or notification system
- State cost as one of your design considerations early
- Identify the top 3 cost drivers in your design
- Make at least two trade-offs explicitly based on cost
- Discuss what you would change at different budget levels

**Part B:** Record yourself or have a partner evaluate on:
- Did you mention cost proactively or only when asked?
- Did you quantify costs (even roughly)?
- Did you articulate trade-offs clearly?
- Did you avoid over-engineering?
- Did you consider operational cost, not just infrastructure?

**Part C:** Self-critique:
- What L6 cost signals did you demonstrate?
- What did you miss?
- How would you improve next time?

**Deliverable:** Recording or written self-assessment with improvement plan.

---

## Exercise 7: Sustainability Audit

**Objective:** Practice evaluating long-term system sustainability.

For a system you operate (or a case study):

**Part A: Measure current sustainability:**
- How much engineering time goes to maintenance vs. features?
- What's the on-call burden (pages/week, MTTR)?
- How long does it take a new team member to become productive?
- What's the bus factor (how many people understand the system)?
- What's the ratio of cost to value delivered?

**Part B: Identify sustainability risks:**
- What would break first under 2x load?
- What knowledge is siloed?
- What dependencies are fragile?
- What technical debt is accumulating?
- What operational toil is growing?

**Part C: Propose improvements:**
- What would make this system more sustainable?
- What's the cost of those improvements?
- What's the cost of NOT making them (2-year projection)?
- Prioritize by ROI

**Deliverable:** Sustainability audit document with prioritized recommendations.

---

## Exercise 8: Graceful Degradation Design

**Objective:** Practice designing cost-aware degradation strategies.

For a system of your choice:

**Part A:** Identify degradation tiers:

| Load Level | System State | Features Disabled | User Impact |
|------------|-------------|-------------------|-------------|
| 0-70% | Normal | None | None |
| 70-85% | Elevated | ? | ? |
| 85-95% | Warning | ? | ? |
| 95-100% | Critical | ? | ? |
| >100% | Emergency | ? | ? |

**Part B:** Design the degradation logic:
- Write pseudocode for admission control
- Write pseudocode for feature toggling
- Explain how you'd monitor and alert

**Part C:** Test the design:
- Describe how you'd validate the degradation works
- What could go wrong?
- How would you prevent cascading failures?

**Deliverable:** Completed table, pseudocode, and test plan.

---

## Exercise 9: Cost Monitoring Design

**Objective:** Practice designing cost observability.

Design a cost monitoring system for a mid-sized platform:

**Requirements:**
- Track cost by service, feature, and team
- Alert on cost anomalies
- Project future costs
- Support cost optimization decisions

**Your design should include:**
- What metrics to collect
- How to attribute costs
- Alert thresholds and escalation
- Dashboard requirements
- Integration with capacity planning

**Pseudocode should cover:**
- Cost aggregation
- Anomaly detection
- Projection model

**Deliverable:** Design document with architecture diagram and pseudocode.

---

## Exercise 10: Multi-Scenario Cost Design

**Objective:** Practice designing for different cost contexts.

Design the same system (notification platform) for three different contexts:

**Context A: Well-funded scale-up**
- $500K/month infrastructure budget
- 50M users
- Maximum reliability expected

**Context B: Early-stage startup**
- $10K/month infrastructure budget
- 100K users
- Reliability can be "good enough"

**Context C: Internal enterprise tool**
- $20K/month infrastructure budget
- 10K users
- Operational simplicity prioritized

**For each context:**
- Draw the architecture
- Explain key cost decisions
- Identify what you would NOT do (and why)
- Describe the evolution path to the next stage

**Deliverable:** Three architectures with comparative analysis.

---

## Exercise 11: AWS Cost Optimization Audit

**Objective:** Practice AWS-specific cost optimization.

Given an AWS architecture with:
- 50 m5.xlarge EC2 instances (On-Demand)
- 10TB RDS MySQL Multi-AZ (db.r5.2xlarge)
- 100TB S3 Standard storage
- 5TB/month data transfer (cross-region)
- NAT Gateway processing 10TB/month
- CloudWatch Logs ingesting 500GB/month

**Part A: Calculate current monthly cost**
- Itemize by service
- Identify the top 3 cost drivers

**Part B: Propose optimizations for each**

| Service | Current State | Optimization | Estimated Savings |
|---------|--------------|--------------|-------------------|
| EC2 | 50 × On-Demand | ? | ? |
| RDS | Multi-AZ r5.2xlarge | ? | ? |
| S3 | 100TB Standard | ? | ? |
| Data Transfer | 5TB cross-region | ? | ? |
| NAT Gateway | 10TB processed | ? | ? |
| CloudWatch | 500GB ingested | ? | ? |

**Part C: Prioritize by ROI**
- Which optimizations have highest impact with lowest effort?
- Which require architectural changes?
- What's the total potential savings?

**Deliverable:** Cost optimization report with calculations.

---

## Exercise 12: Reserved Capacity Planning

**Objective:** Practice AWS commitment-based pricing decisions.

Given 12 months of historical EC2 usage:
- Baseline: 30 instances running 24/7
- Peak (weekdays 9-5): 80 instances
- Off-peak (nights/weekends): 20 instances

**Part A: Analyze usage patterns**
- What percentage of time is each capacity level used?
- What's the average hourly instance count?

**Part B: Design Reserved/Savings Plan strategy**
- How many Reserved Instances or Savings Plans?
- 1-year or 3-year commitment?
- All Upfront, Partial Upfront, or No Upfront?
- What remains On-Demand?

**Part C: Calculate savings**
- Current On-Demand cost
- Proposed blended cost
- Annual savings
- Break-even point

**Part D: Risk analysis**
- What if usage decreases 30%?
- What if instance types change?
- How does Savings Plans vs Reserved flexibility help?

**Deliverable:** Reservation strategy document with financial model.

---

## Exercise 13: Spot Instance Architecture Design

**Objective:** Design a production-ready Spot architecture.

Design a batch processing system for:
- 1TB of data processed daily
- 4-hour processing window
- Can tolerate individual job restarts
- Output must be 100% complete

**Part A: Spot strategy**
- Which instance types and diversification?
- What percentage Spot vs On-Demand?
- How to handle interruptions?

**Part B: Fault tolerance**
- Checkpointing strategy
- Job queue design
- Retry logic
- Progress tracking

**Part C: Cost comparison**
- Full On-Demand cost
- Spot + fallback cost
- Savings percentage
- Complexity trade-off

**Deliverable:** Architecture diagram with Spot handling pseudocode.

---

## Exercise 14: S3 Lifecycle Policy Design

**Objective:** Design cost-optimal S3 lifecycle policies.

For each bucket type, design lifecycle policies:

**Bucket A: Application Logs**
- 5TB/month ingestion
- Accessed frequently first 7 days
- Occasional access 7-90 days
- Compliance requires 7-year retention

**Bucket B: User Uploads (photos/videos)**
- 10TB/month ingestion
- Unpredictable access patterns
- Some content viral, most barely accessed
- No expiration (user data)

**Bucket C: Database Backups**
- Daily full backup (500GB)
- Hourly incremental (10GB)
- Need 30-day point-in-time recovery
- 1-year archive retention

**For each bucket:**
- Design lifecycle rules
- Calculate before/after monthly cost
- Document trade-offs

**Deliverable:** Lifecycle policies with cost analysis.

---

## Exercise 15: Database Cost Optimization

**Objective:** Choose optimal database configuration.

Given requirements:
- 50,000 reads/second (80% single-key lookups)
- 5,000 writes/second
- 500GB data size
- 99.9% availability required
- Global users (US, EU, APAC)

**Compare options:**
1. RDS MySQL Multi-AZ + Read Replicas
2. Aurora MySQL + Global Database
3. DynamoDB + Global Tables
4. DynamoDB + ElastiCache

**For each option, calculate:**
- Monthly infrastructure cost
- Operational complexity (subjective 1-10)
- Latency profile
- Failure modes

**Make a recommendation with justification.**

**Deliverable:** Database selection analysis with cost comparison.

---

## Exercise 16: Data Transfer Cost Reduction

**Objective:** Minimize AWS data transfer costs.

Current architecture:
- 3 regions (us-east-1, eu-west-1, ap-southeast-1)
- Each region syncs full dataset (1TB) daily
- NAT Gateway for all outbound traffic
- CloudWatch Logs sent to central region
- S3 access from EC2 via public endpoints

**Analyze and optimize:**
- Current data transfer cost breakdown
- VPC Endpoint opportunities
- Replication strategy changes
- Log aggregation alternatives
- CDN opportunities

**Calculate:**
- Current monthly data transfer cost
- Optimized monthly cost
- Implementation effort for each optimization

**Deliverable:** Data transfer optimization plan.

---

## Exercise 17: Serverless Cost Analysis

**Objective:** Analyze when serverless is cost-effective.

For a web API handling 10M requests/month:
- Average request duration: 200ms
- Memory requirement: 512MB
- 10% of requests require database access
- Traffic is highly variable (10x peak/average)

**Compare:**
1. Lambda + API Gateway
2. Fargate (always-on, auto-scaling)
3. EC2 (with auto-scaling)

**For each:**
- Calculate monthly cost
- Consider cold start impact
- Consider operational overhead
- Identify break-even points

**At what request volume does each option become cheaper/more expensive?**

**Deliverable:** Serverless vs containers vs VMs analysis with break-even chart.

---

## Exercise 18: Cost-Aware CI/CD Pipeline

**Objective:** Design cost controls into deployment pipeline.

Design a CI/CD pipeline that:
- Estimates infrastructure cost change before deploy
- Alerts on significant cost increases
- Requires approval for changes above threshold
- Tracks cost impact of each deployment

**Include:**
- Pipeline stages
- Cost estimation mechanism
- Approval workflow
- Rollback cost impact
- Dashboards and reporting

**Pseudocode for:**
- Infrastructure cost estimation
- Change comparison
- Alert logic
- Approval gates

**Deliverable:** CI/CD pipeline design with cost controls.

---

# Part 21: GCP Cost Optimization (Google Cloud Perspective)

Staff engineers working with Google Cloud face similar but distinct cost optimization patterns. This section covers GCP-specific strategies.

## GCP Cost Model Fundamentals

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    GCP COST MODEL: KEY DIFFERENCES FROM AWS                 │
│                                                                             │
│   PRICING PHILOSOPHY:                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  AWS: Pay for what you provision                                    │   │
│   │  GCP: Pay for what you use (sustained use discounts automatic)      │   │
│   │                                                                     │   │
│   │  GCP automatically applies discounts:                               │   │
│   │  • 20% discount for 50% monthly usage                               │   │
│   │  • 30% discount for 75% monthly usage                               │   │
│   │  • No commitment required (unlike AWS Reserved)                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   KEY GCP COST LEVERS:                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Committed Use Discounts (CUDs): 1-3 year, up to 57% off          │   │
│   │  • Preemptible VMs: 60-91% off, max 24hr, preemptible anytime       │   │
│   │  • Spot VMs: Similar to preemptible, newer pricing model            │   │
│   │  • Sole-tenant nodes: For compliance/licensing requirements         │   │
│   │  • Custom machine types: Pay exactly for vCPU + RAM you need        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   GCP-SPECIFIC SURPRISES:                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Egress to internet: $0.12/GB (similar to AWS)                    │   │
│   │  • Cross-region: $0.01-0.08/GB (often cheaper than AWS)             │   │
│   │  • BigQuery: Pay per query (easy to run expensive queries)          │   │
│   │  • Cloud SQL: Always-on, no serverless option (until AlloyDB)       │   │
│   │  • GKE: Control plane now charged ($0.10/hour per cluster)          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## GCP Compute Optimization

```
// Pseudocode for GCP compute optimization

CLASS GCPComputeOptimizer:
    
    FUNCTION optimize_vm_fleet(current_fleet):
        recommendations = []
        
        FOR vm IN current_fleet:
            // Check for right-sizing
            avg_cpu = get_avg_cpu_utilization(vm, days=30)
            avg_memory = get_avg_memory_utilization(vm, days=30)
            
            IF avg_cpu < 30 AND avg_memory < 30:
                // Underutilized - recommend smaller or custom
                optimal = calculate_custom_machine_type(
                    vcpus = ceil(vm.vcpus * avg_cpu / 50),  // Target 50% util
                    memory_gb = ceil(vm.memory_gb * avg_memory / 50)
                )
                
                recommendations.append({
                    vm: vm,
                    recommendation: "Downsize to custom machine type",
                    current_cost: vm.monthly_cost,
                    new_cost: optimal.monthly_cost,
                    savings: vm.monthly_cost - optimal.monthly_cost
                })
            
            // Check for sustained use optimization
            uptime_percent = get_uptime_percent(vm, days=30)
            IF uptime_percent < 50:
                recommendations.append({
                    vm: vm,
                    recommendation: "Consider turning off when not in use",
                    note: "Missing out on sustained use discounts"
                })
            
            // Check for preemptible/spot conversion
            IF vm.can_tolerate_preemption:
                preemptible_cost = vm.monthly_cost * 0.2  // ~80% savings
                recommendations.append({
                    vm: vm,
                    recommendation: "Convert to Preemptible/Spot",
                    savings: vm.monthly_cost - preemptible_cost
                })
        
        RETURN recommendations
    
    FUNCTION design_cud_strategy(fleet, planning_horizon):
        // Committed Use Discounts for predictable baseline
        
        // Calculate baseline usage (minimum over 30 days)
        baseline = calculate_baseline_usage(fleet)
        
        // CUD pricing
        cud_1yr_discount = 0.37  // 37% off
        cud_3yr_discount = 0.57  // 57% off
        
        // Recommendation based on confidence
        IF planning_horizon >= 3 AND usage_stable:
            cud_amount = baseline * 0.8  // Cover 80% of baseline
            term = 3
            discount = cud_3yr_discount
        ELSE IF planning_horizon >= 1:
            cud_amount = baseline * 0.6  // More conservative
            term = 1
            discount = cud_1yr_discount
        ELSE:
            RETURN "Rely on sustained use discounts only"
        
        RETURN {
            recommended_cud: cud_amount,
            term_years: term,
            monthly_savings: cud_amount * on_demand_rate * discount,
            break_even_months: term * 12 * (1 - discount)
        }
```

## BigQuery Cost Optimization

BigQuery is powerful but can generate surprise bills. Staff engineers design with query cost in mind.

```
// Pseudocode for BigQuery cost optimization

CLASS BigQueryCostOptimizer:
    
    FUNCTION analyze_query_patterns(project_id, days=30):
        queries = get_query_history(project_id, days)
        
        cost_analysis = {
            total_bytes_processed: 0,
            total_cost: 0,
            expensive_queries: [],
            optimization_opportunities: []
        }
        
        FOR query IN queries:
            query_cost = query.bytes_processed / (1024^4) * 5  // $5/TB
            cost_analysis.total_bytes_processed += query.bytes_processed
            cost_analysis.total_cost += query_cost
            
            // Flag expensive queries
            IF query_cost > 10:  // $10+ per query
                cost_analysis.expensive_queries.append({
                    query: query.sql,
                    user: query.user,
                    cost: query_cost,
                    bytes: query.bytes_processed
                })
            
            // Identify optimization opportunities
            IF query.uses_select_star:
                cost_analysis.optimization_opportunities.append({
                    query: query.sql,
                    issue: "SELECT * scans all columns",
                    fix: "Select only needed columns"
                })
            
            IF NOT query.uses_partition_filter:
                cost_analysis.optimization_opportunities.append({
                    query: query.sql,
                    issue: "Not filtering on partition column",
                    fix: "Add partition filter to reduce scan"
                })
            
            IF query.joins_unpartitioned_tables:
                cost_analysis.optimization_opportunities.append({
                    query: query.sql,
                    issue: "Joining large unpartitioned tables",
                    fix: "Partition tables or use clustering"
                })
        
        RETURN cost_analysis
    
    FUNCTION design_cost_controls(project_id):
        controls = []
        
        // Per-user daily limits
        controls.append({
            type: "Per-user quota",
            limit: "1TB/day per user",
            action: "Block queries exceeding limit",
            rationale: "Prevent runaway exploratory queries"
        })
        
        // Per-query limits
        controls.append({
            type: "Per-query limit",
            limit: "500GB per query",
            action: "Require approval for larger queries",
            rationale: "Force query optimization before large scans"
        })
        
        // Flat-rate pricing evaluation
        monthly_usage = estimate_monthly_bytes()
        on_demand_cost = monthly_usage / (1024^4) * 5
        flat_rate_cost = 2000  // $2000/month for 500 slots
        
        IF on_demand_cost > flat_rate_cost * 1.5:
            controls.append({
                type: "Pricing model",
                recommendation: "Switch to flat-rate pricing",
                current_cost: on_demand_cost,
                flat_rate_cost: flat_rate_cost,
                savings: on_demand_cost - flat_rate_cost
            })
        
        RETURN controls
```

## Cloud Storage Cost Optimization

```
// Pseudocode for GCS lifecycle and cost optimization

FUNCTION design_gcs_lifecycle(bucket_purpose, access_patterns):
    rules = []
    
    SWITCH bucket_purpose:
        CASE "application_logs":
            rules.append({
                age: 30,
                action: "SetStorageClass",
                target: "NEARLINE"  // Lower cost, retrieval fee
            })
            rules.append({
                age: 90,
                action: "SetStorageClass",
                target: "COLDLINE"
            })
            rules.append({
                age: 365,
                action: "SetStorageClass",
                target: "ARCHIVE"
            })
            rules.append({
                age: 2555,  // 7 years
                action: "Delete"
            })
        
        CASE "user_content":
            // Use Autoclass - GCP automatically moves based on access
            RETURN {
                use_autoclass: true,
                rationale: "Unpredictable access patterns, let GCP optimize"
            }
        
        CASE "database_backups":
            rules.append({
                age: 7,
                action: "SetStorageClass",
                target: "NEARLINE"
            })
            rules.append({
                age: 30,
                action: "SetStorageClass",
                target: "COLDLINE"
            })
            rules.append({
                age: 365,
                action: "Delete",
                condition: "Keep last 12 monthly backups"
            })
    
    RETURN rules
```

---

# Part 22: Kubernetes and Container Cost Optimization

Container orchestration adds a layer of cost complexity. Staff engineers must understand both infrastructure and orchestration costs.

## The Kubernetes Cost Challenge

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                KUBERNETES COST: THE HIDDEN LAYERS                            │
│                                                                             │
│   LAYER 1: INFRASTRUCTURE                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Node cost (EC2/GCE/AKS VMs)                                        │   │
│   │  + Control plane (EKS: $0.10/hr, GKE: $0.10/hr, AKS: free)          │   │
│   │  + Load balancers (per-LB charges)                                  │   │
│   │  + Persistent volumes (EBS/PD)                                      │   │
│   │  + Network (cross-AZ, ingress/egress)                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   LAYER 2: ORCHESTRATION OVERHEAD                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  System pods (kube-system namespace)                                │   │
│   │  + Monitoring/observability stack                                   │   │
│   │  + Service mesh (Istio can add 50% overhead)                        │   │
│   │  + Logging agents                                                   │   │
│   │  + Security scanning                                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   LAYER 3: INEFFICIENCY                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Over-provisioned resource requests                                 │   │
│   │  + Fragmentation (can't bin-pack perfectly)                         │   │
│   │  + Unused reserved capacity                                         │   │
│   │  + Right-sizing inertia ("works fine, don't touch")                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   TYPICAL WASTE: 30-50% of Kubernetes spend is on unused resources          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Resource Request/Limit Optimization

```
// Pseudocode for Kubernetes resource optimization

CLASS K8sResourceOptimizer:
    
    FUNCTION analyze_pod_resources(namespace, days=14):
        pods = get_pod_metrics(namespace, days)
        recommendations = []
        
        FOR pod IN pods:
            // Compare actual usage to requests
            cpu_request = pod.spec.resources.requests.cpu
            cpu_actual_p99 = pod.metrics.cpu.p99
            cpu_utilization = cpu_actual_p99 / cpu_request
            
            memory_request = pod.spec.resources.requests.memory
            memory_actual_p99 = pod.metrics.memory.p99
            memory_utilization = memory_actual_p99 / memory_request
            
            // Flag over-provisioned pods
            IF cpu_utilization < 0.3 AND memory_utilization < 0.3:
                recommendations.append({
                    pod: pod.name,
                    issue: "Significantly over-provisioned",
                    current_requests: {cpu: cpu_request, memory: memory_request},
                    recommended: {
                        cpu: cpu_actual_p99 * 1.3,  // 30% headroom
                        memory: memory_actual_p99 * 1.3
                    },
                    savings_estimate: calculate_savings(pod, new_requests)
                })
            
            // Flag under-provisioned pods (risk)
            IF cpu_utilization > 0.9 OR memory_utilization > 0.9:
                recommendations.append({
                    pod: pod.name,
                    issue: "Near limit - risk of throttling/OOM",
                    current_requests: {cpu: cpu_request, memory: memory_request},
                    recommended: {
                        cpu: cpu_actual_p99 * 1.5,
                        memory: memory_actual_p99 * 1.5
                    },
                    priority: "HIGH"
                })
            
            // Flag pods without limits
            IF NOT pod.spec.resources.limits:
                recommendations.append({
                    pod: pod.name,
                    issue: "No resource limits - can starve other pods",
                    recommendation: "Add limits (typically 2x requests)"
                })
        
        RETURN recommendations
    
    FUNCTION optimize_node_pool(cluster):
        nodes = get_cluster_nodes(cluster)
        
        // Calculate cluster-wide utilization
        total_allocatable_cpu = sum(n.allocatable.cpu for n in nodes)
        total_requested_cpu = sum(n.requested.cpu for n in nodes)
        total_used_cpu = sum(n.used.cpu for n in nodes)
        
        request_efficiency = total_requested_cpu / total_allocatable_cpu
        usage_efficiency = total_used_cpu / total_allocatable_cpu
        request_accuracy = total_used_cpu / total_requested_cpu
        
        RETURN {
            node_count: len(nodes),
            request_efficiency: request_efficiency,  // Should be 60-80%
            usage_efficiency: usage_efficiency,      // Actual utilization
            request_accuracy: request_accuracy,      // How accurate are requests
            wasted_capacity: (total_allocatable_cpu - total_used_cpu) * cost_per_cpu,
            recommendations: generate_recommendations(
                request_efficiency, usage_efficiency, request_accuracy
            )
        }
```

## Cluster Autoscaler Optimization

```
// Pseudocode for cluster autoscaler configuration

CLASS ClusterAutoscalerConfig:
    
    FUNCTION design_autoscaler_policy(workload_patterns):
        // Analyze workload characteristics
        scale_up_frequency = workload_patterns.avg_scale_up_events_per_day
        scale_down_frequency = workload_patterns.avg_scale_down_events_per_day
        avg_pending_time = workload_patterns.avg_pod_pending_time
        
        config = {
            // Scale-up settings
            scan_interval: "10s",  // How often to check for pending pods
            scale_up_delay: "0s",  // Scale up immediately when needed
            
            // Scale-down settings (where cost savings happen)
            scale_down_delay_after_add: "10m",  // Don't scale down too fast
            scale_down_unneeded_time: "10m",    // How long node must be underutilized
            scale_down_utilization_threshold: 0.5,  // Scale down if <50% utilized
            
            // Node selection
            expander: "least-waste",  // Choose node type that wastes least capacity
            
            // Safety
            max_node_provision_time: "15m",  // Fail fast if node doesn't come up
            skip_nodes_with_local_storage: false,  // Allow scaling down pods with local storage
            skip_nodes_with_system_pods: true  // Don't scale down kube-system nodes
        }
        
        // Optimize based on patterns
        IF scale_up_frequency > 10:
            // Frequent scaling - pre-provision buffer
            config.over_provisioning = {
                enabled: true,
                buffer_pods: 2,  // Keep capacity for 2 extra pods
                rationale: "Frequent scaling events justify buffer capacity"
            }
        
        IF avg_pending_time > "2m":
            // Slow scale-up - consider larger nodes or pre-provisioning
            config.recommendations.append(
                "Consider larger node types for faster scale-up"
            )
        
        RETURN config
    
    FUNCTION analyze_node_pool_diversity(cluster):
        // Multi-instance-type strategy for better bin-packing and availability
        
        workloads = get_workload_profiles(cluster)
        
        recommended_pools = []
        
        // General purpose pool (default)
        recommended_pools.append({
            name: "general-purpose",
            instance_types: ["m5.xlarge", "m5.2xlarge", "m5a.xlarge"],
            target_capacity: "70%",  // Main workload
            use_spot: false
        })
        
        // Spot pool for fault-tolerant workloads
        recommended_pools.append({
            name: "spot-workers",
            instance_types: ["m5.xlarge", "m5.2xlarge", "m4.xlarge", "c5.xlarge"],
            target_capacity: "20%",
            use_spot: true,
            spot_allocation_strategy: "capacity-optimized"
        })
        
        // Burstable pool for low-priority
        IF has_low_priority_workloads(workloads):
            recommended_pools.append({
                name: "burstable",
                instance_types: ["t3.large", "t3.xlarge"],
                target_capacity: "10%",
                use_spot: true
            })
        
        RETURN recommended_pools
```

## Multi-Tenant Cost Attribution

```
// Pseudocode for Kubernetes cost attribution

CLASS K8sCostAttribution:
    
    FUNCTION calculate_namespace_costs(cluster, period):
        node_costs = get_node_costs(cluster, period)
        namespaces = get_all_namespaces(cluster)
        
        namespace_costs = {}
        
        FOR namespace IN namespaces:
            pods = get_pods(namespace)
            
            // Calculate resource usage
            cpu_seconds = sum(p.cpu_usage * p.duration for p in pods)
            memory_gb_seconds = sum(p.memory_usage * p.duration for p in pods)
            storage_gb_hours = sum(get_pvc_usage(p) for p in pods)
            network_gb = sum(get_network_usage(p) for p in pods)
            
            // Calculate proportional cost
            cluster_cpu_seconds = get_cluster_total_cpu_seconds(period)
            cluster_memory_seconds = get_cluster_total_memory_seconds(period)
            
            cpu_cost = (cpu_seconds / cluster_cpu_seconds) * node_costs.compute
            memory_cost = (memory_gb_seconds / cluster_memory_seconds) * node_costs.memory
            storage_cost = storage_gb_hours * STORAGE_RATE
            network_cost = network_gb * NETWORK_RATE
            
            namespace_costs[namespace] = {
                compute: cpu_cost + memory_cost,
                storage: storage_cost,
                network: network_cost,
                total: cpu_cost + memory_cost + storage_cost + network_cost,
                
                // Efficiency metrics
                request_vs_usage: calculate_request_efficiency(pods),
                recommendation: generate_optimization_recommendation(pods)
            }
        
        RETURN namespace_costs
    
    FUNCTION implement_cost_guardrails(namespace):
        guardrails = {}
        
        // Resource quotas
        guardrails.resource_quota = {
            hard: {
                "requests.cpu": "100",        // 100 CPU cores
                "requests.memory": "200Gi",   // 200GB RAM
                "persistentvolumeclaims": 20,
                "services.loadbalancers": 5
            }
        }
        
        // Limit ranges (default requests if not specified)
        guardrails.limit_range = {
            default: {
                cpu: "500m",
                memory: "512Mi"
            },
            defaultRequest: {
                cpu: "100m",
                memory: "128Mi"
            },
            max: {
                cpu: "4",
                memory: "8Gi"
            }
        }
        
        // Network policies (reduce cross-namespace traffic)
        guardrails.network_policy = {
            allow_same_namespace: true,
            allow_egress_internet: false,  // Require explicit approval
            allow_cross_namespace: ["monitoring", "logging"]
        }
        
        RETURN guardrails
```

---

# Part 23: Cost Governance and Organizational Patterns

Staff engineers don't just optimize individual systems—they establish patterns and governance for sustainable cost management across organizations.

## The FinOps Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FINOPS: CLOUD FINANCIAL OPERATIONS                        │
│                                                                             │
│   THREE PHASES:                                                             │
│                                                                             │
│   PHASE 1: INFORM                                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Tag all resources for cost attribution                           │   │
│   │  • Create cost dashboards per team/service                          │   │
│   │  • Establish cost reporting cadence                                 │   │
│   │  • Make costs visible to engineers (not just finance)               │   │
│   │                                                                     │   │
│   │  Staff Role: Design tagging strategy, build dashboards              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   PHASE 2: OPTIMIZE                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Right-size resources based on data                               │   │
│   │  • Implement auto-scaling                                           │   │
│   │  • Purchase commitments (RI, Savings Plans)                         │   │
│   │  • Clean up unused resources                                        │   │
│   │                                                                     │   │
│   │  Staff Role: Lead optimization initiatives, set targets             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   PHASE 3: OPERATE                                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Continuous cost monitoring                                       │   │
│   │  • Anomaly detection and alerting                                   │   │
│   │  • Cost reviews in architecture decisions                           │   │
│   │  • Budget enforcement and guardrails                                │   │
│   │                                                                     │   │
│   │  Staff Role: Establish ongoing governance, mentor teams             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Team-Level Cost Accountability

```
// Pseudocode for cost accountability framework

CLASS CostAccountabilityFramework:
    
    FUNCTION design_team_cost_model(organization):
        model = {
            attribution: {},
            budgets: {},
            alerts: {},
            governance: {}
        }
        
        // Attribution model
        model.attribution = {
            // Tag hierarchy
            required_tags: [
                "team",           // Which team owns this
                "service",        // Which service is this
                "environment",    // prod, staging, dev
                "cost_center"     // Business unit
            ],
            
            // Shared cost allocation
            shared_cost_strategy: "proportional",  // Split by usage
            shared_services: ["monitoring", "logging", "ci-cd"],
            
            // Untagged cost handling
            untagged_policy: "alert_and_attribute_to_platform"
        }
        
        // Budget model
        FOR team IN organization.teams:
            historical = get_historical_cost(team, months=6)
            growth_rate = calculate_growth_rate(team)
            
            model.budgets[team] = {
                monthly_budget: historical.p75 * (1 + growth_rate),
                alert_thresholds: [0.5, 0.75, 0.9, 1.0],
                overage_policy: "require_justification",
                review_frequency: "monthly"
            }
        
        // Alert model
        model.alerts = {
            anomaly_detection: {
                enabled: true,
                sensitivity: "medium",
                alert_channels: ["email", "slack", "pagerduty"]
            },
            budget_alerts: {
                enabled: true,
                thresholds: [50, 75, 90, 100, 110]  // Percent of budget
            },
            cost_spike_alerts: {
                enabled: true,
                threshold: "20% day-over-day increase"
            }
        }
        
        // Governance
        model.governance = {
            cost_review_cadence: "monthly",
            architecture_review_threshold: "$10,000/month increase",
            approval_required: {
                new_service: "team_lead",
                major_change: "staff_engineer",
                large_commitment: "engineering_director"
            }
        }
        
        RETURN model
    
    FUNCTION implement_cost_culture(organization):
        initiatives = []
        
        // Visibility
        initiatives.append({
            name: "Cost Dashboard Access",
            action: "Give all engineers read access to cost dashboards",
            rationale: "Can't optimize what you can't see"
        })
        
        // Accountability
        initiatives.append({
            name: "Team Cost Reviews",
            action: "Monthly cost review in team meetings",
            rationale: "Make cost a normal engineering topic"
        })
        
        // Incentives
        initiatives.append({
            name: "Cost Efficiency Wins",
            action: "Celebrate significant cost reductions in all-hands",
            rationale: "Reinforce that efficiency is valued"
        })
        
        // Education
        initiatives.append({
            name: "Cost Optimization Training",
            action: "Quarterly workshops on cloud cost optimization",
            rationale: "Build organizational capability"
        })
        
        // Process
        initiatives.append({
            name: "Cost in Design Reviews",
            action: "Include cost estimate in architecture proposals",
            rationale: "Shift cost consideration left"
        })
        
        RETURN initiatives
```

---

# AWS Cost Quick Reference

## AWS Service Cost Cheat Sheet

| Service | Primary Cost Driver | Hidden Costs | Optimization Lever |
|---------|--------------------|--------------|--------------------|
| **EC2** | Instance hours | EBS, network, EIP | Spot, Reserved, Graviton |
| **RDS** | Instance hours | IOPS, storage, backup | Reserved, right-size, Aurora Serverless |
| **DynamoDB** | Read/Write units | Storage, streams, backups | On-Demand vs Provisioned, Reserved |
| **S3** | Storage volume | Requests, transfer | Lifecycle policies, Intelligent-Tiering |
| **Lambda** | Invocations + duration | CloudWatch, VPC | Memory optimization, Graviton |
| **NAT Gateway** | Data processed | Fixed hourly cost | VPC Endpoints, architecture |
| **CloudWatch** | Log ingestion | Metrics, dashboards | Log sampling, retention |
| **Data Transfer** | Cross-region egress | NAT, Internet egress | Same-region, VPC Endpoints, CDN |

## AWS Cost Optimization Checklist

**Compute:**
☐ Right-size instances based on actual utilization
☐ Use Graviton (ARM) where compatible
☐ Implement Savings Plans or Reserved Instances for baseline
☐ Use Spot for fault-tolerant workloads
☐ Auto-scale aggressively (scale down, not just up)

**Storage:**
☐ S3 lifecycle policies (Intelligent-Tiering for unknown access)
☐ EBS GP3 instead of GP2 (20% cheaper)
☐ Delete unattached EBS volumes
☐ RDS storage auto-scaling with reasonable limits
☐ Snapshot lifecycle management

**Database:**
☐ Right-size RDS instances
☐ Reserved Instances for production databases
☐ Aurora Serverless for variable workloads
☐ DynamoDB On-Demand vs Provisioned analysis
☐ Read replicas instead of scaling primary

**Network:**
☐ VPC Gateway Endpoints for S3/DynamoDB (free)
☐ Minimize cross-region data transfer
☐ CloudFront for content delivery
☐ Consolidate NAT Gateways (one per AZ, not per subnet)
☐ PrivateLink for AWS service access

**Observability:**
☐ CloudWatch Logs retention policies
☐ Log sampling for high-volume applications
☐ Metric aggregation (don't store per-second forever)
☐ Dashboard consolidation

---

# GCP Cost Quick Reference

## GCP Service Cost Cheat Sheet

| Service | Primary Cost Driver | Hidden Costs | Optimization Lever |
|---------|--------------------|--------------|--------------------|
| **Compute Engine** | Instance hours | Persistent Disk, Network | Sustained use, CUDs, Preemptible |
| **Cloud SQL** | Instance hours | Storage, backups, HA | Right-size, CUDs |
| **BigQuery** | Bytes scanned | Storage, streaming inserts | Partitioning, flat-rate |
| **Cloud Storage** | Storage volume | Operations, retrieval | Lifecycle, Autoclass |
| **GKE** | Node + control plane | PD, LB, network | Autopilot, Spot nodes |
| **Cloud Run** | CPU-seconds + memory | Network, min instances | Concurrency, cold start |
| **Pub/Sub** | Message operations | Storage, acknowledge | Batching, ordering |
| **Cloud Functions** | Invocations + duration | Network, memory | Right-size memory |

## GCP Cost Optimization Checklist

**Compute:**
☐ Leverage sustained use discounts (automatic)
☐ Evaluate Committed Use Discounts for stable baseline
☐ Use Preemptible/Spot for fault-tolerant workloads
☐ Right-size with custom machine types
☐ Consider Sole-tenant nodes only when required

**Storage:**
☐ Enable Autoclass for unpredictable access patterns
☐ Lifecycle policies for known patterns
☐ Use Regional vs Multi-regional based on requirements
☐ Archive old data to Coldline/Archive

**Database:**
☐ Right-size Cloud SQL instances
☐ Use read replicas instead of scaling primary
☐ Consider Spanner only for true global scale
☐ AlloyDB for PostgreSQL workloads
☐ Firestore vs Datastore based on usage pattern

**BigQuery:**
☐ Partition and cluster tables
☐ Use LIMIT and column selection
☐ Evaluate flat-rate for high-volume users
☐ Set query quotas per user/project
☐ Use BigQuery BI Engine for dashboards

**GKE:**
☐ Consider GKE Autopilot for simplified operations
☐ Use Spot VMs in node pools
☐ Right-size pod requests
☐ Enable cluster autoscaler with aggressive scale-down
☐ Use Workload Identity instead of service account keys

**Network:**
☐ Use Premium vs Standard tier based on latency needs
☐ Cloud CDN for cacheable content
☐ Private Google Access for GCP service traffic
☐ Minimize cross-region data transfer

---

# Quick Reference Card

## Cost Consideration Checklist

| Step | Question | Staff Response |
|------|----------|----------------|
| **1. Identify drivers** | "What drives cost in this design?" | "Top drivers are: database storage, cross-region sync, and ML inference..." |
| **2. Quantify roughly** | "How does cost scale?" | "Storage grows linearly with retention. Compute scales with QPS. Cross-region scales with write volume..." |
| **3. Assess trade-offs** | "What can we trade off?" | "We can reduce reliability for internal paths, use async for cross-region, cache aggressively..." |
| **4. Right-size** | "Are we over-provisioned?" | "Provision for expected + 30% headroom, auto-scale for peaks..." |
| **5. Consider operational** | "What's the human cost?" | "This design has 5 components; each adds on-call surface. Let me simplify..." |

## Cost-Efficiency Patterns

| Pattern | What It Means | When to Use |
|---------|---------------|-------------|
| **Tiered storage** | Hot/warm/cold based on access patterns | Data that ages out of active use |
| **Progressive degradation** | Reduce features under load | Elastic systems with variable load |
| **Selective replication** | Replicate critical, not everything | Multi-region with mixed criticality |
| **Edge caching** | Cache close to users | Read-heavy with cacheable content |
| **Async where possible** | Decouple with queues | Non-user-facing processing |
| **Right-sized redundancy** | Match replicas to criticality | Different SLOs for different paths |

## Anti-Patterns to Avoid

| Anti-Pattern | Why It's Expensive | Staff Alternative |
|--------------|-------------------|-------------------|
| **Provision for peak** | 80% idle capacity | Auto-scale with headroom |
| **Replicate everything** | 3x storage and sync cost | Selective replication |
| **Keep data forever** | Unbounded storage growth | Retention policies and tiering |
| **Multi-region everything** | 2-3x infrastructure | Multi-region only where needed |
| **Synchronous everywhere** | Higher latency, more resources | Async where consistency allows |

---

# Conclusion

Cost is not a constraint imposed after design. It's a dimension of design itself.

Staff engineers approach cost the way they approach any other architectural consideration: with explicit reasoning, clear trade-offs, and calibration to context. A system that works but is too expensive is not a successful system. A system that's efficient but unreliable is also not successful. The goal is to find the right point on the trade-off frontier for your specific use case.

This means:

**Making cost visible.** Before you can optimize cost, you must see it. Understand what drives cost in your system—compute, storage, network, operations—and make those drivers explicit in your design reasoning.

**Trading off explicitly.** Every design decision has cost implications. A Staff engineer articulates these trade-offs: "I'm choosing X because it saves Y at the cost of Z, and Z is acceptable for this use case."

**Designing for sustainability.** A system that requires 5 engineers to operate is expensive even if its infrastructure bill is low. Consider the full cost—human and computational—of your design.

**Matching cost to value.** Not every feature needs 99.99% availability. Not every path needs real-time processing. Staff engineers allocate resources proportionally to the value being delivered.

**Evolving over time.** Cost optimization is not a one-time activity. As systems mature, cost reasoning evolves—from "ship quickly" to "measure and optimize" to "continuous efficiency."

In interviews, cost awareness demonstrates maturity. It shows you've operated real systems with real budgets. It shows you understand that engineering exists in an economic context. It shows you can make the kind of holistic decisions that Staff engineers make every day.

Design systems that work. Design systems that scale. And design systems that your organization can afford to run for years to come.

---

*End of Chapter 11*

*Next: Chapter 12 — Phase 4 & Phase 5: Non-Functional Requirements, Assumptions, and Constraints*
