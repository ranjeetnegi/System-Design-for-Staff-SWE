# Basics Chapter 2: APIs, Frontend, Backend, and Databases — The Building Blocks

---

# Introduction

APIs, frontend, backend, and databases are the building blocks of almost every software system. An **API** defines how software components communicate. The **frontend** is what users see; the **backend** does the work. The **database** persists the data. These concepts seem straightforward—and yet, at Staff level, the decisions you make about APIs (versioning, contracts, boundaries), the frontend/backend split (BFF, rendering strategy), and database choice (SQL vs NoSQL, read/write patterns) shape system scalability, team structure, and long-term maintainability.

This chapter takes you from the basics to Staff-level thinking. We'll explore APIs as contracts and organizational boundaries, the frontend/backend split and when it matters, and databases as the hardest thing to scale—and why Staff engineers obsess over data modeling and query patterns.

---

# Part 1: What is an API? (From Simple to Staff-Level)

## API = Application Programming Interface = A Contract

An **API** is a contract between two pieces of software. It defines:
- **What** can be requested (endpoints, operations)
- **How** to request it (format, headers, auth)
- **What** will be returned (shape of response, error codes)

Just as a restaurant menu defines what you can order and how to order it, an API defines what a client can ask for and what it will receive. The client doesn't access the server's internals—it goes through the API.

## REST API: Resources, Endpoints, HTTP Methods

**REST** (Representational State Transfer) models the world as **resources** accessed via **URLs** and operated on with **HTTP methods**:

| HTTP Method | Typical Use | Example |
|-------------|-------------|---------|
| GET | Read | `GET /users/123` → fetch user |
| POST | Create | `POST /users` → create user |
| PUT | Replace | `PUT /users/123` → replace user |
| PATCH | Partial update | `PATCH /users/123` → update fields |
| DELETE | Delete | `DELETE /users/123` → delete user |

Resources are nouns (`/users`, `/orders`). Actions are implied by the method. This maps cleanly to **CRUD** (Create, Read, Update, Delete).

**REST design patterns**:
- **Nested resources**: `GET /users/123/orders` for a user's orders
- **Filtering**: `GET /orders?status=pending&limit=10`
- **Pagination**: `GET /users?cursor=xyz&limit=20` (cursor) or `?page=2&per_page=10` (offset)
- **Field selection**: `GET /users/123?fields=id,name,email` (if supported)

### REST Conventions

- **Idempotency**: GET, PUT, DELETE are idempotent (same request, same result). POST is not (creates new resource each time). For payment and other critical operations, use idempotency keys so retries don't double-charge.
- **Stateless**: Each request carries everything needed; no server-side session required for the API contract.
- **HTTP status codes**: 200 OK, 201 Created, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 429 Too Many Requests, 500 Internal Server Error—convey outcome clearly so clients can handle them.

## API as a Product: Versioning, Documentation, Backward Compatibility

### Why This Matters at Scale

When your API has 10 consumers, a breaking change might mean 10 updates. When it has 10,000 (internal services, mobile app versions, partner integrations), a breaking change can cause cascading failures and require months of coordinated migration. Staff engineers treat API stability as a first-class concern: deprecation timelines, changelogs, and compatibility tests in CI.

At Staff level, APIs are treated as **products**. They have:
- **Consumers** (frontend, mobile, partners, other services)
- **Contracts** that must remain stable
- **Lifecycles** (versioning, deprecation, sunset)

**Versioning** strategies:
- **URL**: `/v1/users`, `/v2/users` — explicit, easy to route, clear in logs and docs. Most common for REST. Downside: URL clutter, multiple versions in codebase.
- **Header**: `Accept: application/vnd.api+json;version=2` — cleaner URLs, version is in request metadata. Requires client cooperation. Harder to debug (version not visible in URL).
- **Query**: `?version=2` — less common; mixes version with resource semantics. Avoid for critical APIs.
- **Custom header**: `X-API-Version: 2` — similar to Accept but simpler. Some prefer for internal APIs.

**Backward compatibility**: Once an API is in use, changing it can break consumers. Staff engineers adopt **expand-contract** or **additive-only** practices: add new fields, don't remove or rename. Deprecation is planned and communicated. A **changelog** and **deprecation policy** (e.g., "we support each version for 12 months after the next major release") set expectations and reduce surprise.

**Versioning granularity**: Version the whole API (all endpoints move together) vs. version per resource (e.g., `/v1/users` and `/v2/orders` can coexist). Whole-API is simpler; per-resource allows incremental migration but increases complexity. Most companies start with whole-API versioning.

## Internal vs. External vs. Partner APIs

| API Type | Consumers | Concerns |
|----------|-----------|----------|
| **Internal** | Your own services | Speed, flexibility; may use RPC/gRPC |
| **External** | Public developers, third parties | Stability, documentation, rate limits, auth |
| **Partner** | Specific business partners | Custom SLAs, dedicated support, sometimes different schemas |

**Staff-level implication**: Internal APIs can evolve faster (you control all consumers). External and partner APIs require formal versioning, deprecation notices, and often dedicated documentation and support. The same backend might expose different API "surfaces" for each.

## API Design Principles Staff Engineers Care About

### Consistency

- Same patterns across endpoints: `/users/{id}`, `/orders/{id}` — not `/users/{id}` and `/getOrder?id=`
- Consistent error format: `{"error": {"code": "...", "message": "..."}}`
- Consistent pagination: cursor vs. offset, but same across the API

### Predictability

- Same input → same output (deterministic)
- Documented behavior for edge cases (e.g., what happens on duplicate POST?)
- Clear idempotency semantics for mutating operations

### Evolvability

- Additive changes don't break clients
- Optional fields, not required new fields, for new features
- Versioning strategy that doesn't require "big bang" migrations

## API Design Principles Deep Dive

Beyond high-level consistency, Staff engineers apply specific conventions that make APIs predictable, evolvable, and pleasant to consume. These principles reduce integration bugs, speed up onboarding, and prevent breaking changes.

### Naming Conventions: `/users/:id` vs `/getUser?id=`

**Prefer resource-oriented URLs and HTTP methods over verb-based RPC-style paths.**

| Bad | Good | Why |
|-----|------|-----|
| `GET /getUser?id=123` | `GET /users/123` | REST uses nouns and methods. "get" is redundant with GET. |
| `POST /createOrder` | `POST /orders` | Resource is "orders"; action is create (implied by POST). |
| `GET /deleteUser/123` | `DELETE /users/123` | Use HTTP method for action. |
| `POST /users/123/updateEmail` | `PATCH /users/123` with body `{"email": "..."}` | Partial update = PATCH. |
| `GET /fetchUserOrders?userId=123` | `GET /users/123/orders` | Nest sub-resources. Path conveys relationship. |

**Consistency rule**: Always use plural nouns for collections (`/users`, `/orders`). Always nest sub-resources (`/users/123/orders` not `/orders?userId=123` for "user's orders"). This makes the API self-describing: `/users/123/orders` clearly means "orders belonging to user 123."

### Error Response Format: Standard Structure

Every error response should follow the same structure so clients can parse and handle them uniformly.

**Standard error body**:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid email format",
    "details": [
      {
        "field": "email",
        "issue": "Must be a valid email address"
      }
    ],
    "request_id": "req_abc123",
    "timestamp": "2025-02-15T10:30:00Z"
  }
}
```

| Field | Purpose |
|-------|---------|
| `code` | Machine-readable; clients can switch on it. Use UPPER_SNAKE_CASE. |
| `message` | Human-readable; for logging and display. |
| `details` | Optional; for validation errors, list field-specific issues. |
| `request_id` | For support and debugging; client can include in bug reports. |
| `timestamp` | For debugging and audit. |

**HTTP status codes**: Map errors to the right status. 400 for client errors (validation, bad request). 401 for unauthenticated. 403 for unauthorized. 404 for not found. 429 for rate limit. 500 for server errors. Don't return 200 with an error payload—that breaks HTTP semantics and client libraries.

### Pagination: Cursor vs Offset

| Approach | Pros | Cons | When to Use |
|----------|------|------|-------------|
| **Offset** (`?page=2&per_page=20`) | Simple, stateless, can jump to any page | Breaks when data changes between requests (items shift, duplicates, gaps) | Static or slowly changing data; admin UIs |
| **Cursor** (`?cursor=abc123&limit=20`) | Stable under mutating data; no duplicates or gaps | Can't jump to arbitrary page; slightly more complex | Feeds, time-ordered lists, real-time data |

**Cursor format**: Return a cursor in the response. Client sends it back for the next page. Opaque to client (base64-encoded offset or keyset). Example:
```json
{
  "data": [...],
  "next_cursor": "eyJpZCI6MTAwfQ==",
  "has_more": true
}
```

**Limit conventions**: Support `limit` with a max (e.g., default 20, max 100). Reject over-limit with 400. Consistent across all list endpoints.

### Filtering and Sorting Conventions

- **Filtering**: `GET /orders?status=pending&created_after=2025-01-01`. Use query params. Same param names across similar resources (`status`, `created_after`, `user_id`).
- **Sorting**: `GET /orders?sort=created_at&order=desc`. Or `sort=-created_at` (minus = desc). Be consistent.
- **Field selection** (if supported): `GET /users/123?fields=id,name,email` to reduce payload. Optional but valuable for mobile.

### Good API vs Bad API Examples

**Bad**:
```
GET /api/getUserProfile?id=123        ← Verb in path, query for id
POST /api/user/123/update             ← update is redundant with PATCH
GET /api/orders?page=1                ← Offset on rapidly changing data
Error: {"msg": "something went wrong"} ← No code, no request_id
```

**Good**:
```
GET /api/users/123                     ← Resource + id in path
PATCH /api/users/123                   ← Method implies update
GET /api/orders?cursor=xyz&limit=20   ← Cursor for orders
Error: {"error": {"code": "NOT_FOUND", "message": "...", "request_id": "req_123"}}
```

## API as Organizational Boundary (Conway's Law)

**Conway's Law**: "Organizations design systems that mirror their communication structure."

APIs often become **team boundaries**. The User Team owns the User API. The Order Team owns the Order API. When Service A needs user data, it doesn't query the User Team's database—it calls the User API. The API encapsulates the team's domain and allows independent evolution.

**Staff-Level Insight**: API design is org design. Poorly designed APIs create coupling between teams (e.g., "we need to change our API but it would break the Order Team"). Good APIs let teams move at different speeds and with different deployment cycles. When you propose an API boundary, you're implicitly proposing a team boundary.

## API as Organizational Boundary: Expanded

Conway's Law isn't just observation—it's leverage. The most successful tech companies have explicitly used API boundaries to shape how teams work. Understanding this helps you design APIs that enable, rather than constrain, organizational scale.

### The Amazon API Mandate (Bezos Memo)

The often-cited "Bezos memo" (circa 2002) mandated that all teams would expose their data and functionality through service interfaces. Key points that have been widely reported:

- **No direct database access across teams**: Team A cannot query Team B's database. They must go through Team B's API.
- **Interfaces must be designed to be exposed externally**: APIs had to be well-documented and stable enough that they could be used by external developers—even if initially only internal.
- **Communication via APIs only**: Teams that wanted to cooperate had to do so through well-defined interfaces, not ad-hoc queries or shared databases.

The effect: Teams became loosely coupled. The User Team could change their database schema, add features, or migrate storage—as long as their API contract held. The Order Team didn't break. This decoupling is why Amazon could scale to thousands of services and teams without coordination hell.

### How API Contracts Between Teams Are the Most Important Design Decision

When Team A depends on Team B's API:

1. **Team B owns the contract**: They cannot change it unilaterally. Breaking changes require coordination, versioning, or a migration period.

2. **Team A's velocity depends on Team B's stability**: If Team B's API is flaky or changes frequently, Team A spends time fixing integrations instead of building features.

3. **The API is the agreement**: There's no "we'll just talk to the DB" or "we have a handshake." The API *is* the contract. It must be precise, versioned, and documented.

**Staff-level implication**: When you're designing a system that multiple teams will consume, the API contract is your most important deliverable. Get it right upfront—data shapes, error codes, pagination, idempotency. Changing it later is costly.

### Breaking API Changes = Breaking Trust

A "breaking change" isn't just a technical event—it's a breach of trust with consumers.

**What counts as breaking**:
- Removing or renaming a field
- Changing the type or meaning of a field
- Changing error codes or status codes
- Removing an endpoint
- Changing pagination behavior (e.g., offset to cursor with different semantics)
- Changing ordering or sorting defaults

**What's usually safe (additive)**:
- Adding new optional fields
- Adding new endpoints
- Adding new error codes (clients that don't know them can treat as generic)
- Adding new query parameters with defaults

**Process for breaking changes**:
1. **Deprecation period**: Announce the change. Give consumers 3–6–12 months to migrate.
2. **Versioning**: Expose the new behavior under `/v2/` or a version header. Keep v1 until deprecation ends.
3. **Communication**: Changelog, email, Slack. Don't assume everyone reads the docs.
4. **Monitoring**: Track usage of deprecated endpoints. Proactively reach out to stragglers.

**Staff-level**: "We'll just update the API" is a Junior move. "We'll add a new optional field, deprecate the old one in 6 months, and migrate our known consumers before we remove it" is Staff-level.

**Real-world example**: A major e-commerce company renamed a field in their checkout API (`price` → `unit_price`). They didn't deprecate—they made a breaking change. Several partner integrations broke. Support tickets surged. They had to revert and run both fields in parallel for a year. The cost of "we'll just change it" was far higher than a disciplined deprecation would have been. Staff engineers learn from such incidents and build process to prevent them.

## When APIs Become the Bottleneck

At scale, the API layer often introduces:
- **Rate limiting**: Protecting backend from abuse, but also limiting legitimate use
- **Authentication/authorization**: Every request validated—adds latency
- **API gateway**: Single point for routing, auth, logging—can become a bottleneck
- **Throttling**: Deliberate slowdown under load

Staff engineers design for this: **horizontal scaling** of API gateways, **caching** of auth decisions, **connection pooling** to backends, and **circuit breakers** when backends are slow.

## ASCII Diagram: Client ↔ API ↔ Services

```
    ┌─────────────┐
    │   CLIENT    │  (Browser, mobile app, partner system)
    │             │
    └──────┬──────┘
           │
           │  HTTPS Request
           │  (auth, rate limit checked here)
           ▼
    ┌─────────────────────────────────────┐
    │           API GATEWAY                │  ◄── Contract boundary
    │  • Routing    • Auth    • Rate limit  │
    │  • Logging    • Throttling           │
    └──────┬──────────────────────────────┘
           │
     ┌─────┴─────┬─────────────┐
     ▼           ▼             ▼
┌─────────┐ ┌─────────┐ ┌─────────┐
│ User    │ │ Order   │ │ Payment │
│ Service │ │ Service │ │ Service │
└─────────┘ └─────────┘ └─────────┘
     
     The API defines WHAT clients can access.
     Services implement HOW.
```

### L5 vs L6: API Thinking

| Aspect | L5 Thinking | L6 Thinking |
|--------|-------------|-------------|
| **Design** | "I'll add an endpoint for that" | "How does this fit our resource model? What's the versioning story?" |
| **Changes** | "We'll update the API" | "We'll add a new optional field; deprecate the old one in 6 months; consumers migrate" |
| **Ownership** | "The backend team owns it" | "This API is the boundary between Team A and Team B; both need to agree on changes" |
| **Scale** | "We'll add more servers" | "We need to scale the gateway, cache auth, and consider read replicas for high-traffic GETs" |

---

# Part 2: Frontend vs Backend — Why the Split Matters

## Frontend: What the User Sees and Interacts With

The **frontend** is the presentation layer—what runs in the browser or on the mobile device. It handles:
- **UI** (layout, styling, interactions)
- **User input** (clicks, forms, gestures)
- **Display of data** (rendering JSON/HTML from the backend)

Technologies: HTML, CSS, JavaScript (React, Vue, etc.), Swift/Kotlin for native mobile.

## Backend: Business Logic, Data, Integrations

The **backend** runs on servers. It handles:
- **Business logic** (validation, authorization, workflows)
- **Data storage and retrieval** (database access)
- **Integrations** (payment providers, email, third-party APIs)
- **Security** (auth, encryption, rate limiting)

Users don't see the backend. They see the result of its work.

## BFF (Backend for Frontend) Pattern

Different clients have different needs:
- **Web**: May need HTML for SEO, rich layout
- **Mobile**: May need smaller payloads, different auth (tokens), offline support
- **Desktop**: May need different data shapes

A **BFF** is a backend service tailored to a specific frontend. Instead of one generic API for all clients, you have:
- `web-bff` — serves web-specific needs
- `mobile-bff` — serves mobile-specific needs

**Why**: One-size-fits-all APIs lead to over-fetching (mobile gets fields it doesn't need) or under-fetching (mobile needs multiple round-trips). A BFF aggregates and shapes data for its client.

```
    ┌─────────┐     ┌─────────────┐
    │ Web App │────►│  Web BFF    │
    └─────────┘     └──────┬──────┘
                          │
    ┌─────────┐     ┌──────┴──────┐
    │ Mobile  │────►│ Mobile BFF  │
    │  App    │     └──────┬──────┘
    └─────────┘            │
                           │
                    ┌──────┴──────┐
                    │   Shared    │
                    │  Services   │
                    └─────────────┘
```

**Staff-level trade-off**: BFFs add services and teams to maintain. They shine when web and mobile have meaningfully different needs. If both consume the same data in the same way, a single API may suffice.

**When to add a BFF**: Web needs HTML for SEO; mobile needs JSON and smaller payloads. Web needs full product details; mobile needs a summary for list view. Web and mobile have different auth flows (session vs. token). If you're building both and the data shapes diverge, a BFF per client type reduces over-fetching and under-fetching. If you're API-first and both clients consume the same resources, a shared API is simpler.

**When to skip a BFF**: Early-stage product; one client type; or clients that need identical data. Adding a BFF prematurely adds operational overhead (another service to deploy, monitor, scale) without clear benefit. You can always add one later when client needs diverge.

## Thin Client vs. Thick Client

| Model | Where Logic Lives | Example |
|-------|-------------------|---------|
| **Thin client** | Mostly on server | Traditional server-rendered pages; client does minimal work |
| **Thick client** | Mostly on client | SPAs: client fetches data, does routing, state, rendering |

**Staff-level implication**: Thin clients reduce client complexity and improve first-load performance (server sends ready-to-render HTML). Thick clients enable rich interactivity and can reduce server load (client-side routing, caching). The choice affects latency, SEO, and where you invest engineering effort.

## Why Staff Engineers Care: Boundary as Architectural Decision

The frontend/backend boundary determines:
- **Who owns UX** (frontend) vs. **who owns correctness** (backend)
- **Where caching lives** (CDN for static assets, client cache for API responses, server cache for DB)
- **How to scale** (frontend scales with users/devices; backend scales with request volume and data)

**Staff-Level Insight**: The frontend/backend split isn't just technical—it's about ownership and scalability. A team that owns both can move fast but may create tight coupling. Separate teams need clear contracts (APIs) and shared understanding of SLAs. The boundary is where you draw the line for deployability, testability, and team autonomy.

## Rendering Strategies: SSR, CSR, SSG, Hydration

| Strategy | When Content is Rendered | Best For |
|----------|--------------------------|----------|
| **SSR (Server-Side Rendering)** | On server, per request | SEO, dynamic content, first-paint speed |
| **CSR (Client-Side Rendering)** | In browser, after JS loads | Highly interactive apps, dashboards |
| **SSG (Static Site Generation)** | At build time | Blogs, docs, marketing pages |
| **Hydration** | SSR + CSR: server sends HTML, client "hydrates" with interactivity | React Next.js, Nuxt: SEO + interactivity |

**Latency implications**:
- **SSR**: User waits for server to render. TTFB (Time to First Byte) matters.
- **CSR**: User waits for JS to load and run. Larger JS bundles = slower.
- **SSG**: Content is pre-built; CDN can serve. Very fast for static content.

**Staff-level**: Choosing a rendering strategy affects your backend (Do you need a Node layer for SSR? Or is it all static + API?), your CDN strategy, and your client bundle size. There's no single "best" choice—it depends on the product's needs.

### Why This Matters at Scale

Rendering strategy directly impacts **Time to First Contentful Paint (FCP)** and **Largest Contentful Paint (LCP)**—metrics that affect user engagement and SEO. SSR can deliver FCP in 200–400 ms; CSR might add 500–1000 ms for JS parse and hydration. At millions of users, a 200 ms improvement in LCP can materially affect revenue. Staff engineers instrument these metrics, A/B test rendering approaches, and choose based on data—not convention.

### ASCII Diagram: Rendering Strategies Compared

```
    SSR (Server-Side Rendering)          CSR (Client-Side Rendering)
    
    Browser ──► Server ──► Render HTML   Browser ──► Server ──► Send minimal HTML
         │           │          │              │           │
         │           │          │              │           │  + JS bundle
         │           │          ▼              │           └─────────────►
         │           │     [Full HTML]         │
         │           │          │              │  Browser loads JS
         │           │          ▼              │  JS fetches data
         │           │     User sees page      │  JS renders
         │           │     (fast first paint)  │  User sees page
         │           │                        │  (slower first paint)
         
    SSG (Static Site Generation)         HYBRID (e.g., Next.js)
    
    Build time: Generate HTML             First request: SSR (SEO, fast)
    Deploy: Push to CDN                    Subsequent: CSR (interactive)
    Request: CDN serves static HTML        Best of both for many apps
    (fastest possible)
```

## API Design for Frontend Consumption

### Over-fetching and Under-fetching

- **Over-fetching**: Client gets more data than it needs. Wastes bandwidth, slows response.
- **Under-fetching**: Client needs multiple requests to build a view. Adds latency (waterfall requests).

**REST approach**: Design endpoints that match view needs. E.g., `GET /feed` returns the full feed for the home page instead of requiring N calls for user, posts, likes, etc.

**GraphQL approach**: Client specifies exactly what it needs in a query. One request, one response, no over/under-fetching. Trade-off: more complex server implementation, potential for expensive queries if not constrained.

### GraphQL vs REST (Simplified)

| Aspect | REST | GraphQL |
|--------|------|---------|
| **Data shape** | Server-defined | Client-defined (within schema) |
| **Endpoints** | Many (one per resource/view) | One (query endpoint) |
| **Over/under-fetch** | Can occur | Client controls |
| **Caching** | HTTP caching works well | Query-level caching, more complex |
| **Complexity** | Simpler | More flexible, more to implement |

**Staff-level**: GraphQL suits frontends with diverse data needs and many clients. REST suits simpler cases and when HTTP caching is important. The choice affects backend architecture (resolvers, N+1 prevention) and operational complexity.

**GraphQL trade-offs in depth**: GraphQL gives clients control over the response shape, which reduces over-fetching. But it introduces complexity: N+1 queries (each resolver may hit the DB separately; need DataLoader or batching), expensive queries (clients can request deeply nested data; need query depth/size limits and timeout), and caching (no standard HTTP cache key; need persisted queries or query hashing). REST + well-designed endpoints often avoids these. Choose GraphQL when the flexibility benefit outweighs the implementation cost—e.g., many client types (web, mobile, partners) with different needs, or rapid iteration on data shape. For a single client and stable resources, REST is simpler.

## ASCII Diagram: Frontend → BFF → Backend Services → Databases

```
    ┌────────────────────────────────────────────────────────────┐
    │                      FRONTEND LAYER                         │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
    │  │   Web App    │  │ Mobile App  │  │ Desktop App │        │
    │  │ (React/Vue)  │  │ (iOS/Android)│  │ (Electron)  │        │
    │  └──────┬───────┘  └──────┬──────┘  └──────┬──────┘        │
    └─────────┼─────────────────┼────────────────┼──────────────┘
              │                 │                 │
              │   API calls      │                 │
              ▼                 ▼                 ▼
    ┌────────────────────────────────────────────────────────────┐
    │                     BFF LAYER (optional)                     │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
    │  │   Web BFF   │  │ Mobile BFF  │  │  Shared API │        │
    │  └──────┬───────┘  └──────┬──────┘  └──────┬──────┘        │
    └─────────┼─────────────────┼────────────────┼──────────────┘
              │                 │                 │
              └─────────────────┼─────────────────┘
                                │
                                ▼
    ┌────────────────────────────────────────────────────────────┐
    │                   BACKEND SERVICES                           │
    │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐        │
    │  │  Auth   │ │  User   │ │  Feed   │ │ Payment │ ...      │
    │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘        │
    └───────┼──────────┼──────────┼──────────┼──────────────────┘
            │          │          │          │
            ▼          ▼          ▼          ▼
    ┌────────────────────────────────────────────────────────────┐
    │                    DATABASE LAYER                            │
    │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐        │
    │  │ Users   │ │ Posts   │ │ Orders  │ │ Payments│        │
    │  │   DB    │ │   DB    │ │   DB    │ │   DB    │        │
    │  └─────────┘ └─────────┘ └─────────┘ └─────────┘        │
    └────────────────────────────────────────────────────────────┘
```

### L5 vs L6: Frontend/Backend Split

| Aspect | L5 Thinking | L6 Thinking |
|--------|-------------|-------------|
| **Boundary** | "Frontend calls our API" | "The API is our contract; we version it; we own backward compatibility" |
| **Rendering** | "We use React" | "We use React with SSR for SEO-critical pages, CSR for app shell; here's the trade-off" |
| **BFF** | "We have one API" | "Web and mobile need different payloads; we'll add a BFF to avoid over-fetching" |
| **Scale** | "Backend scales with traffic" | "Frontend scales with users (CDN, static assets); backend scales with request volume; we need different strategies" |

---

# Part 3: What is a Database and Why Do We Need It?

## Data Persistence: State That Survives Restarts

A **database** provides **persistent storage**—data that survives process restarts, server failures, and power loss. Without it, everything would be ephemeral: close the app, restart the server, and the data is gone.

In-memory structures (variables, caches) are fast but volatile. Databases trade some speed for **durability** and **queryability**. They're the **source of truth** for critical business data.

## Relational Databases (PostgreSQL, MySQL)

**Relational** databases organize data into **tables** (relations) with **rows** and **columns**. They support:
- **SQL** for declarative queries
- **ACID transactions** (Atomicity, Consistency, Isolation, Durability)
- **Structured schemas** with types, constraints, foreign keys
- **Joins** across tables
- **Indexes** for fast lookups

**Best for**: Structured data, complex queries, consistency requirements, reporting.

**ACID in brief**: **Atomicity** — a transaction either fully commits or fully rolls back; no partial updates. **Consistency** — the database moves from one valid state to another; invariants hold. **Isolation** — concurrent transactions don't see each other's intermediate state (with isolation levels from read-uncommitted to serializable). **Durability** — committed data survives crashes. These guarantees make relational DBs the default for financial and transactional systems, but they come with coordination cost that limits horizontal scaling.

## NoSQL Overview

"NoSQL" lumps together several different models:

| Type | Examples | Model | Best For |
|------|----------|-------|----------|
| **Key-value** | Redis, DynamoDB | Key → value | Caching, sessions, simple lookups |
| **Document** | MongoDB, CouchDB | Document (JSON/BSON) | Flexible schema, hierarchical data |
| **Column-family** | Cassandra, HBase | Rows with column families | Write-heavy, time-series, wide tables |
| **Graph** | Neo4j, Neptune | Nodes, edges | Relationships, recommendations, fraud |

**When to use which**:
- **Structured queries, joins, transactions** → SQL (relational)
- **Flexible schema, nested documents** → Document store
- **Simple get/put by key** → Key-value
- **Relationships as first-class** → Graph
- **Massive write scale, eventually consistent** → Column-family

**Staff-Level Insight**: There's no "best" database—there are trade-offs. SQL gives you flexibility in querying and strong consistency but can be harder to scale horizontally. NoSQL often sacrifices features (joins, transactions) for scale and flexibility. Choose based on access patterns, consistency needs, and scale requirements.

### Database Selection Quick Reference

| Use Case | Typical Choice | Rationale |
|----------|----------------|-----------|
| User accounts, orders, payments | PostgreSQL, MySQL | ACID, joins, mature tooling |
| Session store, rate limit counters | Redis | In-memory, sub-ms latency |
| Caching layer | Redis, Memcached | Fast, TTL support |
| Event stream, log ingestion | Kafka, Kinesis | Append-only, high throughput |
| Time-series metrics | InfluxDB, TimescaleDB | Optimized for time-ordered data |
| Full-text search | Elasticsearch | Indexing, relevance ranking |
| Graph data (social, recommendations) | Neo4j, Neptune | Native graph traversals |

Polyglot persistence—using different stores for different needs—is common at scale. Don't force one database to do everything.

## Database Selection Framework

Choosing a database is one of the most consequential decisions in system design. There's no universal "best"—only trade-offs. A disciplined approach is to ask a set of questions and use the answers to narrow the field.

### The Five Questions

1. **What's the data shape?**  
   - Tabular with fixed columns and relationships? → Relational (SQL).  
   - Flexible, nested documents? → Document store.  
   - Simple key-value? → Key-value.  
   - Rows with many columns, sparse? → Column-family.  
   - Nodes and edges, relationships first-class? → Graph.  
   - Time-ordered events or metrics? → Time-series.

2. **What's the access pattern?**  
   - Primary key lookups? → Key-value, document.  
   - Complex queries, joins, aggregations? → SQL.  
   - Range scans by partition key? → Column-family, document.  
   - Graph traversals (friends-of-friends)? → Graph.  
   - Append-only, stream processing? → Log (Kafka) or time-series.

3. **What are the consistency needs?**  
   - Strong consistency, ACID? → SQL, or carefully configured DynamoDB.  
   - Eventual consistency OK? → Many NoSQL options.  
   - Need distributed transactions? → SQL with 2PC, or SAGA pattern over eventually consistent stores.

4. **What's the scale expectation?**  
   - Single node sufficient? → PostgreSQL, MySQL.  
   - Multi-million QPS, PB of data? → Distributed stores (Cassandra, DynamoDB, Spanner).  
   - Write-heavy, append-only? → Kafka, Cassandra, time-series.

5. **What's the team expertise?**  
   - Strong SQL team? → Default to PostgreSQL unless scale forces otherwise.  
   - Need managed, low-ops? → DynamoDB, Aurora, Cosmos DB.  
   - Willing to operationalize complex systems? → Cassandra, Kafka.

### Decision Tree Diagram

```
                    START: What's the primary access pattern?
                                        │
            ┌───────────────────────────┼───────────────────────────┐
            │                           │                           │
            ▼                           ▼                           ▼
    Key lookups only?           Complex queries,             Graph traversals?
    Range scans?                 joins, aggregations?        (social, recs)
            │                           │                           │
            ▼                           ▼                           ▼
    ┌───────────────┐           ┌───────────────┐           ┌───────────────┐
    │ Key-Value or  │           │  Relational   │           │     Graph     │
    │ Document      │           │  (PostgreSQL, │           │ (Neo4j, etc.)│
    │ (Redis,       │           │   MySQL)      │           └───────────────┘
    │ DynamoDB,     │           └───────┬───────┘
    │ MongoDB)     │                   │
    └──────┬──────┘           Scale limits?
            │                           │
    Scale?  │                   ┌───────┴───────┐
            │                   │               │
            │                   ▼               ▼
            │           Single node OK    Need sharding,
            │           → Stay SQL        distributed?
            │                                   │
            ▼                                   ▼
    Read-heavy? Write-heavy?            ┌───────────────┐
            │                           │ Cassandra,    │
            ▼                           │ DynamoDB,     │
    ┌───────────────┐                   │ Spanner      │
    │ Time-series?  │                   └───────────────┘
    │ → InfluxDB,   │
    │   TimescaleDB │
    └───────────────┘
```

### When Each Database Type Wins

| Type | Wins When | Loses When |
|------|-----------|------------|
| **SQL (PostgreSQL, MySQL)** | You need joins, transactions, complex queries, mature tooling, and single-node or modest scale. | Write throughput or data size exceeds single node; need horizontal scale without application-level sharding. |
| **Key-value (Redis, DynamoDB)** | Simple get/put by key; need single-digit ms latency; predictable access pattern. | Need ad-hoc queries, joins, or flexible querying. |
| **Document (MongoDB)** | Flexible schema, nested documents, team prefers JSON. Good for catalog, content, config. | Need strong consistency, complex joins, or scale that exceeds single-shard designs. |
| **Column-family (Cassandra)** | Write-heavy, append-heavy; global distribution; need horizontal scale. | Need strong consistency, joins, or low-latency point reads (Cassandra favors partition scans). |
| **Graph (Neo4j)** | Relationships are the primary access pattern: recommendations, fraud, social. | Tabular reporting, high-volume simple lookups, or team has no graph expertise. |
| **Time-series (InfluxDB, TimescaleDB)** | Metrics, events, IoT; time-ordered; heavy aggregation by time range. | General-purpose CRUD; need joins across non-time dimensions. |

**Staff-level**: Don't default to "we use PostgreSQL for everything" or "we use the company standard." Justify: "We chose DynamoDB because our access pattern is key-value at 100K QPS with single-digit ms latency. We accepted the loss of ad-hoc SQL. If our query needs evolve, we'd reconsider."

### Hybrid and Edge Cases

Some workloads don't fit neatly into one bucket. Staff engineers recognize these and make deliberate choices:

- **Search + transactional**: E-commerce needs product search (full-text, facets) and order data (ACID). Common pattern: PostgreSQL for orders; Elasticsearch for search, synced via CDC or dual-write. Two systems, clear ownership of what lives where.

- **Graph + high volume**: Recommendation systems need graph traversals but at scale. Options: Dedicated graph DB (Neo4j) for small-to-medium; or denormalize graph into a key-value/document store and do multi-hop in application logic for very high scale. Trade-off: flexibility vs. performance.

- **Time-series + relational**: IoT or metrics with both event streams and relational queries (e.g., "devices by customer"). Hybrid: write to time-series store (InfluxDB, TimescaleDB) for metrics; relational for device metadata and customer data. Join in application or materialized views.

- **When in doubt**: Start with PostgreSQL (or MySQL) if you have relational data and modest scale. It's versatile, well-understood, and you can always add specialized stores later. Premature optimization toward NoSQL often backfires when the team lacks operational experience.

## Database as the Hardest Thing to Scale

Why databases are usually the bottleneck:

1. **State**: Unlike stateless services, you can't just add servers. Data must be partitioned or replicated.
2. **Consistency**: Strong consistency requires coordination (locking, consensus), which limits scalability.
3. **Durability**: Writes must hit disk (or equivalent) before acknowledgment. Disk I/O is slower than memory.
4. **Connections**: Each application server needs connections. Connection pools help, but there's a limit.
5. **Single-writer**: Many databases have a single primary for writes. Write throughput is capped by that node.

**Why Staff Engineers Obsess About Databases**: Data model → query patterns → scaling strategy → cost. Get the data model wrong, and you'll struggle with queries. Get the query patterns wrong, and you'll struggle with scale. The database is often the last place you can fix performance without major rewrites.

**Practical scaling path**: Start with a single primary. Add read replicas when read load exceeds primary capacity. Use connection poolers (PgBouncer, ProxySQL) when connection count becomes an issue. Shard when write throughput or data size exceeds a single node. Each step has operational complexity—replication lag, consistency trade-offs, shard rebalancing. Staff engineers plan the path before they need it, so migrations happen deliberately rather than in crisis.

## Database Scaling Path: From Startup to Scale

Every scaling stage solves a problem—and introduces new ones. Understanding this timeline helps you plan migrations before crisis hits.

### Stage 1: Single Database (0–100K users, ~100–1K QPS)

**Setup**: One primary database. All reads and writes go to it.

**What it solves**: Simplicity. One deployment, one backup, one place to look when something breaks.

**What breaks**: Read load grows. Connection count grows. Single node has finite CPU, memory, disk I/O.

**New problems introduced**: None yet—this is baseline.

---

### Stage 2: Read Replicas (100K–1M users, ~1K–10K QPS)

**Setup**: Primary for writes; 1–N read replicas. Application routes reads to replicas, writes to primary.

**What it solves**: Read load distributed. Primary no longer overwhelmed by SELECTs.

**New problems**:
- **Replication lag**: Replicas are behind. Reads may see stale data. For "read your writes" you must read from primary.
- **Consistency**: Which replica to use? Sticky session? Random? Lag-based routing?
- **Failover**: Primary dies—promote a replica. Requires automation and testing.

---

### Stage 3: Connection Pooling (1K–10K connections)

**Setup**: PgBouncer, ProxySQL, or similar between app and DB. Pools connections; app thinks it has hundreds of connections, DB sees dozens.

**What it solves**: Connection exhaustion. Each app instance doesn't need N connections; the pool shares them.

**New problems**:
- **Pool sizing**: Too small = queuing. Too large = DB overwhelmed.
- **Transaction vs session mode**: PgBouncer in transaction mode can break prepared statements, advisory locks.
- **Another moving part**: One more service to monitor and fail over.

---

### Stage 4: Caching (10K–100K QPS reads)

**Setup**: Redis/Memcached in front of DB. Cache hot data. Cache-aside or read-through.

**What it solves**: DB load from repeated reads of same data. Latency improvement for cache hits.

**New problems**:
- **Invalidation**: When data changes, how do you invalidate? TTL? Write-through? Event-driven?
- **Consistency**: Cache can be stale. How stale is acceptable?
- **Thundering herd**: Cache miss → many requests hit DB. Need stampede protection.

---

### Stage 5: Sharding (100K+ QPS writes, 100M+ users, TB+ data)

**Setup**: Data partitioned across N shards. Each shard is a separate DB (or cluster). Application routes by shard key (e.g., user_id).

**What it solves**: Write throughput and storage limits. Each shard handles a fraction of load.

**New problems**:
- **Cross-shard queries**: Joins across shards are expensive or impossible. Denormalize or accept limitation.
- **Rebalancing**: Data grows unevenly. Need to split shards or migrate.
- **Global uniqueness**: Sequences, UUIDs across shards require coordination or different strategies.
- **Operational complexity**: N databases to back up, monitor, upgrade.

### Scaling Timeline: ASCII Diagram

```
    USERS (approx)    100      10K      100K     1M       10M      100M
    QPS (approx)      100      1K       10K      100K     1M       10M
                         │        │        │         │        │        │
                         ▼        ▼        ▼         ▼        ▼        ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │ STAGE 1: Single DB                                                 │
    │ ●────────●                                                         │
    │ One primary. All traffic.                                          │
    └─────────────────────────────────────────────────────────────────────┘
                              │
                              │ Read load grows
                              ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │ STAGE 2: Read Replicas                                             │
    │         ● (primary)                                                 │
    │        /|\                                                          │
    │       ● ● ● (replicas)                                              │
    │ Replication lag, failover complexity                                │
    └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Connection exhaustion
                                    ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │ STAGE 3: Connection Pooling                                        │
    │ App ──► [PgBouncer] ──► DB                                          │
    │ Hundreds of logical conns → dozens of physical                      │
    └─────────────────────────────────────────────────────────────────────┘
                                          │
                                          │ Repeated reads, hot data
                                          ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │ STAGE 4: Caching                                                    │
    │ App ──► [Redis] ──► DB (on miss)                                    │
    │ Cache invalidation, consistency trade-offs                           │
    └─────────────────────────────────────────────────────────────────────┘
                                                    │
                                                    │ Write limit, storage limit
                                                    ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │ STAGE 5: Sharding                                                   │
    │ Shard 1 │ Shard 2 │ Shard 3 │ ... │ Shard N                         │
    │ (user 0-1M) (1M-2M) (2M-3M)        (N-1 to N)                      │
    │ Cross-shard queries hard; rebalancing complex                        │
    └─────────────────────────────────────────────────────────────────────┘
```

At each stage: **What problem does it solve? What new problems does it introduce?** Staff engineers anticipate the next stage and design schema and access patterns so the migration is possible—e.g., leading with user_id in keys so sharding by user is feasible later.

## Data Modeling Basics

- **Tables**: Collections of related data (e.g., `users`, `orders`)
- **Rows**: Individual records
- **Columns**: Attributes (e.g., `id`, `name`, `email`)
- **Primary key**: Unique identifier for a row
- **Foreign key**: Reference to another table's primary key (e.g., `order.user_id` → `users.id`)
- **Index**: Data structure for fast lookups (e.g., index on `email` for login)

**Modeling for scale**: Partition/shard key choice is critical. You want data distributed evenly and queries to hit one partition when possible (avoid scatter-gather).

## Read/Write Ratio and Architecture

| Pattern | Read/Write | Typical Strategy |
|---------|------------|-------------------|
| **Read-heavy** | 100:1 or more | Read replicas, caching, CDN |
| **Write-heavy** | 1:1 or write-heavy | Sharding, async processing, batch writes |
| **Balanced** | ~10:1 | Replicas + connection pooling |

**Example**: A social feed might be 99% reads, 1% writes. Strategy: cache aggressively, use read replicas, maybe denormalize for feed queries. A metrics pipeline might be write-heavy: batch writes, use column-family or time-series DB, avoid synchronously reading what you write.

**Staff-level**: The read/write ratio drives your first major architectural choices. Get it wrong and you'll either over-provision for reads or drown your primary with write load.

## The Read/Write Ratio Deep Dive

The ratio of reads to writes is one of the most important inputs to database and architecture design. It determines your caching strategy, replication strategy, database choice, and where you'll hit limits first.

### Detailed Analysis by System Type

**Social media feed (99% reads, 1% writes)**:
- *Reads*: Feed loads, profile views, post views, like counts, comment counts. Millions of users refreshing feeds constantly.
- *Writes*: New posts, likes, comments, follows. Far less frequent.
- *Implications*:
  - **Caching**: Aggressive. Cache feed segments, hot posts, user profiles. TTL or event-driven invalidation.
  - **Replication**: Many read replicas. Primary handles writes; replicas serve reads. Replication lag of a few seconds is usually acceptable for feeds.
  - **Database**: PostgreSQL with read replicas works. Or DynamoDB with DAX (cache). Or a mix: Postgres for writes, Elasticsearch/Cassandra for feed reads if specialized.
  - **Denormalization**: Feed is often pre-computed—posts + engagement stored in a read-optimized shape. Write path is heavier (update many structures) but read path is trivial.

**IoT sensor data (99% writes, 1% reads)**:
- *Writes*: Devices send telemetry every second or minute. Millions of devices × high frequency = massive write throughput.
- *Reads*: Dashboards, alerts, analytics. Batch jobs. Much less frequent.
- *Implications*:
  - **Caching**: Minimal for writes. Maybe cache recent data for dashboards.
  - **Replication**: Write path is the bottleneck. Read replicas help for analytics but don't solve write scaling.
  - **Database**: Column-family (Cassandra) or time-series (InfluxDB, TimescaleDB). Append-optimized. Batching writes. Avoid transactional reads on the write path.
  - **Architecture**: Write to a log (Kafka) or append-only store; downstream consumers aggregate. Don't do real-time aggregation on every write.

**E-commerce (mixed, ~10:1 to 50:1 reads)**:
- *Reads*: Product catalog, search, cart view, order history. Browsing dominates.
- *Writes*: Add to cart, checkout, inventory updates, order creation. Fewer but critical.
- *Implications*:
  - **Caching**: Catalog and product pages heavily cached. Cart and checkout are user-specific—careful caching (per-user).
  - **Replication**: Read replicas for catalog, search. Primary for orders, inventory (strong consistency needed).
  - **Database**: Often PostgreSQL for orders (ACID); Redis for cart; search index (Elasticsearch) for catalog. Polyglot.
  - **Consistency**: Reads can be stale for catalog. Writes (orders, payment) need strong consistency. Different rules for different domains.

### How the Ratio Determines Strategy

| Read/Write | Caching Strategy | Replication Strategy | Database Choice |
|------------|------------------|----------------------|-----------------|
| **1000:1** | Cache aggressively. Long TTLs, read-through. | Many replicas. Primary rarely hit for reads. | SQL with replicas; consider read-optimized stores. |
| **100:1** | Cache hot data. Moderate TTL. | 2–5 replicas. | SQL standard. |
| **10:1** | Cache only hottest. | 1–2 replicas. | SQL. |
| **1:1** | Minimal caching. | Replicas for HA, not for read capacity. | Consider write-optimized if scale is high. |
| **1:10** | Almost no read caching. | Focus on write path. | Column-family, append logs, batching. |
| **1:100** | None. | Write scaling is the problem. | Cassandra, Kafka, time-series. Sharding by write partition. |

### Why Getting the Ratio Wrong Is Costly

**Treating writes like reads**: You add read replicas and caches to a write-heavy system. Writes still bottleneck on the primary. You've added complexity without solving the problem.

**Treating reads like writes**: You shard and optimize for writes when you're read-heavy. You've over-provisioned the write path and under-provisioned the read path. Users see slow pages; your primary is underutilized.

**Staff-Level Insight**: Measure the ratio in production. Instrument read vs. write QPS. "We thought we were read-heavy; we were 50:1. We thought we could tolerate replication lag; we couldn't for the checkout flow." Data beats intuition.

### Why This Matters at Scale

A **read-heavy** system (e.g., 1000:1) can tolerate eventual consistency for most reads—cache aggressively, use read replicas, accept slight staleness. A **write-heavy** system (e.g., metrics, event ingestion) needs a database and architecture optimized for writes: batching, append-only logs, column-family stores, horizontal partitioning. Mixing these up leads to either expensive over-provisioning (treating reads like writes) or data loss and corruption (treating writes like reads).

**Staff-Level Insight**: Before choosing a database, write down your expected read/write ratio and your top 5 query patterns. "We'll figure it out later" is expensive when the data model is baked in and migration is painful.

## Indexes: Why They Make Reads Fast and Writes Slow

An **index** is a data structure (e.g., B-tree) that lets the database find rows by a column value without scanning the whole table.

- **Reads**: With index on `email`, `SELECT * FROM users WHERE email = 'x'` does a lookup instead of full table scan. O(log n) vs O(n).
- **Writes**: Every insert/update/delete must update the index. More indexes = more write cost.

**Trade-off**: Index for query patterns you care about. Don't over-index—each one slows writes and consumes storage.

**Staff-Level Insight**: "We need an index for this query" is correct. "We need indexes for every column" is wrong. Understand your query patterns, index for the hot path, and monitor slow queries in production. Missing index = slow reads. Too many indexes = slow writes and bloated tables.

### Practical Numbers: Index Impact

| Table Size | Full Scan Time (rough) | With Index (rough) |
|------------|------------------------|--------------------|
| 10K rows   | ~1–5 ms                | ~0.1 ms            |
| 1M rows    | ~50–200 ms             | ~1–5 ms            |
| 100M rows  | Seconds                | ~10–50 ms          |

Indexes typically add 5–15% overhead per write (for a few indexes) to 50%+ (for many indexes on wide tables). Monitor write latency and storage growth.

## Connection Pools: Why Not One Connection Per Request

Opening a new database connection per request is expensive:
- **TCP handshake**
- **Authentication**
- **Connection state** (memory on DB server)

A **connection pool** maintains a set of open connections. The application checks out a connection, uses it, returns it to the pool. Connection setup cost is amortized across many requests.

**Pool sizing**: Too small = requests queue waiting for connections. Too large = overwhelm the database (each connection uses memory). Rule of thumb: pool size ≈ number of threads/processes × 1–2, bounded by DB max connections.

### Why This Matters at Scale

At 10K QPS, creating 10K connections per second to the database would be catastrophic. A pool of 50–100 connections, each handling requests in turn, keeps the DB manageable. Staff engineers tune pool size based on DB capacity and observed connection utilization.

## ASCII Diagram: Application → Connection Pool → Database

```
    ┌─────────────────────────────────────────────────┐
    │              APPLICATION SERVERS               │
    │  ┌─────────┐ ┌─────────┐ ┌─────────┐          │
    │  │  App 1  │ │  App 2  │ │  App 3  │  ...     │
    │  └────┬────┘ └────┬────┘ └────┬────┘          │
    │       │            │            │               │
    │       └────────────┼────────────┘               │
    │                    │                            │
    │                    ▼                            │
    │            ┌───────────────┐                    │
    │            │ Connection    │                    │
    │            │ Pool          │  (e.g., 20 conns   │
    │            │ (per server)  │   per server)      │
    │            └───────┬───────┘                    │
    └────────────────────┼────────────────────────────┘
                         │
                         │  Reuse connections,
                         │  don't create per-request
                         ▼
    ┌─────────────────────────────────────────────────┐
    │                   DATABASE                       │
    │  ┌─────────────────┐  ┌─────────────────┐      │
    │  │    Primary      │  │   Replicas       │      │
    │  │  (read + write)  │──│  (read-only)    │      │
    │  └─────────────────┘  └─────────────────┘      │
    └─────────────────────────────────────────────────┘
```

### L5 vs L6: Database Thinking

| Aspect | L5 Thinking | L6 Thinking |
|--------|-------------|-------------|
| **Choice** | "We use Postgres" | "We use Postgres for transactional data; Redis for cache; we'll need a different store for the activity stream" |
| **Scaling** | "We'll add read replicas" | "Read replicas help; we'll need sharding by user_id when we hit write limits; here's the migration path" |
| **Modeling** | "We'll add a table" | "This schema supports our query patterns; we've considered N+1 and added appropriate indexes" |
| **Connections** | "We use a connection pool" | "Pool size is 20 per instance; we have 50 instances = 1000 connections; DB max is 1500; we're within limit" |

## L5 vs L6 Database Thinking: Staff-Level Examples

Staff-level database decisions are explicitly about trade-offs. The choice is never "PostgreSQL is better" in the abstract—it's "we chose X because of Y, and we accept Z as a consequence."

### Example: DynamoDB vs PostgreSQL

**L5**: "We use DynamoDB for our user store."

**L6**: "We chose DynamoDB over PostgreSQL for our user profile store because we need single-digit millisecond reads at 100K QPS with predictable latency. DynamoDB gives us that with minimal ops. We accept the loss of ad-hoc SQL queries and cross-table joins—our access pattern is key by user_id and we've designed our data model around that. If our access pattern becomes more complex—e.g., we need to query users by email across the whole table, or do analytics joins—we'd reconsider. We might add a read replica to PostgreSQL synced via CDC, or we might introduce a different store for those workloads."

### Example: Polyglot Persistence Justified

**L5**: "We have Postgres and Redis."

**L6**: "We use PostgreSQL for orders and payments—ACID and joins matter. We use Redis for session store and rate limiting—sub-millisecond reads, TTL support, no durability requirement for that data. We use Elasticsearch for product search—full-text and faceting. We use Kafka for the event stream—append-only, high throughput, consumers can replay. Each store is chosen for its access pattern. We've documented which system is source of truth for which domain so we don't create consistency nightmares."

### Example: Migration Path

**L5**: "We'll shard when we need to."

**L6**: "Our schema uses user_id as the leading column in all user-scoped tables. When we hit write limits on the primary, we'll shard by user_id—each shard gets a contiguous range. We've avoided cross-shard queries in the hot path. We have a migration plan: dual-write during transition, then cut over reads. We'll need to handle in-flight writes during cutover. We've run the migration in staging; it took 4 hours for our dataset size. We'll schedule a maintenance window."

**Staff-level**: The justification includes the trade-off (what we gave up), the conditions for change ("if X happens we'd reconsider"), and the operational reality (migration path, timelines).

---

# Why This Matters at Scale: Cross-Cutting Themes

## APIs at Scale

As API traffic grows:
- **Rate limiting** becomes critical (protect backend, ensure fair use)
- **Authentication** at scale requires caching (JWT validation, session lookups)
- **API gateway** must scale horizontally—it's in the critical path
- **Versioning** and **deprecation** require process; breaking changes affect many consumers

**Staff-Level Insight**: "Our API handles 100K QPS" means the gateway, the auth layer, and every downstream service must handle their share. Capacity planning for APIs includes the gateway, the auth service, and the fan-out to backend services.

## Frontend/Backend at Scale

- **Frontend**: Static assets on CDN; API responses may be cached (carefully—don't cache user-specific data wrongly). Client-side caching reduces server load.
- **Backend**: Stateless services scale horizontally; state (sessions, etc.) moves to distributed cache or DB.
- **BFF**: If you have one BFF per client type, each must scale. Or you consolidate and accept some over-fetching.

## Databases at Scale

- **Read scaling**: Read replicas, caching, read-through caches.
- **Write scaling**: Sharding, async processing, batching.
- **Connection scaling**: Pools, proxy layers (e.g., PgBouncer), serverless connection managers.

**Staff-Level Insight**: The database is the last bastion. When everything else scales horizontally, the database often remains the choke point. Staff engineers plan for this from day one: schema that can shard, query patterns that stay local to a shard, and a path to split or migrate when limits approach.

**Monitoring and alerting**: Database health is critical. Monitor: connection count, query latency (p50, p95, p99), replication lag, disk usage, CPU and memory. Alert on: connection exhaustion, lag exceeding SLA, slow queries. Have runbooks for: failover, adding replicas, scaling the pool. The database is often the last place you want surprises.

**Backup and recovery**: Know your RPO (Recovery Point Objective) and RTO (Recovery Time Objective). How much data can you lose? How long can you be down? Automated backups, point-in-time recovery, and tested restore procedures are table stakes. Staff engineers ensure these exist and are regularly validated.

### Schema Design for Evolvability

Database schemas are hard to change once in production. Staff engineers design for change from the start. Practices: avoid storing computed data that could be derived (denormalize only when read performance demands it); use flexible types (e.g., JSONB in Postgres) for truly variable data; avoid over-indexing—each index slows writes and complicates migration; document the rationale for each constraint so future engineers understand trade-offs. When migration is needed, use expand-contract: add new column, backfill, switch reads to new column, deprecate old column. Never drop a column without a deprecation period—a consumer might still rely on it. Staff-level schema design anticipates that requirements will change and minimizes the cost of that change.

---

# Example in Depth: How Stripe Designs APIs and Data

**Stripe** is a canonical example of API-first, data-critical design. Their choices illustrate how APIs and databases are designed for **stability**, **evolvability**, and **correctness** at scale.

## API Design in Practice

- **Idempotency by default**: Every mutating request (charge, refund, payout) takes an **idempotency key** from the client. Same key retried = same result; no double charges. This is a **first-class part of the contract**, not an afterthought.
- **Versioning**: Stripe versions the API (e.g. `2023-10-16`). New versions add or change behavior; old versions are supported for a documented period. Applications set the version in the request so behavior is **predictable** across releases.
- **Webhooks for async outcomes**: Charges and payouts complete asynchronously. Clients don’t poll; Stripe sends **webhooks** (with retries and signing). The API design separates "initiate" (sync) from "outcome" (async), which matches how payments actually work.
- **Structured errors**: Errors return a type (e.g. `card_error`, `rate_limit_error`), code (e.g. `insufficient_funds`), and message. Clients can **handle by type** and **display or log** consistently. Request IDs support support and debugging.

**Takeaway**: APIs that handle money or critical state need **idempotency**, **versioning**, **async completion (webhooks)**, and **structured errors**. The same principles apply to any high-stakes API (e.g. orders, inventory, billing).

## Database and Data Model Thinking

- **Ledger-style correctness**: Financial systems often use **ledger** or **event-sourced** models: append-only records of every debit/credit. Balance is derived; you never "update balance" without a corresponding event. This gives **auditability** and **correctness** under retries and failures.
- **Idempotency in storage**: Stripe stores idempotency keys and the **result** of the first request. A retry with the same key returns the stored result instead of re-running the operation. The database is part of the **idempotency contract**.
- **Strong consistency where it matters**: For charges and balance-affecting operations, Stripe uses **strong consistency** (single primary, synchronous replication for critical paths). Eventual consistency is reserved for non-financial data (e.g. some reporting).

**Takeaway**: For payment-like systems, **data model** (ledger/events), **idempotency in the DB**, and **consistent reads/writes** are design requirements, not options. Staff engineers make these explicit and trade off complexity (e.g. event sourcing) for correctness.

## Breadth: API and Database Anti-Patterns, Edge Cases

| Anti-pattern | Why it hurts | Better approach |
|--------------|--------------|------------------|
| **No idempotency for writes** | Retries (network, client, load balancer) cause duplicates: double charge, double order. | Idempotency keys (or equivalent) for every mutating operation; store key → result; return stored result on retry. |
| **Breaking changes without versioning** | Deploy breaks all existing clients at once. | Versioned API; additive changes; deprecation window; migrate consumers before removing. |
| **One giant response** | `/users` returns 10,000 users; slow, memory-heavy, often unnecessary. | Pagination (cursor or offset), field selection, or sparse fieldsets. |
| **Database as implementation detail** | "We'll use the DB that’s already there" with no access-path analysis. | Model **access patterns** first (key lookup, range, join, full-text); choose store and schema to match; plan indexing and scaling. |
| **Ignore read/write ratio** | Write-optimized store for read-heavy workload (or the reverse). | Measure or state read/write ratio; choose store and replication (read replicas, cache) to fit. |
| **No error contract** | Ad-hoc error bodies and codes; clients can’t handle consistently. | Standard error shape (code, message, request_id, docs link); use HTTP status + body; document every code. |

**Edge cases:**

- **Pagination**: Offset pagination (`page=2`) breaks when data changes between requests (skips or duplicates). **Cursor-based** (e.g. `after=id_123`) is stable under inserts/deletes and scales better for large datasets.
- **Optional vs required fields**: Adding a **required** field breaks existing clients. Prefer **optional** new fields and default values; migrate consumers; only then consider required.
- **Backward compatibility**: Removing a field or changing type is breaking. **Expand–contract**: add new field, migrate, then deprecate old. Never remove in a single release without a compatibility window.

---

# Summary: From Building Blocks to Staff-Level Architecture

APIs, frontend, backend, and databases are the building blocks. At Staff level, you use them to:

1. **Design APIs as contracts** — versioned, documented, backward-compatible; they are team boundaries
2. **Place the frontend/backend boundary intentionally** — considering BFF, rendering strategy, and ownership
3. **Choose databases from access patterns** — read/write ratio, consistency needs, query shapes
4. **Plan for scale at every layer** — APIs, BFFs, backends, and especially databases

The basics are simple. The Staff-level work is in the trade-offs: when to add a BFF, when to choose GraphQL over REST, when to split a database, when to add a cache. Master the building blocks, then master the decisions that turn them into systems that scale.

---

# Interview Application: How API and Database Questions Appear in Staff Interviews

API and database design questions are common in Staff-level system design interviews. The interviewer is probing for: Can you design stable, evolvable APIs? Can you choose and justify database technology from first principles? Do you think about operational reality?

## How These Topics Appear

**API questions** often come in two forms:
1. **Explicit**: "Design an API for a ride-sharing system." "How would you design the Stripe API?"
2. **Embedded**: As part of a larger design ("Design a notification system"), the interviewer expects you to discuss API design—endpoints, versioning, error handling, backward compatibility.

**Database questions** similarly:
1. **Explicit**: "How would you store and query [X]?" "SQL vs NoSQL—when would you use each?"
2. **Embedded**: In any system design, you'll need to discuss data storage. The interviewer listens for: Do you justify your choice? Do you consider scale, consistency, access patterns?

## Common Mistakes

| Mistake | Why It's a Problem | Better Approach |
|---------|-------------------|-----------------|
| **Choosing a database without justifying** | "We'll use MongoDB" with no rationale. | "We need flexible schema for user-generated content that varies by type. Document store fits. We've considered consistency—eventual is OK for this use case." |
| **Designing APIs without backward compatibility** | "We'll change the field name." | "We'll add a new optional field, deprecate the old one in 6 months, migrate consumers, then remove." |
| **Ignoring the read/write ratio** | Picking a write-optimized DB for a read-heavy system. | "We're 100:1 read-heavy. We'll use PostgreSQL with read replicas and Redis cache." |
| **Over-engineering the API** | Proposing GraphQL when REST suffices. | "REST fits our resource model. We'd consider GraphQL if we had many clients with divergent data needs." |
| **No pagination or error format** | Designing endpoints without considering list size or error handling. | "All list endpoints use cursor pagination. Errors follow a standard format with code, message, request_id." |
| **Treating the DB as an afterthought** | Designing services first, then "we'll need some database." | Data model and access patterns drive the design. "Our primary query is X; that suggests this schema and this indexing strategy." |

## What Strong Answers Look Like

**API**: "We'll expose resources as REST: `/users`, `/users/:id/orders`. We'll version from day one—`/v1/users`. We'll use cursor pagination for lists. Errors will have a standard body with code, message, and request_id. For breaking changes, we'll add optional fields and deprecate with 6-month notice. We'll document rate limits and SLAs for external consumers."

**Database**: "Our access pattern is key lookup by user_id at 50K QPS, with occasional range scans by time. Read/write ratio is 20:1. We'll use PostgreSQL with a read replica and Redis cache for hot user profiles. The schema leads with user_id so we can shard later if needed. We'll use connection pooling—20 connections per instance, 50 instances, 1000 total; DB max is 1500."

## Opening Moves When the Question Involves APIs or Databases

1. **Clarify consumers**: "Who are the API consumers? Internal services, mobile, partners?" This drives auth, rate limits, versioning strictness.
2. **Clarify access patterns**: "What are the primary queries? Key lookup? Range scan? Joins? Full-text?" This drives database choice and schema.
3. **Clarify consistency**: "Do we need strong consistency for any operations? Which can be eventually consistent?" This drives replication and caching strategy.
4. **State trade-offs explicitly**: "We're choosing X over Y because of Z. We accept that we lose [capability]."

### Sample Follow-up Questions and Strong Responses

**"Why did you choose REST over GraphQL?"**  
"REST fits our resource model and we have mature tooling. Our clients need predictable, cacheable responses. GraphQL would help if we had many clients with divergent data needs—we don't yet. We'd reconsider if we add a mobile app that needs batched, tailored payloads."

**"How would you handle a breaking API change?"**  
"We'd add a new optional field or endpoint. Deprecate the old one with 6-month notice. Track usage of deprecated paths. Proactively contact consumers. Remove only after migration. We'd version the API so v1 and v2 can coexist during transition."

**"Why PostgreSQL over DynamoDB for this use case?"**  
"We need joins across users and orders for reporting. We need ACID for payments. Our scale is modest—single digit K QPS. PostgreSQL gives us flexibility and strong consistency. DynamoDB would force us to denormalize and give up ad-hoc queries. If we hit scale limits, we'd add read replicas or consider sharding before switching stores."

**"How do you handle API rate limiting?"**  
"We rate limit at the API gateway by client (user ID or API key). We use a token bucket—allows bursts but caps sustained rate. We return 429 with Retry-After header. For internal services, we may use different limits or no limit. We expose usage metrics so clients can monitor their consumption. For critical partners, we might offer higher limits or dedicated capacity."

---

# Interview Takeaways: What to Demonstrate

When discussing APIs, frontend, backend, and databases in an interview, Staff-level candidates:

- **Treat the API as a contract**: "We'll version our API from day one. V1 will support our current use cases; we'll add optional fields for new features rather than breaking changes. Deprecation will have a 6-month runway."
- **Justify the frontend/backend boundary**: "We're using a BFF for mobile because the mobile app needs a different payload shape—fewer fields, batched responses—and we want to avoid over-fetching. The web can use the shared API directly for now."
- **Explain database choice from access patterns**: "We're read-heavy with a 100:1 ratio. We'll use PostgreSQL with read replicas and a Redis cache for hot data. The primary handles writes; reads are distributed. When we hit write limits, we'll shard by user_id."
- **Connect data model to scaling**: "Our schema uses user_id as the leading key in our main tables, so when we shard we can keep user data co-located. We've avoided cross-shard joins in our hot path."
- **Discuss operational concerns**: "We'll use connection pooling with 20 connections per app instance. With 50 instances, that's 1000 connections; our DB max is 1500, so we have headroom. We'll monitor connection utilization."

The interviewer is listening for: Do you make intentional trade-offs? Do you connect technical choices to business and operational reality?

**Synthesis**: APIs, frontend, backend, and databases are not isolated topics. They connect: the API defines the contract between frontend and backend; the database choice affects what the API can efficiently expose; the frontend's rendering strategy affects what the backend must provide. Staff-level candidates weave these together—"Our BFF exists because mobile needs a different payload; we use cursor pagination for our lists because our data changes frequently; we chose PostgreSQL because we need joins for the order history view." The ability to connect these dots—and to justify each choice from first principles—signals readiness for Staff-level system design. In practice, the most impactful decisions are often the ones at these boundaries: API contracts that outlast implementation, database schemas that can evolve, and rendering strategies that balance performance and flexibility. Get these right, and the rest follows.

**Cross-cutting checklist for Staff interviews**: Before diving into implementation, cover: (1) API: versioning strategy, error format, pagination, backward compatibility. (2) Frontend/backend: BFF need, rendering strategy, caching layers. (3) Database: choice justified by access pattern and read/write ratio; scaling path documented; schema designed for evolution. (4) Operations: connection pooling, monitoring, backup and recovery. Addressing each of these explicitly shows breadth and depth. The interviewer has limited time—prioritize the decisions that are hardest to change later: API contracts, database choice, and system boundaries.

**Real-world integration**: In production systems, API and database decisions often ripple across teams. A poorly designed API creates friction for every consumer—internal teams file tickets, external partners complain, and mobile app releases get blocked. A database choice that doesn't match access patterns leads to slow queries, emergency indexing, and ultimately migration. Staff engineers treat these as cross-team concerns: they consult consumers before locking in API contracts, they model access patterns before choosing a database, and they document the rationale so future maintainers understand the trade-offs. This collaborative, evidence-based approach to API and database design is what separates Staff-level ownership from merely implementing a spec. When you leave an interview, the interviewer should remember not just your technical choices but your reasoning: why this API shape, why this database, why this boundary. That reasoning is the Staff-level signal. Master the building blocks, justify your choices, and connect them to the larger system. That is what Staff-level API and database thinking looks like in practice. Demonstrate it clearly, and you will stand out in the interview.
