# Chapter 54. API Gateway / Edge Request Routing System

---

# Introduction

The API Gateway is the front door of every large-scale distributed system. I've spent years building and operating edge infrastructure at Google, and I'll be direct: the hardest part isn't routing requests to backend services—any reverse proxy can do that. The hard part is doing it at 5 million requests per second with sub-millisecond overhead, making routing decisions that adapt in real-time to backend health, enforcing authentication and rate limiting before a single byte touches your application servers, and surviving a DDoS attack that sends 100× your normal traffic—all without becoming the single point of failure for your entire platform.

This chapter covers the design of an API Gateway and edge request routing system at Staff Engineer depth: with deep understanding of the hot-path decisions that define P99 latency, awareness of the failure modes that turn your gateway from protector into bottleneck, and judgment about where intelligence should live at the edge versus in the application.

**The Staff Engineer's First Law of API Gateways**: The gateway is on the critical path of EVERY request. Every microsecond of gateway overhead is multiplied by every request across every service. A 1ms regression in the gateway is a 1ms regression for your entire platform. Treat gateway performance with the same rigor as database performance.

---

## Quick Visual: API Gateway / Edge Request Routing at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│     API GATEWAY: THE STAFF ENGINEER VIEW                                    │
│                                                                             │
│   WRONG Framing: "A reverse proxy that routes requests to services"         │
│   RIGHT Framing: "The critical-path infrastructure that enforces security,  │
│                   manages traffic, absorbs failures, and provides a         │
│                   stable API surface—all at sub-millisecond overhead        │
│                   for millions of requests per second"                      │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Before designing, understand:                                      │   │
│   │                                                                     │   │
│   │  1. What is the P99 latency budget for the gateway itself? (<5ms)   │   │
│   │  2. How many distinct backend services does it route to? (10? 500?) │   │
│   │  3. Who defines routing rules: platform team only, or every team?   │   │
│   │  4. What protocols must be supported? (HTTP/1.1, HTTP/2, gRPC, WS)  │   │
│   │  5. Is the gateway the authentication boundary?                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   THE UNCOMFORTABLE TRUTH:                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  The API gateway is simultaneously the most critical component      │   │
│   │  (on the path of every request) and the most constrained            │   │
│   │  (must add minimal latency). Every feature you add to the gateway   │   │
│   │  (auth, rate limiting, transformation, logging) competes for the    │   │
│   │  same microsecond budget. The Staff Engineer's job is deciding      │   │
│   │  what belongs at the edge and what belongs in the application.      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 API Gateway Decisions

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Routing** | "Configure nginx or Envoy with static routing rules" | "Route config is version-controlled, validated, and deployed as data—not code. Routing changes propagate in seconds via config push. Routing decisions incorporate real-time backend health, weighted traffic splitting for canaries, and header-based routing for A/B tests. Routing loops and conflicting rules are caught at validation time, not at runtime." |
| **Rate limiting** | "Use a token bucket per IP" | "Layered rate limiting: global (protect infrastructure), per-service (protect backends), per-user (prevent abuse), per-API (enforce quotas). Distributed counters with local approximation—exact counting requires consensus on every request, which is a latency killer. Accept 5-10% over-admission rather than adding distributed lock overhead." |
| **Authentication** | "Verify JWT token, forward to backend" | "Terminate TLS at edge, verify token, extract identity, attach verified identity header, strip the raw token before forwarding. Backend services NEVER see raw credentials—only verified identity claims. Token verification uses cached public keys with background refresh, not per-request key fetch." |
| **Failure handling** | "Return 502 if backend is down" | "Circuit breaker per backend, with health-based routing. If backend A is slow, shed load proactively BEFORE it fails completely. Return cached response if available. Return degraded response (partial data) if possible. 502 is the LAST resort, not the first response." |
| **Observability** | "Log each request to a file" | "Structured access log with request ID, timing breakdown (TLS, auth, routing, backend, total), response size, client identity, and backend instance. Propagate distributed trace context. Emit latency histograms per route, per backend, per status code. The gateway IS your first line of production visibility." |

**Key Difference**: L6 engineers recognize that the API gateway is not just a router—it's a policy enforcement point, a traffic management layer, a failure isolation boundary, and the primary source of cross-cutting observability. Every decision trades off between capability and latency, between safety and throughput.

## Staff One-Liners & Mental Models

| Concept | One-Liner | Use When |
|---------|-----------|----------|
| Latency budget | "Every microsecond on the gateway is multiplied by every request. A 1ms regression is a 1ms regression for the entire platform." | Explaining gateway overhead constraints |
| Hot path | "Nothing external on the hot path. Auth, rate limit, routing—all local, all in-process." | Defending against Redis/cache on every request |
| Failure isolation | "Per-backend connection pools. A slow order-service cannot affect search-service through the gateway." | Justifying architectural choices |
| Scope discipline | "The gateway does NOT aggregate responses. That's a BFF. It does NOT serve static assets. That's a CDN." | Pushing back on feature creep |
| Config safety | "Config changes cause more outages than code bugs. Validate, canary, auto-rollback." | Justifying config deployment rigor |
| Rate limiting | "±10% accuracy for 0ms latency. Users never notice 5% over-admission; they notice 2ms added latency." | Defending local-counters-with-sync |
| Cert expiry | "Automated renewal must be monitored. Automated systems fail silently." | Post-incident / preventive design |
| Circuit breaker | "Slow backends are worse than dead backends. Dead fails fast; slow exhausts resources silently." | Explaining latency-based breakers |

---

# Part 1: Foundations — What an API Gateway Is and Why It Exists

## What Is an API Gateway?

An API Gateway is a server (or fleet of servers) that sits between clients and backend services, acting as the single entry point for all external (and often internal) API traffic. It receives every incoming request, applies cross-cutting concerns (authentication, rate limiting, logging), determines which backend service should handle the request, forwards it, and returns the response to the client.

### The Simplest Mental Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE SIMPLEST MENTAL MODEL                                │
│                                                                             │
│   Without API Gateway:                                                      │
│                                                                             │
│   Client ──── auth check ──── Service A                                     │
│   Client ──── auth check ──── Service B                                     │
│   Client ──── auth check ──── Service C                                     │
│   Client ──── auth check ──── Service D                                     │
│                                                                             │
│   Every service implements auth, rate limiting, logging, TLS.               │
│   Every service is exposed to the internet directly.                        │
│   Every service must handle DDoS traffic.                                   │
│                                                                             │
│   With API Gateway:                                                         │
│                                                                             │
│   Client ──── API Gateway ──┬──── Service A                                 │
│                             ├──── Service B                                 │
│                             ├──── Service C                                 │
│                             └──── Service D                                 │
│                                                                             │
│   Gateway handles: TLS, auth, rate limiting, routing, logging               │
│   Services handle: Business logic only                                      │
│   Only the gateway is exposed to the internet.                              │
│                                                                             │
│   Think of it like a building's front desk:                                 │
│   Visitors check in at the desk (gateway), get a badge (identity),          │
│   and are directed to the right floor (routing). Individual offices         │
│   (services) don't need their own receptionists.                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### What the Gateway Does on Every Request

```
FOR each incoming request:

  1. TLS TERMINATION
     Decrypt the HTTPS connection → Now working with plaintext HTTP
     Cost: ~0.5ms for TLS handshake (amortized across connection)

  2. REQUEST PARSING
     Parse HTTP method, path, headers, query parameters
     Cost: ~10µs

  3. AUTHENTICATION
     Verify JWT/OAuth token → Extract user identity
     Cost: ~50µs (local verification with cached public key)

  4. RATE LIMITING
     Check: Has this user/IP exceeded their quota?
     Cost: ~20µs (local counter with periodic sync)

  5. ROUTING DECISION
     Match request path + method to backend service
     /api/v2/users/* → user-service
     /api/v2/orders/* → order-service
     Cost: ~5µs (compiled routing table)

  6. REQUEST TRANSFORMATION
     Add headers: X-Request-ID, X-User-ID, X-Forwarded-For
     Remove headers: Authorization (strip raw token after verification)
     Cost: ~5µs

  7. LOAD BALANCING
     Choose a specific backend instance (least-connections, weighted round-robin)
     Cost: ~2µs

  8. FORWARD REQUEST TO BACKEND
     Send request to chosen backend instance
     Cost: Network RTT + backend processing time

  9. RESPONSE HANDLING
     Receive response from backend
     Optional: Cache response, transform response, compress
     Cost: ~10µs

  10. ACCESS LOGGING & METRICS
      Log: request_id, path, status, latency, user_id, backend
      Emit: latency histogram, error counter, throughput gauge
      Cost: ~5µs (async, non-blocking)

  TOTAL GATEWAY OVERHEAD: ~100µs (excluding backend time and TLS handshake)
  This is the budget. Every feature added to the gateway competes for this.
```

## Why an API Gateway Exists

### 1. Centralized Cross-Cutting Concerns

```
WITHOUT GATEWAY (every service implements independently):
  Service A: auth middleware v2.3, rate limiter v1.1, logger v3.0
  Service B: auth middleware v2.1, rate limiter v1.0, logger v2.5
  Service C: auth middleware v2.3, rate limiter v1.1, logger v3.0
  Service D: custom auth, no rate limiter, custom logger
  
  PROBLEMS:
  → Auth behavior differs between services (version skew)
  → Rate limiting doesn't protect the overall system (per-service, not per-user)
  → Log formats differ → Hard to aggregate and analyze
  → Service D is a security hole (custom auth is buggy)
  → Updating auth library requires deploying 4+ services
  
WITH GATEWAY (centralized enforcement):
  Gateway: auth v2.3, rate limiter v1.1, logger v3.0
  Service A: business logic only
  Service B: business logic only
  Service C: business logic only
  Service D: business logic only
  
  → Auth is consistent: One implementation, one update point
  → Rate limiting is global: Per-user across all services
  → Logging is uniform: Same format, same fields, same pipeline
  → Service D can't skip auth: Gateway enforces before routing
  → Auth update: Deploy gateway only, not every service
```

### 2. API Surface Stability

```
PROBLEM: Backend services evolve independently.
  user-service moves from /users to /accounts
  order-service splits into order-write-service and order-read-service
  payment-service changes from REST to gRPC

  Without gateway: Every client must update for every backend change.
  → Mobile app update takes 6 weeks (App Store review)
  → Old clients break when backend changes
  → API versioning hell: /v1, /v2, /v3, /v4...

  With gateway: Clients talk to a STABLE API surface.
  /api/v2/users → user-service./accounts (gateway rewrites path)
  /api/v2/orders → order-read-service (gateway routes to new service)
  /api/v2/payments → gRPC translation (gateway converts HTTP to gRPC)
  
  Clients never know about backend reorganization.
  This is the API FACADE pattern at infrastructure level.
```

### 3. Security Boundary

```
WITHOUT GATEWAY:
  Every backend service is internet-facing.
  Every service must handle:
  → TLS termination (certificate management per service)
  → DDoS traffic (attack surface is N services)
  → Malformed requests (each service parses independently)
  → IP blocklisting (replicated across every service)
  
WITH GATEWAY:
  Only the gateway is internet-facing.
  Backend services live in a private network.
  Attack surface: 1 component instead of N.
  The gateway is hardened: battle-tested, audited, purpose-built for abuse.
  Backend services trust gateway-forwarded headers (verified identity).
  
  Staff insight: The security benefit of reducing internet-facing
  surface area from N services to 1 gateway is enormous. Every
  internet-facing service is an attack vector. The gateway concentrates
  that attack surface into one well-defended point.
```

### 4. Traffic Management

```
USE CASE: Canary deployment of order-service v2.5
  
  Without gateway:
  → Deploy v2.5 to a subset of servers
  → DNS or load balancer splits traffic (coarse-grained)
  → No per-user or per-header routing
  → Hard to observe canary health independently
  
  With gateway:
  → Route rule: "Send 5% of traffic to order-service-v2.5"
  → Can target: "Only users in US-East, with header X-Canary: true"
  → Real-time metrics: Compare canary vs control error rates
  → Instant rollback: Change route weight to 0%
  
  The gateway is the CONTROL PLANE for live traffic management.
```

## What Happens If an API Gateway Does NOT Exist (or Fails)

```
SCENARIO 1: No gateway at all (services directly exposed)
  
  Impact:
  → Each service team implements auth, rate limiting, logging independently
  → Inconsistent security posture across services
  → No centralized traffic control (can't do canary, A/B, or traffic shifting)
  → DDoS attacks hit all services simultaneously
  → API surface changes with every backend refactor
  → Client engineers must know about internal service topology
  
  Consequence at scale (500 services):
  → 500 different auth implementations to audit
  → 500 different rate limiters to configure
  → 500 different log formats to parse
  → Zero ability to quickly shed traffic during an incident

SCENARIO 2: Gateway exists but fails
  
  Impact:
  → ALL external traffic is blocked (gateway is the single entry point)
  → 100% external availability failure
  → Internal service-to-service traffic (if not routed through gateway): unaffected
  → Revenue impact: Immediate and total for any user-facing system
  
  Mitigation:
  → Gateway fleet must be multi-AZ, multi-instance (N+2 redundancy)
  → Health checks with instant failover
  → Graceful degradation: If auth is slow, consider pass-through with logging
  → Never a single gateway instance in production

SCENARIO 3: Gateway becomes a bottleneck
  
  Impact:
  → P99 latency spikes for ALL services simultaneously
  → Every team sees their dashboards degrade at the same time
  → Root cause is hard to identify (looks like "everything is slow")
  → Engineers investigate their own services, wasting hours
  
  Staff insight: Gateway-caused latency is the MOST expensive kind of
  performance regression because it affects every service simultaneously.
  A 2ms gateway regression × 5M QPS = 10,000 seconds of wasted user time
  per second. Gateway performance monitoring must be the most sensitive
  alerting in the system.
```

---

# Part 2: Functional Requirements

## Core Use Cases

### 1. Request Routing

```
REQUIREMENT: Route incoming requests to the correct backend service
based on request attributes.

ROUTING DIMENSIONS:
  Path-based:    /api/v2/users/*      → user-service
  Method-based:  POST /api/v2/orders  → order-write-service
                 GET /api/v2/orders   → order-read-service
  Header-based:  X-API-Version: 3     → user-service-v3
  Host-based:    api.example.com      → production fleet
                 staging.example.com  → staging fleet
  Weight-based:  90% → service-v1, 10% → service-v2 (canary)
  User-based:    user_id % 100 < 5    → experiment-service

ROUTING RULE SYNTAX:
  route:
    match:
      path_prefix: "/api/v2/users"
      method: "GET"
      headers:
        X-Region: "us-east"
    action:
      backend: "user-service"
      weight: 100
      timeout: 5s
      retry: {max: 2, on: [502, 503]}

RULE PRIORITY:
  More specific rules match first.
  /api/v2/users/123 takes priority over /api/v2/users/*
  Header-matching rules take priority over path-only rules.
  
  CONFLICT DETECTION:
  Two rules matching the same request → REJECTED at configuration time.
  Not resolved at runtime. Configuration must be unambiguous.

STAFF REQUIREMENT:
  Routing changes must be deployable WITHOUT gateway restart.
  Route config is loaded dynamically (pushed or polled from config store).
  A routing change should take effect in < 10 seconds.
```

### 2. Authentication and Authorization

```
REQUIREMENT: Verify caller identity and enforce access policies
before requests reach backend services.

AUTHENTICATION METHODS:
  1. JWT/OAuth2 tokens (most common for user-facing APIs)
     → Verify signature with cached public key
     → Extract claims: user_id, scopes, expiry
     → Reject expired tokens
  
  2. API keys (for machine-to-machine / third-party integrations)
     → Lookup key in local cache (backed by key store)
     → Map key to: owner, rate limit tier, allowed endpoints
  
  3. mTLS (for internal service-to-service)
     → Verify client certificate
     → Extract service identity from certificate CN/SAN

AUTHORIZATION:
  Gateway handles COARSE authorization:
  → "Does this user have access to the /admin endpoint?"
  → "Does this API key have scope 'orders:read'?"
  
  Fine-grained authorization stays in the backend:
  → "Can this user see THIS specific order?"
  → "Is this user the owner of THIS resource?"
  
  WHY: The gateway doesn't have domain-specific data (e.g., order ownership).
  Moving all authorization to the gateway would require it to query every
  backend's data → adds latency, creates coupling.

IDENTITY PROPAGATION:
  After authentication, gateway attaches VERIFIED identity headers:
  X-User-ID: "user_12345"
  X-User-Scopes: "orders:read,orders:write"
  X-Auth-Method: "jwt"
  X-Request-ID: "req_abc123"
  
  Gateway STRIPS the original Authorization header before forwarding.
  → Backend never sees raw credentials
  → Backend trusts gateway-injected headers (internal network is trusted)
  → If backend needs to make downstream calls, it uses its OWN service identity
```

### 3. Rate Limiting and Throttling

```
REQUIREMENT: Protect backend services from traffic spikes,
abuse, and quota enforcement.

RATE LIMIT LAYERS:
  Layer 1: GLOBAL (infrastructure protection)
    Max 10M requests/second across all clients
    Purpose: Prevent infrastructure from collapsing under DDoS
    
  Layer 2: PER-SERVICE (backend protection)
    user-service: Max 100K requests/second
    order-service: Max 50K requests/second
    Purpose: Prevent one popular API from starving others
    
  Layer 3: PER-USER (abuse prevention)
    Free tier: 100 requests/minute
    Paid tier: 10,000 requests/minute
    Enterprise: 100,000 requests/minute
    Purpose: Enforce API quotas per customer
    
  Layer 4: PER-ENDPOINT (expensive operation protection)
    POST /api/v2/orders: Max 10/second per user
    GET /api/v2/search: Max 100/second per user
    Purpose: Protect expensive endpoints separately

RATE LIMIT ALGORITHM: TOKEN BUCKET (per-user, per-endpoint)
  Bucket capacity: quota_limit
  Refill rate: quota_limit / window_seconds
  
  FUNCTION check_rate_limit(user_id, endpoint):
    bucket = get_or_create_bucket(user_id, endpoint)
    IF bucket.tokens > 0:
      bucket.tokens -= 1
      RETURN ALLOW
    ELSE:
      RETURN DENY (429 Too Many Requests)
      HEADER: Retry-After: {seconds_until_refill}
      HEADER: X-RateLimit-Remaining: 0
      HEADER: X-RateLimit-Reset: {reset_timestamp}

DISTRIBUTED RATE LIMITING:
  Gateway runs on 50+ instances. Rate limits must be roughly global.
  
  Option A: Central counter (Redis)
    + Exact counts
    - 1-2ms latency per request (Redis round-trip)
    - Redis is on the hot path → Redis failure = rate limiting failure
    REJECTED for hot-path enforcement
    
  Option B: Local counters with periodic sync
    + Zero latency overhead (local memory lookup)
    - Approximate: Can over-admit by ~5-10% during sync interval
    - Sync interval: Every 1 second → 50 instances × 1 sync/s = 50 syncs/s
    CHOSEN for hot-path enforcement
    
  Option C: Hybrid
    Local counters for ALLOW decisions (fast path)
    Central counter for DENY decisions (verify before rejecting)
    This avoids false rejections (which are worse than over-admission)
```

### 4. TLS Termination

```
REQUIREMENT: Terminate TLS at the gateway edge. Backend traffic
travels over internal network in plaintext or internal mTLS.

WHY TERMINATE AT GATEWAY:
  → Centralized certificate management (one set of certs, not per-service)
  → TLS handshake is CPU-expensive; do it once at the edge
  → Enables request inspection (routing, auth, logging require plaintext)
  → Backend services don't need individual TLS configuration
  
  EXCEPTION: If compliance requires end-to-end encryption (e.g., PCI DSS),
  gateway does TLS termination + re-encryption to backend (TLS bridging).
  This doubles TLS overhead but satisfies "encrypted at all times" requirement.

CERTIFICATE MANAGEMENT:
  Automated certificate rotation via ACME (Let's Encrypt) or internal PKI.
  Certificate loaded into gateway memory, swapped on renewal.
  No gateway restart needed for certificate rotation.
  
  Multiple certificates: SNI (Server Name Indication) selects certificate
  based on requested hostname → One gateway fleet serves multiple domains.
```

### 5. Load Balancing

```
REQUIREMENT: Distribute requests across backend service instances
based on health, capacity, and affinity.

ALGORITHMS:
  1. WEIGHTED ROUND-ROBIN (default)
     Instances with higher weight get proportionally more traffic.
     Use case: Canary deployment (canary has weight 5, production has weight 95)
  
  2. LEAST CONNECTIONS
     Route to the instance with fewest active connections.
     Use case: Long-lived connections (WebSocket, gRPC streaming)
  
  3. CONSISTENT HASHING (per-user affinity)
     Hash(user_id) determines backend instance.
     Use case: Session affinity, user-partitioned caches
     Downside: Uneven distribution if user activity varies
  
  4. POWER OF TWO RANDOM CHOICES (P2C)
     Pick 2 random instances, route to the one with lower load.
     Use case: High-throughput with heterogeneous backends
     
     FUNCTION p2c_select(instances):
       a = random_choice(instances)
       b = random_choice(instances)
       RETURN min_by_active_requests(a, b)
     
     Staff insight: P2C achieves near-optimal load distribution with
     O(1) selection time. It's used in Envoy and Google's internal
     load balancer because it handles heterogeneous backends gracefully.

HEALTH CHECKING:
  Active: Gateway sends health probe every 5 seconds to each backend
  Passive: Gateway tracks error rate per backend instance
  
  FUNCTION update_instance_health(instance, response):
    IF response.status >= 500 OR response.timed_out:
      instance.consecutive_failures += 1
      IF instance.consecutive_failures >= 3:
        instance.mark_unhealthy()
        remove_from_load_balancer(instance)
    ELSE:
      instance.consecutive_failures = 0
      IF instance.is_unhealthy:
        instance.mark_healthy()
        add_to_load_balancer(instance)
```

## Read Paths

```
READ PATH 1: Standard API request
  Client → TLS → Auth → Rate limit → Route → Backend → Response → Client
  Frequency: 5,000,000/second
  Latency budget: < 5ms gateway overhead

READ PATH 2: Cached response
  Client → TLS → Auth → Rate limit → Route → Cache HIT → Response → Client
  Frequency: ~500,000/second (10% cache hit rate)
  Latency budget: < 2ms gateway overhead (no backend call)

READ PATH 3: Health check probe
  Load balancer → Gateway /healthz → 200 OK
  Frequency: ~100/second (every LB checks every 5s)
  Latency budget: < 1ms
```

## Write Paths

```
WRITE PATH 1: Routing configuration update
  Admin → Config API → Validate → Store → Push to gateways
  Frequency: ~10/day
  Latency budget: < 10 seconds from submit to active on all gateways

WRITE PATH 2: Rate limit configuration update
  Admin → Config API → Validate → Store → Push to gateways
  Frequency: ~5/day
  Latency budget: < 10 seconds

WRITE PATH 3: Certificate rotation
  ACME/PKI → Cert store → Push to gateways → Hot-swap in TLS listener
  Frequency: ~1/month (90-day certs, renewed at 60 days)
  Latency budget: < 60 seconds
```

## Control / Admin Paths

```
CONTROL 1: Traffic weight adjustment (canary / blue-green)
  Admin UI → Set route weight: service-v2 = 10%
  Must take effect in < 10 seconds
  Must be audited: who changed, when, why

CONTROL 2: Emergency traffic drain
  Admin UI → Set service to weight 0 (drain all traffic)
  Must take effect in < 5 seconds
  Existing in-flight requests complete (graceful drain)

CONTROL 3: IP / client blocklisting
  Security → Add IP/client to blocklist
  Must take effect in < 5 seconds
  Must be reversible (remove from blocklist)

CONTROL 4: Circuit breaker override
  SRE → Manually open circuit breaker for a backend
  Immediately stops sending traffic to that backend
  Returns 503 or cached/degraded response

CONTROL 5: Rate limit override
  SRE → Temporarily increase/decrease rate limits during incident
  Must not require gateway restart
```

## Edge Cases

```
EDGE CASE 1: Request routing ambiguity
  /api/v2/users/123/orders → user-service or order-service?
  Resolution: Most-specific-path-wins rule applied at config validation time.
  If ambiguous: Reject configuration, require explicit priority.

EDGE CASE 2: Backend returns before gateway finishes sending request body
  Large file upload: Backend rejects with 413 (too large) before upload completes.
  Gateway must stop reading client body, forward 413, and close cleanly.
  Not all HTTP libraries handle this correctly (half-closed connections).

EDGE CASE 3: Client disconnects mid-request
  Client sends request, disconnects before response.
  Gateway should still log the request (for audit/billing).
  Backend request may or may not be cancelled depending on policy:
  → Idempotent GET: Cancel (save backend resources)
  → Non-idempotent POST: Let complete (avoid partial side effects)

EDGE CASE 4: Backend response exceeds size limit
  Backend returns 500MB response (bug or misconfiguration).
  Gateway enforces max response size (e.g., 10MB).
  Returns 502 to client: "Backend response too large"
  Logs the oversized response for debugging.

EDGE CASE 5: WebSocket upgrade
  Client sends HTTP Upgrade to WebSocket.
  Gateway must: Authenticate, apply rate limit, then PASS-THROUGH.
  Gateway becomes a transparent TCP proxy for the WebSocket connection.
  Gateway maintains connection-level (not request-level) metrics.

EDGE CASE 6: gRPC request routing
  gRPC uses HTTP/2 with binary protobuf payloads.
  Gateway routes on the gRPC service + method (from HTTP/2 path).
  Gateway cannot inspect protobuf body (opaque binary).
  Rate limiting on gRPC: Per-method, not per-path.

EDGE CASE 7: Request with no matching route
  Gateway returns 404 with a generic error (not a backend-specific 404).
  Must NOT leak information about which services exist.
  Log the unmatched request (may indicate client misconfiguration or probing).
```

## Intentionally Out of Scope

```
OUT OF SCOPE 1: Business logic in the gateway
  The gateway routes, it does NOT transform business data.
  No: JSON field filtering, response aggregation, data enrichment.
  These belong in a BFF (Backend-for-Frontend) service, not the gateway.
  
  WHY: Business logic in the gateway creates coupling between the gateway
  team and every product team. Gateway deploys become coordination nightmares.

OUT OF SCOPE 2: Service mesh (internal service-to-service routing)
  The gateway handles EXTERNAL traffic (client → system).
  Internal routing (service → service) is handled by service mesh (Istio/Envoy).
  Some organizations use the same technology (Envoy) for both, but the
  concerns are different: external gateway has auth, rate limiting, API surface;
  internal mesh has circuit breaking, retries, observability.

OUT OF SCOPE 3: CDN / static content delivery
  Static assets (images, JS, CSS) are served by CDN, not the API gateway.
  The gateway handles API requests (dynamic, per-user, non-cacheable mostly).
  CDN sits in FRONT of the gateway for static paths.

OUT OF SCOPE 4: API management portal (developer docs, key provisioning)
  API key creation, documentation, and developer portal are adjacent concerns
  but not part of the data-plane gateway. They're control-plane tools that
  CONFIGURE the gateway, not part of the request processing path.
```

---

# Part 3: Non-Functional Requirements

## Latency Expectations

```
THE LATENCY BUDGET:

  Total user-perceived latency = Gateway overhead + Backend processing
  
  Backend processing: varies (50ms-500ms depending on service)
  Gateway overhead MUST be: < 5ms P99
  
  P50: < 1ms    (most requests add < 1ms overhead)
  P99: < 5ms    (even under load, overhead stays under 5ms)
  P99.9: < 15ms (extreme tail, acceptable during GC or config reload)

LATENCY BREAKDOWN (per request):
  TLS handshake: 0ms (reused connection) or 2-5ms (new connection)
  Request parsing: ~10µs
  Auth (JWT verify): ~50µs (local, cached key)
  Rate limiting: ~20µs (local counter)
  Route matching: ~5µs (compiled routing table)
  Header manipulation: ~5µs
  Backend selection: ~2µs
  Proxying overhead: ~50µs (kernel, buffer copy)
  Logging (async): ~5µs
  
  Total hot path: ~150µs (0.15ms)
  
  The 5ms budget gives 33× headroom. This headroom is for:
  → Auth key rotation (momentary cache miss → remote fetch)
  → Connection establishment to new backend instance
  → Config reload (routing table swap)
  → Garbage collection pauses

WHAT VIOLATES THE LATENCY BUDGET:
  ❌ Synchronous database lookup on every request
  ❌ Remote rate limit check (Redis) on every request
  ❌ Request body inspection/transformation
  ❌ Response body modification
  ❌ Synchronous logging to external system
  ❌ DNS resolution on every request
```

## Availability Expectations

```
TARGET: 99.999% availability (five nines)
  Downtime budget: 5.26 minutes per YEAR
  
  WHY FIVE NINES:
  The gateway is on the path of every request.
  If the gateway is 99.99% available, every service behind it is
  AT MOST 99.99% available—even if services themselves are 99.999%.
  The gateway is the FLOOR for the entire platform's availability.

HOW TO ACHIEVE FIVE NINES:
  1. Multi-instance (minimum 3 instances per AZ, 3 AZs)
  2. Health-check-based failover (< 10 second detection + failover)
  3. No single point of failure (no shared state between instances)
  4. Graceful degradation (if auth is slow, pass through with logging)
  5. Blue-green deploys (zero-downtime gateway updates)
  
  WHAT COUNTS AS "UNAVAILABLE":
  → Returning 5xx to clients when backends are healthy: Unavailable
  → Returning 5xx because backends are unhealthy: NOT gateway unavailability
  → Latency > 5× normal for > 1 minute: Counts as partial unavailability

THE STATELESSNESS REQUIREMENT:
  Gateway instances MUST be stateless with respect to request handling.
  → No server-side sessions
  → No in-gateway data that isn't reproducible from config/backends
  → Any instance can serve any request
  → Instance failure = requests redistributed to surviving instances
  → No data loss, no recovery needed
```

## Consistency Needs

```
ROUTING CONSISTENCY:
  All gateway instances MUST have the same routing configuration.
  Otherwise: Same request goes to different services depending on
  which gateway instance handles it → Unpredictable behavior.
  
  Consistency model: EVENTUAL (with < 10 second convergence)
  → New route config pushed → All instances apply within 10 seconds
  → During the 10-second window: Some instances have old routes
  → Acceptable: Routing changes are infrequent (a few per day)
  → NOT acceptable: Permanent divergence (requires reconciliation)

RATE LIMIT CONSISTENCY:
  Approximate: Local counters synced periodically
  A user at exactly the limit may get 5-10% more requests through
  during the sync interval. This is acceptable.
  
  Exact counting would require distributed consensus per request → 
  latency cost is unacceptable for a gateway.

SESSION CONSISTENCY:
  No sessions in the gateway → No consistency concern.
  If session affinity is needed: Use consistent hashing on user_id.
  This provides "best effort" affinity, not guaranteed stickiness.
```

## Durability

```
REQUEST DATA:
  Requests are transient—not stored durably in the gateway.
  If the gateway crashes mid-request, the request is LOST.
  Client retries (with idempotency key) handle this.

CONFIGURATION DATA:
  Route config, rate limit config, certificates: Stored durably
  in an external config store (not in the gateway itself).
  Gateway reads config at startup and receives updates via push.
  If gateway restarts: Re-reads config from store → No config loss.

ACCESS LOGS:
  Buffered in memory, flushed to log pipeline every 1 second.
  On crash: Up to 1 second of logs may be lost.
  Acceptable: Access logs are for analytics, not for transactions.
  
  If logs MUST be durable (billing, compliance):
  → Write to local disk first, then ship to pipeline
  → Adds ~100µs of disk write per request (acceptable for compliance)
```

## Correctness vs User Experience Trade-offs

```
TRADE-OFF 1: Rate limit accuracy vs latency
  Correct: Globally consistent rate limits (exactly N requests/minute)
  Fast: Locally approximate rate limits (N ± 10%)
  Decision: Fast. Users prefer 5% over-admission over 2ms added latency.

TRADE-OFF 2: Auth strictness vs availability
  Correct: If auth system is slow, reject all requests (fail closed)
  Available: If auth system is slow, pass through with degraded identity
  Decision: DEPENDS. For user-facing reads → pass through (availability).
  For writes and admin → fail closed (security).

TRADE-OFF 3: Route freshness vs stability
  Fresh: Apply route changes to in-flight requests immediately
  Stable: Apply route changes only to NEW requests
  Decision: Stable. In-flight requests complete with old routes.
  New requests use new routes. Avoids mid-request route switching.

TRADE-OFF 4: Error detail vs security
  Detailed: Return specific error ("Backend user-service timed out")
  Secure: Return generic error ("Internal server error")
  Decision: Generic to external clients, detailed to internal callers.
  External clients MUST NOT know about internal service topology.
```

## Security Implications

```
THE GATEWAY IS THE SECURITY PERIMETER:
  It's the ONLY component exposed to the internet.
  Every vulnerability in the gateway = vulnerability in the entire system.

SECURITY REQUIREMENTS:
  1. TLS 1.2+ only (no SSLv3, TLS 1.0, TLS 1.1)
  2. Strong cipher suites (ECDHE key exchange, AES-256-GCM)
  3. HTTP strict transport (HSTS headers)
  4. Request size limits (prevent memory exhaustion attacks)
  5. Header count limits (prevent header bomb attacks)
  6. Timeout on idle connections (prevent slowloris attacks)
  7. No information leakage in error responses
  8. CORS enforcement for browser clients
  9. CSRF protection for state-changing requests
  10. Rate limiting to prevent brute-force and enumeration attacks

ZERO-TRUST INTERNAL:
  Even though backend traffic is "internal," the gateway should:
  → Sign requests (HMAC or mTLS) so backends can verify origin
  → Include trace context so requests are attributable
  → Never forward raw client credentials to backends
```

---

# Part 4: Scale & Load Modeling

## Users and Sources

```
TRAFFIC SOURCES:
  1. Mobile apps (iOS, Android): 40% of traffic
     Behavior: Bursty, connection pooled, aggressive retry
  2. Web browsers (SPAs): 30% of traffic
     Behavior: Many small requests, WebSocket for real-time
  3. Third-party API consumers: 15% of traffic
     Behavior: Machine-generated, predictable patterns, quota-bound
  4. Internal services (through public gateway): 10% of traffic
     Behavior: High QPS, stable, mTLS authenticated
  5. Partner integrations: 5% of traffic
     Behavior: Webhook callbacks, batch operations

UNIQUE CLIENTS:
  50,000,000 active users/day (mobile + web)
  10,000 API key holders (third-party)
  500 internal services
  100 partner integrations
```

## QPS and Throughput

```
AVERAGE QPS: 2,000,000 requests/second (across all gateway instances)
PEAK QPS: 5,000,000 requests/second (2.5× average, during peak hours)
ABSOLUTE PEAK: 10,000,000 requests/second (5× average, flash sale / viral event)

THROUGHPUT:
  Average request size: 2 KB (headers + small JSON body)
  Average response size: 5 KB
  
  Inbound bandwidth: 2M QPS × 2 KB = 4 GB/s = 32 Gbps
  Outbound bandwidth: 2M QPS × 5 KB = 10 GB/s = 80 Gbps
  
  Total gateway bandwidth: ~112 Gbps (inbound + outbound)
  
  This requires ~12 gateway instances with 10 Gbps NICs,
  or ~6 instances with 25 Gbps NICs.
  With headroom for burst: 20 instances minimum.

CONNECTIONS:
  Average active connections: 2,000,000 (HTTP/2 multiplexed)
  Peak active connections: 5,000,000
  Connections per instance (20 instances): 250,000 peak
  
  This requires: Tuned kernel parameters (SO_REUSEPORT, file descriptor limits)
  and event-driven architecture (epoll/kqueue, not thread-per-connection).
```

## Read/Write Ratio

```
API TRAFFIC: 85% reads, 15% writes
  Most requests are GET (fetch data, list resources)
  Writes (POST/PUT/DELETE) are less frequent

GATEWAY CONFIGURATION: 99.999% reads, 0.001% writes
  Configuration changes are rare (a few per day)
  Gateway processes millions of requests per second against the same config
  This extreme read/write ratio means config can be aggressively cached.
```

## Growth Assumptions

```
YEAR 1: 2M QPS average
YEAR 2: 4M QPS (new mobile features, international expansion)
YEAR 3: 8M QPS (partner API program, real-time features)
YEAR 5: 20M QPS (IoT devices, embedded clients)

GROWTH IMPLICATIONS:
  Year 1-2: Horizontal scaling of stateless gateway instances
  Year 3: Need regional deployment (cross-continent latency becomes issue)
  Year 5: Need anycast + per-region gateway fleets
  
  MOST DANGEROUS GROWTH VECTOR: Number of distinct backend services.
  Year 1: 100 services (routing table fits in L1 cache)
  Year 3: 500 services (routing table fits in L2 cache)
  Year 5: 2,000 services (routing table needs careful data structure)
  
  Service count affects: Route matching time, config size, health check volume.
  2,000 services × 20 instances each × 1 health check / 5 seconds
  = 8,000 health checks per second PER gateway instance.
```

## Burst Behavior

```
BURST SCENARIO 1: Flash sale
  Normal: 2M QPS → Spike: 10M QPS in 30 seconds
  Impact: 5× traffic increase
  Gateway response:
  → Auto-scale (if cloud): Add instances in ~60 seconds
  → Until scale-out: Existing instances handle burst via connection queuing
  → Rate limits automatically protect backends from overload
  → If rate limits exceeded: Return 429 (graceful rejection, not crash)

BURST SCENARIO 2: Client retry storm
  Backend outage → All clients receive 503 → All clients retry immediately
  → 2M QPS becomes 6M QPS (each client retries up to 3 times)
  → Backend is now receiving 3× the traffic it was already failing under
  
  Gateway response:
  → Circuit breaker opens → Stop sending to failing backend
  → Return 503 with Retry-After header
  → Client-side exponential backoff (gateway communicates via headers)
  → Gateway absorbs retry traffic, preventing backend from being overwhelmed

BURST SCENARIO 3: Thundering herd on cold start
  Gateway instance restarts → Needs to establish connections to all backends
  → 2,000 services × 20 instances = 40,000 connections to establish
  → All at once → Connection storm on backends
  
  Mitigation: Connection warm-up with jitter
  → Establish connections gradually over 30 seconds (not all at once)
  → Random jitter: Each connection delayed by random(0, 30s)
  → Priority: Most-trafficked backends connect first

BURST SCENARIO 4: DNS TTL expiry storm
  All gateway instances' DNS cache expires simultaneously
  → All instances query DNS at the same moment
  → DNS server overloaded or becomes a bottleneck
  
  Mitigation: Staggered DNS refresh with TTL jitter
  → Add random jitter (±10%) to DNS TTL
  → Background refresh before TTL expires (at 80% of TTL)
```

## What Breaks First at Scale

```
BREAK 1: Connection limits (at ~5M concurrent connections)
  Each connection consumes ~10 KB of kernel memory
  5M connections × 10 KB = 50 GB of kernel memory for connections alone
  → Kernel runs out of socket buffers → New connections rejected
  → Fix: HTTP/2 multiplexing (1 connection per client, many requests)
  
BREAK 2: Route matching CPU (at ~2,000 services with complex rules)
  Linear scan of 2,000 routes × 5M QPS = 10 billion comparisons/second
  → CPU bottleneck on route matching
  → Fix: Compile routes into a trie or prefix tree (O(path_length) matching)

BREAK 3: Health check overhead (at ~50,000 backend instances)
  50,000 instances × 1 check / 5 seconds = 10,000 checks/second per gateway
  → Each check = TCP connection + HTTP request + response parsing
  → Fix: Centralized health checker (separate fleet) that publishes health state
  → Gateway reads health state, doesn't probe directly

BREAK 4: Access log volume (at ~10M QPS)
  10M QPS × 500 bytes/log = 5 GB/s of log data
  → Log pipeline becomes the bottleneck
  → Fix: Sample access logs (1% for detailed, 100% for metrics aggregation)

BREAK 5: TLS session resumption cache (at ~50M unique clients/day)
  TLS session tickets need to be shared across gateway instances
  → If not shared: Every client does full TLS handshake when hitting a different instance
  → Fix: Shared session ticket encryption key (rotated hourly)
  → All instances can resume any client's TLS session
```

## Scale Inflection Quick-Reference

| Scale | QPS | Services | Inflection Point | Mitigation |
|-------|-----|----------|------------------|------------|
| Startup | 1K | 10 | Single instance OK | Static config, no rate limit |
| Growth | 50K | 50 | Auth consistency, config drift | Centralized auth, version-controlled config |
| Mid | 500K | 200 | Redis on hot path (rate limit) | Replace with local counters + sync |
| Large | 5M | 500 | Per-backend pools essential | Isolate connection pools; centralized health checker if > 10K instances |
| Hyperscale | 20M+ | 2K | Route trie, TLS CPU, regional latency | Trie routing; TLS offload evaluation; multi-region gateways |

---

# Part 5: High-Level Architecture

## Core Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    API GATEWAY: HIGH-LEVEL ARCHITECTURE                     │
│                                                                             │
│   EXTERNAL TRAFFIC                                                          │
│   ┌──────┐ ┌──────┐ ┌──────┐                                                │
│   │Mobile│ │ Web  │ │ API  │                                                │
│   │ App  │ │Client│ │Client│                                                │
│   └──┬───┘ └──┬───┘ └──┬───┘                                                │
│      │        │        │                                                    │
│      └────────┼────────┘                                                    │
│               │                                                             │
│        ┌──────▼──────┐                                                      │
│        │    DNS /    │  Anycast / GeoDNS                                    │
│        │  Anycast    │  Route to nearest PoP                                │
│        └──────┬──────┘                                                      │
│               │                                                             │
│        ┌──────▼──────┐                                                      │
│        │  L4 Load    │  TCP-level distribution                              │
│        │  Balancer   │  (ECMP / IPVS / Cloud LB)                            │
│        └──────┬──────┘                                                      │
│               │                                                             │
│   ┌───────────┼───────────┐                                                 │
│   ▼           ▼           ▼                                                 │
│ ┌──────┐  ┌──────┐  ┌──────┐                                                │
│ │ GW 1 │  │ GW 2 │  │ GW N │   Gateway Fleet (stateless)                    │
│ └──┬───┘  └──┬───┘  └──┬───┘                                                │
│    │         │         │                                                    │
│    │   ┌─────┴─────┐   │                                                    │
│    │   │ Components│   │                                                    │
│    │   │ per GW:   │   │                                                    │
│    │   │           │   │                                                    │
│    │   │ • TLS     │   │                                                    │
│    │   │ • Auth    │   │                                                    │
│    │   │ • Rate    │   │                                                    │
│    │   │   Limiter │   │                                                    │
│    │   │ • Router  │   │                                                    │
│    │   │ • LB      │   │                                                    │
│    │   │ • Circuit │   │                                                    │
│    │   │   Breaker │   │                                                    │
│    │   │ • Logger  │   │                                                    │
│    │   └───────────┘   │                                                    │
│    │                   │                                                    │
│    └─────────┬─────────┘                                                    │
│              │                                                              │
│   ┌──────────┼──────────────────────────────────┐                           │
│   ▼          ▼          ▼          ▼            ▼                           │
│ ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────────┐                        │
│ │User  │  │Order │  │Auth  │  │Search│  │500 more  │                        │
│ │Svc   │  │Svc   │  │Svc   │  │Svc   │  │services  │                        │
│ └──────┘  └──────┘  └──────┘  └──────┘  └──────────┘                        │
│                                                                             │
│   CONTROL PLANE (separate from data path):                                  │
│   ┌──────────────────────────────────────────────────────────────┐          │
│   │  Config Store → Route Config, Rate Limits, Auth Config       │          │
│   │  Service Registry → Backend instance list + health           │          │
│   │  Certificate Store → TLS certificates                        │          │
│   │  Admin UI → Traffic management, monitoring                   │          │
│   └──────────────────────────────────────────────────────────────┘          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

```
COMPONENT 1: TLS TERMINATOR
  Responsibility: Decrypt incoming TLS, manage certificates
  State: TLS session cache (shared across instances via session tickets)
  Failure mode: Certificate expired → TLS handshake fails → 100% failure

COMPONENT 2: AUTHENTICATION ENGINE
  Responsibility: Verify tokens, extract identity, enforce coarse auth
  State: Cached public keys for JWT verification (refreshed every 5 minutes)
  Failure mode: Auth service unreachable → Fail open (reads) or closed (writes)

COMPONENT 3: RATE LIMITER
  Responsibility: Enforce per-user, per-service, global rate limits
  State: Local token bucket counters (synced periodically)
  Failure mode: Sync service unreachable → Use local counts (slightly inaccurate)

COMPONENT 4: ROUTER
  Responsibility: Match request to backend service based on route config
  State: Compiled routing table (loaded from config, updated via push)
  Failure mode: No matching route → 404 (generic, no info leakage)

COMPONENT 5: LOAD BALANCER
  Responsibility: Select backend instance, manage health state
  State: Instance list + health status (from service registry)
  Failure mode: All instances unhealthy → Circuit breaker → 503

COMPONENT 6: CIRCUIT BREAKER
  Responsibility: Stop sending traffic to failing backends
  State: Per-backend error rate, circuit state (closed/open/half-open)
  Failure mode: Stuck open → Traffic never sent → Manual override needed

COMPONENT 7: REQUEST PROXY
  Responsibility: Forward request to backend, return response
  State: Connection pool to each backend (persistent connections)
  Failure mode: Connection pool exhausted → Queue or reject new requests

COMPONENT 8: ACCESS LOGGER
  Responsibility: Log every request (async, non-blocking)
  State: In-memory log buffer (flushed every 1 second)
  Failure mode: Log pipeline slow → Buffer fills → Oldest logs dropped (never block)

COMPONENT 9: METRICS EMITTER
  Responsibility: Emit latency, error, throughput metrics
  State: In-memory histogram counters (flushed every 10 seconds)
  Failure mode: Metrics pipeline slow → Stale metrics, no request impact
```

## Stateless vs Stateful Decisions

```
STATELESS (by design):
  ✓ Request processing: Any instance handles any request
  ✓ Routing decisions: Based on config (loaded from external store)
  ✓ Authentication: Based on token + cached public key
  ✓ Connection to client: New request can go to any gateway

STATEFUL (necessary, but managed):
  △ Rate limit counters: Local state, periodically synced
    → Lost on restart → Slight over-admission during warm-up (acceptable)
  △ Circuit breaker state: Per-backend error tracking
    → Lost on restart → Re-evaluated within seconds from live traffic
  △ Connection pools: Persistent connections to backends
    → Lost on restart → Re-established automatically (with jitter)
  △ TLS session cache: Shared via session ticket key
    → Key distributed to all instances → Any instance can resume

CRITICAL DESIGN DECISION:
  The gateway has NO durable state.
  All state is either:
  → Derived from external source (config store, service registry)
  → Ephemeral and reconstructable (counters, connection pools)
  → Shared via symmetric key (TLS sessions)
  
  This means:
  → Gateway instances can be replaced at any time
  → Horizontal scaling is trivial (add instances, no data migration)
  → Crash recovery is instant (restart, reload config, serve traffic)
```

## Data Flow: Request Processing Pipeline

```
CLIENT REQUEST ARRIVES:

  ┌─────────────────────────────────────────────────────────┐
  │ 1. L4 LB selects gateway instance (ECMP / least-conn)   │
  └──────────────────────┬──────────────────────────────────┘
                         │
  ┌──────────────────────▼──────────────────────────────────┐
  │ 2. TLS: Decrypt (or reuse session)                      │
  │    IF new connection: Full handshake (2-5ms)            │
  │    IF resumed: Session ticket (0.5ms)                   │
  └──────────────────────┬──────────────────────────────────┘
                         │
  ┌──────────────────────▼──────────────────────────────────┐
  │ 3. REQUEST PARSING: Method, path, headers, body start   │
  │    Validate: Size limits, header count, method allowed  │
  └──────────────────────┬──────────────────────────────────┘
                         │
  ┌──────────────────────▼──────────────────────────────────┐
  │ 4. EARLY REJECTION: IP blocklist, global rate limit     │
  │    These checks happen BEFORE any expensive processing  │
  │    Reject early → Save CPU for legitimate requests      │
  └──────────────────────┬──────────────────────────────────┘
                         │
  ┌──────────────────────▼──────────────────────────────────┐
  │ 5. AUTHENTICATION: Verify token, extract identity       │
  │    Success → Attach X-User-ID headers                   │
  │    Failure → Return 401 (no further processing)         │
  └──────────────────────┬──────────────────────────────────┘
                         │
  ┌──────────────────────▼──────────────────────────────────┐
  │ 6. PER-USER RATE LIMITING: Check quota                  │
  │    Success → Continue                                   │
  │    Failure → Return 429 with Retry-After                │
  └──────────────────────┬──────────────────────────────────┘
                         │
  ┌──────────────────────▼──────────────────────────────────┐
  │ 7. ROUTE MATCHING: Find backend for this request        │
  │    Match on: path + method + headers + host             │
  │    Result: backend name, timeout, retry policy          │
  └──────────────────────┬──────────────────────────────────┘
                         │
  ┌──────────────────────▼──────────────────────────────────┐
  │ 8. CIRCUIT BREAKER CHECK: Is backend healthy?           │
  │    Closed → Continue                                    │
  │    Open → Return 503 (don't even try)                   │
  │    Half-open → Allow one probe request                  │
  └──────────────────────┬──────────────────────────────────┘
                         │
  ┌──────────────────────▼──────────────────────────────────┐
  │ 9. LOAD BALANCING: Select backend instance              │
  │    Algorithm: P2C (power of two random choices)         │
  │    Input: Instance list + active request counts         │
  └──────────────────────┬──────────────────────────────────┘
                         │
  ┌──────────────────────▼──────────────────────────────────┐
  │ 10. REQUEST FORWARDING: Send to backend instance        │
  │     Add: X-Request-ID, X-Forwarded-For, trace context   │
  │     Remove: Authorization header (identity already      │
  │             extracted and attached as verified headers) │
  └──────────────────────┬──────────────────────────────────┘
                         │
  ┌──────────────────────▼──────────────────────────────────┐
  │ 11. RESPONSE HANDLING: Receive backend response         │
  │     Check: Size limit, timeout, error status            │
  │     Transform: Add CORS headers, security headers       │
  │     Compress: gzip/brotli if client accepts             │
  └──────────────────────┬──────────────────────────────────┘
                         │
  ┌──────────────────────▼──────────────────────────────────┐
  │ 12. ACCESS LOG + METRICS (async, non-blocking)          │
  │     Log: request_id, path, status, latency, user_id     │
  │     Emit: latency histogram, error counter              │
  └─────────────────────────────────────────────────────────┘
```

---

# Part 6: Deep Component Design

## Component 1: TLS Terminator

### Internal Design

```
struct TLSTerminator:
  certificates: HashMap<Hostname, Certificate>  // SNI-based selection
  session_ticket_key: SymmetricKey               // Shared across instances
  tls_config: TLSConfig                          // Cipher suites, min version

CONNECTION HANDLING:
  FUNCTION on_new_connection(tcp_conn):
    // Peek at SNI (Server Name Indication) without consuming data
    sni_hostname = peek_tls_client_hello(tcp_conn)
    
    cert = certificates.get(sni_hostname)
    IF cert == NULL:
      cert = certificates.get("*")  // Default certificate
    IF cert == NULL:
      tcp_conn.close()  // No certificate for this hostname
      RETURN
    
    tls_conn = tls_handshake(tcp_conn, cert, tls_config)
    IF tls_conn.failed:
      metric.increment("tls_handshake_failure", {reason: tls_conn.error})
      RETURN
    
    RETURN tls_conn  // Now an encrypted connection

SESSION RESUMPTION:
  All gateway instances share the same session_ticket_key.
  Key is rotated every hour (new key encrypts, old key still decrypts).
  
  Client connects to GW-1, gets session ticket encrypted with KEY_A.
  Client reconnects to GW-2, presents ticket.
  GW-2 has KEY_A → Decrypts ticket → Resumes session (0-RTT).
  
  Without shared key: Client must do full handshake on every new instance.
  With 20 gateway instances: ~95% chance of hitting a different instance.
  Without session sharing: 95% of reconnections do full handshake.
  With session sharing: ~0% do full handshake (all have the key).

CERTIFICATE HOT-SWAP:
  FUNCTION reload_certificate(hostname, new_cert):
    // Atomic swap using read-copy-update pattern
    old_certs = certificates
    new_certs = old_certs.clone()
    new_certs.put(hostname, new_cert)
    certificates = new_certs  // Atomic pointer swap
    
    // Old certificate still in use by existing connections
    // New connections use new certificate
    // No downtime, no connection interruption
```

### Failure Behavior

```
CERTIFICATE EXPIRED:
  Impact: ALL new TLS connections fail → 100% failure for new requests
  Existing connections: UNAFFECTED (TLS already established)
  Detection: Monitor certificate expiry → Alert at 30 days, 7 days, 1 day
  Recovery: Automated renewal (ACME) should prevent this entirely
  
  Staff insight: Certificate expiry is the #1 cause of "everything died at once"
  outages. A monitoring gap in cert expiry detection has caused major outages
  at Google, Facebook, and Microsoft. Automated renewal + expiry alerting
  is non-negotiable.

SESSION TICKET KEY COMPROMISE:
  Impact: Attacker can decrypt past sessions (if they captured traffic)
  Mitigation: Rotate key hourly → Limits exposure window to 1 hour
  Forward secrecy: Use ECDHE key exchange → Even with ticket key,
  attacker cannot decrypt sessions (key exchange is ephemeral)
  
TLS HANDSHAKE OVERLOAD:
  During DDoS: Attacker sends many TLS handshakes (CPU-intensive)
  → Gateway spends all CPU on handshakes, no capacity for real requests
  Mitigation:
  → SYN cookies at L4 (prevent TCP state exhaustion)
  → Rate limit new connections per IP (not per request)
  → TLS early termination: If handshake takes > 5s, abort
```

## Component 2: Authentication Engine

### Internal Design

```
struct AuthEngine:
  jwt_verifiers: HashMap<Issuer, JWTVerifier>
  api_key_cache: LRUCache<APIKey, KeyMetadata>   // Capacity: 100K keys
  public_key_cache: HashMap<Issuer, PublicKeySet>
  key_refresh_interval: 5 minutes

FUNCTION authenticate(request):
  // Try each auth method in order
  
  // 1. JWT token (most common)
  auth_header = request.headers.get("Authorization")
  IF auth_header != NULL AND auth_header.starts_with("Bearer "):
    token = auth_header.strip_prefix("Bearer ")
    RETURN verify_jwt(token)
  
  // 2. API key
  api_key = request.headers.get("X-API-Key")
  IF api_key != NULL:
    RETURN verify_api_key(api_key)
  
  // 3. mTLS (internal services)
  IF request.tls_client_cert != NULL:
    RETURN verify_mtls(request.tls_client_cert)
  
  // 4. No credentials
  IF route.allows_anonymous:
    RETURN Identity{type: "anonymous", scopes: ["public:read"]}
  ELSE:
    RETURN 401 Unauthorized

FUNCTION verify_jwt(token):
  // Decode without verification (to get issuer and key ID)
  header = decode_jwt_header(token)
  
  // Get public key (from cache or fetch)
  keys = public_key_cache.get(header.issuer)
  IF keys == NULL OR keys.expired:
    keys = fetch_public_keys(header.issuer)  // JWKS endpoint
    public_key_cache.put(header.issuer, keys)
  
  key = keys.get(header.kid)
  IF key == NULL:
    RETURN 401 ("Unknown signing key")
  
  // Verify signature
  IF NOT verify_signature(token, key):
    RETURN 401 ("Invalid signature")
  
  // Check expiry
  claims = decode_jwt_payload(token)
  IF claims.exp < now():
    RETURN 401 ("Token expired")
  
  // Build identity
  RETURN Identity{
    user_id: claims.sub,
    scopes: claims.scope,
    auth_method: "jwt",
    token_expiry: claims.exp
  }

FUNCTION verify_api_key(key):
  // Check local cache first
  metadata = api_key_cache.get(key)
  IF metadata != NULL AND metadata.valid:
    RETURN Identity{
      client_id: metadata.client_id,
      scopes: metadata.scopes,
      auth_method: "api_key",
      rate_limit_tier: metadata.tier
    }
  
  // Cache miss → Fetch from key store (async, with circuit breaker)
  TRY:
    metadata = key_store.lookup(hash(key))  // Never send raw key over network
    api_key_cache.put(key, metadata, ttl=5_MINUTES)
    RETURN Identity{...metadata...}
  CATCH:
    // Key store unreachable
    IF metadata != NULL:  // Stale cache entry
      LOG.warn("Key store unreachable, using stale cache for API key")
      RETURN Identity{...metadata...}
    RETURN 401 ("Unable to verify API key")
```

### Failure Behavior

```
JWT PUBLIC KEY FETCH FAILURE:
  Impact: New signing keys not recognized → New tokens fail
  Existing cached keys: Still work (covers 99% of tokens)
  Duration tolerance: Hours (keys rotate infrequently)
  Mitigation: Cache keys with long TTL (24 hours), background refresh
  
  Timeline:
  T+0:    JWKS endpoint unreachable
  T+5min: Key refresh fails (logged, retries)
  T+24hr: Cached keys expire → NEW tokens with NEW keys fail
  T+24hr: Alert fires → Investigation
  
  Staff insight: Most auth outages are caused by key rotation
  + cache expiry happening simultaneously. Stagger: Rotate key at T+0,
  new key in JWKS at T-6hr (published before use), cached at T+0.

API KEY STORE UNREACHABLE:
  Impact: New API keys cannot be verified (cache miss = failure)
  Cached keys: Continue working
  Mitigation: Large cache (100K keys × 1KB = 100MB) covers most active keys
  
AUTH ENGINE SLOW (>100ms):
  Impact: Every request adds 100ms+ of latency
  Gateway policy:
  → For read requests: Skip auth, forward with "X-Auth-Status: degraded"
  → Backend can choose to serve cached/public data
  → For write requests: Fail with 503 (do not allow unauthenticated writes)
  
  This is the FAIL-OPEN-FOR-READS, FAIL-CLOSED-FOR-WRITES pattern.
```

## Component 3: Rate Limiter

### Internal Design

```
struct RateLimiter:
  local_buckets: HashMap<RateLimitKey, TokenBucket>
  config: RateLimitConfig  // Per-user, per-service, global limits
  sync_interval: 1 second

struct TokenBucket:
  tokens: float
  last_refill: Timestamp
  capacity: int
  refill_rate: float  // tokens per second

struct RateLimitKey:
  dimension: enum {GLOBAL, PER_SERVICE, PER_USER, PER_ENDPOINT}
  identity: String  // user_id, service_name, endpoint_path
  
FUNCTION check_rate_limit(request, identity):
  // Layer 1: Global limit (infrastructure protection)
  IF NOT check_bucket(RateLimitKey{GLOBAL, "all"}, config.global_limit):
    RETURN DENY {reason: "Global rate limit exceeded", retry_after: 60}
  
  // Layer 2: Per-service limit (backend protection)
  service = router.resolve(request).backend_name
  IF NOT check_bucket(RateLimitKey{PER_SERVICE, service}, config.service_limits[service]):
    RETURN DENY {reason: "Service rate limit exceeded", retry_after: 30}
  
  // Layer 3: Per-user limit (abuse prevention)
  user_limit = get_user_limit(identity)  // Based on tier: free, paid, enterprise
  IF NOT check_bucket(RateLimitKey{PER_USER, identity.user_id}, user_limit):
    RETURN DENY {reason: "User rate limit exceeded", retry_after: compute_retry_after()}
  
  // Layer 4: Per-endpoint limit (expensive operation protection)
  endpoint = request.method + ":" + request.path
  IF config.endpoint_limits.has(endpoint):
    IF NOT check_bucket(RateLimitKey{PER_ENDPOINT, identity.user_id + endpoint}, 
                        config.endpoint_limits[endpoint]):
      RETURN DENY {reason: "Endpoint rate limit exceeded", retry_after: 10}
  
  RETURN ALLOW

FUNCTION check_bucket(key, limit):
  bucket = local_buckets.get_or_create(key, limit)
  
  // Refill tokens based on elapsed time
  elapsed = now() - bucket.last_refill
  bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_rate)
  bucket.last_refill = now()
  
  IF bucket.tokens >= 1.0:
    bucket.tokens -= 1.0
    RETURN true
  RETURN false

DISTRIBUTED SYNCHRONIZATION:
  Every 1 second, each gateway instance reports its local counts:
  → "Instance GW-3 used 5,000 tokens for user_123 in the last second"
  → Central aggregator computes global usage per key
  → If global usage > 80% of limit: Send "slow down" signal to all instances
  → Each instance adjusts local capacity: local_limit = global_limit / N_instances
  
  This is the LOCAL-COUNT-WITH-GLOBAL-FEEDBACK pattern.
  
  Accuracy: ±10% of true rate (acceptable for rate limiting)
  Latency impact: 0 (sync is async, never blocks request path)
  Failure mode: Sync fails → Each instance uses local limit (over-admission = N×)
```

### Why Simpler Alternatives Fail

```
ALTERNATIVE 1: Central counter (Redis) on every request
  Each request: INCR user:{user_id}:count (Redis round-trip)
  Latency: 1-2ms per request (Redis RTT)
  At 5M QPS: 5M Redis operations/second → Need Redis cluster
  If Redis is slow: Every API request is slow
  If Redis is down: Rate limiting doesn't work
  
  REJECTED: Redis on the hot path is a latency and availability risk.
  Rate limiting MUST NOT be slower than the operation it protects.

ALTERNATIVE 2: Sticky sessions (route user to same gateway instance)
  → Local counters are accurate (no sync needed)
  → But: Load balancing is uneven (hot users on one instance)
  → Instance failure → All sticky users redistributed → Rate limit reset
  → Defeats the purpose of stateless gateway
  
  REJECTED: Stickiness creates operational complexity for minimal benefit.

ALTERNATIVE 3: No rate limiting (backends protect themselves)
  → Each backend implements its own rate limiting
  → Inconsistent limits across services
  → DDoS traffic reaches backends (gateway provides no protection)
  → Backend resources wasted rejecting bad traffic
  
  REJECTED: Rate limiting at the edge is 10× more efficient than at the backend.
  Rejecting a request at the gateway costs ~100µs. At the backend: ~5ms.
```

## Component 4: Router

### Internal Design

```
struct Router:
  route_table: RouteTrie            // Compiled routing table
  config_version: Version           // Current config version
  default_route: RouteAction        // Fallback for unmatched requests

struct RouteTrie:
  // Prefix trie optimized for URL path matching
  root: TrieNode
  
struct TrieNode:
  children: HashMap<String, TrieNode>     // Exact path segment
  wildcard_child: TrieNode                // * match
  param_child: TrieNode                   // :param match
  rules: List<RouteRule>                  // Rules at this path depth

struct RouteRule:
  match:
    method: HTTP_METHOD (optional)
    headers: HashMap<String, Matcher>  (optional)
    query_params: HashMap<String, Matcher>  (optional)
  action:
    backend: String
    weight: int (0-100, for canary/blue-green)
    timeout: Duration
    retry_policy: RetryPolicy
  priority: int  // Higher = evaluated first

FUNCTION route(request):
  // Step 1: Trie lookup by path
  node = route_table.root
  path_segments = request.path.split("/")
  
  FOR segment IN path_segments:
    IF node.children.has(segment):
      node = node.children[segment]        // Exact match (highest priority)
    ELSE IF node.param_child != NULL:
      node = node.param_child              // Parameter match
      request.params.add(node.param_name, segment)
    ELSE IF node.wildcard_child != NULL:
      node = node.wildcard_child           // Wildcard match
      BREAK  // Wildcard consumes remaining path
    ELSE:
      RETURN default_route  // No match → 404
  
  // Step 2: Apply method + header matching
  FOR rule IN node.rules SORTED BY priority DESC:
    IF rule.matches_method(request.method) AND
       rule.matches_headers(request.headers):
      RETURN resolve_weighted_backend(rule)
  
  RETURN default_route

FUNCTION resolve_weighted_backend(rule):
  // For canary/blue-green: Select backend based on weight
  IF rule.action.backends.length == 1:
    RETURN rule.action.backends[0]
  
  // Weighted random selection
  rand = random(0, 100)
  cumulative = 0
  FOR backend IN rule.action.backends:
    cumulative += backend.weight
    IF rand < cumulative:
      RETURN backend
  
  RETURN rule.action.backends[0]  // Fallback

ROUTE COMPILATION:
  Route config (YAML/JSON) is compiled into a trie at config load time.
  Compilation time: ~1ms for 2,000 routes (done once, not per-request)
  Lookup time: O(path_depth) → typically O(3-5) → ~5µs
  
  WHY TRIE AND NOT REGEX:
  Regex matching for 2,000 routes: O(N × regex_complexity)
  → At 5M QPS: Unacceptable CPU overhead
  Trie matching: O(path_depth) regardless of route count
  → Scales to 100,000 routes with no degradation

ROUTE CONFIG HOT-RELOAD:
  FUNCTION reload_routes(new_config):
    // Validate new config
    errors = validate_routes(new_config)
    IF errors.any:
      LOG.error("Route config validation failed", errors)
      RETURN  // Keep old config, don't apply broken config
    
    // Compile new trie (in background, ~1ms)
    new_trie = compile_trie(new_config)
    
    // Atomic swap (read-copy-update)
    old_trie = route_table
    route_table = new_trie  // Atomic pointer swap
    config_version = new_config.version
    
    // Old trie still referenced by in-flight requests
    // Garbage collected when all in-flight requests complete
    
    LOG.info("Route config updated: v{old} → v{new}")
```

### Route Config Rollback Mechanism

```
ROLLBACK TRIGGERS:
  1. MANUAL: On-call clicks "rollback" in admin UI
  2. AUTOMATIC: Global error rate > threshold within 30s of config push
  3. CANARY FAILURE: Canary instance error rate > control + 1%

FUNCTION rollback_route_config():
  current_version = route_table.version
  previous_version = config_store.get_version(current_version - 1)
  
  IF previous_version == NULL:
    LOG.error("No previous version to rollback to!")
    alert("Route config rollback failed: no previous version")
    RETURN
  
  // Validate previous version is still valid
  errors = validate_routes(previous_version.config)
  IF errors.any:
    LOG.error("Previous route config no longer valid", errors)
    // May happen if backends have been decommissioned since
    alert("Route config rollback to v{} has validation errors", current_version - 1)
    // Force rollback anyway (broken routes better than wrong routes)
  
  // Push rollback to all instances
  config_store.set_active(previous_version)
  // Config push propagates to all instances within 10 seconds
  
  // Log rollback event
  audit_log({
    action: "ROUTE_CONFIG_ROLLBACK",
    from_version: current_version,
    to_version: current_version - 1,
    trigger: rollback_trigger,  // "manual" | "auto_error_rate" | "canary_failure"
    actor: current_actor_or_system()
  })

AUTOMATIC ROLLBACK MECHANISM:
  FUNCTION monitor_post_config_change():
    baseline_error_rate = get_error_rate(window=5_MINUTES)
    
    SLEEP(30_SECONDS)  // Wait for config to propagate and stabilize
    
    current_error_rate = get_error_rate(window=30_SECONDS)
    
    IF current_error_rate > baseline_error_rate + 0.05:  // 5% increase
      LOG.warn("Error rate spike detected after config change")
      rollback_route_config()
      alert("Route config auto-rolled back: error rate {baseline} → {current}")

CONFIG VERSION HISTORY:
  Keep last 50 versions in config store.
  Each version: Full route config + metadata (who, when, why).
  Rollback to ANY of the last 50 versions (not just previous).
  
  WHY 50: Config changes ~10/day → 50 versions = 5 days of history.
  If a subtle bug is discovered days later, you can rollback to before it.
```

### Failure Behavior

```
ROUTE CONFIG LOAD FAILURE:
  Impact: Gateway starts with no routes → All requests get 404
  Prevention: Gateway refuses to start without valid route config
  → Readiness probe fails → Load balancer doesn't send traffic → No impact
  
  If config becomes unavailable DURING operation:
  → Gateway continues with last-known-good config
  → Alert: "Route config refresh failed, running on stale config"

ROUTE CONFLICT:
  Two rules match the same request with different backends.
  Example:
    /api/v2/users/* → user-service
    /api/v2/users/search → search-service
  
  Resolution: More specific path wins (exact > param > wildcard).
  /api/v2/users/search → search-service (exact match)
  /api/v2/users/123 → user-service (wildcard match)
  
  If truly ambiguous: REJECTED at config validation time.
  The router NEVER makes an arbitrary choice at runtime.
```

## Component 5: Circuit Breaker

### Internal Design

```
struct CircuitBreaker:
  backends: HashMap<BackendName, CircuitState>
  config: CircuitBreakerConfig

struct CircuitState:
  state: enum {CLOSED, OPEN, HALF_OPEN}
  failure_count: SlidingWindow  // Failures in last 60 seconds
  success_count: SlidingWindow  // Successes in last 60 seconds
  last_state_change: Timestamp
  
struct CircuitBreakerConfig:
  failure_threshold: 50%     // Open circuit if >50% of requests fail
  min_requests: 20           // Need at least 20 requests to evaluate
  open_duration: 30 seconds  // Stay open for 30 seconds before half-open
  half_open_max: 5           // Allow 5 probe requests in half-open state

FUNCTION check_circuit(backend):
  state = backends.get(backend)
  
  SWITCH state.state:
    CASE CLOSED:
      RETURN ALLOW  // Normal operation
    
    CASE OPEN:
      IF now() - state.last_state_change > config.open_duration:
        state.state = HALF_OPEN
        state.probe_count = 0
        RETURN ALLOW  // Allow probe request
      ELSE:
        RETURN DENY  // Circuit is open, reject
    
    CASE HALF_OPEN:
      IF state.probe_count < config.half_open_max:
        state.probe_count += 1
        RETURN ALLOW  // Allow limited probe
      ELSE:
        RETURN DENY  // Enough probes, wait for results

FUNCTION record_result(backend, success):
  state = backends.get(backend)
  
  IF success:
    state.success_count.add(1)
  ELSE:
    state.failure_count.add(1)
  
  // Evaluate circuit
  total = state.failure_count.sum() + state.success_count.sum()
  IF total >= config.min_requests:
    failure_rate = state.failure_count.sum() / total
    
    IF state.state == CLOSED AND failure_rate > config.failure_threshold:
      state.state = OPEN
      state.last_state_change = now()
      LOG.warn("Circuit OPENED for {backend}: failure_rate={failure_rate}")
      alert("Circuit breaker opened for {backend}")
    
    IF state.state == HALF_OPEN:
      IF failure_rate < config.failure_threshold / 2:
        state.state = CLOSED
        LOG.info("Circuit CLOSED for {backend}: recovered")
      ELSE:
        state.state = OPEN
        state.last_state_change = now()
        LOG.warn("Circuit RE-OPENED for {backend}: still failing")

WHY 50% THRESHOLD (NOT LOWER):
  10% failure rate might be normal for some backends (timeouts under load).
  Opening circuit at 10% → Backend loses ALL traffic → Worse than 10% failure.
  50% threshold: Backend is clearly unhealthy. Shedding load helps it recover.
  
  Staff insight: The circuit breaker threshold should be HIGHER than the
  "we're paging someone" threshold. If 10% errors page the on-call,
  the circuit breaker at 50% is a LAST RESORT, not the first response.
  Most recovery happens through other mechanisms (auto-scaling, restart)
  before the circuit opens.
```

### Failure Behavior

```
CIRCUIT STUCK OPEN:
  Backend recovered but circuit breaker is still open.
  Cause: Half-open probes keep failing (but backend is healthy for non-probe traffic).
  
  Mitigation:
  1. Active health check (separate from probes) that tests backend health
  2. Manual override: "Force close circuit for backend X"
  3. Time-based decay: After 5 minutes open, force half-open regardless

CIRCUIT FLAPPING:
  Backend is intermittently healthy: Open → Half-open → Closed → Open (repeat).
  Impact: Traffic to backend is unstable (on/off/on/off).
  
  Mitigation:
  → Cooldown period: After closing, don't re-evaluate for 60 seconds
  → Gradual close: Half-open allows 5 probes, then 10%, 50%, 100% traffic
  → This prevents "all traffic hits recovering backend → backend fails again"
```

## Component 5b: Centralized Health Checker (Scale Solution)

### Internal Design

```
PROBLEM: At 50,000 backend instances, each gateway doing health checks
generates: 50,000 instances × 1 check/5s × 20 gateways = 200,000 checks/second
total, with each backend receiving 20 checks every 5 seconds (one from each GW).

This is wasteful and creates unnecessary load on backends.

SOLUTION: Centralized health checker fleet (separate from gateway).
  Health checker: 3-5 instances (small fleet, independent of gateway)
  Each backend probed by ONE health checker every 5 seconds
  Health state published to all gateways via push

ARCHITECTURE:
  Health checker fleet → Probes all backend instances every 5 seconds
                       → Publishes health state to shared store (pub/sub)
  Gateway fleet       → Subscribes to health state updates
                       → Updates local instance list immediately

  Total probes: 50,000 instances × 1 check/5s = 10,000 checks/second
  vs WITHOUT centralized checker: 200,000 checks/second (20× more)

struct HealthChecker:
  instance_registry: InstanceRegistry
  health_state: HashMap<InstanceID, HealthStatus>
  publisher: HealthStatePublisher

struct HealthStatus:
  state: enum {HEALTHY, UNHEALTHY, DRAINING}
  last_check: Timestamp
  consecutive_failures: int
  last_latency: Duration

FUNCTION check_instance(instance):
  TRY:
    start = now()
    response = http_get(instance.health_url, timeout=2_SECONDS)
    latency = now() - start
    
    IF response.status == 200:
      update_state(instance, HEALTHY, latency)
    ELSE IF response.status == 503:
      update_state(instance, DRAINING, latency)  // Graceful shutdown
    ELSE:
      record_failure(instance)
  CATCH timeout_or_connection_error:
    record_failure(instance)

FUNCTION record_failure(instance):
  state = health_state.get(instance)
  state.consecutive_failures += 1
  IF state.consecutive_failures >= 3:
    update_state(instance, UNHEALTHY, NULL)
    publisher.publish(instance.id, UNHEALTHY)
    // All gateways receive this within < 1 second

IMPORTANT DESIGN DECISIONS:
  1. Health checker is SEPARATE from gateway → No impact on request processing.
  2. Health checker failure → Gateways use PASSIVE health detection (error rates).
     Gateway circuit breakers work independently of centralized health checker.
  3. Health state is ADDITIVE to circuit breakers, not a replacement.
     Centralized health check: "Is the instance reachable?"
     Gateway circuit breaker: "Is the instance returning errors for MY traffic?"
     Both are needed. An instance can be reachable but returning errors.

WHEN NOT TO USE CENTRALIZED HEALTH CHECKER:
  < 5,000 backend instances → Per-gateway health checks are fine
  5,000 instances × 20 gateways × 1/5s = 20,000 checks/second → Manageable
  
  > 10,000 instances → Centralized checker becomes worthwhile
  50,000 instances → Centralized checker is necessary
```

## Component 6: Connection Pool Manager

### Internal Design

```
struct ConnectionPoolManager:
  pools: HashMap<BackendName, ConnectionPool>

struct ConnectionPool:
  idle_connections: Queue<Connection>
  active_connections: AtomicInt
  config: PoolConfig
  
struct PoolConfig:
  max_connections: 100              // Per backend instance
  max_idle: 10                      // Keep 10 warm connections
  idle_timeout: 90 seconds          // Close idle connections after 90s
  connect_timeout: 1 second         // Max time to establish new connection
  max_lifetime: 5 minutes           // Force-close after 5 minutes (prevent stale)

FUNCTION get_connection(backend_instance):
  pool = pools.get_or_create(backend_instance)
  
  // Try to get an idle connection
  conn = pool.idle_connections.poll()
  IF conn != NULL AND conn.is_healthy():
    pool.active_connections.increment()
    RETURN conn
  
  // No idle connection → Create new one
  IF pool.active_connections.get() >= pool.config.max_connections:
    // Pool exhausted → Queue the request (with timeout)
    RETURN wait_for_connection(pool, timeout=1_SECOND)
  
  // Create new connection
  conn = create_connection(backend_instance, pool.config.connect_timeout)
  pool.active_connections.increment()
  RETURN conn

FUNCTION release_connection(backend_instance, conn):
  pool = pools.get(backend_instance)
  pool.active_connections.decrement()
  
  IF conn.is_healthy() AND pool.idle_connections.size() < pool.config.max_idle:
    pool.idle_connections.offer(conn)  // Return to pool
  ELSE:
    conn.close()  // Too many idle or unhealthy → Close

WHY CONNECTION POOLING MATTERS:
  Without pooling: Each request creates a new TCP connection to backend.
  TCP handshake: ~0.5ms (same datacenter)
  At 5M QPS: 5M handshakes/second → Enormous overhead, TIME_WAIT exhaustion
  
  With pooling: Reuse existing connections.
  Connection reuse rate: >99%
  New connection rate: <1% of requests (new backends, pool warm-up)
  
  Staff insight: Connection pool exhaustion is one of the sneakiest
  failure modes. Backend is "healthy" but all connections are in use.
  New requests queue → Timeout → Client sees 504 → Backend looks fine
  in its own metrics. The bottleneck is in the GATEWAY's pool, not
  the backend itself. Monitor pool utilization as a first-class metric.
```

## Component 7: Access Logger

### Internal Design

```
struct AccessLogger:
  buffer: RingBuffer<LogEntry>     // Fixed-size, non-blocking
  flush_interval: 1 second
  log_pipeline: LogPipelineClient  // Async log shipping

struct LogEntry:
  timestamp: Timestamp
  request_id: String
  method: String
  path: String
  status: int
  latency_ms: float
  gateway_overhead_ms: float  // Latency attributable to gateway
  backend: String
  backend_instance: String
  user_id: String
  client_ip: String
  user_agent: String
  request_size: int
  response_size: int
  tls_version: String
  auth_method: String
  rate_limited: boolean
  circuit_breaker_state: String
  trace_id: String

FUNCTION log_request(request, response, timing):
  entry = LogEntry{
    timestamp: now(),
    request_id: request.id,
    method: request.method,
    path: request.path,
    status: response.status,
    latency_ms: timing.total_ms,
    gateway_overhead_ms: timing.total_ms - timing.backend_ms,
    backend: timing.backend_name,
    backend_instance: timing.backend_instance,
    user_id: request.identity.user_id,
    client_ip: request.remote_addr,
    // ... remaining fields
  }
  
  // Non-blocking write to ring buffer
  IF NOT buffer.try_offer(entry):
    metric.increment("access_log_dropped")
    // Buffer full → Drop log entry (NEVER block the request path)
  
  // Background flusher runs every 1 second
  // Bulk-ships log entries to pipeline

WHY RING BUFFER, NOT QUEUE:
  Queue (unbounded): Memory grows under backpressure → OOM → Gateway crash
  Queue (bounded, blocking): Log pipeline slow → Requests block → Latency spike
  Ring buffer (bounded, non-blocking): Overflow → Old entries overwritten
  
  Staff decision: Drop logs rather than slow down requests.
  Dropped logs: ~0.001% under normal operation (ring buffer is large enough)
  During log pipeline outage: Logs are lost, but requests are unaffected.
  Requests >> Logs in importance.

SAMPLING FOR HIGH-VOLUME ENDPOINTS:
  At 5M QPS × 500 bytes/log = 2.5 GB/s of log data
  
  Strategy: Log 100% of errors, sample successes
  → All 4xx/5xx responses: Full log entry
  → 2xx responses: 10% sampled (reduce to 250 MB/s)
  → Health check responses: 0.1% sampled
  
  For billing/compliance: Separate, durable log pipeline (not access log)
```

---

# Part 7: Data Model & Storage Decisions

## What Data Is Stored

```
DATA CATEGORY 1: Route configuration
  ~2,000 route rules (growing to ~10,000)
  Average rule size: 500 bytes
  Total: ~5 MB (trivially small)
  Stored in: Config store (versioned, auditable)
  Loaded into: Gateway memory (compiled routing trie)

DATA CATEGORY 2: Rate limit configuration
  ~1,000 rate limit rules
  Average rule size: 200 bytes
  Total: ~200 KB
  Stored in: Config store
  Loaded into: Gateway memory

DATA CATEGORY 3: Backend service registry
  ~500 services × 20 instances each = 10,000 entries
  Per entry: hostname, port, weight, health status, metadata
  Average entry: 500 bytes
  Total: ~5 MB
  Source: Service registry (Consul, etcd, Kubernetes API, or custom)
  Updated: Real-time (health changes, scale events)

DATA CATEGORY 4: TLS certificates
  ~50 certificates (one per hostname/domain)
  Average size: 5 KB (cert chain)
  Total: ~250 KB
  Source: Certificate store / PKI
  Updated: On rotation (monthly)

DATA CATEGORY 5: Access logs (transient)
  ~5M entries/second (during peak)
  Average entry: 500 bytes
  Retention in gateway: 1-2 seconds (buffer)
  Shipped to: Log pipeline (Kafka → storage)
  Long-term retention: 30-90 days in log storage

DATA CATEGORY 6: Rate limit counters (ephemeral)
  ~10M active counters (users × endpoints)
  Per counter: 16 bytes (token count + timestamp)
  Total: ~160 MB in-memory per gateway instance
  Persistence: None (reconstructed from traffic patterns)

DATA CATEGORY 7: Circuit breaker state (ephemeral)
  ~500 backends × sliding window counters
  Total: ~500 KB per gateway instance
  Persistence: None (reconstructed within seconds of restart)
```

## How Data Is Keyed

```
ROUTE CONFIG:
  Key: (path_prefix, method, host)
  Example: ("/api/v2/users", "GET", "api.example.com")
  Stored as trie nodes for efficient prefix matching.

RATE LIMIT COUNTERS:
  Key: (dimension, identity, window)
  Example: ("per_user", "user_12345", "2024-01-15T10:05")
  Window key: Truncated to minute boundary for sliding window.

SERVICE REGISTRY:
  Key: (service_name, instance_id)
  Example: ("user-service", "instance-us-east-1-a-001")
  
CERTIFICATES:
  Key: (hostname)
  Example: ("api.example.com")
  SNI selection uses this key.

ACCESS LOGS:
  Key: (timestamp, request_id)
  Ordered by timestamp for efficient time-range queries.
```

## How Data Is Partitioned

```
ROUTE CONFIG: NOT partitioned (entire config on every instance)
  Total config size: ~5 MB → Trivially fits in memory
  Every gateway instance has a COMPLETE copy of all routes.
  No partitioning needed. No partial routing.

RATE LIMIT COUNTERS: Partitioned by gateway instance
  Each instance tracks its own counters locally.
  Global aggregation via periodic sync (no per-request coordination).
  
  WHY NOT centrally partitioned (e.g., Redis shards):
  → Would add latency to every request (Redis round-trip)
  → Gateway is designed for zero-external-dependency request processing

SERVICE REGISTRY: NOT partitioned (full copy per instance)
  10,000 entries × 500 bytes = 5 MB → Fits in memory
  Each gateway needs to know about ALL backends (routes to any service).

ACCESS LOGS: Partitioned by time
  Logs shipped to pipeline in time-ordered batches.
  Log storage partitioned by (date, service_name).
  Query pattern: "Show me all 5xx errors for user-service on 2024-01-15"
```

## Retention Policies

```
ROUTE CONFIG: Versioned, indefinite (for audit)
  Active config: Latest version (in-memory)
  Historical: Keep 100 versions in config store
  Purpose: Rollback, audit, "who changed what"

RATE LIMIT COUNTERS: Ephemeral, current window only
  Token bucket state: Current window (1 minute)
  No historical retention needed (counters are derived from traffic)

ACCESS LOGS: 90 days detailed, 1 year aggregated
  Detailed logs (per-request): 90 days
  Aggregated metrics (per-minute): 1 year
  After 90 days: Detailed logs archived to cold storage (if compliance requires)

CIRCUIT BREAKER HISTORY: 7 days
  When did circuits open/close? (for incident analysis)
  Stored in metrics system (not in gateway)
```

## Schema Evolution

```
ROUTE CONFIG EVOLUTION:
  V1: path + method → backend
  V2: + header matching, + weight (canary support)
  V3: + query param matching, + retry policy, + timeout per route
  V4: + gRPC method matching, + WebSocket upgrade support
  
  Strategy: Additive fields only. New fields have defaults.
  Old config without retry_policy → Use system-wide default retry policy.
  Gateway must accept V1 configs and V4 configs simultaneously.
  
RATE LIMIT CONFIG EVOLUTION:
  V1: per-user, per-IP limits
  V2: + per-service, per-endpoint limits
  V3: + tier-based limits, + burst allowance
  
  Strategy: Same additive approach. Missing fields → defaults.

ACCESS LOG SCHEMA EVOLUTION:
  New fields added over time (e.g., "circuit_breaker_state" in v3).
  Log pipeline must handle: Old logs without new fields.
  Strategy: Log entries include schema_version field.
  Consumers handle missing fields gracefully.
```

## Why Other Data Models Were Rejected

```
REJECTED: Relational database for route config
  Route config is 5 MB. Loading it from a database adds startup latency
  and creates a runtime dependency. Config is loaded once and cached.
  A simple file/config-store is sufficient.

REJECTED: Distributed cache (Redis) for rate limit counters
  Adds ~1ms per request (Redis RTT) to the hot path.
  Local counters with periodic sync achieve 90% accuracy at 0ms cost.
  The accuracy trade-off is acceptable; the latency trade-off is not.

REJECTED: Centralized log database (write-per-request)
  At 5M QPS: 5M writes/second to a database → Impossible.
  Buffered, batched log shipping to a streaming pipeline (Kafka)
  is the only viable approach at this scale.

REJECTED: In-gateway persistent storage (RocksDB, SQLite)
  Gateway must be stateless and disposable.
  Any persistent state creates: Recovery complexity, data migration
  during scaling, backup requirements.
  All gateway state is either derived or ephemeral.
```

---

# Part 8: Consistency, Concurrency & Ordering

## Strong vs Eventual Consistency

```
ROUTE CONFIG: Eventual consistency (< 10 second convergence)
  All gateway instances must have the SAME routing config.
  New config pushes to all instances within 10 seconds.
  During the window: Different instances may have different routes.
  
  IMPACT OF INCONSISTENCY:
  User hits GW-1 (old config): Request goes to service-v1
  User hits GW-2 (new config): Request goes to service-v2
  Duration: 10 seconds (brief, infrequent)
  
  IS THIS ACCEPTABLE? Yes.
  Route changes happen a few times per day.
  10-second inconsistency during a deliberate change is tolerable.
  
  WOULD NOT BE ACCEPTABLE:
  Permanent divergence (GW-1 never gets new config).
  → Config push includes version number + reconciliation.
  → If any instance is > 60 seconds behind → Alert.

API KEY REVOCATION PROPAGATION:
  API key revoked (compromised/abused) → Must stop working immediately.
  But: API key cache has 5-minute TTL → Revoked key works for up to 5 minutes.
  
  5 minutes of continued access with a compromised key is UNACCEPTABLE
  for high-security APIs (payment, admin).
  
  SOLUTION: Revocation list with push invalidation.
  When a key is revoked:
  1. Key marked as revoked in key store (immediate)
  2. Revocation event pushed to all gateway instances (< 5 seconds)
  3. Gateway checks: Is key in revocation list? → Reject immediately
  
  FUNCTION verify_api_key_with_revocation(key):
    // Check revocation list FIRST (fast, in-memory set)
    IF revocation_list.contains(hash(key)):
      RETURN 401 ("API key revoked")
    
    // Then check cache (as before)
    metadata = api_key_cache.get(key)
    ...normal flow...
  
  Revocation list size: ~10,000 entries (recently revoked keys)
  Memory: ~100 KB (trivial)
  Keys removed from revocation list after 24 hours (cache TTL long expired)
  
  Trade-off: 5-second revocation delay (push latency) vs 5-minute delay (cache TTL).
  5 seconds is acceptable for security-critical operations.
  
  Staff insight: Cache invalidation is one of the two hard problems
  in computer science. For API keys, a revocation list (blocklist)
  is simpler and more reliable than trying to invalidate cached entries.
  The blocklist is checked before the cache, so revocation always wins.

RATE LIMITING: Approximate consistency
  Each instance tracks its own counters.
  Global sync every 1 second.
  A user at exactly the rate limit may get 5-10% more requests through.
  
  This is a DELIBERATE TRADE-OFF:
  Perfect accuracy requires per-request consensus → 1-2ms per request.
  Approximate accuracy requires no consensus → 0ms per request.
  
  Staff insight: Users NEVER notice 5% over-admission.
  Users ALWAYS notice 2ms added latency (at P99, across all requests).

CIRCUIT BREAKER STATE: Per-instance, NOT globally consistent
  Each instance independently tracks backend health.
  Instance GW-1 may open circuit (it saw 50% failures).
  Instance GW-2 may keep circuit closed (its requests succeeded).
  
  This is CORRECT behavior: Backend may be partially healthy.
  Per-instance circuit breakers provide finer-grained health signals.
  
  EXCEPTION: Manual circuit override ("force open for all instances")
  is pushed via config and IS consistent across all instances.
```

## Race Conditions

```
RACE 1: Route config update during request processing
  Request arrives → Begins processing with config V1
  Config V2 arrives → Route table swapped
  Request still processing → Uses V1 references
  
  Resolution: Read-copy-update (RCU).
  Old route table is referenced by in-flight requests (reference counting).
  New route table is used by new requests.
  Old table freed when last in-flight request completes.
  → No lock needed, no race condition possible.

RACE 2: Rate limit counter update from multiple threads
  Thread A: Read counter → 99 tokens
  Thread B: Read counter → 99 tokens
  Thread A: Decrement → 98 tokens
  Thread B: Decrement → 98 tokens (should be 97)
  
  Resolution: Atomic operations.
  Token bucket uses atomic compare-and-swap (CAS):
  → Thread A: CAS(99 → 98) → Success
  → Thread B: CAS(99 → 98) → Fail → Retry → CAS(98 → 97) → Success
  
  At 5M QPS on 20 instances: Contention is LOW.
  Each instance handles ~250K QPS across ~16 cores → ~16K QPS per core.
  Probability of CAS contention on same counter: < 0.1%.

RACE 3: Health check update while load balancing
  Health checker: Marks instance as unhealthy → Removes from pool
  Load balancer: Already selected that instance → Sends request
  Request: Goes to unhealthy instance → Likely fails → Retried
  
  Resolution: Acceptable. This race exists for < 1 second.
  The retry covers the race. The cost of locking (to prevent the race)
  exceeds the cost of occasional retry to an unhealthy instance.

RACE 4: Certificate rotation during TLS handshake
  Handshake starts with cert V1
  Cert V2 loaded mid-handshake
  → No impact: Handshake uses the cert that was loaded at handshake start.
  New connections use V2. In-flight handshakes complete with V1.
```

## Idempotency

```
GATEWAY RETRIES AND IDEMPOTENCY:
  Gateway retries failed requests to a different backend instance.
  
  SAFE TO RETRY:
  → GET requests (inherently idempotent)
  → HEAD requests
  → Requests that returned connection error (never reached backend)
  → Requests that returned 502/503/504 (backend didn't process)
  
  NOT SAFE TO RETRY:
  → POST requests (may not be idempotent)
  → Requests that returned 500 (backend may have partially processed)
  → Requests with non-idempotent side effects
  
  IDEMPOTENCY ENFORCEMENT:
  Gateway does NOT determine idempotency. Backend declares it:
  → Route config: retry_policy: {on: [502, 503], methods: ["GET", "POST"]}
  → Backend team explicitly marks POST as retryable (if they use idempotency keys)
  
  DEFAULT: Retry only safe methods (GET, HEAD, OPTIONS).
  Override per-route for backends that support idempotent writes.

CLIENT RETRY HANDLING:
  Client sends request → Gateway sends to backend → Backend slow → Client gives up
  → Client retries (new request) → Gateway sends to (potentially different) backend
  → Now TWO requests are in-flight for the same operation
  
  Gateway does NOT deduplicate. This is the BACKEND's responsibility
  (via idempotency keys). Gateway cannot deduplicate without state
  (remembering all recent requests), which violates statelessness.
```

## Ordering Guarantees

```
REQUEST ORDERING: NONE
  Gateway provides NO ordering guarantees between requests.
  
  Client sends request A, then request B.
  Request A may arrive at gateway before B (network ordering).
  But: Request A may be slower to process (different backend, slower instance).
  → Request B may complete before request A.
  
  This is CORRECT and EXPECTED in an HTTP-based system.
  If ordering matters: Client must use sequence numbers or server-assigned IDs.
  Gateway is a request-level router, not a message queue.

CONFIG UPDATE ORDERING: SEQUENTIAL, VERSIONED
  Config updates are version-numbered.
  Gateway applies V1, then V2, then V3 (never out of order).
  If V3 arrives before V2 (network reorder): V3 is held until V2 arrives.
  
  WHY: Applying config out of order could:
  → Add a route (V2) and then apply the state before it was added (V1)
  → Canary weight goes 10% → 50% → 10% instead of 10% → 50% → 100%
```

## Clock Assumptions

```
GATEWAY CLOCK:
  Used for: Access log timestamps, rate limit window boundaries,
            TLS certificate expiry checking, circuit breaker timing.
  
  Requirement: Synchronized via NTP to within 1 second.
  Impact of clock skew:
  → Rate limit window shifts → Slightly more/fewer requests allowed
  → Access log timestamps off by 1 second → Acceptable for analysis
  → Circuit breaker timing off → Open/half-open transitions shift by 1 second
  
  NO CROSS-INSTANCE CLOCK COORDINATION NEEDED:
  → Rate limiting uses local clocks (synced periodically, not per-request)
  → Circuit breakers use per-instance clocks (independent evaluation)
  → Access logs use per-instance clocks (log analysis tolerates 1s skew)

TOKEN EXPIRY:
  JWT token has exp claim set by auth server's clock.
  Gateway checks: token.exp < gateway_clock()
  If auth server clock is 5 seconds ahead:
  → Tokens expire 5 seconds "early" from the auth server's perspective.
  → Mitigation: Accept tokens within 30-second grace period of expiry.
  → exp + 30 seconds < now() → Actually expired.
  → This grace period covers all reasonable clock skew.
```

---

# Part 9: Failure Modes & Degradation

## Failure Mode 1: Gateway Instance Crash

```
SCENARIO: One of 20 gateway instances crashes (OOM, kernel panic, hardware failure).

IMPACT:
  ~250,000 active connections lost instantly.
  ~5% of total traffic affected.
  
TIMELINE:
  T+0:    Gateway instance crashes
  T+0:    All connections on that instance receive TCP RST
  T+1s:   L4 load balancer detects health check failure
  T+2s:   L4 LB removes instance from rotation
  T+2s:   New connections go to remaining 19 instances
  T+3s:   Clients with dropped connections retry (most HTTP clients auto-retry)
  T+5s:   All traffic redistributed, no user-visible impact (if clients retry)
  
  Impact duration: 2-5 seconds of elevated errors for ~5% of clients.
  
  If clients DON'T auto-retry (non-idempotent requests):
  → Some requests are lost → Client shows error → User retries manually
  → This is the EXPECTED failure mode for non-idempotent operations

BLAST RADIUS:
  1/20 instances = 5% of traffic. 
  Remaining instances absorb the load:
  → Each instance goes from 250K QPS to 263K QPS (+5%)
  → This is within normal headroom (20% headroom per instance)
  → No cascading failure.

PREVENTION:
  → N+2 redundancy: Can lose 2 instances and still serve peak traffic
  → Auto-restart: Crashed instance replaced within 60 seconds
  → No state to recover: New instance loads config, starts serving
```

## Failure Mode 1b: L4 Load Balancer Failure

```
SCENARIO: The L4 load balancer in front of the gateway fleet fails
or misconfigures (e.g., health check misconfigured, all backends marked down).

WHY THIS IS DISTINCT FROM GATEWAY FAILURE:
  Gateway instance crash → LB routes around it → Automatic.
  L4 LB itself fails → NO traffic reaches ANY gateway instance → Total outage.
  The L4 LB is the ONE component that cannot be load-balanced by another LB.
  It's turtles all the way down—someone must be the bottom.

IMPACT:
  All traffic to the region fails.
  Backend services: UNAFFECTED (they don't know about the gateway).
  Internal service-to-service: UNAFFECTED (doesn't go through public gateway).
  
TIMELINE:
  T+0:    L4 LB health check misconfigured → All gateways marked "down"
  T+0:    L4 LB stops forwarding traffic
  T+1s:   100% of external traffic fails (connection refused)
  T+2s:   External monitoring detects: "API unreachable from all probe points"
  T+5s:   Alert fires: "External availability = 0%"
  T+10s:  On-call sees alert, checks gateway health → Gateways are healthy
  T+15s:  On-call suspects LB → Checks LB health check config
  T+20s:  Identifies: Health check path changed from /healthz to /health
          (yesterday's infra deploy), gateways return 404 for /health
  T+22s:  Fixes health check path → LB marks gateways healthy
  T+25s:  Traffic resumes
  
  TOTAL IMPACT: ~25 seconds of total external outage
  ROOT CAUSE: LB config change, not gateway or backend failure

MITIGATION:
  1. L4 LB redundancy: Multi-AZ LB (cloud-managed LBs provide this).
  2. LB health check uses multiple paths:
     Primary: /healthz → If 404, try /ready → If 404, try TCP connect
     → Any one succeeding = instance is healthy
  3. LB config changes go through same canary process as gateway config.
  4. External synthetic monitoring: Independent probes that test the FULL
     path (client → LB → gateway → backend) every 10 seconds.
     This detects LB failure that internal monitoring misses.
  
  REAL-WORLD APPLICATION:
  A major cloud provider's outage was caused by an LB health check change
  that used a path returning 200 in staging but 404 in production.
  The LB drained all backend instances. The fix took 45 minutes because
  the engineer who made the change was asleep and the change wasn't audited.
  
  Staff insight: The L4 LB is the most dangerous single point of failure
  because it's INVISIBLE. When it works, nobody thinks about it. When
  it fails, nothing works and the gateway team investigates their own
  systems first (wasting 10-15 minutes) before looking at the LB.
  ALWAYS check the LB first when "everything is down but nothing changed."
```

## Failure Mode 2: Backend Service Unavailable

```
SCENARIO: user-service (critical backend) becomes completely unavailable.

IMPACT:
  All requests to /api/v2/users/* fail.
  Other services: UNAFFECTED.
  Gateway: UNAFFECTED (continues routing to other services).

TIMELINE:
  T+0:    user-service instances start failing (returning 5xx)
  T+5s:   Gateway's passive health check detects: >50% failure rate
  T+5s:   Circuit breaker opens for user-service
  T+6s:   All requests to user-service → 503 (circuit open)
           Response header: Retry-After: 30
  T+35s:  Circuit transitions to half-open (try 5 probe requests)
  T+36s:  Probes fail → Circuit re-opens
  T+2min: user-service recovered
  T+2.5min: Half-open probes succeed → Circuit closes
  T+2.5min: Normal traffic resumes to user-service

DEGRADED RESPONSE OPTIONS:
  Option A: Return 503 (default)
    "Service temporarily unavailable. Please retry."
  
  Option B: Return cached response (if available)
    If user-service has a read cache, gateway returns stale data
    with header: X-Cache-Status: stale-while-error
    User gets data (possibly stale) instead of error.
  
  Option C: Return partial response
    If the page has multiple backend calls (user + orders + recommendations),
    return the parts that succeeded, mark user data as unavailable.
    This requires BFF/aggregation layer support, not gateway alone.

STAFF INSIGHT:
  The gateway's job is to CONTAIN the failure to user-service.
  Without circuit breaker: Gateway keeps sending requests to failing backend
  → Connection pool fills up → Gateway threads blocked waiting for timeouts
  → Gateway becomes slow for ALL services → Cascading failure
  
  Circuit breaker: "Stop trying to reach a dead service."
  This is the single most important failure isolation mechanism in the gateway.
```

## Failure Mode 3: Slow Backend (Partial Degradation)

```
SCENARIO: order-service responds in 2 seconds instead of 200ms 
(10× slower than normal, but NOT failing).

WHY THIS IS WORSE THAN TOTAL FAILURE:
  Total failure → Circuit breaker opens → Fast 503 → Client retries
  Slow backend → Requests succeed (eventually) → No circuit breaker trigger
  → Gateway threads tied up waiting → Connection pool fills up
  → Other services affected (shared connection pool and thread pool)
  → Slow cascade: Everything gets slow, nothing clearly fails

TIMELINE:
  T+0:    order-service latency increases from 200ms to 2000ms
  T+10s:  Gateway connection pool to order-service filling up
          (100 connections × 2s hold time = 50 QPS capacity, was 500 QPS)
  T+15s:  Connection pool full → New requests queued
  T+20s:  Request queue fills → Requests start timing out at gateway
  T+20s:  Users see: "Request timeout" for order endpoints
  T+25s:  IF connection pools are SHARED → Other services affected too
  T+30s:  Gateway CPU increases (many in-flight requests consuming memory)
  T+60s:  Alert: "order-service P99 > 2000ms"
  T+90s:  On-call investigates

MITIGATION LAYERS:
  1. PER-BACKEND CONNECTION POOL:
     Each backend has its OWN connection pool.
     order-service's pool fills up → Only order-service affected.
     user-service, search-service: Unaffected.
     → CRITICAL: Never share connection pools across backends.
  
  2. BACKEND TIMEOUT:
     Route config: timeout: 1000ms (for order-service)
     If response takes > 1000ms → Gateway returns 504 → Frees connection
     
     Staff insight: The timeout MUST be set by the GATEWAY, not the backend.
     If the backend sets its own timeout, a slow backend never reaches it.
     The gateway timeout is the EXTERNAL contract with the client.
  
  3. ADAPTIVE CIRCUIT BREAKER (latency-based):
     Standard circuit breaker: Opens on ERROR RATE > 50%
     Latency-based circuit breaker: Opens on P99 > 3× NORMAL P99
     
     order-service normal P99: 200ms
     Current P99: 2000ms (10× normal)
     → Latency-based circuit breaker opens → Shed load proactively
     → This catches slow degradation that error-based breaker misses

  4. REQUEST TIMEOUT WITH BUDGET:
     Request enters gateway with total budget: 5000ms
     TLS + auth + rate limit: Consumes 100ms → Budget remaining: 4900ms
     Backend timeout: min(route_timeout, remaining_budget)
     
     This prevents a slow gateway pipeline from sending requests
     with no remaining time budget to the backend.
```

## Failure Mode 3b: Gateway OOM (Memory Exhaustion)

```
SCENARIO: Gateway instance runs out of memory and is killed by the OS (OOM killer).

CAUSES:
  1. Large request body accumulation:
     Client sends 100MB POST body (file upload).
     Gateway buffers in memory before forwarding.
     100 concurrent large uploads × 100MB = 10GB → OOM
  
  2. Connection tracking leak:
     Bug in connection cleanup: Closed connections not freed.
     Over hours: Memory grows linearly → Eventually OOM.
  
  3. Response buffering for slow clients:
     Backend sends 50MB response instantly.
     Client reads slowly (mobile on 3G).
     Gateway buffers response → 10,000 slow clients × 50MB = 500GB → OOM
  
  4. Rate limit counter growth:
     10M unique users × 4 rate limit buckets × 16 bytes = 640MB
     If no eviction: Grows monotonically → Eventually OOM

WHY THIS IS INSIDIOUS:
  Unlike a crash (instant), OOM builds slowly:
  → Memory usage 70%... 80%... 90%... GC thrashing... 95%... OOM kill
  → During GC thrashing: Gateway latency spikes to 100ms+
  → Latency spike looks like "gateway is slow" not "gateway is dying"
  → Engineers investigate backend latency, not gateway memory
  → By the time someone checks gateway memory → Instance is dead

TIMELINE:
  T+0:    Viral event causes 10× traffic spike (many new unique users)
  T+5min: Rate limit counter memory: 640MB → 2GB (10× unique users)
  T+10min: Gateway heap: 3.5GB / 4GB limit
  T+12min: GC frequency increases: 10ms pauses every 500ms
  T+14min: Gateway P99 latency: 150µs → 50ms (GC overhead)
  T+15min: Alert: "Gateway P99 > 50ms"
  T+16min: GC cannot free enough memory: Continuous GC
  T+17min: OOM killer terminates gateway instance
  T+17s:  LB health check fails → Redistributes traffic → Surviving instances
  T+18min: Surviving instances under MORE load → Cascading OOM risk

MITIGATION:
  1. REQUEST BODY SIZE LIMIT:
     Gateway rejects requests > 10MB at the TCP layer (before buffering).
     Large uploads go to a dedicated upload service (not through gateway).
  
  2. RESPONSE STREAMING (never buffer full response):
     FUNCTION proxy_response(backend_conn, client_conn):
       WHILE chunk = backend_conn.read_chunk(64_KB):
         client_conn.write(chunk)
         // Memory used: 64KB at any time (not full response size)
     
     If client is slow: Apply backpressure to backend via flow control.
     If backpressure exceeds timeout: Close connection (free resources).
  
  3. RATE LIMIT COUNTER EVICTION:
     Use LRU eviction with a max entry count.
     Max entries: 5M (5M × 16 bytes = 80MB → Bounded)
     If user not seen in 5 minutes: Evict counter.
     Evicted user: Next request gets full quota (slightly over-admits)
     → Acceptable: Evicted users are low-frequency, don't hit limits.
  
  4. MEMORY PRESSURE ALERTING:
     Alert at 70% heap: "Gateway memory pressure increasing"
     Alert at 85% heap: "Gateway memory critical, investigate"
     Alert at 90% heap: Gateway starts aggressive load shedding
     → Shed Tier 3 (anonymous) traffic to reduce memory pressure
     → This is a LAST RESORT before OOM kills the process

  Staff insight: Memory is the gateway's most scarce resource.
  CPU can be shed (reject requests). Bandwidth can be shed (rate limit).
  Memory is COMMITTED the moment you accept a connection.
  The golden rule: Never buffer unbounded data. Stream everything.
```

## Failure Mode 4: DDoS Attack

```
SCENARIO: 100× normal traffic volume (500M QPS) from a botnet.

IMPACT:
  Without protection: Gateway overwhelmed → ALL traffic fails
  With protection: Legitimate traffic slightly degraded, attack absorbed

DEFENSE LAYERS:
  
  Layer 0: DNS/CDN (Cloudflare, AWS Shield) — NOT our system
    Absorbs volumetric attacks (>100 Gbps)
    Filters known-bad IPs, botnets
    Challenge-response for suspicious traffic (CAPTCHAs)
    
  Layer 1: L4 RATE LIMITING (kernel/NIC level)
    SYN cookies: Prevent SYN flood exhausting connection state
    Connection rate limit per IP: Max 100 new connections/second per IP
    This happens BEFORE TLS (no CPU-expensive handshake for bad traffic)
    
  Layer 2: GATEWAY-LEVEL DEFENSES
    IP-based rate limiting: Max 1000 requests/second per IP
    Request parsing limits: Reject oversized requests immediately
    Slowloris defense: Idle connection timeout (10 seconds)
    
  Layer 3: APPLICATION-LEVEL DEFENSES
    Per-user rate limiting: (already covered)
    CAPTCHA challenge: For suspicious patterns (high request rate + no valid token)
    Bot detection: Request fingerprinting (TLS fingerprint, header patterns)

RESOURCE ALLOCATION DURING ATTACK:
  Problem: Attack traffic consumes CPU (TLS, parsing, rate limit check)
           even though it's ultimately rejected.
  
  At 500M QPS: Even rejecting each request in 10µs = 5,000 CPU-seconds/second
  → Need 5,000 CPU cores just for rejections
  
  Mitigation: REJECT AS EARLY AS POSSIBLE
  → IP blocklist check at L4 (kernel): ~1µs per packet
  → Don't even accept the TCP connection for known-bad IPs
  → This is 10× cheaper than rejecting at application layer
  
  Staff insight: During a DDoS, the gateway's job is to PRIORITIZE
  legitimate traffic, not to process all traffic fairly. If you can
  identify the attack traffic (IP ranges, patterns), drop it at the
  lowest layer possible. Every CPU cycle spent on attack traffic is
  stolen from legitimate users.
```

## Failure Mode 4b: Poison Request (Gateway Crash via Malformed Input)

```
SCENARIO: A specially crafted request triggers a bug in the gateway's
request parser or a ReDoS (Regular Expression Denial of Service)
in a header matching rule.

WHY THIS IS DIFFERENT FROM DDoS:
  DDoS: High volume of VALID requests overwhelm capacity.
  Poison request: SINGLE malformed request crashes/hangs the gateway.
  Volume doesn't matter. One request can kill one instance.
  
  If the attacker sends the poison request to all 20 instances
  (via sequential connections): All 20 crash → Total outage.

EXAMPLES:
  1. REGEX DoS:
     Route config has header matcher: regex("^(a+)+$")
     Attacker sends: X-Custom: "aaaaaaaaaaaaaaaaaaaaaaaa!"
     → Regex engine enters exponential backtracking
     → Single request consumes 100% CPU for seconds
     → Gateway thread hung → No other requests processed on that thread
     → With enough threads hung: Gateway unresponsive
  
  2. HTTP PARSER BUG:
     Malformed HTTP/2 frame with invalid stream dependency
     → Parser crashes with unhandled exception
     → Gateway process dies → OOM or segfault
  
  3. HEADER BOMB:
     Request with 10,000 headers × 8KB each = 80MB in headers alone
     → Gateway allocates 80MB for header parsing → Memory exhaustion
     → Multiple such requests → OOM

TIMELINE:
  T+0:    Attacker sends crafted request to GW-1
  T+0.1s: GW-1 regex engine enters backtracking loop
  T+5s:   GW-1 request processing thread hung
  T+6s:   Attacker sends same request to GW-2 through GW-20
  T+10s:  All 20 instances have hung threads
  T+15s:  With enough threads hung: Gateway fleet unresponsive
  T+20s:  Health checks fail → LB stops sending traffic → Outage

MITIGATION:
  1. REQUEST LIMITS (enforced BEFORE parsing):
     Max header count: 100
     Max header size: 8 KB per header, 64 KB total
     Max URL length: 8 KB
     Max request body: 10 MB (for gateway-processed requests)
     These limits are enforced at the TCP read level, before any parsing.
  
  2. REGEX TIMEOUT:
     All regex evaluations have a timeout: 1ms
     IF regex_match(pattern, input, timeout=1_MS) == TIMEOUT:
       LOG.warn("Regex timeout for pattern on request {id}")
       RETURN default_match_result  // Fail-open or fail-closed per policy
     
     Alternative: Avoid regex entirely. Use compiled prefix/suffix matchers
     which are O(N) and cannot backtrack.
  
  3. REQUEST PROCESSING TIMEOUT:
     Every request has a total processing timeout: 30 seconds
     If any single phase (parsing, auth, routing) exceeds 1 second:
     → Kill the request → Return 408 (Request Timeout)
     → Log: "Request processing exceeded phase timeout"
  
  4. PROCESS ISOLATION (defense in depth):
     Gateway spawns N worker processes (not threads).
     If one worker crashes (segfault from parser bug):
     → Only that worker dies → Other workers continue serving
     → Supervisor restarts crashed worker in < 1 second
     → Impact: 1/N capacity loss for < 1 second
     
     This is the nginx model: Master process + worker processes.
     A bug that crashes a worker doesn't crash the master.

  Staff insight: Parser bugs and regex DoS are GUARANTEED to happen
  eventually. The question is not "will it happen" but "when it happens,
  does one request kill one thread, one process, or the entire fleet?"
  Defense in depth: Limits → Timeouts → Process isolation → Fleet redundancy.
```

## Failure Mode 5: Config Push of Bad Routes

```
SCENARIO: Route config update has a bug that sends ALL traffic to a
single backend (typo: /api/* → wrong-service instead of /api/v2/orders/* → order-service).

TIMELINE:
  T+0:    Bad route config pushed
  T+3s:   Propagated to all gateway instances
  T+3s:   All API traffic routed to wrong-service
  T+4s:   wrong-service overwhelmed → Returning 503
  T+5s:   Error rate spikes to ~100%
  T+6s:   Alert: "Error rate > 50% for all services"
  T+10s:  On-call sees: "Config changed 10 seconds ago"
  T+12s:  On-call clicks "rollback route config"
  T+15s:  Rollback propagated to all instances
  T+16s:  Normal routing restored
  
  TOTAL IMPACT: ~13 seconds of near-total outage

PREVENTION:
  1. ROUTE CONFIG VALIDATION:
     Before applying, validate:
     → No route conflicts (two rules matching same request)
     → Referenced backends exist in service registry
     → No "catch-all" rules that override more specific rules
     → Total traffic weight per backend doesn't exceed capacity
  
  2. CANARY ROUTE DEPLOYMENT:
     New route config applied to 1 gateway instance first.
     Compare: Error rate on canary vs control instances.
     If canary error rate > control + 1%: Reject config.
     
  3. ROUTE DIFF REVIEW:
     Config push shows diff: "This change affects 5 routes, redirecting
     ~30% of total traffic." Requires human approval for changes
     affecting > 10% of traffic.
  
  4. AUTOMATIC ROLLBACK:
     If global error rate increases > 5% within 30 seconds of config push:
     → Automatically revert to previous config version
     → Alert on-call: "Route config auto-rolled back due to error spike"
```

## Failure Mode 6: Retry Storm Amplification

```
SCENARIO: Backend returns 503 → Clients retry → Gateway retries →
Backend receives 3× (gateway retry) × 3× (client retry) = 9× normal traffic.

AMPLIFICATION CHAIN:
  Normal: 100K QPS to order-service
  Backend degrades → Returns 503 for 50% of requests
  Gateway retries: 50K × 2 retries = 100K additional QPS
  Client retries: (100K + 100K) × 2 retries = 400K additional QPS
  Total: 100K + 100K + 400K = 600K QPS (6× normal)
  
  Backend was struggling at 100K QPS → Now receiving 600K QPS → Total collapse

MITIGATION:
  1. GATEWAY RETRY BUDGET:
     Max retries: 2 (configurable per route)
     Retry only on: Connection error, 502, 503 (not 500)
     Backoff: 50ms, 100ms (exponential with jitter)
     Total retry budget per request: 200ms
     
     CRITICAL: Gateway sets Retry-After header in 503 responses.
     → Client respects Retry-After → Reduces client-side retry storm
  
  2. RETRY BUDGET PER BACKEND:
     Max 20% of requests to a backend can be retries.
     If retry_rate > 20% → Stop retrying → Return 503 immediately
     
     FUNCTION should_retry(backend):
       retry_rate = backend.retry_count / backend.total_count
       IF retry_rate > 0.20:
         RETURN false  // Too many retries, backend is overwhelmed
       RETURN true
  
  3. CLIENT BACKOFF SIGNALING:
     Gateway response: 503 with Retry-After: {seconds}
     Well-behaved clients: Wait {seconds} before retrying
     Badly-behaved clients: Ignored → Per-client rate limit catches them
  
  4. CIRCUIT BREAKER (discussed above):
     Opens at 50% error rate → Stops ALL traffic to backend
     This is the nuclear option but prevents total collapse.
```

## Failure Timeline Walkthrough

```
SCENARIO: Cascading failure from slow backend to gateway to all services

T+0:     Database serving order-service has a slow query
T+2s:    order-service P99 increases from 200ms to 5000ms
T+5s:    Gateway connection pool to order-service starts filling
T+10s:   Connection pool full (100 connections all blocked for 5s)
T+10s:   New order requests queued at gateway
T+15s:   Queue grows → Gateway memory pressure increases
T+20s:   Gateway thread pool saturating (threads blocked on order-service)
T+20s:   *** CRITICAL POINT ***
         IF connection pools are SHARED (bad design):
           → All services affected → Total platform degradation
         IF connection pools are PER-BACKEND (good design):
           → Only order-service affected → Other services fine
T+25s:   Latency-based circuit breaker triggers (P99 > 3× normal)
T+26s:   Circuit opens → order-service gets 503 immediately
T+26s:   Gateway connection pool drains (blocked requests timeout)
T+30s:   Gateway resources freed → Other services return to normal
T+60s:   Circuit transitions to half-open → Sends 5 probes
T+61s:   Probes: 3/5 succeed in 200ms → Database query resolved
T+62s:   Circuit closes → Normal traffic resumes
T+65s:   Platform fully recovered

TOTAL IMPACT:
  order-service: ~55 seconds of degradation
  Other services (with per-backend pools): ~0 seconds of degradation
  Other services (with shared pools): ~25 seconds of degradation
  
  LESSON: Per-backend connection pools are the difference between
  "one service had a bad minute" and "total platform outage."
```

## On-Call Runbooks for the API Gateway

```
RUNBOOK 1: ELEVATED ERROR RATE (5xx > 1%)
  Alert: gateway_error_rate > 0.01 for 5 minutes
  
  Diagnosis:
  1. Which backend(s) are returning errors?
     → Check per-backend error rate dashboard
  2. Are errors from gateway itself or from backends?
     → 502: Gateway couldn't reach backend
     → 503: Circuit breaker open or backend rejected
     → 504: Backend timed out
  3. Is it ALL traffic or specific routes?
     → Per-route error rate → Specific backend issue
  4. Did a config change happen recently?
     → Check config change log (last 30 minutes)
  
  Resolution:
  → Backend issue: Escalate to backend team, consider circuit breaker
  → Config issue: Rollback config
  → Gateway issue: Check gateway logs, restart if necessary

RUNBOOK 2: ELEVATED LATENCY (P99 > 50ms gateway overhead)
  Alert: gateway_overhead_p99 > 50ms for 5 minutes
  
  Normal gateway overhead: < 5ms
  If > 50ms: Something is wrong WITH the gateway (not backends)
  
  Diagnosis:
  1. Check per-phase timing: TLS? Auth? Rate limiting? Route matching?
  2. Check CPU usage: > 80% → Need more instances
  3. Check connection pool utilization: > 90% → Slow backends
  4. Check GC pauses: > 10ms → Tune GC or increase memory
  
  Resolution:
  → High CPU: Scale out (add instances)
  → Connection pool full: Check which backend is slow → Timeout or circuit break
  → GC pause: Increase heap, tune GC, or switch to non-GC runtime

RUNBOOK 3: RATE LIMIT MISFIRING (legitimate users blocked)
  Alert: customer_complaint or rate_limit_false_positive_rate > 0.1%
  
  Diagnosis:
  1. Which rate limit tier is triggering? (Global? Per-user? Per-endpoint?)
  2. Is the user actually exceeding their quota?
  3. Is the rate limit config correct? (check recent config changes)
  4. Is distributed sync working? (check sync lag)
  
  Resolution:
  → Config wrong: Fix config (immediate via config push)
  → User exceeding quota: Increase quota (if justified) or inform user
  → Sync broken: Fix sync → Temporary over-admission (acceptable)
```

## Gateway Meta-Monitoring: Who Watches the Gateway

```
PROBLEM: The gateway is the primary source of observability for the platform.
It emits per-route latency, per-backend error rates, and access logs.
But what monitors the GATEWAY ITSELF?

If the gateway's metrics pipeline breaks, you lose visibility into
the health of every service simultaneously. If the gateway is degrading
but its own metrics aren't being collected, nobody knows until
users complain.

PRINCIPLE: Gateway health monitoring MUST NOT flow through the gateway.

MONITORING ARCHITECTURE:
  1. EXTERNAL SYNTHETIC PROBES:
     Independent monitoring service (NOT behind the gateway) sends
     test requests every 10 seconds through the FULL path:
     → DNS → L4 LB → Gateway → Test backend → Response → Verify
     
     This tests: DNS, LB, gateway, and backend connectivity.
     If probe fails: Alert immediately (doesn't depend on gateway metrics).
  
  2. GATEWAY-SIDE PUSH METRICS:
     Gateway pushes metrics directly to monitoring pipeline (Prometheus/StatsD).
     This does NOT go through the gateway itself.
     → gateway_requests_total (counter)
     → gateway_latency_histogram (per-route, per-backend)
     → gateway_error_rate (per-backend, per-status-code)
     → gateway_connection_pool_utilization (per-backend)
     → gateway_circuit_breaker_state (per-backend: closed/open/half-open)
     → gateway_memory_usage_bytes
     → gateway_cpu_usage_percent
     → gateway_active_connections
     → gateway_config_version (to detect config divergence across instances)
  
  3. CROSS-INSTANCE HEALTH COMPARISON:
     Each gateway instance reports its config_version and request_count.
     Central dashboard compares: "All instances should have similar
     request rates and the same config version."
     
     Anomaly: GW-5 has 50% lower request rate than others
     → Possible: LB misconfiguration (not routing to GW-5)
     → Possible: GW-5 is unhealthy and LB reduced its weight
     → Investigate immediately
     
     Anomaly: GW-12 has config_version 41, others have 42
     → Config push failed for GW-12 → Stale routes → Investigate

  4. L4 LB HEALTH CHECK AS META-MONITOR:
     LB health check hits gateway /healthz every 5 seconds.
     /healthz returns 200 ONLY if:
     → Route config loaded (version > 0)
     → At least 1 backend reachable (connectivity test)
     → Memory usage < 90% (not in danger zone)
     → CPU usage < 95% (not saturated)
     
     IF any condition fails → /healthz returns 503 → LB drains instance
     → This is SELF-HEALING: Unhealthy gateway automatically removed

ALERTING RULES (STATIC, not gateway-config-driven):
  CRITICAL: external_probe_failure for 3 consecutive checks (30 seconds)
  CRITICAL: gateway_instance_count < expected - 2 for 2 minutes
  CRITICAL: gateway_config_version divergence across instances > 60 seconds
  WARNING:  gateway_memory_usage > 70% for 5 minutes
  WARNING:  gateway_cpu_usage > 80% for 5 minutes
  WARNING:  gateway_error_rate > 1% for any backend for 5 minutes

Staff insight: The most dangerous gateway outage is the one where
the gateway is degrading but its metrics look fine because the
metrics pipeline is also degrading. External synthetic probes are
the ONLY reliable way to detect this. They're the "canary in the
coal mine" for the entire observability stack.
```

---

# Part 10: Performance Optimization & Hot Paths

## Critical Paths

```
CRITICAL PATH 1: Request routing (per-request, synchronous)
  Budget: < 5µs
  Implementation: Compiled prefix trie
  Optimization: Pre-compiled at config load time, not per-request
  
  WHY THIS IS CRITICAL:
  5M QPS × 5µs = 25 CPU-seconds/second just for routing
  If routing takes 50µs: 250 CPU-seconds/second → 16 CPU cores just for routing
  
  Route matching MUST be O(path_depth), not O(number_of_routes).
  With 2,000 routes and a linear scan: 2000 × 5M = 10 billion comparisons/second

CRITICAL PATH 2: JWT verification (per-request, synchronous)
  Budget: < 50µs
  Implementation: Cached public key, local signature verification
  Optimization: HMAC verification is ~5µs. RSA/ECDSA is ~50µs.
  
  KEY INSIGHT: JWT verification speed depends on the signing algorithm.
  → HS256 (HMAC): ~5µs (symmetric key, fast)
  → RS256 (RSA): ~50µs (asymmetric, slow)
  → ES256 (ECDSA): ~30µs (asymmetric, moderate)
  
  If using RS256: 50µs × 5M QPS = 250 CPU-seconds/second
  Consider: HS256 for internal tokens (if key distribution is secure)
  Staff insight: Token algorithm choice affects gateway CPU budget significantly.

CRITICAL PATH 3: Rate limit check (per-request, synchronous)
  Budget: < 20µs
  Implementation: Local token bucket with atomic CAS
  Optimization: No external calls, no locks, per-core buckets if needed

CRITICAL PATH 4: Access logging (per-request, async)
  Budget: < 5µs (non-blocking write to ring buffer)
  MUST be asynchronous: Logging NEVER blocks request processing.
  If log buffer is full: Drop log entry (never wait).
```

## Caching Strategies

```
CACHE 1: JWT public key cache
  What: Public keys for JWT verification
  TTL: 24 hours (background refresh every 5 minutes)
  Size: ~100 KB (a few issuers, each with a few keys)
  Miss penalty: 50-100ms (HTTP fetch from JWKS endpoint)
  Hit rate: > 99.999% (keys change very rarely)

CACHE 2: API key cache
  What: API key → metadata mapping
  TTL: 5 minutes
  Size: ~100 MB (100K keys × 1KB each)
  Miss penalty: 5-10ms (lookup from key store)
  Hit rate: > 99.9% (active keys are repeatedly used)

CACHE 3: Backend DNS resolution cache
  What: service_name.internal → IP addresses
  TTL: 30 seconds (short TTL for dynamic environments)
  Background refresh: At 80% of TTL (avoid stale DNS at expiry)
  Miss penalty: 1-5ms (DNS query)
  Hit rate: > 99.99%

CACHE 4: Route config (in-memory, complete copy)
  Not a traditional cache—the entire route config is in memory.
  "Miss" = config not loaded → Gateway refuses to start.
  Size: ~5 MB (all routes compiled into trie)

EDGE RESPONSE CACHE (optional, for read-heavy APIs):
  What: HTTP response from backends, keyed by (path, query, user_tier)
  TTL: Route-configurable (e.g., /api/v2/catalog: 60 seconds)
  Size: 1-10 GB per gateway instance
  Miss penalty: Full backend round-trip (50-500ms)
  Hit rate: Varies (0% for user-specific, 80% for catalog-like data)
  
  WHY NOT CACHE EVERYTHING:
  → User-specific responses: Cannot cache (different per user)
  → Write endpoints: Must not cache (stale data is dangerous)
  → Large responses: Memory cost exceeds benefit
  
  Staff insight: Edge caching in the gateway is ONLY worth it for
  highly-read, shared, tolerate-staleness endpoints. For most APIs,
  the backends should handle their own caching.
```

## Precomputation vs Runtime Work

```
PRECOMPUTED (at config load time, not per request):
  ✓ Route trie compilation: Routes → Trie (once per config change)
  ✓ Regex compilation: Header matchers → Compiled regex
  ✓ Rate limit bucket allocation: Pre-create buckets for known users
  ✓ Connection pool warm-up: Pre-establish connections to backends
  ✓ TLS session ticket key distribution: Distribute before clients connect

RUNTIME (per request, cannot precompute):
  ✗ JWT signature verification (token is different each request)
  ✗ Token bucket decrement (depends on request arrival time)
  ✗ Load balancing decision (depends on current instance load)
  ✗ Circuit breaker evaluation (depends on recent error counts)
  
  Staff principle: EVERYTHING that can be precomputed, SHOULD be.
  The per-request budget is 100-150µs. Every microsecond counts.
  Moving 10µs of work from per-request to per-config-change saves:
  10µs × 5M QPS = 50 CPU-seconds/second → 3 CPU cores saved.
```

## Backpressure

```
BACKPRESSURE SCENARIO: Backend slower than expected

MECHANISM 1: Connection pool as backpressure signal
  Connection pool fills up → No more connections available
  → New requests queue → Queue has bounded size
  → Queue full → Return 503 immediately
  
  This naturally rate-limits traffic to slow backends without
  explicit coordination. The pool size IS the concurrency limit.

MECHANISM 2: Request queue with timeout
  When connection pool is full: Queue request for up to 500ms.
  If connection becomes available: Process request.
  If timeout: Return 504 (Gateway Timeout).
  
  Queue size: 1000 requests per backend.
  Beyond 1000: Immediate 503 (no queueing).

MECHANISM 3: HTTP/2 flow control
  For HTTP/2 backends: Use flow control windows.
  If backend is slow to consume: Flow control window shrinks.
  Gateway naturally sends less data → Backpressure without rejection.

WHAT THE GATEWAY NEVER DOES:
  ✗ Buffer unlimited requests in memory (OOM risk)
  ✗ Wait indefinitely for backend (thread exhaustion)
  ✗ Retry infinitely (amplification risk)
  
  Every waiting operation has a BOUNDED timeout and BOUNDED queue depth.
```

## Load Shedding

```
WHEN TO SHED LOAD:
  Gateway CPU > 80% → Start shedding lowest-priority requests
  
PRIORITY TIERS:
  Tier 1 (NEVER shed): Health checks, admin/ops requests
  Tier 2 (shed last): Authenticated user requests (paying customers)
  Tier 3 (shed first): Anonymous requests, bot traffic, unauthenticated
  
SHEDDING MECHANISM:
  FUNCTION should_admit(request, current_load):
    priority = classify_priority(request)
    
    IF current_load < 0.7:
      RETURN ADMIT  // Normal operation, admit all
    
    IF current_load < 0.8:
      IF priority == TIER_3:
        // Probabilistic shed: Higher load → More shedding
        shed_probability = (current_load - 0.7) / 0.1  // 0% at 0.7, 100% at 0.8
        RETURN random() > shed_probability ? ADMIT : SHED
      RETURN ADMIT
    
    IF current_load < 0.95:
      IF priority >= TIER_3: RETURN SHED
      IF priority == TIER_2:
        shed_probability = (current_load - 0.8) / 0.15
        RETURN random() > shed_probability ? ADMIT : SHED
      RETURN ADMIT
    
    // current_load >= 0.95: EMERGENCY
    IF priority >= TIER_2: RETURN SHED
    RETURN ADMIT  // Only Tier 1 admitted

SHEDDING RESPONSE:
  HTTP 503 with:
  Retry-After: {suggested_seconds}
  X-Load-Shed: true
  X-Priority: {tier}
  
  This tells well-behaved clients to back off and helps debugging.
```

## Why Some Optimizations Are Intentionally NOT Done

```
NOT DONE 1: Response body caching for all endpoints
  WHY NOT: Most responses are user-specific → Cache hit rate near 0%
  Memory cost: 10GB per instance × 20 instances = 200GB just for cache
  Benefit: Minimal (< 5% cache hit rate for most APIs)
  When to reconsider: If a specific endpoint has > 50% cache hit rate

NOT DONE 2: Request body compression/decompression at gateway
  WHY NOT: Gateway would need to decompress, inspect, recompress
  CPU cost: 50-100µs per request for gzip
  Benefit: Minimal (saves bandwidth between gateway and backend, same datacenter)
  When to reconsider: If backends are in a different region from gateway

NOT DONE 3: Pre-warming rate limit counters from historical data
  WHY NOT: Rate limit counters rebuild from live traffic in < 60 seconds
  Complexity: Need to load millions of counters from a store on restart
  Benefit: 60 seconds of slightly inaccurate rate limiting
  Risk: Loading bad historical data → Incorrect rate limiting
  
NOT DONE 4: Predictive auto-scaling based on traffic patterns
  WHY NOT: Reactive auto-scaling (CPU threshold) is simpler and sufficient
  Complexity: ML model for traffic prediction, false positive handling
  Benefit: ~30 seconds faster scaling (prediction vs reaction)
  Risk: False predictions → Unnecessary scaling → Cost waste
```

---

# Part 11: Cost & Efficiency

## Major Cost Drivers

```
COST DRIVER 1: Compute (CPU for request processing)
  Gateway instances: Primarily CPU-bound (TLS, auth, routing)
  
  At 5M QPS with 150µs/request:
  → 750 CPU-seconds/second → ~50 vCPUs minimum
  → With headroom (30%): ~65 vCPUs
  → 20 instances × 4 vCPUs each = 80 vCPUs → Sufficient
  
  Monthly cost (c5.xlarge equivalent): 20 × $150/month = $3,000/month
  
  KEY INSIGHT: TLS is the #1 CPU consumer.
  TLS handshake: ~1ms of CPU time
  At 100K new connections/second: 100 CPU-seconds/second for TLS alone
  → This is why HTTP/2 connection reuse matters enormously

COST DRIVER 2: Bandwidth
  Outbound: 80 Gbps (responses to clients)
  Cloud egress pricing: ~$0.05/GB
  Monthly: 80 Gbps × 3600 × 24 × 30 / 8 = ~25 PB/month
  Cost: 25 PB × $50/TB = ... astronomically expensive at cloud rates
  
  REALITY: At this scale, negotiate committed-use bandwidth discounts,
  or use interconnect/CDN to dramatically reduce egress costs.
  Typical negotiated rate: $0.01/GB → $250K/month for bandwidth.
  
  Staff insight: For a gateway at scale, BANDWIDTH is the dominant cost,
  not compute. Most engineering effort goes into compute optimization,
  but the bill is dominated by network egress.

COST DRIVER 3: Log storage and processing
  5M QPS × 500 bytes/log = 2.5 GB/s of log data
  Monthly: ~6.5 PB of raw logs (before compression)
  Compressed (~5:1): ~1.3 PB/month
  Storage cost: ~$26K/month at $0.02/GB
  
  Log processing (Kafka + indexing): ~$15K/month
  
  Total observability cost: ~$41K/month

COST DRIVER 4: SSL/TLS certificates
  Free (Let's Encrypt) or $0 (internal PKI)
  Certificate management tooling: Negligible
```

## TLS CPU Cost Breakdown (The Hidden Dominant Cost)

```
TLS IS THE #1 CPU CONSUMER IN THE GATEWAY.
Everything else (auth, rate limit, routing) combined is < 30% of CPU.
TLS handshakes and bulk encryption consume > 70% of gateway CPU.

COST ANALYSIS:

  TLS HANDSHAKE (new connection):
    RSA-2048 key exchange: ~1ms of CPU time per handshake
    ECDHE-P256 key exchange: ~0.3ms of CPU time per handshake
    
    New connection rate: 100,000/second (conservative)
    RSA: 100,000 × 1ms = 100 CPU-seconds/second → 6.5 CPU cores
    ECDHE: 100,000 × 0.3ms = 30 CPU-seconds/second → 2 CPU cores
    
    SAVINGS FROM ECDHE OVER RSA: 4.5 CPU cores → ~$200/month
    Staff decision: ECDHE everywhere. RSA only for legacy compatibility.

  TLS BULK ENCRYPTION (data transfer):
    AES-256-GCM: ~1 GB/s per CPU core (with AES-NI hardware instructions)
    
    Throughput: 14 GB/s (inbound + outbound)
    CPU cost: 14 CPU cores for bulk encryption
    
    WITHOUT AES-NI: ~100 MB/s per core → 140 CPU cores → CATASTROPHIC
    AES-NI is non-negotiable. Gateway instances MUST have AES-NI support.

  SESSION RESUMPTION SAVINGS:
    Without resumption: 100% of connections do full handshake
    With resumption: ~95% resume, 5% full handshake
    CPU savings: 95% × 100K connections/s × 1ms = 95 CPU-seconds/second saved
    → Session ticket key sharing saves ~6 CPU cores → ~$250/month

  TOTAL TLS CPU BUDGET:
    Handshakes: 2 cores (ECDHE with session resumption)
    Bulk encryption: 14 cores (AES-256-GCM with AES-NI)
    Total: ~16 cores dedicated to TLS
    Non-TLS processing: ~4 cores
    Total: ~20 cores (matching our 20 × 1-core or 10 × 2-core instances)

  WHEN TO CONSIDER TLS OFFLOAD HARDWARE:
    At > 500K new connections/second: CPU-based TLS becomes expensive.
    Options:
    → SmartNICs with TLS offload (Mellanox, Intel QAT)
    → Dedicated TLS termination instances (optimized for handshakes)
    → Cloud LB TLS termination (offloads TLS to cloud infrastructure)
    
    Cost: SmartNIC adds ~$2K per instance → Only justified at > 1M connections/s
    
    Staff insight: Most organizations never need TLS offload hardware.
    The cost crossover point is ~500K new connections/second.
    Below that: CPU-based TLS with ECDHE + session resumption is sufficient.
    Above that: Evaluate offload hardware vs more instances (often more 
    instances wins on total cost of ownership).
```

## How Cost Scales with Traffic

```
LINEAR SCALING:
  Compute: Directly proportional to QPS
  2× QPS = 2× instances = 2× compute cost
  
  Bandwidth: Directly proportional to QPS × response size
  2× QPS = 2× bandwidth = 2× bandwidth cost
  
  Logs: Directly proportional to QPS
  2× QPS = 2× log volume = 2× log storage cost

SUB-LINEAR SCALING:
  Config management: Fixed cost regardless of QPS
  Service registry: Fixed cost (based on number of services, not QPS)
  Certificate management: Fixed cost (number of domains, not traffic)
  
  OPERATIONAL COST: Sub-linear
  1 on-call engineer can manage a gateway serving 1M QPS or 100M QPS.
  The complexity is similar; the scale is different.

COST PER REQUEST AT SCALE:
  1M QPS:  ~$0.10 per million requests (high per-unit cost, small scale)
  5M QPS:  ~$0.06 per million requests (economies of scale)
  20M QPS: ~$0.04 per million requests (bulk discounts, amortized fixed costs)
```

## Trade-offs Between Cost and Reliability

```
TRADE-OFF 1: Instance count vs availability
  Fewer instances: Cheaper, but less redundancy
  More instances: More expensive, but survives multiple failures
  
  Minimum for five-nines: N+2 (can lose 2 instances during peak)
  If peak needs 15 instances: Run 17 (2 spare) vs 20 (5 spare, safer)
  Cost difference: 3 instances × $150/month = $450/month
  
  Staff decision: Run 20. The $450/month buys safety margin for:
  → Rolling deploys (2 instances draining at a time)
  → Unexpected traffic spikes (20% headroom)
  → Instance hardware failures (N+2 covers simultaneous failures)

TRADE-OFF 2: Log completeness vs cost
  100% logging: $41K/month (full visibility, full cost)
  10% sampling: $4.1K/month (good visibility, 10× cheaper)
  1% sampling: $410/month (minimal visibility, 100× cheaper)
  
  Staff decision: 100% for errors, 10% for successes.
  Total cost: ~$8K/month (good compromise)
  Use sampled data for analytics, full errors for debugging.

TRADE-OFF 3: Multi-region vs single-region
  Single region: 20 instances, $3K/month compute
  Multi-region (3 regions): 60 instances, $9K/month compute
  Plus: Cross-region data transfer costs ($5K/month)
  
  Staff decision: Multi-region only if:
  → Users are global (latency matters)
  → Regulatory requirement (data residency)
  → Single-region failure tolerance required
```

## What Over-Engineering Looks Like

```
OVER-ENGINEERING 1: Per-request ML-based abuse detection
  "Use machine learning to detect abusive requests in real-time"
  Reality: ML inference adds 5-50ms per request
  This exceeds the entire gateway overhead budget.
  Better: Rule-based detection at gateway, ML offline for pattern analysis.

OVER-ENGINEERING 2: Exactly-once rate limiting across all instances
  "Distributed consensus for every rate limit check"
  Reality: Adds 1-2ms per request for consensus round-trip
  Better: Local approximate counters with periodic sync (±10% accuracy)

OVER-ENGINEERING 3: Full request/response transformation
  "Gateway should translate between REST and gRPC, aggregate multiple backends"
  Reality: This is a BFF (Backend-For-Frontend), not a gateway.
  Putting business logic in the gateway creates coupling and deployment friction.

OVER-ENGINEERING 4: Custom high-performance HTTP parser
  "Build a custom HTTP parser for maximum performance"
  Reality: Existing parsers (http-parser, h2o, picohttpparser) are highly optimized.
  Custom parser: Months of development, security risk, maintenance burden.
  Better: Use a battle-tested proxy foundation (Envoy, nginx) and extend it.
```

## Cost-Aware Redesign

```
IF BUDGET IS $500/MONTH (startup, 10K QPS):
  → Cloud API gateway (AWS API Gateway, GCP Apigee)
  → No self-hosted infrastructure
  → Cost: ~$3.50 per million requests (AWS pricing)
  → 10K QPS × 2.6M requests/month = ~$9/month for API Gateway
  → Plus: Lambda/Cloud Function for auth = ~$50/month
  → Total: ~$60-100/month

IF BUDGET IS $10,000/MONTH (mid-scale, 500K QPS):
  → Self-hosted Envoy/nginx on 5 instances
  → Managed load balancer in front
  → Basic rate limiting (local counters only)
  → Managed logging (CloudWatch / Stackdriver)
  → Total: ~$3,000-5,000/month

IF BUDGET IS $100,000/MONTH (large scale, 5M+ QPS):
  → This chapter's architecture
  → 20+ gateway instances
  → Full rate limiting, circuit breaking, observability
  → Multi-region deployment
  → Dedicated SRE for gateway operations
  → Total: ~$50,000-80,000/month
```

---

# Part 12: Multi-Region & Global Considerations

## Data Locality

```
PRINCIPLE: Gateway processes requests in the NEAREST region to the client.
Config and routing rules are GLOBAL (same in all regions).

GATEWAY INSTANCES:
  Region US-East: 7 instances (serving Americas)
  Region EU-West: 7 instances (serving Europe)
  Region AP-Southeast: 6 instances (serving Asia-Pacific)
  
  Each region has a COMPLETE gateway fleet with IDENTICAL configuration.
  
CLIENT-TO-GATEWAY ROUTING:
  Option A: GeoDNS
    api.example.com → resolves to nearest region's IP
    Simple, works with any client
    Limitation: DNS caching means failover is slow (TTL-dependent)
  
  Option B: Anycast
    Same IP advertised from all regions via BGP
    Network routing automatically selects nearest region
    Faster failover than DNS (BGP convergence: 30-90 seconds)
    
  Option C: Global Load Balancer (Cloud)
    GCP GCLB / AWS Global Accelerator
    Intelligent routing with health-aware failover
    Best option for cloud-native deployments

BACKEND ROUTING FROM GATEWAY:
  Request arrives at US-East gateway → Routed to US-East backends
  Not cross-region (latency would be 50-100ms extra).
  
  Exception: If the backend ONLY exists in one region:
  → Gateway forwards cross-region → Accept the latency cost
  → Document it in the route config: "cross_region: true, expected_latency: +80ms"
```

## Replication Strategies

```
ROUTE CONFIG REPLICATION:
  Config store (primary) is in one region.
  All gateway instances in ALL regions receive config via push.
  
  Push mechanism: Config change → Push to regional aggregators → Push to instances
  Latency: < 10 seconds from change to applied in all regions.
  
  On primary region failure:
  → Config pushes stop (no new changes)
  → All gateways continue with current config (stale but valid)
  → Duration tolerance: Hours (config changes are rare)

RATE LIMIT SYNC:
  PER-REGION rate limits: No cross-region sync needed.
  GLOBAL rate limits (per-user across all regions):
  → Each region reports per-user counts to a central aggregator
  → Aggregator broadcasts global totals every 5 seconds
  → Regional gateways adjust local limits based on global usage
  
  Accuracy with 5-second global sync: ±20% during cross-region usage
  Acceptable: User making requests from 2 regions simultaneously is rare.

CERTIFICATE REPLICATION:
  Same certificates needed in all regions.
  Distributed by config store (or dedicated cert distribution system).
  Each region maintains a local copy of all certificates.
```

## Traffic Routing

```
NORMAL OPERATION:
  Client → Nearest region → Local gateway → Local backends
  
  Latency optimization: Everything stays in-region.
  
FAILOVER:
  Region failure → Traffic rerouted to next-nearest region.
  
  Mechanism (Anycast): BGP route withdrawn → Traffic automatically shifts.
  Mechanism (GeoDNS): Health check fails → DNS updated to exclude region.
  Mechanism (GCLB): Health check fails → Traffic shifted in seconds.
  
  Impact of failover:
  → Clients in the failed region experience 30-90 second disruption
  → After failover: Latency increases by cross-region RTT (50-100ms)
  → Capacity: Receiving region must have headroom for additional traffic

TRAFFIC SPLITTING (Global canary):
  "Route 5% of global traffic to a new version"
  
  Challenge: Must be consistent per-user (not per-region).
  User in US-East → 5% chance of canary on every request, regardless of region.
  
  Implementation: Hash(user_id) % 100 < 5 → Canary.
  This is evaluated at the gateway, using the same hash in all regions.
  → User experience is consistent globally.
```

## Failure Across Regions

```
SCENARIO: US-East region has a complete outage (network, power).

IMPACT:
  US-East gateway: Down (no instances reachable)
  US-East backends: Down (all services in region unavailable)
  
  Traffic to US-East:
  → Anycast/GeoDNS redirects to EU-West or AP-Southeast
  → Clients experience 30-90 seconds of errors during failover
  → After failover: +50-100ms latency (cross-region)
  → EU-West backends handle US-East traffic (if capacity exists)
  
IF BACKENDS ARE REGION-SPECIFIC (no cross-region service):
  → Gateway in EU-West receives US-East traffic → Routes to EU-West backends
  → EU-West backends process the request → Response to US client
  → This works ONLY if backends are multi-region and data is replicated
  
IF BACKENDS ARE NOT MULTI-REGION:
  → Gateway can route to the service, but the service can't serve the data
  → Return 503: "Service temporarily unavailable"
  → Gateway is NOT responsible for making backends multi-region

SPLIT-BRAIN RISK:
  Both regions think they're primary for rate limiting.
  → User gets 2× their rate limit (one quota per region).
  → Acceptable: Temporary over-admission is better than denial of service.
  → Reconciliation: When connectivity restores, sync counters.
```

## When Multi-Region Is NOT Worth It

```
NOT WORTH IT WHEN:
  1. All users are in one geographic area
     US startup with US users → Single region is fine
     Latency: < 50ms coast-to-coast (acceptable)
     
  2. Traffic < 1M QPS
     Single region handles this easily
     Multi-region complexity isn't justified
     
  3. Backend services are single-region
     Even with multi-region gateways, requests still go to one region
     Gateway multi-region adds latency without benefit

WORTH IT WHEN:
  → Users are globally distributed (US, EU, Asia)
  → Latency is a competitive advantage (< 50ms globally)
  → Regulatory requirements (EU data must be processed in EU)
  → Availability requirements (survive entire region outage)
  → Traffic > 5M QPS (single region may not have capacity)
```

---

# Part 13: Security & Abuse Considerations

## Abuse Vectors

```
ABUSE VECTOR 1: DDoS (volumetric)
  Goal: Overwhelm gateway with traffic volume
  Impact: Gateway CPU saturated → All traffic affected
  
  Defense layers:
  → L3/L4: ISP/cloud DDoS mitigation (volumetric)
  → L4: SYN cookies, connection rate limits
  → L7: Request rate limits, IP reputation

ABUSE VECTOR 2: Credential stuffing
  Goal: Try stolen username/password combinations against /login endpoint
  Impact: User accounts compromised
  
  Defense:
  → Per-IP rate limit on auth endpoints: 10 attempts/minute
  → Per-account rate limit: 5 attempts/minute
  → CAPTCHA after 3 failed attempts
  → IP reputation: Block known credential stuffing IPs
  → Gateway detects: High rate of 401 responses from one IP → Auto-block

ABUSE VECTOR 3: API scraping
  Goal: Extract all data from public-facing APIs
  Impact: Data stolen, competitive advantage lost
  
  Defense:
  → Per-user rate limits (free tier: 100 requests/minute)
  → Endpoint-specific limits (search: 10/minute for free tier)
  → Request fingerprinting (TLS fingerprint, header order, timing)
  → Pagination limits (max 100 items per page, max 1000 pages total)

ABUSE VECTOR 4: Slow request attack (Slowloris)
  Goal: Open many connections, send data very slowly, exhaust connection pool
  Impact: Gateway can't accept new connections → Denial of service
  
  Defense:
  → Idle connection timeout: 10 seconds (close connections that don't send data)
  → Request header timeout: 5 seconds (reject slow headers)
  → Request body timeout: 30 seconds (reject slow uploads)
  → Min data rate: 100 bytes/second (close connections below threshold)

ABUSE VECTOR 5: Request smuggling
  Goal: Exploit HTTP parsing differences between gateway and backend
  Impact: Bypass security controls, access unauthorized endpoints
  
  Defense:
  → Use HTTP/2 between gateway and backends (unambiguous framing)
  → Normalize HTTP/1.1 requests at gateway (resolve ambiguities)
  → Reject ambiguous requests (multiple Content-Length headers)
  → Test for smuggling vulnerabilities in gateway + backend combinations
```

## Rate Abuse

```
SOPHISTICATED RATE ABUSE:
  Attacker creates 1000 free-tier accounts.
  Each account: 100 requests/minute.
  Total: 100,000 requests/minute from "legitimate" accounts.
  
  Defense:
  → Global rate limit per IP: Even with 1000 accounts, one IP can't send
    more than 1000 requests/minute (separate from per-account limit)
  → Account creation rate limit: Max 5 accounts from one IP
  → Behavioral analysis (offline): Accounts with identical access patterns
    → Flag for review → Suspend if confirmed abusive

RATE LIMIT BYPASS ATTEMPTS:
  → Distributed attack from 10,000 IPs (botnet): Per-IP limits ineffective
  → IP rotation (proxies, VPNs): Same attacker appears as different IPs
  → Header spoofing: Fake X-Forwarded-For to appear as different clients
  
  Defense:
  → X-Forwarded-For: NEVER trust client-provided values
     Gateway sets X-Forwarded-For based on the ACTUAL client IP (TCP source)
  → For distributed attacks: Global rate limit protects infrastructure
  → For sophisticated attacks: Requires out-of-band analysis (bot detection ML)
  → Gateway provides the DATA (access logs), analysis happens offline
```

## Data Exposure

```
EXPOSURE RISK 1: Error messages revealing internal topology
  Bad: {"error": "Connection refused to user-service at 10.0.3.45:8080"}
  Good: {"error": "Internal server error", "request_id": "req_abc123"}
  
  Rule: External error responses NEVER include:
  → Backend service names
  → Internal IP addresses
  → Stack traces
  → Database error messages
  
  Internal debugging: Use request_id to trace in internal logs.

EXPOSURE RISK 2: Headers leaking internal state
  Bad: Response includes X-Backend-Instance: user-svc-us-east-1-a-003
  Good: No internal headers in external responses
  
  Rule: Gateway strips ALL internal headers before sending response to client.
  Whitelist approach: Only explicitly allowed headers pass through.

EXPOSURE RISK 3: Timing attacks
  Scenario: Attacker measures response time to determine if a resource exists.
  /api/v2/users/valid-user: 200ms (backend processes, returns data)
  /api/v2/users/invalid-user: 5ms (backend returns 404 quickly)
  → Timing difference reveals user existence
  
  Mitigation: Backend should take similar time for 404 and 200.
  Gateway-level: Not easily fixable without adding artificial delays.
  Staff insight: This is a BACKEND concern, not a gateway concern.
  The gateway provides access logging so backend teams can detect probing.

EXPOSURE RISK 4: Access logs containing PII
  Access logs contain: user_id, client_ip, path (may contain sensitive data)
  Example: /api/v2/search?q=medical+condition
  
  Mitigation:
  → Redact query parameters from access logs for sensitive endpoints
  → Hash client IPs in access logs (for analysis without PII exposure)
  → Restrict access log access to authorized personnel
  → Comply with data retention regulations (GDPR: delete after purpose served)
```

## Privilege Boundaries

```
BOUNDARY 1: External vs Internal
  External traffic: Untrusted, fully authenticated, rate limited
  Internal traffic: Semi-trusted, mTLS authenticated, higher rate limits
  
  Gateway enforces: External clients CANNOT access internal endpoints
  Internal services CAN access internal endpoints (different auth path)

BOUNDARY 2: Read vs Write
  Read operations: Lower risk, can fail open (degraded auth OK)
  Write operations: Higher risk, must fail closed (no auth = no write)
  
  Gateway enforces: Auth degradation policy per route.

BOUNDARY 3: Admin vs User
  Admin endpoints: /admin/*, /internal/*, /_health
  User endpoints: /api/v2/*
  
  Gateway enforces: Admin endpoints require elevated credentials
  (mTLS + admin role, not just user JWT)

BOUNDARY 4: Gateway team vs Backend teams
  Gateway team: Owns gateway code, deployment, and shared infra
  Backend teams: Own route config for their services, rate limit config
  
  Permission model:
  → Backend team A can ONLY modify routes for /api/v2/users/*
  → Backend team A CANNOT modify routes for /api/v2/orders/*
  → Gateway team can modify any route (platform admin)
  → All changes audited, versioned, and reviewable
```

## Why Perfect Security Is Impossible

```
FUNDAMENTAL TENSIONS:
  
  Security vs Latency:
  → More security checks = more CPU = higher latency
  → Request body inspection: +50-100µs per request
  → ML-based anomaly detection: +5-50ms per request
  → At some point: Security overhead makes the service unusable
  
  Security vs Availability:
  → Stricter auth = more rejections during auth system failures
  → "Fail closed" = secure but unavailable
  → "Fail open" = available but potentially insecure
  → The right choice depends on the endpoint and the business impact
  
  Security vs Developer Productivity:
  → Strict gateway policies = Slower development iteration
  → "You can't add a new endpoint without gateway team approval"
  → Teams start bypassing the gateway → Shadow APIs → Worse security
  
  The Staff Engineer's job: Find the balance point that provides
  SUFFICIENT security without crippling availability, latency, or velocity.
  Perfect security would require infinite compute and zero latency → Impossible.
```

## Multi-Team Gateway Governance

```
PROBLEM: 500 backend teams want to configure their own routes,
rate limits, and auth policies. Who controls the gateway?

MODEL 1: CENTRALIZED (gateway team owns everything)
  + Consistent policies, security reviewed
  - Bottleneck: Gateway team is on every team's critical path
  - Every new endpoint needs a gateway team ticket → Delays
  
MODEL 2: FULLY DECENTRALIZED (every team self-serves)
  + Fast: Teams deploy route changes independently
  - Risk: Bad route config from one team breaks all services
  - Security: Teams may misconfigure auth requirements
  
MODEL 3: FEDERATED (recommended)
  Gateway team: Owns gateway infrastructure, shared policies, and deployment
  Backend teams: Own their route configs (within guard rails)
  
  GUARD RAILS:
  → Route configs pass automated validation before applying
  → Config changes cannot affect other teams' routes
  → Auth policies have a MINIMUM floor (set by gateway team)
    → Teams can ADD auth requirements, not remove them
  → Rate limits have a MAXIMUM ceiling (set by gateway team)
    → Teams can set LOWER rate limits, not bypass global limits
  → Config changes that affect > 10% of traffic require gateway team review
  
  Staff insight: Federated governance is the ONLY model that scales.
  Centralized creates bottlenecks. Decentralized creates outages.
  Federated requires investing in TOOLING (validation, guard rails, self-service)
  but pays off enormously in velocity and safety.
```

---

# Part 14: Evolution Over Time

## V1: Naive Design

```
V1 ARCHITECTURE (startup, 10 services, 1,000 QPS):

  Single nginx instance as reverse proxy.
  Static config file with location blocks.
  No auth at gateway (backends handle their own auth).
  No rate limiting (traffic too low to matter).
  Logs to local file, rotated daily.
  
  Configuration: Edit nginx.conf, reload nginx.
  Deployment: SSH, edit file, nginx -s reload.
  
  WHY IT WORKS AT SMALL SCALE:
  → 1,000 QPS: Single nginx handles 10,000 QPS easily
  → 10 services: Config file is 50 lines, easy to manage
  → Small team: Everyone knows the config, changes are rare
  → No abuse: Low traffic, no need for rate limiting
  
  COST: $50/month (single VM)
```

## What Breaks First

```
BREAK 1: Authentication (at ~50 services)
  "Every service implements auth differently. Service D has a bug."
  → First security incident: Unauthenticated access to user data
  → Fix: Move auth to gateway → Consistent enforcement
  → But: nginx auth_request → Adds 5ms per request (external auth call)

BREAK 2: Traffic spikes (at ~50,000 QPS)
  "Our single nginx instance hit 100% CPU during the flash sale"
  → Users couldn't load the site for 15 minutes
  → Fix: Multiple nginx instances behind a load balancer
  → But: Config files must be synchronized across instances
  → Engineers edit one instance, forget the others → Config drift

BREAK 3: Config management (at ~200 services)
  "nginx.conf is 2,000 lines, nobody understands it"
  → Config change broke production (typo in upstream block)
  → No audit: "Who changed the config? When? Why?"
  → Fix: Version-controlled config with CI/CD pipeline
  → But: Config deploy takes 5 minutes (build → test → deploy)

BREAK 4: Rate limiting (at ~100,000 QPS)
  "Our search API is being scraped. 100K requests/minute from one IP"
  → Backend database overloaded → Site slow for everyone
  → Fix: Rate limiting at gateway (per-IP, per-user)
  → But: nginx rate limiting is per-instance, not global

BREAK 5: Observability (at ~500,000 QPS)
  "We have 20 nginx instances. Logs are on each server. Debugging is impossible."
  → Incident: "Which service had the 5xx errors? On which instance?"
  → Takes 30 minutes to grep 20 log files
  → Fix: Centralized logging + structured access logs
```

## V2: Intermediate Design

```
V2 ARCHITECTURE (mid-scale, 200 services, 500,000 QPS):

  Envoy proxy fleet (10 instances) behind cloud load balancer.
  Config managed via xDS (Envoy's dynamic configuration API).
  JWT auth at gateway (local verification with cached keys).
  Rate limiting via Redis (centralized counters).
  Structured access logs shipped to ELK/Splunk.
  Circuit breakers per backend.
  
  Configuration: xDS server pushes config to Envoy instances.
  Deployment: Update xDS config → Envoy hot-reloads.
  
  IMPROVEMENTS OVER V1:
  → Dynamic config (no nginx reload needed)
  → Centralized auth (JWT verification at edge)
  → Rate limiting (Redis-backed, global counters)
  → Observability (structured logs, distributed tracing)
  → Circuit breakers (backend failure isolation)
  
  PROBLEMS:
  → Redis on hot path: 1-2ms per request for rate limit check
  → At 500K QPS: 500K Redis operations/second → Redis cluster needed
  → Redis failure → Rate limiting fails → Backends unprotected
  → xDS server is single point of failure for config updates
  → No canary deployment support for route changes
  → No config validation → Bad config pushed → Outage

  COST: $5,000/month (10 instances + Redis + logging)
```

## V3: Long-Term Stable Architecture

```
V3 ARCHITECTURE (scale, 500+ services, 5,000,000+ QPS):

  This chapter's architecture:
  
  Stateless gateway fleet (20+ instances)
  Local auth (JWT verify with cached keys, no external call)
  Local rate limiting (token buckets, periodic global sync)
  Compiled route trie (O(path_depth) matching)
  Per-backend connection pools (failure isolation)
  Latency-based circuit breakers
  Config management with validation, canary, and auto-rollback
  Multi-region with anycast routing
  Federated governance (backend teams self-serve within guard rails)
  
  IMPROVEMENTS OVER V2:
  → No Redis on hot path (local counters with periodic sync)
  → Config validation prevents bad pushes
  → Canary config deployment (apply to 1 instance first)
  → Automatic rollback on error spike after config change
  → Federated governance (scales to 500+ backend teams)
  → Multi-region with automatic failover
  
  COST: $50,000-80,000/month (compute + bandwidth + logging)
  
  Staff insight: The biggest jump from V2 to V3 is removing ALL external
  dependencies from the hot path. V2's Redis rate limiter added 1-2ms
  per request and created a single point of failure. V3's local counters
  add 0µs and have no external dependency. This single change makes the
  gateway more reliable AND faster. The trade-off (±10% accuracy) is
  trivially acceptable.
```

## Migration Path: V2 to V3 Without Downtime

```
PROBLEM: You cannot shut down the gateway for 500 services while migrating
from Redis-backed rate limiting (V2) to local-counter-with-sync (V3).
The migration must be invisible to clients and backend teams.

PHASE 1: DEPLOY V3 RATE LIMITER IN SHADOW MODE (2-4 weeks)
  Gateway runs BOTH rate limiters simultaneously:
  → V2 (Redis): Makes the actual ALLOW/DENY decision (production)
  → V3 (local counters): Runs in shadow, logs decisions, no enforcement
  
  FUNCTION check_rate_limit_during_migration(request, identity):
    v2_decision = redis_rate_limiter.check(identity)  // Production
    v3_decision = local_rate_limiter.check(identity)   // Shadow
    
    IF v2_decision != v3_decision:
      metric.increment("rate_limit_migration_divergence", {
        user: identity.user_id,
        v2: v2_decision,
        v3: v3_decision
      })
    
    RETURN v2_decision  // V2 is still authoritative
  
  Goal: Divergence rate < 0.1% for 2 consecutive weeks.

PHASE 2: FLIP PRIMARY TO V3 (1-2 weeks)
  V3 makes ALLOW/DENY decision. V2 runs in shadow.
  
  Rollback: Single config flag flips back to V2 in < 10 seconds.
  
  Monitor: Divergence, false rejection rate, customer complaints.
  If regression: Flip back to V2, investigate.

PHASE 3: REMOVE REDIS FROM HOT PATH (1 week)
  Disable V2 shadow mode. V3 is sole rate limiter.
  Redis still runs for rate limit SYNC (aggregation, not enforcement).
  
  Redis failure impact changes from:
  V2: "Rate limiting breaks → Backends unprotected" (CRITICAL)
  V3: "Global sync stops → Local counters slightly inaccurate" (MINOR)

PHASE 4: SIMPLIFY SYNC (2-4 weeks)
  Replace Redis-based sync with custom lightweight aggregation service.
  → Each gateway reports counts via UDP (fire-and-forget, no ack)
  → Aggregation service computes global totals → Broadcasts back
  → Redis fully decommissioned from gateway data path
  
TOTAL MIGRATION: 6-10 weeks, zero downtime, fully reversible until Phase 4.

MIGRATION FOR ROUTING (nginx/static → Envoy/dynamic):
  Phase 1: Deploy Envoy fleet alongside nginx fleet.
  Phase 2: L4 LB splits traffic: 1% → Envoy, 99% → nginx.
  Phase 3: Compare metrics. Gradually shift to 100% Envoy over 4 weeks.
  Phase 4: Decommission nginx.
  
  Key: Identical route config on both nginx and Envoy during migration.
  Tooling: Write route config in ONE format, transpile to both nginx.conf and xDS.
  
  Staff insight: The migration tooling (config transpiler) is MORE work
  than the actual Envoy deployment. Budget 60% of migration effort for
  tooling, 40% for the actual migration.
```

## How Incidents Drive Redesign

```
INCIDENT 1: "Redis cluster failure took down rate limiting for 45 minutes"
  → Redesign: Remove Redis from hot path → Local counters with periodic sync
  → Learning: Never put an external dependency on the per-request hot path.
    If it's not in-process, it's a latency and availability risk.

INCIDENT 2: "Bad route config sent ALL traffic to one backend"
  → Added: Route config validation (check for catch-all overrides)
  → Added: Canary config deployment (apply to 1 instance, compare metrics)
  → Added: Automatic rollback on error spike after config change
  → Learning: Config validation catches the typo. Canary catches the 
    unexpected consequence. Auto-rollback limits blast radius of both.

INCIDENT 3: "Slow order-service caused all services to slow down"
  → Redesign: Per-backend connection pools (isolated failure domains)
  → Added: Latency-based circuit breaker (catches slow != failing)
  → Learning: Shared resources (thread pools, connection pools) are
    the most common cause of cascading failures. Isolate everything.

INCIDENT 4: "TLS certificate expired at 3 AM, total outage for 2 hours"
  → Added: Automated certificate renewal (ACME/Let's Encrypt)
  → Added: Certificate expiry monitoring (alert at 30, 7, 1 days)
  → Added: Runbook: "How to manually replace a certificate in < 5 minutes"
  → Learning: Certificate rotation must be automated AND monitored.
    Automated systems fail silently. Monitoring catches the silence.

INCIDENT 5: "500+ backend teams waiting for gateway team to add their routes"
  → Redesign: Federated governance model
  → Added: Self-service route configuration with guard rails
  → Added: Automated validation pipeline for route changes
  → Learning: Centralized governance doesn't scale beyond 50 teams.
    The gateway team becomes a bottleneck that drives teams to bypass the gateway.

INCIDENT 6: "Client retry storm during backend outage tripled our traffic"
  → Added: Retry budget per backend (max 20% retries)
  → Added: Retry-After header in 503 responses
  → Added: Circuit breaker documentation for client teams
  → Learning: The gateway can control ITS OWN retry behavior.
    Client retries require client teams to implement backoff.
    Gateway provides the SIGNAL (Retry-After), clients decide behavior.
```

## Structured Real Incident Table

The following table documents a production incident in the format Staff Engineers use for post-mortems and interview calibration. Memorize this structure.

| Part | Content |
|------|---------|
| **Context** | API gateway fleet serving 5M QPS across 500 backend services. TLS termination at edge. Certificate renewal via ACME; expiry monitoring existed but alert was misconfigured (wrong certificate path). |
| **Trigger** | Primary TLS certificate expired at 02:47 AM. ACME renewal had failed silently three days prior (DNS challenge timeout). No alert fired; monitoring checked a different certificate path. |
| **Propagation** | All new TLS handshakes failed immediately. Existing connections (reused sessions) continued for minutes until clients rotated. Within 5 minutes, most clients had reconnected; all new handshakes failed. 100% of external traffic effectively down. |
| **User impact** | Total API unavailability for ~2 hours. All mobile apps, web clients, and API consumers received connection errors. Internal service-to-service (mTLS) unaffected. Revenue impact: ~$2M for the two-hour window. |
| **Engineer response** | On-call paged at 02:52. Initially investigated backends (unclear it was gateway). Checked gateway health—instances healthy. 15 minutes: Suspected TLS. Verified certificate expiry. 30 minutes: Obtained emergency certificate from PKI team. Hot-swapped cert at 03:45. Traffic restored by 03:50. |
| **Root cause** | Certificate renewal automation failed; monitoring path did not match actual cert in use; no redundant alert (e.g., TLS handshake failure rate). |
| **Design change** | Automated renewal with two independent implementations (failover); certificate expiry monitored on the ACTUAL cert in use; alert at 30, 7, 1 days; TLS handshake failure rate alert (> 1% = page); runbook for manual cert replacement in < 5 minutes. |
| **Lesson** | Certificate expiry is the #1 "everything died at once" outage pattern. Automated renewal must be monitored; monitoring must validate the production certificate path. Staff principle: "Automated systems fail silently. Monitoring catches the silence." |

---

## Canary Deployment for the Gateway Itself

```
PROBLEM: A bad gateway deploy can affect ALL traffic (not just one service).

CANARY STRATEGY:
  1. Deploy new version to 1 instance (out of 20)
  2. Route ~5% of traffic to canary instance
  3. Compare (canary vs control):
     → Error rate (per backend, per route)
     → P50/P99 latency (gateway overhead, not backend time)
     → CPU usage per request
     → Connection pool utilization
     → Rate limit accuracy (compare with expected)
  4. If no regression after 1 hour: Deploy to 5 instances
  5. If no regression after 2 hours: Deploy to all
  6. If regression at any stage: Rollback canary, investigate

DEPLOYMENT MECHANISM:
  Blue-green with traffic weight:
  → Blue fleet (current): 20 instances, weight 100%
  → Green fleet (new): 1 instance, weight 5%
  → L4 LB splits traffic by weight
  → Gradually shift weight: 5% → 25% → 50% → 100%
  → Once green is 100%: Old blue fleet becomes the "canary" for next deploy

ZERO-DOWNTIME GUARANTEE:
  At no point is an instance taken out of service without replacement.
  Drain: Stop accepting new connections, finish in-flight requests (30s timeout).
  Replace: New instance starts, health check passes, L4 LB adds to rotation.
  Total per-instance: ~60 seconds of reduced capacity, zero dropped requests.
```

## Graceful Drain and Rolling Restart Procedure

```
PROBLEM: Gateway maintenance (code deploy, kernel patch, instance replacement)
requires restarting instances. If done carelessly, draining 1 of 20 instances
means 5% of active connections are terminated mid-request.

DRAIN PROCEDURE:
  FUNCTION graceful_drain(gateway_instance):
    // Phase 1: Stop accepting NEW connections
    gateway_instance.listener.stop_accept()
    
    // Phase 2: Signal L4 LB to remove this instance
    health_check.return_503()  // LB detects, stops routing new traffic
    
    // Phase 3: Wait for in-flight requests to complete
    WAIT_UNTIL active_requests == 0 OR timeout(30_SECONDS)
    
    // Phase 4: Forcefully close remaining connections
    IF active_requests > 0:
      LOG.warn("Force-closing {active_requests} connections after drain timeout")
      gateway_instance.close_all_connections()
    
    // Phase 5: Shutdown
    gateway_instance.shutdown()

ROLLING RESTART STRATEGY:
  Fleet: 20 instances, need at least 17 for peak capacity (3 spare).
  
  1. Drain instance 1 → Wait for drain complete (~30 seconds)
  2. Restart instance 1 → Wait for health check pass (~10 seconds)
  3. Instance 1 back in rotation → Drain instance 2 → ...
  4. Repeat for all 20 instances
  
  Total rolling restart time: 20 × 40 seconds = ~13 minutes
  
  Capacity during restart: 19/20 = 95% → Within headroom
  At MOST 1 instance draining at a time → Never below 95%

FLEET DEGRADATION DURING ROLLING DEPLOY:
  If deploying a new version with a bug:
  → Instance 1 restarted with new version → Starts failing
  → Instance 1 fails health check → LB removes from rotation
  → Capacity: 19/20 = 95% → Still fine
  → Deploy continues: Instance 2 restarted → Also fails
  → Capacity: 18/20 = 90% → Alert: "Multiple unhealthy gateway instances"
  → Deploy paused (auto-brake: stop if > 1 instance unhealthy)
  → Rollback: Restart instances 1-2 with old version
  
  Staff insight: The auto-brake is CRITICAL. Without it, a rolling deploy
  of a bad version kills instances one by one until the fleet is dead.
  The auto-brake limits blast radius to the canary count (1-2 instances).
```

## Route Config Staging and Testing Workflow

```
PROBLEM: Backend teams self-serve their route config. How do they
test route changes before production? A bad route config in production
causes instant outage for their service.

TESTING PIPELINE:
  
  1. CONFIG VALIDATION (automated, < 1 second):
     Structural: Is the YAML/JSON valid?
     Semantic: Do referenced backends exist? Are weights 0-100?
     Conflict: Does this route overlap with another team's routes?
     Compatibility: Is this a breaking change? (path removed, backend changed)
     
     IF validation fails → Change rejected immediately with clear error.
  
  2. STAGING GATEWAY (automated, ~5 minutes):
     A separate gateway fleet running production config + proposed change.
     Synthetic traffic generator sends test requests matching the new route.
     
     Tests:
     → Does the new route match the expected requests?
     → Does the old route still match its expected requests? (regression)
     → Is the backend reachable from the staging gateway?
     → Is the response status 2xx for known-good requests?
     
     IF any test fails → Change rejected with test report.
  
  3. CANARY ON PRODUCTION (automated, ~15 minutes):
     Apply route config to 1 production gateway instance.
     Compare:
     → Error rate on canary vs control
     → Latency on canary vs control
     → 404 rate on canary vs control (new route not matching?)
     
     IF canary has > 1% more errors than control → Auto-rollback.
  
  4. FULL PRODUCTION ROLLOUT:
     Apply to all gateway instances.
     Monitor for 1 hour.
     Any regression → Manual or auto-rollback.

SELF-SERVICE WORKFLOW FOR BACKEND TEAMS:
  
  Team creates route config change → Submits to config store
  → Automatic validation (1 second) 
  → Staging test (5 minutes)
  → Canary production (15 minutes, if staging passes)
  → Full rollout (if canary passes)
  
  Total time: ~20 minutes from submit to full production.
  Human involvement: Zero (unless canary fails, which alerts the team).
  
  GUARD RAILS ENFORCED BY THE PIPELINE:
  → Team can ONLY modify routes in their own path prefix (/api/v2/users/*)
  → Team CANNOT reduce auth requirements below platform minimum
  → Team CANNOT set timeout > 30 seconds (prevent thread exhaustion)
  → Team CANNOT create catch-all routes (/* → their backend)
  → Changes affecting > 100,000 QPS require gateway team review

Staff insight: The self-service pipeline IS the governance model.
If the pipeline has good validation and canary, backend teams can
deploy route changes with confidence and without blocking on the
gateway team. The pipeline replaces human review for 95% of changes.
The remaining 5% (high-traffic changes) get human review because
the blast radius justifies the delay.
```

---

# Part 15: Alternatives & Explicit Rejections

## Alternative 1: Service Mesh as the Only Gateway (No Dedicated Edge Gateway)

```
APPEAL:
  "We already have Istio/Envoy as a service mesh. Just use the mesh
  ingress gateway instead of building a separate edge gateway."
  
  Advantage:
  → Single technology stack (Envoy everywhere)
  → Mesh already handles: routing, rate limiting, circuit breaking, TLS
  → Less infrastructure to maintain

WHY A STAFF ENGINEER REJECTS THIS:
  1. DIFFERENT CONCERNS:
     Edge gateway: Authentication, external rate limiting, API versioning,
     DDoS protection, public-facing error messages, CORS.
     Service mesh: Internal retries, circuit breaking, mutual TLS, tracing.
     
     Combining them means one component handles both → Coupled upgrades,
     conflicting config policies, unclear ownership.
  
  2. SECURITY BOUNDARY:
     Edge gateway is the ONLY component exposed to the internet.
     It must be hardened, audited, and minimized.
     Service mesh processes internal traffic (trusted network).
     Mixing external and internal traffic processing increases attack surface.
  
  3. OPERATIONAL INDEPENDENCE:
     Gateway upgrade should not affect internal service communication.
     Mesh upgrade should not affect external API surface.
     Coupling them means: "Can't upgrade mesh without risking external traffic."
  
  4. SCALE CHARACTERISTICS:
     Edge gateway: 5M QPS concentrated at one layer.
     Mesh sidecar: Distributed across 500K instances (much lower per-instance QPS).
     Performance optimizations differ significantly.
  
  Staff compromise: Use the SAME technology (Envoy) for both, but as
  SEPARATE deployments with SEPARATE configuration and SEPARATE teams.
```

## Alternative 2: Cloud-Managed API Gateway (AWS API Gateway / GCP Apigee)

```
APPEAL:
  "AWS API Gateway handles routing, auth, rate limiting, and monitoring.
  Why build our own?"
  
  Advantage:
  → Zero infrastructure management
  → Built-in auth (Cognito/IAM), rate limiting, monitoring
  → Scales automatically
  → Free tier + pay-per-request pricing

WHY A STAFF ENGINEER REJECTS THIS (at scale):
  1. COST:
     AWS API Gateway: $3.50 per million requests
     At 5M QPS: $3.50 × 5M × 60 × 60 × 24 × 30 / 1,000,000 = ~$45M/month
     Self-hosted: ~$80K/month
     → At scale, managed API gateway is 500× more expensive.
  
  2. LATENCY:
     Managed gateways add 5-30ms of overhead (AWS API Gateway P50: ~10ms)
     Self-hosted (optimized): < 1ms overhead
     For latency-sensitive APIs, 10ms overhead is unacceptable.
  
  3. CUSTOMIZATION:
     Managed gateways have fixed capabilities.
     Custom rate limiting logic: Not supported or limited.
     Custom auth integration: Often requires Lambda/Cloud Function → More latency.
     Latency-based circuit breakers: Not available in most managed gateways.
  
  4. VENDOR LOCK-IN:
     API Gateway config (AWS) is not portable to GCP or Azure.
     Multi-cloud or hybrid strategy requires a portable gateway.
  
  WHEN IT IS CORRECT: Startups, low-traffic APIs (< 100K QPS),
  teams without infrastructure expertise. The managed option is
  CORRECT for most companies. Self-hosted is only justified at scale.
```

## Alternative 3: BFF (Backend-for-Frontend) Instead of Gateway

```
APPEAL:
  "Each client platform (iOS, Android, Web) has its own BFF that aggregates
  backend calls, handles auth, and provides a tailored API. No shared gateway."
  
  Advantage:
  → Client-specific API optimization (exactly the data each client needs)
  → Each platform team owns their BFF (no gateway team bottleneck)
  → BFF can do response aggregation (multiple backends → one response)

WHY A STAFF ENGINEER REJECTS THIS AS A REPLACEMENT:
  1. CROSS-CUTTING DUPLICATION:
     Auth, rate limiting, TLS, logging → Implemented in EVERY BFF.
     → Inconsistency: iOS BFF has auth v2.3, Android has v2.1.
     → Security: Each BFF is independently vulnerable.
     → Updates: Auth library update requires deploying all BFFs.
  
  2. SECURITY SURFACE:
     3 BFFs exposed to the internet → 3 attack surfaces.
     vs 1 gateway → 1 attack surface.
     Each BFF needs its own DDoS protection, TLS, and hardening.
  
  3. OPERATIONAL OVERHEAD:
     3 BFF deployments + monitoring + on-call.
     One bad BFF deploy → One platform's users affected.
     But: 3× the operational surface to manage.
  
  STAFF COMPROMISE: Use BOTH.
  Gateway handles: TLS, auth, rate limiting, routing (cross-cutting).
  BFF handles: Response aggregation, client-specific transformation.
  
  Traffic flow: Client → Gateway → BFF → Backend services
  
  Gateway: Owned by platform team (shared, standardized).
  BFF: Owned by platform-specific team (iOS team owns iOS BFF).
  This separates cross-cutting concerns from client-specific logic.
```

---

# Part 16: Interview Calibration (Staff Signal)

## How Interviewers Probe This System

```
PROBE 1: "Design an API gateway for a large-scale system"
  Testing: Do you understand the scope? (Not just routing)
  Weak answer: Draws a box labeled "API gateway" between client and servers.
  Strong answer: Immediately identifies the critical constraints:
  → "First, the gateway is on the hot path of every request, so I need
     to establish a latency budget. Everything I add to the gateway
     competes for that budget."
  → "The gateway handles: TLS, auth, rate limiting, routing, circuit breaking,
     logging. Let me discuss which of these are on the critical path
     and which are async."

PROBE 2: "How do you handle rate limiting across a fleet of gateway instances?"
  Testing: Distributed systems understanding
  Weak answer: "Use Redis as a centralized counter"
  Strong answer: "Redis on the hot path adds 1-2ms per request and creates a
  single point of failure. Instead, I use local token buckets with periodic
  global sync. The trade-off is ±10% accuracy, which is acceptable because
  users never notice 10% over-admission, but they always notice 2ms latency."

PROBE 3: "What happens when a backend is slow?"
  Testing: Failure mode reasoning, cascading failure awareness
  Weak answer: "Return timeout error to client"
  Strong answer: Discusses per-backend connection pool isolation, latency-based
  circuit breakers (not just error-based), request timeout budgets, and why
  slow backends are MORE dangerous than dead backends (no clear failure signal,
  silent resource exhaustion, cascading to other services through shared pools).

PROBE 4: "How do you deploy changes to the gateway safely?"
  Testing: Operational maturity
  Weak answer: "Blue-green deployment"
  Strong answer: Distinguishes between gateway CODE deployment (canary instances,
  traffic weight shifting, metric comparison) and gateway CONFIG deployment
  (route changes via config push, canary to 1 instance, auto-rollback on
  error spike). "A bad config push is more dangerous than a bad code deploy
  because config changes propagate in seconds to all instances."

PROBE 5: "How do 500 backend teams configure their routes?"
  Testing: Organizational awareness, governance
  Weak answer: "They submit a ticket to the gateway team"
  Strong answer: "Federated governance. Each team manages their own route
  config within guard rails. Config is validated automatically (no catch-all
  overrides, referenced backends must exist, auth policies meet minimum floor).
  The gateway team owns the platform, not the config for every service."

PROBE 6: "What does the gateway NOT do?"
  Testing: Scope discipline, architectural boundaries
  Weak answer: [Doesn't address this, keeps adding features]
  Strong answer: "The gateway does NOT do response aggregation—that's a BFF.
  It does NOT inspect request bodies—that's the backend. It does NOT serve
  static content—that's the CDN. It does NOT handle internal routing—that's
  the service mesh. The gateway is a THIN layer of cross-cutting concerns."
```

## Common L5 Mistakes

```
MISTAKE 1: Treating the gateway as a service orchestrator
  L5: "The gateway calls user-service, then order-service, then combines
  the results into one response for the client."
  Problem: This is a BFF, not a gateway. Putting business logic in the gateway
  creates coupling between the gateway team and every product team.
  If user-service changes its response format, the gateway must be updated.
  
  L6 correction: "The gateway routes the request to ONE backend. If the client
  needs data from multiple backends, that's a BFF or a GraphQL layer
  that sits BEHIND the gateway."

MISTAKE 2: Centralizing ALL rate limiting in Redis
  L5: "Each request checks Redis for the rate limit counter"
  Problem: Redis is on the hot path → 1-2ms per request, SPOF for rate limiting.
  
  L6 correction: "Local counters with periodic sync. Accept ±10% accuracy
  to eliminate the Redis dependency from the hot path."

MISTAKE 3: Failing to isolate backend failures
  L5: "If one backend is slow, the gateway queues requests and waits"
  Problem: Shared resources (threads, connections) become bottleneck →
  All services affected by one slow backend → Cascading failure.
  
  L6 correction: "Per-backend connection pools, per-route timeouts,
  latency-based circuit breakers. One slow backend CANNOT affect other
  services through the gateway."

MISTAKE 4: Putting auth on an external call
  L5: "Gateway calls auth-service to verify every request"
  Problem: Auth-service becomes a SPOF. If slow, ALL requests slow.
  If down, ALL requests fail (or bypass auth, which is worse).
  
  L6 correction: "JWT verification is LOCAL (cached public key + signature check).
  No external call needed. Auth is in-process, < 50µs."

MISTAKE 5: Ignoring config change safety
  L5: "Admin pushes config, all gateways update immediately"
  Problem: Bad config propagates to all instances in seconds → Instant global outage.
  
  L6 correction: "Config changes are validated, canary-deployed to 1 instance,
  compared against control, and auto-rolled back if error rate spikes."
```

## Staff-Level Answers

```
ON GATEWAY LATENCY:
  "The gateway adds < 1ms P50 overhead. I budget 100-150µs for the hot path:
  parsing, auth, rate limit, route match, header manipulation, and proxying.
  The 5ms P99 gives me headroom for occasional cache misses (JWT key refresh),
  GC pauses, and config reloads. I would never add a feature that costs
  more than 50µs per request without a strong justification."

ON FAILURE ISOLATION:
  "The gateway's most important job isn't routing—it's ISOLATING failures.
  Per-backend connection pools mean a slow payment service can't affect the
  search service. The circuit breaker means a dead recommendation service
  gets fast 503s instead of timeout-induced latency. The gateway is the
  FIREWALL between user experience and backend instability."

ON GOVERNANCE:
  "At 500+ backend teams, the gateway team CANNOT review every route change.
  We provide a self-service config interface with automated validation:
  routes are checked for conflicts, backends must exist in the registry,
  auth policies have a minimum floor. The gateway team sets the RULES,
  backend teams play within them. This is federated governance."
```

## Example Phrases a Staff Engineer Uses

```
"Let me start with the latency budget—every feature I add to the gateway
competes for the same microseconds."

"Slow backends are worse than dead backends. Dead backends fail fast;
slow backends exhaust resources silently."

"Rate limiting accuracy of ±10% is an acceptable trade-off for removing
Redis from the hot path."

"I would NOT put response aggregation in the gateway. That's a BFF concern.
The gateway's job is cross-cutting concerns, not business logic."

"Config changes are the leading cause of gateway outages. I treat config
deployment with MORE rigor than code deployment."

"The gateway should be the THINNEST possible layer that provides the
MAXIMUM cross-cutting value. Anything more, and you're building a
monolith at the edge."

"Per-backend connection pools are non-negotiable. Without them, a single
slow backend can cascade failure to the entire platform."

"If the circuit breaker opens, I return 503 in < 1ms instead of waiting
2 seconds for a timeout. That's the difference between '100ms of errors'
and '2 seconds of errors times 5 million requests.'"
```

### Additional Interview Probes and Staff Signals

```
PROBE 7: "How do you handle WebSocket and gRPC through the gateway?"
  Testing: Protocol awareness
  L5 answer: "The gateway proxies the connections"
  L6 answer: "WebSocket: Gateway authenticates the HTTP Upgrade request, applies
  rate limits, then becomes a transparent TCP proxy for the WebSocket connection.
  The gateway tracks connection-level metrics (duration, bytes transferred), not
  request-level metrics. For gRPC: Route on the HTTP/2 path (which contains the
  gRPC service and method). Rate limit per gRPC method, not per HTTP path.
  The gateway CANNOT inspect protobuf bodies—all rate limiting and auth
  must work from headers and metadata only."

PROBE 8: "What observability does the gateway provide?"
  Testing: Production thinking
  L5 answer: "Access logs and error counts"
  L6 answer: "The gateway is the SINGLE BEST observability point in the entire
  system because every request passes through it. I emit:
  → Per-route latency histograms (P50, P99, P99.9)
  → Per-backend error rate and latency
  → Gateway overhead breakdown (TLS, auth, routing, proxy)
  → Rate limit hit/miss rate per user tier
  → Circuit breaker state transitions
  → Connection pool utilization per backend
  → Request-level trace context propagation
  The gateway doesn't just route traffic—it MEASURES the health of the
  entire system at the entry point."

STAFF SIGNALS:
1. LATENCY BUDGET THINKING: Candidate explicitly budgets microseconds
   for each gateway component. This shows awareness that the gateway
   is on the hottest path in the system.

2. FAILURE ISOLATION: Candidate designs for backend independence
   (per-backend pools, per-backend circuit breakers). This is the
   most important Staff signal for gateway design.

3. SCOPE DISCIPLINE: Candidate says "no" to features that belong
   elsewhere (BFF, CDN, service mesh). This shows architectural maturity.

4. OPERATIONAL EXPERIENCE: Candidate mentions specific incident patterns
   (cert expiry, config push outage, retry storms) rather than
   theoretical failure modes.
```

## Leadership Explanation (How to Explain to Non-Engineers)

```
WHEN ASKED: "Why do we need an API gateway? Can't each service handle its own traffic?"

STAFF RESPONSE:
"The gateway is like airport security. Every passenger goes through the same
checkpoint before boarding any flight. We could put security at each gate, but
then we'd have 50 different implementations, 50 different vulnerabilities,
and updating security procedures would require changing 50 systems.

The gateway does one job extremely well: verify identity, enforce limits,
route traffic, and log everything—before a single byte touches our
application servers. It protects our entire platform from a single,
well-audited entry point. A 1ms delay at the gateway affects every user;
we treat it with the same rigor as our database."

WHEN ASKED: "Why can't we add [feature X] to the gateway?"

STAFF RESPONSE:
"Every feature we add to the gateway competes for a ~100 microsecond budget
per request. At 5 million requests per second, adding 50 microseconds means
we need 15 more CPU cores. More importantly, the gateway's job is
cross-cutting concerns—auth, rate limiting, routing—not business logic.
[Feature X] belongs in [BFF/backend] because it's specific to [domain],
and putting it in the gateway would couple the platform team to every
product change."
```

## How to Teach This Topic

```
TEACHING SEQUENCE:
1. Start with the latency budget. "The gateway is on the path of every request.
   Draw a timeline: client → ?ms → gateway → ?ms → backend. Establish that
   the gateway's job is to add as little as possible."

2. Introduce the four responsibilities: TLS, auth, rate limiting, routing.
   Emphasize: "All of these must complete in < 5ms P99. That means no
   external calls—no Redis, no auth-service lookup—on the hot path."

3. Teach failure isolation as the primary architectural decision. "Draw two
   gateways: one with shared connection pools, one with per-backend pools.
   Show how a slow backend cascades in the first, and is contained in the
   second. This single decision prevents the most common class of outages."

4. Use the structured incident table (cert expiry) to show how incidents
   drive design. "What failed? Why? What did we change? What's the lesson?"

5. End with scope discipline. "The gateway is the THINNEST layer. Anything
   that's not cross-cutting—response aggregation, business logic—belongs
   elsewhere. Saying 'no' to features is a Staff skill."

COMMON MISCONCEPTION TO ADDRESS:
"Rate limiting needs to be exact" → No. ±10% accuracy is acceptable;
1-2ms latency for exact counting is not. Protection, not precision.
```

---

# Part 17: Diagrams

## Diagram 1: Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              API GATEWAY: ARCHITECTURE OVERVIEW                             │
│                                                                             │
│   TEACH: How traffic flows from the internet to backend services            │
│          through a multi-layer edge infrastructure                          │
│                                                                             │
│                        Internet                                             │
│                           │                                                 │
│                     ┌─────▼─────┐                                           │
│                     │  Anycast  │  Route to nearest PoP                     │
│                     │  / GeoDNS │                                           │
│                     └─────┬─────┘                                           │
│                           │                                                 │
│                     ┌─────▼─────┐                                           │
│                     │  L4 Load  │  TCP distribution across gateways         │
│                     │  Balancer │  ECMP / least-connections                 │
│                     └─────┬─────┘                                           │
│                           │                                                 │
│              ┌────────────┼────────────┐                                    │
│              ▼            ▼            ▼                                    │
│         ┌────────┐  ┌────────┐  ┌────────┐                                  │
│         │  GW 1  │  │  GW 2  │  │  GW N  │   Stateless fleet                │
│         └───┬────┘  └───┬────┘  └───┬────┘                                  │
│             │           │           │                                       │
│    Per-instance processing pipeline (identical on every instance):          │
│    ┌────────────────────────────────────────────┐                           │
│    │  TLS → Parse → Auth → Rate Limit → Route   │                           │
│    │  → Circuit Break → Load Balance → Proxy    │                           │
│    │  → Response → Log                          │                           │
│    └────────────────────┬───────────────────────┘                           │
│                         │                                                   │
│            ┌────────────┼────────────┐                                      │
│            ▼            ▼            ▼                                      │
│       ┌─────────┐ ┌─────────┐ ┌─────────┐                                   │
│       │ User    │ │ Order   │ │ Search  │   Backend services                │
│       │ Service │ │ Service │ │ Service │   (private network)               │
│       └─────────┘ └─────────┘ └─────────┘                                   │
│                                                                             │
│   CONTROL PLANE (not on request path):                                      │
│   ┌─────────────────────────────────────────────────┐                       │
│   │  Config Store ──push──▶ Gateway instances       │                       │
│   │  Service Registry ──push──▶ Gateway instances   │                       │
│   │  Cert Store ──push──▶ Gateway instances         │                       │
│   └─────────────────────────────────────────────────┘                       │
│                                                                             │
│   KEY INSIGHT: Data plane (request processing) has NO external              │
│   dependencies. Control plane (config, registry) is separate.               │
│   If control plane is down → Gateway frozen at last config → SAFE.          │
│   If data plane is down → ALL traffic fails → NOT SAFE.                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 2: Request Processing Pipeline (Timing)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│           REQUEST PROCESSING PIPELINE: TIMING BREAKDOWN                     │
│                                                                             │
│   TEACH: Where time is spent in the gateway for a single request            │
│                                                                             │
│   Time (µs)   0    10   20   50   70   100  150                             │
│               │    │    │    │    │    │    │                               │
│               ├────┤                           Parse request (10µs)         │
│                    ├─────────────────────┤      JWT verify (50µs)           │
│                                         ├──┤   Rate limit check (20µs)      │
│                                            ├┤  Route match (5µs)            │
│                                             ├┤ Header transform (5µs)       │
│                                              ├┤LB select (2µs)              │
│                                               ├──────┤ Proxy setup (50µs)   │
│               │─── TOTAL GATEWAY OVERHEAD: ~142µs ───│                      │
│                                                                             │
│               ┤──────────────────────────────────────────────────┤          │
│               │     Backend processing: 50,000-500,000µs         │          │
│               │     (50ms - 500ms)                               │          │
│                                                                             │
│   INSIGHT: Gateway overhead is 0.03% of total request time.                 │
│   But if gateway overhead doubles (to 300µs), it's still only 0.06%.        │
│   The ABSOLUTE overhead matters more than the ratio.                        │
│   At 5M QPS: 142µs × 5M = 710 CPU-seconds/second                            │
│              300µs × 5M = 1,500 CPU-seconds/second (+111% CPU)              │
│   Percentage is misleading. Absolute CPU impact is significant.             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 3: Failure Isolation — Per-Backend Connection Pools

```
┌─────────────────────────────────────────────────────────────────────────────┐
│          FAILURE ISOLATION: WHY PER-BACKEND CONNECTION POOLS MATTER         │
│                                                                             │
│   TEACH: How connection pool design prevents cascading failure              │
│                                                                             │
│   BAD DESIGN: Shared connection pool                                        │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │  Gateway                                                    │           │
│   │  ┌───────────────────────────────────┐                      │           │
│   │  │  SHARED CONNECTION POOL (100 max) │                      │           │
│   │  │  ████████████████████████████████ │  ← ALL 100 blocked   │           │
│   │  │  (all waiting for slow backend)   │     by order-service │           │
│   │  └───────────────────────────────────┘                      │           │
│   │         │             │             │                       │           │
│   │    ┌────▼────┐   ┌────▼────┐   ┌────▼────┐                  │           │
│   │    │  User   │   │  Order  │   │  Search │                  │           │
│   │    │  Svc ✓  │   │  Svc 🐢 │   │  Svc ✓  │                  │           │
│   │    │(healthy)│   │ (SLOW)  │   │(healthy)│                  │           │
│   │    └─────────┘   └─────────┘   └─────────┘                  │           │
│   │                                                             │           │
│   │  RESULT: ALL services blocked. User and Search can't get    │           │
│   │  connections because Order is consuming all of them.        │           │
│   └─────────────────────────────────────────────────────────────┘           │
│                                                                             │
│   GOOD DESIGN: Per-backend connection pools                                 │
│   ┌─────────────────────────────────────────────────────────────┐           │
│   │  Gateway                                                    │           │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │           │
│   │  │ User Pool│  │Order Pool│  │Search    │                   │           │
│   │  │ (33 max) │  │ (33 max) │  │Pool (33) │                   │           │
│   │  │ ████░░░░ │  │ ████████ │  │ ██░░░░░░ │                   │           │
│   │  │ 12 used  │  │ 33 FULL  │  │ 8 used   │                   │           │
│   │  └────┬─────┘  └────┬─────┘  └────┬─────┘                   │           │
│   │       │             │             │                         │           │
│   │  ┌────▼────┐   ┌────▼────┐   ┌────▼────┐                    │           │
│   │  │  User   │   │  Order  │   │  Search │                    │           │
│   │  │  Svc ✓  │   │  Svc 🐢 │   │  Svc ✓  │                    │           │
│   │  │(healthy)│   │ (SLOW)  │   │(healthy)│                    │           │
│   │  └─────────┘   └─────────┘   └─────────┘                    │           │
│   │                                                             │           │
│   │  RESULT: Only Order affected. User and Search continue      │           │
│   │  normally with their own pools.                             │           │
│   │  Order requests: Get 503 (pool full) → Fast failure         │           │
│   │  User requests: Get 200 in normal time → Unaffected         │           │
│   └─────────────────────────────────────────────────────────────┘           │
│                                                                             │
│   This is the SINGLE MOST IMPORTANT design decision in a gateway.           │
│   Shared resources → Cascading failure.                                     │
│   Isolated resources → Contained failure.                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 4: Evolution Over Time

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   GATEWAY EVOLUTION: V1 → V2 → V3                           │
│                                                                             │
│   TEACH: How the gateway evolves as scale and requirements grow             │
│                                                                             │
│   V1: SINGLE REVERSE PROXY (startup)                                        │
│   ┌────────────────────────────────────┐                                    │
│   │  Client → nginx → 10 services      │                                    │
│   │  Config: Static file               │                                    │
│   │  Auth: In each service             │                                    │
│   │  Rate limit: None                  │                                    │
│   │  Scale: 1,000 QPS                  │                                    │
│   │  Cost: $50/month                   │                                    │
│   └──────────────┬─────────────────────┘                                    │
│                  │                                                          │
│   BREAKS AT: 50K QPS (single instance CPU), 50+ services (config mess),     │
│              first security incident (no centralized auth)                  │
│                  │                                                          │
│                  ▼                                                          │
│   V2: PROXY FLEET WITH EXTERNAL DEPENDENCIES                                │
│   ┌────────────────────────────────────┐                                    │
│   │  Client → LB → Envoy fleet (10)    │                                    │
│   │                  ↕ Redis (rate)    │                                    │
│   │                  ↕ Auth svc (JWT)  │                                    │
│   │  Config: xDS (dynamic)             │                                    │
│   │  Auth: JWT at gateway              │                                    │
│   │  Rate limit: Redis counters        │                                    │
│   │  Scale: 500K QPS                   │                                    │
│   │  Cost: $5,000/month                │                                    │
│   └──────────────┬─────────────────────┘                                    │
│                  │                                                          │
│   BREAKS AT: Redis on hot path (1-2ms per request), Redis SPOF,             │
│              500+ teams can't use centralized governance,                   │
│              no config validation (bad push = outage)                       │
│                  │                                                          │
│                  ▼                                                          │
│   V3: SELF-CONTAINED GATEWAY (this chapter)                                 │
│   ┌────────────────────────────────────┐                                    │
│   │  Client → Anycast → LB → GW fleet  │                                    │
│   │  Auth: Local JWT verify (cached)   │                                    │
│   │  Rate limit: Local counters        │                                    │
│   │  Routing: Compiled trie            │                                    │
│   │  Config: Push with validation      │                                    │
│   │  Scale: 5M+ QPS                    │                                    │
│   │  Cost: $50-80K/month               │                                    │
│   └────────────────────────────────────┘                                    │
│                                                                             │
│   KEY EVOLUTION INSIGHT:                                                    │
│   V1 → V2: Added capabilities (auth, rate limiting, dynamic config)         │
│   V2 → V3: REMOVED external dependencies from hot path                      │
│   The biggest improvement came from making the gateway MORE self-contained, │
│   not from adding MORE features.                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 18: Brainstorming, Exercises & Redesigns

## "What If X Changes?" Questions

```
Q1: "What if you need to support GraphQL at the gateway?"
  Challenge: GraphQL uses POST for all queries, path is always /graphql.
  → Path-based routing doesn't work (all requests go to same path).
  → Need to inspect request body (GraphQL query) for routing.
  → This violates "gateway doesn't inspect body" principle.
  
  Staff approach: Route ALL /graphql requests to a dedicated GraphQL service.
  The GraphQL service does query parsing, authorization, and backend aggregation.
  The gateway does NOT become a GraphQL engine.
  The gateway treats /graphql as a single route → Simple.

Q2: "What if traffic grows 100× overnight?"
  Challenge: 5M QPS → 500M QPS
  → 20 gateway instances → 2,000 instances (linear scaling)
  → Connection pool to each backend: 100 connections × 2,000 instances = 200,000
    connections PER backend → Backend can't handle 200,000 connections
  
  Staff approach: Introduce a mesh/sidecar layer between gateway and backend.
  Gateway routes to a regional proxy pool (fewer, larger instances).
  Regional proxy pool maintains connections to backends.
  This adds a hop but limits backend connection count.

Q3: "What if you need to support mutual TLS from all mobile clients?"
  Challenge: Mobile devices need client certificates → Certificate distribution.
  → Each device needs a unique cert → 50M certs to manage.
  → Certificate revocation at scale → CRL or OCSP infrastructure.
  → TLS handshake cost increases (client cert verification).
  
  Staff approach: Use device attestation (e.g., Android SafetyNet, iOS DeviceCheck)
  instead of mTLS for mobile. Reserve mTLS for server-to-server.
  Mobile auth: JWT tokens with device attestation claims.

Q4: "What if regulatory requirements mandate request body inspection?"
  Challenge: Gateway must inspect every request body for PII.
  → Body inspection adds 50-100µs per request.
  → Gateway must parse JSON/protobuf (protocol-specific).
  → False positives in PII detection → Blocked legitimate requests.
  
  Staff approach: Asynchronous inspection. Gateway forwards request immediately,
  logs the request body to an inspection pipeline. If PII found: Alert, don't
  block in real-time. For blocking use cases: Accept the latency cost.

Q5: "What if you need to support 10,000 distinct backend services?"
  Challenge: Route table grows 5× (2,000 → 10,000 routes).
  → Trie still O(path_depth) → No routing overhead increase.
  → But: Health checking 10,000 services × 20 instances = 200,000 checks/second.
  → Config size: 10,000 routes × 500 bytes = 5 MB → Still fits in memory.
  
  Staff approach: Centralized health checker (separate fleet).
  Gateway receives health state via push (not probing each backend).
  This decouples health checking from request processing.

Q6: "What if you need to support real-time bidirectional streaming?"
  Challenge: WebSocket and gRPC streaming are long-lived connections.
  → Gateway connection tracking: Millions of long-lived connections.
  → Load balancing: Can't rebalance mid-stream.
  → Circuit breaking: Per-connection, not per-request.
  
  Staff approach: Streaming goes through the gateway for auth and initial routing.
  After establishment: Gateway becomes a transparent proxy.
  For rebalancing: Wait for stream to close, then rebalance new streams.
  For health: Track stream-level metrics (duration, throughput, errors).
```

## Redesign Under New Constraints

```
REDESIGN 1: "Gateway budget is $1,000/month (startup)"
  Changes:
  → Use cloud API gateway (AWS/GCP) for routing and auth
  → No self-hosted infrastructure
  → Rate limiting: Simple per-IP (built into cloud gateway)
  → No circuit breaking (backends handle their own)
  → Logging: Cloud-native (CloudWatch, Stackdriver)
  → This is V1 optimized for cloud, not V3 on a budget

REDESIGN 2: "Zero external dependencies (air-gapped environment)"
  Changes:
  → Config stored on local disk (synced via internal tool)
  → Auth: mTLS only (no external token verification)
  → No cloud services (self-hosted everything)
  → Log shipping via internal message queue
  → Certificate management via internal PKI
  → This is the hardest constraint: Everything must be self-contained

REDESIGN 3: "Gateway must support 1 billion QPS (extreme scale)"
  Changes:
  → Anycast with per-PoP gateway fleets (100+ PoPs globally)
  → Hardware acceleration: FPGA/SmartNIC for TLS termination
  → Kernel bypass (DPDK) for packet processing
  → No per-request logging (counter-based metrics only)
  → Rate limiting: Token bucket in DPDK fast path (no kernel involvement)
  → This is CDN-edge level engineering (Cloudflare, Akamai territory)

REDESIGN 4: "Gateway must have zero added latency"
  Changes:
  → Eliminate JWT verification at gateway (backend does it)
  → Eliminate rate limiting at gateway (backend does it)
  → Gateway becomes a pure L7 load balancer (route only)
  → Total overhead: ~10µs (parsing + routing + proxy)
  
  Trade-off: No centralized security or traffic management.
  This is acceptable ONLY if all backends are trusted internal services.
```

## Failure Injection Exercises

```
EXERCISE 1: Kill one gateway instance during peak traffic
  1. Remove one instance from L4 LB rotation
  2. Observe: Connection redistribution time
  3. Measure: Error rate during redistribution
  4. Verify: Remaining instances handle increased load
  Expected: < 5 seconds of elevated errors, then normal

EXERCISE 2: Make one backend return 500 for 100% of requests
  1. Inject fault in user-service (all 500s)
  2. Observe: Circuit breaker opens (within 10 seconds)
  3. Verify: Other backends unaffected
  4. Remove fault → Verify: Circuit closes, traffic resumes
  Expected: Circuit opens in ~10s, other services unaffected

EXERCISE 3: Slow one backend to 10× normal latency
  1. Inject delay in order-service (200ms → 2000ms)
  2. Observe: Connection pool fills up
  3. Verify: Latency-based circuit breaker opens
  4. Verify: Other services unaffected (per-backend pools)
  Expected: Circuit opens within 30s, user-service unaffected

EXERCISE 4: Push bad route config
  1. Push config that sends /api/* to a non-existent backend
  2. Observe: Canary deployment to 1 instance
  3. Verify: Error rate spike on canary → Auto-rollback
  4. Verify: Other instances unaffected
  Expected: Bad config caught at canary, never reaches all instances

EXERCISE 5: Simulate DDoS (10× normal traffic)
  1. Generate 50M QPS of synthetic traffic
  2. Observe: Load shedding kicks in (low-priority traffic dropped)
  3. Verify: Authenticated user traffic prioritized
  4. Verify: Rate limits protect backends
  Expected: Authenticated traffic serves normally, anonymous traffic shed

EXERCISE 6: Expire TLS certificate in staging
  1. Let certificate expire without renewal
  2. Observe: All new connections fail (TLS handshake error)
  3. Verify: Monitoring detects cert expiry alert
  4. Renew certificate → Verify: Hot-swap, no restart needed
  Expected: Alert fires at 7-day mark, hot-swap restores in < 60s
```

## Trade-Off Debates

```
DEBATE 1: "Thin gateway vs Fat gateway"
  Thin: Route only. Auth, rate limiting, transformations in backends.
  Fat: Auth, rate limiting, transformation, caching, aggregation in gateway.
  
  Thin pros: Minimal overhead, clear ownership, easy to maintain.
  Fat pros: Centralized enforcement, single point of control.
  
  Staff position: "Thin-with-essential." Auth and rate limiting belong in the
  gateway (cross-cutting, security-critical). Transformation and aggregation
  belong in backends/BFFs (business logic, team-specific).

DEBATE 2: "Exact rate limiting vs Approximate rate limiting"
  Exact: Distributed consensus per request (Redis/consensus).
  Approximate: Local counters with periodic sync (±10%).
  
  Exact pros: Accurate quotas for billing/SLA enforcement.
  Approximate pros: Zero latency, no SPOF.
  
  Staff position: "Approximate for protection, exact for billing."
  Gateway rate limiting (protection): Approximate is fine (±10%).
  Billing metering (money): Exact, but measured ASYNCHRONOUSLY (not on hot path).

DEBATE 3: "Gateway-owned auth vs Backend-owned auth"
  Gateway: Verify JWT, inject identity headers, backends trust headers.
  Backend: Each service verifies JWT independently.
  
  Gateway pros: Consistent, centralized, one update point.
  Backend pros: No trust assumption on internal network, defense in depth.
  
  Staff position: "Gateway verifies, backends can re-verify."
  Gateway does PRIMARY auth (blocks unauthenticated traffic).
  Critical backends (payments) can RE-verify as defense in depth.
  Most backends trust gateway headers (simpler, faster).

DEBATE 4: "Monolithic gateway vs Shard-per-API gateway"
  Monolithic: One gateway fleet handles all APIs.
  Sharded: Separate gateway fleet per business domain (payments, users, etc.).
  
  Monolithic pros: Simpler operations, shared infrastructure.
  Sharded pros: Blast radius isolation (payment gateway failure doesn't affect users).
  
  Staff position: "Monolithic until proven otherwise."
  Sharding the gateway adds 3× operational overhead (3 fleets to manage).
  Only justified if: Regulatory isolation (PCI for payments) or extreme
  traffic concentration (one API consumes 80% of resources).

DEBATE 5: "Build vs Buy the API gateway"
  Build: Custom gateway on top of Envoy/nginx core.
  Buy: Cloud managed (AWS API Gateway, Kong, Apigee).
  
  Build pros: Full control, cost-effective at scale, customizable.
  Buy pros: Zero ops, fast to start, pre-built integrations.
  
  Staff position: "Buy until 500K QPS, then build."
  Below 500K QPS: Managed gateway is cheaper (total cost including engineering).
  Above 500K QPS: Cost differential justifies custom.
  The breakeven point is ~500K QPS for most organizations.

DEBATE 6: "Edge compute (WASM/V8 at gateway) vs Simple proxy"
  Edge compute: Run custom logic per-request at the gateway (Cloudflare Workers model).
  Simple proxy: Gateway only routes, auth, rate limits.
  
  Edge compute pros: Per-team customization, A/B test logic at edge, personalization.
  Simple proxy pros: Predictable performance, simple to operate, clear boundaries.
  
  Staff position: "Simple proxy for 95% of traffic. Edge compute ONLY for
  latency-critical, heavily-trafficked paths where saving one backend hop
  makes a measurable difference. Edge compute introduces unpredictable
  performance (user code quality varies) and operational complexity."

DEBATE 7: "Zero-trust internal network vs Trust-the-gateway model"
  Zero-trust: Every service re-verifies auth, even for internal calls.
  Trust-gateway: Services trust X-User-ID header from gateway.
  
  Zero-trust pros: Defense in depth, no trust boundary to exploit.
  Trust-gateway pros: Simpler, faster (no re-verification per service).
  
  Staff position: "Trust the gateway for most services. Zero-trust for
  crown jewels (payment processing, PII stores). The pragmatic approach
  is defense in depth WHERE IT MATTERS, not everywhere uniformly."

DEBATE 8: "Connection pooling per-instance vs per-backend"
  Per-instance: One pool per backend INSTANCE (fine-grained).
  Per-backend: One pool per backend SERVICE (coarser).
  
  Per-instance pros: Better load balancing, per-instance health tracking.
  Per-backend pros: Simpler management, fewer pools.
  
  Staff position: "Per-instance for large backends (>10 instances),
  per-backend for small backends (<10 instances). The choice depends
  on whether the additional granularity justifies the memory overhead."
```

## Additional Brainstorming Questions

```
Q7: "Your gateway is handling 5M QPS when a critical backend team
     deploys a bug that causes their service to return 500 for all
     requests. The circuit breaker opens. But this backend handles
     the login flow—users can't log in. What do you do?"
  
  Staff approach: Distinguish between circuit breaker response types.
  For login: Return a "degraded" login page (cached HTML, "try again in 5 min")
  instead of a raw 503 error. The gateway can serve a pre-configured
  fallback response for critical paths when the circuit is open.
  This is the "graceful degradation" pattern at the gateway level.

Q8: "A partner integration sends requests with consistently malformed
     headers. They account for 15% of your revenue. Rejecting their
     requests would lose revenue. Accepting malformed requests
     violates your HTTP parsing policy. What's your decision?"
  
  Staff approach: Create a "compatibility mode" for specific partners.
  Route partner's traffic (identified by API key) through a
  normalization middleware that fixes known malformations.
  Log every normalization for security review.
  Set a deadline: Partner must fix their client within 90 days.
  After deadline: Strict enforcement resumes.

Q9: "Your multi-region gateway has a split-brain scenario. US-East and
     EU-West both think they're the primary for rate limiting. Users
     in Europe are getting 2× their quota. How do you handle this?"
  
  Staff approach: Accept temporary over-admission during split-brain.
  2× quota for a few minutes < Rejecting legitimate users.
  When connectivity restores: Sync counters, catch up.
  Add guardrail: Even in split-brain, global rate limit (infrastructure
  protection) is enforced per-region independently.

Q10: "You need to migrate from nginx to Envoy without any downtime
      for 5M QPS of production traffic."
  
  Staff approach: Parallel deployment.
  Phase 1: Deploy Envoy fleet alongside nginx fleet.
  Phase 2: Route 1% of traffic to Envoy (via L4 LB weight).
  Phase 3: Compare metrics (latency, error rate, behavior).
  Phase 4: Gradually increase to 100% over 2-4 weeks.
  Phase 5: Decommission nginx fleet.
  Rollback at any phase: Shift traffic back to nginx in seconds.
```

## Additional Full Design Exercises

```
EXERCISE 7: Design a gateway for a healthcare platform (HIPAA compliance)
  Constraints:
  → All traffic must be encrypted end-to-end (TLS to backend)
  → Access logs must include patient data access audit
  → Response must not contain data from patients not in the request
  → Rate limiting must prevent data harvesting
  → Session management must comply with timeout requirements

EXERCISE 8: Design a gateway for an IoT platform (10M devices)
  Constraints:
  → 10M persistent connections (MQTT or WebSocket)
  → Devices have limited TLS capability (TLS 1.2, basic cipher suites)
  → Device authentication: Certificate-based (10M certs)
  → Bidirectional communication (push notifications to devices)
  → Intermittent connectivity (devices go offline/online frequently)

EXERCISE 9: Design a gateway for an internal microservice platform
  Constraints:
  → No external traffic (all internal service-to-service)
  → mTLS only (no JWT, no API keys)
  → Service-level authorization (not user-level)
  → Need: Circuit breaking, retry, timeout, observability
  → This is really a service mesh ingress, not an API gateway
```

---

# Summary

This chapter covered the design of an API Gateway / Edge Request Routing System from first principles through hyperscale production deployment.

The fundamental insight is that the API gateway is the most constrained component in a distributed system: it sits on the critical path of every request, must add minimal latency (< 5ms P99), and yet must provide authentication, rate limiting, routing, circuit breaking, and observability. Every design decision is a trade-off between capability and latency.

Key Staff Engineer principles established:

1. **No external dependencies on the hot path**: JWT verification is local (cached keys), rate limiting is local (synced counters), routing is local (compiled trie). The gateway's request processing touches nothing outside its own process.

2. **Per-backend failure isolation**: Connection pools, circuit breakers, and timeouts are per-backend. A slow order-service cannot affect the search-service through the gateway. This single design decision prevents the most common class of cascading failures.

3. **Config changes are more dangerous than code changes**: Route config is validated, canary-deployed, and auto-rolled back. A typo in a route config can redirect all traffic instantly—more damage than most code bugs.

4. **The gateway is a thin cross-cutting layer**: It handles authentication, rate limiting, routing, and observability. It does NOT handle response aggregation, business logic, or data transformation. Those belong in BFFs or backends.

5. **Federated governance scales**: At 500+ backend teams, centralized gateway configuration creates bottlenecks. Self-service route configuration with automated validation and guard rails provides velocity and safety.

An L5 might design a reverse proxy that routes requests to backends. An L6 designs a self-contained edge infrastructure that enforces security at sub-millisecond overhead, isolates backend failures from each other, manages traffic with surgical precision, and provides the single best observability point in the entire platform—all while being the most operationally reliable component in the system because everything depends on it.

---

### Remaining Considerations (Not Gaps):

1. **API versioning strategy** (URL vs header vs content negotiation) is an API design concern, not a gateway architecture concern
2. **GraphQL federation** is a specialization that uses the gateway but has its own architectural patterns
3. **Service mesh integration** (Istio/Envoy data plane) overlaps with but is distinct from edge gateway
4. **WAF (Web Application Firewall)** integration is a security specialization often deployed as a separate layer

These are intentional scope boundaries, not gaps.

### Pseudo-Code Convention:

All code examples in this chapter use language-agnostic pseudo-code:
- `FUNCTION` keyword for function definitions
- `IF/ELSE/FOR/WHILE/SWITCH` for control flow
- Descriptive variable names in snake_case
- No language-specific syntax
- Comments explain intent, not syntax

### How to Use This Chapter in Interview:

1. Start with the latency budget—"The gateway is on the hot path of every request, so I need to establish how much overhead I can afford"
2. Immediately identify that config/flag/auth reads must be LOCAL (no external calls on hot path)
3. Discuss per-backend failure isolation as the primary architectural decision
4. Distinguish between gateway responsibilities and BFF/backend responsibilities (scope discipline)
5. For rate limiting: Explain the local-counter-with-sync trade-off (±10% accuracy for 0ms latency)
6. Use the cascading failure timeline to demonstrate operational maturity
7. Mention federated governance when the interviewer asks about multi-team operations
8. Practice the brainstorming questions to anticipate follow-ups

---
