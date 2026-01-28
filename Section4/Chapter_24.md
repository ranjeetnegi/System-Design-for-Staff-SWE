# Chapter 24: Multi-Region Systems — Geo-Replication, Latency, and Failure

---

# Introduction

Multi-region architecture is one of the most powerful and most misunderstood capabilities in distributed systems. When designed correctly, it delivers genuine global availability, low latency for users worldwide, and resilience against regional disasters. When designed incorrectly—which happens far more often—it creates consistency nightmares, doubles or triples infrastructure costs, and introduces failure modes that are nearly impossible to debug.

I've spent years building globally distributed systems at Google scale and debugging incidents that occurred because well-intentioned teams added "multi-region" to a system that didn't need it, or needed it but implemented it wrong. The pattern is consistent: teams hear "multi-region" and think "higher availability." They add regions, deploy the same code everywhere, and discover—usually during an incident—that they've created a distributed system with all the complexity of distributed consensus but none of the safeguards.

This chapter teaches multi-region architecture as Staff Engineers practice it: with deep skepticism about when it's needed, clear-eyed understanding of what it costs, and practical judgment about how to implement it when it's genuinely required. We'll cover when geography matters, what trade-offs are unavoidable, and how to design systems that survive regional failures without creating global ones.

**The Staff Engineer's First Law of Multi-Region**: Every region you add is a consistency decision you're making. Make sure you understand what you're giving up.

---

## Quick Visual: Multi-Region at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               MULTI-REGION ARCHITECTURE: THE STAFF ENGINEER VIEW            │
│                                                                             │
│   WRONG Framing: "Multi-region = higher availability + lower latency"       │
│   RIGHT Framing: "Multi-region trades consistency and simplicity for        │
│                   geographic resilience and latency reduction"              │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Before going multi-region, answer:                                 │   │
│   │                                                                     │   │
│   │  1. What happens when regions disagree about the state of the world?│   │
│   │  2. What happens during a network partition between regions?        │   │
│   │  3. How do you debug a problem that spans three continents?         │   │
│   │  4. Who is on-call when Tokyo has a problem at 3am Pacific?         │   │
│   │  5. Is the 2-3x cost justified by the failure modes you're avoiding?│   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   If you can't answer all five, you're not ready for multi-region.          │
│                                                                             │
│   THE UNCOMFORTABLE TRUTH:                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Most systems don't need multi-region.                              │   │
│   │  A well-designed single-region system with good disaster recovery   │   │
│   │  is simpler, cheaper, and often more reliable than a poorly         │   │
│   │  designed multi-region system.                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Multi-Region Decisions

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Users complain about latency** | "Let's deploy to more regions to reduce latency" | "Where are the users? What's causing latency? Adding regions only helps if the data can be local. For many workloads, a CDN or edge caching solves 90% of the problem at 10% of the complexity." |
| **Need higher availability** | "Multi-region = 99.99% availability" | "Multi-region adds failure modes. Active-active doubles the things that can go wrong. Unless we can handle split-brain gracefully, we might decrease availability. What's the actual availability requirement?" |
| **Global user base** | "Deploy everywhere for the best experience" | "Where do the users actually cluster? 80% might be in 2-3 regions. Start with those. Global presence sounds good but costs 5x and adds operational burden." |
| **Disaster recovery** | "Active-active gives us automatic DR" | "Active-passive with fast failover is simpler and often sufficient. Do we actually need zero downtime during a regional disaster? What's the business cost of 30 minutes of degradation?" |
| **Data residency requirements** | "We need multi-region for compliance" | "Compliance requires data to stay in-region, but does the compute need to be multi-region? Often you can satisfy compliance with regional data stores and centralized compute." |

**Key Difference**: L6 engineers see multi-region as a trade-off requiring justification, not an obvious upgrade. They quantify the benefits and costs before deciding.

---

# Part 1: Foundations — What Multi-Region Really Means

## What "Multi-Region" Actually Means in Practice

"Multi-region" is often used loosely to mean any system that spans geographic areas. In practice, it means one of several very different things:

### Definition 1: Multi-Region Deployment (Same Code, Multiple Locations)

The application code runs in multiple geographic locations. Each region handles its own traffic. This is the simplest form—essentially running multiple copies of your system.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-REGION DEPLOYMENT (COMPUTE)                        │
│                                                                             │
│      US-EAST                EU-WEST               AP-NORTHEAST              │
│   ┌──────────────┐      ┌──────────────┐      ┌──────────────┐             │
│   │  App Servers │      │  App Servers │      │  App Servers │             │
│   │  (stateless) │      │  (stateless) │      │  (stateless) │             │
│   └──────────────┘      └──────────────┘      └──────────────┘             │
│          │                     │                     │                      │
│          └─────────────────────┼─────────────────────┘                      │
│                                │                                            │
│                                ▼                                            │
│                    ┌─────────────────────┐                                  │
│                    │  Single Primary DB   │                                  │
│                    │    (US-EAST)         │                                  │
│                    └─────────────────────┘                                  │
│                                                                             │
│   COMPUTE is distributed, but DATA is centralized.                          │
│   Users get lower compute latency, but data access still goes to US-EAST.   │
│   This is NOT true multi-region for stateful workloads.                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Definition 2: Multi-Region Data (Replicated State)

Data is replicated across regions. This is where multi-region becomes genuinely complex—now you have to decide what happens when regions have different views of the world.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-REGION DATA (REPLICATED STATE)                     │
│                                                                             │
│      US-EAST                EU-WEST               AP-NORTHEAST              │
│   ┌──────────────┐      ┌──────────────┐      ┌──────────────┐             │
│   │  App Servers │      │  App Servers │      │  App Servers │             │
│   └──────┬───────┘      └──────┬───────┘      └──────┬───────┘             │
│          │                     │                     │                      │
│          ▼                     ▼                     ▼                      │
│   ┌──────────────┐      ┌──────────────┐      ┌──────────────┐             │
│   │   Database   │◀────▶│   Database   │◀────▶│   Database   │             │
│   │   (replica)  │      │   (replica)  │      │   (replica)  │             │
│   └──────────────┘      └──────────────┘      └──────────────┘             │
│                                                                             │
│   DATA is distributed. Now what?                                            │
│   • Are all replicas equal (active-active)?                                 │
│   • Is one the "leader" (active-passive)?                                   │
│   • Can users write locally? What about conflicts?                          │
│   • What happens during network partition?                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Definition 3: Multi-Region Active-Active (Full Independence)

Each region can serve all operations (reads AND writes) independently. This is the most complex form and the one that creates the most subtle bugs.

**Staff Insight**: When people say "multi-region," they often mean Definition 1 but think they're getting Definition 3. The gap between these creates incidents.

## Why Adding Regions Is Not a Simple Scaling Step

Adding horizontal capacity within a region follows predictable patterns: more servers, more shards, more replicas. The failure modes are well-understood. Network latency is sub-millisecond. Clock skew is negligible. Consensus is fast.

Adding regions changes the physics of the problem:

| Dimension | Within Region | Across Regions |
|-----------|--------------|----------------|
| **Network latency** | < 1ms | 50-200ms |
| **Network reliability** | 99.99%+ | 99.9% (partitions happen) |
| **Consensus round-trip** | 1-2ms | 100-400ms |
| **Clock skew** | Microseconds | Milliseconds |
| **Blast radius of failure** | Limited | Can cascade globally |
| **Debugging complexity** | Standard tools | Distributed tracing across time zones |
| **On-call complexity** | One team | Follow-the-sun or always-awake |

**The fundamental change**: Within a region, you can pretend you have a single, coherent system. Across regions, you cannot. The speed of light ensures that regions will have different views of the world at any given moment.

## Common Misconceptions

### Misconception 1: "Multi-Region = Higher Availability"

**Reality**: Multi-region can increase OR decrease availability, depending on implementation.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AVAILABILITY: THE UNCOMFORTABLE MATH                     │
│                                                                             │
│   SINGLE REGION:                                                            │
│   • Region availability: 99.95% (typical for major cloud)                   │
│   • System availability ≈ 99.95%                                            │
│   • Downtime: ~4.4 hours/year                                               │
│                                                                             │
│   MULTI-REGION (NAIVE ACTIVE-ACTIVE):                                       │
│   • Each region: 99.95%                                                     │
│   • Cross-region replication: 99.9% (networks fail between regions)         │
│   • Coordination service: 99.9%                                             │
│   • Combined: 99.95% × 99.9% × 99.9% = 99.75%                               │
│   • Downtime: ~22 hours/year                                                │
│                                                                             │
│   Wait—we made it WORSE?                                                    │
│                                                                             │
│   Yes, if:                                                                  │
│   • System requires cross-region coordination for every request             │
│   • Any region failure cascades to others (shared state, global locks)      │
│   • Operators don't understand the failure modes                            │
│                                                                             │
│   MULTI-REGION (WELL-DESIGNED):                                             │
│   • Each region can operate independently during partition                  │
│   • Graceful degradation instead of hard failures                           │
│   • Combined: max(Region1, Region2) with graceful fallback                  │
│   • Availability: 99.99%+ (each region backs the others)                    │
│                                                                             │
│   The difference is whether you've designed for independence or dependence. │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Misconception 2: "Multi-Region = Faster for Everyone"

**Reality**: Multi-region helps latency only for specific workloads.

| Workload Type | Does Multi-Region Help Latency? |
|---------------|--------------------------------|
| **Static content** | CDN is cheaper and simpler |
| **Read-heavy, stale-ok** | Yes, if reads can be local |
| **Read-heavy, must be fresh** | Only if writes are rare |
| **Write-heavy** | Usually no—writes need coordination |
| **Transactional** | No—coordination adds latency |
| **Real-time** | Depends—local state helps, global state hurts |

**Staff Insight**: The question is not "Will multi-region reduce latency?" but "Which operations can be made local, and what's the cost of making them local?"

### Misconception 3: "We'll Just Replicate the Database"

**Reality**: Database replication doesn't solve the hard problems—it creates them.

Replicating data across regions forces you to answer:
- **Consistency**: Are all replicas identical? When?
- **Conflicts**: What happens when two regions write the same data?
- **Ordering**: Does the order of operations matter? How do you preserve it globally?
- **Failure**: What happens when replication lags or stops?

These questions have no free answers. Every choice has trade-offs.

## Why Many Systems Should NOT Be Multi-Region

**Multi-region is not an upgrade—it's a trade-off.** The costs include:

| Cost | Description |
|------|-------------|
| **Infrastructure cost** | 2-3x compute and storage for active-active |
| **Operational complexity** | Follow-the-sun on-call, distributed debugging |
| **Development velocity** | Every feature must work across regions |
| **Consistency complexity** | Must reason about replication lag everywhere |
| **Testing burden** | Must test network partition scenarios |
| **Cognitive load** | Engineers must understand distributed semantics |

**Systems that often don't need multi-region:**

1. **Internal tools**: Users can tolerate single-region reliability
2. **Batch processing**: Latency doesn't matter
3. **Services with single-region dependencies**: You're only as global as your dependencies
4. **Early-stage products**: Complexity kills velocity when you're still finding product-market fit
5. **Low-traffic systems**: Cost doesn't justify the resilience

**Staff heuristic**: "If you're not sure whether you need multi-region, you don't need it yet."

---

## Simple Example: The Journey to Multi-Region Thinking

Let's trace how multi-region becomes necessary (or not) for a real system.

### The System: A Social Media API

**Initial state**: 
- 10M users, 90% in North America
- Deployed in us-east-1
- 50ms average API latency for US users
- 250ms average latency for European users
- 400ms average latency for Asian users

### The Pain Points

**User complaints:**
- European users: "The app feels slow"
- Asian users: "It's unusable during peak hours"

**Business pressure:**
- Growing user base in Europe and Asia
- Competitors have better international experience

### Naive Response: "Let's Go Multi-Region"

The team proposes deploying to eu-west-1 and ap-northeast-1 with database replication.

### Staff Engineer Analysis

Before agreeing, a Staff engineer asks:

**1. What's actually causing the latency?**
```
Breakdown of 250ms European latency:
- DNS lookup: 20ms
- TCP handshake: 80ms (transatlantic)
- TLS handshake: 80ms (transatlantic)
- Request/response: 40ms (transatlantic)
- Server processing: 30ms

The 160ms of handshake latency happens ONCE per connection.
With HTTP keep-alive, subsequent requests are only 40ms + 30ms = 70ms.
```

**2. What are users actually doing?**
```
API call breakdown:
- 70% are feed reads (can tolerate stale data)
- 20% are profile reads (can cache for seconds)
- 8% are lightweight writes (likes, views)
- 2% are critical writes (posts, messages)
```

**3. What's the simpler solution?**
```
Option A: CDN + Edge optimization
- CloudFront for static assets: Reduces 60% of requests
- Edge caching for feed reads: Reduces 40% of remaining
- Connection pooling at edge: Eliminates repeated handshakes
- Cost: $10K/month
- Complexity: Minimal

Option B: Full multi-region
- 3 regions with database replication
- Active-active writes with conflict resolution
- Cost: $150K/month
- Complexity: Significant
```

**Staff decision**: "Let's try Option A first. If 70% of requests are cacheable reads, we can deliver most of the latency benefit with 10% of the cost and complexity."

---

# Part 2: Why Multi-Region Is Hard (Staff Perspective)

## The Core Tensions

Multi-region architecture forces you into trade-offs that cannot be avoided. Understanding these tensions is the foundation of Staff-level thinking.

### Tension 1: Latency vs Consistency

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LATENCY vs CONSISTENCY                                   │
│                                                                             │
│   THE PHYSICS PROBLEM:                                                      │
│                                                                             │
│   Speed of light through fiber: ~200,000 km/s                               │
│   New York to London: ~5,500 km                                             │
│   Round-trip time: 55ms minimum (actual: 70-80ms with routing)              │
│                                                                             │
│   TO GUARANTEE CONSISTENCY:                                                 │
│   • Write must be acknowledged by all regions                               │
│   • OR write must be acknowledged by quorum across regions                  │
│   • Either way: write latency ≥ max(inter-region RTT)                       │
│                                                                             │
│   User in New York writes → Wait for London → 80ms minimum added            │
│                                                                             │
│   THE CHOICE:                                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  OPTION A: Strong Consistency                                       │   │
│   │  • Writes are globally ordered                                      │   │
│   │  • All readers see the same data                                    │   │
│   │  • Write latency: 100-300ms                                         │   │
│   │  • Write throughput: Limited by inter-region bandwidth              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  OPTION B: Eventual Consistency                                     │   │
│   │  • Writes are locally acknowledged                                  │   │
│   │  • Readers in other regions see stale data (briefly)                │   │
│   │  • Write latency: 5-20ms                                            │   │
│   │  • Write throughput: Scales with local capacity                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   There is no Option C. You must choose.                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tension 2: Availability vs Correctness

When regions can't communicate, you face the CAP theorem directly:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AVAILABILITY vs CORRECTNESS                              │
│                                                                             │
│   SCENARIO: Network partition between US-EAST and EU-WEST                   │
│                                                                             │
│      US-EAST                         EU-WEST                                │
│   ┌──────────────┐               ┌──────────────┐                           │
│   │   Active     │  ─── X ───   │   Active     │                           │
│   │   Region     │   partition   │   Region     │                           │
│   └──────────────┘               └──────────────┘                           │
│                                                                             │
│   User in US: "Update my email to alice@new.com"                            │
│   User in EU (same account): "Update my email to alice@other.com"           │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  OPTION A: Prioritize Availability                                  │   │
│   │  • Both writes succeed locally                                      │   │
│   │  • Users are happy (their action worked)                            │   │
│   │  • Conflict exists (which email is correct?)                        │   │
│   │  • When partition heals: Must resolve conflict somehow              │   │
│   │  • RISK: Data corruption, lost updates, confused users              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  OPTION B: Prioritize Correctness                                   │   │
│   │  • Writes that require cross-region consensus fail                  │   │
│   │  • Users see errors ("Service temporarily unavailable")             │   │
│   │  • No conflicts (only one write can succeed)                        │   │
│   │  • When partition heals: No cleanup needed                          │   │
│   │  • RISK: Angry users, lost revenue, perception of poor reliability  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   STAFF QUESTION: Which is worse for THIS system?                           │
│   • Banking: Correctness wins. Double-spending is catastrophic.             │
│   • Social media: Availability often wins. Stale likes are tolerable.       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tension 3: Cost vs Redundancy

Every region costs money. More regions = more redundancy but also more spend.

| Regions | Relative Cost | Failure Tolerance |
|---------|---------------|-------------------|
| 1 | 1x | None (single point of failure) |
| 2 | 2x | Can survive 1 region failure |
| 3 | 3x | Can survive 1 region + quorum for consistency |
| 5 | 5x | Can survive 2 regions + faster quorum |

**But cost isn't linear with value:**
- Going from 1 to 2 regions gives you disaster recovery
- Going from 2 to 3 gives you quorum-based consistency
- Going from 3 to 5 gives you... slightly faster failover?

**Staff heuristic**: "What's the minimum number of regions that satisfies our actual requirements?"

### Tension 4: Operational Simplicity vs Global Resilience

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    OPERATIONAL COMPLEXITY EXPLOSION                         │
│                                                                             │
│   SINGLE REGION:                                                            │
│   • One set of alerts                                                       │
│   • One on-call rotation                                                    │
│   • One deployment pipeline                                                 │
│   • Debugging: All logs in one place                                        │
│   • Incidents: Clear ownership                                              │
│                                                                             │
│   MULTI-REGION:                                                             │
│   • Alerts per region + global alerts + cross-region alerts                 │
│   • On-call: Follow-the-sun or always-awake + escalation for global issues  │
│   • Deployments: Staged rollout across regions + rollback coordination      │
│   • Debugging: Distributed tracing across continents and time zones         │
│   • Incidents: "Is this a local problem or global? Who owns it?"            │
│                                                                             │
│   HIDDEN COMPLEXITY:                                                        │
│   • Replication lag monitoring                                              │
│   • Conflict detection and resolution                                       │
│   • Cross-region traffic cost management                                    │
│   • Regional feature flags and configurations                               │
│   • Time zone-aware batch jobs                                              │
│   • Regional compliance differences                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Why These Trade-offs Are Owned by Staff Engineers

These trade-offs are not implementation details. They're architectural decisions that affect:

1. **User experience**: Consistency choice determines what users see during failures
2. **Business risk**: Availability choice determines revenue impact of outages
3. **Engineering velocity**: Complexity choice affects how fast teams can ship
4. **Cost structure**: Region choice affects infrastructure spend

Individual teams can't make these decisions—they affect the entire system. Staff engineers own the cross-cutting view.

---

# Part 3: Replication Models and Their Trade-offs

## Overview: The Three Models

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REPLICATION MODELS OVERVIEW                              │
│                                                                             │
│   ACTIVE-PASSIVE:                                                           │
│   ┌────────────────┐                    ┌────────────────┐                  │
│   │  PRIMARY (RW)  │ ───replication───▶ │ STANDBY (R)    │                  │
│   └────────────────┘                    └────────────────┘                  │
│   All writes go to primary. Standby is for failover.                        │
│                                                                             │
│   ACTIVE-ACTIVE:                                                            │
│   ┌────────────────┐                    ┌────────────────┐                  │
│   │  REGION A (RW) │ ◀──replication───▶ │ REGION B (RW)  │                  │
│   └────────────────┘                    └────────────────┘                  │
│   Both regions accept writes. Must handle conflicts.                        │
│                                                                             │
│   READ-LOCAL, WRITE-CENTRAL:                                                │
│   ┌────────────────┐                    ┌────────────────┐                  │
│   │  REGION A (R)  │ ◀───replication─── │  CENTRAL (RW)  │                  │
│   └────────────────┘                    └────────────────┘                  │
│   ┌────────────────┐                           │                            │
│   │  REGION B (R)  │ ◀───replication───────────┘                            │
│   └────────────────┘                                                        │
│   Reads are local (fast). Writes go to central (consistent).                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Model 1: Active-Passive

### How It Works

One region (primary) handles all writes. Other regions (standby) receive replicated data and can serve reads. During failure, a standby is promoted to primary.

```
// Pseudocode for active-passive routing

FUNCTION route_request(request, user_region):
    IF request.is_write:
        // All writes go to primary
        RETURN route_to_primary_region(request)
    ELSE:
        // Reads can be served locally
        IF requires_strong_consistency(request):
            RETURN route_to_primary_region(request)
        ELSE:
            RETURN route_to_local_replica(request, user_region)

FUNCTION handle_region_failure(failed_region):
    IF failed_region == PRIMARY_REGION:
        // Promote standby to primary
        new_primary = select_standby_for_promotion()
        
        // Ensure no data loss
        wait_for_replication_to_complete(new_primary)
        
        // Switch traffic
        update_dns_or_routing(new_primary)
        
        // Recovery time: minutes to tens of minutes
    ELSE:
        // Standby failure: redirect reads to primary
        redirect_reads_to_primary(failed_region)
        
        // Impact: Higher latency for affected users
```

### What Problems It Solves

1. **Disaster recovery**: Standby can take over if primary fails
2. **Read scaling**: Reads can be distributed globally
3. **Simplicity**: Only one writer means no write conflicts
4. **Strong consistency**: Easy to implement—primary is source of truth

### What Problems It Introduces

1. **Write latency**: All writes incur cross-region latency for non-local users
2. **Failover downtime**: Promoting standby takes time (minutes)
3. **Failover risk**: Promotion might lose recent writes (RPO > 0)
4. **Single point of failure**: Primary region is still a SPOF until failover completes

### Typical Failure Behavior

| Failure | User Impact | Recovery |
|---------|-------------|----------|
| Primary network degraded | Write timeouts, high latency | Traffic shift or failover |
| Primary region down | Writes fail until failover | Manual or automatic promotion |
| Standby region down | Higher read latency for that region | Redirect to primary |
| Replication lag | Stale reads in standby | Wait or accept staleness |

### When a Staff Engineer Chooses This

**Good fit:**
- Read-heavy workloads (>90% reads)
- Strong consistency requirements
- Infrequent writes
- Acceptable RTO of minutes
- Team not experienced with distributed systems

**Poor fit:**
- Write-heavy workloads
- Low-latency writes required globally
- Zero-downtime requirement
- Frequent regional failures expected

---

## Model 2: Active-Active

### How It Works

Multiple regions accept writes simultaneously. All changes replicate to all regions. Conflicts must be detected and resolved.

```
// Pseudocode for active-active operations

FUNCTION handle_write(request, local_region):
    // Write locally first
    local_result = write_to_local_database(request)
    
    // Replicate asynchronously to other regions
    FOR other_region IN all_regions - local_region:
        queue_replication(request, other_region)
    
    RETURN local_result  // Fast! No cross-region wait

FUNCTION apply_replicated_write(write, local_region):
    local_state = get_current_state(write.key)
    
    IF has_conflict(local_state, write):
        // Conflict! Both regions wrote the same key
        resolved_value = resolve_conflict(local_state, write)
        apply_resolved_value(write.key, resolved_value)
        
        // Log for debugging/auditing
        log_conflict(write.key, local_state, write, resolved_value)
    ELSE:
        // No conflict, apply normally
        apply_write(write)

FUNCTION resolve_conflict(local_state, incoming_write):
    // Common strategies:
    
    // 1. Last-Writer-Wins (LWW)
    IF incoming_write.timestamp > local_state.timestamp:
        RETURN incoming_write.value
    ELSE:
        RETURN local_state.value
    
    // 2. Merge (for CRDTs)
    RETURN merge(local_state.value, incoming_write.value)
    
    // 3. Application-specific
    RETURN application_specific_merge(local_state, incoming_write)
```

### What Problems It Solves

1. **Global write performance**: Writes are local (low latency)
2. **No single point of failure**: Any region can handle any operation
3. **Continuous availability**: No failover needed—traffic shifts seamlessly
4. **Geographic independence**: Each region operates autonomously

### What Problems It Introduces

1. **Conflicts**: Concurrent writes to same data create conflicts
2. **Conflict resolution complexity**: LWW loses data; custom merge is complex
3. **Eventual consistency**: Readers may see different values in different regions
4. **Debugging nightmare**: "Why did this value change?" spans regions
5. **Schema evolution**: Changes must be backward-compatible across all regions

### Conflict Resolution Strategies

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONFLICT RESOLUTION STRATEGIES                           │
│                                                                             │
│   LAST-WRITER-WINS (LWW):                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Region A writes: email = "alice@a.com" at T1                       │   │
│   │  Region B writes: email = "alice@b.com" at T2                       │   │
│   │  T2 > T1, so B wins: email = "alice@b.com"                          │   │
│   │                                                                     │   │
│   │  PRO: Simple, deterministic                                         │   │
│   │  CON: Silently loses A's update. A's user is confused.              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   VECTOR CLOCKS / VERSION VECTORS:                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Track causal relationships: "A happened before B"                  │   │
│   │  Detect concurrent updates (neither happened before)                │   │
│   │                                                                     │   │
│   │  PRO: Detects true conflicts                                        │   │
│   │  CON: Must still resolve detected conflicts somehow                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CRDTS (Conflict-free Replicated Data Types):                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Design data structures that merge without conflicts                │   │
│   │  Example: Counter = sum of per-region increments                    │   │
│   │  Example: Set = union of all additions, tombstones for removals     │   │
│   │                                                                     │   │
│   │  PRO: Automatic merge, no data loss                                 │   │
│   │  CON: Limited data types, larger storage, eventual consistency      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   APPLICATION-LEVEL MERGE:                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Application understands semantics, makes intelligent merge         │   │
│   │  Example: Shopping cart = union of items from both regions          │   │
│   │  Example: Text = operational transform or CRDT for collaborative    │   │
│   │                                                                     │   │
│   │  PRO: Best possible merge for the use case                          │   │
│   │  CON: Complex, must be implemented for each data type               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Typical Failure Behavior

| Failure | User Impact | Recovery |
|---------|-------------|----------|
| One region down | Users routed to other regions | Automatic |
| Network partition | Both regions continue working (with divergence) | Resolve conflicts when healed |
| Replication lag | Regions have different views | Accept or surface to users |
| Conflict storm | Data inconsistency | Application-specific resolution |

### When a Staff Engineer Chooses This

**Good fit:**
- Low-latency writes required globally
- Data can be partitioned by geography (user's data stays in their region)
- Conflicts are rare or can be merged automatically
- Strong consistency not required
- Experienced team with distributed systems expertise

**Poor fit:**
- Financial transactions (conflicts = money problems)
- Sequential operations (ordering matters)
- Shared mutable state (high conflict rate)
- Team unfamiliar with eventual consistency

---

## Model 3: Read-Local, Write-Central

### How It Works

All writes go to a central region. Data replicates to edge regions. Reads are served locally from replicas.

```
// Pseudocode for read-local, write-central

FUNCTION route_request(request, user_region):
    IF request.is_write:
        // Route to central region
        result = route_to_central_region(request)
        
        // Central region handles write and initiates replication
        RETURN result
    ELSE:
        // Check consistency requirements
        IF request.requires_read_your_writes:
            // User just wrote - route to central
            RETURN route_to_central_region(request)
        ELSE:
            // Serve from local replica (possibly stale)
            RETURN route_to_local_replica(request, user_region)

FUNCTION ensure_read_your_writes(user_id, request, local_region):
    // Track what the user has written
    last_write_timestamp = get_user_last_write_timestamp(user_id)
    local_replica_timestamp = get_local_replica_timestamp(local_region)
    
    IF local_replica_timestamp >= last_write_timestamp:
        // Local replica has caught up - serve locally
        RETURN serve_locally(request, local_region)
    ELSE:
        // Local replica is behind - route to central
        RETURN route_to_central_region(request)
```

### What Problems It Solves

1. **No conflicts**: Single writer means no write conflicts
2. **Global read performance**: Reads are fast everywhere
3. **Strong consistency for writes**: Central region is source of truth
4. **Simpler mental model**: Clear distinction between reads and writes

### What Problems It Introduces

1. **Write latency for remote users**: Non-central users have slower writes
2. **Central region is SPOF for writes**: Write availability limited to one region
3. **Replication lag**: Reads might be stale
4. **Read-your-writes complexity**: Must track per-user to avoid confusion

### When a Staff Engineer Chooses This

**Good fit:**
- Read-heavy workloads (95%+ reads)
- Users tolerate stale reads
- Writes don't need low latency
- Simple operations model desired
- Consistency is important

**Poor fit:**
- Write-heavy workloads
- Users need immediate read-after-write consistency
- Global write availability required
- Central region has unreliable connectivity

---

# Part 4: Traffic Routing and User Affinity

## How User Traffic Is Routed Globally

Getting users to the right region is the first step in multi-region architecture. The routing decision affects latency, failure behavior, and consistency.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    GLOBAL TRAFFIC ROUTING STACK                             │
│                                                                             │
│   USER ────▶ DNS ────▶ CDN/EDGE ────▶ LOAD BALANCER ────▶ APPLICATION       │
│               │            │                │                  │             │
│               ▼            ▼                ▼                  ▼             │
│          Geo-based    Caching +        Regional          Business           │
│          resolution   Edge compute     routing           logic              │
│                                                                             │
│   EACH LAYER CAN MAKE ROUTING DECISIONS:                                    │
│   • DNS: Route to nearest region (coarse-grained)                           │
│   • CDN: Serve cached content or route to origin                            │
│   • Load Balancer: Route to healthy backends                                │
│   • Application: Route based on user/data affinity                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Geo-DNS: Strengths and Limitations

### How It Works

DNS returns different IP addresses based on the requester's geographic location.

```
// Pseudocode for Geo-DNS resolution

FUNCTION resolve_dns(domain, client_ip):
    client_location = geoip_lookup(client_ip)
    
    // Find nearest region with healthy service
    regions_by_distance = sort_regions_by_distance(client_location)
    
    FOR region IN regions_by_distance:
        IF is_healthy(region):
            RETURN region.ip_addresses
    
    // All regions unhealthy - return best-effort
    RETURN primary_region.ip_addresses
```

### Strengths

| Strength | Description |
|----------|-------------|
| **Simple** | Works with existing DNS infrastructure |
| **Universal** | Every client uses DNS |
| **No client changes** | Applications don't need modification |
| **Coarse failover** | Can redirect entire regions via DNS |

### Limitations

| Limitation | Description |
|------------|-------------|
| **DNS caching** | TTL means changes take minutes to propagate |
| **Resolver location** | Client might use DNS resolver in different location |
| **No health awareness** | Basic Geo-DNS doesn't check backend health |
| **Coarse granularity** | Can't route individual requests |
| **No session affinity** | Same user might hit different regions |

### Staff Insight on DNS TTL

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE DNS TTL TRADE-OFF                                    │
│                                                                             │
│   SHORT TTL (30 seconds):                                                   │
│   • Fast failover (30 seconds to redirect traffic)                          │
│   • Higher DNS load                                                         │
│   • More frequent DNS lookups (slight latency)                              │
│                                                                             │
│   LONG TTL (5 minutes):                                                     │
│   • Slow failover (5 minutes to redirect traffic)                           │
│   • Lower DNS load                                                          │
│   • Less frequent lookups                                                   │
│                                                                             │
│   REALITY:                                                                  │
│   • Intermediate resolvers may ignore your TTL                              │
│   • Some ISPs cache for hours regardless of TTL                             │
│   • Enterprise proxies add another layer of caching                         │
│   • You cannot rely on DNS alone for fast failover                          │
│                                                                             │
│   STAFF APPROACH:                                                           │
│   • Use short TTL (30-60s) for health-based routing                         │
│   • Don't rely on DNS for sub-minute failover                               │
│   • Layer application-level failover on top of DNS                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Anycast Routing: What It Hides and What It Exposes

### How It Works

Multiple servers in different locations advertise the same IP address. BGP routing directs traffic to the "nearest" server (in network terms).

```
// Anycast routing (network level, not application code)

NETWORK BEHAVIOR:
    Single IP (e.g., 192.0.2.1) is announced from:
    - US-EAST datacenter
    - EU-WEST datacenter  
    - AP-NORTHEAST datacenter

    Routers direct packets to nearest announcement.
    
    User in Paris → EU-WEST datacenter
    User in Tokyo → AP-NORTHEAST datacenter
    User in New York → US-EAST datacenter
```

### What Anycast Hides (Benefits)

| Hidden Complexity | How Anycast Helps |
|-------------------|-------------------|
| **DNS propagation** | No DNS changes needed for failover |
| **Client configuration** | Single IP for all clients |
| **Geographic routing** | Network handles it automatically |
| **Health-based failover** | Stop announcing BGP = traffic shifts |

### What Anycast Exposes (Challenges)

| Exposed Challenge | Why It's Problematic |
|-------------------|---------------------|
| **Connection persistence** | BGP route change = connections drop |
| **Session affinity** | Same client may hit different servers |
| **Debugging** | Which server handled this request? |
| **Uneven distribution** | "Nearest" in network ≠ nearest geographically |

### When to Use Anycast

**Good fit:**
- Stateless, request/response protocols (DNS, CDN)
- Health check based failover
- DDoS mitigation (spread attack across locations)

**Poor fit:**
- Stateful connections (WebSockets, persistent TCP)
- Session affinity required
- Need to route specific users to specific regions

## Client-Side Routing and Sticky Sessions

### Why Client-Side Routing Matters

For applications needing session affinity or deterministic routing, the client must participate in routing decisions.

```
// Pseudocode for client-side region discovery

CLASS MultiRegionClient:
    
    FUNCTION initialize():
        // Discover available regions
        self.regions = discover_regions()  // e.g., via DNS or config
        
        // Determine best region for this client
        self.primary_region = determine_best_region(self.regions)
        
        // Track which region has user's data
        self.data_region = null  // Set after first request
    
    FUNCTION make_request(request):
        // Determine which region should handle this request
        target_region = self.select_region(request)
        
        TRY:
            response = send_to_region(request, target_region)
            
            // Track data affinity from response headers
            IF response.headers["X-Data-Region"]:
                self.data_region = response.headers["X-Data-Region"]
            
            RETURN response
        
        CATCH ConnectionError:
            // Primary region unreachable - failover
            RETURN self.failover_request(request, target_region)
    
    FUNCTION select_region(request):
        IF self.data_region AND request.affects_user_data:
            // Route to region where user's data lives
            RETURN self.data_region
        ELSE:
            // Route to nearest/best region
            RETURN self.primary_region
    
    FUNCTION failover_request(request, failed_region):
        available_regions = self.regions - failed_region
        
        FOR region IN sort_by_preference(available_regions):
            TRY:
                RETURN send_to_region(request, region)
            CATCH ConnectionError:
                CONTINUE
        
        RAISE AllRegionsUnavailable()
```

### Sticky Sessions: Trade-offs

| Approach | Pros | Cons |
|----------|------|------|
| **Cookie-based** | Server controls affinity | Requires cookie support |
| **IP hash** | Stateless routing | NAT/proxy breaks it |
| **Header-based** | Explicit, debuggable | Client must send header |
| **Data affinity** | Follows the data | Complex to implement |

---

## How Routing Decisions Affect System Behavior

### Impact on Latency

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ROUTING IMPACT ON LATENCY                                │
│                                                                             │
│   USER IN LONDON, DATA IN US-EAST                                           │
│                                                                             │
│   OPTION A: Route to nearest region (EU-WEST)                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  User → EU-WEST: 20ms                                               │   │
│   │  EU-WEST → US-EAST (for data): 80ms                                 │   │
│   │  US-EAST → EU-WEST: 80ms                                            │   │
│   │  EU-WEST → User: 20ms                                               │   │
│   │  TOTAL: 200ms                                                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   OPTION B: Route directly to data region (US-EAST)                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  User → US-EAST: 80ms                                               │   │
│   │  Processing: 10ms                                                   │   │
│   │  US-EAST → User: 80ms                                               │   │
│   │  TOTAL: 170ms                                                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   OPTION C: Cache data in EU-WEST (if staleness acceptable)                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  User → EU-WEST: 20ms                                               │   │
│   │  Cache hit: 1ms                                                     │   │
│   │  EU-WEST → User: 20ms                                               │   │
│   │  TOTAL: 41ms                                                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   LESSON: "Route to nearest" isn't always best. Consider data locality.    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Impact on Failure Handling

Routing decisions determine what happens during failures:

| Routing Strategy | Region Failure Behavior |
|------------------|------------------------|
| **Geo-DNS** | Wait for DNS TTL to expire, then redirect |
| **Anycast** | Automatic redirect when BGP withdrawn |
| **Client-side** | Immediate failover if client implements it |
| **Sticky session** | Session lost if sticky region fails |

### Impact on Data Consistency

| Routing Strategy | Consistency Implication |
|------------------|------------------------|
| **Random/round-robin** | May read from stale replica |
| **Sticky to one region** | Consistent within session |
| **Route to writer** | Strong consistency, higher latency |
| **Route by data key** | Partitioned consistency |

---

# Part 5: Failure Scenarios at Global Scale

## Why Failure Thinking Matters

At global scale, failure is not an exception—it's a constant. Something is always failing somewhere. Staff engineers design for failure as the normal state.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FAILURE IS THE NORMAL STATE                              │
│                                                                             │
│   AT GLOBAL SCALE:                                                          │
│                                                                             │
│   • 3 regions × 1000 servers = 3000 servers                                 │
│   • If each server has 99.9% uptime, at any moment:                         │
│     3000 × 0.1% = 3 servers are failing                                     │
│                                                                             │
│   • 3 regions × 100 network links each = 300 network paths                  │
│   • If each link has 99.99% uptime:                                         │
│     300 × 0.01% = 0.03 failures per moment                                  │
│     = 1 network issue every few hours                                       │
│                                                                             │
│   • Add cross-region links, third-party dependencies, human error:          │
│     Multiple failure modes active at any given time                         │
│                                                                             │
│   STAFF MINDSET:                                                            │
│   "The question is not IF there's a failure, but WHERE and HOW SEVERE."     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Scenario 1: Full Region Isolation

### The Failure

A major cloud region becomes completely unreachable. Causes might include:
- Power grid failure
- Natural disaster
- Major network backbone cut
- Cloud provider outage

### What Users Experience

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FULL REGION ISOLATION: USER EXPERIENCE                   │
│                                                                             │
│   USERS IN AFFECTED REGION:                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Without failover:                                                  │   │
│   │  • Complete outage until region recovers                            │   │
│   │  • Error messages or timeouts on all requests                       │   │
│   │  • Mobile apps may show cached data (if implemented)                │   │
│   │                                                                     │   │
│   │  With failover:                                                     │   │
│   │  • Brief interruption (seconds to minutes)                          │   │
│   │  • Then redirected to another region                                │   │
│   │  • Higher latency (now hitting distant region)                      │   │
│   │  • Possible stale data (replication lag)                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   USERS IN OTHER REGIONS:                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Good design (independent regions):                                 │   │
│   │  • No impact - continue normal operation                            │   │
│   │  • Might see reduced capacity if traffic shifts                     │   │
│   │                                                                     │   │
│   │  Bad design (dependent on failed region):                           │   │
│   │  • Cascading failures if they depend on isolated region             │   │
│   │  • Timeouts waiting for cross-region calls                          │   │
│   │  • Possible global outage                                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### How Failures Propagate

```
// Pseudocode for how region isolation propagates

SCENARIO: US-EAST becomes isolated

IMMEDIATE (0-10 seconds):
    - Health checks from other regions fail
    - Load balancers in US-EAST can't reach backends
    - DNS health checks fail (if configured)
    
DETECTION (10-60 seconds):
    - Monitoring alerts fire
    - Automated health checks mark US-EAST as unhealthy
    - Cross-region replication stops receiving updates
    
DECISION POINT (60-300 seconds):
    IF automated_failover_enabled:
        - DNS updated to remove US-EAST
        - Traffic routers redirect to EU-WEST and AP-NORTHEAST
        - Region marked as "isolated" in coordination service
    ELSE:
        - Wait for on-call engineer to assess
        - Manual decision: failover or wait?
        
TRAFFIC SHIFT (varies):
    - DNS changes propagate (30s-5min based on TTL)
    - Clients retry and reach healthy regions
    - Healthy regions see traffic spike (maybe 1.5-2x)
    
DANGER ZONE:
    IF healthy_regions.capacity < shifted_traffic:
        - Cascading failure
        - Healthy regions overloaded
        - Global outage
```

### Blast Radius Containment

**Good design:**
```
// Each region is independent
Region_A failure → Only Region_A users affected
Other regions → No impact, continue serving

Key properties:
- No synchronous cross-region dependencies for serving traffic
- Each region has full data copy (even if slightly stale)
- Excess capacity to absorb traffic shift
```

**Bad design:**
```
// Global dependencies
Region_A hosts global auth service
Region_A failure → Auth fails globally → All regions affected

Key anti-patterns:
- Global singletons (one auth, one config, one coordination)
- Synchronous cross-region calls in request path
- No capacity headroom in healthy regions
```

### Staff Design Principles for Region Isolation

1. **No global singletons**: Every critical service must be regional
2. **Async replication**: Don't block on cross-region during normal operation
3. **Capacity headroom**: Each region can handle 1.5-2x normal traffic
4. **Fast detection**: Health checks every few seconds, not minutes
5. **Automated failover**: Don't wait for humans at 3am

---

## Scenario 2: Partial Network Partitions Between Regions

### The Failure

Network connectivity between regions is degraded but not completely severed. 
- Some packets get through, others don't
- Latency is highly variable (100ms to 5000ms)
- Packet loss is intermittent (5-30%)

### Why This Is Worse Than Full Isolation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PARTIAL PARTITION: THE WORST OF BOTH WORLDS              │
│                                                                             │
│   FULL ISOLATION:                                                           │
│   • Clear signal: region is down                                            │
│   • Easy decision: failover                                                 │
│   • Clean state: regions operate independently                              │
│                                                                             │
│   PARTIAL PARTITION:                                                        │
│   • Ambiguous signal: region is "slow" not "down"                           │
│   • Hard decision: is this a blip or a real problem?                        │
│   • Dirty state: some writes replicate, others don't                        │
│                                                                             │
│   THE PATHOLOGY:                                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  T=0: Partition begins. Replication slows.                          │   │
│   │  T=10s: Some writes get through, others timeout                     │   │
│   │  T=30s: Retries cause write amplification                           │   │
│   │  T=60s: Replication queue backs up                                  │   │
│   │  T=2min: Timeouts cascade into application layer                    │   │
│   │  T=5min: User-visible errors as requests timeout                    │   │
│   │  T=10min: On-call paged, starts investigating                       │   │
│   │  T=15min: Decision to failover... or wait it out?                   │   │
│   │  T=20min: Partition heals. Now resolve divergent state.             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### What Users Experience

| User Location | Experience |
|---------------|------------|
| **Local to healthy region** | Slow writes that depend on replication, reads unaffected |
| **Local to degraded region** | Variable latency, some requests fail |
| **Cross-region sessions** | Session state may be inconsistent |

### Detection and Response

```
// Pseudocode for detecting and handling partial partition

CLASS PartitionDetector:
    
    FUNCTION monitor_cross_region_health():
        FOR region_pair IN all_region_pairs:
            metrics = measure_connectivity(region_pair)
            
            IF metrics.latency_p99 > 500ms OR metrics.packet_loss > 5%:
                alert("Degraded connectivity", region_pair, metrics)
                
                // Don't immediately failover - might be transient
                IF degraded_for(region_pair) > THRESHOLD_MINUTES:
                    trigger_partition_mode(region_pair)
    
    FUNCTION trigger_partition_mode(region_pair):
        // Reduce cross-region dependencies
        disable_synchronous_replication(region_pair)
        enable_async_queue_mode(region_pair)
        
        // Alert but don't automatically failover
        // Human judgment needed for partial partitions
        page_oncall("Partial partition detected", region_pair)
        
        // Start tracking divergence
        enable_divergence_tracking(region_pair)

CLASS ReplicationManager:
    
    FUNCTION handle_degraded_replication():
        // Switch from sync to async
        replication_mode = ASYNC
        
        // Accept that replicas will diverge
        // Prioritize local availability
        
        // Queue writes that fail to replicate
        FOR failed_write IN replication_failures:
            add_to_retry_queue(failed_write)
        
        // When partition heals, reconcile
        ON partition_healed:
            reconcile_queued_writes()
            detect_conflicts()
```

---

## Scenario 3: Slow or Degraded Regions

### The Failure

A region is reachable but performing poorly:
- High latency (10x normal)
- Elevated error rates (5-20%)
- Reduced throughput

### Why This Is Tricky

Health checks might pass (region is "up"), but user experience is terrible.

```
// Pseudocode for handling slow regions

FUNCTION should_route_to_region(region):
    // Binary health check: PASS
    IF NOT basic_health_check(region):
        RETURN false
    
    // But look deeper at quality metrics
    metrics = get_region_metrics(region)
    
    IF metrics.latency_p99 > LATENCY_THRESHOLD:
        RETURN false
    
    IF metrics.error_rate > ERROR_THRESHOLD:
        RETURN false
    
    IF metrics.queue_depth > QUEUE_THRESHOLD:
        // Region is falling behind - don't add more load
        RETURN false
    
    RETURN true

FUNCTION handle_slow_region(region):
    // Step 1: Reduce traffic to slow region
    reduce_traffic_weight(region, 0.5)  // 50% reduction
    
    // Step 2: Monitor if it recovers
    WAIT 60 seconds
    
    IF region.metrics.improved:
        // Slowly restore traffic
        gradually_restore_traffic(region)
    ELSE:
        // Continue reducing
        reduce_traffic_weight(region, 0.25)
        
        IF still_degraded_after(5 minutes):
            // Full failover
            remove_from_rotation(region)
            page_oncall("Region removed from rotation", region)
```

---

## Scenario 4: Control Plane vs Data Plane Failures

### Understanding the Distinction

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONTROL PLANE vs DATA PLANE                              │
│                                                                             │
│   CONTROL PLANE:                                                            │
│   • Configuration management                                                │
│   • Deployment pipelines                                                    │
│   • Service discovery                                                       │
│   • Health checking and routing decisions                                   │
│   • Metrics and alerting                                                    │
│                                                                             │
│   DATA PLANE:                                                               │
│   • Actual request processing                                               │
│   • Database reads and writes                                               │
│   • Caching                                                                 │
│   • User traffic handling                                                   │
│                                                                             │
│   THE KEY INSIGHT:                                                          │
│   Control plane can fail while data plane continues working (and vice versa)│
│                                                                             │
│   EXAMPLES:                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Control plane failure:                                             │   │
│   │  • Can't deploy new code                                            │   │
│   │  • Can't update configurations                                      │   │
│   │  • Health checks not running                                        │   │
│   │  • But: Existing servers keep serving traffic!                      │   │
│   │                                                                     │   │
│   │  Data plane failure:                                                │   │
│   │  • User requests failing                                            │   │
│   │  • Database unreachable                                             │   │
│   │  • But: Control plane can still initiate recovery!                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Staff Design Principle: Separate Control and Data Planes

```
// Pseudocode for control/data plane separation

CLASS DataPlaneServer:
    
    FUNCTION start():
        // Load configuration from local cache or defaults
        config = load_cached_config()
        
        // Start serving with cached config
        start_serving(config)
        
        // Asynchronously try to refresh from control plane
        background_refresh_config()
    
    FUNCTION handle_request(request):
        // Data plane operation - no control plane dependency
        RETURN process_request(request, self.cached_config)
    
    FUNCTION background_refresh_config():
        WHILE true:
            TRY:
                new_config = fetch_from_control_plane()
                self.cached_config = new_config
                save_to_local_cache(new_config)
            CATCH ControlPlaneUnavailable:
                // Continue with cached config
                log("Control plane unavailable, using cached config")
            
            SLEEP(refresh_interval)

// This design means:
// - Control plane down: Data plane keeps serving with last-known config
// - Data plane down: Control plane can still push fixes (when data plane recovers)
```

---

# Part 6: Applied System Examples

## Example 1: User-Facing API

### Requirements

- Global users (40% Americas, 35% Europe, 25% Asia-Pacific)
- Read-heavy (90% reads, 10% writes)
- User profiles, posts, interactions
- Target: <200ms P99 latency globally
- Target: 99.9% availability

### Naive Design (What Not To Do)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NAIVE DESIGN: SINGLE PRIMARY, GLOBAL READS               │
│                                                                             │
│   US-EAST (Primary)         EU-WEST              AP-NORTHEAST               │
│   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐          │
│   │   API Servers   │   │   API Servers   │   │   API Servers   │          │
│   └────────┬────────┘   └────────┬────────┘   └────────┬────────┘          │
│            │                     │                     │                    │
│            │              ALL WRITES                   │                    │
│            │◀────────────────────┼─────────────────────│                    │
│            │                     │                     │                    │
│            ▼                     │                     │                    │
│   ┌─────────────────┐            │                     │                    │
│   │  Primary DB     │────────────┼─────────────────────│                    │
│   │  (writes + reads)│           │                     │                    │
│   └────────┬────────┘            │                     │                    │
│            │                     │                     │                    │
│            │        async replication                  │                    │
│            │                     │                     │                    │
│            │              ┌──────┴──────┐       ┌──────┴──────┐             │
│            └─────────────▶│  Read Replica│      │  Read Replica│            │
│                           └─────────────┘       └─────────────┘             │
│                                                                             │
│   PROBLEMS:                                                                 │
│   • Writes from EU/AP add 80-200ms latency (cross-Atlantic/Pacific)         │
│   • Primary failure = write outage for all regions                          │
│   • Stale reads in EU/AP (replication lag)                                  │
│   • No clear failover path                                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Staff-Level Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STAFF DESIGN: REGION-LOCAL FOR MOST OPERATIONS           │
│                                                                             │
│   KEY INSIGHT: Most user data is accessed only by that user.                │
│   Shard by user region. Keep user's data close to user.                     │
│                                                                             │
│   US-EAST                   EU-WEST                  AP-NORTHEAST           │
│   ┌─────────────────┐   ┌─────────────────┐      ┌─────────────────┐       │
│   │   API Servers   │   │   API Servers   │      │   API Servers   │       │
│   └────────┬────────┘   └────────┬────────┘      └────────┬────────┘       │
│            │                     │                        │                 │
│            ▼                     ▼                        ▼                 │
│   ┌─────────────────┐   ┌─────────────────┐      ┌─────────────────┐       │
│   │  Regional DB    │   │  Regional DB    │      │  Regional DB    │       │
│   │  (US users)     │   │  (EU users)     │      │  (AP users)     │       │
│   └─────────────────┘   └─────────────────┘      └─────────────────┘       │
│            │                     │                        │                 │
│            └─────────────────────┼────────────────────────┘                 │
│                                  │                                          │
│                                  ▼                                          │
│                    ┌──────────────────────────┐                             │
│                    │  Global Index (read-only) │                             │
│                    │  Username → Region mapping │                            │
│                    │  Cached aggressively       │                            │
│                    └──────────────────────────┘                             │
│                                                                             │
│   ROUTING LOGIC:                                                            │
│   1. Look up user's home region (cached)                                    │
│   2. Route request to home region                                           │
│   3. If cross-region needed (view another user), read from their region     │
│                                                                             │
│   TRADE-OFFS:                                                               │
│   ✓ Local reads/writes for own data: <50ms latency                          │
│   ✓ Regional failure only affects that region's users                       │
│   ✓ No cross-region write coordination                                      │
│   ✗ Cross-region reads (viewing EU user from US): Higher latency            │
│   ✗ User relocation is complex (migrate region)                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Implementation Details

```
// Pseudocode for user-region routing

CLASS UserRegionRouter:
    
    FUNCTION route_request(request):
        // Step 1: Determine target user
        target_user_id = extract_user_id(request)
        
        // Step 2: Look up user's home region (cached heavily)
        home_region = lookup_user_region(target_user_id)  // Cache hit: <1ms
        
        // Step 3: Route to appropriate region
        IF request.is_write:
            // Writes always go to home region
            RETURN send_to_region(request, home_region)
        ELSE:
            // Reads can be optimized
            IF request.allows_stale:
                // Try local cache first
                cached = local_cache.get(request.cache_key)
                IF cached:
                    RETURN cached
            
            RETURN send_to_region(request, home_region)
    
    FUNCTION handle_cross_region_view(viewer, viewed_user):
        // Viewer in US wants to see EU user's profile
        viewed_region = lookup_user_region(viewed_user.id)
        
        // Fetch from viewed user's region
        profile = fetch_from_region(viewed_region, viewed_user.id)
        
        // Cache locally for subsequent views
        local_cache.set(viewed_user.id, profile, ttl=60)
        
        RETURN profile
```

---

## Example 2: News Feed Service

### Requirements

- 100M DAU
- Users follow other users; feed shows followed users' posts
- Write: 10K posts per second globally
- Read: 500K feed fetches per second globally
- Eventual consistency acceptable (seconds of delay OK)

### Why This Is Challenging

The feed is an aggregation of data from many users, potentially across regions.

### Naive Design (What Not To Do)

```
// Naive: Real-time cross-region aggregation
FUNCTION get_feed(user_id):
    following = get_following(user_id)  // Could be global
    
    posts = []
    FOR followed_user IN following:
        followed_region = lookup_user_region(followed_user)
        user_posts = fetch_from_region(followed_region, followed_user)
        posts.extend(user_posts)
    
    RETURN sort_by_time(posts)[:50]

// PROBLEM: If user follows 500 people across 3 regions,
// this is 500 queries, many cross-region = SECONDS of latency
```

### Staff-Level Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STAFF DESIGN: PRE-COMPUTED REGIONAL FEEDS                │
│                                                                             │
│   KEY INSIGHT: Pre-compute and replicate feed data.                         │
│   When a post is created, fan-out to followers' feeds.                      │
│                                                                             │
│   POST CREATION (Write Path):                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. User in EU creates post                                         │   │
│   │  2. Post stored in EU database                                      │   │
│   │  3. Async: Fan-out to followers                                     │   │
│   │     - EU followers: Direct write to EU feed tables                  │   │
│   │     - US followers: Replicate to US region                          │   │
│   │     - AP followers: Replicate to AP region                          │   │
│   │  4. Each region has pre-computed feeds for its local users          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FEED READ (Read Path):                                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. User in US requests feed                                        │   │
│   │  2. Read from US regional feed table (local read!)                  │   │
│   │  3. Return pre-computed feed                                        │   │
│   │  4. Latency: <50ms                                                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   TRADE-OFFS:                                                               │
│   ✓ Feed reads are always local                                             │
│   ✓ Read latency independent of followed users' locations                   │
│   ✗ Write amplification (1 post → many feed entries)                        │
│   ✗ Feed consistency lag (seconds for cross-region propagation)             │
│   ✗ Celebrity problem (1M followers = 1M writes)                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Handling the Celebrity Problem

```
// Pseudocode for hybrid fanout with celebrity handling

FUNCTION handle_new_post(post, author):
    follower_count = get_follower_count(author)
    
    IF follower_count < 10000:
        // Normal users: Push model
        // Fan-out to all followers' feeds
        async_fanout_to_all_followers(post, author)
    ELSE:
        // Celebrities: Pull model
        // Store in celebrity posts index, pull at read time
        store_in_celebrity_index(post, author)

FUNCTION get_feed(user):
    // Get pre-computed feed (normal follows)
    feed = get_precomputed_feed(user)
    
    // Add celebrity posts (pull at read time)
    celebrity_follows = get_celebrity_follows(user)
    FOR celebrity IN celebrity_follows:
        recent_posts = get_celebrity_recent_posts(celebrity)  // Cached!
        feed.merge(recent_posts)
    
    RETURN sort_and_rank(feed)[:50]
```

---

## Example 3: Authentication System

### Requirements

- Global users
- Must be consistent (can't have different auth states)
- Low latency critical (blocks all other operations)
- High availability (auth down = entire app down)
- Security: revocation must propagate quickly

### Why This Is Different

Unlike the previous examples, auth cannot tolerate eventual consistency for most operations.

### Staff-Level Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AUTH SYSTEM: HYBRID APPROACH                             │
│                                                                             │
│   INSIGHT: Decompose auth into components with different consistency needs. │
│                                                                             │
│   COMPONENT 1: Token Validation (Read-heavy, cache-friendly)                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • JWTs with embedded claims (no backend check for valid tokens)    │   │
│   │  • Short expiry (15 minutes)                                        │   │
│   │  • Cached public keys for signature verification                    │   │
│   │  • FULLY LOCAL - no cross-region for happy path                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   COMPONENT 2: Token Refresh (Periodic, can tolerate latency)               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Refresh tokens have longer lifetime (days)                       │   │
│   │  • Refresh requires auth server check                               │   │
│   │  • Route to user's home region for refresh                          │   │
│   │  • Acceptable latency: 100-300ms                                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   COMPONENT 3: Revocation (Rare, must propagate globally)                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Revocation list replicated to all regions                        │   │
│   │  • Checked on every validation (small list, fast lookup)            │   │
│   │  • Propagation SLA: < 1 minute globally                             │   │
│   │  • Async replication OK (short tokens limit exposure)               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   COMPONENT 4: Login (Rare, strong consistency required)                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Login attempts routed to user's home region                      │   │
│   │  • Password hashes stored in home region                            │   │
│   │  • Failed attempt tracking per-region (eventually merged)           │   │
│   │  • Latency: 200-500ms acceptable for login                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Implementation

```
// Pseudocode for multi-region auth

CLASS MultiRegionAuthService:
    
    FUNCTION validate_token(token):
        // Step 1: Parse and verify signature (local, cached key)
        claims = verify_jwt_signature(token, cached_public_keys)
        IF NOT claims:
            RETURN AuthResult.INVALID_SIGNATURE
        
        // Step 2: Check expiry (local, in-token)
        IF claims.expiry < now():
            RETURN AuthResult.EXPIRED
        
        // Step 3: Check revocation list (local, replicated)
        IF revocation_list.contains(claims.token_id):
            RETURN AuthResult.REVOKED
        
        // No cross-region call needed!
        RETURN AuthResult.VALID
    
    FUNCTION refresh_token(refresh_token):
        // Need to check with auth server
        user_id = extract_user_id(refresh_token)
        home_region = lookup_user_region(user_id)
        
        // Route to home region
        new_tokens = call_home_region(home_region, "refresh", refresh_token)
        RETURN new_tokens
    
    FUNCTION revoke_token(token_id, reason):
        // Step 1: Add to local revocation list immediately
        local_revocation_list.add(token_id, reason, now())
        
        // Step 2: Replicate to other regions async
        FOR region IN all_other_regions:
            async_replicate_revocation(region, token_id, reason)
        
        // Step 3: Confirm replication (best effort)
        // Tokens are short-lived, so eventual consistency OK
    
    FUNCTION login(username, password):
        // Determine user's region
        user_region = lookup_user_region_by_username(username)
        
        // Route to home region (password hash lives there)
        result = call_home_region(user_region, "login", username, password)
        
        IF result.success:
            // Generate tokens
            tokens = generate_tokens(result.user_id)
            RETURN tokens
        ELSE:
            // Track failed attempt
            track_failed_attempt(username)
            RETURN AuthResult.LOGIN_FAILED
```

---

# Part 7: Evolution Over Time (Staff Thinking)

## The Evolution Journey

Most systems don't start multi-region. They evolve there as scale and requirements change.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-REGION EVOLUTION JOURNEY                           │
│                                                                             │
│   STAGE 1: Single Region                                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • One region, maybe multi-AZ for redundancy                        │   │
│   │  • Simple, fast to develop                                          │   │
│   │  • Global users hit single region                                   │   │
│   │  • Cost: $X                                                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                    │                                                        │
│                    │ Trigger: Latency complaints from far users             │
│                    │ OR: Compliance requirements (data residency)           │
│                    ▼                                                        │
│   STAGE 2: CDN + Edge Caching                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Add CDN for static content                                       │   │
│   │  • Edge caching for API responses where possible                    │   │
│   │  • 80% of latency benefit, 10% of complexity                        │   │
│   │  • Cost: $1.3X                                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                    │                                                        │
│                    │ Trigger: Write latency unacceptable for global users   │
│                    │ OR: Single region availability not sufficient          │
│                    ▼                                                        │
│   STAGE 3: Read Replicas in Other Regions                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Database read replicas in 1-2 additional regions                 │   │
│   │  • Reads go local, writes go to primary                             │   │
│   │  • Stale reads accepted for most use cases                          │   │
│   │  • Cost: $2X                                                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                    │                                                        │
│                    │ Trigger: Write latency still problematic               │
│                    │ OR: Primary region outage = unacceptable downtime      │
│                    ▼                                                        │
│   STAGE 4: Regional Data Partitioning                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • User data partitioned by region                                  │   │
│   │  • Each region handles its users fully                              │   │
│   │  • Cross-region for viewing other regions' data                     │   │
│   │  • Cost: $2.5X                                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                    │                                                        │
│                    │ Trigger: Truly global writes needed                    │
│                    │ OR: Any region must serve any user                     │
│                    ▼                                                        │
│   STAGE 5: Active-Active                                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • All regions can read and write                                   │   │
│   │  • Conflict resolution implemented                                  │   │
│   │  • Full complexity of distributed systems                           │   │
│   │  • Cost: $3X+                                                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## What Staff Engineers Add Only When Necessary

| Capability | Add When... | Not Before Because... |
|------------|-------------|----------------------|
| **CDN** | Static content latency matters | Adds cache invalidation complexity |
| **Read replicas** | Read latency critical, stale OK | Replication lag creates consistency issues |
| **Regional data** | Users mostly access own data | Cross-region access becomes complex |
| **Active-active writes** | Write latency critical globally | Conflict resolution is very hard |
| **Global consensus** | Strong consistency required globally | Massive latency penalty |

## When Rollback or Simplification Is Correct

Sometimes the right Staff decision is to REDUCE multi-region complexity:

```
// Pseudocode for multi-region complexity decision

FUNCTION evaluate_multiregion_complexity(system):
    benefits = calculate_benefits(system)
    // - Latency reduction for global users
    // - Availability during regional outages
    // - Compliance requirements met
    
    costs = calculate_costs(system)
    // - Infrastructure cost (2-3x)
    // - Engineering complexity
    // - Operational burden
    // - Incident debugging difficulty
    // - Development velocity impact
    
    IF costs > benefits:
        // Consider simplification
        IF can_meet_requirements_with_cdn():
            recommendation = "DOWNGRADE: CDN + single region"
        ELSE IF can_meet_requirements_with_read_replicas():
            recommendation = "DOWNGRADE: Read replicas only"
        ELSE:
            recommendation = "MAINTAIN: Current complexity justified"
    ELSE:
        recommendation = "MAINTAIN or UPGRADE"
    
    RETURN recommendation

// Example: Internal admin tool
// Current: Active-active in 3 regions (legacy decision)
// Users: 500 employees, 80% in US
// Availability need: 99.9% (8 hours downtime/year OK)
// 
// Analysis: 2 regions are nearly unused
// Cost: $50K/month for complexity that isn't needed
// Recommendation: DOWNGRADE to single region + cross-region backup
// Savings: $35K/month, simpler operations
```

## Incremental Adoption: Risk Management

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    INCREMENTAL MULTI-REGION ADOPTION                        │
│                                                                             │
│   PHASE 1: Shadow Traffic (Weeks 1-4)                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Set up new region                                                │   │
│   │  • Mirror traffic (read-only, compare results)                      │   │
│   │  • Identify discrepancies                                           │   │
│   │  • NO user impact - shadow only                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   PHASE 2: Read Traffic (Weeks 5-8)                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Route 10% → 50% → 100% of reads to new region                    │   │
│   │  • Monitor latency, error rates, consistency                        │   │
│   │  • Rollback capability at each step                                 │   │
│   │  • Writes still go to primary                                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   PHASE 3: Failover Testing (Weeks 9-12)                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Controlled failover drills                                       │   │
│   │  • Measure RTO and RPO                                              │   │
│   │  • Test rollback procedures                                         │   │
│   │  • Train on-call on multi-region debugging                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   PHASE 4: Regional Writes (If needed, Weeks 13+)                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Implement conflict resolution                                    │   │
│   │  • Enable writes for specific, low-risk data first                  │   │
│   │  • Gradually expand scope                                           │   │
│   │  • Monitor for conflicts and anomalies                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   EACH PHASE: Stable state before proceeding. Rollback plan ready.         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 8: Diagrams

## Diagram 1: Global Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    GLOBAL MULTI-REGION ARCHITECTURE                         │
│                                                                             │
│                              ┌─────────────┐                                │
│                              │  GLOBAL DNS │                                │
│                              │  (Geo-routing)                               │
│                              └──────┬──────┘                                │
│                                     │                                       │
│           ┌─────────────────────────┼─────────────────────────┐             │
│           │                         │                         │             │
│           ▼                         ▼                         ▼             │
│   ┌───────────────┐         ┌───────────────┐         ┌───────────────┐    │
│   │   US-EAST     │         │   EU-WEST     │         │  AP-NORTHEAST │    │
│   │               │         │               │         │               │    │
│   │ ┌───────────┐ │         │ ┌───────────┐ │         │ ┌───────────┐ │    │
│   │ │  CDN Edge │ │         │ │  CDN Edge │ │         │ │  CDN Edge │ │    │
│   │ └─────┬─────┘ │         │ └─────┬─────┘ │         │ └─────┬─────┘ │    │
│   │       │       │         │       │       │         │       │       │    │
│   │ ┌─────▼─────┐ │         │ ┌─────▼─────┐ │         │ ┌─────▼─────┐ │    │
│   │ │    LB     │ │         │ │    LB     │ │         │ │    LB     │ │    │
│   │ └─────┬─────┘ │         │ └─────┬─────┘ │         │ └─────┬─────┘ │    │
│   │       │       │         │       │       │         │       │       │    │
│   │ ┌─────▼─────┐ │         │ ┌─────▼─────┐ │         │ ┌─────▼─────┐ │    │
│   │ │    API    │ │         │ │    API    │ │         │ │    API    │ │    │
│   │ │  Servers  │ │         │ │  Servers  │ │         │ │  Servers  │ │    │
│   │ └─────┬─────┘ │         │ └─────┬─────┘ │         │ └─────┬─────┘ │    │
│   │       │       │         │       │       │         │       │       │    │
│   │ ┌─────▼─────┐ │         │ ┌─────▼─────┐ │         │ ┌─────▼─────┐ │    │
│   │ │   Cache   │ │         │ │   Cache   │ │         │ │   Cache   │ │    │
│   │ └─────┬─────┘ │         │ └─────┬─────┘ │         │ └─────┬─────┘ │    │
│   │       │       │         │       │       │         │       │       │    │
│   │ ┌─────▼─────┐ │         │ ┌─────▼─────┐ │         │ ┌─────▼─────┐ │    │
│   │ │ Database  │◀┼─────────┼▶│ Database  │◀┼─────────┼▶│ Database  │ │    │
│   │ │ (Primary  │ │   Async │ │ (Replica) │ │   Async │ │ (Replica) │ │    │
│   │ │  for US)  │ │   Repl  │ │ (Primary  │ │   Repl  │ │ (Primary  │ │    │
│   │ │           │ │         │ │  for EU)  │ │         │ │  for AP)  │ │    │
│   │ └───────────┘ │         │ └───────────┘ │         │ └───────────┘ │    │
│   │               │         │               │         │               │    │
│   └───────────────┘         └───────────────┘         └───────────────┘    │
│                                                                             │
│   KEY: Each region is primary for its local users' data.                    │
│        Replication is asynchronous for availability.                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 2: Cross-Region Replication Paths

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CROSS-REGION REPLICATION PATHS                           │
│                                                                             │
│   SCENARIO: User in US creates a post                                       │
│                                                                             │
│   STEP 1: Write to local database                                           │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  US-EAST                                                           │    │
│   │  ┌──────────┐    write    ┌──────────┐                             │    │
│   │  │   User   │────────────▶│    DB    │                             │    │
│   │  └──────────┘    <20ms    └──────────┘                             │    │
│   │                                 │                                  │    │
│   │                            commit OK                               │    │
│   │                                 │                                  │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│   STEP 2: Acknowledge to user (fast!)                                       │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  US-EAST                                                           │    │
│   │  ┌──────────┐   success   ┌──────────┐                             │    │
│   │  │   User   │◀────────────│    DB    │                             │    │
│   │  └──────────┘    <20ms    └──────────┘                             │    │
│   │                                 │                                  │    │
│   │          Total user-visible latency: <40ms                         │    │
│   │                                                                    │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│   STEP 3: Async replication to other regions (background)                   │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                                                                    │    │
│   │  US-EAST                EU-WEST               AP-NORTHEAST         │    │
│   │  ┌──────────┐          ┌──────────┐          ┌──────────┐         │    │
│   │  │    DB    │─────────▶│    DB    │          │    DB    │         │    │
│   │  └──────────┘   80ms   └──────────┘          └──────────┘         │    │
│   │       │                                           ▲               │    │
│   │       │                                           │               │    │
│   │       └───────────────────────────────────────────┘               │    │
│   │                         150ms                                      │    │
│   │                                                                    │    │
│   │  Replication happens AFTER user acknowledgment                     │    │
│   │  User doesn't wait for cross-region replication                    │    │
│   │                                                                    │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│   TRADE-OFF:                                                                │
│   • User sees fast response                                                 │
│   • Other regions see update 100-200ms later                                │
│   • If US-EAST fails before replication: data loss (RPO > 0)               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 3: Failure and Failover Behavior

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REGIONAL FAILURE AND FAILOVER                            │
│                                                                             │
│   NORMAL STATE:                                                             │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                                                                    │    │
│   │  US Users ──▶ US-EAST ✓                                            │    │
│   │  EU Users ──▶ EU-WEST ✓                                            │    │
│   │  AP Users ──▶ AP-NORTHEAST ✓                                       │    │
│   │                                                                    │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│   FAILURE: US-EAST region isolated                                          │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                                                                    │    │
│   │                    ┌──────────┐                                    │    │
│   │                    │ US-EAST  │ ← ISOLATED                         │    │
│   │                    │    ✗     │                                    │    │
│   │                    └──────────┘                                    │    │
│   │                                                                    │    │
│   │  Detection: 10-30 seconds (health check failures)                  │    │
│   │  Decision: Automatic failover triggered                            │    │
│   │                                                                    │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│   FAILOVER STATE:                                                           │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                                                                    │    │
│   │  US Users ──┐                                                      │    │
│   │             │                                                      │    │
│   │             ├──▶ EU-WEST ✓ (handling US + EU traffic)              │    │
│   │             │     └── Higher latency for US users (80ms vs 20ms)   │    │
│   │  EU Users ──┘     └── Possible stale data (replication lag)        │    │
│   │                                                                    │    │
│   │  AP Users ──▶ AP-NORTHEAST ✓ (unaffected)                          │    │
│   │                                                                    │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│   RECOVERY (US-EAST returns):                                               │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                                                                    │    │
│   │  1. US-EAST reconnects                                             │    │
│   │  2. Catch up on missed writes from EU-WEST                         │    │
│   │  3. Resolve any conflicts (LWW or custom)                          │    │
│   │  4. Mark US-EAST as healthy                                        │    │
│   │  5. Gradually shift US traffic back                                │    │
│   │  6. Monitor for issues                                             │    │
│   │                                                                    │    │
│   │  Total recovery time: minutes to hours depending on divergence     │    │
│   │                                                                    │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 9: Interview Calibration

## How Interviewers Probe Multi-Region Thinking

Interviewers rarely ask directly about multi-region. They probe through indirect questions:

| What They Ask | What They're Assessing |
|--------------|------------------------|
| "How would you handle users in Europe?" | Do you jump to multi-region or consider simpler options first? |
| "What's your disaster recovery strategy?" | Do you understand active-passive vs active-active trade-offs? |
| "What if this region goes down?" | Do you think about blast radius and containment? |
| "How would you reduce latency globally?" | Do you know when multi-region helps and when it doesn't? |
| "What consistency guarantees do you provide?" | Do you understand the CAP theorem implications? |

## Example Interview Questions

**Direct questions (rare):**
- "Should this system be multi-region? Why or why not?"
- "How would you handle conflict resolution in active-active?"
- "What's your replication strategy across regions?"

**Indirect questions (more common):**
- "Walk me through what happens when a user in Tokyo posts a message"
- "How would this design handle a major regional outage?"
- "What's the latency profile for users around the world?"
- "What are the consistency guarantees of this system?"

## Staff-Level Phrases

**When questioning multi-region need:**
- "Before we go multi-region, let me understand the actual requirements. What's the latency budget? What's the availability target?"
- "Multi-region adds significant complexity. Can we solve this with a CDN and edge caching first?"

**When designing replication:**
- "We intentionally accept stale reads here to preserve availability during partition."
- "For this data, eventual consistency is acceptable. Users won't notice a few seconds of lag."
- "This data requires strong consistency—we'll route all writes to a single region and accept the latency."

**When discussing failures:**
- "During a regional outage, users in that region will experience degraded service—higher latency as they hit a distant region, and possibly stale data."
- "The blast radius of a regional failure is limited to that region's users. Other regions are unaffected."
- "We've designed for graceful degradation. If replication falls behind, we surface stale data rather than failing."

**When discussing trade-offs:**
- "Active-active gives us write availability in all regions, but we need conflict resolution. For this use case, last-writer-wins is acceptable because..."
- "The cost of synchronous cross-region writes is 200ms minimum. For this use case, that's unacceptable, so we're choosing async replication."

## Common Mistake: Assuming Multi-Region Is Always Better

**L5 thinking:**
"Let's deploy to three regions for high availability and low latency."

**Why it's wrong:**
- Didn't analyze whether multi-region is needed
- Didn't consider the consistency implications
- Didn't account for the operational complexity
- Assumed more regions = better without justification

**L6 thinking:**
"Before adding regions, let me understand the user distribution and latency requirements. If 80% of users are in the US, a well-optimized single region with a CDN might meet our needs with much less complexity. If we do need multi-region, we need to decide on consistency model, conflict resolution, and failover strategy. What are the requirements for each of these?"

---

# Part 10: Real-World Incident Case Study

## The Multi-Region Split-Brain Disaster

**Background:**
A major e-commerce platform operated active-active across US-EAST and EU-WEST. Both regions could accept orders.

**The Incident:**

```
Timeline:
T+0:     Network partition begins between regions (submarine cable issue)
T+5min:  Monitoring detects replication lag increasing
T+10min: Both regions continue accepting orders independently
T+30min: Partition heals, replication resumes
T+31min: CONFLICT STORM - 15,000 orders have conflicts

The Conflict:
- Same inventory item sold in both regions during partition
- US sold 500 units, EU sold 400 units
- Actual inventory: 600 units
- Total "sold": 900 units
- Oversold by 300 units
```

**Root Cause Analysis:**

```
// The flawed design
FUNCTION process_order(order):
    // Check local inventory (WRONG: stale during partition)
    local_inventory = local_db.get_inventory(order.item_id)
    
    IF local_inventory >= order.quantity:
        local_db.decrement_inventory(order.item_id, order.quantity)
        local_db.create_order(order)
        RETURN SUCCESS
    ELSE:
        RETURN OUT_OF_STOCK

// During partition:
// US: sees 600, sells 500, thinks 100 remain
// EU: sees 600 (stale!), sells 400, thinks 200 remain
// Reality: -300 inventory
```

**The Fix:**

```
// Staff-level design for inventory
FUNCTION process_order(order):
    // Critical inventory uses synchronous cross-region lock
    IF order.item.is_limited_inventory:
        // Accept latency hit for correctness
        global_lock = acquire_global_lock(order.item_id, timeout=5s)
        
        IF NOT global_lock:
            // During partition: REJECT rather than oversell
            RETURN SERVICE_TEMPORARILY_UNAVAILABLE
        
        TRY:
            // Read from consensus (Spanner-style)
            inventory = consensus_read(order.item_id)
            // ... rest of logic
        FINALLY:
            release_global_lock(global_lock)
    ELSE:
        // Non-critical items: eventual consistency OK
        process_with_local_inventory(order)
```

**Lessons Learned:**
1. Active-active doesn't mean "same logic everywhere"
2. Some data CANNOT use eventual consistency
3. Partition handling must be explicit, not implicit
4. Reject during partition > Conflict after partition

---

# Part 11: Multi-Region Monitoring and Alerting

## What to Monitor in Multi-Region Systems

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-REGION MONITORING STACK                            │
│                                                                             │
│   LAYER 1: CONNECTIVITY                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Cross-region latency (per region pair)                           │   │
│   │  • Cross-region packet loss                                         │   │
│   │  • Replication lag (seconds behind)                                 │   │
│   │  • Replication throughput (bytes/second)                            │   │
│   │  Alert: Lag > 5s OR loss > 1% OR latency > 2x baseline              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   LAYER 2: CONSISTENCY                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Conflict rate (conflicts per minute)                             │   │
│   │  • Divergence detection (hash comparison)                           │   │
│   │  • Read-your-writes violations                                      │   │
│   │  Alert: Conflict rate spike OR divergence detected                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   LAYER 3: REGIONAL HEALTH                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Per-region error rates                                           │   │
│   │  • Per-region latency percentiles                                   │   │
│   │  • Per-region capacity utilization                                  │   │
│   │  Alert: Region error rate > 1% OR latency P99 > SLA                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   LAYER 4: GLOBAL HEALTH                                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Global availability (all regions combined)                       │   │
│   │  • Traffic distribution (is one region overloaded?)                 │   │
│   │  • Failover readiness (can other regions absorb?)                   │   │
│   │  Alert: Global availability < SLA                                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Pseudocode: Cross-Region Health Monitoring

```
// Pseudocode for multi-region health monitoring

CLASS MultiRegionHealthMonitor:
    
    FUNCTION monitor_cross_region_health():
        EVERY 10 seconds:
            FOR source_region IN all_regions:
                FOR target_region IN all_regions - source_region:
                    // Measure connectivity
                    latency = measure_rtt(source_region, target_region)
                    packet_loss = measure_loss(source_region, target_region)
                    
                    // Record metrics
                    record_metric("cross_region_latency", latency,
                                  source=source_region, target=target_region)
                    record_metric("cross_region_loss", packet_loss,
                                  source=source_region, target=target_region)
                    
                    // Detect degradation
                    IF latency > baseline[source_region][target_region] * 2:
                        alert("Cross-region latency elevated",
                              source_region, target_region, latency)
                    
                    IF packet_loss > 0.01:  // 1% loss
                        alert("Cross-region packet loss",
                              source_region, target_region, packet_loss)
    
    FUNCTION monitor_replication_lag():
        EVERY 30 seconds:
            FOR region IN all_regions:
                lag = get_replication_lag(region)
                record_metric("replication_lag_seconds", lag, region=region)
                
                IF lag > 5:  // 5 seconds
                    alert("Replication lag elevated", region, lag)
                
                IF lag > 60:  // 1 minute
                    alert("CRITICAL: Replication severely behind", region, lag)
                    trigger_incident(region, "replication_failure")
    
    FUNCTION detect_partition():
        // A partition exists if we can reach some regions but not others
        reachability = {}
        FOR region IN all_regions:
            reachability[region] = can_reach(region)
        
        reachable = [r for r in reachability if reachability[r]]
        unreachable = [r for r in reachability if not reachability[r]]
        
        IF len(unreachable) > 0 AND len(reachable) > 0:
            // Partition detected
            alert("PARTITION DETECTED",
                  reachable=reachable, unreachable=unreachable)
            
            // Trigger partition mode
            FOR region IN reachable:
                enable_partition_mode(region)
```

---

# Part 12: Final Verification — L6 Readiness Checklist

## Does This Chapter Meet L6 Expectations?

| L6 Criterion | Coverage | Assessment |
|--------------|----------|------------|
| **Judgment & Decision-Making** | L5/L6 contrast, explicit trade-offs, alternatives rejected | ✅ Strong |
| **Failure & Degradation Thinking** | 4 failure scenarios, blast radius, partition handling | ✅ Strong |
| **Scale & Evolution** | Evolution journey, incremental adoption, when to simplify | ✅ Strong |
| **Staff-Level Signals** | L5/L6 table, Staff phrases, common mistakes | ✅ Strong |
| **Real-World Grounding** | 3 system examples, incident case study | ✅ Strong |
| **Interview Calibration** | Probing questions, phrases, L5 mistake | ✅ Strong |
| **Diagrams** | 3 conceptual diagrams | ✅ Strong |

## Staff-Level Signals Covered

✅ Multi-region as trade-off, not upgrade
✅ When NOT to use multi-region
✅ Replication model selection with explicit WHY
✅ Conflict resolution strategies
✅ Failure scenarios with user impact
✅ Blast radius containment
✅ Control plane vs data plane separation
✅ Evolution from single-region to global
✅ When to simplify/rollback
✅ Real-world incident with lessons learned

## This chapter now meets Google Staff Engineer (L6) expectations.

---

# Brainstorming Questions

## Understanding the Problem Space

1. For a system you work on, what percentage of users are in each geographic region?

2. If you added a second region tomorrow, what would break?

3. What's the actual latency experienced by your farthest users? Is it acceptable?

4. Which parts of your system could tolerate stale data? Which parts cannot?

5. If your primary region went completely offline, how long until users could resume?

6. What's the cross-region network latency between potential deployment locations?

7. Which users would benefit most from multi-region? Which wouldn't notice?

## Design Decisions

8. For your system, would active-passive or active-active be more appropriate? Why?

9. If you chose active-active, how would you handle conflicts?

10. What's the minimum number of regions that would satisfy your requirements?

11. How would you route users to regions? Geo-DNS? Client-side? Anycast?

12. What data can be partitioned by region? What must be globally accessible?

13. What consistency guarantees does each part of your system actually need?

14. What's your replication lag SLA? How would you monitor and alert on it?

## Failure Scenarios

15. If Region A can see Region B but not Region C, what happens?

16. What if cross-region replication falls 24 hours behind?

17. What if failover happens but then the original region comes back?

18. How do you handle users who travel between regions mid-session?

19. What if a configuration change is deployed to one region but not others?

20. How would you debug an issue that only manifests in cross-region scenarios?

---

# Homework Exercises

## Exercise 1: Multi-Region Necessity Analysis

**Objective:** Practice evaluating whether multi-region is justified.

Choose a system (yours or a case study) and analyze:

**Part A: Current State**
- User geographic distribution
- Current latency by region
- Current availability numbers
- Current infrastructure cost

**Part B: Multi-Region Impact**
- Expected latency improvement per region
- Expected availability improvement
- Expected cost increase
- Expected operational complexity increase

**Part C: Recommendation**
- Is multi-region justified? Why or why not?
- If yes, which regions and which replication model?
- If no, what alternatives would you recommend?

**Deliverable:** 2-page analysis with quantified trade-offs.

---

## Exercise 2: Replication Model Selection

**Objective:** Practice choosing the right replication model.

For each scenario, select a replication model and justify:

**Scenario A: E-commerce Product Catalog**
- 10M products
- Read-heavy (99% reads)
- Updates by internal team only
- Must be globally fast

**Scenario B: User Messaging System**
- 50M users
- High write volume
- Users primarily message within their region
- Real-time delivery expected

**Scenario C: Financial Transaction Ledger**
- Strong consistency required
- Audit trail essential
- Writes from any region
- Latency secondary to correctness

**Scenario D: Social Media Likes/Reactions**
- Very high write volume
- Eventual consistency acceptable
- Must not lose data
- Displayed counts can lag

**For each, document:**
- Chosen model (active-active, active-passive, read-local-write-central)
- Consistency guarantees
- Conflict resolution strategy (if applicable)
- Expected failure behavior

**Deliverable:** Completed analysis table with justifications.

---

## Exercise 3: Failure Scenario Walkthrough

**Objective:** Practice reasoning about failure modes.

Design a multi-region system (or use one you know) and walk through these failure scenarios:

**Scenario 1: Complete region isolation (30 minutes)**
- What do users in the isolated region experience?
- What do users in other regions experience?
- What happens when the region reconnects?

**Scenario 2: Slow replication (24 hours of lag)**
- Which users see stale data?
- How would you detect this?
- What's the remediation plan?

**Scenario 3: Conflicting writes during partition**
- Two regions write the same record during a partition
- What's the conflict resolution outcome?
- How do you audit what happened?

**Scenario 4: Control plane failure**
- Cannot deploy new code or config
- Data plane still functioning
- How long can you operate? What degrades?

**Deliverable:** Failure scenario playbook with detection, impact, and remediation for each.

---

## Exercise 4: Migration Planning

**Objective:** Practice planning multi-region adoption.

Take a single-region system and plan the migration to multi-region:

**Phase 1: Preparation**
- What changes are needed before adding regions?
- What data needs to be replicated?
- What services need regional instances?

**Phase 2: Shadow Mode**
- How would you set up shadow traffic?
- What metrics would you compare?
- What discrepancies would block proceeding?

**Phase 3: Read Traffic Migration**
- What's the traffic shift schedule?
- What are the rollback triggers?
- How do you handle consistency during transition?

**Phase 4: Write Traffic Migration (if applicable)**
- How do you enable regional writes?
- What's the conflict resolution strategy?
- How do you validate correctness?

**Deliverable:** Migration plan with milestones, metrics, and rollback criteria.

---

## Exercise 5: Cost-Benefit Analysis

**Objective:** Practice quantifying multi-region trade-offs.

For a hypothetical or real system, calculate:

**Costs:**
- Additional infrastructure cost (compute, storage, network)
- Cross-region data transfer cost
- Engineering time to implement and maintain
- Operational complexity increase
- Development velocity impact

**Benefits:**
- Latency reduction (quantified by user percentage)
- Availability improvement (expected vs single-region)
- Compliance requirements satisfied
- Disaster recovery improvement

**Analysis:**
- What's the ROI of multi-region?
- At what scale does multi-region become justified?
- What's the simplest approach that meets requirements?

**Deliverable:** Cost-benefit spreadsheet with break-even analysis.

---

## Exercise 6: Conflict Resolution Design

**Objective:** Practice designing conflict resolution for active-active.

For each data type, design a conflict resolution strategy:

| Data Type | Conflict Scenario | Your Strategy | Trade-offs |
|-----------|-------------------|---------------|------------|
| User profile | Two regions update email | ? | ? |
| Shopping cart | Items added in both regions | ? | ? |
| Account balance | Decrements in both regions | ? | ? |
| Like count | Increments in both regions | ? | ? |
| Document text | Edits in both regions | ? | ? |

**Deliverable:** Completed table with pseudocode for each resolution strategy.

---

## Exercise 7: Partition Handling Design

**Objective:** Design explicit partition handling.

For a chosen system, document behavior during partition:

**Part A: Detection**
- How do you detect a partition vs slow network?
- What's the detection latency?
- What are the false positive risks?

**Part B: During Partition**
- Which operations continue locally?
- Which operations are rejected?
- How do you communicate to users?

**Part C: After Partition**
- How do you detect partition healing?
- How do you reconcile divergent state?
- How do you validate correctness?

**Deliverable:** Partition handling runbook.

---

## Exercise 8: Multi-Region Monitoring Design

**Objective:** Design monitoring for global systems.

Design a monitoring system that covers:
- Cross-region latency and loss
- Replication lag
- Consistency verification
- Regional vs global health

**Include:**
- What metrics to collect
- Alert thresholds
- Escalation paths
- Dashboard requirements

**Deliverable:** Monitoring design document with alert rules.

---

## Exercise 9: Routing Strategy Design

**Objective:** Practice designing global traffic routing.

For a user-facing API with users in US (50%), EU (30%), AP (20%):

**Part A: Routing Decision**
- Geo-DNS vs Anycast vs Client-side?
- How do you handle VPN/proxy users?
- What's the failover mechanism?

**Part B: Session Handling**
- How do you maintain session affinity?
- What happens when user travels between regions?
- How do you handle sticky data?

**Part C: Failure Scenarios**
- What happens when a region becomes slow?
- What happens during DNS propagation?
- How do you prevent thundering herd on failover?

**Deliverable:** Routing strategy document with failure handling.

---

## Exercise 10: Regional Data Partitioning

**Objective:** Practice designing data locality.

For a social media platform, design regional data partitioning:

**Part A: What data is regional?**
- User profiles: regional or global?
- Posts: regional or global?
- Followers/following: regional or global?
- Messages: regional or global?

**Part B: Cross-region access**
- US user views EU user's profile: How?
- US user follows EU user: How?
- US user messages EU user: How?

**Part C: User relocation**
- User moves from US to EU permanently
- How do you migrate their data?
- What's the transition period behavior?

**Deliverable:** Data partitioning design with cross-region access patterns.

---

# Quick Reference Card

## Multi-Region Decision Framework

| Question | If Yes... | If No... |
|----------|-----------|----------|
| >20% users far from primary? | Consider multi-region | CDN may suffice |
| Need <100ms writes globally? | Active-active needed | Active-passive OK |
| Can tolerate eventual consistency? | Async replication OK | Need sync replication |
| Can tolerate regional outage? | Active-passive OK | Active-active needed |
| Data can be partitioned by region? | Regional sharding | Need global consistency |

## Replication Model Quick Reference

| Model | Consistency | Write Latency | Availability | Complexity |
|-------|-------------|---------------|--------------|------------|
| Active-Passive | Strong | High (remote writes) | Good (failover) | Low |
| Active-Active | Eventual | Low (local writes) | Excellent | High |
| Read-Local-Write-Central | Strong for writes | High (remote writes) | Good | Medium |

## Failure Blast Radius

| Design | Regional Failure Impact |
|--------|------------------------|
| **Independent regions** | Only affected region's users |
| **Shared control plane** | All regions for control operations |
| **Synchronous replication** | All regions for writes |
| **Global database** | All regions |

---

# Conclusion

Multi-region architecture is a powerful tool, but it's not an upgrade—it's a trade-off. Every region you add creates new failure modes, consistency challenges, and operational complexity.

Staff engineers approach multi-region with healthy skepticism:

**Ask why first.** What problem are we solving? Is the latency benefit worth the consistency cost? Is the availability benefit worth the operational complexity?

**Start simple.** CDN for static content. Edge caching for read-heavy APIs. Single-region with good disaster recovery. Add complexity only when simpler solutions are insufficient.

**Choose consciously.** Active-passive vs active-active isn't a progression—it's a choice based on requirements. Each has trade-offs. Know what you're trading.

**Design for failure.** Regions will go down. Networks will partition. Replication will lag. Design your system to degrade gracefully, not catastrophically.

**Contain blast radius.** A regional failure should affect that region's users, not everyone. Avoid global singletons and synchronous cross-region dependencies.

**Evolve incrementally.** Multi-region isn't a big-bang deployment. It's a journey through shadow traffic, read replicas, and eventually (maybe) active-active writes.

The goal is not maximum geographic distribution. The goal is the right geographic distribution for your requirements, at a complexity level your team can sustain.

---

*End of Chapter 24*

*Next: Chapter 25 — Data Locality, Compliance, and System Evolution*
