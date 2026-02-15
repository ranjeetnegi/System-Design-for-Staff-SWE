# Chapter 47: Global Rate Limiter

---

# Introduction

Rate limiting is one of the most deceptively simple systems in distributed computing. The concept is trivial: count requests and reject those that exceed a threshold. The implementation at global scale is anything but trivial. I've built and operated rate limiters at Google scale, and I've debugged incidents where poorly designed rate limiters either failed to protect systems (allowing cascading failures) or became the bottleneck themselves (ironically causing the outages they were meant to prevent).

This chapter covers rate limiting as Staff Engineers practice it: with deep understanding of the trade-offs between accuracy and performance, awareness of the failure modes, and judgment about when approximate is better than precise.

**The Staff Engineer's First Law of Rate Limiting**: A rate limiter that is perfectly accurate but adds 50ms of latency to every request has failed its mission. The goal is protection, not precision.

---

## Quick Visual: Rate Limiting at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RATE LIMITING: THE STAFF ENGINEER VIEW                   │
│                                                                             │
│   WRONG Framing: "Count requests precisely, reject excess"                  │
│   RIGHT Framing: "Protect the system with acceptable accuracy,              │
│                   minimal latency, and graceful degradation"                │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Before designing, understand:                                      │   │
│   │                                                                     │   │
│   │  1. What are we protecting? (API servers, databases, users)         │   │
│   │  2. What accuracy is acceptable? (Exact? Within 10%? 50%?)          │   │
│   │  3. What latency is acceptable? (Sub-ms? 5ms? 50ms?)                │   │
│   │  4. What happens during rate limiter failure? (Open? Closed?)       │   │
│   │  5. Global consistency or regional approximation?                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   THE UNCOMFORTABLE TRUTH:                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Globally consistent rate limiting is expensive and slow.           │   │
│   │  Most systems should use approximate counting with regional         │   │
│   │  coordination—slightly over-counting is acceptable.                 │   │
│   │  Under-counting (allowing abuse) is the real failure.               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Rate Limiter Decisions

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Global limit enforcement** | "Use Redis with atomic counters, strong consistency" | "What's the cross-region latency? 200ms for consensus is unacceptable. Use local counters with async sync, accept 5-10% over-counting." |
| **Rate limit accuracy** | "We need exact enforcement of 100 req/sec" | "Is 105 req/sec catastrophic? If not, approximate counting saves 10x infrastructure cost and adds 0ms latency." |
| **Rate limiter failure** | "If rate limiter is down, reject all requests" | "Fail open with degraded limits from cache. Better to allow 2x traffic than 0x traffic." |
| **Distributed counting** | "Synchronize counters across all nodes" | "Partition by customer. Each node handles a subset. No synchronization needed for most cases." |
| **Time windows** | "Fixed 1-second windows for precision" | "Sliding windows are more fair but more expensive. Token bucket gives smooth rate. Choose based on use case." |

**Key Difference**: L6 engineers recognize that rate limiting is about protection, not precision. They design for the failure modes and accept approximations that reduce complexity.

---

# Part 1: Foundations — What Rate Limiting Is and Why It Exists

## What Is Rate Limiting?

Rate limiting is the practice of controlling the rate at which requests are processed or resources are consumed. It sets an upper bound on how many operations can occur within a time window.

### The Simplest Mental Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RATE LIMITING: THE BOUNCER ANALOGY                       │
│                                                                             │
│   Imagine a nightclub with a capacity of 100 people.                        │
│                                                                             │
│   The bouncer (rate limiter) at the door:                                   │
│   • Counts people entering                                                  │
│   • Allows entry if under capacity                                          │
│   • Turns away people when at capacity                                      │
│   • Tracks when people leave (time window resets)                           │
│                                                                             │
│   COMPLICATIONS AT SCALE:                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  What if there are 10 doors (distributed system)?                   │   │
│   │  → Each door needs to know total count                              │   │
│   │                                                                     │   │
│   │  What if the bouncer is sick (rate limiter failure)?                │   │
│   │  → Do we close the club (reject all) or let everyone in (no limit)? │   │
│   │                                                                     │   │
│   │  What if counting takes 1 minute (high latency)?                    │   │
│   │  → Line backs up, everyone is delayed                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Why Rate Limiting Exists

Rate limiting serves multiple critical purposes:

### 1. Protection Against Overload

Without rate limiting, a sudden spike in traffic can overwhelm backend systems:

```
// Pseudocode: What happens without rate limiting

SCENARIO: Popular tweet goes viral, links to your API

T+0min:   Normal traffic: 1,000 req/sec
T+1min:   Viral spike: 50,000 req/sec
T+2min:   Database connections exhausted
T+3min:   API servers OOM, crash
T+4min:   Cascading failure, entire system down
T+5min:   Recovery takes hours, data integrity issues

WITH RATE LIMITING:
T+0min:   Normal traffic: 1,000 req/sec
T+1min:   Spike detected: 50,000 req/sec attempted
          Rate limiter: 10,000 req/sec allowed, 40,000 rejected with 429
T+2min:   System healthy, serving at capacity
          Rejected users retry, eventually served
T+5min:   Spike subsides, normal operation
```

### 2. Fair Resource Allocation

Without rate limiting, one customer can monopolize shared resources:

```
Customer A: 10,000 req/sec (legitimate high-volume user)
Customer B: 100 req/sec (small business)
Customer C: 100 req/sec (small business)

Without limits:
→ Customer A consumes 99% of capacity
→ Customers B and C experience timeouts

With per-customer limits (1,000 req/sec each):
→ Customer A gets 1,000 req/sec (limited)
→ Customers B and C get their full 100 req/sec
→ Fair allocation of shared resources
```

### 3. Cost Control

API calls cost money—compute, storage, third-party services. Rate limiting prevents runaway costs:

```
Scenario: Customer's misconfigured script
Without limits: 1M requests in 1 hour = $10,000 bill
With limits: 10,000 requests allowed, script fails fast, $100 bill
```

### 4. Security and Abuse Prevention

Rate limiting is a first line of defense against various attacks:

```
Attack Type               Rate Limiting Defense
─────────────────────────────────────────────────────
Brute force login         5 attempts per account per minute
API scraping              100 requests per IP per minute
DDoS amplification        1,000 requests per source per second
Spam/bot activity         10 actions per user per minute
Resource exhaustion       N requests per customer per hour
```

## What Happens If Rate Limiting Does NOT Exist

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SYSTEMS WITHOUT RATE LIMITING                            │
│                                                                             │
│   FAILURE MODE 1: CASCADING OVERLOAD                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Traffic spike → Backend overload → Timeouts → Retries →            │   │
│   │  More load → Complete failure                                       │   │
│   │                                                                     │   │
│   │  Real example: A single viral post caused 48-hour outage            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 2: NOISY NEIGHBOR                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  One customer's load → Degrades service for all customers           │   │
│   │                                                                     │   │
│   │  Real example: Runaway batch job from one customer caused           │   │
│   │  latency spikes for all other customers                             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 3: COST EXPLOSION                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Misconfigured client → Infinite loop → Millions of requests        │   │
│   │  → Massive infrastructure bill                                      │   │
│   │                                                                     │   │
│   │  Real example: $50,000 bill from 72-hour polling loop bug           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 4: SECURITY BREACH                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  No login limits → Brute force succeeds → Account compromise        │   │
│   │                                                                     │   │
│   │  Real example: 100,000 accounts compromised via credential stuffing │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 2: Functional Requirements

## Core Use Cases

### 1. Per-Customer API Rate Limiting

The most common use case: limit API calls per customer/API key.

```
Use Case: Customer A is allowed 1,000 requests per minute

Input: Request with API key "customer_a_key"
Process: Check count for this key in current time window
Output: 
  - If count < 1000: Allow request, increment count
  - If count >= 1000: Reject with 429 Too Many Requests
```

### 2. Per-Endpoint Rate Limiting

Different endpoints have different costs; limit accordingly.

```
Use Case: Expensive search endpoint limited to 10 req/sec

Endpoint limits:
  /api/v1/users (cheap):     1000 req/sec
  /api/v1/search (expensive): 10 req/sec
  /api/v1/export (very expensive): 1 req/min
```

### 3. Per-User Rate Limiting

Limit actions per authenticated user, regardless of IP or API key.

```
Use Case: User can post 10 messages per minute

Input: POST /messages with user_id="user123"
Process: Check user123's message count in last minute
Output: Allow or reject based on count
```

### 4. Per-IP Rate Limiting

Limit anonymous or unauthenticated traffic by IP address.

```
Use Case: Anonymous access limited to 60 req/min per IP

Input: Request from IP 1.2.3.4
Process: Check request count for this IP
Output: Allow or reject

Complication: NAT, proxies, shared IPs
→ One corporate IP might represent 1000 users
→ Need fallback to other identifiers
```

### 5. Global Rate Limiting

Protect a shared resource with a global limit across all customers.

```
Use Case: Database can handle 100,000 writes/sec total

All customers combined cannot exceed 100,000 writes/sec
Individual customer limits must sum to less than global limit
Or: Best-effort fair sharing when approaching global limit
```

## Read Paths

```
// Pseudocode: Rate limit check (hot path)

FUNCTION check_rate_limit(key, limit, window):
    current_count = get_count(key, window)
    
    IF current_count < limit:
        increment_count(key, window)
        RETURN {
            allowed: TRUE,
            remaining: limit - current_count - 1,
            reset_at: get_window_reset_time(window)
        }
    ELSE:
        RETURN {
            allowed: FALSE,
            remaining: 0,
            reset_at: get_window_reset_time(window),
            retry_after: get_window_reset_time(window) - now()
        }
```

## Write Paths

```
// Pseudocode: Rate limit configuration update

FUNCTION update_rate_limit(key, new_limit, window):
    // Validate new limit
    IF new_limit < 0 OR new_limit > MAX_ALLOWED_LIMIT:
        RETURN ERROR("Invalid limit")
    
    // Update configuration
    store_limit_config(key, {
        limit: new_limit,
        window: window,
        updated_at: now(),
        updated_by: current_user()
    })
    
    // Propagate to rate limiter nodes
    broadcast_config_update(key)
    
    RETURN SUCCESS
```

## Control / Admin Paths

```
// Administrative operations

FUNCTION get_rate_limit_status(key):
    RETURN {
        current_count: get_count(key, current_window),
        limit: get_limit(key),
        window: get_window(key),
        utilization: current_count / limit,
        history: get_count_history(key, last_24_hours)
    }

FUNCTION reset_rate_limit(key):
    // Emergency override to reset a customer's counter
    clear_count(key, current_window)
    log_audit("Rate limit reset", key, current_user())
    RETURN SUCCESS

FUNCTION set_rate_limit_override(key, temporary_limit, duration):
    // Temporary limit increase for special events
    store_override(key, temporary_limit, now() + duration)
    RETURN SUCCESS
```

## Edge Cases

### Edge Case 1: Limit Exactly Met

```
Customer at exactly 1000/1000 requests
Next request arrives at T+0.001 before window reset

Decision: Reject (standard) or Allow (lenient)?
Staff approach: Reject. Limits are limits.
But: Include Retry-After header with precise reset time.
```

### Edge Case 2: Clock Skew Between Nodes

```
Node A: Clock says 12:00:01, starts new window
Node B: Clock says 11:59:59, still in old window

Customer request routed to Node A: Count = 1
Same customer routed to Node B: Count = 999 (old window)

Result: Customer gets 1000 + some extra requests
Staff approach: Accept this inaccuracy. Use NTP. Monitor skew.
```

### Edge Case 3: Rate Limiter Failure

```
Rate limiter database unreachable

Options:
A) Fail closed: Reject all requests (safe but causes outage)
B) Fail open: Allow all requests (risky but maintains service)
C) Fail degraded: Use cached limits, allow 2x normal rate

Staff approach: C. Use stale data from cache.
Log aggressively. Alert on failure. Fix quickly.
```

### Edge Case 4: Burst at Window Boundary

```
Window: 1 minute, Limit: 100 requests

Customer sends 100 requests at 12:00:59
Customer sends 100 requests at 12:01:01

Result: 200 requests in 2 seconds, all allowed

Staff approach: This is correct behavior for fixed windows.
If problematic: Use sliding window or token bucket.
```

## What Is Intentionally OUT of Scope

| Excluded | Why |
|----------|-----|
| Request content inspection | That's a WAF, not a rate limiter |
| User authentication | Rate limiter receives already-authenticated requests |
| Request routing | Rate limiter advises; router decides |
| Billing/metering | Different accuracy requirements, different system |
| Detailed analytics | Rate limiter is hot path; analytics is cold path |

---

# Part 3: Non-Functional Requirements

## Latency Expectations

Rate limiting is in the critical path of every request. Latency requirements are strict.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LATENCY REQUIREMENTS                                     │
│                                                                             │
│   ACCEPTABLE:                                                               │
│   • P50: < 1ms (rate limit check should be negligible)                      │
│   • P99: < 5ms (even worst case shouldn't be noticeable)                    │
│   • P99.9: < 10ms (tail latency matters at scale)                           │
│                                                                             │
│   UNACCEPTABLE:                                                             │
│   • Any synchronous cross-region call (adds 50-200ms)                       │
│   • Database query per request (adds 5-20ms)                                │
│   • Distributed consensus per request (adds 10-100ms)                       │
│                                                                             │
│   STAFF INSIGHT:                                                            │
│   Rate limit check must be faster than the actual request processing.       │
│   If rate limiting adds 50ms and requests take 100ms, you've added 50%      │
│   latency to your entire system. Unacceptable.                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Availability Expectations

Rate limiter must be more available than the systems it protects.

```
If protected service has 99.9% availability target:
Rate limiter needs 99.99%+ availability

Why: Rate limiter failure = all requests fail OR all requests allowed
Both are worse than the protected service being down

Staff approach:
• Rate limiter must be simpler than protected service
• Multiple layers of fallback
• Fail-open with degradation, not fail-closed
```

## Consistency Needs

This is where Staff judgment matters most.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONSISTENCY TRADE-OFFS                                   │
│                                                                             │
│   STRONG CONSISTENCY (Reject 1001st request ALWAYS):                        │
│   • Requires distributed coordination                                       │
│   • Adds 10-100ms latency per request                                       │
│   • Complex failure modes                                                   │
│   • Very expensive at scale                                                 │
│                                                                             │
│   EVENTUAL CONSISTENCY (Might allow 1050 requests before catching up):      │
│   • Local counters with async sync                                          │
│   • Sub-millisecond latency                                                 │
│   • Simple failure modes                                                    │
│   • Much cheaper                                                            │
│                                                                             │
│   STAFF DECISION:                                                           │
│   For most rate limiting: eventual consistency is correct.                  │
│   • 5% over-counting is acceptable                                          │
│   • 5% under-counting is dangerous (allowing abuse)                         │
│   • Design to over-count when uncertain                                     │
│                                                                             │
│   Exception: Financial limits (money movement) may need strong consistency  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Durability

Counter state durability is surprisingly unimportant:

```
Scenario: Rate limiter restarts, counters reset to zero

Impact:
• Customers get their full limit again immediately
• In a 1-minute window, this means at most 2x limit
• For most systems, this is acceptable

Staff approach:
• Don't over-engineer durability for counters
• Persist configuration (limits, keys), not counts
• Counts can be reconstructed from recent requests if needed
```

## Correctness vs User Experience Trade-offs

```
STRICT CORRECTNESS:
• Customer at limit gets 429 error
• Good for protection
• Bad for user experience during legitimate spikes

LENIENT APPROACH:
• Warn at 80% of limit (header: X-RateLimit-Remaining)
• Soft limit at 100% (log but allow, for grace period)
• Hard limit at 120% (reject)

Staff approach: Implement warning and grace period
• Customers can react before hitting hard limit
• Reduces support tickets
• Still provides protection
```

## Security Implications

```
Rate limiter sees:
• All API keys
• All IP addresses
• All user identifiers
• Request patterns for all customers

Security requirements:
• Rate limiter must not log full API keys
• Access to rate limiter config requires elevated privilege
• Rate limiter failure should not expose customer data
• Audit trail for limit changes
```

## How Requirements Conflict

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REQUIREMENT CONFLICTS                                    │
│                                                                             │
│   LATENCY vs ACCURACY:                                                      │
│   • Accurate global counting requires coordination = high latency           │
│   • Low latency requires local counting = approximate accuracy              │
│   Resolution: Accept approximation for latency                              │
│                                                                             │
│   AVAILABILITY vs CONSISTENCY:                                              │
│   • Strong consistency requires quorum = lower availability                 │
│   • High availability requires eventual consistency = lower accuracy        │
│   Resolution: Prioritize availability, accept eventual consistency          │
│                                                                             │
│   SIMPLICITY vs FEATURES:                                                   │
│   • Multiple limit types (per-user, per-IP, per-endpoint) = complexity      │
│   • Simpler system = fewer failure modes                                    │
│   Resolution: Start simple, add features only when needed                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 4: Scale & Load Modeling

## Concrete Numbers

Let's design for a realistic large-scale API:

```
SCALE ASSUMPTIONS:
• 100,000 customers (API keys)
• 10 million requests per second (peak)
• 3 million requests per second (average)
• 100 rate limit checks per second per customer (average)
• 3 regions (US, EU, Asia)

DERIVED NUMBERS:
• Rate limit checks: 10M/sec = 600M/minute = 36B/hour
• Unique keys active per minute: ~500,000
• Counter updates: 10M/sec writes
• Configuration reads: 10M/sec (cached)
• Configuration updates: ~100/hour (rare)
```

## QPS Analysis

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    QPS BREAKDOWN                                            │
│                                                                             │
│   AVERAGE LOAD:                                                             │
│   • Rate limit checks: 3M/sec                                               │
│   • Counter increments: 3M/sec                                              │
│   • Config lookups: 3M/sec (from cache, not storage)                        │
│                                                                             │
│   PEAK LOAD (flash sale, viral event):                                      │
│   • Rate limit checks: 10M/sec (3.3x average)                               │
│   • Counter increments: 10M/sec                                             │
│   • More rejections (customers hitting limits)                              │
│                                                                             │
│   BURST BEHAVIOR:                                                           │
│   • Start of minute: Spike as windows reset                                 │
│   • Can be 2-3x average for a few seconds                                   │
│   • Must handle 30M/sec for short bursts                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Storage Requirements

```
PER-KEY STORAGE:
• Key identifier: 64 bytes
• Current count: 8 bytes
• Window timestamp: 8 bytes
• Limit config: 32 bytes
• Total per key: ~120 bytes

TOTAL STORAGE:
• 500,000 active keys × 120 bytes = 60 MB active set
• With history (24 windows): 1.4 GB
• Fits easily in memory

STORAGE DECISION: In-memory with optional persistence
• Redis: Good fit, handles 100K+ ops/sec per node
• Custom: Can achieve 1M+ ops/sec with careful design
```

## What Breaks First at Scale

```
SCALING BOTTLENECKS (in order of failure):

1. NETWORK (first to fail)
   • 10M req/sec × 1KB = 10 GB/sec of traffic
   • Single network link saturates
   • Solution: Multiple nodes, sharding

2. SINGLE COUNTER (second to fail)
   • Hot keys (popular customers) cause contention
   • Single Redis key can't handle 100K increments/sec
   • Solution: Counter sharding, approximate counting

3. CROSS-REGION LATENCY (architectural limit)
   • Synchronous global coordination adds 50-200ms
   • At 10M req/sec, this is unacceptable
   • Solution: Regional independence with async sync

4. MEMORY (rarely the limit)
   • 60MB active set is tiny
   • Even 100x growth (6GB) fits on single node
   • Not a practical concern
```

## Dangerous Assumptions

```
ASSUMPTION: "All customers have similar request rates"
REALITY: Power law distribution
• 1% of customers = 50% of requests
• Top customer might be 1000x average
• Hot keys require special handling

ASSUMPTION: "Requests are evenly distributed over time"
REALITY: Bursty traffic
• Start of minute: Window resets cause spikes
• Marketing events: Sudden 10x traffic
• Client retries: Rejection causes more load

ASSUMPTION: "Clock skew is negligible"
REALITY: Clocks drift
• NTP accuracy: ~10ms typical, ~100ms worst case
• Window boundaries are fuzzy
• Accept some inaccuracy at boundaries
```

---

# Part 5: High-Level Architecture

## Core Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RATE LIMITER ARCHITECTURE                                │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         CLIENTS                                     │   │
│   │   (API servers, gateways, applications)                             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    RATE LIMITER CLUSTER                             │   │
│   │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │   │
│   │   │   Node 1    │  │   Node 2    │  │   Node 3    │   ...           │   │
│   │   │  (shard A)  │  │  (shard B)  │  │  (shard C)  │                 │   │
│   │   │             │  │             │  │             │                 │   │
│   │   │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │                 │   │
│   │   │ │ Counter │ │  │ │ Counter │ │  │ │ Counter │ │                 │   │
│   │   │ │  Store  │ │  │ │  Store  │ │  │ │  Store  │ │                 │   │
│   │   │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │                 │   │
│   │   │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │                 │   │
│   │   │ │ Config  │ │  │ │ Config  │ │  │ │ Config  │ │                 │   │
│   │   │ │  Cache  │ │  │ │  Cache  │ │  │ │  Cache  │ │                 │   │
│   │   │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │                 │   │
│   │   └─────────────┘  └─────────────┘  └─────────────┘                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    CONFIGURATION STORE                              │   │
│   │   (Persistent storage for limits, rules, overrides)                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

### Rate Limiter Node

```
Responsibilities:
• Receive rate limit check requests
• Determine which shard owns the key
• Check current count against limit
• Increment counter if allowed
• Return allow/reject decision

Stateless?: Mostly. Holds ephemeral counters.
Why: Counters can be lost on restart. Acceptable.

State held:
• Active counters for assigned shards
• Cached configuration
• Local metrics
```

### Counter Store (per node)

```
Responsibilities:
• Store current counts per key per window
• Support atomic increment
• Support atomic check-and-increment
• Expire old windows automatically

Implementation options:
• In-memory hash map with TTL (simplest)
• Redis (if shared state needed)
• Custom lock-free data structure (highest performance)
```

### Configuration Store

```
Responsibilities:
• Persist rate limit configurations
• Serve config to rate limiter nodes
• Support config updates
• Maintain audit trail

Implementation:
• Database (PostgreSQL, MySQL)
• Key-value store (etcd, Consul)
• Config pushed to nodes, not pulled per-request
```

## Data Flow: Rate Limit Check

```
// Pseudocode: Request flow

FUNCTION handle_request(request):
    // Step 1: Extract rate limit key
    key = extract_key(request)  // e.g., API key, user ID, IP
    
    // Step 2: Route to correct shard
    shard = hash(key) % num_shards
    node = get_node_for_shard(shard)
    
    // Step 3: Check rate limit
    result = node.check_rate_limit(key)
    
    // Step 4: Return decision
    IF result.allowed:
        // Add rate limit headers
        response.headers["X-RateLimit-Limit"] = result.limit
        response.headers["X-RateLimit-Remaining"] = result.remaining
        response.headers["X-RateLimit-Reset"] = result.reset_at
        RETURN ALLOW
    ELSE:
        response.status = 429
        response.headers["Retry-After"] = result.retry_after
        RETURN REJECT
```

## Stateless vs Stateful Decisions

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STATE DECISIONS                                          │
│                                                                             │
│   STATELESS (Configuration):                                                │
│   • Rate limit rules                                                        │
│   • Customer tiers                                                          │
│   • Endpoint limits                                                         │
│   Reason: Changes infrequently, can be cached/replicated                    │
│                                                                             │
│   EPHEMERAL STATE (Counters):                                               │
│   • Current request counts                                                  │
│   • Window timestamps                                                       │
│   Reason: Changes constantly, but loss is acceptable                        │
│                                                                             │
│   PERSISTENT STATE (Audit):                                                 │
│   • Rate limit violations (for analytics)                                   │
│   • Configuration change history                                            │
│   Reason: Needed for debugging and compliance                               │
│                                                                             │
│   STAFF INSIGHT:                                                            │
│   Counters don't need durability. If rate limiter restarts and counters     │
│   reset, customers get an extra window of requests. This is acceptable.     │
│   Over-engineering durability for counters adds complexity without benefit. │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 6: Deep Component Design

## Rate Limiting Algorithms

### Algorithm 1: Fixed Window Counter

The simplest algorithm. Divide time into fixed windows, count requests in each.

```
// Pseudocode: Fixed window counter

CLASS FixedWindowCounter:
    counters = {}  // key -> (count, window_start)
    
    FUNCTION check_and_increment(key, limit, window_size):
        current_window = floor(now() / window_size) * window_size
        
        IF key NOT IN counters OR counters[key].window_start != current_window:
            // New window, reset counter
            counters[key] = (0, current_window)
        
        IF counters[key].count < limit:
            counters[key].count += 1
            RETURN ALLOWED
        ELSE:
            RETURN REJECTED

PROS:
• Very simple
• Memory efficient (one counter per key)
• Fast (O(1) operations)

CONS:
• Burst at window boundaries allowed
• Customer can use 2x limit in 2 seconds spanning two windows
```

### Algorithm 2: Sliding Window Log

Track timestamps of all requests, count those within window.

```
// Pseudocode: Sliding window log

CLASS SlidingWindowLog:
    request_logs = {}  // key -> list of timestamps
    
    FUNCTION check_and_increment(key, limit, window_size):
        window_start = now() - window_size
        
        // Remove old entries
        IF key IN request_logs:
            request_logs[key] = filter(t -> t > window_start, request_logs[key])
        ELSE:
            request_logs[key] = []
        
        IF len(request_logs[key]) < limit:
            request_logs[key].append(now())
            RETURN ALLOWED
        ELSE:
            RETURN REJECTED

PROS:
• Accurate sliding window
• No boundary burst problem

CONS:
• Memory: O(limit) per key (stores all timestamps)
• Slow: O(limit) to clean up old entries
• Not practical for high limits
```

### Algorithm 3: Sliding Window Counter (Hybrid)

Approximate sliding window using two fixed windows.

```
// Pseudocode: Sliding window counter

CLASS SlidingWindowCounter:
    counters = {}  // key -> (current_count, previous_count, window_start)
    
    FUNCTION check_and_increment(key, limit, window_size):
        current_window = floor(now() / window_size) * window_size
        previous_window = current_window - window_size
        time_in_current = now() - current_window
        weight = 1 - (time_in_current / window_size)  // 0 to 1
        
        // Get or initialize counters
        entry = counters.get(key, (0, 0, current_window))
        
        // Rotate windows if needed
        IF entry.window_start < current_window:
            entry = (0, entry.current_count, current_window)
        
        // Calculate weighted count
        weighted_count = entry.current_count + (entry.previous_count * weight)
        
        IF weighted_count < limit:
            entry.current_count += 1
            counters[key] = entry
            RETURN ALLOWED
        ELSE:
            RETURN REJECTED

PROS:
• Approximate sliding window behavior
• Memory efficient: O(1) per key (just two counters)
• Fast: O(1) operations
• Smooths out boundary burst problem

CONS:
• Approximation, not exact
• Slightly more complex than fixed window
```

### Algorithm 4: Token Bucket

Tokens added at constant rate, requests consume tokens.

```
// Pseudocode: Token bucket

CLASS TokenBucket:
    buckets = {}  // key -> (tokens, last_refill_time)
    
    FUNCTION check_and_consume(key, bucket_size, refill_rate):
        // bucket_size: Maximum tokens (burst capacity)
        // refill_rate: Tokens added per second
        
        entry = buckets.get(key, (bucket_size, now()))
        
        // Refill tokens based on time elapsed
        time_elapsed = now() - entry.last_refill_time
        tokens_to_add = time_elapsed * refill_rate
        current_tokens = min(bucket_size, entry.tokens + tokens_to_add)
        
        IF current_tokens >= 1:
            // Consume one token
            buckets[key] = (current_tokens - 1, now())
            RETURN ALLOWED
        ELSE:
            // No tokens available
            buckets[key] = (current_tokens, now())
            time_until_token = (1 - current_tokens) / refill_rate
            RETURN REJECTED(retry_after=time_until_token)

PROS:
• Smooth rate limiting (no burst at boundaries)
• Allows controlled bursts up to bucket size
• Intuitive model for API rate limiting

CONS:
• Slightly more complex to implement
• Two parameters to tune (size and rate)
```

### Algorithm 5: Leaky Bucket

Requests added to queue, processed at constant rate.

```
// Pseudocode: Leaky bucket

CLASS LeakyBucket:
    queues = {}  // key -> (queue_size, last_leak_time)
    
    FUNCTION check_and_add(key, bucket_size, leak_rate):
        // bucket_size: Maximum queue size
        // leak_rate: Requests processed per second
        
        entry = queues.get(key, (0, now()))
        
        // Leak requests based on time elapsed
        time_elapsed = now() - entry.last_leak_time
        requests_leaked = time_elapsed * leak_rate
        current_queue = max(0, entry.queue_size - requests_leaked)
        
        IF current_queue < bucket_size:
            // Add request to queue
            queues[key] = (current_queue + 1, now())
            RETURN ALLOWED
        ELSE:
            // Queue full
            queues[key] = (current_queue, now())
            RETURN REJECTED

PROS:
• Guarantees constant output rate
• Good for protecting backends that need steady load

CONS:
• Requests may be delayed (queued), not just rejected
• More complex to implement with actual queuing
• Usually simplified to just rejection (like token bucket)
```

### Algorithm Comparison and Selection

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ALGORITHM SELECTION GUIDE                                │
│                                                                             │
│   Algorithm          Memory   Accuracy   Burst      Best For                │
│   ────────────────────────────────────────────────────────────────────────  │
│   Fixed Window       O(1)     Low        Allowed    Simple APIs, internal   │
│   Sliding Log        O(n)     High       Blocked    Low-rate limits only    │
│   Sliding Counter    O(1)     Medium     Smoothed   Most API rate limiting  │
│   Token Bucket       O(1)     High       Allowed    Controlled burst APIs   │
│   Leaky Bucket       O(1)     High       Blocked    Backend protection      │
│                                                                             │
│   STAFF RECOMMENDATION:                                                     │
│   Start with Sliding Window Counter for most use cases.                     │
│   Use Token Bucket if you need to allow controlled bursts.                  │
│   Avoid Sliding Log unless limits are very low (< 100/window).              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Counter Store Design

### In-Memory Counter Store

```
// Pseudocode: High-performance in-memory counter store

CLASS CounterStore:
    // Sharded hash maps to reduce contention
    num_shards = 256
    shards = [HashMap() for _ in range(num_shards)]
    shard_locks = [RWLock() for _ in range(num_shards)]
    
    FUNCTION get_shard(key):
        RETURN hash(key) % num_shards
    
    FUNCTION increment(key, window):
        shard_id = get_shard(key)
        compound_key = key + ":" + window
        
        WITH shard_locks[shard_id].write_lock():
            current = shards[shard_id].get(compound_key, 0)
            shards[shard_id][compound_key] = current + 1
            RETURN current + 1
    
    FUNCTION get(key, window):
        shard_id = get_shard(key)
        compound_key = key + ":" + window
        
        WITH shard_locks[shard_id].read_lock():
            RETURN shards[shard_id].get(compound_key, 0)
    
    FUNCTION check_and_increment(key, window, limit):
        shard_id = get_shard(key)
        compound_key = key + ":" + window
        
        WITH shard_locks[shard_id].write_lock():
            current = shards[shard_id].get(compound_key, 0)
            IF current < limit:
                shards[shard_id][compound_key] = current + 1
                RETURN (TRUE, limit - current - 1)
            ELSE:
                RETURN (FALSE, 0)
    
    FUNCTION cleanup_expired(current_window):
        // Run periodically to remove old windows
        FOR shard_id IN range(num_shards):
            WITH shard_locks[shard_id].write_lock():
                expired = [k for k in shards[shard_id] if is_expired(k, current_window)]
                FOR key IN expired:
                    del shards[shard_id][key]

// Performance characteristics:
// - 256 shards = 256 independent hash maps
// - Concurrent reads/writes to different shards
// - Single-threaded: 10M+ ops/sec
// - Multi-threaded: scales linearly to ~64 cores
```

### Why Simpler Alternatives Fail

```
SIMPLE ALTERNATIVE 1: Single HashMap with global lock

Problem: Becomes bottleneck at ~100K ops/sec
Rate limiter becomes the slow point, adding latency to every request

SIMPLE ALTERNATIVE 2: Redis for everything

Problem: Network round-trip per request
Even with Redis pipeline, adds 0.5-2ms per request
At 10M req/sec, this is 5-20 million ms of added latency per second

SIMPLE ALTERNATIVE 3: Database (MySQL, PostgreSQL)

Problem: Far too slow for hot path
Database can handle ~10K writes/sec, we need 10M
10,000x gap is unbridgeable

STAFF APPROACH:
In-memory for hot path (counters)
Redis/Database only for cold path (configuration)
```

---

# Part 7: Data Model & Storage Decisions

## What Data Is Stored

### Hot Data (In-Memory)

```
COUNTER DATA:
{
    key: "customer_123:minute:2024-01-15T10:30",
    count: 457,
    first_request: 1705315800000,  // epoch ms
    last_request: 1705315857000
}

Size per entry: ~100 bytes
Active entries: ~500,000
Total hot data: ~50 MB
```

### Warm Data (Cached)

```
CONFIGURATION DATA:
{
    key: "customer_123",
    limits: {
        "default": {rate: 1000, window: "1m"},
        "/api/search": {rate: 10, window: "1s"},
        "/api/export": {rate: 1, window: "1h"}
    },
    tier: "enterprise",
    overrides: [
        {limit: 5000, window: "1m", expires: "2024-01-20T00:00:00Z"}
    ],
    updated_at: "2024-01-15T10:00:00Z"
}

Size per entry: ~500 bytes
Total customers: 100,000
Total config data: ~50 MB
```

### Cold Data (Persistent)

```
AUDIT LOG:
{
    timestamp: "2024-01-15T10:30:00Z",
    key: "customer_123",
    action: "limit_exceeded",
    count: 1001,
    limit: 1000,
    window: "1m",
    source_ip: "1.2.3.4",
    user_agent: "MyApp/1.0"
}

Volume: ~1% of requests (only violations)
At 10M req/sec peak, 1% = 100K events/sec
Daily: ~500M audit events
Storage: ~50 GB/day
```

## Key Design

```
KEY STRUCTURE:
rate_limit:{scope}:{identifier}:{window}

Examples:
- rate_limit:customer:cust_123:minute:2024-01-15T10:30
- rate_limit:user:user_456:minute:2024-01-15T10:30
- rate_limit:ip:1.2.3.4:minute:2024-01-15T10:30
- rate_limit:endpoint:/api/search:second:2024-01-15T10:30:45

KEY HASHING:
shard = hash(scope + identifier) % num_shards

Why include scope in hash:
- Same identifier in different scopes goes to different shards
- Prevents hot spots when one scope dominates
```

## Partitioning Strategy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PARTITIONING STRATEGY                                    │
│                                                                             │
│   PARTITION BY KEY HASH:                                                    │
│   • Each rate limiter node owns a range of hash values                      │
│   • Request routing: hash(key) → node                                       │
│   • Stateless routing, any router can compute correct node                  │
│                                                                             │
│   Example with 16 nodes:                                                    │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │  Node 0:  hash values 0-1023                                         │  │
│   │  Node 1:  hash values 1024-2047                                      │  │
│   │  Node 2:  hash values 2048-3071                                      │  │
│   │  ...                                                                 │  │
│   │  Node 15: hash values 15360-16383                                    │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ADVANTAGES:                                                               │
│   • No coordination between nodes for most requests                         │
│   • Linear scaling: 2x nodes = 2x capacity                                  │
│   • Simple rebalancing when nodes added/removed                             │
│                                                                             │
│   CHALLENGE: Hot keys (celebrity customer)                                  │
│   • One customer with 1M req/sec overloads single node                      │
│   • Solution: Split hot keys across multiple shards                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Retention Policies

```
DATA RETENTION:

COUNTERS (hot):
• TTL: 2 × window size (e.g., 2 minutes for 1-minute windows)
• Automatic expiry, no explicit cleanup needed

CONFIGURATION (warm):
• Retained until explicitly deleted
• Cached with 1-minute TTL, refresh on update

AUDIT LOGS (cold):
• 7 days hot storage (fast queries)
• 90 days warm storage (slower queries)
• 1 year archive (compliance)

METRICS:
• 1-minute resolution: 7 days
• 1-hour resolution: 90 days
• 1-day resolution: 2 years
```

## Schema Evolution

```
VERSION 1: Simple key-value
{key: "cust_123", limit: 1000, window: "1m"}

VERSION 2: Multiple limits per key
{
    key: "cust_123",
    limits: [
        {scope: "default", rate: 1000, window: "1m"},
        {scope: "/api/search", rate: 10, window: "1s"}
    ]
}

VERSION 3: Tiered limits with overrides
{
    key: "cust_123",
    tier: "enterprise",
    tier_limits: "enterprise_default",  // reference
    overrides: [
        {scope: "/api/search", rate: 100, window: "1s", expires: null}
    ],
    temporary_overrides: [
        {scope: "default", rate: 10000, window: "1m", expires: "2024-02-01"}
    ]
}

MIGRATION STRATEGY:
• New fields are optional, old format still works
• Reader handles all versions
• Background migration to latest format
• No downtime required
```

## Why Other Data Models Were Rejected

```
REJECTED: Time-series database for counters
Why: Overkill. We need current window only, not historical queries.
Counter increment is hot path, TSDB adds unnecessary latency.

REJECTED: SQL database for counters
Why: Far too slow. 10M writes/sec is impossible for any SQL database.
Even with sharding, coordination overhead is too high.

REJECTED: Single Redis instance
Why: Single point of failure, capacity limit.
Redis handles ~100K ops/sec per instance.
We need 10M ops/sec → 100+ Redis instances.
At that point, custom in-memory is simpler.

ACCEPTED: Hybrid approach
• In-memory for counters (hot path, ephemeral)
• Redis for configuration cache (warm path, replicated)
• PostgreSQL for configuration source of truth (cold path, persistent)
```

---

# Part 8: Consistency, Concurrency & Ordering

## Strong vs Eventual Consistency

### The Fundamental Trade-off

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONSISTENCY TRADE-OFF                                    │
│                                                                             │
│   STRONG CONSISTENCY (Global agreement on count):                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Every request globally coordinated                                 │   │
│   │  Latency: 50-200ms (cross-region consensus)                         │   │
│   │  Throughput: Limited by coordination                                │   │
│   │  Accuracy: Perfect                                                  │   │
│   │                                                                     │   │
│   │  Use when: Financial limits, legal requirements                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   EVENTUAL CONSISTENCY (Regional counting with sync):                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Requests counted locally, synced periodically                      │   │
│   │  Latency: <1ms                                                      │   │
│   │  Throughput: Scales linearly                                        │   │
│   │  Accuracy: Within 5-10% during sync lag                             │   │
│   │                                                                     │   │
│   │  Use when: Most API rate limiting                                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   STAFF DECISION:                                                           │
│   • Default to eventual consistency                                         │
│   • Accept over-counting (rejecting extra) over under-counting (allowing)   │
│   • Strong consistency only when explicitly required                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Eventual Consistency Implementation

```
// Pseudocode: Regional rate limiting with sync

CLASS RegionalRateLimiter:
    local_counters = {}
    local_budget = global_limit / num_regions
    sync_interval = 5 seconds
    
    FUNCTION check_rate_limit(key):
        // Fast path: Check local counter
        local_count = local_counters.get(key, 0)
        
        IF local_count < local_budget:
            local_counters[key] = local_count + 1
            RETURN ALLOWED
        ELSE:
            // At local limit, could still have global budget
            // Conservative: Reject (over-count is safe)
            RETURN REJECTED
    
    FUNCTION sync_with_global():
        // Run every sync_interval
        FOR key, count IN local_counters:
            // Report local count to global coordinator
            report_count(key, count)
        
        // Get updated budgets
        FOR key IN local_counters:
            global_remaining = get_global_remaining(key)
            // Adjust local budget based on global state
            local_budget[key] = calculate_fair_share(global_remaining)
        
        // Reset local counters for next sync period
        local_counters = {}

// Accuracy analysis:
// - Sync every 5 seconds
// - Worst case: All regions use full local budget before sync
// - Over-count: num_regions × local_budget = global_limit
// - At 3 regions with 1000/region budget: Could allow 3000 instead of 3000
// - Actual over-count: Usually <10% due to staggered sync
```

## Race Conditions

### Race Condition 1: Check-Then-Increment

```
BUGGY CODE:
count = get_count(key)      // Thread A reads: 999
                            // Thread B reads: 999
if count < 1000:
    increment_count(key)    // Thread A writes: 1000
                            // Thread B writes: 1001 (limit exceeded!)
    return ALLOWED

FIX: Atomic check-and-increment
result = atomic_increment_if_less_than(key, 1000)
if result.success:
    return ALLOWED
else:
    return REJECTED
```

### Race Condition 2: Window Boundary

```
SCENARIO:
Time: 11:59:59.999
Customer at 999/1000 requests

Thread A: Reads count (999), checks limit, increments to 1000
Thread B: Window rolls over to 12:00:00.000
Thread C: Reads count (1000 in new window? or old?), confused

FIX: Include window in counter key
key = customer_id + ":" + window_start_time
Each window is independent, no confusion
```

### Race Condition 3: Configuration Update

```
SCENARIO:
Limit being updated from 1000 to 500 req/sec

Thread A: Reads old limit (1000), allows request 750
Thread B: Updates limit to 500
Thread C: Reads new limit (500), rejects request 501

ISSUE: Inconsistent enforcement during update

FIX: Versioned configuration
Each request uses config version from request start
Config updates take effect on next window or after grace period
```

## Idempotency

```
IDEMPOTENCY REQUIREMENTS:

RATE LIMIT CHECK: Not idempotent (intentionally)
• Each check increments counter
• Retrying a check uses additional quota
• This is correct behavior: retry = new request

CONFIGURATION UPDATE: Must be idempotent
• Updating limit to 1000 twice should result in 1000
• Use PUT semantics, not increment semantics

COUNTER RESET: Must be idempotent
• Resetting a counter twice should not cause issues
• Implement as "set to 0" not "decrement by current value"
```

## Ordering Guarantees

```
ORDERING REQUIREMENTS:

WITHIN A KEY: Loose ordering acceptable
• Requests from same customer can be processed out of order
• Counter just needs to increment, order doesn't matter
• At worst, slight inaccuracy in remaining count header

ACROSS KEYS: No ordering required
• Different customers are independent
• No need to serialize requests across customers

CONFIGURATION UPDATES: Ordered by timestamp
• Later update should win
• Use version numbers or timestamps to resolve conflicts

PRACTICAL IMPACT:
Ordering is mostly irrelevant for rate limiting
Focus on throughput, not ordering guarantees
```

## Clock Assumptions

```
CLOCK REQUIREMENTS:

WALL CLOCK ACCURACY: ±1 second acceptable
• Windows are typically 1 minute or longer
• 1 second error = ~1.5% inaccuracy for 1-minute window
• Use NTP, monitor drift

MONOTONIC CLOCK: Required for duration calculations
• Token bucket needs elapsed time
• Wall clock can jump (DST, NTP corrections)
• Use monotonic clock for rate calculations

CROSS-NODE CLOCK SYNC: ±100ms typical
• Window boundaries may differ by 100ms between nodes
• Acceptable for most rate limiting
• If tighter sync needed, use logical clocks or central time service
```

## What Bugs Appear If Mishandled

```
BUG 1: Non-atomic increment
Symptom: Customers allowed 5-10% more than limit
Cause: Race condition between check and increment
Detection: Audit logs show count > limit

BUG 2: Wrong window calculation
Symptom: Limits reset at wrong times, inconsistent behavior
Cause: Timezone issues, DST transitions, clock skew
Detection: Customer complaints about "unfair" limiting

BUG 3: Missing cleanup of old windows
Symptom: Memory grows unbounded, OOM after days/weeks
Cause: Old window counters not expired
Detection: Memory monitoring, crash after extended uptime

BUG 4: Configuration race condition
Symptom: Old limits enforced after update
Cause: Cached configuration not invalidated
Detection: Customer reports limits not changing
```

---

# Part 9: Failure Modes & Degradation

## Failure Mode Enumeration

### Failure 1: Rate Limiter Node Crash

```
SCENARIO: One of 16 rate limiter nodes crashes

IMPACT:
• 1/16 of keys (6.25%) affected
• Requests to that shard fail or timeout
• If client retries to healthy node: Wrong shard, counter not found

DETECTION:
• Health check failures (immediate)
• Increased error rate on that shard
• Shard rebalancing alerts

MITIGATION:
• Consistent hashing with replicas
• Each key assigned to 2-3 nodes
• If primary fails, secondary takes over
• Slight accuracy loss (counter resets on failover)

BLAST RADIUS:
• 6.25% of customers see brief errors (seconds)
• No cascading failure to protected services
• System remains protective (fail-safe)
```

### Failure 2: Rate Limiter Cluster Overload

```
SCENARIO: Traffic spike overwhelms rate limiter cluster

IRONY: The system designed to prevent overload is itself overloaded

SYMPTOMS:
• Rate limit check latency increases to 50ms+
• Protected services now have 50ms extra latency on all requests
• Rate limiter becomes the bottleneck

MITIGATION:
• Rate limiter has its own internal rate limiting
• Shed load when approaching capacity
• Fail open with local caching when overloaded
• Alert on rate limiter latency, not just protected service latency

BLAST RADIUS:
• All requests affected by added latency
• If fail-open: Temporary loss of rate limiting protection
• Protected services may experience spike they should have been protected from
```

### Failure 3: Counter Store Corruption

```
SCENARIO: In-memory counters become corrupted or inconsistent

CAUSES:
• Memory corruption (rare, hardware issue)
• Bug in counter logic
• Race condition not properly handled

SYMPTOMS:
• Some customers always rejected (counter stuck at max)
• Some customers never limited (counter stuck at 0)
• Inconsistent remaining count headers

DETECTION:
• Customer complaints
• Monitoring: customers with 100% rejection rate
• Audit log analysis: violations don't match counter values

MITIGATION:
• Counter TTL forces eventual reset
• Manual reset capability for stuck keys
• Periodic counter verification against audit logs

BLAST RADIUS:
• Affected keys only
• Not system-wide (assuming localized corruption)
```

### Failure 4: Configuration Store Unavailable

```
SCENARIO: PostgreSQL/etcd storing rate limit configs is down

IMPACT:
• Cannot update rate limits
• Cannot add new customers
• Existing cached configs still work

MITIGATION:
• Cache configs aggressively (1-hour TTL)
• Rate limiter nodes can operate for hours without config store
• Fallback to default limits for uncached keys

BLAST RADIUS:
• New customers cannot be onboarded
• Limit changes delayed until config store recovers
• Existing traffic unaffected
```

### Failure 5: Network Partition

```
SCENARIO: Network partition isolates some rate limiter nodes

IMPACT:
• Requests to isolated nodes timeout
• Non-isolated nodes don't know about isolated node's counters
• Accuracy degrades (each partition enforces independently)

EXAMPLE:
• Partition splits 3-node cluster into 2 nodes and 1 node
• Customer with 1000 req/min limit
• 2-node partition: Allows 1000 requests
• 1-node partition: Also allows 1000 requests (doesn't know about other partition)
• Total: 2000 requests allowed (2x limit)

MITIGATION:
• Design for over-counting, not under-counting
• During partition: Each partition gets fraction of global limit
• After partition heals: Sync and reconcile

BLAST RADIUS:
• Temporary accuracy degradation (over-limit allowed)
• Usually resolves in seconds to minutes
```

## Graceful Degradation

```
// Pseudocode: Graceful degradation levels

ENUM DegradationLevel:
    NORMAL          // Full functionality
    ELEVATED        // Rate limiter under stress
    DEGRADED        // Partial functionality
    EMERGENCY       // Minimal protection only

CLASS GracefulDegradation:
    
    FUNCTION get_degradation_level():
        latency = get_p99_latency()
        error_rate = get_error_rate()
        capacity = get_capacity_utilization()
        
        IF latency < 5ms AND error_rate < 0.1% AND capacity < 70%:
            RETURN NORMAL
        ELSE IF latency < 20ms AND error_rate < 1% AND capacity < 90%:
            RETURN ELEVATED
        ELSE IF latency < 100ms AND error_rate < 5%:
            RETURN DEGRADED
        ELSE:
            RETURN EMERGENCY
    
    FUNCTION check_rate_limit(key, level):
        IF level == NORMAL:
            // Full rate limit check
            RETURN full_rate_limit_check(key)
        
        ELSE IF level == ELEVATED:
            // Skip non-critical features
            RETURN rate_limit_check_no_logging(key)
        
        ELSE IF level == DEGRADED:
            // Use cached results, skip counter update
            cached = get_cached_decision(key)
            IF cached != null:
                RETURN cached
            ELSE:
                // Optimistic allow with reduced limit
                RETURN ALLOW with reduced_limit
        
        ELSE:  // EMERGENCY
            // Fail open with minimal protection
            // Only enforce for known abusers
            IF is_known_abuser(key):
                RETURN REJECT
            ELSE:
                RETURN ALLOW
```

## Failure Timeline Walkthrough

```
INCIDENT: Rate Limiter Cluster Failure

T+0:00    Config store becomes unreachable (database failover)
          Impact: Config updates blocked, cached configs still work
          User impact: None (cached configs valid)

T+0:05    Alert: "Config store unreachable"
          On-call acknowledges

T+0:15    Database failover completes, config store back online
          Rate limiters re-sync configuration
          
T+0:30    Node 3 crashes (unrelated memory leak)
          Impact: 1/16 keys see brief errors
          Failover to replica begins

T+0:32    Replica for node 3 takes over
          Counters for affected keys reset to 0
          Impact: Affected customers get extra requests this window
          
T+0:35    Alert: "Node 3 failover complete"

T+1:00    Traffic spike from marketing campaign
          Rate limiter cluster at 85% capacity
          Degradation level: ELEVATED
          Non-critical logging disabled
          
T+1:15    Spike subsides, capacity back to 40%
          Degradation level: NORMAL
          Full functionality restored

T+2:00    Post-incident review scheduled
          Root causes: Database failover (expected), Memory leak (fix needed)
          Action items: Fix memory leak, improve failover alerting
```

## Real Incident: Structured Post-Mortem

| Dimension | Description |
|-----------|-------------|
| **Context** | Enterprise API serving 5M req/sec across 3 regions. Centralized rate limiter cluster (16 nodes) in primary region. Protected backend: search service, database, third-party APIs. |
| **Trigger** | Rate limiter node 3 developed memory leak. GC pauses stretched to 80ms. Concurrently, config store (database) entered planned failover. |
| **Propagation** | Node 3 latency spike → API servers waiting on rate limit check → thread pool exhaustion → 504 timeouts for all customers. Retry storm amplified load 2x. Other rate limiter nodes began queuing. Within 3 minutes, entire rate limiter cluster saturated. |
| **User impact** | 100% of API traffic affected. P99 latency: 30s (normal: 50ms). 15-minute sustained outage. ~2M failed requests. Customer SLAs breached. |
| **Engineer response** | On-call enabled circuit breaker bypass (fail open) at T+12min. Traffic flowed without rate limiting. Backend held. Root-cause: memory leak in counter compaction logic. Node restarted, config store recovered. Rate limiting re-enabled gradually (10%→50%→100%). |
| **Root cause** | No bounded latency on rate limit check. Hot path blocked on slow dependencies. No circuit breaker around rate limiter client. Protective system became single point of failure. |
| **Design change** | 5ms strict timeout on rate limit check. On timeout: fail open with cached decision. Circuit breaker: >10% timeouts → bypass rate limiter. Rate limiter treated as optional path, not blocking. |
| **Lesson** | The rate limiter must be simpler than the system it protects. If rate limiter failure causes outage, the design is wrong. Fail open with degraded limits beats fail closed. |

**Staff relevance**: L6 engineers anticipate that the protective layer can become the bottleneck. They design the caller (API servers) to degrade gracefully when the rate limiter is slow or unavailable—never to block indefinitely.

---

# Part 10: Performance Optimization & Hot Paths

## Critical Paths

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CRITICAL PATH: RATE LIMIT CHECK                          │
│                                                                             │
│   Request → Extract Key → Route to Shard → Check Counter → Respond          │
│              │              │                │                              │
│              ▼              ▼                ▼                              │
│           ~0.1ms         ~0.1ms           ~0.5ms                            │
│         (parsing)      (hashing)      (memory access                        │
│                                        + increment)                         │
│                                                                             │
│   TOTAL: <1ms P50, <5ms P99                                                 │
│                                                                             │
│   OPTIMIZATION PRIORITIES:                                                  │
│   1. Counter access (most time spent here)                                  │
│   2. Key extraction (second most)                                           │
│   3. Routing (negligible)                                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Caching Strategies

```
// Pseudocode: Multi-level caching

CLASS RateLimiterCache:
    
    // Level 1: Process-local cache (fastest)
    local_config_cache = LRUCache(max_size=10000, ttl=60s)
    
    // Level 2: Shared cache (Redis)
    shared_cache = RedisClient()
    
    // Level 3: Persistent store (PostgreSQL)
    config_store = PostgresClient()
    
    FUNCTION get_limit_config(key):
        // Check L1 (process-local)
        config = local_config_cache.get(key)
        IF config != null:
            RETURN config
        
        // Check L2 (shared cache)
        config = shared_cache.get("config:" + key)
        IF config != null:
            local_config_cache.set(key, config)
            RETURN config
        
        // Check L3 (persistent store)
        config = config_store.get(key)
        IF config != null:
            shared_cache.set("config:" + key, config, ttl=300s)
            local_config_cache.set(key, config)
            RETURN config
        
        // Key not found, use default
        RETURN default_config
    
    // Cache invalidation on config update
    FUNCTION on_config_update(key, new_config):
        config_store.update(key, new_config)
        shared_cache.delete("config:" + key)
        broadcast_invalidation(key)  // Tell all nodes to clear L1
```

## Precomputation vs Runtime Work

```
PRECOMPUTED (Offline):
• Window boundaries for next 24 hours
• Hash mappings for key → shard
• Default limits for each tier

RUNTIME (Hot Path):
• Current count lookup
• Limit comparison
• Counter increment

DEFERRED (Async):
• Audit log writes
• Metrics aggregation
• Cross-region sync
```

## Backpressure

```
// Pseudocode: Backpressure in rate limiter

CLASS BackpressureController:
    queue_depth = 0
    max_queue_depth = 1000
    processing_rate = 100000  // req/sec
    
    FUNCTION accept_request(request):
        IF queue_depth >= max_queue_depth:
            // Queue full, apply backpressure
            RETURN BACKPRESSURE_REJECT
        
        queue_depth += 1
        TRY:
            result = process_request(request)
            RETURN result
        FINALLY:
            queue_depth -= 1
    
    FUNCTION get_backpressure_response():
        RETURN {
            status: 503,
            headers: {
                "Retry-After": calculate_retry_delay(),
                "X-Backpressure": "true"
            },
            body: "Rate limiter temporarily overloaded, please retry"
        }
```

## Load Shedding

```
// Pseudocode: Load shedding strategy

CLASS LoadShedder:
    
    FUNCTION should_shed(request, current_load):
        IF current_load < 0.8:
            RETURN FALSE  // Normal operation
        
        // Prioritize by customer tier
        tier = get_customer_tier(request.key)
        
        IF tier == "enterprise" AND current_load < 0.95:
            RETURN FALSE  // Enterprise gets priority
        
        IF tier == "free" AND current_load > 0.85:
            RETURN TRUE  // Shed free tier first
        
        IF current_load > 0.95:
            // Shed randomly to reduce load
            RETURN random() < (current_load - 0.95) / 0.05
        
        RETURN FALSE
    
    FUNCTION shed_request(request):
        RETURN {
            status: 503,
            headers: {
                "Retry-After": "5",
                "X-Load-Shed": "true"
            }
        }
```

## Why Some Optimizations Are NOT Done

```
OPTIMIZATION NOT DONE: Batch counter updates

WHY IT SEEMS GOOD:
Instead of incrementing counter on every request,
batch updates and write every 100 requests

WHY IT'S WRONG:
• Delays limit enforcement by up to 100 requests
• Customer at 999 could get 1098 requests before rejection
• Defeats the purpose of rate limiting

OPTIMIZATION NOT DONE: Predictive limiting

WHY IT SEEMS GOOD:
Use ML to predict which requests will cause limit violation

WHY IT'S WRONG:
• Adds complexity and latency
• Simple counting is accurate and fast
• Prediction errors cause unfair rejections
• Not worth the complexity

OPTIMIZATION NOT DONE: Compressed counters

WHY IT SEEMS GOOD:
Store counts in compressed format to save memory

WHY IT'S WRONG:
• Memory is not the bottleneck (50MB is nothing)
• Compression/decompression adds CPU overhead
• Premature optimization for non-existent problem
```

---

# Part 11: Cost & Efficiency

## Major Cost Drivers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RATE LIMITER COST BREAKDOWN                              │
│                                                                             │
│   COMPUTE (60% of cost):                                                    │
│   • Rate limiter nodes processing 10M req/sec                               │
│   • ~50 nodes at $500/month each = $25,000/month                            │
│                                                                             │
│   MEMORY (15% of cost):                                                     │
│   • 50MB per node for counters (negligible)                                 │
│   • 50MB per node for config cache (negligible)                             │
│   • Memory is not a significant cost driver                                 │
│                                                                             │
│   NETWORK (10% of cost):                                                    │
│   • Inter-node communication for sync                                       │
│   • Cross-region replication                                                │
│   • ~$5,000/month for moderate traffic                                      │
│                                                                             │
│   STORAGE (5% of cost):                                                     │
│   • Audit logs: 50GB/day × 30 days = 1.5TB                                  │
│   • Configuration database: Negligible                                      │
│   • ~$500/month                                                             │
│                                                                             │
│   OPERATIONS (10% of cost):                                                 │
│   • On-call time                                                            │
│   • Monitoring infrastructure                                               │
│   • ~$5,000/month (engineering time)                                        │
│                                                                             │
│   TOTAL: ~$35,000/month for 10M req/sec capacity                            │
│   COST PER MILLION REQUESTS: ~$0.004                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## How Cost Scales

```
SCALING ANALYSIS:

10M req/sec → 50 nodes → $35K/month → $0.004/million
100M req/sec → 500 nodes → $350K/month → $0.004/million

Cost scales linearly with traffic (good)
No super-linear cost drivers

COST OPTIMIZATION OPPORTUNITIES:

1. Better bin-packing (run other services on same nodes)
   Potential savings: 20-30% of compute

2. Spot/preemptible instances for non-critical nodes
   Potential savings: 50% of compute for those nodes

3. Reduce audit log retention
   90 days → 30 days saves 67% of storage

4. Sample audit logs (1% of requests vs all)
   100x reduction in log volume
```

## Trade-offs: Cost vs Reliability

```
RELIABILITY LEVELS:

LEVEL 1: Single region, no redundancy
• Cost: $15K/month
• Availability: 99%
• Failure mode: Region outage = total outage

LEVEL 2: Single region, redundant nodes
• Cost: $25K/month
• Availability: 99.9%
• Failure mode: Can survive node failures

LEVEL 3: Multi-region, active-passive
• Cost: $50K/month
• Availability: 99.95%
• Failure mode: Can survive region outage with failover

LEVEL 4: Multi-region, active-active
• Cost: $75K/month
• Availability: 99.99%
• Failure mode: Transparent regional failures

STAFF RECOMMENDATION:
Most systems: Level 2 (redundant single-region)
Critical APIs: Level 3 (multi-region active-passive)
Global consumer products: Level 4 (active-active)
```

## What Over-Engineering Looks Like

```
OVER-ENGINEERED RATE LIMITER:

• Strong consistency across all regions (adds 100ms latency)
• Microsecond-accurate windows (no one needs this)
• Full request body logging (massive storage, privacy risk)
• ML-based anomaly detection (simple thresholds work fine)
• Real-time analytics dashboard (batch is sufficient)
• Automatic limit adjustment (manual is safer)

COST OF OVER-ENGINEERING:
• 3x infrastructure cost
• 5x operational complexity
• Higher latency (defeats purpose)
• More failure modes

STAFF APPROACH:
• Start simple
• Add complexity only when needed
• Measure before optimizing
```

## Cost-Aware Redesign

```
// Pseudocode: Cost-optimized rate limiter

ORIGINAL DESIGN:
- 50 dedicated rate limiter nodes
- Redis cluster for shared state
- PostgreSQL for configuration
- Elasticsearch for audit logs
Cost: $35K/month

COST-OPTIMIZED DESIGN:
- Rate limiting embedded in API servers (no separate nodes)
- Local counters with async sync (no Redis)
- Configuration from config service (shared with other systems)
- Sampled audit logs to existing log infrastructure
Cost: $5K/month (incremental cost over existing API servers)

TRADE-OFFS:
- Slightly less isolation (rate limiter shares fate with API server)
- Lower accuracy (eventual consistency)
- Less detailed audit trail (sampling)

WHEN TO USE COST-OPTIMIZED:
- Internal services
- Low-risk APIs
- Cost-sensitive environments

WHEN TO USE FULL DESIGN:
- Customer-facing APIs
- Billing-related limits
- Security-critical rate limiting
```

---

# Part 12: Multi-Region & Global Considerations

## Data Locality

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-REGION RATE LIMITING                               │
│                                                                             │
│   OPTION 1: GLOBAL COUNTERS (Strong Consistency)                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │     US-EAST              EU-WEST              AP-NORTH              │   │
│   │        │                    │                    │                  │   │
│   │        └────────────────────┼────────────────────┘                  │   │
│   │                             ▼                                       │   │
│   │                    ┌───────────────┐                                │   │
│   │                    │ Global Counter│                                │   │
│   │                    │  (consensus)  │                                │   │
│   │                    └───────────────┘                                │   │
│   │                                                                     │   │
│   │   Latency: 50-200ms per request (cross-region consensus)            │   │
│   │   Accuracy: Perfect                                                 │   │
│   │   Use: Almost never (latency is unacceptable)                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   OPTION 2: REGIONAL COUNTERS (Eventual Consistency)                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │     US-EAST              EU-WEST              AP-NORTH              │   │
│   │   ┌─────────┐          ┌─────────┐          ┌─────────┐             │   │
│   │   │Regional │──sync─── │Regional │──sync─── │Regional │             │   │
│   │   │Counter  │          │Counter  │          │Counter  │             │   │
│   │   └─────────┘          └─────────┘          └─────────┘             │   │
│   │                                                                     │   │
│   │   Latency: <1ms per request (local counter)                         │   │
│   │   Accuracy: Within 10% during sync lag                              │   │
│   │   Use: Most rate limiting                                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Replication Strategies

```
// Pseudocode: Regional rate limiting with async sync

CLASS GlobalRateLimiter:
    regions = ["us-east", "eu-west", "ap-north"]
    local_region = get_local_region()
    regional_counters = {}  // key -> count
    global_budget = {}      // key -> remaining budget
    sync_interval = 5 seconds
    
    FUNCTION check_rate_limit(key, global_limit):
        // Each region gets fair share of global limit
        regional_budget = global_budget.get(key, global_limit / len(regions))
        regional_count = regional_counters.get(key, 0)
        
        IF regional_count < regional_budget:
            regional_counters[key] = regional_count + 1
            RETURN ALLOWED
        ELSE:
            // At regional limit
            // Could request more budget from global coordinator
            // Or conservatively reject
            RETURN REJECTED
    
    FUNCTION sync():
        // Report local usage to global coordinator
        FOR key, count IN regional_counters:
            report_usage(key, count, local_region)
        
        // Get updated budgets from global coordinator
        FOR key IN regional_counters:
            remaining = get_global_remaining(key)
            // Distribute remaining budget across regions
            // Weight by recent usage patterns
            global_budget[key] = calculate_regional_budget(key, remaining)
        
        // Reset regional counters for next sync period
        regional_counters = {}
    
    FUNCTION get_global_remaining(key):
        // Sum usage across all regions
        total_used = sum(get_usage(key, region) FOR region IN regions)
        RETURN global_limit - total_used
```

## Traffic Routing

```
ROUTING CONSIDERATIONS:

USER AFFINITY:
• User's requests should go to same region (for counter accuracy)
• Use GeoDNS to route to nearest region
• Sticky sessions within a region

KEY AFFINITY:
• Same key should be handled by same shard
• Consistent hashing ensures this
• Cross-region: Key determines primary region

FAILOVER ROUTING:
• If regional rate limiter is down, route to backup region
• Accept accuracy loss during failover
• Sync when original region recovers
```

## Failure Across Regions

```
FAILURE SCENARIO: US-EAST region completely isolated

IMPACT ON RATE LIMITING:
• US-EAST continues with local counters
• EU-WEST and AP-NORTH don't see US-EAST usage
• Global limit potentially exceeded by 33% (US-EAST's share)

MITIGATION:
• Design limits with regional isolation in mind
• Global limit = sum of regional limits (worst case: full limit per region)
• Or: Accept over-limit during partition, reconcile after

POST-RECOVERY:
• Sync all regions
• Reconcile counters
• Adjust for over-usage in next window
```

## When Multi-Region Is NOT Worth It

```
SKIP MULTI-REGION RATE LIMITING IF:

• 90%+ of traffic is from one region
  → Single region with CDN for others

• Accuracy is more important than latency
  → Centralized rate limiting with latency penalty

• Rate limits are generous (10x actual usage)
  → Regional rate limiting with generous local limits

• Protected service is single-region
  → Rate limiter in same region, no multi-region needed

ALWAYS MULTI-REGION IF:

• User-facing API with global users
• Limits are tight (close to actual usage)
• Low latency is critical (<5ms for rate limit check)
• High availability required (99.99%+)
```

---

# Part 13: Security & Abuse Considerations

## Abuse Vectors

```
ABUSE VECTOR 1: KEY FORGERY
Attack: Create fake API keys to get more quota
Mitigation: 
• Cryptographically signed API keys
• Key validation on every request
• Rate limit by account, not just key

ABUSE VECTOR 2: DISTRIBUTED ATTACKS
Attack: Use many IPs to bypass per-IP limits
Mitigation:
• Per-account limits (not just per-IP)
• Behavioral analysis (patterns across IPs)
• CAPTCHA for suspicious patterns

ABUSE VECTOR 3: TIME MANIPULATION
Attack: Client sends requests with fake timestamps
Mitigation:
• Use server-side time only
• Never trust client-provided timestamps
• Validate time-based tokens server-side

ABUSE VECTOR 4: LIMIT PROBING
Attack: Probe to find exact limit, then use exactly that much
Mitigation:
• Not really abuse (they're using their limit)
• Add small randomness to limits if concerned
• Monitor for customers consistently at limit

ABUSE VECTOR 5: RATE LIMITER DOS
Attack: Overwhelm rate limiter itself
Mitigation:
• Rate limiter has its own rate limiting
• Load shedding under stress
• Fail open rather than cascade failure
```

## Rate Abuse Patterns

```
PATTERN 1: CREDENTIAL STUFFING
Behavior: Many login attempts for different accounts from same source
Detection: High request rate to /login endpoint
Response: Progressively stricter limits, CAPTCHA, block source

PATTERN 2: API SCRAPING
Behavior: Systematic access to paginated resources
Detection: Sequential ID access, high data endpoint usage
Response: Per-endpoint limits, exponential backoff for repeat violations

PATTERN 3: FAKE ACCOUNT CREATION
Behavior: Many account creations from same source
Detection: High /signup rate, similar patterns
Response: CAPTCHA, email verification, stricter limits

PATTERN 4: FLASH LOAN ATTACKS (Financial)
Behavior: Many transactions in single block
Detection: Burst of related transactions
Response: Per-block limits, anti-front-running measures
```

## Data Exposure Risks

```
DATA EXPOSED BY RATE LIMITER:

VISIBLE TO RATE LIMITER:
• API keys (authentication)
• User IDs
• IP addresses
• Request paths and methods
• Request rates per customer

PRIVACY MITIGATIONS:
• Hash API keys before logging
• Aggregate metrics (not per-request)
• Short retention for detailed logs
• Access controls on rate limiter data

DATA NOT STORED:
• Request bodies
• Response bodies
• Full headers (only relevant ones)
```

## Privilege Boundaries

```
PRIVILEGE LEVELS:

READ-ONLY (Support):
• View rate limit status for a customer
• View aggregate metrics
• Cannot change limits

OPERATOR:
• Temporarily increase limits
• Reset counters
• Cannot change permanent configuration

ADMIN:
• Create/modify rate limit rules
• Change customer tiers
• Full configuration access

AUTOMATION:
• Automatic temporary overrides
• Alert-triggered limit increases
• Audit-logged, reviewable

SEPARATION:
• Rate limiter cannot modify protected service data
• Rate limiter cannot bypass its own limits
• Changes require approval workflow
```

## Why Perfect Security Is Impossible

```
FUNDAMENTAL LIMITS:

LIMIT 1: Distributed systems have coordination costs
• Perfect enforcement requires global coordination
• Global coordination adds latency
• Trade-off: Accuracy vs performance

LIMIT 2: Determined attackers find workarounds
• Rate limiting is one layer of defense
• Must combine with other security measures
• Assume some abuse will occur

LIMIT 3: False positives harm legitimate users
• Too strict: Block good users
• Too loose: Allow abuse
• Perfect balance is impossible

STAFF APPROACH:
• Defense in depth (multiple layers)
• Optimize for common case (legitimate users)
• Detect and respond to abuse (not just prevent)
• Accept some level of abuse as cost of service
```

---

# Part 13b: Observability

Rate limiting runs in the hot path. Without observability, failures are invisible until users complain. Staff engineers instrument for detection, not just post-mortem debugging.

## SLIs and SLOs

| SLI | Target | Measurement | Rationale |
|-----|--------|-------------|-----------|
| Rate limit check latency (P50) | <1ms | Time from check request to response | Hot path; must not add noticeable delay |
| Rate limit check latency (P99) | <5ms | Same | Tail latency affects overall request latency |
| Rate limit check latency (P99.9) | <10ms | Same | Prevents rate limiter from becoming bottleneck |
| Rate limiter availability | 99.99% | Successful checks / total checks | Must exceed protected service availability |
| Configuration propagation delay | <60s | Time from config update to first enforcement | New limits and overrides must take effect promptly |
| Counter accuracy (when sync enabled) | Within 5% of limit | Sampled audit vs expected | Validates approximate counting assumptions |

## Dashboard Essentials

```
PRIMARY DASHBOARD (On-call view):
• Latency histogram (P50, P90, P99, P99.9) for rate limit checks
• Error rate by error type (timeout, reject, config_missing)
• Requests per second by shard (detect hot shards)
• Circuit breaker state (open/closed, when last opened)
• Config store latency (separate from hot path, but indicative)

SECONDARY (Operational):
• Rejection rate by customer tier
• Top customers by rejection count
• Config cache hit rate
• Counter store memory usage per node
```

## Alerting Strategy

| Alert | Condition | Severity | Action |
|-------|-----------|----------|--------|
| Rate limiter latency high | P99 > 10ms for 5 min | P1 | Investigate; consider circuit breaker |
| Rate limiter errors elevated | Error rate > 1% for 2 min | P1 | Check cluster health, config store |
| Config store unreachable | Connection failures for 1 min | P2 | Cached configs still work; fix store |
| Circuit breaker open | Breaker open for 5 min | P2 | Rate limiting bypassed; fix underlying cause |
| Hot key detected | Single key > 10% of shard traffic | P3 | Capacity planning; consider shard split |

**Staff insight**: Alert on rate limiter health independently of protected service. If you only alert when the API is down, you will miss rate limiter-induced latency and retry storms.

## Cross-Team Considerations

| Concern | Staff Approach |
|---------|----------------|
| **Ownership** | Infra/platform typically owns rate limiter; product owns limit values and policy. Clear handoff: "We enforce; you decide the numbers." |
| **Configuration** | Config store is shared. Product/account team needs UI or API to set limits. Audit who changed what. |
| **Paging** | Rate limiter outage pages infra. Incorrect limits page product/support. Document runbooks per team. |
| **Customer-facing vs internal** | Customer-facing: stricter SLAs, more visible. Internal: can tolerate looser accuracy, faster iteration. |
| **Dependencies** | API servers depend on rate limiter. Rate limiter depends on config store. Document and test failure of each. |

---

## Audit Trail and Forensics

```
WHAT TO LOG (violations only, not every check):
• Key, limit, count, timestamp, source_ip
• NOT: Full API keys, request bodies

RETENTION:
• 7 days hot (fast queries for support)
• 90 days warm (investigations)
• 1 year archive (compliance)

USE CASES:
• Customer claims incorrect limiting → compare audit vs limit
• Abuse investigation → pattern analysis across keys
• Post-incident → verify counter consistency
```

---

# Part 14: Evolution Over Time

## V1: Naive Design

```
V1 DESIGN: In-process rate limiting

ARCHITECTURE:
Each API server has local rate limiter
No coordination between servers

IMPLEMENTATION:
in_memory_counter = {}

def check_limit(key, limit):
    if key not in in_memory_counter:
        in_memory_counter[key] = 0
    if in_memory_counter[key] < limit:
        in_memory_counter[key] += 1
        return ALLOWED
    return REJECTED

PROBLEMS:
• Each server enforces independently
• Customer with 100 req/min limit gets 100 × N servers
• No global enforcement
• Limits ineffective

LIFESPAN: 1-3 months before problems noticed
```

## What Breaks First

```
FAILURE TIMELINE:

MONTH 1: Noisy neighbor incident
• One customer runs 1000x normal traffic
• API servers overloaded
• All customers affected
• Post-mortem: "We need real rate limiting"

MONTH 2: Redis-based rate limiting deployed
• Centralized counters in Redis
• All servers coordinate
• Limits properly enforced

MONTH 6: Redis becomes bottleneck
• 100K ops/sec exceeds single Redis capacity
• Latency increases to 20ms
• Rate limiter slowing down all requests

MONTH 7: Redis cluster deployed
• Sharded Redis cluster
• 1M ops/sec capacity
• Latency back to acceptable

MONTH 12: Multi-region expansion
• Single Redis cluster is single region
• Cross-region latency unacceptable
• Need regional rate limiters with sync
```

## V2: Improvements

```
V2 DESIGN: Distributed rate limiting with regional coordination

ARCHITECTURE:
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│     US-EAST                              EU-WEST                            │
│   ┌───────────────────┐                ┌───────────────────┐                │
│   │  Rate Limiter     │◄──async sync──►│  Rate Limiter     │                │
│   │  Cluster          │                │  Cluster          │                │
│   │  (3 nodes)        │                │  (3 nodes)        │                │
│   └───────────────────┘                └───────────────────┘                │
│            ▲                                    ▲                           │
│            │                                    │                           │
│   ┌────────┴────────┐                  ┌────────┴────────┐                  │
│   │   API Servers   │                  │   API Servers   │                  │
│   └─────────────────┘                  └─────────────────┘                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

IMPROVEMENTS:
• Regional clusters for low latency
• Async sync for global coordination
• Graceful degradation during sync failures
• Scalable to millions of req/sec
```

## Long-Term Stable Architecture

```
V3 DESIGN: Production-grade rate limiting

COMPONENTS:
1. Rate Limiter Nodes (Stateless, sharded)
   • In-memory counters per shard
   • Consistent hashing for key → node
   • Auto-scaling based on load

2. Regional Coordinators
   • Aggregate regional usage
   • Sync with other regions
   • Budget allocation

3. Global Coordinator (Active-Passive)
   • Global limit management
   • Cross-region visibility
   • Rarely in hot path

4. Configuration Service
   • Rate limit rules
   • Customer tiers
   • Admin UI

5. Observability Stack
   • Metrics and alerting
   • Audit logs
   • Analytics

CHARACTERISTICS:
• <1ms P50 latency
• 99.99% availability
• Linear cost scaling
• Regional independence
• Global coordination when needed
```

## How Incidents Drive Redesign

```
INCIDENT: Customer allowed 10x limit during region failover

ROOT CAUSE:
• US-EAST failed over to EU-WEST
• EU-WEST had no knowledge of US-EAST's counters
• Customer got full limit in both regions

REDESIGN:
• Cross-region counter replication
• Failover includes counter handoff
• Budget reservation (not just count sync)

INCIDENT: Rate limiter latency spike during traffic burst

ROOT CAUSE:
• Token bucket implementation had lock contention
• All requests for hot customer serialized on one lock
• P99 latency spiked to 100ms

REDESIGN:
• Sharded counters per customer
• Lock-free data structures
• Hot customer detection and special handling

INCIDENT: Audit log storage explosion

ROOT CAUSE:
• Logging every request, not just violations
• 10M req/sec × 1KB = 10GB/sec of logs
• Storage costs 100x expected

REDESIGN:
• Log violations only
• Sample successful requests (1%)
• Tiered retention (detailed: 1 day, summary: 90 days)
```

---

# Part 15: Alternatives & Explicit Rejections

## Alternative 1: Embedded Rate Limiting (In-Process)

```
DESIGN:
Rate limiting logic embedded in each API server
No external rate limiting service

WHY IT SEEMS ATTRACTIVE:
• Zero network latency for rate limit check
• No external dependency
• Simpler deployment

WHY A STAFF ENGINEER REJECTS IT:
• Cannot enforce global limits across servers
• Customer limit = limit × number of servers
• Scaling API servers increases customer quota (wrong!)
• No central visibility or control

WHEN IT MIGHT WORK:
• Per-connection limits (e.g., WebSocket message rate)
• Supplementary local limits (belt and suspenders)
• Very early stage (MVP)
```

## Alternative 2: Database-Based Rate Limiting

```
DESIGN:
Store counters in MySQL/PostgreSQL
Atomic increment with SELECT FOR UPDATE

WHY IT SEEMS ATTRACTIVE:
• Durable counters (survive restarts)
• Strong consistency
• Existing infrastructure (database already exists)

WHY A STAFF ENGINEER REJECTS IT:
• Far too slow for hot path
• Database handles ~10K writes/sec, we need 10M
• Connection limits become bottleneck
• Adds database dependency to all requests

WHEN IT MIGHT WORK:
• Very low-rate limits (hourly, daily)
• Billing-related limits where accuracy is critical
• Write path for configuration (not counters)
```

## Alternative 3: Consensus-Based Global Counters

```
DESIGN:
Use Paxos/Raft for global counter agreement
Every increment is a consensus operation

WHY IT SEEMS ATTRACTIVE:
• Perfect accuracy
• Strong consistency guarantees
• No over-counting possible

WHY A STAFF ENGINEER REJECTS IT:
• Cross-region consensus adds 50-200ms latency
• Rate limiter becomes slower than protected service
• Defeats the purpose (protection shouldn't be bottleneck)
• Consensus failures affect all requests

WHEN IT MIGHT WORK:
• Financial rate limits where accuracy is critical
• Very low-rate limits (per-hour, per-day)
• When 100ms latency is acceptable
```

---

# Part 16: Interview Calibration

## How Interviewers Probe Rate Limiting

```
PROBE 1: "How do you enforce a global limit across regions?"
Looking for: Understanding of consistency trade-offs
Red flag: "Just use a global counter"
Green flag: "We accept approximate counting for latency..."

PROBE 2: "What happens if the rate limiter goes down?"
Looking for: Failure mode thinking
Red flag: "All requests fail" (no degradation)
Green flag: "Fail open with cached limits, alert on failure"

PROBE 3: "How do you handle a hot key?"
Looking for: Scaling awareness
Red flag: No answer (hasn't thought about it)
Green flag: "Shard the counter, replicate across nodes"

PROBE 4: "Why not just use a database?"
Looking for: Understanding of latency requirements
Red flag: "Sure, that works"
Green flag: "Too slow, explains why in-memory is necessary"
```

## Common L5 Mistakes

```
MISTAKE 1: Designing for perfect accuracy
L5: "We need exactly 1000 requests, no more"
L6: "We need approximately 1000 requests. 5% over-count is acceptable."

MISTAKE 2: Ignoring failure modes
L5: "Rate limiter calls Redis, done"
L6: "What if Redis is down? Slow? What's the degradation plan?"

MISTAKE 3: Over-engineering
L5: "We need ML to detect anomalies in real-time"
L6: "Simple threshold detection works. ML adds complexity without clear benefit."

MISTAKE 4: Under-considering latency
L5: "Let's coordinate across regions for accuracy"
L6: "200ms coordination latency is unacceptable. Local counting with sync."
```

## Staff-Level Answers

```
QUESTION: "Design a global rate limiter"

L5 ANSWER:
"Use Redis cluster, atomic increment, consistent hashing."
(Correct but shallow, doesn't address trade-offs)

L6 ANSWER:
"First, let me understand the requirements:
- What accuracy is needed? Can we tolerate 5-10% over-counting?
- What latency is acceptable? Sub-millisecond or is 5ms OK?
- What happens during failure? Fail open or fail closed?

For most API rate limiting, I'd recommend:
- Regional rate limiting with eventual consistency
- Local counters for sub-millisecond checks
- Async sync between regions (5-second intervals)
- Fail open with degraded limits during failures

This trades perfect accuracy for latency and availability.
If we need exact limits (e.g., financial), we'd use a different approach..."
```

## Example Phrases Staff Engineers Use

```
"We intentionally over-count to avoid under-counting. 
Under-counting means abuse; over-counting just means some legitimate
requests are delayed until the next window."

"The rate limiter must be simpler than the system it protects.
If the rate limiter is a complex distributed system, we've just
moved the problem, not solved it."

"I'd start with the simplest algorithm that meets our needs—
probably sliding window counters. Token bucket adds complexity
that we might not need."

"During a regional outage, we accept temporarily looser limits.
Global consistency would mean global unavailability during partition."

"What's the cost of getting this wrong? If 1100 requests instead of
1000 isn't catastrophic, we can use approximate counting and
save significant complexity."
```

## Staff Signals vs Senior Mistakes

| Signal | Staff (L6) | Senior (L5) |
|--------|------------|-------------|
| **Accuracy** | Asks "What accuracy do we actually need?" before designing. Proposes over-count when uncertain. | Assumes exact limits required. Designs for perfect consistency. |
| **Failure modes** | Enumerates: node crash, config store down, overload, partition. Designs degradation for each. | Mentions failover. Often ignores "rate limiter as bottleneck." |
| **Latency** | Puts latency budget on the table first. Rejects designs that add >5ms. | Focuses on correctness. Latency is an afterthought. |
| **Cross-team** | Considers: Who configures limits? Who gets paged? Product vs infra ownership. | Designs in isolation. Assumes single-team ownership. |

**Common Senior mistake**: Designing a rate limiter that becomes the bottleneck. Senior engineers optimize for accuracy; Staff engineers optimize for the rate limiter remaining invisible and non-blocking.

## How to Teach This Topic

1. **Start with the goal**: Protection, not precision. Every design choice flows from this.
2. **Introduce the tension**: Accuracy vs latency. Strong consistency adds 50–200ms. That is unacceptable for most APIs.
3. **Walk through failure modes**: What if the rate limiter is slow? Down? Partitioned? Fail open with degraded limits.
4. **Use the Real Incident table**: Show how a protective system caused outage. Discuss circuit breaker, timeouts, fail-open.
5. **Compare algorithms**: Fixed window (simple), sliding counter (recommended), token bucket (bursts). Avoid sliding log at scale.
6. **Emphasize observability**: Rate limiter must have its own SLIs. Do not infer health from protected service alone.

## Leadership Explanation (Non-Engineers)

> "Rate limiting is like a bouncer at a club: we count how many people (requests) come in and turn people away when we hit capacity. The hard part at scale: we have many doors (servers) and need them to agree on the count. Perfect agreement is slow and expensive. We accept 'close enough' counting so we stay fast. If the bouncer gets sick, we let people in with a soft limit rather than shutting down the club—better some extra traffic than no service at all."

---

# Part 17: Diagrams

## Diagram 1: High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RATE LIMITER: HIGH-LEVEL ARCHITECTURE                    │
│                                                                             │
│                           ┌───────────────┐                                 │
│                           │    Clients    │                                 │
│                           │ (API Servers) │                                 │
│                           └───────┬───────┘                                 │
│                                   │ Rate limit check                        │
│                                   ▼                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    RATE LIMITER CLUSTER                             │   │
│   │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │   │
│   │   │   Node 1    │  │   Node 2    │  │   Node 3    │   ...           │   │
│   │   │  Hash: 0-3  │  │  Hash: 4-7  │  │  Hash: 8-11 │                 │   │
│   │   │             │  │             │  │             │                 │   │
│   │   │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │                 │   │
│   │   │ │Counters │ │  │ │Counters │ │  │ │Counters │ │                 │   │
│   │   │ │(memory) │ │  │ │(memory) │ │  │ │(memory) │ │                 │   │
│   │   │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │                 │   │
│   │   │             │  │             │  │             │                 │   │
│   │   │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │                 │   │
│   │   │ │ Config  │ │  │ │ Config  │ │  │ │ Config  │ │                 │   │
│   │   │ │ (cache) │ │  │ │ (cache) │ │  │ │ (cache) │ │                 │   │
│   │   │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │                 │   │
│   │   └─────────────┘  └─────────────┘  └─────────────┘                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                   │                                         │
│                          Config sync (async)                                │
│                                   ▼                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    CONFIGURATION STORE                              │   │
│   │                    (PostgreSQL / etcd)                              │   │
│   │                                                                     │   │
│   │   Limits, Rules, Customer Tiers, Overrides                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   KEY INSIGHT: Hot path (rate limit check) never hits configuration store   │
│   Only cold path (config updates, admin operations) touches storage         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 2: Request Flow (Data Flow)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RATE LIMIT CHECK: REQUEST FLOW                           │
│                                                                             │
│   API Server                    Rate Limiter                                │
│       │                              │                                      │
│       │  1. Check rate limit         │                                      │
│       │  key="cust_123"              │                                      │
│       ├─────────────────────────────►│                                      │
│       │                              │                                      │
│       │                              │  2. Hash key, find shard             │
│       │                              │     hash("cust_123") % 16 = 5        │
│       │                              │     → Node handling shard 5          │
│       │                              │                                      │
│       │                              │  3. Get current count                │
│       │                              │     counters["cust_123:min:10:30"]   │
│       │                              │     → 457                            │
│       │                              │                                      │
│       │                              │  4. Get limit from config cache      │
│       │                              │     config["cust_123"].limit         │
│       │                              │     → 1000                           │
│       │                              │                                      │
│       │                              │  5. Compare: 457 < 1000              │
│       │                              │     → ALLOW                          │
│       │                              │                                      │
│       │                              │  6. Increment counter                │
│       │                              │     counters["cust_123:min:10:30"]   │
│       │                              │     → 458                            │
│       │                              │                                      │
│       │  7. Response: ALLOWED        │                                      │
│       │     remaining: 542           │                                      │
│       │     reset_at: 10:31:00       │                                      │
│       │◄─────────────────────────────┤                                      │
│       │                              │                                      │
│                                                                             │
│   LATENCY BREAKDOWN:                                                        │
│   • Network: 0.2ms                                                          │
│   • Hash calculation: 0.01ms                                                │
│   • Counter lookup: 0.1ms                                                   │
│   • Config lookup: 0.1ms (cached)                                           │
│   • Counter increment: 0.1ms                                                │
│   • Response: 0.2ms                                                         │
│   • TOTAL: <1ms                                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 3: Failure Propagation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FAILURE MODES AND BLAST RADIUS                           │
│                                                                             │
│   FAILURE 1: Single Node Crash                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   [Node 1]  [Node 2]  [Node 3]  [Node 4]                            │   │
│   │      ✓         ✗         ✓         ✓                                │   │
│   │                ▲                                                    │   │
│   │                │                                                    │   │
│   │   Blast radius: 25% of keys (those hashed to Node 2)                │   │
│   │   Duration: Seconds (until failover to replica)                     │   │
│   │   Recovery: Counters for Node 2 keys reset to 0                     │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE 2: Config Store Unavailable                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   [Rate Limiter Cluster]                                            │   │
│   │          ▲                                                          │   │
│   │          │ ✗ Cannot reach                                           │   │
│   │          ▼                                                          │   │
│   │   [Config Store] ✗                                                  │   │
│   │                                                                     │   │
│   │   Blast radius: 0% (cached configs still work)                      │   │
│   │   Duration: Hours (cache TTL)                                       │   │
│   │   Impact: New customers can't be added, config changes delayed      │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE 3: Entire Rate Limiter Cluster Down                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   [API Servers]                                                     │   │
│   │        │                                                            │   │
│   │        ▼                                                            │   │
│   │   [Rate Limiter] ✗ ✗ ✗ ✗                                            │   │
│   │                                                                     │   │
│   │   OPTION A (Fail Closed): All requests rejected                     │   │
│   │   → Blast radius: 100%, complete outage                             │   │
│   │                                                                     │   │
│   │   OPTION B (Fail Open): All requests allowed                        │   │
│   │   → Blast radius: 0% (but no protection)                            │   │
│   │   → Risk: Backend overload if traffic spikes                        │   │
│   │                                                                     │   │
│   │   RECOMMENDED: Fail open with local limits from API server cache    │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 4: Evolution Timeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RATE LIMITER EVOLUTION                                   │
│                                                                             │
│   V1: IN-PROCESS (Month 1-3)                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   [API Server 1]  [API Server 2]  [API Server 3]                    │   │
│   │   Local counter   Local counter   Local counter                     │   │
│   │                                                                     │   │
│   │   Problem: No global enforcement                                    │   │
│   │   Customer gets limit × N servers                                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│   V2: CENTRALIZED REDIS (Month 4-9)                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   [API Server 1]  [API Server 2]  [API Server 3]                    │   │
│   │         │               │               │                           │   │
│   │         └───────────────┼───────────────┘                           │   │
│   │                         ▼                                           │   │
│   │                   [Redis Cluster]                                   │   │
│   │                                                                     │   │
│   │   Problem: Redis becomes bottleneck                                 │   │
│   │   Network latency added to every request                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│   V3: DEDICATED CLUSTER (Month 10+)                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   [API Servers] ──► [Rate Limiter Cluster] ──► [Config Store]       │   │
│   │                      (in-memory counters)       (persistent)        │   │
│   │                                                                     │   │
│   │   Benefits: Low latency, high throughput, scalable                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│   V4: MULTI-REGION (Month 18+)                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   US-EAST              EU-WEST              AP-NORTH                │   │
│   │   [RL Cluster]◄──────►[RL Cluster]◄────────►[RL Cluster]            │   │
│   │        ▲                   ▲                    ▲                   │   │
│   │        │                   │                    │                   │   │
│   │   [API Servers]       [API Servers]        [API Servers]            │   │
│   │                                                                     │   │
│   │   Benefits: Low latency globally, regional isolation                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 18: Brainstorming, Exercises & Redesigns

## "What If X Changes?" Questions

1. **What if request volume increases 100x?**
   - Scale rate limiter nodes horizontally
   - Add more shards
   - Consider tiered limiting (different accuracy for different customers)

2. **What if we need sub-millisecond accuracy for limits?**
   - Tighter sync intervals (sub-second)
   - More regional coordination
   - Accept higher infrastructure cost

3. **What if rate limiter needs to run in customer's cloud?**
   - Edge deployment
   - Local-first with cloud sync
   - Eventual consistency by necessity

4. **What if we need to rate limit by content (e.g., image size)?**
   - Weighted requests (large image = 10 units)
   - Content-aware rate limiting
   - Different limits for different resource types

5. **What if malicious actors create millions of API keys?**
   - Per-account (not per-key) limiting
   - Account creation limits
   - Anomaly detection for key creation patterns

## Redesign Exercises

### Exercise 1: Design for 99.999% Availability

```
CONSTRAINT: Rate limiter must be 99.999% available (5 minutes downtime/year)

CURRENT: 99.9% (8 hours downtime/year)

CHANGES NEEDED:
• Multi-region active-active (3 regions minimum)
• Each region independently viable
• Cross-region failover < 30 seconds
• Configuration replicated synchronously

DESIGN:
...

TRADE-OFFS:
• Cost: 3x current (multi-region)
• Accuracy: Lower (regional independence means less coordination)
• Complexity: Higher (more failure modes)
```

### Exercise 2: Design for Strong Consistency

```
CONSTRAINT: Must enforce exact limits globally (financial use case)

CURRENT: Eventual consistency with ~5% over-counting

CHANGES NEEDED:
• Global counter coordination
• Consensus per increment (or batched consensus)
• Accept latency penalty

DESIGN:
...

TRADE-OFFS:
• Latency: 50-200ms per request (cross-region consensus)
• Throughput: Lower (coordination limits)
• Availability: Lower (consensus requires quorum)
```

### Exercise 3: Design for Zero Trust Environment

```
CONSTRAINT: Cannot trust any single component

DESIGN PRINCIPLES:
• Mutual TLS between all components
• Signed rate limit decisions
• Audit log of all decisions
• Multiple rate limiters cross-check each other

TRADE-OFFS:
• Latency: Higher (additional verification)
• Complexity: Much higher
• Cost: 2-3x (redundant systems)
```

## Failure Injection Exercises

### Exercise A: Rate Limiter Node Failure

```
INJECT: Kill one rate limiter node

OBSERVE:
• How quickly is failure detected?
• How does traffic fail over to replica?
• What happens to in-flight requests?
• Do counters reset correctly?

VERIFY:
• No prolonged errors (< 10 seconds)
• Limits still enforced (allow slight over-count during failover)
• No cascading failures
```

### Exercise B: Configuration Store Failure

```
INJECT: Block access to configuration database

OBSERVE:
• How long do cached configs remain valid?
• What happens for new customers (no cached config)?
• How does system behave as caches expire?

VERIFY:
• Existing traffic unaffected (cached configs work)
• New customers get default limits
• Alert fires within 1 minute
```

### Exercise C: Traffic Spike (10x Normal)

```
INJECT: 10x traffic spike (simulate viral event)

OBSERVE:
• Does rate limiter handle the load?
• What's the latency under load?
• Are limits correctly enforced during spike?

VERIFY:
• Latency < 10ms P99 during spike
• Over-limit requests correctly rejected
• Rate limiter doesn't become bottleneck
```

## Trade-off Debates

### Debate 1: Accuracy vs Latency

```
POSITION A: "Accuracy is paramount. Users pay for a specific limit."
• Strong consistency required
• Accept latency penalty
• Users get exactly what they pay for

POSITION B: "Latency is paramount. Rate limiting shouldn't slow down requests."
• Eventual consistency acceptable
• Sub-millisecond latency required
• 5-10% over-counting is acceptable

STAFF RESOLUTION:
For most APIs: Position B (latency wins)
For financial/billing: Position A (accuracy wins)
Offer both tiers if needed
```

### Debate 2: Fail Open vs Fail Closed

```
POSITION A: "Fail closed. Better to block all than allow abuse."
• Rate limiter failure = all requests rejected
• Protects backend absolutely
• Users experience complete outage

POSITION B: "Fail open. Better to allow all than cause outage."
• Rate limiter failure = all requests allowed
• Backend might be overloaded
• Users experience continued service

STAFF RESOLUTION:
Fail open with degraded limits (cached)
• Better than complete outage
• Still provides some protection
• Alert immediately, fix quickly
```

### Debate 3: Centralized vs Embedded

```
POSITION A: "Centralized rate limiting service. Clean separation of concerns."
• Dedicated infrastructure
• Single point of truth
• Network dependency for every request

POSITION B: "Embedded in API servers. Zero network latency."
• No separate service
• Faster checks
• Harder to enforce global limits

STAFF RESOLUTION:
Hybrid approach:
• Embedded for local limits (per-connection, per-request)
• Centralized for global limits (per-customer, per-account)
• Best of both worlds
```

---

# Part 19: Additional Staff-Level Depth (Reviewer Additions)

## Retry Storms Under Rate Limiting

When clients receive 429 (Too Many Requests), poorly behaved clients retry immediately. This creates a dangerous amplification loop.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RETRY STORM AMPLIFICATION                                │
│                                                                             │
│   TIMELINE:                                                                 │
│   T+0:    Customer at 1000/1000 limit                                       │
│   T+1s:   100 new requests arrive, all rejected with 429                    │
│   T+2s:   100 original + 100 retries = 200 requests                         │
│   T+3s:   200 rejected + 200 retries = 400 requests                         │
│   T+4s:   400 rejected + 400 retries = 800 requests                         │
│   T+5s:   Exponential growth, rate limiter overloaded                       │
│                                                                             │
│   PROBLEM: Rejections cause MORE load, not less                             │
│                                                                             │
│   MITIGATION STRATEGIES:                                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. RETRY-AFTER HEADER                                              │   │
│   │     • Include precise retry time in 429 response                    │   │
│   │     • Well-behaved clients respect it                               │   │
│   │     • Poorly-behaved clients still retry immediately                │   │
│   │                                                                     │   │
│   │  2. EXPONENTIAL BACKOFF ENFORCEMENT                                 │   │
│   │     • Track retry attempts per client                               │   │
│   │     • Increase penalty for rapid retries                            │   │
│   │     • 1st rejection: 1s wait, 2nd: 2s, 3rd: 4s...                   │   │
│   │                                                                     │   │
│   │  3. REJECTION RATE LIMITING                                         │   │
│   │     • Rate limit the rejections themselves                          │   │
│   │     • After N rejections/minute, drop packets silently              │   │
│   │     • Reduces amplification at cost of visibility                   │   │
│   │                                                                     │   │
│   │  4. JITTER IN RETRY-AFTER                                           │   │
│   │     • Add randomness to prevent thundering herd                     │   │
│   │     • retry_after = window_reset + random(0, 5s)                    │   │
│   │     • Spreads retries over time                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

```
// Pseudocode: Retry storm mitigation

CLASS RetryStormMitigation:
    rejection_tracker = {}  // client_id -> (count, last_rejection)
    
    FUNCTION handle_rate_limit_exceeded(client_id, window_reset):
        // Track rejection history
        history = rejection_tracker.get(client_id, (0, 0))
        rejections_last_minute = count_recent_rejections(client_id)
        
        // Calculate backoff
        IF rejections_last_minute > 10:
            // Client is hammering us, severe backoff
            backoff = min(60, 2 ^ rejections_last_minute)
            retry_after = now() + backoff + random(0, 5)
        ELSE:
            // Normal backoff with jitter
            retry_after = window_reset + random(0, 2)
        
        // Update tracker
        rejection_tracker[client_id] = (rejections_last_minute + 1, now())
        
        RETURN {
            status: 429,
            headers: {
                "Retry-After": retry_after,
                "X-RateLimit-Reset": window_reset,
                "X-Rejection-Count": rejections_last_minute + 1
            }
        }
```

---

## Slow Dependency Handling: Config Store Latency

The rate limiter depends on configuration (limits, rules). When config store becomes slow, rate limiting latency increases for ALL requests.

```
SCENARIO: Config store P99 latency spikes to 500ms

NAIVE DESIGN:
Every rate limit check fetches config from store
→ All requests now have 500ms+ latency
→ Rate limiter becomes the bottleneck

STAFF DESIGN:
Config cached locally with 5-minute TTL
Config refresh happens asynchronously in background
Hot path NEVER blocks on config store

IMPLEMENTATION:
```

```
// Pseudocode: Async config refresh

CLASS AsyncConfigManager:
    config_cache = {}
    config_ttl = 300  // 5 minutes
    last_refresh = {}
    
    FUNCTION get_config(key):
        // Always return cached value (never block)
        cached = config_cache.get(key)
        
        IF cached != null:
            // Check if refresh needed (async)
            IF now() - last_refresh.get(key, 0) > config_ttl:
                schedule_async_refresh(key)
            RETURN cached
        ELSE:
            // First access: return default, fetch async
            schedule_async_refresh(key)
            RETURN default_config
    
    FUNCTION async_refresh(key):
        // Runs in background, with timeout
        TRY:
            WITH timeout(1 second):
                new_config = config_store.get(key)
                config_cache[key] = new_config
                last_refresh[key] = now()
        CATCH timeout_error:
            // Config store slow, keep using cached value
            log_warning("Config refresh timeout", key)
            // Don't update last_refresh, retry sooner
```

**Key Insight**: The rate limiter hot path must NEVER block on any external dependency. All dependencies are pre-fetched and cached.

---

## Cascading Failure Timeline: Rate Limiter → Protected Service

```
┌─────────────────────────────────────────────────────────────────────────────┐
│           CASCADING FAILURE: RATE LIMITER CAUSES OUTAGE                     │
│                                                                             │
│   INITIAL STATE:                                                            │
│   • Rate limiter cluster: 16 nodes, healthy                                 │
│   • API servers: 50 nodes, healthy                                          │
│   • Database: 3 nodes, healthy                                              │
│                                                                             │
│   T+0:00  Rate limiter node 1 experiences memory leak                       │
│           └─ GC pauses increase, latency spikes to 100ms                    │
│                                                                             │
│   T+0:30  API servers notice rate limit checks taking 100ms                 │
│           └─ Request latency increases by 100ms across the board            │
│           └─ API server thread pools start filling up                       │
│                                                                             │
│   T+1:00  API server connections exhausted waiting for rate limiter         │
│           └─ New requests start timing out                                  │
│           └─ Users see 504 Gateway Timeout                                  │
│                                                                             │
│   T+1:30  Retry storm begins (users refresh, clients retry)                 │
│           └─ Traffic doubles                                                │
│           └─ More rate limiter nodes under pressure                         │
│                                                                             │
│   T+2:00  Rate limiter cluster at 95% capacity                              │
│           └─ All rate limit checks slow                                     │
│           └─ API servers completely blocked                                 │
│                                                                             │
│   T+3:00  Full outage                                                       │
│           └─ Rate limiter (protective system) caused the outage             │
│                                                                             │
│   ROOT CAUSE: Rate limiter latency not bounded, no circuit breaker          │
│                                                                             │
│   CORRECT DESIGN:                                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Rate limit check has strict timeout (5ms)                        │   │
│   │  • On timeout: Fail open with cached result                         │   │
│   │  • Circuit breaker: If >10% timeouts, bypass rate limiter           │   │
│   │  • Rate limiter is OPTIONAL path, not blocking path                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

```
// Pseudocode: Circuit breaker for rate limiter

CLASS RateLimiterClient:
    circuit_breaker = CircuitBreaker(
        failure_threshold = 10,   // 10% failures
        recovery_timeout = 30     // seconds
    )
    timeout = 5  // ms
    
    FUNCTION check_rate_limit(key, limit):
        IF circuit_breaker.is_open():
            // Rate limiter having issues, bypass
            log_metric("rate_limiter_bypassed")
            RETURN ALLOW_DEGRADED
        
        TRY:
            WITH timeout(self.timeout):
                result = rate_limiter.check(key, limit)
                circuit_breaker.record_success()
                RETURN result
        CATCH timeout_error:
            circuit_breaker.record_failure()
            log_warning("Rate limit check timeout")
            RETURN ALLOW_DEGRADED  // Fail open
```

---

## Hot Key Thundering Herd (Celebrity Customer Problem)

When one customer has extremely high traffic, their counter becomes a hot key that overloads a single shard.

```
SCENARIO: Celebrity customer with 1M req/sec (10% of total traffic)

PROBLEM:
• All 1M requests hash to same shard
• Single rate limiter node receives 1M req/sec
• Node capacity: 500K req/sec
• Node overloaded, affects all customers on that shard

SOLUTIONS:

SOLUTION 1: Counter Sharding
Split hot key counter across multiple sub-keys

key = "customer_celebrity"
→ "customer_celebrity:shard_0", "customer_celebrity:shard_1", ...
→ Each request picks random shard
→ Sum shards for total count (approximate)

SOLUTION 2: Local Counting with Aggregation
Count locally per API server
Aggregate periodically (every 100ms)
Hot customer check is always local

SOLUTION 3: Dedicated Hot Key Handler
Detect hot keys automatically
Route to dedicated hot key pool
Higher capacity, more replicas
```

```
// Pseudocode: Hot key detection and handling

CLASS HotKeyHandler:
    key_frequency = {}
    hot_threshold = 10000  // requests per second
    hot_key_pool = HotKeyRateLimiterPool()
    
    FUNCTION route_request(key):
        // Track frequency
        key_frequency[key] = key_frequency.get(key, 0) + 1
        
        // Detect hot key
        IF key_frequency[key] > hot_threshold:
            // Route to dedicated pool
            RETURN hot_key_pool.check_rate_limit(key)
        ELSE:
            // Normal routing
            shard = hash(key) % num_shards
            RETURN normal_pool[shard].check_rate_limit(key)
    
    // Reset frequency counter every second
    FUNCTION reset_frequency():
        key_frequency = {}
```

---

## Counter Overflow at Extreme Scale

At 10M req/sec, 64-bit counters overflow after... well, never practically. But 32-bit counters overflow in ~7 minutes.

```
CALCULATION:
32-bit max: 4,294,967,295
At 10M/sec: Overflow in 429 seconds (~7 minutes)

PROBLEM:
If using 32-bit counters and window is 1 hour:
Counter overflows, wraps to 0
Customer gets unlimited requests

SOLUTION:
• Always use 64-bit counters
• Monitor counter values (alert if approaching 2^63)
• Window-based reset prevents accumulation

EDGE CASE: Counter reset race
Window resets, counter set to 0
Request arrives during reset
Counter might be 0 or 1 depending on timing
→ Not a real problem (off-by-one is acceptable)
```

---

## Zero-Downtime Algorithm Migration

Switching from Fixed Window to Sliding Window requires careful migration.

```
// Pseudocode: Zero-downtime algorithm migration

CLASS AlgorithmMigration:
    
    FUNCTION migrate_to_sliding_window():
        // Phase 1: Shadow mode (1 week)
        // Run both algorithms, compare results, log differences
        FOR request IN incoming_requests:
            fixed_result = fixed_window.check(request)
            sliding_result = sliding_window.check(request)
            
            log_comparison(request, fixed_result, sliding_result)
            
            // Use fixed window for actual decision
            RETURN fixed_result
        
        // Phase 2: Canary (10% traffic, 3 days)
        FOR request IN incoming_requests:
            IF hash(request.key) % 100 < 10:
                // 10% uses new algorithm
                RETURN sliding_window.check(request)
            ELSE:
                RETURN fixed_window.check(request)
        
        // Phase 3: Gradual rollout (10% → 25% → 50% → 100%)
        // Monitor: Rejection rates, customer complaints, error rates
        
        // Phase 4: Cleanup
        // Remove fixed window code
        // Archive migration logs

ROLLBACK TRIGGER:
• Rejection rate increases >5%
• Customer complaints spike
• P99 latency increases >2x
• Any production incident
```

---

## On-Call Runbook Essentials

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RATE LIMITER ON-CALL RUNBOOK                             │
│                                                                             │
│   ALERT: Rate Limiter Latency High                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Check: Is one node slow or all nodes?                           │   │
│   │     → One node: Restart that node                                   │   │
│   │     → All nodes: Check config store, check network                  │   │
│   │                                                                     │   │
│   │  2. Check: Memory usage per node                                    │   │
│   │     → High memory: Force GC or restart                              │   │
│   │     → Normal: Check CPU, check counter store                        │   │
│   │                                                                     │   │
│   │  3. Immediate mitigation: Enable circuit breaker bypass             │   │
│   │     → Customers get unlimited access temporarily                    │   │
│   │     → Better than complete outage                                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ALERT: Customer Complaints About Rate Limiting                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Verify: Check customer's actual usage vs limit                  │   │
│   │     → Usage < limit: Bug in rate limiter, escalate                  │   │
│   │     → Usage ≥ limit: Customer needs limit increase                  │   │
│   │                                                                     │   │
│   │  2. If legitimate increase needed:                                  │   │
│   │     → Check with account team (is customer paying for more?)        │   │
│   │     → Temporary override: 24-hour 2x limit                          │   │
│   │     → Permanent: Update config after approval                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ALERT: Rate Limiter Node Down                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Verify: Is failover working?                                    │   │
│   │     → Check replica health                                          │   │
│   │     → Check error rates for affected shards                         │   │
│   │                                                                     │   │
│   │  2. If failover working: Low urgency, investigate root cause        │   │
│   │     If failover NOT working: High urgency, manual intervention      │   │
│   │                                                                     │   │
│   │  3. Root cause investigation (next business day if failover worked) │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   EMERGENCY: Complete Rate Limiter Outage                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. IMMEDIATELY: Enable bypass mode in API servers                  │   │
│   │     → All requests allowed (no rate limiting)                       │   │
│   │     → Protects user experience                                      │   │
│   │                                                                     │   │
│   │  2. Alert backend teams: Potential traffic spike incoming           │   │
│   │                                                                     │   │
│   │  3. Investigate rate limiter cluster                                │   │
│   │                                                                     │   │
│   │  4. When fixed: Gradually re-enable rate limiting (10% → 100%)      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Production Testing with Canary Limits

```
// Pseudocode: Canary limit testing

CLASS CanaryLimitTester:
    
    FUNCTION test_new_limit(customer_id, new_limit):
        // Don't apply new limit directly
        // Test with shadow traffic first
        
        current_limit = get_current_limit(customer_id)
        
        // Phase 1: Shadow comparison (7 days)
        FUNCTION shadow_check(request):
            current_result = check_against(request, current_limit)
            new_result = check_against(request, new_limit)
            
            log_comparison(customer_id, current_result, new_result)
            
            // Always use current limit
            RETURN current_result
        
        // After 7 days, analyze:
        // - How many requests would be affected?
        // - What's the distribution of affected requests?
        // - Any unexpected patterns?
        
        // Phase 2: Gradual rollout
        // 10% of customer's requests use new limit
        // Monitor for complaints
        
        // Phase 3: Full rollout
        // Apply new limit to all requests
        
    FUNCTION analyze_shadow_results(customer_id):
        results = get_shadow_logs(customer_id, last_7_days)
        
        would_be_rejected = count(r for r in results 
                                   if r.current == ALLOW and r.new == REJECT)
        
        rejection_rate = would_be_rejected / len(results)
        
        IF rejection_rate > 0.05:
            alert("New limit would reject >5% of traffic", customer_id)
            RETURN NEEDS_REVIEW
        
        RETURN SAFE_TO_PROCEED
```

---

## Google L6 Interview Follow-Ups This Design Must Survive

### Follow-Up 1: "What happens if a customer's API key is compromised and used for abuse?"

**Design Answer:**
- Rate limiting still protects backend (abuse limited to customer's quota)
- Audit logs capture abuse pattern for forensics
- Emergency key revocation stops abuse immediately
- Customer's other keys unaffected (per-key, not per-account for this scenario)

### Follow-Up 2: "How do you handle a DDoS attack that targets the rate limiter itself?"

**Design Answer:**
- Rate limiter has its own rate limiting (meta-rate-limiting)
- Load shedding drops packets before rate limit check
- Anycast distributes attack across regions
- Fail open means attack can't cause complete outage (just bypasses limiting temporarily)

### Follow-Up 3: "A customer claims they're being incorrectly rate limited. How do you debug?"

**Design Answer:**
- Check audit logs for actual request counts vs limit
- Compare counter values across all shards/replicas
- Check for clock skew issues at window boundaries
- Verify config propagation (is old limit cached somewhere?)
- Check for hot key issues if customer is high-volume

### Follow-Up 4: "How would you handle rate limits that need to be different for the same customer based on request context?"

**Design Answer:**
- Hierarchical rate limiting: Global → Per-endpoint → Per-operation
- Rate limit key includes context: `customer_123:/api/search:POST`
- Limits can be nested: Customer has 10K/min overall, but only 100/min for expensive operations
- First check that fails determines outcome

### Follow-Up 5: "What's your strategy if you need to reduce a customer's limit during an incident?"

**Design Answer:**
- Emergency limit override with immediate propagation (push, not pull)
- Cached configs invalidated immediately (broadcast invalidation)
- Rate limiter nodes confirm receipt of new limit
- Audit trail of who changed what, when, why
- Automatic revert after incident (time-bounded override)

---

# Quick Reference

## Mental Models & One-Liners

| Model | One-Liner |
|-------|-----------|
| **Staff First Law** | A rate limiter that is perfectly accurate but adds 50ms of latency has failed. Protection, not precision. |
| **Bouncer analogy** | Count people entering, turn away at capacity. Multiple doors = coordination. Sick bouncer = fail open, not closed. |
| **Accuracy asymmetry** | Over-counting (reject extra) is safe. Under-counting (allow abuse) is dangerous. When uncertain, over-count. |
| **Simplicity** | The rate limiter must be simpler than the system it protects. If it's a complex distributed system, you've moved the problem. |
| **Hot path** | Rate limit check must never block on any external dependency. All config, all sync: async and cached. |
| **Failure design** | Rate limiter failure should not cause outage. Fail open with degraded limits. Circuit breaker on the caller. |

## Algorithm Selection

| Algorithm | Use When | Avoid When |
|-----------|----------|------------|
| Fixed Window | Simple needs, OK with boundary burst | Need smooth limiting |
| Sliding Window Counter | Most API rate limiting | Need perfect accuracy |
| Token Bucket | Need to allow controlled bursts | Need simple implementation |
| Sliding Log | Low rate limits only | High limits (memory explosion) |

## Consistency vs Latency

| Requirement | Consistency | Sync Interval | Accuracy |
|-------------|-------------|---------------|----------|
| Most APIs | Eventual | 5 seconds | ~95% |
| Financial | Strong | Per-request | 100% |
| High-volume | Eventual | 10 seconds | ~90% |

## Failure Modes

| Failure | Detection | Mitigation | Blast Radius |
|---------|-----------|------------|--------------|
| Node crash | Health check | Failover to replica | 1/N keys |
| Config store down | Connection error | Use cached config | Config updates only |
| Cluster overload | Latency spike | Load shedding | All requests delayed |
| Network partition | Connectivity check | Regional independence | Accuracy degradation |

---

# Master Review Check

Before considering this chapter complete, verify:

- [ ] **Judgment** — Trade-offs (accuracy vs latency, fail open vs closed) are explicitly articulated and defended.
- [ ] **Failure/blast radius** — Failure modes enumerated with blast radius; Real Incident table present.
- [ ] **Scale/time** — Load model and QPS analysis; bottlenecks and dangerous assumptions documented.
- [ ] **Cost** — Major cost drivers, scaling behavior, and over-engineering pitfalls covered.
- [ ] **Real-world ops** — On-call runbook, degradation levels, and failure injection exercises.
- [ ] **Memorability** — Mental models and one-liners (e.g., Staff First Law, bouncer analogy) present.
- [ ] **Data/consistency** — Strong vs eventual consistency; when to choose each.
- [ ] **Security/compliance** — Abuse vectors, data exposure, privilege boundaries.
- [ ] **Observability** — SLIs, SLOs, dashboards, alerting strategy.
- [ ] **Cross-team** — Ownership, dependencies, who configures and who gets paged.
- [ ] **Interview calibration** — Probes, Staff signals, common Senior mistake, how to teach, leadership explanation.

## L6 Dimension Coverage (A–J)

| Dim | Name | Coverage |
|-----|------|----------|
| **A** | Judgment | L5 vs L6 table, Staff-level answers, trade-off debates; when approximate beats exact. |
| **B** | Failure/blast radius | Part 9 failure modes; Real Incident table; cascading failure timeline; blast radius per failure. |
| **C** | Scale/time | Part 4 scale & load; QPS, storage, bottlenecks; dangerous assumptions; 10M req/sec target. |
| **D** | Cost | Part 11 cost breakdown; scaling analysis; reliability tiers; over-engineering examples. |
| **E** | Real-world ops | On-call runbook; failure injection; evolution timeline; production canary testing. |
| **F** | Memorability | Staff First Law; bouncer analogy; one-liners; algorithm selection guide. |
| **G** | Data/consistency | Part 8 strong vs eventual; over-count vs under-count; race conditions; clock assumptions. |
| **H** | Security/compliance | Part 13 abuse vectors; data exposure; privilege boundaries; audit trail. |
| **I** | Observability | Part 13b SLIs/SLOs; dashboards; alerting; audit trail for forensics. |
| **J** | Cross-team | Interview Calibration cross-team signal; who configures limits; product vs infra. |

---

# Conclusion

Rate limiting is a fascinating case study in trade-offs. The concept is simple—count requests and reject excess—but the implementation at scale requires navigating fundamental tensions between accuracy and latency, consistency and availability, simplicity and resilience.

The key insights for Staff Engineers:

**Rate limiting is about protection, not precision.** A rate limiter that adds 50ms to every request has failed. Accept approximations that reduce complexity.

**Design for failure.** Rate limiter failure should not cause system outage. Fail open with degraded limits.

**Regional independence beats global coordination.** Accept eventual consistency for sub-millisecond latency.

**Start simple.** Sliding window counters solve 90% of rate limiting needs. Add complexity only when required.

**Accuracy asymmetry.** Over-counting (rejecting extra requests) is safe. Under-counting (allowing abuse) is dangerous. Design to over-count when uncertain.

Rate limiting is a critical piece of infrastructure that, when done well, is invisible to users and invaluable to operations.

---

*End of Chapter 41: Global Rate Limiter*

*Next: Chapter 42 — Distributed Cache*
