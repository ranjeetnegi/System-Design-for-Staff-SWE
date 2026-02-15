# Chapter 64: Bonus Advanced Topics — OIDC, gRPC, GraphQL, Webhooks, CQRS, and Warm Pools

---

# Introduction

This chapter covers the remaining gap topics that no existing Section 6 chapter addresses: **OpenID Connect (OIDC)**, **gRPC vs REST**, **GraphQL**, **Webhooks vs Polling**, **CQRS**, and **Warm Pools / Pre-warming**. These map to Topics 194, 302–305, and 315. At Staff level, you're expected to make informed choices among these—when to use OIDC vs plain OAuth, when gRPC beats REST, when GraphQL's flexibility is worth its complexity, when webhooks beat polling, when CQRS justifies separate read/write models, and how to eliminate cold starts before traffic arrives.

**The Staff Engineer's Bonus Topics Principle**: These aren't niche curiosities. OIDC powers "Sign in with Google" on millions of sites. gRPC runs most of Google's and Kubernetes' internal traffic. GraphQL powers Facebook, GitHub, Shopify. Webhooks are how Stripe, GitHub, and Slack push events. CQRS underlies many high-scale read-heavy systems. Warm pools are how Shopify and Netflix survive Black Friday. Know when each fits—and when it doesn't.

---

## Quick Visual: Bonus Topics at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   BONUS TOPICS: THE GAPS THAT STAFF ENGINEERS FILL                          │
│                                                                             │
│   L5 Framing: "We use OAuth, REST, maybe GraphQL, webhooks, CQRS, scaling"   │
│   L6 Framing: "OIDC for identity on top of OAuth; gRPC for internal traffic; │
│                GraphQL when clients need varied data; webhooks for push;     │
│                CQRS when read/write patterns diverge; warm pools for spikes"│
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  OIDC: OAuth = authorization. OIDC = authentication. ID token = who.   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  gRPC: HTTP/2, Protobuf, streaming. REST: HTTP/1.1, JSON. Match     │   │
│   │  protocol to consumer. Public → REST. Internal → gRPC.               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  GraphQL: Client-specified queries. Over/under-fetching solved.      │   │
│   │  N+1 and deep queries are your problems to solve.                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Webhooks: Server pushes. Polling: client pulls. Push when real-time  │   │
│   │  matters. Idempotency and quick 200 are mandatory.                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  CQRS: Commands vs queries. Separate stores when patterns diverge.   │   │
│   │  Eventual consistency. Event sourcing often paired.                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Warm Pools: Pre-provisioned compute. Pre-warm cache, connections,  │   │
│   │  DNS. Be ready before the spike. Black Friday doesn't wait.           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Bonus Topics Thinking

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **"Sign in with Google"** | "We use OAuth" | "OAuth gives access token (authorization). OIDC adds ID token (JWT with sub, name, email). We need identity—use OIDC. Validate ID token: signature, issuer, audience, expiry. Don't call userinfo endpoint for every request; ID token has it." |
| **Internal service communication** | "REST is fine" | "gRPC: 2–10x smaller payloads, HTTP/2 multiplexing, streaming, code generation. For service-to-service at scale, gRPC. For public API or browser clients, REST. Match protocol to consumer." |
| **Complex product page** | "Multiple REST calls" | "GraphQL: one query, exact fields. Product { name, price }, reviews(limit:3), seller { name }. Avoid over-fetching and under-fetching. Use DataLoader for N+1. Add depth limits and complexity scoring for protection." |
| **Payment notification** | "We poll for status" | "Webhooks. Stripe POSTs when payment completes. We respond 200 in <5s, enqueue processing, handle idempotency (event_id). Polling wastes resources; webhooks push when it matters." |
| **Read-heavy dashboard** | "Add read replicas" | "CQRS. Writes to normalized PostgreSQL. Events project to read-optimized store (Elasticsearch, denormalized table). Reads never touch write store. Scale independently. Accept eventual consistency for dashboard." |
| **Black Friday scaling** | "Auto-scale on CPU" | "Warm pool: pre-provision instances. Pre-warm cache with hot products. Pre-warm connection pools. Scale up warm pool 1–2 hours before midnight. Don't wait for the spike to react." |

**Key Difference**: L6 engineers match tools to constraints—who consumes the API, what consistency is needed, what the failure modes are. They don't default to familiar choices; they reason from requirements.

---

# Part 1: OpenID Connect vs OAuth (Topic 302)

## OAuth 2.0: Authorization Only

**OAuth 2.0** is an **authorization** framework. It answers: "Can this app access my resources?" The user grants permission. The app receives an **access token** with scopes (read photos, write calendar, etc.). The app can now act on the user's behalf against the provider's APIs. But the token does **not** identify the user. It says: "Someone with these permissions is making this request." Who? Unknown.

**Use case**: A backup app that syncs your Google Drive. It needs permission to read/write files. It might not care about your name—just that it's your drive. OAuth alone suffices.

## OpenID Connect: Identity Layer on Top

**OpenID Connect (OIDC)** is built **on top of** OAuth 2.0. It adds an **ID token**—a JWT. The ID token contains **user identity claims**: `sub` (subject/user ID), `name`, `email`, `picture`, `iss` (issuer), `aud` (audience), `exp` (expiry). The app decodes the JWT and knows *who* authorized the request. No extra API call. Identity + authorization in one flow.

**Use case**: "Sign in with Google" on a blog. The blog needs to know who you are—to show your name, avatar, and to create an account. OIDC. You get access token (if the app needs to call Google APIs) and ID token (for identity). Most "OAuth login" implementations are actually OIDC.

## OAuth vs OIDC: Key Difference

| | OAuth 2.0 | OpenID Connect |
|---|-----------|----------------|
| **Question** | "What can this app DO?" | "WHO is this user?" |
| **Token** | Access token (scopes) | ID token (JWT with claims) |
| **Purpose** | Authorization | Authentication |
| **User info** | Call /userinfo endpoint (extra round-trip) | In ID token (no extra call) |

**One-liner**: OAuth says "you can." OpenID Connect says "you are."

## OIDC Flow (High Level)

```
  USER          APP          IDENTITY PROVIDER (Google)

    |  "Sign in"   |
    |------------->|
    |              |  Redirect to Google
    |<-------------|
    |              |
    |  [Login at Google] ------>  User enters password
    |              |              <------ Authorization code
    |  Redirect back with code
    |<-------------|
    |              |
    |              |  Exchange code for tokens
    |              |  POST to token endpoint
    |              |  <------ Access Token + ID Token (JWT)
    |              |
    |  App decodes ID token: sub, name, email, picture
    |  Store in session. "Welcome, Ranjeet."
```

## ID Token Structure (JWT Claims)

```json
{
  "sub": "google-user-id-12345",
  "name": "Ranjeet Negi",
  "email": "ranjeet@example.com",
  "picture": "https://...",
  "iss": "https://accounts.google.com",
  "aud": "your-app-client-id",
  "exp": 1700000000,
  "iat": 1699996400
}
```

- **sub**: Subject—unique user ID. Use for account linking.
- **iss**: Issuer. Validate it matches expected provider.
- **aud**: Audience. Must be your app's client ID. Prevents token reuse by other apps.
- **exp**: Expiry. Reject expired tokens.

## Security: Validate Before Trusting

Never trust the ID token without validation:

1. **Verify signature**—JWT is signed (RS256, HS256). Validate with provider's public key (JWKS endpoint).
2. **Check issuer**—`iss` must match provider (e.g., `https://accounts.google.com`).
3. **Check audience**—`aud` must include your client ID.
4. **Check expiry**—`exp` must be in the future.
5. **Check nonce** (if used)—prevent replay attacks.

Libraries (e.g., `jsonwebtoken`, `python-jose`) handle this. Don't decode and trust blindly.

## When to Use OIDC vs OAuth Only

| Need | Use |
|------|-----|
| User identity (name, email, profile) | OIDC |
| Access to provider APIs (photos, calendar) only | OAuth (no identity needed) |
| "Sign in with X" | OIDC (need identity) |
| "Allow app to post on my behalf" | OAuth; OIDC if you also need identity |

**Practical**: Most "OAuth login" flows are OIDC. Make sure your library requests the `openid` scope and that you receive and validate the ID token.

---

# Part 2: gRPC vs REST (Topic 303)

## REST: Human-Readable, Universal

- **Protocol**: HTTP/1.1
- **Format**: JSON (usually)
- **Characteristics**: Human-readable, universal, browser-friendly, curl-able, Postman-friendly
- **Strengths**: Wide compatibility, easy debugging, third-party developer friendly, HTTP caching (URLs are cache keys)
- **Weaknesses**: Verbose payloads, no native streaming, one request per connection (without keep-alive), over/under-fetching

## gRPC: Binary, Fast, Typed

- **Protocol**: HTTP/2
- **Format**: Protocol Buffers (binary)
- **Characteristics**: Not human-readable, strongly typed, code generation
- **Strengths**: 2–10x smaller payloads than JSON, streaming (server, client, bidirectional), multiplexing (many requests over one connection), no head-of-line blocking, auto-generated clients
- **Weaknesses**: Not browser-native (need gRPC-Web proxy), can't curl it easily, tooling less mature for ad-hoc inspection

## Protocol Buffers: Schema-First

Define messages and services in `.proto`:

```protobuf
message User {
  int64 id = 1;
  string name = 2;
  string email = 3;
}

service UserService {
  rpc GetUser(GetUserRequest) returns (User);
  rpc ListUsers(ListUsersRequest) returns (stream User);
}
```

Compile with `protoc` → generate client and server code in Go, Java, Python, etc. Type-safe. Contract enforced. Change schema? Regenerate. Both sides update. No version mismatches hiding in production.

## Comparison Table: REST vs gRPC

| Property | REST | gRPC |
|----------|------|------|
| **Payload** | JSON (verbose) | Protobuf (compact) |
| **Streaming** | No (polling, WebSockets) | Yes (native) |
| **Browser support** | Native | gRPC-Web or proxy |
| **Caching** | URL-based, natural | Harder (POST body varies) |
| **Tooling** | curl, Postman, Swagger | Less universal |
| **Learning curve** | Low | Medium (schema, tooling) |
| **Typical use** | Public APIs, web, mobile | Internal microservices |

## When REST, When gRPC

| Consumer | Preferred |
|----------|------------|
| Public API, third-party devs | REST |
| Browser clients | REST |
| Mobile app (simple CRUD) | REST |
| Internal service-to-service | gRPC |
| High throughput, low latency | gRPC |
| Streaming (logs, real-time) | gRPC |
| Polyglot (Go, Java, Python services) | gRPC (code gen) |

**One-liner**: REST for the world. gRPC for your own backyard.

## ASCII Diagram: REST vs gRPC

```
REST:
  Client ---[HTTP/1.1, JSON]---> Server
  GET /users/123
  Response: {"id":123,"name":"Ranjeet","email":"r@x.com"}

gRPC:
  Client ---[HTTP/2, Protobuf binary]---> Server
  GetUser(UserRequest{id:123})
  Response: <binary blob, ~2-5x smaller>
```

## Staff Insight: Don't Use gRPC for Public API

You chose gRPC for your public API. "It's faster!" Third-party devs want curl, Postman, JSON. They get Protobuf. They need to generate clients from .proto. Adoption drops. Support tickets rise. You saved 50ms latency. You lost adopters. Public API → REST. Internal → gRPC.

### gRPC Streaming Patterns: Four Modes

| Mode | Client | Server | When Used | Real Example |
|------|--------|--------|-----------|--------------|
| **Unary** | 1 request | 1 response | Standard RPC, like REST | GetUser(id) → User |
| **Server streaming** | 1 request | N responses (stream) | Server pushes data over time | Stock prices, log tailing |
| **Client streaming** | N requests (stream) | 1 response | Client sends sequence; server aggregates | File upload, batch ingest |
| **Bidirectional** | Stream | Stream | Full duplex; both send as they want | Chat, real-time collaboration |

**Unary** (`rpc GetUser(GetUserRequest) returns (User)`): One request, one response. Same as HTTP. Use for: single item fetch, simple mutations.

**Server streaming** (`rpc StreamPrices(SubscribeRequest) returns (stream PriceUpdate)`): Client subscribes. Server sends PriceUpdate messages as they occur. Use for: **stock ticker** (prices stream to client), **log tail** (logs stream from server), **server-sent events** style.

**Client streaming** (`rpc UploadFile(stream Chunk) returns (UploadResult)`): Client sends Chunk messages (file pieces). Server accumulates, returns single result. Use for: **file upload** (client streams bytes), **batch metrics** (client streams many samples; server returns aggregate).

**Bidirectional** (`rpc Chat(stream Message) returns (stream Message)`): Both sides send and receive independently. Use for: **chat** (each client streams messages; receives others' messages), **real-time collaboration** (cursor positions, edits), **gaming** (player actions stream both ways).

```
    UNARY:                    SERVER STREAMING:
    Client ──Request──► Server  Client ──Request──► Server
    Client ◄─Response── Server  Client ◄─Msg1────── Server
                             Client ◄─Msg2────── Server
                             Client ◄─Msg3────── Server

    CLIENT STREAMING:          BIDIRECTIONAL:
    Client ──Chunk1──► Server   Client ──MsgA──► Server
    Client ──Chunk2──► Server   Client ◄─MsgB─── Server
    Client ──Chunk3──► Server   Client ──MsgC──► Server
    Client ◄─Result─── Server   Client ◄─MsgD─── Server
```

### gRPC-Web: gRPC in the Browser

Browsers don't speak gRPC natively. **gRPC-Web**: client speaks HTTP/1.1 or HTTP/2 with a special envelope; proxy (e.g., Envoy) translates to real gRPC. Trade-off: some features (e.g., streaming) may be limited. For browser clients that need gRPC, use gRPC-Web + proxy. For most web apps, REST or GraphQL is simpler.

### Schema Evolution and Backward Compatibility

Protobuf supports backward compatibility: add optional fields; old clients ignore them. Don't remove or renumber fields—breaks old clients. Use `reserved` for deprecated field numbers. For REST, versioning (e.g., `/v1/users`) is common. GraphQL: additive changes (new fields, deprecate old) preferred. gRPC + Protobuf handles evolution well when you follow the rules.

---

# Part 3: GraphQL (Topic 304)

## The Problem: Over-Fetching and Under-Fetching

**REST over-fetching**: `GET /users/123` returns 50 fields. You needed 3 (name, email, avatar). You pay for bandwidth and parsing you don't need.

**REST under-fetching**: Product page needs product, 3 reviews, seller name. That's 3 endpoints: `/products/123`, `/products/123/reviews?limit=3`, `/sellers/456`. Multiple round-trips. Waterfall. Slow on mobile.

## GraphQL: Client-Specified Queries

One endpoint. One request. Client specifies exactly what it needs:

```graphql
{
  user(id: "123") {
    name
    email
    orders(last: 5) {
      id
      total
    }
  }
}
```

Response: exactly those fields. No extra. No extra round-trips. Client is in control.

## Schema and Resolvers

GraphQL has a **strongly typed schema**. Types, fields, queries, mutations. Server enforces it. Client discovers via **introspection**. Resolvers: each field has a function that fetches data—from DB, another API, etc. Resolvers can run in parallel. Flexibility is high. But optimization is your responsibility.

## N+1 Problem

Naive implementation: query asks for 100 users, each with 10 orders. Resolver for `user.orders` runs per user. 1 user query + 100 order queries = 101 round-trips. **DataLoader** (or similar): batch and cache. Collect all "get orders for user X" requests; run one batched query; distribute results. Critical for GraphQL performance.

## Caching: Harder Than REST

REST: URL is cache key. `GET /users/123` → cache by URL. GraphQL: single endpoint, POST body varies. No natural cache key. Solutions: (1) Persisted queries—register queries by hash; client sends hash; cache by hash. (2) Field-level caching—cache by (type, id, field). (3) Apollo or similar: normalized cache with entity IDs.

## When GraphQL Fits, When It Doesn't

| Fits | Doesn't Fit |
|------|-------------|
| Complex UIs with varied data needs | Simple CRUD |
| Mobile vs web with different data | Public APIs (REST is standard) |
| Rapid frontend iteration | Heavy server-side joins, team unfamiliar |
| Many clients, one backend | Caching critical and simple REST works |

## Protection: Depth Limits and Complexity Scoring

A malicious or careless client can send: "Give me all users, each with all orders, each order with all line items, ..." Nested 7 levels. Hundreds of joins. Database melts. Add: (1) **Depth limit**—max 5 levels. (2) **Complexity scoring**—assign cost to fields; reject queries over threshold. (3) **Rate limiting**—per client, per query.

**One-liner**: REST gives you what the server decided. GraphQL gives you what you asked for. With great flexibility comes great responsibility.

### DataLoader: Batching and Caching

DataLoader batches requests within a single tick of the event loop. Resolver requests "orders for user 1." Instead of immediate DB call, DataLoader queues. At end of tick, one query: `SELECT * FROM orders WHERE user_id IN (1, 2, 3, ...)`. Distribute results. Also caches per request—same `user(id:1).orders` twice in one request? One DB call. Critical for GraphQL performance.

### Persisted Queries

Client sends query string. Server parses, validates, executes. For production, register queries: client sends hash; server looks up query. Benefits: (1) Smaller request (hash vs full query). (2) Cache by hash. (3) Reject unknown hashes—only allow pre-approved queries. Security and performance. Apollo and Relay support persisted queries.

### GraphQL vs REST: Decision Framework

| Factor | Prefer REST | Prefer GraphQL |
|--------|-------------|----------------|
| Data shape | Fixed per endpoint | Client-defined |
| Clients | Few, similar needs | Many, varied (web, mobile, partners) |
| Caching | URL-based, simple | Requires strategy (persisted, normalized) |
| Team familiarity | High | Lower (learning curve) |
| Over-fetching pain | Tolerable | High (mobile, slow networks) |
| Rapid iteration | Backend drives | Frontend drives (change query) |

### GraphQL vs REST Detailed Comparison

| Dimension | REST | GraphQL |
|-----------|------|--------|
| **Performance** | Multiple round-trips for nested data; over-fetching. Can batch with BFF. | Single request, exact fields. Risk: N+1 if resolvers naive; deep queries can be expensive. |
| **Caching** | HTTP cache: URL = key. CDN, browser, reverse proxy all work. | Single endpoint; cache key is query + variables. Requires persisted queries, normalized cache (Apollo), or field-level caching. |
| **Tooling** | curl, Postman, Swagger/OpenAPI, every HTTP client. Universal. | GraphQL Playground, Apollo DevTools. Less universal. Introspection for discovery. |
| **Team adoption** | Familiar to most developers. Low learning curve. | New paradigm. Resolvers, schema, N+1, complexity scoring. Steeper curve. |
| **Complexity** | Simple: resource per URL. Versioning via /v1/. | Schema design, resolver optimization, N+1, depth limits, complexity scoring. More moving parts. |

**When to migrate from REST to GraphQL**:
- Multiple clients (web, mobile, partners) with different data needs. REST forces many endpoints or over-fetching.
- Mobile suffers from over-fetching (slow networks, battery). GraphQL fetches exactly what the screen needs.
- Frontend iterates fast; backend changes lag. GraphQL lets frontend change queries without backend deploy.
- You're building a new product and expect varied UIs. GraphQL from day one can pay off.

**When to keep REST**:
- Simple CRUD, few clients, similar needs. REST is simpler.
- Public API for third-party developers. REST + OpenAPI is the standard; GraphQL requires more investment from consumers.
- Caching is critical and simple (e.g., CDN by URL). REST excels.
- Team has no GraphQL experience and timeline is tight. Don't add complexity without clear benefit.

---

# Part 4: Webhooks vs Polling (Topic 305)

## Polling: Client Pulls

Client repeatedly asks: "Any updates?" Every 5 seconds, every minute. Simple. Client controls timing. No need for server to know client URL. Works behind firewalls, NAT, mobile. **Cost**: Most requests return nothing. Wasteful. And if event happens between polls, you see it late. 1000 clients × 12 polls/min = 200 req/s of often-empty responses.

## Webhooks: Server Pushes

When event occurs, server POSTs to client's URL. Payment completed? POST. New order? POST. Efficient. Real-time. One event, one request. **Cost**: Client must expose public URL. Server must retry if client is down. Idempotency required—same event may be delivered multiple times.

## ASCII Diagram: Polling vs Webhook

```
POLLING:
  Client                    Server
    | --- GET /updates?t=0 --->  (nothing)
    | <--- [] -------------------|
    | --- GET /updates?t=60 ---> (nothing)
    | <--- [] -------------------|
    | --- GET /updates?t=120 ---> (event at t=95!)
    | <--- [event] --------------|
  (25 seconds delay)

WEBHOOK:
  Client                    Server
    | (listening)              |
    | <--- POST /webhook -------|  (event at t=95)
    | --- 200 OK -------------->|
  (Instant. One request.)
```

## Webhook Reliability

- **Retries**: Server retries on 5xx or timeout. Exponential backoff: 1 min, 5 min, 30 min, 2 hours... For days.
- **Idempotency**: Event has unique `event_id`. Client deduplicates. Process each event_id once. Same event_id, same result.
- **Quick 200**: Respond 200 in <5 seconds. If you process inline and take 30s, provider times out and retries. You process twice. Fix: accept webhook, enqueue to job queue, return 200. Process async.

## Webhook Security: Sign Payloads

Provider signs payload with shared secret (HMAC-SHA256). Header: `X-Webhook-Signature: sha256=abc123...`. Client verifies: `HMAC-SHA256(secret, body) == signature`. Reject if mismatch. Prevents forgery—attacker can't fake events without secret.

## When Polling, When Webhooks

| Use Polling | Use Webhooks |
|-------------|--------------|
| Client can't expose endpoint (firewall) | Real-time needed |
| Data changes rarely | High event frequency |
| Simple integration, no webhook support | Efficient resource usage |
| Mobile background limits | Server-initiated updates |

**One-liner**: Polling: you ask. Webhook: they tell you.

### Long Polling: Hybrid Approach

Client opens request. Server holds it open until new data arrives (or timeout). Then responds. Client immediately opens another. Reduces empty responses. Some real-time systems use this when WebSockets aren't feasible. Trade-off: connection held; server must manage many open connections. Used by some chat and notification systems.

### Webhook Payload and Retry Headers

Common headers: `X-Event-ID` (idempotency key), `X-Webhook-Signature` (HMAC), `X-Retry-Count` (how many retries so far). Stripe-style: `id` in body; store processed IDs; reject duplicates. Retry: exponential backoff. Dead letter after N retries. Alert on webhook failures. Monitor delivery success rate.

### When Polling Is Acceptable

- Health checks: "Is server up?" Poll every 30s. Simple.
- Low-frequency events: Check for updates every 5 minutes. Fine.
- Client behind strict firewall: Can't receive incoming. Poll.
- No webhook support from provider: Poll as fallback.

---

# Part 5: CQRS — Command Query Responsibility Segregation (Topic 194)

## Concept: Separate Write and Read Models

**Commands** change state. "Place order." "Update address." "Cancel subscription." They write. **Queries** return data. "What's my order status?" "List my subscriptions." They read. CQRS: separate the **model** for writing from the **model** for reading. Optimize each for its purpose.

## Why: Different Requirements

- **Writes**: ACID, validation, business rules, normalized schema.
- **Reads**: Speed, denormalization, different query patterns, scale independently.

Example: E-commerce. Write: place order (normalized tables, transactions). Read: "My last 50 orders with product names, prices" (denormalized view—orders + products in one table, optimized for "customer view").

## Implementation Patterns

### Simple CQRS (Same Database)

Separate command handlers and query handlers in code. Same database. Cleaner separation. No events. Less infrastructure. Start here.

### Advanced CQRS (Separate Stores)

- Write to normalized PostgreSQL.
- Publish event (OrderPlaced).
- Read side subscribes, updates denormalized store (Elasticsearch, Redis, materialized table).
- Queries hit read store. Fast. Eventually consistent with writes.

```
    CQRS: SEPARATE WRITE AND READ

    ┌─────────────┐                    ┌─────────────┐
    │  Command    │                    │   Query      │
    │ Place Order │                    │ My Orders?   │
    └──────┬──────┘                    └──────┬──────┘
           │                                   │
           ▼                                   ▼
    ┌─────────────┐    Event     ┌─────────────────────┐
    │ Write Store │ ───────────► │ Read Store          │
    │ (PostgreSQL)│   OrderPlaced│ (Elasticsearch,     │
    │             │              │  denormalized)      │
    └─────────────┘              └─────────────────────┘
```

## Consistency: Eventual

Read model lags behind write model. User places order. Immediately asks "Where is it?" Read model might not have updated. Options: (1) Command returns created data; don't need read model for confirmation. (2) Read from write store for that specific query (e.g., "my last order"). (3) Show "processing" until read model catches up. Design UX for eventual consistency.

## CQRS + Event Sourcing

Common combo. Write = append event to event log. Read = projection built from events. Event store is source of truth. Projections are derived. New read model? Replay events, build it. No schema change on write side. Powerful. Complex. Used in high-scale, event-heavy domains.

## When CQRS, When Not

| Use CQRS | Don't Use CQRS |
|----------|----------------|
| Read and write patterns diverge a lot | Simple CRUD |
| High read volume, complex queries | Low scale |
| Dashboards, search, feeds | Team not ready for complexity |
| Event-sourced systems | Strong consistency required for reads |

**One-liner**: CQRS = two counters. One for orders (writes). One for menu and status (reads). Optimize each.

### Sync Mechanisms: Events, CDC, Polling

- **Events**: Command publishes "OrderPlaced." Consumer updates read model. Decoupled. Eventual.
- **CDC (Change Data Capture)**: Tail DB transaction log. No app-level events. Debezium, etc. Use when you don't control write path.
- **Polling**: Read model polls write store. Simpler but laggy. Use for low-frequency sync.

### Read-After-Write Consistency in CQRS

User places order. Clicks "View order." Read model may not have it. Options: (1) Command returns full order; show that. Don't hit read model for confirmation. (2) "Read your writes" routing: for that user, read from write store (or primary) for recent writes. (3) Show "Order confirmed! Refreshing..." with short delay. Choose based on UX requirements.

### CQRS Without Event Sourcing

CQRS does not require event sourcing. Simple CQRS: same DB, separate handlers. Advanced CQRS: different stores, sync via events. Event sourcing: write = append events; read = project. You can do CQRS with events (OrderPlaced) without event sourcing (event log as source of truth). Event sourcing implies CQRS (events are write model; projections are read model). CQRS does not imply event sourcing.

---

# Part 6: Warm Pools and Pre-Warming (Topic 315)

## Cold Start: The Problem

Resources aren't ready when needed. **Lambda**: 500ms–5s to load. **Cache**: Empty after restart—every request misses, DB stampede. **EC2**: 2–5 minutes to boot, configure, join cluster. **Connections**: First request pays connection setup cost. By the time capacity is ready, the spike might be over—or users left.

## Warm Pool (Compute)

Pre-provisioned instances in standby. Not serving traffic. Booted. Configured. Ready. When auto-scaling triggers, warm pool instance joins in **seconds**. No 2-minute boot delay. AWS Auto Scaling warm pools. Trade-off: you pay for idle instances. For predictable spikes (Black Friday, product launch), worth it.

## Pre-Warming: Cache

Before routing traffic to a new or restarted cache, **fill it** with hot data. Script: query top 10,000 keys from DB. Load into cache. When traffic arrives, cache is warm. High hit rate from request one. No stampede. No DB overload.

## Pre-Warming: Connections

On server start, **eagerly** create all connections in the pool. Don't wait for first request. First request is fast. No "connection pool warming" period with high latency. Same for HTTP clients, gRPC channels.

## Pre-Warming: DNS

Pre-resolve DNS entries at startup. First request doesn't pay DNS resolution latency (often 50–200ms). Small optimization. Adds up at scale.

## Pre-Warming: JVM / Runtime

JIT compilation makes Java apps slow for first minutes. "Warm-up" by sending synthetic traffic. Or use GraalVM native images—no warm-up needed. Cold start is a problem for serverless (Lambda) and Java apps in containers.

## Event Preparation: Black Friday

Before midnight sale:

1. **Compute**: Scale up warm pool 1–2 hours before. Have extra instances ready.
2. **Cache**: Pre-warm with top products, sale prices, inventory. Know what will be hot. Load it.
3. **Connections**: Eager-init pools. Size for expected load.
4. **DNS**: Pre-resolve.
5. **Load test**: Run at expected peak. Validate. Don't rely on auto-scale to react—it's too slow.

```
    COLD SCALING                    WARM POOL SCALING

    Traffic spike ──► Need 10 more   Warm Pool: [ready][ready][ready]
                           │
                           ▼                Traffic spike ──► Take 5
              Boot 10 new EC2                      │
              (2-3 min each)                      ▼
                           │              Join cluster (10-30 sec)
                           ▼                      │
              Configure, join                          ▼
                           │              Serving (fast!)
                           ▼
              Ready (users already left)
```

## Staff Insight: Pre-Warm the Whole Chain

A company had a warm pool. Compute scaled beautifully. But they forgot to pre-warm the cache. Midnight. Every request was a cache miss. Database got hammered. 100x load. Database died. Warm pool couldn't save them—the bottleneck was downstream. Pre-warm compute, cache, connections, and any other cold component. Think end-to-end.

### Lambda and Serverless Cold Start

Lambda: first request (cold) loads runtime, fetches code, init. 500ms–5s. Subsequent requests (warm) reuse. Mitigations: (1) Provisioned concurrency—pay for always-warm instances. (2) Keep-warm ping—scheduled event every 5 min to prevent cold. (3) Smaller packages, fewer dependencies. (4) Consider other runtimes (e.g., custom runtime, smaller base image). For latency-sensitive APIs, cold start is a real constraint.

### Cache Pre-Warm Script Example

```python
# Pseudocode: Pre-warm cache before traffic
hot_keys = db.query("SELECT id FROM products ORDER BY view_count DESC LIMIT 10000")
for key in hot_keys:
    value = db.get(key)
    cache.set(key, value, ttl=3600)
```

Run before deploy or before traffic switch. Know your hot keys—analytics, access logs. Pre-warm what will be hit. Don't guess.

### Event Preparation Checklist

- [ ] Warm pool sized for expected peak
- [ ] Cache pre-warmed with hot data
- [ ] Connection pools eager-initialized and sized
- [ ] DNS pre-resolved
- [ ] Load test at expected peak
- [ ] Runbooks updated; team on call
- [ ] Monitoring and alerting verified

### Warm-up Strategies Checklist: Comprehensive Pre-Production

Pre-warm every layer before traffic. Timing estimates assume typical cloud environments.

| Layer | What to Pre-Warm | How | Timing Estimate |
|-------|------------------|-----|-----------------|
| **Compute (EC2/VMs)** | Warm pool instances | Pre-provision; scale up 1–2 hours before traffic | 1–2 hrs before peak |
| **Lambda/Serverless** | Provisioned concurrency | Set concurrency for critical functions | 30–60 min before; keep-warm ping every 5 min |
| **Cache (Redis/Memcached)** | Hot keys | Script: query top N keys from DB; SET into cache | 15–30 min before traffic switch |
| **Database connections** | Connection pool | Eager-init all connections on startup; don't lazy-connect | At deploy; 10–30 sec per pool |
| **Database (replicas)** | Replication lag | Ensure replicas caught up; avoid cold replicas | Monitor lag; 0–5 min typical |
| **DNS** | Resolution cache | Pre-resolve all dependent hostnames at startup | At deploy; 50–200 ms per hostname |
| **HTTP/gRPC clients** | Connection to dependencies | Create clients and establish connections | At deploy; 100 ms–2 sec per dependency |
| **JVM / Runtime** | JIT, class loading | Synthetic traffic to warm code paths; or GraalVM native | 2–5 min for JVM; native: 0 |
| **CDN** | Edge cache | Pre-fetch critical assets; or accept first-request miss | 5–15 min for propagation |
| **Load balancer** | Health checks | New instances must pass health before traffic | 30–60 sec per instance |
| **Service mesh** | mTLS, routing | Envoy/sidecar ready; connections established | 10–30 sec |
| **Kafka/Queue** | Consumer groups | Consumers joined; partitions assigned | 10–60 sec |

**Pre-production sequence (example)**:
1. **T-2 hours**: Scale warm pool. Start pre-warm scripts for cache.
2. **T-1 hour**: Verify cache warm. Run load test at 50% expected peak.
3. **T-30 min**: Final load test at 100% peak. Verify no errors.
4. **T-10 min**: Verify all health checks green. DNS resolved. Connections warm.
5. **T-0**: Traffic switch. Monitor error rate, latency, queue depth.

**Common warm-up mistakes**: (1) Warming compute but not cache—first requests all miss, DB stampede. (2) Warming only one layer—bottleneck moves downstream. (3) Starting warm-up too late—Lambda cold start takes 30+ seconds per concurrency; need time to provision. (4) Forgetting connection pools—first request pays 100ms+ for connection setup. (5) No load test before switch—assumptions may be wrong. Staff Engineers warm the full chain and validate with load before go-live.

---

# Summary: Key Takeaways

1. **OIDC**: OAuth = authorization. OIDC = authentication. ID token has identity. Validate before trusting. Use OIDC for "Sign in with X."

2. **gRPC vs REST**: REST for public, browser, third-party. gRPC for internal, high-throughput, streaming. Match protocol to consumer.

3. **GraphQL**: Client-specified queries. Solves over/under-fetching. N+1 and deep queries require care. DataLoader, depth limits, complexity scoring.

4. **Webhooks vs Polling**: Webhooks for real-time, efficiency. Polling when client can't expose endpoint. Webhooks: quick 200, idempotency, verify signature.

5. **CQRS**: Separate write and read models. Optimize each. Eventual consistency. Use when patterns diverge. Start simple; add separate read store when needed.

6. **Warm Pools**: Pre-provision compute. Pre-warm cache, connections, DNS. Be ready before the spike. Pre-warm the whole chain.

---

# Appendix: Interview One-Liners

- **"OIDC vs OAuth?"** — OAuth = what can you do. OIDC = who are you. ID token = JWT with identity claims.
- **"gRPC or REST?"** — Public API → REST. Internal services → gRPC. Match to consumer.
- **"GraphQL N+1?"** — DataLoader: batch and cache resolver calls. One query instead of N.
- **"Webhook reliability?"** — Quick 200, enqueue processing. Idempotency by event_id. Verify signature.
- **"When CQRS?"** — Read and write patterns diverge. High read volume. Complex queries. Accept eventual consistency.
- **"Warm pool?"** — Pre-provision instances. Join in seconds when scale-up triggers. Pre-warm cache and connections too.

---

# Extended Interview Q&A

**Q: "We're building a public API for third-party developers. OIDC, gRPC, or REST?"**  
A: REST for the API. OIDC for "Sign in with X" if you need identity. gRPC is not standard for public APIs—third parties expect JSON, curl, Postman. OIDC gives you user identity when they authenticate; REST gives them a familiar API surface.

**Q: "Our GraphQL API is slow. What do we check?"**  
A: (1) N+1 queries—DataLoader? (2) Deep queries—depth limits? (3) Expensive resolvers—caching? (4) Connection pool—enough for parallel resolvers? (5) Database indexes—match query patterns? Profile with Apollo Tracing or similar; find the bottleneck.

**Q: "Stripe webhooks are sometimes duplicated. How do we handle it?"**  
A: Idempotency by `event.id`. Store processed event IDs in DB or Redis. Before processing, check if already processed. If yes, return 200 and skip. Same event, same result. Never process payment twice. Respond 200 quickly; process async.

**Q: "When would you add CQRS to an existing system?"**  
A: When (a) read volume >> write volume, (b) read queries are complex (joins, aggregations) and don't match write schema, (c) you need to scale reads independently, or (d) you're adding event sourcing. Start with logical CQRS (separate handlers); add separate read store when benefits justify sync complexity.

**Q: "Black Friday in 2 weeks. How do we prepare?"**  
A: Warm pool: scale up 1–2 days before. Pre-warm cache: load hot products, prices, inventory. Load test at 2x expected peak. Verify auto-scale, failover, runbooks. Pre-warm connections. Have team on call. Don't rely on reactive scaling—it's too slow for a sharp spike.

## Staff Interview Walkthrough: "Design an API for a Multi-Client App"

**Interviewer**: "We have a web app, mobile app, and third-party developers. One backend. How do we design the API?"

**Strong Answer Structure**:

1. **Public API (third-party)**: REST. JSON. Versioned (`/v1/`). Documented (OpenAPI). Rate limited. OAuth or API keys for auth. Third parties expect REST; don't make them use gRPC or GraphQL unless they ask.

2. **Web and mobile (our clients)**: GraphQL if data needs are varied—web needs 20 fields, mobile needs 5. One schema, many query shapes. Avoid over-fetching on mobile. REST if needs are similar and simple. Consider BFF (Backend for Frontend)—thin GraphQL or REST layer that aggregates for each client.

3. **Internal services**: gRPC. High throughput, code generation, streaming. Not exposed to clients.

4. **Auth**: OIDC for "Sign in with Google." Access token for API calls. ID token for identity. Validate ID token; use for session.

5. **Real-time (if needed)**: WebSockets or SSE for our clients. Webhooks for third-party event notifications. Polling as fallback when webhooks aren't supported.

**Key Staff Signal**: Candidate differentiates by consumer—public vs internal vs own clients. They match protocol to audience. They consider auth (OIDC), real-time (webhooks vs polling), and don't force one solution everywhere.

---

# Cross-Topic Integration: How Bonus Topics Compose

Staff engineers see how these topics fit together in a real system. Consider an **e-commerce platform**:

- **OIDC** for "Sign in with Google"—identity. **OAuth** if you need "share to social"—authorization to post.
- **REST** for public product API (third-party marketplaces). **GraphQL** for your own web and mobile—varied data needs per screen. **gRPC** for internal services (inventory, pricing, orders).
- **Webhooks** from payment provider (Stripe)—payment confirmed. **Polling** as fallback if webhook delivery fails or for status checks.
- **CQRS** for order history: write to orders table; project to "orders by customer" read model. Dashboard reads from denormalized store. Eventual consistency.
- **Warm pools** for Black Friday: scale up compute and cache 1–2 hours before sale. Pre-warm with hot products.

Or a **SaaS with multi-tenant API**:

- **OIDC** for SSO (Okta, Auth0). **REST** or **GraphQL** for API—GraphQL if clients have varied needs (different dashboards).
- **Webhooks** for "notify me when X happens"—integrations, CI/CD triggers. **gRPC** for internal microservices.
- **CQRS** for analytics: write events; project to analytics store. Reads never hit write store.
- **Warm pools** for predictable peaks (monthly report generation, scheduled jobs).

The right combination depends on: who consumes the system, what consistency is needed, what the failure modes are, and what the team can operate.

---

# Decision Frameworks Summary

| Decision | Key Questions | Typical Answer |
|----------|---------------|----------------|
| OIDC vs OAuth | Do we need user identity? | OIDC for "who"; OAuth for "what can do" |
| gRPC vs REST | Who consumes? Internal or public? | gRPC internal; REST public |
| GraphQL vs REST | Varied client data needs? Over-fetching pain? | GraphQL when clients need different shapes |
| Webhook vs Polling | Can client receive push? Real-time needed? | Webhook when possible; polling fallback |
| CQRS | Read/write patterns diverge? Scale independently? | CQRS when justified by complexity |
| Warm pool | Predictable spike? Cold start unacceptable? | Warm pool + pre-warm for Black Friday–style events |

---

# Deep Dive: OIDC Flow — Step-by-Step with Sequence Diagram

## OIDC Authorization Code Flow (Detailed)

```
    CLIENT (SPA/App)          IDENTITY PROVIDER (Google, Okta)     REDIRECT
         │                              │                              │
         │  1. User clicks "Sign in"    │                              │
         │ ──────────────────────────► │                              │
         │  Redirect to:                │                              │
         │  /authorize?client_id=xxx    │                              │
         │  &redirect_uri=https://...   │                              │
         │  &response_type=code         │                              │
         │  &scope=openid profile email │                              │
         │  &state=random_csrf_token    │                              │
         │  &code_challenge=S256(...)   │  (PKCE)                      │
         │  &code_challenge_method=S256 │                              │
         │                              │                              │
         │  2. User authenticates (password, 2FA)                      │
         │                              │                              │
         │  3. IdP redirects to redirect_uri with:                     │
         │  ?code=auth_code_xyz         │                              │
         │  &state=random_csrf_token   │ ────────────────────────────► │
         │                              │                              │
         │  4. Client verifies state (CSRF)                            │
         │  5. POST /token             │                              │
         │  grant_type=authorization_code                              │
         │  code=auth_code_xyz         │                              │
         │  redirect_uri=...           │                              │
         │  code_verifier=original_random  (PKCE - matches challenge)   │
         │  client_id=...               │                              │
         │  (client_secret if confidential)                            │
         │ ──────────────────────────► │                              │
         │                              │                              │
         │  6. IdP returns:             │                              │
         │  { "access_token": "...",    │                              │
         │    "id_token": "jwt...",     │                              │
         │    "refresh_token": "...",   │                              │
         │    "expires_in": 3600 }      │                              │
         │ ◄────────────────────────── │                              │
         │                              │                              │
         │  7. Validate id_token. Create session.                       │
         │     Decode JWT. Use sub, name, email.                        │
         └─────────────────────────────┴──────────────────────────────┘
```

### Token Validation Checklist

Before trusting the ID token:

| Step | Check | How |
|------|-------|-----|
| 1 | **Signature** | Verify JWT signature with IdP's JWKS (public key). Reject if invalid. |
| 2 | **Issuer (iss)** | Must match expected IdP (e.g., `https://accounts.google.com`). |
| 3 | **Audience (aud)** | Must include your `client_id`. Prevents token reuse by another app. |
| 4 | **Expiry (exp)** | `exp` must be in the future. Clock skew: allow small buffer (e.g., 60s). |
| 5 | **Issued At (iat)** | Optional: reject if `iat` is too far in the past (replay). |
| 6 | **Nonce** | If you sent `nonce` in auth request, verify it matches in token. Prevents replay. |

### JWT Claims Explained

| Claim | Purpose |
|-------|---------|
| **sub** | Subject—unique user ID. Stable across sessions. Use for account linking. |
| **iss** | Issuer. Validate matches IdP. |
| **aud** | Audience. Your client_id. Must match. |
| **exp** | Expiration timestamp. Reject if past. |
| **iat** | Issued at. For replay detection. |
| **name** | Display name (OIDC profile scope). |
| **email** | Email (OIDC email scope). |
| **picture** | Profile picture URL. |
| **email_verified** | Boolean. Don't trust unverified email for critical flows. |

### PKCE for Public Clients

**Problem**: Authorization code can be intercepted (browser redirect, malicious app on same device). Attacker gets code, exchanges for tokens.

**PKCE (Proof Key for Code Exchange)**:
1. Client generates `code_verifier` (random 43–128 chars).
2. Client computes `code_challenge = BASE64URL(SHA256(code_verifier))`.
3. Auth request includes `code_challenge` and `code_challenge_method=S256`.
4. Token request includes `code_verifier`.
5. IdP verifies: `SHA256(code_verifier)` matches stored `code_challenge`.
6. Attacker with intercepted code can't get tokens without `code_verifier` (which never left the app).

**Use for**: SPAs, mobile apps, any client that can't keep a secret. Even confidential clients can use PKCE for defense in depth.

---

# Deep Dive: GraphQL Optimization Checklist

1. **DataLoader**: Batch and cache. Resolver for `user.orders`—batch all user IDs in same tick; one query. 2. **Depth limit**: Reject queries nested > 5 levels. 3. **Complexity score**: Assign cost to fields (e.g., `users` = 10, `orders` = 1). Reject if total > 1000. 4. **Persisted queries**: Register allowed queries; client sends hash. Cache by hash. 5. **Query timeout**: Kill long-running queries. 6. **Connection limits**: Paginate lists (`first: 10`). No "give me all users." 7. **Indexing**: Resolvers hit DB—ensure indexes match query patterns. Profile with Apollo Tracing or similar. GraphQL flexibility is powerful; it's also a DoS vector if unconstrained.

---

# Deep Dive: CQRS Implementation Patterns

**Same DB, different handlers**: Simplest. CommandHandler and QueryHandler. Different code paths. Same tables. Good starting point. **Separate read store**: Write to PostgreSQL. Publish event. Consumer updates Elasticsearch or materialized table. Reads from read store. Sync lag: seconds to minutes. **CQRS + Event Sourcing**: Write = append to event log. Read = project from events. Event store is source of truth. Add new read model? Replay events. Powerful. Complex. **CDC for sync**: Don't want app-level events? Use Debezium (or similar) to tail PostgreSQL WAL. Publish changes to Kafka. Consumers update read stores. App stays simple; sync is infrastructure. Choose based on: who owns the write path, how complex is the projection, what's the acceptable lag.

### CQRS Implementation Patterns (Detailed)

**Simple CQRS — Two models, same DB**:
```
    ┌─────────────┐                    ┌─────────────┐
    │  Command   │                    │   Query     │
    │ PlaceOrder │                    │ GetOrders   │
    └──────┬──────┘                    └──────┬──────┘
           │                                  │
           │         ┌──────────────┐         │
           └────────►│   PostgreSQL │◄────────┘
                     │ (same DB)    │
                     └──────────────┘
    CommandHandler: validation, business rules, write.
    QueryHandler: read-optimized queries, maybe different indexes.
```

**Advanced CQRS — Separate read store**:
```
    ┌─────────────┐                    ┌─────────────────────┐
    │  Command   │                    │      Query          │
    └──────┬──────┘                    └──────────┬──────────┘
           │                                      │
           ▼                                      ▼
    ┌─────────────┐    Event/CDC    ┌─────────────────────┐
    │ Write Store │ ──────────────► │ Read Store          │
    │ PostgreSQL  │  OrderPlaced   │ Elasticsearch /     │
    │ normalized  │  or Debezium   │ Materialized View   │
    └─────────────┘                 └─────────────────────┘
```

**CQRS + Event Sourcing**:
```
    ┌─────────────┐     ┌─────────────┐    Replay    ┌─────────────────┐
    │  Command   │────►│ Event Store │ ───────────►│ Read Model(s)   │
    └─────────────┘     │ Append-only │              └─────────────────┘
                        └─────────────┘
    Event store = source of truth. New read model? Replay events.
```

**Sync mechanisms**: App events (100ms–1s lag), CDC/Debezium (1–5s), Polling (seconds–minutes).
